from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from tools._socom import cli
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.source_graph import (
    SOURCE_GRAPH_KIND,
    build_source_graph,
    path_library,
    segments_markdown,
    source_graph,
)
from tools._socom.util import SocomError

BASE = 0x100000
A0, RA = 4, 31
NOP = 0
JR_RA = (RA << 21) | 0x08


def _lui(rt: int, imm: int) -> int:
    return (0x0F << 26) | (rt << 16) | imm


def _addiu(rt: int, rs: int, imm: int) -> int:
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _jal(target: int) -> int:
    return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)


def _strings(names: list[str]) -> tuple[bytes, dict[str, int]]:
    blob, offsets = b"\0", {"": 0}
    for name in names:
        if name not in offsets:
            offsets[name] = len(blob)
            blob += name.encode("ascii") + b"\0"
    return blob, offsets


def _string_attr(code: int, value: str) -> bytes:
    return struct.pack("<H", code | 0x8) + value.encode("ascii") + b"\0"


def _addr_attr(code: int, value: int) -> bytes:
    return struct.pack("<HI", code | 0x1, value)


def _die(tag: int, attributes: bytes) -> bytes:
    return struct.pack("<IH", 6 + len(attributes), tag) + attributes


# Symbol rows: (name, value, size, binding, type); binding 0 LOCAL, 1 GLOBAL;
# type 0 NOTYPE, 1 OBJECT, 2 FUNC, 3 SECTION.  Locals come first, in the
# per-object order a linker writes them.
SYMBOLS = [
    ("@1", 0x100100, 6, 0, 1),
    ("__sinit_a.cpp", 0x100140, 8, 0, 2),
    ("a_assist", 0x100038, 8, 0, 2),
    (".p__sinit_a.cpp", 0x100148, 4, 0, 1),
    ("Helper__13@unnamed@b_cpp@Fv", 0x100040, 8, 0, 2),
    (".text", 0x100048, 0, 0, 3),
    ("__ps2_libinfo__", 0x100120, 16, 0, 1),
    ("gcc2_compiled.", 0x100048, 0, 0, 0),
    (".rodata", 0x100110, 0, 0, 3),
    (".data", 0x100120, 0, 0, 3),
    ("a_first", 0x100000, 16, 1, 2),
    ("a_middle", 0x100010, 8, 1, 2),
    ("a_third", 0x100020, 24, 1, 2),
    ("sceFooInit", 0x100048, 16, 1, 2),
    ("fooHelper", 0x100058, 8, 1, 2),
    ("Run__4CDirFv", 0x100060, 8, 1, 2),
    ("gvar", 0x100108, 4, 1, 1),
]


def _index(name: str) -> int:
    return 1 + next(number for number, row in enumerate(SYMBOLS) if row[0] == name)


def _image() -> tuple[bytes, list[tuple[int, int, int]]]:
    """The ``main`` bytes and its (offset, symbol, type) relocations."""

    words: dict[int, int] = {}

    def code(address: int, *values: int) -> None:
        for number, value in enumerate(values):
            words[address + 4 * number] = value

    code(0x100000, _lui(A0, 0x10), _addiu(A0, A0, 0x100), JR_RA, NOP)  # a_first -> @1
    code(0x100010, JR_RA, NOP)  # a_middle: no references
    code(0x100020, _lui(A0, 0x10), _addiu(A0, A0, 0x100), _jal(0x100038), NOP, JR_RA, NOP)  # a_third
    code(0x100038, JR_RA, NOP)  # a_assist (static)
    code(0x100040, JR_RA, NOP)  # anonymous-namespace helper of b.cpp
    code(0x100048, _lui(A0, 0x10), _addiu(A0, A0, 0x110), JR_RA, NOP)  # sceFooInit -> .rodata
    code(0x100058, JR_RA, NOP)  # fooHelper
    code(0x100060, JR_RA, NOP)  # Run__4CDirFv
    code(0x100140, JR_RA, NOP)  # __sinit_a.cpp
    code(0x100148, 0x100140)  # .p__sinit_a.cpp
    data = bytearray(0x150)
    for address, value in words.items():
        struct.pack_into("<I", data, address - BASE, value)
    data[0x100 : 0x106] = b"a.cpp\0"
    data[0x110 : 0x114] = b"gnu!"
    data[0x120 : 0x130] = b"PsIIlibfoo  2500"
    relocations = [
        (0x100000, _index("@1"), 5),
        (0x100004, _index("@1"), 6),
        (0x100020, _index("@1"), 5),
        (0x100024, _index("@1"), 6),
        (0x100028, _index("a_assist"), 4),
        (0x100048, _index(".rodata"), 5),
        (0x10004C, _index(".rodata"), 6),
        (0x100148, _index("__sinit_a.cpp"), 2),
    ]
    return bytes(data), relocations


def _debug() -> tuple[bytes, bytes]:
    unit = _die(
        0x0011,
        _string_attr(0x0030, r"Z:\dev\x\c.cpp")
        + _string_attr(0x0250, "MW MIPS C Compiler")
        + _addr_attr(0x0110, 0x100060)
        + _addr_attr(0x0120, 0x100068)
        + struct.pack("<HI", 0x0100 | 0x6, 0),
    )
    variable = _die(
        0x0007,
        _string_attr(0x0030, "gvar") + struct.pack("<HH", 0x0020 | 0x3, 5) + bytes([0x03]) + struct.pack("<I", 0x100108),
    )
    line = struct.pack("<II", 18, 0x100060) + struct.pack("<IHI", 12, 0, 0)
    return unit + variable, line


