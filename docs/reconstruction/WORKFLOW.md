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
`authored-function-order` is decomposed by its producer `order-target`, once
stage 4 is accepted with no open amendment, into file-only order-plan items:
one per stage 4 segment holding authored units, plus the link-order plan. A
planner drafts, decides and validates each plan (`order plan draft`,
`order plan decide`, `order plan validate`), and an independent reviewer
accepts it; handoff and acceptance re-run `order plan validate --check`.
Its phase B (skeleton source, static checks, no compile) waits for
`socom:work:order-skeleton-route`, which `progress open-capability-gate`
opens now that the skeleton route is registered. `progress
add-order-skeleton-prepare` adds one serialized prepare item (headers, holding
files, orphan deletions) before the segment applies, which then reserve only
their units' files. Each item is written with `progress apply-order-skeleton`
under its lease (waiting rows settled with `order skeleton decide`), handed
off with `progress handoff-order-skeleton` and accepted by an independent
verifier with `progress accept-order-skeleton`; both re-run
`order skeleton apply-check`. A stage 4 amendment reopens the stage 5 items
built on it (`progress reopen-order-skeleton`), stage 5 absorbs the accepted
amendment (`progress rebase-function-order`), and the reopened skeletons are
re-applied as merges that keep later `src/` edits. Its phase C compile items and the stage gate wait for
`socom:work:order-compile-route`, which opens only once the compiler license
(`socom:blocker:metrowerks-flexlm-license`) works and a compile route exists
([FUNCTION_ORDER.md](FUNCTION_ORDER.md)).
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
