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
         .p__sinit table word, jr ra or tail-jump exits) are void(void) whatever
         v0 holds: the runtime's table type fixes their contract.
P-slot-void
         a void prototype for a virtual function whose vtable slot family is
         void (rules version 18, decision of 2026-10-23): some override's own
         exits leave v0 and f0 unset and no override writes a value a caller
         reads.  Parameters come from the stage 2 prototype when there is one,
         else from the mangled signature, with the receiver proven by the
         vtable slot.  Only rows the older rules leave open take it; this-
         adjusting @N@ stubs stay open (their receiver is the base part at +N).

Rules version 19 (decision of 2026-10-24) adds no draft rule.  It ends the
leftover chains that P-void, P-stage2 and P-slot-void follow at three more
contracts: a function-pointer table entry whose column has an integer
table-family verdict (v0, so an f0 left there is never read), a constructor
returning this, and slot families joined through a base without a vtable.
"""

from __future__ import annotations

import re
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

DRAFT_RULES_VERSION = 19
# Rules version 18 adds the vtable slot-family void rule (decision of
# 2026-10-23).  Passing rules=17 evaluates the earlier behaviour unchanged.
SLOT_VOID_RULES = 18
# Rules version 19 (decision of 2026-10-24, "Yes, all three") ends leftover
# v0/f0 chains at three more contracts: function-pointer table entries whose
# table-family verdict is an integer width, constructors that return this,
# and vtable slot families joined through a base class that has no vtable of
# its own.  It also lets a null argument fit any parameter when reading a
# callback's declared type (the rules-11 gap of CZWeapon::PreTick).  Each only
# removes a blocker; rules=18 evaluates the earlier behaviour unchanged.
CONTRACT_RULES = 19
RULES_VERSIONS = (17, 18, 19)


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

    def nested_in(self, name: str, parent: str) -> bool:
        """The unique live type `name` sits directly under a category named `parent`."""

        found = self.by_name.get(name.casefold(), [])
        if len(found) != 1:
            return False
        segments = [s for s in str(found[0].get("path", "")).split("/") if s]
        if len(segments) < 2:
            return False
        squash = lambda text: "".join(text.split())  # noqa: E731 - spacing differs between spellings
        return squash(segments[-2]) == squash(parent)

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
        components = value.get("components") or []
        name, reason = types.resolve(_class_name(components))
        if name is None:
            return None, reason or "class type needs a planner", reason is not None
        if len(components) > 1 and not types.nested_in(name, readable_component(components[-2])):
            # A nested name (generic_iterator<0>, CharArray) may exist under another
            # parent, e.g. a different template instance (planner of group 182).
            return None, (
                f"nested type {name!r} of {readable_component(components[-2])!r} is absent "
                "(the live type of that name belongs to another parent)"
            ), True
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

    problem, rows = _exit_value_problem(ctx, start)
    return problem is None, rows


def _exit_value_problem(ctx: Any, start: int, indirect_tail_calls: bool = False) -> tuple[str | None, list[str]]:
    """The first value left in v0/f0 at a return that is not dead as a result, and the exit rows.

    None when every value is dead (see ``_exits_pass_through``).  A register
    jump (``jr`` other than ra) is unknown, unless ``indirect_tail_calls``:
    then it adds nothing to check, since a switch's cases have exits of their
    own and any other register jump is a tail call leaving the callee's result.
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

    def live(definitions: set[Any], register: int, fpr: bool) -> Any:
        for d in sorted(definitions, key=str):
            if d == "entry" or (d, register, fpr) in used:
                continue
            prev = flow.fn.decoded.get(d - 4, {})
            if prev.get("kind") in ("call", "call-branch"):
                continue  # a callee's result
            return d
        return None

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
            if not indirect_tail_calls:
                return f"{ctx.text(pc)}@0x{pc:x}: an indirect jump, whose result is unknown", rows
            continue  # a proven switch stays inside; any other register jump is a tail call
        else:
            continue
        for register, fpr in sources:
            definitions = _through_calls(ctx, flow, flow.after(pc + 4, register, fpr), register, fpr)
            d = live(definitions, register, fpr)
            if d is not None:
                return f"{'f0' if fpr else 'v0'}<-{ctx.text(d)}@0x{d:x} at the exit {ctx.text(pc)}@0x{pc:x}", rows
    return (None if rows else "no exit"), rows


_DWARF_VOID: dict[int, frozenset[int]] = {}


def _dwarf_void(ctx: Any) -> frozenset[int]:
    """Entry addresses whose DWARF record declares an explicit void return (FT_void, 20)."""

    key = id(ctx)
    if key not in _DWARF_VOID:
        from .recon_facts import _dies_cached

        path = ctx.elf.path if hasattr(ctx.elf, "path") else None
        found: set[int] = set()
        if path is not None:
            st = Path(path).stat()
            for die in _dies_cached((str(path), st.st_size, int(st.st_mtime)), str(path)):
                if die.tag_name in ("global_subroutine", "subroutine", "member_function"):
                    low = die.integer("low_pc")
                    if low and die.integer("fund_type") == 20:
                        found.add(low)
        _DWARF_VOID[key] = frozenset(found)
    return _DWARF_VOID[key]


_DWARF_RETURNS: dict[int, dict[int, str]] = {}
_GPR_FUNDS = frozenset((0x1, 0x3, 0x5, 0x6, 0x8, 0x9, 0xB, 0xC, 0x8208, 0xA510))


def _dwarf_returns(ctx: Any) -> dict[int, str]:
    """Entry address -> the return register class its DWARF record declares.

    "void" (FT_void), "gpr" (an integer or a pointer/reference: returned in v0),
    or "float" (FT_float: returned in f0).  Double, structs and anything the
    records disagree on are left out.
    """

    key = id(ctx)
    if key not in _DWARF_RETURNS:
        from .recon_facts import _dies_cached

        path = ctx.elf.path if hasattr(ctx.elf, "path") else None
        found: dict[int, set[str]] = {}
        if path is not None:
            st = Path(path).stat()
            for die in _dies_cached((str(path), st.st_size, int(st.st_mtime)), str(path)):
                if die.tag_name not in ("global_subroutine", "subroutine", "member_function"):
                    continue
                low = die.integer("low_pc")
                if not low:
                    continue
                fund = die.integer("fund_type")
                kind = None
                if fund == 0x14:
                    kind = "void"
                elif fund == 0xE:
                    kind = "float"
                elif fund in _GPR_FUNDS:
                    kind = "gpr"
                else:
                    for name, width in (("mod_fund_type", 2), ("mod_u_d_type", 4)):
                        item = die.attribute(name)
                        value = getattr(item, "value", None)
                        if isinstance(value, bytes) and len(value) > width and any(b in (1, 2) for b in value[:-width]):
                            kind = "gpr"  # a pointer or reference
                found.setdefault(low, set()).add(kind or "other")
        _DWARF_RETURNS[key] = {low: next(iter(kinds)) for low, kinds in found.items() if len(kinds) == 1}
    return _DWARF_RETURNS[key]


