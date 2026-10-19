from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tools._socom.constants import REFERENCE_SHA256
from tools._socom.recon import (
    RECON_PLAN_KIND,
    _sccs,
    build_recon_program,
    function_graph,
    group_sha256,
    recon_groups,
    validate_recon_plan,
)
from tools._socom.tracker import (
    RECON_SEED_ID,
    audit_tracker,
    claim_work,
    decompose_reconstruction,
    next_work,
    record_stage_baseline,
    refresh_ready_and_stages,
    work_packet,
)
from tools._socom.util import SocomError, atomic_write_json


@pytest.fixture(scope="module")
def groups(root: Path) -> dict:
    return recon_groups(root)


@pytest.fixture(scope="module")
def graph(root: Path) -> dict:
    return function_graph(root)


def _with_baseline(tracker: dict) -> dict:
    record_stage_baseline(
        tracker,
        "debug-metadata-import",
        "reviewer",
        ["close-out.md"],
        receipt_sha256="9" * 64,
        receipt={"counts": {}, "indexes": {}},
    )
    return tracker


@pytest.fixture()
def decomposed(stage2_tracker: dict, groups: dict) -> dict:
    tracker = _with_baseline(stage2_tracker)
    decompose_reconstruction(tracker, groups)
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    return tracker


def test_sccs_keep_cycles_together_and_order_callees_first() -> None:
    edges = {1: [2], 2: [3], 3: [2, 4], 4: []}
    components = _sccs([1, 2, 3, 4], edges)
    assert components == [[4], [2, 3], [1]]


def test_function_graph_covers_every_sized_function(graph: dict) -> None:
    assert len(graph["functions"]) == 9703
    starts = {row["start"] for row in graph["functions"]}
    assert all(target in starts for targets in graph["edges"].values() for target in targets)
    assert all(source not in targets for source, targets in graph["edges"].items())
    # Self-recursion is not an anomaly; the two remaining anomalies reach the
    # unsized crt0 code at 0x1401d0.
    assert {row["target"] for row in graph["anomalies"]} == {"0x1401d0"}


def test_groups_are_deterministic_bounded_and_callee_first(root: Path, groups: dict, graph: dict) -> None:
    assert recon_groups(root)["graph_sha256"] == groups["graph_sha256"]
    members = [address for group in groups["groups"] for address in group["functions"]]
    assert len(members) == len(set(members)) == groups["function_count"]
    assert all(len(group["functions"]) <= groups["group_size"] for group in groups["groups"])
    position = {group["id"]: index for index, group in enumerate(groups["groups"])}
    group_of = {address: group["id"] for group in groups["groups"] for address in group["functions"]}
    for group in groups["groups"]:
        assert all(position[callee] < position[group["id"]] for callee in group["callee_groups"])
    for component in graph["components"]:
        assert len({group_of[f"0x{member:x}"] for member in component}) == 1
    assert [group["group_number"] for group in groups["groups"]] == list(range(1, len(groups["groups"]) + 1))


def test_decomposition_replaces_the_seed_with_pairs_and_a_gate(decomposed: dict, groups: dict) -> None:
    tracker = decomposed
    assert audit_tracker(tracker, strict=True) == []
    plans = [row for row in tracker["work_items"] if row["kind"] == "recon-plan-group"]
    applies = [row for row in tracker["work_items"] if row["kind"] == "recon-apply-group"]
    assert len(plans) == len(applies) == len(groups["groups"])
    gate = next(row for row in tracker["work_items"] if row["id"] == RECON_SEED_ID)
    assert gate["kind"] == "stage-gate" and gate["status"] == "blocked"
    assert set(gate["dependencies"]) == {row["id"] for row in applies}
    ready = next_work(copy.deepcopy(tracker))
    assert {row["id"] for row in ready} == {group["id"] for group in groups["groups"] if not group["callee_groups"]}
    stage = next(row for row in tracker["stages"] if row["name"] == "ghidra-reconstruction")
    assert stage["status"] == "active"
    assert stage["decomposition"]["graph_sha256"] == groups["graph_sha256"]
    with pytest.raises(SocomError, match="already decomposed"):
        decompose_reconstruction(tracker, groups)


def test_decomposition_requires_the_stage2_baseline(stage2_tracker: dict, groups: dict) -> None:
    tracker = stage2_tracker
    with pytest.raises(SocomError, match="recorded baseline"):
        decompose_reconstruction(tracker, groups)


