from __future__ import annotations

from pathlib import Path

import pytest
import copy

from tools._socom.constants import EXPECTED_GHIDRA_VERSION, ZERO_FILL_MEMORY_ID
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
    tmp_path: Path, root: Path, census: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools._socom import locking

    monkeypatch.setattr(locking, "LOCK_WAIT_SECONDS", 0.5)
    path = tmp_path / "tracker.json"
    atomic_write_json(path, initialize_tracker(root, census))
    with exclusive_state_lock(path):
        with pytest.raises(SocomError, match="state lock exists"):
            mutate(path, 1, lambda tracker: None)


def test_tracker_mutation_waits_for_a_briefly_held_lock(
    tmp_path: Path, root: Path, census: dict
) -> None:
    import threading
    import time

    path = tmp_path / "tracker.json"
    atomic_write_json(path, initialize_tracker(root, census))
    held = threading.Event()

    def hold() -> None:
        with exclusive_state_lock(path):
            held.set()
            time.sleep(0.6)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait()
    updated = mutate(path, 1, lambda tracker: None)
    holder.join()
    assert updated["revision"] == 2


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
        if row["kind"].startswith("debug-import-apply-") or row["kind"] == "ghidra-memory-map":
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
    assert migrated["schema_version"] == 6
    assert migrated["revision"] == 4
    assert [(row["from_schema"], row["to_schema"]) for row in migrated["migration_history"]] == [
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),
    ]
    plans = [row for row in migrated["work_items"] if "-plan-" in row["kind"]]
    applies = [row for row in migrated["work_items"] if "-apply-" in row["kind"]]
    assert len(plans) == len(applies) == 41
    assert all("ghidra-writer" not in row["resources"] for row in plans)
    assert all("ghidra-writer" in row["resources"] for row in applies)
    assert all(
        row["dependencies"][-1] == ZERO_FILL_MEMORY_ID
        for row in applies
        if row["kind"] == "debug-import-apply-batch"
    )
    assert audit_tracker(migrated) == []
    assert migrate_tracker(path, 4)["revision"] == 4


def test_tracker_v3_migration_adds_zero_fill_memory_item(
    tmp_path: Path, root: Path, census: dict
) -> None:
    tracker = initialize_tracker(root, census)
    tracker["work_items"] = [
        row for row in tracker["work_items"] if row["kind"] != "ghidra-memory-map"
    ]
    receipt = {"receipt_sha256": "a" * 64, "scope": {"functions": [], "types": [], "globals": []}, "saved": True}
    for row in tracker["work_items"]:
        if row["kind"] == "debug-import-apply-batch":
            row["dependencies"] = [row["dependencies"][0]]
        if row["id"] in ("socom:work:debug-type-foundation", "socom:work:debug-type-foundation-apply"):
            row["status"] = "accepted"
        if row["id"] == "socom:work:debug-type-foundation-apply":
            row["ghidra_receipt"] = receipt
    first_plan = next(row for row in tracker["work_items"] if row["kind"] == "debug-import-plan-batch")
    first_plan["status"] = "accepted"
    first_apply = next(row for row in tracker["work_items"] if row["id"] == f"{first_plan['id']}-apply")
    first_apply["status"] = "ready"
    tracker["schema_version"] = 3
    tracker["revision"] = 7
    path = tmp_path / "tracker.json"
    atomic_write_json(path, tracker)
    migrated = migrate_tracker(path, 7)
    assert migrated["schema_version"] == 6
    assert [(row["from_schema"], row["to_schema"]) for row in migrated["migration_history"]] == [(3, 4), (4, 5), (5, 6)]
    items = {row["id"]: row for row in migrated["work_items"]}
    memory = items[ZERO_FILL_MEMORY_ID]
    assert memory["status"] == "ready"
    assert memory["resources"] == ["ghidra:soCOM/socom.elf", "ghidra-writer"]
    order = [row["id"] for row in migrated["work_items"]]
    assert order.index(ZERO_FILL_MEMORY_ID) == order.index("socom:work:debug-type-foundation-apply") + 1
    # A batch apply that was ready waits again for the zero-fill image.
    assert items[first_apply["id"]]["status"] == "blocked"
    assert items[first_apply["id"]]["dependencies"] == [first_plan["id"], ZERO_FILL_MEMORY_ID]
    assert audit_tracker(migrated) == []


