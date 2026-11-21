# Holding files, step 1: the provably dead deleted (2026-11-21)

Worker `socom-holding-1`, branch `audit-medium` from `caadcb73`. Inputs: the survey sheet
`build/stage4/owner-decisions/holding-2026-11-20.md` and its records
`build/port/boot-holding-survey/NOTES.md`. No live definition moved to another file (a later step).

## What was deleted

75 definitions in 19 holding files, plus 10 declarations in 7 headers:

- (a) 60 dead copies (`#if 0` text), each checked first: the block is closed with no top-level
  `#else`, and its replacement exists outside any `#if 0` (or it has none: not in the ELF).
- (b) 14 port-only leftovers: no ELF symbol (`.symtab`) and no user in `src/` or `port/`. Their
  header declarations went too.
- (c) `CGameMenu::Draw2DOnly`, a compiled duplicate. The ELF has only `Draw2dOnly__9CGameMenuFv`
  (0x383550, 68 bytes), defined in `src/gamez/zUI/zui.cpp`. Its declaration in `zgame.h` went too.

| holding file | (a) | (b) | (c) | definitions left |
| --- | ---: | ---: | ---: | ---: |
| `Apps/FTS/hud/hud_holding.cpp` | | 2 | | 0 |
| `gamez/zAnim/zanim_holding.cpp` | 1 | | | 1 |
| `gamez/zArchive/zarchive_holding.cpp` | 3 | | | 1 |
| `gamez/zCamera/zcamera_holding.cpp` | 2 | | | 0 |
| `gamez/zCharacter/zcharacter_holding.cpp` | | 1 | | 0 |
| `gamez/zFTS/zfts_holding.cpp` | 6 | | | 0 |
| `gamez/zGame/zgame_holding.cpp` | | | 1 | 0 |
| `gamez/zMath/zmath_holding.cpp` | 13 | | | 0 |
| `gamez/zNode/znode_holding.cpp` | 3 | | | 3 |
| `gamez/zReader/zreader_holding.cpp` | 10 | | | 1 |
| `gamez/zRender/zrender_holding.cpp` | 3 | | | 0 |
| `gamez/zSeal/zseal_holding.cpp` | 2 | 3 | | 0 |
| `gamez/zSound/zsound_holding.cpp` | 2 | 3 | | 0 |
| `gamez/zSystem/zsystem_holding.cpp` | 10 | | | 9 fenced + 15 unfenced |
| `gamez/zUtil/zutil_holding.cpp` | | 1 | | 5 |
| `gamez/zVehicle/zvehicle_holding.cpp` | | 1 | | 0 |
| `gamez/zVideo/zvideo_holding.cpp` | | 3 | | 1 fenced + 2 unfenced |
| `gamez/zVisual/zvisual_holding.cpp` | 4 | | | 0 |
| `posix/posix_holding.cpp` | 1 | | | 0 |
| **total** | **60** | **14** | **1** | |

The other 11 holding files are unchanged.

By fence name:

- (a) zanim: `_local_wildcard_ptr`. zarchive: `Write__Q23zar4CKeyFPQ23zar4CZARP7__sFILE`,
  `ReadDirectory_V2__Q23zar4CZARFiUi`, `WriteDirectory__Q23zar4CZARFP7__sFILE`. zcamera: `peekCur`,
  `GetFirstPersonCameraPos__FP10CAppCamera`. zfts: `g_arrDefCharTypeNames`, `g_iNumUiVehicles`,
  `UpdateMissionArchive__FPCcPCc`, `CreateCustomCharTypes__FP11CVehicleRdrP5_zrdr`,
  `CreateCustomCharTypes__FP5_zrdr`, `LoadMissionMapVisibilities__FP5_zrdr`. zmath:
  `MakeYXZ__5CQuatFfffR5CQuat`, `__ct__7CMatrixFv`, `__vc__7CMatrixFi`, `GetTranslate__7CMatrixCFv`,
  `Transform__7CMatrixFP6CPnt3Di`, `Multiply__7CMatrixFPC7CMatrixPC7CMatrix`,
  `Cross__6CPnt3DFPC6CPnt3DP6CPnt3Db`, `zMathCopyVector`, `zMathAddVector`, `zMathSubVector`,
  `zMathUnitMatrix`, `zMathCopyMatrix`, `zMathMulMatrix`. znode: `g_assetsRecycle__3zdb`,
  `numNodes__3zdb`, `Reset__Q23zdb5CWindFv`. zreader: `buffer`, `zrdr_init`, `warnonce`,
  `IsArray__5_zrdrCFv`, `IsString__5_zrdrCFv`, `GetInt__5_zrdrCFv`, `GetType__5_zrdrCFv`,
  `Get__5_zrdrCFi`, `defcount`, `init`. zrender: `Add__6CAlpha...`,
  `Read__11CLOD_ObjectFPQ23zdb9CSaveLoad`, `bilinearDistance`. zseal:
  `m_crawl1stperson_amplitude__9CSealCtrl`, `m_crawl1stperson_rate__9CSealCtrl`. zsound:
  `g_iReverbTime`, `sound_rdr`. zsystem: `postinit`, `__malloc__FUiPCci`, `__calloc__FUiUiPCci`,
  `__realloc__FPvUiPCci`, `__memalign__FUiUiPCci`, `__strdup__FPCcPCci`, `__free__FPvPCci`,
  `zsysSprGetPacket__FP8_word128`, `zsys_AllocScratchpad__Fv`, `Print__4CTTYFPcUi`. zvisual:
  `m_modelToWorld__Q23zdb7CVisual`, `m_instance_count__Q23zdb8CVisBase`, `__ct__Q23zdb8CVisBaseFUi`,
  `__ct__Q23zdb8CSubMeshFv`. posix: `unparsed:src/posix/strcasecmp.cpp:37` (newlib provider).
