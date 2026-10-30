"""By-value class parameters that Ghidra's storage cannot express (read-only).

Metrowerks passes a class, struct or union argument by value in a GPR while
it fits one: ``C2DBitmapPoly::SetCenterPos(PNT2D, float, float)`` takes the
8-byte PNT2D in a1 (``sd a1,56(sp)`` at 0x2fe4d0, then ``lwc1`` of x and y).
A larger aggregate travels as its address: ``0x2392d0`` takes the 16-byte
CPnt4D by value as ``lwc1 0..12(a1)``, its caller passing ``addiu a1,s1,32``.
Ghidra's r5900 ``__stdcall`` gives the integer argument registers
``maxsize="8"`` and puts a by-value aggregate over 8 bytes on the stack, so a
prototype with such a parameter applies the wrong storage silently.  Stage 2
skips every by-value aggregate; ``recon draft`` (rules version 20) leaves
such rows unresolved (U-byvalue) and ``recon validate`` refuses them.

Sizes come from the DWARF class, struct and union records of the spelled name
(a Ghidra ``NAME@hash`` copy is looked up by NAME); enumerations are scalars.
The drafter also takes the live type's size when it reads one over 8 bytes.

Fitting one GPR is not enough (review of repair 017, 2026-10-30): a class
whose copy is not trivial travels as the address of a caller temporary
whatever its size.  ``HandleFollowTickHideCheck(bool, bool, CAiMapLoc,
void *)`` gets the 4-byte CAiMapLoc (user copy constructor
``__ct__9CAiMapLocFRC9CAiMapLoc``) as ``addiu a3,sp,568``; MSL's
``list::iterator`` (``generic_iterator<0>``, whose converting constructor is
its copy constructor) arrives as ``addiu a1,sp,N`` and is read through
``lw v1,0(a1)`` (0x1d8470), while ``const_iterator`` (``<1>``, implicit copy)
arrives as ``lw a1,N(sp)`` and is spilled with ``sw a1,12(sp)`` (0x197190);
PNT2D (no constructor) and ``vector<bool>::iterator`` arrive as ``ld``
values.  Triviality is not in the ELF (both iterators have copy-constructor
symbols), so the guard reads the callers: a by-value parameter that any
direct caller sets to an address in its own frame (``addiu rN,sp|fp,imm``)
is refused like a large aggregate.  A function without direct callers keeps
the size rule.

Ghidra's r5900 ``__stdcall`` (no ``<rule>`` groups) also gives a ninth float
the next free a0-t3 GPR, where Metrowerks puts it on the stack after the
other overflowing arguments (8-byte slots from +0: ``collideCylinders``,
0x254d90, reads its floats 9-13 at +0x0..+0x20).  ``storage_problems``
compares the two assignments parameter by parameter.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

GPR_SLOT = 8
ARGUMENT_SLOTS = 8  # a0-t3, and f12-f19
_COMPOSITES = frozenset(("class_type", "structure_type", "union_type"))
_SHAPES: dict[int, dict[str, frozenset[tuple[str, int]]]] = {}
_HASHED = re.compile(r"@[0-9a-fA-F]+$")
_GPR_NAMES = ("a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3")
# Scalar spellings (C, Ghidra and the bridge's): never an aggregate.
_SCALARS = frozenset((
    "void", "bool", "char", "schar", "uchar", "signed char", "unsigned char", "short", "ushort", "unsigned short",
    "int", "uint", "unsigned int", "long", "ulong", "unsigned long", "longlong", "ulonglong", "long long",
    "unsigned long long", "float", "double", "wchar_t", "byte", "word", "dword", "qword", "sbyte", "sword",
    "sdword", "sqword", "undefined", "undefined1", "undefined2", "undefined4", "undefined8", "pointer",
    "size_t", "int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64",
))


def dwarf_type_shapes(ctx: Any) -> dict[str, frozenset[tuple[str, int]]]:
    """DWARF type name -> {("composite" | "enum", byte_size)} over every complete record of that name."""

    key = id(ctx)
    if key not in _SHAPES:
        from .recon_facts import _dies_cached

        found: dict[str, set[tuple[str, int]]] = {}
        path = Path(ctx.elf.path) if hasattr(ctx.elf, "path") else None
        if path is not None:
            st = path.stat()
            for die in _dies_cached((str(path), st.st_size, int(st.st_mtime)), str(path)):
                name = die.string("name")
                size = die.integer("byte_size")
                if not name or size is None:
                    continue
                if die.tag_name in _COMPOSITES:
                    found.setdefault(name, set()).add(("composite", size))
                elif die.tag_name == "enumeration_type":
                    found.setdefault(name, set()).add(("enum", size))
        _SHAPES[key] = {name: frozenset(shapes) for name, shapes in found.items()}
    return _SHAPES[key]


def by_value_problem(ctx: Any, type_name: Any, live_size: Any = None) -> str | None:
    """Why a parameter spelled ``type_name`` is an aggregate by value over one GPR slot, or None."""

    if not isinstance(type_name, str):
        return None
    spelled = type_name.strip()
    if "*" in spelled or "[" in spelled:
        return None
    base = _HASHED.sub("", spelled)
    shapes = dwarf_type_shapes(ctx).get(base) or dwarf_type_shapes(ctx).get(base.split("::")[-1]) or frozenset()
    sizes = sorted(size for kind, size in shapes if kind == "composite" and size > GPR_SLOT)
    if sizes:
        size_text = f"{sizes[-1]} bytes" if sizes[0] == sizes[-1] else f"{sizes[0]}-{sizes[-1]} bytes"
        source = f"its DWARF class/struct records are {size_text}"
    elif isinstance(live_size, int) and not isinstance(live_size, bool) and live_size > GPR_SLOT:
        source = f"the live type is {live_size} bytes"
    else:
        return None
    return (
        f"{spelled} is passed by value and {source}: Metrowerks passes an aggregate over {GPR_SLOT} bytes (one GPR "
        "slot) as its address in a GPR, while Ghidra's r5900 __stdcall puts it on the stack, so no prototype can "
        "give it its storage"
    )


def maybe_aggregate(ctx: Any, type_name: Any) -> bool:
    """A by-value parameter type DWARF records only as a class, struct or union of that name.

    Names DWARF does not record as composites (typedefs such as
    ``__gnuc_va_list``, whose value is itself a stack address) are not checked.
    Names are unqualified in DWARF 1, so a qualified spelling is looked up by
    its last component, and a template instance by its template name.
    """

    if not isinstance(type_name, str):
        return False
    spelled = type_name.strip()
    if not spelled or "*" in spelled or "[" in spelled or "&" in spelled:
        return False
    base = _HASHED.sub("", spelled)
    if base in _SCALARS or base.split("::")[-1] in _SCALARS:
        return False
    last = base.split("::")[-1]
    # DWARF names a template instance without its arguments (generic_iterator<0> is generic_iterator).
    shapes = (
        dwarf_type_shapes(ctx).get(base) or dwarf_type_shapes(ctx).get(last)
        or dwarf_type_shapes(ctx).get(last.split("<")[0]) or frozenset()
    )
    # A name DWARF also records as an enumeration (CAiMap::DIR and dirent's DIR) is not decided.
    return bool(shapes) and all(kind == "composite" for kind, _size in shapes)


def address_passing(ctx: Any, function: int, register: int) -> str | None:
    """A direct caller of ``function`` that sets ``register`` to an address in its own frame, as text, or None.

    ``addiu rN,sp,imm`` (or ``fp``) entering the call is the address of a
    caller temporary: the by-value argument travels as its address.
    """

    from .recon_facts import call_sites

    if function not in ctx.size:
        return None
    for caller, site, _kind in call_sites(ctx, function):
        flow = ctx.flow(caller)
        for definition in sorted(flow.entering_callee(site + 4, register), key=str):
            if not isinstance(definition, int):
                continue
            insn = ctx.code.word(definition)
            op, rs, rt = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31
            if op in (0x09, 0x19) and rt == register and rs in (29, 30):
                return (
                    f"its caller {ctx.label(caller)} passes the address of a stack temporary "
                    f"({ctx.text(definition)}@0x{definition:x} for the call at 0x{site:x})"
                )
    return None


def _small_by_address_problem(ctx: Any, type_name: str, function: int, register: int) -> str | None:
    why = address_passing(ctx, function, register)
    if why is None:
        return None
    return (
        f"{type_name.strip()} is passed by value but {why}: Metrowerks passes a class whose copy is not trivial as "
        f"the address of a temporary whatever its size, while a prototype gives {_GPR_NAMES[register - 4]} the "
        "value itself, so no prototype can give it its storage"
    )


def storage_problems(prototype: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Parameters Ghidra's r5900 __stdcall stores elsewhere than Metrowerks passes them.

    Metrowerks: floats take f12-f19, every other argument the next of a0-t3;
    an argument left over goes on the stack in 8-byte slots from +0, in
    parameter order.  Ghidra (no ``<rule>`` groups): floats take f12-f19,
    then the next free a0-t3 like every other argument, then the stack (align
    8 from +0).  They part only when a ninth float finds a GPR free.
    """

    found = []
    ghidra_f = ghidra_g = ghidra_stack = mw_f = mw_g = mw_stack = 0
    for position, param in enumerate((prototype or {}).get("parameters") or [], 1):
        if not isinstance(param, dict):
            continue
        is_float = isinstance(param.get("type"), str) and param["type"].strip() == "float"
        if is_float and ghidra_f < ARGUMENT_SLOTS:
            ghidra, ghidra_f = f"f{12 + ghidra_f}", ghidra_f + 1
        elif ghidra_g < ARGUMENT_SLOTS:
            ghidra, ghidra_g = _GPR_NAMES[ghidra_g], ghidra_g + 1
        else:
            ghidra, ghidra_stack = f"stack+0x{ghidra_stack:x}", ghidra_stack + 8
        if is_float and mw_f < ARGUMENT_SLOTS:
            metrowerks, mw_f = f"f{12 + mw_f}", mw_f + 1
        elif not is_float and mw_g < ARGUMENT_SLOTS:
            metrowerks, mw_g = _GPR_NAMES[mw_g], mw_g + 1
        else:
            metrowerks, mw_stack = f"stack+0x{mw_stack:x}", mw_stack + 8
        if ghidra != metrowerks:
            found.append({
                "position": position, "name": param.get("name"), "type": param.get("type"), "kind": "storage",
                "problem": (
                    f"Metrowerks passes it in {metrowerks}, but Ghidra's r5900 __stdcall would store it in {ghidra} "
                    f"(a float after f12-f19 takes the next free a0-t3 there; Metrowerks puts floats 9+ on the "
                    "stack), so no prototype can give it its storage"
                ),
            })
    return found


