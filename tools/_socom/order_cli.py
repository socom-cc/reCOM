"""CLI handlers for stage 5 (authored-function-order) phase A.

``order target``, ``order link-spec`` and ``order sql``: read-only commands
over the accepted stage 4 owner plans, the source graph and the reference
ELF.  Outputs go under ``build/`` only; the main CLI lists the registry rows
and wires the parser through ``specs`` and ``register``.
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
            "order sql",
            "order",
            "Run one read-only SELECT/WITH over build/cache/order-target.sqlite (regions, objects, contributions, "
            "targets, findings, checks), a derived cache of the order target rebuilt when the graph file, the cited "
            "plans or the gate deferrals change; --output writes the result under build/ and prints its row count.",
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
    sql = order_commands.add_parser("sql")
    sql.add_argument("statement")
    sql.add_argument("--limit", type=int, default=200)
    sql.add_argument("--format", choices=("text", "json"), default="text")
    sql.add_argument("--output", help="write the result (in --format) to this file under build/ instead of stdout")
    sql.add_argument("--graph", default=DEFAULT_GRAPH)
    sql.set_defaults(handler=_order_sql)


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
