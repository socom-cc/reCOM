"""DWARF 1 reader for Metrowerks PS2 debug and line sections."""

from __future__ import annotations

import dataclasses
import struct
from collections import Counter
from pathlib import PureWindowsPath

from .util import SocomError, stable_id

FORM_ADDR = 0x1
FORM_REF = 0x2
FORM_BLOCK2 = 0x3
FORM_BLOCK4 = 0x4
FORM_DATA2 = 0x5
FORM_DATA4 = 0x6
FORM_DATA8 = 0x7
FORM_STRING = 0x8

FORM_NAMES = {
    FORM_ADDR: "addr",
    FORM_REF: "ref",
    FORM_BLOCK2: "block2",
    FORM_BLOCK4: "block4",
    FORM_DATA2: "data2",
    FORM_DATA4: "data4",
    FORM_DATA8: "data8",
    FORM_STRING: "string",
}

TAG_NAMES = {
    0x0000: "padding",
    0x0001: "array_type",
    0x0002: "class_type",
    0x0003: "entry_point",
    0x0004: "enumeration_type",
    0x0005: "formal_parameter",
    0x0006: "global_subroutine",
    0x0007: "global_variable",
    0x000A: "label",
    0x000B: "lexical_block",
    0x000C: "local_variable",
    0x000D: "member",
    0x000F: "pointer_type",
    0x0010: "reference_type",
    0x0011: "compile_unit",
    0x0012: "string_type",
    0x0013: "structure_type",
    0x0014: "subroutine",
    0x0015: "subroutine_type",
    0x0016: "typedef",
    0x0017: "union_type",
    0x0018: "unspecified_parameters",
    0x0019: "variant",
    0x001A: "common_block",
    0x001B: "common_inclusion",
    0x001C: "inheritance",
    0x001D: "inlined_subroutine",
    0x001E: "module",
    0x001F: "ptr_to_member_type",
    0x0020: "set_type",
    0x0021: "subrange_type",
    0x0022: "with_stmt",
}

ATTRIBUTE_NAMES = {
    0x0010: "sibling",
    0x0020: "location",
    0x0030: "name",
    0x0050: "fund_type",
    0x0060: "mod_fund_type",
    0x0070: "user_def_type",
    0x0080: "mod_user_def_type",
    0x0090: "ordering",
    0x00A0: "subscr_data",
    0x00B0: "byte_size",
    0x00C0: "bit_offset",
    0x00D0: "bit_size",
    0x00F0: "element_list",
    0x0100: "stmt_list",
    0x0110: "low_pc",
    0x0120: "high_pc",
    0x0130: "language",
    0x0140: "member",
    0x0150: "discr",
    0x0160: "discr_value",
    0x0170: "visibility",
    0x0180: "import",
    0x0190: "string_length",
    0x01A0: "common_reference",
    0x01B0: "comp_dir",
    0x01C0: "const_value",
    0x01D0: "containing_type",
    0x01E0: "default_value",
    0x01F0: "friends",
    0x0200: "inline",
    0x0210: "is_optional",
    0x0220: "lower_bound",
    0x0230: "program",
    0x0240: "private",
    0x0250: "producer",
    0x0260: "protected",
    0x0270: "prototyped",
    0x0280: "public",
    0x0290: "pure_virtual",
    0x02A0: "return_addr",
    0x02B0: "specification",
    0x02C0: "start_scope",
    0x02E0: "stride_size",
    0x02F0: "upper_bound",
    0x0300: "virtual",
}

TYPE_TAGS = {
    0x0001,
    0x0002,
    0x0004,
    0x000F,
    0x0010,
    0x0012,
    0x0013,
    0x0015,
    0x0016,
    0x0017,
    0x001F,
    0x0020,
    0x0021,
}


@dataclasses.dataclass(frozen=True)
class Attribute:
    encoded_name: int
    name_code: int
    name: str
    form: int
    form_name: str
    value: int | str | bytes


