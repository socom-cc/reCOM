# boot-gameloop notes (2026-11-06, socom-port-gameloop)

Scratch for the game loop after mission load (CCoreState::Tick) and the first 3D frames. Untracked.

## Tools (this folder)
Copied from boot-player3 (paths fixed): dx.ps1, dis.sh/disx.py, sym.py, xref.py, dw.py, status.py,
lay.py/laycheck.sh/layall.sh, multi_replace.py, splice.py, pnm.sh, pword.sh, pdis.sh, a2l.sh, grepasm.sh
(grep patterns with `(` break through wsl.exe: use `wsl -- bash -c "grep ... /tmp/socom_full.asm"`),
fake.sh, flags.sh. New:
- `lg.sh <log> [n]`: the port trace lines of a boot log (HOOK/CORE/PIPE/GRID/STOP/exceptions).
- `hook.sh <build> <pad> <x> <z>` + `hook_spawn.cpp`: TEST HOOK, wraps CameraZoom::AttachSeal (called
  across units from CCoreState::Init; --wrap does not see same-unit calls such as Init itself) and
  moves the player node to x/z on the ground (CWorld::GetAltitude). Needed because the real start
  position comes from the AI maps (not read yet), so every character stands at the world origin.
  Configure the build dir with fake.sh first (the hook object in the linker flags breaks CMake's
  compiler check). Build `boot-gameloop-hook`, x/z 1680/2800 (the m8 grid centre).
- `edits/*.txt`: multi_replace.py edit files used.
- Builds: `boot-gameloop` (default), `boot-gameloop-fake` (pad script below), `boot-gameloop-hook`.
  Pad: `60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS`; m8 world at ~46 s, game
  frames from ~48 s at 60 fps.

## Screenshots
- `k12-61.png` (copied to build/port/screenshots/2026-11-06_214100_first-3d-frame-m8-hook.png): first
  3D game frame (hook build): m8 terrain (red/blue checker texture: wrong texture data), buildings
  and poles untextured dark grey, power lines, fog-coloured sky clear. 60 fps.
- `k11-61.png`: the frame clear in the fog colour (before the projection fix: geometry at centre).

## Boot traces in src (port-only, #ifdef SOCOM_PORT)
CORE: Init/frame 1-3 and every 300th frame (tasks done, RenderWorld counters, pipe counters
socom_port_pipe_stats), TASK: names of the first two frames' tasks, CAM: projection of the player
(frames 1-2), GRID: ordered walk (frames 1-2), WORLD: worldmodel and node read counts by type.

## Found and fixed (ELF evidence in the src comments)
- CSaveLoad::Load fetched "camera" over the CCamera node (vptr, matrix, m_parent) instead of its
  tag_CAMERA_PARAMS base (+0xc0): the AttachTo TLB miss.
- CSnd::PostTick called itself (infinite recursion; smashed the stack and the world camera).
- CMission::Tick ended the mission whenever an end valve was CLEAR (inverted).
- CWorld ctor never set m_type 6 (grid): UpdateGrid ignores children of non-grid parents.
- CWorld::AddChild had the grid insert commented out and inserted at the front; CNode::AddChild was
  not virtual, so CNode::Read(sload, world) bypassed the world's override.
- CGrid::Insert / gridAddNodeToGrids / GetNextAtom were empty TODOs; the free list init wrote 3/4
  past its end (CGridAtom** + 4*i), free-list pushes stored at the old top, InsertAtom always slot 0,
  AllocateAtomBasePtrs keyed on the wrong bits; Create's cell tolerance lacked the 0.5; Read skipped
  Create when "grid_params" is missing (the ELF always creates).
- CCell ctor left the bbox a point; DismemberWorldModel never put the world geometry in the grid.
- CNode::Read(sload, parent): "NodeType" test inverted (found = old format), and params were copied
  FROM the new node instead of TO it; CreateInstance dropped flags/region mask and type 2.
