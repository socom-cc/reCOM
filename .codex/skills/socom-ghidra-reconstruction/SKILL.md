---
name: socom-ghidra-reconstruction
description: Reconstruct the live soCOM Ghidra program under its exclusive writer lease. Use for reviewed types, functions, prototypes, variables, globals, labels, comments, xrefs, focused reanalysis, propagation checks, and semantic-receipt handoff.
---

# soCOM Ghidra reconstruction

Read root [`AGENTS.md`](../../../AGENTS.md) and
[`GHIDRA.md`](../../../docs/reconstruction/GHIDRA.md). Require a parent-assigned
work item, current revision, reviewed conflict-free plan, receipt-scope file,
and exclusive `ghidra-writer` lease. Connect only to project `soCOM` and pass
`program=socom.elf` on every program-sensitive call. Qualify overlays as
`<overlay>::<hex>`.

Work type-first and callee-first. Preserve aliases and source-defined types.
Use stable project categories, resolve conflicts explicitly, and never accept
silent `.conflict` variants. Apply forward declarations, indirections,
composites, prototypes, globals, locals, and allocation types in dependency
order. Verify assembly, xrefs, R5900 ABI, delay slots, `$gp`, relocation pairs,
vtables, RTTI, and source evidence. Treat p-code and decompilation as
provisional. Pass `strict_mode=off` when mutation tools expose plugin
Hungarian/Pascal naming enforcement; that convention is not project authority.

Re-decompile directly affected callers after callee or type changes. Use
focused reanalysis routinely; use full reanalysis only after verified
function-boundary, code/data, or reference changes. Do not open, switch,
import, close, delete, save all, run scripts, use the debugger, patch bytes, or
clear flow. Do not call `save_program` directly. The one exception to the
script rule is `ghidra repair-boundaries`, under
`socom:work:ghidra-repair-split-function-boundaries` only. That command sends
its own pinned, reviewed script (see "One-time boundary repair" in
`GHIDRA.md`); never call a script endpoint yourself.

Finish through `progress handoff-live-ghidra`; it validates the scope, saves
`socom.elf` exactly once, proves the semantic receipt is stable across the
save, and submits the item for independent acceptance. Never self-accept.