def write_elf(path: Path) -> Path:
    """A minimal little-endian ELF32 MIPS image with the sections the producer reads."""

    main, relocations = _image()
    debug, line = _debug()
    return _write_image(path, SYMBOLS, main, relocations, debug, line)


def _write_image(
    path: Path,
    symbols: list[tuple[str, int, int, int, int]],
    main: bytes,
    relocations: list[tuple[int, int, int]] = (),
    debug: bytes = b"",
    line: bytes = b"",
) -> Path:
    first_global = 1 + sum(1 for row in symbols if row[3] == 0)
    strtab, name_offsets = _strings([row[0] for row in symbols])
    symtab = struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)
    for name, value, size, binding, kind in symbols:
        symtab += struct.pack("<IIIBBH", name_offsets[name], value, size, (binding << 4) | kind, 0, 4)
    relmain = b"".join(struct.pack("<II", offset, (symbol << 8) | kind) for offset, symbol, kind in relocations)
    reginfo = bytes(20) + struct.pack("<I", 0x108000)
    names = ["", ".shstrtab", ".strtab", ".symtab", "main", ".relmain", ".debug", ".line", ".reginfo"]
    shstrtab, section_offsets = _strings(names[1:])
    # (name, type, flags, address, data, link, info, entry size)
    sections = [
        ("", 0, 0, 0, b"", 0, 0, 0),
        (".shstrtab", 3, 0, 0, shstrtab, 0, 0, 0),
        (".strtab", 3, 0, 0, strtab, 0, 0, 0),
        (".symtab", 2, 0, 0, symtab, 2, first_global, 16),
        ("main", 1, 7, BASE, main, 0, 0, 0),
        (".relmain", 9, 0, 0, relmain, 3, 4, 8),
        (".debug", 1, 0, 0, debug, 0, 0, 0),
        (".line", 1, 0, 0, line, 0, 0, 0),
        (".reginfo", 1, 0, 0, reginfo, 0, 0, 0),
    ]
    header_size, program_size = 52, 32
    offset = header_size + program_size
    body = b""
    placed = []
    for name, kind, flags, address, data, link, info, entry in sections:
        while (offset + len(body)) % 16:
            body += b"\0"
        placed.append((offset + len(body) if data else 0, len(data)))
        body += data
    section_offset = offset + len(body)
    while section_offset % 4:
        body += b"\0"
        section_offset += 1
    headers = b""
    for (name, kind, flags, address, data, link, info, entry), (data_offset, size) in zip(sections, placed):
        headers += struct.pack(
            "<IIIIIIIIII", section_offsets[name], kind, flags, address, data_offset, size, link, info, 4, entry
        )
    main_offset = placed[4][0]
    ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + bytes(8)
    header = ident + struct.pack(
        "<HHIIIIIHHHHHH", 2, 8, 1, BASE, header_size, section_offset, 0, header_size, program_size, 1, 40, len(sections), 1
    )
    program = struct.pack("<IIIIIIII", 1, main_offset, BASE, BASE, len(main), len(main), 7, 16)
    path.write_bytes(header + program + body + headers)
    return path


@pytest.fixture()
def synthetic(tmp_path: Path) -> dict:
    return build_source_graph(write_elf(tmp_path / "synthetic.elf"))


def _rows(graph: dict) -> dict[str, dict]:
    return {row["id"]: row for row in graph["artifacts"]}


def _primary(row: dict) -> tuple[str, str] | None:
    return (row["tu_candidates"][0]["tu"], row["tu_candidates"][0]["strength"]) if row["tu_candidates"] else None


def test_artifacts_are_sized_symbols_plus_section_gaps(synthetic: dict) -> None:
    rows = _rows(synthetic)
    assert synthetic["kind"] == SOURCE_GRAPH_KIND
    assert synthetic["summary"]["artifact_counts"] == {"data": 4, "function": 9, "gap": 6}
    assert [row["address"] for row in synthetic["artifacts"]] == sorted(
        (row["address"] for row in synthetic["artifacts"]), key=lambda value: int(value, 16)
    )
    padding = rows["socom:gap:0x100018"]
    assert padding["padding"] and padding["fill"] == "zero"
    assert padding["classification"]["candidate"] == "compiler-generated"
    # The gap after gvar is split where the GNU object's .rodata input section starts.
    assert rows["socom:gap:0x10010c"]["padding"] and rows["socom:gap:0x10010c"]["end"] == "0x100110"
    gnu_string = rows["socom:gap:0x100110"]
    assert gnu_string["fill"] == "nonzero" and not gnu_string["padding"]
    names = rows["socom:function:0x100000"]["names"]
    assert names[0]["name"] == "a_first" and names[0]["symbol_id"].startswith("socom:symbol:")
    assert rows["socom:function:0x100048"]["input_section"] == {"name": ".text", "basis": "section-symbol envelope"}
    assert [window["kind"] for window in synthetic["windows"]] == ["code", "data", "code", "data"]


