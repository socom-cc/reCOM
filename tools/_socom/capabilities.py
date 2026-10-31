"""Machine-readable current capability dispositions."""

from __future__ import annotations

from typing import Any

from .constants import STAGES


CAPABILITIES: tuple[dict[str, Any], ...] = (
    {"id": "control-plane", "status": "active", "commands": ["commands", "progress audit", "progress migrate", "progress add-repair", "progress work reopen", "progress work packet", "issue audit"], "reason": "Canonical CAS-protected state, migration, work contracts, and discovery."},
    {"id": "dual-harness", "status": "active", "commands": ["audit agent-surface"], "reason": "Claude and Codex expose paired roles and skills."},
    {"id": "elf-evidence", "status": "active", "commands": ["reference census", "reference verify", "reference relocations"], "reason": "ELF32 MIPS evidence is parsed locally."},
    {"id": "dwarf-planning", "status": "active", "commands": ["debug graph", "debug import-plan", "debug apply-program", "debug batch-program"], "reason": "DWARF plans and their Ghidra type translations are deterministic and file-only."},
    {"id": "ghidra-read", "status": "active", "commands": ["ghidra preflight", "ghidra receipt", "ghidra preflight-batch", "ghidra fingerprint", "verify asm"], "reason": "Every program-sensitive request explicitly targets socom.elf."},
    {"id": "ghidra-write", "status": "active", "commands": ["ghidra apply-types", "ghidra apply-batch", "ghidra map-zero-fill", "ghidra repair-signatures", "ghidra repair-labels", "ghidra repair-boundaries", "ghidra restore-accepted", "progress handoff-live-ghidra", "progress advance-live-ghidra"], "reason": "A single writer lease and semantic receipt govern type application and saves."},
    {"id": "ghidra-reconstruction", "status": "active", "commands": ["progress decompose-stage", "recon graph", "recon evidence", "recon validate", "recon program", "recon facts", "recon asm", "recon live", "recon types", "recon contradictions", "recon partial-candidates", "recon withdrawal-candidates", "recon by-value-rows", "progress add-recon-repair", "recon global-facts", "recon refs", "recon dwarf", "recon bytes", "recon draft", "recon void", "recon table-family", "ghidra apply-recon", "ghidra repair-names", "ghidra check-names-repair", "ghidra check-recon-apply", "progress stage-scope", "progress record-stage-baseline"], "reason": "Callee-first function groups from the ELF, validated plans, and read-back applies under the writer lease."},
    {"id": "code-derived-types", "status": "active", "commands": ["recon layout", "recon type-plan validate", "recon type-plan show", "recon type-plan live", "recon type-plan program", "recon type-plan affected", "ghidra apply-type-plan", "progress add-type-plan"], "reason": "Classes without DWARF records, plain structs named only by mangled parameter types, and families of zAnim command records (pointers proven by their AddCmd registration; existing DWARF record types referenced, not recreated) get ELF-derived layout evidence, reviewed type plans (forward declarations and copied template instantiations included), read-only live checks, and a governed type apply under the writer lease."},
    {"id": "source-trace", "status": "active", "commands": ["source artifacts", "audit docblocks", "audit source-trace"], "reason": "Source annotations are parsed and cross-checked once."},
    {"id": "source-evidence", "status": "active", "commands": ["source graph"], "reason": "Deterministic ELF-only translation-unit evidence: census-derived artifacts and gaps, TU signals with provenance, classification candidates and address segments; candidates only, nothing is owned."},
    {"id": "source-correlation-planning", "status": "active", "commands": ["progress decompose-stage", "source plan evidence", "source plan draft", "source plan open", "source plan decide", "source plan validate", "source sql", "provider archive"], "reason": "The stage 4 seed decomposes from `source graph` into file-only owner-plan items (one per authored segment, one per provider library, one per data kind outside the segment slices) with blocked apply items and a stage gate, and is re-decomposed (--refresh) when the graph changes while accepted plans keep byte-identical slices; versioned draft rules decide what they can with a per-artifact rule, confidence and basis (draft --check proves them), the rest stays open for the planner, who lists only the open rows with their evidence and records one decision at a time; owner plans are validated against their slice, the graph and slice digests, provisional files, the apply reservation and their implied annotation targets; a derived SQLite cache answers read-only queries over the graph, relocations, DWARF units and lines and per-object LOCAL section runs; a provider archive's members and ELF symbols are listed read-only, naming the archive by file name and digest only."},
    {"id": "source-correlation-apply", "status": "active", "stage": "source-correlation", "opens": ["socom:work:source-correlation-apply-route"], "commands": ["source annotate", "source apply-check", "progress apply-source-plan", "progress open-capability-gate"], "reason": "An accepted, unchanged owner plan is applied under its apply item's lease: a segment's moves, creates, retired files (path and content SHA-256 recorded) and deterministic generated annotation docblocks only inside its reserved src/ directories or the plan's recorded correction; a provider's archive-member ownership in tracker evidence only. The apply records the plan SHA-256, an owner-map digest and every written file's SHA-256; handoff and independent acceptance re-check that record. `progress open-capability-gate` accepts the socom:work:source-correlation-apply-route gate once this capability is active and registered."},
    {"id": "source-correlation", "status": "deferred", "stage": "source-correlation", "blocker": "source-correlation-gate-route", "reason": "Owner plans can be decomposed, planned, validated and applied, and `audit source-trace --require-complete` checks completeness against the accepted owner plans and their generated annotations, but no registered route reviews and closes the stage gate (cross-plan unit consistency, the file-only stage-3 baseline check and acceptance); the stage cannot close until that route exists."},
    {"id": "source-guards", "status": "active", "commands": ["guard raw-offset", "guard provider", "guard original-symbol"], "reason": "Current source reconstruction hazards fail closed."},
    {"id": "candidate-comparison", "status": "active", "commands": ["verify linked-byte", "verify final-elf"], "reason": "Candidate comparison is diagnostic until acceptance prerequisites exist."},
    {"id": "final-elf-catalog", "status": "active", "commands": ["audit final-elf-catalog"], "reason": "File and loaded-memory semantic gaps are explicit."},
    {"id": "toolchain-identity", "status": "active", "commands": ["toolchain verify"], "reason": "Compiler identity can be checked without claiming compile readiness."},
    {"id": "native-build", "status": "deferred", "blocker": "socom:blocker:metrowerks-flexlm-license", "reason": "Native probes require the external compiler license."},
    {"id": "provider-closure", "status": "deferred", "blocker": "accepted-provider-classification", "reason": "Provider identities and ABI contracts are not accepted yet."},
    {"id": "authored-relocation-expectations", "status": "deferred", "blocker": "accepted-owner-and-relocation-model", "reason": "Mutation would encode guesses before source correlation."},
    {"id": "source-data-initializers", "status": "deferred", "blocker": "accepted-data-initializer-model", "reason": "No accepted initializer ownership model exists."},
    {"id": "native-order-call-byte-pipeline", "status": "deferred", "blocker": "native-build-and-provider-inputs", "reason": "Object production and exact providers are unavailable."},
    {"id": "artifact-cleanup", "status": "deferred", "blocker": "registered-artifact-cleanup-route", "reason": "Host CMake/CTest products are isolated, but no registered command safely covers every disposable build artifact."},
    {"id": "additional-issue-scheduler", "status": "deferred", "blocker": "demonstrated-scheduling-need", "reason": "Work leases and the issue ledger already cover the current phase."},
    {"id": "pe-coff-metadata", "status": "inapplicable", "reason": "The reference is ELF32 MIPS, not PE/COFF."},
    {"id": "x86-runtime-metadata", "status": "inapplicable", "reason": "The target ABI is R5900/MIPS."},
    {"id": "vc5-mfc-surface", "status": "inapplicable", "reason": "The target uses Metrowerks and PS2 runtime interfaces."},
    {"id": "windows-resources-and-dlls", "status": "inapplicable", "reason": "The PS2 ELF has no Windows resource or DLL model."},
)


