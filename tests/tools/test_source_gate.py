"""Stage 4 gate route: independent review and acceptance, deferrals and the file-stage baseline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools._socom import source_gate
from tools._socom.source_gate import (
    BASELINE_CITATION,
    deferral_cover,
    normalize_deferrals,
    require_independent,
)
from tools._socom.source_plan import SOURCE_APPLY_ROUTE_ID, SOURCE_SEED_ID, derive_annotations, plan_path
from tools._socom.tracker import audit_tracker, record_stage_baseline
from tools._socom.util import SocomError

from test_source_apply import (  # noqa: F401 - workspace is a fixture
    DATA,
    PROVIDER,
    SEGMENT_1,
    SEGMENT_3,
    STATE,
    _accept_plans,
    _apply,
    _census,
    _claim,
    _load,
    _revision,
    _run,
    plans,
    workspace,
)
from test_source_plan import MAIN, stage3_tracker  # noqa: F401 - stage3_tracker is a fixture

GATE = SOURCE_SEED_ID
REVIEWER = "socom-verifier-g4"
ACCEPTER = "socom-verifier-g4b"
ISSUE = "socom:workspace-issue:00000000000000000001"
RESOLVED = "socom:workspace-issue:00000000000000000002"
DEFERRALS = "build/closeout-source-correlation/deferrals.json"


def _stage3_receipt(root: Path) -> str:
    return next(row for row in _load(root)["stages"] if row["name"] == "ghidra-reconstruction")["baseline"]["receipt_sha256"]


def _receipt(monkeypatch, value: str | None) -> None:
    """The live receipt: ``value``, or an unreachable bridge for ``None``."""

    def fake(root: Path, *, bridge_url: str | None = None, scope: dict | None = None) -> dict:
        if value is None:
            raise SocomError("Ghidra bridge request failed: http://127.0.0.1:8089/check_connection: refused")
        assert scope is not None and len(scope["functions"]) > 0
        return {"ok": True, "mutation_performed": False, "receipt_sha256": value, "receipt": {}}

    monkeypatch.setattr(source_gate, "semantic_receipt", fake)


def _write(root: Path, relative: str, value: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _deferrals(*rows: dict) -> dict:
    return {"kind": "socom-source-gate-deferrals", "schema_version": 1, "deferrals": list(rows)}


def _approved(artifact: str) -> dict:
    return {
        "id": "data-fill",
        "artifacts": [artifact],
        "reason": "fill between objects; no owner evidence",
        "approval": {"by": "user", "at": "2026-10-31", "decision": "Defer the fill gap past stage 4"},
    }


@pytest.fixture()
def closing(workspace: tuple[Path, dict], capsys, monkeypatch) -> tuple[Path, dict, str]:
    """Every stage 4 plan, reconcile and apply accepted, one gap left unresolved: the gate is ready."""

    root, graph = workspace
    chosen = plans(graph)
    data = chosen[DATA]
    gap = data["owners"].pop()["artifacts"][0]
    data["unresolved"] = [{"artifact": gap, "reason": "fill between objects; no owner evidence"}]
    data["annotations"] = derive_annotations(data, graph, MAIN)
    _accept_plans(root, chosen)
    code, report = _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", SOURCE_APPLY_ROUTE_ID,
                        "--expected-revision", _revision(root))
    assert code == 0, report
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
    tracker = _load(root)
    assert next(row for row in tracker["work_items"] if row["id"] == GATE)["status"] == "ready"
    # The strict audit needs the reference identity and sections; deferrals may cite the issue ledger.
    _write(root, ".agent/REFERENCE_CENSUS.json",
           {**_census(graph), "reference": tracker["reference"], "sections": tracker["output_sections"]})
    _write(root, ".agent/WORKSPACE_ISSUES.json", {"schema_version": 1, "revision": 1, "issues": [
        {"id": ISSUE, "kind": "problem", "status": "open", "summary": "User decision: defer the data fill gap"},
        {"id": RESOLVED, "kind": "problem", "status": "resolved", "summary": "an old question"},
    ]})
    _receipt(monkeypatch, _stage3_receipt(root))
    return root, graph, gap


def _check(root: Path, capsys, *extra: str) -> tuple[int, dict]:
    return _run(capsys, "--root", str(root), "source", "gate-check", *extra)


def _handoff(root: Path, capsys, *extra: str, owner: str = REVIEWER) -> tuple[int, dict]:
    return _run(capsys, "--root", str(root), "progress", "handoff-source-gate", "--item", GATE, "--owner", owner,
                "--summary", "gate review", "--expected-revision", _revision(root), *extra)


def _accept(root: Path, capsys, accepter: str, *extra: str) -> tuple[int, dict]:
    return _run(capsys, "--root", str(root), "progress", "accept-source-gate", "--item", GATE, "--accepter", accepter,
                "--evidence", "independent re-run of every gate check", "--expected-revision", _revision(root), *extra)


def test_the_gate_lists_pending_items_and_leases(workspace: tuple[Path, dict], capsys, monkeypatch) -> None:
    root, graph = workspace
    _accept_plans(root, plans(graph))
    _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", SOURCE_APPLY_ROUTE_ID,
         "--expected-revision", _revision(root))
    _claim(root, capsys, f"{SEGMENT_1}-apply")
    _receipt(monkeypatch, _stage3_receipt(root))
    code, report = _check(root, capsys)
    assert code == 1 and not report["ok"]
    problems = json.loads((root / report["output"]).read_text(encoding="utf-8"))["problems"]
    assert any("items are not accepted" in line and f"{SEGMENT_1}-apply" in line for line in problems)
    assert any("work items are leased" in line and "(worker)" in line for line in problems)
    # The gate waits for its applies: no reviewer can claim it yet.
    code, report = _run(capsys, "--root", str(root), "progress", "work", "claim", "--item", GATE, "--owner", REVIEWER,
                        "--expected-revision", _revision(root))
    assert code == 2 and "not ready" in report["error"]


def test_an_independent_review_and_acceptance_record_the_file_stage_baseline(
    closing: tuple[Path, dict, str], capsys
) -> None:
    root, _graph, gap = closing
    # Unresolved rows are listed, never silently accepted.
    code, report = _check(root, capsys)
    assert code == 1 and report["counts"]["unresolved"] == 1 and report["counts"]["uncovered"] == 1
    full = json.loads((root / report["output"]).read_text(encoding="utf-8"))
    assert full["unresolved"] == [{"item": DATA, "artifact": gap, "reason": "fill between objects; no owner evidence",
                                   "deferral": None}]
    assert any("have no recorded deferral" in line for line in report["problems"])
    _write(root, DEFERRALS, _deferrals(_approved(gap)))
    code, report = _check(root, capsys, "--deferrals", DEFERRALS)
    assert code == 0 and report["ok"], report["problems"]
    code, report = _check(root, capsys, "--deferrals", DEFERRALS, "--skip-receipt")
    assert code == 1 and "not checked" in report["receipt"]["error"]

    # A planner or a tool maintainer is not an independent reviewer; the generic routes refuse the gate.
    for owner, message in (("mapper", "handed off source-correlation work"), ("socom-tool-maintainer-m18", "tool maintainer")):
        _claim(root, capsys, GATE, owner=owner)
        code, report = _handoff(root, capsys, "--deferrals", DEFERRALS, owner=owner)
        assert code == 2 and message in report["error"], report
        code, report = _run(capsys, "--root", str(root), "progress", "work", "release", "--item", GATE, "--owner", owner,
                            "--expected-revision", _revision(root))
        assert code == 0, report
    _claim(root, capsys, GATE, owner=REVIEWER)
    code, report = _run(capsys, "--root", str(root), "progress", "work", "handoff", "--item", GATE, "--owner", REVIEWER,
                        "--summary", "s", "--expected-revision", _revision(root))
    assert code == 2 and "use progress handoff-source-gate" in report["error"]
    # Without a deferral file the unresolved gap refuses the handoff.
    code, report = _handoff(root, capsys)
    assert code == 2 and "have no recorded deferral" in report["error"]
    state = (root / STATE).read_bytes()
    code, report = _handoff(root, capsys, "--deferrals", DEFERRALS, "--dry-run")
    assert code == 0 and report["dry_run"] and report["baseline_sha256"], report
    assert (root / STATE).read_bytes() == state
    code, report = _handoff(root, capsys, "--deferrals", DEFERRALS, "--evidence", "gate-check report")
    assert code == 0 and report["status"] == "awaiting_acceptance", report
    reviewed = report["baseline_sha256"]
    gate = next(row for row in _load(root)["work_items"] if row["id"] == GATE)
    assert gate["source_gate"]["deferrals"][0]["artifacts"] == [gap]
    assert f"{BASELINE_CITATION}{reviewed}" in gate["evidence"] and "gate-check report" in gate["evidence"]

    # The reviewer cannot accept; the generic accept refuses the gate.
    code, report = _accept(root, capsys, REVIEWER)
    assert code == 2 and "cannot be accepted by its reviewer" in report["error"]
    code, report = _run(capsys, "--root", str(root), "progress", "work", "accept", "--item", GATE, "--accepter", ACCEPTER,
                        "--expected-revision", _revision(root))
    assert code == 2 and "use progress accept-source-gate" in report["error"]
    code, report = _accept(root, capsys, ACCEPTER)
    assert code == 0 and report["stage_status"] == "accepted" and report["baseline_sha256"] == reviewed, report

    tracker = _load(root)
    stage = next(row for row in tracker["stages"] if row["name"] == "source-correlation")
    baseline = stage["baseline"]
    assert baseline["kind"] == "source-file-baseline" and baseline["baseline_sha256"] == reviewed
    assert (baseline["reviewed_by"], baseline["accepted_by"]) == (REVIEWER, ACCEPTER)
    state = baseline["state"]
    assert state["plan_count"] == 5 and state["unresolved"]["count"] == 1 and state["deferrals"]["artifact_count"] == 1
    assert state["deferrals"]["by_basis"] == {"user-approval": 1}
    assert state["ghidra"]["receipt_sha256"] == _stage3_receipt(root)
    assert {row["item"]: row["unresolved_count"] for row in state["plans"]}[DATA] == 1
    assert f"{BASELINE_CITATION}{reviewed}" in stage["accepted_evidence"]
    assert audit_tracker(tracker, strict=True) == []
    code, report = _run(capsys, "--root", str(root), "progress", "audit", "--strict")
    assert code == 0, report
    code, report = _run(capsys, "--root", str(root), "audit", "source-baseline", "--strict")
    assert code == 0 and report["recorded"] and report["apply_files_unchanged"], report
    # The stage-3 route never records a file-only stage's baseline.
    with pytest.raises(SocomError, match="file-only"):
        record_stage_baseline(tracker, "source-correlation", "x", ["e"], receipt_sha256="0" * 64, receipt={})

    # The audits hold the record: a changed baseline or annotation edges outside accepted work.
    tampered = json.loads(json.dumps(tracker))
    next(row for row in tampered["stages"] if row["name"] == "source-correlation")["baseline"]["state"]["unresolved"]["count"] = 0
    assert any("baseline state differs" in error for error in audit_tracker(tampered))
    tampered = json.loads(json.dumps(tracker))
    next(row for row in tampered["work_items"] if row["id"] == GATE)["accepted"].pop("route")
    assert any("accepted outside progress accept-source-gate" in error for error in audit_tracker(tampered))
    extra = root / "src" / "gamez" / "zBaz" / "extra.cpp"
    extra.write_text("// @socom-artifact defines main socom:function:0x140020\n", encoding="utf-8")
    code, report = _run(capsys, "--root", str(root), "audit", "source-baseline")
    assert code == 1 and any("differ from the baseline" in error for error in report["errors"])
    extra.unlink()
    (root / plan_path(DATA)).unlink()
    code, report = _run(capsys, "--root", str(root), "audit", "source-baseline")
    assert code == 0 and report["unavailable_plan_count"] == 1
    code, report = _run(capsys, "--root", str(root), "audit", "source-baseline", "--strict")
    assert code == 1 and any("unavailable" in error for error in report["errors"])


def test_the_gate_refuses_a_changed_or_unreachable_receipt(closing: tuple[Path, dict, str], capsys, monkeypatch) -> None:
    root, _graph, gap = closing
    _write(root, DEFERRALS, _deferrals(_approved(gap)))
    _claim(root, capsys, GATE, owner=REVIEWER)
    state = (root / STATE).read_bytes()
    _receipt(monkeypatch, "0" * 64)
    code, report = _handoff(root, capsys, "--deferrals", DEFERRALS)
    assert code == 2 and "differs from the ghidra-reconstruction baseline" in report["error"]
    _receipt(monkeypatch, None)
    code, report = _handoff(root, capsys, "--deferrals", DEFERRALS)
    assert code == 2 and "live Ghidra receipt is unavailable" in report["error"] and "nothing was recorded" in report["error"]
    code, report = _check(root, capsys, "--deferrals", DEFERRALS)
    assert code == 1 and report["receipt"]["ok"] is False and "unavailable" in report["receipt"]["error"]
    assert (root / STATE).read_bytes() == state
    # A rejected review returns the gate with its record in the review history.
    _receipt(monkeypatch, _stage3_receipt(root))
    code, report = _handoff(root, capsys, "--deferrals", DEFERRALS)
    assert code == 0, report
    _receipt(monkeypatch, None)
    code, report = _accept(root, capsys, ACCEPTER)
    assert code == 2 and "unavailable" in report["error"]
    code, report = _run(capsys, "--root", str(root), "progress", "work", "reject", "--item", GATE, "--reviewer", ACCEPTER,
                        "--reason", "re-run with the bridge up", "--expected-revision", _revision(root))
    assert code == 0, report
    gate = next(row for row in _load(root)["work_items"] if row["id"] == GATE)
    assert gate["status"] == "ready" and "source_gate" not in gate
    assert gate["review_history"][-1]["source_gate"]["reviewed_by"] == REVIEWER


def test_deferrals_cite_an_open_issue_or_the_users_decision() -> None:
    gap, other = "socom:gap:0x426484", "socom:data:0x426470"
    rows, problems = normalize_deferrals(_deferrals(
        {"id": "by-issue", "artifacts": [gap], "reason": "deferred", "issue": ISSUE},
    ))
    assert problems == []
    ledger = {"issues": [{"id": ISSUE, "status": "open"}, {"id": RESOLVED, "status": "resolved"}]}
    cover, problems = deferral_cover([{"item": DATA, "artifact": gap, "reason": "r"}], rows, ledger)
    assert problems == [] and cover["by_basis"] == {"workspace-issue": 1}
    _rows, problems = normalize_deferrals(_deferrals(
        {"id": "both", "artifacts": [gap], "reason": "r", "issue": ISSUE,
         "approval": {"by": "user", "at": "2026-10-31", "decision": "defer"}},
        {"id": "neither", "artifacts": [gap], "reason": "r"},
        {"id": "agent", "artifacts": [gap], "reason": "r", "approval": {"by": "socom-coordinator", "at": "2026-10-31", "decision": "x"}},
        {"id": "Bad Id", "artifacts": [], "reason": ""},
    ))
    assert sum("exactly one of issue" in line for line in problems) == 3  # both, neither, Bad Id
    assert any("agent approval must be" in line for line in problems)
    assert any("needs an id" in line for line in problems) and any("distinct artifact IDs" in line for line in problems)
    rows, _ = normalize_deferrals(_deferrals(
        {"id": "resolved", "artifacts": [gap], "reason": "r", "issue": RESOLVED},
        {"id": "unknown", "artifacts": [gap, other], "reason": "r", "issue": "socom:workspace-issue:ffff"},
    ))
    _cover, problems = deferral_cover([{"item": DATA, "artifact": gap, "reason": "r"}], rows, ledger)
    assert any("which is resolved, not open" in line for line in problems)
    assert any("unknown workspace issue" in line for line in problems)
    assert any("deferred more than once" in line for line in problems)
    assert any("not unresolved in an accepted owner plan" in line and other in line for line in problems)


def test_a_unit_keeps_one_path_original_and_classification_across_plans() -> None:
    def row(unit: str, path: str | None, original: str | None, classification: str = "authored") -> dict:
        return {"translation_unit": unit, "workspace_path": path, "original_path": original, "classification": classification}

    agreeing = [
        ("p1", {"owners": [row("a.cpp", "src/x/a.cpp", "Z:\\dev\\x\\a.cpp")]}),
        ("p2", {"owners": [row("a.cpp", "src/x/a.cpp", None)]}),  # an unstated original path agrees
    ]
    assert source_gate.unit_conflicts(agreeing) == []
    problems = source_gate.unit_conflicts(agreeing + [
        ("p3", {"owners": [row("a.cpp", "src/y/a.cpp", "Z:\\dev\\y\\a.cpp")]}),
        ("p4", {"owners": [row("b.cpp", "src/x/b.cpp", None, "provider")]}),
        ("p5", {"owners": [row("b.cpp", "src/x/b.cpp", None)]}),
    ])
    assert any(line.startswith("unit a.cpp is owned inconsistently") and "p3" in line for line in problems)
    assert any(line.startswith("unit a.cpp names different original paths") for line in problems)
    assert any(line.startswith("unit b.cpp is owned inconsistently") for line in problems)
    assert any(line.startswith("workspace path src/x/b.cpp is owned inconsistently") for line in problems)


def test_gate_reviewers_are_independent() -> None:
    assert require_independent(" socom-verifier-g4 ", "reviewer", {"mapper"}) == "socom-verifier-g4"
    for name in ("", "mapper", "socom-tool-maintainer-m18", "progress open-capability-gate"):
        with pytest.raises(SocomError):
            require_independent(name, "reviewer", {"mapper"})
