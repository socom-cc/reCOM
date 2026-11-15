# audit-unmarked-b notes (2026-11-15, socom-port-audit-b): unmarked functions of list B against the reference ELF

List B: the 140 functions (14,620 bytes) of the user interface, 2D, animation, HUD and application code that the
reference ELF has and no `@socom-skeleton` fence names, for which `src/` has a definition of that name
(constructors, destructors, small members, a few free functions). Each was disassembled (`z.sh` / `dx.ps1`), its
members mapped with `off.py` / `dw.py` and its vtables with `vt.py`, and compared with the port's definition
instruction by instruction: stores, calls, loops, constants, member-initialisation order, base and member
constructor / destructor calls and the return value. No marker was added, moved or changed and no function moved.

## Result
| verdict | rows |
| --- | --- |
| MATCH | 135 |
| EQUIVALENT-IMPLICIT | 2 |
| KEPT | 3 |
| FIXED | 0 |
| NOT LOCATED | 0 |

No source change was needed: every body that differs at all does so through a recorded port model (the CPlainBmp
mixin, below) or through code the compiler generates the same way from the class definition.

## Findings
- The three KEPT rows are one deviation: in the ELF `CPlainBmp` has `UIVarMixin` as a second base at +0x80
  (DWARF), so `~CPlainBmp` 0x1d6260 and the destructors that inline it (`~CPopUpDialog` 0x1d4090, `~CycleItem`
  0x39aca0) end with `UIVarMixin::DetachUIVar(NULL)` (0x1d62a8 / 0x1d4150 / 0x39ad24). The port's `CPlainBmp`
  has no such base (`ztwod.h` records the model: `UIVarMixin` is declared in `zui.h`, after `ztwod.h`); its
  `m_mixin_uivar` stands for the mixin's `m_uivar`, and `CPlainBmp::LoadSpec` stores it without joining the
  variable's `m_attached_items` (recorded at `zui_2d.cpp` LoadSpec). The port's object is therefore never in a
  variable's list and its destructor has nothing to unlink. Consequences of the model (outside this list, in fenced
  functions): a variable that changes or is destroyed does not reach a plain image (its `UpdateUIVar` is empty in
  the ELF too, 0x393830, but the ELF's `Destroy` clears the image's `m_uivar`, the port's `m_mixin_uivar` keeps
  pointing at the variable's slot); `CHProgressBar`, which takes the same shortcut, does not get its
  `UpdateUIVar` calls on a change. Making `UIVarMixin` a base of `CPlainBmp` is a layout change for every image,
  button background, cycle option, progress bar, pop-up and list box; not done here.
- `zdb::CNodeEx::OnWeaponHit` 0x1cfea0 answers -1 and `OnAction` 0x1cfeb0 answers 0 in `v0`; the port's are
  `void`. Their callers discard `v0` (`CZProjectile::HandleImpact` 0x318334 and the other impact paths; no port
  caller of `OnAction`), and the overrides (`CZAnimEx::OnWeaponHit` 0x1cf660 answers 0, `CSealEx` 0x2a4d20 and
  `CNodeAction::OnAction` 0x1fe9c0 tail-call) are `void` in the port as well: no behaviour depends on it.
- `CMatrix::Rotate` 0x1bd170 and `CZNewHudMap::WorldToDraw` 0x3c8b10 (VU0 loops) test the count after the first
  point (do-while); the port's loop tests it first. Every caller passes 1 (29 `Rotate` calls, `WorldToDraw`
  hard-codes 1), so the bodies agree; the VU0 accumulation order (row 0, then 1, then 2, then the translation) is
  the port's order of additions.
- The `GetAssetLibs` family (C2DBitmap 0x1748a0, C2DBitmapPoly 0x2fd190, C2DFont 0x2ff490, C2DLine 0x2ffb20,
  C2DTriFan 0x300d90, C2DPoly 0x3019d0) already keeps the ELF quirk: after the search the ELF tests the iterator
  for NULL (`bnez v0` at 0x174918), so a library is added only to a list that has never held one.
