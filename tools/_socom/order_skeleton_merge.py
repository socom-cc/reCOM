"""Stage 5 skeleton re-apply as a three-way merge (``progress apply-order-skeleton`` after a reopen).

The skeleton route renders each item's files from the frozen base and the
current plans and manifest.  Once ``src/`` holds a skeleton, later work (the
functional port lane, AGENTS.md) edits those files on purpose, so a re-apply
does not overwrite them: per file it merges

* the **ancestor**, the previous render of the file (the content the previous
  record's render gave: ``rendered_sha256``, or ``after_sha256`` for a record
  that predates merges), or the frozen base's content for a file the route
  never wrote;
* **ours**, the live file under ``src/``;
* **theirs**, the new render.

Equal sides decide without a merge (theirs equal to the ancestor keeps ours,
ours equal to the ancestor takes theirs).  Otherwise a deterministic,
standard-library line merge3 (``difflib`` matching blocks, the classic
sync-region algorithm) merges the two changes; overlapping changes conflict.
A conflict writes nothing: the route reports its hunks and writes marker
files under ``build/`` for a source worker, whose resolved file is passed back
with ``--resolutions`` and recorded by digest.

Every merged or resolved file must keep the render's fence lines (the same
sequence, so the order the fences give is the planned one) and its stage 4
blocks.  Contents are kept LF-normalized in a content-addressed blob store
under ``build/stage5/skeleton-route/blobs`` so ``order skeleton apply-check``
can re-run a recorded merge.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .util import SocomError, atomic_write_bytes, atomic_write_json, load_json

ROUTE_DIR = "build/stage5/skeleton-route"
BLOB_DIR = f"{ROUTE_DIR}/blobs"
CONFLICT_DIR = f"{ROUTE_DIR}/conflicts"
CONFLICT_KIND = "socom-order-skeleton-conflicts"
CONFLICT_SCHEMA = 1
MERGE_KINDS = ("render", "kept", "same", "clean", "resolved")
_FENCE = re.compile(r"/\* @socom-skeleton (?:stub|body|decl|end) \S+ \*/")
_MARKERS = ("<<<<<<< ", "||||||| ", "=======", ">>>>>>> ")
_SHOWN = 12


def lf(data: bytes | None) -> bytes | None:
    return None if data is None else data.replace(b"\r\n", b"\n")


def sha(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(lf(data)).hexdigest()


def _text(data: bytes) -> str:
    return lf(data).decode("utf-8", "surrogateescape")  # type: ignore[union-attr]


def _bytes(text: str) -> bytes:
    return text.encode("utf-8", "surrogateescape")


def record_ancestor(row: dict[str, Any]) -> str | None:
    """The digest of a record row's render, the merge ancestor of the next re-apply: ``rendered_sha256``, else ``after_sha256``.

    A record from before merges wrote exactly its render, so its after digest is the render's.
    """

    return row["rendered_sha256"] if "rendered_sha256" in row else row.get("after_sha256")


def item_slug(item_id: str) -> str:
    return item_id.replace(":", "-")


# -- the blob store ------------------------------------------------------------------------


def put_blob(root: Path, data: bytes | None) -> str | None:
    """Store LF-normalized content under its SHA-256 (idempotent); returns the digest."""

    if data is None:
        return None
    body = lf(data)
    digest = hashlib.sha256(body).hexdigest()  # type: ignore[arg-type]
    path = root / BLOB_DIR / digest
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        atomic_write_bytes(path, body)  # type: ignore[arg-type]
    return digest


def get_blob(root: Path, digest: str | None) -> bytes | None:
    """The stored content of ``digest`` (verified), or None when it is not stored."""

    if not digest:
        return None
    path = root / BLOB_DIR / digest
    if not path.is_file():
        return None
    data = path.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == digest else None


def has_blob(root: Path, digest: str | None) -> bool:
    return get_blob(root, digest) is not None


# -- merge3 ---------------------------------------------------------------------------------


def _matches(base: list[str], other: list[str]) -> list[tuple[int, int, int]]:
    return [tuple(block) for block in SequenceMatcher(None, base, other, autojunk=False).get_matching_blocks()]  # type: ignore[misc]


def _sync_regions(base: list[str], ours: list[str], theirs: list[str]) -> list[tuple[int, int, int, int, int, int]]:
    """Regions where all three agree: (base start, end, ours start, end, theirs start, end), ending with the sentinel."""

    regions = []
    left, right = _matches(base, ours), _matches(base, theirs)
    i = j = 0
    while i < len(left) and j < len(right):
        a_base, a_match, a_len = left[i]
        b_base, b_match, b_len = right[j]
        start, end = max(a_base, b_base), min(a_base + a_len, b_base + b_len)
        if start < end:
            regions.append((start, end, a_match + start - a_base, a_match + end - a_base,
                            b_match + start - b_base, b_match + end - b_base))
        if a_base + a_len < b_base + b_len:
            i += 1
        else:
            j += 1
    regions.append((len(base), len(base), len(ours), len(ours), len(theirs), len(theirs)))
    return regions


@dataclass
class Merged:
    """A merge result: ``lines`` (with ``conflicts`` hunks when the two changes overlap)."""

    lines: list[str] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    marked: list[str] = field(default_factory=list)


def merge3(base: list[str], ours: list[str], theirs: list[str]) -> Merged:
    """Deterministic three-way line merge; lines keep their newlines."""

    result = Merged()
    z = a = b = 0
    for z_match, z_end, a_match, a_end, b_match, b_end in _sync_regions(base, ours, theirs):
        mine, yours, old = ours[a:a_match], theirs[b:b_match], base[z:z_match]
        if mine or yours:
            if mine == yours:
                chosen: list[str] | None = mine
            elif mine == old:
                chosen = yours
            elif yours == old:
                chosen = mine
            else:
                chosen = None
            if chosen is not None:
                result.lines.extend(chosen)
                result.marked.extend(chosen)
            else:
                result.conflicts.append({
                    "ancestor_lines": [z + 1, z_match], "ours_lines": [a + 1, a_match], "theirs_lines": [b + 1, b_match],
                    "ancestor": "".join(old), "ours": "".join(mine), "theirs": "".join(yours),
                })
                result.marked.extend(_marker_block(mine, old, yours))
        same = base[z_match:z_end]
        result.lines.extend(same)
        result.marked.extend(same)
        z, a, b = z_end, a_end, b_end
    return result


def _marker_block(ours: list[str], base: list[str], theirs: list[str]) -> list[str]:
    def closed(lines: list[str]) -> list[str]:
        return lines[:-1] + [lines[-1] + "\n"] if lines and not lines[-1].endswith("\n") else lines

    return ["<<<<<<< ours (src/)\n", *closed(ours), "||||||| ancestor (previous render)\n", *closed(base), "=======\n",
            *closed(theirs), ">>>>>>> theirs (new render)\n"]


@dataclass
class FileMerge:
    """The merge of one file: its kind, the content to write (None deletes, ``write`` False keeps ours)."""

    kind: str
    data: bytes | None
    write: bool
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    marked: bytes | None = None
    reason: str | None = None


def _style(ours: bytes | None, theirs: bytes | None) -> bytes:
    for data in (ours, theirs):
        if data is not None and b"\n" in data:
            return b"\r\n" if b"\r\n" in data else b"\n"
    return b"\n"


def merge_file(ancestor_sha256: str | None, ancestor: bytes | None, ours: bytes | None, theirs: bytes | None) -> FileMerge:
    """Merge one file's three versions (each None when the file is absent).

    ``ancestor_sha256`` is the ancestor's LF-normalized digest (None: the file
    was absent).  Its content ``ancestor`` may be None although the digest is
    not, when only the digest is known: the decisions by digest still hold,
    and a real merge refuses.
    """

    a, o, t = ancestor_sha256, sha(ours), sha(theirs)
    if ancestor is not None and sha(ancestor) != a:
        raise SocomError("the merge ancestor's content does not have its recorded digest")
    if t == a:
        return FileMerge("kept", ours, False)
    if o == a:
        return FileMerge("render", theirs, True)
    if o == t:
        return FileMerge("same", ours, False)
    if a is not None and ancestor is None:
        raise SocomError(f"the merge ancestor (sha256 {a}) is not stored and the current inputs no longer render it")
    if ancestor is None or ours is None or theirs is None:
        sides = {"ancestor": ancestor is not None, "ours": ours is not None, "theirs": theirs is not None}
        reason = "the file is " + ", ".join(f"{'present' if value else 'absent'} in {key}" for key, value in sides.items())
        return FileMerge("conflict", None, False, [{"presence": sides}], reason=reason)
    merged = merge3(_text(ancestor).splitlines(keepends=True), _text(ours).splitlines(keepends=True),
                    _text(theirs).splitlines(keepends=True))
    newline = _style(ours, theirs)
    if merged.conflicts:
        marked = _bytes("".join(merged.marked))
        return FileMerge("conflict", None, False, merged.conflicts, marked=marked.replace(b"\n", newline) if newline != b"\n" else marked)
    body = _bytes("".join(merged.lines))
    return FileMerge("clean", body.replace(b"\n", newline) if newline != b"\n" else body, True)


# -- checks on a merged or resolved file -----------------------------------------------------


def fence_lines(data: bytes | None) -> list[str]:
    if data is None:
        return []
    return [line.strip() for line in _text(data).splitlines() if _FENCE.search(line)]


def check_merged(path: str, merged: bytes | None, render: bytes | None) -> list[str]:
    """A merged or resolved file keeps the render's fences (same sequence) and stage 4 blocks, with no conflict marker."""

    from .source_apply import parse_blocks

    if merged is None or render is None:
        return [] if merged == render else [f"{path}: the merge keeps the file the render {'deletes' if render is None else 'writes'}"]
    problems = []
    text = _text(merged)
    if any(line.startswith(_MARKERS) for line in text.splitlines()):
        problems.append(f"{path}: conflict markers remain")
    if fence_lines(merged) != fence_lines(render):
        problems.append(f"{path}: its @socom-skeleton fence lines differ from the render's (a fence was dropped, added or moved)")
    try:
        if parse_blocks(text)[1] != parse_blocks(_text(render))[1]:
            problems.append(f"{path}: its stage 4 blocks differ from the render's")
    except SocomError as failure:
        problems.append(f"{path}: {failure}")
    return problems


