"""CLI handlers for the stage 4 gate route (``source_gate.py``).

``source gate-check``, ``progress handoff-source-gate``,
``progress accept-source-gate`` and ``audit source-baseline``. The registry
rows and parser wiring live here so the main CLI only lists them; handlers
import the shared CLI helpers lazily to avoid an import cycle.
"""

from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

from .source_plan_cli import DEFAULT_GRAPH


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "source gate-check",
            "source",
            "Run every source-correlation gate check read-only: accepted items, no leases or blockers, strict "
            "audits, plan validation, apply records, annotation drift, cross-plan unit consistency, completeness, "
            "the live stage 3 receipt; list every unresolved artifact with its deferral.",
            ghidra_requirement="optional",
        ),
        spec(
            "progress handoff-source-gate",
            "progress",
            "Hand off the source-correlation stage gate under its lease (an independent reviewer): re-run every gate "
            "check with a deferral file and record the deferrals and the candidate file-stage baseline.",
            mutates=True,
            ghidra_requirement="required",
        ),
        spec(
            "progress accept-source-gate",
            "progress",
            "Accept the source-correlation stage gate (an accepter independent of its reviewer): re-run every gate "
            "check with the recorded deferrals, require the reviewed baseline digest and record the file-stage "
            "baseline on the stage.",
            mutates=True,
            ghidra_requirement="required",
        ),
        spec(
            "audit source-baseline",
            "audit",
            "Check the recorded source-correlation file-stage baseline: its tracker record, the plan files and the "
            "@socom-artifact edges under src/.",
        ),
    )


def register(source_commands: Any, progress_commands: Any, audit_commands: Any) -> None:
    def common(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--graph", default=DEFAULT_GRAPH)
        parser.add_argument("--check", action="store_true", help="regenerate the graph from support/socom.elf")
        parser.add_argument("--bridge-url")

    check = source_commands.add_parser("gate-check")
    check.add_argument("--deferrals", help="a socom-source-gate-deferrals file")
    check.add_argument("--output", default="build/closeout-source-correlation/gate-check.json")
    check.add_argument("--skip-receipt", action="store_true", help="do not read Ghidra (the check then fails)")
    common(check)
    check.set_defaults(handler=_source_gate_check)

    handoff = progress_commands.add_parser("handoff-source-gate")
    handoff.add_argument("--item", required=True)
    handoff.add_argument("--owner", required=True)
    handoff.add_argument("--summary", required=True)
    handoff.add_argument("--deferrals", help="a socom-source-gate-deferrals file (needed when rows are unresolved)")
    handoff.add_argument("--evidence", action="append", default=[])
    handoff.add_argument("--expected-revision", type=int, required=True)
    handoff.add_argument("--dry-run", action="store_true")
    common(handoff)
    handoff.set_defaults(handler=_progress_handoff_source_gate)

    accept = progress_commands.add_parser("accept-source-gate")
    accept.add_argument("--item", required=True)
    accept.add_argument("--accepter", required=True)
    accept.add_argument("--evidence", action="append", required=True, help="repeatable; at least one")
    accept.add_argument("--expected-revision", type=int, required=True)
    accept.add_argument("--dry-run", action="store_true")
    common(accept)
    accept.set_defaults(handler=_progress_accept_source_gate)

    baseline = audit_commands.add_parser("source-baseline")
    baseline.add_argument("--strict", action="store_true", help="a missing plan file is an error")
    baseline.set_defaults(handler=_audit_source_baseline)


def _inputs(root: Path, arguments: argparse.Namespace) -> dict[str, Any]:
    """The graph, section lookup, issue ledger and census every review reads."""

    from .issues import issue_path, load_issues
    from .source_plan import loaded_section_lookup
    from .source_plan_cli import _graph
    from .util import load_json

    graph, origin = _graph(root, arguments)
    census = root / ".agent" / "REFERENCE_CENSUS.json"
    return {
        "graph": graph,
        "graph_origin": origin,
        "section_of": loaded_section_lookup(root),
        "issues": load_issues(root) if issue_path(root).is_file() else None,
        "census": load_json(census) if census.is_file() else None,
    }


def _deferrals(root: Path, value: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    from .source_gate import normalize_deferrals
    from .util import SocomError, load_json

    if not value:
        return [], []
    path = Path(value)
    path = path if path.is_absolute() else root / path
    if not path.is_file():
        raise SocomError(f"{value} does not exist")
    return normalize_deferrals(load_json(path))


def _summary(review: dict[str, Any]) -> dict[str, Any]:
    from .source_gate import _REFUSAL_SHOWN

    receipt = review["receipt"]
    return {
        "counts": review["counts"],
        "problems": review["problems"][:_REFUSAL_SHOWN],
        "baseline_sha256": review["baseline_sha256"],
        "receipt": {key: receipt.get(key) for key in ("ok", "receipt_sha256", "baseline_receipt_sha256", "error")},
        "graph": review["graph"],
    }


def _source_gate_check(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .source_gate import SOURCE_SEED_ID, live_stage3_receipt, review_gate, skipped_receipt
    from .tracker import load_tracker
    from .util import atomic_write_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "gate-check reports")
    tracker = load_tracker(tracker_path(root))
    deferrals, deferral_problems = _deferrals(root, arguments.deferrals)
    receipt = (
        skipped_receipt(tracker)
        if arguments.skip_receipt
        else live_stage3_receipt(root, tracker, bridge_url=arguments.bridge_url)
    )
    gate = next((row for row in tracker["work_items"] if row["id"] == SOURCE_SEED_ID), {})
    lease = gate.get("lease") if isinstance(gate.get("lease"), dict) else {}
    review = review_gate(
        root,
        tracker,
        **_inputs(root, arguments),
        deferrals=deferrals,
        deferral_problems=deferral_problems,
        receipt=receipt,
        lease_owner=lease.get("owner"),
    )
    atomic_write_json(output, {"kind": "socom-source-gate-check", "schema_version": 1, "revision": tracker["revision"], **review})
    _emit(
        {
            "ok": review["ok"],
            "mutation_performed": False,
            "revision": tracker["revision"],
            **_summary(review),
            "output": output.relative_to(root).as_posix(),
        }
    )
    return 0 if review["ok"] else 1


def _preview(path: Path, expected: int, operation: Any) -> tuple[dict[str, Any], list[str], int]:
    from .tracker import audit_tracker, load_tracker, refresh_ready_and_stages, require_revision

    tracker = load_tracker(path)
    require_revision(tracker, expected)
    preview = copy.deepcopy(tracker)
    operation(preview)
    refresh_ready_and_stages(preview)
    preview["revision"] += 1
    return preview, audit_tracker(preview, strict=True), tracker["revision"]


def _progress_handoff_source_gate(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .source_gate import _refusal, check_reviewer, handoff_source_gate, live_stage3_receipt, preconditions, review_gate
    from .tracker import load_tracker, mutate, require_revision
    from .util import SocomError

    root = _root(arguments)
    path = tracker_path(root)
    tracker = load_tracker(path)
    require_revision(tracker, arguments.expected_revision)
    # Tracker-only refusals come before Ghidra is read.
    check_reviewer(tracker, arguments.item, arguments.owner)
    if problems := preconditions(tracker, lease_owner=arguments.owner):
        raise SocomError(_refusal("the gate handoff", problems))
    deferrals, deferral_problems = _deferrals(root, arguments.deferrals)
    receipt = live_stage3_receipt(root, tracker, bridge_url=arguments.bridge_url)
    if not receipt["ok"]:
        raise SocomError(f"the gate handoff refused: {receipt['error']}")
    inputs = _inputs(root, arguments)
    captured: dict[str, Any] = {}

    def operation(current: dict[str, Any]) -> None:
        review = review_gate(
            root, current, **inputs, deferrals=deferrals, deferral_problems=deferral_problems,
            receipt=receipt, lease_owner=arguments.owner,
        )
        captured["review"] = review
        captured["record"] = handoff_source_gate(
            current, arguments.item, arguments.owner, arguments.summary, arguments.evidence, review
        )

    if arguments.dry_run:
        preview, errors, revision = _preview(path, arguments.expected_revision, operation)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": revision,
               **_summary(captured["review"]), "errors": errors})
        return 0 if not errors else 1
    updated = mutate(path, arguments.expected_revision, operation)
    write_snapshot(root, updated)
    item = next(row for row in updated["work_items"] if row["id"] == arguments.item)
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"],
           "status": item["status"], **_summary(captured["review"])})
    return 0


