"""Stage 3 (ghidra-reconstruction): callee-first function groups and their plans.

The producer is file-only and deterministic.  It reads the immutable ELF:

* functions are the sized ``FUNC`` symbols, one node per start address;
* a call edge is a ``jal`` to another function's start, and a tail call is a
  ``j`` to another function's start (both decoded from the instruction, so
  calls through section symbols count too); targets that land inside a body
  or outside every function are recorded as anomalies, not edges;
* recursive strongly connected components stay in one group;
* a component's height is the longest chain of distinct components it calls;
* groups pack whole components of one height, in address order, up to
  ``RECON_GROUP_SIZE`` functions.

Each group becomes a file-only plan item (evidence plus a reviewed change
list) and a live apply item.  A plan item depends on the apply items of the
groups holding its callees, so callee contracts are live before callers are
planned.  Indirect calls (vtables, function pointers) are not edges.

``group_evidence`` gathers, per function, the facts a planner starts from:
ELF names and demangling, the compile unit, the DWARF record and the stage 2
outcome, argument registers read at entry, direct callees and callers, and
the data the function's relocations reference.  ``build_recon_program``
translates an accepted plan into the batch-apply program format, so the
existing executor applies and reads back every change.
"""

from __future__ import annotations

import bisect
import hashlib
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from .batch_apply import (
    BATCH_PROGRAM_KIND,
    BATCH_PROGRAM_SCHEMA,
    BUILTINS,
    CALLING_CONVENTION,
    UNDEFINED_TYPES,
    UNSPELLABLE,
    _base_type,
    _data_alias_problem,
    _declared_argument_registers,
    _entry_argument_reads,
    _shown_type,
    _thunk_target,
    build_batch_program,
    claims_nothing,
    expected_signature,
    parse_signature,
)
from .constants import REFERENCE_SHA256
from .elf import Elf32File
from .mwdemangle import demangle, readable_component
from .util import SocomError, atomic_write_json, canonical_json, load_json, sha256_file, stable_id

RECON_GROUP_SIZE = 32
RECON_GRAPH_KIND = "socom-recon-function-graph"
RECON_EVIDENCE_KIND = "socom-recon-group-evidence"
RECON_PLAN_KIND = "socom-ghidra-recon-plan"
RECON_SCHEMA = 1
RECON_PLAN_KINDS = ("recon-plan-group", "recon-apply-group")
GROUP_PREFIX = "socom:recon-group:"
# A recon repair corrects prototypes of functions in applied groups: a
# file-only plan in the recon plan row format and a live apply item.
REPAIR_PLAN_KIND = "recon-repair-plan"
REPAIR_APPLY_KIND = "recon-repair-apply"
REPAIR_PREFIX = "socom:work:recon-repair-"
PLAN_ITEM_KINDS = ("recon-plan-group", REPAIR_PLAN_KIND)
APPLY_ITEM_KINDS = ("recon-apply-group", REPAIR_APPLY_KIND)
ARGUMENT_GPR_NAMES = {4: "a0", 5: "a1", 6: "a2", 7: "a3", 8: "t0", 9: "t1", 10: "t2", 11: "t3"}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# -- graph -----------------------------------------------------------------


def _functions(elf: Elf32File) -> list[dict[str, Any]]:
    by_start: dict[int, dict[str, Any]] = {}
    for symbol in elf.symbols():
        if symbol.type_name != "FUNC" or not symbol.size:
            continue
        row = by_start.setdefault(symbol.value, {"start": symbol.value, "size": symbol.size, "names": set()})
        if row["size"] != symbol.size:
            raise SocomError(f"function symbols at 0x{symbol.value:x} disagree on size")
        if symbol.name:
            row["names"].add(symbol.name)
    rows = sorted(by_start.values(), key=lambda row: row["start"])
    for previous, current in zip(rows, rows[1:]):
        if previous["start"] + previous["size"] > current["start"]:
            raise SocomError(f"functions at 0x{previous['start']:x} and 0x{current['start']:x} overlap")
    for row in rows:
        row["names"] = sorted(row["names"])
    return rows


def _code_word(elf: Elf32File) -> Any:
    segment = next(elf.load_segments())

    def word(address: int) -> int:
        offset = segment.offset + address - segment.virtual_address
        return int.from_bytes(elf.data[offset : offset + 4], "little")

    return word


def _sccs(nodes: list[int], edges: dict[int, list[int]]) -> list[list[int]]:
    """Tarjan's components, callees before callers, deterministic for sorted input."""

    index: dict[int, int] = {}
    low: dict[int, int] = {}
    on_stack: set[int] = set()
    stack: list[int] = []
    components: list[list[int]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(edges.get(root, ())))]
        while work:
            node, successors = work[-1]
            successor = next(successors, None)
            if successor is not None:
                if successor not in index:
                    index[successor] = low[successor] = counter
                    counter += 1
                    stack.append(successor)
                    on_stack.add(successor)
                    work.append((successor, iter(edges.get(successor, ()))))
                elif successor in on_stack:
                    low[node] = min(low[node], index[successor])
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(sorted(component))
    return components


