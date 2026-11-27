# New release functions placed in a class: name proposals

Name proposals for the release functions (SCUS-971.34) that have no prototype counterpart and that evidence places in a class, for the user to check against each body. Written by the agent `socom-release-newnames-p1` on commit 754aef14, from `build/release/unnamed/unnamed-membership.json` (627 unnamed new functions), read-only reads of the release and prototype programs, the release virtual tables and the stage-2 checker notes. 240 functions: tier A (independent evidence: a virtual table, or calls that hand the first argument on) 150, tier B (both neighbours of one class, nothing else) 90. Confidence: high 46, medium 136, low 58. Basis: a virtual-table slot 42, an earlier note checked against the body 162, the body alone 36. 8 get a neutral `fn_<address>` name. 30 rows carry another class than the membership data gave, said in the class and basis columns; the doubtful ones are listed at the end. One function was left out: 0x260430 (CAiState / CAiSRescued neighbours; the evidence names both CSealCtrlAi and CSealCtrl).

Reading the slots: the release added virtuals to several base classes (CAiState at +0xc, +0x30, +0x34; CEntity at +0x24, +0x34, +0x38; C2D at +0x20; CSnd at +0x2c; the CListItem*TypeImpl tables at +0x18), so the later slots of the release tables sit one or more places after the prototype's. A slot name here is the name the release base table holds in the same slot (those functions are named by their own bodies), not the prototype's slot at the same offset. An override of a new virtual takes the name proposed for its base. Offsets are hexadecimal; `this` is the first argument.

## src/Apps/FTS/game/headset.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 1 | 0x309c50 | `Headset` | B | `StopCurrent` | clears +0xb and, when the current line (+0x10) is playing, sets the stop flag (+0xa) | small-2.md proposed it; caller CZSealBody::OnDeath | medium |
| 2 | 0x30aa90 | `Headset` | B | `OpenStream` | offline: starts the headset audio stream (snd_DoExternCall, 11025 Hz); online: marks it unavailable; then state 3 | small-2.md proposed it; caller CSnd::Open | medium |
| 3 | 0x30ab10 | `Headset` | B | `FindDevice` | (out device, out interface, out id): enumerates USB audio devices (lgAudEnumerate) for a 16-bit, 11025 Hz one; returns 1 and the indices, else 0 | small-2.md proposed it; callers ftsGetHeadset (before it creates the headset), DisconnectedTick | medium |

## src/Apps/FTS/game/orders.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 4 | 0x173940 | `C2D` | A | `SetNode` | empty (jr ra); slot 0x20 of all 51 C2D-family tables; CUIMapCtrl (0x3b1760) and CBmpWithNode (0x3c3390) override it to store their argument (+0x210 / +0xa0) | new C2D virtual, no base or prototype slot name; small-2.md guessed SetNode (callers pass the node just created); the overrides only store one word | low |

## src/Apps/FTS/hud/hud_main.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 5 | 0x3d79c0 | `CHUD` | A | `UpdateZoomText` | gets the current item's zoom (CZKit::GetCurZoom; 9.0 for kind 3), hides the text at +0x504 at 1.5x or less, else prints "ZOOM: %2.1fx" into it | hud.md proposed it; callers ZoomIn, ZoomOut | medium |

## src/Apps/FTS/hud/hud_newhudmap.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 6 | 0x3e5c60 | `CZNewHudMap` | A | `ZoomToCurrentObjective` | centres the full-screen map between the viewer and the current objective (CalcNewMatrix), then scales so the objective fits the screen (Transform, fabsf, ftsGetTacMapZoomFar) | hud.md proposed it (split out of TickFullScreenMap, its caller) | medium |

## src/Apps/FTS/hud/hud_scorepopup.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 7 | 0x4201f0 | `@unnamed@hud_scorepopup_cpp@::CHudPopups` | A | `Draw` | (camera): when popups are open, draws the background bitmap and every open popup (vector 0x58d760, virtual Draw) | vtable slot 0xc of CHudPopups; C2D slot 0xc is Draw (hud.md) | high |
| 8 | 0x4206b0 | `(free)` | A | `hudOpenHelpPopup` | (popup record): with no menu open and help windows enabled, sets the pause menu state, stops the rumbler, builds the window bitmap and its C2DString lines, appends it to the open-popup vector | hud.md proposed it; callers hudTickScorePopup and three new hud functions; the membership data gave CHUD | medium |
| 9 | 0x4215c0 | `@unnamed@hud_scorepopup_cpp@::CHudPopups` | A | `~CHudPopups` | deleting destructor: stores the CHudPopups table, C2D::~C2D, deletes when the flag > 0 | vtable slot 0x8 of CHudPopups; C2D slot 0x8 is ~C2D (hud.md) | high |
| 10 | 0x422190 | `std::vector<T*> (T unknown)` | A | `~vector` | vector destructor: frees the buffer (+0x8) through the allocator pair, deletes this when the flag > 0; registered by __sinit_hud_scorepopup.cpp for the vector at 0x58d7e0 | hud.md: one of five new popup vectors' destructors; element types unknown; the membership data gave Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1> | medium |
| 11 | 0x422220 | `std::vector<T*> (T unknown)` | A | `~vector` | the same destructor, for the vector at 0x58d7c0 | hud.md, as 0x422190; the membership data gave Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1> | medium |
| 12 | 0x4222b0 | `std::vector<T*> (T unknown)` | A | `~vector` | the same destructor, for the vector at 0x58d7a0 | hud.md, as 0x422190; the membership data gave Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1> | medium |
| 13 | 0x422340 | `std::vector<T*> (T unknown)` | A | `~vector` | the same destructor, for the vector at 0x58d780 | hud.md, as 0x422190; the membership data gave Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1> | medium |
| 14 | 0x4223d0 | `std::vector<T*> (T unknown)` | A | `~vector` | the same destructor, for the open-popup vector at 0x58d760 | hud.md, as 0x422190; the membership data gave Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1> | medium |

## src/Apps/FTS/main.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 15 | 0x140760 | `CRebootState` | A | `~CRebootState` | deleting destructor: stores the CRebootState table, then CGameState's, frees +0x4 (zgame.h), gives the block back to a small-object pool or deletes it when the flag > 0 | vtable slot 0x8 of CRebootState; CGameState slot 0x8 is ~CGameState; small-1.md and state.md proposed it | high |
| 16 | 0x140980 | `CShutdownState` | A | `~CShutdownState` | the same destructor with the CShutdownState table (0x48c5d0) | vtable slot 0x8 of CShutdownState; CGameState slot 0x8 is ~CGameState; small-1.md, state.md | high |
| 17 | 0x1416d0 | `CGameMenu` | A | `Reboot` | no argument used: 0x30c310 (IOP shutdown), CPipe::Uninit, scePadEnd, sceCdInit(5), sceSifExitCmd, then LoadExecPS2 of the disc or the host executable by a zSys flag | small-1.md proposed Reboot; body agrees; callers zVid_Assert and CGameMenu::SwitchMenu | medium |

## src/gamez/zAI/ai_map.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 18 | 0x185db0 | `CAiMap` | B | `_reset_cell` | MAP_FOREACH_STRUCT callback: clears the cell action's bits (GetCellAction) and resets the cell type bits (type 0xd -> 1), returns 1 | zAI.md proposed it (neighbours _validate_cell, _reset_rtflag); body agrees | medium |
| 19 | 0x1864e0 | `CAiMap` | B | `GetSoilName` | soil id -> name string by a 14-way switch ("nogo" ... "collision", default "default") | zAI.md proposed it (inverse of GetSoilByName, its caller); body agrees | medium |
| 20 | 0x187010 | `CAiMap` | B | `GetDirDot` | cosine between two 8-way directions: same 1.0, +-1 c, +-2 0, +-3 -c, else -1.0 | zAI.md proposed it (between GetDirQuat and GetDirVec); body agrees | medium |

## src/gamez/zAI/ai_mapwalk.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 21 | 0x1a8e90 | `CAiMap` | A | `ComputeLineVisibility` | WalkLine(location, point) then returns 1 - the saturated accumulated value | zAI.md: a CPnt3D overload of ComputeLineVisibility; called by CAiMaps::ComputeLineVisibility | medium |
| 22 | 0x1a9a80 | `CPnt3D` | A | `_interp<CPnt3D>` | a*(1-t) + b*t with CPnt3D::Scale twice and Add, written to the out point and returned | zAI.md: the CPnt3D instance of ai::_interp (the float instance has the same arguments) | high |

## src/gamez/zAI/ai_path.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 23 | 0x192870 | `CAiPath` | A | `AddAvoidPoints` | from the path's last point walks two lines offset sideways (GetClosestDir, GetDirVec, WalkLine with callback 0x192f70), builds points (0x192e80) and prints the path | zAI.md guess; caller 0x2f9cb0 is the CAiSAvoid goal choice | low |
| 24 | 0x193150 | `CAiPath` | B | `FindPoint` | searches the points (+0x90 count, +0x94 data, 12 bytes each) for the same cell x/z as the location; returns 1 and the index in the out argument | zAI.md proposed it (after PointInPath); body agrees | medium |

## src/gamez/zAnim/zanim_anim.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 25 | 0x1c9770 | `CZAnimEx` | A | `IsAlive` | returns m_health (+0x1c) > 0 | override of the new CNodeEx slot 0x10 (base 0x1d0770 returns false); zAnim.md proposed IsAlive | medium |
| 26 | 0x1d0770 | `zdb::CNodeEx` | A | `IsAlive` | returns false; slot 0x10 of CNodeEx and of CNodeAction, CParticleEx, CSealEx (inherited) | new CNodeEx virtual where the prototype had OnMove; its CZAnimEx override tests health > 0; zAnim.md proposed IsAlive | medium |

## src/gamez/zAnim/zanim_menu.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 27 | 0x1d7490 | `@unnamed@zanim_menu_cpp@` | A | `OnUpdateMpFinalStatsUiVars` | calls TickMpStats of st_mpexit.cpp, returns 1; registered under the key "UpdateMpFinalStatsUiVars" | zAnim.md proposed it; the key string; the membership data gave @unnamed@st_mpexit_cpp@ | medium |
| 28 | 0x1d7a30 | `@unnamed@zanim_menu_cpp@` | B | `GetMissionNumber` | maps a mission prefix ("m6 ", "m8 ", "m5 ", ... "m16") to a two-digit string, default "UU" | zAnim.md proposed it; caller OnListSavedGames | medium |
| 29 | 0x1d82b0 | `@unnamed@zanim_menu_cpp@` | A | `OnCleanupMissionMemory` | calls CCharacterType::CleanupTemporary, returns 1; registered under the key "CleanupMissionMemory" | zAnim.md proposed it; the key string; the membership data gave CCharacterType | medium |
| 30 | 0x1d9620 | `std::__vector_deleter<CCharacterWeap,std::allocator<CCharacterWeap>>` | B | `~__vector_deleter` | destroys the elements (0x1d9740, a one-byte element loop), frees the buffer at +8, deletes this when the flag > 0 | zAnim.md: a vector destructor of another element type (not the CCharacterWeap instance next to it) | medium |

