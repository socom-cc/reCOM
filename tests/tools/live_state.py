"""The live tracker without the governed stage 4/5 work in flight: the state the real-data tests assume.

Other workers mutate the live tracker while the suite runs: stage 4
amendments open (``progress amend-source-plan``), stage 5 items are held by
reopenings (``progress reopen-order-skeleton``), planners hand off, reviewers
accept, a rebase (``progress rebase-function-order``) sends plans back.  The
tests that read the live tracker for stage 4/5 route state assume the settled
state before such a wave.  ``settled`` rebuilds it from the tracker's own
records (review-history entries, amendment, reopening and baseline rows), never
from a hard-coded revision, whatever status the wave's items have reached.
"""

from __future__ import annotations

import copy
from typing import Any

from tools._socom.order_plan import ORDER_SKELETON_KINDS
from tools._socom.order_reopen import reopenings
from tools._socom.order_target import ORDER_STAGE
from tools._socom.source_amend import amendments, baseline_chain
from tools._socom.source_apply import APPLY_EVIDENCE_PREFIXES, _record_lines
from tools._socom.source_gate import BASELINE_CITATION
from tools._socom.source_plan import SEGMENT_APPLY_KIND, SOURCE_APPLY_KINDS, SOURCE_STAGE
from tools._socom.tracker import refresh_ready_and_stages


def _stage(tracker: dict[str, Any], name: str) -> dict[str, Any]:
    return next((row for row in tracker.get("stages") or [] if row.get("name") == name), {})


