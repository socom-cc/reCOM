"""Stage 4 owner plans and the source-correlation decomposition (synthetic and reference)."""

from __future__ import annotations

import copy
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from tools._socom import audits, cli
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.source_plan import (
    SKELETON_REASON,
    SOURCE_APPLY_ROUTE_ID,
    SOURCE_PLAN_KIND,
    SOURCE_SEED_ID,
    SOURCE_STAGE,
    apply_reservations,
    derive_annotations,
    graph_digest,
    input_section_text,
    loaded_section_lookup,
    plan_evidence,
    plan_skeleton,
    planning_scopes,
    scope_key,
    validate_source_plan,
)
from tools._socom.tracker import (
    RECON_SEED_ID,
    accept_work,
    audit_tracker,
    claim_work,
    decompose_source_correlation,
    load_tracker,
    next_work,
    refresh_ready_and_stages,
    work_packet,
)
from tools._socom.util import SocomError

MAIN = lambda address: "main"  # noqa: E731 - every synthetic artifact lies in main


def _row(identity: str, kind: str, address: int, size: int, window: str, section: str, **fields) -> dict:
    row = {
        "id": f"socom:{identity}:0x{address:x}",
        "kind": kind,
        "address": f"0x{address:x}",
        "end": f"0x{address + size:x}",
        "size": size,
        "window": window,
        "input_section": {"basis": "section-symbol envelope", "name": section},
        "cluster": None,
        "tu_candidates": fields.pop("tu", []),
        "signals": fields.pop("signals", []),
        "classification": fields.pop("classification", {"candidate": "authored", "library": None, "evidence": []}),
    }
    if kind == "gap":
        row.update(fill="zero", padding=True, labels=[])
    else:
        names = fields.pop("names")
        row.update(binding=names[0][1], names=[{"name": name, "binding": binding} for name, binding in names])
    row.update(fields)
    return row


CODE, DATA = "socom:window:0x140000", "socom:window:0x426400"
SCE = {"candidate": "provider", "library": "SCE", "evidence": []}
UNIT_A = [{"tu": "a.cpp", "strength": "strong", "via": ["dwarf-cu"], "sinit_order": None}]


def synthetic_graph() -> dict:
    """Two authored segments around one SCE segment, plus unsliced data."""

    rows = [
        _row("function", "function", 0x140000, 16, CODE, ".text", names=[("a_first", "GLOBAL")], tu=UNIT_A,
             signals=[{"signal": "dwarf-cu", "strength": "strong", "path": "Z:\\dev\\gamez\\zFoo\\a.cpp", "tu": "a.cpp"}]),
        _row("function", "function", 0x140010, 8, CODE, ".text", names=[("Get__4CBoxFv", "13")], tu=UNIT_A),
        _row("gap", "gap", 0x140018, 8, CODE, ".text", classification={"candidate": "compiler-generated", "library": None, "evidence": []}),
        _row("function", "function", 0x140020, 16, CODE, ".text", names=[("sceFooInit", "GLOBAL")], classification=SCE, gnu_object="0x140020"),
        _row("function", "function", 0x140030, 16, CODE, ".text", names=[("sceFooHelper", "GLOBAL")], classification=SCE, gnu_object="0x140020"),
        _row("function", "function", 0x140040, 16, CODE, ".text", names=[("b_main", "GLOBAL")],
             tu=[{"tu": "b.cpp", "strength": "strong", "via": ["sinit"], "sinit_order": 1}]),
        _row("function", "function", 0x140050, 8, CODE, ".text", names=[("__sinit_b_cpp", "LOCAL")],
             classification={"candidate": "compiler-generated", "library": None, "evidence": []}),
        _row("data", "data", 0x426470, 8, DATA, ".rodata", names=[("@12", "LOCAL")],
             classification={"candidate": "compiler-generated", "library": None, "evidence": []}),
        _row("data", "data", 0x426480, 4, DATA, ".data", names=[("g_shared", "GLOBAL")]),
        _row("gap", "gap", 0x426484, 12, DATA, ".data", classification={"candidate": "compiler-generated", "library": None, "evidence": []}),
        _row("data", "data", 0x4264a0, 16, DATA, ".rodata", names=[("sceTable", "LOCAL")], classification=SCE),
        _row("data", "data", 0x480000, 4, DATA, ".bss", names=[("g_zero", "GLOBAL")]),
    ]
    ids = [row["id"] for row in rows]
    segment = lambda number, members, data, mix, units: {  # noqa: E731
        "id": f"socom:source-segment:{number:020x}",
        "segment_number": number,
        "window": CODE,
        "start": rows[members[0]]["address"],
        "end": rows[members[-1]]["end"],
        "function_count": sum(mix.values()),
        "artifacts": [ids[index] for index in members],
        "data": [ids[index] for index in data],
        "classification_mix": mix,
        "tu_candidates": [{"tu": unit, "functions": 1, "strongest": "strong", "sinit_order": None} for unit in units],
        "boundary": {},
    }
    graph = {
        "kind": "socom-source-graph",
        "schema_version": 1,
        "source_sha256": REFERENCE_SHA256,
        "segment_size": 200,
        "windows": [{"id": CODE, "kind": "code"}, {"id": DATA, "kind": "data"}],
        "units": [
            {"tu": "a.cpp", "paths": ["Z:\\dev\\gamez\\zFoo\\a.cpp"]},
            {"tu": "b.cpp", "paths": []},
        ],
        "gnu_objects": [{"address": "0x140020", "functions": [ids[3], ids[4]], "end_basis": "next GNU anchor", "library": "SCE"}],
        "artifacts": rows,
        "segments": [
            segment(1, [0, 1], [7], {"authored": 2}, ["a.cpp"]),
            segment(2, [3, 4], [10], {"provider:SCE": 2}, []),
            segment(3, [5, 6], [], {"authored": 1, "compiler-generated": 1}, ["b.cpp"]),
        ],
    }
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def undecomposed(tracker: dict) -> dict:
    """The tracker as stage 4 decomposition finds it: stage 3 accepted, a bare seed."""

    tracker = copy.deepcopy(tracker)
    tracker["work_items"] = [
        row for row in tracker["work_items"] if row["stage"] != SOURCE_STAGE or row["id"] == SOURCE_SEED_ID
    ]
    seed = next(row for row in tracker["work_items"] if row["id"] == SOURCE_SEED_ID)
    seed.update(kind="stage-seed", title="Decompose and schedule source-correlation work", status="blocked",
                dependencies=[RECON_SEED_ID], resources=[], selection=None, batch=None, lease=None, handoff=None, evidence=[])
    for key in ("accepted", "review_history", "source_gate"):
        seed.pop(key, None)
    stage = next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)
    # The real stage 4 is accepted: drop its decomposition, baseline and amendments.
    for key in ("decomposition", "baseline", "baseline_history", "amendments"):
        stage.pop(key, None)
    stage["accepted_evidence"] = []
    refresh_ready_and_stages(tracker)
    return tracker


