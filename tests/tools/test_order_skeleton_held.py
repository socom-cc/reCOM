"""Stage 5: held plans retire or move held skeleton entries (``order skeleton held-check`` / ``held-decide``).

The structural tests use small files under tmp_path (the carry and merge of a
re-apply) and in-memory trackers.  The real-data tests render the whole tree
from the build/ inputs in memory (and one preview under build/); nothing
writes the real tracker or src/.
"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from tools._socom import order_skeleton_write
from tools._socom.order_plan import ORDER_PREPARE_KIND, ORDER_SKELETON_PREPARE_ID
from tools._socom.order_skeleton_held import (
    HOLDING_RETIRED,
    PLAN_KIND,
    append_entries,
    check_rows,
    code_lines,
    decision_rows,
    insert_entries,
    load_plan,
    plan_from_decisions,
    row_shape,
    strip_entries,
)
from tools._socom.order_skeleton_merge import conflict_report_path, put_blob, sha
from tools._socom.order_skeleton_route import _merge_scope, check_accepter, held_decide
from tools._socom.tracker import load_tracker
from tools._socom.util import SocomError

from live_state import settled

ROOT = Path(__file__).resolve().parents[2]
TRACKER = ROOT / ".agent" / "RECONSTRUCTION_PROGRESS.json"
INPUTS = (ROOT / "build" / "stage5" / "skeleton-manifest.json", ROOT / "build" / "stage5" / "provisional-bodies.json")
needs_inputs = pytest.mark.skipif(
    not all(path.is_file() for path in INPUTS) or not (ROOT / "build" / "stage5" / "skeleton-route" / "base" / "src").is_dir(),
    reason="needs the skeleton manifest, the body snapshot and the frozen base under build/",
)
HOLD = "src/gamez/zDemo/zdemo_holding.cpp"
UNIT = "src/gamez/zDemo/demo_main.cpp"
NOTE = "/* Unbuilt holding file (stage 5 BD4) */\n"


def _held(name: str, source: str, text: str) -> str:
    return f"/* @socom-skeleton body {name} */\n/* held from {source} */\n{text}"


def _file(head: str, *entries: str) -> bytes:
    return (head + "".join("\n" + entry for entry in entries)).encode()


DEAD = _held("dead__Fv", "src/demo.cpp:3", "void dead()\n{\n}\n")
DEAD_LIVE = _held("dead__Fv", "src/demo.cpp:3", "/* port: deleted (was #if 0): duplicate of demo.cpp:40 */\n")
KEEP = _held("keep__Fv", "src/demo.cpp:9", "void keep()\n{\n}\n")


def _workspace(tmp_path: Path, files: dict[str, tuple[bytes | None, bytes | None, bytes | None]], *,
               retired: list[str], files_retired: list[str]) -> tuple[dict, dict]:
    """(tracker, rendered): per path (previous render, live src/, new render) of the prepare's files."""

    rows = []
    for path, (previous, live, _new) in files.items():
        (tmp_path / "base").mkdir(exist_ok=True)
        if live is not None:
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / path).write_bytes(live)
        put_blob(tmp_path, previous)
        rows.append({"path": path, "action": "holding", "after_sha256": sha(previous)})
    item = {"id": ORDER_SKELETON_PREPARE_ID, "kind": ORDER_PREPARE_KIND, "status": "in_progress", "resources": list(files),
            "order_skeleton": {"kind": "socom-order-skeleton-apply", "item": ORDER_SKELETON_PREPARE_ID, "files": rows}}
    rendered = {"files": {path: new for path, (_old, _live, new) in files.items()},
                "manifest": {"files": [{"path": path, "action": "holding"} for path, row in files.items() if row[2] is not None],
                             "deleted": [{"path": path, "action": HOLDING_RETIRED} for path, row in files.items() if row[2] is None],
                             "entries": [], "held": {"retired": retired, "files_retired": files_retired}}}
    return {"work_items": [item]}, rendered


def _merge(tmp_path: Path, tracker: dict, rendered: dict) -> tuple[dict, dict]:
    rows, changes, _blobs = _merge_scope(tmp_path, tracker, tracker["work_items"][0], rendered, tmp_path / "base", None)
    return {row["path"]: row for row in rows}, changes


# -- the carry of a re-apply -------------------------------------------------------------------