def _rewind(item: dict[str, Any], index: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop review-history entry ``index`` and every later one: (that entry, the later ones)."""

    history = item["review_history"]
    entry, later = history[index], history[index + 1:]
    del history[index:]
    if not history:
        item.pop("review_history")
    return entry, later


def _entry(item: dict[str, Any], key: str, value: Any) -> int | None:
    """The latest review-history entry whose ``key`` is ``value``."""

    history = item.get("review_history") or []
    return next((index for index in range(len(history) - 1, -1, -1) if history[index].get(key) == value), None)


def _accept_again(item: dict[str, Any], entry: dict[str, Any]) -> None:
    """The item as a send-back entry found it: accepted, with that handoff, acceptance and (when kept) evidence."""

    item.update(status="accepted", lease=None, handoff=entry.get("handoff"), accepted=entry.get("accepted"))
    if "handoff_evidence" in entry:
        item["evidence"] = list(entry["handoff_evidence"] or [])
    if item.get("kind") in ORDER_SKELETON_KINDS and isinstance(entry.get("order_skeleton"), dict):
        item["order_skeleton"] = entry["order_skeleton"]


# -- stage 5 ---------------------------------------------------------------------------------


def _undo_reopenings(tracker: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> None:
    rows = _stage(tracker, ORDER_STAGE).get("reopenings") or []
    # Open reopenings are the latest ones (a rebase absorbs every open one): newest first, so an item
    # held by several returns to the status it had before the first.
    while rows and rows[-1].get("status") == "open":
        row = rows.pop()
        for item_id in row.get("items") or []:
            item = by_id[item_id]
            index = _entry(item, "order_reopening", row["id"])
            if index is None:
                continue
            entry, _later = _rewind(item, index)
            if item_id in (row.get("sent_back") or []):
                _accept_again(item, entry)
            else:
                item.update(status=entry.get("status_before"), lease=None)
    if not rows:
        _stage(tracker, ORDER_STAGE).pop("reopenings", None)
    # An absorbed reopening or a rebase sent accepted items back to be re-planned: one not re-accepted yet is
    # accepted again from that send-back (the rebase itself, which moved the frozen base, stays).
    for item in tracker.get("work_items") or []:
        if item.get("stage") != ORDER_STAGE or item.get("status") == "accepted":
            continue
        history = item.get("review_history") or []
        index = next((index for index in range(len(history) - 1, -1, -1) if history[index].get("accepted")), None)
        if index is not None and (history[index].get("order_reopening") or history[index].get("order_rebase")):
            _accept_again(item, _rewind(item, index)[0])


# -- stage 4 ---------------------------------------------------------------------------------


def _reopen_unabsorbed_baselines(tracker: dict[str, Any]) -> None:
    """Accepted amendments stage 5 has not absorbed yet are open again: the stage 4 baseline stage 5 is on is current."""

    stage4 = _stage(tracker, SOURCE_STAGE)
    absorbed = (_stage(tracker, ORDER_STAGE).get("decomposition") or {}).get("stage4_baseline_sha256")
    shas = [row.get("baseline_sha256") for row in baseline_chain(tracker)]
    if absorbed not in shas:
        return
    rows = {row.get("id"): row for row in amendments(tracker)}
    for _ in range(len(shas) - 1 - shas.index(absorbed)):
        later = stage4["baseline"]
        earlier = stage4["baseline_history"].pop()
        for key in ("superseded_at", "superseded_by"):
            earlier.pop(key, None)
        stage4["baseline"] = earlier
        if not stage4["baseline_history"]:
            stage4.pop("baseline_history")
        cited = stage4.get("accepted_evidence") or []
        stage4["accepted_evidence"] = [text for text in cited if text != f"{BASELINE_CITATION}{later.get('baseline_sha256')}"]
        for name in later.get("amendments") or []:
            rows[name]["status"] = "open"
            rows[name].pop("accepted", None)


def _restore_apply(item: dict[str, Any], entry: dict[str, Any], later: list[dict[str, Any]]) -> None:
    """A stage 4 apply as the amendment found it: its acceptance, and the record a re-apply replaced (if one did)."""

    if entry.get("accepted"):
        item.update(status="accepted", accepted=entry["accepted"])
    else:  # already sent back (another open amendment): waiting for its re-apply
        item["status"] = "blocked"
        item.pop("accepted", None)
    item.update(lease=None, handoff=entry.get("handoff"))
    replaced = next((row for row in later if "replaced_at" in row and isinstance(row.get("source_apply"), dict)), None)
    if replaced is None:
        return  # not re-applied: the amendment left its record and evidence as they were
    record = item["source_apply"] = replaced["source_apply"]
    # A rejection keeps the handoff's evidence; the apply's own lines are its record's.
    snapshot = next((row["handoff_evidence"] for row in later if "handoff_evidence" in row), item.get("evidence") or [])
    kept = {text for text in snapshot if not str(text).startswith(APPLY_EVIDENCE_PREFIXES)}
    item["evidence"] = sorted(kept | set(_record_lines(record)))
    if item.get("kind") != SEGMENT_APPLY_KIND:
        return
    batch = item.setdefault("batch", {})
    reservation = record.get("reservation") or {}
    correction = batch.get("reservation_correction")
    if reservation.get("status") == "corrected":
        item["resources"] = list(reservation["directories"])
        batch["directories"] = list(reservation["directories"])
        if isinstance(correction, dict):
            correction["plan_sha256"] = record.get("plan_sha256")
    elif isinstance(correction, dict):  # the re-apply corrected it: the decomposed directories stood before
        item["resources"] = list(correction["from"])
        batch["directories"] = list(correction["from"])
        batch.pop("reservation_correction")


def _undo_amendments(tracker: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> None:
    rows = _stage(tracker, SOURCE_STAGE).get("amendments") or []
    # Every open amendment is accepted together, so the open ones are the latest: newest first.
    while rows and rows[-1].get("status") == "open":
        row = rows.pop()
        for item_id in [row.get("item"), *(row.get("applies") or [])]:
            item = by_id[str(item_id)]
            index = _entry(item, "amendment", row["id"])
            if index is None:
                continue
            entry, later = _rewind(item, index)
            if item.get("kind") in SOURCE_APPLY_KINDS:
                _restore_apply(item, entry, later)
            else:
                _accept_again(item, entry)
    if not rows:
        _stage(tracker, SOURCE_STAGE).pop("amendments", None)


def settled(tracker: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``tracker`` with the stage 4 amendments stage 5 has not absorbed and the stage 5 reopenings undone.

    * Open stage 5 reopenings are removed, newest first: an item a reopening
      sent back is accepted again from its review-history entry (handoff,
      evidence, acceptance, skeleton record), a held item gets its status
      before.  An item an absorbed reopening or a rebase sent back that is not
      re-accepted yet is accepted again from that entry.
    * Accepted amendments after the stage 4 baseline stage 5 is based on are
      open again (the earlier baseline current), then every open amendment is
      removed, newest first: its plan is accepted again from its amendment
      entry, each apply gets its acceptance and the record (and evidence
      lines) a re-apply replaced.
    """

    tracker = copy.deepcopy(tracker)
    by_id = {row["id"]: row for row in tracker.get("work_items") or [] if isinstance(row, dict) and "id" in row}
    _undo_reopenings(tracker, by_id)
    _reopen_unabsorbed_baselines(tracker)
    _undo_amendments(tracker, by_id)
    refresh_ready_and_stages(tracker)
    return tracker
