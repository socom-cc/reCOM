"""Stage 4 amendments: correcting accepted plans after the gate, re-applying and recording the next baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools._socom.source_plan import derive_annotations, plan_path
from tools._socom.tracker import audit_tracker
from tools._socom.util import sha256_file

from test_source_apply import (  # noqa: F401 - workspace and stage3_tracker are fixtures
    DATA,
    PROVIDER,
    SEGMENT_1,
    SEGMENT_3,
    STATE,
    _apply,
    _claim,
    _generated,
    _load,
    _revision,
    _run,
    stage3_tracker,
    workspace,
)
from test_source_gate import (  # noqa: F401 - closing is a fixture
    ACCEPTER,
    DEFERRALS,
    GATE,
    REVIEWER,
    _accept,
    _approved,
    _deferrals,
    _handoff,
    _receipt,
    _stage3_receipt,
    _write,
    closing,
)
from test_source_plan import MAIN

FIRST = "socom:source-amendment:001"
SECOND = "socom:source-amendment:002"
OPENER = "socom-reviewer-a1"
AMENDMENT_ACCEPTER = "socom-verifier-a2"
NEW_DEFERRALS = "build/closeout-source-correlation/amendment-deferrals.json"


@pytest.fixture()
def amendable(closing: tuple[Path, dict, str], capsys) -> tuple[Path, dict, str]:
    """Stage 4 accepted with its file baseline: one deferred gap (the data reconcile's)."""

    root, graph, gap = closing
    _write(root, DEFERRALS, _deferrals(_approved(gap)))
    _claim(root, capsys, GATE, owner=REVIEWER)
    code, report = _handoff(root, capsys, "--deferrals", DEFERRALS)
    assert code == 0, report
    code, report = _accept(root, capsys, ACCEPTER)
    assert code == 0 and report["stage_status"] == "accepted", report
    return root, graph, gap


def _amend(root: Path, capsys, item: str, *extra: str, by: str = OPENER, reason: str = "the owner row is wrong",
           evidence: tuple[str, ...] = ("issue evidence",), revision: str | None = None) -> tuple[int, dict]:
    arguments = ["--root", str(root), "progress", "amend-source-plan", "--item", item, "--by", by,
                 "--reason", reason, "--expected-revision", revision or _revision(root)]
    for line in evidence:
        arguments += ["--evidence", line]
    return _run(capsys, *arguments, *extra)


def _accept_amendment(root: Path, capsys, accepter: str = AMENDMENT_ACCEPTER, *extra: str,
                      amendments: tuple[str, ...] = (FIRST,)) -> tuple[int, dict]:
    arguments = ["--root", str(root), "progress", "accept-source-amendment", "--accepter", accepter,
                 "--evidence", "independent re-run of every gate check", "--expected-revision", _revision(root)]
    for name in amendments:
        arguments += ["--amendment", name]
    return _run(capsys, *arguments, *extra)


def _plan(root: Path, item: str) -> dict:
    return json.loads((root / plan_path(item)).read_text(encoding="utf-8"))


def _revise(root: Path, capsys, item: str, plan: dict, planner: str = "mapper-2", reviewer: str = "scrutinizer-2") -> None:
    """The planner writes the revised plan and hands it off; an independent reviewer accepts it."""

    path = root / plan_path(item)
    path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    _claim(root, capsys, item, owner=planner)
    code, report = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", item, "--owner", planner,
                        "--summary", "revised for the amendment", "--evidence", f"{plan_path(item)} sha256:{sha256_file(path)}",
                        "--expected-revision", _revision(root))
    assert code == 0, report
    code, report = _run(capsys, "--root", str(root), "progress", "work", "accept", "--item", item, "--accepter", reviewer,
                        "--expected-revision", _revision(root))
    assert code == 0, report