def test_a_retired_entry_leaves_with_its_fence_when_it_holds_no_code(tmp_path: Path) -> None:
    files = {HOLD: (_file(NOTE, DEAD, KEEP), _file(NOTE, DEAD_LIVE, KEEP), _file(NOTE, KEEP))}
    tracker, rendered = _workspace(tmp_path, files, retired=["src/demo.cpp:3"], files_retired=[])
    rows, changes = _merge(tmp_path, tracker, rendered)
    assert changes[HOLD] == _file(NOTE, KEEP)
    (retired,) = rows[HOLD]["carried"]
    assert (retired["state"], retired["name"], retired["source"], retired["to"]) == ("retired", "dead__Fv", "src/demo.cpp:3", None)


def test_a_retired_entry_that_still_holds_code_is_a_conflict(tmp_path: Path) -> None:
    edited = DEAD.replace("{\n}\n", "{\n\tport_dead();\n}\n")
    files = {HOLD: (_file(NOTE, DEAD, KEEP), _file(NOTE, edited, KEEP), _file(NOTE, KEEP))}
    tracker, rendered = _workspace(tmp_path, files, retired=["src/demo.cpp:3"], files_retired=[])
    with pytest.raises(SocomError, match="1 files conflict"):
        _merge(tmp_path, tracker, rendered)
    (row,) = json.loads((tmp_path / conflict_report_path(ORDER_SKELETON_PREPARE_ID)).read_text(encoding="utf-8"))["files"]
    assert "still holds code" in row["entries"][0]["reason"]


def test_an_emptied_holding_file_is_deleted_with_its_port_preamble_but_not_with_unfenced_code(tmp_path: Path) -> None:
    preamble = NOTE + '#include "gamez/zDemo/zdemo.h"\n#include <string.h>\n'
    files = {HOLD: (_file(NOTE, DEAD), _file(preamble, DEAD_LIVE), None)}
    tracker, rendered = _workspace(tmp_path, files, retired=["src/demo.cpp:3"], files_retired=[HOLD])
    rows, changes = _merge(tmp_path, tracker, rendered)
    assert changes[HOLD] is None and rows[HOLD]["after_sha256"] is None and rows[HOLD]["action"] == HOLDING_RETIRED
    assert sorted(row["state"] for row in rows[HOLD]["carried"]) == ["dropped-preamble", "retired"]
    # Port code outside every fence is never dropped: the deletion conflicts (a resolution settles it).
    (tmp_path / HOLD).write_bytes(_file(preamble + "int port_counter;\n", DEAD_LIVE))
    with pytest.raises(SocomError, match="1 files conflict"):
        _merge(tmp_path, tracker, rendered)


# -- the plan, its rows and the placement helpers -------------------------------------------------


def test_plan_rows_need_their_fields_reason_and_evidence_class() -> None:
    good = {"source": "src/a.cpp:1", "entry": "f__Fv", "holding_file": "src/x_holding.cpp", "action": "retire",
            "reason": "no-elf-symbol", "evidence_class": "PROVEN", "evidence": ["no ELF symbol"]}
    assert row_shape(good, 1) == []
    assert row_shape({key: value for key, value in good.items() if key != "evidence"}, 1) == ["row 1 (retire) lacks evidence"]
    assert row_shape({**good, "evidence_class": "SURE"}, 1) == ["row 1: evidence_class must be one of PROVEN, LIKELY, GUESS"]
    assert row_shape({**good, "reason": "duplicate"}, 2) == ["row 2: a duplicate names what it duplicates (of)"]
    assert row_shape({**good, "action": "delete"}, 3) == ["row 3: action must be retire or move"]
    move = {**{key: value for key, value in good.items() if key != "reason"}, "action": "move", "destination": "port/compat/x.cpp"}
    assert any("under src/" in text for text in row_shape(move, 4))
    assert any("unknown fields" in text for text in row_shape({**good, "colour": "red"}, 5))


def test_decision_rows_record_the_plan_and_give_its_rows_back(tmp_path: Path) -> None:
    rows = [{"source": "src/a.cpp:1", "entry": "f__Fv", "holding_file": "src/x_holding.cpp", "action": "move",
             "destination": "src/a.h", "fence": "f__FPCc", "evidence_class": "GUESS", "evidence": ["class header"]}]
    plan = {"kind": PLAN_KIND, "schema_version": 1, "reason": "test", "rows": rows}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert load_plan(path) == plan
    (decided,) = decision_rows(plan, "build/stage5/held-plans/plan.json", "worker", "2026-11-21T00:00:00Z")
    assert (decided["kind"], decided["key"], decided["value"], decided["fence"]) == ("held-move", "src/a.cpp:1", "src/a.h", "f__FPCc")
    assert decided["basis"].startswith("GUESS: ") and decided["plan"] == "build/stage5/held-plans/plan.json"
    assert plan_from_decisions([decided]) == rows
    path.write_text(json.dumps({**plan, "reason": " "}), encoding="utf-8")
    with pytest.raises(SocomError, match="needs a reason"):
        load_plan(path)


