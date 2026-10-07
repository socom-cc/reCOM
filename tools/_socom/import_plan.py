"""Build deterministic, non-mutating Ghidra import plans."""

from __future__ import annotations

import collections
from pathlib import Path
from typing import Any

from .constants import REFERENCE_SHA256
from .dwarf1 import Dwarf1Debug, Die, TYPE_TAGS
from .elf import Elf32File
from .mwdemangle import demangle, readable_qualified, split_qualified
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

MIPS_GPR_NAMES = (
    "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
    "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
    "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
    "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra",
)
# DWARF 1 location atoms: REG, BASEREG, ADDR, CONST carry a 4-byte operand.
_LOCATION_OPERAND_ATOMS = {0x01: "reg", 0x02: "basereg", 0x03: "addr", 0x04: "const"}
_LOCATION_PLAIN_ATOMS = {0x05: "deref2", 0x06: "deref4", 0x07: "add"}


def _register(number: int) -> dict[str, Any]:
    name = MIPS_GPR_NAMES[number] if 0 <= number < len(MIPS_GPR_NAMES) else None
    return {"register": number, "register_name": name}


def decode_location(value: Any) -> dict[str, Any] | None:
    """Decode a DWARF 1 location block into register, frame, or address form."""

    if value is None:
        return None
    block = bytes.fromhex(value) if isinstance(value, str) else bytes(value)
    atoms: list[tuple[str, int | None]] = []
    index = 0
    while index < len(block):
        op = block[index]
        index += 1
        if op in _LOCATION_OPERAND_ATOMS:
            if index + 4 > len(block):
                return {"kind": "invalid", "raw": block.hex()}
            operand = int.from_bytes(block[index : index + 4], "little", signed=op == 0x04)
            index += 4
            atoms.append((_LOCATION_OPERAND_ATOMS[op], operand))
        elif op in _LOCATION_PLAIN_ATOMS:
            atoms.append((_LOCATION_PLAIN_ATOMS[op], None))
        else:
            return {"kind": "invalid", "raw": block.hex()}
    if len(atoms) == 1 and atoms[0][0] == "reg":
        return {"kind": "register", **_register(int(atoms[0][1]))}
    if len(atoms) == 1 and atoms[0][0] == "addr":
        return {"kind": "address", "address": int(atoms[0][1])}
    if [atom[0] for atom in atoms] == ["basereg", "const", "add"]:
        return {"kind": "frame", **_register(int(atoms[0][1])), "offset": int(atoms[1][1])}
    return {"kind": "expression", "atoms": [list(atom) for atom in atoms]}


def _symbol_index(elf: Elf32File) -> dict[int, list[str]]:
    names: dict[int, set[str]] = collections.defaultdict(set)
    for symbol in elf.symbols():
        if symbol.name and symbol.type_name in ("FUNC", "OBJECT", "NOTYPE") and symbol.value:
            names[symbol.value].add(symbol.name)
    return {address: sorted(values) for address, values in names.items()}


def _placement(elf: Elf32File, address: int) -> dict[str, Any] | None:
    """Locate an address in a PT_LOAD image; zero-fill lies past the file bytes."""

    for segment in elf.load_segments():
        start = segment.virtual_address
        if start <= address < start + segment.memory_size:
            return {
                "segment": segment.index,
                "initialized": address < start + segment.file_size,
            }
    return None


def _symbol_identity(mangled: str | None) -> str | None:
    parsed = demangle(mangled) if mangled else None
    if not parsed:
        return None
    return readable_qualified([*parsed["qualifier"], parsed["name"]])


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


def parameter_storage(parameters: list[dict[str, Any]]) -> str:
    """Classify recorded parameter locations as usable homes or not.

    Two parameters cannot share one register, and v0 cannot carry an incoming
    R5900 argument (`release__15_zmalloc<4four>FPv` reads a0/a1 while DWARF
    records both parameters in v0).
    """

    registers = [
        row["storage"]["register"]
        for row in parameters
        if row["storage"] and row["storage"]["kind"] == "register"
    ]
    if len(registers) != len(set(registers)):
        return "conflicting"
    if 2 in registers:
        return "not-entry-storage"
    return "recorded"


def _storage_row(die: Die, block: list[int] | None = None) -> dict[str, Any]:
    raw = die.attribute("location").value if die.attribute("location") else None
    row = {
        "name": die.string("name"),
        "die_offset": die.offset,
        "type": type_descriptor(type_ref(die)),
        "location": _attribute_value(raw),
        "storage": decode_location(raw),
    }
    if block is not None:
        row["block"] = block
    return row


def _function_rows(
    dies: tuple[Die, ...],
    parents: dict[int, int],
    by_offset: dict[int, Die],
    symbols: dict[int, list[str]],
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
            _storage_row(child)
            for child in children
            if child.tag_name == "formal_parameter"
        ]
        # Metrowerks nests locals in lexical blocks; keep each block's range.
        locals_: list[dict[str, Any]] = []

        def collect(offset: int, block: list[int] | None) -> None:
            for child in by_parent.get(offset, []):
                if child.tag_name == "local_variable":
                    locals_.append(_storage_row(child, block))
                elif child.tag_name == "lexical_block":
                    collect(child.offset, [child.integer("low_pc"), child.integer("high_pc")])

        collect(die.offset, None)
        scope = _scope_identity(die, parents, by_offset)
        mangled = die.string("attr_0x2000")
        low_pc = die.integer("low_pc")
        result.append(
            {
                "id": stable_id("function-plan", die.offset, name or ""),
                "name": name,
                # Metrowerks DWARF 1 drops the enclosing class; the mangled
                # name keeps it.
                "qualified_name": _symbol_identity(mangled) or scope["qualified_name"],
                "dwarf_qualified_name": scope["qualified_name"],
                "mangled_name": mangled,
                "symbols": symbols.get(low_pc, []) if low_pc is not None else [],
                "scope_path": scope["scope_path"],
                "compile_unit_offset": scope["compile_unit_offset"],
                "compile_unit_path": scope["compile_unit_path"],
                "low_pc": low_pc,
                "high_pc": die.integer("high_pc"),
                "return_type": type_descriptor(type_ref(die)),
                "parameters": parameters,
                "parameter_storage": parameter_storage(parameters),
                "locals": locals_,
                "evidence": _die_evidence(die),
            }
        )
    return result