@dataclasses.dataclass(frozen=True)
class Die:
    offset: int
    length: int
    tag: int
    tag_name: str
    attributes: tuple[Attribute, ...]

    def attribute(self, name: str) -> Attribute | None:
        return next((item for item in self.attributes if item.name == name), None)

    def string(self, name: str) -> str | None:
        item = self.attribute(name)
        return item.value if item and isinstance(item.value, str) else None

    def integer(self, name: str) -> int | None:
        item = self.attribute(name)
        return item.value if item and isinstance(item.value, int) else None


@dataclasses.dataclass(frozen=True)
class LineEntry:
    line: int
    column: int
    address: int


@dataclasses.dataclass(frozen=True)
class LineUnit:
    offset: int
    length: int
    base_address: int
    entries: tuple[LineEntry, ...]


class Dwarf1Debug:
    def __init__(self, data: bytes):
        self.data = data
        self.errors: list[str] = []

    def parse(self, *, strict: bool = True) -> tuple[Die, ...]:
        result: list[Die] = []
        offset = 0
        while offset < len(self.data):
            if len(self.data) - offset < 4:
                self._problem(strict, f"trailing {len(self.data) - offset} bytes at 0x{offset:x}")
                break
            length = struct.unpack_from("<I", self.data, offset)[0]
            if length == 0:
                self._problem(strict, f"zero-length DIE at 0x{offset:x}")
                break
            if length < 6:
                # Metrowerks uses a five-byte padding record: length plus one tag byte.
                if offset + length <= len(self.data):
                    offset += length
                    continue
                self._problem(strict, f"short DIE at 0x{offset:x} exceeds section")
                break
            end = offset + length
            if end > len(self.data):
                self._problem(strict, f"DIE at 0x{offset:x} exceeds section")
                break
            tag = struct.unpack_from("<H", self.data, offset + 4)[0]
            cursor = offset + 6
            attributes: list[Attribute] = []
            try:
                while cursor < end:
                    if cursor + 2 > end:
                        raise SocomError("truncated attribute identifier")
                    encoded = struct.unpack_from("<H", self.data, cursor)[0]
                    cursor += 2
                    form = encoded & 0xF
                    name_code = encoded & 0xFFF0
                    value, cursor = self._value(form, cursor, end)
                    attributes.append(
                        Attribute(
                            encoded_name=encoded,
                            name_code=name_code,
                            name=ATTRIBUTE_NAMES.get(name_code, f"attr_0x{name_code:03x}"),
                            form=form,
                            form_name=FORM_NAMES.get(form, f"form_{form}"),
                            value=value,
                        )
                    )
            except SocomError as exc:
                self._problem(strict, f"DIE 0x{offset:x}: {exc}")
                offset = end
                continue
            if cursor != end:
                self._problem(strict, f"DIE 0x{offset:x} did not end on record boundary")
            result.append(
                Die(
                    offset=offset,
                    length=length,
                    tag=tag,
                    tag_name=TAG_NAMES.get(tag, f"tag_0x{tag:04x}"),
                    attributes=tuple(attributes),
                )
            )
            offset = end
        return tuple(result)

    def _value(self, form: int, cursor: int, end: int) -> tuple[int | str | bytes, int]:
        sizes = {FORM_ADDR: 4, FORM_REF: 4, FORM_DATA2: 2, FORM_DATA4: 4, FORM_DATA8: 8}
        if form in sizes:
            size = sizes[form]
            if cursor + size > end:
                raise SocomError(f"truncated {FORM_NAMES[form]} attribute")
            return int.from_bytes(self.data[cursor : cursor + size], "little"), cursor + size
        if form == FORM_STRING:
            nul = self.data.find(b"\0", cursor, end)
            if nul < 0:
                raise SocomError("unterminated string attribute")
            return self.data[cursor:nul].decode("utf-8", errors="replace"), nul + 1
        if form in (FORM_BLOCK2, FORM_BLOCK4):
            size_width = 2 if form == FORM_BLOCK2 else 4
            if cursor + size_width > end:
                raise SocomError("truncated block length")
            size = int.from_bytes(self.data[cursor : cursor + size_width], "little")
            cursor += size_width
            if cursor + size > end:
                raise SocomError("block attribute exceeds DIE")
            return self.data[cursor : cursor + size], cursor + size
        raise SocomError(f"unknown DWARF 1 form 0x{form:x}")

    def _problem(self, strict: bool, message: str) -> None:
        self.errors.append(message)
        if strict:
            raise SocomError(message)


