# boot-aimove notes (socom-port-aimove): AI GOTO, route planning, path following

## State / next step
- (a) DONE (re-checked on HEAD 1d30942: mv9 = 88 plans, 90 arrivals, 0 STOP, 30 shots, heap 21.88 MB at 166 s). GOTO: mv6 (fake pad, no hook) 56..176 s: 95 plans, 100 arrivals, 0 NO ROUTE, 0 STOP,
  heap steady ~21.85 MB; enemies patrol and OutPatrol4 walks up and engages Bailey (30 shots).
  mv7 (hook) = enemy fires at Hutchins / player, player killed, debrief. Default build (def.png) =
  main menu, no STOP (built before the ent_main edits; rebuild with default.sh before merging).
  Clip: build/port/recordings/2026-11-12_ai-patrol.mp4 (run mv8). Screenshots:
  build/port/screenshots/21-ai-movement/.
- Also written: LOOKAT (+ look setters), WAIT, VALVE, STATE (push only), SOUND, GetValve,
  CEntityList::GetEntity/GetEntityByIndex (mv4 STOPped on GetEntity). Not written: COMM, ScanTick.
- Root causes: (1) the seal's AI map location was never set (UpdateAiMapLoc / GetLocation(pos)
  stubs) -> every GOTO "NO ROUTE"; (2) _delete (zsys_memory.cpp) was an empty stub: EVERY operator
  delete leaked (128 KB per plan hit the 32 MB ceiling at ~94 s in mv2). Fixed to the ELF.
- Next: (b) CAiEvent pool + CTEvent::Tick, HandleEvent/EventTick, CAiSPursue::Tick, lift the
  CanPushAiState gate (it also refuses STATE_RESTRAINED; CQB attack needs CAiEvent - pickups
  worker); COMM; ScanTick; WalkLine transcription; SmoothPathLeg.
- Layouts after HEAD 1d30942 (CBits 8 bytes): CAiEvent 0x28, CAiPath 0x9c, CSealCtrlAi 0x5d0 all
  match DWARF (laycheck); only CSealCtrl m_look_mode/m_look_type (4-byte enums) and
  m_camState/m_menustate shift locally.
- zmath.h: after 1d30942 only my DistToVector line differs (also in edits/s_zmath.txt).

## Files
- mine.txt (whole files): ai_mapwalk.cpp, ai_path.cpp, zai.h, zmath.h, zmath_pnt3d.cpp, seal_ctrl.cpp,
  seal_tasks.cpp. Shared (edit files, shared.txt): ai_astar.cpp (s_astar.txt srep + e_astar.rep.txt),
  ai_maps.cpp (s_maps.txt + e_maps.rep.txt), seal_ai.cpp (s_ai.txt + e_ai.rep.txt + e_follow.rep.txt),
  zseal.h (s_zseal.txt), seal_env.cpp (e_env.rep.txt). Also mine: seal_aiscan.cpp, zsys_memory.cpp.
- FlushPlannerQueue in e_astar.rep.txt supersedes socom-port-missionexit's hunk (it now also clears
  the typed path_queue). ai_maps.cpp's zseal.h include duplicates missionexit's.

## Written (ELF addresses)
- seal_tasks.cpp: CTGoto Begin/Tick/End 0x2bc300/0x2bc210/0x2bc100, CTLookAt Begin/Tick 0x2bb0b0/
  0x2badf0, CTWait Begin/Tick 0x2b4230/0x2b4030, CTValve::Tick 0x2b4450, CTState::Tick 0x2b5820 (push
  only), CTSound Begin/Tick/End 0x2b6820/0x2b64b0/0x2b67e0; TASK_GOTO/LOOKAT/WAIT/VALVE/STATE/SOUND.
- seal_aiscan.cpp: SetLookRate/Timer/Flags, ModifyLookFlags, SetScanAngle/Rate, SetDefaultLookParams
  0x2e4660, SetLookPosW 0x2e4600, SetLookDirW x2 0x2e4510/0x2e4480, SetLookDirR 0x2e4390, ClearLook
  0x2e4310.
- ai_path.cpp: GetLength, GetLegPoints/Map, plan_setup/addleg/complete/legcomplete, IncrementPathId,
  Clear, SetTemplatePath, Append/InsertPathLoc, PostProcess, SmoothPath, UpdateTurnAngles,
  UpdatePointFlags, PrintPath (trace), SetPathType (0x193630..0x196650).
