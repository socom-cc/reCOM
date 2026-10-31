"""Stage 4: ELF facts behind a source graph that the graph JSON does not store.

``source graph`` keeps signals and candidates, not every relocation or DWARF
compile unit.  The owner-plan draft (``source_draft``) and the query cache
(``source_cache``) need those too: every relocation resolved to the artifacts
it joins, every compile-unit DIE with the object contribution of ``.debug``
it lies in, the ``.line`` rows and the LOCAL symbols.  Everything here is
read from the immutable ELF and the graph's artifact table; nothing is
written.

DWARF contributions: Metrowerks writes one compile-unit DIE without a pc
range for each object (its source path), followed by the object's function
and header compile units.  The linker concatenates ``.debug`` per object, so
a header compile unit (an inline or template body emitted from a header)
belongs to the object whose source compile unit precedes it.  The reference
ELF keeps this without exception: each of its 79 object DIEs names a
distinct source and all 573 source function units follow their own object
DIE; only crt0's unit, the first DIE, has no object DIE before it.
"""

from __future__ import annotations

import bisect
from pathlib import Path, PureWindowsPath
from typing import Any

from .source_graph import _Image, _is_source, _references, _tu_name


class _Spans:
    """Address -> artifact ID over a graph's artifact table."""

    def __init__(self, graph: dict[str, Any]) -> None:
        rows = graph["artifacts"]
        self.nodes = [{"start": int(row["address"], 16), "size": int(row["size"]), "id": row["id"]} for row in rows]
        self.starts = [node["start"] for node in self.nodes]

    def find(self, address: int | None) -> int | None:
        if address is None:
            return None
        position = bisect.bisect_right(self.starts, address) - 1
        if position >= 0 and address < self.nodes[position]["start"] + self.nodes[position]["size"]:
            return position
        return None


def _hex(value: int | None) -> str | None:
    return None if value is None else f"0x{value:x}"


def source_facts(root: Path, graph: dict[str, Any]) -> dict[str, Any]:
    """References, compile units, line rows and LOCAL symbols of the reference ELF.

    ``references``: each relocation as ``{site, site_artifact, target,
    target_artifact, type, symbol_index, symbol, symbol_binding,
    symbol_type}`` (artifacts are graph IDs or ``None``).  ``compile_units``:
    each compile-unit DIE with its path, unit name, pc range, line summary
    and the ``object_unit`` whose contribution holds it.  ``lines``: each
    ``.line`` row with the DIE offset of its unit.  ``local_symbols``: each
    LOCAL symbol with the artifact holding its value.
    """

    image = _Image(root / "support" / "socom.elf")
    spans = _Spans(graph)
    symbols = image.symbols
    references = []
    for row in _references(image, spans):
        index = row["symbol_index"]
        symbol = symbols[index] if 0 <= index < len(symbols) else None
        site, target = row["site_node"], row["target_node"]
        references.append(
            {
                "site": row["site"],
                "site_artifact": spans.nodes[site]["id"] if site is not None else None,
                "target": row["target"],
                "target_artifact": spans.nodes[target]["id"] if target is not None else None,
                "type": row["type"],
                "symbol_index": index,
                "symbol": symbol.name if symbol else None,
                "symbol_binding": symbol.binding_name if symbol else None,
                "symbol_type": symbol.type_name if symbol else None,
            }
        )
    units = []
    lines = []
    current: str | None = None
    for die in image.debug:
        if die.tag_name != "compile_unit":
            continue
        path = die.string("name") or ""
        low, high = die.integer("low_pc"), die.integer("high_pc")
        has_pc = low is not None and high is not None and high > low
        source = bool(path) and _is_source(path)
        if source and not has_pc:
            current = _tu_name(path)
        stmt = die.integer("stmt_list")
        line_unit = image.lines.get(stmt) if stmt is not None else None
        entries = line_unit.entries if line_unit is not None else ()
        units.append(
            {
                "die_offset": _hex(die.offset),
                "path": path,
                "tu": _tu_name(path) if path else None,
                "kind": ("object" if not has_pc else "function") if source else ("header" if has_pc else "other"),
                "producer": die.string("producer"),
                "low_pc": _hex(low) if has_pc else None,
                "high_pc": _hex(high) if has_pc else None,
                "artifact": spans.nodes[spans.find(low)]["id"] if has_pc and spans.find(low) is not None else None,
                "stmt_list": stmt,
                "line_first": min((row.line for row in entries), default=None),
                "line_last": max((row.line for row in entries), default=None),
                "line_entries": len(entries),
                "object_unit": current,
            }
        )
        for row in entries:
            located = spans.find(row.address)
            lines.append(
                {
                    "die_offset": _hex(die.offset),
                    "address": row.address,
                    "line": row.line,
                    "column": row.column,
                    "artifact": spans.nodes[located]["id"] if located is not None else None,
                }
            )
    local_symbols = []
    for symbol in symbols:
        if symbol.binding_name != "LOCAL" or not symbol.name:
            continue
        located = spans.find(symbol.value) if symbol.value else None
        local_symbols.append(
            {
                "symbol_index": symbol.index,
                "name": symbol.name,
                "type": symbol.type_name,
                "value": symbol.value,
                "size": symbol.size,
                "section_index": symbol.section_index,
                "artifact": spans.nodes[located]["id"] if located is not None else None,
            }
        )
    return {"references": references, "compile_units": units, "lines": lines, "local_symbols": local_symbols}


def header_contributions(units: list[dict[str, Any]]) -> dict[str, str]:
    """DIE offset -> the unit whose ``.debug`` contribution holds that compile unit."""

    return {row["die_offset"]: row["object_unit"] for row in units if row.get("object_unit")}


def unit_name(path: str) -> str:
    return PureWindowsPath(path.replace("/", "\\")).name