- The copy constructors `CButtonSpec(CButtonSpec &)` 0x39f570 and `CTextSpec(CTextSpec &)` 0x3a0520 are the
  memberwise copies; the port's implicit ones produce the same: the base part through the port's
  `CDlgObjSpec(CDlgObjSpec &)` (a new `CUIVariableSpec` copy, as inlined from 0x39f5a8), the strings (`CSaferStr` is a
  `std::string`), the button states, and the `ActionItem` vector, whose element copy in the ELF
  (`init<PC10ActionItem>` 0x39ae40) is "Animation, Argument 0, State 1, then `operator=`" and in the port the
  `SOCOM_PORT` copy constructor (defaults, then `operator=`).
- Destructors compared member by member (offsets from DWARF): CLensFlareSaturate (`m_CameraLightDI` +0x9c),
  CLetterBox (`m_bitmap[2]` +0x20), CZPauseTest (`m_selections[5]` +0x1c, `m_background` +0x2d0), CTeamNames
  (`m_teamname[4]` +0x8c with `~CHudBrightText` 0x3bbfb0, `m_order[4]` +0x2ac, `m_background` +0x4f0,
  `m_healthdot[4]` +0x570), BitmapReticule (16 members, +0x20 .. +0x3430), CInGameWeaponSel (12 members, +0x20 ..
  +0x1018), CWeaponSel (11 members, +0x20 .. +0xbc0), C2DOrderItem, PoseBitmap, CZLineMap: the port's members
  have the ELF's types in the ELF's order, so the reverse-order destruction is the same.

