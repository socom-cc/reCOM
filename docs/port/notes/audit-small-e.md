# Audit of list small-e (2026-11-19, socom-port-audit-small-e)

296 small functions (22,404 bytes, each under 200 bytes) in 30 files: Apps/FTS (aidemo, game/headset,
hud/hud_claymoremapitem, hud/hud_mapcompass, hud/hud_teamnames, state/st_mpexit), zAI (ai_astar,
ai_main, ai_maps), zAnim (anim, zanim_cmd_tick), zFTS fts_controller, zGraph graph_graph, zIntersect
(int_main, int_material), zMPEG strfile, zNode (node_io, node_lensflare, node_world), zParticle
zparticle_instance, zSeal (seal_ik, seal_sensors), zSound (zsnd_csndsequence, zsnd_jukebox), zSystem
zsys_trc, zTwoD ztwod_messageq, zUI zui_skb, zUtil util_memcard, zVehicle veh_turret, zWeapon
zwep_ftsweapon. HEAD cd4a0470. Judged file by file in the scan's rank order, from the by-file packets.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 276 |
| DEFECT-FIXED | 19 (A 0, B 0, C 19) |
| DEVIATION-KEPT | 1 |
| UNJUDGED | 0 |

Defect rate 19 / 296 (all C).

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #148 (the user's rule: the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)).

Fixes:
- C, #145 CWorld::GarbageCollect: the children trimmed to their size first (vector copy, swap and
  dtor at 0x22f94c..0x22f964), which the port lacked.
- C, #98 CDI::Free: only m_pts (freed with "int_main.cpp", 113) and m_ptcount cleared (0x21c4b0); the
  port also cleared type, material, camera type, flags, inside, shadow and reserved (only the dtors
  call Free). #100 CDI::Allocate: the points sized from the size argument, _malloc(size << 4,
  "int_main.cpp", 100) (0x21c568), not from the 8-bit count with a __FILE__ / __LINE__ tag. #103
  DiIntersect::DiIntersect: _malloc(count << 5, "int_main.cpp", 41) (0x21c770).
- C, #181 CSndSequence::CSndSequence: m_done not set (0x2f2440: the ELF stores m_fading only).
  #176 CSndSequence::FadeOut: the inlined Stop, entry test included (0x2f1ffc), now Stop().
- C, #201 UiSetSkbPurpose (0x3a71a4) and #194 C2DMessageString::SetString (0x201108): an empty
  string through replace(0, npos, 0, '\0'), the (Ui, Ui, Ui, c) overload every replace call of the
  ELF uses (139 in ref.dis), not replace(.., "", 0) / clear(). Header edit file for CSaferStr below.
- C, #191 C2DMessage_Q::ScrollUp: the distance as a float difference (sub.s 0x200120), not an int
  difference converted.
- C, #70 CZAnimExpression::IsOperator: the five strcmp calls short-circuit (0x1b954c..).
- C, #29 CAiMaps::GetCellNameString: "" is the literal @2386 (0x1980a8), not a function-local
  static array.
- C, float compares in the ELF's form (NaN only): #51 CBlendable::MaxTrans1 (c.le.s 0x2cd65c), #74
  zAnimObjectOpacityFromToTick (c.le.s 0x1ba210), #157 Particle::Props::GetOpacity (c.lt.s 0x237934,
  c.le.s 0x237968), #158 Particle::Props::GetTexture (c.lt.s 0x237cac), #250 / #251 / #254
  CZFTSWeapon::SetRumbleLow_Power / SetRumbleLow_Time / SetRumbleHigh_Time (c.le.s 0x3159f8,
  0x315a28, 0x315a78).

Kept deviations (reason in the code):
- #148 CWorld::AddLightMap: the NULL test of CVisual::m_lightMapTexture, the recorded port deviation
  of mod-render.md / mod-znode.md (NULL outside a mission; the ELF reads +0xc through it).
- #175 CSndSequenceEntry::CSndSequenceEntry: m_instance = NULL; the ELF leaves the stack temporary's
  +0x4 unset (CreateSequence 0x2f2300 never writes sp+100), a garbage instance a pause entry's
  FadeOut / Stop would use.

ELF quirks kept (already in the code): #174 the instance released twice; #237 the kick return rate
not cleared; #106 bits 5..7 of the material flags kept; #111 the failed seek closes fd on the CD
path; #146 no bound on the four shadow textures; #20 the plan back to leg 0; #127 / #128 / #225 /
#226 a v0 no caller reads (port void / bool).

Float checks: every other compare's form agrees (c.lt.s / c.le.s / c.eq.s with the port's branch
sense in #63, #153, #174, #290..#293); sums and products in the port's order (#13, #26, #71,
#74, #112, #162, #163, #191); literals 0x3c23d70a, 0x3fc90fdb (fl.py 0x475078 / 0x47507c),
0x3f490fdb, 0x3e860a92, 0x3db2b8c2, 0x30000000, 0x3cf5c28f, 0x40b00000, 0x43fa0000, 0x41600000
equal to the port's spellings.

Header edit file (not owned by this list): `build/port/boot-audit-small-e/edits/zsys_h_safestr_replace.txt`
(zsys.h, CSaferStr::operator= with a NULL string: replace(0, npos, (size_type)0, '\0'), grade C;
CMenuState::Init 0x3795e8 and every other ELF replace call use that overload).

Leads for other lists:
- zIntersect header: CDI's Allocate(int), Free and Read are virtual in the ELF (slots +0xc, +0x10,
  +0x1c of every DI vtable, vt.py 0x471e50 / 0x471e90 / 0x471e70 / 0x471bb0); zintersect.h declares
  Free and Read non-virtual (and an extra non-virtual Allocate(size_t)). No class overrides them, so
  nothing differs today (#97, #101).
- zUI: zui_skb.cpp line 1803 (another function) also empties g_strSkbPurpose with replace(.., "", 0).
- zNode: CWorld's m_grid is a pointer in the port where DWARF embeds the CGrid at +0x670 (known,
  small-c).

