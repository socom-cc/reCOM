# Tracker model

`.agent/RECONSTRUCTION_PROGRESS.json` is canonical generated state. It uses
schema version 5 and a compare-and-swap revision. Manual edits are forbidden.

The tracker separates immutable binaries and physical blocks, symbols and
relocations, semantic spans and types, source owners and physical artifacts,
verification targets, work items, blockers, evidence, and tombstones.

## Reads

```powershell
python tools/socom.py progress next --json
python tools/socom.py progress status
python tools/socom.py progress show <id>
python tools/socom.py progress find <query>
python tools/socom.py progress audit --strict
python tools/socom.py progress work packet --item <id> --owner <owner>
```

## Mutations and leases

Claim, heartbeat, handoff, acceptance, and release require
`--expected-revision`. Successful mutations increment the revision atomically.
Stale revisions, unmet dependencies, invalid transitions, and competing
writers fail closed. A lock covers read/check/live-operation/write, and JSON
replacement is atomic.

Leases expire to `ready` and never imply completion. Handoff owners cannot
self-accept. A reviewer who finds defects runs `progress work reject` with a
reason and evidence; the item returns to `ready`, and the rejected handoff,
its evidence, and any Ghidra receipt move to the item's `review_history`.
Handoff owners cannot reject their own work. `ghidra-writer` is exclusive. Generic handoff/acceptance rejects
items that own it. Undecomposed `stage-seed` items remain blocked and cannot be
claimed, handed off, or accepted.

DWARF work is split into file-only `debug-import-plan-*` items and live
`debug-import-apply-*` items. Plan items use the DWARF importer and write only
under `build/import-plans`; apply items depend on their reviewed plan and alone
own the explicit Ghidra program plus `ghidra-writer` resources. Batch apply
items also depend on `socom:work:ghidra-zero-fill-memory`, a writer item that
maps the load image's zero fill (Ghidra's import mapped only file-backed
bytes, so `.bss` globals had no memory). A `ghidra-repair` writer item restores
accepted live state that an accepted apply changed outside its scope and no
later batch will correct; its spec (targets, the exact wrong state, the state
to restore) lives in `tools/_socom/repairs.py`; `progress add-repair` inserts
one once every apply it corrects is accepted. Work packets render the exact
role, skill, paths, program, validation, and handoff route for an active lease.

Schema upgrades use `progress migrate --expected-revision <revision>`. The
command refuses active leases or pending handoffs, applies each schema step in
order (2 to 3 splits plan and apply items; 3 to 4 adds the zero-fill memory
item and re-blocks batch applies that now wait for it; 4 to 5 adds the repair
of the signatures batch 001 changed through thunks), records one migration
history entry per step, and becomes a no-op at the current schema. A fresh
tracker at schema 5 has no repair item: with the thunk guard, nothing needs
repairing.

## Ghidra target and receipts

The `socom:verification:ghidra-program` target records only portable facts:
project/program identity, immutable source hash, language/compiler/version,
image base, baseline/current semantic receipt SHA-256, and receipt history. It
does not contain the external project directory or bridge endpoint.

`progress handoff-live-ghidra` validates a leased scope, computes a semantic
receipt, saves `socom.elf` exactly once, proves the receipt remains stable, and
moves the item to `awaiting_acceptance`. `progress advance-live-ghidra`
recomputes the stored scope without saving, compares the digest, accepts with a
different owner, and appends target history.

`progress rebaseline-live-ghidra` records a fresh-import baseline after a
Ghidra version re-pin. It is limited to the untouched bootstrap target and
requires unchanged function and type index digests; other deltas are recorded
in the appended history entry.

Receipts are evidence, not acceptance. They cover portable target facts,
analysis/bookmarks, the assembly sentinel, full function/type/data index
digests, and exact scoped facts.

`.agent/WORKSPACE_ISSUES.json` is a separate CAS-protected process/tool ledger.
It is not a shadow reconstruction tracker; stage blockers remain in
`RECONSTRUCTION_PROGRESS.json`.