def _in_function(die: Die, parents: dict[int, int], by_offset: dict[int, Die]) -> bool:
    return any(
        by_offset[offset].tag in FUNCTION_TAGS
        for offset in _ancestor_offsets(die, parents, by_offset)
    )


def _function_entries(elf: Elf32File) -> set[int]:
    return {symbol.value for symbol in elf.symbols() if symbol.type_name == "FUNC" and symbol.value}


def _variable_rows(
    elf: Elf32File,
    dies: tuple[Die, ...],
    parents: dict[int, int],
    by_offset: dict[int, Die],
    symbols: dict[int, list[str]],
    function_entries: set[int],
) -> list[dict[str, Any]]:
    """Compile-unit-level variables; function locals stay with their function.

    Metrowerks also emits a global_variable of subroutine type at the entry
    of some compiler-generated member functions (__ct__12C2DOrderItemFv).
    Those describe the function, not data: they are marked function-object
    and never become present globals.
    """

    rows = []
    for die in dies:
        if die.tag not in VARIABLE_TAGS or not die.string("name"):
            continue
        if _in_function(die, parents, by_offset):
            continue
        scope = _scope_identity(die, parents, by_offset)
        raw = die.attribute("location").value if die.attribute("location") else None
        storage = decode_location(raw)
        address = storage["address"] if storage and storage["kind"] == "address" else None
        placement = _placement(elf, address) if address else None
        names = symbols.get(address, []) if address else []
        descriptor = type_descriptor(type_ref(die))
        target = by_offset.get((descriptor or {}).get("die_offset"))
        function_object = bool(
            address in function_entries
            and target is not None
            and target.tag_name == "subroutine_type"
            and not (descriptor or {}).get("modifiers")
        )
        if function_object:
            status = "function-object"
        else:
            # Address 0 or an address outside every PT_LOAD image means
            # the linker did not place this object.
            status = "present" if placement else "absent"
        rows.append(
            {
                "id": stable_id("variable-plan", die.offset, die.string("name") or ""),
                "name": die.string("name"),
                "qualified_name": scope["qualified_name"],
                "symbol_qualified_names": sorted(
                    {value for name in names if (value := _symbol_identity(name))}
                ),
                "scope_path": scope["scope_path"],
                "compile_unit_offset": scope["compile_unit_offset"],
                "compile_unit_path": scope["compile_unit_path"],
                "kind": die.tag_name,
                "type": descriptor,
                "location": _attribute_value(raw),
                "storage": storage,
                "address": address,
                "placement": placement,
                "symbols": names,
                "status": status,
                "evidence": _die_evidence(die),
            }
        )
    return rows


def _referenced_types(
    dies: tuple[Die, ...],
    parents: dict[int, int],
    by_offset: dict[int, Die],
    identities: TypeIdentities,
    selected: set[int],
    descriptors: list[dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Type rows outside the batch that its functions and variables name.

    Metrowerks DWARF 1 references type DIEs in other compile units.  A batch
    apply only spells these types (the foundation defined them), so the plan
    carries each referenced row with its members, following unnamed array
    elements, and marks it referenced_only.
    """

    children: dict[int, list[Die]] = collections.defaultdict(list)
    for die in dies:
        if die.offset in parents:
            children[parents[die.offset]].append(die)
    pending = sorted(
        {
            row["die_offset"]
            for row in descriptors
            if row and row.get("die_offset") is not None and row["die_offset"] not in selected
        }
    )
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    while pending:
        offset = pending.pop(0)
        if offset in seen or offset in selected or offset not in by_offset:
            continue
        seen.add(offset)
        die = by_offset[offset]
        if die.tag not in TYPE_TAGS:
            continue
        group = (die, *children.get(offset, []))
        row = next(
            item
            for item in _type_rows(group, parents, by_offset, identities)
            if item["evidence"]["die_offset"] == offset
        )
        row["referenced_only"] = True
        rows.append(row)
        element = (row.get("array") or {}).get("element") or {}
        if not row.get("ghidra_path") and element.get("die_offset") is not None:
            pending.append(element["die_offset"])
    return sorted(rows, key=lambda row: row["evidence"]["die_offset"])


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
    symbols = {} if types_only else _symbol_index(elf)
    functions = [] if types_only else _function_rows(selected, parents, by_offset, symbols)
    variables = [] if types_only else _variable_rows(
        elf, selected, parents, by_offset, symbols, _function_entries(elf)
    )
    if not types_only:
        descriptors = [
            descriptor
            for row in functions
            for descriptor in (
                row["return_type"],
                *(item["type"] for item in row["parameters"]),
                *(item["type"] for item in row["locals"]),
            )
        ] + [row["type"] for row in variables if row["status"] == "present"]
        types += _referenced_types(
            dies, parents, by_offset, identities, {die.offset for die in selected}, descriptors
        )
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
        "globals": [
            f"0x{address:x}"
            for address in sorted(
                {row["address"] for row in variables if row["status"] == "present"}
            )
        ],
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
