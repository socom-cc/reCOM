"""CLI handlers for the stage 5 phase B skeleton route (``order_skeleton_route``).

``progress add-order-skeleton-prepare``, ``progress apply-order-skeleton``,
``progress handoff-order-skeleton`` and ``progress accept-order-skeleton``
change tracker state under its lock; ``order skeleton decide`` writes one
item's decisions file under the lock; ``order skeleton apply-check`` is
read-only (its render goes under ``build/``).  The main CLI lists the
registry rows and wires the parsers through ``specs`` and the ``register_*``
functions; handlers import the shared CLI helpers lazily.
"""

from __future__ import annotations

import argparse
import copy
from typing import Any

MANIFEST = "build/stage5/skeleton-manifest.json"
SNAPSHOT = "build/stage5/provisional-bodies.json"


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "progress add-order-skeleton-prepare",
            "progress",
            "Stage 5 phase B (BD3), once and before any skeleton apply: from a whole-tree render of the current skeleton "
            "inputs, add socom:work:order-skeleton-prepare (depends on the skeleton route gate, the link plan and every "
            "accepted order plan; reserves every header the writer changes or creates, the headers a waiting by-value type "
            "would be defined in, the holding files and the orphan deletions) and make each order-segment-NNN-apply depend "
            "on it with its resources narrowed from its directories to its units' files; the plan items and their "
            "acceptances are untouched; the decomposition records the reservations' digest.",
            mutates=True,
        ),
        spec(
            "progress apply-order-skeleton",
            "progress",
            "Write one stage 5 skeleton item's files under src/ under its lease (the prepare: headers, holding files, "
            "orphan deletions; a segment apply: its unit files with their include regions): the first write freezes the "
            "base src/ under build/stage5/skeleton-route/base; every apply renders the whole tree from it (with every "
            "item's decisions), runs the static checks (determinism, S1-S5, S7) over the render, refuses stale inputs "
            "(plan SHA-256s, stage 4 baseline, manifest, snapshot, base), a render that touches a file no skeleton item "
            "reserves or another applied item's file, and own files changed outside the route, then writes its files and "
            "records per-file before/after SHA-256s (LF-normalized), stage 4 block digests, the write and manifest "
            "digests, flags by kind, the derived local-static order conflicts and the waiting rows; a re-apply replaces "
            "the record (the review history keeps it); --dry-run writes nothing under src/ or the tracker.",
            mutates=True,
        ),
        spec(
            "progress handoff-order-skeleton",
            "progress",
            "Hand off an applied stage 5 skeleton item (the lease owner): re-runs order skeleton apply-check and cites the "
            "record's SHA-256; generic progress work handoff refuses these items.",
            mutates=True,
        ),
        spec(
            "progress accept-order-skeleton",
            "progress",
            "Accept a handed-off stage 5 skeleton item as an independent socom-verifier (never a worker of any skeleton "
            "item, never a tool maintainer): re-runs order skeleton apply-check against the record its handoff cited; "
            "generic progress work accept refuses these items.",
            mutates=True,
        ),
        spec(
            "order skeleton decide",
            "order",
            "Settle one waiting skeleton row as the holder of the item's lease, in the item's decisions file "
            "build/stage5/skeleton-decisions/<item>.json that the writer reads: a by-value type without a usable record "
            "(--type, its complete definition), an overload tie (--body, the candidate the body goes to), a local static or "
            "function-local class without an owner (--owner, an out-of-line function of the unit) or an initializer the "
            "ELF bytes cannot render (--initializer); each with its --basis. A row lands in one item's files and is "
            "decided under that item; an undecided row stays waiting and flagged.",
            mutates=True,
        ),
        spec(
            "order skeleton apply-check",
            "order",
            "Read-only check of an applied stage 5 skeleton item: its inputs are not stale (plans, stage 4 baseline, "
            "manifest, snapshot, frozen base, its decisions file), a fresh render from the base passes every static check "
            "and reproduces the recorded write of each of its files, and src/ holds exactly the recorded after-content with "
            "unchanged stage 4 blocks; the render goes under build/stage5/skeleton-route/check/.",
        ),
    )


def register_progress(progress_commands: Any) -> None:
    prepare = progress_commands.add_parser("add-order-skeleton-prepare")
    prepare.add_argument("--expected-revision", type=int, required=True)
    _inputs(prepare)
    prepare.add_argument("--dry-run", action="store_true")
    prepare.set_defaults(handler=_progress_add_prepare)

    apply = progress_commands.add_parser("apply-order-skeleton")
    apply.add_argument("--item", required=True, help=f"socom:work:order-skeleton-prepare or socom:work:order-segment-NNN-apply")
    apply.add_argument("--owner", required=True, help="the lease owner")
    apply.add_argument("--expected-revision", type=int, required=True)
    _inputs(apply)
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(handler=_progress_apply)

    handoff = progress_commands.add_parser("handoff-order-skeleton")
    handoff.add_argument("--item", required=True)
    handoff.add_argument("--owner", required=True)
    handoff.add_argument("--summary", required=True)
    handoff.add_argument("--evidence", action="append", default=[])
    handoff.add_argument("--expected-revision", type=int, required=True)
    _inputs(handoff)
    handoff.add_argument("--dry-run", action="store_true")
    handoff.set_defaults(handler=_progress_handoff)

    accept = progress_commands.add_parser("accept-order-skeleton")
    accept.add_argument("--item", required=True)
    accept.add_argument("--accepter", required=True, help="an independent socom-verifier")
    accept.add_argument("--evidence", action="append", required=True)
    accept.add_argument("--expected-revision", type=int, required=True)
    _inputs(accept)
    accept.add_argument("--dry-run", action="store_true")
    accept.set_defaults(handler=_progress_accept)


