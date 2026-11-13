# boot-fireteam notes (socom-port-fireteam): fireteam follow, unit orders

## State / next step
- (a) DONE. ft3 (hook_fireteam.cpp via hookf.sh, pad_f2): units built at mission start,
  fireteam FOLLOW; Hutchins (Able), Bailey + DiMone (Bravo) follow the walking player on his
  trail (modes 0->2->3), hide when he stops (4->7), engage enemies (DiMone kills OutPatrol1:
  PURSUE / TARGETING over FOLLOW, back to FOLLOW). Hook order HOLDPOS at mission 22 s: the
  fireteam passes it to Bravo (ELF), Bailey + DiMone hold (STATE_HOLD) while the player walks
  730 away; FOLLOW at 38 s: Bravo runs back (800 -> 104) and hides beside him. Mission 133 s,
  no STOP, heap 21.9 MB steady. ft4 = same run with the test-camera shots (ft4.log, mission
  127 s, 0 STOP, heap 21.93 MB): build/port/screenshots/26-fireteam/.
- Default build (def.log/def.png): main menu at 16 s, attract slideshow at 52 s, no STOP.
- (b) NOT written: the command menu (OrdersMenu, Apps/FTS/game/orders.cpp, 30 KB of stubs:
  HandlePad 0x175ff0 3312 B, SetupTuples 0x179da0 3752 B, RefreshContext 0x17b000 2968 B,
  ScrollForward/Back 3 KB, Enable/Disable, SetupTeam/Command/ContextDisplay, C2DOrderItem
  draw/tick, LoadTextures); CHUD::Tick (hud_main.cpp) has the HandlePad call commented out.
  The order path below the menu works (CSealUnit::IssueCommand -> CZSealBody::IssueCommand ->
  CSealCtrlAi::OnCommand): the hook calls it as HandlePad would.
- Other unwritten (c): OnCommand cases ACTION/DEPLOY/GETDOWN/moving orders 13..17 (RUNTO,
  STEALTHTO, LEADTO, ATTACKTO, GOTONODE)/breaches/LASE/AWARE/AWAKE; CSealUnit::IssueCommand
  cases for those + REGROUP, AMBUSH, ESCORT, COVERTARGET, unit 17 (escortees);
  CSealUnit::AllowCommand 0x2d6bf0 (returns false), CSealCtrlAi::AllowCommand 0x2826d0 (stub),
  AllowCommandFOLLOW/HOLDPOS, VoiceHandSignal 0x2d2f40 (player's hand signal), DoHandSignal
  0x2e3760 (seal_handsig.cpp), Notify/DistributeNotify/PrivateNotify (unit messages, e.g.
  player fired -> stub), UpdatePointOutState, ConfirmCommand, CAiSAvoid (follow mode 9).
- Tree: HEAD + copy.txt (= mine.txt whole files) + shared.txt (seal_aistate.cpp belongs to
  socom-port-aistates: my CanPushAiState gate (+FOLLOW, +HOLD: edits/s_aistate.txt) and
  PopToAiState (edits/e_aistate.rep.txt) are edit files for the coordinator to merge).
- NEVER pipe pcsx2-boot.ps1 into Select-Object -First (cuts the script before its kill step).

## Files (mine.txt) and edit files
- mine: seal_unit.cpp, seal_command.cpp, seal_aifollow.cpp, seal_airesponse.cpp (CAiSHold),
  seal.cpp (SetSnakePathUpdate), seal_ai.cpp, zseal.h, zai.h (CAiSHold members, ExtendPath
  bool), zbody.h (friends CSealCtrlAi, CAiSHold for m_state), ai_path.cpp (snake trail),
  ai_maps.cpp (ExtendPath, SmoothPath), ai_mapwalk.cpp (GetLocationWidth), seal_handsig.cpp
  (untouched). Edit files: edits/s_aistate.txt, edits/e_aistate.rep.txt (seal_aistate.cpp).
- edits/d_*.rep.txt are the rep.py sources of what is already applied to my own files.

## Written (ELF addresses)
- seal_unit.cpp: Create 0x2d7620, ctor 0x2d6a20, SealJoinUnit 0x2d68e0, EscorteeJoinUnit
  0x2d67a0, SealLeaveUnit 0x2d6570, GetSealByIndex 0x2d5fb0, InitalizeSealUnit 0x2d4250,
  CreateSinglePlayerUnits 0x2d3750, SetFormation 0x2d31d0, IssueCommand 0x2d07e0 (prelude, list,
  FOLLOW, default), CommandNotifyFromChild 0x2d0620, GetLeader 0x2d04f0, GetTail 0x2d03b0,
  Tick 0x2cf7f0, GetMyLookDir 0x2d7340, GetMyPointOutTurnDir 0x2cf010, GetMyPointOutAnimStart
  0x2ced80, IsMemberOfUnit x2 0x2d6040/0x2d61b0, Get/SetConfirmVoiceCommands, Get/Set
  PlayAutoMessages.
- seal_command.cpp: GetCommandName 0x282d40, GetCommandId 0x282cd0, CSealCtrl::AllowCommand
  0x282cc0, CZSealBody::IssueCommand 0x2825e0, CSealCtrl::OnCommand 0x2825d0,
  CSealCtrlAi::OnCommand 0x281080 (FIREATWILL/HOLDFIRE, HOLDPOS/COVERTARGET, FOLLOW).
- seal_aifollow.cpp: all 16 (FollowTick 0x2df1c0, the 4 helpers, GetSnakeFollowLoc 0x2e20e0,
  CAiSFollow OnSignal/GetStatus/Tick, Set/GetFollowMaster, SetFollowOffset, HasFollower,
  Invalidate/UpdateFollowParams, GetStanceFromState).
- seal_ai.cpp: GetDuckStance 0x261d20, SetHoldFire 0x260db0, ConfirmAiState 0x25fd30; AttackTick
  unit tests (escortees -> targeting; m_ambush -> weapon ready).
- seal_airesponse.cpp: CAiSHold OnSignal 0x2e72c0, Tick 0x2e6ef0. seal_aistate (edit file):
  PopToAiState 0x2dafa0, gate. seal.cpp: SetSnakePathUpdate 0x24eee0. ai_path.cpp:
  SetSnakeLength 0x193d40, AddSnakePoint 0x193930. ai_maps.cpp: ExtendPath 0x199220, SmoothPath
  0x199600. ai_mapwalk.cpp: GetLocationWidth 0x1a8630.

## Key facts
- Units: 1 fireteam (subs 2 Able = player + Hutchins, 3 Bravo = Bailey + DiMone), 17
  escortees, 4 enemies (subs 5..15 by team bit), 28, 29 support. Fireteam orders HOLDPOS,
  ESCORT, ATTACKTO, RUNTO, STEALTHTO, LEADTO, COVERTARGET, AMBUSH go to Bravo only (ELF).
- Follow: the master records a 75-cell snake trail while followed (UpdateFollowParams ->
  SetSnakePathUpdate; trail points have the walkable width, GetLocationWidth); the follower's
  goal is m_followOfs.z/10 cells back on the trail and x/10 across; formation direction =
  facing, or the move direction after 2 s steady motion. SetFormation offsets (25,0,-25) per
  seal, sub-units 1.5x the other side.
- CAiState bit 1 (m_unk_0c_1): order not to be confirmed (quiet / not the unit's first seal /
  already following); ConfirmAiState plays 53 "right away" and sets it.
- Offsets: CSealCtrlAi +0x418 m_master, +0x41c m_followOfs, +0x454 m_followMode, +0x450
  m_followTimer; CZSealBody +0x384 m_snakePath, +0x42c m_formation_dir, +0x458/9 follow flags,
  +0xdd bit 3 m_isAlive, +0xf59 bit 1 m_order_flag, +0xf5a bit 0 m_snake_path; CSealCtrl
  +0xdc m_unit. MW list node_base: +0 prev (back), +4 next (front). CAiSHold 60 B (+0x28 signal,
  +0x2c result, +0x30 look point); CAiSFollow 40 B.
- FT_COMMAND values = port enum (GetCommandName jump table 0x452ef0). OnCommand jump table
  0x4528d0 (orders 0..27).

## ELF quirks kept
- FollowTick's timer countdown assigns -3 where it compares (every value but -1/-2 becomes -3;
  HideCheck counts -3..-1). Its HIDE mode routes to the follower's own cell, so it always goes
  to mode 7. GetSnakeFollowLoc steps x by dir.z and y by dir.x (90 degrees across the trail).
