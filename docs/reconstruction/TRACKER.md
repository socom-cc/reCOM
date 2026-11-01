# Tracker model

`.agent/RECONSTRUCTION_PROGRESS.json` is canonical generated state. It uses
schema version 6 and a compare-and-swap revision. Manual edits are forbidden.

The tracker separates immutable binaries and physical blocks, semantic spans
and types, source owners and physical artifacts, verification targets, work
items, blockers, evidence, and tombstones. Symbols and relocations are
immutable reference evidence and live only in `.agent/REFERENCE_CENSUS.json`
(schema 6 dropped the tracker's copies, which were 91% of its size and never
changed).

`python tools/socom.py progress sql "<SELECT ...>"` queries a derived,
read-only SQLite cache (`build/cache/progress.sqlite`, never committed) built
from the tracker, census and issue ledger; it is rebuilt automatically when
any of them changes. Tables: `work_items`, `stages`, `symbols`,
`relocations`, `issues`, `meta`. Canonical state stays in the JSON files.

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
Handoff owners cannot reject their own work. An accepted reconstruction plan
whose apply has not started can be returned with `progress work reopen` (a
reason is required; the acceptance and handoff move to `review_history`, the
plan becomes `ready` and its apply `blocked`). An apply that started or
finished is corrected through a governed repair instead. An accepted stage 4
segment or provider plan returns the same way with `progress reopen-source-plan`
(reason and evidence required) until its apply or a data reconcile starts
([SOURCE_CORRELATION.md](SOURCE_CORRELATION.md#reopening-an-accepted-plan)). `ghidra-writer` is exclusive. Generic handoff/acceptance rejects
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
of the signatures batch 001 changed through thunks; 5 to 6 drops the
tracker's copies of the census symbols and relocations), records one migration
history entry per step, and becomes a no-op at the current schema. A fresh
tracker has no thunk repair item: with the thunk guard, nothing needs
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

`progress record-stage-baseline --stage <name>` records, once, the live
receipt over the union of an accepted stage's writer-item scopes, as the
baseline the next stage builds on. It needs every item in the stage accepted,
no writer in progress or awaiting acceptance, evidence, and a recorder who
handed off none of the stage's work. It reads Ghidra without saving. The stage
row stores the receipt digest, the union scope's digest and counts, and the
receipt's counts and indexes, and its `accepted_evidence` cites the receipt.
The strict audit recomputes the union scope from the items and requires the
same digest. `--dry-run` reports the entry without writing. It refuses
`source-correlation`, which is file-only: that stage's baseline is recorded
when its gate is accepted (below).

`progress decompose-stage --stage ghidra-reconstruction` replaces the stage 3
seed with callee-first `recon-plan-group`/`recon-apply-group` pairs and turns
the seed into a `stage-gate` that waits for every apply; see
[RECONSTRUCTION.md](RECONSTRUCTION.md). The stage row records the
decomposition's graph digest, group size, and counts, and the audit holds the
items to it. `progress stage-scope` writes an accepted stage's union scope.

`progress decompose-stage --stage source-correlation` replaces the stage 4
seed with file-only `source-plan-segment`, `source-plan-provider` and
`source-data-reconcile` items, `source-apply-segment` items that reserve
their `src/` directories (inferred from neighbouring units when a segment
has no path evidence), `source-apply-provider` items that reserve nothing
and record archive-member ownership in tracker evidence only, and a gate.
Every apply also waits for
`socom:work:source-correlation-apply-route`, a `capability-gate` item that
no worker can claim, hand off or accept. It stays blocked until
`progress open-capability-gate` accepts it, which that command does only
when an active registered capability lists the gate under `opens`. A
source apply's `progress apply-source-plan` records a `source_apply` record
(plan SHA-256, owner-map digest, written files and their SHA-256s, moves and
retired files) on the item; see
[SOURCE_CORRELATION.md](SOURCE_CORRELATION.md).

The `source-correlation` stage gate closes only through its registered
route. Generic `progress work handoff` and `progress work accept` refuse
it. Its reviewer, the lease owner, hands it off with
`progress handoff-source-gate`. A different accepter accepts it with
`progress accept-source-gate`. Neither may have handed off any stage 4
work, and neither may be a tool maintainer. Each route re-runs every gate
check, including the live receipt over the stage 3 scope, which must equal
that stage's baseline. Every unresolved artifact must be covered by exactly
one recorded deferral that cites an open workspace issue or the user's
quoted decision. The handoff stores a `source_gate` record (deferrals and
candidate baseline state) on the gate. The acceptance moves that state to
the stage row's `baseline` (kind `source-file-baseline`), and the stage's
`accepted_evidence` cites `source-file-baseline-sha256:<digest>` and the
kept receipt. `progress audit` checks the record and the baseline on every
mutation, and `audit source-baseline` also checks the plan files and the
annotation edges under `src/`. A rejected review moves the record to the
review history.

After the gate is accepted, an accepted stage 4 plan or data reconcile is
corrected with `progress amend-source-plan` (reason and evidence required;
not by its handoff owner). The item returns for revision and its apply (for
a data reconcile: the segment applies that wrote its annotations, plus any
named with `--reapply`) returns to `blocked` for re-apply, each with a
review-history entry. The stage row records the open amendment under
`amendments` (`socom:source-amendment:NNN`). The stage stays `accepted`,
and accepted stage 4 items that wait for the amended items keep their
acceptance. `progress apply-source-plan` re-applies from the files the
previous apply left; the record is replaced and the old one kept in the
review history. Once every amended item is re-accepted,
`progress accept-source-amendment` (an accepter who did not open the
amendment, handed off no amended item and is not a tool maintainer) re-runs
the gate checks with the live stage 3 receipt and records the recomputed
baseline. The previous baseline moves to `baseline_history` with the
amendment reasons. `progress audit --strict` and `audit source-baseline`
report an open amendment without failing, and validate the baseline chain;
see [SOURCE_CORRELATION.md](SOURCE_CORRELATION.md#amending-an-accepted-plan).

Receipts are evidence, not acceptance. They cover portable target facts,
analysis/bookmarks, the assembly sentinel, full function/type/data index
digests, and exact scoped facts.

`.agent/WORKSPACE_ISSUES.json` is a separate CAS-protected process/tool ledger.
It is not a shadow reconstruction tracker; stage blockers remain in
`RECONSTRUCTION_PROGRESS.json`.
