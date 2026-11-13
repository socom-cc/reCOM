# boot-mapglass notes (2026-11-13, socom-port-mapglass, continued by socom-port-mapglass2)

## mapglass2: State / next step (HEAD d4850cc; my files: mine2.txt = copy.txt; shared.txt empty)
- (a) SETTLED, no code change. mga1.log (cameras played out) / mga2.log (both skipped with SELECT):
  ammo 30 -> 25 after the cameras, input 1, menu 0, m_weaponTickDisabled 0 (hook "HOOK: fire" trace).
  mgf3/mgf4's R1 presses all fell inside m8bs / m8tut1. ELF: a mission camera disables only
  CZWeapon::m_weaponTickDisabled and sets menu state 5 (stateFullScreenMapAnim; TickCompassMap needs
  stateNone); PLAYER_CONTROLS (set-0 cmd 0x36, CftsPlayer::CmdTickControls) is in no m8 anim.
  Leftovers: (1) the first R1 after the cameras fires nothing, the following ones do (both runs);
  (2) a SELECT skip opens the map: CleanupCamera 0x403d10 flushes the pad (CPad::Flush 0x21b2b0
  clears m_state) on frame N+3 and a SELECT still held re-reads as FALLING (ELF behaviour, kept;
  the advertised skip is X). The map then closes normally (mga2: 71.4 open, 74.7 close).
- (b) DONE: zAnimDestructorTick 0x1bfd90 -> Particle::DestructionManager 0x232820 -> PullVisuals
  0x233dc0 -> Create3Sided 0x232a50 -> CreateVisuals 0x232ea0 (split > size at 0.4-0.6, 75 % leaves
  -> CVisual::CopyBuffer 0x30d2b0 of the "fragment" model, SetBuffer, CVisData::ReplaceTextureData
  0x310700, 3 vertices) -> Destruction_Instance::Create 0x2367a0 / ctor 0x2368a0 / Tick 0x236390 /
  Render 0x236750. zparticle.h: m_opacity, Create and CreateVisuals static (CreateVisuals returns the
  visual); zvis.h CopyBuffer returns _word128*; zintersect.h friend ::Particle (CDI::m_pts).
  mgb1.log (faithful): tri_window01 2 polys -> 94 shards, heap +77 KB and back after ~0.8 s; the
  round's marks: tri_window01 then worldchild_58 / alaska4d_ntsign03 behind it (the glass has
  penetration 0.99; later rounds pass the opening). Pane: the window anim's OBJECT_ACTIVE_STATE (0x10,
  already written) hides it; SND_GLASS_BREAK_SMALL plays. mgb2-82.png: shards (test hook stretches
  their life x6 and slows them via a --wrap of Destruction_Instance::Create, SOCOM_HOOK_SHARDLIFE).
- (c) FINDING: "levelmap.tif" (InitMap 0x3c5d90, its only reference) is in no texture library on this
  disc (all 14 *_TXR.ZED of RUN/SP/M8 and RUN/COMMON/ASSETLIB searched; only a prop
  alaska4d_map01.tif): the ELF's map has no background image here either. What the ELF draws as the
  tac map is the AI-map geometry: hud.rdr 'TacMap' Polygons / Lines colours per type, through
  CZLineMap TickLines 0x3c8be0 / TickLine 0x3c8cc0 / SetupPolygon 0x3c9950 / TickRegions 0x3c86b0 /
  TickWayPoints 0x3c7a70 / LineTo 0x3ca5e0 / Clip 0x3c76e0, C2DLine (0x2fe8e0-0x300980), CCircleClip::
  CircleSegmentClip 0x220170, CMission::CreateCompassNavPoints 0x1f85f0 (~14 KB asm). Not written yet.
- Tools: test edit edits/t_cmds.txt (ZCMD trace of AddCmd ids); pad_a1 / pad_a2 / pad_b1-3; asm2/
  dumps; hook_actions.cpp: "HOOK: fire" / "HOOK: mark on" traces, SOCOM_HOOK_GLASSCAM ("dx,dy,dz":
  test camera on the target from the first shot, 150 frames), SOCOM_HOOK_SHARDLIFE (+ EXTRAWRAP in
  hooka.sh).

