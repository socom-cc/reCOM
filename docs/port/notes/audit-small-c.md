# Audit of list small-c (2026-11-19, socom-port-audit-small-c)

296 small functions (24,624 bytes, each under 200 bytes) in 29 files: Apps/FTS (hud_lensflare,
hud_teammatenames, main), zAI (ai_map, ai_path), zArchive zar_main, zCamera zcam_main, zEntity
ent_main, zFTS fts_network_dme, zGame (game_engine, game_state), zGraph graph_route, zMath
(zmath_main, zmath_pnt4d), zNetwork (zNetMedius, zNetVoice), zNode node_main, zSave zsav_manager,
zSeal (ai_target, seal_aifollow, seal_anim, seal_cfg, seal_ex), zSystem zsys_spr, zValve valve_main,
zVehicle vehicle_main, zVideo zvid_main, zVisual (vis_main, vis_texfx). HEAD a17e5177. Judged file
by file in the scan's rank order, from the by-file packets.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 273 |
| DEFECT-FIXED | 19 (A 1, B 2, C 16) |
| DEVIATION-KEPT | 4 |
| UNJUDGED | 0 |

Defect rate 19 / 296 (A 1, B 2, C 16).

Fixes:
- A, #239 CZSealBody::GetMaxZMotion: the ELF switches on the body's current state (lb +0x11d) and
  writes the forward maximum first, the backward second (0x27dfa8..0x27dfe0); the port tested
  m_desiredState and wrote backward first, so CSealCtrl::GetSpeedFromThrottle /
  GetThrottleFromSpeed (axis 0 reads the first output) scaled AI forward motion by the backward
  maximum.
- B, #65 CEntity::SetDisplayName: a NULL name leaves no name (beqz 0x1ee720); the port called
  _strdup(NULL), whose strlen crashes. Masked here (the single-player caller passes a name).
- B, #231 CSealCtrlAi::SetFollowMaster: the seal itself as master stores nothing (beq 0x2e1d64 over
  both stores); the port stored the master anyway.
- C, #260 / #261 CValve::FreeName / SetName, #185 / #193 / #194 / #195 / #197 CNode::SetModelname /
  FreeAtom / ShrinkAtomBasePtrs / AllocateAtomBasePtrs / SetName, #65: the alloc tags are the ELF's
  file / line ("valve_main.cpp" 448 / 438, "node_main.cpp" 2759 / 2762, 1310, 1300 / 1302,
  1285 / 1290, 963 / 964, "ent_main.cpp" 407 / 408), not __FILE__ / __LINE__.
- C, #194 CNode::ShrinkAtomBasePtrs: only when fewer atoms are used than allocated (0x2261e8); the
  port also re-allocated when equal.
- C, #189 / #214 / #216 CNode::ReserveDI / ReserveChildren / ReserveVisuals: room for size more
  than the current size (0x225680, 0x227890, 0x227c70); ReserveDI was commented out, the others
  reserved size.
- C, #114 / #117 / #134 CZOnlineLobby::CreateClan / Censor / SetPlayerDescription: the text is
  memcpy'd 32 / 64 / 64 bytes (0x324678, 0x325174, 0x3290e4), not strncpy'd.
- C, #122 CZOnlineLobby::CreateGame: the inline CValve::Set(0) on "mp_persistent" has no NULL test
  (0x326934; Tick's copy has one, so the shared helper keeps it): written inline without it.
- C, #232 CAiSFollow::GetStatus: the jump table's order (0x457c60: 2 WAIT, 3 FOLLOW, 4 HIDE PLAN,
  5 HIDE WAIT, 6 HIDE FOLLOW, 7 HIDE), not the strings' order. Debug text.
- C, #221 CSaveManager::~CSaveManager: m_TempBuffer cleared only after its delete (0x3f7c50).

