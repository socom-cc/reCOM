# Supporting evidence

`cnode-layout-reference.png` preserves a screenshot from the earlier manual
soCOM investigation. It is supporting evidence only. Exact field names,
offsets, sizes, and inheritance must be confirmed from the ELF, DWARF records,
assembly, xrefs, and Ghidra reconstruction before acceptance.

`commit-map-2026-11-13.tsv` maps old commit hashes to new ones for the 875
commits that followed `5b05af1`. On 2026-11-13 the untracked proprietary inputs
(`support/` and `compiler/`) were filtered out of that range before the branch
was first pushed, which changed every hash in it; commits up to `5b05af1` kept
theirs. The tracker, the issue ledger, and some notes cite the old hashes: look
them up in the first column. The old history was not published.
