"""Workspace health checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .census import build_census, verify_census
from .constants import ReferenceMissingError, tracker_path
from .ghidra import live_preflight
from .source import audit_independence
from .snapshot import snapshot_status
from .toolchain import verify_toolchain
from .tracker import audit_tracker, load_tracker


def run_doctor(
    root: Path,
    *,
    infrastructure_only: bool,
    check_ghidra: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    try:
        census = build_census(root, include_rows=False)
    except ReferenceMissingError as exc:
        # support/ is untracked: a fresh clone reports the missing file and
        # still runs every check that does not read it.
        reference_check: dict[str, Any] = {"missing": True, "errors": [str(exc)]}
    else:
        reference_check = {"errors": verify_census(census)}
    checks.append(
        {
            "name": "reference-elf",
            "ok": not reference_check["errors"],
            **reference_check,
        }
    )

    tracker_file = tracker_path(root)
    tracker = None
    if tracker_file.is_file():
        tracker = load_tracker(tracker_file)
        tracker_errors = audit_tracker(tracker, strict=True)
    else:
        tracker_errors = [f"missing {tracker_file.relative_to(root).as_posix()}"]
    checks.append(
        {
            "name": "tracker",
            "ok": not tracker_errors,
            "errors": tracker_errors,
        }
    )
    if tracker_file.is_file() and not tracker_errors:
        readme = snapshot_status(root, tracker)
        checks.append(
            {
                "name": "progress-snapshot",
                "ok": readme["fresh"],
                "errors": [] if readme["fresh"] else ["progress snapshot is stale (docs/reconstruction/WORKSPACE.md)"],
            }
        )

    independence = audit_independence(root)
    checks.append(
        {
            "name": "independence",
            "ok": not independence,
            "errors": independence,
        }
    )

    toolchain = verify_toolchain(root, compile_probe=not infrastructure_only)
    toolchain_errors = list(toolchain["errors"])
    if not infrastructure_only and not toolchain["compile_ready"]:
        detail = (
            "valid FLEXlm license is required"
            if toolchain["compile_probe"].get("blocked_by_license")
            else "compile probe did not produce deterministic objects"
        )
        toolchain_errors.append(detail)
    checks.append(
        {
            "name": "toolchain",
            "ok": not toolchain_errors,
            "errors": toolchain_errors,
            "identity_ok": toolchain["identity_ok"],
            "compile_ready": toolchain["compile_ready"],
        }
    )

    if check_ghidra:
        target = next(
            (
                row
                for row in (tracker or {}).get("verification_targets", [])
                if row.get("id") == "socom:verification:ghidra-program"
            ),
            {},
        )
        live = live_preflight(root)
        checks.append(
            {
                "name": "ghidra-live-preflight",
                "ok": live["ok"],
                "errors": live["errors"],
                "tracker_status": target.get("status"),
                "baseline_receipt_sha256": target.get(
                    "baseline_receipt_sha256"
                ),
                "current_receipt_sha256": target.get("current_receipt_sha256"),
                "details": live,
            }
        )

    return {
        "mode": "infrastructure-only" if infrastructure_only else "full",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
    }