def test_unit_signals_cluster_and_propagate(synthetic: dict) -> None:
    rows = _rows(synthetic)
    literal = rows["socom:data:0x100100"]
    string = next(item for item in literal["signals"] if item["signal"] == "file-string")
    assert string["tu"] == "a.cpp" and string["literal"]
    assert string["referenced_by"] == ["socom:function:0x100000", "socom:function:0x100020"]
    # Relocations against LOCAL symbols and the symtab's LOCAL order tie
    # the functions, the static, and the static-init pair to one unit.
    for address in ("0x100000", "0x100020", "0x100038"):
        assert _primary(rows[f"socom:function:{address}"]) == ("a.cpp", "strong")
    assert _primary(rows["socom:function:0x100140"]) == ("a.cpp", "strong")
    assert rows["socom:function:0x100140"]["tu_candidates"][0]["sinit_order"] == 1
    assert synthetic["summary"]["cluster_edges"]["symtab-local-order"] >= 1
    # A function between two members of one cluster joins it, as medium.
    middle = rows["socom:function:0x100010"]
    assert _primary(middle) == ("a.cpp", "medium")
    assert "text-contiguity" in middle["tu_candidates"][0]["via"]
    assert _primary(rows["socom:function:0x100040"]) == ("b.cpp", "strong")
    run = rows["socom:function:0x100060"]
    cu = next(item for item in run["signals"] if item["signal"] == "dwarf-cu")
    assert cu["tu"] == "c.cpp" and cu["line"] == {"stmt_list": 0, "first": 12, "last": 12, "entries": 1}
    variable = next(item for item in rows["socom:data:0x100108"]["signals"] if item["signal"] == "dwarf-variable")
    assert variable["strength"] == "weak" and variable["tu"] == "c.cpp"
    assert synthetic["contradictions"] == []


def test_gnu_objects_and_classification_candidates(synthetic: dict) -> None:
    rows = _rows(synthetic)
    (gnu,) = synthetic["gnu_objects"]
    assert gnu["address"] == "0x100048" and gnu["gcc_compiled"]
    assert gnu["functions"] == ["socom:function:0x100048", "socom:function:0x100058"]
    assert gnu["end_basis"].startswith("first Metrowerks-evidence function")
    assert gnu["library"] == "SCE" and "libfoo" in gnu["library_basis"]
    for address in ("0x100048", "0x100058"):
        verdict = rows[f"socom:function:{address}"]["classification"]
        assert (verdict["candidate"], verdict["library"]) == ("provider", "SCE")
        assert verdict["evidence"][0].startswith("GNU object at 0x100048")
    assert rows["socom:data:0x100120"]["classification"]["library"] == "SCE"
    assert rows["socom:function:0x100000"]["classification"]["candidate"] == "authored"
    run = rows["socom:function:0x100060"]["classification"]
    assert run["candidate"] == "authored" and "Z:\\dev\\x\\c.cpp" in run["evidence"][0]
    for identity in ("socom:data:0x100100", "socom:data:0x100148", "socom:function:0x100140"):
        assert rows[identity]["classification"]["candidate"] == "compiler-generated"
    # Original provider paths, without their drive prefix.
    assert path_library(r"\usr\local\sce_2.5.1\EE\lib\crt0.s") == ("provider", "crt0")
    assert path_library(r"\apps\cw301\PS2 Support\Msl\MSL_C++\MSL_Common\Src\ios.cpp") == ("provider", "MSL")
    assert path_library(r"\apps\cw301\PS2 Support\gcc_wrapper.c") == ("provider", "MW runtime")
    assert path_library(r"\dev\libpttclient\decode.c") == ("provider", "libptt")
    assert path_library(r"Z:\dev\Apps\FTS\main.cpp") == ("authored", None)


def test_code_window_opens_at_the_code_input_section_after_a_marker(tmp_path: Path) -> None:
    # A linker-style 1-byte OBJECT marker (``_textStart``) and its fill sit
    # before the first code input section; the code run, and its first
    # segment, start at that section symbol, never at the odd marker end.
    symbols = [
        (".text", 0x100018, 0x10, 0, 3),
        ("mfifoBase", 0x100000, 0x10, 1, 1),
        ("_textStart", 0x100010, 1, 1, 1),
        ("_start", 0x100018, 0, 1, 0),
        ("first", 0x100028, 8, 1, 2),
    ]
    main = bytearray(0x30)
    for address in (0x100018, 0x100020, 0x100028):
        struct.pack_into("<II", main, address - BASE, JR_RA, NOP)
    graph = build_source_graph(_write_image(tmp_path / "marker.elf", symbols, bytes(main)))
    rows = _rows(graph)
    fill, crt = rows["socom:gap:0x100011"], rows["socom:gap:0x100018"]
    assert (fill["end"], fill["padding"], fill["classification"]["candidate"]) == ("0x100018", True, "compiler-generated")
    assert (crt["end"], crt["labels"], crt["input_section"]["name"]) == ("0x100028", ["_start"], ".text")
    assert [(row["kind"], row["start"], row["end"]) for row in graph["windows"]] == [
        ("data", "0x100000", "0x100018"),
        ("code", "0x100018", "0x100030"),
    ]
    assert fill["window"] == "socom:window:0x100000" and crt["window"] == "socom:window:0x100018"
    assert [(row["start"], row["end"]) for row in graph["segments"]] == [("0x100018", "0x100030")]
    code = {row["id"] for row in graph["windows"] if row["kind"] == "code"}
    assert all(int(row["address"], 16) % 4 == 0 for row in graph["artifacts"] if row["window"] in code)