def _progress_accept_source_gate(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .source_gate import _refusal, accept_source_gate, check_accepter, live_stage3_receipt, preconditions, review_gate
    from .tracker import load_tracker, mutate, require_revision
    from .util import SocomError

    root = _root(arguments)
    path = tracker_path(root)
    tracker = load_tracker(path)
    require_revision(tracker, arguments.expected_revision)
    record, _name = check_accepter(tracker, arguments.item, arguments.accepter)
    if problems := preconditions(tracker, lease_owner=None):
        raise SocomError(_refusal("the gate acceptance", problems))
    receipt = live_stage3_receipt(root, tracker, bridge_url=arguments.bridge_url)
    if not receipt["ok"]:
        raise SocomError(f"the gate acceptance refused: {receipt['error']}")
    inputs = _inputs(root, arguments)
    # The accepter re-checks the deferrals the reviewer recorded, not a file.
    deferrals = copy.deepcopy(record.get("deferrals") or [])
    captured: dict[str, Any] = {}

    def operation(current: dict[str, Any]) -> None:
        review = review_gate(
            root, current, **inputs, deferrals=deferrals, deferral_problems=[], receipt=receipt, lease_owner=None
        )
        captured["review"] = review
        captured["baseline"] = accept_source_gate(current, arguments.item, arguments.accepter, arguments.evidence, review)

    if arguments.dry_run:
        preview, errors, revision = _preview(path, arguments.expected_revision, operation)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": revision,
               **_summary(captured["review"]), "errors": errors})
        return 0 if not errors else 1
    updated = mutate(path, arguments.expected_revision, operation)
    write_snapshot(root, updated)
    stage = next(row for row in updated["stages"] if row["name"] == "source-correlation")
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"],
           "stage_status": stage["status"], **_summary(captured["review"])})
    return 0


def _audit_source_baseline(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .source_gate import audit_baseline_files
    from .tracker import load_tracker

    root = _root(arguments)
    report = audit_baseline_files(root, load_tracker(tracker_path(root)), strict=arguments.strict)
    _emit({"audit": "source-baseline", **report})
    return 0 if report["ok"] else 1