def test_tracker_v4_migration_adds_the_thunk_signature_repair(
    tmp_path: Path, root: Path, census: dict
) -> None:
    from tools._socom.repairs import BATCH_001_APPLY_ID, THUNK_REPAIR_ID

    tracker = initialize_tracker(root, census)
    assert not any(row["id"] == THUNK_REPAIR_ID for row in tracker["work_items"])
    tracker["schema_version"] = 4
    tracker["revision"] = 9
    path = tmp_path / "tracker.json"
    atomic_write_json(path, tracker)
    # Without an accepted batch 001 apply there is nothing to repair.
    untouched = migrate_tracker(path, 9)
    assert untouched["schema_version"] == 6
    assert not any(row["id"] == THUNK_REPAIR_ID for row in untouched["work_items"])
    receipt = {"receipt_sha256": "a" * 64, "scope": {"functions": [], "types": [], "globals": []}, "saved": True}
    batch_plan = BATCH_001_APPLY_ID.removesuffix("-apply")
    for row in tracker["work_items"]:
        if row["id"] in (
            "socom:work:debug-type-foundation",
            "socom:work:debug-type-foundation-apply",
            ZERO_FILL_MEMORY_ID,
            batch_plan,
            BATCH_001_APPLY_ID,
        ):
            row["status"] = "accepted"
            if "ghidra-writer" in row["resources"]:
                row["ghidra_receipt"] = receipt
    atomic_write_json(path, tracker)
    migrated = migrate_tracker(path, 9)
    assert migrated["schema_version"] == 6
    assert [(row["from_schema"], row["to_schema"]) for row in migrated["migration_history"]] == [(4, 5), (5, 6)]
    order = [row["id"] for row in migrated["work_items"]]
    assert order.index(THUNK_REPAIR_ID) == order.index(BATCH_001_APPLY_ID) + 1
    repair = next(row for row in migrated["work_items"] if row["id"] == THUNK_REPAIR_ID)
    # Its only dependency, batch 001's apply, is accepted.
    assert repair["kind"] == "ghidra-repair" and repair["status"] == "ready"
    assert repair["dependencies"] == [BATCH_001_APPLY_ID]
    assert repair["resources"] == ["ghidra:soCOM/socom.elf", "ghidra-writer"]
    assert audit_tracker(migrated) == []
    claim_work(migrated, THUNK_REPAIR_ID, "writer", 30)
    packet = work_packet(migrated, THUNK_REPAIR_ID, "writer")
    assert any("ghidra repair-signatures" in line for line in packet["validation"])
    assert packet["handoff"].endswith("handoff-live-ghidra")


def test_add_repair_waits_for_every_corrected_apply(root: Path, census: dict) -> None:
    from tools._socom.repairs import COPY_NAMES_REPAIR_ID, REPAIRS
    from tools._socom.tracker import add_repair_item

    tracker = initialize_tracker(root, census)
    with pytest.raises(SocomError, match="not accepted"):
        add_repair_item(tracker, COPY_NAMES_REPAIR_ID)
    dependencies = REPAIRS[COPY_NAMES_REPAIR_ID]["dependencies"]
    for row in tracker["work_items"]:
        if row["id"] in dependencies:
            row["status"] = "accepted"
    add_repair_item(tracker, COPY_NAMES_REPAIR_ID)
    order = [row["id"] for row in tracker["work_items"]]
    assert order.index(COPY_NAMES_REPAIR_ID) == max(order.index(dep) for dep in dependencies) + 1
    with pytest.raises(SocomError, match="already in the tracker"):
        add_repair_item(tracker, COPY_NAMES_REPAIR_ID)
    repair = next(row for row in tracker["work_items"] if row["id"] == COPY_NAMES_REPAIR_ID)
    repair["status"] = "ready"
    claim_work(tracker, COPY_NAMES_REPAIR_ID, "writer", 30)
    packet = work_packet(tracker, COPY_NAMES_REPAIR_ID, "writer")
    assert any("ghidra repair-labels" in line for line in packet["validation"])