## Runs (final tree = HEAD 86052025 + this note; no STOP, no exception, focus kept in every run)
- Stability (zSeal part 4's stability hook + its firing pad, 210 s): intro movie skipped with CROSS, briefing
  cameras with X, mission from 68 s; heap in use 23.02 MB at 90 s, 23.18 MB at 180-209 s; the HUD on screen
  (weapon box, compass, team names FOLLOWING).
- Win (`port/test-hooks/win`, -DSOCOM_HOOK_WIN): "EXIT: debrief open (objectives 3/7)" at 210.4 s, MISSION
  SUCCESSFUL on screen.
- Round trip (`port/test-hooks/state`, -DSOCOM_HOOK_MISSIONS=8): in use 18,666,708 B at return 1, then
  18,666,804 B at returns 2-8 (free 4,409,528 B, top chunk 232 B): flat and the same as at HEAD, as expected
  with no destructor changed.
- Front end (fake pad): main menu -> OPTIONS -> audio, video, controller selection, presets -> main menu.
- Default build (no hooks, no fake pad): dlgMenu at 15.8 s.

## Result table
Port locations are repository paths under `src/` (line of the definition at HEAD 86052025).

| address | function | port definition | verdict | evidence |
| --- | --- | --- | --- | --- |
| 0x174b10 | C2D::GetZAnimCmdType | gamez/zTwoD/ztwod.h:171 | MATCH | `j GetUICommandType` with a0 = 0; the port returns GetUICommandType(NULL) |
| 0x174b20 | C2D::SetMapOffset | gamez/zTwoD/ztwod.h:146 | MATCH | `jr ra`: empty |
| 0x177290 | CEntity::GetPosW | gamez/zEntity/zentity.h:187 | MATCH | m_node (+0x1c) + 0x30 = &m_matrix[3][0] |
| 0x178cc0 | C2DOrderItem::C2DOrderItem | gamez/zTwoD/ztwod.h:459 | MATCH | C2DBitmap, m_text, m_glowing_background, m_arrow ctors; m_Explanation, m_blinkTime, m_time 0, m_glow 0, m_trans_step 2.0, m_bArrow 0 in that order |
| 0x178d50 | CMD_TABLE::CMD_TABLE | Apps/FTS/game/orders.h:74 | MATCH | submenu (+0xd4) and submenu_items (+0xd0) 0 |
| 0x178d60 | C2DBitmap::~C2DBitmap | gamez/zTwoD/ztwod.h:225 | MATCH | vtable, ~C2D; C2DFade has no dtor |
| 0x17bbd0 | CSubMenu::CSubMenu | Apps/FTS/game/orders.h:45 | MATCH | the three words 0 |
| 0x17bfa0 | C2DString::SetTrans | gamez/zTwoD/ztwod.h:393 | MATCH | f12 to m_color.w (+0x5c) |
| 0x3b9470 | CFader::~CFader | Apps/FTS/hud/hud.h:152 | MATCH | vtable, C2DBitmap part (scalar members only) |
| 0x3bc680 | CLensFlareSaturate::~CLensFlareSaturate | Apps/FTS/hud/hud.h:192 | MATCH | ~DiIntersect on m_CameraLightDI (+0x9c), C2DBitmap part |
| 0x3bc710 | CLetterBox::~CLetterBox | Apps/FTS/hud/hud.h:130 | MATCH | __destroy_arr m_bitmap[2] (+0x20), ~C2D |
| 0x3bc790 | CZPauseTest::~CZPauseTest | Apps/FTS/hud/hud.h:772 | MATCH | m_background (+0x2d0), m_selections[5] (+0x1c), ~C2D |
| 0x3bc830 | CZDynamicRadioBitmap::~CZDynamicRadioBitmap | Apps/FTS/hud/hud.h:911 | MATCH | vtable, C2DBitmap part |
| 0x3bc8a0 | CZStaticRadioBitmap::~CZStaticRadioBitmap | Apps/FTS/hud/hud.h:897 | MATCH | vtable, C2DBitmap part |
| 0x3bc910 | CTeamMateNames::~CTeamMateNames | Apps/FTS/hud/hud.h:730 | MATCH | m_teamMateNames[15] (+0x1c), ~C2D |
| 0x3bc990 | CZActionBitmap::~CZActionBitmap | Apps/FTS/hud/hud.h:879 | MATCH | vtable, C2DBitmap part |
| 0x3bca00 | CTeamNames::~CTeamNames | Apps/FTS/hud/hud.h:620 | MATCH | m_healthdot[4], m_background, m_order[4], m_teamname[4] (~CHudBrightText), ~C2D |
| 0x3bcad0 | BitmapReticule::~BitmapReticule | Apps/FTS/hud/hud.h:845 | MATCH | m_enemy_name .. m_bitmap (16 members) in reverse, ~C2D |
| 0x3bccb0 | PoseBitmap::~PoseBitmap | gamez/zTwoD/ztwod.h:495 | MATCH | m_text (+0x9c), C2DBitmap part |
| 0x3bcd40 | CInGameWeaponSel::~CInGameWeaponSel | Apps/FTS/hud/hud.h:571 | MATCH | m_weaponselectedtitle .. m_weaponicon[4] (12 members) in reverse, ~C2D |
| 0x3bce90 | CWeaponSel::~CWeaponSel | Apps/FTS/hud/hud.h:478 | MATCH | m_magcount .. m_weaponicon[4] (CHudBrightText / C2DString / bitmaps) in reverse, ~C2D |
| 0x3c3080 | CZMapItem::PostDraw | Apps/FTS/hud/hud.h:1196 | MATCH | empty |
| 0x3c3090 | CZMapItem::Clip | Apps/FTS/hud/hud.h:1197 | MATCH | empty |
| 0x3c3450 | CZMapItem::~CZMapItem | Apps/FTS/hud/hud.h:1193 | MATCH | vtable, delete when asked |
| 0x3c34a0 | CZMapItem::Tick | Apps/FTS/hud/hud.h:1194 | MATCH | returns 0 |
| 0x3c34b0 | CZMapItem::Draw | Apps/FTS/hud/hud.h:1195 | MATCH | empty |
| 0x3c7210 | CZLineMap::~CZLineMap | Apps/FTS/hud/hud_linemap.cpp:242 | MATCH | every triangle (size, not active count) deleted, each wide line's segments then the line, every anchor bitmap; vectors, m_stringlist[32], m_linelist[400] destroyed |
| 0x3c8b10 | CZNewHudMap::WorldToDraw | Apps/FTS/hud/hud.h:410 | MATCH | m_matrix (+0x90) affine transform of one point, y through CalcDrawPos |
| 0x3c90f0 | CAiLinePtItr::FindValid | Apps/FTS/hud/hud_linemap.cpp:113 | MATCH | while IsValid: GetCellCenter, found -> WorldToDraw and stop, else next cell |
| 0x3c91c0 | CAiLinePtItr::IsValid | Apps/FTS/hud/hud_linemap.cpp:108 | MATCH | _it != data + size (4-byte CAiMapLoc) |
| 0x3cab20 | CAiLinePtItr::Advance | Apps/FTS/hud/hud_linemap.cpp:84 | MATCH | _it++ first, then FindValid's loop |
| 0x3cabe0 | CAiLinePtItr::GetPt | Apps/FTS/hud/hud_linemap.cpp:100 | MATCH | _pt.x, _pt.y through the hidden pointer |
| 0x3cc1d0 | CHudCompassAnchor::CHudCompassAnchor | Apps/FTS/hud/hud.h:212 | MATCH | m_icon, m_string ctors; +0x278..+0x284 (m_width, m_height, m_htex, m_texture) 0 |
| 0x3d9350 | CHudBrightText::CHudBrightText | Apps/FTS/hud/hud.h:205 | MATCH | C2DString ctor, own vtable, virtual SetTrans(128) = C2DString::SetTrans (vtable 0x4741a0 +0x20) |
| 0x17c830 | CCoreState::PreInit | gamez/zFTS/fts_state.h:76 | MATCH | empty |
| 0x17c840 | CCoreState::PreUnInit | gamez/zFTS/fts_state.h:78 | MATCH | empty |
| 0x320670 | CExitMenu::~CExitMenu | Apps/FTS/state/state.h:74 | MATCH | vtable (+0x884), ~CGameMenu; no own members (DWARF) |
| 0x3dcc00 | CMPExitMenu::~CMPExitMenu | Apps/FTS/state/state.h:85 | MATCH | vtable, ~CGameMenu; m_gameover is a byte |
| 0x3dde10 | CNetClock::GetTimeInGameSec | Apps/FTS/state/st_mpexit.cpp:105 | MATCH | fptoui(0.001 x (float)u32 m_total_time (+0x14)) |
| 0x3dde60 | CNetClock::GetTimeInRoundSec | Apps/FTS/state/st_mpexit.cpp:106 | MATCH | same with m_time_in_round (+0xc) |
| 0x3ddeb0 | CZSealBody::GetGameStats | Apps/FTS/state/st_mpexit.cpp:103 | MATCH | this + 0x46c = m_mp_stats |
| 0x3ddec0 | CZSealBody::GetRoundStats | Apps/FTS/state/st_mpexit.cpp:104 | MATCH | this + 0x4c0 = m_stats |
| 0x3de0b0 | CSealStats::GetBasesDestroyed | Apps/FTS/state/st_mpexit.cpp:100 | MATCH | m_bases_blown (+0x20) |
| 0x3de0c0 | CSealStats::GetRescues | Apps/FTS/state/st_mpexit.cpp:101 | MATCH | m_hostages_rescued (+0x24) |
| 0x3de0d0 | CSealStats::GetHitPct | Apps/FTS/state/st_mpexit.cpp:102 | MATCH | fptosi(0.5 + 100 x m_hit_percent) |
| 0x3de100 | CMPExitMenu::GetReaderFileName | Apps/FTS/state/st_mpexit.cpp:108 | MATCH | m_gameover (+0x890) ? "dlgMultiplayerFinal.rdr" : "dlgMultiplayerRound.rdr" (0x466bb0) |
| 0x1bc4a0 | zdb::CNode::GetBBox | gamez/zNode/znode_holding.cpp:45 | MATCH | m_use_parent_bbox (bit 30 of +0x5c) -> m_parent's, else &m_bbox (+0x40); the ELF unrolls the recursion three times |
| 0x1bd170 | CMatrix::Rotate | gamez/zMath/zmath.h:366 | MATCH | rows 0-2 only, in -> out; do-while (callers pass 1) |
| 0x1ca770 | zdb::CWorld::GetTexHandle | gamez/zNode/znode_holding.cpp:94 | MATCH | tail call CAssetMgr::m_assets.GetTexHandle(name) |
| 0x1cd910 | CZAnimArg::~CZAnimArg | gamez/zAnim/zanim.h:2152 | MATCH | vtable, delete when asked |
| 0x1cfea0 | zdb::CNodeEx::OnWeaponHit | gamez/zNode/znode.h:343 | MATCH | empty; -1 in v0 unread by every caller (port void) |
| 0x1cfeb0 | zdb::CNodeEx::OnAction | gamez/zNode/znode.h:344 | MATCH | empty; 0 in v0 unread (port void) |
| 0x1cfec0 | zdb::CNodeEx::OnMove | gamez/zNode/znode.h:345 | MATCH | empty |
| 0x1cfed0 | zdb::CNodeEx::OnDelete | gamez/zNode/znode.h:346 | MATCH | empty |
| 0x1cfee0 | zdb::CNodeEx::OnCopy | gamez/zNode/znode.h:347 | MATCH | empty |
| 0x1cfef0 | zdb::CNodeEx::OnDoubleClick | gamez/zNode/znode.h:348 | MATCH | empty |
| 0x1cff00 | zdb::CNodeEx::OnSelect | gamez/zNode/znode.h:349 | MATCH | empty |
| 0x1cff10 | CZAnimArgPnt3D::~CZAnimArgPnt3D | gamez/zAnim/zanim.h:2205 | MATCH | own vtable, CZAnimArg's, delete when asked |
| 0x1cff70 | CZAnimArgCmd::~CZAnimArgCmd | gamez/zAnim/zanim.h:2173 | MATCH | own vtable, CZAnimArg's, delete when asked |
| 0x1cffd0 | CZAnimArgValve::~CZAnimArgValve | gamez/zAnim/zanim.h:2215 | MATCH | own vtable, CZAnimArg's, delete when asked |
| 0x1d0030 | CZAnimArgNode::~CZAnimArgNode | gamez/zAnim/zanim.h:2195 | MATCH | own vtable, CZAnimArg's, delete when asked |
| 0x1d0320 | zdb::CVisual::Get2DVisual | gamez/zVisual/zvis.h:369 | MATCH | returns 0 |
| 0x1d13f0 | UIClanHasInvitations | gamez/zAnim/zanim_menu.cpp:2636 | MATCH | tail call theLobby.ClanHasInvitations() |
| 0x1d2c40 | UIGetClan | gamez/zAnim/zanim_menu.cpp:2010 | MATCH | tail call theLobby.GetClan() |
| 0x1d4090 | CPopUpDialog::~CPopUpDialog | gamez/zAnim/zanim_menu.cpp:897 | KEPT | own part matches (m_child deleted and cleared, m_no, m_yes, m_c2d170, m_text); the inlined CPlainBmp part's DetachUIVar is the CPlainBmp mixin model (see 0x1d6260) |
| 0x1d6300 | CPlainBmp::CPlainBmp | gamez/zTwoD/ztwod.h:304 | MATCH | mixin +0x84 0 (m_mixin_uivar), SetColor(128,128,128), SetTrans(128), m_isTrans, SetCanHandleInput(0), m_pulsing 0, m_period 1.0 in that order |
| 0x1d63e0 | UIVarMixin::~UIVarMixin | gamez/zUI/zui.h:549 | MATCH | vtable, DetachUIVar(NULL) |
| 0x1d6c10 | OnRemoveEquipment | gamez/zAnim/zanim_menu.cpp:654 | MATCH | primary / secondary refused; each selected character (UiCharSet mask, Advance inline) RemoveWeapon, UI vars refreshed on success; returns 1 |
| 0x1747e0 | C2DOrderItem::~C2DOrderItem | gamez/zTwoD/ztwod.h:468 | MATCH | m_arrow, m_glowing_background, m_text, C2DBitmap part |
| 0x1748a0 | C2DBitmap::GetAssetLibs | gamez/zTwoD/ztwod_bitmap.cpp:300 | MATCH | texture's library (NULL-iterator quirk kept), then the children's |
| 0x174a70 | C2D::Parse | gamez/zTwoD/ztwod.h:132 | MATCH | empty |
| 0x174a80 | C2D::HandlePad | gamez/zTwoD/ztwod.h:140 | MATCH | returns 0 |
| 0x174ab0 | C2D::SetActive | gamez/zTwoD/ztwod.h:142 | MATCH | empty |
| 0x174ac0 | C2D::SetNormal | gamez/zTwoD/ztwod.h:143 | MATCH | empty |
| 0x174af0 | C2D::ParseZAnimCmd | gamez/zTwoD/ztwod.h:139 | MATCH | returns 0 |
| 0x174b00 | C2D::TickZAnimCmd | gamez/zTwoD/ztwod.h:138 | MATCH | returns 0 |
| 0x1d6260 | CPlainBmp::~CPlainBmp | gamez/zTwoD/ztwod.h:322 | KEPT | ELF: mixin vtable, DetachUIVar(NULL) on +0x80, C2DBitmap part; port model (ztwod.h:297): no UIVarMixin base, the image never joins a variable's list, so nothing to unlink |
| 0x1ff970 | C2D::Draw(const CMatrix &, CTextureRelocMgr *) | gamez/zTwoD/ztwod.h:134 | MATCH | empty |
| 0x1ff980 | C2D::SetTrans | gamez/zTwoD/ztwod.h:144 | MATCH | empty |
| 0x1ff990 | C2D::Reset | gamez/zTwoD/ztwod.h:136 | MATCH | empty |
| 0x200070 | C2DMessageString::~C2DMessageString | gamez/zTwoD/ztwod.h:421 | MATCH | m_text std::string (+0x94), ~C2DString |
| 0x2000f0 | C2D::Tick | gamez/zTwoD/ztwod.h:137 | MATCH | empty |
| 0x2fd190 | C2DBitmapPoly::GetAssetLibs | gamez/zTwoD/c2dbitmap_poly.cpp:263 | MATCH | m_texture (+0x1e0) library (quirk kept), children |
| 0x2fd290 | C2DBitmapPoly::~C2DBitmapPoly | gamez/zTwoD/ztwod.h:280 | MATCH | __destroy_arr m_tris[2] (+0x40), ~C2D |
| 0x2fd310 | C2DPoly::~C2DPoly | gamez/zTwoD/ztwod.h:253 | MATCH | vtable, ~C2D |
| 0x2fe6f0 | C2DBitmapPoly::C2DBitmapPoly | gamez/zTwoD/c2dbitmap_poly.cpp:42 | MATCH | C2D / C2DFade defaults, m_tris ctors, m_texture 0, UVs (0,0,0,1,1,1) / (0,0,1,1,1,0), colours 128, SetTrans(128) |
| 0x2fe8e0 | C2DLine::~C2DLine | gamez/zTwoD/ztwod_holding.cpp:134 | MATCH | vtable, ~C2D |
| 0x2ff490 | C2DFont::GetAssetLibs | gamez/zTwoD/ztwod_font.cpp:190 | MATCH | m_pTexHandle (+0x10) texture's library (quirk kept); no children |
| 0x2ffb20 | C2DLine::GetAssetLibs | gamez/zTwoD/c2dline.cpp:362 | MATCH | m_texture (+0x90) library (quirk kept), children |
| 0x300d90 | C2DTriFan::GetAssetLibs | gamez/zTwoD/ztwod_poly.cpp:328 | MATCH | m_texture (+0x28) library (quirk kept), children |
| 0x3019d0 | C2DPoly::GetAssetLibs | gamez/zTwoD/ztwod_poly.cpp:280 | MATCH | m_texture (+0xc0) library (quirk kept), children |
| 0x3030a0 | zdb::CTextureRelocMgr::AddToBatch | gamez/zTexture/ztex.h:282 | MATCH | empty |
| 0x3030b0 | zdb::CTextureRelocMgr::EndBatchReloc | gamez/zTexture/ztex.h:284 | MATCH | empty |
| 0x3030c0 | zdb::CTextureRelocMgr::StartBatchReloc | gamez/zTexture/ztex.h:286 | MATCH | empty |
| 0x3030d0 | zdb::CTextureRelocMgr::ClearAll | gamez/zTexture/ztex.h:283 | MATCH | empty |
| 0x382d30 | CDlgObjSpec::NumChildren | gamez/zUI/zui.h:233 | MATCH | returns 0 |
| 0x382d50 | CDlgObjSpec::GetChild | gamez/zUI/zui.h:231 | MATCH | returns 0 |
| 0x382d60 | CDlgObjSpec::HasChildren | gamez/zUI/zui.h:232 | MATCH | returns 0 |
| 0x382ef0 | CGameMenu::GetReaderFileName | gamez/zGame/zgame.h:197 | MATCH | m_ReaderName (+0x874) characters |
| 0x384280 | ActionItem::ActionItem | gamez/zUI/zui.h:533 | MATCH | Type 0, Animation / Argument 0, State 1, PadButton 16 |
| 0x384ee0 | GetLocalAnims | gamez/zUI/zui.cpp:165 | MATCH | returns glocal_anims |
| 0x387ad0 | C2DButton::SetNormal | gamez/zTwoD/ztwod.h:716 | MATCH | CanHandleInput test, _fPressedTime 0, NORMAL state (image, scale, colour, SetTrans(100), glow type and fade, Update, pulse) |
| 0x389d20 | C2DButton::SetPressed | gamez/zTwoD/ztwod.h:728 | MATCH | as SetNormal with 0.2 and PRESSED |
| 0x38fcc0 | C3StateButton::~C3StateButton | gamez/zTwoD/ztwod.h:619 | MATCH | _strCaption (+0x20), ~C2D |
| 0x393800 | CPlainBmp::SetMapOffset | gamez/zTwoD/ztwod.h:326 | MATCH | tail call SetPos(x, y, x + m_iWidth, y + m_iHeight) |
| 0x393820 | CPlainBmp::Draw(CCamera *) | gamez/zTwoD/ztwod.h:323 | MATCH | tail call C2DBitmap::Draw |
| 0x393830 | CPlainBmp::UpdateUIVar | gamez/zTwoD/ztwod.h:327 | MATCH | empty |
| 0x393840 | C2DButton::SetCanHandleInput | gamez/zTwoD/ztwod.h:706 | MATCH | flag stored; on: virtual SetNormal (vtable +0x40); off: DISABLED state (SetFadeTimeMaxMin 0x38a870 and SetPulse 0x38a810 are the port's inline stores) |
| 0x393940 | C2DButton::DrawBackground | gamez/zTwoD/ztwod.h:736 | MATCH | centred caption: SetPos(-(m_iWidth/2), 0, (int)(_fWidth/2), (int)_fHeight); then the image's Draw(matrix, reloc) |
| 0x393a00 | C2DButton::SetBackgroundAlpha | gamez/zTwoD/ztwod.h:727 | MATCH | image SetTrans(128 x alpha) (C2DBitmap::SetTrans) |
| 0x394b40 | CClockSpec::~CClockSpec | gamez/zUI/zui.h:451 | MATCH | CTextSpec part (+0x14, +0x8 strings), ~CDlgObjSpec |
| 0x394d40 | CTextSpec::~CTextSpec | gamez/zUI/zui.h:253 | MATCH | strings +0x14, +0x8, ~CDlgObjSpec |
| 0x395560 | CButtonSpec::~CButtonSpec | gamez/zUI/zui.h:300 | MATCH | m_font, m_animations (each ~ActionItem), m_caption, the four state names, ~CDlgObjSpec |
| 0x396270 | CImageSpec::~CImageSpec | gamez/zUI/zui.h:271 | MATCH | m_filename (+0x8), ~CDlgObjSpec |
| 0x39a610 | CWrapSpec::~CWrapSpec | gamez/zUI/zui.h:361 | MATCH | CTextSpec part, ~CDlgObjSpec |
| 0x39aca0 | CycleItem::~CycleItem | gamez/zUI/zui.h:675 | KEPT | own part matches (m_picture +0xb0, ~ActionItem m_action +0xa0); the inlined CPlainBmp part's DetachUIVar is the mixin model (see 0x1d6260) |
| 0x39ad80 | CCounterSpec::~CCounterSpec | gamez/zUI/zui.h:436 | MATCH | m_valVar (+0x30), CTextSpec part, ~CDlgObjSpec |
| 0x39f570 | CButtonSpec::CButtonSpec(CButtonSpec &) | gamez/zUI/zui.h:281 (implicit) | EQUIVALENT-IMPLICIT | memberwise copy; implicit copy = CDlgObjSpec(CDlgObjSpec &) (zui_cleanup.cpp:226) + members; ActionItem copy = defaults + operator= as init 0x39ae40 |
| 0x3a0520 | CTextSpec::CTextSpec(CTextSpec &) | gamez/zUI/zui.h:241 (implicit) | EQUIVALENT-IMPLICIT | memberwise copy of the base part, two strings, scale, two flags and the colour |
| 0x3a1350 | CTickerSpec::~CTickerSpec | gamez/zUI/zui.h:383 | MATCH | CTextSpec part, ~CDlgObjSpec (deletes m_uivar) |
| 0x3a1410 | CTickerSpec::GetType | gamez/zUI/zui.h:386 | MATCH | "TICKERTAPETEXT" |
| 0x3a1640 | CHProgressBarSpec::~CHProgressBarSpec | gamez/zUI/zui.h:404 | MATCH | m_leadingEdgeNode (+0x20), CImageSpec part, ~CDlgObjSpec |
| 0x3a16f0 | CHProgressBarSpec::GetType | gamez/zUI/zui.h:407 | MATCH | "PROGRESSBAR" |
| 0x3a1b00 | CWrapSpec::GetType | gamez/zUI/zui.h:364 | MATCH | "WRAPPEDTEXT" |
| 0x3a1b10 | CTtySpec::~CTtySpec | gamez/zUI/zui.h:337 | MATCH | CTextSpec part, ~CDlgObjSpec |
| 0x3a1bd0 | CTtySpec::GetType | gamez/zUI/zui.h:340 | MATCH | "TELETYPE" |
| 0x3a1be0 | CTextSpec::GetType | gamez/zUI/zui.h:256 | MATCH | "TEXT" |
| 0x3a1bf0 | CImageSpec::GetType | gamez/zUI/zui.h:274 | MATCH | "IMAGE" |
| 0x3a1c00 | CButtonSpec::GetType | gamez/zUI/zui.h:303 | MATCH | "BUTTON" |
| 0x3a2750 | SystemTuner::~SystemTuner | gamez/zUI/zui_tuner.cpp:42 | MATCH | vtable, ~UIVarMixin (DetachUIVar(NULL)) |
| 0x3a27c0 | CSoundTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:62 | MATCH | REAL only (the INTEGER branch after the test is dead in the ELF): SetGroupVol(0, value) |
| 0x3a2820 | CMusicTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:74 | MATCH | REAL only: SetGroupVol(1, value) |
| 0x3a2880 | CBrightnessTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:98 | MATCH | REAL, INTEGER, else 0: tail call CVideo::Brightness |
| 0x3a28c0 | CStickSensitivityTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:114 | MATCH | REAL only, pad 0 when present: SetSensitivity(1, value) |
| 0x3a2920 | CStickAccelerationTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:126 | MATCH | REAL only, pad 0: SetAcceleration(1, value) |
| 0x3a2980 | CStickDeadzoneTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:138 | MATCH | REAL only: 0.02 + value, at most 1, pad 0: SetDeadZone(1, value) |
| 0x3a2a10 | SystemTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:43 | MATCH | empty |
| 0x3a2a20 | CDialogTuner::UpdateUIVar | gamez/zUI/zui_tuner.cpp:86 | MATCH | REAL only: SetGroupVol(2, value) |
| 0x3a3330 | CSoftKeyboard::Local::Decr | gamez/zUI/zui_skb.cpp:1875 | MATCH | i - 1 |
| 0x3a3340 | CSoftKeyboard::Local::Incr | gamez/zUI/zui_skb.cpp:1869 | MATCH | i + 1 |