def register_skeleton(skeleton_commands: Any) -> None:
    decide = skeleton_commands.add_parser("decide")
    decide.add_argument("--item", required=True, help="the skeleton item whose files the row lands in")
    decide.add_argument("--lease-owner", required=True)
    decide.add_argument("--artifact", required=True, help="the waiting row's key (artifact, body id or the type's mangled name)")
    value = decide.add_mutually_exclusive_group(required=True)
    value.add_argument("--type", dest="type_text", help="the complete definition of a by-value type without a usable record")
    value.add_argument("--owner", dest="owner_name", help="the mangled name of the owning out-of-line function")
    value.add_argument("--body", dest="body_name", help="the mangled name of the overload candidate the body goes to")
    value.add_argument("--initializer", dest="initializer_text", help="the initializer text after '='")
    decide.add_argument("--basis", required=True)
    _inputs(decide)
    decide.set_defaults(handler=_order_skeleton_decide)

    check = skeleton_commands.add_parser("apply-check")
    check.add_argument("--item", required=True)
    _inputs(check)
    check.add_argument("--output", help="write the full report as JSON under build/")
    check.set_defaults(handler=_order_skeleton_apply_check)


def _inputs(parser: Any) -> None:
    parser.add_argument("--manifest", default=MANIFEST, help="the skeleton manifest under build/")
    parser.add_argument("--snapshot", default=SNAPSHOT, help="the frozen body snapshot under build/")


def _paths(root: Any, arguments: argparse.Namespace) -> dict[str, Any]:
    from .cli import _build_path

    return {"manifest_path": _build_path(root, arguments.manifest, "skeleton manifests"),
            "snapshot_path": _build_path(root, arguments.snapshot, "body snapshots")}


def _dry(tracker: dict[str, Any], revision: int, operation: Any) -> tuple[dict[str, Any], list[str]]:
    from .tracker import audit_tracker, refresh_ready_and_stages, require_revision

    require_revision(tracker, revision)
    preview = copy.deepcopy(tracker)
    operation(preview)
    refresh_ready_and_stages(preview)
    preview["revision"] += 1
    return preview, audit_tracker(preview, strict=True)


def _item(tracker: dict[str, Any], item_id: str) -> dict[str, Any]:
    return next(row for row in tracker["work_items"] if row["id"] == item_id)


def _progress_add_prepare(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .order_plan import ORDER_SKELETON_PREPARE_ID, add_skeleton_prepare
    from .order_skeleton_route import prepare_reservations, route_inputs, started
    from .order_skeleton_write import render_skeletons
    from .snapshot import write_snapshot
    from .tracker import load_tracker, mutate
    from .util import SocomError

    root = _root(arguments)
    paths = _paths(root, arguments)
    captured: dict[str, Any] = {}

    def operation(tracker: dict[str, Any]) -> None:
        if started(tracker):
            raise SocomError("skeleton items have written src/ already: the reservations are set once, before any apply")
        inputs, _base = route_inputs(root, tracker, **paths)
        rendered = render_skeletons(inputs, segment=None)
        prepare_files, unit_files, counts = prepare_reservations(rendered, inputs)
        captured["record"] = add_skeleton_prepare(
            tracker, prepare_files=prepare_files, unit_files=unit_files, manifest_sha256=inputs.manifest["manifest_sha256"],
            write_sha256=rendered["manifest"]["write_sha256"], counts=counts,
        )
        captured["counts"] = counts

    def shown(tracker: dict[str, Any]) -> dict[str, Any]:
        item = _item(tracker, ORDER_SKELETON_PREPARE_ID)
        return {"prepare": {key: item.get(key) for key in ("id", "status", "dependencies")}, "prepare_files": len(item["resources"]),
                "counts": captured.get("counts"), "record": captured.get("record")}

    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        preview, errors = _dry(tracker, arguments.expected_revision, operation)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": tracker["revision"],
               **shown(preview), "errors": errors})
        return 0 if not errors else 1
    updated = mutate(tracker_path(root), arguments.expected_revision, operation)
    write_snapshot(root, updated)
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"], **shown(updated)})
    return 0


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    keep = ("item", "write_sha256", "files_sha256", "changed", "check", "entries", "regions", "flags", "known_conflicts",
            "waiting_by_kind", "decisions")
    shown = {key: record.get(key) for key in keep}
    shown["inputs"] = {key: value for key, value in record["inputs"].items() if key not in ("plans",)}
    shown["file_count"] = len(record["files"])
    shown["changed_count"] = len(record["changed"])
    shown["changed"] = record["changed"][:20]
    return shown


