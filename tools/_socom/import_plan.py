"""Build deterministic, non-mutating Ghidra import plans."""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Any

from .constants import REFERENCE_SHA256
from .dwarf1 import Dwarf1Debug, Die, TYPE_TAGS
from .elf import Elf32File
from .mwdemangle import split_qualified
from .type_identity import (
    TypeIdentities,
    ghidra_path,
    parse_subscr,
    type_descriptor,
    type_ref,
)
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


def _array_descriptor(die: Die) -> dict[str, Any] | None:
    if die.tag_name != "array_type":
        return None
    subscript = die.attribute("subscr_data")
    dims, element = parse_subscr(
        subscript.value if subscript and isinstance(subscript.value, bytes) else b""
    )
    return {
        "dimensions": [list(dimension) for dimension in dims],
        "element": type_descriptor(element),
    }


def _type_rows(
    dies: tuple[Die, ...],
    parents: dict[int, int],
    by_offset: dict[int, Die],
    identities: TypeIdentities,
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
        resolved = identities.die_identity(die.offset)
        if resolved is not None:
            # Metrowerks DWARF 1 drops namespaces, enclosing classes, and
            # template arguments; the evidence-backed identity restores them.
            if resolved["resolution"].startswith("provisional"):
                scope_path = scope["scope_path"]
            else:
                scope_path = split_qualified(resolved["qualified_name"])[:-1]
            scope.update(
                {
                    "qualified_name": resolved["qualified_name"],
                    "identity": resolved["qualified_name"],
                    "scope_path": scope_path,
                }
            )
            identity_fields = {
                "ghidra_path": resolved["ghidra_path"],
                "identity_resolution": resolved["resolution"],
                "declaration": resolved["declaration"],
            }
        elif scope["anonymous"]:
            identity_fields = {
                "ghidra_path": None,
                "identity_resolution": "anonymous",
                "declaration": False,
            }
        else:
            identity_fields = {
                "ghidra_path": ghidra_path(scope["qualified_name"]),
                "identity_resolution": "dwarf-name",
                "declaration": False,
            }
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
                "type": type_descriptor(type_ref(child)),
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
                **identity_fields,
                "structural_class": identities.structural_class[die.offset],
                "kind": die.tag_name,
                "byte_size": die.integer("byte_size"),
                "type": type_descriptor(type_ref(die)),
                "array": _array_descriptor(die),
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
                "type": type_descriptor(type_ref(child)),
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
                "type": type_descriptor(type_ref(child)),
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
                "return_type": type_descriptor(type_ref(die)),
                "parameters": parameters,
                "locals": locals_,
                "evidence": _die_evidence(die),
            }
        )
    return result


def _conflicts(
    types: list[dict[str, Any]], identities: TypeIdentities
) -> list[dict[str, Any]]:
    """Distinct structures that share one qualified identity."""

    by_class: dict[str, list[str]] = collections.defaultdict(list)
    for row in types:
        by_class[row["structural_class"]].append(row["id"])
    conflicts = []
    for conflict in identities.conflicts:
        conflicts.append(
            {
                **conflict,
                "id": stable_id(
                    "import-conflict", conflict["qualified_name"], conflict["reason"]
                ),
                "type_plan_ids": [
                    row_id
                    for key in conflict["structural_classes"]
                    for row_id in by_class.get(key, [])
                ],
                "status": "blocking",
            }
        )
    dwarf_named: dict[str, set[str]] = collections.defaultdict(set)
    rows_by_name: dict[str, list[str]] = collections.defaultdict(list)
    for row in types:
        if row["identity_resolution"] == "dwarf-name":
            dwarf_named[str(row["qualified_name"])].add(row["structural_class"])
            rows_by_name[str(row["qualified_name"])].append(row["id"])
    for name, keys in dwarf_named.items():
        if len(keys) > 1:
            conflicts.append(
                {
                    "id": stable_id("import-conflict", name),
                    "qualified_name": name,
                    "reason": "incompatible DWARF definitions",
                    "structural_classes": sorted(keys),
                    "type_plan_ids": rows_by_name[name],
                    "status": "blocking",
                }
            )
    return sorted(
        conflicts,
        key=lambda row: (row["qualified_name"].casefold(), row["qualified_name"], row["reason"]),
    )


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
    identities = TypeIdentities(elf, dies, parents)
    types = _type_rows(selected, parents, by_offset, identities)
    types_only = (batch or {}).get("selection") == "types"
    functions = [] if types_only else _function_rows(selected, parents, by_offset)
    variables = [] if types_only else [
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
            "type": type_descriptor(type_ref(die)),
            "location": _attribute_value(
                die.attribute("location").value if die.attribute("location") else None
            ),
            "evidence": _die_evidence(die),
        }
        for die in selected
        if die.tag in VARIABLE_TAGS and die.string("name")
    ]
    conflicts = _conflicts(types, identities)
    selected_classes = {row["structural_class"] for row in types}
    identity_rows = [
        identity
        for identity in identities.identities
        if identity["structural_class"] in selected_classes
    ]
    receipt_scope = {
        "schema_version": 1,
        "functions": sorted(
            {f"0x{row['low_pc']:x}" for row in functions if row.get("low_pc")}
        ),
        "types": sorted(
            {str(row["ghidra_path"]) for row in types if row.get("ghidra_path")},
            # Exact spelling breaks casefold ties (LINE_DATA vs line_data).
            key=lambda path: (path.casefold(), path),
        ),
        "globals": [],
    }
    return {
        "schema_version": 4,
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
        "identities": identity_rows,
        "types": types,
        "functions": functions,
        "variables": variables,
        "conflicts": conflicts,
        "summary": {
            "type_count": len(types),
            "function_count": len(functions),
            "variable_count": len(variables),
            "blocking_conflict_count": len(conflicts),
            "structural_class_count": len(selected_classes),
            "identity_resolution_counts": dict(
                sorted(
                    collections.Counter(
                        identity["resolution"] for identity in identity_rows
                    ).items()
                )
            ),
            "provisional_identity_count": sum(
                1 for identity in identity_rows if identity["resolution"] == "provisional"
            ),
        },
    }