def by_value_parameters(ctx: Any, prototype: dict[str, Any] | None, function: int | None = None) -> list[dict[str, Any]]:
    """The prototype's parameters no Ghidra prototype can store: {position, name, type, kind, problem}.

    ``kind`` is ``over-gpr`` (an aggregate over 8 bytes), ``by-address`` (a
    by-value parameter a direct caller of ``function`` passes as the address
    of a temporary) or ``storage`` (``storage_problems``).
    """

    found = []
    gpr = 0
    for position, param in enumerate((prototype or {}).get("parameters") or [], 1):
        if not isinstance(param, dict):
            continue
        type_name = param.get("type")
        is_float = isinstance(type_name, str) and type_name.strip() == "float"
        register = None if is_float or gpr >= ARGUMENT_SLOTS else 4 + gpr
        gpr += 0 if is_float else 1
        problem = by_value_problem(ctx, type_name)
        kind = "over-gpr"
        if problem is None and function is not None and register is not None and maybe_aggregate(ctx, type_name):
            problem, kind = _small_by_address_problem(ctx, type_name, function, register), "by-address"
        if problem:
            found.append({"position": position, "name": param.get("name"), "type": type_name, "kind": kind, "problem": problem})
    found.extend(storage_problems(prototype))
    return sorted(found, key=lambda row: row["position"])