def function_graph(root: Path) -> dict[str, Any]:
    """The direct call graph of every sized function, from instructions alone."""

    elf = Elf32File(root / "support" / "socom.elf")
    word = _code_word(elf)
    functions = _functions(elf)
    starts = [row["start"] for row in functions]
    start_set = set(starts)

    def owner(address: int) -> int | None:
        position = bisect.bisect_right(starts, address) - 1
        if position >= 0 and address < functions[position]["start"] + functions[position]["size"]:
            return functions[position]["start"]
        return None

    edges: dict[int, set[int]] = defaultdict(set)
    sites: dict[tuple[int, int], list[int]] = defaultdict(list)
    anomalies: list[dict[str, Any]] = []
    self_calls: set[int] = set()
    for row in functions:
        start, end = row["start"], row["start"] + row["size"]
        for site in range(start, end, 4):
            insn = word(site)
            opcode = insn >> 26
            if opcode not in (0x02, 0x03):
                continue
            target = ((site + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)
            kind = "call" if opcode == 0x03 else "jump"
            if target == start and kind == "call":
                self_calls.add(start)
                continue
            if start <= target < end:
                if kind == "call":
                    anomalies.append({"site": f"0x{site:x}", "target": f"0x{target:x}", "kind": "call into own body"})
                continue
            if target in start_set:
                edges[start].add(target)
                sites[(start, target)].append(site)
                continue
            holder = owner(target)
            anomalies.append(
                {
                    "site": f"0x{site:x}",
                    "target": f"0x{target:x}",
                    "kind": f"{kind} into the body of 0x{holder:x}" if holder is not None else f"{kind} outside every function",
                }
            )
    ordered_edges = {node: sorted(targets) for node, targets in edges.items()}
    components = _sccs(starts, ordered_edges)
    component_of = {member: number for number, component in enumerate(components) for member in component}
    height = [0] * len(components)
    for number, component in enumerate(components):
        for member in component:
            for target in ordered_edges.get(member, ()):
                other = component_of[target]
                if other != number:
                    height[number] = max(height[number], height[other] + 1)
    callers: dict[int, list[int]] = defaultdict(list)
    for source, targets in ordered_edges.items():
        for target in targets:
            callers[target].append(source)
    return {
        "functions": functions,
        "edges": ordered_edges,
        "callers": {node: sorted(values) for node, values in callers.items()},
        "call_sites": {key: sorted(value) for key, value in sites.items()},
        "components": components,
        "component_of": component_of,
        "height": height,
        "self_recursive": sorted(self_calls),
        "anomalies": anomalies,
    }


def _hex(value: int) -> str:
    return f"0x{value:x}"


def recon_groups(root: Path, group_size: int = RECON_GROUP_SIZE) -> dict[str, Any]:
    """Deterministic callee-first groups of whole recursive components."""

    if group_size < 1:
        raise SocomError("group size must be positive")
    graph = function_graph(root)
    components = graph["components"]
    by_height: dict[int, list[int]] = defaultdict(list)
    for number, component in enumerate(components):
        by_height[graph["height"][number]].append(number)
    packed: list[tuple[int, list[int]]] = []
    for level in sorted(by_height):
        current: list[int] = []
        for number in sorted(by_height[level], key=lambda value: components[value][0]):
            size = len(components[number])
            if current and sum(len(components[value]) for value in current) + size > group_size:
                packed.append((level, current))
                current = []
            current.append(number)
        if current:
            packed.append((level, current))

    group_of: dict[int, str] = {}
    groups = []
    for group_number, (level, numbers) in enumerate(packed, start=1):
        members = sorted(member for number in numbers for member in components[number])
        group_id = stable_id("recon-group", level, *(_hex(member) for member in members))
        for member in members:
            group_of[member] = group_id
        groups.append(
            {
                "id": group_id,
                "group_number": group_number,
                "height": level,
                "functions": [_hex(member) for member in members],
                "recursive_components": [
                    [_hex(member) for member in components[number]]
                    for number in numbers
                    if len(components[number]) > 1
                ],
            }
        )
    for group in groups:
        callees = {
            group_of[target]
            for member in group["functions"]
            for target in graph["edges"].get(int(member, 16), ())
        } - {group["id"]}
        group["callee_groups"] = sorted(callees)
    body = {
        "kind": RECON_GRAPH_KIND,
        "schema_version": RECON_SCHEMA,
        "source_sha256": REFERENCE_SHA256,
        "group_size": group_size,
        "function_count": len(graph["functions"]),
        "edge_count": sum(len(targets) for targets in graph["edges"].values()),
        "component_count": len(components),
        "recursive_component_count": sum(1 for component in components if len(component) > 1),
        "max_height": max(graph["height"], default=0),
        "anomalies": graph["anomalies"],
        "groups": groups,
    }
    body["graph_sha256"] = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return body


def group_sha256(batch: dict[str, Any]) -> str:
    """Digest identifying one group's membership and position."""

    identity = {key: batch[key] for key in ("group_number", "height", "functions", "graph_sha256")}
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def repair_sha256(batch: dict[str, Any]) -> str:
    """Digest identifying one recon repair's function list (a plan's ``group_sha256``)."""

    identity = {key: batch[key] for key in ("repair_number", "functions", "groups", "graph_sha256")}
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()


def plan_digest(item: dict[str, Any]) -> str:
    """The ``group_sha256`` a plan for this group or repair item must cite."""

    batch = item["batch"]
    return repair_sha256(batch) if item.get("kind") == REPAIR_PLAN_KIND else group_sha256(batch)


# -- evidence --------------------------------------------------------------


def code_data_references(root: Path) -> list[dict[str, Any]]:
    """Every data address an instruction's relocation proves, with its access.

    R_MIPS_LO16 completes the ``lui`` whose write reaches its base register
    (unresolved pairings are kept with their reason) and R_MIPS_GPREL16 is
    relative to the ``.reginfo`` $gp value.  Nothing is inferred from bytes.
    """

    from .ghidra import _IMMEDIATE_OPCODES, _LOAD_OPCODES, _STORE_OPCODES, _lo16_targets_cached, _sign16
    from .util import file_key

    path = root / "support" / "socom.elf"
    elf = Elf32File(path)
    word = _code_word(elf)
    gp = int.from_bytes(elf.section_data(".reginfo")[20:24], "little")
    lo16 = _lo16_targets_cached(file_key(path))
    rows = []
    for relocation in elf.relocations(".relmain"):
        name = relocation.type_name
        site = relocation.offset
        if name == "R_MIPS_LO16":
            pairing = lo16[site]
            target = pairing["target"]
            reason = pairing.get("reason")
        elif name == "R_MIPS_GPREL16":
            target = (gp + _sign16(word(site) & 0xFFFF)) & 0xFFFFFFFF
            reason = None
        else:
            continue
        opcode = word(site) >> 26
        access = (
            "READ"
            if opcode in _LOAD_OPCODES
            else "WRITE" if opcode in _STORE_OPCODES else "DATA" if opcode in _IMMEDIATE_OPCODES else f"opcode 0x{opcode:02x}"
        )
        row = {
            "site": _hex(site),
            "target": _hex(target) if target is not None else None,
            "access": access,
            "relocation": name,
        }
        if reason:
            row["unresolved"] = reason
        rows.append(row)
    return sorted(rows, key=lambda row: int(row["site"], 16))


def _stage2_outcomes(root: Path, tracker: dict[str, Any], batch_ids: set[str]) -> dict[int, dict[str, Any]]:
    """DWARF function rows and the stage 2 program's decision, by address."""

    from .import_plan import build_import_plan

    by_id = {row["id"]: row for row in tracker["work_items"]}
    outcomes: dict[int, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as scratch:
        for batch_id in sorted(batch_ids):
            item = by_id[batch_id]
            # The same batch view `debug import-plan --batch` resolves.
            batch = {"work_item_id": item["id"], "selection": item.get("selection"), **item["batch"]}
            plan = build_import_plan(root, batch)
            plan_path = Path(scratch) / "plan.json"
            atomic_write_json(plan_path, plan)
            program = build_batch_program(root, plan_path)
            decisions = {int(row["address"], 16): row for row in program["functions"]}
            for row in plan["functions"]:
                if not row.get("low_pc"):
                    continue
                decision = decisions.get(row["low_pc"]) or {}
                outcomes[row["low_pc"]] = {
                    "batch": batch_id,
                    "dwarf": {
                        key: row.get(key)
                        for key in (
                            "qualified_name",
                            "mangled_name",
                            "compile_unit_path",
                            "return_type",
                            "parameters",
                            "parameter_storage",
                            "locals",
                        )
                    },
                    "stage2": {
                        key: decision.get(key)
                        for key in ("readable_name", "receiver", "prototype", "prototype_skip", "notes")
                    },
                }
    return outcomes


def group_evidence(root: Path, tracker: dict[str, Any], item_id: str) -> dict[str, Any]:
    """File-only starting facts for one group's planner."""

    from .census import build_census

    item = next((row for row in tracker["work_items"] if row["id"] == item_id), None)
    if item is None or item.get("kind") not in PLAN_ITEM_KINDS:
        raise SocomError(f"{item_id} is not a reconstruction plan item")
    batch = item["batch"]
    graph = function_graph(root)
    decomposition = tracker_stage(tracker).get("decomposition") or {}
    groups = recon_groups(root, decomposition.get("group_size", RECON_GROUP_SIZE))
    if groups["graph_sha256"] != batch["graph_sha256"]:
        raise SocomError("the function graph differs from the decomposition; tools changed")
    group_of = {member: group["id"] for group in groups["groups"] for member in group["functions"]}
    elf = Elf32File(root / "support" / "socom.elf")
    starts = [row["start"] for row in graph["functions"]]
    by_start = {row["start"]: row for row in graph["functions"]}

    census = build_census(root, include_rows=False)
    units = sorted(
        (unit for unit in census["debug"]["compile_units"] if unit.get("low_pc") and unit.get("high_pc")),
        key=lambda unit: unit["low_pc"],
    )
    unit_batch = {
        cu: row["id"]
        for row in tracker["work_items"]
        if row.get("kind") == "debug-import-plan-batch"
        for cu in row["batch"]["compile_unit_ids"]
    }

    def unit_for(address: int) -> dict[str, Any] | None:
        position = bisect.bisect_right([unit["low_pc"] for unit in units], address) - 1
        if position >= 0 and address < units[position]["high_pc"]:
            return units[position]
        return None

    members = [int(value, 16) for value in batch["functions"]]
    member_units = {address: unit_for(address) for address in members}
    outcomes = _stage2_outcomes(
        root,
        tracker,
        {unit_batch[unit["id"]] for unit in member_units.values() if unit and unit["id"] in unit_batch},
    )

    objects: dict[int, dict[str, Any]] = {}
    for symbol in elf.symbols():
        if symbol.type_name == "OBJECT" and symbol.size and symbol.name:
            row = objects.setdefault(symbol.value, {"size": symbol.size, "names": set()})
            row["size"] = max(row["size"], symbol.size)
            row["names"].add(symbol.name)
    object_starts = sorted(objects)

    def object_for(address: int) -> dict[str, Any] | None:
        position = bisect.bisect_right(object_starts, address) - 1
        if position < 0:
            return None
        start = object_starts[position]
        if address >= start + objects[start]["size"]:
            return None
        return {
            "address": _hex(start),
            "size": objects[start]["size"],
            "names": sorted(objects[start]["names"]),
            "offset": address - start,
        }

    member_ranges = sorted((address, address + by_start[address]["size"]) for address in members)
    range_starts = [start for start, _end in member_ranges]
    references: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for reference in code_data_references(root):
        source = int(reference["site"], 16)
        position = bisect.bisect_right(range_starts, source) - 1
        if position < 0 or source >= member_ranges[position][1]:
            continue
        target = reference["target"]
        if target is not None and int(target, 16) in by_start:
            continue
        references[member_ranges[position][0]].append(
            {**reference, "object": object_for(int(target, 16)) if target is not None else None}
        )

    rows = []
    for address in members:
        function = by_start[address]
        mangled = next((name for name in function["names"] if demangle(name)), None)
        parsed = demangle(mangled) if mangled else None
        gprs, fprs = _entry_argument_reads(elf, address, function["size"], pair_partial_loads=True)
        unit = member_units[address]
        thunk = _thunk_target(elf, address, function["size"])
        rows.append(
            {
                "address": _hex(address),
                "size": function["size"],
                "elf_names": function["names"],
                "demangled": (
                    {
                        "qualifier": "::".join(readable_component(part) for part in parsed["qualifier"]),
                        "parsed": parsed,
                    }
                    if parsed
                    else None
                ),
                "compile_unit": {"id": unit["id"], "path": unit["name"]} if unit else None,
                "entry_argument_reads": {
                    "gpr": [ARGUMENT_GPR_NAMES[reg] for reg in sorted(gprs)],
                    "fpr": [f"f{reg}" for reg in sorted(fprs)],
                },
                "thunk_target": _hex(thunk) if thunk is not None else None,
                "callees": [
                    {"address": _hex(target), "group": group_of[_hex(target)], "sites": [_hex(site) for site in graph["call_sites"][(address, target)]]}
                    for target in graph["edges"].get(address, ())
                ],
                "caller_count": len(graph["callers"].get(address, ())),
                "callers": [_hex(value) for value in graph["callers"].get(address, ())[:16]],
                "data_references": references.get(address, []),
                **(outcomes.get(address) or {"batch": None, "dwarf": None, "stage2": None}),
            }
        )
    repair = {"groups": dict(batch["groups"])} if item.get("kind") == REPAIR_PLAN_KIND else {}
    return {
        "kind": RECON_EVIDENCE_KIND,
        "schema_version": RECON_SCHEMA,
        "mutation_performed": False,
        "work_item_id": item_id,
        "group_sha256": plan_digest(item),
        "height": batch.get("height"),
        **repair,
        "anomalies": [
            row
            for row in graph["anomalies"]
            if any(start <= int(row["site"], 16) < end for start, end in member_ranges)
        ],
        "functions": rows,
    }


def tracker_stage(tracker: dict[str, Any]) -> dict[str, Any]:
    return next(row for row in tracker["stages"] if row["name"] == "ghidra-reconstruction")


# -- plans and programs ----------------------------------------------------


# C spellings of fundamental types and the Ghidra builtin each must be written
# as (the names the DWARF import gives them).  The batch executor accepts only
# builtin names, so a C spelling would resolve to nothing and be skipped.
C_SPELLINGS = {name: ghidra for name, ghidra in BUILTINS.items() if name != ghidra}
C_SPELLINGS["ulong"] = "ulonglong or uint (EE long is 64-bit; say which width the code uses)"
_REGISTER_NUMBERS = {name: number for number, name in ARGUMENT_GPR_NAMES.items()}


def _type_problem(type_name: Any) -> str | None:
    if not isinstance(type_name, str) or not type_name.strip():
        return "type must be a non-empty string"
    if UNSPELLABLE.search(type_name):
        return f"type {type_name!r} contains ',' or '&', which the bridge cannot spell"
    base = _base_type(type_name)
    if base in C_SPELLINGS:
        return f"type {type_name!r} spells {base!r} in C; write the Ghidra builtin {C_SPELLINGS[base]}"
    return None


def _dead_entry_reads(
    rows: Any, address: int, size: int | None, gprs: set[int], fprs: set[int]
) -> tuple[set[int], set[int], list[str]]:
    """Entry reads a plan proves dead, as (GPRs, FPRs, problems).

    Each row names the register, the instruction that reads it inside the
    function, and evidence that no bit of the incoming value survives.  A row
    for a register the entry block does not read is stale and refused.
    """

    dead_g: set[int] = set()
    dead_f: set[int] = set()
    problems: list[str] = []
    for row in rows or []:
        register = str((row or {}).get("register", ""))
        site = str((row or {}).get("site", ""))
        if not (row or {}).get("evidence"):
            problems.append(f"dead entry read {register!r} needs evidence")
        try:
            site_value = int(site, 16)
        except ValueError:
            site_value = None
        if site_value is None or not (address <= site_value < address + (size or 0)):
            problems.append(f"dead entry read {register!r} needs a site inside the function")
        if register in _REGISTER_NUMBERS and _REGISTER_NUMBERS[register] in gprs:
            dead_g.add(_REGISTER_NUMBERS[register])
        elif re.fullmatch(r"f(1[2-9])", register) and int(register[1:]) in fprs:
            dead_f.add(int(register[1:]))
        else:
            problems.append(f"dead entry read {register!r} is not an argument register the entry block reads")
    return dead_g, dead_f, problems


_JR = 0x08
_BRANCH_OPS = frozenset({0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17})
_REGIMM_BRANCHES = frozenset({0x00, 0x01, 0x02, 0x03, 0x10, 0x11, 0x12, 0x13})


def noreturn_problem(elf: Elf32File, sizes: dict[int, int], address: int, _seen: set[int] | None = None) -> str | None:
    """Why the ELF does not prove that ``address`` never returns, or None.

    Proven when the body has no ``jr`` (``jr ra`` returns; any other register
    is an unproven target), every branch stays in the body, every ``j`` either
    stays in the body or tail-calls a function proven the same way, and the
    body cannot run past its end: the transfer before the last delay slot is
    a ``j``, an unconditional ``b``, or a ``jal`` to a proven no-return
    function.  Tail jumps that cycle with no other exit never return.
    """

    seen = set() if _seen is None else _seen
    if address in seen:
        return None
    seen.add(address)
    size = sizes.get(address)
    if not size or size < 8:
        return f"0x{address:x} is not a sized function of two or more instructions"
    word = _code_word(elf)
    end = address + size

    def target_of(pc: int, insn: int) -> int:
        return ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)

    for pc in range(address, end, 4):
        insn = word(pc)
        op = insn >> 26
        if op == 0x00 and insn & 0x3F == _JR:
            register = (insn >> 21) & 31
            return (
                f"jr ra at 0x{pc:x} returns"
                if register == 31
                else f"jr ${register} at 0x{pc:x} jumps to an unproven target"
            )
        is_branch = (
            op in _BRANCH_OPS
            or (op == 0x01 and (insn >> 16) & 31 in _REGIMM_BRANCHES)
            or (op == 0x11 and (insn >> 21) & 31 == 0x08)
        )
        if is_branch:
            target = pc + 4 + ((((insn & 0xFFFF) ^ 0x8000) - 0x8000) << 2)
            if not address <= target < end:
                return f"branch at 0x{pc:x} leaves the body for 0x{target:x}"
        if op == 0x02:
            target = target_of(pc, insn)
            if address <= target < end:
                continue
            if target not in sizes:
                return f"j at 0x{pc:x} leaves for 0x{target:x}, which is not a function start"
            if why := noreturn_problem(elf, sizes, target, seen):
                return f"j at 0x{pc:x} tail-calls 0x{target:x}, which is not proven no-return ({why})"
    last = word(end - 8)
    op = last >> 26
    if op == 0x02 or (op in (0x04, 0x14) and (last >> 16) & 0x3FF == 0):
        return None
    if op == 0x03:
        target = target_of(end - 8, last)
        if target not in sizes:
            return f"the body ends with jal 0x{target:x}, which is not a function start, so it may run past its end"
        if why := noreturn_problem(elf, sizes, target, seen):
            return f"the body ends with a call to 0x{target:x}, which is not proven no-return ({why})"
        return None
    return f"the body may run past its end (0x{end:x}): no jump or no-return call before the last delay slot"


# Keys a partial prototype may carry; a complete prototype carries none.
PARTIAL_KEYS = ("contradiction", "live_signature", "noreturn", "noreturn_evidence", "partial", "varargs", "varargs_evidence")


def _contradicted(live: dict[str, Any], parameters: list[dict[str, Any]], varargs: bool) -> list[str]:
    """How a parsed live signature contradicts the planned parameters.

    A live ``undefined*`` parameter type claims nothing; Ghidra's default
    signature (``undefined f(void)``, with or without a convention) claims
    nothing at all.
    """

    if claims_nothing(live):
        return []
    found = []
    planned = [_shown_type(str(param.get("type"))) for param in parameters]
    if len(live["parameters"]) != len(planned):
        found.append(f"count: the live signature has {len(live['parameters'])} parameters, the proof {len(planned)}")
    if live["varargs"] != varargs:
        found.append(f"varargs: the live signature {'has' if live['varargs'] else 'lacks'} '...'")
    for position, ((live_type, live_name), want) in enumerate(zip(live["parameters"], planned), 1):
        if _base_type(live_type) not in UNDEFINED_TYPES and live_type != want:
            found.append(f"type: parameter {position} is {live_type} {live_name} live, {want} by the proof")
    return found


def _varargs_problems(prototype: dict[str, Any], parameters: list[Any]) -> list[str]:
    """A ``varargs: true`` prototype (partial or complete) needs its evidence and a fixed parameter."""

    if prototype.get("varargs") is not True:
        return []
    problems = []
    if not parameters:
        problems.append("varargs needs a fixed parameter: the bridge reads '...' only after a comma")
    if not prototype.get("varargs_evidence"):
        problems.append("varargs needs varargs_evidence")
    return problems


def _partial_problems(
    prototype: dict[str, Any], unresolved: list[Any], elf: Elf32File, sizes: dict[int, int], address: int
) -> list[str]:
    """Shape and proof checks of a partial prototype (decision of 2026-10-22).

    The row sets its proven parameters and leaves the return ``undefined``;
    it is allowed where the live signature contradicts those parameters, or
    where the live signature is Ghidra's default and claims nothing
    (``undefined f(void)``, with or without a convention; decision of
    2026-10-22 "Yes, extend it"): then every parameter needs a proven type.
    """

    problems = []
    if prototype.get("return_type") != "undefined":
        problems.append("partial prototype: the return stays 'undefined' (Ghidra's unknown, left for the decompiler)")
    if prototype.get("calling_convention") != CALLING_CONVENTION:
        problems.append(f"partial prototype needs calling_convention {CALLING_CONVENTION!r}")
    varargs = prototype.get("varargs")
    if not isinstance(varargs, bool):
        problems.append("partial prototype needs varargs true or false")
    if not unresolved:
        problems.append("partial prototype needs the reasons its return stays unresolved (unresolved)")
    live = parse_signature(prototype.get("live_signature"))
    default = live is not None and claims_nothing(live)
    if not prototype.get("contradiction") and not default:
        problems.append("partial prototype needs the contradiction with the live signature it replaces")
    parameters = prototype.get("parameters") if isinstance(prototype.get("parameters"), list) else []
    for param in parameters:
        if not param.get("evidence"):
            problems.append(f"partial prototype parameter {param.get('name')!r} needs evidence")
        if isinstance(param.get("type"), str) and _base_type(param["type"]) == "undefined":
            problems.append(f"parameter {param.get('name')}: 'undefined' is Ghidra's 1-byte default; an unproven type is undefined1/2/4/8")
        elif default and isinstance(param.get("type"), str) and _base_type(param["type"]) in UNDEFINED_TYPES:
            problems.append(
                f"parameter {param.get('name')}: replacing Ghidra's default signature needs every parameter typed; "
                "a register whose type nothing proves leaves the row unresolved"
            )
    problems.extend(_varargs_problems(prototype, parameters))
    if "noreturn" in prototype and not isinstance(prototype["noreturn"], bool):
        problems.append("noreturn must be true or false")
    if prototype.get("noreturn") is True:
        if not prototype.get("noreturn_evidence"):
            problems.append("noreturn needs noreturn_evidence")
        if why := noreturn_problem(elf, sizes, address):
            problems.append(f"noreturn is not proven by the ELF: {why}")
    if live is None:
        problems.append("partial prototype needs live_signature: the Signature line get_function_by_address prints")
    elif all(isinstance(param.get("type"), str) for param in parameters) and isinstance(varargs, bool):
        if not default and not _contradicted(live, parameters, varargs):
            problems.append(
                "the live signature does not contradict the proven parameters (count, order or type): "
                "a partial prototype is not allowed"
            )
    return problems


def _planned_types(root: Path, tracker: dict[str, Any], plan: dict[str, Any], address: str) -> tuple | None:
    """(return, parameter types) planned for ``address`` in this plan or an accepted one."""

    candidates = [plan]
    accepted = [
        item
        for item in tracker["work_items"]
        if item.get("kind") in PLAN_ITEM_KINDS and item.get("status") == "accepted" and address in item["batch"]["functions"]
    ]
    # The newest accepted repair's row supersedes older repairs and the group's row.
    repairs = sorted((item for item in accepted if item["kind"] == REPAIR_PLAN_KIND), key=lambda row: row["id"], reverse=True)
    for item in repairs + [item for item in accepted if item["kind"] != REPAIR_PLAN_KIND]:
        path = plan_path_for(root, item["id"])
        if path.is_file():
            candidates.append(load_json(path))
    for candidate in candidates:
        for row in candidate.get("functions", []):
            if row.get("address") == address and row.get("prototype"):
                prototype = row["prototype"]
                return (prototype.get("return_type"), tuple(p.get("type") for p in prototype.get("parameters") or []))
    return None


def plan_path_for(root: Path, item_id: str) -> Path:
    """The plan file of a group or repair plan item (``build/recon-plans/<slug>.json``)."""

    slug = item_id.removesuffix("-apply").replace("socom:", "socom-").replace(":", "-")
    return root / "build" / "recon-plans" / f"{slug}.json"


def _restates_live(prototype: dict[str, Any], live: dict[str, Any]) -> bool:
    """Whether the planned prototype is the live signature already (names included)."""

    planned = {
        "calling_convention": CALLING_CONVENTION,
        "parameters": [{"name": p.get("name"), "type": p.get("type")} for p in prototype.get("parameters") or []],
        "return_type": prototype.get("return_type") or "",
        "varargs": prototype.get("varargs") is True,
    }
    return parse_signature(expected_signature(planned, live["name"])) == {**live, "noreturn": False}


def _repair_row_problems(entry: dict[str, Any], batch: dict[str, Any], address: str) -> list[str]:
    """What a recon repair row adds to a group row: the group it corrects and why."""

    problems = []
    group = batch.get("groups", {}).get(address)
    if entry.get("group") != group:
        problems.append(f"repair row must cite its group {group!r} (group), not {entry.get('group')!r}")
    reasons = entry.get("repair")
    if not isinstance(reasons, list) or not reasons or not all(isinstance(r, str) and r.strip() for r in reasons):
        problems.append("repair row needs `repair`: why the live state its group left is wrong")
    prototype = entry.get("prototype")
    if not isinstance(prototype, dict):
        return problems + ["a repair row sets a prototype; a row left unresolved repairs nothing"]
    live = parse_signature(prototype.get("live_signature"))
    if live is None:
        problems.append("repair row needs prototype.live_signature: the Signature line get_function_by_address prints")
    elif isinstance(prototype.get("parameters"), list) and _restates_live(prototype, live) and not prototype.get("dead_reads"):
        problems.append("the prototype is the live signature already: a repair must change it (or declare dead_reads)")
    return problems


def _dead_read_rows(root: Path, address: int, rows: Any, cache: dict[str, Any]) -> list[str]:
    """Problems of a prototype's any-path ``dead_reads`` rows (recon_dead)."""

    from .recon_dead import dead_read_problems
    from .recon_facts import argument_reads, context

    if "ctx" not in cache:
        cache["ctx"] = context(root)
    ctx = cache["ctx"]
    return dead_read_problems(ctx, address, rows, argument_reads(ctx, address))[1]


def validate_recon_plan(root: Path, tracker: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    """Structural and evidence checks a reviewer can rerun.  Returns problems."""

    problems: list[str] = []
    if plan.get("kind") != RECON_PLAN_KIND or plan.get("schema_version") != RECON_SCHEMA:
        return [f"plan must be a schema {RECON_SCHEMA} {RECON_PLAN_KIND}"]
    if (plan.get("target") or {}).get("source_sha256") != REFERENCE_SHA256:
        problems.append("plan targets a different program")
    item = next((row for row in tracker["work_items"] if row["id"] == plan.get("work_item_id")), None)
    if item is None or item.get("kind") not in PLAN_ITEM_KINDS:
        return problems + [f"{plan.get('work_item_id')} is not a reconstruction plan item"]
    batch = item["batch"]
    repair = item.get("kind") == REPAIR_PLAN_KIND
    if plan.get("group_sha256") != plan_digest(item):
        problems.append(
            "plan group_sha256 differs from the repair's function list" if repair
            else "plan group_sha256 differs from the decomposed group"
        )
    if repair and plan.get("globals"):
        problems.append("a recon repair corrects function prototypes only: globals must be empty")
    facts: dict[str, Any] = {}
    elf = Elf32File(root / "support" / "socom.elf")
    sizes = {row["start"]: row["size"] for row in _functions(elf)}

    expected = set(batch["functions"])
    seen: set[str] = set()
    for entry in plan.get("functions", []):
        address = str(entry.get("address", ""))
        where = f"function {address}"
        if address in seen:
            problems.append(f"{where} appears twice")
        seen.add(address)
        if address not in expected:
            problems.append(f"{where} is not in the {'repair' if repair else 'group'}")
            continue
        if repair:
            problems.extend(f"{where} {problem}" for problem in _repair_row_problems(entry, batch, address))
        if not isinstance(entry.get("current_name"), str) or not entry["current_name"]:
            problems.append(f"{where} needs the live current_name")
        rename = entry.get("rename")
        if rename is not None:
            if not isinstance(rename, dict) or not isinstance(rename.get("name"), str) or not rename["name"].strip():
                problems.append(f"{where} rename needs a name")
            elif not rename.get("evidence"):
                problems.append(f"{where} rename needs evidence")
        prototype = entry.get("prototype")
        unresolved = entry.get("unresolved") or []
        if prototype is None:
            if not unresolved:
                problems.append(f"{where} needs a prototype or the reasons it is unresolved")
            continue
        partial = prototype.get("partial", False) is True
        if partial:
            # The return stays unresolved: `unresolved` says why (decision of 2026-10-22).
            problems.extend(
                f"{where} {problem}"
                for problem in _partial_problems(prototype, unresolved, elf, sizes, int(address, 16))
            )
        else:
            if prototype.get("partial", False) is not False:
                problems.append(f"{where} partial must be true or absent")
            if unresolved:
                problems.append(f"{where} has both a prototype and unresolved reasons")
            if not prototype.get("evidence"):
                problems.append(f"{where} prototype needs evidence")
            if reason := _type_problem(prototype.get("return_type")):
                problems.append(f"{where} return: {reason}")
            # A repair row names the live signature it replaces, partial or not;
            # a complete prototype may be varargs when its return is decided
            # (decision of 2026-10-22: fprintf, whose 271 callers never read v0).
            allowed = {"partial", "varargs", "varargs_evidence"} | ({"live_signature"} if repair else set())
            extra = [key for key in PARTIAL_KEYS if key in prototype and key not in allowed]
            if "varargs" in prototype and not isinstance(prototype["varargs"], bool):
                problems.append(f"{where} varargs must be true or false")
            if isinstance(prototype.get("parameters"), list):
                problems.extend(f"{where} {problem}" for problem in _varargs_problems(prototype, prototype["parameters"]))
            if extra:
                problems.append(f"{where} {', '.join(extra)}: only a partial prototype carries these")
        parameters = prototype.get("parameters")
        if not isinstance(parameters, list):
            problems.append(f"{where} parameters must be a list")
            continue
        names = [param.get("name") for param in parameters]
        for position, param in enumerate(parameters, 1):
            if not isinstance(param.get("name"), str) or not _IDENTIFIER.match(param["name"]):
                problems.append(f"{where} parameter name {param.get('name')!r} is not an identifier")

            if reason := _type_problem(param.get("type")):
                problems.append(f"{where} parameter {param.get('name')}: {reason}")
        for type_name in [prototype.get("return_type")] + [param.get("type") for param in parameters]:
            if not partial and isinstance(type_name, str) and _base_type(type_name) in UNDEFINED_TYPES:
                problems.append(f"{where} {type_name!r} is Ghidra's unknown type: only a partial prototype may use it")
        if len(set(names)) != len(names):
            problems.append(f"{where} parameter names repeat")
        target = _thunk_target(elf, int(address, 16), sizes.get(int(address, 16)))
        if target is not None and partial:
            problems.append(f"{where} is a thunk of 0x{target:x}: a thunk shares its target's signature, so plan the target")
        elif target is not None:
            # Ghidra makes a whole-body `j target` a thunk, and a thunk shares its
            # target's signature: a prototype set on it rewrites the target
            # (C2DString::On rewrote C2D::On in group 114).  Allow only the
            # target's own planned types.
            wanted = _planned_types(root, tracker, plan, f"0x{target:x}")
            mine = (prototype.get("return_type"), tuple(p.get("type") for p in parameters))
            if wanted is None:
                problems.append(
                    f"{where} is a thunk of 0x{target:x} with no planned prototype; a prototype here would rewrite "
                    "the target: mark it unresolved"
                )
            elif mine != wanted:
                problems.append(f"{where} is a thunk of 0x{target:x}: its prototype must equal the target's {wanted}")
        if all(isinstance(param.get("type"), str) for param in parameters):
            gprs, fprs = _entry_argument_reads(
                elf, int(address, 16), sizes.get(int(address, 16)), pair_partial_loads=True
            )
            dead_g, dead_f, dead_problems = _dead_entry_reads(
                prototype.get("dead_entry_reads"), int(address, 16), sizes.get(int(address, 16)), gprs, fprs
            )
            problems.extend(f"{where} {problem}" for problem in dead_problems)
            gprs, fprs = gprs - dead_g, fprs - dead_f
            if prototype.get("dead_reads") is not None:
                problems.extend(
                    f"{where} {problem}"
                    for problem in _dead_read_rows(root, int(address, 16), prototype["dead_reads"], facts)
                )
            declared_g, declared_f = _declared_argument_registers({"parameters": parameters})
            if prototype.get("varargs") is True:
                # Registers after the fixed parameters carry the variadic arguments.
                gprs = {reg for reg in gprs if reg in declared_g or reg < max(declared_g, default=3)}
                fprs = {reg for reg in fprs if reg in declared_f or reg < max(declared_f, default=11)}
            if not gprs <= declared_g or not fprs <= declared_f:
                missing = sorted(ARGUMENT_GPR_NAMES[reg] for reg in gprs - declared_g) + sorted(
                    f"f{reg}" for reg in fprs - declared_f
                )
                problems.append(f"{where} reads argument registers {missing} that the prototype does not declare")
    for address in sorted(expected - seen, key=lambda value: int(value, 16)):
        problems.append(f"function {address} is missing from the plan")

    for entry in plan.get("globals", []):
        address = str(entry.get("address", ""))
        where = f"global {address}"
        if not entry.get("evidence"):
            problems.append(f"{where} needs evidence")
        if not isinstance(entry.get("current_name"), str) or not entry["current_name"]:
            problems.append(f"{where} needs the live current_name")
        if entry.get("type") is not None:
            if reason := _type_problem(entry["type"]) or _data_alias_problem(entry["type"]):
                problems.append(f"{where}: {reason}")
        rename = entry.get("rename")
        if rename is not None and (not isinstance(rename, str) or not rename.strip()):
            problems.append(f"{where} rename must be a name")
        if entry.get("type") is None and rename is None:
            problems.append(f"{where} changes nothing")
    if plan.get("globals"):
        evidence = group_evidence(root, tracker, plan["work_item_id"])
        referenced = {
            reference["object"]["address"]
            for row in evidence["functions"]
            for reference in row["data_references"]
            if reference["object"]
        } | {
            reference["target"] for row in evidence["functions"] for reference in row["data_references"]
        }
        for entry in plan["globals"]:
            if entry.get("address") not in referenced:
                problems.append(f"global {entry.get('address')} is not referenced by the group's functions")
    return problems


def build_recon_program(root: Path, tracker: dict[str, Any], plan_path: Path) -> dict[str, Any]:
    """Translate a valid reconstruction plan into a batch-apply program."""

    plan = load_json(plan_path)
    problems = validate_recon_plan(root, tracker, plan)
    if problems:
        raise SocomError("the reconstruction plan is invalid:\n- " + "\n- ".join(problems))
    repair = str(plan["work_item_id"]).startswith(REPAIR_PREFIX)
    functions = []
    for entry in sorted(plan["functions"], key=lambda row: int(row["address"], 16)):
        rename = entry.get("rename")
        prototype = entry.get("prototype")
        out = {
            "address": entry["address"],
            "current_name": entry["current_name"],
            "readable_name": rename["name"] if rename else entry["current_name"],
            "rename": bool(rename) and rename["name"] != entry["current_name"],
            "prototype": (
                {
                    "calling_convention": CALLING_CONVENTION,
                    "parameters": [{"name": param["name"], "type": param["type"]} for param in prototype["parameters"]],
                    "return_type": prototype["return_type"],
                    "sources": ["recon-plan"],
                }
                if prototype
                else None
            ),
            "prototype_skip": "; ".join(entry.get("unresolved") or []) or None,
            "notes": list(entry.get("notes") or [])
            + [
                f"entry read of {row['register']} at {row['site']} is dead: {'; '.join(row['evidence']) if isinstance(row['evidence'], list) else row['evidence']}"
                for row in ((prototype or {}).get("dead_entry_reads") or [])
            ],
        }
        if prototype and not prototype.get("partial") and prototype.get("varargs") is True:
            # Absent otherwise, so programs without varargs rows keep their bytes.
            out["prototype"]["varargs"] = True
            out["notes"].append("varargs: " + "; ".join(_texts(prototype["varargs_evidence"])))
        if prototype and prototype.get("dead_reads"):
            from .recon_dead import dead_read_note

            out["notes"].extend(dead_read_note(row) for row in prototype["dead_reads"])
        if repair:
            # The apply refuses unless the function still shows the signature
            # the row replaces (a partial row records it below as well).
            out["prototype"]["live_signature"] = prototype["live_signature"]
            out["notes"].append(f"repair of {entry['group']}: " + "; ".join(_texts(entry["repair"])))
        if prototype and prototype.get("partial"):
            # The prototype is applied; the return stays undefined, for the
            # reasons the row's `unresolved` records.
            out["prototype"].update(
                {"partial": True, "varargs": prototype["varargs"], "live_signature": prototype["live_signature"]}
            )
            out["prototype_skip"] = None
            out["return_unresolved"] = "; ".join(entry["unresolved"])
            out["notes"].append(
                f"partial prototype replacing the live signature {prototype['live_signature']!r}: "
                + "; ".join(_texts(prototype.get("contradiction") or "it is Ghidra's default and claims nothing"))
            )
            if prototype.get("noreturn"):
                # set_function_no_return exists, but a no-return change wakes
                # Ghidra's Call-Fixup Installer (a function-modifier analyzer),
                # which clears and repairs the flow after every call site.
                out["prototype"]["noreturn_proven"] = True
                out["notes"].append(
                    "proven no-return, not applied (it would clear flow at call sites): "
                    + "; ".join(_texts(prototype["noreturn_evidence"]))
                )
        functions.append(out)
    globals_ = []
    for entry in sorted(plan.get("globals", []), key=lambda row: int(row["address"], 16)):
        rename = entry.get("rename")
        globals_.append(
            {
                "address": entry["address"],
                "current_name": entry["current_name"],
                "readable_name": rename or entry["current_name"],
                "rename": bool(rename) and rename != entry["current_name"],
                "type": entry.get("type"),
                "type_skip": None,
                "size": entry.get("size"),
                "replaces_accepted": bool(entry.get("replaces_accepted")),
            }
        )
    relative_plan = plan_path.resolve()
    try:
        relative_plan = relative_plan.relative_to(root.resolve())
    except ValueError:
        pass
    scope_functions = sorted({row["address"] for row in functions}, key=lambda value: (value.casefold(), value))
    scope_globals = sorted({row["address"] for row in globals_}, key=lambda value: (value.casefold(), value))
    partial_count = sum(1 for row in functions if (row["prototype"] or {}).get("partial"))
    program = {
        "kind": BATCH_PROGRAM_KIND,
        "schema_version": BATCH_PROGRAM_SCHEMA,
        "mutation_performed": False,
        "plan": {
            "path": Path(relative_plan).as_posix(),
            "sha256": sha256_file(plan_path),
            "work_item_id": plan["work_item_id"],
        },
        "functions": functions,
        "globals": globals_,
        "absent_variables": [],
        "receipt_scope": {"schema_version": 1, "functions": scope_functions, "types": [], "globals": scope_globals},
        "summary": {
            "function_count": len(functions),
            "renamed_function_count": sum(1 for row in functions if row["rename"]),
            "prototype_count": sum(1 for row in functions if row["prototype"]),
            "unresolved_count": sum(1 for row in functions if row["prototype_skip"]),
            "global_count": len(globals_),
            "typed_global_count": sum(1 for row in globals_ if row["type"]),
            "renamed_global_count": sum(1 for row in globals_ if row["rename"]),
        },
    }
    if partial_count:
        # Absent otherwise, so programs without partial rows keep their bytes.
        program["summary"]["partial_prototype_count"] = partial_count
    return program


def _texts(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else [str(value)]