- ai_astar.cpp (edits): ~CAiStar, find_path, CreatePlanner/DeletePlanner, FlushPlannerQueue,
  PathPlanBegin/AddLeg/Abort/Execute, AbortPathPlan, ResetPathPlan, TickPathPlanner, PathPlanImmediate,
  CAiPlanner reset/dist/is_traversable/fcost, neighbor table; GetNeighbor inline in zai.h.
- ai_maps.cpp (edits): RegisterPathPlan x2, GetLocation(pos) 0x19c9b0, GetLocationDelta, CanTravelLine,
  GetCellAction; GetRegion/GetRandomLoc return none (port).
- ai_mapwalk.cpp: _TravelLineCallback, CAiMap::CanTravelLine, WalkLine(loc,loc) (interim).
- seal_ai.cpp (edits): GetRouteComplete/Failed, ClearRoute, GetDefaultRouteType/Bias, SetRoute x2,
  SetRouteType/SearchLimit, PathFollowTick 0x264e20, _look_ahead, LadderClimbTick (returns 0), GetValve.
- seal_env.cpp (edit): CZSealBody::UpdateAiMapLoc 0x2a4700. ent_main.cpp (edits): CEntityList::GetEntity
  0x1ee290, GetEntityByIndex 0x1ee0f0. seal_ctrl.cpp: GetThrottleFromSpeed 0x2840d0.
  zmath_pnt3d.cpp: DistToVector (4 args) 0x222750. zsys_memory.cpp: _delete 0x2f48a0.

## Not written / next
- COMM 0x2bde00 (unit iteration, 5 uses; still waits), ScanTick 0x2e3bf0 (looks have no visible
  effect), WalkLine transcription, SmoothPathLeg (paths are not smoothed: A* cell steps),
  UpdatePathWidth / GetLocationWidth, cross-map routes (CGraph::BuildRoute), CAiMap::GetRegion.
- (b) CAiEvent pool (ai_events.cpp: Acquire/Create/Release/GetFirst/NextEvent) + CTEvent::Tick,
  HandleEvent 0x2dcd60 (7464 B), EventTick, CAiSPursue::Tick 0x259930 (4668 B) then lift the
  CanPushAiState gate; STATE_ACTION (doors on paths) and STATE_PATHRECO are refused today.
- (c) guard region / unit order tests in AttackTick.

## Layout fixes (zai.h)
- CAiPath was 164 bytes (DWARF 156): ASTAR_STATUS / PATH_TYPE / PATH_STATE are 1-byte enums now;
  m_points is a vector of CAiPath::point (12 bytes: loc, width:8, flags:8, angle), was CPnt3D;
  m_maps a vector of CAiMap*. points is nested in CAiPath (DWARF: top-level `points`).
- CAiStar (44 bytes, no DWARF): planner, open heap, closed list, map, start, goal, stats.
- Planner classes are CBasicTravel / CStealthTravel / CRestrainedTravel (RTTI), 8 bytes.
- MAP_LINEWALK_STRUCT (no DWARF): map, start, end(?), loc, cell, dist, prev cell.

## Key facts
- Path points are stored goal first; back() is the next point. Legs are planned last to first.
- find_path is time-sliced on RCNT0 (H-blank counts, timerlimit 33 ~ 2 ms per frame).
- Status codes: 0 found, 2 200 slices, 3 search limit, 4 no open nodes, 5 out of time (kept PLANNING).
- GOTO record: +8 speed, +0xc u16: bit0 wait, bit1 armed, bits2-9 count, bit14 waypoints, bit15
  random region spot; +0x10 locs (map<<26 | x<<13 | y).

## Port deviations (flagged in source)
- WalkLine(loc, loc) is an interim half-cell walk, not transcribed (ELF 0x1a7570 3332 B).
- Cross-map routes fail (CGraph::BuildRoute unwritten); GetLocationDelta across maps = cell count.
- plan_addleg's region-graph split (flag 0x20) not written; CBasicTravel/CStealthTravel fcost and
  CRestrainedTravel::is_traversable use the base planner's.
- Doors on a path: STATE_ACTION is refused, so an AI waits at a shut door (ELF behaviour with a
  refused push). Stuck -> STATE_PATHRECO refused too.
- UpdateAiMapLoc: UpdateAiVisMap / boundary warnings not written. LadderClimbTick returns 0.
- CAiMaps::GetRegion / GetRandomLoc return none (GOTO bit 15 unsupported).

## ELF quirks kept
- PathFollowTick's turn test compares the angle with -minTurnAngle on both sides (always slows).
- PathFollowTick's line distance uses (pos.x, 0, pos.y).
- ResetPathPlan restarts at leg 0; an ABORT path at the queue front holds the queue for the tick.
