"""Machine-readable current capability dispositions."""

from __future__ import annotations

from typing import Any


CAPABILITIES: tuple[dict[str, Any], ...] = (
    {"id": "control-plane", "status": "active", "commands": ["commands", "progress audit", "progress migrate", "progress work packet", "issue audit"], "reason": "Canonical CAS-protected state, migration, work contracts, and discovery."},
    {"id": "dual-harness", "status": "active", "commands": ["audit agent-surface"], "reason": "Claude and Codex expose paired roles and skills."},
    {"id": "elf-evidence", "status": "active", "commands": ["reference census", "reference verify", "reference relocations"], "reason": "ELF32 MIPS evidence is parsed locally."},
    {"id": "dwarf-planning", "status": "active", "commands": ["debug graph", "debug import-plan", "debug apply-program"], "reason": "DWARF plans and their Ghidra type translations are deterministic and file-only."},
    {"id": "ghidra-read", "status": "active", "commands": ["ghidra preflight", "ghidra receipt", "verify asm"], "reason": "Every program-sensitive request explicitly targets socom.elf."},
    {"id": "ghidra-write", "status": "active", "commands": ["ghidra apply-types", "progress handoff-live-ghidra", "progress advance-live-ghidra"], "reason": "A single writer lease and semantic receipt govern type application and saves."},
    {"id": "source-trace", "status": "active", "commands": ["source artifacts", "audit docblocks", "audit source-trace"], "reason": "Source annotations are parsed and cross-checked once."},
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