def by_value_rows(root: Path, tracker: dict[str, Any]) -> dict[str, Any]:
    """Rows of accepted or applied group and repair plans that declare such a parameter.

    A row whose plan is accepted or whose apply is accepted or awaiting
    acceptance is listed; ``live`` marks the row the accepted applies left in
    Ghidra (the newest accepted repair's row over its group's, as
    ``recon contradictions`` reads them).  Each needs a later fix: such a plan
    no longer validates, and an applied row has the wrong storage live.
    Each parameter carries its ``kind`` (``by_value_parameters``).
    """

    from .recon import REPAIR_PLAN_KIND, plan_path_for
    from .recon_facts import context
    from .recon_withdraw import applied_rows
    from .util import load_json

    ctx = context(root)
    items = {row["id"]: row for row in tracker["work_items"]}
    effective = {address: info["source"] for address, info in applied_rows(root, tracker).items()}
    found = []
    plans = 0
    for item in tracker["work_items"]:
        if item.get("kind") not in ("recon-plan-group", REPAIR_PLAN_KIND):
            continue
        apply = items.get(f"{item['id']}-apply") or {}
        accepted = item.get("status") == "accepted"
        applied = apply.get("status") in ("accepted", "awaiting_acceptance")
        if not (accepted or applied):
            continue
        path = plan_path_for(root, item["id"])
        if not path.is_file():
            continue
        plans += 1
        for row in load_json(path).get("functions", []):
            address = int(str(row["address"]), 16)
            parameters = by_value_parameters(ctx, row.get("prototype"), address)
            if not parameters or row.get("keep") is True:
                continue
            found.append({
                "address": f"0x{address:x}",
                "name": row.get("current_name"),
                "item": item["id"],
                "kind": "repair" if item["kind"] == REPAIR_PLAN_KIND else "group",
                "plan_status": item.get("status"),
                "apply_status": apply.get("status"),
                "live": effective.get(address) == item["id"],
                "draft_rule": row.get("draft_rule"),
                "partial": (row.get("prototype") or {}).get("partial") is True,
                "parameters": parameters,
            })
    found.sort(key=lambda row: (int(row["address"], 16), row["item"]))
    kinds: dict[str, int] = {}
    for row in found:
        for kind in sorted({parameter["kind"] for parameter in row["parameters"]}):
            kinds[kind] = kinds.get(kind, 0) + 1
    return {
        "kind": "socom-recon-by-value-rows",
        "mutation_performed": False,
        "revision": tracker.get("revision"),
        "gpr_slot_bytes": GPR_SLOT,
        "plans_read": plans,
        "row_count": len(found),
        "rows_by_kind": dict(sorted(kinds.items())),
        "live_count": sum(1 for row in found if row["live"]),
        "addresses": sorted({row["address"] for row in found}, key=lambda value: int(value, 16)),
        "rows": found,
    }
