# boot-voicecams notes (2026-11-13, socom-port-voicecams): team-mate speech, HQ voice, mission cams (m8)

Untracked scratch. Changed files: `mine.txt` (= copy.txt for tree.sh); shared-file hunks: `shared.txt` + edits/.
Tools copied from boot-orders (paths -> boot-voicecams / tree-voicecams / voicecams-default). New: fulldis.sh
(whole-ELF objdump to the session scratchpad for call-site scans).

## State / next step
- DONE (a) and (b). v2.log (vc2 = bv.sh vc2 pad_v1.txt; hook_vc.cpp drives the pad from the game state):
  - m8 start: PlayMPEG skipped -> HUD_TRIGGER_MISSION_CAM m8bs: letterbox + "X TO ABORT", AI suspended, the camera
    flies the three 7 s views (21.0 s), HQ SND_VM08_12 streams at once and SND_VM08_01 after it; then m8tut1
    ("*ELIMINATE GUARDS SILENTLY / *USE TERRAIN FOR STEALTH", drop arrow) 13 s; AI back, HUD back.
  - orders (command menu): FIRE AT WILL (the ELF says nothing for it), HOLD POSITION -> Bailey answers (CHRSND_YES:
    SND_VOC_A87L streamed, 121.7 s), FOLLOW (the unit's formation passes it quiet: no answer, as in the ELF).
  - callouts: DiMone "tango sighted" SND_VOC_211B (+ clock line), tango down SND_VOC_151 (125 s); mission 2 Bailey
    tango down SND_VOC_144E. v1.log also: Hutchins sighted (VOC_271E/266D), DiMone tango down (VOC_152A, VOC_149).
  - mission 1 to t 125 s, no STOP, heap 21.83 -> 21.98 MB steady; pause ABORT -> debrief -> TRIANGLE -> menus ->
    PLAY GAME -> mission 2: cams again, SELECT skips m8bs and m8tut1, stable to t 57 s (22.04 MB).
  - Audio confirmed by trace only: each line's 989snd VAG stream started (snd_PlayVAGStreamByLoc_CB) and ended
    (the headset went playing -> idle when 989snd reported the handle done); nobody listened.
  - def.log / def.png (voicecams-default, default.sh): main menu.
  Screens: build/port/screenshots/31-voice-missioncams/.
- Next (not done): CAMERA_PARAMS (CmdBeginParams 0x1e61c0, CmdTickParams 0x1e5570 3148 B, CmdParseParams): the
  cameras keep the game's FOV/clip/fog; CSealCtrlAi::OnDeath 0x2699b0 (death lines 58/59, unit notify);
  CSealUnit::Notify 0x2d57f0 (+ Distribute/PrivateNotify): EnemyCallout calls it (empty).
## Survey (from the ELF and the disc readers)
- All team-mate and HQ lines are streamed VAGs that also have a headset name: sounds.rdr VOICE set entries
  `('SND_VOC_482A' 'ST' ('N1' ('VOC_482A') 'HN' ('VOC_482A')))`, HQ `SND_VM08_12` / `SND_VM08_01`, tutorial
  `SND_TC8_0n` likewise. character.rdr maps each SEAL's CHRSND_* line to a group (bailey CHRSND_TANGO_DOWN ->
  SNDGROUP_BAILEY_TANGO_DOWN = SND_VOC_144A..). CSnd::PlaySoundVolPanPitch / PlaySound3D send every HN sound
  (single player) to Headset::Queue; the Headset (Apps/FTS/game/headset.cpp 0x2f2a00-0x2f3730) was all stubs and
  ftsGetHeadset returned NULL: that is why no voice plays. Without a USB headset (state 2, "disconnected") the
  headset is a one-at-a-time queue: DisconnectedTick dequeues, StreamSoundVolPan(vol, pan 0) through 989snd's
  VAG streaming (same path as the music, which works).
- Orders: the acknowledgement is CHRSND_YES (53) / NO (54): OnCommand (written) and ConfirmAiState (written).
  CSealUnit::ConfirmCommand (0x2d2030, from OrdersMenu::ScrollForward 0x175858) builds "SND_<unit>_<n>_WILL_<cmd>"
  names that sounds.rdr does not define (no "WILL" sound at all): in the ELF it plays nothing either.
- Callouts (virtual PlayAiSound sites): EnemyCallout 0x2b0e90 (55 TANGO_SIGHTED / 45 TANGO_MOVING / clock
  directions), NotifyTargetDown 0x2b10f0 (18 TANGO_DOWN), OnSetHealth (57 DAMAGE), OnDeath (58/59),
  CAiSGrenade (50/51), SensorPreTick (49).
- Mission cams: missioncams.rdr (m8bs, m8tut1..6: IDENTIFIER, NAME, DESCRIPTION[2,3], ON_CALL_ANIMATION,
  ON_CALL_MUSIC); objectives.rdr `start` sequence: PlayMPEG 0122 -> HUD_TRIGGER_MISSION_CAM m8bs, m8tut1;
  `Insert` (player in InsertObj) -> m8tut2; `Crates` -> m8tut4. tutcams.rdr anims: ai::STOPALL, DYNAMICS_RELEASE/
  ACQUIRE_CAMERA, SET_CAMERA_REGION_TEST, CAMERA_PARAMS (SAVE/RESTORE, FOV, CLIP_ALL, FOG_RANGE), SOUND (HQ:
  m8bs SND_VM08_12, after 7 s SND_VM08_01; MUS_M8 MUSIC_LOCAL), OBJECT_MOTION_FROM_TO on GLOBAL camera.

