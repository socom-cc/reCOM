"""Machine-readable current capability dispositions."""

from __future__ import annotations

from typing import Any

from .constants import STAGES


CAPABILITIES: tuple[dict[str, Any], ...] = (
    {"id": "control-plane", "status": "active", "commands": ["commands", "progress audit", "progress migrate", "progress add-repair", "progress work reopen", "progress work packet", "issue audit"], "reason": "Canonical CAS-protected state, migration, work contracts, and discovery."},
    {"id": "dual-harness", "status": "active", "commands": ["audit agent-surface"], "reason": "Claude and Codex expose paired roles and skills."},
    {"id": "elf-evidence", "status": "active", "commands": ["reference census", "reference verify", "reference relocations"], "reason": "ELF32 MIPS evidence is parsed locally."},
    {"id": "metrowerks-name-mangling", "status": "active", "commands": ["reference demangle"], "reason": "Metrowerks C++ symbol names (CodeWarrior PS2 2.4.1, cfront/ARM scheme) parse into a structured form, render as C++ declaration text and mangle back exactly; every ELF symbol round-trips, and the non-function forms (vtables, RTTI, thunks, static initializers, local statics and their flags, labels) are classified. It is the grammar the stage 5 phase B signature check is to use."},
    {"id": "dwarf-planning", "status": "active", "commands": ["debug graph", "debug import-plan", "debug apply-program", "debug batch-program"], "reason": "DWARF plans and their Ghidra type translations are deterministic and file-only."},
    {"id": "ghidra-read", "status": "active", "commands": ["ghidra preflight", "ghidra receipt", "ghidra preflight-batch", "ghidra fingerprint", "verify asm"], "reason": "Every program-sensitive request explicitly targets socom.elf."},
    {"id": "ghidra-write", "status": "active", "commands": ["ghidra apply-types", "ghidra apply-batch", "ghidra map-zero-fill", "ghidra repair-signatures", "ghidra repair-labels", "ghidra repair-boundaries", "ghidra restore-accepted", "progress handoff-live-ghidra", "progress advance-live-ghidra"], "reason": "A single writer lease and semantic receipt govern type application and saves."},
    {"id": "ghidra-reconstruction", "status": "active", "commands": ["progress decompose-stage", "recon graph", "recon evidence", "recon validate", "recon program", "recon facts", "recon asm", "recon live", "recon types", "recon contradictions", "recon partial-candidates", "recon withdrawal-candidates", "recon by-value-rows", "progress add-recon-repair", "recon global-facts", "recon refs", "recon dwarf", "recon bytes", "recon draft", "recon void", "recon table-family", "ghidra apply-recon", "ghidra repair-names", "ghidra check-names-repair", "ghidra check-recon-apply", "progress stage-scope", "progress record-stage-baseline"], "reason": "Callee-first function groups from the ELF, validated plans, and read-back applies under the writer lease."},
    {"id": "code-derived-types", "status": "active", "commands": ["recon layout", "recon type-plan validate", "recon type-plan show", "recon type-plan live", "recon type-plan program", "recon type-plan affected", "ghidra apply-type-plan", "progress add-type-plan"], "reason": "Classes without DWARF records, plain structs named only by mangled parameter types, and families of zAnim command records (pointers proven by their AddCmd registration; existing DWARF record types referenced, not recreated) get ELF-derived layout evidence, reviewed type plans (forward declarations and copied template instantiations included), read-only live checks, and a governed type apply under the writer lease."},
    {"id": "source-trace", "status": "active", "commands": ["source artifacts", "audit docblocks", "audit source-trace"], "reason": "Source annotations are parsed and cross-checked once."},
    {"id": "source-evidence", "status": "active", "commands": ["source graph"], "reason": "Deterministic ELF-only translation-unit evidence: census-derived artifacts and gaps, TU signals with provenance, classification candidates and address segments; candidates only, nothing is owned."},
    {"id": "source-correlation-planning", "status": "active", "commands": ["progress decompose-stage", "source plan evidence", "source plan draft", "source plan open", "source plan decide", "source plan validate", "source plan emit-check", "source sql", "provider archive", "progress reopen-source-plan"], "reason": "The stage 4 seed decomposes from `source graph` into file-only owner-plan items (one per authored segment, one per provider library, one per data kind outside the segment slices) with blocked apply items and a stage gate, and is re-decomposed (--refresh) when the graph changes while accepted plans keep byte-identical slices; versioned draft rules decide what they can with a per-artifact rule, confidence and basis (draft --check proves them), the rest stays open for the planner, who lists only the open rows with their evidence and records one decision at a time; owner plans are validated against their slice, the graph and slice digests, provisional files, the apply reservation and their implied annotation targets; an accepted segment or provider plan returns to its planner for revision (`progress reopen-source-plan`: a reason and evidence in its review history, the plan file untouched) until its apply or a data reconcile starts; a derived SQLite cache answers read-only queries over the graph, relocations, DWARF units and lines and per-object LOCAL section runs; a provider archive's members and ELF symbols are listed read-only, naming the archive by file name and digest only."},
    {"id": "source-correlation-apply", "status": "active", "stage": "source-correlation", "opens": ["socom:work:source-correlation-apply-route"], "commands": ["source annotate", "source apply-check", "progress apply-source-plan", "progress open-capability-gate"], "reason": "An accepted, unchanged owner plan is applied under its apply item's lease: a segment's moves, creates, retired files (path and content SHA-256 recorded) and deterministic generated annotation docblocks only inside its reserved src/ directories or the plan's recorded correction; a provider's archive-member ownership in tracker evidence only. The apply records the plan SHA-256, an owner-map digest and every written file's SHA-256; handoff and independent acceptance re-check that record. `progress open-capability-gate` accepts the socom:work:source-correlation-apply-route gate once this capability is active and registered."},
    {"id": "source-correlation", "status": "active", "stage": "source-correlation", "commands": ["source gate-check", "progress handoff-source-gate", "progress accept-source-gate", "audit source-baseline"], "reason": "The stage gate closes through a registered route once every plan, apply and reconcile is accepted, the route gate is open and nothing is leased. An independent reviewer (no stage 4 handoff, not a tool maintainer) hands it off and a different accepter accepts it. Each re-runs the strict audits, the README snapshot, the issue ledger, open blockers, every accepted plan's validation, apply record and annotation drift, cross-plan unit consistency, `audit docblocks` and `audit source-trace --require-complete`, and the live receipt over the stage 3 scope, which must equal the `ghidra-reconstruction` baseline (an unreachable bridge refuses). Every unresolved artifact must be covered by exactly one recorded deferral that cites an open workspace issue or the user's own decision; the gate decides none. Acceptance records the file-stage baseline (plan and owner-map digests, apply files, annotation edges, unresolved rows, deferrals, stage 3 receipt), which `progress audit` and `audit source-baseline` check."},
    {"id": "function-order-targets", "status": "active", "commands": ["order target", "order link-spec", "order draft", "order sql"], "reason": "Stage 5 phase A, file-only and compiler-free: from the accepted stage 4 owner plans (as their items cite them), stage 4's decomposition graph and the ELF, each authored unit's order target (its owned artifacts per output-section region in address order with an order class: definition, copy, literal or compiler-generated fill; its runs, strays and the deferred stage 4 rows inside its runs with their gate deferral), the global object order (authored units and opaque provider objects) checked per region against .text, a deterministic order digest with a read-only SQLite cache, and the link-order specification checked statically against every region (COMMON excepted). Source-order evidence drafts (DWARF lines, the local-static counter, literal labels, the static initializer and DWARF variable order) give each unit a hypothesis source order of its definitions with every adjacency classed proven, constrained or hypothesis, and calibrate each evidence against the DWARF source order; the order plans built from them are `function-order-plans`."},
    {"id": "function-order-plans", "status": "active", "stage": "authored-function-order", "commands": ["progress decompose-stage", "order plan draft", "order plan decide", "order plan validate"], "reason": "The stage 5 seed decomposes (producer order-target, once stage 4 is accepted with its file baseline and no amendment is open) into file-only order-plan items, one per stage 4 segment holding authored units (each unit planned once, in its primary segment), the reviewed link-order plan, phase B skeleton applies behind the blocked capability gate socom:work:order-skeleton-route, phase C compile items behind socom:work:order-compile-route (linked to the compiler blocker) and the stage gate over every compile item; the record's producer digest binds the order target and the stage 4 baseline. An order plan gives each unit's definition source order (function rows with a position and an in_class flag, data rows per region), every row classed proven, constrained or hypothesis with its basis and evidence; the drafter decides what the evidence and the calibrated rule fix and leaves open only the judgment calls, the lease holder settles one row at a time, and the validator checks completeness, row classes, the order the plan predicts under the rule against the target (mismatches listed) and current digests; handoff and acceptance of a plan item re-run it with --check. Phase B is `function-order-skeletons`, phase C `function-order-compile`."},
    {"id": "source-correlation-amendment", "status": "active", "stage": "source-correlation", "commands": ["progress amend-source-plan", "progress accept-source-amendment"], "reason": "After the stage gate is accepted, an accepted plan or data reconcile is corrected through a governed amendment instead of a manual edit: the item returns for revision and its apply (a reconcile's: the segment applies that wrote its annotations, plus any named) for re-apply, with entries in their review history, while the stage stays accepted and records the open amendment (accepted items that wait for the amended ones keep their acceptance; the audits report it, not an error). The revised plan is re-accepted as usual; `progress apply-source-plan` re-applies from the files the previous apply left, stamps the record with the amendment and keeps the old record in the review history. An accepter who neither opened the amendment nor handed off an amended item, and is not a tool maintainer, accepts every open amendment together: every gate check re-runs with the deferrals in force and the live stage 3 receipt, and the recomputed file baseline becomes current while the previous one moves to `baseline_history` with the amendment reasons. Resolved deferred rows leave the deferrals in force with a note; a new unresolved row needs a new deferral with a basis."},
    {"id": "source-guards", "status": "active", "commands": ["guard raw-offset", "guard provider", "guard original-symbol"], "reason": "Current source reconstruction hazards fail closed."},
    {"id": "candidate-comparison", "status": "active", "commands": ["verify linked-byte", "verify final-elf"], "reason": "Candidate comparison is diagnostic until acceptance prerequisites exist."},
    {"id": "final-elf-catalog", "status": "active", "commands": ["audit final-elf-catalog"], "reason": "File and loaded-memory semantic gaps are explicit."},
    {"id": "toolchain-identity", "status": "active", "commands": ["toolchain verify"], "reason": "Compiler identity can be checked without claiming compile readiness."},
    {"id": "function-order-skeleton-inputs", "status": "active", "stage": "authored-function-order", "commands": ["order skeleton manifest"], "reason": "Stage 5 phase B round 1, read-only: the skeleton generator's inputs from the accepted order plans (as their acceptances cite them), the stage 3 receipt (function-index digest equal to the baseline's), DWARF, the ELF and src/: per planned function its signature with the source of each piece and the S1 check (the written declarator, parsed back with src's scope and typedef tables, mangles to the ELF name), per class its body or header, members to add, virtuals in vtable-slot order and bases, every provisional body mapped by exact mangled name to its row and move action with a frozen body snapshot, per data row its type, ELF initializer and section, and the rows needing judgment; it writes nothing under src/ and opens no gate."},
    {"id": "function-order-skeletons", "status": "deferred", "stage": "authored-function-order", "blocker": "registered-skeleton-generator", "reason": "Stage 5 phase B, no compiler: write each unit's skeleton source under src/ in its accepted order plan's order (exact signatures, provisional bodies moved into place, marked stubs) and check it statically (signatures mangle to the ELF names, the written order predicts the target); it would open socom:work:order-skeleton-route once the skeleton generator and its checks are registered."},
    {"id": "function-order-compile", "status": "deferred", "stage": "authored-function-order", "blocker": "socom:blocker:metrowerks-flexlm-license", "reason": "Stage 5 phase C: compile each unit's accepted skeleton with the exact compiler from a clean checkout and verify the object's definition order against the order target, then close the stage gate; it would open socom:work:order-compile-route, which stays blocked until the compiler's FLEXlm license works and the route is registered."},
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
