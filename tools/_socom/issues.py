"""CAS-protected workspace process/tool issue ledger."""

from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path
from typing import Any, Callable

from .locking import exclusive_state_lock
from .util import SocomError, atomic_write_json, load_json, stable_id


def issue_path(root: Path) -> Path:
    return root / ".agent" / "WORKSPACE_ISSUES.json"


def _now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_issues(root: Path) -> dict[str, Any]:
    value = load_json(issue_path(root))
    if not isinstance(value, dict):
        raise SocomError("workspace issue ledger root must be an object")
    return value


def audit_issues(value: dict[str, Any]) -> list[str]:
    errors = []
    if value.get("schema_version") != 1:
        errors.append("workspace issue schema_version must be 1")
    if not isinstance(value.get("revision"), int) or value["revision"] < 1:
        errors.append("workspace issue revision must be a positive integer")
    rows = value.get("issues")
    if not isinstance(rows, list):
        return errors + ["workspace issues must be a list"]
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if len(ids) != len(set(ids)):
        errors.append("workspace issue IDs are not unique")
    for row in rows:
        if not isinstance(row, dict):
            errors.append("workspace issue row must be an object")
            continue
        if row.get("status") not in {"open", "resolved"}:
            errors.append(f"{row.get('id')} has invalid status")
        if row.get("kind") not in {"problem", "request", "blocker"}:
            errors.append(f"{row.get('id')} has invalid kind")
        if not str(row.get("summary", "")).strip():
            errors.append(f"{row.get('id')} has no summary")
    return errors


def mutate_issues(
    root: Path,
    expected_revision: int,
    operation: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    path = issue_path(root)
    with exclusive_state_lock(path):
        current = load_issues(root)
        if current["revision"] != expected_revision:
            raise SocomError(
                "workspace issue revision conflict: expected "
                f"{expected_revision}, actual {current['revision']}"
            )
        updated = copy.deepcopy(current)
        operation(updated)
        updated["revision"] += 1
        if errors := audit_issues(updated):
            raise SocomError("issue mutation rejected:\n- " + "\n- ".join(errors))
        atomic_write_json(path, updated)
        return updated


def add_issue(
    value: dict[str, Any],
    *,
    kind: str,
    summary: str,
    details: str,
    reporter: str,
) -> str:
    if not summary.strip():
        raise SocomError("issue summary must not be empty")
    issue_id = stable_id("workspace-issue", kind, summary.strip())
    if any(row["id"] == issue_id for row in value["issues"]):
        raise SocomError(f"workspace issue already exists: {issue_id}")
    value["issues"].append(
        {
            "id": issue_id,
            "kind": kind,
            "status": "open",
            "summary": summary.strip(),
            "details": details.strip(),
            "reported_by": reporter.strip(),
            "reported_at": _now(),
            "resolution": None,
        }
    )
    return issue_id


def set_issue_status(
    value: dict[str, Any],
    issue_id: str,
    *,
    status: str,
    resolution: str | None,
) -> None:
    row = next((row for row in value["issues"] if row["id"] == issue_id), None)
    if not row:
        raise SocomError(f"unknown workspace issue: {issue_id}")
    row["status"] = status
    row["resolution"] = (
        {"summary": resolution.strip(), "resolved_at": _now()}
        if status == "resolved" and resolution
        else None
    )