- The master-coming test needs both throttles non-zero. SetFollowMaster stores the seal itself.
- SetSnakeLength(0) leaves m_snake_len (the trail keeps being recorded, emptied each frame).
- AddSnakePoint's m_length = largest distance from the newest to the oldest cell.
- GetLocationWidth's ring scan skips a corner column / row cell.
- SealLeaveUnit keeps the seal's m_unit. HideCheck/HoldTick/OnCommand read states unguarded.

## Port deviations (flagged in source)
- No compass anchor for Bravo / units (CCompass::CreateAnchor is an unwritten stub).
- FollowTick returns after HOLDPOS when it has no master (ELF reads the NULL master's fields).
- CAiSFollow never turns m_do_aimap_collide on (GetCellRepelParams unwritten, see InitAiBrain).
- AttackTick NULL-tests m_unit (CSpawners::Tick, which puts respawned seals in units, is
  unwritten). CSealUnit::AllowCommand returns false (unwritten).
- CAiSHold stores 0 as DoHandSignal's result (void in the port). CSealUnit has no vptr at +4
  (GCC's at +0); the units are std::lists.
- GetStance (seal_body.cpp, not mine) is a placeholder returning stand: duck / stance matching
  use stand for the master.

## Survey (ELF chain for (a) FOLLOW)
- CMission::Open -> CreateSinglePlayerUnits -> unit1->IssueCommand(player, HOLDFIRE) and the
  mission's fireteam_command (default FOLLOW) -> SetFormation -> each seal's IssueCommand ->
  OnCommand FOLLOW (SetFollowOffset/Master, ClearAiState, push STATE_FOLLOW) -> CAiSFollow
  OnSignal(0) sets AIM_FOLLOW -> PreTick -> FollowTick each frame.
- Tasks: UnitTick 0.8 (CSealUnit::TickAll -> Tick: re-issues FOLLOW after deaths / leaving).

## Tools
- hookf.sh: fake-pad build + hook_fireteam.cpp (wraps CZSealBody::CheckDIShoot: orders on the
  mission clock, test camera via ../tools/hook_freecam.h, team trace every 2 s). b.sh <build>
  <pad> with HOOKSH=hookf.sh. pad_f2.txt: start, skip the movie (400), walk 600/1070/1550.
- tree.sh: HEAD + copy.txt + shared.txt edit files (base/ snapshot mechanism unused now).
