# boot-orders notes (socom-port-orders): the command menu and its orders (m8)

## State / next step
- (a) DONE: the whole OrdersMenu works from the fake pad. o2 run (pad_o2.txt, hook_orders.cpp:
  no IssueCommand calls): CIRCLE tap opens the menu, TEAM -> HOLD POSITION -> Bravo
  (Bailey, DiMone) holds while the player walks 770 away, Hutchins keeps following; second
  menu TEAM -> FOLLOW -> Bravo runs back. Mission 143 s, no STOP, heap 21.98 MB steady, enemies
  patrol / fight (Hutchins vs OutPatrol5). Default build: main menu (def.png).
  Screenshots: build/port/screenshots/29-orders-menu/.
- (b) DONE for the moving orders and REGROUP: CAiSGoto (OnSignal 0x2da1d0, Tick 0x2d9780), the
  CanPushAiState gate takes GOTO, OnCommand moving orders 13..17 (0x282278), CSealUnit::IssueCommand
  REGROUP (0x2d135c), ATTACKTO (0x2d1508), the moving orders (0x2d1528). o3/o4 (pad_o3/pad_o4):
  TEAM -> RUN TO -> CROSSHAIRS: Bailey runs there (goto), DiMone follows him, both then hold;
  REGROUP: Bailey goes to the player's trail point 4 (GOTONODE) and holds, Hutchins follows.
  o4: mission 137 s, no STOP, heap ~21.96 MB.
- (c) PARTLY: hand signals (InitHandSignals 0x2e38c0, DoHandSignal 0x2e3760 -> int,
  VoiceHandSignal 0x2d2f40), compass (CCompass Open 0x24e490 / Close 0x24e440 / CreateAnchor
  0x24e290 / DeleteAnchor 0x24e1a0; Bravo's anchor in CreateSinglePlayerUnits, its update in
  CSealUnit::Tick). o5 (pad_o4.txt, all of it): compass shows Bravo's marker (o5-78.png), RUN TO +
  REGROUP as o4, mission 135 s, no STOP, heap 21.95..21.99 MB. Default build (def2.png): main menu.
  ConfirmCommand (the order confirmation sound) is NOT written (see Not written).
- Next: ConfirmCommand and its string helpers; the other unwritten order cases below.

## Written (ELF addresses)
- orders.cpp: Tick 0x174b30, ScrollBack 0x174e40, ScrollForward 0x175420, AllCollapse
  0x175a50, RefreshDisplay 0x175cf0, HandlePad 0x175ff0, PlayScrollSound 0x176cf0,
  DoOrdersMenuCalculations 0x176d60, LoadTextures 0x1772a0, Load 0x1777c0, ClearText
  0x177830, Disable 0x177a20, Enable 0x177bc0, dtor 0x177f60, ctor 0x1780c0,
  SetupContextDisplay 0x178eb0, SetupCommandDisplay 0x1792c0, SetupTeamDisplay 0x1798c0,
  SetupTuples 0x179da0, SetupTuple 0x17ac50, EnableTuples 0x17aed0, RefreshContext 0x17b000,
  C2DOrderItem Tick 0x17bbf0 / SetTrans 0x17bf40 / HandleMoving 0x17bfb0 / Draw 0x17c3a0,
  CMD_TABLE dtor 0x17c4d0; inline: C2DOrderItem ctor 0x178cc0 (ztwod.h), CMD_TABLE ctor
  0x178d50 and CSubMenu ctor/dtor 0x17bbd0/0x177990 (orders.h). HandleRecoCmd / OnRecoCmd
  stay stubs (voice).
- reco.cpp: offline early-outs of recoUnInit, recoInit2, recoSetContextByCol, the four
  threshold functions, recoStart/StopRecognizing, recoGetWordID (recoInited stays 0).
- seal_unit.cpp: AllowCommand 0x2d6bf0, can_run_anim 0x2d72c0, IssueCommand cases above,
  VoiceHandSignal 0x2d2f40, Bravo's compass anchor (CreateSinglePlayerUnits 0x2d3ec0, Tick 0x2d0250).
- seal_handsig.cpp: InitHandSignals 0x2e38c0, DoHandSignal 0x2e3760 (int; CAiSHold stores it now).
- seal.cpp: CCompass Open / Close / CreateAnchor / DeleteAnchor.
- seal_aistate.cpp: CAiSGoto OnSignal / Tick, GOTO in the CanPushAiState gate.
- seal_command.cpp: CSealCtrlAi::AllowCommand 0x2826d0, AllowCommandFOLLOW 0x283350,
  AllowCommandHOLDPOS 0x283090, CanDeploy 0x282c10 (bool now), OnCommand moving orders.
