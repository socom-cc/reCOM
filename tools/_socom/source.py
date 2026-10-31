"""Source ownership, trace annotations, and independence audits."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .util import load_json, stable_id

SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".inc", ".s", ".S"}

PROJECT_SPECIFIC_PATTERNS = {
    "foreign reconstruction ID": re.compile(
        r"\b(?!socom:)[a-z][a-z0-9_-]*:"
        r"(?:work|stage|symbol|type|binary|owner|evidence|blocker):",
        re.IGNORECASE,
    ),
    "foreign reconstruction annotation": re.compile(
        r"@(?!socom-)[a-z][a-z0-9_-]*-(?:anchor|artifact)\b",
        re.IGNORECASE,
    ),
    # This workspace's own test modules live under tests/tools/ and are not
    # foreign entry points.
    "foreign reconstruction CLI": re.compile(
        r"(?<!tests/)(?<!tests\\)tools[/\\](?!socom\.py\b)[a-z][a-z0-9_-]*\.py\b",
        re.IGNORECASE,
    ),
}

ANCHOR_RE = re.compile(r"@socom-anchor\s+(socom:anchor:[A-Za-z0-9_.-]+)\s*$")
ARTIFACT_RE = re.compile(
    r"@socom-artifact\s+(defines|emits)\s+(\S+)\s+"
    r"(socom:[A-Za-z0-9_.-]+:[A-Za-z0-9_.:/+-]+)\s*$"
)

AUDIT_ROOTS = (
    ".agent",
    ".codex",
    ".claude",
    "docs",
    "tests",
    "tools",
)

PORTABILITY_ROOTS = (
    ".codex",
    ".claude",
    "docs",
    "tests",
    "tools",
)

ROOT_AUDIT_FILES = (
    ".gitignore",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "CMakeLists.txt",
    "CMakePresets.json",
)

WINDOWS_DRIVE_PATH_RE = re.compile(
    r"""(?<![A-Za-z0-9])[A-Za-z]:[\\/]+[^\s`'"<>|)]*"""
)
WINDOWS_DEVICE_PATH_RE = re.compile(
    r"""(?<!\\)\\\\\?\\[A-Za-z]:\\[^\s`'"<>|)]*"""
)
WINDOWS_UNC_PATH_RE = re.compile(
    r"""(?<![\\A-Za-z0-9])\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9$_.-]+(?:\\[^\s`'"<>|)]*)?"""
)
UNIX_HOME_PATH_RE = re.compile(
    r"""(?<![A-Za-z0-9])/(?:Users|home)/[A-Za-z0-9._-]+(?:/[^\s`'"<>|)]*)?""",
    re.IGNORECASE,
)

PORTABILITY_PATTERNS = {
    "machine-specific Windows path": WINDOWS_DRIVE_PATH_RE,
    "machine-specific Windows device path": WINDOWS_DEVICE_PATH_RE,
    "machine-specific UNC path": WINDOWS_UNC_PATH_RE,
    "machine-specific Unix home path": UNIX_HOME_PATH_RE,
}

GENERIC_LOCAL_IDENTITIES = {
    "admin",
    "administrator",
    "build",
    "ci",
    "claude",
    "codex",
    "desktop",
    "developer",
    "github",
    "gitlab",
    "localhost",
    "root",
    "runner",
    "test",
    "ubuntu",
    "user",
    "windows",
    "workstation",
}


def source_owners(root: Path) -> list[dict[str, Any]]:
    source_root = root / "src"
    result = []
    for path in sorted(source_root.rglob("*"), key=lambda value: value.as_posix().casefold()):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        result.append(
            {
                "id": stable_id("owner", relative.casefold()),
                "path": relative,
                "status": "unverified",
                "authority": "provisional-source",
                "artifacts": [],
            }
        )
    return result


def _audit_files(root: Path) -> set[Path]:
    files: set[Path] = set()
    for name in AUDIT_ROOTS:
        directory = root / name
        if directory.exists():
            files.update(path for path in directory.rglob("*") if path.is_file())
    for name in ROOT_AUDIT_FILES:
        path = root / name
        if path.is_file():
            files.add(path)
    provenance = root / "compiler" / "PROVENANCE.json"
    if provenance.is_file():
        files.add(provenance)
    return files


