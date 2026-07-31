from __future__ import annotations

import struct

from tools._socom.dwarf1 import (
    Dwarf1Debug,
    Dwarf1Line,
    debug_summary,
    line_summary,
)


def _string_attr(code: int, value: str) -> bytes:
    return struct.pack("<H", code | 0x8) + value.encode("ascii") + b"\0"


def _data4_attr(code: int, value: int) -> bytes:
    return struct.pack("<HI", code | 0x6, value)


def _die(tag: int, attributes: bytes) -> bytes:
    return struct.pack("<IH", 6 + len(attributes), tag) + attributes


def test_synthetic_dwarf_record() -> None:
    raw = _die(
        0x0011,
        _string_attr(0x0030, r"Z:\dev\gamez\sample.cpp")
        + _string_attr(0x0250, "MW MIPS C Compiler")
        + _data4_attr(0x0110, 0x140010)
        + _data4_attr(0x0120, 0x140080),
    )
    dies = Dwarf1Debug(raw).parse()
    assert len(dies) == 1
    assert dies[0].tag_name == "compile_unit"
    assert dies[0].string("name") == r"Z:\dev\gamez\sample.cpp"
    assert dies[0].integer("low_pc") == 0x140010
    summary = debug_summary(dies)
    assert summary["compile_unit_count"] == 1
    assert summary["z_dev_source_path_count"] == 1


def test_synthetic_line_unit() -> None:
    entries = struct.pack("<IHI", 10, 0xFFFF, 0) + struct.pack(
        "<IHI", 11, 3, 4
    )
    raw = struct.pack("<II", 8 + len(entries), 0x1000) + entries
    summary = line_summary(Dwarf1Line(raw).parse())
    assert summary["unit_count"] == 1
    assert summary["entry_count"] == 2
    assert summary["units"][0]["first_address"] == 0x1000
    assert summary["units"][0]["last_address"] == 0x1004


def test_reference_debug_counts(reference) -> None:
    dies = Dwarf1Debug(reference.section_data(".debug")).parse(strict=True)
    summary = debug_summary(dies)
    assert len(dies) == 116_691
    assert summary["compile_unit_count"] == 959
    assert summary["named_type_count"] == 16_602
    assert summary["z_dev_source_path_count"] == 52
    assert any(
        row["name"] == "CNode" for row in summary["named_types"]
    )
    units = Dwarf1Line(reference.section_data(".line")).parse()
    lines = line_summary(units)
    assert lines["unit_count"] == 880
    assert lines["entry_count"] == 18_790

