# Reconstruction knowledge index

This directory is the durable evidence/navigation layer. Tracker state remains
authoritative; prose records methods, constraints, and accepted interpretations
without becoming a second progress system.

| Topic | Document |
| --- | --- |
| Pipeline, work lifecycle, evidence packets | [WORKFLOW.md](WORKFLOW.md) |
| Unified tracker and issue ledger | [TRACKER.md](TRACKER.md) |
| Ghidra safety, receipts, and completion rules | [GHIDRA.md](GHIDRA.md) |
| DWARF 1 graph and import planning | [DWARF_IMPORT.md](DWARF_IMPORT.md) |
| Stage 3 groups, plans, and applies | [RECONSTRUCTION.md](RECONSTRUCTION.md) |
| Compiler identity and readiness | [TOOLCHAIN.md](TOOLCHAIN.md) |
| Functional-port ps2dev toolchain (not a matching compiler) | [PORT_TOOLCHAIN.md](PORT_TOOLCHAIN.md) |
| User decisions the binary does not settle (stage-4 function placements) | [decisions/README.md](decisions/README.md) |
| Final ELF catalog and acceptance boundary | [FINAL_ELF.md](FINAL_ELF.md) |
| Agent/role launch protocol | [AGENT_LAUNCH_CHECKLIST.md](AGENT_LAUNCH_CHECKLIST.md) |
| Source-to-artifact evidence | [SOURCE_TRACEABILITY.md](SOURCE_TRACEABILITY.md) |
| Stage 4 owner plans, items, and validation | [SOURCE_CORRELATION.md](SOURCE_CORRELATION.md) |
| Stage 5 order targets, link order, source-order drafts, the emission-rule calibration, the producer, order plans, and phases | [FUNCTION_ORDER.md](FUNCTION_ORDER.md) |
| Provider classification and ABI closure | [PROVIDER_BOUNDARY.md](PROVIDER_BOUNDARY.md) |
| Reusable proven observations | [VERIFIED_PATTERNS.md](VERIFIED_PATTERNS.md) |
| Behavioral smoke manifest format | [functional target README](../../tools/functional_verify_targets/README.md) |
| Public command registry | [COMMANDS.md](COMMANDS.md) |
| Target-native tool coverage | [TOOL_COVERAGE.md](TOOL_COVERAGE.md) |

Accepted evidence images or extracts belong under `evidence/` with provenance,
scope, and limitations recorded in its README. Disposable plans, reports, and
build products belong under `build/`.

When adding a durable note:

1. cite the immutable ELF address/section/symbol, DWARF DIE, Ghidra view, or exact
   compiler probe;
2. separate observation from inference;
3. state the affected scope and known counterexamples;
4. link the tracker evidence/work item rather than copying its status;
5. update this index if the note creates a new durable topic.
