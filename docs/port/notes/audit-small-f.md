# Audit of list small-f (2026-11-19, socom-port-audit-small-f)

296 small functions (24,940 bytes, each under 200 bytes) in 30 files: Apps/FTS/game (beachball,
orders), Apps/FTS/hud (hud_letterbox, hud_playermapitem), zAI (ai_log, ai_vismap), zAnim
(zanim_anim, zanim_load, zanim_sequence), zCamera fov, zGrid grid_clutter, zInput remote_control,
zMPEG zmpeg, zNetwork zNetDme, zNode (node_projectedmap, node_saveload, node_shadow), zReader
zrdr_main, zSeal (seal_ai, seal_squirm, seal_unit), zSound zsnd_csnd, zSystem (zsys_bench,
zsys_memory), zTexture (ztex_main, ztex_palette), zUI zui_var, zUtil util_bufio, zVideo zvid_draw,
zWeapon zwep_ammo. HEAD cd4a0470. Judged file by file in the scan's rank order, from the by-file
packets.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 273 |
| DEFECT-FIXED | 23 (A 0, B 2, C 21) |
| DEVIATION-KEPT | 0 |
| UNJUDGED | 0 |

Defect rate 23 / 296 (B 2, C 21).

Fixes:
- B, #6 OrdersMenu::OnRecoCmd: the ELF keeps the recogniser's result (recoResult[0..3] = the four
  ints, handle_reco_result 1, sprintf of the last word at +0x10; 0x17c540-0x17c578); the port was
  an empty stub. Masked: the port's recogniser never starts.
- B, #246 _free: the ELF frees with interrupts off (DIntr 0x2f48ec / EIntr 0x2f48fc) as _delete does;
  the port called free alone.
- C, #221 CSnd::AddNewCSnd: m_soundlist insert at the end (*data() + size, 0x2edb60), not begin.
- C, #170 CSealCtrlAi::OnSetHealth: !(old <= health) as the ELF tests it (c.le.s 0x269bb8).
- C, #177 CSealCtrlAi::StopAiSound: the slot cleared only after a Stop (0x26bf84).
- C, #97 CZNetwork::zNetRemoteObjectUpdateCallback: the object pointer is not cleared before
  NetGetObject (0x321348).
- C, #99 CZNetwork::zNetLeaveAndDisconnect: m_bJoined cleared after NetLeave (0x32156c).
- C, #259 CUIVarManager::~CUIVarManager: clear() of the variables first (0x39e080).
- C, #258 CUIVarManager::FindDormantVar: the name goes into theUIVarManager's current table (0x39dd74).
- C, #65 CZAnimMain::UnloadSIScript: _free tag ("zanim_load.cpp", 80), size and frame count cleared
  (0x1c2388-0x1c23a4).
- C, #128 zrdr_findfile: sprintf (0x23e500), not a bounded snprintf.
- C, #127 _zrdr::_zrdr(_zrdr*, CSTable*): only isclone cleared before Clone (0x23e158).
- C, #237-#242, #244 _strdup / _calloc / _realloc / _memalign / _malloc / _new_vec / _new: the
  assert's file is "zsys_memory.cpp" (0x4588a0), not the tree path of __FILE__.
- C, #87 CRemoteCtrl::Tick: CSealCtrl::ClearGoal called directly (jal 0x2ce6c8).
- C, #21 CZAnim::ExecuteSpecialSequence: offset <= 0 returns before ZAnim's anim / sequence are
  saved and stored back (bgtz 0x1c8f18).
- C, #116 CProjectedMap_Object::~CProjectedMap_Object: no body of its own (0x22b260), the swap
  removed.
- C, #71 CSequence::Start: m_currT = down + (up + hold) (add.s 0x1dc930 / 0x1dc934).

Kept deviations: none new. Port deviations already recorded and kept: zsys_MemoryReport's ps2sdk
_ftext / _fdata / _end, ActivateArg's GCC n32 va_list, the port trace lines of Output / Debug /
SetTarget (SOCOM_PORT_TRACE_ON only), the CGrid-by-pointer layout of CWorld (GetMatrix, Tick).

ELF quirks kept: CSnd::CSnd's m_type 0 then 1 and the pool reserve per sound; CSealUnit::
ResetPointOutState's second stores of +0x20 / +0x21; CTexture::~CTexture's double UNNAMED_TEX store;
CZNetwork::zNetCreateObject's unused client index; CBufferIO::freadchar reading into its pointer
argument; sceVu0ClipBBox's uncleared clip register (bits 14+ can carry judgements from before the
call; the port starts at 0 and TestFOV reads only 0x3f / 0x3f00).

Leads for other lists: CZAnimArgValve::Copy (0x1ce4f0) stores the type through a NULL new (not
reproduced). The default _zrdr::_zrdr() kept deviation (small-b #68) is untouched; #127 is the
cloning ctor only.

What the packets lacked: #232 IOPRebootHandler showed st_menu.cpp's static of the same name, not
zsnd_csnd.cpp's (line 325); #13 CZPlayerMapItem::Draw names the slot +0xc calls Tick (they are
Draw); #12 PostDraw's slot +0x18 needed vt.py (C2DString 0x472cb0: Off); #221 needed the vector_pod
data() / end() bodies (0x1737a0 / 0x174a50) to see the insert position; #211 the CKey layout
(zar.h); #144 the _saturate bounds (0x474f90 / 94, read from the ELF); #151 how the port stores
ASTAR_STATUS (raw planner codes, ai_astar.cpp); #101 the NetConnectParams / NetOutParams offsets
(dme.h). About 15 functions needed a lookup outside the packet.

