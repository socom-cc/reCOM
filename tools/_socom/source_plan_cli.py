"""CLI handlers for stage 4 owner plans and the source query cache.

``source plan evidence``, ``source plan draft``, ``source plan validate``,
``source plan open``, ``source plan decide``, ``source plan emit-check`` and
``source sql``.  The registry rows and parser wiring live here so the main
CLI only lists them; handlers import the shared CLI helpers lazily to avoid
an import cycle.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

DEFAULT_GRAPH = "build/source-graph/graph.json"


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "source plan evidence",
            "source",
            "Write one source-correlation plan item's slice with its graph evidence and, with --skeleton, a plan "
            "listing every slice artifact unresolved.",
        ),
        spec(
            "source plan draft",
            "source",
            "Draft a source-owner plan (schema 2): every artifact the versioned rules decide gets an owner entry with "
            "its draft_rule, confidence and basis, the rest stay open for the planner; --check <plan> proves a plan's "
            "drafted rows equal what the rules it was drafted under give and lists the overrides and the owner and "
            "header-emit rows that differ from a fresh draft.",
        ),
        spec(
            "source plan validate",
            "source",
            "Check a source-owner plan: every artifact of its item's slice owned once or unresolved, owner (with "
            "name_basis for unnamed objects), provider, header-emit, contradiction and annotation rows, provisional "
            "files, no control characters, units agreeing with handed-off and accepted plans, and the graph and slice "
            "digests (--check regenerates the graph from the ELF); reports the other applies sharing each reserved "
            "directory; --output writes the full report under build/ and prints its counts.",
        ),
        spec(
            "source plan open",
            "source",
            "Print (or with --output write under build/) only a drafted source-owner plan's open rows compactly: open "
            "unresolved artifacts with their cache evidence, binding, flanking anchors and the WEAK copies between, the "
            "sole referencing unit of a WEAK or inline copy and the drafter's suggestion, then open owner rows, open "
            "header emits and an inferred reservation, so a planner never loads the whole plan.",
        ),
        spec(
            "source plan decide",
            "source",
            "Record one decision in a schema 2 source-owner plan under build/ as the holder of its item's lease "
            "(--lease-owner): move artifacts into an existing owner row with confidence and basis (copying the "
            "draft's open_row_header_emits row of an authored function), into unresolved with a reason, or by "
            "--accept-suggestion as the drafter suggested; add a contradictions row (outside the plan only in a file "
            "it owns) or header_emits row, replacing one with --override, or remove a contradiction; keeps "
            "hand-added empty owner rows; JSON load/dump, no control characters, drafted rows only with --override "
            "and --evidence; re-derives the annotations.",
            mutates=True,
        ),
        spec(
            "source plan emit-check",
            "source",
            "Read-only ODR header-emit check of one plan (--plan) or every plan under build/source-plans (--all): for "
            "each owned authored inline or WEAK copy (no thunks, no MSL), the units involved (holder, referencers, and "
            "vtable readers and constructor callers), the header emit the rulings expect (implicit special members, "
            "two or more units, authored template instances) with its header and line, missing 'no header declares' "
            "notes and emit rows citing a line that does not declare the class; --output writes the JSON under build/.",
        ),
        spec(
            "source sql",
            "source",
            "Run one read-only SELECT/WITH over build/cache/source-graph.sqlite, a derived cache of the source graph, "
            "its relocations, DWARF units and lines, LOCAL symbols, per-object LOCAL section runs and src/ files, "
            "rebuilt when its inputs change; ';' is accepted inside string literals and identifiers; --output writes "
            "the result under build/ and prints its row count.",
        ),
    )


def register(source_commands: Any) -> None:
    from .source_draft import RULES_VERSIONS

    plan = source_commands.add_parser("plan")
    plan_commands = plan.add_subparsers(dest="source_plan_command", required=True)
    evidence = plan_commands.add_parser("evidence")
    evidence.add_argument("--item", required=True)
    evidence.add_argument("--output", required=True)
    evidence.add_argument("--skeleton", help="also write a skeleton plan here (refused when the file exists)")
    evidence.add_argument("--graph", default=DEFAULT_GRAPH)
    evidence.add_argument("--check", action="store_true", help="regenerate the graph from support/socom.elf")
    evidence.set_defaults(handler=_source_plan_evidence)
    draft = plan_commands.add_parser("draft")
    draft.add_argument("--item")
    draft.add_argument("--output", help="the plan to write (refused when the file exists)")
    draft.add_argument("--check", metavar="PLAN", help="check a plan's drafted rows against a fresh draft")
    draft.add_argument("--rules", type=int, choices=RULES_VERSIONS, default=None)
    draft.add_argument("--graph", default=DEFAULT_GRAPH)
    draft.add_argument("--from-elf", action="store_true", help="regenerate the graph from support/socom.elf")
    draft.set_defaults(handler=_source_plan_draft)
    validate = plan_commands.add_parser("validate")
    validate.add_argument("--plan", required=True)
    validate.add_argument("--graph", default=DEFAULT_GRAPH)
    validate.add_argument("--check", action="store_true", help="regenerate the graph from support/socom.elf")
    validate.add_argument(
        "--fill-annotations",
        action="store_true",
        help="first rewrite the plan's annotations with the targets its owner and header-emit rows imply",
    )
    validate.add_argument("--output", help="write the full report (JSON) to this file under build/ and print its counts")
    validate.set_defaults(handler=_source_plan_validate)
    view = plan_commands.add_parser("open")
    view.add_argument("--plan", required=True)
    view.add_argument("--limit", type=int, default=40, help="open artifacts to show (default 40)")
    view.add_argument("--format", choices=("text", "json"), default="text")
    view.add_argument("--output", help="write the view (in --format) to this file under build/ instead of stdout")
    view.add_argument("--graph", default=DEFAULT_GRAPH)
    view.set_defaults(handler=_source_plan_open)
    emit = plan_commands.add_parser("emit-check")
    which = emit.add_mutually_exclusive_group(required=True)
    which.add_argument("--plan", action="append", help="a plan file (repeat for several)")
    which.add_argument("--all", action="store_true", help="every plan under build/source-plans/")
    emit.add_argument("--output", help="write the full report (JSON) to this file under build/ and print its counts")
    emit.add_argument("--graph", default=DEFAULT_GRAPH)
    emit.set_defaults(handler=_source_plan_emit_check)
    decide = plan_commands.add_parser("decide")
    decide.add_argument("--plan", required=True)
    decide.add_argument(
        "--lease-owner",
        required=True,
        help="the stable worker name holding the plan item's lease (progress work claim --owner)",
    )
    decide.add_argument("--artifact", action="append", required=True, help="repeat to decide several artifacts alike")
    decide.add_argument("--owner", help="an owner row: its translation unit, GNU object address, object or <library>:<object>")
    decide.add_argument("--confidence", choices=("high", "medium", "low"))
    decide.add_argument("--basis")
    decide.add_argument("--unresolved", metavar="REASON")
    decide.add_argument(
        "--accept-suggestion",
        action="store_true",
        help="record each open row's suggest {owner, rule, confidence, basis} as a hand entry of that owner row",
    )
    decide.add_argument(
        "--contradiction",
        metavar="KIND",
        help="add a contradictions row of this kind slug per artifact (with --override: replace its rows at that file and line)",
    )
    decide.add_argument(
        "--remove-contradiction",
        action="store_true",
        help="remove each artifact's contradictions rows at --provisional-file and --line",
    )
    decide.add_argument("--provisional-file", help="the provisional file a --contradiction disagrees with")
    decide.add_argument("--line", type=int, help="the --contradiction's line in that file (omit for a file-level one)")
    decide.add_argument("--elf-evidence", action="append", help="an ELF evidence line of the --contradiction (repeat)")
    decide.add_argument("--header-emit", metavar="HEADER", help="add a header_emits row per artifact: src/ header or <name>")
    decide.add_argument("--reason", choices=("template", "inline", "weak"), help="the --header-emit's reason")
    decide.add_argument("--library", help="the provider library of a <name> --header-emit")
    decide.add_argument("--emit-evidence", action="append", help="an evidence line of the --header-emit (repeat)")
    decide.add_argument(
        "--override",
        action="store_true",
        help="move an artifact a draft rule decided, or replace a header-emit or contradiction row",
    )
    decide.add_argument("--evidence", help="why the draft rule or row is wrong (with --override); kept as a plan note")
    decide.add_argument("--graph", default=DEFAULT_GRAPH)
    decide.set_defaults(handler=_source_plan_decide)
    sql = source_commands.add_parser("sql")
    sql.add_argument("statement")
    sql.add_argument("--limit", type=int, default=200)
    sql.add_argument("--format", choices=("text", "json"), default="text")
    sql.add_argument("--output", help="write the result (in --format) to this file under build/ instead of stdout")
    sql.add_argument("--graph", default=DEFAULT_GRAPH)
    sql.add_argument(
        "--from-elf", action="store_true", help="regenerate the graph from support/socom.elf (and rewrite --graph)"
    )
    sql.set_defaults(handler=_source_sql)


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _graph(root: Path, arguments: argparse.Namespace, regenerate: bool | None = None) -> tuple[dict[str, Any], str]:
    from .source_graph import source_graph
    from .util import SocomError, load_json

    if arguments.check if regenerate is None else regenerate:
        return source_graph(root), "regenerated from support/socom.elf"
    path = _path(root, arguments.graph)
    if not path.is_file():
        raise SocomError(
            f"{arguments.graph} does not exist: write it with `source graph --output {arguments.graph}` or regenerate it"
        )
    return load_json(path), arguments.graph


def _facts(root: Path, graph: dict[str, Any], graph_path: Path | None) -> dict[str, Any]:
    from .source_cache import ensure_source_cache, load_facts

    path, _rebuilt = ensure_source_cache(root, graph_path=graph_path, graph=graph)
    return load_facts(path)


def _source_plan_evidence(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .source_plan import plan_evidence, plan_skeleton
    from .tracker import load_tracker
    from .util import SocomError, atomic_write_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "source plan evidence")
    skeleton = _build_path(root, arguments.skeleton, "source plans") if arguments.skeleton else None
    if skeleton is not None and skeleton.exists():
        raise SocomError(f"{arguments.skeleton} exists; a skeleton never replaces a plan")
    tracker = load_tracker(tracker_path(root))
    graph, origin = _graph(root, arguments)
    evidence = plan_evidence(root, tracker, arguments.item, graph)
    atomic_write_json(output, evidence)
    if skeleton is not None:
        atomic_write_json(skeleton, plan_skeleton(tracker, arguments.item, graph))
    _emit(
        {
            "ok": True,
            "mutation_performed": False,
            "work_item_id": arguments.item,
            "graph": origin,
            "graph_sha256": graph["graph_sha256"],
            "slice_sha256": evidence["slice_sha256"],
            "artifact_count": evidence["artifact_count"],
            "output": arguments.output,
            "skeleton": arguments.skeleton,
        }
    )
    return 0


def _source_plan_draft(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .source_draft import DRAFT_RULES_VERSION, check_draft, draft_owner_plan, plan_rules_version
    from .source_plan import loaded_section_lookup
    from .tracker import load_tracker
    from .util import SocomError, atomic_write_json, load_json

    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    graph, origin = _graph(root, arguments, regenerate=arguments.from_elf)
    facts = _facts(root, graph, None if arguments.from_elf else _path(root, arguments.graph))
    section_of = loaded_section_lookup(root)
    if arguments.check:
        plan = load_json(_path(root, arguments.check))
        if not isinstance(plan, dict):
            raise SocomError(f"{arguments.check} is not a plan object")
        rules = arguments.rules if arguments.rules is not None else plan_rules_version(plan)
        fresh = draft_owner_plan(root, tracker, plan.get("work_item_id"), graph, facts, rules=rules, section_of=section_of)
        report = check_draft(fresh, plan)
        _emit(
            {
                "ok": not report["problems"],
                "mutation_performed": False,
                "plan": arguments.check,
                "graph": origin,
                "rules_version": rules,
                "plan_rules_version": (plan.get("draft") or {}).get("rules_version"),
                **report,
            }
        )
        return 0 if not report["problems"] else 1
    if not arguments.item or not arguments.output:
        raise SocomError("source plan draft needs --item and --output (or --check <plan>)")
    output = _build_path(root, arguments.output, "source plans")
    if output.exists():
        raise SocomError(f"{arguments.output} exists; a draft never replaces a plan")
    rules = arguments.rules if arguments.rules is not None else DRAFT_RULES_VERSION
    plan = draft_owner_plan(root, tracker, arguments.item, graph, facts, rules=rules, section_of=section_of)
    atomic_write_json(output, plan)
    draft = plan["draft"]
    _emit(
        {
            "ok": True,
            "mutation_performed": False,
            "output": arguments.output,
            "graph": origin,
            "rules_version": rules,
            "decided": draft["decided"],
            "open": draft["open"],
            "rules": draft["rules"],
            "open_owner_rows": draft["open_owner_rows"],
            "open_header_emits": len(draft["open_header_emits"]),
            "outside_reservation": draft["outside_reservation"],
            "reservation": plan.get("reservation"),
        }
    )
    return 0


def _source_plan_validate(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .source_plan import derive_annotations, loaded_section_lookup, validate_source_plan
    from .tracker import load_tracker
    from .util import atomic_write_json, load_json, sha256_file

    root = _root(arguments)
    output = _build_path(root, arguments.output, "source plan validate") if arguments.output else None
    plan_path = _path(root, arguments.plan)
    plan = load_json(plan_path)
    tracker = load_tracker(tracker_path(root))
    graph, origin = _graph(root, arguments)
    section_of = loaded_section_lookup(root)
    filled = False
    if arguments.fill_annotations and isinstance(plan, dict):
        target = _build_path(root, arguments.plan, "source plans")
        annotations = derive_annotations(plan, graph, section_of)
        if plan.get("annotations") != annotations:
            plan["annotations"] = annotations
            atomic_write_json(target, plan)
            filled = True
    from .source_apply import applied_state

    sha256 = sha256_file(plan_path)
    # Files the recorded applies moved, created and retired (this plan's own
    # apply only when it applied this plan file) are checked in their
    # applied state; without any apply record nothing changes.
    item_id = plan.get("work_item_id") if isinstance(plan, dict) else None
    applied = applied_state(tracker, str(item_id), sha256) if isinstance(item_id, str) else None
    apply = next((row for row in tracker.get("work_items", []) if row.get("id") == f"{item_id}-apply"), None)
    own = ((apply or {}).get("source_apply") or {}).get("plan_sha256") == sha256
    report = validate_source_plan(root, tracker, plan, graph, section_of=section_of, applied=applied)
    if isinstance(plan, dict) and isinstance(item_id, str) and report.get("summary"):
        # Non-blocking: the ODR header-emit check's counts and one review note.
        _emit_review(root, arguments, plan, plan_path, graph, report)
    result = {
        "ok": report["ok"],
        # --fill-annotations rewrites the plan file (under build/) when its annotations change.
        "mutation_performed": filled,
        "plan": arguments.plan,
        "sha256": sha256,
        "graph": origin,
        "graph_sha256": graph.get("graph_sha256"),
        "annotations_filled": filled,
        "applied": own,
        "reservation": report.get("reservation"),
        # For each reserved directory, the other segment applies that reserve it (they apply one at a time).
        "reservation_shared_with": report.get("reservation_shared_with"),
        # Units this plan shares with handed-off or accepted plans, and whether their paths agree.
        "shared_units": report.get("shared_units"),
        "summary": report["summary"],
        "review": report["review"],
        "problems": report["problems"],
    }
    if output is not None:
        # The full report is a disposable file under build/; the planner reads it in parts.
        atomic_write_json(output, result)
        kept = ("ok", "mutation_performed", "plan", "sha256", "graph", "annotations_filled", "applied", "summary")
        result = {key: result[key] for key in kept} | {
            "output": arguments.output,
            "problems": len(report["problems"]),
            "review": len(report["review"]),
        }
    _emit(result)
    return 0 if report["ok"] else 1


def _emit_review(
    root: Path, arguments: argparse.Namespace, plan: dict[str, Any], plan_path: Path, graph: dict[str, Any], report: dict[str, Any]
) -> None:
    """Add the plan's emit check (``source plan emit-check``) to a validate report: one review note and its counts."""

    import sqlite3

    from .source_cache import ensure_source_cache
    from .source_emit_check import emit_check, review_note
    from .util import SocomError

    item = str(plan["work_item_id"])
    try:
        relative = plan_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = arguments.plan
    try:
        graph_file = None if arguments.check else _path(root, arguments.graph)
        cache, _rebuilt = ensure_source_cache(root, graph_path=graph_file, graph=graph if graph_file is None else None)
        checked = emit_check(root, cache, items=[item], graph=graph, replace={item: (relative, plan)})["plans"][item]
    except (SocomError, OSError, sqlite3.Error, KeyError, ValueError) as failure:
        report["review"].append(f"emit check not run: {failure}")
        return
    counts = checked["counts"]
    report["summary"]["emit_check"] = {
        key: counts[key] for key in ("missing_emits", "missing_notes", "wrong_citations", "undetermined")
    }
    if note := review_note(checked, arguments.plan):
        report["review"].append(note)


