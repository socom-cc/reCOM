"""Read-only scan for live signatures that contradict the ELF facts (stage 3).

Some live signatures came from Ghidra's built-in library archives (glibc
order and types) and were never proven; a group whose row stays unresolved
leaves them live.  ``live_contradictions`` lists every group function whose
live signature makes a claim the facts disprove:

* ``registers``: an argument register the code reads before writing it, on
  some path, that the live signature does not declare (``recon facts``
  ``argument_reads``).  Dropped: dead entry reads and ``dead_reads`` sites an
  accepted plan or repair declares, reads ``recon_dead`` proves masked
  before use, and registers after a varargs signature's fixed parameters;
* ``count`` / ``type``: the Metrowerks mangled signature has another
  parameter count or varargs, or a parameter of another shape: pointer depth,
  float versus integer register, builtin width, or a scalar where the mangled
  type is a class (class names are not compared);
* ``drift``: an applied group's plan (or the newest applied recon repair of
  the function) set a prototype that the live signature no longer shows;
* ``recorded``: a reviewed plan row records that the live signature is wrong
  (a contradiction, a disagreement, a wrong width or a different type; a
  remark that a signature is unproven or where it came from is not one).

Ghidra's default signature (``undefined FUN(void)``, no convention) and the
convention-only placeholder ``undefined __stdcall FUN(void)`` (the signature
repairs restore) claim nothing, and ``undefined*`` parameter types claim no
type.  A thunk (a whole-body ``j``/``b``) shows its target's signature, so it
is not checked against its own facts; thunks that would conflict are listed
separately.  Live types whose only definition lies outside ``/project``
(Ghidra's archives) are listed as ``library types``; they are not a
contradiction by themselves.  Nothing is written to Ghidra or the tracker.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .batch_apply import (
    BUILTIN_SIZES,
    BUILTINS,
    CALLING_CONVENTION,
    UNDEFINED_TYPES,
    _base_type,
    _declared_argument_registers,
    _SIGNATURE_LINE,
    _thunk_target,
    _Types,
    claims_nothing,
    expected_signature,
    parse_signature,
)
from .mwdemangle import demangle
from .util import SocomError, load_json

APPLIED_STATUSES = frozenset({"accepted", "awaiting_acceptance"})
_GPR = {4: "a0", 5: "a1", 6: "a2", 7: "a3", 8: "t0", 9: "t1", 10: "t2", 11: "t3"}
_REGISTER = {name: number for number, name in _GPR.items()} | {f"f{n}": 100 + n for n in range(12, 20)}
# Wording a reviewed plan uses when it records a wrong live signature: a
# contradiction, a disagreement, a wrong width or a different type.  Remarks
# that a signature is unproven ("no evidence") or where it came from ("library
# type archive") record no contradiction.
_RECORDED = re.compile(
    r"live (?:signature|prototype)[^;]*?(?:contradict|disagree|wrong width|\(\d+ bytes\), not )"
    r"|(?:contradict|disagree|different \d+-byte type|wrong width)[^;]*?live (?:signature|prototype)"
    r"|in the live (?:signature|prototype) is a different",
    re.IGNORECASE,
)
_BUILTIN_NAMES = frozenset(BUILTINS.values()) | frozenset(BUILTIN_SIZES)


def _slug(item_id: str) -> str:
    return item_id.replace("socom:", "socom-").replace(":", "-")



def _live_shape(type_name: str) -> tuple | None:
    """(pointer depth, kind, builtin, size) of a printed live type, or None if unknown."""

    base = _base_type(type_name)
    if base in UNDEFINED_TYPES or "[" in type_name:
        return None
    depth = type_name.count("*")
    if base in _BUILTIN_NAMES:
        return (depth, "builtin", base, BUILTIN_SIZES.get(base))
    return (depth, "other", None, None)


def _shape_conflict(live: tuple | None, mangled: tuple | None) -> str | None:
    if live is None or mangled is None:
        return None
    if live[0] != mangled[0]:
        return f"pointer depth {live[0]} vs {mangled[0]}"
    if live[0]:
        return None
    if mangled[1] == "builtin" and live[1] == "builtin":
        if (live[2] == "float") != (mangled[2] == "float"):
            return f"{live[2]} vs {mangled[2]} (float and integer registers differ)"
        if live[3] and mangled[3] and live[3] != mangled[3]:
            return f"{live[2]} ({live[3]} bytes) vs {mangled[2]} ({mangled[3]} bytes)"
        return None
    if mangled[1] == "class" and live[1] == "builtin":
        return f"scalar {live[2]} where the mangled type is a class passed by value"
    return None


def _mangled_conflicts(names: list[str], live: dict[str, Any]) -> list[str]:
    mangled = next((name for name in names if demangle(name)), None)
    parsed = demangle(mangled) if mangled else None
    if not parsed or parsed.get("params") is None:
        return []
    params = list(parsed["params"])
    if params == [{"modifiers": [], "kind": "builtin", "name": "void"}]:
        params = []
    varargs = bool(params) and params[-1].get("kind") == "builtin" and params[-1].get("name") == "..."
    if varargs:
        params = params[:-1]
    shown = list(live["parameters"])
    if parsed.get("qualifier") and shown and shown[0][1] == "this":
        shown = shown[1:]
    # Destructors (and their @N@__dt adjustor thunks) take the hidden flags.
    if str(parsed.get("name")).endswith("__dt") and shown and shown[-1][1] == "__dtor_flags":
        shown = shown[:-1]
    found = []
    if len(shown) != len(params):
        found.append(f"count: {mangled} has {len(params)} parameters, the live signature {len(shown)}")
    if varargs != live["varargs"]:
        found.append(f"count: {mangled} {'ends' if varargs else 'does not end'} in '...', the live signature "
                     f"{'does' if live['varargs'] else 'does not'}")
    for position, ((live_type, live_name), value) in enumerate(zip(shown, params), 1):
        conflict = _shape_conflict(_live_shape(live_type), _Types.mangled_shape(value))
        if conflict:
            found.append(f"type: parameter {position} {live_type} {live_name}: {conflict} ({mangled})")
    return found


def _register_conflicts(
    reads: dict[str, list[int]],
    live: dict[str, Any],
    dead: set[str],
    dead_sites: dict[str, set[int]] | None = None,
    masked: Callable[[str, int], bool] | None = None,
    explained: list[str] | None = None,
) -> list[str]:
    """Undeclared argument reads.  ``dead`` registers (entry block) and
    ``dead_sites`` (any path) are declared dead by a plan; ``masked(register,
    site)`` proves a read dead; ``explained`` collects the reads so dropped."""

    declared_g, declared_f = _declared_argument_registers({"parameters": [{"type": t} for t, _ in live["parameters"]]})
    declared = declared_g | {100 + reg for reg in declared_f}
    found = []
    for register, sites in reads.items():
        number = _REGISTER.get(register)
        if number is None or register in dead or number in declared:
            continue
        if live["varargs"] and (
            (number < 100 and number > max(declared_g, default=3))
            or (number >= 100 and number - 100 > max(declared_f, default=11))
        ):
            continue
        declared_dead = (dead_sites or {}).get(register, set())
        remaining = [site for site in sites if site not in declared_dead]
        proven = [site for site in remaining if masked is not None and masked(register, site)]
        remaining = [site for site in remaining if site not in proven]
        if explained is not None:
            explained.extend(f"{register}@0x{site:x} declared dead" for site in sites if site in declared_dead)
            explained.extend(f"{register}@0x{site:x} masked" for site in proven)
        if not remaining:
            continue
        found.append(
            f"registers: {register} is read before any write (0x{remaining[0]:x}) but the live signature declares "
            f"{len(live['parameters'])} parameter(s)"
        )
    return found


def _planned_signature(prototype: dict[str, Any]) -> dict[str, Any]:
    return parse_signature(
        expected_signature(
            {
                "calling_convention": CALLING_CONVENTION,
                "parameters": prototype.get("parameters") or [],
                "return_type": prototype.get("return_type") or "",
                "varargs": prototype.get("varargs") is True,
            },
            "planned",
        )
    ) or {}


def live_contradictions(
    root: Path,
    tracker: dict[str, Any],
    *,
    groups: str = "all",
    signatures: dict[int, str] | None = None,
    type_paths: dict[str, list[str]] | None = None,
    bridge_url: str | None = None,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Every group function whose live signature contradicts the facts.

    ``signatures`` (address -> Signature line) and ``type_paths`` (type name
    -> live paths) come from a fingerprint; otherwise they are read live.
    """

    from .recon_facts import argument_reads, context

    if groups not in ("all", "applied"):
        raise SocomError("--groups is applied or all")
    items = {row["id"]: row for row in tracker["work_items"]}
    plans = [row for row in tracker["work_items"] if row.get("kind") == "recon-plan-group"]
    if not plans:
        raise SocomError("the tracker has no reconstruction groups")
    owner: dict[int, dict[str, Any]] = {}
    for plan in plans:
        apply = items.get(f"{plan['id']}-apply") or {}
        info = {
            "group": plan["id"],
            "group_number": plan["batch"].get("group_number"),
            "plan_status": plan.get("status"),
            "apply_status": apply.get("status"),
            "applied": apply.get("status") in APPLIED_STATUSES,
            "plan_path": root / "build" / "recon-plans" / f"{_slug(plan['id'])}.json",
        }
        for value in plan["batch"]["functions"]:
            owner[int(value, 16)] = info
    # Recon repairs of each function, oldest first.
    repairs: dict[int, list[dict[str, Any]]] = {}
    repair_plans = sorted((row for row in tracker["work_items"] if row.get("kind") == "recon-repair-plan"), key=lambda row: row["id"])
    for plan in repair_plans:
        apply = items.get(f"{plan['id']}-apply") or {}
        info = {
            "repair": plan["id"],
            "repair_number": plan["batch"].get("repair_number"),
            "plan_status": plan.get("status"),
            "apply_status": apply.get("status"),
            "applied": apply.get("status") in APPLIED_STATUSES,
            "plan_path": root / "build" / "recon-plans" / f"{_slug(plan['id'])}.json",
        }
        for value in plan["batch"]["functions"]:
            repairs.setdefault(int(value, 16), []).append(info)
    wanted = sorted(address for address, info in owner.items() if groups == "all" or info["applied"])
    rows_by_plan: dict[Path, dict[int, dict[str, Any]]] = {}

    def plan_row(info: dict[str, Any], address: int) -> dict[str, Any] | None:
        path = info["plan_path"]
        if path not in rows_by_plan:
            rows_by_plan[path] = {}
            if path.is_file():
                try:
                    plan = load_json(path)
                except SocomError:
                    plan = {}
                for row in plan.get("functions", []) if isinstance(plan, dict) else []:
                    try:
                        rows_by_plan[path][int(str(row.get("address")), 16)] = row
                    except ValueError:
                        continue
        return rows_by_plan[path].get(address)

    if signatures is None or type_paths is None:
        from .ghidra import GhidraBridge, _type_index

        bridge = GhidraBridge(bridge_url, timeout=300.0)
        if type_paths is None:
            type_paths = {}
            for row in _type_index(bridge):
                type_paths.setdefault(row["name"], []).append(row["path"])
        if signatures is None:
            signatures = {}
            log(f"live signatures of {len(wanted)} functions")
            for address in wanted:
                text = bridge.request("get_function_by_address", address=f"0x{address:x}")
                lines = text.splitlines() if isinstance(text, str) else []
                found = next((m.group(1) for line in lines if (m := _SIGNATURE_LINE.match(line))), None)
                if found is not None:
                    signatures[address] = found
    from .recon_dead import GPR_NUMBERS, masked_read_problem

    ctx = context(root)
    names = {row["start"]: row["names"] for row in ctx.functions}

    def masked(start: int) -> Callable[[str, int], bool]:
        return lambda register, site: register in GPR_NUMBERS and masked_read_problem(ctx, start, GPR_NUMBERS[register], site) is None

    rows = []
    thunks = []
    thunk_count = 0
    claim_count = 0
    explained_count = 0
    library_typed = 0
    for address in wanted:
        info = owner[address]
        signature = signatures.get(address)
        live = parse_signature(signature)
        if live is None or claims_nothing(live):
            continue
        group_row = plan_row(info, address)
        # The newest applied repair whose plan is accepted supersedes the
        # group's row; a repair not applied yet is listed with the row.
        repaired = [r for r in repairs.get(address, []) if r["applied"] and r["plan_status"] == "accepted"]
        latest = repaired[-1] if repaired else None
        row = plan_row(latest, address) if latest else group_row
        effective = latest or info
        prototype = (row or {}).get("prototype") or None
        accepted_rows = ([group_row] if info["plan_status"] == "accepted" else []) + [
            plan_row(r, address) for r in repairs.get(address, []) if r["plan_status"] == "accepted"
        ]
        accepted_prototypes = [(r or {}).get("prototype") or {} for r in accepted_rows]
        dead = {str(entry.get("register")) for p in accepted_prototypes for entry in (p.get("dead_entry_reads") or [])}
        dead_sites: dict[str, set[int]] = {}
        for p in accepted_prototypes:
            for entry in p.get("dead_reads") or []:
                try:
                    dead_sites.setdefault(str(entry.get("register")), set()).add(int(str(entry.get("site")), 16))
                except ValueError:
                    continue
        explained: list[str] = []
        kinds = _register_conflicts(argument_reads(ctx, address), live, dead, dead_sites, masked(address), explained)
        kinds += _mangled_conflicts(names.get(address, []), live)
        if prototype and effective["applied"] and effective["plan_status"] == "accepted":
            want = _planned_signature(prototype)
            if want and (
                [t for t, _ in want["parameters"]] != [t for t, _ in live["parameters"]]
                or want["return_type"] != live["return_type"]
                or want["varargs"] != live["varargs"]
            ):
                source = f"repair {latest['repair_number']:03d}" if latest else "the applied plan"
                kinds.append(f"drift: {source} sets {want['return_type']} ({', '.join(t for t, _ in want['parameters']) or 'void'})")
        for reason in (row or {}).get("unresolved") or []:
            if isinstance(reason, str) and (match := _RECORDED.search(reason)):
                start = max(0, match.start() - 40)
                kinds.append(f"recorded ({effective['plan_status']} plan): ...{reason[start : match.end() + 60]}...")
                break
        target = _thunk_target(ctx.elf, address, ctx.size.get(address))
        if target is not None:
            # A thunk shows its target's signature: no row of its own can repair it.
            thunk_count += 1
            if kinds:
                thunks.append(
                    {
                        "address": f"0x{address:x}",
                        "name": live["name"],
                        "signature": signature,
                        "target": f"0x{target:x}",
                        "target_name": ctx.label(target),
                        "group_number": info["group_number"],
                        "would_flag": kinds,
                    }
                )
            continue
        claim_count += 1
        explained_count += len(explained)
        library = sorted(
            {
                f"{_base_type(t)} ({', '.join(paths)})"
                for t in [live["return_type"]] + [t for t, _ in live["parameters"]]
                if _base_type(t) not in _BUILTIN_NAMES | UNDEFINED_TYPES
                and (paths := (type_paths or {}).get(_base_type(t)))
                and not any(path.startswith("/project/") for path in paths)
                and not all(path.count("/") == 1 for path in paths)
            }
        )
        library_typed += bool(library)
        if not kinds:
            continue
        state = (
            "missing from its plan" if row is None
            else "partial" if (prototype or {}).get("partial")
            else "prototype" if prototype
            else "open" if row.get("draft") == "open"
            else "unresolved"
        )
        rows.append(
            {
                "address": f"0x{address:x}",
                "name": live["name"],
                "signature": signature,
                "group": info["group"],
                "group_number": info["group_number"],
                "plan_status": info["plan_status"],
                "apply_status": info["apply_status"],
                "applied": info["applied"],
                "row": state if effective["plan_path"].is_file() else "no plan file",
                "repairs": [
                    {key: r[key] for key in ("repair", "repair_number", "plan_status", "apply_status", "applied")}
                    for r in repairs.get(address, [])
                ],
                "contradictions": kinds,
                "explained_reads": explained,
                "library_types": library,
            }
        )
    kinds_count: dict[str, int] = {}
    for row in rows:
        for kind in {text.split(":", 1)[0].split(" (", 1)[0] for text in row["contradictions"]}:
            kinds_count[kind] = kinds_count.get(kind, 0) + 1
    return {
        "kind": "socom-recon-live-contradictions",
        "mutation_performed": False,
        "groups": groups,
        "scanned": len(wanted),
        # Thunks are counted apart: they show their target's signature.
        "with_live_claims": claim_count,
        "contradiction_count": len(rows),
        "applied_count": sum(1 for row in rows if row["applied"]),
        # The live signature is a prototype this project planned, not an unproven one.
        "planned_prototype_count": sum(1 for row in rows if row["row"] in ("prototype", "partial")),
        "kinds": dict(sorted(kinds_count.items())),
        "library_typed_count": library_typed,
        "explained_read_count": explained_count,
        "thunk_count": thunk_count,
        "thunks": thunks,
        "functions": rows,
    }


