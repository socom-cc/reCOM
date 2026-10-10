from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools._socom.constants import EXPECTED_GHIDRA_VERSION
from tools._socom.tracker import load_tracker, next_work


def _run(root: Path, *arguments: str) -> tuple[int, dict]:
    completed = subprocess.run(
        [sys.executable, "tools/socom.py", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout)


def test_progress_next_accepts_trailing_json(root: Path) -> None:
    code, result = _run(root, "progress", "next", "--json")
    assert code == 0
    tracker = json.loads(
        (root / ".agent" / "RECONSTRUCTION_PROGRESS.json").read_text(
            encoding="utf-8"
        )
    )
    assert result["revision"] == tracker["revision"]
    expected = next_work(
        load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    )[:1]
    assert [row["id"] for row in result["work_items"]] == [
        row["id"] for row in expected
    ]


def test_reference_verify(root: Path) -> None:
    code, result = _run(root, "reference", "verify", "--json")
    assert code == 0
    assert result["ok"] is True
    assert result["stored_match"] is True


def test_reference_relocation_query(root: Path) -> None:
    code, result = _run(
        root,
        "reference",
        "relocations",
        "--at",
        "0x1401b4",
        "--size",
        "8",
    )
    assert code == 0
    assert result["match_count"] == 2
    assert result["relocations"][0]["pair_context"] is not None


def test_infrastructure_doctor(root: Path) -> None:
    code, result = _run(
        root, "doctor", "--infrastructure-only", "--ghidra", "--json"
    )
    assert code == 0
    assert result["ok"] is True


def test_registered_alignment_audits(root: Path) -> None:
    for command in (
        ("audit", "agent-surface"),
        ("audit", "workflow-contracts"),
        ("audit", "pipeline-reachability"),
        ("audit", "docs"),
        ("issue", "audit"),
    ):
        code, result = _run(root, *command, "--json")
        assert code == 0, result
        assert result["ok"] is True


def test_live_ghidra_preflight_is_explicitly_targeted(root: Path) -> None:
    code, result = _run(root, "ghidra", "preflight", "--strict", "--json")
    assert code == 0, result
    assert result["ok"] is True
    assert result["project"] == "soCOM"
    assert result["program"] == "socom.elf"
    assert result["language"] == "r5900:LE:32:default"
    assert result["entry_point"] == "00140010"
    assert result["active_ui_program_required"] is False
    assert result["required_ghidra_version"] == EXPECTED_GHIDRA_VERSION
    assert "local_profile_versions" in result
    assert "ghidra_version" not in result


def test_assembly_verification_reads_explicit_ghidra_program(root: Path) -> None:
    code, result = _run(root, "verify", "asm", "main", "--json")
    assert code == 0, result
    assert result["ok"] is True
    assert "Function: main at 00140d00" in result["function"]
    assert "00140d00: addiu sp,sp,-0x30" in result["assembly"]


def test_identical_final_candidate_is_diagnostic_not_acceptance(root: Path) -> None:
    code, result = _run(
        root,
        "verify",
        "final-elf",
        "--candidate",
        "support/socom.elf",
    )
    assert code == 0
    assert result["comparison_ok"] is True
    assert result["acceptance_ready"] is False
    assert result["ok"] is True
    assert result["final_elf_catalog"]["complete"] is False

    code, result = _run(
        root,
        "verify",
        "final-elf",
        "--candidate",
        "support/socom.elf",
        "--acceptance",
    )
    assert code == 1
    assert result["comparison_ok"] is True
    assert result["acceptance_ready"] is False
    assert result["ok"] is False


def test_current_final_catalog_fails_closed_without_crashing(root: Path) -> None:
    code, result = _run(root, "audit", "final-elf-catalog")
    assert code == 1
    assert result["complete"] is False
    assert result["loaded_file_gaps"]


def test_cli_output_is_utf8_when_piped(root) -> None:
    import subprocess
    import sys

    # The error echoes the unknown id, so non-ASCII must survive as UTF-8.
    result = subprocess.run(
        [sys.executable, str(root / "tools" / "socom.py"), "progress", "show", "socom:work:—missing—"],
        capture_output=True,
        cwd=root,
    )
    assert "socom:work:—missing—" in result.stdout.decode("utf-8")
