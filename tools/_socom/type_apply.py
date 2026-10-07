"""Translate an accepted DWARF type plan into Ghidra bridge operations.

The plan stores raw Metrowerks DWARF 1 facts.  The GhidraMCP bridge that
applies them resolves data types by bare name only, cannot place bitfields at
explicit positions, drops component names when it retypes a component, and
clears data applications when it deletes a type.  The translation therefore:

* creates every type under a unique temporary name, verifies its layout while
  that name is unambiguous, and moves and renames it last;
* lays out ordinary composites with explicit offsets (zero-length stub, then
  ``resize_struct`` and ``add_struct_field``);
* builds composites with bitfields or 128-bit members through one
  self-contained ``#pragma pack(1)`` C import each, using exact-size
  placeholders for every member that names another type, then retypes the
  placeholders with ``modify_struct_field`` (which keeps the given name);
* never deletes a data type.

``build_apply_program`` is file-only and deterministic.  ``execute_apply_program``
mutates the live program and must run under the item's ``ghidra-writer`` lease.
"""

from __future__ import annotations

import keyword
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .constants import REFERENCE_SHA256
from .util import SocomError, load_json, sha256_file

APPLY_PROGRAM_KIND = "socom-ghidra-type-apply-program"
APPLY_PROGRAM_SCHEMA = 1
TEMP_PREFIX = "socom_t_"
ANONYMOUS_CATEGORY = "/project/anonymous"
POINTER_SIZE = 4
STUB_FIELD = "socom_stub"
ANON_FIELD_PREFIX = "socom_anon_"


@dataclass(frozen=True)
class FundType:
    ghidra: str
    c: str
    size: int | None


# DWARF 1 fundamental types as emitted by Metrowerks for the R5900.  Widths are
# Ghidra's r5900 data organization (long is 64-bit), cross-checked against
# plan member offsets.  0x8208 is GNU's FT_unsigned_long_long; 0xA510 is only
# used for 16-byte members (_word128::u128, DMA packet pointers) whose source
# spelling is u_long128, so it maps to Ghidra's unsigned 16-byte integer.
FUND_TYPES: dict[int, FundType] = {
    0x0001: FundType("char", "char", 1),
    0x0003: FundType("uchar", "unsigned char", 1),
    0x0005: FundType("short", "short", 2),
    0x0006: FundType("ushort", "unsigned short", 2),
    0x0008: FundType("int", "int", 4),
    0x0009: FundType("uint", "unsigned int", 4),
    # The bridge sizes an inserted long/ulong with Ghidra's default data
    # organization (4 bytes) unless the program already resolved it, so the
    # 64-bit EE long is spelled with the fixed-width long long types.
    0x000B: FundType("longlong", "long long", 8),
    0x000C: FundType("ulonglong", "unsigned long long", 8),
    0x000E: FundType("float", "float", 4),
    0x000F: FundType("double", "double", 8),
    0x0014: FundType("void", "void", None),
    0x8208: FundType("ulonglong", "unsigned long long", 8),
    0xA510: FundType("uint16", "uint16", 16),
}
INT128_FUND = 0xA510
VOID_FUND = 0x0014


C_RESERVED = set(keyword.kwlist) | {
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "_Bool", "_Complex",
}
C_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DECISIONS = (
    "Metrowerks DWARF 1 bit_offset is the least-significant-bit position in the "
    "little-endian storage unit (sceGifTag NLOOP/EOP; __ct__8CAiEventFv stores "
    "m_id with sh 0x18, m_visible via byte 0x1a bit 0, m_type via halfword "
    "0x1a bits 1-15).",
    "Fundamental types keep their R5900 widths: the 64-bit EE long and "
    "unsigned long are spelled longlong/ulonglong (the bridge sizes long/ulong "
    "with Ghidra's default 4-byte organization), 0x8208 is ulonglong, and "
    "0xA510 is uint16 (16-byte unsigned, u_long128).",
    "Multi-dimensional arrays T[a][b] are created as arrays of T[b] because "
    "the bridge parses one array dimension.",
    "reference_to modifiers become Ghidra pointers.",
    "A class whose two or more data members all share one offset becomes a "
    "Ghidra union; members sharing a non-zero offset inside a class become an "
    "unnamed component of a helper union named @union@<offset> in the owner's "
    "category.",
    "Base classes are components named super_<base>. An empty base (no "
    "members, at most one byte) that shares its offset with another component "
    "(empty-base optimization) or sits in a C-imported layout cannot be "
    "represented by the bridge and is omitted; each omission is listed.",
    "A data member whose DWARF type is plain void is typed undefined1[n] over "
    "its exact layout extent (Metrowerks pointer-to-member-function).",
    "Anonymous classes reached from named types are named "
    "/project/anonymous/<raw-name>@<structural-class>; subroutine types become "
    "function definitions /project/anonymous/@subroutine@<structural-class> "
    "with the plan's return type and unspecified (...) parameters, because the "
    "plan records no formal parameters.",
    "Enum element values are decoded at the enum's byte width as signed "
    "little-endian integers.",
    "Composites with bitfields or 128-bit members are created by one "
    "self-contained #pragma pack(1) C import each, with unnamed bitfield "
    "padding for gaps; all other composites are non-packed with explicit "
    "offsets and undefined filler.",
)


def _hex10(structural_class: str) -> str:
    return structural_class.rsplit(":", 1)[-1][:10]


def _location_offset(location: str | None) -> int:
    # DW_OP_CONST <u32> DW_OP_ADD: a constant member offset.
    if (
        not isinstance(location, str)
        or len(location) != 12
        or not location.startswith("04")
        or not location.endswith("07")
    ):
        raise SocomError(f"unsupported member location expression: {location!r}")
    return int.from_bytes(bytes.fromhex(location[2:10]), "little")


def _split_path(path: str) -> tuple[str, str]:
    category, _, name = path.rpartition("/")
    if not category.startswith("/project") or not name:
        raise SocomError(f"type path is outside /project: {path!r}")
    return category, name


