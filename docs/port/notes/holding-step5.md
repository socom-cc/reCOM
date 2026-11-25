# Holding files, follow-up: the three leads of step 4 (2026-11-25)

[holding-step4.md](holding-step4.md) ended with three leads. The user asked for all three to be
settled: the `CSealCtrlAi` statics recorded in `seal_ai.cpp`, `CBatchRelocator::AddToBatch` put
where the ELF has it, and the `zai.h` doubt looked at.

## The CSealCtrlAi statics

The definitions were already in `seal_ai.cpp`, as unfenced port code; what was missing was the
stage-4 owner. The user chose a full amendment wave over a record-only change. While planning it
a sixth unresolved static turned up in the same file's `.sdata` run, and the user's decision
covers it too.

| Address | Member | Section | Amendment | Plan |
|---|---|---|---|---|
| 0x475d54 | `aiActiveCount` | `.sbss` | 043 | data-bss |
| 0x475d58 | `aiSleepingCount` | `.sbss` | 043 | data-bss |
| 0x475d5c | `aiSnoozingCount` | `.sbss` | 043 | data-bss |
| 0x475d60 | `diCount` | `.sbss` | 044 | segment 035 |
| 0x475d64 | `aiDebugEnabled` | `.sbss` | 043 | data-bss |
| 0x474f60 | `aiCameraRangeFilter` | `.sdata` | 045 | segment 013 |

The decision is in `docs/reconstruction/decisions/stage4-data-placements.md` (59 objects now;
earlier revisions under `history/`).

How strong the evidence is:

- The five `.sbss` members lie in one run of `CSealCtrlAi` / `ai` statics between `seal.cpp`'s
  last local and `seal_ai.cpp`'s `aiLogEnabled` (0x475d68). `seal.cpp` and `seal_ai.cpp` are
  neighbours in link order, so the binary permits either; the run continuing into
  `seal_ai.cpp`'s own statics favours `seal_ai.cpp`.
- The three counters are read by `CSealCtrlAi::PreTick` in `seal_ai.cpp`: supported.
- `diCount` is only written, by `CSealCtrlAi::PrePostTick` in `seal_sensors.cpp`; `aiDebugEnabled`
  is written by `options.cpp` and read in `seal_tasks.cpp`. Both rest on their class and on the
  run being contiguous: permitted, not proven.
- `aiCameraRangeFilter` lies strictly inside `seal_ai.cpp`'s `.sdata` run, between `aiEnabled`
  (0x474f5c) and `aiSoundHandle` (0x474f68). Its only access is a store of zero in `options.cpp`,
  which link order rules out as the owner.

`aiDebugEnabled` and `aiCameraRangeFilter` keep the port's `unsigned char` (DWARF has
`aiDebugEnabled` as `uchar`).

Three objects of the same run stay unresolved: `CZSealBody::m_oktocallinit` (0x475d44),
`ai::snooze_time` (0x475d48) and `ai::snooze_count` (0x475d4c).

### Stage 4

Tracker revisions 5244 to 5442. Plans by `socom-amend-planner-h2`. The scrutinizer
`socom-amend-scrutinizer-s2` sent two back once (the readers and writers were misstated and the
contiguity argument was missing) and accepted all three after revision. 44 marked applies
re-applied by `socom-wave2-worker-a` and `-b`: only `seal_ai.cpp` changed, by 12 generated
annotation lines. Accepted by `socom-wave2-verifier-v3`. The acceptance of the three amendments
was run by the user; the live Ghidra receipt was unchanged.

### Stage 5

`progress rebase-function-order` (5443); 45 function-order plans re-drafted by
`socom-order2-planner-p1` / `-p2` and accepted by `socom-order2-reviewer-r2` (to 5578). Only plan
031 changed: six data rows for `seal_ai.cpp`. The link-order plan was not reopened. Skeleton
prepare and 45 segment applies by `socom-skel2-worker-k2`, accepted by `socom-skel2-verifier-kv2`
(to 5762).

In `seal_ai.cpp` each of the six statics is now defined once, in its rendered entry, in ELF
address order, with the port's type and initial value (`aiCameraRangeFilter = 1`). The unfenced
port definitions they replace are removed. No function body changed.

## CBatchRelocator::AddToBatch

The held route used to sort moved entries by their old line, which left `AddToBatch` (0x2f9b20)
before `ClearAll` (0x2f9ab0). Since 466d6412 a held move into a unit file follows the ELF's
address order, and segment 041's re-apply in this wave carried it out: a 12-line move in
`ztex_manager.cpp`, text unchanged. The order is now `ClearAll`, `AddToBatch`, `EndBatchReloc`
(0x2f9b70), `StartBatchReloc` (0x2f9ca0), as in the ELF.

## zai.h: no change

The doubt was that `CAiCell` had been moved ahead of `CAiMap` without need. It is needed:
`CAiMap::IsWalkable`, an inline defined inside `CAiMap`, reads `cell->m_soil`, so `CAiCell` must
be complete first. Putting it back at its rendered position fails to compile ("invalid use of
incomplete type 'const class CAiCell'"). The ELF agrees that the inline exists: its copy sits in
`CAiMap::GetNeighbor` (0x182830). The file is unchanged. The rendered order of `zai.h` stays a
lead for correction in the render.

## Checks

Default port build links (0 undefined, 0 multiple definitions), also in the verifier's own
build. `order skeleton` apply-check on all 46 items, `audit docblocks`, `audit source-trace`,
`audit source-baseline --strict`, `guard provider` and `progress audit --strict` pass; the
reference census was rewritten and verifies.
