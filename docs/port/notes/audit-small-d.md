# Audit of list small-d (2026-11-19, socom-port-audit-small-d)

296 small functions (25,304 bytes, each under 200 bytes) in 29 files: Apps/FTS/hud (hud_linemap,
hud_main, hud_weaponsel), Apps/FTS/state (st_core, st_menu), zArchive zar_search, zBody body,
zEntity (ent_entity, pickup_main), zFTS fts_remote, zGraph (graph_edge, graph_tree), zGrid
grid_cell, zInput zin_main, zIntersect int_bbox, zNetwork znetwork_holding, zNode node_vector,
zSeal (seal_ailines, seal_create, seal_handsig), zSound zsnd_csndinstance, zTexture ztex_handle,
zTwoD c2dstring, zUI zui_2d, zUtil (util_output, util_stable), zVideo zvid_init, zWeapon
(zwep_ammolist, zwep_global). HEAD a17e5177. Judged file by file in the scan's rank order, from
the by-file packets.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 280 |
| DEFECT-FIXED | 15 (A 0, B 1, C 14) |
| DEVIATION-KEPT | 1 |
| UNJUDGED | 0 |

Defect rate 15 / 296 (B 1, C 14).

Fixes:
- B, #231 CRenderableString::UpdateUIVar: the variable's text goes through the virtual
  C2DString::Format (slot +0x60 at 0x390f78; vt.py 0x473af0), which keeps the raw text in
  m_Ustring and applies the "$" escapes, then SetString; the port called SetString directly, so a
  value with "$$" / "$~" showed raw and m_Ustring was not kept.
- C, #10 CWeaponSel::Increment: the down branch as the ELF tests it (!(val <= goal) at 0x3d1a9c,
  v - inc < goal at 0x3d1ab0); the port's goal < val / goal <= v differed for NaN only.
- C, #53 CZBodyAnim::TrueLoopTime (c.le.s 0x1e1b80), #192 C2DString::Tick (c.le.s 0x302d2c),
  #230 CPlainBmp::Tick (c.le.s 0x390cb8): a `>` written as the ELF's !(<=).
- C, #17 CCoreState::CCoreState: the name through the inline SetName ("zgame.h", 84 at
  0x17d788), not zstrdup's st_core.cpp / __LINE__ tag. CGameState's inline ctor zeroes m_name
  first (0x17d750): header edit file `fts_state_h_gamestate_ctor.txt`.
- C, #59 CBody::ClearBlendOverlay: the anim cleared once (CActiveAnimPool::PutBack inline,
  RTArray::PutBack at 0x1e2310); the port cleared it by hand and PutBack cleared it again.
- C, #69 CZBodyPart::~CZBodyPart: m_node zeroed only when set (0x1e386c).
- C, #81 CPickup::FindNetPickup: the empty-list test first (0x24c628).
- C, #87 CPickup::SetVisibleByUnit: |= 1, |= 2, |= 3 as three stores (0x24d1a0..0x24d1c4).
- C, #193 / #194 C2DString::On / Off: tail calls of C2D::On / C2D::Off (0x302db0, 0x302dc0).
- C, #272 COutput::~COutput: Close, then operator delete without a destructor (0x304354; the
  port's inline ~CFileIO closed again); m_doLog no longer cleared (the ELF zeroes +0x4).
- C, #278 zUtilInit: COutput(log, true) (li a2,1 at 0x304538); debug has no other reader.
- C, #283 CSTable::CSTable: _malloc(size, "util_stable.cpp", 25) (0x306824), not libc malloc.

Kept deviation (reason in the code): #265 CListItemArrayTypeImpl::GetString returns "" where the
ELF returns the address of achFallback$3573 (0x3943b0), PrepListItem's fenced function-local
static that this function cannot name; the same empty text.

ELF quirks kept (already in the code): #128 CreatePad's m_pads[0]; #150 Remove's moved iterator
in the result; #153 GetElement's index == size; #185 Destroy's count before the NULL test; #181
SetVol's double volume; #207 / #224 GetZAnimCmdType fallbacks and Highlight_on; #214 HandlePad's
word count; #213 / #215 / #247 no string Tick; #218 / #132 a v0 no caller reads (port void).

Float checks: every compare's form agrees after the four fixes (c.lt.s / c.le.s / c.eq.s with the
port's branch sense in #135, #176, #186, #206, #213, #215, #221, #247, #248); sums and
products in the port's order (#11, #159 mula / madd, #181, #192, #230); literals 0x3f7d70a4,
0x40c90fdb, 0x4048f5c3, 0x4b7ffffa, 0x3c866666, 0x3c23d70a, 0x3ea8f5c3, 0x3e4ccccd,
0x3ecccccd, 0x3f19999a, 0x3c888889 equal to the port's spellings; _saturate bounds 0 / 1
(fl.py 0x475358..0x475364).

Leads for other lists:
- zFTS header: CGameState has no ctor (edit file above); CMenuState's ctor (state_holding.cpp
  line 10) also names itself with zstrdup("MenuState"), probably the same inline SetName.
