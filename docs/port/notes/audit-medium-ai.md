# Audit of list medium-ai (2026-11-19, socom-port-audit-mai)

87 functions (31,072 bytes) in 13 files of `gamez/zAI/` (`ai_astar.cpp`, `ai_cell.cpp`,
`ai_events.cpp`, `ai_log.cpp`, `ai_main.cpp`, `ai_map.cpp`, `ai_mapdata.cpp`, `ai_mapio.cpp`,
`ai_maps.cpp`, `ai_mapwalk.cpp`, `ai_path.cpp`, `ai_search.cpp`, `ai_vismap.cpp`). HEAD 81f11022.
Judged file by file in the scan's rank order (ai_map, ai_path, ai_astar, ai_maps, ai_log, ai_cell,
ai_events, ai_vismap, ai_mapdata, ai_mapio, ai_mapwalk, ai_main, ai_search), each against the
packet's disassembly, with the header layouts (CAiCell / CAiMap::action / region bitfields,
AIMAP_PARAMS and CAiMap offsets from `mem.py`, CAiPath, CAiEvent, CAiVisMap).

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 81 |
| DEFECT-FIXED | 5 (A 1, B 0, C 4) |
| DEVIATION-KEPT | 1 |
| UNJUDGED | 0 |

Defect rate 5 / 87 (A or B 1 / 87).

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #53, #85 (the user's rule: the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)).

## Fixes

- A, #79 `CAiPath::~CAiPath` (ai_path.cpp): the port's destructor was empty. The ELF calls
  DeletePlanner (0x196664) and then runs Clear's body inline, so a path destroyed with its plan in
  state INQUEUE, PLANNING or ABORT goes through ai::AbortPathPlan (0x1966a8) and leaves
  ai::path_queue. Without this, the queue kept a dangling pointer that TickPathPlanner reads on the
  next tick, and the path's CAiStar (two node vectors with 8192 entries reserved) leaked. The body
  is now `DeletePlanner(); Clear();`. Graded A because it can crash. The m8 run below destroyed no
  path (the trace never fired), so it only happens when a path's owner (CAiSPathRecover, a seal) is
  deleted while its plan is open.
- C, #69 `CAiPath::UpdatePathWidth`: a leg index of -1 takes m_planleg (+0x24, 0x193f98 /
  0x193fdc); the port took m_curleg. This cannot happen, because the index counts up from 1.
- C, #45 `CAiMaps::GetRegionTypeContainer`: a port-only NULL test of the region is removed. The
  ELF reads the region without a test (0x1977cc), the same as GetClosestRegion (audit-large-c row
  43). Every corner in m_regions is a region of a map in the set (UpdateActionTables), so the test
  never fired.

## Kept deviations

Each reason is recorded in the code. #53 GetLocationDelta: when a map is not in the set, nothing
is transformed and its cell count is 0 (mod-zai.md). #11 GetNextEvent: a cursor with no list
returns NULL; the ELF reads the tail of a NULL list. Both callers pass class 0 or 1. #85 CloseAll:
a NULL entry is skipped; the ELF stores -1 to its id through NULL.

ELF quirks kept (already commented in the code): #68 SetSnakeLength(0) keeps m_snake_len; #2 an
ABORT path at the front of the queue holds the queue for the tick; #50 a map that fails to read
leaks; #17 a full buffer with no write mode is not emptied; #18 Create seeks on the non-append
open; #21 the linear root is stored twice to r2; #22 a zero length leaves `out` unchanged; #20 the
behind-and-far-left/right case can never reach 9 / 3; #86 the far edge is compared with the cell
size; #41 SetCellLink does not NULL-test the cell; #15 Close leaves the persistent events alone.

