# Stage 2: gamez/zUI (2026-11-26)

The one list of `gamez/zUI` (list a): the owner files zui.cpp (release 0x39c340-0x3a14d0),
zui_2d.cpp (0x3a1570-0x3b2980), zui_spec.cpp (0x3b2bb0-0x3bc0a0), zui_var.cpp (0x3bc0d0-0x3bd530),
zui_cleanup.cpp (0x3bd740-0x3c08d0), zui_tuner.cpp (0x3c0a00-0x3c1aa0) and zui_skb.cpp
(0x3c1ab0-0x3c9ac0). It holds 39 uncertain rows (22 new, 3 removed, 3 unsure, 1 weak pair
(`slot-only`) and 10 exact rows flagged `identical-copy`), 15 sampled deviating rows out of 195,
and 306 exact rows that were not checked. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-ui`, who did not write the
tool, at HEAD fa04cf2f. The check sheet (`compare.py --sheet gamez/zUI --list a`) was the starting
point. Both images were disassembled with the release tools. Callers were found by scanning both
images for `jal`/`j`, `lui`/`addiu` pairs and data words. The vtables were found and paired with
the tool's own RTTI reader, and each paired table was aligned slot by slot through the map. As a
guard on the committed pairs, every paired row in the range 0x39c340-0x3c9b00 (529 rows) had its
callers, address loaders, vtable slots and ordered callee sequence compared with the prototype's
through the map. Ghidra was not needed.

Slots below count from the first function word of a table (slot 0 is at +0x08). Two new virtuals
shift most slot numbers by one, and the shift is the same on every table. C2D gained one at
slot 6 (`jr ra; nop` at 0x173940, overridden by CUIMapCtrl and CBmpWithNode), so every C2D
table has one more slot from slot 6 on. CListItemTypeImpl gained one at slot 4.

What settled rows, in the order it was used: vtable slots, including the vtable each destructor
stores; the call site in a paired caller (CScrollSpec::CreateDisplayObj); the receiving call
(RegisterRebootCallback); the order of tuner construction in InitSystemTuners and the release
RTTI names; strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x39e210 | - | new, copy | confirmed | zeroes three words and returns `this`: a default constructor for a 12-byte container. Its only caller is new 0x421620 (outside zUI). No prototype candidate |
| 0x39fe90 | 0x383b40 `AddNode__9CGameMenuFP3C2DPQ23zdb16CTextureRelocMgr` | deviating (weak), slot-only | corrected to new | not AddNode: it calls CSnd::GetSoundByName on a name taken from a global record and stores the result in the zui.cpp global that PlayCountSound plays (`g_pTtySound`, which LoadFromDesign and Clear also write). Callers are CMenuState::Init and the zMenuState IOPRebootHandler. AddNode's only caller, CLoadMenu::PrepControls, is gone |
| 0x3a1670 | - | new | confirmed | `jr ra; lwc1 f0,0xb0(a0)`: slot 28 of every CRenderableString-family table (CRenderableString, C2DClock, CTickerTapeText, CScrollText, CWrappedText, CTeleType, C2DCounter). The prototype tables had C2DString::GetSpacing there, or the CWrappedText/CTeleType overrides, which read the same +0xb0 |
| 0x3a1ae0 | - | new | confirmed | CUIMapCtrl helper called by TickZAnimCmd and HandlePad. Its IsCovered ×8, CalcAlternateZoomedPos and SetPosition calls were made by the prototype TickZAnimCmd |
| 0x3a2180 | - | new | confirmed | CUIMapCtrl helper (a per-axis interpolation of a CPnt3D), called by TickZAnimCmd and HandlePad |
| 0x3a21f0 | - | new, copy | confirmed | slot 8 (Tick) of the CUIMapCtrl table. The prototype used C2D::Tick there. It stores dt in a global. It has the same bytes as UiSetTtySpeedFactor, but the vtable decides |
| 0x3a8510 | - | new | confirmed | slot 8 (Tick) of the CSliderBar table (the prototype used C2DButton::Tick). Calls SetPulse and SetFadeTimeMaxMin |
| 0x3a9f20 | - | new | confirmed | split out of CUIListBox::HandlePad (its only caller): decrements the selection (+0x190), scrolls, plays the selection anim and sound. The prototype HandlePad made those calls itself |
| 0x3aa1f0 | - | new | confirmed | the same, incrementing the selection |
| 0x3aaa20 | - | new | confirmed | CUIListBox method. Walks the items, compares each item's string (virtual +0x14) with the argument and returns whether that item is in the visible window. Caller: new zNetwork 0x34a7b0 |
| 0x3aee80 | - | new, copy | confirmed | slot 20 (GetZAnimCmdType) of the CWrappedText and CScrollText tables. The prototype inherited CRenderableString's. Strings "Scroll_Up", "Scroll_Down", "Caption" |
| 0x3aef80 | - | new | confirmed | slot 8 (Tick) of the CWrappedText table (the prototype inherited CRenderableString::Tick); calls C2DString::Tick |
| 0x3aefe0 | - | new | confirmed | slot 19 (TickZAnimCmd) of the CWrappedText and CScrollText tables |
| 0x3af170 | - | new | confirmed | slot 18 (ParseZAnimCmd) of the CWrappedText and CScrollText tables; "SCROLL_UP", "SCROLL_DOWN", "CAPTION" and zui_2d.cpp lines |
| - | 0x389390 `LoadSpec__11CScrollTextFRC11CScrollSpec` | removed | corrected to 0x3a5920 | see the row below |
| 0x3a5920 | 0x389380 `GetSpacing__12CWrappedTextFv` | unsure, position | corrected to 0x389390 `LoadSpec__11CScrollTextFRC11CScrollSpec` | its only caller, CScrollSpec::CreateDisplayObj, calls it right after SetFont, as the prototype called LoadSpec. It sits between Tick and Draw of CScrollText, as LoadSpec did. The body is now empty (`jr ra; nop`). GetSpacing__12CWrappedTextFv is removed: its slot holds 0x3a1670 |
| - | 0x390c70 `GetSpacing__9CTeleTypeFv` | removed | confirmed | CTeleType's slot 28 now holds the shared 0x3a1670 |
| 0x3b1470 | 0x393350 `DrawPrep__...CListItemImageTypeImpl...` | exact, identical-copy | confirmed | slot 1 of the CListItemImageTypeImpl table on both sides |
| 0x3b1480 | 0x393360 `GetString__...CListItemImageTypeImplFv` | exact, identical-copy | confirmed | slot 3 of the same table |
| 0x3b1490 | - | new, copy | confirmed | the new slot 4 of the CListItemImageTypeImpl table (`j GetTrans__9C2DBitmapFv` on this+16). It has the same bytes as SetPos (0x3b14c0), but the slots decide |
| 0x3b14a0 | 0x393370 `PrepListItem__...CListItemImageTypeImpl...` | exact, identical-copy | confirmed | slot 4 → 5 of the same table |
| 0x3b14b0 | 0x393380 `SetFont__...CListItemImageTypeImpl...` | exact, identical-copy | confirmed | slot 5 → 6 |
| 0x3b14c0 | 0x393390 `SetPos__...CListItemImageTypeImpl...` | exact, ambiguous, identical-copy | confirmed | slot 6 → 7 (the twin 0x3b1490 is the new slot 4) |
| 0x3b14d0 | 0x3933a0 `SetScale__...CListItemImageTypeImplFf` | exact, identical-copy | confirmed | slot 7 → 8 |
| 0x3b16d0 | - | new | confirmed | the new slot 4 of the CListItemStringTypeImpl and CListItemTimedTextTypeImpl tables (returns the float at +0x64) |
| 0x3b16e0 | 0x3935a0 `PrepListItem__...CListItemStringTypeImpl...` | exact, identical-copy | confirmed | slot 4 → 5 of the CListItemStringTypeImpl and CListItemTimedTextTypeImpl tables |
| 0x3b16f0 | 0x3935b0 `SetFont__...CListItemStringTypeImpl...` | exact, identical-copy | confirmed | slot 5 → 6 of the same two tables |
| 0x3b1760 | - | new | confirmed | slot 6 of the CUIMapCtrl table, overriding the new C2D virtual (stores its argument at +0x210) |
| 0x3b17d0 | 0x393690 `Get2DVisual__9C2DVisualFv` | exact, identical-copy | confirmed | slot 6 → 5 of the C2DVisual table: the release table lost the slot before it (`Write__Q23zdb7CVisualFRQ23zar4CZAR`) |
| 0x3b23e0 | - | new | confirmed | the new slot 4 of the CListItemArrayTypeImpl table (first element's virtual +0x18, else 128.0) |
| - | 0x394b40 `__dt__10CClockSpecFv` | removed | corrected to 0x3b2bb0 | see "Just outside the list" |
| 0x3b8b30 | - | new | corrected to 0x39a610 `__dt__9CWrapSpecFv` | slot 0 of the CWrapSpec table on both sides; stores the CWrapSpec vtable, then the CTextSpec one, as the prototype does; 152 → 192 bytes |
| 0x3b8bf0 | - | new | confirmed | out-of-line CWrapSpec constructor from a reader (CDlgObjSpec, CTextSpec, CWrapSpec vtables; "WIDTH", "SPACING", "HEIGHT", new "UP_ARROW"/"DOWN_ARROW" with TEXTURE, SIZE, OFFSET); the prototype built it inline in GetControlSpec, its caller |
| 0x3c08d0 | - | new, no owner | confirmed | calls virtual +0xc (UpdateUIVar) with the tuner's variable for each of the ten system-tuner globals that InitSystemTuners writes and UninitSystemTuners clears. Caller: UIStoreOptions. Owner zui_tuner.cpp |
| 0x3c0b30 | - | new | confirmed | slot 1 of the release table whose RTTI name is `CStickInertiaTuner`. Writes 1.0 - value into a pad field (+0x1c4), where the prototype CStickAccelerationTuner::UpdateUIVar called CPad::SetAcceleration (removed) |
| 0x3c1050 | 0x3a1fa0 `__dt__23CStickAccelerationTunerFv` | exact, identical-copy | corrected to new | it stores the `CStickInertiaTuner` vtable (and is its slot 0): `__dt__18CStickInertiaTunerFv`. The class is not CStickAccelerationTuner: no release RTTI or string of that name is left, "STICK_ACCELERATION" became "STICK_INERTIA", and InitSystemTuners builds CStickInertiaTuner where it built CStickAccelerationTuner |
| 0x3c1a70 | 0x3a2920 `UpdateUIVar__23CStickAccelerationTunerFP11CUIVariable` | unsure, position | corrected to new | not in any vtable. InitSystemTuners passes it to CIOPManager::RegisterRebootCallback (new in the release). It calls UIStoreOptions(0, 0) and returns 1. The Acceleration UpdateUIVar is removed (see 0x3c0b30) |
| 0x3c3390 | - | new | confirmed | slot 6 of the CBmpWithNode table, overriding the new C2D virtual (stores its argument at +0xa0) |
| 0x3c65c0 | 0x3a71c0 `UiGetTextFromUser__FP13C2DAnimCmdHdrPf` | unsure, exact, ref-kind | confirmed | same single caller (zanim_menu OnGetTextFromUser); masked code equal; the same "KEYBOARD", "skb_done" and skb globals. The one reference the tool classes differently does not change the identity |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x39ce70 | 0x380f50 `ParseButtonAnim__FP5_zrdrP10ActionItem` | yes | the same six callers (five spec constructors, CGameDlgDesign::LoadFromRdr); zui.cpp allocator lines |
| 0x39f1f0 | 0x382f00 `HandlePad__9CGameMenuFPC4CPad` | yes | same caller CGameMenu::Tick, same callees |
| 0x39fec0 | 0x383bf0 `__dt__9CGameMenuFv` | yes | slot 0 of the CGameMenu table; the same four derived destructors call it |
| 0x3a00c0 | 0x383df0 `__ct__9CGameMenuFv` | yes | the same four state Init callers; "CGameMenu backplane/foreplane" |
| 0x3a17d0 | 0x385510 `__dt__...CListItemStringTypeImplFv` | yes | slot 0 of the CListItemStringTypeImpl table |
| 0x3a3230 | 0x386da0 `__ct__10CUIMapCtrlFv` | yes | same caller CUIMapCtrlSpec::CreateDisplayObj |
| 0x3a74b0 | 0x38af00 `ParseZAnimCmd__11CRadioStripFP5_zrdr` | yes | CRadioStrip slot 17 → 18 (the C2D shift); same strings |
| 0x3ad270 | 0x38fa10 `__ct__9C2DButtonFv` | yes | the same eight callers |
| 0x3afb90 | 0x391b20 `Draw__17CRenderableString...` | yes | slot 2 of the CRenderableString, C2DClock and C2DCounter tables |
| 0x3afdb0 | 0x391d50 `__ct__17CRenderableStringFv` | yes | the same callers, except GetPopUp and CScrollSpec::CreateDisplayObj now go through new 0x1d69c0 (an out-of-line constructor that stores the CWrappedText vtable); CLoadState::Init no longer calls it |
| 0x3b21e0 | 0x3941c0 `__dt__...CListItemArrayTypeImplFv` | yes | slot 0 of the CListItemArrayTypeImpl table |
| 0x3b8520 | 0x399fe0 `__ct__9CTextSpecFP5_zrdr` | yes | same caller GetObjectSpec; GetControlSpec's inline use moved into new 0x3b8bf0 |
| 0x3b8790 | 0x39a210 `GetControlSpec__FP5_zrdrPCc` | yes | same three callers; same control keywords |
| 0x3be750 | 0x39fd20 `Copy__14CSliderBarSpecFv` | yes | slot 1 of the CSliderBarSpec table |
| 0x3c2930 | 0x3a3940 `ShowNonScalingElements__...CSoftKeyboardFb` | yes | the same five CSoftKeyboard callers |

Just outside the list (inside its owner ranges; found by the vtable comparison):

| release | map | finding |
|---|---|---|
| 0x3b2bb0 | exact, 0x39a610 `__dt__9CWrapSpecFv` (`exact-callee`, `moved`) | wrong: it is `__dt__10CClockSpecFv` (0x394b40). It is slot 0 of the CClockSpec table and stores the CClockSpec vtable. It sits before GetType__10CClockSpecFv and CreateDisplayObj__10CClockSpec... on both sides. The CWrapSpec destructor is 0x3b8b30 (above) |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner |
|---|---|---|---|---|---|
| 0x3b2bb0 | 0x394b40 | slot 0 of the CClockSpec table; stores the CClockSpec vtable; before GetType__10CClockSpecFv on both sides (outside list a) | socom-release-check-ui | 2026-11-26 | |
| 0x3b8b30 | 0x39a610 | slot 0 of the CWrapSpec table on both sides; stores the CWrapSpec vtable | socom-release-check-ui | 2026-11-26 | |
| 0x3a5920 | 0x389390 | called by CScrollSpec::CreateDisplayObj right after SetFont, as LoadSpec was; between Tick and Draw of CScrollText on both sides (body now empty) | socom-release-check-ui | 2026-11-26 | |
| removed | 0x389380 | GetSpacing__12CWrappedTextFv: its slot 28 holds the shared CRenderableString-family function 0x3a1670 | socom-release-check-ui | 2026-11-26 | |
| 0x39fe90 | new | caches GetSoundByName's result in the zui.cpp global PlayCountSound plays; callers CMenuState::Init and the zMenuState IOPRebootHandler | socom-release-check-ui | 2026-11-26 | |
| removed | 0x383b40 | AddNode__9CGameMenu: its only caller CLoadMenu::PrepControls is gone | socom-release-check-ui | 2026-11-26 | |
| 0x3c1050 | new | stores the CStickInertiaTuner vtable (release RTTI) and is its slot 0 | socom-release-check-ui | 2026-11-26 | |
| removed | 0x3a1fa0 | __dt__23CStickAccelerationTunerFv: the class is replaced by CStickInertiaTuner ("STICK_ACCELERATION" -> "STICK_INERTIA" in InitSystemTuners) | socom-release-check-ui | 2026-11-26 | |
| 0x3c1a70 | new | passed by InitSystemTuners to CIOPManager::RegisterRebootCallback; calls UIStoreOptions(0, 0) | socom-release-check-ui | 2026-11-26 | |
| removed | 0x3a2920 | UpdateUIVar__23CStickAccelerationTunerFP11CUIVariable: replaced by CStickInertiaTuner's (0x3c0b30); its callee CPad::SetAcceleration is gone | socom-release-check-ui | 2026-11-26 | |
| 0x3c08d0 | new | calls UpdateUIVar on the ten system-tuner globals of InitSystemTuners/UninitSystemTuners | socom-release-check-ui | 2026-11-26 | src/gamez/zUI/zui_tuner.cpp |
| 0x3c65c0 | 0x3a71c0 | same single caller OnGetTextFromUser; masked code equal | socom-release-check-ui | 2026-11-26 | |
| 0x3b1470 | 0x393350 | slot 1 of the CListItemImageTypeImpl table | socom-release-check-ui | 2026-11-26 | |
| 0x3b1480 | 0x393360 | slot 3 of the CListItemImageTypeImpl table | socom-release-check-ui | 2026-11-26 | |
| 0x3b14a0 | 0x393370 | CListItemImageTypeImpl slot 4 -> 5 (new slot 4) | socom-release-check-ui | 2026-11-26 | |
| 0x3b14b0 | 0x393380 | CListItemImageTypeImpl slot 5 -> 6 | socom-release-check-ui | 2026-11-26 | |
| 0x3b14c0 | 0x393390 | CListItemImageTypeImpl slot 6 -> 7; its twin 0x3b1490 is the new slot 4 | socom-release-check-ui | 2026-11-26 | |
| 0x3b14d0 | 0x3933a0 | CListItemImageTypeImpl slot 7 -> 8 | socom-release-check-ui | 2026-11-26 | |
| 0x3b16e0 | 0x3935a0 | CListItemStringTypeImpl and CListItemTimedTextTypeImpl slot 4 -> 5 | socom-release-check-ui | 2026-11-26 | |
| 0x3b16f0 | 0x3935b0 | CListItemStringTypeImpl and CListItemTimedTextTypeImpl slot 5 -> 6 | socom-release-check-ui | 2026-11-26 | |
| 0x3b17d0 | 0x393690 | C2DVisual slot 6 -> 5 (the Write slot before it is gone) | socom-release-check-ui | 2026-11-26 | |

Rows that change together: the two spec destructors (0x3b2bb0, 0x3b8b30); 0x3a5920 and the
removed GetSpacing__12CWrappedTextFv; the four tuner rows (0x3c1050, 0x3c1a70 and the two
removed CStickAccelerationTuner functions).

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x39e210 | default constructor of a 12-byte container (three zeroed words) | guess: an MSL `__vector_deleter<...>` default constructor (the same bytes as many of them); the element type is unknown |
| 0x39fe90 | looks up the menu's count/teletype sound and caches it in `g_pTtySound` | guess: `LoadTtySound__Fv` (zui.cpp: the global is a zui.cpp static) |
| 0x3a1670 | returns the spacing (+0xb0) | guess: `GetSpacing__17CRenderableStringFv` (slot 28 of the whole family; the removed overrides read the same field) |
| 0x3a1ae0 | tests IsCovered eight times, calls CalcAlternateZoomedPos, then sets the node position | guess: a CUIMapCtrl helper that keeps the zoomed position clear of the corners, e.g. `AdjustZoomedPos__10CUIMapCtrl...` |
| 0x3a2180 | interpolates a CPnt3D per axis | guess: a CUIMapCtrl helper, e.g. `LerpPos__10CUIMapCtrl...` |
| 0x3a21f0 | stores dt in a global | `Tick__10CUIMapCtrlFf` (vtable slot) |
| 0x3a8510 | the slider bar's own Tick (C2DBitmap::Load, SetPulse, SetFadeTimeMaxMin, C2DString::Update on two elements) | `Tick__10CSliderBarFf` (vtable slot) |
| 0x3a9f20 | moves the selection up one item | guess: `SelectPrev__10CUIListBoxFv` |
| 0x3aa1f0 | moves the selection down one item | guess: `SelectNext__10CUIListBoxFv` |
| 0x3aaa20 | is the item with this string visible | guess: `IsItemVisible__10CUIListBoxFPCc` |
| 0x3aee80, 0x3aef80, 0x3aefe0, 0x3af170 | CWrappedText's own zanim commands (Caption, Scroll_Up, Scroll_Down) and Tick | `GetZAnimCmdType__12CWrappedTextFPCc`, `Tick__12CWrappedTextFf`, `TickZAnimCmd__12CWrappedTextFP14_zanim_cmd_hdrPfPb`, `ParseZAnimCmd__12CWrappedTextFP5_zrdr` (vtable slots; signatures from the base slots) |
| 0x3b1490, 0x3b16d0, 0x3b23e0 | the new CListItemTypeImpl slot 4 for the image, string/timed-text and array kinds (a float extent; array default 128.0) | guess: `GetWidth` or `GetHeight` on each `@unnamed@zui_2d_cpp@::CListItem*TypeImpl`; the name is not known |
| 0x3b1760, 0x3c3390 | overrides of the new C2D slot 6 (store an int at +0x210 / +0xa0) in CUIMapCtrl and CBmpWithNode | the base is 0x173940 (zTwoD); name not known |
| 0x3b8bf0 | builds a CWrapSpec from a reader, with the new scroll-arrow textures | `__ct__9CWrapSpecFP5_zrdr` (the stored vtables; the prototype had it inline in GetControlSpec) |
| 0x3c08d0 | re-applies every system tuner from its UI variable | guess: `UpdateSystemTuners__Fv` (zui_tuner.cpp) |
| 0x3c0b30 | sets the stick inertia from the UI variable | `UpdateUIVar__18CStickInertiaTunerFP11CUIVariable` (release RTTI, slot 1) |
| 0x3c1050 | the tuner destructor | `__dt__18CStickInertiaTunerFv` (release RTTI, slot 0) |
| 0x3c1a70 | IOP reboot callback: stores the options | guess: `IOPRebootHandler__FQ211CIOPManager11RebootPhaseQ211CIOPManager10RebootModePv` (the callback type RegisterRebootCallback takes; other files have statics of that name) |

Not new, though the map has them as new: 0x3b8b30 (`__dt__9CWrapSpecFv`).

Really removed:

- AddNode__9CGameMenu, with its caller CLoadMenu::PrepControls.
- GetSpacing__12CWrappedTextFv and GetSpacing__9CTeleTypeFv: one CRenderableString-level
  function (0x3a1670) serves every class of the family.
- CStickAccelerationTuner (its destructor and UpdateUIVar): replaced in place by
  CStickInertiaTuner. Another reading would pair 0x3c1050/0x3c0b30 with the Acceleration pair as a
  renamed class. The release RTTI name, the new UI variable and the different body (no
  SetAcceleration) favour new and removed. With a pair, the prototype name would carry over
  wrongly.
- Not removed, though the map has them: LoadSpec__11CScrollText (0x3a5920) and
  `__dt__10CClockSpecFv` (0x3b2bb0).

Layouts plainly shown by settled rows: C2D gained a virtual at slot 6; CListItemTypeImpl gained one
at slot 4; C2DVisual lost its Write slot; CWrapSpec grew (its destructor 152 → 192 bytes, its
constructor reads arrow textures).

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses where marked.
- The CStickInertiaTuner reading (new and removed rather than a renamed pair) is a judgement; the
  facts are above.
- Outside zUI: new 0x1d69c0 stores the CWrappedText vtable after calling the CRenderableString
  constructor (guess: an out-of-line `__ct__12CWrappedTextFv`). GetPopUp and
  CScrollSpec::CreateDisplayObj call it. New 0x421620 calls 0x39e210 and several zUI helpers. Both
  belong to other lists.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 22 | 21 | 1: 0x3b8b30 is `__dt__9CWrapSpecFv` |
| removed | 3 | 1 (GetSpacing__9CTeleType) | 2: LoadSpec__11CScrollText is 0x3a5920, `__dt__10CClockSpecFv` is 0x3b2bb0 |
| unsure | 3 | 1 (UiGetTextFromUser) | 2: 0x3a5920 is LoadSpec__11CScrollText; 0x3c1a70 is new |
| deviating (weak, slot-only) | 1 | 0 | 1: 0x39fe90 is new, AddNode removed |
| exact, identical-copy | 10 | 9 | 1: 0x3c1050 is the CStickInertiaTuner destructor |

Outside the list, in its owner ranges: 1 exact pair wrong (0x3b2bb0, crossed with the CWrapSpec
destructor).

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 529 pairs compared (callers, address loaders, vtable slots, ordered callee
sequences) and 70 paired vtables aligned slot by slot. 130 rows showed a difference, almost all the
uniform one-slot shift. The rest were callers that moved or were inlined (the CUIListBox and
CUIMapCtrl helpers split out, the zNetCnf UI commands, CLoadMenu's destructor). 2 callee
substitutions came out (AddNode; CTextSpec's copy constructor, which now calls the CUIVariableSpec
copy constructor it inlined before). 2 committed pairs were wrong: 0x3b2bb0 and 0x3c1050; the
in-list errors are counted above.

What misled it:

- The spec destructors: CClockSpec's and CWrapSpec's destructors are byte-identical once masked.
  CWrapSpec's grew in the release, so the tool gave the CClockSpec copy to CWrapSpec (`exact-callee`,
  `moved`) and left CClockSpec's removed. The vtable each destructor stores (and its table slot)
  decides.
- The tuner: the release table's class name differs, so the table went unpaired. The destructor was
  then paired by its bytes, and the UpdateUIVar slot fell to a position guess that took a new
  36-byte callback from another place in the file.
- LoadSpec__11CScrollText: its body is now empty, so similarity was useless. The tool took the
  neighbouring removed GetSpacing by position. The call site in CreateDisplayObj decides.
- AddNode: a 40-byte new function in AddNode's place, paired by slot only (similarity 0.075).

What cost the most time: telling the uniform vtable shift apart from real slot changes. Aligning
each paired table through the map does it at once. Suggestions:

- Pair destructors (and other byte-identical members) by the vtable address they store.
- Do not pair a function by position when its similarity is below about 0.1 and its caller sets are
  disjoint (AddNode, 0x3c1a70).
- Show in the sheet, for a function passed to a registration call (RegisterRebootCallback), the
  receiving call.