def _source_plan_emit_check(arguments: argparse.Namespace) -> int:
    """The ODR header-emit check of plans, read-only."""

    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .source_emit_check import emit_check
    from .tracker import load_tracker
    from .util import SocomError, atomic_write_json, load_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "source plan emit-check") if arguments.output else None
    cache = _plan_cache(root, arguments)
    graph = load_json(_path(root, arguments.graph))
    tracker_file = tracker_path(root)
    statuses = (
        {str(row.get("id")): str(row.get("status")) for row in load_tracker(tracker_file).get("work_items") or []}
        if tracker_file.is_file() else None
    )
    items: list[str] | None = None
    replace: dict[str, tuple[str, dict[str, Any]]] = {}
    for value in arguments.plan or []:
        plan = load_json(_path(root, value))
        if not isinstance(plan, dict) or not isinstance(plan.get("work_item_id"), str):
            raise SocomError(f"{value} is not a source-owner plan with a work_item_id")
        replace[plan["work_item_id"]] = (value, plan)
    if arguments.plan:
        items = list(replace)
    report = emit_check(root, cache, items=items, graph=graph, replace=replace, statuses=statuses)
    if output is None:
        _emit({"ok": True, "mutation_performed": False, **report})
        return 0
    # The full report is a disposable file under build/ that the parent hands to sweep agents.
    atomic_write_json(output, report)
    _emit(
        {
            "ok": True,
            "mutation_performed": False,
            "output": arguments.output,
            "graph_sha256": report["graph_sha256"],
            "counts": report["counts"],
            "plans": {
                item: "{missing_emits} emits, {missing_notes} notes, {wrong_citations} citations".format(**result["counts"])
                for item, result in report["plans"].items()
                if any(result["counts"][key] for key in ("missing_emits", "missing_notes", "wrong_citations"))
            },
        }
    )
    return 0


