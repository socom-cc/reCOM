"""A derived, read-only SQLite cache over the stage 4 source graph.

``source sql`` answers planner questions with one SELECT instead of ad-hoc
scripts over the 30 MB graph and the evidence files.  The cache
``build/cache/source-graph.sqlite`` is built from the graph JSON
(``build/source-graph/graph.json``, or a graph regenerated from the ELF), the
ELF facts the graph does not store (``source_facts``: relocations, compile
units, line rows, LOCAL symbols) and the ``src/`` file list.  It is rebuilt
whenever the graph file's or graph's SHA-256, the reference census or the
``src/`` listing changes, so a query never sees stale rows; deleting it loses
nothing.  Tables are documented in ``SCHEMA`` and in SOURCE_CORRELATION.md.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .util import SocomError, _replace, sha256_file

CACHE_RELATIVE = Path("build") / "cache" / "source-graph.sqlite"
CACHE_VERSION = "3"
SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
-- One row per graph artifact (function, data or gap).  address/end/size are
-- integers; id spells the address in hex.  segment/item: the planning scope
-- whose slice holds it.  classification/library/class_weak/class_evidence:
-- the graph's candidate.  tu/tu_strength/tu_via: the primary unit candidate.
-- common: a COMMON allocation (GLOBAL zero-fill data after every input
-- section; its classification and slice are not changed by the tag).
CREATE TABLE artifacts (
  id TEXT PRIMARY KEY, kind TEXT, address INTEGER, "end" INTEGER, size INTEGER,
  name TEXT, names TEXT, binding TEXT, weak INTEGER, inline INTEGER, named INTEGER,
  section TEXT, input_section TEXT, "window" TEXT, cluster TEXT, gnu_object INTEGER,
  classification TEXT, library TEXT, class_weak INTEGER, class_evidence TEXT,
  tu TEXT, tu_strength TEXT, tu_via TEXT, emitted_from_header TEXT,
  fill TEXT, padding INTEGER, labels TEXT, segment INTEGER, item TEXT, common INTEGER);
CREATE TABLE names (artifact TEXT, name TEXT, binding TEXT, symbol_index INTEGER);
CREATE TABLE tu_candidates (artifact TEXT, rank INTEGER, tu TEXT, strength TEXT, via TEXT, sinit_order INTEGER);
CREATE TABLE signals (artifact TEXT, signal TEXT, strength TEXT, tu TEXT, path TEXT, text TEXT, json TEXT);
CREATE TABLE units (
  tu TEXT PRIMARY KEY, paths TEXT, library TEXT, sinit_order INTEGER, signals TEXT,
  anchored_functions INTEGER, anchored_data INTEGER, first_function INTEGER, last_function INTEGER);
-- segment_library: the library the segment cuts follow, when member rules or
-- coupling refined it; data_only: a member without code (from its LOCAL block).
CREATE TABLE gnu_objects (
  address INTEGER PRIMARY KEY, gcc_compiled INTEGER, end_basis TEXT, library TEXT, library_basis TEXT,
  function_count INTEGER, gap_count INTEGER, first_function INTEGER, last_function INTEGER, anchor TEXT,
  data_only INTEGER, data_count INTEGER, segment_library TEXT);
-- Per-object LOCAL-bracketed section runs: each data input section a GNU
-- object's LOCAL SECTION symbol opens, to the next input section (end_basis
-- 'next section symbol': room_for_member 0, the next object starts right
-- there) or cut short by another object's artifact, a COMMON allocation, a
-- change between file bytes and zero fill, or the window end
-- (room_for_member 1: the bytes up to next_start may hold a separate member).
CREATE TABLE object_sections (
  gnu_object INTEGER, library TEXT, data_only INTEGER, name TEXT, symbol_index INTEGER, start INTEGER, "end" INTEGER,
  end_basis TEXT, room_for_member INTEGER, next_start INTEGER, artifacts INTEGER, named TEXT);
CREATE TABLE clusters (id TEXT PRIMARY KEY, member_count INTEGER, units TEXT, libraries TEXT, local_low INTEGER, local_high INTEGER);
CREATE TABLE segments (
  number INTEGER PRIMARY KEY, id TEXT, "window" TEXT, start INTEGER, "end" INTEGER, function_count INTEGER,
  family TEXT, library TEXT, item TEXT, anchor_strength TEXT, start_edge TEXT, end_edge TEXT,
  unanchored_count INTEGER, unanchored_at_start INTEGER, unanchored_at_end INTEGER,
  classification_mix TEXT, tu_candidates TEXT);
CREATE TABLE internal_boundaries (
  segment INTEGER, after_unit TEXT, before_unit TEXT, last_anchor TEXT, next_anchor TEXT,
  unanchored_count INTEGER, unanchored TEXT);
CREATE TABLE scopes (
  item TEXT PRIMARY KEY, kind TEXT, segment_number INTEGER, library TEXT, data_kind TEXT,
  artifact_count INTEGER, function_count INTEGER, slice_sha256 TEXT);
CREATE TABLE slices (item TEXT, artifact TEXT, position INTEGER);
-- Every relocation, resolved to the artifacts it joins (NULL outside every
-- artifact).  symbol_*: the relocation's symbol (LOCAL symbols prove that
-- site and target share one object).
CREATE TABLE refs (
  site INTEGER, site_artifact TEXT, target INTEGER, target_artifact TEXT, type TEXT,
  symbol_index INTEGER, symbol TEXT, symbol_binding TEXT, symbol_type TEXT);
-- Every DWARF compile-unit DIE: kind object (source path, no pc), function,
-- header or other; object_unit is the unit whose .debug contribution holds it.
CREATE TABLE dwarf_cus (
  die_offset TEXT PRIMARY KEY, path TEXT, tu TEXT, kind TEXT, producer TEXT, low_pc INTEGER, high_pc INTEGER,
  artifact TEXT, stmt_list INTEGER, line_first INTEGER, line_last INTEGER, line_entries INTEGER, object_unit TEXT);
CREATE TABLE dwarf_lines (die_offset TEXT, address INTEGER, line INTEGER, "column" INTEGER, artifact TEXT);
-- __FILE__-like strings: one row per referencing artifact (NULL when none).
CREATE TABLE file_strings (string INTEGER, artifact TEXT, text TEXT, tu TEXT, strength TEXT, literal INTEGER, referenced_by TEXT);
CREATE TABLE sinit (tu TEXT, sinit_order INTEGER, artifact TEXT, symbol TEXT, kind TEXT);
-- LOCAL symbols in symbol-table order: the linker writes each object's
-- LOCAL symbols contiguously, so index runs are local-symbol blocks.
CREATE TABLE local_symbols (
  symbol_index INTEGER PRIMARY KEY, name TEXT, type TEXT, value INTEGER, size INTEGER,
  section_index INTEGER, artifact TEXT, cluster TEXT);
CREATE TABLE contradictions (kind TEXT, at TEXT, json TEXT);
CREATE TABLE provisional_files (path TEXT PRIMARY KEY, name TEXT, directory TEXT, bytes INTEGER);
CREATE INDEX artifacts_address ON artifacts(address);
CREATE INDEX artifacts_item ON artifacts(item);
CREATE INDEX artifacts_tu ON artifacts(tu);
CREATE INDEX names_name ON names(name);
CREATE INDEX tu_candidates_artifact ON tu_candidates(artifact);
CREATE INDEX signals_artifact ON signals(artifact);
CREATE INDEX refs_site ON refs(site_artifact);
CREATE INDEX refs_target ON refs(target_artifact);
CREATE INDEX lines_die ON dwarf_lines(die_offset);
CREATE INDEX slices_item ON slices(item);
"""
TABLES = (
    "meta", "artifacts", "names", "tu_candidates", "signals", "units", "gnu_objects", "object_sections", "clusters", "segments",
    "internal_boundaries", "scopes", "slices", "refs", "dwarf_cus", "dwarf_lines", "file_strings", "sinit",
    "local_symbols", "contradictions", "provisional_files",
)


