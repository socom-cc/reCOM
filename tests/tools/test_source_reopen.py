"""``progress reopen-source-plan``: an accepted stage 4 plan returns for revision until its apply starts."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tools._socom.source_plan import plan_path
from tools._socom.tracker import audit_tracker, refresh_ready_and_stages, reopen_source_plan
from tools._socom.util import SocomError

from test_source_apply import (  # noqa: F401 - ready, workspace and stage3_tracker are fixtures
    BSS,
    DATA,
    PROVIDER,
    SEGMENT_1,
    SEGMENT_3,
    _accept_plans,
    _claim,
    _load,
    _revision,
    _run,
    plans,
    ready,
    stage3_tracker,
    workspace,
)

OWNER_PLANS = (SEGMENT_1, SEGMENT_3, PROVIDER)


def _reopen(root: Path, capsys, item: str, *extra: str, by: str = "orchestrator",
            reason: str = "the linked kind is contested", evidence: tuple[str, ...] = ("stationery lists the file",),
            revision: str | None = None) -> tuple[int, dict]:
    arguments = ["--root", str(root), "progress", "reopen-source-plan", "--item", item, "--by", by,
                 "--reason", reason, "--expected-revision", revision or _revision(root)]
    for line in evidence:
        arguments += ["--evidence", line]
    return _run(capsys, *arguments, *extra)


@pytest.fixture()
def accepted(workspace: tuple[Path, dict]) -> tuple[Path, dict]:
    """Every segment and provider plan accepted: the data reconciles are ready, the applies blocked."""

    root, graph = workspace
    chosen = plans(graph)
    _accept_plans(root, {item: chosen[item] for item in OWNER_PLANS})
    statuses = {row["id"]: row["status"] for row in _load(root)["work_items"]}
    assert {statuses[DATA], statuses[BSS]} == {"ready"}
    assert {statuses[f"{item}-apply"] for item in OWNER_PLANS} == {"blocked"}
    return root, graph


def test_a_reopened_plan_returns_for_revision_and_re_review(accepted: tuple[Path, dict], capsys) -> None:
    root, _graph = accepted
    before = next(row for row in _load(root)["work_items"] if row["id"] == SEGMENT_1)
    plan_bytes = (root / plan_path(SEGMENT_1)).read_bytes()
    revision = _load(root)["revision"]

    code, report = _reopen(root, capsys, SEGMENT_1, "--dry-run")
    assert code == 0, report
    assert report["dry_run"] is True and report["mutation_performed"] is False and report["errors"] == []
    assert report["blocked"] == sorted([BSS, DATA]) and report["status"] == "ready"
    assert _load(root)["revision"] == revision

    code, report = _reopen(root, capsys, SEGMENT_1, evidence=("line 2", "line 1", "line 1"))
    assert code == 0, report
    assert report["revision"] == revision + 1 and report["mutation_performed"] is True
    tracker = _load(root)
    by_id = {row["id"]: row for row in tracker["work_items"]}
    item = by_id[SEGMENT_1]
    assert item["status"] == "ready" and item["handoff"] is None and "accepted" not in item
    assert item["batch"] == before["batch"] and item["evidence"] == before["evidence"]
    entry = item["review_history"][-1]
    assert entry["reopened_by"] == "orchestrator" and entry["reason"] == "the linked kind is contested"
    assert entry["evidence"] == ["line 1", "line 2"] and entry["reopened_at"].endswith("Z")
    assert entry["accepted"] == before["accepted"] and entry["handoff"] == before["handoff"]
    assert entry["handoff_evidence"] == before["evidence"]
    assert {by_id[f"{SEGMENT_1}-apply"]["status"], by_id[DATA]["status"], by_id[BSS]["status"]} == {"blocked"}
    assert by_id[SEGMENT_3]["status"] == "accepted"
    assert (root / plan_path(SEGMENT_1)).read_bytes() == plan_bytes
    assert audit_tracker(tracker, strict=True) == []

    # The re-review: the planner hands off again and may not accept its own plan.
    _claim(root, capsys, SEGMENT_1, owner="mapper-2")
    code, report = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", SEGMENT_1,
                        "--owner", "mapper-2", "--summary", "revised", "--evidence", "plan sha256:revised",
                        "--expected-revision", _revision(root))
    assert code == 0, report
    code, report = _run(capsys, "--root", str(root), "progress", "work", "accept", "--item", SEGMENT_1,
                        "--accepter", "mapper-2", "--expected-revision", _revision(root))
    assert code == 2 and "self-accepted" in report["error"]
    code, report = _run(capsys, "--root", str(root), "progress", "work", "accept", "--item", SEGMENT_1,
                        "--accepter", "scrutinizer-2", "--expected-revision", _revision(root))
    assert code == 0, report
    by_id = {row["id"]: row for row in _load(root)["work_items"]}
    assert by_id[SEGMENT_1]["status"] == "accepted" and len(by_id[SEGMENT_1]["review_history"]) == 1
    assert {by_id[DATA]["status"], by_id[BSS]["status"]} == {"ready"}
    assert audit_tracker(_load(root), strict=True) == []


def test_reopen_refusals_leave_the_tracker_unchanged(accepted: tuple[Path, dict], capsys) -> None:
    root, _graph = accepted
    state = (root / ".agent" / "RECONSTRUCTION_PROGRESS.json").read_bytes()
    revision = _revision(root)
    refusals = [
        ((DATA,), {}, "not a source-correlation segment or provider plan"),
        (("socom:work:ghidra-reconstruction-seed",), {}, "not a source-correlation segment or provider plan"),
        ((SEGMENT_1,), {"revision": str(int(revision) - 1)}, "revision conflict"),
        ((SEGMENT_1,), {"by": "mapper"}, "cannot be reopened by its handoff owner mapper"),
        ((SEGMENT_1,), {"reason": "  "}, "reason must not be empty"),
        ((SEGMENT_1,), {"evidence": (" ",)}, "at least one --evidence line"),
        (("socom:work:no-such-item",), {}, "unknown work item"),
    ]
    for arguments, options, message in refusals:
        code, report = _reopen(root, capsys, *arguments, **options)
        assert code == 2 and message in report["error"], (arguments, report)
    with pytest.raises(SystemExit):  # --evidence is required
        _run(capsys, "--root", str(root), "progress", "reopen-source-plan", "--item", SEGMENT_3, "--by", "x",
             "--reason", "r", "--expected-revision", revision)
    capsys.readouterr()
    assert (root / ".agent" / "RECONSTRUCTION_PROGRESS.json").read_bytes() == state
    code, report = _reopen(root, capsys, SEGMENT_1)
    assert code == 0, report
    code, report = _reopen(root, capsys, SEGMENT_1)
    assert code == 2 and "is ready, not accepted" in report["error"]


def test_reopen_is_refused_once_the_apply_or_a_reconcile_has_started(ready: tuple[Path, dict], capsys) -> None:
    root, _graph = ready
    # Every reconcile is accepted: no plan can be reopened any more, even with its apply ready.
    code, report = _reopen(root, capsys, SEGMENT_3)
    assert code == 2 and f"{BSS} (accepted)" in report["error"] and f"{DATA} (accepted)" in report["error"]
    _claim(root, capsys, f"{SEGMENT_1}-apply")
    code, report = _reopen(root, capsys, SEGMENT_1)
    assert code == 2 and f"{SEGMENT_1}-apply is in_progress" in report["error"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda apply: apply.update(source_apply={"plan_item": SEGMENT_1}), "has an apply record"),
        (lambda apply: apply.update(review_history=[{"rejected_by": "verifier"}]), "has review history"),
        (lambda apply: apply.update(handoff={"owner": "worker"}), "has a handoff"),
        (lambda apply: apply["batch"].update(reservation_correction={"from": ["src"]}), "reservation correction"),
        (lambda apply: apply.update(status="awaiting_acceptance"), "is awaiting_acceptance"),
        (lambda apply: apply.update(status="ready", lease={"owner": "worker"}), "is leased"),
    ],
)
def test_any_trace_of_an_apply_refuses_the_reopen(accepted: tuple[Path, dict], change, message) -> None:
    root, _graph = accepted
    tracker = _load(root)
    by_id = {row["id"]: row for row in tracker["work_items"]}
    change(by_id[f"{SEGMENT_1}-apply"])
    with pytest.raises(SocomError, match=message):
        reopen_source_plan(tracker, SEGMENT_1, "orchestrator", "reason", ["evidence"])


def test_a_leased_plan_or_dependent_refuses_the_reopen(accepted: tuple[Path, dict]) -> None:
    root, _graph = accepted
    tracker = _load(root)
    by_id = {row["id"]: row for row in tracker["work_items"]}
    leased = copy.deepcopy(tracker)
    next(row for row in leased["work_items"] if row["id"] == SEGMENT_1)["lease"] = {"owner": "mapper"}
    with pytest.raises(SocomError, match="is leased by mapper"):
        reopen_source_plan(leased, SEGMENT_1, "orchestrator", "reason", ["evidence"])
    by_id[DATA].update(status="in_progress", lease={"owner": "reconciler"})
    with pytest.raises(SocomError, match=rf"{DATA} \(in_progress\)"):
        reopen_source_plan(tracker, PROVIDER, "orchestrator", "reason", ["evidence"])


def test_a_reopened_provider_plan_keeps_the_strict_audit(accepted: tuple[Path, dict]) -> None:
    root, _graph = accepted
    tracker = _load(root)
    result = reopen_source_plan(tracker, PROVIDER, "orchestrator", "reason", ["evidence"])
    assert result == {"work_item_id": PROVIDER, "apply_item": f"{PROVIDER}-apply", "blocked": sorted([BSS, DATA])}
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    assert audit_tracker(tracker, strict=True) == []