def _plan_cache(root: Path, arguments: argparse.Namespace) -> Path:
    from .source_cache import ensure_source_cache
    from .util import SocomError

    graph_path = _path(root, arguments.graph)
    if not graph_path.is_file():
        raise SocomError(f"{arguments.graph} does not exist: write it with `source graph --output {arguments.graph}`")
    path, _rebuilt = ensure_source_cache(root, graph_path=graph_path)
    return path


def _source_plan_open(arguments: argparse.Namespace) -> int:
    """The open rows of a drafted plan, compactly."""

    from .cli import _build_path, _emit, _root
    from .source_plan_edit import cache_graph, open_text, open_view
    from .util import atomic_write_json, atomic_write_text, load_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "source plan open") if arguments.output else None
    plan = load_json(_path(root, arguments.plan))
    path = _plan_cache(root, arguments)
    view = open_view(plan, path, limit=arguments.limit)
    cached = cache_graph(path)
    view["cache_graph_sha256"] = cached
    note = None
    if cached != view["plan_graph_sha256"]:
        note = f"note: the cache holds graph {str(cached)[:12]}, the plan cites {str(view['plan_graph_sha256'])[:12]}"
    if output is not None:
        # A disposable view under build/: the planner reads it in parts instead of the whole plan.
        if arguments.format == "json":
            atomic_write_json(output, {"plan": arguments.plan, **view})
        else:
            atomic_write_text(output, (note + "\n" if note else "") + open_text(view))
        _emit(
            {
                "ok": True,
                "mutation_performed": False,
                "plan": arguments.plan,
                "output": arguments.output,
                "format": arguments.format,
                "open_rows": view["open_rows"],
                "shown": view["shown"],
                "note": note,
            }
        )
        return 0
    if arguments.format == "json":
        _emit({"ok": True, "mutation_performed": False, "plan": arguments.plan, **view})
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    if note:
        print(note)
    sys.stdout.write(open_text(view))
    return 0


