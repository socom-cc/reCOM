# Audit of list small-g (2026-11-20, socom-port-audit-small-g)

296 small functions (24,828 bytes, each under 200 bytes) in 30 files: Apps/FTS (database,
hud_bitmapreticule, hud_ingame_weaponsel), zAI (ai_mapdata, ai_mapwalk, zai_holding), zAnim
zanim_cmd_parse, zBone bone_init, zEntity zentity_holding, zFTS (fts_mission, fts_net_bomb,
fts_player), zMPEG playpss, zMath zmath_matrix, zNode (node_model, node_wave, znode_holding),
zReader zrdr_edit, zSeal (seal_body, seal_command, seal_control, seal_kit), zSystem zsys_init,
zTexture (ztex_manager, ztex_read), zTwoD (ztwod_bitmap, ztwod_font), zUtil util_sonyio, zWeapon
(zwep_explosive, zwep_projectilelist). HEAD c182c48f. Judged file by file in the scan's rank order,
from the by-file packets.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 277 |
| DEFECT-FIXED | 18 (A 6, B 1, C 11) |
| DEVIATION-KEPT | 1 |
| UNJUDGED | 0 |

Defect rate 18 / 296 (A 6, B 1, C 11).

Fixes:
- A, #80-#85 the HUD anim commands HUD_ON / HUD_OFF / HUD_LETTERBOX_ON / HUD_LETTERBOX_OFF
  (registered by CMission, fts_mission.cpp 790-793): the three parsers and two ticks were stubs
  returning NULL / false, so the commands were dropped. Written from the ELF: 8-byte timeless
  records with an on bit (byte +4 bit 0) or off bit (bit 1), _calloc tags ("fts_mission.cpp",
  843 / 859 / 899 / 915); the ticks call CHUD::On / Off or theHUD +0x14280 m_letterbox Add /
  RemoveLetterbox and return 1 (0x1f9af0-0x1f9dd4). Whether m8's scripts use them is not known.
- B, #48 zBoneClose: the ELF tail-calls boneArchive's CZAR::Close (0x1dd674); the port was a stub,
  motion.zar stayed open across missions.
- C, #123 CStack::Multiply: multiplies from m_top - 1 in place (0x221e00), no local copy.
- C, #168 ~CObjAnims: clear() before the swap (0x27d5c4).
- C, #53 CMission::TickInFirefight: the player from ftsGetPlayer() (0x1f2b4c).
- C, #252 InterruptDmacBusError: the ELF's text ("you friendly neighborhood", 0x458a90), break /
  sync / ei and 0 (0x2f52a0), not abort().
- C, #182 CSealCtrl::GetThrowAverage: reading[i] <= reading[last] as the ELF tests it (0x2844c8).
- C, #232 CZKit::CanChangeItem: !(m_firetime <= 0) as the ELF tests it (0x2acc20).
- C, #36 zAnimLoadTimer: _calloc tag ("zanim_cmd_parse.cpp", 4637) (0x1aae4c), not __FILE__.
- C, #2 / #3 BitmapReticule::Off / On: tail calls of C2D::Off / On (0x3ce4c0 / 0x3ce4d0).
- C, #287 CZProjectileList::GetNextIndirectFireDI: the bound test reads m_direct_firstfree
  (0x31a6a4, an ELF quirk now kept), not the indirect one.
- C, #260 C2DBitmap::TickFade: the fade-down clamp tests alpha < limit, then alpha < 0
  (0x303118 / 0x303130).

Kept deviations: #209 CZKit::FillWeaponEnum stores NULL where the ELF stores m_item[-1] (+0xcc,
m_itemstate[29], not a weapon) for slot -1; recorded by an earlier worker, the reason added to its
comment. Port spellings already recorded and kept: Vu0MatrixInverseWithUniformScale's aligned
locals, GetCustomCharTypeName's own copy of the name table, ftsPlayer as the body with a separate
ftsPlayerCount (ftsSetPlayerCount, CftsPlayer::IsInside), CFileIO's separate m_cd, CFileIO::fwrite's
0 on a CD boot, CRdrEditor's by-value stack, the port-only trace lines (SOCOM_PORT_TRACE).

ELF quirks kept: IsSelected's always-true test of &m_listWeapons; SetMovingChangeToRifle's two
stores of m_flags; CurWeaponIsM203Mode's double unwrap; ItemHasAmmo(EQUIP_ITEM)'s test of slot -1;
GetFiremodeGraphic's read at the unwrapped index; ComputeLineVisibility's unbounded shadow_scale
index; the IF / ELSE / ELSEIF / ENDIF parsers' writes through a NULL record; GetNextIndirectFireDI's
direct-list bound; GetLocation's second NULL test.

Leads for other lists: none.

What the packets lacked: #10 mem.py gave C2DBitmap's array element offsets wrongly ("[0] +256");
dw.py gave the 128-byte size (m_weaponicon[2] is +0x120). #4 BitmapReticule::UnInit's slot +0x78
was named C2D::Off (vt.py 0x472cb0: C2DString::ClearAndWipe). #30 _saturate's bounds showed as ''
strings (0x474d70 / 74, read from the ELF: 0, 1). #19 / #21 / #24 FindByLocation's body (the
source). #48 what Close frees and whether the scripts keep pointers into the archive (zar_main.cpp,
si_script.cpp). #81-#85 the HUD's member offsets (mem.py CHUD) and the command registrations.
About 14 functions needed a lookup outside the packet.