def test_newlib_system_call_stubs_cast_no_library_vote(tmp_path: Path) -> None:
    # The SCE kernel's newlib glue defines the bare system calls newlib
    # leaves to the platform; only newlib's own ``_<name>_r`` wrappers vote
    # newlib, so the glue object is SCE by its one SCE name.
    symbols = [
        (".text", 0x100000, 0, 0, 3),
        ("gcc2_compiled.", 0x100000, 0, 0, 0),
        (".text", 0x100028, 0, 0, 3),
        ("gcc2_compiled.", 0x100028, 0, 0, 0),
        ("sceTtyInit", 0x100000, 8, 1, 2),
        ("lseek", 0x100008, 8, 1, 2),
        ("sbrk", 0x100010, 8, 1, 2),
        ("isatty", 0x100018, 8, 1, 2),
        ("fstat", 0x100020, 8, 1, 2),
        ("_lseek_r", 0x100028, 8, 1, 2),
        ("_sbrk_r", 0x100030, 8, 1, 2),
    ]
    main = bytearray(0x38)
    for address in range(0x100000, 0x100038, 8):
        struct.pack_into("<II", main, address - BASE, JR_RA, NOP)
    graph = build_source_graph(_write_image(tmp_path / "glue.elf", symbols, bytes(main)))
    glue, wrappers = graph["gnu_objects"]
    assert (glue["library"], glue["library_basis"]) == ("SCE", "function names (1 of 1 matches)")
    assert (wrappers["library"], wrappers["library_basis"]) == ("newlib", "function names (2 of 2 matches)")
    rows = _rows(graph)
    for address in ("0x100000", "0x100008", "0x100020"):
        assert rows[f"socom:function:{address}"]["classification"]["library"] == "SCE"
    assert {"fstat", "isatty", "lseek", "sbrk"} <= set(graph["rules"]["gnu_vote_neutral_names"])


def test_segments_cut_at_classification_changes_and_respect_the_size(tmp_path: Path) -> None:
    path = write_elf(tmp_path / "synthetic.elf")
    graph = build_source_graph(path)
    spans = [(row["start"], row["end"], row["function_count"]) for row in graph["segments"]]
    assert spans == [
        ("0x100000", "0x100048", 5),
        ("0x100048", "0x100060", 2),
        ("0x100060", "0x100068", 1),
        ("0x100130", "0x100148", 1),
    ]
    first, gnu = graph["segments"][0], graph["segments"][1]
    assert first["boundary"]["start"]["strength"] == "window edge"
    assert first["boundary"]["end"]["strength"] == "hard"
    assert first["classification_mix"] == {"authored": 5}
    assert [row["tu"] for row in first["tu_candidates"]] == ["a.cpp", "b.cpp"]
    assert "socom:data:0x100100" in first["data"]
    assert {"socom:data:0x100120", "socom:gap:0x100110"} <= set(gnu["data"])
    small = build_source_graph(path, segment_size=3)
    assert [row["function_count"] for row in small["segments"]] == [3, 2, 2, 1, 1]
    assert small["segments"][0]["boundary"]["end"]["strength"] == "weak"
    covered = [identity for row in small["segments"] for identity in row["artifacts"] if identity.startswith("socom:function:")]
    assert len(covered) == len(set(covered)) == 9
    with pytest.raises(SocomError, match="segment size"):
        build_source_graph(path, segment_size=0)


def _archive_image(tmp_path: Path) -> dict:
    """GNU archive members: libgcc, a GOFAST dptofp, SCE, lgAud around an RSA-coupled object, RSA.

    LOCAL blocks in symbol order: __muldi3, dptofp, a data-only ``.rodata``
    block (__thenan_df), sceFoo (with its .rodata, opened by the
    unreferenced ``sce_const``), lgAudOpen, SidInit (12 bytes: its last word
    is the object's alignment padding), lgAudClose, and the RSA object
    (with its .rodata).
    """

    symbols = [
        (".text", 0x100000, 0, 0, 3), ("gcc2_compiled.", 0x100000, 0, 0, 0),
        (".text", 0x100010, 0, 0, 3), ("gcc2_compiled.", 0x100010, 0, 0, 0),
        (".rodata", 0x100090, 0, 0, 3),
        (".rodata", 0x100098, 0, 0, 3), (".text", 0x100020, 0, 0, 3), ("gcc2_compiled.", 0x100020, 0, 0, 0),
        (".text", 0x100030, 0, 0, 3), ("gcc2_compiled.", 0x100030, 0, 0, 0),
        (".text", 0x100040, 0, 0, 3), ("gcc2_compiled.", 0x100040, 0, 0, 0),
        (".text", 0x100050, 0, 0, 3), ("gcc2_compiled.", 0x100050, 0, 0, 0),
        (".rodata", 0x1000a0, 0, 0, 3), (".text", 0x100060, 0, 0, 3), ("gcc2_compiled.", 0x100060, 0, 0, 0),
        ("__muldi3", 0x100000, 16, 1, 2),
        ("dptofp", 0x100010, 16, 1, 2),
        ("sceFoo", 0x100020, 16, 1, 2),
        ("lgAudOpen", 0x100030, 16, 1, 2),
        ("SidInit", 0x100040, 12, 1, 2),
        ("lgAudClose", 0x100050, 16, 1, 2),
        ("RSAEncrypt", 0x100060, 16, 1, 2),
        ("RSADecrypt", 0x100070, 16, 1, 2),
        ("RSAHelper", 0x100080, 16, 1, 2),
        ("__thenan_df", 0x100090, 8, 1, 1),
        ("tail", 0x1000a8, 8, 1, 1),
        ("sce_const", 0x100098, 4, 1, 1),
    ]
    index = {row[0]: number + 1 for number, row in reversed(list(enumerate(symbols)))}
    rodata = [1 + number for number, row in enumerate(symbols) if row[0] == ".rodata"]
    main = bytearray(0xB0)

    def code(address: int, *values: int) -> None:
        for number, value in enumerate(values):
            struct.pack_into("<I", main, address - BASE + 4 * number, value)

    code(0x100000, _lui(A0, 0x10), _addiu(A0, A0, 0x90), JR_RA, NOP)  # __muldi3 -> __thenan_df
    code(0x100010, JR_RA, NOP, NOP, NOP)
    code(0x100020, _lui(A0, 0x10), _addiu(A0, A0, 0x9C), JR_RA, NOP)  # sceFoo -> its .rodata after sce_const
    code(0x100030, JR_RA, NOP, NOP, NOP)
    code(0x100040, _jal(0x100080), NOP, JR_RA, NOP)  # SidInit -> RSAHelper
    code(0x100050, JR_RA, NOP, NOP, NOP)
    code(0x100060, _jal(0x100040), NOP, JR_RA, NOP)  # RSAEncrypt -> SidInit
    code(0x100070, _jal(0x100040), NOP, JR_RA, NOP)  # RSADecrypt -> SidInit
    code(0x100080, _lui(A0, 0x10), _addiu(A0, A0, 0xA0), JR_RA, NOP)  # RSAHelper -> its .rodata
    main[0x90:0xB0] = b"N" * 0x20
    relocations = [
        (0x100000, index["__thenan_df"], 5), (0x100004, index["__thenan_df"], 6),
        (0x100020, rodata[1], 5), (0x100024, rodata[1], 6),
        (0x100040, index["RSAHelper"], 4),
        (0x100060, index["SidInit"], 4), (0x100070, index["SidInit"], 4),
        (0x100080, rodata[2], 5), (0x100084, rodata[2], 6),
    ]
    return build_source_graph(_write_image(tmp_path / "archive.elf", symbols, bytes(main), relocations))


