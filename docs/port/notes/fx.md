# boot-fx notes (2026-11-07, socom-port-fx)

Scratch for effects: gunfire/impact sounds, particles, muzzle flash, footsteps, tracers, decals.
Untracked. Changed files: `mine.txt`.

## Tools (this folder)
Copied from boot-shapes (paths fixed): dx.ps1/dis.sh/disx.py, sym.py, xref.py, fences.py, ctree.py,
mem.py, rep.py, lay.py/laycheck.sh, ccm.sh, a2l.sh, pdis.sh, fake.sh. New:
- `tree.sh [--fresh]`: ~/.cache/socom/tree-fx = HEAD (git archive) + whole files of `copy.txt` +
  files shared with other workers (`shared.txt`: `<file> <edit files>`; HEAD copy + only my edits,
  srep.py or `*.rep.txt` through rep.py) so others' WIP stays out.
- `srep.py <root> <edits>`: literal old/new blocks (`@@@ file` / `@@=`); `SREP_TOUCH=1` records the
  file in `<root>/.touched`.
- `diag.py <tree> <spec>`: trace statements at the start of fenced functions (test tree only).
- `stubcmd.py <tree>`: TEST ONLY, refuses roots outside ~/.cache: empty non-void command tick
  stubs get a trace + `return 1` (lists the unwritten commands mission anims reach).
- `bd.sh <build> <pad-file> [spec|-] [test edits...]` (env STUBCMD=1): restore touched files from
  HEAD, tree.sh, diag, test edits, fake-pad build in ~/.cache/socom/<build>.
- Edit files: `edits/*.txt` (=== blocks for rep.py, @@@ blocks for srep.py; t_*.txt = test traces).
- Pads: `pad_d1.txt` (= boot-weapons pad_f10: menu, turn, L3 x2, R1 bursts, R3, aim up, L2/L1),
  `pad_e2.txt` (+ 975:LY=0+180 run forward).

## Root cause: fire/impact anims never reached SOUND
`CMission::OnMissionStart` (0x1f4618) starts the "common" and "mission" anim sets; the port had
`common = NULL // ZAnim.GetAnimSet("common")`, so `CZAnim::Activate` returned NULL at once (set not
m_IsStarted) for every weapon/impact anim (d1.log: Activate traced, no Tick). Fixed (committed in
f53995a with the HUD/deathcam work). Then (d4/d5): muzzle_m4SD runs CALL_ANIMATION x4 + SOUND 0x82;
the SOUND ticks; PlaySound3D one-shots go to 989snd: gunfire bank 6 (m8_efx) sound 22 vol 926,
SND_BULLET_SNOW bank 7 sound 26 vol ~500 (d7.log PS3D trace).
Starting the sets also starts every on-start mission anim (objectives, mission cam, ambient fire/
generator/wind sounds, snow, alarm switch...): needed HUDTriggerMissionCamTick, CftsPlayer
IsPlayerNode/Controls/IndoorsTest (they STOPped), UIPlayMPEG (other worker), CAMERA_INDOORS.

## Written (ELF addresses)
- Anim arguments: ActivateArgV 0x1ce750 (8-byte slots; n32 GCC va_list is the slot pointer),
  ActivateArg 0x1ce6d0, arg ctors/Copy (0x1ce370..0x1ce630), GetPnt3D 0x1ce250, GetCmd/GetValve,
  GetNode 0xfa node argument, re-root helper (0x1ce8c0); zAnimCallAnimBegin args 0x1b8380; SOUND
  flag 8; OBJECT_TRANSLATE_STATE flag 2; OBJECT_MOTION_FROM_TO from/to arguments; terminators added
  to CZKit::Fire (0x2adc24) and HandleImpact (0x3184ec, + node arg 3) ActivateArg calls.
- Conditions/flow: FAIL, RANDOM_WEIGHT, LOD_TEST, HEALTH_TEST (+GetHealth 0x1cf5a0), RANGE_TEST,
  NODE_RENDERED, NODE_ACTIVE, BREAK, END_WHILE, STOP_SEQUENCE (+CZAnimMain::StopSequence 0x1c3890),
  OBJECT_ROTATE_STATE 0x1bd1f0.
- CZAnim: GetParticleSource 0x1ca780, GetTexture 0x1ca620, Stop/DeleteParticleSources, Running
  (particles), CreateInstanceNode xref path 0x1caca0 (+ auto-add flag), world add/remove helpers
  (Activate 0x1cf1e0 / stop paths), Copy 0x1c8fd0 + GetAvailable copies 0x1ccc30, State(2) fix.
- Particles: zAnimParticleSourceTick 0x1bee80; Props Create/Branch/DecRefCount/GetTexture/
  GetColor/GetScale/GetOpacity; Source ctor (no box DI node)/dtor/Create/Default/SetActive/Reset/
  setters/CheckExtents/Tick 0x239480/List::Uninit; Instance ctor/dtor/Expire/Tick (inline in
  zparticle.h, 0x237380)/Render 0x236a90/List::Tick/Uninit; Particle Init/Open/Close/Tick/Render/
  AddDynTexture/FlushDynTexList/Reserve/FreeNodePool/GetFreeInstance/ReleaseInstance;
  BufferElement::Draw 0x234850 (GS sprite packet). compat: sceVu0RotTransPers, sceVu0FTOI0Vector.
- Footsteps: HandleSealStep 0x291b60, HandleFootfallSound 0x2920c0, Init/ReInitDatabaseHandles
  0x293900/0x2936e0, InitDecalHandles 0x293910 (footstep part), GetVisualNode/GetDecalNode.
- Fixes: CPnt3D::Reflect returns by value (0x222b10), CNode::CreateXRef(model) missing return,
  CAMERA_INDOORS (0x1e73f0, was always true -> snow off).

## Results
- p1/g3: impact puffs on snow and on the enemy (white sprites at the hit), snow falling particles,
  muzzle flash model (muzzle_flash_hider:zanim_instance) at the muzzle; tracers acquired every 4th
  round (f3.log FLYOUT) - too short-lived to catch so far.
- e2: footfalls every ~0.3 s running, material SNOW: step sound found and played 3D; no
  seal_footfall_SNOW anim in m8; footprint texture found, ApplyDecal is a stub.

## Not written / next
- Decals (bullet holes, footprints): CNode::ApplyDecal 0x2253a0, CVisual::ApplyDecalRender,
  CDecal::AddDecal + pools, CZMarkList Init/ReadDecalNames/AddNewMark, the decal VU batch.
- DrawRotated/DrawXZ/DrawStreaked (m8 effects seen use the standard draw), Source::GetBBox,
  the box DI node, Destruction_Instance/DestructionManager, CZAnim copy_instance path, LIGHT,
  OBJECT_MOTION (shell ejection), CAMERA, TIMER/MESSAGE/DESTRUCTOR ticks.
- CMission::Close is a stub: Particle::Close (task "ParticleTick", sources) is not called on
  mission exit.
