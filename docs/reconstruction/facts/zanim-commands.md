# zAnim command records - evidence scan

Read-only scan (no Ghidra/tracker writes). Generated from `build/facts/zanim-scan/` (asm dumps, analyzer output). Names below are provisional unless marked DWARF; offsets are byte offsets from the record start (the `_zanim_cmd_hdr *`).

## Summary

- Registrations: 102 AddCmd call sites -> **99 unique commands** (OBJECT_OPACITY_FROM_TO, OBJECT_ADD_CHILD, OBJECT_DELETE_CHILD are each registered twice with identical callbacks).
- Registrars: CZAnimMain::InitCommands 0x1a9f70 (46), zdb::CCamera::RegisterAnimCommands 0x1e75c0 (6), CAppCamera::RegisterAnimCommands 0x1eba10 (1), CMission::Init 0x1f8e30 (8), CftsPlayer::RegisterAnimCommands 0x1fdef0 (3), CWind::RegisterAnimCommands 0x22d6a0 (1), CSealCtrlAi::RegisterCommands 0x2be630 (33), CValve::RegisterCommands 0x2f8700 (1).
- Callback functions: 224 unique parser/begin/tick/end addresses (+ 29 helpers/UI sub-command functions analysed). 91 of 226 callback live signatures are still `undefined f(void)`.
- Evidence grades: A=56, B=27, C=2, DWARF=8, n/a (header-only)=6. A = exact size proven (calloc size == data_size) and every non-padding byte accessed; B = fixed part proven but variable tail / small unexplained gaps; C = substantial unexplained extent; DWARF = record type already in DWARF/live.
- **Cast hypothesis holds.** DWARF for zcam_main.cpp shows the pattern literally (callback param `hdr` is `_zanim_cmd_hdr *`, local `cmd`/`cmd_ptr` is `_camera_params_cmd *` / `_camera_control_cmd *` / `_camera_set_regions_cmd *`); in asm every parser callocs the exact record size and writes it into `data_size`, and every begin/tick/end reads fields at offsets >= 4 through the header pointer. Only the camera module, TASK_HDR/TASK_SELECT and C2DAnimCmdHdr have DWARF record types; zanim_cmd_parse.cpp / zanim_cmd_tick.cpp / the AI task CU have no DWARF, so ~85 record types are missing.
- Layout sharing: header-only: QUAD_ALIGN, FAIL, BREAK, CAMERA_INDOORS, GET_CAMERA_REGION_TEST, CAMERA_3RD_PERSON, STOP_IMAGE_RECORDER, PLAYER_INDOORS; if-family-8: IF, ELSEIF, ELSE, ENDIF; u16-state-u16-node-8: NODE_ACTIVE, OBJECT_ACTIVE_STATE; f32-8: RANDOM_WEIGHT, HUD_START_DEFUSE_TIMER; blend-tail: OBJECT_BLENDMODE, LIGHT; u16-u8-u8-pnt3d-20: OBJECT_TRANSLATE_STATE, OBJECT_ROTATE_STATE; while-family-8: WHILE, END_WHILE; u8-callanim-8: STOP_ANIMATION, PAUSE_ANIMATION, RESUME_ANIMATION, INVALIDATE_ANIMATION; u8-name-8: CALL_SEQUENCE, STOP_SEQUENCE, HUD_TRIGGER_MISSION_CAM; u16-u8-u8-8: OBJECT_ADD_CHILD, OBJECT_DELETE_CHILD; switch-bits-8: DYNAMICS_RELEASE_CAMERA, DYNAMICS_ACQUIRE_CAMERA, SET_CAMERA_REGION_TEST, HUD_ON, HUD_OFF, HUD_LETTERBOX_ON, HUD_LETTERBOX_OFF, PLAYER_CONTROLS; task-hdr: ai::ACTION, ai::COMM, ai::DEBUG, ai::DOOR, ai::EVENT, ai::FIREMODE, ai::FIREWEAPON, ai::GOTO, ai::HOLD, ai::INSTATE, ai::INVIEW, ai::LOOKAT, ai::MACRO, ai::MAP, ai::MOVE, ai::PAINT, ai::PARAM, ai::PURSUE, ai::ANIMATE, ai::INRANGE, ai::INREGION, ai::SETMODE, ai::SETANIMSET, ai::SIGNAL, ai::SOUND, ai::STANCE, ai::STATE, ai::STOPALL, ai::SPECIAL, ai::TEAM, ai::VALVE, ai::WAIT.

## Header and dispatch

`_zanim_cmd_hdr` (4 bytes, uint bitfields, LSB-first):

| bits | field | access | meaning |
| --- | --- | --- | --- |
| 0..15 | data_type | `lhu +0 / sh +0` | zanim_cmd_val (zanim_cmd_index {u8 cmd, u8 set} or u16 val); stamped by CZAnimMain::AnimParseCmd (sh v0,0(rec)) from zanim_cmd.cmd_val; AI parsers also store ai_cmdid[0] themselves |
| 16 | quad_align | `lbu +2 & 1` | SeqAppendCmd inserts a QUAD_ALIGN padding record (AnimLoadQuadAlignCmd) so the record starts 16-byte aligned in the sequence stream |
| 17 | timeless | `lbu +2 & 2 / sb +2 (or 2)` | set by most parsers (see per-command timeless_set) |
| 18..31 | data_size | `lhu +2 >> 2 ; sh +2 = (old & 0xffff0003) OR (size<<2)` | total record bytes INCLUDING the 4-byte header; CmdNext advances the cursor by it; zAnimCmdAddData/realloc grow it |

- CZAnimMain::AddCmd(this=ZAnim@0x49b320 in a0, a1=name ("set::name" split by SplitName), a2=parser, a3=begin, t0=tick, t1=end) stores parser/begin/tick/end at zanim_cmd +8/+12/+16/+20 (24-byte entries, cmd_set+8 list) and returns zanim_cmd_val (u16). Confirmed from AddCmd body 0x1c4a50 (sw s4,8 / s3,12 / s2,16 / s6,20).
- Mangled tick type is bool (*)(_zanim_cmd_hdr*, float*) (PFP14_zanim_cmd_hdrPf_b); DWARF zanim_cmd.tick (0xa1ada) records uchar - same 1-byte ABI.
- CZAnimMain::AnimParseCmd(name, zrdr) looks up the entry, calls parser(zrdr) via jalr, then stamps rec->data_type = entry.cmd_val; SeqAppendCmd copies data_size bytes into the sequence stream (realloc of seq buffer) and frees nothing; AnimLoadQuadAlignCmd frees its temp record after appending.
- CZAnimMain::CmdTick(float*) takes rec = m_curSeq(+60)->+8 (cursor into the stream), calls begin(rec) on first tick (state 2->4), tick(rec, dt) while state 4, end(rec) when tick returns nonzero. The record pointer given to callbacks is therefore an interior pointer into the packed stream: the callbacks must cast it.
- Variable tails: zAnimCmdAddData(hdr, data, n) = realloc(hdr, data_size+n) + memcpy + data_size += n; several parsers inline the same realloc/memcpy/data_size sequence; AnimParseExpression appends expression sub-records (IF/ELSEIF/WHILE); GetBlendValueSequence appends blend data (OBJECT_BLENDMODE/LIGHT).
- AI tasks (CSealCtrlAi::RegisterCommands): records start with DWARF TASK_HDR {_zanim_cmd_hdr m_cmd; uint m_seal_index}; begin/tick/end call taskFindParam(ai_cmdid[2] = SELECT id, m_seal_index) which scans the current CZAnim arg list (ZAnim+0x38 ->+24, CZAnimArgList::GetCmd) for a TASK_SELECT record and then use TASK_SELECT.m_seal (+12).
- Cursor access: zAnimIfTick/zAnimGoToEndIf/CZAnimExpression::ProcExpr read the *following* records (ELSE/ELSEIF/ENDIF headers and +4 depth bytes, expression operands) through ZAnim+0x3c ->+8 after CmdNext, not through a0.

## DWARF

| type | DIE | size | layout |
| --- | --- | --- | --- |
| `_zanim_cmd_hdr` | 0xde6b/0x9bd18/0xf079d... | 4 | header bitfields (above) |
| `zanim_cmd` | 0x98e00 (orders.cpp) | 24 | char* name; zanim_cmd_val cmd_val(+4); parser(+8) _zanim_cmd_hdr*(*)(_zrdr*) [0x9dd1e]; begin(+12) void(*)(_zanim_cmd_hdr*) [0xa01e3]; tick(+16) uchar(*)(_zanim_cmd_hdr*,float*) [0xa1ada]; end(+20) void(*)(_zanim_cmd_hdr*) [0xa2a17] |
| `zanim_cmd_val` | 0xa7f60 | 2 | union { zanim_cmd_index index; ushort val; } |
| `zanim_cmd_index` | 0xa30a1 | 2 | uchar cmd; uchar set |
| `_zanim_cmd_set` | 0x93fe0 | 12 | char* name; int count; zanim_cmd* cmd_list |
| `_camera_params_cmd` | 0xf570e (zcam_main.cpp) | 36 | hdr; uint save_params:1..fog_altitude_enabled:1 (+4 bits0-5); float run_time(+8); 7 x {uint X_offset:16, X_count:16} (+12..+32) |
| `_camera_param_1d/2d/3d_data` | 0xf2e45/0xf2dba/0xf66dd | 8/12/16 | float time; float a[,b[,c]] - tail elements of _camera_params_cmd |
| `_camera_control_cmd` | 0xf3cbf | 8 | hdr; int release:1; int acquire:1 (+4) |
| `_camera_set_regions_cmd` | 0xf2c50 | 8 | hdr; int set_on:1 (+4) |
| `TASK_HDR` | 0x56ca2 (database.cpp) | 8 | _zanim_cmd_hdr m_cmd; uint m_seal_index(+4) |
| `TASK_SELECT` | 0x5a250 | 16 | TASK_HDR base; CSealCtrlAi* m_ai(+8); CZSealBody* m_seal(+12) |
| `C2DAnimCmdHdr` | 0xa130e (orders.cpp) | 8 | _zanim_cmd_hdr header; ushort node_ref_index(+4); uchar m_command_type(+6); uchar m_argument_index(+7) |
| `_zanim_si_script / _zanim_node_ref / _zanim_call_anim_ref / _zanim_sound / _zanim_valve_ref / _zanim_tex_ref / _zanim_particle` | various | 20/8/12/12/8/8/8 | CZAnim reference tables that the u8/u16 *_ref index fields in command records select (GetNode/GetCallAnimRef/GetSoundRef/GetValve/GetTexture/GetParticleSource) |

DWARF cast evidence (function locals):

- zdb::CCamera::CmdBeginParams: param hdr (_zanim_cmd_hdr*), local cmd_ptr (_camera_params_cmd*).
- zdb::CCamera::CmdTickParams: param hdr (_zanim_cmd_hdr*), local cmd_ptr (_camera_params_cmd*, s0) + tail element pointers lod/fog/clip/fov (_camera_param_Nd_data*).
- zdb::CCamera::CmdTickControlSwitch: local cmd (_camera_control_cmd*); CmdParseAcquire/Release: local cmd (_camera_control_cmd*).
- zdb::CCamera::CmdParseSetRegions: local cmd (_camera_set_regions_cmd*); CmdParseParams: local cmd (_camera_params_cmd*).
- CmdParseGetRegions / CmdParseIndoorsTest / CAppCamera::CmdParse3rdPersonTest: local cmd (_zanim_cmd_hdr*) - header-only records.