def _reapply(root: Path, capsys, item: str, worker: str = "worker-2", verifier: str = "verifier-2") -> dict:
    _claim(root, capsys, item, owner=worker)
    code, report = _apply(root, capsys, item, owner=worker)
    assert code == 0, report
    code, handed = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", item, "--owner", worker,
                        "--summary", "re-applied", "--expected-revision", _revision(root))
    assert code == 0, handed
    code, accepted = _run(capsys, "--root", str(root), "progress", "work", "accept", "--item", item, "--accepter", verifier,
                          "--expected-revision", _revision(root))
    assert code == 0, accepted
    return report


def _items(root: Path) -> dict[str, dict]:
    return {row["id"]: row for row in _load(root)["work_items"]}


def _stage(tracker: dict) -> dict:
    return next(row for row in tracker["stages"] if row["name"] == "source-correlation")


def _audits(root: Path, capsys, *strict: str) -> tuple[dict, dict]:
    code, progress = _run(capsys, "--root", str(root), "progress", "audit", "--strict")
    assert code == 0, progress
    code, baseline = _run(capsys, "--root", str(root), "audit", "source-baseline", *strict)
    assert code == 0, baseline
    return progress, baseline


def test_an_amended_reconcile_resolves_a_deferred_row_and_records_the_next_baseline(
    amendable: tuple[Path, dict, str], capsys, monkeypatch
) -> None:
    root, graph, gap = amendable
    first = _stage(_load(root))["baseline"]
    state = (root / STATE).read_bytes()

    # A dry run reports the amendment without writing.
    code, report = _amend(root, capsys, DATA, "--dry-run")
    assert code == 0 and report["dry_run"] and report["errors"] == [], report
    assert report["amendment"] == FIRST and report["applies"] == [f"{SEGMENT_1}-apply"]
    assert report["statuses"] == {DATA: "ready", f"{SEGMENT_1}-apply": "blocked"} and report["stage_status"] == "accepted"
    assert (root / STATE).read_bytes() == state

    code, report = _amend(root, capsys, DATA, evidence=("line 2", "line 1"))
    assert code == 0 and report["mutation_performed"], report
    tracker = _load(root)
    items = {row["id"]: row for row in tracker["work_items"]}
    stage = _stage(tracker)
    # The stage, the gate and the items that wait for the reconcile keep their acceptance.
    assert stage["status"] == "accepted" and items[GATE]["status"] == "accepted"
    assert {items[f"{SEGMENT_3}-apply"]["status"], items[f"{PROVIDER}-apply"]["status"]} == {"accepted"}
    assert items[DATA]["status"] == "ready" and "accepted" not in items[DATA] and items[DATA]["handoff"] is None
    entry = items[DATA]["review_history"][-1]
    assert (entry["amendment"], entry["amended_by"], entry["evidence"]) == (FIRST, OPENER, ["line 1", "line 2"])
    assert entry["accepted"]["by"] == "scrutinizer"
    apply = items[f"{SEGMENT_1}-apply"]
    assert apply["status"] == "blocked" and apply["review_history"][-1]["amendment"] == FIRST
    assert apply["source_apply"]["plan_item"] == SEGMENT_1  # the record stays until the re-apply replaces it
    row = stage["amendments"][0]
    assert (row["id"], row["status"], row["item"], row["applies"]) == (FIRST, "open", DATA, [f"{SEGMENT_1}-apply"])
    assert row["base_baseline_sha256"] == first["baseline_sha256"]
    assert audit_tracker(tracker, strict=True) == []
    # The audits report the open amendment, not an error; the baseline still holds.
    progress, baseline = _audits(root, capsys, "--strict")
    assert progress["open_amendments"][0]["id"] == FIRST
    assert baseline["open_amendments"][0]["item"] == DATA and baseline["baseline_sha256"] == first["baseline_sha256"]

    # One amendment per item at a time; acceptance waits for the re-accepted items.
    code, report = _amend(root, capsys, DATA)
    assert code == 2 and f"{FIRST} is already open on {DATA}" in report["error"], report
    code, report = _accept_amendment(root, capsys)
    assert code == 2 and "not re-accepted yet" in report["error"] and DATA in report["error"], report

    # The planner revises the reconcile: the deferred gap gets its owner row back.
    plan = _plan(root, DATA)
    plan["owners"].append(_generated([gap]))
    plan["unresolved"] = []
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    code, baseline = _run(capsys, "--root", str(root), "audit", "source-baseline")
    _revise(root, capsys, DATA, plan)
    _progress, baseline = _audits(root, capsys)
    assert baseline["amended_plan_files"] == [plan_path(DATA)] and not baseline["annotation_edges_pending_amendment"]
    items = _items(root)
    assert items[f"{SEGMENT_1}-apply"]["status"] == "ready"

    # The apply must be re-applied before it is handed off again; the amended plan cannot change meanwhile.
    _claim(root, capsys, f"{SEGMENT_1}-apply", owner="worker-2")
    code, report = _amend(root, capsys, SEGMENT_1)
    assert code == 2 and f"{SEGMENT_1}-apply is in_progress" in report["error"], report
    code, report = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", f"{SEGMENT_1}-apply",
                        "--owner", "worker-2", "--summary", "s", "--expected-revision", _revision(root))
    assert code == 2 and f"without a re-apply for {FIRST}" in report["error"], report
    code, report = _run(capsys, "--root", str(root), "progress", "work", "release", "--item", f"{SEGMENT_1}-apply",
                        "--owner", "worker-2", "--expected-revision", _revision(root))
    assert code == 0, report
    previous = _items(root)[f"{SEGMENT_1}-apply"]["source_apply"]
    _reapply(root, capsys, f"{SEGMENT_1}-apply")
    apply = _items(root)[f"{SEGMENT_1}-apply"]
    assert apply["source_apply"]["amendments"] == [FIRST] and f"source-reapply {FIRST}" in apply["evidence"]
    replaced = [entry for entry in apply["review_history"] if "replaced_at" in entry]
    assert len(replaced) == 1 and replaced[0]["source_apply"] == previous and replaced[0]["amendments"] == [FIRST]

    # Only an independent accepter accepts; an unreachable bridge refuses with nothing recorded.
    for name, message in (
        (OPENER, "opened the amendment or handed off"),
        ("mapper-2", "opened the amendment or handed off"),
        ("worker-2", "opened the amendment or handed off"),
        ("socom-tool-maintainer-m21", "tool maintainer"),
    ):
        code, report = _accept_amendment(root, capsys, name)
        assert code == 2 and message in report["error"], (name, report)
    state = (root / STATE).read_bytes()
    _receipt(monkeypatch, None)
    code, report = _accept_amendment(root, capsys)
    assert code == 2 and "live Ghidra receipt is unavailable" in report["error"], report
    _receipt(monkeypatch, _stage3_receipt(root))
    code, report = _accept_amendment(root, capsys, AMENDMENT_ACCEPTER, "--dry-run")
    assert code == 0 and report["dry_run"] and report["deferrals_resolved"] == 1, report
    assert (root / STATE).read_bytes() == state

    code, report = _accept_amendment(root, capsys)
    assert code == 0 and report["stage_status"] == "accepted" and report["amendments"] == [FIRST], report
    assert report["previous_baseline_sha256"] == first["baseline_sha256"]
    tracker = _load(root)
    stage = _stage(tracker)
    current = stage["baseline"]
    assert current["baseline_sha256"] == report["baseline_sha256"] != first["baseline_sha256"]
    assert current["state"]["unresolved"]["count"] == 0 and current["state"]["deferrals"]["count"] == 0
    assert current["deferrals_resolved"] == [
        {"artifact": gap, "deferral": "data-fill", "note": f"resolved by {FIRST}: no accepted plan leaves it unresolved"}
    ]
    history = stage["baseline_history"]
    assert len(history) == 1 and history[0]["baseline_sha256"] == first["baseline_sha256"]
    assert history[0]["superseded_by"] == [{"amendment": FIRST, "reason": "the owner row is wrong"}]
    assert stage["amendments"][0]["status"] == "accepted"
    assert stage["amendments"][0]["accepted"]["baseline_sha256"] == current["baseline_sha256"]
    assert f"source-file-baseline-sha256:{current['baseline_sha256']}" in stage["accepted_evidence"]
    # The gate's own record is never rewritten.
    assert next(row for row in tracker["work_items"] if row["id"] == GATE)["source_gate"]["deferrals"][0]["artifacts"] == [gap]
    progress, baseline = _audits(root, capsys, "--strict")
    assert "open_amendments" not in progress and baseline["baseline_history_count"] == 1
    assert baseline["baseline_sha256"] == current["baseline_sha256"] and baseline["open_amendments"] == []

    # The audits hold the chain.
    def tampered(change) -> list[str]:
        copy = json.loads(json.dumps(tracker))
        change(_stage(copy))
        return audit_tracker(copy)

    assert any("state differs from its digest" in line for line in tampered(
        lambda stage: stage["baseline_history"][0]["state"].update(plan_count=0)))
    assert any("must name the amendments that superseded it" in line for line in tampered(
        lambda stage: stage["baseline_history"][0].pop("superseded_by")))
    assert any("not an amendment accepted with it" in line for line in tampered(
        lambda stage: stage["amendments"][0]["accepted"].update(baseline_sha256="0" * 64)))
    assert any("does not follow the baseline before it" in line for line in tampered(
        lambda stage: stage["baseline"].update(previous_baseline_sha256="0" * 64)))
    assert any("names no deferred artifact" in line for line in tampered(
        lambda stage: stage["baseline"]["deferrals_resolved"][0].update(artifact="socom:gap:0x1")))
    assert any("tool maintainer" in line for line in tampered(
        lambda stage: stage["amendments"][0]["accepted"].update(by="socom-tool-maintainer-m21")))


