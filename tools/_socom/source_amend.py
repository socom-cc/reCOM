"""Stage 4 (source-correlation) amendments: governed corrections of accepted plans after the gate.

Once the stage gate is accepted, ``progress reopen-source-plan`` refuses,
because the applies, data reconciles and gate have started. An amendment
corrects an accepted plan or data reconcile anyway, without a manual tracker
edit, and invalidates explicitly what depended on it:

* ``progress amend-source-plan`` opens an amendment on one accepted segment
  plan, provider plan or data reconcile. The item returns for revision with
  an amendment entry in its review history. Its paired apply (for a data
  reconcile: the segment applies whose records list it, plus any named with
  ``--reapply``) returns to ``blocked`` and needs a re-apply. The stage stays
  accepted, its row records the open amendment, and accepted stage 4 items
  that wait for the amended items keep their acceptance.
* The planner revises the plan, hands it off and an independent reviewer
  accepts it as usual. Each apply is re-applied with
  ``progress apply-source-plan``: the record is replaced (stamped with the
  amendment) and the previous record kept in the review history. It is then
  handed off and accepted as usual.
* ``progress accept-source-amendment`` is run by an accepter who did not open
  the amendment, did not hand off any amended item and is not a tool
  maintainer. Once every amended item is re-accepted, it re-runs every gate
  check, requires the live stage 3 receipt, and records the recomputed file
  baseline as the stage's current baseline. The previous baseline moves to
  ``baseline_history`` with the amendment reasons. A deferred row that the
  amendment resolved leaves the deferrals in force with a note; a new
  unresolved row needs a new deferral with a basis.

The deferrals in force are the gate's recorded deferrals with each amendment
baseline's resolutions and additions applied in order; the gate's own record
is never rewritten.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from .source_apply import _shown, cited_plan
from .source_gate import (
    BASELINE_CITATION,
    BASELINE_KIND,
    BASELINE_SCHEMA,
    MAINTAINER_MARKER,
    _digest,
    _refusal,
    deferral_body,
    normalize_deferrals,
    state_sha256,
)
from .capabilities import CAPABILITY_GATE_ACCEPTER
from .source_plan import (
    DATA_RECONCILE_KIND,
    SEGMENT_APPLY_KIND,
    SOURCE_APPLY_KINDS,
    SOURCE_PLAN_KINDS,
    SOURCE_SEED_ID,
    SOURCE_STAGE,
)
from .tracker import RECON_STAGE, _iso, _utc_now, open_source_amendments
from .util import SocomError

AMENDMENT_KIND = "socom-source-amendment"
AMENDMENT_SCHEMA = 1
AMENDMENT_PREFIX = "socom:source-amendment:"
OPEN_ROUTE = "progress amend-source-plan"
ACCEPT_ROUTE = "progress accept-source-amendment"
_AMENDMENT_ID = re.compile(r"^socom:source-amendment:(\d{3,})$")


def _by_id(tracker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in tracker.get("work_items", []) if isinstance(row, dict) and "id" in row}


def _stage(tracker: dict[str, Any]) -> dict[str, Any]:
    return next((row for row in tracker.get("stages", []) if row.get("name") == SOURCE_STAGE), {})


def amendments(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in _stage(tracker).get("amendments") or [] if isinstance(row, dict)]


def baseline_chain(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    """Every file baseline of the stage, oldest first: the gate's, then one per amendment acceptance."""

    stage = _stage(tracker)
    rows = [row for row in stage.get("baseline_history") or [] if isinstance(row, dict)]
    return rows + ([stage["baseline"]] if isinstance(stage.get("baseline"), dict) else [])


def _require_accepted_stage(tracker: dict[str, Any]) -> dict[str, Any]:
    gate = _by_id(tracker).get(SOURCE_SEED_ID) or {}
    stage = _stage(tracker)
    if gate.get("kind") != "stage-gate" or gate.get("status") != "accepted" or not isinstance(stage.get("baseline"), dict):
        raise SocomError(
            f"{SOURCE_STAGE} is not accepted with a file baseline: before its gate is accepted, an accepted plan "
            "returns with progress reopen-source-plan or progress work reject"
        )
    return stage