Kept deviations (reasons in the code): #92 CQuat::Apply loads the quaternion from an aligned local
(GCC does not align CQuat to 16; the ELF's lqc2 reads `this`, 0x221290); #124 / #127
CZOnlineLobby::Register / Login strncpy the stats literal where the ELF memcpys 256 bytes from a
47-byte literal (0x326ec8, 0x327078: the bytes past it are the port's unrelated rodata); #276
zVid_ZTestOnWriteSet builds the zon_writeon_dmaref qword (REF 5 -> zon_writeon, FLUSH, DIRECT 5,
read from the ELF) because the port has no definition of that object.

Leads for other lists: the CValve ctor 0x2f77e0 (not in this list) still tags its _strdup with
__FILE__ / __LINE__ (its inline SetName is the ELF's 438 tag); the LobbySetStateValve helper keeps
its NULL test for Tick (0x327d0c tests the valve).

What the packets lacked: the Medius record layouts for the zNetMedius rows (port/compat medius.h);
member offsets of CZNetwork, _zsys_public, CMission / CZNetGame, CWorld (m_grid embedded in DWARF,
a pointer in the port), CAiCell's m_rtflag bit and CZSealBody's state at +0x11d (mem.py); the
element type of CBodyAnimBlendStack for #245 (dw.py); Tick's copy of the valve set (0x327d08) to
judge the helper's NULL test for #122; the words of zon_writeon_dmaref for #276 (data, read from the
ELF: `wsl.ps1 dis.sh -r` fails because PowerShell binds `-r`, and Git Bash has no objdump); the
callers of GetMaxZMotion (seal_ctrl.cpp) to grade #239; _strdup's NULL behaviour and the
SetDisplayName callers to grade #65. Fifth arguments (t0) checked by hand for #2 and #10. Roughly
20 functions needed a lookup outside the packet.

Runs: default build linked (audit-small-c-default, 0 undefined); one fake-pad m8 smoke run
(pad_start.txt, smoke-m8, 170 s: the mission ran from 55 s to the end, about 95 s after the
cameras, 3,487 frames, no fault).

## Verdicts

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 260 | 0x2f74d0 | 104 | CValve::FreeName() | valve_main.cpp | DEFECT-FIXED | C | Pooled: m_name cleared, no free; else _free(m_name) when set, cleared; bit 0 of +0x7 cleared, others kept: agree. The _free was tagged __FILE__ / __LINE__, the ELF "valve_main.cpp" 448 (0x2f7500..0x2f7508): fixed. |
| 261 | 0x2f7540 | 180 | CValve::SetName(char const*) | valve_main.cpp | DEFECT-FIXED | C | Inlined FreeName, then _strdup(name) or NULL into +0x0, pooled bit cleared: agree. The _strdup tag was __FILE__ / __LINE__, the ELF "valve_main.cpp" 438 (0x2f75a4..0x2f75b4): fixed. |
| 262 | 0x2f7600 | 140 | CValve::AssignName(char*) | valve_main.cpp | MATCH | | Inlined FreeName, m_name = a1, bit 0 of +0x7 set (0x2f7654..0x2f7674): agree. |
| 263 | 0x2f8160 | 8 | CValve::CmdTickCmp(_zanim_cmd_hdr*, float*) | valve_main.cpp | MATCH | | Tail call VALVE_CMD_DATA::Compare on header + 4: agree. |
| 264 | 0x2f8700 | 44 | CValve::RegisterCommands() | valve_main.cpp | MATCH | | AddCmd(ZAnim, "VALVE", CmdParseCmp, begin 0, CmdTickCmp in t0, end 0 in t1): agree. |
| 265 | 0x2f8730 | 152 | debugValve(CValve*, bool) | valve_main.cpp | MATCH | | Walks valveWatch$1141 entries (name word +0, flag byte +4) calling strcmp on the valve's name and drops every result; nothing stored or returned: the port's empty body has the same effect. The scan's strings are the watch table's. |
| 102 | 0x322420 | 72 | CZOnlineLobby::SendEndGameReport() | zNetMedius.cpp | MATCH | | SessionKey 17 bytes to +0x0, MediusWorldID to +0x14, bytes +0x18 / +0x58 and word +0x78 zeroed, no memset (0x322420..0x322458): agree with medius.h's record. |
| 103 | 0x322470 | 8 | CZOnlineLobby::GetDMEJoinedCount() | zNetMedius.cpp | MATCH | | dme_joined_count returned. |
| 104 | 0x322480 | 136 | CZOnlineLobby::SyncGameClock(int) | zNetMedius.cpp | MATCH | | GameClock made once (Add longevity 2), DeleteChildren, type 2, real = 10.0f + (float)seconds (add.s $f1, $f0 at 0x3224e8), UpdateDependents: agree. |
| 105 | 0x3226f0 | 8 | CZOnlineLobby::MediusConnectionIndex() | zNetMedius.cpp | MATCH | | myConnectionIndex returned. |
| 106 | 0x322860 | 56 | CZOnlineLobby::ResetMissionSequence() | zNetMedius.cpp | MATCH | | i 0..10: first zero byte at +0x89 + i sets +0x94 = i and returns; unchanged otherwise: agree. |
| 107 | 0x3228a0 | 148 | CZOnlineLobby::SetMissionSequence(unsigned char, unsigned char*) | zNetMedius.cpp | MATCH | | 12 bytes seq -> +0x88 (the unrolled loop), +0x94 = index & 0xff (sw): agree; the scan's stores are the ELF's inlined copy. |
| 108 | 0x322940 | 152 | CZOnlineLobby::GetMissionSequence(unsigned char*, unsigned char*) | zNetMedius.cpp | MATCH | | *index = low byte of +0x94, 12 bytes +0x88 -> seq: agree. |
| 109 | 0x322ae0 | 16 | CZOnlineLobby::IsMemberOfClan() | zNetMedius.cpp | MATCH | | PlayerClanID != -1 (nor / sltu): agree. |
| 110 | 0x322af0 | 140 | CZOnlineLobby::DisbandClan() | zNetMedius.cpp | MATCH | | Open and state 11 tests, memset 44, session key at +0x15, message id type 62, ClanID +0x28 = StoredClanInfo+0x1c, MediusDisbandClan(cbDisbandClan): agree. |
| 111 | 0x323aa0 | 8 | cbClanInviteRevokeHack(...) | zNetMedius.cpp | MATCH | | Empty. |
| 112 | 0x323ab0 | 8 | cbAddPlayerToClan(...) | zNetMedius.cpp | MATCH | | Empty. |
| 113 | 0x323ac0 | 16 | CZOnlineLobby::ClanHasInvitations() | zNetMedius.cpp | MATCH | | ClanInvitationVec's count word (+0x4) != 0; the port's !empty() of its own vector: same test. |
| 114 | 0x324600 | 160 | CZOnlineLobby::CreateClan(char const*) | zNetMedius.cpp | DEFECT-FIXED | C | Open / state 11 tests, memset 108, type 90, TextFilterType 0, cbFilterClanName: agree. The ELF memcpys 32 bytes of the name to +0x2c (0x324678), the port strncpy'd: fixed. |
| 115 | 0x3249b0 | 8 | cbUpdateClanStats(...) | zNetMedius.cpp | MATCH | | Empty. |
| 116 | 0x3249c0 | 144 | CZOnlineLobby::GetAnnouncements() | zNetMedius.cpp | MATCH | | Open / state 11, uiv_MediusMOTD = "No Message", memset 44, type 24, MediusGetAnnouncements(cbGetAnnouncements): agree. |
| 117 | 0x325100 | 172 | CZOnlineLobby::Censor(char const*, void (*)(char const*, void*), void*) | zNetMedius.cpp | DEFECT-FIXED | C | No open test (both), memset 108, type 90, TextFilterType 1, appcallback / censor_userdata, cbCensor: agree. The ELF memcpys 64 bytes of the text (0x325174), the port strncpy'd: fixed. |
| 118 | 0x3251b0 | 52 | cbCensor(int, int, int, MediusTextFilterResponse*) | zNetMedius.cpp | MATCH | | appcallback(response + 21, censor_userdata) when set, both cleared: agree. |
| 119 | 0x3251f0 | 80 | CZOnlineLobby::RejoinRoom() | zNetMedius.cpp | MATCH | | Open test, LobbyWorldID >= 0 pushes 11 on the fifo (+0x64): agree. The ELF's v0 (0 closed, 1 open) is read by neither caller; the port's void is the header's. |
| 120 | 0x325430 | 168 | CZOnlineLobby::OnCorrectClanTeam() | zNetMedius.cpp | MATCH | | affiliation 0 -> 1; seals = aff >= 0; clan match = aff == id or -id; side = theMission.m_pNetGame (+0x584) ->m_net_team (+0x90) bit 0; the two false cases: agree (mem.py for the offsets). |
| 121 | 0x3254e0 | 12 | CZOnlineLobby::IsTeamGame() | zNetMedius.cpp | MATCH | | g_iCreateGameClanAffiliation != 0. |
| 122 | 0x3268f0 | 144 | CZOnlineLobby::CreateGame() | zNetMedius.cpp | DEFECT-FIXED | C | Open / state 11 (false), Create("mp_persistent", 1), the inline Set(0) (change 2 when the half was set, sh 0, MakeCallbacks), push 13, true: agree. The port's helper LobbySetStateValve tests the valve for NULL, which this copy lacks (0x326934; Tick's copy has it): the set is written inline here without the test. |
| 123 | 0x326e00 | 52 | CZOnlineLobby::RefreshGameList(C2D*) | zNetMedius.cpp | MATCH | | Open test, GetGameList(1), 1: agree. |
| 124 | 0x326e40 | 192 | CZOnlineLobby::Register(char const*, char const*) | zNetMedius.cpp | DEVIATION-KEPT | | Open test, m_id -1, 32-byte name / password memcpys when set, DoLogin 0, push 12, true: agree. The ELF memcpys 256 bytes from the 47-byte literal to PlayerInfo+0x48 (0x326ec8); the port strncpy's (zero tail): kept, as Login's, reason in the code (the bytes past the literal are the port's unrelated rodata). |
| 125 | 0x326f00 | 164 | CZOnlineLobby::Bailout() | zNetMedius.cpp | MATCH | | Open test, sleep zSys.timerTicksPerSecond (+0x20) while ThreadId, m_bNetwork (+0x9): MediusDisconnect / CloseBare, m_network_init (+0xd): zNetClose and m_bNetwork 0, m_isopen 0, ReleaseUIResources: agree. v0 1 unread by its caller. |
| 126 | 0x326fb0 | 60 | CZOnlineLobby::Logout() | zNetMedius.cpp | MATCH | | Open test, push 18: agree; v0 unread. |
| 127 | 0x326ff0 | 196 | CZOnlineLobby::Login(char const*, char const*) | zNetMedius.cpp | DEVIATION-KEPT | | As Register with DoLogin 1 (0x327088): agree; the same 256-byte literal copy (0x327078) kept as strncpy, reason in the code. |
| 128 | 0x3270c0 | 56 | CZOnlineLobby::UnInit() | zNetMedius.cpp | MATCH | | Open: m_isopen 0, ReleaseUIResources; m_isinit 0, g_bJoiningRandomGame 0: agree. |
| 129 | 0x327c40 | 8 | CZOnlineLobby::Close() | zNetMedius.cpp | MATCH | | m_isopen 0, tail call ReleaseUIResources. |
| 130 | 0x328b50 | 12 | CZOnlineLobby::GetKeyPair() | zNetMedius.cpp | MATCH | | &rsaKeyPair. |
| 131 | 0x328e00 | 88 | cbConnect(int) | zNetMedius.cpp | MATCH | | -1: push 2; else myConnectionIndex = a0, push 1: agree. |
| 132 | 0x328e60 | 48 | cbErrorMessage(int, int, int, MediusErrorMessage*) | zNetMedius.cpp | MATCH | | theLobby+0x58 handler("MP_MEDIUS_ERROR", message + 4) when set. |
| 133 | 0x328e90 | 8 | cbBuddyGetPermission(...) | zNetMedius.cpp | MATCH | | Empty. |
| 134 | 0x329080 | 156 | CZOnlineLobby::SetPlayerDescription(char const*) | zNetMedius.cpp | DEFECT-FIXED | C | memset 108, type 90, TextFilterType 1, appcallback = cbFilterPlayerDescription, userdata 0, cbCensor: agree. The ELF memcpys 64 bytes of the text (0x3290e4), the port strncpy'd: fixed. |
| 135 | 0x329380 | 132 | CZOnlineLobby::GetLadderRanking() | zNetMedius.cpp | MATCH | | No open test (both), memset 56, type 87, +0x28 m_id, +0x2c 1, +0x30 10, +0x34 1, cbGetLadderRanking: agree. |
| 136 | 0x329490 | 160 | CZOnlineLobby::GetLadderInfo() | zNetMedius.cpp | MATCH | | As #135 behind the open / state 11 tests, cbGetLadderPosition: agree. |
| 137 | 0x329530 | 176 | cbGetLadderPosition(int, int, int, MediusLadderPositionResponse*) | zNetMedius.cpp | MATCH | | Status (+0x1c) != 0: Surrounding(1, 10, 1); else Surrounding(pos +0x18, 10, 1) and LadderRanking (Add longevity 1, type 1, integer = pos): agree. |
| 138 | 0x32a020 | 12 | CZOnlineLobby::GetLowestLadderPosition() | zNetMedius.cpp | MATCH | | LadderRankingVec+0x10. |
| 139 | 0x32a030 | 12 | CZOnlineLobby::GetCurrentLadderPosition() | zNetMedius.cpp | MATCH | | LadderRankingVec+0xc. |
| 140 | 0x32a4e0 | 100 | cbTransferClanLeadership(...) | zNetMedius.cpp | MATCH | | Status +0x18 == 0: handler("MP_LEADERSHIP_TRANSFER_SUCCESS", 0), else ("MP_PLAYER_NOT_FOUND", 0), each when theLobby+0x58 is set: same effect as the port's handler test first. |
| 141 | 0x32a640 | 128 | cbFilterClanMessage(char const*, void*) | zNetMedius.cpp | MATCH | | memset 238, type 74, strncpy(+0x26, text, 200), cbSendClanMessage: agree. |
| 142 | 0x32ad40 | 16 | CZOnlineLobby::HasClanInvitations() | zNetMedius.cpp | MATCH | | InvitationVec count word != 0; the port's !empty(): same test. |
| 143 | 0x32aeb0 | 124 | CZOnlineLobby::DeclineClanInvitation(int) | zNetMedius.cpp | MATCH | | memset 248, type 71, +0x2c 2, +0x28 invitation, cbRespondToClanInvitation: agree. |
| 144 | 0x32af30 | 124 | CZOnlineLobby::AcceptClanInvitation(int) | zNetMedius.cpp | MATCH | | As #143 with +0x2c 1. |
| 145 | 0x32afb0 | 12 | cbRespondToClanInvitation(...) | zNetMedius.cpp | MATCH | | Tail call theLobby.CheckClanInvitations. |
| 146 | 0x32b660 | 100 | cbFindRoomByName(int, int, int, MediusFindWorldByNameResponse*) | zNetMedius.cpp | MATCH | | Status != 0: push 11; else LobbyWorldID = +0x44, push 19: agree. |
| 147 | 0x32bfb0 | 100 | cbFindGameByName(int, int, int, MediusFindWorldByNameResponse*) | zNetMedius.cpp | MATCH | | Status != 0: push 11; else MediusWorldID = +0x44, push 15: agree. |
| 148 | 0x32c140 | 8 | ConnectErrorStateHandler(CZOnlineLobby::LOBBY_STATE_FLAG) | zNetMedius.cpp | MATCH | | Empty. |
| 149 | 0x32c150 | 8 | CreateFailureStateHandler(CZOnlineLobby::LOBBY_STATE_FLAG) | zNetMedius.cpp | MATCH | | Empty. |
| 150 | 0x32c160 | 8 | ConnectSuccessStateHandler(CZOnlineLobby::LOBBY_STATE_FLAG) | zNetMedius.cpp | MATCH | | Empty. |
| 151 | 0x32c170 | 8 | LoginFailureStateHandler(CZOnlineLobby::LOBBY_STATE_FLAG) | zNetMedius.cpp | MATCH | | Empty. |
| 152 | 0x32c180 | 8 | RegistrationFailureStateHandler(CZOnlineLobby::LOBBY_STATE_FLAG) | zNetMedius.cpp | MATCH | | Empty. |
| 153 | 0x32c270 | 84 | cbSessionEnd(int, int, int, MediusSessionEndResponse*) | zNetMedius.cpp | MATCH | | Both branches push 0 (0x32c29c, 0x32c2b4): the port's single push. |
| 154 | 0x32c410 | 100 | cbSessionBegin(int, int, int, MediusSessionBeginResponse*) | zNetMedius.cpp | MATCH | | Status != 0: push 10; else 17 bytes response+0x1c -> SessionKey: agree. |
| 155 | 0x32c480 | 188 | AccountRegistrationStateHandler(CZOnlineLobby::LOBBY_STATE_FLAG) | zNetMedius.cpp | MATCH | | Only flag 1: memset 108, type 90, TextFilterType 0, 32 bytes of the account name to +0x2c, cbFilterAcctName: agree. |
| 156 | 0x32c610 | 196 | cbAccountRegistration(int, int, int, MediusAccountRegistrationResponse*) | zNetMedius.cpp | MATCH | | Status != 0: push 6; else memset 102, type 3, name to +0x26, password to +0x46 (32 each), cbAccountLoginAfterRegister: agree. |
| 157 | 0x32d2d0 | 192 | RefreshDMEJoinedCount() | zNetMedius.cpp | MATCH | | Outstanding, m_pNetGame->m_my_major_game_state (+0xdc lbu) == 2, late_joiner half != 0, accum 0, memset 44, type 31, +0x28 MediusWorldID, Outstanding = 1 when the call returns 0: agree. |
| 158 | 0x32d390 | 80 | cbRefreshDMEJoinedCount(int, int, int, MediusGameWorldPlayerListResponse*) | zNetMedius.cpp | MATCH | | Status 0: Stats[12] (+0x4c lb) == 'j' counts, EndOfList (+0x144) publishes and clears Outstanding: agree. |
| 159 | 0x32d3e0 | 12 | CZOnlineLobby::ForceStatusReport() | zNetMedius.cpp | MATCH | | ForceReport byte = 1. |
| 160 | 0x32d3f0 | 32 | cbDMENetPingCallback(NetErrorCode, char*, unsigned int) | zNetMedius.cpp | MATCH | | Error 14: 65000, else the time (a2): agree. |
| 161 | 0x32d410 | 8 | cbChatToggle(...) | zNetMedius.cpp | MATCH | | Empty. |
| 162 | 0x32d5d0 | 48 | cbClientDisconnect(int, int, char const*) | zNetMedius.cpp | MATCH | | handler("ON_CLIENT_CONNECT", 0) when set (the ELF's string, kept). |
| 163 | 0x32d600 | 48 | cbClientConnect(int, int, char const*) | zNetMedius.cpp | MATCH | | handler("ON_CLIENT_CONNECT", 0) when set. |
| 164 | 0x32dae0 | 8 | cbUpdateAccountStats(...) | zNetMedius.cpp | MATCH | | Empty. |
| 165 | 0x32daf0 | 8 | cbVersionServer(...) | zNetMedius.cpp | MATCH | | Empty. |
| 166 | 0x32db00 | 8 | cbSetGameListFilter(...) | zNetMedius.cpp | MATCH | | Empty. |
| 167 | 0x32db10 | 132 | CZOnlineLobby::QuitClan() | zNetMedius.cpp | MATCH | | Open test, memset 48, type 67, +0x2c PlayerClanID, +0x28 m_id, cbQuitClan: agree. |
| 168 | 0x32dba0 | 8 | cbQuitClan(...) | zNetMedius.cpp | MATCH | | Empty. |
| 169 | 0x32dbb0 | 88 | cbGetPolicyRequest(int, int, int, MediusGetPolicyResponse*) | zNetMedius.cpp | MATCH | | Status 0: UsagePolicy (longevity 1) = response + 0x1c: agree. |
| 170 | 0x32dc10 | 144 | CZOnlineLobby::BanSelfFromGame() | zNetMedius.cpp | MATCH | | Open test, memset 56, type 86, +0x2c 120, +0x34 0, +0x28 m_id, +0x30 MediusWorldID: agree. |
| 171 | 0x32dca0 | 8 | cbBanSelfFromGame(...) | zNetMedius.cpp | MATCH | | Empty. |
| 172 | 0x32df70 | 40 | _roomplayer_sort_aux(...) | zNetMedius.cpp | MATCH | | !(strcmp(a+0x24, b+0x24) > 0) (slt / xori): agree. |
| 173 | 0x32dfa0 | 172 | GetRoomList(int) | zNetMedius.cpp | MATCH | | UpdateRoomListDisplay, open and state 11: RoomListPage = page, memset 42, type 27, PageSize 999 (+0x28), PageID = (short)RoomListPage (+0x26), cbRoomList: agree. |
| 174 | 0x32f800 | 180 | GamePassesTypeFilter(int) | zNetMedius.cpp | MATCH | | 0 any; 101: 2 / 5; 102: 1 / 7 / 9; 103: 4 / 6; else mission == filter (each failed group falls to the equality): agree. |
| 175 | 0x32f8c0 | 184 | CZOnlineLobby::~CZOnlineLobby() | zNetMedius.cpp | MATCH | | Close inline (open: clear, ReleaseUIResources), m_isinit: UnInit inline; the deque teardown is the compiler's: agree. |
| 176 | 0x32fac0 | 96 | CZOnlineLobby::PasswordSecurity() | zNetMedius.cpp | MATCH | | SecurePassword (type 1) half == 0: PLAYERPASSWORD (longevity 1) = "": agree. |
| 177 | 0x32fdd0 | 112 | BriefingRoom::LastClone() | zNetMedius.cpp | MATCH | | The ELF's recursion unrolled four deep along +0xa0 ends on the last clone: the port's loop. |
| 185 | 0x2248a0 | 108 | zdb::CNode::SetModelname(char const*) | node_main.cpp | DEFECT-FIXED | C | Old name freed and cleared, then _strdup(name) or NULL into +0xb4: agree. Tags were __FILE__ / __LINE__, the ELF "node_main.cpp" 2759 / 2762 (0x2248c4, 0x2248ec): fixed. |
| 186 | 0x224b00 | 44 | zdb::CLight::SetActive(bool) | node_main.cpp | MATCH | | Bit 0 of +0x5c = (a1 != 0), others kept; old bit returned (sltu at 0x224b20): agree. |
| 187 | 0x225580 | 56 | zdb::CNode::VisualEffectsTick(float, void*) | node_main.cpp | MATCH | | CDecal / CRipple / CTextureFX::Tick(dT), returns 0: agree. |
| 188 | 0x2255c0 | 188 | zdb::CNode::AddDI(zdb::CDI*) | node_main.cpp | MATCH | | NULL / Exists tests, +0x14 refcount++, insert at end, bit 1 of +0x9a and bit 4 of +0x5d (m_hasDI, bit 12 of the word) set, 1; else 0: agree. |
| 189 | 0x225680 | 16 | zdb::CNode::ReserveDI(int) | node_main.cpp | DEFECT-FIXED | C | The ELF reserves size + m_di.size_ (0x225680..0x225688); the port's body was commented out (no reserve): written. Capacity only. |
| 190 | 0x226110 | 8 | zdb::CNode::SetAtomCnt(int) | node_main.cpp | MATCH | | sh a1 at +0xa8. |
| 191 | 0x226120 | 52 | zdb::CNode::GetAtom(int) | node_main.cpp | MATCH | | index < m_AtomAlloc (lh +0xaa): m_Atom[index], else NULL. |
| 192 | 0x226160 | 32 | zdb::CNode::InsertAtom(zdb::CGridAtom*) | node_main.cpp | MATCH | | m_Atom[m_AtomCnt++] = atom. |
| 193 | 0x226180 | 68 | zdb::CNode::FreeAtom() | node_main.cpp | DEFECT-FIXED | C | Free when set, +0xa0 cleared, +0xaa 0: agree. Tag was __FILE__ / __LINE__, the ELF 1310 (0x22619c): fixed. |
| 194 | 0x2261d0 | 132 | zdb::CNode::ShrinkAtomBasePtrs() | node_main.cpp | DEFECT-FIXED | C | The ELF shrinks only when m_AtomCnt < m_AtomAlloc (slt / beqz 0x2261e8); the port also re-allocated when equal: fixed (same contents, a needless allocation). malloc / free tags 1300 / 1302 (0x2261f8, 0x226230): fixed. Copy and the new alloc = count: agree. |
| 195 | 0x226260 | 184 | zdb::CNode::AllocateAtomBasePtrs(int, int) | node_main.cpp | DEFECT-FIXED | C | Bits 1 and 2 of +0x5c (dynamic motion / light) choose (x + 1) * (y + 1) else x * y; malloc when none, realloc when the alloc is smaller: agree. Tags 1285 / 1290 (0x2262c4, 0x2262fc): fixed. |
| 196 | 0x226320 | 120 | zdb::CNode::DeleteChildren() | node_main.cpp | MATCH | | While +0x6c: child = data[0], virtual DeleteChild (slot +0x1c) == 0 and child: deleting dtor (slot +0x8, a1 1) = the port's delete: agree. |
| 197 | 0x2266d0 | 120 | zdb::CNode::SetName(char const*) | node_main.cpp | DEFECT-FIXED | C | Old name freed unless NULL or UNNAMED_NODE; _strdup(name) or UNNAMED_NODE into +0x90: agree. Tags 963 / 964 (0x2266fc, 0x22671c) were __FILE__ / __LINE__: fixed. |
| 198 | 0x226870 | 112 | zdb::CLightMap::~CLightMap() | node_main.cpp | MATCH | | Vtable stores and CNode dtor only: the compiler's. |
| 199 | 0x226a20 | 184 | zdb::CLight::UpdateBBox(bool) | node_main.cpp | MATCH | | range = min when max <= min (c.le.s 0x226a30), box +-range, then the m_use_parent_bbox (bit 6 of +0x5f) chain over two parents and the third's GetBBox: agree. |
| 200 | 0x226ae0 | 96 | zdb::CLight::~CLight() | node_main.cpp | MATCH | | Empty body. |
| 201 | 0x226b40 | 96 | zdb::CLight::CLight() | node_main.cpp | MATCH | | type 8, +0xc0 / +0xc8 0, diffuse 128.0f x3, opacity 64.0f, +0xe4 0: agree. |
| 202 | 0x226f30 | 24 | zdb::CNode::Rendered() | node_main.cpp | MATCH | | +0x99 byte == low byte of zVid+0x10. |
| 203 | 0x226f50 | 92 | zdb::CNode::GetRadius() | node_main.cpp | MATCH | | (x x + y y) + z z per corner (adda / madd), max chosen when min <= max, tail call sqrtf: agree. |
| 204 | 0x226fb0 | 92 | zdb::CNode::GetRadiusSq() | node_main.cpp | MATCH | | As #203 without the sqrtf. |
| 205 | 0x227010 | 40 | zdb::CNode::GetRotation(CPnt3D*) const | node_main.cpp | MATCH | | m_matrix.ToEuler(rotation), rotation returned. |
| 206 | 0x227060 | 8 | zdb::CNode::GetScale() | node_main.cpp | MATCH | | [0][0] in $f0. |
| 207 | 0x227070 | 100 | zdb::CNode::SetScale(CPnt3D*) | node_main.cpp | MATCH | | Diagonal +0x0 / +0x14 / +0x28 = x / y / z, bit 1 of +0x9a, OnMove (slot +0x10) when m_nodeEx: agree. |
| 208 | 0x2270e0 | 88 | zdb::CNode::SetScale(float) | node_main.cpp | MATCH | | The same with f12 three times. |
| 209 | 0x227140 | 88 | zdb::CNode::SetRotation(CPnt3D const*) | node_main.cpp | MATCH | | SetRotate, modified, OnMove: agree. |
| 210 | 0x2271a0 | 96 | zdb::CNode::SetRotation(CQuat const&) | node_main.cpp | MATCH | | ToMatrix(&m_matrix), modified, OnMove: agree. |
| 211 | 0x227200 | 108 | zdb::CNode::SetPosition(float, float, float) | node_main.cpp | MATCH | | +0x30..+0x38, virtual UpdateGrid (slot +0x10; virtual in the port too), modified, OnMove: agree. |
| 212 | 0x227270 | 104 | zdb::CNode::SetMatrix(CMatrix const*) | node_main.cpp | MATCH | | sceVu0CopyMatrix = the port's copy, then as #211. |
| 213 | 0x2272e0 | 72 | zdb::CNode::UpdateGrid() | node_main.cpp | MATCH | | Parent set and its half type (+0x58) == 6: CGrid::Update(this) on the world's grid (embedded at +0x670 in the ELF, a pointer in the port's CWorld: self-consistent), 1; else 0: agree. |
| 214 | 0x227890 | 16 | zdb::CNode::ReserveChildren(int) | node_main.cpp | DEFECT-FIXED | C | The ELF reserves size + m_child.size_ (0x227890); the port reserved size: fixed. Capacity only. |
| 215 | 0x2278a0 | 52 | zdb::CNode::RemoveFromParent() | node_main.cpp | MATCH | | Parent's virtual DeleteChild (slot +0x1c) when set. |
| 216 | 0x227c70 | 16 | zdb::CNode::ReserveVisuals(int) | node_main.cpp | DEFECT-FIXED | C | As #214 for m_visual (0x227c70): fixed. |
| 217 | 0x227e10 | 36 | zdb::CNode::Release() | node_main.cpp | MATCH | | +0xac--, clamped at 0, returned. |
| 218 | 0x2285a0 | 20 | zdb::CNode::Copy() const | node_main.cpp | MATCH | | Tail call virtual _Copy(NULL) (slot +0xc). |
| 90 | 0x220590 | 24 | CFRect::CFRect() | zmath_main.cpp | MATCH | | Four words zeroed. |
| 91 | 0x2205b0 | 88 | zMath_Init() | zmath_main.cpp | MATCH | | init_trig_table, CVU(0), FlushCache(0), Code(.dma.1 & 0x0fffffff, 0), CVU dtor: agree. |
| 92 | 0x221240 | 164 | CQuat::Apply(CPnt3D const*, CPnt3D*, int) const | zmath_main.cpp | DEVIATION-KEPT | | Per point (count down to 0): point w 0, qmtc2.i / lqc2 vf1 / vf2, vcallms 0x60, sqc2 vf3, x y z out: agree. The port loads the quaternion from an aligned local copy where the ELF's lqc2 reads `this` (0x221290): kept, reason in the code (GCC does not align CQuat to 16). |
| 93 | 0x2212f0 | 76 | CQuat::ToEuler(CPnt3D*) const | zmath_main.cpp | MATCH | | sceVu0UnitMatrix (the port's inline CMatrix ctor), ToMatrix, CMatrix::ToEuler: agree. |
| 94 | 0x221340 | 168 | CQuat::Mul(CQuat const*, CQuat*) const | zmath_main.cpp | MATCH | | Cross (w 0), += this * other.w, += other * this.w (each read after out is written, as the port), w = out.w - (tmp.w + dot) (0x2213c4..0x2213c8): agree; the scan's float counts are the VU0 library calls written out. |
| 95 | 0x2214e0 | 96 | CQuat::Normalize() | zmath_main.cpp | MATCH | | The ELF inlines #96 on this (w w + dot, 1 / sqrtf, scale all four), returns this: the port's call. |
| 96 | 0x221540 | 104 | CQuat::Normalize(CQuat*) const | zmath_main.cpp | MATCH | | sqrtf(w w + (x x + y y) + z z) (add.s 0x22156c), 1.0f / it, out = this * scale: agree. |
| 97 | 0x2216b0 | 168 | CQuat::MakeYXRot(float, float) | zmath_main.cpp | MATCH | | sin / cos of 0.5f * yaw then of 0.5f * pitch; w = cy cx, x = cy sx, y = sy cx, z = (-sy) sx: agree. |
| 98 | 0x221760 | 84 | CQuat::MakeZRot(float) | zmath_main.cpp | MATCH | | z = sin, w = cos of 0.5f * a, x y 0. |
| 99 | 0x2217c0 | 84 | CQuat::MakeYRot(float) | zmath_main.cpp | MATCH | | y = sin, w = cos, x z 0. |
| 100 | 0x221820 | 84 | CQuat::MakeXRot(float) | zmath_main.cpp | MATCH | | x = sin, w = cos, y z 0. |
| 266 | 0x1a2d20 | 52 | CVehicleRdrEntry::GetStartDir() const | vehicle_main.cpp | MATCH | | m_startIndex (+0x108) <u m_count (+0x70): the 20-byte start's dir (+0x84), else 0: agree. |
| 267 | 0x1a2d60 | 48 | CVehicleRdrEntry::GetStartPos() const | vehicle_main.cpp | MATCH | | The same test, the start's name (+0x74 + 20 i), else NULL. |
| 268 | 0x1a2d90 | 56 | CVehicleRdrEntry::GetStart(unsigned int, char const*&, int&) const | vehicle_main.cpp | MATCH | | index <u count: name and dir written, 1; else nothing written, 0: agree. |
| 269 | 0x1a2dd0 | 124 | CVehicleRdrEntry::Randomize(bool) | vehicle_main.cpp | MATCH | | first, count 0 or respawn (+0xf4): 0; count - 1 == 0: 0; else rand() % count (signed div): agree. |
| 270 | 0x1a2e50 | 48 | CVehicleRdrEntry::SetCharacterName(char const*) | vehicle_main.cpp | MATCH | | NULL: byte +0x20 0; else strncpy(+0x20, name, 48): agree. |
| 271 | 0x1a3720 | 140 | CVehicleRdr::GetEntryByName(char const*) const | vehicle_main.cpp | MATCH | | NULL name: NULL; 268-byte entries from data_ to data_ + size_, first strcasecmp == 0 returned: agree. |
| 272 | 0x1a37b0 | 88 | CVehicleRdr::Open(char const*) | vehicle_main.cpp | MATCH | | zrdr_read(name, 0, 0), Load, zrdr_free, Load's bool returned: agree. |
| 273 | 0x1a3810 | 76 | CVehicleRdr::Close() | vehicle_main.cpp | MATCH | | clear, empty temporary, clear again (a no-op on the emptied vector), swap, temporary destroyed: the port's clear and swap. |
| 274 | 0x1a38e0 | 52 | CVehicleRdr::CVehicleRdr() | vehicle_main.cpp | MATCH | | The vector base only. |
| 275 | 0x1a5270 | 120 | AI_PARAMS::AI_PARAMS() | vehicle_main.cpp | MATCH | | The 15 words: mask 0, 0x3f4ccccd, 0x3f19999a, 0x3e4ccccd, 0.5, 0.5, 0x3f4ccccd, 400, 60, 0xbd99999a (-0.075f), 25, respawn 0, 0.75, 0.5, m_veh 0: agree (the port's comment gives 0.075's word unsigned). |
| 34 | 0x1e44b0 | 8 | zdb::CCamera::GetVuMtxSet() | zcam_main.cpp | MATCH | | +0x3c0 m_mtxSet.m_vu returned. |
| 35 | 0x1e4820 | 120 | zdb::CCamera::GetScaledZSquared(CPnt3D*) | zcam_main.cpp | MATCH | | (row3 - p) * row2 summed x + y + z (vmulax / vmadday / vmaddz), squared, times m_RangeScale (mul.s 0x1e488c): agree. |
| 36 | 0x1e48a0 | 108 | zdb::CCamera::GetZ(CPnt3D*) | zcam_main.cpp | MATCH | | The same depth unsquared. |
| 37 | 0x1e4b10 | 168 | zdb::CCamera::InsideMidPlane(zdb::CCell*) | zcam_main.cpp | MATCH | | The cell's translation's depth, minus CNode::GetRadius; 0 when mid <= that (c.le.s 0x1e4b90), else 1: agree. |
| 38 | 0x1e4bc0 | 108 | zdb::CCamera::GetScaledRangeSquared(CPnt3D*) | zcam_main.cpp | MATCH | | copy.Sub(row3, &copy), scale * ((x x + y y) + z z): agree. |
| 39 | 0x1e4c30 | 12 | zdb::CCamera::GetPlayerCanSeeRegion() | zcam_main.cpp | MATCH | | +0x2a0 | 1. |
| 40 | 0x1e4c40 | 52 | zdb::CCamera::PlayerCanSeeRegion(unsigned int) | zcam_main.cpp | MATCH | | mask 0 -> 1; no region test: 1; else ((+0x2a0 | 1) & mask) != 0: agree. |
| 41 | 0x1e4c80 | 52 | zdb::CCamera::CanSeeRegion(unsigned int) | zcam_main.cpp | MATCH | | mask 0 -> 1; no test: 1; else (+0x2a8 & mask) != 0. |
| 42 | 0x1e4cc0 | 40 | zdb::CCamera::SetPlayerCanSeeRegions(unsigned int) | zcam_main.cpp | MATCH | | Nonzero: +0x2a0 = r, +0x2a8 = (+0x2a0 | 1) | +0x2a4. |
| 43 | 0x1e4cf0 | 40 | zdb::CCamera::SetCameraCanSeeRegions(unsigned int) | zcam_main.cpp | MATCH | | Nonzero: +0x2a4 = r, the same +0x2a8. |
| 44 | 0x1e5410 | 12 | zdb::CCamera::SetNearClip(float) | zcam_main.cpp | MATCH | | +0xe8 and +0x48c. |
| 45 | 0x1e5420 | 40 | zdb::CCamera::SetMidClip(float) | zcam_main.cpp | MATCH | | +0xec; !(mid <= far): +0xf0 and +0x49c = mid. |
| 46 | 0x1e5450 | 12 | zdb::CCamera::SetFarClip(float) | zcam_main.cpp | MATCH | | +0xf0 and +0x49c. |
| 47 | 0x1e5460 | 144 | zdb::CCamera::SetHalfVerticalFOVRadians(float) | zcam_main.cpp | MATCH | | Argument ignored (ELF quirk kept): vfov = (448 * hfov) / 640, sin / cos, tan = sin / cos and cot = 1 / tan from the stored values: agree. |
| 48 | 0x1e54f0 | 124 | zdb::CCamera::SetHalfHorizontalFOVRadians(float) | zcam_main.cpp | MATCH | | hfov, sin / cos, tan, cot, m_scrZ = +0x4a0 * cot: agree. |
| 49 | 0x1e7270 | 8 | zdb::CCamera::CmdTickGetRegions(_zanim_cmd_hdr*, float*) | zcam_main.cpp | MATCH | | m_do_region_test byte returned. |
| 50 | 0x1e7280 | 108 | zdb::CCamera::CmdParseGetRegions(_zrdr*) | zcam_main.cpp | MATCH | | NULL reader: NULL; calloc(1, 4, "zcam_main.cpp", 264), data_size 4, timeless: agree. |
| 51 | 0x1e72f0 | 40 | zdb::CCamera::CmdTickSetRegions(_zanim_cmd_hdr*, float*) | zcam_main.cpp | MATCH | | Bit 0 of +4 sets / clears m_do_region_test, 1. |
| 52 | 0x1e73f0 | 16 | zdb::CCamera::CmdTickIndoorsTest(_zanim_cmd_hdr*, float*) | zcam_main.cpp | MATCH | | CWorld::m_world +0xc0 camera, byte +0x2ac returned. |
| 53 | 0x1e7400 | 108 | zdb::CCamera::CmdParseIndoorsTest(_zrdr*) | zcam_main.cpp | MATCH | | As #50 with line 207. |
| 54 | 0x1e7470 | 56 | zdb::CCamera::CmdTickControlSwitch(_zanim_cmd_hdr*, float*) | zcam_main.cpp | MATCH | | Bit 0 of +4: m_dynamics_controlled 0; else bit 1: 1; returns 1. |
| 55 | 0x1e74b0 | 124 | zdb::CCamera::CmdParseAcquire(_zrdr*) | zcam_main.cpp | MATCH | | calloc(1, 8, line 178), data_size 8, timeless, bit 1 of +4: agree. |
| 56 | 0x1e7530 | 132 | zdb::CCamera::CmdParseRelease(_zrdr*) | zcam_main.cpp | MATCH | | calloc(1, 8, line 162), data_size 8, timeless, bit 0 of +4: agree. |
| 57 | 0x1e76e0 | 152 | zdb::CCamera::~CCamera() | zcam_main.cpp | MATCH | | The two vectors and the CNode dtor: the compiler's. |
| 252 | 0x2f57b0 | 88 | CSPR::Copy(_word128*, _word128*, int) | zsys_spr.cpp | MATCH | | Wait while D9_CHCR bit 8, MADR = from, SADR = to, QWC = qwc, CHCR 0x101, returns to + qwc qwords: agree. |
| 253 | 0x2f5a20 | 136 | zSysFifoEnd() | zsys_spr.cpp | MATCH | | written = sprPx (zSys+0x18) * 0x1f30 + 0x70000000, flipped once when it is the kicked half, sprPx flipped, tag 0x70000000 / 0 / 0x11000000 x2, tail call zSysFifoKick(p, 1): agree. |
| 254 | 0x2f5ab0 | 148 | zSysSprGetPacket(uint16**) | zsys_spr.cpp | MATCH | | As #253's half choice; *end = sprPacketEnd[sprPx] - 16 bytes when end is set; sprPx flipped; written returned: agree. |
| 255 | 0x2f5cf0 | 48 | zSysFifoInit() | zsys_spr.cpp | MATCH | | RBOR (0x1000e050) = mfifoBase, RBSR (0x1000e040) = 0x3fff0, sync. |
| 256 | 0x2f5d20 | 16 | zSysAddDMA(uint16*, uint16*) | zsys_spr.cpp | MATCH | | One qword copied, to + 16 returned. |
| 257 | 0x2f5d30 | 96 | CVU::Code(uint16*, unsigned int) | zsys_spr.cpp | MATCH | | +0x8 = code, sceDmaSync(+0x4, 0, 0), sceDmaSend, sync again: agree. The ELF's v0 0 is not read by zMath_Init. |
| 258 | 0x2f5d90 | 132 | CVU::~CVU() | zsys_spr.cpp | MATCH | | m_refCount--, at 0 with unit 0: DisableIntc(4), RemoveIntcHandler(4, m_VifHandlerID): agree. |
| 259 | 0x2f5f20 | 48 | InterruptFromVIF0(int) | zsys_spr.cpp | MATCH | | cause 4: m_running 0, VIF0_FBRST 8, sync; then sync, ei, 0: agree. |
| 24 | 0x1d8740 | 104 | zar::CZAR::ReleaseDataBuffer() | zar_main.cpp | MATCH | | NULL buffer: 0; dynamic_cast<CBufferIO*>(m_pFile) Release when it is one; buffer returned, +0x18 cleared: agree. |
| 25 | 0x1d8cd0 | 96 | zar::CZAR::GetSize(char const*) | zar_main.cpp | MATCH | | Front open key or m_root, FindKey (no NULL test, both), -1 or key+0x10: agree. |
| 26 | 0x1d8d30 | 40 | zar::CZAR::GetOpenKey() | zar_main.cpp | MATCH | | Empty list: m_root, else the front key. |
| 27 | 0x1d8d60 | 100 | zar::CZAR::OpenKey(zar::CKey*) | zar_main.cpp | MATCH | | Non-NULL key inserted at the list's head (push_front), key returned. |
| 28 | 0x1d8dd0 | 84 | zar::CZAR::FindKey(char const*) | zar_main.cpp | MATCH | | Front key or m_root; NULL: 0; else CKey::FindKey. |
| 29 | 0x1d9680 | 192 | zar::CZAR::Close(bool) | zar_main.cpp | MATCH | | Owned stream: Close (slot +0xc), freed, both pointers 0; else m_pFile Close; m_key_buffer cleared and swapped empty; m_root erased; m_stable Destroy: agree (the delete as Close() 0x1d97a0, judged in medium-rest-b). |
| 30 | 0x1d98f0 | 20 | zar::CZAR::CloseKeepDir() | zar_main.cpp | MATCH | | Tail call m_pFile Close (slot +0xc). |
| 31 | 0x1d9910 | 140 | zar::CZAR::SetFilename(char const*) | zar_main.cpp | MATCH | | Own name (not NULL / DEFAULT): same pointer returns, else _free 89 and cleared; NULL / DEFAULT -> DEFAULT_ZAR_NAME, else _strdup 96: agree. |
| 32 | 0x1d9eb0 | 8 | zar::CZAR::DoMemAlign(bool) | zar_main.cpp | MATCH | | m_memalign = a0 byte. |
| 33 | 0x1d9ec0 | 8 | zar::CZAR::DoMemAlign() | zar_main.cpp | MATCH | | m_memalign returned. |
| 58 | 0x1ee0f0 | 152 | CEntityList::GetEntityByIndex(unsigned int) const | ent_main.cpp | MATCH | | index >= size_: NULL; else index steps from the head, that node's entity: the port's walk to the end gives the same. |
| 59 | 0x1ee390 | 48 | CEntity::OnDeath() | ent_main.cpp | MATCH | | Bit 3 of +0xdd cleared, others kept; tail call m_control (+0xc0) slot +0x18 (the port's virtual OnDeath). |
| 60 | 0x1ee3d0 | 8 | CEntity::OnRecycleEntity(CEntity*) | ent_main.cpp | MATCH | | Empty. |
| 61 | 0x1ee3e0 | 8 | CEntity::UpdateAiMapLoc(bool&) | ent_main.cpp | MATCH | | *changed = 0 (byte). |
| 62 | 0x1ee3f0 | 72 | CEntity::GetTargetPosW(CPnt3D*) | ent_main.cpp | MATCH | | Virtual GetPosW (slot +0xc), x y z copied, pos returned. |
| 63 | 0x1ee6d0 | 8 | CEntity::OnMissionStart() | ent_main.cpp | MATCH | | Empty. |
| 64 | 0x1ee6e0 | 8 | CEntity::ResetToInitialState() | ent_main.cpp | MATCH | | Empty. |
| 65 | 0x1ee6f0 | 112 | CEntity::SetDisplayName(char const*) | ent_main.cpp | DEFECT-FIXED | B | Old name freed, +0x14 cleared, then _strdup(name) only when name is set, else 0 (beqz 0x1ee720 / 0x1ee744): the port called _strdup(NULL) (strlen crash) for a NULL name: fixed. Masked here (the single-player caller passes a non-empty name; the network creators can pass others). Tags 407 / 408 were __FILE__ / __LINE__: fixed. |
| 66 | 0x1ee760 | 40 | CEntity::JoinTeam(unsigned int) | ent_main.cpp | MATCH | | team <u 32: +0xc4 |= 1 << team. |
| 67 | 0x1ee790 | 8 | CEntity::SetTeamMask(unsigned int) | ent_main.cpp | MATCH | | +0xc4 = mask. |
| 68 | 0x1ee7a0 | 8 | CEntity::GetNode() | ent_main.cpp | MATCH | | +0x1c. |
| 69 | 0x1ee7b0 | 188 | CEntity::~CEntity() | ent_main.cpp | MATCH | | _free(name, "ent_main.cpp", 370) when set, +0x14 0, SetIncludeInTargetList(false); the CSaferStr array and target vector are the compiler's: agree. |
| 70 | 0x1eec50 | 24 | CEntity::GetEntityIndex(CEntity const*) | ent_main.cpp | MATCH | | NULL: -1, else +0x8. |
| 71 | 0x1ef620 | 80 | CEntity::RecycleEntity(CEntity*) | ent_main.cpp | MATCH | | Appended to m_recycle, SetIncludeInTargetList(false); the ELF's v0 1 is unread by CMission::RecycleEntity. |
| 72 | 0x1ef670 | 132 | CEntity::CreateEntity(CEntity*, bool) | ent_main.cpp | MATCH | | recycler_index -1: m_index = m_list size, appended, SetIncludeInTargetList(include); else m_index = recycler_index: agree. |
| 73 | 0x1ef700 | 160 | CEntity::EntityIsValid(CEntity*) | ent_main.cpp | MATCH | | Walk of m_list, 1 on the first match, else 0. |
| 74 | 0x1ef7a0 | 12 | CEntity::CloseRecycler() | ent_main.cpp | MATCH | | recycler_index = -1. |
| 75 | 0x1ef7b0 | 8 | CEntity::OpenRecycler(unsigned int) | ent_main.cpp | MATCH | | recycler_index = a0. |
| 227 | 0x2e1860 | 68 | CZSealBody::GetStanceFromState(SEAL_STATE, SEAL_STANCE) | seal_aifollow.cpp | MATCH | | State byte 0 / 1 / 2 -> stance 0 / 1 / 2, else the stance argument: agree. |
| 228 | 0x2e1ba0 | 104 | CZSealBody::InvalidateFollowParams() | seal_aifollow.cpp | MATCH | | Not current: +0x459 0; m_control NULL or not IsPlayer (slot +0x2c): SetSnakePathUpdate(false, 50); +0x458 0: agree. |
| 229 | 0x2e1c10 | 8 | CZSealBody::HasFollower() | seal_aifollow.cpp | MATCH | | +0x459 byte. |
| 230 | 0x2e1d00 | 92 | CSealCtrlAi::SetFollowOffset(CPnt3D const*) | seal_aifollow.cpp | MATCH | | Offset copied, +0x444 = sqrtf((x x + y y) + z z) of the stored copy: agree. |
| 231 | 0x2e1d60 | 28 | CSealCtrlAi::SetFollowMaster(CZSealBody*) | seal_aifollow.cpp | DEFECT-FIXED | B | The ELF stores neither m_master (+0x418) nor m_followMode 0 when the master is the seal itself (beq 0x2e1d64 over both stores); the port stored the master always (its comment said the ELF did): fixed. Masked: no m8 command names a seal its own master. |
| 232 | 0x2e1e70 | 176 | CAiSFollow::GetStatus() const | seal_aifollow.cpp | DEFECT-FIXED | C | Jump table 0x457c60: 2 -> WAIT, 3 -> FOLLOW, 4 -> HIDE PLAN, 5 -> HIDE WAIT, 6 -> HIDE FOLLOW, 7 -> HIDE; the port's table had the strings' order (2 FOLLOW, 3 WAIT, 4 HIDE ...): fixed. >= 10: UNKNOWN: agree. Debug status text only. |
| 2 | 0x3dece0 | 192 | WordIntersectionTest(int, int, int, int, C2DString*) | hud_teammatenames.cpp | MATCH | | The string in t0 (fifth argument): left / top = m_pos >> 4 (sra), bottom = top + font (+0x1c - +0x18), right = fptosi((float)left + length +0x40); x1 < right, left < x2, y1 < bottom, top < y2: agree. |
| 3 | 0x3deda0 | 124 | CTeamMateNames::UnInit() | hud_teammatenames.cpp | MATCH | | 15 strings (136 bytes from +0x1c): Off (slot +0x18), SetString(NULL) (slot +0x5c); the port's direct calls on the member objects reach the same C2DString methods. |
| 4 | 0x3dee20 | 172 | CTeamMateNames::Init(C2DFont*) | hud_teammatenames.cpp | MATCH | | xMargin (+0x814) 0, then per string SetFont, scale 0x3f4ccccd, appended to the list: agree. |
| 235 | 0x27da60 | 68 | CZSealBody::SetupGear() | seal_cfg.cpp | MATCH | | FindGear("rifle") -> +0x2fc, FindGear("pistol") -> +0x300. |
| 236 | 0x27dbb0 | 164 | CZSealBody::AddItem(char const*) | seal_cfg.cpp | MATCH | | NewBodyPart(NULL, NULL), AttachAuxPart(part, NULL), part +0x24 = BodyId (sh), +0x26 0, new 8-byte entry (part, 0) when allocated, pushed even NULL, true: agree. |
| 237 | 0x27de30 | 160 | CZSealBody::AnimsScaleTS(CActiveAnimList*, CBlendable*, float) | seal_cfg.cpp | MATCH | | Per active anim: ts (+0xc) read, Contains(lh +0x1a), SetTS(scale * ts) (mul.s $f21, $f20): agree. |
| 238 | 0x27ded0 | 148 | CZSealBody::GetMaxXMotion(float&, float&) | seal_cfg.cpp | MATCH | | State (lb +0x11d) 0 / 1 / 2: left = +0xc / +0x1c / +0x2c, right = +0x8 / +0x18 / +0x28; 5: ladder +0x30 both; else 0 both: agree. |
| 239 | 0x27df70 | 148 | CZSealBody::GetMaxZMotion(float&, float&) | seal_cfg.cpp | DEFECT-FIXED | A | The ELF switches on the current state (lb +0x11d, as #238) and writes forward first (a1 <- +0x0 / +0x10 / +0x20) and backward second (a2 <- +0x4 / +0x14 / +0x24) (0x27dfa8..0x27dfe0); the port tested m_desiredState and wrote backward first, so GetSpeedFromThrottle / GetThrottleFromSpeed (axis 0, which read the first) scaled AI forward motion by the backward maximum: fixed. |
| 240 | 0x27e680 | 132 | CZSealBody::RefPointY(AnimType) | seal_cfg.cpp | MATCH | | Anim by type (NULL without a set), first refpoint whose +0xc is it: y (+0x4), else 0.0f: agree. |
| 241 | 0x27e710 | 152 | CZSealBody::RefPoint(CZBodyAnim*, CPnt3D*) | seal_cfg.cpp | MATCH | | CPnt3D::zero, the matching refpoint's point and 1, written to out: agree. |
| 242 | 0x27ea80 | 64 | CZSealBody::GetAnimByType(AnimType) | seal_cfg.cpp | MATCH | | No set: NULL; else GetAnimById(AnimId(type)). |
| 243 | 0x280bb0 | 108 | CZSealBody::BaseAnim_0(AnimType, SEAL_ITEM) | seal_cfg.cpp | MATCH | | The inline GetAnimByType, NULL: NULL, else BaseAnim_0(anim, item). |
| 244 | 0x280c20 | 104 | CZSealBody::BaseAnim(AnimType) | seal_cfg.cpp | MATCH | | As #243 with m_item (lb +0xe58). |
| 245 | 0x280c90 | 48 | CZSealBody::BaseFirePose() | seal_cfg.cpp | MATCH | | m_blends->m_stack[0] (CZBodyAnimBlend) m_animType (lh +0x30) == 1: 1, else 2. |
| 246 | 0x280cc0 | 192 | CZSealBody::FirePosAnim(CZBodyAnim*, SEAL_ITEM) | seal_cfg.cpp | MATCH | | Item 2: PistolFPAnim, item 1: RifleFPAnim of lh +0x1a (m_animgps read without a set test, as the port), then the anim by id or NULL without a set; else the anim: agree. |
| 247 | 0x280d80 | 168 | CZSealBody::GpAnim(CZBodyAnim*, SEAL_ITEM) | seal_cfg.cpp | MATCH | | Item 2: the PistolAnim variant, or the anim when NULL; otherwise the anim: agree. |
| 248 | 0x280e30 | 76 | BodyWepPart(CZSealBody*, SEAL_ITEM) | seal_cfg.cpp | MATCH | | 3: +0x2dc, 2: +0x2d8, 1: +0x2d4, else NULL. |
| 249 | 0x280e80 | 36 | ClearBodyPartNames_Map() | seal_cfg.cpp | MATCH | | Map cleared, BodyPartNamesMap_Inited 0. |
| 250 | 0x281030 | 60 | CZSealBody::InitMotionRdrFile() | seal_cfg.cpp | MATCH | | Read once ("motion.rdr", "data/common", 0), returned. |
| 276 | 0x307920 | 84 | zVid_ZTestOnWriteSet(bool) | zvid_main.cpp | DEVIATION-KEPT | | Both branches copy zon_writeon_dmaref (ELF quirk kept); its words are REF 5 -> zon_writeon (0x43af80), FLUSH, DIRECT 5 (read from the ELF), which the port builds through zvid_kick_ref5, then zSysFifoKick(p, 1): same qword. Kept: the port has no definition of the dmaref object, reason in the code. |
| 277 | 0x307980 | 84 | zVid_ZTestOn() | zvid_main.cpp | MATCH | | 0x30000005, zVid.ztest_on (+0x64), 0x11000000, 0x50000005 into the packet, kicked with 1: the port's helper. |
| 278 | 0x3079e0 | 84 | zVid_ZTestOff() | zvid_main.cpp | MATCH | | The same with ztest_off (+0x68). |
| 10 | 0x185ab0 | 148 | CAiMaps::GetCellRepelParams(CAiMapLoc const&, CPnt3D const*, float, CPnt3D&, float&) | ai_map.cpp | MATCH | | GetMapByIndex(m_mapid & 0x3f) on AiMaps; NULL: 0; else CAiMap::GetCellRepelParams with loc, pos, f12, repel and depth (t0, the fifth argument) passed on, result & 0xff: agree. |
| 11 | 0x185ff0 | 132 | CAiMap::GetMapRegion(CAiMap::region&) const | ai_map.cpp | MATCH | | Location word all zero (mapid, x, y 0), m_dx = low half of m_nx (+0x18), m_dy = of m_ny (+0x1c): agree. |
| 12 | 0x186bf0 | 40 | CAiMap::_reset_rtflag(MAP_FOREACH_STRUCT const&, void*) | ai_map.cpp | MATCH | | The cell (+0x4) byte +3 bit 2 (m_rtflag, bit 26) cleared, returns 1. |
| 13 | 0x187a70 | 52 | CAiMap::GetDirDelta(CAiMap::DIR, CAiMap::DIR) | ai_map.cpp | MATCH | | d = to - from (bytes); d >= 5: -8; else d < -4: +8: agree. |
| 14 | 0x187e90 | 8 | CAiMap::dummy_cell() | ai_map.cpp | MATCH | | &_dummy_cell. |
| 15 | 0x188e90 | 196 | CAiMap::read_scanlines(CFileIO&) | ai_map.cpp | MATCH | | resize(m_ny), virtual fread (slot +0x24) of m_ny * 12 bytes, then per row m_cell + 8 * running count, map-ex 0, count += end - start; returns 1: agree. |
| 222 | 0x2e9ad0 | 192 | CAiTarget::Tick(CEntity*, float) | ai_target.cpp | MATCH | | A living target (bit 3 of +0xdd) with no team bit in common with the owner (+0xc4 &) is kept; else UpdateTarget(NULL, 0.0f), on a change both times = theMission.m_timer, bit 0 of +0x5c set and bit 1 = changed: agree. |
| 223 | 0x2e9b90 | 108 | CAiTarget::GetTimeVisible() const | ai_target.cpp | MATCH | | Target set, alive and visible (bit 2 of +0x24): timer - +0x3c, else 0.0f. |
| 224 | 0x2e9c00 | 20 | CAiTarget::GetTimeAcquired() const | ai_target.cpp | MATCH | | timer - +0x38. |
| 225 | 0x2e9c20 | 20 | CAiTarget::GetTimeSinceLastSighting() const | ai_target.cpp | MATCH | | timer - +0x40. |
| 226 | 0x2e9c40 | 96 | CAiTarget::UpdateLastKnownPosW() | ai_target.cpp | MATCH | | Target's virtual GetPosW (slot +0xc), copied to +0x44 when non-NULL. |
| 1 | 0x3bdb50 | 72 | CLensFlareSaturate::PreDITick(float) | hud_lensflare.cpp | MATCH | | m_On (+0x8c): +0xe4 = 1, RegIntersectDelayed(m_world, +0x9c DI, +0x90 camera, +0x114 light); else +0xe4 = 0: agree. |
| 80 | 0x20e790 | 8 | CGame::StopPlay() | game_engine.cpp | MATCH | | +0x4 = 0. |
| 81 | 0x20e7a0 | 20 | CGame::StartPlay() | game_engine.cpp | MATCH | | +0x4 = 1, tail call Switch(m_InitialState, 0). |
| 279 | 0x309360 | 88 | zdb::CVisual::RemoveDecal(zdb::CDecal*) | vis_main.cpp | MATCH | | List head m_decals[decal m_vid (lhu +0xc)], walk m_next (+0x0); the match unlinked (prev or head) and its next cleared: agree. |
| 280 | 0x30c8f0 | 148 | zdb::CVisual::AddLocalLight(zdb::CLight*, CPnt3D*) | vis_main.cpp | MATCH | | 32 bytes at localLightBuf + cnt: position, +0xc0, diffuse, 1.0f / (+0xc0 - min * min) (0x30c93c..0x30c95c); localLightPtr[cnt] = light, cnt++: agree. |
| 281 | 0x30c990 | 48 | zdb::CVisual::Render(CMatrix*) | vis_main.cpp | MATCH | | Buffers' count (+0x34) != 0: VuUpdate(1.0f). The port's SOCOM_PORT pipe counter is instrumentation only. |
| 282 | 0x30cfb0 | 20 | zdb::CVisual::LandmarkEnable(bool) | vis_main.cpp | MATCH | | m_landmarkFlag = a0, m_lightingEnable = !a0. |
| 283 | 0x30cfd0 | 12 | zdb::CVisual::AlphaEnable(bool) | vis_main.cpp | MATCH | | m_primAlpha = a0 & 0xff, tail call zVid_ZTestOnWriteSet(a0). |
| 284 | 0x30d100 | 48 | zdb::CVisual::Write(zar::CZAR&) | vis_main.cpp | MATCH | | Insert("vparams", the tag_VIS_PARAMS part, 24), 1: agree (the port's cast skips its vptr). |
| 285 | 0x30d270 | 16 | zdb::CVisual::UpdateCentroid() | vis_main.cpp | MATCH | | Three words from +0xc zeroed = the centroid (the port's layout sits 4 bytes later, its vptr). |
| 286 | 0x30d280 | 8 | zdb::CVisual::ComputeBBox(CBBox*) | vis_main.cpp | MATCH | | Empty. |
| 287 | 0x30d290 | 20 | zdb::CVisual::Release() | vis_main.cpp | MATCH | | m_ref_count (+0x18) -1, returned. |
| 288 | 0x30d890 | 124 | zdb::CVisual::ResolveTextureName(_word128*, unsigned int) | vis_main.cpp | MATCH | | GetTexHandle(packet + offset), else "null_xmas.bmp"; handle: texture +0xc, Add(handle, 1), its palette (+0x1c, no texture test, both) Add(palette, 1); texture returned: agree. |
| 289 | 0x30d910 | 160 | zdb::CVisual::ResolveTextureName(_word128*, _word128*) | vis_main.cpp | MATCH | | As #288 with the entry's word 1 as offset; a texture: entry = its +0x40 qword, byte 2 = 5: agree. |
| 290 | 0x30d9b0 | 168 | zdb::CVisual::GetTextureSelectBlock_ver2(unsigned int, _word128**, _word128*, _word128*) | vis_main.cpp | MATCH | | *select += 16, header zeroed and byte 12 bit 1 set, qword after the block 0x15000000 / 0 x3, dmaRef qwc|0x30000000 / new select / 0x11000000 / qwc|0x50000000, dmaRefVu (qwc+2)|0x30000000 / header / 0x01000101 / ((qwc+1) << 16)|0x6c008000, header returned: agree. |
| 291 | 0x30db60 | 64 | zdb::CVisual::Flush() | vis_main.cpp | MATCH | | m_specMapList size 0, swapped with an empty vector, destroyed. |
| 292 | 0x30e250 | 172 | zdb::CVisual::Init() | vis_main.cpp | MATCH | | 32 push_backs and pop_backs on m_stack_vid, resize 16 / 4 / 8 with 0, CMesh::Init: agree. |
| 293 | 0x314010 | 176 | zdb::CTextureFX::Tick(float) | vis_texfx.cpp | MATCH | | Walk of m_texfxpool; byte +0xe == 1: ScrollTexture(dT): agree. |
| 294 | 0x3140c0 | 168 | zdb::CTextureFX::InTexfxpool(zdb::CVisual*) | vis_texfx.cpp | MATCH | | First effect whose +0x8 is the visual: 1, else 0. |
| 295 | 0x314280 | 36 | zdb::CTextureFX::Uninit() | vis_texfx.cpp | MATCH | | Deleting RTPool dtor (a1 1, the dtor's own NULL test) on m_texfxfreepool, then 0: the port's delete. |
| 296 | 0x3142b0 | 56 | zdb::CTextureFX::Init() | vis_texfx.cpp | MATCH | | new 12 bytes, RTPool(20) when allocated, stored. |
| 82 | 0x20bf80 | 68 | CGameStateChangeCmd::DestroyPool() | game_state.cpp | MATCH | | Empty temporary, m_pool cleared, swapped, temporary destroyed: the port's swap leaves the same (the elements go with the temporary). |
| 83 | 0x20c050 | 116 | CGameStateChangeCmd::CreatePool(unsigned int) | game_state.cpp | MATCH | | resize(count), bit 0 of +0x9 set on every 12-byte entry: agree. |
| 84 | 0x20c0d0 | 100 | CGameStateChangeCmd::Release(CGameStateChangeCmd*) | game_state.cpp | MATCH | | NULL: nothing; pooled (bit 0 of +0x9): +0x8 0, +0x0 / +0x4 0, bit 1 of +0x9 cleared; else operator delete: agree. |
| 219 | 0x3f7130 | 184 | CSaveManager::SaveRdr(zar::CKey*, char const*, CRdrFile*) | zsav_manager.cpp | MATCH | | sprintf "%s.rdr"; parent set: CreateKey on m_pZar (+0xc), non-NULL key: rdr Insert, CloseKey, appended to g_KeyToilet; always 0 (ELF quirk kept): agree. |
| 220 | 0x3f7670 | 152 | RemoveExtension(char const*) | zsav_manager.cpp | MATCH | | strncpy(buf, name, strlen - 4), buf[strlen - 4] = 0, assign(buf, strlen(buf)), returned by copy: agree. |
| 221 | 0x3f7c20 | 184 | CSaveManager::~CSaveManager() | zsav_manager.cpp | DEFECT-FIXED | C | Temp buffer (+0x18) deleted when set, the list erased begin..end: agree. The ELF clears +0x18 only after a delete (sw zero 0x3f7c50, inside the test); the port stored it always: moved. No effect (the object is dying). |
| 16 | 0x1938f0 | 40 | CAiPath::SetPathType(CAiPath::PATH_TYPE) | ai_path.cpp | MATCH | | State (+0x78) != 2: +0x9 = type; returns +0x9 == type & 0xff: agree. |
| 17 | 0x1958d0 | 8 | CAiPath::SetTemplatePath(CAiPath*) | ai_path.cpp | MATCH | | +0x10 = path. |
| 18 | 0x195ab0 | 56 | CAiPath::IncrementPathId() | ai_path.cpp | MATCH | | +0x98++, flags & 0x40: PrintPath. |
| 19 | 0x195af0 | 156 | CAiPath::plan_complete(CAiPath::PATH_STATE) | ai_path.cpp | MATCH | | State, legs 0, flags 1 SmoothPath, UpdatePointFlags, 2 UpdateTurnAngles, 4 UpdatePathWidth(5), 0x40 PrintPath, +0x98++: agree. |
| 20 | 0x1961a0 | 108 | CAiPath::plan_setup() | ai_path.cpp | MATCH | | Points, maps (size 0) and waypoints cleared, nine stats words zeroed, visited cleared, state 0, legcount and planleg 0: agree. |
| 21 | 0x196470 | 64 | CAiPath::GetLegMap(int) | ai_path.cpp | MATCH | | -1 -> m_planleg; i <u m_legcount: m_maps[i], else NULL. |
| 22 | 0x1964b0 | 96 | CAiPath::GetLegPoints(CAiMapLoc&, CAiMapLoc&, int) const | ai_path.cpp | MATCH | | -1 -> planleg; in range: waypts[2i], [2i+1] copied; 1 either way (ELF quirk kept). |
| 23 | 0x1968e0 | 44 | CAiPathStats::reset() | ai_path.cpp | MATCH | | Nine words zeroed, tail call m_visited (+0x28) clear. |
| 85 | 0x20f7d0 | 8 | CGRoute::PostProcess() | graph_route.cpp | MATCH | | Empty. |
| 86 | 0x20f7e0 | 56 | CGRoute::Clear() | graph_route.cpp | MATCH | | The node list erased begin..end = clear. |
| 87 | 0x20f820 | 68 | CGRoute::Append(CGNode*) | graph_route.cpp | MATCH | | Inserted before the list's end = push_back. |
| 88 | 0x20f870 | 156 | CGRoute::~CGRoute() | graph_route.cpp | MATCH | | Erase begin..end, then the list dtor: the port's clear and its member's dtor. |
| 89 | 0x20f910 | 40 | CGRoute::CGRoute() | graph_route.cpp | MATCH | | The list ctor only. |
| 233 | 0x26cae0 | 172 | CZSealBody::GetRootPos(float, CPnt3D&) | seal_anim.cpp | MATCH | | Top blend's Representative; f = t * (float)m_nFrames (lh), key = floorf(f), a = fptosi(key); objects_for_body[m_basepart (lh +0x1c)]->GetPosRaw(a, a + 1, f - key, &pos): agree. |
| 234 | 0x26e580 | 96 | CSealAnim::~CSealAnim() | seal_anim.cpp | MATCH | | _free(m_stack, "seal_anim.cpp", 86). |
| 5 | 0x140500 | 8 | COurGame::StopPlay() | main.cpp | MATCH | | Tail jump CGame::StopPlay. |
| 6 | 0x140510 | 8 | COurGame::StartPlay() | main.cpp | MATCH | | Tail jump CGame::StartPlay. |
| 7 | 0x140520 | 40 | COurGame::StopEngine() | main.cpp | MATCH | | CGame::StopEngine, then theLobby.UnInit. |
| 8 | 0x140de0 | 40 | operator delete[](void*) | main.cpp | MATCH | | Non-NULL: _delete_vec(p, "unknown", 0). |
| 9 | 0x140ee0 | 16 | operator new[](unsigned int) | main.cpp | MATCH | | Tail call _new_vec(size, "unknown", 0). |
| 178 | 0x333010 | 64 | CZNetVoice::ServerPermit(unsigned int*) | zNetVoice.cpp | MATCH | | m_do_voice: PTTServer_PermitWANAddress(buf[0], buf[1]) >= 0: PTTServer_Sync(0, 0, 1). |
| 179 | 0x333050 | 64 | CZNetVoice::Permit(unsigned int*) | zNetVoice.cpp | MATCH | | The same through PTT_PermitWANAddress / PTT_Sync. |
| 180 | 0x333090 | 52 | CZNetVoice::Channel(int, unsigned int) | zNetVoice.cpp | MATCH | | No voice: -1; not debugging: channel |= flags; +0x0 = channel, returned. |
| 181 | 0x3330d0 | 180 | CZNetVoice::IAmNewSessionMaster() | zNetVoice.cpp | MATCH | | PTTServer_Start("natservice...", 10070) != -1: Sync(0, 0, 1); QueryWANAddress < 0 stops; Sync(+0x38, 16, 1) != 0 stops; sprintf with a2..t2 = the four address bytes (sra and 0xff) and the port's low half (lhu +0x3c), RemoteSMUpdateCallback(+0x38): agree. |
| 182 | 0x333660 | 104 | CZNetVoice::Tick(float) | zNetVoice.cpp | MATCH | | theNetwork.m_bNetwork and m_isOn (+0xd) else 1; RotateThreadReadyQueue(5), g_status byte cleared when set, +0x4 = PTT_Heartbeat(1000000), 0: agree. |
| 183 | 0x3336d0 | 60 | CZNetVoice::PreTick() | zNetVoice.cpp | MATCH | | Both flags: PTT_HeartbeatPrepare; 0. |
| 184 | 0x333710 | 136 | CZNetVoice::UnInit() | zNetVoice.cpp | MATCH | | Voice on and not m_uninited: m_done_with_thread 1, RotateThreadReadyQueue(5) while it is set, PTTServer_Shutdown, PTT_Destroy, +0x18 0, m_uninited 1: agree; the ELF's v0 is unread. |
| 76 | 0x201800 | 44 | DMEDisconnectFromGameServer() | fts_network_dme.cpp | MATCH | | m_bConnected (+0xa): zNetLeaveAndDisconnect. |
| 77 | 0x201830 | 168 | DMEJoinGameServer() | fts_network_dme.cpp | MATCH | | m_bJoined (+0xb): 1; zNetJoin(joins, leaves) != 0: 0; m_bSessionMaster (+0x8) = master index == my index, m_sessionmaster_index (+0xd8) = master index (called again), 1: agree. |
| 78 | 0x2018e0 | 64 | DMEConnectToGameServer() | fts_network_dme.cpp | MATCH | | +0x8 = 0, zNetConnect(connects, disconnects) == 0 returned. |
| 79 | 0x201fd0 | 44 | DMEinit() | fts_network_dme.cpp | MATCH | | m_network_init (+0xd) clear: zNetInitEx. |
| 101 | 0x222ed0 | 92 | CPnt4D::Rotate_AxisY(float) | zmath_pnt4d.cpp | MATCH | | c = cosf, then s = sinf; x = x c + z s (mula / madd), z = z c - x s (mula / msub) from the old values: agree. |
| 251 | 0x2a4d20 | 16 | CSealEx::OnWeaponHit(zdb::CNode*, zdb::IntersectStruct*, CZProjectile*) | seal_ex.cpp | MATCH | | Tail call m_seal (+0x4) OnWeaponHit(intersection, projectile). |
