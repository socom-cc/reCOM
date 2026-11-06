"""Unified reconstruction tracker with CAS revisions and work leases."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .constants import (
    EXPECTED_GHIDRA_VERSION,
    PRIMARY_STAGE_CHAIN,
    SCHEMA_VERSION,
    STAGES,
    TRACKER_ID,
    ZERO_FILL_MEMORY_ID,
)

from .capabilities import CAPABILITY_GATE_ACCEPTER, capability_opening
from .ghidra import normalize_receipt_scope
from .locking import exclusive_state_lock
from .order_plan import (
    ORDER_APPLY_KIND,
    ORDER_COMPILE_KIND,
    ORDER_COMPILE_ROUTE_ID,
    ORDER_LINK_KIND,
    ORDER_PLAN_KINDS,
    ORDER_PREPARE_KIND,
    ORDER_ROUTED_KINDS,
    ORDER_SEGMENT_KIND,
    ORDER_SKELETON_KINDS,
    ORDER_SKELETON_PREPARE_ID,
    ORDER_SKELETON_ROUTE_ID,
    ORDER_STAGE,
    audit_function_order,
    order_plan_path,
)
from .recon import REPAIR_APPLY_KIND, REPAIR_PLAN_KIND, REPAIR_PREFIX
from .repairs import REPAIRS
from .source import source_owners
from .source_plan import (
    APPLY_KIND_BY_PLAN,
    CAPABILITY_GATE_KIND,
    DATA_RECONCILE_KIND,
    PLAN_KIND_BY_SCOPE,
    PROVIDER_APPLY_KIND,
    PROVIDER_PLAN_KIND,
    SEGMENT_APPLY_KIND,
    SEGMENT_PLAN_KIND,
    SOURCE_APPLY_KINDS,
    SOURCE_APPLY_ROUTE_ID,
    SOURCE_PLAN_KINDS,
    SOURCE_PLAN_RESOURCES,
    SOURCE_SEED_ID,
    SOURCE_STAGE,
    apply_reservation,
    decomposed_directories,
    plan_path,
    scope_batches,
    scope_item_id,
    scope_key,
    verify_graph,
)
from .util import SocomError, atomic_write_json, canonical_json, load_json, stable_id

WORK_STATUSES = {
    "blocked",
    "ready",
    "in_progress",
    "awaiting_acceptance",
    "accepted",
}
STAGE_STATUSES = {"pending", "active", "accepted"}

GHIDRA_WRITER_RESOURCES = ["ghidra:soCOM/socom.elf", "ghidra-writer"]
RECON_STAGE = "ghidra-reconstruction"
RECON_SEED_ID = "socom:work:ghidra-reconstruction-seed"
RECON_PLAN_RESOURCES = ["build/recon-plans"]
# Every capability-gate work item and the stage it belongs to.
CAPABILITY_GATES = {
    SOURCE_APPLY_ROUTE_ID: SOURCE_STAGE,
    ORDER_SKELETON_ROUTE_ID: ORDER_STAGE,
    ORDER_COMPILE_ROUTE_ID: ORDER_STAGE,
}


def open_source_amendments(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    """The open amendments of the accepted stage 4 (``progress amend-source-plan``)."""

    stage = next((row for row in tracker.get("stages", []) if row.get("name") == SOURCE_STAGE), {})
    return [
        row for row in stage.get("amendments") or [] if isinstance(row, dict) and row.get("status") == "open"
    ]


def amended_items(tracker: dict[str, Any]) -> set[str]:
    """Plan and apply items that an open stage 4 amendment sends back for revision and re-apply.

    While an amendment is open the stage stays accepted, and an accepted
    stage 4 item may wait for these items (its acceptance stands).
    """

    items: set[str] = set()
    for row in open_source_amendments(tracker):
        items.add(str(row.get("item")))
        items.update(str(value) for value in row.get("applies") or [])
    return items


def _zero_fill_memory_item(foundation_apply_id: str) -> dict[str, Any]:
    return {
        "id": ZERO_FILL_MEMORY_ID,
        "stage": "debug-metadata-import",
        "kind": "ghidra-memory-map",
        "title": "Map the zero-fill load image in Ghidra",
        "status": "blocked",
        "dependencies": [foundation_apply_id],
        "resources": list(GHIDRA_WRITER_RESOURCES),
        "selection": None,
        "batch": None,
        "lease": None,
        "handoff": None,
        "evidence": [],
    }


def _repair_item(item_id: str) -> dict[str, Any]:
    """A governed repair of accepted live state (specs in repairs.REPAIRS)."""

    spec = REPAIRS[item_id]
    return {
        "id": item_id,
        "stage": spec.get("stage", "debug-metadata-import"),
        "kind": "ghidra-repair",
        "title": spec["title"],
        "status": "blocked",
        "dependencies": list(spec["dependencies"]),
        "resources": list(GHIDRA_WRITER_RESOURCES),
        "selection": None,
        "batch": None,
        "lease": None,
        "handoff": None,
        "evidence": [],
    }


def add_repair_item(tracker: dict[str, Any], item_id: str) -> None:
    """Insert a recorded repair once every apply it corrects is accepted."""

    spec = REPAIRS.get(item_id)
    if spec is None:
        raise SocomError(f"{item_id} has no recorded repair")
    items = tracker["work_items"]
    if any(row.get("id") == item_id for row in items):
        raise SocomError(f"{item_id} is already in the tracker")
    by_id = _work_by_id(tracker)
    for dependency in spec["dependencies"]:
        if by_id.get(dependency, {}).get("status") != "accepted":
            raise SocomError(f"{item_id} repairs {dependency}, which is not accepted")
    positions = [position for position, row in enumerate(items) if row.get("id") in spec["dependencies"]]
    if positions:
        items.insert(max(positions) + 1, _repair_item(item_id))
    else:
        items.append(_repair_item(item_id))
    if spec.get("stage") == RECON_STAGE:
        # A stage 3 repair is part of the stage: its gate waits for it too.
        gate = by_id.get(RECON_SEED_ID)
        if gate is None or gate.get("kind") != "stage-gate":
            raise SocomError(f"{item_id} needs the decomposed {RECON_STAGE} gate")
        gate["dependencies"] = list(gate.get("dependencies", [])) + [item_id]


TYPE_PLAN_KIND = "recon-type-plan"
TYPE_APPLY_KIND = "recon-type-apply"
TYPE_PLAN_RESOURCES = ["build/type-plans"]
TYPE_PLAN_PREFIX = "socom:work:type-plan-"


def add_type_plan_items(
    tracker: dict[str, Any],
    class_name: str | None,
    with_derived: bool,
    struct: bool = False,
    records: list[str] | None = None,
    family: str | None = None,
    registrar: str | None = None,
) -> list[str]:
    """Insert a code-derived type plan item and its live apply item into stage 3.

    The plan is file-only (``build/type-plans``) and has no dependencies: its
    evidence comes from the immutable ELF.  The apply alone owns
    ``ghidra-writer`` and waits for the accepted plan.  Both join the stage 3
    gate, as stage 3 repairs do.  ``struct`` plans a plain struct named only by
    mangled parameter types (``recon layout --struct``): the batch records
    ``"struct": true``; the item kinds and gate are the same.  ``records``
    plans one family of command records (``recon layout --records``, the
    expanded command names) as ``type-plan-<registrar>-<family>``; the batch
    records ``records``, ``family``, ``registrar`` and the optional class.
    """

    from .type_plan import records_item_id, type_plan_item_id
    from .type_records import FAMILY_SLUG, REGISTRARS

    if records is not None:
        if struct:
            raise SocomError("a records family is not a plain struct; drop --struct")
        if not records or records != sorted(set(records)) or not all(isinstance(item, str) and item for item in records):
            raise SocomError("the records are the expanded, sorted command names")
        if not family or not FAMILY_SLUG.match(family):
            raise SocomError("--family is a lower-case slug (letters, digits and hyphens)")
        if registrar not in REGISTRARS:
            raise SocomError(f"unknown registrar {registrar!r}")
        if class_name is not None and not class_name.strip():
            raise SocomError("the class name must not be empty")
        if with_derived and class_name is None:
            raise SocomError("--with-derived needs a class")
        plan_id = records_item_id(registrar, family)
    else:
        if class_name is None or not class_name.strip():
            raise SocomError("the class name must not be empty")
        if struct and with_derived:
            raise SocomError("a plain struct has no derived classes; drop --with-derived")
        plan_id = type_plan_item_id(class_name)
    apply_id = f"{plan_id}-apply"
    items = tracker["work_items"]
    if any(row.get("id") in (plan_id, apply_id) for row in items):
        raise SocomError(f"{plan_id} is already in the tracker")
    by_id = _work_by_id(tracker)
    gate = by_id.get(RECON_SEED_ID)
    if gate is None or gate.get("kind") != "stage-gate":
        raise SocomError(f"{plan_id} needs the decomposed {RECON_STAGE} gate")
    if gate.get("status") == "accepted":
        raise SocomError(f"the {RECON_STAGE} gate is already accepted")
    if records is not None:
        batch: dict[str, Any] = {"records": list(records), "family": family, "registrar": registrar, "with_derived": bool(with_derived)}
        if class_name is not None:
            batch["class"] = class_name
        subject = f"the {registrar} {family} command records ({len(records)})" + (f" with {class_name}" if class_name else "")
        title = f"Plan the code-derived layouts of {subject}" + (" and its derived classes" if with_derived else "")
    else:
        batch = {"class": class_name, "with_derived": bool(with_derived)}
        if struct:
            batch["struct"] = True
        subject = str(class_name)
        title = (
            f"Plan the code-derived layout of {'the plain struct ' if struct else ''}{class_name}"
            + (" and its derived classes" if with_derived else "")
        )
    plan = {
        "id": plan_id,
        "stage": RECON_STAGE,
        "kind": TYPE_PLAN_KIND,
        "title": title,
        "status": "blocked",
        "dependencies": [],
        "resources": list(TYPE_PLAN_RESOURCES),
        "selection": "types",
        "batch": batch,
        "lease": None,
        "handoff": None,
        "evidence": [],
    }
    apply = {
        "id": apply_id,
        "stage": RECON_STAGE,
        "kind": TYPE_APPLY_KIND,
        "title": f"Apply the reviewed code-derived types of {subject} in Ghidra",
        "status": "blocked",
        "dependencies": [plan_id],
        "resources": list(GHIDRA_WRITER_RESOURCES),
        "selection": "types",
        "batch": copy.deepcopy(batch),
        "lease": None,
        "handoff": None,
        "evidence": [],
    }
    position = next(index for index, row in enumerate(items) if row.get("id") == RECON_SEED_ID)
    items[position:position] = [plan, apply]
    gate["dependencies"] = list(gate.get("dependencies", [])) + [plan_id, apply_id]
    return [plan_id, apply_id]


RECON_REPAIR_ID = re.compile(r"^socom:work:recon-repair-(\d{3,})$")


def _global_scope_items(items: list[dict[str, Any]], address: str) -> list[dict[str, Any]]:
    """Reconstruction applies whose stored receipt scope lists the global ``address``."""

    found = []
    for row in items:
        if row.get("kind") not in ("recon-apply-group", REPAIR_APPLY_KIND):
            continue
        for value in ((row.get("ghidra_receipt") or {}).get("scope") or {}).get("globals", []):
            if "::" not in str(value) and f"0x{int(str(value), 16):x}" == address:
                found.append(row)
                break
    return found


def add_recon_repair_items(
    tracker: dict[str, Any],
    functions: list[str],
    globals_: list[str] | None = None,
    global_facts: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Insert a numbered recon repair: a file-only plan item and its live apply item.

    The repair corrects prototypes of functions whose reconstruction group is
    applied and accepted (``progress work reopen`` covers plans whose apply has
    not run).  The plan (kind ``recon-repair-plan``, ``build/recon-plans``)
    depends on the apply items of the groups it corrects and of any accepted
    earlier repair of the same functions; the apply (``recon-repair-apply``)
    alone owns ``ghidra-writer`` and waits for the accepted plan.  Both join
    the stage 3 gate.  A function already in an unfinished repair is refused.

    A repair may also list globals (with or without functions): it gives each
    its readable label and a proven type.  ``global_facts``
    (``recon_globals.global_symbol_facts``) refuses an address that is not a
    sized .symtab object, lies in a function, has file-local copies, or that a
    DWARF record describes (stage 2 typed and named those from DWARF, and a
    repair may not contradict DWARF); the tracker refuses one in an unfinished
    repair or in the receipt of an apply awaiting acceptance.  The plan then
    also depends on the accepted applies whose receipt scope lists a global.
    """

    globals_ = list(globals_ or [])
    if not functions and not globals_:
        raise SocomError("a recon repair needs at least one function or global")
    addresses = []
    for value in functions:
        try:
            addresses.append(f"0x{int(str(value), 16):x}")
        except ValueError:
            raise SocomError(f"{value!r} is not a hex function address") from None
    if len(set(addresses)) != len(addresses):
        raise SocomError("a function is listed twice")
    addresses.sort(key=lambda value: int(value, 16))
    data = []
    for value in globals_:
        try:
            data.append(f"0x{int(str(value), 16):x}")
        except ValueError:
            raise SocomError(f"{value!r} is not a hex global address") from None
    if len(set(data)) != len(data):
        raise SocomError("a global is listed twice")
    data.sort(key=lambda value: int(value, 16))
    if data and global_facts is None:
        raise SocomError("a recon repair of globals needs their ELF and DWARF facts")
    items = tracker["work_items"]
    by_id = _work_by_id(tracker)
    gate = by_id.get(RECON_SEED_ID)
    if gate is None or gate.get("kind") != "stage-gate":
        raise SocomError(f"a recon repair needs the decomposed {RECON_STAGE} gate")
    if gate.get("status") == "accepted":
        raise SocomError(f"the {RECON_STAGE} gate is already accepted")
    group_of = {
        address: row
        for row in items
        if row.get("kind") == "recon-plan-group"
        for address in row["batch"]["functions"]
    }
    dependencies: set[str] = set()
    groups: dict[str, str] = {}
    problems = []
    for address in addresses:
        group = group_of.get(address)
        if group is None:
            problems.append(f"{address} is not a function of any reconstruction group")
            continue
        apply = by_id.get(f"{group['id']}-apply") or {}
        number = group["batch"].get("group_number")
        if group.get("status") != "accepted" or apply.get("status") != "accepted":
            problems.append(
                f"{address} belongs to group {number:03d} (plan {group.get('status')}, apply {apply.get('status')}): "
                "a repair corrects applied and accepted groups only; reopen a plan whose apply has not run"
            )
            continue
        groups[address] = group["id"]
        dependencies.add(apply["id"])
        for row in items:
            if row.get("kind") != REPAIR_PLAN_KIND or address not in row["batch"]["functions"]:
                continue
            earlier = by_id.get(f"{row['id']}-apply") or {}
            if earlier.get("status") != "accepted":
                problems.append(f"{address} is in the unfinished repair {row['id']} (apply {earlier.get('status')})")
            else:
                dependencies.add(earlier["id"])
    for address in data:
        fact = (global_facts or {}).get(address) or {}
        name = ", ".join(fact.get("names") or []) or "no object"
        if not fact.get("object"):
            problems.append(f"global {address} is not the start of a sized .symtab OBJECT")
            continue
        if fact.get("inside_function"):
            problems.append(f"global {address} ({name}) lies inside function {fact['inside_function']}")
        if fact.get("dwarf"):
            records = ", ".join(f"{row['tag']} {row['die']}" for row in fact["dwarf"])
            problems.append(
                f"global {address} ({name}) has DWARF records ({records}): stage 2 typed and named it from DWARF, "
                "and a repair may not contradict DWARF"
            )
        if fact.get("copies"):
            problems.append(f"global {address} ({name}): file-local copies share {fact['copies']}, so no copy is canonical")
        for row in items:
            if row.get("kind") != REPAIR_PLAN_KIND or address not in row["batch"].get("globals", []):
                continue
            earlier = by_id.get(f"{row['id']}-apply") or {}
            if earlier.get("status") != "accepted":
                problems.append(f"global {address} is in the unfinished repair {row['id']} (apply {earlier.get('status')})")
            else:
                dependencies.add(earlier["id"])
        for row in _global_scope_items(items, address):
            if row.get("status") == "accepted":
                dependencies.add(row["id"])
            else:
                problems.append(f"global {address} is in the receipt scope of {row['id']} ({row.get('status')}); wait for its acceptance")
    if problems:
        raise SocomError("cannot add the recon repair:\n- " + "\n- ".join(problems))
    numbers = [int(match.group(1)) for row in items if (match := RECON_REPAIR_ID.match(str(row.get("id"))))]
    number = max(numbers, default=0) + 1
    plan_id = f"{REPAIR_PREFIX}{number:03d}"
    apply_id = f"{plan_id}-apply"
    decomposition = next((row for row in tracker["stages"] if row["name"] == RECON_STAGE), {}).get("decomposition") or {}
    batch = {
        "repair_number": number,
        "functions": addresses,
        "groups": groups,
        "graph_sha256": decomposition.get("graph_sha256"),
    }
    # Absent from function-only repairs, so their batches (and digests) keep their bytes.
    if data:
        batch["globals"] = data
    subject = (
        f"{len(addresses)} functions of applied groups"
        if not data
        else ", ".join(
            part for part in (f"{len(addresses)} functions of applied groups" if addresses else "", f"{len(data)} globals") if part
        )
    )
    plan = {
        "id": plan_id,
        "stage": RECON_STAGE,
        "kind": REPAIR_PLAN_KIND,
        "title": f"Plan recon repair {number:03d} ({subject})",
        "status": "blocked",
        "dependencies": sorted(dependencies),
        "resources": list(RECON_PLAN_RESOURCES),
        "selection": "functions",
        "batch": batch,
        "lease": None,
        "handoff": None,
        "evidence": [],
    }
    apply = {
        "id": apply_id,
        "stage": RECON_STAGE,
        "kind": REPAIR_APPLY_KIND,
        "title": f"Apply reviewed recon repair {number:03d} in Ghidra",
        "status": "blocked",
        "dependencies": [plan_id],
        "resources": list(GHIDRA_WRITER_RESOURCES),
        "selection": "functions",
        "batch": copy.deepcopy(batch),
        "lease": None,
        "handoff": None,
        "evidence": [],
    }
    position = next(index for index, row in enumerate(items) if row.get("id") == RECON_SEED_ID)
    items[position:position] = [plan, apply]
    gate["dependencies"] = list(gate.get("dependencies", [])) + [plan_id, apply_id]
    return [plan_id, apply_id]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _compile_unit_batches(census: dict[str, Any], chunk_size: int = 24) -> list[dict[str, Any]]:
    units = sorted(census["debug"]["compile_units"], key=lambda row: row["die_offset"])
    debug_size = next(
        section["size"] for section in census["sections"] if section["name"] == ".debug"
    )
    result = []
    for number, start in enumerate(range(0, len(units), chunk_size), 1):
        batch_units = units[start : start + chunk_size]
        ranges = []
        for unit in batch_units:
            unit_start = int(unit["die_offset"])
            # AT_sibling is represented by the next CU start in the flattened
            # stream for scheduling purposes; the importer still retains every
            # raw DWARF reference in evidence.
            global_index = start + len(ranges)
            unit_end = (
                int(units[global_index + 1]["die_offset"])
                if global_index + 1 < len(units)
                else debug_size
            )
            ranges.append([unit_start, unit_end])
        paths = [unit["name"] for unit in batch_units if unit.get("name")]
        project_count = sum(
            1 for path in paths if str(path).casefold().startswith("z:\\dev\\")
        )
        result.append(
            {
                "id": stable_id("debug-batch", number, ranges[0][0]),
                "batch_number": number,
                "die_ranges": ranges,
                "compile_unit_ids": [unit["id"] for unit in batch_units],
                "source_paths": paths,
                "project_compile_unit_count": project_count,
            }
        )
    # Project compile units first, then stable original order.
    return sorted(
        result,
        key=lambda row: (
            0 if row["project_compile_unit_count"] else 1,
            row["batch_number"],
        ),
    )