def _handoff_owners(item: dict[str, Any], before: str | None = None) -> set[str]:
    handoffs = [item.get("handoff")] + [
        entry.get("handoff") for entry in item.get("review_history") or [] if isinstance(entry, dict)
    ]
    return {
        str(row["owner"])
        for row in handoffs
        if isinstance(row, dict)
        and row.get("owner")
        and (before is None or str(row.get("submitted_at") or "") <= before)
    }


def amendment_workers(tracker: dict[str, Any], rows: list[dict[str, Any]], before: str | None = None) -> set[str]:
    """The openers of ``rows`` and everyone who handed off one of their items (review history included)."""

    by_id = _by_id(tracker)
    names = {str(row.get("opened_by")) for row in rows if row.get("opened_by")}
    for row in rows:
        for item_id in [row.get("item"), *(row.get("applies") or [])]:
            names |= _handoff_owners(by_id.get(str(item_id)) or {}, before)
    return names


def require_independent_accepter(name: str, workers: set[str]) -> str:
    name = str(name or "").strip()
    if not name:
        raise SocomError("the amendment accepter must not be empty")
    if MAINTAINER_MARKER in name.casefold() or name == CAPABILITY_GATE_ACCEPTER:
        raise SocomError(f"amendment accepter {name} is a tool maintainer: an amendment needs an independent accepter")
    if name in workers:
        raise SocomError(
            f"amendment accepter {name} opened the amendment or handed off one of its items: "
            "an amendment needs an independent accepter"
        )
    return name


# -- opening ------------------------------------------------------------------------------


def open_source_amendment(
    tracker: dict[str, Any],
    item_id: str,
    by: str,
    reason: str,
    evidence: list[str],
    reapply: list[str] | None = None,
) -> dict[str, Any]:
    """Open an amendment on an accepted stage 4 plan or data reconcile (``progress amend-source-plan``)."""

    by_id = _by_id(tracker)
    item = by_id.get(item_id)
    if item is None:
        raise SocomError(f"unknown work item: {item_id}")
    if item.get("stage") != SOURCE_STAGE or item.get("kind") not in SOURCE_PLAN_KINDS:
        raise SocomError(
            f"{item_id} is a {item.get('kind')} item, not a {SOURCE_STAGE} plan or data reconcile "
            f"({', '.join(SOURCE_PLAN_KINDS)})"
        )
    stage = _require_accepted_stage(tracker)
    if item.get("lease"):
        raise SocomError(f"{item_id} is leased by {item['lease'].get('owner')}")
    current = [row["id"] for row in open_source_amendments(tracker) if row.get("item") == item_id]
    if current:
        raise SocomError(
            f"{current[0]} is already open on {item_id}: accept it with {ACCEPT_ROUTE} before another amendment"
        )
    if item.get("status") != "accepted":
        raise SocomError(f"{item_id} is {item.get('status')}, not accepted")
    opener = by.strip()
    stated = reason.strip()
    lines = sorted({str(text).strip() for text in evidence if str(text).strip()})
    if not opener:
        raise SocomError("--by must not be empty")
    if not stated:
        raise SocomError("amendment reason must not be empty")
    if not lines:
        raise SocomError("an amendment needs at least one --evidence line")
    handoff = item.get("handoff") or {}
    if handoff.get("owner") == opener:
        raise SocomError(f"{item_id} cannot be amended by its handoff owner {opener}")
    extra = sorted(set(reapply or []))
    if item.get("kind") == DATA_RECONCILE_KIND:
        wrote = [
            row["id"]
            for row in tracker.get("work_items", [])
            if row.get("kind") == SEGMENT_APPLY_KIND
            and item_id in ((row.get("source_apply") or {}).get("reconciles") or [])
        ]
        for apply_id in extra:
            apply = by_id.get(apply_id) or {}
            if apply.get("kind") != SEGMENT_APPLY_KIND or apply.get("stage") != SOURCE_STAGE:
                raise SocomError(f"--reapply {apply_id} is not a {SOURCE_STAGE} segment apply")
        applies = sorted(set(wrote) | set(extra))
    else:
        if extra:
            raise SocomError("--reapply names further segment applies for a data reconcile amendment only")
        applies = [f"{item_id}-apply"]
        if applies[0] not in by_id:
            raise SocomError(f"{item_id} has no apply item {applies[0]}")
    for apply_id in applies:
        apply = by_id[apply_id]
        if apply.get("lease") or apply.get("status") in ("in_progress", "awaiting_acceptance"):
            raise SocomError(
                f"{apply_id} is {apply.get('status')}: finish or reject its current work before amending {item_id}"
            )
    number = len(stage.get("amendments") or []) + 1
    identifier = f"{AMENDMENT_PREFIX}{number:03d}"
    now = _iso(_utc_now())
    accepted_plan = next(
        (row for row in (stage["baseline"].get("state") or {}).get("plans") or [] if row.get("item") == item_id), {}
    )
    note = {"amendment": identifier, "amended_by": opener, "amended_at": now, "reason": stated, "evidence": lines}
    item.setdefault("review_history", []).append(
        {**note, "handoff": item.get("handoff"), "handoff_evidence": list(item.get("evidence") or []), "accepted": item.get("accepted")}
    )
    # Blocked until what it waits for is accepted; the refresh makes it ready.
    item["status"] = "blocked"
    item["handoff"] = None
    item.pop("accepted", None)
    for apply_id in applies:
        apply = by_id[apply_id]
        apply.setdefault("review_history", []).append(
            {**note, "handoff": apply.get("handoff"), "accepted": apply.get("accepted")}
        )
        apply["status"] = "blocked"
        apply["handoff"] = None
        apply.pop("accepted", None)
    record = {
        "kind": AMENDMENT_KIND,
        "schema_version": AMENDMENT_SCHEMA,
        "id": identifier,
        "status": "open",
        "item": item_id,
        "item_kind": item.get("kind"),
        "applies": applies,
        "opened_by": opener,
        "opened_at": now,
        "reason": stated,
        "evidence": lines,
        "plan_sha256": accepted_plan.get("plan_sha256"),
        "base_baseline_sha256": stage["baseline"].get("baseline_sha256"),
    }
    stage.setdefault("amendments", []).append(record)
    return {"amendment": identifier, "work_item_id": item_id, "applies": applies}