No other command-record types exist in DWARF (searched all 21614 type DIEs for *cmd*/*CMD*/TASK*/_zanim*/_camera*/_hud*/*_DATA). Missing named types referenced only by mangled symbols:

| type | size | evidence |
| --- | --- | --- |
| `VALVE_CMD_DATA` | 12 | mangled methods Compare/GetValue/ParseValveName (0x2f8310/0x2f8600/0x2f8070); embedded at VALVE+4 and ai::VALVE+8; +0 int/valve, +4 int/valve, +8 u8 operator (jump-table index), +9 u8 flags |
| `CZAnimFromToAcc` | 56 | mangled Tick(float, CPnt3D*) 0x1baf10 / ComputeRunTime(CPnt3D*,CPnt3D*) 0x1bb100; appended at OBJECT_MOTION_FROM_TO+128 (realloc +56) when flags & 0x6000; accessed +0..+52 |
| `_zanim_object_motion_script` | 60 | apply_script_frame__FP27_zanim_object_motion_script...; entries at OBJECT_MOTION_SI_SCRIPT+8+60k, each starts with a _zanim_cmd_hdr (ticked by zAnimObjectMotionScriptTick(entry)); accessed +4,+5,+7,+12..+28,+56 |
| `zanim_script_frame_header` | ? | mangled param of apply_script_frame/_store_frame_data (SI script data, not a command record) |
| `_zanim_blend_fix` | ? | mangled param of GetBlendSequenceValue; likely element of the OBJECT_BLENDMODE/LIGHT blend tail |

## Inventory

Groups: recon-group number (plan/apply status at scan time). Live: `T` = typed live signature, `u` = `undefined f(void)`.

| command | registrar | parser | begin | tick | end | size | grade | proposed type |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QUAD_ALIGN | CZAnimMain::InitCommands | - | - | 0x1bfe80 `zAnimQuadAlignTick` g23(acc/acc) T | - | - | n/a (header-only) | _zanim_cmd_hdr (no new type) |
| IF | CZAnimMain::InitCommands | 0x1b09e0 `zAnimLoad_If` g274(blo/blo) u | - | 0x1b8f20 `zAnimIfTick` g129(acc/acc) T | - | 8 + tail | B | _zanim_if_cmd (provisional) |
| ELSEIF | CZAnimMain::InitCommands | 0x1b0940 `zAnimLoad_ElseIf` g274(blo/blo) u | - | 0x1b8e70 `zAnimGoToEndIf` g101(acc/acc) T | - | 8 + tail | B | _zanim_if_cmd (provisional) |
| ELSE | CZAnimMain::InitCommands | 0x1b08c0 `zAnimLoad_Else` g228(acc/acc) T | - | 0x1b8e70 `zAnimGoToEndIf` g101(acc/acc) T | - | 8 | A | _zanim_if_cmd (provisional) |
| ENDIF | CZAnimMain::InitCommands | 0x1b0830 `zAnimLoad_EndIf` g228(acc/acc) T | - | 0x1b8e50 `zAnimEndIfTick` g22(acc/acc) T | - | 8 | A | _zanim_if_cmd (provisional) |
| NODE_ACTIVE | CZAnimMain::InitCommands | 0x1b06e0 `zAnimLoadNodeActive` g265(blo/blo) u | - | 0x1b8c50 `zAnimNodeActiveTick` g166(acc/acc) T | - | 8 | A | _zanim_node_state_cmd (provisional) |
| NODE_RENDERED | CZAnimMain::InitCommands | 0x1b0620 `zAnimLoadNodeRendered` g265(blo/blo) u | - | 0x1b8c00 `zAnimNodeRenderedTick` g166(acc/acc) T | - | 8 | A | _zanim_node_rendered_cmd (provisional) |
| RANGE_TEST | CZAnimMain::InitCommands | 0x1b00c0 `zAnimLoadRangeTest` g265(blo/blo) u | - | 0x1b88d0 `zAnimRangeTestTick` g166(acc/acc) T | - | 40 | A | _zanim_range_test_cmd (provisional) |
| RANDOM_WEIGHT | CZAnimMain::InitCommands | 0x1aff50 `zAnimLoadRandomWeight` g228(acc/acc) T | - | 0x1b8730 `zAnimRandomWeightTick` g101(acc/acc) T | - | 8 | A | _zanim_random_weight_cmd (provisional) |
| FAIL | CZAnimMain::InitCommands | 0x1afef0 `zAnimLoadFail` g228(acc/acc) T | - | 0x1b8720 `zAnimFailTick` g22(acc/acc) T | - | 4 | n/a (header-only) | _zanim_cmd_hdr (no new type) |
| ANIM_HEALTH | CZAnimMain::InitCommands | 0x1afbd0 `zAnimLoadAnimHealthTest` g228(acc/acc) T | - | 0x1b8840 `zAnimHealthTestTick` g101(acc/acc) T | - | 12 + tail | B | _zanim_anim_health_cmd (provisional) |
| ANIM_LOD | CZAnimMain::InitCommands | 0x1af650 `zAnimLoadAnimLODTest` g228(acc/acc) T | - | 0x1b8790 `zAnimLODTestTick` g22(acc/acc) T | - | 8 | A | _zanim_anim_lod_cmd (provisional) |
| LOOP | CZAnimMain::InitCommands | 0x1b18d0 `zAnimLoadLoop` g228(acc/acc) T | - | 0x1b9750 `zAnimLoopTick` g102(acc/acc) T | - | 12 | A | _zanim_loop_cmd (provisional) |
| WAIT | CZAnimMain::InitCommands | 0x1b1230 `zAnimLoadWait` g228(acc/acc) T | 0x1b96c0 `zAnimWaitBegin` g102(acc/acc) T | 0x1b95c0 `zAnimWaitTick` g22(acc/acc) T | - | 12 + tail | B | _zanim_wait_cmd (provisional) |
| OBJECT_BLENDMODE | CZAnimMain::InitCommands | 0x1b3560 `zAnimLoadObjectBlendMode` g266(blo/blo) u | - | 0x1bd590 `zAnimObjectBlendModeTick` g166(acc/acc) T | - | 20 + tail | B | _zanim_object_blendmode_cmd (provisional) |
| OBJECT_ACTIVE_STATE | CZAnimMain::InitCommands | 0x1b3420 `zAnimLoadObjectActiveState` g266(blo/blo) u | - | 0x1bd510 `zAnimObjectActiveStateTick` g166(acc/acc) T | - | 8 | A | _zanim_node_state_cmd (provisional) |
| OBJECT_TRANSLATE_STATE | CZAnimMain::InitCommands | 0x1b31c0 `zAnimLoadObjectTranslateState` g266(blo/blo) u | - | 0x1bd320 `zAnimObjectTranslateStateTick` g166(acc/acc) T | - | 20 | A | _zanim_object_xform_state_cmd (provisional) |
| OBJECT_ROTATE_STATE | CZAnimMain::InitCommands | 0x1b2fb0 `zAnimLoadObjectRotateState` g266(blo/blo) u | - | 0x1bd1f0 `zAnimObjectRotateStateTick` g171(acc/acc) T | - | 20 | A | _zanim_object_xform_state_cmd (provisional) |
| OBJECT_MOTION | CZAnimMain::InitCommands | 0x1ac7d0 `zAnimLoadObjectMotion` g274(blo/blo) u | 0x1bc540 `zAnimObjectMotionBegin` g166(acc/acc) T | 0x1bb330 `zAnimObjectMotionTick` g281(blo/blo) u | - | 124 + tail | B | _zanim_object_motion_cmd (provisional) |
| OBJECT_MOTION_FROM_TO | CZAnimMain::InitCommands | 0x1b1b90 `zAnimLoadObjectMotionFromTo` g265(blo/blo) u | 0x1ba630 `zAnimObjectMotionFromToBegin` g254(blo/blo) u | 0x1ba2d0 `zAnimObjectMotionFromToTick` g170(acc/acc) T | - | 128 + tail | B | _zanim_object_motion_from_to_cmd (provisional) + CZAnimFromToAcc (missing, 56 bytes) |
| OBJECT_OPACITY_FROM_TO | CZAnimMain::InitCommands | 0x1b1a20 `zAnimLoadObjectOpacityFromTo` g265(blo/blo) u | 0x1ba280 `zAnimObjectOpacityFromToBegin` g166(acc/acc) T | 0x1ba1c0 `zAnimObjectOpacityFromToTick` g166(acc/acc) T | - | 24 | A | _zanim_object_opacity_from_to_cmd (provisional) |
| OBJECT_MOTION_SI_SCRIPT | CZAnimMain::InitCommands | 0x1abcf0 `zAnimLoadObjectMotionSIScript` g274(blo/blo) u | 0x1b9b10 `zAnimMultiObjectMotionScriptBegin` g22(acc/acc) T | 0x1b9a30 `zAnimMultiObjectMotionScriptTick` g178(acc/acc) T | - | 68 + tail | C | _zanim_object_motion_si_script_cmd (provisional) + _zanim_object_motion_script (missing, 60 bytes) |
| PARTICLE_SOURCE | CZAnimMain::InitCommands | 0x1b5e30 `zAnimLoadParticleSource` g266(blo/blo) u | - | 0x1bee80 `zAnimParticleSourceTick` g286(blo/blo) u | - | 220 + tail | B | _zanim_particle_source_cmd (provisional) |
| CAMERA | CZAnimMain::InitCommands | 0x1b4ca0 `zAnimLoadCamera` g266(blo/blo) u | 0x1be9b0 `zAnimCameraBegin` g166(acc/acc) T | 0x1be5e0 `zAnimCameraTick` g166(acc/acc) T | - | 132 | A | _zanim_camera_cmd (provisional) |
| DESTRUCTION_SOURCE | CZAnimMain::InitCommands | 0x1b7750 `zAnimLoadDestructor` g266(blo/blo) u | - | 0x1bfd90 `zAnimDestructorTick` g298(blo/blo) u | - | 80 | A | _zanim_destruction_source_cmd (provisional) |
| SOUND | CZAnimMain::InitCommands | 0x1b4920 `zAnimLoadSound` g266(blo/blo) u | - | 0x1be170 `zAnimSoundTick` g281(blo/blo) u | - | 32 | A | _zanim_sound_cmd (provisional) |
| LIGHT | CZAnimMain::InitCommands | 0x1b37f0 `zAnimLoadLight` g266(blo/blo) u | - | 0x1bd7c0 `zAnimLightTick` g274(blo/blo) u | - | 64 + tail | B | _zanim_light_cmd (provisional) |
| WHILE | CZAnimMain::InitCommands | 0x1b0c10 `zAnimLoadWhile` g274(blo/blo) u | - | 0x1b8de0 `zAnimWhileTick` g129(acc/acc) T | - | 8 + tail | B | _zanim_while_cmd (provisional) |
| END_WHILE | CZAnimMain::InitCommands | 0x1b0b00 `zAnimLoadEndWhile` g228(acc/acc) T | - | 0x1b8db0 `zAnimEndWhileTick` g101(acc/acc) T | - | 8 | B | _zanim_while_cmd (provisional) |
| EXPRESSION | CZAnimMain::InitCommands | - | - | - | - | - | n/a (header-only) | _zanim_cmd_hdr-headed operand records (NewCmd, 8 bytes) |
| BREAK | CZAnimMain::InitCommands | 0x1b0a90 `zAnimLoadBreak` g228(acc/acc) T | - | 0x1b8ce0 `zAnimBreakTick` g101(acc/acc) T | - | 4 | n/a (header-only) | _zanim_cmd_hdr (no new type) |
| CALL_ANIMATION | CZAnimMain::InitCommands | 0x1af2f0 `zAnimLoadCallAnim` g265(blo/blo) u | 0x1b8380 `zAnimCallAnimBegin` g298(blo/blo) u | 0x1b8310 `zAnimCallAnimTick` g274(blo/blo) u | - | 24 | A | _zanim_call_animation_cmd (provisional) |
| STOP_ANIMATION | CZAnimMain::InitCommands | 0x1af1d0 `zAnimLoadStopAnim` g265(blo/blo) u | - | 0x1b8280 `zAnimStopAnimTick` g274(blo/blo) u | - | 8 | A | _zanim_anim_ref_cmd (provisional) |
| PAUSE_ANIMATION | CZAnimMain::InitCommands | 0x1af0d0 `zAnimLoadPauseAnim` g265(blo/blo) u | - | 0x1b81d0 `zAnimPauseAnimTick` g274(blo/blo) u | - | 8 | A | _zanim_anim_ref_cmd (provisional) |
| RESUME_ANIMATION | CZAnimMain::InitCommands | 0x1aefb0 `zAnimLoadResumeAnim` g265(blo/blo) u | - | 0x1b8140 `zAnimResumeAnimTick` g274(blo/blo) u | - | 8 | A | _zanim_anim_ref_cmd (provisional) |
| INVALIDATE_ANIMATION | CZAnimMain::InitCommands | 0x1aee90 `zAnimLoadInvalidateAnim` g265(blo/blo) u | - | 0x1b80c0 `zAnimInvalidateAnimTick` g274(blo/blo) u | - | 8 | A | _zanim_anim_ref_cmd (provisional) |
| CALL_SEQUENCE | CZAnimMain::InitCommands | 0x1aed80 `zAnimLoadCallSequence` g265(blo/blo) u | - | 0x1b8080 `zAnimCallSequenceTick` g161(acc/acc) T | - | 8 | A | _zanim_sequence_cmd (provisional) |
| STOP_SEQUENCE | CZAnimMain::InitCommands | 0x1aec70 `zAnimLoadStopSequence` g265(blo/blo) u | - | 0x1b8040 `zAnimStopSequenceTick` g161(acc/acc) T | - | 8 | A | _zanim_sequence_cmd (provisional) |
| DEBUG | CZAnimMain::InitCommands | 0x1aaef0 `zAnimLoadDebug` g265(blo/blo) u | - | 0x1b7c80 `zAnimDebugTick` g22(acc/acc) T | - | 20 + tail | B | _zanim_debug_cmd (provisional) |
| OBJECT_ADD_CHILD | CZAnimMain::InitCommands | 0x1abb80 `zAnimLoadObjectAddChild` g265(blo/blo) u | - | 0x1b98b0 `zAnimObjectAddChildTick` g166(acc/acc) T | - | 8 | A | _zanim_object_child_cmd (provisional) |
| OBJECT_DELETE_CHILD | CZAnimMain::InitCommands | 0x1aba30 `zAnimLoadObjectDeleteChild` g265(blo/blo) u | - | 0x1b9830 `zAnimObjectDeleteChildTick` g166(acc/acc) T | - | 8 | B | _zanim_object_child_cmd (provisional) |
| MESSAGE | CZAnimMain::InitCommands | 0x1aacb0 `zAnimLoadMessage` g265(blo/blo) u | - | 0x1bfce0 `zAnimMessageTick` g254(blo/blo) u | - | 8 | A | _zanim_message_cmd (provisional) |
| TIMER | CZAnimMain::InitCommands | 0x1aae30 `zAnimLoadTimer` g228(acc/acc) T | - | 0x1bfd70 `zAnimTimerTick` g23(acc/acc) T | - | 8 | A | _zanim_timer_cmd (provisional) |
| FIRE_WEAPON | CZAnimMain::InitCommands | 0x1aa840 `zAnimLoadFireWeapon` g265(blo/blo) u | - | 0x1b7c90 `zAnimFireWeaponTick` g318(blo/blo) u | - | 44 | A | _zanim_fire_weapon_cmd (provisional) |
| ui::UI_COMMAND | CZAnimMain::InitCommands | 0x1d04b0 `zAnimLoadUIMenu` g286(blo/blo) u | - | 0x1d0140 `zAnimUIMenuTick` g286(blo/blo) u | - | 8 | DWARF | C2DAnimCmdHdr (DWARF, 8 bytes) / control-specific C2DAnimCmdHdr-prefixed records |
| ui::UI_APP_COMMAND | CZAnimMain::InitCommands | 0x1d0330 `zAnimLoadUIAppMenu` g266(blo/blo) u | - | 0x1d0130 `zAnimUIAppMenuTick` g24(acc/acc) T | - | 8 | A | _zanim_ui_app_cmd (provisional) |
| DYNAMICS_RELEASE_CAMERA | zdb::CCamera::RegisterAnimCommands | 0x1e7530 `zdb::CCamera::CmdParseRelease` g229(acc/acc) T | - | 0x1e7470 `zdb::CCamera::CmdTickControlSwitch` g28(acc/acc) T | - | 8 | DWARF | _camera_control_cmd (DWARF) |
| DYNAMICS_ACQUIRE_CAMERA | zdb::CCamera::RegisterAnimCommands | 0x1e74b0 `zdb::CCamera::CmdParseAcquire` g229(acc/acc) T | - | 0x1e7470 `zdb::CCamera::CmdTickControlSwitch` g28(acc/acc) T | - | 8 | DWARF | _camera_control_cmd (DWARF) |
| CAMERA_INDOORS | zdb::CCamera::RegisterAnimCommands | 0x1e7400 `zdb::CCamera::CmdParseIndoorsTest` g229(acc/acc) T | - | 0x1e73f0 `zdb::CCamera::CmdTickIndoorsTest` g28(acc/acc) T | - | 4 | DWARF | _zanim_cmd_hdr (DWARF parser locals) |
| SET_CAMERA_REGION_TEST | zdb::CCamera::RegisterAnimCommands | 0x1e7320 `zdb::CCamera::CmdParseSetRegions` g229(acc/acc) T | - | 0x1e72f0 `zdb::CCamera::CmdTickSetRegions` g28(acc/acc) T | - | 8 | DWARF | _camera_set_regions_cmd (DWARF) |
| GET_CAMERA_REGION_TEST | zdb::CCamera::RegisterAnimCommands | 0x1e7280 `zdb::CCamera::CmdParseGetRegions` g229(acc/acc) T | - | 0x1e7270 `zdb::CCamera::CmdTickGetRegions` g28(acc/acc) T | - | 4 | DWARF | _zanim_cmd_hdr (DWARF parser locals) |
| CAMERA_PARAMS | zdb::CCamera::RegisterAnimCommands | 0x1e6300 `zdb::CCamera::CmdParseParams` g237(rea/blo) u | 0x1e61c0 `zdb::CCamera::CmdBeginParams` g28(acc/acc) T | 0x1e5570 `zdb::CCamera::CmdTickParams` g161(acc/acc) T | - | 36 + tail | DWARF | _camera_params_cmd (DWARF) |
| CAMERA_3RD_PERSON | CAppCamera::RegisterAnimCommands | 0x1eb9a0 `CAppCamera::CmdParse3rdPersonTest` g229(acc/acc) T | - | 0x1eb980 `CAppCamera::CmdTick3rdPersonTest` g28(acc/acc) T | - | 4 | DWARF | _zanim_cmd_hdr (DWARF parser locals) |
| HUD_ON | CMission::Init | 0x1f9d60 `HUDCmdParseOn` g229(acc/acc) T | - | 0x1f9c70 `HUDCmdTickControlSwitch` g237(rea/blo) u | - | 8 | A | _hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd) |
| HUD_OFF | CMission::Init | 0x1f9ce0 `HUDCmdParseOff` g229(acc/acc) T | - | 0x1f9c70 `HUDCmdTickControlSwitch` g237(rea/blo) u | - | 8 | A | _hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd) |
| HUD_LETTERBOX_ON | CMission::Init | 0x1f9be0 `HUDLetterBoxCmdParseOn` g229(acc/acc) T | - | 0x1f9af0 `HUDLetterBoxCmdTick` g104(acc/acc) T | - | 8 | A | _hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd) |
| HUD_LETTERBOX_OFF | CMission::Init | 0x1f9b60 `HUDLetterBoxCmdParseOff` g229(acc/acc) T | - | 0x1f9af0 `HUDLetterBoxCmdTick` g104(acc/acc) T | - | 8 | A | _hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd) |
| HUD_TRIGGER_MISSION_CAM | CMission::Init | 0x1f9980 `HUDTriggerMissionCamParse` g267(blo/blo) u | 0x1f9930 `HUDTriggerMissionCamBegin` g302(blo/blo) u | 0x1f98d0 `HUDTriggerMissionCamTick` g104(acc/acc) T | - | 8 | A | _hud_mission_cam_cmd (provisional) |
| HUD_START_DEFUSE_TIMER | CMission::Init | 0x1f9760 `HUDStartDefuseTimerParse` g229(acc/acc) T | - | 0x1f9740 `HUDStartDefuseTimerTick` g267(blo/blo) u | - | 8 | A | _hud_defuse_timer_cmd (provisional) |
| START_IMAGE_RECORDER | CMission::Init | 0x1f9e80 `StartImageRecorderParse` g267(blo/blo) u | - | 0x1f9e70 `StartImageRecorderTick` g31(acc/acc) T | - | 12 | A | _image_recorder_cmd (provisional) |
| STOP_IMAGE_RECORDER | CMission::Init | 0x1f9e00 `StopImageRecorderParse` g229(acc/acc) T | - | 0x1f9df0 `StopImageRecorderTick` g31(acc/acc) T | - | 4 | n/a (header-only) | _zanim_cmd_hdr (no new type) |
| PLAYER_INDOORS | CftsPlayer::RegisterAnimCommands | 0x1fde80 `CftsPlayer::CmdParseIndoorsTest` g229(acc/acc) T | - | 0x1fde50 `CftsPlayer::CmdTickIndoorsTest` g31(acc/acc) T | - | 4 | n/a (header-only) | _zanim_cmd_hdr (no new type) |
| PLAYER_CONTROLS | CftsPlayer::RegisterAnimCommands | 0x1fdd80 `CftsPlayer::CmdParseControls` g229(acc/acc) T | - | 0x1fdd10 `CftsPlayer::CmdTickControls` g31(acc/acc) T | - | 8 | A | _hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd) |
| IS_PLAYER_NODE | CftsPlayer::RegisterAnimCommands | 0x1fdc20 `CftsPlayer::CmdParseIsPlayerNode` g267(blo/blo) u | - | 0x1fdb80 `CftsPlayer::CmdTickIsPlayerNode` g167(acc/acc) T | - | 8 | A | _player_is_node_cmd (provisional) |
| WIND | CWind::RegisterAnimCommands | 0x22cd40 `CWind::CmdParseWind` g230(acc/acc) T | - | 0x22cb30 `CWind::CmdTickWind` g37(acc/acc) T | - | 68 | A | _wind_cmd (provisional) |
| ai::ACTION | CSealCtrlAi::RegisterCommands | 0x2be520 `CTAction::Parse` g269(blo/blo) u | - | 0x2be2f0 `CTAction::Tick` g277(blo/blo) u | - | 16 | A | TASK_ACTION : TASK_HDR (provisional) |
| ai::COMM | CSealCtrlAi::RegisterCommands | 0x2be230 `CTComm::Parse` g231(acc/acc) T | - | 0x2bde00 `CTComm::Tick` g287(blo/blo) u | - | 16 | A | TASK_COMM : TASK_HDR (provisional) |
| ai::DEBUG | CSealCtrlAi::RegisterCommands | 0x2bdc90 `CTDebug::Parse` g231(acc/acc) T | - | 0x2bdb70 `CTDebug::Tick` g146(acc/acc) T | - | var (sizeof 16) | B | TASK_DEBUG : TASK_HDR (provisional) |
| ai::DOOR | CSealCtrlAi::RegisterCommands | 0x2bdb60 `Parse` g277(blo/blo) u<br>0x2ba460 `CTMove::Parse` g269(blo/blo) u | 0x2bdb50 `Begin` g269(blo/blo) u<br>0x2b9c90 `CTMove::Begin` g258(blo/blo) u | 0x2bda90 `CTDoor::Tick` g146(acc/acc) T | 0x2bda20 `CTDoor::End` g146(acc/acc) T | 44 | A | TASK_MOVE (shared with ai::MOVE; provisional) |
| ai::EVENT | CSealCtrlAi::RegisterCommands | 0x2bd860 `CTEvent::Parse` g269(blo/blo) u | 0x2bd850 `CTEvent::Begin` g48(acc/acc) T | 0x2bd5e0 `CTEvent::Tick` g258(blo/blo) u | - | 36 | A | TASK_EVENT : TASK_HDR (provisional) |
| ai::FIREMODE | CSealCtrlAi::RegisterCommands | 0x2bd3a0 `CTFireMode::Parse` g230(acc/acc) T | 0x2bd1a0 `CTFireMode::Begin` g321(blo/blo) u | 0x2bd100 `CTFireMode::Tick` g146(acc/acc) T | - | 28 | A | TASK_FIREMODE : TASK_HDR (provisional) |
| ai::FIREWEAPON | CSealCtrlAi::RegisterCommands | 0x2bd060 `CTFireWeapon::Parse` g230(acc/acc) T | 0x2bcfa0 `CTFireWeapon::Begin` g146(acc/acc) T | 0x2bcd70 `CTFireWeapon::Tick` g277(blo/blo) u | - | 44 | C | TASK_FIREWEAPON : TASK_HDR (provisional) |
| ai::GOTO | CSealCtrlAi::RegisterCommands | 0x2bc910 `CTGoto::Parse` g247(blo/blo) u | 0x2bc300 `CTGoto::Begin` g296(blo/blo) u | 0x2bc210 `CTGoto::Tick` g146(acc/acc) T | 0x2bc100 `CTGoto::End` g146(acc/acc) T | var (sizeof 20) | B | TASK_GOTO : TASK_HDR (provisional) |
| ai::HOLD | CSealCtrlAi::RegisterCommands | 0x2bc030 `CTHold::Parse` g230(acc/acc) T | 0x2bbf30 `CTHold::Begin` g258(blo/blo) u | 0x2bbe50 `CTHold::Tick` g146(acc/acc) T | 0x2bbda0 `CTHold::End` g258(blo/blo) u | 20 | A | TASK_HOLD : TASK_HDR (provisional) |
| ai::INSTATE | CSealCtrlAi::RegisterCommands | 0x2bbb00 `CTInState::Parse` g230(acc/acc) T | - | 0x2bb9c0 `CTInState::Tick` g146(acc/acc) T | - | var (sizeof 16) | B | TASK_INSTATE : TASK_HDR (provisional) |
| ai::INVIEW | CSealCtrlAi::RegisterCommands | 0x2bb800 `CTInView::Parse` g230(acc/acc) T | - | 0x2bb680 `CTInView::Tick` g155(acc/acc) T | - | var (sizeof 20) | B | TASK_INVIEW : TASK_HDR (provisional) |
| ai::LOOKAT | CSealCtrlAi::RegisterCommands | 0x2bb1c0 `CTLookAt::Parse` g230(acc/acc) T | 0x2bb0b0 `CTLookAt::Begin` g146(acc/acc) T | 0x2badf0 `CTLookAt::Tick` g146(acc/acc) T | - | var (sizeof 48) | B | TASK_LOOKAT : TASK_HDR (provisional) |
| ai::MACRO | CSealCtrlAi::RegisterCommands | 0x2bacd0 `CTMacro::Parse` g230(acc/acc) T | 0x2babe0 `CTMacro::Begin` g269(blo/blo) u | 0x2baa30 `CTMacro::Tick` g298(blo/blo) u | - | var (sizeof 20) | B | TASK_MACRO : TASK_HDR (provisional) |
| ai::MAP | CSealCtrlAi::RegisterCommands | 0x2ba8a0 `CTMap::Parse` g230(acc/acc) T | - | 0x2ba710 `CTMap::Tick` g258(blo/blo) u | - | 20 | A | TASK_MAP : TASK_HDR (provisional) |
| ai::MOVE | CSealCtrlAi::RegisterCommands | 0x2ba460 `CTMove::Parse` g269(blo/blo) u | 0x2b9c90 `CTMove::Begin` g258(blo/blo) u | 0x2b9bd0 `CTMove::Tick` g146(acc/acc) T | 0x2b9b30 `CTMove::End` g145(acc/acc) T | 44 | A | TASK_MOVE : TASK_HDR (provisional) |
| ai::PAINT | CSealCtrlAi::RegisterCommands | 0x2b98d0 `CTPaint::Parse` g230(acc/acc) T | - | 0x2b9820 `CTPaint::Tick` g258(blo/blo) u | - | 20 | A | TASK_PAINT : TASK_HDR (provisional) |
| ai::PARAM | CSealCtrlAi::RegisterCommands | 0x2b93d0 `CTParam::Parse` g230(acc/acc) T | - | 0x2b8230 `CTParam::Tick` g287(blo/blo) u | - | var (sizeof 20) | B | TASK_PARAM : TASK_HDR (provisional) |
| ai::PURSUE | CSealCtrlAi::RegisterCommands | 0x2b81a0 `CTPursue::Parse` g230(acc/acc) T | 0x2b80b0 `CTPursue::Begin` g277(blo/blo) u | 0x2b8000 `CTPursue::Tick` g145(acc/acc) T | 0x2b7f80 `CTPursue::End` g145(acc/acc) T | 12 | A | TASK_PURSUE : TASK_HDR (provisional) |
| ai::ANIMATE | CSealCtrlAi::RegisterCommands | 0x2b7c40 `CTPlay::Parse` g277(blo/blo) u<br>0x2b7dd0 `CTPlay::Create` g230(acc/acc) u | 0x2b7ae0 `CTPlay::Begin` g145(acc/acc) T | 0x2b7640 `CTPlay::Tick` g325(blo/blo) u | 0x2b7a10 `CTPlay::End` g145(acc/acc) T | var (sizeof 40) | B | TASK_PLAY : TASK_HDR (provisional) |
| ai::INRANGE | CSealCtrlAi::RegisterCommands | 0x2b55d0 `CTRange::Parse` g230(acc/acc) T | - | 0x2b53f0 `CTRange::Tick` g145(acc/acc) T | - | var (sizeof 20) | B | TASK_RANGE : TASK_HDR (provisional) |
| ai::INREGION | CSealCtrlAi::RegisterCommands | 0x2b5260 `CTRegion::Parse` g230(acc/acc) T | - | 0x2b4c50 `CTRegion::Tick` g145(acc/acc) T | - | var (sizeof 28) | B | TASK_REGION : TASK_HDR (provisional) |
| ai::SELECT | CSealCtrlAi::RegisterCommands | 0x2b74b0 `CTSelect::Parse` g230(acc/acc) T | - | 0x2b74a0 `CTSelect::Tick` g48(acc/acc) T | - | 16 | A | ? |
| ai::SETMODE | CSealCtrlAi::RegisterCommands | 0x2b73a0 `CTSetMode::Parse` g230(acc/acc) T | - | 0x2b7250 `CTSetMode::Tick` g287(blo/blo) u | - | 12 | A | TASK_SETMODE : TASK_HDR (provisional) |
| ai::SETANIMSET | CSealCtrlAi::RegisterCommands | 0x2b7130 `CTSetAnimSet::Parse` g230(acc/acc) T | - | 0x2b7050 `CTSetAnimSet::Tick` g318(blo/blo) u | - | var (sizeof 16) | B | TASK_SETANIMSET : TASK_HDR (provisional) |
| ai::SIGNAL | CSealCtrlAi::RegisterCommands | 0x2b6d60 `CTSignal::Parse` g230(acc/acc) T | - | 0x2b6c50 `CTSignal::Tick` g283(blo/blo) u | - | var (sizeof 16) | B | TASK_SIGNAL : TASK_HDR (provisional) |
| ai::SOUND | CSealCtrlAi::RegisterCommands | 0x2b6840 `CTSound::Parse` g230(acc/acc) T | 0x2b6820 `CTSound::Begin` g48(acc/acc) T | 0x2b64b0 `CTSound::Tick` g277(blo/blo) u | 0x2b67e0 `CTSound::End` g111(acc/acc) T | var (sizeof 20) | B | TASK_SOUND : TASK_HDR (provisional) |
| ai::STANCE | CSealCtrlAi::RegisterCommands | 0x2b6010 `CTStance::Parse` g230(acc/acc) T | 0x2b5f70 `CTStance::Begin` g155(acc/acc) T | 0x2b5de0 `CTStance::Tick` g145(acc/acc) T | 0x2b5eb0 `CTStance::End` g145(acc/acc) T | 24 | A | TASK_STANCE : TASK_HDR (provisional) |
| ai::STATE | CSealCtrlAi::RegisterCommands | 0x2b5bd0 `CTState::Parse` g230(acc/acc) T | - | 0x2b5820 `CTState::Tick` g277(blo/blo) u | - | var (sizeof 40) | B | TASK_STATE : TASK_HDR (provisional) |
| ai::STOPALL | CSealCtrlAi::RegisterCommands | 0x2b5750 `CTStopAll::Parse` g230(acc/acc) T | - | 0x2b5700 `CTStopAll::Tick` g283(blo/blo) u | - | 12 | A | TASK_STOPALL : TASK_HDR (provisional) |
| ai::SPECIAL | CSealCtrlAi::RegisterCommands | 0x2b6450 `CTSpecial::Parse` g230(acc/acc) T | 0x2b63d0 `CTSpecial::Begin` g145(acc/acc) T | 0x2b6150 `CTSpecial::Tick` g135(acc/acc) u | 0x2b62d0 `CTSpecial::End` g171(acc/acc) T | 12 | A | TASK_SPECIAL : TASK_HDR (provisional) |
| ai::TEAM | CSealCtrlAi::RegisterCommands | 0x2b4b40 `CTTeam::Parse` g230(acc/acc) T | - | 0x2b49f0 `CTTeam::Tick` g145(acc/acc) T | - | 16 | A | TASK_TEAM : TASK_HDR (provisional) |
| ai::VALVE | CSealCtrlAi::RegisterCommands | 0x2b4510 `CTValve::Parse` g269(blo/blo) u | - | 0x2b4450 `CTValve::Tick` g283(blo/blo) u | - | 24 | A | TASK_VALVE : TASK_HDR (provisional) |
| ai::WAIT | CSealCtrlAi::RegisterCommands | 0x2b4300 `CTWait::Parse` g230(acc/acc) T | 0x2b4230 `CTWait::Begin` g145(acc/acc) T | 0x2b4030 `CTWait::Tick` g145(acc/acc) T | - | 20 | A | TASK_WAIT : TASK_HDR (provisional) |
| VALVE | CValve::RegisterCommands | 0x2f7930 `CValve::CmdParseCmp` g270(blo/blo) u | - | 0x2f8160 `CValve::CmdTickCmp` g283(blo/blo) u<br>0x2f8310 `VALVE_CMD_DATA::Compare` g278(blo/blo) u | - | 16 | A | _valve_cmp_cmd (provisional) = { hdr; VALVE_CMD_DATA (missing, 12 bytes) at +4 } |

## Per-command field tables

Columns: offset, width, kind (f32 = lwc1/swc1 or FPU use; index:* = byte/half passed to CZAnim::Get* table lookups; ptr = dereferenced; u8/u16/u32 = integer of unknown signedness), roles that read (R) / write (W), signedness evidence, bit operations (mask/shift) and other evidence. `?` before an offset = only seen through a may-alias base. Header bytes (+0..+3) omitted unless written by a non-standard path. Callee-written = record address passed to a callee (zrdr_find*, CPnt3D methods, strcpy...).

### QUAD_ALIGN

- size: n/a; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **n/a (header-only)**
- proposed: `_zanim_cmd_hdr (no new type)` (cluster `header-only`)
- notes: Inserted by SeqAppendCmd/AnimLoadQuadAlignCmd as 4..15-byte padding before a quad_align record; tick returns 1; body is padding only.
- typeable functions: `0x1bfe80 zAnimQuadAlignTick`

### IF

- size: 8; data_size written: [8]; variable tail: AnimParseExpression; timeless set: True; quad_align set: False; grade: **B**
- proposed: `_zanim_if_cmd (provisional)` (cluster `if-family-8`)
- notes: 8-byte fixed part: hdr + u8 m_depth(+4) + 3 pad. IF/ELSEIF append an inline expression stream (AnimParseExpression realloc) read by CZAnimExpression::ProcExpr after CmdNext(8). zAnimIfTick reads +4 of following ELSE/ELSEIF/ENDIF records through the ZAnim cursor (ZAnim+0x3c ->+8), so all four share the layout.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1b09e0 zAnimLoad_If`, `0x1b8f20 zAnimIfTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ?+4 | 1 | u8 |  | parse |  |  |  | W:zAnimLoad_If@0x1b0a78 |

### ELSEIF

- size: 8; data_size written: [8]; variable tail: AnimParseExpression; timeless set: True; quad_align set: False; grade: **B**
- proposed: `_zanim_if_cmd (provisional)` (cluster `if-family-8`)
- notes: 8-byte fixed part: hdr + u8 m_depth(+4) + 3 pad. IF/ELSEIF append an inline expression stream (AnimParseExpression realloc) read by CZAnimExpression::ProcExpr after CmdNext(8). zAnimIfTick reads +4 of following ELSE/ELSEIF/ENDIF records through the ZAnim cursor (ZAnim+0x3c ->+8), so all four share the layout.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1b0940 zAnimLoad_ElseIf`, `0x1b8e70 zAnimGoToEndIf`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ?+4 | 1 | u8 |  | parse |  |  |  | W:zAnimLoad_ElseIf@0x1b09c4 |

### ELSE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_if_cmd (provisional)` (cluster `if-family-8`)
- notes: 8-byte fixed part: hdr + u8 m_depth(+4) + 3 pad. IF/ELSEIF append an inline expression stream (AnimParseExpression realloc) read by CZAnimExpression::ProcExpr after CmdNext(8). zAnimIfTick reads +4 of following ELSE/ELSEIF/ENDIF records through the ZAnim cursor (ZAnim+0x3c ->+8), so all four share the layout.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1b08c0 zAnimLoad_Else`, `0x1b8e70 zAnimGoToEndIf`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ?+4 | 1 | u8 |  | parse |  |  |  | W:zAnimLoad_Else@0x1b092c |

### ENDIF

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_if_cmd (provisional)` (cluster `if-family-8`)
- notes: 8-byte fixed part: hdr + u8 m_depth(+4) + 3 pad. IF/ELSEIF append an inline expression stream (AnimParseExpression realloc) read by CZAnimExpression::ProcExpr after CmdNext(8). zAnimIfTick reads +4 of following ELSE/ELSEIF/ENDIF records through the ZAnim cursor (ZAnim+0x3c ->+8), so all four share the layout.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1b0830 zAnimLoad_EndIf`, `0x1b8e50 zAnimEndIfTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ?+4 | 1 | u8 |  | parse |  |  |  | W:zAnimLoad_EndIf@0x1b08a0 |

### NODE_ACTIVE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_node_state_cmd (provisional)` (cluster `u16-state-u16-node-8`)
- notes: Identical 8-byte layout: hdr + u16 state(+4, compared with 0/1/2) + u16 node_ref index(+6, CZAnim::GetNode arg).
- typeable functions: `0x1b06e0 zAnimLoadNodeActive`, `0x1b8c50 zAnimNodeActiveTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | tick | parse | unsigned-load |  | cmpeq c:0x1 c:0x2 | W:zAnimLoadNodeActive@0x1b07bc W:zAnimLoadNodeActive@0x1b07e4 W:zAnimLoadNodeActive@0x1b07ec (+1) |
| +6 | 2 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadNodeActive@0x1b0784 R:zAnimNodeActiveTick@0x1b8c60 |

### NODE_RENDERED

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_node_rendered_cmd (provisional)` (cluster `u16-node-8`)
- notes: hdr + u16 node_ref index(+4) + 2 pad (alloc 8).
- alignment/tail padding (not accessed): +6..+8
- typeable functions: `0x1b0620 zAnimLoadNodeRendered`, `0x1b8c00 zAnimNodeRenderedTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadNodeRendered@0x1b06c0 R:zAnimNodeRenderedTick@0x1b8c0c |

### RANGE_TEST

- size: 40; data_size written: [40]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_range_test_cmd (provisional)`
- notes: 40 bytes: hdr, u32 flags(+4), u8 node_ref(+8), u8 node_ref(+9), pad, CPnt3D(+12), CPnt3D(+24), f32(+36).
- alignment/tail padding (not accessed): +10..+12
- typeable functions: `0x1b00c0 zAnimLoadRangeTest`, `0x1b88d0 zAnimRangeTestTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | parse,tick | parse |  | andi:0x1 andi:0x10 andi:0x100 andi:0x2 | cmpeq fld | R:zAnimLoadRangeTest@0x1b0158 W:zAnimLoadRangeTest@0x1b0170 R:zAnimLoadRangeTest@0x1b01ac (+28) |
| +8 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadRangeTest@0x1b0188 R:zAnimRangeTestTick@0x1b89b8 |
| +9 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadRangeTest@0x1b0238 R:zAnimRangeTestTick@0x1b8a70 |
| +36 | 4 | f32 | parse,tick | parse |  |  | float | R:zAnimLoadRangeTest@0x1b05d0 W:zAnimLoadRangeTest@0x1b05e0 R:zAnimRangeTestTick@0x1b8af8 (+5) |

Callee-written/passed: +12 Add(CPnt3D*, 12 B) in zAnimRangeTestTick; +12 zrdr_findreal(f32*, 12 B) in zAnimLoadRangeTest; +24 Add(CPnt3D*, 12 B) in zAnimRangeTestTick; +24 zrdr_findreal(f32*, 12 B) in zAnimLoadRangeTest; +36 zrdr_findreal(f32*, 4 B) in zAnimLoadRangeTest

### RANDOM_WEIGHT

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_random_weight_cmd (provisional)` (cluster `f32-8`)
- notes: hdr + f32 weight(+4, default 0.5).
- typeable functions: `0x1aff50 zAnimLoadRandomWeight`, `0x1b8730 zAnimRandomWeightTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | f32 | tick | parse |  |  | float c:0x3f000000 | W:zAnimLoadRandomWeight@0x1b0098 W:zAnimLoadRandomWeight@0x1b00a0 R:zAnimRandomWeightTick@0x1b874c |

### FAIL

- size: 4; data_size written: [4]; variable tail: no; timeless set: True; quad_align set: False; grade: **n/a (header-only)**
- proposed: `_zanim_cmd_hdr (no new type)` (cluster `header-only`)
- notes: Parser allocates exactly 4 bytes (data_size 4).
- typeable functions: `0x1afef0 zAnimLoadFail`, `0x1b8720 zAnimFailTick`

### ANIM_HEALTH

- size: 12; data_size written: [12]; variable tail: _realloc; timeless set: False; quad_align set: False; grade: **B**
- proposed: `_zanim_anim_health_cmd (provisional)`
- notes: 12-byte fixed (hdr, u32 flags +4, f32 +8) + f32 array tail appended 4 bytes at a time (realloc+memcpy 4).
- typeable functions: `0x1afbd0 zAnimLoadAnimHealthTest`, `0x1b8840 zAnimHealthTestTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | parse,tick | parse |  | andi:0x1 ori:0x1 | cmpeq fld | R:zAnimLoadAnimHealthTest@0x1afdb8 W:zAnimLoadAnimHealthTest@0x1afdc4 R:zAnimHealthTestTick@0x1b885c |
| +8 | 4 | f32 | tick | parse |  |  | float | W:zAnimLoadAnimHealthTest@0x1afd24 R:zAnimHealthTestTick@0x1b886c R:zAnimHealthTestTick@0x1b889c |
| +12 | 4 | f32 | tick |  |  |  | float | R:zAnimHealthTestTick@0x1b8880 |

### ANIM_LOD

- size: 8; data_size written: [8]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `_zanim_anim_lod_cmd (provisional)`
- notes: 8 bytes: hdr, u8 flags(+4), u8 lod(+5).
- alignment/tail padding (not accessed): +6..+8
- typeable functions: `0x1af650 zAnimLoadAnimLODTest`, `0x1b8790 zAnimLODTestTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | tick | parse | unsigned-load | andi:0x1 andi:0x10 andi:0x2 andi:0x4 | cmpeq c:0x1 c:0x10 c:0x2 c:0x4 | W:zAnimLoadAnimLODTest@0x1af6c0 W:zAnimLoadAnimLODTest@0x1af740 W:zAnimLoadAnimLODTest@0x1af7c8 (+5) |
| +5 | 1 | u8 | tick | parse | signed-cmp,unsigned-cmp,unsigned-load | xor:None | cmp:slt cmp:sltiu c:0x0 c:0x1 c:0x2 | W:zAnimLoadAnimLODTest@0x1afa6c W:zAnimLoadAnimLODTest@0x1afaf0 W:zAnimLoadAnimLODTest@0x1afb74 (+5) |

### LOOP

- size: 12; data_size written: [12]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_loop_cmd (provisional)`
- notes: 12 bytes: hdr, u32 flags(+4), f32 count/time(+8, -1.0 default, also compared as word with -1).
- typeable functions: `0x1b18d0 zAnimLoadLoop`, `0x1b9750 zAnimLoopTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | parse,tick | parse |  | andi:0x1 andi:0x2 ori:0x1 ori:0x2 | cmpeq fld | R:zAnimLoadLoop@0x1b1954 W:zAnimLoadLoop@0x1b1964 R:zAnimLoadLoop@0x1b19ac (+2) |
| +8 | 4 | f32 | tick | parse |  |  | cmpeq float c:0xbf800000 c:0xffffffff | W:zAnimLoadLoop@0x1b1968 W:zAnimLoadLoop@0x1b1994 W:zAnimLoadLoop@0x1b19d4 (+2) |

Callee-written/passed: +8 zrdr_findreal(f32*, 4 B) in zAnimLoadLoop

### WAIT

- size: 12; data_size written: [12]; variable tail: _realloc; timeless set: False; quad_align set: False; grade: **B**
- proposed: `_zanim_wait_cmd (provisional)`
- notes: 12-byte fixed: hdr, u16 flags(+4), s16 runtime counter(+6, written by begin/tick), f32 time(+8) + optional f32 tail (realloc) indexed by begin/tick.
- typeable functions: `0x1b1230 zAnimLoadWait`, `0x1b96c0 zAnimWaitBegin`, `0x1b95c0 zAnimWaitTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | begin,parse,tick | parse | unsigned-load | andi:0x10 andi:0x2 andi:0x20 andi:0x4 | arg:rand(a0) cmpeq fld | R:zAnimLoadWait@0x1b1378 W:zAnimLoadWait@0x1b1384 R:zAnimLoadWait@0x1b1388 (+24) |
| +6 | 2 | u16 | tick | begin,tick | signed-cmp,unsigned-load |  | cmp:slt c:0x0 | W:zAnimWaitBegin@0x1b96e0 R:zAnimWaitTick@0x1b9678 W:zAnimWaitTick@0x1b9684 (+1) |
| +8 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadWait@0x1b1758 W:zAnimWaitBegin@0x1b9730 R:zAnimWaitTick@0x1b9614 |

Indexed/tail accesses (base offset + variable): +8/w4/f32(begin,parse,tick), +12/w4/f32(begin)

### OBJECT_BLENDMODE

- size: 20; data_size written: [20]; variable tail: GetBlendValueSequence; timeless set: True; quad_align set: False; grade: **B**
- proposed: `_zanim_object_blendmode_cmd (provisional)` (cluster `blend-tail`)
- notes: 20-byte fixed: hdr, u16 flags(+4), u8 node_ref(+6), u8 blend bitfields(+7, 2-bit fields), f32(+8), s16(+12), s16(+14), f32(+16) + GetBlendValueSequence tail (likely _zanim_blend_fix[] - type missing).
- typeable functions: `0x1b3560 zAnimLoadObjectBlendMode`, `0x1bd590 zAnimObjectBlendModeTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | parse,tick | parse | unsigned-load | andi:0x1 andi:0x2 andi:0x4 andi:0x8 | cmpeq c:0x0 fld | W:zAnimLoadObjectBlendMode@0x1b3604 R:zAnimLoadObjectBlendMode@0x1b3620 W:zAnimLoadObjectBlendMode@0x1b3628 (+6) |
| +6 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadObjectBlendMode@0x1b35fc R:zAnimObjectBlendModeTick@0x1bd5d0 |
| +7 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xffffff3f and:0xffffffcf and:0xfffffff3 and:0xfffffffc | arg:GetBlendSequenceValue(t2) arg:SetBlendMode(t2) arg:zrdr_findtag(a2) arg:zrdr_findtag(a3) arg:zrdr_findtag(t0) | R:zAnimLoadObjectBlendMode@0x1b36b0 W:zAnimLoadObjectBlendMode@0x1b36d8 R:zAnimLoadObjectBlendMode@0x1b36e0 (+6) |
| +8 | 4 | f32 | tick | parse |  |  | float | W:zAnimLoadObjectBlendMode@0x1b3738 R:zAnimObjectBlendModeTick@0x1bd684 |
| +12 | 2 | u16 | tick |  | signed-load |  | arg:GetBlendSequenceValue(a2) | R:zAnimObjectBlendModeTick@0x1bd760 |
| +14 | 2 | u16 | tick | parse | signed-load |  | fld | W:zAnimLoadObjectBlendMode@0x1b3764 R:zAnimObjectBlendModeTick@0x1bd754 |
| +16 | 4 | f32 | tick | parse |  |  | float c:0x0 | W:zAnimLoadObjectBlendMode@0x1b3614 R:zAnimObjectBlendModeTick@0x1bd600 |

### OBJECT_ACTIVE_STATE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_node_state_cmd (provisional)` (cluster `u16-state-u16-node-8`)
- notes: Identical 8-byte layout: hdr + u16 state(+4, compared with 0/1/2) + u16 node_ref index(+6, CZAnim::GetNode arg).
- typeable functions: `0x1b3420 zAnimLoadObjectActiveState`, `0x1bd510 zAnimObjectActiveStateTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | tick | parse | unsigned-load |  | cmpeq c:0x0 c:0x1 | W:zAnimLoadObjectActiveState@0x1b34fc W:zAnimLoadObjectActiveState@0x1b351c R:zAnimObjectActiveStateTick@0x1bd53c |
| +6 | 2 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadObjectActiveState@0x1b34c4 R:zAnimObjectActiveStateTick@0x1bd520 |

### OBJECT_TRANSLATE_STATE

- size: 20; data_size written: [20]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_object_xform_state_cmd (provisional)` (cluster `u16-u8-u8-pnt3d-20`)
- notes: Identical 20-byte layout: hdr, u16 flags(+4), u8 node_ref(+6), u8 node_ref(+7), CPnt3D(+8).
- typeable functions: `0x1b31c0 zAnimLoadObjectTranslateState`, `0x1bd320 zAnimObjectTranslateStateTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | parse,tick | parse | unsigned-load | andi:0x1 andi:0x10 andi:0x2 andi:0x20 | cmpeq fld | R:zAnimLoadObjectTranslateState@0x1b32dc W:zAnimLoadObjectTranslateState@0x1b32e4 R:zAnimLoadObjectTranslateState@0x1b32fc (+12) |
| +6 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadObjectTranslateState@0x1b3278 R:zAnimObjectTranslateStateTick@0x1bd354 |
| +7 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectTranslateState@0x1b3288 W:zAnimLoadObjectTranslateState@0x1b32b8 R:zAnimObjectTranslateStateTick@0x1bd360 |

Callee-written/passed: +8 Add(CPnt3D*, 12 B) in zAnimObjectTranslateStateTick; +8 zrdr_findreal(f32*, 12 B) in zAnimLoadObjectTranslateState

### OBJECT_ROTATE_STATE

- size: 20; data_size written: [20]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_object_xform_state_cmd (provisional)` (cluster `u16-u8-u8-pnt3d-20`)
- notes: Identical 20-byte layout: hdr, u16 flags(+4), u8 node_ref(+6), u8 node_ref(+7), CPnt3D(+8).
- typeable functions: `0x1b2fb0 zAnimLoadObjectRotateState`, `0x1bd1f0 zAnimObjectRotateStateTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | parse,tick | parse | unsigned-load | andi:0x1 andi:0x2 ori:0x1 ori:0x2 | cmpeq fld | R:zAnimLoadObjectRotateState@0x1b30cc W:zAnimLoadObjectRotateState@0x1b30e0 R:zAnimLoadObjectRotateState@0x1b313c (+3) |
| +6 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadObjectRotateState@0x1b3050 R:zAnimObjectRotateStateTick@0x1bd220 |
| +7 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectRotateState@0x1b3060 W:zAnimLoadObjectRotateState@0x1b3090 R:zAnimObjectRotateStateTick@0x1bd22c |
| +8 | 4 | f32 | parse | parse |  |  | float | R:zAnimLoadObjectRotateState@0x1b30e4 W:zAnimLoadObjectRotateState@0x1b30ec R:zAnimLoadObjectRotateState@0x1b3154 (+1) |
| +12 | 4 | f32 | parse | parse |  |  | float | R:zAnimLoadObjectRotateState@0x1b30f0 W:zAnimLoadObjectRotateState@0x1b30f8 R:zAnimLoadObjectRotateState@0x1b3160 (+1) |
| +16 | 4 | f32 | parse | parse |  |  | float | R:zAnimLoadObjectRotateState@0x1b30fc W:zAnimLoadObjectRotateState@0x1b3104 R:zAnimLoadObjectRotateState@0x1b316c (+1) |

Callee-written/passed: +8 Add(CPnt3D*, 12 B) in zAnimObjectRotateStateTick; +8 zrdr_findreal(f32*, 12 B) in zAnimLoadObjectRotateState

### OBJECT_MOTION

- size: 124; data_size written: [124]; variable tail: _realloc; timeless set: False; quad_align set: False; grade: **B**
- proposed: `_zanim_object_motion_cmd (provisional)`
- notes: 124-byte fixed + realloc tail (GetTranslation keys). Large float/CPnt3D body; CPnt3D at +36/+48/+60/+72/+84/+100 used by CPnt3D helpers.
- unexplained gaps: +28..+29
- typeable functions: `0x1ac7d0 zAnimLoadObjectMotion`, `0x1bc540 zAnimObjectMotionBegin`, `0x1bb330 zAnimObjectMotionTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,parse,tick | parse |  | and:0x10000 and:0x20000 andi:0x1 andi:0x10 | arg:rand(a0) cmpeq fld | R:zAnimLoadObjectMotion@0x1ac8e8 W:zAnimLoadObjectMotion@0x1ac8f4 R:zAnimLoadObjectMotion@0x1ac93c (+71) |
| +8 | 1 | index:node_ref | begin,tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadObjectMotion@0x1ac880 R:zAnimObjectMotionBegin@0x1bc584 R:zAnimObjectMotionTick@0x1bb398 |
| +9 | 1 | index:node_ref | begin | parse | unsigned-load |  | arg:GetNode(a1) cmpeq c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectMotion@0x1ac8c0 W:zAnimLoadObjectMotion@0x1ac8c4 R:zAnimObjectMotionBegin@0x1bcaa4 (+1) |
| +10 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) arg:InvExp(a1) cmpeq c:0x0 ret:AddName | W:zAnimLoadObjectMotion@0x1ad6e0 W:zAnimLoadObjectMotion@0x1ad6e4 R:zAnimObjectMotionTick@0x1bc06c |
| +11 | 1 | index:sound_ref | tick | parse | unsigned-load |  | arg:GetSoundRef(a1) arg:InvExp(a1) cmpeq ret:AddName | W:zAnimLoadObjectMotion@0x1ad4dc W:zAnimLoadObjectMotion@0x1ad5e4 R:zAnimObjectMotionTick@0x1bc0cc |
| +12 | 4 | f32 | tick | parse |  |  | float c:0xbf800000 | W:zAnimLoadObjectMotion@0x1ad668 W:zAnimLoadObjectMotion@0x1ad670 R:zAnimObjectMotionTick@0x1bc10c |
| +16 | 4 | f32 | begin,parse,tick | parse |  |  | float c:0x3f800000 | W:zAnimLoadObjectMotion@0x1ad2f8 W:zAnimLoadObjectMotion@0x1ad340 R:zAnimLoadObjectMotion@0x1ad390 (+3) |
| +20 | 4 | f32 | parse,tick | parse |  |  | float | R:zAnimLoadObjectMotion@0x1ad364 W:zAnimLoadObjectMotion@0x1ad384 W:zAnimLoadObjectMotion@0x1ad3ac (+1) |
| +24 | 4 | f32 | begin | parse |  |  | arg:Scale(f12) c:0x3f800000 | W:zAnimLoadObjectMotion@0x1ad190 R:zAnimObjectMotionBegin@0x1bd038 R:zAnimObjectMotionBegin@0x1bd0a0 |
| +29 | 1 | u8 | parse,tick | parse | signed-cmp,signed-load |  | cmp:slt cmpeq | R:zAnimLoadObjectMotion@0x1adb00 R:zAnimLoadObjectMotion@0x1adb98 W:zAnimLoadObjectMotion@0x1adba4 (+2) |
| +30 | 2 | u16 | tick | parse | signed-cmp,signed-load |  | cmp:blez fld | W:zAnimLoadObjectMotion@0x1adb18 R:zAnimObjectMotionTick@0x1bb83c R:zAnimObjectMotionTick@0x1bbc1c |
| +32 | 2 | u16 | begin | parse | signed-load |  | fld | W:zAnimLoadObjectMotion@0x1acf08 W:zAnimLoadObjectMotion@0x1acfc4 R:zAnimObjectMotionBegin@0x1bc688 (+1) |
| +34 | 2 | u16 | begin | parse | signed-load |  | fld | W:zAnimLoadObjectMotion@0x1ad0c8 R:zAnimObjectMotionBegin@0x1bcc6c |
| +36 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotion@0x1ace9c W:zAnimObjectMotionBegin@0x1bc734 W:zAnimObjectMotionBegin@0x1bc7b8 (+6) |
| +40 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotion@0x1acea4 W:zAnimObjectMotionBegin@0x1bc73c W:zAnimObjectMotionBegin@0x1bc7c0 (+6) |
| +44 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotion@0x1aceac W:zAnimObjectMotionBegin@0x1bc744 W:zAnimObjectMotionBegin@0x1bc7c8 (+6) |
| +48 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotion@0x1aced8 W:zAnimObjectMotionBegin@0x1bc770 W:zAnimObjectMotionBegin@0x1bc7f4 (+6) |
| +52 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotion@0x1acee0 W:zAnimObjectMotionBegin@0x1bc778 W:zAnimObjectMotionBegin@0x1bc7fc (+6) |
| +56 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotion@0x1acee8 W:zAnimObjectMotionBegin@0x1bc784 W:zAnimObjectMotionBegin@0x1bc808 (+6) |
| +60 | 4 | f32 | tick | begin,tick |  |  | float | W:zAnimObjectMotionBegin@0x1bd088 W:zAnimObjectMotionBegin@0x1bd0f0 R:zAnimObjectMotionTick@0x1bb81c (+8) |
| +64 | 4 | f32 | tick | begin,tick |  |  | float | W:zAnimObjectMotionBegin@0x1bd090 W:zAnimObjectMotionBegin@0x1bd0f8 R:zAnimObjectMotionTick@0x1bb660 (+11) |
| +68 | 4 | f32 | tick | begin,tick |  |  | float | W:zAnimObjectMotionBegin@0x1bd09c W:zAnimObjectMotionBegin@0x1bd100 R:zAnimObjectMotionTick@0x1bb824 (+8) |
| +72 | 4 | f32 | tick |  |  |  | float | R:zAnimObjectMotionTick@0x1bb9b0 R:zAnimObjectMotionTick@0x1bbe28 R:zAnimObjectMotionTick@0x1bc1c8 |
| +76 | 4 | f32 | begin,tick | begin,tick |  |  | float | R:zAnimObjectMotionBegin@0x1bcee8 W:zAnimObjectMotionBegin@0x1bcef4 R:zAnimObjectMotionTick@0x1bb9b4 (+4) |
| +80 | 4 | f32 | tick |  |  |  | float | R:zAnimObjectMotionTick@0x1bb9b8 R:zAnimObjectMotionTick@0x1bbe30 R:zAnimObjectMotionTick@0x1bc1dc |
| +84 | 4 | f32 | begin,parse | parse |  |  | float fld | W:zAnimLoadObjectMotion@0x1acde0 R:zAnimLoadObjectMotion@0x1ace04 W:zAnimLoadObjectMotion@0x1ace10 (+4) |
| +88 | 4 | f32 | begin | parse |  |  | c:0x0 | W:zAnimLoadObjectMotion@0x1ace14 W:zAnimLoadObjectMotion@0x1ace30 R:zAnimObjectMotionBegin@0x1bcacc (+1) |
| +92 | 4 | f32 | begin,parse | parse |  |  | float fld | W:zAnimLoadObjectMotion@0x1acdf8 R:zAnimLoadObjectMotion@0x1ace1c W:zAnimLoadObjectMotion@0x1ace28 (+4) |
| +96 | 4 | f32 | tick | parse |  |  | arg:Scale(f12) float c:0x3e99999a | W:zAnimLoadObjectMotion@0x1ad418 R:zAnimObjectMotionTick@0x1bb948 R:zAnimObjectMotionTick@0x1bbcf0 |
| +112 | 2 | u16 | begin,tick | parse | signed-load |  | fld | W:zAnimLoadObjectMotion@0x1ae300 R:zAnimObjectMotionBegin@0x1bcf40 R:zAnimObjectMotionTick@0x1bc2c0 (+1) |
| +114 | 2 | u16 | begin,tick | parse | signed-load |  | fld | W:zAnimLoadObjectMotion@0x1adf24 R:zAnimObjectMotionBegin@0x1bcf08 R:zAnimObjectMotionTick@0x1bc234 |
| +116 | 2 | u16 | begin,tick | parse | signed-load |  | fld | W:zAnimLoadObjectMotion@0x1ae94c R:zAnimObjectMotionBegin@0x1bd118 R:zAnimObjectMotionTick@0x1bc3b8 |
| +118 | 2 | u16 | begin | parse | signed-cmp,signed-load |  | cmp:blez fld | W:zAnimLoadObjectMotion@0x1ad270 R:zAnimObjectMotionBegin@0x1bc5b0 |
| +120 | 4 | f32 | parse,tick | begin,parse |  |  | float c:0x0 c:0x3a83126f c:0x3f800000 | R:zAnimLoadObjectMotion@0x1ac8f8 W:zAnimLoadObjectMotion@0x1ac918 W:zAnimLoadObjectMotion@0x1ac920 (+2) |

Callee-written/passed: +0 GetTranslation(?) in zAnimLoadObjectMotion; +20 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectMotion; +24 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectMotion; +36 memcpy(bytes, 12 B) in zAnimObjectMotionBegin; +48 memcpy(bytes, 12 B) in zAnimObjectMotionBegin; +60 Add(CPnt3D*, 12 B) in zAnimObjectMotionBegin,zAnimObjectMotionTick; +60 Normalize(CPnt3D*, 12 B) in zAnimObjectMotionTick; +60 Reflect(CPnt3D*, 12 B) in zAnimObjectMotionTick; +60 Scale(CPnt3D*, 12 B) in zAnimObjectMotionTick; +60 memcpy(bytes, 12 B) in zAnimObjectMotionBegin; +72 Scale(CPnt3D*, 12 B) in zAnimObjectMotionTick; +72 memcpy(bytes, 12 B) in zAnimObjectMotionBegin; +84 Scale(CPnt3D*, 12 B) in zAnimLoadObjectMotion; +84 zAnimGetDirectionFromAzimuthZenith(CPnt3D*, 12 B) in zAnimObjectMotionBegin; +96 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectMotion; +100 Add(CPnt3D*, 12 B) in zAnimObjectMotionTick; +100 GetRotation(CPnt3D*, 12 B) in zAnimObjectMotionBegin; +100 SetRotation(CPnt3D*, 12 B) in zAnimObjectMotionTick; +120 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectMotion

Indexed/tail accesses (base offset + variable): +0/w1/u8(tick), +0/w2/u16(tick), +0/w4/f32(begin,tick), +2/w2/u16(tick), +4/w4/f32(begin,tick), +8/w4/f32(begin,tick), +12/w1/f32(tick), +12/w2/f32(tick), +12/w4/f32(begin,tick), +14/w2/u16(tick), +16/w4/f32(begin,tick), +20/w4/f32(begin,tick), +24/w1/u8(tick), +24/w2/u16(tick), +24/w4/f32(begin,tick), +26/w2/u16(tick) ...

### OBJECT_MOTION_FROM_TO

- size: 128; data_size written: [128]; variable tail: _realloc; timeless set: False; quad_align set: False; grade: **B**
- proposed: `_zanim_object_motion_from_to_cmd (provisional) + CZAnimFromToAcc (missing, 56 bytes)`
- notes: 128-byte fixed; when flags(+4) & 0x6000 the parser appends a 56-byte CZAnimFromToAcc (realloc+memcpy 56) at +128, used via Tick__15CZAnimFromToAcc / ComputeRunTime (this = rec+128).
- typeable functions: `0x1b1b90 zAnimLoadObjectMotionFromTo`, `0x1ba630 zAnimObjectMotionFromToBegin`, `0x1ba2d0 zAnimObjectMotionFromToTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | begin,parse,tick | parse | unsigned-load | andi:0x1 andi:0x100 andi:0x1000 andi:0x1070 | cmpeq fld | R:zAnimLoadObjectMotionFromTo@0x1b1cac W:zAnimLoadObjectMotionFromTo@0x1b1cbc R:zAnimLoadObjectMotionFromTo@0x1b1d8c (+54) |
| +6 | 1 | index:node_ref | begin,tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadObjectMotionFromTo@0x1b1c74 R:zAnimObjectMotionFromToBegin@0x1ba660 R:zAnimObjectMotionFromToTick@0x1ba2fc |
| +7 | 1 | index:node_ref | begin | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectMotionFromTo@0x1b2338 W:zAnimLoadObjectMotionFromTo@0x1b2370 R:zAnimObjectMotionFromToBegin@0x1ba6b4 |
| +8 | 1 | index:node_ref | begin | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectMotionFromTo@0x1b2458 W:zAnimLoadObjectMotionFromTo@0x1b2490 R:zAnimObjectMotionFromToBegin@0x1ba794 |
| +9 | 1 | index:name | begin | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadObjectMotionFromTo@0x1b25e4 R:zAnimObjectMotionFromToBegin@0x1ba838 R:zAnimObjectMotionFromToBegin@0x1ba928 |
| +10 | 1 | index:name | begin | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadObjectMotionFromTo@0x1b2640 R:zAnimObjectMotionFromToBegin@0x1ba884 R:zAnimObjectMotionFromToBegin@0x1ba974 |
| +11 | 1 | index:name | begin | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadObjectMotionFromTo@0x1b269c R:zAnimObjectMotionFromToBegin@0x1ba8d0 R:zAnimObjectMotionFromToBegin@0x1ba9c0 |
| +12 | 4 | f32 |  | parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2828 |
| +16 | 4 | f32 |  | parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2830 |
| +20 | 4 | f32 |  | parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2838 |
| +24 | 4 | f32 | begin,tick | parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b28a4 R:zAnimObjectMotionFromToBegin@0x1bad18 R:zAnimObjectMotionFromToTick@0x1ba3f8 |
| +28 | 4 | f32 | begin,tick | parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b28ac R:zAnimObjectMotionFromToBegin@0x1bad20 R:zAnimObjectMotionFromToTick@0x1ba400 |
| +32 | 4 | f32 | begin,tick | parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b28b4 R:zAnimObjectMotionFromToBegin@0x1bad24 R:zAnimObjectMotionFromToTick@0x1ba404 |
| +36 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2914 W:zAnimObjectMotionFromToBegin@0x1badb8 |
| +40 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b291c W:zAnimObjectMotionFromToBegin@0x1badc0 |
| +44 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2924 W:zAnimObjectMotionFromToBegin@0x1badc8 |
| +48 | 4 | f32 | begin,parse | begin |  |  | arg:SetPosition(f12) float | R:ComputeRunTime@0x1bb170 R:ComputeRunTime@0x1bb1b4 R:ComputeRunTime@0x1bb200 (+9) |
| +52 | 4 | f32 | begin,parse | begin |  |  | arg:SetPosition(f13) float | R:ComputeRunTime@0x1bb168 R:ComputeRunTime@0x1bb1f4 R:ComputeRunTime@0x1bb2ec (+7) |
| +56 | 4 | f32 | begin,parse | begin |  |  | arg:SetPosition(f14) float | R:ComputeRunTime@0x1bb190 R:ComputeRunTime@0x1bb220 W:zAnimObjectMotionFromToBegin@0x1ba6f4 (+5) |
| +60 | 4 | f32 | begin,parse,tick | begin |  |  | arg:SetPosition(f12) float | R:ComputeRunTime@0x1bb174 R:ComputeRunTime@0x1bb1a4 R:ComputeRunTime@0x1bb208 (+20) |
| +64 | 4 | f32 | begin,parse,tick | begin |  |  | arg:SetPosition(f13) float | R:ComputeRunTime@0x1bb194 R:ComputeRunTime@0x1bb1a8 R:ComputeRunTime@0x1bb224 (+18) |
| +68 | 4 | f32 | begin,parse,tick | begin,parse |  |  | arg:SetPosition(f14) float | W:ComputeRunTime@0x1bb18c R:ComputeRunTime@0x1bb1ac W:ComputeRunTime@0x1bb21c (+18) |
| +72 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadObjectMotionFromTo@0x1b2708 W:ComputeRunTime@0x1bb304 W:ComputeRunTime@0x1bb308 (+11) |
| +76 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadObjectMotionFromTo@0x1b2710 W:ComputeRunTime@0x1bb1a0 R:ComputeRunTime@0x1bb1b0 (+17) |
| +80 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadObjectMotionFromTo@0x1b2718 W:ComputeRunTime@0x1bb18c R:ComputeRunTime@0x1bb1ac (+9) |
| +84 | 4 | f32 | begin | begin,parse |  |  | float | W:ComputeRunTime@0x1bb304 W:ComputeRunTime@0x1bb308 R:zAnimObjectMotionFromToBegin@0x1baacc (+2) |
| +88 | 4 | f32 | begin,parse,tick | begin,parse |  |  | float c:0x3f800000 | W:ComputeRunTime@0x1bb1a0 R:ComputeRunTime@0x1bb1b0 W:ComputeRunTime@0x1bb230 (+12) |
| +92 | 4 | f32 | begin,tick | parse |  |  | float c:0x3f800000 | W:zAnimLoadObjectMotionFromTo@0x1b2974 W:zAnimLoadObjectMotionFromTo@0x1b2a68 W:zAnimLoadObjectMotionFromTo@0x1b2bb4 (+2) |
| +96 | 4 | f32 | begin,tick | parse |  |  | float c:0x3f800000 | W:zAnimLoadObjectMotionFromTo@0x1b2970 W:zAnimLoadObjectMotionFromTo@0x1b2ad0 W:zAnimLoadObjectMotionFromTo@0x1b2c18 (+2) |
| +100 | 4 | f32 | begin,tick | parse |  |  | float c:0x3f800000 | W:zAnimLoadObjectMotionFromTo@0x1b2c60 W:zAnimLoadObjectMotionFromTo@0x1b2ce8 W:zAnimLoadObjectMotionFromTo@0x1b2e34 (+4) |
| +104 | 4 | f32 | begin,tick | parse |  |  | float c:0x3f800000 | W:zAnimLoadObjectMotionFromTo@0x1b2c58 W:zAnimLoadObjectMotionFromTo@0x1b2d4c W:zAnimLoadObjectMotionFromTo@0x1b2e98 (+4) |
| +108 | 4 | f32 | begin,tick | parse |  |  | float c:0x3f800000 | W:zAnimLoadObjectMotionFromTo@0x1b2c54 W:zAnimLoadObjectMotionFromTo@0x1b2db4 W:zAnimLoadObjectMotionFromTo@0x1b2efc (+4) |
| +112 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2f60 W:zAnimObjectMotionFromToBegin@0x1baed8 |
| +116 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2f68 W:zAnimObjectMotionFromToBegin@0x1baee0 |
| +120 | 4 | f32 |  | begin,parse |  |  |  | W:zAnimLoadObjectMotionFromTo@0x1b2f70 W:zAnimObjectMotionFromToBegin@0x1baee8 |
| +124 | 4 | f32 | begin,parse,tick | begin,parse |  |  | float c:0x3a83126f c:0x3f800000 | W:zAnimLoadObjectMotionFromTo@0x1b1cc4 R:zAnimLoadObjectMotionFromTo@0x1b1ce4 W:zAnimLoadObjectMotionFromTo@0x1b1d08 (+10) |
| +128 | 4 | f32 | begin |  |  |  | float | R:ComputeRunTime@0x1bb170 R:ComputeRunTime@0x1bb1b4 R:ComputeRunTime@0x1bb200 (+2) |
| +132 | 4 | f32 | begin,tick |  |  |  | float | R:ComputeRunTime@0x1bb168 R:ComputeRunTime@0x1bb1f4 R:ComputeRunTime@0x1bb2ec (+3) |
| +136 | 4 | f32 | begin |  |  |  | float | R:ComputeRunTime@0x1bb190 R:ComputeRunTime@0x1bb220 |
| +140 | 4 | f32 | begin,tick |  |  |  | float | R:ComputeRunTime@0x1bb174 R:ComputeRunTime@0x1bb1a4 R:ComputeRunTime@0x1bb208 (+2) |
| +144 | 4 | f32 | begin,tick |  |  |  | float | R:ComputeRunTime@0x1bb194 R:ComputeRunTime@0x1bb1a8 R:ComputeRunTime@0x1bb224 (+2) |
| +148 | 4 | f32 | begin,tick | begin |  |  | float | W:ComputeRunTime@0x1bb18c R:ComputeRunTime@0x1bb1ac W:ComputeRunTime@0x1bb21c (+4) |
| +152 | 4 | f32 | begin,tick | begin |  |  | float | W:ComputeRunTime@0x1bb304 W:ComputeRunTime@0x1bb308 R:zAnimObjectMotionFromToBegin@0x1bac68 (+2) |
| +156 | 4 | f32 | begin | begin |  |  | float | W:ComputeRunTime@0x1bb1a0 R:ComputeRunTime@0x1bb1b0 W:ComputeRunTime@0x1bb230 (+3) |
| +160 | 4 | f32 | tick | begin,tick |  |  | float c:0x0 | W:zAnimObjectMotionFromToBegin@0x1bac40 R:Tick@0x1baf68 W:Tick@0x1baf84 (+6) |
| +164 | 4 | f32 | tick | begin,tick |  |  | arg:Scale(f12) float fld | W:zAnimObjectMotionFromToBegin@0x1bac64 W:zAnimObjectMotionFromToBegin@0x1bac88 W:zAnimObjectMotionFromToBegin@0x1baca8 (+6) |
| ?+168 | 4 | f32 |  | begin |  |  |  | W:zAnimObjectMotionFromToBegin@0x1bacb4 |
| ?+172 | 4 | f32 |  | begin |  |  |  | W:zAnimObjectMotionFromToBegin@0x1bacbc |
| ?+176 | 4 | f32 |  | begin |  |  |  | W:zAnimObjectMotionFromToBegin@0x1bacc8 |
| +180 | 1 | u8 | tick | begin,tick | unsigned-load |  | cmpeq c:0x1 c:0x2 c:0x3 | W:zAnimObjectMotionFromToBegin@0x1bac58 W:zAnimObjectMotionFromToBegin@0x1bac7c W:zAnimObjectMotionFromToBegin@0x1baca0 (+4) |

Callee-written/passed: +12 Add(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin,zAnimObjectMotionFromToTick; +12 GetRotation(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin; +12 SetRotation(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin; +12 Sub(CPnt3D*, 12 B) in zAnimLoadObjectMotionFromTo,zAnimObjectMotionFromToBegin; +24 Sub(CPnt3D*, 12 B) in zAnimLoadObjectMotionFromTo; +36 Scale(CPnt3D*, 12 B) in zAnimObjectMotionFromToTick; +48 Add(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin,zAnimObjectMotionFromToTick; +48 Sub(CPnt3D*, 12 B) in zAnimLoadObjectMotionFromTo,zAnimObjectMotionFromToBegin; +48 TransformToWorld(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin; +48 zrdr_findreal(f32*, 12 B) in zAnimLoadObjectMotionFromTo; +60 Add(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin,zAnimObjectMotionFromToTick; +60 Sub(CPnt3D*, 12 B) in zAnimLoadObjectMotionFromTo,zAnimObjectMotionFromToBegin; +60 TransformToWorld(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin; +60 zrdr_findreal(f32*, 12 B) in zAnimLoadObjectMotionFromTo; +72 Scale(CPnt3D*, 12 B) in zAnimObjectMotionFromToTick; +84 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectMotionFromTo; +88 GetScale(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin; +88 SetScale(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin; +88 Sub(CPnt3D*, 12 B) in zAnimLoadObjectMotionFromTo,zAnimObjectMotionFromToBegin; +100 Sub(CPnt3D*, 12 B) in zAnimLoadObjectMotionFromTo; +112 Scale(CPnt3D*, 12 B) in zAnimObjectMotionFromToTick; +124 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectMotionFromTo; +168 Normalize(CPnt3D*, 12 B) in zAnimObjectMotionFromToBegin; +168 Scale(CPnt3D*, 12 B) in Tick

### OBJECT_OPACITY_FROM_TO

- size: 24; data_size written: [24]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `_zanim_object_opacity_from_to_cmd (provisional)`
- notes: 24 bytes: hdr, u16 node_ref(+4), pad, f32 from(+8), f32 to(+12), f32 cur(+16), f32 time(+20). Registered twice (same name, same callbacks).
- alignment/tail padding (not accessed): +6..+8
- typeable functions: `0x1b1a20 zAnimLoadObjectOpacityFromTo`, `0x1ba280 zAnimObjectOpacityFromToBegin`, `0x1ba1c0 zAnimObjectOpacityFromToTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | index:node_ref | begin,tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadObjectOpacityFromTo@0x1b1ab0 R:zAnimObjectOpacityFromToBegin@0x1ba290 R:zAnimObjectOpacityFromToTick@0x1ba1d8 |
| +8 | 4 | f32 | begin,parse |  |  |  | float | R:zAnimLoadObjectOpacityFromTo@0x1b1b58 R:zAnimObjectOpacityFromToBegin@0x1ba2ac |
| +12 | 4 | f32 | parse,tick |  |  |  | float | R:zAnimLoadObjectOpacityFromTo@0x1b1b50 R:zAnimObjectOpacityFromToTick@0x1ba248 |
| +16 | 4 | f32 | tick | parse |  |  | float | W:zAnimLoadObjectOpacityFromTo@0x1b1b68 R:zAnimObjectOpacityFromToTick@0x1ba254 |
| +20 | 4 | f32 | parse,tick | parse |  |  | float c:0x3a83126f c:0x3f800000 | R:zAnimLoadObjectOpacityFromTo@0x1b1ad4 W:zAnimLoadObjectOpacityFromTo@0x1b1af8 W:zAnimLoadObjectOpacityFromTo@0x1b1b00 (+2) |

Callee-written/passed: +8 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectOpacityFromTo; +12 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectOpacityFromTo; +20 zrdr_findreal(f32*, 4 B) in zAnimLoadObjectOpacityFromTo

### OBJECT_MOTION_SI_SCRIPT

- size: 68; data_size written: -; variable tail: _realloc; timeless set: False; quad_align set: False; grade: **C**
- proposed: `_zanim_object_motion_si_script_cmd (provisional) + _zanim_object_motion_script (missing, 60 bytes)`
- notes: hdr + u16 count(+4) + pad + _zanim_object_motion_script[count] at +8 (60 bytes each; first alloc 68 = 8+60, realloc 68+60*count). Each entry starts with its own _zanim_cmd_hdr and is ticked by zAnimObjectMotionScriptTick(entry) and apply_script_frame(entry).
- unexplained gaps: +6..+13, +14..+15, +16..+20, +28..+64
- typeable functions: `0x1abcf0 zAnimLoadObjectMotionSIScript`, `0x1b9b10 zAnimMultiObjectMotionScriptBegin`, `0x1b9a30 zAnimMultiObjectMotionScriptTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | begin,parse,tick | parse | signed-cmp,unsigned-load | sll:0x4 | cmp:bgtz cmp:slt | R:zAnimLoadObjectMotionSIScript@0x1ac098 R:zAnimLoadObjectMotionSIScript@0x1ac0f0 R:zAnimLoadObjectMotionSIScript@0x1ac120 (+13) |
| +13 | 1 | index:node_ref | tick |  | unsigned-load |  | arg:GetNode(a1) cmpeq | R:zAnimObjectMotionScriptTick@0x1b9bbc |
| +15 | 1 | u8 | tick |  | unsigned-load |  | arg:SIScript(a1) | R:zAnimObjectMotionScriptTick@0x1b9bf8 |
| +20 | 4 | u32 |  | begin,tick |  |  | c:0x0 | W:zAnimMultiObjectMotionScriptBegin@0x1b9b4c W:zAnimObjectMotionScriptTick@0x1b9d10 |
| +24 | 4 | u32 | tick | begin,tick | signed-cmp |  | cmp:slt c:0x0 | W:zAnimMultiObjectMotionScriptBegin@0x1b9b48 R:zAnimObjectMotionScriptTick@0x1b9c30 R:zAnimObjectMotionScriptTick@0x1b9c58 (+9) |
| +64 | 4 | u32 | tick | begin,tick |  |  | c:0x0 | W:zAnimMultiObjectMotionScriptBegin@0x1b9b50 R:zAnimObjectMotionScriptTick@0x1b9c98 W:zAnimObjectMotionScriptTick@0x1b9ca0 |

Callee-written/passed: +8 apply_script_frame(?) in zAnimObjectMotionScriptTick

Indexed/tail accesses (base offset + variable): +20/w4/u32(begin), +24/w4/u32(begin), +64/w4/u32(begin)

### PARTICLE_SOURCE

- size: 220; data_size written: [220]; variable tail: _realloc; timeless set: True; quad_align set: False; grade: **B**
- proposed: `_zanim_particle_source_cmd (provisional)`
- notes: 220-byte fixed + realloc tails; two u32 bitfield words (+4,+8), index bytes +12..+19, ~40 f32 parameters +32..+216, u16 offset/count pairs +196..+208.
- alignment/tail padding (not accessed): +210..+212
- typeable functions: `0x1b5e30 zAnimLoadParticleSource`, `0x1bee80 zAnimParticleSourceTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | parse,tick | parse |  | and:0x10000 and:0x100000 and:0x1000000 and:0x10000000 | arg:zrdr_findtag(a2) cmpeq c:0x0 fld | W:zAnimLoadParticleSource@0x1b5f08 R:zAnimLoadParticleSource@0x1b5f24 W:zAnimLoadParticleSource@0x1b5f30 (+107) |
| +8 | 4 | u32 | parse,tick | parse | unsigned-cmp | and:0x10000 and:0x20000 and:0x40000 andi:0x1 | arg:zrdr_findtag(a2) cmp:sltu cmpeq c:0x0 fld | W:zAnimLoadParticleSource@0x1b5f18 R:zAnimLoadParticleSource@0x1b64e4 W:zAnimLoadParticleSource@0x1b6504 (+58) |
| +12 | 1 | index:particle_ref | tick | parse | unsigned-load |  | arg:GetParticleSource(a1) ret:AddName | W:zAnimLoadParticleSource@0x1b5ef0 W:zAnimLoadParticleSource@0x1b5f00 R:zAnimParticleSourceTick@0x1beebc |
| +13 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadParticleSource@0x1b63c0 W:zAnimLoadParticleSource@0x1b6404 W:zAnimLoadParticleSource@0x1b6474 (+2) |
| +14 | 1 | u8 | tick | parse | unsigned-load |  |  | W:zAnimLoadParticleSource@0x1b6c14 R:zAnimParticleSourceTick@0x1bf7cc |
| +15 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadParticleSource@0x1b76cc R:zAnimParticleSourceTick@0x1bfbf4 |
| +16 | 1 | u8 | tick | parse | signed-cmp,unsigned-load |  | cmp:slt c:0x0 c:0xff | W:zAnimLoadParticleSource@0x1b7074 W:zAnimLoadParticleSource@0x1b72ec R:zAnimParticleSourceTick@0x1bfb68 |
| +17 | 1 | u8 | tick | parse | signed-cmp,unsigned-load |  | cmp:slt c:0x0 c:0xff | W:zAnimLoadParticleSource@0x1b7464 R:zAnimParticleSourceTick@0x1bfbd0 |
| +18 | 1 | u8 | tick | parse | signed-cmp,unsigned-load |  | cmp:slt c:0x0 c:0xff | W:zAnimLoadParticleSource@0x1b75e4 R:zAnimParticleSourceTick@0x1bfc98 |
| +19 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xffffff0f and:0xfffffff0 andi:0xf dsll32:0x18 | arg:zrdr_findtag(a2) cmpeq fld | R:zAnimLoadParticleSource@0x1b5f58 W:zAnimLoadParticleSource@0x1b5f7c R:zAnimLoadParticleSource@0x1b5fa0 (+16) |
| +32 | 4 | f32 | tick | parse |  |  | arg:Scale(f12) c:0x3f800000 | W:zAnimLoadParticleSource@0x1b6604 W:zAnimLoadParticleSource@0x1b66a0 R:zAnimParticleSourceTick@0x1bf260 (+3) |
| +36 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf444 |
| +40 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf440 |
| +44 | 4 | f32 | tick | parse |  |  | arg:Scale(f12) c:0x3f800000 | W:zAnimLoadParticleSource@0x1b678c W:zAnimLoadParticleSource@0x1b6828 R:zAnimParticleSourceTick@0x1bf4a8 (+3) |
| +48 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf63c |
| +52 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf638 |
| +56 | 4 | f32 | parse,tick |  |  |  |  | R:zAnimLoadParticleSource@0x1b69e8 R:zAnimLoadParticleSource@0x1b6a04 R:zAnimParticleSourceTick@0x1bf67c |
| +60 | 4 | f32 | parse,tick |  |  |  |  | R:zAnimLoadParticleSource@0x1b69f0 R:zAnimLoadParticleSource@0x1b6a0c R:zAnimParticleSourceTick@0x1bf678 |
| +64 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b69ec R:zAnimParticleSourceTick@0x1bf69c |
| +68 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b69f4 R:zAnimParticleSourceTick@0x1bf698 |
| +72 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b6a08 R:zAnimParticleSourceTick@0x1bf6bc |
| +76 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b6a10 R:zAnimParticleSourceTick@0x1bf6b8 |
| +80 | 4 | f32 | parse,tick |  |  |  |  | R:zAnimLoadParticleSource@0x1b6ac0 R:zAnimLoadParticleSource@0x1b6adc R:zAnimParticleSourceTick@0x1bf6dc |
| +84 | 4 | f32 | parse,tick |  |  |  |  | R:zAnimLoadParticleSource@0x1b6ac8 R:zAnimLoadParticleSource@0x1b6ae4 R:zAnimParticleSourceTick@0x1bf6d8 |
| +88 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b6ac4 R:zAnimParticleSourceTick@0x1bf6fc |
| +92 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b6acc R:zAnimParticleSourceTick@0x1bf6f8 |
| +96 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b6ae0 R:zAnimParticleSourceTick@0x1bf71c |
| +100 | 4 | f32 | tick | parse |  |  | fld | W:zAnimLoadParticleSource@0x1b6ae8 R:zAnimParticleSourceTick@0x1bf718 |
| +104 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bfc24 |
| +108 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bfc20 |
| +112 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bfc34 |
| +116 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bfc30 |
| +120 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bfc44 |
| +124 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bfc40 |
| +128 | 4 | f32 | tick |  |  |  | float | R:zAnimParticleSourceTick@0x1bf744 R:zAnimParticleSourceTick@0x1bf770 |
| +132 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf7f0 |
| +136 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf7ec |
| +140 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf7e8 |
| +144 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf82c |
| +148 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf858 |
| +152 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bfab0 |
| +156 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf888 |
| +160 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf884 |
| +164 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf8ac |
| +168 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf8a8 |
| +172 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf8d0 |
| +176 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf8cc |
| +180 | 4 | f32 | tick |  |  |  | float | R:zAnimParticleSourceTick@0x1bf8f4 |
| +184 | 4 | f32 | tick |  |  |  | float | R:zAnimParticleSourceTick@0x1bf8f0 |
| +188 | 4 | f32 | tick |  |  |  | float | R:zAnimParticleSourceTick@0x1bf95c |
| +192 | 4 | f32 | tick |  |  |  | float | R:zAnimParticleSourceTick@0x1bf958 |
| +196 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:zAnimLoadParticleSource@0x1b6514 R:zAnimParticleSourceTick@0x1bf13c |
| +198 | 2 | u16 | parse,tick | parse | signed-cmp,signed-load |  | cmp:bgez cmpeq c:0xffffffff | W:zAnimLoadParticleSource@0x1b6b70 R:zAnimLoadParticleSource@0x1b6bd0 W:zAnimLoadParticleSource@0x1b6be8 (+1) |
| +200 | 2 | u16 | tick | parse | unsigned-load |  | fld | W:zAnimLoadParticleSource@0x1b7098 W:zAnimLoadParticleSource@0x1b7310 R:zAnimParticleSourceTick@0x1bfae8 |
| +202 | 2 | u16 | tick | parse | unsigned-load |  | fld | W:zAnimLoadParticleSource@0x1b7490 R:zAnimParticleSourceTick@0x1bfb8c |
| +204 | 2 | u16 | tick | parse | unsigned-load |  | fld | W:zAnimLoadParticleSource@0x1b7608 R:zAnimParticleSourceTick@0x1bfc64 |
| +206 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:zAnimLoadParticleSource@0x1b61bc W:zAnimLoadParticleSource@0x1b630c R:zAnimParticleSourceTick@0x1bef64 |
| +208 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:zAnimLoadParticleSource@0x1b6074 R:zAnimParticleSourceTick@0x1bef34 |
| +212 | 4 | f32 | tick | parse |  |  | c:0x3f000000 | W:zAnimLoadParticleSource@0x1b6ee8 W:zAnimLoadParticleSource@0x1b6f24 R:zAnimParticleSourceTick@0x1bfa74 |
| +216 | 4 | f32 | tick |  |  |  |  | R:zAnimParticleSourceTick@0x1bf9bc |

Callee-written/passed: +20 Add(CPnt3D*, 12 B) in zAnimParticleSourceTick; +20 zrdr_findreal(f32*, 12 B) in zAnimLoadParticleSource; +32 zrdr_findreal(f32*, 4 B) in zAnimLoadParticleSource; +32 zrdr_findreal(f32*, 12 B) in zAnimLoadParticleSource; +44 zrdr_findreal(f32*, 4 B) in zAnimLoadParticleSource; +44 zrdr_findreal(f32*, 12 B) in zAnimLoadParticleSource; +56 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +64 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +72 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +80 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +88 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +96 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +104 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +112 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +120 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +128 zrdr_findreal(f32*, 4 B) in zAnimLoadParticleSource; +132 zrdr_findreal(f32*, 12 B) in zAnimLoadParticleSource; +144 zrdr_findreal(f32*, 4 B) in zAnimLoadParticleSource; +148 zrdr_findreal(f32*, 4 B) in zAnimLoadParticleSource; +152 zrdr_findreal(f32*, 4 B) in zAnimLoadParticleSource; +156 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +164 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +172 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +180 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +188 zrdr_findreal(f32*, 8 B) in zAnimLoadParticleSource; +216 zrdr_findreal(f32*, 4 B) in zAnimLoadParticleSource

Indexed/tail accesses (base offset + variable): +0/w2/u16(tick), +0/w4/f32(tick), +4/w4/f32(tick), +8/w4/f32(tick), +12/w4/f32(tick), +16/w4/f32(tick), +20/w4/f32(tick)

### CAMERA

- size: 132; data_size written: [132]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `_zanim_camera_cmd (provisional)`
- notes: 132 bytes: hdr, u32 flags(+4; low 24 bits flags, byte +7 = node_ref index), 10 x {f32 a, f32 b, f32 c} at +8..+127 (FOV/clip/etc: begin applies +8/+12 via SetHalf*FOV/Set*Clip), f32 rate(+128).
- typeable functions: `0x1b4ca0 zAnimLoadCamera`, `0x1be9b0 zAnimCameraBegin`, `0x1be5e0 zAnimCameraTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,parse,tick | parse |  | and:0x10000 and:0x20000 and:0xff000000 andi:0x1 | cmpeq fld | R:zAnimLoadCamera@0x1b4df4 W:zAnimLoadCamera@0x1b4e1c R:zAnimLoadCamera@0x1b4eb0 (+80) |
| +7 | 1 | index:node_ref | begin,tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadCamera@0x1b4d30 R:zAnimCameraBegin@0x1be9c4 R:zAnimCameraTick@0x1be608 |
| +8 | 4 | f32 | begin,parse | begin,parse |  |  | arg:SetHalfHorizontalFOVRadians(f12) float | W:zAnimLoadCamera@0x1b4e84 R:zAnimLoadCamera@0x1b4e8c W:zAnimLoadCamera@0x1b4eac (+4) |
| +12 | 4 | f32 | begin,parse,tick | parse |  |  | arg:SetHalfHorizontalFOVRadians(f12) float | W:zAnimLoadCamera@0x1b4f48 R:zAnimLoadCamera@0x1b4f50 W:zAnimLoadCamera@0x1b4f70 (+3) |
| +16 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b4f9c W:zAnimCameraBegin@0x1bea58 R:zAnimCameraTick@0x1be7bc |
| +20 | 4 | f32 | begin,parse | begin,parse |  |  | arg:SetHalfVerticalFOVRadians(f12) float | W:zAnimLoadCamera@0x1b5080 R:zAnimLoadCamera@0x1b5088 W:zAnimLoadCamera@0x1b50a8 (+4) |
| +24 | 4 | f32 | begin,parse,tick | parse |  |  | arg:SetHalfVerticalFOVRadians(f12) float | W:zAnimLoadCamera@0x1b5144 R:zAnimLoadCamera@0x1b514c W:zAnimLoadCamera@0x1b516c (+3) |
| +28 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5198 W:zAnimCameraBegin@0x1bead0 R:zAnimCameraTick@0x1be7ec |
| +32 | 4 | f32 | begin,parse | begin,parse |  |  | arg:SetNearClip(f12) float | W:zAnimLoadCamera@0x1b527c R:zAnimLoadCamera@0x1b5338 R:zAnimCameraBegin@0x1beaf4 (+2) |
| +36 | 4 | f32 | begin,parse,tick | parse |  |  | arg:SetNearClip(f12) float | W:zAnimLoadCamera@0x1b5318 R:zAnimLoadCamera@0x1b5334 R:zAnimCameraBegin@0x1beb34 (+1) |
| +40 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5344 W:zAnimCameraBegin@0x1beb48 R:zAnimCameraTick@0x1be81c |
| +44 | 4 | f32 | begin,parse | begin,parse |  |  | arg:SetMidClip(f12) float | W:zAnimLoadCamera@0x1b5428 R:zAnimLoadCamera@0x1b54e4 R:zAnimCameraBegin@0x1beb6c (+2) |
| +48 | 4 | f32 | begin,parse,tick | parse |  |  | arg:SetMidClip(f12) float | W:zAnimLoadCamera@0x1b54c4 R:zAnimLoadCamera@0x1b54e0 R:zAnimCameraBegin@0x1bebac (+1) |
| +52 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b54f0 W:zAnimCameraBegin@0x1bebc0 R:zAnimCameraTick@0x1be84c |
| +56 | 4 | f32 | begin,parse | begin,parse |  |  | arg:SetFarClip(f12) float | W:zAnimLoadCamera@0x1b55d4 R:zAnimLoadCamera@0x1b5690 R:zAnimCameraBegin@0x1bebe4 (+2) |
| +60 | 4 | f32 | begin,parse,tick | parse |  |  | arg:SetFarClip(f12) float | W:zAnimLoadCamera@0x1b5670 R:zAnimLoadCamera@0x1b568c R:zAnimCameraBegin@0x1bec24 (+1) |
| +64 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b569c W:zAnimCameraBegin@0x1bec38 R:zAnimCameraTick@0x1be87c |
| +68 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5780 R:zAnimLoadCamera@0x1b583c R:zAnimCameraBegin@0x1bec5c (+2) |
| +72 | 4 | f32 | begin,parse,tick | parse |  |  | float | W:zAnimLoadCamera@0x1b581c R:zAnimLoadCamera@0x1b5838 R:zAnimCameraBegin@0x1bec94 (+1) |
| +76 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5848 W:zAnimCameraBegin@0x1beca8 R:zAnimCameraTick@0x1be8ac |
| +80 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b592c R:zAnimLoadCamera@0x1b59e8 R:zAnimCameraBegin@0x1beccc (+2) |
| +84 | 4 | f32 | begin,parse,tick | parse |  |  | float | W:zAnimLoadCamera@0x1b59c8 R:zAnimLoadCamera@0x1b59e4 R:zAnimCameraBegin@0x1bed04 (+1) |
| +88 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b59f4 W:zAnimCameraBegin@0x1bed18 R:zAnimCameraTick@0x1be8d8 |
| +92 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5ad8 R:zAnimLoadCamera@0x1b5d48 R:zAnimCameraBegin@0x1bed44 (+2) |
| +96 | 4 | f32 | begin,parse,tick | parse |  |  | float | W:zAnimLoadCamera@0x1b5c34 R:zAnimLoadCamera@0x1b5d44 R:zAnimCameraBegin@0x1bedbc (+1) |
| +100 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5d54 W:zAnimCameraBegin@0x1bedd0 R:zAnimCameraTick@0x1be930 |
| +104 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5b3c R:zAnimLoadCamera@0x1b5d5c R:zAnimCameraBegin@0x1bed40 (+2) |
| +108 | 4 | f32 | begin,parse,tick | parse |  |  | float | W:zAnimLoadCamera@0x1b5cb0 R:zAnimLoadCamera@0x1b5d58 R:zAnimCameraBegin@0x1bedd4 (+1) |
| +112 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5d68 W:zAnimCameraBegin@0x1bede4 R:zAnimCameraTick@0x1be944 |
| +116 | 4 | f32 | begin,parse | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5ba0 R:zAnimLoadCamera@0x1b5d70 R:zAnimCameraBegin@0x1bed3c (+2) |
| +120 | 4 | f32 | begin,parse,tick | parse |  |  | float | W:zAnimLoadCamera@0x1b5d28 R:zAnimLoadCamera@0x1b5d6c R:zAnimCameraBegin@0x1bede8 (+1) |
| +124 | 4 | f32 | tick | begin,parse |  |  | float | W:zAnimLoadCamera@0x1b5d7c W:zAnimCameraBegin@0x1bedf8 R:zAnimCameraTick@0x1be958 |
| +128 | 4 | f32 | begin,parse,tick | parse |  |  | float c:0x3727c5ac c:0x3a83126f | R:zAnimLoadCamera@0x1b4d54 W:zAnimLoadCamera@0x1b4d78 W:zAnimLoadCamera@0x1b4d84 (+10) |

Callee-written/passed: +128 zrdr_findreal(f32*, 4 B) in zAnimLoadCamera

### DESTRUCTION_SOURCE

- size: 80; data_size written: [80]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_destruction_source_cmd (provisional)`
- notes: 80 bytes: hdr, u8 node_ref(+4), u8 name(+5), u8(+6), pad, CPnt3D(+8), f32(+20), f32 (+24..+76).
- alignment/tail padding (not accessed): +7..+8
- typeable functions: `0x1b7750 zAnimLoadDestructor`, `0x1bfd90 zAnimDestructorTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadDestructor@0x1b7830 R:zAnimDestructorTick@0x1bfe2c |
| +5 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadDestructor@0x1b7870 R:zAnimDestructorTick@0x1bfe0c |
| +6 | 1 | u8 | tick | parse | unsigned-load |  | arg:DestructionManager(t3) c:0x0 c:0x1 | W:zAnimLoadDestructor@0x1b7a0c W:zAnimLoadDestructor@0x1b7a1c W:zAnimLoadDestructor@0x1b7a34 (+1) |
| +24 | 4 | f32 | parse,tick | parse |  |  | arg:DestructionManager(f12) float c:0x41200000 | R:zAnimLoadDestructor@0x1b7aa8 W:zAnimLoadDestructor@0x1b7ac8 R:zAnimDestructorTick@0x1bfe40 |
| +28 | 4 | f32 | tick | parse |  |  |  | W:zAnimLoadDestructor@0x1b7938 R:zAnimDestructorTick@0x1bfdb4 |
| +32 | 4 | f32 | tick | parse |  |  |  | W:zAnimLoadDestructor@0x1b7944 R:zAnimDestructorTick@0x1bfdcc |
| +36 | 4 | f32 | tick | parse |  |  |  | W:zAnimLoadDestructor@0x1b7960 R:zAnimDestructorTick@0x1bfdac |
| +40 | 4 | f32 | tick | parse |  |  |  | W:zAnimLoadDestructor@0x1b796c R:zAnimDestructorTick@0x1bfdc8 |
| +44 | 4 | f32 | tick | parse |  |  |  | W:zAnimLoadDestructor@0x1b7988 R:zAnimDestructorTick@0x1bfda4 |
| +48 | 4 | f32 | tick | parse |  |  |  | W:zAnimLoadDestructor@0x1b7994 R:zAnimDestructorTick@0x1bfdc4 |
| +52 | 4 | f32 | tick | parse |  |  | c:0x40800000 | W:zAnimLoadDestructor@0x1b79a4 W:zAnimLoadDestructor@0x1b79dc R:zAnimDestructorTick@0x1bfde4 |
| +56 | 4 | f32 | tick | parse |  |  | c:0x40800000 | W:zAnimLoadDestructor@0x1b79ac W:zAnimLoadDestructor@0x1b79e0 R:zAnimDestructorTick@0x1bfde0 |
| +60 | 4 | f32 | tick |  |  |  |  | R:zAnimDestructorTick@0x1bfddc |
| +64 | 4 | f32 | tick | parse |  |  | c:0x0 | W:zAnimLoadDestructor@0x1b7a58 W:zAnimLoadDestructor@0x1b7a78 R:zAnimDestructorTick@0x1bfdfc |
| +68 | 4 | f32 | tick | parse |  |  | c:0xc2c40000 | W:zAnimLoadDestructor@0x1b7a60 W:zAnimLoadDestructor@0x1b7a7c R:zAnimDestructorTick@0x1bfdf8 |
| +72 | 4 | f32 | tick | parse |  |  | c:0x0 | W:zAnimLoadDestructor@0x1b7a6c W:zAnimLoadDestructor@0x1b7a70 R:zAnimDestructorTick@0x1bfdf4 |
| +76 | 4 | f32 | tick | parse |  |  | arg:DestructionManager(f13) c:0x3f800000 | W:zAnimLoadDestructor@0x1b7aa4 R:zAnimDestructorTick@0x1bfe44 |

Callee-written/passed: +8 DestructionManager(CPnt3D*, 12 B) in zAnimDestructorTick; +8 zrdr_findreal(f32*, 4 B) in zAnimLoadDestructor; +12 zrdr_findreal(f32*, 4 B) in zAnimLoadDestructor; +16 zrdr_findreal(f32*, 4 B) in zAnimLoadDestructor; +20 zrdr_findreal(f32*, 4 B) in zAnimLoadDestructor; +24 zrdr_findreal(f32*, 4 B) in zAnimLoadDestructor; +60 zrdr_findreal(f32*, 4 B) in zAnimLoadDestructor; +76 zrdr_findreal(f32*, 4 B) in zAnimLoadDestructor

### SOUND

- size: 32; data_size written: [32]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_sound_cmd (provisional)`
- notes: 32 bytes: hdr, u16 flags(+4), u8 sound_ref(+6), u8 node_ref(+7), f32 volume(+8), s16 pan(+12), s16 pitch(+14), u8 node_ref(+16), pad, CPnt3D(+20).
- alignment/tail padding (not accessed): +17..+20
- typeable functions: `0x1b4920 zAnimLoadSound`, `0x1be170 zAnimSoundTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | parse,tick | parse | unsigned-load | andi:0x1 andi:0x10 andi:0x100 andi:0x2 | arg:fptosi(a0) cmpeq c:0x0 fld | W:zAnimLoadSound@0x1b49cc R:zAnimLoadSound@0x1b49ec W:zAnimLoadSound@0x1b4a04 (+34) |
| +6 | 1 | index:sound_ref | tick | parse | unsigned-load |  | arg:GetSoundRef(a1) ret:AddName | W:zAnimLoadSound@0x1b49c4 R:zAnimSoundTick@0x1be1e8 |
| +7 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 | W:zAnimLoadSound@0x1b49d4 R:zAnimSoundTick@0x1be1d0 |
| +8 | 4 | f32 | tick | parse |  |  | arg:SetVol(f12) arg:jalr:t9(f12) | W:zAnimLoadSound@0x1b4a98 R:zAnimSoundTick@0x1be238 R:zAnimSoundTick@0x1be430 |
| +12 | 2 | u16 | tick | parse | signed-load |  | arg:SetPan(a1) arg:jalr:t9(a1) ret:fptosi | W:zAnimLoadSound@0x1b4b58 R:zAnimSoundTick@0x1be24c R:zAnimSoundTick@0x1be44c |
| +14 | 2 | u16 | tick | parse | signed-load |  | arg:SetPitch(a1) arg:jalr:t9(a2) ret:fptosi | W:zAnimLoadSound@0x1b4bb0 R:zAnimSoundTick@0x1be25c R:zAnimSoundTick@0x1be468 |
| +16 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadSound@0x1b49e0 W:zAnimLoadSound@0x1b4a1c R:zAnimSoundTick@0x1be2fc (+1) |

Callee-written/passed: +20 Add(CPnt3D*, 12 B) in zAnimSoundTick; +20 zrdr_findreal(f32*, 12 B) in zAnimLoadSound

### LIGHT

- size: 64; data_size written: [64]; variable tail: GetBlendValueSequence, _realloc; timeless set: True; quad_align set: False; grade: **B**
- proposed: `_zanim_light_cmd (provisional)` (cluster `blend-tail`)
- notes: 64-byte fixed + blend tail: hdr, u16 flags(+4), u8 node_ref(+6), u8 tex_ref(+7), u8 node_ref(+8), u8 bitfields(+9), f32 +12/+16, CPnt3D(+20), CPnt3D(+32), f32(+44), f32(+48), s16 x4(+52..+58), f32(+60).
- alignment/tail padding (not accessed): +10..+12
- typeable functions: `0x1b37f0 zAnimLoadLight`, `0x1bd7c0 zAnimLightTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | parse,tick | parse | unsigned-load | andi:0x1 andi:0x10 andi:0x100 andi:0x2 | cmpeq c:0x0 fld | W:zAnimLoadLight@0x1b38d4 R:zAnimLoadLight@0x1b391c W:zAnimLoadLight@0x1b3924 (+35) |
| +6 | 1 | index:node_ref | parse,tick | parse | unsigned-load |  | arg:GetNode(a1) arg:GetNodeRef(a1) ret:LoadNodeNames | W:zAnimLoadLight@0x1b389c R:zAnimLoadLight@0x1b38ac R:zAnimLightTick@0x1bd818 (+2) |
| +7 | 1 | index:tex_ref | tick | parse | unsigned-load |  | arg:GetTexture(a1) ret:AddName | W:zAnimLoadLight@0x1b3938 R:zAnimLightTick@0x1bd9d0 |
| +8 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadLight@0x1b3980 R:zAnimLightTick@0x1bdad8 |
| +9 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xffffff3f and:0xffffffcf and:0xfffffff3 and:0xfffffffc | arg:zrdr_findtag(a2) arg:zrdr_findtag(a3) fld | R:zAnimLoadLight@0x1b3ad8 W:zAnimLoadLight@0x1b3ae8 R:zAnimLoadLight@0x1b3af0 (+6) |
| +12 | 4 | f32 | tick |  |  |  |  | R:zAnimLightTick@0x1bdb7c R:zAnimLightTick@0x1bdbe4 |
| +16 | 4 | f32 | tick |  |  |  | float | R:zAnimLightTick@0x1bdb74 R:zAnimLightTick@0x1bdbdc |
| +32 | 4 | f32 | tick |  |  |  |  | R:zAnimLightTick@0x1bdc4c R:zAnimLightTick@0x1bdc70 |
| +36 | 4 | f32 | tick |  |  |  |  | R:zAnimLightTick@0x1bdc54 R:zAnimLightTick@0x1bdc78 |
| +40 | 4 | f32 | tick |  |  |  |  | R:zAnimLightTick@0x1bdc5c R:zAnimLightTick@0x1bdc80 |
| +44 | 4 | f32 | parse,tick | parse |  |  | float | R:zAnimLoadLight@0x1b3a54 W:zAnimLoadLight@0x1b3a68 R:zAnimLightTick@0x1bdca0 |
| +48 | 4 | f32 | tick | parse |  |  | float | W:zAnimLoadLight@0x1b3b44 R:zAnimLightTick@0x1bdcc0 |
| +52 | 2 | u16 | tick | parse | signed-load | sll:0x1 | arg:DeleteLightMap(t0) arg:GetBlendSequenceValue(t0) arg:jalr:t9(t0) c:0x0 | W:zAnimLoadLight@0x1b3e54 R:zAnimLightTick@0x1bddc4 |
| +54 | 2 | u16 | tick | parse | signed-load |  | fld | W:zAnimLoadLight@0x1b3e68 R:zAnimLightTick@0x1bdd98 |
| +56 | 2 | u16 | tick |  | signed-load |  | arg:GetBlendSequenceValue(a2) | R:zAnimLightTick@0x1be01c |
| +58 | 2 | u16 | tick | parse | signed-load |  | fld | W:zAnimLoadLight@0x1b3f44 R:zAnimLightTick@0x1be010 |
| +60 | 4 | f32 | parse,tick | parse |  |  | float c:0x0 | W:zAnimLoadLight@0x1b38e4 R:zAnimLoadLight@0x1b3d08 W:zAnimLoadLight@0x1b3d1c (+1) |

Callee-written/passed: +12 zrdr_findreal(f32*, 8 B) in zAnimLoadLight; +20 Add(CPnt3D*, 12 B) in zAnimLightTick; +20 zrdr_findreal(f32*, 12 B) in zAnimLoadLight; +32 Scale(CPnt3D*, 12 B) in zAnimLoadLight; +32 zrdr_findreal(f32*, 12 B) in zAnimLoadLight; +44 zrdr_findreal(f32*, 4 B) in zAnimLoadLight

Indexed/tail accesses (base offset + variable): +-8/w4/f32(tick), +-4/w4/f32(tick), +0/w4/f32(tick), +4/w4/f32(tick), +8/w4/f32(tick), +12/w4/f32(tick), +16/w4/f32(tick), +20/w4/f32(tick)

### WHILE

- size: 8; data_size written: [8]; variable tail: AnimParseExpression; timeless set: True; quad_align set: False; grade: **B**
- proposed: `_zanim_while_cmd (provisional)` (cluster `while-family-8`)
- notes: 8-byte fixed: hdr + s16 m_always(+4, 1 when literal TRUE) + s16 m_jump_offset(+6, seq-relative; END_WHILE parser patches WHILE.+6 via seq_offset_stack and stores the WHILE offset in its own +6). WHILE appends an expression stream.
- typeable functions: `0x1b0c10 zAnimLoadWhile`, `0x1b8de0 zAnimWhileTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | tick | parse | signed-load |  | cmpeq c:0x1 | W:zAnimLoadWhile@0x1b0d18 R:zAnimWhileTick@0x1b8df4 |
| +6 | 2 | u16 | tick |  | signed-load |  | arg:CmdSet(a1) | R:zAnimWhileTick@0x1b8e20 |

### END_WHILE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **B**
- proposed: `_zanim_while_cmd (provisional)` (cluster `while-family-8`)
- notes: 8-byte fixed: hdr + s16 m_always(+4, 1 when literal TRUE) + s16 m_jump_offset(+6, seq-relative; END_WHILE parser patches WHILE.+6 via seq_offset_stack and stores the WHILE offset in its own +6). WHILE appends an expression stream.
- unexplained gaps: +4..+6
- typeable functions: `0x1b0b00 zAnimLoadEndWhile`, `0x1b8db0 zAnimEndWhileTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +6 | 2 | u16 | tick | parse | signed-load |  | arg:CmdSet(a1) c:0x0 | W:zAnimLoadEndWhile@0x1b0bb0 R:zAnimEndWhileTick@0x1b8db8 |

### EXPRESSION

- size: n/a; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **n/a (header-only)**
- proposed: `_zanim_cmd_hdr-headed operand records (NewCmd, 8 bytes)` (cluster `expression`)
- notes: Registered with no callbacks; ids stored at ZAnim+0x68. Records are produced by CZAnimExpression::NewCmd (calloc 8) inside IF/ELSEIF/WHILE expression tails.
- typeable functions: 

### BREAK

- size: 4; data_size written: [4]; variable tail: no; timeless set: True; quad_align set: False; grade: **n/a (header-only)**
- proposed: `_zanim_cmd_hdr (no new type)` (cluster `header-only`)
- notes: Parser allocates exactly 4 bytes (data_size 4).
- typeable functions: `0x1b0a90 zAnimLoadBreak`, `0x1b8ce0 zAnimBreakTick`

### CALL_ANIMATION

- size: 24; data_size written: [24]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_call_animation_cmd (provisional)`
- notes: 24 bytes: hdr, u16 flags(+4), u8 call_anim_ref(+6), u8 call_anim_ref(+7), u8 node_ref x3(+8..+10), pad, CPnt3D(+12).
- alignment/tail padding (not accessed): +11..+12
- typeable functions: `0x1af2f0 zAnimLoadCallAnim`, `0x1b8380 zAnimCallAnimBegin`, `0x1b8310 zAnimCallAnimTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | begin,parse,tick | parse | unsigned-load | andi:0x1 andi:0x10 andi:0x2 andi:0x20 | cmpeq fld | R:zAnimLoadCallAnim@0x1af46c W:zAnimLoadCallAnim@0x1af474 R:zAnimLoadCallAnim@0x1af48c (+21) |
| +6 | 1 | index:call_anim_ref | begin,tick | parse | unsigned-load |  | arg:GetCallAnimRef(a2) c:0x0 ret:AddName | W:zAnimLoadCallAnim@0x1af44c W:zAnimLoadCallAnim@0x1af450 R:zAnimCallAnimBegin@0x1b83cc (+1) |
| +7 | 1 | index:call_anim_ref | begin,tick | parse | unsigned-load |  | arg:GetCallAnimRef(a1) ret:AddName | W:zAnimLoadCallAnim@0x1af3e0 R:zAnimCallAnimBegin@0x1b83c8 R:zAnimCallAnimTick@0x1b832c |
| +8 | 1 | index:node_ref | begin | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadCallAnim@0x1af4dc R:zAnimCallAnimBegin@0x1b84c0 |
| +9 | 1 | index:node_ref | begin | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadCallAnim@0x1af528 R:zAnimCallAnimBegin@0x1b8530 |
| +10 | 1 | index:node_ref | begin | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:zAnimLoadCallAnim@0x1af594 R:zAnimCallAnimBegin@0x1b85b4 |
| +12 | 4 | f32 | begin |  |  |  |  | R:zAnimCallAnimBegin@0x1b85dc |
| +16 | 4 | f32 | begin |  |  |  |  | R:zAnimCallAnimBegin@0x1b85e4 |
| +20 | 4 | f32 | begin |  |  |  |  | R:zAnimCallAnimBegin@0x1b85ec |

Callee-written/passed: +12 Add(CPnt3D*, 12 B) in zAnimCallAnimBegin; +12 zrdr_findreal(f32*, 12 B) in zAnimLoadCallAnim

### STOP_ANIMATION

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_anim_ref_cmd (provisional)` (cluster `u8-callanim-8`)
- notes: Identical 8-byte layout: hdr + u8 call_anim_ref index(+4, CZAnim::GetCallAnimRef) + 3 pad.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1af1d0 zAnimLoadStopAnim`, `0x1b8280 zAnimStopAnimTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:call_anim_ref | tick | parse | unsigned-load |  | arg:GetCallAnimRef(a1) ret:AddName | W:zAnimLoadStopAnim@0x1af2b4 R:zAnimStopAnimTick@0x1b8290 |

### PAUSE_ANIMATION

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_anim_ref_cmd (provisional)` (cluster `u8-callanim-8`)
- notes: Identical 8-byte layout: hdr + u8 call_anim_ref index(+4, CZAnim::GetCallAnimRef) + 3 pad.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1af0d0 zAnimLoadPauseAnim`, `0x1b81d0 zAnimPauseAnimTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:call_anim_ref | tick | parse | unsigned-load |  | arg:GetCallAnimRef(a1) arg:Pause(a1) cmpeq ret:AddName | W:zAnimLoadPauseAnim@0x1af1b4 R:zAnimPauseAnimTick@0x1b81e0 |

### RESUME_ANIMATION

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_anim_ref_cmd (provisional)` (cluster `u8-callanim-8`)
- notes: Identical 8-byte layout: hdr + u8 call_anim_ref index(+4, CZAnim::GetCallAnimRef) + 3 pad.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1aefb0 zAnimLoadResumeAnim`, `0x1b8140 zAnimResumeAnimTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:call_anim_ref | tick | parse | unsigned-load |  | arg:GetCallAnimRef(a1) ret:AddName | W:zAnimLoadResumeAnim@0x1af094 R:zAnimResumeAnimTick@0x1b8150 |

### INVALIDATE_ANIMATION

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_anim_ref_cmd (provisional)` (cluster `u8-callanim-8`)
- notes: Identical 8-byte layout: hdr + u8 call_anim_ref index(+4, CZAnim::GetCallAnimRef) + 3 pad.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1aee90 zAnimLoadInvalidateAnim`, `0x1b80c0 zAnimInvalidateAnimTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:call_anim_ref | tick | parse | unsigned-load |  | arg:GetCallAnimRef(a1) cmpeq c:0x0 ret:AddName | W:zAnimLoadInvalidateAnim@0x1aef74 W:zAnimLoadInvalidateAnim@0x1aef90 R:zAnimInvalidateAnimTick@0x1b80cc |

### CALL_SEQUENCE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_sequence_cmd (provisional)` (cluster `u8-name-8`)
- notes: Identical 8-byte layout: hdr + u8 name index(+4, CZAnim::GetName) + 3 pad.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1aed80 zAnimLoadCallSequence`, `0x1b8080 zAnimCallSequenceTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadCallSequence@0x1aee54 R:zAnimCallSequenceTick@0x1b808c |

### STOP_SEQUENCE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_sequence_cmd (provisional)` (cluster `u8-name-8`)
- notes: Identical 8-byte layout: hdr + u8 name index(+4, CZAnim::GetName) + 3 pad.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1aec70 zAnimLoadStopSequence`, `0x1b8040 zAnimStopSequenceTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadStopSequence@0x1aed44 R:zAnimStopSequenceTick@0x1b804c |

### DEBUG

- size: 20; data_size written: [20]; variable tail: _realloc; timeless set: False; quad_align set: False; grade: **B**
- proposed: `_zanim_debug_cmd (provisional)`
- notes: 20-byte fixed + realloc string tails: hdr, u32 flags(+4), u32 packed bitfields(+8, 10-bit fields), u16 x4 (+12..+18, tail offsets). Tick is a stub (returns 1).
- typeable functions: `0x1aaef0 zAnimLoadDebug`, `0x1b7c80 zAnimDebugTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | parse | parse |  | ori:0x1 ori:0x10 ori:0x100 ori:0x2 | fld | R:zAnimLoadDebug@0x1aaf74 W:zAnimLoadDebug@0x1aaf8c R:zAnimLoadDebug@0x1aafe4 (+15) |
| +8 | 1 | u8 | parse | parse | unsigned-load | and:0xfc0003ff and:0xfffffc03 and:0xfffffffd and:0xfffffffe | fld | R:zAnimLoadDebug@0x1aaf98 W:zAnimLoadDebug@0x1aafb0 R:zAnimLoadDebug@0x1aafb4 (+5) |
| +8 | 2 | u16 | parse | parse | unsigned-load | and:0xfc0003ff and:0xfffffc03 and:0xfffffffd and:0xfffffffe | fld | R:zAnimLoadDebug@0x1ab7c4 W:zAnimLoadDebug@0x1ab7dc |
| +8 | 4 | u32 | parse | parse |  | and:0xfc0003ff and:0xfffffc03 and:0xfffffffd and:0xfffffffe | fld | R:zAnimLoadDebug@0x1ab070 R:zAnimLoadDebug@0x1ab200 W:zAnimLoadDebug@0x1ab21c |
| +12 | 2 | u16 |  | parse |  |  | c:0x0 fld | W:zAnimLoadDebug@0x1ab250 W:zAnimLoadDebug@0x1ab3e0 |
| +14 | 2 | u16 |  | parse |  |  | c:0x0 fld | W:zAnimLoadDebug@0x1ab414 W:zAnimLoadDebug@0x1ab5a4 |
| +16 | 2 | u16 |  | parse |  |  | c:0x0 fld | W:zAnimLoadDebug@0x1ab5d8 W:zAnimLoadDebug@0x1ab768 |
| +18 | 2 | u16 |  | parse |  |  | c:0x0 fld | W:zAnimLoadDebug@0x1ab854 W:zAnimLoadDebug@0x1ab9e4 |

### OBJECT_ADD_CHILD

- size: 8; data_size written: [8]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `_zanim_object_child_cmd (provisional)` (cluster `u16-u8-u8-8`)
- notes: Identical 8-byte layout: hdr, u16 flags(+4, ADD only), u8 parent node_ref(+6), u8 child node_ref(+7). Each name registered twice.
- typeable functions: `0x1abb80 zAnimLoadObjectAddChild`, `0x1b98b0 zAnimObjectAddChildTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | parse,tick | parse | unsigned-load | andi:0x1 ori:0x1 | cmpeq fld | R:zAnimLoadObjectAddChild@0x1abcb8 W:zAnimLoadObjectAddChild@0x1abcc0 R:zAnimObjectAddChildTick@0x1b9910 (+1) |
| +6 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectAddChild@0x1abc38 W:zAnimLoadObjectAddChild@0x1abc3c R:zAnimObjectAddChildTick@0x1b98d0 |
| +7 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectAddChild@0x1abc98 W:zAnimLoadObjectAddChild@0x1abc9c R:zAnimObjectAddChildTick@0x1b98e0 |

### OBJECT_DELETE_CHILD

- size: 8; data_size written: [8]; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `_zanim_object_child_cmd (provisional)` (cluster `u16-u8-u8-8`)
- notes: Identical 8-byte layout: hdr, u16 flags(+4, ADD only), u8 parent node_ref(+6), u8 child node_ref(+7). Each name registered twice.
- unexplained gaps: +4..+6
- typeable functions: `0x1aba30 zAnimLoadObjectDeleteChild`, `0x1b9830 zAnimObjectDeleteChildTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +6 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectDeleteChild@0x1abae8 W:zAnimLoadObjectDeleteChild@0x1abaec R:zAnimObjectDeleteChildTick@0x1b9840 |
| +7 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) c:0x0 ret:LoadNodeNames | W:zAnimLoadObjectDeleteChild@0x1abb48 W:zAnimLoadObjectDeleteChild@0x1abb4c R:zAnimObjectDeleteChildTick@0x1b9854 |

### MESSAGE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_message_cmd (provisional)`
- notes: 8 bytes: hdr, u8 name(+4), u8 x3 (+5..+7, message args from fptoui).
- typeable functions: `0x1aacb0 zAnimLoadMessage`, `0x1bfce0 zAnimMessageTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadMessage@0x1aad54 R:zAnimMessageTick@0x1bfcf0 |
| +5 | 1 | u8 | tick | parse | unsigned-load |  | arg:Add_Message(a2) cmpeq ret:fptoui | W:zAnimLoadMessage@0x1aad8c W:zAnimLoadMessage@0x1aadf4 R:zAnimMessageTick@0x1bfd00 |
| +6 | 1 | u8 | tick | parse | unsigned-load |  | arg:Add_Message(a3) cmpeq ret:fptoui | W:zAnimLoadMessage@0x1aadb0 W:zAnimLoadMessage@0x1aae00 R:zAnimMessageTick@0x1bfd0c (+1) |
| +7 | 1 | u8 | tick | parse | unsigned-load |  | arg:Add_Message(t0) cmpeq ret:fptoui | W:zAnimLoadMessage@0x1aadd0 W:zAnimLoadMessage@0x1aae0c R:zAnimMessageTick@0x1bfd18 (+1) |

### TIMER

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_timer_cmd (provisional)` (cluster `int-8`)
- notes: hdr + int(+4, -1 when tag present, else zrdr_findint); tick converts to float into theMission+0x68.
- typeable functions: `0x1aae30 zAnimLoadTimer`, `0x1bfd70 zAnimTimerTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | int | tick | parse |  |  | int->float c:0x0 c:0xffffffff | W:zAnimLoadTimer@0x1aaeb4 W:zAnimLoadTimer@0x1aaecc R:zAnimTimerTick@0x1bfd70 |

Callee-written/passed: +4 zrdr_findint(int*, 4 B) in zAnimLoadTimer

### FIRE_WEAPON

- size: 44; data_size written: [44]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `_zanim_fire_weapon_cmd (provisional)`
- notes: 44 bytes: hdr, u8 flags(+4), u8 name x3(+5..+7), u8 node_ref x2(+8,+9), pad, f32(+12), f32(+16), CPnt3D(+20), f32(+32), f32(+36), f32(+40).
- alignment/tail padding (not accessed): +10..+12
- typeable functions: `0x1aa840 zAnimLoadFireWeapon`, `0x1b7c90 zAnimFireWeaponTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | unsigned-load | andi:0x1 andi:0x2 ori:0x1 ori:0x2 | cmpeq fld | R:zAnimLoadFireWeapon@0x1aaaa0 W:zAnimLoadFireWeapon@0x1aaaa8 R:zAnimLoadFireWeapon@0x1aaac0 (+3) |
| +5 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadFireWeapon@0x1aa92c R:zAnimFireWeaponTick@0x1b7d28 |
| +6 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadFireWeapon@0x1aa9b4 R:zAnimFireWeaponTick@0x1b7d04 |
| +7 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) cmpeq ret:AddName | W:zAnimLoadFireWeapon@0x1aaa3c R:zAnimFireWeaponTick@0x1b7ee4 |
| +8 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) cmpeq c:0x0 ret:LoadNodeNames | W:zAnimLoadFireWeapon@0x1aaa50 W:zAnimLoadFireWeapon@0x1aaa7c R:zAnimFireWeaponTick@0x1b7e54 |
| +9 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:Fire(a1) arg:GetMuzzleVelocity(a1) arg:GetNode(a1) cmpeq c:0x0 | W:zAnimLoadFireWeapon@0x1aaafc W:zAnimLoadFireWeapon@0x1aab40 R:zAnimFireWeaponTick@0x1b7f1c |
| +12 | 4 | f32 | parse,tick | parse |  |  | float c:0x3c23d70a | W:zAnimLoadFireWeapon@0x1aac38 R:zAnimLoadFireWeapon@0x1aac58 R:zAnimFireWeaponTick@0x1b7f0c |
| +16 | 4 | f32 | tick | parse |  |  |  | W:zAnimLoadFireWeapon@0x1aac70 R:zAnimFireWeaponTick@0x1b7f14 |
| +32 | 4 | f32 | parse,tick | parse |  |  | float fld | W:zAnimLoadFireWeapon@0x1aaadc W:zAnimLoadFireWeapon@0x1aab84 R:zAnimLoadFireWeapon@0x1aaba8 (+4) |
| +36 | 4 | f32 | tick | parse |  |  | c:0x0 | W:zAnimLoadFireWeapon@0x1aaae8 W:zAnimLoadFireWeapon@0x1aabb8 W:zAnimLoadFireWeapon@0x1aabd4 (+1) |
| +40 | 4 | f32 | parse,tick | parse |  |  | float fld | W:zAnimLoadFireWeapon@0x1aaaf4 W:zAnimLoadFireWeapon@0x1aab9c R:zAnimLoadFireWeapon@0x1aabc0 (+4) |

Callee-written/passed: +12 zrdr_findreal(f32*, 4 B) in zAnimLoadFireWeapon; +16 zrdr_findreal(f32*, 4 B) in zAnimLoadFireWeapon; +20 Add(CPnt3D*, 12 B) in zAnimFireWeaponTick; +20 zrdr_findreal(f32*, 12 B) in zAnimLoadFireWeapon; +32 Scale(CPnt3D*, 12 B) in zAnimFireWeaponTick

### ui::UI_COMMAND

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `C2DAnimCmdHdr (DWARF, 8 bytes) / control-specific C2DAnimCmdHdr-prefixed records` (cluster `c2d`)
- notes: zAnimLoadUIMenu callocs 8 (C2DAnimCmdHdr: header, u16 node_ref_index +4, u8 m_command_type +6, u8 m_argument_index +7) or returns the control ParseZAnimCmd record (CUIMapCtrl 24, CPopUpDialog 208, others exactly 8).
- typeable functions: `0x1d04b0 zAnimLoadUIMenu`, `0x1d0140 zAnimUIMenuTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | tick | parse | unsigned-load | andi:0xffff | cmpeq c:0x0 | W:zAnimLoadUIMenu@0x1d0608 R:zAnimUIMenuTick@0x1d017c |
| +6 | 1 | u8 | tick | parse | unsigned-cmp,unsigned-load | sll:0x1 xor:None | cmp:sltiu cmpeq c:0x0 c:0x95 | W:zAnimLoadUIMenu@0x1d06a4 R:zAnimUIMenuTick@0x1d0224 |
| +7 | 1 | index:name | tick | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:zAnimLoadUIMenu@0x1d06e0 R:zAnimUIMenuTick@0x1d0218 |

Callee-written/passed: +0 jalr:t9(?) in zAnimUIMenuTick; +0 jalr:v0(?) in zAnimUIMenuTick

### ui::UI_APP_COMMAND

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_zanim_ui_app_cmd (provisional)`
- notes: 8 bytes: hdr, u8 command enum(+4, < 0x95), u8 name(+5). Tick is a stub.
- alignment/tail padding (not accessed): +6..+8
- typeable functions: `0x1d0330 zAnimLoadUIAppMenu`, `0x1d0130 zAnimUIAppMenuTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 |  | parse |  |  | c:0x0 c:0x95 | W:zAnimLoadUIAppMenu@0x1d0448 |
| +5 | 1 | u8 |  | parse |  |  | ret:AddName | W:zAnimLoadUIAppMenu@0x1d0484 |

### DYNAMICS_RELEASE_CAMERA

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `_camera_control_cmd (DWARF)` (cluster `switch-bits-8`)
- notes: DWARF 0xf3cbf: hdr + int release:1 (bit0) + int acquire:1 (bit1) at +4; CmdTickControlSwitch local `cmd` is _camera_control_cmd*.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1e7530 zdb::CCamera::CmdParseRelease`, `0x1e7470 zdb::CCamera::CmdTickControlSwitch`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffe dsll32:0x1e dsll32:0x1f dsra32:0x1f | cmpeq fld | R:CmdParseRelease@0x1e7598 W:CmdParseRelease@0x1e75a4 R:CmdTickControlSwitch@0x1e7470 |

### DYNAMICS_ACQUIRE_CAMERA

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `_camera_control_cmd (DWARF)` (cluster `switch-bits-8`)
- notes: DWARF 0xf3cbf: hdr + int release:1 (bit0) + int acquire:1 (bit1) at +4; CmdTickControlSwitch local `cmd` is _camera_control_cmd*.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1e74b0 zdb::CCamera::CmdParseAcquire`, `0x1e7470 zdb::CCamera::CmdTickControlSwitch`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffd dsll32:0x1e dsll32:0x1f dsra32:0x1f | cmpeq fld | R:CmdParseAcquire@0x1e7510 W:CmdParseAcquire@0x1e751c R:CmdTickControlSwitch@0x1e7470 |

### CAMERA_INDOORS

- size: 4; data_size written: [4]; variable tail: no; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `_zanim_cmd_hdr (DWARF parser locals)` (cluster `header-only`)
- notes: Header-only records; DWARF parser local `cmd` is _zanim_cmd_hdr*.
- typeable functions: `0x1e7400 zdb::CCamera::CmdParseIndoorsTest`, `0x1e73f0 zdb::CCamera::CmdTickIndoorsTest`

### SET_CAMERA_REGION_TEST

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `_camera_set_regions_cmd (DWARF)` (cluster `switch-bits-8`)
- notes: DWARF 0xf2c50: hdr + int set_on:1 at +4 (asm: dsll32/dsra32 0x1f signed 1-bit).
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1e7320 zdb::CCamera::CmdParseSetRegions`, `0x1e72f0 zdb::CCamera::CmdTickSetRegions`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffe dsll32:0x1f dsra32:0x1f | cmpeq fld | R:CmdParseSetRegions@0x1e73a4 W:CmdParseSetRegions@0x1e73bc R:CmdParseSetRegions@0x1e73c0 (+2) |

### GET_CAMERA_REGION_TEST

- size: 4; data_size written: [4]; variable tail: no; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `_zanim_cmd_hdr (DWARF parser locals)` (cluster `header-only`)
- notes: Header-only records; DWARF parser local `cmd` is _zanim_cmd_hdr*.
- typeable functions: `0x1e7280 zdb::CCamera::CmdParseGetRegions`, `0x1e7270 zdb::CCamera::CmdTickGetRegions`

### CAMERA_PARAMS

- size: 36; data_size written: [36]; variable tail: zAnimCmdAddData; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `_camera_params_cmd (DWARF)`
- notes: DWARF 0xf570e (36 bytes) matched field-for-field by the scan; tails of _camera_param_{1d,2d,3d}_data (8/12/16) appended with zAnimCmdAddData and addressed by the u16 offset/count pairs.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1e6300 zdb::CCamera::CmdParseParams`, `0x1e61c0 zdb::CCamera::CmdBeginParams`, `0x1e5570 zdb::CCamera::CmdTickParams`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | begin,parse,tick | parse | unsigned-cmp,unsigned-load | and:0xffffffdf and:0xffffffef and:0xfffffff7 and:0xfffffffb | arg:zrdr_findtag(a2) cmp:sltu cmpeq fld | R:CmdParseParams@0x1e6394 W:CmdParseParams@0x1e63a8 R:CmdParseParams@0x1e63c0 (+21) |
| +8 | 4 | f32 | parse,tick | parse |  |  | float c:0x0 | W:CmdParseParams@0x1e6388 R:CmdParseParams@0x1e66b0 W:CmdParseParams@0x1e66c4 (+11) |
| +12 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:CmdParseParams@0x1e66dc R:CmdTickParams@0x1e5638 |
| +14 | 2 | u16 | parse,tick | parse | unsigned-load | sll:0x1 | arg:sinf(t0) | R:CmdParseParams@0x1e66e0 W:CmdParseParams@0x1e66f8 R:CmdTickParams@0x1e5660 |
| +16 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:CmdParseParams@0x1e6914 R:CmdTickParams@0x1e5a6c |
| +18 | 2 | u16 | parse,tick | parse | unsigned-load | sll:0x1 | arg:sinf(t0) | R:CmdParseParams@0x1e6918 W:CmdParseParams@0x1e6930 R:CmdTickParams@0x1e5a94 (+1) |
| +20 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:CmdParseParams@0x1e6bd4 R:CmdTickParams@0x1e5910 |
| +22 | 2 | u16 | parse,tick | parse | unsigned-load | sll:0x4 | arg:sinf(t0) | R:CmdParseParams@0x1e6bd8 W:CmdParseParams@0x1e6bf0 R:CmdTickParams@0x1e5938 (+2) |
| +24 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:CmdParseParams@0x1e6e0c R:CmdTickParams@0x1e5bac |
| +26 | 2 | u16 | parse,tick | parse | unsigned-load | sll:0x1 | arg:sinf(t0) | R:CmdParseParams@0x1e6e10 W:CmdParseParams@0x1e6e28 R:CmdTickParams@0x1e5bd4 (+1) |
| +28 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:CmdParseParams@0x1e7044 R:CmdTickParams@0x1e5cb8 |
| +30 | 2 | u16 | parse,tick | parse | unsigned-load | sll:0x1 | arg:sinf(t0) | R:CmdParseParams@0x1e7048 W:CmdParseParams@0x1e7060 R:CmdTickParams@0x1e5ce0 (+1) |
| +32 | 2 | u16 | tick | parse | signed-cmp,unsigned-load | andi:0xffff | cmp:blez fld | W:CmdParseParams@0x1e71f4 R:CmdTickParams@0x1e5ea4 |
| +34 | 2 | u16 | parse,tick | parse | unsigned-load | sll:0x3 | arg:sinf(t0) | R:CmdParseParams@0x1e71f8 W:CmdParseParams@0x1e7210 R:CmdTickParams@0x1e5ecc |

Indexed/tail accesses (base offset + variable): +-12/w4/f32(tick), +-8/w4/f32(tick), +-4/w4/f32(tick), +0/w4/f32(tick), +4/w4/f32(tick), +8/w4/f32(tick), +12/w4/f32(tick), +16/w4/f32(tick), +20/w4/f32(tick), +24/w4/f32(tick), +28/w4/f32(tick)

### CAMERA_3RD_PERSON

- size: 4; data_size written: [4]; variable tail: no; timeless set: True; quad_align set: False; grade: **DWARF**
- proposed: `_zanim_cmd_hdr (DWARF parser locals)` (cluster `header-only`)
- notes: Header-only records; DWARF parser local `cmd` is _zanim_cmd_hdr*.
- typeable functions: `0x1eb9a0 CAppCamera::CmdParse3rdPersonTest`, `0x1eb980 CAppCamera::CmdTick3rdPersonTest`

### HUD_ON

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd)` (cluster `switch-bits-8`)
- notes: 8 bytes: hdr + signed 1-bit flags bit0 (ON / LETTERBOX_ON) and bit1 (OFF) at +4, read by a shared ControlSwitch-style tick - same shape as DWARF _camera_control_cmd.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1f9d60 HUDCmdParseOn`, `0x1f9c70 HUDCmdTickControlSwitch`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffe dsll32:0x1e dsll32:0x1f dsra32:0x1f | cmpeq fld | R:HUDCmdParseOn@0x1f9dc8 W:HUDCmdParseOn@0x1f9dd4 R:HUDCmdTickControlSwitch@0x1f9c8c |

### HUD_OFF

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd)` (cluster `switch-bits-8`)
- notes: 8 bytes: hdr + signed 1-bit flags bit0 (ON / LETTERBOX_ON) and bit1 (OFF) at +4, read by a shared ControlSwitch-style tick - same shape as DWARF _camera_control_cmd.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1f9ce0 HUDCmdParseOff`, `0x1f9c70 HUDCmdTickControlSwitch`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffd dsll32:0x1e dsll32:0x1f dsra32:0x1f | cmpeq fld | R:HUDCmdParseOff@0x1f9d40 W:HUDCmdParseOff@0x1f9d4c R:HUDCmdTickControlSwitch@0x1f9c8c |

### HUD_LETTERBOX_ON

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd)` (cluster `switch-bits-8`)
- notes: 8 bytes: hdr + signed 1-bit flags bit0 (ON / LETTERBOX_ON) and bit1 (OFF) at +4, read by a shared ControlSwitch-style tick - same shape as DWARF _camera_control_cmd.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1f9be0 HUDLetterBoxCmdParseOn`, `0x1f9af0 HUDLetterBoxCmdTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffe dsll32:0x1e dsll32:0x1f dsra32:0x1f | cmpeq fld | R:HUDLetterBoxCmdParseOn@0x1f9c48 W:HUDLetterBoxCmdParseOn@0x1f9c54 R:HUDLetterBoxCmdTick@0x1f9b0c |

### HUD_LETTERBOX_OFF

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd)` (cluster `switch-bits-8`)
- notes: 8 bytes: hdr + signed 1-bit flags bit0 (ON / LETTERBOX_ON) and bit1 (OFF) at +4, read by a shared ControlSwitch-style tick - same shape as DWARF _camera_control_cmd.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1f9b60 HUDLetterBoxCmdParseOff`, `0x1f9af0 HUDLetterBoxCmdTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffd dsll32:0x1e dsll32:0x1f dsra32:0x1f | cmpeq fld | R:HUDLetterBoxCmdParseOff@0x1f9bc0 W:HUDLetterBoxCmdParseOff@0x1f9bcc R:HUDLetterBoxCmdTick@0x1f9b0c |

### HUD_TRIGGER_MISSION_CAM

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_hud_mission_cam_cmd (provisional)` (cluster `u8-name-8`)
- notes: hdr + u8 name index(+4) (begin -> CZHudMissionCams::PlayCamera(GetName)).
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1f9980 HUDTriggerMissionCamParse`, `0x1f9930 HUDTriggerMissionCamBegin`, `0x1f98d0 HUDTriggerMissionCamTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:name | begin | parse | unsigned-load |  | arg:GetName(a1) ret:AddName | W:HUDTriggerMissionCamParse@0x1f9acc R:HUDTriggerMissionCamBegin@0x1f9948 |

### HUD_START_DEFUSE_TIMER

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_hud_defuse_timer_cmd (provisional)` (cluster `f32-8`)
- notes: hdr + f32 seconds(+4) -> hudStartDefuseTimer(f12).
- typeable functions: `0x1f9760 HUDStartDefuseTimerParse`, `0x1f9740 HUDStartDefuseTimerTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | f32 | tick | parse |  |  | arg:hudStartDefuseTimer(f12) | W:HUDStartDefuseTimerParse@0x1f98b4 R:HUDStartDefuseTimerTick@0x1f974c |

### START_IMAGE_RECORDER

- size: 12; data_size written: [12]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_image_recorder_cmd (provisional)`
- notes: 12 bytes: hdr, packed bitfields +4..+7 (12/10-bit ints from zrdr_findint, flag bits at +5), f32 fps(+8, 29.97 default).
- typeable functions: `0x1f9e80 StartImageRecorderParse`, `0x1f9e70 StartImageRecorderTick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 |  | parse |  | and:0xffc00fff | arg:zrdr_findint(t0) ret:AddName | W:StartImageRecorderParse@0x1f9f30 |
| +4 | 4 | u32 | parse | parse |  | and:0xffc00fff | arg:zrdr_findint(t0) fld | R:StartImageRecorderParse@0x1f9f34 W:StartImageRecorderParse@0x1f9f68 R:StartImageRecorderParse@0x1f9f98 (+1) |
| +5 | 1 | u8 | parse | parse | unsigned-load | and:0xfffffffb and:0xfffffffd and:0xfffffffe | fld | R:StartImageRecorderParse@0x1f9f74 W:StartImageRecorderParse@0x1f9f90 R:StartImageRecorderParse@0x1f9fec (+3) |
| +6 | 2 | u16 | parse | parse | unsigned-load | and:0xffff003f | arg:zrdr_findint(t0) fld | R:StartImageRecorderParse@0x1f9fb0 W:StartImageRecorderParse@0x1f9fe0 R:StartImageRecorderParse@0x1fa010 (+1) |
| +8 | 4 | f32 |  | parse |  |  | c:0x41efc28f | W:StartImageRecorderParse@0x1fa03c W:StartImageRecorderParse@0x1fa070 |

### STOP_IMAGE_RECORDER

- size: 4; data_size written: [4]; variable tail: no; timeless set: True; quad_align set: False; grade: **n/a (header-only)**
- proposed: `_zanim_cmd_hdr (no new type)` (cluster `header-only`)
- notes: Header-only (data_size 4).
- typeable functions: `0x1f9e00 StopImageRecorderParse`, `0x1f9df0 StopImageRecorderTick`

### PLAYER_INDOORS

- size: 4; data_size written: [4]; variable tail: no; timeless set: True; quad_align set: False; grade: **n/a (header-only)**
- proposed: `_zanim_cmd_hdr (no new type)` (cluster `header-only`)
- notes: Header-only (data_size 4).
- typeable functions: `0x1fde80 CftsPlayer::CmdParseIndoorsTest`, `0x1fde50 CftsPlayer::CmdTickIndoorsTest`

### PLAYER_CONTROLS

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_hud_switch_cmd / _player_controls_cmd (provisional; same shape as _camera_control_cmd)` (cluster `switch-bits-8`)
- notes: 8 bytes: hdr + signed 1-bit flags bit0 (ON / LETTERBOX_ON) and bit1 (OFF) at +4, read by a shared ControlSwitch-style tick - same shape as DWARF _camera_control_cmd.
- alignment/tail padding (not accessed): +5..+8
- typeable functions: `0x1fdd80 CftsPlayer::CmdParseControls`, `0x1fdd10 CftsPlayer::CmdTickControls`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | u8 | parse,tick | parse | signed-load | and:0xfffffffd and:0xfffffffe dsll32:0x1f dsra32:0x1f | cmpeq fld | R:CmdParseControls@0x1fde04 W:CmdParseControls@0x1fde1c R:CmdParseControls@0x1fde20 (+2) |

### IS_PLAYER_NODE

- size: 8; data_size written: [8]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_player_is_node_cmd (provisional)`
- notes: 8 bytes: hdr, u8 node_ref(+4), u8 flag bit0(+5).
- alignment/tail padding (not accessed): +6..+8
- typeable functions: `0x1fdc20 CftsPlayer::CmdParseIsPlayerNode`, `0x1fdb80 CftsPlayer::CmdTickIsPlayerNode`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 1 | index:node_ref | tick | parse | unsigned-load |  | arg:GetNode(a1) ret:LoadNodeNames | W:CmdParseIsPlayerNode@0x1fdcc4 R:CmdTickIsPlayerNode@0x1fdb94 |
| +5 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xfffffffe andi:0x1 | cmpeq fld | R:CmdParseIsPlayerNode@0x1fdcd8 W:CmdParseIsPlayerNode@0x1fdcec R:CmdTickIsPlayerNode@0x1fdbcc |

### WIND

- size: 68; data_size written: [68]; variable tail: no; timeless set: True; quad_align set: False; grade: **A**
- proposed: `_wind_cmd (provisional)`
- notes: 68 bytes: hdr, u16 flags(+4), 15 x f32 (+8..+64).
- alignment/tail padding (not accessed): +6..+8
- typeable functions: `0x22cd40 CWind::CmdParseWind`, `0x22cb30 CWind::CmdTickWind`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 2 | u16 | parse,tick | parse | unsigned-load | andi:0x1 andi:0x10 andi:0x100 andi:0x2 | cmpeq fld | R:CmdParseWind@0x22cdd8 W:CmdParseWind@0x22cde0 R:CmdParseWind@0x22cf14 (+24) |
| +8 | 4 | f32 | parse,tick | parse |  |  | float | W:CmdParseWind@0x22ce40 R:CmdParseWind@0x22ce48 W:CmdParseWind@0x22ce5c (+1) |
| +12 | 4 | f32 | tick | parse |  |  | float c:0x0 | W:CmdParseWind@0x22cee4 W:CmdParseWind@0x22cee8 R:CmdTickWind@0x22cb40 |
| +16 | 4 | f32 | parse,tick | parse |  |  | float | W:CmdParseWind@0x22cf7c R:CmdParseWind@0x22cf84 W:CmdParseWind@0x22cf98 (+1) |
| +20 | 4 | f32 | tick | parse |  |  | float c:0x0 | W:CmdParseWind@0x22d020 W:CmdParseWind@0x22d024 R:CmdTickWind@0x22cba8 |
| +24 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d0b8 R:CmdTickWind@0x22cc1c |
| +28 | 4 | f32 | tick | parse |  |  | float c:0x0 | W:CmdParseWind@0x22d144 W:CmdParseWind@0x22d148 R:CmdTickWind@0x22cc10 |
| +32 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d208 R:CmdTickWind@0x22cc80 |
| +36 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d26c R:CmdTickWind@0x22cc78 |
| +40 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d304 R:CmdTickWind@0x22cc9c |
| +44 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d3c4 R:CmdTickWind@0x22ccc0 |
| +48 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d428 R:CmdTickWind@0x22ccb8 |
| +52 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d4c0 R:CmdTickWind@0x22ccdc |
| +56 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d580 R:CmdTickWind@0x22cd00 |
| +60 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d5e4 R:CmdTickWind@0x22ccf8 |
| +64 | 4 | f32 | tick | parse |  |  |  | W:CmdParseWind@0x22d67c R:CmdTickWind@0x22cd1c |

### ai::ACTION

- size: 16; data_size written: [16]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_ACTION : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- alignment/tail padding (not accessed): +15..+16
- typeable functions: `0x2be520 CTAction::Parse`, `0x2be2f0 CTAction::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2be314 |
| +8 | 4 | index:valve_ref | tick | parse |  |  | arg:GetValve(a1) ret:AddValve | W:Parse@0x2be5e8 R:Tick@0x2be38c |
| +12 | 2 | u16 | tick | parse | unsigned-load |  | c:0xffff | W:Parse@0x2be5f0 R:Tick@0x2be4d8 |
| +14 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xfffffffe andi:0x1 | cmpeq fld | R:Parse@0x2be5f8 W:Parse@0x2be604 R:Tick@0x2be3a4 |

### ai::COMM

- size: 16; data_size written: [16]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_COMM : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- alignment/tail padding (not accessed): +14..+16
- typeable functions: `0x2be230 CTComm::Parse`, `0x2bde00 CTComm::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2bde34 |
| +8 | 4 | u32 | tick | parse |  | and:None sllv:0x1 | arg:GetUnitByTeam(a0) cmpeq c:0xffffffff | W:Parse@0x2be2a0 R:Tick@0x2bdf98 R:Tick@0x2be118 (+1) |
| +12 | 1 | u8 | tick |  | unsigned-load |  | arg:jalr:t9(a2) cmpeq | R:Tick@0x2bde84 |
| +12 | 2 | u16 |  | parse |  |  | arg:jalr:t9(a2) cmpeq c:0x0 | W:Parse@0x2be2a8 W:Parse@0x2be2c8 |

Callee-written/passed: +8 zrdr_findint(int*, 4 B) in Parse

### ai::DEBUG

- size: variable, sizeof 16; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_DEBUG : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 16 -> trailing char m_name[4] at +12 (min/sizeof 16).
- typeable functions: `0x2bdc90 CTDebug::Parse`, `0x2bdb70 CTDebug::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2bdb98 |
| +8 | 4 | u32 | tick | parse |  |  | cmpeq c:0x0 c:0xffffffff ret:fptosi | W:Parse@0x2bdddc R:Tick@0x2bdc1c |
| +12 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2bddd0 |

Callee-written/passed: +12 Debug(?) in Tick; +12 strcpy(char*) in Parse

### ai::DOOR

- size: 44; data_size written: [44]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_MOVE (shared with ai::MOVE; provisional)` (cluster `task-hdr`)
- notes: Parse/Begin are `j CTMove::Parse/Begin` stubs - record is TASK_MOVE (44).
- alignment/tail padding (not accessed): +41..+44
- typeable functions: `0x2bdb60 Parse`, `0x2ba460 CTMove::Parse`, `0x2bdb50 Begin`, `0x2b9c90 CTMove::Begin`, `0x2bda90 CTDoor::Tick`, `0x2bda20 CTDoor::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end,tick | parse |  |  | arg:taskFindParam(a1) c:0x0 | W:Parse@0x2ba6f0 R:Begin@0x2b9cac R:Tick@0x2bdaac (+1) |
| +8 | 4 | f32 | begin | parse |  |  | float | W:Parse@0x2ba4f0 R:Begin@0x2b9f60 |
| +12 | 4 | f32 | begin | parse |  |  | float | W:Parse@0x2ba4fc R:Begin@0x2b9f78 |
| +16 | 4 | f32 | begin | parse |  |  | float | W:Parse@0x2ba508 R:Begin@0x2b9fa0 |
| +20 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2ba518 |
| +24 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2ba524 |
| +28 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2ba530 |
| +32 | 4 | f32 | begin | parse |  |  | arg:Scale(f12) c:0x0 | W:Parse@0x2ba510 R:Begin@0x2b9ee0 R:Begin@0x2ba184 (+1) |
| +36 | 4 | index:node_ref | begin | parse |  |  | arg:GetNode(a1) arg:taskFindParam(a1) c:0x0 ret:LoadNodeNames | W:Parse@0x2ba534 W:Parse@0x2ba570 R:Begin@0x2b9d7c (+2) |
| +40 | 1 | u8 | begin,parse | parse | unsigned-load | and:0xffffffdf and:0xfffffff0 andi:0xf | arg:zrdr_findstring(a3) arg:zrdr_findstring(t1) cmpeq fld | R:Parse@0x2ba4dc W:Parse@0x2ba4e8 R:Parse@0x2ba538 (+12) |

Callee-written/passed: +4 zrdr_finduint(int*, 4 B) in Parse; +8 Scale(CPnt3D*, 12 B) in Begin; +8 zrdr_findPNT3D(CPnt3D*, 12 B) in Parse; +20 zrdr_findPNT3D(CPnt3D*, 12 B) in Parse; +32 zrdr_findreal(f32*, 4 B) in Parse; +36 zrdr_toINT(int*, 4 B) in Parse

Indexed/tail accesses (base offset + variable): +12/w4/f32(begin), +16/w4/f32(begin), +24/w4/f32(begin), +28/w4/f32(begin), +36/w4/f32(begin), +40/w4/f32(begin), +48/w4/f32(begin), +52/w4/f32(begin), +60/w4/f32(begin), +64/w4/f32(begin), +72/w4/f32(begin), +76/w4/f32(begin)

### ai::EVENT

- size: 36; data_size written: [36]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_EVENT : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- alignment/tail padding (not accessed): +35..+36
- typeable functions: `0x2bd860 CTEvent::Parse`, `0x2bd850 CTEvent::Begin`, `0x2bd5e0 CTEvent::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2bd5fc |
| +8 | 4 | f32 | tick | parse |  |  |  | W:Parse@0x2bd8d0 R:Tick@0x2bd7c4 |
| +12 | 4 | f32 | tick | parse |  |  |  | W:Parse@0x2bd8dc R:Tick@0x2bd7cc |
| +16 | 4 | f32 | tick | parse |  |  |  | W:Parse@0x2bd8e8 R:Tick@0x2bd7d4 |
| +20 | 4 | f32 | tick |  |  |  | float | R:Tick@0x2bd69c |
| +24 | 4 | f32 | tick |  |  |  |  | R:Tick@0x2bd678 |
| +28 | 4 | index:node_ref | tick | parse |  |  | arg:GetNode(a1) ret:LoadNodeNames | W:Parse@0x2bd954 R:Tick@0x2bd708 |
| +32 | 1 | u8 | tick |  | signed-load | andi:0x7fff sll:0x1 |  | R:Tick@0x2bd800 |
| +32 | 2 | u16 |  | parse |  | andi:0x7fff sll:0x1 | c:0x1 | W:Parse@0x2bd8f0 W:Parse@0x2bd910 |
| +34 | 1 | u8 | parse,tick | parse | unsigned-cmp,unsigned-load | and:0xfffffff7 and:0xfffffffb and:0xfffffffd and:0xfffffffe | cmp:sltu cmpeq fld | R:Parse@0x2bd95c W:Parse@0x2bd96c R:Parse@0x2bd990 (+9) |

Callee-written/passed: +8 zrdr_findPNT3D(CPnt3D*, 12 B) in Parse; +20 zrdr_findreal(f32*, 4 B) in Parse; +24 zrdr_findreal(f32*, 4 B) in Parse

Indexed/tail accesses (base offset + variable): +12/w4/f32(tick), +16/w4/f32(tick), +24/w4/f32(tick), +28/w4/f32(tick), +36/w4/f32(tick), +40/w4/f32(tick), +48/w4/f32(tick), +52/w4/f32(tick), +60/w4/f32(tick), +64/w4/f32(tick)

### ai::FIREMODE

- size: 28; data_size written: [28]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_FIREMODE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- alignment/tail padding (not accessed): +10..+12, +25..+28
- typeable functions: `0x2bd3a0 CTFireMode::Parse`, `0x2bd1a0 CTFireMode::Begin`, `0x2bd100 CTFireMode::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2bd1c4 R:Tick@0x2bd114 |
| +8 | 1 | u8 | begin,parse | parse | unsigned-load | and:0xffffff3f and:0xffffffcf and:0xfffffff3 and:0xfffffffc | cmpeq fld | R:Parse@0x2bd464 W:Parse@0x2bd470 R:Parse@0x2bd474 (+10) |
| +9 | 1 | u8 | parse | parse | unsigned-load | and:0xffffffc3 and:0xfffffffd and:0xfffffffe | arg:zrdr_findint(t1) arg:zrdr_findint(t3) fld | R:Parse@0x2bd4a4 W:Parse@0x2bd4b0 R:Parse@0x2bd4b8 (+5) |
| +12 | 4 | u32 |  | parse |  |  | c:0x0 | W:Parse@0x2bd4b4 |
| +16 | 4 | f32 | begin | parse |  |  | c:0x3dcccccd | W:Parse@0x2bd45c W:Parse@0x2bd544 R:Begin@0x2bd240 |
| +20 | 4 | f32 | begin | parse |  |  | c:0x3f4ccccd | W:Parse@0x2bd460 W:Parse@0x2bd54c R:Begin@0x2bd23c |
| +24 | 1 | u8 | begin,parse | parse | unsigned-load | and:0xfffffffe andi:0x1 | cmpeq fld | R:Parse@0x2bd528 W:Parse@0x2bd53c R:Begin@0x2bd22c |

Callee-written/passed: +8 ChooseWeapon(?) in Begin

### ai::FIREWEAPON

- size: 44; data_size written: [44]; variable tail: no; timeless set: False; quad_align set: False; grade: **C**
- proposed: `TASK_FIREWEAPON : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- unexplained gaps: +32..+44
- alignment/tail padding (not accessed): +13..+16
- typeable functions: `0x2bd060 CTFireWeapon::Parse`, `0x2bcfa0 CTFireWeapon::Begin`, `0x2bcd70 CTFireWeapon::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2bcfb4 R:Tick@0x2bcd8c |
| +8 | 1 | u8 | begin |  | unsigned-load |  | arg:HasItem(a1) | R:Begin@0x2bd014 |
| +8 | 4 | u32 | tick | parse |  |  | arg:HasItem(a1) | W:Parse@0x2bd0d4 R:Tick@0x2bcf68 |
| +12 | 1 | u8 | begin,parse,tick | begin,parse,tick | unsigned-cmp,unsigned-load | and:0xfffffffe andi:0x1 dsll32:0x1c dsll32:0x1e | cmp:sltiu cmpeq fld | R:Parse@0x2bd0dc W:Parse@0x2bd0ec R:Begin@0x2bd028 (+4) |
| +20 | 4 | f32 | tick |  |  |  |  | R:Tick@0x2bce34 |
| +24 | 4 | f32 | tick |  |  |  |  | R:Tick@0x2bce40 |
| +28 | 4 | f32 | tick |  |  |  |  | R:Tick@0x2bce48 |

Callee-written/passed: +16 GetCellCenter(CPnt3D*, 12 B) in Tick

### ai::GOTO

- size: variable, sizeof 20; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_GOTO : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: size = 20 + 4*(n-1): fixed 16 + CAiMapLoc(4) route[n] at +16 (trailing [1] idiom).
- alignment/tail padding (not accessed): +14..+16
- typeable functions: `0x2bc910 CTGoto::Parse`, `0x2bc300 CTGoto::Begin`, `0x2bc210 CTGoto::Tick`, `0x2bc100 CTGoto::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2bc320 R:Tick@0x2bc234 R:End@0x2bc11c |
| +8 | 4 | f32 | begin | parse |  |  |  | W:Parse@0x2bcc68 R:Begin@0x2bc8a4 |
| +12 | 1 | u8 | begin,end,parse,tick | begin,end,parse | signed-cmp,unsigned-load | and:0xfffffc03 and:0xfffffffd and:0xfffffffe andi:0x1 | arg:Q23std21allocator<9CAiMapLoc>>Fv(t3) cmp:slt cmp:slti cmpeq fld | R:Parse@0x2bcc38 W:Parse@0x2bcc44 R:Parse@0x2bcc58 (+7) |
| +12 | 2 | u16 | begin,parse | parse | signed-cmp,unsigned-load | and:0xfffffc03 and:0xfffffffd and:0xfffffffe andi:0x1 | arg:Q23std21allocator<9CAiMapLoc>>Fv(t3) cmp:slt cmp:slti cmpeq fld | R:Parse@0x2bcc48 W:Parse@0x2bcc54 R:Begin@0x2bc3cc (+1) |
| +13 | 1 | u8 | begin,parse | parse | unsigned-load | and:0xffffff7f and:0xffffffbf and:0xffffffc3 andi:0xff | arg:Q23std21allocator<9CAiMapLoc>>Fv(a3) arg:Q23std21allocator<9CAiMapLoc>>Fv(t1) cmpeq fld | R:Parse@0x2bcc6c W:Parse@0x2bcc78 R:Parse@0x2bcc7c (+8) |
| +16 | 4 | u32 | begin | parse | unsigned-cmp | and:0xfff8003f andi:0x1fff andi:0x3f dsll32:0xd | arg:Debug(a3) arg:GetRegion(t1) arg:SetRoute(a3) arg:_saturate<f>(a3) cmp:sltu | W:Parse@0x2bccd8 R:Begin@0x2bc4e8 R:Begin@0x2bc590 (+2) |
| +20 | 4 | u32 | begin | parse |  | and:0xfff8003f andi:0x1fff andi:0x3f sll:0x3 | arg:GetRegion(t1) | W:Parse@0x2bccd8 R:Begin@0x2bc6c4 R:Begin@0x2bc7ac |

Indexed/tail accesses (base offset + variable): +16/w4/u32(begin,parse)

### ai::HOLD

- size: 20; data_size written: [20]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_HOLD : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- typeable functions: `0x2bc030 CTHold::Parse`, `0x2bbf30 CTHold::Begin`, `0x2bbe50 CTHold::Tick`, `0x2bbda0 CTHold::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2bbf44 R:Tick@0x2bbe68 R:End@0x2bbdb0 |
| +8 | 4 | f32 | begin | parse |  |  | float c:0xbf800000 | W:Parse@0x2bc09c W:Parse@0x2bc0d8 W:Parse@0x2bc0e0 (+2) |
| +12 | 4 | f32 | begin | parse |  |  | float c:0x0 | W:Parse@0x2bc0a0 W:Parse@0x2bc0e4 R:Begin@0x2bbfa8 (+1) |
| +16 | 4 | f32 | end,tick | begin,parse,tick |  |  | float c:0x0 fld | W:Parse@0x2bc0a8 W:Begin@0x2bc00c R:Tick@0x2bbedc (+3) |

Callee-written/passed: +8 zrdr_findRfloat(f32*, 8 B) in Parse

### ai::INSTATE

- size: variable, sizeof 16; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_INSTATE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 16 -> trailing char m_name[4] at +12 (min/sizeof 16).
- typeable functions: `0x2bbb00 CTInState::Parse`, `0x2bb9c0 CTInState::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2bb9d4 |
| +8 | 1 | u8 | tick |  | unsigned-load | and:0x80000000 | arg:AiStateIs(a1) arg:FindAiState(a1) arg:strcpy(a3) | R:Tick@0x2bbabc R:Tick@0x2bbad0 |
| +8 | 4 | u32 | parse | parse |  | and:0x80000000 | arg:AiStateIs(a1) arg:FindAiState(a1) arg:strcpy(a3) fld | R:Parse@0x2bbc08 W:Parse@0x2bbc14 |
| +11 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xffffff7f dsll32:0x18 dsrl32:0x1f | arg:strcpy(a2) cmpeq fld | R:Parse@0x2bbc18 W:Parse@0x2bbc28 R:Tick@0x2bbaa8 |
| +12 | 1 | u8 | tick | parse | signed-load |  | cmpeq c:0x0 | W:Parse@0x2bbc3c R:Tick@0x2bba2c R:Tick@0x2bba34 |

Callee-written/passed: +12 GetEntity(char*) in Tick; +12 strcpy(char*) in Parse

### ai::INVIEW

- size: variable, sizeof 20; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_INVIEW : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 20 -> trailing char m_name[4] at +16 (min/sizeof 20).
- typeable functions: `0x2bb800 CTInView::Parse`, `0x2bb680 CTInView::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +8 | 4 | u32 | tick | parse | unsigned-cmp | andi:0xff xor:0x0 | cmp:sltiu c:0x0 | W:Parse@0x2bb988 R:Tick@0x2bb6e0 |
| +12 | 4 | u32 | tick | parse |  | and:None | arg:strlen(a1) cmpeq ret:ParseTeamBlock | W:Parse@0x2bb994 R:Tick@0x2bb708 |
| +16 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2bb940 |

Callee-written/passed: +16 GetEntity(char*) in Tick; +16 strcpy(char*) in Parse; +16 strlen(char*) in Tick

Indexed/tail accesses (base offset + variable): +16/w1/u8(parse)

### ai::LOOKAT

- size: variable, sizeof 48; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_LOOKAT : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 48 -> trailing char m_name[4] at +44 (min/sizeof 48).
- unexplained gaps: +25..+27
- typeable functions: `0x2bb1c0 CTLookAt::Parse`, `0x2bb0b0 CTLookAt::Begin`, `0x2badf0 CTLookAt::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2bb0cc R:Tick@0x2bae18 |
| +8 | 4 | f32 | begin | parse |  |  | float c:0x0 | W:Parse@0x2bb2bc W:Parse@0x2bb640 R:Begin@0x2bb16c (+1) |
| +12 | 4 | f32 | begin | parse |  |  | float c:0x0 | W:Parse@0x2bb2c4 W:Parse@0x2bb648 R:Begin@0x2bb14c (+1) |
| +16 | 4 | f32 | tick | begin,parse,tick |  |  | arg:SetLookTimer(f12) float c:0x0 fld | W:Parse@0x2bb2b8 W:Begin@0x2bb19c R:Tick@0x2bafd0 (+3) |
| +20 | 4 | f32 | tick | parse |  |  | arg:SetLookRate(f12) c:0x3f59999a | W:Parse@0x2bb2b4 R:Tick@0x2bafb4 |
| +24 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xfffffff0 andi:0xf | cmpeq fld | R:Parse@0x2bb278 W:Parse@0x2bb288 R:Parse@0x2bb2e4 (+10) |
| +27 | 1 | u8 | tick | parse | unsigned-load |  | arg:SetLookDirW(a2) ret:GetDirByName | W:Parse@0x2bb5f8 R:Tick@0x2baf98 |
| +28 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2bb324 W:Parse@0x2bb5b4 |
| +32 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2bb32c W:Parse@0x2bb5bc |
| +36 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2bb334 W:Parse@0x2bb5c4 |
| +40 | 4 | u32 | tick | parse,tick |  |  | arg:GetEntityById(a1) arg:SetLookRate(a1) arg:SetLookTimer(a1) arg:jalr:t9(a1) cmpeq | W:Parse@0x2bb2a4 R:Tick@0x2baee0 W:Tick@0x2baf20 (+1) |
| +44 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2bb2d8 |

Callee-written/passed: +20 zrdr_findreal(f32*, 4 B) in Parse; +28 GetCellCenter(CPnt3D*, 12 B) in Parse; +28 SetLookPosW(CPnt3D*, 12 B) in Tick; +44 GetEntity(char*) in Tick; +44 strcasecmp(char*) in Tick; +44 strcpy(char*) in Parse

### ai::MACRO

- size: variable, sizeof 20; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_MACRO : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 20 -> trailing char m_name[4] at +16 (min/sizeof 20).
- alignment/tail padding (not accessed): +13..+16
- typeable functions: `0x2bacd0 CTMacro::Parse`, `0x2babe0 CTMacro::Begin`, `0x2baa30 CTMacro::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2babf8 R:Tick@0x2baa54 |
| +8 | 4 | ptr? | tick | begin,parse |  |  | arg:ActivateArg(a0) cmpeq c:0x0 ret:GetAnim | W:Parse@0x2bad9c W:Begin@0x2bacac R:Tick@0x2baabc |
| +12 | 1 | u8 | parse | parse | unsigned-load | and:0xfffffffe | arg:strcpy(a2) fld | R:Parse@0x2bada0 W:Parse@0x2badb0 |
| +16 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2badc4 |

Callee-written/passed: +16 GetAnim(char*) in Begin; +16 strcpy(char*) in Parse; +16 strlen(char*) in Begin

### ai::MAP

- size: 20; data_size written: [20]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_MAP : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- alignment/tail padding (not accessed): +9..+12
- typeable functions: `0x2ba8a0 CTMap::Parse`, `0x2ba710 CTMap::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +8 | 1 | u8 | tick | parse | unsigned-load |  | cmpeq c:0x1 c:0x2 | W:Parse@0x2ba91c W:Parse@0x2baa00 R:Tick@0x2ba72c |
| +12 | 1 | u8 | tick |  | unsigned-load |  | arg:SetRegionType(a2) | R:Tick@0x2ba86c |
| +12 | 4 | u32 |  | parse |  |  | arg:SetRegionType(a2) c:0x1 | W:Parse@0x2baa0c |
| +16 | 4 | u32 |  | parse |  |  |  | W:Parse@0x2baa08 |

Callee-written/passed: +16 GetRegion(?) in Tick

### ai::MOVE

- size: 44; data_size written: [44]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_MOVE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: 44: TASK_HDR, CPnt3D(+8), CPnt3D(+20), f32(+32), node_ref int(+36), u8 type/flags(+40, low nibble switch), pad.
- alignment/tail padding (not accessed): +41..+44
- typeable functions: `0x2ba460 CTMove::Parse`, `0x2b9c90 CTMove::Begin`, `0x2b9bd0 CTMove::Tick`, `0x2b9b30 CTMove::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end,tick | parse |  |  | arg:taskFindParam(a1) c:0x0 | W:Parse@0x2ba6f0 R:Begin@0x2b9cac R:Tick@0x2b9bec (+1) |
| +8 | 4 | f32 | begin | parse |  |  | float | W:Parse@0x2ba4f0 R:Begin@0x2b9f60 |
| +12 | 4 | f32 | begin | parse |  |  | float | W:Parse@0x2ba4fc R:Begin@0x2b9f78 |
| +16 | 4 | f32 | begin | parse |  |  | float | W:Parse@0x2ba508 R:Begin@0x2b9fa0 |
| +20 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2ba518 |
| +24 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2ba524 |
| +28 | 4 | f32 |  | parse |  |  |  | W:Parse@0x2ba530 |
| +32 | 4 | f32 | begin | parse |  |  | arg:Scale(f12) c:0x0 | W:Parse@0x2ba510 R:Begin@0x2b9ee0 R:Begin@0x2ba184 (+1) |
| +36 | 4 | index:node_ref | begin | parse |  |  | arg:GetNode(a1) arg:taskFindParam(a1) c:0x0 ret:LoadNodeNames | W:Parse@0x2ba534 W:Parse@0x2ba570 R:Begin@0x2b9d7c (+2) |
| +40 | 1 | u8 | begin,parse | parse | unsigned-load | and:0xffffffdf and:0xfffffff0 andi:0xf | arg:zrdr_findstring(a3) arg:zrdr_findstring(t1) cmpeq fld | R:Parse@0x2ba4dc W:Parse@0x2ba4e8 R:Parse@0x2ba538 (+12) |

Callee-written/passed: +4 zrdr_finduint(int*, 4 B) in Parse; +8 Scale(CPnt3D*, 12 B) in Begin; +8 zrdr_findPNT3D(CPnt3D*, 12 B) in Parse; +20 zrdr_findPNT3D(CPnt3D*, 12 B) in Parse; +32 zrdr_findreal(f32*, 4 B) in Parse; +36 zrdr_toINT(int*, 4 B) in Parse

Indexed/tail accesses (base offset + variable): +12/w4/f32(begin), +16/w4/f32(begin), +24/w4/f32(begin), +28/w4/f32(begin), +36/w4/f32(begin), +40/w4/f32(begin), +48/w4/f32(begin), +52/w4/f32(begin), +60/w4/f32(begin), +64/w4/f32(begin), +72/w4/f32(begin), +76/w4/f32(begin)

### ai::PAINT

- size: 20; data_size written: [20]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_PAINT : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- typeable functions: `0x2b98d0 CTPaint::Parse`, `0x2b9820 CTPaint::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +8 | 4 | u32 |  | parse |  |  |  | W:Parse@0x2b9964 |
| +12 | 4 | u32 | parse,tick | parse |  | ori:0x4 ori:0x8 | arg:Tile(a3) c:0x0 c:0x1 fld | W:Parse@0x2b996c R:Parse@0x2b99c8 W:Parse@0x2b99d4 (+4) |
| +16 | 1 | u8 | tick |  | unsigned-load |  | arg:SetRegionType(a2) arg:Tile(a2) | R:Tick@0x2b989c |
| +16 | 2 | u16 | tick | parse | unsigned-load |  | arg:SetRegionType(a2) arg:Tile(a2) c:0x0 c:0x1 | W:Parse@0x2b9968 W:Parse@0x2b99c4 W:Parse@0x2b9a10 (+2) |
| +18 | 1 | u8 | tick | parse | unsigned-load |  | cmpeq c:0x0 c:0x1 c:0x2 c:0x3 | W:Parse@0x2b9970 W:Parse@0x2b99bc W:Parse@0x2b9a08 (+2) |
| +19 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2b9974 |

Callee-written/passed: +8 GetRegion(?) in Tick

### ai::PARAM

- size: variable, sizeof 20; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_PARAM : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 20 -> trailing char m_name[4] at +16 (min/sizeof 20).
- typeable functions: `0x2b93d0 CTParam::Parse`, `0x2b8230 CTParam::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick | parse |  |  | arg:SetSprayTimer(a1) arg:fptosi(a1) arg:jalr:t9(a1) arg:taskFindParam(a1) c:0x0 | W:Parse@0x2b966c R:Tick@0x2b829c |
| +8 | 2 | u16 | tick | parse | unsigned-cmp,unsigned-load | sll:0x2 | cmp:sltiu | W:Parse@0x2b9630 R:Tick@0x2b8330 R:Tick@0x2b84c0 |
| +10 | 1 | u8 | tick |  | unsigned-cmp,unsigned-load | andi:0xff sll:0x2 | cmp:sltiu cmpeq | R:Tick@0x2b8300 |
| +10 | 2 | u16 |  | parse | unsigned-cmp | andi:0xff sll:0x2 | cmp:sltiu cmpeq | W:Parse@0x2b9634 |
| +12 | 4 | f32 | tick | parse |  |  | arg:SetAiAware(f12) arg:SetHealth(f12) arg:SetSprayTimer(f12) arg:fptosi(f12) float | W:Parse@0x2b963c R:Tick@0x2b835c R:Tick@0x2b8374 (+24) |
| +16 | 1 | u8 | tick | parse | signed-load |  | cmpeq c:0x0 | W:Parse@0x2b9650 R:Tick@0x2b8250 |

Callee-written/passed: +4 zrdr_finduint(int*, 4 B) in Parse; +16 GetEntity(char*) in Tick; +16 strcpy(char*) in Parse

### ai::PURSUE

- size: 12; data_size written: [12]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_PURSUE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- typeable functions: `0x2b81a0 CTPursue::Parse`, `0x2b80b0 CTPursue::Begin`, `0x2b8000 CTPursue::Tick`, `0x2b7f80 CTPursue::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2b80c4 R:Tick@0x2b8014 R:End@0x2b7f8c |
| +8 | 4 | f32 | begin | parse |  |  | c:0xbf800000 | W:Parse@0x2b8210 R:Begin@0x2b8158 R:Begin@0x2b8160 |

Callee-written/passed: +8 zrdr_findreal(f32*, 4 B) in Parse

### ai::ANIMATE

- size: variable, sizeof 40; data_size written: -; variable tail: no; timeless set: False; quad_align set: True; grade: **B**
- proposed: `TASK_PLAY : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: CTPlay::Create(count, list, f, f): size = 40 + 4*(count-1) -> fixed 36 + uint m_list[count] at +36 (trailing [1] idiom).
- typeable functions: `0x2b7c40 CTPlay::Parse`, `0x2b7dd0 CTPlay::Create`, `0x2b7ae0 CTPlay::Begin`, `0x2b7640 CTPlay::Tick`, `0x2b7a10 CTPlay::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end,tick | parse |  |  | arg:taskFindParam(a1) c:0x0 | W:Parse@0x2b7da0 R:Begin@0x2b7afc R:Tick@0x2b766c (+1) |
| +8 | 4 | f32 | begin | parse |  |  | float | W:Create@0x2b7f48 R:Begin@0x2b7b9c R:Begin@0x2b7bc0 |
| +12 | 4 | f32 | begin | parse |  |  | float c:0x0 | W:Create@0x2b7f4c R:Begin@0x2b7b7c R:Begin@0x2b7bb8 |
| +16 | 4 | f32 | begin | parse |  |  | float | W:Create@0x2b7f50 R:Begin@0x2b7bf0 R:Begin@0x2b7c14 |
| +20 | 4 | f32 | begin | parse |  |  | float c:0x0 | W:Create@0x2b7f54 R:Begin@0x2b7bd0 R:Begin@0x2b7c0c |
| +24 | 4 | f32 | tick | begin,tick |  |  | float fld | W:Begin@0x2b7bcc R:Tick@0x2b76e8 W:Tick@0x2b7718 |
| +28 | 4 | f32 | tick | begin,tick |  |  | float fld | W:Begin@0x2b7c20 R:Tick@0x2b7804 R:Tick@0x2b79b4 (+2) |
| +32 | 1 | u8 | end |  | unsigned-load | and:0xfffe01ff and:0xfffffe01 andi:0x1 dsll32:0x17 | cmpeq | R:End@0x2b7aac |
| +32 | 2 | u16 | parse,tick | parse | unsigned-load | and:0xfffe01ff and:0xfffffe01 andi:0x1 dsll32:0x17 | cmpeq fld | R:Create@0x2b7e70 W:Create@0x2b7e80 R:Tick@0x2b771c |
| +32 | 4 | u32 | parse | parse |  | and:0xfffe01ff and:0xfffffe01 andi:0x1 dsll32:0x17 | cmpeq fld | R:Create@0x2b7f28 W:Create@0x2b7f44 |
| +36 | 4 | u32 | tick | parse | signed-cmp | dsll32:0x10 dsra32:0x10 | cmp:bgez cmpeq c:0xffffffff | W:Parse@0x2b7d4c W:Create@0x2b7eb8 R:Tick@0x2b7764 |
| +40 | 4 | u32 |  | parse |  |  | c:0xffffffff | W:Parse@0x2b7d4c W:Create@0x2b7ec0 |
| +44 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ec8 |
| +48 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ed0 |
| +52 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ed8 |
| +56 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ee0 |
| +60 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ee8 |
| +64 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ef4 |
| +68 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7eb8 |
| +72 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ec0 |
| +76 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ec8 |
| +80 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ed0 |
| +84 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ed8 |
| +88 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ee0 |
| +92 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ee8 |
| +96 | 4 | u32 |  | parse |  |  |  | W:Create@0x2b7ef4 |

Callee-written/passed: +4 zrdr_finduint(int*, 4 B) in Parse; +8 zrdr_findRfloat(f32*, 8 B) in Parse; +16 zrdr_findRfloat(f32*, 8 B) in Parse

Indexed/tail accesses (base offset + variable): +36/w4/u32(parse,tick), +40/w4/u32(parse), +44/w4/u32(parse), +48/w4/u32(parse), +52/w4/u32(parse), +56/w4/u32(parse), +60/w4/u32(parse), +64/w4/u32(parse)

### ai::INRANGE

- size: variable, sizeof 20; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_RANGE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 20 -> trailing char m_name[4] at +16 (min/sizeof 20).
- typeable functions: `0x2b55d0 CTRange::Parse`, `0x2b53f0 CTRange::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b5414 |
| +8 | 4 | f32 | tick | parse |  |  | float | W:Parse@0x2b56a0 R:Tick@0x2b5584 |
| +12 | 4 | u32 | tick | parse,tick |  |  | arg:GetEntityById(a1) arg:jalr:t9(a1) cmpeq | W:Parse@0x2b56bc R:Tick@0x2b548c W:Tick@0x2b54cc (+1) |
| +16 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2b56d8 |

Callee-written/passed: +16 GetEntity(char*) in Tick; +16 strcasecmp(char*) in Tick; +16 strcpy(char*) in Parse

### ai::INREGION

- size: variable, sizeof 28; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_REGION : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 28 -> trailing char m_name[4] at +24 (min/sizeof 28).
- typeable functions: `0x2b5260 CTRegion::Parse`, `0x2b4c50 CTRegion::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b4e5c |
| +8 | 1 | u8 | tick |  | unsigned-cmp,unsigned-load | andi:0x3f xor:None | cmp:sltiu | R:Tick@0x2b4d64 R:Tick@0x2b4f98 R:Tick@0x2b5130 |
| +8 | 4 | u32 |  | parse | unsigned-cmp | andi:0x3f xor:None | cmp:sltiu | W:Parse@0x2b5368 |
| +12 | 4 | ptr | tick | parse,tick |  |  | cmpeq deref+0 deref+2 deref+4 deref+6 | W:Parse@0x2b536c R:Tick@0x2b4c70 W:Tick@0x2b4ca8 (+1) |
| +16 | 1 | u8 | tick | parse | unsigned-load | and:None sllv:0x1 | cmpeq c:0x0 | W:Parse@0x2b5370 R:Tick@0x2b4e30 |
| +17 | 1 | u8 | tick | parse,tick | unsigned-cmp,unsigned-load | xor:None | cmp:sltiu c:0x0 | W:Parse@0x2b53a0 R:Tick@0x2b4c80 W:Tick@0x2b4c94 |
| +18 | 2 | u16 | tick | parse | unsigned-load |  | cmpeq c:0x0 | W:Parse@0x2b5378 W:Parse@0x2b53cc R:Tick@0x2b4ccc (+1) |
| +20 | 4 | u32 | tick | parse,tick |  |  | arg:GetEntityById(a1) cmpeq | W:Parse@0x2b5394 R:Tick@0x2b4e40 W:Tick@0x2b4ec0 (+1) |
| +24 | 1 | u8 |  | parse,tick |  |  | c:0x0 | W:Parse@0x2b53b4 W:Tick@0x2b4f10 |

Callee-written/passed: +8 GetRegion(?) in Tick; +24 GetEntity(char*) in Tick; +24 strcasecmp(char*) in Tick; +24 strcpy(char*) in Parse

### ai::SELECT

- size: 16; data_size written: [16]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `?`
- typeable functions: `0x2b74b0 CTSelect::Parse`, `0x2b74a0 CTSelect::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +8 | 4 | u32 |  | parse |  |  | c:0x0 ret:jalr:t9 | W:Parse@0x2b7510 W:Parse@0x2b7560 W:Parse@0x2b7568 |
| +12 | 4 | u32 |  | parse |  |  | c:0x0 | W:Parse@0x2b750c W:Parse@0x2b7544 |

### ai::SETMODE

- size: 12; data_size written: [12]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_SETMODE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- typeable functions: `0x2b73a0 CTSetMode::Parse`, `0x2b7250 CTSetMode::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick | parse |  |  | arg:taskFindParam(a1) c:0x0 | W:Parse@0x2b747c R:Tick@0x2b7274 |
| +8 | 1 | u8 | tick |  | unsigned-load |  | arg:SetAiMode(a1) cmpeq | R:Tick@0x2b72f4 |
| +8 | 4 | u32 | tick | parse |  |  | arg:SetAiMode(a1) cmpeq c:0x1 | W:Parse@0x2b7400 W:Parse@0x2b7464 R:Tick@0x2b7324 |

Callee-written/passed: +4 zrdr_finduint(int*, 4 B) in Parse

### ai::SETANIMSET

- size: variable, sizeof 16; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_SETANIMSET : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 16 -> trailing char m_name[4] at +12 (min/sizeof 16).
- alignment/tail padding (not accessed): +9..+12
- typeable functions: `0x2b7130 CTSetAnimSet::Parse`, `0x2b7050 CTSetAnimSet::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b7074 |
| +8 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xfffffffe andi:0x1 | arg:strcpy(a2) cmpeq fld | R:Parse@0x2b7200 W:Parse@0x2b7210 R:Tick@0x2b70f4 |
| +12 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2b7224 |

Callee-written/passed: +12 BindAnimSet(char*) in Tick; +12 strcpy(char*) in Parse

### ai::SIGNAL

- size: variable, sizeof 16; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_SIGNAL : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 16 -> trailing char m_name[4] at +12 (min/sizeof 16).
- typeable functions: `0x2b6d60 CTSignal::Parse`, `0x2b6c50 CTSignal::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b6c68 |
| +8 | 1 | u8 | tick |  | unsigned-load |  | arg:AnimSignal(a2) | R:Tick@0x2b6d34 |
| +8 | 4 | u32 |  | parse |  |  | arg:AnimSignal(a2) | W:Parse@0x2b6f14 |
| +12 | 1 | u8 | tick | parse | signed-load |  | cmpeq c:0x0 | W:Parse@0x2b6f28 R:Tick@0x2b6cc0 R:Tick@0x2b6cc8 |

Callee-written/passed: +12 GetEntity(char*) in Tick; +12 strcpy(char*) in Parse

### ai::SOUND

- size: variable, sizeof 20; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_SOUND : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 20 -> trailing char m_name[4] at +16 (min/sizeof 20).
- typeable functions: `0x2b6840 CTSound::Parse`, `0x2b6820 CTSound::Begin`, `0x2b64b0 CTSound::Tick`, `0x2b67e0 CTSound::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b64e0 |
| +8 | 1 | u8 | parse,tick | parse | signed-cmp,unsigned-cmp,unsigned-load | and:0xfffe01ff and:0xfffffffb and:0xfffffffd and:0xfffffffe | arg:zrdr_findtag(t0) cmp:slt cmp:sltu cmpeq fld | R:Parse@0x2b6b9c W:Parse@0x2b6bb0 R:Parse@0x2b6bcc (+7) |
| +8 | 4 | u32 | parse,tick | parse | signed-cmp,unsigned-cmp | and:0xfffe01ff and:0xfffffffb and:0xfffffffd and:0xfffffffe | arg:zrdr_findtag(t0) cmp:slt cmp:sltu cmpeq fld | R:Parse@0x2b6b50 W:Parse@0x2b6b7c R:Tick@0x2b6598 |
| +9 | 1 | u8 | begin,tick | begin,tick | unsigned-load | and:0xfffffffe andi:0x1 | cmpeq fld | R:Begin@0x2b6820 W:Begin@0x2b6834 R:Tick@0x2b6514 (+3) |
| +10 | 2 | u16 | parse,tick | parse | unsigned-load | and:0xfffffe01 dsll32:0x17 dsrl32:0x18 | arg:zrdr_findtag(a2) fld | R:Parse@0x2b6b80 W:Parse@0x2b6b90 R:Tick@0x2b6558 |
| +12 | 4 | u32 | end,tick | begin,end,tick |  |  | arg:IsPlaying(a0) arg:TerminateOnFinish(a0) cmpeq c:0x0 ret:jalr:t9 | W:Begin@0x2b683c W:Tick@0x2b671c W:Tick@0x2b6758 (+3) |
| +16 | 1 | u8 | tick | parse | signed-load |  | cmpeq c:0x0 | W:Parse@0x2b6a60 W:Parse@0x2b6b28 R:Tick@0x2b6600 |

Callee-written/passed: +16 GetEntity(char*) in Tick; +16 GetSoundByName(char*) in Tick; +16 strcpy(char*) in Parse; +16 strlen(char*) in Parse,Tick

Indexed/tail accesses (base offset + variable): +16/w1/u8(parse,tick)

### ai::STANCE

- size: 24; data_size written: [24]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_STANCE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- typeable functions: `0x2b6010 CTStance::Parse`, `0x2b5f70 CTStance::Begin`, `0x2b5de0 CTStance::Tick`, `0x2b5eb0 CTStance::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2b5f88 R:Tick@0x2b5df8 R:End@0x2b5ec8 |
| +8 | 4 | u32 | begin,end | parse |  |  | cmpeq | W:Parse@0x2b612c R:Begin@0x2b5fec R:End@0x2b5f40 |
| +12 | 1 | u8 | begin |  | signed-load |  | arg:SetStance(a1) | R:Begin@0x2b5fe8 |
| +12 | 4 | u32 |  | parse |  |  | arg:SetStance(a1) | W:Parse@0x2b6130 |
| +16 | 4 | f32 | begin,end | parse |  |  | float | W:Parse@0x2b6128 R:Begin@0x2b5ff4 R:End@0x2b5f24 |
| +20 | 4 | f32 | tick | begin,tick |  |  | float fld | W:Begin@0x2b5ff8 R:Tick@0x2b5e6c W:Tick@0x2b5e7c (+1) |

### ai::STATE

- size: variable, sizeof 40; data_size written: -; variable tail: no; timeless set: False; quad_align set: False; grade: **B**
- proposed: `TASK_STATE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Variable size = align4(strlen(name)) + 40 -> trailing char m_name[4] at +36 (min/sizeof 40).
- unexplained gaps: +16..+20
- typeable functions: `0x2b5bd0 CTState::Parse`, `0x2b5820 CTState::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b584c |
| +8 | 1 | u8 | tick |  | unsigned-load | andi:0xff | arg:PushAiState(a1) cmpeq | R:Tick@0x2b58bc |
| +8 | 4 | u32 |  | parse |  | andi:0xff | arg:PushAiState(a1) cmpeq | W:Parse@0x2b5d00 |
| +12 | 4 | u32 | tick | parse |  |  | c:0x4 | W:Parse@0x2b5dac R:Tick@0x2b59ec |
| +20 | 4 | f32 | tick |  |  |  | float | R:Tick@0x2b591c |
| +24 | 4 | f32 | tick | parse |  |  | float c:0x0 | W:Parse@0x2b5d38 R:Tick@0x2b5980 |
| +28 | 4 | u32 |  | parse |  |  | c:0x0 | W:Parse@0x2b5d40 |
| +32 | 4 | u32 |  | parse |  |  | c:0x41a00000 | W:Parse@0x2b5d4c |
| +36 | 1 | u8 |  | parse |  |  | c:0x0 | W:Parse@0x2b5d14 |

Callee-written/passed: +20 zrdr_findreal(f32*, 4 B) in Parse; +24 SetFollowOffset(CPnt3D*, 12 B) in Tick; +24 zrdr_findPNT3D(CPnt3D*, 12 B) in Parse; +24 zrdr_findreal(f32*, 4 B) in Parse; +36 GetEntity(char*) in Tick; +36 strcpy(char*) in Parse; +36 strlen(char*) in Tick

### ai::STOPALL

- size: 12; data_size written: [12]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_STOPALL : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- alignment/tail padding (not accessed): +9..+12
- typeable functions: `0x2b5750 CTStopAll::Parse`, `0x2b5700 CTStopAll::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +8 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xfffffffd and:0xfffffffe andi:0x1 dsll32:0x1e | fld | R:Parse@0x2b57ec W:Parse@0x2b57f8 R:Parse@0x2b57fc (+2) |

### ai::SPECIAL

- size: 12; data_size written: [12]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_SPECIAL : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- alignment/tail padding (not accessed): +10..+12
- typeable functions: `0x2b6450 CTSpecial::Parse`, `0x2b63d0 CTSpecial::Begin`, `0x2b6150 CTSpecial::Tick`, `0x2b62d0 CTSpecial::End`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,end |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2b63e0 R:End@0x2b62e8 |
| +8 | 1 | u8 | tick | begin,end,tick | unsigned-load |  | arg:GetCmd(a1) arg:jalr:v0(a1) c:0x1 | W:Begin@0x2b6428 R:Tick@0x2b6178 R:Tick@0x2b6294 (+2) |
| +9 | 1 | u8 | begin,end,tick | begin,end,tick | unsigned-load | and:0xfffffff0 andi:0xf | cmpeq fld | R:Begin@0x2b642c W:Begin@0x2b643c R:Tick@0x2b61cc (+10) |

### ai::TEAM

- size: 16; data_size written: [16]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_TEAM : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- typeable functions: `0x2b4b40 CTTeam::Parse`, `0x2b49f0 CTTeam::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b4a18 |
| +8 | 4 | u32 | tick | parse |  | and:None nor:0x0 | c:0x0 ret:ftmask_create | W:Parse@0x2b4c18 W:Parse@0x2b4c24 R:Tick@0x2b4ac0 (+1) |
| +12 | 4 | u32 | tick | parse |  |  | cmpeq c:0xffffffff | W:Parse@0x2b4c14 W:Parse@0x2b4c20 R:Tick@0x2b4a94 |

### ai::VALVE

- size: 24; data_size written: [24]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_VALVE : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: 24: TASK_HDR + VALVE_CMD_DATA(12) at +8 (Tick calls VALVE_CMD_DATA::Compare(rec+8)) + u32 valve ref(+20).
- typeable functions: `0x2b4510 CTValve::Parse`, `0x2b4450 CTValve::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | tick |  |  |  | arg:taskFindParam(a1) | R:Tick@0x2b4468 |
| +8 | 4 | index:valve_ref | tick | parse,tick |  |  | arg:GetValve(a1) arg:MakeCallbacks(a0) arg:debugValve(a0) cmpeq deref+0 | W:Parse@0x2b4678 W:Parse@0x2b4778 W:Parse@0x2b4890 (+5) |
| +12 | 4 | index:valve_ref | tick | parse |  |  | arg:GetValve(a1) cmpeq deref+0 deref+4 c:0x0 | W:Parse@0x2b467c W:Parse@0x2b477c W:Parse@0x2b48d8 (+4) |
| +16 | 1 | ptr | tick | parse | unsigned-cmp,unsigned-load | andi:0xff sll:0x2 | arg:GetValue(a0) cmp:sltiu deref+0 deref+8 c:0x1 | W:Parse@0x2b462c W:Parse@0x2b472c W:Parse@0x2b4858 (+1) |
| +17 | 1 | u8 | parse,tick | parse | unsigned-load | and:0xffffffef and:0xfffffff7 and:0xfffffffb and:0xfffffffd | arg:ParseValveName(a3) arg:ParseValveName(t1) arg:fptosi(a3) arg:fptosi(t1) cmpeq | R:Parse@0x2b4634 W:Parse@0x2b4664 R:Parse@0x2b4668 (+35) |
| +20 | 1 | index:valve_ref | tick |  | unsigned-load |  | arg:GetValve(a1) | R:Tick@0x2b44dc |
| +20 | 4 | index:valve_ref |  | parse |  |  | arg:GetValve(a1) | W:Parse@0x2b4628 |

### ai::WAIT

- size: 20; data_size written: [20]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `TASK_WAIT : TASK_HDR (provisional)` (cluster `task-hdr`)
- notes: Record begins with DWARF TASK_HDR (m_cmd hdr, uint m_seal_index +4); begin/tick/end read +4 and pass it to taskFindParam(ai_cmdid[2], idx) to reach the TASK_SELECT record.
- typeable functions: `0x2b4300 CTWait::Parse`, `0x2b4230 CTWait::Begin`, `0x2b4030 CTWait::Tick`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | u32 | begin,tick |  |  |  | arg:taskFindParam(a1) | R:Begin@0x2b4240 R:Tick@0x2b4050 |
| +8 | 4 | f32 | begin,parse,tick | parse |  |  | float | W:Parse@0x2b4388 R:Parse@0x2b43a4 R:Parse@0x2b43c4 (+6) |
| +12 | 4 | f32 | begin,parse,tick | parse |  |  | float | W:Parse@0x2b439c R:Parse@0x2b43b4 R:Parse@0x2b43d8 (+5) |
| +16 | 4 | f32 | tick | begin,parse,tick |  |  | float fld | W:Parse@0x2b43d4 W:Parse@0x2b4428 W:Begin@0x2b42e8 (+3) |

### VALVE

- size: 16; data_size written: [16]; variable tail: no; timeless set: False; quad_align set: False; grade: **A**
- proposed: `_valve_cmp_cmd (provisional) = { hdr; VALVE_CMD_DATA (missing, 12 bytes) at +4 }` (cluster `valve-cmd-data`)
- notes: CmdTickCmp is `j VALVE_CMD_DATA::Compare` with a0 = rec+4. VALVE_CMD_DATA: +0 valve/int, +4 valve/int, +8 u8 operator (jump-table index), +9 u8 flags.
- typeable functions: `0x2f7930 CValve::CmdParseCmp`, `0x2f8160 CValve::CmdTickCmp`, `0x2f8310 VALVE_CMD_DATA::Compare`

| off | w | kind | R | W | sign | bits | evidence | sites |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +4 | 4 | index:valve_ref | tick | parse |  |  | arg:GetValve(a1) arg:MakeCallbacks(a0) arg:debugValve(a0) cmpeq deref+0 | W:CmdParseCmp@0x2f7ab8 W:CmdParseCmp@0x2f7ad0 W:CmdParseCmp@0x2f7c98 (+6) |
| ?+8 | 1 | index:valve_ref | tick |  | unsigned-cmp,unsigned-load | andi:0xff sll:0x2 | arg:GetValue(a0) arg:GetValve(a1) cmp:sltiu cmpeq deref+0 | R:Compare@0x2f83c4 |
| +8 | 4 | index:valve_ref | tick | parse | unsigned-cmp | andi:0xff sll:0x2 | arg:GetValue(a0) arg:GetValve(a1) cmp:sltiu cmpeq deref+0 | W:CmdParseCmp@0x2f7ad8 W:CmdParseCmp@0x2f7cb8 W:CmdParseCmp@0x2f7f70 (+3) |
| +9 | 1 | u8 | tick |  | unsigned-load | andi:0x1 dsll32:0x1b dsll32:0x1c dsll32:0x1d | cmpeq | R:Compare@0x2f832c R:GetValue@0x2f8610 |
| +12 | 1 | ptr | tick | parse | unsigned-cmp,unsigned-load | andi:0xff sll:0x2 | arg:GetValue(a0) cmp:sltiu deref+0 deref+8 c:0x1 | W:CmdParseCmp@0x2f7a78 W:CmdParseCmp@0x2f7c54 W:CmdParseCmp@0x2f7e68 (+1) |
| +13 | 1 | index:valve_ref | parse,tick | parse | unsigned-load | and:0xffffffef and:0xfffffff7 and:0xfffffffb and:0xfffffffd | arg:AddValve(a2) arg:Create(a2) arg:fptosi(a1) arg:fptosi(a2) cmpeq | R:CmdParseCmp@0x2f7a80 W:CmdParseCmp@0x2f7a9c R:CmdParseCmp@0x2f7aa0 (+35) |

## UI sub-command records (ui::UI_COMMAND dispatch)

zAnimLoadUIMenu callocs an 8-byte C2DAnimCmdHdr or returns the record produced by the target control's virtual ParseZAnimCmd; zAnimUIMenuTick calls the control's TickZAnimCmd(this, hdr, dt, bool*).

| function | allocs | accessed offsets (op) |
| --- | --- | --- |
| 0x385eb0 `ParseZAnimCmd::CUIMapCtrl` | {'0': 24, '1': 8, '2': 8} | +2/1 +2/2 +6/1 +8/4 +12/4 +16/4 +20/4 |
| 0x3858e0 `TickZAnimCmd::CUIMapCtrl` | - | +4/2 +6/1 |
| 0x387c00 `ParseZAnimCmd::CPopUpDialog` | {'0': 208} | +2/1 +2/2 +8/1 +9/1 +12/4 +16/4 +40/4 +44/4 +48/4 +52/1 +68/1 +69/1 +70/1 +71/1 +72/1 +73/1 +74/1 +76/4 +80/4 +84/4 +88/4 +92/1 +96/4 +100/4 +104/4 +108/4 +112/4 +116/4 +120/4 +124/4 +128/4 +132/4 +136/4 +140/1 +141/1 +142/1 +144/4 +148/4 +152/4 +156/4 +160/1 +164/4 +168/4 +172/4 +176/4 +180/4 +184/4 +188/4 +192/4 +196/4 +200/4 +204/4 |
| 0x387020 `TickZAnimCmd::CPopUpDialog` | - | +4/2 +8/1 +9/1 +12/4 +16/4 +20/4 +24/4 +28/4 +32/4 +36/4 +40/4 +44/4 +48/4 +68/1 +69/1 +70/1 +71/1 +72/1 +73/1 +74/1 +76/4 +80/4 +84/4 +88/4 +92/1 +96/4 +100/4 +104/4 +108/4 +112/4 +116/4 +120/4 +124/4 +128/4 +132/4 +136/4 +140/1 +141/1 +142/1 +144/4 +148/4 +152/4 +156/4 +160/1 +164/4 +168/4 +172/4 +176/4 +180/4 +184/4 +188/4 +192/4 +196/4 +200/4 +204/4 |
| 0x388e10 `ParseZAnimCmd::CRenderableString` | {'0': 8} | +2/1 +2/2 +6/1 +7/1 |
| 0x388d60 `TickZAnimCmd::CRenderableString` | - | +6/1 +7/1 |
| 0x38af00 `ParseZAnimCmd::CRadioStrip` | {'0': 8, '1': 8} | +2/1 +2/2 +6/1 +7/1 |
| 0x38ad60 `TickZAnimCmd::CRadioStrip` | - | +6/1 +7/1 |
| 0x38c340 `ParseZAnimCmd::CSliderBar` | {'0': 8, '1': 8} | +2/1 +2/2 +6/1 +7/1 |
| 0x38c200 `TickZAnimCmd::CSliderBar` | - | +6/1 +7/1 |
| 0x38c690 `ParseZAnimCmd::CUIListBox` | {'0': 8, '1': 8, '2': 8, '3': 8} | +2/1 +2/2 +6/1 +7/1 |
| 0x38c590 `TickZAnimCmd::CUIListBox` | - | +6/1 |
| 0x38efc0 `ParseZAnimCmd::2DButton` | {'0': 8} | +2/1 +2/2 +6/1 +7/1 |
| 0x38ef20 `TickZAnimCmd::2DButton` | - | +6/1 +7/1 |
| 0x3904e0 `ParseZAnimCmd::TeleType` | {'0': 8, '1': 8} | +2/1 +2/2 +6/1 +7/1 |
| 0x390400 `TickZAnimCmd::TeleType` | - | +6/1 +7/1 |
| 0x392f70 `ParseZAnimCmd::C2DCounter` | {'0': 8, '1': 8, '2': 8} | +2/1 +2/2 +6/1 +7/1 |
| 0x392cf0 `TickZAnimCmd::C2DCounter` | - | +6/1 +7/1 |
| 0x174af0 `ParseZAnimCmd::2D` | - |  |
| 0x174b00 `TickZAnimCmd::2D` | - |  |

## Embedded helper types (accesses relative to the embedded object)

- 0x2b7dd0 `Create__6CTPlayFiPUiff`: +0/2[W:sh] +2/1[R:lbu,W:sb] +2/2[R:lhu,W:sh] +8/4[W:swc1] +12/4[W:sw] +16/4[W:swc1] +20/4[W:sw] +32/2[R:lhu,W:sh] +32/4[R:lw,W:sw] +36/4[W:sw] +40/4[W:sw] +44/4[W:sw] +48/4[W:sw] +52/4[W:sw] +56/4[W:sw] +60/4[W:sw] +64/4[W:sw] +68/4[W:sw] +72/4[W:sw] +76/4[W:sw] +80/4[W:sw] +84/4[W:sw] +88/4[W:sw] +92/4[W:sw] +96/4[W:sw]
- 0x2b7590 `Create__8CTSelectFP10CZSealBody`: +0/2[W:sh] +2/2[R:lhu,W:sh] +8/4[W:sw] +12/4[W:sw]
- 0x1b9b80 `zAnimObjectMotionScriptTick__FP14_zanim_cmd_hdrPf`: +5/1[R:lbu] +7/1[R:lbu] +12/4[W:sw] +16/4[R:lw,W:sw] +56/4[R:lw,W:sw]
- 0x1b9d90 `apply_script_frame__FP27_zanim_object_motion_scriptP16_zanim_si_scriptPQ23zdb5CNodeP25zanim_script_frame_headerfPf`: +4/1[R:lbu] +12/4[R:lwc1,W:sw,W:swc1] +16/4[R:lw,W:sw] +20/4[R:lwc1] +24/4[R:lwc1] +28/4[R:lwc1] +56/4[R:lw,W:sw]
- 0x1baf10 `Tick__15CZAnimFromToAccFfP6CPnt3D`: +4/4[R:lwc1] +12/4[R:lwc1] +16/4[R:lwc1] +20/4[R:lwc1] +24/4[R:lwc1] +32/4[R:lwc1,W:sw,W:swc1] +36/4[R:lwc1,W:swc1] +52/1[R:lbu,W:sb]
- 0x1bb100 `ComputeRunTime__15CZAnimFromToAccFP6CPnt3DP6CPnt3D`: +0/4[R:lwc1] +4/4[R:lwc1] +8/4[R:lwc1] +12/4[R:lwc1] +16/4[R:lwc1] +20/4[R:lwc1,W:swc1] +24/4[W:swc1] +28/4[R:lwc1,W:swc1]
- 0x2f8310 `Compare__14VALVE_CMD_DATAFv`: +0/4[R:lw] +8/1[R:lbu] +9/1[R:lbu]
- 0x2f8600 `GetValue__14VALVE_CMD_DATAFv`: +4/4[R:lw] +9/1[R:lbu]
- 0x1b90e0 `NewCmd__16CZAnimExpressionFPCc`: 

## Type-plan candidates (best first)

1. `VALVE_CMD_DATA` (12 B; mangled class with Compare/GetValue/ParseValveName) - `progress add-type-plan --class VALVE_CMD_DATA` route; unlocks VALVE (hdr + VALVE_CMD_DATA) and ai::VALVE (TASK_HDR + VALVE_CMD_DATA + u32) and 5 functions.
2. AI task records deriving from DWARF `TASK_HDR` (precedent: `TASK_SELECT : TASK_HDR`): grade-A fixed sizes first - TASK_WAIT(20), TASK_HOLD(20), TASK_PURSUE(12), TASK_SETMODE(12), TASK_STANCE(24), TASK_TEAM(16), TASK_MOVE(44, also ai::DOOR), TASK_EVENT(36), TASK_PAINT(20), TASK_MAP(20); then the char m_name[4] trailing-string family (DEBUG/INSTATE/SETANIMSET/SIGNAL/INVIEW/MACRO/SOUND/STATE/INRANGE/PARAM/INREGION/LOOKAT) and trailing-array GOTO/PLAY. ~80 callbacks become typeable.
3. `CZAnimFromToAcc` (56 B, mangled class) and `_zanim_object_motion_script` (60 B, mangled struct param) - add-type-plan --class / --struct; prerequisites for OBJECT_MOTION_FROM_TO and OBJECT_MOTION_SI_SCRIPT.
4. Small core zanim records with shared layouts (all grade A, 8-20 B): u8-callanim-8 (STOP/PAUSE/RESUME/INVALIDATE_ANIMATION), u8-name-8 (CALL/STOP_SEQUENCE, HUD_TRIGGER_MISSION_CAM), u16-state-u16-node-8 (NODE_ACTIVE, OBJECT_ACTIVE_STATE), u16-u8-u8-8 (OBJECT_ADD/DELETE_CHILD), u16-u8-u8-pnt3d-20 (OBJECT_TRANSLATE/ROTATE_STATE), switch-bits-8 (HUD_*, PLAYER_CONTROLS; same shape as DWARF _camera_control_cmd), TIMER/RANDOM_WEIGHT/HUD_START_DEFUSE_TIMER.
5. Large grade-A core records: CAMERA(132) [user example zAnimCameraTick/Begin], SOUND(32), FIRE_WEAPON(44), RANGE_TEST(40), DESTRUCTION_SOURCE(80), WIND(68), CALL_ANIMATION(24), OBJECT_OPACITY_FROM_TO(24).
6. Already-DWARF records (CAMERA_PARAMS, DYNAMICS_*_CAMERA, SET_CAMERA_REGION_TEST, UI_COMMAND/C2DAnimCmdHdr): no new type; only check that callback locals/casts are applied in Ghidra.

## Caveats

- Field kinds come from a forward may-dataflow over `recon asm`; registers merged from several paths are flagged `?`. Loop-carried pointers are widened to indexed accesses; values read only via the ZAnim cursor (IF family, expressions) are described in notes, not tables.
- Signedness: lb/lh vs lbu/lhu and slt/bltz vs sltu compare use only; MWCC often uses lhu for u16 bitfield-free shorts, so "unsigned-load" alone does not prove unsigned.
- Bit masks show the RMW pattern (and ~mask / ori bit) and extraction shifts (dsll32/dsrl32); bitfield names are unknown outside the camera module.
- Variable-size AI records: sizeof inferred from `align4(strlen)+K` / `4*(n-1)+K` formulas (trailing [4]/[1] idiom); exact member arrays need confirmation.
- Group status and live signatures are a snapshot; other jobs were applying groups during the scan.
