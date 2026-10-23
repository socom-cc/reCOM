"""CLI handlers for code-derived type recovery (``recon layout``, ``recon type-plan``).

The registry rows and parser wiring live here so the main CLI only lists
them; handlers import the shared CLI helpers lazily to avoid an import cycle.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import sys
from pathlib import Path
from typing import Any


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "recon layout",
            "recon",
            "Write ELF-derived layout evidence of a class (and its bases and derived classes), or with --struct of a "
            "plain struct named only by mangled parameter types (its callers' own objects included): every proven "
            "access per offset.",
            mutates=True,
        ),
        spec("recon type-plan validate", "recon", "Check a code-derived type plan against regenerated layout evidence."),
        spec("recon type-plan show", "recon", "Render a code-derived type plan as a review table with its validation."),
        spec(
            "recon type-plan live",
            "recon",
            "Check a valid code-derived type plan against the live program, read-only: no target or forward-declared "
            "name exists, and every referenced live type and instantiation source resolves exactly once with the "
            "recorded layout.",
            ghidra_requirement="required",
        ),
        spec(
            "recon type-plan program",
            "recon",
            "Translate a valid code-derived type plan into a type apply program.",
            mutates=True,
        ),
        spec(
            "recon type-plan affected",
            "recon",
            "List the reconstruction groups whose functions name a planned class, and which rows were left unresolved for it.",
        ),
        spec(
            "ghidra apply-type-plan",
            "ghidra",
            "Apply a reviewed code-derived type program under the item's writer lease and verify it (--dry-run: read-only checks).",
            mutates=True,
            ghidra_requirement="required",
            mutates_ghidra=True,
        ),
        spec(
            "progress add-type-plan",
            "progress",
            "Add a file-only code-derived type plan item and its live apply item to the stage 3 gate.",
            mutates=True,
        ),
    )


def register(recon_commands: Any, ghidra_commands: Any, progress_commands: Any) -> None:
    layout = recon_commands.add_parser("layout")
    layout.add_argument("--class", dest="class_name", required=True)
    layout.add_argument("--with-derived", action="store_true")
    layout.add_argument("--struct", action="store_true", help="a plain struct named only by mangled parameter types")
    layout.add_argument("--output", required=True)
    layout.set_defaults(handler=_recon_layout)

    type_plan = recon_commands.add_parser("type-plan")
    type_plan_commands = type_plan.add_subparsers(dest="type_plan_command", required=True)
    validate = type_plan_commands.add_parser("validate")
    validate.add_argument("--plan", required=True)
    validate.set_defaults(handler=_type_plan_validate)
    show = type_plan_commands.add_parser("show")
    show.add_argument("--plan", required=True)
    show.add_argument("--output")
    show.set_defaults(handler=_type_plan_show)
    live = type_plan_commands.add_parser("live")
    live.add_argument("--plan", required=True)
    live.add_argument("--bridge-url")
    live.set_defaults(handler=_type_plan_live)
    program = type_plan_commands.add_parser("program")
    program.add_argument("--plan", required=True)
    program.add_argument("--output", required=True)
    program.set_defaults(handler=_type_plan_program)
    affected = type_plan_commands.add_parser("affected")
    target = affected.add_mutually_exclusive_group(required=True)
    target.add_argument("--class", dest="class_name")
    target.add_argument("--plan")
    affected.add_argument("--with-derived", action="store_true")
    affected.add_argument("--struct", action="store_true", help="--class names a plain struct (recon layout --struct)")
    affected.add_argument("--output")
    affected.set_defaults(handler=_type_plan_affected)

    apply = ghidra_commands.add_parser("apply-type-plan")
    apply.add_argument("--program", required=True)
    apply.add_argument("--item", required=True)
    apply.add_argument("--owner", required=True)
    apply.add_argument("--scope-output", required=True)
    apply.add_argument("--report-output", required=True)
    apply.add_argument("--dry-run", action="store_true")
    apply.add_argument("--bridge-url")
    apply.set_defaults(handler=_ghidra_apply_type_plan)

    add = progress_commands.add_parser("add-type-plan")
    add.add_argument("--class", dest="class_name", required=True)
    add.add_argument("--with-derived", action="store_true")
    add.add_argument("--struct", action="store_true", help="a plain struct named only by mangled parameter types")
    add.add_argument("--expected-revision", type=int, required=True)
    add.add_argument("--dry-run", action="store_true")
    add.set_defaults(handler=_progress_add_type_plan)


def _path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _recon_layout(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .type_layout import class_layout, render_layout
    from .type_plan import layout_sha256
    from .util import atomic_write_json, atomic_write_text

    root = _root(arguments)
    output = _build_path(root, arguments.output, "layout evidence")
    report = class_layout(root, arguments.class_name, arguments.with_derived, struct=arguments.struct)
    if output.suffix == ".json":
        atomic_write_json(output, report)
    else:
        atomic_write_text(output, render_layout(report))
    _emit(
        {
            "mutation_performed": False,
            "class": report["class"],
            "with_derived": report["with_derived"],
            **({"struct": True} if report.get("struct") else {}),
            "layout_sha256": layout_sha256(report),
            "summary": report["summary"],
            "classes": [
                {"class": row["class"], "role": row["role"], "size_evidence": row["size_evidence"], "offsets": len(row["offsets"])}
                for row in report["classes"]
            ],
            "output": arguments.output,
        }
    )
    return 0


def _load_plan(arguments: argparse.Namespace) -> tuple[Path, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    from .cli import _root
    from .constants import tracker_path
    from .tracker import load_tracker
    from .type_plan import plan_layout
    from .util import load_json

    root = _root(arguments)
    plan_path = _path(root, arguments.plan)
    plan = load_json(plan_path)
    spec = plan.get("layout") or {}
    layout = plan_layout(root, spec) if spec.get("class") else {"classes": []}
    return root, plan_path, plan, layout, load_tracker(tracker_path(root))


def _type_plan_validate(arguments: argparse.Namespace) -> int:
    from .cli import _emit
    from .type_plan import layout_sha256, validate_type_plan
    from .util import sha256_file

    root, plan_path, plan, layout, tracker = _load_plan(arguments)
    problems = validate_type_plan(root, tracker, plan, layout) if layout["classes"] else ["layout.class is missing"]
    _emit(
        {
            "ok": not problems,
            "mutation_performed": False,
            "plan": arguments.plan,
            "sha256": sha256_file(plan_path),
            "layout_sha256": layout_sha256(layout) if layout["classes"] else None,
            "problems": problems,
        }
    )
    return 0 if not problems else 1


def _type_plan_show(arguments: argparse.Namespace) -> int:
    from .cli import _build_path
    from .type_plan import render_type_plan, validate_type_plan
    from .type_plan_evidence import TypeEvidence
    from .util import atomic_write_text

    root, _plan_path, plan, layout, tracker = _load_plan(arguments)
    problems = validate_type_plan(root, tracker, plan, layout) if layout["classes"] else ["layout.class is missing"]
    text = render_type_plan(plan, layout, problems, TypeEvidence(root))
    if arguments.output:
        atomic_write_text(_build_path(root, arguments.output, "type plan reviews"), text)
    sys.stdout.write(text)
    return 0 if not problems else 1


def _live_layout_reader(bridge: Any) -> Any:
    from .type_apply import parse_struct_layout

    return lambda leaf: parse_struct_layout(bridge.request("get_struct_layout", struct_name=leaf))


def _type_plan_live(arguments: argparse.Namespace) -> int:
    from .cli import _emit
    from .ghidra import GhidraBridge, _type_index
    from .type_plan import build_type_plan_program, live_type_problems
    from .util import sha256_file

    root, plan_path, _plan, layout, tracker = _load_plan(arguments)
    program = build_type_plan_program(root, tracker, plan_path, layout)
    bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
    problems = live_type_problems(program, _type_index(bridge), _live_layout_reader(bridge))
    _emit(
        {
            "ok": not problems,
            "mutation_performed": False,
            "plan": arguments.plan,
            "sha256": sha256_file(plan_path),
            "checked": {
                "types": len(program["types"]),
                "forward_declarations": sum(1 for entry in program["types"] if entry.get("declaration")),
                "external_types": len(program["external_types"]),
                "template_arguments": len(program.get("template_arguments", [])),
                "layout_sources": len(program["layout_sources"]),
            },
            "live_problems": problems,
        }
    )
    return 0 if not problems else 1


def _type_plan_program(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit
    from .type_plan import build_type_plan_program
    from .util import atomic_write_json, canonical_json

    root, plan_path, _plan, layout, tracker = _load_plan(arguments)
    program = build_type_plan_program(root, tracker, plan_path, layout)
    atomic_write_json(_build_path(root, arguments.output, "type programs"), program)
    _emit(
        {
            "kind": program["kind"],
            "mutation_performed": False,
            "plan": program["plan"],
            "summary": program["summary"],
            "program_sha256": hashlib.sha256(canonical_json(program).encode("utf-8")).hexdigest(),
            "output": arguments.output,
        }
    )
    return 0


def _type_plan_affected(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .constants import tracker_path
    from .tracker import load_tracker
    from .type_layout import _Family
    from .type_plan import affected_groups, plan_classes
    from .util import atomic_write_json, load_json
    from .mwdemangle import readable_qualified

    root = _root(arguments)
    if arguments.plan:
        classes = plan_classes(load_json(_path(root, arguments.plan)))
    else:
        family = _Family(root, arguments.class_name, arguments.with_derived, struct=arguments.struct)
        classes = sorted(readable_qualified(list(cls)) for cls in family.classes)
    report = affected_groups(root, load_tracker(tracker_path(root)), classes)
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "affected-group reports"), report)
    _emit({key: value for key, value in report.items() if key != "functions"} | {"output": arguments.output})
    return 0


def _ghidra_apply_type_plan(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _require_accepted_plan, _root
    from .constants import tracker_path
    from .ghidra import GhidraBridge, _type_index, live_preflight
    from .tracker import TYPE_APPLY_KIND, load_tracker, require_ghidra_lease
    from .type_apply import ApplyFailure, execute_apply_program
    from .type_plan import build_type_plan_program, live_type_problems
    from .util import SocomError, atomic_write_json, canonical_json, load_json

    root = _root(arguments)
    program = load_json(_path(root, arguments.program))
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "apply reports")
    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    if item.get("kind") != TYPE_APPLY_KIND:
        raise SocomError(f"{arguments.item} is not a code-derived type apply item")
    plan_path = _require_accepted_plan(root, tracker, item, program)
    if canonical_json(build_type_plan_program(root, tracker, plan_path)) != canonical_json(program):
        raise SocomError("the type program is stale or edited; regenerate it")
    preflight = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
    base = {
        "kind": "socom-ghidra-type-plan-apply-report",
        "schema_version": 1,
        "dry_run": arguments.dry_run,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        "program_sha256": hashlib.sha256(canonical_json(program).encode("utf-8")).hexdigest(),
        "plan": program["plan"],
        "summary": program["summary"],
    }
    problems = live_type_problems(program, _type_index(bridge), _live_layout_reader(bridge))
    if problems or arguments.dry_run:
        report = {**base, "ok": not problems, "live_problems": problems, "writes": 0}
        atomic_write_json(report_output, report)
        _emit(report)
        return 0 if not problems else 1
    try:
        result = execute_apply_program(
            program,
            bridge,
            type_index=lambda: _type_index(bridge),
            log=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except ApplyFailure as failure:
        report = {
            **base,
            "ok": False,
            "error": str(failure),
            "completed_steps": failure.completed_steps,
            "details": failure.details,
            "recovery": "close socom.elf without saving and reopen it before retrying",
        }
        atomic_write_json(report_output, report)
        _emit({key: value for key, value in report.items() if key != "details"})
        return 1
    atomic_write_json(scope_output, program["receipt_scope"])
    report = {**base, "ok": True, "result": result, "decisions": program["decisions"], "scope_output": scope_output.relative_to(root).as_posix()}
    atomic_write_json(report_output, report)
    _emit(report)
    return 0


def _progress_add_type_plan(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .tracker import add_type_plan_items, audit_tracker, load_tracker, mutate, refresh_ready_and_stages, require_revision

    root = _root(arguments)
    captured: list[str] = []
    if arguments.struct:
        from .type_layout import _Family

        # The name must qualify (no member, vtable, RTTI or DWARF record; a mangled T * / T & parameter names it).
        _Family(root, arguments.class_name, arguments.with_derived, struct=True)

    def add(tracker: dict[str, Any]) -> None:
        captured.extend(add_type_plan_items(tracker, arguments.class_name, arguments.with_derived, struct=arguments.struct))

    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        require_revision(tracker, arguments.expected_revision)
        preview = copy.deepcopy(tracker)
        add(preview)
        refresh_ready_and_stages(preview)
        preview["revision"] += 1
        errors = audit_tracker(preview, strict=True)
        _emit({"ok": not errors, "dry_run": True, "revision": tracker["revision"], "items": captured, "errors": errors})
        return 0 if not errors else 1
    updated = mutate(tracker_path(root), arguments.expected_revision, add)
    write_snapshot(root, updated)
    items = [row for row in updated["work_items"] if row["id"] in captured]
    _emit({"ok": True, "revision": updated["revision"], "work_items": items})
    return 0