Runs: the default build links (audit-small-g-default). Smoke: gate.ps1 -Only roundtrip on this tree PASS (4 returns, in use 18,642,780 B flat; 486 s).

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 127 | 0x2223d0 | 140 | CMatrix::SetRows(CPnt3D const*, CPnt3D const*, CPnt3D const*, CPnt3D const*) | zmath_matrix.cpp | MATCH | - | each row NULL-tested (beqz), memcpy 12 bytes to +0, +16, +32, +48 (the scan's byte stores are GCC's inlined memcpy) |
| 125 | 0x221f90 | 164 | Vu0MatrixInverseWithUniformScale(CMatrix*, CMatrix*) | zmath_matrix.cpp | MATCH | - | the VU0 macro sequence instruction by instruction (vdiv by row 0's squared length, transposed 3x3 * Q, w by vf0.y, translation vsub); the 16-byte aligned local copies are the recorded port spelling (comment in the code) |
| 126 | 0x222360 | 104 | CMatrix::CMatrix(float x16) | zmath_matrix.cpp | MATCH | - | the 16 stores +0x0..+0x3c in order, this returned |
| 123 | 0x221dd0 | 92 | CStack::Multiply(CMatrix const*, bool) | zmath_matrix.cpp | DEFECT-FIXED | C | other: m_top += 1 matrix, m_pointer++, sceVu0MulMatrix(m_top, m_top - 1, matrix) (addiu a1,a0,-64 0x221e00); else (m_top, m_top, matrix); m_top returned. The port copied *m_top into a local first and multiplied from the copy (same values); now m_top - 1 in place |
| 124 | 0x221f80 | 12 | CMatrix::SetZero() | zmath_matrix.cpp | MATCH | - | memset(this, 0, 64) tail |
| 10 | 0x3fb040 | 192 | CInGameWeaponSel::AfterCloseFirst() | hud_ingame_weaponsel.cpp | MATCH | - | goal = (2 + (32 + y1)) - (y1 - 1) (operands swapped in commutative adds only), cur = goal, centery = goal / 2, goaly / goalx from [1], startx 0, openstate 7 in that order; slot +0x18 Off on m_weaponicon[0] (+0x20), m_selectionback[0] (+0x460), [2] (+0x120), [2] (+0x560) (C2DBitmap 128 bytes) |
| 7 | 0x3f80c0 | 176 | CInGameWeaponSel::IsSelected(int) | hud_ingame_weaponsel.cpp | MATCH | - | 6 slots +0x114c (lbu), 255 skipped, GetWeaponByIndex(&m_listWeapons, index), NULL skipped, slot == m_ID +0x60 (lbu) -> 1, else 0; the ELF's test of &m_listWeapons != NULL (0x3f80e8) is always true |
| 8 | 0x3f98d0 | 96 | CInGameWeaponSel::Increment(float, float, float) | hud_ingame_weaponsel.cpp | MATCH | - | val < goal (c.lt.s): val + inc, <= goal (c.le.s) kept else goal; !(val <= goal): val - inc, < goal -> goal; else val |
| 9 | 0x3fa760 | 96 | CInGameWeaponSel::RePackEquipment() | hud_ingame_weaponsel.cpp | MATCH | - | slots 2..5 == 255: j = i..4 slot[j] = slot[j + 1], slot 5 (+0x1151) = 255 |
| 152 | 0x274030 | 192 | CZSealBody::DropBody() | seal_body.cpp | MATCH | - | m_state (lb) != 9 exits; m_carry NULL skips to m_carry = NULL; DetachBody, Top, pop while m_top + 1 >= 2, last blend m_ctrl 0, m_desiredPeek 2, PushBlend(FallForward01, 8, false), m_inAirHorizVel = m_velW (xyz) |
| 154 | 0x2750d0 | 148 | CZSealBody::BeginThrowItem(float, float&) | seal_body.cpp | MATCH | - | frac / offset 0; GetThrowAnim(power, anim, frac, offset, release) a1-t0; PushBlend(anim, m_state lb, false); firetime = offset + frac * TrueLoopTime (mul.s then add.s); 1 / 0; the GREN trace is port-only (SOCOM_PORT_TRACE) |
| 155 | 0x2768a0 | 180 | CZSealBody::Stand(int) | seal_body.cpp | MATCH | - | Top; m_state (lb) 0 or top +0x2f 0 exits; Top again, pop while m_top + 1 >= 2, m_ctrl 0, m_desiredPeek 2, Stand_0(state, arg) |
| 151 | 0x273800 | 132 | CZSealBody::LowerBinoculars() | seal_body.cpp | MATCH | - | Top m_ctrl (lb) 2 and m_animType (lh +0x30) 59 / 60 / 61, else NULL; PopBlend, its m_ctrl 0, m_lookitem Clear, the popped blend returned |
| 156 | 0x2772d0 | 48 | CZSealBody::StanceChanged() | seal_body.cpp | MATCH | - | bit 0 of +0xf5b tested, cleared (others kept), 1; else 0 |
| 158 | 0x27b960 | 68 | CZSealBody::SetMovingChangeToPistol(ACTIVE_ANIM*) | seal_body.cpp | MATCH | - | m_airborne bit 5 of +0xf5a -> -4 else 0; overlay +0x118: m_anim, m_triggerT, m_ovlyT 0, m_state (sh) 0, m_event 4 (the scan's S4 at +0xc is GCC merging the two halves) |
| 159 | 0x27b9b0 | 156 | CZSealBody::SetMovingChangeToRifle(ACTIVE_ANIM*) | seal_body.cpp | MATCH | - | trigger as #158; m_ovlyT = m_anim TrueLoopTime, m_state 0, m_event 3; m_flags & 0xff7f then \| 0x80 (the ELF stores both steps; the port's one store gives the same final halfword with nothing between) |
| 160 | 0x27ba50 | 36 | CZSealBody::SetMovingPistolReload(ACTIVE_ANIM*) | seal_body.cpp | MATCH | - | m_anim, -4, 0, m_state 0, m_event 2 |
| 161 | 0x27ba80 | 36 | CZSealBody::SetMovingRifleReload(ACTIVE_ANIM*) | seal_body.cpp | MATCH | - | m_anim, -4, 0, m_state 0, m_event 1 |
| 164 | 0x27d1c0 | 128 | CZSealBody::ClearStack(unsigned int, bool) | seal_body.cpp | MATCH | - | Top, pop while depth < m_top + 1 (sltu), reset: blend m_ctrl 0 when non-NULL, m_desiredPeek 2 |
| 145 | 0x26fdb0 | 144 | CrouchToPickupBuddyCallback(void*, void*) | seal_body.cpp | MATCH | - | NULL seal exits; the ELF's inline loop pops while m_top + 1 >= 3, m_ctrl 0, m_desiredPeek 2 (= ClearStack(2, true)); CrouchToPickupBuddy(buddy) |
| 148 | 0x272dc0 | 148 | CZSealBody::PerformAction(AnimType, SEAL_STATE) | seal_body.cpp | MATCH | - | lh +0x464 == (s16)BaseAnim(type) -> Top, else PushBlend(type, (u8)state, false) |
| 153 | 0x2743f0 | 88 | CZSealBody::DoWallStop() | seal_body.cpp | MATCH | - | m_control +0x168 bit 2 m_action (read before the NULL test, as the port) -> 0; NULL control -> 1; slot +0x30 IsAi, !ai |
| 157 | 0x27a1b0 | 152 | CZSealBody::CanCrouch() | seal_body.cpp | MATCH | - | AnimId(18) and AnimId(87) >= 0; m_inwater bit 7 of +0xf5a clear -> 1; m_waterdepth +0xe70 <= 8.5 (c.le.s) |
| 165 | 0x27d240 | 88 | CZSealBody::BodySetState(int) | seal_body.cpp | MATCH | - | state != m_state (lb): m_control slot +0x64 OnStateChange((u8)m_state, (u8)state); CBody::BodySetState (this + 0x110, state) |
| 147 | 0x270cc0 | 72 | CZSealBody::UseVelY() | seal_body.cpp | MATCH | - | Top, Representative, m_flags (lhu +0x1e) & 8 as bool |
| 149 | 0x2735f0 | 108 | CZSealBody::BaseState() | seal_body.cpp | MATCH | - | m_top down to 0: stack[i] +0x2f state 0 / 1 / 2 returned; none -> 0 |
| 150 | 0x273660 | 84 | CZSealBody::PeekBaseState() | seal_body.cpp | MATCH | - | m_top down: first +0x2f != 3 returned; none -> 0 |
| 162 | 0x27bfd0 | 124 | CZSealBody::CanTurn() | seal_body.cpp | MATCH | - | Top +0x34 m_anims Begin; along ACTIVE_ANIM +0xc m_overlay, turn = m_anim m_flags & 0x1000 (the last decides) |
| 166 | 0x27d3e0 | 152 | CZSealBody::GetSpeedState() | seal_body.cpp | MATCH | - | sqrtf(x*x + y*y + z*z) of m_velM (mul, adda, madd order); m_state != 0 -> 0; < 0.5 -> 1, < 20 -> 2, else 3 (c.lt.s) |
| 142 | 0x26e990 | 88 | CZSealBody::AdrenalineIncr(float) | seal_body.cpp | MATCH | - | NULL -> 1 (exits); 1 == value (c.eq.s) exits; value + incr, <= 1 (c.le.s) else 1, stored |
| 143 | 0x26e9f0 | 8 | CZSealBody::Adrenaline() | seal_body.cpp | MATCH | - | lw +0xdac returned |
| 144 | 0x26f0e0 | 8 | RestoreCameraPosition(void*, void*) | seal_body.cpp | MATCH | - | empty |
| 146 | 0x26fe40 | 8 | PickupBuddyCallback(void*, void*) | seal_body.cpp | MATCH | - | tail PickupBuddy(buddy) |
| 163 | 0x27c050 | 60 | CZSealBody::IsCurrentBlend(AnimType) const | seal_body.cpp | MATCH | - | lh +0x464 == (s16)BaseAnim(type) |
| 167 | 0x27d510 | 72 | CObjAnims::GetObjAnim(int) | seal_body.cpp | MATCH | - | data_ to data_ + size_: entry +0x0 part, lh +0x24 id == id -> entry; else NULL |
| 168 | 0x27d560 | 192 | CObjAnims::~CObjAnims() | seal_body.cpp | DEFECT-FIXED | C | each entry deleted; the ELF sets size_ 0 (clear(), sw 0x27d5c4) before the swap with an empty vector; the port swapped without the clear (same effect); clear() added |
| 70 | 0x1f5ff0 | 160 | CMission::FadeToEndMission(float, int) | fts_mission.cpp | MATCH | - | theNetwork +0x9 set exits; first call: +0x71 1, theMission +0x70 m_DelayEndMission 1, +0x74 flashes, +0x78 delay, AddTask("MissionFadeToEnd", fadeToEndMissionTick, 0.98f 0x3f7ae148, this); later: delay < next (c.lt.s), flashes < counter (slt) stored; the trace is port-only |
| 53 | 0x1f2b30 | 192 | CMission::TickInFirefight(float) | fts_mission.cpp | DEFECT-FIXED | C | the ELF takes the player from ftsGetPlayer() (jal 0x1f2b4c); the port read the global ftsPlayer (same value); now the call. aware > 0 (blez): timer == 0 (c.eq.s) -> IsInFight(1), timer 4; else timer != 0: -= dT, <= 0 (c.le.s) -> 0, IsInFight(0) agree |
| 68 | 0x1f4000 | 132 | CZNetGame::UnInitialize() | fts_mission.cpp | MATCH | - | the 31 stores in the ELF's order and widths, m_net_start_flag 1 |
| 61 | 0x1f37d0 | 132 | CMission::GetGameTime() | fts_mission.cpp | MATCH | - | theNetwork +0x9 and m_pNetGame: (f32)(u32)m_clock.m_game_time * 0.001f (0x3a83126f), fptoui; else fptosi(+0x68 m_winlosstimer) |
| 54 | 0x1f2bf0 | 172 | CMission::GetMissionCamByIdentifier(char const*) | fts_mission.cpp | MATCH | - | m_missioncams (+0x5b4) begin to end: node +0x8 cam, NULL skipped, strcmp(cam +0x0 m_identifier (char*), id) == 0 -> cam; NULL |
| 55 | 0x1f3460 | 192 | CMission::UnSerialize(char const*, CRdrFile*, int) | fts_mission.cpp | MATCH | - | zrdr_findint(reader, "state", +0x18, 1); "database" NULL exits; SetDatabase, atoi(db + 1), Create("CurrentMission", 1), m_value (lhu) != n -> n ? 1 : 2, sh n, MakeCallbacks, PreOpen(db) |
| 56 | 0x1f3520 | 140 | CMission::Serialize(int) | fts_mission.cpp | MATCH | - | CRdrEditor; push(NULL), addint("state", lbu +0x18), addSTRING("database", GetDatabase()), pop, SaveRdr(this, "MissionData", &rdr), dtor |
| 58 | 0x1f3710 | 156 | CNetClock::Tick() | fts_mission.cpp | MATCH | - | +0x1c and +0x1d set: now = zNetGetTime() - +0x18; initial < now (sltu) -> now - initial else 1 into +0xc; max != 0: t < max ? max - t : 0, else t into +0x10 |
| 63 | 0x1f3d50 | 112 | CZNetGame::LateJoiner(bool) | fts_mission.cpp | MATCH | - | +0x94 = late; valve +0x28 m_value (lhu) vs late ? 1 : 0, change 1 / 2, sh, MakeCallbacks; late returned |
| 64 | 0x1f3dc0 | 92 | CZNetGame::MyMinorGameState(CZNetGame::MP_MINOR_GAME_STATE) | fts_mission.cpp | MATCH | - | +0xdd, valve +0x20 with (u8)state, change rule, returned |
| 65 | 0x1f3e20 | 92 | CZNetGame::MyMajorGameState(CZNetGame::MP_MAJOR_GAME_STATE) | fts_mission.cpp | MATCH | - | +0xdc, valve +0x1c with (u8)state, change rule, returned |
| 67 | 0x1f3fb0 | 72 | CZNetGame::SetE3RoundCount(int) | fts_mission.cpp | MATCH | - | +0xe4, valve +0x8 m_value (16 bits) vs count (32), change rule, sh count |
| 69 | 0x1f5bf0 | 76 | CLadderList::GetLadderByIndex(int) | fts_mission.cpp | MATCH | - | index & ~LADDER_MASK (the variable), < 0 or >= size_ (sltu) NULL, data_ + 40 * index |
| 52 | 0x1f2a10 | 16 | CMission::RecoverFromNetError(int) | fts_mission.cpp | MATCH | - | tail theMission._RecoverFromNetError(error) |
| 57 | 0x1f35b0 | 28 | CZNetGame::OnSealTeam() | fts_mission.cpp | MATCH | - | +0x90 & 0x40000001 as 0 / 1 |
| 59 | 0x1f37b0 | 12 | CNetClock::SetInitialRead(unsigned int, bool) | fts_mission.cpp | MATCH | - | sw +0x8, sb +0x1c |
| 60 | 0x1f37c0 | 8 | CZNetGame::SetE3Index(int) | fts_mission.cpp | MATCH | - | sw +0xf4 |
| 62 | 0x1f3d30 | 28 | CZNetGame::ResetScores() | fts_mission.cpp | MATCH | - | +0xe4, +0xf0, +0xec 0, +0xe8 64, +0x9b 0 in that order |
| 66 | 0x1f3e80 | 12 | CZNetGame::MPMajorGameState(CZNetGame::MP_MAJOR_GAME_STATE) | fts_mission.cpp | MATCH | - | sb +0xdb, returned |
| 71 | 0x1f6090 | 8 | CMission::fadeToEndMissionTick(float, void*) | fts_mission.cpp | MATCH | - | tail FadeToEndMissionTick(dT) on the registrar |
| 72 | 0x1f65d0 | 8 | CMission::DestroyNetGame() | fts_mission.cpp | MATCH | - | tail m_pNetGame->UnInitialize() |
| 73 | 0x1f65e0 | 44 | CMission::CreateNetGame() | fts_mission.cpp | MATCH | - | m_pNetGame Initialize, m_pNetGame reloaded and returned |
| 74 | 0x1f6fa0 | 32 | CMission::tick(float, void*) | fts_mission.cpp | MATCH | - | Tick(dT) on the registrar, 0 |
| 81 | 0x1f9b60 | 124 | HUDLetterBoxCmdParseOff(_zrdr*) | fts_mission.cpp | DEFECT-FIXED | A | the port was a stub returning NULL (the command dropped); the ELF: NULL reader -> NULL, _calloc(1, 8, "fts_mission.cpp", 915), data_size 8 (\| 32 into the halfword +2), timeless (bit 1 of +2), off bit 1 of +4 (0x1f9bc0-0x1f9bcc). Written; the record is a port struct (no DWARF). Whether m8's scripts use the command is not known |
| 82 | 0x1f9be0 | 132 | HUDLetterBoxCmdParseOn(_zrdr*) | fts_mission.cpp | DEFECT-FIXED | A | stub returning NULL; the ELF as #81 with line 899 and the on bit 0 of +4 (0x1f9c48-0x1f9c54). Written |
| 84 | 0x1f9ce0 | 124 | HUDCmdParseOff(_zrdr*) | fts_mission.cpp | DEFECT-FIXED | A | stub returning NULL; the ELF as #81 with line 859, off bit (0x1f9d40-0x1f9d4c). Written |
| 85 | 0x1f9d60 | 132 | HUDCmdParseOn(_zrdr*) | fts_mission.cpp | DEFECT-FIXED | A | stub returning NULL; the ELF as #82 with line 843, on bit (0x1f9dc8-0x1f9dd4). Written |
| 80 | 0x1f9af0 | 112 | HUDLetterBoxCmdTick(_zanim_cmd_hdr*, float*) | fts_mission.cpp | DEFECT-FIXED | A | stub returning false; the ELF: theHUD NULL -> 1; +4 bit 0 -> theHUD +0x14280 m_letterbox AddLetterbox, else bit 1 -> RemoveLetterbox; 1 (0x1f9b0c-0x1f9b50). Written |
| 83 | 0x1f9c70 | 100 | HUDCmdTickControlSwitch(_zanim_cmd_hdr*, float*) | fts_mission.cpp | DEFECT-FIXED | A | stub returning false; the ELF: theHUD NULL -> 1; bit 0 -> CHUD::On, else bit 1 -> CHUD::Off; 1 (0x1f9c8c-0x1f9cc4). Written |
| 75 | 0x1f7c10 | 72 | CMission::ReOpen_Unload2() | fts_mission.cpp | MATCH | - | m_world read before RemoveAll (delay slot), CAiEvent::Close, ClearLightMapList, ClearShadowList, GarbageCollect; the ELF's v0 1 is read by no caller (CExitState::Init); the trace is port-only |
| 76 | 0x1f8700 | 68 | FilterNavPointString(char const*) | fts_mission.cpp | MATCH | - | (s8)tolower(lb name[0]) - 99, < 0 or >= 24 -> 0, else + 9 |
| 77 | 0x1f9740 | 32 | HUDStartDefuseTimerTick(_zanim_cmd_hdr*, float*) | fts_mission.cpp | MATCH | - | hudStartDefuseTimer(+0x4 float), 1 |
| 78 | 0x1f98d0 | 84 | HUDTriggerMissionCamTick(_zanim_cmd_hdr*, float*) | fts_mission.cpp | MATCH | - | theHUD NULL -> 1; !(+0x14590 m_missioncams IsPlaying); the ELF's NULL test of theHUD + 0x14590 cannot fail |
| 79 | 0x1f9930 | 76 | HUDTriggerMissionCamBegin(_zanim_cmd_hdr*) | fts_mission.cpp | MATCH | - | theHUD NULL exits; PlayCamera(ZAnim +0x38 m_CurAnim GetName(lbu +0x4)) |
| 86 | 0x1f9df0 | 8 | StopImageRecorderTick(_zanim_cmd_hdr*, float*) | fts_mission.cpp | MATCH | - | returns 1 |
| 87 | 0x1f9e00 | 108 | StopImageRecorderParse(_zrdr*) | fts_mission.cpp | MATCH | - | NULL -> NULL; _calloc(1, 4, "fts_mission.cpp", 795), data_size 4, timeless |
| 88 | 0x1f9e70 | 8 | StartImageRecorderTick(_zanim_cmd_hdr*, float*) | fts_mission.cpp | MATCH | - | returns 1 |
| 89 | 0x1fa770 | 20 | GetDefCharTypeName(int) | fts_mission.cpp | MATCH | - | g_arrDefCharTypeNames + 64 * index |
| 90 | 0x1fa790 | 44 | GetCustomCharTypeName(int) | fts_mission.cpp | MATCH | - | index < 32 (slti) -> table[index], else NULL; the port's own copy of c_arrCustomCharTypeNames (same 32 strings) is the recorded port spelling (comment in the code) |
| 91 | 0x1fa7c0 | 112 | ftsIsMapInVisibleList(unsigned int, unsigned int) | fts_mission.cpp | MATCH | - | viewer >= 10 (sltiu) -> 0; i < counts[viewer] (slt): g_arrMapVis[9 * viewer + i] (lbu) == map -> 1; 0 |
| 92 | 0x1fa830 | 32 | ftsGetVisibleMap(unsigned int, int) | fts_mission.cpp | MATCH | - | lbu g_arrMapVis[9 * map + index], no range test |
| 93 | 0x1fa850 | 8 | ftsGetTacMapZoomNear() | fts_mission.cpp | MATCH | - | lwc1 g_fTacMapZoomNear |
| 94 | 0x1fa860 | 8 | ftsGetTacMapZoomFar() | fts_mission.cpp | MATCH | - | lwc1 g_fTacMapZoomFar |
| 95 | 0x1fa870 | 8 | ftsGetTacMapZoom() | fts_mission.cpp | MATCH | - | lwc1 g_fTacMapZoomInit |
| 96 | 0x1fa880 | 44 | ftsGetNumVisibleMaps(unsigned int) | fts_mission.cpp | MATCH | - | map >= 10 -> 0, else g_arrMapVisCounts[map] |
| 252 | 0x2f5280 | 64 | InterruptDmacBusError(int) | zsys_init.cpp | DEFECT-FIXED | C | the second line is "Please contact you friendly neighborhood software expert" (0x458a90; the port had "you neighborhood friendly"); the ELF then traps with break (0x2f52a0), sync, ei and returns 0; the port called abort(). Now the ELF's text, break / sync.l / ei (GCC inline asm) and 0; printf stands for scePrintf (the port has none). Reached only on a DMA bus error |
| 251 | 0x2f4df0 | 160 | zSysInit() | zsys_init.cpp | MATCH | - | isT10K (+0x1c) = !(size < 0x2000000); isCdBoot (+0x1d) 0 before RebootIOP(FirstBoot); +0x1d or cdSounds (+0x1e) -> BuildTOC; recoGrabMemory, AddDmacHandler(15, InterruptDmacBusError, 0), EnableIntc(15) (the scan's zSys offsets are the port's layout) |
| 246 | 0x2f4980 | 64 | zSysSleep(int) | zsys_init.cpp | MATCH | - | GetThreadId, SetAlarm((u16)ticks, SleepAlarmCB, id), SleepThread |
| 247 | 0x2f49c0 | 8 | SleepAlarmCB(int, unsigned short, void*) | zsys_init.cpp | MATCH | - | tail iWakeupThread(arg) |
| 248 | 0x2f4d20 | 56 | zSysUnloadIRX(int) | zsys_init.cpp | MATCH | - | sceSifStopModule(id, 0, NULL, &result), sceSifUnloadModule(id) |
| 249 | 0x2f4d60 | 104 | zSysLoadIRX(char*, int, char*, bool) | zsys_init.cpp | MATCH | - | PS2FileName(name, path, false); sceSifLoadModule(path, len, args) again while < 0 and retry; id returned |
| 250 | 0x2f4dd0 | 24 | zSysPostInit() | zsys_init.cpp | MATCH | - | postinited 0 -> 1 |
| 181 | 0x284420 | 120 | CSealCtrl::TriggerPowerReset() | seal_control.cpp | MATCH | - | +0xf0 m_trigger_power 0, the ten readings +0xf8..+0x11c 0 (the ELF's loop unrolled by 8) |
| 180 | 0x2843f0 | 36 | CSealCtrl::SetCameraZoom(float, float) | seal_control.cpp | MATCH | - | +0x128 level, +0x12c increment, bit 0 of +0x169 m_update_zoom set, others kept |
| 177 | 0x284370 | 32 | CSealCtrl::GetZoomIncrement() | seal_control.cpp | MATCH | - | bit 0 of +0x169 cleared, +0x12c returned |
| 178 | 0x284390 | 32 | CSealCtrl::GetZoomLevel() | seal_control.cpp | MATCH | - | bit 0 of +0x169 cleared, +0x128 returned |
| 194 | 0x2882b0 | 124 | CSealCtrl::~CSealCtrl() | seal_control.cpp | MATCH | - | ReleaseDynamicVisMap(+0xe0), delete it, +0xe0 NULL, then ~CEntityCtrl |
| 187 | 0x287b50 | 112 | CSealCtrl::SetTrigger(bool, float) | seal_control.cpp | MATCH | - | +0xf0 power first, then SetTrigger(bool)'s switch inline (as #186) |
| 173 | 0x2842c0 | 96 | CSealCtrl::SetLowRumbleTime(float, float) | seal_control.cpp | MATCH | - | RumbleIsOn (lbu) exits; m_rumblestr < str (c.lt.s) or m_rumbletime <= 0 (c.le.s) -> str; m_rumbletime < time -> time |
| 174 | 0x284320 | 44 | CSealCtrl::SetHighRumbleTime(float) | seal_control.cpp | MATCH | - | RumbleIsOn and +0x138 < time (c.lt.s) -> time |
| 179 | 0x2843b0 | 56 | CSealCtrl::UpdateHudWeapon() | seal_control.cpp | MATCH | - | bit 4 of +0x168 tested, cleared (others kept), 1; else 0 |
| 186 | 0x287ae0 | 108 | CSealCtrl::SetTrigger(bool) | seal_control.cpp | MATCH | - | lbu +0xec: 0 -> down ? 2 : 0, 1 and 2 -> down ? 1 : 3, 3 -> down ? 2 : 0; other values stored back unchanged (the port leaves them, same) |
| 190 | 0x288010 | 60 | CSealCtrl::OnWeaponHit(zdb::IntersectStruct*, CZProjectile*) | seal_control.cpp | MATCH | - | SetHighRumbleTime(0.05f 0x3d4ccccd), inline in the ELF |
| 184 | 0x287ab0 | 28 | CSealCtrl::SetMenuState(MENU_STATE) | seal_control.cpp | MATCH | - | (u8)state < 6 -> sb +0x221 (MENU_STATE is unsigned char in the port) |
| 182 | 0x2844a0 | 188 | CSealCtrl::GetThrowAverage() | seal_control.cpp | DEFECT-FIXED | C | i = last - 1 (+10 below 0); the ELF takes reading[last] when reading[i] <= reading[last] (c.le.s 0x2844c8); the port's !(reading[last] < best) differed for NaN only; now in the ELF's form. The five earlier readings (c.le.s, keep), == 0 (c.eq.s) else / 255 agree |
| 189 | 0x287bd0 | 112 | CSealCtrl::PlayAiSound(CHARACTER_SOUND) | seal_control.cpp | MATCH | - | m_entity +0x4, its m_id, GetCharacter, slot +0xc GetPosW, PlayAt(sound, id, pos) |
| 175 | 0x284350 | 8 | IsRumbleOn() | seal_control.cpp | MATCH | - | lbu RumbleIsOn |
| 176 | 0x284360 | 8 | SetRumbleOn(bool) | seal_control.cpp | MATCH | - | sb RumbleIsOn |
| 183 | 0x2852d0 | 8 | CSealCtrl::PerformCollisionActions() | seal_control.cpp | MATCH | - | empty; the ELF's v0 0 has no caller |
| 185 | 0x287ad0 | 8 | CSealCtrl::GetMenuState() | seal_control.cpp | MATCH | - | +0x221 returned (lb in the ELF; states 0..5 equal either way) |
| 188 | 0x287bc0 | 8 | CSealCtrl::ResetToInitialState() | seal_control.cpp | MATCH | - | empty |
| 191 | 0x288120 | 8 | CSealCtrl::OnMissionEnd() | seal_control.cpp | MATCH | - | empty |
| 192 | 0x288130 | 8 | CSealCtrl::OnMissionStart() | seal_control.cpp | MATCH | - | empty |
| 193 | 0x288140 | 8 | CSealCtrl::OnRecycleEntity(CEntity*) | seal_control.cpp | MATCH | - | empty |
| 135 | 0x229ff0 | 132 | zdb::CModel::CModel(char const*) | node_model.cpp | MATCH | - | CNode(), vtable, m_list ctor (+0xc8); +0xd8 m_AssetLib NULL, m_type 7, +0xd4 m_bbox_valid 0, SetName(name), +0xc0 m_variant 0, +0xc4 m_bForceExport 0 in that order |
| 131 | 0x229490 | 124 | zdb::CNode::GetSubMesh() | node_model.cpp | MATCH | - | m_visual size_ 0 -> NULL; first visual NULL -> NULL; m_vtype (lb +0x4) != 2 -> NULL; __dynamic_cast to CSubMesh |
| 128 | 0x228f20 | 164 | zdb::CNode::SetModel(zdb::CModel*) | node_model.cpp | MATCH | - | m_type 3 or 2 else 0; type 3: slot +0x20 DeleteChildren, model -> slot +0x18 AddChild(model); m_model +0xb0, SetModelname(model ? model +0x90 m_name : NULL), 1 |
| 129 | 0x2290f0 | 88 | zdb::CNode::CreateXRef() | node_model.cpp | MATCH | - | new 192, CNode(), m_type 3, SetName("XRef"), returned |
| 133 | 0x2297f0 | 120 | zdb::CNode::UpdateBBox(bool) | node_model.cpp | MATCH | - | the ELF's inline GetBBox two parent levels (bit 6 of +0x5f m_use_parent_bbox, +0x40 bbox, +0x64 m_parent) then GetBBox(); the port's GetBBox() recursion gives the same box |
| 134 | 0x229d60 | 92 | zdb::CModel::Release(zdb::CNode*) | node_model.cpp | MATCH | - | remove_if(equal_to node) on m_list (+0xc8); m_parent == node -> NULL |
| 130 | 0x229460 | 40 | zdb::CNode::GetFirstVisual() | node_model.cpp | MATCH | - | size_ 0 -> NULL, else data_[0] |
| 132 | 0x229510 | 100 | zdb::CNode::GetMesh() | node_model.cpp | MATCH | - | first visual, NULL or m_vtype (lb) != 1 -> NULL, else it |
| 97 | 0x206e20 | 156 | CZBombState::UninitBomb() | fts_net_bomb.cpp | MATCH | - | m_pNetGame NULL, m_game_type (+0xd9) != 7, m_bomb_created (+0x9d) 0 exit; session master (theNetwork +0x8) and BombObjectIndex (+0x1c) -> NetFreeObject(index); +0x9d, +0x9c, New, Current, Defuser, Holder, BombObject 0 in that order (TypeBombStatus as DWARF; the scan's offsets are noise) |
| 98 | 0x2070b0 | 60 | CZBombState::CreateBombHere(CPnt3D*) | fts_net_bomb.cpp | MATCH | - | NewBombState (+0x1) 1, BombLocation (+0x4) = *pos, Holder (+0x14) 0, tail UpdateLocalBomb |
| 101 | 0x207740 | 136 | CZBombState::RemoteBombPostUpdateCallback(int, int, int) | fts_net_bomb.cpp | MATCH | - | the three game tests; zNetGetObject(second argument), NULL exit; +0x1c data NULL exit; data +0xc (lbu) == Current (lbu) exit; NewBombState = it, ChangeBombState |
| 99 | 0x207490 | 44 | CZBombState::RequestNewBombState(int, CZBombState::EnumBombState, CPnt3D const*) | fts_net_bomb.cpp | MATCH | - | m_pNetGame != NULL -> SendBombStateRequest(object, state, pos), arguments passed through |
| 100 | 0x207730 | 8 | CZBombState::RemoteBombDeletionCallback(int, int) | fts_net_bomb.cpp | MATCH | - | empty |
| 279 | 0x305cc0 | 64 | CFileIO::CFileIO(CFileIO const&) | util_sonyio.cpp | MATCH | - | vtables, +0x4 -1, +0x8 m_filesize, +0x4 m_file, +0xc m_mode copied in that order; the port's separate m_cd copy mirrors the ELF's union at +0x4 (recorded) |
| 280 | 0x305d30 | 112 | CFileIO::SetRootPath(char const*) | util_sonyio.cpp | MATCH | - | strstr(path, "cdrom") -> m_file_version ";1" else "", strcpy(m_root_path, path) (the scan's stores are GCC's inlined strcpy) |
| 272 | 0x304f70 | 160 | CFileCD::Find(char const*) | util_sonyio.cpp | MATCH | - | m_TOC NULL -> NULL; i < m_TOCNum and nothing found: strcmp(name, entry +0x0) == 0 -> entry (16 bytes each) |
| 278 | 0x305c70 | 68 | CFileIO::IsOpen() const | util_sonyio.cpp | MATCH | - | CD boot (zSys +0x1d): word +0x4 != -1 and != 0; else !(m_file < 0) (the port keeps m_file = (u32)m_cd in CD mode) |
| 275 | 0x305650 | 44 | CFileIO::fwrite(void const*, int) | util_sonyio.cpp | MATCH | - | host: sceWrite(+0x4, buf, count) returned; on a CD boot the ELF leaves v0 unset, the port's 0 is its recorded choice (comment in the code) |
| 276 | 0x305680 | 72 | CFileIO::fread(void*, int) | util_sonyio.cpp | MATCH | - | size 0 -> 0; CD boot -> CFileCD::Read(m_cd, buf, size) (the member overload), else sceRead(+0x4, buf, size) |
| 277 | 0x305c60 | 12 | CBufferIO::IsOpen() const | util_sonyio.cpp | MATCH | - | +0x10 (the first CBufferIO member, m_buffer) != NULL |
| 273 | 0x305630 | 8 | CFileIO::fflush() | util_sonyio.cpp | MATCH | - | empty |
| 274 | 0x305640 | 8 | CFileIO::ftell() const | util_sonyio.cpp | MATCH | - | returns 0 |
| 281 | 0x305e30 | 12 | CFileIO::fread(int, void**) | util_sonyio.cpp | MATCH | - | *buf NULL, 0 |
| 195 | 0x2a4f70 | 36 | CZKit::ResetScreenOffsetXY() | seal_kit.cpp | MATCH | - | +0x44 / +0x48 0; m_world +0xc0 camera +0x450 / +0x454 = m_sniper_posx / posy |
| 210 | 0x2a7410 | 188 | CZKit::FireGrenade(CPnt3D const*, CPnt3D const*) | seal_kit.cpp | MATCH | - | vel = CPnt3D::zero; m_item[sel] NULL -> NULL; (u8)GetIDType() == 150 -> HandleRemotePlaceExplosive(from, m_body + 0x50 quat); else Fire(sel, from, dir, &vel) (t0 the fifth argument) |
| 208 | 0x2a6c40 | 136 | CZKit::CurItemHasFiremodeGraphic() | seal_kit.cpp | MATCH | - | unwrap called, result unused (ELF); m_item[sel] NULL -> 0; m_type (lbu +0x1bc) 3 -> 0; id (+0x60) 182 / 186 / 183 -> 0, else 1 |
| 205 | 0x2a5780 | 36 | CZKit::PendingPickupHandled() | seal_kit.cpp | MATCH | - | bit 5 of +0x1 cleared (others kept), +0x878 0 |
| 201 | 0x2a5010 | 48 | CZKit::InitializeSniperKick() | seal_kit.cpp | MATCH | - | +0x28 0; m_body m_control non-NULL -> +0x24 = control +0x130 m_aimPitch; tail m_body AdrenalineIncr(0.5) |
| 202 | 0x2a5670 | 196 | CZKit::IsUsingItem(EQUIP_ITEM) | seal_kit.cpp | MATCH | - | (u8) 182: zoom (lb +0x160) 3 or >= 4; 184: zoom 2; else the first slot with m_ID (lbu +0x60) == item -> IsUsingItem(i); 0 |
| 199 | 0x2a4fd0 | 20 | CZKit::IsUsingBinocs() | seal_kit.cpp | MATCH | - | m_body zoom (lb +0x160) == 3 |
| 200 | 0x2a4ff0 | 32 | CZKit::Binocs_Enabled(bool) | seal_kit.cpp | MATCH | - | bit 5 of +0x0 = enable & 1, others kept |
| 203 | 0x2a5740 | 20 | CZKit::IsUsingScope() | seal_kit.cpp | MATCH | - | !(zoom < 4) |
| 204 | 0x2a5760 | 28 | CZKit::SetWeaponInfoChanged() | seal_kit.cpp | MATCH | - | bit 2 of +0x0 set |
| 206 | 0x2a57b0 | 128 | CZKit::UpdateNumItems() | seal_kit.cpp | MATCH | - | last non-NULL of 30 slots + 1 into +0x810; num < sel (slt) or m_item[sel] NULL -> sel 0, bit 2 of +0x0 set |
| 207 | 0x2a6c00 | 56 | CZKit::WeaponInfoChanged() | seal_kit.cpp | MATCH | - | bit 2 of +0x0 tested, cleared, 1; else 0 |
| 209 | 0x2a6e40 | 132 | CZKit::FillWeaponEnum(int, CZFTSWeapon**) | seal_kit.cpp | DEVIATION-KEPT | - | unwrap inline, *weapon = m_item[slot]; for slot -1 the ELF stores m_item[-1] (+0xcc, DWARF m_itemstate[29], flags), the port NULL (recorded by an earlier worker; the reason, a wild pointer for DropItem, added to the comment) |
| 211 | 0x2a7b50 | 160 | CZKit::CurWeaponIsM203Mode() | seal_kit.cpp | MATCH | - | unwrap twice (calls), slot -1 -> NULL, NULL -> 0, IsM203Weapon, m_firemode[once-wrapped] (+0x6e8) < 4 -> 0, else 1 (the ELF quirk kept) |
| 212 | 0x2a7bf0 | 92 | CZKit::ItemHasAmmo(int) | seal_kit.cpp | MATCH | - | index < count (slt): any of m_reloads[index][0..9] (+0x1c0 + 40 * index) > 0 |
| 213 | 0x2a7e90 | 164 | CZKit::ItemHasAmmo(EQUIP_ITEM) | seal_kit.cpp | MATCH | - | first slot with m_ID (lbu) == (u8)item, else -1; then ItemHasAmmo(int) inline (slot -1 tested too, the ELF quirk kept) |
| 214 | 0x2a80a0 | 144 | CZKit::SetItemAmmo(unsigned int, CZAmmo*) | seal_kit.cpp | MATCH | - | index >= 30 (sltiu) or NULL item -> 0; GetAmmoCapacity, GetNumMags, SetItemAmmo(index, ammo, cap, mags) (t0) & 0xff |
| 215 | 0x2a8220 | 100 | CZKit::SetItem(unsigned int, EQUIP_ITEM) | seal_kit.cpp | MATCH | - | GetWeapon(id) first; NULL or index >= 30 -> 0; SetItemByIndex(index, weapon), 1 |
| 196 | 0x2a4fa0 | 16 | CZKit::IncrScreenOffsetY(float) | seal_kit.cpp | MATCH | - | +0x48 += dy |
| 197 | 0x2a4fb0 | 8 | CZKit::ScreenOffsetY() | seal_kit.cpp | MATCH | - | +0x48 returned |
| 198 | 0x2a4fc0 | 8 | CZKit::ScreenOffsetX() | seal_kit.cpp | MATCH | - | +0x44 returned |
| 216 | 0x2a8290 | 8 | CZKit::SetBody(CZSealBody*) | seal_kit.cpp | MATCH | - | sw +0x814 |
| 217 | 0x2a82a0 | 8 | CZKit::GetNumItems() const | seal_kit.cpp | MATCH | - | lw +0x810 |
| 218 | 0x2a82b0 | 8 | CZKit::GetSelectedItemNum() | seal_kit.cpp | MATCH | - | lw +0x808 |
| 219 | 0x2a82c0 | 168 | CZKit::GetIcon(int) | seal_kit.cpp | MATCH | - | unwrap inline, -1 -> NULL; m_item[slot] NULL -> NULL, else +0x94 m_icontex |
| 220 | 0x2a8440 | 196 | CZKit::GetFiremodeGraphic(int) | seal_kit.cpp | MATCH | - | the wrapped index only tested (-1 -> NULL); m_item[item] (the given index, no NULL test) IsGrenadeLauncherAmmo -> +0x94, else NULL (the ELF quirk kept) |
| 234 | 0x2ae190 | 184 | CZKit::ReParentToRifle() | seal_kit.cpp | MATCH | - | m_body +0x2d4 / +0x2d8 parts; m_items_avail size_ >= 2 -> data_[1], >= 3 -> data_[2]; each non-NULL: slot +0x34 SetActive(1), part +0xc m_node = it |
| 224 | 0x2a8970 | 88 | CZKit::GetCurZoom() | seal_kit.cpp | MATCH | - | 1f; m_item[sel] NULL -> 1; (u32)(zoom (lb) - 3) < m_zoommode size_ (+0x1c4, sltu) -> GetZoomRange(index) |
| 241 | 0x2af290 | 124 | CZKit::HasSniperRifle() | seal_kit.cpp | MATCH | - | item ? (u8)GetIDType() : 254; == 100 and ItemHasAmmo(sel, lbu m_firemode[sel]) |
| 232 | 0x2acc00 | 100 | CZKit::CanChangeItem() | seal_kit.cpp | DEFECT-FIXED | C | bit 1 of +0x1 m_waiting_to_fire -> 0; the ELF goes on only when m_firetime <= 0 (c.le.s 0x2acc20, bc1f -> 0); the port's > 0 differed for NaN only; now in the ELF's form. zoom (lb) < 4 and != 3 -> 1 agree |
| 245 | 0x2af580 | 140 | CZKit::GetCurItemEnum() const | seal_kit.cpp | MATCH | - | m_item[sel]; IsGrenadeLauncherWeapon and m_firemode[sel] >= 4 -> m_item[mode - 3]; NULL -> 255, else lb +0x60 |
| 230 | 0x2abed0 | 168 | CZKit::GetCurAmmoCount() | seal_kit.cpp | MATCH | - | slot = unwrap(sel, num); WeaponIsGrenadeLauncherMode(sel): g = m_firemode[slot] - 3, m_reloads[g][m_currentmag[g] (+0x670)]; else m_reloads[slot][m_currentmag[slot]] |
| 235 | 0x2ae4f0 | 164 | CZKit::SetupBinocular() | seal_kit.cpp | MATCH | - | num read once; a slot with m_ID (lbu) 182 exits; GetWeapon(182), non-NULL and (u32)num < 30 -> SetItemByIndex(num, binocs) |
| 221 | 0x2a8510 | 160 | CZKit::GetItemName(int) | seal_kit.cpp | MATCH | - | unwrap inline, -1 -> NULL, else m_item[slot]->GetName() (no NULL test, as the ELF) |
| 238 | 0x2aecd0 | 96 | CZKit::NVG_Enabled(bool) | seal_kit.cpp | MATCH | - | enable: m_world non-NULL and +0x5c8 m_night_mission -> bit 4 of +0x0 set; else bit 4 cleared |
| 223 | 0x2a8830 | 84 | CZKit::CurReticuleTypeChanged() | seal_kit.cpp | MATCH | - | bit 1 of +0x0 tested, cleared, m_body AdrenalineIncr(0.5), 1; else 0 |
| 227 | 0x2abca0 | 148 | CZKit::GetItemByIndex(int) | seal_kit.cpp | MATCH | - | unwrap inline, -1 -> NULL, else m_item[slot] |
| 240 | 0x2aed50 | 104 | CZKit::~CZKit() | seal_kit.cpp | MATCH | - | m_items_avail (+0x818) vector destructor only (the port's implicit member destructor) |
| 242 | 0x2af310 | 88 | CZKit::HasItem(EQUIP_ITEM) const | seal_kit.cpp | MATCH | - | a slot below m_num_items with m_ID (lbu +0x60) == (u8)item |
| 243 | 0x2af370 | 88 | CZKit::GetItemIndex(SEAL_ITEM) | seal_kit.cpp | MATCH | - | first slot with m_type (lbu +0x1bc) == (u8)type, else -1 |
| 244 | 0x2af520 | 88 | CZKit::GetItemIndex(EQUIP_ITEM) const | seal_kit.cpp | MATCH | - | first slot with m_ID (lbu +0x60) == (u8)id, else -1 |
| 222 | 0x2a87e0 | 68 | CZKit::SetCurReticule() | seal_kit.cpp | MATCH | - | bit 1 of +0x0 set, +0x40 = GetReticuleByIndex(sel) |
| 225 | 0x2a89d0 | 44 | CZKit::IsZoomed() | seal_kit.cpp | MATCH | - | zoom (lb) >= 4 or == 3 |
| 231 | 0x2ac760 | 72 | CZKit::GetNumMags(int) | seal_kit.cpp | MATCH | - | count of m_reloads[item][0..9] > 0, no range test |
| 236 | 0x2aec60 | 44 | CZKit::GetCurItemType() | seal_kit.cpp | MATCH | - | m_item[sel] NULL -> 0, else lbu +0x1bc |
| 237 | 0x2aec90 | 52 | CZKit::GetCurItemIDType() | seal_kit.cpp | MATCH | - | m_item[sel] NULL -> 254, else GetIDType() |
| 226 | 0x2a9340 | 20 | Timer_PlaceC4(void*, void*) | seal_kit.cpp | MATCH | - | second argument non-NULL -> *(f32*) 0 |
| 228 | 0x2abd40 | 20 | CZKit::GetCurItem() const | seal_kit.cpp | MATCH | - | m_item[sel], no range test |
| 229 | 0x2abd60 | 20 | CZKit::GetCurFireMode() | seal_kit.cpp | MATCH | - | lbu of m_firemode[sel] (+0x6e8), the 1-byte FIREMODE |
| 233 | 0x2adea0 | 24 | CZKit::FireCur(CPnt3D const*, CPnt3D const*, CPnt3D const*) | seal_kit.cpp | MATCH | - | tail Fire(sel, from, dir, vel), vel in t0 |
| 239 | 0x2aed30 | 20 | CZKit::NVG_Enabled() const | seal_kit.cpp | MATCH | - | m_body zoom (lb) == 2 |
| 36 | 0x1aae30 | 184 | zAnimLoadTimer(_zrdr*) | zanim_cmd_parse.cpp | DEFECT-FIXED | C | the ELF tags its _calloc ("zanim_cmd_parse.cpp", 4637) (0x1aae44 / 0x1aae4c); the port's zcalloc passed __FILE__ / __LINE__; now the ELF's tag. 8 bytes, data_size 8, timeless; HIDE -> -1, else 0 then findint("TIME", +0x4, 1) agree |
| 44 | 0x1b7af0 | 156 | zAnimCmdAddData(_zanim_cmd_hdr*, void*, int) | zanim_cmd_parse.cpp | MATCH | - | total = data_size (bits 2-15 of +0x2) + size; _realloc(cmd, total, "zanim_cmd_parse.cpp", 194); memcpy(new + its data_size, data, size); data_size = total & 0x3fff; no NULL tests |
| 37 | 0x1afef0 | 96 | zAnimLoadFail(_zrdr*) | zanim_cmd_parse.cpp | MATCH | - | _calloc(1, 4, file, 3125), data_size 4, timeless; the reader unused |
| 38 | 0x1b0620 | 188 | zAnimLoadNodeRendered(_zrdr*) | zanim_cmd_parse.cpp | MATCH | - | _calloc(1, 8, file, 2947), 8 / timeless; findtag("NAME") else the reader; LoadNodeNames(m_CurAnim, tag, NULL, 0, bits 3-4 of m_CurAnim +0x4 scope) into +0x4 (sh) |
| 39 | 0x1b0830 | 144 | zAnimLoad_EndIf(_zrdr*) | zanim_cmd_parse.cpp | MATCH | - | tag -> _calloc(1, 8, file, 2836); m_CurSeq +0x7 level into +0x4 (through NULL without a tag, the ELF quirk kept), then the level - 1 |
| 40 | 0x1b08c0 | 124 | zAnimLoad_Else(_zrdr*) | zanim_cmd_parse.cpp | MATCH | - | as #39 without the decrement |
| 41 | 0x1b0940 | 152 | zAnimLoad_ElseIf(_zrdr*) | zanim_cmd_parse.cpp | MATCH | - | tag -> _calloc(1, 8, file, 2764), AnimParseExpression(&ZAnim, cmd, tag); level into the result's +0x4 |
| 42 | 0x1b09e0 | 172 | zAnimLoad_If(_zrdr*) | zanim_cmd_parse.cpp | MATCH | - | as #41, the level + 1 first, then stored into the result |
| 43 | 0x1b0a90 | 108 | zAnimLoadBreak(_zrdr*) | zanim_cmd_parse.cpp | MATCH | - | NULL -> NULL; _calloc(1, 4, file, 2737), 4 / timeless |
| 45 | 0x1b7c60 | 8 | zAnim_ResetSequenceOffsetStackSize() | zanim_cmd_parse.cpp | MATCH | - | sw 0 seq_offset_stack_size |
| 46 | 0x1b7c70 | 8 | zAnim_GetSequenceOffsetStackSize() | zanim_cmd_parse.cpp | MATCH | - | lw seq_offset_stack_size |
| 111 | 0x1fdd10 | 108 | CftsPlayer::CmdTickControls(_zanim_cmd_hdr*, float*) | fts_player.cpp | MATCH | - | ftsPlayer or its m_control NULL -> 1; record +0x4 bit 0 -> m_input_enabled (bit 3 of +0x169) 0, else 1; 1 |
| 104 | 0x1fd0d0 | 140 | CMission::InitalizeTeamValves() | fts_player.cpp | MATCH | - | sprintf("aiteam_%02d", i), Create(name, 0, 2) into +0x5d4[i] for 32; "player_valve_alive" (0, 2) into +0x654 |
| 103 | 0x1fcc60 | 72 | CMission::RecycleEntity(CEntity*) | fts_player.cpp | MATCH | - | spawners list (+0xc) empty exits; +0x1c m_timer 2, +0x18 m_pending + 1, CEntity::RecycleEntity(entity); the SPAWN trace is port-only |
| 107 | 0x1fdb50 | 8 | ftsSetPlayerCount(int) | fts_player.cpp | MATCH | - | the ELF stores the second word of its 8-byte ftsPlayer object; the port's separate ftsPlayerCount is the recorded port layout (fts_player.cpp, the ftsPlayer comment) |
| 110 | 0x1fdb80 | 156 | CftsPlayer::CmdTickIsPlayerNode(_zanim_cmd_hdr*, float*) | fts_player.cpp | MATCH | - | m_CurAnim GetNode(lbu +0x4, false), NULL -> 0; ftsPlayer GetNode() == node -> 1; +0x5 bit 0 and slot +0x28 FindChild(node, true) -> 1; else 0 (ftsPlayer not NULL-tested, as the ELF) |
| 102 | 0x1fcb00 | 56 | CSpawners::Clear() | fts_player.cpp | MATCH | - | erase(begin, end) of the list at +0xc |
| 105 | 0x1fd9a0 | 56 | CMission::CloseVehicleRdr() | fts_player.cpp | MATCH | - | CleanupTemporary, +0x590 non-NULL -> Close |
| 106 | 0x1fd9e0 | 40 | CMission::OpenVehicleRdr() | fts_player.cpp | MATCH | - | +0x590 non-NULL -> Open("vehicles.rdr") |
| 108 | 0x1fdb60 | 8 | ftsGetPlayer() | fts_player.cpp | MATCH | - | lw ftsPlayer |
| 109 | 0x1fdb70 | 8 | ftsSetPlayer(CZSealBody*) | fts_player.cpp | MATCH | - | sw ftsPlayer |
| 112 | 0x1fde50 | 48 | CftsPlayer::CmdTickIndoorsTest(_zanim_cmd_hdr*, float*) | fts_player.cpp | MATCH | - | ftsPlayer NULL -> 0, else bit 2 of +0xf5c m_inside |
| 113 | 0x1fde80 | 108 | CftsPlayer::CmdParseIndoorsTest(_zrdr*) | fts_player.cpp | MATCH | - | NULL -> NULL; _calloc(1, 4, "fts_player.cpp", 140), 4 / timeless |
| 114 | 0x1fdef0 | 152 | CftsPlayer::RegisterAnimCommands() | fts_player.cpp | MATCH | - | AddCmd PLAYER_INDOORS, PLAYER_CONTROLS, IS_PLAYER_NODE with their parse / tick, begin and end NULL (t1) |
| 115 | 0x1fdf90 | 48 | CftsPlayer::IsInside() | fts_player.cpp | MATCH | - | body (the ELF's this +0x0, the port's ftsPlayer: recorded in the code) non-NULL and bit 2 of +0xf5c |
| 116 | 0x1fe120 | 8 | ftsGetSquirm() | fts_player.cpp | MATCH | - | lbu doSquirm |
| 271 | 0x2ff3b0 | 108 | C2DFont::C2DFont() | ztwod_font.cpp | MATCH | - | vtable, m_charlist empty (the vector's ctor), +0x10 / +0x14 NULL, +0x18 / +0x1c 0, +0x28 / +0x2c 1f |
| 269 | 0x2fe9a0 | 112 | C2DFont::SetXSpacing(float) | ztwod_font.cpp | MATCH | - | each 40-byte entry +0x10 = fptosi(spacing) << 4 |
| 270 | 0x2ff350 | 88 | C2DFont::GetIndex(char) | ztwod_font.cpp | MATCH | - | first entry whose m_char (lb +0x0) == (s8)character -> index; -1 |
| 28 | 0x1a6100 | 76 | _tile_boundary(MAP_FOREACH_STRUCT const&, void*) | ai_mapwalk.cpp | MATCH | - | record byte +0x0 vs the cell's bits 3-4 of +0x2; differ: bits 3-4 = value & 3 (others kept), record +0x8 1; 1 |
| 30 | 0x1a8280 | 176 | CAiMap::ComputeLineVisibility(CAiMapLoc const&, CAiMapLoc const&) | ai_mapwalk.cpp | MATCH | - | {0, -1, -1} on the stack, WalkLine(from, to, _VisLineCallback, &vis); _saturate(v, 0, 1) (0x474d70 / 74 read from the ELF); 1 - v; last - first > 0 -> v * shadow_scale[step] (unbounded, the ELF quirk kept) |
| 29 | 0x1a6150 | 136 | _tile_soil(MAP_FOREACH_STRUCT const&, void*) | ai_mapwalk.cpp | MATCH | - | soil (bits 0-4 of the cell +0x0) == record byte -> 1; flags (+0x4) bit 0, or soil 1, or bit 1 and soil 11: bits 0-4 = value & 0x1f, +0x8 1; 1 |
| 34 | 0x1a8460 | 92 | _SeeLineCallback(MAP_LINEWALK_STRUCT const&, void*) | ai_mapwalk.cpp | MATCH | - | cell (+0x10) soil bits 0-4: 0 / 8 / 10 block; blocked and data -> *data = +0xc m_loc (one word); open returned |
| 31 | 0x1a8330 | 16 | CAiMap::CanSeeLine(CAiMapLoc const&, CPnt3D const*, CAiMapLoc*) | ai_mapwalk.cpp | MATCH | - | tail WalkLine(from, to, _SeeLineCallback, blocked) (t0) |
| 32 | 0x1a8340 | 16 | CAiMap::CanSeeLine(CAiMapLoc const&, CAiMapLoc const&, CAiMapLoc*) | ai_mapwalk.cpp | MATCH | - | tail WalkLine(loc, loc) with _SeeLineCallback, blocked (t0) |
| 33 | 0x1a8350 | 16 | CAiMap::CanTravelLine(CAiMapLoc const&, CAiMapLoc const&, CAiMapLoc*) | ai_mapwalk.cpp | MATCH | - | tail WalkLine(loc, loc) with _TravelLineCallback, blocked (t0) |
| 136 | 0x232050 | 36 | zdb::CRipple::Uninit() | node_wave.cpp | MATCH | - | ~RTPool(m_ripplefreepool, 1) (delete), then NULL |
| 137 | 0x232080 | 56 | zdb::CRipple::Init() | node_wave.cpp | MATCH | - | new 12, RTPool(16) when non-NULL, stored |
| 138 | 0x17d2b0 | 44 | zdb::CNode::SetActive(bool) | znode_holding.cpp | MATCH | - | bit 0 of +0x5c = active ? 1 : 0, others kept; the old bit returned |
| 119 | 0x3351b0 | 72 | stopPss(sceMpeg*) | playpss.cpp | MATCH | - | doAudio -> audioDecReset(&audioDec), isStarted 0; sceMpegReset, sceMpegDelete; the trace is port-only |
| 122 | 0x335670 | 60 | initPssAudio(playPssRsrcs*) | playpss.cpp | MATCH | - | doAudio -> audioDecCreate(&audioDec, +0x18, +0x1c, +0x24), isStarted 0; the trace is port-only |
| 117 | 0x334d10 | 8 | errorCallback(sceMpeg*, sceMpegCbData*, void*) | playpss.cpp | MATCH | - | returns 1 |
| 118 | 0x334d20 | 96 | backgroundCallback(sceMpeg*, sceMpegCbData*, void*) | playpss.cpp | MATCH | - | BlockingPSSPlayback: fillBuff(mp, 0) while T0_COUNT < 480 (sltiu); else OKtoFillBuff 1; 1 |
| 120 | 0x335200 | 32 | testdonePss(sceMpeg*) | playpss.cpp | MATCH | - | sceMpegIsEnd != 0 |
| 121 | 0x335640 | 40 | uninitPssAudio() | playpss.cpp | MATCH | - | doAudio -> audioDecDelete(&audioDec) |
| 6 | 0x3d0aa0 | 20 | hudStartDefuseTimer(float) | hud_bitmapreticule.cpp | MATCH | - | g_fDefuseTime = time, tail CValve::Create(c_szDefusingValve "hud_defuse_timer", 1, 2) |
| 4 | 0x3d0490 | 80 | BitmapReticule::UnInit() | hud_bitmapreticule.cpp | MATCH | - | slot +0x78 of the three C2DStrings (+0x3124, +0x31d4, +0x3430): vt.py 0x472cb0 gives ClearAndWipe (the packet named C2D::Off); the port calls ClearAndWipe on each, same order |
| 5 | 0x3d04e0 | 52 | BitmapReticule::Draw(zdb::CCamera*) | hud_bitmapreticule.cpp | MATCH | - | m_reticuleTex[m_rettype] (+0x33b0) non-NULL -> C2D::Draw(camera); the port's rettype == -1 test spells out the ELF's read of the word before the array (m_rettype, -1, non-zero) without the out-of-range index |
| 2 | 0x3ce4c0 | 8 | BitmapReticule::Off() | hud_bitmapreticule.cpp | DEFECT-FIXED | C | the ELF tail-calls C2D::Off (0x3ce4c0); the port set m_on itself (the same store); now C2D::Off() |
| 3 | 0x3ce4d0 | 8 | BitmapReticule::On() | hud_bitmapreticule.cpp | DEFECT-FIXED | C | the ELF tail-calls C2D::On (0x3ce4d0); the port set m_on itself; now C2D::On() |
| 48 | 0x1dd670 | 12 | zBoneClose() | bone_init.cpp | DEFECT-FIXED | B | the ELF tail-calls boneArchive's CZAR::Close (boneArchive + 0xc, 0x1dd674) after zBoneLoadAll; the port was a stub returning true, so motion.zar, its keys and string table stayed open across missions (a later zBoneOpen saw it open and skipped the open). Now Close(); the loaded scripts are kept in m_scripts with copied names and the released data buffer, as in the ELF. Masked: nothing read the open archive again |
| 47 | 0x1dd620 | 76 | zBoneLoadAll() | bone_init.cpp | MATCH | - | LoadAll (u8), Sizeof_MotionRdr = +0x28 m_databuffer_size, pBuffer_MotionRdr = ReleaseDataBuffer(), the LoadAll result returned |
| 49 | 0x1dd680 | 156 | zBoneOpen() | bone_init.cpp | MATCH | - | is_init 0 -> 0; m_pFile slot +0x10 IsOpen -> 0; Open("run/motion.zar", bone_archive_version, 1, 16), then m_pFile IsOpen (u8) returned |
| 11 | 0x19dca0 | 60 | CAiMap::DestroyGraph() | ai_mapdata.cpp | MATCH | - | CGraph::Destroy(+0x128), +0x128 NULL, bit 0 of +0x58 cleared |
| 12 | 0x19e300 | 20 | _invalid_route(CAiMap::route&) | ai_mapdata.cpp | MATCH | - | +0x0 & 1 as 0 / 1 |
| 13 | 0x19e570 | 68 | CAiMap::reader::SetReader(CRdrFile*) | ai_mapdata.cpp | MATCH | - | rdr != +0x4 -> zrdr_free(old), +0x4 = rdr |
| 14 | 0x19e5c0 | 172 | CAiMap::readers::~readers() | ai_mapdata.cpp | MATCH | - | each 16-byte reader: +0x4 non-NULL -> zrdr_free, NULL; then the vector's own destructor |
| 15 | 0x19e670 | 20 | CAiMap::reader::reader() | ai_mapdata.cpp | MATCH | - | +0x4, +0x8, +0xc 0 |
| 16 | 0x19e690 | 120 | CAiMap::region::GetCenter(CAiMapLoc&) const | ai_mapdata.cpp | MATCH | - | out.x = (m_loc.x + (m_dx (lhu) >> 1)) & 0x1fff, out.y likewise with m_dy (u32 bitfields, no sign difference), map id kept; &out |
| 17 | 0x19ea90 | 152 | CAiMap::GetRegion(char const*, CAiMapLoc&) | ai_mapdata.cpp | MATCH | - | NULL name -> NULL; first 28-byte region with strcasecmp(+0xc m_name, name) == 0: loc = its +0x0 word, the region |
| 18 | 0x19eb30 | 148 | CAiMap::GetRegion(CAiMapLoc const&) | ai_mapdata.cpp | MATCH | - | first region whose m_loc x (bits 6-18) and y (bits 3-15 of +0x2) equal loc's; NULL |
| 19 | 0x19ebd0 | 140 | CAiMap::GetCellLink(CAiMapLoc const&) | ai_mapdata.cpp | MATCH | - | FindByLocation over the 8-byte links (+0xd4 / +0xd8): x and y compared, map id not |
| 20 | 0x19efc0 | 108 | CAiMap::FindActionLocation(unsigned int, CAiMapLoc&, CAiMap::action**) | ai_mapdata.cpp | MATCH | - | 40-byte actions: m_actionId (bits 4-19 of +0x4) == id -> *out = entry when out, loc = +0x0, 1; else 0 |
| 21 | 0x19f030 | 148 | CAiMap::GetCellAction(CAiMapLoc const&) | ai_mapdata.cpp | MATCH | - | FindByLocation over the 40-byte actions (+0xc8 / +0xcc) |
| 22 | 0x19f0d0 | 188 | CAiMap::GetLocation(char const*, CAiMapLoc&) const | ai_mapdata.cpp | MATCH | - | NULL -> 0 (tested twice in the ELF); first 24-byte name with strncasecmp(+0x8, str, 14) == 0: loc = +0x0, 1 |
| 23 | 0x19f190 | 40 | CAiMap::names::SortByNames() | ai_mapdata.cpp | MATCH | - | tail sort(data_, data_ + 24 * size_, CompareT<name>) |
| 24 | 0x19f1c0 | 148 | CAiMap::GetCellName(CAiMapLoc const&) | ai_mapdata.cpp | MATCH | - | FindByLocation over the 24-byte names (+0xbc / +0xc0) |
| 25 | 0x19f260 | 8 | CAiMap::name::ValidateName() | ai_mapdata.cpp | MATCH | - | sb 0 at +0x16 (m_name[14]) |
| 26 | 0x19f270 | 192 | CAiMap::GetMapEx(CAiMapLoc const&) | ai_mapdata.cpp | MATCH | - | m_mapex NULL -> NULL; y < m_ny, x < m_nx (sltu); 12-byte row: x < m_start or !(x < m_end) -> NULL; row +0x8 + m_mapex_bytes * (x - start) |
| 27 | 0x19f330 | 96 | CAiMap::FreeEx() | ai_mapdata.cpp | MATCH | - | delete[] +0xac, +0xac / +0x60 0, every row's +0x8 m_mapEx NULL |
| 170 | 0x282c10 | 164 | CanDeploy(CZKit*, EQUIP_ITEM, CNodeAction*) | seal_command.cpp | MATCH | - | type = action ? lb +0x20 : 7; HasItem, then ItemHasAmmo(GetItemIndex(item)); (u8)item 152 with (u8)type != 6 -> 0; else 1 |
| 172 | 0x282cd0 | 104 | CSealCtrl::GetCommandId(char const*) | seal_command.cpp | MATCH | - | NULL -> 0; i 0..65: strcasecmp(GetCommandName((u8)i), name) == 0 -> (u8)i; 0 |
| 169 | 0x2825d0 | 8 | CSealCtrl::OnCommand(CZSealBody*, FT_COMMAND, void*, bool) | seal_command.cpp | MATCH | - | empty |
| 171 | 0x282cc0 | 8 | CSealCtrl::AllowCommand(CZSealBody*, FT_COMMAND, void*) | seal_command.cpp | MATCH | - | returns 0 |
| 287 | 0x31a690 | 156 | CZProjectileList::GetNextIndirectFireDI(zdb::DiIntersect**, int*) | zwep_projectilelist.cpp | DEFECT-FIXED | C | the ELF's bound test reads m_direct_firstfree (+0x14c, 0x31a6a4, again at 0x31a6b0), not the indirect one; the port tested m_indirect_firstfree (a guard the ELF lacks). Now the ELF's test (quirk noted in the code). Then *di = m_indirectFireDI[indirect ff], *handle, Used 1, ff advanced while < 30 and used, 1 agree. Masked: 30 direct DIs or 30 grenades in flight at once |
| 290 | 0x31a810 | 164 | CZProjectileList::GetNumRemoteExplosives(int) | zwep_projectilelist.cpp | MATCH | - | each listed explosive: +0xa9 m_remote, +0x90 shooter == shooter, GetInstance() bit 0 of +0x5c -> count |
| 289 | 0x31a770 | 148 | CZProjectileList::GetNextDirectFireDI(zdb::DiIntersect**, int*) | zwep_projectilelist.cpp | MATCH | - | [0] (+0x20) NULL -> 0; +0x14c < 60 else 0; *di = [ff], *handle = ff, Used (+0x110) 1, ff advanced while < 60 and used; 1 |
| 291 | 0x31a8c0 | 136 | CZProjectileList::RemoveExplosive(PlacedExplosive*) | zwep_projectilelist.cpp | MATCH | - | NULL exits; the listed entry: CPickup::Destroy(+0x14), ~PlacedExplosive(1), erase(it) |
| 293 | 0x31aea0 | 120 | CZProjectileList::FreeIdx(int) | zwep_projectilelist.cpp | MATCH | - | m_used[index] 0; index < m_firstfree -> it; index == m_lastused -> FindLastUsed (inline in the ELF) |
| 294 | 0x31b6e0 | 112 | CZProjectileList::~CZProjectileList() | zwep_projectilelist.cpp | MATCH | - | UnInit, then m_explosives' (+0x4) vector destructor |
| 292 | 0x31ae50 | 76 | CZProjectileList::FindLastUsed() | zwep_projectilelist.cpp | MATCH | - | last i < m_size with m_used[i] (lbu) == 1, else -1, into +0x18 |
| 286 | 0x31a650 | 56 | CZProjectileList::ReleaseIndirectFireDI(zdb::DiIntersect**, int*) | zwep_projectilelist.cpp | MATCH | - | [0] (+0x150) NULL exits; Used[*h] (+0x1c8) 0; *h < +0x204 -> it |
| 288 | 0x31a730 | 56 | CZProjectileList::ReleaseDirectFireDI(zdb::DiIntersect**, int*) | zwep_projectilelist.cpp | MATCH | - | [0] (+0x20) NULL exits; Used[*h] (+0x110) 0; *h < +0x14c -> it |
| 295 | 0x31c940 | 68 | ZWepReader::~ZWepReader() | zwep_projectilelist.cpp | MATCH | - | nothing but the delete flag |
| 296 | 0x31c990 | 8 | ZWepReader::ZWepReader() | zwep_projectilelist.cpp | MATCH | - | returns this |
| 35 | 0x2d1e60 | 136 | CAiState::Reset(AI_STATE) | zai_holding.cpp | MATCH | - | bit 1 of +0xc 0, +0x10 state (sb), +0x14 0, bit 0 0, +0x8 0, +0x4 0, bit 2 0, bits 3-31 of the word 0, in that order |
| 260 | 0x3030e0 | 188 | C2DBitmap::TickFade() | ztwod_bitmap.cpp | DEFECT-FIXED | C | m_fade_enable (lbu +0x1c); alpha = +0x3c + dx; dx < 0: the ELF takes the limit when alpha < limit (c.lt.s 0x303118), else 0 when alpha < 0, else alpha; the port's !(limit <= alpha) differed for NaN only; now the ELF's tests. dx >= 0: alpha <= limit (c.le.s) and <= 128 -> alpha, else 128 / limit agree; slot +0x20 SetTrans |
| 268 | 0x303900 | 192 | C2DBitmap::Draw(zdb::CCamera*) | ztwod_bitmap.cpp | MATCH | - | CBatchRelocator on the stack; IsOn or return; bit 3 of +0x15 m_hasTexture with no handle / texture: bit 0 first cleared when set; else MakePacket(camera, &reloc, NULL); C2D::Draw(camera) |
| 263 | 0x303580 | 80 | C2DBitmap::SetPos(int, int) | ztwod_bitmap.cpp | MATCH | - | texture of +0x70 (NULL handle -> NULL) non-NULL: +0x28 x, +0x2c y, +0x74 / +0x78 = texture width / height (lhu) |
| 266 | 0x3037e0 | 36 | C2DBitmap::SetTrans(float) | ztwod_bitmap.cpp | MATCH | - | +0x3c and +0x4c alpha, bit 2 of +0x15 m_isTrans set |
| 261 | 0x3031a0 | 24 | C2DBitmap::Reset() | ztwod_bitmap.cpp | MATCH | - | +0x28, +0x2c, +0x70, +0x74, +0x78 0 |
| 262 | 0x303560 | 28 | C2DBitmap::SetPos(int, int, int, int) | ztwod_bitmap.cpp | MATCH | - | x, y, width x1 - x, height y1 - y |
| 264 | 0x3037b0 | 28 | C2DBitmap::SetUV(float, float, float, float) | ztwod_bitmap.cpp | MATCH | - | +0x50 u0, +0x54 -v0, +0x60 u1, +0x64 -v1 |
| 265 | 0x3037d0 | 8 | C2DBitmap::GetTrans() | ztwod_bitmap.cpp | MATCH | - | +0x3c returned |
| 267 | 0x303810 | 28 | C2DBitmap::SetColor(float, float, float) | ztwod_bitmap.cpp | MATCH | - | r, g, b into +0x30..0x38 and +0x40..0x48 |
| 50 | 0x1ea1c0 | 12 | CEntity::GetEntityList() | zentity_holding.cpp | MATCH | - | &m_list returned |
| 51 | 0x25ab70 | 20 | CEntity::IsAlive() const | zentity_holding.cpp | MATCH | - | bit 3 of +0xdd m_isAlive as 0 / 1 |
| 139 | 0x23fce0 | 44 | _zrdr::Write(__sFILE*) | zrdr_edit.cpp | MATCH | - | _OutputASCII(file, this, 0) & 0xff |
| 140 | 0x241070 | 136 | CRdrEditor::~CRdrEditor() | zrdr_edit.cpp | MATCH | - | the stack deque (+0x2c) torn down, then ~CRdrFile; the port's by-value stack is its recorded layout (comment in the code) |
| 141 | 0x241100 | 92 | CRdrEditor::CRdrEditor() | zrdr_edit.cpp | MATCH | - | CRdrFile(), an empty deque copied into +0x2c (the temporary destroyed): both empty, the port's implicit member ctors |
| 253 | 0x2fa130 | 184 | zdb::CTexManager::ClearPktBufs(zdb::CTexManager&, bool) | ztex_manager.cpp | MATCH | - | every buffer but the first unless all (no NULL test, as the ELF): +0x1c m_pktbuf cleared and swapped with an empty vector (the ELF clears twice), +0x18 m_chainp NULL |
| 255 | 0x2fbb90 | 184 | zdb::CGSTexBuffer::RelocateAll() | ztex_manager.cpp | MATCH | - | next = +0x8; palettes: +0x0 != next -> next, next += (lhu +0x4) / 256; textures: handle +0xc texture +0x8 likewise, next += lhu +0x2e |
| 256 | 0x2fc550 | 184 | zdb::CDynTexList::Add(zdb::CTexPalette*, bool) | ztex_manager.cpp | MATCH | - | check: listed -> return; appended at the end (the ELF reserves size + 1 when full: capacity only) |
| 257 | 0x2fca70 | 180 | zdb::CGSTexBuffer::CGSTexBuffer() | ztex_manager.cpp | MATCH | - | the three vectors empty; +0x4 1, +0x8, +0xc, +0x10, +0x14, +0x18, +0x0 0 |
| 254 | 0x2fafa0 | 172 | zdb::CTexManager::WipePktBuf() | ztex_manager.cpp | MATCH | - | every non-NULL buffer of m_texmanager: as #253; the ELF reads the count once (nothing changes it in the loop) |
| 258 | 0x2fcb40 | 12 | zdb::CBatchRelocator::TakeDrawPacket(uint16*, unsigned int) | ztex_manager.cpp | MATCH | - | tail zSysFifoKick(spr, qwc) |
| 282 | 0x315420 | 108 | PlacedExplosive::PreTick(float) | zwep_explosive.cpp | MATCH | - | m_state (lbu +0xa) 3: +0x8c = m_world RegProximityDelayed(+0x20 di, this + 0x38, m_ammo GetExplosionRadius()), SetProjectileState(4, true); 1 |
| 284 | 0x315660 | 172 | PlacedExplosive::~PlacedExplosive() | zwep_explosive.cpp | MATCH | - | DeleteTextureAssetCharacter(2, +0x18 m_instance); m_shottype (lbu +0x9) 1 -> ReleaseDirectFireDI(&+0x20, &+0x24), else ReleaseIndirectFireDI; then ~CZProjectile |
| 285 | 0x315710 | 68 | PlacedExplosive::PlacedExplosive() | zwep_explosive.cpp | MATCH | - | CZProjectile(), vtable, +0xa8 0, +0x74 9999999f (0x4b18967f) |
| 283 | 0x315650 | 12 | PlacedExplosive::RemoteDetonate() | zwep_explosive.cpp | MATCH | - | sb 1 at +0xa8 |
| 1 | 0x1735e0 | 44 | testUnload() | database.cpp | MATCH | - | theMission.Close(), CSnd::m_listener NULL, UnloadTheWorld(), 1 |
| 259 | 0x2f9600 | 172 | po2(unsigned int) | ztex_read.cpp | MATCH | - | n < 3, 5, 9, 17, 33, 65, 129, 257, 513 (sltiu) -> 1..9, else 10 |