CAPABILITY_GATE_ACCEPTER = "progress open-capability-gate"


def capability_opening(item_id: str) -> dict[str, Any] | None:
    """The capability row that lists a ``capability-gate`` work item under ``opens``."""

    rows = [row for row in CAPABILITIES if item_id in (row.get("opens") or [])]
    return dict(rows[0]) if len(rows) == 1 else None


def audit_capabilities(commands: list[dict[str, Any]]) -> dict[str, Any]:
    registered = {row["command"] for row in commands}
    errors: list[str] = []
    ids: set[str] = set()
    for row in CAPABILITIES:
        identifier = str(row.get("id", ""))
        if not identifier or identifier in ids:
            errors.append(f"capability ID is missing or duplicated: {identifier!r}")
        ids.add(identifier)
        status = row.get("status")
        if status not in {"active", "deferred", "inapplicable"}:
            errors.append(f"{identifier}: invalid status {status!r}")
        if not row.get("reason"):
            errors.append(f"{identifier}: disposition reason is missing")
        if status == "active":
            missing = sorted(set(row.get("commands", [])) - registered)
            if missing:
                errors.append(f"{identifier}: active commands are missing: {missing}")
        elif status == "deferred" and not row.get("blocker"):
            errors.append(f"{identifier}: deferred capability has no blocker")
        if "stage" in row and row["stage"] not in STAGES:
            errors.append(f"{identifier}: unknown stage {row['stage']!r}")
        opens = row.get("opens")
        if opens is not None:
            if status != "active" or not isinstance(opens, list) or not all(
                isinstance(value, str) and value.startswith("socom:work:") for value in opens
            ):
                errors.append(f"{identifier}: only an active capability opens capability-gate work items")
            elif any(capability_opening(value) is None for value in opens):
                errors.append(f"{identifier}: a capability gate is opened by more than one capability")
    return {
        "ok": not errors,
        "capability_count": len(CAPABILITIES),
        "capabilities": [dict(row) for row in CAPABILITIES],
        "errors": errors,
    }


def capability_document() -> str:
    lines = [
        "# soCOM Tool Coverage",
        "",
        "This target-native inventory is generated from the authoritative capability registry.",
        "Active means implemented and tested; deferred means useful after a named prerequisite;",
        "inapplicable means the capability would encode the wrong executable format or ABI.",
        "",
        "| Capability | Status | Commands or blocker | Rationale |",
        "| --- | --- | --- | --- |",
    ]
    for row in CAPABILITIES:
        route = ", ".join(f"`{value}`" for value in row.get("commands", []))
        if not route:
            route = f"`{row.get('blocker', 'target mismatch')}`"
        lines.append(
            f"| `{row['id']}` | {row['status']} | {route} | {row['reason']} |"
        )
    return "\n".join(lines) + "\n"
