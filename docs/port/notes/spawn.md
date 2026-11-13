# boot-spawn notes (2026-11-06, socom-port-spawn)

Scratch for the real spawn (AI map read) and the player-control mapping. Untracked.

## Tools (this folder)
Copied from boot-gameloop (paths fixed): dx.ps1, dis.sh/disx.py, sym.py, xref.py, dw.py, lay.py/laycheck.sh/
layall.sh, pnm.sh, pword.sh, pdis.sh, a2l.sh, grepasm.sh, fake.sh, flags.sh, lg.sh. New:
- `edits/ed.py <file>`: apply an edit file (`@@@ FILE path`, `<<<` old `===` new `>>>`; each old must match
  once; keeps LF/CRLF). Write edit files with the Write tool (bash heredocs with quotes break).
- `iso.py <path> [-ls | off n]`, `iso_lib.py`: read-only look into the user's disc image (env SOCOM_DISC, raw
  2352-byte sectors). Never writes disc data. `mps.py [mission]`: parses AIMAPS.MPS exactly as the reader asm
  does (v19), prints counts / names. Only /RUN/SP/M8 is on this disc (demo): file header 2, 4 maps, all
  version 19, graph (1, 208 B, 8 nodes, 10 edges), 0 set spores, parse ends exactly at EOF.
- `cc.sh <cpp>` / `ccs.sh <cpp>`: syntax-only / to-assembly compile of a scratch unit with the port flags
  (lay/bits.cpp: bitfield setters -> masks; all AI map bitfields match DWARF bit positions).
