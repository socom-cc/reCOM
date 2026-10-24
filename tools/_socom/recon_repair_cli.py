"""CLI handlers for recon repairs (``progress add-recon-repair``),
``recon partial-candidates`` and ``recon global-facts``.

The registry rows and parser wiring live here so the main CLI only lists
them; handlers import the shared CLI helpers lazily to avoid an import cycle.
"""

from __future__ import annotations

import argparse
import copy
import sys
from typing import Any


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "progress add-recon-repair",
            "progress",
            "Add a numbered stage 3 recon repair (file-only plan item and live apply item) for functions of applied, "
            "accepted groups whose live prototype is wrong, and/or globals without DWARF records to label and type.",
            mutates=True,
        ),
        spec(
            "recon global-facts",
            "recon",
            "Print each global's .symtab size and binding, DWARF records, initial bytes, data relocations and every "
            "code access (width, sign, load/store, stored values, typed parameters it flows from or into).",
        ),
        spec(
            "recon partial-candidates",
            "recon",
            "List unresolved rows of accepted plans whose live signature is Ghidra's default and whose parameters "
            "the facts prove, for a partial-prototype repair or re-plan.",
            ghidra_requirement="optional",
        ),
    )


def register(recon_commands: Any, progress_commands: Any) -> None:
    add = progress_commands.add_parser("add-recon-repair")
    add.add_argument("--functions", nargs="+", default=[], help="function start addresses (hex)")
    add.add_argument("--globals", nargs="+", default=[], help="global (.symtab object) start addresses (hex)")
    add.add_argument("--expected-revision", type=int, required=True)
    add.add_argument("--dry-run", action="store_true")
    add.set_defaults(handler=_progress_add_recon_repair)

    candidates = recon_commands.add_parser("partial-candidates")
    candidates.add_argument("--groups", choices=("applied", "all"), default="all")
    candidates.add_argument("--fingerprint", help="read signatures and types from a stored fingerprint, not live")
    candidates.add_argument("--output")
    candidates.add_argument("--bridge-url")
    candidates.set_defaults(handler=_recon_partial_candidates)

    facts = recon_commands.add_parser("global-facts")
    selection = facts.add_mutually_exclusive_group(required=True)
    selection.add_argument("--address", nargs="+", help="global start addresses (hex)")
    selection.add_argument("--qualifier", help="every sized object whose demangled qualifier is this (zdb::CVisual)")
    selection.add_argument("--item", help="the globals a recon repair item lists")
    facts.add_argument("--json", action="store_true", help="print the structured facts")
    facts.add_argument("--output")
    facts.set_defaults(handler=_recon_global_facts)


def _progress_add_recon_repair(arguments: argparse.Namespace) -> int:
    from .cli import _emit, _root
    from .constants import tracker_path
    from .snapshot import write_snapshot
    from .tracker import add_recon_repair_items, audit_tracker, load_tracker, mutate, refresh_ready_and_stages, require_revision

    root = _root(arguments)
    captured: list[str] = []
    if not arguments.functions and not arguments.globals:
        raise SystemExit("socom progress add-recon-repair: give --functions and/or --globals")
    facts = None
    if arguments.globals:
        from .recon_globals import global_symbol_facts

        facts = global_symbol_facts(root, arguments.globals)

    def add(tracker: dict[str, Any]) -> None:
        captured.extend(add_recon_repair_items(tracker, arguments.functions, arguments.globals, facts))

    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        require_revision(tracker, arguments.expected_revision)
        preview = copy.deepcopy(tracker)
        add(preview)
        refresh_ready_and_stages(preview)
        preview["revision"] += 1
        errors = audit_tracker(preview, strict=True)
        items = [row for row in preview["work_items"] if row["id"] in captured]
        _emit({"ok": not errors, "dry_run": True, "revision": tracker["revision"], "work_items": items, "errors": errors})
        return 0 if not errors else 1
    updated = mutate(tracker_path(root), arguments.expected_revision, add)
    write_snapshot(root, updated)
    items = [row for row in updated["work_items"] if row["id"] in captured]
    _emit({"ok": True, "revision": updated["revision"], "work_items": items})
    return 0


def _recon_partial_candidates(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _recon_text, _root
    from .constants import tracker_path
    from .recon_partial import candidates_text, partial_candidates
    from .recon_scan import fingerprint_inputs
    from .tracker import load_tracker
    from .util import load_json

    root = _root(arguments)
    signatures = type_rows = None
    if arguments.fingerprint:
        fingerprint = load_json(_build_path(root, arguments.fingerprint, "fingerprints"))
        signatures, paths = fingerprint_inputs(fingerprint)
        type_rows = [{"name": name, "path": path} for name, values in paths.items() for path in values]
    result = partial_candidates(
        root,
        load_tracker(tracker_path(root)),
        groups=arguments.groups,
        signatures=signatures,
        type_rows=type_rows,
        bridge_url=arguments.bridge_url,
        log=lambda message: print(message, file=sys.stderr, flush=True),
    )
    return _recon_text(root, arguments, candidates_text(result))


def _recon_global_facts(arguments: argparse.Namespace) -> int:
    from .cli import _recon_text, _root
    from .constants import tracker_path
    from .recon_globals import global_facts, global_facts_text, qualifier_globals
    from .tracker import load_tracker
    from .util import SocomError, canonical_json

    root = _root(arguments)
    if arguments.item:
        item_id = arguments.item.removesuffix("-apply")
        item = next((row for row in load_tracker(tracker_path(root))["work_items"] if row["id"] == item_id), None)
        if item is None or item.get("kind") != "recon-repair-plan":
            raise SocomError(f"{arguments.item} is not a recon repair item")
        addresses = list((item.get("batch") or {}).get("globals") or [])
        if not addresses:
            raise SocomError(f"{arguments.item} lists no globals")
    elif arguments.qualifier:
        addresses = [f"0x{value:x}" for value in qualifier_globals(root, arguments.qualifier)]
        if not addresses:
            raise SocomError(f"no sized .symtab object has the demangled qualifier {arguments.qualifier!r}")
    else:
        addresses = arguments.address
    report = global_facts(root, addresses)
    text = canonical_json(report) if arguments.json else global_facts_text(report)
    return _recon_text(root, arguments, text)
