# Stage 2: Apps/FTS/hud (2026-11-26)

The one list of `Apps/FTS/hud` (list a): the 23 hud owner files (hud_main.cpp, hud_scorepopup.cpp,
hud_newhudmap.cpp, hud_bitmapreticule.cpp, hud_linemap.cpp, hud_objectives.cpp, hud_actionbitmap.cpp,
hud_ingame_weaponsel.cpp, hud_weaponsel.cpp and the smaller ones; release 0x3d6fe0-0x405d00 and
0x41f9c0-0x422520). It holds 35 uncertain rows (24 new, 4 of them without an owner; 7 removed; 3 weak
pairs (`slot-only`); 1 exact row flagged `identical-copy`), 15 sampled deviating rows out of 214, and
127 exact rows that were not checked one by one. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-hud`, who did not write the
tool, at HEAD 293696c3. The check sheet (`compare.py --sheet Apps/FTS/hud --list a`) was the
starting point. Both images were disassembled with the release tools; callers were found by
scanning both images for `jal`/`j`, `lui`/`addiu` pairs, `$gp` accesses and data words. Ghidra was
not needed.

As the guard on the committed pairs, all 344 paired rows of the owner ranges had their callers and
address-loaders compared with the prototype's through the map, and their ordered calls and loads
compared for substitutions; the 27 vtables with a slot in the ranges were found by RTTI name and
aligned slot by slot; the 57 functions that store a vtable had the stored tables compared by RTTI
name; the 16 functions anywhere that load the address of a hud function had their ordered pointer
loads compared; the 2 hud functions stored in data outside vtables had their stored neighbours
compared.

What settled rows, in the order it was used: the call site in a paired caller (CheckDIShoot,
TickFullScreenMap, ZoomIn/ZoomOut, InitMap, HandleSelectionInput, CCoreState::Tick, HudTick); the
registrations of the `__sinit_` functions; vtable slots and the release RTTI names; strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x3d79c0 | - | new, owner guess | confirmed | CHUD method: gets the current item's zoom (CZKit::GetCurZoom), hides the text at +0x504 at 1.5x or less, else prints "ZOOM: %2.1fx" into it. ZoomIn and ZoomOut call it where the prototype made the GetCurZoom/fptodp/sprintf calls inline |
| 0x3dcf50 | - | new, owner guess | confirmed | toggles the valve "HelpWindowsEnabled" (cached in a global by hudInit, new code) and runs its callbacks; caller CZPauseTest::HandleSelectionInput. Before hudInit, after the CWeaponSel destructor |
| 0x3dcfc0 | - | new, owner guess | confirmed | reads that valve's state; callers ReInit and HandleSelectionInput of CZPauseTest and the new popup opener 0x4206b0 |
| 0x3e5c60 | - | new, owner guess | confirmed | CZNewHudMap method split out of TickFullScreenMap (its only caller): the six calls GetCurrentObjective, CalcNewMatrix, Transform, fabsf ×2, ftsGetTacMapZoomFar moved from TickFullScreenMap into it in the same order. Centres the map (+0x4bc/+0x4c0) on the current objective and sets the zoom (+0x74) |
| 0x3e66b0 | - | new, owner guess | confirmed | builds the map legend ("NAV POINTS", "PRIMARY OBJECTIVE", "EXTRACTION POINT", "HOSTAGE/POW/TRAITOR", new "ABLE's POSITION"/"BRAVO's POSITION"); caller InitMap. In the prototype CZObjectiveList::RefreshStatics loaded those strings; the release RefreshStatics does not |
| 0x3e72e0 | - | new, copy, owner guess | confirmed | `__arraydtor` of a new CPlainBmp array (0x57bbf0, used by 0x3e66b0); registered by `__sinit_hud_newhudmap.cpp`, so the copy is decided |
| 0x3e7300 | - | new, owner guess | confirmed | `__arraydtor` of a new C2DString array (0x57b6f0); registered by the same sinit |
| 0x3eacc0 | - | new, copy, owner guess | confirmed | `jr ra; nop`; only caller 0x3e5c60, at its end. No prototype function in its slot (CZLineMap ctor and hudGetTacMapPulseTrans are adjacent in the prototype). Owner by position only |
| 0x3f0130 | - | new, owner guess | corrected to 0x29b650 `DrawAutoReticle__FP6CPnt3D` (zSeal) | see Still unsure of zSeal-a, decided here: the release CheckDIShoot, at the place where the prototype called DrawAutoReticle(&hit) (right after SetAimPointW with the GetCharacterHit point), stores that point at seal +0x534..+0x53c and sets bit 0 of +0x532; 0x3f0130 reads exactly those fields of the HUD owner and projects the point with the same code (sceVu0CopyMatrix of the world camera matrix, 2048, 320, 224, alpha 0.2) before its Draw2DLine calls. The drawing moved from the seal tick into BitmapReticule::HudTick (its only caller, a0 = this, a1 = HUD owner); it now draws six lines with new length constants (10, 4; were distOff 5, retLen 10) and starts with CHUD::IsOn |
| 0x4201f0 | - | new, owner guess | confirmed | slot +0xc (Draw) of the new class `@unnamed@hud_scorepopup_cpp@::CHudPopups` (release RTTI name): draws the background bitmap, then each open popup in the vector at 0x58d760 |
| 0x4206b0 | - | new, owner guess | confirmed | opens a help popup: tests HelpWindowsEnabled (0x3dcfc0), sets the menu state, stops the rumbler, builds the window bitmaps and its C2DString lines, appends it to the open-popup vector; callers hudTickScorePopup and the triggers 0x420b30, 0x420c20, 0x421290 |
| 0x420b30 | - | new, owner guess | confirmed | trigger: matches the objective name against the "HudObjective" entries (vector 0x58d7c0) and opens the popup once; caller SwitchToCompassMap |
| 0x420c20 | - | new, owner guess | confirmed | trigger: matches a zAnim name against the "AnimCmd" entries (vector 0x58d7a0); caller new zFTS 0x1fbe50 (passes CZAnim::GetName) |
| 0x4211b0 | - | new, owner guess | confirmed | clears the "shown" flags of the entries of the vectors 0x58d7a0, 0x58d7c0, 0x58d7e0; callers CHUD::Init and ReInit_Init |
| 0x421290 | - | new, owner guess | confirmed | trigger: "ActionIcon1stTime" entries (vector 0x58d780), offline only (theNetwork+9); caller CActionTxtrMachine::Open |
| 0x4213c0 | - | new, owner guess | confirmed | reads the popup window settings (TopMargin, LeftMargin, BottomMargin, PromptText, BackgroundOpacity, ForceOpenTime, OpeningSound, ClosingSound) with zrdr_find*; caller hudInit |
| 0x421550 | - | new, copy, owner guess | confirmed | returns the function-local static CHudPopups (guard byte, C2D ctor, stores the CHudPopups vtable, registers 0x4215c0); caller CCoreState::Tick, after the CFlashFXVector Draw |
| 0x4215c0 | - | new, copy, owner guess | confirmed | slot +0x8 of the CHudPopups table: its destructor |
| 0x421620 | - | new, owner guess | confirmed | reads one popup entry (Trigger, Type, Name, Mission, Icons, ObjName, Valve, WindowPos, WindowSize, TextSize, LineInterval, TextLines) and appends it to the vector of its trigger type; caller hudInit, once per tag |
| 0x421fc0 | - | new, copy, owner guess | confirmed | `data + 4 * size`: a vector `end()` instance; only caller 0x421620 |
| 0x422190 | 0x3f7a90 `__dt__Q23std52vector<PQ23zar4CKey,...>Fv` | exact, global, ambiguous, identical-copy | corrected to new | its only loader is the release `__sinit_hud_scorepopup.cpp` (0x488180), which registers it as the destructor of the fifth of five new vectors (0x58d7e0). The prototype 0x3f7a90's only loader, `__sinit_zsav_manager.cpp`, has as its release counterpart 0x488070, which registers 0x1dac10 instead. The pair came from equal bytes; see Still unsure for 0x3f7a90 |
| 0x422220 | - | new, copy, no owner | confirmed; owner hud_scorepopup.cpp | destructor of the vector at 0x58d7c0, registered by `__sinit_hud_scorepopup.cpp` |
| 0x4222b0 | - | new, copy, no owner | confirmed; owner hud_scorepopup.cpp | the same, vector 0x58d7a0 |
| 0x422340 | - | new, copy, no owner | confirmed; owner hud_scorepopup.cpp | the same, vector 0x58d780 |
| 0x4223d0 | - | new, copy, no owner | confirmed; owner hud_scorepopup.cpp | the same, vector 0x58d760 (open popups) |
| - | 0x3c2fb0 `__arraydtor$2524` | removed | confirmed | the release `__sinit_hud_objectives.cpp` no longer constructs g_arrAnchorIconBitmaps (its `__construct_array` and the registration of this arraydtor are gone; its C2DBitmap registrations are unchanged) |
| - | 0x3c5780 `RefreshBackground__11CZNewHudMapFPQ23zdb6CWorld` | removed | confirmed | its three callers (HudTick, SwitchToCompassMap, SwitchMapToFullScreen) drop the call; the new call in the two switches (0x200c30) pauses and resumes zAnims and is not its successor |
| - | 0x3c5be0 `MapWorldPointToUV__11CZNewHudMap...` | removed | confirmed | its only caller was RefreshBackground |
| - | 0x3d0520 `DefuseTick__14BitmapReticuleFf` | removed | confirmed | HudTick no longer calls it and "DEFUSING: %d" is gone from the release; the defuse timer now goes through CZWeapon (hudStartDefuseTimer calls RegisterTimer, HudTick calls ClearTimer and creates the valve inline; TimerProgressTick draws the bar) |
| 0x3f6970 | 0x3d5e30 `UnInit__14CZActionBitmapFv` | deviating (weak), slot-only | confirmed | same callers at the same places (ReInit_Uninit +0x70, ~CHUD); still clears ActionTxtrMachine_HUD+0x14 |
| - | 0x3d9820 `StatusLine__4CHUDFv` | removed | confirmed | really gone: its only caller CCoreState::Tick drops the call (with GetAssetReport and CBench::Reset) and calls nothing in its place; its only callee DrawTaskLine and its format strings are absent; NetGetBandwidthInfo, called only by it, has no caller left in the release. The whole hud_devtext.cpp object is gone, `__sinit_hud_devtext.cpp` (0x470640) included |
| - | 0x3db5f0 `DrawTaskLine__FiPfff` | removed | confirmed | only caller StatusLine |
| - | 0x3db860 `GetAssetReport__4CHUDFv` | removed | confirmed | its only caller CCoreState::Tick drops the call |
| 0x3fda60 | 0x3dece0 `WordIntersectionTest__FiiiiP9C2DString` | deviating (weak), slot-only | confirmed | the same two callers (TickWayPoints, CTeamMateNames::Tick) at the same place in their call order; the body lost its fptosi calls like its callers |
| 0x401190 | 0x3fa760 `RePackEquipment__16CInGameWeaponSelFv` | deviating (weak), slot-only | confirmed | same caller SelectEquipment at the same place; the GetWeaponByIndex and PlayErrorSound calls that SelectEquipment made in the prototype are now inside it |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x3d8550 | 0x3b8ec0 `IsOn__4CHUDFv` | yes | the same four callers, plus 0x3f0130 |
| 0x3db070 | 0x3bb1c0 `ReInit_Uninit__4CHUDFv` | yes | same callers OnMissionStart and ReOpen_Unload1; same call sequence |
| 0x3dc830 | 0x3bc910 `__dt__14CTeamMateNamesFv` | yes | slot +0x8 of the CTeamMateNames table; stores that table |
| 0x3de8e0 | 0x3be7c0 `On__11CZPauseTestFv` | yes | slot +0x1c of the CZPauseTest table |
| 0x3e6160 | 0x3c6790 `__ct__11CZNewHudMapFv` | yes | same caller, the CHUD constructor; stores the CZNewHudMap table |
| 0x3e8b60 | 0x3c8cc0 `TickLine__9CZLineMap...` | yes | same caller 0x3e8a80 |
| 0x3e9650 | 0x3c9590 `Tick__9CZLineMapFP11CZNewHudMapf` | yes | slot +0xc of the CZLineMap table |
| 0x3f2a00 | 0x3d1ea0 `AfterOpenFirst__10CWeaponSelFv` | yes | same caller 0x3f2630 |
| 0x3f4fb0 | 0x3d4430 `Init__10CWeaponSelFPQ23zdb6CWorldP7C2DFont` | yes | same caller CHUD::Init |
| 0x3f63a0 | 0x3d5870 `HudTick__14CZActionBitmapF10MENU_STATE` | yes | same caller CHUD::Tick |
| 0x3f7a30 | 0x3d6ea0 `Render_ver_2__18CActionTxtrMachine...` | yes | same caller CZActionBitmap::HudTick |
| 0x4025c0 | 0x3fba70 `HandleOpenState__16CInGameWeaponSelFP4CPadf` | yes | same caller 0x400360 |
| 0x402e80 | 0x3fc360 `Clear__16CInGameWeaponSelFv` | yes | same caller UnInit |
| 0x404aa0 | 0x403120 `Tick__14CFlashFXVectorFf` | yes | same caller CCoreState::Tick |
| 0x421190 | 0x4220b0 `GetE3ScoreTeam08__9CZNetGameCFv` | yes | the same word of the getter table (+0x10 after GetE3ScoreTeam00 on both sides); both getters read 0x10 further on (0xec/0xf0 -> 0xfc/0x100) |

The cross-check found one wrong committed pair (0x422190, above) and one missed pair outside the
list (`__sinit_hud_scorepopup.cpp`, below).

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x3f0130 | 0x29b650 | CheckDIShoot stores the auto-aim point (seal +0x534, flag +0x532 bit 0) where it called DrawAutoReticle; 0x3f0130 reads those fields and projects the point with the same code; caller BitmapReticule::HudTick | socom-release-check-hud | 2026-11-26 | src/Apps/FTS/hud/hud_bitmapreticule.cpp | |
| 0x422190 | new | only loader `__sinit_hud_scorepopup.cpp` (dtor of the new vector 0x58d7e0); the prototype 0x3f7a90's loader `__sinit_zsav_manager.cpp` registers 0x1dac10 in the release | socom-release-check-hud | 2026-11-26 | src/Apps/FTS/hud/hud_scorepopup.cpp | |
| 0x488180 | 0x470cf0 | `__sinit_hud_scorepopup.cpp`: the same first 12 registrations in the same order (CSTable MultiplayerMsgStrings, the ten CScoreBmp g_bmp*, the two CTeamDisplay arrays); directly after `__sinit_hud_missioncams.cpp` on both sides | socom-release-check-hud | 2026-11-26 | src/Apps/FTS/hud/hud_scorepopup.cpp | |
| 0x422220 | new | owner: registered by `__sinit_hud_scorepopup.cpp` (dtor of the vector 0x58d7c0) | socom-release-check-hud | 2026-11-26 | src/Apps/FTS/hud/hud_scorepopup.cpp | |
| 0x4222b0 | new | owner: the same (vector 0x58d7a0) | socom-release-check-hud | 2026-11-26 | src/Apps/FTS/hud/hud_scorepopup.cpp | |
| 0x422340 | new | owner: the same (vector 0x58d780) | socom-release-check-hud | 2026-11-26 | src/Apps/FTS/hud/hud_scorepopup.cpp | |
| 0x4223d0 | new | owner: the same (vector 0x58d760) | socom-release-check-hud | 2026-11-26 | src/Apps/FTS/hud/hud_scorepopup.cpp | |

Rows that change together: 0x3f0130 and the removed 0x29b650 (one row once paired, deviating;
the zSeal owner of 0x29b650 moves to hud_bitmapreticule.cpp); 0x488180 and the removed 0x470cf0.

## New and removed

New in the list (names are guesses unless the basis says otherwise; the prototype's naming
patterns are followed):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x3d79c0 | updates the zoom readout | guess: `UpdateZoomText__4CHUDFv` |
| 0x3dcf50 | toggles the HelpWindowsEnabled valve | guess: `hudToggleHelpWindows__Fv` |
| 0x3dcfc0 | is HelpWindowsEnabled on | guess: `hudHelpWindowsEnabled__Fv` |
| 0x3e5c60 | centres and zooms the full-screen map on the current objective | guess: `ZoomToCurrentObjective__11CZNewHudMapFv` |
| 0x3e66b0 | builds the map legend | guess: `SetupLegend__27@unnamed@hud_newhudmap_cpp@Fv` (next to SetupNorthIndicator) |
| 0x3e72e0, 0x3e7300 | destroy the legend's CPlainBmp and C2DString arrays | `__arraydtor$<n>` (compiler-generated; the numbers are unknown) |
| 0x3eacc0 | nothing (`jr ra; nop`) | unknown; an emptied hook, guess |
| 0x4201f0 | draws the open help popups | `Draw__Q228@unnamed@hud_scorepopup_cpp@10CHudPopupsFPQ23zdb7CCamera` (RTTI name and slot; the C2D Draw slot) |
| 0x4215c0 | CHudPopups destructor | `__dt__Q228@unnamed@hud_scorepopup_cpp@10CHudPopupsFv` (RTTI name and slot) |
| 0x421550 | returns the static CHudPopups | guess: `hudGetHudPopups__Fv` (next to hudGetScorePopupPtr) |
| 0x4206b0 | opens a help popup | guess: `hudOpenHelpPopup__F...` (arguments not recovered) |
| 0x420b30, 0x420c20, 0x421290 | the HudObjective, AnimCmd and ActionIcon1stTime triggers | guess: `hudHelpPopupObjective__FPCc`, `hudHelpPopupAnimCmd__FPCc`, `hudHelpPopupActionIcon__FUi` |
| 0x4211b0 | clears the popups' shown flags | guess: `hudResetHelpPopups__Fv` |
| 0x4213c0, 0x421620 | read the popup settings and one popup entry from the hud file | guess: `hudReadHelpPopupSettings__FP5_zrdr`, `hudReadHelpPopup__FP5_zrdr` |
| 0x421fc0 | vector `end()` | a `std::vector<T*>::end()` instance, T unknown |
| 0x422190, 0x422220, 0x4222b0, 0x422340, 0x4223d0 | destructors of the five new popup vectors (0x58d7e0 ... 0x58d760) | `__dt__Q23std..vector<P..>Fv` instances; the element types are unknown (five distinct instances, so five types) |

The help popups (with the HelpWindowsEnabled valve and the pause-menu toggle) are new in the
release: none of their strings is in the prototype.

Not new, though the map has it as new: 0x3f0130 (DrawAutoReticle, rewritten and moved from zSeal).

Really removed: `__arraydtor$2524` (the anchor icon array), RefreshBackground and MapWorldPointToUV
(no successor; the callers drop the call), DefuseTick (the defuse timer went to CZWeapon's timer
calls and HudTick), and the whole of hud_devtext.cpp: StatusLine, DrawTaskLine, GetAssetReport and
`__sinit_hud_devtext.cpp` (0x470640, correctly removed in the map).

Layouts, plainly shown by settled rows: CZSealBody holds the auto-aim point at +0x534 and its flag
in bit 0 of +0x532 (what was there in the prototype was not checked).

## Still unsure

- 0x3f7a90 `__dt__Q23std52vector<PQ23zar4CKey,...>Fv` (zSave): once 0x422190 is new, its release
  counterpart by its only loader is 0x1dac10, whose instructions equal it after masking. But
  0x1dac10 is paired with 0x1d9160 `list<CKey*>::~list()` (zArchive check, by its CreateKey call
  sites). One release function now serves both: zar's container became a vector, so the linker
  keeps the zar_main copy of `vector<CKey*>::~vector` and the zsav_manager copy is gone. For the
  coordinator: either pair 0x1dac10 with 0x3f7a90 (exact; the name carries over) and make 0x1d9160
  removed (recommended), or keep the zArchive pair and make 0x3f7a90 removed.
- The names of the new functions are guesses, except the two CHudPopups members.
- 0x3eacc0 belongs to hud_linemap.cpp by position only.
- `_TransformPointXYZ__FPC6CPnt4DP6CPnt4D` (0x3fabc0, exact, `moved`) now sits inside the
  hud_playermapitem.cpp range, whose SetViewCone is its only caller; its owner may be
  hud_playermapitem.cpp. The pair is not in doubt.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 24 | 23 | 1: 0x3f0130 is DrawAutoReticle |
| removed | 7 | 7 | 0 |
| deviating (weak), slot-only | 3 | 3 | 0 |
| exact, identical-copy | 1 | 0 | 1: 0x422190 is new |

Owners: the 20 owner guesses held; the 4 owner-less rows belong to hud_scorepopup.cpp (its sinit).

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 344 paired rows compared (callers and address-loaders through the map, ordered
calls and loads), 27 vtables slot by slot (70 hud slots), 57 vtable stores, 16 pointer loaders, 2
data-stored functions. Differences looked at: 10 caller sets, 7 call-order substitutions, 21
vtables, 2 vtable-store sequences, 2 pointer-load sequences. All but one are callers added in the
release (GetHUDOwner, Clear__11CZPauseTest, hudTurnOffScorePopup, Reset__14CFlashFXVector,
GetCurrentObjectiveRetainer), calls that moved into new functions (TickFullScreenMap into 0x3e5c60;
SelectEquipment into RePackEquipment), removed callers (RefreshBackground), changed bodies (CHUD::Tick,
HandleSelectionInput, RefreshStatics, hudStartDefuseTimer, PlayCamera, CleanupCamera, a tail call in
UnInit__14CZActionBitmap), the C2D virtual inserted at +0x20 of every C2D table (0x173940), extra
C2DBitmap members destroyed by ~CHUD and ~CTeamNames, and the two new arrays of
`__sinit_hud_newhudmap.cpp`. The exception is the `__sinit_zsav_manager.cpp` load that exposed
0x422190.
Pairs wrong: 1 (0x422190 <- 0x3f7a90). Missed pair found: 0x488180 <-> 0x470cf0
(`__sinit_hud_scorepopup.cpp`, outside every list: no owner on either side).

What misled it:

- 0x422190: byte-equal template instances (six `vector<T*>` destructors in the release); the tool
  took the one in the hud range by its global look-alike match, though the prototype's only
  loader maps to a loader of a different copy.
- 0x3f0130: DrawAutoReticle moved from zSeal to the hud and changed its argument (a point became
  the seal); its caller changed with it, so no caller or slot evidence linked them. The link is the
  data handed over: the point CheckDIShoot now stores is what 0x3f0130 reads.
- `__sinit_hud_scorepopup.cpp`: grew from 1384 to 2400 bytes and lies outside every owner range.

What cost the most time: the CKey destructor (tracing the five new vectors through the sinit) and
the help-popup group. Suggestions:

- Pair `__sinit_<file>` functions by their position in the sinit run (they follow the link order on
  both sides) and by their first registrations, and give them their file as owner.
- Flag an identical-copy pair when the prototype side's loader maps to a release loader that
  loads a different copy.
