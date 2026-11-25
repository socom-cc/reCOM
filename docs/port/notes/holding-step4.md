# Holding files, last step: the stage-4 amendment wave for the data members (2026-11-24)

After [holding-step3.md](holding-step3.md) eight holding files were left, holding 53 static data
members and the inline `CEntity::IsAlive`. Their owners were decided by the user but had no
resolved owner row in stage 4, so placing them needed a real owner amendment. The user chose to
run all ten drafted amendments as one wave. With it no `*holding*` file is left under `src/`.

## A decision that changed

The 14 zWeapon statics (rows 58-71) were first placed in `zwep_global.cpp`. The independent
scrutinizer found the evidence favours `zwep_weapon.cpp`, and that the reason given to the user
had been wrong (`zwep_weaponlist.cpp`, not `zwep_global.cpp`, is the first zWeapon unit in
`.text`). The user changed the decision on 2026-11-24: all 14 go to `zwep_weapon.cpp`.
`docs/reconstruction/decisions/stage4-data-placements.md` records it, with its earlier
revisions under `history/`. They stay marked as owners accepted on a guess: `CZProjectile` also
reads `personMaterialId` and `m_timer_pCurval`, and no `zwep_weapon.cpp` code reads
`m_allowFireAnimations`, `m_allowImpactAnimations` or `m_allowWeaponIntersection`.

## Stage 4

Amendments 033 to 042 (tracker revisions 4678 to 4921):

| Amendment | Plan | Places |
|---|---|---|
| 033 | segment 031 | the header-emit row for `CEntity::IsAlive` (0x25ab70) in `zentity.h` |
| 034 | data-bss | 26 zero-initialised statics (rows 19, 21, 25-30, 32-41, 48, 49, 51, 53, 57, 64, 65, 67) |
| 035 | data-data | 4 initialised statics (rows 31, 59-61) |
| 036 | segment 013 | `CVideo::m_defaultFrameRate` |
| 037 | segment 039 | `CBench::dmaTime`, `__HeapSize` |
| 038 | segment 040 | `CTexture::m_startAddress` |
| 039 | segment 041 | five `C2D` statics |
| 040 | segment 042 | `CVideo::m_maxFrameRate`, `m_brightness` |
| 041 | segment 044 | eight zWeapon statics |
| 042 | segment 065 | four `CBench` particle counters |

- Plans by `socom-amend-planner-h1`. The scrutinizer `socom-amend-scrutinizer-s1` accepted four
  at once and sent four back: three reserved directories they did not need, with a false reason
  (a fault in the planner's generator), and one misstated the DWARF evidence for `zentity.h`.
  All ten were accepted after revision.
- 44 marked segment applies re-applied by `socom-wave-worker-a` and `-b`; nine changed files, and
  only by generated annotation lines (84 added, none removed). Accepted by
  `socom-wave-verifier-v2`, who confirmed that each of the 53 data addresses and 0x25ab70 is
  defined or emitted in exactly the file the user decided.
- The acceptance of the ten amendments was run by the user (the permission system does not let
  an agent run it), recording the verifier's review; the live Ghidra receipt was unchanged.

How strong the evidence is, by the scrutinizer: it supports the `CBench` statics read by
`CBench::Reset`, `__HeapSize`, `CTexture::m_startAddress`, `CVideo::m_brightness` and three of
the zWeapon pointers; it only permits most of the rest (their readers sit in files that link
order rules out); for the `C2D` statics it mildly favours the user's `ztwod_init.cpp`; for
`ai::do_aimap_collide` it is mixed (read only in `seal.cpp`).

## Stage 5

- `progress rebase-function-order` (4922); the link-order plan and 45 function-order plans
  re-drafted by `socom-order-planner-p1` / `-p2` and accepted by `socom-order-reviewer-r1` (to
  5060). No unit's function order changed; the link order is the same 643 objects. Eight plans
  gained rows for the new data. `zsys_bench.cpp` is now planned in segment 065 instead of 039
  (the unit goes to the segment holding most of its rows); its link position and its function's
  position are unchanged.
- Skeleton prepare and 45 segment applies re-applied by `socom-skel-worker-k1`, accepted by
  `socom-skel-verifier-kv` (to 5244). Held plan `holding-decided-4` rode on the prepare: it moved
  `CEntity::IsAlive` into `zentity.h` and retired two misspelt held fences
  (`m_bulletPassSound__8CZWeapon`, `_HeapSize`).
- The 53 data members are each defined once, in their owner file, with the port's type and
  initial value. `m_bulletPassSound` is spelt `m_bulletpassSound`, as the ELF has it, in
  `zweapon.h` and the two accessors of `zwep_weapon.cpp`; no other function body changed.
- 38 fences in other files became port comments with their code kept. They are compiler copies
  (37 binding-13 copies, one local implicit destructor) that the port lane had fenced itself and
  that no render ever placed; the documented carry rule for unowned port fences applies now
  because those files were re-applied for the first time since. The list is in
  `build/port/boot-wave-sv/portfences.json`.

## Leads

- The five `CSealCtrlAi` statics at 0x475d54-0x475d64 (`aiActiveCount`, `aiSleepingCount`,
  `aiSnoozingCount`, `diCount`, `aiDebugEnabled`) lie inside `seal_ai.cpp`'s `.sbss` run now that
  `do_aimap_collide` is placed there; stage 4 still leaves them unresolved.
- `CBatchRelocator::AddToBatch` sits before `ClearAll` in `ztex_manager.cpp`; the ELF has it after.
- In `zai.h`'s recorded region reorder, `CAiCell` did not need to move.

All three were settled on 2026-11-25, see [holding-step5.md](holding-step5.md). The third one was
wrong: `CAiCell` does have to come before `CAiMap`.

## Checks

Default port build links (0 undefined, 0 multiple definitions), also in the verifier's own
build. `order skeleton` apply-check on all 46 items, `audit docblocks`, `audit source-trace`,
`audit source-baseline --strict`, `guard provider`, `progress audit --strict` pass; the reference
census was rewritten.
