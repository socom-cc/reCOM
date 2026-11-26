# Stage 2: Apps/FTS/state (2026-11-26)

The one list of `Apps/FTS/state` (list a): the owner files st_core.cpp, st_menu.cpp, st_load.cpp,
st_exit.cpp and st_mpexit.cpp (release 0x17bdb0-0x17d2f0, 0x395000-0x396560, 0x39a330-0x39c330,
0x33b1f0-0x33c1f0 and 0x3fb7e0-0x3fd340). It holds 19 uncertain rows (12 removed, 2 new, 3 exact
pairs flagged `identical-copy`, 1 weak pair (`position`, `slot-only`, `caller-mismatch`), 1 unsure),
15 sampled deviating rows out of 39, and 51 exact rows that were not checked one by one. Pairing
produced by `socom-release-compare-c1` (`python tools/release/compare.py`); checked by
`socom-release-check-input-state`, who did not write the tool, at HEAD 293696c3. The check sheet
(`compare.py --sheet Apps/FTS/state --list a`) was the starting point. Both images were
disassembled with the release tools; callers were found by scanning both images for `jal`/`j`,
data words and `lui`/`addiu` pairs. Ghidra was not needed.

As the guard on the committed pairs, all 92 paired rows of the ranges had their callers and
address-loaders compared with the prototype's through the map, and their ordered calls and loads
compared for substitutions; the 17 vtables with a slot in the ranges (the eleven state and menu
classes with CCoreState and CGameMenu, and six zdb classes whose inline virtuals are emitted here) were aligned slot by
slot; the 3 functions that load the address of a state function had their pointer loads compared;
the member-pointer tables of the stat getters were read on both sides.

What settled rows, in the order it was used: the pointer-to-member tables of the CSealStats getters
(`c_arrStatFuncs`, built by `__sinit_st_mpexit.cpp`, and the records SetRoundStatUiVars loads);
the CLoadMenu vtable; the call sites in TickMpStats and SetMpStatUiVars.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x321260 `GetDeaths__10CSealStatsCFv` | removed | confirmed | used only through a member pointer of SetRoundStatUiVars; the release SetRoundStatUiVars loads two records (GetKills, NumPrimaryRoundsFired) where the prototype loaded eleven; no member pointer to such a getter is left in the release data |
| - | 0x321270 `GetTimesWasHit__10CSealStatsCFv` | removed | corrected to 0x3fce20 | see 0x3fce20 |
| - | 0x321280 `NumCQBUsed__10CSealStatsCFv` | removed | confirmed | as GetDeaths |
| - | 0x321290 `NumGrenadesUsed__10CSealStatsCFv` | removed | confirmed | as GetDeaths |
| - | 0x3212a0 `NumSecondaryRoundsFired__10CSealStatsCFv` | removed | confirmed | as GetDeaths |
| - | 0x3212c0 `NumTimesSeen__10CSealStatsCFv` | removed | confirmed | as GetDeaths |
| - | 0x3212d0 `NumRestrained__10CSealStatsCFv` | removed | confirmed | as GetDeaths |
| - | 0x3212e0 `NumStealthKills__10CSealStatsCFv` | removed | confirmed | as GetDeaths |
| - | 0x3212f0 `GetHeadShots__10CSealStatsCFv` | removed | corrected to 0x3fce60 | see 0x3fce60 |
| 0x33c1c0 | 0x321300 `GetKills__10CSealStatsCFv` | exact, identical-copy | confirmed | entry 0 of `c_arrStatFuncs` on both sides and the first record SetRoundStatUiVars loads (0x44c048 / @2541) |
| - | 0x3793d0 `SetSkipMenu__10CMenuStateFb` | removed | confirmed | its only caller, process_arguments, is removed; no copy of its three instructions in the release |
| - | 0x37f940 `MyTick__9CLoadMenuFf` | removed | confirmed | slot +0xc of the release CLoadMenu vtable holds the inherited `MyTick__9CGameMenuFf` |
| - | 0x37fa30 `PrepControls__9CLoadMenuF...` | removed | confirmed | slot +0x14 holds the inherited `PrepControls__9CGameMenuF...`; its five loading-screen bitmaps ("Menu220_loading_loadingnormal.tif" and others) are not in the release |
| 0x3fcba0 | 0x3dded0 `SetFinalTeamTotalsUiVar__23@unnamed@st_mpexit_cpp@FbPCc` | deviating (weak), position, slot-only, caller-mismatch | confirmed | the same body (CRdrEditor, the entity loop over `c_arrStatFuncs`, sprintf @3025, UI variable); its two calls moved from the end of SetMpStatUiVars to the end of TickMpStats. It now averages the hit percentage (compares the record with a static copy of the GetHitPct member pointer) |
| 0x3fce00 | 0x3de0b0 `GetBasesDestroyed__10CSealStatsCFv` | exact, identical-copy | confirmed | entry 5 of `c_arrStatFuncs` on both sides |
| 0x3fce10 | 0x3de0c0 `GetRescues__10CSealStatsCFv` | exact, identical-copy | confirmed | entry 4 |
| 0x3fce20 | - | new, copy, owner guess | corrected to 0x321270 `GetTimesWasHit__10CSealStatsCFv` | entry 3 of `c_arrStatFuncs`, where the prototype has GetTimesWasHit; the same `lw v0,0x14(a0)` |
| 0x3fce30 | 0x3de0d0 `GetHitPct__10CSealStatsCFv` | unsure, position | confirmed, deviating | entry 2 on both sides; the same `(int)(100 * x + 0.5)` on +0x28, the `fptosi` call now an inline conversion |
| 0x3fce60 | - | new, copy, owner guess | corrected to 0x3212f0 `GetHeadShots__10CSealStatsCFv` | entry 1, where the prototype has GetHeadShots; the same `lw v0,0x0(a0)` |