## src/gamez/zArchive/zar_search.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 31 | 0x1dda40 | `zar::CKey` | B | `GetRecordSize` | returns 16 (no other work) | zArchive.md guess: WriteDirectory multiplies the key count by it | low |
| 32 | 0x1dda50 | `zar::CKey` | B | `CountKeys` | (bool deep): 1 for this key plus, when deep, the recursive count of every key in each child vector (+0x4 count, +0x8 data) | zArchive.md proposed CountKeys(bool recursive); WriteDirectory calls it with (root, true) | medium |

## src/gamez/zBody/body.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 33 | 0x1e29d0 | `ACTIVE_ANIM` | B | `SetTime` | (time): wraps time into [0, 1], stores it (+0x10), sets the current and next frame (+0x1c, +0x1e) and the fraction (+0x18), clamped at the last frame unless looping | small-1.md proposed it; body agrees; callers CBlendOverlay::Tick, CZBodyAnimBlend::Reset and Synch | medium |
| 34 | 0x1e3b70 | `CBody` | A | `PopBlendTo` | (depth): PopBlend until the blend stack holds depth entries; returns the last top | small-1.md proposed it; body agrees; caller CZSealBody::PushBlend | medium |
| 35 | 0x1e3c20 | `CBody` | B | `BlendPose` | (t, part): moves part i's position toward its saved pose (+0x28) by Scale/Add and Slerps its rotation toward the saved one (+0x40) | small-1.md proposed it; body agrees; caller new 0x277ec0 | medium |
| 36 | 0x1e3dd0 | `CBody` | B | `ApplyPose` | for every part (+0x34 count, +0x38 data) with a node: CNode::SetPosition and SetRotation from the part's stored pose | small-1.md proposed it; caller CSealCtrlAi::SetAiEnabled | medium |
| 37 | 0x1e3e80 | `CBody` | B | `SavePose` | (part): copies part i's position and rotation into its second pose slot (+0x28, +0x40) | small-1.md proposed it; the counterpart of BlendPose | medium |

## src/gamez/zBone/bone_archive.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 38 | 0x1dea00 | `CScriptArchive` | B | `Fetch` | (script, index): takes the script at that index of the archive's array (+0x8) and, if there is one, CZSIScript::Share's it into the given script; returns whether there was one | small-3.md proposed this Fetch overload (next to Fetch(const char*, CZSIScript*, bool)); body agrees | medium |

## src/gamez/zCamera/camera.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 39 | 0x1ebc30 | `CAppCamera` | B | `UpdateRegions` | from the ground under the camera node (GetAltitude, not a seal): SetCameraCanSeeRegions, the material into +0x2b0, IsInside into +0x2ac | small-2.md proposed it; caller CZHudMissionCams::HudTick | medium |

## src/gamez/zCamera/zcam_update.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 40 | 0x1e9370 | `zdb::CCamera` | B | `InitFogAlt` | copies the eight floats at +0x4d0 into two new blocks at +0x510 and +0x530; unless bit 7 of +0x14f, writes -10000.0 / 0.001 defaults; copies +0x130 | small-2.md proposed it; only caller the CCamera constructor | medium |

## src/gamez/zCharacter/char_type.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 41 | 0x24bcf0 | `CSnd` | A | `SetDialogMode` | stores 3 into the byte at +0x24 | new CSnd virtual (slot 0x2c, the table grew from 9 to 10 slots), no base name; 3 is SND_MODE_DIALOG if +0x24 is m_soundmode (small-1.md's reading); CSndGroup's override passes it to every member | low |

## src/gamez/zEntity/ent_entity.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 42 | 0x1f38f0 | `CEntity` | A | `PostPostTick` | empty; new CEntity slot 0x24, after PostTick (0x20); PostTickAll calls it for every entity with dt in a third loop | small-1.md proposed it (the tick-phase series PreTick, PostPreTick, PrePostTick, PostTick); no base | medium |

## src/gamez/zEntity/ent_main.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 43 | 0x1efcd0 | `CEntity` | A | `GetNeckPosW` | copies the cached position (+0x1c..+0x24) to the out point and returns it; CZSealBody overrides it (0x29db40) with the world position of the part at +0x290 | new CEntity virtual (slot 0x38), no base; name from the CZSealBody override's part (small-1.md, zSeal-a.md) | medium |
| 44 | 0x1efcf0 | `CEntity` | A | `GetHeadPosW` | the same body as 0x1efcd0; CZSealBody overrides it (0x29dc10) with the part at +0x28c | new CEntity virtual (slot 0x34), no base; name from the override's part (small-1.md, zSeal-a.md) | medium |
| 45 | 0x1f1100 | `CEntity` | B | `PurgeInvalid` | static: m_list.erase(remove_if(begin, end, 0x1f1210), end), then renumbers the entities (+0x8) | small-1.md proposed it; caller CMPExitState::Tick | medium |
| 46 | 0x1f1210 | `CEntity` | B | `DeleteIfInvalid` | predicate: an entity whose id (+0x4) is -1 is deleted (virtual slot 0x8 with 1) and true is returned | small-1.md had IsInvalid; the body also deletes, so the name says so | medium |
| 47 | 0x1f1470 | `std` | B | `remove_copy_if<std::list<CEntity*>::generic_iterator<0>, ..., bool (*)(CEntity*)>` | list walk copying the elements the predicate rejects to the output iterator; returns the output end | small-1.md: byte twin of the named 0x30b830 remove_copy_if over list<CSched_Task*>; called by remove_if 0x1f1310; the membership data gave std::__vector_deleter<CTarget,std::allocator<CTarget>> | high |

## src/gamez/zEntity/pickup_main.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 48 | 0x250b80 | `CPickup` | B | `DestroyMPBombNode` | deletes the MP bomb node (0x48d900): notifies the parent, DeleteTextureAssetCharacter, CNode::Delete, clears the pointer | small-1.md proposed it; caller new 0x298220 | medium |
| 49 | 0x250c90 | `CPickup` | B | `TickDroppedPickups` | (dt, point): walks the pickups of types 8 and 9, counts their timer down and destroys those whose timer ran out and that are farther than 300 from the point | small-1.md proposed it; caller CMission::Tick | medium |
| 50 | 0x250e30 | `CPickup` | B | `CleanupMPBomb` | when the flag 0x48d904 is set: the same bomb-node delete as 0x250b80, then clears the flag | small-1.md proposed it; callers CMission::Tick, ftsNetworkGameUninit | medium |

## src/gamez/zFTS/fts_action.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 51 | 0x200f50 | `CNodeAction` | B | `OnAnimDone` | (anim, action): clears the action's anim pointer (+0x10) and bumps the 8-bit counter in +0x2e | zFTS.md proposed it: the callback ExecuteAction stores in the new CZAnim (+0x1c, action at +0x20) | medium |
| 52 | 0x200f80 | `CNodeAction` | B | `IsReady` | returns m_anim (+0x10) == 0 | zFTS.md proposed it; caller CSealCtrlAi::AllowCommand on the reticule action | medium |

## src/gamez/zFTS/fts_controller.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 53 | 0x20de70 | `CCtrlrConfigs` | A | `fn_0020de70` | returns the byte at a0 + 0x13 + index | zFTS.md: an out-of-line inline of the stick readers; nothing names the field | low |
| 54 | 0x20de80 | `CCtrlrConfigs` | B | `fn_0020de80` | returns the signed byte *a0 | zFTS.md: an out-of-line inline helper (GetFwdBackStickPos reads a config button through it) | low |
| 55 | 0x20de90 | `CCtrlrConfigs` | B | `fn_0020de90` | returns a0 + a1 (GetFwdBackStickPos passes config +10 and a button index) | zFTS.md: an out-of-line inline helper | low |
| 56 | 0x20e060 | `CCtrlrConfigs` | B | `GetButtonPressure` | (func, pad): the button the current config maps to func (config +10 + func); 0 when unmapped (16), else the pad's float at +0x24 + 4*button | zFTS.md proposed it; caller CSealCtrl::PreTick | medium |

## src/gamez/zFTS/fts_mission.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 57 | 0x1f7c80 | `CLadderList` | B | `GetLadderByNode` | (node, alt): finds the 36-byte ladder entry whose node (+0x18) is the argument, or with alt its +0x64 | zFTS.md proposed it (between GetClosestLadder and GetLadderByIndex) | medium |
| 58 | 0x1f84f0 | `CMission` | B | `EndMission` | unless +0x70: _OnMissionComplete, CVideo::Clear, CFlashFXVector::Reset, ResetDeathCam, CGame::Push of the next state | zFTS.md proposed it; caller CCoreState::Tick | medium |
| 59 | 0x1f88b0 | `CMission` | B | `UpdateNetGame` | j CZGameState::UpdateLocalGame with the net game (a1) as its argument | zFTS.md proposed it; caller CZOnlineLobby::ForceStatusReport | low |
| 60 | 0x1f9710 | `CMission` | B | `fn_001f9710` | fills a 48-byte block at its argument with constants (0, 4, 10000.0, 60.0, a global, 0.75, 2500.0, 2.0, 1.0, 0.25, 9, 5) | zFTS.md: the constructor of a 48-byte member at CMission+0xb4; its type is unknown, so no name | low |

## src/gamez/zFTS/fts_net_seal.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 61 | 0x206dd0 | `CZSealState` | B | `ClearRemoteGuyList` | j 0x208a80 (vector clear) on m_RemoteGuyList (0x4ddec0) | zFTS.md proposed it (next to UnloadRemoteGuyList); caller CLoadState::Init | medium |
| 62 | 0x208ad0 | `std::vector (8-byte element)` | A | `~__vector_deleter` | destroys the 8-byte elements, zeroes the count (+0x4), deletes the buffer (+0x8), deletes this when the flag > 0 | zFTS.md: the destructor of the std::vector behind m_RemoteGuyList; called by ~CRemoteGuyList and the insert 0x208640; the membership data gave CZSealState::CRemoteGuyList | medium |

## src/gamez/zFTS/fts_objectivecam.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 63 | 0x20e6a0 | `CMissionObjectiveCam` | B | `AddFlag` | (text): sets the bit of the string's first letter (a-z or A-Z) in the mask at +0x50 | zFTS.md proposed it; caller CMission::LoadObjectiveCams | medium |

## src/gamez/zGrid/grid_di.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 64 | 0x217090 | `CPnt3D` | B | `operator-` | (out, a, b): CPnt3D::Sub(a, b) into the returned value | small-2.md: the bytes of CPnt3D::operator+ (0x293390) with Sub for Add; placement said zdb::CGrid; the membership data gave zdb::CGrid | high |

## src/gamez/zGrid/grid_main.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 65 | 0x218e00 | `zdb::CGrid` | B | `GetCell` | (x, z): the cell list of the grid cell under the point, indices clamped to +0xc/+0x10 into the table at +0x30 | small-2.md proposed it; caller the new CWorld light level 0x231930 | medium |

