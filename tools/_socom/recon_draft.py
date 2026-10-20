"""Draft stage 3 plans: decide the rows a fixed rule settles, leave the rest open.

A planner fills only the open rows; a reviewer re-runs ``recon draft --check``
to confirm every drafted row is exactly what the rules give, and reviews the
open rows by hand.  Each rule is conservative: when its conditions are not all
met the row stays open, never guessed.

Rules (``draft_rule`` on each decided row):

U-type   unresolved: a parameter's mangled class type (or the receiver class
         of a method proven to have one) is absent from the live program,
         names several live types, or contains ',' or '&' (the bridge cannot
         spell it).  Not applied when stage 2 typed the function from DWARF.
U-vararg unresolved: the mangled signature ends in '...'.
P-stage2 restate the prototype stage 2 applied from DWARF, when every argument
         register read on any path is declared and, for a void return, every
         exit leaves v0 and f0 unset.
P-void   a void prototype from the mangled signature, when every parameter
         type resolves to one live type, every argument register read on any
         path is declared, every exit (jr ra) leaves v0 and f0 unset, nothing
         takes the function's address or stores it in a table (so no override
         or callback contract applies), and a method's receiver is proven: a
         const method, or an argument register read beyond the declared
         parameters that the receiver accounts for.  ``__sinit_*`` static initializers
         (no mangled name, no argument reads, no direct call sites, only their
         .p__sinit table word, jr ra exits) are void(void) whatever v0 holds:
         the runtime's table type fixes their contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .batch_apply import (
    ARGUMENT_FPRS,
    ARGUMENT_GPRS,
    BUILTINS,
    UNSPELLABLE,
    _declared_argument_registers,
    readable_component,
)
from .constants import REFERENCE_SHA256
from .mwdemangle import demangle
from .recon import RECON_PLAN_KIND, RECON_SCHEMA, group_evidence
from .recon_facts import GPR, JR_RA, _reads_at, _through_calls, _use_after_call, argument_reads, call_sites, callee_preserves, context, return_sources
from .util import SocomError, canonical_json

DRAFT_RULES_VERSION = 6


class _TypeIndex:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            self.by_name.setdefault(row["name"].casefold(), []).append(row)

    def resolve(self, name: str) -> tuple[str | None, str | None]:
        """(spelling, None) for exactly one live type of that name, else (None, reason)."""

        if UNSPELLABLE.search(name):
            return None, f"type name {name!r} contains ',' or '&', which the bridge cannot spell"
        found = self.by_name.get(name.casefold(), [])
        if not found:
            if any(key.startswith(name.casefold() + "@") for key in self.by_name):
                # Only a disambiguated provisional copy (NAME@hash) exists: a planner decides.
                return None, None
            return None, f"type {name!r} is absent from the live program"
        if len(found) > 1:
            paths = ", ".join(sorted(row["path"] for row in found)[:4])
            return None, f"type name {name!r} is ambiguous: {len(found)} live types ({paths})"
        if found[0]["name"] != name:
            return None, None  # only a differently-cased type: a planner decides
        return name, None

    def spells(self, text: str) -> bool:
        """Every type in a rendered spelling ('CFoo * *', 'uint') names exactly one live type."""

        base = text.replace("*", "").strip()
        if base in BUILTIN_SPELLINGS:
            return True
        return self.resolve(base)[0] is not None


BUILTIN_SPELLINGS = frozenset(BUILTINS.values()) | {"undefined", "byte", "word", "dword"}


def _uses_vu0(ctx: Any, start: int) -> bool:
    """Any COP2 (VU0 macro) instruction, lqc2 or sqc2: VU register contracts need a planner."""

    for pc in range(start, start + ctx.size.get(start, 0), 4):
        op = ctx.code.word(pc) >> 26
        if op in (0x12, 0x36, 0x3E):
            return True
    return False


def _class_name(components: list[str]) -> str:
    return readable_component(components[-1])


def _render(value: dict[str, Any], types: _TypeIndex) -> tuple[str | None, str | None, bool]:
    """(spelling, reason, type_problem): type_problem marks a missing/ambiguous/unspellable class."""

    modifiers = value.get("modifiers") or []
    if value.get("kind") == "builtin":
        name = BUILTINS.get(value.get("name"))
        if name is None:
            return None, f"builtin {value.get('name')!r} has no Ghidra spelling", False
    elif value.get("kind") == "class":
        name, reason = types.resolve(_class_name(value.get("components") or []))
        if name is None:
            return None, reason or "class type needs a planner", reason is not None
    else:
        return None, f"{value.get('kind')} parameter needs a planner", False
    for modifier in modifiers:
        if modifier in ("P", "R"):
            name = f"{name} *"
        elif modifier != "C":
            return None, f"modifier {modifier!r} needs a planner", False
    return name, None, False


def _read_registers(ctx: Any, start: int) -> tuple[set[int], set[int], dict[str, list[int]]]:
    reads = argument_reads(ctx, start)
    gprs = {GPR.index(name) for name in reads if not name.startswith("f")}
    fprs = {int(name[1:]) for name in reads if name.startswith("f")}
    return gprs, fprs, reads


def _exits_unset(ctx: Any, start: int) -> tuple[bool, list[str]]:
    rows = return_sources(ctx, start)
    ok = bool(rows) and all(
        row.startswith("jr ra@") and "v0<-entry;" in row and row.endswith("f0<-entry") for row in rows
    )
    return ok, rows


def _exits_pass_through(ctx: Any, start: int) -> tuple[bool, list[str]]:
    """Every value v0 and f0 can hold at a return is dead as a result.

    Allowed: nothing (entry), a callee's result (user decision 2026-10-20),
    or a scratch value that some other instruction in the function reads (it
    was a temporary: stored, moved to the FPU, passed on, used as a base --
    second user decision 2026-10-20).  A value computed only to be returned
    (a lone `li v0,0` before `jr ra`) is not.
    """

    rows = return_sources(ctx, start)
    flow = ctx.flow(start)
    used: set[tuple[Any, int, bool]] = set()
    for pc in range(start, flow.end, 4):
        if not flow.reachable(pc):
            continue
        read_g, read_f = _reads_at(ctx, pc, flow.end)
        for register, fpr, reads in ((2, False, read_g), (0, True, read_f)):
            if register in reads:
                for d in _through_calls(ctx, flow, flow.defs(pc, register, fpr), register, fpr):
                    used.add((d, register, fpr))

    def dead(definitions: set[Any], register: int, fpr: bool) -> bool:
        for d in definitions:
            if d == "entry" or (d, register, fpr) in used:
                continue
            prev = flow.fn.decoded.get(d - 4, {})
            if prev.get("kind") in ("call", "call-branch"):
                continue  # a callee's result
            return False
        return True

    for pc in range(start, flow.end, 4):
        if not flow.reachable(pc):
            continue
        insn = ctx.code.word(pc)
        if insn == JR_RA:
            sources = [(2, False), (0, True)]
        elif insn >> 26 == 0x02:
            target = ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)
            if start <= target < flow.end:
                continue
            # The callee's result, plus what reaches the jump where it may leave the register.
            sources = [(r, f) for r, f in ((2, False), (0, True)) if callee_preserves(ctx, target, r, f) != "none"]
        elif insn >> 26 == 0x00 and insn & 0x3F == 0x08:
            return False, rows  # indirect jump: unknown
        else:
            continue
        for register, fpr in sources:
            definitions = _through_calls(ctx, flow, flow.after(pc + 4, register, fpr), register, fpr)
            if not dead(definitions, register, fpr):
                return False, rows
    return bool(rows), rows


def _callers_ignore_v0(ctx: Any, start: int, depth: int = 0, seen: frozenset[int] = frozenset()) -> tuple[bool, int]:
    """No code ever reads the value this function leaves in v0 or f0.

    Every direct call site leaves both unread on every path.  A caller that
    returns the value (or tail-calls this function) passes the question on:
    its own call sites must ignore it too, and nothing may take its address.
    Chains are followed six deep; a cycle reads nothing new.
    """

    sites = call_sites(ctx, start)
    if depth > 6:
        return False, len(sites)
    # Only a register this function can leave a value in matters: a caller
    # reading f0 after calling a function that never writes f0 reads its own.
    checked = [fpr for fpr, register in ((False, 2), (True, 0)) if callee_preserves(ctx, start, register, fpr) != "all"]
    for caller, site, kind in sites:
        passes_on = kind == "tail"
        if not passes_on:
            for fpr in checked:
                use = _use_after_call(ctx, caller, site, fpr=fpr)
                if not use.startswith("unused:"):
                    return False, len(sites)
                passes_on = passes_on or "returned by caller" in use
        if passes_on and caller not in seen:
            if ctx.addr_taken.get(caller) or ctx.word32.get(caller):
                return False, len(sites)
            if not _callers_ignore_v0(ctx, caller, depth + 1, seen | {start})[0]:
                return False, len(sites)
    return True, len(sites)


def _sites(values: list[int]) -> str:
    return ",".join(f"0x{pc:x}" for pc in values[:3])


def draft_function(ctx: Any, row: dict[str, Any], live_name: str, types: _TypeIndex) -> dict[str, Any]:
    address = int(row["address"], 16)
    base = {"address": row["address"], "current_name": live_name}
    open_row = {**base, "draft": "open"}
    names = row.get("elf_names") or []
    mangled = next((name for name in names if demangle(name)), None)
    parsed = demangle(mangled) if mangled else None
    stage2 = row.get("stage2") or {}
    stage2_prototype = stage2.get("prototype") if isinstance(stage2, dict) else None
    if row.get("thunk_target"):
        return {**open_row, "open_reason": 'thunk: Ghidra derives its signature from the target'}
    params = list((parsed or {}).get("params") or [])
    if params == [{"modifiers": [], "kind": "builtin", "name": "void"}]:
        params = []

    # U-vararg
    if parsed and params and params[-1].get("kind") == "builtin" and params[-1].get("name") == "...":
        return {**base, "prototype": None, "draft_rule": "U-vararg",
                "unresolved": [f"varargs: the mangled signature {mangled} ends in '...'"]}

    # P-stage2
    if stage2_prototype:
        spellings = [stage2_prototype["return_type"]] + [p["type"] for p in stage2_prototype["parameters"]]
        if _uses_vu0(ctx, address) or not all(types.spells(text) for text in spellings):
            return {**open_row, "open_reason": 'stage 2 prototype: VU0 instructions or a type name that is not exactly one live type'}
        gprs, fprs, reads = _read_registers(ctx, address)
        declared_g, declared_f = _declared_argument_registers(stage2_prototype)
        if gprs <= declared_g and fprs <= declared_f:
            unset, exits = _exits_unset(ctx, address)
            if stage2_prototype["return_type"] != "void" or unset:
                return {
                    **base,
                    "draft_rule": "P-stage2",
                    "prototype": {
                        "return_type": stage2_prototype["return_type"],
                        "parameters": [{"name": p["name"], "type": p["type"]} for p in stage2_prototype["parameters"]],
                        "evidence": [
                            f"stage 2 prototype from DWARF (receiver {stage2.get('receiver') or 'none'}) restated",
                            "argument registers read on any path: "
                            + (", ".join(f"{r}@{_sites(s)}" for r, s in reads.items()) or "none")
                            + "; all declared",
                        ]
                        + ([f"every exit leaves v0 and f0 unset ({len(exits)} jr ra)"] if stage2_prototype["return_type"] == "void" else []),
                    },
                }
        return {**open_row, "open_reason": 'stage 2 prototype: an argument register read is undeclared, or void with a value left in v0/f0'}

    if not parsed:
        if not live_name.startswith("__sinit_"):
            return {**open_row, "open_reason": 'no mangled signature and no stage 2 prototype'}
        params = []

    # U-type: parameter classes, then a proven receiver's class.
    rendered = []
    problems = []
    planner = False
    for index, value in enumerate(params, 1):
        name, reason, type_problem = _render(value, types)
        if name is None:
            (problems if type_problem else []).append(f"parameter {index}: {reason}")
            planner = planner or not type_problem
        rendered.append(name)
    qualifier = (parsed or {}).get("qualifier") or []
    const_method = bool((parsed or {}).get("const"))
    special = (parsed or {}).get("name") in ("__ct", "__dt")
    receiver_type = None
    if qualifier and (const_method or special):
        receiver_type, reason = types.resolve(_class_name(qualifier))
        if receiver_type is None:
            if reason is None:
                return {**open_row, "open_reason": 'receiver class exists only as a NAME@hash copy or in another case'}
            problems.append(f"receiver: {reason}")
    if problems:
        return {**base, "prototype": None, "draft_rule": "U-type", "unresolved": problems}
    if planner or special:
        return {**open_row, "open_reason": 'a parameter needs a planner (function pointer, unknown modifier, NAME@hash or case-variant class) or a constructor/destructor'}

    # P-void
    if _uses_vu0(ctx, address):
        return {**open_row, "open_reason": 'VU0 instructions: register contracts need a planner'}
    sinit = live_name.startswith("__sinit_") and not parsed
    unset, exits = _exits_unset(ctx, address)
    pass_through = False
    if not unset and not sinit:
        through, exits_through = _exits_pass_through(ctx, address)
        ignored, site_count = _callers_ignore_v0(ctx, address)
        if through and ignored and site_count:
            unset, exits, pass_through = True, exits_through, True
    if sinit:
        # A static initializer's type is fixed by the runtime, not by its body:
        # __initialize_cpp_rts calls each through the void (**)(void) .p__sinit
        # table and never reads v0, so a callee result left in v0 is residue.
        unset = bool(exits) and all(row.startswith("jr ra@") for row in exits) and not call_sites(ctx, address)
    if not unset:
        return {**open_row, "open_reason": 'return: v0/f0 hold a value at some exit (own value, or a callee result that some code may read)'}
    slots = [ctx.object_for(site) or f"0x{site:x}" for site in ctx.word32.get(address, ())]
    if sinit:
        if not slots or any(not str(slot).startswith(".p__sinit") for slot in slots):
            return {**open_row, "open_reason": 'static initializer referenced other than by its .p__sinit word'}
        slots = []
    if slots or ctx.addr_taken.get(address):
        return {**open_row, "open_reason": 'address taken or stored in a table: an override or callback contract may apply'}
    parameters = [{"name": f"param_{index}", "type": name} for index, name in enumerate(rendered, 1)]
    gprs, fprs, reads = _read_registers(ctx, address)
    declared_g, declared_f = _declared_argument_registers({"parameters": parameters})
    receiver_evidence = None
    if qualifier:
        with_this = [{"name": "this", "type": "?"}] + parameters
        this_g, this_f = _declared_argument_registers({"parameters": with_this})
        beyond = (gprs - declared_g) | {f + 100 for f in fprs - declared_f}
        if const_method:
            receiver_evidence = "const method (mangled C): it has a receiver"
        elif beyond and gprs <= this_g and fprs <= this_f:
            receiver_evidence = (
                "receiver: reads " + ", ".join(sorted(GPR[r] for r in gprs - declared_g))
                + " beyond the declared parameters, which the receiver accounts for"
            )
        else:
            return {**open_row, "open_reason": 'receiver unproven: not a const method and no register read beyond the parameters'}
        receiver_type, reason = types.resolve(_class_name(qualifier))
        if receiver_type is None:
            if reason is None:
                return {**open_row, "open_reason": 'receiver class exists only as a NAME@hash copy or in another case'}
            return {**base, "prototype": None, "draft_rule": "U-type", "unresolved": [f"receiver: {reason}"]}
        parameters = [{"name": "this", "type": f"{receiver_type} *"}] + [
            {"name": f"param_{index + 1}", "type": p["type"]} for index, p in enumerate(parameters, 1)
        ]
        declared_g, declared_f = _declared_argument_registers({"parameters": parameters})
    if not (gprs <= declared_g and fprs <= declared_f):
        return {**open_row, "open_reason": 'an argument register read on some path is not declared by the mangled signature'}
    evidence = [
        (f"mangled signature {mangled}" if mangled else f"{live_name}: static initializer, no mangled signature")
        + f" gives parameters ({', '.join(rendered) or 'void'})",
        "argument registers read on any path: "
        + (", ".join(f"{r}@{_sites(s)}" for r, s in reads.items()) or "none") + "; all declared",
        (f"every exit leaves v0 and f0 unset or holding a callee's result ({len(exits)} exits) and all "
         f"{len(call_sites(ctx, address))} direct call sites leave v0 unread (callee-result pass-through, "
         "or scratch value decisions of 2026-10-20)" if pass_through else
         f"every exit leaves v0 and f0 unset ({len(exits)} jr ra)" if not sinit else
         f"static initializer: {len(exits)} jr ra, no direct call sites; the runtime calls it through the "
         "void (**)(void) .p__sinit table (__initialize_cpp_rts) and never reads v0"),
        "no word refs or address-taken sites" if not live_name.startswith("__sinit_")
        else "referenced only by its own .p__sinit table word",
    ]
    if receiver_evidence:
        evidence.insert(1, receiver_evidence)
    return {**base, "draft_rule": "P-void",
            "prototype": {"return_type": "void", "parameters": parameters, "evidence": evidence}}


def draft_plan(root: Path, tracker: dict[str, Any], item_id: str, bridge_url: str | None = None) -> dict[str, Any]:
    from .ghidra import GhidraBridge, _function_index, _type_index

    evidence = group_evidence(root, tracker, item_id)
    bridge = GhidraBridge(bridge_url, timeout=300.0)
    live = {int(row["address"], 16): row["name"] for row in _function_index(bridge) if "::" not in row["address"]}
    types = _TypeIndex(_type_index(bridge))
    ctx = context(root)
    functions = []
    for row in evidence["functions"]:
        name = live.get(int(row["address"], 16))
        if name is None:
            raise SocomError(f"no live function at {row['address']}")
        functions.append(draft_function(ctx, row, name, types))
    decided = [row for row in functions if row.get("draft_rule")]
    return {
        "kind": RECON_PLAN_KIND,
        "schema_version": RECON_SCHEMA,
        "work_item_id": item_id,
        "group_sha256": evidence["group_sha256"],
        "target": {"source_sha256": REFERENCE_SHA256},
        "draft": {
            "rules_version": DRAFT_RULES_VERSION,
            "decided": len(decided),
            "open": [row["address"] for row in functions if not row.get("draft_rule")],
        },
        "functions": functions,
        "globals": [],
    }


def _decision(row: dict[str, Any]) -> Any:
    prototype = row.get("prototype")
    if not prototype:
        return "unresolved"
    return (prototype.get("return_type"), tuple(p.get("type") for p in prototype.get("parameters") or []))


def check_drafted_rows(draft: dict[str, Any], plan: dict[str, Any]) -> list[str]:
    """Problems where a plan disagrees with a fresh draft.

    A row carrying ``draft_rule`` must still be decided by the rules, with the
    same rule, name and decision (return and parameter types and names, or
    unresolved); evidence wording may differ between rule versions.  A
    hand-written row that the rules now decide must agree in substance, except
    that a hand-written unresolved row is accepted where the rules have since
    gained a case (unresolved is incomplete, never unsafe).
    """

    fresh = {row["address"]: row for row in draft["functions"] if row.get("draft_rule")}
    rows = {row.get("address"): row for row in plan.get("functions", [])}
    problems = []

    def named(row: dict[str, Any]) -> Any:
        prototype = row.get("prototype")
        if not prototype:
            return "unresolved"
        return (prototype.get("return_type"), tuple((p.get("name"), p.get("type")) for p in prototype.get("parameters") or []))

    for address, row in fresh.items():
        planned = rows.get(address)
        if planned is None:
            problems.append(f"{address}: drafted ({row['draft_rule']}) but missing from the plan")
        elif planned.get("draft_rule"):
            if (planned.get("draft_rule"), planned.get("current_name"), named(planned)) != (
                row["draft_rule"], row.get("current_name"), named(row)
            ):
                problems.append(f"{address}: differs from its {row['draft_rule']} draft")
        elif _decision(planned) != _decision(row) and _decision(planned) != "unresolved":
            problems.append(
                f"{address}: hand-written row disagrees with its {row['draft_rule']} draft "
                f"({_decision(planned)} vs {_decision(row)})"
            )
    for address, row in rows.items():
        if row.get("draft_rule") and address not in fresh:
            problems.append(f"{address}: claims {row['draft_rule']} but the rules leave it open")
    return problems


def void_verdict(ctx: Any, start: int) -> str:
    """Why rules v6 does or does not let a function be void: exits, then callers.

    Prints the first blocking exit value or reader, with the caller chain that
    leads to it, so a planner or reviewer need not walk the callers by hand.
    """

    label = ctx.label(start)
    lines = [f"## {label}"]
    unset, rows = _exits_unset(ctx, start)
    if unset:
        lines.append("exits: v0 and f0 unset at every exit -> void needs no caller check")
        return "\n".join(lines)
    dead, rows = _exits_pass_through(ctx, start)
    lines.extend(f"exit {row}" for row in rows)
    if not dead:
        lines.append(
            "VERDICT open: some exit can return a value that is neither a callee's result nor a "
            "scratch value with another use in the function (or an indirect jump)"
        )
        return "\n".join(lines)
    if ctx.addr_taken.get(start) or ctx.word32.get(start):
        lines.append("VERDICT open: the function's address is taken or stored in a table")
        return "\n".join(lines)

    def walk(function: int, chain: list[str], depth: int, seen: frozenset[int]) -> str | None:
        if depth > 6:
            return "chain deeper than six levels: " + " -> ".join(chain)
        checked = [
            (fpr, name)
            for fpr, register, name in ((False, 2, "v0"), (True, 0, "f0"))
            if callee_preserves(ctx, function, register, fpr) != "all"
        ]
        for caller, site, kind in call_sites(ctx, function):
            passes_on = kind == "tail"
            if not passes_on:
                for fpr, name in checked:
                    use = _use_after_call(ctx, caller, site, fpr=fpr)
                    if not use.startswith("unused:"):
                        return f"{name} read at 0x{site:x} in {ctx.label(caller)}: {use[:120]} (chain: {' -> '.join(chain)})"
                    passes_on = passes_on or "returned by caller" in use
            if passes_on and caller not in seen:
                if ctx.addr_taken.get(caller) or ctx.word32.get(caller):
                    return (
                        f"passed on by {ctx.label(caller)}, whose address is taken or stored in a table "
                        f"(chain: {' -> '.join(chain + [ctx.label(caller)])})"
                    )
                found = walk(caller, chain + [ctx.label(caller)], depth + 1, seen | {function})
                if found:
                    return found
        return None

    blocker = walk(start, [label], 0, frozenset())
    sites = len(call_sites(ctx, start))
    if blocker:
        lines.append(f"VERDICT open: {blocker}")
    elif not sites:
        lines.append("VERDICT open: no direct call sites (pass-through needs at least one)")
    else:
        lines.append(f"VERDICT void: {sites} direct call sites; no code reads the leftover")
    return "\n".join(lines)
