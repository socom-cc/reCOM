"""A derived, read-only SQLite query cache over the canonical JSON state.

Canonical state stays in reviewable JSON (tracker, reference census, issue
ledger).  This module builds ``build/cache/progress.sqlite`` from them and
rebuilds it whenever any source file's SHA-256 changes, so a query never sees
stale rows.  The cache is disposable: deleting it loses nothing.

Tables: work_items, stages, symbols, relocations, issues, plus ``meta`` (the
source hashes the cache was built from).  ``query`` accepts a single SELECT or
WITH statement and opens the database read-only.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .util import _replace, SocomError, load_json, sha256_file

CACHE_RELATIVE = Path("build") / "cache" / "progress.sqlite"
SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE work_items (
  id TEXT PRIMARY KEY, kind TEXT, status TEXT, stage TEXT, title TEXT,
  group_number INTEGER, height INTEGER, function_count INTEGER,
  lease_owner TEXT, handoff_owner TEXT, accepted_by TEXT, accepted_at TEXT,
  dependencies TEXT, json TEXT);
CREATE TABLE stages (name TEXT PRIMARY KEY, status TEXT, json TEXT);
CREATE TABLE symbols (
  "index" INTEGER PRIMARY KEY, name TEXT, type TEXT, binding TEXT,
  section_index INTEGER, value INTEGER, size INTEGER);
CREATE TABLE relocations (
  "index" INTEGER PRIMARY KEY, offset INTEGER, type TEXT, symbol_index INTEGER, addend INTEGER);
CREATE TABLE issues (id TEXT PRIMARY KEY, status TEXT, kind TEXT, summary TEXT, reported_at TEXT, json TEXT);
CREATE INDEX work_items_status ON work_items(kind, status);
CREATE INDEX symbols_name ON symbols(name);
CREATE INDEX symbols_value ON symbols(value);
CREATE INDEX relocations_offset ON relocations(offset);
"""


def _sources(root: Path) -> dict[str, Path]:
    agent = root / ".agent"
    return {
        "tracker": agent / "RECONSTRUCTION_PROGRESS.json",
        "census": agent / "REFERENCE_CENSUS.json",
        "issues": agent / "WORKSPACE_ISSUES.json",
    }


def _hashes(root: Path) -> dict[str, str]:
    return {name: sha256_file(path) for name, path in _sources(root).items() if path.is_file()}


def _fresh(path: Path, hashes: dict[str, str]) -> bool:
    if not path.is_file():
        return False
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
            stored = dict(connection.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return False
    return all(stored.get(f"{name}_sha256") == value for name, value in hashes.items())


def _build(root: Path, path: Path, hashes: dict[str, str]) -> None:
    sources = _sources(root)
    tracker = load_json(sources["tracker"])
    census = load_json(sources["census"]) if sources["census"].is_file() else {}
    issues = load_json(sources["issues"]) if sources["issues"].is_file() else {}
    path.parent.mkdir(parents=True, exist_ok=True)
    # One temporary file per process: concurrent rebuilds do not collide.
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    with closing(sqlite3.connect(temporary)) as connection:
        connection.executescript(SCHEMA)
        connection.executemany("INSERT INTO meta VALUES (?, ?)", [(f"{k}_sha256", v) for k, v in hashes.items()])
        connection.execute("INSERT INTO meta VALUES ('tracker_revision', ?)", (str(tracker.get("revision")),))
        rows = []
        for item in tracker.get("work_items", []):
            batch = item.get("batch") or {}
            rows.append(
                (
                    item["id"], item.get("kind"), item.get("status"), item.get("stage"), item.get("title"),
                    batch.get("group_number"), batch.get("height"),
                    len(batch["functions"]) if isinstance(batch.get("functions"), list) else None,
                    (item.get("lease") or {}).get("owner"), (item.get("handoff") or {}).get("owner"),
                    (item.get("accepted") or {}).get("by"), (item.get("accepted") or {}).get("at"),
                    json.dumps(item.get("dependencies") or []), json.dumps(item, sort_keys=True),
                )
            )
        connection.executemany(f"INSERT INTO work_items VALUES ({','.join('?' * 14)})", rows)
        connection.executemany(
            "INSERT INTO stages VALUES (?, ?, ?)",
            [(s["name"], s.get("status"), json.dumps(s, sort_keys=True)) for s in tracker.get("stages", [])],
        )
        connection.executemany(
            "INSERT INTO symbols VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (s["index"], s.get("name"), s.get("type"), s.get("binding"), s.get("section_index"), s.get("value"), s.get("size"))
                for s in census.get("symbols", [])
            ],
        )
        connection.executemany(
            "INSERT INTO relocations VALUES (?, ?, ?, ?, ?)",
            [(r["index"], r.get("offset"), r.get("type"), r.get("symbol_index"), r.get("addend")) for r in census.get("relocations", [])],
        )
        connection.executemany(
            "INSERT INTO issues VALUES (?, ?, ?, ?, ?, ?)",
            [
                (i["id"], i.get("status"), i.get("kind"), i.get("summary"), i.get("reported_at"), json.dumps(i, sort_keys=True))
                for i in issues.get("issues", [])
            ],
        )
        connection.commit()
    try:
        _replace(temporary, path)
    except PermissionError:
        # A reader holds the old file open; another process may already have
        # installed an equal rebuild.
        temporary.unlink(missing_ok=True)
        if not _fresh(path, hashes):
            raise


def ensure_cache(root: Path) -> Path:
    """The cache path, rebuilt first if any source changed."""

    path = root / CACHE_RELATIVE
    hashes = _hashes(root)
    if not _fresh(path, hashes):
        _build(root, path, hashes)
    return path


def query(root: Path, statement: str, limit: int = 200) -> dict[str, Any]:
    """Run one read-only SELECT/WITH statement against a fresh cache."""

    text = statement.strip().rstrip(";").strip()
    if not text.lower().startswith(("select", "with")) or ";" in text:
        raise SocomError("progress sql accepts a single SELECT or WITH statement")
    path = ensure_cache(root)
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        try:
            cursor = connection.execute(text)
        except sqlite3.Error as exc:
            raise SocomError(f"query failed: {exc}") from exc
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(limit + 1)
    return {"columns": columns, "rows": [list(r) for r in rows[:limit]], "truncated": len(rows) > limit}
