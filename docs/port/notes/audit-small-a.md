# Audit of list small-a (2026-11-19, socom-port-audit-small-a)

296 functions (26,404 bytes, each under 200) in 27 files: the HUD (hud_bombmapitem, hud_fader,
hud_newhudmap, hud_scorepopup), st_load, zanim_menu (123 UI commands), bone_archive, char_type,
con_main / con_ps2, ent_target, fts_net_seal, grid_di / grid_main, zmath_trig, zNetCnf, zparticle,
zrdr_file, seal_aievent / aiscan / aistate / ctrl, zsys_sched, ztwod_holding / ztwod_init, vis_bands
and zwep_weaponlist. HEAD 7f6dabc0. Judged file by file in the scan's rank order of each file's
highest-ranked function, from the by-file packets (addresses relied on checked in
`build/port/boot-auditkit/ref.dis` where a dropped line mattered).

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 289 |
| DEFECT-FIXED | 3 (A 1, B 0, C 2) |
| DEVIATION-KEPT | 4 |
| UNJUDGED | 0 |

Defect rate 3 / 296 (A 1, C 2).

Fixes:
- A, #154 CCharacterType::PlayAt (graded B by the worker; raised to A at landing: a hurt or dying AI's 3D line was not cut, which is audible): the 3D call (CSnd vtable slot +0x24 = PlaySound3D(pos, bool,
  float, int, CSndInstance*, uint)) passes the entity id in t1 (move t1, a2 at 0x247a88, unchanged to
  the jalr 0x247ad8); the port passed 0, so every AI 3D line (CSealCtrlAi::PlayAiSound,
  ConfirmAiState, CAiSReload::Tick) was owned by entity 0 (m_entityID, the death-damage Remove).
- C, #160 DeleteTemporaryCharType: m_istemporary is read without a NULL test (0x24a32c); the port's
  test removed.
- C, #192 CGrid::DeleteClutter: the ELF calls CCell::DeleteClutter on the inlined GetCell's result
  unchecked (0x214e90 / 0x214e98); the port's type guard removed, the call goes through GetCell.

Kept deviations (reasons in the code): #262 / #263 GetSpeedFromThrottle / GetThrottleFromSpeed give
the unset local of an unknown axis 0 / 1 (0x284054, 0x284104); #24 CLoadState::CLoadState leaves out
InitThread (0x37f924) under SOCOM_PORT (ps2sdk's _InitSys ran it); #199 CGrid::~CGrid deletes the
clutter manager before Destroy (the ELF order writes into freed clutter).

ELF quirks kept (noted in the code): #30 UISysLoadIRX loads nothing; #83 UILoadConfig's "ON" turning
the messages off; #213 GetIfcDisplayName searching over the device count; #252 CAiSScript::GetStatus
returning the name, not the buffer; #275 ReplaceTextureData's type / qword quirks; #288
CLOD_Object::Read without the sload test; #163 AddWeapon ignoring its item; #190 Read's folded
Fetch result; #143 / #145 atof of an unchecked name; #105 / #107 unchecked strcmp of the name.

SEAL_STANCE lead (from the prompt): DWARF runs NONE -1 .. MAX 4, the port's enum 0 .. 5, but no code
names an enumerator: every use casts raw numbers, which are the ELF's (#255 CAiSAvoid::OnSignal
tests m_stance == 2 and sets 1: DWARF prone -> crouch, as 0x2da708 / 0x2da714). So the functions
agree; only the names mislead. Edit file `zseal_h_seal_stance.txt` gives the enum DWARF's values
(names only); the one comment that used the wrong names (CAiSHostage::Tick, seal_aistate.cpp, not on
this list) is corrected in place.

Return values: #222 CNetCnf::Close returns 1 in the ELF (its one caller UINetCnfClose 0x1d2028 does
not read it); #253 ActivateSeq returns ActivateSequence & 0xff (its one caller CAiSCorpse::Tick
overwrites v0 at 0x2e6dc8): the port's void is equivalent in both.

Float checks: every compare's form as the ELF (#251 c.lt.s, #260 c.le.s, #187 two c.le.s, #188
c.lt / c.eq, #200 c.le / c.lt); operation order of #8, #9, #10, #13, #15, #16, #200, #262 / #263, #195
as the ELF; literal words 0x39ee500f (#18), 0x3f733333 (#260), 0x3f400000 (#247) equal to the port's
spellings.

Leads for other lists:
- zReader (zreader_holding.cpp): the port's shared `_zrdr()` zeroes type, length and array; the
  ELF's inline form (CRdrFile::CRdrFile 0x23cf30) clears only isclone / packed (defined values
  only, no reason comment there).
- zSeal header: SEAL_STANCE names one off (edit file above).
- zUtil: CMemCard members sit 16 bytes higher in the port's layout (theMemCard+0x30 / +0x34 for
  m_card_port / m_card_slot, ELF +0x20 / +0x24); self-consistent, by name.

What the packets lacked: the pointer-to-member constants pushed by the CNetCnf jobs (0x43d328,
0x43d338, 0x43d3e8, 0x43d478, 0x43d4c8 shown as '' strings; sym.py gave StartState / IdleState /
GetComboCount / DeleteAll / AllocMem); CSnd's vtable slot +0x24 (vt.py) for #154; the CHNetCnf
member offsets (zNetCnf.cpp comments) behind #202..#216; the band element sizes (zrender.h) behind
#278 / #283 / #288; the bit positions of m_input_enabled / m_mpbomb_bTimerAvailable (zseal.h) for
#12 / #259; the CAiEvent word layout (zai.h) for #237; the full UiCommandObject body (cut at 5
lines) for #109..#112; the _zrdr / CSTable default ctors for #233; the one ActivateSeq caller's use
of v0 for #253. Lookups outside the packet: about 20 functions.

