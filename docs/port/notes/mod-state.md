# boot-mod-state notes (2026-11-14, socom-port-mod-state): completing the game-state code

Scratch `build/port/boot-mod-state/` (untracked). Changed files: `mine.txt` (`src/Apps/FTS/state/*`, small in-place
edits in zFTS / zNetwork / zSeal and the `state` test hook, listed below, and this note); edits of zAnim files (owned by
the zAnim worker): `shared.txt` + `edits/`.

## State
- `survey.py Apps/FTS/state`: 0 stubs (25.4 KB written; 18 stubs / 7.7 KB at the start, plus the multiplayer exit state
  whose fenced bodies were empty, and the network parts of `CLoadState::Init` / `Tick` marked `port: not written`).
  No `port: stub` / `port: not written` marker is left in the folder.
- Single-player transitions run (menus -> load -> core -> cinematic -> core -> exit -> menus, four times). The
  multiplayer code (CMPExitState, the e3config table, the load state's network branches) is written from the ELF and
  untested (no network game offline).
- Known problems investigated: both are one heap problem, see "Menu hang and emulator shutdown". Three port leaks
  that caused it were fixed; a fourth (zUI design specs) remains, so the fourth return to the menus still runs out of
  contiguous memory in the briefing.
- Default build (`default.sh`, no hooks): main menu at 16 s, attract screen at 45 s.
- Screenshots (untracked): `build/port/screenshots/43-state/`.

## Written (ELF addresses)
- `st_core.cpp`: `~CCoreState` 0x17d670 (nothing of its own).
- `st_exit.cpp`: `CEntityItr::GetSeal` 0x320a60, `Advance` 0x320a90 (DWARF members `_it`, `_iIdx` in `state.h`).
- `st_load.cpp`: `CE3MissionPlayers::Parse` 0x37dbf0, `CE3Config::Parse` 0x37e080 (DWARF layouts: 16 type / 16 name
  strings, seals 0-7, terrorists 8-15, game type, time, rounds; `map<CSaferStr, CE3MissionPlayers>`),
  `CLoadState::AbortLoad` 0x37e560, `~CLoadMenu` 0x37e6e0, `~CLoadState` 0x37f7b0; `Init` 0x37f550 and `Tick` 0x37e940
  network parts (net error handler, bomb, round flags; client count, host takes type / time / rounds from e3config,
  "WAITING" / "HOST SELECTING MISSION", seal init, start flag, late joiner / ghost / lobby / net-error paths, fade-out
  gated by `m_bdown`).
- `st_menu.cpp`: `RunEventAnim` 0x3788c0, `OnPop` 0x378e10, `OnPush` 0x379230, `SetSkipMenu` 0x3793d0;
  `ActionItem::GetEvent` 0x378e70 (inline, emitted here) as a file-local function.
- `st_mpexit.cpp` (whole file): `CMPExitState` ctor 0x3dd2e0, `Init` 0x3dcee0, `Tick` 0x3dcc60, `UnInit` 0x3dca90,
  `LoadLibs` 0x3dca80; `TickMpStats` 0x3dd3c0, `SetStatLbUiVar` 0x3dd5a0, `SetMpStatUiVars` 0x3dd820,
  `SetFinalTeamTotalsUiVar` 0x3dded0, `CompareSeals` 0x3de070; members emitted here: `CMPExitMenu` (DWARF, 2208 bytes,
  `GetReaderFileName` 0x3de100), `CSealStats::GetBasesDestroyed` / `GetRescues` / `GetHitPct` 0x3de0b0..0x3de0d0,
  `CZSealBody::GetGameStats` / `GetRoundStats` 0x3ddeb0 / 0x3ddec0, `CNetClock::GetTimeInGameSec` /
  `GetTimeInRoundSec` 0x3dde10 / 0x3dde60.
- Outside the folder (in place, free at HEAD): `fts_state.h` (`CMPExitState::m_menu` is `CMPExitMenu*`, DWARF);
  `znet.h` / `zNetMedius.cpp` (`CZOnlineLobby::GetDMEJoinedCount` 0x322470 returns `dme_joined_count`; the CNetClock
  getters; `CMPExitState` friend of `CZNetVoice` for `m_block_talk`); `zseal.h` (the two stats getters);
  `fts_mission.cpp` (objective anchors, below); `seal_body.cpp` (`~CObjAnims`, below).

## Menu hang and emulator shutdown (the two known problems)
- Reproduced with `port/test-hooks/state` (menus -> m8 -> pause ABORT -> debrief TRIANGLE -> briefing -> m8 -> fatal
  fall -> debrief -> ..., four missions, then idle). Before the fixes the second return failed: after the mission's
  unload 14.8 MB were free but no hole held the 2.6 MB archive buffer (`zar_main.cpp:394`, `ui/assetlib/ui2d`) that
  `CGameMenu::LoadFromDesign` loads right after `Clear()`: `memalign` returned NULL, `zVid_Assert` does not stop, and the
  game died; on an idle menu the same happens when the attract dialog (dlgHype) loads its libraries, and then PCSX2
  closes by itself ("PCSX2 exited before 450 s" in the run report).
- It is not the demo's own behaviour: the ELF never calls `LoadExecPS2` / `ExecPS2`, and `exit` only on a failed
  mission load and in the seal constructor; the ELF's `malloc` is the same newlib allocator as the port's
  (`malloc_extend_top`, `_malloc_r`), so its heap behaves the same way. The cause is port leaks: small blocks made during
  a mission that survive its unload stay between the freed mission memory and split it (a heap walk at the menus' world
  load lists them with their allocation sites).
- Fixed from the ELF:
  - `CZBodyAnimBlend` had no destructor: the ELF's `RTArray<CZBodyAnimBlend>` dtor 0x1e4190 deletes each blend's
    REFPT_INFO and anim list (~370 blocks a mission). `edits/e_blend_dtor.txt` (zanim.h).
  - `CZAnim::Unload` 0x1c8b80 deletes the nodes the anim made (`created_here`), the health record (+0x28) and the
    instance node (+0x34) (~45 XRef nodes + names + ~30 records a mission). `edits/e_zanim_unload.txt` (zanim_anim.cpp).
  - `~CObjAnims` 0x27d560 was empty: each seal's gear entries (AddItem's OBJ_ANIM) leaked. Written in seal_body.cpp.
  - Found on the way: `CMission::Close` (0x1f75e4) and `ReOpen_Unload1` (0x1f7cac) never emptied `m_objanchor_vec`, so
    `TickObjectives` read the previous mission's freed objective cams (a TLB miss in `IsComplete` once a second from the
    third mission on). Both loops written in fts_mission.cpp.