def test_an_amended_segment_re_annotates_and_new_unresolved_rows_need_a_deferral_basis(
    amendable: tuple[Path, dict, str], capsys
) -> None:
    root, graph, gap = amendable
    ids = [row["id"] for row in graph["artifacts"]]
    code, report = _amend(root, capsys, SEGMENT_3)
    assert code == 0 and report["applies"] == [f"{SEGMENT_3}-apply"], report
    items = _items(root)
    # The data reconciles wait for every plan, yet keep their acceptance.
    assert items[DATA]["status"] == "accepted" and items[SEGMENT_3]["status"] == "ready"

    # The revision leaves b_main unresolved: its annotation goes.
    plan = _plan(root, SEGMENT_3)
    plan["owners"][0]["artifacts"] = [ids[6]]
    plan["unresolved"] = [{"artifact": ids[5], "reason": "the unit of b_main is contested"}]
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    _revise(root, capsys, SEGMENT_3, plan)
    # Before the re-apply the edges still match; a stray edit is still an error.
    stray = root / "src" / "gamez" / "zBaz" / "stray.cpp"
    stray.write_text("// @socom-artifact defines main socom:function:0x140020\n", encoding="utf-8")
    code, report = _run(capsys, "--root", str(root), "audit", "source-baseline")
    assert code == 1 and any("no amended apply is re-applied yet" in line for line in report["errors"]), report
    stray.unlink()
    _reapply(root, capsys, f"{SEGMENT_3}-apply")
    _progress, baseline = _audits(root, capsys)
    assert baseline["annotation_edges_pending_amendment"] and baseline["reapplied"] == [f"{SEGMENT_3}-apply"]

    # The new unresolved row is refused without a deferral basis, and a deferral may not reuse an ID.
    code, report = _accept_amendment(root, capsys)
    assert code == 2 and "have no recorded deferral" in report["error"], report
    reused = {"id": "data-fill", "artifacts": [ids[5]], "reason": "contested",
              "approval": {"by": "user", "at": "2026-11-01", "decision": "Defer b_main"}}
    _write(root, NEW_DEFERRALS, _deferrals(reused))
    code, report = _accept_amendment(root, capsys, AMENDMENT_ACCEPTER, "--deferrals", NEW_DEFERRALS)
    assert code == 2 and "reuse the IDs ['data-fill']" in report["error"], report
    _write(root, NEW_DEFERRALS, _deferrals({**reused, "id": "sinit-owner"}))
    code, report = _accept_amendment(root, capsys, AMENDMENT_ACCEPTER, "--deferrals", NEW_DEFERRALS)
    assert code == 0 and report["deferrals_added"] == 1 and report["deferrals_resolved"] == 0, report
    current = _stage(_load(root))["baseline"]
    assert current["state"]["unresolved"]["count"] == 2 and current["state"]["deferrals"]["count"] == 2
    assert current["deferrals_added"][0]["id"] == "sinit-owner"
    _audits(root, capsys, "--strict")


