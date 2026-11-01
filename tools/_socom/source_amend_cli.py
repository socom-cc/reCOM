"""CLI handlers for stage 4 amendments (``source_amend.py``).

``progress amend-source-plan`` and ``progress accept-source-amendment``. The
registry rows and parser wiring live here so the main CLI only lists them;
handlers import the shared CLI helpers lazily to avoid an import cycle.
"""

from __future__ import annotations

import argparse
from typing import Any

from .source_plan_cli import DEFAULT_GRAPH


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "progress amend-source-plan",
            "progress",
            "Open a governed amendment on an accepted source-correlation plan or data reconcile after the stage gate: "
            "the item returns for revision and its apply (a reconcile's: the segment applies that wrote its "
            "annotations, plus --reapply) for re-apply, recorded in their review history; the stage stays accepted "
            "and records the open amendment.",
            mutates=True,
        ),
        spec(
            "progress accept-source-amendment",
            "progress",
            "Accept open source-correlation amendments once every amended plan and re-applied apply is accepted (an "
            "accepter independent of the opener and the amended items' workers): re-run every gate check with the "
            "deferrals in force and the live stage 3 receipt, and record the recomputed file baseline, keeping the "
            "previous one in baseline_history.",
            mutates=True,
            ghidra_requirement="required",
        ),
    )


def register(progress_commands: Any) -> None:
    amend = progress_commands.add_parser("amend-source-plan")
    amend.add_argument("--item", required=True)
    amend.add_argument("--by", required=True, help="who opens the amendment (not the item's handoff owner)")
    amend.add_argument("--reason", required=True)
    amend.add_argument("--evidence", action="append", required=True, help="repeatable; at least one")
    amend.add_argument(
        "--reapply",
        action="append",
        default=[],
        help="repeatable; a data reconcile amendment: a further segment apply whose files the revision annotates",
    )
    amend.add_argument("--expected-revision", type=int, required=True)
    amend.add_argument("--dry-run", action="store_true")
    amend.set_defaults(handler=_progress_amend_source_plan)

    accept = progress_commands.add_parser("accept-source-amendment")
    accept.add_argument("--amendment", action="append", required=True, help="repeatable; every open amendment")
    accept.add_argument("--accepter", required=True)
    accept.add_argument("--evidence", action="append", required=True, help="repeatable; at least one")
    accept.add_argument(
        "--deferrals", help="a socom-source-gate-deferrals file with new deferrals for rows the amendment leaves unresolved"
    )
    accept.add_argument("--expected-revision", type=int, required=True)
    accept.add_argument("--dry-run", action="store_true")
    accept.add_argument("--graph", default=DEFAULT_GRAPH)
    accept.add_argument("--check", action="store_true", help="regenerate the graph from support/socom.elf")
    accept.add_argument("--bridge-url")
    accept.set_defaults(handler=_progress_accept_source_amendment)


def _status(tracker: dict[str, Any], ids: list[str]) -> dict[str, str]:
    by_id = {row["id"]: row for row in tracker["work_items"]}
    return {item_id: by_id[item_id]["status"] for item_id in ids}


def _progress_amend_source_plan(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .source_amend import open_source_amendment
    from .source_gate_cli import _preview
    from .tracker import mutate

    root = _root(arguments)
    path = tracker_path(root)
    captured: dict[str, Any] = {}

    def operation(tracker: dict[str, Any]) -> None:
        captured.update(
            open_source_amendment(
                tracker, arguments.item, arguments.by, arguments.reason, arguments.evidence, arguments.reapply
            )
        )

    def summary(tracker: dict[str, Any]) -> dict[str, Any]:
        stage = next(row for row in tracker["stages"] if row["name"] == "source-correlation")
        return {
            **captured,
            "statuses": _status(tracker, [captured["work_item_id"], *captured["applies"]]),
            "stage_status": stage["status"],
        }

    if arguments.dry_run:
        preview, errors, revision = _preview(path, arguments.expected_revision, operation)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": revision,
               **summary(preview), "errors": errors})
        return 0 if not errors else 1
    updated = mutate(path, arguments.expected_revision, operation)
    write_snapshot(root, updated)
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"], **summary(updated)})
    return 0


def _progress_accept_source_amendment(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .source_amend import accept_source_amendment, check_amendment_accepter, deferral_delta
    from .source_gate import _refusal, live_stage3_receipt, preconditions, review_gate
    from .source_gate_cli import _deferrals, _inputs, _preview, _summary
    from .tracker import load_tracker, mutate, require_revision
    from .util import SocomError

    root = _root(arguments)
    path = tracker_path(root)
    tracker = load_tracker(path)
    require_revision(tracker, arguments.expected_revision)
    # Tracker-only refusals come before Ghidra is read.
    check_amendment_accepter(tracker, arguments.amendment, arguments.accepter)
    if problems := preconditions(tracker, lease_owner=None):
        raise SocomError(_refusal("the amendment acceptance", problems))
    added, added_problems = _deferrals(root, arguments.deferrals)
    receipt = live_stage3_receipt(root, tracker, bridge_url=arguments.bridge_url)
    if not receipt["ok"]:
        raise SocomError(f"the amendment acceptance refused: {receipt['error']}")
    inputs = _inputs(root, arguments)
    captured: dict[str, Any] = {}

    def operation(current: dict[str, Any]) -> None:
        delta = deferral_delta(root, current, arguments.amendment, added)
        review = review_gate(
            root, current, **inputs, deferrals=delta["deferrals"], deferral_problems=added_problems + delta["problems"],
            receipt=receipt, lease_owner=None,
        )
        captured["review"] = review
        captured["delta"] = delta
        captured["baseline"] = accept_source_amendment(
            current, arguments.amendment, arguments.accepter, arguments.evidence, review, delta
        )

    def summary() -> dict[str, Any]:
        delta = captured["delta"]
        return {
            **_summary(captured["review"]),
            "amendments": captured["baseline"]["amendments"],
            "previous_baseline_sha256": captured["baseline"]["previous_baseline_sha256"],
            "deferrals_resolved": len(delta["resolved"]),
            "deferrals_added": len(delta["added"]),
        }

    if arguments.dry_run:
        _preview_tracker, errors, revision = _preview(path, arguments.expected_revision, operation)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": revision,
               **summary(), "errors": errors})
        return 0 if not errors else 1
    updated = mutate(path, arguments.expected_revision, operation)
    write_snapshot(root, updated)
    stage = next(row for row in updated["stages"] if row["name"] == "source-correlation")
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"],
           "stage_status": stage["status"], **summary()})
    return 0