def test_memory_map_item_has_a_ghidra_writer_packet(root: Path, census: dict) -> None:
    tracker = initialize_tracker(root, census)
    memory = next(row for row in tracker["work_items"] if row["id"] == ZERO_FILL_MEMORY_ID)
    memory["status"] = "ready"
    claim_work(tracker, ZERO_FILL_MEMORY_ID, "writer", 30)
    packet = work_packet(tracker, ZERO_FILL_MEMORY_ID, "writer")
    assert packet["role"] == "socom-ghidra-reconstructor"
    assert any("ghidra map-zero-fill" in line for line in packet["validation"])
    assert packet["handoff"].endswith("handoff-live-ghidra")


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


def test_next_work_orders_batches_numerically() -> None:
    from tools._socom.tracker import next_work

    def batch(number: int) -> dict:
        return {
            "id": f"socom:debug-batch:{number:020x}",
            "stage": "debug-metadata-import",
            "status": "ready",
            "lease": None,
            "batch": {"batch_number": number},
        }

    tracker = {"work_items": [batch(20), batch(2), batch(10), batch(3), batch(1)]}
    assert [item["batch"]["batch_number"] for item in next_work(tracker)] == [1, 2, 3, 10, 20]


def test_stage_baseline_records_the_union_of_accepted_writer_scopes(stage2_tracker: dict) -> None:
    from tools._socom.tracker import record_stage_baseline, stage_live_scope

    tracker = stage2_tracker
    stage = "debug-metadata-import"
    writers = [row for row in tracker["work_items"] if row["stage"] == stage and "ghidra-writer" in row["resources"]]
    # Two items naming one function count it once.
    writers[1]["ghidra_receipt"]["scope"]["functions"] = list(writers[0]["ghidra_receipt"]["scope"]["functions"])
    scope = stage_live_scope(tracker, stage)
    assert len(scope["functions"]) == len(writers) - 1
    receipt = _rebaseline_receipt()
    with pytest.raises(SocomError, match="handed off work"):
        record_stage_baseline(tracker, stage, "worker", ["r.md"], receipt_sha256="9" * 64, receipt=receipt)
    with pytest.raises(SocomError, match="requires evidence"):
        record_stage_baseline(tracker, stage, "reviewer", [], receipt_sha256="9" * 64, receipt=receipt)
    with pytest.raises(SocomError, match="not accepted"):
        record_stage_baseline(
            tracker, "ghidra-reconstruction", "reviewer", ["r.md"], receipt_sha256="9" * 64, receipt=receipt
        )
    entry = record_stage_baseline(tracker, stage, "reviewer", ["r.md"], receipt_sha256="9" * 64, receipt=receipt)
    assert entry["scope_counts"] == {"functions": len(writers) - 1, "types": 0, "globals": 0}
    assert entry["live_item_count"] == len(writers)
    assert tracker["stages"][1]["accepted_evidence"] == ["ghidra-receipt-sha256:" + "9" * 64]
    assert audit_tracker(tracker, strict=True) == []
    with pytest.raises(SocomError, match="already records a baseline"):
        record_stage_baseline(tracker, stage, "reviewer", ["r.md"], receipt_sha256="9" * 64, receipt=receipt)

    tampered = copy.deepcopy(tracker)
    tampered["stages"][1]["baseline"]["scope_sha256"] = "0" * 64
    assert any("baseline scope differs" in e for e in audit_tracker(tampered, strict=True))
    tampered = copy.deepcopy(tracker)
    tampered["stages"][1]["accepted_evidence"] = []
    assert any("omits its baseline receipt" in e for e in audit_tracker(tampered, strict=True))