def test_member_rules_coupling_and_data_only_members_keep_the_segment_cuts(tmp_path: Path) -> None:
    from tools._socom.source_plan import planning_scopes

    graph = _archive_image(tmp_path)
    rows = _rows(graph)
    objects = {row["address"]: row for row in graph["gnu_objects"]}
    # GOFAST dptofp is libgcc's by a member rule; the segment cut keeps the base rules.
    gofast = objects["0x100010"]
    assert (gofast["library"], gofast["segment_library"]) == ("libgcc", None)
    # SidInit lies between lgAud objects but only RSA calls it, and it calls RSA.
    sid = objects["0x100040"]
    assert (sid["library"], sid["segment_library"]) == ("RSA", "lgAud")
    assert sid["library_basis"].startswith("coupling: referenced only by RSA objects (2 artifacts")
    assert graph["rules"]["coupling_moves"] == [
        {"address": "0x100040", "from": "lgAud", "from_basis": "archive-contiguity", "to": "RSA", "referrers": 2}
    ]
    assert rows["socom:function:0x100040"]["classification"]["library"] == "RSA"
    # The .rodata block between dptofp's and sceFoo's LOCAL blocks is a data-only member.
    member = objects["0x100090"]
    assert member["data_only"] and member["data"] == ["socom:data:0x100090"] and member["functions"] == []
    assert (member["library"], member["library_basis"]) == ("libgcc", "referenced only by libgcc objects (1 functions)")
    assert member["sections"] == [
        {"name": ".rodata", "symbol_index": 5, "start": "0x100090", "end": "0x100098", "end_basis": "next section symbol"}
    ]
    assert rows["socom:data:0x100090"]["gnu_object"] == "0x100090"
    assert graph["summary"]["data_only_member_count"] == 1
    # One gap spanned two objects' .rodata: it is split at the second section symbol.
    assert {"socom:gap:0x10009c", "socom:gap:0x1000a0"} <= set(rows)
    assert rows["socom:gap:0x10009c"]["end"] == "0x1000a0"
    assert objects["0x100020"]["sections"] == [
        {"name": ".rodata", "symbol_index": 6, "start": "0x100098", "end": "0x1000a0", "end_basis": "next section symbol"}
    ]
    # Its unreferenced, otherwise unclassified sce_const lies in that run,
    # which reaches the next input section: it is sceFoo's, in its slice.
    const = rows["socom:data:0x100098"]["classification"]
    assert (const["candidate"], const["library"], const.get("weak")) == ("provider", "SCE", None)
    assert const["evidence"][0].startswith("unreferenced datum inside GNU object at 0x100020's .rodata section run")
    assert "socom:data:0x100098" in graph["segments"][2]["data"]
    # The moved SidInit's alignment padding moves with it.
    padding = rows["socom:gap:0x10004c"]
    assert padding["padding"] and "gnu_object" not in padding
    assert (padding["classification"]["candidate"], padding["classification"]["library"]) == ("provider", "RSA")
    # Five segments as under the base rules; the refined classification only
    # moves artifacts between provider scopes.
    segments = graph["segments"]
    assert [segment["classification_mix"] for segment in segments] == [
        {"provider:libgcc": 1}, {"provider:libgcc": 1}, {"provider:SCE": 1},
        {"provider:RSA": 1, "provider:lgAud": 2}, {"provider:RSA": 3},
    ]
    assert segments[1]["cut_classification_mix"] == {"provider:unidentified GNU object": 1}
    assert segments[3]["cut_classification_mix"] == {"provider:lgAud": 3}
    scopes = {entry["scope"]["library"]: entry for entry in planning_scopes(graph) if entry["scope"]["kind"] == "provider"}
    assert [segment["segment_number"] for segment in scopes["libgcc"]["segments"]] == [1, 2]
    assert "socom:function:0x100040" in scopes["RSA"]["artifacts"] and scopes["RSA"]["moved_from"] == [4]
    assert "socom:function:0x100040" not in scopes["lgAud"]["artifacts"]
    assert "socom:gap:0x10004c" in scopes["RSA"]["artifacts"] and "socom:gap:0x10004c" not in scopes["lgAud"]["artifacts"]