- Result (r11, all fixes): four missions and four returns (in use 17.35..17.40 MB at each return, +45 KB a trip; the
  largest free block at the menus 2.4 -> 1.7 -> 0.6 MB); the briefing after the fourth return still fails a 634 KB
  archive buffer. Was: failed at the second return.
- Left (largest remaining pins): the dialog designs' object specs. `CDesignDlgObj`'s dtor (0x395250: deletes `m_spec`)
  and `operator=` (0x3951b0: deletes the old spec, copies the other's with the spec's `Copy`, vtable +0xc) are empty
  stubs in zui_spec.cpp, so every design read (each menu switch, the debrief) leaks its specs (`GetObjectSpec`,
  `CTextSpec`, `CGameDlgDesign::LoadFromRdr` vectors). Writing the dtor alone would double-free the copies libstdc++
  makes with the implicit copy constructor: it needs a copy constructor that copies the spec, and the spec `Copy`
  functions (unwritten). zUI work for the zUI owner. Smaller ones: `CAiMap::read_readers`, the GS texture buffer names
  (ztex_manager.cpp `SetupBuffer`), `zui_cleanup.cpp:254`, `CAiState::Create`.

## Runs (HEAD 193e49fd + mine + edit files unless noted)
- r1 (920f54c4): m1 ABORT, m2 fall, m3 ABORT, then the briefing hung at 268 s (634 KB request, 10.1 MB free); TLB
  misses in `IsComplete` during m3. r2: the 2.6 MB `ui2d` buffer failed at the second return (189 s).
