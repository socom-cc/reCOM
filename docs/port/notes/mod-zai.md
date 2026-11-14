# boot-mod-zai notes (2026-11-13, socom-port-mod-zai): completing the zAI module

Scratch `build/port/boot-mod-zai/` (untracked). Changed files: `mine.txt` (`src/gamez/zAI/*` and this note);
shared-file edits (zSeal): `shared.txt` + `edits/`.

## State
- DONE. `survey.py gamez/zAI`: 0 stubs (99.9 KB written). The placeholder bodies found in written fences are
  written too, except the cross-map pieces that need zGraph (below).
- Runs (all on HEAD fc0ed62 + mine + the zSeal edit files; `t_trace.txt` = DIAG counters, test tree only):
  - z2 (fake pad, `hook_zai.cpp`: X skips the mission cameras, player cell trace), ~110 s of mission: no STOP,
    heap 21.98 -> 22.00 MB, patrols (`GOTO arrived`), the team follows, cell repel 67 pushes / 28814 calls.
    z1 (same, but SELECT skipped the cameras and opened the tactical map, which pauses): the tac map draws.
  - c1 (`combat` hook, zai3), to 204 s: shot at -> cover cell, pursue with "Finding COVER location", RUSH,
    Shed1 opens door 12 on its path, SURRENDER, FLEE; repel 490 / 103202; heap 22.19 -> 22.28 MB, no STOP.
  - r3 (`exit` hook, `-DSOCOM_HOOK_PAUSE_AT=1500`): pause ABORT 126.6 s, debrief X ->
    `DIAG: CAiMaps::Reset (4 maps)` 146.1 s -> ReOpen_Load -> mission 2 at 148.5 s with patrols again; on to
    362 s, no STOP.
  - def (default.sh, no hook / fake pad): main menu at 9.9 s, then the attract screen; no STOP.
  - Screenshots (untracked): `build/port/screenshots/39-zai/`.
- m8 (disc `RUN/SP/M8/AIMAPS.MPS`): 4 AI maps (map 0 "BaseMap" 265 x 414 cells of 10 units); the links between
  them come with the set's graph. No ladders on the demo disc (see pickups.md / leftovers.md). No m8 GOTO in
  these runs went to another map (`AIPATH` lines are all map 0).

## Written (ELF addresses)
- ai_vismap.cpp: CAiVisMap ctor 0x1a1c40 / dtor 0x1a1be0, RegisterDynamicVisMap 0x1a2500 (static, bool),
  UpdateDynamicVisMap 0x1a1f10 (static: no `this`), ReleaseDynamicVisMap 0x1a1ed0, CloseAll 0x1a1dd0,
  TickVisMaps 0x1a2790, CAiMap::UpdateVisibilityMap 0x1a0950, visCallback 0x1a0460, CAiMap::CenterRegion
  0x1a2300, GetMark 0x1a1b10 (int), CheckBoxEdges 0x1a0fc0, FindEvadeLocation 0x1a0ea0 (bool), reset_line
  (inline). zai.h: the 92-byte CAiVisMap layout (no DWARF; names invented), VIS_TYPE 0 unseen / 1 seen.
- ai_map.cpp: CAiMap::GetCellRepelParams 0x1853a0 (uchar) + CAiMaps' 0x185ab0, ResetCells 0x186080,
  GetMapRegion 0x185ff0, GetSoilByName 0x1871d0, GetDirByName 0x187ab0, GetClosestDir(loc, loc) 0x187790.
