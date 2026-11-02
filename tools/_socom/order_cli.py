"""CLI handlers for stage 5 (authored-function-order) phase A.

``order target``, ``order link-spec``, ``order draft`` and ``order sql``:
read-only commands over the accepted stage 4 owner plans, the source graph
and the reference ELF (``order draft`` also reads the source cache).
``order plan draft``, ``order plan decide`` and ``order plan validate``
write and check the order plans of the stage 5 items (``order_plan``).
Outputs go under ``build/`` only; the main CLI lists the registry rows and
wires the parser through ``specs`` and ``register``.
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
            "order target",
            "order",
            "Read-only stage 5 order target from the accepted stage 4 owner plans, the source graph (stage 4's "
            "decomposition graph) and the ELF: for every authored unit (owner rows merged across plans) its owned "
            "artifacts in address order per output-section region with an order class (definition, copy, literal, "
            "compiler-generated fill), runs and strays, the deferred rows inside its runs with their gate deferral, "
            "and the global object order (authored units and opaque provider objects) checked per region against "
            ".text; a deterministic order_sha256; --unit or --segment selects units, --output writes the JSON under "
            "build/ and prints its counts.",
        ),
        spec(
            "order link-spec",
            "order",
            "Write the link-order specification (socom-link-order JSON: objects in order with their source path or "
            "archive member, and a plain text list) derived from the order target, checked statically against the "
            "ELF: every object's contribution to every region must follow this order (COMMON allocations excepted); "
            "prints the counts and the violations.",
        ),
        spec(
            "order draft",
            "order",
            "Read-only stage 5 source-order evidence draft over the order target: per authored unit the evidence for "
            "the source order of its definitions (DWARF lines, the local-static counter name$N/init$N, private literal "
            "labels @N, the static initializer's order, DWARF variable order) as pairwise constraints, a hypothesis "
            "source order of its functions and of its data per region with every adjacency classed proven, "
            "constrained or hypothesis, and the definitions without a source position; plus the calibration of each "
            "evidence against the DWARF source order and the emission rule it supports. Reads the source cache; "
            "--unit or --segment selects units, --output writes the JSON under build/ and prints its counts.",
        ),
        spec(
            "order sql",
            "order",
            "Run one read-only SELECT/WITH over build/cache/order-target.sqlite (regions, objects, contributions, "
            "targets, findings, checks), a derived cache of the order target rebuilt when the graph file, the cited "
            "plans or the gate deferrals change; --output writes the result under build/ and prints its row count.",
        ),
        spec(
            "order plan draft",
            "order",
            "Draft the order plan of a stage 5 plan item at its packet path under build/order-plans/ (socom-order-plan: "
            "per unit of the segment the source order of its definitions, function rows with a position and an "
            "in_class flag, data rows per region in declaration order, each classed proven, constrained or hypothesis "
            "with its basis and evidence, the definitions without a source position, copies and literals as stage 7 "
            "targets, and open rows only where judgment is needed: a DWARF line or a counter against the rule, stray "
            "artifacts outside the unit's main run, deferred stage 4 rows inside its runs); a re-draft keeps the "
            "planner's decisions; for socom:work:order-link it writes the order link-spec output.",
        ),
        spec(
            "order plan decide",
            "order",
            "Settle one row of an order plan under build/ as the holder of its item's lease (--lease-owner): a new "
            "source position (--position, or --no-position for an in-class member), --in-class/--out-of-line, --class "
            "and the --basis it rests on, recorded with the decision; settles the artifact's open rows (an open row "
            "without a row of its own, a stray copy or a deferred stage 4 row, is settled with --basis only).",
            mutates=True,
        ),
        spec(
            "order plan validate",
            "order",
            "Check an order plan against its item, the current order target and the evidence: schema, every "
            "definition of the segment's units listed exactly once, not-placed definitions and stage 7 targets "
            "complete, positions, row classes against the DWARF lines and counters, the order the plan predicts under "
            "the rule (reverse source order for out-of-line definitions, in-class members right after their first "
            "caller, data in declaration order) equal to the target order with every mismatch listed, open rows "
            "neither dropped nor silently settled, and the order-target, stage 4 baseline, graph, evidence and segment "
            "digests current (stale: re-draft); a link plan must equal the current link-order specification; --check "
            "also fails on open rows; --output writes the full report under build/.",
        ),
        spec(
            "order skeleton manifest",
            "order",
            "Read-only stage 5 phase B inputs over the accepted order plans (each at the SHA-256 its acceptance cites), "
            "the stage 3 receipt (function-index digest equal to the stage 3 baseline's), DWARF, the ELF and src/: per "
            "planned function its signature (mangled and structured name, scope kinds, static/instance and return type "
            "each with its source, const, extern \"C\", the declarator) and S1 (the written declarator parsed back "
            "mangles to the ELF name); per class its body or new header, members to add, virtuals in vtable-slot order, "
            "bases and static data members; every provisional body mapped by exact mangled name to its row and action "
            "(move, cross-file move, BD4 holding, BD6 declarator rewrite); per data row its type and source, ELF "
            "initializer and section; the rows needing judgment and counts per segment; writes the frozen body snapshot "
            "build/stage5/provisional-bodies.json once (then only compares it; --refresh-snapshot replaces it); --output "
            "writes the manifest (with manifest_sha256) under build/. Once the skeleton route's frozen base "
            "build/stage5/skeleton-route/base exists, every provisional input (headers, bodies, preamble, file-scope data) "
            "is read from its src/, never from the written src/, so a rebuild reproduces the manifest the route applied; "
            "--refresh-snapshot is then refused.",
        ),
        spec(
            "order skeleton write",
            "order",
            "Stage 5 phase B (rounds 2 and 3a), preview only: from the skeleton manifest (its digest, the body snapshot, the src/ "
            "digest and the cited accepted order plans must hold; the src/ is the skeleton route's frozen base once it "
            "exists) write a mirror of that src/ under --root (a directory under "
            "build/; src/ is refused: the governed route of round 3b writes it) where each unit file (--segment N, or --all) "
            "keeps its stage 4 blocks byte-identical and its authored preamble, then one entry per planned row fenced "
            "/* @socom-skeleton <stub|body> <mangled> */ in an order that keeps the plan's function and region data "
            "orders: moved bodies from the frozen snapshot (byte-identical but for recorded BD6 or out-of-line head "
            "rewrites), canonical stubs (BD1 pieces flagged), data entries from the ELF initializer (BD5; struct, enum "
            "and nested arrays from DWARF), local statics and function-local classes inside their owner; --all also "
            "writes the unbuilt per-module holding files (BD4), removes the orphan files the moves empty, and runs the "
            "header writer once for the tree (BD2, additive): fenced /* @socom-skeleton decl <name> */ ... end regions "
            "with each class's missing member declarations (own virtuals in vtable-slot order, planned members, "
            "in-class rows, static data members, nested types), the new class bodies in their chosen headers (key, "
            "RTTI/DWARF bases; new headers get an include guard), complete by-value types from their DWARF or stage 3 "
            "record, forward declarations, and per unit the includes and forward declarations its rows need; the "
            "in-class bodies of out-of-line rows become declarations, and header text outside the regions stays "
            "byte-identical. Every judgment row gets a deterministic default with a flag; rows no default can write "
            "without inventing content are listed as waiting; the write manifest (skeleton-write.json, write_sha256 "
            "over LF-normalized digests, the same for every checkout) records it all.",
        ),
        spec(
            "order skeleton check",
            "order",
            "Read-only static checks of a preview written by order skeleton write (none is stage evidence): "
            "determinism (two renders from freshly loaded inputs equal each other and the files on disk), S1 (each "
            "fenced definition and data entry, parsed back from its file, mangles to its fence's name), S2 (the order "
            "re-derived from the fences equals the plan and, under the rule, the target; each planned row written once "
            "in its own unit; unwritten rows listed with their reason), S3 (stage 4 blocks byte-identical, annotation "
            "edges and the stage 4 edge digest unchanged, audit docblocks and source-trace pass over the preview), S4 "
            "(each body entry is its snapshot body, or its recorded head and the snapshot body's text; each lands once, "
            "an in-class body moved out of line no longer in its header), S5 (no guard finding the src/ tree lacks), "
            "S7 (headers: outside the generated regions identical to src/ but for the re-derived in-class "
            "replacements, regions paired and as recorded, every planned member declared exactly once in its class; "
            "S1 also parses each generated declaration back); --lint adds the report-only S6 (MSVC cl /Zs unique "
            "error counts by category, with and without the written headers); --output writes the full report under "
            "build/.",
        ),
    )


def register(commands: Any) -> None:
    order = commands.add_parser("order")
    order_commands = order.add_subparsers(dest="order_command", required=True)
    target = order_commands.add_parser("target")
    which = target.add_mutually_exclusive_group()
    which.add_argument("--unit", help="one authored translation unit (e.g. database.cpp)")
    which.add_argument("--segment", type=int, help="the units of one stage 4 segment plan (its number)")
    which.add_argument("--all", action="store_true", help="every unit (the default)")
    target.add_argument("--output", help="write the target (or the selection) as JSON under build/ and print its counts")
    target.add_argument("--graph", default=DEFAULT_GRAPH)
    target.add_argument("--from-elf", action="store_true", help="regenerate the graph from support/socom.elf")
    target.set_defaults(handler=_order_target)
    link = order_commands.add_parser("link-spec")
    link.add_argument("--output", help="the socom-link-order JSON to write under build/")
    link.add_argument("--text", help="the plain list to write under build/ (default: --output with .txt)")
    link.add_argument("--graph", default=DEFAULT_GRAPH)
    link.add_argument("--from-elf", action="store_true", help="regenerate the graph from support/socom.elf")
    link.set_defaults(handler=_order_link_spec)
    draft = order_commands.add_parser("draft")
    which = draft.add_mutually_exclusive_group()
    which.add_argument("--unit", help="one authored translation unit (e.g. database.cpp)")
    which.add_argument("--segment", type=int, help="the units of one stage 4 segment plan (its number)")
    which.add_argument("--all", action="store_true", help="every unit (the default)")
    draft.add_argument("--output", help="write the draft (or the selection) as JSON under build/ and print its counts")
    draft.add_argument("--graph", default=DEFAULT_GRAPH)
    draft.add_argument("--from-elf", action="store_true", help="regenerate the graph from support/socom.elf")
    draft.set_defaults(handler=_order_draft)
    sql = order_commands.add_parser("sql")
    sql.add_argument("statement")
    sql.add_argument("--limit", type=int, default=200)
    sql.add_argument("--format", choices=("text", "json"), default="text")
    sql.add_argument("--output", help="write the result (in --format) to this file under build/ instead of stdout")
    sql.add_argument("--graph", default=DEFAULT_GRAPH)
    sql.set_defaults(handler=_order_sql)
    plan = order_commands.add_parser("plan")
    plan_commands = plan.add_subparsers(dest="order_plan_command", required=True)
    draft_plan = plan_commands.add_parser("draft")
    draft_plan.add_argument("--item", required=True, help="a stage 5 plan item (socom:work:order-segment-NNN or socom:work:order-link)")
    draft_plan.add_argument("--output", help="the plan file under build/ (default: the item's packet path)")
    draft_plan.add_argument("--graph", default=DEFAULT_GRAPH)
    draft_plan.set_defaults(handler=_order_plan_draft)
    decide = plan_commands.add_parser("decide")
    decide.add_argument("--plan", required=True)
    decide.add_argument("--lease-owner", required=True, help="the worker holding the plan item's lease")
    decide.add_argument("--artifact", required=True)
    where = decide.add_mutually_exclusive_group()
    where.add_argument("--position", type=int, help="the row's new source position in its scope (1 = first)")
    where.add_argument("--no-position", action="store_true", help="an in-class member without a source position")
    member = decide.add_mutually_exclusive_group()
    member.add_argument("--in-class", action="store_true", help="defined in its class body, emitted on demand")
    member.add_argument("--out-of-line", action="store_true", help="defined out of line (in the file's source order)")
    decide.add_argument("--class", dest="klass", choices=("proven", "constrained", "hypothesis"))
    decide.add_argument("--basis", required=True, help="the evidence or judgment the decision rests on")
    decide.set_defaults(handler=_order_plan_decide)
    validate = plan_commands.add_parser("validate")
    validate.add_argument("--plan", required=True)
    validate.add_argument("--check", action="store_true", help="also fail on open rows")
    validate.add_argument("--output", help="write the full report as JSON under build/")
    validate.add_argument("--graph", default=DEFAULT_GRAPH)
    validate.set_defaults(handler=_order_plan_validate)
    skeleton = order_commands.add_parser("skeleton")
    skeleton_commands = skeleton.add_subparsers(dest="order_skeleton_command", required=True)
    manifest = skeleton_commands.add_parser("manifest")
    which = manifest.add_mutually_exclusive_group()
    which.add_argument("--segment", type=int, help="the rows of one segment plan (its number)")
    which.add_argument("--all", action="store_true", help="every planned row (the default)")
    manifest.add_argument("--output", help="write the manifest as JSON under build/")
    manifest.add_argument("--snapshot", default="build/stage5/provisional-bodies.json",
                          help="the frozen provisional-body snapshot under build/ (written once, then compared)")
    manifest.add_argument("--refresh-snapshot", action="store_true", help="replace the snapshot with the current bodies")
    manifest.add_argument("--receipt", help="a `ghidra receipt --scope` export under build/ (default: the stage 3 closeout receipt)")
    manifest.add_argument("--graph", default=DEFAULT_GRAPH)
    manifest.set_defaults(handler=_order_skeleton_manifest)
    write = skeleton_commands.add_parser("write")
    which = write.add_mutually_exclusive_group(required=True)
    which.add_argument("--segment", type=int, help="the unit files of one segment plan (its number)")
    which.add_argument("--all", action="store_true", help="every unit file, the holding files and the emptied orphans")
    write.add_argument("--root", dest="preview_root", required=True, help="the preview directory under build/ (src/ is refused this round)")
    write.add_argument("--manifest", default="build/stage5/skeleton-manifest.json", help="the skeleton manifest under build/")
    write.add_argument("--snapshot", default="build/stage5/provisional-bodies.json", help="the frozen body snapshot under build/")
    write.set_defaults(handler=_order_skeleton_write)
    check = skeleton_commands.add_parser("check")
    check.add_argument("--root", dest="preview_root", required=True, help="a preview directory written by order skeleton write")
    check.add_argument("--manifest", default="build/stage5/skeleton-manifest.json")
    check.add_argument("--snapshot", default="build/stage5/provisional-bodies.json")
    check.add_argument("--lint", action="store_true", help="also run the report-only S6 (MSVC cl /Zs)")
    check.add_argument("--output", help="write the full report as JSON under build/")
    check.set_defaults(handler=_order_skeleton_check)
    from . import order_route_cli

    order_route_cli.register_skeleton(skeleton_commands)


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _graph(root: Path, arguments: argparse.Namespace) -> tuple[dict[str, Any], str]:
    from .source_graph import source_graph
    from .util import SocomError, load_json

    if getattr(arguments, "from_elf", False):
        return source_graph(root), "regenerated from support/socom.elf"
    path = _path(root, arguments.graph)
    if not path.is_file():
        raise SocomError(
            f"{arguments.graph} does not exist: write it with `source graph --output {arguments.graph}` or pass --from-elf"
        )
    return load_json(path), arguments.graph


def _target(root: Path, arguments: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], str]:
    from .constants import tracker_path
    from .order_target import build_order_target, load_inputs
    from .tracker import load_tracker

    tracker = load_tracker(tracker_path(root))
    graph, origin = _graph(root, arguments)
    inputs = load_inputs(root, tracker, graph)
    target = build_order_target(
        graph, inputs["plans"], deferrals=inputs["deferrals"], boundaries=inputs["boundaries"], notes=inputs["notes"]
    )
    return target, tracker, origin


def _order_target(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .order_target import counts, order_view, select_units
    from .util import atomic_write_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "order targets") if arguments.output else None
    target, _tracker, origin = _target(root, arguments)
    selection = (
        {"unit": arguments.unit} if arguments.unit else {"segment": arguments.segment} if arguments.segment is not None else None
    )
    body = target if selection is None else order_view(target, select_units(target, **selection), selection)
    if output is not None:
        atomic_write_json(output, body)
    if selection is not None and output is None:
        _emit(body)
        return 0
    report: dict[str, Any] = {
        "ok": True,
        "mutation_performed": False,
        "graph": origin,
        "output": arguments.output,
        **counts(target),
    }
    if selection is not None:
        report["selection"] = selection
        report["selected_units"] = len(body["units"])
    else:
        report["findings"] = [row for row in target["findings"] if row["kind"] != "deferred-in-span"][:12]
        if output is None:
            report["note"] = "pass --output build/<file>.json for the full target, or --unit/--segment for a selection"
    _emit(report)
    return 0


def _order_draft(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_draft import build_order_draft, headline, load_evidence
    from .order_target import build_order_target, load_inputs
    from .source_cache import ensure_source_cache
    from .tracker import load_tracker
    from .util import atomic_write_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "order drafts") if arguments.output else None
    tracker = load_tracker(tracker_path(root))
    graph, origin = _graph(root, arguments)
    inputs = load_inputs(root, tracker, graph)
    target = build_order_target(
        graph, inputs["plans"], deferrals=inputs["deferrals"], boundaries=inputs["boundaries"], notes=inputs["notes"]
    )
    selection = (
        {"unit": arguments.unit} if arguments.unit else {"segment": arguments.segment} if arguments.segment is not None else None
    )
    if arguments.from_elf:
        cache, _rebuilt = ensure_source_cache(root, graph=graph)
    else:
        cache, _rebuilt = ensure_source_cache(root, graph_path=_path(root, arguments.graph))
    draft = build_order_draft(target, load_evidence(root, cache, graph), selection)
    if output is not None:
        atomic_write_json(output, draft)
    elif selection is not None:
        _emit(draft)
        return 0
    report: dict[str, Any] = {"ok": True, "mutation_performed": False, "graph": origin, "output": arguments.output, **headline(draft)}
    if selection is not None:
        report["selection"] = selection
    elif output is None:
        report["note"] = "pass --output build/<file>.json for the whole draft, or --unit/--segment for a selection"
    _emit(report)
    return 0


def _order_link_spec(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .order_target import link_order, link_order_text
    from .util import atomic_write_json, atomic_write_text

    root = _root(arguments)
    output = _build_path(root, arguments.output, "link-order files") if arguments.output else None
    text_value = arguments.text or (Path(arguments.output).with_suffix(".txt").as_posix() if arguments.output else None)
    text = _build_path(root, text_value, "link-order lists") if text_value else None
    target, _tracker, origin = _target(root, arguments)
    body = link_order(target)
    if output is not None:
        atomic_write_json(output, body)
    if text is not None:
        atomic_write_text(text, link_order_text(body))
    check = body["check"]
    _emit(
        {
            "ok": check["ok"],
            "mutation_performed": False,
            "graph": origin,
            "output": arguments.output,
            "text": text_value,
            "order_sha256": body["order_sha256"],
            "link_order_sha256": body["link_order_sha256"],
            "objects": len(body["objects"]),
            "authored": sum(1 for row in body["objects"] if row["kind"] == "authored"),
            "provider": sum(1 for row in body["objects"] if row["kind"] == "provider"),
            "regions_checked": check["regions_checked"],
            "regions_skipped": check["regions_skipped"],
            "violations": check["violations"],
            "violation_regions": check["violation_regions"],
            "split_contributions": check["split_contributions"],
            "split_regions": check["split_regions"],
        }
    )
    return 0 if check["ok"] else 1


def _order_sql(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_target import CACHE_RELATIVE, build_order_target, cache_fingerprint, cache_fresh, load_inputs, write_cache
    from .source_cache import query
    from .tracker import load_tracker
    from .util import SocomError, atomic_write_json, atomic_write_text, load_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "order sql") if arguments.output else None
    graph_path = _path(root, arguments.graph)
    if not graph_path.is_file():
        raise SocomError(f"{arguments.graph} does not exist: write it with `source graph --output {arguments.graph}`")
    tracker = load_tracker(tracker_path(root))
    path = root / CACHE_RELATIVE
    fingerprint = cache_fingerprint(root, tracker, graph_path)
    rebuilt = not cache_fresh(path, fingerprint)
    if rebuilt:
        graph = load_json(graph_path)
        inputs = load_inputs(root, tracker, graph)
        target = build_order_target(
            graph, inputs["plans"], deferrals=inputs["deferrals"], boundaries=inputs["boundaries"], notes=inputs["notes"]
        )
        write_cache(path, target, fingerprint)
    try:
        result = query(path, arguments.statement, arguments.limit)
    except SocomError as exc:
        raise SocomError(str(exc).replace("source sql", "order sql")) from exc
    cache = CACHE_RELATIVE.as_posix()
    if arguments.format == "json" and output is None:
        _emit({**result, "cache": cache, "rebuilt": rebuilt})
        return 0
    lines = ["\t".join(result["columns"])]
    lines.extend("\t".join("" if value is None else str(value) for value in row) for row in result["rows"])
    if result["truncated"]:
        lines.append(f"... (truncated at {arguments.limit} rows; use --limit)")
    if output is not None:
        if arguments.format == "json":
            atomic_write_json(output, {**result, "cache": cache, "rebuilt": rebuilt})
        else:
            atomic_write_text(output, "\n".join(lines) + "\n")
        _emit(
            {
                "ok": True, "mutation_performed": False, "output": arguments.output, "format": arguments.format,
                "columns": result["columns"], "rows": len(result["rows"]), "truncated": result["truncated"], "rebuilt": rebuilt,
            }
        )
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write("\n".join(lines) + "\n")
    return 0


def _order_plan_draft(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_plan import ORDER_LINK_ID, draft_order_plan, order_context, order_plan_path, plan_item
    from .order_target import link_order
    from .tracker import load_tracker
    from .util import SocomError, atomic_write_json, load_json

    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    item = plan_item(tracker, arguments.item)
    relative = arguments.output or order_plan_path(item["id"])
    output = _build_path(root, relative, "order plans")
    if relative == order_plan_path(item["id"]) and item.get("status") in ("awaiting_acceptance", "accepted"):
        # A handed-off or accepted plan changes only after progress work reject or reopen.
        raise SocomError(
            f"{item['id']} is {item['status']}: its plan is under review or accepted; reopen it (progress work reopen) "
            "or reject it before re-drafting, or draft to another --output under build/"
        )
    if item["id"] == ORDER_LINK_ID:
        target, _none = order_context(root, tracker, _path(root, arguments.graph), evidence=False)
        body = link_order(target)
        atomic_write_json(output, body)
        _emit({"ok": body["check"]["ok"], "mutation_performed": False, "item": item["id"], "output": relative,
               "objects": len(body["objects"]), "link_order_sha256": body["link_order_sha256"],
               "violations": body["check"]["violations"]})
        return 0 if body["check"]["ok"] else 1
    target, derived = order_context(root, tracker, _path(root, arguments.graph))
    previous = load_json(output) if output.is_file() else None
    plan, carried = draft_order_plan(tracker, item, target, derived or {}, previous if isinstance(previous, dict) else None)
    atomic_write_json(output, plan)
    open_rows = [row for unit in plan["units"] for row in unit["open"]]
    kinds: dict[str, int] = {}
    for row in open_rows:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    rows = [row for unit in plan["units"] for row in unit["functions"]] + [
        row for unit in plan["units"] for region in unit["data"] for row in region["rows"]
    ]
    classes: dict[str, int] = {}
    for row in rows:
        classes[row["class"]] = classes.get(row["class"], 0) + 1
    _emit(
        {
            "ok": True, "mutation_performed": False, "item": item["id"], "output": relative, "units": len(plan["units"]),
            "functions": sum(len(unit["functions"]) for unit in plan["units"]),
            "data": sum(len(region["rows"]) for unit in plan["units"] for region in unit["data"]),
            "classes": dict(sorted(classes.items())), "open_rows": len(open_rows), "open_by_kind": dict(sorted(kinds.items())),
            "carried_decisions": carried["carried"], "dropped_decisions": carried["dropped"],
        }
    )
    return 0


def _order_plan_decide(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_plan import ORDER_PLAN_KIND, UNSET, decide_order_row
    from .source_plan_edit import require_plan_lease
    from .tracker import load_tracker
    from .util import SocomError, atomic_write_json, load_json

    root = _root(arguments)
    target = _build_path(root, arguments.plan, "order plans")
    plan = load_json(target)
    if not isinstance(plan, dict) or plan.get("kind") != ORDER_PLAN_KIND:
        raise SocomError(f"{arguments.plan} is not a {ORDER_PLAN_KIND} file (a link-order plan has no rows to decide)")
    # Only the worker holding the plan item's lease edits its plan.
    require_plan_lease(load_tracker(tracker_path(root)), plan.get("work_item_id"), arguments.lease_owner)
    position = None if arguments.no_position else arguments.position if arguments.position is not None else UNSET
    in_class = True if arguments.in_class else False if arguments.out_of_line else None
    unit, changes = decide_order_row(
        plan, arguments.artifact, owner=arguments.lease_owner, basis=arguments.basis, position=position, in_class=in_class,
        klass=arguments.klass,
    )
    atomic_write_json(target, plan)
    _emit(
        {
            "ok": True, "mutation_performed": True, "plan": arguments.plan, "unit": unit, "changes": changes,
            "open_rows": sum(len(row.get("open") or []) for row in plan.get("units") or []),
        }
    )
    return 0


def _order_skeleton_manifest(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_skeleton import build_manifest, headline, settle_snapshot
    from .tracker import load_tracker
    from .util import SocomError, atomic_write_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "skeleton manifests") if arguments.output else None
    snapshot_path = _build_path(root, arguments.snapshot, "body snapshots")
    receipt = _build_path(root, arguments.receipt, "receipt exports") if arguments.receipt else None
    tracker = load_tracker(tracker_path(root))
    base = _preview_base(root, tracker)
    if base is not None and arguments.refresh_snapshot:
        raise SocomError(f"the body snapshot is frozen with the skeleton route's base ({_source_label(root, base)}): "
                         "--refresh-snapshot is refused once the base exists")
    manifest, snapshot = build_manifest(
        root, tracker, graph_path=_path(root, arguments.graph), receipt_path=receipt, segment=arguments.segment,
        source_root=base,
    )
    snapshot_state = settle_snapshot(snapshot_path, snapshot, refresh=arguments.refresh_snapshot)
    if output is not None:
        atomic_write_json(output, manifest)
    ok = snapshot_state["status"] != "stale"
    source = _source_label(root, base)
    report = {"ok": ok, "mutation_performed": False, "output": arguments.output, "source": source,
              "snapshot": {"path": arguments.snapshot, **snapshot_state}}
    if not ok:
        report["note"] = (f"{source} changed since the snapshot was frozen: pass --refresh-snapshot only if no skeleton apply has started"
                          if base is None else f"{source} differs from the snapshot frozen with it: restore the base, never refresh the snapshot")
    _emit({**report, **headline(manifest)})
    return 0 if ok else 1


def _preview_base(root: Path, tracker: dict[str, Any]) -> Path | None:
    """The root of the src/ the read-only skeleton commands take their provisional inputs from (None: src/ itself).

    Once the skeleton route's frozen base exists, src/ holds skeletons: the manifest, previews and checks read the base.
    """

    from .order_skeleton_route import provisional_root

    return provisional_root(root, tracker)


def _source_label(root: Path, base: Path | None) -> str:
    return "src/" if base is None else f"{base.relative_to(root).as_posix()}/src/"


def _order_skeleton_write(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_skeleton_write import SkeletonInputs, preview_root, render_skeletons, tree_digest, write_skeletons
    from .tracker import load_tracker

    root = _root(arguments)
    target = preview_root(root, arguments.preview_root)
    tracker = load_tracker(tracker_path(root))
    base = _preview_base(root, tracker)
    inputs = SkeletonInputs(
        root, tracker, manifest_path=_build_path(root, arguments.manifest, "skeleton manifests"),
        snapshot_path=_build_path(root, arguments.snapshot, "body snapshots"), source_root=base,
    )
    rendered = render_skeletons(inputs, segment=arguments.segment)
    write_skeletons(base if base is not None else root, target, rendered)
    manifest = rendered["manifest"]
    _emit({
        "ok": True, "mutation_performed": False, "root": arguments.preview_root, "source": _source_label(root, base),
        "write_manifest": f"{arguments.preview_root.rstrip('/')}/skeleton-write.json",
        "write_sha256": manifest["write_sha256"], "tree_sha256": tree_digest(target), "summary": manifest["summary"],
        "waiting": manifest["waiting"], "order_conflicts": manifest["order_conflicts"],
        "header_waiting": (manifest.get("headers") or {}).get("waiting") or [],
        "deleted": [row["path"] for row in manifest["deleted"]],
    })
    return 0


def _order_skeleton_check(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_skeleton_check import check_skeletons, headline
    from .order_skeleton_write import preview_root
    from .tracker import load_tracker
    from .util import atomic_write_json

    root = _root(arguments)
    target = preview_root(root, arguments.preview_root)
    output = _build_path(root, arguments.output, "skeleton check reports") if arguments.output else None
    tracker = load_tracker(tracker_path(root))
    base = _preview_base(root, tracker)
    report = check_skeletons(
        root, tracker, target, manifest_path=_build_path(root, arguments.manifest, "skeleton manifests"),
        snapshot_path=_build_path(root, arguments.snapshot, "body snapshots"), lint=arguments.lint, source_root=base,
    )
    if output is not None:
        atomic_write_json(output, report)
    _emit({**headline(report), "mutation_performed": False, "output": arguments.output, "source": _source_label(root, base)})
    return 0 if report["ok"] else 1


def _order_plan_validate(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .order_plan import validate_plan_file
    from .tracker import load_tracker
    from .util import atomic_write_json, load_json

    root = _root(arguments)
    output = _build_path(root, arguments.output, "order plan reports") if arguments.output else None
    plan = load_json(_path(root, arguments.plan))
    report = validate_plan_file(
        root, load_tracker(tracker_path(root)), plan, check=arguments.check, graph_path=_path(root, arguments.graph)
    )
    if output is not None:
        atomic_write_json(output, report)
    shown = {key: report.get(key) for key in ("ok", "work_item_id", "summary", "problems", "notes", "stale")}
    shown["mismatches"] = len(report.get("mismatches") or [])
    _emit({**shown, "mutation_performed": False, "check": arguments.check, "output": arguments.output})
    return 0 if report["ok"] else 1