# -- conflict reports and resolutions ----------------------------------------------------------


def conflict_report_path(item_id: str) -> str:
    return f"{CONFLICT_DIR}/{item_slug(item_id)}.json"


def conflict_marker_root(item_id: str) -> str:
    return f"{CONFLICT_DIR}/{item_slug(item_id)}"


def write_conflict_report(root: Path, item_id: str, rows: list[dict[str, Any]], markers: dict[str, bytes]) -> str:
    """Write the item's conflict report and marker files under build/ (replacing earlier ones); returns the report path."""

    import shutil

    marker_root = root / conflict_marker_root(item_id)
    if marker_root.exists():
        shutil.rmtree(marker_root)
    for path, data in markers.items():
        atomic_write_bytes(marker_root / path, data)
    report = {
        "kind": CONFLICT_KIND,
        "schema_version": CONFLICT_SCHEMA,
        "work_item_id": item_id,
        "files": rows,
        "markers": conflict_marker_root(item_id),
        "resolve": (f"copy each marked file to <dir>/<path> under build/ (not under {CONFLICT_DIR}), resolve every hunk "
                    "keeping the fence lines and stage 4 blocks, then re-run progress apply-order-skeleton with "
                    "--resolutions <dir>"),
    }
    relative = conflict_report_path(item_id)
    atomic_write_json(root / relative, report)
    return relative