def contradictions_text(result: dict[str, Any]) -> str:
    lines = [
        f"# recon contradictions --groups {result['groups']}: {result['contradiction_count']} of "
        f"{result['with_live_claims']} live signatures with claims ({result['scanned']} group functions scanned) "
        f"contradict the facts; {result['applied_count']} are in applied groups",
        "# by kind: " + (", ".join(f"{kind} {count}" for kind, count in result["kinds"].items()) or "none")
        + f"; {result['planned_prototype_count']} of the signatures are prototypes a plan set, the rest unproven",
        f"# {result['library_typed_count']} scanned signatures use a type defined only outside /project (Ghidra's archives)",
        f"# {result.get('explained_read_count', 0)} undeclared any-path reads are dead (proven masked, or declared "
        "by an accepted plan's dead_reads) and not listed",
        f"# {result.get('thunk_count', 0)} thunks with live claims show their target's signature and are not checked; "
        f"{len(result.get('thunks', []))} would conflict (listed at the end)",
    ]
    for row in result["functions"]:
        lines.append("")
        lines.append(f"{row['address']} {row['name']} :: {row['signature']}")
        lines.append(
            f"  group {row['group_number']} {row['group']}: plan {row['plan_status']}, apply {row['apply_status']}"
            f" ({'applied' if row['applied'] else 'not applied'}); row {row['row']}"
        )
        for repair in row.get("repairs", []):
            lines.append(
                f"  repair {repair['repair_number']:03d} {repair['repair']}: plan {repair['plan_status']}, apply "
                f"{repair['apply_status']} ({'applied' if repair['applied'] else 'not applied'})"
            )
        lines.extend(f"  {text}" for text in row["contradictions"])
        if row["library_types"]:
            lines.append("  library types: " + "; ".join(row["library_types"]))
    if result.get("thunks"):
        lines.append("")
        lines.append("# thunks: not contradictions, a thunk shows its target's signature (plan the target instead)")
        for row in result["thunks"]:
            lines.append(
                f"{row['address']} {row['name']} -> {row['target_name']} (group {row['group_number']}) :: {row['signature']}"
            )
            lines.extend(f"  would flag {text}" for text in row["would_flag"])
    return "\n".join(lines)


def fingerprint_inputs(fingerprint: dict[str, Any]) -> tuple[dict[int, str], dict[str, list[str]]]:
    """Signature lines and type paths from a stored program fingerprint."""

    signatures: dict[int, str] = {}
    for row in fingerprint.get("functions", []):
        for line in row.get("details") or []:
            if match := _SIGNATURE_LINE.match(line):
                signatures[int(row["address"], 16)] = match.group(1)
    paths: dict[str, list[str]] = {}
    for text in fingerprint.get("types", []):
        path = text.rsplit("|", 1)[0]
        paths.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    return signatures, paths