class Dwarf1Line:
    def __init__(self, data: bytes):
        self.data = data

    def parse(self) -> tuple[LineUnit, ...]:
        result = []
        offset = 0
        while offset < len(self.data):
            if len(self.data) - offset < 8:
                raise SocomError(f"truncated line unit at 0x{offset:x}")
            length, base = struct.unpack_from("<II", self.data, offset)
            if length < 8 or offset + length > len(self.data):
                raise SocomError(f"invalid line-unit length {length} at 0x{offset:x}")
            payload = length - 8
            if payload % 10:
                raise SocomError(f"line unit at 0x{offset:x} has partial entry")
            entries = []
            cursor = offset + 8
            end = offset + length
            while cursor < end:
                line, column, delta = struct.unpack_from("<IHI", self.data, cursor)
                entries.append(LineEntry(line=line, column=column, address=base + delta))
                cursor += 10
            result.append(LineUnit(offset, length, base, tuple(entries)))
            offset += length
        return tuple(result)


def debug_summary(dies: tuple[Die, ...]) -> dict[str, object]:
    tags = Counter(die.tag_name for die in dies)
    compile_units = []
    source_paths: set[str] = set()
    producers: set[str] = set()
    named_types = []

    for die in dies:
        name = die.string("name")
        if name and (":\\" in name or name.startswith("\\\\")):
            source_paths.add(name)
        if die.tag_name == "compile_unit":
            compile_units.append(
                {
                    "id": stable_id("cu", f"0x{die.offset:x}", name or ""),
                    "die_offset": die.offset,
                    "name": name,
                    "producer": die.string("producer"),
                    "language": die.integer("language"),
                    "low_pc": die.integer("low_pc"),
                    "high_pc": die.integer("high_pc"),
                    "stmt_list": die.integer("stmt_list"),
                }
            )
        producer = die.string("producer")
        if producer:
            producers.add(producer)
        if die.tag in TYPE_TAGS and name:
            named_types.append(
                {
                    "id": stable_id("type-evidence", f"0x{die.offset:x}", name),
                    "die_offset": die.offset,
                    "tag": die.tag_name,
                    "name": name,
                    "byte_size": die.integer("byte_size"),
                }
            )

    original_paths = sorted(source_paths, key=str.casefold)
    original_zdev = [
        path
        for path in original_paths
        if str(PureWindowsPath(path)).casefold().startswith("z:\\dev\\")
    ]
    return {
        "die_count": len(dies),
        "tag_counts": dict(sorted(tags.items())),
        "compile_unit_count": len(compile_units),
        "compile_units": compile_units,
        "named_type_count": len(named_types),
        "named_types": named_types,
        "producer_strings": sorted(producers, key=str.casefold),
        "source_path_count": len(original_paths),
        "source_paths": original_paths,
        "z_dev_source_path_count": len(original_zdev),
    }


def line_summary(units: tuple[LineUnit, ...]) -> dict[str, object]:
    entries = sum(len(unit.entries) for unit in units)
    return {
        "unit_count": len(units),
        "entry_count": entries,
        "units": [
            {
                "offset": unit.offset,
                "length": unit.length,
                "base_address": unit.base_address,
                "entry_count": len(unit.entries),
                "first_address": unit.entries[0].address if unit.entries else None,
                "last_address": unit.entries[-1].address if unit.entries else None,
            }
            for unit in units
        ],
    }
