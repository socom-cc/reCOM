from __future__ import annotations

from pathlib import Path

import pytest
import copy

from tools._socom.constants import EXPECTED_GHIDRA_VERSION
from tools._socom.locking import exclusive_state_lock
from tools._socom.tracker import (
    accept_ghidra_work,
    accept_work,
    audit_tracker,
    claim_work,
    handoff_ghidra_work,
    handoff_work,
    initialize_tracker,
    migrate_tracker,
    mutate,
    next_work,
    rebaseline_ghidra_target,
    reject_work,
    work_packet,
)
from tools._socom.util import SocomError, atomic_write_json


def test_initial_tracker_is_valid_and_starts_with_debug_foundation(
    root: Path, census: dict
) -> None:
    tracker = initialize_tracker(root, census)
    assert audit_tracker(tracker) == []
    assert tracker["stages"][0]["status"] == "accepted"
    assert tracker["stages"][1]["status"] == "active"
    ready = next_work(tracker)
    assert ready[0]["id"] == "socom:work:debug-type-foundation"
    assert ready[0]["resources"] == [
        "build/import-plans",
    ]
    assert ready[0]["kind"] == "debug-import-plan-foundation"
    assert all(owner["status"] == "unverified" for owner in tracker["owners"])


def test_linked_bytes_wait_for_both_order_and_authored_byte(
    root: Path, census: dict
) -> None:
    tracker = initialize_tracker(root, census)
    linked = next(
        row for row in tracker["work_items"] if row["stage"] == "linked-byte-match"
    )
    assert "socom:work:full-function-order-seed" in linked["dependencies"]
    assert "socom:work:authored-byte-match-seed" in linked["dependencies"]


def test_cas_lease_handoff_and_acceptance(
    tmp_path: Path, root: Path, census: dict
) -> None:
    path = tmp_path / "tracker.json"
    atomic_write_json(path, initialize_tracker(root, census))
    item = "socom:work:debug-type-foundation"

    claimed = mutate(
        path,
        1,
        lambda tracker: claim_work(tracker, item, "test-worker", 30),
    )
    assert claimed["revision"] == 2
    with pytest.raises(SocomError, match="revision conflict"):
        mutate(path, 1, lambda tracker: None)

    handed = mutate(
        path,
        2,
        lambda tracker: handoff_work(
            tracker,
            item,
            "test-worker",
            "type plan reviewed",
            ["plan.json"],
        ),
    )
    assert handed["revision"] == 3
    accepted = mutate(
        path,
        3,
        lambda tracker: accept_work(
            tracker,
            item,
            "parent",
            ["review.txt"],
        ),
    )
    assert accepted["revision"] == 4
    apply_id = "socom:work:debug-type-foundation-apply"
    assert next(row for row in accepted["work_items"] if row["id"] == apply_id)[
        "status"
    ] == "ready"
    applied = mutate(
        path,
        4,
        lambda tracker: claim_work(tracker, apply_id, "ghidra-worker", 30),
    )
    assert applied["revision"] == 5
    handed_live = mutate(
        path,
        5,
        lambda tracker: handoff_ghidra_work(
            tracker,
            apply_id,
            "ghidra-worker",
            "type plan applied",
            ["plan.json"],
            scope={"functions": [], "types": [], "globals": []},
            receipt_sha256="a" * 64,
            receipt_summary={"counts": {}, "indexes": {}},
        ),
    )
    completed = mutate(
        path,
        6,
        lambda tracker: accept_ghidra_work(
            tracker,
            apply_id,
            "parent",
            ["review.txt"],
            receipt_sha256="a" * 64,
        ),
    )
    assert all(
        row["status"] == "ready"
        for row in completed["work_items"]
        if row["kind"] == "debug-import-plan-batch"
    )
    assert handed_live["revision"] == 6
    assert completed["revision"] == 7
    assert audit_tracker(completed) == []


def test_exclusive_ghidra_writer(root: Path, census: dict) -> None:
    tracker = initialize_tracker(root, census)
    applies = [
        row
        for row in tracker["work_items"]
        if row["kind"].startswith("debug-import-apply-")
    ]
    first, second = applies[:2]
    first["status"] = "ready"
    second["status"] = "ready"
    claim_work(tracker, first["id"], "one", 30)
    with pytest.raises(SocomError, match="already claimed"):
        claim_work(tracker, second["id"], "two", 30)