Runs: the default build links (audit-small-f-default). Smoke: gate.ps1 -Only roundtrip on this tree PASS (4 returns, in use 18,657,916 B flat; 471 s).

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 232 | 0x2ee360 | 56 | IOPRebootHandler(RebootPhase, RebootMode, void*) | zsnd_csnd.cpp | MATCH | - | the packet showed st_menu.cpp's static of the same name; the zsnd_csnd.cpp static (line 325): phase == PreReboot (andi 0xff, bnez) snd_StopSoundSystem, else snd_StartSoundSystem, returns 1 |
| 204 | 0x2ebd20 | 136 | CSnd::ResetGroupVolTemp() | zsnd_csnd.cpp | MATCH | - | 7 groups: m_fadegroup[i] != -1 -> snd_SetMasterVolume(group, m_fade_oldvol[i]), group = -1; m_fadepct then m_fadetime 0 |
| 205 | 0x2ebec0 | 60 | CSnd::SetGroupVol(int, float) | zsnd_csnd.cpp | MATCH | - | (int)(1024 * volume) (mul.s f0, f12), snd_SetMasterVolume(group, ...) |
| 206 | 0x2ebf00 | 64 | CSnd::SetReverbSeconds(float const*) | zsnd_csnd.cpp | MATCH | - | NULL -> 240, else 240 * *seconds; fptosi to g_iReverbTime |
| 207 | 0x2ebf40 | 72 | CSnd::SetReverbDepth(float const*) | zsnd_csnd.cpp | MATCH | - | NULL -> 10922f, else 32767f * *depth; fptosi to g_iReverbDepth |
| 208 | 0x2ebf90 | 120 | CSnd::WaitForCDRead() | zsnd_csnd.cpp | MATCH | - | m_max_num_vags 0 / snd_system_initialized (lbu) 0 exits; StopAllStreams, flush while nonzero, StreamSafeCheckCDIdle(1) until nonzero |
| 209 | 0x2ec010 | 52 | CSnd::PlayErrorSound() | zsnd_csnd.cpp | MATCH | - | m_errorsound (CSnd*) NULL test, slot +0xc PlaySound(NULL, 255) |
| 210 | 0x2ec050 | 36 | CSnd::OnListenerDeath() | zsnd_csnd.cpp | MATCH | - | CSndJukebox::FadeOut, StopAllSounds(3 SND_MODE_DIALOG) |
| 211 | 0x2ec470 | 128 | CSnd::vagReadOffset(char const*, unsigned int&, unsigned int&) | zsnd_csnd.cpp | MATCH | - | m_isDisabled -> 0; FindKey; offset = key +0x14 m_offset, size = +0x10 m_size, CloseKey; returns key != NULL |
| 212 | 0x2ec780 | 112 | CSnd::CalcVol(float, float) | zsnd_csnd.cpp | MATCH | - | dist <= m_range.x 1, <= m_range.y 1 - (dist - x) / (y - x), else 0 (c.le.s both); volume * ((1024 att) m_mastervol), tail fptosi |
| 213 | 0x2ec9b0 | 72 | CSnd::PlaySoundVolPanPitch(float, int, int, bool, CSndInstance*, unsigned int) | zsnd_csnd.cpp | MATCH | - | m_isOneShot +0x1d saved (lbu), set from a3, slot +0x18 with instance t0 -> a3, entity t1 -> t0, restored, result returned |
| 214 | 0x2eca00 | 76 | CSnd::PlaySound3D(CPnt3D const*, bool, float, int, CSndInstance*, unsigned int) | zsnd_csnd.cpp | MATCH | - | +0x1d saved / set from a2 / restored; slot +0x14 (pos, volume f12, pitch a3 -> a2, instance t0 -> a3, entity t1 -> t0) |
| 215 | 0x2eca50 | 72 | CSnd::PlaySoundVol(float, bool, CSndInstance*, unsigned int) | zsnd_csnd.cpp | MATCH | - | +0x1d saved / set from a1 / restored; slot +0x10 (volume, instance, entity) |
| 216 | 0x2ecaa0 | 72 | CSnd::PlaySound(bool, CSndInstance*, unsigned int) | zsnd_csnd.cpp | MATCH | - | +0x1d saved / set from a1 / restored; slot +0xc (instance, entity) |
| 217 | 0x2ed200 | 64 | CSnd::PlaySoundVol(float, CSndInstance*, unsigned int) | zsnd_csnd.cpp | MATCH | - | m_isDisabled -> NULL; slot +0x18 (volume, -1, 0, instance, entity) |
| 218 | 0x2ed240 | 72 | CSnd::PlaySound(CSndInstance*, unsigned int) | zsnd_csnd.cpp | MATCH | - | m_isDisabled -> NULL; slot +0x18 (1f, -1, 0, instance, entity) |
| 219 | 0x2ed290 | 8 | CSnd::GetSubtitles() | zsnd_csnd.cpp | MATCH | - | lbu m_bShowSubtitles returned |
| 220 | 0x2ed2a0 | 8 | CSnd::SetSubtitles(bool) | zsnd_csnd.cpp | MATCH | - | sb m_bShowSubtitles |
| 221 | 0x2edb10 | 140 | CSnd::AddNewCSnd(CSnd*) | zsnd_csnd.cpp | DEFECT-FIXED | C | m_isDisabled exit, sound_map[string(m_name +0x8)] = sound agree; the ELF inserts into m_soundlist at *data() + size (data() 0x1737a0 returns &vec+8, size at vec+4: the end, as LoadSounds' end() 0x174a50) at 0x2edb60-0x2edb88; the port inserted at begin(). Only the delete order in the teardown read the list; now end() |
| 222 | 0x2edf50 | 48 | CSnd::LoadSounds(char const*) | zsnd_csnd.cpp | MATCH | - | m_isDisabled -> 0, else LoadSounds(name, name) |
| 223 | 0x2edf80 | 8 | CSnd::SetupJukebox(char const*) | zsnd_csnd.cpp | MATCH | - | tail CSndJukebox::LoadPlaylists(name) |
| 224 | 0x2edf90 | 40 | CSnd::SetupSoundGroups() | zsnd_csnd.cpp | MATCH | - | !m_isDisabled -> CSndGroup::LoadSoundGroups |
| 225 | 0x2edfc0 | 128 | CSnd::GetSoundByName(char const*) | zsnd_csnd.cpp | MATCH | - | m_isDisabled -> NULL; sound_map.find(string(name)), == end (tail) -> NULL, else node +0x10 second |
| 226 | 0x2ee040 | 16 | CSnd::CleanupLoading() | zsnd_csnd.cpp | MATCH | - | reads m_isDisabled only; empty |
| 227 | 0x2ee050 | 40 | CSnd::Close() | zsnd_csnd.cpp | MATCH | - | m_max_num_vags 0, ftsDeleteHeadset, snd_CloseVAGStreaming, m_streamingSndActive 0 |
| 228 | 0x2ee080 | 88 | CSnd::Open() | zsnd_csnd.cpp | MATCH | - | m_streamingSndActive 1, NULL _sound_rdr -> zrdr_read("sounds.rdr", NULL, 0), m_max_num_vags 6, snd_InitVAGStreamingEx(6, 0xf000, 1, 1) |
| 229 | 0x2ee0e0 | 88 | CSnd::UIOpen() | zsnd_csnd.cpp | MATCH | - | sounds.rdr read when NULL; m_vagEnabled -> streaming 1, 4 vags, InitVAGStreamingEx(4, 0xf000, 1, 1) |
| 230 | 0x2ee140 | 104 | CSnd::NetOpen() | zsnd_csnd.cpp | MATCH | - | as UIOpen with snd_SetMasterVolume(8, 1024) between |
| 231 | 0x2ee1b0 | 32 | CSnd::Uninit() | zsnd_csnd.cpp | MATCH | - | zrdr_free(_sound_rdr), _sound_rdr NULL |
| 233 | 0x2ee490 | 180 | CSnd::CSnd() | zsnd_csnd.cpp | MATCH | - | m_isDisabled return; every store's offset and value (1f, NULL, 160f, 430f, -1, -1, bytes 0, subtitle_time before translator), m_type 0 then pool reserve(48) and m_type 1 (the ELF's quirk, stored in the call's delay slot) |
| 234 | 0x2ee550 | 8 | GetSoundRdrFile() | zsnd_csnd.cpp | MATCH | - | lw _sound_rdr returned |
| 202 | 0x2d2b10 | 180 | GetUnitNameStringFromUnitNum(int, char*) | seal_unit.cpp | MATCH | - | sprintf(out, name) for 2 ABLE, 3 BRAVO, 1 TEAM, 17 ESCORTEE, 29 SUPPORT, others untouched (the scan's vfprintf / stores are GCC's sprintf-to-copy) |
| 194 | 0x2cece0 | 156 | _check_proximity(MAP_LINEWALK_STRUCT const&, void*) | seal_unit.cpp | MATCH | - | x bits 6-18 of walk +0xc / data +0 (dsll32 13 / dsrl32 19), y bits 19-31 (lhu +0xe / +2), CAiMapLoc's x:13 / y:13 after m_mapid:6; abs differences summed < +0x4 m_cells -> 0; data +0xc = walk +0x14 dist, returns dist < +0x8 range (c.lt.s) |
| 195 | 0x2cf110 | 36 | CSealUnit::ResetPointOutState() | seal_unit.cpp | MATCH | - | sb 0 to +0x8, +0x20, +0x21, +0x22, +0xc, +0xe; the ELF stores +0x20 / +0x21 a second time (same value) |
| 196 | 0x2cf140 | 56 | CSealUnit::UpdatePointOutState() | seal_unit.cpp | MATCH | - | +0x8 = (+0x22 != 0 \|\| +0xe != 0), reread, +0x9c m_point_ticks = 2 when set |
| 197 | 0x2cf720 | 8 | SetPlayAutoMessages(bool) | seal_unit.cpp | MATCH | - | sb bgAutoMessagesOn |
| 198 | 0x2cf730 | 8 | GetPlayAutoMessages() | seal_unit.cpp | MATCH | - | lbu bgAutoMessagesOn returned |
| 199 | 0x2cf740 | 172 | CSealUnit::TickAll(float, void*) | seal_unit.cpp | MATCH | - | !m_created_units_test -> 1; every m_list unit with +0x3c m_parent NULL ticked (dT, buf); returns 0 |
| 200 | 0x2d22a0 | 8 | CSealUnit::GetConfirmVoiceCommands() | seal_unit.cpp | MATCH | - | lbu ShouldConfirmVoiceCommands returned |
| 201 | 0x2d22b0 | 8 | CSealUnit::SetConfirmVoiceCommands(bool) | seal_unit.cpp | MATCH | - | sb ShouldConfirmVoiceCommands |
| 203 | 0x2d7590 | 144 | CSealUnit::GetUnitByTeam(unsigned int) | seal_unit.cpp | MATCH | - | first m_list unit whose +0x38 m_unit_num == team, else NULL |
| 165 | 0x267470 | 164 | CSealCtrl::ClearGoal(GOAL_TYPE) | seal_ai.cpp | MATCH | - | type 0 -> lb +0x1a8 m_goal_type; lbu goal type != (u8)type exits; bit 0 of +0x168 cleared, others kept; bit 1 clear -> type byte 0; SetGoalDir(type, NULL, 0); +0x1b8 m_timer, +0x1b0 m_min = infinite, +0x1b4 m_range 0 in that order (the slt at 0x26749c is always 0 there: a dead branch) |
| 158 | 0x264170 | 36 | CSealCtrlAi::Output(char const*, ...) | seal_ai.cpp | MATCH | - | the ELF only spills the varargs; the port formats nothing in the default build (the text goes to the port trace only with SOCOM_PORT_TRACE_ON, port-only) |
| 159 | 0x2641a0 | 36 | CSealCtrlAi::Debug(char const*, ...) | seal_ai.cpp | MATCH | - | as Output |
| 157 | 0x2640d0 | 152 | CSealCtrlAi::SetTarget(CTarget*) | seal_ai.cpp | MATCH | - | same = target ? +0x4bc == target->m_ent : +0x4bc == NULL, exit; NULL entity skips CanAttack (v1 1); CAiTarget::SetTarget(+0x4bc, target, 0f); the trace line is port-only |
| 160 | 0x2641d0 | 120 | CSealCtrlAi::PutAiLog(unsigned int, unsigned int, void const*) | seal_ai.cpp | MATCH | - | aiLogEnabled (lbu), GetAiLog NULL exit, Write(type, m_entity->m_id, size, data) a1-t0 |
| 161 | 0x264250 | 28 | CSealCtrlAi::SetDebug(bool) | seal_ai.cpp | MATCH | - | bit 0 of +0x280 from a1 & 1, others kept |
| 162 | 0x264640 | 92 | CSealCtrlAi::SlideTick(float) | seal_ai.cpp | MATCH | - | goals +0x274/278/27c, throttles +0xc, +0x10, +0x8 zeroed in that order; CSealCtrl::SlideTick (0/1); 0 -> SetAiMode(1); byte returned |
| 163 | 0x264d30 | 136 | CSealCtrlAi::AllStop(bool) | seal_ai.cpp | MATCH | - | slew: slot +0x20 SetThrottle(1, 0), (2, 0), (0, 0); else the six stores in the ELF's order |
| 164 | 0x264dc0 | 88 | CSealCtrlAi::SetThrottle(unsigned int, float) | seal_ai.cpp | MATCH | - | lbu +0x30c m_mode == 2 and !(0 == throttle) (c.eq.s) exits; goal[index] (+0x274), index 2 also throttle[2] (+0x10); the ELF's this == NULL path (a3 1) cannot happen |
| 166 | 0x267520 | 104 | CSealCtrlAi::ResetToInitialState() | seal_ai.cpp | MATCH | - | CSealCtrl::ResetToInitialState, ClearAiState(1), ActivateEx(1, 1, 1, +0x318 m_select, 3, GetNode(), 0) a1-t3 |
| 167 | 0x267590 | 80 | CSealCtrlAi::OnRecycleEntity(CEntity*) | seal_ai.cpp | MATCH | - | m_entity == entity; +0xdc m_unit -> SealLeaveUnit(m_entity); slot +0x60 OnMissionEnd |
| 168 | 0x269430 | 192 | CSealCtrlAi::Dump() | seal_ai.cpp | MATCH | - | CSealCtrl::Dump, the empty loops (8..14, the +0x324 list), PrintPath(+0x36c) |
| 169 | 0x269800 | 80 | CSealCtrlAi::AnimIsPlaying(AnimType) | seal_ai.cpp | MATCH | - | m_entity +0x130 m_blends Top(); NULL 0; lh +0x30 m_animType == (s16)type |
| 170 | 0x269bb0 | 80 | CSealCtrlAi::OnSetHealth(float, float) | seal_ai.cpp | DEFECT-FIXED | C | the ELF goes on when !(old <= health) (c.le.s $f13,$f12 0x269bb8, bc1t skip); the port's health < old differed for NaN only, now in the ELF's form; Remove(m_id, 1, 1), slot +0x24 PlayAiSound(57) agree |
| 171 | 0x26adf0 | 76 | CSealCtrlAi::OnMissionEnd() | seal_ai.cpp | MATCH | - | ClearAiState(1); +0x364 m_task_handle[4] Stop, NULL; SetAiMode(2) |
| 172 | 0x26ae40 | 140 | CSealCtrlAi::OnMissionStart() | seal_ai.cpp | MATCH | - | SetupAnimations; ActivateEx(1, 1, 1, select, 3, node, 0) and (4, 0, 1, select, 3, node, 0) |
| 173 | 0x26b9e0 | 104 | CSealCtrlAi::get_valve(SEAL_VALVE) | seal_ai.cpp | MATCH | - | jump table 0x4520f0: 0 holdfire, 1 shotat, 2 alive, 3 aware, 4 / 5 / above "error" |
| 174 | 0x26bb40 | 72 | CSealCtrlAi::AiStateIs(AI_STATE) const | seal_ai.cpp | MATCH | - | GetAiState NULL -> 0 else +0x10 (u8 m_state); bytes compared |
| 175 | 0x26bb90 | 48 | CSealCtrlAi::GetAiStateEnum() const | seal_ai.cpp | MATCH | - | +0x10 or 0 (lb; every state below 30, no sign difference) |
| 176 | 0x26bdf0 | 64 | CSealCtrlAi::SetAiLogEnabled(bool, bool) | seal_ai.cpp | MATCH | - | aiLogEnabled = on, aiLogFlag 0; on -> flag; off with flag -> ~CAiLog(aiLogFile, 1), aiLogFile 0 |
| 177 | 0x26bf50 | 72 | CSealCtrlAi::StopAiSound(AI_SOUND) | seal_ai.cpp | DEFECT-FIXED | C | (s8) index into aiSoundInstance; the ELF clears the slot only after Stop (sw 0x26bf84 inside the non-NULL branch); the port stored NULL every time (same effect); moved inside |
| 178 | 0x26bfa0 | 100 | CSealCtrlAi::PlayAiSound(AI_SOUND) | seal_ai.cpp | MATCH | - | (s8) index; instance set or handle NULL exits; handle slot +0xc PlaySound(NULL, 255) into the instance slot |
| 179 | 0x26c010 | 32 | CSealCtrlAi::SetAiAccuracyAngle(float) | seal_ai.cpp | MATCH | - | tanf(angle) to aiAccuracyAngle |
| 180 | 0x26c030 | 60 | CSealCtrlAi::ReleaseDatabaseHandles() | seal_ai.cpp | MATCH | - | memset 8 of aiSoundHandle, of aiSoundInstance, CloseDiPool |
| 181 | 0x26c070 | 68 | CSealCtrlAi::AcquireDatabaseHandles() | seal_ai.cpp | MATCH | - | handles SND_STREAM_ABORT / STREAMING_BOUNDRY_WARNING, OpenDiPool, snooze_count 0, snooze_time -3f |
| 182 | 0x26c1a0 | 104 | sealai::get_stance(SEAL_STANCE) | seal_ai.cpp | MATCH | - | (s8) 0 stand, 1 crouch, 2 prone, 3 idle, else none |
| 183 | 0x26c210 | 116 | sealai::get_aiseq(unsigned int) | seal_ai.cpp | MATCH | - | 0-4 on_aware0..4, else on_awareX |
| 184 | 0x26c290 | 116 | sealai::get_state(char const*) | seal_ai.cpp | MATCH | - | NULL 0; i 0..29 strcasecmp(get_state(i), name) == 0 returns the byte; else 0 |
| 129 | 0x259230 | 12 | CSealCtrlAi::HasSniperRifle() | seal_ai.cpp | MATCH | - | tail CZKit::HasSniperRifle(m_entity + 0x520 m_kit) |
| 130 | 0x259240 | 176 | CSealCtrlAi::InGuardRegion() | seal_ai.cpp | MATCH | - | m_mapid / x / y of m_entity +0xe4 copied field by field into a local, GetRegionTypeContainer(6, &loc) != NULL |
| 131 | 0x259680 | 52 | CAiSRescued::SetExtractValve(CValve*) | seal_ai.cpp | MATCH | - | +0x30 m_valve; +0x4 flags &= ~(valve == NULL), then \|= (valve != NULL) |
| 132 | 0x25ac10 | 152 | CAiSPursue::GetStatus() const | seal_ai.cpp | MATCH | - | +0x14 m_substate < 8 (unsigned) into the eight names in the jump table's order, else "unknown" |
| 133 | 0x25acb0 | 80 | CAiSPursue::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_ai.cpp | MATCH | - | signal byte 4: +0x28 = -1f, +0x30 = 0; 0-3 nothing |
| 134 | 0x25aee0 | 84 | CAiSAnimate::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_ai.cpp | MATCH | - | signal 4: +0x8 0, +0x30 1f, sb +0x28 0 |
| 135 | 0x25d080 | 64 | is_throwtype(EQUIP_ITEM) | seal_ai.cpp | MATCH | - | (u8)item - 120 < 6 unsigned (the jump table all true) |
| 136 | 0x25d0c0 | 72 | CAiSGrenade::OnSignal(CAiState::SIGNAL, CSealCtrlAi*) | seal_ai.cpp | MATCH | - | signal 0: sb +0x2c m_gone 0 |
| 137 | 0x25fc90 | 160 | CSealCtrlAi::PlayAiSound(CHARACTER_SOUND) | seal_ai.cpp | MATCH | - | GetCharacter; bit 1 of +0x280 m_navyseal -> PlayAt(sound, m_id, NULL), else PlayAt(sound, m_id, slot +0xc GetPosW) |
| 138 | 0x25ff70 | 8 | CSealCtrlAi::OnActionButton() | seal_ai.cpp | MATCH | - | empty |
| 139 | 0x25ff80 | 8 | CSealCtrlAi::PerformProximityActions() | seal_ai.cpp | MATCH | - | empty; the ELF's v0 = 0 is read by no caller (the virtual caller in CSealCtrl ignores it) |
| 140 | 0x25ff90 | 8 | CSealCtrlAi::PerformReticleActions() | seal_ai.cpp | MATCH | - | as #139 |
| 141 | 0x25ffa0 | 8 | CSealCtrlAi::PerformCollisionActions() | seal_ai.cpp | MATCH | - | as #139 |
| 142 | 0x25ffb0 | 80 | CSealCtrlAi::GetAiAware() const | seal_ai.cpp | MATCH | - | GetAiAware(+0xc0 m_value) inlined in the ELF: first i < 5 with value < awareRangeMax[i] (c.lt.s), else 4 |
| 143 | 0x260000 | 76 | CSealCtrlAi::GetAiAware(float) | seal_ai.cpp | MATCH | - | the same loop on the argument |
| 144 | 0x260420 | 180 | CSealCtrlAi::SetAiAware(float, unsigned int) | seal_ai.cpp | MATCH | - | bit 0: v (+ goal +0xc4 with bit 2, v + goal), _saturate(v, 0f, 1f) (0x474f90/94 read: 0, 1) to +0xc0; bit 1: the same to +0xc4 |
| 145 | 0x260770 | 192 | CSealCtrlAi::SetDoReaction(bool, AI_REACTION const&, bool) | seal_ai.cpp | MATCH | - | bit 7 of +0x280 = navyseal (bit 1) ? 0 : on; set: the four weights copied to +0x2fc..; !exact: surrender * s, then none / rush / flee * (1 - s); v0 = the bit read by no caller |
| 146 | 0x260db0 | 120 | CSealCtrlAi::SetHoldFire(bool) | seal_ai.cpp | MATCH | - | +0x5bc m_valve[0]; was = value (lhu +0x4) != 0; the inlined CValve::Set(hold): sh, callbacks 1 / 2 on a change; was returned |
| 147 | 0x260e30 | 44 | CSealCtrlAi::GetValve(SEAL_VALVE) const | seal_ai.cpp | MATCH | - | (u8) < 4 -> +0x5bc[i], else NULL |
| 148 | 0x260e60 | 8 | CSealCtrlAi::SetRouteSearchLimit(unsigned int) | seal_ai.cpp | MATCH | - | sw +0x3f0 m_search_limit |
| 149 | 0x260e70 | 64 | CSealCtrlAi::SetRouteType(CAiPath::PATH_TYPE, float) | seal_ai.cpp | MATCH | - | SetPathType(+0x36c path, type) true -> +0x378 m_type_bias = bias |
| 150 | 0x261500 | 108 | CSealCtrlAi::ClearRoute() | seal_ai.cpp | MATCH | - | Debug("ClearRoute()...\n"), AbortPathPlan, Clear 0 -> 0; SetPathType(0) -> bias 1f; +0x3f0 0; 1 |
| 151 | 0x261570 | 112 | CSealCtrlAi::GetRouteFailed() const | seal_ai.cpp | MATCH | - | state (lbu +0x3e4) 2 / 1 / 3 -> 0; points (+0x3fc size) and state 4 -> 0; else +0x3e5 m_status (raw planner codes in both, 0 found) |
| 152 | 0x2615e0 | 116 | CSealCtrlAi::GetRouteComplete() const | seal_ai.cpp | MATCH | - | points and state 4 -> 0; state 2 / 1 / 3 -> 0; else 1 |
| 153 | 0x261d00 | 32 | CSealCtrlAi::SetStance(SEAL_STANCE) | seal_ai.cpp | MATCH | - | DoSetStance(stance), byte returned |
| 154 | 0x263970 | 112 | CSealCtrlAi::SetSprayTimer(float) | seal_ai.cpp | MATCH | - | GetCurItem() +0x20 (lbu) < 3 exits; SetWeaponState(1), SetAimDirR(&unit_nz, 0), +0x5b8 = time |
| 155 | 0x2639e0 | 80 | CSealCtrlAi::CanAttack(CEntity*) | seal_ai.cpp | MATCH | - | NULL 0 (the ELF has the test), bit 0 of +0xdd m_noshoot 0, lbu +0x10 m_type 3 -> 0, else 1 |
| 156 | 0x264050 | 124 | CSealCtrlAi::SetValve(SEAL_VALVE, unsigned int) | seal_ai.cpp | MATCH | - | (u8) < 4 -> +0x5bc[i]; NULL 0; the u16 value against the whole argument, sh, change 1 / 2 -> MakeCallbacks, returns change != 0 |
| 113 | 0x321ca0 | 184 | CZNetwork::zNetInitialize() | zNetDme.cpp | MATCH | - | default params, +0x8 10020, +0x4 256, +0xc GetKeyPair; NetInitialize; ErrorCode 0 -> +0xd m_network_init 1; +0xaf IP[0] 0, NetGetMyIpAddress; 4096 bytes from +0xe6 zeroed (the ELF's unrolled loop = memset); ErrorCode returned |
| 97 | 0x321340 | 132 | CZNetwork::zNetRemoteObjectUpdateCallback(int, int, int) | zNetDme.cpp | DEFECT-FIXED | C | NetGetObject(&obj, index), obj NULL / callback NULL tests, m_ObjectUpdateCallbackList[byte +0x0] (+0x4 owner, index, fields), m_ObjectFieldUpdate[index] (+0xe6) 1 agree; the ELF does not clear obj before the call (0x321348; zNetGetObject does), the port set it NULL; removed (the offline NetGetObject writes it) |
| 98 | 0x3213d0 | 108 | CZNetwork::zNetRegisterRemoteObjectCallback(int, ...) | zNetDme.cpp | MATCH | - | NetRegisterRemoteObjectCallback(type, create, zNetRemoteObjectUpdateCallback, destroy); +0x10e8[type] update, +0x1128[type] post |
| 99 | 0x321550 | 92 | CZNetwork::zNetLeaveAndDisconnect() | zNetDme.cpp | DEFECT-FIXED | C | the ELF clears +0xb m_bJoined after NetLeave returns (delay slot 0x32156c); the port cleared it before the call; now after. NetDisconnect when 0, +0xa 0, counts 12 / 2, +0x8, +0x0, +0x4, +0xe in that order agree |
| 100 | 0x3215b0 | 128 | CZNetwork::zNetJoin(void (*)(int, int), void (*)(int, int)) | zNetDme.cpp | MATCH | - | the 50-byte zero block copied, NetJoin(conn, &params, +0xc8, +0xcc, 2, 0, join, leave) a0-t3; 0 -> +0xb 1; error returned |
| 101 | 0x321630 | 136 | CZNetwork::zNetConnect(void (*)(int, int, char const*), void (*)(int, int, char const*)) | zNetDme.cpp | MATCH | - | default params, SetConnectionInfo(&params +0x4), +0xc0 / +0xc4 callbacks, +0xb8 / +0xbc 0; NetConnect; +0xd0 = out +0x8; ErrorCode 0 -> +0xa 1; +0xb 0; ErrorCode returned |
| 102 | 0x3216c0 | 40 | CZNetwork::zNetGetValidGameClientCount() | zNetDme.cpp | MATCH | - | count 0, NetGetValidClientCount(&count, +0xd0), count returned |
| 103 | 0x3216f0 | 8 | CZNetwork::zNetGetLocalTime() | zNetDme.cpp | MATCH | - | lw +0xe0 |
| 104 | 0x321700 | 8 | CZNetwork::zNetGetTime() | zNetDme.cpp | MATCH | - | lw +0xdc |
| 105 | 0x321710 | 64 | CZNetwork::zNetGetGameSessionMasterClientIndex() | zNetDme.cpp | MATCH | - | index -1, NetGetSessionMasterClientIndex(&index, theNetwork +0xd0), nonzero -> -1 |
| 106 | 0x321750 | 64 | CZNetwork::zNetGetMyGameClientIndex() | zNetDme.cpp | MATCH | - | as #105 with NetGetMyClientIndex |
| 107 | 0x321790 | 56 | CZNetwork::zNetGetClient(int, int) | zNetDme.cpp | MATCH | - | rec 0, NetGetClient(&rec, connection, client), nonzero -> NULL |
| 108 | 0x3217d0 | 68 | CZNetwork::zNetGetGameClient(int) | zNetDme.cpp | MATCH | - | the same on theNetwork +0xd0 |
| 109 | 0x321820 | 56 | CZNetwork::zNetGetObject(int) | zNetDme.cpp | MATCH | - | obj 0, NetGetObject, nonzero -> NULL |
| 110 | 0x321860 | 160 | CZNetwork::zNetCreateObject(int*, ...) | zNetDme.cpp | MATCH | - | NetCreateObject(index, own, life, a, b, c, d, data t3, name / e on the stack) in order; me -1, NetGetMyClientIndex (unused, ELF); error or *index >= 256 -> RecoverFromNetError(333); error returned |
| 111 | 0x321900 | 56 | CZNetwork::zNetClose() | zNetDme.cpp | MATCH | - | +0x9 m_bNetwork -> NetClose, +0xd 0, +0xa 0 |
| 112 | 0x3219e0 | 8 | CZNetwork::zNetTick() | zNetDme.cpp | MATCH | - | tail NetTick |
| 114 | 0x321d60 | 188 | CZNetwork::zNetInitEx() | zNetDme.cpp | MATCH | - | zNetInit, zNetLoadIRX 0 -> 0; zNetInitialize; strncpy(name, +0x4f, 64); Name2Address(cd, buf, 0, addr, name, 6000, 4) and Address2String(cd, buf, text, 64, addr) 0 -> strcpy back |
| 115 | 0x322300 | 24 | CZBroadcastSchedule::CZBroadcastSchedule(unsigned int, NetThresholdMethod, double) | zNetDme.cpp | MATCH | - | +0x0 interval, +0x4 method, sd +0x8 threshold, sb +0x10 0 |
| 76 | 0x1e8750 | 140 | _OutsideGuardBand(float*, float*, float[4]*, float[4]*, int) | fov.cpp | MATCH | - | the VU0 code in C: p = m[0] x + m[1] y + m[2] z + m[3] w (the ACC order), x / y against band min / max scaled by p.w, w against band w (vsub.xyw both ways), the sticky ZS / SS flags (0xc0) cleared per point (ctc2 0x1e8794); the first flagged point's flags, else 0 (the ELF's do-while needs count >= 1, every caller passes 8) |
| 77 | 0x1e87e0 | 112 | sceVu0ClipBBox(float[4]*, PNT4D*) | fov.cpp | MATCH | - | vclipw.xyz of the 8 corners: +x, -x, +y, -y, +z, -z against \|w\|, the clip register shifted 6 per corner (24 bits), AND from 63, OR, returned AND \| OR << 8; the ELF does not clear the clip register, so its bits 14+ can hold judgements from before the call; the port starts at 0 (TestFOV reads only 0x3f / 0x3f00) |
| 235 | 0x2f3730 | 156 | CBench::Reset() | zsys_bench.cpp | MATCH | - | dmaTime 0, drawTimeX[0..9] 0 (the ELF's unrolled 8 + 2), the six counters 0 in order |
| 6 | 0x17c540 | 64 | OrdersMenu::OnRecoCmd(int, int, int, int, char*) | orders.cpp | DEFECT-FIXED | B | the ELF keeps the result: recoResult[3] = a3, handle_reco_result 1, [0..2] = a0..a2, sprintf(&recoResult[4], "%s", t0) (0x17c540-0x17c578); the port was an empty stub; written. Masked: the port's recogniser never starts, so cbrecoResult never calls it |
| 2 | 0x176cf0 | 100 | OrdersMenu::PlayScrollSound() | orders.cpp | MATCH | - | +0x10 flag (lbu); GetSoundByName(m_upSound +0xb4 data); NULL -> flag 0; else slot +0x1c PlaySound(true, NULL, 255) |
| 3 | 0x1777c0 | 112 | OrdersMenu::Load(float, float, float, float) | orders.cpp | MATCH | - | fptosi of each to +0x68 / +0x6c / +0x70 / +0x74 |
| 4 | 0x17bf40 | 92 | C2DOrderItem::SetTrans(float) | orders.cpp | MATCH | - | m_text (+0xb4) and m_arrow (+0x1c0) SetTrans through their vtables (+0x20; GCC calls the members' known type), then C2DBitmap::SetTrans(this) |
| 5 | 0x17c4d0 | 104 | CMD_TABLE::~CMD_TABLE() | orders.cpp | MATCH | - | +0xd4 submenu -> __destroy_new_array(~CSubMenu) (delete[]), NULL; deleting flag -> delete this |
| 259 | 0x39e050 | 164 | CUIVarManager::~CUIVarManager() | zui_var.cpp | DEFECT-FIXED | C | the ELF's body clears the variable vector first (clear 0x39e080), then m_stab[2] (+0x2c, 28 each), ~CSaveModule (+0xc), the vector base; the port's empty body left the variables to the base dtor, after the string tables; clear() added |
| 257 | 0x39dc90 | 152 | CUIVarManager::Find(char const*) | zui_var.cpp | MATCH | - | 28-byte variables from data_ to data_ + size_: +0x18 longevity != 0 and strcasecmp(name, +0x8 name) == 0 returned, else NULL |
| 258 | 0x39dd30 | 180 | CUIVarManager::FindDormantVar(char const*, _zrdr*, UIVAR_LONGEVITY) | zui_var.cpp | DEFECT-FIXED | C | first longevity 0 slot: +0x8 = CreateString(name) on theUIVarManager's current table (the global's +0x28 / +0x2c at 0x39dd74, not this'), sb +0x18 longevity, reader -> Set; the port used this' table (the same object for the one caller); now the global's |
| 260 | 0x39e8d0 | 100 | CUIVariable::UpdateDependents() | zui_var.cpp | MATCH | - | each m_attached_items item (+0x14 data, +0x10 size) slot +0xc UpdateUIVar(this) |
| 273 | 0x304270 | 96 | CBufferIO::CBufferIO(CBufferIO const&) | util_bufio.cpp | MATCH | - | CFileIO copy, vtable, then +0x18 m_size, +0x14 m_bufsize, +0x10 m_buffer, +0x1c m_pos copied in that order (the ELF's layout; the port's names agree) |
| 269 | 0x304050 | 80 | CBufferIO::Close() | util_bufio.cpp | MATCH | - | m_buffer -> _free(buf, "util_bufio.cpp", 119); buffer, bufsize, pos, size 0; CFileIO::Close |
| 272 | 0x304250 | 28 | CBufferIO::Open(void*, unsigned int) | util_bufio.cpp | MATCH | - | size to +0x18 and +0x14, buf to +0x10, +0x1c = buffer; 1 |
| 271 | 0x304230 | 20 | CBufferIO::Release() | util_bufio.cpp | MATCH | - | bufsize, size, pos, buffer 0, tail CFileIO::Release |
| 274 | 0x3042d0 | 68 | CBufferIO::CBufferIO() | util_bufio.cpp | MATCH | - | CFileIO(), vtable, pos / buffer / bufsize / size 0 |
| 265 | 0x303e10 | 132 | CBufferIO::fread(int, void**) | util_bufio.cpp | MATCH | - | pos = slot +0x1c ftell; !(pos < size) -> 0; !(pos + n < size) -> n = size - pos; *buf = m_pos, m_pos += n; n (no buffer test in either) |
| 266 | 0x303ea0 | 168 | CBufferIO::fread(void*, int) | util_bufio.cpp | MATCH | - | no buffer -> CFileIO::fread; else as #265 with memcpy(buf, m_pos, n) |
| 264 | 0x303da0 | 112 | CBufferIO::freadchar(char*) | util_bufio.cpp | MATCH | - | no buffer -> CFileIO::fread(&arg, 1) (into the pointer argument, ELF); m_pos + 1 < buffer + size (unsigned) -> *buf = *m_pos++, 1; else 0 |
| 267 | 0x303f50 | 188 | CBufferIO::fseek(int, int) | util_bufio.cpp | MATCH | - | no buffer -> CFileIO::fseek; origin 2 size + offset, 1 offset + ftell (slot +0x1c), 0 offset, others 0 (movz); pos <= size and pos >= 0 -> m_pos = buffer + pos, pos; else -1 |
| 261 | 0x303ca0 | 48 | CBufferIO::fwrite(void const*, int) | util_bufio.cpp | MATCH | - | buffer -> -1, else CFileIO::fwrite |
| 262 | 0x303cd0 | 152 | CBufferIO::fwrite(char const*) | util_bufio.cpp | MATCH | - | buffer -> -1; length = buf ? strlen : 0; slot +0x2c fwrite(&length, 4), buf -> += fwrite(buf, length) |
| 263 | 0x303d70 | 40 | CBufferIO::fflush() | util_bufio.cpp | MATCH | - | no buffer -> CFileIO::fflush |
| 268 | 0x304010 | 52 | CBufferIO::ftell() const | util_bufio.cpp | MATCH | - | buffer -> m_pos - buffer, else CFileIO::ftell |
| 270 | 0x3041a0 | 136 | CBufferIO::Open(char const*, unsigned int) | util_bufio.cpp | MATCH | - | CFileIO::Open byte; IsOpen and mode & 1 and !(mode & 0x20) -> LoadBuffer byte; 0 -> slot +0xc Close; returned |
| 65 | 0x1c2370 | 72 | CZAnimMain::UnloadSIScript(_zanim_si_script*) | zanim_load.cpp | DEFECT-FIXED | C | the ELF frees with ("zanim_load.cpp", 80) and clears +0x10 script_data, +0xc script_data_size, +0x8 total_frame_count (0x1c2398-0x1c23a4); the port tagged ("anim_main.cpp", 0) and cleared only the data pointer; written as the ELF (the return 1 is read by no caller) |
| 61 | 0x1c01f0 | 72 | CZAnimMain::CloseZAR(CZAnimZAR*) | zanim_load.cpp | MATCH | - | CZAR::Close(archive) before the NULL test (ELF), then slot +0x8 deleting dtor; the ELF's 1 is read by none of its 4 callers |
| 62 | 0x1c0570 | 116 | CZAnimMain::AnimParseCmd(char const*, _zrdr*) | zanim_load.cpp | MATCH | - | GetCmdEntry(name, 0); entry and +0x8 parser -> parser(reader); a result gets sh +0x0 = lhu entry +0x4 |
| 63 | 0x1c05f0 | 188 | CZAnimMain::AnimLoadQuadAlignCmd(char const*, int) | zanim_load.cpp | MATCH | - | entry; _calloc(1, size, "zanim_load.cpp", 2071); data_size = bits 2-15 of +0x2 (size & 0x3fff, bits 0-1 kept), data_type = +0x4; SeqAppendCmd; _free(.., 2077); the ELF's 0 is not read |
| 64 | 0x1c2200 | 112 | CZAnimMain::Load(char const*, char const*) | zanim_load.cpp | MATCH | - | !m_LoadFromZAR: setname -> +0x34 = GetAnimSet(GetAnimSetIndex(set, 1)), +0x38 / +0x3c 0; AnimLoadZRDFile(NULL, path); 1 |
| 121 | 0x22bba0 | 140 | zdb::CRenderMap::~CRenderMap() | node_shadow.cpp | MATCH | - | vtable; DeleteLightMap(CWorld::m_world, +0x188 m_lightmap); +0x2d0 m_gsPacket -> _free(.., "node_shadow.cpp", 248); NULL; ~CLightMap base; deleting flag |
| 128 | 0x23e4e0 | 68 | zrdr_findfile(char const*, char const*) | zrdr_main.cpp | DEFECT-FIXED | C | dir -> "%s/%s" (dir, name) into _buffer$711, returned, else name; the ELF calls sprintf (0x23e500), the port bounded it with snprintf (a guard the ELF lacks); now sprintf |
| 122 | 0x23d6a0 | 68 | zrdr_finduint(_zrdr const*, char const*, unsigned int*, int) | zrdr_main.cpp | MATCH | - | findtag_startidx(reader, name, 1), zrdr_toINT(tag, output, startidx) |
| 123 | 0x23dab0 | 104 | zrdr_findstring(_zrdr const*, char const*) | zrdr_main.cpp | MATCH | - | tag NULL -> NULL; type byte 3 -> +0x4; type 4 and array[1] (+0x8) type 3 -> its +0xc; else NULL |
| 124 | 0x23db20 | 112 | zrdr_nexttag(_zrdr const*, char const*, _zrdr*) | zrdr_main.cpp | MATCH | - | NULL or type != 4 -> NULL; _zrdr_nexttag(reader, name, strlen(name), other) |
| 125 | 0x23dc90 | 8 | zrdr_findtag(_zrdr const*, char const*) | zrdr_main.cpp | MATCH | - | tail findtag_startidx(.., 1) |
| 126 | 0x23df40 | 68 | _zrdr::~_zrdr() | zrdr_main.cpp | MATCH | - | nothing of its own, deleting flag |
| 127 | 0x23e140 | 68 | _zrdr::_zrdr(_zrdr*, CSTable*) | zrdr_main.cpp | DEFECT-FIXED | C | the ELF clears only isclone (bit 8 of the first word, 0x23e158-0x23e16c) before Clone; the port also zeroed type, packed, unused and length (Clone writes type / length, and packed for an array); now isclone only. Not the default ctor, whose kept deviation (small-b #68) stays |
| 83 | 0x218df0 | 176 | zdb::CClutter::GetMatrix() | grid_clutter.cpp | MATCH | - | bit 1 of +0x4c clear -> this (m_matrix); else the manager's +0x10 matrix (CGrid by value in the ELF, the port's pointer: a known layout deviation) unit, AnimRotation(+0x10)->Mul(Rotation(+0), &q), ToMatrix; identity scale (CMatrix() is the unit matrix) with [i][i] = +0x2c; MulMatrix(m, scale, m); [3][0..2] = +0x20..0x28 |
| 78 | 0x217680 | 176 | zdb::CClutterAnimManager::UnRegisterEffector(void const*) | grid_clutter.cpp | MATCH | - | first effector (list +0x5c) whose +0x0 owner matches: delete, erase, return |
| 79 | 0x217810 | 40 | zdb::CClutterAnimManager::Tick(float, void*) | grid_clutter.cpp | MATCH | - | m_world grid manager (+0x698 by value in the ELF) l_Tick(dt, data); 0 |
| 80 | 0x218110 | 172 | zdb::CClutterAnimManager::ClearEffectors() | grid_clutter.cpp | MATCH | - | every effector deleted, then erase(begin, end) = clear |
| 81 | 0x218560 | 148 | zdb::CClutterAnimManager::CClutterAnimManager() | grid_clutter.cpp | MATCH | - | +0x10 unit matrix, the two lists (+0x50, +0x5c), AddTask("CClutterAnimManager", Tick, 0.95f, NULL), m_ClutterAnims erased (clear) |
| 82 | 0x218980 | 144 | zdb::CClutterAnim::~CClutterAnim() | grid_clutter.cpp | MATCH | - | +0x0 clutter -> AnimRotation (+0x10) MakeYXZRot(0, 0, 0); +0x4 node -> its deleting dtor (vtable at node +0x60, slot +0x8); +0x4 NULL |
| 84 | 0x218ea0 | 32 | zdb::CClutter::GetTranslate() | grid_clutter.cpp | MATCH | - | bit 1 of +0x4c -> this + 0x20, else this + 0x30 |
| 85 | 0x219040 | 124 | zdb::CClutterList::Free() | grid_clutter.cpp | MATCH | - | every pointer from data_ to data_ + size deleted, size_ 0 (clear) |
| 237 | 0x2f4520 | 132 | _strdup(char const*, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | C | strlen + 1, DIntr, malloc, strcpy, EIntr, zVid_Assert(size == 0 \|\| p, 0x800000ff, file, 660) agree; the ELF's file is "zsys_memory.cpp" (0x4588a0), the port's __FILE__ the tree path; now the ELF's string (as in #238-#242, #244) |
| 238 | 0x2f45b0 | 116 | _calloc(unsigned int, unsigned int, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | C | count * size, DIntr / malloc / EIntr, memset after, assert line 641 agree; file string as #237 |
| 239 | 0x2f4630 | 108 | _realloc(void*, unsigned int, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | C | DIntr / realloc / EIntr, assert line 619 agree; file string as #237 |
| 240 | 0x2f46a0 | 108 | _memalign(unsigned int, unsigned int, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | C | DIntr / memalign(alignment, size) / EIntr, assert line 597 agree; file string as #237 |
| 241 | 0x2f4710 | 100 | _malloc(unsigned int, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | C | DIntr / malloc / EIntr, assert line 579 agree; file string as #237 |
| 242 | 0x2f4780 | 100 | _new_vec(unsigned int, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | C | as _malloc, assert line 561; file string as #237 |
| 244 | 0x2f4830 | 100 | _new(unsigned int, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | C | as _malloc, assert line 524; file string as #237 |
| 246 | 0x2f48e0 | 52 | _free(void*, char const*, int) | zsys_memory.cpp | DEFECT-FIXED | B | the ELF frees with interrupts off (DIntr 0x2f48ec, free, EIntr 0x2f48fc) as _delete does; the port called free alone, open to a thread switch inside the allocator (the sound and network threads allocate too); masked on the disc so far. DIntr / EIntr added |
| 236 | 0x2f4490 | 132 | zsys_MemoryReport() | zsys_memory.cpp | MATCH | - | __HeapSizePS2 = 0x1f7e000 - image end, the three printf lines (start, size) in order; _textStart / _dataStart / .vubss end as ps2sdk's _ftext / _fdata / _end (recorded port equivalents) |
| 243 | 0x2f47f0 | 64 | _delete_vec(void*, char const*, int) | zsys_memory.cpp | MATCH | - | NULL test (the ELF has it), DIntr / free / EIntr |
| 245 | 0x2f48a0 | 52 | _delete(void*, char const*, int) | zsys_memory.cpp | MATCH | - | DIntr / free / EIntr, no NULL test in either |
| 247 | 0x2f4920 | 92 | zsys_FullAllocAndFree() | zsys_memory.cpp | MATCH | - | from 4096 by 4096 while malloc succeeds (freed) and size < 0x2000001 (unsigned); __HeapSize = size - 16, reread, returned |
| 8 | 0x3bd1d0 | 72 | CLetterBox::AddLetterbox() | hud_letterbox.cpp | MATCH | - | sb +0x120 m_slidedir 1, then m_bitmap[0] (+0x20) and [1] (+0xa0) slot +0x1c On (GCC calls the members' known type) |
| 7 | 0x3bd1c0 | 12 | CLetterBox::RemoveLetterbox() | hud_letterbox.cpp | MATCH | - | sb +0x120 = 2 SLIDE_OUT |
| 9 | 0x3bd3c0 | 80 | CLetterBox::Draw(zdb::CCamera*) | hud_letterbox.cpp | MATCH | - | m_bitmap[0] / [1] slot +0xc Draw(camera) in order |
| 16 | 0x3dca10 | 108 | CZPlayerMapItem::InitStaticItems() | hud_playermapitem.cpp | MATCH | - | m_ablestring color +0x50 / +0x54 / +0x58 = 20, 80, 20, Off; the same for m_bravostring |
| 13 | 0x3dc6c0 | 160 | CZPlayerMapItem::Draw(zdb::CCamera*) | hud_playermapitem.cpp | MATCH | - | slot +0xc Draw(camera) (the packet names Tick) on m_blip (+0x10), m_cone (+0x200), m_clippedcone[0] / [1] (+0x448 / +0x474), m_clippedblip[0] / [1] (+0x3f0 / +0x41c) in that order |
| 10 | 0x3db990 | 44 | CZPlayerMapItem::MissionEndCleanup() | hud_playermapitem.cpp | MATCH | - | ClearAndWipe on m_ablestring, then m_bravostring |
| 11 | 0x3dc640 | 88 | CZPlayerMapItem::DrawAlphaBravo(zdb::CCamera*) | hud_playermapitem.cpp | MATCH | - | C2DString::Draw(camera) able, bravo; Off able, bravo |
| 12 | 0x3dc6a0 | 20 | CZPlayerMapItem::PostDraw(zdb::CCamera*) | hud_playermapitem.cpp | MATCH | - | tail slot +0x18 of m_namestring (+0x4cc): Off (vt.py 0x472cb0) |
| 14 | 0x3dc760 | 8 | CZPlayerMapItem::Clip(CZNewHudMap*) | hud_playermapitem.cpp | MATCH | - | empty |
| 15 | 0x3dc9d0 | 52 | CZPlayerMapItem::UnInitStaticItems() | hud_playermapitem.cpp | MATCH | - | SetString(NULL) on bravo, then able |
| 276 | 0x308ed0 | 68 | CVideo::Fade(float, unsigned char, unsigned char, unsigned char) | zvid_draw.cpp | MATCH | - | zvid +0x260..0x262 = r, g, b; +0x263 = fptoui(255 * level) byte (the scan's 2^31 constant is GCC's float-to-unsigned) |
| 275 | 0x308a00 | 192 | CVideo::WriteGsMemory(unsigned int, uint16*, unsigned int) | zvid_draw.cpp | MATCH | - | DIntr, DmaSync(zSys +0x8); do: SetDefLoadImage(&li, (s16)gsaddr, 4, 0, 0, 0, 256, 256), FlushCache(0), ExecLoadImage, DmaSync; size -= 0x40000, buf += 0x40000 bytes, gsaddr += 1024 while size; EIntr |
| 277 | 0x308f20 | 28 | CVideo::MaxFrameRate(int) | zvid_draw.cpp | MATCH | - | 60 -> -1; old m_maxFrameRate returned, the new one stored |
| 278 | 0x309180 | 116 | CTTY::~CTTY() | zvid_draw.cpp | MATCH | - | +0xc40 & 0xdfffffff nonzero -> _free(.., "zvid_draw.cpp", 88); +0xc40 0; deleting flag |
| 279 | 0x309200 | 172 | CTTY::CTTY() | zvid_draw.cpp | MATCH | - | 40 lines of 78 strcpy "", +0xc30 0, +0xc34 39, +0xc3c 1, +0xc40 = _memalign(64, 0x27000, "zvid_draw.cpp", 79) \| 0x20000000, memset of it |
| 87 | 0x2ce6c0 | 32 | CRemoteCtrl::Tick(float) | remote_control.cpp | DEFECT-FIXED | C | the ELF calls CSealCtrl::ClearGoal(0) directly (jal 0x2ce6c8), the port through the vtable (no override, same target); now qualified; returns 1 |
| 86 | 0x2ce210 | 8 | CRemoteCtrl::PostTick(float) | remote_control.cpp | MATCH | - | empty; the ELF's v0 = 1 is read by no caller |
| 88 | 0x2ce6e0 | 84 | CRemoteCtrl::AllowCommand(CZSealBody*, FT_COMMAND, void*) | remote_control.cpp | MATCH | - | command byte 5 -> AllowCommandHOLDPOS, 4 -> AllowCommandFOLLOW (byte), else 0 |
| 89 | 0x2ce740 | 72 | CRemoteCtrl::OnCommand(CZSealBody*, FT_COMMAND, void*, bool) | remote_control.cpp | MATCH | - | 5 or 4 -> NetSendAiOrders(commander +0x4 id, m_entity id, command byte, point) |
| 90 | 0x2ce790 | 196 | CRemoteCtrl::GetRemoteAiFollowMaster() | remote_control.cpp | MATCH | - | m_entity +0xc nonzero -> low byte of slot +0x6c GetAiNetState; != 9 -> NULL; GetEntityById(bits 8-23 of a second GetAiNetState); m_type (+0x10) 2 -> it, else NULL |
| 91 | 0x2ce860 | 80 | CRemoteCtrl::GetRemoteAiState() | remote_control.cpp | MATCH | - | m_entity +0xc 0 -> 0, else the low byte of GetAiNetState |
| 248 | 0x2f87d0 | 144 | zdb::CTexList::Free() | ztex_main.cpp | MATCH | - | every handle CTexHandle::Destroy'd and its slot set 0, size_ 0 (storage kept) |
| 249 | 0x2f8a30 | 104 | zdb::CTexList::GetHandle(zdb::CTexture*) | ztex_main.cpp | MATCH | - | first handle whose +0xc m_texture == texture (the ELF copies the argument through $f0), else NULL |
| 250 | 0x2f8be0 | 68 | zdb::CTexture::CopyTextureSelect(_word128*) | ztex_main.cpp | MATCH | - | qwc = lhu +0x30, memcpy(dst, +0x34, qwc * 16), dst + qwc |
| 251 | 0x2f8db0 | 180 | zdb::CTexture::~CTexture() | ztex_main.cpp | MATCH | - | +0x14 name not NULL / UNNAMED_TEX -> _free(.., 305); UNNAMED_TEX stored twice (ELF); +0x68 loadimage -> _free(.., 243), 0; the +0x5c vector member; deleting flag |
| 252 | 0x2f8e70 | 20 | zdb::CTexture::Release_HTEX() | ztex_main.cpp | MATCH | - | lhu +0x2c - 1 stored and returned as u16 |
| 253 | 0x2f90b0 | 40 | zdb::CTexture::Init() | ztex_main.cpp | MATCH | - | m_baseAddress = zVid +0x48, m_endAddress = +0x4c, m_startAddress = base + 512 |
| 39 | 0x1cd5c0 | 84 | CZAnim::SequenceRunning(char const*) | zanim_anim.cpp | MATCH | - | ZAnim m_CurSeq 0, m_CurAnim saved and set to this, CZAnimMain::SequenceRunning(name) byte, m_CurAnim restored, m_CurSeq 0 |
| 40 | 0x1cd620 | 84 | CZAnim::SequenceExists(char const*) | zanim_anim.cpp | MATCH | - | as #39 with SequenceExists |
| 41 | 0x1cd680 | 80 | CZAnim::ResumeSequence(char const*) | zanim_anim.cpp | MATCH | - | as #39 with ResumeSequence |
| 42 | 0x1cd6d0 | 80 | CZAnim::PauseSequence(char const*) | zanim_anim.cpp | MATCH | - | as #39 with PauseSequence |
| 43 | 0x1cd720 | 80 | CZAnim::StopSequence(char const*) | zanim_anim.cpp | MATCH | - | as #39 with StopSequence |
| 44 | 0x1cd770 | 80 | CZAnim::ActivateSequence(char const*) | zanim_anim.cpp | MATCH | - | as #39 with ActivateSequence |
| 21 | 0x1c8f00 | 196 | CZAnim::ExecuteSpecialSequence(int) | zanim_anim.cpp | DEFECT-FIXED | C | offset <= 0 returns 1 at once in the ELF (bgtz 0x1c8f18, before ZAnim's m_CurAnim / m_CurSeq are read); the port saved and stored them back there too (same values); now the early return. The run (m_CurSeq = data + offset, m_CurAnim = this, SeqSetState(2), SeqTick(1f), !SeqRunning, SeqSetState(1), restore) agrees |
| 22 | 0x1c9f10 | 144 | CZAnim::GetNodeRefName(int) | zanim_anim.cpp | MATCH | - | index < 0 / >= m_node_ref_count (bits 11-18 of +0x2c, unsigned) -> NULL; name_index bits 8-18 of the 8-byte ref; GetName(GetAnimSet(bits 3-10), name) on the +0x1c table |
| 23 | 0x1ca9f0 | 84 | CZAnim::AddValve(char const*) | zanim_anim.cpp | MATCH | - | +0x1c table AddName(GetAnimSet(m_animset_index), name) |
| 24 | 0x1caa50 | 84 | CZAnim::AddName(char const*) | zanim_anim.cpp | MATCH | - | as #23 |
| 25 | 0x1caab0 | 84 | CZAnim::GetName(int) | zanim_anim.cpp | MATCH | - | GetName(GetAnimSet(set), index) |
| 26 | 0x1cab10 | 84 | CZAnim::GetName() | zanim_anim.cpp | MATCH | - | GetName(GetAnimSet(set), lbu +0x0 m_name_index) |
| 27 | 0x1cab70 | 100 | CZAnim::Name(char const*) | zanim_anim.cpp | MATCH | - | NULL -> sb +0x0 0; else sb AddName(GetAnimSet(set), name) |
| 28 | 0x1cabe0 | 56 | CZAnim::ClearValvePtrs() | zanim_anim.cpp | MATCH | - | i < lbu +0x32 count: +0x40 list[i] (8 bytes) +0x4 valve = 0 |
| 29 | 0x1cac20 | 120 | CZAnim::ClearNodePtrs() | zanim_anim.cpp | MATCH | - | each ref but the root (+0x1) of a clone (bit 1 of +0x5) and the created_here ones (bit 23 of the ref word): +0x4 node 0 |
| 30 | 0x1cb430 | 96 | CZAnim::GetNodeRef(int) | zanim_anim.cpp | MATCH | - | 0 and 250 -> NULL; &list[index], node NULL -> GetNode(index, 0); the ref |
| 31 | 0x1cb8f0 | 8 | CZAnim::Priority(float) | zanim_anim.cpp | MATCH | - | swc1 +0xc |
| 32 | 0x1cbf60 | 128 | CZAnim::DeleteParticleSources() | zanim_anim.cpp | MATCH | - | each +0x44 source (8 bytes, +0x4) deleted (~Source(1)) and cleared |
| 33 | 0x1cbfe0 | 152 | CZAnim::StopParticleSources() | zanim_anim.cpp | MATCH | - | a source with +0x0 active or +0x128 shutting off -> Reset |
| 34 | 0x1cc5c0 | 72 | CZAnim::GetRootNode() | zanim_anim.cpp | MATCH | - | +0x34 instance node, else root index 0 -> NULL, else list[root] +0x4 |
| 35 | 0x1cc8f0 | 196 | CZAnim::Pause() | zanim_anim.cpp | MATCH | - | the inlined Running (StateRunning(m_state), then the particle sources): running -> sb +0x2 1; the ELF's 1 / 0 is read by none of its 5 callers |
| 36 | 0x1cc9c0 | 168 | CZAnim::Running() | zanim_anim.cpp | MATCH | - | StateRunning(lbu +0x3) byte, else a source active / shutting off -> 1, else 0 |
| 37 | 0x1cd0a0 | 184 | CZAnim::RestartClones() | zanim_anim.cpp | MATCH | - | activation (bits 0-1 of +0x4) 3 exits; this and +0x5c siblings: ClearNodePtrs, GetNodes, ClearValvePtrs; state 1 / 5: activation 1 Activate(NULL), 3 OnWeaponHitInit |
| 38 | 0x1cd160 | 176 | CZAnim::Start() | zanim_anim.cpp | MATCH | - | ClearNodePtrs, GetNodes, the valve pointers cleared inline, then as #37 |
| 45 | 0x1ce370 | 112 | CZAnimArgPnt3D::Copy() | zanim_anim.cpp | MATCH | - | new(24), the inlined ctor: base vtable, type 0, +0x8 0, vtable, type = lb +0x4, the point +0xc..+0x14 |
| 46 | 0x1ce3e0 | 68 | CZAnimArgPnt3D::CZAnimArgPnt3D(CZAnimArg::TYPE, CPnt3D const*) | zanim_anim.cpp | MATCH | - | vtables, type 0 then type, +0x8 0, x / y / z to +0xc..+0x14 |
| 47 | 0x1ce4a0 | 104 | CZAnimArgValve::Copy() | zanim_anim.cpp | MATCH | - | new(16): ctor (type 4, +0x8 0), +0xc valve, then type = lb +0x4; the ELF stores the type even when new returned NULL (0x1ce4f0, unreachable with the port's new) |
| 48 | 0x1ce510 | 96 | CZAnimArgNode::Copy() | zanim_anim.cpp | MATCH | - | new(16), ctor with (lb +0x4 type, +0xc node) |
| 49 | 0x1ce570 | 48 | CZAnimArgNode::CZAnimArgNode(CZAnimArg::TYPE, zdb::CNode*) | zanim_anim.cpp | MATCH | - | vtables, type 0 then type, +0x8 0, +0xc node |
| 50 | 0x1ce5a0 | 132 | CZAnimArgCharP::~CZAnimArgCharP() | zanim_anim.cpp | MATCH | - | +0xc value -> _free(.., "zanim_anim.cpp", 681), 0; base vtable; deleting flag |
| 51 | 0x1ce630 | 152 | CZAnimArgCharP::Copy() | zanim_anim.cpp | MATCH | - | new(16): vtables, type 0, +0x8 0, +0xc = _strdup(value, "zanim_anim.cpp", 669), type = lb +0x4 |
| 52 | 0x1ce6d0 | 116 | CZAnim::ActivateArg(int, ...) | zanim_anim.cpp | MATCH | - | count 0 -> Activate(NULL); else ActivateArgV(the first vararg slot, sp + 0x30 of the 8-byte spills); the port passes GCC's n32 va_list pointer to the same 8-byte slots (recorded) |
| 53 | 0x1cf590 | 8 | CZAnimMain::NetworkPacketSize(void*) | zanim_anim.cpp | MATCH | - | lw +0x0 of the packet |
| 54 | 0x1cf5a0 | 40 | CZAnim::GetHealth() | zanim_anim.cpp | MATCH | - | +0x28 NULL -> 0f, else its +0x4 |
| 55 | 0x1cf5d0 | 80 | CZAnim::HealthInit() | zanim_anim.cpp | MATCH | - | +0x28 set -> nothing; new(24), memset 0, byte +0x0 = root index (+0x1) |
| 56 | 0x1cf620 | 64 | CZAnimEx::Reset(float*, float*) | zanim_anim.cpp | MATCH | - | +0x14 = *armor or +0x18; +0x1c = *health or +0x20 |
| 57 | 0x1cfab0 | 116 | CZAnimExVector::Reset() | zanim_anim.cpp | MATCH | - | each Reset(NULL, NULL) |
| 58 | 0x1cfb30 | 124 | CZAnimExVector::Free() | zanim_anim.cpp | MATCH | - | each ~CZAnimEx(1), size_ 0 |
| 59 | 0x1cfbb0 | 112 | CZAnimExVector::Add(CZAnimEx*) | zanim_anim.cpp | MATCH | - | size == capacity -> reserve(size + 15); insert at the end |
| 60 | 0x1cfc20 | 112 | CZAnimEx::~CZAnimEx() | zanim_anim.cpp | MATCH | - | +0x8 node -> SetNodeEx(NULL, 1); deleting flag |
| 116 | 0x22b260 | 100 | zdb::CProjectedMap_Object::~CProjectedMap_Object() | node_projectedmap.cpp | DEFECT-FIXED | C | the ELF has no body of its own: only the vector_pod base dtor (0x22b28c) and the deleting flag; the port swapped the vector with an empty one first (the base frees the storage anyway); removed |
| 117 | 0x22b2d0 | 60 | zdb::CProjectedMap_Object::CProjectedMap_Object() | node_projectedmap.cpp | MATCH | - | the empty vector (+0x4 size, +0x8 data 0), +0xc m_bandMax 256 |
| 254 | 0x2f98b0 | 180 | zdb::CTexPalette::Read(zdb::CSaveLoad&) | ztex_palette.cpp | MATCH | - | Fetch("par", this, 8) byte; ok: +0x1c = _malloc(96, .., 111), +0x14 = _memalign(128, m_size (lhu +0x4), .., 112), Fetch("buf", buf, size); +0x10 m_id = +0x0 m_gsaddr; FlushCache(0); ok returned |
| 255 | 0x2f9970 | 160 | zdb::CTexPalette::~CTexPalette() | ztex_palette.cpp | MATCH | - | name (line 64), loadimage (66), buffer (67) freed when set and cleared in that order; deleting flag |
| 256 | 0x2f9a10 | 156 | zdb::CTexPalette::CTexPalette(char const*) | ztex_palette.cpp | MATCH | - | +0xc = _strdup(name, .., 44), +0x1c 0, +0x0 = m_palId, +0x18 0, sh +0x4 0, +0x14 0; byte +0x7: bit 1 m_dynamic 0, bits 2-7 0, bit 0 kept; +0x8 0; m_palId++ |
| 68 | 0x1dc820 | 188 | CSequence::LinearWeight() | zanim_sequence.cpp | MATCH | - | total = down + (up + hold); !(t < total) -> total, stored; t <= 0 -> 0; !(t <= hold + down) -> (total - t) / up; t < down -> t / down, else 1 (the medium-anim-b fix, compares as the ELF) |
| 66 | 0x1dc6a0 | 8 | PushAnim(CActiveAnimList*, ACTIVE_ANIM*, float) | zanim_sequence.cpp | MATCH | - | +0x4 m_wt = wt, tail RTList::Add |
| 67 | 0x1dc6b0 | 92 | RenormAnims(CActiveAnimList*, float) | zanim_sequence.cpp | MATCH | - | Begin / Next, each +0x4 = scale * wt |
| 69 | 0x1dc8e0 | 44 | CSequence::Tick(float) | zanim_sequence.cpp | MATCH | - | currT - dT stored; < 0 -> 0; reread returned |
| 70 | 0x1dc910 | 20 | CSequence::Clear() | zanim_sequence.cpp | MATCH | - | the four times 0 |
| 71 | 0x1dc930 | 28 | CSequence::Start(float, float, float) | zanim_sequence.cpp | DEFECT-FIXED | C | up / hold / down stored; the ELF sums down + (up + hold) (add.s 0x1dc930, 0x1dc934), the port (down + up) + hold; now in the ELF's order |
| 72 | 0x1dc950 | 76 | PointAlongLine(CPnt3D const&, CPnt3D const&, float, CPnt3D&) | zanim_sequence.cpp | MATCH | - | per axis from + t (to - from) |
| 73 | 0x1dc9a0 | 108 | LineIntersectPlane(float, CPnt3D const&, CPnt3D const&, CPnt3D const&) | zanim_sequence.cpp | MATCH | - | nb = (nx dx + ny dy) + nz dz, na = (nx ax + ny ay) + nz az (the adda / madd order), (-d - na) / nb |
| 74 | 0x1dca10 | 48 | PlaneConstant(CPnt3D const&, CPnt3D const&) | zanim_sequence.cpp | MATCH | - | -((x x + y y) + z z) |
| 75 | 0x1dd020 | 92 | quadW(float) | zanim_sequence.cpp | MATCH | - | w <= 0.5 -> (2w) w; else d = 2(w - 1), 1 - (0.5 d) d (the factor 2 / 0.5 swaps are exact) |
| 92 | 0x333a90 | 8 | CMPEG::SetDisplayHeight(int) | zmpeg.cpp | MATCH | - | sw _Display_Height |
| 93 | 0x333aa0 | 8 | CMPEG::SetMaxHeight(int) | zmpeg.cpp | MATCH | - | sw _Max_Height |
| 94 | 0x333bf0 | 52 | CMPEG::Done() | zmpeg.cpp | MATCH | - | BlockingPSSPlayback -> 1, else testdonePss(p_mp) byte |
| 95 | 0x333d50 | 92 | CMPEG::IdleTick() | zmpeg.cpp | MATCH | - | p_mp NULL exits; while T0 (0x10000000) % 525 (divu) < 480: fillBuff(p_mp, 0) |
| 96 | 0x333db0 | 48 | CMPEG::Tick(int) | zmpeg.cpp | MATCH | - | !BlockingPSSPlayback -> tickPss(p_mp, &rsrcs, fbp << 5) |
| 187 | 0x2e24d0 | 32 | CSealCtrlSquirm::Tick(float) | seal_squirm.cpp | MATCH | - | CZSealState::UpdateLocalSeal(m_entity), 1 |
| 185 | 0x2e24b0 | 8 | CSealCtrlSquirm::OnActionButton() | seal_squirm.cpp | MATCH | - | empty |
| 186 | 0x2e24c0 | 8 | CSealCtrlSquirm::PostMortemPreTick(float) | seal_squirm.cpp | MATCH | - | empty; the ELF's v0 = 1 is read by no caller |
| 188 | 0x2e2c00 | 8 | CSealCtrlSquirm::ResetToInitialState() | seal_squirm.cpp | MATCH | - | empty |
| 189 | 0x2e2c10 | 8 | CSealCtrlSquirm::OnDeath() | seal_squirm.cpp | MATCH | - | empty |
| 190 | 0x2e2c20 | 8 | CSealCtrlSquirm::OnSetHealth(float, float) | seal_squirm.cpp | MATCH | - | empty |
| 191 | 0x2e2c30 | 8 | CSealCtrlSquirm::OnStunDamage(STUN_TYPE, float, CPnt3D const*) | seal_squirm.cpp | MATCH | - | empty |
| 192 | 0x2e2c40 | 8 | CSealCtrlSquirm::OnWeaponHit(zdb::IntersectStruct*, CZProjectile*) | seal_squirm.cpp | MATCH | - | empty |
| 193 | 0x2e2da0 | 96 | CSealCtrlSquirm::~CSealCtrlSquirm() | seal_squirm.cpp | MATCH | - | vtable, ~CSealCtrl, deleting flag |
| 280 | 0x31fa80 | 16 | CZAmmo::GetAmmoId(char const*) | zwep_ammo.cpp | MATCH | - | tail m_ammolist.GetAmmoId(name) |
| 281 | 0x31fa90 | 16 | CZAmmo::GetAmmo(EQUIP_AMMO) | zwep_ammo.cpp | MATCH | - | tail m_ammolist.GetAmmo(id) |
| 282 | 0x31faa0 | 8 | CZAmmo::GetExplosionRadius() | zwep_ammo.cpp | MATCH | - | lwc1 +0x18 |
| 283 | 0x31fab0 | 8 | CZAmmo::GetExplosionDamage() | zwep_ammo.cpp | MATCH | - | lwc1 +0x14 |
| 284 | 0x31fac0 | 8 | CZAmmo::GetArmorPierce() | zwep_ammo.cpp | MATCH | - | lwc1 +0x10 |
| 285 | 0x31fad0 | 8 | CZAmmo::GetImpactDamage() | zwep_ammo.cpp | MATCH | - | lwc1 +0x8 |
| 286 | 0x31fae0 | 8 | CZAmmo::GetName() | zwep_ammo.cpp | MATCH | - | lw +0x0 |
| 287 | 0x31faf0 | 8 | CZAmmo::SetExplosionRadius(float) | zwep_ammo.cpp | MATCH | - | swc1 +0x18 |
| 288 | 0x31fb00 | 8 | CZAmmo::SetExplosionDamage(float) | zwep_ammo.cpp | MATCH | - | swc1 +0x14 |
| 289 | 0x31fb10 | 8 | CZAmmo::SetArmorPierce(float) | zwep_ammo.cpp | MATCH | - | swc1 +0x10 |
| 290 | 0x31fb20 | 8 | CZAmmo::SetStun(float) | zwep_ammo.cpp | MATCH | - | swc1 +0xc |
| 291 | 0x31fb30 | 8 | CZAmmo::SetImpactDamage(float) | zwep_ammo.cpp | MATCH | - | swc1 +0x8 |
| 292 | 0x31fb40 | 52 | CZAmmo::SetHitAnim(char const*) | zwep_ammo.cpp | MATCH | - | +0x1c = ZAnim.GetAnim(name, NULL) |
| 293 | 0x31fb80 | 92 | CZAmmo::SetDescription(char*) | zwep_ammo.cpp | MATCH | - | +0x4 set -> _free(.., 40); +0x4 = _strdup(.., 42) |
| 294 | 0x31fbe0 | 96 | CZAmmo::SetName(char*) | zwep_ammo.cpp | MATCH | - | +0x0 set -> _free(.., 33); 0; _strdup(.., 34) |
| 295 | 0x31fc40 | 132 | CZAmmo::~CZAmmo() | zwep_ammo.cpp | MATCH | - | name (27) and description (28) freed when set and cleared; deleting flag |
| 296 | 0x31fcd0 | 28 | CZAmmo::CZAmmo() | zwep_ammo.cpp | MATCH | - | +0x0, +0x4, +0x1c 0; sb +0x20 m_ID 255 |
| 18 | 0x1a1b10 | 196 | CAiVisMap::GetMark(CAiMapLoc const&) const | ai_vismap.cpp | MATCH | - | ox / oy = loc x / y - the region's (+0x1c, bit fields 6-18 / 19-31); negative or not below +0x20 dx / +0x22 dy (unsigned) -> 0; index = ox + oy dx; (m_bits (+0x50)[index >> 4] & 3 << 2(index & 15)) >> that |
| 19 | 0x1a1be0 | 92 | CAiVisMap::~CAiVisMap() | ai_vismap.cpp | MATCH | - | +0x4c 0, +0x0 0, delete[] +0x50, 0; deleting flag |
| 20 | 0x1a1ed0 | 56 | CAiVisMap::ReleaseDynamicVisMap(CAiVisMap*) | ai_vismap.cpp | MATCH | - | dynamicVisMap.remove_if(equal_to(vm)) = remove(vm) |
| 1 | 0x305e40 | 24 | CBeachBall::Uninit() | beachball.cpp | MATCH | - | m_init (lbu) set -> sb 0 |
| 17 | 0x1a94f0 | 160 | CAiLog::CAiLog(bool) | ai_log.cpp | MATCH | - | vector ctor, +0xc / +0x10 / +0x18 0, CFileIO at +0x1c, +0xc = _malloc(8192, "ai_log.cpp", 22), global -> m_log = this, +0x18 \|= 0x80 |
| 118 | 0x22a900 | 32 | zdb::CSaveLoad::LoadAssetLib(zdb::CWorld*, zdb::CAssetLib*, int) | node_saveload.cpp | MATCH | - | LoadAssetLib_PS2(world, library, type) byte |
| 119 | 0x22b1c0 | 96 | zdb::CSaveLoad::~CSaveLoad() | node_saveload.cpp | MATCH | - | m_zfile (+0x4) Close, then its dtor; deleting flag |
| 120 | 0x22b220 | 60 | zdb::CSaveLoad::CSaveLoad() | node_saveload.cpp | MATCH | - | +0x0 m_world 0, CZAR(NULL, NULL) at +0x4, sb +0xa8 0 |
