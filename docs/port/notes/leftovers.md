# boot-leftovers notes (2026-11-12, socom-port-leftovers)

Scratch for finishing body carry (a), leaving a mission from the pause menu + replay (b), ladders (c),
CQB attack (d). Untracked. Changed files: `mine.txt` (= copy.txt, whole files laid over HEAD by tree.sh).
All edit files were applied to the repo once their files came back clean (12c30bd): edits/applied/.

## State / next step
- DONE. HEAD 12c30bd. a, b, d WORK; c written, untestable on this disc. Final runs: a4.log (carry, at
  2f8b0e3 + mine), d1.log (CQB), b4.log (round trip at 12c30bd + mine: same sequence as b3, heap at the
  menu 10.34 -> 10.48 -> 10.58 MB), dflt.log (default build ldef = default.sh: main menu at 15.7 s,
  attract 42 s, no fake pad / hooks). Screens: screenshots/27-leftovers/.
- Next (not done): ladder table (CMission::CreateLadderTable 0x1f5c40, CLadderList GetClosestLadder
  0x1f5a90 / GetLadderByIndex 0x1f5bf0) and the ladder part of ftsFixupAiMap; CSealCtrlAi::
  LadderClimbTick 0x266320; the pause menu selection (CZPauseTest m_curselection) is kept between opens (row 1
  after an abort: check the ELF's OpenPauseMenu/ReInit); CAiMaps::Reset 0x19d460 / CAiMap::ResetCells
  0x186080 (replay leaves the AI map cells as the last run left them); Sample_ExtractionLoc
  (stub, also in Open); stance changes (SetStance / UpdateStance stubs: TRIANGLE does nothing; after
  a put-down the player stays crouched until the stick runs him up).

## (a) body carry - WORKS (a3.log, a4.log)
- Written (seal_body.cpp): IsStopped 0x27b300 (bool), CanCrouch 0x27a1b0 (bool), InStateCrouch 0x279740,
  CrouchMoveControl 0x277970, InStateCarrying 0x278bc0, InStateCarried 0x2788b0, Crouch_0 0x2762d0,
  OKToStand 0x2740f0, PickupBuddyCallback 0x26fe40, CrouchToPickupBuddyCallback 0x26fdb0,
  CrouchToPickupBuddy 0x26f750, PickupBuddy 0x26f530, PutdownBuddy 0x26f350, GetStance 0x27d2a0
  (was a placeholder returning stand). seal_env.cpp: AlignForPickup 0x2a0210, BuddyPickupRefpoint
  {5.26, -4.22, -3.26} (__sinit_seal_env 0x46d010). seal_control.cpp: gate for action 8 lifted.
  zseal.h: IsStopped / CanCrouch bool.
- a4.log (la1 = pb.sh la1 pad_a1.txt; hook_leftovers.cpp drives the pad through a scePadRead wrap):
  knife 58.7 s -> OutPatrol4 detached 61.7 -> "PICKUP BODY" offered (avail 0x110: TAKE 552 first; the
  hook holds CROSS + LEFT to rotate the HUD list) -> CrouchToPickupBuddy 62.8 (Stand2Crouch, PickupBuddy
  at 0.99) -> PickupBuddy 63.4 (states 9 / 10) -> 90 reads forward, 50 units, body on the shoulder,
  "DROP BODY" -> PutdownBuddy 69.4 -> detached 71.6, player crouched, "PICKUP BODY" again; full stick
  while crouched -> sneak blend pushed crouched (ELF), back to Crouch on release. To 153 s, no STOP.
- The action runs on the button's release; LEFT/RIGHT while held rotates the HUD list.

## (b) leaving a mission / replay - WORKS (b3.log, b4.log)
- Written: CMission::ReOpen_Load 0x1f79a0 (fts_mission.cpp), CMissionObjectiveCamList::Reset 0x20a750
  (fts_objectivecam.cpp). The pause menu, abort valve, exit state, debrief and OnReplayMission were
  already written.
- b3.log (lb1 = pbx.sh lb1 pad_b1.txt hook_exit; hook_exit.cpp drives the pad from theGame's top state
  and a CMission::OnMissionStart wrap): mission 1 pause -> ABORT 74.0 s -> "complete, state 4" -> debrief
  (MISSION FAILURE, BRIEFING / REPLAY) 77.9 -> X (2nd press) -> ReOpen_Load 95.7 (30 entities) ->
  mission 2; pause -> REPLAY 112.7 -> exit state pops 1 at once -> ReOpen_Load 117.5 -> mission 3;
  pause -> ABORT -> debrief -> TRIANGLE -> menus 156.6 -> PLAY GAME, START -> mission 4 (movie skipped)
  -> 30 s -> ABORT -> debrief -> TRIANGLE -> menus 239.0. No STOP / TLB.
- Heap `use` at "MENU: loading world ui": boot 10.34 MB; after missions 1-3 (2 replays + abort): 10.50
  MB; after mission 4: 10.60 MB (~+0.1 MB per menu trip, as missionexit saw). brk 0x10f2000 ->
  0x1ca9000 -> 0x1ce1000 (fragmentation; heap end 0x1fdf000).
- Seen after the second menu: idle main menu -> dlgHype (attract) 250 s -> the VM shut down ~290 s
  (the kiosk demo leaving to its launcher? not chased; nothing traced).

## (c) ladders - written, UNTESTED
- The disc image (demo, May 13 2002) holds one mission: run/sp/m8 (iso.py lists it; no other run/sp or
  run/mp folder), and m8 has no flag-2 DI (pickups' k1.log census). Nothing to test on.
- Written: InStateClimbLadder 0x278f20, SlideLadderDown 0x274450 (seal_body.cpp); CheckDILadder 0x29ff80
  (bool), PostCheckDILadder 0x2a01d0, PreClimbLadderDown 0x2a0350 (seal_env.cpp); each flagged UNTESTED.
  PreClimbLadderDown runs from PopBlend after Rotate180 (it may now ClearStack outside a ladder: ELF).

## (d) CQB attack - WORKS (d1.log)
- Written: CZAnim::ActivateEx 0x1ceee0 (zanim_anim.cpp; returns the copy, zanim.h), CZSealBody::
  ExecuteAction_CQBAttack 0x24ed60 (seal.cpp, bool), SetHudHitFlag 0x294180 (seal_env.cpp); gate for
  action 12 lifted (seal_control.cpp).
- d1.log (ld1 = pb.sh ld1 pad_a1.txt -DSOCOM_HOOK_CQB: victim 12 ahead facing the player): CQB offered
  first (0x1000) -> "CQB: player attacks OutPatrol4 (ai_cqb_attack ...)" 57.3 s, player anim CQB (201),
  WEPHIT event taken by the victim -> its ANIMATION 150 -> victim down (dead), drops 552 + ammo box.
  To 151 s, no STOP.

## ELF quirks kept
- InStateCrouch: the crouch strafe weight is not mirrored by the strafe side; the crouch walk's
  CrouchMoveControl gets a first argument of 1 (unused) and the quadranted throttles; full stick while
  crouched pushes the sneak blend in the crouched state. InStateCarried's stopped case leaves
  m_is_moving / m_is_turning. CrouchToPickupBuddy copies the buddy's node z row and overwrites it.
  AlignForPickup negates the caller's direction in place and writes the target twice. OKToStand: the
  hit poly is not NULL-tested. ActivateEx appends the terminating NULL command as an argument too.
  PreClimbLadderDown calls IsRemote twice. ReOpen_Load creates mission_replay with value 1.

## Port deviations
- Crouch_0 from a hang or an unknown state: the ELF writes the representative flags of NULL (port:
  returns NULL; CrouchToPickupBuddy then returns the top). CrouchToPickupBuddy: the buddy's controller
  is NULL-tested. CrouchToPickupBuddyCallback calls ClearStack(2, true) (inline in the ELF).
- ReOpen_Load passes CEntity::m_list.size() to CAiEvent::Open / CPickup::Open (as Open does).

## Tools
Copied from boot-pickups (+ fx2's hook.sh with the freecam wrap, missionexit's build scripts), paths ->
boot-leftovers / tree-leftovers. hook.sh builds `${HOOK:-hook_leftovers}.cpp`, wraps scePadRead (hook-
driven presses) and `$WRAPX`. pbx.sh <build> <pad> <hook> [wraps]. cc.sh <src-rel files>: syntax check
in the test tree. iso.py <image> ls|get: read-only ISO9660 listing of the disc image (path given on the
command line, never recorded). final.sh / final2.sh: the final builds. hook_exit.cpp: reusable
state-driven pad (pause menu rows by m_curselection, debrief X / TRIANGLE, menus, movie skip).