def _declared_drop(ctx: Any, caller: int, fpr: bool, rules: int = DRAFT_RULES_VERSION) -> bool:
    """The caller's DWARF return cannot carry this register to its own callers.

    Declared void carries nothing; a declared integer/pointer return is read
    from v0, so f0 left by a callee dies there; a declared float return is read
    from f0, so v0 dies there (rules version 10).
    """

    kind = _dwarf_returns(ctx).get(caller)
    if kind is None and fpr and _is_destructor(ctx, caller):
        # Metrowerks destructors return this (void *) in v0 (rules version 16):
        # nothing reads an f0 left by their callees (zBoneUnloadAll, group 188).
        return True
    if kind is None and fpr and rules >= CONTRACT_RULES and _is_constructor(ctx, caller):
        # Constructors return this (void *) in v0 as well (rules version 19,
        # issue bab16750: CSaveModule::CSaveModule ends RegisterModule's f0 chain).
        return True
    return kind == "void" or (fpr and kind == "gpr") or (not fpr and kind == "float")


def _is_destructor(ctx: Any, function: int) -> bool:
    """A __dt destructor whose body keeps the Metrowerks contract."""

    names = _function_names(ctx).get(function, ())
    return any(name.startswith("__dt__") for name in names) and _destructor_evidence(ctx, function) is not None


def _is_constructor(ctx: Any, function: int) -> bool:
    """A __ct constructor that returns its entry a0 (this) in v0 at every exit (rules version 19).

    Every DWARF __ct record in the program declares a `void *` return, which
    the body confirms by returning this through plain copies.  A constructor
    whose address is formed in code or stored in a table could be called
    through another type, so it gets no contract.
    """

    names = _function_names(ctx).get(function, ())
    if not any(name.startswith("__ct__") for name in names):
        return False
    if ctx.addr_taken.get(function) or ctx.word32.get(function):
        return False
    return _returns_this(ctx, function)


_CALLBACKS: dict[tuple[int, bool], dict[int, str]] = {}
_GPR_BUILTINS = frozenset(("char", "signed char", "unsigned char", "short", "unsigned short", "int",
                           "unsigned int", "long", "unsigned long", "long long", "unsigned long long", "bool", "wchar_t",
                           "uint16"))


def _result_class(result: dict[str, Any] | None) -> str | None:
    """Register class of a demangled function type's result: void, gpr (v0) or float (f0)."""

    if not isinstance(result, dict):
        return None
    if any(m in ("P", "R") for m in result.get("modifiers") or []):
        return "gpr"
    if result.get("kind") != "builtin":
        return None
    name = result.get("name")
    if name == "void":
        return "void"
    if name == "float":
        return "float"
    return "gpr" if name in _GPR_BUILTINS else None


_GPR_POSITION = {4: 0, 5: 1, 6: 2, 7: 3, 8: 4, 9: 5, 10: 6, 11: 7}


def _callback_kind(ctx: Any, flow: Any, pc: int, position: int, callee: int, null_fits_any: bool) -> str | None:
    """Result class of the function-pointer parameter at GPR ``position`` of the call at ``pc``.

    Which argument register maps to which parameter is settled by requiring
    every argument register to fit the reading: function-pointer parameters
    get code addresses (or zero), others do not.  With ``null_fits_any``
    (rules version 19) a zero fits any parameter, so `move a3,zero` for
    AddTask's trailing `void *` no longer rejects the reading.
    """

    parsed = next((demangle(n) for n in _function_names(ctx).get(callee, ()) if demangle(n)), None)
    if not parsed:
        return None
    params = parsed.get("params") or []
    if any(
        p.get("kind") == "builtin" and not p.get("modifiers")
        and p.get("name") in ("double", "long long", "unsigned long long")
        for p in params
    ):
        return None  # 64-bit arguments shift the register positions
    # A plain float travels in an FPR (f12...) and takes no GPR slot
    # (AddTask(name, PFfPv_b tick, float, void *): tick in a2).
    params = [
        p for p in params
        if not (p.get("kind") == "builtin" and not p.get("modifiers") and p.get("name") == "float")
    ]

    def code_address(register: int) -> bool | None:
        # True: a function address or zero; False: something else; None: unknown.
        defs = flow.entering_callee(pc + 4, register)
        if len(defs) != 1:
            return None
        (where,) = defs
        if not isinstance(where, int):
            return None
        row = ctx.ref_at.get(where)
        if row and row.get("target") is not None:
            return int(row["target"], 16) in ctx.size
        word = ctx.code.word(where)
        if word >> 26 == 0 and word & 0x3F in (0x21, 0x25, 0x2D) and (word >> 21) & 31 == 0 and (word >> 16) & 31 == 0:
            return None if null_fits_any else True  # move rd,zero: a null callback (or any null pointer)
        return None

    candidates = set()
    for offset in ((0, 1) if parsed.get("qualifier") else (0,)):
        index = position - offset
        if not (0 <= index < len(params) and params[index].get("kind") == "function"):
            continue
        fits = True
        for register, slot in _GPR_POSITION.items():
            argument = slot - offset
            if argument < 0 or argument >= len(params):
                continue
            seen = code_address(register)
            if seen is None:
                continue
            if seen != (params[argument].get("kind") == "function"):
                fits = False
                break
        if fits:
            candidates.add(_result_class(params[index].get("result")))
    return candidates.pop() if len(candidates) == 1 else None


def _callback_returns(ctx: Any, rules: int = DRAFT_RULES_VERSION) -> dict[int, str]:
    """Function -> return class declared by the callback parameter it is passed as.

    A function whose address is formed in code (never stored in a table) and
    always passed straight to a direct call, in an argument register whose
    position in the callee's mangled parameters is a function pointer, is
    only ever called through that declared type (rules version 11).  From
    rules version 19 a site the earlier reading leaves undecided is read again
    with a null argument fitting any parameter.
    """

    widened = rules >= CONTRACT_RULES
    key = (id(ctx), widened)
    if key in _CALLBACKS:
        return _CALLBACKS[key]
    from .recon_facts import _writes

    found: dict[int, str] = {}
    for function, sites in ctx.addr_taken.items():
        if function not in ctx.size or ctx.word32.get(function):
            continue
        kinds: set[str | None] = set()
        for site in sites:
            owner = ctx.owner(site)
            if owner is None:
                kinds.add(None)
                break
            written = _writes(ctx.code.word(site))[0]
            flow = ctx.flow(owner)
            kind = None
            for pc in range(max(owner, site - 4), min(site + 64, owner + ctx.size[owner]), 4):
                insn = ctx.code.word(pc)
                if insn >> 26 != 0x03:
                    continue
                registers = [r for r in written if r in _GPR_POSITION and flow.entering_callee(pc + 4, r) == {site}]
                if len(registers) != 1:
                    break
                callee = ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)
                position = _GPR_POSITION[registers[0]]
                kind = _callback_kind(ctx, flow, pc, position, callee, False)
                if kind is None and widened:
                    kind = _callback_kind(ctx, flow, pc, position, callee, True)
                break
            kinds.add(kind)
        if len(kinds) == 1 and None not in kinds:
            found[function] = kinds.pop()
    _CALLBACKS[key] = found
    return found


