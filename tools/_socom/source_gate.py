"""Stage 4 (source-correlation) gate: review, independent acceptance and the file-stage baseline.

Stage 4 is file-only, so its gate cannot close through the live receipt
handoff. The route mirrors the stage 3 close-out (an independent reviewer,
an independent accepter and a recorded baseline) for files:

* ``source gate-check`` runs every gate check read-only. It lists every
  unresolved artifact of the accepted owner plans with the deferral that
  covers it, if any.
* ``progress handoff-source-gate`` is run by the reviewer under the gate's
  lease. It re-runs the checks with a deferral file and records the
  deferrals and the candidate baseline on the gate item.
* ``progress accept-source-gate`` is run by an accepter other than the
  reviewer. It re-runs the checks with the recorded deferrals and requires
  the same baseline digest. It then accepts the gate and records the
  baseline on the stage row.

Neither the reviewer nor the accepter may have handed off stage 4 work, and
neither may be a tool maintainer. The gate decides no row: each unresolved
artifact must be covered by exactly one recorded deferral, which cites an
open workspace issue or the user's own decision. The baseline records the
digests of every accepted plan and owner map, the apply records, the
annotation edges under ``src/``, the unresolved rows and the deferrals.
It also records the live receipt over the stage 3 scope, which must still
equal the ``ghidra-reconstruction`` baseline.
"""

from __future__ import annotations

import copy
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from .capabilities import CAPABILITY_GATE_ACCEPTER
from .ghidra import semantic_receipt
from .issues import audit_issues
from .snapshot import snapshot_status
from .source import audit_docblocks, audit_source_trace, source_artifacts
from .source_apply import (
    _shown,
    annotate,
    applied_state,
    cited_plan,
    owner_map_sha256,
    verify_source_apply,
)
from .source_plan import (
    CAPABILITY_GATE_KIND,
    DATA_RECONCILE_KIND,
    SEGMENT_PLAN_KIND,
    SOURCE_APPLY_ROUTE_ID,
    SOURCE_PLAN_KINDS,
    SOURCE_SEED_ID,
    SOURCE_STAGE,
    validate_source_plan,
    verify_graph,
)
from .tracker import RECON_STAGE, _iso, _utc_now, audit_tracker, scope_sha256, stage_live_scope
from .util import SocomError, canonical_json, sha256_file

GATE_RECORD_KIND = "socom-source-gate-review"
GATE_RECORD_SCHEMA = 1
BASELINE_KIND = "source-file-baseline"
BASELINE_SCHEMA = 1
DEFERRALS_KIND = "socom-source-gate-deferrals"
DEFERRALS_SCHEMA = 1
HANDOFF_ROUTE = "progress handoff-source-gate"
ACCEPT_ROUTE = "progress accept-source-gate"
CLOSEOUT = f"build/closeout-{SOURCE_STAGE}"
BASELINE_CITATION = "source-file-baseline-sha256:"
# A tool maintainer changes the gate's own checks: it never reviews or accepts the gate.
MAINTAINER_MARKER = "tool-maintainer"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}Z)?$")
_REFUSAL_SHOWN = 12


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def state_sha256(state: dict[str, Any]) -> str:
    """Digest of a baseline state: the reviewer and the accepter must compute the same one."""

    return _digest(state)


def _by_id(tracker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in tracker.get("work_items", []) if isinstance(row, dict) and "id" in row}


def _stage_row(tracker: dict[str, Any], name: str) -> dict[str, Any]:
    return next((row for row in tracker.get("stages", []) if row.get("name") == name), {})


def _stage_items(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in tracker.get("work_items", []) if row.get("stage") == SOURCE_STAGE]


def _refusal(what: str, problems: list[str]) -> str:
    shown = problems[:_REFUSAL_SHOWN]
    more = f"\n- +{len(problems) - len(shown)} more" if len(problems) > len(shown) else ""
    return (
        f"{what} refused ({len(problems)} problems; `source gate-check --output {CLOSEOUT}/gate-check.json` "
        "lists them all):\n- " + "\n- ".join(shown) + more
    )


# -- independence ---------------------------------------------------------------------


def stage_workers(tracker: dict[str, Any]) -> set[str]:
    """Everyone who handed off stage 4 work: planners, reconcilers and apply workers (the gate excluded)."""

    owners: set[str] = set()
    for item in _stage_items(tracker):
        if item.get("id") == SOURCE_SEED_ID:
            continue
        handoffs = [item.get("handoff")] + [entry.get("handoff") for entry in item.get("review_history") or [] if isinstance(entry, dict)]
        owners.update(str(row["owner"]) for row in handoffs if isinstance(row, dict) and row.get("owner"))
    return owners


def require_independent(name: str, role: str, workers: set[str]) -> str:
    """The gate's reviewer or accepter: not a stage 4 worker, not a tool maintainer."""

    name = str(name or "").strip()
    if not name:
        raise SocomError(f"the gate {role} must not be empty")
    if MAINTAINER_MARKER in name.casefold() or name == CAPABILITY_GATE_ACCEPTER:
        raise SocomError(f"gate {role} {name} is a tool maintainer: the {SOURCE_STAGE} gate needs an independent {role}")
    if name in workers:
        raise SocomError(f"gate {role} {name} handed off {SOURCE_STAGE} work: the gate needs an independent {role}")
    return name


