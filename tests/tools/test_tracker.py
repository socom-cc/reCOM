from __future__ import annotations

from pathlib import Path

import pytest
import copy

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
