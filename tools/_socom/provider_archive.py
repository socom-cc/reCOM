"""Read-only listing of a provider archive: its members and their ELF symbols.

``provider archive --lib <path> [--member NAME ...] [--format json|text]`` is
an ``ar``/``nm`` equivalent for toolchain, SDK and middleware libraries
(``.a``, CodeWarrior ``.LIB``) that provider planners compare with the
reference ELF.  It reads the ``ar`` container (System V/GNU ``/`` and
``//`` tables, ``/<n>`` long names, BSD ``#1/<n>`` names and
``__.SYMDEF``) and each member's ELF32 little-endian symbol table, and
prints every member's header name (16 bytes, so an archiver without a
long-name table truncates it), resolved name, size, sections, defined
symbols (binding, type, section, value, size) and undefined symbols.

The archive is external input that stays outside the workspace.  The
command writes nothing, and its report names the archive only by file name,
size and SHA-256, never by its path, so no machine-specific location can
reach a tracked surface by copying the report.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Any

from .elf import SHT_NOBITS, SHT_PROGBITS, SHT_SYMTAB, Elf32File
from .util import SocomError

AR_MAGIC = b"!<arch>\n"
THIN_MAGIC = b"!<thin>\n"
HEADER_SIZE = 60
NAME_FIELD = 16
SHN_UNDEF, SHN_ABS, SHN_COMMON = 0, 0xFFF1, 0xFFF2
STT_SECTION, STT_FILE = 3, 4
_GNU_LONG = re.compile(r"^/(\d+)$")
_BSD_LONG = re.compile(r"^#1/(\d+)$")


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "provider archive",
            "provider",
            "List a provider archive's (.a/.LIB, given by path) members with their header and resolved names, sizes, "
            "sections and defined/undefined ELF symbols with sizes; read-only, and the report names the archive by "
            "file name and SHA-256 only.",
        ),
    )


def register(commands: Any) -> None:
    provider = commands.add_parser("provider")
    provider_commands = provider.add_subparsers(dest="provider_command", required=True)
    archive = provider_commands.add_parser("archive")
    archive.add_argument("--lib", required=True, help="the archive to read (never recorded)")
    archive.add_argument(
        "--member", action="append", default=[], help="list only this member (resolved or header name; repeatable)"
    )
    archive.add_argument("--format", choices=("json", "text"), default="json")
    archive.set_defaults(handler=_provider_archive)


# -- the ar container -------------------------------------------------------------


def _long_name(table: bytes | None, offset: int) -> str:
    if table is None or not 0 <= offset < len(table):
        raise SocomError(f"long member name /{offset} lies outside the archive's // table")
    end = len(table)
    for terminator in (b"/\n", b"\n", b"\0"):
        found = table.find(terminator, offset)
        if found >= 0:
            end = min(end, found)
    return table[offset:end].decode("latin-1").rstrip("/")


def _sysv_symbols(body: bytes, wide: bool) -> list[tuple[str, int]] | None:
    """(symbol, member header offset) of a System V/GNU archive symbol table, or ``None`` when it does not parse."""

    width = 8 if wide else 4
    if len(body) < width:
        return None
    count = int.from_bytes(body[:width], "big")
    names_at = width * (count + 1)
    if names_at > len(body):
        return None
    offsets = [int.from_bytes(body[width * (index + 1) : width * (index + 2)], "big") for index in range(count)]
    names = body[names_at:].split(b"\0")
    if len(names) < count:
        return None
    return [(names[index].decode("latin-1"), offsets[index]) for index in range(count)]


def read_archive(data: bytes) -> dict[str, Any]:
    """The members of an ``ar`` archive in order, with their names, sizes and data."""

    if data.startswith(THIN_MAGIC):
        raise SocomError("thin archives (members stored outside the archive) are not supported")
    if not data.startswith(AR_MAGIC):
        raise SocomError("not an ar archive (no !<arch> magic)")
    members: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    armap: dict[int, list[str]] = {}
    long_names: bytes | None = None
    offset = len(AR_MAGIC)
    while offset < len(data):
        if data[offset:] in (b"\n", b"\0"):
            break  # final padding byte
        header = data[offset : offset + HEADER_SIZE]
        if len(header) < HEADER_SIZE:
            raise SocomError(f"member header at offset {offset} is truncated")
        if header[58:60] != b"`\n":
            raise SocomError(f"member header at offset {offset} lacks its `\\n terminator")
        field = header[:NAME_FIELD].decode("latin-1").rstrip(" ")
        try:
            size = int(header[48:58].decode("ascii").strip() or "0")
        except ValueError as exc:
            raise SocomError(f"member header at offset {offset} has no decimal size") from exc
        start = offset + HEADER_SIZE
        body = data[start : start + size]
        if len(body) != size:
            raise SocomError(f"member at offset {offset} claims {size} bytes past the end of the archive")
        if field in ("/", "/SYM64/"):
            parsed = _sysv_symbols(body, wide=field == "/SYM64/")
            if parsed is None or any(value not in range(len(AR_MAGIC), len(data)) for _name, value in parsed):
                # A COFF second linker member (Windows .LIB) has another layout.
                tables.append({"kind": "linker-member", "offset": offset, "size": size, "symbols": None})
            else:
                tables.append({"kind": "sysv", "offset": offset, "size": size, "symbols": len(parsed)})
                for name, value in parsed:
                    armap.setdefault(value, []).append(name)
        elif field == "//":
            long_names = body
        elif field.startswith("__.SYMDEF"):
            tables.append({"kind": "bsd", "offset": offset, "size": size, "symbols": None})
        else:
            member: dict[str, Any] = {"offset": offset, "header_name": field}
            if match := _GNU_LONG.match(field):
                member.update(name=_long_name(long_names, int(match.group(1))), name_source="long-name-table")
            elif match := _BSD_LONG.match(field):
                length = int(match.group(1))
                member.update(name=body[:length].rstrip(b"\0").decode("latin-1"), name_source="bsd-long-name")
                body = body[length:]
            else:
                member.update(name=field[:-1] if field.endswith("/") else field, name_source="header")
            # Every byte of the header's name field is used: an archiver
            # without a long-name table may have cut the name there.
            member["header_name_full"] = member["name_source"] == "header" and len(field) == NAME_FIELD
            member["size"] = len(body)
            member["sha256"] = hashlib.sha256(body).hexdigest()
            member["data"] = body
            members.append(member)
        offset = start + size + (size & 1)
    for index, member in enumerate(members, 1):
        member["index"] = index
        member["armap_symbols"] = sorted(armap.get(member["offset"], []))
    return {"members": members, "symbol_tables": tables, "long_name_table": long_names is not None}


# -- the members' ELF symbols -----------------------------------------------------------


def _section_name(elf: Elf32File, index: int) -> str:
    if index == SHN_ABS:
        return "ABS"
    if index == SHN_COMMON:
        return "COMMON"
    return elf.sections[index].name if 0 <= index < len(elf.sections) else f"section {index}"


def member_symbols(member: dict[str, Any]) -> dict[str, Any]:
    """The sections and symbols of one member's ELF32 object (an error line when it is none)."""

    body = member["data"]
    if body[:4] != b"\x7fELF":
        return {"format": "unknown", "error": "not an ELF object"}
    try:
        elf = Elf32File(Path(member["name"] or "member"), data=body)
    except SocomError as failure:
        return {"format": "ELF", "error": str(failure)}
    sections = [
        {"name": section.name, "type": section.type_name, "size": section.size, "alloc": bool(section.flags & 0x2)}
        for section in elf.sections
        if section.index and section.type in (SHT_PROGBITS, SHT_NOBITS) and section.size
    ]
    files: list[str] = []
    defined: list[dict[str, Any]] = []
    undefined: list[dict[str, Any]] = []
    tables = [section for section in elf.sections if section.type == SHT_SYMTAB]
    try:
        symbols = elf.symbols(tables[0].name) if tables else ()
    except SocomError as failure:
        return {"format": "ELF32", "sections": sections, "error": str(failure)}
    for symbol in symbols[1:]:
        if symbol.type == STT_SECTION:
            continue
        if symbol.type == STT_FILE:
            files.append(symbol.name)
            continue
        if symbol.section_index == SHN_UNDEF:
            undefined.append({"name": symbol.name, "binding": symbol.binding_name})
            continue
        defined.append(
            {
                "name": symbol.name,
                "binding": symbol.binding_name,
                "type": symbol.type_name,
                "section": _section_name(elf, symbol.section_index),
                "value": symbol.value,
                "size": symbol.size,
            }
        )
    return {"format": "ELF32", "sections": sections, "files": files, "defined": defined, "undefined": undefined}


