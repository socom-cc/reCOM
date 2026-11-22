# Holding files, steps 3 and 4: the user's decisions for the last 72 entries (2026-11-22)

After steps 1 and 2 ([holding-step1.md](holding-step1.md), [holding-step2.md](holding-step2.md))
14 holding files held 72 definitions: the survey's LIKELY and GUESS groups. The user went through
them and accepted the proposed owner of every one. The decisions are recorded in
`docs/reconstruction/decisions/stage4-function-placements.md` (functions, rows 1-18 and 72 of the
review) and the new `docs/reconstruction/decisions/stage4-data-placements.md` (data, rows 19-71).
Row 5 and rows 49-72 are owners the user accepted on a guess and are marked so.

## What the decisions were

- Fourteen inline functions into their class headers (rows 1-5, 7-15).
- `CBatchRelocator::AddToBatch` into `ztex_manager.cpp` (row 6); the three `C2DString::Load`
  overloads into `c2dstring.cpp` (rows 16-18).
- Thirty static data members into the file that holds their class's other members: `CTexture`'s
  into `ztex_main.cpp`, `CVideo`'s into `zvid_video.cpp`, the 22 `CBench` ones into
  `zsys_bench.cpp`, `__HeapSize` into `zsys_memory.cpp`, `ai::do_aimap_collide` into
  `seal_ai.cpp` (rows 19-48).
- Guesses: `zSys` into `zsys_init.cpp`, the seven `C2D` statics into `ztwod_init.cpp`,
  `CZAnimMain::m_LoadFromZAR` into `zanim_load.cpp`, the 14 zWeapon statics into
  `zwep_global.cpp`, and `CSTable::CSTable()` kept, in `util_stable.cpp` (rows 49-72).

## What was carried out: held plan holding-decided-3

`build/order-plans/held/holding-decided-3.json` (canonical sha256 32fc4329...cb4b; 18 rows),
planned by `socom-amend-planner-h1`, applied by `socom-held-worker-w1`, accepted by
`socom-held-verifier-v1` on the skeleton prepare and on the applies of segments 041 and 042
(tracker revisions 4663 to 4678).

- 13 inline copies moved into their headers: one each into `zai.h`, `zar.h`, `node_world.h`,
  `znode.h`, `zrdr.h`, `zui.h`, `zvalve.h`, two into `ztwod.h`, four into `util_systemio.h`.
  Three fence names were corrected to the ELF's symbols (`GetBBox` const, `GetTexHandle` with
  `const char*`, `CValve::Set` with an unsigned argument).
- `AddToBatch` (0x2f9b20) moved into `ztex_manager.cpp`. The render places it before `ClearAll`,
  while the ELF has it after (0x2f9ab0, 0x2f9b20, 0x2f9b70): the held route sorts moved entries by
  their old line, and the order of compiler copies is left to a later stage. Recorded as a lead.
- `CSTable::CSTable()` moved into `util_stable.cpp`. It is not in the ELF, and the port does not
  link without it: the static initialisers of six files default-construct a `CSTable`.
- Rows 16-18 turned out to be dead: the held overloads took the port's own font type, had no ELF
  symbol and no caller, and `c2dstring.cpp` already holds the ELF's three overloads (0x3022e0,
  0x3023a0, 0x302480). They are retired, not moved.
- Six holding files deleted: `zarchive`, `znode`, `zreader`, `zui`, `zutil`, `zvalve`.
- Two headers needed their declaration regions in another order than the render's, because a
  class holds another by value: `zui.h` (`CPopUpDialog` after `CWrappedText`) and `zai.h`
  (`CAiMapLoc` before `CAiMap`). The tool rule that allows this in a header resolution was added
  in 7d4a90bc; both reorders are recorded and are leads for correcting the rendered order.

## What is not carried out

- The 53 data members (rows 19-71) have no resolved owner row in stage 4 (deferral
  data-link-order). Placing them needs a stage-4 owner amendment: ten revised plans are drafted
  in `build/source-plans/socom-amend-planner-h1/final/`, and the sequence is in
  `build/port/boot-holding-3/NOTES-step4.md`. One of them (data-bss) forces a re-plan of the
  function order across the tree, about 12 to 14 agent sessions in all. Whether and when to run
  it is the user's choice; until then the data stays in the eight remaining holding files.
- Row 1, `CEntity::IsAlive`, needs a header-emit row for `zentity.h` in segment 031 first and
  goes with that amendment (held plan `holding-decided-4.json` is drafted for afterwards).
- Row 66's fence spells `m_bulletPassSound`; the ELF has `m_bulletpassSound`.

## Checks

Default port build links (0 undefined, 0 multiple definitions). `order skeleton` apply-check on
the three items, `audit docblocks`, `audit source-trace`, `audit source-baseline --strict`,
`guard provider`, `progress audit --strict` and `source placements check` pass; the reference
census was rewritten after the deletions.
