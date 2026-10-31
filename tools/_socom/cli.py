"""Command-line interface for the soCOM reconstruction workspace."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import audits
from .capabilities import CAPABILITIES, capability_document
from .census import build_census, require_valid_census, verify_census
from .constants import (
    EXPECTED_GHIDRA_VERSION,
    STAGES,
    agent_dir,
    tracker_path,
    workspace_root,
)
from .doctor import run_doctor
from .dwarf1 import Dwarf1Debug, Dwarf1Line, debug_summary, line_summary
from .elf import Elf32File
from .functional import list_targets, run_target
from .final_catalog import final_elf_catalog
from .import_plan import build_import_plan
from .repairs import REPAIRS, repair_labels, repair_signatures
from .guards import GUARDS, run_guard, source_placement
from .issues import (
    add_issue,
    audit_issues,
    load_issues,
    mutate_issues,
    set_issue_status,
)
from .reference import query_relocations
from .ghidra import (
    GhidraBridge,
    _data_index,
    _function_index,
    _type_index,
    data_overlaps,
    live_preflight,
    load_receipt_scope,
    map_zero_fill,
    semantic_receipt,
)
from .batch_apply import BatchFailure, build_batch_program, execute_batch_program
from .recon import (
    RECON_GROUP_SIZE,
    RECON_PLAN_KIND,
    build_recon_program,
    group_evidence,
    recon_groups,
    recon_program_summary,
    validate_recon_plan,
)
from .fingerprint import SWEEP_MODES, compare_fingerprints, program_fingerprint
from .type_apply import ApplyFailure, build_apply_program, execute_apply_program
from . import provider_archive, recon_repair_cli, source_apply_cli, source_gate_cli, source_plan_cli, type_plan_cli
from .source import (
    audit_docblocks,
    audit_independence,
    audit_source_trace,
    source_artifacts,
    source_owners,
)
from .source_apply import verify_source_apply
from .source_graph import SEGMENT_SIZE as SOURCE_SEGMENT_SIZE, segments_markdown, source_graph
from .source_plan import SOURCE_APPLY_KINDS, SOURCE_STAGE, apply_reservations
from .snapshot import snapshot_status, write_snapshot
from .toolchain import bootstrap_toolchain, verify_toolchain
from .tracker import (
    accept_ghidra_work,
    accept_work,
    audit_tracker,
    claim_work,
    find_rows,
    handoff_ghidra_work,
    handoff_work,
    heartbeat_work,
    initialize_tracker,
    load_tracker,
    add_repair_item,
    migrate_tracker,
    mutate,
    next_work,
    rebaseline_ghidra_target,
    record_stage_baseline,
    refresh_ready_and_stages,
    scope_sha256,
    stage_live_scope,
    decompose_reconstruction,
    decompose_source_correlation,
    reject_work,
    reopen_work,
    release_work,
    require_ghidra_lease,
    require_revision,
    work_packet,
)
from .util import (
    SocomError,
    atomic_write_json,
    atomic_write_text,
    canonical_json,
    load_json,
    sha256_file,
)
from .verify import compare_elf


@dataclass(frozen=True)
class CommandSpec:
    path: str
    category: str
    summary: str
    mutates: bool = False
    ghidra_requirement: str = "none"
    mutates_ghidra: bool = False

    @property
    def needs_ghidra(self) -> bool:
        """Compatibility view for older command-registry consumers."""

        return self.ghidra_requirement != "none"


def _spec(
    path: str,
    category: str,
    summary: str,
    *,
    mutates: bool = False,
    ghidra_requirement: str = "none",
    mutates_ghidra: bool = False,
) -> CommandSpec:
    if ghidra_requirement not in {"none", "optional", "required"}:
        raise ValueError(f"invalid Ghidra requirement: {ghidra_requirement}")
    return CommandSpec(
        path,
        category,
        summary,
        mutates,
        ghidra_requirement,
        mutates_ghidra,
    )


def _emit(value: Any) -> None:
    """Write one JSON document to stdout as UTF-8 without a byte-order mark.

    The bytes go to the binary buffer, so neither the console code page nor
    a ``PYTHONIOENCODING`` such as ``utf-8-sig`` changes them.  (A Windows
    PowerShell 5.1 ``>`` redirect re-encodes native output and adds its own
    BOM; redirect through ``cmd /c`` or read the output in memory instead.)
    """

    text = canonical_json(value)
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def _root(arguments: argparse.Namespace) -> Path:
    return Path(arguments.root).resolve()


def _census_path(root: Path) -> Path:
    return agent_dir(root) / "REFERENCE_CENSUS.json"


def _reference_census(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    census = build_census(root, include_rows=not arguments.summary_only)
    errors = verify_census(census)
    if arguments.write:
        if arguments.summary_only:
            raise SocomError("--write cannot be combined with --summary-only")
        require_valid_census(census)
        atomic_write_json(_census_path(root), census)
    _emit(
        census
        if arguments.output_rows
        else {
            "ok": not errors,
            "written": (
                _census_path(root).relative_to(root).as_posix()
                if arguments.write
                else None
            ),
            "errors": errors,
            "reference": census["reference"],
            "elf_header": census["elf_header"],
            "section_count": len(census["sections"]),
            "symbol_summary": {
                key: value
                for key, value in census["symbol_summary"].items()
                if key != "alias_groups"
            },
            "relocation_summary": {
                key: value
                for key, value in census["relocation_summary"].items()
                if key not in {"hi16_lo16_groups", "unmatched_hi16_indices", "unmatched_lo16_indices"}
            },
            "debug": {
                key: value
                for key, value in census["debug"].items()
                if key not in {"compile_units", "named_types", "source_paths"}
            },
            "line": {
                key: value for key, value in census["line"].items() if key != "units"
            },
            "source_correlation": {
                key: value
                for key, value in census["source_correlation"].items()
                if key != "rows"
            },
        }
    )
    return 0 if not errors else 1


def _reference_verify(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    census = build_census(root, include_rows=True)
    errors = verify_census(census)
    stored = _census_path(root)
    stored_match = None
    if stored.is_file():
        previous = load_json(stored)
        stored_match = previous == census
        if not stored_match:
            errors.append(
                "stored reference census differs from a complete live parse "
                "(including symbols, relocations, debug rows, and line rows)"
            )
    else:
        errors.append("stored .agent/REFERENCE_CENSUS.json is missing")
    _emit({"ok": not errors, "stored_match": stored_match, "errors": errors})
    return 0 if not errors else 1


def _reference_show(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    census = load_json(_census_path(root))
    if arguments.section:
        rows = [row for row in census["sections"] if row["name"] == arguments.section]
        if not rows:
            raise SocomError(f"unknown section: {arguments.section}")
        _emit(rows[0])
    elif arguments.symbol is not None:
        query = arguments.symbol.casefold()
        rows = [
            row
            for row in census.get("symbols", [])
            if query in str(row["name"]).casefold()
        ][: arguments.limit]
        _emit({"count": len(rows), "rows": rows})
    else:
        _emit(census)
    return 0


def _reference_relocations(arguments: argparse.Namespace) -> int:
    census = load_json(_census_path(_root(arguments)))
    report = query_relocations(
        census,
        at=arguments.at,
        size=arguments.size,
        symbol=arguments.symbol,
        relocation_type=arguments.type,
        limit=arguments.limit,
    )
    _emit(report)
    return 0


def _debug_inspect(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    elf = Elf32File(root / "support" / "socom.elf")
    dies = Dwarf1Debug(elf.section_data(".debug")).parse(strict=True)
    units = Dwarf1Line(elf.section_data(".line")).parse()
    summary = {
        "debug": debug_summary(dies),
        "line": line_summary(units),
    }
    if not arguments.rows:
        summary["debug"] = {
            key: value
            for key, value in summary["debug"].items()
            if key not in {"compile_units", "named_types", "source_paths"}
        }
        summary["line"] = {
            key: value for key, value in summary["line"].items() if key != "units"
        }
    _emit(summary)
    return 0


def _resolve_batch(root: Path, batch_id: str | None) -> dict[str, Any] | None:
    if not batch_id:
        return None
    tracker = load_tracker(tracker_path(root))
    item = next(
        (row for row in tracker["work_items"] if row["id"] == batch_id), None
    )
    if not item:
        raise SocomError(f"unknown work item/batch: {batch_id}")
    return {
        "work_item_id": item["id"],
        "selection": item.get("selection"),
        **(item.get("batch") or {}),
    }


def _debug_import_plan(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    batch = _resolve_batch(root, arguments.batch)
    plan = build_import_plan(root, batch)
    selection = (batch or {}).get("selection")
    if selection == "types":
        plan["functions"] = []
        plan["variables"] = []
        plan["summary"]["function_count"] = 0
        plan["summary"]["variable_count"] = 0
    if arguments.output:
        output = Path(arguments.output)
        if not output.is_absolute():
            output = root / output
        # Import plans are disposable generated artifacts; refuse to overwrite
        # project inputs or control state.
        allowed = (root / "build").resolve()
        try:
            output.resolve().relative_to(allowed)
        except ValueError as exc:
            raise SocomError("import plans may only be written under build/") from exc
        atomic_write_json(output, plan)
    _emit(
        plan
        if arguments.rows
        else {
            "kind": plan["kind"],
            "mutation_performed": False,
            "target": plan["target"],
            "receipt_scope": plan["receipt_scope"],
            "batch": plan["batch"],
            "selected_die_count": plan["selected_die_count"],
            "application_order": plan["application_order"],
            "summary": plan["summary"],
            "output": arguments.output,
        }
    )
    return 0


def _debug_conflicts(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    batch = _resolve_batch(root, arguments.batch)
    plan = build_import_plan(root, batch)
    row_limit = max(0, arguments.limit)
    member_limit = max(0, arguments.member_limit)
    rows = []
    for conflict in plan["conflicts"][:row_limit]:
        type_ids = conflict.get("type_plan_ids", [])
        rows.append(
            {
                **{key: value for key, value in conflict.items() if key != "type_plan_ids"},
                "type_plan_count": len(type_ids),
                "type_plan_ids": type_ids[:member_limit],
                "omitted_type_plan_ids": max(
                    0, len(type_ids) - member_limit
                ),
            }
        )
    _emit(
        {
            "ok": not plan["conflicts"],
            "mutation_performed": False,
            "batch": plan["batch"],
            "count": len(plan["conflicts"]),
            "rows": rows,
            "omitted": max(0, len(plan["conflicts"]) - len(rows)),
        }
    )
    return 0 if not plan["conflicts"] else 1


def _ghidra_preflight(arguments: argparse.Namespace) -> int:
    report = live_preflight(
        _root(arguments),
        bridge_url=arguments.bridge_url,
        # Bootstrap counts bind only while the tracker target is
        # bootstrap-r5900; accepted live reconstruction changes them.
        strict_baseline=None if arguments.strict else False,
    )
    _emit(report)
    return 0 if report["ok"] else 1


def _ghidra_data_overlap(arguments: argparse.Namespace) -> int:
    report = data_overlaps(
        _root(arguments),
        bridge_url=arguments.bridge_url,
        addresses=tuple(arguments.address),
        limit=arguments.limit,
    )
    _emit(report)
    return 0 if report["ok"] else 1


def _ghidra_receipt(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    scope = None
    if arguments.scope:
        scope_path = Path(arguments.scope)
        if not scope_path.is_absolute():
            scope_path = root / scope_path
        scope = load_receipt_scope(scope_path)
    report = semantic_receipt(
        root,
        bridge_url=arguments.bridge_url,
        scope=scope,
    )
    if arguments.output:
        output = Path(arguments.output)
        if not output.is_absolute():
            output = root / output
        try:
            output.resolve().relative_to((root / "build").resolve())
        except ValueError as exc:
            raise SocomError("Ghidra receipts may only be written under build/") from exc
        atomic_write_json(output, report)
    _emit(report)
    return 0


def _build_path(root: Path, value: str, what: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    try:
        path.resolve().relative_to((root / "build").resolve())
    except ValueError as exc:
        raise SocomError(f"{what} may only be written under build/") from exc
    return path


def _debug_apply_program(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    plan_path = Path(arguments.plan)
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    program = build_apply_program(root, plan_path)
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "apply programs"), program)
    _emit(
        {
            "kind": program["kind"],
            "mutation_performed": False,
            "plan": program["plan"],
            "summary": program["summary"],
            "omissions": program["omissions"],
            "output": arguments.output,
        }
    )
    return 0


def _ghidra_apply_types(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    program_path = Path(arguments.program)
    if not program_path.is_absolute():
        program_path = root / program_path
    program = load_json(program_path)
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "apply reports")

    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    plan_info = program.get("plan") or {}
    plan_item_id = plan_info.get("work_item_id")
    if plan_item_id not in item.get("dependencies", []):
        raise SocomError(f"{arguments.item} does not depend on plan item {plan_item_id}")
    plan_item = next(
        (row for row in tracker["work_items"] if row["id"] == plan_item_id), None
    )
    if not plan_item or plan_item.get("status") != "accepted":
        raise SocomError(f"plan item {plan_item_id} is not accepted")
    plan_sha256 = str(plan_info.get("sha256", ""))
    cited = [
        text
        for text in plan_item.get("evidence", [])
        + ((plan_item.get("handoff") or {}).get("evidence") or [])
        if isinstance(text, str)
    ]
    if len(plan_sha256) != 64 or not any(plan_sha256 in text for text in cited):
        raise SocomError("the accepted plan item does not cite this plan's SHA-256")
    plan_path = root / plan_info["path"]
    if sha256_file(plan_path) != plan_sha256:
        raise SocomError("the plan file no longer matches the apply program")
    if canonical_json(build_apply_program(root, plan_path)) != canonical_json(program):
        raise SocomError("the apply program is stale or edited; regenerate it")

    preflight = live_preflight(
        root, bridge_url=arguments.bridge_url, strict_baseline=False
    )
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
    try:
        result = execute_apply_program(
            program,
            bridge,
            type_index=lambda: _type_index(bridge),
            log=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except ApplyFailure as failure:
        report = {
            "kind": "socom-ghidra-type-apply-report",
            "schema_version": 1,
            "ok": False,
            "work_item_id": arguments.item,
            "error": str(failure),
            "completed_steps": failure.completed_steps,
            "details": failure.details,
            "recovery": "close socom.elf without saving and reopen it before retrying",
        }
        atomic_write_json(report_output, report)
        _emit({key: value for key, value in report.items() if key != "details"})
        return 1
    atomic_write_json(scope_output, program["receipt_scope"])
    report = {
        "kind": "socom-ghidra-type-apply-report",
        "schema_version": 1,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        "program_sha256": hashlib.sha256(
            canonical_json(program).encode("utf-8")
        ).hexdigest(),
        "plan": program["plan"],
        "result": result,
        "decisions": program["decisions"],
        "omissions": program["omissions"],
        "summary": program["summary"],
        "scope_output": scope_output.relative_to(root).as_posix(),
    }
    atomic_write_json(report_output, report)
    _emit({"ok": True, **report})
    return 0


def _debug_batch_program(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    plan_path = Path(arguments.plan)
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    program = build_batch_program(root, plan_path)
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "batch programs"), program)
    _emit(
        {
            "kind": program["kind"],
            "mutation_performed": False,
            "plan": program["plan"],
            "summary": program["summary"],
            "output": arguments.output,
        }
    )
    return 0


def _require_accepted_plan(
    root: Path, tracker: dict[str, Any], item: dict[str, Any], program: dict[str, Any]
) -> Path:
    plan_info = program.get("plan") or {}
    plan_item_id = plan_info.get("work_item_id")
    if plan_item_id not in item.get("dependencies", []):
        raise SocomError(f"{item['id']} does not depend on plan item {plan_item_id}")
    plan_item = next((row for row in tracker["work_items"] if row["id"] == plan_item_id), None)
    if not plan_item or plan_item.get("status") != "accepted":
        raise SocomError(f"plan item {plan_item_id} is not accepted")
    plan_sha256 = str(plan_info.get("sha256", ""))
    cited = [
        text
        for text in plan_item.get("evidence", [])
        + ((plan_item.get("handoff") or {}).get("evidence") or [])
        if isinstance(text, str)
    ]
    if len(plan_sha256) != 64 or not any(plan_sha256 in text for text in cited):
        raise SocomError("the accepted plan item does not cite this plan's SHA-256")
    plan_path = root / plan_info["path"]
    if sha256_file(plan_path) != plan_sha256:
        raise SocomError("the plan file no longer matches the program")
    return plan_path


def _global_names(root: Path, bridge: GhidraBridge) -> dict[str, set[str]]:
    """Symbol names in use, by address: every ELF .symtab name plus the
    primary name of every defined data item (which carries earlier batches'
    renames).  The bridge has no complete read-only symbol listing, so a
    renamed label on bytes without defined data is not seen here."""

    names: dict[str, set[str]] = {}
    for symbol in Elf32File(root / "support" / "socom.elf").symbols():
        if symbol.name and symbol.value:
            names.setdefault(symbol.name, set()).add(f"0x{symbol.value:x}")
    for row in _data_index(bridge):
        if row.get("name") and "::" not in str(row["address"]).replace("0x", ""):
            names.setdefault(row["name"], set()).add(f"0x{int(str(row['address']), 16):x}")
    return names


class _ReadOnlyBridge:
    """Bridge view for dry runs: GETs pass through; every POST is refused."""

    def __init__(self, bridge: GhidraBridge) -> None:
        self._bridge = bridge

    def request(self, endpoint: str, **params: Any) -> Any:
        return self._bridge.request(endpoint, **params)

    def post_json(self, endpoint: str, **body: Any) -> Any:
        raise SocomError(f"dry run attempted a bridge write: {endpoint}")


def _accepted_scope_globals(tracker: dict[str, Any], exclude: str | None) -> frozenset[str]:
    """Globals in the stored receipt scope of every accepted batch apply.

    DWARF batch applies, reconstruction group applies and recon repairs of
    globals type globals; the zero-fill map's scope lists every .bss object
    and a label repair types nothing.
    """

    addresses: set[str] = set()
    for item in tracker["work_items"]:
        if item["id"] == exclude or item.get("status") != "accepted":
            continue
        if item.get("kind") not in ("debug-import-apply-batch", "recon-apply-group", "recon-repair-apply"):
            continue
        for value in ((item.get("ghidra_receipt") or {}).get("scope") or {}).get("globals", []):
            if "::" not in value:
                addresses.add(f"0x{int(value, 16):x}")
    return frozenset(addresses)


def _batch_scope_problems(
    program: dict[str, Any], result: dict[str, Any], live_types: set[str] | None = None
) -> list[str]:
    scope = program["receipt_scope"]
    problems = []
    if live_types is not None:
        for path in scope.get("types", []):
            if path not in live_types:
                problems.append(f"scope type {path} does not exist live")
    functions = {int(value, 16) for value in scope.get("functions", [])}
    globals_ = {int(value, 16) for value in scope.get("globals", [])}
    for step in result["steps"]:
        address = step["body"].get("address") or step["body"].get("function_address")
        if address is None:
            continue
        value = int(str(address), 16)
        if value not in functions and value not in globals_:
            problems.append(f"{step['endpoint']} writes 0x{value:x} outside the receipt scope")
    program_functions = {int(row["address"], 16) for row in program["functions"]}
    program_globals = {int(row["address"], 16) for row in program.get("globals", [])}
    for value in sorted(functions - program_functions):
        problems.append(f"scope function 0x{value:x} is not in the program")
    for value in sorted(globals_ - program_globals):
        problems.append(f"scope global 0x{value:x} is not in the program")
    return problems


def _ghidra_preflight_batch(arguments: argparse.Namespace) -> int:
    """Dry-run a batch program against live Ghidra without writing anything."""

    root = _root(arguments)
    program_path = Path(arguments.program)
    if not program_path.is_absolute():
        program_path = root / program_path
    program = load_json(program_path)
    output = _build_path(root, arguments.output, "batch preflight reports") if arguments.output else None
    errors: list[str] = []
    plan_info = program.get("plan") or {}
    plan_path = root / str(plan_info.get("path", ""))
    tracker = load_tracker(tracker_path(root))
    recon = False
    if not plan_path.is_file() or sha256_file(plan_path) != plan_info.get("sha256"):
        errors.append("the plan file is missing or no longer matches the program")
    else:
        # Stage 3 plans regenerate through the reconstruction builder.
        recon = load_json(plan_path).get("kind") == RECON_PLAN_KIND
        try:
            rebuilt = build_recon_program(root, tracker, plan_path) if recon else build_batch_program(root, plan_path)
        except SocomError as failure:
            errors.append(f"the program does not regenerate from its plan: {failure}")
        else:
            if canonical_json(rebuilt) != canonical_json(program):
                errors.append("the batch program is stale or edited; regenerate it")
    plan_item = next((row for row in tracker["work_items"] if row["id"] == plan_info.get("work_item_id")), None)
    accepted = _accepted_scope_globals(tracker, f"{plan_info.get('work_item_id')}-apply")
    if recon:
        # The same exemption apply-recon grants a deliberate correction.
        accepted = frozenset(accepted - {row["address"] for row in program.get("globals", []) if row.get("replaces_accepted")})
    preflight = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        errors.extend(preflight["errors"])
    result: dict[str, Any] | None = None
    if not errors:
        bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
        before = bridge.request("analysis_status")
        try:
            result = execute_batch_program(
                program,
                _ReadOnlyBridge(bridge),
                type_index=lambda: _type_index(bridge),
                function_names=lambda: {
                    f"0x{int(row['address'], 16):x}": row["name"]
                    for row in _function_index(bridge)
                    if "::" not in row["address"]
                },
                global_names=lambda: _global_names(root, bridge),
                log=lambda message: print(message, file=sys.stderr, flush=True),
                dry_run=True,
                accepted_globals=frozenset(accepted),
            )
        except SocomError as failure:
            errors.append(f"the apply would refuse or fail: {failure}")
        after = bridge.request("analysis_status")
        if before != after:
            errors.append(f"analysis state changed during the dry run: {before!r} -> {after!r}")
        if result is not None:
            live_types = {row["path"] for row in _type_index(bridge) if row.get("path")}
            errors.extend(_batch_scope_problems(program, result, live_types))
    report = {
        "kind": "socom-ghidra-batch-preflight",
        "schema_version": 1,
        "ok": not errors,
        "errors": errors,
        "program_sha256": hashlib.sha256(canonical_json(program).encode("utf-8")).hexdigest(),
        "plan": plan_info,
        "plan_item_status": (plan_item or {}).get("status"),
        "summary": program.get("summary"),
    }
    if result is not None:
        report.update(
            {
                "bridge_call_count": result["bridge_call_count"],
                "planned_calls": result["planned_calls"],
                "skipped": result["skipped"],
                "unchanged": result["unchanged"],
                "steps": result["steps"],
            }
        )
    if output:
        atomic_write_json(output, report)
    _emit({key: value for key, value in report.items() if key != "steps"})
    return 0 if report["ok"] else 1


def _ghidra_fingerprint(arguments: argparse.Namespace) -> int:
    """Fingerprint all of live socom.elf; optionally diff it against an earlier one."""

    root = _root(arguments)
    output = _build_path(root, arguments.output, "Ghidra fingerprints")
    baseline = None
    if arguments.compare:
        compare_path = Path(arguments.compare)
        if not compare_path.is_absolute():
            compare_path = root / compare_path
        baseline = load_json(compare_path)
    started = time.monotonic()
    fingerprint = program_fingerprint(
        root,
        bridge_url=arguments.bridge_url,
        log=lambda message: print(f"[{time.monotonic() - started:7.1f}s] {message}", file=sys.stderr, flush=True),
        sweep_mode=arguments.sweep_mode,
    )
    atomic_write_json(output, fingerprint)
    report: dict[str, Any] = {
        "ok": True,
        "output": output.relative_to(root).as_posix(),
        "fingerprint_sha256": fingerprint["fingerprint_sha256"],
        "counts": fingerprint["counts"],
        "digests": fingerprint["digests"],
    }
    if baseline is not None:
        diff = compare_fingerprints(baseline, fingerprint)
        if arguments.diff_output:
            atomic_write_json(_build_path(root, arguments.diff_output, "fingerprint diffs"), diff)
        report["diff"] = {
            "identical": diff["identical"],
            "sections_changed": diff["sections_changed"],
            "functions_changed": len(diff["functions"]),
            "data": {key: len(value) for key, value in diff["data"].items()},
            "types": {key: len(value) for key, value in diff["types"].items()},
            "references": {key: len(value) for key, value in diff["references"].items()},
            "bookmarks_equal": diff["bookmarks_equal"],
            "blocks_equal": diff["blocks_equal"],
        }
    _emit(report)
    return 0


def _ghidra_apply_batch(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    program_path = Path(arguments.program)
    if not program_path.is_absolute():
        program_path = root / program_path
    program = load_json(program_path)
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "apply reports")
    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    if item.get("kind") != "debug-import-apply-batch":
        raise SocomError(f"{arguments.item} is not a batch apply item")
    plan_path = _require_accepted_plan(root, tracker, item, program)
    if canonical_json(build_batch_program(root, plan_path)) != canonical_json(program):
        raise SocomError("the batch program is stale or edited; regenerate it")
    preflight = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
    try:
        result = execute_batch_program(
            program,
            bridge,
            type_index=lambda: _type_index(bridge),
            function_names=lambda: {
                f"0x{int(row['address'], 16):x}": row["name"]
                for row in _function_index(bridge)
                if "::" not in row["address"]
            },
            global_names=lambda: _global_names(root, bridge),
            log=lambda message: print(message, file=sys.stderr, flush=True),
            accepted_globals=_accepted_scope_globals(tracker, arguments.item),
        )
    except BatchFailure as failure:
        report = {
            "kind": "socom-ghidra-batch-apply-report",
            "schema_version": 1,
            "ok": False,
            "work_item_id": arguments.item,
            "error": str(failure),
            "completed_steps": failure.completed_steps,
            "details": failure.details,
            "recovery": "close socom.elf without saving and reopen it before retrying",
        }
        atomic_write_json(report_output, report)
        _emit({key: value for key, value in report.items() if key != "details"})
        return 1
    atomic_write_json(scope_output, program["receipt_scope"])
    report = {
        "kind": "socom-ghidra-batch-apply-report",
        "schema_version": 1,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        "program_sha256": hashlib.sha256(canonical_json(program).encode("utf-8")).hexdigest(),
        "plan": program["plan"],
        "summary": program["summary"],
        "absent_variables": program["absent_variables"],
        "result": result,
        "scope_output": scope_output.relative_to(root).as_posix(),
    }
    atomic_write_json(report_output, report)
    _emit({"ok": True, **{key: value for key, value in report.items() if key != "result"}, "skipped": result["skipped"], "bridge_call_count": result["bridge_call_count"]})
    return 0


def _ghidra_restore_accepted(arguments: argparse.Namespace) -> int:
    """Rebuild accepted live semantics on a fresh baseline import, provably.

    Used after a saved defect: the program must first equal the recorded
    baseline import receipt; each accepted Ghidra apply is then replayed from
    its accepted plan and must reproduce its accepted receipt exactly.
    """

    root = _root(arguments)
    report_output = _build_path(root, arguments.report_output, "restore reports")
    tracker = load_tracker(tracker_path(root))
    require_ghidra_lease(tracker, arguments.item, arguments.owner)
    target = next(
        row
        for row in tracker["verification_targets"]
        if row["id"] == "socom:verification:ghidra-program"
    )
    current = semantic_receipt(root, bridge_url=arguments.bridge_url)
    if current["receipt_sha256"] != target["baseline_receipt_sha256"]:
        raise SocomError(
            "the live program is not the recorded baseline import "
            f"({current['receipt_sha256']} != {target['baseline_receipt_sha256']})"
        )
    replayed = []
    bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
    for item in tracker["work_items"]:
        if item.get("status") != "accepted" or "ghidra-writer" not in item.get("resources", []):
            continue
        if item["kind"] != "debug-import-apply-foundation":
            raise SocomError(f"no replay route for accepted {item['kind']} item {item['id']}")
        plan_id = item["dependencies"][0]
        plan_path = root / "build" / "import-plans" / f"{plan_id.replace(':', '-')}.json"
        program = build_apply_program(root, plan_path)
        _require_accepted_plan(root, tracker, item, program)
        program_sha256 = hashlib.sha256(canonical_json(program).encode("utf-8")).hexdigest()
        if program_sha256 not in json.dumps(item):
            raise SocomError(f"{item['id']} never cited apply program {program_sha256}")
        print(f"replaying {item['id']}", file=sys.stderr, flush=True)
        result = execute_apply_program(
            program,
            bridge,
            type_index=lambda: _type_index(bridge),
            log=lambda message: print(message, file=sys.stderr, flush=True),
        )
        stored = item["ghidra_receipt"]
        receipt = semantic_receipt(root, bridge_url=arguments.bridge_url, scope=stored["scope"])
        if receipt["receipt_sha256"] != stored["receipt_sha256"]:
            raise SocomError(
                f"replaying {item['id']} gives receipt {receipt['receipt_sha256']}, "
                f"accepted {stored['receipt_sha256']}"
            )
        replayed.append(
            {
                "work_item_id": item["id"],
                "program_sha256": program_sha256,
                "receipt_sha256": receipt["receipt_sha256"],
                "bridge_call_count": result["bridge_call_count"],
            }
        )
    report = {
        "kind": "socom-ghidra-restore-report",
        "schema_version": 1,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        "baseline_receipt_sha256": target["baseline_receipt_sha256"],
        "replayed": replayed,
    }
    atomic_write_json(report_output, report)
    _emit({"ok": True, **report})
    return 0


def _ghidra_map_zero_fill(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "memory-map reports")
    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    if item.get("kind") != "ghidra-memory-map":
        raise SocomError(f"{arguments.item} is not a ghidra-memory-map item")
    try:
        report = map_zero_fill(
            root,
            bridge_url=arguments.bridge_url,
            log=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except SocomError as failure:
        report = {
            "kind": "socom-ghidra-memory-map-report",
            "schema_version": 1,
            "ok": False,
            "work_item_id": arguments.item,
            "error": str(failure),
            "recovery": "close socom.elf without saving and reopen it before retrying",
        }
        atomic_write_json(report_output, report)
        _emit(report)
        return 1
    atomic_write_json(scope_output, report["receipt_scope"])
    result = {
        "kind": "socom-ghidra-memory-map-report",
        "schema_version": 1,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        **{key: value for key, value in report.items() if key != "receipt_scope"},
        "receipt_scope_global_count": len(report["receipt_scope"]["globals"]),
        "scope_output": scope_output.relative_to(root).as_posix(),
    }
    atomic_write_json(report_output, result)
    _emit(result)
    return 0


def _ghidra_repair(arguments: argparse.Namespace, kind: str, run: Callable[..., dict[str, Any]]) -> int:
    root = _root(arguments)
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "repair reports")
    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    if item.get("kind") != "ghidra-repair":
        raise SocomError(f"{arguments.item} is not a ghidra-repair item")
    if REPAIRS.get(arguments.item, {}).get("kind") != kind:
        raise SocomError(f"{arguments.item} is not a {kind} repair")
    preflight = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    try:
        result = run(
            arguments.item,
            GhidraBridge(arguments.bridge_url, timeout=300.0),
            log=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except SocomError as failure:
        report = {
            "kind": "socom-ghidra-repair-report",
            "schema_version": 1,
            "ok": False,
            "work_item_id": arguments.item,
            "error": str(failure),
            "recovery": "close socom.elf without saving and reopen it before retrying",
        }
        atomic_write_json(report_output, report)
        _emit(report)
        return 1
    atomic_write_json(scope_output, result["receipt_scope"])
    report = {
        "kind": "socom-ghidra-repair-report",
        "schema_version": 1,
        "ok": True,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        **{key: value for key, value in result.items() if key != "receipt_scope"},
        "scope_output": scope_output.relative_to(root).as_posix(),
    }
    atomic_write_json(report_output, report)
    _emit(report)
    return 0


def _ghidra_check_names_repair(arguments: argparse.Namespace) -> int:
    from .recon_check import check_names_repair

    root = _root(arguments)
    result = check_names_repair(
        root,
        arguments.label,
        arguments.prev,
        fingerprint_output=_build_path(root, arguments.fingerprint_output, "fingerprints"),
        bridge_url=arguments.bridge_url,
        log=lambda message: print(message, file=sys.stderr, flush=True),
    )
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "repair checks"), result)
    _emit(result)
    return 0 if result["ok"] else 1


def _ghidra_repair_names(arguments: argparse.Namespace) -> int:
    """Rename mangled functions to their readable names (REPAIRS kind "names")."""

    from .readable_names import readable_names_program

    root = _root(arguments)
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "repair reports")
    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    if item.get("kind") != "ghidra-repair" or REPAIRS.get(arguments.item, {}).get("kind") != "names":
        raise SocomError(f"{arguments.item} is not a names repair")
    preflight = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    program = readable_names_program(root)
    program_path = report_output.with_name(report_output.stem + "-program.json")
    atomic_write_json(program_path, program)
    bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
    try:
        result = execute_batch_program(
            program,
            _ReadOnlyBridge(bridge) if arguments.dry_run else bridge,
            type_index=lambda: _type_index(bridge),
            function_names=lambda: {
                f"0x{int(row['address'], 16):x}": row["name"]
                for row in _function_index(bridge)
                if "::" not in row["address"]
            },
            log=lambda message: print(message, file=sys.stderr, flush=True),
            dry_run=arguments.dry_run,
        )
    except (BatchFailure, SocomError) as failure:
        report = {
            "kind": "socom-ghidra-repair-report",
            "schema_version": 1,
            "ok": False,
            "dry_run": arguments.dry_run,
            "work_item_id": arguments.item,
            "error": str(failure),
            "recovery": "a dry run wrote nothing; after a real run close socom.elf without saving and reopen it",
        }
        atomic_write_json(report_output, report)
        _emit(report)
        return 1
    if not arguments.dry_run:
        atomic_write_json(scope_output, program["receipt_scope"])
    report = {
        "kind": "socom-ghidra-repair-report",
        "schema_version": 1,
        "ok": True,
        "dry_run": arguments.dry_run,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        "program": program_path.relative_to(root).as_posix(),
        "program_sha256": program["program_sha256"],
        "summary": program["summary"],
        "result": result,
        "scope_output": None if arguments.dry_run else scope_output.relative_to(root).as_posix(),
    }
    atomic_write_json(report_output, report)
    _emit(
        {
            key: value
            for key, value in report.items()
            if key not in ("result", "summary")
        }
        | {
            "bridge_call_count": result["bridge_call_count"],
            "unchanged": len(result.get("unchanged", [])),
            "skipped": len(result.get("skipped", [])),
            "renamed_planned": program["summary"]["function_count"],
        }
    )
    return 0


def _ghidra_repair_signatures(arguments: argparse.Namespace) -> int:
    return _ghidra_repair(arguments, "signatures", repair_signatures)


def _ghidra_repair_boundaries(arguments: argparse.Namespace) -> int:
    """Rejoin the split function boundaries with the pinned one-time script (REPAIRS kind "boundaries")."""

    from .boundary_repair import repair_boundaries

    root = _root(arguments)
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "repair reports")
    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    if item.get("kind") != "ghidra-repair" or REPAIRS.get(arguments.item, {}).get("kind") != "boundaries":
        raise SocomError(f"{arguments.item} is not a boundary repair")
    preflight = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    bridge = GhidraBridge(arguments.bridge_url, timeout=600.0)
    base = {
        "kind": "socom-ghidra-repair-report",
        "schema_version": 1,
        "dry_run": arguments.dry_run,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
    }
    error: str | None = None
    wrote = False
    try:
        result = repair_boundaries(
            root,
            arguments.item,
            _ReadOnlyBridge(bridge) if arguments.dry_run else bridge,
            dry_run=arguments.dry_run,
            log=lambda message: print(message, file=sys.stderr, flush=True),
        )
    except SocomError as failure:
        error, wrote = str(failure), bool(getattr(failure, "wrote", False))
        response = getattr(failure, "response", None)
        result = {"script_response": response} if response is not None else {}
    if error is None and not arguments.dry_run:
        after = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
        if not after["ok"]:
            error, wrote = "live preflight failed after the repair: " + "; ".join(after.get("errors", [])), True
    if error is not None:
        report = base | {
            "ok": False,
            "error": error,
            "script_may_have_run": wrote,
            "recovery": (
                "close socom.elf without saving and reopen it before retrying"
                if wrote
                else "nothing was written; the live program is unchanged"
            ),
        } | result
        atomic_write_json(report_output, report)
        _emit({key: value for key, value in report.items() if key != "script_response"})
        return 1
    if arguments.dry_run:
        # The reviewed text the real run sends, and its pinned hash.
        print(f"--- {result['script']['path']} sha256 {result['script']['sha256']}", file=sys.stderr)
        print(result["source"], file=sys.stderr, end="", flush=True)
        print(f"--- args: {result['script']['arguments']}", file=sys.stderr, flush=True)
    else:
        atomic_write_json(scope_output, result["receipt_scope"])
    report = base | {
        "ok": True,
        **{key: value for key, value in result.items() if key not in ("receipt_scope", "source")},
        "scope_output": None if arguments.dry_run else scope_output.relative_to(root).as_posix(),
    }
    atomic_write_json(report_output, report)
    _emit({key: value for key, value in report.items() if key not in ("functions", "script_result")})
    return 0


def _ghidra_repair_labels(arguments: argparse.Namespace) -> int:
    return _ghidra_repair(arguments, "labels", repair_labels)


def _progress_add_repair(arguments: argparse.Namespace) -> int:
    return _mutate_work(arguments, lambda tracker: add_repair_item(tracker, arguments.item))


def _verify_asm(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    preflight = live_preflight(
        root, bridge_url=arguments.bridge_url, strict_baseline=False
    )
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    bridge = GhidraBridge(arguments.bridge_url)
    target = arguments.target
    if not target.casefold().startswith("0x"):
        inventory = bridge.request("list_functions")
        if not isinstance(inventory, str):
            raise SocomError("Ghidra function inventory is unavailable")
        matches = [
            line.rsplit(" at ", 1)[1]
            for line in inventory.splitlines()
            if line.rsplit(" at ", 1)[0] == target and " at " in line
        ]
        if len(matches) != 1:
            raise SocomError(
                f"function name must resolve exactly once: {target} "
                f"(matches={len(matches)})"
            )
        target = "0x" + matches[0]
    function = bridge.request("get_function_by_address", address=target)
    assembly = bridge.request("disassemble_function", address=target)
    _emit(
        {
            "ok": True,
            "mutation_performed": False,
            "preflight": preflight,
            "function": function,
            "assembly": assembly,
        }
    )
    return 0


def _verify_functional(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    if not arguments.target:
        rows = list_targets(root)
        _emit({"ok": True, "count": len(rows), "targets": rows})
        return 0
    report = run_target(root, arguments.target, dry_run=arguments.dry_run)
    _emit(report)
    return 0 if report["ok"] else 1


def _verify_functional_batch(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    targets = arguments.target or [row["id"] for row in list_targets(root)]
    if not targets:
        _emit(
            {
                "ok": False,
                "dry_run": arguments.dry_run,
                "count": 0,
                "reports": [],
                "error": "no functional targets are registered",
            }
        )
        return 1
    reports = [
        run_target(root, target, dry_run=arguments.dry_run) for target in targets
    ]
    _emit(
        {
            "ok": all(row["ok"] for row in reports),
            "dry_run": arguments.dry_run,
            "count": len(reports),
            "reports": reports,
        }
    )
    return 0 if all(row["ok"] for row in reports) else 1


def _progress_init(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    output = tracker_path(root)
    if output.exists() and not arguments.force:
        raise SocomError(
            f"{output.relative_to(root).as_posix()} already exists; use --force"
        )
    census_file = _census_path(root)
    census = load_json(census_file) if census_file.is_file() else build_census(root)
    require_valid_census(census)
    tracker = initialize_tracker(root, census)
    if errors := audit_tracker(tracker):
        raise SocomError("initial tracker is invalid:\n- " + "\n- ".join(errors))
    if arguments.write:
        atomic_write_json(output, tracker)
    _emit(
        {
            "ok": True,
            "written": output.relative_to(root).as_posix() if arguments.write else None,
            "revision": tracker["revision"],
            "counts": {
                key: len(tracker[key])
                for key in (
                    "symbols",
                    "relocations",
                    "owners",
                    "work_items",
                )
            },
            "next": next_work(tracker)[:1],
        }
    )
    return 0


def _progress_next(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    rows = next_work(copy.deepcopy(tracker))
    if arguments.limit:
        rows = rows[: arguments.limit]
    _emit({"revision": tracker["revision"], "count": len(rows), "work_items": rows})
    return 0


def _progress_show(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    if arguments.id:
        collections = (
            "stages",
            "symbols",
            "relocations",
            "owners",
            "types",
            "work_items",
            "blockers",
            "evidence",
        )
        matches = [
            {"collection": name, "row": row}
            for name in collections
            for row in tracker.get(name, [])
            if row.get("id") == arguments.id
        ]
        if not matches:
            raise SocomError(f"unknown tracker ID: {arguments.id}")
        _emit(matches[0])
    else:
        _emit(tracker)
    return 0


def _progress_status(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    status_counts: dict[str, int] = {}
    for item in tracker["work_items"]:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    _emit(
        {
            "revision": tracker["revision"],
            "stages": tracker["stages"],
            "work_status_counts": dict(sorted(status_counts.items())),
            "active_leases": [
                {"id": item["id"], "lease": item["lease"]}
                for item in tracker["work_items"]
                if item.get("lease")
            ],
            "next": next_work(copy.deepcopy(tracker))[:1],
        }
    )
    return 0


def _progress_sql(arguments: argparse.Namespace) -> int:
    """One read-only SELECT over build/cache/progress.sqlite, as compact text or JSON."""

    from .progress_cache import query

    result = query(_root(arguments), arguments.statement, arguments.limit)
    if arguments.format == "json":
        _emit(result)
        return 0
    sys.stdout.reconfigure(encoding="utf-8")
    print("\t".join(result["columns"]))
    for row in result["rows"]:
        print("\t".join("" if value is None else str(value) for value in row))
    if result["truncated"]:
        print(f"... (truncated at {arguments.limit} rows; use --limit)")
    return 0


def _progress_find(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    rows = find_rows(tracker, arguments.query, load_json(_census_path(root)))[: arguments.limit]
    _emit({"count": len(rows), "rows": rows})
    return 0


def _progress_audit(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    census = load_json(_census_path(root)) if arguments.strict else None
    errors = audit_tracker(tracker, strict=arguments.strict, census=census)
    if arguments.strict:
        status = snapshot_status(root, tracker)
        if not status["fresh"]:
            errors.append("README progress snapshot is stale")
    _emit({"ok": not errors, "revision": tracker["revision"], "errors": errors})
    return 0 if not errors else 1


def _progress_snapshot(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    status = snapshot_status(root, tracker)
    if arguments.write:
        write_snapshot(root, tracker)
        status = snapshot_status(root, tracker)
    _emit(
        {
            "ok": status["fresh"],
            "fresh": status["fresh"],
            "written": arguments.write,
            "revision": tracker["revision"],
        }
    )
    return 0 if status["fresh"] else 1


def _mutate_work(
    arguments: argparse.Namespace,
    operation: Callable[[dict[str, Any]], None],
) -> int:
    root = _root(arguments)
    path = tracker_path(root)
    updated = mutate(path, arguments.expected_revision, operation)
    write_snapshot(root, updated)
    item = next(
        row for row in updated["work_items"] if row["id"] == arguments.item
    )
    _emit({"ok": True, "revision": updated["revision"], "work_item": item})
    return 0


def _work_claim(arguments: argparse.Namespace) -> int:
    return _mutate_work(
        arguments,
        lambda tracker: claim_work(
            tracker, arguments.item, arguments.owner, arguments.lease_minutes
        ),
    )


def _work_heartbeat(arguments: argparse.Namespace) -> int:
    return _mutate_work(
        arguments,
        lambda tracker: heartbeat_work(
            tracker, arguments.item, arguments.owner, arguments.lease_minutes
        ),
    )


def _require_unchanged_source_apply(root: Path, tracker: dict[str, Any], item_id: str) -> None:
    """A source apply hands off and is accepted only while its record still holds."""

    item = next((row for row in tracker["work_items"] if row["id"] == item_id), None)
    if item is None or item.get("kind") not in SOURCE_APPLY_KINDS or not isinstance(item.get("source_apply"), dict):
        return
    problems = verify_source_apply(root, tracker, item)
    if problems:
        raise SocomError(f"{item_id} no longer matches its apply record: " + "; ".join(problems))


def _work_handoff(arguments: argparse.Namespace) -> int:
    root = _root(arguments)

    def operation(tracker: dict[str, Any]) -> None:
        _require_unchanged_source_apply(root, tracker, arguments.item)
        handoff_work(
            tracker,
            arguments.item,
            arguments.owner,
            arguments.summary,
            arguments.evidence,
        )

    return _mutate_work(arguments, operation)


def _work_accept(arguments: argparse.Namespace) -> int:
    root = _root(arguments)

    def operation(tracker: dict[str, Any]) -> None:
        _require_unchanged_source_apply(root, tracker, arguments.item)
        accept_work(tracker, arguments.item, arguments.accepter, arguments.evidence)

    return _mutate_work(arguments, operation)


def _work_reject(arguments: argparse.Namespace) -> int:
    return _mutate_work(
        arguments,
        lambda tracker: reject_work(
            tracker,
            arguments.item,
            arguments.reviewer,
            arguments.reason,
            arguments.evidence,
        ),
    )


def _work_reopen(arguments: argparse.Namespace) -> int:
    return _mutate_work(
        arguments,
        lambda tracker: reopen_work(
            tracker,
            arguments.item,
            arguments.reviewer,
            arguments.reason,
            arguments.evidence,
        ),
    )


def _work_release(arguments: argparse.Namespace) -> int:
    return _mutate_work(
        arguments,
        lambda tracker: release_work(tracker, arguments.item, arguments.owner),
    )


def _handoff_live_ghidra(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    scope_path = Path(arguments.scope)
    if not scope_path.is_absolute():
        scope_path = root / scope_path
    scope = load_receipt_scope(scope_path)
    captured: dict[str, Any] = {}

    def handoff_saved_program(tracker: dict[str, Any]) -> None:
        require_ghidra_lease(tracker, arguments.item, arguments.owner)
        before = semantic_receipt(
            root, bridge_url=arguments.bridge_url, scope=scope
        )
        GhidraBridge(arguments.bridge_url).save_program()
        after = semantic_receipt(
            root, bridge_url=arguments.bridge_url, scope=scope
        )
        if before["receipt_sha256"] != after["receipt_sha256"]:
            raise SocomError(
                "Ghidra semantic receipt changed while saving the program"
            )
        summary = {
            "counts": after["receipt"]["counts"],
            "indexes": after["receipt"]["indexes"],
            "bookmark_profile": after["receipt"]["bookmark_profile"],
        }
        handoff_ghidra_work(
            tracker,
            arguments.item,
            arguments.owner,
            arguments.summary,
            arguments.evidence + ["ghidra-save:explicit-program"],
            scope=scope,
            receipt_sha256=after["receipt_sha256"],
            receipt_summary=summary,
        )
        captured.update(after)

    updated = mutate(
        tracker_path(root), arguments.expected_revision, handoff_saved_program
    )
    write_snapshot(root, updated)
    item = next(row for row in updated["work_items"] if row["id"] == arguments.item)
    _emit(
        {
            "ok": True,
            "revision": updated["revision"],
            "receipt_sha256": captured["receipt_sha256"],
            "saved_program": "socom.elf",
            "work_item": item,
        }
    )
    return 0


def _advance_live_ghidra(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    captured: dict[str, Any] = {}

    def accept_live_program(tracker: dict[str, Any]) -> None:
        item = next(
            (
                row
                for row in tracker["work_items"]
                if row["id"] == arguments.item
            ),
            None,
        )
        if not item:
            raise SocomError(f"unknown work item: {arguments.item}")
        if item["status"] != "awaiting_acceptance":
            raise SocomError(
                f"{arguments.item} is {item['status']}, not awaiting_acceptance"
            )
        stored = item.get("ghidra_receipt") or {}
        scope = stored.get("scope")
        if not isinstance(scope, dict):
            raise SocomError("handed-off Ghidra receipt scope is unavailable")
        current = semantic_receipt(
            root, bridge_url=arguments.bridge_url, scope=scope
        )
        accept_ghidra_work(
            tracker,
            arguments.item,
            arguments.accepter,
            arguments.evidence,
            receipt_sha256=current["receipt_sha256"],
        )
        target = next(
            (
                row
                for row in tracker.get("verification_targets", [])
                if row.get("id")
                == "socom:verification:ghidra-program"
            ),
            None,
        )
        if target is None:
            raise SocomError("tracker has no Ghidra verification target")
        target["status"] = "live-reconstruction"
        target["current_receipt_sha256"] = current["receipt_sha256"]
        target.setdefault("receipt_history", []).append(
            {
                "tracker_revision": tracker["revision"] + 1,
                "work_item_id": arguments.item,
                "receipt_sha256": current["receipt_sha256"],
                "counts": current["receipt"]["counts"],
                "indexes": current["receipt"]["indexes"],
            }
        )
        captured.update(current)

    updated = mutate(
        tracker_path(root), arguments.expected_revision, accept_live_program
    )
    write_snapshot(root, updated)
    item = next(row for row in updated["work_items"] if row["id"] == arguments.item)
    _emit(
        {
            "ok": True,
            "revision": updated["revision"],
            "receipt_sha256": captured["receipt_sha256"],
            "saved_program": False,
            "work_item": item,
        }
    )
    return 0


def _rebaseline_live_ghidra(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    captured: dict[str, Any] = {}

    def record_baseline(tracker: dict[str, Any]) -> None:
        preflight = live_preflight(
            root, bridge_url=arguments.bridge_url, strict_baseline=True
        )
        if not preflight["ok"]:
            raise SocomError(
                "strict live Ghidra preflight failed:\n- "
                + "\n- ".join(preflight["errors"])
            )
        current = semantic_receipt(root, bridge_url=arguments.bridge_url)
        entry = rebaseline_ghidra_target(
            tracker,
            arguments.recorder,
            arguments.evidence,
            ghidra_version=EXPECTED_GHIDRA_VERSION,
            receipt_sha256=current["receipt_sha256"],
            receipt=current["receipt"],
        )
        captured.update(entry)

    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        require_revision(tracker, arguments.expected_revision)
        preview = copy.deepcopy(tracker)
        record_baseline(preview)
        errors = audit_tracker(preview)
        _emit(
            {
                "ok": not errors,
                "dry_run": True,
                "revision": tracker["revision"],
                "history_entry": captured,
                "errors": errors,
            }
        )
        return 0 if not errors else 1
    updated = mutate(tracker_path(root), arguments.expected_revision, record_baseline)
    write_snapshot(root, updated)
    _emit(
        {
            "ok": True,
            "dry_run": False,
            "revision": updated["revision"],
            "history_entry": captured,
            "saved_program": False,
        }
    )
    return 0


def _recon_graph(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    groups = recon_groups(root, arguments.group_size)
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "reconstruction graphs"), groups)
    _emit(
        {
            "mutation_performed": False,
            **{key: value for key, value in groups.items() if key != "groups"},
            "group_count": len(groups["groups"]),
            "ready_group_count": sum(1 for row in groups["groups"] if not row["callee_groups"]),
            "output": arguments.output,
        }
    )
    return 0


def _recon_evidence(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    output = _build_path(root, arguments.output, "reconstruction evidence")
    evidence = group_evidence(root, load_tracker(tracker_path(root)), arguments.item)
    atomic_write_json(output, evidence)
    _emit(
        {
            "mutation_performed": False,
            "work_item_id": arguments.item,
            "group_sha256": evidence["group_sha256"],
            "function_count": len(evidence["functions"]),
            "output": output.relative_to(root).as_posix(),
            "sha256": sha256_file(output),
        }
    )
    return 0


def _recon_addresses(root: Path, arguments: argparse.Namespace) -> list[int]:
    if getattr(arguments, "item", None):
        tracker = load_tracker(tracker_path(root))
        item_id = arguments.item.removesuffix("-apply")
        item = next((row for row in tracker["work_items"] if row["id"] == item_id), None)
        if item is None or item.get("kind") not in ("recon-plan-group", "recon-repair-plan"):
            raise SocomError(f"{arguments.item} is not a reconstruction group or recon repair item")
        return [int(value, 16) for value in item["batch"]["functions"]]
    addresses = []
    for value in arguments.function:
        try:
            addresses.append(int(value, 16))
        except ValueError:
            # A symbol name: every sized FUNC symbol of that name.
            from .elf import Elf32File

            found = sorted(
                {s.value for s in Elf32File(root / "support" / "socom.elf").symbols() if s.name == value and s.type_name == "FUNC" and s.size}
            )
            if not found:
                raise SocomError(f"{value} is neither an address nor a sized FUNC symbol")
            addresses.extend(found)
    return addresses


def _recon_text(root: Path, arguments: argparse.Namespace, text: str) -> int:
    """Write facts/asm text to --output (repository build/ path) or stdout."""

    if arguments.output:
        output = _build_path(root, arguments.output, "reconstruction facts")
        atomic_write_text(output, text + "\n")
        print(f"wrote {output.relative_to(root).as_posix()} ({len(text.splitlines())} lines)")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


def _recon_facts(arguments: argparse.Namespace) -> int:
    from .recon_facts import context, function_facts

    root = _root(arguments)
    ctx = context(root)
    evidence: dict[int, Any] = {}
    if arguments.item:
        slug = arguments.item.removesuffix("-apply").replace("socom:", "socom-").replace(":", "-")
        paths = [root / "build" / "recon-plans" / f"{slug}-evidence.json"]
    else:
        # Single functions: use whichever group evidence file already holds them.
        paths = sorted((root / "build" / "recon-plans").glob("*-evidence.json"))
    wanted = set(_recon_addresses(root, arguments))
    for path in paths:
        if path.is_file():
            for row in load_json(path)["functions"]:
                if int(row["address"], 16) in wanted:
                    evidence[int(row["address"], 16)] = row
    blocks = [
        function_facts(ctx, address, caller_limit=arguments.callers, evidence=evidence.get(address))
        for address in _recon_addresses(root, arguments)
    ]
    return _recon_text(root, arguments, "\n\n".join(blocks))


def _recon_asm(arguments: argparse.Namespace) -> int:
    from .recon_facts import context, function_asm

    root = _root(arguments)
    ctx = context(root)
    return _recon_text(root, arguments, "\n\n".join(function_asm(ctx, address) for address in _recon_addresses(root, arguments)))


def _recon_draft(arguments: argparse.Namespace) -> int:
    """Draft a plan's rule-decided rows, or check a plan's drafted rows against a fresh draft."""

    from .recon_draft import DRAFT_RULES_VERSION, check_drafted_rows, check_rules_version, draft_plan

    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    if arguments.check:
        plan = load_json(_build_path(root, arguments.check, "reconstruction plans"))
        # A plan keeps the rules it was drafted under unless --rules says otherwise.
        rules = arguments.rules if arguments.rules is not None else check_rules_version(plan)
        draft = draft_plan(root, tracker, plan["work_item_id"], arguments.bridge_url, rules)
        problems = check_drafted_rows(draft, plan)
        drafted = sum(1 for row in plan.get("functions", []) if row.get("draft_rule"))
        _emit({
            "ok": not problems,
            "mutation_performed": False,
            "rules_version": rules,
            "plan_rules_version": (plan.get("draft") or {}).get("rules_version"),
            "drafted_rows": drafted,
            "open_rows": len(plan.get("functions", [])) - drafted,
            "problems": problems,
        })
        return 0 if not problems else 1
    if not arguments.item or not arguments.output:
        raise SocomError("recon draft needs --item and --output (or --check <plan>)")
    rules = arguments.rules if arguments.rules is not None else DRAFT_RULES_VERSION
    draft = draft_plan(root, tracker, arguments.item.removesuffix("-apply"), arguments.bridge_url, rules)
    output = _build_path(root, arguments.output, "reconstruction plans")
    atomic_write_json(output, draft)
    rules: dict[str, int] = {}
    for row in draft["functions"]:
        if row.get("draft_rule"):
            rules[row["draft_rule"]] = rules.get(row["draft_rule"], 0) + 1
    _emit({
        "ok": True,
        "mutation_performed": False,
        "output": output.relative_to(root).as_posix(),
        "decided": draft["draft"]["decided"],
        "rules": dict(sorted(rules.items())),
        "open": draft["draft"]["open"],
    })
    return 0


def _recon_void(arguments: argparse.Namespace) -> int:
    from .recon_draft import void_verdict
    from .recon_facts import context

    root = _root(arguments)
    ctx = context(root)
    texts = [void_verdict(ctx, address, arguments.rules) for address in _recon_addresses(root, arguments)]
    return _recon_text(root, arguments, "\n\n".join(texts))


def _recon_table_family(arguments: argparse.Namespace) -> int:
    """The table-family return width of one function-pointer table column (decision of 2026-10-24)."""

    from .recon_facts import context
    from .recon_table import table_family, table_family_text

    root = _root(arguments)
    result = table_family(context(root), arguments.table, column=arguments.column, stride=arguments.stride)
    return _recon_text(root, arguments, canonical_json(result) if arguments.json else table_family_text(result))


def _recon_bytes(arguments: argparse.Namespace) -> int:
    from .recon_facts import context, object_bytes

    root = _root(arguments)
    ctx = context(root)
    texts = []
    for value in arguments.address:
        try:
            addresses = [int(value, 16)]
        except ValueError:
            addresses = sorted(a for a, name in ctx.names.items() if name == value)
            if not addresses:
                raise SocomError(f"no FUNC or OBJECT symbol named {value!r}")
        texts += [object_bytes(ctx, address, arguments.length) for address in addresses]
    return _recon_text(root, arguments, "\n\n".join(texts))


def _recon_dwarf(arguments: argparse.Namespace) -> int:
    from .recon_facts import dwarf_entries

    root = _root(arguments)
    if not arguments.die and not arguments.name and not arguments.address:
        raise SystemExit("socom recon dwarf: give --die, --name and/or --address")
    offsets = [int(value, 16) if value.lower().startswith("0x") else int(value) for value in arguments.die or ()]
    return _recon_text(root, arguments, dwarf_entries(
        root, offsets, arguments.depth, arguments.name, [int(value, 16) for value in arguments.address or ()]
    ))


def _recon_refs(arguments: argparse.Namespace) -> int:
    from .recon_facts import context, object_refs

    root = _root(arguments)
    ctx = context(root)
    return _recon_text(root, arguments, "\n\n".join(object_refs(ctx, key) for key in arguments.object))


def _recon_live(arguments: argparse.Namespace) -> int:
    from .recon_facts import live_signatures

    root = _root(arguments)
    return _recon_text(root, arguments, live_signatures(_recon_addresses(root, arguments), arguments.bridge_url))


def _recon_contradictions(arguments: argparse.Namespace) -> int:
    """List group functions whose live signature contradicts the ELF facts (read-only)."""

    from .recon_scan import contradictions_text, fingerprint_inputs, live_contradictions

    root = _root(arguments)
    signatures = type_paths = None
    if arguments.fingerprint:
        signatures, type_paths = fingerprint_inputs(load_json(_build_path(root, arguments.fingerprint, "fingerprints")))
    result = live_contradictions(
        root,
        load_tracker(tracker_path(root)),
        groups=arguments.groups,
        signatures=signatures,
        type_paths=type_paths,
        bridge_url=arguments.bridge_url,
        log=lambda message: print(message, file=sys.stderr, flush=True),
    )
    return _recon_text(root, arguments, contradictions_text(result))


def _recon_types(arguments: argparse.Namespace) -> int:
    from .recon_facts import type_matches

    root = _root(arguments)
    return _recon_text(root, arguments, type_matches(arguments.names, arguments.bridge_url))


def _recon_validate(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    plan_path = Path(arguments.plan)
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    problems = validate_recon_plan(root, load_tracker(tracker_path(root)), load_json(plan_path))
    _emit(
        {
            "ok": not problems,
            "mutation_performed": False,
            "plan": arguments.plan,
            "sha256": sha256_file(plan_path),
            "problems": problems,
        }
    )
    return 0 if not problems else 1


def _recon_program(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    plan_path = Path(arguments.plan)
    if not plan_path.is_absolute():
        plan_path = root / plan_path
    program = build_recon_program(root, load_tracker(tracker_path(root)), plan_path)
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "reconstruction programs"), program)
    _emit(
        {
            "kind": program["kind"],
            "mutation_performed": False,
            "plan": program["plan"],
            "summary": recon_program_summary(program),
            "program_sha256": hashlib.sha256(canonical_json(program).encode("utf-8")).hexdigest(),
            "output": arguments.output,
        }
    )
    return 0


def _ghidra_check_recon_apply(arguments: argparse.Namespace) -> int:
    from .recon_check import check_recon_apply

    root = _root(arguments)
    result = check_recon_apply(
        root,
        arguments.item,
        arguments.label,
        arguments.prev,
        fingerprint_output=_build_path(root, arguments.fingerprint_output, "fingerprints"),
        bridge_url=arguments.bridge_url,
        log=lambda message: print(message, file=sys.stderr, flush=True),
    )
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "apply checks"), result)
    _emit(result)
    return 0 if result["ok"] else 1


def _ghidra_apply_recon(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    program_path = Path(arguments.program)
    if not program_path.is_absolute():
        program_path = root / program_path
    program = load_json(program_path)
    scope_output = _build_path(root, arguments.scope_output, "receipt scopes")
    report_output = _build_path(root, arguments.report_output, "apply reports")
    tracker = load_tracker(tracker_path(root))
    item = require_ghidra_lease(tracker, arguments.item, arguments.owner)
    if item.get("kind") not in ("recon-apply-group", "recon-repair-apply"):
        raise SocomError(f"{arguments.item} is not a reconstruction or recon repair apply item")
    plan_path = _require_accepted_plan(root, tracker, item, program)
    if canonical_json(build_recon_program(root, tracker, plan_path)) != canonical_json(program):
        raise SocomError("the reconstruction program is stale or edited; regenerate it")
    preflight = live_preflight(root, bridge_url=arguments.bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        _emit({"ok": False, "preflight": preflight})
        return 1
    bridge = GhidraBridge(arguments.bridge_url, timeout=300.0)
    # A plan may deliberately retype a global an earlier apply typed; it says so.
    replaced = {row["address"] for row in program["globals"] if row.get("replaces_accepted")}
    accepted = _accepted_scope_globals(tracker, arguments.item) - replaced
    try:
        result = execute_batch_program(
            program,
            _ReadOnlyBridge(bridge) if arguments.dry_run else bridge,
            type_index=lambda: _type_index(bridge),
            function_names=lambda: {
                f"0x{int(row['address'], 16):x}": row["name"]
                for row in _function_index(bridge)
                if "::" not in row["address"]
            },
            global_names=lambda: _global_names(root, bridge),
            log=lambda message: print(message, file=sys.stderr, flush=True),
            dry_run=arguments.dry_run,
            accepted_globals=frozenset(accepted),
        )
    except BatchFailure as failure:
        report = {
            "kind": "socom-ghidra-recon-apply-report",
            "schema_version": 1,
            "ok": False,
            "work_item_id": arguments.item,
            "error": str(failure),
            "completed_steps": failure.completed_steps,
            "details": failure.details,
            "recovery": "close socom.elf without saving and reopen it before retrying",
        }
        atomic_write_json(report_output, report)
        _emit({key: value for key, value in report.items() if key != "details"})
        return 1
    if not arguments.dry_run:
        atomic_write_json(scope_output, program["receipt_scope"])
    report = {
        "kind": "socom-ghidra-recon-apply-report",
        "schema_version": 1,
        "ok": True,
        "dry_run": arguments.dry_run,
        "work_item_id": arguments.item,
        "owner": arguments.owner,
        "program_sha256": hashlib.sha256(canonical_json(program).encode("utf-8")).hexdigest(),
        "plan": program["plan"],
        "summary": program["summary"],
        "result": result,
        "scope_output": None if arguments.dry_run else scope_output.relative_to(root).as_posix(),
    }
    atomic_write_json(report_output, report)
    summary = {key: value for key, value in report.items() if key != "result"}
    summary["skipped"] = result["skipped"]
    summary["bridge_call_count"] = result["bridge_call_count"]
    _emit(summary)
    return 0


def _stage_item_counts(tracker: dict[str, Any], stage: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in tracker["work_items"]:
        if row["stage"] == stage:
            counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    return dict(sorted(counts.items()))


def _progress_decompose_stage(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    captured: dict[str, Any] = {}
    if arguments.refresh and arguments.stage != SOURCE_STAGE:
        raise SocomError(f"--refresh re-decomposes only {SOURCE_STAGE}")
    if arguments.stage == "ghidra-reconstruction":
        groups = recon_groups(root)

        def decompose(tracker: dict[str, Any]) -> None:
            captured.update(decompose_reconstruction(tracker, groups))

    elif arguments.stage == SOURCE_STAGE:
        graph = source_graph(root)
        reservations = apply_reservations(root, graph)

        def decompose(tracker: dict[str, Any]) -> None:
            if arguments.refresh:
                # Governed re-decomposition from a changed graph (source_refresh).
                from .source_refresh import refresh_source_correlation

                captured["refresh"] = refresh_source_correlation(tracker, graph, reservations)
                captured.update(next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)["decomposition"])
            else:
                captured.update(decompose_source_correlation(tracker, graph, reservations))

    else:
        raise SocomError(f"no registered producer decomposes {arguments.stage}")

    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        require_revision(tracker, arguments.expected_revision)
        preview = copy.deepcopy(tracker)
        decompose(preview)
        refresh_ready_and_stages(preview)
        preview["revision"] += 1
        errors = audit_tracker(preview, strict=True)
        ready = next_work(copy.deepcopy(preview))
        _emit(
            {
                "ok": not errors,
                "dry_run": True,
                "revision": tracker["revision"],
                "decomposition": captured,
                "item_counts": _stage_item_counts(preview, arguments.stage),
                "ready_count": len(ready),
                "ready_sample": [row["id"] for row in ready[:5]],
                "errors": errors,
            }
        )
        return 0 if not errors else 1
    updated = mutate(tracker_path(root), arguments.expected_revision, decompose)
    write_snapshot(root, updated)
    _emit(
        {
            "ok": True,
            "dry_run": False,
            "revision": updated["revision"],
            "decomposition": captured,
            "item_counts": _stage_item_counts(updated, arguments.stage),
            "ready_count": len(next_work(copy.deepcopy(updated))),
        }
    )
    return 0


def _progress_stage_scope(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    scope = stage_live_scope(load_tracker(tracker_path(root)), arguments.stage)
    body = {"schema_version": 1, **scope}
    if arguments.output:
        atomic_write_json(_build_path(root, arguments.output, "receipt scopes"), body)
    _emit(
        {
            "mutation_performed": False,
            "stage": arguments.stage,
            "counts": {key: len(value) for key, value in scope.items()},
            "scope_sha256": scope_sha256(scope),
            "output": arguments.output,
        }
    )
    return 0


def _record_stage_baseline(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    captured: dict[str, Any] = {}

    def record_baseline(tracker: dict[str, Any]) -> None:
        scope = stage_live_scope(tracker, arguments.stage)
        current = semantic_receipt(root, bridge_url=arguments.bridge_url, scope=scope)
        entry = record_stage_baseline(
            tracker,
            arguments.stage,
            arguments.recorder,
            arguments.evidence,
            receipt_sha256=current["receipt_sha256"],
            receipt=current["receipt"],
        )
        captured.update(entry)

    if arguments.dry_run:
        tracker = load_tracker(tracker_path(root))
        require_revision(tracker, arguments.expected_revision)
        preview = copy.deepcopy(tracker)
        record_baseline(preview)
        preview["revision"] += 1
        errors = audit_tracker(preview, strict=True)
        _emit(
            {
                "ok": not errors,
                "dry_run": True,
                "revision": tracker["revision"],
                "baseline": captured,
                "errors": errors,
            }
        )
        return 0 if not errors else 1
    updated = mutate(tracker_path(root), arguments.expected_revision, record_baseline)
    write_snapshot(root, updated)
    _emit(
        {
            "ok": True,
            "dry_run": False,
            "revision": updated["revision"],
            "baseline": captured,
            "saved_program": False,
        }
    )
    return 0


def _progress_report(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    counts: dict[str, int] = {}
    for item in tracker["work_items"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    report = {
        "revision": tracker["revision"],
        "stages": [
            {"name": row["name"], "status": row["status"]}
            for row in tracker["stages"]
        ],
        "work_status_counts": dict(sorted(counts.items())),
        "open_blockers": [
            row for row in tracker["blockers"] if row.get("status") == "open"
        ],
        "next": next_work(copy.deepcopy(tracker))[:1],
    }
    if arguments.format == "markdown":
        lines = [
            f"# soCOM progress (revision {tracker['revision']})",
            "",
            "| Stage | Status |",
            "| --- | --- |",
            *[
                f"| `{row['name']}` | {row['status']} |"
                for row in report["stages"]
            ],
            "",
            f"Open blockers: {len(report['open_blockers'])}",
        ]
        sys.stdout.write("\n".join(lines) + "\n")
    else:
        _emit(report)
    return 0


def _progress_work_leases(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    rows = [
        {
            "work_item_id": row["id"],
            "stage": row["stage"],
            "resources": row.get("resources", []),
            "lease": row["lease"],
        }
        for row in tracker["work_items"]
        if row.get("lease")
    ]
    _emit({"revision": tracker["revision"], "count": len(rows), "leases": rows})
    return 0


def _progress_work_show(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    rows = tracker["work_items"]
    if arguments.item:
        rows = [row for row in rows if row["id"] == arguments.item]
        if not rows:
            raise SocomError(f"unknown work item: {arguments.item}")
    _emit({"revision": tracker["revision"], "count": len(rows), "work_items": rows})
    return 0


def _progress_migrate(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    before = load_tracker(tracker_path(root))
    updated = migrate_tracker(tracker_path(root), arguments.expected_revision)
    write_snapshot(root, updated)
    _emit(
        {
            "ok": True,
            "changed": updated["revision"] != before["revision"],
            "revision": updated["revision"],
            "schema_version": updated["schema_version"],
            "migration_history": updated.get("migration_history", []),
        }
    )
    return 0


def _progress_work_packet(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    _emit(work_packet(tracker, arguments.item, arguments.owner))
    return 0


def _source_owners(arguments: argparse.Namespace) -> int:
    rows = source_owners(_root(arguments))
    _emit({"count": len(rows), "owners": rows if arguments.rows else []})
    return 0


def _source_audit(arguments: argparse.Namespace) -> int:
    findings = audit_independence(_root(arguments))
    _emit({"ok": not findings, "findings": findings})
    return 0 if not findings else 1


def _source_graph(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    # Resolve both destinations before the build so a bad path fails fast.
    output = _build_path(root, arguments.output, "source graphs") if arguments.output else None
    markdown = _build_path(root, arguments.markdown, "source graph summaries") if arguments.markdown else None
    graph = source_graph(root, segment_size=arguments.segment_size)
    if output is not None:
        atomic_write_json(output, graph)
    if markdown is not None:
        atomic_write_text(markdown, segments_markdown(graph))
    _emit(
        {
            "mutation_performed": False,
            "kind": graph["kind"],
            "schema_version": graph["schema_version"],
            "source_sha256": graph["source_sha256"],
            "segment_size": graph["segment_size"],
            "graph_sha256": graph["graph_sha256"],
            "summary": graph["summary"],
            "output": arguments.output,
            "markdown": arguments.markdown,
        }
    )
    return 0


def _source_artifacts(arguments: argparse.Namespace) -> int:
    parsed = source_artifacts(_root(arguments))
    _emit(
        {
            "ok": not parsed["errors"],
            "anchor_count": len(parsed["anchors"]),
            "artifact_count": len(parsed["artifacts"]),
            **parsed,
        }
    )
    return 0 if not parsed["errors"] else 1


def _command_rows() -> list[dict[str, Any]]:
    return [
        {
            "command": row.path,
            "category": row.category,
            "summary": row.summary,
            "mutates": row.mutates,
            "needs_ghidra": row.needs_ghidra,
            "ghidra_requirement": row.ghidra_requirement,
            "mutates_ghidra": row.mutates_ghidra,
        }
        for row in COMMAND_SPECS
    ]


def _commands(arguments: argparse.Namespace) -> int:
    rows = _command_rows()
    if getattr(arguments, "output", None):
        # A file needs no shell redirect (Windows PowerShell adds a BOM to piped or redirected output).
        atomic_write_json(_build_path(_root(arguments), arguments.output, "command lists"), rows)
    _emit(rows)
    return 0


def _command_help(arguments: argparse.Namespace) -> int:
    query = " ".join(arguments.command_path).strip()
    if not query:
        _emit(
            {
                "program": "socom",
                "usage": "python tools/socom.py <command> [options]",
                "command_count": len(COMMAND_SPECS),
                "categories": sorted({row.category for row in COMMAND_SPECS}),
                "discovery": "python tools/socom.py commands --json",
            }
        )
        return 0
    row = next((row for row in COMMAND_SPECS if row.path == query), None)
    if not row:
        raise SocomError(f"unknown command path: {query}")
    _emit(
        {
            "command": row.path,
            "category": row.category,
            "summary": row.summary,
            "mutates": row.mutates,
            "needs_ghidra": row.needs_ghidra,
            "ghidra_requirement": row.ghidra_requirement,
            "mutates_ghidra": row.mutates_ghidra,
        }
    )
    return 0


def _audit(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    commands = _command_rows()
    name = arguments.audit_name
    if name == "agent-surface":
        report = audits.agent_surface(root, commands)
    elif name == "workflow-contracts":
        report = audits.workflow_contracts(root, commands)
    elif name == "workspace":
        report = audits.workspace(root)
    elif name == "docs":
        report = audits.docs(root, commands)
    elif name == "pipeline-reachability":
        report = audits.pipeline_reachability(root, commands)
    elif name == "retired-surface":
        report = audits.retired_surface(root)
    elif name == "capability-coverage":
        report = audits.capability_coverage(root, commands)
    elif name == "docblocks":
        report = audit_docblocks(root)
    elif name == "source-trace":
        report = audit_source_trace(
            root, require_complete=arguments.require_complete
        )
    elif name == "final-elf-catalog":
        report = final_elf_catalog(root)
    elif name == "independence":
        report = audits.independence(root)
    elif name == "issues":
        errors = audit_issues(load_issues(root))
        report = {"ok": not errors, "errors": errors}
    elif name == "current-metadata":
        tracker = load_tracker(tracker_path(root))
        status = snapshot_status(root, tracker)
        report = {
            "ok": status["fresh"],
            "revision": tracker["revision"],
            "readme_progress_fresh": status["fresh"],
            "errors": [] if status["fresh"] else ["README progress snapshot is stale"],
        }
    elif name == "provenance":
        toolchain = verify_toolchain(root, compile_probe=False)
        census_errors = verify_census(build_census(root, include_rows=False))
        errors = [*toolchain["errors"], *census_errors]
        report = {
            "ok": not errors,
            "reference_sha256": sha256_file(root / "support" / "socom.elf"),
            "toolchain_identity_ok": toolchain["identity_ok"],
            "errors": errors,
        }
    elif name == "source-fragments":
        report = run_guard(root, "source-fragments")
    elif name == "live-validation-surface":
        retired = [
            relative
            for relative in (
                ".agent/RECONSTRUCTION_ISSUES.json",
                "compiler/PROBE_STATUS.json",
            )
            if (root / relative).exists()
        ]
        errors = [f"retired shadow state still exists: {path}" for path in retired]
        expected = {
            "support/socom.elf": (
                "00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a"
            ),
        }
        for relative, digest in expected.items():
            if sha256_file(root / relative) != digest:
                errors.append(f"immutable input hash differs: {relative}")
        report = {"ok": not errors, "errors": errors}
    else:  # pragma: no cover - parser choices prevent this
        raise SocomError(f"unknown audit: {name}")
    _emit({"audit": name, **report})
    return 0 if report["ok"] else 1


def _guard(arguments: argparse.Namespace) -> int:
    report = (
        source_placement(_root(arguments))
        if arguments.guard_name == "source-placement"
        else run_guard(_root(arguments), arguments.guard_name)
    )
    _emit(report)
    return 0 if report["ok"] else 1


def _issue_list(arguments: argparse.Namespace) -> int:
    value = load_issues(_root(arguments))
    rows = value["issues"]
    if not arguments.all:
        rows = [row for row in rows if row["status"] == "open"]
    _emit({"revision": value["revision"], "count": len(rows), "issues": rows})
    return 0


def _issue_show(arguments: argparse.Namespace) -> int:
    value = load_issues(_root(arguments))
    row = next((row for row in value["issues"] if row["id"] == arguments.issue), None)
    if not row:
        raise SocomError(f"unknown workspace issue: {arguments.issue}")
    _emit({"revision": value["revision"], "issue": row})
    return 0


def _issue_audit(arguments: argparse.Namespace) -> int:
    value = load_issues(_root(arguments))
    errors = audit_issues(value)
    _emit({"ok": not errors, "revision": value.get("revision"), "errors": errors})
    return 0 if not errors else 1


def _issue_add(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    created: list[str] = []

    def operation(value: dict[str, Any]) -> None:
        created.append(
            add_issue(
                value,
                kind=(
                    "problem"
                    if arguments.issue_command == "report"
                    else arguments.issue_command
                ),
                summary=arguments.summary,
                details=arguments.details,
                reporter=arguments.reporter,
            )
        )

    updated = mutate_issues(root, arguments.expected_revision, operation)
    row = next(row for row in updated["issues"] if row["id"] == created[0])
    _emit({"ok": True, "revision": updated["revision"], "issue": row})
    return 0


def _issue_status(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    status = "resolved" if arguments.issue_command == "resolve" else "open"
    updated = mutate_issues(
        root,
        arguments.expected_revision,
        lambda value: set_issue_status(
            value,
            arguments.issue,
            status=status,
            resolution=getattr(arguments, "resolution", None),
        ),
    )
    row = next(row for row in updated["issues"] if row["id"] == arguments.issue)
    _emit({"ok": True, "revision": updated["revision"], "issue": row})
    return 0


def _docs_readme_progress(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    if arguments.write:
        write_snapshot(root, tracker)
    status = snapshot_status(root, tracker)
    _emit(
        {
            "ok": status["fresh"],
            "fresh": status["fresh"],
            "written": arguments.write,
            "revision": tracker["revision"],
        }
    )
    return 0 if status["fresh"] else 1


def _command_index_text() -> str:
    lines = [
        "# soCOM Command Index",
        "",
        "Generated from `python tools/socom.py commands --json`.",
        "",
        "| Command | Category | Workspace writes | Ghidra requirement | Live Ghidra writes | Purpose |",
        "| --- | --- | ---: | --- | ---: | --- |",
    ]
    for row in COMMAND_SPECS:
        lines.append(
            f"| `python tools/socom.py {row.path}` | {row.category} | "
            f"{'yes' if row.mutates else 'no'} | "
            f"{row.ghidra_requirement} | "
            f"{'yes' if row.mutates_ghidra else 'no'} | {row.summary} |"
        )
    return "\n".join(lines) + "\n"


def _docs_command_index(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    target = root / "docs" / "reconstruction" / "COMMANDS.md"
    rendered = _command_index_text()
    current = target.read_text(encoding="utf-8") if target.is_file() else None
    if arguments.write and current != rendered:
        atomic_write_text(target, rendered)
        current = rendered
    fresh = current == rendered
    _emit(
        {
            "ok": fresh,
            "path": target.relative_to(root).as_posix(),
            "fresh": fresh,
            "written": arguments.write,
            "command_count": len(COMMAND_SPECS),
        }
    )
    return 0 if fresh else 1


def _docs_capability_coverage(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    target = root / "docs" / "reconstruction" / "TOOL_COVERAGE.md"
    rendered = capability_document()
    current = target.read_text(encoding="utf-8") if target.is_file() else None
    if arguments.write and current != rendered:
        atomic_write_text(target, rendered)
        current = rendered
    fresh = current == rendered
    _emit(
        {
            "ok": fresh,
            "path": target.relative_to(root).as_posix(),
            "fresh": fresh,
            "written": arguments.write,
        }
    )
    return 0 if fresh else 1


def _policy_show(arguments: argparse.Namespace) -> int:
    tracker = load_tracker(tracker_path(_root(arguments)))
    _emit(
        {
            "project": tracker["project"],
            "policy": tracker["policy"],
            "stage_order": tracker["stage_order"],
            "primary_stage_chain": tracker["primary_stage_chain"],
            "capabilities": [dict(row) for row in CAPABILITIES],
        }
    )
    return 0


def _env(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    report = {
        "ok": sys.version_info >= (3, 11),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "workspace": str(root),
        "cwd": os.getcwd(),
        "ghidra_url": os.environ.get(
            "SOCOM_GHIDRA_URL", "http://127.0.0.1:8089"
        ),
        "toolchain": verify_toolchain(root, compile_probe=False),
    }
    report["ok"] = report["ok"] and report["toolchain"]["identity_ok"]
    _emit(report)
    return 0 if report["ok"] else 1


def _toolchain_bootstrap(arguments: argparse.Namespace) -> int:
    report = bootstrap_toolchain(_root(arguments), force=arguments.force)
    _emit(report)
    return 0 if report["identity_ok"] else 1


def _toolchain_verify(arguments: argparse.Namespace) -> int:
    report = verify_toolchain(
        _root(arguments), compile_probe=not arguments.identity_only
    )
    ok = report["identity_ok"] and (
        arguments.identity_only or report["compile_ready"] is True
    )
    report["ok"] = ok
    _emit(report)
    return 0 if ok else 1


def _doctor(arguments: argparse.Namespace) -> int:
    report = run_doctor(
        _root(arguments),
        infrastructure_only=arguments.infrastructure_only,
        check_ghidra=arguments.ghidra,
    )
    _emit(report)
    return 0 if report["ok"] else 1


VERIFY_STAGE_MAP = {
    "linked-byte": "linked-byte-match",
    "final-elf": "final-validation",
}


def _verify_stage(arguments: argparse.Namespace) -> int:
    root = _root(arguments)
    tracker = load_tracker(tracker_path(root))
    stage = VERIFY_STAGE_MAP[arguments.verification]
    stage_row = next(row for row in tracker["stages"] if row["name"] == stage)
    reference_errors = verify_census(build_census(root, include_rows=False))
    work = [row for row in tracker["work_items"] if row["stage"] == stage]
    errors = list(reference_errors)
    comparison = None
    candidate = Path(arguments.candidate)
    if not candidate.is_absolute():
        candidate = root / candidate
    if not candidate.is_file():
        errors.append(f"candidate ELF does not exist: {candidate}")
    else:
        comparison = compare_elf(
            root / "support" / "socom.elf",
            candidate,
            mode="final" if arguments.verification == "final-elf" else "linked",
        )
        if not comparison["ok"]:
            errors.extend(
                f"candidate: {message}" for message in comparison["errors"]
            )
    catalog = (
        final_elf_catalog(root) if arguments.verification == "final-elf" else None
    )
    readiness_errors: list[str] = []
    if stage_row["status"] != "accepted":
        readiness_errors.append(f"stage {stage} is {stage_row['status']}, not accepted")
    if not work or any(row["status"] != "accepted" for row in work):
        readiness_errors.append(f"stage {stage} has unaccepted work")
    if any(row.get("kind") == "stage-seed" for row in work):
        readiness_errors.append(f"stage {stage} has no registered real producer")
    if comparison is None or not comparison["ok"]:
        readiness_errors.append("candidate comparison is not exact")
    if catalog is not None and not catalog["complete"]:
        readiness_errors.append("final ELF semantic catalog is incomplete")
    acceptance_ready = not readiness_errors
    if arguments.acceptance:
        errors.extend(readiness_errors)
    _emit(
        {
            "ok": not errors,
            "verification": arguments.verification,
            "acceptance_requested": arguments.acceptance,
            "comparison_ok": comparison["ok"] if comparison is not None else False,
            "acceptance_ready": acceptance_ready,
            "stage": stage_row,
            "work_item_count": len(work),
            "candidate_comparison": comparison,
            "final_elf_catalog": catalog,
            "readiness_errors": readiness_errors,
            "errors": errors,
            "note": (
                "Diagnostic comparison does not imply stage acceptance. Acceptance "
                "fails closed until real producers and typed evidence are accepted."
            ),
        }
    )
    return 0 if not errors else 1


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    _spec(
        "commands",
        "docs",
        "List the authoritative machine-readable command registry as UTF-8 JSON without a byte-order mark "
        "(--output also writes it to a file under build/, which needs no shell redirect).",
    ),
    _spec("help", "docs", "Show registry metadata for one command path."),
    _spec(
        "doctor",
        "validation",
        "Run categorized workspace health checks.",
        ghidra_requirement="optional",
    ),
    _spec("env", "validation", "Report the local host and pinned toolchain environment."),
    _spec("policy show", "docs", "Show machine-readable reconstruction policy and stage order."),
    _spec("toolchain bootstrap", "toolchain", "Acquire and verify the pinned Metrowerks toolchain.", mutates=True),
    _spec("toolchain verify", "toolchain", "Verify pinned compiler identity and optional compile readiness."),
    _spec("reference census", "reference", "Parse the immutable ELF into a deterministic evidence census.", mutates=True),
    _spec("reference verify", "reference", "Deep-compare the complete stored census with a fresh ELF parse."),
    _spec("reference show", "reference", "Query stored reference sections or symbols."),
    _spec("reference relocations", "reference", "Query MIPS relocations with symbol and HI16/LO16 context."),
    _spec("debug inspect", "debug", "Inspect DWARF 1 and line-program facts."),
    _spec("debug graph", "debug", "Build the scoped DWARF import graph without mutating Ghidra."),
    _spec("debug conflicts list", "debug", "List scoped blocking DWARF definition conflicts."),
    _spec("debug import-plan", "debug", "Build a deterministic scoped Ghidra import plan."),
    _spec("debug apply-program", "debug", "Translate an accepted type plan into deterministic Ghidra type operations."),
    _spec("debug batch-program", "debug", "Translate an accepted DWARF batch plan into deterministic Ghidra function and global operations."),
    _spec("ghidra preflight", "ghidra", "Verify project soCOM and the explicit socom.elf program.", ghidra_requirement="required"),
    _spec(
        "ghidra preflight-batch",
        "ghidra",
        "Dry-run a batch program against live Ghidra: every read and pre-write check, no writes.",
        ghidra_requirement="required",
    ),
    _spec(
        "ghidra fingerprint",
        "ghidra",
        "Fingerprint every function signature, data item, type, block and reference; optionally diff two.",
        mutates=True,
        ghidra_requirement="required",
    ),
    _spec(
        "ghidra apply-batch",
        "ghidra",
        "Apply a translated batch program (names, prototypes, globals) under the item's writer lease and verify it.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra apply-recon",
        "ghidra",
        "Apply a reviewed reconstruction group or recon repair program under the item's writer lease and verify it.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra restore-accepted",
        "ghidra",
        "Replay accepted Ghidra applies on a fresh baseline import and prove their receipts reproduce.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra repair-labels",
        "ghidra",
        "Delete the readable labels a recorded label repair names, under the repair item's writer lease.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra check-names-repair",
        "ghidra",
        "Run the names repair verifier's checklist read-only and print evidence lines.",
        mutates=True,
        ghidra_requirement="required",
    ),
    _spec(
        "ghidra repair-names",
        "ghidra",
        "Give mangled functions their readable names (names repair), with --dry-run, under the writer lease.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra repair-signatures",
        "ghidra",
        "Restore function signatures a recorded repair names, under the repair item's writer lease.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra repair-boundaries",
        "ghidra",
        "Rejoin the ten split function boundaries with the pinned one-time script, with --dry-run, under the writer lease.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra map-zero-fill",
        "ghidra",
        "Map the ELF load image's zero fill in Ghidra under the item's writer lease.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "ghidra apply-types",
        "ghidra",
        "Apply a translated type program under the item's writer lease and verify it.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec("ghidra data-overlap", "ghidra", "Report overlapping Ghidra data roots.", ghidra_requirement="required"),
    _spec("ghidra receipt", "ghidra", "Create a portable deterministic semantic receipt.", mutates=True, ghidra_requirement="required"),
    _spec("audit agent-surface", "audit", "Audit command, skill, role, and harness alignment."),
    _spec("audit capability-coverage", "audit", "Audit active, deferred, and target-inapplicable capabilities."),
    _spec("audit current-metadata", "audit", "Verify generated current progress metadata."),
    _spec("audit docblocks", "audit", "Validate source annotation grammar and evidence identities."),
    _spec("audit docs", "audit", "Audit local documentation links and registered command invocations."),
    _spec("audit final-elf-catalog", "audit", "Report typed file and loaded-memory ELF coverage."),
    _spec(
        "audit independence",
        "audit",
        "Reject foreign-project, machine-specific, or external-workspace dependencies.",
    ),
    _spec("audit issues", "audit", "Validate the workspace issue ledger."),
    _spec("audit live-validation-surface", "audit", "Reject retired shadow state and changed immutable inputs."),
    _spec("audit pipeline-reachability", "audit", "Prove each stage has a reachable evidence producer."),
    _spec("audit provenance", "audit", "Audit immutable ELF and compiler provenance."),
    _spec("audit retired-surface", "audit", "Reject obsolete analysis-backend files and terms."),
    _spec("audit source-trace", "audit", "Validate source-to-artifact topology and accepted coverage."),
    _spec("audit source-fragments", "audit", "Inventory prohibited production source fragments."),
    _spec("audit workflow-contracts", "audit", "Audit reservation, acceptance, and mutation contracts."),
    _spec("audit workspace", "audit", "Detect generated artifacts outside approved roots."),
    *(
        _spec(f"guard {name}", "guard", summary)
        for name, (summary, _patterns, _allowlist) in sorted(GUARDS.items())
    ),
    _spec("guard source-placement", "guard", "Reject machine-specific paths in active source."),
    _spec("issue audit", "issue", "Validate the workspace issue ledger."),
    _spec("issue list", "issue", "List open or all workspace issues."),
    _spec("issue show", "issue", "Show one workspace issue."),
    _spec("issue report", "issue", "Record a tooling/process problem.", mutates=True),
    _spec("issue request", "issue", "Record a tooling/process improvement request.", mutates=True),
    _spec("issue resolve", "issue", "Resolve a workspace issue.", mutates=True),
    _spec("issue reopen", "issue", "Reopen a workspace issue.", mutates=True),
    _spec("docs readme-progress", "docs", "Check or update the generated README progress snapshot.", mutates=True),
    _spec("docs command-index", "docs", "Check or update the generated complete command index.", mutates=True),
    _spec("docs capability-coverage", "docs", "Check or update the generated tool coverage inventory.", mutates=True),
    _spec("recon graph", "recon", "Build the deterministic callee-first function groups from the ELF."),
    _spec("recon evidence", "recon", "Write a reconstruction group's file-only planning evidence.", mutates=True),
    _spec("recon validate", "recon", "Check a reconstruction plan against its group and the ELF."),
    _spec("recon program", "recon", "Translate a valid reconstruction plan into an apply program.", mutates=True),
    _spec(
        "ghidra check-recon-apply",
        "ghidra",
        "Run the stage 3 apply verifier's checklist read-only and print evidence lines.",
        mutates=True,
        ghidra_requirement="required",
    ),
    _spec("recon facts", "recon", "Print compact ELF-derived call-contract facts for functions or a group."),
    _spec("recon asm", "recon", "Print annotated ELF disassembly of functions."),
    _spec("recon draft", "recon", "Draft a plan's rule-decided rows from facts and live types, or --check a plan's drafted rows.", ghidra_requirement="required"),
    _spec("recon void", "recon", "Print the void verdict of functions: exit values, the first blocking caller chain, and the vtable slot family verdict."),
    _spec(
        "recon table-family",
        "recon",
        "Print a function-pointer table column's entries, their exit-value classes and argument reads, and the family's return-width verdict.",
    ),
    _spec("recon bytes", "recon", "Print initialized bytes at an address or symbol, with relocated words and strings."),
    _spec("recon dwarf", "recon", "Print DWARF 1 entries by offset with their children."),
    _spec("recon refs", "recon", "Print a data object's relocated slots and every code access to it."),
    _spec("recon live", "recon", "Print live Ghidra names and signatures of functions or a group.", ghidra_requirement="required"),
    _spec("recon types", "recon", "Print every live Ghidra type matching each name, ignoring case.", ghidra_requirement="required"),
    _spec(
        "recon contradictions",
        "recon",
        "List group functions whose live signature contradicts the ELF facts, with each owning group's apply state.",
        ghidra_requirement="optional",
    ),
    *type_plan_cli.specs(_spec),
    *recon_repair_cli.specs(_spec),
    _spec("progress init", "progress", "Initialize unified reconstruction state.", mutates=True),
    _spec("progress next", "progress", "Select ready work from the canonical stage graph."),
    _spec("progress show", "progress", "Show the tracker or one exact entity."),
    _spec("progress status", "progress", "Show derived stage, lease, and next-work status."),
    _spec("progress find", "progress", "Search unified reconstruction entities."),
    _spec("progress sql", "progress", "Query the derived read-only SQLite cache of tracker, census and issues."),
    _spec("progress audit", "progress", "Audit tracker structure and strict derived invariants."),
    _spec("progress snapshot", "progress", "Check or update the README progress snapshot.", mutates=True),
    _spec("progress report", "progress", "Render an on-demand progress report."),
    _spec("progress migrate", "progress", "Migrate canonical tracker state to the current schema.", mutates=True),
    _spec(
        "progress add-repair",
        "progress",
        "Add a recorded Ghidra repair item once the applies it corrects are accepted.",
        mutates=True,
    ),
    _spec(
        "progress handoff-live-ghidra",
        "progress",
        "Save and hand off a leased Ghidra item with a stable semantic receipt.",
        mutates=True,
        ghidra_requirement="required",
        mutates_ghidra=True,
    ),
    _spec(
        "progress advance-live-ghidra",
        "progress",
        "Accept a Ghidra handoff only when its live semantic receipt is unchanged.",
        mutates=True,
        ghidra_requirement="required",
    ),
    _spec(
        "progress rebaseline-live-ghidra",
        "progress",
        "Record a fresh-import baseline receipt after a Ghidra version re-pin.",
        mutates=True,
        ghidra_requirement="required",
    ),
    _spec(
        "progress decompose-stage",
        "progress",
        "Replace a stage seed with its registered producer's work items (--refresh rebuilds a decomposed "
        "source-correlation stage from a changed graph while no stage 4 plan is accepted).",
        mutates=True,
    ),
    _spec("progress stage-scope", "progress", "Write the union of an accepted stage's writer receipt scopes."),
    _spec(
        "progress record-stage-baseline",
        "progress",
        "Record an accepted stage's live receipt over the union of its writer scopes.",
        mutates=True,
        ghidra_requirement="required",
    ),
    _spec("progress work claim", "progress", "Claim ready work with a bounded lease.", mutates=True),
    _spec("progress work heartbeat", "progress", "Renew an owned work lease.", mutates=True),
    _spec("progress work handoff", "progress", "Submit work and evidence for independent acceptance.", mutates=True),
    _spec("progress work accept", "progress", "Independently accept handed-off work.", mutates=True),
    _spec("progress work reject", "progress", "Independently return handed-off work for rework with findings.", mutates=True),
    _spec("progress work reopen", "progress", "Return an accepted reconstruction plan whose apply has not started for re-planning, with the reason.", mutates=True),
    _spec("progress work release", "progress", "Release an owned work lease.", mutates=True),
    _spec("progress work leases", "progress", "Show all active leases and exclusive resources."),
    _spec("progress work packet", "progress", "Render the exact contract for an actively leased item."),
    _spec("progress work show", "progress", "Show one or all structured work items."),
    _spec("source owners", "source", "Inventory provisional source owners."),
    _spec("source artifacts", "source", "Inventory source artifact annotations."),
    _spec(
        "source graph",
        "source",
        "Build deterministic ELF-only translation-unit evidence, classification candidates and address segments.",
    ),
    _spec("source audit", "source", "Audit soCOM workspace independence."),
    *source_plan_cli.specs(_spec),
    *source_apply_cli.specs(_spec),
    *source_gate_cli.specs(_spec),
    *provider_archive.specs(_spec),
    _spec("verify asm", "verification", "Read function and assembly evidence from Ghidra.", ghidra_requirement="required"),
    _spec("verify functional", "verification", "List or run one deterministic behavioral smoke target."),
    _spec("verify functional-batch", "verification", "Run a reviewed batch of behavioral smoke targets."),
    *(
        _spec(f"verify {name}", "verification", f"Fail-closed {stage} stage verification.")
        for name, stage in VERIFY_STAGE_MAP.items()
    ),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="socom",
        description="Authoritative soCOM reconstruction control plane",
    )
    parser.add_argument(
        "--root", default=str(workspace_root()), help="workspace root (default: repo root)"
    )
    parser.add_argument("--json", action="store_true", help="accepted for script clarity")
    commands = parser.add_subparsers(dest="command", required=True)

    command_list = commands.add_parser("commands", help="list command registry")
    command_list.add_argument("--output", help="also write the registry as UTF-8 JSON without a BOM to this path under build/")
    command_list.set_defaults(handler=_commands)
    command_help = commands.add_parser("help", help="show command metadata")
    command_help.add_argument("command_path", nargs="*")
    command_help.set_defaults(handler=_command_help)

    doctor = commands.add_parser("doctor", help="check workspace health")
    doctor.add_argument("--infrastructure-only", action="store_true")
    doctor.add_argument("--ghidra", action="store_true")
    doctor.set_defaults(handler=_doctor)

    environment = commands.add_parser("env", help="report local environment")
    environment.set_defaults(handler=_env)

    policy = commands.add_parser("policy")
    policy_commands = policy.add_subparsers(dest="policy_command", required=True)
    policy_show = policy_commands.add_parser("show")
    policy_show.set_defaults(handler=_policy_show)

    toolchain = commands.add_parser("toolchain")
    toolchain_commands = toolchain.add_subparsers(dest="toolchain_command", required=True)
    bootstrap = toolchain_commands.add_parser("bootstrap")
    bootstrap.add_argument("--force", action="store_true")
    bootstrap.set_defaults(handler=_toolchain_bootstrap)
    verify = toolchain_commands.add_parser("verify")
    verify.add_argument("--identity-only", action="store_true")
    verify.set_defaults(handler=_toolchain_verify)

    reference = commands.add_parser("reference")
    reference_commands = reference.add_subparsers(dest="reference_command", required=True)
    census = reference_commands.add_parser("census")
    census.add_argument("--write", action="store_true")
    census.add_argument("--summary-only", action="store_true")
    census.add_argument("--output-rows", action="store_true")
    census.set_defaults(handler=_reference_census)
    reference_verify = reference_commands.add_parser("verify")
    reference_verify.add_argument("--strict", action="store_true")
    reference_verify.set_defaults(handler=_reference_verify)
    show = reference_commands.add_parser("show")
    show.add_argument("--section")
    show.add_argument("--symbol")
    show.add_argument("--limit", type=int, default=50)
    show.set_defaults(handler=_reference_show)
    relocations = reference_commands.add_parser("relocations")
    relocations.add_argument("--at")
    relocations.add_argument("--size", type=int, default=1)
    relocations.add_argument("--symbol")
    relocations.add_argument("--type")
    relocations.add_argument("--limit", type=int, default=100)
    relocations.set_defaults(handler=_reference_relocations)

    recon = commands.add_parser("recon")
    recon_commands = recon.add_subparsers(dest="recon_command", required=True)
    recon_graph = recon_commands.add_parser("graph")
    recon_graph.add_argument("--group-size", type=int, default=RECON_GROUP_SIZE)
    recon_graph.add_argument("--output")
    recon_graph.set_defaults(handler=_recon_graph)
    recon_evidence = recon_commands.add_parser("evidence")
    recon_evidence.add_argument("--item", required=True)
    recon_evidence.add_argument("--output", required=True)
    recon_evidence.set_defaults(handler=_recon_evidence)
    recon_validate = recon_commands.add_parser("validate")
    recon_validate.add_argument("--plan", required=True)
    recon_validate.set_defaults(handler=_recon_validate)
    recon_program = recon_commands.add_parser("program")
    recon_program.add_argument("--plan", required=True)
    recon_program.add_argument("--output")
    recon_program.set_defaults(handler=_recon_program)
    recon_facts = recon_commands.add_parser("facts")
    recon_facts_target = recon_facts.add_mutually_exclusive_group(required=True)
    recon_facts_target.add_argument("--item")
    recon_facts_target.add_argument("--function", nargs="+")
    recon_facts.add_argument("--callers", type=int, default=12)
    recon_facts.add_argument("--output")
    recon_facts.set_defaults(handler=_recon_facts)
    recon_asm = recon_commands.add_parser("asm")
    recon_asm.add_argument("--function", nargs="+", required=True)
    recon_asm.add_argument("--output")
    recon_asm.set_defaults(handler=_recon_asm)
    from .recon_draft import DRAFT_RULES_VERSION, RULES_VERSIONS

    recon_draft = recon_commands.add_parser("draft")
    recon_draft.add_argument("--item")
    recon_draft.add_argument("--output")
    recon_draft.add_argument("--check")
    recon_draft.add_argument("--bridge-url")
    # Default: the newest rules to draft; with --check, the plan's own (check_rules_version).
    recon_draft.add_argument("--rules", type=int, choices=RULES_VERSIONS, default=None)
    recon_draft.set_defaults(handler=_recon_draft)
    recon_void = recon_commands.add_parser("void")
    recon_void.add_argument("--function", nargs="+", required=True)
    recon_void.add_argument("--output")
    recon_void.add_argument("--rules", type=int, choices=RULES_VERSIONS, default=DRAFT_RULES_VERSION)
    recon_void.set_defaults(handler=_recon_void)
    recon_table = recon_commands.add_parser("table-family")
    recon_table.add_argument("--table", required=True, help="table symbol, or an address inside the table")
    recon_table.add_argument("--column", type=lambda text: int(text, 0), help="byte offset of the function column in a row")
    recon_table.add_argument("--stride", type=lambda text: int(text, 0), help="row size in bytes")
    recon_table.add_argument("--json", action="store_true", help="print the structured result")
    recon_table.add_argument("--output")
    recon_table.set_defaults(handler=_recon_table_family)
    recon_bytes = recon_commands.add_parser("bytes")
    recon_bytes.add_argument("--address", nargs="+", required=True)
    recon_bytes.add_argument("--length", type=int)
    recon_bytes.add_argument("--output")
    recon_bytes.set_defaults(handler=_recon_bytes)
    recon_dwarf = recon_commands.add_parser("dwarf")
    recon_dwarf_target = recon_dwarf.add_argument_group()
    recon_dwarf_target.add_argument("--die", nargs="+")
    recon_dwarf_target.add_argument("--name", nargs="+")
    recon_dwarf_target.add_argument("--address", nargs="+")
    recon_dwarf.add_argument("--depth", type=int, default=1)
    recon_dwarf.add_argument("--output")
    recon_dwarf.set_defaults(handler=_recon_dwarf)
    recon_refs = recon_commands.add_parser("refs")
    recon_refs.add_argument("--object", nargs="+", required=True)
    recon_refs.add_argument("--output")
    recon_refs.set_defaults(handler=_recon_refs)
    recon_live = recon_commands.add_parser("live")
    recon_live_target = recon_live.add_mutually_exclusive_group(required=True)
    recon_live_target.add_argument("--item")
    recon_live_target.add_argument("--function", nargs="+")
    recon_live.add_argument("--output")
    recon_live.add_argument("--bridge-url")
    recon_live.set_defaults(handler=_recon_live)
    recon_types = recon_commands.add_parser("types")
    recon_types.add_argument("names", nargs="+")
    recon_types.add_argument("--output")
    recon_types.add_argument("--bridge-url")
    recon_types.set_defaults(handler=_recon_types)
    recon_contradictions = recon_commands.add_parser("contradictions")
    recon_contradictions.add_argument("--groups", choices=("applied", "all"), default="all")
    recon_contradictions.add_argument("--fingerprint", help="read signatures and types from a stored fingerprint, not live")
    recon_contradictions.add_argument("--output")
    recon_contradictions.add_argument("--bridge-url")
    recon_contradictions.set_defaults(handler=_recon_contradictions)
    debug = commands.add_parser("debug")
    debug_commands = debug.add_subparsers(dest="debug_command", required=True)
    inspect = debug_commands.add_parser("inspect")
    inspect.add_argument("--rows", action="store_true")
    inspect.set_defaults(handler=_debug_inspect)
    graph = debug_commands.add_parser("graph")
    graph.add_argument("--batch")
    graph.add_argument("--output")
    graph.add_argument("--rows", action="store_true")
    graph.set_defaults(handler=_debug_import_plan)
    conflicts = debug_commands.add_parser("conflicts")
    conflict_commands = conflicts.add_subparsers(
        dest="conflict_command", required=True
    )
    conflict_list = conflict_commands.add_parser("list")
    conflict_list.add_argument("--batch")
    conflict_list.add_argument("--limit", type=int, default=100)
    conflict_list.add_argument("--member-limit", type=int, default=20)
    conflict_list.set_defaults(handler=_debug_conflicts)
    plan = debug_commands.add_parser("import-plan")
    plan.add_argument("--batch")
    plan.add_argument("--output")
    plan.add_argument("--rows", action="store_true")
    plan.set_defaults(handler=_debug_import_plan)
    apply_program = debug_commands.add_parser("apply-program")
    apply_program.add_argument("--plan", required=True)
    apply_program.add_argument("--output")
    apply_program.set_defaults(handler=_debug_apply_program)
    batch_program = debug_commands.add_parser("batch-program")
    batch_program.add_argument("--plan", required=True)
    batch_program.add_argument("--output")
    batch_program.set_defaults(handler=_debug_batch_program)

    ghidra = commands.add_parser("ghidra")
    ghidra_commands = ghidra.add_subparsers(dest="ghidra_command", required=True)
    preflight = ghidra_commands.add_parser("preflight")
    preflight.add_argument("--bridge-url")
    preflight.add_argument("--strict", action="store_true")
    preflight.set_defaults(handler=_ghidra_preflight)
    overlap = ghidra_commands.add_parser("data-overlap")
    overlap.add_argument("address", nargs="*")
    overlap.add_argument("--bridge-url")
    overlap.add_argument("--limit", type=int, default=40)
    overlap.set_defaults(handler=_ghidra_data_overlap)
    receipt = ghidra_commands.add_parser("receipt")
    receipt.add_argument("--scope")
    receipt.add_argument("--output")
    receipt.add_argument("--bridge-url")
    receipt.set_defaults(handler=_ghidra_receipt)
    preflight_batch = ghidra_commands.add_parser("preflight-batch")
    preflight_batch.add_argument("--program", required=True)
    preflight_batch.add_argument("--output")
    preflight_batch.add_argument("--bridge-url")
    preflight_batch.set_defaults(handler=_ghidra_preflight_batch)
    fingerprint = ghidra_commands.add_parser("fingerprint")
    fingerprint.add_argument("--output", required=True)
    fingerprint.add_argument("--compare")
    fingerprint.add_argument("--diff-output")
    fingerprint.add_argument("--bridge-url")
    fingerprint.add_argument(
        "--sweep-mode",
        choices=SWEEP_MODES,
        default="concurrent",
        help="concurrent (default) keeps three identical read requests in flight; legacy sends them one at a time",
    )
    fingerprint.set_defaults(handler=_ghidra_fingerprint)
    apply_batch = ghidra_commands.add_parser("apply-batch")
    apply_batch.add_argument("--program", required=True)
    apply_batch.add_argument("--item", required=True)
    apply_batch.add_argument("--owner", required=True)
    apply_batch.add_argument("--scope-output", required=True)
    apply_batch.add_argument("--report-output", required=True)
    apply_batch.add_argument("--bridge-url")
    apply_batch.set_defaults(handler=_ghidra_apply_batch)
    apply_recon = ghidra_commands.add_parser("apply-recon")
    apply_recon.add_argument("--program", required=True)
    apply_recon.add_argument("--item", required=True)
    apply_recon.add_argument("--owner", required=True)
    apply_recon.add_argument("--scope-output", required=True)
    apply_recon.add_argument("--report-output", required=True)
    apply_recon.add_argument("--dry-run", action="store_true")
    apply_recon.add_argument("--bridge-url")
    apply_recon.set_defaults(handler=_ghidra_apply_recon)
    check_recon = ghidra_commands.add_parser("check-recon-apply")
    check_recon.add_argument("--item", required=True)
    check_recon.add_argument("--label", required=True)
    check_recon.add_argument("--prev", required=True)
    check_recon.add_argument("--fingerprint-output", required=True)
    check_recon.add_argument("--output")
    check_recon.add_argument("--bridge-url")
    check_recon.set_defaults(handler=_ghidra_check_recon_apply)
    restore = ghidra_commands.add_parser("restore-accepted")
    restore.add_argument("--item", required=True)
    restore.add_argument("--owner", required=True)
    restore.add_argument("--report-output", required=True)
    restore.add_argument("--bridge-url")
    restore.set_defaults(handler=_ghidra_restore_accepted)
    zero_fill = ghidra_commands.add_parser("map-zero-fill")
    zero_fill.add_argument("--item", required=True)
    zero_fill.add_argument("--owner", required=True)
    zero_fill.add_argument("--scope-output", required=True)
    zero_fill.add_argument("--report-output", required=True)
    zero_fill.add_argument("--bridge-url")
    zero_fill.set_defaults(handler=_ghidra_map_zero_fill)
    check_names = ghidra_commands.add_parser("check-names-repair")
    check_names.add_argument("--label", required=True)
    check_names.add_argument("--prev", required=True)
    check_names.add_argument("--fingerprint-output", required=True)
    check_names.add_argument("--output")
    check_names.add_argument("--bridge-url")
    check_names.set_defaults(handler=_ghidra_check_names_repair)
    repair_names_parser = ghidra_commands.add_parser("repair-names")
    repair_names_parser.add_argument("--item", required=True)
    repair_names_parser.add_argument("--owner", required=True)
    repair_names_parser.add_argument("--scope-output", required=True)
    repair_names_parser.add_argument("--report-output", required=True)
    repair_names_parser.add_argument("--dry-run", action="store_true")
    repair_names_parser.add_argument("--bridge-url")
    repair_names_parser.set_defaults(handler=_ghidra_repair_names)
    repair = ghidra_commands.add_parser("repair-signatures")
    repair.add_argument("--item", required=True)
    repair.add_argument("--owner", required=True)
    repair.add_argument("--scope-output", required=True)
    repair.add_argument("--report-output", required=True)
    repair.add_argument("--bridge-url")
    repair.set_defaults(handler=_ghidra_repair_signatures)
    repair_boundaries_parser = ghidra_commands.add_parser("repair-boundaries")
    repair_boundaries_parser.add_argument("--item", required=True)
    repair_boundaries_parser.add_argument("--owner", required=True)
    repair_boundaries_parser.add_argument("--scope-output", required=True)
    repair_boundaries_parser.add_argument("--report-output", required=True)
    repair_boundaries_parser.add_argument("--dry-run", action="store_true")
    repair_boundaries_parser.add_argument("--bridge-url")
    repair_boundaries_parser.set_defaults(handler=_ghidra_repair_boundaries)
    repair_labels_parser = ghidra_commands.add_parser("repair-labels")
    repair_labels_parser.add_argument("--item", required=True)
    repair_labels_parser.add_argument("--owner", required=True)
    repair_labels_parser.add_argument("--scope-output", required=True)
    repair_labels_parser.add_argument("--report-output", required=True)
    repair_labels_parser.add_argument("--bridge-url")
    repair_labels_parser.set_defaults(handler=_ghidra_repair_labels)
    apply_types = ghidra_commands.add_parser("apply-types")
    apply_types.add_argument("--program", required=True)
    apply_types.add_argument("--item", required=True)
    apply_types.add_argument("--owner", required=True)
    apply_types.add_argument("--scope-output", required=True)
    apply_types.add_argument("--report-output", required=True)
    apply_types.add_argument("--bridge-url")
    apply_types.set_defaults(handler=_ghidra_apply_types)

    audit_group = commands.add_parser("audit")
    audit_commands = audit_group.add_subparsers(dest="audit_name", required=True)
    for name in (
        "agent-surface",
        "capability-coverage",
        "current-metadata",
        "docblocks",
        "docs",
        "final-elf-catalog",
        "independence",
        "issues",
        "live-validation-surface",
        "pipeline-reachability",
        "provenance",
        "retired-surface",
        "source-fragments",
        "workflow-contracts",
        "workspace",
    ):
        audit_parser = audit_commands.add_parser(name)
        audit_parser.add_argument("--strict", action="store_true")
        audit_parser.set_defaults(require_complete=False)
        audit_parser.set_defaults(handler=_audit)
    source_trace = audit_commands.add_parser("source-trace")
    source_trace.add_argument("--require-complete", action="store_true")
    source_trace.add_argument("--strict", action="store_true")
    source_trace.set_defaults(handler=_audit)

    guard_group = commands.add_parser("guard")
    guard_commands = guard_group.add_subparsers(dest="guard_name", required=True)
    for name in (*sorted(GUARDS), "source-placement"):
        guard_commands.add_parser(name).set_defaults(handler=_guard)

    issue = commands.add_parser("issue")
    issue_commands = issue.add_subparsers(dest="issue_command", required=True)
    issue_audit = issue_commands.add_parser("audit")
    issue_audit.set_defaults(handler=_issue_audit)
    issue_list = issue_commands.add_parser("list")
    issue_list.add_argument("--all", action="store_true")
    issue_list.set_defaults(handler=_issue_list)
    issue_show = issue_commands.add_parser("show")
    issue_show.add_argument("issue")
    issue_show.set_defaults(handler=_issue_show)
    for name in ("report", "request"):
        sub = issue_commands.add_parser(name)
        sub.add_argument("--summary", required=True)
        sub.add_argument("--details", default="")
        sub.add_argument("--reporter", required=True)
        sub.add_argument("--expected-revision", type=int, required=True)
        sub.set_defaults(handler=_issue_add)
    issue_resolve = issue_commands.add_parser("resolve")
    issue_resolve.add_argument("issue")
    issue_resolve.add_argument("--resolution", required=True)
    issue_resolve.add_argument("--expected-revision", type=int, required=True)
    issue_resolve.set_defaults(handler=_issue_status)
    issue_reopen = issue_commands.add_parser("reopen")
    issue_reopen.add_argument("issue")
    issue_reopen.add_argument("--expected-revision", type=int, required=True)
    issue_reopen.set_defaults(handler=_issue_status)

    docs = commands.add_parser("docs")
    docs_commands = docs.add_subparsers(dest="docs_command", required=True)
    readme_progress = docs_commands.add_parser("readme-progress")
    readme_progress.add_argument("--write", action="store_true")
    readme_progress.set_defaults(handler=_docs_readme_progress)
    command_index = docs_commands.add_parser("command-index")
    command_index.add_argument("--write", action="store_true")
    command_index.set_defaults(handler=_docs_command_index)
    capability_coverage = docs_commands.add_parser("capability-coverage")
    capability_coverage.add_argument("--write", action="store_true")
    capability_coverage.set_defaults(handler=_docs_capability_coverage)

    progress = commands.add_parser("progress")
    progress_commands = progress.add_subparsers(dest="progress_command", required=True)
    init = progress_commands.add_parser("init")
    init.add_argument("--write", action="store_true")
    init.add_argument("--force", action="store_true")
    init.set_defaults(handler=_progress_init)
    progress_next = progress_commands.add_parser("next")
    progress_next.add_argument("--limit", type=int, default=1)
    progress_next.set_defaults(handler=_progress_next)
    progress_show = progress_commands.add_parser("show")
    progress_show.add_argument("id", nargs="?")
    progress_show.set_defaults(handler=_progress_show)
    status = progress_commands.add_parser("status")
    status.set_defaults(handler=_progress_status)
    find = progress_commands.add_parser("find")
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=50)
    find.set_defaults(handler=_progress_find)
    sql = progress_commands.add_parser("sql")
    sql.add_argument("statement")
    sql.add_argument("--limit", type=int, default=200)
    sql.add_argument("--format", choices=("text", "json"), default="text")
    sql.set_defaults(handler=_progress_sql)
    audit = progress_commands.add_parser("audit")
    audit.add_argument("--strict", action="store_true")
    audit.set_defaults(handler=_progress_audit)
    snapshot = progress_commands.add_parser("snapshot")
    snapshot.add_argument("--write", action="store_true")
    snapshot.set_defaults(handler=_progress_snapshot)
    report = progress_commands.add_parser("report")
    report.add_argument("--format", choices=("json", "markdown"), default="json")
    report.set_defaults(handler=_progress_report)
    migrate = progress_commands.add_parser("migrate")
    migrate.add_argument("--expected-revision", type=int, required=True)
    migrate.set_defaults(handler=_progress_migrate)
    add_repair = progress_commands.add_parser("add-repair")
    add_repair.add_argument("--item", required=True)
    add_repair.add_argument("--expected-revision", type=int, required=True)
    add_repair.set_defaults(handler=_progress_add_repair)
    live_handoff = progress_commands.add_parser("handoff-live-ghidra")
    live_handoff.add_argument("--item", required=True)
    live_handoff.add_argument("--expected-revision", type=int, required=True)
    live_handoff.add_argument("--owner", required=True)
    live_handoff.add_argument("--summary", required=True)
    live_handoff.add_argument("--scope", required=True)
    live_handoff.add_argument("--evidence", action="append", default=[])
    live_handoff.add_argument("--bridge-url")
    live_handoff.set_defaults(handler=_handoff_live_ghidra)
    advance = progress_commands.add_parser("advance-live-ghidra")
    advance.add_argument("--item", required=True)
    advance.add_argument("--expected-revision", type=int, required=True)
    advance.add_argument("--accepter", required=True)
    advance.add_argument("--evidence", action="append", default=[])
    advance.add_argument("--bridge-url")
    advance.set_defaults(handler=_advance_live_ghidra)
    rebaseline = progress_commands.add_parser("rebaseline-live-ghidra")
    rebaseline.add_argument("--expected-revision", type=int, required=True)
    rebaseline.add_argument("--recorder", required=True)
    rebaseline.add_argument("--evidence", action="append", default=[])
    rebaseline.add_argument("--dry-run", action="store_true")
    rebaseline.add_argument("--bridge-url")
    rebaseline.set_defaults(handler=_rebaseline_live_ghidra)
    stage_baseline = progress_commands.add_parser("record-stage-baseline")
    stage_baseline.add_argument("--stage", required=True)
    stage_baseline.add_argument("--expected-revision", type=int, required=True)
    stage_baseline.add_argument("--recorder", required=True)
    stage_baseline.add_argument("--evidence", action="append", default=[])
    stage_baseline.add_argument("--dry-run", action="store_true")
    stage_baseline.add_argument("--bridge-url")
    stage_baseline.set_defaults(handler=_record_stage_baseline)
    decompose_stage = progress_commands.add_parser("decompose-stage")
    decompose_stage.add_argument("--stage", required=True)
    decompose_stage.add_argument("--expected-revision", type=int, required=True)
    decompose_stage.add_argument("--dry-run", action="store_true")
    decompose_stage.add_argument(
        "--refresh",
        action="store_true",
        help="rebuild a decomposed source-correlation stage from the current graph (no stage 4 plan accepted)",
    )
    decompose_stage.set_defaults(handler=_progress_decompose_stage)
    stage_scope = progress_commands.add_parser("stage-scope")
    stage_scope.add_argument("--stage", required=True)
    stage_scope.add_argument("--output")
    stage_scope.set_defaults(handler=_progress_stage_scope)

    type_plan_cli.register(recon_commands, ghidra_commands, progress_commands)
    recon_repair_cli.register(recon_commands, progress_commands)
    work = progress_commands.add_parser("work")
    work_commands = work.add_subparsers(dest="work_command", required=True)
    for name, handler in (
        ("claim", _work_claim),
        ("heartbeat", _work_heartbeat),
        ("handoff", _work_handoff),
        ("accept", _work_accept),
        ("release", _work_release),
    ):
        sub = work_commands.add_parser(name)
        sub.add_argument("--item", required=True)
        sub.add_argument("--expected-revision", type=int, required=True)
        if name in {"claim", "heartbeat", "handoff", "release"}:
            sub.add_argument("--owner", required=True)
        if name in {"claim", "heartbeat"}:
            sub.add_argument("--lease-minutes", type=int, default=60)
        if name == "handoff":
            sub.add_argument("--summary", required=True)
            sub.add_argument("--evidence", action="append", default=[])
        if name == "accept":
            sub.add_argument("--accepter", required=True)
            sub.add_argument("--evidence", action="append", default=[])
        sub.set_defaults(handler=handler)
    reject = work_commands.add_parser("reject")
    reject.add_argument("--item", required=True)
    reject.add_argument("--expected-revision", type=int, required=True)
    reject.add_argument("--reviewer", required=True)
    reject.add_argument("--reason", required=True)
    reject.add_argument("--evidence", action="append", default=[])
    reject.set_defaults(handler=_work_reject)
    reopen = work_commands.add_parser("reopen")
    reopen.add_argument("--item", required=True)
    reopen.add_argument("--expected-revision", type=int, required=True)
    reopen.add_argument("--reviewer", required=True)
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--evidence", action="append", default=[])
    reopen.set_defaults(handler=_work_reopen)
    leases = work_commands.add_parser("leases")
    leases.set_defaults(handler=_progress_work_leases)
    packet = work_commands.add_parser("packet")
    packet.add_argument("--item", required=True)
    packet.add_argument("--owner", required=True)
    packet.set_defaults(handler=_progress_work_packet)
    work_show = work_commands.add_parser("show")
    work_show.add_argument("item", nargs="?")
    work_show.set_defaults(handler=_progress_work_show)

    source = commands.add_parser("source")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    owners = source_commands.add_parser("owners")
    owners.add_argument("--rows", action="store_true")
    owners.set_defaults(handler=_source_owners)
    artifacts = source_commands.add_parser("artifacts")
    artifacts.set_defaults(handler=_source_artifacts)
    graph_command = source_commands.add_parser("graph")
    graph_command.add_argument("--segment-size", type=int, default=SOURCE_SEGMENT_SIZE)
    graph_command.add_argument("--output")
    graph_command.add_argument("--markdown")
    graph_command.set_defaults(handler=_source_graph)
    source_audit = source_commands.add_parser("audit")
    source_audit.set_defaults(handler=_source_audit)
    source_plan_cli.register(source_commands)
    source_apply_cli.register(source_commands, progress_commands)
    source_gate_cli.register(source_commands, progress_commands, audit_commands)
    provider_archive.register(commands)

    verify = commands.add_parser("verify")
    verify_commands = verify.add_subparsers(dest="verification", required=True)
    verify_asm = verify_commands.add_parser("asm")
    verify_asm.add_argument("target")
    verify_asm.add_argument("--bridge-url")
    verify_asm.set_defaults(handler=_verify_asm)
    functional = verify_commands.add_parser("functional")
    functional.add_argument("target", nargs="?")
    functional.add_argument("--dry-run", action="store_true")
    functional.set_defaults(handler=_verify_functional)
    functional_batch = verify_commands.add_parser("functional-batch")
    functional_batch.add_argument("target", nargs="*")
    functional_batch.add_argument("--dry-run", action="store_true")
    functional_batch.set_defaults(handler=_verify_functional_batch)
    for name in VERIFY_STAGE_MAP:
        sub = verify_commands.add_parser(name)
        sub.add_argument("--candidate", required=True)
        sub.add_argument("--acceptance", action="store_true")
        sub.set_defaults(handler=_verify_stage)
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    # `--json` is deliberately position-independent because every command
    # already emits canonical JSON and automation commonly appends the flag.
    # Commands with a text form (recon table-family, recon global-facts) read
    # the flag after it is stripped.
    json_requested = "--json" in argv
    argv = [argument for argument in argv if argument != "--json"]
    parser = build_parser()
    arguments = parser.parse_args(argv)
    arguments.json = json_requested
    try:
        return int(arguments.handler(arguments))
    except SocomError as exc:
        _emit({"ok": False, "error": str(exc)})
        return 2
    except KeyboardInterrupt:
        _emit({"ok": False, "error": "interrupted"})
        return 130