def load_resolutions(root: Path, item_id: str, directory: Path | None, conflicts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{path: {"data", "path", "sha256"}} for every conflicting file, from ``directory``; refuses a stale or partial set.

    The item's last conflict report must list each file with the same
    ancestor, ours and theirs digests as now, so a resolution made before a
    later edit of ``src/`` or a later input change is never applied.
    """

    if directory is None or not conflicts:
        return {}
    report_path = root / conflict_report_path(item_id)
    if not report_path.is_file():
        raise SocomError(f"--resolutions needs the conflict report {conflict_report_path(item_id)}: re-run without it first")
    report = load_json(report_path)
    listed = {row["path"]: row for row in report.get("files") or [] if isinstance(row, dict)}
    found: dict[str, dict[str, Any]] = {}
    problems = []
    for path, now in sorted(conflicts.items()):
        row = listed.get(path)
        keys = ("ancestor_sha256", "ours_sha256", "theirs_sha256")
        if row is None or any(row.get(key) != now.get(key) for key in keys):
            problems.append(f"{path}: the conflict report is stale (src/ or the render changed since): re-run without --resolutions")
            continue
        file = directory / path
        if not file.is_file():
            problems.append(f"{path}: no resolved file at {(directory / path).relative_to(root).as_posix()}")
            continue
        data = file.read_bytes()
        found[path] = {"data": data, "path": file.relative_to(root).as_posix(), "sha256": sha(data)}
    if problems:
        raise SocomError("refused, resolutions:\n- " + "\n- ".join(problems[:_SHOWN]))
    return found


def resolution_directory(root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    build = (root / "build").resolve()
    if not path.is_relative_to(build) or path == build:
        raise SocomError("--resolutions must be a directory under build/")
    if path.is_relative_to((root / CONFLICT_DIR).resolve()):
        raise SocomError(f"--resolutions may not lie under {CONFLICT_DIR} (each run replaces the marker files there)")
    if not path.is_dir():
        raise SocomError(f"--resolutions {value} is not a directory")
    return path
