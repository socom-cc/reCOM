"""The governed export of the prototype's data types to a Ghidra file archive.

GhidraMCP 6.0.0 has no endpoint that writes a data type archive (`.gdt`), so
on 2026-11-25 the user allowed a second reviewed Ghidra script (the first is
the boundary repair of 2026-10-30): `ExportTypeArchive.java` copies every data
type of `socom.elf` into a new file archive so the release program and later
game versions can reuse the prototype's types. Every other script stays
forbidden.

`export_type_archive` refuses a script whose SHA-256 is not `SCRIPT_SHA256`
and an output outside `support/` or `build/` (the `.gdt` is never tracked;
`support/` and `build/` are git-ignored). It takes a read-only snapshot of
the program's types, sends the pinned script once to `run_script_inline`
(facts in `boundary_repair`'s docstring; the bridge splits `args` at
whitespace, so the output path travels as hex of its UTF-8 bytes), checks
the script's result line, takes the snapshot again and requires it equal,
and hashes the file. A dry run stops before the script.

The snapshot is `ghidra._type_index`'s request (what `ghidra fingerprint`'s
`types` section reads: every `list_data_types` row, which the plugin builds from
`ProgramBasedDataTypeManager.getAllDataTypes()`, as name, category, size and
path) plus the `list_data_type_categories` names. It sees added, removed,
renamed or resized types and renamed categories, not member layouts or a
type's source-archive association. Those are covered inside the script,
which records around the copy the program's `DBHandle.getModCount()`
(`BufferMgr` raises it on every dirty buffer release, so any database write
shows), `getModificationNumber()` (raised by every change event),
`isChanged()`, the type count and `getSourceArchives()`; any difference is a
failure and the script aborts a nested transaction so Ghidra rolls the
script transaction back.

Why copying cannot change the program (Ghidra 12.1.4 sources of
`DataTypeManagerDB`, `FileDataTypeManager`, `StandAloneDataTypeManager`,
`DomainObjectTransactionManager` and `GhidraScript`):

- `archive.addDataTypes(types, DEFAULT_HANDLER, monitor)` calls
  `archive.resolve(type, handler)` for each type. A program type's source
  archive is the program's local archive, whose type is `PROGRAM`, so
  `resolve` takes `resolveDataTypeNoSource` ("dataTypes from a program ...
  don't carry over their identity"); `resolveNoEquivalentFound` drops a
  `PROGRAM` source and `createDataType` gives the copy a new universal ID.
  Every write (`createCategory`, `createDataType`, `resolveSourceArchive`,
  the resolve and equivalence caches, `dataTypeAdded`) goes to the archive;
  the program type is only read.
- Association is a separate call, `associateDataTypeWithArchive`, which the
  script never makes; nor does it open the archive in the tool's data type
  manager, so the GUI cannot associate either.
- `GhidraScript.executeNormal` wraps `run()` in `start()`/`end(true)`; a
  committed transaction with no changes makes `DBHandle.endTransaction`
  return false, so `DomainObjectTransactionManager` neither sets `changed`
  nor adds an undo entry. Nothing saves the program.

Architecture: `FileDataTypeManager.createFileArchive(File, LanguageID,
CompilerSpecID)` exists in 12.1.4; it refuses an existing file and calls
`setProgramArchitecture(language, compilerSpecId, CLEAR, ...)`, so the
archive's data organization is the compiler spec's. The script reopens the
archive read-only and requires language `r5900:LE:32:default`, compiler spec
`default`, a data organization equal to the program's, and no archive
warning.

Lease: the export writes no program state, so it holds no `ghidra-writer`
lease and is not a tracker item. It refuses while any item holds the writer
lease, because a writer's uncommitted edits would be copied and its own
read-backs could race the script on the Swing thread.

A successful export to `support/` writes `.agent/TYPE_ARCHIVE.json`: the
archive's file name (never a directory), SHA-256, size, universal ID and
counts, the program's identity, the script hash and the Ghidra pin. An
export to `build/` is a disposable trial and writes only its report.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from .constants import EXPECTED_GHIDRA_VERSION
from .ghidra import EXPECTED_LANGUAGE, SOCOM_PROGRAM_PATH, SOCOM_PROJECT, _digest, _parse_types
from .util import SocomError, sha256_file

SCRIPT_PATH = "tools/_socom/ghidra_scripts/ExportTypeArchive.java"
# SHA-256 of the script with CRLF line ends read as LF: the exact text sent.
SCRIPT_SHA256 = "488ec9c2efd48ba32f93312d28e903fd7bbce0620335367c96817d3f33b9c6d8"
SCRIPT_CLASS = "ExportTypeArchive"
SCRIPT_ENDPOINT = "run_script_inline"
RESULT_MARK = "SOCOM_TYPE_ARCHIVE_RESULT "
COMPLETED = "=== SCRIPT COMPLETED SUCCESSFULLY ==="
USER_DECISION = "2026-11-25"
RECORD_PATH = ".agent/TYPE_ARCHIVE.json"
RECORD_KIND = "socom-type-archive"
DEFAULT_OUTPUT = "support/socom-types.gdt"
DEFAULT_REPORT = "build/type-archive/report.json"
OUTPUT_ROOTS = ("support", "build")
EXPECTED_COMPILER_SPEC = "default"
KINDS = ("structure", "union", "enum", "typedef", "function_definition", "pointer", "array", "builtin", "other")
CONFLICT_SUFFIX = ".conflict"
_RESULT_LINE = re.compile(re.escape(RESULT_MARK) + r"(\{.*\})\s*$")
_PUBLIC_CLASS = re.compile(r"public\s+class\s+(\w+)")


class TypeArchiveFailure(SocomError):
    """A refused or failed export; `ran` says whether the script may have run."""

    def __init__(self, message: str, *, ran: bool, written: bool = False, response: Any = None) -> None:
        super().__init__(message)
        self.ran = ran
        self.written = written
        self.response = response


def archive_script(root: Path, pinned: str = SCRIPT_SHA256) -> dict[str, Any]:
    """The pinned script text (CRLF read as LF) and its hash."""

    data = (root / SCRIPT_PATH).read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    if digest != pinned:
        raise SocomError(f"{SCRIPT_PATH} has SHA-256 {digest}, not the reviewed {pinned}")
    try:
        source = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SocomError(f"{SCRIPT_PATH} is not ASCII") from exc
    if _PUBLIC_CLASS.findall(source) != [SCRIPT_CLASS] or "extends GhidraScript" not in source:
        raise SocomError(f"{SCRIPT_PATH} must declare exactly one public class {SCRIPT_CLASS} extends GhidraScript")
    return {"path": SCRIPT_PATH, "sha256": digest, "endpoint": SCRIPT_ENDPOINT, "source": source}


def resolve_output(root: Path, value: str) -> Path:
    """An absolute `.gdt` path under support/ or build/ of this checkout."""

    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        parts = resolved.relative_to(root.resolve()).parts
    except ValueError as exc:
        raise SocomError("the type archive may only be written under support/ or build/") from exc
    if len(parts) < 2 or parts[0] not in OUTPUT_ROOTS:
        raise SocomError("the type archive may only be written under support/ or build/")
    if resolved.suffix != ".gdt" or resolved.name == ".gdt":
        raise SocomError(f"{resolved.name} is not a .gdt file name")
    return resolved


def output_root(root: Path, output: Path) -> str:
    return output.relative_to(root.resolve()).parts[0]


def check_output(output: Path, replace: bool) -> None:
    """Refuse an existing archive without --replace, a non-file, or an open (locked) archive."""

    if output.exists():
        if not replace:
            raise SocomError(f"{output.name} exists; pass --replace to overwrite it")
        if not output.is_file():
            raise SocomError(f"{output.name} exists and is not a file")
    if output.parent.is_dir():
        locks = sorted(
            entry.name
            for entry in output.parent.iterdir()
            if entry.name.startswith(output.name + ".") and entry.name.endswith("lock")
        )
        if locks:
            raise SocomError(f"{output.name} has Ghidra lock files {locks}; close the archive in Ghidra first")


def script_arguments(output: Path, replace: bool) -> str:
    return f"{str(output).encode('utf-8').hex()} {'replace' if replace else 'create'}"


def active_writers(tracker: dict[str, Any]) -> list[str]:
    return sorted(
        row["id"]
        for row in tracker.get("work_items", [])
        if row.get("status") == "in_progress" and "ghidra-writer" in row.get("resources", [])
    )


def _paged(bridge: Any, endpoint: str, *, page_size: int, **parameters: object) -> list[str]:
    """GhidraBridge.paged_text over `request` alone, so a dry run's read-only view works."""

    rows: list[str] = []
    offset = 0
    for _ in range(1_000):
        value = bridge.request(endpoint, offset=offset, limit=page_size, **parameters)
        if not isinstance(value, str):
            raise SocomError(f"Ghidra /{endpoint} response is not text")
        page = [line.strip() for line in value.splitlines() if line.strip()]
        if len(page) == 1 and page[0].startswith("No "):
            return rows
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += len(page)
    raise SocomError(f"Ghidra /{endpoint} exceeded 1000 pages")