# -- deferrals ------------------------------------------------------------------------


def normalize_deferrals(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """(normalized deferrals sorted by ID, problems) of a ``socom-source-gate-deferrals`` body."""

    if not isinstance(value, dict) or value.get("kind") != DEFERRALS_KIND or value.get("schema_version") != DEFERRALS_SCHEMA:
        return [], [f"a deferral file is a {DEFERRALS_KIND} schema {DEFERRALS_SCHEMA} object"]
    rows = value.get("deferrals")
    if not isinstance(rows, list):
        return [], ["deferrals must be a list"]
    problems: list[str] = []
    result: list[dict[str, Any]] = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            problems.append(f"deferral {number} must be an object")
            continue
        identifier = row.get("id")
        label = identifier if isinstance(identifier, str) and identifier else str(number)
        unknown = sorted(set(row) - {"id", "artifacts", "reason", "issue", "approval"})
        if unknown:
            problems.append(f"deferral {label} has unknown fields {unknown}")
        if not isinstance(identifier, str) or not _SLUG.match(identifier):
            problems.append(f"deferral {label} needs an id (a lowercase slug)")
        artifacts = row.get("artifacts")
        if (
            not isinstance(artifacts, list)
            or not artifacts
            or not all(isinstance(value, str) and value.startswith("socom:") for value in artifacts)
            or len(set(artifacts)) != len(artifacts)
        ):
            problems.append(f"deferral {label} must list distinct artifact IDs")
            artifacts = [value for value in artifacts or [] if isinstance(value, str)] if isinstance(artifacts, list) else []
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"deferral {label} needs a reason")
            reason = ""
        issue, approval = row.get("issue"), row.get("approval")
        if (issue is None) == (approval is None):
            problems.append(
                f"deferral {label} must cite exactly one of issue (an open workspace issue) or approval (the user's decision)"
            )
        if issue is not None and not (isinstance(issue, str) and issue.startswith("socom:workspace-issue:")):
            problems.append(f"deferral {label} issue must be a socom:workspace-issue: ID")
        if approval is not None:
            if (
                not isinstance(approval, dict)
                or set(approval) != {"by", "at", "decision"}
                or approval.get("by") != "user"
                or not isinstance(approval.get("decision"), str)
                or not approval["decision"].strip()
                or not _DATE.match(str(approval.get("at")))
            ):
                problems.append(
                    f"deferral {label} approval must be {{by: \"user\", at: <YYYY-MM-DD>, decision: <the user's words>}}"
                )
                approval = None
            else:
                approval = {"by": "user", "at": approval["at"], "decision": approval["decision"].strip()}
        result.append(
            {
                "id": identifier if isinstance(identifier, str) else str(number),
                "artifacts": sorted(set(artifacts)),
                "reason": reason.strip(),
                "issue": issue if isinstance(issue, str) else None,
                "approval": approval,
            }
        )
    counts = Counter(row["id"] for row in result)
    duplicated = sorted(identifier for identifier, count in counts.items() if count > 1)
    if duplicated:
        problems.append(f"deferral IDs are not unique: {duplicated}")
    return sorted(result, key=lambda row: row["id"]), problems