- r4-r10, r12 (`HLEAK=1 build.sh ... -- -DSOCOM_HOOK_LEAK -DSOCOM_HLEAK_MIN=1 -DSOCOM_HLEAK_SLOTS=131072`): leak lists
  and heap walks at `LoadWorld("ui")` after a mission.
- r11 (`build.sh` + `-DSOCOM_HOOK_MALLOC`, all fixes): boot -> m1 ABORT -> menus (110 s) -> m2 fall -> menus (181 s) ->
  m3 ABORT -> menus (248 s) -> m4 fall -> menus (329 s) -> briefing allocation fails. No STOP, no TLB miss.
- def1 (`default.sh`): main menu 16 s, attract 45 s.

## ELF quirks kept
- `CMenuState::OnPop` calls `RestartBackgroundMPEG` before testing the menu for NULL; `RunEventAnim` / GetEvent treat
  ONSTART like an unknown name (0, nothing runs).
- `CE3MissionPlayers::Parse`: "random" stores the low byte of `rand() * 7`; player lists are not bounded by the 8 slots.
- `CLoadState::Tick` (network): `OnSealTeam` is called once and its result dropped; the host writes the game time into
  the saved maximum only while the maximum is 0.
- `CMPExitState::Init`: the net game is NULL-tested for the round winner only; a winner that is neither 0 nor 8 counts a
  tie; the hit share is hits / shots without a zero test.

## Port deviations
- `CMenuState::RunEventAnim` returns 1 when the event is known (the ELF returns `CGameMenu::RunEventAnim`'s result,
  declared void in the port's zgame.h; the memory-card callers ignore it).
- `CE3Config::Parse`, the MP list walks (`SetStatLbUiVar`, `SetFinalTeamTotalsUiVar`, `SetMpStatUiVars`, `TickMpStats`,
  `Init`'s seal loop): NULL tests where the ELF reads through the first entry without a type test.
- File-local helpers (not ELF functions): `ShowLoadBitmaps` (st_load.cpp), `FormatClock` (st_mpexit.cpp), `GetMenuEvent`
  (the inline `ActionItem::GetEvent`).
- `CEntityItr` got an inline constructor (built inline by its users in the ELF).

## Test hook
`port/test-hooks/state/` (`hook_state.cpp`, `build.sh`, `pad_idle.txt`): drives the pad from the top state and the
open dialog (`m_ReaderName`), skips the intro movie with CROSS and the briefing cameras with X, odd missions pause ABORT,
even missions the real fatal fall, debrief TRIANGLE; stops after `SOCOM_HOOK_MISSIONS` (4) and idles. Heap figures and
the largest free block at every state / dialog change. `-DSOCOM_HOOK_MALLOC`: failed and break-growing requests with
their file:line. `HLEAK=1` + `-DSOCOM_HOOK_LEAK`: with `death/hook_leak.cpp` (now `SOCOM_HLEAK_MIN`,
`SOCOM_HLEAK_SLOTS`, a per-MB histogram and `socom_hleak_tag`), the survivors and a newlib heap walk (free chunks of
256 KB+, what lies between them by allocation site, XRef nodes by creator) when the menus load their world.

## Not written / next
- zUI: `CDesignDlgObj` dtor / `operator=` / copy and the spec `Copy` functions (the remaining fragmentation; see above).
- The light-map part of `CZAnim::Unload` (0x1c8d00) and the rest of that function beyond the three leaks (in the edit
  file's comment).