- zTwoD header: C2DString's Load overloads are non-virtual in ztwod.h where the ELF calls them
  through slots +0x68..+0x70 (#189); no class overrides them, so nothing differs today.
- zUtil header: COutput's ELF layout (no DWARF) is +0 CFileIO*, +4 word, +8 doLog byte, +0xc
  word (16 bytes, ctor 0x3043a0); zutil.h has only doLog and the file (no reader of the others).
- zUI: zui_2d.cpp line 2551 (another function) also uses "" for the achFallback$3573 address.

What the packets lacked: the slot +0x78 method of #12 (named C2D::Off; ClearAndWipe, as small-b
found); vt.py 0x473af0 to confirm #231's slot +0x60 against SetString's +0x5c; the bodies of
C2DString::Format / SetString (#231), C2D::On / Off (#193 / #194), ~CKey (#27..#29), ~CFileIO
and CIO (#272), CGameState (#16 / #17 / #21), CActiveAnimPool::PutBack's users (#59); the
fts_remote packet structs (source, for the t0..t3 arguments checked by hand); CTeleType's ELF
offsets (zui.h comments); COutput's layout (no DWARF: the ctor and dtor, and ref.dis for debug's
readers); CSTable's _malloc (zsys_memory.cpp); fl.py for the _saturate bounds (#159 / #162).
Roughly 14 functions needed a lookup outside the packet.

Runs: default build linked (audit-small-d-default, 0 undefined, the fts_state.h edit file applied
through shared.txt); one menus round trip (gate.ps1 -Only roundtrip -Missions 3 on this tree: PASS, 3 returns to the menus, in use 18,657,916 B flat; menus, m8 loading and the static CSTable / CCoreState ctors ran with the fixes).

## Verdicts

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 10 | 0x3d1a70 | 96 | CWeaponSel::Increment(float, float, float) | hud_weaponsel.cpp | DEFECT-FIXED | C | up branch c.lt.s / add / c.le.s as the port; the down branch tests !(val <= goal) (c.le.s 0x3d1a9c) and clamps when val - inc < goal (c.lt.s 0x3d1ab0): the port's goal < val / goal <= v differed for NaN only; rewritten in the ELF's form |
| 11 | 0x3d2e90 | 192 | CWeaponSel::AfterCloseFirst() | hud_weaponsel.cpp | MATCH | - | goalheight (y + 32 + 2) - (y - 1) (2 + (32 + y), commutative), stored to cur, reloaded / 2 to centery; goaly / goalx from slot 1, startx 0, state 7; Off (slot +0x18) on icon 0, back 0, icon 2, back 2 in that order |
| 12 | 0x3d4390 | 160 | CWeaponSel::UnInit() | hud_weaponsel.cpp | MATCH | - | OnClose when +0xc78 m_openstate != 0; slot +0x78 (ClearAndWipe; the packet names C2D::Off) on the seven texts in the port's order |
| 13 | 0x17ca80 | 12 | CCoreState::Unload() | st_core.cpp | MATCH | - | sb zero +0xb4 m_loading / +0xb5 m_loadstarted, tail j auxUnload |
| 14 | 0x17cbe0 | 140 | LoadThreadEntry(void*) | st_core.cpp | MATCH | - | skyColor words 190 / 220 / 250 (theGame+0x1a4..0x1ac), doSetupBuffers(m_texmanager, GetDatabase()), exit(0) when testLoad fails, LoadLibs on m_MPexitState when theNetwork+0x9 m_bNetwork (lbu), m_loading cleared in ExitDeleteThread's delay slot |
| 15 | 0x17cc70 | 92 | CCoreState::UnInit() | st_core.cpp | MATCH | - | GIF MODE 0x10003010 &= -5, sync; +0xb4 / +0xb5 cleared; auxUnload, CValve::Reset, ClearFreeList(zTaskScheduler, 1), MaxFrameRate(-1); the port's trace is instrumentation only |
| 16 | 0x17d670 | 188 | CCoreState::~CCoreState() | st_core.cpp | MATCH | - | nothing of its own; the ELF's inlined ~CGameState twice (m_name freed "zgame.h" 84 and zeroed, the second pass finds it NULL) is the port's one ~CGameState; deleting part by the flag (compiler) |
| 17 | 0x17d730 | 184 | CCoreState::CCoreState() | st_core.cpp | DEFECT-FIXED | C | name by the inline SetName: _strdup("CoreState", "zgame.h", 84) at 0x17d788 after the test / free of m_name; the port's zstrdup tagged st_core.cpp / __LINE__: now SetName. CGameState's inline ctor zeroes m_name first (sw 0x17d750): the port's CGameState has no ctor (edit file fts_state_h_gamestate_ctor.txt). Unit matrices at +0x20 / +0x60, +0xb4 / +0xb5 / +0xbc m_skip_swap zeroed |
| 18 | 0x17d8c0 | 52 | CCoreState::OnPush(int) | st_core.cpp | MATCH | - | zSysFifoEnd, sceGsSyncPath(0, 0), m_pads[0] bytes +0xd and +0xc zeroed (GCC merges them into one sh) |
| 19 | 0x17d900 | 196 | CCinematicState::UnInit() | st_core.cpp | MATCH | - | CMPEG::Uninit, FIFO end / disable, ReadGsMemory(gsTexAddr, pBuffer_MotionRdr, mpegWorkspaceSize), MaxFrameRate(+0x10), displayBuf 0, renderBuf = save[1] < save[0] ? save[0] : save[1] (slt / movz), doMpeg224 sb 0, GIF MODE |= 4, sync; m_moviename freed "st_core.cpp" 275 and zeroed; Fade(1.0f, 0, 0, 0) |
| 20 | 0x17dc60 | 96 | CCinematicState::SetMovie(char const*) | st_core.cpp | MATCH | - | +0xc freed (97), zeroed, _strdup(name, "st_core.cpp", 98) stored |
| 21 | 0x17dcc0 | 164 | CCinematicState::~CCinematicState() | st_core.cpp | MATCH | - | m_moviename freed (89) and zeroed, then the inline ~CGameState (zgame.h 84); deleting part by the flag |
| 37 | 0x1df300 | 164 | CZBodyAnimCallbackList::Clear() | body.cpp | MATCH | - | this's entries (data +0x8, size +0x4): each non-NULL one's string dtor then operator delete (the port's delete *it); the global's size zeroed and swapped with an empty temp, the temp destroyed (port: swap with an empty vector) |
| 38 | 0x1df5b0 | 96 | CZBodyAnim::~CZBodyAnim() | body.cpp | MATCH | - | vtable, ~CZSIScript, deleting part (compiler) |
| 39 | 0x1df870 | 176 | CBody::~CBody() | body.cpp | MATCH | - | Destroy, then the vectors at +0x3c / +0x30 / +0x24 (members, compiler) |
| 40 | 0x1dfa30 | 128 | CZBodyAnimBlend::CountAnims() | body.cpp | MATCH | - | Begin / Next on +0x34 m_anims; one per anim plus one per +0xc overlay link |
| 41 | 0x1dfab0 | 104 | CZBodyAnimBlend::FindAnim(CZBodyAnim*) | body.cpp | MATCH | - | first active whose +0x0 m_anim equals the argument, else 0 |
| 42 | 0x1dfeb0 | 124 | CZBodyAnimBlend::ReverseDir() | body.cpp | MATCH | - | bit 0x20 of +0x2c cleared then set (a one-bit store: = the port's or); first anim's +0xc tScale = -fabsf; +0x1c tfrac = +0xc quitT when bit 0x40 clear |
| 43 | 0x1dff30 | 32 | CZBodyAnimBlend::Representative() | body.cpp | MATCH | - | Begin()->+0x0, no NULL test |
| 44 | 0x1dff50 | 44 | CZBodyAnimBlend::SetRepresentativeWt(float) | body.cpp | MATCH | - | Begin()->+0x4 = wt |
| 45 | 0x1dff80 | 20 | CZBodyAnimBlend::ThisFoot() | body.cpp | MATCH | - | fptosi(60 * +0x1c) (truncation) |
| 46 | 0x1e0fc0 | 100 | CBlendOverlay::CallbackTick(void*, float) | body.cpp | MATCH | - | +0x14 func set and IsTriggerTime(+0x10, dT): func(body, +0x18), then +0x14 / +0x10 / +0x18 zeroed |
| 47 | 0x1e1980 | 124 | ACTIVE_ANIM::ClearOverlays(CBody*) | body.cpp | MATCH | - | next read first; each overlay cleared and RTArray::PutBack on body+0x18 (the inline CActiveAnimPool::PutBack the port calls); +0xc zeroed |
| 48 | 0x1e1a00 | 40 | ACTIVE_ANIM::Clear() | body.cpp | MATCH | - | words +0x0 / 4 / c / 10 / 8 / 14 / 18, halves +0x1c / +0x1e zeroed |
| 49 | 0x1e1a30 | 40 | CActiveAnimPool::PutBack(ACTIVE_ANIM*) | body.cpp | MATCH | - | inline Clear, tail j RTArray::PutBack |
| 50 | 0x1e1a60 | 152 | CActiveAnimPool::GetActiveAnim(CZBodyAnim*) | body.cpp | MATCH | - | GetNext(1); NULL out; cleared, +0x0 = anim; anim's +0x1e bits 0x2 and 0x4 set (one-bit stores) when anim is set |
| 51 | 0x1e1b00 | 36 | CZBodyAnim::SetTimeScale(float) | body.cpp | MATCH | - | m_looped (lb +0x4 bit 1, signed) then * +0x10 m_multiplier; +0xc stored |
| 52 | 0x1e1b30 | 8 | CZBodyAnim::SetTS(float) | body.cpp | MATCH | - | +0xc = scale |
| 53 | 0x1e1b40 | 112 | CZBodyAnim::TrueLoopTime() | body.cpp | DEFECT-FIXED | C | looped: tf * 1; else (f32)(lh m_pCommon+0x4); fraction (n - 1) / n unless n <= 1 (c.le.s 0x1e1b80): the port's n > 1 (differs for NaN only; n comes from an int): written !(n <= 1); tf * fraction |
| 54 | 0x1e1bb0 | 56 | CZBodyAnim::Reset() | body.cpp | MATCH | - | +0x1e &= 0xffbf, +0xc = fabsf(+0xc) |
| 55 | 0x1e1d20 | 160 | CZBodyAnim::CopyValues(CZBodyAnim*) | body.cpp | MATCH | - | +0x18 id (lh / sh), +0x1a = -1, +0x1c basepart, +0x1e flags with 0x80 cleared when set, the four index bytes +0x20..+0x23, SetLoopTime(other +0x8), SetMultiplier(0), +0xc = 1.0f |
| 56 | 0x1e1dc0 | 84 | CZBodyAnim::GetMaxVelocity() | body.cpp | MATCH | - | looped and +0x1e bit 0x200 clear: 100.0f, else 1.0f |
| 57 | 0x1e2210 | 88 | CZBodyAnim::GetCallbackIndex(int) | body.cpp | MATCH | - | slot 3 / 2 / 1 / 0 tested in that order, lbu +0x23 / 22 / 21 / 20, else 0 |
| 58 | 0x1e2270 | 92 | CZBodyAnim::SetCallbackIndex(int, int) | body.cpp | MATCH | - | index < 256 (slti, signed), then the slot tests in order 3 / 2 / 1 / 0, sb |
| 59 | 0x1e22d0 | 124 | CBody::ClearBlendOverlay() | body.cpp | DEFECT-FIXED | C | the overlay's +0x0 anim cleared once and RTArray::PutBack (0x1e2310: CActiveAnimPool::PutBack inline); the port cleared it by hand and then called CActiveAnimPool::PutBack, which clears again: now only PutBack. The overlay's words +0x0 / 4 / 8, halves +0xc / +0xe, callback +0x14 / +0x10 / +0x18 zeroed |
| 60 | 0x1e29b0 | 8 | CBody::BodySetState(int) | body.cpp | MATCH | - | sb +0xd m_state |
| 61 | 0x1e29c0 | 56 | CBody::GetAnimById(int) | body.cpp | MATCH | - | negative: 0; unsigned id < +0x28 size: data[id], else 0 |
| 62 | 0x1e2b00 | 156 | CBody::Snap() | body.cpp | MATCH | - | each non-NULL part: +0x0..+0x8 to +0x28..+0x30, the quat +0x10..+0x1c to +0x40..+0x4c (PNT3D operator= and w) |
| 63 | 0x1e2ba0 | 168 | CBody::SetBlendPool(int) | body.cpp | MATCH | - | CBlendPool(size, 1, 0) to +0x1c, CActiveAnimPool(3 size, 1, 0) to +0x18, CBodyAnimBlendStack(size) to +0x20 |
| 64 | 0x1e2c50 | 124 | CBody::AddAnim(CZBodyAnim*, int, int) | body.cpp | MATCH | - | insert at the end of +0x24 (push_back); anim set: sh +0x18 id, sh +0x1a type |
| 65 | 0x1e3070 | 160 | CBody::FindPart(char const*) const | body.cpp | MATCH | - | each non-NULL part: strcmp(node ? node+0x90 m_name : "", name) == 0 returns it |
| 66 | 0x1e3110 | 80 | CBody::FindBodyPart(int) | body.cpp | MATCH | - | first non-NULL part with lh +0x24 == id |
| 67 | 0x1e3240 | 136 | CBody::AttachAuxPart(CZBodyPart*, CZBodyPart*) | body.cpp | MATCH | - | +0x20 = parent; node = +0xc; parent: parent->m_node->AddChild(node) (slot +0x18); +0xc = node; pushed on +0x3c aux; part returned |
| 68 | 0x1e33e0 | 192 | CBody::AddBodyPart(zdb::CNode*, CZBodyPart*) | body.cpp | MATCH | - | inline NewBodyPart: NullNode (slot +0xc), BodyId(node+0x90) < 0 gives NULL, new 80-byte part, +0x20 parent, sh +0x24 id; data[lh +0x24] = part |
| 69 | 0x1e3850 | 80 | CZBodyPart::~CZBodyPart() | body.cpp | DEFECT-FIXED | C | +0xc m_node zeroed only when set (0x1e386c); the port zeroed it always: the test added back |
| 70 | 0x1e38a0 | 116 | CZBodyPart::CZBodyPart(zdb::CNode*) | body.cpp | MATCH | - | +0x24 = -1, +0x26 = 1 (halves), +0xc node, +0x20 0, m_pos = CPnt3D::zero, m_rot = CQuat::identity word by word |
| 71 | 0x1f1e20 | 68 | CEntity::UpdateNextPosition() | ent_entity.cpp | MATCH | - | quat +0x70..+0x7c to +0x50..+0x5c, velw +0x60..+0x68 to +0x2c..+0x34, tail SetMatrix(+0x1c node, this+0x80 m_next_matrix) |
| 72 | 0x1f1f80 | 8 | CEntity::PostTick(float) | ent_entity.cpp | MATCH | - | empty |
| 73 | 0x1f1f90 | 8 | CEntity::PrePostTick(float) | ent_entity.cpp | MATCH | - | empty |
| 74 | 0x1f1fa0 | 8 | CEntity::PostPreTick(float) | ent_entity.cpp | MATCH | - | empty |
| 75 | 0x1f1fb0 | 8 | CEntity::Tick(float) | ent_entity.cpp | MATCH | - | empty |
| 76 | 0x1f1fc0 | 8 | CEntity::PreTick(float) | ent_entity.cpp | MATCH | - | empty |
| 77 | 0x1f2000 | 44 | CEntity::SetController(CEntityCtrl*) | ent_entity.cpp | MATCH | - | old +0xc0's +0x4 m_entity zeroed when set; +0xc0 = ctrl, reloaded; its +0x4 = this when set |
| 197 | 0x3853b0 | 8 | CRenderableString::Tick(float) | zui_2d.cpp | MATCH | - | tail C2DString::Tick |
| 198 | 0x3853c0 | 36 | CRenderableString::SetMapOffset(int, int) | zui_2d.cpp | MATCH | - | cvt.s.w x / y to m_offset +0x94 / +0x98, +0x9c zero |
| 199 | 0x385500 | 8 | CListItemTypeImpl::Tick(float) | zui_2d.cpp | MATCH | - | empty |
| 200 | 0x385600 | 76 | CListItemTypeImpl::~CListItemTypeImpl() | zui_2d.cpp | MATCH | - | vtable and the deleting part only (compiler) |
| 201 | 0x385650 | 8 | CListItemTypeImpl::SetSequenceTime(float, float) | zui_2d.cpp | MATCH | - | returns $f12 |
| 202 | 0x385660 | 8 | CListItemTypeImpl::Finish() | zui_2d.cpp | MATCH | - | empty |
| 203 | 0x385670 | 156 | ListItem::~ListItem() | zui_2d.cpp | MATCH | - | +0x20 USERDATA freed ("zui_2d.cpp" 4524) and zeroed; +0x30 impl's deleting dtor (slot +0x8, flag 1) when set; the two ActionItem members (compiler) |
| 204 | 0x385710 | 8 | CListItemTypeImpl::IsEnabled() | zui_2d.cpp | MATCH | - | returns 1 |
| 205 | 0x385820 | 188 | CUIMapCtrl::GetZAnimCmdType(char const*) | zui_2d.cpp | MATCH | - | NULL +4, "" 0, Pan +1, ZOOM_IN +2, ZOOM_OUT +3 (strcasecmp(literal, name)), else GetUICommandType(NULL) |
| 206 | 0x386ec0 | 180 | C2DVisual::Render(CMatrix*) | zui_2d.cpp | MATCH | - | opacity = thePipe stack[index]; < 1 (c.lt.s): 0.99f (0x3f7d70a4) == it gives 1, SetTrans(128 * op) (slot +0x20); Draw(*transform, +0x6c reloc) (slot +0x10) on +0x68 |
| 207 | 0x386f80 | 152 | CPopUpDialog::GetZAnimCmdType(char const*) | zui_2d.cpp | MATCH | - | NULL +1, "" 0, Caption +1, Background +2, else GetUICommandType(NULL) (the quirk kept) |
| 208 | 0x388cf0 | 100 | CRenderableString::GetZAnimCmdType(char const*) | zui_2d.cpp | MATCH | - | NULL +2, "" 0, Caption +1, else GetUICommandType(NULL) |
| 209 | 0x388d60 | 168 | CRenderableString::TickZAnimCmd(_zanim_cmd_hdr*, float*, bool*) | zui_2d.cpp | MATCH | - | ZAnim.m_CurAnim read first; lbu +0x6 - GetUICommandType(NULL) == 1: SetString(GetName(lbu +0x7)) (slot +0x5c), Update (slot +0x8c), *result = 1, returns 1; else 0 |
| 210 | 0x388ee0 | 84 | C2DVisual::C2DVisual(C2D*, zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | CVisual(), vtable, +0x68 object, +0x6c reloc |
| 211 | 0x3890c0 | 120 | CTickerTapeText::SetString(char const*) | zui_2d.cpp | MATCH | - | string(text), assigned text + text, C2DString::SetString(c_str) |
| 212 | 0x3891b0 | 8 | CTickerTapeText::Draw(CMatrix const&, zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | empty |
| 213 | 0x3891c0 | 76 | CTickerTapeText::Tick(float) | zui_2d.cpp | MATCH | - | +0xb4 scroll += dT * +0xac speed; zeroed unless scroll <= +0x40 length / 2 (c.le.s, as the port) |
| 214 | 0x389210 | 168 | CScrollText::HandlePad(CPad const*, int) | zui_2d.cpp | MATCH | - | CanHandleInput (slot +0x34) else 0; DOWN (+0x18) FALLING and topLine < size - lines (unsigned): ++, 1; UP (+0x17) FALLING and topLine > 0: --, 1; else 0 (the word-count quirk kept) |
| 215 | 0x3892c0 | 192 | CScrollText::Tick(float) | zui_2d.cpp | MATCH | - | GetSpacing (slot +0x74) first; step 30 dT; target (f32)topLine * spacing; d = target - scroll; |d| through fabs on a double (bit-equal to fabsf); !(step <= |d|): scroll = target; d < 0 negates step; scroll += step |
| 216 | 0x389380 | 12 | CWrappedText::GetSpacing() | zui_2d.cpp | MATCH | - | cvt.s.w of +0xb0 m_spacing |
| 217 | 0x389390 | 92 | CScrollText::LoadSpec(CScrollSpec const&) | zui_2d.cpp | MATCH | - | lines, width (float), spacing, fptosi(height) in that order, then CRenderableString::LoadSpec |
| 218 | 0x389770 | 116 | CPopUpDialog::Load(zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | +0xa0 reloc; SetFont(+0x15c font) on the text, the yes and no captions; text scale 1.0, width 100.0, spacing 20, Update (slot +0x8c); v0 = 0 that its one caller does not read (port void) |
| 219 | 0x389ae0 | 48 | CPopUpDialog::Tick(float) | zui_2d.cpp | MATCH | - | +0x18c child's Tick (slot +0x24) when set |
| 220 | 0x38ad50 | 12 | CRadioStrip::LoadSpec(CRadioStripSpec const*, zdb::CTexHandle*) | zui_2d.cpp | MATCH | - | sb 1 m_init, tail C2DButton::LoadSpec(*spec) |
| 221 | 0x38b850 | 52 | CHProgressBar::Tick(float) | zui_2d.cpp | MATCH | - | progress += dT / duration, stored; 1 unless <= 1 (c.le.s, as the port) |
| 222 | 0x38ba00 | 160 | CHProgressBar::UpdateUIVar(CUIVariable*) | zui_2d.cpp | MATCH | - | REAL: inline GetReal; INTEGER: (f32) inline GetInt (fptosi branch dead); progress 0 |
| 223 | 0x38baa0 | 72 | CSliderBar::UpdateUIVar(CUIVariable*) | zui_2d.cpp | MATCH | - | REAL only: +0x4 real stored (the dead INTEGER branch of the inline GetReal) |
| 224 | 0x38c8e0 | 188 | CUIListBox::GetZAnimCmdType(char const*) | zui_2d.cpp | MATCH | - | NULL +5, "" 0, Finish +1, Highlight_on +1 (quirk), Has_Items +4, else GetUICommandType(NULL) |
| 225 | 0x38ec90 | 8 | CHandlerButton::LoadSpec(CHandlerButtonSpec const&) | zui_2d.cpp | MATCH | - | tail C2DButton::LoadSpec |
| 226 | 0x38eeb0 | 100 | C2DButton::GetZAnimCmdType(char const*) | zui_2d.cpp | MATCH | - | NULL +2, "" 0, Caption +1, else GetUICommandType(NULL) |
| 227 | 0x38ef20 | 148 | C2DButton::TickZAnimCmd(_zanim_cmd_hdr*, float*, bool*) | zui_2d.cpp | MATCH | - | type - GetUICommandType == 1: +0x1c = GetName(+0x7); set: _strCaption SetString (slot +0x5c) and UpdatePos; returns 0, *result untouched |
| 228 | 0x390640 | 156 | CTeleType::SetString(char const*) | zui_2d.cpp | MATCH | - | C2DString::SetString(""); NULL / empty: +0x3b0 length and +0x3b4 index zeroed; else +0x3b4 / +0x3b8 / +0x3c8 / +0x3d4 zeroed, +0x3b0 strlen, +0x3ac 0, sprintf(+0xac, "%s"), Update (slot +0x8c) (offsets from zui.h's ELF comments) |
| 229 | 0x390c70 | 8 | CTeleType::GetSpacing() | zui_2d.cpp | MATCH | - | lwc1 +0x3cc m_spacing |
| 230 | 0x390c80 | 184 | CPlainBmp::Tick(float) | zui_2d.cpp | DEFECT-FIXED | C | pulsing (lbu +0x88): curtrans += 2pi (0x40c90fdb) * (dT / period); minus 2 pi unless curtrans <= 2 pi (c.le.s 0x390cb8): the port's > (NaN only) written !(<=); + 2 pi when < 0; SetTrans(64 + 64 sinf) (slot +0x20) |
| 231 | 0x390f10 | 148 | CRenderableString::UpdateUIVar(CUIVariable*) | zui_2d.cpp | DEFECT-FIXED | B | the zeroed 768-byte buffer, +0x8c m_uivar set and == var: CUIVariable::Format, then slot +0x60 (vt.py 0x473af0: C2DString::Format(const char*, ...), the packet named it) at 0x390f78, then Update (slot +0x8c). The port called SetString: a value's "$" escapes were shown raw and m_Ustring was not kept; now Format |
| 232 | 0x391c70 | 8 | CRenderableString::Update() | zui_2d.cpp | MATCH | - | empty |
| 233 | 0x391d50 | 144 | CRenderableString::CRenderableString() | zui_2d.cpp | MATCH | - | C2DString(), the mixin's vtable and +0x8c m_uivar 0 (UIVarMixin ctor), vtables, +0x90 font 0, +0x48 scale 2.0, colour 255.0 x3, m_offset = CPnt3D::zero |
| 234 | 0x393260 | 8 | UiSetTtySpeedFactor(float) | zui_2d.cpp | MATCH | - | g_fTtySpeedFactor = factor |
| 235 | 0x393270 | 8 | UiSetCounterSpeedFactor(float) | zui_2d.cpp | MATCH | - | g_fCounterSpeedFactor = factor |
| 236 | 0x393350 | 8 | CListItemImageTypeImpl::DrawPrep(CUIListBox const&, int, int, int) | zui_2d.cpp | MATCH | - | empty |
| 237 | 0x393360 | 8 | CListItemImageTypeImpl::GetString() | zui_2d.cpp | MATCH | - | address of the static ach (0) |
| 238 | 0x393370 | 8 | CListItemImageTypeImpl::PrepListItem(std::vector<ColumnData*> const&, C2DFont*, float, zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | empty |
| 239 | 0x393380 | 8 | CListItemImageTypeImpl::SetFont(C2DFont*) | zui_2d.cpp | MATCH | - | empty |
| 240 | 0x393390 | 8 | CListItemImageTypeImpl::SetPos(int, int, int, int) | zui_2d.cpp | MATCH | - | tail C2DBitmap::SetPos on +0x10 m_bmp, the four arguments through |
| 241 | 0x3933a0 | 8 | CListItemImageTypeImpl::SetScale(float) | zui_2d.cpp | MATCH | - | empty |
| 242 | 0x3933b0 | 40 | CListItemImageTypeImpl::SetColor(int, int, int) | zui_2d.cpp | MATCH | - | cvt.s.w r / g / b to $f12.., tail C2DBitmap::SetColor on +0x10 |
| 243 | 0x3933e0 | 32 | CListItemImageTypeImpl::VisualGratification(zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | m_bmp's Draw (slot +0x10) with CMatrix::identity and reloc; the port's direct call on the member object is the same method |
| 244 | 0x393400 | 136 | CListItemTimedTextTypeImpl::~CListItemTimedTextTypeImpl() | zui_2d.cpp | MATCH | - | vtables, the string member's ~CRenderableString, deleting part (compiler) |
| 245 | 0x393490 | 8 | CListItemTimedTextTypeImpl::Finish() | zui_2d.cpp | MATCH | - | +0xb4 m_start zero |
| 246 | 0x3934a0 | 12 | CListItemTimedTextTypeImpl::SetSequenceTime(float, float) | zui_2d.cpp | MATCH | - | +0xb4 = time, returns time + interval |
| 247 | 0x3934b0 | 100 | CListItemTimedTextTypeImpl::Tick(float) | zui_2d.cpp | MATCH | - | started = !(+0xb8 elapsed <= +0xb4 start); elapsed += dT; not started and now !(elapsed <= start): PlayCountSound; no string Tick (quirk kept) |
| 248 | 0x393520 | 68 | CListItemTimedTextTypeImpl::VisualGratification(zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | unless elapsed < start (c.lt.s): C2DString::Draw(+0x4, reloc, NULL, 16777210.0f = 0x4b7ffffa) |
| 249 | 0x393570 | 40 | CListItemStringTypeImpl::GetString() | zui_2d.cpp | MATCH | - | string's +0x30 m_Ustring when set and non-empty (lb), else +0x24 m_string |
| 250 | 0x3935a0 | 8 | CListItemStringTypeImpl::PrepListItem(std::vector<ColumnData*> const&, C2DFont*, float, zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | empty |
| 251 | 0x3935b0 | 8 | CListItemStringTypeImpl::SetFont(C2DFont*) | zui_2d.cpp | MATCH | - | tail C2DString::SetFont on +0x4 |
| 252 | 0x3935c0 | 20 | CListItemStringTypeImpl::SetPos(int, int, int, int) | zui_2d.cpp | MATCH | - | x << 4 to +0x84, y << 4 to +0x88 (string m_pos) |
| 253 | 0x3935e0 | 8 | CListItemStringTypeImpl::SetScale(float) | zui_2d.cpp | MATCH | - | +0x4c string m_scale |
| 254 | 0x3935f0 | 52 | CListItemStringTypeImpl::SetColor(int, int, int) | zui_2d.cpp | MATCH | - | sb 1 +0xb0 m_colorSet, cvt.s.w to the string's m_color +0x54..+0x5c |
| 255 | 0x393630 | 96 | C2DVisual::~C2DVisual() | zui_2d.cpp | MATCH | - | vtable, ~CVisual, deleting part (compiler) |
| 256 | 0x393690 | 8 | C2DVisual::Get2DVisual() | zui_2d.cpp | MATCH | - | returns this |
| 257 | 0x393790 | 108 | CScrollText::~CScrollText() | zui_2d.cpp | MATCH | - | vtables, ~CWrappedText (compiler) |
| 258 | 0x393a30 | 96 | CRadioStrip::~CRadioStrip() | zui_2d.cpp | MATCH | - | vtable, ~C2DButton (compiler) |
| 259 | 0x393b90 | 8 | CCheckBox::UpdateUIVar(CUIVariable*) | zui_2d.cpp | MATCH | - | empty |
| 260 | 0x393fc0 | 96 | CHandlerButton::~CHandlerButton() | zui_2d.cpp | MATCH | - | vtable, ~C2DButton (compiler) |
| 261 | 0x394020 | 20 | C3StateButton::Tick(float) | zui_2d.cpp | MATCH | - | _strCaption (+0x20) Tick through its vtable (slot +0x24); the port's call on the member object reaches the same method |
| 262 | 0x394180 | 20 | CListItemStringTypeImpl::Tick(float) | zui_2d.cpp | MATCH | - | +0x4 string's Tick (slot +0x24), as #261 |
| 263 | 0x3941a0 | 28 | CListItemStringTypeImpl::VisualGratification(zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | tail C2DString::Draw(+0x4, reloc, NULL, 16777210.0f) |
| 264 | 0x3942f0 | 124 | CListItemArrayTypeImpl::Finish() | zui_2d.cpp | MATCH | - | each cell (size +0x8 reread): impl +0x30's Finish (slot +0x10) when set |
| 265 | 0x394370 | 80 | CListItemArrayTypeImpl::GetString() | zui_2d.cpp | DEVIATION-KEPT | - | cell 0's impl GetString (slot +0x14) when set, no size test; else the address of achFallback (0x3943b0), PrepListItem's fenced function-local static that this function cannot name: the port's "" gives the same empty text (reason now in the code) |
| 266 | 0x3944b0 | 8 | CListItemArrayTypeImpl::IsEnabled() | zui_2d.cpp | MATCH | - | lbu +0x10 m_enabled |
| 267 | 0x3944c0 | 8 | CListItemArrayTypeImpl::SetPos(int, int, int, int) | zui_2d.cpp | MATCH | - | empty |
| 268 | 0x3945c0 | 168 | CListItemArrayTypeImpl::SetColor(int, int, int) | zui_2d.cpp | MATCH | - | each cell: impl's SetColor(r, g, b) (slot +0x28) when set |
| 269 | 0x394670 | 132 | CListItemArrayTypeImpl::SetSequenceTime(float, float) | zui_2d.cpp | MATCH | - | each cell with an impl: time = its SetSequenceTime(time, interval) (slot +0x2c); returns time |
| 270 | 0x394700 | 136 | CListItemArrayTypeImpl::Tick(float) | zui_2d.cpp | MATCH | - | each cell: impl's Tick(dT) (slot +0x30) when set |
| 271 | 0x394790 | 136 | CListItemArrayTypeImpl::VisualGratification(zdb::CTextureRelocMgr*) | zui_2d.cpp | MATCH | - | each cell: impl's VisualGratification(reloc) (slot +0x34) when set |
| 279 | 0x306040 | 176 | CSTable::FindString(char const*) const | util_stable.cpp | MATCH | - | NULL str: 0; each slot: non-NULL, strlen(str) and strlen(slot) non-zero, strcmp(slot, str) == 0 returns the slot; else 0 |
| 280 | 0x3060f0 | 184 | CSTable::Clear() | util_stable.cpp | MATCH | - | +0x10 buffer: memset(buffer, 0, +0x18 reserve), +0x14 bytes 0; else each string _free ("util_stable.cpp" 37, no NULL test) and its slot zeroed; size 0 |
| 281 | 0x3062b0 | 68 | CSTable::ReleaseBuffer(bool) | util_stable.cpp | MATCH | - | owner and buffer set: _free (182); +0x10 zeroed on both paths |
| 282 | 0x306500 | 144 | CSTable::Relocate(void*) | util_stable.cpp | MATCH | - | size 0 or no buffer: 0; offset = buffer - m_buffer, memcpy(buffer, m_buffer, +0x14), the empty entry walk (quirk kept), offset returned |
| 283 | 0x3067b0 | 172 | CSTable::CSTable(unsigned int, unsigned int) | util_stable.cpp | DEFECT-FIXED | C | vector, sb 1 +0xc owner, +0x10 / +0x14 / +0x18 zeroed; size: +0x18 = size, +0x10 = _malloc(size, "util_stable.cpp", 25) (0x306824), reserve(count). The port called libc malloc (no tag, no interrupt guard of _malloc): now _malloc |
| 22 | 0x3788a0 | 8 | CMenuState::RestartBackgroundMPEG() | st_menu.cpp | MATCH | - | tail CGameMenu::RestartBackgroundMPEG(+0x8) |
| 23 | 0x3788b0 | 8 | CMenuState::HaltBackgroundMPEG() | st_menu.cpp | MATCH | - | tail CGameMenu::HaltBackgroundMPEG(+0x8) |
| 24 | 0x378e10 | 96 | CMenuState::OnPop(int) | st_menu.cpp | MATCH | - | RestartBackgroundMPEG before the +0x8 NULL test; GetEvent("ON_STATE_POP") (the port's file-local GetMenuEvent, the ELF's compare order), non-zero: RunEventAnim(event, NULL); +0x10 m_skip_swap = 2 on both paths |
| 25 | 0x379230 | 8 | CMenuState::OnPush(int) | st_menu.cpp | MATCH | - | tail HaltBackgroundMPEG(+0x8) |
| 26 | 0x3793d0 | 12 | CMenuState::SetSkipMenu(bool) | st_menu.cpp | MATCH | - | sw (u8)skip to +0xc m_skip |
| 91 | 0x2022c0 | 168 | SendGameSignalMessage(int, unsigned char, unsigned char, unsigned char, int, bool) | fts_remote.cpp | MATCH | - | theNetwork+0x8 master; the zero packet (@2666), signal / team / e3 bytes, value word, game_type lb +0xd9, strcpy(+0x8, GetDatabase()); send (64, +0xd0 conn, client, GameSignal, t1 16, t2 &packet, t3 reliable) |
| 92 | 0x202450 | 64 | BombStatePacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | pos copied, HandleBombStateRequest(lbu +0xc, lbu +0xd, &pos), 16 |
| 93 | 0x202660 | 112 | SendVoteMessage(int, int, bool) | fts_remote.cpp | MATCH | - | packet index / vote (movz 1/0); seal found: +0xec2 = vote, send (64, conn, +0xeb8 client, Voter, t1 2, &packet, t3 1) |
| 94 | 0x2026d0 | 132 | PickupAckPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | entity by lbu +0x4; NULL or type byte +0x10 != 2: 0; HandlePickupAck(lbu +0, lhu +2, +5), 6 |
| 95 | 0x202760 | 96 | SendPickupAckMessage(int, unsigned short, unsigned char, AckUnion) | fts_remote.cpp | MATCH | - | host sb, pickup sh, seal sb, ack byte at +5; send (64, conn, -1, PUAck, t1 6, &packet, t3 0) |
| 96 | 0x2027c0 | 144 | PickupMayIPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | entity by GetEntityIDFromNetID(lhu +2); a seal: CanPickupNetItem(lbu +0, lhu +2, +4, t0 lbu +0x14); 22 always |
| 97 | 0x202920 | 172 | AmmoPUPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | pos +0x24..+0x2c; entity by lhu +0x22; a seal: CreateNetAmmoPickup(lbu +0, +2, +0x12, t0 lhu +0x22, t1 &pos); 48 |
| 98 | 0x202e70 | 28 | SendChatMsg(char const*) | fts_remote.cpp | MATCH | - | tail theLobby.Censor(text, AuxSendChatMsg, NULL) |
| 99 | 0x202e90 | 120 | AuxSendChatMsg(char const*, void*) | fts_remote.cpp | MATCH | - | index = lb netgame+0x70; strncpy(+1, text, 32); +0x20 zero; send (64, conn, -1, ChatText, t1 33, &packet, t3 0); ChatPacketHandler(0, 0, 0, &packet) |
| 100 | 0x203200 | 84 | SendMessageMessage(int, R_SEND_TO, int) | fts_remote.cpp | MATCH | - | index sb, (s8)to as a half at +2, message sh +4; send (64, conn, -1, Message, t1 6, &packet, t3 0) |
| 101 | 0x203260 | 184 | ReadyPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | gAllowGhosts, netgame +0xdb == 3 (no NULL test), master: zero packet, signal 14, zeros, game_type, database; send (64, conn, client, GameSignal, 16, &packet, t3 1); 4 |
| 102 | 0x203320 | 152 | NetSendRequestTeamSwitch(int) | fts_remote.cpp | MATCH | - | master: my index, master tested again, RequestTeamSwitch(me, team); else conn read before the master index, send (64, conn, master, TeamSwitch, t1 4, &team, t3 1) |
| 103 | 0x2033c0 | 52 | TeamSwitchPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | master: RequestTeamSwitch(client, *data); 4 |
| 104 | 0x203400 | 176 | NetSendE3Index(int, unsigned int, int, bool) | fts_remote.cpp | MATCH | - | team sw, index sb; own client: index fetched again, NetworkTeam(+0), SetE3Index(lbu +4), UpdateLocalPersona; else send (64, conn, client, E3Index, t1 8, &packet, t3 reliable) |
| 105 | 0x2034b0 | 84 | E3IndexPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | NetworkTeam(lw +0), SetE3Index(lbu +4), UpdateLocalPersona; 8 |
| 106 | 0x203510 | 104 | ActionAnimPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | netgame NULL test and +0xdb == 3; ExecuteAction(GetActionById(lhu +4), GetBodyFromObjectIndex(lw +0), 0), no NULL tests; 8 |
| 107 | 0x203580 | 92 | NetSendActionAnim(int, unsigned int, unsigned char, int) | fts_remote.cpp | MATCH | - | theNetwork+0x9; index sw, action sh, arg sh at +6; send (64, conn, client, ActionAnim, t1 8, &packet, t3 0) |
| 108 | 0x2035e0 | 108 | ZAnimNetworkPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | size first; netgame set and in play: NetworkReceive; size returned |
| 109 | 0x203650 | 76 | SendZAnimNetworkPacket(void*, int) | fts_remote.cpp | MATCH | - | +0x9: send (64, conn, -1, ZAnim, t1 size, t2 data, t3 0) |
| 110 | 0x203780 | 168 | NetSendAiOrders(unsigned int, unsigned int, unsigned int, void*) | fts_remote.cpp | MATCH | - | commander / target / command bytes; (u8)command 4 and a point: fptosi x / z bytes; conn before the master index; send (64, conn, master, AiOrders, t1 5, &packet, t3 0) |
| 111 | 0x203830 | 104 | PushBlendAnimPacketHandler(int, int, int, void*) | fts_remote.cpp | MATCH | - | in play; seal by lbu +0; found: PushBlend(lh +2, lbu +4, lbu +5); 6 |
| 112 | 0x2038a0 | 168 | NetSendPushBlend(unsigned int, int, int, bool) | fts_remote.cpp | MATCH | - | +0x9; aux bit 0 of +0x0 network_log; index sb, anim sh, arg sb, flag sb; send (64, conn, -1, PushBlendAnim, t1 6, &packet, t3 0) |
| 113 | 0x203c00 | 132 | SaveFireMessage(CZSealBody*, CPnt3D const*) | fts_remote.cpp | MATCH | - | remote = +0xc0 ctrl ? IsRemote (slot +0x34) : 0; local: +0x17c byte ++, 0 when >= 201; +0x184 = target y |
| 114 | 0x204140 | 120 | zRemoteClientLeavesCallback(int, int) | fts_remote.cpp | MATCH | - | the Medius connection returns; zero fix (@2348, 28 bytes), +0 type 2, +4 client, AddToFixList |
| 115 | 0x2041c0 | 148 | zRemoteClientJoinsCallback(int, int) | fts_remote.cpp | MATCH | - | not Medius: zNetGetClient (unused), valid count; valve netgame+0x40: change = lhu +4 != count ? (count ? 1 : 2) : 0, sh count, MakeCallbacks(change) when non-zero |
| 116 | 0x204260 | 112 | zRemoteClientDisconnectsCallback(int, int, char const*) | fts_remote.cpp | MATCH | - | not Medius: m_LJArray[client] = 0; netgame set and lbu +0x94 late_joiner 0: UpdateLocalGame |
| 127 | 0x2194e0 | 72 | CInput::DeletePad(unsigned int) | zin_main.cpp | MATCH | - | slot < 2 (sltiu) and set: deleting ~CPad (flag 1), slot zeroed |
| 128 | 0x219530 | 168 | CInput::CreatePad(unsigned int) | zin_main.cpp | MATCH | - | slot >= 2: 0; set: returned; new 404-byte CPad(slot, 0) stored; not open: m_pads[0] deleted and zeroed when set; m_pads[0] returned (quirk kept) |
| 129 | 0x2195e0 | 92 | CInput::Flush() | zin_main.cpp | MATCH | - | both pads' Flush when set |
| 130 | 0x219640 | 120 | CInput::Tick(float) | zin_main.cpp | MATCH | - | keyboard Tick when set, then both pads' Tick(dT) when set |
| 131 | 0x2196c0 | 56 | CInput::Uninit() | zin_main.cpp | MATCH | - | keyboard deleted and zeroed when set; ClosePadIO; m_init 0 |
| 132 | 0x219700 | 112 | CInput::Init() | zin_main.cpp | MATCH | - | m_init = OpenPadIO() == 0; RegisterRebootCallback(IOPRebootHandler, NULL); InitKeyreadStuff; new CKeyboard; m_init 1; v0 = 0 its one caller does not read (port void) |
| 133 | 0x2199a0 | 32 | CPad::SetButtonState(PAD_BUTTON, KEY_STATE) | zin_main.cpp | MATCH | - | sb state to +0x13[(u8)button], +0x44 click[button] = -3.0f (0xc0400000) |
| 134 | 0x2199c0 | 56 | CPad::GetTwoButtons(PAD_BUTTON, PAD_BUTTON) | zin_main.cpp | MATCH | - | state[b1] == KEY_DOWN (2), then state[b2] == KEY_FALLING (1); buttons masked to a byte (the port's (u32) of the 1-byte enum is the same) |
| 135 | 0x219a00 | 68 | CPad::GetDoubleClick(PAD_BUTTON) | zin_main.cpp | MATCH | - | click == -2.0f (c.eq.s): -3.0f stored, 1; else 0 |
| 136 | 0x21ae80 | 188 | CStickType::ReadControlFile(int) | zin_main.cpp | MATCH | - | words 0x3c866666 / 0x3c23d70a / 0x3ea8f5c3 / 1.0 / 2.0; stick 0: separate 1 / 1, 0.2 (0x3e4ccccd); else 0 / 1, 0.4 (0x3ecccccd); normalize / dilate 1 (GCC merges the two bytes) |
| 137 | 0x21af40 | 152 | CPad::SetPreset(int, int) | zin_main.cpp | MATCH | - | stick * 32: preset 0: 0.6 (0x3f19999a) / 1 / 0.33; 1: 1 / 1 / 0.33; 2: 1 / 2 / 0.33 at +0x160 / +0x164 / +0x158 |
| 138 | 0x21afe0 | 24 | CPad::GetDeadZone(int) | zin_main.cpp | MATCH | - | +0x158 * deadZoneScaleFactor |
| 139 | 0x21b000 | 32 | CPad::SetDeadZone(int, float) | zin_main.cpp | MATCH | - | +0x158 = dz / deadZoneScaleFactor |
| 140 | 0x21b1d0 | 56 | CPad::GetSensitivity(int) | zin_main.cpp | MATCH | - | (+0x160 - min) / (1 - min) |
| 141 | 0x21b210 | 44 | CPad::SetSensitivity(int, float) | zin_main.cpp | MATCH | - | +0x160 = min + (1 - min) * s |
| 142 | 0x21b240 | 100 | CPad::~CPad() | zin_main.cpp | MATCH | - | +0x8 open: scePadPortClose(+0x0, +0x4); deleting part (compiler) |
| 143 | 0x21b390 | 12 | CPad::IsOpen() const | zin_main.cpp | MATCH | - | +0x8 != 0 |
| 144 | 0x21b5a0 | 72 | CInput::ClosePadIO() | zin_main.cpp | MATCH | - | DeletePad(0), DeletePad(1), scePadEnd |
| 145 | 0x21d830 | 8 | zdb::CDIBBox::GetAltitude(zdb::DiIntersect*) | int_bbox.cpp | MATCH | - | returns 0 |
| 146 | 0x21e350 | 116 | zdb::CDIBBox::~CDIBBox() | int_bbox.cpp | MATCH | - | own vtable, Free through it (slot +0x10: CDI::Free, as the port's call in the dtor resolves), ~CDI, deleting part |
| 147 | 0x21e3d0 | 56 | zdb::CDIBBox::CDIBBox() | int_bbox.cpp | MATCH | - | CDI(), vtable, +0x24 m_box 0 |
| 148 | 0x21e410 | 116 | zdb::CDIPoly::~CDIPoly() | int_bbox.cpp | MATCH | - | as #146 for CDIPoly |
| 149 | 0x3f02c0 | 168 | PTT_HeartbeatPrepare() | znetwork_holding.cpp | MATCH | - | not initialised: -1; WaitSema; buffer word 1 = 40; sceSifCallRpc(&g_cd_hb, 8, 1, buf, t0 0x8000, t1 buf, t2 0x8000, t3 _PTT_HeartbeatCallback, stack NULL) < 0: -1; g_wasPrepared 1, returns 1 |
| 186 | 0x301fd0 | 76 | C2DString::SetFont(C2DFont*) | c2dstring.cpp | MATCH | - | +0x1c = font; 128.0 == +0x5c alpha (c.eq.s): SetTrans(128 * font+0x28 opacity) (slot +0x20) |
| 187 | 0x302170 | 8 | C2DString::NewLine() | c2dstring.cpp | MATCH | - | tail AddCharacter(10) |
| 188 | 0x3022d0 | 8 | C2DString::Update() | c2dstring.cpp | MATCH | - | empty |
| 189 | 0x302480 | 20 | C2DString::Load(float, char const*, C2DFont*, int, int) | c2dstring.cpp | MATCH | - | +0x48 scale, then Load(message, font, x, y) through slot +0x6c (tail); the port's header declares the Load overloads non-virtual (ELF slots +0x68..+0x70), no class overrides them, so the call reaches the same body (lead) |
| 190 | 0x302700 | 128 | C2DString::Draw(zdb::CCamera*) | c2dstring.cpp | MATCH | - | stack CBatchRelocator; IsOn, +0x28 numChars, +0x1c font, font+0x10 handle: MakePacket(&reloc, 0), C2D::Draw(camera) |
| 191 | 0x302c50 | 160 | C2DString::Draw(zdb::CTextureRelocMgr*, zdb::CCamera*, float) | c2dstring.cpp | MATCH | - | the same tests; MakePacket(reloc, fptosi(z)), C2D::Draw(camera) |
| 192 | 0x302cf0 | 192 | C2DString::Tick(float) | c2dstring.cpp | DEFECT-FIXED | C | lbu +0x70 == 1 (GLOWY); t = elapsed + dT / 2 stored; t - fadeTime unless t <= fadeTime (c.le.s 0x302d2c): the port's fadeTime < t (NaN only) written !(t <= fadeTime); sinf(3.14 (0x4048f5c3) * elapsed / fadeTime); SetTrans(128 (min + s (max - min))) (slot +0x20) |
| 193 | 0x302db0 | 8 | C2DString::On() | c2dstring.cpp | DEFECT-FIXED | C | tail j C2D::On (0x302db0); the port set m_on itself (the same store): now C2D::On() |
| 194 | 0x302dc0 | 8 | C2DString::Off() | c2dstring.cpp | DEFECT-FIXED | C | tail j C2D::Off (0x302dc0); as #193: now C2D::Off() |
| 195 | 0x302dd0 | 96 | C2DString::ClearAndWipe() | c2dstring.cpp | MATCH | - | +0x20 freed (72) when set, +0x20 / +0x24 zeroed; +0x2c freed (74), +0x2c / +0x30 zeroed |
| 196 | 0x302e30 | 156 | C2DString::~C2DString() | c2dstring.cpp | MATCH | - | vtable; +0x20 freed (60) and zeroed; +0x2c freed (61) and zeroed; ~C2D; deleting part |
| 272 | 0x304320 | 108 | COutput::~COutput() | util_output.cpp | DEFECT-FIXED | C | +0x0 file's Close (slot +0xc), +0x4 word zeroed, operator delete(file) with no destructor (0x304354); the port also ran the inline ~CFileIO (a second Close) and cleared m_doLog: now Close and ::operator delete. ELF layout (no DWARF): +0 file, +4 word, +8 doLog byte, +0xc word; the port's has no +4 / +0xc (no reader: lead) |
| 273 | 0x304390 | 8 | COutput::DumpLog(char const*) | util_output.cpp | MATCH | - | empty |
| 274 | 0x3043a0 | 116 | COutput::COutput(char const*, bool) | util_output.cpp | MATCH | - | doLog stored (sb +0x8), new 16-byte CFileIO to +0x0, file set: Open(file, 26) (slot +0x8); the ELF also zeroes the +0x4 / +0xc words the port's layout lacks (no reader; see #272) |
| 275 | 0x304420 | 88 | CIOPManager::UnRegisterRebootCallback(int) | util_output.cpp | MATCH | - | remove_if(begin, end, delid{id}) then erase to the end (16-byte records) |
| 276 | 0x304480 | 96 | CIOPManager::RegisterRebootCallback(bool (*)(CIOPManager::RebootPhase, CIOPManager::RebootMode, void*), void*) | util_output.cpp | MATCH | - | record {callback, data, m_last_id (post-increment), flag 0}, insert one at the end, its id returned |
| 277 | 0x3044e0 | 36 | zUtilUninit() | util_output.cpp | MATCH | - | debug's deleting dtor (it tests NULL itself), debug 0 |
| 278 | 0x304510 | 68 | zUtilInit(char const*) | util_output.cpp | DEFECT-FIXED | C | new 16-byte COutput(log, 1) (li a2,1 at 0x304538): the port passed false; debug is read only here and in zUtilUninit (ref.dis), so no effect |
| 284 | 0x307b60 | 84 | zVid_FrameRestore() | zvid_init.cpp | MATCH | - | spr packet: 0x3000000c, &framecode, 0x11000000, 0x5000000c; zSysFifoKick(p, 1) |
| 285 | 0x308160 | 108 | zVid_Sync0() | zvid_init.cpp | MATCH | - | frameNumber dword 0, vsync_odd 1, frameRate 60, frameTime 0x3c888889; sceGsSyncV(0) until non-zero; T0 COUNT (0x10000000) 0 |
| 286 | 0x3081d0 | 68 | zVid_ClearColor(unsigned int*) | zvid_init.cpp | MATCH | - | c0 / c1 << 8 / c2 << 16 (lwu) / 0x80 << 24 / 1.0f << 32 as one dword through zvid+0x244 frame_restore |
| 287 | 0x308390 | 144 | zvid_KickPacket(unsigned long*, int, bool) | zvid_init.cpp | MATCH | - | fifo: qwc / 0x30000000, packet, 0x13000000, qwc / 0x50000000, kick 1; else sceDmaSendN(zSys DmaToGif, packet, qwc), sceGsSyncPath(0, 0) |
| 288 | 0x308500 | 140 | SetGSReg(short, unsigned long) | zvid_init.cpp | MATCH | - | words 0x10000002 / 0 / 0x11000000 / 0x50000002, dwords 0x1000000000008001, 14, value, (s64)(s16)reg; kick 3 |
| 289 | 0x308660 | 44 | zVid_Uninit() | zvid_init.cpp | MATCH | - | theTerminal's deleting dtor when set; zeroed |
| 2 | 0x3b8ec0 | 16 | CHUD::IsOn() | hud_main.cpp | MATCH | - | lbu +0x14955 m_ison |
| 3 | 0x3b9350 | 28 | CHUD::PostDITick(float) | hud_main.cpp | MATCH | - | +0x14460 m_LensFlareFade's Tick through its vtable (slot +0x24), tail; the port's call on the member object reaches the same method |
| 4 | 0x3b9370 | 16 | CHUD::PreDITick(float) | hud_main.cpp | MATCH | - | tail CLensFlareSaturate::PreDITick on +0x14460 |
| 5 | 0x3ba040 | 108 | CHUD::PauseGame() | hud_main.cpp | MATCH | - | GetMenuState of appCamera+0x3c entity's +0xc0 ctrl first (no NULL tests); pause = +0x14038 m_pausetest.m_on, else (u8)state == 4; then !theNetwork+0x9 |
| 6 | 0x3bb3a0 | 52 | GetTextureByName(zdb::CWorld*, char const*) | hud_main.cpp | MATCH | - | m_assets.GetTexHandle(name); set: +0xc texture, else 0 |
| 7 | 0x3bb3e0 | 56 | CHUD::DrawPhase(zdb::_RenderPhase, zdb::CCamera*) | hud_main.cpp | MATCH | - | ((phase & 0xff) - 12) * 28 + 0x14900: that C2D's Draw(camera) (slot +0xc), tail, no range test |
| 8 | 0x3bc100 | 108 | CHUD::HudText_to_upper(char*) | hud_main.cpp | MATCH | - | strlen; each char toupper(lb, signed) stored |
| 9 | 0x3bc170 | 12 | CHUD::GetHUDOwner() | hud_main.cpp | MATCH | - | appCamera+0x3c |
| 122 | 0x217010 | 184 | zdb::CCell::GetMidPoint(CPnt3D*) | grid_cell.cpp | MATCH | - | max (+0x4c).Sub(&min +0x40, &size); size.Scale(0.5f, &half); min.Add(&half, &out); *mid = out (the ELF's temporaries are copies) |
| 123 | 0x2170d0 | 8 | zdb::CCell::RenderClutter(zdb::CCell*) | grid_cell.cpp | MATCH | - | tail CClutterList::Render(+0xcc, cell) |
| 124 | 0x2170e0 | 8 | zdb::CCell::AddClutter(zdb::CClutter*) | grid_cell.cpp | MATCH | - | tail CClutterList::Add(+0xcc, clutter) |
| 125 | 0x2170f0 | 8 | zdb::CCell::DeleteClutter() | grid_cell.cpp | MATCH | - | tail CClutterList::Free(+0xcc) |
| 126 | 0x217300 | 120 | zdb::CCell::UpdateBBox(bool) | grid_cell.cpp | MATCH | - | the inline GetBBox: bit 6 of +0x5f m_use_parent_bbox up two parents (+0x64), the third level through CNode::GetBBox; this+0x40 otherwise |
| 164 | 0x289820 | 8 | CZSealBody::GetCharacter() | seal_create.cpp | MATCH | - | +0x468 m_charType |
| 165 | 0x289830 | 128 | CZSealBody::DeleteCameraEffectsNode() | seal_create.cpp | MATCH | - | GetNode()->FindChild("camera_effects", 1) (slot +0x24); found: +0x64 parent's DeleteChild (slot +0x1c) when set, then its deleting dtor (slot +0x8, flag 1) |
| 166 | 0x28a510 | 76 | CZSealBody::GetSeal(zdb::CNode*) | seal_create.cpp | MATCH | - | NULL: 0; __dynamic_cast(+0x94 m_nodeEx, CNodeEx to CSealEx); found: +0x4 seal, else 0 |
| 168 | 0x2eedf0 | 16 | CSndInstance::PlaySoundCallback(unsigned int, unsigned long) | zsnd_csndinstance.cpp | MATCH | - | the instance (low word, sign-extended) +0x0 = handle |
| 169 | 0x2ef100 | 108 | CSndInstance::DebugSoundList() | zsnd_csndinstance.cpp | MATCH | - | walks m_instancelist doing nothing (the listing compiled out); the port's SOCOM_PORT trace is instrumentation only |
| 170 | 0x2ef170 | 28 | CSndInstance::Init() | zsnd_csndinstance.cpp | MATCH | - | not disabled: m_allpaused 0, m_mastervol 1.0f |
| 171 | 0x2ef190 | 196 | CSndInstance::ResumeAllSounds() | zsnd_csndinstance.cpp | MATCH | - | disabled: nothing; each instance (no NULL test): disabled re-read, +0x1a paused: handle -1: +0x1d pauseASAP cleared if set, else +0x1e continueASAP 1; else snd_ContinueSound(handle) |
| 172 | 0x2ef540 | 172 | CSndInstance::UIStopAllSounds() | zsnd_csndinstance.cpp | MATCH | - | each non-NULL instance, not disabled: handle -1: +0x1c and +0x1b = 1; else snd_StopSound(handle) |
| 173 | 0x2ef5f0 | 12 | CSndInstance::TerminateOnFinish() | zsnd_csndinstance.cpp | MATCH | - | sb 1 +0x1b |
| 174 | 0x2ef600 | 16 | CSndInstance::Set3D(float) | zsnd_csndinstance.cpp | MATCH | - | +0x8 = volume, sb 1 +0x18 |
| 175 | 0x2ef610 | 12 | CSndInstance::IsPlaying() | zsnd_csndinstance.cpp | MATCH | - | +0x0 != 0 |
| 176 | 0x2ef620 | 40 | CSndInstance::IsFading() | zsnd_csndinstance.cpp | MATCH | - | !(+0x20 <= 0) (c.le.s, as the port) |
| 177 | 0x2ef650 | 172 | CSndInstance::FadeOut(float) | zsnd_csndinstance.cpp | MATCH | - | +0x20 = time before the disabled test; flush while pending (-1); vol 0; snd_AutoVol(handle, fptosi(vol * (0 * master)), fptosi(240 time), 2) |
| 178 | 0x2efca0 | 44 | CSndInstance::SetPos(CPnt3D const*) | zsnd_csndinstance.cpp | MATCH | - | not disabled: +0xc..+0x14 = pos |
| 179 | 0x2efcd0 | 100 | CSndInstance::SetPitch(int) | zsnd_csndinstance.cpp | MATCH | - | not disabled; flush while pending; snd_SetSoundPitch(handle, pitch) |
| 180 | 0x2efd40 | 108 | CSndInstance::SetPan(int) | zsnd_csndinstance.cpp | MATCH | - | not disabled; flush while pending; snd_SetSoundVolPan(handle, 0x7fffffff, pan) |
| 181 | 0x2efdb0 | 168 | CSndInstance::SetVol(float) | zsnd_csndinstance.cpp | MATCH | - | not disabled: +0x8 = vol; 2D only: flush while pending; snd_SetSoundVolPan(handle, fptosi(m_vol * ((1024 vol) master)), -2) (the double volume quirk kept) |
| 182 | 0x2efe60 | 68 | CSndInstance::Stop() | zsnd_csndinstance.cpp | MATCH | - | not disabled: handle -1: +0x1c / +0x1b = 1; else snd_StopSound(handle) |
| 183 | 0x2f0240 | 12 | CSndInstance::Cleanup() | zsnd_csndinstance.cpp | MATCH | - | m_removallist's size word zeroed (clear) |
| 27 | 0x1db680 | 180 | zar::CZAR::Insert(char const*, void const*, int) | zar_search.cpp | MATCH | - | NewKey, GetOpenKey, Insert(key, buf, size); true: open->InsertKey(key), key; false and key set: the key deleted (the ELF's inline list dtor = the port's ~CKey, which clears the same list), NULL |
| 28 | 0x1db740 | 156 | zar::CZAR::Insert(char const*, unsigned int) | zar_search.cpp | MATCH | - | as #27 with &value (stack), 4 |
| 29 | 0x1db7e0 | 156 | zar::CZAR::Insert(char const*, int) | zar_search.cpp | MATCH | - | as #28 |
| 30 | 0x1dbed0 | 116 | zar::CZAR::Fetch(char const*, float*) | zar_search.cpp | MATCH | - | no open key: 0; Fetch(open->FindKey(name), buf, 4, t0 0) as a bool |
| 31 | 0x1dbf50 | 116 | zar::CZAR::Fetch(char const*, unsigned int*) | zar_search.cpp | MATCH | - | as #30 |
| 32 | 0x1dbfd0 | 116 | zar::CZAR::Fetch(char const*, int*) | zar_search.cpp | MATCH | - | as #30 |
| 33 | 0x1dc050 | 140 | zar::CZAR::Fetch(char const*, bool*) | zar_search.cpp | MATCH | - | as #30 into a stack byte, size 1; success: *buf = byte != 0 (movz); the success returned |
| 34 | 0x1dc450 | 72 | zar::CKey::InsertKey(zar::CKey*) | zar_search.cpp | MATCH | - | list insert at the end (push_back), key returned |
| 35 | 0x1dc4a0 | 52 | zar::CKey::CKey() | zar_search.cpp | MATCH | - | list ctor, +0xc / +0x10 / +0x14 zeroed |
| 36 | 0x1dc4e0 | 64 | zar::CKey::CKey(char const*) | zar_search.cpp | MATCH | - | list ctor, +0xc = name (not copied), +0x10 / +0x14 zeroed |
| 78 | 0x24c3f0 | 16 | CPickup::GetPickupNetEntityID() | pickup_main.cpp | MATCH | - | (u16)(lhu +0xc >> 8) |
| 79 | 0x24c400 | 32 | CPickup::GetPosW() const | pickup_main.cpp | MATCH | - | +0x0 node: node+0x30 (matrix row 3), else 0 |
| 80 | 0x24c420 | 148 | CPickup::GetMPBomb() | pickup_main.cpp | MATCH | - | empty list 0; first whose type (lbu +0x8 & 0x7f) is 11 |
| 81 | 0x24c610 | 160 | CPickup::FindNetPickup(unsigned int) | pickup_main.cpp | DEFECT-FIXED | C | the empty-list test first (0x24c628), then lhu +0xc == id (whole argument); the port lacked the test (the same result): added |
| 82 | 0x24c6b0 | 16 | CPickup::GetEntityIDFromNetID(unsigned short) | pickup_main.cpp | MATCH | - | (u16)(id >> 8) |
| 83 | 0x24c7a0 | 160 | CPickup::FindPickup(unsigned int) | pickup_main.cpp | MATCH | - | empty list 0; lhu +0xa == id (whole argument) |
| 84 | 0x24cb40 | 160 | CPickup::GetNext(std::list<CPickup*>::generic_iterator<0>&, CPickup::PU_TYPE) | pickup_main.cpp | MATCH | - | empty list 0; from it: iterator advanced past each; (u8)type 0 or the 7-bit type equal returns the pickup; end 0 |
| 85 | 0x24cbe0 | 20 | CPickup::GetFirst() | pickup_main.cpp | MATCH | - | the list's first node (m_list+0x8) as the returned iterator |
| 86 | 0x24cc00 | 176 | CPickup::DestroyNetPickups(unsigned char) | pickup_main.cpp | MATCH | - | iterator advanced before the test; (u8)(netid >> 8) == entity: Destroy; no empty-list test in the ELF |
| 87 | 0x24d180 | 92 | CPickup::SetVisibleByUnit(unsigned int) | pickup_main.cpp | DEFECT-FIXED | C | units 2 / 4 / 8: +0x18 |= 1, |= 2, |= 3 as three read-modify-writes (0x24d1a0..0x24d1c4); else |= unit. The port's single |= 3 had the same result: written as the ELF |
| 88 | 0x24d1e0 | 20 | CPickup::GetVisibleByUnit(unsigned int) | pickup_main.cpp | MATCH | - | (+0x18 & unit) != 0 |
| 89 | 0x24d420 | 124 | CPickup::DebugPickups() | pickup_main.cpp | MATCH | - | an empty walk of the list |
| 90 | 0x24d630 | 16 | CPickup::Open(unsigned int) | pickup_main.cpp | MATCH | - | bit_count = bits, m_isOpen 1 |
| 120 | 0x210860 | 72 | CGTree::RemoveChild(CGTree*) | graph_tree.cpp | MATCH | - | child's +0xc parent == this: the list's remove_if(equal_to child) (= remove), parent zeroed |
| 121 | 0x2108b0 | 160 | CGTree::~CGTree() | graph_tree.cpp | MATCH | - | the child list erased begin..end (clear); deleting part |
| 290 | 0x315030 | 168 | CZAmmoList::GetAmmo(EQUIP_AMMO) | zwep_ammolist.cpp | MATCH | - | first whose lbu +0x20 m_ID == (u8)id (the enum's values fit a byte), else 0 |
| 291 | 0x3150e0 | 148 | CZAmmoList::GetAmmo(int) | zwep_ammolist.cpp | MATCH | - | the index-th entry, else 0 |
| 292 | 0x315250 | 76 | CZAmmoList::AddAmmo(CZAmmo*) | zwep_ammolist.cpp | MATCH | - | non-NULL: inserted at the end |
| 293 | 0x3153f0 | 40 | CZAmmoList::CZAmmoList() | zwep_ammolist.cpp | MATCH | - | the list ctor only |
| 117 | 0x20f940 | 76 | CGEdge::~CGEdge() | graph_edge.cpp | MATCH | - | vtable and the deleting part only |
| 118 | 0x20f990 | 148 | CGEdge::Delete(CGEdge*) | graph_edge.cpp | MATCH | - | +0xc first / +0x10 second, when set: their +0x10 edge list remove_if(equal_to edge); both zeroed; the deleting dtor (slot +0x8, flag 1) behind delete's NULL test; returns 0 |
| 119 | 0x20fa30 | 36 | CGEdge::CGEdge(CGNode*, CGNode*, float) | graph_edge.cpp | MATCH | - | vtable, +0x8 weight, +0x14 0, +0xc first, +0x10 second |
| 150 | 0x224260 | 168 | zdb::CNodeVector::Remove(zdb::CNode const*) | node_vector.cpp | MATCH | - | find; found: remove_copy(it + 1, end, it, node) becomes it; erase(it, end); returns it != end (the moved it: quirk kept) |
| 151 | 0x224310 | 60 | zdb::CNodeVector::Exists(zdb::CNode const*) | node_vector.cpp | MATCH | - | find != end |
| 152 | 0x224460 | 60 | zdb::CVisualVector::Exists(zdb::CVisual const*) | node_vector.cpp | MATCH | - | find != end |
| 153 | 0x224580 | 60 | zdb::CNodeUniverse::GetElement(int) | node_vector.cpp | MATCH | - | negative 0; size < index (unsigned) 0; else at(index) (index == size reaches at: quirk kept) |
| 154 | 0x2245c0 | 76 | zdb::CNodeUniverse::GetIndex(zdb::CNode*) | node_vector.cpp | MATCH | - | the 0-based position, else -1 |
| 155 | 0x224610 | 64 | zdb::CNodeUniverse::RemoveNode(zdb::CNode*) | node_vector.cpp | MATCH | - | the first equal slot zeroed |
| 156 | 0x224650 | 164 | zdb::CNodeUniverse::AddNode(zdb::CNode*) | node_vector.cpp | MATCH | - | +0xc locked: 0; full (size == capacity): reserve(3000) when size < 3000 (slti, = the port's capacity test there), else size + 100; insert at data + size; 1 |
| 157 | 0x224700 | 60 | zdb::CLightMapVector::Exists(zdb::CLightMap const*) | node_vector.cpp | MATCH | - | find != end |
| 184 | 0x2f96b0 | 160 | zdb::CTexHandle::SetTexture(zdb::CTexture*) | ztex_handle.cpp | MATCH | - | old +0xc texture's Release_HTEX when set; +0xc = texture; set: its +0x14 name; +0x0 freed (91) when set, zeroed, _strdup(name, 92) or 0; texture +0x2c htex count (half) + 1 |
| 185 | 0x2f9750 | 140 | zdb::CTexHandle::Destroy(zdb::CTexHandle*) | ztex_handle.cpp | MATCH | - | +0x4 count - 1 before the NULL test (quirk kept); 0: texture set: Release_HTEX == 0 deletes it (deleting dtor), +0xc zeroed; name freed (33) when set and zeroed; operator delete (implicit dtor) |
| 294 | 0x315f40 | 152 | CZWeapon::MakeWeaponEventCallbacks(unsigned int, CZProjectile*) | zwep_global.cpp | MATCH | - | each callback with m_events & events: m_func(projectile, events, m_data) |
| 295 | 0x315ff0 | 184 | CZWeapon::RemoveWeaponEventCallback(void (*)(CZProjectile*, unsigned int, void*)) | zwep_global.cpp | MATCH | - | NULL: erase(begin, end); else remove_if(m_func == func) then erase the tail (the port's erase loop leaves the same list) |
| 296 | 0x3160b0 | 68 | CZWeapon::AddWeaponEventCallback(void (*)(CZProjectile*, unsigned int, void*), unsigned int, void*) | zwep_global.cpp | MATCH | - | {func, events, data} inserted at the end |
| 158 | 0x2e32a0 | 40 | ai::MoveTo(CPnt3D const&) | seal_ailines.cpp | MATCH | - | ai_line_pos[0..2] = pos x / y / z |
| 159 | 0x2e32d0 | 48 | ai::SetLineFuncOpacity(float) | seal_ailines.cpp | MATCH | - | opacity = start (1 - t) + end t (mula / madd in the port's order), stored; tail _saturate(&opacity, 0.0, 1.0) (fl.py 0x475360 / 0x475364) |
| 160 | 0x2e3300 | 12 | ai::SetLineFuncOpacity(float, float) | seal_ailines.cpp | MATCH | - | start = $f12, end = $f13 |
| 161 | 0x2e3310 | 8 | ai::GetLineOpacity() | seal_ailines.cpp | MATCH | - | returns ai_line_opacity |
| 162 | 0x2e3320 | 20 | ai::SetLineOpacity(float) | seal_ailines.cpp | MATCH | - | opacity stored, tail _saturate(&opacity, 0.0, 1.0) (fl.py 0x475358 / 0x47535c) |
| 163 | 0x2e3340 | 52 | ai::PopLineColor() | seal_ailines.cpp | MATCH | - | erase of the first node (pop_front), no empty test |
| 1 | 0x3ca970 | 8 | hudGetTacMapPulseTrans() | hud_linemap.cpp | MATCH | - | returns g_fPulseTrans |
| 167 | 0x2e3bd0 | 24 | CHandSignal::CHandSignal() | seal_handsig.cpp | MATCH | - | words +0x8 / +0x4 / +0x0 = -1 |