def test_handoff_owner_cannot_self_accept(root: Path, census: dict) -> None:
    tracker = initialize_tracker(root, census)
    item = "socom:work:debug-type-foundation-apply"
    next(row for row in tracker["work_items"] if row["id"] == item)["status"] = "ready"
    claim_work(tracker, item, "same-worker", 30)
    handoff_ghidra_work(
        tracker,
        item,
        "same-worker",
        "review me",
        ["evidence.json"],
        scope={"functions": [], "types": [], "globals": []},
        receipt_sha256="b" * 64,
        receipt_summary={"counts": {}, "indexes": {}},
    )
    with pytest.raises(SocomError, match="self-accepted"):
        accept_ghidra_work(
            tracker,
            item,
            "same-worker",
            [],
            receipt_sha256="b" * 64,
        )


def test_generic_handoff_rejects_ghidra_writer(root: Path, census: dict) -> None:
    tracker = initialize_tracker(root, census)
    item = "socom:work:debug-type-foundation-apply"
    next(row for row in tracker["work_items"] if row["id"] == item)["status"] = "ready"
    claim_work(tracker, item, "writer", 30)
    with pytest.raises(SocomError, match="handoff-live-ghidra"):
        handoff_work(tracker, item, "writer", "unsafe handoff", [])


def test_tracker_mutation_fails_closed_while_locked(
    tmp_path: Path, root: Path, census: dict
) -> None:
    path = tmp_path / "tracker.json"
    atomic_write_json(path, initialize_tracker(root, census))
    with exclusive_state_lock(path):
        with pytest.raises(SocomError, match="state lock exists"):
            mutate(path, 1, lambda tracker: None)


def test_work_packets_enforce_active_owner_and_plan_apply_contract(
    root: Path, census: dict
) -> None:
    tracker = initialize_tracker(root, census)
    plan_id = "socom:work:debug-type-foundation"
    claim_work(tracker, plan_id, "planner", 30)
    plan_packet = work_packet(tracker, plan_id, "planner")
    assert plan_packet["kind"] == "socom-work-packet-v1"
    assert plan_packet["role"] == "socom-dwarf-importer"
    assert plan_packet["ghidra_scope"] is None
    assert plan_packet["allowed_paths"][0].startswith("build/import-plans/")
    with pytest.raises(SocomError, match="leased by planner"):
        work_packet(tracker, plan_id, "other")

    apply_id = "socom:work:debug-type-foundation-apply"
    apply = next(row for row in tracker["work_items"] if row["id"] == apply_id)
    apply["status"] = "ready"
    claim_work(tracker, apply_id, "writer", 30)
    apply_packet = work_packet(tracker, apply_id, "writer")
    assert apply_packet["role"] == "socom-ghidra-reconstructor"
    assert apply_packet["ghidra_scope"]["program"] == "socom.elf"
    assert apply_packet["handoff"].endswith("handoff-live-ghidra")


def _legacy_tracker(root: Path, census: dict) -> dict:
    tracker = initialize_tracker(root, census)
    legacy_items = []
    plan_ids = []
    for row in tracker["work_items"]:
        if row["kind"].startswith("debug-import-apply-"):
            continue
        item = copy.deepcopy(row)
        if item["kind"] == "debug-import-plan-foundation":
            item["kind"] = "debug-import-foundation"
            item["resources"] = ["ghidra:soCOM/socom.elf", "ghidra-writer"]
            plan_ids.append(item["id"])
        elif item["kind"] == "debug-import-plan-batch":
            item["kind"] = "debug-import-batch"
            item["dependencies"] = ["socom:work:debug-type-foundation"]
            item["resources"] = ["ghidra:soCOM/socom.elf", "ghidra-writer"]
            plan_ids.append(item["id"])
        elif item["id"] == "socom:work:ghidra-reconstruction-seed":
            item["dependencies"] = list(plan_ids)
        legacy_items.append(item)
    tracker["work_items"] = legacy_items
    tracker["schema_version"] = 2
    tracker["revision"] = 3
    tracker.pop("migration_history", None)
    tracker["blockers"] = [
        row
        for row in tracker["blockers"]
        if row["id"] != "socom:blocker:deferred-stage-producers"
    ]
    return tracker


