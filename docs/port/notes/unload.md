# boot-unload notes (2026-11-07, socom-port-unload)

Scratch for the menu/load-state teardown. Untracked. Tools: dx.ps1/dis.sh/disx.py (annotated ELF asm),
dg.sh (several functions into one file), calltree.py (jal call tree + port status), sym.py/syms.txt,
xref.py, status.py, dw.py (DWARF layouts), fake.sh (fake-pad build), diag.sh + diag.cpp (TEST HOOK:
asset list, world/grid stats, GS buffers, character sets at CameraZoom::AttachSeal and RenderWorld frames
3/300; optional enemy skip with DIAG_SKIP_ENEMIES), mkexport.sh + head.tar + mine.txt (build HEAD plus only
this worker's files in ~/.cache/socom/src-*, so other workers' in-progress edits cannot break a test),
build2-5.sh (variant builds used for the render bisect).

## Result (u4.log, fake pad, default configuration, all characters)
- menu peak use 17.94 MB (brk 0x15aa000); UnloadTheWorld -4.65 MB, whole CMenuState::UnInit -5.95 MB
  -> 11.99 MB; m8 world 19.71 MB; 41 vehicle entries (30 created, 11 recycle/disabled entries skipped by
  the game's own LoadVehicles) -> testLoad end 22.69 MB (brk 0x19b1000, 6.2 MB below heap end 0x1fdf000);
  CLoadState::UnInit -0.87 MB; in mission 21.94 MB. Before: out of heap at the ~18th character.
- Screenshots: u4-20 menu, u4-31 briefing, u4-42 load screen, u4-58 first in-mission view (textured
  terrain, lit player).

## Bugs found on the way
- GetLoadedLibRef revived a recycled library without taking it out of the bin, then emptied the bin
  (deleted it): first SwitchMenu after ReleaseLibRef became real corrupted the menu. Rewritten from 0x2307a0
  (also push_back, as the ELF; the port had push_front).
- ActionItem: libstdc++ vector copy-constructs (shallow) where MSL assigns; with ~ActionItem freeing the
  strings that double-freed. Port-only copy constructor (operator= semantics) under SOCOM_PORT.
- CNode ctor never cleared m_character (bit 2 of +0x9a): with freed memory reused, terrain nodes came out
  as characters and RenderNode skipped them (missing ground). Fixed from 0x2285c0 (also m_flatten 1,
  m_customGlobalLight -1 as the ELF).
- Base "render 23 vs 13" bisect: lib order (v1) was not it; m_character was.

## Not written (reached)
CUIVarManager::CollectGarbage (+_Refresh, CSTable::Clear, zrdr_pack/relocate), InvalidateSkbsDisplay,
CMPEG::End chain (only with a running MPEG), CVisual::DereferenceDecals / CMeshDecal (no decals yet),
~CClutterAnimManager (never created in the port), CBeachBall::Uninit (m_init has no source owner),
CCoreState::Unload (abort path only).

## Follow-up: no scheduler tasks in the mission (HEAD 4900309)
- Cause: CHUD::PauseGame (0x3ba040) reads m_pausetest.m_on (+0x14038). Nothing initialises it in the ELF
  (CZPauseTest ctor 0x3bf5b0, CHUD ctor 0x3bc180, CZPauseTest::Init/ReInit: only On/Off 0x3be7c0/0x3be7b0
  store it). CHUD is a plain new (0x17d314). Before the unload work the 84 KB CHUD came from fresh, zeroed
  sbrk memory; now it lands in freed menu memory, m_on != 0, CCoreState::Tick skips zTaskScheduler.Tick.
  None of the scheduler/menu clears touch zTaskScheduler after CCoreState::Init (ELF callers of
  CSched_Manager::Clear: StartEngine/StopEngine/zUISchedulerClear only).
- Fix: port guard m_on = false in the CZPauseTest ctor (src/Apps/FTS/hud/hud_pausemenu.cpp, HUD worker's file).
- Evidence: build-move.sh (HEAD + that file only, parent's stick script), mv1.log: TASK lines for frames 1-2
  (17 tasks), eye 2270 58 4748 -> 2048 80 4526 -> 1821 59 4299 ...; mv1-74.png.