- seal_body.cpp: FindValidReticleGotoLoc 0x26e700 (bool now, zseal.h).
- fts_player.cpp: ParseTeamBlock 0x1fda10 (u32, declared in zfts.h).
- ai_maps.cpp GetActionById 0x19c800, ai_mapdata.cpp FindActionLocation 0x19efc0 (bool now).
- hud_main.cpp: CHUD::Tick calls m_ordermenu.HandlePad (menu state none / orders).
- headers: hud.h (CSaferStr sounds, typed m_submenu / m_command), orders.h (CMD_TABLE,
  CSubMenu, reco declarations), ztwod.h (C2DOrderItem public + ctor), znet.h (CZNetVoice
  friend OrdersMenu), zai.h (CAiSGoto members, bool decls).

## Pad
- TeamCommand = CIRCLE (controller.rdr config 0). Tap (< PTT_circle_down_time 0.3 s) opens
  the menu; X or CIRCLE steps right, UP/DOWN rows, TRIANGLE back, START closes.
- Reads: mission t ~= (read - 390) / 30. pad_o2: menu at 900 (t~17), hold 990, walk 1070,
  menu 1450 (t~35), follow 1540, walk 1620.
- m8 TEAM rows at t17: Fire At Will, Cover Target, Run to, Lead To, Follow, Hold Position,
  Regroup (Follow shows because a seal was pursuing). After HOLD: ..., Follow, Regroup.

## ELF quirks kept
- HandlePad: START's close still runs the second button chain (L2+left/right twice); the
  TeamCommand button state is set back to pressed after the press.
- C2DOrderItem::Draw loads the glow frame but never draws it; HandleMoving: with exactly one
  step left the target x takes the target y.
- RefreshContext sizes the moving orders' list for every nav point but fills only type-1 ones;
  DEPLOY's unit and the fireteam's Bravo lookups are not NULL-tested.
- ParseTeamBlock: a team number outside 0..31 becomes the mask. CSealUnit::AllowCommand: the
  members' answer is ignored for BOMB / EXTRACT / AMBUSH. can_run_anim's run_once never clears.
- SetupTuples counts the network teams 32 / 25 as commandable; recoThreshold* return an unset
  register without recognition (port: 0).

## Port deviations (flagged in source)
- HandlePad: UP in the team column wraps before the team is tested (ELF reads team_table[-1]).
- Team lookups that match no row give no team (ELF reads team_table[-1]).
- SetupContextDisplay shows "" for an unfilled context entry (ELF strncpy from address 0).
- CHUD::Tick: HandlePad not called without a pad (network spectator only).
- Votes, SOP renaming of orders, remote (network) controls in AllowCommandFOLLOW/HOLDPOS: not
  written (multiplayer). EXTRACT never allowed (CAiMap::region::Contains unwritten).
- ~OrdersMenu clears cmd_table after deleting it.
- CSealUnit::UnInit does not delete a unit's compass anchor (the ELF's inlined dtor does): 24 B +
  name leaked per mission (CCompass::Close empties the list, so nothing dangles).
- DeleteAnchor is void (the ELF returns whether it was listed; no caller reads it).

## Not written / next
- Voice: HandleRecoCmd, OnRecoCmd, the gsapi engine (stays stubbed).
- CSealUnit::ConfirmCommand 0x2d2030 (the leader's "SND_<unit>_<n>_WILL_..." confirmation;
  needs GetUnitLeaderHandle 0x2d1f00, GetUnitNameStringFromUnitNum 0x2d2b10,
  GetSoundNameStringFromCmd 0x2d2730, Get{Node,Weapon}NameStringFromSRString 0x2d22c0/
  0x2d24e0); CSealUnit::UpdatePointOutState /
  ResetPointOutState (point-out, LEADTO).
- IssueCommand: breaches, COVERTARGET / LASETARGET / DEPLOY / AMBUSH / ACTION / ESCORT cases
  (0x2d0ef8..0x2d1d00); OnCommand ACTION 0x28240c, DEPLOY 0x281a80, GETDOWN 0x281f10,
  breaches 0x282574, LASETARGET 0x281148, AWARE 0x2824b4, AWAKE 0x282588.

## Tools
- hooko.sh + hook_orders.cpp: fake-pad build with team trace every 2 s and the test camera
  behind Bravo at mission 26..37 s. No IssueCommand calls. b.sh <build> <pad> with
  HOOKSH=hooko.sh. tree.sh = HEAD + copy.txt (= mine.txt). default.sh = default build.
- edits/d_*.rep.txt = rep.py sources of what is applied (already in the repo files).
- asm_o/: the disassembly of the functions written here.