def _stem(name: str) -> str:
    base = re.split(r"[\\/]", name)[-1]
    return base.rsplit(".", 1)[0].casefold() if "." in base else base.casefold()


def archive_report(data: bytes, file_name: str, wanted: list[str] | None = None) -> dict[str, Any]:
    """The listing of one archive; ``wanted`` keeps the members of those names (resolved or header)."""

    archive = read_archive(data)
    members = archive["members"]
    if wanted:
        keys = {value.casefold() for value in wanted}
        chosen = [row for row in members if row["name"].casefold() in keys or row["header_name"].casefold() in keys]
        if not chosen:
            names = ", ".join(row["name"] for row in members[:40]) + (" ..." if len(members) > 40 else "")
            raise SocomError(f"the archive has no member named {', '.join(wanted)}; members: {names}")
    else:
        chosen = members
    rows = []
    for member in chosen:
        listing = member_symbols(member)
        stem = _stem(member["name"])
        # A source file symbol longer than the header name that starts with
        # it names what the cut header name stood for.
        longer = sorted({name for name in listing.get("files") or [] if _stem(name).startswith(stem) and _stem(name) != stem})
        row = {key: member[key] for key in ("index", "name", "header_name", "name_source", "offset", "size", "sha256")}
        row["possibly_truncated"] = member["name_source"] == "header" and (member["header_name_full"] or bool(longer))
        row["armap_symbols"] = member["armap_symbols"]
        row.update(listing)
        rows.append(row)
    return {
        "library": {"file_name": file_name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
        "format": "ar",
        "member_count": len(members),
        "long_name_table": archive["long_name_table"],
        "symbol_tables": archive["symbol_tables"],
        "members": rows,
    }


def report_text(report: dict[str, Any]) -> str:
    library = report["library"]
    lines = [
        f"{library['file_name']} {library['bytes']} bytes sha256 {library['sha256']}: {report['member_count']} members"
        + ("" if report["long_name_table"] else ", no long-name table")
    ]
    for table in report["symbol_tables"]:
        lines.append(f"symbol table {table['kind']} at {table['offset']}: {table['symbols'] if table['symbols'] is not None else '?'} symbols")
    for row in report["members"]:
        header = f" header {row['header_name']!r}" if row["header_name"] != row["name"] else ""
        flags = " possibly truncated" if row["possibly_truncated"] else ""
        files = f" files {', '.join(row['files'])}" if row.get("files") else ""
        lines.append(f"member {row['index']} {row['name']}{header}{flags} {row['size']} bytes{files}")
        if row.get("error"):
            lines.append(f"    error: {row['error']}")
        for section in row.get("sections") or []:
            lines.append(f"    section {section['name']} {section['type']} 0x{section['size']:x}")
        for symbol in row.get("defined") or []:
            lines.append(
                f"    D {symbol['binding']} {symbol['type']} {symbol['section']} 0x{symbol['value']:08x} "
                f"0x{symbol['size']:x} {symbol['name']}"
            )
        for symbol in row.get("undefined") or []:
            lines.append(f"    U {symbol['binding']} {symbol['name']}")
    return "\n".join(lines) + "\n"


def _provider_archive(arguments: argparse.Namespace) -> int:
    from .cli import _emit

    path = Path(arguments.lib)
    if not path.is_file():
        # Only the file name: the report never repeats the archive's location.
        raise SocomError(f"--lib names no file ({path.name})")
    report = archive_report(path.read_bytes(), path.name, arguments.member)
    if arguments.format == "text":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(report_text(report))
        return 0
    _emit({"ok": True, "mutation_performed": False, **report})
    return 0
