# boot-missionwin notes (2026-11-13, socom-port-missionwin): winning m8

Untracked scratch. Changed files: `mine.txt` (= copy.txt for tree.sh); shared-file edits: `shared.txt` + edits/.
Tools copied from boot-leftovers + boot-mapglass (paths -> boot-missionwin / tree-missionwin / missionwin-default),
plus survey.py (boot-teamhud), hook_skipcams.h (boot-stance), g2.sh (gpref with the regex from a file).
Disc readers dumped (read-only, from the user's image) into the session scratchpad `disc/` only.
NOTE: an ELF string's file offset is not its address (main: file 0x80 = vaddr 0x100000).

## State / next step
- DONE a + b (c: see below). HEAD 1c4077a; every edit file applied in place (edits/applied/); mine.txt lists the
  10 changed files. Final run w12 (mw1 = HEAD + mine, hook_win.cpp, test traces t_menu.txt): every m8 objective
  through its own trigger (log: "HOOK: read N VALVE ..."), HUD messages, tac map checkboxes, real C4 on the three
  weapon caches, Snow3 restrained -> CMD_ESCORT -> RESCUED in Extract -> extract.pss -> success -> debrief
  MISSION SUCCESSFUL (stats) -> X -> dlgDebriefing -> dlgHype -> main menu (dlgMenu at 257 s). No STOP.
  Screens: build/port/screenshots/35-mission-win/. Default build (mwdef, default.sh): menu init 15.7 s, attract.
- Exit-path regression e1 (mwe = hook_win.cpp -DSOCOM_HOOK_EXITPATHS): mission 1 pause ABORT -> MISSION FAILURE debrief ->
  X replay (ReOpen_Load) -> mission 2 pause REPLAY -> mission 3 pause ABORT -> debrief TRIANGLE -> menus (158 s). No STOP.
  (boot-leftovers' hook_exit.cpp via hookx.sh pressed nothing after the movie skip in x2: not chased.)
- Known, not chased: the menu sometimes stops (log ends) in CGameMenu::LoadFromDesign right after Clear(), at the
  design's asset lib (w9: loading dlgDebriefing; w12: the second dlgHype after 80 s idle at the main menu; boot-
  leftovers saw the VM stop ~290 s after a menu return too). Not in the success path's code.
- Next: COUNTER objects (debrief TOTAL column, objectives complete counts, percentage; below), the debrief's
  RESTRAINED stat (0 after a restraint), Sample_ExtractionLoc, the hostage-surrender interplay (Findings).
- Test: `HOOKSH=hookw.sh bash tb.sh <build> pad_a1.txt -DSOCOM_HOOK_WIN [edits/t_menu.txt]`, `go.ps1 <build> <run> 530 <shots>`.
  hook_win.cpp = the scripted playthrough (header). The player and the SEALs are made invincible (m_invincible:
  SetHealth floors at 0.1; 66d011d enemies rush and throw grenades); kills use the real fall damage with the player
  as killer (the Leader first, or he erases the documents 60 s after the first cache: nodocs fails the mission);
  the C4 is selected with SetCurItemByIndex (the weapon menu's choice) and placed with R1 facing a cache face;
  the escort order uses the cached reticule seal (the restrained captive sits below the standing aim); the walk to
  the extraction zone is a teleport of captive, Bravo and player in the frame of the order.
- Part c (records): the success path's own records are script valves: dlgDebriefing's Progress_flash runs
  incr_spec_mission_comp (incr_miss_8 += 1, TestForCompletionLevel: GameComplete = the lowest incr_miss_*,
  IncrAiDiff: ai_difficulty), all PERSIST valves from readerc global_valves.rdr (the memory-card save writes
  persistent valves). The demo's dlgDebriefing only saves from its save button (MemCheckSave / SaveGameOnListBox:
  left stubbed, not reached). w12's X landed on the debriefing's CROSS button (OffToHype) 0.5 s after it opened,
  before Progress_flash's valves were traced; the demo has one mission, so unlocks / next missions cannot be shown.
## Survey: the m8 objective chain (readerm.zar objectives.rdr + hudobjectives.rdr; demo disc)
The mission anim `objectives` (ON_STARTUP) runs one sequence per objective, each a WHILE TRUE poll:
| # | HUD objective (valve)           | set by (sequence)                                                     | needs in the port |
|---|---------------------------------|-----------------------------------------------------------------------|-------------------|
| 1 | OBTAIN INTEL (POBJ1) primary     | Computer: valve computer == 99 (laptop node action GetDocs sets it)    | works (actions)   |
| 2 | INSERT INTO MISSION (POBJ4) sec  | Insert: ai::INREGION InsertObj player; then m8tut2 cam, new obj text   | CTRegion::Tick    |
| 3 | BRAVO TO CHARLIE (SOBJ10) sec    | Ambush_cover: Bailey && DiMone in region Ambush (fail: sentry dead 1st)| CTRegion, orders  |
| 4 | NEUTRALIZE SENTRY (SOBJ1) sec    | Sentry: OutPatrol4_valve_alive == 0 or INSTATE restrained/following    | kill; CTInState   |
| 5 | BRAVO COVER DREDGE (SOBJ9) sec   | Sleeper5 (team 1 in Dredge) -> Bravo_cover: Bailey/DiMone in Cover     | CTRegion          |
| 6 | SECURE COMPOUND (POBJ5) primary  | Compound: SOBJ2 && SOBJ3 && SOBJ4                                      | -                 |
| 7 | SECURE LODGE (SOBJ2) sec         | Lodge: player in SearchLodge && aiteam_11 == 0                        | CTRegion, kills   |
| 8 | SECURE BOSLER HOUSE (SOBJ3) sec  | Snow: player in SearchSnow && Snow1, Snow2 dead                       | CTRegion, kills   |
| 9 | SECURE PINCUSHION (POBJ3) sec    | RestrainKola: Snow3 INSTATE following or restrained                    | CTInState         |
|10 | SECURE CABIN (SOBJ4) sec         | Cabin: CabinBreech == 2 (Bravo breach) or Cabin2: Safe1 && Shed1 dead  | CTRegion, kill    |
|11 | DESTROY WEAPONS (POBJ2) primary  | Crates: cratecount == 3 (crate_group** WEAPON_HIT anims, HEALTH 1 SHIELD 11: +1 5 s after each) | C4 / explosion damage |
|12 | EXTRACT CAPTIVE (SOBJ6) primary  | Extract: Snow3 in region Extract && INSTATE rescued -> extract=1, PlayMPEG m8/extract.pss | rescue chain |
|13 | OUTHOUSE AMBUSH (SOBJ7) bonus    | Bonus: Shed2 dead && outhouse1 == 1                                    | -                 |
- Rescue chain (ELF): restrain Snow3 (RestrainBuddy: STATE_RESTRAINED) -> order CMD_ESCORT (OnCommand 0x2820a0:
  a team-0x20000 target joins the player's unit as an escortee, FOLLOW (9) = "following") -> CSealCtrlAi::PostTick
  0x268704: an escortee in FOLLOW inside a type-1 (extraction) region -> SetAiState(STATE_RESCUED 17) ->
  CAiSRescued::Tick 0x2592f0 (joins unit 17 ...). CMD_EXTRACT (HandleSupport 0x2d2bd0, cmd 22) only plays
  "escortee_extract" (not in m8).
- Player feedback: the script's MESSAGE lines ("OBJECTIVE COMPLETED: ...", "NEW OBJECTIVE: ...") go through
  zAnimMessageTick 0x1bfce0 -> theMission.m_messenger.Add_Message (C2DMessage_Q, drawn by the HUD's 2D list);
  HQ / team lines: SOUND / ai::SOUND (headset, written); MUS_OBJ_COMPLETE music events; mission cams m8tut2/m8tut4;
  the tac map list re-reads IsComplete (checkboxes) and TickObjectives moves the compass anchor to the next open one.
- Success: `start` polls computer == 99 && extract == 1 && cratecount >= 3 && POBJ5 == 1 (also re-tested by
  Extract) -> "VICTORY: MISSION OBJECTIVES COMPLETED", SND_VM08_67, 5 s, `success`: nofade = 1,
  mission_complete = 1 -> CMission::Tick -> OnMissionComplete(MISSION_SUCCESS) -> nofade: _OnMissionComplete,
  theGame.Push(m_exitState) at once (written). Failures: player death, nodocs, aiteam_01 (SEALs down), Snow3 dead.
- Debrief (readerx.zar dlgExitState.rdr): ExitOnStart IsMissionSuccessful (written) -> MUS_SUCCESS +
  SuccessBackground (db_back.tif), stats teletype (SetRoundStatUiVars: primary / secondary counts, StatObjectivesPct
  = 100 * (0.6 p + 0.4 s)); X when done -> CloseAndSwitch dlgDebriefing.rdr (run/ui readerc.zar); TRIANGLE on a
  success does nothing. dlgDebriefing (demo): Progress_flash -> incr_spec_mission_comp (incr_miss_8 += 1,
  TestForCompletionLevel: GameComplete = min incr_miss_*, ai_difficulty), "THANK YOU FOR PLAYING.", ShowGameReview
  teletype "CONGRATULATIONS COMMANDER! ... MORE MISSIONS WILL BE AVAILABLE IN AUGUST.", MUS_SUCCESS, after 11 s
  OffToHype -> SWITCHMENU dlgHype.rdr (attract). Save: MemCheckSave / SaveGameOnListBox only on the save button
  (memory card; not wanted).
- ELF records: incr_miss_5..21 and GameComplete are the persistent valves of the CValve ctor's table 0x43a7e0
  (type 1, survive CValve::Reset); the debrief scripts change them; memory-card saving goes through the save UI.

## Empty functions on these chains (survey.py / fences.py)
- seal_tasks.cpp (enemyai2's file -> edit file): CTRegion::Tick 0x2b4c50 1540 B, CTInState::Tick 0x2bb9c0 312,
  CTInView::Tick 0x2bb680 372, CTRange::Tick 0x2b53f0 472, CTTeam::Tick 0x2b49f0 324 (all `return false`).
- ztwod_messageq.cpp: C2DMessage_Q Draw 0x1ff9a0 896, Tick 0x1ffd20 844, Add_Message(c,i,i,i) 0x200130 892,
  Add_Message(c,i) 0x2004b0 884, LastMessage 0x200890 144, dtor 0x200a10 372; C2DMessageString SetString 0x2010b0
  116, Tick 0x201130 304. zanim_cmd_tick.cpp: zAnimMessageTick 0x1bfce0 136.
- seal_ai.cpp (enemyai2): PostTick's rescue part (0x268704..0x268854), CAiSRescued Tick 0x2592f0 904, OnSignal
  0x2596c0 220, SetExtractValve 0x259680 52. CMission::Sample_ExtractionLoc (fts_mission.cpp, mapglass2): stub.

## Written (ELF addresses)
- ztwod_messageq.cpp (mine): C2DMessage_Q Add_Message(text, time) 0x2004b0, Add_Message(text, r, g, b) 0x200130
  (shared part QueueMessage: wrap at the last space that fits m_maxlength - 2 XMargin, the rest queued by a
  recursive call), Tick 0x1ffd20 (descent / slide-up, max size, 0.5 s after a message's time it goes), Draw
  0x1ff9a0 (two background halves, newest message at m_cur_top, older ones above), LastMessage 0x200890, dtor
  0x200a10; C2DMessageString SetString 0x2010b0 / Tick 0x201130 (types at m_ttySpeed, fades over 0.5 s).
  ztwod.h: C2DMessageString derives from C2DString (ctor 0x302ed0 in Add_Message), members m_time / m_elapsed /
  m_ttySpeed / m_text (+0x88..+0x94, no DWARF, names invented).
- edits/w_msgtick.txt (zanim_cmd_tick.cpp): zAnimMessageTick 0x1bfce0 (record +4 text index, +5..7 RGB).
- edits/w_tasks.txt (seal_tasks.cpp): CTRegion::Tick 0x2b4c50, CTInState::Tick 0x2bb9c0, CTInView::Tick 0x2bb680,
  CTRange::Tick 0x2b53f0, CTTeam::Tick 0x2b49f0 (records TASK_REGION/INSTATE/INVIEW/RANGE/TEAM).
- edits/w_rescued_ai.txt (seal_ai.cpp): CSealCtrlAi::PostTick rescue part 0x268704, CAiSRescued Tick 0x2592f0,
  OnSignal 0x2596c0, SetExtractValve 0x259680; edits/w_rescued_zai.txt (zai.h): CAiSRescued m_region / m_master /
  m_valve (+0x28..+0x30).
- seal_unit.cpp (mine): CSealUnit::IssueCommand CMD_ESCORT branch 0x2d0ef8.

## ELF quirks kept
- CTRegion: a missing entity clears the first byte of the task's name (the next lookup by name fails).
- CTRange / CTTeam: no select seal = done at once. CTInView uses up the frame's time, CTInState does not.
- C2DMessage_Q Draw / LastMessage cast every list member to a message string without a type test.

## Port deviations
- CTRegion's pickup mode (task +0x12) not written (no m8 script uses it).
- CSealUnit CMD_ESCORT skips an empty unit (ELF reads front() of it); a NULL reticule seal is skipped.
- CAiSRescued::Tick phase 6: the pushed state is only written when it is STATE_SUSPENDED (ELF writes through NULL).

## Findings for other areas (open)
- DESTROY WEAPONS (POBJ2, primary, needed for success) needs C4: the crates' WEAPON_HIT anims have shield 11; the
  M67 frag's explosion damage is 10 (zweapon.zar AMMO14), C4 18 (AMMO20), satchel 20. C4 placement / detonation
  (CZKit::TickExplosives' placement branch, the detonator) is not written (socom-port-kit). Test stand-in in
  hook_win.cpp: the thrown M67s get the C4 ammo record (c4_standin), so the crate anims run from a real blast.
- 66d011d: Snow3 (courage -1, surrender 1) surrenders right after a restraint (CSealCtrlAi::Tick's reaction: outmatched
  -> DoReaction -> ClearAiState(true) pops RESTRAINED -> SURRENDER). In the ELF the same Tick code exists (0x268a64:
  FindAiState FLEE / SURRENDER only), so this may be faithful when the captive becomes aware while restrained
  (sensors / CanScan of a restrained AI not verified). The hook restrains him again (RESTRAINED over SURRENDER,
  then no new reaction) before the escort order.
- The port's CanPushAiState gate (seal_aistate.cpp) refused STATE_RESCUED: edits/w_gate.txt allows it.
- CAiMaps::GetRegion(loc) was empty (every ai::INREGION and CTGoto region lookup failed): edits/w_aimaps.txt.
- CSealCtrlAi::OnDeath was empty: "<name>_valve_alive" never went to 0 (sentry, Bosler, cabin, Snow3 failure,
  buddy death music): written in edits/w_rescued_ai.txt.

## Checkpoint (HEAD 1c4077a, all edit files applied in place, edits/applied/)
- w9 (cb07c7a tree, C4 stand-in): every objective through its own trigger -> Snow3 RESCUED in Extract ->
  extract.pss -> extract = 1 -> success -> mission_complete / nofade -> MISSION: complete state 2 -> debrief
  "MISSION SUCCESSFUL" with the per-seal stats (w9-270.png) -> X (StatsProgress 100) -> menu state reads
  dlgDebriefing.rdr, then the log stops (hang; t_menu.txt traces LoadFromDesign to find where).
- w11 (1c4077a, real C4: the kit worker's placement; the stand-in is gone): R1 with C4 selected in front of a crate
  face places it ("EXPL: C4 placed"), 5 s later the crate's WEAPON_HIT anim -> cratecount 3 -> POBJ2. The escortee
  then gave up (FollowTick HOLDPOS: the player's teleport trail made the master "far") -> the hook now moves the
  captive, Bravo and the player into Extract in the frame of the escort order.
- Debrief gaps: COUNTER objects are not written (GetObjectSpec skips COUNTER: CCounterSpec::CreateDisplayObj
  0x399450, Copy 0x399570, C2DCounter Tick 0x392e40 / TickZAnimCmd 0x392cf0 / GetZAnimCmdType 0x393160 /
  dtor 0x394820, UiSetCounterSpeedFactor 0x393270): the TOTAL column, objectives complete counts and the
  percentage stay empty; the dialog's NODE START/CONTINUE commands fall through (UI_COMMAND 0x98).