def _portability_files(root: Path) -> set[Path]:
    files: set[Path] = set()
    for name in PORTABILITY_ROOTS:
        directory = root / name
        if directory.exists():
            files.update(path for path in directory.rglob("*") if path.is_file())
    schema = root / ".agent" / "schema"
    if schema.exists():
        files.update(path for path in schema.rglob("*") if path.is_file())
    for name in (*ROOT_AUDIT_FILES, ".agent/WORKSPACE_ISSUES.json", "compiler/PROVENANCE.json"):
        path = root / name
        if path.is_file():
            files.add(path)
    return files


def _dynamic_machine_patterns(root: Path) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    path_values: list[tuple[str, str | None]] = [
        ("absolute workspace path", str(root.resolve())),
        ("local user profile", os.environ.get("USERPROFILE")),
        ("local user profile", os.environ.get("HOME")),
        ("local user profile", str(Path.home())),
    ]
    seen_paths: set[str] = set()
    for label, value in path_values:
        if not value:
            continue
        for variant in {value, value.replace("\\", "/"), value.replace("/", "\\")}:
            folded = variant.casefold()
            if len(variant) < 3 or folded in seen_paths:
                continue
            seen_paths.add(folded)
            patterns.append((label, re.compile(re.escape(variant), re.IGNORECASE)))

    identity_values = (
        ("local account name", os.environ.get("USERNAME") or os.environ.get("USER")),
        ("local computer name", os.environ.get("COMPUTERNAME")),
    )
    seen_identities: set[str] = set()
    for label, value in identity_values:
        if not value:
            continue
        folded = value.casefold()
        if (
            len(value) < 4
            or folded in GENERIC_LOCAL_IDENTITIES
            or folded in seen_identities
        ):
            continue
        seen_identities.add(folded)
        patterns.append(
            (
                label,
                re.compile(
                    rf"(?<![A-Za-z0-9_-]){re.escape(value)}(?![A-Za-z0-9_-])",
                    re.IGNORECASE,
                ),
            )
        )
    return patterns


def _is_original_path_evidence(value: str) -> bool:
    normalized = re.sub(r"\\+", r"\\", value.replace("/", "\\"))
    normalized = normalized.casefold().rstrip(".,;:")
    return normalized == "z:\\dev" or normalized.startswith("z:\\dev\\")


def audit_independence(root: Path) -> list[dict[str, Any]]:
    operational_files = _portability_files(root)
    files = _audit_files(root) | operational_files
    dynamic_patterns = _dynamic_machine_patterns(root)

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for path in sorted(files, key=lambda value: value.as_posix().casefold()):
        if path.suffix.casefold() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".elf",
            ".exe",
            ".dll",
            ".pyc",
            ".pyo",
        }:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        patterns = list(PROJECT_SPECIFIC_PATTERNS.items())
        if path in operational_files:
            patterns.extend(PORTABILITY_PATTERNS.items())
        patterns.extend(dynamic_patterns)
        for label, pattern in patterns:
            for match in pattern.finditer(text):
                if label == "machine-specific Windows path" and _is_original_path_evidence(
                    match.group(0)
                ):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                relative = path.relative_to(root).as_posix()
                key = (relative, line, label, match.group(0).casefold())
                if key in seen:
                    continue
                seen.add(key)
                findings.append(
                    {"path": relative, "line": line, "rule": label, "match": match.group(0)}
                )
    return findings


def _annotation_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for base in ("src", "include"):
        directory = root / base
        if not directory.is_dir():
            continue
        result.extend(
            path
            for path in directory.rglob("*")
            if path.is_file() and path.suffix in SOURCE_SUFFIXES
        )
    return sorted(result, key=lambda path: path.as_posix().casefold())


def source_artifacts(root: Path) -> dict[str, Any]:
    """Parse the source-trace annotations once for listing and audits."""

    anchors: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in _annotation_files(root):
        relative = path.relative_to(root).as_posix()
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if "@socom-" not in line:
                continue
            value = line.strip().lstrip("/*# ").rstrip("*/ ").strip()
            if "@socom-anchor" in value:
                match = ANCHOR_RE.search(value)
                if not match:
                    errors.append(f"{relative}:{number}: malformed @socom-anchor")
                    continue
                anchors.append(
                    {"id": match.group(1), "path": relative, "line": number}
                )
            elif "@socom-artifact" in value:
                match = ARTIFACT_RE.search(value)
                if not match:
                    errors.append(f"{relative}:{number}: malformed @socom-artifact")
                    continue
                artifacts.append(
                    {
                        "relation": match.group(1),
                        "section": match.group(2),
                        "artifact_id": match.group(3),
                        "path": relative,
                        "line": number,
                    }
                )
            else:
                errors.append(f"{relative}:{number}: unknown soCOM annotation")
    return {
        "anchors": anchors,
        "artifacts": artifacts,
        "errors": errors,
    }