def type_snapshot(bridge: Any) -> dict[str, Any]:
    """The read-only type snapshot compared before and after the script."""

    # ghidra._type_index's request: an explicitly empty category lists all.
    types = _parse_types(_paged(bridge, "list_data_types", page_size=5_000, category=""))
    categories = sorted(_paged(bridge, "list_data_type_categories", page_size=10_000))
    return {
        "type_count": len(types),
        "category_names": len(categories),
        "types_sha256": _digest(types),
        "categories_sha256": _digest(categories),
        "conflict_names": sorted(row["path"] for row in types if CONFLICT_SUFFIX in row["name"]),
    }


def parse_result(response: Any) -> dict[str, Any]:
    """The script's one result line (printed to the script and the console output)."""

    if not isinstance(response, str):
        raise TypeArchiveFailure(f"{SCRIPT_ENDPOINT} did not run the script: {response!r}", ran=False, response=response)
    results = []
    for line in response.splitlines():
        match = _RESULT_LINE.search(line)
        if match:
            try:
                results.append(json.loads(match.group(1)))
            except json.JSONDecodeError as exc:
                raise TypeArchiveFailure(f"unreadable script result {match.group(1)!r}", ran=True, response=response) from exc
    if not results or any(result != results[0] for result in results):
        raise TypeArchiveFailure("the script printed no single result line", ran=True, response=response)
    if not isinstance(results[0], dict):
        raise TypeArchiveFailure("the script result is not an object", ran=True, response=response)
    return results[0]