Scratch for (a) the full-screen objective map and (b) breakable glass. Untracked. Changed files:
`mine.txt`; shared-file edits in `edits/` (srep format, listed in `shared.txt`).

## State / next step
- (a) DONE: SELECT opens the full-screen map (objectives list with checkboxes, legend, pad legend,
  player / team blips with view cones, objective anchor star, scroll arrows, north "N"); DOWN/UP
  move the selection (highlight pulses), CIRCLE/SQUARE centre, sticks scroll/zoom, SELECT/TRIANGLE
  close. Logs mg2.log, mgfin.log; screens mg2-70.png, mgfin-72.png.
- (b) PARTLY: the weapon-hit chain is written (CZAnim::OnWeaponHitInit, CZAnimEx::OnWeaponHit /
  Reset, CZAnimExVector, CZAnimSet::AddAnimEx, CZProjectile::GetDamage(4 args)): m8's 12 windows,
  crates, barrels, lights, tyres, generator get their activation-3 anims; a shot destroys a window
  (gl1.log: "ANIMEX: hit tri_window01 ... destroyed", then its anim runs the DESTRUCTOR command).
  NOT written: the shards (DESTRUCTOR -> Particle::DestructionManager chain, see "Next").
- Last runs: mgf3/mgf4 (HEAD 6ab484e tree): map opens/closes after the briefing cameras, stable to
  186 s, heap 21.86 -> 21.96 MB, no STOP. R1 presses after the cameras fired no round (30/30 ammo,
  mgf3-92.png in front of tri_window01), so the shatter was not re-shown there; gl1.log (HEAD
  e13e82a tree) is the hit evidence. Default build (HEAD b175ed7 + mine + edits): dflt.png main menu.
- Next step: find why R1 does not fire after the mission cameras (6ab484e; AI freeze / hold fire?),
  then the shard chain below. Pad scripts must wait out the 21 s briefing cameras (or SELECT them).
- Build: `HOOKSH=hooka.sh bash tb.sh <build> <pad> '<targets>' [test edits]` (hook_actions.cpp puts
  the player in front of node `n<name>:<gap>`, TRIANGLE = next target). Use build names starting
  `mg` (~/.cache/socom is shared: `fin` belonged to boot-fx2 and was reconfigured by me by mistake).
  `tree.sh --fresh` after HEAD moves. `gpref.sh <regex>`: grep the whole-ELF disassembly with the
  containing function (gp-relative refs).

## Written (ELF addresses)
### Map (hud_newhudmap.cpp, hud_playermapitem.cpp, hud_objectives.cpp, hud_linemap.cpp)
- CZNewHudMap: ctor (grid/north SetTrans), GetZoomOut 0x3c6470, ReInit 0x3c6440, InitMap 0x3c5d90,
  UninitMap 0x3c5c80, MapWorldPointToUV 0x3c5be0 (returns CPnt3D), RefreshBackground 0x3c5780,
  CalcNewMatrix 0x3c5510, GetScrollPermissions 0x3c50f0 (CScrollBools), SwitchMapToFullScreen
  0x3c4e20, SwitchToCompassMap 0x3c4c10, HandleScrolling 0x3c4950, TickFullScreenMap 0x3c4420,
  HudTick 0x3c3fc0 (items, player items), Draw 0x3c3c60, TickFullScreenAnims 0x3c3790,
  FindMPBombItem 0x3c34c0, SetupNorthIndicator 0x3c6a50.
- CZPlayerMapItem: all (ctor 0x3dc850, Tick 0x3dc770, TickSealCone 0x3dbe70, SetViewCone 0x3db9c0,
  GetBlipID 0x3dc3f0, Draw/PostDraw/Clip/DrawAlphaBravo, static items, MissionEndCleanup).