def _identifier(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_")
    return cleaned or "base"


def decode_enum_values(row: dict[str, Any]) -> list[list[Any]]:
    width = row.get("byte_size")
    attribute = row["evidence"]["attributes"].get("element_list")
    if width not in (1, 2, 4) or not attribute:
        raise SocomError(f"enum {row.get('ghidra_path')} has no decodable element list")
    block = bytes.fromhex(attribute["value"])
    values: list[list[Any]] = []
    index = 0
    while index < len(block):
        if index + width > len(block):
            raise SocomError(f"enum {row.get('ghidra_path')} element list is truncated")
        value = int.from_bytes(block[index : index + width], "little", signed=True)
        index += width
        end = block.find(b"\x00", index)
        if end < 0:
            raise SocomError(f"enum {row.get('ghidra_path')} element name is unterminated")
        name = block[index:end].decode("ascii")
        index = end + 1
        if not C_IDENTIFIER.match(name):
            raise SocomError(f"enum {row.get('ghidra_path')} has invalid element {name!r}")
        values.append([name, value])
    if not values:
        raise SocomError(f"enum {row.get('ghidra_path')} has no elements")
    return values


# Type references are nested tuples:
#   ("fund", code) | ("named", key) | ("ptr", ref) | ("array", ref, count)
#   | ("raw", size)
Ref = tuple


def _contains_fund(ref: Ref, code: int) -> bool:
    if ref[0] == "fund":
        return ref[1] == code
    if ref[0] in ("ptr", "array"):
        return _contains_fund(ref[1], code)
    return False


def _named_keys(ref: Ref, *, through_pointers: bool) -> list[tuple]:
    if ref[0] == "named":
        return [ref[1]]
    if ref[0] == "array":
        return _named_keys(ref[1], through_pointers=through_pointers)
    if ref[0] == "ptr" and through_pointers:
        return _named_keys(ref[1], through_pointers=through_pointers)
    return []


def _pointer_targets(ref: Ref) -> list[tuple]:
    if ref[0] == "ptr":
        return _named_keys(ref[1], through_pointers=True)
    if ref[0] == "array":
        return _pointer_targets(ref[1])
    return []


def _c_direct(ref: Ref) -> bool:
    """True when the reference spells in C without naming another type."""

    if ref[0] == "fund":
        return ref[1] != VOID_FUND
    if ref[0] == "ptr":
        inner = ref[1]
        while inner[0] == "ptr":
            inner = inner[1]
        return inner[0] == "fund"
    if ref[0] == "array":
        return _c_direct(ref[1])
    return False


def _c_declaration(ref: Ref, declarator: str) -> str:
    if ref[0] == "fund":
        return f"{FUND_TYPES[ref[1]].c} {declarator}"
    if ref[0] == "ptr":
        inner = ref[1]
        wrapped = f"(*{declarator})" if inner[0] == "array" else f"*{declarator}"
        return _c_declaration(inner, wrapped)
    if ref[0] == "array":
        return _c_declaration(ref[1], f"{declarator}[{ref[2]}]")
    raise SocomError(f"reference cannot be spelled in C: {ref!r}")


class _Translator:
    def __init__(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.by_die: dict[int, dict[str, Any]] = {}
        for row in plan["types"]:
            offset = row["evidence"]["die_offset"]
            if offset in self.by_die:
                raise SocomError(f"duplicate DIE offset in plan: {offset}")
            self.by_die[offset] = row
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in plan["types"]:
            if row.get("ghidra_path"):
                groups[row["ghidra_path"]].append(row)
        self.representatives: dict[str, dict[str, Any]] = {}
        for path, rows in sorted(groups.items()):
            complete = sorted(
                (row for row in rows if not row["declaration"]),
                key=lambda row: row["evidence"]["die_offset"],
            )
            classes = {row["structural_class"] for row in complete}
            if len(classes) > 1:
                raise SocomError(f"{path} has more than one complete layout")
            self.representatives[path] = (
                complete[0]
                if complete
                else min(rows, key=lambda row: row["evidence"]["die_offset"])
            )
        # entity key -> entity description (filled by _entity)
        self.entities: dict[tuple, dict[str, Any]] = {}
        self.pending: list[tuple] = []
        self.omissions: list[dict[str, Any]] = []

    # -- references -----------------------------------------------------

    def ref(self, descriptor: dict[str, Any] | None, where: str) -> Ref:
        if descriptor is None:
            raise SocomError(f"{where}: missing type descriptor")
        modifiers = descriptor.get("modifiers") or []
        for modifier in modifiers:
            if modifier not in ("pointer_to", "reference_to"):
                raise SocomError(f"{where}: unsupported type modifier {modifier!r}")
        if descriptor.get("die_offset") is None:
            code = descriptor.get("fund_type")
            if code not in FUND_TYPES:
                raise SocomError(f"{where}: unsupported fundamental type {code!r}")
            result: Ref = ("fund", code)
        else:
            result = self._die_ref(int(descriptor["die_offset"]), where)
        for _ in modifiers:
            result = ("ptr", result)
        return result

    def _die_ref(self, offset: int, where: str) -> Ref:
        row = self.by_die.get(offset)
        if row is None:
            raise SocomError(f"{where}: reference to DIE 0x{offset:x} outside the plan")
        kind = row["kind"]
        if kind == "array_type":
            array = row.get("array") or {}
            element = self.ref(array.get("element"), f"{where} array element")
            dimensions = array.get("dimensions") or []
            if not dimensions:
                raise SocomError(f"{where}: array without dimensions")
            for dimension in reversed(dimensions):
                if len(dimension) != 4 or dimension[0] != "fund":
                    raise SocomError(f"{where}: unsupported array dimension {dimension!r}")
                count = int(dimension[3]) - int(dimension[2]) + 1
                if count <= 0:
                    raise SocomError(f"{where}: unsupported array bound {dimension!r}")
                element = ("array", element, count)
            return element
        if kind == "subroutine_type":
            key = ("function", row["structural_class"])
            self._entity(key, row)
            return ("named", key)
        if row.get("ghidra_path"):
            key = ("path", row["ghidra_path"])
            self._entity(key, self.representatives[row["ghidra_path"]])
            return ("named", key)
        if kind in ("class_type", "structure_type", "union_type"):
            key = ("anonymous", row["structural_class"])
            self._entity(key, row)
            return ("named", key)
        raise SocomError(f"{where}: unsupported anonymous {kind}")

    def _entity(self, key: tuple, row: dict[str, Any]) -> None:
        if key not in self.entities:
            self.entities[key] = {"key": key, "row": row}
            self.pending.append(key)

    # -- sizes ------------------------------------------------------------

    def size(self, ref: Ref, where: str) -> int:
        if ref[0] == "fund":
            size = FUND_TYPES[ref[1]].size
            if size is None:
                raise SocomError(f"{where}: void used by value")
            return size
        if ref[0] == "ptr":
            return POINTER_SIZE
        if ref[0] == "array":
            return ref[2] * self.size(ref[1], where)
        if ref[0] == "raw":
            return ref[1]
        key = ref[1]
        row = self.entities[key]["row"]
        if key[0] == "function":
            raise SocomError(f"{where}: function type used by value")
        size = row.get("byte_size")
        if not isinstance(size, int) or row["declaration"]:
            raise SocomError(f"{where}: incomplete type used by value")
        return size

    def is_empty_class(self, key: tuple) -> bool:
        row = self.entities[key]["row"]
        return (
            key[0] in ("path", "anonymous")
            and row["kind"] != "enumeration_type"
            and not row["members"]
            and (row.get("byte_size") or 0) <= 1
        )

    # -- composites -------------------------------------------------------

    def composite(self, key: tuple) -> dict[str, Any]:
        row = self.entities[key]["row"]
        where = self.final_path(key)
        size = row.get("byte_size") if not row["declaration"] else None
        items: list[dict[str, Any]] = []
        bitfields: list[dict[str, Any]] = []
        void_members: list[dict[str, Any]] = []
        for member in row["members"]:
            offset = _location_offset(member.get("location"))
            label = f"{where}.{member.get('name') or '<base>'}"
            if member["tag"] == "inheritance":
                base = self.ref(member["type"], label)
                if base[0] != "named" or base[1][0] not in ("path", "anonymous"):
                    raise SocomError(f"{label}: base is not a class")
                items.append(
                    {
                        "role": "base",
                        "offset": offset,
                        "ref": base,
                        "empty": self.is_empty_class(base[1]),
                    }
                )
            elif member["tag"] != "member":
                raise SocomError(f"{label}: unsupported member tag {member['tag']!r}")
            elif member.get("bit_size") is not None:
                descriptor = member["type"]
                if descriptor.get("die_offset") is not None or descriptor.get("modifiers"):
                    raise SocomError(f"{label}: bitfield of non-fundamental type")
                code = descriptor.get("fund_type")
                fund = FUND_TYPES.get(code)
                if fund is None or fund.size is None or code == INT128_FUND:
                    raise SocomError(f"{label}: unsupported bitfield type {code!r}")
                width = int(member["bit_size"])
                if width <= 0 or width > fund.size * 8:
                    raise SocomError(f"{label}: bitfield width {width} does not fit its type")
                # Metrowerks places the field at bit location*8 + bit_offset of
                # the little-endian layout, counted from the least-significant
                # bit (CAiEvent::m_visible: location 24, bit_offset 16).
                bitfields.append(
                    {
                        "name": member["name"],
                        "absolute": offset * 8 + int(member["bit_offset"]),
                        "width": width,
                        "fund": code,
                    }
                )
            else:
                descriptor = member["type"]
                if (
                    descriptor.get("die_offset") is None
                    and descriptor.get("fund_type") == VOID_FUND
                    and not descriptor.get("modifiers")
                ):
                    entry = {"role": "field", "offset": offset, "name": member["name"], "ref": None}
                    void_members.append(entry)
                    items.append(entry)
                else:
                    items.append(
                        {
                            "role": "field",
                            "offset": offset,
                            "name": member["name"],
                            "ref": self.ref(descriptor, label),
                        }
                    )
        # Bitfields whose bytes touch form one run that starts on a byte.
        bitfields.sort(key=lambda field: field["absolute"])
        run: dict[str, Any] | None = None
        end_bit = 0
        for field in bitfields:
            if run is not None and field["absolute"] < end_bit:
                raise SocomError(f"{where}: bitfield {field['name']} overlaps another bitfield")
            if run is None or field["absolute"] // 8 >= (end_bit + 7) // 8:
                run = {"role": "bits", "offset": field["absolute"] // 8, "fields": []}
                items.append(run)
            start = run["offset"] * 8
            run["fields"].append({**field, "bit": field["absolute"] - start})
            end_bit = field["absolute"] + field["width"]
            run["size"] = (end_bit + 7) // 8 - run["offset"]

        starts = sorted({item["offset"] for item in items})
        limit = size if isinstance(size, int) else None
        for entry in void_members:
            later = [start for start in starts if start > entry["offset"]]
            end = later[0] if later else limit
            if end is None or end <= entry["offset"]:
                raise SocomError(f"{where}.{entry['name']}: void member without extent")
            entry["ref"] = ("raw", end - entry["offset"])
            self.omissions.append(
                {
                    "type": where,
                    "member": entry["name"],
                    "offset": entry["offset"],
                    "reason": f"DWARF type void; typed undefined1[{end - entry['offset']}] over its layout extent",
                }
            )
        for item in items:
            if item["role"] == "field":
                item["size"] = self.size(item["ref"], f"{where}.{item['name']}")
            elif item["role"] == "base":
                item["size"] = 0 if item["empty"] else self.size(item["ref"], f"{where} base")

        # Metrowerks lists a virtual base as inheritance at offset 0 and places
        # its subobject as a data member of the same type.
        virtual: list[dict[str, Any]] = []
        for item in items:
            if item["role"] != "base" or item["empty"]:
                continue
            overlaps = any(
                other is not item
                and other["size"] > 0
                and other["offset"] < item["offset"] + item["size"]
                and item["offset"] < other["offset"] + other["size"]
                for other in items
            )
            placed = [
                other
                for other in items
                if other["role"] == "field" and other["ref"] == item["ref"]
            ]
            if overlaps and placed:
                virtual.append(item)
                self.omissions.append(
                    {
                        "type": where,
                        "member": self.base_name(item["ref"]),
                        "offset": item["offset"],
                        "reason": (
                            "virtual base: subobject placed by member "
                            f"{placed[0]['name']} at {placed[0]['offset']}"
                        ),
                    }
                )
        items = [item for item in items if item not in virtual]

        # Empty bases take no space when another component shares their byte.
        kept: list[dict[str, Any]] = []
        for item in items:
            if item["role"] == "base" and item["empty"]:
                shared = any(
                    other is not item
                    and other["size"] > 0
                    and other["offset"] <= item["offset"] < other["offset"] + other["size"]
                    for other in items
                )
                outside = isinstance(size, int) and item["offset"] >= size
                if shared or outside:
                    self.omissions.append(
                        {
                            "type": where,
                            "member": self.base_name(item["ref"]),
                            "offset": item["offset"],
                            "reason": (
                                "empty base shares its offset (empty-base optimization)"
                                if shared
                                else "empty base at the end of the layout takes no space"
                            ),
                        }
                    )
                    continue
                item["size"] = 1
            kept.append(item)

        kept.sort(key=lambda item: (item["offset"], -item["size"]))
        clusters: list[list[dict[str, Any]]] = []
        end = -1
        for item in kept:
            if clusters and item["offset"] < end:
                clusters[-1].append(item)
                end = max(end, item["offset"] + item["size"])
            else:
                clusters.append([item])
                end = item["offset"] + item["size"]

        components: list[dict[str, Any]] = []
        for cluster in clusters:
            if len(cluster) == 1:
                components.append(cluster[0])
                continue
            offset = cluster[0]["offset"]
            if any(item["role"] != "field" or item["offset"] != offset for item in cluster):
                raise SocomError(
                    f"{where}: overlapping members at offset {offset} are not a plain union"
                )
            components.append(
                {
                    "role": "union",
                    "offset": offset,
                    "size": max(item["size"] for item in cluster),
                    "fields": [{"name": item["name"], "ref": item["ref"], "size": item["size"]} for item in cluster],
                }
            )

        if isinstance(size, int):
            for component in components:
                if component["offset"] + component["size"] > size:
                    raise SocomError(f"{where}: component at {component['offset']} exceeds the type size")
        elif components:
            raise SocomError(f"{where}: declaration with members")

        names = [
            component.get("name") or ""
            for component in components
            if component["role"] == "field"
        ] + [
            field["name"]
            for component in components
            if component["role"] in ("bits", "union")
            for field in component["fields"]
        ]
        named = [name for name in names if name]
        if len(named) != len(set(named)) or len(named) != len(names):
            raise SocomError(f"{where}: missing or duplicate member names")

        uses_int128 = any(
            _contains_fund(field["ref"], INT128_FUND)
            for component in components
            for field in ([component] if component["role"] in ("field", "base") else component.get("fields", []))
            if component["role"] != "bits"
        )
        has_bits = any(component["role"] == "bits" for component in components)
        is_union = (
            len(components) == 1
            and components[0]["role"] == "union"
            and components[0]["offset"] == 0
            and size == components[0]["size"]
        )
        if is_union:
            union_fields = components[0]["fields"]
            if uses_int128:
                if not all(_c_direct(field["ref"]) for field in union_fields):
                    raise SocomError(f"{where}: 128-bit union needs non-C members")
                route = "c-union"
            else:
                route = "union"
            return {"route": route, "size": size, "union_fields": union_fields}
        if has_bits or uses_int128:
            for component in components:
                if component["role"] == "base" and self.is_empty_class(component["ref"][1]):
                    # A zero-length component would shift a packed C layout.
                    self.omissions.append(
                        {
                            "type": where,
                            "member": self.base_name(component["ref"]),
                            "offset": component["offset"],
                            "reason": "empty base inside a C-imported layout",
                        }
                    )
            components = [
                component
                for component in components
                if not (component["role"] == "base" and self.is_empty_class(component["ref"][1]))
            ]
            return {"route": "c", "size": size, "components": components}
        if not components:
            return {"route": "empty", "size": size}
        return {"route": "fields", "size": size, "components": components}

    def base_name(self, ref: Ref) -> str:
        _category, leaf = self.final_path(ref[1]).rsplit("/", 1)
        return "super_" + _identifier(leaf)

    # -- naming -----------------------------------------------------------

    def final_path(self, key: tuple) -> str:
        kind = key[0]
        if kind == "path":
            return key[1]
        if kind == "anonymous":
            row = self.entities[key]["row"]
            raw = row.get("raw_name") or "@" + row["kind"].removesuffix("_type")
            return f"{ANONYMOUS_CATEGORY}/{raw}@{_hex10(key[1])}"
        if kind == "function":
            return f"{ANONYMOUS_CATEGORY}/@subroutine@{_hex10(key[1])}"
        if kind == "helper-union":
            return f"{self.final_path(key[1])}/@union@0x{key[2]:x}"
        raise SocomError(f"unknown entity key {key!r}")


def _render(ref: Ref, names: dict[tuple, str]) -> str:
    if ref[0] == "fund":
        return FUND_TYPES[ref[1]].ghidra
    if ref[0] == "named":
        return names[ref[1]]
    if ref[0] == "ptr":
        return f"{_render(ref[1], names)} *"
    if ref[0] == "array":
        inner = ref[1]
        counts = [ref[2]]
        while inner[0] == "array":
            counts.append(inner[2])
            inner = inner[1]
        return _render(inner, names) + "".join(f"[{count}]" for count in counts)
    if ref[0] == "raw":
        return f"undefined1[{ref[1]}]"
    raise SocomError(f"cannot render {ref!r}")


def _bit_lines(
    offset: int, bit: int, width: int, type_name: str, name: str
) -> list[Any]:
    start = offset + bit // 8
    size = (bit % 8 + width + 7) // 8
    return [start, size, f"{type_name}:{width}", name]


def _c_layout(
    translator: _Translator,
    names: dict[tuple, str],
    temp: str,
    size: int,
    components: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[list[Any]]]:
    """Return (C source, placeholder retypes, expected layout lines)."""

    lines: list[str] = []
    retypes: list[dict[str, Any]] = []
    expected: list[list[Any]] = []
    cursor = 0

    def filler(until: int) -> None:
        nonlocal cursor
        while cursor < until:
            lines.append("  unsigned char : 8;")
            expected.append([cursor, 1, "uchar:8", "(unnamed)"])
            cursor += 1

    for component in components:
        filler(component["offset"])
        if cursor != component["offset"]:
            raise SocomError(f"{temp}: overlapping C components at {component['offset']}")
        role = component["role"]
        if role == "bits":
            # pack(1) allocates bitfields contiguously; unnamed padding of the
            # neighbouring field's type fills holes and closes the last byte.
            def pad(position: int, width: int, fund: FundType) -> None:
                chunk = (fund.size or 1) * 8
                while width > 0:
                    step = min(width, chunk)
                    lines.append(f"  {fund.c} : {step};")
                    expected.append(_bit_lines(cursor, position, step, fund.ghidra, "(unnamed)"))
                    position += step
                    width -= step

            position = 0
            fund = FUND_TYPES[component["fields"][0]["fund"]]
            for field in component["fields"]:
                fund = FUND_TYPES[field["fund"]]
                pad(position, field["bit"] - position, fund)
                if not C_IDENTIFIER.match(field["name"]) or field["name"] in C_RESERVED:
                    raise SocomError(f"{temp}: bitfield name {field['name']!r} is not a C identifier")
                lines.append(f"  {fund.c} {field['name']} : {field['width']};")
                expected.append(_bit_lines(cursor, field["bit"], field["width"], fund.ghidra, field["name"]))
                position = field["bit"] + field["width"]
            pad(position, component["size"] * 8 - position, fund)
            cursor += component["size"]
            continue
        if role == "union":
            helper = names[("helper-union", component["owner"], component["offset"])]
            placeholder = f"{ANON_FIELD_PREFIX}{component['offset']:x}"
            lines.append(f"  unsigned char {placeholder}[{component['size']}];")
            retypes.append({"placeholder": placeholder, "type": helper, "name": ""})
            expected.append([cursor, component["size"], helper, "(unnamed)"])
        else:
            name = component.get("name") if role == "field" else translator.base_name(component["ref"])
            ref = component["ref"]
            if role == "field" and _c_direct(ref):
                if not C_IDENTIFIER.match(name) or name in C_RESERVED:
                    raise SocomError(f"{temp}: member name {name!r} is not a C identifier")
                lines.append(f"  {_c_declaration(ref, name)};")
            else:
                placeholder = name if C_IDENTIFIER.match(name) and name not in C_RESERVED else f"socom_ph_{component['offset']:x}"
                lines.append(f"  unsigned char {placeholder}[{component['size']}];")
                retypes.append({"placeholder": placeholder, "type": _render(ref, names), "name": name})
            expected.append([cursor, component["size"], _render(ref, names), name])
        cursor += component["size"]
    filler(size)
    source = (
        "#pragma pack(push, 1)\n"
        f"struct {temp} {{\n" + "\n".join(lines) + "\n};\n#pragma pack(pop)\n"
    )
    return source, retypes, expected


def build_apply_program(root: Path, plan_path: Path) -> dict[str, Any]:
    plan = load_json(plan_path)
    if plan.get("kind") != "socom-ghidra-import-plan" or plan.get("schema_version") != 4:
        raise SocomError("apply programs require a schema 4 socom-ghidra-import-plan")
    if plan.get("conflicts"):
        raise SocomError("the import plan still has blocking conflicts")
    if (plan.get("batch") or {}).get("selection") != "types":
        raise SocomError("only types-only import plans can be applied")
    if plan.get("functions") or plan.get("variables"):
        raise SocomError("types-only plans must not carry functions or variables")
    target = plan.get("target") or {}
    if target.get("source_sha256") != REFERENCE_SHA256 or target.get("program") != "socom.elf":
        raise SocomError("the import plan targets a different program")

    translator = _Translator(plan)
    scope_paths = sorted(plan["receipt_scope"]["types"])
    for path in scope_paths:
        if path not in translator.representatives:
            raise SocomError(f"receipt-scope type has no plan rows: {path}")
        translator._entity(("path", path), translator.representatives[path])

    composites: dict[tuple, dict[str, Any]] = {}
    while translator.pending:
        key = translator.pending.pop(0)
        row = translator.entities[key]["row"]
        if key[0] == "function":
            descriptor = row.get("type")
            translator.entities[key]["return"] = (
                translator.ref(descriptor, translator.final_path(key))
                if descriptor
                else ("fund", VOID_FUND)
            )
        elif row["kind"] == "enumeration_type":
            translator.entities[key]["values"] = decode_enum_values(row)
        else:
            composites[key] = translator.composite(key)

    helpers: dict[tuple, dict[str, Any]] = {}
    for key, layout in composites.items():
        for component in layout.get("components", []):
            if component["role"] == "union":
                component["owner"] = key
                helper_key = ("helper-union", key, component["offset"])
                if any(_contains_fund(field["ref"], INT128_FUND) for field in component["fields"]):
                    raise SocomError(f"{translator.final_path(helper_key)}: 128-bit helper union")
                helpers[helper_key] = {
                    "route": "union",
                    "size": component["size"],
                    "union_fields": component["fields"],
                }

    all_keys = list(translator.entities) + list(helpers)
    paths = {key: translator.final_path(key) for key in all_keys}
    if len(set(paths.values())) != len(paths):
        raise SocomError("two entities map to the same Ghidra path")
    ordered_keys = sorted(all_keys, key=lambda key: paths[key])
    names = {key: f"{TEMP_PREFIX}{index:04d}" for index, key in enumerate(ordered_keys, start=1)}

    def kind_of(key: tuple) -> str:
        if key[0] == "function":
            return "function"
        if key[0] == "helper-union":
            return "union"
        row = translator.entities[key]["row"]
        if row["kind"] == "enumeration_type":
            return "enum"
        route = composites[key]["route"]
        return "union" if route in ("union", "c-union") else "struct"

    layouts = {**composites, **helpers}

    # Definition order: by-value dependencies first; pointers to unions also
    # wait for the union because unions have no stubs.
    union_keys = {key for key in all_keys if kind_of(key) == "union"}
    dependencies: dict[tuple, set[tuple]] = {key: set() for key in layouts}
    for key, layout in layouts.items():
        refs: list[Ref] = []
        for component in layout.get("components", []):
            if component["role"] in ("field", "base"):
                refs.append(component["ref"])
            elif component["role"] == "union":
                dependencies[key].add(("helper-union", key, component["offset"]))
        refs.extend(field["ref"] for field in layout.get("union_fields", []))
        for ref in refs:
            for target in _named_keys(ref, through_pointers=False):
                if target in layouts:
                    dependencies[key].add(target)
            for target in _pointer_targets(ref):
                if target in union_keys:
                    dependencies[key].add(target)
        dependencies[key].discard(key)
    order: list[tuple] = []
    remaining = {key: set(values) for key, values in dependencies.items()}
    while remaining:
        ready = sorted((key for key, values in remaining.items() if not values), key=lambda key: paths[key])
        if not ready:
            raise SocomError("by-value type dependencies contain a cycle")
        for key in ready:
            order.append(key)
            del remaining[key]
        for values in remaining.values():
            values.difference_update(ready)

    for key in translator.entities:
        if key[0] == "function":
            for target in _named_keys(translator.entities[key]["return"], through_pointers=True):
                if target in union_keys or target[0] == "function":
                    raise SocomError(
                        f"{paths[key]}: return type names a union or function type"
                    )

    entries: list[dict[str, Any]] = []
    for key in sorted((key for key in all_keys if key not in layouts), key=lambda key: paths[key]):
        category, leaf = _split_path(paths[key])
        entry: dict[str, Any] = {
            "temp": names[key],
            "path": paths[key],
            "category": category,
            "name": leaf,
            "kind": kind_of(key),
        }
        row = translator.entities[key]["row"]
        entry["structural_class"] = row.get("structural_class")
        if entry["kind"] == "enum":
            entry.update({"route": "enum", "size": row["byte_size"], "values": translator.entities[key]["values"]})
        else:
            entry.update(
                {
                    "route": "function",
                    "return_type": _render(translator.entities[key]["return"], names),
                    "parameters": "...",
                }
            )
        entries.append(entry)
    for key in order:
        layout = layouts[key]
        category, leaf = _split_path(paths[key])
        entry = {
            "temp": names[key],
            "path": paths[key],
            "category": category,
            "name": leaf,
            "kind": kind_of(key),
            "route": layout["route"],
            "size": layout["size"],
            "structural_class": (
                translator.entities[key]["row"].get("structural_class")
                if key[0] != "helper-union"
                else None
            ),
        }
        if layout["route"] in ("union", "c-union"):
            entry["fields"] = [
                {"name": field["name"], "type": _render(field["ref"], names), "size": field["size"]}
                for field in layout["union_fields"]
            ]
            if layout["route"] == "c-union":
                body = "\n".join(
                    f"  {_c_declaration(field['ref'], field['name'])};" for field in layout["union_fields"]
                )
                entry["c_source"] = (
                    "#pragma pack(push, 1)\n"
                    f"union {names[key]} {{\n{body}\n}};\n#pragma pack(pop)\n"
                )
        elif layout["route"] == "c":
            source, retypes, expected = _c_layout(translator, names, names[key], layout["size"], layout["components"])
            entry.update({"c_source": source, "retypes": retypes, "expected_layout": expected})
        elif layout["route"] == "fields":
            fields = []
            expected = []
            for component in layout["components"]:
                if component["role"] == "union":
                    helper = names[("helper-union", key, component["offset"])]
                    fields.append(
                        {
                            "offset": component["offset"],
                            "name": "",
                            "type": helper,
                            "size": component["size"],
                        }
                    )
                    expected.append([component["offset"], component["size"], helper, "(unnamed)"])
                    continue
                name = component["name"] if component["role"] == "field" else translator.base_name(component["ref"])
                type_name = _render(component["ref"], names)
                fields.append({"offset": component["offset"], "name": name, "type": type_name, "size": component["size"]})
                expected.append([component["offset"], component["size"], type_name, name])
            entry.update({"fields": fields, "expected_layout": expected})
        else:
            entry["expected_layout"] = []
        entries.append(entry)

    categories: set[str] = set()
    for entry in entries:
        parts = entry["category"].strip("/").split("/")
        for index in range(1, len(parts) + 1):
            categories.add("/" + "/".join(parts[:index]))
    scope = sorted(entry["path"] for entry in entries)
    missing = sorted(set(scope_paths) - set(scope))
    if missing:
        raise SocomError(f"apply program misses receipt-scope types: {missing[:5]}")
    routes: dict[str, int] = defaultdict(int)
    for entry in entries:
        routes[entry["route"]] += 1
    relative_plan = plan_path.resolve()
    try:
        relative_plan = relative_plan.relative_to(root.resolve())
    except ValueError:
        pass
    return {
        "kind": APPLY_PROGRAM_KIND,
        "schema_version": APPLY_PROGRAM_SCHEMA,
        "mutation_performed": False,
        "plan": {
            "path": relative_plan.as_posix() if isinstance(relative_plan, Path) else str(relative_plan),
            "sha256": sha256_file(plan_path),
            "work_item_id": (plan.get("batch") or {}).get("work_item_id"),
        },
        "target": target,
        "decisions": list(DECISIONS),
        "fund_types": {
            f"0x{code:04x}": {"ghidra": fund.ghidra, "c": fund.c, "size": fund.size}
            for code, fund in sorted(FUND_TYPES.items())
        },
        "categories": sorted(categories, key=lambda path: (path.count("/"), path)),
        "types": entries,
        "omissions": sorted(translator.omissions, key=lambda row: (row["type"], row["offset"], row["member"])),
        "receipt_scope": {"schema_version": 1, "functions": [], "types": scope, "globals": []},
        "summary": {
            "type_count": len(entries),
            "plan_scope_type_count": len(scope_paths),
            "added_type_count": len(scope) - len(scope_paths),
            "routes": dict(sorted(routes.items())),
            "omission_count": len(translator.omissions),
            "category_count": len(categories),
        },
    }


# -- live execution --------------------------------------------------------


_MULTI_ARRAY = re.compile(r"^(.*?)((?:\[\d+\]){2,})$")
_LAYOUT_ROW = re.compile(r"^\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*$")


def parse_struct_layout(text: Any) -> dict[str, Any] | None:
    """Parse a bridge get_struct_layout response; None when it is not a struct."""

    if not isinstance(text, str) or not text.startswith("Structure:"):
        return None
    size_match = re.search(r"^Size:\s*(\d+)\s*bytes", text, re.MULTILINE)
    rows: list[list[Any]] = []
    started = False
    for line in text.splitlines():
        if line.startswith("-------|"):
            started = True
            continue
        if not started or not line.strip():
            continue
        match = _LAYOUT_ROW.match(line)
        if not match:
            raise SocomError(f"cannot parse struct layout row: {line!r}")
        rows.append([int(match.group(1)), int(match.group(2)), match.group(3), match.group(4)])
    return {"size": int(size_match.group(1)) if size_match else None, "components": rows}


def parse_enum_values(text: Any) -> dict[str, Any] | None:
    if not isinstance(text, str) or not text.startswith("Enumeration:"):
        return None
    size_match = re.search(r"^Size:\s*(\d+)\s*bytes", text, re.MULTILINE)
    values: list[list[Any]] = []
    started = False
    for line in text.splitlines():
        if line.startswith("-----|"):
            started = True
            continue
        if not started or not line.strip():
            continue
        name, _, value = line.partition("|")
        number = value.strip().split(" ", 1)[0]
        values.append([name.strip(), int(number)])
    return {"size": int(size_match.group(1)) if size_match else None, "values": sorted(values)}


class ApplyFailure(SocomError):
    """A failed live step; the unsaved program must be reverted before retrying."""

    def __init__(self, message: str, details: list[Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or []
        self.completed_steps = 0


def execute_apply_program(
    program: dict[str, Any],
    bridge: Any,
    *,
    type_index: Callable[[], list[dict[str, Any]]],
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Apply a translated program through the bridge and verify it."""

    if program.get("kind") != APPLY_PROGRAM_KIND or program.get("schema_version") != APPLY_PROGRAM_SCHEMA:
        raise SocomError("not a schema 1 type apply program")
    entries = program["types"]
    steps: list[dict[str, Any]] = []

    def post(endpoint: str, ok: Callable[[Any], bool], **body: Any) -> Any:
        response = bridge.post_json(endpoint, **body)
        steps.append({"endpoint": endpoint, "body": body, "response": response})
        if not ok(response):
            failure = ApplyFailure(f"{endpoint} failed for {body}: {response!r}")
            failure.completed_steps = len(steps) - 1
            raise failure
        return response

    def success(prefix: str) -> Callable[[Any], bool]:
        return lambda response: isinstance(response, str) and response.startswith(prefix)

    def status_ok(response: Any) -> bool:
        return isinstance(response, dict) and response.get("status") == "success"

    before = type_index()
    existing_names = {row["name"] for row in before}
    existing_paths = {row["path"] for row in before}
    for entry in entries:
        if entry["temp"] in existing_names:
            raise SocomError(f"temporary name already exists: {entry['temp']}")
        if entry["path"] in existing_paths:
            raise SocomError(f"target type already exists: {entry['path']}")
    if any(name.startswith(TEMP_PREFIX) for name in existing_names):
        raise SocomError("program already contains temporary apply types")

    stubbed = [entry for entry in entries if entry["kind"] == "struct" and entry["route"] in ("fields", "c", "empty")]
    log(f"stubs: {len(stubbed)}")
    for entry in stubbed:
        post(
            "create_struct",
            success("Successfully created structure"),
            name=entry["temp"],
            fields=[{"name": STUB_FIELD, "type": "undefined1", "offset": "0"}],
        )
        post("remove_struct_field", success("Successfully removed field"), struct_name=entry["temp"], field_name=STUB_FIELD)

    enums = [entry for entry in entries if entry["route"] == "enum"]
    log(f"enums: {len(enums)}")
    for entry in enums:
        post(
            "create_enum",
            status_ok,
            name=entry["temp"],
            size=entry["size"],
            values={name: value for name, value in entry["values"]},
        )

    functions = [entry for entry in entries if entry["route"] == "function"]
    log(f"function definitions: {len(functions)}")
    for entry in functions:
        post(
            "create_function_signature",
            success("Successfully created function signature"),
            name=entry["temp"],
            return_type=entry["return_type"],
            parameters=entry["parameters"],
        )

    c_entries = [entry for entry in entries if entry["route"] in ("c", "c-union")]
    log(f"C imports: {len(c_entries)}")
    for entry in c_entries:
        post(
            "import_data_types",
            lambda response: isinstance(response, dict)
            and response.get("parse_succeeded") is True
            and not response.get("error"),
            source=entry["c_source"],
            format="c",
        )

    # The bridge parses one array dimension only; build T[a][b] as an array
    # of T[b] just before its first use, when T is complete.
    known_names = set(existing_names)

    def ensure_array(type_name: str) -> None:
        match = _MULTI_ARRAY.match(type_name)
        if not match:
            return
        base = match.group(1)
        counts = [int(count) for count in re.findall(r"\[(\d+)\]", match.group(2))]
        inner = f"{base}[{counts[-1]}]"
        for count in reversed(counts[:-1]):
            outer = f"{base}[{count}]{inner[len(base):]}"
            if outer not in known_names:
                post(
                    "create_array_type",
                    success("Successfully created array type"),
                    base_type=inner,
                    length=count,
                )
                known_names.add(outer)
            inner = outer

    definitions = [entry for entry in entries if entry["route"] in ("fields", "union", "c", "empty")]
    log(f"definitions: {len(definitions)}")
    for index, entry in enumerate(definitions, start=1):
        if index % 100 == 0:
            log(f"  {index}/{len(definitions)}")
        if entry["route"] == "union":
            for field in entry["fields"]:
                ensure_array(field["type"])
            post(
                "create_union",
                lambda response: isinstance(response, str) and "created successfully" in response,
                name=entry["temp"],
                fields=[{"name": field["name"], "type": field["type"]} for field in entry["fields"]],
            )
            continue
        if entry["route"] == "c":
            for retype in entry["retypes"]:
                ensure_array(retype["type"])
                post(
                    "modify_struct_field",
                    success("Successfully modified field"),
                    struct_name=entry["temp"],
                    field_name=retype["placeholder"],
                    new_type=retype["type"],
                    new_name=retype["name"],
                )
            continue
        size = entry.get("size")
        # A zero-length stub reports one byte but has no room for fields; an
        # empty one-byte class stays zero-length so it can sit under a member.
        if isinstance(size, int) and (size > 1 or (size == 1 and entry.get("fields"))):
            post("resize_struct", status_ok, name=entry["temp"], new_size=size)
        for field in entry.get("fields", []):
            name = field["name"] or f"{ANON_FIELD_PREFIX}{field['offset']:x}"
            ensure_array(field["type"])
            post(
                "add_struct_field",
                success("Successfully added field"),
                struct_name=entry["temp"],
                field_name=name,
                field_type=field["type"],
                offset=field["offset"],
            )
            if not field["name"]:
                post(
                    "modify_struct_field",
                    success("Successfully modified field"),
                    struct_name=entry["temp"],
                    field_name=name,
                    new_type=field["type"],
                    new_name="",
                )

    log("verifying layouts")
    mismatches: list[dict[str, Any]] = []
    for entry in entries:
        if entry["route"] in ("fields", "c", "empty"):
            layout = parse_struct_layout(bridge.request("get_struct_layout", struct_name=entry["temp"]))
            expected_size = entry["size"] if isinstance(entry["size"], int) and entry["size"] > 0 else 1
            if layout is None or layout["components"] != entry["expected_layout"] or layout["size"] != expected_size:
                mismatches.append({"type": entry["path"], "temp": entry["temp"], "expected": entry["expected_layout"], "actual": layout})
        elif entry["route"] == "enum":
            values = parse_enum_values(bridge.request("get_enum_values", enum_name=entry["temp"]))
            if values is None or values["size"] != entry["size"] or values["values"] != sorted(entry["values"]):
                mismatches.append({"type": entry["path"], "temp": entry["temp"], "expected": entry["values"], "actual": values})
    index_rows = {row["name"]: row for row in type_index()}
    for entry in entries:
        row = index_rows.get(entry["temp"])
        expected_size: Any = "variable" if entry["route"] == "function" else (
            entry["size"] if isinstance(entry["size"], int) and entry["size"] > 0 else 1
        )
        if row is None or row["size"] != expected_size:
            mismatches.append({"type": entry["path"], "temp": entry["temp"], "expected_size": expected_size, "actual": row})
    if mismatches:
        failure = ApplyFailure(f"{len(mismatches)} applied types differ from the program", mismatches)
        failure.completed_steps = len(steps)
        raise failure

    log(f"categories: {len(program['categories'])}")
    known_categories = {row["path"].rsplit("/", 1)[0] for row in before}
    for category in program["categories"]:
        if category in known_categories:
            continue
        post(
            "create_data_type_category",
            lambda response: status_ok(response)
            or "already exists" in str(response).lower(),
            category_path=category,
        )
    log("moving and renaming")
    for entry in entries:
        post(
            "move_data_type_to_category",
            success("Successfully moved data type"),
            type_name=entry["temp"],
            category_path=entry["category"],
        )
    for entry in entries:
        post(
            "rename_data_type",
            success("Successfully renamed data type"),
            old_name=entry["temp"],
            new_name=entry["name"],
        )

    after = type_index()
    by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in after:
        by_path[row["path"]].append(row)
    problems: list[str] = []
    for row in before:
        if row not in after:
            problems.append(f"pre-existing type changed or vanished: {row['path']}")
    for entry in entries:
        rows = by_path.get(entry["path"], [])
        if len(rows) != 1:
            problems.append(f"{entry['path']} resolves {len(rows)} times")
    if any(row["name"].startswith(TEMP_PREFIX) for row in after):
        problems.append("temporary type names remain")
    if any(".conflict" in row["name"] for row in after):
        problems.append("Ghidra created .conflict variants")
    if problems:
        failure = ApplyFailure(f"{len(problems)} post-rename problems", problems)
        failure.completed_steps = len(steps)
        raise failure
    log("applied and verified")
    return {
        "ok": True,
        "type_count": len(entries),
        "bridge_call_count": len(steps),
        "types_before": len(before),
        "types_after": len(after),
    }