- CCamera: SetHalfHorizontalFOVRadians wrote m_scrZ from the wrong member (0 -> everything at the
  screen centre); Set{Far,Mid,Near}Clip / SetHalfVerticalFOVRadians wrong or empty; UpdateFrustum,
  find_convex_hull_xz, theta_x_z, GetLandmarkFarPlane were stubs (no frustum, no traversal).
- CAppCamera: SetZoom wrote m_Zmin/m_Zmax (ELF: m_screenAspect), ResetDeathCam/ctor wrote the
  wrong members (death camera started at once), Tick/FTSTick rough decomps; SEAL_PEEK values wrong
  (DWARF: LEFT -1, UP 0, RIGHT 1, NONE 2).
- CLight ctor cleared the wrong members; CLight::_Copy was a stub (STOP in world load).

## ELF quirks kept (listed in src comments)
CEntity::TickAll/PostTickAll call PostPreTick/PrePostTick on the first entity only; CGrid::Read
creates the default grid without the key; gridAddNodeToGrids hands out a NULL atom when the free
list is empty; theta_x_z sums in double; SetHalfVerticalFOVRadians ignores its argument;
CAppCamera::Tick decays the peek by RCNT0 seconds; CNode::Read returns NULL for instances;
CCoreState::Tick's oddeven local static.

## Next blockers
- Real spawn: CMission::LoadVehicle needs CAiMaps::GetLocation (by name) / GetCellCenter and the
  AI map read (CAiMaps::ReadMapSet 0x198680 -> CAiMap::Read 3688 B with versioned cell tables,
  CGraph::Create, name/action tables). Without it the default build looks out of the grid corner.
- Textures: terrain shows a red/blue checker, buildings untextured (texture buffers/upload path:
  CGSTexBuffer::Load, FIFO_Insert/Signal, CTexture::LoadGS are stubs or provisional).
- Characters are not drawn (the character texture-set pass after the world rings).
- Player control: CZSealBody::PreTick 0x2563e0 (1088 B) / Tick 0x255870 (2928 B) / PostTick
  0x255080 (824 B) are stubs; CSealCtrl's pad reading and movement not written.

## Mapped, not written
- AI maps (real spawn): CMission::Open -> CAiMaps::ReadMapSet 0x198680 (464 B: CFileIO header, per
  map new CAiMap 0x186e40 + CAiMap::Read 0x189390 3688 B (versioned: read_scanlines/cells/readers/
  routes/lines, ReadCellTable<names|links|spores|regions|actions> + v4/v15/v18 converters, AllocEx,
  SetCellLink, ValidateCells/Routes, CreateGraph), CGraph::Create 0x20f4b0 with node/edge fixups,
  spores table, UpdateActionTables 0x199010, UpdateNameTables 0x198d10 (764 B), ValidateLinks,
  CAiMaps::CreateGraph). LoadVehicle then needs CAiMaps::GetLocation(name) 0x19c8e0 ->
  CAiMap::GetLocation 0x19f0d0, GetCellCenter 0x19bc60 (864 B), CAiMap::GetDirQuat 0x187bd0. All stubs.
- Player control: CZSealBody::PreTick/Tick/PostTick call ~50 unwritten seal functions (UpdateStance,
  UpdatePeek, WeaponsTick, CheckDIFwd1, PostCheckDIDown, SealGetAltitude, SealAnim, Tick_0,
  DoWallStop, BlendOverlayPreTick, CZKit::Tick ...). The pad is read by CSealCtrl::PreTick 0x285af0
  (3676 B) -> ThrottlesPreTick 0x286950 (1560 B), via the controller's PreTick/Tick/PostTick
  (vtable +0xc/+0x10/+0x3c); none written.
- HUD: PreDITick/PostDITick forward to CLensFlareSaturate (stubs); StatusLine/Tick/DrawPhase/
  MapCompass::Draw/m_pausetest.Draw stubs or provisional; CHUD has no m_FlashFXVector
  (CFlashFXVector is declared after CHUD in hud.h), so its Tick/Draw are not called.
- AI tasks (ai_pre_tick, ai_direg_tick, ai_post_tick, CAiEventTick, ai_route_planner) return false
  without their bodies (flagged port: stub).
