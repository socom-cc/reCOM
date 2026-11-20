# Audit of list small-h (2026-11-20, socom-port-audit-small-h)

296 small functions (25,484 bytes, each under 200 bytes) in 30 files: Apps/FTS/game (reco, thezoom),
Apps/FTS/hud (hud_actionbitmap, hud_missioncams), Apps/FTS/state st_exit, zAnim (anim_main,
zanim_set), zArchive zarchive_holding, zCamera camera, zEntity ent_control, zFTS (fts_action,
fts_net_grenade), zGraph graph_node, zInput zin_keyboard, zMath (zmath_holding, zmath_pnt3d), zNode
node_assetlib, zParticle zparticle_source, zReader zrdr_parse, zSeal (seal, seal_airesponse,
seal_env), zSoftImage (si_object, si_script), zTexture ztexture_holding, zTwoD (c2dline, ztwod_main,
ztwod_poly), zUI zui, zVideo zvid_video. HEAD c182c48f. Judged file by file in the scan's rank
order, from the by-file packets.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 264 |
| DEFECT-FIXED | 23 (A 1, B 5, C 17) |
| DEVIATION-KEPT | 9 |
| UNJUDGED | 0 |

Defect rate 23 / 296 (A 1, B 5, C 17).

Fixes:
- A, #296 CVideo::Clear: the ELF clears the render buffer through the vramcode sprite packet
  (FRAME_1 renderBuf / FBW 10, RGBAQ with Q 1.0, XYZ2 640 x 448, sceDmaSendN 10 qwords, sceDmaSync;
  0x307870-0x307908); the port body was empty. Called at mission complete / fade, the exit state
  and cinematics.
- B, #205 CZSealBody::AttemptBombDefuse: RequestNewBombState(m_id, 4 defused, &zero) (0x28c21c); the
  port was empty. MP bomb games only.
- B, #2 recoStopRecognizing: a running engine is stopped (gsapi_EngineStop 0x3360dc), the flag
  cleared, an error printed, the result returned. Unreachable (recoInited never set, ELF too).
- B, #6 recoStartRecognizing: recoNumHeads 1, gsapi_EngineStart (0x3363ec), recoRecognizing set
  (also on failure, quirk), the result returned. Unreachable as #2. gsapi_EngineStart is added to
  port/compat/gsapi_offline.c by an edit file (the scratch folder's edits/gsapi_offline.txt).
- B, #77 CAppCamera::CmdParse3rdPersonTest: the header gets data_size 4 and timeless 1 from
  _calloc(1, 4, "camera.cpp", 421) (0x1eb9b4-0x1eb9fc); the port left data_size 0. The disc's anims
  load from ZAR, the parser is not used.
- B, #121 zdb::CAssetLib::AddPalette: appended and the palette returned (0x231080 / 0x231088); the
  port inserted first and returned NULL (the audit-medium-node lead).
- C, #105 sceUsbKeybdInit: the delay loop counts from 0x10000 (0x21ba54).
- C, #217 CZSealBody::UninitDatabaseHandles and #144 CCompass::Close: clear() before the swap with an
  empty vector (0x292240, 0x24e44c).
- C, #225 ParentPistolToRHandCallback: m_id lh compared unsigned with the whole size (0x298834).
- C, #232 SetMoveWeaponEncumbMod (0x29b918), #73 CAppCamera::WiggleScalar (0x1ea458), #252 / #253 /
  #255 CZSIScript SetFrameRate / SetLoopTime / Share (0x1de2bc, 0x1de2fc, 0x1dec4c): the compare
  forms as the ELF has them (NaN only).
- C, #27 CZAnimNameTable::Unload: the free loop compares signed (slt 0x1c2e7c).
- C, #47 CZAnimMain::GetCmdEntry(name, create): GetCmd gets GetCmdSet's whole result (0x1c4b9c).
- C, #55 CZAnimMain::Close, #67 CZAnimSet::Name: the _free / _strdup tags (anim_main.cpp 1898 / 159;
  zanim_set.cpp 111 / 113) where the port used zfree / zstrdup.
- C, #75 ~CAppCamera: m_track cleared (0x1eb76c).
- C, #82 CEntityCtrl::CEntityCtrl: m_throttle by memset(12) (0x1f20c8).
- C, #70 zar::CKey::~CKey: no clear() of its own (0x1d8164).
- C, #286 ActionItem::operator=: Animation / Argument cleared after each free, before other's is
  read (0x3842e8 / 0x384328; a self-assignment copies NULL).

Kept deviations (reasons in the code): #102 / #103 / #104 the USB keyboard requests return -1 with
no bound server (USBKB.IRX is offline); #209 HandlePickupEquip's seven unused items zeroed (the ELF
sends them unset); #25 CZAnimNameIndexTable::Load's count slot zeroed before the Fetch; #29 / #30
SequenceExists / ResumeSequence and #65 CZAnimSet::Anim(name) keep the name NULL tests the ELF
lacks (as audit-medium-anim-b kept for the other walks); #134 Particle::Source::List::Uninit takes
the next node before the delete (the ELF reads it from the freed node, 0x23aac8).

Leads for other lists:
- zanim.h: CZAnimNameTable::m_count is u32 in the port, sint in DWARF (the loops compare signed).
- si_script.cpp CZSIScript::Read 0x1de600 (not on this list): its inlined SetLoopTime tests
  m_tf > 0 where SetLoopTime's ELF form is !(m_tf <= 0).
- seal_env.cpp: the u16 casts of the m_body_parts index tests in the other weapon parenting
  functions (lines near 4144-4188) should be checked against their ELF as #225 was.

What the packets lacked: the fifth and later arguments (checked by hand: zNetCreateObject's stack
words, InitButton's t0 / t1, CanPickupNetItem's t0, AddCmd's t0 / t1, PartInSpace's t0); two
vtable slots named another class's method (#292 slot +0x5c is C2DString::SetString, #19 slot +0x78 is
ClearAndWipe; vt.py); #110 / #111 showed the #if 0 held copy where the live definition is the inline
in zmath.h; the DWARF sign of CZAnimNameTable::m_count (dw.py); the C2DString vtable, the
_zvid_public layout, the gsapi compat file and the _zanim_cmd_hdr bitfields were looked up for
#292, #296, #2 / #6 and #46 / #77. About 15 functions needed a lookup outside the packet.

Runs: the default build links (audit-small-h-default); one `gate.ps1 -Only roundtrip` on the final tree
(HEAD + mine.txt + the gsapi shared edit): PASS, 4 returns to the menus, in use 18657916 B flat. No
per-function emulator run.

