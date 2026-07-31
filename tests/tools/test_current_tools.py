from __future__ import annotations

import json
import shutil
from pathlib import Path

from tools._socom import audits
from tools._socom.cli import _command_rows
from tools._socom.final_catalog import final_elf_catalog
from tools._socom.guards import run_guard
from tools._socom.reference import query_relocations
from tools._socom.source import audit_docblocks, audit_source_trace, source_artifacts


def test_relocation_query_joins_symbols_and_hi16_lo16_pairs(census: dict) -> None:
    report = query_relocations(census, at="0x1401b4", size=8, limit=10)
    assert report["match_count"] == 2
    assert [row["type"] for row in report["relocations"]] == [
        "R_MIPS_HI16",
        "R_MIPS_LO16",
    ]
    assert report["relocations"][0]["symbol"]["index"] == 4
    assert report["relocations"][0]["pair_context"]["role"] == "hi16"
    assert report["relocations"][1]["pair_context"]["role"] == "lo16"


def test_source_annotation_parser_and_trace_topology(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / ".agent").mkdir()
    (tmp_path / "src" / "unit.cpp").write_text(
        "// @socom-anchor socom:anchor:unit\n"
        "// @socom-artifact defines main socom:symbol:test\n"
        "// @socom-artifact emits main socom:symbol:test\n",
        encoding="utf-8",
    )
    (tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(
        json.dumps(
            {
                "symbols": [{"id": "socom:symbol:test"}],
                "relocations": [],
                "owners": [],
                "types": [],
                "work_items": [],
                "evidence": [],
                "semantic_spans": [],
                "storage_contributions": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".agent" / "REFERENCE_CENSUS.json").write_text(
        json.dumps({"sections": [{"name": "main"}]}), encoding="utf-8"
    )
    parsed = source_artifacts(tmp_path)
    assert len(parsed["anchors"]) == 1
    assert len(parsed["artifacts"]) == 2
    assert audit_docblocks(tmp_path)["ok"] is True
    assert audit_source_trace(tmp_path)["ok"] is True

    with (tmp_path / "src" / "unit.cpp").open("a", encoding="utf-8") as stream:
        stream.write("// @socom-anchor socom:anchor:unit\n")
    report = audit_docblocks(tmp_path)
    assert report["ok"] is False
    assert any("duplicated" in error for error in report["errors"])


def test_current_source_guards_reject_targeted_constructs(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "bad.cpp"
    source.write_text(
        "int value = *(int *)((char *)object + 0x14);\n"
        "void FakeRuntimeProvider();\n"
        "void call() { FUN_00123456(); }\n",
        encoding="utf-8",
    )
    assert run_guard(tmp_path, "raw-offset")["ok"] is False
    assert run_guard(tmp_path, "provider")["ok"] is False
    assert run_guard(tmp_path, "original-symbol")["ok"] is False


def test_retired_surface_normalizes_wrapped_terms(tmp_path: Path) -> None:
    (tmp_path / "role.md").write_text(
        ("Binary" + "\n" + "Ninja"), encoding="utf-8"
    )
    report = audits.retired_surface(tmp_path)
    assert report["ok"] is False
    assert report["findings"] == [{"path": "role.md", "where": "content"}]


def test_agent_surface_rejects_mirror_authority_drift(
    tmp_path: Path, root: Path
) -> None:
    shutil.copytree(root / ".codex", tmp_path / ".codex")
    shutil.copytree(root / ".claude", tmp_path / ".claude")
    shutil.copyfile(root / "CLAUDE.md", tmp_path / "CLAUDE.md")
    mirror = tmp_path / ".claude" / "skills" / "socom-ghidra-workflow" / "SKILL.md"
    mirror.write_text(
        mirror.read_text(encoding="utf-8").replace(
            "Root `AGENTS.md` is authoritative. ", ""
        ),
        encoding="utf-8",
    )
    report = audits.agent_surface(tmp_path, _command_rows())
    assert report["ok"] is False
    assert any("omits root authority" in error for error in report["errors"])


def test_final_elf_catalog_is_incomplete_for_current_reference(root: Path) -> None:
    report = final_elf_catalog(root)
    assert report["ok"] is False
    assert report["complete"] is False
    assert report["loaded_file_gaps"]
    assert report["loaded_memory_gaps"]
    assert report["excluded_reference_evidence_rows"] > 0


def test_final_elf_catalog_accepts_complete_synthetic_semantics(
    tmp_path: Path, root: Path
) -> None:
    (tmp_path / "support").mkdir()
    (tmp_path / ".agent").mkdir()
    target = tmp_path / "support" / "socom.elf"
    shutil.copyfile(root / "support" / "socom.elf", target)
    from tools._socom.elf import Elf32File

    elf = Elf32File(target)
    segments = list(elf.load_segments())
    memory_start = min(row.virtual_address for row in segments)
    memory_end = max(row.virtual_address + row.memory_size for row in segments)
    tracker = {
        "semantic_spans": [
            {
                "id": "socom:semantic:complete",
                "status": "accepted",
                "classification": "code",
                "file_range": [0, len(elf.data)],
                "memory_range": [memory_start, memory_end],
            }
        ],
        "storage_contributions": [],
    }
    (tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(
        json.dumps(tracker), encoding="utf-8"
    )
    report = final_elf_catalog(tmp_path)
    assert report["ok"] is True
    assert report["whole_file_gaps"] == []
    assert report["loaded_memory_gaps"] == []


def test_final_elf_catalog_rejects_accepted_overlap(
    tmp_path: Path, root: Path
) -> None:
    (tmp_path / "support").mkdir()
    (tmp_path / ".agent").mkdir()
    target = tmp_path / "support" / "socom.elf"
    shutil.copyfile(root / "support" / "socom.elf", target)
    spans = [
        {
            "id": f"socom:semantic:{index}",
            "status": "accepted",
            "classification": "data",
            "file_range": interval,
            "memory_range": None,
        }
        for index, interval in enumerate(([0, 100], [50, 150]), 1)
    ]
    (tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(
        json.dumps({"semantic_spans": spans, "storage_contributions": []}),
        encoding="utf-8",
    )
    report = final_elf_catalog(tmp_path)
    assert report["ok"] is False
    assert report["file_overlaps"]