def deferral_body(deferrals: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": DEFERRALS_KIND, "schema_version": DEFERRALS_SCHEMA, "deferrals": deferrals}


def deferral_cover(
    unresolved: list[dict[str, Any]], deferrals: list[dict[str, Any]], issues: dict[str, Any] | None
) -> tuple[dict[str, Any], list[str]]:
    """Each unresolved artifact covered by exactly one deferral; no deferral of anything else."""

    problems: list[str] = []
    holders: dict[str, list[str]] = defaultdict(list)
    for row in deferrals:
        for artifact in row["artifacts"]:
            holders[artifact].append(row["id"])
    wanted = [row["artifact"] for row in unresolved]
    uncovered = [artifact for artifact in wanted if artifact not in holders]
    twice = sorted(artifact for artifact, ids in holders.items() if len(ids) > 1)
    stale = sorted(set(holders) - set(wanted))
    if uncovered:
        problems.append(
            f"{len(uncovered)} unresolved artifacts have no recorded deferral (the gate does not decide them): {_shown(uncovered)}"
        )
    if twice:
        problems.append(f"{len(twice)} artifacts are deferred more than once: {_shown(twice)}")
    if stale:
        problems.append(f"{len(stale)} deferred artifacts are not unresolved in an accepted owner plan: {_shown(stale)}")
    ledger = {
        row.get("id"): row for row in (issues or {}).get("issues") or [] if isinstance(row, dict)
    }
    for row in deferrals:
        if row["issue"] is None:
            continue
        issue = ledger.get(row["issue"])
        if issues is None:
            problems.append(f"deferral {row['id']} cites {row['issue']}, but the workspace issue ledger is missing")
        elif issue is None:
            problems.append(f"deferral {row['id']} cites unknown workspace issue {row['issue']}")
        elif issue.get("status") != "open":
            problems.append(f"deferral {row['id']} cites {row['issue']}, which is {issue.get('status')}, not open")
    by_basis = Counter("workspace-issue" if row["issue"] else "user-approval" for row in deferrals)
    cover = {
        "count": len(deferrals),
        "artifact_count": sum(len(row["artifacts"]) for row in deferrals),
        "by_basis": dict(sorted(by_basis.items())),
        "sha256": _digest(deferral_body(deferrals)),
        "uncovered": uncovered,
        "twice": twice,
        "stale": stale,
        "holders": {artifact: ids for artifact, ids in sorted(holders.items())},
    }
    return cover, problems


# -- the live receipt ---------------------------------------------------------------------


def live_stage3_receipt(root: Path, tracker: dict[str, Any], *, bridge_url: str | None = None) -> dict[str, Any]:
    """The live receipt over the stage 3 scope and whether it still equals that stage's baseline.

    Stage 4 never writes Ghidra. This reads Ghidra (``ghidra receipt``)
    without saving. An unreachable bridge or a failed preflight is reported
    as ``error``, not raised.
    """

    baseline = _stage_row(tracker, RECON_STAGE).get("baseline") or {}
    result: dict[str, Any] = {
        "ok": False,
        "stage": RECON_STAGE,
        "baseline_receipt_sha256": baseline.get("receipt_sha256"),
        "baseline_scope_sha256": baseline.get("scope_sha256"),
        "receipt_sha256": None,
        "scope_sha256": None,
        "error": None,
    }
    if not baseline.get("receipt_sha256"):
        result["error"] = f"{RECON_STAGE} records no baseline receipt"
        return result
    try:
        scope = stage_live_scope(tracker, RECON_STAGE)
    except SocomError as failure:
        result["error"] = f"the {RECON_STAGE} scope is unavailable: {failure}"
        return result
    result["scope_sha256"] = scope_sha256(scope)
    result["scope_counts"] = {key: len(value) for key, value in scope.items()}
    try:
        current = semantic_receipt(root, bridge_url=bridge_url, scope=scope)
    except SocomError as failure:
        result["error"] = (
            f"the live Ghidra receipt is unavailable ({str(failure).splitlines()[0]}): the gate needs the bridge "
            "and project soCOM with socom.elf; nothing was recorded"
        )
        return result
    result["receipt_sha256"] = current["receipt_sha256"]
    if result["scope_sha256"] != result["baseline_scope_sha256"]:
        result["error"] = f"the {RECON_STAGE} scope {result['scope_sha256']} differs from its baseline scope {result['baseline_scope_sha256']}"
    elif current["receipt_sha256"] != baseline["receipt_sha256"]:
        result["error"] = (
            f"the live receipt {current['receipt_sha256']} differs from the {RECON_STAGE} baseline "
            f"{baseline['receipt_sha256']}: stage 4 is file-only, Ghidra changed since stage 3 closed"
        )
    else:
        result["ok"] = True
    return result


def skipped_receipt(tracker: dict[str, Any]) -> dict[str, Any]:
    baseline = _stage_row(tracker, RECON_STAGE).get("baseline") or {}
    return {
        "ok": False,
        "stage": RECON_STAGE,
        "baseline_receipt_sha256": baseline.get("receipt_sha256"),
        "baseline_scope_sha256": baseline.get("scope_sha256"),
        "receipt_sha256": None,
        "scope_sha256": None,
        "skipped": True,
        "error": "the live receipt was not checked (--skip-receipt)",
    }


# -- the review -----------------------------------------------------------------------


def preconditions(tracker: dict[str, Any], *, lease_owner: str | None) -> list[str]:
    """Cheap tracker-only gate conditions, checked before Ghidra is read.

    The stage is decomposed, every other stage 4 item is accepted (the route
    gate by its registered capability), no tracker blocker blocks the stage,
    and nothing is leased except the gate itself by ``lease_owner``.
    """

    problems: list[str] = []
    by_id = _by_id(tracker)
    gate = by_id.get(SOURCE_SEED_ID)
    if gate is None or gate.get("kind") != "stage-gate" or not isinstance(_stage_row(tracker, SOURCE_STAGE).get("decomposition"), dict):
        return [f"{SOURCE_STAGE} is not decomposed: {SOURCE_SEED_ID} is not its stage gate"]
    pending = [row["id"] for row in _stage_items(tracker) if row["id"] != SOURCE_SEED_ID and row.get("status") != "accepted"]
    if pending:
        problems.append(f"{len(pending)} {SOURCE_STAGE} items are not accepted: {_shown(pending)}")
    route = by_id.get(SOURCE_APPLY_ROUTE_ID)
    if route is None or route.get("kind") != CAPABILITY_GATE_KIND:
        problems.append(f"{SOURCE_APPLY_ROUTE_ID} is missing")
    elif route.get("status") != "accepted" or (route.get("accepted") or {}).get("by") != CAPABILITY_GATE_ACCEPTER:
        problems.append(f"{SOURCE_APPLY_ROUTE_ID} is not opened by {CAPABILITY_GATE_ACCEPTER}")
    leased = [
        f"{row['id']} ({row['lease'].get('owner')})"
        for row in tracker.get("work_items", [])
        if isinstance(row.get("lease"), dict)
        and not (row["id"] == SOURCE_SEED_ID and lease_owner is not None and row["lease"].get("owner") == lease_owner)
    ]
    if leased:
        problems.append(f"{len(leased)} work items are leased: {_shown(leased)}")
    blockers = [
        row.get("id")
        for row in tracker.get("blockers", [])
        if row.get("status") == "open" and SOURCE_STAGE in (row.get("blocks") or [])
    ]
    if blockers:
        problems.append(f"open blockers block {SOURCE_STAGE}: {blockers}")
    return problems


def unit_conflicts(plans: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Cross-plan unit consistency: one unit keeps one workspace path, original path and classification.

    Rows are compared both ways, by unit and by workspace path. A row that
    leaves ``original_path`` null (a data reconcile's row, say) states no
    path, so it agrees with any; two different stated paths conflict.
    """

    units: dict[str, dict[tuple[Any, ...], set[str]]] = defaultdict(lambda: defaultdict(set))
    paths: dict[str, dict[tuple[Any, ...], set[str]]] = defaultdict(lambda: defaultdict(set))
    originals: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for item_id, plan in plans:
        for owner in plan.get("owners") or []:
            if not isinstance(owner, dict):
                continue
            unit, path, original = owner.get("translation_unit"), owner.get("workspace_path"), owner.get("original_path")
            if unit:
                units[str(unit)][(path, owner.get("classification"))].add(item_id)
                if original:
                    originals[("unit", str(unit))][str(original)].add(item_id)
            if path:
                paths[str(path)][(unit, owner.get("classification"))].add(item_id)
                if original:
                    originals[("workspace path", str(path))][str(original)].add(item_id)
    problems: list[str] = []
    for label, table in (("unit", units), ("workspace path", paths)):
        for key, variants in sorted(table.items()):
            if len(variants) > 1:
                shown = "; ".join(
                    f"{list(variant)} in {', '.join(sorted(items))}" for variant, items in sorted(variants.items(), key=str)
                )
                problems.append(f"{label} {key} is owned inconsistently across plans: {shown}")
    for (label, key), variants in sorted(originals.items()):
        if len(variants) > 1:
            shown = "; ".join(f"{value} in {', '.join(sorted(items))}" for value, items in sorted(variants.items()))
            problems.append(f"{label} {key} names different original paths across plans: {shown}")
    return problems


def _unresolved_message(rows: list[str]) -> str:
    # Exactly the line ``source_apply.lean_completeness`` reports for them.
    return f"{len(rows)} artifacts are unresolved in accepted owner plans: {_shown(rows)}"


def review_gate(
    root: Path,
    tracker: dict[str, Any],
    *,
    graph: dict[str, Any],
    graph_origin: str,
    section_of: Callable[[int], str | None],
    deferrals: list[dict[str, Any]],
    deferral_problems: list[str],
    issues: dict[str, Any] | None,
    census: dict[str, Any] | None,
    receipt: dict[str, Any],
    lease_owner: str | None,
) -> dict[str, Any]:
    """Every gate check over the current workspace, with the baseline state it would record."""

    problems = preconditions(tracker, lease_owner=lease_owner)
    by_id = _by_id(tracker)
    decomposition = _stage_row(tracker, SOURCE_STAGE).get("decomposition") or {}
    # Strict audits and current generated snapshots.
    problems.extend(f"progress audit --strict: {error}" for error in audit_tracker(tracker, strict=True, census=census))
    if not snapshot_status(root, tracker)["fresh"]:
        problems.append("the README progress snapshot is stale (docs readme-progress --write)")
    if issues is None:
        problems.append("the workspace issue ledger .agent/WORKSPACE_ISSUES.json is missing")
    else:
        problems.extend(f"issue audit: {error}" for error in audit_issues(issues))
    # Reproducible evidence: the decomposition's graph.
    graph_sha = graph.get("graph_sha256") if isinstance(graph, dict) else None
    if graph_sha != decomposition.get("graph_sha256"):
        problems.append(f"the graph {graph_sha} is not the decomposition's graph {decomposition.get('graph_sha256')}")
    else:
        problems.extend(f"source graph: {problem}" for problem in verify_graph(graph))

    rows: list[dict[str, Any]] = []
    plans: list[tuple[str, dict[str, Any]]] = []
    unresolved: list[dict[str, Any]] = []
    for item in _stage_items(tracker):
        if item.get("kind") not in SOURCE_PLAN_KINDS or item.get("status") != "accepted":
            continue
        try:
            plan, relative, sha = cited_plan(root, tracker, item["id"])
        except SocomError as failure:
            problems.append(str(failure))
            continue
        plans.append((item["id"], plan))
        report = validate_source_plan(root, tracker, plan, graph, section_of=section_of, applied=applied_state(tracker, item["id"], sha))
        if not report["ok"]:
            problems.append(f"{relative} does not validate ({len(report['problems'])} problems): {_shown(report['problems'])}")
        owner_map = owner_map_sha256(plan)
        artifacts = sum(len(owner.get("artifacts") or []) for owner in plan.get("owners") or [] if isinstance(owner, dict))
        plan_unresolved = [row for row in plan.get("unresolved") or [] if isinstance(row, dict)]
        unresolved.extend(
            {"item": item["id"], "artifact": str(row.get("artifact")), "reason": str(row.get("reason", ""))}
            for row in plan_unresolved
        )
        row: dict[str, Any] = {
            "item": item["id"],
            "kind": item.get("kind"),
            "plan": relative,
            "plan_sha256": sha,
            "owner_map_sha256": owner_map,
            "owner_count": len(plan.get("owners") or []),
            "owned_artifact_count": artifacts,
            "unresolved_count": len(plan_unresolved),
            "apply": None,
            "annotations_sha256": None,
            "annotation_count": 0,
        }
        if item.get("kind") != DATA_RECONCILE_KIND:
            apply = by_id.get(f"{item['id']}-apply") or {}
            record = apply.get("source_apply") if isinstance(apply.get("source_apply"), dict) else {}
            row["apply"] = apply.get("id")
            if apply.get("status") != "accepted" or record.get("plan_sha256") != sha:
                problems.append(f"{item['id']}-apply is not accepted with a record of the accepted plan {sha}")
            elif record.get("owner_map_sha256") != owner_map:
                problems.append(f"{item['id']}-apply recorded owner map {record.get('owner_map_sha256')}, the plan's is {owner_map}")
            else:
                problems.extend(f"source apply-check {apply['id']}: {problem}" for problem in verify_source_apply(root, tracker, apply))
            row["annotations_sha256"] = record.get("annotations_sha256")
            row["annotation_count"] = record.get("annotation_count", 0)
            if item.get("kind") == SEGMENT_PLAN_KIND:
                try:
                    checked = annotate(root, tracker, item["id"], write=False)
                except SocomError as failure:
                    problems.append(f"source annotate --check {relative}: {failure}")
                else:
                    if not checked["ok"]:
                        drift = [f"{entry['path']} ({entry['state']})" for entry in checked["drift"]]
                        problems.append(f"source annotate --check {relative}: {_shown(checked['problems'] + drift)}")
                    row["annotations_sha256"] = checked["annotations_sha256"]
                    row["annotation_count"] = checked["annotation_count"]
        rows.append(row)
    # No blocking conflicts between the plans.
    problems.extend(unit_conflicts(plans))
    # Annotation grammar and completeness (unresolved rows are the deferrals' business).
    docblocks = audit_docblocks(root)
    problems.extend(f"audit docblocks: {error}" for error in docblocks["errors"])
    trace = audit_source_trace(root, require_complete=True)
    expected_unresolved = _unresolved_message([row["artifact"] for row in unresolved]) if unresolved else None
    problems.extend(
        f"audit source-trace --require-complete: {error}"
        for error in trace["errors"]
        if error not in docblocks["errors"] and error != expected_unresolved
    )
    problems.extend(deferral_problems)
    cover, cover_problems = deferral_cover(unresolved, deferrals, issues)
    problems.extend(cover_problems)
    if not receipt.get("ok"):
        problems.append(str(receipt.get("error") or "the live receipt differs from the stage 3 baseline"))

    parsed = source_artifacts(root)
    edges = sorted({(row["relation"], row["section"], row["artifact_id"], row["path"]) for row in parsed["artifacts"]})
    current = _applied_files(root, tracker)
    kinds = Counter(row["artifact"].split(":")[1] if row["artifact"].count(":") >= 2 else "other" for row in unresolved)
    state = {
        "graph_sha256": decomposition.get("graph_sha256"),
        "plan_count": len(rows),
        "plans": sorted(rows, key=lambda row: row["item"]),
        "owned_artifact_count": sum(row["owned_artifact_count"] for row in rows),
        "annotations": {
            "edge_count": len(edges),
            "file_count": len({edge[3] for edge in edges}),
            "sha256": _digest([list(edge) for edge in edges]),
        },
        "apply_files": {"count": len(current), "sha256": _digest(current)},
        "unresolved": {
            "count": len(unresolved),
            "plan_count": len({row["item"] for row in unresolved}),
            "by_kind": dict(sorted(kinds.items())),
            "sha256": _digest(sorted([row["item"], row["artifact"], row["reason"]] for row in unresolved)),
        },
        "deferrals": {key: cover[key] for key in ("count", "artifact_count", "by_basis", "sha256")},
        "ghidra": {
            "stage": RECON_STAGE,
            "receipt_sha256": receipt.get("receipt_sha256"),
            "scope_sha256": receipt.get("scope_sha256"),
        },
    }
    return {
        "ok": not problems,
        "problems": problems,
        "graph": graph_origin,
        "state": state,
        "baseline_sha256": state_sha256(state) if not problems else None,
        "unresolved": [
            {**row, "deferral": cover["holders"].get(row["artifact"])} for row in unresolved
        ],
        "deferrals": deferrals,
        "receipt": receipt,
        "counts": {
            "problems": len(problems),
            "plans": len(rows),
            "unresolved": len(unresolved),
            "uncovered": len(cover["uncovered"]),
            "deferrals": cover["count"],
            "annotation_edges": len(edges),
        },
    }


# -- the tracker mutations ----------------------------------------------------------------


def _gate(tracker: dict[str, Any], item_id: str) -> dict[str, Any]:
    item = _by_id(tracker).get(item_id)
    if item_id != SOURCE_SEED_ID or item is None or item.get("kind") != "stage-gate":
        raise SocomError(f"{item_id} is not the decomposed {SOURCE_STAGE} stage gate ({SOURCE_SEED_ID})")
    return item


def check_reviewer(tracker: dict[str, Any], item_id: str, owner: str) -> str:
    """The gate is leased by ``owner``, an independent reviewer (checked before Ghidra is read)."""

    item = _gate(tracker, item_id)
    lease = item.get("lease")
    if item.get("status") != "in_progress" or not isinstance(lease, dict):
        raise SocomError(f"{item_id} is not actively leased: claim it with progress work claim first")
    if lease.get("owner") != owner:
        raise SocomError(f"{item_id} is leased by {lease.get('owner')}")
    return require_independent(owner, "reviewer", stage_workers(tracker))


def check_accepter(tracker: dict[str, Any], item_id: str, accepter: str) -> tuple[dict[str, Any], str]:
    """The gate awaits acceptance with a review record; ``accepter`` is independent of it."""

    item = _gate(tracker, item_id)
    if item.get("status") != "awaiting_acceptance":
        raise SocomError(f"{item_id} is {item.get('status')}, not awaiting_acceptance")
    record = item.get("source_gate")
    if not isinstance(record, dict) or not isinstance(record.get("state"), dict):
        raise SocomError(f"{item_id} has no gate review record: the reviewer hands off with {HANDOFF_ROUTE}")
    name = require_independent(accepter, "accepter", stage_workers(tracker))
    if name in {record.get("reviewed_by"), (item.get("handoff") or {}).get("owner")}:
        raise SocomError(f"{item_id} cannot be accepted by its reviewer {name}")
    return record, name


def _evidence_lines(state: dict[str, Any], sha: str) -> list[str]:
    return [
        f"{BASELINE_CITATION}{sha}",
        f"ghidra-receipt-sha256:{state['ghidra']['receipt_sha256']} (equal to the {RECON_STAGE} baseline)",
        f"source-gate-deferrals-sha256:{state['deferrals']['sha256']} count:{state['deferrals']['count']} "
        f"artifacts:{state['deferrals']['artifact_count']}",
        f"source-gate-plans count:{state['plan_count']} unresolved:{state['unresolved']['count']} "
        f"annotation-edges:{state['annotations']['edge_count']}",
    ]


def handoff_source_gate(
    tracker: dict[str, Any], item_id: str, owner: str, summary: str, evidence: list[str], review: dict[str, Any]
) -> dict[str, Any]:
    """Hand the reviewed gate off with its deferrals and the candidate baseline state."""

    reviewer = check_reviewer(tracker, item_id, owner)
    if not summary.strip():
        raise SocomError("handoff summary must not be empty")
    if review["problems"]:
        raise SocomError(_refusal("the gate handoff", review["problems"]))
    item = _gate(tracker, item_id)
    state = copy.deepcopy(review["state"])
    sha = state_sha256(state)
    now = _iso(_utc_now())
    item["status"] = "awaiting_acceptance"
    item["lease"] = None
    item["handoff"] = {"owner": reviewer, "summary": summary.strip(), "submitted_at": now}
    item["source_gate"] = {
        "kind": GATE_RECORD_KIND,
        "schema_version": GATE_RECORD_SCHEMA,
        "reviewed_by": reviewer,
        "reviewed_at": now,
        "graph": review["graph"],
        "baseline_sha256": sha,
        "deferrals": copy.deepcopy(review["deferrals"]),
        "state": state,
    }
    item["evidence"] = sorted(set(evidence) | set(_evidence_lines(state, sha)))
    return item["source_gate"]


def accept_source_gate(
    tracker: dict[str, Any], item_id: str, accepter: str, evidence: list[str], review: dict[str, Any]
) -> dict[str, Any]:
    """Accept the gate independently and record the file-stage baseline on the stage row."""

    record, name = check_accepter(tracker, item_id, accepter)
    if not [line for line in evidence if line.strip()]:
        raise SocomError("gate acceptance requires evidence")
    if review["problems"]:
        raise SocomError(_refusal("the gate acceptance", review["problems"]))
    sha = state_sha256(review["state"])
    if sha != record.get("baseline_sha256"):
        changed = sorted(key for key in review["state"] if review["state"].get(key) != record["state"].get(key))
        raise SocomError(
            f"the workspace changed since the review: baseline {sha} != reviewed {record.get('baseline_sha256')} "
            f"(differs in {changed}); reject the gate for a new review"
        )
    stage = _stage_row(tracker, SOURCE_STAGE)
    if stage.get("baseline"):
        raise SocomError(f"stage {SOURCE_STAGE} already records a baseline")
    item = _gate(tracker, item_id)
    now = _iso(_utc_now())
    item["status"] = "accepted"
    item["accepted"] = {"by": name, "at": now, "route": ACCEPT_ROUTE}
    item["evidence"] = sorted(set(item.get("evidence") or []) | set(evidence))
    state = record.pop("state")
    baseline = {
        "kind": BASELINE_KIND,
        "schema_version": BASELINE_SCHEMA,
        "tracker_revision": tracker["revision"] + 1,
        "baseline_sha256": sha,
        "state": state,
        "reviewed_by": record.get("reviewed_by"),
        "accepted_by": name,
        "recorded_at": now,
        "evidence": sorted(set(evidence)),
    }
    stage["baseline"] = baseline
    cited = stage.setdefault("accepted_evidence", [])
    for line in (f"{BASELINE_CITATION}{sha}", f"ghidra-receipt-sha256:{state['ghidra']['receipt_sha256']}"):
        if line not in cited:
            cited.append(line)
    return baseline


# -- audits ----------------------------------------------------------------------------


def audit_source_gate(tracker: dict[str, Any]) -> list[str]:
    """Tracker-only checks of the gate record and the file-stage baseline (``progress audit``)."""

    errors: list[str] = []
    by_id = _by_id(tracker)
    gate = by_id.get(SOURCE_SEED_ID)
    stage = _stage_row(tracker, SOURCE_STAGE)
    baseline = stage.get("baseline")
    if gate is None or gate.get("kind") != "stage-gate":
        if baseline:
            errors.append(f"{SOURCE_STAGE} records a baseline without a decomposed stage gate")
        return errors
    status = gate.get("status")
    record = gate.get("source_gate")
    if status in ("awaiting_acceptance", "accepted") and not isinstance(record, dict):
        errors.append(f"{SOURCE_SEED_ID} is {status} without a gate review record ({HANDOFF_ROUTE})")
        return errors
    if record is None:
        if baseline:
            errors.append(f"{SOURCE_STAGE} records a baseline but its gate has no review record")
        return errors
    if status not in ("awaiting_acceptance", "accepted"):
        errors.append(f"{SOURCE_SEED_ID} keeps a gate review record while {status}")
        return errors
    if record.get("kind") != GATE_RECORD_KIND or record.get("schema_version") != GATE_RECORD_SCHEMA:
        errors.append(f"{SOURCE_SEED_ID} gate review record must be {GATE_RECORD_KIND} schema {GATE_RECORD_SCHEMA}")
        return errors
    if record.get("reviewed_by") != (gate.get("handoff") or {}).get("owner"):
        errors.append(f"{SOURCE_SEED_ID} gate review record names a reviewer other than its handoff owner")
    deferrals, problems = normalize_deferrals(deferral_body(record.get("deferrals")))
    if problems or deferrals != record.get("deferrals"):
        errors.append(f"{SOURCE_SEED_ID} gate review record holds malformed deferrals")
    workers = stage_workers(tracker)
    names = [record.get("reviewed_by")]
    if status == "awaiting_acceptance":
        state = record.get("state")
        if not isinstance(state, dict) or state_sha256(state) != record.get("baseline_sha256"):
            errors.append(f"{SOURCE_SEED_ID} gate review state differs from its baseline digest")
            return errors
        if baseline:
            errors.append(f"{SOURCE_STAGE} records a baseline before its gate is accepted")
    else:
        accepted = gate.get("accepted") or {}
        if accepted.get("route") != ACCEPT_ROUTE:
            errors.append(f"{SOURCE_SEED_ID} was accepted outside {ACCEPT_ROUTE}")
        if "state" in record:
            errors.append(f"{SOURCE_SEED_ID} keeps its review state after acceptance: it moves to the stage baseline")
        if not isinstance(baseline, dict):
            errors.append(f"{SOURCE_STAGE} gate is accepted without its file-stage baseline")
            return errors
        names.append(accepted.get("by"))
        state = baseline.get("state")
        sha = baseline.get("baseline_sha256")
        if baseline.get("kind") != BASELINE_KIND or baseline.get("schema_version") != BASELINE_SCHEMA:
            errors.append(f"{SOURCE_STAGE} baseline must be {BASELINE_KIND} schema {BASELINE_SCHEMA}")
            return errors
        if not isinstance(state, dict) or state_sha256(state) != sha or sha != record.get("baseline_sha256"):
            errors.append(f"{SOURCE_STAGE} baseline state differs from its digest or the reviewed digest")
            return errors
        if baseline.get("accepted_by") != accepted.get("by") or baseline.get("reviewed_by") != record.get("reviewed_by"):
            errors.append(f"{SOURCE_STAGE} baseline names a reviewer or accepter other than its gate's")
        if accepted.get("by") == record.get("reviewed_by"):
            errors.append(f"{SOURCE_SEED_ID} was accepted by its reviewer")
        cited = stage.get("accepted_evidence") or []
        if f"{BASELINE_CITATION}{sha}" not in cited:
            errors.append(f"stage {SOURCE_STAGE} accepted evidence omits its file-stage baseline")
        recon = _stage_row(tracker, RECON_STAGE).get("baseline") or {}
        ghidra = state.get("ghidra") or {}
        if ghidra.get("receipt_sha256") != recon.get("receipt_sha256") or ghidra.get("scope_sha256") != recon.get("scope_sha256"):
            errors.append(f"{SOURCE_STAGE} baseline receipt is not the {RECON_STAGE} baseline")
        if f"ghidra-receipt-sha256:{ghidra.get('receipt_sha256')}" not in cited:
            errors.append(f"stage {SOURCE_STAGE} accepted evidence omits the stage 3 receipt it kept")
        plans = {
            row["id"]: row for row in tracker.get("work_items", [])
            if row.get("stage") == SOURCE_STAGE and row.get("kind") in SOURCE_PLAN_KINDS
        }
        recorded = {row.get("item"): row for row in state.get("plans") or [] if isinstance(row, dict)}
        if set(recorded) != set(plans):
            errors.append(f"{SOURCE_STAGE} baseline plans differ from the stage's plan items")
        for item_id, row in sorted(recorded.items(), key=lambda pair: str(pair[0])):
            item = plans.get(item_id)
            if item is None:
                continue
            sha256 = str(row.get("plan_sha256"))
            if len(sha256) != 64 or not any(sha256 in str(text) for text in item.get("evidence") or []):
                errors.append(f"{item_id} evidence does not cite its baseline plan SHA-256")
            if item.get("kind") != DATA_RECONCILE_KIND:
                record_apply = (by_id.get(f"{item_id}-apply") or {}).get("source_apply") or {}
                if record_apply.get("plan_sha256") != sha256 or record_apply.get("owner_map_sha256") != row.get("owner_map_sha256"):
                    errors.append(f"{item_id}-apply record differs from the baseline plan and owner map")
        unresolved = (state.get("unresolved") or {}).get("count")
        if unresolved != sum(int(row.get("unresolved_count") or 0) for row in recorded.values()):
            errors.append(f"{SOURCE_STAGE} baseline unresolved count differs from its plans")
        deferred = state.get("deferrals") or {}
        if (
            deferred.get("sha256") != _digest(deferral_body(record.get("deferrals")))
            or deferred.get("artifact_count") != unresolved
            or deferred.get("artifact_count") != sum(len(row.get("artifacts") or []) for row in record.get("deferrals") or [])
        ):
            errors.append(f"{SOURCE_STAGE} baseline deferrals do not cover exactly its unresolved artifacts")
    for name in names:
        try:
            require_independent(str(name or ""), "reviewer or accepter", workers)
        except SocomError as failure:
            errors.append(f"{SOURCE_SEED_ID}: {failure}")
    return errors


def audit_baseline_files(root: Path, tracker: dict[str, Any], *, strict: bool) -> dict[str, Any]:
    """``audit source-baseline``: the recorded file-stage baseline against the workspace.

    The tracker checks always apply. Annotation edges under ``src/`` may change
    only through accepted stage 4 work, so a drift is an error. Plan files live
    under the disposable ``build/``: a missing one is reported as unavailable,
    and is an error with ``--strict``. A changed plan file is always an error.
    Later stages edit source bodies, so the applied files' digest is reported
    for information only.
    """

    errors = audit_source_gate(tracker)
    baseline = _stage_row(tracker, SOURCE_STAGE).get("baseline")
    if not isinstance(baseline, dict) or baseline.get("kind") != BASELINE_KIND or not isinstance(baseline.get("state"), dict):
        return {"ok": not errors, "recorded": False, "errors": errors}
    state = baseline["state"]
    unavailable: list[str] = []
    changed: list[str] = []
    for row in state.get("plans") or []:
        path = root / str(row.get("plan"))
        if not path.is_file():
            unavailable.append(str(row.get("plan")))
        elif sha256_file(path) != row.get("plan_sha256"):
            changed.append(str(row.get("plan")))
    if changed:
        errors.append(f"{len(changed)} accepted plan files changed after the gate: {_shown(changed)}")
    if unavailable and strict:
        errors.append(f"{len(unavailable)} accepted plan files are unavailable: {_shown(unavailable)}")
    parsed = source_artifacts(root)
    edges = sorted({(row["relation"], row["section"], row["artifact_id"], row["path"]) for row in parsed["artifacts"]})
    annotations = state.get("annotations") or {}
    if _digest([list(edge) for edge in edges]) != annotations.get("sha256"):
        errors.append(
            f"the @socom-artifact edges under src/ ({len(edges)}) differ from the baseline's "
            f"({annotations.get('edge_count')}): annotations change only through accepted {SOURCE_STAGE} work"
        )
    files = _applied_files(root, tracker)
    return {
        "ok": not errors,
        "recorded": True,
        "baseline_sha256": baseline.get("baseline_sha256"),
        "plan_count": len(state.get("plans") or []),
        "unavailable_plan_count": len(unavailable),
        "annotation_edge_count": len(edges),
        "unresolved_count": (state.get("unresolved") or {}).get("count"),
        "deferral_count": (state.get("deferrals") or {}).get("count"),
        "apply_files_unchanged": _digest(files) == (state.get("apply_files") or {}).get("sha256"),
        "errors": errors,
    }


def _applied_files(root: Path, tracker: dict[str, Any]) -> list[list[Any]]:
    """[path, current SHA-256 or None] of every file a stage 4 apply record names."""

    paths = sorted(
        {
            str(entry.get("path"))
            for item in _stage_items(tracker)
            if isinstance(item.get("source_apply"), dict)
            for entry in item["source_apply"].get("files") or []
            if isinstance(entry, dict)
        }
    )
    return [[path, sha256_file(root / path) if (root / path).is_file() else None] for path in paths]
