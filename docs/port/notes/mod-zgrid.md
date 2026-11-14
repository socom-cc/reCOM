# boot-mod-zgrid notes (2026-11-13, socom-port-mod-zgrid): completing the zGrid module

Scratch `build/port/boot-mod-zgrid/` (untracked). Changed files: `mine.txt` (`src/gamez/zGrid/*`, small
in-place edits in zMath / zVisual / zNode listed below, and this note); shared-file edits (zSeal, zFTS):
`shared.txt` + `edits/`.

## State
- DONE. `survey.py gamez/zGrid`: 0 stubs (32.2 KB written; 27 stubs / 9.2 KB at the start). No
  `port: stub` / `port: not written` placeholders are left in the module.
- What was missing was the whole clutter system (trees, bushes, debris placed per grid cell from the
  mission's `clutter.zar`). Root cause: the port's `CSaveLoad::Load` never called `CGrid::ReadClutter`
  (0x22a8b0), so no clutter was read, no clutter manager made, and the cell clutter lists stayed empty;
  every clutter function and the DI clutter walks were unwritten or skipped.
- m8 `clutter.zar`: 365 clutter in 198 cells (90 animated grass in 14 cells, 169 far-fading, 90
  near-fading, none region-gated); 40-80 drawn per frame; the 30 seals register as effectors.
- Runs (`hook_zgrid.cpp` in the scratch folder: census after ReadClutter, per-150-frame clutter stats,
  -DZG_CAM test camera, -DZG_BEND test effector), all with the edit files:
  - zg3 (fake pad: START, CROSS movie, X cameras, a short walk, shots at the ground; bend test), HEAD
    bc3a59a + mine: mission 67-240 s, no STOP, heap 22.09 -> 22.18 MB (22.165 -> 22.176 over the last
    90 s). A test effector swept across alaska4d_grass02 (max force 0.294): anims 0 -> 3, bend
    quaternion z to -0.103, the force decays, the anims are deleted ~5 s later (anims 0), the effector
    unregisters (31 -> 30). Shots hit the ground (AIM), blood drips, OutPatrol4 killed by the team.
  - zg1 (walk into the valley, shooting): trees and grass drawn, collision / shooting / blood / AI paths
    as before; the player was shot dead at 188 s -> ReOpen_Unload1 ClearEffectors (30) /
    ClearAnimations fine.
  - zg2b (`exit` hook, -DSOCOM_HOOK_PAUSE_AT=1500, HEAD bc3a59a + mine): abort -> debrief X replay ->
    pause REPLAY -> abort ->
    TRIANGLE -> menus (world torn down: ~CGrid deletes the manager) -> PLAY GAME -> ReadClutter again
    (365, new manager) -> mission 4 ran 190 s; heap 22.36 MB at the end, no STOP.
  - zg4 (`win` hook, HEAD 920f54c + mine): the scripted playthrough to MISSION SUCCESSFUL (doors, C4
    crates, restraint, escort, extraction), same objectives as the zFTS reference run (3/5, 7/8).
  - zgdef (default.sh, HEAD 920f54c + mine, no hooks / pad): dlgMenu at 15.7 s (main menu), attract
    loop at 42 s.
  - Screenshots (untracked): build/port/screenshots/41-zgrid/.

## Written (ELF addresses)
- grid_clutter.cpp: CClutterList Add 0x219340 (non-fading first, repel / far-fade summary), Render 0x2190c0,
  Free 0x219040; CClutter ctor 0x218f50, Read 0x218ec0, GetTranslate 0x218ea0, GetMatrix 0x218df0, Render
  0x218a10 (region, near / far fade opacity, added colour, light scale, RenderMesh / RenderNode);
  CClutterAnim dtor 0x218980, TickForce 0x218600; CClutterAnimManager ctor 0x218560 (scheduler task
  "CClutterAnimManager" 0.95), dtor 0x218300, ClearAnimations 0x2181c0, ClearEffectors 0x218110, TestCellMid
  0x217f50, ClutterTick 0x217ba0, l_Tick 0x217840, Tick 0x217810, RegisterEffector 0x217730,
  UnRegisterEffector 0x217680.
- grid_cell.cpp: CCell GetMidPoint 0x217010, RenderClutter 0x2170d0, AddClutter 0x2170e0, DeleteClutter
  0x2170f0, UpdateBBox 0x217300.
- grid_main.cpp: CGrid ReadClutter 0x214940 (clutter.zar version 4, "Clutter" / model / clutter keys),
  AddClutter 0x214ed0 (returns bool), DeleteClutter 0x214e30.
- grid_di.cpp: the cell clutter walks in GetAltitude 0x2143b0, GetIntersect 0x2141f0, GetIntersectBatch
  0x213830 (each clutter's matrix pushed, its model node tested) and InitDescendantsDI 0x212210 /
  InitDescendantsVisuals 0x212110 (were "port: not written").
- Layouts (headers): CClutter (112 bytes, not in DWARF; bytes 0-0x5f are the archive's "params": matrix or
  quaternion form, fade ranges, flag bits, colour), CClutterAnim (36), tag_CLUTTER_EFFECTOR (40, invented
  name), CClutterAnimManager (DWARF 112), CClutterList (DWARF: vector + m_ContainsRepelClutter +
  m_max_farFadeSq; was a std::list). CGrid now derives publicly from tag_GRID_PARAMS (m_CellDim).
- Callees outside the module, written in place (files clean at HEAD): CQuat::MakeYXZRot 0x2215b0 and
  SlerpFaster 0x220a20 (zMath/zmath_main.cpp; MakeYXZRot is also called by fts_remote, zwep_projectile and
  seal_env, which got an empty quaternion before), ColConvTo3D 0x310460 (zVisual/vis_bands.cpp, now returns
  CPnt3D; declared in zvis.h), CNode::SetApplyClutterFlag 0x225690 and SetApplyMultipassEffects 0x225850
  (zNode/node_main.cpp), and the ReadClutter call in CSaveLoad::Load (zNode/node_saveload.cpp).

## Edit files for other modules' files (scratch `edits/`, listed in `shared.txt`)
- `edits/s_seal.txt` (zSeal/seal.cpp, ~CZSealBody) and `edits/s_mission.txt` (zFTS/fts_mission.cpp,
  CMission::ReOpen_Unload1): the "port never makes the clutter manager" NULL guards removed (the ELF calls
  UnRegisterEffector / ClearEffectors / ClearAnimations on the grid's manager directly; ReadClutter now
  always makes it for a mission world).

## ELF quirks kept
- CClutterList::Render returns at the first fading clutter of an out-of-range cell without restoring
  CVisual::m_applyLocalLights (RenderWorld sets it again each frame).
- ClutterTick stores NULL as the anim's node right after a dynamic_cast<CModel*> of the clutter node it
  discards, so the anim's node (and its delete in the dtor) is never used.
- The anim wobble is stored 0 at every push and only ever negated or damped, so it stays 0: the bend angle
  is the force (and 0 at force 0).
- ReadClutter makes the clutter manager before opening the archive (a mission without clutter.zar still
  gets one and its scheduler task); m_ClutterCreated is set whenever the archive opened, also with a wrong
  version or no "Clutter" key.
- AddClutter clamps the cell index twice; ReadClutter's path buffer is 64 bytes.

## Port deviations
- ~CGrid deletes the clutter manager before Destroy (the ELF order: Destroy deletes the cells and their
  clutter first, then the anims' destructors reset the freed clutter's bend - a write into freed memory).
- CGrid::DeleteClutter skips a grid slot whose first atom is not a cell (the ELF calls
  CCell::DeleteClutter on it unchecked; the cells always come first).
- CClutterList::Add appends with push_back (the ELF reserves 10 more when full).
- CQuat::SlerpFaster is void (the ELF returns 1 / 0; no caller reads it).

## Not written / next
- Nothing in the module. CSaveLoad::Load still skips the LOD / material / scrolling-texture object reads
  between CWorld::Read and the clutter (0x22a618-0x22a884; zNode, not this task).
- Written, untested: ReadClutter's root-folder and "mp" paths (multiplayer), the near-fade and region
  branches if m8 has none (census below), the effector velocity estimate (seals pass their own velocity).

## Tools / test
- `build/port/boot-mod-zgrid/hook_zgrid.cpp` (scratch, not tracked): wraps CGrid::ReadClutter,
  CCell::RenderClutter, the manager's ClearEffectors / ClearAnimations; links next to the `exit` and
  `win` hooks (no CheckDIShoot wrap without -DZG_CAM).
- `survey.py gamez/zGrid`, `ctree.py`, `xref.py`, `dx.ps1` for the ELF.

## Survey at the start (HEAD 3f054bb6; `survey.py gamez/zGrid`): 27 stubs, 9224 B
Nothing was reached: CSaveLoad::Load did not call ReadClutter. m8 has /RUN/SP/M8/CLUTTER.ZAR (59 KB).
- Load: CGrid ReadClutter (1032) / AddClutter (588) / DeleteClutter (160), CCell AddClutter / DeleteClutter
  (8 each), CClutter ctor (236) / Read (140) / GetTranslate (32), CClutterList::Add (~408); outside:
  CNode::SetApplyClutterFlag (436), SetApplyMultipassEffects (436).
- Render (CPipe::RenderWorld -> CCell::RenderClutter): CCell RenderClutter (8) / GetMidPoint (184),
  CClutterList::Render (628), CClutter Render (968) / GetMatrix (176), manager TestCellMid (444) /
  ClutterTick (940), CClutterAnim::TickForce (896); outside: ColConvTo3D (252), CQuat MakeYXZRot (256) /
  SlerpFaster (576).
- Tick / effectors: manager ctor (148) / dtor (596) / Tick (40) / l_Tick (852) / RegisterEffector (220,
  PostCreateSeal) / UnRegisterEffector (176, ~CZSealBody) / ClearEffectors (172) / ClearAnimations (308)
  (ReOpen_Unload1), CClutterAnim dtor (144).
- CCell::UpdateBBox (120, virtual). DI placeholders: the clutter walks of GetAltitude, GetIntersect,
  GetIntersectBatch, InitDescendantsDI / Visuals.