def test_workspace_stage2_baseline_matches_its_writer_scopes(root: Path) -> None:
    from tools._socom.tracker import load_tracker, scope_sha256, stage_live_scope

    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    baseline = tracker["stages"][1]["baseline"]
    scope = stage_live_scope(tracker, "debug-metadata-import")
    assert baseline["scope_counts"] == {"functions": 881, "types": 840, "globals": 3103}
    assert baseline["scope_sha256"] == scope_sha256(scope)
    assert baseline["receipt_sha256"] == "19ea3466aa8e7bc308605b4b23160f95a3c87ed859493d0eab2e63320527f1ab"


def test_stage_baseline_refuses_an_active_writer(root: Path, census: dict) -> None:
    from tools._socom.tracker import record_stage_baseline

    tracker = initialize_tracker(root, census)
    for row in tracker["work_items"]:
        if row["stage"] == "debug-metadata-import":
            row["status"] = "accepted"
    seed = next(
        row for row in tracker["work_items"] if row["id"] == "socom:work:ghidra-reconstruction-seed"
    )
    seed["kind"] = "test-writer"
    seed["resources"] = ["ghidra:soCOM/socom.elf", "ghidra-writer"]
    seed["status"] = "awaiting_acceptance"
    with pytest.raises(SocomError, match="no active Ghidra writer"):
        record_stage_baseline(
            tracker, "debug-metadata-import", "reviewer", ["r.md"],
            receipt_sha256="9" * 64, receipt=_rebaseline_receipt(),
        )


def test_tracker_v5_migration_moves_symbols_and_relocations_to_the_census(
    tmp_path: Path, root: Path, census: dict
) -> None:
    tracker = initialize_tracker(root, census)
    assert "symbols" not in tracker and "relocations" not in tracker
    legacy = dict(tracker, schema_version=5, revision=11)
    legacy["symbols"] = [dict(row) for row in census["symbols"][:3]]
    legacy["relocations"] = [dict(row) for row in census["relocations"][:3]]
    path = tmp_path / "tracker.json"
    atomic_write_json(path, legacy)
    migrated = migrate_tracker(path, 11)
    assert migrated["schema_version"] == 6
    assert "symbols" not in migrated and "relocations" not in migrated
    assert [(row["from_schema"], row["to_schema"]) for row in migrated["migration_history"]] == [(5, 6)]
    assert audit_tracker(migrated) == []
    # A schema 6 tracker may not carry them again.
    assert any("reference census" in error for error in audit_tracker(dict(migrated, symbols=[])))


def test_reopen_returns_an_unapplied_accepted_plan() -> None:
    from tools._socom.tracker import reopen_work

    plan = {"id": "socom:recon-group:abc", "kind": "recon-plan-group", "status": "accepted",
            "handoff": {"owner": "planner"}, "accepted": {"by": "reviewer", "at": "2026-10-20T00:00:00Z"},
            "evidence": ["plan sha"]}
    apply = {"id": "socom:recon-group:abc-apply", "kind": "recon-apply-group", "status": "ready"}
    tracker = {"work_items": [plan, apply]}
    with pytest.raises(SocomError, match="handoff owner"):
        reopen_work(tracker, plan["id"], "planner", "reason", [])
    reopen_work(tracker, plan["id"], "controller", "void rows v6 cannot confirm", ["audit"])
    assert plan["status"] == "ready" and "accepted" not in plan and plan["handoff"] is None
    assert apply["status"] == "blocked"
    history = plan["review_history"][-1]
    assert history["reopened_by"] == "controller" and history["accepted"]["by"] == "reviewer"
    # An apply that started or finished is corrected by a repair instead.
    plan["status"], apply["status"] = "accepted", "accepted"
    with pytest.raises(SocomError, match="governed repair"):
        reopen_work(tracker, plan["id"], "controller", "reason", [])
