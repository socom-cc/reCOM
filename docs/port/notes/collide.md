# boot-collide notes (2026-11-07, socom-port-collide)

Scratch for world collision (grid/DI intersect, the seal's probe chords) and the aim point
(CheckDIShoot). Untracked.

## Result
- w3.log (hook build, m8 grid centre, `alaska4d_depot` house): the player runs into the house wall
  head-on and stops 5 units in front of it (4 chord hits, move 1.04 0.28 -> 0 0) while the run anim
  keeps playing; a diagonal stick slides him along the wall; steep terrain (worldchild_*) stops him
  too. Aim point valid every camera tick (AIM trace: solid hit on the wall / terrain / pole, norm 1).
  UP/DOWN toggle into first person and back re-aims from the aim point (no guards now).
- w1.log: same at the map-edge fence (fence_20) from the real spawn.
- d1.log: default build (no hooks) boots to the main menu.
- Screenshots: build/port/screenshots/08-collision-aiming/2026-11-07_0500_m8-*.png (= w3-49/55/57/59).

## Tools (this folder)
Copied from boot-camera (paths now point at the repo itself, no isolated tree: I was the only
worker): dis.sh/disx.py/dx.ps1, sym.py, xref.py (text only up to 0x2f0000: misses __sinit_*),
dw.py, mem.py, fences.py, rep.py, g.sh/zs.sh, ccm.sh, fake.sh. New:
- `stubchk.py <regex>...`: skeleton fences by mangled name: stub/body, EMPTY or line count, file.
- `squash.py <decompile.c>`: condenses Ghidra output (VU0 transform loops -> XFORM, seal chord
  registrations -> CHORD, xyz copies). dec_cnp_s.c = ComputeNextPosition condensed.
- `hook.sh <build> <pad> <gap> <range> [<x> <z> [<name>]]` + `hook_wall.cpp`: TEST HOOK wrapping
  CameraZoom::AttachSeal: optional teleport to x/z, 36 level rays (CWorld::GetIntersect) traced,
  then the player <gap> in front of the nearest wall (node name containing <name>), facing it
  head-on. Configure with fake.sh first; hook.sh deletes the ELF to force the relink.
- `fixnl.py`: repairs inline-asm literals whose \n\t became real newlines (heredoc via the Bash
  tool unescapes backslashes: write edit files with the Write tool, never heredocs, when they hold
  backslashes). `edits/c*.txt`: ed.py edit files used (c01..c10).
- Builds: boot-collide-default, boot-collide-w1 (spawn), boot-collide-w2 (grid centre, depot).
  Pad: `60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS,380:LY=0+150,560:UP,
  620:DOWN,650:LY=0+120,650:LX=255+120,790:LY=0+120,840:CROSS`; hook `90 800 1680 2800 depot`.
  Screenshot time ~= emulator log time + 1..2 s.

## VU0 facts used
- CDIPoly::GetIntersect: slot 2 vu0IntersectPlaneTest (vf3 normal w=ptcount, vf4 last pt, vf5 first
  pt, VU0 qwords 0/1 = tip/tail+backface mask) -> vf29 (hit, w 1/0); slot 4 per edge (vf4 = vf5,
  vf5 next pt); vf3 written back each pass (negated on a back-face hit; vi02 persists, so it flips
  every passing edge: ELF behaviour). vf29.w of the previous call is the tip-side threshold.
- CBBox/CDIBBox: slot 8, vf3 min, vf4 max (w = cull mask 0/224) -> vf10 (w += 1 on hit), vf30.
  vf10.w is only reset by Vu0MatrixInverseWithUniformScale (vmuly.w by vf0.y): kept on VU0.
- All VU0 data goes through 16-aligned locals (GCC aligns neither CMatrix nor the heap records).

## Not written / next
- OKToJump 0x274250 (416 B) is writable now (CWorld::GetIntersect); still returns false.
- Climbing: ImpactFront dispatches by DI app flags 1..5 into Climb/ClimbLadder(Down) (nonvoid
  stubs: STOP), ClimbOver/PlaceLaterally/AlignForClimb (void stubs). Normal walls (flags 0) return
  -99 with no climb. Untested in a boot (the CROSS press did not reach CheckDIFwd1).
- Character DIs: AddDIPolys 0x27dd50 / SetDIBBox 0x22c420 need CNode::UpdateBBox 0x2297f0 (nonvoid
  stub); without them characters have no DI: not hit by shots/aim, no auto aim (GetCharacterHit
  loops over zero bbox hits), DrawAutoReticle never runs (Draw2DLine is an empty stub anyway).
- ClipCameraChord 0x1ebbb0 (2480 B, camera vs walls; GetNearestIntersectCamPoint 0x1ec580).
- Clutter (CClutterList never filled) is skipped by GetIntersect/GetIntersectBatch as in GetAltitude.
- With a weapon: CanAttainAim 0x2befc0, CurWeaponIsM203Mode 0x2a7b50, Crouch 0x276530 (nonvoid
  stubs on UpdateAimDir's weapon path); CNodeAction::GetAction is a loop lambda in CheckDIShoot.
