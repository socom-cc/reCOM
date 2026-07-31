"""Deterministic, manifest-driven functional smoke targets."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .util import SocomError, load_json


def target_directory(root: Path) -> Path:
    return root / "tools" / "functional_verify_targets"


def list_targets(root: Path) -> list[dict[str, Any]]:
    rows = []
    directory = target_directory(root)
    if not directory.is_dir():
        return rows
    for path in sorted(directory.glob("*.json")):
        value = load_json(path)
        if not isinstance(value, dict):
            raise SocomError(f"functional target must be an object: {path}")
        rows.append(
            {
                "id": value.get("id", path.stem),
                "summary": value.get("summary", ""),
                "path": path.relative_to(root).as_posix(),
            }
        )
    return rows


def load_target(root: Path, target: str) -> dict[str, Any]:
    if not target or Path(target).name != target or target.endswith(".json"):
        raise SocomError("functional target must be a manifest stem")
    path = target_directory(root) / f"{target}.json"
    value = load_json(path)
    if not isinstance(value, dict):
        raise SocomError(f"functional target must be an object: {path}")
    command = value.get("command")
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(part, str) and part for part in command)
    ):
        raise SocomError(f"{path}: command must be a non-empty string array")
    if value.get("id", target) != target:
        raise SocomError(f"{path}: target id must equal manifest stem {target!r}")
    timeout = value.get("timeout_seconds", 30)
    if not isinstance(timeout, int) or timeout < 1 or timeout > 600:
        raise SocomError(f"{path}: timeout_seconds must be between 1 and 600")
    expected = value.get("expected_exit_code", 0)
    if not isinstance(expected, int):
        raise SocomError(f"{path}: expected_exit_code must be an integer")
    cwd = root / str(value.get("cwd", "."))
    try:
        cwd.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SocomError(f"{path}: cwd escapes the workspace") from exc
    if not cwd.is_dir():
        raise SocomError(f"{path}: cwd does not exist: {cwd}")
    return {
        **value,
        "id": target,
        "_path": path,
        "_cwd": cwd,
        "timeout_seconds": timeout,
        "expected_exit_code": expected,
    }


def run_target(root: Path, target: str, *, dry_run: bool) -> dict[str, Any]:
    value = load_target(root, target)
    public = {
        key: item for key, item in value.items() if not key.startswith("_")
    }
    report: dict[str, Any] = {
        "target": target,
        "manifest": value["_path"].relative_to(root).as_posix(),
        "dry_run": dry_run,
        "command": value["command"],
        "cwd": value["_cwd"].relative_to(root).as_posix() or ".",
        "expected_exit_code": value["expected_exit_code"],
        "timeout_seconds": value["timeout_seconds"],
        "contract": public.get("contract", {}),
    }
    if dry_run:
        return {"ok": True, **report}
    environment = dict(os.environ)
    for key, item in value.get("environment", {}).items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise SocomError(
                f"{value['_path']}: environment must map strings to strings"
            )
        environment[key] = item
    try:
        completed = subprocess.run(
            value["command"],
            cwd=value["_cwd"],
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=value["timeout_seconds"],
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            **report,
            "timed_out": True,
            "stdout": (exc.stdout or "")[-8000:],
            "stderr": (exc.stderr or "")[-8000:],
        }
    ok = completed.returncode == value["expected_exit_code"]
    return {
        "ok": ok,
        **report,
        "timed_out": False,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-8000:],
        "stderr": completed.stderr[-8000:],
    }