## src/gamez/zInput/remote_control.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 66 | 0x2e01d0 | `CRemoteCtrl` | A | `OnMissionStart` | empty | vtable slot 0x5c of CRemoteCtrl; CSealCtrl slot 0x5c is OnMissionStart (zInput.md) | high |
| 67 | 0x2e01e0 | `CRemoteCtrl` | A | `OnMissionEnd` | empty | vtable slot 0x60 of CRemoteCtrl; CSealCtrl slot 0x60 is OnMissionEnd (zInput.md) | high |

## src/gamez/zNetwork/zNetCnf.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 68 | 0x404130 | `CNetCnf` | A | `LoadConfigModules` | loads netcnf (host or cdrom icon), inet and inetctl, then only the device drivers the selected configuration needs (ppp, pppoe, smap or an986), then the libnet set-up | body; zNetwork-a.md describes it and gives no name; caller InitFromCombo | low |

## src/gamez/zNetwork/zNetMedius.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 69 | 0x341e40 | `CZOnlineLobby` | B | `RefreshGameInfo` | (C2D*): finds the briefing room named by the lobby world name and requests the game info (0x34a7b0) for each of its games | zNetwork-a.md proposed it (between RefreshRoomList and RefreshGameList); caller the UI command 0x1d1050 | medium |
| 70 | 0x343b20 | `PersistentGame` | A | `PersistentGame` | constructor: stores the RoomGame table (0x48aa90), clears the record, copies the MediusGameListResponse argument, then stores the PersistentGame table (0x48aa70) and clears the tail | zNetwork-a.md proposed it (the table stores); the membership data gave MediusGameListResponse | high |

## src/gamez/zNode/node_wave.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 71 | 0x235620 | `zdb::CRipple` | B | `fn_00235620` | VU0/MMI: widens three s16 vertex coordinates, converts them to float and adds the record at a1, stores the quadword to a2 | zNode.md: a header inline of the CVisData vertex format; nothing names it | low |

## src/gamez/zNode/node_world.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 72 | 0x231930 | `zdb::CWorld` | B | `GetLightLevel` | (point, flags, radius): ambient (+0x660) plus directional terms (+0x630...) plus the point lights of the grid cell under the point (0x218e00), each part skipped by a flag bit | zNode.md proposed it | medium |
| 73 | 0x231f00 | `zdb::CWorld` | B | `GetAltitude` | the GetAltitude body (grid altitude, highest intersect) between a set and a restore of bit 1 of the intersect's flags by the bool | zNode.md: the bool overload of GetAltitude; callers ftsGetAltitudeApprox, zAnimObjectMotionTick | high |
| 74 | 0x2320d0 | `zdb::CWorld` | B | `GetIntersect` | the GetIntersect body (two points, nearest intersect) between a set and a restore of bit 0 of the intersect's flags by the bool | zNode.md: the bool overload of GetIntersect; caller zAnimObjectMotionTick | high |

## src/gamez/zParticle/zparticle_source.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 75 | 0x23cf30 | `Particle::Source` | B | `SetActive` | (bool): creates the DI node (+0x100) on first use (0x23e1a0), stores the flag at +0x11c and passes it to the node's virtual +0x34, CNode::SetActive | small-3.md proposed it; the node call is CNode::SetActive (CNode table slot 0x34) | medium |
| 76 | 0x23e1a0 | `Particle::Source` | B | `CreateDINode` | builds the "PARTICLE DI NODE": new CNode, six CDIPoly at +0x104..., AddDI, SetName, SetNodeEx (moved out of the constructor) | small-3.md proposed it; the node name string | medium |

## src/gamez/zSeal/ai_target.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 77 | 0x300940 | `CAiTarget` | A | `IsTargetValid` | the target entity (+0x0) is set, alive (+0xdd bit) and a seal (type 2); when its controller is an AI (virtual +0x30, then +0x38), also not flagged at +0x281 | zSeal-d.md proposed it (the prototype's inline validity test, xcheck-2.md); 31 callers | medium |

## src/gamez/zSeal/seal.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 78 | 0x253070 | `CSealStats` | B | `Rescue` | (seal): when online and the seal is the player, ++m_hostages_rescued (+0x24) | zSeal-f.md proposed it; +0x24 is m_hostages_rescued in the prototype layout (which +0x28 and +0x48 in 0x2532f0 confirm) | medium |
| 79 | 0x2530e0 | `CSealStats` | B | `Bomb` | (seal): when online and the seal is the player, ++m_bases_blown (+0x20) | zSeal-f.md proposed it; caller CZBombState::ChangeBombState | medium |
| 80 | 0x2532f0 | `CSealStats` | B | `Pack` | (MPSealStats*): memsets the 10-byte record, packs the stats bytes, m_hit_percent * 100 and m_sMvpScore (+0x48) | zSeal-f.md proposed it; GetMPStats tail-calls it | medium |
| 81 | 0x253700 | `CZSealBody` | A | `ExecuteAction_PickupBuddy` | (buddy): CrouchToPickupBuddy(buddy) and ++ the counter at +0x500 when there is one; returns whether there was | zSeal-f.md proposed it (byte twin of ExecuteAction_KnifeAttack next to it; caller OnActionButton) | medium |
| 82 | 0x254020 | `CZSealBody` | A | `AnnounceKill` | online: finds the killer by id, posts "%s fragged %s with %s" to the message queue and plays the remote kill sounds | zSeal-f.md proposed it (the block came out of OnDeath); twelve callers, the Damage* functions | medium |
| 83 | 0x2544c0 | `CZSealBody` | B | `GetTimeDead` | 0 while alive (+0xdd bit), else now - the death time (+0xed8) | zSeal-f.md proposed it; callers CTeamMateNames::Tick, 0x2608c0 | medium |
| 84 | 0x255da0 | `CZSealBody` | A | `IsStanceBlocked` | casts a ray 11.2 units ahead of the seal at half height (0x2a8700) and returns true when something is hit | zSeal-f.md proposed it; UpdateStance keeps the stance when it is true | medium |
| 85 | 0x25a6d0 | `CZSealBody` | A | `PostPostTick` | flushes and reads the altitude batch (0x2ad2a0, 0x2ad0e0), then the region-visibility shift of the node (and of a carried node) | override of CEntity slot 0x24 (base 0x1f38f0, named here PostPostTick); zSeal-f.md described it as UpdateRegionVisibility | medium |
| 86 | 0x25a800 | `CZSealBody` | A | `GetFollowState` | 0, or 1 / 2 by AiStateIs(STATE 9) of the controller's AI when the +0xf85 flag is set | zSeal-f.md proposed it; caller PostTick | medium |

