# Audit of list small-b (2026-11-19, socom-port-audit-small-b)

296 small functions (24,812 bytes, each under 200 bytes) in 29 files: Apps/FTS/hud (hud_devtext,
hud_objectives, hud_pausemenu, hud_posebitmap), zAI ai_events, zConsole con_packet, zFTS
(fts_missioncam, fts_net_game, fts_net_persona, fts_network, fts_objectivecam), zGame game_main,
zMPEG audiodec, zReader (zrdr_archive, zreader_holding), zRender zrndr_pipe, zSave zsav_module,
zSeal (seal_aimoves, seal_tasks, seal_weapon), zTwoD c2dbitmap_poly, zUI (zui_cleanup, zui_spec),
zUtil zutil_holding, zValve valve_list, zVisual (vis_decal, vis_mesh), zWeapon (zwep_projectile,
zwep_weapon). HEAD 7f6dabc0 (104655e3 at the end: small-a's commit, no shared file). Judged file by
file in the scan's rank order, from the by-file packets.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 284 |
| DEFECT-FIXED | 10 (A 0, B 2, C 8) |
| DEVIATION-KEPT | 2 |
| UNJUDGED | 0 |

Defect rate 10 / 296 (B 2, C 8).

Fixes:
- B, #101 CTFireMode::Tick: dT is zeroed only without an AI (sw zero 0x2bd178; the AI path 0x2bd184
  leaves it); the port zeroed it always, so the anim lost the frame's remaining time after an AI's
  ai::FIREMODE (m8's on_aware4 uses it).
- B, #82 CTValve::Tick: the same, dT zeroed only on the no-AI path (0x2b44d0).
- C, #134 CRadioStripSpec::Copy / #140 CHandlerButtonSpec::Copy: the ELF moves the children to the
  copy and clears the original's count / pointer (0x39f558, 0x3a0254); the header's inline copy
  ctors deep-copied them with a wrong "freed objects" reason. Header edit file
  `zui_h_spec_copy_move.txt` (not merged here; built into the test trees through shared.txt).
- C, #80 CSaveModule::CSaveModule: the name's _strdup tagged "zsav_module.cpp" 27 (0x3f70d8), not
  the port's __FILE__ / __LINE__.
- C, #205 CFlyout::~CFlyout: CNode::Delete only when m_node is set (0x317070).
- C, #95 CTPaint::Tick: the port-only NULL test before SetRegionType removed (0x2b989c).
- C, #176 CMeshDecal::FreeMem and the inline copy in #178 CMeshDecalPool::RecycleTick: the block is
  freed by its address's low 28 bits (dsll32 / dsrl32 4, 0x312e38, 0x3131ec).
- C, #170 CFileIO::fwrite(const char *): the length word is written for a NULL string too
  (0x304b08..0x304b18), as CIO::fwrite.

Kept deviations (reasons in the code): #86 CTSpecial::Begin tests the controller before Debug (as
End, #25 of medium-seal-c: the port's trace Debug reads its receiver); #68 _zrdr::_zrdr zeroes type,
unused, length and array where the ELF clears only isclone / packed (a CRdrFile freed after a failed
ReadPacked runs zrdr_freearray on them; CRdrFile's ctor 0x23cf30 leaves them unset too).

ELF quirks kept (already noted in the code): #245 SetDecalSetName's unguarded _strdup; #21
CAiEvent::Open drops the in-use events; #183 CDecalPool::RecycleTick counts on this pool but takes
from CDecal::m_tempPool; #254 / #257 / #173 / #81 return a v0 no caller reads (the port's void).

Float checks: GetAimDot / IsInRange as (x x + y y) + z z (adda / madd); every compare's form agrees
(c.eq.s / c.le.s / c.lt.s with the branch sense of the port's expression: #17, #84, #98, #10, #199,
#209, #211); literals 0x3dcccccd, 0x47c35000, 0x47c3504d, 0x3f000000, 0x42fe0000, 0xbf800000,
0x40a00000, 0xc2c60000 equal to the port's spellings.

SEAL_STANCE lead: the functions of this list that carry a stance (CTStance::Begin / End, #85 / #84)
pass get_stance's numbers (-1..3, the DWARF values) through (s8) casts and never name an
enumerator, so the port enum's shifted names (0..5) do not reach them. Any code that compares a
stance with SEAL_STANCE::STANCE_* by name is off by one (not on this list).

Leads for other lists:
- zUI: docs/port/notes/mod-zui.md lines 104-105 and 223 (port deviations) describe the old deep copy
  of #134 / #140; stale once zui_h_spec_copy_move.txt is merged.
- zUI header: CWrappedText's ctor also zeroes m_width / m_spacing and CRadioStrip's m_init (the ELF
  leaves them; LoadSpec sets them; recorded in zui.h).
- zMath header: CBits::m_bits is u32 where the ELF shifts it arithmetically (sra 0x17f2fc): same for
  any real bit count.

What the packets lacked: the slot +0x78 method of #14's C2DString (the packet named another class's
method; vt.py 0x472cb0 gives ClearAndWipe); the remove_if functor _tick (0x1800f0) behind #19; the
CGame DWARF offsets for #57 (dw.py); the CSubMesh / CMeshDecal offsets (no DWARF; zvis.h comments);
the CRdrFile ctor (0x23cf30) and the default-ctor users for #68; the callers of the vector init that
runs CDesignDlgObj::operator= (0x39f1f4 in CUIMapCtrlSpec::Copy) for #134 / #140; TASK_* layouts and
get_stance for the seal_tasks rows (source); the zanim command loop's use of *dT (anim_main.cpp) to
grade #82 / #101; TypeGameState's size for #35. Roughly 14 functions needed a lookup outside the packet.

Runs: default build linked (audit-small-b-default, 0 undefined, with the zui.h edit file applied
through shared.txt); one fake-pad m8 smoke run (pad_start.txt, smoke-m8, 170 s: the mission ran from
54 s to the end, about 96 s after the cameras, AI scripts, goto / look / blood traces, no fault).

## Verdicts

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 117 | 0x2fe0b0 | 196 | C2DBitmapPoly::FlipImage_Yaxis() | c2dbitmap_poly.cpp | MATCH | | Six whole-vertex copies in order b0<-b2, b2<-a0, a0<-b0, a2<-a1, a1<-b1, b1<-a2 (m_tris[0].m_vertex +0xd0/e0/f0, m_tris[1] +0x1a0/1b0/1c0; 0x2fe0b0..0x2fe170): agree. The scan's stores are the port's out-of-line copy helper. |
| 118 | 0x2fe180 | 196 | C2DBitmapPoly::FlipImage_Xaxis() | c2dbitmap_poly.cpp | MATCH | | a0<-a1, a1<-b0, b0<-a0, b1<-b2, b2<-a2, a2<-b1 (0x2fe180..0x2fe240): agree. |
| 116 | 0x2fe020 | 132 | C2DBitmapPoly::FlipImage_XYaxis() | c2dbitmap_poly.cpp | MATCH | | a0<-a2, a2<-b0, b1<-b0, b0<-a0 (0x2fe020..0x2fe0a0): agree. |
| 119 | 0x2fe250 | 108 | C2DBitmapPoly::SetUseFrameBufferAlpha(bool) | c2dbitmap_poly.cpp | MATCH | | Bit 4 of +0x15 (m_isFrameAlpha) = a1 & 1, others kept (0x2fe254..0x2fe280), then slot +0x44 on m_tris[0] (+0x40) and m_tris[1] (+0x110) with the same bool; the port's direct calls reach the same C2DPoly method (member objects). |
| 120 | 0x2fe2c0 | 8 | C2DBitmapPoly::GetTrans() | c2dbitmap_poly.cpp | MATCH | | Tail call C2DPoly::GetTrans on m_tris[0] (returns m_RGB[0][3]); the port reads the same word directly. |
| 121 | 0x2fe2d0 | 80 | C2DBitmapPoly::SetTrans(float) | c2dbitmap_poly.cpp | MATCH | | Slot +0x20 SetTrans(f12) on both triangles: agree. |
| 122 | 0x2fe320 | 96 | C2DBitmapPoly::SetColor(float, float, float) | c2dbitmap_poly.cpp | MATCH | | C2DPoly::SetColor(r, g, b) on m_tris[0] then m_tris[1]: agree. |
| 123 | 0x2fe380 | 144 | C2DBitmapPoly::SetUV(float, float, float, float, float, float, float, float) | c2dbitmap_poly.cpp | MATCH | | tri 0 (v0, v1, v2), tri 1 (v0, v2, v3) through f12..f17 (0x2fe3c8..0x2fe3e4): agree. |
| 124 | 0x2fe410 | 132 | C2DBitmapPoly::SetUV(float, float, float, float) | c2dbitmap_poly.cpp | MATCH | | tri 0 (u0 v0, u0 v1, u1 v1), tri 1 (u0 v0, u1 v1, u1 v0) (0x2fe434..0x2fe470): agree. |
| 125 | 0x2fe4a0 | 172 | C2DBitmapPoly::SetCenterPos(PNT2D, float, float) | c2dbitmap_poly.cpp | MATCH | | half = 0.5f * w / h (0x3f00 word), left/right = x -/+ hw, top/bottom = y -/+ hh, tri 0 (l t, l b, r b), tri 1 (l t, r b, r t) (0x2fe4e0..0x2fe528): agree. |
| 126 | 0x2fe550 | 144 | C2DBitmapPoly::SetPos(float, float, float, float, float, float, float, float) | c2dbitmap_poly.cpp | MATCH | | tri 0 (v0, v1, v2), tri 1 (v0, v2, v3), as SetUV: agree. |
| 127 | 0x2fe5e0 | 96 | C2DBitmapPoly::Draw(zdb::CCamera*) | c2dbitmap_poly.cpp | MATCH | | Non-virtual C2D::IsOn, then slot +0xc Draw(camera) on both triangles: agree. |
| 128 | 0x2fe640 | 164 | C2DBitmapPoly::Load(float, float, float, float, float, float, float, float, zdb::CTexture*) | c2dbitmap_poly.cpp | MATCH | | m_texture (+0x1e0) = texture first (0x2fe670), then C2DPoly::Load (v0, v1, v2, tex) and (v0, v2, v3, tex): agree. The scan's +0x1a8 is the port's layout. |
| 143 | 0x3a04a0 | 128 | CScrollSpec::Copy() | zui_cleanup.cpp | MATCH | | new(52), CTextSpec(CTextSpec &), CWrapSpec members +0x24 / +0x28 / +0x2c and own +0x30 copied, vtables: the port's implicit memberwise copy (the scan's CWrapSpec call is the port's out-of-line implicit ctor). |
| 145 | 0x3a0840 | 176 | CTtySpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_cleanup.cpp | MATCH | | new(1168), CRenderableString, CTeleType vtables, CPlainBmp m_cursor (+0x3e0), m_sound (+0x480) / m_pause (+0x484) 0, SetFont(font), LoadSpec(*this), returned: agree (header ctor). |
| 138 | 0x39fd20 | 136 | CSliderBarSpec::Copy() | zui_cleanup.cpp | MATCH | | new(248), CButtonSpec copy, m_knobTexture (+0xe8) string copy, m_knobSize (+0xec / +0xf0, copied through FPRs: same bits), m_intervals (+0xf4): the implicit copy. |
| 144 | 0x3a0690 | 136 | CWrapSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_cleanup.cpp | MATCH | | new(184), CRenderableString, CWrappedText vtables, m_height (+0xb4) -1, SetFont, LoadSpec: agree; the header ctor's extra zeroing of m_width / m_spacing is recorded there (LoadSpec sets them). |
| 136 | 0x39fa30 | 144 | CTickerSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_cleanup.cpp | MATCH | | new(188), CRenderableString, CTickerTapeText vtables, +0xac..+0xb8 zeroed (four floats), SetFont, LoadSpec: agree. |
| 133 | 0x39f460 | 152 | CRadioStripSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_cleanup.cpp | MATCH | | new(1056), C2DButton, CRadioStrip vtable, m_selection (+0x410) 0, _strCaption (+0x20) SetFont, LoadSpec(this, NULL), InitializeButton(strip, reloc), returned. The header ctor also clears m_init (+0x414; LoadSpec sets it). |
| 135 | 0x39f9b0 | 124 | CCycleButtonSpec::Copy() | zui_cleanup.cpp | MATCH | | new(252), CButtonSpec copy, m_margin (+0xe8 / +0xec) and the m_options pointer vector (+0xf0) copied (pointers shared, as the header says): the implicit copy. |
| 140 | 0x3a0210 | 96 | CHandlerButtonSpec::Copy() | zui_cleanup.cpp | DEFECT-FIXED | C | new(236), CButtonSpec copy, vtable, m_child (+0xe8) copied, then the ORIGINAL's m_child zeroed (sw zero,0xe8(s1) at 0x3a0254): the ELF moves the child. The header's inline copy ctor deep-copied it, with a wrong "freed objects" reason. Fix in edit file zui_h_spec_copy_move.txt (header). Same result where the original dies after the copy. |
| 134 | 0x39f500 | 108 | CRadioStripSpec::Copy() | zui_cleanup.cpp | DEFECT-FIXED | C | new(244), CButtonSpec copy, vtable, the child-pointer vector_pod copied (0x39f548), then the original's count (+0xec, NumChildren's) zeroed at 0x39f558: a move, not the shared pointers the header comment describes. Fix in edit file zui_h_spec_copy_move.txt. |
| 129 | 0x39ed20 | 180 | CUIMapCtrlSpec::~CUIMapCtrlSpec() | zui_cleanup.cpp | MATCH | | m_animations (+0x24) then m_elements (+0x18) destroyed, then the inline ~CDlgObjSpec (m_uivar deleted): the member / base chain of the port's empty body in the header's member order. |
| 130 | 0x39ede0 | 12 | CUIMapCtrlSpec::GetType() | zui_cleanup.cpp | MATCH | | "MAPCONTROL". |
| 131 | 0x39edf0 | 148 | CUIVariableSpec::~CUIVariableSpec() | zui_cleanup.cpp | MATCH | | m_name freed if set ("zui_cleanup.cpp" 302) and zeroed, m_array DeleteChildren then deleting ~_zrdr, ~CSTable (+0x8): agree. |
| 132 | 0x39ee90 | 172 | CUIVariableSpec::CUIVariableSpec(CUIVariableSpec*) | zui_cleanup.cpp | MATCH | | m_name / m_array 0, CSTable(0, 1024), _strdup(other->m_name, 285) unguarded, new(8) _zrdr(other->m_array, &m_stable) when set, m_type copied as a byte (lb / sb 0x39ef1c; the port's u32 holds 1..3). |
| 137 | 0x39fbe0 | 56 | CCheckBoxSpec::Copy() | zui_cleanup.cpp | MATCH | | new(260) + CCheckBoxSpec(CCheckBoxSpec &). |
| 139 | 0x3a0180 | 144 | CHandlerButtonSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_cleanup.cpp | MATCH | | new(1040), C2DButton, CHandlerButton vtable, _strCaption SetFont, LoadSpec(*this), InitializeButton(button, reloc), returned: agree. |
| 141 | 0x3a03e0 | 12 | CHandlerButtonSpec::HasChildren() const | zui_cleanup.cpp | MATCH | | m_child (+0xe8) != 0. |
| 142 | 0x3a03f0 | 176 | CScrollSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_cleanup.cpp | MATCH | | new(204), CRenderableString, CWrappedText then CScrollText vtables, m_height -1, +0xbc byte 0, +0xc0..+0xc8 0, SetFont, LoadSpec: agree (header ctors). |
| 146 | 0x3a0a20 | 112 | CTextSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_cleanup.cpp | MATCH | | new(172), CRenderableString, SetFont(font), LoadSpec(*this), returned. |
| 147 | 0x3a0f40 | 196 | CDlgObjSpec::~CDlgObjSpec() | zui_cleanup.cpp | MATCH | | m_uivar (+0x4) deleted when set, its dtor inline (as #131): agree. |
| 148 | 0x3a1100 | 132 | ActionItem::~ActionItem() | zui_cleanup.cpp | MATCH | | Animation (+0x4) freed (line 23) and zeroed, Argument (+0x8) freed (24) and zeroed: agree. |
| 149 | 0x3a1190 | 12 | CRadioStripSpec::HasChildren() const | zui_cleanup.cpp | MATCH | | count (+0xec) != 0. |
| 150 | 0x3a11a0 | 8 | CRadioStripSpec::NumChildren() const | zui_cleanup.cpp | MATCH | | count (+0xec) returned. |
| 151 | 0x3a11b0 | 20 | CRadioStripSpec::GetChild(int) const | zui_cleanup.cpp | MATCH | | data (+0xf0)[i], unchecked. |
| 152 | 0x3a11d0 | 12 | CRadioStripSpec::GetType() | zui_cleanup.cpp | MATCH | | "RADIOSTRIP". |
| 153 | 0x3a1340 | 12 | CCycleButtonSpec::GetType() | zui_cleanup.cpp | MATCH | | "CYCLEBUTTON". |
| 154 | 0x3a1630 | 12 | CCheckBoxSpec::GetType() | zui_cleanup.cpp | MATCH | | "CHECKBOX". |
| 155 | 0x3a1850 | 12 | CSliderBarSpec::GetType() | zui_cleanup.cpp | MATCH | | "SLIDERBAR". |
| 156 | 0x3a19e0 | 12 | CUIListBoxSpec::GetType() | zui_cleanup.cpp | MATCH | | "LISTBOX". |
| 157 | 0x3a19f0 | 12 | CHandlerButtonSpec::GetType() | zui_cleanup.cpp | MATCH | | "HANDLERBUTTON". |
| 158 | 0x3a1a00 | 48 | CHandlerButtonSpec::NumChildren() const | zui_cleanup.cpp | MATCH | | Virtual HasChildren (slot +0x1c), 1 or 0: agree. |
| 159 | 0x3a1a30 | 8 | CHandlerButtonSpec::GetChild(int) const | zui_cleanup.cpp | MATCH | | m_child (+0xe8), index ignored. |
| 160 | 0x3a1a40 | 168 | CScrollSpec::~CScrollSpec() | zui_cleanup.cpp | MATCH | | Vtables down to CTextSpec, its strings +0x14 and +0x8, ~CDlgObjSpec, deleting flag: the compiler chain of the empty body. |
| 161 | 0x3a1af0 | 12 | CScrollSpec::GetType() | zui_cleanup.cpp | MATCH | | "SCROLLINGTEXT". |
| 113 | 0x2c0620 | 44 | CZSealBody::WepWaitOn() | seal_weapon.cpp | MATCH | | m_wep_upT / waitT / downT / sumT (+0xdd0..+0xddc) = 0x3dcccccd, 0x47c35000, 0x3f000000, 0x47c3504d: the port's spellings give the same words. The scan's offsets are the port's layout. |
| 114 | 0x2c0650 | 20 | CZSealBody::WepWaitOff() | seal_weapon.cpp | MATCH | | The four timers zeroed. |
| 111 | 0x2bfe60 | 112 | CZSealBody::SetAimDirR(CPnt3D const*, bool) | seal_weapon.cpp | MATCH | | CalcAimGoal(&m_aim_dir +0x10a0, dir, &m_aim_goal +0x10ac), result & 0xff; 0 and reset -> m_aim_goal = CPnt3D::unit_nz (three words); the masked result returned: agree. |
| 108 | 0x2bf210 | 44 | CZSealBody::GetAimDot() | seal_weapon.cpp | MATCH | | (dir.x goal.x + dir.y goal.y) + dir.z goal.z (mul, mul, adda / madd 0x2bf228..0x2bf238) in $f0: the port's order. |
| 109 | 0x2bf820 | 116 | CZSealBody::GetFP(CPnt3D&) | seal_weapon.cpp | MATCH | | m_curr_firept (+0x111c) set: out = m_curr_firepos (+0x1110), Add(GetPosW() slot +0xc, &out), v0 1; else GetFirepointPos(out, "firepoint")'s result: agree. |
| 110 | 0x2bf8a0 | 116 | CZSealBody::GetAP(CPnt3D&) | seal_weapon.cpp | MATCH | | As #109 with m_curr_aimpt (+0x110c) / m_curr_aimpos (+0x1100) and "aimpoint": agree. |
| 112 | 0x2c00a0 | 152 | CZSealBody::GetFirepointNode(char const*) | seal_weapon.cpp | MATCH | | m_kit (+0x520) GetCurItemType, m_weapons.data_ (+0xf80)[item] NULL -> 0, BodyWepPart(this, item & 0xff) NULL -> 0, name NULL or part->m_node (+0xc) NULL -> m_node, else slot +0x24 FindChild(name, false): agree (items 0..4, so the port's (s8) index is the ELF's). |
| 115 | 0x2c0670 | 20 | CZSealBody::GetWeaponState() const | seal_weapon.cpp | MATCH | | m_weapon_state (+0xe54) & ~0x10, & 0xff. |
| 7 | 0x3c21c0 | 80 | CZObjectiveList::Init() | hud_objectives.cpp | MATCH | | GetTexHandle "hud_checkbox.tif" -> m_unfinished_tex (+0x9c4), "hud_check.tif" -> m_completed_tex (+0x9c8), "team_background.tif" -> m_background_tex (+0x9c0), in that order: agree. |
| 5 | 0x3c0960 | 136 | CZObjectiveList::SetCurColor(int) | hud_objectives.cpp | MATCH | | previous in [0, size_ +0x20): its string's colour x / y / z (+0x50..+0x58) read, then m_selected_objective (+0x9b8) in range: written to that string; no write otherwise: agree. |
| 2 | 0x3bf8c0 | 20 | CZObjectiveList::IsPlayingAnimation() | hud_objectives.cpp | MATCH | | Tail call CZHudMissionCams::IsPlaying on theHUD's m_missioncams (+0x14590 in the ELF; the scan's 0x12b14 is the port's CHUD layout). |
| 3 | 0x3bfd60 | 8 | CZObjectiveList::GetCurrentObjectiveRetainer() const | hud_objectives.cpp | MATCH | | m_cur_selected_objective (+0x9bc). |
| 4 | 0x3bff60 | 136 | CZObjectiveList::SelectObjective() | hud_objectives.cpp | MATCH | | GetObjective(m_selected_objective) NULL -> out, m_missioncams.IsPlaying -> out, letterbox m_slidedir (theHUD +0x143a0, lbu) == SLIDE_OUT (2) -> out, else PlayCamera(objective, false): agree. |
| 6 | 0x3c09f0 | 132 | CZObjectiveList::IsAnySelectable() const | hud_objectives.cpp | MATCH | | i over m_objectivenames.size_ (+0x20), m_vecSelectable (+0x34) test_bit(i), 1 on the first set bit, else 0: agree. |
| 19 | 0x17f780 | 184 | CAiEvent::Tick(float, void*) | ai_events.cpp | MATCH | | TickVisMaps(dT), then remove_if(m_inuse, _tick{dT, &m_pool}) and erase of the tail; _tick (0x1800f0, ref.dis) runs CAiEvent::Tick(dT) per event and push_backs the expired ones on m_pool: the port's erase loop keeps the same order in both lists; returns 0. The port-only trace is under SOCOM_PORT (scan items). |
| 18 | 0x17f270 | 184 | CAiEvent::Initalize() | ai_events.cpp | MATCH | | m_duration 0, m_pos = CPnt3D::zero, m_type (bits 1-15 of +0x1a) 0 with bit 0 kept, m_owner -1, m_visible (bit 0) 0, m_id (+0x18 half) 0, m_userdata 0; m_bits.m_vec set: memset ((m_bits >> 5) + 1) words, else m_bits.m_bits = 0 (0x17f318): agree (sra in the ELF, the port's u32 shifts logically: same for any real bit count). |
| 16 | 0x17f180 | 132 | CAiEvent::MakeMaskEx(CAiEvent::EVENT, ...) | ai_events.cpp | MATCH | | first and each vararg read as a signed byte of its 8-byte slot (lb 0x17f1e8), mask |= 1 << event until -1, returned: agree. |
| 17 | 0x17f210 | 84 | CAiEvent::Tick(float) | ai_events.cpp | MATCH | | m_duration == -99 (c.eq.s) -> 0; else m_duration -= dT stored, returns m_duration <= 0 (c.le.s): agree. |
| 20 | 0x17f840 | 172 | CAiEvent::Release(CAiEvent*) | ai_events.cpp | MATCH | | NoExpire (0x448f18) == m_duration -> m_persist remove(event), else m_inuse remove(event); then insert at m_pool's end: agree, no NULL test in either. |
| 21 | 0x17fe70 | 188 | CAiEvent::Open(unsigned int) | ai_events.cpp | MATCH | | bit_count (gp) = bits; a non-empty m_inuse erased from its first node to the end (the walk to end is the inlined end search): clear(), events not pooled (ELF quirk kept, noted). |
| 22 | 0x17ff30 | 124 | CAiEvent::GetEventFromString(char const*, CAiEvent::EVENT) | ai_events.cpp | MATCH | | name NULL -> fallback; i 0..14 strcasecmp(GetEventString(i), name) == 0 -> i (as a signed byte); else fallback: agree. |
| 23 | 0x17ffb0 | 72 | CAiEvent::GetEventRate(CAiEvent::EVENT) | ai_events.cpp | MATCH | | 0.0f, HELPATTACK (12) 5.0f (0x40a0), out of range 0: jump table at 0x448f30 agrees. |
| 163 | 0x394bf0 | 128 | CClockSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_spec.cpp | MATCH | | new(172), CRenderableString, C2DClock vtables (no own members), SetFont(font), LoadSpec(*this), returned: agree. The scan's stores are the port's layout. |
| 162 | 0x394be0 | 12 | CClockSpec::GetType() | zui_spec.cpp | MATCH | | "CLOCK". |
| 164 | 0x394dd0 | 124 | CUIMapCtrlSpec::CreateDisplayObj(C2DFont*, zdb::CTextureRelocMgr*) const | zui_spec.cpp | MATCH | | new(528), CUIMapCtrl(), LoadSpec(*this, font, NULL, reloc) (a3 0, t0 reloc), returned: agree. |
| 165 | 0x3951b0 | 156 | CDesignDlgObj::operator=(CDesignDlgObj const&) | zui_spec.cpp | MATCH | | Own spec's deleting dtor (slot +0x8, a1 1), m_spec = other's slot +0xc Copy or 0, m_x / m_y, m_name (+0xc) / m_parent (+0x10) assign(other, 0, npos): agree. Its callers are vector insert / resize and CUIMapCtrlSpec::Copy's vector init (0x39f1f4); the elements copied there are object specs. |
| 166 | 0x395250 | 144 | CDesignDlgObj::~CDesignDlgObj() | zui_spec.cpp | MATCH | | m_spec's deleting dtor when set, then m_parent and m_name destroyed: the port's body plus the member chain. |
| 167 | 0x39ae30 | 12 | CCounterSpec::GetType() | zui_spec.cpp | MATCH | | "COUNTER". |
| 57 | 0x20b650 | 140 | CGame::CGame() | game_main.cpp | MATCH | | Vtable, m_Active (+0x4, sb) 0, m_InitialState 0, m_CurrentState 0, m_MinIdlePeriod (+0x54) 100, the queue's deque ctor (+0x58), m_TestVariable 0, memset(m_Stack, 0, 64), m_pad (+0x74) 0, m_maxtick (+0x78) 0 (offsets from dw.py; the scan's are the port's member order): agree. |
| 55 | 0x20b0d0 | 128 | NetTickThreadEntry(void*) | game_main.cpp | MATCH | | RunState (gp byte) = 1, NetTickSleepTime = zSys.timerTicksPerSecond (+0x20, u32) / 20 unsigned (multu 0xcccccccd, >> 4); while RunState (lbu): zSysSleep(time), zNetTick nonzero -> time = ticks per second; then RunState = 1, ExitDeleteThread: agree. |
| 56 | 0x20b550 | 132 | CGame::~CGame() | game_main.cpp | MATCH | | Vtable, the queue's deque tear_down and its cdeque dtor (+0x58 / +0x5c), deleting flag: the member chain of the empty body. |
| 15 | 0x3d9790 | 132 | PoseBitmap::PoseBitmap() | hud_posebitmap.cpp | MATCH | | C2DBitmap, vtable, C2DString m_text (+0x9c), m_curpose (+0x80) 0, m_posx / m_posy (+0x90 / +0x94) 0, m_error (+0x98, sb) 0, m_posetex[3] (+0x84..+0x8c) 0, m_trans (+0x130) 127.0f (0x42fe): agree. |
| 13 | 0x3d9560 | 76 | PoseBitmap::Draw(zdb::CCamera*) | hud_posebitmap.cpp | MATCH | | C2D::IsOn, then m_text's slot +0xc Draw(camera): agree. |
| 14 | 0x3d95b0 | 84 | PoseBitmap::Clear() | hud_posebitmap.cpp | MATCH | | m_text's slot +0x78 (C2DString::ClearAndWipe, vt.py 0x472cb0; the packet named another class's method there), then the C2D list (+0x4) erase(begin, end): agree. |
| 80 | 0x3f70b0 | 116 | CSaveModule::CSaveModule(char const*, CSaveManager*) | zsav_module.cpp | DEFECT-FIXED | C | Vtable, m_ModuleName = _strdup(name) tagged "zsav_module.cpp" 27 (0x3f70d8), m_Priority / m_Flags 0, m_Manager = manager, RegisterModule(this) when set. The port's zstrdup tagged its own __FILE__ / __LINE__: now the ELF's tag. |
| 76 | 0x3f6fd0 | 8 | CSaveModule::UnSerialize(char const*, zar::CZAR*, int) | zsav_module.cpp | MATCH | | Empty. |
| 77 | 0x3f6fe0 | 8 | CSaveModule::UnSerialize(char const*, CRdrFile*, int) | zsav_module.cpp | MATCH | | Empty. |
| 78 | 0x3f6ff0 | 60 | CSaveModule::SaveRdr(char const*, CRdrFile*) | zsav_module.cpp | MATCH | | m_Manager NULL -> 0, else m_Manager->SaveRdr(m_pKey, name, rdr) & 0xff: agree. |
| 79 | 0x3f7030 | 120 | CSaveModule::~CSaveModule() | zsav_module.cpp | MATCH | | Vtable, m_ModuleName freed ("zsav_module.cpp" 41) when set and zeroed. The ELF zeroes only inside the test (0x3f7074); the port's unconditional store leaves the same 0. |
| 203 | 0x316f50 | 180 | CFlyoutMachine::~CFlyoutMachine() | zwep_projectile.cpp | MATCH | | The ELF zeroes the two vector_pod counts (+0x8, +0x14) first, then __destroy_new_array(m_flyouts, ~CFlyout) and m_flyouts = 0 when set, then the two vectors' dtors: the port's delete[] / NULL and the member dtors give the same end state (the counts of dying vectors are not read; the ELF's ~CFlyout calls are the scan's item). |
| 216 | 0x319e60 | 124 | CZProjectile::SetVelW(CPnt3D const*) | zwep_projectile.cpp | MATCH | | vel NULL: m_state (+0xa) 2, m_vel = CPnt3D::zero; else m_state 1, m_vel = *vel, m_done (bit 0 of +0x4) 0 with the other bits kept, m_intersecthandle (+0x8c) -1: agree. |
| 202 | 0x316de0 | 104 | CFlyoutMachine::HookupReset() | zwep_projectile.cpp | MATCH | | GetModel "tracer", "tracer_enemy", "tracer_ally" on CWorld::GetAssetList() (= &CAssetMgr::m_assets) into the Standard / Enemy / Ally statics, Registered = Standard: agree. |
| 204 | 0x317010 | 60 | CFlyoutMachine::CFlyoutMachine() | zwep_projectile.cpp | MATCH | | The two vector_pods (+0x4, +0x10) constructed, m_flyouts 0. |
| 205 | 0x317050 | 96 | CFlyout::~CFlyout() | zwep_projectile.cpp | DEFECT-FIXED | C | The ELF calls CNode::Delete(m_node) only when set (beqz 0x317070); the port called it unconditionally (Delete's own NULL test hid it): the test restored. |
| 206 | 0x317350 | 16 | CZProjectile::WasDetonated() | zwep_projectile.cpp | MATCH | | m_state (lbu +0xa) == 5. |
| 207 | 0x317360 | 68 | CZProjectile::SetProjectileState(PROJECTILE_STATE, bool) | zwep_projectile.cpp | MATCH | | Stored (sb +0xa) when !theNetwork.m_bNetwork (+0x9), force, m_isplayer (bit 2 of +0x4) or m_shooterID (+0x90) == 0: agree. |
| 208 | 0x3174f0 | 84 | CZProjectile::ReportGrenadeStatus() | zwep_projectile.cpp | MATCH | | m_isplayer and m_shottype (lbu +0x9) not 1 / 2 -> CZGrenadeState::UpdateLocalGrenade(this): agree. |
| 209 | 0x317550 | 188 | CZProjectile::IsInRange(CPnt3D const*, float) | zwep_projectile.cpp | MATCH | | d = *pos - m_framestartpos (+0x38, mem.py), (x x + y y) + z z (adda / madd) <= range * range (c.le.s, then the xori): agree. |
| 210 | 0x317610 | 8 | CZProjectile::SetAnimInstance(CZAnim*) | zwep_projectile.cpp | MATCH | | m_animinstance (+0x28) = arg. |
| 211 | 0x317620 | 148 | CZProjectile::ResolveDamage(float*, float*, float, float) | zwep_projectile.cpp | MATCH | | armorpct = damage - *armor * (mult / 10), healthpct = damage - armorpct, armorpct <= 0 -> 0 and damage - 0; *armor -= healthpct / 4 floored at 0; *health -= armorpct floored at 0; *health re-read into $f0: same operations and compares. |
| 212 | 0x317ca0 | 8 | CZProjectile::GetExplosionDamage() | zwep_projectile.cpp | MATCH | | Tail call m_ammo (+0x10)->GetExplosionDamage(). |
| 213 | 0x317cb0 | 8 | CZProjectile::SetInstance(zdb::CNode*) | zwep_projectile.cpp | MATCH | | m_instance (+0x18) = node. |
| 214 | 0x317cc0 | 8 | CZProjectile::GetInstance() | zwep_projectile.cpp | MATCH | | m_instance (+0x18). |
| 215 | 0x3180c0 | 12 | CZProjectile::Detonate() | zwep_projectile.cpp | MATCH | | m_state = 3 (sb). |
| 217 | 0x319ee0 | 176 | CZProjectile::FireValidityCheck() | zwep_projectile.cpp | MATCH | | 1 when m_weapon NULL, IsDirectFire, offline or not the player; else m_object_index (+0x94) = CreateLocalGrenade, < 0 -> 0, else m_grenadestate (+0x8) CREATE and UpdateLocalGrenade, 1: agree. |
| 218 | 0x319f90 | 88 | CZProjectile::PreFireProjectile() | zwep_projectile.cpp | MATCH | | m_shottype == ONE_FRAME -> GetNextDirectFireDI(&m_di +0x20, &m_di_handle +0x24), else GetNextIndirectFireDI; m_remove_ASAP (+0xa0) 0 on both: agree. |
| 219 | 0x31a2e0 | 180 | CZProjectile::~CZProjectile() | zwep_projectile.cpp | MATCH | | Vtable, Cleanup, m_instance = CNode::Delete(m_instance) when set, m_di / m_weapon / m_ammo / m_owner 0, m_animinstance Stop and 0, m_pickup CPickup::Destroy and 0: agree. |
| 97 | 0x2b9bd0 | 180 | CTMove::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | The select lookup and a GetSealCtrlAi call with no effect, then dT 0 and 1 on both paths (0x2b9c58 / 0x2b9c64): the port's body. The scan's items are the left-out lookup. |
| 104 | 0x2bda90 | 180 | CTDoor::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | As #97: dT 0 and 1 on both paths (0x2bdb18 / 0x2bdb24). |
| 96 | 0x2b9b30 | 152 | CTMove::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | Only the select lookup and a GetSealCtrlAi call whose result is dropped: nothing (GetSealCtrlAi has no side effect). |
| 101 | 0x2bd100 | 152 | CTFireMode::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | DEFECT-FIXED | B | Select seal, m_control's slot +0x38 GetSealCtrlAi; no AI -> dT 0 (0x2bd178), with an AI dT is left untouched (0x2bd184); returns 1 on both. The port zeroed dT always, so the anim lost the frame's remaining time after an AI's ai::FIREMODE (m8's on_aware4 uses it): now as the ELF. |
| 103 | 0x2bda20 | 108 | CTDoor::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | As #96: nothing. |
| 85 | 0x2b5f70 | 160 | CTStance::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | Select seal, GetSealCtrlAi; AI: SetStance(lb m_stance +0xc), m_desiredPeek (+0x305) = m_peek (+0x8) as a byte, m_timer (+0x14) = m_delay (+0x10): agree. SEAL_STANCE lead: Parse stores get_stance's numbers (-1..3, the DWARF values) and Begin passes them as (s8) casts, so the port enum's shifted names (0..5) are not involved here. |
| 84 | 0x2b5eb0 | 184 | CTStance::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | AI, m_delay != 0 (c.eq.s / bc1t) and m_peek != 2 -> m_desiredPeek = 2 (sb +0x305): agree. |
| 91 | 0x2b7590 | 172 | CTSelect::Create(CZSealBody*) | seal_tasks.cpp | MATCH | | _calloc(16, 1, "seal_tasks.cpp" 27), data_size 16 (64 in the half-word's bits 2-15), type ai_cmdid+8, m_seal (+0xc); seal NULL -> m_ai (+0x8) 0, else GetSealCtrlAi (slot +0x38 of m_control +0xc0) and the type stored again: agree. |
| 94 | 0x2b81a0 | 136 | CTPursue::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc 12, type ai_cmdid+0, m_duration -1 (0xbf80) then zrdr_findreal "duration": agree. |
| 86 | 0x2b63d0 | 128 | CTSpecial::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | DEVIATION-KEPT | | Select's m_ai (+0x8) Debug("CTSpecial::BEGIN\n") (the ELF calls it on a NULL controller too), m_index (+0x8) 1, m_phase (low nibble of +0x9) 0: agree. The port's controller test is kept as End's (#25 of medium-seal-c): the port's trace Debug reads its receiver; the reason is now in the code. |
| 82 | 0x2b4450 | 192 | CTValve::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | DEFECT-FIXED | B | Select seal, GetSealCtrlAi; no AI -> dT 0 and 1 (0x2b44d0); AI: m_cmd.m_valve (+0x8) = GetValve(lbu +0x14), Compare, m_valve 0, result & 0xff, dT untouched. The port zeroed dT before the test: now only without an AI. |
| 83 | 0x2b5700 | 68 | CTStopAll::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | SetAiEnabled(bit 0 of +0x8 clear, bit 1 clear), 1: agree; dT untouched in both. |
| 87 | 0x2b6450 | 84 | CTSpecial::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc 12, data_size 12 (48), type ai_cmdid+0xc (ai::SPECIAL's own id): agree. |
| 88 | 0x2b67e0 | 56 | CTSound::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | m_instance (+0xc) TerminateOnFinish when set, then 0. |
| 89 | 0x2b6820 | 32 | CTSound::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | m_pending: bit 0 of byte +0x9 = bit 8 of the port's word at +0x8 (the scan's +0x8 is GCC's word access), m_instance 0: agree. |
| 90 | 0x2b74a0 | 8 | CTSelect::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | Returns 1. |
| 92 | 0x2b7f80 | 120 | CTPursue::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | Select seal, GetSealCtrlAi called, result dropped: the port's body. |
| 93 | 0x2b8000 | 164 | CTPursue::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | No AI -> dT 0, 1; AI -> AiStateIs(STATE_SCRIPT 1), dT 0, & 0xff: dT is zeroed on both paths, as the port. |
| 95 | 0x2b9820 | 172 | CTPaint::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | DEFECT-FIXED | C | GetRegion(m_loc); m_mode (+0x12) 1 / 2 with a region: Tile(region, m_value lhu +0x10, m_mask +0xc); 3: SetRegionType(region, lbu +0x10) untested (0x2b989c); dT 0, 1. The port's NULL test on mode 3 (no ELF test) is removed. |
| 98 | 0x2bbda0 | 172 | CTHold::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | AI and m_timer (+0x10) != -1 (c.eq.s / bc1t) -> SetAiMode(1): agree. |
| 99 | 0x2bcfa0 | 180 | CTFireWeapon::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | AI and m_kit (+0x520) HasItem(lbu m_item +0x8) -> m_armed (bit 0 of +0xc) set: agree. |
| 100 | 0x2bd060 | 160 | CTFireWeapon::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc 44 (176), type ai_cmdid+0, m_item = GetWeaponId(findstring "weapon") & 0xff as a word, m_armed 0: agree. |
| 102 | 0x2bd850 | 8 | CTEvent::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | Empty. |
| 105 | 0x2bdb50 | 8 | CTDoor::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | Tail call CTMove::Begin. |
| 106 | 0x2bdb60 | 8 | CTDoor::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | Tail call CTMove::Parse. |
| 107 | 0x2be230 | 180 | CTComm::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc 16 (64), type ai_cmdid+0, m_team -1, m_cmd (sh +0xc) 0, findint "team", m_cmd = GetCommandId(findstring "cmd") & 0xff: agree. |
| 43 | 0x208260 | 124 | CZPersonaState::UpdateTeamNumsEx() | fts_net_persona.cpp | MATCH | | UpdateTeamNums, then the 16 m_LJArray bytes: bit 4 set -> bit 3 set ? m_NumTerr++ : m_NumSeal++ (gp words): agree. The scan's stores are the port's own layout of the statics. |
| 39 | 0x207b30 | 80 | CZPersonaState::ClearPersonaList() | fts_net_persona.cpp | MATCH | | A non-empty m_PersonaList (size word) erased from its first node to the end. |
| 40 | 0x207b80 | 176 | CZPersonaState::GetPersonaName(int) | fts_net_persona.cpp | MATCH | | Per list id: zNetGetObject, name[0] (lb +0xc) == 'P', data (+0x1c) set and ClientIndex (lbu +0x2d1) == client -> &PersonaName (+0x9); else NULL: agree. |
| 41 | 0x207ec0 | 84 | CZPersonaState::ToggleReady() | fts_net_persona.cpp | MATCH | | theMission.m_pNetGame NULL -> out; minor state (lbu +0xdd) == READY (2) -> MyMinorGameState(NOTREADY 1), else (READY 2); UpdateLocalPersona: agree. |
| 42 | 0x207f20 | 180 | CZPersonaState::AllReadyToPlay() | fts_net_persona.cpp | MATCH | | Per 'P' object with data: major (lbu +0x0) == LOADING (2) and minor (+0x1) != READY -> 0; else 1: agree. |
| 44 | 0x208810 | 176 | CZPersonaState::NumActiveSeals() | fts_net_persona.cpp | MATCH | | Count of 'P' objects with data whose TeamBlock (+0x4) & 1: agree. |
| 45 | 0x2088c0 | 176 | CZPersonaState::NumActiveTerrorists() | fts_net_persona.cpp | MATCH | | As #44 with & 0x100. |
| 46 | 0x209120 | 192 | CZPersonaState::RemotePersonaDeletionCallback(int, int) | fts_net_persona.cpp | MATCH | | zNetGetObject(index) NULL -> out; the first list node holding index erased when found; UpdatePersonaLists, CheckStateSwitch: agree (first argument unused in both). |
| 47 | 0x2091f0 | 36 | CZPersonaState::RemotePersonaPostUpdateCallback(int, int, int) | fts_net_persona.cpp | MATCH | | UpdatePersonaLists then UpdateLocalPersona. |
| 191 | 0x30ef40 | 92 | zdb::CSubMesh::CSubMesh(zdb::CMesh*) | vis_mesh.cpp | MATCH | | CVisual(), vtable (+0x20), m_vtype (+0x4, sb) 2, m_render_mode (+0x1c) 3, m_matrix_id (+0x68) 0xabcd, m_mesh (+0x6c) = mesh (offsets from zvis.h's ELF comments; no DWARF class): agree. |
| 186 | 0x30ed60 | 116 | zdb::CMesh::DereferenceDecals(unsigned int) | vis_mesh.cpp | MATCH | | Per decal: next (+0x4) read, FreeMem, +0x0 / +0x4 / +0x8 / +0x10 / +0x34 m_chain / +0x30 m_qwc zeroed, PutTempDecal; then m_mesh_decals (+0x6c) 0: agree (the scan's S8 is GCC pairing +0x0 / +0x4). |
| 190 | 0x30eee0 | 96 | zdb::CSubMesh::~CSubMesh() | vis_mesh.cpp | MATCH | | Vtable (+0x20), ~CVisual, deleting flag: the empty body's chain. |
| 187 | 0x30ede0 | 72 | zdb::CMesh::RemoveMeshDecal(zdb::CMeshDecal*) | vis_mesh.cpp | MATCH | | Walk m_mesh_decals; the match unlinked through prev->m_next or the head, its m_next 0, out: agree. |
| 188 | 0x30ee30 | 96 | zdb::CSubMesh::Write(zar::CZAR&) | vis_mesh.cpp | MATCH | | Insert("vtype", int 2), Insert("matrix_id", uint m_matrix_id), CVisual::Write's result: agree. |
| 189 | 0x30ee90 | 76 | zdb::CSubMesh::Read(zar::CZAR&) | vis_mesh.cpp | MATCH | | Fetch("matrix_id", &m_matrix_id), CVisual::Read's result. |
| 192 | 0x30efa0 | 168 | zdb::CMesh::SetMeshTextureSelects(_word128*, _word128*) | vis_mesh.cpp | MATCH | | u8[2] of the header 0 -> set 1, then the u16[0] tags after it: type (u8[2]) 6 -> ResolveTextureName(wname, tag): agree. |
| 193 | 0x30f050 | 152 | zdb::CMesh::SetMeshBuffer(_word128*, _word128*, _word128*) | vis_mesh.cpp | MATCH | | m_mesh_decals 0, chain->u32[2] = vertex, per tag (jump table 0x459a60, types 5..12): 7 / 10 / 11 / 12 u32[1] += vertex, 9 u32[1] = m_matrices data (+0x88)[u32[1]], others nothing: agree. |
| 194 | 0x30f0f0 | 76 | zdb::CMesh::Write(zar::CZAR&) | vis_mesh.cpp | MATCH | | Insert("vtype", 1), CVisual::Write's result. |
| 195 | 0x30f140 | 8 | zdb::CMesh::Read(zar::CZAR&) | vis_mesh.cpp | MATCH | | Tail call CVisual::Read. |
| 196 | 0x30f310 | 8 | zdb::CMesh::UpdateCentroid() | vis_mesh.cpp | MATCH | | Empty. |
| 197 | 0x30f320 | 8 | zdb::CMesh::ComputeBBox(CBBox*) | vis_mesh.cpp | MATCH | | Empty. |
| 198 | 0x30f710 | 44 | zdb::CMesh::SetLOD(unsigned int, unsigned int) | vis_mesh.cpp | MATCH | | m_buffers data (+0x38)[instance] = m_lods data (+0x78)[lod] (12-byte entries) m_chain (+0x8): agree. |
| 199 | 0x30f740 | 104 | zdb::CMesh::SetLOD(unsigned int, float) | vis_mesh.cpp | MATCH | | Fewer than 2 LODs -> out; first LOD with rangeSqd < m_range_sqd (c.lt.s) sets the instance's buffer: agree. |
| 200 | 0x30f8f0 | 152 | zdb::CMesh::InitMatrices() | vis_mesh.cpp | MATCH | | While i < m_mtx_count (re-read): new(64), sceVu0UnitMatrix when non-NULL, inserted at the end (NULL too): agree. |
| 201 | 0x30fa90 | 48 | zdb::CMesh::Init() | vis_mesh.cpp | MATCH | | locals = _malloc(1184, "vis_mesh.cpp", 42), localsI 0. |
| 239 | 0x31e420 | 92 | CZWeapon::IsDirectFire() | zwep_weapon.cpp | MATCH | | GetIDType(lb m_ID +0x60) & 0xff: 170, 120, 150, 180 -> 0, else 1: the port's four enum compares (port values 170 / 120 / 150 / 180). The scan's constants are the port's enum names. |
| 220 | 0x31c9a0 | 8 | CZWeapon::TimerCleared() | zwep_weapon.cpp | MATCH | | m_timer_bTimerCleared (gp, lbu). |
| 221 | 0x31c9b0 | 32 | CZWeapon::ClearTimer() | zwep_weapon.cpp | MATCH | | pCurval 0, bTimerRegistered 0, bTimerCleared 1, maxval -1.0f, bIncrTimer 1. |
| 222 | 0x31c9d0 | 8 | CZWeapon::TimerRegistered() | zwep_weapon.cpp | MATCH | | m_timer_bTimerRegistered. |
| 223 | 0x31c9e0 | 32 | CZWeapon::RetrieveTimerRegistration(float**, float*, bool*) | zwep_weapon.cpp | MATCH | | *max = maxval, *incr = bIncrTimer (byte), *value = pCurval, bTimerRegistered 0. |
| 224 | 0x31ca00 | 28 | CZWeapon::RegisterTimer(float*, float, bool) | zwep_weapon.cpp | MATCH | | pCurval = value, maxval = max, bTimerRegistered 1, bIncrTimer = incr, bTimerCleared 0. |
| 225 | 0x31cb50 | 16 | CZWeapon::AI_PARAMS::GetAccuracy(float) const | zwep_weapon.cpp | MATCH | | 1.0f in $f0. |
| 226 | 0x31cb60 | 76 | CZWeapon::Close() | zwep_weapon.cpp | MATCH | | m_flyout_machine.ReleaseAllActive, m_pProjectilelist Clear when set (the ELF's test), m_listWeapons.ClearAnimations, zwep::personMaterialId -1, 1. |
| 227 | 0x31cc90 | 64 | CZWeapon::Open() | zwep_weapon.cpp | MATCH | | InitializeWeapons, HookupReset, personMaterialId = ResolveMaterialIndex("PERSON"), 1. |
| 228 | 0x31ccd0 | 192 | CZWeapon::Init() | zwep_weapon.cpp | MATCH | | CZAR(NULL, NULL), Open("run/zweapon.zar", GetVersion(), 1, 16) & 0xff; failed -> ~CZAR, the result; else ZWepReader Read(archive, &m_listWeapons, &CZAmmo::m_ammolist), ~ZWepReader (empty, 0x31c940, so its later run in the port changes nothing), m_flyout_machine.Init(100), ~CZAR: agree. |
| 229 | 0x31d150 | 136 | CZDecalSet::GetDecalSetByName(char const*) | zwep_weapon.cpp | MATCH | | i < m_decalsets size (re-read), strcmp(set->m_name +0x4, name) == 0 -> that set, else NULL. |
| 230 | 0x31d770 | 64 | GetVisualNode(zdb::CNode*) | zwep_weapon.cpp | MATCH | | m_hasVisuals (bit 7 of +0x5e) -> node; parent (+0x64) == CWorld::m_world -> node; else node = parent (delay slot), NULL ends with NULL: agree. |
| 231 | 0x31d7b0 | 68 | GetDecalNode(zdb::CNode*) | zwep_weapon.cpp | MATCH | | m_type (lhu +0x58) == 2 -> node; node = m_parent; the world -> NULL; loop while non-NULL: agree. |
| 232 | 0x31e140 | 16 | CZWeapon::GetWeaponName(EQUIP_ITEM) | zwep_weapon.cpp | MATCH | | Tail call m_listWeapons.GetWeaponName(id). |
| 233 | 0x31e150 | 108 | CZWeapon::GetWeaponId(char const*) | zwep_weapon.cpp | MATCH | | NULL -> 255, strcasecmp "NVG" -> 184, "BINOCULARS" -> 182, else m_listWeapons.GetWeaponId(name): the port's NONE / OLD_NVG_ID / BINOCULARS values. |
| 234 | 0x31e320 | 44 | CZWeapon::PackItemAndAmmoEnums(EQUIP_ITEM, EQUIP_AMMO) | zwep_weapon.cpp | MATCH | | (item & 0xff) << 8 | (ammo & 0xff), & 0xffff (the sign extensions of 0..0xff00 change nothing). |
| 235 | 0x31e350 | 28 | CZWeapon::UnpackItemAndAmmoEnums(unsigned short, EQUIP_ITEM*, EQUIP_AMMO*) | zwep_weapon.cpp | MATCH | | *item = packed >> 8, *ammo = low byte (sb both). |
| 236 | 0x31e370 | 40 | CZWeapon::IsSecondary(EQUIP_ITEM) | zwep_weapon.cpp | MATCH | | GetIDType(item) & 0xff == 0 (PISTOL). |
| 237 | 0x31e3a0 | 112 | CZWeapon::IsPrimary(EQUIP_ITEM) | zwep_weapon.cpp | MATCH | | GetIDType & 0xff in {30, 50, 80, 90, 140, 100} -> 1, else 0: agree. |
| 238 | 0x31e410 | 8 | CZWeapon::GetIDType() | zwep_weapon.cpp | MATCH | | Tail call GetIDType(lb m_ID). |
| 240 | 0x31e480 | 100 | CZWeapon::GetDefaultAmmoId() | zwep_weapon.cpp | MATCH | | m_LegalAmmoList (+0x9c) size > 0 -> GetAmmo(0); ammo ? lb m_ID (+0x20) : 255: agree. |
| 241 | 0x31e4f0 | 60 | CZWeapon::GetDefaultAmmo() | zwep_weapon.cpp | MATCH | | size <= 0 -> NULL, else GetAmmo(0). |
| 242 | 0x31e530 | 52 | CZWeapon::PostTick(float, void*) | zwep_weapon.cpp | MATCH | | m_weaponTickDisabled -> 0; else m_pProjectilelist->PostTick(dT) (no NULL test in either), 0. |
| 243 | 0x31e570 | 92 | CZWeapon::PreTick(float, void*) | zwep_weapon.cpp | MATCH | | Disabled -> 0; PreTick(dT); theMission.m_pNetGame set and m_game_type (lbu +0xd9) == FOOTBOMB (7) -> CZBombState::UpdateLocalBomb; 0. |
| 244 | 0x31e5d0 | 104 | CZWeapon::SetReloadSoundName(char*) | zwep_weapon.cpp | MATCH | | Old freed (809), 0, name set -> _strdup(812): agree. |
| 245 | 0x31e640 | 100 | CZWeapon::SetDecalSetName(char const*) | zwep_weapon.cpp | MATCH | | Old freed (803), 0, _strdup(name, 805) unguarded (ELF quirk kept, noted). |
| 246 | 0x31e6b0 | 8 | CZWeapon::GetDecalSetName() | zwep_weapon.cpp | MATCH | | m_decalsetname (+0x1c). |
| 247 | 0x31e6c0 | 100 | CZWeapon::ClearAnims() | zwep_weapon.cpp | MATCH | | m_hitanim freed (784) and 0 when set; fire / zoomed / default special 0; m_specialmaterialanim freed (792) and 0 when set. |
| 248 | 0x31e730 | 8 | CZWeapon::SetZoomedFireAnim(CZAnim*) | zwep_weapon.cpp | MATCH | | +0x6c = anim. |
| 249 | 0x31e740 | 32 | CZWeapon::GetFireAnim(bool) | zwep_weapon.cpp | MATCH | | zoomed ? +0x6c : +0x68. |
| 250 | 0x31e760 | 8 | CZWeapon::GetDefaultSpecialAnim() | zwep_weapon.cpp | MATCH | | +0x70. |
| 251 | 0x31e770 | 48 | CZWeapon::GetHitAnim(int) | zwep_weapon.cpp | MATCH | | material < m_materialex_list size (slt, signed) -> m_hitanim[material], else NULL. |
| 252 | 0x31e7a0 | 8 | CZWeapon::GetFireAnimName() | zwep_weapon.cpp | MATCH | | +0x84. |
| 253 | 0x31e7b0 | 48 | CZWeapon::GetSpecialMaterialAnim(int) | zwep_weapon.cpp | MATCH | | As #251 with +0x74. |
| 254 | 0x31e7e0 | 48 | CZWeapon::SetSpecialMaterialAnim(int, CZAnim*) | zwep_weapon.cpp | MATCH | | In range -> m_specialmaterialanim[material] = anim. The ELF's v0 (1 / 0) is read by neither caller; the port's void is noted in the code. |
| 255 | 0x31e810 | 8 | CZWeapon::SetDefaultSpecialAnim(CZAnim*) | zwep_weapon.cpp | MATCH | | +0x70 = anim. |
| 256 | 0x31e820 | 8 | CZWeapon::SetFireAnim(CZAnim*) | zwep_weapon.cpp | MATCH | | +0x68 = anim. |
| 257 | 0x31e830 | 48 | CZWeapon::SetHitAnim(int, CZAnim*) | zwep_weapon.cpp | MATCH | | As #254 with m_hitanim; v0 unread. |
| 258 | 0x31e860 | 8 | CZWeapon::GetSpecialMaterialAnimName() | zwep_weapon.cpp | MATCH | | +0x8c. |
| 259 | 0x31e870 | 8 | CZWeapon::GetDefaultSpecialAnimName() | zwep_weapon.cpp | MATCH | | +0x88. |
| 260 | 0x31e880 | 8 | CZWeapon::GetHitAnimName() | zwep_weapon.cpp | MATCH | | +0x80. |
| 261 | 0x31e890 | 76 | CZWeapon::AllocateHitAnimMem() | zwep_weapon.cpp | MATCH | | m_hitanim = _malloc(materials * 4, 679), re-read != 0 returned. |
| 262 | 0x31e8e0 | 76 | CZWeapon::AllocateSpecialMaterialAnimMem() | zwep_weapon.cpp | MATCH | | As #261 with +0x74, 673. |
| 263 | 0x31e930 | 112 | CZWeapon::SetSpecialMaterialAnimName(char const*) | zwep_weapon.cpp | MATCH | | Old freed (667), 0, name ? _strdup(668) : 0. |
| 264 | 0x31e9a0 | 112 | CZWeapon::SetDefaultSpecialAnimName(char const*) | zwep_weapon.cpp | MATCH | | As #263: 662 / 663, +0x88. |
| 265 | 0x31ea10 | 112 | CZWeapon::SetFireAnimName(char const*) | zwep_weapon.cpp | MATCH | | As #263: 657 / 658, +0x84. |
| 266 | 0x31ea80 | 112 | CZWeapon::SetHitAnimName(char const*) | zwep_weapon.cpp | MATCH | | As #263: 652 / 653, +0x80. |
| 267 | 0x31ebe0 | 8 | CZWeapon::GetModelName() const | zwep_weapon.cpp | MATCH | | +0x18. |
| 268 | 0x31ebf0 | 8 | CZWeapon::GetAssociatedGearName() | zwep_weapon.cpp | MATCH | | +0x14. |
| 269 | 0x31ec00 | 68 | CZWeapon::AddLegalAmmo(CZAmmo*) | zwep_weapon.cpp | MATCH | | m_LegalAmmoList insert(end, ammo), NULL too. |
| 270 | 0x31ec60 | 8 | CZWeapon::GetImpactRadius() const | zwep_weapon.cpp | MATCH | | +0x44 in $f0. |
| 271 | 0x31ec70 | 8 | CZWeapon::GetEffectiveRange() | zwep_weapon.cpp | MATCH | | +0x3c. |
| 272 | 0x31ec80 | 8 | CZWeapon::GetMaxRange() | zwep_weapon.cpp | MATCH | | +0x38. |
| 273 | 0x31ec90 | 8 | CZWeapon::GetEncumbrance() | zwep_weapon.cpp | MATCH | | lb +0x34 (values 0..5, so the port's u8 enum is the same). |
| 274 | 0x31eca0 | 8 | CZWeapon::GetNumMags() | zwep_weapon.cpp | MATCH | | +0x28. |
| 275 | 0x31ecd0 | 8 | CZWeapon::GetName() const | zwep_weapon.cpp | MATCH | | +0x4. |
| 276 | 0x31ece0 | 112 | CZWeapon::SetIconTextureName(char const*) | zwep_weapon.cpp | MATCH | | As #263: 550 / 551, +0x10. |
| 277 | 0x31ed50 | 112 | CZWeapon::SetModelName(char const*) | zwep_weapon.cpp | MATCH | | As #263: 544 / 545, +0x18. |
| 278 | 0x31edc0 | 112 | CZWeapon::SetAssociatedGearName(char const*) | zwep_weapon.cpp | MATCH | | As #263: 539 / 540, +0x14. |
| 279 | 0x31ee30 | 8 | CZWeapon::SetMuzzleVelocity(float) | zwep_weapon.cpp | MATCH | | +0x40 = $f12. |
| 280 | 0x31ee40 | 8 | CZWeapon::SetImpactRadius(float) | zwep_weapon.cpp | MATCH | | +0x44. |
| 281 | 0x31ee50 | 8 | CZWeapon::SetEffectiveRange(float) | zwep_weapon.cpp | MATCH | | +0x3c. |
| 282 | 0x31ee60 | 8 | CZWeapon::SetMaxRange(float) | zwep_weapon.cpp | MATCH | | +0x38. |
| 283 | 0x31ee70 | 8 | CZWeapon::SetEncumbrance(ENCUMBRANCE) | zwep_weapon.cpp | MATCH | | sb +0x34. |
| 284 | 0x31ee80 | 16 | CZWeapon::SetSoundRadius(float) | zwep_weapon.cpp | MATCH | | +0x2c = r, +0x30 = r * r. |
| 285 | 0x31ee90 | 8 | CZWeapon::SetNumMags(int) | zwep_weapon.cpp | MATCH | | +0x28. |
| 286 | 0x31eea0 | 8 | CZWeapon::SetAmmoCapacity(int) | zwep_weapon.cpp | MATCH | | +0x24. |
| 287 | 0x31eeb0 | 44 | CZWeapon::SetHasFireMode(FIREMODE) | zwep_weapon.cpp | MATCH | | m_hasFireModes (+0xa8)[mode & 0xff] = 1; lbu m_maxfiremode (+0x20) < mode -> stored: agree. |
| 288 | 0x31eee0 | 36 | CZWeapon::HasFireMode(int) const | zwep_weapon.cpp | MATCH | | id < 5 (slti) -> lbu m_hasFireModes[id], else 1: agree. |
| 289 | 0x31ef10 | 112 | CZWeapon::SetDescription(char const*) | zwep_weapon.cpp | MATCH | | As #263: 465 / 466, +0x8. |
| 290 | 0x31ef80 | 112 | CZWeapon::SetName(char const*) | zwep_weapon.cpp | MATCH | | As #263: 459 / 460, +0x4. |
| 291 | 0x31f410 | 8 | CZWeapon::SetBulletPassSound(CSnd*) | zwep_weapon.cpp | MATCH | | The static (gp 0x476684) = sound. |
| 292 | 0x31f420 | 8 | CZWeapon::GetBulletPassSound() | zwep_weapon.cpp | MATCH | | The static. |
| 293 | 0x31f430 | 8 | CZWeapon::CreateWeaponList() | zwep_weapon.cpp | MATCH | | 1. |
| 294 | 0x31f530 | 124 | CZWeapon::CreateMarkList() | zwep_weapon.cpp | MATCH | | new(52), the list and the two vector_deleters constructed, +0xc / +0x28 / +0x2c (the three tables) 0, m_pMarklist stored, != 0 returned: the header's inline ctor. |
| 295 | 0x31f5b0 | 56 | CZWeapon::DestroyProjectileList() | zwep_weapon.cpp | MATCH | | NULL -> 0; deleting dtor, NULL stored, 1. |
| 296 | 0x31f5f0 | 76 | CZWeapon::CreateProjectileList(int) | zwep_weapon.cpp | MATCH | | new(520) CZProjectileList(count), stored, != 0 returned. |
| 8 | 0x3be7b0 | 8 | CZPauseTest::Off() | hud_pausemenu.cpp | MATCH | | m_on (+0x358) 0, tail call C2D::Off. The scan's +0x360 is the port's layout. |
| 9 | 0x3be7c0 | 12 | CZPauseTest::On() | hud_pausemenu.cpp | MATCH | | m_on 1, tail call C2D::On. |
| 12 | 0x3bef20 | 40 | CZPauseTest::Init() | hud_pausemenu.cpp | MATCH | | ReInit, then m_wason (+0x359) 0. |
| 10 | 0x3be7d0 | 176 | CZPauseTest::Draw(zdb::CCamera*) | hud_pausemenu.cpp | MATCH | | Not m_on and g_fFadeoutTime < 0 (c.lt.s / bc1t) -> out; i < m_num_selections (+0x368, re-read): m_selections[i] (136-byte strings from +0x1c) slot +0xc Draw; then m_background (+0x2d0) slot +0xc: the port's direct calls on member objects reach the same methods. |
| 11 | 0x3beba0 | 136 | CZPauseTest::Clear() | hud_pausemenu.cpp | MATCH | | g_fFadeoutTime -1.0f, the five strings' slot +0x78 (ClearAndWipe), the C2D list erase(begin, end): agree. |
| 33 | 0x1ed870 | 180 | CPacket::CPacket(CPacket*, unsigned int, unsigned int) | con_packet.cpp | MATCH | | Vtable, m_data / m_size 0, m_size = other's, m_data = calloc(m_size, 1), memcpy(other's data), flags (+0xc) |= set then &= ~clear (two stores), m_src / m_dst (+0x6 / +0x7) swapped: agree (the scan's half-word is GCC's swap of the two bytes). |
| 24 | 0x1ed500 | 68 | CPacketMsg::GetArg(unsigned int) const | con_packet.cpp | MATCH | | m_data NULL -> NULL; i < header m_argc (+0x14, sltu) -> m_args (+0xc)[i], else NULL. |
| 25 | 0x1ed550 | 32 | CPacketMsg::GetArgCount() const | con_packet.cpp | MATCH | | m_data ? m_argc : 0. |
| 26 | 0x1ed570 | 156 | CPacketMsg::~CPacketMsg() | con_packet.cpp | MATCH | | Vtable, m_args freed when set and 0, then the inline ~CPacket (m_data freed, m_data / m_size 0), deleting flag: agree. |
| 27 | 0x1ed610 | 96 | CPacket::Compare(CPacket*, CPacket*) | con_packet.cpp | MATCH | | Headers' m_id (+0x8) equal, then m_type (+0x10), then m_size (+0x8 of the packets), no NULL tests: agree. |
| 28 | 0x1ed670 | 32 | CPacket::GetPacketID() const | con_packet.cpp | MATCH | | m_data ? m_id : 0. |
| 29 | 0x1ed690 | 32 | CPacket::GetFlags() const | con_packet.cpp | MATCH | | m_data ? m_flags : 0. |
| 30 | 0x1ed6b0 | 32 | CPacket::GetPacketType() const | con_packet.cpp | MATCH | | m_data ? m_type : 0. |
| 31 | 0x1ed6d0 | 76 | CPacket::CopyTo(void*, int) | con_packet.cpp | MATCH | | max < m_size (sltu) -> -1; memcpy(dst, m_data, m_size), m_size re-read and returned. |
| 32 | 0x1ed720 | 112 | CPacket::~CPacket() | con_packet.cpp | MATCH | | Vtable, m_data freed when set, m_data / m_size 0, deleting flag. |
| 178 | 0x313190 | 176 | zdb::CMeshDecalPool::RecycleTick() | vis_decal.cpp | DEFECT-FIXED | C | While m_recycle: GetOldestUsed of CMeshDecal::m_tempPool, its m_count--, PutBack, m_mesh (+0x8) RemoveMeshDecal, the inline FreeMem, m_recycle--: agree but for the free's address, which the ELF masks to its low 28 bits (0x3131ec / 0x3131f4): now as the ELF (the mesh decal list is never filled on this disc). |
| 175 | 0x312de0 | 56 | zdb::CMeshDecalPool::Uninit() | vis_decal.cpp | MATCH | | m_array's deleting dtor (unguarded; the dtor tests this), m_array / m_count / m_recycle 0. |
| 176 | 0x312e20 | 76 | zdb::CMeshDecal::FreeMem() | vis_decal.cpp | DEFECT-FIXED | C | m_mem (+0x10) freed when set as m_mem & 0x0fffffff (dsll32 / dsrl32 4, 0x312e38) tagged 518, then m_mem / m_chain (+0x34) / m_qwc (+0x30) 0. The port freed the unmasked pointer: mask added. |
| 177 | 0x312e70 | 8 | zdb::CDecal::Tick(float) | vis_decal.cpp | MATCH | | Empty. |
| 179 | 0x313240 | 60 | zdb::CMeshDecal::PutTempDecal(zdb::CMeshDecal*) | vis_decal.cpp | MATCH | | m_tempPool.m_recycle-- when non-zero, m_count--, tail call PutBack(decal). |
| 180 | 0x313280 | 104 | zdb::CMeshDecalPool::Init(unsigned int, unsigned int) | vis_decal.cpp | MATCH | | m_base, m_overflow, m_array = new(28) RTArray(base + overflow, true, true) (NULL stored if new fails). |
| 181 | 0x3132f0 | 36 | zdb::CDecal::PutPermDecal(zdb::CDecal*) | vis_decal.cpp | MATCH | | m_permPool.m_count--, tail call PutBack. |
| 182 | 0x313320 | 60 | zdb::CDecal::PutTempDecal(zdb::CDecal*) | vis_decal.cpp | MATCH | | As #179 on CDecal::m_tempPool. |
| 183 | 0x313360 | 128 | zdb::CDecalPool::RecycleTick() | vis_decal.cpp | MATCH | | While this pool's m_recycle: CDecal::m_tempPool's oldest, its m_count--, PutBack, m_visual (+0x4) RemoveDecal, m_recycle-- (ELF quirk kept, noted). |
| 184 | 0x3133e0 | 120 | zdb::CDecalPool::Get(bool) | vis_decal.cpp | MATCH | | m_count < base + overflow (sltu) -> GetNext(recycle); non-NULL: m_count++, m_base < m_count (sltu) -> m_recycle++; the decal or NULL: agree. |
| 185 | 0x313460 | 104 | zdb::CDecalPool::Init(unsigned int, unsigned int) | vis_decal.cpp | MATCH | | As #180 with RTArray<CDecal>. |
| 68 | 0x23e380 | 60 | _zrdr::_zrdr() | zreader_holding.cpp | DEVIATION-KEPT | | The ELF clears only isclone (bit 8) and packed (bit 9) of the first word, others kept; the port also zeroes type, unused, length and array. Kept (reason now in the code): a CRdrFile (its ctor 0x23cf30 leaves them unset too) freed after a failed ReadPacked runs zrdr_freearray on them. |
| 67 | 0x1aba20 | 16 | _zrdr::IsArray() const | zreader_holding.cpp | MATCH | | type (lbu +0x0) == ZRDR_ARRAY (4). |
| 69 | 0x3a7550 | 72 | _zrdr::GetInt() const | zreader_holding.cpp | MATCH | | type 1 -> integer (+0x4), 2 -> fptosi(real), else 0: the port's truncating cast. |
| 170 | 0x304ad0 | 144 | CFileIO::fwrite(char const*) | zutil_holding.cpp | DEFECT-FIXED | C | length = buf ? strlen : 0, slot +0x2c fwrite(&length, 4) always, then fwrite(buf, length) only for a string, the sum returned (0x304b08..0x304b40). The port returned 0 for NULL without writing the length word: now as the ELF (CIO::fwrite's shape). |
| 171 | 0x305da0 | 144 | CIO::fwrite(char const*) | zutil_holding.cpp | MATCH | | As #170: the length word always, the characters for a string, the sum: agree. |
| 168 | 0x1a93c0 | 8 | CFileIO::GetSize() const | zutil_holding.cpp | MATCH | | m_filesize (+0x8). |
| 169 | 0x303c90 | 8 | CFileIO::GetMode() const | zutil_holding.cpp | MATCH | | m_mode (+0xc). |
| 50 | 0x20a830 | 148 | CMissionObjectiveCamList::ClearValves() | fts_objectivecam.cpp | MATCH | | Per list node: the objective's m_valve / m_invalidvalve / m_pDisplayValve (+0x2c / +0x30 / +0x34) 0: agree. |
| 51 | 0x20a8d0 | 36 | CMissionObjectiveCam::IsInvalid() const | fts_objectivecam.cpp | MATCH | | m_invalidvalve ? m_value (lhu +0x4) != 0 : 0. |
| 52 | 0x20a900 | 36 | CMissionObjectiveCam::IsDisplayOn() const | fts_objectivecam.cpp | MATCH | | m_pDisplayValve ? m_value != 0 : 1. |
| 53 | 0x20a930 | 36 | CMissionObjectiveCam::IsComplete() const | fts_objectivecam.cpp | MATCH | | m_valve ? m_value != 0 : 0. |
| 54 | 0x20aae0 | 172 | CMissionObjectiveCam::IsAvailable() const | fts_objectivecam.cpp | MATCH | | !complete, then !invalid, then display on (no valve: 1), then m_isCompass (bit 2 of +0x40), each only while the previous held: agree. |
| 65 | 0x23be70 | 140 | CRdrArchive::CloseAll() | zrdr_archive.cpp | MATCH | | Every m_list archive's CZAR::Close, first to last. |
| 66 | 0x23bf00 | 148 | CRdrArchive::OpenAll() | zrdr_archive.cpp | MATCH | | Every archive's ReOpen(1, READ 1). |
| 81 | 0x2df040 | 124 | CAiDodge::Destroy() | seal_aimoves.cpp | MATCH | | Empty list -> 0; else while non-empty: front's value (+0x8 of the first node), erase it, operator delete when non-NULL (beqz 0x2df084); then 1. The ELF's v0 is read by neither caller (CMission::Close / ReOpen_Unload1); the port's void is noted in the code. |
| 70 | 0x241cb0 | 120 | CPipe::RenderUiNode(zdb::CNode*) | zrndr_pipe.cpp | MATCH | | CStack::m_top += one matrix, m_pointer++, sceVu0CopyMatrix(m_top, identity), RenderUiNodeRecursive(node), m_pointer-- and m_top -= one matrix: agree. |
| 71 | 0x245fa0 | 40 | CPipe::Uninit() | zrndr_pipe.cpp | MATCH | | DisableIntc(5), RemoveIntcHandler(5, VifHandlerID). |
| 72 | 0x245fd0 | 52 | CPipe::Init() | zrndr_pipe.cpp | MATCH | | VifHandlerID = AddIntcHandler(5, InterruptFromVIF1, 0), EnableIntc(5). |
| 73 | 0x246010 | 136 | CPipe::FIFO_Signal(zdb::CGSTexBuffer*) | zrndr_pipe.cpp | MATCH | | NULL -> out; entry m_texLoadIdx++ (12-byte records from +0x8): pTexAsset 0, pTexAssetUsed = buffer (pWaitTime untouched); then the inline FIFO_Insert(0x55555555) packet: the port's call writes the same eight words. |
| 74 | 0x2460a0 | 188 | CPipe::FIFO_Signal(zdb::CGSTexBuffer*, unsigned int*) | zrndr_pipe.cpp | MATCH | | NULL -> out; Load(false); entry: pTexAsset = buffer, used 0, pWaitTime = waitTime; the 0x44444444 packet: agree. |
| 75 | 0x246160 | 100 | FIFO_Insert(int) | zrndr_pipe.cpp | MATCH | | zSysSprGetPacket(NULL), words 0x10000001, marker, 0x11000000, 0, 0x80000000, 0, 0, 0, zSysFifoKick(p, 2). |
| 35 | 0x206200 | 156 | CZGameState::CreateLocalGame(CZNetGame*) | fts_net_game.cpp | MATCH | | zNetCreateObject(&index, 1, 2, t0..t3 0, stack NULL, "GameObject", m_NetStructIndexGameObject) (the stack arguments checked: sp+0 / +8 / +0x10), nonzero -> -1; zNetGetObject NULL -> -1; memset(m_data +0x1c, 0, 64 = sizeof TypeGameState), index: agree. |
| 36 | 0x2062a0 | 8 | CZGameState::RemoteGameDeletionCallback(int, int) | fts_net_game.cpp | MATCH | | Empty. |
| 37 | 0x2062b0 | 96 | CZGameState::RemoteGameCreationCallback(int, int) | fts_net_game.cpp | MATCH | | theMission.m_pNetGame NULL -> out; MPMajorGameState(UNKNOWN 0), m_game_object_index (+0x74) = index, RemoteGameUpdateCallback(client, index, -1). |
| 38 | 0x206310 | 8 | CZGameState::RemoteGamePostUpdateCallback(int, int, int) | fts_net_game.cpp | MATCH | | Empty. |
| 49 | 0x2012c0 | 112 | ftsNetworkGameInit() | fts_network.cpp | MATCH | | theMission.m_pNetGame; session master (+0x8): m_game_object_index (+0x74) = CreateLocalGame, m_clock.m_rtime_delta (+0xb8) 0, UpdateLocalGame; m_persona_created (+0x97) clear: m_persona_object_index (+0x70) = CreateLocalPersona, flag 1, UpdateLocalPersona: agree (no NULL test of the game in either). |
| 48 | 0x201290 | 40 | ftsNetworkGameUninit() | fts_network.cpp | MATCH | | ClearPersonaList, theVoice.UnInit. |
| 61 | 0x334aa0 | 188 | audioDecBeginPut(AudioDec*, unsigned char**, int*, unsigned char**, int*) | audiodec.cpp | MATCH | | state 0: hdr + hdrCount, 40 - hdrCount, data, size; else room = size - count, toEnd = size - put: toEnd < room (slt) -> data + put / size - put / data / room - (size - put), else data + put / room / 0 / 0: agree. |
| 58 | 0x3349a0 | 80 | audioDecStart(AudioDec*) | audiodec.cpp | MATCH | | snd_StartMovieSound(iopBuff, iopBuffSize / 1024 * 1024 (signed, rounded to 0), iopBuff + iopPausePos), state 2. |
| 59 | 0x3349f0 | 20 | audioDecIsPreset(AudioDec*) | audiodec.cpp | MATCH | | !(totalBytesSent < iopBuffSize) (slt). |
| 60 | 0x334a10 | 136 | audioDecEndPut(AudioDec*, int) | audiodec.cpp | MATCH | | state 0: n = min(len, 40 - hdrCount) (sltu), hdrCount += n, >= 40 (sltiu) -> state 1, len -= n; put = (put + len) % size (div), count += len, totalBytes += len: agree. |
| 62 | 0x334b60 | 32 | audioDecDelete(AudioDec*) | audiodec.cpp | MATCH | | snd_CloseMovieSound, 1. |
| 63 | 0x334b80 | 68 | audioDecReset(AudioDec*) | audiodec.cpp | MATCH | | snd_ResetMovieSound, then state / hdrCount / put / count / totalBytes / totalBytesSent / iopLastPos / iopPausePos 0. |
| 64 | 0x334bd0 | 112 | audioDecCreate(AudioDec*, unsigned char*, int, int) | audiodec.cpp | MATCH | | Fields set as the port, iopBuff = snd_InitMovieSound(iopBuffSize, 819, 0, 2), re-read >= 0 returned. |
| 1 | 0x3db860 | 8 | CHUD::GetAssetReport() | hud_devtext.cpp | MATCH | | Empty. |
| 34 | 0x20b0a0 | 36 | CMissionCam::CMissionCam() | fts_missioncam.cpp | MATCH | | m_identifier, m_name, m_anim, m_music, m_description[0..2] all 0. |
| 172 | 0x2f6020 | 136 | CValve::AddCallback(unsigned int, void (*)(CValve*, void*), void*) | valve_list.cpp | MATCH | | new(12); when non-NULL mask / function / data stored; the entry (NULL too) inserted at m_callbacks' list end (+0x8); returned: agree. |
| 173 | 0x2f6780 | 8 | CValve::Init() | valve_list.cpp | MATCH | | Empty; the ELF's v0 1 is read by no caller (CGame::StartEngine). |
| 174 | 0x2f6860 | 52 | CValve::Destroy(CValve*) | valve_list.cpp | MATCH | | NULL -> out (the ELF's test); m_type (lbu +0x6) != 2 -> 2; DeleteCallbacks: agree. |
