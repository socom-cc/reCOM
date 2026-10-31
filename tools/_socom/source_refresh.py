"""Governed re-decomposition of stage 4 after the source graph changes.

``progress decompose-stage --stage source-correlation --refresh`` rebuilds
every stage 4 item's batch from a new ``source graph`` while no stage 4 plan
is accepted.  The fresh items come from the same producer as the first
decomposition (``tracker.decompose_source_correlation``, run on a scratch
copy); they are then merged with the live items:

* an item whose ID the new graph still gives keeps its ID, status, history
  and evidence, and takes the new batch, title, resources and dependencies;
* a handed-off plan item returns to ``ready``: its handoff and evidence move
  to a ``review_history`` note ("graph refreshed <old> -> <new>; replan",
  with whether its slice changed);
* scopes the new graph adds become new items; items whose scope is gone are
  removed and named in the refresh record;
* the decomposition record is replaced by the new one, which keeps the
  earlier refreshes and appends this one under ``refreshes``.

Nothing is refreshed while a stage 4 item is leased, an apply has started,
or any stage 4 plan is accepted: an accepted plan is evidence for its apply
and is only replaced through review.
"""

from __future__ import annotations

import copy
import datetime as dt
from typing import Any

from .source_plan import SOURCE_PLAN_KINDS, SOURCE_SEED_ID, SOURCE_STAGE, verify_graph
from .util import SocomError

RESET_SEED = {
    "kind": "stage-seed",
    "title": "Decompose and schedule source-correlation work",
    "status": "blocked",
    "resources": [],
    "selection": None,
    "batch": None,
    "lease": None,
    "handoff": None,
    "evidence": [],
}
FRESH_FIELDS = ("kind", "title", "dependencies", "resources", "selection", "batch")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def refresh_source_correlation(
    tracker: dict[str, Any], graph: dict[str, Any], reservations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Rebuild stage 4 from ``graph`` in place; returns the refresh record."""

    from .tracker import RECON_SEED_ID, decompose_source_correlation

    stage = next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)
    old = stage.get("decomposition")
    if not isinstance(old, dict):
        raise SocomError(f"{SOURCE_STAGE} is not decomposed: decompose it first")
    if problems := verify_graph(graph):
        raise SocomError("a refresh needs a valid source graph: " + "; ".join(problems))
    items = tracker["work_items"]
    stage_items = [row for row in items if row.get("stage") == SOURCE_STAGE]
    accepted = sorted(row["id"] for row in stage_items if row.get("kind") in SOURCE_PLAN_KINDS and row.get("status") == "accepted")
    if accepted:
        raise SocomError(f"stage 4 plans are accepted ({', '.join(accepted[:5])}): a refresh may not replace accepted plans")
    leased = sorted(row["id"] for row in stage_items if row.get("status") == "in_progress" or row.get("lease"))
    if leased:
        raise SocomError(f"stage 4 items are leased ({', '.join(leased[:5])}): release or hand them off before a refresh")
    started = sorted(
        row["id"] for row in stage_items
        if row.get("kind") not in SOURCE_PLAN_KINDS and row["id"] != SOURCE_SEED_ID and row.get("status") not in ("blocked", "ready")
    )
    if started:
        raise SocomError(f"stage 4 applies or gates have started ({', '.join(started[:5])}): no refresh")

    # The same producer as the first decomposition, on a scratch copy.
    scratch = copy.deepcopy(tracker)
    scratch["work_items"] = [row for row in scratch["work_items"] if row.get("stage") != SOURCE_STAGE or row["id"] == SOURCE_SEED_ID]
    seed = next(row for row in scratch["work_items"] if row["id"] == SOURCE_SEED_ID)
    seed.update(copy.deepcopy(RESET_SEED), dependencies=[RECON_SEED_ID])
    scratch_stage = next(row for row in scratch["stages"] if row["name"] == SOURCE_STAGE)
    scratch_stage.pop("decomposition", None)
    fresh = decompose_source_correlation(scratch, graph, reservations)
    fresh_items = [row for row in scratch["work_items"] if row.get("stage") == SOURCE_STAGE]

    live = {row["id"]: row for row in stage_items}
    new_sha = graph["graph_sha256"]
    note = f"graph refreshed {old.get('graph_sha256')} -> {new_sha}; replan"
    merged: list[dict[str, Any]] = []
    added, replan, changed, reserved = [], [], [], []
    for row in fresh_items:
        current = live.get(row["id"])
        if current is None:
            merged.append(row)
            added.append(row["id"])
            continue
        kept = copy.deepcopy(current)
        before = copy.deepcopy(current.get("batch"))
        for field in FRESH_FIELDS:
            kept[field] = copy.deepcopy(row.get(field))
        if row["id"] == SOURCE_SEED_ID:
            merged.append(kept)
            continue
        slice_changed = (before or {}).get("slice_sha256") != (row.get("batch") or {}).get("slice_sha256")
        if slice_changed:
            changed.append(row["id"])
        if sorted(current.get("resources") or []) != sorted(row.get("resources") or []):
            reserved.append(row["id"])
        if kept.get("kind") in SOURCE_PLAN_KINDS and kept.get("status") == "awaiting_acceptance" and before != kept["batch"]:
            kept.setdefault("review_history", []).append(
                {
                    "handoff": kept.get("handoff"),
                    "handoff_evidence": kept.get("evidence", []),
                    "refreshed_at": _now(),
                    "reason": note,
                    "slice": "changed" if slice_changed else "unchanged: re-cite the graph digest",
                    "previous_batch": {key: (before or {}).get(key) for key in ("graph_sha256", "slice_sha256", "artifact_count")},
                }
            )
            kept["status"] = "ready"
            kept["handoff"] = None
            kept["evidence"] = []
            replan.append(row["id"])
        merged.append(kept)
    fresh_ids = {row["id"] for row in fresh_items}
    removed = [{"id": row["id"], "status": row.get("status")} for row in stage_items if row["id"] not in fresh_ids]
    if not (added or removed or changed or reserved or replan) and old.get("graph_sha256") == new_sha and all(
        live[row["id"]].get("batch") == row.get("batch") for row in fresh_items if row["id"] in live
    ):
        raise SocomError("nothing to refresh: the graph and every batch are unchanged")

    rebuilt: list[dict[str, Any]] = []
    inserted = False
    for row in items:
        if row.get("stage") == SOURCE_STAGE:
            if not inserted:
                rebuilt.extend(merged)
                inserted = True
            continue
        rebuilt.append(row)
    tracker["work_items"] = rebuilt
    record = {
        "from_graph_sha256": old.get("graph_sha256"),
        "to_graph_sha256": new_sha,
        "tracker_revision": tracker["revision"] + 1,
        "added": added,
        "removed": removed,
        "replan": replan,
        "slice_changed": changed,
        "reservation_changed": reserved,
    }
    fresh["first_tracker_revision"] = old.get("first_tracker_revision", old.get("tracker_revision"))
    fresh["refreshes"] = [*copy.deepcopy(old.get("refreshes") or []), record]
    stage["decomposition"] = fresh
    return record