## src/gamez/zSeal/seal_ai.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 87 | 0x25f050 | `CAiState` | A | `OnNotify` | empty; base of the new CAiState slot 0xc (27 tables); CAiSScript (0x2ed130) and CAiSAction (0x2675c0) override it with an (id, kind) handler | new virtual, no prototype slot; zSeal-b.md guessed OnNotify from the overrides; the membership data gave CAiSRescued: this is the root class of the tables holding it | low |
| 88 | 0x25f0a0 | `CAiState` | A | `CanAccept` | returns 1; base of the new CAiState slot 0x30; overrides: CAiSBreach (0x2ec870) true when a 7-bit field of the third argument is 3 or 8, CAiSAction (0x267650) while its status < 6 | new virtual, no prototype slot; zSeal-b.md guessed CanAccept from the overrides; the membership data gave CAiSRescued: this is the root class of the tables holding it | low |
| 89 | 0x25f0b0 | `CAiState` | A | `CanCheckStuck` | returns 1; base of the new CAiState slot 0x34; CAiSAction's override (0x2676b0) returns status < 6 | new virtual with no name in either program; the stuck check 0x25fbf0 asks it of the current state and resets the idle timer when it is false; the membership data gave CAiSRescued: this is the root class of the tables holding it | low |
| 90 | 0x25f0c0 | `CSealCtrlAi` | A | `PushEventState` | (kind, point, ..., flags): when the kind's bit is set in the mask at +1392, pushes AI state 25 (STATE_EVENT) and stores the kind in it; otherwise raises awareness (SetAiAware GENERAL or DIRECTION) by the flags | zSeal-b.md proposed it (zSeal-f.md had PushHitEvent); caller OnWeaponHit | medium |
| 91 | 0x25f260 | `CSealCtrlAi` | A | `FindDeployLoc` | (from, to, ..., out loc): AI-map search between two points (GetLocation, GetMapByIndex, GetClosestDir, scanline cells, callback 0x25fa70) for a free location | zSeal-f.md proposed it (caller OnCommand after PushAiState(STATE_DEPLOY), FindValidReticleGotoLoc the fallback); zSeal-b.md had FindCommandGotoLoc | low |
| 92 | 0x25fbf0 | `CSealCtrlAi` | A | `CheckStuck` | asks the current state's slot 0x34; if false resets the reaction and idle timers; else checks the ladder climb anims, the idle time against 2.0/2.0/2.5 and pushes STATE_AVOID or STATE_PATHRECOVER | zSeal-f.md proposed it (zSeal-b.md had HandleStuck); caller CSealCtrlAi::PreTick | medium |
| 93 | 0x2608c0 | `CSealCtrlAi` | A | `OnSeeCorpse` | (entity): for a teammate's body: target checks (0x300940), sniper rifle, guard region, the time since death (GetTimeDead), then pushes a state | zSeal-f.md proposed it; caller HandleEvent | medium |
| 94 | 0x2629a0 | `CAiSAnimate` | B | `fn_002629a0` | returns its argument (this) | zSeal-b.md: an inline accessor of the list at CAiSAnimate +64 (byte twin of 0x264240); nothing names it | low |
| 95 | 0x264240 | `CAiSGrenade` | B | `fn_00264240` | returns its argument (this) | zSeal-e.md: the end/sentinel accessor of the callback list's type, on CAiSAnimate +52 | low |
| 96 | 0x264250 | `CAiSGrenade` | B | `GrenadeThrowCallback` | (.., seal, grenade state): builds the hand node's world matrix, rotates the velocity stored at state +0x58 into it and calls the projectile's position-and-velocity setter (0x3304d0); returns 1 | zSeal-e.md: one of the "Return throw grenade" callbacks CAiSGrenade::Tick registers, left unnamed; name from the body (position and velocity at the hand) | low |
| 97 | 0x2643a0 | `CAiSGrenade` | B | `GrenadeInHandCallback` | the same check, then sets the projectile's position only (0x3305c0) to the hand node's world position; returns 1 | zSeal-e.md: a "Return throw grenade" callback; name from the body | low |
| 98 | 0x264440 | `CAiSGrenade` | B | `GrenadeGrabCallback` | the same check, then sets the projectile's position at the hand with zero velocity (0x330620); returns 1 | zSeal-e.md: a "Return throw grenade" callback; name from the body | low |
| 99 | 0x2644e0 | `CAiSGrenade` | B | `GrenadeReleaseCallback` | the same check, then uses the body's matrix and the projectile's own position with the stored velocity (0x3304d0) | zSeal-e.md: a "Return throw grenade" callback; name from the body | low |
| 100 | 0x265e00 | `CAiSDeploy` | A | `CanPushAiState` | returns status (+0x10) < 4 | vtable slot 0x18 of CAiSDeploy; CAiState slot 0x18 is CanPushAiState (zSeal-e.md) | high |
| 101 | 0x267330 | `CAiSAction` | A | `GetStatus` | status (+0x10) -> "INIT", "CREEP", "PLAN", "WAIT", "GOTO", "ORIENT", "EXECUTE", "ACTION", "COMPLETE", "FAILED", else "unknown" | vtable slot 0x14 of CAiSAction; CAiState slot 0x14 is GetStatus (zSeal-e.md) | high |
| 102 | 0x2675c0 | `CAiSAction` | A | `OnNotify` | (id, kind, ai): when the id is +0x48, kind 6 sets bits in +0x8, kind 1 clears +0x48; then sets bit 0 of ai +1000 | override of the new CAiState slot 0xc (base 0x25f050, named here OnNotify) | low |
| 103 | 0x267650 | `CAiSAction` | A | `CanAccept` | true while status < 6; otherwise, unless the fifth argument is set, true when the field (+0x1a >> 1) of the third argument is 3 or 5 | override of the new CAiState slot 0x30 (base 0x25f0a0, named here CanAccept) | low |
| 104 | 0x2676b0 | `CAiSAction` | A | `CanCheckStuck` | returns status (+0x10) < 6 | override of the new CAiState slot 0x34 (base 0x25f0b0, named here CanCheckStuck) | low |
| 105 | 0x2676c0 | `CAiSAction` | A | `CanAttack` | returns +0x48 == 0 | vtable slot 0x20 of CAiSAction; CAiState slot 0x20 is CanAttack (zSeal-e.md) | high |
| 106 | 0x2676d0 | `CAiSAction` | A | `CanPursue` | returns 0 | vtable slot 0x28 of CAiSAction; CAiState slot 0x28 is CanPursue (zSeal-e.md) | high |
| 107 | 0x2676e0 | `CAiSAction` | A | `CanScan` | returns +0x48 == 0 | vtable slot 0x24 of CAiSAction; CAiState slot 0x24 is CanScan (zSeal-d.md) | high |
| 108 | 0x2676f0 | `CAiSAction` | A | `CanPushAiState` | (state, ai): state 25 false; state 3 only while +0x48 is 0; otherwise true | vtable slot 0x18 of CAiSAction; CAiState slot 0x18 is CanPushAiState (zSeal-d.md) | high |
| 109 | 0x267f60 | `CSealCtrlAi` | A | `PostSoundEvent` | (radius): acquires a CAiEvent (type 4), owner the seal's id, range radius^2, duration 0.5, at the seal's position, posts it (Create) and returns it | zSeal-c.md proposed it; caller CTSound::Tick after a sound plays; next to PlayAiSound; the membership data gave CAiEvent | medium |
| 110 | 0x269ed0 | `CSealCtrlAi` | B | `SetStanceTimer` | (time, stance, force): unless the stance is 2, or the target is valid with bit 2 of +0x598, or force: return; else stores the stance at seal +0x305 and the timer at +0x338/+0x33c/+0x340 | zSeal-c.md proposed it; callers CTStance::Begin/End, CAiState::Signal | medium |
| 111 | 0x26bc70 | `CSealCtrlAi` | A | `CanEngageTarget` | for a valid target: true in state 2 with flag 0x20, with AI state 8 (flags 0x80) or 10 on the stack, or a target flag; else a timed visibility test (cached 0.5) | zSeal-c.md proposed it; caller AttackTick | medium |
| 112 | 0x26f020 | `CSealCtrlAi` | A | `LookAhead` | (dist, loc, out): fills the look-ahead record from the seal's AI-map cell and facing, then WalkLine on the map with the callback _look_ahead (0x26f210) | zSeal-c.md proposed it (the prototype did this inline in PathFollowTick); callers PathFollowTick, CreepTick, CAiSAction::Tick | medium |
| 113 | 0x2704c0 | `CSealCtrlAi` | A | `UpdateThrottle` | (dt): per axis, ramps the throttle (+0x8...) toward the target (+0x274...) at the accel or decel rate, snapping with _close_enough | zSeal-c.md proposed it (split out of PreTick, its caller) | medium |
| 114 | 0x271020 | `CSealCtrl` | A | `SetGoalPos` | (time, goal type, cell): GetCellCenter of the AI-map cell, then the SetGoalPos stores (goal position, timer, type, SetGoalDir on a type change); false when the type ranks lower | zSeal-c.md: a SetGoalPos overload from a cell; callers CAiSAvoid::Tick, CAiSPathRecover::Tick | high |
| 115 | 0x275ed0 | `CSealCtrlAi` | A | `AiStateIs` | (state, mask): the current AI state's enum (+0xc) is the given one and its flags (+0x8) share a bit with the mask | zSeal-d.md proposed this overload of the neighbouring AiStateIs; caller CSealCtrl::ComputeVisibility | medium |
| 116 | 0x276500 | `CSealCtrlAi` | A | `SetTeammateSoundValve` | (ai, value): with no AI sets the valves snd_hutchins, snd_bailey, snd_dimone to the value; else only the one its seal's +0x284 picks; MakeCallbacks on a change | zSeal-d.md proposed it; callers OnDeath, InitAiBrain, AcquireDatabaseHandles | medium |

## src/gamez/zSeal/seal_aifollow.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 117 | 0x2f63c0 | `CSealCtrlAi` | A | `CheckFollowFireLane` | FollowTick helper: for a follow master (+0x4d0) whose controller is the player: weapon state, cached constants 100, 40, 20 and tan(40 deg), AI-map cells along the path, then a cone test (0x2f6fc0) | zSeal-c.md proposed it; caller FollowTick | low |
| 118 | 0x2f7290 | `(free)` | A | `PointInWedgeXZ` | (a, b, c, d): XZ side tests of two points against the edges a-b and c-d (cross products), returns one of three cached result values | zSeal-c.md proposed it and zSeal-f.md kept it; caller the cone test 0x2f6fc0; the membership data gave CPnt3D | low |

## src/gamez/zSeal/seal_airesponse.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 119 | 0x2fccb0 | `CAiSEvent` | B | `SetName` | (name): copies up to 16 characters to +0x59, or clears it for NULL | zSeal-f.md proposed it; caller 0x2608c0 with "on_corpse" | medium |
| 120 | 0x2fd030 | `CAiSRestrained` | A | `CanPushAiState` | (state, ai): true when the seal's body has flag 0x20000 (+0xc4) | vtable slot 0x18 of CAiSRestrained; CAiState slot 0x18 is CanPushAiState (zSeal-f.md) | high |
| 121 | 0x2fdc90 | `CAiSSurrender` | A | `CanPushAiState` | (state, ai): with that body flag, true once the stage (+0x10) is at least 5; otherwise only state 7 (STATE_RESTRAINED) | vtable slot 0x18 of CAiSSurrender; CAiState slot 0x18 is CanPushAiState (zSeal-f.md) | high |

## src/gamez/zSeal/seal_aistate.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 122 | 0x2ec870 | `CAiSBreach` | A | `CanAccept` | true when the field (+0x1a >> 1) of the third argument is 3 or 8 | override of the new CAiState slot 0x30 (base 0x25f0a0, named here CanAccept) | low |
| 123 | 0x2ec8b0 | `CAiSBreach` | A | `CanPushAiState` | (state): true, except state 3 while the substate (+0x10) is 4 ... 9 | vtable slot 0x18 of CAiSBreach; CAiState slot 0x18 is CanPushAiState (zSeal-e.md) | high |
| 124 | 0x2ed130 | `CAiSScript` | A | `OnNotify` | (id, kind): when the id is +0x24: kind 3 clears bit 0 of +0x28, kind 2 sets it, kind 1 clears +0x24 | override of the new CAiState slot 0xc (base 0x25f050, named here OnNotify) | low |
| 125 | 0x2ed1b0 | `CAiSScript` | A | `CanPushAiState` | (state): while bit 0 of +0x28 is set, refuses states 26 and 12 | vtable slot 0x18 of CAiSScript; CAiState slot 0x18 is CanPushAiState (zSeal-e.md) | high |
| 126 | 0x2ee9e0 | `CSealCtrlAi` | B | `DeleteIfAvoidState` | predicate: a state whose type (+0xc) is 3 is deleted (virtual slot 0x38, the destructor) and true is returned | zSeal-e.md: a static predicate StateTick passes to 0x2f09f0; 3 is STATE_AVOID in the prototype's numbering | low |
| 127 | 0x2eebd0 | `CSealCtrlAi` | B | `GetStateMask` | (state 0...29): a constant mask per AI state by jump table (0 -> 0x3ffffffe, 1 -> 0x3ffffbd6, ...); UpdateStackFlags ANDs them over the stack | zSeal-e.md proposed it; caller UpdateStackFlags | medium |
| 128 | 0x2ef4f0 | `CSealCtrlAi` | B | `AiStateHasFlags` | (state, mask): if the state's bit is set in +0x3e0, finds that state on the AI stack (list +0x3d0) and tests its flags (+0x8) against the mask | zSeal-e.md proposed it; caller CanEngageTarget 0x26bc70 | medium |
| 129 | 0x2ef9c0 | `CSealCtrlAi` | B | `GetPrevAiState` | with two or more states on the stack (+0x3d0), returns the state below the top, else NULL | zSeal-e.md proposed it; caller CAiSAvoid::Tick | medium |
| 130 | 0x2f9ba0 | `CAiSAvoid` | B | `InitAvoid` | (time, seal, target, from, to, point): status (+0x10) = 3, +0x24 = target, the avoid direction at +0x38 ((seal - point) / time, or normalized to - from) and the timer at +0x34 | body; zSeal-e.md: a CAiSAvoid set-up, left unnamed; caller CSealCtrl::SensorPreTick | low |
| 131 | 0x2f9cb0 | `CAiSAvoid` | B | `ChooseAvoidGoal` | (seal, other): stores the other seal at +0x24, compares both seals' motion (is_moving), picks a side with rand, tests AI-map cells with CanTravelLine and sets the goal (SetGoalPos) | body; zSeal-e.md: the CAiSAvoid goal choice, left unnamed; caller the stuck check 0x25fbf0 | low |
| 132 | 0x2fa470 | `CAiSAvoid` | B | `ShouldAvoid` | (dist, seal, other): within range, from both seals' motion, their controllers, stance and AiStateIs 3, whether the seal must yield | zSeal-e.md proposed it; callers CSealCtrl::SensorPreTick, 0x2602e0 | low |