def test_section_runs_end_at_the_fill_change_and_the_common_tail(tmp_path: Path) -> None:
    from tools._socom.source_cache import ensure_source_cache, query

    # One GNU object with .sdata (a_flag) and .bss (labelled a_buf).  The
    # file bytes end at 0x100030: a Metrowerks-like zero-fill datum follows
    # .sdata, and the GLOBAL c_one/c_two after the last input section are
    # COMMON allocations.
    symbols = [
        (".text", 0x100000, 0, 0, 3), ("gcc2_compiled.", 0x100000, 0, 0, 0),
        (".sdata", 0x100020, 0, 0, 3), (".bss", 0x100040, 0, 0, 3),
        ("a_flag", 0x100020, 4, 0, 1), ("a_buf", 0x100044, 0, 0, 0),
        ("sceInit", 0x100000, 16, 1, 2),
        ("mw_count", 0x100030, 4, 1, 1),
        ("c_one", 0x100050, 4, 1, 1),
        ("c_two", 0x100058, 8, 1, 1),
    ]
    main = bytearray(0x30)
    for number, value in enumerate((_lui(A0, 0x10), _addiu(A0, A0, 0x20), _lui(A0, 0x10), _addiu(A0, A0, 0x40))):
        struct.pack_into("<I", main, 4 * number, value)
    relocations = [(0x100000, 3, 5), (0x100004, 3, 6), (0x100008, 4, 5), (0x10000C, 4, 6)]
    (tmp_path / "support").mkdir()
    elf = _write_image(tmp_path / "support" / "socom.elf", symbols, bytes(main), relocations)
    graph = build_source_graph(elf)
    rows = _rows(graph)
    (gnu,) = graph["gnu_objects"]
    assert gnu["sections"] == [
        {"name": ".sdata", "symbol_index": 3, "start": "0x100020", "end": "0x100030", "end_basis": "file bytes end at socom:data:0x100030"},
        {"name": ".bss", "symbol_index": 4, "start": "0x100040", "end": "0x100050", "end_basis": "COMMON allocation socom:data:0x100050"},
    ]
    assert [identity for identity, row in rows.items() if row.get("common")] == ["socom:data:0x100050", "socom:data:0x100058"]
    common = next(item for item in rows["socom:data:0x100050"]["signals"] if item["signal"] == "common")
    assert common == {"signal": "common", "strength": "hint", "tail": ["socom:data:0x100050", "socom:data:0x100058"], "count": 2}
    # The tag changes neither the classification nor the slice.
    assert rows["socom:data:0x100050"]["classification"]["candidate"] == "unknown"
    assert "common" not in rows["socom:data:0x100030"] and graph["summary"]["common_allocations"] == 2
    path, _rebuilt = ensure_source_cache(tmp_path, graph=graph)
    assert query(path, "SELECT id FROM artifacts WHERE common = 1 ORDER BY address")["rows"] == [
        ["socom:data:0x100050"], ["socom:data:0x100058"],
    ]
    assert query(path, "SELECT name, end_basis, room_for_member FROM object_sections ORDER BY start")["rows"] == [
        [".sdata", "file bytes end at socom:data:0x100030", 1], [".bss", "COMMON allocation socom:data:0x100050", 1],
    ]


def test_a_leading_local_block_opens_its_objects_section_runs(tmp_path: Path) -> None:
    # Like newlib's locale.o: its .data section symbol and last_lc_ctype
    # precede its .text symbol, between the previous object's block and its
    # own; its .data holds the object's lc_ctype.  The block's section opens
    # the object's .data run; the block's datum keeps its own cluster.
    symbols = [
        (".text", 0x100000, 0, 0, 3), ("gcc2_compiled.", 0x100000, 0, 0, 0),
        (".data", 0x100060, 0, 0, 3), ("last_ctype", 0x100068, 4, 0, 1),
        (".text", 0x100010, 0, 0, 3), ("lc_ctype", 0x100064, 4, 0, 1), ("gcc2_compiled.", 0x100010, 0, 0, 0),
        ("sceAlpha", 0x100000, 16, 1, 2),
        ("sceBeta", 0x100010, 16, 1, 2),
        ("mb_max", 0x100060, 4, 1, 1),
    ]
    main = bytearray(0x70)
    for address in (0x100000, 0x100008, 0x100010, 0x100018):
        struct.pack_into("<II", main, address - BASE, JR_RA, NOP)
    graph = build_source_graph(_write_image(tmp_path / "block.elf", symbols, bytes(main)))
    rows = _rows(graph)
    objects = {row["address"]: row for row in graph["gnu_objects"]}
    assert set(objects) == {"0x100000", "0x100010"}
    beta = objects["0x100010"]
    assert beta["attached_blocks"] == [{"local_symbols": [3, 4], "sections": [3]}]
    assert beta["sections"] == [
        {"name": ".data", "symbol_index": 3, "start": "0x100060", "end": "0x10006c", "end_basis": "window end"}
    ]
    assert rows["socom:data:0x100064"]["cluster"] == "socom:tu-cluster:0x100010"
    assert rows["socom:data:0x100068"]["cluster"] is None and "attached_blocks" not in objects["0x100000"]


def test_graph_is_deterministic_and_hashes_its_content(tmp_path: Path) -> None:
    from tools._socom.util import canonical_json
    import hashlib

    path = write_elf(tmp_path / "synthetic.elf")
    first, second = build_source_graph(path), build_source_graph(path)
    assert canonical_json(first) == canonical_json(second)
    body = {key: value for key, value in first.items() if key != "graph_sha256"}
    assert first["graph_sha256"] == hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    markdown = segments_markdown(first)
    assert first["graph_sha256"] in markdown and "| 1 | 0x100000-0x100048 | 5 |" in markdown