- `hookai.sh <build> <pad> <ai>` + `hook_ai.cpp`: TEST HOOK, wraps CMission::Open (database.cpp, cross-unit)
  and passes `ai` (0 = the mission's own player-only load). `PROF=1 hookai.sh ...` adds a live-heap profiler
  (malloc & co. wrapped, 16-byte headers, sites by _malloc file:line or operator-new return pc; dump before /
  after CMission::Open). The profiler's headers cost ~1.6 MB: use it only to profile.
- `ctree.py <addr> [depth]`: ELF direct-call tree with port status per callee (W written, S empty stub,
  ? no fence). `ctree_sealctrl_pretick.txt`: CSealCtrl::PreTick depth 2.
- Builds: `boot-spawn` (default), `boot-spawn-fake` (pad script below), `boot-spawn-hook` (fake + hook_ai 0).
  Pad: `60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS`.

## Written (all from the asm; see the src comments)
- AI map set read: CAiMaps::ReadMapSet 0x198680, GetMapByIndex 0x19d3c0, GetCell 0x19bfc0, GetCellCenter
  0x19bc60, UpdateActionTables 0x199010, UpdateNameTables 0x198d10, ValidateLinks 0x198420, CreateGraph
  0x1981a0 (keep-the-read-graph path), _fixupNode 0x198870, _fixupEdge 0x198850, scanline::GetCell 0x197660.
- CAiMap: ctor 0x186e40, Read 0x189390 (v19 + the version fixups), read_cells 0x188f60 (v>=17),
  read_scanlines 0x188e90, read_lines 0x18a3c0, read_readers 0x18a200, read_routes 0x18a2d0,
  ReadCellTable<> (0x18a4a0..0x18a890), AllocEx 0x19f390, GetLocation(name) 0x19f0d0, GetCellName 0x19f1c0,
  GetCellAction 0x19f030, GetCellLink 0x19ebd0, SetCellLink 0x19ec60, ValidateCells 0x186430,
  _validate_cell 0x186a30, ValidateRoutes 0x19e0a0, CreateGraph 0x19dce0, GetDirVec 0x187d90, GetDirQuat
  0x187bd0, dummy_cell 0x187e90, CAiMapLoc(x,y,id) 0x1863c0, name::ValidateName 0x19f260, names::SortByNames
  0x19f190 (+CompareT 0x19f4a0), reader ctor 0x19e670, SetReader 0x19e570, _invalid_route 0x19e300,
  CAiMapLocVec::ComputeLength 0x19dea0, FindByLocation/FindIteratorByLocation templates.
- zGraph: CGraph ctor/Create(name)/Create(io)/Read/Destroy/CreateNode/CreateEdge/GetNodeByIndex/
  GetNodeByNodeEx, CGNode ctor/dtor/SetName/FindEdge, CGEdge ctor/dtor/Delete (layouts from the ctors).
- CRdrFile::ReadPacked 0x23c040 (the map's packed readers).

## Results
- Plain fake-pad build (s1-s3.log): maps read (4 maps, graph), every character gets its real start (player
  startPlayer 2250 36 4728; LOAD trace prints start name + position), then the load HANGS creating
  vehicle 18 of 41 (Snow2): out of heap (in-use 29.1 MB of 29.2; the AI maps add 0.9 MB, ~67 KB per
  character). Owned now by socom-port-unload (CMenuState/CLoadState::UnInit empty).
- Heap profile before CMission::Open (h1.log, profiler build): zar_main.cpp:394 (non-streamed ZAR data
  buffers, CZAR::ReadDirectory) 16.2 MB in 28 blocks; operator new @pc 2.0 MB/75 blocks;
  zrdr_file.cpp:450 1.45 MB/10; main.cpp:76 0.8 MB/2 (pools); int_main.cpp:91 0.5 MB/9994; grid 0.5 MB.
  The original's static image ends at 0x5e7f04, the port's at 0x40ca54: the port has ~2 MB more heap
  than the ELF and still runs out -> the front end the ELF frees in CMenuState::UnInit 0x378cd0.
- Player-only hook (h3.log, h3-54.png -> build/port/screenshots/2026-11-06_223700_m8-real-spawn-player-only-hook.png):
  load completes, game loop 60 fps, eye 2272 58 4745 behind the player at startPlayer; textured snow
  terrain, fog, building at right; the player stands in a T-pose (body ticks not written).

## ELF quirks kept
ReadMapSet leaks a map that fails Read; CGraph::Read and CAiMap::CreateGraph use CreateEdge's result
without a NULL test; CGNode ctor ignores its name; SetCellLink does not test the cell; GetCellCenter does
not test the action of an action cell; ValidateCells walks the action table with an empty body; Read's
version < 12 / < 15 / < 17 fixups kept (dead for v19).

## Port deviations / not written
- CAiMap::Read versions 2-18 (52/84/88-byte headers, actions_v15/v18 and regions_v4 converters) and the old
  read_cells formats: trace + false. Disc has v19 only.
- CAiMaps::CreateGraph rebuild (ai::PathPlanImmediate 0x180ae0, CAiPath) and CAiMap::ReRoute 0x19e320: trace /
  empty; unreached with the disc data.
- ftsFixupAiMap 0x1f47d0 still a stub (FreeEx for mapex != 4, pickups from the map readers "PICKUP").
- CGraph::Destroy deletes through ~CGraph (stub) where the ELF frees inline.

## Player control: mapped, not written (callee-first order)
Entities tick through CEntity::PreTickAll/TickAll/PostTickAll -> vtable +16/... -> CZSealBody::PreTick
0x2563e0 (1088), Tick 0x255870 (2928), PostTick 0x255080 (824). Direct callees of these + CSealCtrl::PreTick
0x285af0 (3676): 85 empty stubs, 17 written (ctree.py). The pad: CSealCtrl::PreTick -> ThrottlesPreTick
0x286950 (1560, stub; statics pitch/yawSpeedControl, use_piecewise, fangle) via the controller vtable +0xc.
Motion is animation-driven: Tick -> CheckAnim 0x277300 (1644) -> SealAnim 0x27b4d0 (1160) ->
CZBodyAnimBlend::Propagate 0x1e0420 (504) / BlendOverlayPreTick 0x26fe50 (376); collision/altitude
CheckDIFwd1 0x2a1bb0 (1684), PostCheckDIDown 0x29eb00 (4768), SealGetAltitude 0x2a2250 (288),
GetTerrainMotionFactor 0x2a2a80 (492); Tick_0 0x26ffd0 (3308); PostTick -> PostComputeNextPosition 0x24fc10
(3696, the position integration) -> SetMatrix/SetPosition; then Post 0x26c930, CZKit::Tick 0x2a9c20 (1384),
HandleSealStep 0x291b60 (1376). PreTick: UpdateLODFlags 0x256820 (1120), UpdateStance 0x256c80 (516),
UpdatePeek 0x273020 (1124), WeaponsTick 0x2c02c0 (452), CanTurn, TickRumbler.
Suggested order: ThrottlesPreTick (+ its CPad getters), CSealCtrl::PreTick's movement part, SealAnim/CheckAnim
with GetSpeedState/IsCurrentBlend/CanInterrupt, Propagate, PostComputeNextPosition, SealGetAltitude, then the
DI checks. Fake pad: port/compat/libpad.c holds sticks at 0x80 (rdata[4..7]); a stick term (e.g.
`300:LY=00x60` = left stick up for 60 reads) is needed for a scripted move.