DECISIONS = ("--owner", "--unresolved", "--accept-suggestion", "--contradiction", "--remove-contradiction", "--header-emit")


def _decision(arguments: argparse.Namespace) -> str:
    """The one decision a ``source plan decide`` call records; refuses options of another."""

    from .util import SocomError

    given = [
        flag
        for flag, value in zip(
            DECISIONS,
            (
                arguments.owner,
                arguments.unresolved,
                arguments.accept_suggestion or None,
                arguments.contradiction,
                arguments.remove_contradiction or None,
                arguments.header_emit,
            ),
        )
        if value is not None
    ]
    if len(given) != 1:
        raise SocomError(f"give exactly one of {', '.join(DECISIONS)} (with its options)")
    decision = given[0]
    contradiction = decision in ("--contradiction", "--remove-contradiction")
    stray = {
        "--confidence/--basis": (arguments.confidence, arguments.basis) if decision != "--owner" else (),
        "--provisional-file/--line": (arguments.provisional_file, arguments.line) if not contradiction else (),
        "--elf-evidence": (arguments.elf_evidence,) if decision != "--contradiction" else (),
        "--reason/--library/--emit-evidence": (arguments.reason, arguments.library, arguments.emit_evidence)
        if decision != "--header-emit"
        else (),
        "--override/--evidence": (arguments.override or None, arguments.evidence)
        if decision in ("--accept-suggestion", "--remove-contradiction")
        else (),
    }
    for flags, values in stray.items():
        if any(value is not None for value in values):
            raise SocomError(f"{flags} do not apply to {decision}")
    return decision