@pytest.fixture(scope="module")
def stage3_tracker(root: Path) -> dict:
    tracker = undecomposed(load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json"))
    assert audit_tracker(tracker, strict=True) == []
    return tracker


SEGMENT_1 = "segment:socom:source-segment:00000000000000000001"
SEGMENT_3 = "segment:socom:source-segment:00000000000000000003"
FALLBACK = "fallback to all of src: no neighbouring unit shares the TU-name prefix of b.cpp"
INFERENCE = "a.cpp has no path or provisional-file evidence; the nearest units with its TU-name prefix lie in src/gamez/zFoo"
DIRECTORIES = {
    SEGMENT_1: {"directories": ["src/gamez/zFoo"], "inferred": False, "reason": None},
    SEGMENT_3: {"directories": ["src"], "inferred": False, "reason": FALLBACK},
}
# Segment 1's reservation inferred instead of evidenced.
INFERRED = {**DIRECTORIES, SEGMENT_1: {"directories": ["src/gamez/zFoo"], "inferred": True, "reason": INFERENCE}}


def decompose(tracker: dict, graph: dict, directories: dict | None = None) -> dict:
    tracker = copy.deepcopy(tracker)
    decompose_source_correlation(tracker, graph, directories or DIRECTORIES)
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    return tracker


@pytest.fixture()
def synthetic(stage3_tracker: dict) -> tuple[dict, dict]:
    graph = synthetic_graph()
    return decompose(stage3_tracker, graph), graph


# -- scopes and decomposition ---------------------------------------------------


def test_planning_scopes_partition_the_graph() -> None:
    graph = synthetic_graph()
    scopes = planning_scopes(graph)
    ids = [row["id"] for row in graph["artifacts"]]
    assert [scope_key(entry["scope"]) for entry in scopes] == [
        "segment:socom:source-segment:00000000000000000001",
        "provider:SCE",
        "segment:socom:source-segment:00000000000000000003",
        "data:data",
        "data:bss",
    ]
    # The code gap between two segments goes with the segment before it.
    assert scopes[0]["artifacts"] == [ids[0], ids[1], ids[2], ids[7]]
    assert scopes[1]["artifacts"] == [ids[3], ids[4], ids[10]]
    assert scopes[3]["artifacts"] == [ids[8], ids[9]] and scopes[4]["artifacts"] == [ids[11]]
    held = [identity for entry in scopes for identity in entry["artifacts"]]
    assert sorted(held) == sorted(ids) and len(held) == len(set(held))


def test_apply_reservations_keep_the_existing_module_spelling(tmp_path: Path) -> None:
    (tmp_path / "src" / "gamez" / "zfoo").mkdir(parents=True)
    (tmp_path / "src" / "Apps" / "FTS").mkdir(parents=True)
    (tmp_path / "src" / "Apps" / "FTS" / "b.cpp").write_text("", encoding="utf-8")
    # Providers reserve nothing: they have no source body.  b.cpp has no
    # original ELF path: a provisional file's name alone is an inference the
    # plan must confirm.
    assert apply_reservations(tmp_path, synthetic_graph()) == {
        SEGMENT_1: {"directories": ["src/gamez/zfoo"], "inferred": False, "basis": "path", "reason": None},
        SEGMENT_3: {
            "directories": ["src/Apps/FTS"],
            "inferred": True,
            "basis": "provisional-name",
            "reason": "inferred by name: b.cpp has no original ELF path; only a provisional file of that name lies in src/Apps/FTS",
        },
    }


def _renamed(graph: dict, unit: str) -> dict:
    """The synthetic graph with segment 3's unit b.cpp renamed."""

    graph = copy.deepcopy(graph)
    graph["segments"][2]["tu_candidates"][0]["tu"] = unit
    graph["units"][1]["tu"] = unit
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def test_apply_reservations_infer_a_directory_from_neighbouring_prefixes(tmp_path: Path) -> None:
    (tmp_path / "src" / "gamez" / "zfoo").mkdir(parents=True)
    # a_two.cpp has no evidence; a.cpp, two segments away (past the SCE
    # segment), shares its prefix and has a Z:\dev path.
    reservation = apply_reservations(tmp_path, _renamed(synthetic_graph(), "a_two.cpp"))[SEGMENT_3]
    assert reservation["directories"] == ["src/gamez/zfoo"] and reservation["inferred"] is True
    assert "a_two.cpp has no path or provisional-file evidence" in reservation["reason"]
    assert "prefix 'a' (segment 001 a.cpp)" in reservation["reason"]


def test_apply_reservations_fall_back_to_src_only_without_an_inference(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    reservation = apply_reservations(tmp_path, synthetic_graph())[SEGMENT_3]
    assert reservation == {"directories": ["src"], "inferred": False, "basis": "fallback", "reason": FALLBACK}


def test_decomposition_builds_file_only_plans_blocked_applies_and_a_gate(synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    assert audit_tracker(tracker, strict=True) == []
    rows = [row for row in tracker["work_items"] if row["stage"] == SOURCE_STAGE]
    assert Counter(row["kind"] for row in rows) == {
        "source-plan-segment": 2,
        "source-apply-segment": 2,
        "source-plan-provider": 1,
        "source-apply-provider": 1,
        "source-data-reconcile": 2,
        "capability-gate": 1,
        "stage-gate": 1,
    }
    by_id = {row["id"]: row for row in rows}
    plans = ["socom:work:source-segment-001", "socom:work:source-provider-sce", "socom:work:source-segment-003"]
    reconciles = ["socom:work:source-data-data", "socom:work:source-data-bss"]
    for plan in plans:
        assert by_id[plan]["dependencies"] == [RECON_SEED_ID]
        assert by_id[plan]["resources"] == ["build/source-plans"]
        assert by_id[plan]["batch"]["graph_sha256"] == graph["graph_sha256"]
        assert by_id[f"{plan}-apply"]["dependencies"] == [plan, *reconciles, SOURCE_APPLY_ROUTE_ID]
    assert by_id["socom:work:source-segment-001-apply"]["resources"] == ["src/gamez/zFoo"]
    assert by_id["socom:work:source-segment-001-apply"]["batch"]["resource_inferred"] is False
    # A provider apply writes nothing under src/ and reserves nothing.
    provider_apply = by_id["socom:work:source-provider-sce-apply"]
    assert provider_apply["resources"] == [] and "directories" not in provider_apply["batch"]
    fallback = by_id["socom:work:source-segment-003-apply"]
    assert fallback["resources"] == ["src"] and fallback["batch"]["resource_reason"] == FALLBACK
    for reconcile in reconciles:
        assert sorted(by_id[reconcile]["dependencies"]) == sorted(plans)
    gate = by_id[SOURCE_SEED_ID]
    assert gate["kind"] == "stage-gate" and set(gate["dependencies"]) == {f"{plan}-apply" for plan in plans} | set(reconciles)
    assert not any("ghidra" in value for row in rows for value in row["resources"])
    assert {row["id"] for row in next_work(copy.deepcopy(tracker)) if row["stage"] == SOURCE_STAGE} == set(plans)
    stage = next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)
    assert stage["status"] == "active"
    assert stage["decomposition"]["provider_libraries"] == ["SCE"] and stage["decomposition"]["data_kinds"] == ["data", "bss"]
    assert stage["decomposition"]["inferred_reservations"] == []
    assert stage["decomposition"]["fallback_reservations"] == [
        {"item": "socom:work:source-segment-003-apply", "reason": FALLBACK}
    ]
    with pytest.raises(SocomError, match="already decomposed"):
        decompose_source_correlation(tracker, graph, DIRECTORIES)


def test_an_inferred_reservation_is_recorded_on_the_apply_and_the_decomposition(stage3_tracker: dict) -> None:
    tracker = decompose(stage3_tracker, synthetic_graph(), INFERRED)
    assert audit_tracker(tracker, strict=True) == []
    apply = next(row for row in tracker["work_items"] if row["id"] == "socom:work:source-segment-001-apply")
    assert apply["resources"] == ["src/gamez/zFoo"]
    assert apply["batch"]["resource_inferred"] is True and apply["batch"]["resource_reason"] == INFERENCE
    record = next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)["decomposition"]
    assert record["inferred_reservations"] == [
        {"item": "socom:work:source-segment-001-apply", "directories": ["src/gamez/zFoo"], "reason": INFERENCE}
    ]
    claim_work(tracker, "socom:work:source-segment-001", "mapper", 30)
    packet = work_packet(tracker, "socom:work:source-segment-001", "mapper")
    assert any("confirm or correct" in line and INFERENCE in line for line in packet["validation"])


def test_the_apply_route_gate_cannot_be_claimed_and_keeps_applies_blocked(synthetic: tuple[dict, dict]) -> None:
    tracker, _graph = synthetic
    with pytest.raises(SocomError, match="capability gate"):
        claim_work(tracker, SOURCE_APPLY_ROUTE_ID, "anyone", 30)
    # Every plan and reconcile accepted: the applies still wait for the route.
    for row in tracker["work_items"]:
        if row["kind"] in ("source-plan-segment", "source-plan-provider", "source-data-reconcile"):
            row.update(status="accepted", handoff={"owner": "mapper"}, accepted={"by": "reviewer"})
    refresh_ready_and_stages(tracker)
    statuses = {row["status"] for row in tracker["work_items"] if row["kind"].startswith("source-apply-")}
    assert statuses == {"blocked"}
    assert next(row for row in tracker["work_items"] if row["id"] == SOURCE_APPLY_ROUTE_ID)["status"] == "blocked"
    with pytest.raises(SocomError, match="capability gate"):
        accept_work(tracker, SOURCE_APPLY_ROUTE_ID, "reviewer", ["evidence"])


def test_decomposition_preconditions(stage3_tracker: dict) -> None:
    graph = synthetic_graph()
    tracker = copy.deepcopy(stage3_tracker)
    next(row for row in tracker["stages"] if row["name"] == "ghidra-reconstruction").pop("baseline")
    with pytest.raises(SocomError, match="recorded baseline"):
        decompose_source_correlation(tracker, graph, DIRECTORIES)
    tampered = copy.deepcopy(graph)
    tampered["segments"][0]["data"] = []
    with pytest.raises(SocomError, match="differs from its graph_sha256"):
        decompose_source_correlation(copy.deepcopy(stage3_tracker), tampered, DIRECTORIES)
    with pytest.raises(SocomError, match="no src/ directory"):
        decompose_source_correlation(copy.deepcopy(stage3_tracker), graph, {})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda by_id: by_id["socom:work:source-segment-001"].update(resources=["src"]), "not file-only"),
        (lambda by_id: by_id["socom:work:source-segment-001"].update(dependencies=[]), "accepted ghidra-reconstruction gate"),
        (lambda by_id: by_id["socom:work:source-segment-001-apply"].update(resources=["ghidra-writer"]), "Ghidra resource"),
        (lambda by_id: by_id["socom:work:source-segment-001-apply"]["dependencies"].pop(), "every data reconcile"),
        (lambda by_id: by_id["socom:work:source-data-bss"]["dependencies"].pop(), "every source plan item"),
        (lambda by_id: by_id[SOURCE_APPLY_ROUTE_ID].update(status="ready"), "must stay blocked"),
        (lambda by_id: by_id[SOURCE_SEED_ID]["dependencies"].pop(), "gate does not depend"),
        (lambda by_id: by_id["socom:work:source-provider-sce"]["batch"].update(graph_sha256="0" * 64), "different source graph"),
        (lambda by_id: by_id["socom:work:source-provider-sce"]["batch"]["scope"].update(library="newlib"), "differs from the"),
        (lambda by_id: by_id["socom:work:source-provider-sce-apply"].update(resources=["src/providers/sce"]),
         "a provider apply reserves no resource"),
        (lambda by_id: by_id["socom:work:source-provider-sce-apply"]["batch"].update(directories=[]),
         "a provider apply reserves no resource"),
        (lambda by_id: by_id["socom:work:source-segment-001-apply"]["batch"].pop("resource_inferred"),
         "whether its reservation is inferred"),
        (lambda by_id: by_id["socom:work:source-segment-001-apply"]["batch"].update(resource_inferred=True),
         "inferred reservation needs a reason"),
        (lambda by_id: by_id["socom:work:source-segment-003-apply"]["batch"].update(resource_reason=None),
         "without the reason no inference was possible"),
        (lambda by_id: by_id["socom:work:source-segment-001-apply"]["batch"].update(
            resource_inferred=True, resource_reason="x"), "inferred and fallback reservations"),
    ],
)
def test_audit_rejects_broken_source_structure(synthetic: tuple[dict, dict], change, message: str) -> None:
    tracker, _graph = synthetic
    broken = copy.deepcopy(tracker)
    change({row["id"]: row for row in broken["work_items"]})
    assert any(message in error for error in audit_tracker(broken)), audit_tracker(broken)