Runs (tree = HEAD 7f6dabc0 + this list's files):
- Syntax check of the edited files (`ccm.sh`): clean. Default build (`default.sh
  audit-small-a-default`): library 0 errors, link 0 undefined.
- Smoke (AI sounds in m8, mission load / close for DeleteClutter and CleanupTemporary):
  `gate.ps1 -Only roundtrip -Missions 2 -Build audit-small-a-gate` on this tree: PASS, 2 returns to
  the menus, heap in use 18,657,916 B flat, 308 s; no memory card.

## Verdicts

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 8 | 0x403490 | 84 | CFlashFX::Flash(float, float, float) | hud_fader.cpp | MATCH | | +0xa4 / +0xa8 / +0xac times stored, own m_fadedir (+0xa0) and CFader::m_fadedir (+0x80) = OUT (1) as bytes, m_timer / m_fadetime / m_fadetotal = re-read fadeout time, m_brightness = 1.0 word, m_faderate = (1 - m_min_brightness) / m_fadetotal (0x4034cc / d0): all agree. The scan's offsets are the port's vptr-first layout. |
| 9 | 0x403560 | 40 | CFader::SetMinBrightness(float) | hud_fader.cpp | MATCH | | m_min_brightness = arg, m_faderate = (1 - arg) / m_fadetotal (0x403570 / 74): agree. |
| 10 | 0x403590 | 64 | CFader::FadeIn(float) | hud_fader.cpp | MATCH | | m_fadedir = IN (0, sb), m_fadetime = m_fadetotal = time, m_brightness = m_min_brightness, m_faderate = (1 - re-read min) / m_fadetotal: agree. |
| 4 | 0x402f60 | 128 | CFlashFX::~CFlashFX() | hud_fader.cpp | MATCH | | Vtable stores CFlashFX / CFader / C2DBitmap then C2D::~C2D(this, 0) and the deleting-flag delete: the compiler-made base chain of the port's empty body; no member destruction in either. |
| 5 | 0x402fe0 | 156 | CFlashFXVector::Reset() | hud_fader.cpp | MATCH | | Count = size_ read once, each non-NULL element's slot +0x8 deleting dtor (a1 = 1), then an empty vector swapped in and destroyed. The ELF zeroes size_ before the swap (0x403054): the old storage is freed either way, same result. |
| 6 | 0x403080 | 160 | CFlashFXVector::Draw(zdb::CCamera*) | hud_fader.cpp | MATCH | | size_ once, per element non-virtual C2D::IsOn then slot +0xc Draw(camera), data_ re-read: agree. |
| 7 | 0x403120 | 124 | CFlashFXVector::Tick(float) | hud_fader.cpp | MATCH | | size_ once, per element slot +0x24 Tick(dT), no NULL test in either: agree. |
| 176 | 0x1edd30 | 144 | CConsole::Initalize() | con_ps2.cpp | MATCH | | m_socket (+0x24) -1, m_read_len / m_read_status / m_write_status / m_write_len / m_writing / m_unknown48 0, m_read_buf / m_write_buf = _rbuf / _wbuf or 0x20000000, the two 0x10000 memsets, then m_last_event (+0x2c) and m_event (+0x28) 0: all agree (offsets from zsys.h's ELF comments; the scan's are the port's layout). |
| 172 | 0x1edbf0 | 188 | CConsole::Tick() | con_ps2.cpp | MATCH | | CheckEvent, len = m_socket >= 0 ? m_read_len : 0, OnRecvPacket(m_read_buf), m_read_len / m_read_status 0, m_read_buf = _rbuf uncached, RecvPacket and the non-NULL packet's slot +0x8 deleting dtor (port: virtual delete), len returned: agree. |
| 175 | 0x1edcd0 | 84 | CConsole::Disconnect() | con_ps2.cpp | MATCH | | m_socket >= 0 -> sceDeci2Close(m_socket), m_socket = -1; returns 0: agree. |
| 173 | 0x1edcb0 | 8 | CConsole::OnDestroy() | con_ps2.cpp | MATCH | | Empty in both. |
| 174 | 0x1edcc0 | 8 | CConsole::OnDisconnect() | con_ps2.cpp | MATCH | | Empty in both. |
| 177 | 0x1edec0 | 192 | CAckList::FindPacket(CPacket*) | con_ps2.cpp | MATCH | | begin to end walk, CPacket::Compare(node value, packet), first equal value returned, else NULL: agree. |
| 3 | 0x3c7170 | 156 | CZMPBombMapItem::CZMPBombMapItem(zdb::CNode*) | hud_bombmapitem.cpp | MATCH | | CZMapItem then own vtable, m_graphic (+0x10) / m_clippedgraphic (+0x200) constructed, m_node (+0x234) = node, m_wasdetonated (+0x22c) = 0 byte, m_size (+0x230) = 3.0 word, m_graphic.SetColor(255, 0, 0): agree. The scan's offsets are the port's C2D layout. |
| 1 | 0x3c6dc0 | 176 | CZMPBombMapItem::~CZMPBombMapItem() | hud_bombmapitem.cpp | MATCH | | ~C2DTriFan(+0x200), the inlined ~C2DBitmapPoly of m_graphic (C2DPoly array of 2 x 208 at +0x50, ~C2D), CZMapItem vtable, deleting flag: the compiler-made member / base chain of the port's empty body. |
| 2 | 0x3c6e70 | 20 | CZMPBombMapItem::Draw(zdb::CCamera*) | hud_bombmapitem.cpp | MATCH | | m_graphic (+0x10) Draw(camera) as a tail call through its vtable slot +0xc; the port's direct call on the member object is the same method (its dynamic type is fixed). |
| 26 | 0x1d0090 | 160 | CSelectedCharsItr::Advance() | zanim_menu.cpp | MATCH | | ++m_index (+0x4), the < 32 loop, bit m_index of m_mask (+0x0), GetByNameMod(GetCustomCharTypeName(i)), m_list (+0x8) = type + 592 or NULL, stop on non-NULL re-read: agree. |
| 27 | 0x1d0130 | 8 | zAnimUIAppMenuTick(_zanim_cmd_hdr*, float*) | zanim_menu.cpp | MATCH | | Returns 1. |
| 28 | 0x1d0710 | 188 | GetUICommandType(char const*) | zanim_menu.cpp | MATCH | | NULL -> 149 (0x95), "" -> 0 (lb), strcasecmp(table[i].name (+0x4), name) over 12-byte entries, id (+0x0) returned, end at id 0. The ELF compares entry 0 before any id test; entry 0's id is 1 (earlier lead), so the port's test-first loop is the same. |
| 29 | 0x1d07d0 | 12 | GetMenuStack() | zanim_menu.cpp | MATCH | | &g_MenuStack. |
| 30 | 0x1d07e0 | 136 | UISysLoadIRX(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | The inlined UiArgument (GetName(lbu +0x7), "INPUT_STRING" -> GetCharP(0)), strncpy to a 256-byte local, returns 1 (ELF quirk kept, noted). The scan's call is the port's helper. |
| 31 | 0x1d0870 | 88 | UISysPostInit(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | m_streamingSndActive (lbu) -> CSnd::Close, zSysPostInit, CSnd::UIOpen when it was set, returns 1. |
| 32 | 0x1d08d0 | 32 | UIPasswordSecurity(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CZOnlineLobby::PasswordSecurity, returns 1. |
| 33 | 0x1d08f0 | 12 | UIIsTeamGame(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call theLobby.IsTeamGame(). |
| 34 | 0x1d0a30 | 148 | UIAcceptInvitation(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Inlined UiArgument, atoi, AcceptClanInvitation(n), returns 1. |
| 35 | 0x1d0ad0 | 40 | UINotOnCorrectClanTeam(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | !OnCorrectClanTeam() (sltu / xori). |
| 36 | 0x1d0b00 | 36 | UIUpdateClanStats(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UpdateClanStats, returns 1. |
| 37 | 0x1d0b30 | 68 | UICanLadderPressDown(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | current first, then lowest >= current + 10 (slt / xori). |
| 38 | 0x1d0b80 | 40 | UICanLadderPressUp(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | current >= 1 (slti 1 / xori). |
| 39 | 0x1d0bb0 | 60 | UILadderDown(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | GetSurroundingLadderPosition(current + 4, 4, false), returns 1. |
| 40 | 0x1d0bf0 | 80 | UILadderUp(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | current <= 0 skips; current - 4 clamped at 0, (pos, 4, false); returns 1. |
| 41 | 0x1d0c40 | 104 | UISetPlayerDescription(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Add("PlayerDescription", NULL, 1), non-NULL and type (lbu +0x0) 3 -> SetPlayerDescription(string +0x4); returns 1. |
| 42 | 0x1d0cb0 | 36 | UIForceMediusStatusReport(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | ForceStatusReport, returns 1. |
| 43 | 0x1d0dc0 | 40 | AuxNetCensorText(char const*, void*) | zanim_menu.cpp | MATCH | | user != NULL (in the ELF, 0x1d0dc8) -> CUIVariable::operator=(text). |
| 44 | 0x1d0df0 | 40 | UIRebootIOP(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theIOPManager.RebootIOP(2), returns 1. |
| 45 | 0x1d0e20 | 32 | UIStopAllSounds(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CSndInstance::UIStopAllSounds, returns 1. |
| 46 | 0x1d0e40 | 12 | UIHasClanInvitations(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call HasClanInvitations. |
| 47 | 0x1d0e50 | 108 | UINetCnfDeleteAll(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Byte static ticking (guarded init 0): clear -> ticking = DeleteAll(HCnf), return 0; set -> DeleteAllTick(HCnf) & 0xff, true clears ticking, result returned. |
| 48 | 0x1d1840 | 120 | UINetGetDevIndex(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Create(GetName(lbu +0x7), TEMP 2) without a NULL test, GetDevIndex(HCnf), the inlined UiSetValve (lhu m_value vs the full int, change 1 / 2, sh, MakeCallbacks): agree. |
| 49 | 0x1d18c0 | 108 | UINetSaveDev(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #47 with SaveDev / SaveDevTick. |
| 50 | 0x1d1930 | 108 | UINetAddCombo(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #47 with AddCombo / AddComboTick. |
| 51 | 0x1d19a0 | 108 | UINetAddIfc(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #47 with AddIFC / AddIFCTick. |
| 52 | 0x1d1ed0 | 76 | UINetCnfSelectCombo(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Create(name, 2), NULL test (in the ELF), SelectCombo(HCnf, lhu m_value - 1), returns 1. |
| 53 | 0x1d1f20 | 128 | UINetCnfCurrCombo(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Create(name, 2), NULL test, UiSetValve(GetDefaultCombo + 1) inlined, returns 1. |
| 54 | 0x1d1fa0 | 128 | UINetCnfCount(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Create(name, 2), NULL test, UiSetValve(NumCombos), returns 1. |
| 55 | 0x1d2020 | 36 | UINetCnfClose(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Close(HCnf), HCnf = 0, returns 1. |
| 56 | 0x1d2050 | 80 | UINetCnfOpen(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | HCnf NULL -> HCnf = Open(GetName(+0x7)), return 0; else OpenTick(HCnf) & 0xff. |
| 57 | 0x1d20a0 | 32 | UINetCnfUninit(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CNetCnf::Uninit() & 0xff returned. |
| 58 | 0x1d20c0 | 32 | UINetCnfInit(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CNetCnf::Init(false) & 0xff returned. |
| 59 | 0x1d20e0 | 56 | UIAbortLoad(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theGame+0xe0 (m_loadState).AbortLoad(GetName(+0x7)), returns 0. |
| 60 | 0x1d2280 | 36 | UIGetLadderInfo(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | GetLadderInfo, returns 1. |
| 61 | 0x1d22e0 | 36 | UIBanSelfFromGame(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | BanSelfFromGame, returns 1. |
| 62 | 0x1d2310 | 140 | UISetDefaultMenuScreen(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Inlined UiArgument, strncpy(theGame+0x9c m_DefaultMenu, name, 64), returns 1. |
| 63 | 0x1d23a0 | 40 | UIGameStatePopCommand(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theGame.Pop(0), returns 1. |
| 64 | 0x1d23d0 | 8 | UIHaveBeenBannedFromGame(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CZPersonaState::m_VotedOff (lbu). |
| 65 | 0x1d23e0 | 132 | UISetMPMissionSeq(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Create MapValve / MapValve2 / MapValve3 (PERM 1, no NULL test), low byte of m_value (lbu +0x4) into bytes 0..2, byte 3 = 0, SetMissionSequence(0, seq), ResetMissionSequence, returns 1. |
| 66 | 0x1d2560 | 8 | UIIsClanChallengeGame(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Returns 0. |
| 67 | 0x1d2570 | 168 | UIChangeCharacterType(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument, atoi - 1, GetCustomCharTypeName, strncpy(theNetwork+0x1188, name, 31), byte +0x11a6 (= [30]) = 0, returns 1. |
| 68 | 0x1d2710 | 132 | UIRevokeInvite(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument, RevokeInvite's result returned. |
| 69 | 0x1d27a0 | 36 | UIGetClanRoster(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | GetClanRoster, returns 1. |
| 70 | 0x1d27d0 | 36 | UICheckClanInvites(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CheckClanInvitations, returns 1. |
| 71 | 0x1d2800 | 36 | UIGetInvitedPlayers(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | GetInvitedPlayers, returns 1. |
| 72 | 0x1d2830 | 180 | UIVagStreaming(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument's two tests inline, strcmp(name, "ON") without a NULL test -> m_vagEnabled = 1 (before UIOpen, delay slot 0x1d28ac) and UIOpen; else "OFF" -> 0; returns 1. The scan's 'ON' is a merged suffix string. |
| 73 | 0x1d28f0 | 132 | UIInvitePlayerToClanWithArg(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument, InvitePlayerToClan's result returned. |
| 74 | 0x1d2a70 | 68 | UIRemovePlayerFromClan(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | m_arg_list (+0x18) NULL -> NULL else GetCharP(0), RemovePlayerFromClan, returns 1. |
| 75 | 0x1d2ac0 | 132 | UIIsLeaderOfClan(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument, IsLeaderOfClan's result returned. |
| 76 | 0x1d2b50 | 12 | UIIsMemberOfClan(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call IsMemberOfClan. |
| 77 | 0x1d2b60 | 36 | UIDisbandClan(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | DisbandClan, returns 1. |
| 78 | 0x1d2b90 | 168 | UICreateClan(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | m_CurAnim read first, Add("CLANNAMEVAR", NULL, 1), non-NULL string -> CreateClan(string), else CreateClan(GetName(+0x7)); returns 1. |
| 79 | 0x1d2c50 | 132 | UIPlayMPEG(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Byte static alt (guarded init 0): was = alt, alt = !was; was 0 -> SetMovie(GetName) on theGame+0x1f0, Push(&that, 0); was returned. |
| 80 | 0x1d2ce0 | 12 | UIMediusEnabled(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theNetwork+0xe4 m_bMediusEnabled (lbu). |
| 81 | 0x1d2cf0 | 8 | UICoopMissionExists(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Returns 0. |
| 82 | 0x1d2d00 | 56 | UISaveConfig(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theMemCard.SaveConfig(GetName(+0x7)), returns 1. |
| 83 | 0x1d2d40 | 164 | UILoadConfig(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | LoadConfig(GetName), Add("AUTOMESSAGES", NULL, 1) without a NULL test, type 3 -> strcasecmp(string, "ON"): 0 -> SetPlayAutoMessages(false), else true (ELF quirk kept, noted); returns 1. |
| 84 | 0x1d2df0 | 36 | UIMC_CreateIconFiles(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CreateIconFiles, returns 1. |
| 85 | 0x1d2e20 | 52 | UIMC_Exists(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Exists(GetName(+0x7))'s result returned. |
| 86 | 0x1d2e60 | 60 | UIMC_ChSlot(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | atoi(GetName), >= 0 -> theMemCard+0x24 m_card_slot; returns 1. The scan's +0x34 is the port's CMemCard layout (member by name). |
| 87 | 0x1d2ea0 | 60 | UIMC_ChPort(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | atoi(GetName), >= 0 -> theMemCard+0x20 m_card_port; returns 1. Scan: port layout as #86. |
| 88 | 0x1d2ee0 | 52 | UIMC_MkDir(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | mkdir(GetName(+0x7))'s result returned. |
| 89 | 0x1d2f20 | 52 | UIMC_ChDir(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | chdir(GetName(+0x7))'s result returned. |
| 90 | 0x1d2f60 | 32 | UIMC_Uninit(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CMemCard::Uninit, returns 1. |
| 91 | 0x1d2f80 | 32 | UIMC_Init(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theMemCard.Init (a0 left as the caller's: the ELF does not load theMemCard, 0x1d2f88; Init's body only uses statics there), returns 1. |
| 92 | 0x1d2fa0 | 40 | UIIsSpaceForSaveGameFile(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | GetFreeSpace() > 300 (slti 301 / xori). |
| 93 | 0x1d3f40 | 128 | UIToggleAutoMessages(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Add("AUTOMESSAGES", NULL, 1) first, GetPlayAutoMessages: on -> var = "OFF", Set(false); off -> "ON", Set(true); returns 1. |
| 94 | 0x1d3fc0 | 8 | UIClearGameState(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Returns 1. |
| 95 | 0x1d3fd0 | 180 | UIFlushMenuHistory(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | 20 x strcpy(m_cmds[i].arg (+4 + 52 i), DEFAULT_ARGNAME); while m_list (+0x418) not empty: m_free (+0xa24).push_back(m_list.back()), strcpy(m_free.back(), MENUHISTORY_STRPOOL), m_list.pop_back(); returns 1. The scan's stores / 'POOL' are GCC's inlined strcpy of the port's literal. |
| 96 | 0x1d4230 | 188 | UISetMenuState(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | MyMajor(MENUS 1), MyMinor(NOTREADY 1) on theMission+0x584; m_bSessionMaster (theNetwork+0x8) -> MPMajor(1), UpdateLocalGame, i < 16 with bit 4 of m_LJArray[i] (dsll32 0x1b / dsrl32 0x1f) -> SendGameSignalMessage(i, 13, 0, 0, 0, true); UpdateLocalPersona; returns 1. |
| 97 | 0x1d42f0 | 128 | UIReadyToLoad(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | g_can_use_ready <u local time; m_late_joiner (+0x94 lbu) -> MyMajor(LOADING 2), MyMinor(1), else ToggleReady; g_can_use_ready = time + 5000; returns 1. |
| 98 | 0x1d4370 | 128 | UISendChatText(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Find(GetName), NULL test, type 3, strlen(string) != 0 -> SendChatMsg(string); returns 1. |
| 99 | 0x1d4620 | 128 | UIForceMPLaunch(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | m_ten_second_launch (+0x9f lbu) clear -> TenSecondLaunch(1), UpdateLocalGame; else zNetGetTime <u +0xa8 - 5000 -> TenSecondLaunch(0), UpdateLocalGame; returns 1. |
| 100 | 0x1d46a0 | 84 | UISwitchSides(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | g_can_use_switch <u local time -> NetSendRequestTeamSwitch(+0x70), g_can_use_switch = time + 5000; returns 1. |
| 101 | 0x1d4700 | 28 | UIIsTerrorist(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | (m_net_team (+0x90 lw) & 1) == 0. |
| 102 | 0x1d4720 | 96 | UIKillPopUp(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | g_MenuStack+0xa30 m_popup non-NULL -> g_menuRootNode->FindChild("POPUP", true) (slot +0x24), non-NULL -> SetActive(false) (slot +0x34); returns 1. |
| 103 | 0x1d4780 | 36 | UIGetMediusAnnouncements(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | GetAnnouncements, returns 1. |
| 104 | 0x1d47b0 | 124 | UISendMediusChat(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Find(GetName), non-NULL type 3 -> string else NULL, SendChat; returns 1. |
| 105 | 0x1d4830 | 148 | UIJoinMPRoom(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | strcmp(name, "INPUT_STRING") unchecked -> GetCharP(0); else "RANDOM" -> NULL; JoinRoom's result returned. |
| 106 | 0x1d4b90 | 132 | UIGameHasPassword(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument, GameIsPasswordProtected's result returned. |
| 107 | 0x1d4c20 | 120 | UIJoinMPGame(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Unchecked strcmp INPUT_STRING -> GetCharP(0), JoinGame & 0xff returned. |
| 108 | 0x1d4ca0 | 12 | UICreateMPGame(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call CreateGame. |
| 109 | 0x1d4cb0 | 156 | UIRefreshGamePlayerList(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiCommandObject: node_ref_index (lhu +0x4) 0 -> NULL, Refresh(false), GetNode(i, false), GetFirstVisual, Get2DVisual (slot +0x20), its +0x68 m_2d, each NULL -> NULL; RefreshGamePlayerList's result returned. |
| 110 | 0x1d4d50 | 156 | UIRefreshRoomPlayerList(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #109, RefreshRoomPlayerList. |
| 111 | 0x1d4df0 | 156 | UIRefreshRoomList(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #109, RefreshRoomList. |
| 112 | 0x1d4e90 | 156 | UIRefreshGameList(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #109, RefreshGameList. |
| 113 | 0x1d4f30 | 8 | UIGetAcctInfo(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Returns 0. |
| 114 | 0x1d4f40 | 36 | UILobbyBailout(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Bailout, returns 1. |
| 115 | 0x1d4f70 | 80 | UILobbyLogout(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theLobby+0x60 byte: 0 -> 1; 18 -> 0; else Logout, 0. |
| 116 | 0x1d4fc0 | 196 | UILobbyLogin(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Both Add(…, NULL, 1) calls, then each type 3 -> string else NULL (no NULL test of the variables), NULL / empty (lb) of either -> 0, else Login(name, password)'s result. |
| 117 | 0x1d5090 | 196 | UILobbyRegister(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #116 with Register. |
| 118 | 0x1d5230 | 172 | UIDoesSlotHaveGame(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument, atoi, sprintf(static filename, "SaveGame%d"), Exists(filename)'s result returned. |
| 119 | 0x1d52e0 | 12 | UIFormatMemCard(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call theMemCard.Format() (the port's refusal lives in port/compat/libmc.c, not here). |
| 120 | 0x1d52f0 | 12 | UIIsMemCardFormatted(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call IsFormatted. |
| 121 | 0x1d5300 | 12 | UIIsMemCardInserted(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call IsInserted. |
| 122 | 0x1d5310 | 136 | UICheckJoinMP(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Static b (-1 on first use; the port's load-time -1 is the same), GetDMEJoinedCount stored when it differs, 0 -> m_pJoinGameValve (+0x24): change = lhu m_value != 10 (1 else 0), sh 10, MakeCallbacks(1) when changed; returns 1. |
| 123 | 0x1d53a0 | 116 | UIJoinGameServer(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | m_late_joiner (+0x94) clear -> DMEJoinGameServer (0 -> return 0), ftsNetworkGameInit; m_bNetwork (+0x9) and m_bSessionMaster (+0x8) -> UpdateLocalGame; returns 1. |
| 124 | 0x1d5420 | 108 | UIDisconnectFromGameServer(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Session master and valid client count 1 -> SendEndGameReport; ftsNetworkGameUninit, DMEDisconnectFromGameServer, RejoinRoom, DestroyNetGame; returns 1. |
| 125 | 0x1d5490 | 80 | UIConnectToGameServer(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | CreateNetGame, DMEConnectToGameServer nonzero -> 1; else RejoinRoom, DestroyNetGame, 0. |
| 126 | 0x1d54e0 | 68 | UIUnInitNetwork(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | m_bMediusEnabled (+0xe4) -> theLobby+0x58 m_event_handler = 0 (delay slot, before Close), Close; m_bNetwork (+0x9) = 0; returns 1. |
| 127 | 0x1d5530 | 128 | UIInitNetwork(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Medius: Open() & 0xff, then m_event_handler (+0x58) = UILobbyEventHandler, Open's result; else m_bNetwork = 1 (before CreateNetGame, delay slot), CreateNetGame, DMEinit, DMEConnectToGameServer, DMEJoinGameServer, ftsNetworkGameInit, 1. The scan's +0x58 is the same member. |
| 128 | 0x1d55b0 | 24 | UILobbyEventHandler(char const*, char const*) | zanim_menu.cpp | MATCH | | Tail call theGame+0x7c m_menuState.RunEventAnim(anim, arg). |
| 129 | 0x1d55d0 | 12 | UIIsNetwork(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theNetwork+0x9 (lbu). |
| 130 | 0x1d55e0 | 52 | UIIsSessionMaster(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | +0x9 clear -> 0; +0x8 nonzero -> 1 else 0. |
| 131 | 0x1d5a20 | 56 | UIPopUpDialog(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | g_MenuStack.PopUpDialog(GetName(+0x7)), returns 1. |
| 132 | 0x1d5a60 | 168 | UISetMission(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument's tests inline, HaltBackgroundMPEG, strcpy(database, name) unchecked, theMission.PreOpen(name), RestartBackgroundMPEG; returns 1. |
| 133 | 0x1d5c80 | 88 | CMenuStack::KillPopUp() | zanim_menu.cpp | MATCH | | m_popup (+0xa30) NULL -> return; FindChild("POPUP", true) (slot +0x24), non-NULL -> SetActive(false) (slot +0x34). |
| 134 | 0x1d5df0 | 72 | CMenuStack::CleanPopup() | zanim_menu.cpp | MATCH | | m_popup non-NULL -> its deleting dtor (slot +0x8 of the vtable at +0xc, a1 = 1), m_popup = 0. |
| 135 | 0x1d5e40 | 12 | FetchMissionFontsRdr() | zanim_menu.cpp | MATCH | | theMission+0x5a0 m_fontsRdr. |
| 136 | 0x1d6440 | 128 | CMenuStack::AddToHistory(char const*) | zanim_menu.cpp | MATCH | | buffer = m_free (+0xa24) data[size - 1], size - 1 (pop_back), m_list (+0x418).insert(end, 1, buffer) (push_back), strcpy(buffer, name). |
| 137 | 0x1d6740 | 8 | GetMenuNode() | zanim_menu.cpp | MATCH | | g_menuRootNode. |
| 138 | 0x1d6750 | 8 | UnRegisterMenuNode() | zanim_menu.cpp | MATCH | | g_menuRootNode = 0. |
| 139 | 0x1d6760 | 8 | RegisterMenuNode(zdb::CNode*) | zanim_menu.cpp | MATCH | | g_menuRootNode = node. |
| 140 | 0x1d6770 | 12 | GetDatabase() | zanim_menu.cpp | MATCH | | &database. |
| 141 | 0x1d6780 | 16 | SetDatabase(char const*) | zanim_menu.cpp | MATCH | | Tail call strcpy(database, db), its result returned. |
| 142 | 0x1d69c0 | 132 | UISetControllerConfig(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument inline, CCtrlrConfigs::SelectConfig(name), returns 1. |
| 143 | 0x1d6a50 | 148 | OnSetTtySpeedFactor(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | UiArgument inline, atof (name unchecked), dptofp, UiSetTtySpeedFactor; returns 1. |
| 144 | 0x1d6af0 | 8 | OnSetSkbPurpose(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call UiSetSkbPurpose(cmd, dT). |
| 145 | 0x1d6b00 | 148 | OnSetCounterSpeedFactor(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | As #143, UiSetCounterSpeedFactor. |
| 146 | 0x1d6ba0 | 108 | OnReplayMission(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | m_bNetwork clear -> theGame.Pop(1); session master -> MPMajor(NEWROUND 5), UpdateLocalGame; returns 1. |
| 147 | 0x1d6f00 | 20 | OnIsMissionSuccessful(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | theMission+0x18 m_state (lbu) == 2. |
| 148 | 0x1d7090 | 8 | OnGetTextFromUser(C2DAnimCmdHdr*, float*) | zanim_menu.cpp | MATCH | | Tail call UiGetTextFromUser(cmd, dT). |
| 11 | 0x3c34c0 | 180 | CZNewHudMap::FindMPBombItem() | hud_newhudmap.cpp | MATCH | | m_itemlist (+0x1c) begin..end, __dynamic_cast(item, CZMapItem -> CZMPBombMapItem), first non-NULL returned, else NULL. The scan's strings are the two compilers' RTTI names. |
| 12 | 0x3c48b0 | 160 | CZNewHudMap::TickCompassMap(CPad*, MENU_STATE) | hud_newhudmap.cpp | MATCH | | GetHUDOwner, m_control (+0xc0) or NULL, m_state[1] (+0x14 lbu) == KEY_FALLING 1, !m_bNetwork (+0x9), m_input_enabled (bit 3 of +0x169 = bit 11 of the +0x168 word, as zseal.h), menustate & 0xff == 0 -> SwitchMapToFullScreen. |
| 13 | 0x3c56c0 | 24 | CZNewHudMap::CalcDrawPos(float) const | hud_newhudmap.cpp | MATCH | | m_screencentery + m_scale * (y - m_screencentery), same order. |
| 14 | 0x3c56e0 | 24 | CZNewHudMap::SetWorldWidth(float) | hud_newhudmap.cpp | MATCH | | m_width (+0x74) = width; the ELF stores m_worldcenterx / y back unchanged (no effect). |
| 15 | 0x3c5700 | 124 | CZNewHudMap::SetMapScreenPos(float, float, float, float) | hud_newhudmap.cpp | MATCH | | The four corners, centres x1 + (x2 - x1) / 2 and y1 + (y2 - y1) / 2 (div.s by 2.0, the scan's mul is GCC's exact 0.5), !m_isFullScreen (+0x4c4) -> m_circleclipper (+0x4b8) Cx = m_topx + cx, Cy = m_topy + cy, Radius = cy - y1. |
| 16 | 0x3c5be0 | 160 | CZNewHudMap::MapWorldPointToUV(CPnt3D const*, CBBox const*, zdb::CTexture*) | hud_newhudmap.cpp | MATCH | | tex width / height (lhu +0x0 / +0x2) to float, (p.x - min.x) * (w / (max.x - min.x)), (p.z - min.z) * (h / (max.z - min.z)), each / w, / h, z = 0, returned through a0: same operations and order. |
| 17 | 0x3c6440 | 40 | CZNewHudMap::ReInit() | hud_newhudmap.cpp | MATCH | | m_isFullScreen (lbu) -> SwitchToCompassMap. |
| 18 | 0x3c6470 | 24 | CZNewHudMap::GetZoomOut() const | hud_newhudmap.cpp | MATCH | | 0x39ee500f * m_width (+0x74); the port spells the same word. |
| 19 | 0x3c6cf0 | 112 | COverlayLine::~COverlayLine() | hud_newhudmap.cpp | MATCH | | Own then C2DLine vtable, ~C2D(this, 0), deleting flag: the compiler-made chain of the empty body (C2DLine's dtor inlined in the ELF). |
| 20 | 0x3c6d60 | 84 | COverlayLine::COverlayLine() | hud_newhudmap.cpp | MATCH | | C2DLine ctor, own vtable, SetColor(64, 192, 255). |
| 21 | 0x421d40 | 168 | hudTurnOffScorePopup() | hud_scorepopup.cpp | MATCH | | g_bOn = 0, then 27 strings of g_oSeals2Ds then 27 of g_oTerrs2Ds (_arrStrs at +0x100, 136 bytes each) ClearAndWipe through vtable slot +0x78 (the port's direct call on the typed element is the same method). |
| 22 | 0x4220d0 | 100 | hudGetScorePopupPtr() | hud_scorepopup.cpp | MATCH | | Guarded local static CScorePopup (C2D ctor, own vtable, exit dtor registered), its address returned. The scan's __register_exitproc is GCC's form of the same static. |
| 238 | 0x2e4310 | 120 | CSealCtrl::ClearLook(AI_LOOK) | seal_aiscan.cpp | MATCH | | Signed byte look: -1 or == m_look_mode (lb +0x20) passes; m_look_data = CPnt3D::unit_nz, m_look_type = LOOK_DIRR 3, m_look_mode = 0, m_look_timer = CAiTimer::infinite, m_look_flags = 0, SetDefaultLookParams(0). The scan's offsets are the port's vptr-first layout. |
| 239 | 0x2e4480 | 140 | CSealCtrl::SetLookDirW(AI_LOOK, CAiMap::DIR) | seal_aiscan.cpp | MATCH | | GetDirVec(dir, vec) first, then signed look < m_look_mode -> false; m_look_data = vec, m_look_type = LOOK_DIRW 2, SetDefaultLookParams(look), true. |
| 240 | 0x2e4600 | 96 | CSealCtrl::SetLookPosW(AI_LOOK, CPnt3D const*) | seal_aiscan.cpp | MATCH | | Signed look < m_look_mode -> false; m_look_data = *pos, LOOK_POSW 1, SetDefaultLookParams(look), true. |
| 241 | 0x2e49d0 | 16 | CSealCtrl::SetScanRate(float) | seal_aiscan.cpp | MATCH | | m_scan_timer.m_timer (+0x5c) and m_period.m_min (+0x54) = period, m_range (+0x58) = 0. |
| 242 | 0x2e49e0 | 20 | CSealCtrl::SetScanAngle(float) | seal_aiscan.cpp | MATCH | | m_min = -angle, m_range = angle + angle. |
| 243 | 0x2e4a00 | 32 | CSealCtrl::ModifyLookFlags(unsigned int, unsigned int) | seal_aiscan.cpp | MATCH | | m_look_flags (+0x48) &= ~clear, stored, re-read, |= set. |
| 244 | 0x2e4a20 | 8 | CSealCtrl::SetLookFlags(unsigned int) | seal_aiscan.cpp | MATCH | | m_look_flags = flags. |
| 245 | 0x2e4a30 | 8 | CSealCtrl::SetLookTimer(float) | seal_aiscan.cpp | MATCH | | m_look_timer (+0x14) = time. |
| 246 | 0x2e4a40 | 12 | CSealCtrl::SetLookRate(float) | seal_aiscan.cpp | MATCH | | m_look_rate.m_min = rate, m_range = 0 word. |
| 237 | 0x2deff0 | 76 | CSealCtrlAi::SetAiEvent(CAiEvent::EVENT, float, CPnt3D const*) | seal_aievent.cpp | MATCH | | m_event.m_type = sign-extended byte event & 0x7fff into bits 1-15 of half +0x49a, m_visible (bit 0) kept (the port's u32 word +0x498: m_id 0-15, m_visible 16, m_type 17-31: the same bits); m_duration (+0x490), m_pos (+0x480..0x488) = *pos. The scan's +0x498 / +0x49a is the word vs half access. |
| 255 | 0x2da6c0 | 144 | CAiSAvoid::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_aistate.cpp | MATCH | | Byte signal: 0 -> m_stance (lb +0x285) == 2 -> SetStance(1); 3 -> the same, then m_substate (+0x14) = 0; 1 / 2 / 4 / others nothing. SEAL_STANCE lead: 2 / 1 are DWARF PRONE / CROUCH (prone gets up to a crouch); the port casts the same raw numbers, so it agrees; only the port enum's names are one off (edit file zseal_h_seal_stance.txt). |
| 247 | 0x2d7bc0 | 120 | CAiSCQBAttack::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_aistate.cpp | MATCH | | Byte signal: 4 -> m_victim (+0x28) = 0, m_delay (+0x2c) = 0; 0 -> m_delay = m_navyseal (bit 1 of +0x280) ? 0 : 0.75 (0x3f400000); 1 / 2 / 3 nothing. |
| 248 | 0x2d7c40 | 8 | CAiSUnknown::Tick(float, CSealCtrlAi*) | seal_aistate.cpp | MATCH | | Returns 1. |
| 249 | 0x2d7c50 | 8 | CAiSUnknown::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_aistate.cpp | MATCH | | Empty. |
| 250 | 0x2d8b60 | 188 | CAiSBreach::GetStatus() const | seal_aistate.cpp | MATCH | | m_substate (+0x14 lbu) < 12 through the jump table 0x457430: 0-5 and 7-11 the eleven names, 6 and >= 12 "UNKNOWN". |
| 251 | 0x2d9130 | 108 | CAiSScript::CanPursue(CSealCtrlAi*) const | seal_aistate.cpp | MATCH | | m_aware (+0x2e lbu) == GetAiAware() & 0xff, then !(m_timer (+0x30) < 5.0) (c.lt.s, the same form). |
| 252 | 0x2d94e0 | 132 | CAiSScript::GetStatus() const | seal_aistate.cpp | MATCH | | m_anim (+0x28) ? GetName() : "", strcpy into the static buffer, m_critical (bit 0 of +0x2c) -> strcat " CRIT", the name returned (ELF quirk kept, noted). |
| 253 | 0x2d96c0 | 192 | CSealCtrlAi::ActivateSeq(char const*, unsigned int) | seal_aistate.cpp | MATCH | | AiStateIs(1) else 0; top = size (+0x324) ? front : NULL, NULL -> _unknown; m_state (+0x10) == 1 -> ActivateSequence(name, flags). The ELF calls it with NULL when the top is not the script state, unreachable after AiStateIs on the same top. Its & 0xff result: the one caller (CAiSCorpse::Tick 0x2e6dc0) overwrites v0, so the port's void is equivalent. |
| 254 | 0x2da450 | 72 | CAiSHostage::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_aistate.cpp | MATCH | | Byte signal 4 -> m_commander (+0x28) = 0; others nothing. |
| 256 | 0x2da910 | 100 | CAiSPickup::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_aistate.cpp | MATCH | | Byte signal 4 -> m_pickup (+0x28) = 0, bit 0 of +0x30 m_take = 0 (others kept), m_pickup_id (+0x2c) = 0. |
| 257 | 0x2dbd20 | 76 | CSealCtrlAi::GetAiState() const | seal_aistate.cpp | MATCH | | m_stateStack size (+0x324) 0 -> NULL, else the first node's value; NULL -> &_unknown. |
| 258 | 0x2dbd70 | 76 | CSealCtrlAi::GetAiState() | seal_aistate.cpp | MATCH | | As #257. |
| 264 | 0x284260 | 96 | CSealCtrl::StopRumbler() | seal_ctrl.cpp | MATCH | | m_padid (u32, sltiu 2) -> CInput::m_pads[id] else NULL, non-NULL -> bytes +0xd then +0xc = 0; m_highrumbletime / m_rumbletime / m_rumblestr = 0; CInput::Flush, StopAllHeartbeatSounds. The scan's offsets are the port's layout. |
| 260 | 0x283e00 | 92 | CSealCtrl::SetViewRange(float) | seal_ctrl.cpp | MATCH | | !(range <= 0) (c.le.s / bc1t, the same form) -> m_visrange value / goal = range; else CWorld::m_world->m_camera (+0xc0) non-NULL -> 0x3f733333 * m_mid_plane (+0xec) into both. |
| 259 | 0x283730 | 32 | CSealCtrl::MPBomb_TimerAvailable(bool) | seal_ctrl.cpp | MATCH | | Bit 4 of +0x169 (= bit 12 of the +0x168 flag word, m_mpbomb_bTimerAvailable in zseal.h) = arg & 1, others kept. |
| 261 | 0x283e60 | 184 | CSealCtrl::UpdateAiVisMap() | seal_ctrl.cpp | MATCH | | m_vismap (+0xe0) NULL -> 0; else a CAiMapLoc built from m_entity's m_mapLocValid (mapid bits 0-5, x 6-18, y 19-31: the whole word, as the port's struct copy) and UpdateDynamicVisMap(m_vismap, &loc)'s result returned. |
| 262 | 0x284020 | 164 | CSealCtrl::GetSpeedFromThrottle(float, int) | seal_ctrl.cpp | DEVIATION-KEPT | | axis 1 GetMaxXMotion, 0 GetMaxZMotion, each max * m_movespeedmod (+0xecc), 2 theCharacterDynamics+0x40 m_turn_maxRate; throttle * max: agree. Kept (reason in the code): another axis multiplies the ELF's unset stack local (0x284054); the port starts it at 0. |
| 263 | 0x2840d0 | 168 | CSealCtrl::GetThrottleFromSpeed(float, int) | seal_ctrl.cpp | DEVIATION-KEPT | | As #262 with speed / max (div.s 0x284168). Kept (reason in the code): another axis divides by the unset local (0x284104); the port starts it at 1. |
| 273 | 0x303c60 | 48 | C2D::Init() | ztwod_init.cpp | MATCH | | m_topx / m_botx / m_topy / m_boty = 1728 / 2368 / 1824 / 2272 (words 0x44d8 / 0x4514 / 0x44e4 / 0x450e << 16), m_fXPixel = m_fYPixel = 1.0. The scan's float loads are GCC's literal pool. |
| 272 | 0x303c10 | 68 | C2D::Open() | ztwod_init.cpp | MATCH | | m_p2dcamera NULL -> new CCamera (1312 bytes in the ELF; the port's own size) constructed when the allocation succeeded, stored. |
| 216 | 0x3ff390 | 96 | CNetCnf::SelectCombo(void*, int) | zNetCnf.cpp | MATCH | | data = h + 3520 + combo * 4928 (m_open.m_combos[combo]), sceNetcnfifDataDump(data), m_setInit (+0xbd40) .m_data (+0x40 = 0xbd80) = *data (operator=), m_selected_combo = combo. Offsets against zNetCnf.cpp's CHNetCnf comments; the scan's constants are the port's own layout. |
| 202 | 0x3fd5b0 | 128 | CNetCnf::DeleteAll(void*) | zNetCnf.cpp | MATCH | | m_deleteAll (+0xd0c0): states (+0x10) push StartState (pmf 0x43d338, sym.py), m_done (+0x2c) = 0, push CSMDeleteAll::DeleteAll (0x43d478); returns 1: the inlined Begin. |
| 204 | 0x3fdac0 | 140 | CNetCnf::AddCombo(void*) | zNetCnf.cpp | MATCH | | m_addCombo (+0xa980): push StartState, m_done = 0, sceNetcnfifDataInit(+0xa9c0 m_data), push IdleState (0x43d328); returns 1. |
| 205 | 0x3fe100 | 180 | CNetCnf::SaveDev(void*) | zNetCnf.cpp | MATCH | | device = m_device (+0xd0f4) read first, m_saveDev (+0x9580): push StartState, m_done = 0, m_entry (+0x38) = device, m_data (+0x3c) = &m_addDev.m_data (+0x8200), push CSMSaveDev::AllocMem (0x43d4c8); returns 1. |
| 209 | 0x3fe450 | 140 | CNetCnf::AddIFC(void*) | zNetCnf.cpp | MATCH | | m_addIFC (+0x95c0): push StartState, m_done = 0, sceNetcnfifDataInit(+0x9600), push IdleState; returns 1. |
| 223 | 0x3ff8a0 | 124 | CNetCnf::Open(char const*) | zNetCnf.cpp | MATCH | | m_open_handle = &theNetCnf, m_open's states (+0x10) push StartState, m_done (+0x2c) = 0, push CSMOpen::GetComboCount (0x43d3e8); m_open_handle re-read and returned. |
| 203 | 0x3fd630 | 12 | CNetCnf::GetComboData(void*) | zNetCnf.cpp | MATCH | | h + 0xa9c0 (m_addCombo.m_data). |
| 206 | 0x3fe1c0 | 168 | CNetCnf::GetDevIndex(void*) | zNetCnf.cpp | MATCH | | sprintf(name, "%s/%s", m_device + 12 vendor, + 268 product), i < m_numDevs (+0x3c, re-read): strcmp(m_devList (+0x8144)[i] (576 bytes) + 264 usr_name, name) == 0 -> i; else -1. |
| 207 | 0x3fe270 | 152 | CNetCnf::GetMACAddr(void*, char*, int) | zNetCnf.cpp | MATCH | | m_addDev m_macValid (byte +0x9540) -> sprintf(buf, "%02X:..", the six bytes +0x9541..0x9546), else buf[0] = 0; buf returned. |
| 208 | 0x3fe310 | 12 | CNetCnf::GetEnvData(void*) | zNetCnf.cpp | MATCH | | h + 0x9600 (m_addIFC.m_data). |
| 210 | 0x3fe760 | 40 | CNetCnf::GetInterfaceEntry(void*, int) | zNetCnf.cpp | MATCH | | m_interface.m_list (+0x81b4) + i * 524. |
| 211 | 0x3fe790 | 16 | CNetCnf::InterfaceCount(void*) | zNetCnf.cpp | MATCH | | m_interface.m_count (+0x81b0). |
| 212 | 0x3fe8d0 | 48 | CNetCnf::ReadInterfaceList(void*) | zNetCnf.cpp | MATCH | | m_interface (+0x8180).Start(6, h + 3520 m_combos); returns 1. |
| 213 | 0x3ff1f0 | 180 | CNetCnf::GetIfcDisplayName(void*, int) | zNetCnf.cpp | MATCH | | i < m_numDevs (+0x3c; ELF quirk kept, noted): strcmp(m_combos[combo] (+3520, 4928 each) attach_ifc, m_ifcList (+0x8140)[i] + 8 sys_name) == 0 -> + 264 usr_name; else "". |
| 214 | 0x3ff2b0 | 180 | CNetCnf::GetDevDisplayName(void*, int) | zNetCnf.cpp | MATCH | | As #213 with attach_dev (+256 of the combo) and m_devList (+0x8144). |
| 215 | 0x3ff370 | 24 | CNetCnf::GetNetDisplayName(void*, int) | zNetCnf.cpp | MATCH | | h + combo * 576 + 328 (m_comboList[combo].usr_name). |
| 217 | 0x3ff810 | 8 | CNetCnf::GetDefaultCombo(void*) | zNetCnf.cpp | MATCH | | +0x34 m_defaultCombo. |
| 218 | 0x3ff840 | 32 | CNetCnf::GetIFC(void*, int) | zNetCnf.cpp | MATCH | | m_ifcList (+0x8140) + i * 576. |
| 219 | 0x3ff860 | 8 | CNetCnf::NumDevs(void*) | zNetCnf.cpp | MATCH | | +0x3c. |
| 220 | 0x3ff870 | 8 | CNetCnf::NumIFC(void*) | zNetCnf.cpp | MATCH | | +0x38. |
| 221 | 0x3ff880 | 8 | CNetCnf::NumCombos(void*) | zNetCnf.cpp | MATCH | | +0x30. |
| 222 | 0x3ff890 | 12 | CNetCnf::Close(void*) | zNetCnf.cpp | MATCH | | m_open_handle = 0. The ELF returns 1 (0x3ff898); its one caller UINetCnfClose (0x1d2028) does not read it, so the port's void is equivalent (header lead). |
| 224 | 0x3ff9f0 | 68 | CNetCnf::Uninit() | zNetCnf.cpp | MATCH | | m_open_handle non-NULL -> 0; modid_NETCNFIF > 0 -> zSysUnloadIRX, 0; m_isinit = 0; returns 1. |
| 183 | 0x204590 | 72 | CZSealState::GetPackedWeaponData(CZSealBody*) | fts_net_seal.cpp | MATCH | | NetGetObject(&obj (zeroed), body->m_id (+0x4)): a nonzero result or NULL object -> NULL, else m_data (+0x1c) + 52 (SealWeapons), no m_data test in either. The port's zNetGetObject wrapper makes the same call and tests (the scan's call difference). |
| 184 | 0x2045e0 | 120 | CZSealState::GetBodyFromObjectIndex(int) | fts_net_seal.cpp | MATCH | | NetGetObject as #183, strcmp(obj + 12 m_name, "SealObject") != 0 -> NULL, m_data NULL -> NULL, else m_data + 0x94 pBody. |
| 182 | 0x204540 | 68 | CZSealState::RemoveNetSeal(int, bool) | fts_net_seal.cpp | MATCH | | theMission+0x584 net game NULL -> return; force or m_mp_major_game_state (+0xdb lbu) == GAMEOVER 6 -> NetFreeObject(index). |
| 185 | 0x204dc0 | 72 | CZSealState::RemoteSealPostUpdateCallback(int, int, int) | fts_net_seal.cpp | MATCH | | zNetGetObject(index, the second argument), m_data (+0x1c) and pBody (+0x94) non-NULL -> UpdateRollandsUnitStuff(pBody, m_data). |
| 186 | 0x205600 | 60 | CZSealState::SealDeleteCleanup(int) | fts_net_seal.cpp | MATCH | | zNetGetObject(index), m_data non-NULL -> pBody (+0x94) = 0. |
| 158 | 0x248560 | 136 | CCharacterType::CreateInstance(char const*) | char_type.cpp | MATCH | | m_model (+0x240) ? CNode::CreateInstance(model, NULL, NULL) : NULL; NULL node or re-read model NULL -> NULL; m_bForceExport (+0xc4) = 1, SetName(name), node returned. The scan's offsets are the port's layout. |
| 154 | 0x247a70 | 196 | CCharacterType::PlayAt(CHARACTER_SOUND, unsigned int, CPnt3D const*) | char_type.cpp | DEFECT-FIXED | A | Signed byte sound 0..65 -> m_sounds[i] (+0x11c) else NULL, NULL -> return; pos NULL -> slot +0x1c PlaySound(true, NULL, id); TerminateOnFinish on a non-NULL instance: agree. Fixed: the 3D call (slot +0x24 = PlaySound3D(pos, bool, float, int, CSndInstance*, uint), vt.py) passes the id as the entity in t1 (move t1, a2 at 0x247a88, unchanged to the jalr 0x247ad8); the port passed 0, so the AI's 3D lines got entity 0 (m_entityID, the death-damage Remove). |
| 152 | 0x2477e0 | 148 | CCharacterType::GetBaseName() | char_type.cpp | MATCH | | m_parentID (+0x10) <u m_char_list size -> m_char_list[id], non-NULL -> its m_name (+0x0), else NULL. |
| 153 | 0x247880 | 192 | CCharacterType::RdrFetch_CharacterType(char const*) | char_type.cpp | MATCH | | FindRdr("chartype.rdr") NULL -> NULL; match_name_to_chartype over navyseals / terrorists / escortees until non-NULL, GetByNameMod(type) (NULL passed through), zrdr_free(rdr), the type returned. |
| 150 | 0x247720 | 116 | CCharacterWeapList::RemoveWeapon(EQUIP_ITEM) | char_type.cpp | MATCH | | remove_if(begin, end, compare_item{signed byte item}), erase(first, end), first != end returned. |
| 151 | 0x2477a0 | 52 | CCharacterType::GetWeaponByIndex(unsigned int) const | char_type.cpp | MATCH | | index >=u m_weapons size (+0x254) -> 255 (the port's EQUIP_NONE value), else data (+0x258)[index] (12 bytes) m_wepId (lb). |
| 155 | 0x247bb0 | 128 | CCharacterType::ClearMultiplayerMessageSounds() | char_type.cpp | MATCH | | Every type of m_char_list (end re-read), every MultiplayerMessages entry (+0x2f4 size / +0x2f8 data, re-read) -> word +0x4 of the message = 0. |
| 156 | 0x248110 | 124 | GetCharacterSoundType(char const*) | char_type.cpp | MATCH | | NULL -> -1; i 0..65 as a signed byte: strcasecmp(name, GetCharacterSoundTypeString(i)) == 0 -> i; else -1. |
| 157 | 0x2484f0 | 100 | CCharacterGear::CreateInstance(char const*) const | char_type.cpp | MATCH | | m_model (+0x18) ? CreateInstance(model, NULL, NULL) : NULL; node and name non-NULL -> SetName; node returned. |
| 159 | 0x24a2c0 | 88 | CCharacterType::CleanupTemporary() | char_type.cpp | MATCH | | m_char_list.erase(remove_if(begin, end, DeleteTemporaryCharType), end). |
| 160 | 0x24a320 | 60 | DeleteTemporaryCharType(CCharacterType*) | char_type.cpp | DEFECT-FIXED | C | m_istemporary (+0x268 lbu) clear -> false; else delete (deleting dtor, a1 = 1) and the flag returned: agree. Fixed: the ELF reads the flag without a NULL test (0x24a32c); the port's `if (!chartype) return false` removed (the list holds no NULL: GetByNameMod 0x24a440 dereferences every entry). |
| 161 | 0x24a440 | 128 | CCharacterType::GetByNameMod(char const*) | char_type.cpp | MATCH | | begin..end (re-read): strcmp(type->m_name, name) == 0 -> type; else NULL; no NULL tests in either. |
| 162 | 0x24aff0 | 104 | CCharacterWeap::SetupCharacterWeapon(EQUIP_ITEM) | char_type.cpp | MATCH | | m_wepId (sb +0x0) = item first, m_listWeapons.GetWeapon(item), non-NULL -> m_ammoCount (+0x4) = GetAmmoCapacity, m_magCount (+0x8) = GetNumMags, m_ammoId (sb +0x1) = GetDefaultAmmoId. |
| 163 | 0x24b060 | 96 | CCharacterWeapList::AddWeapon(EQUIP_ITEM) | char_type.cpp | MATCH | | A local {255, 255, 0, 0} inserted once at end (the item unused: ELF quirk kept, noted); the later store of 255 to the dead local has no effect. |
| 181 | 0x1f0d00 | 108 | CEntity::SetUpdateTargetList(bool) | ent_target.cpp | MATCH | | update & 0xff == bit 1 of +0xdd -> return; !update -> m_targets (+0xcc).clear(); bit 1 = update & 1, others kept. The scan's +0xcc store is the port's word access of the same flag word. |
| 178 | 0x1ef920 | 84 | CTarget::GetRange() | ent_target.cpp | MATCH | | Bit 0 of +0x24 clear -> m_dist (+0x14) = sqrtf(m_distSq (+0x10)), bit 0 set; m_dist returned. |
| 179 | 0x1efad0 | 196 | CTarget::CTarget() | ent_target.cpp | MATCH | | m_ent, m_distSq, m_dist, m_visibility, m_aware, m_diHandle = 0; bits 0-4 and 6-31 of +0x24 cleared one by one, bit 5 m_dirty_di and m_vec left as they were in both. |
| 180 | 0x1efba0 | 76 | CTargetList::FindTarget(CEntity*) | ent_target.cpp | MATCH | | data .. data + size * 40, m_ent (+0x0) == ent -> that target, else NULL. |
| 24 | 0x37f8a0 | 156 | CLoadState::CLoadState() | st_load.cpp | DEVIATION-KEPT | | CGameState vtable and m_name (+0x4) = 0, the inlined SetName("LoadState") (free of a NULL name skipped, _strdup tagged "zgame.h" 84), own vtable, m_menu (+0x8) = m_e3config (+0xc) = 0: agree. Kept (reason in the code): InitThread (0x37f924) is left out under SOCOM_PORT, ps2sdk's _InitSys has already run it. |
| 23 | 0x37e560 | 56 | CLoadState::AbortLoad(char const*) | st_load.cpp | MATCH | | strncpy(theGame+0x9c m_DefaultMenu, menu, 64), m_abort (+0x1e) = 1. |
| 25 | 0x37fdd0 | 12 | CLoadMenu::GetReaderFileName() | st_load.cpp | MATCH | | "dlgLoad.rdr". |
| 280 | 0x310bb0 | 60 | zdb::CScrollingTexture_Object::CScrollingTexture_Object() | vis_bands.cpp | MATCH | | Empty vector (size_ +0x4, data_ +0x8 = 0), m_bandMax (+0xc) = 256. The scan's +0x4 / +0x8 are the vector's own init in GCC's base. |
| 282 | 0x310d00 | 60 | zdb::CPreLight_Object::CPreLight_Object() | vis_bands.cpp | MATCH | | As #280. |
| 285 | 0x310e90 | 60 | zdb::CMaterial_Object::CMaterial_Object() | vis_bands.cpp | MATCH | | As #280. |
| 287 | 0x310f50 | 60 | zdb::CSubSurf_Object::CSubSurf_Object() | vis_bands.cpp | MATCH | | As #280. |
| 290 | 0x3110b0 | 60 | zdb::CLOD_Object::CLOD_Object() | vis_bands.cpp | MATCH | | As #280. |
| 275 | 0x310700 | 164 | zdb::CVisData::ReplaceTextureData(uint16*) | vis_bands.cpp | MATCH | | m_pkt_idx = 0, m_pkt = m_chain + 16, while idx <u m_pkt_count: type (byte +2) 5 -> lq / sq the qword, the next packet's type (+0x12, re-read m_pkt) 8 -> half +0 - 1; 6 -> the qword, type byte = 5; idx / pkt advance (ELF quirks kept, noted). |
| 278 | 0x310a80 | 184 | zdb::CScrollingTexture_Object::Read(zdb::CSaveLoad*) | vis_bands.cpp | MATCH | | sload NULL (and sload + 4) -> return; OpenKey("TextureScroll_Object"), NULL -> GetOpenKey, return; resize(key size (+0x10) / 520 (0xfc0fc0fd >> 9)), Fetch(key, data, size, 0), CloseKey. ReadBands' sizeof is 520 (zrender.h layout); the scan's constants are GCC's division magic. |
| 283 | 0x310d50 | 196 | zdb::CMaterial_Object::Read(zdb::CSaveLoad*) | vis_bands.cpp | MATCH | | As #278 with "Material_Object" and / 28 (CMaterial_band: 12 + 4 + 4 + 1 + pad + pointer = 28). |
| 288 | 0x310fa0 | 148 | zdb::CLOD_Object::Read(zdb::CSaveLoad*) | vis_bands.cpp | MATCH | | No sload test (ELF quirk kept, noted), "LOD_Object", size >> 5 (32-byte CLOD_band), Fetch, CloseKey. |
| 274 | 0x310650 | 172 | zdb::CVisData::SetBilinear(uint16*, unsigned int) | vis_bands.cpp | MATCH | | m_pkt_count = lhu chain[0], m_pkt_idx = 0, m_pkt = chain + 16; first type 8 packet: reg = (word +4 + 16) or 0x20000000, half &= ~0x1c0 | (b & 7) << 6, then byte &= ~0x20 | (b & 1) << 5, return. |
| 276 | 0x3109a0 | 140 | zdb::CVisData::SelectVertex(zdb::CVisual*, unsigned int, unsigned int) | vis_bands.cpp | MATCH | | Clear, m_chain = visual m_buffers (+0x30 vector) [vid], m_pkt_count = lhu chain[0], m_pkt = chain + 16, m_index_pos = index, m_pkt_idx = 0, SearchVertex's result returned. |
| 277 | 0x310a30 | 80 | zdb::CVisData::Clear() | vis_bands.cpp | MATCH | | The 18 stores (+0x1c, +0x20, +0x10, +0x48, +0x28, +0x4, +0x44, +0x30, +0x4c, +0x50, +0x34, +0xc, +0x8, +0x14, +0x18 = 0; +0x54 / +0x5c = 0xffff, +0x58 = 0) by name. |
| 279 | 0x310b40 | 100 | zdb::CScrollingTexture_Object::~CScrollingTexture_Object() | vis_bands.cpp | MATCH | | The vector's dtor (storage freed) and the deleting flag; the port's swap with an empty vector frees it too before the base dtor. |
| 281 | 0x310c90 | 100 | zdb::CPreLight_Object::~CPreLight_Object() | vis_bands.cpp | MATCH | | As #279. |
| 284 | 0x310e20 | 100 | zdb::CMaterial_Object::~CMaterial_Object() | vis_bands.cpp | MATCH | | As #279. |
| 286 | 0x310ee0 | 100 | zdb::CSubSurf_Object::~CSubSurf_Object() | vis_bands.cpp | MATCH | | As #279. |
| 289 | 0x311040 | 100 | zdb::CLOD_Object::~CLOD_Object() | vis_bands.cpp | MATCH | | As #279. |
| 194 | 0x215860 | 164 | zdb::CGrid::GetNextAtomOrdered() | grid_main.cpp | MATCH | | m_NextAtom (+0xf8) NULL -> rt (+0x110) == count (+0x10c) -> NULL, else m_ring = entry rt ring (+0x120 + 16 rt), rt + 1, m_NextAtom = entry cellAtom (+0x11c); else its Next (+0x4); NULL -> again; node m_active (bit 0 of +0x5c) clear or its m_TickNum (+0xa4) >= m_TickNum (+0x50) -> again; else the tick stored, the atom returned. |
| 192 | 0x214e30 | 160 | zdb::CGrid::DeleteClutter() | grid_main.cpp | DEFECT-FIXED | C | count = cx * cy, for each slot: the inlined GetCell of m_Atoms[i] (type lhu +0x58 == 10, else NULL) and CCell::DeleteClutter on it, m_ClutterCreated (+0x2c) = 0: agree. Fixed: the ELF calls DeleteClutter on GetCell's result unchecked (0x214e90 / 0x214e98); the port's type guard (skipping a non-cell) removed, the call now goes through GetCell as the ELF. |
| 195 | 0x215a30 | 164 | zdb::CGrid::gridGetGridXandZIndex(int*, int*, float, float) | grid_main.cpp | MATCH | | m_InvCellDim * (px - m_origin.x) and * (pz - m_origin.z), truncated (vftoi0; the port's (s32) cast truncates too), < 0 -> 0, !(x < cx) -> cx - 1, same for z with cy. |
| 190 | 0x214d50 | 176 | zdb::CGrid::Read(zdb::CSaveLoad&) | grid_main.cpp | MATCH | | params = {N_ATOMS, 16, 640.0, 8, 8}, Fetch("grid_params", &params, 20) folded to 1 (ELF quirk kept, noted), Create(sload.m_world, &params) & 0xff returned. |
| 191 | 0x214e00 | 40 | zdb::CGridAtom::GetCell() | grid_main.cpp | MATCH | | Ent (+0x0) m_type (lhu +0x58) == 10 -> Ent, else NULL. |
| 193 | 0x215850 | 8 | zdb::CGrid::Insert(zdb::CNode*) | grid_main.cpp | MATCH | | Tail call gridAddNodeToGrids(node). |
| 196 | 0x215ca0 | 48 | zdb::CGrid::StartTraversalOrdered() | grid_main.cpp | MATCH | | m_NextAtom = 0, = GetNextAtomOrdered(), re-read and returned. |
| 197 | 0x215cd0 | 108 | zdb::CGrid::StartTraversal() | grid_main.cpp | MATCH | | m_xx = m_ix, m_zz = m_iz, m_iz_start = m_zz, m_iz_next_row = m_izb, m_NextAtom = 0, m_zz - 1, m_RowCellIn = 0, m_CurCellOut = 1, m_iz_dir = 1, m_NextAtom = GetNextAtom() returned. |
| 198 | 0x216e70 | 88 | zdb::CGrid::gridGetAtomBasePtr(int, int) | grid_main.cpp | MATCH | | x, y clamped to 0 .. cx - 1 / cy - 1, m_Atoms (+0x30) + x + y * cx. The ELF compares signed, the port's u32 locals unsigned: the same for any grid with cells (x, y >= 0 there). |
| 199 | 0x216ed0 | 108 | zdb::CGrid::~CGrid() | grid_main.cpp | DEVIATION-KEPT | | Destroy, the clutter manager's deleting dtor and m_ClutterAnimManager (+0x28) = 0, the deleting flag: the same calls. Kept (reason in the code): the port deletes the manager before Destroy; in the ELF order its anims' dtors write into the clutter Destroy has freed. |
| 200 | 0x222f90 | 160 | exp_tl(float) | zmath_trig.cpp | MATCH | | !(x <= 10) -> 10 (c.le.s / bc1t), else x < 0 -> 0 (c.lt.s), f = x * m_exp_scl, i = fptosi(f), lo = exptbl[i], lo + (f - (f32)i) * (exptbl[i + 1] - lo): the same forms and order. |
| 201 | 0x223030 | 24 | uninit_trig_table() | zmath_trig.cpp | MATCH | | tableInit (lbu) set -> 0. |
| 225 | 0x232630 | 188 | Particle::ReleaseInstance(zdb::CNode*) | zparticle.cpp | MATCH | | particle_node_free_list.push_back(node) (MSL's inline grows a full vector by 10: the library's policy), SetActive(false) (slot +0x34), DeleteVisuals, CWorld::m_world->DeleteChild(node) (slot +0x1c); particle_node_count untouched in both. |
| 227 | 0x2340f0 | 176 | Particle::FreeNodePool() | zparticle.cpp | MATCH | | CNode::Delete on every pool node, size = 0, swap with an empty vector, which is destroyed (storage freed). |
| 226 | 0x233ed0 | 132 | Particle::FlushDynTexList() | zparticle.cpp | MATCH | | m_tex_list (+0x0) then m_pal_list (+0xc): clear, swap with an empty vector, destroy it. |
| 228 | 0x2341a0 | 60 | Particle::ReserveNodePool() | zparticle.cpp | MATCH | | capacity <u 160 -> reserve(160). |
| 229 | 0x2341e0 | 80 | Particle::AddDynTexture(zdb::CTexHandle*) | zparticle.cpp | MATCH | | m_dyntexlist.Add(texture, true), m_texture (+0xc) m_palette (+0x1c) non-NULL -> Add(palette, true). |
| 230 | 0x234230 | 12 | Particle::GetDynTexList() | zparticle.cpp | MATCH | | &m_dyntexlist. |
| 231 | 0x2343e0 | 60 | Particle::Init() | zparticle.cpp | MATCH | | As #228. |
| 167 | 0x1ec7e0 | 184 | CConsole::FindHandler(unsigned int) | con_main.cpp | MATCH | | m_handlers (+0x18) size 0 -> NULL; begin..end, the handler's m_type (+0x4) == type -> it; else NULL: HandlerOfType's body. |
| 164 | 0x1ec6f0 | 60 | CHandler::Dispatch(CPacket*, CConsole*) | con_main.cpp | MATCH | | m_func (+0x8) NULL -> 0; else m_func(packet, console, m_data (+0xc)), 1. |
| 165 | 0x1ec730 | 96 | CHandler::~CHandler() | con_main.cpp | MATCH | | m_name non-NULL -> free, m_name = 0 (delay slot 0x1ec76c, either way), deleting flag. |
| 166 | 0x1ec790 | 80 | CHandler::CHandler(char const*, unsigned int, void (*)(CPacket*, CConsole*, void*), void*) | con_main.cpp | MATCH | | m_name = 0, m_type, m_func, m_data, then m_name = name ? strdup(name) : NULL. |
| 168 | 0x1ecb20 | 120 | CConsole::Debug(int, char const*, ...) | con_main.cpp | MATCH | | m_debug < level (slt) -> nothing; vsprintf into a 1024-byte local from the varargs, printf(buffer) (the text as the format, ELF). |
| 169 | 0x1ed250 | 8 | _on_error(CPacket*, CConsole*, void*) | con_main.cpp | MATCH | | Empty. |
| 170 | 0x1ed260 | 8 | _on_ping(CPacket*, CConsole*, void*) | con_main.cpp | MATCH | | Empty. |
| 171 | 0x1ed270 | 16 | _on_status(CPacket*, CConsole*, void*) | con_main.cpp | MATCH | | Tail call of the packet's virtual GetPacketMsg (slot +0xc), result unused. |
| 233 | 0x23cf30 | 124 | CRdrFile::CRdrFile() | zrdr_file.cpp | MATCH | | The inlined base ctor clearing isclone / packed (bits 8 / 9 of +0x0), CSTable(0, 1024) at +0x8, m_buffer (+0x24) = m_size (+0x28) = 0. The port's member CSTable() differs from CSTable(0, 1024) only in m_owner, which nothing reads while m_buffer is NULL (LoadTable sets it). Lead: the port's shared _zrdr() (zreader_holding.cpp, not this list) also zeroes type, length and array, which the ELF's inline form leaves as they were (defined values only; no reason comment there). |
| 232 | 0x23ce90 | 148 | CRdrFile::~CRdrFile() | zrdr_file.cpp | MATCH | | m_buffer NULL -> zrdr_freearray(this); else _free(m_buffer, "zrdr_file.cpp", 48), m_buffer = m_size = 0; then ~CSTable (+0x8), ~_zrdr, the deleting flag (member / base dtors in the port). |
| 234 | 0x23cfb0 | 124 | zrdr_free(CRdrFile*) | zrdr_file.cpp | MATCH | | NULL test (in the ELF), the inlined ~CRdrFile and delete; returns 0. |
| 235 | 0x23d030 | 52 | zrdr_findbool(_zrdr const*, char const*, bool*) | zrdr_file.cpp | MATCH | | zrdr_tobool(zrdr_findtag_startidx(reader, tag, 1), output)'s result. |
| 236 | 0x23d300 | 168 | zrdr_findSTRING(_zrdr const*, char const*, char const**) | zrdr_file.cpp | MATCH | | findtag(name, 1) NULL or list NULL -> 0; type (lbu) 4 with array->integer >= 2 -> array + 8 (element 1); type 3 -> *list = string, 1; type 1 with integer 0 -> *list = 0, 1; else 0. |
| 268 | 0x1749b0 | 136 | C2D::GetAssetLibs(C2D::CLibList&) | ztwod_holding.cpp | MATCH | | Every child of the list: its GetAssetLibs(libs) through vtable slot +0x48 (vptr +0xc). |
| 269 | 0x174a90 | 8 | C2D::CanHandleInput() | ztwod_holding.cpp | MATCH | | m_active_and_handling_input (+0x14 lbu). |
| 270 | 0x174aa0 | 8 | C2D::SetCanHandleInput(bool) | ztwod_holding.cpp | MATCH | | +0x14 = enable (sb). |
| 271 | 0x174ad0 | 32 | C2D::SetUseFrameBufferAlpha(bool) | ztwod_holding.cpp | MATCH | | Bit 4 of +0x15 m_isFrameAlpha = enable & 1, others kept. |
| 291 | 0x314690 | 116 | CZWeaponList::ClearAnimations() | zwep_weaponlist.cpp | MATCH | | begin..end, each weapon's ClearAnims. |
| 292 | 0x314a40 | 148 | CZWeaponList::GetWeaponByIndex(int) | zwep_weaponlist.cpp | MATCH | | Walk with a counter, counter == index -> that weapon, else NULL. |
| 293 | 0x314ae0 | 144 | CZWeaponList::GetWeapon(EQUIP_ITEM) | zwep_weaponlist.cpp | MATCH | | m_ID (+0x60 lbu) == id & 0xff -> the weapon, else NULL. |
| 294 | 0x314b70 | 184 | CZWeaponList::GetWeaponName(EQUIP_ITEM) | zwep_weaponlist.cpp | MATCH | | As #293, found -> GetName(), else "Unknown Weapon". |
| 295 | 0x314d00 | 184 | CZWeaponList::GetWeapon(char const*) | zwep_weaponlist.cpp | MATCH | | strcmp(name, weapon GetName()) == 0 -> the weapon, else NULL (arguments in that order). |
| 296 | 0x314f20 | 40 | CZWeaponList::CZWeaponList() | zwep_weaponlist.cpp | MATCH | | The empty list's ctor only. |
| 187 | 0x214580 | 148 | zdb::DiIntersect::GetHighestAltitude(CPnt3D const*, float) | grid_di.cpp | MATCH | | m_Cnt (+0x34) <= 0 -> NULL; top = pos.y + height; each hit (32 bytes from m_Intersects +0x44): y <= top (c.le.s / bc1f) and (no best or !(y <= best.y)) -> best; best returned: the same forms. |
| 188 | 0x214860 | 92 | _cmpdi(void const*, void const*) | grid_di.cpp | MATCH | | _cmpdi_rs[*a] < [*b] -> -1; else == -> 0, else 1 (c.lt.s, c.eq.s forms as the port's). |
| 189 | 0x2148c0 | 8 | zdb::SetCameraCollideFlagRequired(bool) | grid_di.cpp | MATCH | | cameraCollideFlagRequired = required (sb). |
| 149 | 0x1dd1f0 | 48 | CScriptArchive::LoadAll() | bone_archive.cpp | MATCH | | FetchAll on the CZAR part (this + 12; the port's static_cast) with CZSIScript::CreateAndReadIt and the same pointer as data; 0 < (result & 0xff) returned. |
| 265 | 0x2f37d0 | 104 | CSched_Task::~CSched_Task() | zsys_sched.cpp | MATCH | | m_name non-NULL -> _free(m_name, "zsys_sched.cpp", 361); m_name = 0; deleting flag. |
| 266 | 0x2f3b10 | 100 | _task_cleanup(CSched_Task*) | zsys_sched.cpp | MATCH | | m_removed (+0x4 lbu) clear -> false; the task NULL test after that read (in the ELF too), the inlined dtor and delete; true. |
| 267 | 0x2f4180 | 104 | CSched_Manager::CSched_Manager() | zsys_sched.cpp | MATCH | | Task list constructed, m_inTick (+0xc) = 0, m_priority (+0x10) = 0, m_FreeList (+0x14) constructed and erased begin..end (clear). |
