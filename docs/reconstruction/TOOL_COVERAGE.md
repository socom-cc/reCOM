# soCOM Tool Coverage

This target-native inventory is generated from the authoritative capability registry.
Active means implemented and tested; deferred means useful after a named prerequisite;
inapplicable means the capability would encode the wrong executable format or ABI.

| Capability | Status | Commands or blocker | Rationale |
| --- | --- | --- | --- |
| `control-plane` | active | `commands`, `progress audit`, `progress migrate`, `progress add-repair`, `progress work packet`, `issue audit` | Canonical CAS-protected state, migration, work contracts, and discovery. |
| `dual-harness` | active | `audit agent-surface` | Claude and Codex expose paired roles and skills. |
| `elf-evidence` | active | `reference census`, `reference verify`, `reference relocations` | ELF32 MIPS evidence is parsed locally. |
| `dwarf-planning` | active | `debug graph`, `debug import-plan`, `debug apply-program`, `debug batch-program` | DWARF plans and their Ghidra type translations are deterministic and file-only. |
| `ghidra-read` | active | `ghidra preflight`, `ghidra receipt`, `ghidra preflight-batch`, `ghidra fingerprint`, `verify asm` | Every program-sensitive request explicitly targets socom.elf. |
| `ghidra-write` | active | `ghidra apply-types`, `ghidra apply-batch`, `ghidra map-zero-fill`, `ghidra repair-signatures`, `ghidra repair-labels`, `ghidra restore-accepted`, `progress handoff-live-ghidra`, `progress advance-live-ghidra` | A single writer lease and semantic receipt govern type application and saves. |
| `ghidra-reconstruction` | active | `progress decompose-stage`, `recon graph`, `recon evidence`, `recon validate`, `recon program`, `recon facts`, `recon asm`, `recon live`, `recon types`, `recon refs`, `recon dwarf`, `ghidra apply-recon`, `ghidra check-recon-apply`, `progress stage-scope`, `progress record-stage-baseline` | Callee-first function groups from the ELF, validated plans, and read-back applies under the writer lease. |
| `source-trace` | active | `source artifacts`, `audit docblocks`, `audit source-trace` | Source annotations are parsed and cross-checked once. |
| `source-guards` | active | `guard raw-offset`, `guard provider`, `guard original-symbol` | Current source reconstruction hazards fail closed. |
| `candidate-comparison` | active | `verify linked-byte`, `verify final-elf` | Candidate comparison is diagnostic until acceptance prerequisites exist. |
| `final-elf-catalog` | active | `audit final-elf-catalog` | File and loaded-memory semantic gaps are explicit. |
| `toolchain-identity` | active | `toolchain verify` | Compiler identity can be checked without claiming compile readiness. |
| `native-build` | deferred | `socom:blocker:metrowerks-flexlm-license` | Native probes require the external compiler license. |
| `provider-closure` | deferred | `accepted-provider-classification` | Provider identities and ABI contracts are not accepted yet. |
| `authored-relocation-expectations` | deferred | `accepted-owner-and-relocation-model` | Mutation would encode guesses before source correlation. |
| `source-data-initializers` | deferred | `accepted-data-initializer-model` | No accepted initializer ownership model exists. |
| `native-order-call-byte-pipeline` | deferred | `native-build-and-provider-inputs` | Object production and exact providers are unavailable. |
| `artifact-cleanup` | deferred | `registered-artifact-cleanup-route` | Host CMake/CTest products are isolated, but no registered command safely covers every disposable build artifact. |
| `additional-issue-scheduler` | deferred | `demonstrated-scheduling-need` | Work leases and the issue ledger already cover the current phase. |
| `pe-coff-metadata` | inapplicable | `target mismatch` | The reference is ELF32 MIPS, not PE/COFF. |
| `x86-runtime-metadata` | inapplicable | `target mismatch` | The target ABI is R5900/MIPS. |
| `vc5-mfc-surface` | inapplicable | `target mismatch` | The target uses Metrowerks and PS2 runtime interfaces. |
| `windows-resources-and-dlls` | inapplicable | `target mismatch` | The PS2 ELF has no Windows resource or DLL model. |