- ai_maps.cpp: SetOccupied 0x196e60, SetRegionType 0x1971c0 (bool), Tile 0x197f70 (uchar), GetCellName
  0x1980c0, GetCellNameString 0x198060, GetSporeLocation 0x198a00 (bool), GetBoundary 0x19c120, GetRegion(name)
  0x19c720, Reset 0x19d460, ~CAiMaps 0x19d790, GetInterpolatedShadow 0x19b290 (was "return 0"),
  CAiMap::GetInterpolationCells 0x19ba90 (no fence; this file's artifact), GetLocationDelta across maps.
- ai_mapdata.cpp: CAiMap::GetRegion(name, loc) 0x19ea90, GetRegionContaining 0x19e970 (region *), ReRoute
  0x19e320 (bool; was empty). ai_mapwalk.cpp: CAiMap::Tile 0x1a59a0, _tile_soil 0x1a6150, _tile_boundary
  0x1a6100 (MAP_TILE_STRUCT, no DWARF). ai_path.cpp: UpdatePathWidth 0x193e80, PassesThrough 0x1937f0 (bool).
- ai_astar.cpp: CBasicTravel::fcost 0x183450, CStealthTravel::fcost 0x182ed0, CRestrainedTravel::
  is_traversable 0x182db0 (were the base planner's).
- ai_log.cpp: CAiLog ctor 0x1a94f0, dtor 0x1a93d0, Create 0x1a92f0, Write 0x1a9190 (layout in zai.h; m_log is
  a CAiLog *). ai_main.cpp: CAi::GetToRightXZ 0x17ec40, AlignToPoint 0x17ed10. ai_cell.cpp: CAiCell 0x185200.

## Edit files for other modules' files (scratch `edits/`, listed in `shared.txt`)
- `s_zseal.txt` (zseal.h): CSealCtrl::UpdateAiVisMap returns bool; CSealCtrlAi Play/StopAiSound(AI_SOUND)
  static (UpdateAiMapLoc 0x2a4b44 passes the sound in a0).
- `e_ctrl.rep.txt` (seal_ctrl.cpp): UpdateAiVisMap 0x283e60. `e_control.rep.txt` (seal_control.cpp):
  CSealCtrl::Initalize 0x288050 (was empty: vis map radius 50, m_aimPitch from the character dynamics,
  SetSnakePathUpdate(true, 75)) and ~CSealCtrl 0x2882b0 (vis map released and deleted).
- `s_env.txt` (seal_env.cpp, UpdateAiMapLoc): `changed = UpdateAiVisMap()`; the player's mission boundary
  part (GetBoundary of old and new cell; 2 = outside sets the abort valve; sounds through the still empty
  Play/StopAiSound).
- `s_follow.txt` (seal_aifollow.cpp) and `s_ai.txt` (seal_ai.cpp, InitAiBrain): m_do_aimap_collide is turned
  on as the ELF does (the `#ifndef SOCOM_PORT` guards and the "port:" notes go).
- `s_resp.txt` (seal_airesponse.cpp): the CAiSReload comment (vis maps exist now).

## ELF quirks kept
- The vis maps are vestigial in this build: CenterRegion compares the box's far edge with m_dx / m_dy (the
  cell size, 10 on m8) instead of the grid size, so every box sits at (0, 0); and UpdateAiMapLoc only updates a
  vis map when its caller passes true, which UpdateTargetList / TeleportTo never do, so the player's vis map
  stays at its registration cell (0, 0). FindEvadeLocation then finds an unseen walkable cell 2 rings out.
- UpdateVisibilityMap: a line budget that runs out still moves the state on (the update ends early).
- CheckBoxEdges' box "centre" is the corner less half the size (only used without `closest`, so unused).
- GetCellRepelParams: depth is always 1; the action of an action cell is not NULL-tested (GetCellPos).
- CBasicTravel: leaving a road costs 2 x 0.8, a step between two non-road cells 0.8.
- CAiLog::Write: a full buffer without write mode is not emptied; Create seeks to the end on the non-append
  open. GetToRightXZ: with a zero x/z length the turn works on out as it was.
- SetRegionType writes the region through its const pointer; an old type past 6 is not bounded.

## Port deviations
- visCallback: a cell outside the vis map's box is not marked (the ELF writes its 2 bits unchecked, past
  the 2500-byte array, because of the CenterRegion quirk above).
- The edge / ring cells of UpdateVisibilityMap and CheckBoxEdges take the box's map id (the ELF leaves that
  stack word unset; CAiMaps::CanTravelLine compares it). UpdateDynamicVisMap keeps the eye altitude when the
  cell is missing (ELF: an unset FPU register). CloseAll skips NULL entries.
- UpdatePathWidth skips points past the last leg (ELF: calls through NULL). CStealthTravel: a missing cell
  counts as open. GetLocationDelta: a map off the set transforms nothing. UpdateAiMapLoc's abort valve is
  NULL-tested.

