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