def test_tracker_v2_migration_splits_plans_and_apply_items(
    tmp_path: Path, root: Path, census: dict
) -> None:
    path = tmp_path / "tracker.json"
    atomic_write_json(path, _legacy_tracker(root, census))
    migrated = migrate_tracker(path, 3)
    assert migrated["schema_version"] == 3
    assert migrated["revision"] == 4
    assert len(migrated["migration_history"]) == 1
    plans = [row for row in migrated["work_items"] if "-plan-" in row["kind"]]
    applies = [row for row in migrated["work_items"] if "-apply-" in row["kind"]]
    assert len(plans) == len(applies) == 41
    assert all("ghidra-writer" not in row["resources"] for row in plans)
    assert all("ghidra-writer" in row["resources"] for row in applies)
    assert audit_tracker(migrated) == []
    assert migrate_tracker(path, 4)["revision"] == 4


def test_tracker_migration_refuses_active_lease(
    tmp_path: Path, root: Path, census: dict
) -> None:
    path = tmp_path / "tracker.json"
    legacy = _legacy_tracker(root, census)
    claim_work(legacy, "socom:work:debug-type-foundation", "worker", 30)
    atomic_write_json(path, legacy)
    with pytest.raises(SocomError, match="requires no leases"):
        migrate_tracker(path, 3)


def test_stage_seed_cannot_be_claimed_or_accepted(root: Path, census: dict) -> None:
    tracker = initialize_tracker(root, census)
    seed = next(row for row in tracker["work_items"] if row["kind"] == "stage-seed")
    seed["status"] = "ready"
    with pytest.raises(SocomError, match="undecomposed stage seed"):
        claim_work(tracker, seed["id"], "worker", 30)


def _bootstrap_ghidra_tracker(root: Path, census: dict) -> dict:
    tracker = initialize_tracker(root, census)
    target = next(
        row
        for row in tracker["verification_targets"]
        if row["id"] == "socom:verification:ghidra-program"
    )
    target["ghidra_version"] = "0.0.0-previous"
    target["status"] = "bootstrap-r5900"
    target["baseline_receipt_sha256"] = "c" * 64
    target["current_receipt_sha256"] = "c" * 64
    target["receipt_history"] = [
        {
            "tracker_revision": 1,
            "work_item_id": None,
            "receipt_sha256": "c" * 64,
            "counts": {"function_count": 2, "memory_block_count": 26},
            "indexes": {
                "functions": {"count": 2, "sha256": "f" * 64},
                "types": {"count": 1, "sha256": "e" * 64},
                "data": {"count": 3, "sha256": "d" * 64},
            },
        }
    ]
    return tracker


def _rebaseline_receipt(*, functions: str = "f" * 64, data: str = "a" * 64) -> dict:
    return {
        "counts": {"function_count": 2, "memory_block_count": 27},
        "indexes": {
            "functions": {"count": 2, "sha256": functions},
            "types": {"count": 1, "sha256": "e" * 64},
            "data": {"count": 3, "sha256": data},
        },
    }


def test_ghidra_rebaseline_records_version_and_explicit_deltas(
    tmp_path: Path, root: Path, census: dict
) -> None:
    path = tmp_path / "tracker.json"
    atomic_write_json(path, _bootstrap_ghidra_tracker(root, census))
    updated = mutate(
        path,
        1,
        lambda tracker: rebaseline_ghidra_target(
            tracker,
            "reviewer",
            ["fresh-import.json"],
            ghidra_version=EXPECTED_GHIDRA_VERSION,
            receipt_sha256="9" * 64,
            receipt=_rebaseline_receipt(),
        ),
    )
    target = next(
        row
        for row in updated["verification_targets"]
        if row["id"] == "socom:verification:ghidra-program"
    )
    assert target["ghidra_version"] == EXPECTED_GHIDRA_VERSION
    assert target["status"] == "bootstrap-r5900"
    assert target["baseline_receipt_sha256"] == "9" * 64
    assert target["current_receipt_sha256"] == "9" * 64
    assert len(target["receipt_history"]) == 2
    entry = target["receipt_history"][-1]
    assert entry["tracker_revision"] == updated["revision"] == 2
    assert entry["kind"] == "ghidra-version-rebaseline"
    assert entry["previous_ghidra_version"] == "0.0.0-previous"
    assert entry["previous_receipt_sha256"] == "c" * 64
    assert entry["index_comparison"]["functions"]["sha256_equal"] is True
    assert entry["index_comparison"]["data"] == {
        "count_equal": True,
        "sha256_equal": False,
    }
    assert entry["count_deltas"] == {
        "memory_block_count": {"before": 26, "after": 27}
    }
    assert audit_tracker(updated) == []