def test_cli_writes_only_under_build_and_requires_the_reference(tmp_path: Path, capsys) -> None:
    (tmp_path / "support").mkdir()
    write_elf(tmp_path / "support" / "socom.elf")
    assert cli.main(["--root", str(tmp_path), "source", "graph", "--output", "elsewhere/graph.json"]) == 2
    assert "only be written under build/" in json.loads(capsys.readouterr().out)["error"]
    assert cli.main(["--root", str(tmp_path), "source", "graph", "--output", "build/source-graph/graph.json"]) == 2
    assert "pinned reference SHA-256" in json.loads(capsys.readouterr().out)["error"]
    assert not (tmp_path / "build").exists()


# -- the reference ELF ---------------------------------------------------------


@pytest.fixture(scope="module")
def reference_graph(reference_source_graph: dict) -> dict:
    return reference_source_graph


def test_reference_graph_covers_the_census_artifacts(reference_graph: dict, census: dict) -> None:
    graph = reference_graph
    assert graph["source_sha256"] == REFERENCE_SHA256
    sized = {
        (("function" if row["type"] == "FUNC" else "data"), row["value"])
        for row in census["symbols"]
        if row["type"] in ("FUNC", "OBJECT") and row["size"]
    }
    rows = [row for row in graph["artifacts"] if row["kind"] != "gap"]
    assert {(row["kind"], int(row["address"], 16)) for row in rows} == sized
    assert graph["summary"]["artifact_counts"]["function"] == 9703
    functions = [identity for segment in graph["segments"] for identity in segment["artifacts"] if identity.startswith("socom:function:")]
    assert len(functions) == len(set(functions)) == 9703
    assert all(segment["function_count"] <= graph["segment_size"] for segment in graph["segments"])
    for segment in graph["segments"]:
        # Cut at every change of the segmentation classification (member
        # refinements may leave a second provider family in the mix).
        cut = segment.get("cut_classification_mix") or segment["classification_mix"]
        assert len({key for key in cut if key not in ("compiler-generated", "unknown")}) <= 1
    # Every static-init unit has its table word and its function.
    sinit = [row for row in graph["units"] if row["sinit_order"] is not None]
    assert sorted(row["sinit_order"] for row in sinit) == list(range(1, 149))
    assert graph["contradictions"] == []
    summary = graph["summary"]
    assert summary["functions_without_tu_anchor"] == sum(summary["functions_without_tu_anchor_by_class"].values())


def test_reference_code_starts_at_instruction_addresses_and_kernel_glue_is_sce(reference_graph: dict) -> None:
    graph = reference_graph
    code = {row["id"] for row in graph["windows"] if row["kind"] == "code"}
    assert all(int(row["address"], 16) % 4 == 0 for row in graph["artifacts"] if row["window"] in code)
    assert all(int(row["start"], 16) % 4 == 0 == int(row["end"], 16) % 4 for row in graph["segments"])
    # crt0's .text input section, after the 1-byte _textStart marker.
    assert graph["segments"][0]["start"] == "0x140008"
    glue = next(row for row in graph["gnu_objects"] if row["address"] == "0x15b9a0")
    assert glue["library"] == "SCE"


def test_reference_graph_is_deterministic(root: Path, reference_graph: dict) -> None:
    assert source_graph(root)["graph_sha256"] == reference_graph["graph_sha256"]


def test_reference_runtime_msl_boundary_follows_relocations(reference_graph: dict) -> None:
    # MSL's inline ~ios_base::failure and ~locale (binding 13, no DWARF) lead
    # MSL's text before ios.cpp's first compile unit (0x1449b0): their
    # relocations reach only MSL provider code, so the MW runtime -> MSL
    # boundary is 0x1448d0, not the compile unit's low_pc.
    rows = _rows(reference_graph)
    for address in ("0x1448d0", "0x144950"):
        verdict = rows[f"socom:function:{address}"]["classification"]
        assert (verdict["candidate"], verdict["library"], verdict.get("weak")) == ("provider", "MSL", True)
        assert verdict["evidence"][0].startswith("relocations reach only MSL provider code")
    spans = {(row["start"], row["end"]) for row in reference_graph["segments"]}
    assert ("0x142140", "0x1448c8") in spans
    assert any(start == "0x1448d0" for start, _end in spans)
    assert reference_graph["summary"]["classification"]["function"]["unknown"] == 1


def test_reference_literal_runs_stop_at_object_boundaries(reference_graph: dict) -> None:
    # The @N run from 0x4445d0 (MW runtime members) used to cross MSL's
    # ios.cpp object at 0x444808 and give its literals ios.cpp.
    rows = _rows(reference_graph)
    for address in ("0x4445d0", "0x444660", "0x4447f8"):
        assert not any(row["tu"] == "ios.cpp" for row in rows[f"socom:data:{address}"]["tu_candidates"])
    assert _primary(rows["socom:data:0x444808"]) == ("ios.cpp", "strong")
    assert reference_graph["summary"]["literal_pool_conflicts"] == 0


def test_reference_crt0_object_is_its_gap(reference_graph: dict) -> None:
    rows = _rows(reference_graph)
    crt0 = next(row for row in reference_graph["gnu_objects"] if row["address"] == "0x140008")
    assert crt0["functions"] == [] and crt0["gaps"] == ["socom:gap:0x140008"]
    assert crt0["library"] == "crt0" and crt0["library_basis"].startswith("DWARF path ")
    gap = rows["socom:gap:0x140008"]
    assert gap["gnu_object"] == "0x140008" and gap["classification"]["library"] == "crt0"