The two corrected getters are header inlines. In the prototype the linker kept the st_exit.cpp copy
and dropped st_mpexit.cpp's; the release st_exit.cpp no longer uses them, so the copies kept are
st_mpexit.cpp's. The release order BasesDestroyed, Rescues, TimesWasHit, HitPct, HeadShots is the
reverse of the table order, as the prototype's BasesDestroyed, Rescues, HitPct was.

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x17ccf0 | 0x17d900 `UnInit__15CCinematicStateFv` | yes | its slot of the CCinematicState vtable (8 of 8 slots align) |
| 0x17ce40 | 0x17d9d0 `Tick__15CCinematicStateFf` | yes | the same |
| 0x17cfc0 | 0x17db20 `Init__15CCinematicStateFv` | yes | the same |
| 0x395670 | 0x378db0 `__dt__14CMenuStateMenuFv` | yes | slot +0x8 of the CMenuStateMenu vtable |
| 0x3956d0 | 0x378e10 `OnPop__10CMenuStateFi` | yes | its slot of the CMenuState vtable |
| 0x39ace0 | 0x37e5a0 `UnInit__10CLoadStateFv` | yes | its slot of the CLoadState vtable |
| 0x39ae20 | 0x37e6e0 `__dt__9CLoadMenuFv` | yes | slot +0x8 of the CLoadMenu vtable; stores that vtable |
| 0x39ae80 | 0x37e940 `Tick__10CLoadStateFf` | yes | its CLoadState slot |
| 0x39b750 | 0x37f550 `Init__10CLoadStateFv` | yes | its CLoadState slot; loads the CLoadMenu vtable on both sides |
| 0x39b990 | 0x37f7b0 `__dt__10CLoadStateFv` | yes | its CLoadState slot |
| 0x3fb7f0 | 0x3dca90 `UnInit__12CMPExitStateFv` | yes | its CMPExitState slot |
| 0x3fb9d0 | 0x3dcc60 `Tick__12CMPExitStateFf` | yes | its CMPExitState slot |
| 0x3fc170 | 0x3dd3c0 `TickMpStats__23@unnamed@st_mpexit_cpp@Fv` | yes | the same 22 calls in the same order, plus the two SetFinalTeamTotalsUiVar calls |
| 0x3fc370 | 0x3dd5a0 `SetStatLbUiVar__23@unnamed@st_mpexit_cpp@F...` | yes | the same four call sites in SetMpStatUiVars |
| 0x3fcdc0 | 0x3de070 `CompareSeals__23@unnamed@st_mpexit_cpp@F...` | yes | its address is loaded by SetStatLbUiVar on both sides |

