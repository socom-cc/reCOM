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
FIRST_GLOBAL = 11  # null symbol plus ten locals


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
    strtab, name_offsets = _strings([row[0] for row in SYMBOLS])
    symtab = struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)
    for name, value, size, binding, kind in SYMBOLS:
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
        (".symtab", 2, 0, 0, symtab, 2, FIRST_GLOBAL, 16),
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
    assert synthetic["summary"]["artifact_counts"] == {"data": 4, "function": 9, "gap": 5}
    assert [row["address"] for row in synthetic["artifacts"]] == sorted(
        (row["address"] for row in synthetic["artifacts"]), key=lambda value: int(value, 16)
    )
    padding = rows["socom:gap:0x100018"]
    assert padding["padding"] and padding["fill"] == "zero"
    assert padding["classification"]["candidate"] == "compiler-generated"
    gnu_string = rows["socom:gap:0x10010c"]
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
    assert {"socom:data:0x100120", "socom:gap:0x10010c"} <= set(gnu["data"])
    small = build_source_graph(path, segment_size=3)
    assert [row["function_count"] for row in small["segments"]] == [3, 2, 2, 1, 1]
    assert small["segments"][0]["boundary"]["end"]["strength"] == "weak"
    covered = [identity for row in small["segments"] for identity in row["artifacts"] if identity.startswith("socom:function:")]
    assert len(covered) == len(set(covered)) == 9
    with pytest.raises(SocomError, match="segment size"):
        build_source_graph(path, segment_size=0)


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
def reference_graph(root: Path) -> dict:
    return source_graph(root)


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
        assert len({key for key in segment["classification_mix"] if key not in ("compiler-generated", "unknown")}) <= 1
    # Every static-init unit has its table word and its function.
    sinit = [row for row in graph["units"] if row["sinit_order"] is not None]
    assert sorted(row["sinit_order"] for row in sinit) == list(range(1, 149))
    assert graph["contradictions"] == []
    summary = graph["summary"]
    assert summary["functions_without_tu_anchor"] == sum(summary["functions_without_tu_anchor_by_class"].values())


def test_reference_graph_is_deterministic(root: Path, reference_graph: dict) -> None:
    assert source_graph(root)["graph_sha256"] == reference_graph["graph_sha256"]