## src/gamez/zSeal/seal_anim.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 133 | 0x277ce0 | `CZSealBody` | A | `SavePartPoses` | CBody::SavePose (0x1e3e80) for each body part held at +0x26c...+0x2c0 (the part index at part +0x24), and for three more when they have an anim | body: the callee is the pose-saving CBody method (small-1.md); zSeal-e.md's ResetWeaponAnims read the callee as an anim reset; callers BlendOverlayPreTick, 0x27b620 | medium |
| 134 | 0x2780f0 | `CZSealBody` | A | `SmoothBlendWeights` | counts the blend weights at +0x120 and +0xfa8 down by dt, quadW of the ratio, CBody::SmoothAnims, and the pose blend 0x277ec0 | zSeal-e.md proposed it (the block from the start of the prototype's Post); caller CZSealBody::Tick | medium |

## src/gamez/zSeal/seal_body.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 135 | 0x279bc0 | `CZSealBody` | A | `ResetGear` | when the top blend's action part is the "rifle": detaches its node and places it as gear again (PartInSpace, quaternion, SetPosition, SetPartAsGear twice) | zSeal-b.md proposed it; callers _OnMissionComplete, CheckAnim, PopBlend | medium |
| 136 | 0x27a420 | `CZSealBody` | A | `AlignToRestrainBuddy` | (buddy): when slow enough (speed^2 <= 100), aligns to the buddy (ClearStack, PushBlend, AlignForPickup) with callback 0x27a650 | zSeal-b.md proposed it (after CrouchToPickupBuddy); caller ExecuteAction_ApplyRestraint | medium |
| 137 | 0x27a650 | `CZSealBody` | B | `RestrainBuddyCallback` | j CZSealBody::RestrainBuddy (a0, a1 passed on) | zSeal-b.md proposed it, after the prototype's PickupBuddyCallback(void*, void*) | medium |
| 138 | 0x27a890 | `CZSealBody` | A | `AlignToStabBuddy` | (buddy): the same alignment as 0x27a420 with callback 0x27aac0 (which stabs) | zSeal-b.md proposed it; caller ExecuteAction_KnifeAttack | medium |
| 139 | 0x27b620 | `CZSealBody` | A | `FinishWeaponChange` | ticks the blend overlay; when it completes, PostChangeWeapon(rifle / pistol) for events 3 / 4, SavePartPoses when blending, and resets +0xfa8 (0.4) | zSeal-b.md proposed it; caller CZSealBody::Tick_0 | medium |
| 140 | 0x284800 | `CZSealBody` | A | `CanProneAimNow` | false while the flag in +0xf86 is set and health > 2.0, else CanProneAim() | zSeal-b.md proposed it; caller CSealCtrl::PreTick | low |
| 141 | 0x285760 | `CZSealBody` | A | `CheckRestoreAnimSet` | standing still in the stand/crouch/prone base anim with the special anim set bound: rebinds the character's set, stops the +0x470 anim, clears the weapon timer | zSeal-b.md proposed it; caller SealAnim | medium |
| 142 | 0x285890 | `CZSealBody` | A | `RestoreAnimSet` | the same restore without the standing-still test | zSeal-b.md proposed it; caller OnWeaponHit | medium |
| 143 | 0x2872c0 | `CZSealBody` | A | `IsLanding` | the current blend anim is the base of animTypeJumpLand or animTypeJumpLandHard | zSeal-b.md proposed it; callers CanFire, SampleActionAvailable | medium |
| 144 | 0x287350 | `CZSealBody` | A | `IsJumping` | the current blend anim (+0x46c) is the base of animTypeJumpLaunch or animTypeJumpFall | zSeal-b.md proposed it (the prototype's jumping test in ComputeNextPosition) | medium |
| 145 | 0x2873e0 | `CZSealBody` | A | `IsLandingFromFall` | the current blend anim is one of the two AnimTypes globals found by "Land forward" / "Land backwards" | zSeal-b.md proposed it; callers ComputeNextPosition, PostCheckDIDown | medium |
| 146 | 0x287470 | `CZSealBody` | A | `IsFalling` | the current blend anim is one of the AnimTypes globals of "Fall forward" / "Fall backwards" | zSeal-b.md proposed it (the prototype's falling test) | medium |
| 147 | 0x287500 | `CZSealBody` | B | `fn_00287500` | returns 0 | zFTS.md: the empty receiver of a new DME message (handler 0x205e10, registered between PushBlend and ActionAnim); nothing says what it receives | low |
| 148 | 0x288720 | `CZSealBody` | A | `IsBlendInStack` | (anim type): true if any entry of the blend stack (+0x130) has that type at +0x30 | zSeal-b.md proposed it; seven calls from IsReloading | medium |

## src/gamez/zSeal/seal_control.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 149 | 0x28faa0 | `CSealCtrl` | B | `ClearPadButtons` | the controller's pad (index +0xe8, table at gp-0x7d90): Flush, then CROSS, SQUARE, TRIANGLE, CIRCLE set KEY_UP | zSeal-a.md proposed it; callers CCinematicState::UnInit, CZHudMissionCams::CleanupCamera | medium |

## src/gamez/zSeal/seal_env.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 150 | 0x298220 | `CZSealBody` | B | `DeleteMPBombPickup` | DestroyMPBombNode (0x250b80), then the player's compass anchor and CompassAnchor_MPBomb(NULL) | zSeal-a.md proposed it (between CreateMPBombPickup and DropMPBomb) | medium |
| 151 | 0x29db40 | `CZSealBody` | A | `GetNeckPosW` | world position of the part at +0x290 (m_neck): PartInSpace, then the node matrix on VU0, into the out point | override of the new CEntity slot 0x38 (base 0x1efcd0, named here GetNeckPosW); +0x290 is m_neck in the prototype layout (zSeal-a.md) | medium |
| 152 | 0x29dc10 | `CZSealBody` | A | `GetHeadPosW` | the same for the part at +0x28c (m_head) | override of the new CEntity slot 0x34 (base 0x1efcf0, named here GetHeadPosW); +0x28c is m_head (zSeal-a.md) | medium |
| 153 | 0x29ddb0 | `CZSealBody` | A | `ApplyFootDecal` | (foot point): applies a footprint decal at the last altitude hit (+0x360), texture from the per-material table, size 3.5 | zSeal-a.md proposed it (the prototype HandleSealStep had it inline twice); caller HandleSealStep | medium |
| 154 | 0x2a3230 | `CZSealBody` | A | `AbortWeaponChange` | in a Rifle2Pistol / CrouchRifle2Pistol / ProneRifle2Pistol anim: fires and clears the blend callback, switches back to the rifle, re-poses, restores gear and aim/fire points | zSeal-a.md proposed it; callers FlingBody, WeaponHitAnim | medium |
| 155 | 0x2a5800 | `CZSealBody` | A | `CanUsePickup` | alive, body state not 6, not jumping or landing, speed^2 <= 49, then CanFire() | zSeal-a.md proposed it; caller CSealCtrl::TickPickups | medium |
| 156 | 0x2a8700 | `CZSealBody` | A | `GetNearestBlockingHit` | casts two segments with this entity's node ignored (static DiIntersects at 0x521210 / 0x521270, GetIntersectBatch) and returns the nearest hit whose material flag +0x38 is 1 | body; zSeal-a.md had GetNearestHit2; caller 0x255da0 (IsStanceBlocked); the membership data gave CEntity | low |
| 157 | 0x2a97a0 | `CZSealBody` | A | `CanMarkNode` | (node): true unless the node is a seal that is not alive | zSeal-a.md proposed it; caller CZMarkList::AddNewMark | medium |
| 158 | 0x2abe70 | `CZSealBody` | A | `ApplyFall` | (hit): falling step: integrates the vertical speed, lands on the altitude hit plus the material's height offset (Propagate, GetRootPos) | zSeal-a.md proposed it (split out of PostCheckDIDown, its caller) | medium |
| 159 | 0x2ad0e0 | `CZSealBody` | A | `ProcessQueuedAltitude` | reads this seal's queued altitude result (handle into the batch, SealProcessAltitude), else resets the last hit to the node position | zSeal-a.md proposed it; caller PostPostTick 0x25a6d0 | medium |
| 160 | 0x2ad2a0 | `CZSealBody` | B | `FlushAltitudeBatch` | when queued (count > 0): GetIntersectBatch of the batch list, count = 0 | zSeal-a.md proposed it; caller 0x25a6d0 | medium |
| 161 | 0x2ad2d0 | `CZSealBody` | A | `QueueAltitudeCheck` | when the get-new-altitude bit (+0xdc bit 7) is set: clears it, builds a downward segment at the seal and queues it in the altitude batch, growing the batch (_realloc, seal_env.cpp; new DiIntersect) | zSeal-a.md proposed it; caller CZSealBody::PostTick | medium |
| 162 | 0x2ae7a0 | `CZSealBody` | A | `HomingStep` | (out): the homing variant used when the homing record's flag is set: from the top blend's homing data (Representative, tfrac) computes the correction into the out vector | zSeal-a.md proposed it (it shares most of HomingTick's calls); caller Tick_0 | low |
| 163 | 0x2afad0 | `CZSealBody` | A | `CanDoAction` | (u8 action): a large predicate: alive, body state, falling/landing, anim tests, the action kind (1 ...), reload and M203 mode | zSeal-a.md proposed it; nine callers (CanChangeItem, CanUseCQB, CanUseKnife, CanUseRestraint, CZKit::Reload ...) | medium |
| 164 | 0x2b1750 | `CZSealBody` | B | `FreeAltitudeBatch` | deletes every DiIntersect of the altitude batch, frees the list (seal_env.cpp:475), zeroes the counts | zSeal-a.md proposed it; callers CCoreState::UnInit, CMPExitState::Init, CMission::ReOpen_Unload1 | medium |

## src/gamez/zSeal/seal_kit.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 165 | 0x2b6670 | `CZKit` | A | `GrenadeLauncherFull` | true if the item after the current one (unwrap twice) is a grenade launcher weapon whose count (+0x6f4 area) is >= 4 | zSeal-a.md proposed it; caller CZSealBody::Reload | medium |
| 166 | 0x2b7500 | `CZKit` | B | `GetCurReticule` | returns GetReticuleByIndex(the current reticule index, +0x814) | zSeal-a.md proposed it (between GetReticuleByIndex and SetCurReticule); caller CheckDIShoot | medium |
| 167 | 0x2b7f40 | `CZKit` | B | `SolveLobAim` | iterative aim solve from a start to a target point with local statics (98.0, 0.85, 12 steps, tolerance via _close_enough) | zSeal-a.md proposed it; caller HandleFireWeapon before firing | low |
| 168 | 0x2b89a0 | `CZKit` | A | `FirstTickSetup` | PreTick's first-tick block: rifle or pistol mode for item 3 with SetPartAsGear, CycleFireMode, then the fire-mode set-up | zSeal-a.md proposed it (the block absorbed the removed ChangeItemModel); caller PreTick | low |
| 169 | 0x2ba780 | `CZKit` | A | `GetPlacementPos` | the ground point under the seal's right hand (+0x284): PartInSpace, quaternion, position, GetAltitudes, material | zSeal-a.md proposed it; caller TickExplosives | low |

## src/gamez/zSeal/seal_tasks.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 170 | 0x2caa90 | `(free, file static)` | B | `taskParamCompare` | (cur, value, op): op 1 !=, 2 ==, 3 >, 4 <, 5 >=, 6 <=, otherwise true | zSeal-c.md: the name of the static helper in the reconstructed seal_tasks.cpp that has the same cases in the same order (the prototype inlined it); the membership data gave CTParam | medium |

## src/gamez/zSeal/seal_unit.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 171 | 0x2ea6e0 | `CSealUnit` | A | `CanExtractEscortee` | (seal): when the "escortee_extract" anim is available, finds the unit of type 17 in CSealUnit::m_list and checks its members against the seal's location (GetLocationDelta) | zSeal-a.md proposed it; callers AllowCommand, HandleSupport | medium |

## src/gamez/zSoftImage/si_script.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 172 | 0x1e02f0 | `CZSIScript` | B | `Load` | (index): fetches the boneArchive script at the index into this (0x1dea00), keeps the result in bit 0 of +0x4 and returns it | small-3.md proposed this Load overload (next to Load(const char*, bool), same caller BodyAddAnim) | medium |

## src/gamez/zSound/zsnd_csnd.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 173 | 0x302a20 | `CSnd` | A | `TickGroupVolTemp` | (dt): counts the group-volume fade timer (0x48e374) down and calls ResetGroupVolTemp when it runs out | small-1.md proposed it; caller CMenuState::Tick | medium |

## src/gamez/zSound/zsnd_csndgroup.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 174 | 0x307350 | `CSndGroup` | A | `SetDialogMode` | calls slot 0x2c on every member sound (vector +0x4c / +0x50) | override of the new CSnd slot 0x2c (base 0x24bcf0, named here SetDialogMode) | low |

## src/gamez/zSound/zsnd_csndinstance.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 175 | 0x306430 | `CSndInstance` | B | `FadeOutAllSounds` | unless disabled: for every instance in m_instancelist stores 1.5 at +0x20 and fades it to 0 over 1.5 s (0x306bf0) | small-1.md proposed it (next to StopAllSounds, UIStopAllSounds); caller the anim command handler 0x1d1840 | medium |
| 176 | 0x306bf0 | `CSndInstance` | B | `FadeTo` | (vol, time): waits for the instance's handle (snd_FlushSoundCommands, up to 500 times), stores vol, snd_AutoVol(handle, vol x 1024 x master, time x 240, 2) | small-1.md proposed it | medium |
| 177 | 0x307140 | `CSndInstance` | B | `DumpInstances` | an empty walk over m_instancelist (the loop body compiled away) | small-1.md proposed it (a debug body removed); caller CMission::Close | low |

## src/gamez/zSound/zsnd_jukebox.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 178 | 0x308640 | `CSndJukebox` | B | `ProcessQueue` | the jukebox's queue and fade step: by the state (0x48e3cc) fades the current instance or sequence out (FadeOut 3.0) and plays the next (Play) | small-1.md proposed it (split out of CSndJukebox::Tick, its caller) | medium |

## src/gamez/zTwoD/ztwod_messageq.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 179 | 0x201f90 | `C2DMessage_Q` | A | `SetColor` | walks this list and writes the four floats of a1 into +0x54..+0x60 of every message string | small-2.md proposed it (next to SetBkgColor); the list calls are C2DMessage_Q's own list base; the membership data gave std::__list_deleter<void_const*,std::allocator<void_const*>> | medium |
| 180 | 0x202810 | `C2DMessage_Q` | B | `Add_Message` | the general overload: the prototype Add_Message(const char*, int, int, int) body (new C2DString, text after leading blanks) with an int, a bool and a float more | small-2.md: the prototype overload's body; the other Add_Message overloads forward to it | high |
| 181 | 0x202ca0 | `C2DMessage_Q` | B | `Add_Message` | (text, bool, time): time 0 -> +0x120, then the general Add_Message with +0x130, +0x138, +0x134, +0x140 | small-2.md proposed this overload; caller zAnimMessageTick | high |
| 182 | 0x202ce0 | `C2DMessage_Q` | B | `Add_Message` | (text, three ints, bool, time): time 0 -> +0x120, then the general Add_Message | small-2.md proposed this overload; zAnimMessageTick calls it where the prototype called the (PCciii) one | high |

## src/gamez/zUI/zui.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 183 | 0x39e210 | `std::__vector_deleter<T> (T unknown)` | B | `__vector_deleter` | zeroes three words and returns this: a default constructor of a 12-byte container | zUI.md: the same bytes as many MSL __vector_deleter default constructors; only caller the new 0x421620 (hud); the membership data gave CGameMenu | low |

## src/gamez/zUI/zui_2d.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 184 | 0x3a1670 | `CRenderableString` | A | `GetSpacing` | returns the float at +0xb0 | vtable slot 0x78 of CRenderableString (and C2DClock, CTickerTapeText, CScrollText, CWrappedText, CTeleType, C2DCounter); C2DString slot 0x78 is GetSpacing (zUI.md) | high |
| 185 | 0x3a1ae0 | `CUIMapCtrl` | A | `AdjustZoomedPos` | (t, zoom, this, node): from the zoom step computes the node's target position and scale, tests IsCovered eight times, calls CalcAlternateZoomedPos and sets the node position | zUI.md proposed it (the calls the prototype TickZAnimCmd made); callers TickZAnimCmd, HandlePad | low |
| 186 | 0x3a2180 | `CUIMapCtrl` | B | `LerpPos` | (t, x, y, out, from): out.x = x - t (x - from.x), out.y the same, out.z = from.z | zUI.md proposed it; callers TickZAnimCmd, HandlePad | low |
| 187 | 0x3a21f0 | `CUIMapCtrl` | A | `Tick` | (dt): stores dt in a global (gp-0x5e64) | vtable slot 0x28 of CUIMapCtrl; C2D slot 0x28 is Tick (zUI.md) | high |
| 188 | 0x3a8510 | `CSliderBar` | A | `Tick` | (dt): ticks its two elements, counts the timer at +0x21c down and on expiry reloads the bitmap (C2DBitmap::Load), SetPulse, SetFadeTimeMaxMin | vtable slot 0x28 of CSliderBar; C2D / C2DButton slot 0x28 is Tick (zUI.md) | high |
| 189 | 0x3a9f20 | `CUIListBox` | A | `SelectPrev` | when the selection (+0x190) > 0: decrements it, scrolls (+0xb0 by the item height +0xac), plays the selection anim and sound | zUI.md proposed it (split out of HandlePad, its caller) | medium |
| 190 | 0x3aa1f0 | `CUIListBox` | A | `SelectNext` | the same, incrementing the selection while below the item count - 1 | zUI.md proposed it | medium |
| 191 | 0x3aaa20 | `CUIListBox` | B | `IsItemVisible` | (text): finds the item whose string (virtual +0x14) matches (strcasecmp); 1 if it is in the visible window, 0 if not, -1 if absent | zUI.md proposed it; caller zNetwork 0x34a7b0 | medium |
| 192 | 0x3aee80 | `CWrappedText` | A | `GetZAnimCmdType` | (name): "Scroll_Up", "Scroll_Down", "Caption" -> GetUICommandType() + 3 / 4 / 2 (5 for NULL), else the base's | vtable slot 0x58 of CWrappedText and CScrollText; CRenderableString slot 0x58 is GetZAnimCmdType (zUI.md) | high |
| 193 | 0x3aef80 | `CWrappedText` | A | `Tick` | (dt): C2DString::Tick, then the Tick of two members | vtable slot 0x28 of CWrappedText; CRenderableString slot 0x28 is Tick (zUI.md) | high |
| 194 | 0x3aefe0 | `CWrappedText` | A | `TickZAnimCmd` | (cmd): scroll down / up by the line height (virtual +0x78) within the text, or the Caption command sets the text by name | vtable slot 0x54 of CWrappedText and CScrollText; CRenderableString slot 0x54 is TickZAnimCmd (zUI.md) | high |
| 195 | 0x3af170 | `CWrappedText` | A | `ParseZAnimCmd` | (reader): SCROLL_UP, SCROLL_DOWN, CAPTION tags -> 8-byte commands (_calloc, zui_2d.cpp), the caption name added to the anim names | vtable slot 0x50 of CWrappedText and CScrollText; CRenderableString slot 0x50 is ParseZAnimCmd (zUI.md) | high |
| 196 | 0x3b1490 | `@unnamed@zui_2d_cpp@::CListItemImageTypeImpl` | A | `GetTrans` | j C2DBitmap::GetTrans on its bitmap (+0x10) | body: the new slot 0x18 of the list-item type tables returns the item's transparency: here the bitmap's GetTrans, the array kind defaults to 128.0 (opaque, as SetTrans(128.0f)); zUI.md had left it unnamed (GetWidth or GetHeight) | medium |
| 197 | 0x3b16d0 | `@unnamed@zui_2d_cpp@::CListItemStringTypeImpl` | A | `GetTrans` | returns the float at +0x64 (inside m_string at +0x4) | the same new slot 0x18 (string and timed-text tables); named with its image and array siblings, whose bodies read a transparency | medium |
| 198 | 0x3b1760 | `CUIMapCtrl` | A | `SetNode` | (arg): stores its argument at +0x210 | override of the new C2D slot 0x20 (base 0x173940, named here SetNode after small-2.md) | low |
| 199 | 0x3b23e0 | `@unnamed@zui_2d_cpp@::CListItemArrayTypeImpl` | A | `GetTrans` | the first cell's virtual +0x18 (its GetTrans), or 128.0 without one | the same new slot 0x18 of CListItemArrayTypeImpl; 128.0 is the opaque transparency | medium |

## src/gamez/zUI/zui_skb.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 200 | 0x3c3390 | `@unnamed@zui_skb_cpp@::CBmpWithNode` | A | `SetNode` | (arg): stores its argument at +0xa0 | override of the new C2D slot 0x20 (base 0x173940, named here SetNode after small-2.md); the class's own name, CBmpWithNode, fits a stored node | low |

## src/gamez/zUI/zui_tuner.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 201 | 0x3c0b30 | `CStickInertiaTuner` | A | `UpdateUIVar` | (var): for a float variable and a pad table, writes 1.0 - value to the pad field +0x1c4 of the tuner's pad (+0x8) | vtable slot 0xc of CStickInertiaTuner; SystemTuner slot 0xc is UpdateUIVar (zUI.md) | high |
| 202 | 0x3c1050 | `CStickInertiaTuner` | A | `~CStickInertiaTuner` | deleting destructor: stores the CStickInertiaTuner, then the base tables, DetachUIVar, deletes when the flag > 0 | vtable slot 0x8 of CStickInertiaTuner; SystemTuner / UIVarMixin slot 0x8 are their destructors (zUI.md) | high |
| 203 | 0x3c1a70 | `(free, file static)` | B | `IOPRebootHandler` | UIStoreOptions(0, 0), returns 1 | zUI.md proposed it: InitSystemTuners passes it to CIOPManager::RegisterRebootCallback, whose callbacks elsewhere are statics named IOPRebootHandler; the membership data gave SystemTuner | medium |

## src/gamez/zUtil/util_memcard.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 204 | 0x31e370 | `CMemCard` | B | `CheckCard` | (bool sync): polls the card on the port at +0x24 (sceMcGetInfo, then sceMcSync), true for a formatted card, flips the port global; MEMCARD_ERROR event anim on error | small-2.md proposed it; callers Init (four times), 0x31e880 | medium |
| 205 | 0x31e880 | `CMemCard` | B | `ReInit` | Init's body again with the init count forced to 1: loads MCMAN / MCSERV, sceMcInit, CheckCard four times, sceMcSync | small-2.md proposed it; caller the zMenuState IOPRebootHandler | medium |

## src/gamez/zVisual/vis_bands.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 206 | 0x327d00 | `zdb::CVisData` | A | `SearchBatchVertex` | (id): in a type 10 packet, finds the entry whose halfword +6 is the id and steps past it; past the end, Clear and NULL | body; zVisual.md: the by-batch search of the new mesh-vertex walk, names only guessed there; caller 0x327df0 | low |
| 207 | 0x327fc0 | `zdb::CVisData` | A | `SearchMeshVertexInPacket` | the inner search of the new walk: steps the packets (types 1, 3, 5, 11) until a type 11 batch holds vertices; Clear and 0 at the end | body; zVisual.md: the inner part of the walk, like SearchVertex's; caller 0x3280c0 | low |
| 208 | 0x328290 | `zdb::CVisData` | A | `SelectMeshVertex` | (mesh, id): Clear, points the walk at the mesh's packet data, stores the matrix id at +0x54 and starts the outer search (0x3280c0) | zVisual.md proposed it (the mirror of SelectVertex) | low |

## src/gamez/zVisual/vis_decal.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 209 | 0x32c600 | `RTArray<zdb::CMeshDecal>` | B | `GetNext` | (bool keep): pops the next free entry of the array (count +0x14) and, with the flag (+0x18), puts it on the used list | zVisual.md: the raw bytes of RTArray<CDecal>::GetNext; only caller CMeshDecalPool::Get; between PutBack and ~RTArray | high |

## src/gamez/zWeapon/zwep_ftsweapon.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 210 | 0x32ef20 | `CTargetMods` | B | `GetTarget_DilateUponFire` | returns the float at +0x20 | zWeapon.md: the field SetTarget_DilateUponFire writes, in the getter run after GetTarget_DilateUponMovement | high |

## src/gamez/zWeapon/zwep_projectile.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 211 | 0x331280 | `PlacedExplosive` | A | `HandleProximityHit` | with a hit list (+0x20) and a line test (+0x28) that BlastReaches (0x331550) passes: calls the hit node's handler (+0x94, slot 2) for the hit at the index in +5, then advances the index | zWeapon.md proposed it; caller PlacedExplosive::PostTick | medium |
| 212 | 0x331340 | `CZProjectile` | A | `RegBlastLineOfSight` | for the next proximity hit not already handled for its node: registers a line test (+0x28) from the blast point to the node's box centre | zWeapon.md proposed it; callers CZProjectile::PreTick, PlacedExplosive::PreTick | medium |
| 213 | 0x331550 | `CZProjectile` | A | `BlastReaches` | (intersect): walks the hits on the line; a material whose blast factor (+0x20) is ~0 stops the blast, else the distance is weighed against the explosion radius^2 | zWeapon.md proposed it; callers CZProjectile::PostTick, 0x331280 | medium |

## src/gamez/zWeapon/zwep_projectilelist.cpp

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 214 | 0x3354a0 | `CZProjectileList` | B | `FreezeAll` | sets bit 0 of +6 on every active projectile and on every placed one in use (both PreTicks return early on it) | zWeapon.md proposed it; caller _OnMissionComplete | medium |
| 215 | 0x336e90 | `CZAmmoPickupInstance` | A | `Compact` | erases, in step, the entries of the three vectors (+0x0, +0xc, +0x18) whose count (third vector) is 0 | zWeapon.md proposed it for the new CZAmmoPickupInstance members; the membership data gave std::__vector_pod<unsigned_int,std::allocator<unsigned_int>> | medium |
| 216 | 0x337280 | `CZAmmoPickupInstance` | A | `AddEntry` | (a, b, c): appends one value to each of the three vectors | zWeapon.md proposed it; callers ftsFixupAiMap, CreateNetAmmoPickup, FillAmmoPickupInstance; the membership data gave std::__vector_pod<unsigned_int,std::allocator<unsigned_int>> | medium |
| 217 | 0x337320 | `CZAmmoPickupInstance` | A | `CZAmmoPickupInstance` | constructor: three empty vectors (+0x0, +0xc, +0x18) and +0x24 = 0 | zWeapon.md: called after new(40) at the three sites that built the record inline in the prototype; the membership data gave Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1> | high |

## (no owner file)

| # | address | class | tier | proposed name | what the body does | basis | confidence |
|---|---|---|---|---|---|---|---|
| 218 | 0x14e310 | `std::basic_string<char,std::char_traits<char>,std::allocator<char>>` | A | `append` | append(n, c): throws the "basic_string::append results in ..." error on overflow, grows with __change_size and memsets n copies of c | MSL basic_string::append(size_type, charT) shape and its error string | high |
| 219 | 0x1a53f0 | `CAiMaps` | A | `WalkLine` | (from, to, callback, data): locates both points on the maps, steps along the line (GetLocation, GetMapByIndex, GetCell, _interp) and calls the callback per cell until it returns false | body; the CAiMap::WalkLine overloads take the same callback; zSeal-f.md calls it a WalkLine-style walk | medium |
| 220 | 0x1d9780 | `zar::CZAR` | A | `BufferWrite` | appends n bytes to the memory write buffer at +0x30, creating it (16 bytes) on first use and growing it with calloc/realloc (zar_main.cpp 1108/1109), memcpy | zArchive.md proposed it (the memory counterpart of fwrite in Insert(CKey*)) | medium |
| 221 | 0x24b210 | `std::__vector_deleter<T> (T unknown)` | A | `__vector_deleter` | default constructor of a 12-byte vector base: the allocator constructor, then three zeroed words; called by __sinit_zrndr_pipe.cpp | the same bytes as the MSL vector default constructors (zUI.md said so of 0x39e210); the allocator call carries no element type; the membership data gave std::allocator<unsigned_int> | low |
| 222 | 0x24b260 | `std::__vector_deleter<T> (T unknown)` | A | `__vector_deleter` | the same default constructor as 0x24b210 (another instance); called by __sinit_zrndr_pipe.cpp | byte twin of 0x24b210; the membership data gave std::allocator<unsigned_int> | low |
| 223 | 0x2517a0 | `CZSealBody` | A | `CreateHostageAnchor` | (type, name): unless m_hostage_anchor (+0xde0) is set, creates a compass anchor by type (9 "BRAVO", 8, 4 "ESCORTEE" at +0x1c with three extra points), renames it, sets m_type, stores it at +0xde0 | body: it replaces the removed CZSealBody::CompassAnchor_Hostage (zSeal-f.md, xcheck-1.md); seal.cpp strings; the membership data gave CSealCtrlAi | medium |
| 224 | 0x25ef90 | `CZSealBody` | A | `@272@BodySetState` | thunk: this - 272, then BodySetState | the thunk pattern (zSeal-f.md); slot 0x14 of the CBody-in-CZSealBody table | high |
| 225 | 0x28f120 | `CSealCtrl` | B | `MenuStateIs` | returns arg == the menu-state byte +0x221 (the byte Get/SetMenuState use) | zSeal-d.md proposed it; callers CMission::Tick, 0x1f9210 on the player's controller | medium |
| 226 | 0x297d50 | `CZSealBody` | A | `ReleaseLadder` | when the ladder index (+0xf8a) is valid, decrements that ladder's user count and resets the index | zSeal-d.md proposed it; callers OnDeath, PreTick, the destructor, FlingBody, PopBlend | medium |
| 227 | 0x297df0 | `CZSealBody` | A | `IsReadyToFire` | alive, the top blend is none of ten anim types, CanFire(), a flag in +0xf86 clear and the body state not 6 | zSeal-d.md proposed it; callers CSealCtrl::PreTick, CZKit::HandleFireWeapon | medium |
| 228 | 0x2e0880 | `CSealUnit` | A | `GetCenter` | (out, depth): the average position (+0x1c) of the member entities (list +0x40) and, while depth > 0, of the sub-units (list +0x58) weighted by their counts; returns the count | body; recursive; callers CSealUnit::AllowCommand and itself | low |
| 229 | 0x2e0a80 | `CSealUnit` | A | `GetMaxDistSq` | (point, depth): the largest squared distance from the point to a member entity (list +0x40) and, while depth > 0, to the sub-units' members | body; recursive; callers CSealUnit::AllowCommand and itself | low |
| 230 | 0x301b30 | `(free, 989snd)` | A | `snd_StopAllSounds` | snd_SendIOPCommandNoWait(0x18, 0, 0, 0, 0) | body: a 989snd IOP command between snd_SoundIsStillPlaying_CB and snd_ContinueSound; callers CSndInstance::StopAllSounds and UIStopAllSounds; the command name is a guess; the membership data gave CSndInstance | low |
| 231 | 0x302870 | `CSnd` | A | `StopGroupVolTemp` | when the group-volume fade timer runs (> 0 or 1e9): sets the group volume back to 1.0 and calls ResetGroupVolTemp(0.01) | body; next to ResetGroupVolTemp; caller CSndInstance::StopAllSounds | low |
| 232 | 0x309a60 | `Headset` | A | `Flush` | when the headset is available and the stream not stopped (+0x9 != 3): stops it (snd_DoExternCall 6), state 3; then DeQueue until empty, clears the vector at +0x18 and sets +0xb | body; next to StopSound; caller CCinematicState::Init | low |
| 233 | 0x3d6e70 | `CHUD` | A | `UpdateClockText` | once a second prints the game time as "%02d:%02d" into the text at +0x3540 and shows or hides it and its partner (+0x35d0) by the viewer's state and the online flag; a negative time shows another string | body (the style of UpdateZoomText); caller CHUD::Tick | low |
| 234 | 0x431b08 | `(free, SCE ezNetCnf)` | A | `ezNetCnfExit` | when bound: finds the eznetcnf module, stops and unloads it, clears the bound flag; returns it | zNetwork-c.md: part of the SCE ezNetCnf library (libezcnf.c) beside ezNetCnfInit; the name is its guess; the membership data gave CNetCnf | low |
| 235 | 0x432760 | `CShutdownState` | A | `UnInit` | empty | vtable slot 0x1c of CShutdownState; CGameState slot 0x1c is UnInit (state.md) | high |
| 236 | 0x432770 | `CShutdownState` | A | `Tick` | returns 0 | vtable slot 0x14 of CShutdownState; CGameState slot 0x14 is Tick (state.md) | high |
| 237 | 0x432780 | `CShutdownState` | A | `Init` | shuts down sound (0x30c310), CPipe, pads, CD and SIF, then LoadExecPS2 of NTGUI.ELF (or the host build) with the return arguments; returns 1 | vtable slot 0x10 of CShutdownState; CGameState slot 0x10 is Init (state.md) | high |
| 238 | 0x43d460 | `CRebootState` | A | `UnInit` | empty | vtable slot 0x1c of CRebootState; CGameState slot 0x1c is UnInit (state.md) | high |
| 239 | 0x43d470 | `CRebootState` | A | `Tick` | returns 0 | vtable slot 0x14 of CRebootState; CGameState slot 0x14 is Tick (state.md) | high |
| 240 | 0x43d480 | `CRebootState` | A | `Init` | the same shutdown, then LoadExecPS2 of the game itself ("-m", "dlgAfterReboot.rdr"; or the host build); returns 1 | vtable slot 0x10 of CRebootState; CGameState slot 0x10 is Init (state.md) | high |

## Class doubts

Functions whose class the body does not support as given (no use of the first argument as an object of that class, or a free helper, a static, a template instance, a library function):

- #3 0x30ab10 `FindDevice` (membership class `Headset`): no this, three out arguments: a static.
- #8 0x4206b0 `hudOpenHelpPopup` (membership class `CHUD`, proposed `(free)`): its a0 is a popup record (x, y, w, h, ...), not a CHUD; the CHUD hint is the static GetHUDOwner call.
- #10 0x422190 `~vector` (membership class `Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1>`, proposed `std::vector<T*> (T unknown)`): a std::vector instance; compressed_pair_imp is only its allocator member.
- #11 0x422220 `~vector` (membership class `Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1>`, proposed `std::vector<T*> (T unknown)`): as 0x422190.
- #12 0x4222b0 `~vector` (membership class `Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1>`, proposed `std::vector<T*> (T unknown)`): as 0x422190.
- #13 0x422340 `~vector` (membership class `Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1>`, proposed `std::vector<T*> (T unknown)`): as 0x422190.
- #14 0x4223d0 `~vector` (membership class `Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1>`, proposed `std::vector<T*> (T unknown)`): as 0x422190.
- #17 0x1416d0 `Reboot` (membership class `CGameMenu`): uses no this: looks like a free function (the "given" hint is a register-scan artefact; zVid_Assert calls it too).
- #22 0x1a9a80 `_interp<CPnt3D>` (membership class `CPnt3D`): not a CPnt3D member: the template function ai::_interp<CPnt3D> (namespace ai), its a0 is a point argument.
- #27 0x1d7490 `OnUpdateMpFinalStatsUiVars` (membership class `@unnamed@st_mpexit_cpp@`, proposed `@unnamed@zanim_menu_cpp@`): evidence says @unnamed@st_mpexit_cpp@ only because it calls TickMpStats; it is a zanim_menu.cpp command handler (its key, both neighbours).
- #29 0x1d82b0 `OnCleanupMissionMemory` (membership class `CCharacterType`, proposed `@unnamed@zanim_menu_cpp@`): evidence says CCharacterType because it calls CleanupTemporary (a static); it is a zanim_menu.cpp command handler.
- #30 0x1d9620 `~__vector_deleter` (membership class `std::__vector_deleter<CCharacterWeap,std::allocator<CCharacterWeap>>`): the instance is not CCharacterWeap's (that destructor is the next function); the element type is unknown.
- #31 0x1dda40 `GetRecordSize` (membership class `zar::CKey`): uses no this: could be a static or an inline constant.
- #47 0x1f1470 `remove_copy_if<std::list<CEntity*>::generic_iterator<0>, ..., bool (*)(CEntity*)>` (membership class `std::__vector_deleter<CTarget,std::allocator<CTarget>>`, proposed `std`): a free std algorithm instance, not a __vector_deleter<CTarget> member (neighbour placement only).
- #53 0x20de70 `fn_0020de70` (membership class `CCtrlrConfigs`): uses its a0 only as a byte array: an inline helper, not a CCtrlrConfigs member.
- #54 0x20de80 `fn_0020de80` (membership class `CCtrlrConfigs`): a dereference helper (of a byte pointer or iterator), not a CCtrlrConfigs member.
- #55 0x20de90 `fn_0020de90` (membership class `CCtrlrConfigs`): a pointer-add helper, not a CCtrlrConfigs member.
- #59 0x1f88b0 `UpdateNetGame` (membership class `CMission`): only forwards its second argument; this is unused.
- #60 0x1f9710 `fn_001f9710` (membership class `CMission`): its a0 is CMission+0xb4, not a CMission: the constructor of an unknown member type.
- #62 0x208ad0 `~__vector_deleter` (membership class `CZSealState::CRemoteGuyList`, proposed `std::vector (8-byte element)`): a std vector instance (element type unnamed), not a CRemoteGuyList member: ~CRemoteGuyList hands it its vector.
- #64 0x217090 `operator-` (membership class `zdb::CGrid`, proposed `CPnt3D`): a CPnt3D operator, not a zdb::CGrid member (it sits in grid_di.cpp, its only caller).
- #70 0x343b20 `PersistentGame` (membership class `MediusGameListResponse`, proposed `PersistentGame`): evidence named MediusGameListResponse (its base's operator= on this); the tables make it PersistentGame's constructor.
- #71 0x235620 `fn_00235620` (membership class `zdb::CRipple`): no this: a vertex-unpack helper (caller CVisual::ApplyDecal), placed in node_wave.cpp by position only.
- #91 0x25f260 `FindDeployLoc` (membership class `CSealCtrlAi`): the body never uses its first argument: a static or a free helper.
- #94 0x2629a0 `fn_002629a0` (membership class `CAiSAnimate`): an accessor of the list type, not a CAiSAnimate member (callers pass CAiSAnimate +64).
- #95 0x264240 `fn_00264240` (membership class `CAiSGrenade`): an accessor of the list type, not a CAiSGrenade member.
- #109 0x267f60 `PostSoundEvent` (membership class `CAiEvent`, proposed `CSealCtrlAi`): evidence said CAiEvent (the acquired event is handed to CAiEvent::Create); this is the controller (+0x4 its seal).
- #116 0x276500 `SetTeammateSoundValve` (membership class `CSealCtrlAi`): it tests its first argument for NULL: a static or free function taking the AI.
- #118 0x2f7290 `PointInWedgeXZ` (membership class `CPnt3D`, proposed `(free)`): a free geometry helper: CPnt3D is only its argument type (CPnt3D::Sub calls).
- #126 0x2ee9e0 `DeleteIfAvoidState` (membership class `CSealCtrlAi`): no this: a static predicate (like CEntity's 0x1f1210).
- #127 0x2eebd0 `GetStateMask` (membership class `CSealCtrlAi`): uses no this: a static.
- #132 0x2fa470 `ShouldAvoid` (membership class `CAiSAvoid`): takes two seals and no CAiSAvoid: a static or free function.
- #137 0x27a650 `RestrainBuddyCallback` (membership class `CZSealBody`): the prototype's PickupBuddyCallback__FPvPv next to it is a free function; this callback is likely free too.
- #150 0x298220 `DeleteMPBombPickup` (membership class `CZSealBody`): uses no this (works on the player from ftsGetPlayer): a static.
- #156 0x2a8700 `GetNearestBlockingHit` (membership class `CEntity`, proposed `CZSealBody`): the evidence (CEntity) is a base call (CEntity::GetNode); CZSealBody is a CEntity, so the class stays its seal_env.cpp neighbours'.
- #157 0x2a97a0 `CanMarkNode` (membership class `CZSealBody`): its a0 is a node passed to the static GetSeal: a static or free function.
- #160 0x2ad2a0 `FlushAltitudeBatch` (membership class `CZSealBody`): uses no this: a static.
- #164 0x2b1750 `FreeAltitudeBatch` (membership class `CZSealBody`): uses no this: a static.
- #170 0x2caa90 `taskParamCompare` (membership class `CTParam`, proposed `(free, file static)`): no this: a static helper of CTParam::Tick, not a CTParam member.
- #183 0x39e210 `__vector_deleter` (membership class `CGameMenu`, proposed `std::__vector_deleter<T> (T unknown)`): no CGameMenu use: placement only; a container constructor.
- #186 0x3a2180 `LerpPos` (membership class `CUIMapCtrl`): uses no this: a static helper.
- #203 0x3c1a70 `IOPRebootHandler` (membership class `SystemTuner`, proposed `(free, file static)`): an IOP reboot callback, not a SystemTuner member (placement only).
- #205 0x31e880 `ReInit` (membership class `CMemCard`): uses no this (works on the global card 0x4d4840): a static.
- #215 0x336e90 `Compact` (membership class `std::__vector_pod<unsigned_int,std::allocator<unsigned_int>>`, proposed `CZAmmoPickupInstance`): evidence names std::__vector_pod<unsigned int> because the first member is such a vector; the class is CZAmmoPickupInstance (zWeapon.md).
- #216 0x337280 `AddEntry` (membership class `std::__vector_pod<unsigned_int,std::allocator<unsigned_int>>`, proposed `CZAmmoPickupInstance`): as 0x336e90: the vector calls are on its members.
- #217 0x337320 `CZAmmoPickupInstance` (membership class `Metrowerks::details::compressed_pair_imp<std::allocator<unsigned_int>,unsigned_int,1>`, proposed `CZAmmoPickupInstance`): evidence names compressed_pair_imp (the vectors' allocator pairs); the class is CZAmmoPickupInstance.
- #221 0x24b210 `__vector_deleter` (membership class `std::allocator<unsigned_int>`, proposed `std::__vector_deleter<T> (T unknown)`): evidence names std::allocator<unsigned int> only because the empty allocator constructor it calls is named so; it constructs a 12-byte container.
- #222 0x24b260 `__vector_deleter` (membership class `std::allocator<unsigned_int>`, proposed `std::__vector_deleter<T> (T unknown)`): as 0x24b210.
- #223 0x2517a0 `CreateHostageAnchor` (membership class `CSealCtrlAi`, proposed `CZSealBody`): evidence said CSealCtrlAi (one caller register scan); the body reads CZSealBody fields (+0xde0 the hostage anchor, +0x1c the position).
- #230 0x301b30 `snd_StopAllSounds` (membership class `CSndInstance`, proposed `(free, 989snd)`): no argument: a 989snd library function (provider), not a CSndInstance member; the "given" hint is a register-scan artefact.
- #231 0x302870 `StopGroupVolTemp` (membership class `CSnd`): uses no this: a static.
- #234 0x431b08 `ezNetCnfExit` (membership class `CNetCnf`, proposed `(free, SCE ezNetCnf)`): an SCE library function (provider); CNetCnf::Uninit only calls it.