def test_pairing_audit_and_removed_applies(synthetic: tuple[dict, dict]) -> None:
    tracker, _graph = synthetic
    broken = copy.deepcopy(tracker)
    broken["work_items"] = [row for row in broken["work_items"] if row["id"] != "socom:work:source-segment-003-apply"]
    errors = audit_tracker(broken)
    assert any("pairing is incomplete" in error for error in errors)


def test_packets_route_mapper_worker_and_verifier(synthetic: tuple[dict, dict]) -> None:
    tracker, _graph = synthetic
    claim_work(tracker, "socom:work:source-provider-sce", "mapper", 30)
    packet = work_packet(tracker, "socom:work:source-provider-sce", "mapper")
    assert packet["role"] == "socom-source-owner-mapper" and packet["skill"] == "socom-provider-boundary"
    assert packet["allowed_paths"] == [
        "build/source-plans/socom-work-source-provider-sce-evidence.json",
        "build/source-plans/socom-work-source-provider-sce.json",
        "build/source-plans/mapper/",
    ]
    assert packet["scratch_dir"] == "build/source-plans/mapper/" and packet["reservation"] is None
    assert any("source plan validate" in line and "--check" in line for line in packet["validation"])
    assert any("source plan draft --item socom:work:source-provider-sce" in line for line in packet["validation"])
    assert any("source plan draft --check" in line for line in packet["validation"])
    claim_work(tracker, "socom:work:source-segment-001", "mapper", 30)
    segment = work_packet(tracker, "socom:work:source-segment-001", "mapper")
    assert segment["skill"] == "socom-source-model-recovery"
    assert segment["reservation"] == {
        "apply_item": "socom:work:source-segment-001-apply", "directories": ["src/gamez/zFoo"], "inferred": False, "reason": None,
    }
    apply = next(row for row in tracker["work_items"] if row["id"] == "socom:work:source-segment-001-apply")
    apply["status"] = "ready"
    claim_work(tracker, apply["id"], "worker", 30)
    packet = work_packet(tracker, apply["id"], "worker")
    assert packet["role"] == "socom-source-worker" and packet["allowed_paths"] == ["src/gamez/zFoo"]
    assert packet["ghidra_scope"] is None
    # The provider apply writes no file: no allowed path, evidence only.
    provider_apply = next(row for row in tracker["work_items"] if row["id"] == "socom:work:source-provider-sce-apply")
    provider_apply["status"] = "ready"
    claim_work(tracker, provider_apply["id"], "worker", 30)
    packet = work_packet(tracker, provider_apply["id"], "worker")
    assert packet["role"] == "socom-source-worker" and packet["skill"] == "socom-provider-boundary"
    assert packet["allowed_paths"] == [] and packet["ghidra_scope"] is None
    assert any("tracker evidence and writes no file" in line for line in packet["validation"])
    assert not any("src/" in line for line in packet["validation"])
    gate = next(row for row in tracker["work_items"] if row["id"] == SOURCE_SEED_ID)
    gate["status"] = "ready"
    claim_work(tracker, SOURCE_SEED_ID, "verifier", 30)
    packet = work_packet(tracker, SOURCE_SEED_ID, "verifier")
    assert packet["role"] == "socom-verifier"
    assert any("--stage ghidra-reconstruction" in line for line in packet["validation"])
    assert any("audit source-trace --require-complete" in line for line in packet["validation"])


