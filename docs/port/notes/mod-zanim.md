# mod-zanim notes (2026-11-13, socom-port-mod-zanim): completing the zAnim module

Port worker for `src/gamez/zAnim/*` (owned in place). Scratch: `build/port/boot-mod-zanim/`
(NOTES.md, mine.txt, shared.txt + edits/, hook_zanim.cpp, diag1.txt, tools/, helper folders h-*).
Disc ZARs read from the user's image into the scratch `disc/` only.

## Result
- `survey.py gamez/zAnim`: 120 empty fences (83 KB) -> 24 (23.1 KB); the 13 placeholder command
  ticks (`return true; /* port: stub - not written */`, which the survey counts as written) are
  all written. Left: see "Not written".
- m8 fake-pad run z6 (scratch hook_zanim.cpp: SELECT skips the mission cameras, TRIANGLE closes the
  tactical map the skip opens, then the player walks forward 20 s; pad_start.txt skips the intro movie
  with CROSS; tree = HEAD 3f054bb6 + my files + the shared edits): in the mission from 76 s to the end
  of the run at 248 s (~170 s), the AI turning aware, no STOP, heap use 22164884..22188820 from 112 s on. Traced (diag1.txt, first 3 calls each): CAMERA
  begin/tick (the briefing cameras), PAUSE_ANIMATION, LIGHT (anim lights, light maps),
  CZAnim::MakeClones / FindClones (CZAnimSet::Start), CZAnimSetSave::Add, StopLights.
