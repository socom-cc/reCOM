"""Unified reconstruction tracker with CAS revisions and work leases."""

from __future__ import annotations

import copy
import datetime as dt
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

from .locking import exclusive_state_lock
from .source import source_owners
from .util import SocomError, atomic_write_json, load_json, stable_id

WORK_STATUSES = {
    "blocked",
    "ready",
    "in_progress",
    "awaiting_acceptance",
    "accepted",
}
STAGE_STATUSES = {"pending", "active", "accepted"}

GHIDRA_WRITER_RESOURCES = ["ghidra:soCOM/socom.elf", "ghidra-writer"]


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

    section_by_index = {section["index"]: section for section in census["sections"]}
    symbols = [
        {
            **row,
            "section": section_by_index.get(row["section_index"], {}).get("name"),
            "reconstruction": {
                "boundary": "unverified",
                "identity": "reference-evidence",
                "prototype": "unverified",
                "return_type": "unverified",
                "parameters": "unverified",
                "callee_contracts": "unverified",
                "receiver_and_locals": "unverified",
                "globals_and_data": "unverified",
                "source_path": "unverified",
                "decompilation_consistency": "unverified",
            },
        }
        for row in census.get("symbols", [])
    ]

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
        "symbols": symbols,
        "relocations": census.get("relocations", []),
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
    for item in items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.startswith(
            ("socom:work:", "socom:debug-batch:")
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
        if kind == "stage-seed" and status != "blocked":
            errors.append(f"{item_id} undecomposed stage seed must remain blocked")
        missing = set(item.get("dependencies", [])) - known
        if missing:
            errors.append(f"{item_id} has missing dependencies {sorted(missing)}")
        if status == "accepted":
            unmet = [
                dep
                for dep in item.get("dependencies", [])
                if _work_by_id(tracker)[dep]["status"] != "accepted"
            ]
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
    if reconstruction_seed is not None and set(reconstruction_seed.get("dependencies", [])) != {
        item["id"] for item in apply_items
    }:
        errors.append("Ghidra reconstruction seed does not depend on all debug apply items")
    if strict:
        required_collections = (
            "binaries",
            "physical_blocks",
            "semantic_spans",
            "symbols",
            "relocations",
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
        if census is not None:
            if tracker.get("reference") != census.get("reference"):
                errors.append("tracker reference identity differs from reference census")
            if len(tracker.get("symbols", [])) != len(census.get("symbols", [])):
                errors.append("tracker symbol population differs from reference census")
            if len(tracker.get("relocations", [])) != len(
                census.get("relocations", [])
            ):
                errors.append(
                    "tracker relocation population differs from reference census"
                )
            census_sections = census.get("sections", [])
            if tracker.get("output_sections") != census_sections:
                errors.append("tracker output sections differ from reference census")
    return errors


def require_revision(tracker: dict[str, Any], expected_revision: int) -> None:
    actual = tracker["revision"]
    if actual != expected_revision:
        raise SocomError(f"revision conflict: expected {expected_revision}, actual {actual}")


def _refresh_ready_and_stages(tracker: dict[str, Any]) -> None:
    items = _work_by_id(tracker)
    for item in tracker["work_items"]:
        if item["status"] != "blocked":
            continue
        if item.get("kind") == "stage-seed":
            continue
        if all(items[dep]["status"] == "accepted" for dep in item["dependencies"]):
            item["status"] = "ready"

    for stage in tracker["stages"]:
        stage_items = [
            item for item in tracker["work_items"] if item["stage"] == stage["name"]
        ]
        if stage["name"] == "reference-census":
            stage["status"] = "accepted"
        elif stage_items and all(item["status"] == "accepted" for item in stage_items):
            stage["status"] = "accepted"
        elif any(
            item["status"] in {"ready", "in_progress", "awaiting_acceptance"}
            for item in stage_items
        ):
            stage["status"] = "active"
        else:
            stage["status"] = "pending"


def next_work(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    _expire_leases_in_memory(tracker)
    ready = [item for item in tracker["work_items"] if item["status"] == "ready"]
    stage_rank = {name: index for index, name in enumerate(STAGES)}
    return sorted(
        ready,
        key=lambda item: (
            stage_rank[item["stage"]],
            str(item.get("batch", {}).get("batch_number", 0) if item.get("batch") else 0),
            item["id"],
        ),
    )


def find_rows(tracker: dict[str, Any], query: str) -> list[dict[str, Any]]:
    folded = query.casefold()
    result = []
    for collection in (
        "symbols",
        "owners",
        "types",
        "work_items",
        "blockers",
        "evidence",
    ):
        for row in tracker.get(collection, []):
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
    if item["lease"]["owner"] != owner:
        raise SocomError(f"{item_id} is leased by {item['lease']['owner']}")
    if "ghidra-writer" in item.get("resources", []):
        raise SocomError(
            f"{item_id} owns ghidra-writer; use progress handoff-live-ghidra"
        )
    if not summary.strip():
        raise SocomError("handoff summary must not be empty")
    item["status"] = "awaiting_acceptance"
    item["lease"] = None
    item["handoff"] = {
        "owner": owner,
        "summary": summary.strip(),
        "submitted_at": _iso(_utc_now()),
    }
    item["evidence"] = sorted(set(evidence))


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
    if item.get("kind") == "stage-seed":
        raise SocomError(f"{item_id} is an undecomposed stage seed")
    if item["status"] != "awaiting_acceptance":
        raise SocomError(f"{item_id} is {item['status']}, not awaiting_acceptance")
    if "ghidra-writer" in item.get("resources", []):
        raise SocomError(
            f"{item_id} owns ghidra-writer; use progress advance-live-ghidra"
        )
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
    item.setdefault("review_history", []).append(record)
    item["status"] = "ready"
    item["handoff"] = None
    item["evidence"] = []


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


def migrate_tracker(path: Path, expected_revision: int) -> dict[str, Any]:
    """Migrate the tracker to the current schema under its normal lock."""

    with exclusive_state_lock(path):
        current = load_tracker(path)
        require_revision(current, expected_revision)
        if current.get("schema_version") == SCHEMA_VERSION:
            return current
        if current.get("schema_version") not in (2, 3):
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
    elif kind == "ghidra-memory-map":
        role = "socom-ghidra-reconstructor"
        skill = "socom-ghidra-reconstruction"
        slug = item_id.replace(":", "-")
        validation = [
            "python tools/socom.py ghidra preflight --strict",
            f"python tools/socom.py ghidra map-zero-fill --item {item_id} --owner <owner> "
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
    else:
        raise SocomError(f"{item_id} has no registered work-packet contract")
    return {
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
