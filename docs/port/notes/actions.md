# boot-actions notes (socom-port-actions 2026-11-07, finished by socom-port-actions2 2026-11-12)

Scratch for node actions (action button: doors, switches, the laptop, climbs). Untracked.
Changed files: `mine.txt`. Edits of files other workers own: `edits/s03_sealai_rep.txt`,
`edits/s04_nodemain_rep.txt` (rep.py fence blocks, applied to my test tree only by `sync.sh`).
Everything already in the repo files is kept for reference under `edits/applied/`.

## Tools (this folder)
Copied set (dx.ps1/d.sh/dis.sh/disx.py, sym.py, xref.py, dw.py, mem.py, lay.py, stubchk.py, rep.py,
ed.py, ccm.sh, a2l.sh, g.sh/zs.sh, rdr.py). Own:
- `tree.sh` / `sync.sh [--fresh]`: ~/.cache/socom/tree-actions = HEAD + `mine.txt` files, then the
  `edits/s*` files on HEAD copies of seal_ai.cpp and node_main.cpp.
- `build.sh <build> <pad-file> <targets>`: sync, fake-pad configure, link with `hook_actions.cpp`.
- `default.sh`: the default build (no hook, no fake pad) in ~/.cache/socom/actions-default.
- `run.ps1 -Build <dir> -Name <run> -Seconds n -Shots "a,b"`: copies the ELF out of WSL and boots it
  through `tools/pcsx2-boot.ps1` (log `<run>.log`, shots `<run>-<t>.png`, helper output `<run>.run.txt`).
- `hook_actions.cpp` (test only): puts the player in front of an action node / climb wall and moves
  on with each TRIANGLE. Targets, /-separated: `n<node>:<gap>` (tries the DI poly normal, its reverse
  and the compass until an eye-height ray meets the node's action first), `b` (back to phase 0's
  stand point), `t<flag>:<pick>:<gap>` / `f...` (wall DI polys by app flags). Per-frame trace:
  anim, position, forward hit, action masks, reticule nodes, goal flags, valve, target matrix.
- Pads: `pad_b2.txt` (final run: START path, 450 CROSS, 540 TRIANGLE + walk, then TRIANGLE / CROSS
  pairs), `pad_arm.txt` (armory). In mission ~30 pad reads/s; the mission starts near read 375, but
  the wall-clock start moved between 54 s and 63 s with other emulators running: take shots every
  2 s and pick them by the log.

## Root causes
1. Doors were never offered: `CGrid::InitDescendantsDI` (0x212210, CMission::Open) was an empty
   stub. The door models' `doorhit` node is saved without the has-DI flag, so NodeGetIntersect
   stopped above `doordi` (reticule ray, and every other DI walk). Written, with
   InitDescendantsVisuals and the CWorld tail calls.
2. "Availability drops one frame after the hook's teleport" was the hook: a standing seal keeps
   `m_last_altitude` (m_get_new_altitude is cleared every still frame, seal.cpp CheckDI), so after
   TeleportTo he snapped back to the height of the place he left (57.4 -> 70.1) and the camera ray
   passed over the switch. The ELF's test is CheckDIShoot's ray + GetReticuleAction's x/z range
   only; nothing wrong there. The hook now refreshes the altitude hit after the teleport.
3. The action anim hung at its first command: every `ai::` task command was a stub returning
   "not done". The mission anims are loaded compiled from zanim.zar, so only Begin/Tick/End matter.
4. The door never turned: `CMatrix::SetRotate` (0x222250) was empty, `CNode::GetRotation`
   (0x227010) returned NULL without filling the vector and `CMatrix::ToEuler` did not match the ELF.
   A RELATIVE rotation ignores ROTATE_FROM in the loader (0x1b27b4), so the door starts from
   GetRotation.