def test_header_entries_go_before_the_closing_guard_and_strip_back_exactly() -> None:
    header = "#ifndef DEMO_H\n#define DEMO_H\nclass C { bool f(); };\n\n#endif /* DEMO_H */\n"
    entry = {"name": "f__1CFv", "block": "/* @socom-skeleton body f__1CFv */\n/* held from src/c.cpp:3 */\ninline bool C::f()\n{\n}",
             "lines": 5}
    written = insert_entries(header, [entry])
    assert written.index("inline bool C::f()") < written.index("#endif") and written.endswith("#endif /* DEMO_H */\n")
    assert strip_entries(written, [entry]) == header
    twice = [entry, {**entry, "name": "g__1CFv", "block": entry["block"].replace("f__1CFv", "g__1CFv")}]
    for text in ("#pragma once\nclass C { bool f(); };\n", "#pragma once\nclass C {};\n\n\n"):
        assert strip_entries(insert_entries(text, twice), twice) == text
    unit = append_entries("/* @socom-skeleton stub g__Fv */\nvoid g()\n{\n}\n", [entry])
    assert unit.endswith("{\n}\n\n" + entry["block"] + "\n")
    assert code_lines(["/* port: deleted */\n", "// gone\n", "\n"]) == []
    assert code_lines(['#include "a.h"\n'], preamble=True) == [] and code_lines(["int x;\n"], preamble=True) == ["int x;"]


# -- who records and who accepts ---------------------------------------------------------------------


def test_only_the_prepares_lease_holder_records_a_held_plan(tmp_path: Path) -> None:
    tracker = {"work_items": [{"id": ORDER_SKELETON_PREPARE_ID, "kind": ORDER_PREPARE_KIND, "status": "in_progress",
                               "lease": {"owner": "worker"}},
                              {"id": "socom:work:order-segment-041-apply", "kind": "order-skeleton-apply", "status": "ready"}]}
    plan = tmp_path / "plan.json"
    with pytest.raises(SocomError, match="decide a held plan under"):
        held_decide(tmp_path, tracker, "socom:work:order-segment-041-apply", "worker", plan, manifest_path=INPUTS[0],
                    snapshot_path=INPUTS[1])
    with pytest.raises(SocomError, match="is leased by worker"):
        held_decide(tmp_path, tracker, ORDER_SKELETON_PREPARE_ID, "someone-else", plan, manifest_path=INPUTS[0],
                    snapshot_path=INPUTS[1])


def test_the_worker_who_applied_a_held_plan_cannot_accept_it() -> None:
    tracker = {"work_items": [{"id": ORDER_SKELETON_PREPARE_ID, "kind": ORDER_PREPARE_KIND, "status": "awaiting_acceptance",
                               "order_skeleton": {"applied_by": "socom-holding-worker"},
                               "handoff": {"owner": "socom-holding-worker"}}]}
    with pytest.raises(SocomError, match="must be an independent socom-verifier"):
        check_accepter(tracker, ORDER_SKELETON_PREPARE_ID, "socom-holding-worker")
    with pytest.raises(SocomError, match="tool maintainer"):
        check_accepter(tracker, ORDER_SKELETON_PREPARE_ID, "socom-tool-maintainer-x")
    assert check_accepter(tracker, ORDER_SKELETON_PREPARE_ID, "socom-verifier-h1") == "socom-verifier-h1"


# -- real data: the render's held entries, the checks and a render with held decisions -------------


@pytest.fixture(scope="module")
def live() -> dict:
    return settled(load_tracker(TRACKER))


@pytest.fixture(scope="module")
def render(live: dict) -> tuple:
    from tools._socom.order_skeleton_route import route_inputs

    inputs, _base = route_inputs(ROOT, live, manifest_path=INPUTS[0], snapshot_path=INPUTS[1])
    rendered = order_skeleton_write.render_skeletons(inputs, segment=None)
    return inputs, rendered


SET_ACTIVE = "src/gamez/zNode/node_main.cpp:671"
CLEAR_ALL = "src/gamez/zTexture/ztex_manager.cpp:18"
END_RELOC = "src/gamez/zTexture/ztex_manager.cpp:23"
EVIDENCE = {"evidence_class": "PROVEN", "evidence": ["survey build/stage4/owner-decisions/holding-2026-11-20.md"]}


