# Stage 2: gamez/zAI (2026-11-26)

The one list of `gamez/zAI` (list a): the owner files ai_main.cpp, ai_events.cpp, ai_astar.cpp,
ai_cell.cpp, ai_map.cpp, ai_mapio.cpp, ai_path.cpp, ai_maps.cpp, ai_mapdata.cpp, ai_vismap.cpp,
ai_mapwalk.cpp, ai_search.cpp and ai_log.cpp (release 0x17d400-0x1aa780, and 0x31ac40). It holds 21
uncertain rows (11 new, 8 removed, 1 unsure, 1 weak pair (`slot-only`); none flagged
`identical-copy`), 15 sampled deviating rows out of 47, and 394 exact rows that were not checked
one by one. Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`);
checked by `socom-release-check-ai-node`, who did not write the tool, at HEAD 293696c3. The check
sheet (`compare.py --sheet gamez/zAI --list a`) was the starting point. Both images were decoded
with the release tools; callers were found by scanning both images for `jal`/`j`, `lui`/`addiu`
address loads, vtable slots and data words. Ghidra was not needed.

As the guard on the committed pairs, all 443 paired rows of the zAI owner files had their callers,
address loaders, vtable slots and data-word counts compared with the prototype's through the map,
and their own ordered calls and loads compared for substitutions. The ordered calls of every
paired caller (616) of a zAI function were compared too. The 6 vtables with a slot in these files
were aligned slot by slot. Because the module is full of byte-identical template instances (vectors
and lists of map records), each of the 145 paired rows that has a byte twin on either side was
scored: how many of the prototype side's callers (mapped) each release twin shares.

What settled rows, in the order it was used: the call site in a paired caller
(CAiMaps::ComputeLineVisibility, ResetCells, GetSoilByName, CAiSAvoid::Tick, HandleSupport and
AllowCommand, CSealCtrl::Initalize); the callee overload (WalkLine with a CPnt3D or a CAiMapLoc);
the static-init pointer table; the slot between paired neighbours; strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x17d9a0 | - | new, no owner | confirmed; owner ai_main.cpp | Rfloat constructor: stores the minimum at +0 and max - min at +4. The prototype AddNoise built `Rfloat(0, 1)` inline; the release AddNoise calls this three times, and so do CAiSPursue::Tick, CTurret::AcquireTarget and CTurret::Tick. It sits right after Rfloat::operator float (0x17d930), which also moved into ai_main.cpp's range |
| - | 0x17ec40 `GetToRightXZ__3CAiFPC6CPnt3DP6CPnt3Db` | removed | confirmed | its only caller CAiSAvoid::Tick was rewritten (no SubXZ, Normalize or Scale; it calls new 0x2ef9c0, ChooseLookDir and new 0x271020); no release body is like it |
| 0x185db0 | - | new, owner guess | confirmed | resets one cell from a MAP_FOREACH_STRUCT (map +0, cell +4, location +12): the action bits through GetCellAction and the cell's type bits. The prototype ResetCells did this inline; the release ResetCells calls it where the prototype called GetCellAction. It sits between _validate_cell and _reset_rtflag |
| 0x1864e0 | - | new, owner guess | confirmed | soil id to name: a 14-way switch over the soil strings ("nogo" ... "collision", default "default"). GetSoilByName now loops over the ids, calling it and strcasecmp; the prototype loaded each string inline |
| 0x187010 | - | new, owner guess | confirmed | the cosine between two 8-way directions: difference 0 gives 1.0, 1 gives c, 2 gives 0, 3 gives -c, others -1.0. c is the float at 0x460a28 that the release __sinit_ai_map.cpp sets to 0.5 * sqrt(2), and that GetDirVec also reads. Caller new 0x2e6b70; it sits between GetDirQuat and GetDirVec |
| 0x192870 | - | new, no owner | confirmed; owner ai_path.cpp (guess) | CAiPath method (point count +0x90, type +0x78, points +0x8c). From the path's last point it walks two lines offset sideways along GetDirVec(GetClosestDir) with WalkLine and callback 0x192f70. It inserts the points found (built by 0x192e80) into the point vector, then calls PrintPath. Caller new 0x2f9cb0, next to CAiSAvoid::Tick |
| 0x192e80 | - | new, no owner | confirmed; owner ai_path.cpp (guess) | builds a CAiPath::point from a CAiMapLoc (map index, x and z bitfields; width, flags and angle cleared); caller 0x192870 |
| 0x192f70 | - | new, no owner | confirmed; owner ai_path.cpp (guess) | MAP_LINEWALK callback: 0x192870 loads its address and passes it to WalkLine. It tests CanTravelLine both ways and a distance limit |
| 0x193150 | - | new, owner guess | confirmed | CAiPath method: finds a location among the path points by exact cell (x, z) and returns its index from the front; caller CAiSBreach::Tick. It sits after PointInPath, which tests within the point width and counts from the back |
| - | 0x1937f0 `PassesThrough__7CAiPathFRC9CAiMapLocQ26CAiMap3DIRi` | removed | confirmed | its only caller LadderClimbTick was rewritten and no longer uses the path. 0x193150 also searches the points, but it takes no direction and is not in this slot |
| 0x199c00 | 0x19a120 `ComputeLineVisibility__7CAiMapsFRC9CAiMapLocRC9CAiMapLoc` | deviating (weak), slot-only | confirmed | same caller ComputeVisibility (HandleEvent added). Same first part: the map list walk, then the per-map ComputeLineVisibility for the same map. The cross-map part now uses GetCellAction, GetDirVec, Scale and Add and the new CPnt3D overload 0x1a8e90 instead of TransformTo |
| 0x19b0c0 | - | new, owner guess | confirmed | CAiMaps method: GetAltitude with a bool result and the altitude through a float pointer. It gets the map by index and the cell through its scanline, then computes altitude bits * scale (+0xb4) + base (+4), as the release GetAltitude does. Caller CAiSPathRecover::Tick |
| - | 0x19e020 `Contains__Q26CAiMap6regionCFRC9CAiMapLoc` | removed | confirmed | its callers HandleSupport and AllowCommand moved that test into new 0x2ea6e0, which uses CAiMaps::GetLocationDelta instead |
| - | 0x1a2500 `RegisterDynamicVisMap__9CAiVisMapFP9CAiVisMapRC9CAiMapLoci` | removed | confirmed | its only caller CSealCtrl::Initalize is 28 bytes in the release: no `new CAiVisMap`, no registration |
| 0x1a8e90 | 0x1a8280 `ComputeLineVisibility__6CAiMapFRC9CAiMapLocRC9CAiMapLoc` | unsure, position, ambiguous | corrected to new | it calls WalkLine(CAiMapLoc, CPnt3D*), so it is a new CPnt3D overload. CAiMaps::ComputeLineVisibility calls it twice from its new cross-map part |
| 0x1a8f20 | - | new, owner guess | corrected to 0x1a8280 `ComputeLineVisibility__6CAiMapFRC9CAiMapLocRC9CAiMapLoc` | it calls WalkLine(CAiMapLoc, CAiMapLoc) as the prototype did. CAiMaps::ComputeLineVisibility calls it at the paired call site (+0xc4 → +0xd0). The overloads come in the order of WalkLine and CanSeeLine (CPnt3D first, CAiMapLoc second). It takes one argument more (a bool in a3) |
| 0x1a9a80 | - | new, owner guess | confirmed | a·(1-t) + b·t on CPnt3D (Scale, Scale, Add), returning the output: the CPnt3D instance of `ai::_interp`, whose float instance `_interp<f>__2aiFRCfRCffRf` takes the same arguments. Caller new 0x1a53f0 |
| - | 0x1a9190 `Write__6CAiLogFUiUiUiPCv` | removed | confirmed | the release has no "ai_log.cpp" string; CSealCtrlAi's PutAiLog, GetAiLog and SetAiLogEnabled are removed too, and the paired SetAiMode, PreTick and InitAiBrain no longer call it |
| - | 0x1a92f0 `Create__6CAiLogFPCcb` | removed | confirmed | the same (only caller GetAiLog, removed) |
| - | 0x1a93d0 `__dt__6CAiLogFv` | removed | confirmed | the same |
| - | 0x1a94f0 `__ct__6CAiLogFb` | removed | confirmed | the same |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x17d5e0 | 0x17e070 `quadratic__2aiFfffRfRf` | yes | the same four callers |
| 0x17d6f0 | 0x17e1b0 `AddNoise__2aiFP6CPnt3DRC5PNT2D` | yes | same caller OnWeaponHit (ComputeThrowFireParams added); Rfloat now out of line |
| 0x17dc20 | 0x17e8a0 `MakeNoise__2aiFP6CPnt3DRC5PNT2D` | yes | same caller ModifyAimDir |
| 0x1816d0 | 0x182500 `fcost__10CAiPlanner...` | yes | slot 3 of the CAiPlanner and CRestrainedTravel tables on both sides |
| 0x184d50 | 0x185b50 `TransformTo__6CAiMap...` | yes | same callers GetLocationDelta and GetBoundary |
| 0x186460 | 0x1871d0 `GetSoilByName__6CAiMapFPCc` | yes | same caller CTPaint::Parse |
| 0x1865c0 | 0x187330 `GetClosestDir__6CAiMapFRC9CAiMapLocPC6CPnt3D` | yes | same caller _find_cover |
| 0x1886a0 | 0x189390 `Read__6CAiMapFR7CFileIO` | yes | same caller ReadMapSet |
| 0x195ea0 | 0x196510 `GetLength__7CAiPathFb` | yes | the same three callers |
| 0x199040 | 0x199610 `GetLocationDelta__7CAiMaps...` | yes | same caller PathFollowTick (new 0x2ea6e0 and HandleFollowTickStance added) |
| 0x19a6a0 | 0x19a820 `GetBilinearAltitude__6CAiMap...` | yes | same caller ftsGetAltitudeApprox |
| 0x19c9b0 | 0x19c9b0 `GetLocation__7CAiMapsFPC6CPnt3DR9CAiMapLoc` | yes | 18 shared callers |
| 0x19e1f0 | 0x19dea0 `ComputeLength__12CAiMapLocVecCFv` | yes | same caller CAiMap::CreateGraph |
| 0x1a2180 | 0x1a1f10 `UpdateDynamicVisMap__9CAiVisMap...` | yes | same caller UpdateAiVisMap (RegisterDynamicVisMap removed) |
| 0x1a5fb0 | 0x1a56d0 `CountMapVisDir__6CAiMap...` | yes | same caller ChooseLookDir |

Found by the cross-check, outside the list's rows:

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x4817e0 | - | new, compiler-generated | corrected to 0x46a2e0 `__sinit_ai_map.cpp` | the same entry of the static-init pointer table (release 0x488bc4, prototype 0x471284, between the ai_astar.cpp and ai_path.cpp initialisers). Both construct the same CAiCell global. The release one also sets the new static float 0x460a28 to 0.5 * sqrt(2) |
| - | 0x46a2e0 `__sinit_ai_map.cpp` | removed | corrected to 0x4817e0 | see the row above |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x1a8f20 | 0x1a8280 | calls WalkLine(CAiMapLoc, CAiMapLoc) as the prototype did; called at the paired call site of CAiMaps::ComputeLineVisibility (+0xc4 → +0xd0); overload order as WalkLine and CanSeeLine | socom-release-check-ai-node | 2026-11-26 | | |
| 0x1a8e90 | new | calls WalkLine(CAiMapLoc, CPnt3D*): the new CPnt3D overload, called twice from the new cross-map part of CAiMaps::ComputeLineVisibility | socom-release-check-ai-node | 2026-11-26 | src/gamez/zAI/ai_mapwalk.cpp | |
| 0x4817e0 | 0x46a2e0 | the same static-init table entry between __sinit_ai_astar.cpp and __sinit_ai_path.cpp; constructs the same CAiCell global | socom-release-check-ai-node | 2026-11-26 | src/gamez/zAI/ai_map.cpp | |
| 0x17d9a0 | new | owner: the Rfloat constructor, emitted after Rfloat::operator float inside ai_main.cpp's range; first caller AddNoise | socom-release-check-ai-node | 2026-11-26 | src/gamez/zAI/ai_main.cpp | guess |
| 0x192870 | new | owner: CAiPath method (+0x8c, +0x90), directly before ai_path.cpp's first template instances | socom-release-check-ai-node | 2026-11-26 | src/gamez/zAI/ai_path.cpp | guess |
| 0x192e80 | new | owner: CAiPath::point constructor, called only by 0x192870; between ai_path.cpp's instances | socom-release-check-ai-node | 2026-11-26 | src/gamez/zAI/ai_path.cpp | guess |
| 0x192f70 | new | owner: WalkLine callback of 0x192870, directly before PointInPath | socom-release-check-ai-node | 2026-11-26 | src/gamez/zAI/ai_path.cpp | guess |
| 0x31ac40 | 0x1a93c0 | owner: GetSize__7CFileIOCFv sits between util_bufio.cpp's GetMode and fwrite; ai_log.cpp, which emitted the prototype's copy, is gone | socom-release-check-ai-node | 2026-11-26 | src/gamez/zUtil/util_bufio.cpp | |

Rows that change together: 0x1a8f20 and 0x1a8e90 (the unsure candidate moves to its twin); 0x4817e0 and the removed 0x46a2e0 (one row once paired).

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x17d9a0 | builds an Rfloat from a minimum and a maximum | guess: `__ct__6RfloatFff` (the struct's {min, range} layout; the inline `Rfloat(0, 1)` of the prototype AddNoise) |
| 0x185db0 | resets one cell's action and type bits | guess: `_reset_cell__6CAiMapFRC18MAP_FOREACH_STRUCTPv` (the neighbours _validate_cell and _reset_rtflag) |
| 0x1864e0 | soil id to name | guess: `GetSoilName__6CAiMapFUc` (the inverse of GetSoilByName) |
| 0x187010 | cosine between two 8-way directions | guess: `GetDirDot__6CAiMapFQ26CAiMap3DIRQ26CAiMap3DIR` (next to GetDirQuat and GetDirVec) |
| 0x192870 | adds side points to a path along two walked lines (avoidance) | guess: `AddAvoidPoints__7CAiPath...`; arguments not decoded |
| 0x192e80 | CAiPath::point from a CAiMapLoc | guess: `__ct__Q27CAiPath5pointFRC9CAiMapLoc` |
| 0x192f70 | line-walk callback for 0x192870 | guess: a static `_avoid_callback__FRC19MAP_LINEWALK_STRUCTPv` (the pattern of _VisLineCallback) |
| 0x193150 | finds a location among the path points | guess: `FindPoint__7CAiPathCFRC9CAiMapLocPUi` (next to PointInPath) |
| 0x19b0c0 | altitude of a map location, with success flag | guess: `GetAltitude__7CAiMapsFRC9CAiMapLocPf` |
| 0x1a8e90 | line visibility from a location to a point | guess: `ComputeLineVisibility__6CAiMapFRC9CAiMapLocPC6CPnt3Db` (the WalkLine overload it calls) |
| 0x1a9a80 | linear interpolation of two CPnt3D | `_interp<6CPnt3D>__2aiFRC6CPnt3DRC6CPnt3DfR6CPnt3D` (the float instance's signature; a guess in the details) |

Not new, though the map has it as new: 0x1a8f20 (`ComputeLineVisibility__6CAiMapFRC9CAiMapLocRC9CAiMapLoc`) and 0x4817e0 (`__sinit_ai_map.cpp`).

Really removed:

- GetToRightXZ: CAiSAvoid::Tick was rewritten without it.
- CAiPath::PassesThrough: LadderClimbTick no longer uses the path.
- CAiMap::region::Contains: the support test moved into new 0x2ea6e0 (a distance test).
- CAiVisMap::RegisterDynamicVisMap: CSealCtrl::Initalize no longer creates a dynamic vis map.
- CAiLog (Write, Create, destructor, constructor): the AI log is gone, with its CSealCtrlAi users.
- Not removed, though the map has it: `__sinit_ai_map.cpp` (0x4817e0).

Layouts, plainly shown by settled rows: ai_map.cpp gained a dynamically initialised static float
(0x460a28, 0.5 * sqrt(2), the diagonal factor GetDirVec and 0x187010 read).

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses, and so is the purpose of 0x192870.
- The owners of 0x192870, 0x192e80 and 0x192f70 (ai_path.cpp) and of 0x17d9a0 (ai_main.cpp) are by
  class and position.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 11 | 10 | 1: 0x1a8f20 is ComputeLineVisibility(CAiMapLoc, CAiMapLoc) |
| removed | 8 | 8 | 0 |
| unsure | 1 | 0 | 1: the candidate 0x1a8e90 is the new CPnt3D overload |
| deviating (weak), slot-only | 1 | 1 | 0 |

Owners: of the 4 owner-less rows, 3 belong by class to ai_path.cpp and 1 by position to ai_main.cpp
(guesses). The tool's owner guesses held. One exact row has a stale owner: GetSize__7CFileIOCFv
(0x31ac40) is now util_bufio.cpp's copy.

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 443 paired rows compared (callers, address loaders, vtable slots, data words,
ordered calls), the ordered calls of 616 paired callers, 6 vtables slot by slot (no change), 145
rows with byte twins scored by shared callers. Differences looked at: 67 caller sets, 75 caller call sequences, 4 call-order
substitutions, 3 data-word counts, 28 twin ties. They are callers added in the release, callers
rewritten or moved (CAiSAvoid::Tick, LadderClimbTick, the CSealUnit support code into new 0x2ea6e0,
CSealCtrlAi's debug output compiled out), the cross-map part of CAiMaps::ComputeLineVisibility, and
inlining in reserve<CAiMapLoc>. The list<PCv> instances lost their zar callers. The data words are not pointers (round constants, a table of odd code addresses). Twin
ties are all decided by the call position in the shared caller or by the vtable slot (CAiPlanner
`reset`, CFileIO `GetSize`); no twin is given to the wrong row.
Pairs wrong: 0 committed pairs; one missed pair (`__sinit_ai_map.cpp`, a new and a removed row).

What misled it:

- ComputeLineVisibility: the two release overloads have the same bytes except the WalkLine callee and
  their constants, and the same caller; the tool took the first by position. The callee overload
  decides.
- `__sinit_ai_map.cpp`: the prototype one is an 8-byte tail jump, the release one 64 bytes (the new
  static float), so no similarity was possible. Its static-init table entry decides.

What cost the most time: the twin scoring of the template instances (none wrong) and reading
0x192870. Suggestions:

- Pair the static initialisers by their entry in the init pointer table.
- For two release overloads with one prototype candidate, compare the callees' paired overloads.
