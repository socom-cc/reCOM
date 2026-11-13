# boot-jump notes (2026-11-07, socom-port-jump)

Scratch for jumping, landing / fall damage and the climb chain (ImpactFront's callees). Untracked.

## Facts (j1.log)
- controller.rdr "Default" buttons (PAD: buttons trace, PAD_BUTTON values): Action 9 = X, Jump 8 =
  SQUARE (not shared with Action), Fire 10 R1, Inventory 11 R2, Swap1 12 L1, Swap2 13 L2, Reload 14
  (R3 slot), FireMode 15 (L3 slot), TeamCmd 7 CIRCLE, AimMode/StrafeL/StrafeR none.
- m8 DI census (hook_jump.cpp, 3162 nodes / 10340 DIs): app flags 0: 10008, 4: 202 (step / climb
  walls: g23632, g23646, climbwall02 ...), 5: 130 (alaska4d_fence01: climb over). No 1, 2 (ladders)
  or 3 polys: ImpactFront's ladder / hang-climb cases are unreachable in m8; Climb(28..32) can still
  hang (flag 4).
- Player path to a climb (ELF): the jump button at a wall only clears the pending jump
  (CheckDIFwd1 with a forward hit). Climbs come from the action button: CZActionBitmap::HudTick
  0x3d5870 -> CSealCtrl::SampleActionAvailable 0x284b40 -> CanClimbWall 0x28c100 -> CanTraverse
  0x2a1850 (flags 3/4/1/5; a 5..10 step (flag 4) is climbed right there through ImpactFront) set
  the available mask bit 2; the HUD's action list (CActionTxtrMachine::Open) selects it; X release
  -> OnActionButton 0x284560 bit 2: ExecuteDelayedAction_Climb + m_action -> next Tick
  CheckDIFwd1 -> ImpactFront. HudTick, Open, SampleActionAvailable, CanTraverse, OnActionButton
  are unwritten (HUD files are not mine).

## Tools (this folder)
Copied from boot-collide (paths fixed). tree.sh: ~/.cache/socom/tree-jump = HEAD src/ port/ + the
files in mine.txt (the camclip worker's WIP stays at HEAD). fake.sh / ccm.sh / hook.sh default to
that tree. New:
- `hook.sh <build> <pad> [<flag> <pick> <gap> [climb]]` + `hook_jump.cpp`: AttachSeal wrap: DI
  app-flag census (nearest 8 per flag); with flag: the player <gap> in front of that poly, facing
  it. `climb`: also wraps CZSealBody::DoWallStop (X release at a forward hit = the HUD-selected
  climb: ExecuteDelayedAction_Climb + m_action, as OnActionButton does) and
  GetTerrainMotionFactor (per-frame player anim / pos / air trace).
- `animenum.py <value|name>`: AnimType enumerator values (counts `animtypeCrouch2PeekU`).
- `bitrd.sh <off>`: bitfield readers of a byte offset in the full ELF disassembly.
- `edits/j0*.txt`: rep.py definition files used.

## Result (j5.log, hook build: census + flag-4 wall g23632 300 in front + climb trigger)
- SQUARE jumps. Standing (speed < 15): the in-place Jump anim (184) plays (~1 s, no impulse, node
  stays). Running: JumpLaunch (8), impulse -79.9 (jump factor 0.85, gravity 235: ~13 high,
  ~0.7 s), lands (HandleLanding: impact 53..81, damage 0, JumpLand pushed, the run goes on).
  Landings are ignored for the mission's first 10 s (m_wait_before_falling, ELF).
- SQUARE at a wall does nothing (ELF: CheckDIFwd1 clears the pending jump at a forward hit).
- X release at the flag-4 wall (hook = HUD-selected climb): ImpactFront facing 1.00, Climb 19.8
  -> blended crate/medium climb (192), AlignForClimb homing, HomingTick lifts the body 60.9 ->
  81.0 over ~1.3 s, pops to stand on top, then runs on. No STOP.
- Player m_interpolate_animations = 1 every frame (UpdateLODFlags).
- d1.log: default build (tree-jump = HEAD + mine.txt, no hooks) boots to the main menu.
- Screenshots: build/port/screenshots/10-jumping/2026-11-07_1316_m8-*.png (= j5-64/65/66/68/69).

## Engine bugs fixed
- zrdr_tobool (zReader): an array value read its count element (array[0]) instead of array[1],
  so every `looped (...)` / vehicle bool read true; integers returned false. Made every anim
  looped: JumpLaunch froze mid-air, the in-place jump and the climb anims were replaced by the
  stand logic the next frame (looped blends inherit the old top's time).

## Not written / next
- Player climb trigger: CZActionBitmap::HudTick 0x3d5870 (HUD) + CActionTxtrMachine::Open
  0x3d7380 select the action; CSealCtrl::SampleActionAvailable 0x284b40, CanTraverse 0x2a1850
  (auto step-up 5..10 via ImpactFront), OnActionButton 0x284560 (1500 B dispatcher: pickups,
  knife, restraints, satchel/MP bomb, team commands; CNodeAction m_type/m_valve are private and
  the layout is unsure). Without them X does nothing (OnActionButton stub).
- Ladders (flag 2, none in m8): InStateClimbLadder, PostCheckDILadder, CheckDILadder,
  PreClimbLadderDown, SlideLadderDown are still nonvoid stubs (unreachable in m8).
- UpdateHealth 0x294210 (void stub): fall damage 2/3 sets the part health but nobody dies.
- Hang_0 (SetStance only), CanClimbWall/CanTraverse (HUD path) unwritten.