def _row(index: dict, source: str, action: str, **fields: str) -> dict:
    entry = index[source]
    return {"source": source, "entry": entry["name"], "holding_file": entry["holding_file"], "action": action, **EVIDENCE, **fields}


def _moves(index: dict) -> list[dict]:
    return [_row(index, SET_ACTIVE, "move", destination="src/gamez/zNode/znode.h"),
            _row(index, CLEAR_ALL, "move", destination="src/gamez/zTexture/ztex_manager.cpp"),
            _row(index, END_RELOC, "move", destination="src/gamez/zTexture/ztex_manager.cpp",
                 fence="EndBatchReloc__Q23zdb15CBatchRelocatorCFv")]


def _camera(index: dict) -> list[dict]:
    rows = []
    for source, entry in sorted(index.items()):
        if entry["holding_file"] == "src/gamez/zCamera/zcamera_holding.cpp":
            rows.append(_row(index, source, "retire", reason="duplicate", of="gamez/zCamera/camera.cpp"))
    return rows


@needs_inputs
def test_a_plan_retires_and_moves_copies_where_stage_4_places_them(render: tuple) -> None:
    inputs, rendered = render
    index = rendered["held"]["index"]
    assert index and all(row["holding_file"].endswith("_holding.cpp") for row in index.values())
    problems, report = check_rows(ROOT, inputs, index, _moves(index) + _camera(index))
    assert problems == []
    by_source = {row["source"]: row for row in report}
    assert by_source[SET_ACTIVE]["stage4"] == "emits socom:function:0x17d2b0 src/gamez/zNode/znode.h"
    assert by_source[CLEAR_ALL]["stage4"] == "defines socom:function:0x2f9ab0 src/gamez/zTexture/ztex_manager.cpp"
    # A corrected fence resolves the ELF copy the held (misspelt) fence could not.
    assert by_source[END_RELOC]["artifact"] == "socom:function:0x2f9b70"


@needs_inputs
def test_a_plan_is_refused_outside_its_rules(render: tuple) -> None:
    inputs, rendered = render
    index = rendered["held"]["index"]
    ordered = next(source for source, row in sorted(index.items()) if row["kind"] == "data" and row.get("artifact"))
    no_artifact = next(source for source, row in sorted(index.items()) if row["kind"] == "function" and not row.get("artifact"))
    copy_row = _row(index, CLEAR_ALL, "move", destination="src/gamez/zTexture/ztex_manager.cpp")
    cases = {
        "not a held entry": {**copy_row, "source": "src/gamez/zTexture/ztex_manager.cpp:999"},
        "under that fence name": {**copy_row, "entry": "ClearAll__Q23zdb15CBatchRelocatorCFv"},
        "outside the plan: no header": {**copy_row, "destination": "src/gamez/zTexture/ztex_nowhere.h"},
        "outside the plan: not a unit file": {**copy_row, "destination": "src/gamez/zTexture/ztex_nowhere.cpp"},
        "is a holding file": {**copy_row, "destination": index[CLEAR_ALL]["holding_file"]},
        "stage 4 does not place": {**copy_row, "destination": "src/gamez/zTexture/ztex_main.cpp"},
        "ordered ELF artifact": _row(index, ordered, "move", destination="src/gamez/zTexture/ztex_manager.cpp"),
        "retire it as a duplicate": _row(index, CLEAR_ALL, "retire", reason="no-elf-symbol"),
        "no single ELF function": {**_row(index, no_artifact, "move", destination="src/gamez/zTexture/ztex_manager.cpp"),
                                   "fence": "NoSuchSymbol__Fv"},
    }
    for needle, row in cases.items():
        problems, _report = check_rows(ROOT, inputs, index, [row])
        assert any(needle in text for text in problems), (needle, problems)
    problems, _report = check_rows(ROOT, inputs, index, [copy_row, copy_row])
    assert any("listed twice" in text for text in problems)
    problems, _report = check_rows(ROOT, inputs, index, [copy_row], decided={CLEAR_ALL: "socom:work:order-segment-041-apply"})
    assert any("decides this entry already" in text for text in problems)