def _source_plan_decide(arguments: argparse.Namespace) -> int:
    """Record one decision in a plan file (JSON load/dump)."""

    from .cli import _build_path, _emit, _root
    from .source_plan import DRAFT_OPEN, loaded_section_lookup
    from .source_plan_edit import (
        accept_suggestions,
        add_contradictions,
        add_header_emits,
        cache_graph,
        cache_has_artifact,
        decide,
        refresh_annotations,
        remove_contradictions,
    )
    from .util import SocomError, atomic_write_json, load_json

    from .constants import tracker_path
    from .source_plan_edit import require_plan_lease
    from .tracker import load_tracker

    root = _root(arguments)
    target = _build_path(root, arguments.plan, "source plans")
    decision = _decision(arguments)
    plan = load_json(target)
    tracker_file = tracker_path(root)
    if not tracker_file.is_file():
        raise SocomError("source plan decide checks the item's lease in the tracker, which is missing")
    # Only the worker holding the plan item's lease edits its plan.
    require_plan_lease(load_tracker(tracker_file), plan.get("work_item_id") if isinstance(plan, dict) else None, arguments.lease_owner)
    graph_path = _path(root, arguments.graph)
    caches: list[Path] = []

    def cache() -> Path | None:
        """The query cache of --graph, built once and only when needed."""

        if not caches and graph_path.is_file():
            caches.append(_plan_cache(root, arguments))
        return caches[0] if caches else None

    def in_graph(identity: str) -> bool:
        path = cache()
        return path is not None and cache_has_artifact(path, identity)

    if decision == "--accept-suggestion":
        changes = accept_suggestions(plan, arguments.artifact)
    elif decision in ("--contradiction", "--remove-contradiction"):
        if not arguments.provisional_file:
            raise SocomError(f"{decision} needs --provisional-file")
        if decision == "--remove-contradiction":
            changes = remove_contradictions(plan, arguments.artifact, provisional_file=arguments.provisional_file, line=arguments.line)
        else:
            changes = add_contradictions(
                plan,
                arguments.artifact,
                kind=arguments.contradiction,
                provisional_file=arguments.provisional_file,
                line=arguments.line,
                elf_evidence=arguments.elf_evidence,
                root=root,
                in_graph=in_graph,
                override=arguments.override,
                override_evidence=arguments.evidence,
            )
    elif decision == "--header-emit":
        if not arguments.reason:
            raise SocomError("--header-emit needs --reason")
        changes = add_header_emits(
            plan,
            arguments.artifact,
            header=arguments.header_emit,
            reason=arguments.reason,
            evidence=arguments.emit_evidence,
            library=arguments.library,
            override=arguments.override,
            override_evidence=arguments.evidence,
        )
    else:
        changes = decide(
            plan,
            arguments.artifact,
            owner=arguments.owner,
            confidence=arguments.confidence,
            basis=arguments.basis,
            unresolved=arguments.unresolved,
            override=arguments.override,
            evidence=arguments.evidence,
        )
    annotations = "stale: run source plan validate --fill-annotations"
    path = cache()
    if path is not None:
        if cache_graph(path) == plan.get("graph_sha256"):
            refresh_annotations(plan, path, loaded_section_lookup(root))
            annotations = "re-derived"
    atomic_write_json(target, plan)
    _emit(
        {
            "ok": True,
            "mutation_performed": True,
            "plan": arguments.plan,
            "changes": changes,
            "annotations": annotations,
            "open_rows": sum(1 for row in plan.get("unresolved") or [] if isinstance(row, dict) and row.get("draft") == DRAFT_OPEN),
        }
    )
    return 0