def test_audit_rejects_broken_reconstruction_structure(decomposed: dict) -> None:
    tracker = decomposed
    broken = copy.deepcopy(tracker)
    gate = next(row for row in broken["work_items"] if row["id"] == RECON_SEED_ID)
    gate["dependencies"] = gate["dependencies"][1:]
    assert any("gate does not depend" in error for error in audit_tracker(broken))
    broken = copy.deepcopy(tracker)
    broken["work_items"] = [row for row in broken["work_items"] if row["kind"] != "recon-apply-group" or row["batch"]["group_number"] != 5]
    assert any("pairing is incomplete" in error for error in audit_tracker(broken))
    broken = copy.deepcopy(tracker)
    plan = next(row for row in broken["work_items"] if row["kind"] == "recon-plan-group")
    plan["resources"] = ["ghidra-writer"]
    assert any("not file-only" in error for error in audit_tracker(broken))
    broken = copy.deepcopy(tracker)
    plan = next(row for row in broken["work_items"] if row["kind"] == "recon-plan-group")
    plan["batch"]["graph_sha256"] = "0" * 64
    assert any("different function graph" in error for error in audit_tracker(broken))


def test_reconstruction_packets_route_plan_apply_and_gate(decomposed: dict) -> None:
    tracker = decomposed
    plan_id = next_work(copy.deepcopy(tracker))[0]["id"]
    claim_work(tracker, plan_id, "mapper", 30)
    packet = work_packet(tracker, plan_id, "mapper")
    assert packet["role"] == "socom-recon-planner"
    assert packet["ghidra_scope"]["read_only"] is True
    assert any("recon evidence" in line for line in packet["validation"])
    apply_id = f"{plan_id}-apply"
    apply = next(row for row in tracker["work_items"] if row["id"] == apply_id)
    apply["status"] = "ready"
    claim_work(tracker, apply_id, "writer", 30)
    packet = work_packet(tracker, apply_id, "writer")
    assert packet["role"] == "socom-ghidra-reconstructor"
    assert any("ghidra apply-recon" in line for line in packet["validation"])
    assert packet["handoff"].endswith("handoff-live-ghidra")
    gate = next(row for row in tracker["work_items"] if row["id"] == RECON_SEED_ID)
    gate["status"] = "ready"
    claim_work(tracker, RECON_SEED_ID, "verifier", 30)
    packet = work_packet(tracker, RECON_SEED_ID, "verifier")
    assert packet["role"] == "socom-verifier"
    assert any("progress stage-scope" in line for line in packet["validation"])


def _plan(tracker: dict, group_number: int, root: Path) -> dict:
    item = next(
        row
        for row in tracker["work_items"]
        if row["kind"] == "recon-plan-group" and row["batch"]["group_number"] == group_number
    )
    return {
        "kind": RECON_PLAN_KIND,
        "schema_version": 1,
        "work_item_id": item["id"],
        "group_sha256": group_sha256(item["batch"]),
        "target": {"source_sha256": REFERENCE_SHA256},
        "functions": [
            {"address": address, "current_name": f"FUN_{address[2:]}", "prototype": None, "unresolved": ["test"]}
            for address in item["batch"]["functions"]
        ],
        "globals": [],
    }