# -- owner plans --------------------------------------------------------------------


def _workspace(tmp_path: Path) -> Path:
    (tmp_path / "src" / "gamez" / "zFoo").mkdir(parents=True)
    (tmp_path / "src" / "gamez" / "zFoo" / "a.cpp").write_bytes(b"// provisional\n")
    (tmp_path / "src" / "gamez" / "zFoo" / "zfoo.h").write_text("", encoding="utf-8")
    (tmp_path / "src" / "gamez" / "zFoo" / "stale.cpp").write_text("", encoding="utf-8")
    return tmp_path


def segment_plan(graph: dict) -> dict:
    ids = [row["id"] for row in graph["artifacts"]]
    plan = {
        "kind": SOURCE_PLAN_KIND,
        "schema_version": 1,
        "work_item_id": "socom:work:source-segment-001",
        "scope": {"kind": "segment", "segment_id": graph["segments"][0]["id"], "segment_number": 1},
        "graph_sha256": graph["graph_sha256"],
        "slice_sha256": planning_scopes(graph)[0]["slice_sha256"],
        "target": {"source_sha256": REFERENCE_SHA256},
        "owners": [
            {
                "translation_unit": "a.cpp",
                "classification": "authored",
                "workspace_path": "src/gamez/zFoo/a.cpp",
                "original_path": "Z:\\dev\\gamez\\zFoo\\a.cpp",
                "provisional_file": "src/gamez/zFoo/a.cpp",
                "library": None,
                "archive_member": None,
                "confidence": "high",
                "evidence": ["dwarf-cu covers 0x140000"],
                "artifacts": [ids[0], ids[1], ids[7]],
            },
            {
                "translation_unit": None,
                "classification": "compiler-generated",
                "workspace_path": None,
                "original_path": None,
                "provisional_file": None,
                "library": None,
                "archive_member": None,
                "confidence": "medium",
                "evidence": ["alignment padding before the next object"],
                "artifacts": [ids[2]],
            },
        ],
        "header_emits": [
            {"artifact": ids[1], "header": "src/gamez/zFoo/zfoo.h", "reason": "inline", "evidence": ["binding 13 instance"]},
        ],
        "annotations": [],
        "unresolved": [],
        "retire_files": [{"path": "src/gamez/zFoo/stale.cpp", "reason": "empty, unevidenced", "evidence": ["0 bytes"]}],
        "notes": [],
    }
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    return plan