- CZObjectiveList: all but the dtor (ctor 0x3c24e0, Init, AddObjective 0x3c2210, RefreshList
  0x3c1c40, RefreshStatics 0x3c0c90 (frame, legend from the compass anchor images/colours),
  Tick, FreeList, Next/Previous/Select* (inline step helpers), SetCurColor, GetObjective, Draw,
  MissionEndCleanup, IsPlayingAnimation).
- CZLineMap: ctor, Tick 0x3c9590 (pulse, cleanup, visible AI maps), TickAnchors 0x3c9220
  (objective / extraction anchors as icons), Draw 0x3c74d0; hudGetTacMapPulseTrans.
- Objectives data: CMission::LoadObjectiveCams 0x1f2ca0 (hudobjectives.rdr HUD_OBJECTIVES, 13 in
  m8), TickObjectives 0x1f6610 (compass anchors of the selected / first open objective; completed
  ones removed), LoadMissionMapVisibilities 0x1fa500, ftsIsMapInVisibleList / GetNumVisibleMaps /
  GetVisibleMap / GetTacMapZoom* (fts_mission.cpp, in place since 6ab484e); CMissionObjectiveCam
  ctor/Set/IsAvailable/IsDisplayOn/IsInvalid (fts_objectivecam.cpp); CZSealBody::GetLookDirW
  0x29e850, HudUpdateViewCone 0x2941a0 (seal_env.cpp).
- Completion: an objective is complete while its VALVE is set (IsComplete); the mission scripts set
  the valves (zAnim VALVE commands, already written). The list re-reads them on every open.
### Glass / destructibles (zanim_anim.cpp, zanim_set.cpp, zwep_projectile.cpp)
- CZAnim::OnWeaponHitInit 0x1cfc90, HealthInit 0x1cf5d0, CZAnimEx::OnWeaponHit 0x1cf660 / Reset
  0x1cf620 / dtor, CZAnimExVector Add/Free/Reset, CZAnimSet::AddAnimEx 0x1c7be0,
  CZProjectile::GetDamage(at, health*, armor*, shield) 0x3176c0.

## Shared-file edits (edits/, shared.txt)
- hu01_map.txt (hud.h): CScrollBools, m_itemlist type, MapWorldPointToUV / GetScrollPermissions
  returns, CZLineMap and CZPlayerMapItem DWARF members, hudGetTacMapPulseTrans declaration.
- zf01_objectives.txt (zfts.h): SObjectiveCam_Anchor, CMission::m_objanchor_vec, fts* map
  declarations, CMissionObjectiveCam::m_vecLines, IsInvalid returns unsigned char.
- zs01_viewcone.txt (zseal.h): HudUpdateViewCone returns bool.
- za01_animex.txt (zanim.h): CZAnimHealth layout, CZAnimEx members public.
- (mc01_missioncam.txt is obsolete: 6ab484e wrote CMissionCam; fm01_objectives.txt was applied in place
  to fts_mission.cpp after 6ab484e, kept for reference.)

## Root causes found
- Heap corruption at load (mg1 hung loading DiMone): CMissionCam's ctor left m_description[2] unset
  (ELF too) and Set frees it -> port clears it (now also in 6ab484e).

## ELF quirks kept
- CMissionObjectiveCam::Set frees m_maptext and never sets it. TickObjectives types the first open
  objective "PRIMARY OBJ" even when it is a secondary. RefreshList returns as soon as it finds a
  selectable primary. TickFullScreenAnims' vertical grid loop stops at the first line not started.
  CZNewHudMap ctor: only the first horizontal grid line gets 128 (delay-slot constant). CalcNewMatrix
  does not negate y. PostDraw switches the name string off (never drawn). SetViewCone ignores the
  range argument.

## Port deviations
- _blips has 9 rows; blip 9 (hidden, still fading) reads past it in the ELF: black here.
- C2DTriFan has no texture member: the clipped-fan texture copies are not made (fans never drawn).
- CZLineMap ctor also clears m_lastline/m_laststring/m_linetex.
- Legend / anchor colours for a type outside 0..32 (unreachable) use zero instead of stack garbage.

