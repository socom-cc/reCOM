"""Generated progress snapshot, kept in docs/reconstruction/WORKSPACE.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .tracker import next_work
from .util import SocomError, atomic_write_text

BEGIN = "<!-- SOCOM_PROGRESS_BEGIN -->"
END = "<!-- SOCOM_PROGRESS_END -->"
SNAPSHOT_RELPATH = "docs/reconstruction/WORKSPACE.md"


def snapshot_path(root: Path) -> Path:
    return root / SNAPSHOT_RELPATH


def render_snapshot(tracker: dict[str, Any]) -> str:
    counts: dict[str, int] = {}
    for item in tracker["work_items"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    ready = next_work(tracker)
    next_id = ready[0]["id"] if ready else "none"
    open_blockers = sum(
        1 for blocker in tracker.get("blockers", []) if blocker.get("status") == "open"
    )
    unverified_owners = sum(
        1 for owner in tracker.get("owners", []) if owner.get("status") == "unverified"
    )
    lines = [
        BEGIN,
        "### Generated progress snapshot",
        "",
        f"- Tracker revision: `{tracker['revision']}`",
        f"- Next work item: `{next_id}`",
        f"- Work items: {len(tracker['work_items'])} total "
        f"({counts.get('ready', 0)} ready, "
        f"{counts.get('in_progress', 0)} active, "
        f"{counts.get('awaiting_acceptance', 0)} awaiting acceptance, "
        f"{counts.get('accepted', 0)} accepted, "
        f"{counts.get('blocked', 0)} dependency-blocked)",
        f"- Open blockers: {open_blockers}",
        f"- Provisional source owners still unverified: {unverified_owners}",
        "",
        "| Stage | Status |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| `{stage['name']}` | {stage['status']} |"
        for stage in tracker["stages"]
    )
    lines.extend([END, ""])
    return "\n".join(lines)


def replace_snapshot(readme: str, snapshot: str) -> str:
    begin = readme.find(BEGIN)
    end = readme.find(END)
    if begin < 0 or end < 0 or end < begin:
        raise SocomError(f"{SNAPSHOT_RELPATH}: progress markers are missing or malformed")
    end += len(END)
    suffix = readme[end:]
    if suffix.startswith("\r\n"):
        suffix = suffix[2:]
    elif suffix.startswith("\n"):
        suffix = suffix[1:]
    return readme[:begin] + snapshot + suffix


def snapshot_status(root: Path, tracker: dict[str, Any]) -> dict[str, Any]:
    path = snapshot_path(root)
    actual = path.read_text(encoding="utf-8")
    expected = replace_snapshot(actual, render_snapshot(tracker))
    return {"fresh": actual == expected, "expected": expected, "actual": actual}


def write_snapshot(root: Path, tracker: dict[str, Any]) -> None:
    status = snapshot_status(root, tracker)
    atomic_write_text(snapshot_path(root), status["expected"])