## Not written / next
- Cross-map routes: CAiMaps::RegisterPathPlan's other-map goal and CAiPath::plan_addleg's region split
  (flag 0x20) need zGraph's CGraph::BuildRoute 0x20fa60 and the graph tree / CGRoute (graph_tree.cpp,
  graph_route.cpp, DeleteNode: 5.4 KB of zGraph stubs, not this module). A goal on another map still fails the
  plan; m8 has 4 maps but no tested GOTO crosses them. CAiMaps::CreateGraph(rebuild): the disc sets carry
  their graph. Map versions below 19 (not on the disc).
- CSealCtrlAi::GetAiLog still returns no log (zSeal; CAiLog is written but nothing creates one), and
  Play/StopAiSound are empty (zSeal), so the boundary warnings are silent.
- Ladders: CreateLadderTable / GetClosestLadder are zFTS (socom-port-mod-zfts wrote them); PassesThrough is
  written for LadderClimbTick: written, untested (no ladders on the disc).

## Tools / test
- `hook_zai.cpp` (scratch): X skips the m8 cameras (SELECT opens the map and pauses), player cell trace.
- `t_trace.txt` (scratch, test tree only): DIAG vis map / repel / evade counters and heap every 300 ticks,
  `CAiMaps::Reset` and `GetBoundary` traces. `wsl.ps1` drops a bare `--`: pass `'--'` for hook flags.

## Survey at the start (HEAD df9c0ef; `survey.py gamez/zAI`): 43 stubs, 22456 B
- vis maps (ai_vismap.cpp, 12 fn, 9.4 KB): ctor/dtor, Register/Update/ReleaseDynamicVisMap, TickVisMaps,
  CAiMap::UpdateVisibilityMap + visCallback, CenterRegion, GetMark, CheckBoxEdges, FindEvadeLocation. Callers:
  CAiEvent::Tick, CSealCtrl Initalize / dtor / UpdateAiVisMap (zSeal stubs), CAiSReload, CAiSDeploy.
- map cells (ai_map.cpp, 7 fn): CAiMap::GetCellRepelParams 0x1853a0 (1796) + CAiMaps' 0x185ab0, ResetCells
  0x186080, GetMapRegion, GetSoilByName / GetDirByName (task Parse only), GetClosestDir(loc, loc).
- map set (ai_maps.cpp, 10 fn): SetOccupied, SetRegionType, Tile, GetCellName(String), GetSporeLocation,
  GetBoundary 0x19c120, GetRegion(name), Reset 0x19d460, ~CAiMaps; map data (ai_mapdata.cpp): GetRegion(name),
  GetRegionContaining; map walk (ai_mapwalk.cpp): CAiMap::Tile + _tile_soil / _tile_boundary.
- path (ai_path.cpp): UpdatePathWidth 0x193e80 (flag 4 paths), PassesThrough 0x1937f0 (LadderClimbTick).
- AI log (ai_log.cpp, 4 fn), CAi::GetToRightXZ / AlignToPoint (ai_main.cpp), CAiCell ctor (ai_cell.cpp).
- Written but placeholder bodies found in zAI: CAiMaps::GetInterpolatedShadow 0x19b290 (returned 0: characters
  always lit), CBasicTravel / CStealthTravel fcost and CRestrainedTravel::is_traversable (base planner used),
  CAiMap::ReRoute 0x19e320 (empty), GetLocationDelta across maps (cell count), CAiMaps::CreateGraph(rebuild),
  RegisterPathPlan / plan_addleg across maps (CGraph::BuildRoute, zGraph), map versions < 19 (not on the disc).
- Deviations elsewhere that existed only because of these stubs: follow state / InitAiBrain never turned
  m_do_aimap_collide on (seal_aifollow.cpp, seal_ai.cpp); UpdateAiMapLoc left out UpdateAiVisMap and the
  player's boundary warnings (seal_env.cpp); CSealCtrl::Initalize / dtor / UpdateAiVisMap were empty (no vis
  map, so CAiSReload never evaded); GetAiLog returns no log (CAiLog).