def check_result(
    result: dict[str, Any], response: str, *, archive: str, mode: str, live_count: int
) -> list[str]:
    """Every way the result line disagrees with a clean, complete export."""

    problems: list[str] = []
    expected_counts = {"total", *KINDS}
    program_counts = result.get("program_counts")
    archive_counts = result.get("archive_counts")
    if COMPLETED not in response:
        problems.append("the bridge did not report the script as completed")
    if result.get("written") is not True:
        problems.append("the script did not write the archive")
    if result.get("program") != SOCOM_PROGRAM_PATH or result.get("archive") != archive or result.get("mode") != mode:
        problems.append(
            f"the result names {result.get('program')!r} {result.get('archive')!r} {result.get('mode')!r}, "
            f"not {SOCOM_PROGRAM_PATH!r} {archive!r} {mode!r}"
        )
    if not isinstance(program_counts, dict) or set(program_counts) != expected_counts:
        problems.append(f"program counts are {program_counts!r}")
    elif program_counts != archive_counts:
        problems.append(f"archive counts {archive_counts!r} differ from program counts {program_counts!r}")
    elif program_counts["total"] != live_count or sum(program_counts[kind] for kind in KINDS) != live_count:
        problems.append(f"the script counted {program_counts['total']} types; list_data_types lists {live_count}")
    if result.get("program_categories") != result.get("archive_categories"):
        problems.append("the archive categories differ from the program's")
    for key in ("conflict_names", "program_conflict_names", "missing", "extra", "not_equivalent"):
        if result.get(key) != 0:
            problems.append(f"{key} is {result.get(key)!r}, not 0")
    if result.get("archive_architecture") != {"language": EXPECTED_LANGUAGE, "compiler_spec": EXPECTED_COMPILER_SPEC}:
        problems.append(f"the archive architecture is {result.get('archive_architecture')!r}")
    if result.get("data_organization_equal") is not True or result.get("archive_warning") != "NONE":
        problems.append("the archive data organization or warning state is not the program's")
    if not str(result.get("universal_id", "")).lstrip("-").isdigit():
        problems.append(f"the archive universal ID is {result.get('universal_id')!r}")
    before, after = result.get("program_state_before"), result.get("program_state_after")
    if result.get("program_unchanged") is not True or not isinstance(before, dict) or before != after:
        problems.append(f"the script saw the program change: {before!r} -> {after!r}")
    if result.get("problems") != []:
        problems.append("the script reported problems: " + "; ".join(map(str, result.get("problems") or [])))
    return problems