- (b) `tacmap_polys`, `tacmap_lines`, `CCharacterType::CCharacterType()`, `seal_init`,
  `CTSelect::Begin`, `CTSelect::End`, `CSnd::m_snd_data`, `CSnd::m_snd_len`, `CSnd::m_soundmap`,
  `dumpLog`, `_dest`, `lastRenderTime`, `curRenderTime`, `theWindow`. Declarations removed:
  `zchar.h` (`CCharacterType();`), `zseal.h` (`CTSelect::Begin`/`End`), `zsnd.h` (the three
  statics), `zutil.h` (`extern bool dumpLog`), `zvehicle.h` (`extern ... _dest`), `zvid.h`
  (`extern CWindow* theWindow`). `tacmap_*`, `seal_init`, `lastRenderTime` and `curRenderTime` had
  no declaration. `gopt.dumpLog` (a member of the options struct) is another object and stays.
- (c) `Draw2DOnly__9CGameMenuFv`; `zgame.h` loses `void Draw2DOnly();`.

## How an entry was deleted: the fence lines stay

Every one of the 75 definitions sits in a stage 5 skeleton fence (`/* @socom-skeleton body ... */`)
of the accepted prepare item `socom:work:order-skeleton-prepare`. None has a stage 4 annotation:
the holding files have no stage 4 block, and the header lines removed lie outside every
`@socom-skeleton decl ... end` region.

Each entry keeps its fence line and its `/* held from ... */` line. Its definition, `#if 0`
wrapper and old port comment became one line, `/* port: deleted (...): <reason> */`. Why:

- **Inside a fence:** the text is the port lane's. `order skeleton apply-check` reports an edited
  file as drift, never as a failure. A re-apply whose render of the file is unchanged keeps the
  live file (`kept`).
- **The fence lines:** they belong to the render. A merged or resolved re-apply must keep the
  render's fence lines (`order_skeleton_merge.check_merged`: "its @socom-skeleton fence lines
  differ from the render's (a fence was dropped, added or moved)"). If a fence were deleted here,
  the first re-apply that changes the file's render would conflict, and only by restoring the fence
  could that conflict be resolved. Step 2's moves will change these renders.
- **No route deletes a held entry:** `holding_text` (`order_skeleton_write.py`) renders every held
  body of the frozen base `build/stage5/skeleton-route/base`. Only `progress
  rebase-function-order` changes the base, and it refuses a delta that changes authored content
  (`order_reopen.py`: "<path>: its authored content changes"). No `order skeleton decide` kind
  drops a held entry.

## What was left and why

- Nothing in scope was left with its text. The 75 fence lines (plus held-from lines) stay until a
  governed route can retire held entries (see below).
- 12 holding files now hold no definition: `hud_holding`, `zcamera_holding`,
  `zcharacter_holding`, `zfts_holding`, `zgame_holding`, `zmath_holding`, `zrender_holding`,
  `zseal_holding`, `zsound_holding`, `zvehicle_holding`, `zvisual_holding` and `posix_holding`.
  They are not deleted: the prepare's render writes them, and a merge "may not delete the file the
  render writes". Their `#include` preambles are the render's and stay too.
- Stale comments outside the scope: `hud_linemap.cpp:196/216` still say `tacmap_*` "lives only in
  the unbuilt holding file". Also stale: `zsnd.h:8` `#include <unordered_map>`, which no line of that
  header uses any more (harmless).
- `CSTable::CSTable()` (port-only, kept by the survey for GCC default construction) is outside this
  step.

## Governed steps

- Taken: none needed a tracker change. `progress next --json` listed no ready item, and `progress
  work leases` none (revision 4648). No item was claimed. Nothing was handed off.
- Open: retiring the emptied fences and the 12 empty files needs a tool change, which is
  tool-maintainer work. For example: a recorded retirement of held entries that the writer reads,
  like the skeleton decisions, followed by a re-apply of the prepare, `progress
  handoff-order-skeleton` by the worker and `progress accept-order-skeleton` by an independent
  `socom-verifier`. Until then, no accepter command is pending.

## Checks (all exit 0)

- Before: `audit docblocks`, `audit source-trace`, `guard provider`, `audit independence --strict`,
  `audit docs --strict`, `progress audit --strict`; after: the same, all exit 0.
- `order skeleton apply-check --item socom:work:order-skeleton-prepare`: ok, no problem, all static
  checks pass (S1 6,285, S3 9,122 edges with the baseline digest). Drift went from 15 to 36 files:
  the 21 changed files, as expected. This needs the stage 5 inputs under `build/` (`stage5/`,
  `order-plans/`, `source-plans/`). A fresh worktree lacks them, so they were copied read-only from
  the main checkout.
- Default port build (`default.sh holding-1-default`): library 0 errors, link 0 undefined, 0
  multiple.
- `gate.ps1 -Only roundtrip -Build holding-1-gate`: PASS, 4 returns, 18,642,780 B in use, flat.