def initialize_tracker(root: Path, census: dict[str, Any]) -> dict[str, Any]:
    foundation_id = "socom:work:debug-type-foundation"
    foundation_apply_id = f"{foundation_id}-apply"
    batches = _compile_unit_batches(census)
    work_items = [
        {
            "id": foundation_id,
            "stage": "debug-metadata-import",
            "kind": "debug-import-plan-foundation",
            "title": "Plan and reconcile the global DWARF type graph",
            "status": "ready",
            "dependencies": [],
            "resources": ["build/import-plans"],
            "selection": "types",
            "batch": None,
            "lease": None,
            "handoff": None,
            "evidence": [],
        },
        {
            "id": foundation_apply_id,
            "stage": "debug-metadata-import",
            "kind": "debug-import-apply-foundation",
            "title": "Apply the reviewed global DWARF type plan in Ghidra",
            "status": "blocked",
            "dependencies": [foundation_id],
            "resources": ["ghidra:soCOM/socom.elf", "ghidra-writer"],
            "selection": "types",
            "batch": None,
            "lease": None,
            "handoff": None,
            "evidence": [],
        },
        _zero_fill_memory_item(foundation_apply_id),
    ]
    batch_apply_ids = []
    for batch in batches:
        apply_id = f"{batch['id']}-apply"
        batch_apply_ids.append(apply_id)
        work_items.append(
            {
                "id": batch["id"],
                "stage": "debug-metadata-import",
                "kind": "debug-import-plan-batch",
                "title": (
                    f"Plan DWARF compile-unit batch {batch['batch_number']:03d} "
                    f"({len(batch['compile_unit_ids'])} units)"
                ),
                "status": "blocked",
                "dependencies": [foundation_apply_id],
                "resources": ["build/import-plans"],
                "selection": "all",
                "batch": batch,
                "lease": None,
                "handoff": None,
                "evidence": [],
            }
        )
        work_items.append(
            {
                "id": apply_id,
                "stage": "debug-metadata-import",
                "kind": "debug-import-apply-batch",
                "title": (
                    f"Apply reviewed DWARF batch {batch['batch_number']:03d} in Ghidra"
                ),
                "status": "blocked",
                "dependencies": [batch["id"], ZERO_FILL_MEMORY_ID],
                "resources": ["ghidra:soCOM/socom.elf", "ghidra-writer"],
                "selection": "all",
                "batch": batch,
                "lease": None,
                "handoff": None,
                "evidence": [],
            }
        )

    stage_seed_ids: dict[str, str] = {}
    previous_dependencies = [foundation_apply_id, *batch_apply_ids]
    for stage in (
        "ghidra-reconstruction",
        "source-correlation",
        "authored-function-order",
        "authored-call-contract",
        "authored-byte-match",
        "full-function-order",
        "linked-byte-match",
        "final-validation",
    ):
        item_id = f"socom:work:{stage}-seed"
        stage_seed_ids[stage] = item_id
        if stage == "authored-byte-match":
            dependencies = [stage_seed_ids["authored-function-order"]]
        elif stage == "linked-byte-match":
            dependencies = list(previous_dependencies) + [
                stage_seed_ids["authored-byte-match"]
            ]
        else:
            dependencies = list(previous_dependencies)
        work_items.append(
            {
                "id": item_id,
                "stage": stage,
                "kind": "stage-seed",
                "title": f"Decompose and schedule {stage} work",
                "status": "blocked",
                "dependencies": dependencies,
                "resources": [],
                "selection": None,
                "batch": None,
                "lease": None,
                "handoff": None,
                "evidence": [],
            }
        )
        if stage != "authored-byte-match":
            previous_dependencies = [item_id]

    stage_rows = []
    for stage in STAGES:
        if stage == "reference-census":
            status = "accepted"
        elif stage == "debug-metadata-import":
            status = "active"
        else:
            status = "pending"
        stage_rows.append(
            {
                "id": f"socom:stage:{stage}",
                "name": stage,
                "status": status,
                "accepted_evidence": (
                    [".agent/REFERENCE_CENSUS.json"]
                    if stage == "reference-census"
                    else []
                ),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "tracker_id": TRACKER_ID,
        "revision": 1,
        "migration_history": [],
        "project": "soCOM",
        "reference": census["reference"],
        "policy": {
            "manual_json_edits_forbidden": True,
            "expected_revision_required": True,
            "ghidra_writer_limit": 1,
            "source_is_provisional": True,
            "post_link_patching_forbidden": True,
        },
        "stage_order": list(STAGES),
        "primary_stage_chain": list(PRIMARY_STAGE_CHAIN),
        "stages": stage_rows,
        "binaries": [
            {
                **census["reference"],
                "format": "ELF32",
                "machine": "MIPS/R5900",
                "endianness": "little",
            }
        ],
        "physical_blocks": [
            {
                "id": stable_id("physical-block", segment["index"]),
                "segment_index": segment["index"],
                "file_offset": segment["offset"],
                "file_size": segment["file_size"],
                "virtual_address": segment["virtual_address"],
                "memory_size": segment["memory_size"],
                "status": "reference-evidence",
            }
            for segment in census["program_headers"]
        ],
        "semantic_spans": [],
        # Symbols and relocations are immutable reference evidence: they live
        # only in the reference census (schema 6), not in the mutable tracker.
        "output_sections": census["sections"],
        "storage_contributions": [
            {
                "id": stable_id("storage", section["index"], section["name"]),
                "section_id": section["id"],
                "file_range": (
                    [section["offset"], section["offset"] + section["size"]]
                    if section["file_backed"]
                    else None
                ),
                "memory_range": (
                    [section["address"], section["address"] + section["size"]]
                    if section["size"]
                    else None
                ),
                "status": "reference-evidence",
            }
            for section in census["sections"]
        ],
        "owners": source_owners(root),
        "types": [],
        "verification_targets": [
            {
                "id": "socom:verification:reference-elf",
                "kind": "typed-elf",
                "path": "support/socom.elf",
                "expected_sha256": census["reference"]["sha256"],
                "status": "accepted-reference",
            },
            {
                "id": "socom:verification:ghidra-program",
                "kind": "ghidra-program",
                "project": "soCOM",
                "program": "socom.elf",
                "program_path": "/socom.elf",
                "source_sha256": census["reference"]["sha256"],
                "language": "r5900:LE:32:default",
                "compiler": "default",
                "ghidra_version": EXPECTED_GHIDRA_VERSION,
                "image_base": "00100000",
                "status": "unreceipted-r5900",
                "baseline_receipt_sha256": None,
                "current_receipt_sha256": None,
                "receipt_history": [],
            },
            {
                "id": "socom:verification:metrowerks-toolchain",
                "kind": "compiler",
                "path": "compiler/mwcps2-2.4-001213/mwccps2.exe",
                "status": "identity-verified-compile-blocked",
            },
        ],
        "work_items": work_items,
        "blockers": [
            {
                "id": "socom:blocker:metrowerks-flexlm-license",
                "kind": "external-toolchain-input",
                "status": "open",
                "summary": (
                    "A valid FLEXlm license.dat is required before native "
                    "Metrowerks compile probes and matching builds can run."
                ),
                "blocks": [
                    "authored-call-contract",
                    "authored-byte-match",
                    "linked-byte-match",
                    "final-validation",
                ],
                "evidence": [".agent/WORKSPACE_ISSUES.json"],
            },
            {
                "id": "socom:blocker:mips-relocation-type-123",
                "kind": "unresolved-reference-format",
                "status": "open",
                "summary": (
                    "Ten reference relocation records use numeric type 123; "
                    "their Metrowerks/Sony semantics require evidence."
                ),
                "blocks": [
                    "linked-byte-match",
                    "final-validation",
                ],
                "evidence": [
                    ".agent/REFERENCE_CENSUS.json",
                    ".agent/WORKSPACE_ISSUES.json",
                ],
            },
            {
                "id": "socom:blocker:deferred-stage-producers",
                "kind": "missing-stage-producer",
                "status": "open",
                "summary": (
                    "Later build stages remain closed until a real native producer "
                    "and stage-specific acceptance route are registered."
                ),
                "blocks": [
                    "authored-function-order",
                    "authored-call-contract",
                    "authored-byte-match",
                    "full-function-order",
                    "linked-byte-match",
                    "final-validation",
                ],
                "evidence": ["docs/reconstruction/TOOL_COVERAGE.md"],
            }
        ],
        "evidence": [
            {
                "id": "socom:evidence:reference-census",
                "kind": "generated-census",
                "path": ".agent/REFERENCE_CENSUS.json",
                "authority": "immutable-reference",
            }
        ],
        "tombstones": [],
    }


def load_tracker(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if not isinstance(value, dict):
        raise SocomError(f"tracker root must be an object: {path}")
    return value


def _work_by_id(tracker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in tracker["work_items"]}


def audit_tracker(
    tracker: dict[str, Any],
    *,
    strict: bool = False,
    census: dict[str, Any] | None = None,
) -> list[str]:
    errors = []
    if tracker.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version {tracker.get('schema_version')} != {SCHEMA_VERSION}"
        )
    if tracker.get("tracker_id") != TRACKER_ID:
        errors.append(f"tracker_id must be {TRACKER_ID}")
    if tracker.get("project") != "soCOM":
        errors.append("project must be soCOM")
    if tracker.get("policy", {}).get("ghidra_writer_limit") != 1:
        errors.append("policy must enforce one Ghidra writer")
    if not isinstance(tracker.get("revision"), int) or tracker["revision"] < 1:
        errors.append("revision must be a positive integer")
    if not isinstance(tracker.get("migration_history"), list):
        errors.append("migration_history must be a list")
    for moved in ("symbols", "relocations"):
        if moved in tracker and (tracker.get("schema_version") or 0) >= 6:
            errors.append(f"{moved} belong to the reference census, not the tracker (schema 6)")
    if tracker.get("stage_order") != list(STAGES):
        errors.append("stage_order differs from the canonical ten-stage pipeline")
    stage_rows = tracker.get("stages", [])
    stage_names = [row.get("name") for row in stage_rows]
    if stage_names != list(STAGES):
        errors.append("stage rows differ from stage_order")
    for row in stage_rows:
        if row.get("status") not in STAGE_STATUSES:
            errors.append(f"stage {row.get('name')} has invalid status {row.get('status')}")

    ghidra_targets = [
        row
        for row in tracker.get("verification_targets", [])
        if row.get("id") == "socom:verification:ghidra-program"
    ]
    if len(ghidra_targets) != 1:
        errors.append("tracker must contain exactly one Ghidra verification target")
    else:
        target = ghidra_targets[0]
        required_target = {
            "kind": "ghidra-program",
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "language": "r5900:LE:32:default",
            "compiler": "default",
            "ghidra_version": EXPECTED_GHIDRA_VERSION,
            "image_base": "00100000",
        }
        for key, expected in required_target.items():
            if target.get(key) != expected:
                errors.append(
                    f"Ghidra target {key} is {target.get(key)!r}, expected {expected!r}"
                )
        history = target.get("receipt_history")
        if not isinstance(history, list):
            errors.append("Ghidra target receipt_history must be a list")
        elif history and target.get("current_receipt_sha256") != history[-1].get(
            "receipt_sha256"
        ):
            errors.append("Ghidra current receipt differs from receipt history")

    items = tracker.get("work_items", [])
    ids = [item.get("id") for item in items]
    if len(ids) != len(set(ids)):
        errors.append("work item IDs are not unique")
    known = set(ids)
    amended = amended_items(tracker)
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.startswith(
            ("socom:work:", "socom:debug-batch:", "socom:recon-group:")
        ):
            errors.append(f"invalid work item ID: {item_id!r}")
        status = item.get("status")
        if not isinstance(item.get("dependencies"), list):
            errors.append(f"{item_id} dependencies must be a list")
            continue
        if status not in WORK_STATUSES:
            errors.append(f"{item_id} has invalid status {status}")
        if item.get("stage") not in STAGES:
            errors.append(f"{item_id} references an unknown stage")
        kind = item.get("kind")
        resources = set(item.get("resources", []))
        if str(kind).startswith("debug-import-plan-"):
            if "ghidra-writer" in resources or any(
                value.startswith("ghidra:") for value in resources
            ):
                errors.append(f"{item_id} is a plan item with Ghidra resources")
            if resources != {"build/import-plans"}:
                errors.append(f"{item_id} plan resources are not file-only")
            expected_dependencies = (
                []
                if kind == "debug-import-plan-foundation"
                else ["socom:work:debug-type-foundation-apply"]
            )
            if item.get("dependencies") != expected_dependencies:
                errors.append(f"{item_id} plan dependencies differ from contract")
        if str(kind).startswith("debug-import-apply-"):
            required_resources = set(GHIDRA_WRITER_RESOURCES)
            if resources != required_resources:
                errors.append(f"{item_id} apply resources differ from Ghidra contract")
            expected_plan = str(item_id).removesuffix("-apply")
            # Batch applies also wait for the zero-fill image their globals use.
            expected_dependencies = (
                [expected_plan, ZERO_FILL_MEMORY_ID]
                if kind == "debug-import-apply-batch"
                else [expected_plan]
            )
            if item.get("dependencies") != expected_dependencies:
                errors.append(
                    f"{item_id} dependencies differ from {expected_dependencies}"
                )
        if kind == "ghidra-memory-map":
            if item_id != ZERO_FILL_MEMORY_ID:
                errors.append(f"{item_id} is an unexpected memory-map item")
            if resources != set(GHIDRA_WRITER_RESOURCES):
                errors.append(f"{item_id} memory-map resources differ from Ghidra contract")
            if item.get("dependencies") != ["socom:work:debug-type-foundation-apply"]:
                errors.append(f"{item_id} must depend only on the type foundation apply")
        if kind == "ghidra-repair":
            spec = REPAIRS.get(str(item_id))
            if spec is None:
                errors.append(f"{item_id} is a repair item without a recorded repair")
            else:
                if resources != set(GHIDRA_WRITER_RESOURCES):
                    errors.append(f"{item_id} repair resources differ from Ghidra contract")
                if item.get("dependencies") != spec["dependencies"]:
                    errors.append(f"{item_id} dependencies differ from {spec['dependencies']}")
        if kind == "stage-seed" and status != "blocked":
            errors.append(f"{item_id} undecomposed stage seed must remain blocked")
        if kind == "recon-plan-group":
            if resources != set(RECON_PLAN_RESOURCES):
                errors.append(f"{item_id} plan resources are not file-only")
            if not all(
                str(dep).startswith("socom:recon-group:") and str(dep).endswith("-apply")
                for dep in item.get("dependencies", [])
            ):
                errors.append(f"{item_id} plan may depend only on reconstruction apply items")
        if kind == "recon-apply-group":
            if resources != set(GHIDRA_WRITER_RESOURCES):
                errors.append(f"{item_id} apply resources differ from Ghidra contract")
            if item.get("dependencies") != [str(item_id).removesuffix("-apply")]:
                errors.append(f"{item_id} must depend only on its plan")
        if kind == REPAIR_PLAN_KIND:
            batch = item.get("batch") or {}
            if not RECON_REPAIR_ID.match(str(item_id)):
                errors.append(f"{item_id} is not a recon repair plan ID")
            if resources != set(RECON_PLAN_RESOURCES):
                errors.append(f"{item_id} repair plan resources are not file-only")
            functions = batch.get("functions") or []
            listed_globals = batch.get("globals")
            if (not functions and not listed_globals) or functions != sorted(set(functions), key=lambda value: int(value, 16)):
                errors.append(f"{item_id} must list its functions once each, in address order")
            if listed_globals is not None and (
                not listed_globals or listed_globals != sorted(set(listed_globals), key=lambda value: int(value, 16))
            ):
                errors.append(f"{item_id} must list its globals once each, in address order")
            if set(batch.get("groups") or {}) != set(functions):
                errors.append(f"{item_id} must name the group of every function it repairs")
            wanted = {f"{group}-apply" for group in (batch.get("groups") or {}).values()}
            dependencies = set(item.get("dependencies", []))
            if not wanted <= dependencies or not all(
                str(dep).endswith("-apply")
                and (str(dep).startswith("socom:recon-group:") or RECON_REPAIR_ID.match(str(dep).removesuffix("-apply")))
                for dep in dependencies
            ):
                errors.append(f"{item_id} must depend on the applies of the groups it repairs (and earlier repairs only)")
        if kind == REPAIR_APPLY_KIND:
            if resources != set(GHIDRA_WRITER_RESOURCES):
                errors.append(f"{item_id} apply resources differ from Ghidra contract")
            if item.get("dependencies") != [str(item_id).removesuffix("-apply")]:
                errors.append(f"{item_id} must depend only on its repair plan")
        if kind == TYPE_PLAN_KIND:
            if resources != set(TYPE_PLAN_RESOURCES):
                errors.append(f"{item_id} type plan resources are not file-only")
            if item.get("dependencies") != []:
                errors.append(f"{item_id} type plan must not depend on other items")
            if not str(item_id).startswith(TYPE_PLAN_PREFIX) or str(item_id).endswith("-apply"):
                errors.append(f"{item_id} is not a type plan ID")
            if (item.get("batch") or {}).get("struct") and (item.get("batch") or {}).get("with_derived"):
                errors.append(f"{item_id} plans a plain struct with derived classes")
            batch = item.get("batch") or {}
            if "records" in batch:
                records = batch.get("records")
                if (
                    not isinstance(records, list) or not records or records != sorted(set(records))
                    or not all(isinstance(entry, str) and entry for entry in records)
                    or batch.get("struct")
                    or not isinstance(batch.get("family"), str) or not isinstance(batch.get("registrar"), str)
                    or str(item_id) != f"{TYPE_PLAN_PREFIX}{batch.get('registrar')}-{batch.get('family')}"
                ):
                    errors.append(f"{item_id} records batch needs sorted command names, a family and a registrar matching its ID")
        if kind == TYPE_APPLY_KIND:
            if resources != set(GHIDRA_WRITER_RESOURCES):
                errors.append(f"{item_id} apply resources differ from Ghidra contract")
            if item.get("dependencies") != [str(item_id).removesuffix("-apply")]:
                errors.append(f"{item_id} must depend only on its type plan")
        if item.get("stage") == SOURCE_STAGE and (
            "ghidra-writer" in resources or any(str(value).startswith("ghidra:") for value in resources)
        ):
            errors.append(f"{item_id} owns a Ghidra resource in the file-only {SOURCE_STAGE} stage")
        if kind in SOURCE_PLAN_KINDS or kind in SOURCE_APPLY_KINDS:
            if item.get("stage") != SOURCE_STAGE:
                errors.append(f"{item_id} is a {kind} item outside {SOURCE_STAGE}")
        if kind in SOURCE_PLAN_KINDS:
            batch = item.get("batch") or {}
            scope = batch.get("scope")
            if resources != set(SOURCE_PLAN_RESOURCES):
                errors.append(f"{item_id} source plan resources are not file-only")
            try:
                expected_id = scope_item_id(scope)
                expected_kind = PLAN_KIND_BY_SCOPE[scope["kind"]]
            except (SocomError, KeyError, TypeError, ValueError):
                errors.append(f"{item_id} has no valid planning scope")
            else:
                if expected_id != item_id or expected_kind != kind:
                    errors.append(f"{item_id} differs from the {expected_kind} ID {expected_id} its scope gives")
            if not all(isinstance(batch.get(key), str) and len(batch[key]) == 64 for key in ("graph_sha256", "slice_sha256")):
                errors.append(f"{item_id} must cite its graph and slice digests")
            if kind != DATA_RECONCILE_KIND and item.get("dependencies") != [RECON_SEED_ID]:
                errors.append(f"{item_id} must depend only on the accepted {RECON_STAGE} gate")
        if kind in SOURCE_APPLY_KINDS:
            plan_id = str(item_id).removesuffix("-apply")
            plan = _work_by_id(tracker).get(plan_id)
            if not str(item_id).endswith("-apply") or plan is None or APPLY_KIND_BY_PLAN.get(plan.get("kind")) != kind:
                errors.append(f"{item_id} has no matching source plan item")
            elif (item.get("batch") or {}).get("scope") != (plan.get("batch") or {}).get("scope"):
                errors.append(f"{item_id} plans another scope than {plan_id}")
            batch = item.get("batch") or {}
            decomposed = set(decomposed_directories(item))
            correction = batch.get("reservation_correction")
            if kind == PROVIDER_APPLY_KIND:
                # Provider ownership is recorded in tracker evidence only.
                if resources or "directories" in batch or correction is not None:
                    errors.append(f"{item_id} writes nothing under src/: a provider apply reserves no resource")
            elif not resources or not all(value == "src" or str(value).startswith("src/") for value in resources):
                errors.append(f"{item_id} must reserve its src/ directories")
            elif sorted(resources) != sorted(batch.get("directories") or []):
                errors.append(f"{item_id} resources differ from its batch directories")
            elif correction is not None and (
                not isinstance(correction, dict)
                or not decomposed
                or not all(value == "src" or str(value).startswith("src/") for value in decomposed)
                or not isinstance(correction.get("plan_sha256"), str)
                or len(correction["plan_sha256"]) != 64
            ):
                errors.append(f"{item_id} reservation correction needs the decomposed directories and the plan SHA-256")
            else:
                inferred = batch.get("resource_inferred")
                reason = batch.get("resource_reason")
                stated = isinstance(reason, str) and bool(reason.strip())
                if not isinstance(inferred, bool):
                    errors.append(f"{item_id} must record whether its reservation is inferred")
                elif inferred and (not stated or decomposed == {"src"}):
                    errors.append(f"{item_id} inferred reservation needs a reason and a narrower directory than src")
                elif decomposed == {"src"} and not stated:
                    errors.append(f"{item_id} reserves all of src without the reason no inference was possible")
            errors.extend(_audit_source_apply_record(item, resources))
        if kind == CAPABILITY_GATE_KIND:
            if item_id not in CAPABILITY_GATES:
                errors.append(f"{item_id} is an unexpected capability gate")
            elif item.get("stage") != CAPABILITY_GATES[item_id]:
                errors.append(f"{item_id} is a capability gate outside {CAPABILITY_GATES[item_id]}")
            if resources or item.get("dependencies"):
                errors.append(f"{item_id} capability gate must own no resources and have no dependencies")
            if status == "accepted":
                # Only `progress open-capability-gate` accepts a gate, once an
                # active capability registers the route it waits for.
                capability = capability_opening(str(item_id))
                accepted_by = (item.get("accepted") or {})
                if capability is None or capability.get("status") != "active":
                    errors.append(f"{item_id} is accepted but no active capability opens it")
                elif accepted_by.get("capability") != capability["id"] or accepted_by.get("by") != CAPABILITY_GATE_ACCEPTER:
                    errors.append(f"{item_id} must be accepted by {CAPABILITY_GATE_ACCEPTER} for capability {capability['id']}")
            elif status != "blocked":
                errors.append(
                    f"{item_id} capability gate must stay blocked until progress open-capability-gate accepts it"
                )
        if kind == "stage-gate" and resources:
            errors.append(f"{item_id} stage gate must not own resources")
        missing = set(item.get("dependencies", [])) - known
        if missing:
            errors.append(f"{item_id} has missing dependencies {sorted(missing)}")
        if status == "accepted":
            unmet = [
                dep
                for dep in item.get("dependencies", [])
                if _work_by_id(tracker)[dep]["status"] != "accepted"
            ]
            if unmet and item.get("stage") == SOURCE_STAGE and set(unmet) <= amended:
                # An accepted stage 4 item keeps its acceptance while an open
                # amendment revises and re-applies the items it waits for.
                unmet = []
            if unmet == [ORDER_SKELETON_PREPARE_ID] and kind == ORDER_APPLY_KIND and any(
                isinstance(entry, dict) and entry.get("reopened_at")
                for entry in (_work_by_id(tracker).get(ORDER_SKELETON_PREPARE_ID) or {}).get("review_history") or []
            ):
                # An accepted segment apply keeps its acceptance while the reopened prepare is re-applied.
                unmet = []
            if unmet:
                errors.append(f"{item_id} is accepted before dependencies {unmet}")
        lease = item.get("lease")
        if status == "in_progress" and not lease:
            errors.append(f"{item_id} is in_progress without a lease")
        if status != "in_progress" and lease:
            errors.append(f"{item_id} has a lease while status is {status}")
        handoff = item.get("handoff")
        accepted = item.get("accepted")
        if (
            isinstance(handoff, dict)
            and isinstance(accepted, dict)
            and handoff.get("owner")
            and handoff.get("owner") == accepted.get("by")
        ):
            errors.append(f"{item_id} was self-accepted by {accepted.get('by')}")
        if (
            "ghidra-writer" in item.get("resources", [])
            and status in {"awaiting_acceptance", "accepted"}
        ):
            live_receipt = item.get("ghidra_receipt")
            if not isinstance(live_receipt, dict):
                errors.append(f"{item_id} has no Ghidra semantic receipt")
            elif not (
                live_receipt.get("receipt_sha256")
                and isinstance(live_receipt.get("scope"), dict)
                and live_receipt.get("saved") is True
            ):
                errors.append(f"{item_id} has an incomplete Ghidra semantic receipt")

    active_writer = [
        item["id"]
        for item in items
        if item.get("status") == "in_progress"
        and "ghidra-writer" in item.get("resources", [])
    ]
    if len(active_writer) > 1:
        errors.append(f"multiple Ghidra writers are active: {active_writer}")
    plan_ids = {
        item["id"]
        for item in items
        if str(item.get("kind", "")).startswith("debug-import-plan-")
    }
    apply_items = [
        item
        for item in items
        if str(item.get("kind", "")).startswith("debug-import-apply-")
    ]
    for item in apply_items:
        if not set(item.get("dependencies", [])) - {ZERO_FILL_MEMORY_ID} <= plan_ids:
            errors.append(f"{item['id']} does not depend on its reviewed plan")
    if [item["id"] for item in items if item.get("kind") == "ghidra-memory-map"] != [
        ZERO_FILL_MEMORY_ID
    ]:
        errors.append(f"tracker must hold exactly one {ZERO_FILL_MEMORY_ID} item")
    if {
        f"{item['id']}-apply"
        for item in items
        if str(item.get("kind", "")).startswith("debug-import-plan-")
    } != {item["id"] for item in apply_items}:
        errors.append("debug import plan/apply item pairing is incomplete")
    reconstruction_seed = next(
        (item for item in items if item.get("id") == "socom:work:ghidra-reconstruction-seed"),
        None,
    )
    recon_plans = [item for item in items if item.get("kind") == "recon-plan-group"]
    recon_applies = [item for item in items if item.get("kind") == "recon-apply-group"]
    if {f"{item['id']}-apply" for item in recon_plans} != {item["id"] for item in recon_applies}:
        errors.append("reconstruction plan/apply item pairing is incomplete")
    type_items = {item["id"] for item in items if item.get("kind") in (TYPE_PLAN_KIND, TYPE_APPLY_KIND)}
    recon_repairs = {item["id"] for item in items if item.get("kind") in (REPAIR_PLAN_KIND, REPAIR_APPLY_KIND)}
    if {f"{item['id']}-apply" for item in items if item.get("kind") == REPAIR_PLAN_KIND} != {
        item["id"] for item in items if item.get("kind") == REPAIR_APPLY_KIND
    }:
        errors.append("recon repair plan/apply item pairing is incomplete")
    if {f"{item['id']}-apply" for item in items if item.get("kind") == TYPE_PLAN_KIND} != {
        item["id"] for item in items if item.get("kind") == TYPE_APPLY_KIND
    }:
        errors.append("type plan/apply item pairing is incomplete")
    if reconstruction_seed is not None:
        seed_dependencies = set(reconstruction_seed.get("dependencies", []))
        if reconstruction_seed.get("kind") == "stage-seed":
            if recon_plans or seed_dependencies != {item["id"] for item in apply_items}:
                errors.append("Ghidra reconstruction seed does not depend on all debug apply items")
        elif reconstruction_seed.get("kind") == "stage-gate":
            stage_repairs = {
                item["id"] for item in items if item.get("kind") == "ghidra-repair" and item.get("stage") == RECON_STAGE
            }
            if not recon_applies or seed_dependencies != (
                {item["id"] for item in recon_applies} | stage_repairs | type_items | recon_repairs
            ):
                errors.append("Ghidra reconstruction gate does not depend on all reconstruction apply items")
        else:
            errors.append(f"{RECON_SEED_ID} has unexpected kind {reconstruction_seed.get('kind')!r}")
    recon_stage = next((row for row in stage_rows if row.get("name") == RECON_STAGE), {})
    decomposition = recon_stage.get("decomposition")
    if recon_plans and (
        not isinstance(decomposition, dict) or decomposition.get("group_count") != len(recon_plans)
    ):
        errors.append(f"{RECON_STAGE} decomposition record differs from its plan items")
    if decomposition and any(
        (item.get("batch") or {}).get("graph_sha256") != decomposition.get("graph_sha256")
        for item in recon_plans + recon_applies
    ):
        errors.append(f"{RECON_STAGE} items cite a different function graph")
    errors.extend(_audit_source_correlation(items, stage_rows))
    errors.extend(audit_function_order(tracker))
    from .order_reopen import audit_reopenings
    from .order_skeleton_route import audit_skeleton_records

    errors.extend(audit_skeleton_records(tracker))
    errors.extend(audit_reopenings(tracker))
    from .source_gate import audit_source_gate

    errors.extend(audit_source_gate(tracker))
    if strict:
        required_collections = (
            "binaries",
            "physical_blocks",
            "semantic_spans",
            "output_sections",
            "storage_contributions",
            "owners",
            "types",
            "verification_targets",
            "work_items",
            "blockers",
            "evidence",
            "tombstones",
        )
        for name in required_collections:
            if not isinstance(tracker.get(name), list):
                errors.append(f"{name} must be a list")
        for collection in ("owners", "blockers"):
            for row in tracker.get(collection, []):
                if not isinstance(row, dict) or not str(row.get("id", "")).startswith(
                    "socom:"
                ):
                    errors.append(f"{collection} contains an invalid entity ID")
        for item in items:
            for key in ("id", "stage", "status", "dependencies", "lease"):
                if key not in item:
                    errors.append(f"{item.get('id')} is missing required field {key}")
        derived = copy.deepcopy(tracker)
        _refresh_ready_and_stages(derived)
        actual_stage_status = {
            row.get("name"): row.get("status") for row in stage_rows
        }
        derived_stage_status = {
            row.get("name"): row.get("status") for row in derived.get("stages", [])
        }
        if actual_stage_status != derived_stage_status:
            errors.append(
                "stored stage status differs from dependency-derived stage status"
            )
        for row in stage_rows:
            baseline = row.get("baseline")
            if not baseline:
                continue
            name = row.get("name")
            if name == SOURCE_STAGE:
                # A file-only stage's baseline: checked by audit_source_gate.
                continue
            if row.get("status") != "accepted":
                errors.append(f"stage {name} records a baseline but is not accepted")
            try:
                expected_scope = scope_sha256(stage_live_scope(tracker, name))
            except SocomError as failure:
                errors.append(f"stage {name} baseline scope is unavailable: {failure}")
            else:
                if baseline.get("scope_sha256") != expected_scope:
                    errors.append(
                        f"stage {name} baseline scope differs from its live item scopes"
                    )
            citation = f"ghidra-receipt-sha256:{baseline.get('receipt_sha256')}"
            if citation not in row.get("accepted_evidence", []):
                errors.append(f"stage {name} accepted evidence omits its baseline receipt")
        if census is not None:
            if tracker.get("reference") != census.get("reference"):
                errors.append("tracker reference identity differs from reference census")
            census_sections = census.get("sections", [])
            if tracker.get("output_sections") != census_sections:
                errors.append("tracker output sections differ from reference census")
    return errors


def _audit_source_apply_record(item: dict[str, Any], resources: set[str]) -> list[str]:
    """A source apply's ``source_apply`` record (``progress apply-source-plan``)."""

    item_id = item.get("id")
    record = item.get("source_apply")
    if record is None:
        if item.get("status") in ("awaiting_acceptance", "accepted"):
            return [f"{item_id} has no source_apply record: only progress apply-source-plan applies a plan"]
        return []
    if not isinstance(record, dict):
        return [f"{item_id} source_apply must be an object"]
    errors: list[str] = []
    sha = record.get("plan_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or record.get("plan_item") != str(item_id).removesuffix("-apply"):
        errors.append(f"{item_id} source_apply must name its plan item and the plan SHA-256")
    files = record.get("files")
    removed = record.get("removed")
    if (
        not isinstance(files, list)
        or not all(isinstance(row, dict) and isinstance(row.get("path"), str) and len(str(row.get("sha256"))) == 64 for row in files)
        or not isinstance(removed, list)
        or not all(isinstance(path, str) for path in removed)
    ):
        errors.append(f"{item_id} source_apply must list its files with SHA-256s and its removed paths")
        return errors
    paths = [row["path"] for row in files] + list(removed)
    if item.get("kind") == PROVIDER_APPLY_KIND:
        if paths:
            errors.append(f"{item_id} is a provider apply: it records no file")
        return errors
    directories = sorted(resources, key=str.casefold)
    if (record.get("reservation") or {}).get("directories") != directories:
        errors.append(f"{item_id} source_apply reservation differs from its resources")
    outside = [path for path in paths if not any(path.startswith(f"{directory}/") for directory in directories)]
    if outside:
        errors.append(f"{item_id} source_apply records paths outside its reservation: {outside[:5]}")
    return errors


def _audit_source_correlation(items: list[dict[str, Any]], stage_rows: list[dict[str, Any]]) -> list[str]:
    """Structure of the decomposed stage 4: pairs, reconciles, route and gate."""

    errors: list[str] = []
    plans = [item for item in items if item.get("kind") in SOURCE_PLAN_KINDS and item.get("kind") != DATA_RECONCILE_KIND]
    reconciles = [item for item in items if item.get("kind") == DATA_RECONCILE_KIND]
    applies = [item for item in items if item.get("kind") in SOURCE_APPLY_KINDS]
    routes = [item for item in items if item.get("kind") == CAPABILITY_GATE_KIND and item.get("stage") == SOURCE_STAGE]
    if {f"{item['id']}-apply" for item in plans} != {item["id"] for item in applies}:
        errors.append("source plan/apply item pairing is incomplete")
    plan_ids = sorted(item["id"] for item in plans)
    reconcile_ids = [item["id"] for item in reconciles]
    for item in reconciles:
        if sorted(item.get("dependencies", [])) != plan_ids:
            errors.append(f"{item['id']} must depend on every source plan item")
    for item in applies:
        wanted = {str(item["id"]).removesuffix("-apply"), *reconcile_ids, SOURCE_APPLY_ROUTE_ID}
        if set(item.get("dependencies", [])) != wanted or len(item.get("dependencies", [])) != len(wanted):
            errors.append(f"{item['id']} must depend on its plan, every data reconcile and {SOURCE_APPLY_ROUTE_ID}")
    seed = next((item for item in items if item.get("id") == SOURCE_SEED_ID), None)
    stage = next((row for row in stage_rows if row.get("name") == SOURCE_STAGE), {})
    decomposition = stage.get("decomposition")
    decomposed = plans or reconciles or applies or routes
    if seed is not None and seed.get("kind") == "stage-seed":
        if decomposed or decomposition:
            errors.append(f"{SOURCE_STAGE} has source items or a decomposition but an undecomposed seed")
    elif seed is not None and seed.get("kind") == "stage-gate":
        if not isinstance(decomposition, dict) or not applies:
            errors.append(f"{SOURCE_STAGE} gate has no decomposition record or apply items")
        if set(seed.get("dependencies", [])) != {item["id"] for item in applies} | set(reconcile_ids):
            errors.append(f"{SOURCE_STAGE} gate does not depend on every apply and data reconcile")
        if [item["id"] for item in routes] != [SOURCE_APPLY_ROUTE_ID]:
            errors.append(f"{SOURCE_STAGE} needs exactly one {SOURCE_APPLY_ROUTE_ID} item")
    elif seed is not None:
        errors.append(f"{SOURCE_SEED_ID} has unexpected kind {seed.get('kind')!r}")
    if isinstance(decomposition, dict):
        counts = Counter(item.get("kind") for item in plans)
        if (
            counts.get(SEGMENT_PLAN_KIND, 0) != decomposition.get("authored_segment_count")
            or counts.get(PROVIDER_PLAN_KIND, 0) != len(decomposition.get("provider_libraries") or [])
            or len(reconciles) != len(decomposition.get("data_kinds") or [])
        ):
            errors.append(f"{SOURCE_STAGE} decomposition record differs from its plan items")
        segment_applies = [item for item in applies if item.get("kind") == SEGMENT_APPLY_KIND]
        recorded = {
            name: sorted(str((row or {}).get("item")) for row in decomposition.get(name) or [])
            for name in ("inferred_reservations", "fallback_reservations")
        }
        actual = {
            "inferred_reservations": sorted(
                item["id"] for item in segment_applies if (item.get("batch") or {}).get("resource_inferred") is True
            ),
            "fallback_reservations": sorted(
                item["id"]
                for item in segment_applies
                if decomposed_directories(item) == ["src"] and (item.get("batch") or {}).get("resource_inferred") is not True
            ),
        }
        if recorded != actual:
            errors.append(f"{SOURCE_STAGE} decomposition record differs from its inferred and fallback reservations")
        if any(
            (item.get("batch") or {}).get("graph_sha256") != decomposition.get("graph_sha256")
            for item in plans + reconciles + applies
        ):
            errors.append(f"{SOURCE_STAGE} items cite a different source graph")
    return errors


def require_revision(tracker: dict[str, Any], expected_revision: int) -> None:
    actual = tracker["revision"]
    if actual != expected_revision:
        raise SocomError(f"revision conflict: expected {expected_revision}, actual {actual}")


def _refresh_ready_and_stages(tracker: dict[str, Any]) -> None:
    from .order_reopen import held_items

    items = _work_by_id(tracker)
    # A stage 5 item an open reopening sent back waits for the rebase that absorbs its stage 4 amendment.
    held = held_items(tracker)
    for item in tracker["work_items"]:
        if item["status"] != "blocked":
            continue
        if item.get("kind") in ("stage-seed", CAPABILITY_GATE_KIND):
            # A seed waits for its producer, a capability gate for its route.
            continue
        if item["id"] in held:
            continue
        if all(items[dep]["status"] == "accepted" for dep in item["dependencies"]):
            item["status"] = "ready"

    # An open amendment of the accepted stage 4 keeps the stage accepted.
    amended = amended_items(tracker)
    for stage in tracker["stages"]:
        stage_items = [
            item for item in tracker["work_items"] if item["stage"] == stage["name"]
        ]
        if stage["name"] == "reference-census":
            stage["status"] = "accepted"
        elif stage_items and all(
            item["status"] == "accepted" or (stage["name"] == SOURCE_STAGE and item["id"] in amended)
            for item in stage_items
        ):
            stage["status"] = "accepted"
        elif any(
            item["status"] in {"ready", "in_progress", "awaiting_acceptance"}
            for item in stage_items
        ):
            stage["status"] = "active"
        else:
            stage["status"] = "pending"


def refresh_ready_and_stages(tracker: dict[str, Any]) -> None:
    """Derive ready items and stage status, as every mutation does."""

    _refresh_ready_and_stages(tracker)


def next_work(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    _expire_leases_in_memory(tracker)
    ready = [item for item in tracker["work_items"] if item["status"] == "ready"]
    stage_rank = {name: index for index, name in enumerate(STAGES)}
    return sorted(
        ready,
        key=lambda item: (
            stage_rank[item["stage"]],
            int((item.get("batch") or {}).get("batch_number") or 0),
            item["id"],
        ),
    )


def find_rows(
    tracker: dict[str, Any], query: str, census: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Rows whose text contains ``query``; symbols come from the reference census."""

    folded = query.casefold()
    result = []
    sources = [("symbols", (census or {}).get("symbols", []))] + [
        (collection, tracker.get(collection, []))
        for collection in ("owners", "types", "work_items", "blockers", "evidence")
    ]
    for collection, rows in sources:
        for row in rows:
            if folded in str(row).casefold():
                result.append({"collection": collection, "row": row})
    return result


def _expire_leases_in_memory(tracker: dict[str, Any]) -> None:
    now = _utc_now()
    for item in tracker["work_items"]:
        lease = item.get("lease")
        if not lease:
            continue
        expires = dt.datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00"))
        if expires <= now:
            item["lease"] = None
            item["status"] = "ready"


def mutate(
    path: Path,
    expected_revision: int,
    operation: Any,
) -> dict[str, Any]:
    with exclusive_state_lock(path):
        tracker = load_tracker(path)
        require_revision(tracker, expected_revision)
        _expire_leases_in_memory(tracker)
        updated = copy.deepcopy(tracker)
        operation(updated)
        _refresh_ready_and_stages(updated)
        updated["revision"] += 1
        if errors := audit_tracker(updated):
            raise SocomError("tracker mutation rejected:\n- " + "\n- ".join(errors))
        atomic_write_json(path, updated)
        return updated


def claim_work(
    tracker: dict[str, Any],
    item_id: str,
    owner: str,
    lease_minutes: int,
) -> None:
    item = _work_by_id(tracker).get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    if item.get("kind") == "stage-seed":
        raise SocomError(
            f"{item_id} is an undecomposed stage seed; register a real producer first"
        )
    if item.get("kind") == CAPABILITY_GATE_KIND:
        raise SocomError(
            f"{item_id} is a capability gate: it opens when its route is registered, not by a worker"
        )
    if item["status"] != "ready":
        raise SocomError(f"{item_id} is {item['status']}, not ready")
    if lease_minutes < 1 or lease_minutes > 240:
        raise SocomError("lease duration must be between 1 and 240 minutes")
    if "ghidra-writer" in item.get("resources", []):
        other = [
            row["id"]
            for row in tracker["work_items"]
            if row["id"] != item_id
            and row["status"] == "in_progress"
            and "ghidra-writer" in row.get("resources", [])
        ]
        if other:
            raise SocomError(f"Ghidra writer is already claimed by {other[0]}")
    now = _utc_now()
    item["status"] = "in_progress"
    item["lease"] = {
        "owner": owner,
        "claimed_at": _iso(now),
        "heartbeat_at": _iso(now),
        "expires_at": _iso(now + dt.timedelta(minutes=lease_minutes)),
    }


def heartbeat_work(
    tracker: dict[str, Any], item_id: str, owner: str, lease_minutes: int
) -> None:
    item = _work_by_id(tracker).get(item_id)
    if not item or item["status"] != "in_progress" or not item.get("lease"):
        raise SocomError(f"{item_id} does not have an active lease")
    if item["lease"]["owner"] != owner:
        raise SocomError(f"{item_id} is leased by {item['lease']['owner']}")
    now = _utc_now()
    item["lease"]["heartbeat_at"] = _iso(now)
    item["lease"]["expires_at"] = _iso(now + dt.timedelta(minutes=lease_minutes))


def handoff_work(
    tracker: dict[str, Any],
    item_id: str,
    owner: str,
    summary: str,
    evidence: list[str],
) -> None:
    item = _work_by_id(tracker).get(item_id)
    if not item or item["status"] != "in_progress" or not item.get("lease"):
        raise SocomError(f"{item_id} is not actively leased")
    if item.get("kind") == "stage-seed":
        raise SocomError(f"{item_id} is an undecomposed stage seed")
    if item.get("kind") == "stage-gate" and item.get("stage") == SOURCE_STAGE:
        raise SocomError(f"{item_id} is the {SOURCE_STAGE} stage gate; use progress handoff-source-gate")
    if item.get("stage") == ORDER_STAGE and item.get("kind") in ORDER_SKELETON_KINDS:
        raise SocomError(f"{item_id} is a {ORDER_STAGE} skeleton item; use progress handoff-order-skeleton")
    if item.get("stage") == ORDER_STAGE and item.get("kind") in ("stage-gate", *ORDER_ROUTED_KINDS):
        raise SocomError(f"{item_id} closes through the {ORDER_STAGE} compile route, which is not registered yet")
    if item["lease"]["owner"] != owner:
        raise SocomError(f"{item_id} is leased by {item['lease']['owner']}")
    if "ghidra-writer" in item.get("resources", []):
        raise SocomError(
            f"{item_id} owns ghidra-writer; use progress handoff-live-ghidra"
        )
    if not summary.strip():
        raise SocomError("handoff summary must not be empty")
    kept: list[str] = []
    if item.get("kind") in SOURCE_APPLY_KINDS:
        # The apply route's record and evidence lines are part of the handoff.
        if not isinstance(item.get("source_apply"), dict):
            raise SocomError(f"{item_id} has not been applied: run progress apply-source-plan first")
        kept = list(item.get("evidence") or [])
    item["status"] = "awaiting_acceptance"
    item["lease"] = None
    item["handoff"] = {
        "owner": owner,
        "summary": summary.strip(),
        "submitted_at": _iso(_utc_now()),
    }
    item["evidence"] = sorted(set(kept + evidence))


def require_ghidra_lease(
    tracker: dict[str, Any], item_id: str, owner: str
) -> dict[str, Any]:
    item = _work_by_id(tracker).get(item_id)
    if not item or item["status"] != "in_progress" or not item.get("lease"):
        raise SocomError(f"{item_id} is not actively leased")
    if item["lease"]["owner"] != owner:
        raise SocomError(f"{item_id} is leased by {item['lease']['owner']}")
    if "ghidra-writer" not in item.get("resources", []):
        raise SocomError(f"{item_id} does not own ghidra-writer")
    if item["stage"] not in {"debug-metadata-import", "ghidra-reconstruction"}:
        raise SocomError(f"{item_id} is not a live Ghidra reconstruction item")
    return item


def handoff_ghidra_work(
    tracker: dict[str, Any],
    item_id: str,
    owner: str,
    summary: str,
    evidence: list[str],
    *,
    scope: dict[str, list[str]],
    receipt_sha256: str,
    receipt_summary: dict[str, Any],
) -> None:
    item = require_ghidra_lease(tracker, item_id, owner)
    if not summary.strip():
        raise SocomError("handoff summary must not be empty")
    if len(receipt_sha256) != 64:
        raise SocomError("Ghidra receipt SHA-256 is invalid")
    item["status"] = "awaiting_acceptance"
    item["lease"] = None
    item["handoff"] = {
        "owner": owner,
        "summary": summary.strip(),
        "submitted_at": _iso(_utc_now()),
    }
    item["ghidra_receipt"] = {
        "saved": True,
        "scope": scope,
        "receipt_sha256": receipt_sha256,
        "summary": receipt_summary,
    }
    item["evidence"] = sorted(
        set(evidence + [f"ghidra-receipt-sha256:{receipt_sha256}"])
    )


def accept_work(
    tracker: dict[str, Any], item_id: str, accepter: str, evidence: list[str]
) -> None:
    item = _work_by_id(tracker).get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    if item.get("kind") in ("stage-seed", CAPABILITY_GATE_KIND):
        raise SocomError(f"{item_id} is an undecomposed stage seed or a capability gate")
    if item["status"] != "awaiting_acceptance":
        raise SocomError(f"{item_id} is {item['status']}, not awaiting_acceptance")
    if "ghidra-writer" in item.get("resources", []):
        raise SocomError(
            f"{item_id} owns ghidra-writer; use progress advance-live-ghidra"
        )
    if item.get("kind") == "stage-gate" and item.get("stage") == SOURCE_STAGE:
        raise SocomError(f"{item_id} is the {SOURCE_STAGE} stage gate; use progress accept-source-gate")
    if item.get("stage") == ORDER_STAGE and item.get("kind") in ORDER_SKELETON_KINDS:
        raise SocomError(f"{item_id} is a {ORDER_STAGE} skeleton item; use progress accept-order-skeleton")
    if item.get("stage") == ORDER_STAGE and item.get("kind") in ("stage-gate", *ORDER_ROUTED_KINDS):
        raise SocomError(f"{item_id} closes through the {ORDER_STAGE} compile route, which is not registered yet")
    _accept_work_item(item, accepter, evidence)


def _accept_work_item(
    item: dict[str, Any], accepter: str, evidence: list[str]
) -> None:
    handoff_owner = (item.get("handoff") or {}).get("owner")
    if handoff_owner and handoff_owner == accepter:
        raise SocomError(
            f"{item['id']} cannot be self-accepted by handoff owner {accepter}"
        )
    item["status"] = "accepted"
    item["accepted"] = {
        "by": accepter,
        "at": _iso(_utc_now()),
    }
    item["evidence"] = sorted(set(item.get("evidence", []) + evidence))


def accept_ghidra_work(
    tracker: dict[str, Any],
    item_id: str,
    accepter: str,
    evidence: list[str],
    *,
    receipt_sha256: str,
) -> None:
    item = _work_by_id(tracker).get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    if item["status"] != "awaiting_acceptance":
        raise SocomError(f"{item_id} is {item['status']}, not awaiting_acceptance")
    if "ghidra-writer" not in item.get("resources", []):
        raise SocomError(f"{item_id} does not own ghidra-writer")
    live_receipt = item.get("ghidra_receipt") or {}
    expected = live_receipt.get("receipt_sha256")
    if expected != receipt_sha256:
        raise SocomError(
            f"live Ghidra receipt {receipt_sha256} != handed-off receipt {expected}"
        )
    _accept_work_item(
        item,
        accepter,
        evidence + [f"ghidra-receipt-sha256:{receipt_sha256}"],
    )


def reject_work(
    tracker: dict[str, Any],
    item_id: str,
    reviewer: str,
    reason: str,
    evidence: list[str],
) -> None:
    """Return a handed-off item for rework, keeping the rejected handoff."""

    item = _work_by_id(tracker).get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    if item["status"] != "awaiting_acceptance":
        raise SocomError(f"{item_id} is {item['status']}, not awaiting_acceptance")
    handoff = item.get("handoff") or {}
    if not reviewer.strip():
        raise SocomError("reviewer must not be empty")
    if handoff.get("owner") == reviewer:
        raise SocomError(f"{item_id} cannot be rejected by handoff owner {reviewer}")
    if not reason.strip():
        raise SocomError("rejection reason must not be empty")
    record = {
        "handoff": handoff,
        "handoff_evidence": item.get("evidence", []),
        "rejected_by": reviewer.strip(),
        "rejected_at": _iso(_utc_now()),
        "reason": reason.strip(),
        "evidence": sorted(set(evidence)),
    }
    if "ghidra_receipt" in item:
        record["ghidra_receipt"] = item.pop("ghidra_receipt")
    if "source_gate" in item:
        record["source_gate"] = item.pop("source_gate")
    kept: list[str] = []
    if isinstance(item.get("source_apply"), dict):
        # The applied files stay on disk: the record stays with the item so a
        # rework reapplies the same plan idempotently; history keeps a copy.
        record["source_apply"] = copy.deepcopy(item["source_apply"])
        kept = [text for text in item.get("evidence", []) if str(text).startswith("source-")]
    if isinstance(item.get("order_skeleton"), dict):
        # A rejected skeleton item keeps its written files and record; the rework re-applies and replaces it.
        from .order_skeleton_route import RECORD_CITATION

        record["order_skeleton"] = copy.deepcopy(item["order_skeleton"])
        kept = [text for text in item.get("evidence", []) if str(text).startswith("order-skeleton-")
                and not str(text).startswith(RECORD_CITATION)]
    item.setdefault("review_history", []).append(record)
    item["status"] = "ready"
    item["handoff"] = None
    item["evidence"] = kept


def reopen_work(
    tracker: dict[str, Any],
    item_id: str,
    reviewer: str,
    reason: str,
    evidence: list[str],
) -> None:
    """Return an accepted reconstruction or stage 5 order plan for re-planning before it applies.

    Only a recon-plan-group, order-plan-segment or order-plan-link whose
    apply item (the link plan has none) has not started (ready or blocked)
    can be reopened; what is already in Ghidra is corrected through a
    governed repair instead.  The acceptance and handoff are kept in the
    review history, the plan becomes ready and its apply blocked again.
    """

    by_id = _work_by_id(tracker)
    item = by_id.get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    if item.get("kind") in ORDER_SKELETON_KINDS:
        _reopen_skeleton(tracker, item, reviewer, reason, evidence)
        return
    if item.get("kind") not in ("recon-plan-group", *ORDER_PLAN_KINDS):
        raise SocomError(f"{item_id} is not a reconstruction, order plan or skeleton item")
    if item["status"] != "accepted":
        raise SocomError(f"{item_id} is {item['status']}, not accepted")
    apply = by_id.get(f"{item_id}-apply")
    if item.get("kind") == ORDER_LINK_KIND:
        pass  # the link plan has no apply of its own
    elif apply is None or apply.get("status") not in ("ready", "blocked"):
        raise SocomError(
            f"{item_id}-apply is {apply.get('status') if apply else 'missing'}: an apply that started "
            "or finished is corrected through a governed repair (progress add-recon-repair once it is "
            "accepted), not by reopening its plan"
        )
    handoff = item.get("handoff") or {}
    if not reviewer.strip():
        raise SocomError("reviewer must not be empty")
    if handoff.get("owner") == reviewer:
        raise SocomError(f"{item_id} cannot be reopened by its handoff owner {reviewer}")
    if not reason.strip():
        raise SocomError("reopen reason must not be empty")
    item.setdefault("review_history", []).append(
        {
            "handoff": handoff,
            "handoff_evidence": item.get("evidence", []),
            "accepted": item.get("accepted"),
            "reopened_by": reviewer.strip(),
            "reopened_at": _iso(_utc_now()),
            "reason": reason.strip(),
            "evidence": sorted(set(evidence)),
        }
    )
    item["status"] = "ready"
    item["handoff"] = None
    item.pop("accepted", None)
    item["evidence"] = []
    if apply is not None:
        apply["status"] = "blocked"


def _reopen_skeleton(tracker: dict[str, Any], item: dict[str, Any], reviewer: str, reason: str, evidence: list[str]) -> None:
    """Return an accepted stage 5 skeleton item (the prepare or a segment apply) for re-apply.

    Its files stay written and its record stays with it, so the re-apply
    starts from them and replaces the record (the review history keeps a
    copy of it and of the acceptance).  A segment apply reopens while its
    compile item has not started; the prepare while no segment apply is in
    progress or awaiting acceptance (ready applies wait for it again; accepted
    ones keep their acceptance, since the prepare's files are not theirs).
    """

    from .order_skeleton_route import RECORD_CITATION

    by_id = _work_by_id(tracker)
    item_id = item["id"]
    if item["status"] != "accepted":
        raise SocomError(f"{item_id} is {item['status']}, not accepted")
    if item.get("kind") == ORDER_APPLY_KIND:
        compile_item = by_id.get(item_id.removesuffix("-apply") + "-compile") or {}
        if compile_item.get("status") not in _UNSTARTED_STATUSES:
            raise SocomError(f"{compile_item.get('id')} has started: its skeleton is not reopened under it")
        dependents: list[dict[str, Any]] = []
    else:
        applies = [row for row in tracker["work_items"] if row.get("kind") == ORDER_APPLY_KIND]
        if busy := [row["id"] for row in applies if row["status"] in ("in_progress", "awaiting_acceptance")]:
            raise SocomError(f"segment applies are in progress or under review ({', '.join(busy[:6])}): reopen the prepare after them")
        dependents = [row for row in applies if row["status"] == "ready"]
    handoff = item.get("handoff") or {}
    if not reviewer.strip():
        raise SocomError("reviewer must not be empty")
    if handoff.get("owner") == reviewer:
        raise SocomError(f"{item_id} cannot be reopened by its handoff owner {reviewer}")
    if not reason.strip():
        raise SocomError("reopen reason must not be empty")
    item.setdefault("review_history", []).append(
        {
            "handoff": handoff,
            "handoff_evidence": item.get("evidence", []),
            "accepted": item.get("accepted"),
            "order_skeleton": copy.deepcopy(item.get("order_skeleton")),
            "reopened_by": reviewer.strip(),
            "reopened_at": _iso(_utc_now()),
            "reason": reason.strip(),
            "evidence": sorted(set(evidence)),
        }
    )
    item["status"] = "ready"
    item["handoff"] = None
    item.pop("accepted", None)
    # The record's lines stay with the record; the handoff's citation of it does not.
    item["evidence"] = [
        text for text in item.get("evidence") or []
        if str(text).startswith("order-skeleton-") and not str(text).startswith(RECORD_CITATION)
    ]
    for row in dependents:
        row["status"] = "blocked"


SOURCE_REOPEN_KINDS = (SEGMENT_PLAN_KIND, PROVIDER_PLAN_KIND)
_UNSTARTED_STATUSES = ("blocked", "ready")


def _source_apply_started(apply: dict[str, Any]) -> str | None:
    """Why a source apply item has started, or ``None`` when it never has."""

    if apply.get("status") not in _UNSTARTED_STATUSES:
        return f"is {apply.get('status')}"
    if apply.get("lease"):
        return "is leased"
    for key, label in (
        ("source_apply", "has an apply record"),
        ("handoff", "has a handoff"),
        ("accepted", "has an acceptance"),
        ("review_history", "has review history"),
    ):
        if apply.get(key):
            return label
    if (apply.get("batch") or {}).get("reservation_correction") is not None:
        return "has a recorded reservation correction"
    return None


def reopen_source_plan(
    tracker: dict[str, Any],
    item_id: str,
    by: str,
    reason: str,
    evidence: list[str],
) -> dict[str, Any]:
    """Send an accepted stage 4 owner plan back for revision (``progress reopen-source-plan``).

    Only a segment or provider plan item in ``accepted`` is reopened, and only
    while its apply item has never started (``blocked`` or ``ready`` with no
    lease, apply record, handoff, acceptance, review history or reservation
    correction) and no other item that waits for the plan (the data
    reconciles wait for every plan) has been claimed, handed off or
    accepted.  The item keeps its ID, batch and evidence and returns to
    ``ready``; its handoff and acceptance move to a ``review_history`` entry
    with the reopener, reason and evidence.  The apply and any ready
    dependent return to ``blocked``.  The plan file is not touched: the
    planner revises it and hands off again, and the accepter must still
    differ from that handoff's owner.
    """

    by_id = _work_by_id(tracker)
    item = by_id.get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    if item.get("stage") != SOURCE_STAGE or item.get("kind") not in SOURCE_REOPEN_KINDS:
        raise SocomError(
            f"{item_id} is a {item.get('kind')} item, not a {SOURCE_STAGE} segment or provider plan "
            f"({', '.join(SOURCE_REOPEN_KINDS)})"
        )
    if item.get("lease"):
        raise SocomError(f"{item_id} is leased by {item['lease'].get('owner')}")
    if item["status"] != "accepted":
        raise SocomError(f"{item_id} is {item['status']}, not accepted")
    reopener = by.strip()
    stated = reason.strip()
    lines = sorted({str(text).strip() for text in evidence if str(text).strip()})
    if not reopener:
        raise SocomError("--by must not be empty")
    if not stated:
        raise SocomError("reopen reason must not be empty")
    if not lines:
        raise SocomError("reopening an accepted plan needs at least one --evidence line")
    handoff = item.get("handoff") or {}
    if handoff.get("owner") == reopener:
        raise SocomError(f"{item_id} cannot be reopened by its handoff owner {reopener}")
    apply_id = f"{item_id}-apply"
    apply = by_id.get(apply_id)
    if apply is None:
        raise SocomError(f"{item_id} has no apply item {apply_id}")
    if why := _source_apply_started(apply):
        raise SocomError(f"{apply_id} {why}: a plan whose source apply has started cannot be reopened")
    dependents = [
        row for row in tracker["work_items"] if item_id in row.get("dependencies", []) and row["id"] != apply_id
    ]
    started = sorted(
        f"{row['id']} ({row['status']})"
        for row in dependents
        if row["status"] not in _UNSTARTED_STATUSES or row.get("lease")
    )
    if started:
        raise SocomError(
            f"items that wait for {item_id} have started: {', '.join(started)}; "
            "a plan is reopened only before the items built on its acceptance start"
        )
    item.setdefault("review_history", []).append(
        {
            "handoff": handoff,
            "handoff_evidence": list(item.get("evidence", [])),
            "accepted": item.get("accepted"),
            "reopened_by": reopener,
            "reopened_at": _iso(_utc_now()),
            "reason": stated,
            "evidence": lines,
        }
    )
    item["status"] = "ready"
    item["handoff"] = None
    item.pop("accepted", None)
    blocked = []
    for row in (apply, *dependents):
        if row["status"] == "ready":
            row["status"] = "blocked"
            blocked.append(row["id"])
    return {"work_item_id": item_id, "apply_item": apply_id, "blocked": sorted(blocked)}


def rebaseline_ghidra_target(
    tracker: dict[str, Any],
    recorder: str,
    evidence: list[str],
    *,
    ghidra_version: str,
    receipt_sha256: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Record a fresh-import baseline receipt after a Ghidra version re-pin.

    Only the untouched bootstrap import may be rebaselined, and function/type
    index digests must survive the version change.  Other differences are
    recorded explicitly in the appended history entry.
    """

    targets = [
        row
        for row in tracker.get("verification_targets", [])
        if row.get("id") == "socom:verification:ghidra-program"
    ]
    if len(targets) != 1:
        raise SocomError("tracker must contain exactly one Ghidra verification target")
    target = targets[0]
    if target.get("status") != "bootstrap-r5900":
        raise SocomError(
            "Ghidra rebaseline is limited to the bootstrap import; "
            f"target status is {target.get('status')!r}"
        )
    live_work = [
        row["id"]
        for row in tracker["work_items"]
        if "ghidra-writer" in row.get("resources", [])
        and (
            row.get("lease")
            or row["status"] in {"in_progress", "awaiting_acceptance", "accepted"}
        )
    ]
    if live_work:
        raise SocomError(
            f"Ghidra rebaseline requires no leased or accepted writer work: {live_work!r}"
        )
    previous_version = target.get("ghidra_version")
    if previous_version == ghidra_version:
        raise SocomError(f"Ghidra target is already pinned to {ghidra_version}")
    history = target.get("receipt_history")
    if not isinstance(history, list) or not history:
        raise SocomError("Ghidra rebaseline requires a recorded baseline receipt")
    if not recorder.strip():
        raise SocomError("rebaseline recorder must not be empty")
    if not evidence:
        raise SocomError("Ghidra rebaseline requires evidence")
    if len(receipt_sha256) != 64:
        raise SocomError("Ghidra receipt SHA-256 is invalid")

    previous = history[-1]
    comparison = {}
    for name in ("functions", "types", "data"):
        before = previous.get("indexes", {}).get(name, {})
        after = receipt["indexes"][name]
        comparison[name] = {
            "count_equal": before.get("count") == after["count"],
            "sha256_equal": before.get("sha256") == after["sha256"],
        }
    changed = [
        name for name in ("functions", "types") if not comparison[name]["sha256_equal"]
    ]
    if changed:
        raise SocomError(
            "Ghidra rebaseline changes semantic index digests "
            f"{changed!r}; review the new import before re-pinning"
        )
    previous_counts = previous.get("counts", {})
    count_deltas = {
        key: {"before": previous_counts.get(key), "after": value}
        for key, value in sorted(receipt["counts"].items())
        if previous_counts.get(key) != value
    }
    entry = {
        "tracker_revision": tracker["revision"] + 1,
        "work_item_id": None,
        "kind": "ghidra-version-rebaseline",
        "ghidra_version": ghidra_version,
        "previous_ghidra_version": previous_version,
        "previous_receipt_sha256": previous.get("receipt_sha256"),
        "receipt_sha256": receipt_sha256,
        "counts": receipt["counts"],
        "indexes": receipt["indexes"],
        "index_comparison": comparison,
        "count_deltas": count_deltas,
        "recorded_by": recorder.strip(),
        "recorded_at": _iso(_utc_now()),
        "evidence": sorted(set(evidence)),
    }
    target["ghidra_version"] = ghidra_version
    target["baseline_receipt_sha256"] = receipt_sha256
    target["current_receipt_sha256"] = receipt_sha256
    history.append(entry)
    return entry


def stage_live_scope(tracker: dict[str, Any], stage: str) -> dict[str, list[str]]:
    """Return the union of the stored receipt scopes of a stage's live items."""

    live = [
        item
        for item in tracker["work_items"]
        if item["stage"] == stage and "ghidra-writer" in item.get("resources", [])
    ]
    if not live:
        raise SocomError(f"stage {stage} has no Ghidra writer items")
    union: dict[str, list[str]] = {"functions": [], "types": [], "globals": []}
    for item in live:
        scope = (item.get("ghidra_receipt") or {}).get("scope")
        if item["status"] != "accepted" or not isinstance(scope, dict):
            raise SocomError(f"{item['id']} has no accepted Ghidra receipt scope")
        for key in union:
            union[key].extend(scope.get(key, []))
    return normalize_receipt_scope({"schema_version": 1, **union})


def scope_sha256(scope: dict[str, list[str]]) -> str:
    return hashlib.sha256(
        canonical_json({"schema_version": 1, **scope}).encode("utf-8")
    ).hexdigest()


def record_stage_baseline(
    tracker: dict[str, Any],
    stage: str,
    recorder: str,
    evidence: list[str],
    *,
    receipt_sha256: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    """Record the live semantic receipt over an accepted stage's union scope.

    The receipt must have been computed over ``stage_live_scope`` while no
    Ghidra writer was leased or awaiting acceptance.  A stage records one
    baseline; later stages build on it.
    """

    row = next((row for row in tracker["stages"] if row["name"] == stage), None)
    if row is None:
        raise SocomError(f"unknown stage: {stage}")
    if stage == SOURCE_STAGE:
        raise SocomError(
            f"{SOURCE_STAGE} is file-only: progress accept-source-gate records its baseline when it accepts the gate"
        )
    stage_items = [item for item in tracker["work_items"] if item["stage"] == stage]
    if not stage_items or any(item["status"] != "accepted" for item in stage_items):
        raise SocomError(f"stage {stage} has work that is not accepted")
    if row.get("baseline"):
        raise SocomError(f"stage {stage} already records a baseline")
    pending = [
        item["id"]
        for item in tracker["work_items"]
        if "ghidra-writer" in item.get("resources", [])
        and item["status"] in {"in_progress", "awaiting_acceptance"}
    ]
    if pending:
        raise SocomError(f"stage baseline requires no active Ghidra writer: {pending!r}")
    recorder = recorder.strip()
    if not recorder:
        raise SocomError("baseline recorder must not be empty")
    owners = {
        (item.get("handoff") or {}).get("owner") for item in stage_items
    } - {None}
    if recorder in owners:
        raise SocomError(f"baseline recorder {recorder} handed off work in {stage}")
    if not evidence:
        raise SocomError("stage baseline requires evidence")
    if len(receipt_sha256) != 64:
        raise SocomError("Ghidra receipt SHA-256 is invalid")
    scope = stage_live_scope(tracker, stage)
    target = next(
        (
            row
            for row in tracker.get("verification_targets", [])
            if row.get("id") == "socom:verification:ghidra-program"
        ),
        {},
    )
    baseline = {
        "kind": "ghidra-semantic-receipt",
        "tracker_revision": tracker["revision"] + 1,
        "receipt_sha256": receipt_sha256,
        "scope_sha256": scope_sha256(scope),
        "scope_counts": {key: len(value) for key, value in scope.items()},
        "live_item_count": sum(
            "ghidra-writer" in item.get("resources", []) for item in stage_items
        ),
        "target_receipt_sha256": target.get("current_receipt_sha256"),
        "counts": receipt["counts"],
        "indexes": receipt["indexes"],
        "recorded_by": recorder,
        "recorded_at": _iso(_utc_now()),
        "evidence": sorted(set(evidence)),
    }
    row["baseline"] = baseline
    row.setdefault("accepted_evidence", []).append(
        f"ghidra-receipt-sha256:{receipt_sha256}"
    )
    return baseline


def decompose_reconstruction(tracker: dict[str, Any], groups: dict[str, Any]) -> dict[str, Any]:
    """Replace the stage 3 seed with callee-first group items and a stage gate.

    ``groups`` is ``recon.recon_groups`` output.  Each group gets a file-only
    plan item, which waits for the apply items of the groups holding its
    callees, and a live apply item, which waits for its plan.  The seed keeps
    its ID (later stages depend on it) and becomes the stage gate: ordinary
    reviewed work that waits for every apply item.
    """

    previous = next(row for row in tracker["stages"] if row["name"] == "debug-metadata-import")
    if previous.get("status") != "accepted" or not previous.get("baseline"):
        raise SocomError("decomposition needs debug-metadata-import accepted with a recorded baseline")
    stage = next(row for row in tracker["stages"] if row["name"] == RECON_STAGE)
    if stage.get("decomposition"):
        raise SocomError(f"{RECON_STAGE} is already decomposed")
    items = tracker["work_items"]
    seed_position = next(
        (position for position, row in enumerate(items) if row["id"] == RECON_SEED_ID), None
    )
    if seed_position is None or items[seed_position].get("kind") != "stage-seed":
        raise SocomError(f"{RECON_SEED_ID} is not an undecomposed stage seed")
    if any(row["stage"] == RECON_STAGE and row["id"] != RECON_SEED_ID for row in items):
        raise SocomError(f"{RECON_STAGE} already has work items")
    if not groups.get("groups"):
        raise SocomError("decomposition needs at least one group")

    created = []
    apply_ids = []
    for group in groups["groups"]:
        batch = {
            "batch_number": group["group_number"],
            "group_number": group["group_number"],
            "height": group["height"],
            "function_count": len(group["functions"]),
            "functions": list(group["functions"]),
            "recursive_components": [list(row) for row in group["recursive_components"]],
            "graph_sha256": groups["graph_sha256"],
        }
        apply_id = f"{group['id']}-apply"
        apply_ids.append(apply_id)
        created.append(
            {
                "id": group["id"],
                "stage": RECON_STAGE,
                "kind": "recon-plan-group",
                "title": (
                    f"Plan reconstruction group {group['group_number']:03d} "
                    f"(height {group['height']}, {len(group['functions'])} functions)"
                ),
                "status": "blocked",
                "dependencies": [f"{callee}-apply" for callee in group["callee_groups"]],
                "resources": list(RECON_PLAN_RESOURCES),
                "selection": "functions",
                "batch": batch,
                "lease": None,
                "handoff": None,
                "evidence": [],
            }
        )
        created.append(
            {
                "id": apply_id,
                "stage": RECON_STAGE,
                "kind": "recon-apply-group",
                "title": f"Apply reviewed reconstruction group {group['group_number']:03d} in Ghidra",
                "status": "blocked",
                "dependencies": [group["id"]],
                "resources": list(GHIDRA_WRITER_RESOURCES),
                "selection": "functions",
                "batch": copy.deepcopy(batch),
                "lease": None,
                "handoff": None,
                "evidence": [],
            }
        )
    seed = items[seed_position]
    seed["kind"] = "stage-gate"
    seed["title"] = f"Review and close {RECON_STAGE}"
    seed["dependencies"] = apply_ids
    items[seed_position:seed_position] = created
    decomposition = {
        "producer": "recon-function-graph",
        "graph_sha256": groups["graph_sha256"],
        "group_size": groups["group_size"],
        "group_count": len(groups["groups"]),
        "function_count": groups["function_count"],
        "tracker_revision": tracker["revision"] + 1,
    }
    stage["decomposition"] = decomposition
    return decomposition


def _source_item(item_id: str, kind: str, title: str, dependencies: list[str], resources: list[str], batch: Any) -> dict[str, Any]:
    return {
        "id": item_id,
        "stage": SOURCE_STAGE,
        "kind": kind,
        "title": title,
        "status": "blocked",
        "dependencies": dependencies,
        "resources": resources,
        "selection": "artifacts" if batch else None,
        "batch": batch,
        "lease": None,
        "handoff": None,
        "evidence": [],
    }


def decompose_source_correlation(
    tracker: dict[str, Any], graph: dict[str, Any], reservations: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Replace the stage 4 seed with owner-plan items, their applies and a gate.

    ``graph`` is ``source graph`` output and ``reservations`` the ``src/``
    reservation of each authored-segment apply, by scope key
    (``source_plan.apply_reservations``): its directories, whether they are
    inferred, and the reason for an inference or the all-of-``src`` fallback.
    Every authored segment gets a file-only ``source-plan-segment`` item and
    every provider library a ``source-plan-provider`` item, both waiting for
    the accepted stage 3 gate; every data kind outside the segment slices
    gets a ``source-data-reconcile`` item that waits for every plan.  Each
    plan has an apply item that waits for its plan, every reconcile, and the
    ``capability-gate`` item of the guarded apply route, which stays blocked
    until ``progress open-capability-gate`` accepts it (``open_capability_gate``)
    once that route is registered.  A segment apply reserves its ``src/``
    directories.  A provider apply reserves nothing: it writes no file and
    records its archive members' ownership in tracker evidence only.  The
    seed keeps its ID (later stages depend on it) and becomes the stage gate
    over every apply and reconcile.  No item owns a Ghidra resource: the
    stage is file-only.
    """

    previous = next(row for row in tracker["stages"] if row["name"] == RECON_STAGE)
    if previous.get("status") != "accepted" or not previous.get("baseline"):
        raise SocomError(f"decomposition needs {RECON_STAGE} accepted with a recorded baseline")
    stage = next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)
    if stage.get("decomposition"):
        raise SocomError(f"{SOURCE_STAGE} is already decomposed")
    items = tracker["work_items"]
    seed_position = next(
        (position for position, row in enumerate(items) if row["id"] == SOURCE_SEED_ID), None
    )
    if seed_position is None or items[seed_position].get("kind") != "stage-seed":
        raise SocomError(f"{SOURCE_SEED_ID} is not an undecomposed stage seed")
    if any(row["stage"] == SOURCE_STAGE and row["id"] != SOURCE_SEED_ID for row in items):
        raise SocomError(f"{SOURCE_STAGE} already has work items")
    if problems := verify_graph(graph):
        raise SocomError("decomposition needs a valid source graph: " + "; ".join(problems))
    batches = scope_batches(graph)
    if not any(batch["scope"]["kind"] != "data" for batch in batches):
        raise SocomError("decomposition needs at least one segment")

    plans: list[dict[str, Any]] = []
    applies: list[dict[str, Any]] = []
    reconciles: list[dict[str, Any]] = []
    inferred: list[dict[str, Any]] = []
    fallback: list[dict[str, Any]] = []
    for batch in batches:
        scope = batch["scope"]
        item_id = scope_item_id(scope)
        kind = PLAN_KIND_BY_SCOPE[scope["kind"]]
        if scope["kind"] == "data":
            title = (
                f"Reconcile {scope['data_kind']} data owners "
                f"({batch['artifact_count']} artifacts outside the segment slices)"
            )
            reconciles.append(_source_item(item_id, kind, title, [], list(SOURCE_PLAN_RESOURCES), batch))
            continue
        if scope["kind"] == "segment":
            number = scope["segment_number"]
            start, end = batch["ranges"][0]
            title = f"Plan source owners of segment {number:03d} ({start}-{end}, {batch['function_count']} functions)"
            apply_title = f"Apply the reviewed source owners of segment {number:03d} under src/"
        else:
            title = (
                f"Plan provider owners of {scope['library']} "
                f"({len(batch['segment_numbers'])} segments, {batch['function_count']} functions)"
                if batch["segment_numbers"]
                else f"Plan provider owners of {scope['library']} ({batch['artifact_count']} artifacts in other segments)"
            )
            apply_title = f"Record the reviewed provider owners of {scope['library']} in tracker evidence"
        apply_batch = copy.deepcopy(batch)
        reserved: list[str] = []
        if scope["kind"] == "segment":
            reservation = reservations.get(scope_key(scope)) or {}
            reserved = list(reservation.get("directories") or [])
            if not reserved:
                raise SocomError(f"{item_id} has no src/ directory to reserve")
            reason = reservation.get("reason")
            apply_batch.update(
                directories=list(reserved),
                resource_inferred=reservation.get("inferred") is True,
                resource_reason=reason,
            )
            if reservation.get("basis"):
                apply_batch["resource_basis"] = reservation["basis"]
            if apply_batch["resource_inferred"]:
                inferred.append({"item": f"{item_id}-apply", "directories": list(reserved), "reason": reason})
            elif reserved == ["src"]:
                fallback.append({"item": f"{item_id}-apply", "reason": reason})
        plans.append(_source_item(item_id, kind, title, [RECON_SEED_ID], list(SOURCE_PLAN_RESOURCES), batch))
        applies.append(_source_item(f"{item_id}-apply", APPLY_KIND_BY_PLAN[kind], apply_title, [], reserved, apply_batch))
    plan_ids = [row["id"] for row in plans]
    reconcile_ids = [row["id"] for row in reconciles]
    for row in reconciles:
        row["dependencies"] = list(plan_ids)
    for row in applies:
        row["dependencies"] = [row["id"].removesuffix("-apply"), *reconcile_ids, SOURCE_APPLY_ROUTE_ID]
    route = _source_item(
        SOURCE_APPLY_ROUTE_ID,
        CAPABILITY_GATE_KIND,
        "Register the guarded source apply route (owner-plan annotations under src/, provider evidence)",
        [],
        [],
        None,
    )
    route["batch"] = {
        "capability": SOURCE_STAGE,
        "requires": (
            "a registered command that applies an accepted owner plan: a segment's files and annotations under "
            "its reserved src/ directories, a provider's archive-member ownership in tracker evidence only"
        ),
    }
    created: list[dict[str, Any]] = []
    for plan, apply in zip(plans, applies):
        created.extend((plan, apply))
    created.extend(reconciles)
    created.append(route)
    seed = items[seed_position]
    seed["kind"] = "stage-gate"
    seed["title"] = f"Review and close {SOURCE_STAGE}"
    seed["dependencies"] = [row["id"] for row in applies] + reconcile_ids
    items[seed_position:seed_position] = created
    libraries = [batch["scope"]["library"] for batch in batches if batch["scope"]["kind"] == "provider"]
    decomposition = {
        "producer": "source-graph",
        "graph_sha256": graph["graph_sha256"],
        "segment_size": graph["segment_size"],
        "segment_count": len(graph["segments"]),
        "artifact_count": len(graph["artifacts"]),
        "authored_segment_count": sum(1 for batch in batches if batch["scope"]["kind"] == "segment"),
        "provider_libraries": libraries,
        "data_kinds": [batch["scope"]["data_kind"] for batch in batches if batch["scope"]["kind"] == "data"],
        "apply_route": SOURCE_APPLY_ROUTE_ID,
        "inferred_reservations": inferred,
        "fallback_reservations": fallback,
        "tracker_revision": tracker["revision"] + 1,
    }
    stage["decomposition"] = decomposition
    return decomposition


def open_capability_gate(tracker: dict[str, Any], item_id: str, registered: set[str]) -> dict[str, Any]:
    """Accept a ``capability-gate`` item once the capability it waits for is active and registered.

    No worker claims, hands off or accepts a gate.  It opens when the
    capability registry (``capabilities.py``) has an active row that lists
    the gate under ``opens`` and every command of that row is registered;
    the acceptance records the capability and its digest as evidence.
    Returns the capability row.
    """

    item = _work_by_id(tracker).get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    if item.get("kind") != CAPABILITY_GATE_KIND:
        raise SocomError(f"{item_id} is not a capability gate")
    if item["status"] != "blocked":
        raise SocomError(f"{item_id} is {item['status']}, not a blocked capability gate")
    capability = capability_opening(item_id)
    if capability is None:
        raise SocomError(f"no registered capability opens {item_id}")
    if capability.get("status") != "active":
        raise SocomError(f"capability {capability['id']} is {capability.get('status')}, not active")
    wanted = (item.get("batch") or {}).get("capability")
    if wanted and capability.get("stage") != wanted:
        raise SocomError(f"{item_id} waits for a {wanted} capability, {capability['id']} serves {capability.get('stage')}")
    commands = list(capability.get("commands") or [])
    if not commands:
        raise SocomError(f"capability {capability['id']} registers no command")
    missing = sorted(set(commands) - registered)
    if missing:
        raise SocomError(f"capability {capability['id']} commands are not registered: {missing}")
    digest = hashlib.sha256(canonical_json(capability).encode("utf-8")).hexdigest()
    item["status"] = "accepted"
    item["accepted"] = {"by": CAPABILITY_GATE_ACCEPTER, "at": _iso(_utc_now()), "capability": capability["id"]}
    item["evidence"] = sorted(
        set(item.get("evidence") or [])
        | {f"capability:{capability['id']}", f"capability-sha256:{digest}"}
        | {f"registered-command:{command}" for command in commands}
    )
    return dict(capability)


def release_work(tracker: dict[str, Any], item_id: str, owner: str) -> None:
    item = _work_by_id(tracker).get(item_id)
    if not item or item["status"] != "in_progress" or not item.get("lease"):
        raise SocomError(f"{item_id} does not have an active lease")
    if item["lease"]["owner"] != owner:
        raise SocomError(f"{item_id} is leased by {item['lease']['owner']}")
    item["status"] = "ready"
    item["lease"] = None


def _migrate_2_to_3(updated: dict[str, Any]) -> None:
    """Split debug import items into file-only plans and Ghidra applies."""

    old_items = updated["work_items"]
    new_items: list[dict[str, Any]] = []
    foundation_id = "socom:work:debug-type-foundation"
    foundation_apply_id = f"{foundation_id}-apply"
    apply_ids: list[str] = []
    for item in old_items:
        kind = item.get("kind")
        if kind not in {"debug-import-foundation", "debug-import-batch"}:
            continue
        is_foundation = kind == "debug-import-foundation"
        plan = copy.deepcopy(item)
        plan["kind"] = (
            "debug-import-plan-foundation" if is_foundation else "debug-import-plan-batch"
        )
        plan["title"] = (
            "Plan and reconcile the global DWARF type graph"
            if is_foundation
            else str(plan["title"]).replace("Import DWARF", "Plan DWARF")
        )
        plan["dependencies"] = [] if is_foundation else [foundation_apply_id]
        plan["resources"] = ["build/import-plans"]
        plan["status"] = "ready" if is_foundation else "blocked"
        new_items.append(plan)

        apply_id = foundation_apply_id if is_foundation else f"{item['id']}-apply"
        apply_ids.append(apply_id)
        apply = copy.deepcopy(item)
        apply["id"] = apply_id
        apply["kind"] = (
            "debug-import-apply-foundation" if is_foundation else "debug-import-apply-batch"
        )
        apply["title"] = (
            "Apply the reviewed global DWARF type plan in Ghidra"
            if is_foundation
            else str(item["title"]).replace("Import DWARF", "Apply reviewed DWARF")
        )
        apply["status"] = "blocked"
        apply["dependencies"] = [item["id"]]
        apply["resources"] = ["ghidra:soCOM/socom.elf", "ghidra-writer"]
        apply["lease"] = None
        apply["handoff"] = None
        apply.pop("accepted", None)
        apply.pop("ghidra_receipt", None)
        new_items.append(apply)

    for item in old_items:
        if item.get("kind") in {"debug-import-foundation", "debug-import-batch"}:
            continue
        migrated = copy.deepcopy(item)
        if migrated.get("id") == "socom:work:ghidra-reconstruction-seed":
            migrated["dependencies"] = list(apply_ids)
        migrated["status"] = "blocked" if migrated.get("kind") == "stage-seed" else migrated["status"]
        new_items.append(migrated)
    updated["work_items"] = new_items
    if not any(
        row.get("id") == "socom:blocker:deferred-stage-producers"
        for row in updated.get("blockers", [])
    ):
        updated.setdefault("blockers", []).append(
            {
                "id": "socom:blocker:deferred-stage-producers",
                "kind": "missing-stage-producer",
                "status": "open",
                "summary": (
                    "Later build stages remain closed until a real native producer "
                    "and stage-specific acceptance route are registered."
                ),
                "blocks": [
                    "authored-function-order",
                    "authored-call-contract",
                    "authored-byte-match",
                    "full-function-order",
                    "linked-byte-match",
                    "final-validation",
                ],
                "evidence": ["docs/reconstruction/TOOL_COVERAGE.md"],
            }
        )
    updated["schema_version"] = 3


def _migrate_3_to_4(updated: dict[str, Any]) -> None:
    """Add the zero-fill memory-map item that every batch apply waits for."""

    items = updated["work_items"]
    foundation_apply_id = "socom:work:debug-type-foundation-apply"
    if not any(row.get("id") == ZERO_FILL_MEMORY_ID for row in items):
        index = next(
            position for position, row in enumerate(items) if row.get("id") == foundation_apply_id
        )
        items.insert(index + 1, _zero_fill_memory_item(foundation_apply_id))
    for row in items:
        if row.get("kind") != "debug-import-apply-batch":
            continue
        if row["status"] in {"in_progress", "awaiting_acceptance", "accepted"}:
            # Applied globals would have used memory this schema adds.
            raise SocomError(f"{row['id']} started before the zero-fill memory item existed")
        if ZERO_FILL_MEMORY_ID not in row["dependencies"]:
            row["dependencies"] = [*row["dependencies"], ZERO_FILL_MEMORY_ID]
        # Readiness refresh only promotes; a new unmet dependency re-blocks.
        if row["status"] == "ready":
            row["status"] = "blocked"
    updated["schema_version"] = 4


def _migrate_4_to_5(updated: dict[str, Any]) -> None:
    """Add the repair of the signatures batch 001 changed through thunks."""

    from .repairs import BATCH_001_APPLY_ID, THUNK_REPAIR_ID

    items = updated["work_items"]
    index = next(
        (position for position, row in enumerate(items) if row.get("id") == BATCH_001_APPLY_ID),
        None,
    )
    # Only a tracker whose batch 001 apply was accepted (before the thunk
    # guard) holds the defect; any other tracker has nothing to repair.
    if (
        index is not None
        and items[index].get("status") == "accepted"
        and not any(row.get("id") == THUNK_REPAIR_ID for row in items)
    ):
        items.insert(index + 1, _repair_item(THUNK_REPAIR_ID))
    updated["schema_version"] = 5


def _migrate_5_to_6(updated: dict[str, Any]) -> None:
    """Drop the tracker's copies of the census symbols and relocations.

    They are immutable reference evidence (91% of the schema 5 file); no
    tracker operation ever changed them, and the reference census keeps them.
    """

    updated.pop("symbols", None)
    updated.pop("relocations", None)
    updated["schema_version"] = 6


def migrate_tracker(path: Path, expected_revision: int) -> dict[str, Any]:
    """Migrate the tracker to the current schema under its normal lock."""

    with exclusive_state_lock(path):
        current = load_tracker(path)
        require_revision(current, expected_revision)
        if current.get("schema_version") == SCHEMA_VERSION:
            return current
        if current.get("schema_version") not in (2, 3, 4, 5):
            raise SocomError(
                f"no migration path from schema {current.get('schema_version')}"
            )
        active = [
            row["id"]
            for row in current.get("work_items", [])
            if row.get("lease")
            or row.get("status") in {"in_progress", "awaiting_acceptance"}
        ]
        if active:
            raise SocomError(
                "tracker migration requires no leases or pending handoffs: "
                + repr(active)
            )
        updated = copy.deepcopy(current)
        updated["revision"] += 1
        steps = []
        if updated["schema_version"] == 2:
            _migrate_2_to_3(updated)
            steps.append((2, 3))
        if updated["schema_version"] == 3:
            _migrate_3_to_4(updated)
            steps.append((3, 4))
        if updated["schema_version"] == 4:
            _migrate_4_to_5(updated)
            steps.append((4, 5))
        if updated["schema_version"] == 5:
            _migrate_5_to_6(updated)
            steps.append((5, 6))
        for from_schema, to_schema in steps:
            updated.setdefault("migration_history", []).append(
                {
                    "from_schema": from_schema,
                    "to_schema": to_schema,
                    "tracker_revision": updated["revision"],
                    "at": _iso(_utc_now()),
                }
            )
        _refresh_ready_and_stages(updated)
        if errors := audit_tracker(updated):
            raise SocomError("tracker migration rejected:\n- " + "\n- ".join(errors))
        atomic_write_json(path, updated)
        return updated


def work_packet(
    tracker: dict[str, Any], item_id: str, owner: str
) -> dict[str, Any]:
    item = _work_by_id(tracker).get(item_id)
    if not item:
        raise SocomError(f"unknown work item: {item_id}")
    lease = item.get("lease")
    if item.get("status") != "in_progress" or not isinstance(lease, dict):
        raise SocomError(f"{item_id} does not have an active lease")
    if lease.get("owner") != owner:
        raise SocomError(f"{item_id} is leased by {lease.get('owner')}")
    kind = str(item.get("kind", ""))
    packet_extra: dict[str, Any] = {}
    if kind.startswith("debug-import-plan-"):
        role = "socom-dwarf-importer"
        skill = "socom-debug-import"
        slug = item_id.replace(":", "-")
        output = f"build/import-plans/{slug}.json"
        validation = [
            f"python tools/socom.py debug conflicts list --batch {item_id}",
            f"python tools/socom.py debug import-plan --batch {item_id} --output {output}",
        ]
        handoff = "python tools/socom.py progress work handoff"
        allowed_paths = [output]
        ghidra_scope = None
    elif kind.startswith("debug-import-apply-"):
        role = "socom-ghidra-reconstructor"
        skill = "socom-ghidra-reconstruction"
        translate, apply = (
            ("batch-program", "apply-batch")
            if kind == "debug-import-apply-batch"
            else ("apply-program", "apply-types")
        )
        validation = [
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py debug {translate} --plan <accepted-plan> --output build/apply/<item>.json",
            f"python tools/socom.py ghidra {apply} --program build/apply/<item>.json --item <item> --owner <owner> --scope-output build/receipts/<item>-scope.json --report-output build/apply/<item>-report.json",
            "python tools/socom.py ghidra receipt --scope <reviewed-scope>",
        ]
        handoff = "python tools/socom.py progress handoff-live-ghidra"
        allowed_paths = []
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "receipt_scope_required": True,
        }
    elif kind in ("ghidra-memory-map", "ghidra-repair"):
        role = "socom-ghidra-reconstructor"
        skill = "socom-ghidra-reconstruction"
        slug = item_id.replace(":", "-")
        command = (
            "map-zero-fill"
            if kind == "ghidra-memory-map"
            else {"labels": "repair-labels", "names": "repair-names", "boundaries": "repair-boundaries"}.get(
                REPAIRS.get(item_id, {}).get("kind"), "repair-signatures"
            )
        )
        validation = [
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py ghidra {command} --item {item_id} --owner <owner> "
            f"--scope-output build/receipts/{slug}-scope.json "
            f"--report-output build/apply/{slug}-report.json",
            f"python tools/socom.py ghidra receipt --scope build/receipts/{slug}-scope.json",
        ]
        handoff = "python tools/socom.py progress handoff-live-ghidra"
        allowed_paths = []
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "receipt_scope_required": True,
        }
    elif kind == "recon-plan-group":
        role = "socom-recon-planner"
        skill = "socom-ghidra-workflow"
        slug = item_id.replace(":", "-")
        evidence = f"build/recon-plans/{slug}-evidence.json"
        plan = f"build/recon-plans/{slug}.json"
        validation = [
            f"python tools/socom.py recon evidence --item {item_id} --output {evidence}",
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py recon validate --plan {plan}",
            f"python tools/socom.py recon program --plan {plan} --output build/apply/{slug}-apply.json",
        ]
        handoff = "python tools/socom.py progress work handoff (cite the plan SHA-256)"
        allowed_paths = [evidence, plan]
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "read_only": True,
        }
    elif kind == "recon-apply-group":
        role = "socom-ghidra-reconstructor"
        skill = "socom-ghidra-reconstruction"
        slug = item_id.replace(":", "-")
        plan = f"build/recon-plans/{item_id.removesuffix('-apply').replace(':', '-')}.json"
        validation = [
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py recon program --plan {plan} --output build/apply/{slug}.json",
            f"python tools/socom.py ghidra apply-recon --program build/apply/{slug}.json --item {item_id} "
            f"--owner <owner> --scope-output build/receipts/{slug}-scope.json "
            f"--report-output build/apply/{slug}-report.json --dry-run",
            f"python tools/socom.py ghidra apply-recon --program build/apply/{slug}.json --item {item_id} "
            f"--owner <owner> --scope-output build/receipts/{slug}-scope.json "
            f"--report-output build/apply/{slug}-report.json",
            f"python tools/socom.py ghidra receipt --scope build/receipts/{slug}-scope.json",
        ]
        handoff = "python tools/socom.py progress handoff-live-ghidra"
        allowed_paths = []
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "receipt_scope_required": True,
        }
    elif kind == REPAIR_PLAN_KIND:
        role = "socom-recon-planner"
        skill = "socom-ghidra-workflow"
        slug = item_id.replace(":", "-")
        evidence = f"build/recon-plans/{slug}-evidence.json"
        plan = f"build/recon-plans/{slug}.json"
        validation = [
            f"python tools/socom.py recon evidence --item {item_id} --output {evidence}",
            f"python tools/socom.py recon live --item {item_id}",
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py recon validate --plan {plan}",
            f"python tools/socom.py recon program --plan {plan} --output build/apply/{slug}-apply.json",
            f"python tools/socom.py ghidra preflight-batch --program build/apply/{slug}-apply.json",
        ]
        if (item.get("batch") or {}).get("globals"):
            # A repair of globals types them from their code accesses.
            validation.insert(2, f"python tools/socom.py recon global-facts --item {item_id}")
        handoff = "python tools/socom.py progress work handoff (cite the plan SHA-256)"
        allowed_paths = [evidence, plan]
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "read_only": True,
        }
    elif kind == REPAIR_APPLY_KIND:
        role = "socom-ghidra-reconstructor"
        skill = "socom-ghidra-reconstruction"
        slug = item_id.replace(":", "-")
        plan = f"build/recon-plans/{item_id.removesuffix('-apply').replace(':', '-')}.json"
        apply_args = (
            f"--program build/apply/{slug}.json --item {item_id} --owner <owner> "
            f"--scope-output build/receipts/{slug}-scope.json --report-output build/apply/{slug}-report.json"
        )
        validation = [
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py recon program --plan {plan} --output build/apply/{slug}.json",
            f"python tools/socom.py ghidra apply-recon {apply_args} --dry-run",
            f"python tools/socom.py ghidra apply-recon {apply_args}",
            f"python tools/socom.py ghidra receipt --scope build/receipts/{slug}-scope.json",
        ]
        handoff = "python tools/socom.py progress handoff-live-ghidra"
        allowed_paths = []
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "receipt_scope_required": True,
        }
    elif kind == TYPE_PLAN_KIND:
        role = "socom-recon-planner"
        skill = "socom-ghidra-workflow"
        slug = item_id.removeprefix(TYPE_PLAN_PREFIX)
        batch = item.get("batch") or {}
        derived = " --with-derived" if batch.get("with_derived") else " --struct" if batch.get("struct") else ""
        layout = f"build/type-plans/{slug}-layout"
        plan = f"build/type-plans/{slug}.json"
        if "records" in batch:
            target = (f"--class {batch['class']} " if batch.get("class") else "") + (
                f"--records {' '.join(batch.get('records') or [])} --registrar {batch.get('registrar')}"
            )
        else:
            target = f"--class {batch.get('class')}"
        validation = [
            f"python tools/socom.py recon layout {target}{derived} --output {layout}.json",
            f"python tools/socom.py recon layout {target}{derived} --output {layout}.txt",
            f"python tools/socom.py recon type-plan validate --plan {plan}",
            f"python tools/socom.py recon type-plan show --plan {plan}",
            f"python tools/socom.py recon type-plan program --plan {plan} --output build/apply/{item_id.replace(':', '-')}-apply.json",
        ]
        handoff = "python tools/socom.py progress work handoff (cite the plan SHA-256)"
        allowed_paths = [f"{layout}.json", f"{layout}.txt", plan]
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "read_only": True,
        }
    elif kind == TYPE_APPLY_KIND:
        role = "socom-ghidra-reconstructor"
        skill = "socom-ghidra-reconstruction"
        slug = item_id.replace(":", "-")
        plan = f"build/type-plans/{item_id.removeprefix(TYPE_PLAN_PREFIX).removesuffix('-apply')}.json"
        apply_args = (
            f"--program build/apply/{slug}.json --item {item_id} --owner <owner> "
            f"--scope-output build/receipts/{slug}-scope.json --report-output build/apply/{slug}-report.json"
        )
        validation = [
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py recon type-plan program --plan {plan} --output build/apply/{slug}.json",
            f"python tools/socom.py ghidra apply-type-plan {apply_args} --dry-run",
            f"python tools/socom.py ghidra apply-type-plan {apply_args}",
            f"python tools/socom.py ghidra receipt --scope build/receipts/{slug}-scope.json",
        ]
        handoff = "python tools/socom.py progress handoff-live-ghidra"
        allowed_paths = []
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "receipt_scope_required": True,
        }
    elif kind in SOURCE_PLAN_KINDS:
        # Stage 4 is file-only: the mapper writes only its evidence and plan.
        role = "socom-source-owner-mapper"
        skill = "socom-provider-boundary" if kind == PROVIDER_PLAN_KIND else "socom-source-model-recovery"
        slug = item_id.replace(":", "-")
        evidence = f"build/source-plans/{slug}-evidence.json"
        plan = f"build/source-plans/{slug}.json"
        scratch = f"build/source-plans/{owner}/"
        validation = [
            "python tools/socom.py source graph --output build/source-graph/graph.json (once per graph; shared)",
            f"python tools/socom.py source plan evidence --item {item_id} --output {evidence}",
            f"python tools/socom.py source plan draft --item {item_id} --output {plan}",
            'python tools/socom.py source sql "SELECT ..." (questions about the open rows; tables in SOURCE_CORRELATION.md)',
            f"python tools/socom.py source plan validate --plan {plan} --check --fill-annotations",
            f"python tools/socom.py source plan validate --plan {plan} --check",
            f"python tools/socom.py source plan draft --check {plan}",
        ]
        handoff = (
            "python tools/socom.py progress work handoff (cite the plan SHA-256; "
            "independent review: socom-source-owner-scrutinizer, of the rows without draft_rule and the "
            "draft --check overrides)"
        )
        reservation = apply_reservation(tracker, item)
        if reservation is not None and reservation["inferred"]:
            validation.insert(
                3,
                f"confirm or correct in the plan's reservation the directories {reservation['apply_item']} "
                f"reserves by inference ({', '.join(reservation['directories'])}): {reservation['reason']}",
            )
        packet_extra = {
            "scratch_dir": scratch,
            "reservation": (
                {key: reservation[key] for key in ("apply_item", "directories", "inferred", "reason")}
                if reservation is not None
                else None
            ),
        }
        allowed_paths = [evidence, plan, scratch]
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "read_only": True,
        }
    elif kind == PROVIDER_APPLY_KIND:
        # A provider has no source body: its apply writes no file at all.
        role = "socom-source-worker"
        skill = "socom-provider-boundary"
        plan = plan_path(item_id)
        apply = f"python tools/socom.py progress apply-source-plan --item {item_id} --owner <owner> --expected-revision <n>"
        validation = [
            f"python tools/socom.py source plan validate --plan {plan} --check",
            f"{apply} --check --dry-run",
            f"{apply} --check (records each archive member's ownership, library + GNU object or object name, "
            "in tracker evidence and writes no file)",
            "python tools/socom.py guard provider",
            f"acceptance (independent socom-verifier): python tools/socom.py source apply-check --item {item_id}, "
            f"then python tools/socom.py progress work accept --item {item_id}",
        ]
        handoff = (
            "python tools/socom.py progress work handoff (after progress apply-source-plan; its record and evidence "
            "lines are kept; no file changes)"
        )
        allowed_paths = []
        ghidra_scope = None
    elif kind == SEGMENT_APPLY_KIND:
        role = "socom-source-worker"
        skill = "socom-source-model-recovery"
        plan = plan_path(item_id)
        apply = f"python tools/socom.py progress apply-source-plan --item {item_id} --owner <owner> --expected-revision <n>"
        validation = [
            f"python tools/socom.py source plan validate --plan {plan} --check",
            f"{apply} --check --dry-run",
            f"{apply} --check (moves, creates, retires and writes the generated annotations only in the reserved "
            "directories, or the plan's corrected reservation, which it re-reserves on the item)",
            f"python tools/socom.py source annotate --plan {plan} --check",
            "python tools/socom.py audit docblocks",
            "python tools/socom.py audit source-trace",
            "python tools/socom.py guard source-placement",
            f"acceptance (independent socom-verifier): python tools/socom.py source apply-check --item {item_id}; "
            f"python tools/socom.py source plan validate --plan {plan} --check; "
            f"python tools/socom.py source annotate --plan {plan} --check; "
            f"python tools/socom.py audit source-trace; then python tools/socom.py progress work accept --item {item_id}",
        ]
        handoff = (
            "python tools/socom.py progress work handoff (after progress apply-source-plan; its record of the plan "
            "SHA-256 and every written, moved and retired file is kept as evidence)"
        )
        allowed_paths = list(item.get("resources", []))
        ghidra_scope = None
    elif kind == ORDER_SEGMENT_KIND:
        # Stage 5 phase A is file-only: the planner writes only its plan and scratch notes.
        role = "socom-source-owner-mapper"
        skill = "socom-source-model-recovery"
        plan = order_plan_path(item_id)
        scratch = f"build/order-plans/{owner}/"
        number = (item.get("batch") or {}).get("segment_number")
        decide = f"python tools/socom.py order plan decide --plan {plan} --lease-owner {owner} --artifact <id>"
        validation = [
            "python tools/socom.py source graph --output build/source-graph/graph.json (once per graph; shared)",
            f"python tools/socom.py order plan draft --item {item_id} (writes {plan}; a re-draft keeps the decisions)",
            f"python tools/socom.py order draft --segment {number} --output {scratch}evidence.json (the evidence: "
            "DWARF lines, counters, labels, initializer and variable order)",
            f"python tools/socom.py order plan validate --plan {plan} (open rows, mismatches against the rule, notes)",
            f"{decide} [--position N | --no-position] [--in-class | --out-of-line] [--class <class>] --basis \"<evidence>\"",
            f"python tools/socom.py order plan validate --plan {plan} --check",
        ]
        handoff = (
            f"python tools/socom.py progress work handoff --evidence \"{plan} sha256:<sha>\" (re-runs order plan validate "
            "--check and refuses an uncited SHA-256; independent review: socom-source-owner-scrutinizer; "
            "progress work accept re-checks the plan)"
        )
        packet_extra = {"scratch_dir": scratch, "plan": plan}
        allowed_paths = [plan, scratch]
        ghidra_scope = None
    elif kind == ORDER_LINK_KIND:
        role = "socom-source-owner-mapper"
        skill = "socom-source-model-recovery"
        plan = order_plan_path(item_id)
        validation = [
            f"python tools/socom.py order plan draft --item {item_id} (writes the order link-spec output to {plan})",
            f"python tools/socom.py order plan validate --plan {plan} --check",
            "python tools/socom.py order sql \"SELECT label, objects, drops, link_violations FROM checks WHERE objects > 0\"",
        ]
        handoff = (
            f"python tools/socom.py progress work handoff --evidence \"{plan} sha256:<sha>\" (re-runs order plan validate "
            "--check; independent review: socom-source-owner-scrutinizer; progress work accept re-checks the plan)"
        )
        packet_extra = {"plan": plan}
        allowed_paths = [plan]
        ghidra_scope = None
    elif kind in ORDER_SKELETON_KINDS:
        # Stage 5 phase B: the governed skeleton route writes only the item's reserved files under src/.
        from .order_skeleton_route import CHECK_DIR, RENDER_DIR, ROUTE_DIR
        from .order_skeleton_write import decisions_path

        role = "socom-source-worker"
        skill = "socom-source-model-recovery"
        decisions = decisions_path(item_id)
        apply = f"python tools/socom.py progress apply-order-skeleton --item {item_id} --owner {owner} --expected-revision <n>"
        validation = [
            f"{apply} --dry-run (renders the whole tree into {RENDER_DIR} from the frozen base and runs the static checks; "
            "refuses stale inputs and any change outside the item's files)",
            f"python tools/socom.py order skeleton decide --item {item_id} --lease-owner {owner} --artifact <waiting row> "
            "(--type <definition> | --owner <mangled function> | --body <mangled candidate> | --initializer <text>) --basis \"<evidence>\" "
            f"(only the waiting rows the dry run lists for this item; an undecided row stays waiting and flagged; writes {decisions})",
            f"{apply} (writes the item's files under src/ and records before/after SHA-256s, flags, conflicts and waiting rows)",
            f"python tools/socom.py order skeleton apply-check --item {item_id}",
            "python tools/socom.py audit docblocks",
            "python tools/socom.py audit source-trace",
            f"acceptance (independent socom-verifier, not a skeleton worker, not a tool maintainer): python tools/socom.py "
            f"order skeleton apply-check --item {item_id}; then python tools/socom.py progress accept-order-skeleton --item {item_id} "
            "--accepter <verifier> --evidence <review evidence> --expected-revision <n>",
        ]
        handoff = (
            f"python tools/socom.py progress handoff-order-skeleton --item {item_id} --owner {owner} --summary <summary> "
            "--expected-revision <n> (re-runs order skeleton apply-check and cites the record's SHA-256)"
        )
        packet_extra = {"decisions": decisions, "route_dir": ROUTE_DIR, "check_dir": CHECK_DIR}
        allowed_paths = [*item.get("resources", []), decisions, f"{ROUTE_DIR}/"]
        ghidra_scope = None
    elif kind == "stage-gate" and item["stage"] == SOURCE_STAGE:
        # A file-only stage: the live program must still be the stage 3 baseline.
        role = "socom-verifier"
        skill = "socom-validation"
        out = f"build/closeout-{SOURCE_STAGE}"
        validation = [
            "python tools/socom.py progress audit --strict",
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py progress stage-scope --stage {RECON_STAGE} --output {out}/stage3-scope.json",
            f"python tools/socom.py ghidra receipt --scope {out}/stage3-scope.json (equal to the {RECON_STAGE} baseline)",
            "python tools/socom.py source plan validate --plan <every accepted source plan> --check",
            "python tools/socom.py audit docblocks",
            "python tools/socom.py audit source-trace --require-complete (only unresolved rows covered by deferrals remain)",
            f"python tools/socom.py source gate-check --deferrals {out}/deferrals.json --output {out}/gate-check.json "
            "(every gate check; lists each unresolved artifact and its deferral)",
            "acceptance (an independent accepter, not the reviewer): python tools/socom.py progress accept-source-gate "
            f"--item {item_id} --accepter <accepter> --evidence <review evidence> --expected-revision <n>",
        ]
        handoff = (
            f"python tools/socom.py progress handoff-source-gate --item {item_id} --owner <owner> --summary <summary> "
            f"--deferrals {out}/deferrals.json --expected-revision <n>"
        )
        allowed_paths = [f"{out}/"]
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "read_only": True,
        }
    elif kind == "stage-gate":
        role = "socom-verifier"
        skill = "socom-validation"
        scope = f"build/closeout-{item['stage']}/stage-scope.json"
        validation = [
            "python tools/socom.py progress audit --strict",
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py progress stage-scope --stage {item['stage']} --output {scope}",
            f"python tools/socom.py ghidra receipt --scope {scope}",
            f"after acceptance: python tools/socom.py progress record-stage-baseline --stage {item['stage']} ...",
        ]
        handoff = "python tools/socom.py progress work handoff"
        allowed_paths = [f"build/closeout-{item['stage']}/"]
        ghidra_scope = {
            "project": "soCOM",
            "program": "socom.elf",
            "program_path": "/socom.elf",
            "read_only": True,
        }
    else:
        raise SocomError(f"{item_id} has no registered work-packet contract")
    packet = {
        "kind": "socom-work-packet-v1",
        "tracker_revision": tracker["revision"],
        "item": {
            key: copy.deepcopy(item.get(key))
            for key in ("id", "stage", "kind", "status", "dependencies", "resources", "selection", "batch")
        },
        "lease": copy.deepcopy(lease),
        "owner": owner,
        "role": role,
        "skill": skill,
        "allowed_paths": allowed_paths,
        "ghidra_scope": ghidra_scope,
        "validation": validation,
        "handoff": handoff,
        "prohibitions": [
            "manual tracker, census, or issue-ledger edits",
            "work outside the leased item and its explicit dependencies",
            "Ghidra mutation without ghidra-writer and the live handoff route",
            "reference ELF mutation or byte patching",
        ],
    }
    packet.update(packet_extra)
    amendments = [
        {"id": row.get("id"), "item": row.get("item"), "applies": row.get("applies"), "reason": row.get("reason")}
        for row in open_source_amendments(tracker)
        if item_id == row.get("item") or item_id in (row.get("applies") or [])
    ]
    if amendments:
        # Revise (or re-apply) for the open amendment; the stage accepts it with progress accept-source-amendment.
        packet["amendments"] = amendments
    return packet
