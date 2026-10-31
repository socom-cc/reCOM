"""CLI handlers for the stage 4 apply route.

``source annotate``, ``source apply-check``, ``progress apply-source-plan``,
``progress open-capability-gate`` and ``progress reopen-source-plan`` (which
sends an accepted plan back for revision until its apply starts).  The
registry rows and parser wiring
live here so the main CLI only lists them; handlers import the shared CLI
helpers lazily to avoid an import cycle.
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
            "source annotate",
            "source",
            "Check (--check) or write (--write, under the apply item's lease) an accepted owner plan's generated "
            "@socom-artifact docblocks, and the accepted data reconciles' ones into a segment's files, only inside "
            "the apply's reserved directories.",
            mutates=True,
        ),
        spec(
            "source apply-check",
            "source",
            "Verify an applied source apply item read-only: the accepted plan is unchanged, every recorded file "
            "still has its SHA-256, moved-from and retired files are gone, paths lie in the reservation and the "
            "generated annotations have not drifted.",
        ),
        spec(
            "progress apply-source-plan",
            "progress",
            "Apply an accepted, unchanged owner plan under the apply item's lease: a segment's moves, creates, "
            "retired files and generated annotations inside its reservation; a provider's archive members in "
            "tracker evidence only; records the plan and file SHA-256s on the item.",
            mutates=True,
        ),
        spec(
            "progress open-capability-gate",
            "progress",
            "Accept a capability-gate work item once an active capability that opens it is registered.",
            mutates=True,
        ),
        spec(
            "progress reopen-source-plan",
            "progress",
            "Send an accepted stage 4 segment or provider plan back for revision with a reason and evidence, "
            "recorded in its review history; refused once its source apply or a data reconcile has started. "
            "The plan file is untouched.",
            mutates=True,
        ),
    )


def register(source_commands: Any, progress_commands: Any) -> None:
    annotate = source_commands.add_parser("annotate")
    annotate.add_argument("--plan", required=True)
    mode = annotate.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="report drift without writing")
    mode.add_argument("--write", action="store_true", help="write the generated docblocks")
    annotate.add_argument("--owner", help="lease owner of the plan's apply item (required with --write)")
    annotate.set_defaults(handler=_source_annotate)

    check = source_commands.add_parser("apply-check")
    check.add_argument("--item", required=True)
    check.set_defaults(handler=_source_apply_check)

    apply = progress_commands.add_parser("apply-source-plan")
    apply.add_argument("--item", required=True)
    apply.add_argument("--owner", required=True)
    apply.add_argument("--expected-revision", type=int, required=True)
    apply.add_argument("--graph", default=DEFAULT_GRAPH)
    apply.add_argument("--check", action="store_true", help="regenerate the graph from support/socom.elf")
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(handler=_progress_apply_source_plan)

    gate = progress_commands.add_parser("open-capability-gate")
    gate.add_argument("--item", required=True)
    gate.add_argument("--expected-revision", type=int, required=True)
    gate.add_argument("--dry-run", action="store_true")
    gate.set_defaults(handler=_progress_open_capability_gate)

    reopen = progress_commands.add_parser("reopen-source-plan")
    reopen.add_argument("--item", required=True)
    reopen.add_argument("--by", required=True, help="who sends the plan back (not its handoff owner)")
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--evidence", action="append", required=True, help="repeatable; at least one")
    reopen.add_argument("--expected-revision", type=int, required=True)
    reopen.add_argument("--dry-run", action="store_true")
    reopen.set_defaults(handler=_progress_reopen_source_plan)


def _plan_item_id(root: Path, value: str) -> str:
    from .source_plan import plan_path
    from .util import SocomError, load_json

    path = Path(value)
    path = path if path.is_absolute() else root / path
    plan = load_json(path)
    item_id = plan.get("work_item_id") if isinstance(plan, dict) else None
    if not isinstance(item_id, str):
        raise SocomError(f"{value} names no work item")
    expected = root / plan_path(item_id)
    if path.resolve() != expected.resolve():
        raise SocomError(f"the owner plan of {item_id} lives at {plan_path(item_id)}, not {value}")
    return item_id


def _source_annotate(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .locking import exclusive_state_lock
    from .source_apply import annotate
    from .tracker import load_tracker

    root = _root(arguments)
    item_id = _plan_item_id(root, arguments.plan)
    path = tracker_path(root)
    if arguments.write:
        # Writes under src/ are serialized with the apply route by the tracker lock.
        with exclusive_state_lock(path):
            report = annotate(root, load_tracker(path), item_id, write=True, owner=arguments.owner)
    else:
        report = annotate(root, load_tracker(path), item_id, write=False)
    _emit(report)
    return 0 if report["ok"] else 1


def _source_apply_check(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .source_apply import verify_source_apply
    from .tracker import load_tracker
    from .util import SocomError

    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    item = next((row for row in tracker["work_items"] if row["id"] == arguments.item), None)
    if item is None:
        raise SocomError(f"unknown work item: {arguments.item}")
    problems = verify_source_apply(root, tracker, item)
    record = item.get("source_apply") or {}
    _emit(
        {
            "ok": not problems,
            "mutation_performed": False,
            "work_item_id": arguments.item,
            "status": item.get("status"),
            "plan": record.get("plan"),
            "plan_sha256": record.get("plan_sha256"),
            "owner_map_sha256": record.get("owner_map_sha256"),
            "file_count": len(record.get("files") or []),
            "removed_count": len(record.get("removed") or []),
            "member_count": len(record.get("members") or []),
            "problems": problems,
        }
    )
    return 0 if not problems else 1


def _progress_apply_source_plan(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .source_apply import prepare_apply, record_apply
    from .source_plan import loaded_section_lookup
    from .source_plan_cli import _graph
    from .tracker import _iso, _utc_now, audit_tracker, load_tracker, mutate, refresh_ready_and_stages, require_revision

    root = _root(arguments)
    graph, origin = _graph(root, arguments)
    section_of = loaded_section_lookup(root)
    path = tracker_path(root)

    def summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            key: record.get(key)
            for key in (
                "plan",
                "plan_sha256",
                "owner_map_sha256",
                "annotations_sha256",
                "annotation_count",
                "reservation",
                "moves",
                "created",
                "retired",
                "files",
                "reconciles",
                "members",
                "changed",
            )
            if key in record
        }

    if arguments.dry_run:
        tracker = load_tracker(path)
        require_revision(tracker, arguments.expected_revision)
        record, _overlay = prepare_apply(root, tracker, arguments.item, arguments.owner, graph, section_of)
        preview = copy.deepcopy(tracker)
        record_apply(next(row for row in preview["work_items"] if row["id"] == arguments.item), record, _iso(_utc_now()))
        refresh_ready_and_stages(preview)
        preview["revision"] += 1
        errors = audit_tracker(preview, strict=True)
        _emit(
            {
                "ok": not errors,
                "dry_run": True,
                "mutation_performed": False,
                "revision": tracker["revision"],
                "graph": origin,
                "record": summary(record),
                "errors": errors,
            }
        )
        return 0 if not errors else 1

    state: dict[str, Any] = {}

    def operation(tracker: dict[str, Any]) -> None:
        record, overlay = prepare_apply(root, tracker, arguments.item, arguments.owner, graph, section_of)
        state["overlay"] = overlay
        state["backups"] = overlay.commit()
        item = next(row for row in tracker["work_items"] if row["id"] == arguments.item)
        record_apply(item, record, _iso(_utc_now()))
        state["record"] = item["source_apply"]

    try:
        updated = mutate(path, arguments.expected_revision, operation)
    except BaseException:
        # The tracker was not written: restore every file the apply changed.
        if "backups" in state:
            state["overlay"].rollback(state["backups"])
        raise
    write_snapshot(root, updated)
    _emit(
        {
            "ok": True,
            "dry_run": False,
            "mutation_performed": True,
            "revision": updated["revision"],
            "graph": origin,
            "record": summary(state["record"]),
        }
    )
    return 0


def _progress_open_capability_gate(arguments: argparse.Namespace) -> int:
    from .cli import _command_rows, _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .tracker import audit_tracker, load_tracker, mutate, open_capability_gate, refresh_ready_and_stages, require_revision

    root = _root(arguments)
    registered = {row["command"] for row in _command_rows()}
    path = tracker_path(root)
    captured: dict[str, Any] = {}

    def operation(tracker: dict[str, Any]) -> None:
        captured.update(open_capability_gate(tracker, arguments.item, registered))

    if arguments.dry_run:
        tracker = load_tracker(path)
        require_revision(tracker, arguments.expected_revision)
        preview = copy.deepcopy(tracker)
        operation(preview)
        refresh_ready_and_stages(preview)
        preview["revision"] += 1
        errors = audit_tracker(preview, strict=True)
        item = next(row for row in preview["work_items"] if row["id"] == arguments.item)
        _emit({"ok": not errors, "dry_run": True, "revision": tracker["revision"], "capability": captured["id"], "work_item": item, "errors": errors})
        return 0 if not errors else 1
    updated = mutate(path, arguments.expected_revision, operation)
    write_snapshot(root, updated)
    item = next(row for row in updated["work_items"] if row["id"] == arguments.item)
    _emit({"ok": True, "dry_run": False, "revision": updated["revision"], "capability": captured["id"], "work_item": item})
    return 0


def _progress_reopen_source_plan(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .tracker import audit_tracker, load_tracker, mutate, refresh_ready_and_stages, reopen_source_plan, require_revision

    root = _root(arguments)
    path = tracker_path(root)
    captured: dict[str, Any] = {}

    def operation(tracker: dict[str, Any]) -> None:
        captured.update(
            reopen_source_plan(tracker, arguments.item, arguments.by, arguments.reason, arguments.evidence)
        )

    def entry(tracker: dict[str, Any]) -> dict[str, Any]:
        item = next(row for row in tracker["work_items"] if row["id"] == arguments.item)
        return {"status": item["status"], "review_history_entry": (item.get("review_history") or [None])[-1]}

    if arguments.dry_run:
        tracker = load_tracker(path)
        require_revision(tracker, arguments.expected_revision)
        preview = copy.deepcopy(tracker)
        operation(preview)
        refresh_ready_and_stages(preview)
        preview["revision"] += 1
        errors = audit_tracker(preview, strict=True)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": tracker["revision"],
               **captured, **entry(preview), "errors": errors})
        return 0 if not errors else 1
    updated = mutate(path, arguments.expected_revision, operation)
    write_snapshot(root, updated)
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"],
           **captured, **entry(updated)})
    return 0
