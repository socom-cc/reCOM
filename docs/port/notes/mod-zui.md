# mod-zui notes (2026-11-14, socom-port-mod-zui): the menus' heap leaks, then the zUI module

Scratch `build/port/boot-mod-zui/` (untracked: NOTES.md, mine.txt, copy.txt, asm dumps, pad_fe.txt, the disc's
`readerc.zar` and reader dumps under `disc/`, a script counting the control types per dialog). Changed files:
`mine.txt` (zUI in place, and the small in-place edits in other modules listed below, all free at HEAD 36422b82).

## Result
- Step 1 (the reason for this task): the mission -> menus round trip no longer leaks. Run zm1
  (`port/test-hooks/state/build.sh zm1 pad_idle.txt -DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8`, 720 s): eight
  missions (odd ones pause ABORT, even ones the fatal fall) and eight returns, no failed allocation (the only
  "FAILED" lines are the game's own `zsys_FullAllocAndFree` probe), no STOP; the main menu after the last return.
  In use at the returns: 17,213,716 then 17,213,812 bytes seven times (flat; was 17.35 -> 17.40 MB, +45 KB a trip).
  Largest free block at the returns: 6.24 / 3.64 / 3.64 / 6.24 / 3.64 / 3.64 / 6.24 / 3.64 MB: it follows where the
  break was left (arena 21.6 or 24.2 MB), with no downward trend (was 5.26 -> 2.61 -> 1.35 MB, then a failed 634 KB
  briefing buffer at the fourth return). Leak walks zl1 / zl2 (`HLEAK=1 ... -DSOCOM_HOOK_LEAK -DSOCOM_HLEAK_MIN=1`):
  blocks alive at the menus' world load 512 -> 1025 (+513 a trip) before, 71 -> 83 -> 92 after the zAnim / reader /
  AI fixes; the remaining +11 / +1 per trip (pickup bit words, the HUD map's circle clipper) are fixed since.
- Step 2: `survey.py gamez/zUI` written 57,004 -> 84,480 B, stubs 86,540 -> 59,064 B (`zui.cpp` and `zui_tuner.cpp`
  now have no stub). Front end: the options screens work (audio, video, controller, presets): sliders, radio strips
  with their check boxes, the volume / brightness / stick tuners (run zfe2, fake pad `pad_fe.txt`: main menu ->
  OPTIONS -> audio (two RIGHT on music, LEFT on sound, RIGHT on the stereo strip) -> video -> controller -> presets
  -> main menu -> attract, no STOP, no "not written" spec).
- Final tree, run zm2 (same eight-return hook): in use 17,213,828 then 17,213,924 bytes at returns 2-8, largest
  free block 6.24 MB at every return but the sixth (3.64 MB, the break left higher); no failed allocation, no STOP.
- m8, run zm8 (the state hook with one mission and SOCOM_HOOK_PLAY_AT=999999: intro movie skipped with CROSS,
  briefing cameras with X): in the mission from 72 s to the end of the run at 250 s, no STOP, heap in use
  22.07-22.09 MB from 80 s on.
- Briefing map, run zmap2 (fake pad `pad_map.txt`: PLAY GAME, DOWN x3 + CROSS on the briefing's map button, RIGHT
  pans, L1 zoom in, L2 zoom out, UP, TRIANGLE back to the briefing): no STOP. Its screenshots failed (the emulator
  window was captured too small); zmap1's shows the map.
- Default build (`default.sh zdef2`): main menu at 15.7 s, attract screen (dlgHype) at 43 s.

## Root causes of the menu leak (all from the ELF)
- zUI: `CDesignDlgObj` had no dtor / operator= / copy, `CDlgObjSpec` no dtor (its UI variable spec: name, value
  clone, string table) and no copy ctor, the specs no `Copy`: every design read (each menu switch, the debrief) kept
  its specs. Written: `~CDesignDlgObj` 0x395250, `operator=` 0x3951b0 (deletes its spec, takes the other's `Copy`),
  an inline copy ctor (MSL's vector builds copies as default ctor + operator=; libstdc++ would otherwise share the
  spec and free it twice), `~CDlgObjSpec` 0x3a0f40, `CDlgObjSpec(CDlgObjSpec &)` 0x3a1010, every `Copy` (0x394c70,
  0x399570, 0x39f100, 0x39f500, 0x39f9b0, 0x39fac0, 0x39fbe0, 0x39fc20, 0x39fd20, 0x39fdb0, 0x3a0210, 0x3a04a0,
  0x3a0720, 0x3a08f0, 0x3a0a90, 0x3a0b80, 0x3a0c50: new + the memberwise copy). `Copy` returns `CDlgObjSpec *` and is
  pure in the base (vtable +0xc is 0 in `__vt__11CDlgObjSpec`); `GetType` returns the TYPE name (all 17 written).
- zReader: `zrdr_free` 0x23cfb0 deletes the reader (the port kept the `CRdrFile` and its string table of every
  reader read, menus and missions); `~CRdrFile` 0x23ce90 frees the parsed arrays or the packed buffer.
- zAnim: `CZAnim::Unload` 0x1c8b80 as the ELF: the auto copies (`m_sibling_anim`, calloc'd by `Copy`) unloaded and
  freed first, a running anim leaves its scheduler and goes to state 5, then particle sources, argument list,
  health, the node refs (light maps off the world list, nodes made here deleted), sound / texture / call / valve /
  particle lists, user commands, sequence data, instance node. The port kept ~13 copies a mission with their lists.
- zSeal: `~CSealCtrlAi` 0x26afc0 deletes the stacked AI states (~20 a mission); `CSealCtrlAi::CloseDiPool` 0x2b3060
  written (the sight-line requests: queued ones reset to the free list, then all deleted); `CSealUnit::UnInit`
  deletes a unit's compass anchor (Bravo's "BRAVOTEAM", the inlined dtor's part at 0x2d5604).
- zEntity: `CPickup::Close(true)` frees each pooled pickup's bit words (`__dt__5CBitsFv` 0x17f440).
- HUD: `~CZNewHudMap` 0x3c6490 (was empty): the circle clipper, the map items, the objective list, the player
  items' statics.
- Not leaks (constant across trips, kept as the ELF keeps them): the menus' `readerc` archive buffer
  (zar_main.cpp:394, re-read each return), the UI ZAR directory, `CAiMap` statics, the GS texture buffer names
  (ztex_manager.cpp `SetupBuffer`), valve_main.cpp:218 (14 global valves).

## Written (zUI, ELF addresses)
- Specs (zui_spec.cpp, zui_cleanup.cpp): the above; `CCheckBoxSpec` ctor 0x395f50 / copy 0x395ba0 / dtor 0x3a1420 /
  `CreateDisplayObj` 0x3959b0; `CSliderBarSpec` (inline ctor from `GetControlSpec` 0x39a3e8, `CreateDisplayObj`
  0x3962f0, dtor 0x3a1700); `CRadioStripSpec` ctor 0x395680 (SUBORDINATES as design objects), dtor 0x39f2b0,
  `CreateDisplayObj` 0x39f460, `GetChild` / `NumChildren` / `HasChildren` 0x3a11b0 / 0x3a11a0 / 0x3a1190;
  `GetControlSpec` creates SLIDERBAR, CHECKBOX, RADIOSTRIP and MAPCONTROL.
- Controls (zui_2d.cpp): `CRenderableString` Caption command (`GetZAnimCmdType` 0x388cf0, `ParseZAnimCmd`
  0x388e10); `C2DButton` Caption command (`GetZAnimCmdType` 0x38eeb0, `ParseZAnimCmd` 0x38efc0,
  `TickZAnimCmd` 0x38ef20); `CCheckBox` `LoadSpec` 0x38b380, `Draw` 0x38b150, `HandlePad` 0x38b4b0, dtor 0x393a90,
  `UpdateUIVar` 0x393b90 (empty in the ELF); `CSliderBar` `LoadSpec` 0x38c0a0, `Draw` 0x38bc50, `HandlePad`
  0x38baf0, `UpdateUIVar` 0x38baa0, the SetValue command 0x38c4c0 / 0x38c340 / 0x38c200, dtor 0x393c70;
  `CRadioStrip` `LoadSpec` 0x38ad50, `Tick` 0x38a560, `PressActive` 0x38a880, `HandlePad` 0x38aa70, the Selection
  command 0x38b080 / 0x38af00 / 0x38ad60, dtor 0x393a30. Layouts in zui.h (no DWARF; names from the reader keys).
- Menu (zui.cpp): `LoadFromDesign`'s child loop 0x3826e8 (a radio strip's options appended to its own C2D list),
  `DidStickMovePrev` / `Next` 0x384a40 / 0x384c20, `SetFaderOpacity` 0x384550, `TickMPEG` 0x381680,
  `RestartBackgroundMPEG` 0x381710, `HaltBackgroundMPEG` 0x381790.
- Briefing map (dlgAk8_map's MAPCONTROL): `CUIMapCtrlSpec` ctor 0x394e50, `CreateDisplayObj` 0x394dd0, dtor
  0x39ed20; `CUIMapCtrl` ctor 0x386da0, dtor 0x386c50, `LoadSpec` 0x3866c0, `Draw` 0x3865c0 (scissored to the
  window), `HandlePad` 0x386840, `IsCovered` 0x386400, `OnPan` 0x386170, `CalcAlternateZoomedPos` 0x386a50 and the
  Pan / ZOOM_IN / ZOOM_OUT commands (0x385820, 0x385eb0, 0x3858e0); `CUIMapCtrlAnimCmdHdr` and `CCorners` defined in
  zui_2d.cpp (no DWARF; names from the keys).
- Tuners (zui_tuner.cpp, whole file): `InitSystemTuners` 0x3a2220, `UninitSystemTuners` 0x3a1d80 and the classes
  (SystemTuner and the sound / music / dialog volume, brightness, stick sensitivity / acceleration / dead zone
  tuners, `UpdateUIVar` 0x3a27c0..0x3a2a20): PERMANENT UI variables applied through `CSnd::SetGroupVol`,
  `CVideo::Brightness`, `CPad::SetSensitivity` / `SetAcceleration` / `SetDeadZone`.

## Outside zUI (small in-place edits, free at HEAD)
`zAnim/zanim_anim.cpp` (`CZAnim::Unload`), `zReader/zrdr_file.cpp` (`zrdr_free`, `~CRdrFile`), `zSeal/seal_ai.cpp`
(`~CSealCtrlAi`), `zSeal/seal_sensors.cpp` (`CloseDiPool`), `zSeal/seal_unit.cpp` (`UnInit`), `zEntity/pickup_main.cpp`
(`Close`), `Apps/FTS/hud/hud_newhudmap.cpp` (`~CZNewHudMap`), `zNode/node_main.cpp` (`CNode::GetScale()` 0x227060
and `SetScale(float)` 0x2270e0, reached by the map's zoom: a STOP in the first map run), `zTwoD/ztwod.h`
(`CUIMapCtrl` a friend of `C2DBitmap`: `IsCovered` reads the images' place and size), `zVideo/zvid.h` (`CVideo::Brightness` static: 0x307790
uses no object and the brightness tuner calls it with its own a0).

## ELF quirks kept
- `CDesignDlgObj::operator=` deletes its spec before copying the other's (a self-assignment would copy a deleted
  spec; nothing does that). `LoadDlgObjects` / the radio strip's children fall back to "unnamed".
- `CCheckBox::UpdateUIVar` is empty: a check box does not follow its variable; only its own CROSS (or its radio
  strip) changes it. `CSliderBar::UpdateUIVar` and the volume / stick tuners act only on REAL variables (their
  INTEGER conversion is dead code); the brightness tuner takes INTEGER too.
- `CRadioStrip`: LEFT wraps to the last option, RIGHT and CROSS to the first; a Selection index past the last is
  ignored but still sets the command's result. The options are cast to `CCheckBox` unchecked.
- `CZAnim::Unload` only forgets `m_animEx` (the set's list owns it) and does not run the cleanup sequence (state 5
  directly, unlike `Stop`).

## Port deviations
- `CRadioStripSpec`'s copy (inline in `Copy` 0x39f500) copies its children; the ELF copies the pointers, and the
  original's dtor (0x39f2b0) deletes them, so a copy made when a design's vector grows points at freed objects.
- `CDlgObjSpec::GetChild` returns `CDesignDlgObj *` (the radio strip's children are design objects; the skeleton had
  `CDlgObjSpec *`); `Copy` / `GetType` / `DidStickMove*` got their ELF return types (the skeleton had void);
  `RestartBackgroundMPEG` / `HaltBackgroundMPEG` stay void (no caller reads the result).
- Zeroed where the ELF leaves memory as it was: the check box / slider / radio strip offsets and sizes, the radio
  strip children's XPOS / YPOS; `InitSystemTuners` NULL-tests the variable before its PERMANENT store (the ELF stores
  in a branch delay slot).
- File-local helpers for inlined code: `RadioShowSelection`, `RunOptionAnim` (zui_2d.cpp), `MakeTuner`,
  `TunerReal` (zui_tuner.cpp); `CRadioStrip::Tick` calls `C2DButton::Tick` (inline in the ELF); the CBits dtor
  body is written in `CPickup::Close` (CBits has no port dtor).
- `LoadFromDesign` still starts no menu background movie (earlier port decision); `RestartBackgroundMPEG` would.

## Runs (tree = HEAD 36422b82 + mine.txt)
- zl1 / zl2: leak walks (above). zm1: the eight-return run (above), screenshot at 715 s: the main menu.
- zfe1 / zfe2: options screens (zfe1 without RADIOSTRIP in `GetControlSpec`; zfe2 complete). zm8: m8 stability.
- zmap1: the map opened; the first RIGHT pan STOPped in the `CNode::GetScale()` stub (written since). zmap2: map
  pan / zoom / back, no STOP. zm2: eight returns on the final tree. zdef1 / zdef2: default builds.

## Not written / next
- zui_2d.cpp: the list box family (`CUIListBox`, `ListItem`, the list item types: dlgDebriefing,
  dlgPBMenu, online screens); `CCycleButton`, `CHandlerButton`, `CScrollText`, `CTickerTapeText`, `C2DClock`,
  `CWrappedText::LoadSpec` / `CWrapSpec` (a CTextSpec in the ELF).
- zui_skb.cpp: the soft keyboard (21.6 KB; online player names, chat).
- zui_var.cpp: `CUIVarManager::Serialize` / `UnSerialize`, `_Refresh` (memory card).
- zui_spec.cpp: `CClockSpec::CreateDisplayObj`, `CUIListBoxSpec`, `CCycleButtonSpec`,
  `CHandlerButtonSpec` ctors; zui_cleanup.cpp: the remaining spec dtors / `CreateDisplayObj` of those types.