def test_amendment_refusals(amendable: tuple[Path, dict, str], capsys) -> None:
    root, _graph, _gap = amendable
    state = (root / STATE).read_bytes()
    revision = _revision(root)
    refusals = [
        ((SEGMENT_1,), {"revision": str(int(revision) - 1)}, "revision conflict"),
        (("socom:work:no-such-item",), {}, "unknown work item"),
        (("socom:work:ghidra-reconstruction-seed",), {}, "not a source-correlation plan or data reconcile"),
        ((f"{SEGMENT_1}-apply",), {}, "not a source-correlation plan or data reconcile"),
        ((SEGMENT_1,), {"by": "mapper"}, "cannot be amended by its handoff owner mapper"),
        ((SEGMENT_1,), {"reason": " "}, "reason must not be empty"),
        ((SEGMENT_1,), {"evidence": (" ",)}, "at least one --evidence line"),
        ((SEGMENT_1, "--reapply", f"{SEGMENT_3}-apply"), {}, "for a data reconcile amendment only"),
        ((DATA, "--reapply", f"{PROVIDER}-apply"), {}, "is not a source-correlation segment apply"),
    ]
    for arguments, options, message in refusals:
        code, report = _amend(root, capsys, *arguments, **options)
        assert code == 2 and message in report["error"], (arguments, report)
    assert (root / STATE).read_bytes() == state

    # A named further apply is re-applied too; every open amendment is accepted together.
    code, report = _amend(root, capsys, DATA, "--reapply", f"{SEGMENT_3}-apply")
    assert code == 0 and report["applies"] == [f"{SEGMENT_1}-apply", f"{SEGMENT_3}-apply"], report
    code, report = _amend(root, capsys, PROVIDER)
    assert code == 0 and report["amendment"] == SECOND, report
    code, report = _accept_amendment(root, capsys)
    assert code == 2 and f"also --amendment {SECOND}" in report["error"], report
    code, report = _accept_amendment(root, capsys, AMENDMENT_ACCEPTER, amendments=(FIRST, "socom:source-amendment:009"))
    assert code == 2 and "unknown amendment" in report["error"], report
    # A leased amended item cannot be amended again.
    _claim(root, capsys, PROVIDER, owner="mapper-3")
    code, report = _amend(root, capsys, PROVIDER)
    assert code == 2 and "is leased by mapper-3" in report["error"], report
    assert audit_tracker(_load(root), strict=True) == []


def test_an_amendment_needs_the_accepted_stage(closing: tuple[Path, dict, str], capsys) -> None:
    root, _graph, _gap = closing
    code, report = _amend(root, capsys, SEGMENT_1)
    assert code == 2 and "is not accepted with a file baseline" in report["error"], report
    code, report = _accept_amendment(root, capsys)
    assert code == 2 and "is not accepted with a file baseline" in report["error"], report