## Written (ELF addresses)
- headset.cpp (Apps/FTS/game): ftsGetHeadset 0x2f36b0, ctor 0x2f3600, dtor 0x2f34e0, ftsDeleteHeadset 0x2f3400,
  Queue 0x2f3290 (bool), DeQueue 0x2f30f0 (bool), StaticSoundSysCallback 0x2f30c0, SoundSysCallback 0x2f3040,
  Tick 0x2f2ff0, DisconnectedTick 0x2f2ea0, ConnectedTick 0x2f2cf0, Remove 0x2f2b30, StopSound 0x2f2a00;
  zfts.h: Headset members (no DWARF; offsets from the asm), theHeadset typed Headset*.
- seal_sensors.cpp: CSealCtrlAi::EnemyCallout 0x2b0e90, NotifyTargetDown 0x2b10f0.
  ai_main.cpp: ai::get_clock_direction 0x17de90 (int; static in zseal.h via edits/s_zseal.txt).
- Mission cams: fts_missioncam.cpp CMissionCam ctor 0x20b0a0 / Set 0x20adf0; fts_mission.cpp LoadMissionCams
  0x1f31b0, GetMissionCamByIdentifier 0x1f2bf0, HUDTriggerMissionCamParse 0x1f9980 / Begin 0x1f9930, the
  m_missioncams deletes in Close (zfts.h: m_missioncams list, CMissionCam members public);
  hud_missioncams.cpp PlayCamera(CMissionCam*, bool) 0x403830, PlayCamera(const char*) 0x403c10, CleanupCamera
  0x403d10, UnInit 0x4040f0 (cur_zoomstate initial -1 fixed: was (ZOOMSTATE)255).
- zcam_main.cpp: CmdTickControlSwitch 0x1e7470 (DYNAMICS_RELEASE/ACQUIRE_CAMERA), CmdTickSetRegions 0x1e72f0,
  CmdTickGetRegions 0x1e7270. seal_tasks.cpp: CTStopAll::Tick 0x2b5700.
- AI freeze: CSealCtrlAi::SetAiEnabled 0x26bbc0 (edits/s_ai.txt, seal_ai.cpp shared); CAiSSuspended Tick 0x2d7c60 /
  OnSignal 0x2d7e10 (seal_aistate.cpp; members m_matrix / m_was_* in zai.h).
- anim_main.cpp CZAnimMain::GetDatabaseNode 0x1c3230: the landmark search and the GLOBAL NodeUniverse search
  (edits/s_animmain.txt) - this is what finds 'GLOBAL camera' for the cameras' OBJECT_MOTION_FROM_TO.

## ELF quirks kept
- Headset::DeQueue never leaves its loop after taking a line: it drains the queue and keeps the newest, so of the
  lines queued while one plays only the last is heard (EnemyCallout's "tango sighted" + clock + "moving" in one
  frame: the last one plays).
- Headset::Remove: with "conversational" set any current line of the entity stops (type not tested).
- zAnimSoundTick STOP passes entity 0 to Headset::StopSound while anim sounds are queued as 255: STOP_ON_EXIT does not
  stop a mission camera's HQ line (VM08_01 still plays after a skipped m8bs).
- get_clock_direction: the |x| > 0.708 sectors (see the source comment).
- CSealUnit::ConfirmCommand (0x2d2030) is NOT written: it only builds "SND_<unit>_<n>_WILL_<cmd>" names for voice-
  recognition confirmations and sounds.rdr has none (GetSoundByName -> NULL in the ELF too). Its helpers neither.

## Port deviations
- Headset: std::vector for the two vector_pod<Ui> lists; DeQueue's skip list advances the loop (ELF loops for ever;
  unreachable: every caller passes none); Remove guards a NULL current sound; Queue/DeQueue return bool (decl was void).
- GetDatabaseNode: the universe is searched by name inline (CNodeUniverse is a std::vector in the port; the ELF calls
  CNodeVector::GetNode on it).
- EnemyCallout / Headset / mission cam traces (SOCOM_PORT_TRACE).

## Edit files (shared files: apply with srep.py; listed in shared.txt)
- edits/s_zseal.txt (zseal.h: ai::get_clock_direction static int - needed by ai_main.cpp),
  edits/s_ai.txt (seal_ai.cpp: SetAiEnabled), edits/s_animmain.txt (anim_main.cpp: GetDatabaseNode).
- edits/m_mission.txt: already applied to fts_mission.cpp (mine), kept as the record.

## Tools
- bv.sh <build> <pad> = tree.sh + fake.sh + hookv.sh (hook_vc.cpp: scePadRead + CMission::OnMissionStart wraps;
  mission 1 lets the cams play, gives the orders and walks, aborts at SOCOM_HOOK_ABORT_AT reads; mission 2 skips the
  cams with SELECT). default.sh = default build. fulldis.sh, fv.py (float at an ELF address).