def test_reference_member_rules_coupling_and_data_only_members(reference_graph: dict) -> None:
    graph = reference_graph
    objects = {row["address"]: row for row in graph["gnu_objects"]}
    # The Sid object is speech middleware (callers gsapi_*/StartListening/
    # StopListening/ProcessAudio, calls heap_Alloc/heap_Free), not lgAud.
    sid = objects["0x3b7248"]
    assert (sid["library"], sid["segment_library"]) == ("speech middleware", "lgAud")
    assert [(row["address"], row["from"], row["to"]) for row in graph["rules"]["coupling_moves"]] == [
        ("0x3aae18", None, "Medius"), ("0x3b7248", "lgAud", "speech middleware"),
    ]
    # libgcc's GOFAST _df_to_sf.o and _df_to_usi.o.
    for address in ("0x16e398", "0x16e3f0"):
        assert (objects[address]["library"], objects[address]["segment_library"]) == ("libgcc", None)
    # Data-only members from their LOCAL section-symbol blocks.
    members = {address: row["library"] for address, row in objects.items() if row.get("data_only")}
    assert {address: members.get(address) for address in ("0x43bc88", "0x466cc0", "0x447c00", "0x448090")} == {
        "0x43bc88": "newlib", "0x466cc0": "newlib", "0x447c00": "newlib", "0x448090": "libgcc",
    }
    assert objects["0x43bc88"]["data"] == ["socom:data:0x43bc88", "socom:data:0x43bf74"]
    # Gaps split where an input section starts: puts.o's and strtod.o's .rodata.
    rows = _rows(graph)
    assert rows["socom:gap:0x466fa0"]["end"] == "0x466fb0" and "socom:gap:0x466fb0" in rows
    assert rows["socom:gap:0x466c89"]["end"] == "0x466c90"
    # The segmentation is unchanged: 76 segments, the lgAud segment keeps the Sid functions.
    assert len(graph["segments"]) == 76
    lgaud = graph["segments"][61]
    assert lgaud["cut_classification_mix"] == {"provider:lgAud": 39}
    assert lgaud["classification_mix"] == {"provider:lgAud": 25, "provider:speech middleware": 14}


def test_reference_section_runs_common_tail_and_object_padding(reference_graph: dict) -> None:
    graph = reference_graph
    rows = _rows(graph)
    objects = {row["address"]: row for row in graph["gnu_objects"]}
    runs = {run["symbol_index"]: run for run in objects["0x425ea0"]["sections"]}
    # SCE's .sdata ends where the file bytes end (.sbss: the CAiPath guard,
    # MSL's ninit_cnt_s/winit_cnt_s); its .bss before the COMMON tail.
    assert (runs[11798]["end"], runs[11798]["end_basis"]) == ("0x475600", "file bytes end at socom:data:0x475600")
    assert (runs[11800]["end"], runs[11800]["end_basis"]) == ("0x5b17c0", "COMMON allocation socom:data:0x5b17c0")
    common = [row for row in graph["artifacts"] if row.get("common")]
    assert len(common) == graph["summary"]["common_allocations"] == 250
    assert (common[0]["address"], common[-1]["address"]) == ("0x5b17c0", "0x5e7e94")
    assert rows["socom:data:0x5b1aa4"].get("common") and rows["socom:data:0x5b1aa4"]["names"][0]["name"] == "errno"
    # locale.o's .data section symbol precedes its .text symbol.
    locale = objects["0x3e1a70"]
    assert locale["attached_blocks"] == [{"local_symbols": [10768, 10769], "sections": [10768]}]
    data = next(run for run in locale["sections"] if run["symbol_index"] == 10768)
    assert (data["start"], data["end"], data["end_basis"]) == ("0x43bf78", "0x43bf90", "next section symbol")
    # Medius's unreferenced RT_MSG_CLIENT_MAX_AGGREGATION_LEN lies in its object's .rodata run.
    verdict = rows["socom:data:0x468af2"]["classification"]
    assert (verdict["candidate"], verdict["library"]) == ("provider", "Medius")
    assert "socom:data:0x468af2" in graph["segments"][70]["data"]
    # The Sid object's padding is speech middleware's, like its functions.
    for address in ("0x3b7284", "0x3b751c", "0x3b760c", "0x3b76ec", "0x3b778c", "0x3b77ac", "0x3b7818"):
        verdict = rows[f"socom:gap:{address}"]["classification"]
        assert (verdict["candidate"], verdict["library"]) == ("provider", "speech middleware")


def test_reference_segments_report_internal_unit_boundaries(reference_graph: dict) -> None:
    # zAnimQuadAlignTick sits unanchored between zanim_cmd_tick.cpp and
    # zanim_load.cpp inside one segment.
    found = [
        row
        for segment in reference_graph["segments"]
        for row in segment["internal_boundaries"]
        if "socom:function:0x1bfe80" in row["unanchored"]
    ]
    assert len(found) == 1
    assert (found[0]["after"], found[0]["before"]) == ("zanim_cmd_tick.cpp", "zanim_load.cpp")
    assert (found[0]["last_anchor"], found[0]["next_anchor"]) == ("socom:function:0x1bfd90", "socom:function:0x1bfe90")
    summary = reference_graph["summary"]
    assert summary["internal_boundary_count"] == sum(len(row["internal_boundaries"]) for row in reference_graph["segments"])