def _source_sql(arguments: argparse.Namespace) -> int:
    """One read-only SELECT over build/cache/source-graph.sqlite, as compact text or JSON."""

    from .cli import _build_path, _emit, _root
    from .source_cache import ensure_source_cache, query
    from .util import atomic_write_json, atomic_write_text

    root = _root(arguments)
    output = _build_path(root, arguments.output, "source sql") if arguments.output else None
    graph_path = _path(root, arguments.graph)
    if arguments.from_elf or not graph_path.is_file():
        # The graph JSON is disposable build output: write it once for later queries.
        from .source_graph import source_graph

        graph = source_graph(root)
        atomic_write_json(_build_path(root, arguments.graph, "source graphs"), graph)
    path, rebuilt = ensure_source_cache(root, graph_path=graph_path)
    result = query(path, arguments.statement, arguments.limit)
    cache = path.relative_to(root).as_posix()
    if arguments.format == "json" and output is None:
        _emit({**result, "cache": cache, "rebuilt": rebuilt})
        return 0
    lines = ["\t".join(result["columns"])]
    lines.extend("\t".join("" if value is None else str(value) for value in row) for row in result["rows"])
    if result["truncated"]:
        lines.append(f"... (truncated at {arguments.limit} rows; use --limit)")
    if output is not None:
        # A disposable result under build/: a large answer stays out of the caller's context.
        if arguments.format == "json":
            atomic_write_json(output, {**result, "cache": cache, "rebuilt": rebuilt})
        else:
            atomic_write_text(output, "\n".join(lines) + "\n")
        _emit(
            {
                "ok": True,
                "mutation_performed": False,
                "output": arguments.output,
                "format": arguments.format,
                "columns": result["columns"],
                "rows": len(result["rows"]),
                "truncated": result["truncated"],
                "rebuilt": rebuilt,
            }
        )
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0