def provider_plan(graph: dict) -> dict:
    ids = [row["id"] for row in graph["artifacts"]]
    return {
        "kind": SOURCE_PLAN_KIND,
        "schema_version": 1,
        "work_item_id": "socom:work:source-provider-sce",
        "scope": {"kind": "provider", "library": "SCE"},
        "graph_sha256": graph["graph_sha256"],
        "slice_sha256": planning_scopes(graph)[1]["slice_sha256"],
        "target": {"source_sha256": REFERENCE_SHA256},
        "owners": [
            {
                "translation_unit": None,
                "classification": "provider",
                "workspace_path": None,
                "original_path": None,
                "provisional_file": None,
                "library": "SCE",
                "archive_member": {"gnu_object": "0x140020", "object": None},
                "confidence": "high",
                "evidence": ["gcc2_compiled. at 0x140020"],
                "artifacts": [ids[3], ids[4]],
            }
        ],
        "header_emits": [],
        "annotations": [],
        "unresolved": [{"artifact": ids[10], "reason": "no relocation ties the table to the object"}],
        "retire_files": [],
        "notes": [],
    }


def test_complete_plans_validate(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    plan = segment_plan(graph)
    assert [(row["relation"], row["path"]) for row in plan["annotations"]] == [
        ("defines", "src/gamez/zFoo/a.cpp"),
        ("defines", "src/gamez/zFoo/a.cpp"),
        ("emits", "src/gamez/zFoo/zfoo.h"),
    ]
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    # The @12 literal is owned through the artifact list, not annotated.
    assert report["summary"]["annotations"] == {"defines": 2, "emits": 1}
    report = validate_source_plan(root, tracker, provider_plan(graph), graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert report["summary"]["annotations"] == {}


def _ids(graph: dict) -> list[str]:
    return [row["id"] for row in graph["artifacts"]]


SEGMENT_DEFECTS = [
    (lambda plan, ids: plan["owners"][0]["artifacts"].remove(ids[7]), "neither owned nor unresolved"),
    (lambda plan, ids: plan["unresolved"].append({"artifact": ids[0], "reason": "x"}), "is listed 2 times"),
    (lambda plan, ids: plan["unresolved"].append({"artifact": ids[8], "reason": "x"}), "outside the scope's slice"),
    (lambda plan, ids: plan["unresolved"].append({"artifact": ids[7], "reason": SKELETON_REASON})
     or plan["owners"][0]["artifacts"].remove(ids[7]), "skeleton reason"),
    (lambda plan, ids: plan["owners"][0].update(workspace_path="src/gamez/zFoo/zfoo.h"), "headers only declare or emit"),
    (lambda plan, ids: plan["owners"][0].update(workspace_path="src/gamez/zfoo/a.cpp", provisional_file=None), "letter case"),
    (lambda plan, ids: plan["owners"][0].update(provisional_file=None), "cite it as provisional_file"),
    (lambda plan, ids: plan["owners"][0].update(provisional_file="src/gamez/zFoo/A.cpp"), "existing file exactly"),
    (lambda plan, ids: plan["owners"][0].update(workspace_path="src/gamez/zFoo/c.cpp"), "keep the unit's file name"),
    (lambda plan, ids: plan["owners"][0].update(original_path="Z:\\dev\\gamez\\zBar\\a.cpp"), "not quoted by the graph"),
    (lambda plan, ids: plan["owners"][0].update(evidence=[]), "needs evidence lines"),
    (lambda plan, ids: plan["owners"][0].update(confidence="certain"), "confidence must be one of"),
    (lambda plan, ids: plan["header_emits"][0].update(reason="weak"), "needs WEAK binding"),
    (lambda plan, ids: plan["header_emits"][0].update(reason="template"), "template arguments"),
    (lambda plan, ids: plan["header_emits"][0].update(header="src/gamez/zFoo/a.cpp"), "header path"),
    (lambda plan, ids: plan["annotations"].pop(), "are not listed"),
    (lambda plan, ids: plan["annotations"].append(
        {"artifact": ids[7], "relation": "defines", "section": "main", "path": "src/gamez/zFoo/a.cpp"}), "no owner row implies"),
    (lambda plan, ids: plan["retire_files"][0].update(path="src/gamez/zFoo/a.cpp"), "cited by an owner"),
    (lambda plan, ids: plan["header_emits"][0].update(artifact=[ids[1]]), "with string values"),
    (lambda plan, ids: plan["annotations"][0].update(path=["src/gamez/zFoo/a.cpp"]), "every annotation must be exactly"),
    (lambda plan, ids: plan["retire_files"][0].update(path=["x"]), "retire_files row 1 must be"),
    (lambda plan, ids: plan.update(graph_sha256="1" * 64), "the plan cites graph"),
    (lambda plan, ids: plan.update(slice_sha256="2" * 64), "the plan cites slice"),
    (lambda plan, ids: plan.update(scope={"kind": "data", "data_kind": "bss"}), "scope differs"),
    (lambda plan, ids: plan.update(extra=True), "unknown fields"),
    (lambda plan, ids: plan.update(work_item_id="socom:work:source-segment-001-apply"), "not a source-correlation plan item"),
    # The apply may write only its reserved directories.
    (lambda plan, ids: plan["owners"][0].update(workspace_path="src/gamez/zBar/a.cpp"),
     "lies outside the reservation of socom:work:source-segment-001-apply (src/gamez/zFoo)"),
    (lambda plan, ids: plan.update(reservation=_reservation(["src/gamez"], "confirmed")), "a confirmed reservation must equal"),
    (lambda plan, ids: plan.update(reservation=_reservation(["src/gamez/zFoo"], "corrected")), "must differ"),
    (lambda plan, ids: plan.update(reservation=_reservation(["src/gamez/zFoo"], "inferred")), "still the decomposition's inference"),
    (lambda plan, ids: plan.update(reservation=_reservation(["build/x"], "corrected")), "distinct src/ directories"),
    (lambda plan, ids: plan.update(reservation=_reservation(["src/gamez/zfoo"], "corrected")), "differs in letter case"),
    (lambda plan, ids: plan.update(reservation={**_reservation(["src/gamez"], "corrected"), "evidence": []}),
     "needs evidence lines"),
    (lambda plan, ids: plan.update(reservation={"directories": ["src/gamez/zFoo"]}), "reservation must be"),
]


def _reservation(directories: list[str], status: str) -> dict:
    return {"directories": directories, "status": status, "reason": "the units' module", "evidence": ["Z:\\dev path"]}


@pytest.mark.parametrize(("change", "message"), SEGMENT_DEFECTS)
def test_segment_plan_defects_are_refused(tmp_path: Path, synthetic: tuple[dict, dict], change, message: str) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    plan = segment_plan(graph)
    change(plan, _ids(graph))
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert not report["ok"]
    assert any(message in problem for problem in report["problems"]), report["problems"]


def test_a_corrected_reservation_admits_a_move_outside_the_reserved_directory(
    tmp_path: Path, synthetic: tuple[dict, dict]
) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    plan = segment_plan(graph)
    plan["owners"][0]["workspace_path"] = "src/gamez/zBar/a.cpp"
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert any("lies outside the reservation" in problem for problem in report["problems"]), report["problems"]
    plan["reservation"] = _reservation(["src/gamez/zFoo", "src/gamez/zBar"], "corrected")
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert report["reservation"] == {
        "apply_item": "socom:work:source-segment-001-apply",
        "reserved": ["src/gamez/zFoo"],
        "inferred": False,
        "status": "corrected",
        "directories": ["src/gamez/zBar", "src/gamez/zFoo"],
    }
    # A reservation that only confirms the evidenced one is accepted too.
    plan = segment_plan(graph)
    plan["reservation"] = _reservation(["src/gamez/zFoo"], "confirmed")
    assert validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["ok"]


def test_an_inferred_reservation_must_be_confirmed_or_corrected(tmp_path: Path, stage3_tracker: dict) -> None:
    graph = synthetic_graph()
    tracker = decompose(stage3_tracker, graph, INFERRED)
    root = _workspace(tmp_path)
    plan = segment_plan(graph)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert any(
        "reserves src/gamez/zFoo by inference" in problem and "must confirm or correct" in problem
        for problem in report["problems"]
    ), report["problems"]
    plan["reservation"] = _reservation(["src/gamez/zFoo"], "confirmed")
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert report["reservation"]["inferred"] is True and report["reservation"]["status"] == "confirmed"
    # The skeleton carries the inference, which validation refuses as is.
    skeleton = plan_skeleton(tracker, "socom:work:source-segment-001", graph)
    assert skeleton["reservation"] == {
        "directories": ["src/gamez/zFoo"], "status": "inferred", "reason": INFERENCE, "evidence": [],
    }
    problems = validate_source_plan(root, tracker, skeleton, graph, section_of=MAIN)["problems"]
    assert any("still the decomposition's inference" in problem for problem in problems)
    evidence = plan_evidence(root, tracker, "socom:work:source-segment-001", graph, section_of=MAIN)
    assert evidence["reservation"] == {
        "apply_item": "socom:work:source-segment-001-apply",
        "directories": ["src/gamez/zFoo"],
        "inferred": True,
        "reason": INFERENCE,
    }


PROVIDER_DEFECTS = [
    (lambda plan: plan["owners"][0].update(archive_member=None), "archive_member needs"),
    (lambda plan: plan["owners"][0].update(archive_member={"gnu_object": "0x999999"}), "not a GNU object"),
    (lambda plan: plan["owners"][0].update(workspace_path="src/providers/sce/foo.c"), "without a source body"),
    (lambda plan: plan["owners"][0].update(library=None), "needs its library"),
    (lambda plan: plan["owners"].append(copy.deepcopy(plan["owners"][0]))
     or plan["owners"][1].update(artifacts=[plan["owners"][0]["artifacts"].pop()]), "one owner row per archive member"),
    (lambda plan: plan["owners"][0].update(classification="authored", library=None, archive_member=None,
                                           translation_unit="foo.c", workspace_path="src/x/foo.c"),
     "belongs to GNU object 0x140020"),
    (lambda plan: plan.update(reservation=_reservation(["src/providers/sce"], "corrected")),
     "only a segment plan records a reservation"),
]


@pytest.mark.parametrize(("change", "message"), PROVIDER_DEFECTS)
def test_provider_plan_defects_are_refused(tmp_path: Path, synthetic: tuple[dict, dict], change, message: str) -> None:
    tracker, graph = synthetic
    plan = provider_plan(graph)
    change(plan)
    report = validate_source_plan(_workspace(tmp_path), tracker, plan, graph, section_of=MAIN)
    assert any(message in problem for problem in report["problems"]), report["problems"]


def test_a_stale_graph_is_refused(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    other = copy.deepcopy(graph)
    other["segment_size"] = 100
    other["graph_sha256"] = graph_digest(other)
    report = validate_source_plan(_workspace(tmp_path), tracker, segment_plan(graph), other, section_of=MAIN)
    assert any("stale graph" in problem for problem in report["problems"])
    tampered = copy.deepcopy(graph)
    tampered["units"] = []
    report = validate_source_plan(_workspace(tmp_path / "t"), tracker, segment_plan(graph), tampered, section_of=MAIN)
    assert any("differs from its graph_sha256" in problem for problem in report["problems"])


def test_control_characters_are_refused_by_json_path(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    plan = segment_plan(graph)
    # A path's "\apps" written through a string escape: the evidence holds BEL.
    plan["owners"][0]["evidence"].append("Msl\apps\\x")
    plan["notes"].append("tab\there")
    plan["header_emits"][0]["evidence"] = {"line\n": "x"}
    problems = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["problems"]
    controls = [problem for problem in problems if problem.startswith("control character")]
    assert controls == [
        "control character in a plan string at $.owners[0].evidence[1]: U+0007 in 'Msl\\x07pps\\\\x'",
        "control character in a plan string at $.header_emits[0].evidence key: U+000A in 'line\\n'",
        "control character in a plan string at $.notes[0]: U+0009 in 'tab\\there'",
    ]


def test_structured_contradictions(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    ids = _ids(graph)
    plan = segment_plan(graph)
    row = {"artifact": ids[0], "provisional_file": "src/gamez/zFoo/a.cpp", "line": 1, "kind": "defined-elsewhere",
           "elf_evidence": ["dwarf-cu Z:\\dev\\gamez\\zFoo\\a.cpp covers 0x140000"]}
    plan["contradictions"] = [row]
    problems = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["problems"]
    assert any("unknown fields ['contradictions']" in problem for problem in problems)  # schema 2 only
    plan["schema_version"] = 2
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert report["summary"]["contradictions"] == 1
    assert "contradictions" not in validate_source_plan(root, tracker, segment_plan(graph), graph, section_of=MAIN)["summary"]
    for change, message in (
        # Outside the slice only in a file this plan's authored rows own (stale.cpp is not cited).
        ({"artifact": ids[3], "provisional_file": "src/gamez/zFoo/stale.cpp"}, "must be one this plan's authored rows own"),
        ({"artifact": "socom:function:0x999999"}, "is not an artifact of the graph"),
        ({"artifact": 7}, "must lie in the scope's slice"),
        ({"provisional_file": "src/gamez/zFoo/missing.cpp"}, "must name an existing file exactly"),
        ({"provisional_file": "src/gamez/zfoo/a.cpp"}, "(on disk: src/gamez/zFoo/a.cpp)"),
        ({"line": 2}, "has 1 lines, not 2"),
        ({"line": 0}, "positive line number or null"),
        ({"kind": "Defined Elsewhere"}, "lowercase slug"),
        ({"elf_evidence": []}, "needs elf_evidence lines"),
    ):
        plan["contradictions"] = [{**row, **change}]
        problems = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["problems"]
        assert any(message in problem for problem in problems), (change, problems)
    plan["contradictions"] = [{**row, "line": None}, {**row, "line": None}]
    assert any("is listed twice" in problem for problem in validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["problems"])
    plan["contradictions"] = [{key: row[key] for key in ("artifact", "kind")}]
    assert any("contradictions row 1 must be" in problem for problem in validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["problems"])
    # A handed-off plan's text notes stay valid; the report asks new plans for the field.
    plan = segment_plan(graph)
    plan["notes"] = ["contradiction: provisional a.cpp defines b_main, the ELF puts it in b.cpp"]
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"] and any("1 notes record contradictions as text" in note for note in report["review"])


def test_report_lists_shared_reservations_and_unemitted_inline_functions(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    plan = segment_plan(graph)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    # Segment 3's apply falls back to all of src, which holds src/gamez/zFoo.
    assert report["reservation_shared_with"] == {"src/gamez/zFoo": ["socom:work:source-segment-003-apply"]}
    assert not any("no header-emit row" in note for note in report["review"])
    plan["header_emits"] = []
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert "1 owned inline or WEAK functions have no header-emit row (their owner's file defines them): socom:function:0x140010" in report["review"]
    # A provider plan has no reservation to share.
    assert "reservation_shared_with" not in validate_source_plan(root, tracker, provider_plan(graph), graph, section_of=MAIN)


def test_evidence_and_skeleton(tmp_path: Path, synthetic: tuple[dict, dict]) -> None:
    tracker, graph = synthetic
    root = _workspace(tmp_path)
    evidence = plan_evidence(root, tracker, "socom:work:source-segment-001", graph, section_of=MAIN)
    assert [row["id"] for row in evidence["artifacts"]] == planning_scopes(graph)[0]["artifacts"]
    assert evidence["provisional_files"] == [{"path": "src/gamez/zFoo/a.cpp", "bytes": 15}]
    assert [row["named"] for row in evidence["artifacts"]] == [True, True, False, False]
    first = evidence["artifacts"][1]
    assert (first["inline"], first["weak"], first["classification"]["weak"]) == (True, False, False)
    assert first["classification"]["evidence"] == [] and first["input_section"] == ".text"
    assert input_section_text({"input_section": {"name": None, "between": [".vutext", ".data"]}}) == "between .vutext and .data"
    skeleton = plan_skeleton(tracker, "socom:work:source-segment-001", graph)
    problems = validate_source_plan(root, tracker, skeleton, graph, section_of=MAIN)["problems"]
    assert len(problems) == 4 and all("skeleton reason" in problem for problem in problems)


def _cli_root(tmp_path: Path, root: Path, tracker: dict, graph: dict) -> Path:
    workspace = _workspace(tmp_path)
    (workspace / ".agent").mkdir()
    (workspace / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(json.dumps(tracker), encoding="utf-8")
    (workspace / "support").mkdir()
    shutil.copyfile(root / "support" / "socom.elf", workspace / "support" / "socom.elf")
    (workspace / "build" / "source-graph").mkdir(parents=True)
    (workspace / "build" / "source-graph" / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    return workspace


def test_cli_evidence_fill_and_check(tmp_path: Path, root: Path, synthetic: tuple[dict, dict], capsys, monkeypatch) -> None:
    tracker, graph = synthetic
    workspace = _cli_root(tmp_path, root, tracker, graph)
    base = ["--root", str(workspace), "source", "plan"]
    plan_path = "build/source-plans/socom-work-source-segment-001.json"
    assert cli.main([*base, "evidence", "--item", "socom:work:source-segment-001",
                     "--output", "build/source-plans/e.json", "--skeleton", plan_path]) == 0
    assert json.loads(capsys.readouterr().out)["artifact_count"] == 4
    assert cli.main([*base, "evidence", "--item", "socom:work:source-segment-001",
                     "--output", "build/source-plans/e.json", "--skeleton", plan_path]) == 2
    assert "never replaces a plan" in json.loads(capsys.readouterr().out)["error"]
    plan = segment_plan(graph)
    plan["annotations"] = []
    (workspace / plan_path).write_text(json.dumps(plan), encoding="utf-8")
    assert cli.main([*base, "validate", "--plan", plan_path]) == 1
    assert any("are not listed" in problem for problem in json.loads(capsys.readouterr().out)["problems"])
    assert cli.main([*base, "validate", "--plan", plan_path, "--fill-annotations"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["annotations_filled"] and report["summary"]["annotations"]["defines"] == 2
    # The ODR header-emit check (source plan emit-check) adds its counts, never a problem.
    assert report["summary"]["emit_check"] == {"missing_emits": 0, "missing_notes": 0, "wrong_citations": 0, "undetermined": 0}
    # Rewriting the plan is a (build/) mutation; the reservation checked is printed.
    assert report["mutation_performed"] is True
    assert report["reservation"]["apply_item"] == "socom:work:source-segment-001-apply"
    assert cli.main([*base, "validate", "--plan", plan_path, "--fill-annotations"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mutation_performed"] is False and report["annotations_filled"] is False
    # --output writes the full report under build/ and prints its counts.
    assert cli.main([*base, "validate", "--plan", plan_path, "--output", "build/source-plans/report.json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["problems"] == 0 and summary["review"] == len(report["review"]) and "shared_units" not in summary
    full = json.loads((workspace / "build" / "source-plans" / "report.json").read_text(encoding="utf-8"))
    assert full["ok"] and full["problems"] == [] and full["sha256"] == summary["sha256"] and full["review"] == report["review"]
    assert cli.main([*base, "validate", "--plan", plan_path, "--output", "src/report.json"]) == 2
    assert "only be written under build/" in json.loads(capsys.readouterr().out)["error"]
    # --check regenerates the graph from the ELF: the reference graph is not
    # the synthetic one the item was decomposed from.
    regenerated = dict(graph, segment_size=100)
    regenerated["graph_sha256"] = graph_digest(regenerated)
    monkeypatch.setattr("tools._socom.source_graph.source_graph", lambda _root: regenerated)
    assert cli.main([*base, "validate", "--plan", plan_path, "--check"]) == 1
    assert any("stale graph" in problem for problem in json.loads(capsys.readouterr().out)["problems"])
    assert cli.main([*base, "validate", "--plan", plan_path, "--fill-annotations", "--graph", "missing.json"]) == 2


# -- the reference tracker and graph ---------------------------------------------------


def test_reference_dry_run_decomposition(root: Path, stage3_tracker: dict, reference_source_graph: dict) -> None:
    graph = reference_source_graph
    scopes = planning_scopes(graph)
    held = [identity for entry in scopes for identity in entry["artifacts"]]
    assert len(held) == len(set(held)) == len(graph["artifacts"])
    tracker = decompose(stage3_tracker, graph, apply_reservations(root, graph))
    assert audit_tracker(tracker, strict=True) == []
    counts = Counter(row["kind"] for row in tracker["work_items"] if row["stage"] == SOURCE_STAGE)
    assert counts == {
        "source-plan-segment": 46,
        "source-apply-segment": 46,
        "source-plan-provider": 13,
        "source-apply-provider": 13,
        "source-data-reconcile": 3,
        "capability-gate": 1,
        "stage-gate": 1,
    }
    ready = [row["id"] for row in next_work(copy.deepcopy(tracker)) if row["stage"] == SOURCE_STAGE]
    assert len(ready) == 59
    by_id = {row["id"]: row for row in tracker["work_items"]}
    # crt0's unsymbolled object (gap 0x140008) is planned by its own provider
    # item, not by segment 001; MSL plans its units' static initializers.
    crt0 = by_id["socom:work:source-provider-crt0"]["batch"]
    assert crt0["segment_numbers"] == [] and crt0["moved_from_segments"] == [1] and crt0["artifact_count"] == 1
    assert by_id["socom:work:source-provider-msl"]["batch"]["moved_from_segments"] == [len(graph["segments"])]
    record = next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)["decomposition"]
    assert record["segment_count"] == len(graph["segments"]) and record["graph_sha256"] == graph["graph_sha256"]
    # The static-initializer window (mostly compiler-generated) is planned as
    # an authored segment; the speech window is one provider library.
    last = next(row for row in tracker["work_items"] if row["id"] == f"socom:work:source-segment-{len(graph['segments']):03d}")
    assert last["batch"]["classification_mix"].get("compiler-generated", 0) > 100
    assert "socom:work:source-provider-speech-middleware" in {row["id"] for row in tracker["work_items"]}
    # Provider applies write nothing under src/.
    assert all(row["resources"] == [] for row in by_id.values() if row["kind"] == "source-apply-provider")
    # zui_skb.cpp (segment 57) has no path or provisional file: its directory
    # is inferred from the neighbouring zui_ units, not all of src.
    skb = by_id["socom:work:source-segment-057-apply"]
    assert skb["batch"]["tu_candidates"] == ["zui_skb.cpp"]
    assert skb["resources"] == ["src/gamez/zUI"] and skb["batch"]["resource_inferred"] is True
    assert skb["batch"]["resource_basis"] == "neighbour-prefix"
    assert "prefix 'zui' (segment 056 zui_cleanup.cpp; segment 056 zui_spec.cpp)" in skb["batch"]["resource_reason"]
    # A directory resting only on a provisional file's name is inferred too
    # (segment 017: zanim_cmd_tick.cpp has no original path).
    tick = by_id["socom:work:source-segment-017-apply"]["batch"]
    assert tick["resource_inferred"] is True and tick["resource_basis"] == "provisional-name"
    inferred = [row["item"] for row in record["inferred_reservations"]]
    assert skb["id"] in inferred and "socom:work:source-segment-017-apply" in inferred and len(inferred) == 39
    assert "socom:work:source-segment-001-apply" not in inferred
    assert record["fallback_reservations"] == []
    assert not any(row["resources"] == ["src"] for row in by_id.values() if row["kind"] == "source-apply-segment")


def test_reference_skeleton_regenerates_its_slice(root: Path, stage3_tracker: dict, reference_source_graph: dict) -> None:
    graph = reference_source_graph
    tracker = decompose(stage3_tracker, graph, apply_reservations(root, graph))
    item = "socom:work:source-segment-001"
    skeleton = plan_skeleton(tracker, item, graph)
    section_of = loaded_section_lookup(root)
    problems = validate_source_plan(root, tracker, skeleton, graph, section_of=section_of)["problems"]
    assert problems and all("skeleton reason" in problem for problem in problems)
    assert (section_of(0x140008), section_of(0x5B0000), section_of(0x5E7F00), section_of(0x90000000)) == (
        "main", "main", "heap", None,
    )


def test_cli_dry_run_against_a_copy_of_the_reference_tracker(
    tmp_path: Path, root: Path, stage3_tracker: dict, reference_source_graph: dict, capsys, monkeypatch
) -> None:
    (tmp_path / ".agent").mkdir()
    state = tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json"
    state.write_text(json.dumps(stage3_tracker), encoding="utf-8")
    shutil.copytree(root / "src", tmp_path / "src")
    before = state.read_bytes()
    monkeypatch.setattr(cli, "source_graph", lambda _root: reference_source_graph)
    arguments = ["--root", str(tmp_path), "progress", "decompose-stage", "--stage", SOURCE_STAGE,
                 "--expected-revision", str(stage3_tracker["revision"]), "--dry-run"]
    assert cli.main(arguments) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["errors"] == []
    assert report["item_counts"]["source-plan-segment"] == 46 and report["item_counts"]["source-data-reconcile"] == 3
    assert report["item_counts"]["source-plan-provider"] == 13
    inferred = [row["item"] for row in report["decomposition"]["inferred_reservations"]]
    assert "socom:work:source-segment-057-apply" in inferred and len(inferred) == 39
    assert report["decomposition"]["fallback_reservations"] == []
    assert state.read_bytes() == before


def test_pipeline_reachability_reports_the_stage_producible_before_and_after_decomposition(
    tmp_path: Path, stage3_tracker: dict, synthetic: tuple[dict, dict]
) -> None:
    tracker, _graph = synthetic
    (tmp_path / ".agent").mkdir()
    rows = cli._command_rows()
    for state in (stage3_tracker, tracker):
        (tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(json.dumps(state), encoding="utf-8")
        report = audits.pipeline_reachability(tmp_path, rows)
        assert report["ok"], report["missing"]
        # Its gate route is registered (source_gate.py): the stage is no longer deferred.
        assert SOURCE_STAGE not in {row["stage"] for row in report["deferred"]}