def _copy_source(insn: int) -> int | None:
    """Source register of a plain copy (move/addu/or/daddu with zero), else None."""

    if insn >> 26 or (insn & 0x3F) not in (0x21, 0x25, 0x2D) or (insn >> 6) & 0x1F:
        return None
    rs, rt = (insn >> 21) & 0x1F, (insn >> 16) & 0x1F
    if rt == 0:
        return rs
    if rs == 0:
        return rt
    return None


def _returns_this(ctx: Any, start: int) -> bool:
    """Every exit returns the entry a0 (this), through plain register copies."""

    flow = ctx.flow(start)
    exits = 0
    for pc in range(start, flow.end, 4):
        if not flow.reachable(pc):
            continue
        insn = ctx.code.word(pc)
        if insn == JR_RA:
            exits += 1
            if not _traces_to_a0_register(ctx, flow, flow.after(pc + 4, 2), 2, 4):
                return False
        elif insn >> 26 == 0x02 or (insn >> 26 == 0x00 and insn & 0x3F == 0x08):
            return False  # tail jumps and register jumps: not a plain return of this
    return exits > 0


def _a1_short(ctx: Any, start: int) -> str | None:
    """How a1 (the destructor flags) is used: unread, or sign-extended from 16 bits."""

    flow = ctx.flow(start)
    reads = argument_reads(ctx, start)
    if "a1" not in reads:
        return "a1 unread"
    for pc in range(start, flow.end, 4):
        insn = ctx.code.word(pc)
        if insn >> 26 == 0 and (insn & 0x3F) in (0x00, 0x3C) and (insn >> 6) & 0x1F == 16:
            rt = (insn >> 16) & 0x1F
            if _traces_to_a0_register(ctx, flow, flow.defs(pc, rt), rt, 5):
                return f"a1 sign-extended from 16 bits ({ctx.text(pc)}@0x{pc:x})"
    return None


def _traces_to_a0_register(ctx: Any, flow: Any, defs: set[Any], register: int, wanted: int, depth: int = 0) -> bool:
    """Definitions are the entry value of `wanted`, through plain copies."""

    if not defs or depth > 6:
        return False
    for d in defs:
        if d == "entry":
            if register != wanted:
                return False
            continue
        if not isinstance(d, int):
            return False
        source = _copy_source(ctx.code.word(d))
        if source is None or not _traces_to_a0_register(ctx, flow, flow.defs(d, source), source, wanted, depth + 1):
            return False
    return True


def _destructor_evidence(ctx: Any, start: int) -> list[str] | None:
    """Evidence for the Metrowerks destructor contract `void *(X *this, short flags)` (rules v14).

    Every DWARF __dt record in the program declares a `void *` return, the
    local CPlusLib.h declares the flags argument as short, and the body must
    agree: only a0/a1 read, a1 unread or sign-extended from 16 bits, and every
    exit returning the entry a0.
    """

    reads = set(argument_reads(ctx, start))
    if not reads <= {"a0", "a1"}:
        return None
    flags = _a1_short(ctx, start)
    if flags is None or not _returns_this(ctx, start):
        return None
    return [
        "Metrowerks destructor convention: every DWARF __dt record declares a void * return; "
        "the local CPlusLib.h DTORARG_TYPE is short",
        f"argument registers read: {', '.join(sorted(reads)) or 'none'}; {flags}",
        "every exit returns the entry a0 (this) through plain register copies",
    ]