The cross-check found no wrong committed pair outside the list's rows.

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x3fce20 | 0x321270 | entry 3 of c_arrStatFuncs (__sinit_st_mpexit.cpp) on both sides; same body | socom-release-check-input-state | 2026-11-26 | src/Apps/FTS/state/st_mpexit.cpp | |
| 0x3fce60 | 0x3212f0 | entry 1 of c_arrStatFuncs on both sides; same body | socom-release-check-input-state | 2026-11-26 | src/Apps/FTS/state/st_mpexit.cpp | |
| 0x3fce30 | 0x3de0d0 | entry 2 of c_arrStatFuncs on both sides | socom-release-check-input-state | 2026-11-26 | | |
| 0x33c1c0 | 0x321300 | entry 0 of c_arrStatFuncs and the first member-pointer record of SetRoundStatUiVars on both sides | socom-release-check-input-state | 2026-11-26 | | |
| 0x3fce00 | 0x3de0b0 | entry 5 of c_arrStatFuncs on both sides | socom-release-check-input-state | 2026-11-26 | | |
| 0x3fce10 | 0x3de0c0 | entry 4 of c_arrStatFuncs on both sides | socom-release-check-input-state | 2026-11-26 | | |
| 0x3fcba0 | 0x3dded0 | same body; its two calls moved from the end of SetMpStatUiVars to the end of TickMpStats | socom-release-check-input-state | 2026-11-26 | | |