def _int(value: Any) -> int | None:
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else None


def src_listing(root: Path) -> list[tuple[str, int]]:
    source = root / "src"
    if not source.is_dir():
        return []
    return sorted(
        (path.relative_to(root).as_posix(), path.stat().st_size) for path in source.rglob("*") if path.is_file()
    )


def _inputs(root: Path, graph_path: Path | None, graph: dict[str, Any] | None) -> dict[str, str]:
    census = root / ".agent" / "REFERENCE_CENSUS.json"
    listing = hashlib.sha256(json.dumps(src_listing(root)).encode("utf-8")).hexdigest()
    found = {"cache_version": CACHE_VERSION, "census_sha256": sha256_file(census) if census.is_file() else "", "src_sha256": listing}
    if graph_path is not None:
        found["graph_file_sha256"] = sha256_file(graph_path)
    elif graph is not None:
        found["graph_sha256"] = graph["graph_sha256"]
    return found


def _stored(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
            return dict(connection.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return None


def _fresh(path: Path, wanted: dict[str, str]) -> bool:
    stored = _stored(path)
    return stored is not None and all(stored.get(key) == value for key, value in wanted.items())


def ensure_source_cache(
    root: Path, *, graph_path: Path | None = None, graph: dict[str, Any] | None = None
) -> tuple[Path, bool]:
    """The cache path, (re)built first when its inputs changed; and whether it was rebuilt.

    Pass ``graph`` (a graph in memory, e.g. regenerated from the ELF) or
    ``graph_path`` (a graph JSON file); the file is loaded only for a rebuild.
    """

    from .util import load_json

    if graph is None and graph_path is None:
        raise SocomError("the source cache needs a graph or a graph file")
    path = root / CACHE_RELATIVE
    wanted = _inputs(root, graph_path, graph)
    if _fresh(path, wanted):
        return path, False
    body = graph if graph is not None else load_json(graph_path)
    meta = dict(wanted)
    meta["graph_sha256"] = body["graph_sha256"]
    _build(root, path, body, meta)
    return path, True


def _build(root: Path, path: Path, graph: dict[str, Any], meta: dict[str, str]) -> None:
    from .source_facts import source_facts
    from .source_plan import (
        input_section_text,
        loaded_section_lookup,
        named,
        planning_scopes,
        provider_units,
        scope_item_id,
        segment_family,
    )

    facts = source_facts(root, graph)
    section_of = loaded_section_lookup(root)
    item_of: dict[str, tuple[str, int | None]] = {}
    scope_rows = []
    slice_rows = []
    by_id = {row["id"]: row for row in graph["artifacts"]}
    for entry in planning_scopes(graph):
        scope = entry["scope"]
        item = scope_item_id(scope)
        numbers = [segment["segment_number"] for segment in entry["segments"]]
        for position, identity in enumerate(entry["artifacts"]):
            item_of[identity] = (item, numbers[0] if len(numbers) == 1 else None)
            slice_rows.append((item, identity, position))
        scope_rows.append(
            (
                item, scope["kind"], scope.get("segment_number"), scope.get("library"), scope.get("data_kind"),
                len(entry["artifacts"]), sum(1 for identity in entry["artifacts"] if by_id[identity]["kind"] == "function"),
                entry["slice_sha256"],
            )
        )
    segment_of = {identity: segment["segment_number"] for segment in graph["segments"] for identity in segment["artifacts"]}
    segment_of.update({identity: segment["segment_number"] for segment in graph["segments"] for identity in segment["data"]})

    artifacts, names, candidates, signals, file_strings, sinit = [], [], [], [], [], []
    for row in graph["artifacts"]:
        identity = row["id"]
        classification = row["classification"]
        bindings = {item.get("binding") for item in row.get("names") or []} | {row.get("binding")}
        primary = (row.get("tu_candidates") or [None])[0] or {}
        artifacts.append(
            (
                identity, row["kind"], int(row["address"], 16), int(row["end"], 16), row["size"],
                (row.get("names") or [{}])[0].get("name"), " ".join(item["name"] for item in row.get("names") or []),
                row.get("binding"), int("WEAK" in bindings), int("13" in bindings), int(named(row)),
                section_of(int(row["address"], 16)), input_section_text(row), row["window"], row.get("cluster"),
                _int(row.get("gnu_object")), classification.get("candidate"), classification.get("library"),
                int(classification.get("weak") is True), "; ".join(classification.get("evidence") or []),
                primary.get("tu"), primary.get("strength"), ",".join(primary.get("via") or []),
                row.get("emitted_from_header"), row.get("fill"), None if "padding" not in row else int(bool(row["padding"])),
                ",".join(row.get("labels") or []) or None, segment_of.get(identity), item_of.get(identity, (None,))[0],
                int(bool(row.get("common"))),
            )
        )
        for item in row.get("names") or []:
            names.append((identity, item["name"], item.get("binding"), item.get("symbol_index")))
        for rank, candidate in enumerate(row.get("tu_candidates") or []):
            candidates.append((identity, rank, candidate["tu"], candidate["strength"], ",".join(candidate["via"]), candidate.get("sinit_order")))
        for item in row.get("signals") or []:
            signals.append(
                (identity, item["signal"], item.get("strength"), item.get("tu"), item.get("path"), item.get("text"), json.dumps(item, sort_keys=True))
            )
            if item["signal"] in ("file-string", "file-string-header"):
                users = item.get("referenced_by") or [None]
                for user in users:
                    file_strings.append(
                        (_int(item.get("string")), identity, item.get("text"), item.get("tu"), item.get("strength"), int(bool(item.get("literal"))), user)
                    )
            if item["signal"] == "sinit":
                sinit.append((item.get("tu"), item.get("order") or primary.get("sinit_order"), identity, item.get("symbol"), row["kind"]))
    libraries = provider_units(graph)
    units = [
        (
            unit["tu"], "\n".join(unit.get("paths") or []), libraries.get(unit["tu"].casefold()), unit.get("sinit_order"),
            ",".join(unit.get("signals") or []), unit.get("anchored_functions"), unit.get("anchored_data"),
            _int(unit.get("first_function")), _int(unit.get("last_function")),
        )
        for unit in graph["units"]
    ]
    gnu = [
        (
            int(row["address"], 16), int(bool(row.get("gcc_compiled"))), row.get("end_basis"), row.get("library"), row.get("library_basis"),
            len(row.get("functions") or []), len(row.get("gaps") or []),
            _int((row.get("functions") or [""])[0].rsplit(":", 1)[-1]) if row.get("functions") else None,
            _int((row.get("functions") or [""])[-1].rsplit(":", 1)[-1]) if row.get("functions") else None,
            ", ".join(item["name"] for item in row.get("anchor") or []),
            int(bool(row.get("data_only"))), len(row.get("data") or []), row.get("segment_library"),
        )
        for row in graph["gnu_objects"]
    ]
    section_starts = sorted(
        {row["value"] for row in facts["local_symbols"] if row["type"] == "SECTION" and row["value"] and ".DVP." not in row["name"]}
    )
    addresses = sorted(int(row["address"], 16) for row in graph["artifacts"])
    by_address = {int(row["address"], 16): row for row in graph["artifacts"]}
    object_sections = []
    for row in graph["gnu_objects"]:
        for run in row.get("sections") or []:
            start, end = int(run["start"], 16), int(run["end"], 16)
            following = next((value for value in section_starts[bisect.bisect_right(section_starts, start) :]), None)
            inside = [by_address[value] for value in addresses[bisect.bisect_left(addresses, start) : bisect.bisect_left(addresses, end)]]
            named_rows = [item["names"][0]["name"] for item in inside if item.get("names")]
            object_sections.append(
                (
                    int(row["address"], 16), row.get("library"), int(bool(row.get("data_only"))), run["name"], run["symbol_index"],
                    start, end, run["end_basis"], int(run["end_basis"] != "next section symbol"), following, len(inside),
                    " ".join(named_rows[:8]) + (f" +{len(named_rows) - 8}" if len(named_rows) > 8 else ""),
                )
            )
    cluster_of = {}
    clusters = []
    for row in graph.get("clusters") or []:
        for member in row["members"]:
            cluster_of[member] = row["id"]
        local = row.get("local_symbol_range") or [None, None]
        clusters.append(
            (row["id"], len(row["members"]), ",".join(unit["tu"] for unit in row.get("units") or []), ",".join(row.get("libraries") or []), local[0], local[1])
        )
    segments, boundaries = [], []
    for segment in graph["segments"]:
        family, library = segment_family(segment)
        number = segment["segment_number"]
        boundary = segment.get("boundary") or {}
        segments.append(
            (
                number, segment["id"], segment["window"], int(segment["start"], 16), int(segment["end"], 16), segment["function_count"],
                family, library, item_of.get(segment["artifacts"][0], (None,))[0] if segment["artifacts"] else None,
                segment.get("anchor_strength"), (boundary.get("start") or {}).get("reason"), (boundary.get("end") or {}).get("reason"),
                segment.get("unanchored_function_count"), boundary.get("unanchored_at_start"), boundary.get("unanchored_at_end"),
                json.dumps(segment.get("classification_mix") or {}, sort_keys=True), json.dumps(segment.get("tu_candidates") or []),
            )
        )
        for row in segment.get("internal_boundaries") or []:
            boundaries.append(
                (number, row["after"], row["before"], row["last_anchor"], row["next_anchor"], len(row["unanchored"]), " ".join(row["unanchored"]))
            )
    refs = [
        (
            row["site"], row["site_artifact"], row["target"], row["target_artifact"], row["type"], row["symbol_index"],
            row["symbol"], row["symbol_binding"], row["symbol_type"],
        )
        for row in facts["references"]
    ]
    cus = [
        (
            row["die_offset"], row["path"], row["tu"], row["kind"], row["producer"], _int(row["low_pc"]), _int(row["high_pc"]),
            row["artifact"], row["stmt_list"], row["line_first"], row["line_last"], row["line_entries"], row["object_unit"],
        )
        for row in facts["compile_units"]
    ]
    lines = [(row["die_offset"], row["address"], row["line"], row["column"], row["artifact"]) for row in facts["lines"]]
    locals_ = [
        (row["symbol_index"], row["name"], row["type"], row["value"], row["size"], row["section_index"], row["artifact"], cluster_of.get(row["artifact"]))
        for row in facts["local_symbols"]
    ]
    contradictions = [(row.get("kind"), row.get("at"), json.dumps(row, sort_keys=True)) for row in graph.get("contradictions") or []]
    files = [(relative, relative.rsplit("/", 1)[-1], relative.rsplit("/", 1)[0], size) for relative, size in src_listing(root)]

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    with closing(sqlite3.connect(temporary)) as connection:
        connection.executescript(SCHEMA)
        connection.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
        for table, rows in (
            ("artifacts", artifacts), ("names", names), ("tu_candidates", candidates), ("signals", signals), ("units", units),
            ("gnu_objects", gnu), ("object_sections", object_sections), ("clusters", clusters), ("segments", segments), ("internal_boundaries", boundaries),
            ("scopes", scope_rows), ("slices", slice_rows), ("refs", refs), ("dwarf_cus", cus), ("dwarf_lines", lines),
            ("file_strings", file_strings), ("sinit", sinit), ("local_symbols", locals_), ("contradictions", contradictions),
            ("provisional_files", files),
        ):
            if rows:
                connection.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        connection.commit()
    try:
        _replace(temporary, path)
    except PermissionError:
        temporary.unlink(missing_ok=True)
        if not _fresh(path, meta):
            raise


def query(path: Path, statement: str, limit: int = 200) -> dict[str, Any]:
    """Run one read-only SELECT/WITH statement against the cache."""

    text = statement.strip().rstrip(";").strip()
    if not text.lower().startswith(("select", "with")) or ";" in text:
        raise SocomError("source sql accepts a single SELECT or WITH statement")
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        try:
            cursor = connection.execute(text)
        except sqlite3.Error as exc:
            raise SocomError(f"query failed: {exc}") from exc
        columns = [description[0] for description in cursor.description or []]
        rows = cursor.fetchmany(limit + 1)
    return {"columns": columns, "rows": [list(row) for row in rows[:limit]], "truncated": len(rows) > limit}


def load_facts(path: Path) -> dict[str, Any]:
    """The draft's facts (references and compile units) read back from a fresh cache."""

    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        references = [
            {"site_artifact": site, "target_artifact": target, "symbol_index": index, "symbol_type": kind, "symbol_binding": binding}
            for site, target, index, kind, binding in connection.execute(
                "SELECT site_artifact, target_artifact, symbol_index, symbol_type, symbol_binding FROM refs "
                "WHERE site_artifact IS NOT NULL AND target_artifact IS NOT NULL"
            )
        ]
        units = [
            {"die_offset": die, "object_unit": unit}
            for die, unit in connection.execute("SELECT die_offset, object_unit FROM dwarf_cus WHERE object_unit IS NOT NULL")
        ]
    return {"references": references, "compile_units": units}