def test_ghidra_rebaseline_refuses_changed_semantic_indexes(
    root: Path, census: dict
) -> None:
    tracker = _bootstrap_ghidra_tracker(root, census)
    with pytest.raises(SocomError, match="semantic index digests"):
        rebaseline_ghidra_target(
            tracker,
            "reviewer",
            ["fresh-import.json"],
            ghidra_version=EXPECTED_GHIDRA_VERSION,
            receipt_sha256="9" * 64,
            receipt=_rebaseline_receipt(functions="0" * 64),
        )


def test_ghidra_rebaseline_refuses_live_work_and_same_version(
    root: Path, census: dict
) -> None:
    arguments = {
        "ghidra_version": EXPECTED_GHIDRA_VERSION,
        "receipt_sha256": "9" * 64,
        "receipt": _rebaseline_receipt(),
    }
    tracker = _bootstrap_ghidra_tracker(root, census)
    apply_id = "socom:work:debug-type-foundation-apply"
    next(row for row in tracker["work_items"] if row["id"] == apply_id)[
        "status"
    ] = "ready"
    claim_work(tracker, apply_id, "writer", 30)
    with pytest.raises(SocomError, match="writer work"):
        rebaseline_ghidra_target(tracker, "reviewer", ["e.json"], **arguments)

    tracker = _bootstrap_ghidra_tracker(root, census)
    target = next(
        row
        for row in tracker["verification_targets"]
        if row["id"] == "socom:verification:ghidra-program"
    )
    target["status"] = "live-reconstruction"
    with pytest.raises(SocomError, match="limited to the bootstrap"):
        rebaseline_ghidra_target(tracker, "reviewer", ["e.json"], **arguments)

    target["status"] = "bootstrap-r5900"
    target["ghidra_version"] = EXPECTED_GHIDRA_VERSION
    with pytest.raises(SocomError, match="already pinned"):
        rebaseline_ghidra_target(tracker, "reviewer", ["e.json"], **arguments)


def test_reviewer_rejection_returns_handoff_for_rework(
    tmp_path: Path, root: Path, census: dict
) -> None:
    path = tmp_path / "tracker.json"
    atomic_write_json(path, initialize_tracker(root, census))
    item = "socom:work:debug-type-foundation"
    mutate(path, 1, lambda tracker: claim_work(tracker, item, "planner", 30))
    mutate(
        path,
        2,
        lambda tracker: handoff_work(tracker, item, "planner", "plan ready", ["plan.json"]),
    )
    with pytest.raises(SocomError, match="handoff owner"):
        mutate(path, 3, lambda tracker: reject_work(tracker, item, "planner", "no", []))
    with pytest.raises(SocomError, match="reason must not be empty"):
        mutate(path, 3, lambda tracker: reject_work(tracker, item, "reviewer", " ", []))
    rejected = mutate(
        path,
        3,
        lambda tracker: reject_work(
            tracker, item, "reviewer", "wrong template names", ["review.md"]
        ),
    )
    row = next(row for row in rejected["work_items"] if row["id"] == item)
    assert row["status"] == "ready"
    assert row["handoff"] is None
    assert row["evidence"] == []
    record = row["review_history"][-1]
    assert record["rejected_by"] == "reviewer"
    assert record["handoff"]["owner"] == "planner"
    assert record["handoff_evidence"] == ["plan.json"]
    assert record["evidence"] == ["review.md"]
    assert audit_tracker(rejected) == []
    reclaimed = mutate(path, 4, lambda tracker: claim_work(tracker, item, "planner", 30))
    assert next(row for row in reclaimed["work_items"] if row["id"] == item)[
        "status"
    ] == "in_progress"
    with pytest.raises(SocomError, match="not awaiting_acceptance"):
        reject_work(reclaimed, item, "reviewer", "again", [])
