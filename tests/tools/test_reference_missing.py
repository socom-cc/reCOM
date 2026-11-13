"""A checkout without the untracked reference executable fails cleanly, naming it."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools._socom.constants import (
    REFERENCE_RECORD_PATH,
    REFERENCE_RELATIVE_PATH,
    REFERENCE_SHA256,
    ReferenceMissingError,
    is_reference_path,
    reference_missing_message,
    require_reference,
)
from tools._socom.elf import Elf32File
from tools._socom.util import SocomError, load_json


def _run(root: Path, workspace: Path, *arguments: str) -> tuple[int, dict, str]:
    completed = subprocess.run(
        [sys.executable, "tools/socom.py", "--root", str(workspace), *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout), completed.stderr


def test_the_message_names_the_path_the_hash_and_its_record(root: Path) -> None:
    message = reference_missing_message()
    assert REFERENCE_RELATIVE_PATH in message and "not part of the repository" in message
    assert REFERENCE_SHA256 in message and REFERENCE_RECORD_PATH in message
    record = load_json(root / REFERENCE_RECORD_PATH)
    assert record["path"] == REFERENCE_RELATIVE_PATH and record["sha256"] == REFERENCE_SHA256


def test_require_reference_and_the_elf_reader_raise_the_named_error(tmp_path: Path) -> None:
    with pytest.raises(ReferenceMissingError, match="not part of the repository"):
        require_reference(tmp_path)
    with pytest.raises(ReferenceMissingError, match="not part of the repository"):
        Elf32File(tmp_path / "support" / "socom.elf")
    # Any other missing ELF keeps its plain message.
    with pytest.raises(SocomError, match="ELF does not exist") as raised:
        Elf32File(tmp_path / "build" / "candidate.elf")
    assert not isinstance(raised.value, ReferenceMissingError)
    assert is_reference_path(tmp_path / "support" / "socom.elf")
    assert not is_reference_path(tmp_path / "build" / "socom.elf") and not is_reference_path(None)


def test_doctor_reports_a_named_check_and_runs_the_others(root: Path, tmp_path: Path) -> None:
    code, result, stderr = _run(root, tmp_path, "doctor", "--infrastructure-only")
    assert code == 1 and "Traceback" not in stderr
    checks = {row["name"]: row for row in result["checks"]}
    assert checks["reference-elf"] == {
        "errors": [reference_missing_message()],
        "missing": True,
        "name": "reference-elf",
        "ok": False,
    }
    assert {"tracker", "independence", "toolchain"} <= set(checks)


@pytest.mark.parametrize(
    "command",
    [
        ("reference", "census"),  # the shared census reader
        ("debug", "graph"),  # hashes the file before parsing it
        ("recon", "facts", "--function", "main"),
    ],
)
def test_readers_fail_cleanly_without_the_reference(root: Path, tmp_path: Path, command: tuple[str, ...]) -> None:
    code, result, stderr = _run(root, tmp_path, *command)
    assert code == 2 and "Traceback" not in stderr
    assert result == {"check": "reference-elf", "error": reference_missing_message(), "ok": False}