## Rows

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 101 | 0x21b870 | 120 | sceUsbKeybdSync(int) | gamez/zInput/zin_keyboard.cpp | MATCH | | mode 1 returns CheckStatRpc, mode 0 spins until 0 and returns 0, else -1 (0x21b878-0x21b8d8) |
| 102 | 0x21b8f0 | 96 | sceUsbKeybdGetLocation(int, unsigned char*) | gamez/zInput/zin_keyboard.cpp | DEVIATION-KEPT | | sdata[0] = n sw, RPC 3 mode 1, sizes 32/32, t3 and the stack end-param 0, result returned (0x21b900-0x21b940); the unbound-server return -1 is the port's (USBKB offline), reason in the code |
| 103 | 0x21b950 | 96 | sceUsbKeybdRead(unsigned int, unsigned char*) | gamez/zInput/zin_keyboard.cpp | DEVIATION-KEPT | | as #102 with RPC 2 (0x21b978); the unbound-server guard is the port's, reason in the code |
| 104 | 0x21b9b0 | 88 | sceUsbKeybdGetInfo(unsigned char*) | gamez/zInput/zin_keyboard.cpp | DEVIATION-KEPT | | RPC 1 mode 1, sdata unchanged, 32/32, end 0 (0x21b9c0-0x21b9e4); the unbound-server guard is the port's, reason in the code |
| 105 | 0x21ba10 | 128 | sceUsbKeybdInit() | gamez/zInput/zin_keyboard.cpp | DEFECT-FIXED | C | InitRpc(0), bind 0x80000211, hang on < 0, server +0x24 test match; the delay loop counts from 0x10000 with the test before the decrement (0x21ba54-0x21ba6c), the port from 0xffff: fixed. The offline-module early return is the port's (kept, reason in the code) |
| 106 | 0x21be90 | 32 | InitKeyreadStuff() | gamez/zInput/zin_keyboard.cpp | MATCH | | sceUsbKeybdInit, returns 0 |
| 107 | 0x21beb0 | 8 | CKeyboard::Tick(float) | gamez/zInput/zin_keyboard.cpp | MATCH | | empty |
| 108 | 0x21bec0 | 68 | CKeyboard::~CKeyboard() | gamez/zInput/zin_keyboard.cpp | MATCH | | nothing of its own, deleting-dtor delete only |
| 109 | 0x21bf10 | 12 | CKeyboard::CKeyboard() | gamez/zInput/zin_keyboard.cpp | MATCH | | sb zero +0x0 m_unknown0 (u8) |
| 83 | 0x1fe790 | 184 | CNodeAction::SyncActionsMP(int) | gamez/zFTS/fts_action.cpp | MATCH | | every action: m_network_log bit 0 of +0x2e, valve m_value lhu != 0, NetSendActionAnim(-1, m_id lhu +0x2c, value & 0xff, player) (0x1fe7cc-0x1fe800) |
| 84 | 0x1fe9c0 | 12 | CNodeAction::OnAction(zdb::CNode*, void*) | gamez/zFTS/fts_action.cpp | MATCH | | tail call ExecuteAction(seal = a2, 0) |
| 85 | 0x1fe9d0 | 128 | CNodeAction::GetVUIString(std::string&) | gamez/zFTS/fts_action.cpp | MATCH | | GetUIString(out), then each char = tolower(signed char) in place, begin to end (0x1fea18-0x1fea30) |
| 86 | 0x1fea50 | 172 | CNodeAction::GetUIString() | gamez/zFTS/fts_action.cpp | MATCH | | m_type lbu +0x20 jump table 0x44e5c0 (5 BREACH, 6 SATCHEL), door / window close text when m_value != 0, NULL past 6 |
| 87 | 0x1fec80 | 152 | CNodeAction::~CNodeAction() | gamez/zFTS/fts_action.cpp | MATCH | | Destroy(m_valve), m_valve 0, _free(m_descriptor, "fts_action.cpp", 381) when set, m_descriptor 0, then the +0x4 vector dtor |
| 88 | 0x1fefd0 | 168 | CNodeAction::GetActionById(unsigned int) | gamez/zFTS/fts_action.cpp | MATCH | | list walk, m_id lhu +0x2c == id returns the action, else NULL |
| 89 | 0x1ff080 | 180 | CNodeAction::FindActionByValve(CValve const*) | gamez/zFTS/fts_action.cpp | MATCH | | NULL valve returns NULL (ELF test 0x1ff090), m_valve +0x18 compare, else NULL |
| 90 | 0x1ff5b0 | 168 | CNodeAction::Reset() | gamez/zFTS/fts_action.cpp | MATCH | | each non-NULL action: m_valve Set(0) when set, m_handle +0x10 = 0 (0x1ff604-0x1ff628) |
| 91 | 0x1ff7d0 | 108 | _actionValveCallback(CValve*, void*) | gamez/zFTS/fts_action.cpp | MATCH | | NULL data returns; act 0, AiMaps.GetActionById(m_id, loc, &act); act byte +6 bits 4-6 (m_state) = m_value & 7, others kept (0x1ff80c-0x1ff828) |
| 92 | 0x1ff840 | 140 | CNodeAction::GetActionType(CNodeAction::ACTION_TYPE) | gamez/zFTS/fts_action.cpp | MATCH | | type & 0xff, jump table 0x44e6a0: 2 SWITCH, 3 DEFUSE, 5 BREACH, 6 SATCHEL, UNKNOWN past 6 |
| 202 | 0x28c100 | 104 | CZSealBody::CanClimbWall() | gamez/zSeal/seal_env.cpp | MATCH | | CanTraverse 3, 4, 1, 5 in that order, short-circuit, bool (0x28c104-0x28c154) |
| 203 | 0x28c170 | 8 | CZSealBody::CanClimbLadder() | gamez/zSeal/seal_env.cpp | MATCH | | tail call CanTraverse(2) |
| 204 | 0x28c1f0 | 8 | CZSealBody::HandleBombDefuse() | gamez/zSeal/seal_env.cpp | MATCH | | empty |
| 205 | 0x28c200 | 48 | CZSealBody::AttemptBombDefuse() | gamez/zSeal/seal_env.cpp | DEFECT-FIXED | B | the ELF asks RequestNewBombState(m_id, 4 BOMB_DEFUSED, &zero point) (0x28c204-0x28c21c); the port body was empty: written. Masked: MP bomb games only |
| 206 | 0x28c3e0 | 144 | CZSealBody::DropMPBomb() | gamez/zSeal/seal_env.cpp | MATCH | | kit +0x520 HasItem(154), RequestNewBombState(m_id, 1, GetPosW slot +0xc), FindAuxNode("Satchel", false), SetActive(false) slot +0x34 when found |
| 207 | 0x28c540 | 48 | CZSealBody::HandlePickupMPBomb(CPickup*) | gamez/zSeal/seal_env.cpp | MATCH | | RequestNewBombState(m_id, 2, &zero point) |
| 208 | 0x28c570 | 80 | CZSealBody::EnableMPBombGear(bool) | gamez/zSeal/seal_env.cpp | MATCH | | FindAuxNode("Satchel", false), SetActive(enable) slot +0x34 when found |
| 209 | 0x28e2f0 | 188 | CZSealBody::HandlePickupEquip(CPickup*) | gamez/zSeal/seal_env.cpp | DEVIATION-KEPT | | m_isAlive bit 3 of +0xdd, theNetwork+0x9 off: PickupItem; owner = net entity id & 0xff, m_data NULL returns, items[0] = weapon lbu +0x60, owner == m_id: CanPickupNetItem(1, m_netid, items, m_id & 0xff), else SendMayIPickupMessage(1, m_netid, items, m_id & 0xff, owner) (t0 checked); the seven other items are zero in the port where the ELF leaves them unset (0x28e340), reason in the code |
| 210 | 0x28e3b0 | 48 | CZSealBody::HandlePickupAmmoInstance(CPickup*) | gamez/zSeal/seal_env.cpp | MATCH | | m_isAlive bit 3, kit PickupAmmo(pickup) |
| 211 | 0x28f1f0 | 44 | CZSealBody::SetArmor(DAMAGE_LOCATION, float) | gamez/zSeal/seal_env.cpp | MATCH | | index & 0xff, m_armor +0xf28, c.lt armor[i] < new then store (0x28f200) |
| 212 | 0x290a90 | 16 | CZSealBody::RemoteWeaponDamageNonVictim(...) | gamez/zSeal/seal_env.cpp | MATCH | | tail call RemoteWeaponDamageVictim with 0.0f, 0.0f, the other arguments passed on (t0 / t1 unchanged) |
| 213 | 0x290f10 | 148 | CZSealBody::SetMPStats(MPSealStats*, bool) | gamez/zSeal/seal_env.cpp | MATCH | | mp: +0x46c else +0x4c0; kills lb to +0x10, headshots +0x0, washit +0x14, deaths +0x18, bases +0x20, hostages rescued +0x24, hit % unsigned to float / 100 to +0x28, MVP score lh / sh +0x48 |
| 214 | 0x290fb0 | 136 | CZSealBody::GetMPStats(MPSealStats*, bool) | gamez/zSeal/seal_env.cpp | MATCH | | the same offsets back as bytes (lb), hit % fptoui(100 * m_hit_percent), MVP score halfword |
| 215 | 0x2918d0 | 196 | CZSealBody::GetTargetPosW(CPnt3D*) | gamez/zSeal/seal_env.cpp | MATCH | | PartInSpace(m_spinehi, NULL, pos, NULL) (t0 0), m_node matrix Transform of one point with the translation (inlined), returns pos |
| 216 | 0x2921d0 | 64 | CZSealBody::Uninit_ReInitDatabaseHandles() | gamez/zSeal/seal_env.cpp | MATCH | | m_dropanim 0, _free(m_sealstep, "seal_env.cpp", 8705) when set, 0, RemoveWeaponEventCallback(HandleWeaponEvent) |
| 217 | 0x292210 | 140 | CZSealBody::UninitDatabaseHandles() | gamez/zSeal/seal_env.cpp | DEFECT-FIXED | C | _free tags 8697 / 8705, the statics cleared, the callback removed match; the ELF clears m_blooddriptexhandles before swapping it with an empty vector (clear 0x292240, swap 0x292250), the port only swapped: clear() added, same effect |
| 218 | 0x293900 | 8 | CZSealBody::InitDatabaseHandles() | gamez/zSeal/seal_env.cpp | MATCH | | tail call ReInitDatabaseHandles |
| 219 | 0x294180 | 28 | CZSealBody::SetHudHitFlag() | gamez/zSeal/seal_env.cpp | MATCH | | bit 1 of +0xf58 set, others kept |
| 220 | 0x2941a0 | 48 | CZSealBody::HudUpdateViewCone() | gamez/zSeal/seal_env.cpp | MATCH | | bit 0 of +0xf58 tested and cleared, returns 1 / 0 |
| 221 | 0x2941d0 | 56 | CZSealBody::GetHudHitFlag() | gamez/zSeal/seal_env.cpp | MATCH | | bit 1 of +0xf58 tested and cleared, returns 1 / 0 |
| 222 | 0x294940 | 172 | CZSealBody::GetBodyDamage(float, float) | gamez/zSeal/seal_env.cpp | MATCH | | health <= k * max (c.le) with 0x3dcccccd, 0x3e99999a, 0x3f333333, 0x3f666666 returning 4, 3, 2, 1, else 0 |
| 223 | 0x294a70 | 128 | CZSealBody::GetLegDamage(float, float) | gamez/zSeal/seal_env.cpp | MATCH | | 0x3e99999a, 0x3f333333, 0x3f666666 returning 3, 2, 1, else 0 |
| 224 | 0x294af0 | 112 | CZSealBody::GetHeadDamage(float, float) | gamez/zSeal/seal_env.cpp | MATCH | | health <= 0 returns 3, <= 0.5 * max 2, <= 0x3f7d70a4 * max 1, else 0 |
| 225 | 0x2987b0 | 192 | ParentPistolToRHandCallback(void*, void*) | gamez/zSeal/seal_env.cpp | DEFECT-FIXED | C | m_pistol +0x2d8 node test, DeleteChild slot +0x1c on the old parent's node, parent = m_rhand +0x284, AddChild slot +0x18, m_blendme +0x26 sh 0 match; the index test is m_id lh, sign-extended, against the full size (sltu 0x298834), the port truncated both to u16: written as the ELF |
| 226 | 0x298870 | 180 | CZSealBody::IsChangingWeapons() | gamez/zSeal/seal_env.cpp | MATCH | | Top of m_blends; IsCurrentBlend 56, 57, 58: !IsDone(m_dT); else m_overlay->m_anim, its m_anim, m_animType lh +0x1a == MovingRifle2Pistol, NULLs false |
| 227 | 0x298a10 | 184 | CZSealBody::IsThrowing(bool) | gamez/zSeal/seal_env.cpp | MATCH | | top blend +0x30 lh against Throw, CrouchThrow, ProneThrow, Toss, PistolToss, ProneToss, PistolProneToss, CrouchThrow again; noPeek false, else the two peek tosses |
| 228 | 0x299360 | 120 | CZSealBody::CanChangeItem() | gamez/zSeal/seal_env.cpp | MATCH | | m_isAlive bit 3, CanFire, m_airborne bit 5 of +0xf5a, m_state lb +0x11d != 6 |
| 229 | 0x29a790 | 104 | CZSealBody::CacheReticuleSeal(bool) | gamez/zSeal/seal_env.cpp | MATCH | | on: bit 0 of +0x178 set, then GetSeal(m_last_reticule.m_node) to +0x174; off: bit cleared, +0x174 0 |
| 230 | 0x29a800 | 52 | CZSealBody::GetReticuleSeal() | gamez/zSeal/seal_env.cpp | MATCH | | bit 0 of +0x178: +0x174, else GetSeal(+0x35c) |
| 231 | 0x29a840 | 8 | CZSealBody::GetReticuleDi() | gamez/zSeal/seal_env.cpp | MATCH | | this + 0x340 |
| 232 | 0x29b8d0 | 108 | CZSealBody::SetMoveWeaponEncumbMod() | gamez/zSeal/seal_env.cpp | DEFECT-FIXED | C | encumb = 1 - 0.01 * enc (0x3c23d70a) to +0xed0, move = encumb * m_damagemod to +0xecc match (product operands swapped only); the clamp tests !(move <= 1) (c.le / bc1t 0x29b918), the port move > 1: written as the ELF |
| 233 | 0x29c420 | 16 | CZSealBody::HandleWepHit() | gamez/zSeal/seal_env.cpp | MATCH | | m_wephit->m_node 0, Top() for nothing (quirk kept) |
| 234 | 0x29cbf0 | 104 | CZSealBody::DestroyAimAnims() | gamez/zSeal/seal_env.cpp | MATCH | | size word +0x4 zero returns 0; else data[size - 1], size--, operator delete, until 0, returns 1 |
| 235 | 0x29cc60 | 192 | CZSealBody::ApplyBlinkAnim() | gamez/zSeal/seal_env.cpp | MATCH | | both lids +0x2e8 / +0x2ec non-NULL, Align(unit_nz, m_blink +0x10), quat to both parts' m_rot, SetRotation on both nodes |
| 236 | 0x29cd20 | 192 | CZSealBody::ApplyEyeLookAnim() | gamez/zSeal/seal_env.cpp | MATCH | | as #235 with the eyeballs +0x2e0 / +0x2e4 and m_eyelook +0xf94 |
| 237 | 0x29cde0 | 12 | CZSealBody::GetLookDir() const | gamez/zSeal/seal_env.cpp | MATCH | | m_look +0xf90 plus 0x10 |
| 238 | 0x29d080 | 180 | CBlink::Blink(int) | gamez/zSeal/seal_env.cpp | MATCH | | m_done +0x70 and m_org +0x80 == 0; 1: m_org 1, MakeXRot(0xbf17e9d9), Apply(unit_nz, &down, 1), SetDir(&down, &unit_nz, 1.5); else m_org -1, SetDir(&unit_nz, &m_curr_dir, 1.5) |
| 239 | 0x29d140 | 176 | CLook::LookTick(float) | gamez/zSeal/seal_env.cpp | MATCH | | fracT + dT / deltaT, !(fracT < 1) sets 1 and done (c.lt / bc1t), m_cross +0x60 Scale(0.5 * quadW), Exp, m_quat0 Mul, Apply to m_curr_dir |
| 240 | 0x29da30 | 192 | CBlink::CBlink() | gamez/zSeal/seal_env.cpp | MATCH | | the inline CLook part (Clear, -z, rate 0, done, goal = curr), m_org 0, m_nextT = 2 + 6 * (0x30000000 * rand()) in that order |
| 241 | 0x29daf0 | 92 | CLook::CLook() | gamez/zSeal/seal_env.cpp | MATCH | | Clear, curr (0, 0, -1), m_rate 0, m_done 1, goal = curr |
| 242 | 0x29dd20 | 100 | CZSealBody::SetLookDir(CPnt3D const*, float) | gamez/zSeal/seal_env.cpp | MATCH | | CanHeadLook false returns 0; else m_look->SetLookDir(this, dir, rate) result |
| 243 | 0x29e7c0 | 136 | CZSealBody::RotateHead(float, float) | gamez/zSeal/seal_env.cpp | MATCH | | pitch == 0 (c.eq): CQuat::identity to m_fwdlook +0xf60; else MakeXRot(pitch) copied |
| 244 | 0x29e850 | 148 | CZSealBody::GetLookDirW(CPnt3D*) const | gamez/zSeal/seal_env.cpp | MATCH | | m_node matrix rows 0-2 Rotate of m_look->m_curr_dir into dir (inlined), returns dir |
| 245 | 0x29fda0 | 12 | CZSealBody::PreCheckDIDown() | gamez/zSeal/seal_env.cpp | MATCH | | +0x25c = -999 |
| 246 | 0x29fdb0 | 96 | CZSealBody::SetWepHit(zdb::IntersectStruct*) | gamez/zSeal/seal_env.cpp | MATCH | | hit: pos, norm and node copied into m_wephit (poly not); NULL: node 0 |
| 247 | 0x29fe10 | 136 | CZSealBody::SetWallHit(zdb::IntersectStruct*, CPnt3D*, CPnt3D*) | gamez/zSeal/seal_env.cpp | MATCH | | memcpy 32 bytes (sizeof IntersectStruct is 32 in the port too), hit0 / hit1 at +0x20 / +0x2c; NULL: m_fwdhit node 0 |
| 248 | 0x2a01d0 | 64 | CZSealBody::PostCheckDILadder(float&, float&, float&) | gamez/zSeal/seal_env.cpp | MATCH | | fb < stoppedV (c.lt / bc1f) returns 1, else CheckDILadder |
| 258 | 0x3003e0 | 156 | C2DLine::SetClipInfo(float[4]*, float[4]*, float[4]*, int) | gamez/zTwoD/c2dline.cpp | MATCH | | two ends, four words each: pos to m_vertex +0x30, rgb to m_RGB +0x50, uv to m_NewUV +0x70, component by component; the count unread |
| 259 | 0x300480 | 156 | C2DLine::FillClipInfo(float[4]*, float[4]*, float[4]*) | gamez/zTwoD/c2dline.cpp | MATCH | | the same three arrays back out, same order |
| 260 | 0x300700 | 92 | C2DLine::Draw(zdb::CCamera*) | gamez/zTwoD/c2dline.cpp | MATCH | | IsOn & 0xff, m_texture +0x90 non-NULL, MakePacket(camera), C2D::Draw(camera) |
| 261 | 0x300760 | 28 | C2DLine::SetUV(float, float, float, float) | gamez/zTwoD/c2dline.cpp | MATCH | | u0 +0x70, -v0 +0x74, u1 +0x80, -v1 +0x84 |
| 262 | 0x300780 | 128 | C2DLine::SetPos(int, int, int, int) | gamez/zTwoD/c2dline.cpp | MATCH | | m_x / m_y words, each vertex = top + (f32)v * pixel (mul then add, operand order as the ELF) to +0x30 / +0x34 / +0x40 / +0x44 |
| 263 | 0x300930 | 36 | C2DLine::SetTrans(float) | gamez/zTwoD/c2dline.cpp | MATCH | | alpha +0x5c / +0x6c, bit 2 of +0x15 set |
| 264 | 0x300960 | 28 | C2DLine::SetColor(float, float, float) | gamez/zTwoD/c2dline.cpp | MATCH | | r g b to +0x50..0x58 and +0x60..0x68 |
| 271 | 0x300e90 | 136 | C2DTriFan::Draw(zdb::CCamera*) | gamez/zTwoD/ztwod_poly.cpp | MATCH | | IsOn, then each 208-byte C2DPoly of m_polys: Draw(camera) through the vtable at +0xc slot +0xc; no children |
| 272 | 0x300f20 | 136 | C2DTriFan::~C2DTriFan() | gamez/zTwoD/ztwod_poly.cpp | MATCH | | m_polys clear(), the vector dtor, C2D::~C2D |
| 273 | 0x301390 | 80 | C2DPoly::Draw(zdb::CCamera*) | gamez/zTwoD/ztwod_poly.cpp | MATCH | | IsOn & 0xff, MakePacket(camera), C2D::Draw(camera) |
| 274 | 0x3014e0 | 40 | C2DPoly::SetUV(float, float, float, float, float, float) | gamez/zTwoD/ztwod_poly.cpp | MATCH | | u to +0x60 / +0x70 / +0x80, -v to +0x64 / +0x74 / +0x84 |
| 275 | 0x301620 | 8 | C2DPoly::GetTrans() | gamez/zTwoD/ztwod_poly.cpp | MATCH | | $f0 = +0x3c (m_RGB[0][3]) |
| 276 | 0x301630 | 40 | C2DPoly::SetTrans(float) | gamez/zTwoD/ztwod_poly.cpp | MATCH | | alpha +0x3c / +0x4c / +0x5c, bit 2 of +0x15 set |
| 277 | 0x301660 | 64 | C2DPoly::GetColor() | gamez/zTwoD/ztwod_poly.cpp | MATCH | | PNT3D returned through the hidden pointer: +0x30 / +0x34 / +0x38 |
| 278 | 0x3016a0 | 40 | C2DPoly::SetColor(float, float, float) | gamez/zTwoD/ztwod_poly.cpp | MATCH | | r g b to the three vertices +0x30 / +0x40 / +0x50 |
| 1 | 0x3360a0 | 8 | recoGetNumHeads() | Apps/FTS/game/reco.cpp | MATCH | | $f0 = recoNumHeads |
| 2 | 0x3360b0 | 100 | recoStopRecognizing() | Apps/FTS/game/reco.cpp | DEFECT-FIXED | B | the ELF stops a running engine (gsapi_EngineStop(g_hEngine) 0x3360dc), clears recoRecognizing, prints a negative result and returns it (0x3360e4-0x336100); the port only cleared the flag: written. Masked: recoInited is never set (recoInit2), in the ELF too |
| 3 | 0x336210 | 184 | recoGetFirstWordID(int*) | Apps/FTS/game/reco.cpp | MATCH | | recoInited, GetResultString(*word), NULL returns, sprintf "%s", i = 0..*word (none when negative), strcasecmp == 0 stores i and returns |
| 4 | 0x3362d0 | 140 | recoEnableWord(int, int) | Apps/FTS/game/reco.cpp | MATCH | | recoInited; loop: {1, &word} by value, EnableWords, negative printed, RECO_DBG_PRINT: GetResultString(word), negative printed; while recoGetNextWordID(&word) |
| 5 | 0x336360 | 68 | recoDisableAllWords(int) | Apps/FTS/game/reco.cpp | MATCH | | recoInited, EngineStop, DisableAllWords, negative printed |
| 6 | 0x3363b0 | 140 | recoStartRecognizing() | Apps/FTS/game/reco.cpp | DEFECT-FIXED | B | the ELF sets recoNumHeads 1.0, the first-call guard iRecoMode 0, gsapi_EngineStart (0x3363ec), recoRecognizing 1 on success; on failure recoRecognizing 1 and the error printed only when it was clear (quirk), the result returned; the port returned 0: written (gsapi_EngineStart is added to port/compat/gsapi_offline.c by an edit file). Masked: recoInited is never set |
| 7 | 0x336440 | 40 | recoTick() | Apps/FTS/game/reco.cpp | MATCH | | recoInited lbu, ExecServer(0) |
| 8 | 0x336940 | 152 | recoSetupLanguage() | Apps/FTS/game/reco.cpp | MATCH | | LanguageLoadBuffer(RecoLngData, 0), negative printed and returned; EngineOpen(0, &g_hEngine), NotifySetCallback(cbrecoNotify), EngineSetMode(1) while >= 0, last negative printed, returned |
| 9 | 0x336d90 | 12 | recoInit() | Apps/FTS/game/reco.cpp | MATCH | | recoShouldInit sb 0, returns 1 |
| 10 | 0x336da0 | 28 | recoIsRecognizing() | Apps/FTS/game/reco.cpp | MATCH | | recoInited ? recoRecognizing (lbu) : 0 |
| 136 | 0x24d800 | 60 | CZSealBody::StopAllHeartbeatSounds() | gamez/zSeal/seal.cpp | MATCH | | instance set: Stop, ReleaseSoundInstance, instance 0, cur index -1 |
| 137 | 0x24d840 | 84 | CZSealBody::CloseHeartbeatSounds() | gamez/zSeal/seal.cpp | MATCH | | the inlined stop (#136), the three sounds 0 |
| 138 | 0x24d8a0 | 80 | CZSealBody::OpenHeartbeatSounds() | gamez/zSeal/seal.cpp | MATCH | | GetSoundByName SLOW / MEDIUM / FAST _LOOP into [0..2] |
| 139 | 0x24e0e0 | 40 | CZSealBody::CurrentPickupSecondary() | gamez/zSeal/seal.cpp | MATCH | | m_control NULL returns NULL (ELF test 0x24e0ec), FindPickup(ctrl +0x14c) |
| 140 | 0x24e110 | 40 | CZSealBody::CurrentPickup() | gamez/zSeal/seal.cpp | MATCH | | as #139 with ctrl +0x148 |
| 141 | 0x24e140 | 28 | CZSealBody::CompassAnchor_Hostage(CCompassAnchor*) | gamez/zSeal/seal.cpp | MATCH | | 1 when +0xdbc was NULL, then stored, returned & 0xff |
| 142 | 0x24e160 | 28 | CZSealBody::CompassAnchor_MPBase(CCompassAnchor*) | gamez/zSeal/seal.cpp | MATCH | | as #141 with +0xdb8 |
| 143 | 0x24e180 | 28 | CZSealBody::CompassAnchor_MPBomb(CCompassAnchor*) | gamez/zSeal/seal.cpp | MATCH | | as #141 with +0xdb4 |
| 144 | 0x24e440 | 72 | CCompass::Close() | gamez/zSeal/seal.cpp | DEFECT-FIXED | C | the ELF clears the vector (size 0 at 0x24e44c) before swapping it with an empty one and destroying that (0x24e454-0x24e470); the port only swapped: clear() added, same effect |
| 145 | 0x24e490 | 8 | CCompass::Open() | gamez/zSeal/seal.cpp | MATCH | | tail call reserve(48) |
| 146 | 0x24e4a0 | 8 | CZSealBody::ActionCommand(unsigned int) | gamez/zSeal/seal.cpp | MATCH | | +0xdcc sw |
| 147 | 0x24e4b0 | 8 | CZSealBody::ActionCommand() | gamez/zSeal/seal.cpp | MATCH | | +0xdcc lw |
| 148 | 0x24e4c0 | 8 | CZSealBody::ActionDisplayOn(bool) | gamez/zSeal/seal.cpp | MATCH | | +0xdc8 sb |
| 149 | 0x24e4d0 | 68 | CZSealBody::ActionSelectionMask(unsigned int, bool) | gamez/zSeal/seal.cpp | MATCH | | (0, false) clears +0xdc4; add: or-in 1 << bit; else = 1 << bit |
| 150 | 0x24e520 | 8 | CZSealBody::ActionSelectionMask() | gamez/zSeal/seal.cpp | MATCH | | +0xdc4 lw |
| 151 | 0x24e530 | 68 | CZSealBody::ActionAvailableMask(unsigned int, bool) | gamez/zSeal/seal.cpp | MATCH | | as #149 on +0xdc0 |
| 152 | 0x24e580 | 8 | CZSealBody::ActionDisplayOn() | gamez/zSeal/seal.cpp | MATCH | | +0xdc8 lbu |
| 153 | 0x24e590 | 8 | CZSealBody::ActionAvailableMask() | gamez/zSeal/seal.cpp | MATCH | | +0xdc0 lw |
| 154 | 0x24e5a0 | 100 | CSealStats::WasHit(CZSealBody const&) | gamez/zSeal/seal.cpp | MATCH | | !theNetwork+0x9 or the body is ftsGetPlayer: m_washit +0x14 ++ |
| 155 | 0x24e610 | 176 | CSealStats::UpdateMvpScore(CZSealBody const&) | gamez/zSeal/seal.cpp | MATCH | | same gate; (s16)(lh tied + 2 lh won + lh kills) << 8 plus (hits << 8) / shots (0 when no shots), sh +0x48 |
| 156 | 0x24e7d0 | 140 | CSealStats::GetPointsEarned(int, int, int, float) const | gamez/zSeal/seal.cpp | MATCH | | 3.8 * (kills / (1 + a)); (b / 8) * rate + (40 * (x - 0.5)) * ((5 + c) / (5 + b)) in the ELF's operand order (the ELF's mula / madd pair), fptosi |
| 157 | 0x24e860 | 16 | CSealStats::IncrSecondaryRoundsFired(int) | gamez/zSeal/seal.cpp | MATCH | | +0x44 += count |
| 158 | 0x24e870 | 16 | CSealStats::IncrPrimaryRoundsFired(int) | gamez/zSeal/seal.cpp | MATCH | | +0x40 += count |
| 159 | 0x24e880 | 16 | CSealStats::IncrGrenadesUsed(int) | gamez/zSeal/seal.cpp | MATCH | | +0x38 += count |
| 160 | 0x24e890 | 16 | CSealStats::IncrTimesSeen(int) | gamez/zSeal/seal.cpp | MATCH | | +0x2c += count |
| 161 | 0x24e8a0 | 88 | CSealStats::Reset() | gamez/zSeal/seal.cpp | MATCH | | every word 0x0-0x44 and 0x4c / 0x50 zero, m_sMvpScore sh 0 |
| 162 | 0x24eb00 | 100 | CSealStats::HeadShot(CZSealBody const&) | gamez/zSeal/seal.cpp | MATCH | | the #154 gate, m_headshots +0x0 ++ |
| 163 | 0x24ec60 | 100 | CSealStats::Death(CZSealBody const&) | gamez/zSeal/seal.cpp | MATCH | | the #154 gate, m_deaths +0x18 ++ |
| 164 | 0x24ecd0 | 32 | CZSealBody::ExecuteDelayedAction_Jump() | gamez/zSeal/seal.cpp | MATCH | | bit 2 of +0xf5a set, returns 1 |
| 165 | 0x24ecf0 | 32 | CZSealBody::ExecuteDelayedAction_Climb() | gamez/zSeal/seal.cpp | MATCH | | bit 1 of +0xf5a set, returns 1 |
| 166 | 0x24ed10 | 68 | CZSealBody::ExecuteAction_ApplyRestraint(CZSealBody*) | gamez/zSeal/seal.cpp | MATCH | | NULL victim returns; RestrainBuddy, m_mp_stats restrained +0x4a0 ++ (the ELF's v0 1 / 0 is unread, port void, noted in the code) |
| 167 | 0x24ee90 | 68 | CZSealBody::ExecuteAction_KnifeAttack(CZSealBody*) | gamez/zSeal/seal.cpp | MATCH | | as #166 with StabBuddy and stealth kills +0x49c |
| 168 | 0x24eee0 | 128 | CZSealBody::SetSnakePathUpdate(bool, unsigned int) | gamez/zSeal/seal.cpp | MATCH | | on and bit 0 of +0xf5a set returns; on: bit set, SetSnakeLength(len) on +0x384; off: bit cleared, SetSnakeLength(0) |
| 169 | 0x24ef60 | 32 | CZSealBody::ResetAltitude(float) | gamez/zSeal/seal.cpp | MATCH | | m_alt +0xe98, bit 7 of +0xdc set |
| 170 | 0x24ef80 | 92 | CZSealBody::TeleportTo(CMatrix const*) | gamez/zSeal/seal.cpp | MATCH | | m_alt = matrix +0x34, bit 7 of +0xdc, CEntity::TeleportTo(mtx), changed 0, UpdateAiMapLoc slot +0x3c |
| 171 | 0x24efe0 | 100 | CZSealBody::TeleportTo(CPnt3D const*, CQuat const*) | gamez/zSeal/seal.cpp | MATCH | | pos set: m_alt = pos y and the flag; CEntity::TeleportTo(pos, rot), UpdateAiMapLoc slot +0x3c |
| 172 | 0x24f2a0 | 140 | CZSealBody::PostMortemPreTick(float) | gamez/zSeal/seal.cpp | MATCH | | network: +0xec5 RemoteRespawn(1), +0xec3 AdvancePiggyBack and return, +0xec4 RetreatPiggyBack; else +0xec5 DoRespawn |
| 173 | 0x24f4c0 | 172 | _rethrow_grenade(CValve*, void*) | gamez/zSeal/seal.cpp | MATCH | | NULL pickup or node returns; vel = (z.x * 150, 80, z.z * 150) from the node matrix row 2, SetVelW on m_data; the ELF's first-call guards store the statics' 80 / 150, the port's constant statics hold the same |
| 174 | 0x24f570 | 20 | CZSealBody::ResetToInitialState() | gamez/zSeal/seal.cpp | MATCH | | controller slot +0x58 tail call |
| 175 | 0x250f20 | 8 | CZSealBody::PrePostTick(float) | gamez/zSeal/seal.cpp | MATCH | | empty |
| 176 | 0x250f30 | 8 | CZSealBody::PostPreTick(float) | gamez/zSeal/seal.cpp | MATCH | | curChord 0 |
| 177 | 0x2557c0 | 168 | CZSealBody::CreateAiEvent() | gamez/zSeal/seal.cpp | MATCH | | Acquire to +0x380, m_type bits 1-15 = 3 (visible kept), NoExpire, rangeSq 0x38d1b717, pos = *GetPosW (slot +0xc), owner m_id, Create |
| 178 | 0x257710 | 8 | CZSealBody::GetRootPart() const | gamez/zSeal/seal.cpp | MATCH | | +0x26c |
| 179 | 0x257720 | 20 | CZSealBody::OnRecycleEntity(CEntity*) | gamez/zSeal/seal.cpp | MATCH | | controller slot +0x48 tail call, entity passed |
| 180 | 0x257740 | 76 | CZSealBody::OnMissionEnd() | gamez/zSeal/seal.cpp | MATCH | | m_id != invalidId: DestroyNetPickups(m_id & 0xff); controller slot +0x60 |
| 181 | 0x257790 | 60 | CZSealBody::OnMissionStart() | gamez/zSeal/seal.cpp | MATCH | | kit +0x520 PostSetupItems, controller slot +0x5c |
| 296 | 0x307870 | 172 | CVideo::Clear(unsigned char, unsigned char, unsigned char, unsigned char) | gamez/zVideo/zvid_video.cpp | DEFECT-FIXED | A | the ELF clears the render buffer: vramcode[4] = renderBuf (zVid +0x34, lwu) or 0xa0000, [14] = r, g << 8, b << 16, a << 24 with Q 1.0 in the high word, [18] = 0x1c002800, FlushCache(0), sceDmaSendN(zSys DmaToGif, vramcode, 10), sceDmaSync (0x307870-0x307908); the port body was empty: written. Called at mission complete / fade, the exit state and cinematics (the screen is cleared to black there) |
| 24 | 0x1c2860 | 44 | CZAnimMain::AnimSchedulerTick(float, void*) | gamez/zAnim/anim_main.cpp | MATCH | | NULL anim returns 1 (ELF test 0x1c2864), else CZAnim::Tick(dT) |
| 25 | 0x1c2890 | 192 | CZAnimNameIndexTable::Load(zar::CZAR&) | gamez/zAnim/anim_main.cpp | DEVIATION-KEPT | | GetOpenKey, Fetch count (4 bytes), > 0: _free(m_index, line 1623), 0 / 0, _realloc(count * 2, line 1656), Fetch "Name_Index_Table", m_count; returns 1: same. Kept (now commented): the count slot zeroed where the ELF leaves it unset, as audit-medium-anim-b recorded for CZAnim::Load |
| 26 | 0x1c2ad0 | 76 | CZAnimNameIndexTable::GetName(CZAnimSet*, int) | gamez/zAnim/anim_main.cpp | MATCH | | index < 0 or >= m_count NULL, set->GetName(m_index[index] lhu) |
| 27 | 0x1c2e20 | 156 | CZAnimNameTable::Unload() | gamez/zAnim/anim_main.cpp | DEFECT-FIXED | C | _free of each name (line 1495) and the table (1497), both 0 match; the loop compares signed (slt 0x1c2e7c, DWARF m_count sint), the port unsigned (the header's u32): written signed |
| 28 | 0x1c3060 | 56 | CZAnimNameTable::GetName(int) | gamez/zAnim/anim_main.cpp | MATCH | | index < 0 or >= m_count (signed) NULL, else m_name[index] |
| 29 | 0x1c3600 | 188 | CZAnimMain::SequenceExists(char const*) | gamez/zAnim/anim_main.cpp | DEVIATION-KEPT | | NULL name returns 0; m_CurSeq saved, walk from m_seq_data below data + size by seq_data_size, strcmp(GetName(name_index), name) == 0 returns 1, restored: same. Kept (now commented): the seqname NULL test the ELF lacks (0x1c3650), as audit-medium-anim-b recorded for the other walks |
| 30 | 0x1c36c0 | 188 | CZAnimMain::ResumeSequence(char const*) | gamez/zAnim/anim_main.cpp | DEVIATION-KEPT | | same walk; the first of that name gets paused (bit 0 of +4) cleared, walk stops, m_CurSeq restored: same. Kept (now commented): the seqname NULL test, as #29 |
| 31 | 0x1c3bd0 | 60 | CZAnimMain::SeqRunning() | gamez/zAnim/anim_main.cpp | MATCH | | state lbu +5 in 3, 4, 2 |
| 32 | 0x1c3c10 | 52 | CZAnimMain::StateRunning(int) | gamez/zAnim/anim_main.cpp | MATCH | | 3, 4, 2 true |
| 33 | 0x1c3c50 | 28 | CZAnimMain::SeqValid() | gamez/zAnim/anim_main.cpp | MATCH | | m_CurSeq < m_seq_data + m_seq_data_size (sltu) |
| 34 | 0x1c3c70 | 20 | CZAnimMain::SeqNext() | gamez/zAnim/anim_main.cpp | MATCH | | m_CurSeq += seq_data_size (+0xc) |
| 35 | 0x1c3c90 | 16 | CZAnimMain::SeqFirst() | gamez/zAnim/anim_main.cpp | MATCH | | m_CurSeq = m_CurAnim->m_seq_data |
| 36 | 0x1c4050 | 172 | CZAnimMain::SeqSetState(int) | gamez/zAnim/anim_main.cpp | MATCH | | NULL m_CurSeq returns; state sb +5, re-read: 5, 2, 1 clear paused bit 0 of +4, 4 / 3 not |
| 37 | 0x1c4100 | 48 | CZAnimMain::SeqSetName(char const*) | gamez/zAnim/anim_main.cpp | MATCH | | AddName on m_CurAnim, sh into name_index |
| 38 | 0x1c4210 | 92 | CZAnimMain::GetAnimSet(char const*) | gamez/zAnim/anim_main.cpp | MATCH | | GetAnimSetIndex(name, false), out of 0..count NULL, list + i * 48 |
| 39 | 0x1c4270 | 64 | CZAnimMain::GetAnimSet(int) | gamez/zAnim/anim_main.cpp | MATCH | | same range test, list + i * 48 |
| 40 | 0x1c42b0 | 136 | CZAnimMain::GetAnimIndex(CZAnim*, int*, int*) | gamez/zAnim/anim_main.cpp | MATCH | | m_animset_index bits 3-10 of +0x2c into *set_index, re-read, out of range NULL set (quirk kept), GetAnimIndex into *anim_index, >= 0 |
| 41 | 0x1c44d0 | 56 | CZAnimMain::GetAnim(int, int) | gamez/zAnim/anim_main.cpp | MATCH | | list + set * 48 (no range test), its address tested (0x1c44ec), Anim(anim_index) |
| 42 | 0x1c4620 | 196 | CZAnimMain::NewAnimSet(int) | gamez/zAnim/anim_main.cpp | MATCH | | while count <= index: _realloc((count + 1) * 48, line 727), memset 48, Init, Name("None"), count++; returns 1 |
| 43 | 0x1c49c0 | 24 | CZAnimMain::CmdValid() | gamez/zAnim/anim_main.cpp | MATCH | | cmd_pc < seq + seq_data_size (sltu) |
| 44 | 0x1c49e0 | 28 | CZAnimMain::CmdSet(int) | gamez/zAnim/anim_main.cpp | MATCH | | cmd_pc = seq + offset, cmd_state +6 = 2 |
| 45 | 0x1c4a00 | 32 | CZAnimMain::CmdNext(int) | gamez/zAnim/anim_main.cpp | MATCH | | cmd_pc += bytes, cmd_state 2 |
| 46 | 0x1c4a20 | 44 | CZAnimMain::CmdNext() | gamez/zAnim/anim_main.cpp | MATCH | | cmd_pc += header data_size (bits 2-15 of the halfword +2), cmd_state 2 |
| 47 | 0x1c4b50 | 192 | CZAnimMain::GetCmdEntry(char const*, bool) | gamez/zAnim/anim_main.cpp | DEFECT-FIXED | C | SplitName, GetCmdSet, _free(setname, line 480), the entry from the set and command bytes (12- and 24-byte records) match; GetCmd gets GetCmdSet's whole result (a1 = s0 0x1c4b9c), the port passed it & 0xff: passed whole, bytes only for the index |
| 48 | 0x1c4c10 | 64 | CZAnimMain::GetCmdEntry(unsigned short) | gamez/zAnim/anim_main.cpp | MATCH | | high byte the set, low byte the command |
| 49 | 0x1c4f90 | 156 | CZAnimMain::SplitName(char const*, char**) | gamez/zAnim/anim_main.cpp | MATCH | | NULL: *split NULL, returns 0; no "::": *split = name; else _strdup(line 343), cut at "::", *split past it, the copy returned |
| 50 | 0x1c5220 | 8 | CZAnimMain::OpenFile(char const*, char const*) | gamez/zAnim/anim_main.cpp | MATCH | | returns 0 |
| 51 | 0x1c5230 | 8 | CZAnimMain::AddPath(char const*) | gamez/zAnim/anim_main.cpp | MATCH | | empty |
| 52 | 0x1c5240 | 64 | CZAnimMain::FreeNetworkPacketBuffer() | gamez/zAnim/anim_main.cpp | MATCH | | _free(+0x1b4, line 159) and 0 when set, +0x1b8 0 |
| 53 | 0x1c5280 | 88 | CZAnimMain::GetNetworkPacket(int) | gamez/zAnim/anim_main.cpp | MATCH | | max < size (slt): _realloc(size, line 149), max = size; returns +0x1b4 |
| 54 | 0x1c52e0 | 92 | CZAnimMain::InvExp(float) | gamez/zAnim/anim_main.cpp | MATCH | | fptosi(40 * x), >= 41 -> 40, < 0 -> 0, m_inv_exp +0x110 |
| 55 | 0x1c5340 | 112 | CZAnimMain::Close() | gamez/zAnim/anim_main.cpp | DEFECT-FIXED | C | Unload, statics cleared, packet freed, max 0, m_IsOpen / m_IsStarted 0 match; the two _free tags are ("anim_main.cpp", 1898) and (159) (0x1c5360 / 0x1c5384), the port's zfree gave its own file / line: written as the ELF |
| 71 | 0x1ea1d0 | 36 | CAppCamera::ResetDeathCam() | gamez/zCamera/camera.cpp | MATCH | | +0x94 sb 0, +0x92 sb 1, save_short_tether_length 0x461c4000, DeltaRot / DeltaAim 0 |
| 72 | 0x1ea420 | 20 | CAppCamera::WiggleEcho(bool) | gamez/zCamera/camera.cpp | MATCH | | +0x88 sb echo, echo: +0x80 0 |
| 73 | 0x1ea440 | 52 | CAppCamera::WiggleScalar(float) | gamez/zCamera/camera.cpp | DEFECT-FIXED | C | no echo: +0x84 = w; echo: stored unless w <= scalar (c.le.s / bc1t 0x1ea458), the port scalar < w (differs for a NaN): written as the ELF |
| 74 | 0x1eb3f0 | 40 | CAppCamera::SetZoom(float) | gamez/zCamera/camera.cpp | MATCH | | camera +0x440 / +0x444 = zoom, +0x2b8 = 1 / zoom |
| 75 | 0x1eb740 | 96 | CAppCamera::~CAppCamera() | gamez/zCamera/camera.cpp | DEFECT-FIXED | C | +0x40, +0x3c, +0x38, +0x34 cleared match; the ELF clears m_track +0x8c first (0x1eb76c), the port did not: added |
| 76 | 0x1eb980 | 24 | CAppCamera::CmdTick3rdPersonTest(_zanim_cmd_hdr*, float*) | gamez/zCamera/camera.cpp | MATCH | | appCamera m_camera_mode +0x89 != 2 |
| 77 | 0x1eb9a0 | 108 | CAppCamera::CmdParse3rdPersonTest(_zrdr*) | gamez/zCamera/camera.cpp | DEFECT-FIXED | B | NULL reader returns NULL; the ELF's header gets data_size 4 (halfword +2 masked 0xffff0003, or 16) and timeless 1 (bit 1 of byte +2), quad_align left 0, from _calloc(1, 4, "camera.cpp", 421) (0x1eb9b4-0x1eb9fc); the port cleared both flags and left data_size 0 (a command that never advances), with zcalloc's tag: written as the ELF. Masked: the disc's anims load from ZAR, the text parser is not used |
| 78 | 0x1eba10 | 44 | CAppCamera::RegisterAnimCommands() | gamez/zCamera/camera.cpp | MATCH | | AddCmd(ZAnim, "CAMERA_3RD_PERSON", parse, NULL, tick (t0), NULL (t1)) |
| 279 | 0x3805f0 | 12 | CDblBufTextureRelocator::TakeDrawPacket(uint16*, unsigned int) | gamez/zUI/zui.cpp | MATCH | | tail call zSysFifoKick(packet, qwc) |
| 280 | 0x381680 | 132 | CGameMenu::TickMPEG() | gamez/zUI/zui.cpp | MATCH | | +0x245 and +0x244 set; Done: RunEventAnim(3 ONMPEGEND, NULL), +0x244 = Loop(); FifoEnd, FifoDisable, Tick(zVid renderBuf +0x34), FifoEnable(1) |
| 281 | 0x381710 | 120 | CGameMenu::RestartBackgroundMPEG() | gamez/zUI/zui.cpp | MATCH | | background and not running: FifoEnd, FifoDisable, +0x244 = Run(name, 1, 0) != 0, FifoEnable(1); the ELF's v0 is unread (port void, in the code) |
| 282 | 0x381790 | 72 | CGameMenu::HaltBackgroundMPEG() | gamez/zUI/zui.cpp | MATCH | | background and running: End, +0x244 0; the ELF's v0 1 / 0 has no caller (port void, in the code) |
| 283 | 0x383500 | 72 | CGameMenu::DrawForeplane() | gamez/zUI/zui.cpp | MATCH | | thePipe +0x630 = foreplane +0xc8, +0x63d 1, RenderUiNode(foreplane), +0x63d 0 |
| 284 | 0x383550 | 68 | CGameMenu::Draw2dOnly() | gamez/zUI/zui.cpp | MATCH | | thePipe +0x630 = backplane +0xc4, +0x63d 1, RenderUiNode(this = m_nodeTop), +0x63d 0 |
| 285 | 0x383b40 | 172 | CGameMenu::AddNode(C2D*, zdb::CTextureRelocMgr*) | gamez/zUI/zui.cpp | MATCH | | the inlined Add2dNode (#294) under the backplane +0xc4 |
| 286 | 0x3842b0 | 196 | ActionItem::operator=(ActionItem const&) | gamez/zUI/zui.cpp | DEFECT-FIXED | C | Type lb / sb, _free / _strdup tags 404-407, PadButton +0xd then State +0xc match; the ELF clears Animation and Argument after each free, before other's is read (0x3842e8 / 0x384328), so a self-assignment copies NULL where the port would _strdup a freed string: written as the ELF |
| 287 | 0x384540 | 8 | UiGetCurMenu() | gamez/zUI/zui.cpp | MATCH | | g_pCurMenu |
| 288 | 0x384550 | 12 | SetFaderOpacity(float) | gamez/zUI/zui.cpp | MATCH | | g_pFaderNode +0x9c = opacity, no NULL test |
| 289 | 0x384560 | 132 | PrepTexture(char const*, zdb::CTextureRelocMgr*) | gamez/zUI/zui.cpp | MATCH | | NULL name 0; GetTexHandle, NULL handle or texture +0xc 0; AddToBatch slot +0x8; the handle |
| 290 | 0x3845f0 | 60 | PlaySelectionSound() | gamez/zUI/zui.cpp | MATCH | | theGame +0x98 set: PlaySound slot +0x1c (1, NULL, 255) |
| 291 | 0x384630 | 56 | PlayCountSound() | gamez/zUI/zui.cpp | MATCH | | g_pTtySound set: PlaySound slot +0x1c (1, NULL, 255) |
| 292 | 0x3846f0 | 84 | InitButton(C2DButton*, zdb::CTexHandle*, zdb::CTexHandle*, zdb::CTexHandle*, zdb::CTexHandle*, char const*) | gamez/zUI/zui.cpp | MATCH | | the textures to +0x110 / +0xe4 / +0xb8 / +0x13c (t0 disabled), caption (t1) +0x1c; caption set: _strCaption (+0x20) slot +0x5c = C2DString::SetString (vt.py; the packet named another class's slot), UpdatePos |
| 293 | 0x384820 | 92 | GetStickDir() | gamez/zUI/zui.cpp | MATCH | | x < y (c.lt): x < -y 2 else 3; else x < -y 4 else 1 |
| 294 | 0x384e00 | 172 | Add2dNode(C2D*, zdb::CTextureRelocMgr*, zdb::CNode*) | gamez/zUI/zui.cpp | MATCH | | Create("Add2dNode"), new 112 C2DVisual(object, reloc), AddVisual, parent FindChild(node, 1) slot +0x28 (result unread), AddChild slot +0x18, node returned |
| 295 | 0x384eb0 | 48 | zUISchedulerClear() | gamez/zUI/zui.cpp | MATCH | | zUIScheduler Clear, ClearFreeList(1) |
| 16 | 0x403820 | 12 | CZHudMissionCams::IsPlaying() | Apps/FTS/hud/hud_missioncams.cpp | MATCH | | m_animhandle +0x20 != 0 |
| 17 | 0x403c10 | 64 | CZHudMissionCams::PlayCamera(char const*) | Apps/FTS/hud/hud_missioncams.cpp | MATCH | | theMission.GetMissionCamByIdentifier, non-NULL: PlayCamera(cam, 1) |
| 18 | 0x403c50 | 180 | CZHudMissionCams::Draw(zdb::CCamera*) | Apps/FTS/hud/hud_missioncams.cpp | MATCH | | m_animhandle set: Draw (slot +0xc) of the name +0x24, the three descriptions +0xac by 136, the cross text +0x2d0, the cross bitmap +0x250, in that order (member objects: the virtual and direct calls reach the same Draw) |
| 19 | 0x4040f0 | 124 | CZHudMissionCams::UnInit() | Apps/FTS/hud/hud_missioncams.cpp | MATCH | | slot +0x78 on the three descriptions, the name, the cross text: C2DString::ClearAndWipe for all (vt.py; the packet named C2D::Off for two) |
| 20 | 0x4042c0 | 180 | CZHudMissionCams::~CZHudMissionCams() | Apps/FTS/hud/hud_missioncams.cpp | MATCH | | members destroyed cross text, cross bitmap, descriptions (__destroy_arr 3 x 136), name, then C2D: the port's implicit order |
| 14 | 0x3d5530 | 184 | CZDynamicRadioBitmap::Init(CHUD*) | Apps/FTS/hud/hud_actionbitmap.cpp | MATCH | | Off (slot +0x18), SetTrans(0) (slot +0x20), m_fade_limit 64, m_fade_dx 2, m_fade_enable 1, C2DBitmap::SetColor(color_base), the two GetTexHandle results to +0x80 / +0x84, parent +0x88 |
| 15 | 0x3d5e30 | 12 | CZActionBitmap::UnInit() | Apps/FTS/hud/hud_actionbitmap.cpp | MATCH | | tail call ClearAndWipe on ActionTxtrMachine_HUD +0x14 (m_action_string) |
| 21 | 0x3205c0 | 176 | CExitState::UnInit() | Apps/FTS/state/st_exit.cpp | MATCH | | CSnd::Close, zSysFifoEnd, sceGsSyncPath(0, 0), animfile CloseZAR and 0, m_menu deleting dtor (slot +0x8, a1 1) when set and 0, EmptyAssetRecycleBin, theUIVarManager.Reset, RemoveArchive("readerx.zar", "run/ui"), FlushHistory(1) |
| 22 | 0x3206d0 | 100 | CExitState::Tick(float) | Apps/FTS/state/st_exit.cpp | MATCH | | PostTick(dT, NULL), CInput::Tick, m_menu Tick and Draw2dOnly, zSysFifoEnd, zVid_Swap(1), returns 0 |
| 23 | 0x320a90 | 196 | CEntityItr::Advance() | Apps/FTS/state/st_exit.cpp | MATCH | | ++_it and _iIdx++ each step, end returns, else the entity when non-NULL with type lbu +0x10 == 2, again while none or team +0xc4 & 0x20000 |
| 56 | 0x1c5e70 | 108 | CZAnimSet::GarbageCollect() | gamez/zAnim/zanim_set.cpp | MATCH | | NULL list returns; each 96-byte anim GarbageCollect; the ELF's v0 1 is unread (port void, in the code) |
| 57 | 0x1c6300 | 144 | CZAnimSet::SaveNodeStates(_zanim_node_ref*) | gamez/zAnim/zanim_set.cpp | MATCH | | +0x28 NULL: new 48-byte CZAnimSetSave (four vectors); non-NULL: Add(ref) |
| 58 | 0x1c63b0 | 196 | CZAnimSet::SaveNodeStates() | gamez/zAnim/zanim_set.cpp | MATCH | | ZAnim +0x34 = this, +0x38 / +0x3c 0; each anim (range-tested) and its m_sibling_anim +0x5c chain SaveNodeStates(1) |
| 59 | 0x1c6480 | 168 | CZAnimSet::Reset() | gamez/zAnim/zanim_set.cpp | MATCH | | node states Reset, AnimEx list Reset when set, each anim (inline range test) Reset |
| 60 | 0x1c66e0 | 56 | CZAnimSet::Init() | gamez/zAnim/zanim_set.cpp | MATCH | | +0x0 / +0x1 0, +0x2 1, +0x4 and +0x10..+0x2c zero |
| 61 | 0x1c7ba0 | 60 | CZAnimSet::SIScript(int) | gamez/zAnim/zanim_set.cpp | MATCH | | < 0 or >= +0x10 NULL, else +0x14 + index * 20 |
| 62 | 0x1c7be0 | 100 | CZAnimSet::AddAnimEx(CZAnimEx*) | gamez/zAnim/zanim_set.cpp | MATCH | | +0x18 NULL: new 12-byte vector; Add(ex) |
| 63 | 0x1c7c50 | 8 | CZAnimSet::AddName(char const*) | gamez/zAnim/zanim_set.cpp | MATCH | | tail call m_name_table (+0x8) AddName |
| 64 | 0x1c7c60 | 8 | CZAnimSet::GetName(int) | gamez/zAnim/zanim_set.cpp | MATCH | | tail call m_name_table (+0x8) GetName |
| 65 | 0x1c7c70 | 148 | CZAnimSet::Anim(char const*) | gamez/zAnim/zanim_set.cpp | DEVIATION-KEPT | | NULL name NULL; each anim: strcasecmp(name, GetName()) == 0 returns it, else NULL: same. Kept (now commented): the animname NULL test the ELF lacks (0x1c7cb4), as the seqname tests audit-medium-anim-b kept |
| 66 | 0x1c7d10 | 60 | CZAnimSet::Anim(int) | gamez/zAnim/zanim_set.cpp | MATCH | | < 0 or >= count NULL, else list + index * 96 |
| 67 | 0x1c7d50 | 92 | CZAnimSet::Name(char const*) | gamez/zAnim/zanim_set.cpp | DEFECT-FIXED | C | old name freed, the copy stored match; the ELF's tags are ("zanim_set.cpp", 111) and (113) (0x1c7d74 / 0x1c7d90), the port's zfree / zstrdup gave its own file / line: written as the ELF |
| 68 | 0x1c7db0 | 72 | CZAnimSet::GetAnimIndex(CZAnim*) | gamez/zAnim/zanim_set.cpp | MATCH | | (anim - list) / 96 signed, < count returns it, else -1 (no lower bound, as the ELF) |
| 69 | 0x1c7fd0 | 36 | CZAnimSet::TaskScheduler() | gamez/zAnim/zanim_set.cpp | MATCH | | +0x2c, else &zTaskScheduler |
| 118 | 0x230700 | 148 | zdb::CAssetMgr::ReleaseLibRef(zdb::CAssetLib*) | gamez/zNode/node_assetlib.cpp | MATCH | | NULL returns; ref count +0x34 decremented, > 0 returns; m_assets remove(lib), m_cache_model (+0xc) 0, inserted at the recycle bin's end |
| 119 | 0x230c40 | 160 | zdb::CAssetList::FindLib(zdb::_RenderPhase) | gamez/zNode/node_assetlib.cpp | MATCH | | first library whose byte +0x2b equals phase & 0xff, else NULL |
| 120 | 0x230e70 | 160 | zdb::CAssetList::GetTexHandle(char const*) | gamez/zNode/node_assetlib.cpp | MATCH | | each library's m_textures (+0x10) GetHandle(name), the first non-NULL, else NULL |
| 121 | 0x231000 | 168 | zdb::CAssetLib::AddPalette(zdb::CTexPalette*, bool) | gamez/zNode/node_assetlib.cpp | DEFECT-FIXED | B | the duplicate test matches; the ELF appends (insert at data + size 0x231080), sets m_AssetLib (+0x8) and returns the palette (0x231088, NULL for a duplicate); the port inserted first and returned NULL: written as the ELF (the audit-medium-node lead). Masked: palettes are found by match, not position; HookupLib's order follows the list |
| 122 | 0x2316d0 | 120 | zdb::CAssetLib::RootName() | gamez/zNode/node_assetlib.cpp | MATCH | | from strlen - 1 down to 0, lb '/' or '\\' returns the name past it, else m_name |
| 93 | 0x206a70 | 188 | CZGrenadeState::CreateLocalGrenade(CZProjectile*) | gamez/zFTS/fts_net_grenade.cpp | MATCH | | zNetCreateObject(&index, 1, 2, 0, 0, 0, 0 in a1-t3; stack NULL, "ProjectileObject", m_NetStructIndexGrenadeObject) checked; nonzero -1, zNetGetObject NULL -1, memset 36 (sizeof 36), pProjectile +0x1c, index returned |
| 94 | 0x206b30 | 128 | CZGrenadeState::RemoteGrenadeDeletionCallback(int, int) | gamez/zFTS/fts_net_grenade.cpp | MATCH | | object unchecked (quirk), name lb +0xc == 'P', data NULL or own client returns, pProjectile and the list non-NULL: NetRemoveProjectile |
| 95 | 0x206bb0 | 48 | CZGrenadeState::RemoteGrenadePostUpdateCallback(int, int, int) | gamez/zFTS/fts_net_grenade.cpp | MATCH | | zNetGetObject only (the data load is dead) |
| 96 | 0x206be0 | 152 | CZGrenadeState::RemoteGrenadeUpdateCallback(int, int, int) | gamez/zFTS/fts_net_grenade.cpp | MATCH | | object, data, pProjectile, pThrower NULL tests; position / velocity copies, UpdateGrenade(&pos, &vel, lbu +0x18) |
| 97 | 0x206c80 | 156 | CZGrenadeState::RemoteGrenadeCreationCallback(int, int) | gamez/zFTS/fts_net_grenade.cpp | MATCH | | object, data NULL tests; pThrower / pProjectile 0, GetBodyFromObjectIndex(lbu +0x19), NULL returns; pThrower set, pProjectile = kit +0x520 FireGrenade(&pos, &vel) |
| 249 | 0x1dd870 | 176 | CZSIObject::GetRotFast(int, int, float, CQuat*) | gamez/zSoftImage/si_object.cpp | MATCH | | t < 0.5 (c.lt) key a else b, m_constRot bit 2 of +0x8 -> 0, the 16-byte quat m_rotations[key] copied to out, out returned |
| 250 | 0x1dddd0 | 76 | CZSIObject::~CZSIObject() | gamez/zSoftImage/si_object.cpp | MATCH | | numSiObject-- |
| 251 | 0x1de050 | 88 | CZSIObject::Initalize(CZSIScriptCommon*) | gamez/zSoftImage/si_object.cpp | MATCH | | NULL common returns 0; bits 1 and 2 of +0x8 cleared, +0x0 / +0x4 0, returns 1 |
| 182 | 0x2e51d0 | 32 | CAiSRush::SetTarget(CZSealBody*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | target m_id, else CEntity::invalidId, to +0x2c |
| 183 | 0x2e51f0 | 152 | CAiSRush::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | signal & 0xff: 0 SetStance(0) and +0x8 = -1.0; 3 bit 0 of +0xc cleared; 4 +0x2c invalidId; 1 / 2 nothing |
| 184 | 0x2e5750 | 120 | CAiSPathRecover::GetStatus() const | gamez/zSeal/seal_airesponse.cpp | MATCH | | +0x14: 0 INIT, 1 CREEP, 2 REGISTER, 3 REPLAN, 4 COMPLETE, else "" |
| 185 | 0x2e57d0 | 120 | CAiSPathRecover::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | 0 SetAiMode(4 CREEP); 3 bit 0 of +0xc cleared |
| 186 | 0x2e5d50 | 16 | CAiSFlee::CanAttack() const | gamez/zSeal/seal_airesponse.cpp | MATCH | | +0x14 != 2 |
| 187 | 0x2e5d60 | 72 | CAiSFlee::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | 4: +0x30 0, +0x28 sb 1 |
| 188 | 0x2e5db0 | 84 | CAiSTarget::Tick(float, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | setup bit 0 of +0xc clear returns 0; !(ctrl +0x330 < +0x8) (c.lt / bc1t) clears it; returns the bit |
| 189 | 0x2e5e10 | 108 | CAiSTarget::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | 0 SetAiMode(4); 3 ClearGoal(0) |
| 190 | 0x2e6520 | 144 | CAiSEvent::ComputeNextState(CAiSEvent::EVENT_STATE&, float) | gamez/zSeal/seal_airesponse.cpp | MATCH | | next 8; state 2: flags & 2 -> 3; 1: & 1 -> 2, else & 2 -> 3; 0 -> 1; +0x50 = wait, +0x54 = next, state = wait == 0 (c.eq) ? next : 7 |
| 191 | 0x2e65b0 | 8 | CAiSEvent::GetStatus() const | gamez/zSeal/seal_airesponse.cpp | MATCH | | tail call GetEventString(lb +0x28) |
| 192 | 0x2e65c0 | 8 | CAiSEvent::CanPursue(CSealCtrlAi*) const | gamez/zSeal/seal_airesponse.cpp | MATCH | | 0 |
| 193 | 0x2e65d0 | 44 | CAiSEvent::CanAttack() const | gamez/zSeal/seal_airesponse.cpp | MATCH | | !(flags & 4) and !(flags & 8) |
| 194 | 0x2e6870 | 180 | CAiSRestrained::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | body = ctrl ? ctrl->m_entity : NULL; 0 SetAiMode(2), team +0xc4 & 0x20000: flags or 1; 4 +0x28 0 |
| 195 | 0x2e6b70 | 180 | CAiSStunResponse::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | 0: +0x30 = 0 + 0.75 * (0x30000000 * rand) (product operands swapped only), courage goal +0x564 0; 1: goal = +0x52c; 4: +0x30 0 |
| 196 | 0x2e6e20 | 92 | CAiSCorpse::SetCorpse(CEntity*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | *GetPosW (slot +0xc) to +0x28..+0x30, m_id to +0x34 |
| 197 | 0x2e6e80 | 112 | CAiSCorpse::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | 4: CPnt3D::zero to +0x28, invalidId to +0x34 |
| 198 | 0x2e72c0 | 120 | CAiSHold::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | 0 / 3 ClearRoute; 1 ctrl +0x240 sb 0; 4 +0x28 -1 |
| 199 | 0x2e77e0 | 8 | delayed_dropitems(void*, void*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | tail call DropAllItems |
| 200 | 0x2e7de0 | 72 | CAiSNoAmmo::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | 4: +0x28 0 |
| 201 | 0x2e8580 | 8 | CAiSReload::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | gamez/zSeal/seal_airesponse.cpp | MATCH | | empty |
| 265 | 0x300bf0 | 32 | C2D::Enable(bool) | gamez/zTwoD/ztwod_main.cpp | MATCH | | bit 5 of +0x15 = enable & 1, others kept |
| 266 | 0x300c10 | 20 | C2D::IsOn() const | gamez/zTwoD/ztwod_main.cpp | MATCH | | bit 5 of +0x15 != 0 (a 1-bit field: == true is the same test) |
| 267 | 0x300c30 | 28 | C2D::On() | gamez/zTwoD/ztwod_main.cpp | MATCH | | bit 5 of +0x15 set |
| 268 | 0x300c50 | 32 | C2D::Off() | gamez/zTwoD/ztwod_main.cpp | MATCH | | bit 5 of +0x15 cleared |
| 269 | 0x300c70 | 160 | C2D::Draw(zdb::CCamera*) | gamez/zTwoD/ztwod_main.cpp | MATCH | | bit 5 clear returns; each child of the list: Draw(camera) slot +0xc through the vtable at +0xc |
| 270 | 0x300d10 | 116 | C2D::~C2D() | gamez/zTwoD/ztwod_main.cpp | MATCH | | vtable store, the child list's dtor, the deleting flag: the port's implicit chain |
| 79 | 0x1f2030 | 8 | CEntityCtrl::Tick(float) | gamez/zEntity/ent_control.cpp | MATCH | | returns 0 |
| 80 | 0x1f2040 | 8 | CEntityCtrl::PreTick(float) | gamez/zEntity/ent_control.cpp | MATCH | | returns 0 |
| 81 | 0x1f2050 | 76 | CEntityCtrl::~CEntityCtrl() | gamez/zEntity/ent_control.cpp | MATCH | | vtable store and the deleting flag only |
| 82 | 0x1f20a0 | 68 | CEntityCtrl::CEntityCtrl(int) | gamez/zEntity/ent_control.cpp | DEFECT-FIXED | C | vtable, m_entity +0x4 0 match; the ELF clears m_throttle with memset(+0x8, 0, 12) (0x1f20c8), the port with three float stores (the same bits): written as the ELF |
| 123 | 0x238a70 | 116 | Particle::Source::RenderBBox() | gamez/zParticle/zparticle_source.cpp | MATCH | | each listed source GetBBox into a stack box, unused |
| 124 | 0x239400 | 12 | Particle::Source::Reset() | gamez/zParticle/zparticle_source.cpp | MATCH | | +0x128 sb 1 |
| 125 | 0x239410 | 112 | Particle::Source::SetActive(bool) | gamez/zParticle/zparticle_source.cpp | MATCH | | unchanged returns; +0x0 = active; +0x11c set: m_diNode SetActive(active) slot +0x34; on: +0x128 0, off: +0x1 0 |
| 126 | 0x23a580 | 112 | Particle::Source::ScaleSequenceAdd(float, float) | gamez/zParticle/zparticle_source.cpp | MATCH | | m_props = Branch(), {fraction, scale} inserted at the scale sequence's end |
| 127 | 0x23a5f0 | 56 | Particle::Source::ScaleSequenceClear() | gamez/zParticle/zparticle_source.cpp | MATCH | | Branch, the scale sequence (+0x1c) clear |
| 128 | 0x23a700 | 56 | Particle::Source::ColorSequenceClear() | gamez/zParticle/zparticle_source.cpp | MATCH | | Branch, the colour sequence (+0x10) clear |
| 129 | 0x23a740 | 120 | Particle::Source::TextureSequenceAdd(float, zdb::CTexHandle*) | gamez/zParticle/zparticle_source.cpp | MATCH | | Branch, {fraction, texture} at the texture sequence's end, AddDynTexture(texture) |
| 130 | 0x23a7c0 | 56 | Particle::Source::TextureSequenceClear() | gamez/zParticle/zparticle_source.cpp | MATCH | | Branch, the texture sequence (+0x4) clear |
| 131 | 0x23a800 | 84 | Particle::Source::TexturesAdd(zdb::CTexHandle*) | gamez/zParticle/zparticle_source.cpp | MATCH | | inserted at m_textures' end (+0xd8), AddDynTexture |
| 132 | 0x23aa00 | 8 | Particle::Source::TexturesClear() | gamez/zParticle/zparticle_source.cpp | MATCH | | m_textures size +0xdc 0 |
| 133 | 0x23aa10 | 92 | Particle::Source::Create() | gamez/zParticle/zparticle_source.cpp | MATCH | | new 308, Source(), inserted at the list's end, returned |
| 134 | 0x23aa70 | 172 | Particle::Source::List::Uninit() | gamez/zParticle/zparticle_source.cpp | DEVIATION-KEPT | | each source's deleting dtor, then erase(begin, end): same. Kept (now commented): the ELF reads the next node from the node after the delete (0x23aac8), which ~Source has unlisted and freed; the port takes it before |
| 252 | 0x1de280 | 88 | CZSIScript::SetFrameRate(float) | gamez/zSoftImage/si_script.cpp | DEFECT-FIXED | C | time = (f32)m_nFrames (lh) / rate, m_isLoaded bit 0 match; the store is skipped when time <= 0 (c.le.s / bc1t 0x1de2bc), the port tested time > 0 (differs for a NaN): written as the ELF |
| 253 | 0x1de2e0 | 56 | CZSIScript::SetLoopTime(float) | gamez/zSoftImage/si_script.cpp | DEFECT-FIXED | C | as #252: !(time <= 0) (0x1de2fc) |
| 254 | 0x1deb50 | 36 | CZSIScript::ReadIt(zar::CZAR&, int, void*) | gamez/zSoftImage/si_script.cpp | MATCH | | tail call of script's Read(archive, size) through its vtable slot +0xc (the port's virtual call) |
| 255 | 0x1debf0 | 168 | CZSIScript::Share(CZSIScript*) | gamez/zSoftImage/si_script.cpp | DEFECT-FIXED | C | NULL returns 0; m_isLoaded set, common shared and its ref count (lh / sh) ++, m_tScale, distance when objects_ready == 0, m_multiplier, returns 1 match; the m_tf copy tests !(other m_tf <= 0) (0x1dec4c), the port > 0: written as the ELF |
| 135 | 0x23f6e0 | 120 | CFileStack::pop(bool) | gamez/zReader/zrdr_parse.cpp | MATCH | | non-empty: the front element (node +0x8) Close (slot +0xc) or CBufferIO::Release, then erase(begin) (the earlier fix holds) |
| 70 | 0x1d8130 | 108 | zar::CKey::~CKey() | gamez/zArchive/zarchive_holding.cpp | DEFECT-FIXED | C | the ELF runs only the key ring's list dtor and the deleting flag (0x1d8164); the port called clear() first (the same effect): removed |
| 98 | 0x20f650 | 112 | CGNode::SetName(char const*) | gamez/zGraph/graph_node.cpp | MATCH | | _free(name, line 51) when set, 0, name ? _strdup(line 52) : NULL |
| 99 | 0x20f6c0 | 188 | CGNode::~CGNode() | gamez/zGraph/graph_node.cpp | MATCH | | _free(name, line 38) when set, 0, m_edges erase(begin, end) (clear), the list dtor, deleting flag |
| 100 | 0x20f780 | 76 | CGNode::CGNode(char const*) | gamez/zGraph/graph_node.cpp | MATCH | | +0x4 / +0x8 / +0xc 0, the edge list ctor, +0x1c 0, +0x20 0; the name unused (quirk kept) |
| 11 | 0x320590 | 16 | CameraZoom::SetGoal(float) | Apps/FTS/game/thezoom.cpp | MATCH | | m_goal = goal, m_isGoalHit sb 1 |
| 12 | 0x3205a0 | 8 | CameraZoom::AttachHud(CHUD*) | Apps/FTS/game/thezoom.cpp | MATCH | | m_hud = hud |
| 13 | 0x3205b0 | 8 | CameraZoom::AttachSeal(CZSealBody*) | Apps/FTS/game/thezoom.cpp | MATCH | | m_seal = seal |
| 110 | 0x222460 | 40 | CMatrix::CMatrix() | gamez/zMath/zmath_holding.cpp | MATCH | | sceVu0UnitMatrix(this): the live definition is the inline in zmath.h line 350 (the same call); the packet showed the #if 0 held copy |
| 111 | 0x233db0 | 8 | CMatrix::GetTranslate() const | gamez/zMath/zmath_holding.cpp | MATCH | | this + 0x30: the inline in zmath.h line 357 (the held copy is #if 0) |
| 112 | 0x222cb0 | 144 | CPnt3D::Normalize(CPnt3D*) const | gamez/zMath/zmath_pnt3d.cpp | MATCH | | length = sqrtf(x x + y y + z z), length == 0 (c.eq) leaves other alone, else inv = 1 / length, components times inv into other; length returned in $f0 |
| 113 | 0x222d40 | 132 | CPnt3D::Normalize() | gamez/zMath/zmath_pnt3d.cpp | MATCH | | as #112 in place |
| 114 | 0x222dd0 | 40 | CPnt3D::Scale(float, CPnt3D*) const | gamez/zMath/zmath_pnt3d.cpp | MATCH | | each component * scale into out |
| 115 | 0x222e00 | 28 | CPnt3D::ToRightXZ(CPnt3D*) const | gamez/zMath/zmath_pnt3d.cpp | MATCH | | out = (-z, 0, x) |
| 116 | 0x222e20 | 36 | CPnt3D::SubXZ(CPnt3D const*, CPnt3D*) const | gamez/zMath/zmath_pnt3d.cpp | MATCH | | x and z differences only, this - other |
| 117 | 0x222e50 | 52 | CPnt3D::Sub(CPnt3D const*, CPnt3D*) const | gamez/zMath/zmath_pnt3d.cpp | MATCH | | this - other per component |
| 256 | 0x2f9ab0 | 100 | zdb::CBatchRelocator::ClearAll() | gamez/zTexture/ztexture_holding.cpp | MATCH | | buffer m_texmanager[0]: the two dyn-tex lists (+0x28, +0x34) and the packet buffer (+0x1c) cleared in that order, _free(name, "ztex_manager.cpp", 88) when set, name 0 |
| 257 | 0x2f9b20 | 72 | zdb::CBatchRelocator::AddToBatch(zdb::CTexHandle*) const | gamez/zTexture/ztexture_holding.cpp | MATCH | | buffer 0's dyn-tex list (+0x28) Add(handle, 1), m_chainp +0x18 0 |