def export_type_archive(
    root: Path,
    bridge: Any,
    output: Path,
    *,
    replace: bool = False,
    dry_run: bool = False,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Export every program type with the pinned script (or, dry, check everything but run nothing)."""

    script = archive_script(root)
    check_output(output, replace)
    mode = "replace" if replace else "create"
    before = type_snapshot(bridge)
    if before["conflict_names"]:
        raise TypeArchiveFailure(f"the program has .conflict types: {before['conflict_names'][:20]}", ran=False)
    log(f"{before['type_count']} types in {before['category_names']} category names; exporting to {output.name} ({mode})")
    summary = {key: value for key, value in script.items() if key != "source"}
    if dry_run:
        return {
            "dry_run": True,
            "script": summary,
            "source": script["source"],
            "archive": output.name,
            "mode": mode,
            "output_directory_exists": output.parent.is_dir(),
            "snapshot": before,
            "bridge_call_count": 0,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    previous = sha256_file(output) if output.is_file() else None
    log(f"running {script['path']} ({script['sha256']}) through {SCRIPT_ENDPOINT}")
    try:
        response = bridge.post_json(SCRIPT_ENDPOINT, code=script["source"], args=script_arguments(output, replace))
    except SocomError as failure:
        # A lost request: the script may have run.
        raise TypeArchiveFailure(str(failure), ran=True, written=output.is_file()) from failure
    result = parse_result(response)
    if result.get("ok") is not True:
        raise TypeArchiveFailure(
            "the script refused or failed: " + "; ".join(map(str, result.get("problems", []))),
            ran=True,
            written=result.get("written") is True,
            response=response,
        )
    problems = check_result(result, response, archive=output.name, mode=mode, live_count=before["type_count"])
    try:
        after = type_snapshot(bridge)
    except SocomError as failure:
        problems.append(f"the after snapshot failed: {failure}")
        after = None
    if after is not None and after != before:
        problems.append(f"the program's types changed: {before!r} -> {after!r}")
    if not output.is_file():
        problems.append(f"{output.name} does not exist after the script")
    if problems:
        raise TypeArchiveFailure("; ".join(problems), ran=True, written=output.is_file(), response=response)
    digest = sha256_file(output)
    return {
        "dry_run": False,
        "script": summary,
        "script_result": result,
        "snapshot": before,
        "archive": {
            "name": output.name,
            "sha256": digest,
            "size": output.stat().st_size,
            "replaced_sha256": previous,
        },
        "bridge_call_count": 1,
    }


def type_archive_record(
    result: dict[str, Any], preflight: dict[str, Any], *, exported_on: _dt.date | None = None
) -> dict[str, Any]:
    """The small tracked record of a successful export (no directory, no local path)."""

    script_result = result["script_result"]
    return {
        "kind": RECORD_KIND,
        "schema_version": 1,
        "archive": result["archive"]["name"],
        "sha256": result["archive"]["sha256"],
        "size": result["archive"]["size"],
        "universal_id": script_result["universal_id"],
        "type_counts": script_result["archive_counts"],
        "category_count": script_result["archive_categories"],
        "pointer_size": script_result["pointer_size"],
        "program": {
            "project": SOCOM_PROJECT,
            "path": SOCOM_PROGRAM_PATH,
            "source_sha256": preflight["source_sha256"],
            "language": script_result["archive_architecture"]["language"],
            "compiler_spec": script_result["archive_architecture"]["compiler_spec"],
        },
        "script": {"path": result["script"]["path"], "sha256": result["script"]["sha256"]},
        "ghidra_version": EXPECTED_GHIDRA_VERSION,
        "user_decision": USER_DECISION,
        "exported_on": (exported_on or _dt.datetime.now(_dt.timezone.utc).date()).isoformat(),
    }