# -- the deferrals in force -------------------------------------------------------------------


def apply_deferral_delta(
    deferrals: list[dict[str, Any]], resolved: Any, added: Any
) -> tuple[list[dict[str, Any]], list[str]]:
    """Deferrals with ``resolved`` artifacts removed (a deferral left empty is dropped) and ``added`` ones appended."""

    problems: list[str] = []
    rows = {row["id"]: dict(row, artifacts=list(row.get("artifacts") or [])) for row in copy.deepcopy(deferrals)}
    if not isinstance(resolved, list) or not isinstance(added, list):
        return sorted(rows.values(), key=lambda row: row["id"]), ["an amendment baseline must list its resolved and added deferrals"]
    for entry in resolved:
        row = rows.get(str((entry or {}).get("deferral"))) if isinstance(entry, dict) else None
        artifact = entry.get("artifact") if isinstance(entry, dict) else None
        if row is None or artifact not in row["artifacts"] or not str(entry.get("note") or "").strip():
            problems.append(f"resolved deferral entry {entry} names no deferred artifact or has no note")
            continue
        row["artifacts"].remove(artifact)
    result = [row for row in rows.values() if row["artifacts"]]
    normalized, malformed = normalize_deferrals(deferral_body(added))
    if malformed or normalized != sorted(added, key=lambda row: str((row or {}).get("id"))):
        problems.append("added deferrals are malformed")
    clash = sorted(row["id"] for row in normalized if row["id"] in rows)
    if clash:
        problems.append(f"added deferrals reuse the IDs {clash}")
    return sorted(result + normalized, key=lambda row: row["id"]), problems


