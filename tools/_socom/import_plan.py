"""Build deterministic, non-mutating Ghidra import plans."""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Any

from .constants import REFERENCE_SHA256
from .dwarf1 import Dwarf1Debug, Die, TYPE_TAGS
from .elf import Elf32File
from .util import stable_id

FUNCTION_TAGS = {0x0003, 0x0006, 0x0014, 0x001D}
VARIABLE_TAGS = {0x0007, 0x000C}
COMPOSITE_TAGS = {0x0002, 0x0013, 0x0017}


def _parent_map(dies: tuple[Die, ...]) -> dict[int, int]:
    parents: dict[int, int] = {}
    stack: list[tuple[int, int]] = []
    for die in dies:
        while stack and die.offset >= stack[-1][1]:
            stack.pop()
        if stack:
            parents[die.offset] = stack[-1][0]
        sibling = die.integer("sibling")
        if sibling is not None and sibling > die.offset + die.length:
            stack.append((die.offset, sibling))
    return parents


def _attribute_value(value: Any) -> Any:
    return value.hex() if isinstance(value, bytes) else value


def _die_evidence(die: Die) -> dict[str, Any]:
    return {
        "die_offset": die.offset,
        "tag": die.tag_name,
        "attributes": {
            attribute.name: {
                "form": attribute.form_name,
                "value": _attribute_value(attribute.value),
            }
            for attribute in die.attributes
        },
    }


def _ancestor_offsets(
    die: Die, parents: dict[int, int], by_offset: dict[int, Die]
) -> list[int]:
    result: list[int] = []
    current = parents.get(die.offset)
    seen: set[int] = set()
    while current is not None and current not in seen:
        seen.add(current)
        result.append(current)
        current = parents.get(current)
    result.reverse()
    return result


def _scope_identity(
    die: Die, parents: dict[int, int], by_offset: dict[int, Die]
) -> dict[str, Any]:
    ancestors = _ancestor_offsets(die, parents, by_offset)
    compile_unit = next(
        (by_offset[offset] for offset in ancestors if by_offset[offset].tag_name == "compile_unit"),
        None,
    )
    scope_names = [
        name
        for offset in ancestors
        if by_offset[offset].tag_name != "compile_unit"
        and (name := by_offset[offset].string("name"))
    ]
    raw_name = die.string("name")
    # Metrowerks emits several synthetic spellings (`@anon...`, `@class`,
    # and similar). None is a globally qualified source identity.
    anonymous = not raw_name or raw_name.startswith("@")
    qualified_name = "::".join([*scope_names, raw_name]) if raw_name else None
    if anonymous:
        identity = (
            f"cu@0x{compile_unit.offset:x}" if compile_unit else "cu@unknown"
        ) + f"/parent@0x{parents.get(die.offset, 0):x}/die@0x{die.offset:x}"
    else:
        identity = qualified_name or raw_name
    return {
        "raw_name": raw_name,
        "qualified_name": qualified_name,
        "identity": identity,
        "anonymous": anonymous,
        "scope_path": scope_names,
        "compile_unit_offset": compile_unit.offset if compile_unit else None,
        "compile_unit_path": compile_unit.string("name") if compile_unit else None,
        "parent_die_offset": parents.get(die.offset),
    }


def _type_rows(
    dies: tuple[Die, ...],
    parents: dict[int, int],
    by_offset: dict[int, Die],
) -> list[dict[str, Any]]:
    by_parent: dict[int, list[Die]] = collections.defaultdict(list)
    for die in dies:
        if die.offset in parents:
            by_parent[parents[die.offset]].append(die)

    result = []
    for die in dies:
        if die.tag not in TYPE_TAGS:
            continue
        scope = _scope_identity(die, parents, by_offset)
        name = scope["raw_name"]
        children = by_parent.get(die.offset, [])
        members = [
            {
                "name": child.string("name"),
                "tag": child.tag_name,
                "die_offset": child.offset,
                "byte_size": child.integer("byte_size"),
                "bit_offset": child.integer("bit_offset"),
                "bit_size": child.integer("bit_size"),
                "location": _attribute_value(
                    child.attribute("location").value
                    if child.attribute("location")
                    else None
                ),
                "type_reference": (
                    child.integer("user_def_type")
                    or child.integer("mod_user_def_type")
                    or child.integer("fund_type")
                ),
            }
            for child in children
            if child.tag_name in {"member", "inheritance"}
        ]
        result.append(
            {
                "id": stable_id("type-plan", die.offset, name or die.tag_name),
                "action": (
                    "forward-declare-then-define"
                    if die.tag in COMPOSITE_TAGS
                    else "define"
                ),
                **scope,
                "kind": die.tag_name,
                "byte_size": die.integer("byte_size"),
                "type_reference": (
                    die.integer("user_def_type")
                    or die.integer("mod_user_def_type")
                    or die.integer("fund_type")
                ),
                "members": members,
                "evidence": _die_evidence(die),
            }
        )
    return result


