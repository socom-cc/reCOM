# Reconstruction workflow

The tracker is the authority for ordering, ownership, evidence, and completion.
The current source tree is an input to evaluate, not a progress ledger.

## Stage gates

`reference-census` is accepted only from the live immutable ELF and canonical
workspace parser. `debug-metadata-import` first produces and independently
accepts a file-only global type plan, applies that plan under the Ghidra writer
lease, then repeats the plan/apply split for compile-unit batches. Semantic
reconstruction then completes unresolved types/functions/data callee-first and
type-first.

`source-correlation` assigns accepted artifacts to translation units and
separates source ownership from physical ELF storage. Authored order and call
contracts follow. Authored-byte work is an independent monotonic lane once its
blocks have accepted order. The full-order lane integrates providers; both
lanes join before linked-byte matching. Final validation starts only when every
typed region and provider input is accounted for.

`ghidra-reconstruction` is decomposed by its registered producer into
callee-first function groups ([RECONSTRUCTION.md](RECONSTRUCTION.md)).
`source-correlation` is decomposed into file-only owner-plan items per
segment, provider library and data kind
([SOURCE_CORRELATION.md](SOURCE_CORRELATION.md)). Its apply items wait for
a capability gate that `progress open-capability-gate` opens once the
registered apply route (`progress apply-source-plan`) is active. An
independent reviewer and accepter close its stage gate with
`progress handoff-source-gate` and `progress accept-source-gate`, which
record a file-stage baseline.
`authored-function-order` has its phase A tools (`order target`,
`order link-spec`; [FUNCTION_ORDER.md](FUNCTION_ORDER.md)) but no producer
yet, so its seed stays closed.
Later native stages currently have explicit blockers and undecomposed seeds.
Those seeds cannot be used as generic work or accepted as proof. A stage
becomes executable only after a real producer and stage-specific acceptance
route replace the seed.

## Work lifecycle

1. Run strict doctor and tracker audits.
2. Read the next item and all dependencies/evidence.
3. Claim it with the current revision and bounded lease.
4. Render `progress work packet --item <id> --owner <owner>` and perform only
   its scope, heartbeating if necessary.
5. Produce commands, hashes, addresses, and artifacts that reproduce the result.
6. Handoff without accepting your own disputed conclusions.
7. Parent/owner review accepts or returns the packet.

The tracker uses compare-and-swap revisions. A stale mutation fails rather than
overwriting another worker. Exclusive resources, especially the Ghidra
writer, are enforced in addition to logical dependencies.

Known bootstrap blockers are retained rather than normalized away: the
Metrowerks compiler needs a valid FLEXlm license for native compilation, and
ten reference relocation rows use vendor relocation type 123 whose exact
semantics must be proven before linked-byte acceptance.

## Evidence packets

Evidence should contain:

- reference hashes and Ghidra semantic receipt digests;
- exact address/section/symbol or DIE identities;
- commands and tool versions;
- affected callees/callers/types/globals;
- compiler flags and provider inputs when applicable;
- test and verifier output;
- unresolved contradictions and why they block acceptance.

Generated data belongs in a disposable `build/` directory unless it is an
accepted canonical census or tracker state. Local CMake, CTest, and Ninja
products are never tracked: they resolve the current checkout, interpreter,
and tool installation by design. Authored instructions and configuration use
repository-relative paths or environment forms such as `%USERPROFILE%`,
PowerShell `$env:NAME`, and CMake `$env{NAME}` instead of literal local paths.

Linked and final candidate ELFs can be checked without changing them:

```powershell
python tools/socom.py verify linked-byte --candidate build/socom.elf
python tools/socom.py verify final-elf --candidate build/socom.elf
```

The first command compares linked sections and relocation-bearing regions. The
second additionally compares typed metadata and whole-file bytes. Both report
`comparison_ok` separately from `acceptance_ready`; a byte-identical candidate
cannot bypass unmet dependencies or blockers. Final `--acceptance` also
requires `audit final-elf-catalog` to be complete.