Rows that change together: 0x3fce20 with the removed 0x321270, and 0x3fce60 with the removed
0x3212f0 (one row each once paired). The owner of those two moves from st_exit.cpp (the
prototype's kept copy) to st_mpexit.cpp.

## New and removed

New in the list: none (both were the st_mpexit.cpp copies of existing getters).

Just outside the list (new, no owner; checked because the coordinator named "ShutdownState"):
two new game states, both `CGameState` subclasses by their RTTI and vtables, both constructed by
`__sinit_main.cpp` (global objects) with the CGameState name constructor of zgame.h (line 84).

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x432810 | stores the vtable 0x48c5d0, name "ShutdownState" | `__ct__14CShutdownStateFv` (RTTI "CShutdownState") |
| 0x432780 | slot +0x10: shuts down sound (0x30c310), CPipe, pads, CD (sceCdInit(5)) and SIF, then `LoadExecPS2("cdrom0:\NTGUI.ELF;1", 3, {"cdrom0:\SCUS_971.34;1", "-m", "dlgReturnFromNTGUI2.rdr"})`, or `host0:./ntguihost.elf` with `host0:./ftsd0.elf` when the flag at 0x52718d is clear | `Init__14CShutdownStateFv` (CGameState slot +0x10) |
| 0x432770, 0x432760 | `return 0`; empty | `Tick__14CShutdownStateFf`, `UnInit__14CShutdownStateFv` (slots +0x14, +0x1c) |
| 0x140980 | the destructor (slot +0x8; stores 0x48c5d0 then the CGameState table) | `__dt__14CShutdownStateFv` |
| 0x43d500 | stores the vtable 0x48c600, name "RebootState" | `__ct__12CRebootStateFv` (RTTI "CRebootState") |
| 0x43d480 | the same shutdown, then `LoadExecPS2("cdrom0:\SCUS_971.34;1", 2, {"-m", "dlgAfterReboot.rdr"})` (or `host0:./ftsd0.elf`): the game restarts itself | `Init__12CRebootStateFv` (slot +0x10) |
| 0x43d470, 0x43d460 | `return 0`; empty | `Tick__12CRebootStateFf`, `UnInit__12CRebootStateFv` |
| 0x140760 | the destructor (slot +0x8) | `__dt__12CRebootStateFv` |

So the earlier finding holds: CShutdownState hands over to NTGUI.ELF and asks it to return to
SCUS_971.34 with the dialog dlgReturnFromNTGUI2.rdr. CRebootState is its partner that reboots the
game into dlgAfterReboot.rdr. Their owners are open: the destructors sit in main.cpp's range with
the other state destructors; the other methods sit apart, before the PTT library (0x432760-0x432810)
and before libusbkb (0x43d460-0x43d500), as late objects in the link order. A guess:
`st_shutdown.cpp` and `st_reboot.cpp`, after the other st_*.cpp files.

Really removed:

- The seven CSealStats getters of the round statistics that the release no longer shows (deaths,
  CQB and grenades used, secondary rounds, times seen, restrained, stealth kills): the round screen
  now lists kills and primary rounds only.
- CMenuState::SetSkipMenu, with its caller process_arguments.
- CLoadMenu's MyTick and PrepControls overrides: the loading menu uses CGameMenu's, and its
  bitmaps are gone.

Layout: none shown plainly by these rows.

## Still unsure

None of the list's rows. Open points:

- The owner files of CShutdownState and CRebootState (above); the names are from RTTI and the
  CGameState slots, the file names a guess.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| removed | 12 | 10 | 2: GetTimesWasHit and GetHeadShots are 0x3fce20 and 0x3fce60 |
| new, copy | 2 | 0 | 2: the same two |
| exact, identical-copy | 3 | 3 | 0 |
| deviating (weak), position, slot-only, caller-mismatch | 1 | 1 | 0 |
| unsure, position | 1 | 1 (GetHitPct, deviating) | 0 |

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 92 paired rows compared (callers and address-loaders through the map, ordered
calls), 17 vtables slot by slot, 3 pointer loaders, the stat member-pointer tables. Differences
looked at: 12 caller sets and data counts, 3 call-order substitutions. All are callers added in
the release (new zanim_menu.cpp commands calling SetMovie, the background MPEG functions,
RunEventAnim and TickMpStats; the memory-card functions of util_memcard.cpp and UINetCnfOpen now
calling RunEventAnim), calls that moved (SetFinalTeamTotalsUiVar into TickMpStats;
TickMpStats out of CMPExitState::Tick into new 0x1d7490), the entity loop removed from
SetMpStatUiVars, CLoadMenu inheriting CGameMenu's MyTick and PrepControls, the extra GetHitPct
record, and changed callees (CExitState::Tick calls CSnd::PostTick for CSndInstance::PostTick,
CMenuState::Init CSnd::SetupSoundGroups for CSnd::UIOpen, CLoadState::Init
CZPersonaState::UpdateLocalPersona where it read a file).
Pairs wrong: 0.

What misled it:

- 0x3fce20 and 0x3fce60: one-load getters with many equal copies, at a release position (in
  st_mpexit.cpp) other than the prototype's (st_exit.cpp), because the linker kept another copy of
  the same inline. The member-pointer table `c_arrStatFuncs` decides them; the tool reads vtables
  and command tables but not the 12-byte member-pointer records `{0, -1, function}`.

What cost the most time: the stat getters (reading the member-pointer records) and tracing the two
new states. Suggestion:

- Read pointer-to-member records (`{delta, -1, function}`) in data as table entries, so that an
  inline getter kept in another file pairs by its entry.
