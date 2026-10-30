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
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

GPR_SLOT = 8
_COMPOSITES = frozenset(("class_type", "structure_type", "union_type"))
_SHAPES: dict[int, dict[str, frozenset[tuple[str, int]]]] = {}
_HASHED = re.compile(r"@[0-9a-fA-F]+$")


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


def by_value_parameters(ctx: Any, prototype: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The prototype's parameters that ``by_value_problem`` refuses: {position, name, type, problem}."""

    found = []
    for position, param in enumerate((prototype or {}).get("parameters") or [], 1):
        if not isinstance(param, dict):
            continue
        problem = by_value_problem(ctx, param.get("type"))
        if problem:
            found.append({"position": position, "name": param.get("name"), "type": param.get("type"), "problem": problem})
    return found


def by_value_rows(root: Path, tracker: dict[str, Any]) -> dict[str, Any]:
    """Rows of accepted or applied group and repair plans that declare such a parameter.

    A row whose plan is accepted or whose apply is accepted or awaiting
    acceptance is listed; ``live`` marks the row the accepted applies left in
    Ghidra (the newest accepted repair's row over its group's, as
    ``recon contradictions`` reads them).  Each needs a later fix: such a plan
    no longer validates, and an applied row has the wrong storage live.
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
            parameters = by_value_parameters(ctx, row.get("prototype"))
            if not parameters or row.get("keep") is True:
                continue
            address = int(str(row["address"]), 16)
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
    return {
        "kind": "socom-recon-by-value-rows",
        "mutation_performed": False,
        "revision": tracker.get("revision"),
        "gpr_slot_bytes": GPR_SLOT,
        "plans_read": plans,
        "row_count": len(found),
        "live_count": sum(1 for row in found if row["live"]),
        "addresses": sorted({row["address"] for row in found}, key=lambda value: int(value, 16)),
        "rows": found,
    }