def _progress_apply(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .order_skeleton_route import commit_changes, prepare_skeleton_apply, record_skeleton, rollback_changes
    from .snapshot import write_snapshot
    from .tracker import _iso, _utc_now, load_tracker, mutate

    root = _root(arguments)
    paths = _paths(root, arguments)
    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        captured: dict[str, Any] = {}

        def preview_operation(preview: dict[str, Any]) -> None:
            record, changes = prepare_skeleton_apply(root, preview, arguments.item, arguments.owner, write=False, **paths)
            record_skeleton(_item(preview, arguments.item), record, _iso(_utc_now()))
            captured["record"] = record

        _preview, errors = _dry(tracker, arguments.expected_revision, preview_operation)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": tracker["revision"],
               "record": _summary(captured["record"]), "waiting": captured["record"]["waiting"], "errors": errors})
        return 0 if not errors else 1
    state: dict[str, Any] = {}

    def operation(tracker: dict[str, Any]) -> None:
        record, changes = prepare_skeleton_apply(root, tracker, arguments.item, arguments.owner, write=True, **paths)
        state["backups"] = commit_changes(root, changes)
        record_skeleton(_item(tracker, arguments.item), record, _iso(_utc_now()))
        state["record"] = record

    try:
        updated = mutate(tracker_path(root), arguments.expected_revision, operation)
    except BaseException:
        # The tracker was not written: restore every file the apply changed.
        if "backups" in state:
            rollback_changes(root, state["backups"])
        raise
    write_snapshot(root, updated)
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"],
           "record": _summary(state["record"]), "waiting": state["record"]["waiting"]})
    return 0


def _progress_handoff(arguments: argparse.Namespace) -> int:
    return _review(arguments, handoff=True)


def _progress_accept(arguments: argparse.Namespace) -> int:
    return _review(arguments, handoff=False)


def _review(arguments: argparse.Namespace, *, handoff: bool) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .order_skeleton_route import accept_skeleton, check_accepter, check_handoff, handoff_skeleton, verify_skeleton
    from .snapshot import write_snapshot
    from .tracker import load_tracker, mutate

    root = _root(arguments)
    paths = _paths(root, arguments)
    captured: dict[str, Any] = {}

    def operation(tracker: dict[str, Any]) -> None:
        # The lease or the accepter's independence first: the apply-check takes a render and every static check.
        if handoff:
            check_handoff(tracker, arguments.item, arguments.owner)
        else:
            check_accepter(tracker, arguments.item, arguments.accepter)
        report = verify_skeleton(root, tracker, arguments.item, **paths)
        captured["report"] = report
        if handoff:
            handoff_skeleton(tracker, arguments.item, arguments.owner, arguments.summary, arguments.evidence, report)
        else:
            accept_skeleton(tracker, arguments.item, arguments.accepter, arguments.evidence, report)

    def shown(tracker: dict[str, Any]) -> dict[str, Any]:
        item = _item(tracker, arguments.item)
        report = captured["report"]
        return {"work_item": {key: item.get(key) for key in ("id", "status", "handoff", "accepted")},
                "apply_check": {key: report.get(key) for key in ("ok", "record_sha256", "write_sha256", "file_count", "check", "problems")}}

    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        preview, errors = _dry(tracker, arguments.expected_revision, operation)
        _emit({"ok": not errors, "dry_run": True, "mutation_performed": False, "revision": tracker["revision"],
               **shown(preview), "errors": errors})
        return 0 if not errors else 1
    updated = mutate(tracker_path(root), arguments.expected_revision, operation)
    write_snapshot(root, updated)
    _emit({"ok": True, "dry_run": False, "mutation_performed": True, "revision": updated["revision"], **shown(updated)})
    return 0


def _order_skeleton_decide(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .locking import exclusive_state_lock
    from .order_skeleton_route import decide
    from .tracker import load_tracker

    root = _root(arguments)
    paths = _paths(root, arguments)
    option, value = next((name, text) for name, text in (
        ("type", arguments.type_text), ("owner", arguments.owner_name), ("body", arguments.body_name),
        ("initializer", arguments.initializer_text)) if text is not None)
    path = tracker_path(root)
    # The decisions file is a route input: it is written under the tracker lock, like the route's own writes.
    with exclusive_state_lock(path):
        report = decide(root, load_tracker(path), arguments.item, arguments.lease_owner, arguments.artifact, option, value,
                        arguments.basis, **paths)
    _emit(report)
    return 0


def _order_skeleton_apply_check(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_skeleton_route import verify_skeleton
    from .tracker import load_tracker
    from .util import atomic_write_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "apply-check reports") if arguments.output else None
    report = verify_skeleton(root, load_tracker(tracker_path(root)), arguments.item, **_paths(root, arguments))
    if output is not None:
        atomic_write_json(output, report)
    _emit({**report, "output": arguments.output})
    return 0 if report["ok"] else 1
