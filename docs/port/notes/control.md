# boot-control notes (2026-11-07, socom-port-control)

Scratch for the player's control path: pad -> CSealCtrl throttles -> CZSealBody ticks (anim, motion,
ground) -> node. Untracked.

## Result
Player-only hook build (b5.log): the player stands in the idle stand anim (no T-pose), runs forward
with the run anims (velM.z -64), follows the terrain height, turns in place (Step anim, velR 2.27),
strafes, runs while turning; the app camera follows. Screenshots: build/port/screenshots/
2026-11-07_0056_m8-player-{idle-stand-anim,running-forward,turning-in-place,running-after-turn}.png.

## Tools (this folder)
Copied from boot-spawn (paths fixed): dx.ps1, dis.sh/disx.py, sym.py, xref.py, dw.py, lay.py, laycheck.sh,
pnm.sh, pdis.sh, ctree.py (now uses fences.py), fake.sh, hookai.sh/hook_ai.cpp (REPO overridable by
SOCOM_TREE). New:
- `fences.py <regex>`: brace-matched skeleton fence scan (W/S, nonvoid flag); ctree marks nonvoid empty
  stubs `S!` (they STOP the game through -fsanitize=return).
- `mem.py <Class> <off>...`: DWARF member at a byte offset (bases flattened, bitfields).
- `rep.py <defs>`: replace whole function definitions by fence name (`=== <mangled>` blocks; inner
  static-local fences must reappear). `edits/ed.py`: old/new block edits. `edits/d*.txt`, `e*.txt`: the
  edit files used.
- `g.sh '<fixed string>'`: grep the full ELF disassembly with the containing function (from Git Bash:
  `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash .../g.sh "',1232('"`).
- `ccm.sh <src files>`: syntax-only compile with the port flags.
- `tree.sh` + `tree_nw.py`: isolated source tree ~/.cache/socom/tree-control = HEAD src/ port/ (git
  archive) + my working-tree files; the unload worker's in-progress files stay at HEAD
  (node_world.cpp: HEAD + my GetAltitudes). Needed because their WIP (zsys_sched Clear/ClearFreeList,
  CMenuState::UnInit...) leaves zTaskScheduler empty in the game (b1.log: no TASK lines, no entity
  ticks). Build: `env SOCOM_TREE=~/.cache/socom/tree-control fake.sh / hookai.sh boot-control-t1 ...`.
- Boot: pcsx2-boot.ps1 only. Never pipe it into `Select-Object -First n` (stops the script; the
  watchdog then closes PCSX2 without screenshots).

## Fake pad stick terms (port/compat/libpad.c)
`<read>:<AXIS>=<0..255>[+<reads>]`, AXIS LX LY RX RY (rdata[6] [7] [4] [5]); LY=0 pushes the left stick
up. Reads run ~30/s and keep counting through the load: the game starts near read 350.
Script used: `60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS,500:LY=0+300,
830:RX=0+120,980:LY=0+150,1160:LX=255+90,1280:LY=0+150,1280:RX=0+150`.
controller.rdr Default: MoveLong/Strafe left stick, Rotate/Pitch right stick (PAD trace).

## Bugs found
- CNode::SetActive returned the new state (ELF 0x17d2b0 returns the old): SealGetAltitude's restore
  left the player node inactive -> not drawn.
- CQuat::Exp never set the vector part: no turning.

## Not written / mapped (see the src comments)
Wall collision: ComputeNextPosition's probe chords (RegIntersectDelayed) and PostComputeNextPosition's
chord response; CWorld::GetIntersect / CGrid::GetIntersect(Batch) 0x2141f0 / 0x213830 / 0x212310
(5.4 KB). OKToJump (needs GetIntersect) -> false; OKToPeek -> false; GetInterpolatedShadow -> 0.
Void stubs on the path: UpdateStance (no crouch/prone), UpdatePeek, WeaponsTick, UpdateLODFlags,
TickAimPitch, look/blink, Recoil, HandleSealStep (footsteps), CZKit::Tick, UpdateAiEvent,
CollidePlayers, HandleSliding, FootInSpace, SetWeaponState. Nonvoid stubs off the walking path:
InStateCrouch/Prone/Hang/ClimbLadder/Carrying/Carried, PostCheckDILadder, ImpactFront,
FindRandomDeathAnim, CreateMPBombPickup, TargetMods/GetSniper_DecayRate (with a weapon; the kit has
none), HandleWeaponIntersect (firing), GetCellRepelParams.
