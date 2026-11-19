# Audit of the medium HUD functions, list medium-hud (2026-11-16, socom-port-audit-mhud)

List `medium-hud` of the correctness audit ([AUDIT_PLAN.md](../AUDIT_PLAN.md)): the 88 fenced
functions of 200 to 699 bytes (37,828 bytes) in 19 files of `src/Apps/FTS/hud/`. Judged file by
file in the scan's rank order (`build/port/audit/scan-medium-hud.md`), each body compared with its
packet's ELF disassembly instruction by instruction (operand order, widths and signedness, float
operation order, constant words, call arguments, stores, guards), including the port helpers that
stand for the ELF's inline code. HEAD 73d7d121.

**Unfinished: 70 of 88 judged; the list continues.** Left (18 rows, for a follow-up worker):
`hud_fader.cpp` #10-12, `hud_mapcompass.cpp` #46-47, `hud_scorepopup.cpp` #77-80,
`hud_actionbitmap.cpp` #1-5, `hud_bitmapreticule.cpp` #6-8, `hud_devtext.cpp` #9.

## Counts (70 judged)

| Verdict | Rows |
|---|---|
| MATCH | 59 |
| DEFECT-FIXED | 10 (A 0, B 2, C 8) |
| DEVIATION-KEPT | 1 |
| UNJUDGED | 18 (not reached) |

Defect rate 10 / 70 (14%); A or B 2 / 70. Six of the eight C rows are only the form of a float
test (`a > b` for the ELF's `!(a <= b)`), NaN-only.

## Fixes (ELF evidence)

- B, #45 hudInit 0x3bd010: the TacMap Polygons / Lines loops never ran (count 0, the Lines loop
  read the Polygons array), so the tactical map's line and polygon types kept the built-in
  defaults; rewritten with the ELF's inline `_zrdr::Get` walk. Needs a tacmap before / after pair
  (grade A if the colours change); hudAddPolyType / hudAddLineType now run and were not judged
  here (small band).
- B, #67 CZPauseTest::HandleSelectionInput 0x3bf0a4: fptoui gives 0 for -1; GCC's `(u32)` gave
  0xffffffff, so INVERT_PITCH_CONTROLLER got 0xffff / callback 1 instead of 0 / callback 2.
- C, #74 CZPlayerMapItem ctor 0x3dc850 (and TickSealCone's death swap 0x3dc16c, the hud-b #38
  deviation): the clipped fans' texture copies (C2DTriFan::m_texture exists now).
- C (compare forms, NaN only): #73 0x3dc7d4, #66 0x3be694 / 0x3be6b4, #88 0x3d37d8, #64 0x3c212c,
  #75 0x3d94f8, #33 0x3ca698 / 0x3ca720, #29 0x3bd290.

## Kept deviations

- #34 CZLineMap ctor: also clears m_lastline / m_laststring / m_linetex (reason in the code).

## Leads

- audit-large-hud-b.md #38 (TickSealCone) is no longer a deviation: the texture copies are made.
- CEntity::m_type is a 4-byte enum in the port; the ELF reads it as a byte (+0x10).
- hudAddPolyType / hudAddLineType (hud_linemap.cpp) now run on hud.rdr data: judge them.

## What the packets lacked

Same-file helpers (IgwsLoadHighlight, StepDown / StepUp, SetMapScreenPos, AfterCloseFirst), enum
values (PadBtnFunc, Selection, ZOOMSTATE), C2DString vtable slots (vt.py), CHUD member offsets
(off.py), the fptoui body, list tail() / end() bodies, and the ELF's `_zrdr::Get` inline.
Working file by file helped: a file's helpers, layout and enums were read once for all its rows.

## Runs

