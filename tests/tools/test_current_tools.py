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


def _write_trace_state(
    root: Path, *, census: dict, tracker: dict | None = None
) -> None:
    """A schema 6 tracker (no symbols/relocations) beside a census fixture."""

    state = {
        "schema_version": 6,
        "owners": [],
        "types": [],
        "work_items": [],
        "evidence": [],
        "semantic_spans": [],
        "storage_contributions": [],
        **(tracker or {}),
    }
    (root / ".agent").mkdir(exist_ok=True)
    (root / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(
        json.dumps(state), encoding="utf-8"
    )
    (root / ".agent" / "REFERENCE_CENSUS.json").write_text(
        json.dumps(census), encoding="utf-8"
    )


def test_docblocks_resolve_census_symbols_relocations_and_tracker_ids(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "unit.cpp").write_text(
        "// @socom-artifact defines .text socom:symbol:6e3ac706f66228048f0e\n"
        "// @socom-artifact emits .text socom:relocation:5feceb66ffc86f38d952\n"
        "// @socom-artifact defines .data socom:owner:unit\n",
        encoding="utf-8",
    )
    census = {
        "sections": [{"name": ".text"}, {"name": ".data"}],
        "symbols": [{"id": "socom:symbol:6e3ac706f66228048f0e", "index": 100}],
        "relocations": [{"id": "socom:relocation:5feceb66ffc86f38d952", "index": 0}],
    }
    _write_trace_state(
        tmp_path, census=census, tracker={"owners": [{"id": "socom:owner:unit"}]}
    )
    report = audit_docblocks(tmp_path)
    assert report["ok"] is True, report["errors"]
    assert report["artifact_edge_count"] == 3


def test_docblocks_reject_unknown_ids_and_ignore_retired_tracker_rows(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "unit.cpp").write_text(
        "// @socom-artifact defines .text socom:symbol:unknown\n"
        "// @socom-artifact defines .text socom:symbol:tracker-only\n"
        "// @socom-artifact defines .bogus socom:symbol:known\n",
        encoding="utf-8",
    )
    _write_trace_state(
        tmp_path,
        census={
            "sections": [{"name": ".text"}],
            "symbols": [{"id": "socom:symbol:known"}],
            "relocations": [],
        },
        # A pre-schema-6 tracker copy is not identity evidence any more.
        tracker={"symbols": [{"id": "socom:symbol:tracker-only"}]},
    )
    report = audit_docblocks(tmp_path)
    assert report["ok"] is False
    assert report["errors"] == [
        "src/unit.cpp:1: artifact ID is not present in tracker or "
        "reference-census evidence: socom:symbol:unknown",
        "src/unit.cpp:2: artifact ID is not present in tracker or "
        "reference-census evidence: socom:symbol:tracker-only",
        "src/unit.cpp:3: unknown ELF section '.bogus'",
    ]


def test_docblocks_resolve_symbols_of_the_stored_reference_census(
    tmp_path: Path, root: Path
) -> None:
    census = json.loads(
        (root / ".agent" / "REFERENCE_CENSUS.json").read_text(encoding="utf-8")
    )
    symbol = next(row for row in census["symbols"] if row["type"] == "FUNC")
    section = next(
        row["name"] for row in census["sections"] if row["index"] == symbol["section_index"]
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "unit.cpp").write_text(
        f"// @socom-artifact defines {section} {symbol['id']}\n", encoding="utf-8"
    )
    (tmp_path / ".agent").mkdir()
    shutil.copyfile(
        root / ".agent" / "RECONSTRUCTION_PROGRESS.json",
        tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json",
    )
    shutil.copyfile(
        root / ".agent" / "REFERENCE_CENSUS.json",
        tmp_path / ".agent" / "REFERENCE_CENSUS.json",
    )
    report = audit_docblocks(tmp_path)
    assert report["ok"] is True, report["errors"]


def test_source_correlation_is_producible_once_its_gate_route_is_registered(
    root: Path,
) -> None:
    report = audits.pipeline_reachability(root, _command_rows())
    assert report["ok"] is True, report["missing"]
    # Planning, the apply route and the gate route are all registered.
    assert "source-correlation" not in {row["stage"] for row in report["deferred"]}
    commands = {row["command"] for row in _command_rows()}
    assert {
        "progress decompose-stage",
        "source plan validate",
        "source annotate",
        "progress apply-source-plan",
        "progress handoff-source-gate",
        "progress accept-source-gate",
    } <= commands
    # Without its gate route the stage has no complete producer.
    report = audits.pipeline_reachability(
        root, [row for row in _command_rows() if row["command"] != "progress accept-source-gate"]
    )
    assert report["ok"] is False
    assert [row["stage"] for row in report["missing"]] == ["source-correlation"]


def test_pipeline_reachability_requires_a_seed_for_a_deferred_stage(
    tmp_path: Path, root: Path
) -> None:
    (tmp_path / ".agent").mkdir()
    tracker = json.loads(
        (root / ".agent" / "RECONSTRUCTION_PROGRESS.json").read_text(encoding="utf-8")
    )
    tracker["work_items"] = [
        row
        for row in tracker["work_items"]
        if not (row.get("stage") == "authored-call-contract" and row.get("kind") == "stage-seed")
    ]
    (tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(
        json.dumps(tracker), encoding="utf-8"
    )
    report = audits.pipeline_reachability(tmp_path, _command_rows())
    assert report["ok"] is False
    assert report["missing"] == [
        {
            "stage": "authored-call-contract",
            "error": "deferred stage lacks a seed and explicit blocker",
        }
    ]


def test_capability_stage_names_are_validated() -> None:
    from tools._socom.capabilities import CAPABILITIES, audit_capabilities

    report = audit_capabilities(_command_rows())
    assert report["ok"] is True, report["errors"]
    staged = {row["id"]: row for row in CAPABILITIES if row.get("stage")}
    # The gate route closes the stage: no blocker is left.
    assert staged["source-correlation"]["status"] == "active" and "blocker" not in staged["source-correlation"]
    assert {"progress handoff-source-gate", "progress accept-source-gate", "audit source-baseline"} <= set(
        staged["source-correlation"]["commands"]
    )
    planning = next(row for row in CAPABILITIES if row["id"] == "source-correlation-planning")
    assert planning["status"] == "active" and "source plan validate" in planning["commands"]
    # The apply route is active and opens the apply items' capability gate.
    apply = staged["source-correlation-apply"]
    assert apply["status"] == "active" and apply["opens"] == ["socom:work:source-correlation-apply-route"]
    assert {"source annotate", "progress apply-source-plan", "progress open-capability-gate"} <= set(apply["commands"])


def test_source_annotation_parser_and_trace_topology(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / ".agent").mkdir()
    (tmp_path / "src" / "unit.cpp").write_text(
        "// @socom-anchor socom:anchor:unit\n"
        "// @socom-artifact defines main socom:symbol:test\n"
        "// @socom-artifact emits main socom:symbol:test\n",
        encoding="utf-8",
    )
    _write_trace_state(
        tmp_path,
        census={
            "sections": [{"name": "main"}],
            "symbols": [{"id": "socom:symbol:test"}],
            "relocations": [],
        },
    )
    parsed = source_artifacts(tmp_path)
    assert len(parsed["anchors"]) == 1
    assert len(parsed["artifacts"]) == 2
    assert audit_docblocks(tmp_path)["ok"] is True
    assert audit_source_trace(tmp_path)["ok"] is True

    # A template instance from a header outside the workspace (MSL) is owned
    # by its source file's emits edge alone; a header's emits edge is not an owner.
    (tmp_path / "src" / "msl.cpp").write_text("// @socom-artifact emits main socom:symbol:msl\n", encoding="utf-8")
    (tmp_path / "src" / "only.h").write_text("// @socom-artifact emits main socom:symbol:hdr\n", encoding="utf-8")
    _write_trace_state(
        tmp_path,
        census={
            "sections": [{"name": "main"}],
            "symbols": [{"id": "socom:symbol:test"}, {"id": "socom:symbol:msl"}, {"id": "socom:symbol:hdr"}],
            "relocations": [],
        },
    )
    errors = audit_source_trace(tmp_path)["errors"]
    assert errors == ["artifact socom:symbol:hdr in main has 0 defining edges"]
    (tmp_path / "src" / "only.h").unlink()
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