# Evidence identities an annotation may cite.  Tracker schema 6 moved the
# immutable symbol and relocation rows into the reference census.
CENSUS_ID_COLLECTIONS = ("symbols", "relocations")
TRACKER_ID_COLLECTIONS = ("owners", "types", "work_items", "evidence")


def known_artifact_ids(
    tracker: dict[str, Any], census: dict[str, Any]
) -> set[str]:
    """Identities an annotation may cite: census rows plus tracker entities."""

    return {
        str(row.get("id"))
        for state, collections in (
            (census, CENSUS_ID_COLLECTIONS),
            (tracker, TRACKER_ID_COLLECTIONS),
        )
        for collection in collections
        for row in state.get(collection, [])
        if isinstance(row, dict) and row.get("id")
    }


def audit_docblocks(root: Path) -> dict[str, Any]:
    parsed = source_artifacts(root)
    errors = list(parsed["errors"])
    tracker = load_json(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    census = load_json(root / ".agent" / "REFERENCE_CENSUS.json")
    sections = {str(row.get("name")) for row in census.get("sections", [])}
    known_ids = known_artifact_ids(tracker, census)
    anchor_locations: dict[str, list[str]] = {}
    for row in parsed["anchors"]:
        anchor_locations.setdefault(row["id"], []).append(
            f"{row['path']}:{row['line']}"
        )
    for anchor, locations in sorted(anchor_locations.items()):
        if len(locations) != 1:
            errors.append(f"anchor {anchor} is duplicated at {locations}")
    for row in parsed["artifacts"]:
        location = f"{row['path']}:{row['line']}"
        if row["section"] not in sections:
            errors.append(
                f"{location}: unknown ELF section {row['section']!r}"
            )
        if row["artifact_id"] not in known_ids:
            errors.append(
                f"{location}: artifact ID is not present in tracker or "
                f"reference-census evidence: "
                f"{row['artifact_id']}"
            )
    return {
        "ok": not errors,
        "anchor_count": len(parsed["anchors"]),
        "artifact_edge_count": len(parsed["artifacts"]),
        "errors": errors,
    }


def audit_source_trace(root: Path, *, require_complete: bool = False) -> dict[str, Any]:
    parsed = source_artifacts(root)
    docblocks = audit_docblocks(root)
    errors = list(docblocks["errors"])
    by_artifact: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in parsed["artifacts"]:
        by_artifact.setdefault((row["section"], row["artifact_id"]), []).append(row)
    for key, rows in sorted(by_artifact.items()):
        definitions = [row for row in rows if row["relation"] == "defines"]
        if len(definitions) != 1:
            errors.append(
                f"artifact {key[1]} in {key[0]} has {len(definitions)} defining edges"
            )
        locations = {(row["path"], row["line"], row["relation"]) for row in rows}
        if len(locations) != len(rows):
            errors.append(f"artifact {key[1]} contains duplicate trace edges")

    tracker = load_json(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    required_ids = {
        str(row["id"])
        for collection in ("semantic_spans", "storage_contributions")
        for row in tracker.get(collection, [])
        if isinstance(row, dict) and row.get("status") == "accepted" and row.get("id")
    }
    defined_ids = {
        row["artifact_id"]
        for row in parsed["artifacts"]
        if row["relation"] == "defines"
    }
    missing = sorted(required_ids - defined_ids)
    if require_complete and missing:
        errors.append(
            f"{len(missing)} accepted physical artifacts have no defining source edge"
        )
    return {
        "ok": not errors,
        "require_complete": require_complete,
        "artifact_count": len(by_artifact),
        "accepted_artifact_count": len(required_ids),
        "missing_accepted_artifact_ids": missing,
        "errors": errors,
    }