- Exit / restart round trip z7 (port/test-hooks/win, -DSOCOM_HOOK_EXITPATHS): mission 1 pause ABORT ->
  debrief -> X replay -> mission 2 pause REPLAY -> mission 3 pause ABORT -> debrief TRIANGLE -> menus
  (157 s), no STOP; CZAnimSet::GarbageCollect / Reset and CZAnimSetSave::Reset ran at the first exit;
  heap at each mission start 21922084 / 21810628 / ~22.1 MB, at the menus 17439316.
  (port/test-hooks/exit stalls after the pause press in this tree too - the missionwin note's issue.)
- Default build zdef (default.sh, no hook, no fake pad): links; boots to the main menu (menu frame 300 at
  33 s) and its attract screen; no STOP. (A first boot of it ended at 17 s with PCSX2 itself exiting,
  not the game; the repeat ran clean.)

## Survey (before coding)
Command use was counted over every anim's compiled Seq_Data in the disc's zanim ZARs (m8 mzanim,
czanim, uizanim, extzanim, ldzanim, mpzanim; a scratch script cmdscan.py in my scratch folder). The text (.rdr) loader
and every zAnimLoad* parser never run on retail data (`m_LoadFromZAR`: anims come compiled), so
they are "written, untested". Data-reached groups (written first): CAMERA (m8: 5 commands),
LIGHT (62), OBJECT_MOTION_FROM_TO acceleration (1331 FROM_TO commands), OBJECT_MOTION_SI_SCRIPT
(m8: 5, with 5 SoftImage scripts), FIRE_WEAPON (m8: 5), ADD/DELETE_CHILD (22/22), PAUSE (3) /
INVALIDATE (17) ANIMATION, the managers (CZAnimSet::Start clones, mission exit / restart
GarbageCollect / Reset / node-state save), GetFractionalRotations (every soldier tick). Unused
anywhere: NODE_ACTIVE, NODE_RENDERED, RANGE_TEST, RANDOM_WEIGHT, ANIM_HEALTH, ANIM_LOD,
OBJECT_BLENDMODE, TIMER, RESUME_ANIMATION, UI_APP_COMMAND.

## Written (ELF addresses)
- Ticks (zanim_cmd_tick.cpp): zAnimCameraBegin 0x1be9b0, zAnimCameraTick 0x1be5e0, zAnimLightTick
  0x1bd7c0, zAnimObjectBlendModeTick 0x1bd590, CZAnimFromToAcc::Tick 0x1baf10 / ComputeRunTime
  0x1bb100 (returns f32) and the accelerated part of zAnimObjectMotionFromToBegin 0x1ba630,
  zAnimMultiObjectMotionScriptBegin 0x1b9b10 / Tick 0x1b9a30, zAnimObjectMotionScriptTick
  0x1b9b80, apply_script_frame 0x1b9d90 (returns f32), zAnimObjectAddChildTick 0x1b98b0 /
  DeleteChildTick 0x1b9830, zAnimInvalidateAnimTick 0x1b80c0, ResumeAnimTick 0x1b8140,
  PauseAnimTick 0x1b81d0, zAnimFireWeaponTick 0x1b7c90, zAnimTimerTick 0x1bfd70, zAnimDebugTick
  0x1b7c80 (empty in the ELF), CZAnimExpression::NewCmd 0x1b90e0.
- Managers: CZAnim GarbageCollect 0x1cb900, Reset 0x1cd210, GetRootNode 0x1cc5c0, MakeClones
  0x1ccf60, RestartClones 0x1cd0a0, FindClones 0x1ccc70, Refresh 0x1cd3c0, StopLights 0x1cbd40,
  CreateInstanceNode's copy_instance path 0x1cad4c; CZAnimSet GarbageCollect 0x1c5e70, Reset
  0x1c6480, SaveNodeStates 0x1c6300, SIScript(int) 0x1c7ba0, GetAnimIndex 0x1c7db0, Unload's
  CZAnimEx list / node-state part 0x1c5f60; CZAnimSetSave Reset 0x1c5580, Add 0x1c5730;
  CZAnimMain GetAnimIndex 0x1c42b0 (bool), GetAnim 0x1c44d0, GetNetworkPacket 0x1c5280,
  FreeNetworkPacketBuffer 0x1c5240, NetworkReceive 0x1cf490, NetworkPacketSize 0x1cf590, Unload
  0x1c23c0 (now as the ELF: anim sets unloaded, command sets freed); AnimSet Close 0x2cd2d0 /
  CloseAll 0x2cd580; CAnimAuxData::Get 0x2cc7c0 (static, returns the entry);
  GetFractionalRotations 0x1dcde0; Unload_MissionReader 0x1d5e50; CMenuStack::KillPopUp 0x1d5c80 and
  ~CMenuStack 0x1d65d0.
- Text loader (zanim_load.cpp, anim_main.cpp, zanim_anim.cpp): AnimParseCmd, AnimLoadQuadAlignCmd,
  AnimLoadSeq, AnimLoadAnim, AnimLoadNameZRDR, AnimLoadAnimList, AnimLoadZRDFile, UnloadCmdSet,
  ZAnimWildcardApply/Next/Init, GetNodeSearchScope, SeqAppendCmd, SeqSetName, NewSeq, NewAnim,
  OpenFile/AddPath (empty in the ELF), LoadSaveNodeStates, LoadNodeNames, GetNodeRefName,
  AddValve, the sequence-offset stack, zAnimCmdAddData; the old provisional AnimParseExpression,
  zAnimLoadWhile and zAnimLoad_If/ElseIf/Else/EndIf rewritten from the ELF.
- Parsers (zanim_cmd_parse.cpp): CAMERA, LIGHT, OBJECT_BLENDMODE (+ CZAnimBlendMode GetBlendMode /
  GetBlendModes / GetBlendValueSequence / GetBlendSequenceValue, all static), OBJECT_MOTION (+
  CZAnimObjectMotion::GetTranslation), OBJECT_MOTION_FROM_TO, SOUND, FIRE_WEAPON, MESSAGE, TIMER,
  DESTRUCTION_SOURCE, ADD/DELETE_CHILD, CALL/STOP_SEQUENCE, CALL/STOP/PAUSE/RESUME/INVALIDATE
  _ANIMATION, ANIM_LOD, ANIM_HEALTH, FAIL, RANDOM_WEIGHT, RANGE_TEST, NODE_RENDERED, NODE_ACTIVE,
  BREAK, END_WHILE, WAIT, LOOP, OBJECT_OPACITY_FROM_TO, OBJECT_ROTATE/TRANSLATE/ACTIVE_STATE.
- Records (zanim.h; no DWARF, names the port's): _zanim_cmd_camera (+ _zanim_camera_param),
  _zanim_cmd_light (+ _zanim_light_range), _zanim_cmd_blendmode, _zanim_blend_fix,
  _zanim_cmd_si_script, _zanim_object_motion_script, zanim_script_frame_header,
  _zanim_cmd_child, _zanim_cmd_timer, _zanim_cmd_fire_weapon, _zanim_cmd_message (moved from the
  tick file), _zanim_cmd_destructor, _zanim_cmd_loop, CZAnimFromToAcc's 56-byte layout,
  _zanim_node_save + CZAnimSetSave with the DWARF member names (m_translationList,
  m_rotationList, m_parentList). zanim_cmd_val is a union (DWARF); m_max_anim_copies is u32.

## Shared edit files (other modules; applied to test trees through shared.txt)
- `edits/zrdr_nexttag.txt` (zReader/zrdr.h): declaration of zrdr_flat_nexttag (AnimLoadAnimList).
- `edits/light_node_main.rep.txt` (zNode/node_main.cpp): zdb::CLight::SetActive 0x224b00 and
  UpdateBBox 0x226a20 - the LIGHT tick STOPped on the UpdateBBox stub (run z1) without it.
- `edits/acquire_projectile.rep.txt` (zWeapon/zwep_projectilelist.cpp): CZProjectileList::
  AcquireProjectile 0x31a4e0 (a non-void stub FIRE_WEAPON reaches).

## ELF quirks kept
- CZAnimFromToAcc::ComputeRunTime gets the stored "to", without the relative (0x1) offset.
- apply_script_frame counts a frame it stops before; GetFractionalRotations' acos of z / the
  flat length near the vertical; CZAnimSetSave::Reset deletes from the current parent unchecked
  and keeps the saved states; CZAnim::GarbageCollect keeps the node reference list; the Reset of
  an anim with a weapon-hit extension and no health passes pointers into a NULL health record;
  CZAnimMain::GetAnimIndex asks a NULL set when the index is out of range; FIRE_WEAPON scales the
  direction by 1 + the muzzle velocity; Unload_MissionReader builds a path it never uses.
- Text path: see the helper reports in the scratch (AnimParseExpression never steps over a
  non-string, non-list element; LoadSaveNodeStates' INPUT/ROOT node refs 250/249; WildcardApply
  reads past its digit table with more '*' than digits; LIGHT's LOCAL_LIGHT writes the node ref
  unchecked; several parsers read a tag's first element without a type check).

## Port deviations
- apply_script_frame, CZAnimFromToAcc::ComputeRunTime, GetAnimIndex, CAnimAuxData::Get,
  GetBlendMode(s) got their ELF return types (the skeleton declared void).
- Several text-path functions return a value in the ELF that no caller reads and stay void
  (UnloadCmdSet, AnimLoadAnim, AnimLoadNameZRDR, AnimLoadAnimList, AnimLoadZRDFile,
  AnimLoadQuadAlignCmd, NewAnim, CZAnimSet::GarbageCollect, CZAnim::GarbageCollect).
- Inline code the ELF has (zAnimCmdAddData's realloc/memcpy, CZAnim::Anim(int), GetRootNode,
  CBlendable::Clear) is called instead; stack slots the ELF leaves unset are zeroed in the
  OBJECT_MOTION and blend-mode parsers.

## Not written / next
- Parsers PARTICLE_SOURCE 0x1b5e30, DEBUG 0x1aaef0, OBJECT_MOTION_SI_SCRIPT 0x1abcf0 +
  ForObject 0x1ac460; CZAnimSet::SIScript(name, ...) 0x1c6720, load_si_script 0x1c6900,
  _store_frame_data 0x1c78f0 (text path only; disassembly in the scratch h-pd1/).
- CZAnimArgList::Parse/AddNetworkPacketArgs 0x1cd960 / 0x1cdcf0 and CZAnim::Activate's network
  packet part (network play only).
- zanim_menu.cpp: 15 empty UI stubs (UI_COMMAND / UI_APP_COMMAND parsers, CMenuStack::PopUpDialog,
  OnListSavedGames, AuxNetCensorText, UICheckJoinMP, UILobbyEventHandler, the UINet* network-configuration functions) and 114 placeholder
  UI_COMMAND functions (`return true`), mostly network / lobby / clan / memory card; 37 front-end
  ones listed in the scratch h-pd2/SET2.txt, the 99 network ones in u2_set.txt.
- Untested in the demo data: FIRE_WEAPON, SI scripts, ADD/DELETE_CHILD and INVALIDATE ran in no
  traced run (their anims are triggered later in m8 than the passive runs got); every text-path
  function; the network functions.

# Part 2 (2026-11-13, socom-port-mod-zanim2): front-end UI commands, SI-script loaders, parsers, online commands

Scratch: `build/port/boot-mod-zanim2/` (NOTES.md, mine.txt, edits/trace400.txt, pad_fe1/pad_fe2.txt,
hook_zanim2.cpp = the first part's m8 hook, asm dumps, tools/). Tree = HEAD 920f54c4 + mine.txt.

## Result
- `survey.py gamez/zAnim`: 24 empty fences (23104 B) -> 14 (11436 B). Placeholder bodies
  (`return true; /* port: stub - not written */`): 114 (15224 B) -> 67 (9000 B), all online
  (network / lobby / clan / network configuration); partial bodies 5 -> 4.
- Runs: fe3 (fake pad pad_fe2.txt, HEAD 8f2e84ef + these files): main menu -> OPTIONS -> audio,
  video (CheckVideoMode), controller, presets (CROSS: SetControllerConfig "Default") and back each
  time -> main menu (StoreOptions again) -> attract, no STOP. m2 (first part's m8 hook, the intro
  movie skipped with CROSS, cameras with SELECT; HEAD 920f54c4): in the mission 72..257 s, no STOP,
  heap 22.20 MB flat from 160 s; a 600-command UI trace shows no online or memory-card command on
  the m8 path. x3 (port/test-hooks/win, -DSOCOM_HOOK_EXITPATHS): abort -> debrief -> replay,
  replay, abort -> debrief -> menus at 158 s and the menu / attract cycle after, no STOP and no
  menu hang. def2 (default.sh, HEAD 8f2e84ef): boots to the main menu.

## Written (ELF addresses)
- Front end (zanim_menu.cpp): PopUpDialog 0x1d5f20 / UIPopUpDialog 0x1d5a20, UIKillPopUp 0x1d4720,
  UISetControllerConfig 0x1d69c0, UISetStickPreset 0x1d3310, UIStoreOptions 0x1d3470,
  UIInitializeOptions 0x1d2fd0, UICheckVideoMode 0x1d38a0, UISwitchProgressiveVideo 0x1d37c0,
  UISetDefaultMenuScreen 0x1d2310, UITestUIVar 0x1d2120, OnGetTextFromUser 0x1d7090,
  OnSetSkbPurpose 0x1d6af0, UISwitchMenu's PREVIOUS_SCREEN back sound 0x1d57b0, the
  UI_COMMAND / UI_APP_COMMAND parsers 0x1d04b0 / 0x1d0330 (text path); the memory-card commands
  (_LoadSavedGame 0x1d68c0, _SaveSavedGame 0x1d6790, OnListSavedGames 0x1d6d70,
  UIIsMemCardFormatted, UIFormatMemCard, UIDoesSlotHaveGame, UIGetNumSavedGames,
  UIIsSpaceForSaveGameFile, UIMC_ChDir / MkDir / ChSlot / Exists / CreateIconFiles, UILoadConfig,
  UISaveConfig) with their argument, valve and UI-variable parts; each CMemCard call answers as
  with no card (needs zUtil: CMemCard - util_memcard.cpp is stubs and theMemCard a placeholder;
  the first part's UIIsMemCardInserted already reports no card).
- zUI (zui_skb.cpp): UiGetTextFromUser 0x3a71c0, UiSetSkbPurpose 0x3a7150 (g_strSkbPurpose,
  g_strSkbUiVar, g_arrSkbs, g_pSkbScaleUpSound typed; CSoftKeyboard::m_name +0x0).
- SI scripts (zanim_set.cpp, text path): CZAnimSet::SIScript(name, ...) 0x1c6720, load_si_script
  0x1c6900 (frames, spline coefficients, constant-block removal), _store_frame_data 0x1c78f0;
  parsers OBJECT_MOTION_SI_SCRIPT 0x1abcf0 and ...ForObject 0x1ac460 (returns the record);
  DEBUG 0x1aaef0 (record _zanim_cmd_debug). _zanim_object_motion_script: +0x20 rotate_offset,
  +0x2c scale_offset.
- Online UI commands (written, untested: nothing online runs): UISysLoadIRX, UIPasswordSecurity,
  UITransferLeadership, UIDeclineInvitation, UIAcceptInvitation, UIUpdateClanStats,
  UICanLadderPressDown / Up, UILadderDown / Up, UISetPlayerDescription, UIForceMediusStatusReport,
  UINetCensorText + AuxNetCensorText, UIRebootIOP, UIIsNetwork, UIIsSessionMaster, UIAbortLoad,
  UIClearGameState, UILobbyBailout, UIUnInitNetwork, UIGetAcctInfo, UILobbyEventHandler. The m8
  path (trace of 600 UI commands) and the options screens run none of the online or
  memory-card commands.

## Outside the module (small in-place edits)
- zSeal/seal_control.cpp: SetRumbleOn 0x284360 / IsRumbleOn 0x284350 (UIStoreOptions /
  UIInitializeOptions).
- port/compat/libvu0.c + include/libvu0.h: sceVu0RotMatrixX 0x152688 / sceVu0RotMatrixZ 0x1525e0
  (load_si_script; the X/Z twins of the existing RotMatrixY).

## ELF quirks kept
- UIStoreOptions / UIInitializeOptions disagree: INVERT_PITCH_CONTROLLER set gives hackPitchFactor
  -1 but is set back from a factor of 1; STEREO_CONTROLLER set gives playback mode 0 but is set
  back from a mode other than 0. UILoadConfig: AUTOMESSAGES "ON" turns the messages off.
- UISwitchProgressiveVideo (and UIStoreOptions' video_mode) test the current mode for NTSC and
  the requested one for DTV; _SaveSavedGame prints the clock's BCD bytes as decimals;
  UISysLoadIRX copies its argument and loads nothing; UIStoreOptions makes STICK_SWAP_CONTROLLER
  and never reads it.
- load_si_script: the curve's multiply-by-zero terms (t0 = 0); a frame header whose blocks are
  all removed stays; an "Object" entry missing a value reads tokens to the end of the file;
  CZAnimMain::OpenFile is empty in the ELF, so no SI script or OBJECT_MOTION_SI_SCRIPT ALL_NAMES
  file is ever read. OMSI's NAMES branch takes SCRIPT_OBJECT_NAME from the NAMES list, not the
  item; OMSI makes an unused CFileIO (port: not made).

## Port deviations
- zAnimUIMenuTick tests the command id against the table size before UICommandTable[id] (the ELF
  reads past the table for the 2D objects' own command types, 0x95 on, when the node has no 2D
  object - the options screens do this).
- filename$2674 is at file scope (every memory-card command writes it; the ELF's static of
  OnListSavedGames); the commands' INPUT_STRING read, the inline valve set and UI-variable set
  are file-local helpers (UiArgument, UiSetValve, UiSetRealVar, UiApplyStickPreset); DEBUG's
  string add and OMSI's object add are file-local helpers; load_si_script and
  _store_frame_data stay void (no caller reads the ELF's return); load_si_script zeroes the
  values the ELF leaves unset.

## Not written / next
- needs zUI: CPopUpDialog (Load 0x389770, Draw 0x3897f0, Tick 0x389ae0, HandlePad 0x389b10,
  TickZAnimCmd 0x387020, GetZAnimCmdType 0x386f80) and CWrappedText (SetString 0x391630, Draw
  0x391110, dtor 0x391480, LoadSpec 0x3919a0): CMenuStack::GetPopUp makes no pop-up, so the
  menus have no POPUP node and PopUpDialog / KillPopUp show and hide nothing. needs zUI: the soft
  keyboard (CreateSoftKeyboard 0x3a7940, PrepSkbsForDisplay 0x3a7720, ShowSkb 0x3a36f0):
  GetTextInput finds no keyboard and sets skb_done at once.
- needs zUtil: CMemCard (all of util_memcard.cpp) for the memory-card commands; CRdrEditor's
  port body (zReader) is a non-working placeholder, so OnListSavedGames' list stays empty.
- needs zMath: CQuat::Div 0x220eb0 / Ln 0x220750 (stubs) for _store_frame_data's rotations.
- zAnimLoadParticleSource 0x1b5e30 (6424 B, text path; the scratch asm_particle.txt has it).
- CZAnimArgList::ParseNetworkPacketArgs 0x1cd960 / AddNetworkPacketArgs 0x1cdcf0 and
  CZAnim::Activate's network part; OnCloseAndSwitch / OnReplayMission's network parts.
- 67 online UI commands from UINetGetIFCInfo 0x1d0f90 upward (address order), and the empty
  UINet* / UICheckJoinMP stubs; several need zNetwork return types first (IsTeamGame,
  OnCorrectClanTeam, HasClanInvitations and CNetCnf::Close / Uninit are void in znet.h).
- Step 4 not done: FIRE_WEAPON, the SI scripts and ADD / DELETE_CHILD still ran in no traced run.

# Part 3 (2026-11-13, socom-port-mod-zanim3): pop-ups, PARTICLE_SOURCE, network arguments, online commands

Scratch: `build/port/boot-mod-zanim3/` (NOTES.md, mine.txt, shared.txt + edits/, hook_popup.cpp,
pad_pop.txt, hook_m8.cpp = the second part's m8 hook, on2-on4.rep.txt, asm dumps, and two scratch\nscripts listing the pop-up records per anim and an anim's commands with their UI names).

## Result
- `survey.py gamez/zAnim`: 12 empty fences (10456 B) -> 8 (2540 B, all network-configuration
  `UINet*`). Placeholder bodies (`return true; /* port: stub - not written */`): 67 -> 14.
- Pop-ups on screen (run pop1: fake pad pad_pop.txt plus the scratch hook_popup.cpp, which raises
  the options menu's MEMCARD_ERROR event and later runs its save_and_leave anim): "Error loading
  data" (CROSS closes it); "Would you like to save to the memory card (PS2)?" with Yes / No
  (RIGHT / LEFT move the active button, CROSS on Yes sets the AreYouSure valve to 1); the protected
  "Saving preferences" one; "Can not save. No memory card (PS2) ..." with Continue; CROSS ->
  PREVIOUS_SCREEN -> main menu. Then main menu -> OPTIONS -> audio, video, controller, presets and
  back each time -> main menu -> attract; no STOP. The demo's own menu flow raises none of these by
  itself (the disc's options screens leave through check_then_save_and_leave, which shows none; the
  pop-ups sit in memory-card, video-mode (DTV) and online anims), hence the hook. m8 has no pop-up
  record in its zanim data.
- m8a (the second part's m8 hook, common/pad_start.txt; tree = HEAD 193e49fd + these files + the
  zNetwork edit files): in the mission from 57 s to the end at 255 s, no STOP, heap 22.229-22.248 MB
  from 93 s. x1 (port/test-hooks/win, -DSOCOM_HOOK_EXITPATHS): abort -> debrief -> X replay ->
  mission 2 -> mission 3 -> abort -> debrief TRIANGLE -> main menu loaded at 158 s, no STOP
  (PCSX2 itself closed at about 160 s, as in the first part's note). def1 (default.sh): boots to
  the main menu.

## Written (ELF addresses)
- zUI (zui_2d.cpp): CWrappedText SetString 0x391630 (one CRenderableString per word in the object's
  own C2D list), Draw 0x391110 (lines of m_width, m_spacing apart; a height scissors and scrolls),
  ~CWrappedText 0x391480, GetSpacing 0x389380; CPopUpDialog Load 0x389770, Draw 0x3897f0, Tick
  0x389ae0, HandlePad 0x389b10, TickZAnimCmd 0x387020, GetZAnimCmdType 0x386f80. Layouts in zui.h:
  CWrappedText +0xac width / +0xb0 spacing / +0xb4 height; CPopUpDialog (2544 bytes, member names
  from the command's reader keys): relocator +0xa0, text +0xa4, font +0x15c, offsets +0x160,
  size +0x168, child +0x18c, valve +0x190, selection +0x194, YES / NO buttons +0x1a0 / +0x5c0 with
  their positions and text offsets, PROTECTED +0x9e0. The compiled command (208 bytes) is the
  port's `_zui_popup_cmd` (zui_2d.cpp, names from ParseZAnimCmd 0x387c00's keys).
- zui.cpp: CGameMenu::LoadFromDesign's pop-up part 0x382a00 (font, Load, hidden POPUP foreplane
  node). zanim_menu.cpp: CMenuStack::GetPopUp 0x1d6080 (typed CPopUpDialog*), ~CPopUpDialog 0x1d4090.
- zanim_cmd_parse.cpp: zAnimLoadParticleSource 0x1b5e30 (text path; written, untested).
- zanim_anim.cpp: CZAnimArgList::ParseNetworkPacketArgs 0x1cd960, AddNetworkPacketArgs 0x1cdcf0,
  CZAnim::Activate's network part 0x1cf390 (network play only; written, untested).
- Online UI commands (zanim_menu.cpp; written, untested, nothing online runs): UIIsTeamGame,
  UINotOnCorrectClanTeam, UIHasClanInvitations, UIClanHasInvitations, UIGetLadderInfo ..
  UICoopMissionExists (0x1d2280-0x1d2cf0), UISetFilters 0x1d3c70 .. UIIsTerrorist 0x1d4700,
  UIGetMediusAnnouncements 0x1d4780 .. UILobbyRegister 0x1d5090, UICheckJoinMP 0x1d5310,
  UIJoinGameServer 0x1d53a0, UIDisconnectFromGameServer 0x1d5420, UIConnectToGameServer 0x1d5490.

## Shared edit files (not merged into the checkout: znet.h and zNetMedius.cpp were held by another worker)
- `edits/znet_h.txt` (zNetwork/znet.h): CZOnlineLobby return types from the callers' use of v0:
  bool HasClanInvitations, IsTeamGame, OnCorrectClanTeam, ClanHasInvitations, IsMemberOfClan,
  GetClan, SendClanMessage, InvitePlayerToClan, RevokeInvite, IsLeaderOfClan, JoinRoom,
  GameIsPasswordProtected, JoinGame, CreateGame, RefreshGameList / RoomList / RoomPlayerList /
  GamePlayerList, Login, Register; int GetDMEJoinedCount.
- `edits/znetmedius.txt` (zNetwork/zNetMedius.cpp): the matching definitions; the ELF bodies of
  HasClanInvitations 0x32ad40, IsTeamGame 0x3254e0, ClanHasInvitations 0x323ac0, IsMemberOfClan
  0x322ae0; the others stay stubs returning a constant.

## ELF quirks kept
- CWrappedText::Draw draws nothing on the first call after SetString (it only counts the lines)
  and places each next word where the drawn one ended (MakePacket's end position).
- CPopUpDialog: CROSS and TRIANGLE "clear" the text with an empty string, which SetString ignores;
  TickZAnimCmd handles any command type, leaves the result untouched, drops (does not destroy) an
  earlier valve; the button states get no glow or pulse although the parser reads them;
  GetZAnimCmdType answers GetUICommandType(NULL) for any unknown name.
- PARTICLE_SOURCE: NAME / ACTIVE_STATE read their first element unchecked; the ROTATED rotate rate
  is appended twice; a missing single ACCELERATION clears the velocity pair; BOUNDARY_BOX takes a
  density only from a tag that is itself a real; MODEL looks the model up and drops the result.
- AddNetworkPacketArgs treats a type-9 argument as an argument list; UISendChatText strlens a
  string variable without text; UIStoreSOP does not check the variables for NULL; UIJoinMPRoom /
  UIJoinMPGame strcmp the name unchecked.

## Port deviations
- The CPopUpDialog and CWrappedText inline constructors zero the members the ELF leaves unset;
  the CPopUpDialog declaration moved below CWrappedText in zui.h (it holds one by value).
- The particle parser's streak and rotate buffers start zeroed (the ELF appends stack contents).
- File-local helpers for code the ELF inlines: PopUpSetValve, PopUpSetButton (zui_2d.cpp),
  ParticleVelocity / ParticleRotateRate / ParticleTableCount (zanim_cmd_parse.cpp),
  AppendNetworkPacket (zanim_anim.cpp), UiCommandObject (zanim_menu.cpp).

## Not written / next
- The network-configuration commands: UINetCnf* (Init, Uninit, Open, Close, Count, CurrCombo,
  SelectCombo, GetDispNames, DeleteAll), UINet* (GetIFCInfo, GetDevInfo, UpdateIFCVars, GetDevIndex,
  SaveCombo, SaveIfc, SaveDev, AddCombo, AddIfc, AddDev, GetInterfaceList): they need CNetCnf's
  declarations made static with their ELF return types (Close, NumCombos, NumIFC, GetIFC, GetDev,
  GetDefaultCombo, SelectCombo, Uninit, DeleteAll(Tick), GetComboData, SaveCombo(Tick), ...) and the
  file-local HCnf / pIFCInfo / pDevInfo typed (int placeholders now).
- UILobbyLogout (reads CZOnlineLobby's private state byte +0x60) and UIInitNetwork (stores
  UILobbyEventHandler(const char *, const char *) where znet.h declares m_event_handler as
  (const char *, int)).
- CWrappedText::LoadSpec 0x3919a0 / CWrapSpec::CreateDisplayObj: CWrapSpec is a CTextSpec in the
  ELF (caption, scale, font, colour, then width / spacing / height at +0x24); the port's derives
  from CDlgObjSpec. CPopUpDialog::ParseZAnimCmd 0x387c00 (text path).
- Step 5 not done: FIRE_WEAPON, the SI scripts and ADD / DELETE_CHILD still ran in no traced run.