def _stage2_parameters(stage2_prototype: dict[str, Any], mangled_params: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Stage 2 parameters, with a mangled `bool` (b) kept where DWARF 1 says uchar.

    DWARF 1 has no bool type, so the Metrowerks records spell bool as uchar;
    the mangled signature still says bool (review of group 128: AllCollapse).
    """

    rows = [{"name": p["name"], "type": p["type"]} for p in stage2_prototype["parameters"]]
    explicit = [row for row in rows if row["name"] != "this"]
    if len(explicit) == len(mangled_params):
        for row, mangled in zip(explicit, mangled_params):
            if (
                row["type"] == "uchar"
                and mangled.get("kind") == "builtin"
                and mangled.get("name") == "bool"
                and not mangled.get("modifiers")
            ):
                row["type"] = "bool"
    return rows


_SLOTS: dict[int, dict[int, str]] = {}


def _vtable_class(name: str) -> str | None:
    """Readable class name of a `__vt__<mangled class>` symbol."""

    if not name.startswith("__vt__"):
        return None
    parsed = demangle("x__" + name[len("__vt__"):] + "Fv")
    if not parsed or not parsed.get("qualifier"):
        return None
    return "::".join(parsed["qualifier"])


def _slot_returns(ctx: Any) -> dict[int, str]:
    """Virtual function -> return class declared for its vtable slot (rules version 13).

    Classes linked by DWARF inheritance form a family.  Functions stored at
    the same offset of the family's vtables, with the same method name, are
    one virtual function: C++ gives every override the base's return type.
    When the DWARF records among them declare one return class (void, v0 or
    f0) and none disagrees, every function in the slot has that contract.
    """

    key = id(ctx)
    if key in _SLOTS:
        return _SLOTS[key]
    from .recon_facts import _dies_cached

    path = ctx.elf.path if hasattr(ctx.elf, "path") else None
    found: dict[int, str] = {}
    if path is None:
        _SLOTS[key] = found
        return found
    st = Path(path).stat()
    dies = _dies_cached((str(path), st.st_size, int(st.st_mtime)), str(path))
    by_offset = {die.offset: die for die in dies}
    # Union-find over class names linked by inheritance.
    parent: dict[str, str] = {}

    def root(name: str) -> str:
        while parent.setdefault(name, name) != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    current = None
    for die in dies:
        if die.tag_name in ("class_type", "structure_type"):
            current = die.string("name")
        elif die.tag_name == "inheritance" and current:
            base = by_offset.get(die.integer("user_def_type") or -1)
            base_name = base.string("name") if base is not None else None
            if base_name:
                parent[root(current)] = root(base_name)
    # Vtable words: (family, offset) -> functions.
    names = _function_names(ctx)
    slots: dict[tuple[str, int], set[int]] = {}
    for symbol in ctx.elf.symbols():
        cls = _vtable_class(symbol.name or "")
        if not cls or not symbol.size:
            continue
        family = root(cls.split("::")[-1])
        for offset in range(0, symbol.size, 4):
            site = symbol.value + offset
            if site in ctx.reloc32:
                target = ctx.code.word(site)
                if target in ctx.size:
                    slots.setdefault((family, offset), set()).add(target)
    declared = _dwarf_returns(ctx)
    for functions in slots.values():
        methods = set()
        for function in functions:
            parsed = next((demangle(n) for n in names.get(function, ()) if demangle(n)), None)
            methods.add(parsed.get("name") if parsed else None)
        if len(methods) != 1 or None in methods:
            continue  # not provably one virtual function
        kinds = {declared[f] for f in functions if f in declared}
        if len(kinds) == 1 and "other" not in kinds:
            kind = kinds.pop()
            for function in functions:
                if found.get(function, kind) != kind:
                    found[function] = "conflict"
                else:
                    found[function] = kind
    _SLOTS[key] = {f: k for f, k in found.items() if k != "conflict"}
    return _SLOTS[key]


def _only_in_vtables(ctx: Any, function: int) -> bool:
    """Every reference to the function is a vtable word (no code address formation)."""

    if ctx.addr_taken.get(function):
        return False
    sites = ctx.word32.get(function, ())
    return bool(sites) and all((ctx.object_for(site) or "").startswith("__vt__") for site in sites)


def _contract_drops(
    ctx: Any, function: int, fpr: bool, rules: int = DRAFT_RULES_VERSION, families: bool = True
) -> bool:
    """A declared callback, table or vtable-slot contract never hands this register on.

    From rules version 18 a void slot family is such a contract too (unless
    ``families`` is false: a slot family's own walk uses no family verdicts);
    from version 19 a function-pointer table column of integer width ends an
    f0 chain.
    """

    if _callback_drops(ctx, function, fpr, rules):
        return True
    if _table_drops(ctx, function, fpr, rules):
        return True
    if families and rules >= SLOT_VOID_RULES and _slot_void(ctx, function, rules):
        return True
    if not _only_in_vtables(ctx, function):
        return False
    kind = _slot_returns(ctx).get(function)
    return kind == "void" or (fpr and kind == "gpr") or (not fpr and kind == "float")


def _declared_void(ctx: Any, function: int, rules: int = DRAFT_RULES_VERSION, families: bool = True) -> bool:
    """Referenced only through a contract (callback type or vtable slot) declared void.

    From rules version 18 a void slot family counts as such a contract (unless
    ``families`` is false).
    """

    if _callback_returns(ctx, rules).get(function) == "void":
        return True
    if _only_in_vtables(ctx, function) and _slot_returns(ctx).get(function) == "void":
        return True
    return families and rules >= SLOT_VOID_RULES and _slot_void(ctx, function, rules)


# -- vtable slot families (rules version 18) ----------------------------------

# Metrowerks names a this-adjusting stub @N@Method (and @N@M@Method through a
# virtual base): it adjusts a0 and jumps to the overrider.
_STUB_PREFIX = re.compile(r"^@(?:-?\d+@)+")
_FAMILIES: dict[tuple[int, bool], dict[int, "SlotFamily"]] = {}
# id(ctx) -> {(rules, first member): verdict}
_FAMILY_VERDICTS: dict[int, dict[tuple[int, int], dict[str, Any]]] = {}


class SlotFamily:
    """Every function occupying one virtual function's vtable slots.

    ``members`` are sorted function entries (overriders, inherited entries and
    @N@ stubs), ``slots`` the vtable words that hold them, ``methods`` their
    method names with any @N@ prefix removed.
    """

    __slots__ = ("members", "slots", "methods")

    def __init__(self, members: tuple[int, ...], slots: tuple[int, ...], methods: frozenset[str | None]) -> None:
        self.members, self.slots, self.methods = members, slots, methods

    @property
    def method(self) -> str | None:
        """The one method name the members share, else None (not provably one virtual)."""

        return next(iter(self.methods)) if len(self.methods) == 1 else None


def _symbol_class(name: str, prefix: str) -> str | None:
    """Readable class of a `__vt__<class>` or `__RTTI__<class>` symbol."""

    if not name.startswith(prefix):
        return None
    parsed = demangle("x__" + name[len(prefix):] + "Fv")
    if not parsed or not parsed.get("qualifier"):
        return None
    return "::".join(parsed["qualifier"])


def _method_name(ctx: Any, function: int) -> str | None:
    for name in _function_names(ctx).get(function, ()):
        parsed = demangle(name)
        if parsed and parsed.get("name"):
            return _STUB_PREFIX.sub("", parsed["name"]) or None
    return None


def _is_stub(ctx: Any, function: int) -> bool:
    """A this-adjusting @N@ stub (by its symbol name)."""

    return any(_STUB_PREFIX.match(name) for name in _function_names(ctx).get(function, ()))


def _stub_target(ctx: Any, function: int) -> int | None:
    """The overrider a @N@ stub jumps to: its one `j` that leaves the stub."""

    if not _is_stub(ctx, function) or function not in ctx.size:
        return None
    end = function + ctx.size[function]
    targets = set()
    for pc in range(function, end, 4):
        insn = ctx.code.word(pc)
        if insn >> 26 == 0x02:
            target = ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)
            if not function <= target < end:
                targets.add(target)
    if len(targets) != 1:
        return None
    (target,) = targets
    return target if target in ctx.size else None


def _signed32(value: int) -> int:
    return value - (1 << 32) if value & 0x80000000 else value


def _method_class(ctx: Any, function: int) -> str | None:
    """The class qualifying a function's mangled name, spelled as `_symbol_class` spells RTTI classes."""

    for name in _function_names(ctx).get(function, ()):
        parsed = demangle(name)
        if parsed and parsed.get("qualifier"):
            return "::".join(parsed["qualifier"])
    return None


def slot_families(ctx: Any, rules: int = DRAFT_RULES_VERSION) -> dict[int, SlotFamily]:
    """Function -> its vtable slot family, derived from the ELF alone.

    A Metrowerks vtable is one or more blocks, each an RTTIVTableHeader
    {type_info *; int complete_offset;} followed by its slots.  The first block
    starts the table; another starts at each relocated word naming an
    __RTTI__ record, and serves the subobject at -complete_offset.  Slot i of
    a class's block at offset N is slot i of the primary block of every base
    the class's RTTI base list places at N (non-ambiguous entries).  A @N@
    stub joins the overrider it jumps to.  A function stored in several slots
    joins them all (one overrider of several bases' virtuals).

    From rules version 19 a base without a vtable of its own still joins the
    blocks that place it (decision of 2026-10-24).  Its slots are a prefix of
    each such block, and a slot holding one of the base's own methods (an
    inherited, not overridden, entry such as zdb::CTextureRelocMgr::
    PreGetSprPacket in __vt__Q23zdb15CBatchRelocator+0x10) proves the prefix
    reaches that slot; slots up to there are joined across the blocks.
    """

    joined = rules >= CONTRACT_RULES
    key = (id(ctx), joined)
    if key in _FAMILIES:
        return _FAMILIES[key]
    rtti: dict[int, str] = {}
    rtti_by_class: dict[str, int] = {}
    vtables = []
    for symbol in ctx.elf.symbols():
        name = symbol.name or ""
        if not symbol.size:
            continue
        if name.startswith("__RTTI__") and (cls := _symbol_class(name, "__RTTI__")):
            rtti[symbol.value] = cls
            rtti_by_class.setdefault(cls, symbol.value)
        elif name.startswith("__vt__") and (cls := _symbol_class(name, "__vt__")):
            vtables.append((symbol.value, symbol.size, cls))
    parent: dict[Any, Any] = {}

    def find(node: Any) -> Any:
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: Any, b: Any) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    lengths: dict[tuple[str, int], int] = {}
    holders: dict[Any, list[int]] = {}
    own_rtti: dict[str, int] = {}
    held: dict[tuple[str, int, int], set[int]] = {}
    for address, size, cls in sorted(vtables):
        if address in ctx.reloc32 and ctx.code.word(address) in rtti:
            own_rtti.setdefault(cls, ctx.code.word(address))
        heads = [0] + [
            offset for offset in range(8, size, 4)
            if address + offset in ctx.reloc32 and ctx.code.word(address + offset) in rtti
        ]
        for index, head in enumerate(heads):
            end = heads[index + 1] if index + 1 < len(heads) else size
            subobject = -_signed32(ctx.code.word(address + head + 4))
            count = max(0, (end - head - 8) // 4)
            lengths[(cls, subobject)] = max(lengths.get((cls, subobject), 0), count)
            for slot in range(count):
                site = address + head + 8 + 4 * slot
                if site in ctx.reloc32 and ctx.code.word(site) in ctx.size:
                    function = ctx.code.word(site)
                    union(("slot", cls, subobject, slot), ("fn", function))
                    holders.setdefault(function, []).append(site)
                    held.setdefault((cls, subobject, slot), set()).add(function)
    placed: list[tuple[str, str, int]] = []
    for cls in sorted({cls for cls, _subobject in lengths}):
        record = own_rtti.get(cls, rtti_by_class.get(cls))
        if record is None or record + 4 not in ctx.reloc32:
            continue
        cursor = ctx.code.word(record + 4)
        for _ in range(256):
            if cursor not in ctx.reloc32:
                break
            base = rtti.get(ctx.code.word(cursor))
            offset = ctx.code.word(cursor + 4)
            cursor += 8
            if base is None or offset & 0x80000000:
                continue  # unknown base, or ambiguous: no single subobject
            placed.append((cls, base, offset))
            for slot in range(min(lengths.get((base, 0), 0), lengths.get((cls, offset), 0))):
                union(("slot", cls, offset, slot), ("slot", base, 0, slot))
    if joined:
        # A base with no vtable: its own methods inherited into a derived block prove its extent.
        extent: dict[str, int] = {}
        for cls, base, offset in placed:
            if (base, 0) in lengths:
                continue
            for slot in range(lengths.get((cls, offset), 0)):
                if any(_method_class(ctx, f) == base for f in held.get((cls, offset, slot), ())):
                    extent[base] = max(extent.get(base, 0), slot + 1)
        for cls, base, offset in placed:
            for slot in range(min(extent.get(base, 0), lengths.get((cls, offset), 0))):
                union(("slot", cls, offset, slot), ("slot", base, 0, slot))
    nodes = set(holders)
    for function in sorted(holders):
        target = _stub_target(ctx, function)
        if target is not None:
            union(("fn", function), ("fn", target))
            nodes.add(target)
    groups: dict[Any, list[int]] = {}
    for function in sorted(nodes):
        groups.setdefault(find(("fn", function)), []).append(function)
    found: dict[int, SlotFamily] = {}
    for members in groups.values():
        family = SlotFamily(
            tuple(sorted(members)),
            tuple(sorted(site for member in members for site in holders.get(member, ()))),
            frozenset(_method_name(ctx, member) for member in members),
        )
        for member in members:
            found[member] = family
    _FAMILIES[key] = found
    return found


def _witness_fits(ctx: Any, function: int) -> bool:
    """The body reads only the registers its mangled signature gives (with this).

    A by-value struct result comes back through a hidden pointer in a0 and
    leaves v0 untouched; its receiver then arrives in a1, which this refuses.
    """

    from .type_layout import parameter_registers

    parsed = next((demangle(n) for n in _function_names(ctx).get(function, ()) if demangle(n)), None)
    if not parsed or not parsed.get("qualifier"):
        return False
    mapped, _complete = parameter_registers(parsed.get("params"), True)
    allowed = {"a0"} | {register for register, _value in mapped}
    return set(argument_reads(ctx, function)) <= allowed


def slot_family_verdict(ctx: Any, function: int, rules: int = DRAFT_RULES_VERSION) -> dict[str, Any] | None:
    """The rules-18 verdict of a function's vtable slot family (decision of 2026-10-23).

    The family is void when one override's own body proves void (every exit
    is `jr ra` with v0 and f0 unset, its argument reads fit its mangled
    signature, and no DWARF record declares a return) and no member writes a
    value a caller reads.  A member blocks the rule when its DWARF record
    declares a non-void return; when an exit holds its own value (not a
    callee's result -- an indirect tail call's included -- or a scratch value:
    computed only to be returned, so the slot's callers read it); when it
    leaves a value and its address is formed
    in code or stored outside vtables; or when a direct caller reads the value
    it leaves, followed through callers that return it as in rules version
    17.  A caller that is itself a member hands the value to the slot, which
    is what is being decided, so the walk stops there.  The walk uses the
    rules-17 contracts, not other families' verdicts; under rules 19 it also
    uses that version's table and constructor contracts, and the families
    joined through bases without a vtable.

    Returns None for a function in no vtable slot, else a dict with
    ``family``, ``void``, ``witnesses`` and ``blockers`` ((member, reason)).
    """

    family = slot_families(ctx, rules).get(function)
    if family is None:
        return None
    cache = _FAMILY_VERDICTS.setdefault(id(ctx), {})
    if (rules, family.members[0]) in cache:
        return cache[(rules, family.members[0])]
    declared = _dwarf_returns(ctx)
    witnesses = []
    blockers: list[tuple[int, str]] = []
    members = frozenset(family.members)
    for member in family.members:
        kind = declared.get(member)
        if kind in ("gpr", "float", "other"):
            blockers.append((member, f"its DWARF record declares a non-void return ({kind})"))
            continue
        if _exits_unset(ctx, member)[0]:
            if not _is_stub(ctx, member) and _witness_fits(ctx, member):
                witnesses.append(member)
            continue
        problem, rows = _exit_value_problem(ctx, member, indirect_tail_calls=True)
        if not rows:
            continue  # it never returns, so it leaves no value
        if problem:
            blockers.append((
                member,
                f"an exit holds its own value ({problem}): computed only to be returned, so callers "
                "through the slot read it",
            ))
            continue
        if not _only_in_vtables(ctx, member):
            blockers.append((
                member,
                "it leaves a value and its address is formed in code or stored outside vtables "
                "(callers through that pointer are not followed)",
            ))
            continue
        checked = [
            (fpr, name)
            for fpr, register, name in ((False, 2, "v0"), (True, 0, "f0"))
            if callee_preserves(ctx, member, register, fpr) != "all"
        ]
        reader = _first_reader(ctx, member, checked, rules=rules, stop=members, families=False)
        if reader:
            blockers.append((member, reader))
    earlier = slot_families(ctx, SLOT_VOID_RULES).get(function) if rules >= CONTRACT_RULES else family
    verdict = {
        "family": family,
        "void": bool(witnesses) and not blockers and family.method is not None,
        "witnesses": witnesses,
        "blockers": blockers,
        # Rules version 19 joined it through a base class without a vtable of its own.
        "joined": earlier is None or earlier.members != family.members,
    }
    cache[(rules, family.members[0])] = verdict
    return verdict


def _slot_void(ctx: Any, function: int, rules: int = DRAFT_RULES_VERSION) -> bool:
    verdict = slot_family_verdict(ctx, function, rules)
    return bool(verdict and verdict["void"])


def _family_summary(ctx: Any, verdict: dict[str, Any]) -> str:
    family = verdict["family"]
    method = family.method or "/".join(sorted(str(m) for m in family.methods))
    return f"{len(family.members)} functions in {len(family.slots)} vtable slots (method {method})"


def slot_family_lines(ctx: Any, verdict: dict[str, Any]) -> list[str]:
    """Short text for `recon void`: the family, its witness and its first blocker."""

    family = verdict["family"]
    head = f"slot family: {_family_summary(ctx, verdict)}"
    if family.method is None:
        return [head + ": the members' method names differ, so they are not provably one virtual"]
    witness = (
        f"{ctx.label(verdict['witnesses'][0])} has no path that writes v0 or f0 before returning"
        if verdict["witnesses"] else "no override's own exits leave v0 and f0 unset"
    )
    lines = [f"{head}; {witness}"]
    if verdict.get("joined"):
        lines.append(
            "slot family joined through a base class without a vtable of its own: a slot holding the base's "
            "inherited method is the base's slot in every block that places the base (rules version 19)"
        )
    for member, reason in verdict["blockers"][:3]:
        lines.append(f"slot family blocked by {ctx.label(member)}: {reason}")
    if len(verdict["blockers"]) > 3:
        lines.append(f"slot family: {len(verdict['blockers']) - 3} more blocking overrides")
    return lines


_NAMES: dict[int, tuple[Any, dict[int, list[str]]]] = {}


def _function_names(ctx: Any) -> dict[int, list[str]]:
    cached = _NAMES.get(id(ctx))
    if cached is None or cached[0] is not ctx.functions:
        cached = _NAMES[id(ctx)] = (ctx.functions, {row["start"]: row["names"] for row in ctx.functions})
    return cached[1]


def _callback_drops(ctx: Any, function: int, fpr: bool, rules: int = DRAFT_RULES_VERSION) -> bool:
    """The function's declared callback type never hands this register to its caller."""

    kind = _callback_returns(ctx, rules).get(function)
    return kind == "void" or (fpr and kind == "gpr") or (not fpr and kind == "float")


def _table_drops(ctx: Any, function: int, fpr: bool, rules: int = DRAFT_RULES_VERSION) -> bool:
    """A function-pointer table entry whose column returns an integer never hands on f0 (rules version 19).

    `recon table-family` proves the column's return width; an integer width
    is returned in v0, so the dispatcher never reads an f0 the entry leaves.
    """

    if rules < CONTRACT_RULES or not fpr:
        return False
    from .recon_table import table_contracts

    return function in table_contracts(ctx)


def _callers_ignore_v0(
    ctx: Any, start: int, depth: int = 0, seen: frozenset[int] = frozenset(), registers: tuple | None = None,
    rules: int = DRAFT_RULES_VERSION, families: bool = True,
) -> tuple[bool, int]:
    """No code ever reads the value this function leaves in v0 or f0.

    Every direct call site leaves the register unread on every path.  A caller
    that returns it (or tail-calls this function) passes the question on for
    that same register: its own call sites must leave it unread too, and
    nothing may take its address.  Chains are followed twelve deep (rules version 17); a cycle reads
    nothing new.
    """

    sites = call_sites(ctx, start)
    if depth > 12:
        return False, len(sites)
    if registers is None:
        # Only a register this function can leave a value in matters: a caller
        # reading f0 after calling a function that never writes f0 reads its own.
        registers = tuple(
            (fpr, register) for fpr, register in ((False, 2), (True, 0))
            if callee_preserves(ctx, start, register, fpr) != "all"
        )
    for caller, site, kind in sites:
        for fpr, register in registers:
            passes_on = kind == "tail"
            if not passes_on:
                use = _use_after_call(ctx, caller, site, fpr=fpr)
                if not use.startswith("unused:"):
                    return False, len(sites)
                passes_on = "returned by caller" in use
            if passes_on and caller not in seen:
                if caller in _dwarf_void(ctx) or _declared_drop(ctx, caller, fpr, rules):
                    continue  # its declared return never carries this register to its callers
                if (ctx.addr_taken.get(caller) or ctx.word32.get(caller)) and not _contract_drops(
                    ctx, caller, fpr, rules, families
                ):
                    return False, len(sites)
                if not _callers_ignore_v0(ctx, caller, depth + 1, seen | {start}, ((fpr, register),), rules, families)[0]:
                    return False, len(sites)
    return True, len(sites)


def _first_reader(
    ctx: Any, start: int, checked: list[tuple[bool, str]], rules: int = DRAFT_RULES_VERSION,
    stop: frozenset[int] = frozenset(), families: bool = True,
) -> str | None:
    """The first code that reads what ``start`` leaves in v0/f0, with its caller chain, or None.

    The same walk as ``_callers_ignore_v0``, keeping the evidence.  A caller in
    ``stop`` (the slot family being decided) ends its chain.
    """

    def walk(function: int, chain: list[str], depth: int, seen: frozenset[int], checked: list) -> str | None:
        if depth > 12:
            return "chain deeper than twelve levels: " + " -> ".join(chain)
        for caller, site, kind in call_sites(ctx, function):
            for fpr, name in checked:
                passes_on = kind == "tail"
                if not passes_on:
                    use = _use_after_call(ctx, caller, site, fpr=fpr)
                    if not use.startswith("unused:"):
                        return f"{name} read at 0x{site:x} in {ctx.label(caller)}: {use[:120]} (chain: {' -> '.join(chain)})"
                    passes_on = "returned by caller" in use
                if passes_on and caller not in seen:
                    if caller in stop:
                        continue  # a member of the slot family: it hands the value to the slot
                    if caller in _dwarf_void(ctx) or _declared_drop(ctx, caller, fpr, rules):
                        continue  # declared return (DWARF) never carries this register to its callers
                    if (ctx.addr_taken.get(caller) or ctx.word32.get(caller)) and not _contract_drops(
                        ctx, caller, fpr, rules, families
                    ):
                        return (
                            f"{name} passed on by {ctx.label(caller)}, whose address is taken or stored in a table "
                            f"(chain: {' -> '.join(chain + [ctx.label(caller)])})"
                        )
                    found = walk(caller, chain + [ctx.label(caller)], depth + 1, seen | {function}, [(fpr, name)])
                    if found:
                        return found
        return None

    return walk(start, [ctx.label(start)], 0, frozenset(), checked)


def _sites(values: list[int]) -> str:
    return ",".join(f"0x{pc:x}" for pc in values[:3])


def _slot_receiver(ctx: Any, function: int) -> str | None:
    """Receiver evidence from a vtable word: a virtual function is a non-static member."""

    sites = [site for site in ctx.word32.get(function, ()) if (ctx.object_for(site) or "").startswith("__vt__")]
    if not sites or _is_stub(ctx, function):
        return None
    return f"receiver: stored in vtable slot {ctx.object_for(min(sites))}, so it is a virtual member and a0 is this"


def _slot_evidence(ctx: Any, function: int, rules: int = DRAFT_RULES_VERSION) -> str:
    verdict = slot_family_verdict(ctx, function, rules) or {}
    witness = ctx.label(verdict["witnesses"][0]) if verdict.get("witnesses") else "?"
    return (
        f"vtable slot family of {_family_summary(ctx, verdict)}: {witness} has no path that writes v0 or f0 "
        "before returning and no override writes a value a caller reads, so the slot returns void "
        "(rules version 18, decision of 2026-10-23)"
    )


def draft_function(
    ctx: Any, row: dict[str, Any], live_name: str, types: _TypeIndex, rules: int = DRAFT_RULES_VERSION
) -> dict[str, Any]:
    """One plan row: decided by a rule (``draft_rule``), or open for the planner.

    ``rules`` selects a rules version from ``RULES_VERSIONS``; 17 leaves out
    the slot-family rule of version 18, and 18 the contracts of version 19.
    """

    if rules not in RULES_VERSIONS:
        raise SocomError(f"draft rules version {rules} is not one of {', '.join(map(str, RULES_VERSIONS))}")
    drafted = _draft_row(ctx, row, live_name, types, rules)
    address = int(row["address"], 16)
    if drafted.get("draft") == "open" and rules >= SLOT_VOID_RULES and _is_stub(ctx, address) and _slot_void(ctx, address, rules):
        drafted["open_reason"] = (
            "this-adjusting @N@ stub whose vtable slot family is void (rules version 18): the return is void; "
            "its receiver is the base part at +N, so a planner decides the parameters"
        )
    return drafted


def _draft_row(ctx: Any, row: dict[str, Any], live_name: str, types: _TypeIndex, rules: int) -> dict[str, Any]:
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
    # The slot-family rule (version 18) decides only what the older rules leave
    # open; @N@ stubs stay open (their receiver is the base part at +N).
    slot_void = rules >= SLOT_VOID_RULES and not _is_stub(ctx, address) and _slot_void(ctx, address, rules)
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
            declared_void = stage2_prototype["return_type"] == "void" and address in _dwarf_void(ctx)
            by_slot = False
            if stage2_prototype["return_type"] == "void" and not unset and not declared_void:
                # A leftover nobody reads (callee result or scratch, all readers checked).
                through, through_exits = _exits_pass_through(ctx, address)
                ignored, site_count = _callers_ignore_v0(ctx, address, rules=rules)
                if through and ignored and site_count and not (ctx.addr_taken.get(address) or ctx.word32.get(address)):
                    unset, exits = True, through_exits
                elif slot_void:
                    # The slot family's verdict covers every member's exits and direct callers.
                    unset, exits, by_slot = True, through_exits, True
            if stage2_prototype["return_type"] != "void" or unset or declared_void:
                return {
                    **base,
                    "draft_rule": "P-slot-void" if by_slot else "P-stage2",
                    "prototype": {
                        "return_type": stage2_prototype["return_type"],
                        "parameters": _stage2_parameters(stage2_prototype, params),
                        "evidence": [
                            f"stage 2 prototype from DWARF (receiver {stage2.get('receiver') or 'none'}) restated",
                            "argument registers read on any path: "
                            + (", ".join(f"{r}@{_sites(s)}" for r, s in reads.items()) or "none")
                            + "; all declared",
                        ]
                        + (
                            ["the DWARF record declares an explicit void return (FT_void): a value left in v0/f0 is residue"]
                            if declared_void else
                            [f"every exit leaves v0 and f0 unset or a callee's result or scratch value ({len(exits)} exits)",
                             _slot_evidence(ctx, address, rules)]
                            if by_slot else
                            [f"every exit leaves v0 and f0 unset or an unread leftover ({len(exits)} exits)"]
                            if stage2_prototype["return_type"] == "void" else []
                        ),
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
    if (
        not planner and (parsed or {}).get("name") == "__dt" and receiver_type and not params
        and not _uses_vu0(ctx, address)
    ):
        dtor = _destructor_evidence(ctx, address)
        if dtor:
            return {
                **base,
                "draft_rule": "P-dtor",
                "prototype": {
                    "return_type": "void *",
                    "parameters": [
                        {"name": "this", "type": f"{receiver_type} *"},
                        {"name": "__dtor_flags", "type": "short"},
                    ],
                    "evidence": dtor,
                },
            }
    if planner or special:
        return {**open_row, "open_reason": 'a parameter needs a planner (function pointer, unknown modifier, NAME@hash or case-variant class) or a constructor/destructor'}

    # P-void
    if _uses_vu0(ctx, address):
        return {**open_row, "open_reason": 'VU0 instructions: register contracts need a planner'}
    if _dwarf_returns(ctx).get(address) in ("gpr", "float", "other"):
        # A declared non-void return (a struct may come back through a hidden a0
        # and leave v0 untouched) is never void, whatever the exits show.
        return {**open_row, "open_reason": 'DWARF declares a non-void return (possibly a struct returned through a hidden pointer)'}
    sinit = live_name.startswith("__sinit_") and not parsed
    slot_void = slot_void and not sinit
    unset, exits = _exits_unset(ctx, address)
    pass_through = by_slot = False
    if not unset and not sinit:
        through, exits_through = _exits_pass_through(ctx, address)
        ignored, site_count = _callers_ignore_v0(ctx, address, rules=rules)
        if through and ignored and (site_count or _declared_void(ctx, address, rules, families=False)):
            unset, exits, pass_through = True, exits_through, True
        elif slot_void:
            # The slot family's verdict covers every member's exits and direct callers.
            unset, exits, pass_through, by_slot = True, exits_through, True, True
    if sinit:
        # A static initializer's type is fixed by the runtime, not by its body:
        # __initialize_cpp_rts calls each through the void (**)(void) .p__sinit
        # table and never reads v0, so a callee result left in v0 is residue.
        # The exit form does not matter (tail-jump exits too, review of group 125).
        unset = bool(exits) and all(row.startswith(("jr ra@", "tail j@")) for row in exits) and not call_sites(ctx, address)
    if not unset:
        return {**open_row, "open_reason": 'return: v0/f0 hold a value at some exit (own value, or a callee result that some code may read)'}
    slots = [ctx.object_for(site) or f"0x{site:x}" for site in ctx.word32.get(address, ())]
    if sinit:
        if not slots or any(not str(slot).startswith(".p__sinit") for slot in slots):
            return {**open_row, "open_reason": 'static initializer referenced other than by its .p__sinit word'}
        slots = []
    if (slots or ctx.addr_taken.get(address)) and not _declared_void(ctx, address, rules, families=False):
        if not slot_void:
            return {**open_row, "open_reason": 'address taken or stored in a table: an override or callback contract may apply'}
        by_slot = True
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
        elif slot_void and (proof := _slot_receiver(ctx, address)):
            receiver_evidence, by_slot = proof, True
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
        (f"every exit leaves v0 and f0 unset or a callee's result or scratch value ({len(exits)} exits); "
         "the slot family's verdict covers the direct callers" if pass_through and by_slot else
         f"every exit leaves v0 and f0 unset or holding a callee's result ({len(exits)} exits) and all "
         f"{len(call_sites(ctx, address))} direct call sites leave v0 unread (callee-result pass-through, "
         "or scratch value decisions of 2026-10-20)" if pass_through else
         f"every exit leaves v0 and f0 unset ({len(exits)} jr ra)" if not sinit else
         f"static initializer: {len(exits)} exit(s), no direct call sites; the runtime calls it through the "
         "void (**)(void) .p__sinit table (__initialize_cpp_rts) and never reads v0"),
        _slot_evidence(ctx, address, rules) if by_slot else
        "no word refs or address-taken sites" if not live_name.startswith("__sinit_")
        else "referenced only by its own .p__sinit table word",
    ]
    if receiver_evidence:
        evidence.insert(1, receiver_evidence)
    return {**base, "draft_rule": "P-slot-void" if by_slot else "P-void",
            "prototype": {"return_type": "void", "parameters": parameters, "evidence": evidence}}


def draft_plan(
    root: Path, tracker: dict[str, Any], item_id: str, bridge_url: str | None = None, rules: int = DRAFT_RULES_VERSION
) -> dict[str, Any]:
    from .ghidra import GhidraBridge, _function_index, _type_index

    if rules not in RULES_VERSIONS:
        raise SocomError(f"draft rules version {rules} is not one of {', '.join(map(str, RULES_VERSIONS))}")
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
        functions.append(draft_function(ctx, row, name, types, rules))
    decided = [row for row in functions if row.get("draft_rule")]
    return {
        "kind": RECON_PLAN_KIND,
        "schema_version": RECON_SCHEMA,
        "work_item_id": item_id,
        "group_sha256": evidence["group_sha256"],
        "target": {"source_sha256": REFERENCE_SHA256},
        "draft": {
            "rules_version": rules,
            "decided": len(decided),
            "open": [row["address"] for row in functions if not row.get("draft_rule")],
        },
        "functions": functions,
        "globals": [],
    }


def check_rules_version(plan: dict[str, Any]) -> int:
    """The rules version `recon draft --check` uses for a plan when none is given.

    A plan keeps the rules it was drafted under (its ``draft.rules_version``).
    Plans drafted before version 19, or with no draft block, are checked under
    version 18, the version every accepted plan was last validated with; a
    row that version 19 would decide differently stays as accepted, and
    ``--rules 19`` shows the new decision.
    """

    recorded = (plan.get("draft") or {}).get("rules_version")
    if isinstance(recorded, int) and not isinstance(recorded, bool) and recorded in RULES_VERSIONS and recorded >= CONTRACT_RULES:
        return recorded
    return SLOT_VOID_RULES


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
        elif (planned.get("prototype") or {}).get("partial") is True:
            # A partial row leaves the return unresolved, so it may replace an
            # unresolved draft (U-type, U-vararg), never a decided prototype.
            # Open rows (the rules decided nothing) are not in `fresh`: a partial
            # row is accepted there too, its proof checked by recon validate.
            if _decision(row) != "unresolved":
                problems.append(
                    f"{address}: partial row where the rules decide a complete prototype ({row['draft_rule']}); "
                    "use the drafted row"
                )
        elif row["draft_rule"] == "U-vararg" and (planned.get("prototype") or {}).get("varargs") is True:
            # A complete varargs row whose return the planner decided (decision
            # of 2026-10-22: a void verdict or a proven width) replaces U-vararg.
            pass
        elif _decision(planned) != _decision(row) and _decision(planned) != "unresolved":
            problems.append(
                f"{address}: hand-written row disagrees with its {row['draft_rule']} draft "
                f"({_decision(planned)} vs {_decision(row)})"
            )
    for address, row in rows.items():
        if row.get("draft_rule") and address not in fresh:
            problems.append(f"{address}: claims {row['draft_rule']} but the rules leave it open")
    return problems


_SLOT_VOID_VERDICT = (
    "VERDICT void: its vtable slot family is void (rules version 18): an override's own exits leave "
    "v0 and f0 unset and no override writes a value a caller reads"
)


def void_verdict(ctx: Any, start: int, rules: int = DRAFT_RULES_VERSION) -> str:
    """Why the void rules do or do not let a function be void: exits, then callers.

    Prints the first blocking exit value or reader, with the caller chain that
    leads to it, so a planner or reviewer need not walk the callers by hand.
    From rules version 18 a function stored in vtables also gets its slot
    family's verdict: the family, the override whose body proves void, and
    each blocking override with its reader.  ``rules=17`` and ``rules=18``
    print the earlier verdicts.
    """

    if rules not in RULES_VERSIONS:
        raise SocomError(f"void rules version {rules} is not one of {', '.join(map(str, RULES_VERSIONS))}")
    if start not in ctx.size:
        return f"## 0x{start:x}: not the start of a sized FUNC symbol"
    label = ctx.label(start)
    lines = [f"## {label}"]
    declared = _dwarf_returns(ctx).get(start)
    if declared in ("gpr", "float", "other"):
        lines.append(
            f"VERDICT open: the DWARF record declares a non-void return ({declared}; a struct may be "
            "returned through a hidden a0 and leave v0 untouched)"
        )
        return "\n".join(lines)
    family = slot_family_verdict(ctx, start, rules) if rules >= SLOT_VOID_RULES else None
    family_lines = slot_family_lines(ctx, family) if family else []
    unset, rows = _exits_unset(ctx, start)
    if unset:
        lines.append("exits: v0 and f0 unset at every exit -> void needs no caller check")
        lines.extend(family_lines)
        if family and family["void"]:
            lines.append(_SLOT_VOID_VERDICT)
        return "\n".join(lines)
    dead, rows = _exits_pass_through(ctx, start)
    lines.extend(f"exit {row}" for row in rows)
    lines.extend(family_lines)
    if family and family["void"]:
        # The family verdict checked every member's exits and direct callers.
        lines.append(_SLOT_VOID_VERDICT)
        return "\n".join(lines)
    if not rows:
        lines.append(
            "VERDICT open: the function has no exit (it never returns), so no return value is observable; "
            "a return type needs a declaration"
        )
        return "\n".join(lines)
    if not dead:
        lines.append(
            "VERDICT open: some exit can return a value that is neither a callee's result nor a "
            "scratch value with another use in the function (or an indirect jump)"
        )
        return "\n".join(lines)
    if (ctx.addr_taken.get(start) or ctx.word32.get(start)) and not _declared_void(ctx, start, rules):
        lines.append("VERDICT open: the function's address is taken or stored in a table")
        return "\n".join(lines)

    first = [
        (fpr, name)
        for fpr, register, name in ((False, 2, "v0"), (True, 0, "f0"))
        if callee_preserves(ctx, start, register, fpr) != "all"
    ]
    blocker = _first_reader(ctx, start, first, rules)
    sites = len(call_sites(ctx, start))
    if blocker:
        lines.append(f"VERDICT open: {blocker}")
    elif not sites and _declared_void(ctx, start, rules):
        lines.append("VERDICT void: no direct call sites; only called through a contract (callback type or vtable slot) declared void")
    elif not sites:
        lines.append("VERDICT open: no direct call sites (pass-through needs at least one)")
    else:
        lines.append(f"VERDICT void: {sites} direct call sites; no code reads the leftover")
    return "\n".join(lines)
