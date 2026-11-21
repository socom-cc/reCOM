# Holding files, step 2: the first held plan (2026-11-21)

Step 1 ([holding-step1.md](holding-step1.md)) deleted the dead and unused definitions but had to
leave their skeleton fences. The held-plan route added in 9fe3e56d (`order skeleton held-check` /
`held-decide`, described in `docs/reconstruction/FUNCTION_ORDER.md`) retires such fences and moves
inline copies to their owners. This note records its first use.

## The plan

`build/stage5/held-plans/holding-proven-1.json` (canonical sha256 6c09cc6c...8cd5; the plan file
itself is generated and not tracked): 85 rows, every one classed PROVEN.

- 75 retirements: 40 `duplicate` (the live definition sits in a real source file) and 35
  `no-elf-symbol`.
- 10 moves, all Metrowerks binding-13 inline copies, each into the file stage 4's annotations
  name:
  - `CTextureRelocMgr::ClearAll` (0x2f9ab0), `CBatchRelocator::EndBatchReloc` (0x2f9b70) and
    `StartBatchReloc` (0x2f9ca0) into `src/gamez/zTexture/ztex_manager.cpp`; the last two are the
    user's placements, with their fence names corrected to the ELF's `...CFv` symbols.
  - four C2D functions into `src/gamez/zTwoD/ztwod.h`.
  - `CNode::SetActive` into `src/gamez/zNode/znode.h`, `CEntity::GetEntityList` into
    `src/gamez/zEntity/zentity.h`, the `CMenuState` constructor into `src/gamez/zFTS/fts_state.h`.

## What it changed

- 13 holding files deleted: the 12 that step 1 had emptied and `state_holding.cpp`. 17 remain.
- 75 fences retired; 69 entries are still held (plus 21 definitions outside any fence).
- The moved bodies are the port's text, unchanged apart from the `inline` the render adds in a
  header. Two headers conflicted with port-lane edits before their `#endif` (`znode.h`,
  `zentity.h`); both resolutions keep the port's lines and the moved entry.

## Who did what

Plan and apply: `socom-held-worker-w1`. Reopening of the skeleton prepare and of segment 041's
apply: the coordinator. Independent review and acceptance of both: `socom-held-verifier-v1`, who
checked every retirement against the ELF's symbols and every move against stage 4's owner rows.
Tracker revisions 4648 to 4658.

The verifier doubts four reason labels; the outcome is the same, since a retirement drops the
entry either way:

- `m_modelToWorld`: the ELF has `m_ModelToWorld`, so it is a misspelt duplicate, not
  `no-elf-symbol`.
- `buffer`: the ELF has a `buffer`, but as a size-0 local label inside a gap, not an object.
- `IsString` and `GetType`: labelled duplicates, but the ELF has neither symbol.

## Left for the stage-4 amendment route

The held-plan route does not move ordinary functions or data. Of the survey's PROVEN entries
these still wait: the 16 file-local data objects (`is_init` in `bone_init.cpp`, six in
`zmpeg.cpp`, nine in `zNetMedius.cpp`), `LoadDlgObjects` (a file-local function, 0x39a9f0) and
`PTT_HeartbeatPrepare` (provider code, 0x3f02c0). The LIKELY and GUESS entries have not been
decided.

Tool gap found: `held-check` lets a data entry through as code with no ELF symbol, although the
route's rules refuse all data; the worker left the data rows out by hand.

## Checks

Default port build links (0 undefined, 0 multiple definitions). `order skeleton` apply-check,
`audit docblocks`, `audit source-trace` and `progress audit --strict` pass; the reference census
was rewritten after the file deletions.
