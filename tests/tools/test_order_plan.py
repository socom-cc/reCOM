"""Stage 5 phase A2: the order-target producer, order plans and their draft, decide and validate routes."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools._socom.order_draft import derive_evidence
from tools._socom.order_plan import (
    COMPILER_BLOCKER,
    ORDER_COMPILE_ROUTE_ID,
    ORDER_LINK_ID,
    ORDER_SEED_ID,
    ORDER_SEGMENT_KIND,
    ORDER_SKELETON_ROUTE_ID,
    ORDER_STAGE,
    UNSET,
    decide_order_row,
    draft_order_plan,
    order_plan_path,
    validate_order_plan,
)
from tools._socom.tracker import audit_tracker
from tools._socom.util import SocomError, sha256_file

from test_order_draft import ROWS, _raw, _target
from test_source_amend import _amend, amendable  # noqa: F401 - amendable is a fixture
from test_source_apply import DATA, STATE, _claim, _load, _revision, _run, workspace  # noqa: F401 - workspace is a fixture
from test_source_gate import closing  # noqa: F401 - a fixture amendable needs
from test_source_plan import stage3_tracker  # noqa: F401 - a fixture the workspace needs

ITEM = "socom:work:order-segment-001"
BASELINE = "b" * 64


def _id(key: str) -> str:
    return ROWS[key]["id"]


def _tracker(baseline: str = BASELINE) -> dict:
    return {
        "revision": 7,
        "stages": [{"name": "source-correlation", "status": "accepted", "baseline": {"baseline_sha256": baseline}}],
        "work_items": [
            {"id": ITEM, "stage": ORDER_STAGE, "kind": ORDER_SEGMENT_KIND, "status": "in_progress",
             "batch": {"segment_number": 1, "units": ["d.cpp", "n.cpp"]}},
        ],
    }


@pytest.fixture()
def context() -> tuple[dict, dict, dict]:
    target = _target()
    return _tracker(), target, derive_evidence(target, _raw())


def _draft(context: tuple[dict, dict, dict]) -> dict:
    tracker, target, derived = context
    plan, carried = draft_order_plan(tracker, tracker["work_items"][0], target, derived)
    assert carried == {"carried": 0, "dropped": []}
    return plan


def _unit(plan: dict, name: str) -> dict:
    return next(row for row in plan["units"] if row["unit"] == name)


def _validate(context: tuple[dict, dict, dict], plan: dict, check: bool = False) -> dict:
    tracker, target, derived = context
    return validate_order_plan(tracker, plan, target, derived, check=check)


def _decide(plan: dict, key: str, **options) -> list[dict]:
    options.setdefault("owner", "planner")
    options.setdefault("basis", "evidence")
    return decide_order_row(plan, _id(key), **options)[1]


def test_the_draft_decides_what_the_evidence_and_rule_fix_and_leaves_judgment_open(context: tuple) -> None:
    plan = _draft(context)
    assert (plan["kind"], plan["work_item_id"], plan["segment_number"]) == ("socom-order-plan", ITEM, 1)
    assert [unit["unit"] for unit in plan["units"]] == ["d.cpp", "n.cpp"]
    assert plan["inputs"]["stage4_baseline_sha256"] == BASELINE and len(plan["inputs"]["segment_target_sha256"]) == 64
    d = _unit(plan, "d.cpp")
    # DWARF lines prove the source order; the in-class member off the reverse chain is drafted in_class and left open.
    rows = [(row["name"], row["position"], row["in_class"], row["class"], row["basis"]) for row in d["functions"]]
    assert rows == [
        ("Get__Q215@unnamed@d_cpp@4CItrFv", 1, True, "proven", "dwarf-line 5"),
        ("f0__Fv", 2, False, "proven", "dwarf-line 8"),
        ("f1__Fv", 3, False, "proven", "dwarf-line 10"),
        ("f2__Fv", 4, False, "proven", "dwarf-line 20"),
        ("f3__Fv", 5, False, "proven", "dwarf-line 30"),
    ]
    assert d["functions"][0]["evidence"] == {"line": 5, "first_user": _id("f2")}
    assert [(row["artifact"], row["kind"]) for row in d["open"]] == [(_id("inl"), "out-of-rule")]
    assert "its first caller f2__Fv is emitted before it" in d["open"][0]["reason"]
    assert [(row["name"], row["reason"]) for row in d["not_placed"]] == [
        ("__arraydtor$12", "compiler-generated"), ("__dt__Q215@unnamed@d_cpp@4CItrFv", "no-dwarf-line"),
    ]
    assert d["stage7_targets"] == {"copies": [_id("copy")], "literals": []}
    n = _unit(plan, "n.cpp")
    # Without lines the rule drafts reverse address order; the local-static counter constrains what it agrees with.
    rows = [(row["name"], row["position"], row["class"], row["basis"]) for row in n["functions"]]
    assert rows == [
        ("ga__Fv", 1, "constrained", "local-static-counter 100"),
        ("gb__Fv", 2, "constrained", "local-static-counter 150"),
        ("gc__Fv", 3, "hypothesis", "reverse-address rule"),
        ("gz__Fv", 4, "hypothesis", "reverse-address rule"),
    ]
    (bss,) = n["data"]
    rows = [(row["name"], row["position"], row["class"], row["basis"]) for row in bss["rows"]]
    assert rows == [
        ("x$110", 1, "constrained", "local-static-counter 110"),
        ("y$120", 2, "constrained", "local-static-counter 120"),
        ("g_one", 3, "constrained", "static-initializer rank 0"),
        ("g_two", 4, "hypothesis", "declaration-order rule (address order)"),
        ("g_three", 5, "hypothesis", "declaration-order rule (address order)"),
    ]
    assert sorted((row["artifact"], row["kind"]) for row in n["open"]) == sorted(
        (_id(key), "constraint-conflict") for key in ("gc", "gz", "two", "three")
    )
    assert [(row["name"], row["reason"]) for row in n["not_placed"]] == [
        ("__sinit_n_cpp", "generated"), ("init$111", "static-guard"), ("g_common", "common"),
    ]
    report = _validate(context, plan)
    assert report["ok"] and report["mismatches"] == [] and report["summary"]["open"] == 5, report
    assert report["summary"]["classes"] == {"proven": 5, "constrained": 5, "hypothesis": 4}
    checked = _validate(context, plan, check=True)
    assert not checked["ok"] and "5 open rows remain" in checked["problems"][-1]


def test_decisions_settle_open_rows_and_the_rule_check_lists_mismatches(context: tuple) -> None:
    plan = _draft(context)
    changes = _decide(plan, "inl", in_class=True, basis="one-line member of the file-local class CItr")
    assert changes == [{"artifact": _id("inl"), "settled": "out-of-rule"}, {"artifact": _id("inl"), "decided": "functions"}]
    d = _unit(plan, "d.cpp")
    assert d["open"] == [] and d["settled"][0]["basis"] == "one-line member of the file-local class CItr"
    assert d["functions"][0]["decision"]["by"] == "planner"
    # Keeping the rule order against a counter settles the conflict.
    for key in ("gc", "gz"):
        _decide(plan, key, basis="the counter's static belongs to an inlined helper")
    for key in ("two", "three"):
        _decide(plan, key, basis="initializer scheduling noise; DIE order agrees with the address")
    assert _validate(context, plan, check=True)["ok"]

    # Moving a function against the rule is listed as a mismatch, with the positions.
    _decide(plan, "gz", position=1, basis="moved")
    n = _unit(plan, "n.cpp")
    assert [(row["name"], row["position"]) for row in n["functions"]] == [
        ("gz__Fv", 1), ("ga__Fv", 2), ("gb__Fv", 3), ("gc__Fv", 4),
    ]
    report = _validate(context, plan)
    assert not report["ok"]
    assert [(row["before"], row["after"], row["positions"]) for row in report["mismatches"]] == [("gz__Fv", "gc__Fv", [1, 4])]
    _decide(plan, "gz", position=4, basis="back to the rule order")
    # An out-of-rule member decided out of line breaks the reverse order; in class again, it fits.
    _decide(plan, "inl", in_class=False, basis="try out of line")
    assert {row["kind"] for row in _validate(context, plan)["mismatches"]} == {"reverse-order"}
    _decide(plan, "inl", in_class=True, position=None, basis="in its class body, no source position")
    assert _unit(plan, "d.cpp")["functions"][-1]["position"] is None
    assert [row["position"] for row in _unit(plan, "d.cpp")["functions"][:4]] == [1, 2, 3, 4]
    assert _validate(context, plan, check=True)["ok"]
    # Data out of declaration order is a mismatch too.
    _decide(plan, "x", position=2, basis="swap")
    assert {row["kind"] for row in _validate(context, plan)["mismatches"]} == {"declaration-order"}

    with pytest.raises(SocomError, match="cannot be proven"):
        _decide(plan, "gz", klass="proven")
    with pytest.raises(SocomError, match="functions only"):
        _decide(plan, "x", in_class=True)
    with pytest.raises(SocomError, match="needs a source position"):
        _decide(plan, "f0", position=None)
    with pytest.raises(SocomError, match="needs --basis"):
        _decide(plan, "f0", basis=" ")
    with pytest.raises(SocomError, match="not in the plan"):
        decide_order_row(plan, "socom:function:0xdead", owner="planner", basis="x")
    with pytest.raises(SocomError, match="outside 1..4"):
        _decide(plan, "f0", position=9)


def test_validation_refuses_incomplete_dishonest_or_stale_plans(context: tuple) -> None:
    tracker, target, derived = context
    plan = _draft(context)

    def problems(changed: dict, state: dict = tracker) -> list[str]:
        return validate_order_plan(state, changed, target, derived)["problems"]

    changed = copy.deepcopy(plan)
    _unit(changed, "n.cpp")["functions"].pop()
    found = problems(changed)
    assert any("definitions not listed" in text for text in found) and any("positions must number" not in text for text in found)
    changed = copy.deepcopy(plan)
    _unit(changed, "n.cpp")["not_placed"].append(dict(_unit(changed, "n.cpp")["not_placed"][0]))
    assert any("listed more than once" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    _unit(changed, "n.cpp")["stage7_targets"]["copies"] = [_id("copy")]
    assert any("stage7_targets" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    _unit(changed, "n.cpp")["functions"][3]["class"] = "proven"
    assert any("proven without a DWARF line" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    _unit(changed, "n.cpp")["functions"][3]["class"] = "constrained"
    assert any("constrained, but no counter" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    _unit(changed, "n.cpp")["open"] = []
    assert any("open rows removed without a decision" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    _unit(changed, "d.cpp")["functions"][1]["evidence"]["line"] = 99
    assert any("evidence differs" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    changed["units"].reverse()
    assert any("the plan lists units" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    _unit(changed, "d.cpp")["functions"][1]["position"] = 7
    assert any("positions must number" in text for text in problems(changed))
    changed = copy.deepcopy(plan)
    changed["surprise"] = 1
    _unit(changed, "d.cpp")["notes"].append("bad\x07bell")
    found = problems(changed)
    assert any("unknown plan fields" in text for text in found) and any("control character" in text for text in found)
    # A changed stage 4 baseline makes the plan stale: re-draft.
    stale = problems(plan, _tracker("c" * 64))
    assert any(text.startswith("stale stage 4 baseline") and "re-draft" in text for text in stale)
    other = copy.deepcopy(tracker)
    other["work_items"][0]["batch"]["units"] = ["d.cpp"]
    assert any("units changed since decomposition" in text for text in problems(plan, other))
    assert "is not a" in validate_order_plan(tracker, {**plan, "work_item_id": "socom:work:x"}, target, derived)["problems"][-1]


def test_a_re_draft_keeps_the_planners_decisions(context: tuple) -> None:
    tracker, target, derived = context
    plan = _draft(context)
    _decide(plan, "inl", in_class=True, basis="in-class member")
    _decide(plan, "gc", basis="rule order kept")
    _decide(plan, "gz", basis="rule order kept")
    _decide(plan, "x", position=2, basis="moved")
    _unit(plan, "n.cpp")["notes"].append("checked the counters")
    fresh, carried = draft_order_plan(tracker, tracker["work_items"][0], target, derived, plan)
    assert carried == {"carried": 7, "dropped": []}
    n = _unit(fresh, "n.cpp")
    assert [row["name"] for row in sorted(n["data"][0]["rows"], key=lambda row: row["position"])][:2] == ["y$120", "x$110"]
    assert n["notes"] == ["checked the counters"] and n["functions"][2]["decision"]["by"] == "planner"
    # The settled rows come along; the conflicts nobody decided stay open.
    assert sorted(row["artifact"] for row in n["open"]) == sorted(_id(key) for key in ("two", "three"))
    assert _unit(fresh, "d.cpp")["open"] == []


# -- the producer, the items and the CLI over a synthetic accepted stage 4 -------------------


def _decompose(root: Path, capsys, *extra: str) -> tuple[int, dict]:
    return _run(capsys, "--root", str(root), "progress", "decompose-stage", "--stage", ORDER_STAGE,
                "--expected-revision", _revision(root), *extra)


def _handoff(root: Path, capsys, item: str, owner: str, *evidence: str) -> tuple[int, dict]:
    arguments = ["--root", str(root), "progress", "work", "handoff", "--item", item, "--owner", owner,
                 "--summary", "order plan", "--expected-revision", _revision(root)]
    for line in evidence:
        arguments += ["--evidence", line]
    return _run(capsys, *arguments)


def _accept(root: Path, capsys, item: str, accepter: str = "scrutinizer-5") -> tuple[int, dict]:
    return _run(capsys, "--root", str(root), "progress", "work", "accept", "--item", item, "--accepter", accepter,
                "--evidence", "order plan validate --check re-run", "--expected-revision", _revision(root))


def _cited(root: Path, item: str) -> str:
    return f"{order_plan_path(item)} sha256:{sha256_file(root / order_plan_path(item))}"


def test_the_producer_decomposes_the_stage_and_plans_hand_off_only_when_valid(
    amendable: tuple[Path, dict, str], capsys
) -> None:
    root, _graph, _gap = amendable
    state = (root / STATE).read_bytes()
    code, report = _decompose(root, capsys, "--dry-run")
    assert code == 0 and report["errors"] == [], report
    assert report["item_counts"] == {
        "capability-gate": 2, "order-apply-segment": 2, "order-compile-segment": 2, "order-plan-link": 1,
        "order-plan-segment": 2, "stage-gate": 1,
    }
    assert set(report["ready_sample"]) >= {"socom:work:order-segment-001", "socom:work:order-segment-003", ORDER_LINK_ID}
    assert (root / STATE).read_bytes() == state
    code, report = _decompose(root, capsys)
    assert code == 0, report
    tracker = _load(root)
    assert audit_tracker(tracker, strict=True) == []
    items = {row["id"]: row for row in tracker["work_items"]}
    stage = next(row for row in tracker["stages"] if row["name"] == ORDER_STAGE)
    record = stage["decomposition"]
    baseline = next(row for row in tracker["stages"] if row["name"] == "source-correlation")["baseline"]["baseline_sha256"]
    assert (record["producer"], record["segments"], record["unit_count"]) == ("order-target", [1, 3], 2)
    assert record["stage4_baseline_sha256"] == baseline and len(record["producer_sha256"]) == 64
    first, third = items["socom:work:order-segment-001"], items["socom:work:order-segment-003"]
    assert (first["batch"]["units"], third["batch"]["units"]) == (["a.cpp"], ["b.cpp"])
    assert first["dependencies"] == ["socom:work:source-correlation-seed"] and first["resources"] == ["build/order-plans"]
    assert first["status"] == "ready" and items[ORDER_LINK_ID]["status"] == "ready"
    # Phase B (skeletons, no compile) waits for the skeleton route; phase C (compile) for its apply and the compile route.
    apply = items["socom:work:order-segment-001-apply"]
    assert apply["resources"] == ["src/gamez/zBar"] and apply["dependencies"] == ["socom:work:order-segment-001", ORDER_SKELETON_ROUTE_ID]
    assert apply["batch"]["phase"] == "B" and items["socom:work:order-segment-003-apply"]["resources"] == ["src/gamez/zBaz"]
    compiled = items["socom:work:order-segment-001-compile"]
    assert compiled["kind"] == "order-compile-segment" and compiled["batch"]["phase"] == "C"
    assert compiled["dependencies"] == ["socom:work:order-segment-001-apply", ORDER_COMPILE_ROUTE_ID]
    skeleton, route = items[ORDER_SKELETON_ROUTE_ID], items[ORDER_COMPILE_ROUTE_ID]
    assert (skeleton["kind"], skeleton["status"], skeleton["batch"].get("blocker")) == ("capability-gate", "blocked", None)
    assert (route["kind"], route["status"], route["batch"]["blocker"]) == ("capability-gate", "blocked", COMPILER_BLOCKER)
    gate = items[ORDER_SEED_ID]
    # The stage is not accepted without the compiler: the gate waits for every phase C item.
    assert gate["kind"] == "stage-gate" and set(gate["dependencies"]) == {
        "socom:work:order-segment-001-compile", "socom:work:order-segment-003-compile", ORDER_LINK_ID,
    }
    assert ORDER_STAGE in next(row for row in tracker["blockers"] if row["id"] == COMPILER_BLOCKER)["blocks"]
    code, refused = _decompose(root, capsys)
    assert code == 2 and "already decomposed" in refused["error"]
    # The skeleton route is registered (function-order-skeletons opens its gate); the compile route is not.
    code, opened = _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", ORDER_SKELETON_ROUTE_ID,
                        "--expected-revision", _revision(root), "--dry-run")
    assert code == 0 and opened["ok"] and opened["capability"] == "function-order-skeletons", opened
    code, refused = _run(capsys, "--root", str(root), "progress", "open-capability-gate", "--item", ORDER_COMPILE_ROUTE_ID,
                         "--expected-revision", _revision(root))
    assert code == 2 and "no registered capability opens" in refused["error"]

    # The audit holds the structure: the routes stay blocked, the items wait for them, the record binds the items.
    for gate_id, message in ((ORDER_SKELETON_ROUTE_ID, "must be accepted by progress open-capability-gate"),
                             (ORDER_COMPILE_ROUTE_ID, "no active capability opens it")):
        broken = copy.deepcopy(tracker)
        next(row for row in broken["work_items"] if row["id"] == gate_id)["status"] = "accepted"
        assert any(message in text for text in audit_tracker(broken))
    broken = copy.deepcopy(tracker)
    next(row for row in broken["work_items"] if row["id"] == "socom:work:order-segment-001-apply")["status"] = "ready"
    assert any("the order applies must stay blocked" in text for text in audit_tracker(broken))
    broken = copy.deepcopy(tracker)
    next(row for row in broken["work_items"] if row["id"] == "socom:work:order-segment-001-compile")["dependencies"] = [
        "socom:work:order-segment-001", ORDER_COMPILE_ROUTE_ID,
    ]
    assert any("must depend on socom:work:order-segment-001-apply" in text for text in audit_tracker(broken))
    broken = copy.deepcopy(tracker)
    next(row for row in broken["work_items"] if row["id"] == "socom:work:order-segment-003")["batch"]["units"] = ["a.cpp"]
    assert any("producer_sha256 differs" in text for text in audit_tracker(broken))

    # A segment plan: drafted, decided under the lease, validated, handed off citing its SHA-256, accepted independently.
    base = ["--root", str(root), "order", "plan"]
    plan = order_plan_path("socom:work:order-segment-001")
    _claim(root, capsys, "socom:work:order-segment-001", owner="planner-5")
    code, packet = _run(capsys, "--root", str(root), "progress", "work", "packet", "--item", "socom:work:order-segment-001",
                        "--owner", "planner-5")
    assert code == 0 and packet["role"] == "socom-source-owner-mapper" and packet["allowed_paths"] == [plan, "build/order-plans/planner-5/"]
    code, drafted = _run(capsys, *base, "draft", "--item", "socom:work:order-segment-001")
    assert code == 0 and (drafted["output"], drafted["units"], drafted["open_rows"]) == (plan, 1, 0), drafted
    body = json.loads((root / plan).read_text(encoding="utf-8"))
    function = body["units"][0]["functions"][0]["artifact"]
    code, refused = _run(capsys, *base, "decide", "--plan", plan, "--lease-owner", "someone-else", "--artifact", function,
                         "--basis", "x")
    assert code == 2 and "leased by planner-5" in refused["error"]
    code, decided = _run(capsys, *base, "decide", "--plan", plan, "--lease-owner", "planner-5", "--artifact", function,
                         "--basis", "the only out-of-line definition of a.cpp")
    assert code == 0 and decided["changes"] == [{"artifact": function, "decided": "functions"}]
    code, valid = _run(capsys, *base, "validate", "--plan", plan, "--check", "--output", "build/order-plans/report.json")
    assert code == 0 and valid["ok"] and valid["summary"]["decided"] == 1, valid
    code, refused = _handoff(root, capsys, "socom:work:order-segment-001", "planner-5", "no citation")
    assert code == 2 and "must cite the plan's SHA-256" in refused["error"]
    code, handed = _handoff(root, capsys, "socom:work:order-segment-001", "planner-5", _cited(root, "socom:work:order-segment-001"))
    assert code == 0 and handed["work_item"]["status"] == "awaiting_acceptance", handed
    code, accepted = _accept(root, capsys, "socom:work:order-segment-001")
    assert code == 0 and accepted["work_item"]["status"] == "accepted", accepted
    # An accepted plan is re-drafted only after a reopen (not by its planner); the re-draft keeps the decision.
    code, refused = _run(capsys, *base, "draft", "--item", "socom:work:order-segment-001")
    assert code == 2 and "reopen it" in refused["error"]
    reopen = ["--root", str(root), "progress", "work", "reopen", "--item", "socom:work:order-segment-001", "--reason", "re-plan"]
    code, refused = _run(capsys, *reopen, "--reviewer", "planner-5", "--expected-revision", _revision(root))
    assert code == 2 and "handoff owner" in refused["error"]
    code, reopened = _run(capsys, *reopen, "--reviewer", "scrutinizer-5", "--expected-revision", _revision(root))
    assert code == 0 and reopened["work_item"]["status"] == "ready", reopened
    assert _load(root)["work_items"][0]["id"]  # the tracker still loads
    code, drafted = _run(capsys, *base, "draft", "--item", "socom:work:order-segment-001")
    assert code == 0 and drafted["carried_decisions"] == 1, drafted

    # A plan edited after its handoff is refused at acceptance.
    third_plan = order_plan_path("socom:work:order-segment-003")
    _claim(root, capsys, "socom:work:order-segment-003", owner="planner-6")
    assert _run(capsys, *base, "draft", "--item", "socom:work:order-segment-003")[0] == 0
    code, handed = _handoff(root, capsys, "socom:work:order-segment-003", "planner-6", _cited(root, "socom:work:order-segment-003"))
    assert code == 0, handed
    edited = json.loads((root / third_plan).read_text(encoding="utf-8"))
    edited["notes"].append("edited after the handoff")
    (root / third_plan).write_text(json.dumps(edited), encoding="utf-8")
    code, refused = _accept(root, capsys, "socom:work:order-segment-003")
    assert code == 2 and "must cite the plan's SHA-256" in refused["error"]

    # The link plan is the order link-spec output.
    link = order_plan_path(ORDER_LINK_ID)
    _claim(root, capsys, ORDER_LINK_ID, owner="planner-7")
    code, drafted = _run(capsys, *base, "draft", "--item", ORDER_LINK_ID)
    assert code == 0 and drafted["objects"] == 3 and drafted["violations"] == 0
    assert json.loads((root / link).read_text(encoding="utf-8"))["stage4_baseline_sha256"] == baseline
    code, valid = _run(capsys, *base, "validate", "--plan", link, "--check")
    assert code == 0 and valid["ok"], valid
    assert _handoff(root, capsys, ORDER_LINK_ID, "planner-7", _cited(root, ORDER_LINK_ID))[0] == 0
    assert _accept(root, capsys, ORDER_LINK_ID)[0] == 0
    tracker = _load(root)
    statuses = {row["id"]: row["status"] for row in tracker["work_items"] if row["stage"] == ORDER_STAGE}
    # Phase B stays closed behind the route, whatever the plans' state.
    assert statuses["socom:work:order-segment-001-apply"] == "blocked" and statuses[ORDER_SEED_ID] == "blocked"
    assert statuses["socom:work:order-segment-001-compile"] == "blocked"
    assert audit_tracker(tracker, strict=True) == []
    code, audit = _run(capsys, "--root", str(root), "audit", "pipeline-reachability")
    assert code == 0 and {"stage": ORDER_STAGE, "seed_count": 0, "blocked": True, "decomposed": True} in audit["deferred"]

    # A changed stage 4 baseline makes every plan stale: validate says re-draft.
    changed = _load(root)
    next(row for row in changed["stages"] if row["name"] == "source-correlation")["baseline"]["baseline_sha256"] = "d" * 64
    (root / STATE).write_text(json.dumps(changed), encoding="utf-8")
    code, stale = _run(capsys, *base, "validate", "--plan", plan)
    assert code == 1 and any(text.startswith("stale stage 4 baseline") for text in stale["problems"]), stale
    code, stale = _run(capsys, *base, "validate", "--plan", link)
    assert code == 1 and any(text.startswith("stale stage 4 baseline") for text in stale["problems"]), stale


def test_the_producer_needs_an_accepted_stage_4_without_open_amendments(
    amendable: tuple[Path, dict, str], capsys
) -> None:
    root, _graph, _gap = amendable
    code, report = _amend(root, capsys, DATA)
    assert code == 0, report
    code, refused = _decompose(root, capsys)
    assert code == 2 and "waits for the open source-correlation amendments" in refused["error"]


def test_the_producer_refuses_an_unaccepted_stage_4_and_undecomposed_items(workspace: tuple[Path, dict], capsys) -> None:
    root, _graph = workspace
    code, refused = _decompose(root, capsys)
    assert code == 2 and "no accepted source-correlation owner plans" in refused["error"]
    tracker = _load(root)
    assert next(row for row in tracker["work_items"] if row["id"] == ORDER_SEED_ID)["kind"] == "stage-seed"
    code, refused = _run(capsys, "--root", str(root), "order", "plan", "draft", "--item", ORDER_SEED_ID)
    assert code == 2 and "is not a authored-function-order plan item" in refused["error"]
    assert UNSET is not None