What the packets lacked: the vtables of CSealCtrlAi (#166), C2DBitmapPoly (#8, #11), CDI and its
subclasses (#97, #101), CSnd (#173) and CHudBrightText (#17) for the slot names (vt.py); the
_saturate bound words (fl.py, #164); the readers of LoadConfig / SaveConfig's v0 (ref.dis, #225);
the stack slot of CreateSequence's entry temporary (ref.dis, #175); the zero words at 0x2231a8 /
0x22320c (#112, ref.dis); CSaferStr (zsys.h) and the ELF's replace overload census (#201); the
struct layouts of the zAnim command records (zanim.h, #61..#66) and CMemCard (zutil.h); the
GetCallAnimRef overloads (zanim_anim.cpp); CPlainBmp / UIVarMixin dtors (#208); CNodeVector's base
(#145); CMatrix::Transform (#112); m_lightMapTexture's earlier notes (#148). Roughly 20 functions
needed a lookup outside the packet.

Runs: default build linked (audit-small-e-default, 0 undefined, the zsys.h edit file applied through
shared.txt); one menus round trip (gate.ps1 -Only roundtrip -Missions 3 on this tree: PASS, 3 returns
to the menus, in use 18,657,916 B flat; menus, m8 loading, the soft keyboard / zAnim / jukebox / DI
code and the mission reloads ran with the fixes). Audits: independence --strict, docblocks and guard
provider exit 0.

## Verdicts

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 163 | 0x2afeb0 | 184 | CSealCtrl::UpdateViewCone() | seal_sensors.cpp | MATCH | - | m_kit.GetCurZoom (+0x520), GetHeadParams(&pos, &dir); height zoom * visrange, inv 1 / height, radius fovtan * visrange / zoom, point radius word 25.0f, pos / dir copied; scan offsets are the port's layout |
| 164 | 0x2aff70 | 112 | CSealCtrl::SetViewFOV(float) | seal_sensors.cpp | MATCH | - | _saturate bounds 0x475078 0.01 (0x3c23d70a) / 0x47507c pi/2 (0x3fc90fdb) as the port's literals; m_fov, cosf(0.5 * fov) to +0x6c, tanf(0.5 * fov) to +0x68 |
| 166 | 0x2b10f0 | 20 | CSealCtrlAi::NotifyTargetDown(CZSealBody*) | seal_sensors.cpp | MATCH | - | tail call slot +0x24 (vt.py 0x4722d0: PlayAiSound) with 18; the port's trace compiles only with tracing on |
| 161 | 0x2afd40 | 44 | CAiWepHint::GetWeaponAccuracy(CZWeapon*, float, bool) | seal_sensors.cpp | MATCH | - | NULL weapon -> 0 (beqz 0x2afd44, the ELF's own test); m_ai_params (+0x54).GetAccuracy(range) |
| 162 | 0x2afd70 | 52 | CAiWepHint::GetWeaponEffectiveRange(CZWeapon*) | seal_sensors.cpp | MATCH | - | NULL -> 0 (ELF's test); 0.5 * (max +0x5c + min +0x58), add then mul as the port |
| 165 | 0x2b10e0 | 8 | CSealCtrl::NotifyTargetDown(CZSealBody*) | seal_sensors.cpp | MATCH | - | empty |
| 167 | 0x2b1910 | 92 | CSealCtrl::OnSetTargetVisible(CTarget&, bool, zdb::DiIntersect*) | seal_sensors.cpp | MATCH | - | bit 5 of +0x24 = di ? 0 < diNonVolCount (slt, signed int) : 1; bit 2 = visible; others kept |
| 168 | 0x2b1970 | 8 | CSealCtrl::SetTarget(CTarget*) | seal_sensors.cpp | MATCH | - | empty |
| 169 | 0x2b3240 | 8 | CSealCtrlAi::OpenDiPool() | seal_sensors.cpp | MATCH | - | empty |
| 208 | 0x3a8e60 | 188 | CBmpWithNode::~CBmpWithNode() | zui_skb.cpp | MATCH | - | nothing of its own; the ELF's inlined ~CPlainBmp / ~UIVarMixin (DetachUIVar(NULL) at 0x3a8ec4) / C2D::~C2D are the port's inline ~CPlainBmp (ztwod.h 345) and ~UIVarMixin (zui.h 574); deleting part by the flag |
| 198 | 0x3a60a0 | 164 | CSoftKeyboard::GetKeyAtGridPos(int, int) const | zui_skb.cpp | MATCH | - | GetSkbKey inline on m_grid (+0x8): the same keyDefault$1791 static (init$1792 guard), y >= 0, y < size, x >= 0, x < row size, row data + x * 2 |
| 196 | 0x3a3230 | 164 | CSkbGrid::GetSkbKey(int, int) const | zui_skb.cpp | MATCH | - | function-local keyDefault zeroed once; tests y >= 0 (slt / xori), (u32)y < size (sltu), x >= 0 (bgez), (u32)x < row size; else &keyDefault; scan offsets are GCC's vector |
| 197 | 0x3a32e0 | 68 | CSkbKeyProps::SetButtonState(void (C2DButton::*)(void const*, void*)) | zui_skb.cpp | MATCH | - | pointer-to-member copied, called through __ptmf_scall on +0x14 m_button only when set (beqz 0x3a3308, the ELF's own test); the ELF passes no further arguments (a1 / a2 left over), the port's members take none |
| 204 | 0x3a78c0 | 116 | InvalidateSkbsDisplay() | zui_skb.cpp | MATCH | - | InvalidateDisplay on each of g_arrSkbs (size +0x4, data +0x8); then EnterSound, g_bmpLegend.m_node (+0xa0), KeyPress, Navigation, Negative, ScaleDown, ScaleUp zeroed in that order |
| 200 | 0x3a6bb0 | 184 | CSkbGrid::MoveToNextPos(int*, int*, @unnamed@zui_skb_cpp@::TwoDAxis::_, int (*)(int)) const | zui_skb.cpp | MATCH | - | pos = axis ? y : x (movn), *pos = step(*pos); horizontal: (u32)*y >= size returns, count row size; vertical count size; < 0 -> count - 1, !(pos < count) -> 0 |
| 199 | 0x3a6280 | 72 | CSoftKeyboard::FindKeyProps(@unnamed@zui_skb_cpp@::CSkbKey const&) | zui_skb.cpp | MATCH | - | m_keyProps (+0x2c).find(key), end header +0x30 -> NULL, else node +0x10 second |
| 195 | 0x3a3200 | 44 | CSkbKey::operator<(@unnamed@zui_skb_cpp@::CSkbKey const&) const | zui_skb.cpp | MATCH | - | lbu +0 kinds: differ -> slt; else lbu +1 values slt (zero-extended bytes, unsigned) |
| 205 | 0x3a8d10 | 152 | GetRdrArrayInt(_zrdr*, int) | zui_skb.cpp | MATCH | - | NULL array -> 0; Get inline: type 4 array, len integer of element 0 - 1, (u32)i < len -> &array[i + 1]; GetInt: type 1 integer, 2 fptosi (truncation, the port's cast), else 0 |
| 206 | 0x3a8e00 | 8 | CIntPair::Get2nd() const | zui_skb.cpp | MATCH | - | lw +0x4 returned |
| 207 | 0x3a8e10 | 8 | CIntPair::Get1st() const | zui_skb.cpp | MATCH | - | lw +0x0 returned |
| 201 | 0x3a7150 | 112 | UiSetSkbPurpose(C2DAnimCmdHdr*, float*) | zui_skb.cpp | DEFECT-FIXED | C | GetName(ZAnim+0x38 m_CurAnim, lbu +0x7); a name -> assign(name, strlen); none -> replace(0, npos, 0, '\0') (the (Ui, Ui, Ui, c) overload at 0x3a71a4) where the port called replace(0, npos, "", 0): the same empty text; returns 1 |
| 202 | 0x3a73a0 | 40 | TickSkb(float) | zui_skb.cpp | MATCH | - | Tick(dT) on g_pActiveSkb when set |
| 203 | 0x3a7510 | 60 | SkbHandleInput(CPad const&, CGameMenu*) | zui_skb.cpp | MATCH | - | HandleInput(pad, menu) when g_pActiveSkb set; returns g_pActiveSkb != NULL reloaded (movz) |
| 129 | 0x22e940 | 120 | zdb::CWorld::RegIntersectDelayed(zdb::DiIntersect*, CPnt3D const*, CPnt3D const*) | node_world.cpp | MATCH | - | NULL di -> -1; count +0x4d0 >= 256 (slti) -> -1; count + 1, m_diIntDelay[slot] (+0xd0), sh m_Type 2, tail / tip copied, slot returned; scan offsets are the port's vptr |
| 116 | 0x22c4f0 | 128 | CWind::Reset() | node_world.cpp | MATCH | - | goals 0 / 0 / 8, sb +0x67 m_TickGoal 0, azimuth / zenith 0, speed 8; offsets 0, -/+0x3f490fdb, 0, -/+0x3f490fdb, velocities 0x3e860a92 / 0x3db2b8c2, speed offset 3, -7.5, 9, 3: every word equals the port's literal |
| 126 | 0x22e880 | 108 | zdb::CWorld::RegProximityDelayed(zdb::DiIntersect*, CPnt3D const*, float) | node_world.cpp | MATCH | - | as #129 with m_Type 4, m_Tail = *pos, m_Tip.x radius ($f12), m_Tip.y / z zero; slot returned |
| 143 | 0x22f2e0 | 140 | zdb::CWorld::Update() | node_world.cpp | MATCH | - | m_Wind (+0x4d4).Tick(zVid+0x1c frameTime); vu = m_camera->m_mtxSet.m_vu; dir flag (+0x660): NormalLightMatrix(vu+0xe0, dir 0..2 at +0x5f0..), [3][3] word 1.0f, flag cleared; colour flag (+0x661): LightColorMatrix(vu+0x120, col 0..2, ambient +0x650), cleared |
| 145 | 0x22f930 | 188 | zdb::CWorld::GarbageCollect() | node_world.cpp | DEFECT-FIXED | C | the ELF first trims m_child to its size (vector copy ctor, swap, dtor at 0x22f94c..0x22f964); the port lacked it: added. Then dynamic_cast<CCell*> (RTTI 0x44fc08 / 0x44fbe0) per child, ShrinkAtomBasePtrs when not a cell |
| 146 | 0x22f9f0 | 144 | zdb::CWorld::AddShadow(zdb::CNode*) | node_world.cpp | MATCH | - | texture m_shadowTex[m_shadows.size] (+0x6bc0), new CRenderMap(node, 0, texture) (736 the ELF's size, the port's own class), appended; no bound (ELF quirk kept, noted in the code) |
| 136 | 0x22eb00 | 104 | zdb::CWorld::GetIntersects(CPnt3D const*, CPnt3D const*) | node_world.cpp | MATCH | - | m_diInt (+0xcc) tail / tip copied, m_grid.GetIntersect(m_diInt), m_diInt returned; the port's m_grid pointer for DWARF's embedded grid (+0x670) is known (small-c) |
| 137 | 0x22eb70 | 124 | zdb::CWorld::GetIntersect(CPnt3D const*, CPnt3D const*) | node_world.cpp | MATCH | - | as #136, then m_Cnt (+0x34) == 0 -> NULL, else GetNearestIntersect() |
| 134 | 0x22ea30 | 72 | zdb::CWorld::GetAltitudes(CPnt3D const*, float) | node_world.cpp | MATCH | - | m_Tail = (x, 0, z), m_grid.GetAltitude(m_diInt), m_diInt returned; height unread |
| 135 | 0x22ea80 | 120 | zdb::CWorld::GetAltitude(CPnt3D const*, float) | node_world.cpp | MATCH | - | as #134, m_Cnt == 0 -> NULL, else GetHighestAltitude(pos, height) |
| 130 | 0x22e9c0 | 52 | zdb::CWorld::diTick(float, void*) | node_world.cpp | MATCH | - | m_world's grid GetIntersectBatch(m_diIntDelay +0xd0, count +0x4d0), m_world's count zeroed, returns 0 |
| 139 | 0x22ec80 | 76 | zdb::CWorld::DeleteLandmark(zdb::CNode*) | node_world.cpp | MATCH | - | bit 3 of +0x5c tested, cleared (others kept), m_landmarks (+0x6b8c).Remove(node) |
| 140 | 0x22ecd0 | 108 | zdb::CWorld::AddLandmark(zdb::CNode*) | node_world.cpp | MATCH | - | bit 3 of +0x5c set -> RemoveFromParent, appended to m_landmarks |
| 142 | 0x22f030 | 88 | zdb::CWorld::ReleaseLandmarkList() | node_world.cpp | MATCH | - | CNode::Delete on each landmark, size zeroed (capacity kept, as clear) |
| 138 | 0x22ebf0 | 132 | zdb::CWorld::FindLandmark(char const*) | node_world.cpp | MATCH | - | strcmp(landmark +0x90 m_name, name) == 0 -> that node; else NULL |
| 141 | 0x22ed40 | 56 | zdb::CWorld::ReleaseLightList() | node_world.cpp | MATCH | - | m_lights (+0x544) erase(begin, end) |
| 147 | 0x22fa80 | 152 | zdb::CWorld::DeleteLightMap(zdb::CLightMap*) | node_world.cpp | MATCH | - | find, remove_copy from the next, erase to the end on m_lightMaps (+0x55c): std::remove + erase |
| 148 | 0x22fb20 | 132 | zdb::CWorld::AddLightMap(zdb::CLightMap*) | node_world.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: m_lightMapTexture's texture is read as is. Earlier: +0x100 m_pTex NULL and bits 0 / 1 of +0x160 clear -> SetTexture(m_lightMapTexture +0xc), appended; the port's NULL test of m_lightMapTexture is the recorded deviation of mod-render / mod-znode (reason in the code: NULL outside a mission) |
| 115 | 0x22c3c0 | 96 | SetMaterial(zdb::CNode*, int) | node_world.cpp | MATCH | - | empty m_di (+0x78) returns; each DI's +0x18 bits 10..17 = material & 0xff (mask 0xfffc03ff), the port's 8-bit m_material bitfield |
| 118 | 0x22dc50 | 108 | zdb::CWorld::RemoveDecals() | node_world.cpp | MATCH | - | count +0x6c read once, CNode::RemoveDecals on each child |
| 119 | 0x22dfa0 | 196 | zdb::CWorld::FindTextureAssetCharacter(zdb::CNode*) | node_world.cpp | MATCH | - | each set of the list at +0x6b9c: set->m_nodes (+0x8).Exists(node) -> 1; else 0 |
| 122 | 0x22e290 | 100 | zdb::CWorld::AddTextureAssetDecals(zdb::CTexHandle*) | node_world.cpp | MATCH | - | m_TextureDecals (+0x6bb4).GetHandle(handle +0xc m_texture) NULL -> appended |
| 123 | 0x22e300 | 76 | zdb::CWorld::AddTextureAssetCharacterAll(zdb::CTexHandle*) | node_world.cpp | MATCH | - | appended to m_TextureCharacterCommon (+0x6ba8) |
| 120 | 0x22e1f0 | 72 | zdb::CWorld::DeleteTextureAssetCharacter(zdb::_RenderPhase, zdb::CNode*) | node_world.cpp | MATCH | - | FindLib(phase) on CAssetMgr::m_assets, then the (CAssetLib*, CNode*) overload |
| 121 | 0x22e240 | 72 | zdb::CWorld::DeleteTextureAssetCharacter(char*, zdb::CNode*) | node_world.cpp | MATCH | - | FindLib(name), then the (CAssetLib*, CNode*) overload |
| 124 | 0x22e5a0 | 72 | zdb::CWorld::AddTextureAssetCharacter(char*, zdb::CNode*) | node_world.cpp | MATCH | - | FindLib(name), then the (CAssetLib*, CNode*) overload |
| 125 | 0x22e5f0 | 72 | zdb::CWorld::AddTextureAssetCharacter(zdb::_RenderPhase, zdb::CNode*) | node_world.cpp | MATCH | - | FindLib(phase), then the (CAssetLib*, CNode*) overload |
| 117 | 0x22d6a0 | 44 | CWind::RegisterAnimCommands() | node_world.cpp | MATCH | - | ZAnim.AddCmd("WIND", CmdParseWind, NULL, CmdTickWind, NULL) (t1 zero) |
| 127 | 0x22e8f0 | 32 | zdb::CWorld::ClearIgnoreNodeDelayed(zdb::DiIntersect*) | node_world.cpp | MATCH | - | NULL -> nothing (ELF's test), else +0x3c m_Node zeroed; the ELF's -1 / 1 has no reader (port void, noted) |
| 128 | 0x22e910 | 48 | zdb::CWorld::RegIgnoreNodeDelayed(zdb::DiIntersect*, zdb::CNode*) | node_world.cpp | MATCH | - | NULL di or node -> nothing (ELF's tests), else m_Node = node; v0 unread (port void, noted) |
| 131 | 0x22ea00 | 8 | zdb::CWorld::InitDescendantsVisuals() | node_world.cpp | MATCH | - | tail call on the grid (+0x670) |
| 132 | 0x22ea10 | 8 | zdb::CWorld::InitDescendantsDI() | node_world.cpp | MATCH | - | tail call on the grid |
| 133 | 0x22ea20 | 12 | zdb::CWorld::GetIntersectBatch(zdb::DiIntersect**, int) | node_world.cpp | MATCH | - | m_world's grid, arguments passed through |
| 144 | 0x22f920 | 16 | zdb::CWorld::ReserveChildren(int) | node_world.cpp | MATCH | - | m_child.reserve(count + size +0x6c), tail call |
| 149 | 0x22fbb0 | 16 | zdb::CWorld::GetModel(char const*) | node_world.cpp | MATCH | - | CAssetMgr::m_assets.GetModel(name), tail call |
| 150 | 0x230520 | 8 | zdb::CWorld::Uninit() | node_world.cpp | MATCH | - | empty |
| 151 | 0x230530 | 8 | zdb::CWorld::Init() | node_world.cpp | MATCH | - | empty |
| 152 | 0x230540 | 12 | zdb::CWorld::GetVersion() | node_world.cpp | MATCH | - | returns 0x10001 |
| 230 | 0x307700 | 136 | CMemCard::CMemCard() | util_memcard.cpp | MATCH | - | CIO then CMemCardIO vtables; +0x4 m_fd -1, +0x8 m_port / +0xc m_slot / +0x10 m_size 0; m_game (+0x18) and m_config (+0x1c) new CSaveManager(this) (36 bytes); m_card_port / slot left (the ELF too); the scan's names are the packet's port: labels, the offsets agree with zutil.h |
| 225 | 0x307450 | 76 | CMemCard::LoadConfig(char const*) | util_memcard.cpp | MATCH | - | m_port / m_slot = m_card_port / m_card_slot (+0x20 / +0x24 to +0x8 / +0xc); m_config->Load(name, 1); fail -> theGame+0x7c RunEventAnim("MEMCARD_ERROR", NULL); the ELF's v0 (RunEventAnim's on failure) has no reader (UILoadConfig 0x1d2d60) |
| 226 | 0x3074a0 | 84 | CMemCard::SaveConfig(char const*) | util_memcard.cpp | MATCH | - | as LoadConfig with Save(name, 1, 0, NULL); v0 unread (UISaveConfig 0x1d2d20, noted in the code) |
| 227 | 0x307500 | 28 | CMemCard::LoadGame(char const*) | util_memcard.cpp | MATCH | - | card copied in, tail call m_game->Load(name, 2) |
| 228 | 0x307520 | 36 | CMemCard::SaveGame(char const*, char*) | util_memcard.cpp | MATCH | - | card copied in, tail call m_game->Save(name, 2, 0, description) (t0 = a2) |
| 217 | 0x306a70 | 88 | CMemCardIO::Close() | util_memcard.cpp | MATCH | - | IsOpen through slot +0x10 (the port's virtual), sceMcClose(m_fd) < 0 returns, sceMcSync(0, ..), m_fd = -1 |
| 229 | 0x307690 | 100 | CMemCard::~CMemCard() | util_memcard.cpp | MATCH | - | deleting ~CSaveManager on m_game then m_config (delete; the NULL test is the dtor's); no base work; deleting part by the flag |
| 218 | 0x306c40 | 84 | CMemCard::chdir(char const*) | util_memcard.cpp | MATCH | - | sceMcChdir(m_card_port, m_card_slot, name, NULL) < 0 -> false; sync; result == 0 |
| 219 | 0x306ca0 | 80 | CMemCard::mkdir(char const*) | util_memcard.cpp | MATCH | - | sceMcMkdir(port, slot, name) < 0 -> false; sync; result == 0 |
| 220 | 0x306cf0 | 108 | CMemCard::Exists(char const*) | util_memcard.cpp | MATCH | - | sceMcGetDir(port, slot, name, 0, 1, table) < 0 -> false; sync; result > 0 (blez) |
| 221 | 0x307260 | 84 | CMemCard::GetFreeSpace() | util_memcard.cpp | MATCH | - | free = 0; sceMcGetInfo(port, slot, NULL, &free, NULL) < 0 -> 0; sync; free |
| 222 | 0x3072c0 | 72 | CMemCard::Format() | util_memcard.cpp | MATCH | - | sceMcFormat(port, slot) < 0 -> false; sync; result == 0 (the compat layer's refusal unchanged) |
| 223 | 0x307310 | 144 | CMemCard::IsFormatted() | util_memcard.cpp | MATCH | - | two tries: GetInfo(port, slot, NULL, NULL, &format) < 0 returns the last answer; sync; format != 0 ends the loop |
| 224 | 0x3073a0 | 172 | CMemCard::IsInserted() | util_memcard.cpp | MATCH | - | two tries: GetInfo(.., &type, NULL, NULL); !(result < -9) && type == 2 ends the loop; < 0 returns the last answer |
| 209 | 0x306870 | 48 | CMemCardIO::fflush() | util_memcard.cpp | MATCH | - | sceMcFlush(m_fd) >= 0 -> sceMcSync(0, &cmd, &result) |
| 210 | 0x3068a0 | 88 | CMemCardIO::fwrite(void const*, int) | util_memcard.cpp | MATCH | - | sceMcWrite(m_fd, buf, size) < 0 -> 0; sync; result >= 0 ? result : 0 |
| 211 | 0x306900 | 88 | CMemCardIO::fread(void*, int) | util_memcard.cpp | MATCH | - | sceMcRead as fwrite |
| 212 | 0x306960 | 12 | CMemCardIO::fread(int, void**) | util_memcard.cpp | MATCH | - | *buf = NULL, 0 |
| 213 | 0x306970 | 128 | CMemCardIO::fseek(int, int) | util_memcard.cpp | MATCH | - | whence 1 -> 1, 2 -> 2, else 0; sceMcSeek(m_fd, offset, whence); result as fwrite |
| 214 | 0x3069f0 | 96 | CMemCardIO::ftell() const | util_memcard.cpp | MATCH | - | sceMcSeek(m_fd, 0, 1); result as fwrite |
| 215 | 0x306a50 | 8 | CMemCardIO::GetSize() const | util_memcard.cpp | MATCH | - | lw +0x10 m_size |
| 216 | 0x306a60 | 16 | CMemCardIO::IsOpen() const | util_memcard.cpp | MATCH | - | m_fd >= 0 (slt / xori) |
| 191 | 0x200100 | 48 | C2DMessage_Q::ScrollUp() | ztwod_messageq.cpp | DEFECT-FIXED | C | m_target_top = (float)-m_YMargin; the ELF's distance is that float minus (float)m_cur_top (cvt.s.w, sub.s 0x200120), the port's an int difference converted: equal while the values are exact; now in the ELF's form; m_moveTime 0 (sw zero) |
| 193 | 0x200890 | 144 | C2DMessage_Q::LastMessage() | ztwod_messageq.cpp | MATCH | - | the list walked to its last element (no type test), its +0x94 m_text's data, else "" (0x44e810) |
| 192 | 0x200830 | 96 | C2DMessage_Q::SetBkgColor(float, float, float) | ztwod_messageq.cpp | MATCH | - | SetColor(r, g, b) on m_background1 (+0x20) then m_background2 (+0xa0) |
| 194 | 0x2010b0 | 116 | C2DMessageString::SetString(char const*) | ztwod_messageq.cpp | DEFECT-FIXED | C | C2DString::SetString(""); text -> m_text (+0x94).assign(text, strlen); NULL -> replace(0, npos, 0, '\0') (the (Ui, Ui, Ui, c) overload at 0x201108) where the port called clear(): the same empty text |
| 7 | 0x3c2fd0 | 176 | CZClaymoreMapItem::~CZClaymoreMapItem() | hud_claymoremapitem.cpp | MATCH | - | nothing of its own: ~C2DTriFan on +0x200, the inlined ~C2DBitmapPoly on m_graphic (+0x10: C2DPoly[2] at +0x50 of 208 bytes, C2D::~C2D), CZMapItem's vtable, deleting part by the flag: the port's member and base dtors |
| 9 | 0x3c33c0 | 144 | CZClaymoreMapItem::CZClaymoreMapItem(CZSealBody*, CZProjectile*) | hud_claymoremapitem.cpp | MATCH | - | CZMapItem then own vtable, C2DBitmapPoly ctor (+0x10), C2DTriFan ctor (+0x200); owner +0x4, projectile +0x8, sb +0x22c m_wasdetonated 0, +0x230 m_size word 3.0f |
| 8 | 0x3c30a0 | 20 | CZClaymoreMapItem::Draw(zdb::CCamera*) | hud_claymoremapitem.cpp | MATCH | - | m_graphic (+0x10) slot +0xc (vt.py 0x472ac0: C2DBitmapPoly::Draw) tail call; GCC binds the member's call statically, the same method |
| 100 | 0x21c530 | 84 | zdb::CDI::Allocate(int) | int_main.cpp | DEFECT-FIXED | C | bits 2..9 of the half at +0x18 (m_ptcount) = size; m_pts = _malloc(size << 4, "int_main.cpp", 100) (0x21c568): the port sized it from the 8-bit m_ptcount (the same for the counts Read passes, under 256) and tagged it with __FILE__ / __LINE__ |
| 98 | 0x21c4b0 | 92 | zdb::CDI::Free() | int_main.cpp | DEFECT-FIXED | C | _free(m_pts, "int_main.cpp", 113) when set, m_pts zeroed, m_ptcount (bits 2..9 of +0x18) zeroed, nothing else; the port also cleared type, material, camera type, flags, inside, shadow and reserved and tagged zfree's __FILE__: only the dtors call Free (int_bbox.cpp 46 / 60, here 91) |
| 103 | 0x21c750 | 152 | zdb::DiIntersect::DiIntersect(int) | int_main.cpp | DEFECT-FIXED | C | m_BufCnt, _malloc(count << 5, "int_main.cpp", 41) (0x21c770; the port tagged __FILE__ / __LINE__), m_Node / m_Cnt 0, sh m_Type 0, +0x2 bit 0 set, bit 1 clear, bit 2 set, others kept |
| 101 | 0x21c590 | 104 | zdb::CDI::~CDI() | int_main.cpp | MATCH | - | CDI's vtable, Free through slot +0x10 (CDI::Free, the port's direct call: no class overrides it, vt.py 0x471e50 / 0x471e90 / 0x471e70 / 0x471bb0); deleting part by the flag |
| 97 | 0x21c410 | 152 | zdb::CDI::Create(zdb::CSaveLoad&) | int_main.cpp | MATCH | - | GetOpenKey on sload+4; new CDIPoly (36), Read through slot +0x1c (CDI::Read in every DI vtable, the port's direct call), failure -> deleting dtor (slot +0x8, flag 1) and NULL |
| 102 | 0x21c6e0 | 104 | zdb::DiIntersect::~DiIntersect() | int_main.cpp | MATCH | - | _free(m_Intersects, "int_main.cpp", 53) when set (the ELF's test); deleting part by the flag |
| 99 | 0x21c510 | 20 | zdb::CDI::Release() | int_main.cpp | MATCH | - | +0x14 m_refcount - 1 stored and reloaded as the result |
| 94 | 0x21c2c0 | 44 | zdb::IntersectStruct::IsInside() | int_main.cpp | MATCH | - | m_poly NULL -> 0, else bit 7 of +0x1a (m_inside) as 0 / 1 |
| 95 | 0x21c2f0 | 32 | zdb::IntersectStruct::GetRegion() | int_main.cpp | MATCH | - | m_poly NULL -> 0, else +0x10 m_region |
| 96 | 0x21c310 | 40 | zdb::IntersectStruct::GetMaterial() | int_main.cpp | MATCH | - | m_poly NULL -> 0, else bits 10..17 of +0x18 (dsll32 14 / dsrl32 24) |
| 112 | 0x223180 | 176 | zdb::CNode::TransformToWorld(CPnt3D&) const | node_io.cpp | MATCH | - | from this while not NULL and +0x58 m_type != 6 (GRID), through +0x64 m_parent: the inlined VU0 Transform (count 1: x row0 + y row1 + z row2 + row3 w, the order of the port's inline CMatrix::Transform, zmath_matrix.h 50) |
| 113 | 0x224210 | 8 | zdb::CLight::_Write(zdb::CSaveLoad&) | node_io.cpp | MATCH | - | returns 0 |
| 114 | 0x231ca0 | 92 | zdb::CLensFlare::CLensFlare() | node_lensflare.cpp | MATCH | - | CNode(), own vtable (+0x60 in the ELF's layout), the vector at +0xcc empty (capacity pair 0, size / data 0: the port's member ctor), +0x58 m_type 9; the scan's offsets are GCC's vptr placement |
| 189 | 0x402e10 | 52 | TRC_PowerOffThread(void*) | zsys_trc.cpp | MATCH | - | forever: WaitSema(sema), printf("trc_hdd> power off requested\n") (GCC turns it into puts), TRC_PowerOffThread_Aux() |
| 188 | 0x402d90 | 120 | _UnPreparePowerOff(CIOPManager::RebootPhase, CIOPManager::RebootMode, void*) | zsys_trc.cpp | MATCH | - | phase (andi 0xff) != PreReboot -> 0; else 1 after: tid set, TerminateThread >= 0, DeleteThread >= 0, then tid = 0 and DeleteSema(sema) |
| 190 | 0x402f50 | 8 | TRC_PowerOffHandler(void*) | zsys_trc.cpp | MATCH | - | tail call iSignalSema(sema) |
| 160 | 0x2a4d30 | 148 | CZSealBody::TurnSetup(int) | seal_ik.cpp | MATCH | - | m_blends (+0x130)->Top()->Representative(); +0xe90 m_local_drot and +0xe80 m_twist_back zeroed; FootInSpace(rep, &m_footL +0xe74, &m_footR +0xe84, 0, 0, (lhu +0x1e & 0x40) == 0) (t0 1 / 0 on the two paths); scan offsets are the port's layout |
| 187 | 0x2f1ab0 | 184 | CSndJukebox::LoadPlaylists(char const*) | zsnd_jukebox.cpp | MATCH | - | Cleanup when m_playlists_loaded == 1; zrdr_read(name, NULL, 0); JUKEBOX, then FIGHT_MUSIC found before STEALTH_MUSIC, LoadMusicLists(stealth, 0), (fight, 1); zrdr_free when read; the port's trace compiles only with tracing on |
| 186 | 0x2f15d0 | 108 | CSndJukebox::FadeOut() | zsnd_jukebox.cpp | MATCH | - | sequence set: FadeOut unless IsFading; else sound set and not fading: FadeOut(5.5f, 0x40b00000) |
| 182 | 0x2f0fc0 | 88 | CSndJukebox::Stop() | zsnd_jukebox.cpp | MATCH | - | m_jukebox_stopped 1; sequence Stop; sound Stop, ReleaseSoundInstance, NULL; m_queue.sound 0 (sw), mode -1 (sb +0x4) |
| 183 | 0x2f1020 | 20 | CSndJukebox::Start() | zsnd_jukebox.cpp | MATCH | - | m_queue.sound 0, m_jukebox_stopped 0, mode -1 |
| 184 | 0x2f1370 | 8 | CSndJukebox::IsInFight(bool) | zsnd_jukebox.cpp | MATCH | - | sb a0 to m_isinfight |
| 185 | 0x2f15c0 | 16 | CSndJukebox::ClearQueue() | zsnd_jukebox.cpp | MATCH | - | m_queue.sound 0, mode -1 |
| 181 | 0x2f2410 | 68 | CSndSequence::CSndSequence() | zsnd_csndsequence.cpp | DEFECT-FIXED | C | vector empty (pair, +0x4 / +0x8 zero), +0xc m_current -1, +0x10 m_name 0, sb +0x15 m_fading 0; the ELF leaves +0x14 m_done unset (Play sets it before any Tick): the port's initialisation removed |
| 176 | 0x2f1fc0 | 120 | CSndSequence::FadeOut() | zsnd_csndsequence.cpp | DEFECT-FIXED | C | an entry playing: its FadeOut, m_fading 1; else the inlined Stop (its entry test, m_current -1, m_done 1, m_fading 0 at 0x2f1ffc..0x2f2024): the port wrote Stop's stores without its test (unreachable there); now Stop() |
| 178 | 0x2f2080 | 84 | CSndSequence::Stop() | zsnd_csndsequence.cpp | MATCH | - | the current entry's Stop when m_current != -1; m_current -1, sb m_done 1, sb m_fading 0 (GCC merges the two bytes) |
| 179 | 0x2f20e0 | 20 | CSndSequence::Play() | zsnd_csndsequence.cpp | MATCH | - | m_current -1, m_done 0, m_fading 0 |
| 177 | 0x2f2040 | 52 | CSndSequence::IsFading() | zsnd_csndsequence.cpp | MATCH | - | m_current == -1 -> 0, else entries[m_current] (16 bytes each).IsFading() |
| 175 | 0x2f1fa0 | 20 | CSndSequenceEntry::CSndSequenceEntry(CSnd*, float) | zsnd_csndsequence.cpp | DEVIATION-KEPT | - | m_sound +0x0, m_pausetime +0x8, m_timer +0xc zero as the ELF; the port's m_instance = NULL is kept (reason in the code): the ELF leaves the stack temporary's +0x4 unset (CreateSequence 0x2f2300 never writes sp+100), a garbage instance a pause entry's FadeOut / Stop would use |
| 173 | 0x2f1ea0 | 72 | CSndSequenceEntry::Play() | zsnd_csndsequence.cpp | MATCH | - | m_sound set: slot +0x1c (vt.py 0x472a20: PlaySound(bool, CSndInstance*, Ui)) with false, NULL, 255, result to m_instance |
| 174 | 0x2f1ef0 | 168 | CSndSequenceEntry::Tick(float) | zsnd_csndsequence.cpp | MATCH | - | a sound entry: playing -> 0; else released twice (ELF quirk kept), NULL, 1; a pause: m_timer += dT, timer <= pause (c.le.s, the port's form) -> 0, else timer 0 and 1 |
| 170 | 0x2f1df0 | 40 | CSndSequenceEntry::IsFading() | zsnd_csndsequence.cpp | MATCH | - | m_instance NULL -> 0, else its IsFading() |
| 171 | 0x2f1e20 | 64 | CSndSequenceEntry::FadeOut() | zsnd_csndsequence.cpp | MATCH | - | instance: FadeOut(5.5f); else m_timer = m_pausetime |
| 172 | 0x2f1e60 | 64 | CSndSequenceEntry::Stop() | zsnd_csndsequence.cpp | MATCH | - | instance: Stop, ReleaseSoundInstance; m_instance NULL either way |
| 180 | 0x2f2380 | 132 | CSndSequence::~CSndSequence() | zsnd_csndsequence.cpp | MATCH | - | _free(m_name, "zsnd_csndsequence.cpp", 29) when set, m_name 0 (the ELF twice), the vector's dtor, deleting part by the flag |
| 43 | 0x2c7e70 | 52 | CAnimsByFP::Clear() | anim.cpp | MATCH | - | 300 groups of m_animgroups: the four halves -1 (GCC merges the stores) |
| 53 | 0x2cd6e0 | 84 | CBlendable::Clear() | anim.cpp | MATCH | - | memset(this, 0, 48), then m_animtype (+0x8 of each 12-byte entry) -1 four times |
| 38 | 0x2c08f0 | 128 | AnimSet::SetMaxMotion() | anim.cpp | MATCH | - | MaxTrans1 of +0x64..+0x80 into +0x0..+0x1c in order (rt from strafe L, left from strafe R, as the ELF) |
| 51 | 0x2cd640 | 72 | CBlendable::MaxTrans1() | anim.cpp | DEFECT-FIXED | C | max 0; entries until m_animtype -1 (lh +0x8); the ELF takes trans1 (+0x4) when !(trans1 <= max) (c.le.s 0x2cd65c), the port when trans1 > max: NaN only; written in the ELF's form |
| 47 | 0x2cd240 | 116 | FindAnimType(char const*) | anim.cpp | MATCH | - | NULL -> -1; std::string(name), newNamesMap.find, string dtor, end -> -1, else the value read as a half (lh +0x10: the AnimType cast) |
| 44 | 0x2c7eb0 | 64 | AnimSet::BaseAnim(AnimType) | anim.cpp | MATCH | - | type (s16) < 0 -> -1; < m_basetypes size (+0x4c) -> data (+0x50)[type] (lh), else -1 |
| 46 | 0x2cca90 | 64 | AnimSet::AnimId(AnimType) const | anim.cpp | MATCH | - | as BaseAnim on m_animIDs (+0x40 / +0x44) |
| 49 | 0x2cd580 | 88 | AnimSet::CloseAll() | anim.cpp | MATCH | - | Close on each of AnimSet::list (data +0x8, size +0x4 reloaded) |
| 50 | 0x2cd5f0 | 80 | CBlendable::Contains(AnimType) | anim.cpp | MATCH | - | four entries: -1 -> false, == type -> true; else false |
| 52 | 0x2cd690 | 76 | CBlendable::AddBlendable(float, float, AnimType) | anim.cpp | MATCH | - | four entries: == type returns; -1 -> trans0, trans1, type stored, returns |
| 39 | 0x2c7d80 | 40 | CAnimsByFP::SetPistolAnim(AnimType, AnimType) | anim.cpp | MATCH | - | group [(s16)rifle] (8 bytes): +0 rifle, +2 pistol; no range check |
| 40 | 0x2c7db0 | 64 | CAnimsByFP::PistolFPAnim(AnimType) const | anim.cpp | MATCH | - | 0 <= type < 300 -> lh +0x6 of the group, else -1 |
| 41 | 0x2c7df0 | 64 | CAnimsByFP::RifleFPAnim(AnimType) const | anim.cpp | MATCH | - | as #40 with +0x4 |
| 42 | 0x2c7e30 | 64 | CAnimsByFP::PistolAnim(AnimType) const | anim.cpp | MATCH | - | as #40 with +0x2 |
| 45 | 0x2cc7c0 | 24 | CAnimAuxData::Get(unsigned int) | anim.cpp | MATCH | - | list data (+0x8)[anim], no range check |
| 48 | 0x2cd2c0 | 8 | GetAnimTypeMax() | anim.cpp | MATCH | - | numAnimTypes |
| 6 | 0x2f36b0 | 128 | Headset::ftsGetHeadset() | headset.cpp | MATCH | - | theHeadsetState 1 or 2 -> theHeadset; else new Headset (60) when none, state 2, theHeadset +0x9 m_state 3, returned; scan offsets are the port's layout |
| 5 | 0x2f3600 | 176 | Headset::Headset() | headset.cpp | MATCH | - | the two vectors (+0x18, +0x24), m_entries (+0x34) new[] of 20 x 12, 0..19 appended to m_free (+0x24), +0x30 / +0x38 zero, sb +0xa m_stop 0 |
| 2 | 0x2f2ff0 | 68 | Headset::Tick(float) | headset.cpp | MATCH | - | theHeadsetState 2 -> DisconnectedTick(dT), 1 -> ConnectedTick(dT) |
| 3 | 0x2f3040 | 120 | Headset::SoundSysCallback(unsigned int) | headset.cpp | MATCH | - | m_state 0: result 0 -> theHeadsetState 2, m_state 4, else 1; m_state 2: result 0 -> 3 and m_stop 0, else 1; 1 / 3 / others nothing |
| 4 | 0x2f30c0 | 44 | Headset::StaticSoundSysCallback(unsigned int, unsigned long) | headset.cpp | MATCH | - | user as a 32-bit value != 0 -> SoundSysCallback(result) on it |
| 77 | 0x1bfce0 | 136 | zAnimMessageTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | GetName(lbu +0x4); any of +0x5 / +0x6 / +0x7 set -> theMission+0x100 Add_Message(text, r, g, b) (a2 / a3 / t0), else Add_Message(text, 0); returns 1; the trace compiles only with tracing on |
| 78 | 0x1bfd70 | 24 | zAnimTimerTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | +0x4 int to float (cvt.s.w) into m_winlosstimer (theMission+0x68; the port's layout puts it at +0x6c, its own readers agree), 1 |
| 76 | 0x1bd510 | 124 | zAnimObjectActiveStateTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | GetNode(lhu +0x6, false); set: SetActive (slot +0x34, the port's virtual) with lhu +0x4 == 1; 1 |
| 69 | 0x1b8e70 | 172 | zAnimGoToEndIf(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | CmdNext until !CmdValid, or a command whose data_type (lhu +0) is ZAnim+0x60 m_cmd_endif's and nest level (lbu +4) is m_CurSeq +0x7's (that level decremented); 1 |
| 57 | 0x1b80c0 | 120 | zAnimInvalidateAnimTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | index (lbu +4) 0: bit 0 of m_CurAnim +0x2c set; else GetCallAnimRef(int): ref and base_anim -> its bit 0 set; 1 |
| 72 | 0x1b9830 | 116 | zAnimObjectDeleteChildTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | parent GetNode(lbu +6), child GetNode(lbu +7); both -> parent's DeleteChild (slot +0x1c, virtual in znode.h 302); 1 |
| 70 | 0x1b9530 | 144 | CZAnimExpression::IsOperator(char const*) | zanim_cmd_tick.cpp | DEFECT-FIXED | C | strcmp with "!", "&&", "||", "(", ")" in turn, the first match returning 1 (beqz after each); the port ran all five then tested: the same answer; now short-circuit |
| 71 | 0x1b96c0 | 136 | zAnimWaitBegin(_zanim_cmd_hdr*) | zanim_cmd_tick.cpp | MATCH | - | flags (lhu +4) & 0x10: sh +6 0; & 0x20: base 2 / 1 (movz), value[0] (+8) = value[base] + value[base + 1] * (2^-31 (0x30000000) * rand()), the port's order |
| 74 | 0x1ba1c0 | 192 | zAnimObjectOpacityFromToTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | DEFECT-FIXED | C | no node -> 1; done = !(*dT + cmd_timer <= duration) (c.le.s 0x1ba210), the port's duration < sum differed for NaN only: written in the ELF's form; done: *dT -= duration - timer, opacity = to (+0xc); else *dT 0, opacity += rate (+0x10) * step |
| 73 | 0x1b9b10 | 104 | zAnimMultiObjectMotionScriptBegin(_zanim_cmd_hdr*) | zanim_cmd_tick.cpp | MATCH | - | NULL or count (lhu +4) 0 returns; each 60-byte entry at +8: +0x10, +0xc, +0x38 zeroed (the entry's NULL test is the ELF's) |
| 75 | 0x1ba280 | 68 | zAnimObjectOpacityFromToBegin(_zanim_cmd_hdr*) | zanim_cmd_tick.cpp | MATCH | - | GetNode(lhu +4); set -> +0x9c m_Opacity = from (+0x8) |
| 59 | 0x1b81d0 | 164 | zAnimPauseAnimTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | index 0: m_CurAnim Pause; else ref: executing set -> Pause when Running; else base set and Running -> Pause; 1 |
| 58 | 0x1b8140 | 140 | zAnimResumeAnimTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | ref: executing set -> Resume when Running; else base set and Running -> Resume; 1 |
| 60 | 0x1b8280 | 140 | zAnimStopAnimTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | ref: executing set -> Stop when Running, executing NULL; else base Running -> Stop; 1 |
| 61 | 0x1b8310 | 104 | zAnimCallAnimTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | lhu +4 & 0x80 clear -> 1; GetCallAnimRef(lbu +7, lbu +6); ref, executing and Running -> 0, else 1 |
| 63 | 0x1b8730 | 84 | zAnimRandomWeightTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | 2^-31 (0x30000000, the port's 4.656613e-10f) * (float)rand() <= weight (+0x4) (c.le.s) |
| 64 | 0x1b8790 | 164 | zAnimLODTestTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | lod ZAnim+0x48 as an unsigned byte against lbu +5: flag 1 ==, 2 <, 4 <=, 8 >, 0x10 >=, else 0 |
| 65 | 0x1b8c00 | 76 | zAnimNodeRenderedTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | GetNode(lhu +4, false) set and Rendered() |
| 66 | 0x1b8c50 | 140 | zAnimNodeActiveTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | GetNode(lhu +6); arg (lhu +4) 1: bit 0 of +0x5c set; 2: clear; else 0 |
| 67 | 0x1b8db0 | 40 | zAnimEndWhileTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | CmdSet(lh +6), 0 |
| 68 | 0x1b8e50 | 28 | zAnimEndIfTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | m_CurSeq +0x7 m_IF_NestLevel - 1 (byte), 1 |
| 55 | 0x1b8040 | 56 | zAnimStopSequenceTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | StopSequence(GetName(lbu +4)), 1 |
| 56 | 0x1b8080 | 56 | zAnimCallSequenceTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | ActivateSequence(GetName(lbu +4)), 1 |
| 54 | 0x1b7c80 | 8 | zAnimDebugTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | returns 1 |
| 62 | 0x1b8720 | 8 | zAnimFailTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | returns 0 |
| 79 | 0x1bfe80 | 8 | zAnimQuadAlignTick(_zanim_cmd_hdr*, float*) | zanim_cmd_tick.cpp | MATCH | - | returns 1 |
| 296 | 0x315e90 | 172 | CZFTSWeapon::CZFTSWeapon() | zwep_ftsweapon.cpp | MATCH | - | CZWeapon(), own vtable, three CTargetMods (76 bytes from +0xb0), m_zoommode (+0x1c0) empty; sb +0x194 / +0x19c 0, times / power 0, burst counts 0xffffff, scalars 1.0f, slope 0; the scan's S4f are the port's float stores of the same words |
| 238 | 0x315800 | 48 | CZFTSWeapon::TargetMods(int) | zwep_ftsweapon.cpp | MATCH | - | stance >= 3 (slti) -> 0, this + 0xb0 + stance * 76 (no lower bound, as the port) |
| 242 | 0x315880 | 60 | CZFTSWeapon::IsGrenadeLauncherWeapon() | zwep_ftsweapon.cpp | MATCH | - | lbu +0x60 m_ID in 52, 61, 142, 143 |
| 243 | 0x3158c0 | 40 | CZFTSWeapon::IsM203Weapon() | zwep_ftsweapon.cpp | MATCH | - | lbu +0x60 m_ID 52 or 61 |
| 236 | 0x315760 | 56 | CZFTSWeapon::GetZoomRange(unsigned int) | zwep_ftsweapon.cpp | MATCH | - | size (+0x1c4) 0 or level >= size (sltu) -> 500.0f (0x43fa0000), else data (+0x1c8)[level] |
| 237 | 0x3157a0 | 88 | CTargetMods::CTargetMods() | zwep_ftsweapon.cpp | MATCH | - | +0x0..+0x38 and +0x40 / +0x44 zero, +0x3c kick return rate left (ELF quirk kept, noted), +0x48 wiggle report 0x3cf5c28f (0.03f) |
| 245 | 0x315900 | 76 | CZFTSWeapon::AddZoommode(float) | zwep_ftsweapon.cpp | MATCH | - | insert(end, 1, range) on m_zoommode |
| 246 | 0x315950 | 112 | CZFTSWeapon::GetZoommode(int) | zwep_ftsweapon.cpp | MATCH | - | size < (u32)index or index < 0 -> 0; index - 1 < 0 -> 0; else data[index - 1] (the branch at 0x3159a0 unreachable) |
| 281 | 0x315c40 | 44 | CTargetMods::SetTarget_DilateUponMovement(float) | zwep_ftsweapon.cpp | MATCH | - | +0x24 = v, +0x28 = sqrtf(v) |
| 290 | 0x315cf0 | 84 | CZFTSWeapon::AccuracyScalar_Max(float) | zwep_ftsweapon.cpp | MATCH | - | +0x1b4 = scalar; span (float)(max +0x1ac - min +0x1a8); 0 == span (c.eq.s) -> slope 0, else (max - min scalar) / span |
| 291 | 0x315d50 | 84 | CZFTSWeapon::AccuracyScalar_Min(float) | zwep_ftsweapon.cpp | MATCH | - | +0x1b0 = scalar, slope as #290 |
| 292 | 0x315db0 | 84 | CZFTSWeapon::AccuracyBurstCnt_Max(int) | zwep_ftsweapon.cpp | MATCH | - | +0x1ac = count, slope as #290 |
| 293 | 0x315e10 | 84 | CZFTSWeapon::AccuracyBurstCnt_Min(int) | zwep_ftsweapon.cpp | MATCH | - | +0x1a8 = count, slope as #290 |
| 241 | 0x315850 | 40 | CZFTSWeapon::IsGrenadeLauncherAmmo() | zwep_ftsweapon.cpp | MATCH | - | GetIDType() (andi 0xff) == 0xaa EQUIP_LAUNCHED_GRENADE |
| 244 | 0x3158f0 | 16 | CZFTSWeapon::ResolveFTSDamage(float) | zwep_ftsweapon.cpp | MATCH | - | 14.0f * damage (mul.s 14, f12) |
| 250 | 0x3159f0 | 44 | CZFTSWeapon::SetRumbleLow_Power(float) | zwep_ftsweapon.cpp | DEFECT-FIXED | C | +0x1a4 = power; enable (+0x19c) = !(power <= 0) (c.le.s 0x3159f8), the port's power > 0 differed for NaN only; written in the ELF's form |
| 251 | 0x315a20 | 44 | CZFTSWeapon::SetRumbleLow_Time(float) | zwep_ftsweapon.cpp | DEFECT-FIXED | C | +0x1a0 = time; enable (+0x19c) = !(time <= 0) (c.le.s 0x315a28); NaN only, as #250 |
| 254 | 0x315a70 | 44 | CZFTSWeapon::SetRumbleHigh_Time(float) | zwep_ftsweapon.cpp | DEFECT-FIXED | C | +0x198 = time; enable (+0x194) = !(time <= 0) (c.le.s 0x315a78); NaN only, as #250 |
| 289 | 0x315ce0 | 8 | CZFTSWeapon::Recoil() | zwep_ftsweapon.cpp | MATCH | - | empty |
| 239 | 0x315830 | 8 | CTargetMods::SetWiggleReport(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x48 |
| 240 | 0x315840 | 8 | CTargetMods::GetWiggleReport() | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x48 returned in $f0 |
| 247 | 0x3159c0 | 8 | CZFTSWeapon::GetRumbleLow_Power() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x1a4 returned in $f0 |
| 248 | 0x3159d0 | 8 | CZFTSWeapon::GetRumbleLow_Time() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x1a0 returned in $f0 |
| 249 | 0x3159e0 | 8 | CZFTSWeapon::GetRumbleLow_Enable() const | zwep_ftsweapon.cpp | MATCH | - | lbu +0x19c returned (bool byte) |
| 252 | 0x315a50 | 8 | CZFTSWeapon::GetRumbleHigh_Time() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x198 returned in $f0 |
| 253 | 0x315a60 | 8 | CZFTSWeapon::GetRumbleHigh_Enable() const | zwep_ftsweapon.cpp | MATCH | - | lbu +0x194 returned (bool byte) |
| 255 | 0x315aa0 | 8 | CTargetMods::GetFireRifle_KickRandomDist() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x44 returned in $f0 |
| 256 | 0x315ab0 | 8 | CTargetMods::GetFireRifle_KickBaseDist() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x40 returned in $f0 |
| 257 | 0x315ac0 | 8 | CTargetMods::GetFireRifle_KickReturnRate() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x3c returned in $f0 |
| 258 | 0x315ad0 | 8 | CTargetMods::GetFireRifle_KickRate() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x38 returned in $f0 |
| 259 | 0x315ae0 | 8 | CTargetMods::SetFireRifle_KickRandomDist(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x44 |
| 260 | 0x315af0 | 8 | CTargetMods::SetFireRifle_KickBaseDist(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x40 |
| 261 | 0x315b00 | 8 | CTargetMods::SetFireRifle_KickReturnRate(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x3c |
| 262 | 0x315b10 | 8 | CTargetMods::SetFireRifle_KickRate(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x38 |
| 263 | 0x315b20 | 8 | CTargetMods::GetSniper_DecayRate() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x1c returned in $f0 |
| 264 | 0x315b30 | 8 | CTargetMods::SetSniper_DecayRate(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x1c |
| 265 | 0x315b40 | 8 | CTargetMods::GetSniper_DistLimit_PosY() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x18 returned in $f0 |
| 266 | 0x315b50 | 8 | CTargetMods::GetSniper_DistLimit_PosX() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x14 returned in $f0 |
| 267 | 0x315b60 | 8 | CTargetMods::SetSniper_DistLimit_PosY(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x18 |
| 268 | 0x315b70 | 8 | CTargetMods::SetSniper_DistLimit_PosX(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x14 |
| 269 | 0x315b80 | 8 | CTargetMods::GetSniper_DistPPFrame_PosY() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x10 returned in $f0 |
| 270 | 0x315b90 | 8 | CTargetMods::GetSniper_DistPPFrame_PosX() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0xc returned in $f0 |
| 271 | 0x315ba0 | 8 | CTargetMods::SetSniper_DistPPFrame_PosY(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x10 |
| 272 | 0x315bb0 | 8 | CTargetMods::SetSniper_DistPPFrame_PosX(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0xc |
| 273 | 0x315bc0 | 8 | CTargetMods::GetTarget_Max() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x34 returned in $f0 |
| 274 | 0x315bd0 | 8 | CTargetMods::GetTarget_Min() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x30 returned in $f0 |
| 275 | 0x315be0 | 8 | CTargetMods::GetTarget_Constrict() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x2c returned in $f0 |
| 276 | 0x315bf0 | 8 | CTargetMods::GetTarget_DilateUponMovementSqrt() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x28 returned in $f0 |
| 277 | 0x315c00 | 8 | CTargetMods::GetTarget_DilateUponMovement() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x24 returned in $f0 |
| 278 | 0x315c10 | 8 | CTargetMods::SetTarget_Max(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x34 |
| 279 | 0x315c20 | 8 | CTargetMods::SetTarget_Min(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x30 |
| 280 | 0x315c30 | 8 | CTargetMods::SetTarget_Constrict(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x2c |
| 282 | 0x315c70 | 8 | CTargetMods::SetTarget_DilateUponFire(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x20 |
| 283 | 0x315c80 | 8 | CTargetMods::GetReticuleKnock_Max() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x8 returned in $f0 |
| 284 | 0x315c90 | 8 | CTargetMods::GetReticuleKnock_Return() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x4 returned in $f0 |
| 285 | 0x315ca0 | 8 | CTargetMods::GetReticuleKnock() const | zwep_ftsweapon.cpp | MATCH | - | lwc1 +0x0 returned in $f0 |
| 286 | 0x315cb0 | 8 | CTargetMods::SetReticuleKnock_Max(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x8 |
| 287 | 0x315cc0 | 8 | CTargetMods::SetReticuleKnock_Return(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x4 |
| 288 | 0x315cd0 | 8 | CTargetMods::SetReticuleKnock(float) | zwep_ftsweapon.cpp | MATCH | - | swc1 $f12 to +0x0 |
| 294 | 0x315e70 | 8 | CZFTSWeapon::AccuracyBurstCnt_Max() const | zwep_ftsweapon.cpp | MATCH | - | lw +0x1ac returned |
| 295 | 0x315e80 | 8 | CZFTSWeapon::AccuracyBurstCnt_Min() const | zwep_ftsweapon.cpp | MATCH | - | lw +0x1a8 returned |
| 155 | 0x236e70 | 164 | Particle::Instance::~Instance() | zparticle_instance.cpp | MATCH | - | own vtable, the inlined Expire (Props DecRefCount(1) and NULL, ReleaseInstance(node) and NULL, the source's +0x12c count - 1 and NULL): the port's Expire(); deleting part by the flag |
| 156 | 0x237130 | 184 | Particle::Render() | zparticle_instance.cpp | MATCH | - | numParticles 0; view = thePipe+0x628 m_camera + 0x2c0 (m_mtxSet); Render(view) through slot +0xc on each of Instance::list |
| 159 | 0x237d10 | 148 | Particle::Props::DecRefCount(int) | zparticle_instance.cpp | MATCH | - | m_refCount -= count, reloaded; not > 0 -> delete this (the three sequence vectors' dtors at +0x1c / +0x10 / +0x4: ~Props) |
| 158 | 0x237c80 | 140 | Particle::Props::GetTexture(float, zdb::CTexHandle*&) const | zparticle_instance.cpp | DEFECT-FIXED | C | empty -> NULL; the walk stops at the first entry with t < fraction (c.lt.s 0x237cac), the port at !(fraction <= t): NaN only, written in the ELF's form; index i - 1 (count - 1 past the end), < 0 -> 0, clamped below count; entry +4 data |
| 157 | 0x237930 | 136 | Particle::Props::GetOpacity(float) const | zparticle_instance.cpp | DEFECT-FIXED | C | 0 when !(depth < farFade2) (c.lt.s 0x237934; the port's farFade2 <= depth) or depth <= nearFade1; far fade invFarFade * (farFade2 - depth) when !(depth <= farFade1) (c.le.s 0x237968; the port's farFade1 < depth); near fade when depth < nearFade2; else 1: NaN only, written in the ELF's forms |
| 153 | 0x236750 | 72 | Particle::Destruction_Instance::Render(CMatrix const&) | zparticle_instance.cpp | MATCH | - | age (+0xc) < lifespan (+0x64) (c.lt.s) and node (+0x44) -> SetPosition(pos +0x20 / +0x24 / +0x28) |
| 154 | 0x236e00 | 108 | Particle::Instance::Expire() | zparticle_instance.cpp | MATCH | - | Props DecRefCount(1), NULL; ReleaseInstance(node), NULL; source +0x12c count - 1, NULL (each only when set, the ELF's tests) |
| 92 | 0x20f1f0 | 168 | CGraph::Create(char const*) | graph_graph.cpp | MATCH | - | new (28) and the inlined ctor (#91): the port's new CGraph(name) |
| 91 | 0x20ef20 | 152 | CGraph::CGraph(char const*) | graph_graph.cpp | MATCH | - | m_name 0, the two lists (+0x4, +0x10), the dead _free(m_name, "graph_graph.cpp", 61), 0, name ? _strdup(name, "graph_graph.cpp", 62) : 0 |
| 88 | 0x20e8b0 | 168 | CGraph::GetNodeByNodeEx(void const*) | graph_graph.cpp | MATCH | - | first node of m_nodes (+0x4) whose +0xc m_nodeEx is the argument, else NULL |
| 89 | 0x20e960 | 164 | CGraph::GetNodeByIndex(unsigned int) | graph_graph.cpp | MATCH | - | index tested and decremented before the end test, then ++; the list header (+0x8) -> NULL, else the node |
| 90 | 0x20eca0 | 108 | CGraph::CreateNode(char const*) | graph_graph.cpp | MATCH | - | new CGNode(name) (36), inserted at the end of m_nodes, returned |
| 93 | 0x20f4b0 | 160 | CGraph::Create(CFileIO&, void (*)(CGraph*, CGNode*, bool, unsigned int&, void*), void (*)(CGraph*, CGEdge*, bool, unsigned int&, void*), void*) | graph_graph.cpp | MATCH | - | new CGraph(NULL); Read(io, fixupNode, fixupEdge, user) (t0 user); failure -> deleting ~CGraph (flag 1) and NULL |
| 234 | 0x37c250 | 112 | CTurret::LoadTurrets() | veh_turret.cpp | MATCH | - | ScanForTurretDefinitionHookups(landmark, true) for each of m_world's m_landmarks (+0x6b8c), then (m_world, true); the trace compiles only with tracing on |
| 231 | 0x37a2a0 | 192 | CTurret::SetTarget(CTarget*) | veh_turret.cpp | MATCH | - | target set and its +0x0 m_ent == m_target's entity (+0x170) -> m_target.UpdateTarget(target, 1.0f); else the old entity, when set and alive (bit 3 of +0xdd), looked up in m_targets (+0xcc, result unused), m_target.SetTarget(target, 1.0f) |
| 235 | 0x37cca0 | 68 | CTurretDef::~CTurretDef() | veh_turret.cpp | MATCH | - | nothing of its own; deleting part by the flag |
| 232 | 0x37b1d0 | 8 | CTurret::ComputeNextPosition(float) | veh_turret.cpp | MATCH | - | empty |
| 233 | 0x37b1e0 | 8 | CTurret::PostTick(float) | veh_turret.cpp | MATCH | - | empty |
| 11 | 0x3cbc00 | 20 | MapCompass::SetTrans(float) | hud_mapcompass.cpp | MATCH | - | m_poly (+0x240) slot +0x20 (vt.py 0x472ac0: C2DBitmapPoly::SetTrans) tail call; GCC binds the member's call statically, the same method |
| 13 | 0x3cbc60 | 136 | MapCompass::SetPos(float, float, float, float) | hud_mapcompass.cpp | MATCH | - | four corners stored, centres (a + b) / 2.0f (div.s), top / bottom cy + scale * (y - cy); Load(topx, top, topx, bottom, botx, bottom, botx, top, m_newcompasstex) ($f12..$f19, a1) tail call |
| 10 | 0x3cbb90 | 100 | MapCompass::Draw(zdb::CCamera*) | hud_mapcompass.cpp | MATCH | - | theHUD->IsOn(): Draw (slot +0xc) on m_poly (+0x240) then m_anchor_head (+0x430), the members' own methods |
| 14 | 0x3cbcf0 | 64 | MapCompass::Off() | hud_mapcompass.cpp | MATCH | - | slot +0x18 (C2D::Off) on m_poly then m_anchor_head |
| 15 | 0x3cbd30 | 64 | MapCompass::On() | hud_mapcompass.cpp | MATCH | - | slot +0x1c (C2D::On) on m_poly then m_anchor_head |
| 12 | 0x3cbc20 | 64 | MapCompass::SetTexture(zdb::CTexture*) | hud_mapcompass.cpp | MATCH | - | +0x4 = texture; widths from lhu +0x0 / +0x2 (cvt.s.w) or 0 without a texture, to +0x218 / +0x21c |
| 16 | 0x3cbd70 | 8 | MapCompass::SetScale(float) | hud_mapcompass.cpp | MATCH | - | swc1 to +0x0 m_scale |
| 83 | 0x20a480 | 156 | CCtrlrConfigs::GetPitchStickPosDilated(CPad const&) | fts_controller.cpp | MATCH | - | config +0x9 m_pitchAimMode set and the AimMode button (+0xb; 16 = unmapped -> KEY_UP; pad +0x13 state, lb) not KEY_DOWN -> 0; else StickAxis(+0x6: 2 right +0xf4, 1 left +0xec, else 0) |
| 84 | 0x20a520 | 164 | CCtrlrConfigs::GetFwdBackStickPos(CPad const&) | fts_controller.cpp | MATCH | - | +0x8 m_moveAimOff set and AimMode KEY_DOWN -> 0; else StickAxis(+0x4: right +0xe0, left +0xd8) |
| 85 | 0x20a5d0 | 156 | CCtrlrConfigs::GetFireButtonPressure(CPad const&) | fts_controller.cpp | MATCH | - | Fire (+0xc) R1 (10) -> m_InData[17] (+0x99), CROSS (9) -> [14] (+0x96), as unsigned bytes to float (the ELF's unsigned conversion), else 0 |
| 86 | 0x20a670 | 24 | CCtrlrConfigs::IsJumpAndActionShared() | fts_controller.cpp | MATCH | - | lbu +0xa (Action) == lbu +0xf (Jump) |
| 87 | 0x20a690 | 48 | CCtrlrConfigs::GetButtonState(PadBtnFunc::_, CPad const&) | fts_controller.cpp | MATCH | - | button +0xa + func; 16 -> KEY_UP, else pad state +0x13 + button |
| 82 | 0x20a430 | 68 | CCtrlrConfigs::GetRotateStickPosDilated(CPad const&) | fts_controller.cpp | MATCH | - | -(StickAxis(+0x7: 2 right +0xf0, 1 left +0xe8, else 0)) (neg.s on every path) |
| 80 | 0x209a70 | 56 | CCtrlrConfigs::SetButtonState(CPad*, PadBtnFunc::_, KEY_STATE) | fts_controller.cpp | MATCH | - | button +0xa + func; not 16 -> pad->SetButtonState(button, state) |
| 81 | 0x209ab0 | 140 | CCtrlrConfigs::SelectConfig(char const*) | fts_controller.cpp | MATCH | - | the first of g_vecConfigs (size +0x4 reloaded, data +0x8) whose m_name strcasecmp-matches becomes g_pCurrentConfig; none: unchanged |
| 17 | 0x3d8940 | 184 | CTeamNames::Clear() | hud_teamnames.cpp | MATCH | - | four rows: slot +0x78 (vt.py 0x4741a0: C2DString::ClearAndWipe) on m_teamname[i] (+0x8c, 136 each) then m_order[i] (+0x2ac); g_strAlphaBracket / g_strBravoBracket SetString(NULL); the child list erased begin..end; m_ally kept (ELF) |
| 106 | 0x21f350 | 192 | CMaterialEx::CMaterialEx() | int_material.cpp | MATCH | - | name / decal 0, opacity 1.0f, penetration / ricochet / elasticity 0, stealth factor 0.5f (+0x30), foot step offset 0; bits 0, 1, 3, 2, 4 of +0x38 cleared in that order (5..7 kept, quirk noted); weapon anim and the four sounds 0, impact radius 1.0f (+0x2c) |
| 105 | 0x21f230 | 116 | CMaterialExArray::ResolveDecalMaterialIndex(char const*, int) | int_material.cpp | MATCH | - | NULL -> 0; m_materialex_map.find(std::string(name)), end -> 0, else the value (+0x10) |
| 104 | 0x21ed50 | 132 | CMaterialExArray::GetWeaponAnimMaterialEx(unsigned int) | int_material.cpp | MATCH | - | index >= size -> 0; NULL material -> NULL; +0x18 m_weapon_anim 0 -> the material; >= size -> 0; list[anim] |
| 107 | 0x3356b0 | 40 | loadImage(unsigned int*) | strfile.cpp | MATCH | - | D2_TADR (0x1000a030) = tags & 0x0fffffff (dsll32 / dsrl32 4), D2_QWC 0, D2_CHCR 0x105, in that order |
| 110 | 0x335a10 | 108 | strFileClose() | strfile.cpp | MATCH | - | CD: snd_DoExternCall('dstr' 0x64737472, 4, 0 x5), sceSifFreeIopHeap(infile +0xc), m_streamingActive 0; else sceClose(infile +0x10 fd), m_streamingActive 0; returns 1 |
| 109 | 0x335960 | 168 | strFileRead(void*, int) | strfile.cpp | MATCH | - | CD: snd_DoExternCall(id, 5, (u32)size >> 11, buf, 0, &status, 0) << 11; else the one sceRead(fd, buf, size) per request (nonBlockReadReq), sceIoctl(fd, 1, &busy): busy -> 0, else request cleared and size |
| 111 | 0x335a80 | 132 | strFileRewind() | strfile.cpp | MATCH | - | zSys isCdBoot (+0x1d): snd_DoExternCall(id, 2, infile toc->startSector (+0x8 -> +0x4), 0 x4); else sceLseek(fd, 0, 0); < 0 -> sceClose(fd) and 0 (the quirk kept), else 1 |
| 108 | 0x335940 | 24 | setLoadImageTags(unsigned int*, void*, int, int, unsigned int) | strfile.cpp | MATCH | - | tail call setLoadImageTagsYX(tags, image, 1024, width, height, dbp) (a2 / a3 / t0 / t1 shifted) |
| 33 | 0x19c5a0 | 180 | CAiMaps::GetCellAction(CAiMapLoc const&) | ai_maps.cpp | MATCH | - | GetMapByIndex inline (mapid bits 0..5 < size, list walk); a map -> its GetCellAction(loc), else NULL |
| 34 | 0x19c660 | 180 | CAiMaps::GetRegion(CAiMapLoc const&) | ai_maps.cpp | MATCH | - | as #33 with CAiMap::GetRegion(loc) |
| 37 | 0x19d4e0 | 140 | CAiMaps::Close() | ai_maps.cpp | MATCH | - | FlushPlannerQueue; while size: the front map taken off (erase begin), deleting ~CAiMap (flag 1); FreeTables; byte +0xdc m_cookie + 1 |
| 36 | 0x19d460 | 124 | CAiMaps::Reset() | ai_maps.cpp | MATCH | - | ResetCells on every map of the list |
| 29 | 0x198060 | 96 | CAiMaps::GetCellNameString(CAiMapLoc const&) const | ai_maps.cpp | DEFECT-FIXED | C | GetMapByIndex(mapid & 0x3f), GetCellName(loc); a name -> its m_name (+0x8); none -> the literal "" @2386 (0x1980a8) where the port returned a function-local static array: the same empty text; now the literal |
| 35 | 0x19d3c0 | 152 | CAiMaps::GetMapByIndex(unsigned int) const | ai_maps.cpp | MATCH | - | index >= size -> NULL; begin, index steps, the element (+0x8) |
| 31 | 0x199600 | 8 | CAiMaps::SmoothPath(CAiPath&) | ai_maps.cpp | MATCH | - | tail call path.SmoothPath() |
| 32 | 0x199860 | 12 | CAiMaps::RegisterPathPlan(CAiMapLoc const&, CAiMapLoc const&, CAiPath*) | ai_maps.cpp | MATCH | - | tail call RegisterPathPlan(start, &goal, 1, path) (a3 1, t0 path) |
| 28 | 0x197660 | 80 | CAiMap::scanline::GetCell(unsigned int) const | ai_maps.cpp | MATCH | - | x < lhu +0 m_start or !(x < lhu +2 m_end) -> dummy_cell(); else m_cell (+0x4) + (x - start) * 8 |
| 30 | 0x198850 | 28 | _fixupEdge(CGraph*, CGEdge*, bool, unsigned int&, void*) | ai_maps.cpp | MATCH | - | reading: edge +0x14 m_edgeEx 0; else data 0 |
| 23 | 0x1811c0 | 188 | ai::FlushPlannerQueue() | ai_astar.cpp | MATCH | - | path_queue erased begin..end, then ValidateCells on every map of AiMaps |
| 20 | 0x180da0 | 140 | ai::ResetPathPlan() | ai_astar.cpp | MATCH | - | empty queue returns; the front path with +0x78 m_state 2 (PLANNING): the inlined DeletePlanner, +0x24 m_planleg 0 (quirk kept), m_points (+0x8c) clear, m_stats (+0x44) reset, state 1 (INQUEUE) |
| 24 | 0x181280 | 76 | CAiPath::DeletePlanner() | ai_astar.cpp | MATCH | - | deleting ~CAiStar on m_astar (its own NULL test), 0; m_custom (+0x8) -> operator delete(m_planner) (no dtor: CAiPlanner has none in the port either; GCC's sized delete is the scan's 44), m_planner 0, m_custom 0 |
| 21 | 0x181070 | 48 | ai::PathPlanAbort() | ai_astar.cpp | MATCH | - | _plan_path->Clear(), its +0x78 state 0, _plan_path NULL |
| 22 | 0x1810a0 | 48 | ai::PathPlanAddLeg(CAiMap*, CAiMapLoc const&, CAiMapLoc const&) | ai_astar.cpp | MATCH | - | _plan_path->plan_addleg(map, start, goal) as a byte |
| 19 | 0x3de070 | 60 | CompareSeals(CZSealBody*, CZSealBody*) | st_mpexit.cpp | MATCH | - | lh +0x4b4 m_sMvpScore differ -> slt (signed); else strcmp(+0x14 m_display_name a, b) < 0 |
| 18 | 0x3dca80 | 8 | CMPExitState::LoadLibs() | st_mpexit.cpp | MATCH | - | empty |
| 1 | 0x17de80 | 8 | ai::plot_tick(float, bool) | aidemo.cpp | MATCH | - | empty |
| 25 | 0x17e190 | 32 | ai::elevate(CPnt3D&, float, float) | ai_main.cpp | MATCH | - | x *= c, z *= c, y = s, in that order |
| 26 | 0x17ec00 | 56 | ai::is_moving(CPnt3D const*, float) | ai_main.cpp | MATCH | - | !(x * x + y * y + z * z <= threshold) (mul, adda / madd in the port's order; c.le.s false) |
| 27 | 0x17ee60 | 72 | CAi::Extrapolate(CPnt3D const*, CPnt3D const*, float, CPnt3D*) | ai_main.cpp | MATCH | - | vel->Scale(time, out), out->Add(pos, out) |
