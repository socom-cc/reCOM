# audit-unmarked-b2 notes (2026-11-15, socom-port-audit-b2): UIVarMixin as the ELF has it; the unlocated unmarked functions of UI, 2D, animation and application

Two tasks on top of list B's audit (`audit-unmarked-b.md`): give the port's UI classes the base-class lists the
reference ELF has (list B's three KEPT destructors came from one missing base), and judge the 26 rows of
`build/port/unmarked/unmarked-not-found.md` whose nearest marked file is under `gamez/zUI`, `gamez/zTwoD`,
`gamez/zAnim` or `Apps/FTS`. No `@socom-anchor`, `@socom-artifact` or `@socom-skeleton` marker was added, moved or
changed and no function moved between files.

## Task 1: the UIVarMixin family

### Evidence
- DWARF: `CPlainBmp` (160 bytes) = `C2DBitmap` @0, `UIVarMixin` @0x80, `m_pulsing` @0x88, `m_period` @0x8c,
  `m_curtrans` @0x90; `CRenderableString` (172) = `C2DString` @0, `UIVarMixin` @0x88; `C2DButton` 1040 bytes with
  a `CPlainBmp _bmp` @0x170. No DWARF for the other classes.
- RTTI base lists (`__RTTI__<class>` +4: (base RTTI, offset) pairs) give every class's bases, and the
  `@<offset>@UpdateUIVar__...` thunks and the second half of each vtable (`ffffff80` / `ffffff78` / `fffffbf0`)
  agree with them.
- Every `CPlainBmp`, whether a base or a member, carries the mixin: `UIVarMixin::DetachUIVar` (0x39e100) is called
  by the inlined `~CPlainBmp` of `~CGameMenu` (2, `_bmpBackground` / `_bmpFade`), `~CLoadMenu` (5, `m_bitmaps`),
  `~C2DButton` (`_bmp`), `~CUIListBox` (5: its own part and its four images), `~CCheckBox`, `~CSliderBar`, `~CHUD`,
  the list-row impls, `~CPopUpDialog` 0x1d4150, `~CycleItem` 0x39ad24, `~CBmpWithNode` 0x3a8ec4, `~CHProgressBar`
  0x393c18.

### Class table
ELF offsets from DWARF / RTTI; port sizes from a compile probe (GCC, `sizeof`), before = HEAD 85b06ea2, after = this
change. In the port a second base sits right after the primary base (offset = the primary's port size).

| class | ELF bases (RTTI) | ELF mixin @ | ELF size | port before | port after |
| --- | --- | --- | --- | --- | --- |
| UIVarMixin | - | (vptr, m_uivar +4) | 8 | same | same |
| CPlainBmp | C2DBitmap, UIVarMixin | 0x80 | 160 | C2DBitmap only, `m_mixin_uivar` standing for the mixin's m_uivar; 140 B | C2DBitmap, UIVarMixin (@124); 144 B |
| CHProgressBar | CPlainBmp | 0x80 (CPlainBmp's) | 176 (no DWARF) | CPlainBmp (no mixin); 176 B | CPlainBmp; 180 B |
| CPopUpDialog | CPlainBmp | 0x80 | 2544 | CPlainBmp (no mixin); 2592 B | CPlainBmp; 2604 B |
| CycleItem | CPlainBmp | 0x80 | 192 | CPlainBmp (no mixin); 180 B | CPlainBmp; 184 B |
| CUIListBox | CPlainBmp | 0x80 | 1536 | CPlainBmp, UIVarMixin (port deviation: a second mixin @140); 1428 B | CPlainBmp; 1440 B |
| CBmpWithNode (skb) | CPlainBmp | 0x80 | - | CPlainBmp (no mixin) | CPlainBmp |
| CRenderableString | C2DString, UIVarMixin | 0x88 | 172 | same (mixin @140); 176 B | unchanged |
| C2DClock, C2DCounter, CTeleType, CTickerTapeText, CWrappedText | CRenderableString | 0x88 | - | same | unchanged |
| CScrollText | CWrappedText | 0x88 | - | same | unchanged |
| CCheckBox, CSliderBar | C2DButton, UIVarMixin | 0x410 | 1264 / - | same (mixin @ port C2DButton size) | unchanged (C2DButton grows by its `_bmp`'s vptr) |
| CRadioStrip, CCycleButton, CHandlerButton | C2DButton (no mixin of their own) | - | - | same | unchanged |
| SystemTuner and the 7 tuners | UIVarMixin @0 | 0 | 8 | same | unchanged |

### What changed (source)
- `gamez/zUI/zui.h`: the header is read in three sections: part A (to `ActionItem`), the UIVarMixin section (its
  own guard, `ZUI_UIVARMIXIN_H`) and part B (`ZUI_H_PART_A` .. `ZUI_H_PART_B`). `gamez/zTwoD/ztwod.h` includes it
  with `SOCOM_ZUI_MIXIN_ONLY` just before `CPlainBmp`, so the class can take `UIVarMixin` as a base while its fence
  stays where it is. `CUIListBox` loses its second `UIVarMixin` base (the port deviation recorded by mod-zui part
  2): its attaches and its `UpdateUIVar` go through `CPlainBmp`'s mixin as in the ELF.
- `gamez/zTwoD/ztwod.h`: `class CPlainBmp : public C2DBitmap, public UIVarMixin`; `m_mixin_uivar` removed. The
  destructor is the ELF's 0x1d6260: `~UIVarMixin` (`DetachUIVar(NULL)`), then the `C2DBitmap` part; so the three
  KEPT destructors of list B (`~CPlainBmp` 0x1d6260, `~CPopUpDialog` 0x1d4090, `~CycleItem` 0x39aca0) now end with
  the detach, and so do `~CHProgressBar`, `~CUIListBox`, `~CBmpWithNode` and every class holding a `CPlainBmp`.
- `gamez/zUI/zui_2d.cpp`: `CPlainBmp::LoadSpec` (0x390d40) and `CHProgressBar::LoadSpec` (0x38b890, twice, as the
  ELF) attach with `AttachUIVar` and then call `UpdateUIVar` through the mixin (the port stored the pointer and
  called `UpdateUIVar` directly); `CPlainBmp::Draw` (0x390e10) and `CHProgressBar::Draw` (0x38b5d0) read the mixin's
  `m_uivar` (+0x84).
- `loadscreen.md`'s gap "CPlainBmp has no UIVarMixin base ... variable changes don't reach CPlainBmp or
  CHProgressBar" is closed by this.
- Port deviations removed: `CUIListBox`'s second base (zui.h) and the `m_mixin_uivar` model with its two "unproven"
  notes in `CPlainBmp::LoadSpec` / `CHProgressBar::LoadSpec` (zui_2d.cpp) and the one in ztwod.h.

### Checked against the ELF, no change needed
- `UpdateUIVar` overrides: `CPlainBmp` 0x393830 and `CCheckBox` 0x393b90 empty; `CHProgressBar` 0x38ba00 (REAL or
  INTEGER is the fill time, progress 0; no attached-variable test); `CSliderBar` 0x38baa0 (REAL only; the INTEGER
  branch is dead); `CRenderableString` 0x390f10 and `C2DClock` 0x3853f0 (only for the attached variable, +0x8c);
  `CUIListBox` 0x38d8a0 (array variables only); the tuners (list B). Every port override has the ELF's tests.
- Attach sites (callers of `AttachUIVar` 0x39e1e0): `CPlainBmp`, `CHProgressBar` (x2), `CRenderableString`,
  `CTeleType`, `CTickerTapeText` and `CWrappedText` (CRenderableString::LoadSpec inline), `CCheckBox` (after
  C2DButton::LoadSpec), `CSliderBar` (before it), `CUIListBox` (x2), `InitSystemTuners` (x7): the port attaches at
  each, in the ELF's order. `CScrollText::LoadSpec` 0x389390 calls `CRenderableString::LoadSpec`, as the port.
- `AttachUIVar` 0x39e1e0: the ELF repeats the attach inline after joining the list; there `m_uivar` is already the
  variable (`beq a1,s1` at 0x39e300), so the repeat (DetachUIVar, `IsAttached`, push_back, a recursive
  AttachUIVar) never runs; the port's AttachUIVar ends before it. `DetachUIVar` 0x39e100, `CUIVariable::Destroy`
  0x39ebc0 / `DetachAll` 0x39ea70 / `Reset` 0x39df70 match.

### What it changes for the player
- Offline, the CPlainBmp-family controls bound to a UI variable are the loading screen's (dlgLoad): the
  `LoadingBackground` image (`LoadingScreenBackground`, the texture name) and the `load_progress_filling` progress
  bar (`Load_progress`, the fill time; the mission's `mission.rdr` UiVars give `LOAD_PROGRESS` 21 s and
  `ld_m8_back.tif`). Both are now in their variable's list: a change of the variable reaches them
  (`CHProgressBar::UpdateUIVar` restarts the fill with the new time), and a reset or destroyed variable clears
  their pointer (the port's image kept pointing at a freed slot, which a later variable could reuse). Online
  screens: the clan badge image and the list boxes (unchanged behaviour: they had the deviation base).
- Trace (run f_m8, test-tree-only trace statements at the start of AttachUIVar, DetachUIVar, CHProgressBar::UpdateUIVar
  and Reset, plus a test edit in CHProgressBar::Tick that sets the bar's variable to 6 three seconds into the load
  screen):
  `attach 0xe400bc to LoadingScreenBackground`, `attach 0xe402dc to LOAD_PROGRESS`, `bar UpdateUIVar LOAD_PROGRESS
  type 2 value 21 (attached 1)`, the second attach (`was 0x6767b4`: already attached, returns) and update;
  `test: bar duration 21 s progress 0.14, var LOAD_PROGRESS (attached 1): set it to 6` -> `bar UpdateUIVar
  LOAD_PROGRESS type 1 value 6` -> `after Set: duration 6 s progress 0`: the bar follows its variable (at HEAD the
  bar was never in the variable's list, so the Set reached nothing and the fill kept its 21 s). When the load
  screen goes: `detach 0xe400bc from LoadingScreenBackground (items 1)`, `detach 0xe402dc from LOAD_PROGRESS`,
  then `CUIVarManager::Reset`. The list box (zui hook, run f_ui): the SavedGames variable has 1 attached object,
  the list box through CPlainBmp's mixin, and scrolls as before.

## Task 2: the unlocated unmarked functions of this area
Verdicts: LOCATED-MATCH 5, EQUIVALENT-IMPLICIT 18, WRITTEN 3, LOCATED-FIXED 0, LEFT 0. `~CCharacterWeap` is in
`gamez/zCharacter/zchar.h`, a file another worker owns now: it was handed over as an edit file and is in the tested tree.

| address | function | verdict | evidence / port location |
| --- | --- | --- | --- |
| 0x173520 | zdb::CNodeVector::~CNodeVector | EQUIVALENT-IMPLICIT | only the `vector<CNode *>` base (zNode/znode.h:154); a static of zparticle.cpp's `__sinit` |
| 0x177990 | CSubMenu::~CSubMenu | LOCATED-MATCH | inline in Apps/FTS/game/orders.h: `_free` of m_display and m_explanation ("orders.cpp", 181), each cleared |
| 0x3bbfb0 | CHudBrightText::~CHudBrightText | EQUIVALENT-IMPLICIT | own vtable, then ~C2DString; no members of its own (hud.h:201) |
| 0x3c5bc0 | _TransformPointXYZ | LOCATED-MATCH | file-local `TransformPointXYZ` in hud_newhudmap.cpp (the matrix passed instead of VF4..VF7); SetViewCone's call site is `CMatrix::Transform` (hud_playermapitem.cpp:376). The ELF stores VF9's stale w; no caller reads w |
| 0x3cbe90 | CHudCompassAnchor::~CHudCompassAnchor | EQUIVALENT-IMPLICIT | m_string (+496) then m_icon (C2DBitmapPoly: m_tris, ~C2D); MapCompass's anchor array |
| 0x3d81f0 | CActionTxtrMachine::~CActionTxtrMachine | EQUIVALENT-IMPLICIT | m_reco_speechIcon, m_reco_speechmeterBKGD[2], m_reco_speechmeter[2], m_timer_BKGRD, m_timer_IMAGE, m_action_string, the vector: the port's members in that order |
| 0x3d8310 | CActionTxtr::~CActionTxtr | EQUIVALENT-IMPLICIT | m_2DBitmap only |
| 0x3d8380 | CActionTxtr::CActionTxtr | WRITTEN | hud.h (declaration) + hud_actionbitmap.cpp: the bitmap, no texture, action 0, m_name = DEFAULT_ACTION_NAME ("UNKNOWN"), inactive; `__sinit_hud_actionbitmap.cpp` builds ActionTxtrPool[18] with it (the port's pool had empty names) |
| 0x1c0190 | CZAnimZAR::~CZAnimZAR | EQUIVALENT-IMPLICIT | own vtable, ~zar::CZAR (virtual in the port too; zanim.h:1346) |
| 0x1d76b0 | CCharacterWeap::~CCharacterWeap | WRITTEN | zCharacter/zchar.h, inline: m_ammoId = 0xff (AMMO_NONE); its ELF callers are vector<CCharacterWeap>'s reserve 0x24ba30 and assign 0x1d78f4, the port's are libstdc++'s |
| 0x2fd120 | zdb::CTexManager::~CTexManager | EQUIVALENT-IMPLICIT | only the `vector<CDynTexList *>` base (ztex.h:239) |
| 0x2fda80 | C2DWidePolyline::CPnt2D$1514 ctor | LOCATED-MATCH | the two-float point is PNT2D in SetSegments (c2dbitmap_poly.cpp:292); the two calls at 0x2fd6b4 / 0x2fd6d8 build the points it builds |
| 0x2ff9a0 | C2DFontEntry::operator= | EQUIVALENT-IMPLICIT | memberwise: m_char and nine ints (ztwod.h C2DFontEntry, DWARF order and types) |
| 0x2ffa00 | C2DFontEntry::C2DFontEntry(const C2DFontEntry &) | EQUIVALENT-IMPLICIT | the same memberwise copy |
| 0x380ce0 | CGameDlgDesign::~CGameDlgDesign | EQUIVALENT-IMPLICIT | m_models, m_objects, m_controls, m_animations, m_script, m_unused14, m_background, m_font, m_libs: the port's members (zui.h) in reverse; locals of SwitchMenu / Init (zui.cpp) |
| 0x38a810 | CPlainBmp::SetPulse | LOCATED-MATCH | C2DButton::ShowState (ztwod.h): period 0: SetTrans(128) (vtable +0x20 = C2DBitmap::SetTrans), not pulsing; else pulsing with that period; its ELF callers (CRadioStrip::Tick, CHandlerButton::Tick, C2DButton::SetCanHandleInput) reach ShowState through C2DButton::Tick / SetCanHandleInput |
| 0x38a870 | C2DString::SetFadeTimeMaxMin | LOCATED-MATCH | the three stores (+0x64, +0x68, +0x6c) in ShowState |
| 0x39cea0 | CDlgDesignModel::operator= | EQUIVALENT-IMPLICIT | the two strings, six floats, the flag (zui.h CDlgDesignModel); vector insert / erase |
| 0x39e3a0 | CUIVariable::IsAttached | WRITTEN | inline in zui.h; its one ELF call (0x39e334) is in AttachUIVar's unreachable repeat (task 1), so no port caller |
| 0x3a1ea0 | CDialogTuner::~CDialogTuner | EQUIVALENT-IMPLICIT | own, SystemTuner's, UIVarMixin's vtables, DetachUIVar(NULL): the port's ~SystemTuner + ~UIVarMixin (zui_tuner.cpp) |
| 0x3a1f20 | CStickDeadzoneTuner::~CStickDeadzoneTuner | EQUIVALENT-IMPLICIT | as above |
| 0x3a1fa0 | CStickAccelerationTuner::~CStickAccelerationTuner | EQUIVALENT-IMPLICIT | as above |
| 0x3a2020 | CStickSensitivityTuner::~CStickSensitivityTuner | EQUIVALENT-IMPLICIT | as above |
| 0x3a20a0 | CBrightnessTuner::~CBrightnessTuner | EQUIVALENT-IMPLICIT | as above |
| 0x3a2120 | CMusicTuner::~CMusicTuner | EQUIVALENT-IMPLICIT | as above |
| 0x3a21a0 | CSoundTuner::~CSoundTuner | EQUIVALENT-IMPLICIT | as above |

## ELF quirks kept
- `AttachUIVar`'s inline repeat is unreachable in the ELF and is not written; `IsAttached` exists only for it.
- `CHProgressBar::LoadSpec` attaches and updates twice (CPlainBmp::LoadSpec inline, then its own copy).
- `_TransformPointXYZ` writes a stale w.

## Port deviations
- The zui.h section guards (`SOCOM_ZUI_MIXIN_ONLY`, `ZUI_UIVARMIXIN_H`, `ZUI_H_PART_A` / `_B`) exist only so that
  ztwod.h can see UIVarMixin while its fence stays in zui.h.
- `~CCharacterWeap` writes `(EQUIP_AMMO)0xff`: zchar.h only declares the enum (AMMO_NONE is in zweapon.h).

## Runs
Final tree = HEAD 8aafdbdb + mine.txt + the zchar.h edit file; every run: no STOP, no exception, focus kept True.
- Front end (run f_fe, fake pad `pad_fe.txt` of mod-zui part 2): main menu -> OPTIONS -> audio, video, controller
  selection, presets -> main menu -> attract -> main menu; no "not written" spec.
- zUI hook (f_ui): SavedGames list on dlgDebriefing (12 rows, DOWN to row 11, top row 4, scroll -72, UP, TRIANGLE)
  and dlgPBMenu (its no-memory-card pop-up closed first), dlgNotEnoughSpace (wrapped text); in use back at
  dlgMenu 18,157,204 B after each test screen. Soft keyboard (f_skb, `-DSOCOM_HOOK_SKB`): typed and accepted "Sad",
  opened again, typed "a", cancelled: PLAYERNAMEVAR "Sad", skb_done 1.
- m8 (f_m8, state hook, one mission, `SOCOM_HOOK_PLAY_AT=999999`, intro movie skipped with CROSS, briefing cameras
  with X, plus the task-1 traces): in the mission from 61.9 s to the end of the run at 301 s (239 s); heap in use
  23.05 MB from 139 s to the end (23,051,780 -> 23,057,540 B); the HUD on screen (weapon box, compass, team names
  FOLLOWING).
- Win (f_win, `port/test-hooks/win`, `-DSOCOM_HOOK_WIN`): "EXIT: debrief open (objectives 3/7)" at 208.2 s, MISSION
  SUCCESSFUL on screen.
- Round trip (f_rt, `port/test-hooks/state`, `-DSOCOM_HOOK_MISSIONS=8`; odd missions pause ABORT, even ones the
  fatal fall, each through the debrief): in use 18,666,980 B at return 1, then 18,667,076 B at returns 2-8 (free
  4,413,352 B): flat. The same hook on HEAD 8aafdbdb alone (run h_rt, two returns): 18,666,708 then 18,666,804 B,
  and 18,156,820 B at the first dlgMenu (this tree: 18,156,996). The +176 B at the menu and +272 B at a return are
  the mixin's vptr: every CPlainBmp (base or member: each button's `_bmp`, the menu's two bitmaps, the keyboards'
  key images) is 4 bytes larger (140 -> 144), as the ELF's has the mixin (160 bytes there).
- Default build (`default.sh`, no hooks, no fake pad): dlgMenu at 16.0 s, the main menu on screen.