## Results
- mg2.log (pad_m1): map at 63.5 s, objectives 0-2 selected with DOWN/UP, closes and reopens;
  mg2-70.png. mgfin.log (pad_f1, hook at tri_window01): map opened/closed twice, 31 items (one
  blip per seal; only the viewer's team-mates show), stable to 176 s, heap 21.83 -> 21.99 MB.
- gl1.log: tri_window01 hit -> destroyed -> DESTRUCTOR (texture alaska4d_window01.tif, shards,
  colour 63 63 70 20, size 10, vel x/z -7..7 y 0..12, life 0.8/0.5, acc 0 -98 0).

## Not written / next
- Level map texture: "levelmap.tif" is in no loaded asset library (TLIB trace in mg3.log: 10 libs),
  so the map background stays off and the world shows through the map rectangle. Find which
  library the ELF loads it from (CHUD::Init / the world's library list).
- Glass shards: zAnimDestructorTick 0x1bfd90 (record: +4 node, +5 texture name, +6 strips, +8 RGBA,
  +24 max size, +28/32 +36/40 +44/48 velocity x/y/z ranges, +52/56 life, +60 friction, +64 accel,
  +76 opacity) -> Particle::DestructionManager 0x232820 -> PullVisuals 0x233dc0 (DI polys of the
  subtree) -> Create3Sided 0x232a50 (fan triangles, UV from the w word /4096, world space) ->
  CreateVisuals 0x232ea0 (3856 B: splits triangles bigger than max size at random 0.4-0.6 into 4;
  a leaf (75 %) copies the "fragment" model's visual buffer (CVisual::CopyBuffer 0x30d2b0 stub,
  CVisData::ReplaceTextureData stub), writes the 3 vertices (pos x16, colour, normal x32768, UV
  x4096) and calls Destruction_Instance::Create 0x2367a0) -> Destruction_Instance ctor 0x2368a0,
  Tick 0x236390, Render 0x236750. Strips (+6 = 1) do nothing in the ELF.
- Whether the pane itself is hidden / its DI removed is done by the window anim's other commands
  (see Results of mgf3).
- CZLineMap TickLines / TickWayPoints / TickRegions / SetupPolygon / Clip (AI-map lines, nav-point
  waypoints, regions; need C2DLine and CCircleClip::CircleSegmentClip, all stubs); C2DLine itself
  (grid / hash / north arrow lines are not drawn); CMission::CreateCompassNavPoints; claymore and
  MP bomb items, UpdateExplosives; CZObjectiveList dtor; CZNewHudMap dtor.
- SELECT during the briefing cameras: the cameras' skip and TickCompassMap both see it; in the port
  the map opens over a playing camera and then cannot close until it ends (TickFullScreenMap returns
  while a mission camera plays). The ELF presumably has the player's input disabled during the
  cameras (TickCompassMap tests m_input_enabled) - voicecams' camera code should check that.

## mapglass2 results
- mgb3.log (pad_b3, hook targets tri_window01 / depot_window01): cameras skipped, map opened/closed 3x, window shattered (94 shards, rounds through to alaska4d_ntsign03 / worldchild_58), mission 72 -> 188 s, no STOP, heap 21.85 -> 21.95 MB. mg2dflt.png: default build (HEAD d4850cc + mine2) at the main menu.
- Screens copied to build/port/screenshots/32-map-glass/ (glass-shards-falling, window-gone-map-after-cameras, facing-window-after-cameras).
- Next: part (c) line map (see FINDING above): C2DLine first (callee), CircleSegmentClip, then CZLineMap TickLine/TickLines/SetupPolygon/TickRegions/TickWayPoints/LineTo/Clip, CreateCompassNavPoints.
- First R1 after the cameras: not checked against the ELF (player anim 1, state 0, no visible cause in the traces).