@needs_inputs
def test_a_render_with_held_decisions_moves_retires_and_passes_its_checks(live: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools._socom.order_skeleton_check import check_skeletons
    from tools._socom.order_skeleton_route import check_held_decisions, provisional_root, route_inputs

    decisions_dir = "build/test-skeleton-held-decisions"
    preview = ROOT / "build" / "test-skeleton-held-preview"
    real = ROOT / order_skeleton_write.DECISIONS_DIR
    monkeypatch.setattr(order_skeleton_write, "DECISIONS_DIR", decisions_dir)
    try:
        if (ROOT / decisions_dir).exists():
            shutil.rmtree(ROOT / decisions_dir)
        shutil.copytree(real, ROOT / decisions_dir) if real.is_dir() else (ROOT / decisions_dir).mkdir(parents=True)
        inputs, _base = route_inputs(ROOT, live, manifest_path=INPUTS[0], snapshot_path=INPUTS[1])
        before = order_skeleton_write.render_skeletons(inputs, segment=None)
        index = before["held"]["index"]
        plan = {"kind": PLAN_KIND, "schema_version": 1, "reason": "test", "rows": _moves(index) + _camera(index)}
        path = ROOT / order_skeleton_write.decisions_path(ORDER_SKELETON_PREPARE_ID)
        current = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {
            "kind": order_skeleton_write.DECISIONS_KIND, "schema_version": 1, "work_item_id": ORDER_SKELETON_PREPARE_ID, "decisions": []}
        current["decisions"] = sorted(current["decisions"] + decision_rows(plan, "build/x.json", "worker", "2026-11-21T00:00:00Z"),
                                      key=lambda row: (row["kind"], row["key"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current), encoding="utf-8")
        inputs, base = route_inputs(ROOT, live, manifest_path=INPUTS[0], snapshot_path=INPUTS[1])
        rendered = order_skeleton_write.render_skeletons(inputs, segment=None)
        assert inputs.unused_decisions() == [] and check_held_decisions(ROOT, inputs, rendered) == []
        held = rendered["manifest"]["held"]
        assert held["files_retired"] == ["src/gamez/zCamera/zcamera_holding.cpp"] and len(held["retired"]) == len(_camera(index))
        assert rendered["files"]["src/gamez/zCamera/zcamera_holding.cpp"] is None
        assert {"path": "src/gamez/zCamera/zcamera_holding.cpp", "action": HOLDING_RETIRED} == {
            key: value for key, value in next(row for row in rendered["manifest"]["deleted"]
                                              if row["path"] == "src/gamez/zCamera/zcamera_holding.cpp").items() if key in ("path", "action")}
        unit = rendered["files"]["src/gamez/zTexture/ztex_manager.cpp"].decode("utf-8")
        assert "/* @socom-skeleton body EndBatchReloc__Q23zdb15CBatchRelocatorCFv */" in unit
        assert "/* @socom-skeleton body ClearAll__Q23zdb15CBatchRelocatorFv */" in unit
        holding = rendered["files"][index[CLEAR_ALL]["holding_file"]].decode("utf-8")
        assert "ClearAll__Q23zdb15CBatchRelocatorFv" not in holding and "EndBatchReloc" not in holding
        header = rendered["files"]["src/gamez/zNode/znode.h"].decode("utf-8").replace("\r\n", "\n")
        assert "\ninline bool CNode::SetActive(" in header and header.rstrip().endswith("#endif")
        # Without held decisions the render is the recorded one: its digest does not change.
        assert before["manifest"]["write_sha256"] != rendered["manifest"]["write_sha256"] and "held" not in before["manifest"]
        if preview.exists():
            shutil.rmtree(preview)
        order_skeleton_write.write_skeletons(base or ROOT, preview, rendered)
        report = check_skeletons(ROOT, live, preview, manifest_path=INPUTS[0], snapshot_path=INPUTS[1],
                                 source_root=provisional_root(ROOT, live))
        assert report["ok"], {key: report[key] for key in report["failed"]}
        # A decision whose entry the render no longer holds refuses the render.
        stale = copy.deepcopy(current)
        stale["decisions"].append({**decision_rows(plan, "build/x.json", "w", "t")[0], "key": "src/gamez/zNode/node_main.cpp:1"})
        path.write_text(json.dumps(stale), encoding="utf-8")
        inputs, _base = route_inputs(ROOT, live, manifest_path=INPUTS[0], snapshot_path=INPUTS[1])
        with pytest.raises(SocomError, match="the render holds no such entry"):
            order_skeleton_write.render_skeletons(inputs, segment=None)
    finally:
        if (ROOT / decisions_dir).exists():
            shutil.rmtree(ROOT / decisions_dir)
        if preview.exists():
            shutil.rmtree(preview)