def _function_rows(
    dies: tuple[Die, ...],
    parents: dict[int, int],
    by_offset: dict[int, Die],
) -> list[dict[str, Any]]:
    by_parent: dict[int, list[Die]] = collections.defaultdict(list)
    for die in dies:
        if die.offset in parents:
            by_parent[parents[die.offset]].append(die)
    result = []
    for die in dies:
        if die.tag not in FUNCTION_TAGS:
            continue
        name = die.string("name")
        if not name and die.integer("low_pc") is None:
            continue
        children = by_parent.get(die.offset, [])
        parameters = [
            {
                "name": child.string("name"),
                "die_offset": child.offset,
                "type_reference": (
                    child.integer("user_def_type")
                    or child.integer("mod_user_def_type")
                    or child.integer("fund_type")
                ),
                "location": _attribute_value(
                    child.attribute("location").value
                    if child.attribute("location")
                    else None
                ),
            }
            for child in children
            if child.tag_name == "formal_parameter"
        ]
        locals_ = [
            {
                "name": child.string("name"),
                "die_offset": child.offset,
                "type_reference": (
                    child.integer("user_def_type")
                    or child.integer("mod_user_def_type")
                    or child.integer("fund_type")
                ),
                "location": _attribute_value(
                    child.attribute("location").value
                    if child.attribute("location")
                    else None
                ),
            }
            for child in children
            if child.tag_name == "local_variable"
        ]
        scope = _scope_identity(die, parents, by_offset)
        result.append(
            {
                "id": stable_id("function-plan", die.offset, name or ""),
                "name": name,
                "qualified_name": scope["qualified_name"],
                "scope_path": scope["scope_path"],
                "compile_unit_offset": scope["compile_unit_offset"],
                "compile_unit_path": scope["compile_unit_path"],
                "low_pc": die.integer("low_pc"),
                "high_pc": die.integer("high_pc"),
                "return_type_reference": (
                    die.integer("user_def_type")
                    or die.integer("mod_user_def_type")
                    or die.integer("fund_type")
                ),
                "parameters": parameters,
                "locals": locals_,
                "evidence": _die_evidence(die),
            }
        )
    return result


def _conflicts(types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in types:
        if row["qualified_name"] and not row["anonymous"]:
            grouped[str(row["identity"])].append(row)
    conflicts = []
    for name, rows in sorted(grouped.items(), key=lambda item: item[0].casefold()):
        layouts = {
            (
                row["kind"],
                row["byte_size"],
                tuple(
                    (
                        member["name"],
                        member["byte_size"],
                        member["bit_offset"],
                        member["bit_size"],
                        member["location"],
                    )
                    for member in row["members"]
                ),
            )
            for row in rows
        }
        if len(layouts) > 1:
            conflicts.append(
                {
                    "id": stable_id("import-conflict", name),
                    "qualified_name": name,
                    "reason": "incompatible DWARF definitions",
                    "type_plan_ids": [row["id"] for row in rows],
                    "status": "blocking",
                }
            )
    return conflicts


def build_import_plan(root: Path, batch: dict[str, Any] | None = None) -> dict[str, Any]:
    elf = Elf32File(root / "support" / "socom.elf")
    dies = Dwarf1Debug(elf.section_data(".debug")).parse(strict=True)
    parents = _parent_map(dies)
    by_offset = {die.offset: die for die in dies}
    if batch and batch.get("die_ranges"):
        ranges = [(int(a), int(b)) for a, b in batch["die_ranges"]]
        selected = tuple(
            die for die in dies if any(start <= die.offset < end for start, end in ranges)
        )
    else:
        selected = dies
    types = _type_rows(selected, parents, by_offset)
    functions = _function_rows(selected, parents, by_offset)
    variables = [
        {
            "id": stable_id("variable-plan", die.offset, die.string("name") or ""),
            "name": die.string("name"),
            "qualified_name": _scope_identity(die, parents, by_offset)[
                "qualified_name"
            ],
            "scope_path": _scope_identity(die, parents, by_offset)["scope_path"],
            "compile_unit_offset": _scope_identity(die, parents, by_offset)[
                "compile_unit_offset"
            ],
            "compile_unit_path": _scope_identity(die, parents, by_offset)[
                "compile_unit_path"
            ],
            "kind": die.tag_name,
            "type_reference": (
                die.integer("user_def_type")
                or die.integer("mod_user_def_type")
                or die.integer("fund_type")
            ),
            "location": _attribute_value(
                die.attribute("location").value if die.attribute("location") else None
            ),
            "evidence": _die_evidence(die),
        }
        for die in selected
        if die.tag in VARIABLE_TAGS and die.string("name")
    ]
    conflicts = _conflicts(types)
    receipt_scope = {
        "schema_version": 1,
        "functions": sorted(
            {f"0x{row['low_pc']:x}" for row in functions if row.get("low_pc")}
        ),
        "types": sorted(
            {
                str(row["qualified_name"])
                for row in types
                if row.get("qualified_name") and not row.get("anonymous")
            },
            key=str.casefold,
        ),
        "globals": [],
    }
    return {
        "schema_version": 2,
        "kind": "socom-ghidra-import-plan",
        "mutation_performed": False,
        "target": {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "source_sha256": REFERENCE_SHA256,
            "language": "r5900:LE:32:default",
            "compiler": "default",
        },
        "receipt_scope": receipt_scope,
        "batch": batch,
        "selected_die_count": len(selected),
        "application_order": [
            "forward_declarations",
            "typedefs_and_indirections",
            "composite_definitions",
            "functions",
            "variables_and_locals",
            "reanalyze_and_review",
            "save_program_through_live_handoff",
        ],
        "types": types,
        "functions": functions,
        "variables": variables,
        "conflicts": conflicts,
        "summary": {
            "type_count": len(types),
            "function_count": len(functions),
            "variable_count": len(variables),
            "blocking_conflict_count": len(conflicts),
        },
    }
