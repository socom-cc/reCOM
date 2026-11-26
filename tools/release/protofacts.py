"""Prototype facts: function symbols, provider classification, owning source files.

Inputs (all read-only): the prototype symbol table; the generated cache
``build/cache/source-graph.sqlite`` (table ``artifacts``, kind 'function') for
classification and library, optional; the ``@socom-artifact defines|emits``
annotation lines under ``src/`` for the owning source file.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

ANNOTATION = re.compile(r"@socom-artifact (defines|emits) (\S+) socom:function:0x([0-9a-f]+)")
SOURCE_SUFFIXES = (".c", ".cpp", ".cc", ".h", ".hpp", ".inl", ".s", ".S")


@dataclass
class ProtoFunction:
    address: int
    size: int
    names: list[str]
    classification: str = ""
    library: str = ""
    owner: str = ""  # repo-relative source file
    owner_kind: str = ""  # defines | emits
    sized: bool = True  # False: found by the sweep where the symbol table gives no size

    @property
    def name(self) -> str:
        return self.names[0] if self.names else "sub_%x" % self.address


def module_of(path: str) -> str:
    """``gamez/<module>``, ``Apps/FTS/<part>`` or the first two folders under src/."""

    if not path:
        return ""
    parts = path.split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if not parts:
        return ""
    if parts[0] == "Apps":
        return "/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:2])
    if len(parts) == 1:
        return "(src root)"
    return "/".join(parts[:2])


def sized_functions(image) -> dict[int, ProtoFunction]:
    out: dict[int, ProtoFunction] = {}
    for symbol in sorted(image.symbols, key=lambda s: (s.address, s.name)):
        if symbol.kind != 2 or not symbol.size or not image.contains(symbol.address):
            continue
        entry = out.get(symbol.address)
        if entry is None:
            out[symbol.address] = ProtoFunction(symbol.address, symbol.size, [symbol.name])
        else:
            entry.size = max(entry.size, symbol.size)
            if symbol.name not in entry.names:
                entry.names.append(symbol.name)
    return out


def symbol_names(image) -> dict[int, list[str]]:
    names: dict[int, list[str]] = {}
    for symbol in sorted(image.symbols, key=lambda s: (s.address, s.kind != 2, s.name)):
        if symbol.name and not symbol.name.startswith("."):
            names.setdefault(symbol.address, []).append(symbol.name)
    return names


def apply_source_graph(functions: dict[int, ProtoFunction], database: Path) -> bool:
    if not database.is_file():
        return False
    uri = "file:" + database.resolve().as_posix() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute(
            "select address, name, classification, coalesce(library, '') from artifacts where kind = 'function'"
        ).fetchall()
    finally:
        connection.close()
    for address, name, classification, library in rows:
        entry = functions.get(address)
        if entry is None:
            continue
        entry.classification = classification or ""
        entry.library = library or ""
        if name and name in entry.names and entry.names[0] != name:
            entry.names.remove(name)
            entry.names.insert(0, name)
    return True


def apply_annotations(functions: dict[int, ProtoFunction], root: Path) -> int:
    source = root / "src"
    count = 0
    if not source.is_dir():
        return 0
    for path in sorted(source.rglob("*"), key=lambda p: p.as_posix()):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "@socom-artifact" not in text:
            continue
        relative = path.relative_to(root).as_posix()
        for match in ANNOTATION.finditer(text):
            entry = functions.get(int(match.group(3), 16))
            if entry is None:
                continue
            # a definition outranks an emission; otherwise keep the first file in path order
            if not entry.owner or (entry.owner_kind == "emits" and match.group(1) == "defines"):
                entry.owner = relative
                entry.owner_kind = match.group(1)
                count += 1
    return count