- Default build (`default.sh audit-mhud-default`): library and link exit 0. No emulator run
  (stopped by the coordinator before the smoke run).

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 22 | 0x3fadc0 | 628 | CInGameWeaponSel::OnScrollDown() | hud_ingame_weaponsel.cpp | MATCH | - | State 5, slot 3 from slot 0, highlight (x-1, y-1, 171+, 64+) with texture 3 and On, goal (0, y2-y1), the inlined GetPrevItem (owner test, wrap, CanSelectWeapon then GetPrevItem, the dropped GetName), icon texture +0x94, IsSelected byte, icon Load without On (quirk), slot 1's highlight with texture 0 (quirk), arrow 1 trans 128 / colour 100, arrow 0 colour 60, 50 rising, trans 128/40/40/128, sound slot 0x10 (0.5, 0, 255), SwitchOffText: all agree. The scan's call / store differences are the inlined GetPrevItem and the port's layout. |
| 21 | 0x3fab30 | 652 | CInGameWeaponSel::OnScrollUp() | hud_ingame_weaponsel.cpp | MATCH | - | As OnScrollDown with slot 2, state 4, the inlined GetNextItem (with its loop), IsSelected before the texture lookup, the icon switched on, arrow 0 trans 128 / colour 100, arrow 1 colour 60, trans 40/128/128/40, the scroll-up sound: all agree. |
| 16 | 0x3f9cb0 | 364 | CInGameWeaponSel::AfterOpenFirst() | hud_ingame_weaponsel.cpp | MATCH | - | Icons 0 and 2 On, state 2, goal (0, 64), slots 0 / 2 from slot 1, each icon Load + On and highlight Load + On in the ELF's order and textures. |
| 26 | 0x3fc450 | 368 | CInGameWeaponSel::UnInit() | hud_ingame_weaponsel.cpp | MATCH | - | State test, the inlined close (owner test, arrows / background Off, 4 highlights On, state 6, SwitchOffText, UpdateCharacter), the inlined AfterCloseFirst (height ((32+y)+2)-(y-1), centre /2, goal from slot 1, start 0, state 7, Off of icon 0, highlight 0, icon 2, highlight 2), AfterClose, Clear: all agree (the port calls AfterCloseFirst). |
| 20 | 0x3fa8c0 | 616 | CInGameWeaponSel::SelectWeapon() | hud_ingame_weaponsel.cpp | MATCH | - | Owner test, the unguarded id (lb +0x60), primary to loadout slot 0 / secondary to slot 1 with icon 1 = 1 and the NULL-tested re-lookup (255), else SelectEquipment; sound (0.5, 0, 255); the inlined GetPrevItem / GetNextItem; m_selected 0..2 and the three IsSelected bytes; PlaceWeaponText, UpdateCharacter. |
| 24 | 0x3fba70 | 572 | CInGameWeaponSel::HandleOpenState(CPad*, float) | hud_ingame_weaponsel.cpp | MATCH | - | Owner test; the pulse (0.3 x dT, targets 0x3dcccccd / 0x3f333333, flag flips on equality), colour 0.5 x (255 x c) on highlight 1; PAD_UP (+0x17) / PAD_DOWN (+0x18) falling, GetButtonState(Action 0) and (Inventory 4) with the owner test and the inlined close; PulseSelectionArrows in every path. |
| 23 | 0x3fb7f0 | 636 | CInGameWeaponSel::PulseSelectionArrows(float) | hud_ingame_weaponsel.cpp | MATCH | - | The two GetColor copies (m_tris[0], +0x40), the tests `!(up <= down)` / `!(down <= up)`, step 500 x dT in all three, Sub into itself, the `<` clamp to the other's colour with trans 100 (slot 0x20), rising and the colour; else c + 250 dT with `!(c <= 120)` and c - 250 dT with `c < 60`, the flag flip, both SetColor. |
| 13 | 0x3f8620 | 268 | CInGameWeaponSel::GetPrevItem(int) | hud_ingame_weaponsel.cpp | MATCH | - | Owner test (0), cur-1 wrapping to size-1, one recursion level inlined (the same body), the dropped GetName calls. |
| 14 | 0x3f8730 | 300 | CInGameWeaponSel::GetNextItem(int) | hud_ingame_weaponsel.cpp | MATCH | - | Owner test (0), cur+1 wrapping at `!(i < size)` to 0, the while loop over CanSelectWeapon with the inlined level (its own loop), the dropped GetName. |
| 19 | 0x3fa7c0 | 256 | CInGameWeaponSel::SelectEquipment(int) | hud_ingame_weaponsel.cpp | MATCH | - | Selected: slots 2..5, a NULL weapon skips the compare, the byte compare with m_ID, 255, icon 1 = 0, RePackEquipment, error sound after the loop; not selected: the first 255 slot takes the id (255 for NULL), icon 1 = 1; error sound. |
| 17 | 0x3f9e20 | 500 | CInGameWeaponSel::AfterOpenSecond() | hud_ingame_weaponsel.cpp | MATCH | - | Background (x-1, ((y-1)+centre)-0.5h-96, 171+x, 256+top) and On; arrow texture width +0 / height +2 (unsigned), arrow 0 On then Load (centre 85.5+x, +-0.5w, (y0-10)+10), arrow 1 On then Load ((y2+48)+10, the ELF's 0+ terms change nothing); 4 highlights Off, PlaceWeaponText, state 3. |
| 18 | 0x3fa610 | 332 | CInGameWeaponSel::AfterClose() | hud_ingame_weaponsel.cpp | MATCH | - | Owner test, SetMenuState(0), pad id < 2 or NULL (untested, quirk), SetButtonState(TRIANGLE 6, KEY_DOWN 2), highlights then icons Off, arrows, the five texts, state 0. |
| 15 | 0x3f8eb0 | 232 | CInGameWeaponSel::SwitchOffText() | hud_ingame_weaponsel.cpp | MATCH | - | Off (slot 0x18) of the five texts, the 3 selected texts (stride 136), the 6 names, the title. |
| 25 | 0x3fc360 | 232 | CInGameWeaponSel::Clear() | hud_ingame_weaponsel.cpp | MATCH | - | ClearAndWipe (slot 0x78, vt.py) of the same 15 strings in the same order. |
| 74 | 0x3dc850 | 384 | CZPlayerMapItem::CZPlayerMapItem(CEntity*) | hud_playermapitem.cpp | DEFECT-FIXED | C | Member ctors (two C2DBitmapPoly, two C2DTriFan[2] of 44 bytes, C2DString), alive, entity, the two texture pairs, oldpos zero, fade 0 / in, name colour (10, 10, 40) agree. The four clipped-fan texture copies (+0x470 / +0x49c cone, +0x418 / +0x444 blip) were left out as a deviation "C2DTriFan has no texture member"; it has one now (ztwod.h m_texture +0x28): written. C: Clip is empty, so the fans never draw. The same copies were added to TickSealCone's death swap (0x3dc16c..0x3dc188, the hud-b #38 deviation). |
| 71 | 0x3db870 | 284 | CZPlayerMapItem::~CZPlayerMapItem() | hud_playermapitem.cpp | MATCH | - | Member destructors only: the name string, the two fan arrays (__destroy_arr, 44 x 2), cone and blip polys, the CZMapItem vtable, delete on the flag: the port's empty body gives the same. |
| 72 | 0x3dc3f0 | 580 | CZPlayerMapItem::GetBlipID(CZSealBody*) | hud_playermapitem.cpp | MATCH | - | NULL entity 8, the seal type byte (+0x10 == 2), the alive bit (+0xdd bit 3) 8; IsAi (slot 0x30), sleeping bit (+0x281) 9, GetAiAware, team bits 8 / 4 / 0x20000 -> 6 / 0 / 7, viewer team 0, show_all (static 0) or aware counter (+0xd8 > 0) -> aware + 1 else 9; IsRemote (slot 0x34): team 0, show_enemies (static 1), counter 5 / 9; else 5 / 0 by team. The scan's +0x10 width is the port's 4-byte CEntity::TYPE against the ELF's byte (the compare is the same). |
| 73 | 0x3dc770 | 216 | CZPlayerMapItem::Tick(CZNewHudMap*, float) | hud_playermapitem.cpp | DEFECT-FIXED | C | EntityIsValid -> true; fade in fadeval + 0.51 dT (0x3f028f5c) with the clamp at `!(v <= 1)` (0x3dc7d4) where the port tested `v > 1` (NaN only): written as the ELF; fade out `v < 0` agrees; TickSealCone, false. |
| 68 | 0x3bf210 | 484 | CZPauseTest::OpenPauseMenu() | hud_pausemenu.cpp | MATCH | - | Owner / control (NULL control not tested, as the ELF), StopRumbler, pad id < 2, SetButtonState(START 0, KEY_DOWN 2), PauseAllSounds, PostTick(0, NULL), On, AddLetterbox (theHUD+0x14280), the full-screen map test (+0xe834) and SwitchToCompassMap, CHUD::Off, background On, old menu state byte, SetMenuState(3), IsPlayer (slot 0x2c) and Apply_LensEffects(false, NULL), selections trans 128, background 40, time 0, the five colours (86, 63, 27), curcolor 1. The trace is port-only. |
| 66 | 0x3be590 | 544 | CZPauseTest::TickOffState(CPad const&, float) | hud_pausemenu.cpp | DEFECT-FIXED | C | Input bit (+0x169 bit 3), START falling, the network byte, bConnected (static, read before it is stored), the disconnect start, GetMenuState != 5, OpenPauseMenu; the letterbox byte and CHUD::On agree. Fade: the ELF enters at `!(t < 0)` (0x3be694) and takes one flag `!(t + dT < 0.5)` (0x3be6b4) for both the alpha and the -1 reset; the port tested `t >= 0` and `time >= 0.5` twice (NaN only): written as the ELF. |
| 67 | 0x3bef50 | 696 | CZPauseTest::HandleSelectionInput(CPad const&) | hud_pausemenu.cpp | DEFECT-FIXED | B | Inputs (state 9 rising, 0 falling, 3 or 2 falling), the select sound (slot 0xc, 0, 255), the 5 x 3 table (bytes at 0x464d00 checked), replay Set(2) / abort Set(1) with callback 1, auto aim toggle, valve Create(.., 2), the change state 1 / 2, the two SetString texts (slot 0x5c, selections 4 and 2), close: all agree. Invert pitch: the ELF converts the factor with fptoui (0x3bf0a4; 0x16d7a0 gives 0 for a negative value), the port's `(u32)` gave 0xffffffff for -1, so INVERT_PITCH_CONTROLLER became 0xffff with callback 1 instead of 0 with callback 2 (UIStoreOptions reads it back as "invert on"): written with the negative case. |
| 69 | 0x3bf400 | 428 | CZPauseTest::ClosePauseMenu() | hud_pausemenu.cpp | MATCH | - | m_on test, ResumeAllSounds, pad id < 2, SetButtonState CROSS 9 / SQUARE 8 / TRIANGLE 6 / CIRCLE 7 to KEY_UP, SetMenuState(old byte), RemoveLetterbox, night byte (+0x5c8), IsPlayer, zoom byte == 2 (NVG, lens +0x5cc) or >= 3 (starlight, +0x5d8), Off (slot 0x18), wason, fade time 0. |
| 70 | 0x3bf5b0 | 380 | CZPauseTest::CZPauseTest() | hud_pausemenu.cpp | MATCH | - | C2D base, 5 C2DStrings (136), C2DBitmap, m_num_selections 0, the virtual Off (clears m_on), curcolor 0, inc 50, font NULL, old menu state 0, three sounds NULL. The port's extra `m_on = false` repeats what Off stores (no effect). |
| 27 | 0x3bdba0 | 284 | CLensFlareSaturate::Init() | hud_lensflare.cpp | MATCH | - | Every default store (+0x80..+0x124: DI type halfword 2, glare 0 / 0 / 0.5, min dot 0.75 and 1 / (1 - dot) at run time, distance 15, scale 0x3a83126f and 0x3c23d70a - min (GCC folds the same single subtraction: the scan's 0.009 word), opacity / light ranges), SetColor(225, 224, 133), Off (slot 0x18), LoadRdr("lensflare.rdr"), Add2D(this, -1, false) only when both flags are set. |
| 52 | 0x3c4c10 | 516 | CZNewHudMap::SwitchToCompassMap() | hud_newhudmap.cpp | MATCH | - | Menu state back, the night lens branches (zoom 2 / >= 3), the inlined SetMapScreenPos (486, 2, 614, 130, centre 550 / 66, clipper) and SetWorldWidth(1200), scale 1, compass On, RefreshBackground, FreeList(false), TRIANGLE KEY_DOWN, CHUD::SwitchToCompassMap agree (trace port-only). |
| 53 | 0x3c5510 | 424 | CZNewHudMap::CalcNewMatrix() | hud_newhudmap.cpp | MATCH | - | atan2f(z, x), the two translations (y not negated, quirk), +0x3fc90fdb with `!(a < pi)` wrap, RotMatrixY, the screen matrix cells and MulMatrix(m, screen, m), the centre stores agree. |
| 51 | 0x3c3580 | 524 | CZNewHudMap::UpdateExplosives() | hud_newhudmap.cpp | MATCH | - | The explosives loop, the claymore item search by +0x8, shooter (+0x90) seal test, new 576 pushed at tail() (= end(), list+4), the MP bomb item once agree (trace port-only). |
| 54 | 0x3c5c80 | 268 | CZNewHudMap::UninitMap() | hud_newhudmap.cpp | MATCH | - | Virtual delete (slot 0x8) of each non-NULL item, the list cleared, MissionEndCleanup, the "N" string freed, the children erased from the front until empty. |
| 55 | 0x3c6a50 | 576 | SetupNorthIndicator(CZSealBody*) | hud_newhudmap.cpp | MATCH | - | x*x + z*z, the double 1 / sqrt, the three line loads with the ELF's terms (10 / 20 / 30), the three SetUVs, Load(1, "N", font, 596, 107) agree. |
| 85 | 0x3d1ea0 | 388 | CWeaponSel::AfterOpenFirst() | hud_weaponsel.cpp | MATCH | - | Icons On, state 2, goal (0, 64), slots 0 / 2 from slot 1, icon Load + On, highlight (x-1, y-1, +(g_iBgRightX - 29), +64) + On, in the ELF's order. |
| 86 | 0x3d2030 | 368 | CWeaponSel::AfterOpenSecond() | hud_weaponsel.cpp | MATCH | - | Arrow right edge 10 + ((x - 1) + (g - 29)), width / height from +0 / +2, the two arrow loads at 173 / 359, 4 highlights Off, PlaceHotSwapLabels, PlaceWeaponText, state 3. |
| 87 | 0x3d2f50 | 304 | CWeaponSel::OnClose() | hud_weaponsel.cpp | MATCH | - | Owner test, arrows / background Off, 4 highlights On, state 6, m_usehudret byte 0, SetCurReticule, the seven texts Off. |
| 88 | 0x3d3770 | 636 | CWeaponSel::PulseSelectionArrows(float) | hud_weaponsel.cpp | DEFECT-FIXED | C | Same body as CInGameWeaponSel's (500 / 250 steps, 60 / 120, trans 100); the port's tests `down < up`, `up < down`, `120 < c` stand for the ELF's `!(up <= down)` (0x3d37d8), `!(down <= up)`, `!(c <= 120)` (NaN only): written as the ELF. |
| 84 | 0x3d0e40 | 608 | CWeaponSel::PlaceHotSwapLabels() | hud_weaponsel.cpp | MATCH | - | Owner test, the two hot swap floats (+0x224 / +0x228) by fptosi (truncation, as the cast), both labels On, equal ids return (quirk), per label Load(0x3f4ccccd, text, font, x + 80, y + 62) (slot 0x68), UpdatePos, x = (x + (g - 29)) - (length + 4) and y << 4, UpdatePos, else Off. |
| 65 | 0x3c24e0 | 548 | CZObjectiveList::CZObjectiveList() | hud_objectives.cpp | MATCH | - | C2D base, the three vectors, member strings / bitmaps, reserve(4), selected -1, textures NULL, increment 1, current NULL. |
| 62 | 0x3c0460 | 480 | CZObjectiveList::SelectNextObjective() | hud_objectives.cpp | MATCH | - | Three inlined steps down (++, lookup, TickObjectives(1000), wrap at size to 0 with its own lookup), the selectable bit after each, then the recursion: StepDown gives the same. |
| 60 | 0x3bfff0 | 440 | CZObjectiveList::SelectPreviousObjective() | hud_objectives.cpp | MATCH | - | Two inlined steps up (wrap below 0 to size - 1, then to 0), the bit tests, the recursion: StepUp gives the same. |
| 61 | 0x3c01b0 | 684 | CZObjectiveList::PreviousObjective() | hud_objectives.cpp | MATCH | - | Previous index read first, the inlined IsAnySelectable, one step up, SelectPreviousObjective when not selectable, the colour copy (+0x50..+0x58) through two range checks, the old line to grey 80. |
| 57 | 0x3bf8e0 | 600 | CZObjectiveList::MissionEndCleanup() | hud_objectives.cpp | MATCH | - | ClearAndWipe of the 8 strings and 7 anchor strings, the lookup, the list erased, the lines and bitmaps deleted (virtual), the three vectors swapped empty. |
| 63 | 0x3c0ab0 | 452 | CZObjectiveList::FreeList(bool) | hud_objectives.cpp | MATCH | - | Lookup, list erased, lines / bitmaps deleted, sizes 0, the swaps only with release. |
| 64 | 0x3c2080 | 312 | CZObjectiveList::Tick(float) | hud_objectives.cpp | DEFECT-FIXED | C | Mission-cam test, PostTick(0), range check, 600 dT pulse, the X label trans 0.5 c agree; the upper clamp is `!(c <= 255)` in the ELF (0x3c212c) where the port tested `c > 255` (NaN only): written as the ELF. |
| 56 | 0x3bf730 | 392 | CZObjectiveList::~CZObjectiveList() | hud_objectives.cpp | MATCH | - | Member and base destruction only, as the port's empty body. |
| 58 | 0x3bfc70 | 232 | CZObjectiveList::GetObjective(int) const | hud_objectives.cpp | MATCH | - | Range check, the objective-cam list walked index steps (unrolled by 8), its +0x8 value. |
| 59 | 0x3bfd70 | 240 | CZObjectiveList::GetCurrentObjective() const | hud_objectives.cpp | MATCH | - | GetObjective(m_selected_objective) inlined. |
| 81 | 0x3d8dc0 | 608 | CTeamNames::SetupTeamNameEntry(int, CZSealBody*) | hud_teamnames.cpp | MATCH | - | NULL seal return, the 32 zero bytes, strncpy 31 and upper case only with a name, Load(0x3f428f5c, text, font, 0, 0) (slot 0x68), UpdatePos, x 510 - length and y (15 i + 382) + bravo (fptosi, << 4), goal / colour green, dot (0, 127.5, 0), text colours, the two push_backs, order Off. |
| 82 | 0x3d9020 | 372 | CTeamNames::SetOpacity(float) | hud_teamnames.cpp | MATCH | - | The static 0x4299999a, box / divider 76.8 x o, per row name / dot 128 x o, order raw o (quirk), dot again, brackets (0.3 o) x c. |
| 83 | 0x3d91a0 | 420 | CTeamNames::CTeamNames() | hud_teamnames.cpp | MATCH | - | C2D base, the member arrays (CHudBrightText 4, C2DString 4, bitmap, 4 dots), memset of the 4 allies, the 4 fade times -1. |
| 76 | 0x3d9610 | 384 | PoseBitmap::Init(zdb::CWorld*) | hud_posebitmap.cpp | MATCH | - | Three texture lookups, position 535 / 382, Load(0x3f2e147b, "stand", font, the unset text position) (quirk), text colour, push_back, trans 127, SetString, pos << 4, SetTrans(128). |
| 75 | 0x3d93a0 | 444 | PoseBitmap::Tick(float) | hud_posebitmap.cpp | DEFECT-FIXED | C | Owner, StanceChanged, IsRemote (slot 0x34), trans 127 before the state byte (+0x304) test, the three words and positions agree; the fade is entered at `!(t <= 0)` (0x3d94f8) where the port tested `t > 0` (NaN only): written as the ELF. |
| 48 | 0x403d10 | 516 | CZHudMissionCams::CleanupCamera(CPad*) | hud_missioncams.cpp | MATCH | - | Texts Off, anim NULL, music fade / clear, weapons and AI on, menu state back, the zoom lens branches (2 / >= 3) and -1, the zoom `!(1 == z)` reset, heartbeat bit, pad Flush, skip swap 1, letterbox out, HUD On (trace port-only). |
| 49 | 0x403f20 | 460 | CZHudMissionCams::HudTick(CPad*, float) | hud_missioncams.cpp | MATCH | - | Input bit, SELECT / state 9 falling skip (Stop, swap 3, pause 3), the pause countdown, Running / CleanupCamera, IsOn and letterbox test, texts On when GetString (slot 0x64) is set, cross text / bitmap On. |
| 50 | 0x404170 | 324 | CZHudMissionCams::Init() | hud_missioncams.cpp | MATCH | - | The six children pushed and switched off in order, "action_x.tif" handle. |
| 34 | 0x3ca850 | 284 | CZLineMap::CZLineMap() | hud_linemap.cpp | DEVIATION-KEPT | - | Vtables, map / HUD map NULL, the 400 lines, 32 strings, the three vectors, triangle count 0 agree; the port also clears m_lastline / m_laststring / m_linetex, which the ELF leaves to the first Tick (reason in the code: no stale heap words for a Draw before it). |
| 33 | 0x3ca5e0 | 616 | CZLineMap::LineTo(CPnt3D const*) | hud_linemap.cpp | DEFECT-FIXED | C | Transform, CalcDrawPos, the 400 cap, Load / SetUV(0.5, 0.9375) / On, A = B agree; the right and bottom outside tests are `!(a <= edge)` in the ELF (0x3ca698, 0x3ca720) where the port had `a > edge` (NaN only): written as the ELF. |
| 31 | 0x3c74d0 | 520 | CZLineMap::Draw(zdb::CCamera*) | hud_linemap.cpp | MATCH | - | Triangles (count), lines (i < last, i < 400), wide polyline segments, bitmaps, strings (i < last, i < 32), each Draw slot 0xc. |
| 32 | 0x3c8be0 | 224 | CZLineMap::TickLines(CAiMap const&, float, bool) | hud_linemap.cpp | MATCH | - | 16-byte lines, TickLine when not polygon (bit 5 of +0xd) or outlined (bit 6), SetupPolygon for polygons. |
| 29 | 0x3bd220 | 416 | CLetterBox::Tick(float) | hud_letterbox.cpp | DEFECT-FIXED | C | Direction byte, the `64 == p` / `0 == p` ends, 128 dT steps, the out clamp `p <= 0` with both Off, the two Loads agree; the in clamp is `!(p < 64)` in the ELF (0x3bd290) where the port had `p >= 64` (NaN only): written as the ELF. |
| 30 | 0x3bd410 | 556 | CLetterBox::CLetterBox() | hud_letterbox.cpp | MATCH | - | C2D base, two bitmaps: no texture bit, Load(0, 0, 1, 1, NULL), black, trans 127, isTrans bit, Off, push_back; m_curpos 0, m_slidedir unset (quirk). |
| 45 | 0x3bd010 | 428 | hudInit() | hud_main.cpp | DEFECT-FIXED | B | The port's loops had a constant count of 0 (and the Lines loop read the Polygons array), so hud.rdr's TacMap Polygons / Lines never reached hudAddPolyType / hudAddLineType and the map used the built-in _linedata defaults; rewritten from the ELF (count = element 0's integer - 1 each pass, child = the inline _zrdr::Get, Lines found after the polygon loop). B until a tacmap before / after pair shows the colours change (then A). |
| 40 | 0x3b90f0 | 596 | CHUD::On() | hud_main.cpp | MATCH | - | m_ison (+0x14955), network num_connected, the 18 On calls in the ELF's order (offsets checked with off.py), the two messengers, ZoomOut on mode 1 else ZoomIn, full-screen map, network team-mate names. |
| 39 | 0x3b8ed0 | 536 | CHUD::Off() | hud_main.cpp | MATCH | - | The same elements Off in order (with m_ammotype), network names, m_ison 0, the two messengers. |
| 43 | 0x3bb1c0 | 468 | CHUD::ReInit_Uninit() | hud_main.cpp | MATCH | - | UninitMap, team names Clear (single player), the five UnInits, the nine ClearAndWipes and 30 perf strings, pause close / Clear, pose Clear, order menu ClearText / Disable, flash Reset, team-mate UnInit, MissionEndCleanup, hudTurnOffScorePopup. |
| 42 | 0x3bb050 | 364 | CHUD::ReInit_Init() | hud_main.cpp | MATCH | - | theHUD On / RemoveLetterbox, piggy-back texts Off, InitMap, ZoomOut, team names Init or Off, pause Init, pose Init, team-mate names Init or Off, viewer = ftsGetPlayer, map ReInit. |
| 44 | 0x3bc010 | 240 | CHUD::ReleaseHUD(CHUD**) | hud_main.cpp | MATCH | - | NULL tests, three Clear_Messages (+0x100, +0x400, +0x280), the three clears, font delete, UninitMap, the five static textures, delete, NULL, 1. |
| 41 | 0x3b9380 | 236 | CHUD::Flash(float, CPnt3D const&, float, float, float) | hud_main.cpp | MATCH | - | new 192 (CFader + CFlashFX vtable), SetMinBrightness, SetColor, Flash(fadeout, duration, fadein), push_back. |
| 35 | 0x3b7820 | 424 | CHUD::DoRangeText(CZSealBody*, MENU_STATE) | hud_main.cpp | MATCH | - | NVG and menu 4 / 5 tests, GetReticuleDi, sqrtf((xx + yy) + zz) x 0x3dcccccd, "%5.1fM", Load(0x3f4ccccd, .., 523, 429), green (25, 127, 25), On, the m_ison Off. |
| 36 | 0x3b8240 | 352 | CHUD::Add2D(C2D*, int, bool) | hud_main.cpp | MATCH | - | GetAssetLibs (slot 0x48), the first non-zero render phase byte (+0x2b), < 12 or > 14 -> 2 else r - 12, push_back / push_front on m_phase (0x14900, 28). |
| 37 | 0x3b83a0 | 328 | CHUD::SwitchToCompassMap() | hud_main.cpp | MATCH | - | Reticule, team names, fire mode On, SetupAmmoCount(appCamera +0x3c), the five On calls, messenger / subtitles, zoom layout, network names, fade time 0. |
| 38 | 0x3b84f0 | 432 | CHUD::SwitchToFullScreenMap() | hud_main.cpp | MATCH | - | The ten Off calls, map On, zoom text / messenger / subtitles / the three action bitmaps Off, network names. |
| 28 | 0x3be4a0 | 240 | CLensFlareSaturate::CLensFlareSaturate() | hud_lensflare.cpp | MATCH | - | C2DBitmap base, DiIntersect(8) (the default argument), the six clears, m_hasTexture (bit 3 of +0x15) 0, Load(0, 0, 640, 448, NULL), SetTrans(128) (slot 0x20), m_isTrans (bit 2) 1. |
