"""CLI handlers for stage 4 owner plans (``source plan evidence``, ``source plan validate``).

The registry rows and parser wiring live here so the main CLI only lists
them; handlers import the shared CLI helpers lazily to avoid an import cycle.
"""

from __future__ import annotations

import argparse
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
            "source plan validate",
            "source",
            "Check a source-owner plan: every artifact of its item's slice owned once or unresolved, owner, provider, "
            "header-emit and annotation rows, provisional files, and the graph and slice digests (--check regenerates "
            "the graph from the ELF).",
        ),
    )


def register(source_commands: Any) -> None:
    plan = source_commands.add_parser("plan")
    plan_commands = plan.add_subparsers(dest="source_plan_command", required=True)
    evidence = plan_commands.add_parser("evidence")
    evidence.add_argument("--item", required=True)
    evidence.add_argument("--output", required=True)
    evidence.add_argument("--skeleton", help="also write a skeleton plan here (refused when the file exists)")
    evidence.add_argument("--graph", default=DEFAULT_GRAPH)
    evidence.add_argument("--check", action="store_true", help="regenerate the graph from support/socom.elf")
    evidence.set_defaults(handler=_source_plan_evidence)
    validate = plan_commands.add_parser("validate")
    validate.add_argument("--plan", required=True)
    validate.add_argument("--graph", default=DEFAULT_GRAPH)
    validate.add_argument("--check", action="store_true", help="regenerate the graph from support/socom.elf")
    validate.add_argument(
        "--fill-annotations",
        action="store_true",
        help="first rewrite the plan's annotations with the targets its owner and header-emit rows imply",
    )
    validate.set_defaults(handler=_source_plan_validate)


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _graph(root: Path, arguments: argparse.Namespace) -> tuple[dict[str, Any], str]:
    from .source_graph import source_graph
    from .util import SocomError, load_json

    if arguments.check:
        return source_graph(root), "regenerated from support/socom.elf"
    path = _path(root, arguments.graph)
    if not path.is_file():
        raise SocomError(
            f"{arguments.graph} does not exist: write it with `source graph --output {arguments.graph}` or pass --check"
        )
    return load_json(path), arguments.graph


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


def _source_plan_validate(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .source_plan import derive_annotations, loaded_section_lookup, validate_source_plan
    from .tracker import load_tracker
    from .util import atomic_write_json, load_json, sha256_file

    root = _root(arguments)
    plan_path = _path(root, arguments.plan)
    plan = load_json(plan_path)
    tracker = load_tracker(tracker_path(root))
    graph, origin = _graph(root, arguments)
    section_of = loaded_section_lookup(root)
    filled = False
    if arguments.fill_annotations and isinstance(plan, dict):
        target = _build_path(root, arguments.plan, "source plans")
        plan["annotations"] = derive_annotations(plan, graph, section_of)
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
    _emit(
        {
            "ok": report["ok"],
            "mutation_performed": False,
            "plan": arguments.plan,
            "sha256": sha256,
            "graph": origin,
            "graph_sha256": graph.get("graph_sha256"),
            "annotations_filled": filled,
            "applied": own,
            "summary": report["summary"],
            "review": report["review"],
            "problems": report["problems"],
        }
    )
    return 0 if report["ok"] else 1
