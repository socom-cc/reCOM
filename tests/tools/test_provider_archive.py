"""`provider archive`: a read-only ar/nm listing of provider libraries."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from tools._socom import cli
from tools._socom.provider_archive import archive_report, read_archive, report_text
from tools._socom.util import SocomError


def _strings(names: list[str]) -> tuple[bytes, dict[str, int]]:
    table, offsets = b"\0", {"": 0}
    for name in names:
        if name not in offsets:
            offsets[name] = len(table)
            table += name.encode("latin-1") + b"\0"
    return table, offsets


def relocatable(symbols: list[tuple[str, int, int, int, int, int]], text: bytes = b"\0" * 16) -> bytes:
    """An ELF32 LE MIPS relocatable object: (name, value, size, binding, type, section index) symbols."""

    strtab, offsets = _strings([row[0] for row in symbols])
    symtab = bytes(16) + b"".join(
        struct.pack("<IIIBBH", offsets[name], value, size, (binding << 4) | kind, 0, section)
        for name, value, size, binding, kind, section in symbols
    )
    names = [".text", ".data", ".symtab", ".strtab", ".shstrtab"]
    shstrtab, shoffsets = _strings(names)
    # (name, type, flags, data, link, info, entry size)
    sections = [
        ("", 0, 0, b"", 0, 0, 0),
        (".text", 1, 0x6, text, 0, 0, 0),
        (".data", 1, 0x3, b"\1\2\3\4", 0, 0, 0),
        (".symtab", 2, 0, symtab, 4, 1, 16),
        (".strtab", 3, 0, strtab, 0, 0, 0),
        (".shstrtab", 3, 0, shstrtab, 0, 0, 0),
    ]
    body, placed = b"", []
    for _name, _kind, _flags, data, _link, _info, _entry in sections:
        while (52 + len(body)) % 4:
            body += b"\0"
        placed.append((52 + len(body) if data else 0, len(data)))
        body += data
    while (52 + len(body)) % 4:
        body += b"\0"
    section_offset = 52 + len(body)
    headers = b"".join(
        struct.pack("<IIIIIIIIII", shoffsets[name], kind, flags, 0, offset, size, link, info, 4, entry)
        for (name, kind, flags, _data, link, info, entry), (offset, size) in zip(sections, placed)
    )
    ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + bytes(8)
    header = ident + struct.pack("<HHIIIIIHHHHHH", 1, 8, 1, 0, 0, section_offset, 0, 52, 0, 0, 40, len(sections), 5)
    return header + body + headers


def _member(name: str, data: bytes) -> bytes:
    header = f"{name:<16}{0:<12}{0:<6}{0:<6}{644:<8}{len(data):<10}".encode("latin-1") + b"`\n"
    return header + data + (b"\n" if len(data) % 2 else b"")


def archive(*, long_names: bool) -> bytes:
    first = relocatable([
        ("staticinitializers.c", 0, 0, 0, 4, 0xFFF1),
        (".text", 0, 0, 0, 3, 1),
        ("__init_cpp", 0, 16, 1, 2, 1),
        ("local_table", 0, 4, 0, 1, 2),
        ("__inline_copy", 8, 8, 13, 2, 1),
        ("__sinit_dummy", 0, 0, 1, 0, 0),
    ])
    second = relocatable([("gcc_wrapper.c", 0, 0, 0, 4, 0xFFF1), ("__wrap", 0, 12, 1, 2, 1), ("memcpy", 0, 0, 1, 0, 0)])
    long = "staticinitializers.o"
    members: list[tuple[str, bytes]] = []
    if long_names:
        table = f"{long}/\n".encode("latin-1")
        members.append(("//", table))
        members.append(("/0", first))
    else:
        # A 16-byte header field and no long-name table: the archiver cut the name.
        members.append((long[:16], first))
    members.append(("gcc_wrapper.o/", second))
    # The System V symbol table first: offsets of the member headers.
    names = [b"__init_cpp", b"__wrap"]
    table_size = 4 + 4 * len(names) + sum(len(name) + 1 for name in names)
    offset = 8 + 60 + table_size + (table_size % 2)
    starts = []
    for name, data in members:
        starts.append(offset)
        offset += 60 + len(data) + (len(data) % 2)
    member_starts = [start for (name, _data), start in zip(members, starts) if name != "//"]
    symbols = struct.pack(">I", len(names)) + b"".join(struct.pack(">I", start) for start in member_starts)
    symbols += b"".join(name + b"\0" for name in names)
    return b"!<arch>\n" + _member("/", symbols) + b"".join(_member(name, data) for name, data in members)


@pytest.mark.parametrize("long_names", [True, False])
def test_members_names_sizes_and_symbols(long_names: bool) -> None:
    data = archive(long_names=long_names)
    report = archive_report(data, "LIBTEST.LIB")
    assert report["member_count"] == 2 and report["long_name_table"] is long_names
    assert report["symbol_tables"][0]["kind"] == "sysv" and report["symbol_tables"][0]["symbols"] == 2
    first, second = report["members"]
    if long_names:
        assert (first["name"], first["header_name"], first["name_source"], first["possibly_truncated"]) == (
            "staticinitializers.o", "/0", "long-name-table", False,
        )
    else:
        # The cut header name is listed as is; its source file symbol shows what it stood for.
        assert (first["name"], first["name_source"], first["possibly_truncated"]) == ("staticinitialize", "header", True)
    assert first["files"] == ["staticinitializers.c"]
    assert first["armap_symbols"] == ["__init_cpp"]
    assert first["defined"] == [
        {"name": "__init_cpp", "binding": "GLOBAL", "type": "FUNC", "section": ".text", "value": 0, "size": 16},
        {"name": "local_table", "binding": "LOCAL", "type": "OBJECT", "section": ".data", "value": 0, "size": 4},
        {"name": "__inline_copy", "binding": "13", "type": "FUNC", "section": ".text", "value": 8, "size": 8},
    ]
    assert first["undefined"] == [{"name": "__sinit_dummy", "binding": "GLOBAL"}]
    assert {row["name"]: row["size"] for row in first["sections"]} == {".text": 16, ".data": 4}
    assert (second["name"], second["header_name"], second["possibly_truncated"]) == ("gcc_wrapper.o", "gcc_wrapper.o/", False)
    assert second["undefined"] == [{"name": "memcpy", "binding": "GLOBAL"}]
    text = report_text(report)
    assert "D GLOBAL FUNC .text 0x00000000 0x10 __init_cpp" in text and "U GLOBAL memcpy" in text
    assert report["library"] == {"file_name": "LIBTEST.LIB", "bytes": len(data), "sha256": report["library"]["sha256"]}


def test_member_filter_and_refusals() -> None:
    data = archive(long_names=True)
    (only,) = archive_report(data, "x.a", ["GCC_WRAPPER.O"])["members"]
    assert only["name"] == "gcc_wrapper.o"
    with pytest.raises(SocomError, match="no member named nope.o; members: staticinitializers.o, gcc_wrapper.o"):
        archive_report(data, "x.a", ["nope.o"])
    with pytest.raises(SocomError, match="not an ar archive"):
        read_archive(b"\x7fELF")
    with pytest.raises(SocomError, match="thin archives"):
        read_archive(b"!<thin>\n")
    with pytest.raises(SocomError, match="past the end"):
        read_archive(data[:-40])
    odd = b"!<arch>\n" + _member("junk.o/", b"not elf")
    (member,) = archive_report(odd, "x.a")["members"]
    assert member["error"] == "not an ELF object" and member["size"] == 7


def test_cli_lists_an_archive_and_records_nothing(tmp_path: Path, capsys) -> None:
    library = tmp_path / "outside" / "LIBTEST.LIB"
    library.parent.mkdir()
    library.write_bytes(archive(long_names=False))
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    base = ["--root", str(workspace), "provider", "archive", "--lib", str(library)]
    assert cli.main([*base, "--member", "staticinitialize"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["ok"] and not report["mutation_performed"] and len(report["members"]) == 1
    # The report names the archive by file name and digest, never by path.
    assert str(library.parent) not in out and report["library"]["file_name"] == "LIBTEST.LIB"
    assert list(workspace.iterdir()) == []
    assert cli.main([*base, "--format", "text"]) == 0
    assert capsys.readouterr().out.startswith("LIBTEST.LIB ")
    assert cli.main(["--root", str(workspace), "provider", "archive", "--lib", str(tmp_path / "missing.a")]) == 2
    error = capsys.readouterr().out
    assert "--lib names no file (missing.a)" in error and str(tmp_path) not in error
    row = next(row for row in json.loads(_commands(capsys)) if row["command"] == "provider archive")
    assert row["mutates"] is False and row["ghidra_requirement"] == "none"


def _commands(capsys) -> str:
    assert cli.main(["commands", "--json"]) == 0
    return capsys.readouterr().out