def test_plan_validation_and_program_translation(tmp_path: Path, root: Path, decomposed: dict) -> None:
    tracker = decomposed
    plan = _plan(tracker, 1, root)
    assert validate_recon_plan(root, tracker, plan) == []

    # 0x142250 (__destroy_arr) reads a0-a3 at entry.
    entry = next(row for row in plan["functions"] if row["address"] == "0x142250")
    entry.update(
        {
            "unresolved": [],
            "rename": {"name": "__destroy_arr_renamed", "evidence": ["test"]},
            "prototype": {
                "return_type": "void",
                "parameters": [{"name": "block", "type": "void *"}, {"name": "dtor", "type": "void *"}],
                "evidence": ["test"],
            },
        }
    )
    problems = validate_recon_plan(root, tracker, plan)
    assert problems == [
        "function 0x142250 reads argument registers ['a2', 'a3'] that the prototype does not declare"
    ]
    entry["prototype"]["parameters"] += [
        {"name": "size", "type": "uint"},
        {"name": "count", "type": "uint"},
    ]
    assert validate_recon_plan(root, tracker, plan) == []
    path = tmp_path / "plan.json"
    atomic_write_json(path, plan)
    program = build_recon_program(root, tracker, path)
    row = next(row for row in program["functions"] if row["address"] == "0x142250")
    assert row["rename"] is True and row["readable_name"] == "__destroy_arr_renamed"
    assert row["prototype"]["calling_convention"] == "__stdcall"
    assert [param["name"] for param in row["prototype"]["parameters"]] == ["block", "dtor", "size", "count"]
    assert program["receipt_scope"]["functions"] == sorted(plan_row["address"] for plan_row in plan["functions"])
    assert program["summary"]["prototype_count"] == 1
    assert build_recon_program(root, tracker, path) == program


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda plan: plan["functions"].pop(), "missing from the plan"),
        (lambda plan: plan["functions"].append(dict(plan["functions"][0])), "appears twice"),
        (lambda plan: plan.update(group_sha256="0" * 64), "group_sha256 differs"),
        (lambda plan: plan["functions"][0].update(unresolved=[]), "needs a prototype or the reasons"),
        (
            lambda plan: plan["functions"][0].update(
                unresolved=[],
                prototype={"return_type": "pair<int, int>", "parameters": [], "evidence": ["x"]},
            ),
            "cannot spell",
        ),
        (
            lambda plan: plan["functions"][0].update(
                unresolved=[], prototype={"return_type": "void", "parameters": [], "evidence": []}
            ),
            "prototype needs evidence",
        ),
        (
            lambda plan: plan["functions"][0].update(
                unresolved=[],
                prototype={
                    "return_type": "void",
                    "parameters": [{"name": "a b", "type": "int"}, {"name": "a b", "type": "int"}],
                    "evidence": ["x"],
                },
            ),
            "not an identifier",
        ),
        (
            lambda plan: plan["globals"].append(
                {"address": "0x4f0000", "current_name": "g", "type": "uint16", "evidence": ["x"]}
            ),
            "global 0x4f0000",
        ),
    ],
)
def test_plan_validation_refuses_defects(root: Path, decomposed: dict, change, message: str) -> None:
    tracker = decomposed
    plan = _plan(tracker, 1, root)
    change(plan)
    assert any(message in problem for problem in validate_recon_plan(root, tracker, plan))


def test_completed_partial_loads_are_writes_not_argument_reads(root: Path) -> None:
    from tools._socom.batch_apply import _entry_argument_reads
    from tools._socom.elf import Elf32File

    elf = Elf32File(root / "support" / "socom.elf")
    # sceDmaGetEnv loads a1/a2 with ldl/ldr pairs before using them.
    assert _entry_argument_reads(elf, 0x150018, 56) == ({4, 5, 6}, set())
    assert _entry_argument_reads(elf, 0x150018, 56, pair_partial_loads=True) == ({4}, set())


def test_c_spellings_of_builtins_are_refused(root: Path, decomposed: dict) -> None:
    plan = _plan(decomposed, 1, root)
    plan["functions"][0].update(
        unresolved=[], prototype={"return_type": "unsigned int", "parameters": [], "evidence": ["x"]}
    )
    assert any("write the Ghidra builtin uint" in problem for problem in validate_recon_plan(root, decomposed, plan))


def test_dead_entry_reads_need_a_real_read_and_reach_the_notes(tmp_path: Path, root: Path, decomposed: dict) -> None:
    item = next(
        row
        for row in decomposed["work_items"]
        if row["kind"] == "recon-plan-group" and "0x16bad8" in row["batch"]["functions"]
    )
    plan = _plan(decomposed, item["batch"]["group_number"], root)
    entry = next(row for row in plan["functions"] if row["address"] == "0x16bad8")
    prototype = {
        "return_type": "longlong",
        "parameters": [{"name": "a", "type": "longlong"}, {"name": "b", "type": "longlong"}],
        "evidence": ["libgcc __muldi3"],
    }
    entry.update(unresolved=[], prototype=prototype)
    assert validate_recon_plan(root, decomposed, plan) == [
        "function 0x16bad8 reads argument registers ['t1'] that the prototype does not declare"
    ]
    prototype["dead_entry_reads"] = [{"register": "t2", "site": "0x16bb14", "evidence": ["x"]}]
    problems = validate_recon_plan(root, decomposed, plan)
    assert any("'t2' is not an argument register the entry block reads" in problem for problem in problems)
    prototype["dead_entry_reads"] = [{"register": "t1", "site": "0x16bb14", "evidence": ["cleared at 0x16bb28"]}]
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "plan.json"
    atomic_write_json(path, plan)
    row = next(row for row in build_recon_program(root, decomposed, path)["functions"] if row["address"] == "0x16bad8")
    assert row["notes"] == ["entry read of t1 at 0x16bb14 is dead: cleared at 0x16bb28"]