def effective_deferrals(tracker: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """The deferrals in force: the gate's recorded ones with every amendment baseline's delta applied."""

    gate = _by_id(tracker).get(SOURCE_SEED_ID) or {}
    current = copy.deepcopy((gate.get("source_gate") or {}).get("deferrals") or [])
    problems: list[str] = []
    for entry in baseline_chain(tracker)[1:]:
        current, step = apply_deferral_delta(current, entry.get("deferrals_resolved"), entry.get("deferrals_added"))
        problems.extend(f"baseline {entry.get('baseline_sha256')}: {problem}" for problem in step)
    return current, problems


def _unresolved_artifacts(root: Path, tracker: dict[str, Any]) -> set[str]:
    """Every unresolved artifact of the accepted plans (a plan that cannot be read is the review's problem)."""

    found: set[str] = set()
    for item in tracker.get("work_items", []):
        if item.get("stage") != SOURCE_STAGE or item.get("kind") not in SOURCE_PLAN_KINDS or item.get("status") != "accepted":
            continue
        try:
            plan, _relative, _sha = cited_plan(root, tracker, item["id"])
        except SocomError:
            continue
        found.update(str(row.get("artifact")) for row in plan.get("unresolved") or [] if isinstance(row, dict))
    return found


def deferral_delta(
    root: Path, tracker: dict[str, Any], names: list[str], added: list[dict[str, Any]]
) -> dict[str, Any]:
    """The deferrals an amendment acceptance records: rows no longer unresolved leave, ``added`` ones join."""

    current, problems = effective_deferrals(tracker)
    unresolved = _unresolved_artifacts(root, tracker)
    note = f"resolved by {', '.join(sorted(set(names)))}: no accepted plan leaves it unresolved"
    resolved = [
        {"artifact": artifact, "deferral": row["id"], "note": note}
        for row in current
        for artifact in row["artifacts"]
        if artifact not in unresolved
    ]
    deferrals, step = apply_deferral_delta(current, resolved, added)
    return {
        "deferrals": deferrals,
        "resolved": resolved,
        "added": copy.deepcopy(added),
        "problems": problems + step,
    }


# -- acceptance ------------------------------------------------------------------------------


def check_amendment_accepter(
    tracker: dict[str, Any], names: list[str], accepter: str
) -> tuple[list[dict[str, Any]], str]:
    """The named open amendments, every open one, with every amended item re-accepted; an independent accepter."""

    _require_accepted_stage(tracker)
    known = {row.get("id"): row for row in amendments(tracker)}
    named = sorted(set(names))
    if not named:
        raise SocomError("name the amendment to accept with --amendment")
    for identifier in named:
        row = known.get(identifier)
        if row is None:
            raise SocomError(f"unknown amendment: {identifier}")
        if row.get("status") != "open":
            raise SocomError(f"{identifier} is {row.get('status')}, not open")
    others = sorted(str(row.get("id")) for row in open_source_amendments(tracker) if row.get("id") not in named)
    if others:
        raise SocomError(
            f"the file baseline covers the whole stage: accept every open amendment together (also --amendment {' --amendment '.join(others)})"
        )
    rows = [known[identifier] for identifier in named]
    by_id = _by_id(tracker)
    pending = sorted(
        f"{item_id} ({(by_id.get(item_id) or {}).get('status')})"
        for row in rows
        for item_id in {str(row.get("item")), *(str(value) for value in row.get("applies") or [])}
        if (by_id.get(item_id) or {}).get("status") != "accepted"
    )
    if pending:
        raise SocomError(f"{len(pending)} amended items are not re-accepted yet: {_shown(pending)}")
    stale = sorted(
        f"{apply_id} for {row['id']}"
        for row in rows
        for apply_id in row.get("applies") or []
        if row["id"] not in (((by_id.get(apply_id) or {}).get("source_apply") or {}).get("amendments") or [])
    )
    if stale:
        raise SocomError(f"applies were not re-applied with progress apply-source-plan: {_shown(stale)}")
    return rows, require_independent_accepter(accepter, amendment_workers(tracker, rows))


def accept_source_amendment(
    tracker: dict[str, Any],
    names: list[str],
    accepter: str,
    evidence: list[str],
    review: dict[str, Any],
    delta: dict[str, Any],
) -> dict[str, Any]:
    """Accept open amendments and record the recomputed file baseline as the stage's current one."""

    rows, name = check_amendment_accepter(tracker, names, accepter)
    lines = sorted({str(text).strip() for text in evidence if str(text).strip()})
    if not lines:
        raise SocomError("amendment acceptance requires evidence")
    if review["problems"]:
        raise SocomError(_refusal("the amendment acceptance", review["problems"]))
    stage = _stage(tracker)
    previous = stage["baseline"]
    state = copy.deepcopy(review["state"])
    sha = state_sha256(state)
    now = _iso(_utc_now())
    ids = [row["id"] for row in rows]
    stage.setdefault("baseline_history", []).append(
        {
            **copy.deepcopy(previous),
            "superseded_at": now,
            "superseded_by": [{"amendment": row["id"], "reason": row.get("reason")} for row in rows],
        }
    )
    baseline = {
        "kind": BASELINE_KIND,
        "schema_version": BASELINE_SCHEMA,
        "tracker_revision": tracker["revision"] + 1,
        "baseline_sha256": sha,
        "state": state,
        "amendments": ids,
        "previous_baseline_sha256": previous.get("baseline_sha256"),
        "accepted_by": name,
        "recorded_at": now,
        "evidence": lines,
        "deferrals_resolved": copy.deepcopy(delta["resolved"]),
        "deferrals_added": copy.deepcopy(delta["added"]),
    }
    stage["baseline"] = baseline
    for row in rows:
        row["status"] = "accepted"
        row["accepted"] = {"by": name, "at": now, "route": ACCEPT_ROUTE, "evidence": lines, "baseline_sha256": sha}
    cited = stage.setdefault("accepted_evidence", [])
    if f"{BASELINE_CITATION}{sha}" not in cited:
        cited.append(f"{BASELINE_CITATION}{sha}")
    return baseline


# -- audits ----------------------------------------------------------------------------------


def _audit_rows(tracker: dict[str, Any], rows: list[Any]) -> list[str]:
    errors: list[str] = []
    by_id = _by_id(tracker)
    open_items: dict[str, list[str]] = {}
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            errors.append(f"{SOURCE_STAGE} amendment {number} must be an object")
            continue
        identifier = row.get("id")
        label = str(identifier)
        if row.get("kind") != AMENDMENT_KIND or row.get("schema_version") != AMENDMENT_SCHEMA:
            errors.append(f"{label} must be a {AMENDMENT_KIND} schema {AMENDMENT_SCHEMA} record")
        if identifier != f"{AMENDMENT_PREFIX}{number:03d}":
            errors.append(f"{SOURCE_STAGE} amendment {number} must have ID {AMENDMENT_PREFIX}{number:03d}")
        item = by_id.get(str(row.get("item"))) or {}
        if item.get("stage") != SOURCE_STAGE or item.get("kind") not in SOURCE_PLAN_KINDS or item.get("kind") != row.get("item_kind"):
            errors.append(f"{label} must amend a {SOURCE_STAGE} plan or data reconcile")
        applies = row.get("applies")
        if not isinstance(applies, list) or applies != sorted(set(applies)) or not all(
            (by_id.get(str(value)) or {}).get("kind") in SOURCE_APPLY_KINDS for value in applies
        ):
            errors.append(f"{label} must list its source applies once each, sorted")
            applies = []
        elif item.get("kind") == DATA_RECONCILE_KIND:
            if any((by_id.get(value) or {}).get("kind") != SEGMENT_APPLY_KIND for value in applies):
                errors.append(f"{label} re-applies a data reconcile through segment applies only")
        elif applies != [f"{row.get('item')}-apply"]:
            errors.append(f"{label} must re-apply exactly {row.get('item')}-apply")
        if not all(str(row.get(key) or "").strip() for key in ("opened_by", "opened_at", "reason")) or not row.get("evidence"):
            errors.append(f"{label} must record its opener, time, reason and evidence")
        traced = [
            entry for entry in item.get("review_history") or [] if isinstance(entry, dict) and entry.get("amendment") == identifier
        ]
        if not traced:
            errors.append(f"{label}: {row.get('item')} has no review-history entry for the amendment")
        status = row.get("status")
        if status == "open":
            open_items.setdefault(str(row.get("item")), []).append(label)
            if "accepted" in row:
                errors.append(f"{label} is open but records an acceptance")
            for apply_id in applies:
                apply = by_id.get(apply_id) or {}
                if apply.get("status") in ("awaiting_acceptance", "accepted") and identifier not in (
                    (apply.get("source_apply") or {}).get("amendments") or []
                ):
                    errors.append(
                        f"{apply_id} is {apply.get('status')} without a re-apply for {label}: "
                        "progress apply-source-plan re-applies it first"
                    )
        elif status == "accepted":
            accepted = row.get("accepted") or {}
            if accepted.get("route") != ACCEPT_ROUTE or not accepted.get("by") or not accepted.get("evidence"):
                errors.append(f"{label} was accepted outside {ACCEPT_ROUTE}")
            else:
                try:
                    require_independent_accepter(
                        str(accepted["by"]), amendment_workers(tracker, [row], before=str(accepted.get("at") or ""))
                    )
                except SocomError as failure:
                    errors.append(f"{label}: {failure}")
        else:
            errors.append(f"{label} has invalid status {status!r}")
    for item_id, labels in sorted(open_items.items()):
        if len(labels) > 1:
            errors.append(f"{item_id} has more than one open amendment: {labels}")
    return errors


def audit_amendments(tracker: dict[str, Any]) -> list[str]:
    """Tracker-only checks of the amendment records and the baseline history chain (``progress audit``)."""

    stage = _stage(tracker)
    rows = stage.get("amendments")
    history = stage.get("baseline_history")
    if rows is None and history is None:
        return []
    if not isinstance(rows if rows is not None else [], list) or not isinstance(history if history is not None else [], list):
        return [f"{SOURCE_STAGE} amendments and baseline_history must be lists"]
    errors = _audit_rows(tracker, rows or [])
    chain = baseline_chain(tracker)
    accepted = {row.get("id"): row for row in rows or [] if isinstance(row, dict) and row.get("status") == "accepted"}
    seen: list[str] = []
    recon = next((row for row in tracker.get("stages", []) if row.get("name") == RECON_STAGE), {}).get("baseline") or {}
    gate = _by_id(tracker).get(SOURCE_SEED_ID) or {}
    deferrals = copy.deepcopy((gate.get("source_gate") or {}).get("deferrals") or [])
    for index, entry in enumerate(chain):
        sha = entry.get("baseline_sha256")
        label = f"{SOURCE_STAGE} baseline {index} ({sha})"
        state = entry.get("state")
        if entry.get("kind") != BASELINE_KIND or entry.get("schema_version") != BASELINE_SCHEMA:
            errors.append(f"{label} must be {BASELINE_KIND} schema {BASELINE_SCHEMA}")
            continue
        if not isinstance(state, dict) or state_sha256(state) != sha:
            errors.append(f"{label} state differs from its digest")
            continue
        ghidra = state.get("ghidra") or {}
        if ghidra.get("receipt_sha256") != recon.get("receipt_sha256") or ghidra.get("scope_sha256") != recon.get("scope_sha256"):
            errors.append(f"{label} receipt is not the {RECON_STAGE} baseline")
        last = index == len(chain) - 1
        superseded = entry.get("superseded_by")
        if last and ("superseded_by" in entry or "superseded_at" in entry):
            errors.append(f"{label} is the current baseline but records a supersession")
        if not last:
            following = chain[index + 1].get("amendments") or []
            if not isinstance(superseded, list) or [row.get("amendment") for row in superseded if isinstance(row, dict)] != following:
                errors.append(f"{label} must name the amendments that superseded it, with their reasons")
            elif not all(str(row.get("reason") or "").strip() for row in superseded):
                errors.append(f"{label} must keep each superseding amendment's reason")
        if index == 0:
            if entry.get("amendments") or entry.get("previous_baseline_sha256"):
                errors.append(f"{label} is the gate's baseline: it follows no amendment")
        else:
            names = entry.get("amendments")
            if not isinstance(names, list) or not names or names != sorted(set(names)):
                errors.append(f"{label} must name the amendments it accepts")
                names = []
            if entry.get("previous_baseline_sha256") != chain[index - 1].get("baseline_sha256"):
                errors.append(f"{label} does not follow the baseline before it")
            for name in names:
                row = accepted.get(name)
                if row is None or (row.get("accepted") or {}).get("baseline_sha256") != sha:
                    errors.append(f"{label} names {name}, which is not an amendment accepted with it")
                seen.append(str(name))
            if not entry.get("accepted_by") or not entry.get("evidence"):
                errors.append(f"{label} must record its accepter and evidence")
            deferrals, step = apply_deferral_delta(deferrals, entry.get("deferrals_resolved"), entry.get("deferrals_added"))
            errors.extend(f"{label}: {problem}" for problem in step)
        # The gate's baseline holds the gate's recorded deferrals; each later one the deferrals in force.
        recorded = state.get("deferrals") or {}
        if (
            recorded.get("sha256") != _digest(deferral_body(deferrals))
            or recorded.get("artifact_count") != (state.get("unresolved") or {}).get("count")
            or recorded.get("artifact_count") != sum(len(row.get("artifacts") or []) for row in deferrals)
        ):
            errors.append(f"{label} deferrals are not the deferrals in force, covering exactly its unresolved artifacts")
    if sorted(seen) != sorted(accepted) or len(seen) != len(set(seen)):
        errors.append(f"{SOURCE_STAGE} accepted amendments and the baselines that accept them differ")
    return errors
