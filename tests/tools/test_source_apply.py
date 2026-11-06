"""Stage 4 apply route: generated annotations, guarded applies, the route gate and lean completeness."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools._socom import cli
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.source import audit_docblocks, audit_source_trace, source_artifacts
from tools._socom.source_apply import parse_blocks, render_block, render_file
from tools._socom.source_plan import (
    SOURCE_APPLY_ROUTE_ID,
    SOURCE_PLAN_KIND,
    derive_annotations,
    plan_path,
    planning_scopes,
    validate_source_plan,
)
from tools._socom.tracker import audit_tracker, claim_work, refresh_ready_and_stages, work_packet
from tools._socom.util import SocomError, sha256_file

from test_source_plan import (  # noqa: F401 - stage3_tracker is a fixture
    MAIN,
    _cli_root,
    _reservation,
    decompose,
    provider_plan,
    segment_plan,
    stage3_tracker,
    synthetic_graph,
)

SEGMENT_1 = "socom:work:source-segment-001"
SEGMENT_3 = "socom:work:source-segment-003"
PROVIDER = "socom:work:source-provider-sce"
DATA = "socom:work:source-data-data"
BSS = "socom:work:source-data-bss"
STATE = Path(".agent") / "RECONSTRUCTION_PROGRESS.json"


def _ids(graph: dict) -> list[str]:
    return [row["id"] for row in graph["artifacts"]]


def _owner(unit: str, workspace: str, artifacts: list[str], provisional: str | None = None) -> dict:
    return {
        "translation_unit": unit,
        "classification": "authored",
        "workspace_path": workspace,
        "original_path": None,
        "provisional_file": provisional,
        "library": None,
        "archive_member": None,
        "confidence": "medium",
        "evidence": ["unit evidence"],
        "artifacts": artifacts,
    }


def _generated(artifacts: list[str]) -> dict:
    return {
        "translation_unit": None,
        "classification": "compiler-generated",
        "workspace_path": None,
        "original_path": None,
        "provisional_file": None,
        "library": None,
        "archive_member": None,
        "confidence": "medium",
        "evidence": ["fill"],
        "artifacts": artifacts,
    }


def _plan(graph: dict, item_id: str, scope: dict, number: int, owners: list[dict]) -> dict:
    plan = {
        "kind": SOURCE_PLAN_KIND,
        "schema_version": 1,
        "work_item_id": item_id,
        "scope": scope,
        "graph_sha256": graph["graph_sha256"],
        "slice_sha256": planning_scopes(graph)[number]["slice_sha256"],
        "target": {"source_sha256": REFERENCE_SHA256},
        "owners": owners,
        "header_emits": [],
        "annotations": [],
        "unresolved": [],
        "retire_files": [],
        "notes": [],
    }
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    return plan


def moved_segment_plan(graph: dict) -> dict:
    """Segment 1: a.cpp moves to src/gamez/zBar (a corrected reservation), zfoo.h emits, stale.cpp retires."""

    plan = segment_plan(graph)
    plan["owners"][0]["workspace_path"] = "src/gamez/zBar/a.cpp"
    plan["reservation"] = _reservation(["src/gamez/zFoo", "src/gamez/zBar"], "corrected")
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    return plan


def plans(graph: dict) -> dict[str, dict]:
    ids = _ids(graph)
    provider = provider_plan(graph)
    provider["owners"][0]["artifacts"].append(ids[10])
    provider["unresolved"] = []
    return {
        SEGMENT_1: moved_segment_plan(graph),
        PROVIDER: provider,
        SEGMENT_3: _plan(
            graph,
            SEGMENT_3,
            {"kind": "segment", "segment_id": graph["segments"][2]["id"], "segment_number": 3},
            2,
            [_owner("b.cpp", "src/gamez/zBaz/b.cpp", [ids[5], ids[6]])],
        ),
        DATA: _plan(
            graph, DATA, {"kind": "data", "data_kind": "data"}, 3,
            [_owner("a.cpp", "src/gamez/zBar/a.cpp", [ids[8]]), _generated([ids[9]])],
        ),
        BSS: _plan(graph, BSS, {"kind": "data", "data_kind": "bss"}, 4, [_owner("b.cpp", "src/gamez/zBaz/b.cpp", [ids[11]])]),
    }


def _census(graph: dict) -> dict:
    kinds = {"function": "FUNC", "data": "OBJECT"}
    return {
        "sections": [{"name": "main"}, {"name": "heap"}],
        "symbols": [
            {"id": f"socom:symbol:{index}", "type": kinds[row["kind"]], "value": int(row["address"], 16), "size": row["size"]}
            for index, row in enumerate(graph["artifacts"])
            if row["kind"] in kinds
        ],
        "relocations": [],
    }


def _load(root: Path) -> dict:
    return json.loads((root / STATE).read_text(encoding="utf-8"))


def _save(root: Path, tracker: dict) -> None:
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    assert audit_tracker(tracker, strict=True) == []
    (root / STATE).write_text(json.dumps(tracker), encoding="utf-8")


def _accept_plans(root: Path, chosen: dict[str, dict]) -> None:
    """Write the plans at their packet paths and accept their items citing the plan SHA-256."""

    tracker = _load(root)
    by_id = {row["id"]: row for row in tracker["work_items"]}
    for item_id, plan in chosen.items():
        path = root / plan_path(item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        by_id[item_id].update(
            status="accepted",
            lease=None,
            handoff={"owner": "mapper", "summary": "plan", "submitted_at": "2026-10-31T00:00:00Z"},
            accepted={"by": "scrutinizer", "at": "2026-10-31T00:00:00Z"},
            evidence=[f"{plan_path(item_id)} sha256:{sha256_file(path)}"],
        )
    _save(root, tracker)


def _run(capsys, *arguments: str) -> tuple[int, dict]:
    code = cli.main(list(arguments))
    return code, json.loads(capsys.readouterr().out)


def _revision(root: Path) -> str:
    return str(_load(root)["revision"])


@pytest.fixture()
def workspace(tmp_path: Path, root: Path, stage3_tracker: dict) -> tuple[Path, dict]:
    graph = synthetic_graph()
    tracker = decompose(stage3_tracker, graph)
    workspace = _cli_root(tmp_path, root, tracker, graph)
    (workspace / ".agent" / "REFERENCE_CENSUS.json").write_text(json.dumps(_census(graph)), encoding="utf-8")
    # Tracker mutations refresh the README progress snapshot.
    (workspace / "README.md").write_bytes((root / "README.md").read_bytes())
    return workspace, graph


@pytest.fixture()
def ready(workspace: tuple[Path, dict], capsys) -> tuple[Path, dict]:
    """Every plan and reconcile accepted, the route gate opened: the applies are ready."""

    root, graph = workspace
    _accept_plans(root, plans(graph))
    code, report = _run(capsys, "--root", str(root), "progress", "open-capability-gate",
                        "--item", SOURCE_APPLY_ROUTE_ID, "--expected-revision", _revision(root))
    assert code == 0, report
    statuses = {row["id"]: row["status"] for row in _load(root)["work_items"]}
    assert {statuses[f"{item}-apply"] for item in (SEGMENT_1, SEGMENT_3, PROVIDER)} == {"ready"}
    return root, graph


def _claim(root: Path, capsys, item: str, owner: str = "worker") -> None:
    code, report = _run(capsys, "--root", str(root), "progress", "work", "claim", "--item", item,
                        "--owner", owner, "--expected-revision", _revision(root))
    assert code == 0, report


def _apply(root: Path, capsys, item: str, *extra: str, owner: str = "worker") -> tuple[int, dict]:
    return _run(capsys, "--root", str(root), "progress", "apply-source-plan", "--item", item, "--owner", owner,
                "--expected-revision", _revision(root), *extra)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted((root / "src").rglob("*")) if path.is_file()}


# -- generated docblocks --------------------------------------------------------------


ROWS = [
    {"artifact": "socom:function:0x140000", "relation": "defines", "section": "main", "path": "src/x/a.cpp"},
    {"artifact": "socom:data:0x426480", "relation": "defines", "section": "main", "path": "src/x/a.cpp"},
]


def test_generated_blocks_are_deterministic_idempotent_and_parsed(tmp_path: Path) -> None:
    text = "﻿#include \"a.h\"\r\n\r\nint a_first(void) { return 0; }\r\n"
    once = render_file(text, {SEGMENT_1: ROWS}, {SEGMENT_1}, assembly=False)
    assert render_file(once, {SEGMENT_1: ROWS}, {SEGMENT_1}, assembly=False) == once
    assert once.startswith("﻿/* socom-owner-annotations begin socom:work:source-segment-001\r\n")
    assert once.endswith("\r\n\r\n#include \"a.h\"\r\n\r\nint a_first(void) { return 0; }\r\n")
    # Another plan's block is kept, in plan-ID order; removing both restores the file.
    both = render_file(once, {DATA: ROWS[1:]}, {DATA}, assembly=False)
    assert both.index(DATA) < both.index(SEGMENT_1)
    assert render_file(both, {DATA: ROWS[1:]}, {DATA}, assembly=False) == both
    assert render_file(both, {}, {SEGMENT_1, DATA}, assembly=False) == text
    _bom, blocks, rest = parse_blocks(both)
    assert set(blocks) == {SEGMENT_1, DATA} and rest == text[1:]
    # The audits parse exactly the artifact lines; the markers carry no @socom- token.
    (tmp_path / "src" / "x").mkdir(parents=True)
    (tmp_path / "src" / "x" / "a.cpp").write_text(both[1:], encoding="utf-8", newline="")
    (tmp_path / "src" / "x" / "b.s").write_text(render_block(SEGMENT_3, ROWS[:1], assembly=True), encoding="utf-8")
    parsed = source_artifacts(tmp_path)
    assert parsed["errors"] == []
    assert sorted((row["path"], row["relation"], row["section"], row["artifact_id"]) for row in parsed["artifacts"]) == [
        ("src/x/a.cpp", "defines", "main", "socom:data:0x426480"),
        ("src/x/a.cpp", "defines", "main", "socom:data:0x426480"),
        ("src/x/a.cpp", "defines", "main", "socom:function:0x140000"),
        ("src/x/b.s", "defines", "main", "socom:function:0x140000"),
    ]
    assert render_block(SEGMENT_3, [], assembly=True).splitlines()[0] == f"# socom-owner-annotations begin {SEGMENT_3}"
    for broken in (once.replace("socom-owner-annotations end", "x"), once + once[1:]):
        with pytest.raises(SocomError):
            parse_blocks(broken)


# -- the route gate -----------------------------------------------------------------------


def test_the_route_gate_opens_only_through_its_registered_capability(workspace: tuple[Path, dict], capsys, monkeypatch) -> None:
    root, _graph = workspace
    base = ["--root", str(root), "progress", "open-capability-gate", "--item", SOURCE_APPLY_ROUTE_ID]
    before = (root / STATE).read_bytes()
    code, report = _run(capsys, *base, "--expected-revision", _revision(root), "--dry-run")
    assert code == 0 and report["capability"] == "source-correlation-apply" and report["work_item"]["status"] == "accepted"
    assert (root / STATE).read_bytes() == before
    with monkeypatch.context() as patch:
        patch.setattr("tools._socom.tracker.capability_opening", lambda _item: {"id": "x", "status": "deferred"})
        code, report = _run(capsys, *base, "--expected-revision", _revision(root))
        assert code == 2 and "not active" in report["error"]
    code, report = _run(capsys, *base, "--expected-revision", _revision(root))
    assert code == 0, report
    gate = report["work_item"]
    assert gate["accepted"]["by"] == "progress open-capability-gate" and gate["accepted"]["capability"] == "source-correlation-apply"
    assert "capability:source-correlation-apply" in gate["evidence"]
    assert "registered-command:progress apply-source-plan" in gate["evidence"]
    code, report = _run(capsys, *base, "--expected-revision", _revision(root))
    assert code == 2 and "not a blocked capability gate" in report["error"]
    # Only the registered route accepts a gate.
    tracker = _load(root)
    next(row for row in tracker["work_items"] if row["id"] == SOURCE_APPLY_ROUTE_ID)["accepted"]["by"] = "someone"
    assert any("must be accepted by progress open-capability-gate" in error for error in audit_tracker(tracker))
    code, report = _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", SEGMENT_1,
                        "--expected-revision", _revision(root))
    assert code == 2 and "not a capability gate" in report["error"]


# -- annotate ------------------------------------------------------------------------------


def test_annotate_checks_and_writes_only_under_the_lease(workspace: tuple[Path, dict], capsys) -> None:
    root, graph = workspace
    chosen = plans(graph)
    chosen[SEGMENT_1] = segment_plan(graph)  # in place: no move
    chosen[DATA]["owners"][0]["workspace_path"] = "src/gamez/zFoo/a.cpp"
    chosen[DATA]["annotations"] = derive_annotations(chosen[DATA], graph, MAIN)
    _accept_plans(root, chosen)
    plan = plan_path(SEGMENT_1)
    base = ["--root", str(root), "source", "annotate", "--plan", plan]
    code, report = _run(capsys, *base, "--check")
    assert code == 1 and {row["path"] for row in report["drift"]} >= {"src/gamez/zFoo/a.cpp", "src/gamez/zFoo/zfoo.h"}
    assert report["reconciles"] == [DATA] and report["annotation_count"] == 4
    assert {"path": "src/gamez/zFoo/stale.cpp", "state": "pending-retire"} in report["drift"]
    code, report = _run(capsys, *base, "--write")
    assert code == 2 and "--owner" in report["error"]
    code, report = _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", SOURCE_APPLY_ROUTE_ID,
                        "--expected-revision", _revision(root))
    _claim(root, capsys, f"{SEGMENT_1}-apply")
    code, report = _run(capsys, *base, "--write", "--owner", "intruder")
    assert code == 2 and "leased by worker" in report["error"]
    code, report = _run(capsys, *base, "--write", "--owner", "worker")
    assert code == 0 and report["written"] == ["src/gamez/zFoo/a.cpp", "src/gamez/zFoo/zfoo.h"], report
    text = (root / "src" / "gamez" / "zFoo" / "a.cpp").read_text(encoding="utf-8")
    assert text.endswith("\n\n// provisional\n") and f"begin {DATA}" in text and f"begin {SEGMENT_1}" in text
    assert "@socom-artifact defines main socom:function:0x140000" in text
    assert "@socom-artifact emits main socom:function:0x140010" in (root / "src" / "gamez" / "zFoo" / "zfoo.h").read_text(encoding="utf-8")
    snapshot = _snapshot(root)
    code, report = _run(capsys, *base, "--write", "--owner", "worker")
    assert code == 0 and report["written"] == [] and _snapshot(root) == snapshot
    code, report = _run(capsys, *base, "--check")
    assert code == 1 and report["drift"] == [{"path": "src/gamez/zFoo/stale.cpp", "state": "pending-retire"}]
    code, report = _run(capsys, "--root", str(root), "source", "annotate", "--plan", plan_path(DATA), "--check")
    assert code == 2 and "data reconcile" in report["error"]
    code, report = _run(capsys, "--root", str(root), "source", "annotate", "--plan", "build/other.json", "--check")
    assert code == 2


# -- segment and provider applies ---------------------------------------------------------------


def test_segment_and_provider_applies_record_their_files_and_hand_off(ready: tuple[Path, dict], capsys) -> None:
    root, graph = ready
    original = (root / "src" / "gamez" / "zFoo" / "a.cpp").read_bytes()
    stale = (root / "src" / "gamez" / "zFoo" / "stale.cpp").read_bytes()
    apply = f"{SEGMENT_1}-apply"
    _claim(root, capsys, apply)
    # Handing off before the route ran is refused.
    code, report = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", apply, "--owner", "worker",
                        "--summary", "s", "--expected-revision", _revision(root))
    assert code == 2 and "run progress apply-source-plan first" in report["error"]
    before, state = _snapshot(root), (root / STATE).read_bytes()
    # Annotating alone neither moves files nor re-reserves a corrected reservation.
    code, report = _run(capsys, "--root", str(root), "source", "annotate", "--plan", plan_path(SEGMENT_1), "--write",
                        "--owner", "worker")
    assert code == 1 and report["written"] == [] and _snapshot(root) == before
    assert any("moves are pending" in line for line in report["problems"])
    assert any("re-reserves the corrected directories" in line for line in report["problems"])
    code, report = _apply(root, capsys, apply, "--dry-run")
    assert code == 0 and report["dry_run"], report
    assert _snapshot(root) == before and (root / STATE).read_bytes() == state
    code, report = _apply(root, capsys, apply)
    assert code == 0, report
    record = report["record"]
    assert record["moves"] == [{"from": "src/gamez/zFoo/a.cpp", "to": "src/gamez/zBar/a.cpp"}]
    assert record["retired"] == [{"path": "src/gamez/zFoo/stale.cpp", "sha256": sha256_file_bytes(stale), "bytes": len(stale)}]
    assert record["reservation"] == {"directories": ["src/gamez/zBar", "src/gamez/zFoo"], "status": "corrected", "reserved": ["src/gamez/zFoo"]}
    assert record["reconciles"] == [DATA]
    assert [row["path"] for row in record["files"]] == ["src/gamez/zBar/a.cpp", "src/gamez/zFoo/zfoo.h"]
    assert not (root / "src" / "gamez" / "zFoo" / "a.cpp").exists() and not (root / "src" / "gamez" / "zFoo" / "stale.cpp").exists()
    moved = (root / "src" / "gamez" / "zBar" / "a.cpp").read_bytes()
    assert moved.endswith(original) and b"@socom-artifact defines main socom:data:0x426480" in moved
    item = next(row for row in _load(root)["work_items"] if row["id"] == apply)
    # The corrected reservation is re-reserved on the item; the decomposed one is kept.
    assert item["resources"] == ["src/gamez/zBar", "src/gamez/zFoo"] and item["batch"]["directories"] == item["resources"]
    assert item["batch"]["reservation_correction"]["from"] == ["src/gamez/zFoo"]
    assert f"source-retired src/gamez/zFoo/stale.cpp sha256:{sha256_file_bytes(stale)} bytes:{len(stale)}" in item["evidence"]
    assert "source-moved src/gamez/zFoo/a.cpp -> src/gamez/zBar/a.cpp" in item["evidence"]
    assert any(line.startswith("source-owner-map-sha256:") for line in item["evidence"])
    # The applied plan still validates (in its applied state); the annotations have no drift.
    code, report = _run(capsys, "--root", str(root), "source", "plan", "validate", "--plan", plan_path(SEGMENT_1))
    assert code == 0 and report["applied"] is True, report["problems"]
    code, report = _run(capsys, "--root", str(root), "source", "annotate", "--plan", plan_path(SEGMENT_1), "--check")
    assert code == 0 and report["drift"] == [], report
    code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", apply)
    assert code == 0 and report["problems"] == []
    # A rerun is idempotent.
    after = _snapshot(root)
    code, report = _apply(root, capsys, apply)
    assert code == 0 and report["record"]["changed"] == [] and _snapshot(root) == after
    assert report["record"]["files"] == record["files"] and report["record"]["retired"] == record["retired"]
    # Hand off (the record's evidence is kept) and accept independently.
    code, report = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", apply, "--owner", "worker",
                        "--summary", "applied", "--evidence", "handoff note", "--expected-revision", _revision(root))
    assert code == 0, report
    assert "handoff note" in report["work_item"]["evidence"]
    assert "source-moved src/gamez/zFoo/a.cpp -> src/gamez/zBar/a.cpp" in report["work_item"]["evidence"]
    accept = ["--root", str(root), "progress", "work", "accept", "--item", apply, "--evidence", "apply-check ok"]
    code, report = _run(capsys, *accept, "--accepter", "worker", "--expected-revision", _revision(root))
    assert code == 2 and "self-accepted" in report["error"]
    # A changed generated block blocks acceptance; an edit outside the blocks (a later stage, the port lane) is drift.
    target = root / "src" / "gamez" / "zBar" / "a.cpp"
    target.write_bytes(moved.replace(b"socom:data:0x426480", b"socom:data:0x426484"))
    code, report = _run(capsys, *accept, "--accepter", "verifier", "--expected-revision", _revision(root))
    assert code == 2 and "generated annotations drifted" in report["error"]
    target.write_bytes(moved + b"// a later port edit\n")
    code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", apply)
    assert code == 0 and report["problems"] == [] and report["drift"] == ["src/gamez/zBar/a.cpp"], report
    target.write_bytes(moved)
    code, report = _run(capsys, *accept, "--accepter", "verifier", "--expected-revision", _revision(root))
    assert code == 0 and report["work_item"]["status"] == "accepted", report
    code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", apply)
    assert code == 0 and report["drift"] == [] and report["drift_count"] == 0, report

    # A provider apply writes no file: tracker evidence only.
    provider = f"{PROVIDER}-apply"
    _claim(root, capsys, provider)
    before = _snapshot(root)
    code, report = _apply(root, capsys, provider)
    assert code == 0, report
    assert report["record"]["files"] == [] and report["record"]["changed"] == [] and _snapshot(root) == before
    assert [(row["library"], row["gnu_object"], row["artifacts"]) for row in report["record"]["members"]] == [("SCE", "0x140020", 3)]
    item = next(row for row in _load(root)["work_items"] if row["id"] == provider)
    assert "source-provider-member SCE gnu_object:0x140020 object:- artifacts:3" in item["evidence"]
    assert item["resources"] == []
    code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", provider)
    assert code == 0, report


def sha256_file_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def test_a_provider_plan_that_needs_files_is_refused(workspace: tuple[Path, dict], capsys) -> None:
    root, graph = workspace
    chosen = plans(graph)
    chosen[PROVIDER]["retire_files"] = [{"path": "src/gamez/zFoo/stale.cpp", "reason": "empty", "evidence": ["0 bytes"]}]
    assert validate_source_plan(root, _load(root), chosen[PROVIDER], graph, section_of=MAIN)["ok"]
    _accept_plans(root, chosen)
    _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", SOURCE_APPLY_ROUTE_ID,
         "--expected-revision", _revision(root))
    _claim(root, capsys, f"{PROVIDER}-apply")
    code, report = _apply(root, capsys, f"{PROVIDER}-apply")
    assert code == 2 and "writes no file under src/" in report["error"]
    assert (root / "src" / "gamez" / "zFoo" / "stale.cpp").exists()


def test_writes_outside_the_reservation_are_refused(workspace: tuple[Path, dict], capsys) -> None:
    root, graph = workspace
    chosen = plans(graph)
    plan = segment_plan(graph)
    # The header lies outside segment 1's reserved src/gamez/zFoo.
    plan["header_emits"][0]["header"] = "src/gamez/zBar/zbar.h"
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    # Validation refuses a header emit outside the reservation; the apply must
    # refuse it as well, even for a plan accepted without that check.
    assert not validate_source_plan(root, _load(root), plan, graph, section_of=MAIN)["ok"]
    chosen[SEGMENT_1] = plan
    _accept_plans(root, chosen)
    _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", SOURCE_APPLY_ROUTE_ID,
         "--expected-revision", _revision(root))
    _claim(root, capsys, f"{SEGMENT_1}-apply")
    before, state = _snapshot(root), (root / STATE).read_bytes()
    code, report = _apply(root, capsys, f"{SEGMENT_1}-apply")
    assert code == 2 and "outside the reservation" in report["error"] and "src/gamez/zBar/zbar.h" in report["error"]
    assert _snapshot(root) == before and (root / STATE).read_bytes() == state


def test_a_stale_plan_is_refused(ready: tuple[Path, dict], capsys) -> None:
    root, _graph = ready
    path = root / plan_path(SEGMENT_1)
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["notes"] = ["edited after acceptance"]
    path.write_text(json.dumps(plan), encoding="utf-8")
    _claim(root, capsys, f"{SEGMENT_1}-apply")
    before = _snapshot(root)
    code, report = _apply(root, capsys, f"{SEGMENT_1}-apply")
    assert code == 2 and "stale plan" in report["error"]
    code, report = _run(capsys, "--root", str(root), "source", "annotate", "--plan", plan_path(SEGMENT_1), "--check")
    assert code == 2 and "stale plan" in report["error"]
    assert _snapshot(root) == before


def test_a_failed_tracker_write_restores_every_file(ready: tuple[Path, dict], capsys, monkeypatch) -> None:
    root, _graph = ready
    _claim(root, capsys, f"{SEGMENT_1}-apply")
    before, state = _snapshot(root), (root / STATE).read_bytes()
    monkeypatch.setattr("tools._socom.tracker.audit_tracker", lambda *_args, **_kwargs: ["synthetic failure"])
    code, report = _apply(root, capsys, f"{SEGMENT_1}-apply")
    assert code == 2 and "synthetic failure" in report["error"]
    assert _snapshot(root) == before and (root / STATE).read_bytes() == state
    assert not (root / "src" / "gamez" / "zBar").exists()


def test_apply_packets_name_the_route_and_its_acceptance(ready: tuple[Path, dict]) -> None:
    root, _graph = ready
    tracker = _load(root)
    for item, owner in ((f"{SEGMENT_1}-apply", "worker"), (f"{PROVIDER}-apply", "worker")):
        claim_work(tracker, item, owner, 30)
        packet = work_packet(tracker, item, owner)
        assert any(f"progress apply-source-plan --item {item}" in line and "--dry-run" in line for line in packet["validation"])
        assert any(f"source apply-check --item {item}" in line and "progress work accept" in line for line in packet["validation"])
        assert "progress work handoff" in packet["handoff"]


# -- completeness under the lean model ------------------------------------------------------------


def test_require_complete_checks_accepted_plans_and_generated_annotations(ready: tuple[Path, dict], capsys) -> None:
    root, _graph = ready
    report = audit_source_trace(root, require_complete=True)
    assert not report["ok"]
    assert any("source applies are not accepted" in error for error in report["errors"])
    assert any("annotations the accepted owner plans imply are missing" in error for error in report["errors"])
    for item in (f"{SEGMENT_1}-apply", f"{SEGMENT_3}-apply", f"{PROVIDER}-apply"):
        _claim(root, capsys, item)
        code, report = _apply(root, capsys, item)
        assert code == 0, report
        code, report = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", item, "--owner",
                            "worker", "--summary", "applied", "--expected-revision", _revision(root))
        assert code == 0, report
        code, report = _run(capsys, "--root", str(root), "progress", "work", "accept", "--item", item, "--accepter",
                            "verifier", "--expected-revision", _revision(root))
        assert code == 0, report
    assert audit_docblocks(root)["ok"], audit_docblocks(root)["errors"]
    report = audit_source_trace(root, require_complete=True)
    assert report["ok"], report["errors"]
    assert report["accepted_artifact_count"] == 12 and report["missing_accepted_artifact_ids"] == []
    assert report["completeness"]["expected_annotation_count"] == 6
    # b.cpp was created with its block only; __sinit_b_cpp is owned through the row, not annotated.
    created = (root / "src" / "gamez" / "zBaz" / "b.cpp").read_text(encoding="utf-8")
    assert "socom:function:0x140040" in created and "socom:function:0x140050" not in created
    assert f"begin {BSS}" in created and "socom:data:0x480000" in created
    # An annotation no accepted plan implies, or a missing generated one, is incomplete.
    extra = root / "src" / "gamez" / "zBaz" / "extra.cpp"
    extra.write_text("// @socom-artifact defines main socom:function:0x140020\n", encoding="utf-8")
    report = audit_source_trace(root, require_complete=True)
    assert any("no accepted owner plan implies" in error and "socom:function:0x140020" in error for error in report["errors"])
    assert audit_source_trace(root)["ok"]  # the default mode checks topology only
    extra.unlink()
    header = root / "src" / "gamez" / "zFoo" / "zfoo.h"
    header.write_text("", encoding="utf-8")
    report = audit_source_trace(root, require_complete=True)
    assert any("missing from source" in error and "emits socom:function:0x140010" in error for error in report["errors"])
    # An unresolved artifact in an accepted plan is incomplete too.
    tracker = _load(root)
    path = root / plan_path(BSS)
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["unresolved"] = [{"artifact": plan["owners"][0]["artifacts"].pop(), "reason": "no owner evidence"}]
    path.write_text(json.dumps(plan), encoding="utf-8")
    next(row for row in tracker["work_items"] if row["id"] == BSS)["evidence"].append(f"sha256:{sha256_file(path)}")
    (root / STATE).write_text(json.dumps(tracker), encoding="utf-8")
    report = audit_source_trace(root, require_complete=True)
    assert any("unresolved in accepted owner plans" in error for error in report["errors"])


def test_require_complete_without_owner_plans_fails(tmp_path: Path, root: Path, stage3_tracker: dict) -> None:
    (tmp_path / ".agent").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(json.dumps(stage3_tracker), encoding="utf-8")
    (tmp_path / ".agent" / "REFERENCE_CENSUS.json").write_text(json.dumps({"sections": [], "symbols": []}), encoding="utf-8")
    assert audit_source_trace(tmp_path)["ok"]
    report = audit_source_trace(tmp_path, require_complete=True)
    assert report["errors"] == ["source-correlation has no owner plans: completeness is checked against accepted owner plans"]


def test_docblocks_resolve_census_derived_artifact_ids(workspace: tuple[Path, dict]) -> None:
    root, _graph = workspace
    (root / "src" / "gamez" / "zFoo" / "x.cpp").write_text(
        "// @socom-artifact defines main socom:function:0x140000\n"
        "// @socom-artifact defines main socom:data:0x426480\n"
        "// @socom-artifact defines main socom:function:0x426480\n",
        encoding="utf-8",
    )
    report = audit_docblocks(root)
    # A data artifact is not a function: only the census-derived kind resolves.
    assert report["errors"] == [
        "src/gamez/zFoo/x.cpp:3: artifact ID is not present in tracker or reference-census evidence: socom:function:0x426480"
    ]


def test_a_rejected_apply_keeps_its_record_and_reapplies(ready: tuple[Path, dict], capsys) -> None:
    root, _graph = ready
    apply = f"{SEGMENT_3}-apply"
    _claim(root, capsys, apply)
    assert _apply(root, capsys, apply)[0] == 0
    assert _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", apply, "--owner", "worker",
                "--summary", "applied", "--expected-revision", _revision(root))[0] == 0
    code, report = _run(capsys, "--root", str(root), "progress", "work", "reject", "--item", apply, "--reviewer", "verifier",
                        "--reason", "recheck", "--expected-revision", _revision(root))
    assert code == 0, report
    item = report["work_item"]
    assert item["status"] == "ready" and item["source_apply"]["created"] == ["src/gamez/zBaz/b.cpp"]
    assert item["review_history"][-1]["source_apply"] == item["source_apply"]
    _claim(root, capsys, apply, owner="worker-2")
    code, report = _apply(root, capsys, apply, owner="worker-2")
    assert code == 0 and report["record"]["changed"] == [] and report["record"]["created"] == ["src/gamez/zBaz/b.cpp"], report


def test_a_unit_file_shared_by_two_segment_plans(workspace: tuple[Path, dict], capsys) -> None:
    root, graph = workspace
    ids = _ids(graph)
    chosen = plans(graph)
    # Segment 3's functions belong to a.cpp too: both plans move it to src/gamez/zBar.
    chosen[SEGMENT_3] = _plan(
        graph, SEGMENT_3, {"kind": "segment", "segment_id": graph["segments"][2]["id"], "segment_number": 3}, 2,
        [_owner("a.cpp", "src/gamez/zBar/a.cpp", [ids[5], ids[6]], provisional="src/gamez/zFoo/a.cpp")],
    )
    chosen[BSS] = _plan(graph, BSS, {"kind": "data", "data_kind": "bss"}, 4, [_owner("a.cpp", "src/gamez/zBar/a.cpp", [ids[11]])])
    _accept_plans(root, chosen)
    _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", SOURCE_APPLY_ROUTE_ID,
         "--expected-revision", _revision(root))
    for item in (f"{SEGMENT_1}-apply", f"{SEGMENT_3}-apply"):
        _claim(root, capsys, item)
        code, report = _apply(root, capsys, item)
        assert code == 0, report
    # The second apply found the move done by the first and added its own block.
    assert report["record"]["moves"] == [] and report["record"]["changed"] == ["src/gamez/zBar/a.cpp"]
    text = (root / "src" / "gamez" / "zBar" / "a.cpp").read_text(encoding="utf-8")
    assert [text.index(f"begin {key}") for key in (BSS, DATA, SEGMENT_1, SEGMENT_3)] == sorted(
        text.index(f"begin {key}") for key in (BSS, DATA, SEGMENT_1, SEGMENT_3)
    )
    for item in (SEGMENT_1, SEGMENT_3):
        code, report = _run(capsys, "--root", str(root), "source", "apply-check", "--item", f"{item}-apply")
        assert code == 0, report
        code, report = _run(capsys, "--root", str(root), "source", "plan", "validate", "--plan", plan_path(item))
        assert code == 0 and report["applied"] is True, report["problems"]


def test_the_plan_validates_unchanged_before_its_apply(workspace: tuple[Path, dict]) -> None:
    root, graph = workspace
    tracker = _load(root)
    for plan in plans(graph).values():
        report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
        assert report["ok"] and report["applied"] is False, report["problems"]
    # An applied record of another plan SHA-256 changes nothing.
    report = validate_source_plan(root, copy.deepcopy(tracker), moved_segment_plan(graph), graph, section_of=MAIN, applied=None)
    assert report["ok"]


def test_apply_check_reports_later_edits_as_drift_and_layout_changes_as_failures(ready: tuple[Path, dict], capsys) -> None:
    root, _graph = ready
    apply = f"{SEGMENT_1}-apply"
    _claim(root, capsys, apply)
    assert _apply(root, capsys, apply)[0] == 0
    check = ["--root", str(root), "source", "apply-check", "--item", apply]
    moved, header = root / "src" / "gamez" / "zBar" / "a.cpp", root / "src" / "gamez" / "zFoo" / "zfoo.h"
    original, original_header = moved.read_bytes(), header.read_bytes()
    # Edits outside the stage 4 blocks (later stages, the functional port lane): drift, listed by path, not failing.
    moved.write_bytes(original + b"int port_only;\n")
    # (A file that held only its blocks keeps stage 4's form: one blank line, then the content.)
    header.write_bytes(original_header + b"\n// port edit\n")
    code, report = _run(capsys, *check)
    assert code == 0 and report["problems"] == [], report["problems"]
    assert report["drift"] == ["src/gamez/zBar/a.cpp", "src/gamez/zFoo/zfoo.h"] and report["drift_count"] == 2
    header.write_bytes(original_header)
    # A block moved below the authored content, or a malformed block, fails.
    _bom, blocks, rest = parse_blocks(original.decode("utf-8"))
    moved.write_bytes((rest + "".join(blocks.values())).encode("utf-8"))
    code, report = _run(capsys, *check)
    assert code == 1 and any("generated annotations drifted" in text for text in report["problems"]), report
    moved.write_bytes(original.replace(b"socom-owner-annotations end", b"socom-owner-annotations stop"))
    code, report = _run(capsys, *check)
    assert code == 1 and any("malformed" in text or "not terminated" in text for text in report["problems"]), report
    moved.write_bytes(original)
    # A missing recorded file, an undone move and a retired file that reappears fail.
    header.unlink()
    code, report = _run(capsys, *check)
    assert code == 1 and "src/gamez/zFoo/zfoo.h is missing" in report["problems"], report
    header.write_bytes(original_header)
    for back in ("a.cpp", "stale.cpp"):
        (root / "src" / "gamez" / "zFoo" / back).write_bytes(b"int provisional;\n")
        code, report = _run(capsys, *check)
        assert code == 1 and f"src/gamez/zFoo/{back} was removed by the apply but exists" in report["problems"], report
        (root / "src" / "gamez" / "zFoo" / back).unlink()
    code, report = _run(capsys, *check)
    assert code == 0 and report["drift"] == [], report


def test_a_contradiction_line_may_lie_in_the_frozen_skeleton_base(tmp_path: Path) -> None:
    from tools._socom.order_skeleton_route import BASE_DIR
    from tools._socom.source_plan import _check_contradictions

    path = "src/gamez/zFoo/a.cpp"
    (tmp_path / path).parent.mkdir(parents=True)
    (tmp_path / path).write_bytes(b"/* skeleton */\nvoid f() { }\n")
    row = {"artifact": "socom:function:0x100000", "provisional_file": path, "line": 12, "kind": "defined-elsewhere",
           "elf_evidence": ["the ELF places it in another unit"]}

    def problems_of() -> tuple[list[str], list[str]]:
        problems: list[str] = []
        review: list[str] = []
        _check_contradictions(tmp_path, [row], {row["artifact"]}, {}, set(), problems, review=review)
        return problems, review

    # The provisional file was rewritten (a skeleton, port edits): without the frozen base the bound fails.
    problems, _review = problems_of()
    assert problems == [f"contradiction 1 (socom:function:0x100000): {path} has 2 lines, not 12"]
    # The frozen base holds the provisional file the line quotes.
    (tmp_path / BASE_DIR / path).parent.mkdir(parents=True)
    (tmp_path / BASE_DIR / path).write_bytes(b"".join(b"int line%d;\n" % number for number in range(20)))
    problems, review = problems_of()
    assert problems == [] and any("frozen skeleton base" in text for text in review)
    row["line"] = 30
    assert problems_of()[0] == [f"contradiction 1 (socom:function:0x100000): {path} has 2 lines, not 30"]