5. `CSealCtrlAi::RegisterCommands` never stored ai::SELECT's command id in `ai_cmdid+8`
   (taskFindParam's key; CTSelect::Create read 0), and registered ai::WAIT with CTValve::Tick.

## Written (ELF addresses)
- First worker (in the repo since 2026-11-07): CNodeAction (Open 0x1ff140, Close, Reset,
  FindActionByValve, GetActionById, GetClosestAction, ctor/dtor, GetUIString x2, GetVUIString,
  OnAction, ExecuteAction 0x1fe850, SyncActionsMP, GetAction 0x29a6b0); CSealCtrl
  OnActionButton 0x284560, SampleActionAvailable 0x284b40, PerformProximityActions 0x284d20,
  PerformReticleActions, PerformCollisionActions, CanPerformAction, CanPlaceBomb, TickVictims
  (clearing only); CZSealBody CanTraverse 0x2a1850, CanClimbWall, CanClimbLadder,
  GetReticuleAction 0x29a540; CZKit::ItemHasAmmo(EQUIP_ITEM); CZActionBitmap / CActionTxtrMachine
  / CActionTxtr (HudTick 0x3d5870, Open 0x3d7380, Add, Render_ver_2, TickTransparencyFade...);
  C2DBitmap::TickFade fix.
- grid_di.cpp / node_world.cpp: InitDescendantsDI 0x212210, InitDescendantsVisuals 0x212110,
  CWorld's 0x22ea10 / 0x22ea00.
- seal_tasks.cpp: taskFindParam 0x2b4190; CTMove Begin 0x2b9c90 / Tick 0x2b9bd0 / End; CTDoor
  (= CTMove: Begin 0x2bdb50 tail call, Tick 0x2bda90, End); CTPlay Begin 0x2b7ae0 / Tick 0x2b7640 /
  End 0x2b7a10; CTSignal::Tick 0x2b6c50; CTSelect::Tick 0x2b74a0; CTEvent::Tick 0x2bd5e0 (see
  deviations); RegisterCommands ids. Task records TASK_MOVE / TASK_PLAY / TASK_SIGNAL are local
  structs (no DWARF; names invented).
- seal_body.cpp: SetStanceIdle 0x275da0. seal_env.cpp: FindDeathAnimTypeCQB 0x299900.
- zmath_matrix.cpp: CMatrix::SetRotate 0x222250, ToEuler 0x221e30 (rewritten from the ELF).
- zbody.h: friend CTPlay.
- Edit files (not in the repo): seal_ai.cpp CSealCtrl::SetGoalPos 0x267380, SetGoalDir 0x2671e0,
  ClearGoal 0x267470 (s03: the slide to the door; socom-port-ai's file); node_main.cpp
  CNode::GetRotation 0x227010 (s04; socom-port-decals has the file modified). s04 has to go in
  with the zmath change: without it a RELATIVE rotation starts from an unset vector.

## How an action runs (m8)
actions.rdr -> CNodeAction on the node. CheckDIShoot's camera ray keeps the nearest action node in
front of the aim hit; HudTick samples the mask (13 = node action, 2 = climb) and lists icon + text;
the action button runs ExecuteAction -> the anim with (node, valve, the seal's select task).
singleDoor: ai::MOVE (goal: 18 from the door's free edge, facing it; CSealCtrl::SlideTick slides the
player there in 0.4 s), ai::ANIMATE "Open door" (type 66, SetStanceIdle), VALVE = 1, ai::EVENT,
ai::MOVE self (step back 12.5), SOUND, OBJECT_MOTION_FROM_TO RELATIVE 0,-160,0 in 0.6 s, ai::SIGNAL.

## Results (b4.log, screenshots/16-node-actions/)
Final run: hook targets `ndoor_depot01:14/b/ncomputer_action:12/ngen_fiddle_switch:14/
nalarm_action_plate:12/t4:0:20/ndoor_depot01:14`, pad_b2.
- door_depot01: "OPEN DOOR" + door icon; button -> execute 2, valve 0 -> 1, the leaf turns 160
  degrees (node x axis -0.97,-0.26 -> 1.00,-0.09); the player walks through (x 2179 -> 2277, inside
  the depot); later "CLOSE DOOR" and the door closes (valve back to 0, matrix back).
- computer_action: hand icon + "TAKE LAPTOP"; button -> Flipswitch (284) and Get from surface
  (68) anims, valve 99, the laptop and its action node go inactive.
- gen_fiddle_switch and alarm_action_plate: "FLIP SWITCH" + lever icon; button -> anim, valve
  toggles, the action is offered again.
- Climb: walking into the flag-4 wall g23632 lists "CLIMB" (mask 0x4); button -> "climb 21.1 high:
  anim 192", the player ends on top (y 59.7 -> 82.0).
- Default build links and boots to the main menu; the armory (3D models, the only other Euler
  SetRotation user that runs) looks as before.

## ELF quirks kept
- HudTick rebuilds the list only when the mask was 0 or changed: going straight from one node
  action to another (a teleport) keeps the old icon and text.
- CTPlay: a prewait ending at exactly 0 plays again next tick; a negative anim type plays type 1.
- CTMove: SetGoalPos tolerance 3 replaced by 1 right after; SetGoalDir's replaced-position test
  compares the goal type with itself.
- FindDeathAnimTypeCQB does not NULL-test the attacker; CTSignal does not NULL-test the control.
- Those of the first worker are in the function comments (OnActionButton, CanTraverse, Open...).

## Port deviations
- CTEvent::Tick makes no AI event (CAiEvent Acquire / Create / pool are unwritten, zAI); the
  record's layout is in its comment.
- CTPlay::Tick: one anim is not drawn with rand() (the ELF's rand() % count would divide by a zero
  count; GCC traps that). The handlers' unused GetSealCtrlAi calls are left out.
- InitDescendantsDI / Visuals skip the cells' clutter nodes (CClutterList is never filled).
- SetGoalPos stays void (the ELF returns 0/1; no port caller reads it).
- PerformReticleActions offers no unit orders (14/15) and OnActionButton does not issue them:
  CSealUnit is unwritten. TickVictims only clears the victim / corpse (no CQB, restraint, knife,
  body carry). _actionValveCallback is not written (CAiMaps::GetActionById, CValve::MakeCallbacks).

## Not written / next
- Weapon and MP-bomb pickups (CSealCtrl::TickPickups, CPickup) and the CQB / restraint / knife /
  body-carry actions (CanUse*, ExecuteAction_*, TickVictims' target scan).
- The other ai:: task commands (CTGoto, CTHold, CTLookAt, CTWait...: all still return "not done",
  which hangs AI scripts), CAiEvent, CSealCtrlAi::AnimSignal / SetAiMode, CEntityList::GetEntity
  (CTSignal with a named entity would reach that empty stub).
- Ladders (CanClimbLadder is written; no ladder was tested in m8), kick_singleDoor (the action's
  second anim, used by AI / orders).
- The doorway shows grey from outside until the camera is inside (indoor region rendering, not
  part of this work).