Float checks: the sum orders (x x + y y) + z z and the adda/madd chains in #29, #30, #70, #11,
#22, #24; b b - (4 a) c in #21; the altitude expression min.y + (k (max.y - min.y)) alt in #56, #71,
#64. The literals 0x3f490fdb, 0x4016cbe4, 0x3fc90fdb, 0x40afede0, 0x4096cbe4, 0x407b53d2,
0x40490fdb, 0x3f34fdf4, 0x3a800004 (two spellings), 0x3dcccccd, 0x3e6147ae, 0x3ecccccd,
0x3d088889, 0x3e910cb3 and 0x3f353f7d were checked to give the ELF word under GCC's truncating
conversion. The one float-to-unsigned conversion (#86 CenterRegion, fptoui) goes through
vis_fptoui, which returns 0 for a negative value, the same as the ELF. Every other conversion is
fptosi, or an unsigned-to-float conversion of a value of 16 bits or less.

Leads for other lists: none new. The NULL-path lead of audit-large-c (lead 1) is closed in the
build flags (`-fno-delete-null-pointer-checks`, `-fno-isolate-erroneous-paths-dereference` in
port/CMakeLists.txt), which #7 ~CAiStar and #41 SetCellLink rely on.

What the packets lacked: the bodies of the ELF's std helpers the port replaces (`find` /
`remove_copy` of CAiMapLoc 0x193cd0, which compares x and y only: read from ref.dis for #72 / #73);
CAiMapLoc::invalid's value (sym.py: 0); AIMAP_PARAMS offsets for the CAiMap constructor's stores
(the packet listed the offsets but not their member names: mem.py); CBits::Resize's word count
(source); the CAiPath owners, which decide whether #79 can be reached (grep).

Runs, on HEAD aac25173 plus these files:
- Default build links (`default.sh audit-mai-default`, 0 undefined).
- One fake-pad m8 run (`pad_start.txt`, 177 s, `audit-mai-fake`, with a test-only trace in
  ~CAiPath): no STOP. The mission ran to frame 3570, and 24 plans completed in the planner (state
  4). Patrols arrived at their GOTO points, and the heap held near 23.07 MB. No CAiPath was
  destroyed during play, so the trace never fired.
- `gate.ps1 -Only roundtrip` on this tree (the destructor is a memory-lifetime change): PASS. 4
  returns, with the heap flat at 18,657,916 bytes in use.

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 28 | 0x1871d0 | 340 | CAiMap::GetSoilByName(char const*) | ai_map.cpp | MATCH | | NULL -> 1, strcasecmp against the 13 names in jump-table order (0x4491f0; index 12 "default" again), index (u8) on a hit, 1 after the loop. Scan differences are the port's string table |
| 27 | 0x186e40 | 512 | CAiMap::CAiMap() | ai_map.cpp | MATCH | | the nine table constructors, dummy cell soil 10 (low 5 bits), bbox min / max = CPnt3D::zero, nx ny dx dy 0, m_cell NULL, m_mapid 0, floor -1, name[0] 0, resolution 0.5, slope 0x3f490fdb (literal checked), flags 0, version (19), mapex NULL / bytes 0, compressed, cellcount, light[0..1] 0, alt_quant 1, overlay / graph NULL |
| 26 | 0x186c20 | 544 | CAiMap::~CAiMap() | ai_map.cpp | MATCH | | bbox min / max = zero, nx ny dx dy 0, m_cell _free("ai_map.cpp", 368) when set, m_cell NULL, FreeEx, DestroyGraph, then the member tables (readers' own dtor) |
| 25 | 0x186a30 | 440 | CAiMap::_validate_cell(MAP_FOREACH_STRUCT const&, void*) | ai_map.cpp | MATCH | | astar dir 8 (bits 28-31), f / g -1, rtflag (bit 26) 0; action bit -> GetCellAction: m_type_invalid (bit 4 of +8) and m_state (bits 20-22) 0 when found; occupied 0; name / action / link bits cleared when GetCellName / GetCellAction / GetCellLink find nothing; 1 |
| 29 | 0x187790 | 244 | CAiMap::GetClosestDir(CAiMapLoc const&, CAiMapLoc const&) | ai_map.cpp | MATCH | | d = (to.x - from.x, 0, to.y - from.y) as signed ints, Normalize, N vector, (x nx + y ny) + z nz < 0 -> GetClosestDir(2, 6) else (6, 10) |
| 30 | 0x187890 | 472 | CAiMap::GetClosestDir(CPnt3D const*) | ai_map.cpp | MATCH | | the same N test with the helper 0x187680 inlined: best = first, least 1, i first..last, d = (i + 8) % 8, cost 1 - dot (same sum order), cost < least replaces; the port calls its copy of the helper |
| 31 | 0x187ab0 | 276 | CAiMap::GetDirByName(char const*) | ai_map.cpp | MATCH | | NULL -> N, strcasecmp against N NE E SE S SW W NW (jump table 0x449270 resolves index i to that name), i on a hit, N after the loop |
| 32 | 0x187bd0 | 444 | CAiMap::GetDirQuat(CAiMap::DIR, CQuat&, bool) | ai_map.cpp | MATCH | | (u8) dir switch, MakeYRot words 0x40490fdb / 0x4016cbe4 / 0x3fc90fdb / 0x3f490fdb / 0 / 0x40afede0 / 0x4096cbe4 / 0x407b53d2 (literals checked), default pi; flip: turn = YRot(pi), quat.Mul(turn, out), copied back, Normalize |
| 33 | 0x187d90 | 256 | CAiMap::GetDirVec(CAiMap::DIR, CPnt3D&) | ai_map.cpp | MATCH | | the eight unit xz vectors (N = -z, diagonals 0x3f34fdf4), default N, returns vec |
| 79 | 0x196650 | 380 | CAiPath::~CAiPath() | ai_path.cpp | DEFECT-FIXED | A | the port's destructor was empty. The ELF first calls DeletePlanner (0x196664), then Clear's body inline: a plan in state 1 / 2 / 3 goes through ai::AbortPathPlan (0x1966a8, which takes the path out of ai::path_queue), and when it is no longer planning the points, waypoints, maps, stats (CAiPathStats::reset) and leg counts are cleared. Without it a path destroyed while queued or planning stayed in the planner queue as a dangling pointer (TickPathPlanner reads it next tick) and its CAiStar (two 8192-node reservations) leaked. Now `DeletePlanner(); Clear();` (Clear's stores equal the inline copy). Reached when a CAiPath owner (CAiSPathRecover, a seal's paths) is deleted with a plan open |
| 68 | 0x193d40 | 320 | CAiPath::SetSnakeLength(unsigned int) | ai_path.cpp | MATCH | | len 0 with a snake length: flag 4 off, Clear inline (abort test, clears, reset, legs 0), m_snake_len kept (quirk, commented); same length returns; len < size resize, reserve(len), m_snake_len, flag 4, state COMPLETE |
| 66 | 0x193630 | 384 | CAiPath::PrintPath() const | ai_path.cpp | MATCH | | the ELF walks the points against the leg goals (m_planleg for -1) and calls AiMaps.GetCellName per point, printing nothing (output compiled out); no state changes. The port's SOCOM_PORT trace line is a debug aid |
| 65 | 0x193540 | 228 | CAiPath::PointInPath(CAiMapLoc const&, unsigned int*) const | ai_path.cpp | MATCH | | empty or no flag 4 -> 0; per point dx unsigned (larger - smaller), dy signed, !(width < dx + dy) -> left = size - k - 1 when given, 1; 0 after |
| 67 | 0x1937f0 | 244 | CAiPath::PassesThrough(CAiMapLoc const&, CAiMap::DIR, int) | ai_path.cpp | MATCH | | first point with the location's x / y: no next point 0, next on another map (6-bit id) 1, else GetClosestDir(point, next) == (u8) dir; none 0; the int unused |
| 69 | 0x193e80 | 492 | CAiPath::UpdatePathWidth(unsigned int) | ai_path.cpp | DEFECT-FIXED | C | the leg index -1 case reads m_planleg (+0x24, 0x193f98 / 0x193fdc, as GetLegMap / GetLegPoints inline); the port read m_curleg. Unreachable (the index counts up from 1). Rest matches: map maps[0] / goal waypts[1] with legs, points from the back, width (byte +4) = GetLocationWidth(p, max), goal hit -> next leg's map (NULL past the last) and goal [2 i + 1]. Kept (recorded): a point with no map is skipped where the ELF calls through NULL |
| 70 | 0x194470 | 644 | CAiPath::UpdateTurnAngles() | ai_path.cpp | MATCH | | < 3 points return; back point angle 0; b from size-2 down to 1 with a = b + 1, c = b - 1: map id change on either side 0x3fc90fdb, a or c on b's cell 0, else in = b - a, out = c - b (x, 0, y as signed ints), both normalised, acosf((x x + y y) + z z) |
| 71 | 0x194f80 | 424 | _SmoothLineCallback(MAP_LINEWALK_STRUCT const&, void*) | ai_path.cpp | MATCH | | NULL cell 0; walkable (0 10 8 9); soil 11 with a previous cell other than this one: altitudes min.y + (0x3a800004 (max.y - min.y)) alt (literal checked), here <= prev else 0; flag 8 with a template: template PointInPath(loc, NULL) |
| 72 | 0x195130 | 220 | CAiPath::SmoothPath() | ai_path.cpp | MATCH | | no points or not COMPLETE 0; SmoothPathLeg per leg; find / remove_copy / erase of CAiMapLoc::invalid (0, compared on x / y only, 0x193cd0) = remove_invalid; 1 |
| 73 | 0x195210 | 344 | CAiPath::PostProcess() | ai_path.cpp | MATCH | | flag 1, points and COMPLETE: legs smoothed, invalid points removed; UpdatePointFlags; flag 2 UpdateTurnAngles; flag 4 UpdatePathWidth(5); flag 0x40 PrintPath |
| 74 | 0x195380 | 520 | CAiPath::InsertPathLoc(CAiMapLoc const&, CAiMap*) | ai_path.cpp | MATCH | | states 1 / 2 / 3 -> 0; point (loc, width / flags / unused 0, angle 0) inserted at end(): no points -> COMPLETE, else only when COMPLETE; then pathId++ and flag 0x40 PrintPath; the map unused |
| 76 | 0x1959c0 | 232 | CAiPath::plan_legcomplete(CAiPath::PATH_STATE) | ai_path.cpp | MATCH | | m_astar NULL; COMPLETE with m_planleg != 0: planleg--, INQUEUE, path_length / cost / ticks / time 0, 1; else state, planleg / curleg 0, PostProcess, pathId++, 0 (the ELF's two copies of that block) |
| 77 | 0x196210 | 604 | CAiPath::GetLegBoundary(int&, int&, int) const | ai_path.cpp | MATCH | | first / last -1, leg -1 -> m_planleg, past the legs 0, one leg (size - 1, 0), else the walk from the back with the leg's start / goal waypoints, first on the start when cur == want, last on the goal when cur == want (1), else next leg (-1 -> planleg) reloaded when < legcount; 1 after. The port zeroes start / goal where the ELF leaves them unset (never read: two or more legs here) |
| 78 | 0x196510 | 308 | CAiPath::GetLength(bool) | ai_path.cpp | MATCH | | no points: m_length 0; m_length == 0 or force: sum over consecutive points on the same map (6-bit id) of sqrtf((f32)(dx dx + dy dy)), dx / dy prev - next as ints, m_length + s; returns m_length |
| 80 | 0x1967d0 | 232 | CAiPath::CAiPath() | ai_path.cpp | MATCH | | vectors constructed, stats reset, state 0 (byte), type 0, bias 1, astar / planner NULL, pathId, legcount / planleg / curleg, app_flags 0, flags 3, length 0, template / overlay NULL, snake_len 0, custom false |
| 75 | 0x1958e0 | 224 | CAiPath::Clear() | ai_path.cpp | MATCH | | states 2 / 1 / 3 -> ai::AbortPathPlan; still one of them -> 0; else points / waypoints cleared, maps size 0, stats fields 0 and m_visited cleared, legcount / planleg 0, 1 |
| 6 | 0x1812d0 | 452 | CAiPath::CreatePlanner() | ai_astar.cpp | MATCH | | four guarded function statics (vtables CAiPlanner / CBasicTravel / CStealthTravel / CRestrainedTravel, byte +4 0); not custom: type 3 / 2 / 1 / 0 picks restrained / stealth / basic / default (other types keep m_planner); new(44): planner, the two node vectors, map GetLegMap(-1), stats &m_stats, GetLegPoints(start, goal, -1), both reserve(8192); m_astar = it (NULL on failure), returned |
| 7 | 0x182b00 | 680 | CAiStar::~CAiStar() | ai_astar.cpp | MATCH | | open nodes' cells (inline GetCell: y < ny, x < nx, scanline span or dummy, NULL off the map and written through, as the port's GetCell with the null-check flags): dir 8, f -1, g -1; closed nodes' cells dir 8, g -1; then the vectors |
| 1 | 0x180ae0 | 280 | ai::PathPlanImmediate(CAiMap*, CAiMapLoc const&, CAiMapLoc const&, CAiPath*) | ai_astar.cpp | MATCH | | PLANNING -> 0; INQUEUE -> removed from path_queue; timerlimit saved and -1, plan_setup, plan_addleg: on success INQUEUE, CreatePlanner()->find_path, DeletePlanner inline, plan_complete((s8) state); timerlimit restored, 1 |
| 2 | 0x180c00 | 412 | ai::TickPathPlanner(float, void*) | ai_astar.cpp | MATCH | | timeroffset = T0_COUNT; while the queue is not empty and (T0 - offset) < timerlimit unsigned: front's state 5 / 4 / 0 -> PrintPath + pop; 1 -> CreatePlanner (NULL -> 5, no step count); 2 and 1 -> find_path, then unless still planning DeletePlanner inline + plan_legcomplete, 0 -> pop + planned++; steps++; other states loop without a step (quirk, commented); returns 0. The port's trace line is a debug aid |
| 3 | 0x180e30 | 204 | ai::AbortPathPlan(CAiPath*) | ai_astar.cpp | MATCH | | PLANNING: DeletePlanner inline, plan_complete(0), remove from path_queue; INQUEUE: plan_complete(5), remove; 1 |
| 4 | 0x180f00 | 336 | ai::PathPlanExecute() | ai_astar.cpp | MATCH | | no legs: the AbortPathPlan branches inline, _plan_path NULL; else not INQUEUE: INQUEUE, push at the tail, peak = max(peak, size); m_planleg = legcount - 1; _plan_path NULL |
| 5 | 0x1810d0 | 212 | ai::PathPlanBegin(CAiPath*) | ai_astar.cpp | MATCH | | the AbortPathPlan branches inline (PLANNING: DeletePlanner, plan_complete(0), remove; INQUEUE: plan_complete(5), remove), plan_setup, _plan_path = path, 1 |
| 52 | 0x199010 | 520 | CAiMaps::UpdateActionTables() | ai_maps.cpp | MATCH | | per map with its list index: every action's id (bits 4-19) = action::invalid[0], m_locExValid (bit 28) -> the six ex locations' 6-bit map id = index; every region's map id = index, m_type (5 bits) < 7 -> pushed to m_regions[type] (+0x84 + 12 type) |
| 50 | 0x198680 | 464 | CAiMaps::ReadMapSet(char const*, char const*) | ai_maps.cpp | MATCH | | path dir + name (or name), Open(path, 1): header word, 36-byte AIMAPS_PARAMS at +12, per m_map_count (re-read each pass) new CAiMap + Read, kept ones pushed with m_mapid = size - 1 (a failed map leaks, quirk commented); CGraph::Create(io, _fixupNode, _fixupEdge, this), spores, UpdateActionTables, UpdateNameTables, ValidateLinks, CreateGraph(false); CFileIO closed by its vtable Close; returns opened. The trace line is a debug aid |
| 62 | 0x19d790 | 256 | CAiMaps::~CAiMaps() | ai_maps.cpp | MATCH | | CGraph::Destroy(m_graph), NULL, then the 7 region vectors, 6 name tables, spores and the list nodes (maps not deleted) |
| 61 | 0x19d570 | 252 | CAiMaps::FreeTables() | ai_maps.cpp | MATCH | | spores, 6 name tables, 7 region vectors each cleared and swapped with an empty temporary (released), CGraph::Destroy(m_graph), NULL |
| 49 | 0x198420 | 608 | CAiMaps::ValidateLinks() | ai_maps.cpp | MATCH | | per map: each link's map id = m_mapid; GetMapByIndex(link map id) inline, GetCellLink(m_link) there, kept when the back link's m_link x / y equal this link's location; the others collected and SetCellLink(loc, false) after the walk |
| 56 | 0x19a660 | 436 | CAiMaps::GetAltitude(CAiMapLoc const&) | ai_maps.cpp | MATCH | | GetMapByIndex inline (NULL 0), inline GetCell (NULL 0), min.y + ((0x3a800004 (max.y - min.y)) alt) (literal checked) |
| 57 | 0x19bfc0 | 348 | CAiMaps::GetCell(CAiMapLoc const&) | ai_maps.cpp | MATCH | | GetMapByIndex inline, NULL -> NULL, y < ny and x < nx, scanline span or dummy cell, else NULL |
| 47 | 0x1980c0 | 224 | CAiMaps::GetCellName(CAiMapLoc const&) const | ai_maps.cpp | MATCH | | GetMapByIndex inline, map GetCellName(loc), NULL without a map |
| 48 | 0x1981a0 | 628 | CAiMaps::CreateGraph(bool) | ai_maps.cpp | MATCH | | kept graph unless rebuild; "AiMap Graph"; per map per link: node by node ex, else a node (link as ex), the peer GetCellLink on the link's map (NULL map not tested), a second node and a 0-length edge; then per earlier link: its node, FlushPlannerQueue, a local CAiPath with flags 0, PathPlanImmediate(map, l, o) -> edge(node, peer) with GetLength(false); m_graph = graph |
| 53 | 0x199610 | 584 | CAiMaps::GetLocationDelta(CAiMapLoc const&, CAiMapLoc const&) | ai_maps.cpp | DEFECT-FIXED | C | recorded (code and mod-zai.md): a map off the set transforms nothing and counts 0 cells where the ELF calls TransformTo / reads m_cellcount through NULL. Rest matches: same map |dx| (unsigned larger - smaller) + |dy| kept earlier; guard removed 2026-11-20: TransformTo / m_cellcount through the maps unchecked. Earlier: (signed); else both maps by index, TransformTo(a, mb, moved) -> distance moved .. b, else _max of the two m_cellcount (+0x70) |
| 45 | 0x1976d0 | 464 | CAiMaps::GetRegionTypeContainer(CAiMap::region::TYPE, CAiMapLoc const&) | ai_maps.cpp | DEFECT-FIXED | C | port-only guard removed: a NULL region was skipped; the ELF reads it (0x1977cc), as GetClosestRegion (audit-large-c row 43); every corner in m_regions is a region of a map of the set, so it is never NULL. Rest matches: m_regions[(u8) type], map by index, GetRegion(corner), dx / dy signed in [0, m_dx) / [0, m_dy) (u16 extents) -> region; NULL |
| 46 | 0x197f70 | 232 | CAiMaps::Tile(CAiMap::region const*, unsigned int, unsigned int) | ai_maps.cpp | MATCH | | NULL region 0; map by index, none 0; map Tile(region, value, flags) (u8), ai::ResetPathPlan, the answer |
| 54 | 0x19a480 | 232 | CAiMaps::CanSeeLine(CAiMapLoc const&, CAiMapLoc const&, CAiMapLoc*) | ai_maps.cpp | MATCH | | different map ids 0; map by index, NULL 0; CAiMap::CanSeeLine (u8) |
| 55 | 0x19a570 | 232 | CAiMaps::CanTravelLine(CAiMapLoc const&, CAiMapLoc const&, CAiMapLoc*) | ai_maps.cpp | MATCH | | as row 54 with CAiMap::CanTravelLine |
| 58 | 0x19c720 | 216 | CAiMaps::GetRegion(char const*, CAiMapLoc&) | ai_maps.cpp | MATCH | | name NULL or no map has it: loc = CAiMapLoc::invalid word, NULL; else the first map's region, loc's map id = the list index |
| 59 | 0x19c800 | 212 | CAiMaps::GetActionById(unsigned int, CAiMapLoc&, CAiMap::action**) | ai_maps.cpp | MATCH | | first map whose FindActionLocation(id, loc, out) succeeds: loc map id = index, 1; else 0 |
| 60 | 0x19c8e0 | 200 | CAiMaps::GetLocation(char const*, CAiMapLoc&) | ai_maps.cpp | MATCH | | first map whose GetLocation(name, loc) succeeds: loc map id = index (6 bits; the port's u8 counter gives the same), 1; else 0 |
| 51 | 0x198870 | 392 | _fixupNode(CGraph*, CGNode*, bool, unsigned int&, void*) | ai_maps.cpp | MATCH | | reading: loc from the packed word (id >> 26, x bits 13-25, y bits 0-12), map by index, node ex = GetCellLink(loc) or NULL; writing: (id << 26) / (x << 13) / y of the link's location |
| 19 | 0x1a93d0 | 276 | CAiLog::~CAiLog() | ai_log.cpp | MATCH | | write mode (2): used bytes written when the file is open (vtable IsOpen / fwrite), used 0; Close; _free(buffer, "ai_log.cpp", 33), NULL; m_log cleared when it is this; then the CFileIO member (its Close) and the vector |
| 17 | 0x1a9190 | 340 | CAiLog::Write(unsigned int, unsigned int, unsigned int, void const*) | ai_log.cpp | MATCH | | type < 32 and not in the mask -> 0; !(size + 12 < 8192 - used) and write mode: flush when used and open, used 0 (quirk commented: no flush without write mode); 12-byte header {type, word, size} memcpy, used += 12, data when size != 0; 1 |
| 18 | 0x1a92f0 | 208 | CAiLog::Create(char const*, bool) | ai_log.cpp | MATCH | | open file -> 0; append: mode 26, Open(name, mode); else mode 10, Open(name, 10) and fseek(0, 2) on success (quirk commented); returns IsOpen |
| 8 | 0x185200 | 408 | CAiCell::CAiCell() | ai_cell.cpp | MATCH | | soil 1, occupied / name / action (byte 0 bits 5-7), link (bit 8), boundary (19-20), altitude (9-18), shadow (22-23), inside / badalt / rtflag / bilinear (24-27) 0, astar dir 8 (28-31), f / g -1; m_mes (bit 21) untouched as the ELF |
| 14 | 0x17f9f0 | 504 | CAiEvent::Acquire() | ai_events.cpp | MATCH | | empty pool: new(40) with the constructor inline (bits 0 / NULL, Resize(bit_count), Initalize's stores, the word clear); else the pool's front erased and Initalize inline (duration 0, pos zero, type / id 0, owner -1, visible 0, userdata 0, (bits >> 5) + 1 words cleared or count 0); m_id (u16) = nextId, nextId++ |
| 10 | 0x17f330 | 260 | CAiEvent::CAiEvent() | ai_events.cpp | MATCH | | bits 0 / NULL, Resize(bit_count), Initalize inline (as row 14; m_rangeSq untouched) |
| 15 | 0x17fca0 | 460 | CAiEvent::Close() | ai_events.cpp | MATCH | | bit_count 32, in-use events appended to the pool, in-use list emptied, every pooled event deleted and its slot NULL, pool emptied, CAiVisMap::CloseAll; the persistent list untouched (quirk, commented) |
| 11 | 0x17f4a0 | 436 | CAiEvent::GetNextEvent(CPnt3D const*, CAiEvent::iterator&, float) | ai_events.cpp | DEVIATION-KEPT | | recorded in the code: a cursor with no list (GetFirstEvent of a class other than 0 / 1; both callers pass 0 or 1) returns NULL where the ELF reads the NULL list's tail and an unset node. Rest matches: node advanced before the tests, (s8) type in the mask, cursor type 15 = any else equal, owner skipped, seal bit (not for ENTITY 3) seen -> skip, range 0 found, else (x x + y y) + z z of pos - ... < range * scale |
| 12 | 0x17f660 | 244 | CAiEvent::GetFirstEvent(CAiEvent::EVENT_CLASS) | ai_events.cpp | MATCH | | (u8) class 0 in-use / 1 persistent list and its begin, else list NULL (node unset); type 15 (byte), mask -1, owner -1, bit -1 |
| 13 | 0x17f8f0 | 232 | CAiEvent::Create(CAiEvent*) | ai_events.cpp | MATCH | | duration == NoExpire (-99) -> persistent list tail, else in-use tail; every callback m_fn(event, m_data) in order. The port returns the event where the ELF's v0 is left over (no caller reads it) |
| 9 | 0x17f080 | 248 | CAiEventQ::Create(unsigned int) | ai_events.cpp | MATCH | | first handle whose 16-bit id equals id (the ELF compares the whole id; its one caller HandleEvent passes the 16-bit m_id), else a handle {id, state 0, data 0} inserted at the end and returned |
| 16 | 0x180000 | 240 | CAiEvent::GetEventString(CAiEvent::EVENT) | ai_events.cpp | MATCH | | (s8) event unsigned < 15 through the jump table 0x449010 (13 ALARM, 14 LIGHTSOFF), else UNKNOWN |
| 86 | 0x1a2300 | 500 | CAiMap::CenterRegion(CAiMapLoc const&, CAiMap::region&) const | ai_vismap.cpp | MATCH | | hw / hh = region dx / dy >> 1 (u16); (f32)(u32)(x + hw) <= m_dx (the cell size, quirk commented) -> x - hw else fptoui(m_dx - (f32) region dx) (vis_fptoui: negative 0, as fptoui 0x16d7a0); y - hh < 0 (signed) -> 0, (f32)(s32)(y + hh) <= m_dy -> y - hh, else fptoui(m_dy - (f32) region dy); 13-bit stores; 1 |
| 84 | 0x1a1c40 | 388 | CAiVisMap::CAiVisMap() | ai_vismap.cpp | MATCH | | m_map NULL, m_loc = CAiMapLoc::invalid, region corner unset, dx / dy 0, type / nodisplay / flags / unused 0, name[0] 0, state (byte +0x40) 0, line / cells / bytes 0, bits NULL, id -1, lifetime -1 |
| 85 | 0x1a1dd0 | 252 | CAiVisMap::CloseAll() | ai_vismap.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: an entry's id is written without a NULL test (0x1a1e08). Earlier: recorded (code, mod-zai.md): a NULL entry of globalVisMap is skipped where the ELF stores its id -1 through NULL (delay slot 0x1a1e08). Rest matches: id -1, the inline destructor (bytes / map 0, delete[] bits, NULL), delete; both lists erased |
| 83 | 0x1a0ea0 | 288 | CAiVisMap::FindEvadeLocation(CAiMapLoc const&, CAiMapLoc&) | ai_vismap.cpp | MATCH | | no map 0; function statics max 20 / min 2 (guarded); s from min while s < max: CheckBoxEdges(loc, s, out, UNSEEN, 0, 0), stop on a hit; none 0; else (u16) out.y < ny and out.x < nx |
| 87 | 0x1a2500 | 588 | CAiVisMap::RegisterDynamicVisMap(CAiVisMap*, CAiMapLoc const&, int) | ai_vismap.cpp | MATCH | | already listed 1; size 2 r, cells size^2, words (cells >> 4) + (cells & 15 != 0), bytes 4 words, !(bytes < 16000) -> 0; m_cells; m_bytes < bytes: bytes / map 0, delete[] bits, new[](bytes), width / height = size; m_bytes, memset(bits, nosee_byte 0) when bits; pushed at the tail, corner (0, 0, map 0), dx / dy = size (u16), state 1, UpdateDynamicVisMap(vm, loc), 1 |
| 34 | 0x19dce0 | 440 | CAiMap::CreateGraph(bool) | ai_mapdata.cpp | MATCH | | rebuild: Destroy, NULL, flag 1 off; no routes: the same and return; "AiMap Graph"; a node per type-4 region (5 bits of +8; node ex = region, SetName(m_name)); per route without flag 1: FindByLocation of both region corners, nodes by ex (first, then second), CreateEdge, length = m_path.ComputeLength, edge ex = route; m_graph, flag 1 when set |
| 36 | 0x19e0a0 | 604 | CAiMap::ValidateRoutes(bool) | ai_mapdata.cpp | MATCH | | routes without flag 1: both regions found else flag 1; first waypoint in the first region (signed dx / dy in [0, u16 extent)) and type 4, last waypoint in the second and type 4, else flag 1; reroute -> ReRoute; then remove_if(_invalid_route) + erase |
| 35 | 0x19dea0 | 212 | CAiMapLocVec::ComputeLength() const | ai_mapdata.cpp | MATCH | | empty 0; sum of sqrtf((f32)(dx dx + dy dy)) over consecutive locations, dx / dy prev - next as ints, length + s |
| 37 | 0x19e320 | 532 | CAiMap::ReRoute(CAiMap::route*) | ai_mapdata.cpp | MATCH | | flag 1 set first; a missing region -> 0; >= 2 waypoints: local CAiPath, PathPlanBegin, PathPlanAddLeg per consecutive pair until one fails (-> PathPlanAbort), else PathPlanExecute, TickPathPlanner(0x3d088889, NULL) while state 2 / 1 / 3, points and COMPLETE: flag 1 off, m_path cleared, resized, path[j] = points[n - j - 1]; returns !(flags & 1) |
| 38 | 0x19e710 | 204 | CAiMap::region::Union(CAiMapLoc const&) | ai_mapdata.cpp | MATCH | | x: loc < corner (unsigned) -> left, else corner + dx < loc -> right; y the same signed -> top / bottom; any -> InflateRegion(left, top, right, bottom, NULL) |
| 39 | 0x19e7e0 | 392 | CAiMap::region::InflateRegion(int, int, int, int, CAiMap const*) | ai_mapdata.cpp | MATCH | | x = corner x - left, y = corner y - top, w = right + (x0 + dx) - x, h = bottom + (y0 + dy) - y, max = max_value or nx - 1 / ny - 1; _saturate x (stored), y (stored), w to [0, maxx - x] -> dx (16 bits), h to [0, maxy - y] -> dy, in the ELF's order |
| 40 | 0x19e970 | 276 | CAiMap::GetRegionContaining(CAiMapLoc const&, CAiMap::region::TYPE, bool) | ai_mapdata.cpp | MATCH | | (u8) type; displayed skips m_nodisplay (bit 5 of +8) regions; type 7 any else the 5-bit type; box dx / dy signed in [0, extent); first hit, else NULL |
| 41 | 0x19ec60 | 552 | CAiMap::SetCellLink(CAiMapLoc const&, bool) | ai_mapdata.cpp | MATCH | | inline GetCell (dummy outside the span, NULL off the map, not tested: quirk commented); clear: FindIteratorByLocation + erase, link bit 0, NULL; set: FindByLocation, else a record {loc, link unset} inserted at the end; soil 0 10 8 9 -> 1, link bit 1; the record |
| 42 | 0x19f390 | 272 | CAiMap::AllocEx(unsigned int) | ai_mapdata.cpp | MATCH | | delete[] m_mapex, NULL, bytes 0, every scanline's m_mapEx NULL; bytes != 0: m_mapex_bytes, new[](bytes * m_cellcount), memset 0, scanline m_mapEx = mapex + offset, offset += bytes (end - start); returns m_mapex |
| 43 | 0x18a200 | 208 | CAiMap::read_readers(CFileIO&) | ai_mapio.cpp | MATCH | | ReadCellTable of the reader records; per record: m_reader NULL, new(44) CRdrFile, ReadPacked(io, m_bytes) -> SetReader else zrdr_free; 1 |
| 44 | 0x18a3c0 | 220 | CAiMap::read_lines(CFileIO&) | ai_mapio.cpp | MATCH | | count word (0 preset) read 4 and non-zero: resize(count), per 16-byte line ReadCellTable of its locations and from version 10 its line_data word (+12) read 4; 1 |
| 63 | 0x1a8360 | 256 | _VisLineCallback(MAP_LINEWALK_STRUCT const&, void*) | ai_mapwalk.cpp | MATCH | | guarded statics grass 0x3dcccccd / brush 0x3e6147ae / forest 0x3ecccccd (literals checked); soil 12 / 4 / 5 cover else 0, cover += it; shadow (bits 22-23): first -1 -> first and last, else last; cover < 1 |
| 64 | 0x1a84c0 | 368 | _TravelLineCallback(MAP_LINEWALK_STRUCT const&, void*) | ai_mapwalk.cpp | MATCH | | walkable (0 10 8 9); soil 11 with a previous cell other than this one: altitudes min.y + (0x3a800004 (max.y - min.y)) alt, here <= prev else 0; failed and data -> *data = walk location; the answer |
| 20 | 0x17de90 | 468 | ai::get_clock_direction(CPnt3D const*) | ai_main.cpp | MATCH | | fabsf(x); z < 0: |x| <= 0x3e910cb3 12, <= 0x3f353f7d x <= 0 ? 11 : 1, z <= 0xbe910cb3 9 / 3, else 10 / 2; z >= 0: 6, 7 / 5, z <= -0.2833 9 / 3 (unreachable, quirk commented), 8 / 4; every compare form as the ELF (le / lt), literals checked |
| 21 | 0x17e070 | 284 | ai::quadratic(float, float, float, float&, float&) | ai_main.cpp | MATCH | | a == 0: b == 0 false, else -c / b stored twice to r2 (quirk commented); disc = b b - (4 a) c, inv = 1 / (2 a); !(disc <= 0): r1 = inv (-b + sqrt), r2 = inv (-b - sqrt); disc < 0 false; else -b inv to r2 and r1 |
| 22 | 0x17ec40 | 204 | CAi::GetToRightXZ(CPnt3D const*, CPnt3D*, bool) | ai_main.cpp | MATCH | | normalize: len = sqrtf(x x + z z), 0 == len leaves out (quirk commented), else out = (x / len via 1 / len, y, z / len); else out = in; then y = x, x = -z, z = y, y = 0; returns len (0 without normalize) |
| 23 | 0x17ed10 | 332 | CAi::AlignToPoint(CMatrix const*, CPnt3D const*, CMatrix*, float) | ai_main.cpp | MATCH | | dir 0, point SubXZ(row 3, dir), len = Normalize, Scale(len - dist), at = row 3 + step, side = sceVu0OuterProduct(dir w 1, row 1 w 1) normalised (CPnt3D::Cross inline), SetRows(side, row 1, dir, at) |
| 24 | 0x17eeb0 | 440 | CAi::LeadTargetG(CPnt3D const*, CPnt3D const*, float, CPnt3D const*, CPnt3D const*, CPnt3D*) | ai_main.cpp | MATCH | | speed 0 false; inv = 1 / speed; d = (target - pos) inv, vs = (tvel - vel) inv; a = 1 - ((x x + y y) + z z) of vs, a <= 0 false; b = vs . d, c = d . d (same sum order), t = (b + sqrtf(a c + b b)) / a; lead = (tvel - vel) t, lead.y += 49 (t t); out = target + lead; true |
| 81 | 0x1a9d50 | 228 | _find_look(MAP_FLOODFILL_STRUCT&, void*) | ai_search.cpp | MATCH | | state 1: CanSeeLine(fill loc, &target (the CPnt3D overload), &blocked) -> state 2, find loc = fill loc, 0; else 1; state 0: walkable (0 10 8 9); other states 0 |
| 82 | 0x1a9e40 | 304 | _find_cover(MAP_FLOODFILL_STRUCT&, void*) | ai_search.cpp | MATCH | | state 1 -> 1; not 0 -> 0; walkable -> 1; soil 0 / 8 / 10 only: GetClosestDir(m_next, &target), GetDirDelta(it, (s8) m_next_dir) != 0 -> 0, else state 2, find loc = fill loc, 1; other soils 0 |
