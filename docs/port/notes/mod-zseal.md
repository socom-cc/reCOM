# mod-zseal notes (2026-11-14, socom-port-mod-zseal): the unwritten part of the zSeal module

Scratch `build/port/boot-mod-zseal/` (untracked: NOTES.md, mine.txt, the survey before / after, the scratch hook
`hook_zseal.cpp`, the Recoil table generator `recoil_gen.py` / `recoil_c.py`). Changed files: `mine.txt` (zSeal in
place, and the small in-place edits in other modules listed below, all free at HEAD).

## State
- Partly done (the module is too large for one session; see "Not written / next").
- `survey.py gamez/zSeal`: stub fences 193 -> 154 (87,376 -> 61,012 B); written 469,428 -> 495,792 B. The survey
  counts some empty bodies as written (whitespace or `return NULL`): `InitLookAnims` (1724 B) was one, written now;
  every `CT*::Parse` in seal_tasks.cpp still returns NULL (the m8 scripts are compiled in MZANIM.ZAR, so none runs
  offline).

## Findings
- "Task 1/4 NULL -- Activation failed!" for Hutchins / Bailey / DiMone is the ELF's own message: MZANIM.ZAR has only
  `<name>_special` for the three team mates (no `_start` / `_ambient`); SetupAnimations is as the ELF.
- RESTRAINED stays 0 at the debrief: ELF quirk. `ExecuteAction_ApplyRestraint` 0x24ed10 counts into `m_mp_stats`
  (+0x4a0) while the single-player debrief reads `m_stats` (+0x4c0); `m_stats.m_num_restrained` (+0x4f4) is written
  only by RemoteRespawn and CMPExitState::Init. Times seen and stealth kills go to `m_mp_stats` the same way.
- `CMission::Read` (zFTS) lacked `respawn_range` (default 50 squared), `fireteam_command`, `SATCHEL_TIMER` (10 s; the
  satchel fuse was 0) and `SEEFARTHER_BINOCS` / `SEEFARTHER_WEAPZOOM` (the binocular / zoom fog factors).
- Corpses far from the player whose node is inactive (the LOD) are never recycled, as in the ELF (PostMortemPreTick
  returns early for an inactive node without respawns).

## Written (ELF addresses)
- Dead AIs: `CSealCtrlAi::PostMortemPreTick` 0x267b30 (recycle out of view after recycle_time; with respawns: fade
  out after respawn_time, then `m_needs_respawn`), `CZSealBody::DoRespawn` 0x289260 (first other vehicle start out of
  the player's range and view; respawns used up without one), `CZSealBody::ReCreate` 0x289b10 (the body destroyed and
  constructed again in place, keeping id, team, vehicle index, display name, controller and matrix),
  `CVehicleRdrEntry::GetStart` returns bool (0x1a2d90).
- Body: `UpdatePeek` 0x273020 / `AbortPeek` 0x2736c0, `HandleSliding` 0x254130, `HandleWater` 0x2a2700,
  `HandleSmokeAndGas` 0x2a2370, `Recoil` 0x270d10 (22 parts x 6 stance / item tables generated from the ELF's
  constants), `GetMaxXMotion` 0x27ded0; head look and blinking: `InitLookAnims` 0x29dd90, `ComputeDeltaLookQuat`
  0x29e6a0, `GetLookQuat` 0x29e450, `CLook::LookTick` 0x29d140, `CBlink::Blink` 0x29d080 / `BlinkTick` 0x29cf30,
  `ApplyLookAnim` 0x29cdf0, `ApplyEyeLookAnim` 0x29cd20, `ApplyBlinkAnim` 0x29cc60 (the look tables are typed now:
  `dQlook*` CQuat[12], `Rlook*` CPnt3D[12]).
- AI: `AnimSignal` 0x2609a0 (ai::SIGNAL: anim done, critical sections, suspend), `AcquireAiAware` 0x260050 (buddies
  share awareness and targets), `SetSnoozing` 0x2670a0 (the snooze LOD: far AIs suspended), `AcquireDatabaseHandles`
  0x26c070 (boundary sounds, DI pool, snooze reset), `PlayAiSound` / `StopAiSound(AI_SOUND)` 0x26bfa0 / 0x26bf50,
  `CleanupDiPool` 0x2b3250 (now called by OnDeath), `CAiSAvoid` Tick 0x2da4a0 / OnSignal 0x2da6c0 (and its push in
  SensorPreTick), `CAiSNoAmmo` Tick 0x2e77f0 / OnSignal 0x2e7de0, `ai::find_closest_ammo` 0x2e7e30,
  `FindTraversableNeighbor` 0x2e7a30 (bool). CanPushAiState's port gate lets SUSPENDED, AVOID and NOAMMO through.
- Units: `CSealUnit::Notify` 0x2d57f0, `DistributeNotify` 0x2d5b40, `PrivateNotify` 0x2d5c90 (enemy callouts to the
  team, member died, re-follow, the player's shot ends an ambush).
- Controller / kit / stats: `CSealCtrl::PostTick` 0x287450 (the player's sensors; the throw arc is not written),
  `CZKit::CanAddAmmo` 0x2a6160 (bool), `SetCurFireMode` 0x2abd80, `SetupBinocular` 0x2ae4f0,
  `CSealStats::IncrTimesSeen` 0x24e890.
- zMath: `CQuat::Exp(const CPnt3D *, float)` 0x220860 (was empty; Recoil uses it).

## Outside zSeal (small in-place edits, free at HEAD)
`zFTS/fts_mission.cpp` (CMission::Read keys), `zVehicle/vehicle_main.cpp` + `zvehicle.h` (GetStart bool),
`zMath/zmath_main.cpp` (CQuat::Exp), `zAI/zai.h` (CAiSNoAmmo / CAiSAvoid members, CPickup forward declaration).

## ELF quirks kept
- PrivateNotify(0) points out along the pointer difference of the two positions (in CPnt3D units, all three axes).
- Notify tests the grandparent unit, so a fireteam sub-unit keeps messages 0 and 3 to itself.
- UpdatePeek's pop keeps the body in statePeek; AnimSignal's end of a critical section still marks the flags dirty;
  find_closest_ammo takes a box by its last matching entry; CanAddAmmo ignores its count; the respawned AI keeps its
  recycle timer.

## Port deviations
- HandleWater: a speed state of 3 plays no ripple (the ELF reads the word after each 3-entry array).
- HandleSmokeAndGas finds the cloud's source through `Particle::Source::list` (no CParticleEx in the port; the port
  builds no particle box DI node yet, so it is not reached).
- Recoil with no stance table (not standing, crouching or prone): identity kicks (the ELF uses unset stack slots).
- NULL tests where the ELF writes through a possibly NULL state (AnimSignal 4, SetSnoozing, the AVOID push).

## Runs (tree = HEAD + mine.txt; screenshots under `build/port/screenshots/45-zseal/`)
- zs1-zs3 (`hook_zseal.cpp`: X skips the m8 cameras, the player invincible, enemies killed at a set time):
  OutPatrol2 / 3 / 5 / 1 recycled 10-15 s after dying out of view, LeaderBud1, Alarm1-3 spawned in their slots; two
  enemies given respawns faded and came back at another start (ReCreate) with their scripts restarted; the recoil
  parameter rises to 0.7-0.95 while firing; no STOP, heap 22.1 MB.

## Not written / next
- AI states: CAiSPathRecover (its own CAiPath and planner use), CAiSAnimate, CAiSCQBAttack, CAiSPickup, CAiSHostage,
  CAiSBreach (+ AddBreachMember), CAiSGrenade Tick (6.4 KB) with SetReturnVelocity / is_throwtype, CAiSDeploy Tick
  (4.2 KB) with CanDeployItem and GetPutativeFirePointW; then their CanPushAiState gate entries.
- The throw arc of CSealCtrl::PostTick (CDynGrenade helpers, ai::DrawFunc, seal_ailines.cpp, zRender
  RenderLineWorld, zTwoD's 3D line).
- Units: HandleSupport, ConfirmCommand and its string helpers (GetSoundNameStringFromCmd...), point-out state,
  CheckPathProximity, GetAwareCounter, GetUnitLeaderHandle.
- Kit: TickLaserDesignator / FetchLaseTarget, TickFlashlight, HandlePlacingExlosive, ~CZKit; body: Hang_0,
  Raise/LowerBinoculars, FootInSpace, Slide, CheckForRegionTrigger, TickRumbler, CacheReticuleSeal; CHandSignal ctor;
  the squirm controller; seal_tasks.cpp's Parse functions (not reached offline).
- Network only (untouched): ghosts, piggy-back camera, remote AI / respawn / seal creation, MP bomb, net pickups,
  damage replication, MP stats, CreateMultiPlayerUnits, Revive, PlayRemoteMsg.

# Part 2 (2026-11-14, socom-port-mod-zseal2): the remaining AI states

Scratch `build/port/boot-mod-zseal2/` (untracked: NOTES.md, mine.txt, survey before / after, the scratch hook
`hook_zseal2.cpp`, the diag spec `diag_tasks.txt`).

## State
- Partly done again: item 1 of the plan is written except CAiSBreach and CAiSDeploy; items 2-5 are not started.
- `survey.py gamez/zSeal`: stub fences 154 -> 139 (61,012 -> 48,768 B); written 495,792 -> 508,036 B;
  `port: not written` placeholders in zSeal 35 -> 33.
- Bodies the survey counts as written but which are empty (a `return false` or nothing) while the ELF's are not:
  `CTFireWeapon::Begin` 0x2bcfa0 / `Tick` 0x2bcd70 (pushes STATE_DEPLOY), `CTAction::Tick` 0x2be2f0, `CTMap::Tick`
  0x2ba710, `CTPaint::Tick` 0x2b9820, `CTSpecial::Begin` / `Tick` / `End` 0x2b63d0 / 0x2b6150 / 0x2b62d0. A diag
  run in m8 reached none of them (it reached `CTEvent::Tick`, written, and `CTPursue::End`, written now).

## Written (ELF addresses)
- `CAiSAnimate` Tick 0x25ad00 / OnSignal 0x25aee0 (push an anim, end on its fraction, a time or either).
- `CAiSPathRecover` Tick 0x2e5290 / OnSignal 0x2e57d0 / GetStatus 0x2e5750 (creep back to the last valid cell, plan a
  route to the point the AI was stuck short of and put it in front of its path), and PathFollowTick's push.
- `CAiSCQBAttack` Tick 0x2d7a70 / OnSignal 0x2d7bc0 and SensorPreTick's push (CanUseCQB was written already).
- `CAiSHostage` Tick 0x2da2d0 / OnSignal 0x2da450 and OnCommand's GETDOWN case 0x281f10.
- `CAiSPickup` Tick 0x2da750 / OnSignal 0x2da910 (CAiState::Create now builds it).
- `CAiSGrenade` Tick 0x25af40 / OnSignal 0x25d0c0, `is_throwtype` 0x25d080 (bool), `CSealCtrlAi::SetReturnVelocity`
  0x25c860; SensorPreTick's pickup walk 0x2b26b8 (STATE_GRENADE for a live grenade in blast range, STATE_EVENT for one
  the unit has not called out); `PickupObject` 0x24f330 returns bool and has the grenade branch, `_rethrow_grenade`
  0x24f4c0; `CTPursue::End` 0x2b7f80.
- CanPushAiState's port gate lets ANIMATE, CQB, PATHRECO, PICKUP, HOSTAGE and GRENADE through (BREACH, DEPLOY,
  LASING stay refused).

## Outside zSeal (small in-place edits, free at HEAD)
- `zAI/zai.h`: members of CAiSAnimate, CAiSPathRecover, CAiSCQBAttack, CAiSHostage, CAiSGrenade.
- `zValve/zvalve.h`, `zValve/valve_list.cpp`: valve callbacks as the ELF has them (a 12-byte entry with a state mask
  and data: AddCallback 0x2f6020 appends, MakeCallbacks 0x2f60b0 runs the entries whose mask has the change,
  DeleteCallbacks 0x2f5f50); before, the entries kept no data and MakeCallbacks was empty, so no valve callback ever
  ran (the only other user, CNodeAction's `_actionValveCallback`, is still an empty stub). `Create(name, type)` with a
  NULL name acquires a nameless valve (ELF 0x2f68a0; the port returned NULL) and GetByName skips nameless valves.
- `zEntity/pickup_main.cpp`, `zentity.h`: `CPickup::GetVisibleByUnit` 0x24d1e0 (bool) / `SetVisibleByUnit` 0x24d180.
- `zBody/zbody.h`: friends CAiSAnimate (top blend) and CAiSGrenade (the right hand's node).

## Findings
- `allowThrowbacks` in CAiSGrenade::Tick is a static initialised to 0 that nothing sets: the kick and throw-back
  phases (4-8, SetReturnVelocity's callers) are never taken; enemies always run or take cover.
- A grenade is taken seriously the first time only if the seal saw it thrown (by itself or by a target it sees: the
  unit is told and the seal shouts) or a team mate threw it; from the next frame on any seal that has seen it and
  whose unit has not called it out also gets STATE_EVENT (flinch) after a skill-dependent delay.
- m8 has no escortee (every unit reports 0 escortees), and AllowCommand refuses GETDOWN to an enemy; an enemy in
  STATE_RUSH also refuses the HOSTAGE push (mask 0x100de9da): CAiSHostage is not reached in m8.
- STATE_PICKUP has no direct pusher in the ELF (only scripts through ai::STATE / ai::MACRO with a state number).
- Breach orders reach AddBreachMember only from OnCommand's breach cases with a template state the unit builds in
  CSealUnit::IssueCommand (its breach part, 0x2d0fcc.., is not written): breach is fire-team-order-only.

## ELF quirks kept
- CAiSAnimate ends at once when its anim is already the top blend; CAiSHostage's phase 0 never moves on and phase 2
  releases the stance every tick; CAiSPickup takes a weapon / ammo pickup again every tick (PickupObject answers 0
  for them); PathRecover computes a cell centre it does not use; SetReturnVelocity's seal fallback adds the
  direction's x to its y; FindPeekDir's answer is dropped in the grenade flood flee.

## Port deviations
- NULL tests where the ELF writes through a state that may be another one (the CQB, PATHRECO, GRENADE, EVENT,
  HOSTAGE and ANIMATE pushes) and on the pickup's seen-bits buffer and the seal's unit.
- `CValvePool::Release` drops the valve's callbacks (the ELF keeps them on a pooled valve, so a reused temporary
  valve would run the callbacks of the object it served before).

## Runs (tree = HEAD + mine.txt; screenshots under `build/port/screenshots/45-zseal/`)
- zq1 / zq2 (`hook_zseal2.cpp`): a frag grenade dropped beside OutPatrol4 -> "sees a live grenade (type 1, 42
  away): STATE_GRENADE", "GRENADE LOOK FLEE: will run to ...", route, "GRENADE_GOTO Arrived!", phase 11 (stand),
  stunned by the blast, the state ends; the player put 15 in front of OutPatrol3 -> "[player] within CQB Range!",
  STATE_CQB, 0.75 s, "CQB attack on player" (anim 201), recovery; STATE_PICKUP walks OutPatrol1 to the nearest ammo
  box (not reached inside the run); STATE_ANIMATE plays KickGrenade (anim 259). No STOP; heap 22.1-22.3 MB.
- zst / zst2 (part 1's `hook_zseal.cpp` on f0fbe925 and 2c3f092f, 200 s): no STOP; heap 22.06-22.18 / 22.15 MB at the
  end; the killed enemies recycle and OutPatrol3 respawns, firing, the team follows (Hutchins 16, DiMone 34 from the
  player).
- zw (`port/test-hooks/win`): extract valve, mission_complete 0 -> 1, debrief, dlgHype; no STOP.
- zsr (`port/test-hooks/state`, 8 missions): in use 17,209,428 B at return 1, then 17,209,524 B at returns 2-8;
  no STOP.
- z2def (default build, no hooks): boots to dlgMenu (then the attract dlgHype); no STOP.

## Not written / next
- CAiSBreach (Tick 0x2d8000, GetStatus, OnSignal), AddBreachMember 0x2d3540, OnCommand's breach cases and
  CSealUnit::IssueCommand's breach part.
- CAiSDeploy (Tick 0x25d110, CanDeployItem 0x25e190, OnSignal 0x25e290), GetPutativeFirePointW 0x274800, OnCommand
  DEPLOY 0x281a80, CTFireWeapon Begin / Tick, the kit's deploy-state projectile (+0x54); then their gate entries.
- The empty task bodies listed under "State"; items 2-5 of the plan as in part 1's list (throw arc, HandleSupport /
  ConfirmCommand, laser / flashlight, Hang_0, binoculars, the Parse functions, the network group).

# Part 3 (2026-11-14, socom-port-mod-zseal3): breach, deploy, tasks, orders, kit, single-player leftovers

Scratch `build/port/boot-mod-zseal3/` (untracked: NOTES.md, mine.txt, survey before / after, the scratch hook
`hook_zseal3.cpp` (fire-team breach / deploy orders), `pad_fire.txt`).

## State
- Partly done again: items 1-4 of the plan are written except the pieces listed under "Not written / next"; item 5
  (the task Parse functions) is started, item 6 (network) is not.
- `survey.py gamez/zSeal`: stub fences 139 -> 61 (48,768 -> 26,076 B); written 508,036 -> 530,748 B. `port: not
  written` placeholders 33 -> 30. The task bodies the survey counted as written while empty (CTFireWeapon, CTAction,
  CTMap, CTPaint, CTSpecial) are written.

## Written (ELF addresses)
- Breach: `CAiSBreach` Tick 0x2d8000 / GetStatus 0x2d8b60 / OnSignal 0x2d8c20 (96-byte layout in zai.h),
  `AddBreachMember` 0x2d3540, OnCommand's breach cases 0x282574, CSealUnit::IssueCommand's breach template
  0x2d1a40 (the door under the source's reticle, its AI map action and cell, the target 9 over the cell centre).
  Phases: stack places (m_locEx 0-2), the leader waits for all (10 s), the door is opened (STATE_ACTION) when shut,
  the opener throws (STATE_DEPLOY: flashbang 123 / frag 121), all enter (m_locEx 3-5) shouting; breach valve 1 / 2 / 3.
- Deploy: `CAiSDeploy` Tick 0x25d110, CanDeployItem 0x25e190 (bool), OnSignal 0x25e290 (100-byte layout),
  `CZSealBody::GetPutativeFirePointW` 0x274800, OnCommand DEPLOY 0x281a80; CZKit::Fire / HandleRemotePlaceExplosive
  keep the projectile in the deploy state (0x2adc9c / 0x2a734c).
- IssueCommand's remaining cases: ACTION (first AI acts, the others follow it), FOLLOW for escortees (unit 17),
  AMBUSH (ambush direction, hold / hold fire), COVERTARGET, LASETARGET / DEPLOY (first member or sub-unit allowed);
  OnCommand ACTION 0x28240c, AWARE 0x2824b4, AWAKE 0x282588. CanPushAiState lets BREACH and DEPLOY through.
- Tasks: `CTFireWeapon` Begin 0x2bcfa0 / Tick 0x2bcd70, `CTAction::Tick` 0x2be2f0, `CTMap::Tick` 0x2ba710,
  `CTPaint::Tick` 0x2b9820, `CTSpecial` Begin 0x2b63d0 / Tick 0x2b6150 / End 0x2b62d0 (record layouts in
  seal_tasks.cpp); Parse (written, untested): CTFireWeapon, CTAction, CTSpecial, CTPursue, CTHold, CTComm, CTDoor.
- Orders and voice: `ConfirmCommand` 0x2d2030, `GetUnitLeaderHandle` 0x2d1f00, `HandleSupport` 0x2d2bd0,
  `GetSoundNameStringFromCmd` 0x2d2730, `GetUnitNameStringFromUnitNum` 0x2d2b10, the speech-recognition name maps
  0x2d22c0 / 0x2d24e0, `GetAwareCounter` 0x2cf180, `Update/ResetPointOutState` 0x2cf140 / 0x2cf110,
  `CheckPathProximity` (seal 0x2cead0, unit 0x2ce8d0, `_check_proximity` 0x2cece0; CAiSFlee uses it).
- Body / controller / kit: Raise/LowerBinoculars 0x273890 / 0x273800, Hang_0 0x275c40, Slide 0x29fea0,
  CheckForRegionTrigger 0x291710, CacheReticuleSeal, Get{Head,Leg,Arm,Body}Damage, TeleportTo(CMatrix),
  ResetAltitude, OnMissionEnd, ResetToInitialState, GetFP, compass anchors; CSealCtrl::OnWeaponEvent 0x288150
  (bullet-pass AI event and sound), TickRumbler 0x284180, PlayAiSound 0x287bd0; CSealCtrlAi OnMissionEnd,
  ResetToInitialState, PutAiLog, SetAiLogEnabled, SetAiAccuracyAngle; kit TickLaserDesignator 0x2a90a0,
  FetchLaseTarget 0x2a9360, TickFlashlight 0x2aa4e0, HandlePlacingExlosive 0x2a94f0, FireGrenade, FireCur,
  GetAmmoIndex (int), GetItemIndex(SEAL_ITEM), EmptyAmmoCountTotal, PendingPickupHandled; the squirm controller's
  ctor / Initalize / empty handlers; CHandSignal ctor; CSealStats::GetPointsEarned.

## Outside zSeal (small in-place edits, free at HEAD)
- `zAI/zai.h`: CAiSBreach and CAiSDeploy members, `CAiMap::region::Contains` declaration.
- `zAI/ai_mapdata.cpp`: `CAiMap::region::Contains` 0x19e020 (was missing; HandleSupport / AllowCommand EXTRACT).

## Findings
- The breach template must be Reset to STATE_BREACH once (the ELF's init block): without it the members' copied
  state type is 0 and the leader's breach state is never found (abort).
- Only actions whose AI map record has `m_locExValid` can be breached (AllowCommand); in m8 these are the depot,
  tri, dredge, outbuilding and shack doors (not the outhouses). An enemy inside often opens the door first; the
  OPEN phase then goes straight on.
- The second member aborts once the leader's breach ends (its leader's state is gone): ELF behaviour.

## ELF quirks kept
- The breach Debug line names the previous phase; the throw point tables of GetPutativeFirePointW are zero CPnt3Ds
  (a throw starts at the node's origin); the ACTION confirmation name is overwritten by the order's own; the leader
  handle search never reaches the sub-units; TickLaserDesignator calls CSnd::PlayErrorSound when the finish sound
  exists; CheckPathProximity starts every leg at the path's last point; Hang_0 from crouch / prone answers no blend.

## Port deviations
- NULL tests where the ELF writes through a state that may be another one (the BREACH / DEPLOY / ACTION / GOTO
  pushes, the kit's deploy projectile) and on the breach leader and the reticle's door action.
- GetSoundNameStringFromCmd's default passes the command name past "CMD_" where the ELF passes a char as `%s`.

## Runs (tree = HEAD 0266b548 + mine.txt; screenshots under `build/port/screenshots/45-zseal/`)
- zb1 (`hook_zseal3.cpp`, -DDEPLOY_AT): the fireteam is ordered DEPLOY 122 at a point 80 ahead of the player:
  DiMone takes it ("I can see it from here", prefire, DEPLOY_FIRE), throws the smoke grenade, waits for its fuse,
  DEPLOY_COMPLETE; the smoke cloud stands at the aim point (deploy-smoke screenshot).
- zb5 (`hook_zseal3.cpp`, -DBREACH_AT, door_outbuild01, enemies asleep): BREACHBANGCLEAR: the template is set,
  Bailey leads, DiMone opens; both route to their stack places (STACK), WAIT, OPEN (Shed2 inside had opened the door
  already), DiMone throws the flashbang (STATE_DEPLOY 123), ENTER to the entry cells, CLEAR with shouts, Bailey END
  (valve 2); the team HUD shows BREACHING / DEPLOYING (breach-stack screenshot). No STOP.
- zst4 (part 1's `hook_zseal.cpp`, pad with R1 fire): m8 for 160 s, no STOP; firing with recoil 0.4-0.7; kills,
  respawns (OutPatrol1 / 3) and recycling (OutPatrol2 / 4 / 5, Help1, Alarm1-3, LeaderBud1, Rush1); the team follows
  (Hutchins 15, DiMone 32); heap use 22.69 -> 22.82 MB, flat (22.817 MB) over the last 90 s.
- zw3 / zw4 (`port/test-hooks/win`, -DSOCOM_HOOK_WIN; zw4 on HEAD e06077e4): extract 0 -> 1, mission_complete 0 -> 1, "EXIT: debrief open
  (objectives 3/7)", IsMissionSuccessful, X (StatsProgress 100), menu: the same objectives and lines as the zFTS
  reference run zfw1 and zGrid's zg4 (3/7; "MISSION SUCCESSFUL" is debrief text, never a log line in any of them).
  The debrief shows MISSION SUCCESSFUL with the per-seal counters (win-debrief screenshot).
- zsr3 (`port/test-hooks/state`, 8 missions, tree on 0266b548): in use 17,836,340 B at return 1, then 17,836,436 B
  at returns 2-8 (flat); no STOP.
- z4def (default build on e06077e4, no hooks): boots to dlgMenu at 16.5 s; no STOP.

## Not written / next
- The throw arc of CSealCtrl::PostTick and the ai line drawing (DrawLine, LineTo; seal_ailines.cpp): they need
  zRender's RenderLineWorld (not in the port; zRender is another worker's module).
- FootInSpace (TurnSetup's foot IK; needs the `seal_foot_bone` static), sealSaveFireModes (CSavedFireModeInfo's
  layout), CTPlay::Create, get_param / get_state_fixup / ftmask_create (Parse helpers), RemoveAmmo /
  RemoveItemAndAmmo (network callers only), the IssueCommand unit-17 escortee hand-over, OnCommand LASETARGET
  0x281148.
- Task Parse functions still returning NULL (26): ai::WAIT, VALVE, TEAM, INREGION, INRANGE, STOPALL, STATE,
  STANCE, SOUND, SIGNAL, SETANIMSET, SETMODE, SELECT, ANIMATE, PARAM, PAINT, MOVE, MAP, MACRO, LOOKAT, INVIEW,
  INSTATE, GOTO, FIREMODE, EVENT, DEBUG (the m8 scripts are compiled: none runs offline).
- The network group (item 6): ghosts, piggy-back, remote AI / respawn / seal creation (RemoteRespawn,
  AcquireRemoteAi, SetAiNetState, NetworkPlayerCreate), the MP bomb (InitMPBomb, TickMPBomb, Drop / Pickup /
  HandlePlace), net pickups (HandlePickupAck, CheckForAmmoPickups, CanPickupNetItem, CreateNet*Pickup,
  FillNetworkAmmoPickupValues, RemotePickupItem), damage replication (Set*Damage, RemoteWeaponDamage*), MP stats,
  UpdateMvpScore, CreateMultiPlayerUnits, Revive, PlayRemoteMsg, Destroy (remote seals), the squirm PreTick.

# Part 4 (2026-11-14, socom-port-mod-zseal4): single-player leftovers, the throw arc, the task parsers, the other gameplay modules

Scratch `build/port/boot-mod-zseal4/` (untracked: NOTES.md, mine.txt, the surveys before / after, the scratch hooks
`hook_zseal4.cpp` (throw arc, ammo message, census), `hook_zseal1.cpp` (part 1's stability hook with team traces),
`hook_escort.cpp` (generated by `mk_escort.py` from `port/test-hooks/win`: the escort walking test), the Parse
writers `pparse.py` / `parse_b*.py`).

## State
- `survey.py gamez/zSeal`: stub fences 61 -> 35 (26,076 -> 21,888 B); written 530,748 -> 534,856 B (the survey
  counted the 26 task Parse functions as written while they returned NULL: they are written now, about 13 KB).
  `port: not written` placeholders 30 -> 18 (left: network, the AI log, ladders, the aim-anim list).
- zValve 8 -> 0 stubs (3,160 B), zWeapon 8 -> 0 (2,044 B), zCharacter 6 -> 0 (2,120 B), zEntity 18 -> 0 (1,520 B),
  zBody 2 -> 0 (384 B); `OrdersMenu::HandleRecoCmd` written.
- Not done: most of the network group (see "Not written / next").

## Written (ELF addresses)
- Single player: `FootInSpace` 0x2a4dd0 (TurnSetup's feet; the `seal_foot_bone` static 0x450d30 = 1.09, in seal.cpp
  beside turnV), `sealSaveFireModes` 0x2afad0 with `CSavedFireModeInfo` (8 bytes, ctor 0x2afba0; the array typed),
  `CTPlay::Create` 0x2b7dd0 (answers the record), `get_param` 0x2b96a0, `get_state_fixup` 0x2bbc70, `ftmask_create`
  0x2a4bf0, OnCommand LASETARGET 0x281148 (lase targets: AiMaps names of type 3; m8 has none), the squirm controller's
  PreTick 0x2e24f0, CSealCtrlAi::Initalize's mode byte 0x26af90, InitAiBrain's inline ClearRoute 0x26a964, its hostage
  branch 0x26abdc (team 0x20000: restrained in a network game, restrainable offline with bit 0x80000000, an ESCORTEE
  compass anchor) and on_respawn 0x26ad40, `CAiDodge::Destroy` 0x2df040 (the list typed; nothing creates a dodge),
  PerformReticleActions 0x2851f0 / OnActionButton 0x2849e4 (the escortee orders FOLLOW / HOLD POSITION via unit 17),
  CSealUnit::IssueCommand's unit-17 hand-over 0x2d0d28, PickupAmmo's ammo messenger line 0x2a64b4, CTRegion's pickup
  mode 0x2b4ccc, ComputeVisibility's particle-system volume 0x2b0204 (a smoke cloud's bbox x its emitter's density).
- Lines: `ai::DrawLine` 0x2e2f90, `LineTo` 0x2e3110, `MoveTo`, `Push/PopLineColor` (ai::color_stack, an MSL list of
  CPnt3D starting with (127, 0, 0)), `Set/GetLineOpacity`, `SetLineFuncOpacity` (both); `ai::DrawFunc<CDynGrenade>`
  0x2889a0 and `CDynGrenade` (28 bytes; ComputeMaxVel 0x2879f0, ComputeElevOfs 0x287980, ComputeTimeToImpact
  0x287930) in seal_control.cpp; CSealCtrl::PostTick's throw arc 0x2874b0.. (yellow, 100 segments, t = -1 to twice
  the time to the ground, opacity 0.75 -> 0.1).
- Tasks: all 26 remaining Parse functions (WAIT 0x2b4300, VALVE 0x2b4510, TEAM 0x2b4b40, INREGION 0x2b5260, INRANGE
  0x2b55d0, STOPALL 0x2b5750, STATE 0x2b5bd0, STANCE 0x2b6010, SOUND 0x2b6840, SIGNAL 0x2b6d60, SETANIMSET 0x2b7130,
  SETMODE 0x2b73a0, SELECT 0x2b74b0, ANIMATE 0x2b7c40, PARAM 0x2b93d0, PAINT 0x2b98d0, MOVE 0x2ba460, MAP 0x2ba8a0,
  MACRO 0x2bacd0, LOOKAT 0x2bb1c0, INVIEW 0x2bb800, INSTATE 0x2bbb00, GOTO 0x2bc910, FIREMODE 0x2bd3a0, EVENT 0x2bd860,
  DEBUG 0x2bdc90): written, untested (m8's scripts are compiled). `CAiMap::region::GetTypeName` 0x2b9aa0 is a
  file-local helper (zai.h declares none).
- zValve: `ParseOperator` 0x2f8170 (static; the old body tested strcmp without `== 0` and had the wrong numbers),
  `ParseValveName` 0x2f8070 (answers the valve), `CmdParseCmp` 0x2f7930, `Destroy` 0x2f6860 (~CNodeAction: the valve
  becomes temporary and loses its callbacks), `~CValve` 0x2f7690, `CValveSaveManager::Serialize` 0x2f73a0 /
  `UnSerialize` 0x2f72b0, `debugValve` 0x2f8730 (no effect).
- zWeapon: `UpdateGrenade` 0x3173b0, `ReportGrenadeStatus` 0x3174f0, `HandleShotgunImpact` 0x3185d0,
  `NetRemoveProjectile` 0x31aae0, `CZProjectileList::Clear(int)` 0x31b110, `~CZWeapon` 0x31f640 (the names and hit
  anim tables freed), ZWepReader ctor / dtor.
- zCharacter: `GetBaseName` 0x2477e0, `RdrFetch_CharacterType` 0x247880, `match_name_to_chartype` 0x247940,
  `InitMultiplayerMessages` 0x247c30 (Parse calls it offline; `MultiplayerMsgStrings` typed CSTable(0, 1024)),
  `UnPack` 0x24ada0 (static), `KorusGetPackedWeapons` 0x24aea0, `CCharacterWeapPacked` (6 bytes).
- zEntity: `ComputeNextPosition` 0x1f1e70, `UpdateNextPosition` 0x1f1e20, `RefreshAwareCounters` 0x1f0220 (live: the
  AI pre-tick calls it), the empty ticks, `UpdateAiMapLoc` 0x1ee3e0, pickup net ids (`FindNetPickup` 0x24c610,
  `IsNetIdUsed` 0x24c6c0 static bool, `DestroyNetPickups` 0x24cc00, `DebugPickups` static, `GetPickupNetEntityID`,
  `GetEntityIDFromNetID`), `~CEntityCtrl`.
- zBody: `~CZBodyAnimCallbackList` 0x1df480 (Clear inlined), `~CZBodyAnim` 0x1df5b0.
- `OrdersMenu::HandleRecoCmd` 0x176e60 (voice orders: the recognized words fill the menu's columns; surrender / get
  down AI events 10 / 11 without the menu; a complete order is confirmed and issued).
- Network (part): `CSealStats::UpdateMvpScore` 0x24e610, `MPBomb_TimerAvailable`, `Get/SetMPStats` with `MPSealStats` (10 bytes), `DropMPBomb`,
  `RemoteDropMPBomb`, `HandlePickupMPBomb`, `GetProximityMPBomb`, `RemoteWeaponDamageNonVictim`, `CZKit::RemoveAmmo`
  0x2a5a80 / `RemoveItemAndAmmo` 0x2a5830.

## Outside zSeal (small in-place edits, free at HEAD)
- `zTwoD/c2dline.cpp`: `clip3DLine(planes, ...)` 0x2ffc20 used the near-plane point as a normal, so every world line
  was clipped away; now as the ELF (the near plane through NearPlanePoint, the four sides through the view point).
- zValve, zWeapon, zCharacter, zEntity, zBody and `Apps/FTS/game/orders.cpp` as listed above.

## Findings
- CTSound's record (ai::SOUND) is a bit word at +8 (wait, sitrep, broadcast, a 4-bit aware limit, pending, the names
  count, the values count): the port's Tick read +8 as one byte and +0xa as the count; m8's compiled ai::SOUND
  records use the ELF layout, so Tick now reads them right (fixed with Parse).
- Snow3 (Pincushion) is m8's only team-0x20000 seal; it now gets its ESCORTEE compass anchor at brain init.
- The AI aware counters are refreshed every AI pre-tick now (RefreshAwareCounters).

## ELF quirks kept
- The throw arc starts at t = -1 (behind the hand) and runs to twice the time to the ground computed from the hand's
  body-space height; its landing point is computed and not used. The AI lines use the matrix stack's top (the ELF
  pushes an identity for them at static init: port: the stack base is the identity).
- sealSaveFireModes reads the slot's weapon id through NULL for an unwrapped index (port: 255); CTWait::Parse draws
  its timer twice; CTDebug / CTSignal / CValve::CmdParseCmp leave the record's command type to the loader; CmdParseCmp's
  operand keeps the valve's input index when the operand names a plain valve; CTSound::Parse copies its names from the
  first m_num_names values only; CTGoto::Parse reads "timer" and drops it; CTLookAt's "dbnode" finds a node and drops
  it (port: not looked up); get_state_fixup maps "reloading" to STATE_PATHRECO like "path reco".
- RefreshAwareCounters clears each entity's counter when its own turn in the entity list comes, so what the entities
  before it added is lost.
- PickupAmmo compares the new ammo name with the last messenger line (a wrapped name's last line), so a long ammo
  name is shown again for every pickup.

## Port deviations
- NULL tests: the reticle-seal and source tests of the unit-17 hand-over, the deploy state of LASETARGET, the restrained
  state of the hostage branch, the escortee anchor, Remove(Item)Ammo with no items, a missing PARAM / MP values.
- CTRegion's pickup mode reads the pickups' data through raw offsets (types 4-7 have no port names).
- CTLookAt::Parse's "dbnode" lookup is left out (no effect in the ELF).

## The escortee (Snow3 / Pincushion): ELF check and walking test
Standard: the reference ELF's code. Compared instruction by instruction: CSealCtrlAi::OnCommand's FOLLOW case
(jump-table entry 4, 0x2820a4), `CSealUnit::EscorteeJoinUnit` 0x2d67a0, `CSealCtrl::AllowCommandFOLLOW` 0x283350,
`CAiSFollow::Tick` 0x2e1d80, the escortee parts of `FollowTick` 0x2df1c0 (the give-up at 0x2df21c, "wait up" at
0x2dfb9c), `HandleFollowTickHideCheck` 0x2e1510, `HandleFollowTickStance` 0x2e12a0, `CSealCtrlAi::PostTick`'s rescue
0x268704, `CAiSRescued::Tick` 0x2592f0, CSealUnit::IssueCommand's CMD_ESCORT 0x2d0ef8.
- Matches the ELF: all of the above, except one difference fixed: OnCommand FOLLOW clears its "already following"
  flag in a delay slot (0x28210c) whenever an escortee joins, also without a source unit; the port cleared it only with
  a unit (no visible effect: a source always has a unit).
- Constants checked against the ELF's data (FollowTick's function statics, set on first use): lostFollowThreshold
  90000 (300 units), SLOP 15, waitUpLengthSquared 10000 (100 units), waitUpTimer -1, waitUpResetTime 10 (then + up to
  5 s at random), a_followMultiplier 0.2 (unused), a_pathMultiplier 0.1, b_acceptablePathSlop 3, acceptablePathDelta 5
  (unused), a_numPathLocsThreshold 10, a_maximumUnplannedLocs 15, acceptableMinPathLocs 7; HideCheck's distanceSQ 4200
  and HutchinsDistanceSQ 1600. The follow-mode jump table (0x457c30, 10 entries) is in the port's case order.
- What the ELF makes the captive do: the ESCORT order goes to the seal under the reticle, which joins the unit as an
  escortee and is ordered FOLLOW by the unit's first seal (unit 1 hands it to Bravo: "follows Bailey") with the
  default offset (15, 0, -15); a follower whose master is dead or whose follow error passes 300 units gives up with
  HOLD POSITION (an escortee only); a non-SEAL (handle 0) calls "wait up" (character sound 47) when its goal is more
  than 100 away, at most every 10-15 s (one timer shared by all followers); moving it stands, stopped it takes the
  master's stance; inside a type-1 region (Extract) while following it becomes RESCUED.
- Port deviations on this path: CMD_ESCORT skips an empty unit and NULL-tests the reticle seal (the ELF reads the list
  head / through NULL; not visible: the player's unit is never empty); FollowTick returns after the NULL-master
  HOLD POSITION (the ELF goes on reading the NULL master); CAiSRescued phase 6 NULL-tests the SUSPENDED state (the
  ELF writes through NULL when the push did not land on top). None changes what the player sees in m8.
- Not verified: the generic route following of FollowTick (its other ~7 KB, the same for every follower) and the
  sensors / CanScan of a restrained AI.
- Walking test (scratch `hook_escort.cpp`, from the win hook with -DESCORT_WALK; the player walks by pad along AI-map
  routes): restraining Snow3 before he has surrendered races his surrender reaction: the ReceiveRestraints blend runs
  on with a cleared m_carry and CZSealBody::PostTick (0x25519c..) copies the NULL carry's matrix (the ELF has no test
  either), so the hook now waits for his surrender. Given right after the hook's teleports, the ESCORT gives up at once
  (FollowTick 0x2df21c: the follow goal lies on the player's trail, which still holds the teleports: error 651 > 300)
  and the same FollowTick call goes on (as the ELF does) to plan a route to that goal: the restrained captive runs off
  at full speed and stops there. After the player has walked a fresh trail, a new ESCORT order holds: the captive
  follows (FOLLOW, route mode), 80-290 behind the player over about 1,400 units of open ground, calls "wait up" (twice
  in 60 s), stands while moving and crouches when stopped (hiding). The run ended about 90 short of Extract, so the
  rescue was not seen from a walk (the win hook's rescue after its teleport still works: zwin1).

## Runs (tree = HEAD c1b25067 + mine.txt; screenshots under `build/port/screenshots/45-zseal/`)
- zs4c (`hook_zseal4.cpp`): M67 held on R1: the yellow throw arc is drawn (76 of 101 segments past the clip each frame,
  after the c2dline fix; before it no line passed); a test ammo pickup puts "5.56 x 45mm NATO SD" in the ammo
  messenger; Snow3 gets the ESCORTEE anchor; m8 has no lase targets (throw-arc screenshot).
- zs4st3 (part 1's hook with team traces, pad_fire.txt, 235 s): no STOP / TLB miss; firing, kills, recycling and
  respawns; the team follows (Hutchins 32, DiMone 49 at the end); heap in use 23.34-23.52 MB over the last 90 s.
- zwin1 (`port/test-hooks/win`, -DSOCOM_HOOK_WIN): mission_complete 0 -> 1, "EXIT: debrief open (objectives 3/7)",
  IsMissionSuccessful; MISSION SUCCESSFUL on the debrief (win-debrief-part4 screenshot).
- zs4sr (`port/test-hooks/state`, 8 missions): in use 18,660,356 B at return 1, then 18,660,452 B at returns 2-8
  (flat); no STOP.
- zs4def (default build, no hooks): boots to dlgMenu at 16.9 s.
- zesc1-3 (`hook_escort.cpp`): the escortee walking test (see its section).

## CRemoteCtrl::PreTick (zInput, 0x2ce310, 932 B): what it needs
It is a remote (network) seal's controller tick: the network clock (`CZNetwork::zNetGetTime`) and an exponential
smoothing factor (`sm$2347`, `expf`), then the seal's node is moved toward the last received network state (position
interpolation `CPnt3D::Interp`, `SetPosition`, `ResetAltitude`, orientation `CQuat::SlerpFaster`), its aim
(`AimWeapon`, `SetAimDirR`) and, when the state says it fires, `GetFP` + `CZKit::FireCur`. It reads the received state
kept in CRemoteCtrl's own members (the network seal state copied in by zNetwork) rather than CSealCtrl's; it needs
CSealCtrl's base members only as every controller does (`m_entity`). Not written (not short; network only).

## Not written / next
- Network group (untested once written): ghosts (Make/UnMakeGhost), piggy-back camera (Advance/RetreatPiggyBack),
  remote AI / respawn / seal creation (AcquireRemoteAi, Set/GetAiNetState, RemoteRespawn, CreateRemoteSeal,
  NetworkPlayerCreate, Destroy), the MP bomb (InitMPBomb, TickMPBomb, CreateMPBombPickup, PickupMPBomb,
  HandlePlaceMPBomb), net pickups (HandlePickupAck, CheckForAmmoPickups, CanPickupNetItem, CreateNet*Pickup,
  FillNetworkAmmoPickupValues, RemotePickupItem), damage replication (Set*Damage x6, RemoteWeaponDamageVictim),
  CreateMultiPlayerUnits, Revive, PlayRemoteMsg, the Dump debug functions, CRemoteCtrl::PreTick.
- Single-player placeholders left: the ladder tick (0x266320; m8 has no ladders), the AI log (CAiLog), the aim-anim
  list (never filled in the ELF).

# Part 5 (2026-11-14, socom-port-mod-zsealnet): the network group, CRemoteCtrl::PreTick, the last placeholders

Scratch `build/port/boot-mod-zsealnet/` (untracked: NOTES.md, mine.txt, the surveys before / after, the stub
disassembly `asm/`, the escort walking test generator `mk_escort2.py` (+ `case20.txt`) and its hook `hook_escort2.cpp`,
`buildall.sh`, the edit file `edits/znet_h.txt`).

## State
- `survey.py gamez/zSeal`: stub fences 35 -> 0 (21,888 -> 0 B); written 534,856 -> 556,744 B. `gamez/zInput`: 0 -> 0
  stubs (11,940 B), but `CRemoteCtrl::PreTick` was a placeholder returning 1: written now.
- Lines marked "not written" in zSeal + zInput 34 -> 9, "port: stub" 3 -> 1 (left: see "Not written / next").
- Everything network-only is written, untested (no network game on the demo disc); the offline game is unchanged
  (each network branch tests `theNetwork.m_bNetwork` as the ELF does; UpdateLocalSeal returns at once offline).

## Written (ELF addresses)
- Damage replication: `Set{Body 0x290990, Head 0x290850, LArm 0x2906f0, RArm 0x290590, LLeg 0x290430, RLeg
  0x2902d0}Damage` (the part's wound level from the network: health = the level's share of the maximum less 0.01,
  then UpdateHealth), `RemoteWeaponDamageVictim` 0x290aa0.
- Net pickups: `FillNetworkAmmoPickupValues` 0x28d900, `CheckForAmmoPickups` 0x28cdb0, `CanPickupNetItem` 0x28d0a0,
  `CreateNetAmmoPickup` 0x28d230, `CreateNetWeaponPickup` 0x28d590, `HandlePickupAck` 0x28c5c0, `RemotePickupItem`
  0x28dba0, and the network branches of DropAmmo 0x28e9c0, DropItem 0x28e6c8, HandlePickupEquip 0x28e2f0, PickupItem
  0x28dfbc, CZKit::PickupAmmo(CPickup *) 0x2a66a4; `CPickup::NetworkCreate` 0x24d200 (zEntity).
- MP bomb: `CreateMPBombPickup` 0x28c230, `CSealCtrl::InitMPBomb` 0x283750 / `TickMPBomb` 0x2838f0, TickPickups' bomb
  part 0x2854cc, `CZKit::PickupMPBomb` 0x2a6900 / `HandlePlaceMPBomb` 0x2a6b30.
- Remote seals: `CreateRemoteSeal` 0x289480 (the CRemoteCtrl ctor is inlined there: zinput.h has it inline with the
  trivial virtuals OnDeath 0x2ce1d0, GetRemoteControl 0x2ce1c0, IsPlayer 0x2ce1f0, IsRemote 0x2ce200, OnStunDamage
  0x2ce1e0; the dtor 0x2ce160 is in remote_control.cpp), `RemoteRespawn` 0x288cb0, `Destroy` 0x2898b0,
  `CSealCtrlAi::GetAiNetState` 0x2682e0, `CRemoteCtrl::SetAiNetState` 0x2680d0, `AcquireRemoteAi` 0x267f00,
  `NetworkPlayerCreate` 0x24db80, `MakeGhost` 0x24da30 / `UnMakeGhost` 0x24d8f0, the spectator camera
  `AdvancePiggyBack` 0x24f180 / `RetreatPiggyBack` 0x24f050, ~CZSealBody's network branch 0x2570f8 (with
  `CEntity::deletedId` 0x44cd78 = -2), the remote branches of AllowCommandFOLLOW 0x283474 / AllowCommandHOLDPOS
  0x2831b8.
- Units and messages: `CSealUnit::CreateMultiPlayerUnits` 0x2d4a40, `Revive` 0x2d63a0, `PlayRemoteMsg` 0x2cf330,
  IssueCommand's radio units and voice channels 0x2d0924, OnDeath's voice-unit order 0x287cf8, CZKit::Fire's network
  messages 0x2ad1d4 and SaveFireMessage 0x2adda0, PostMortemPreTick's `theVoice.m_block_talk` 0x283fd0.
- `CRemoteCtrl::PreTick` 0x2ce310 (zInput): once per network clock tick the smoothing factor exp(-dT x the net game's
  m_pos_smooth); the node takes the received opacity; more than sqrt(1000) from the received position the seal jumps
  there, else moves toward it by the factor (the received height kept); the orientation slerps toward the received
  one by min(2 x factor, 1); the aim from the received fire elevation; one replayed round per frame while
  m_RemoteRoundCount lasts (GetFP, FireCur). It reads CSealCtrl's own members (m_remote_goal_pos / quat,
  m_ai_net_state), nothing new in CRemoteCtrl.
- Debug / AI log: `CSealCtrl::Dump` 0x2694f0 (no effect: the printing is compiled out), `CSealCtrlAi::Dump` 0x269430,
  `GetAiLog` 0x26be30 ("<database>.ailog", header records 32 / 33), the per-frame log record of PreTick 0x267674.
- Single player (untested, m8 has no ladders): `CSealCtrlAi::LadderClimbTick` 0x266320 (states 0-3: to the ladder,
  creep on, climb up / down by the next point's height, off). Also CSealCtrlAi::Tick's and CSealCtrlSquirm::Tick's
  UpdateLocalSeal calls (0x2693e8, 0x2e24d0).
- `GetFP` returns bool (0x2bf820; PreTick tests it).

## Outside zSeal / zInput (small in-place edits, free at HEAD)
- `zEntity/pickup_main.cpp` (NetworkCreate), `zEntity/zentity.h` (GetRemoteControl answers CRemoteCtrl *; deletedId),
  `zEntity/ent_main.cpp` (deletedId).
- Edit file for zNetwork (owned by another worker): `znet.h` friends CSealCtrl (m_block_talk) and CSealUnit
  (m_isOn / m_isOn_save).

## Findings
- The AI net state word (CSealCtrl +0xe4; no DWARF type, the ELF copies a 4-byte local with memcpy): byte 0 the top AI
  state; bits 8-23 the follow master's id (FOLLOW: m_master; RESCUED: the state's master); byte 3: bits 0-3 the node's
  transparency (15 x (1 - opacity), 15 when off), bit 4 m_restrained, bit 5 the hostage compass anchor, bit 6 the ghost
  flag. zseal.h `SealAiNetState` (names invented).
- `AckUnion` is one byte of bits (ammo box entry i = bit i, a weapon = bit 0). The zFTS pickup packets' "host" field is
  the item count; PickupMayI's "type" is the asking seal's id.

## ELF quirks kept
- RemoteWeaponDamageVictim resolves the hit on the body again after the part (its flag is set to 1 and only re-set to
  1); SetHeadDamage(4) gives 0.7 of the maximum; CanPickupNetItem runs its check once per item on the same pickup;
  CreateNetWeaponPickup does not add the model to the world; CreateNetAmmoPickup leaks the record without a model;
  CreateMPBombPickup answers 0 when told to make no pickup; the ammo entry readers read an index equal to the size;
  PlayRemoteMsg's two side colours are the same call; CreateMultiPlayerUnits and SetAiNetState ask for the player and
  drop the answer; NetworkPlayerCreate clears the name's 31st character; LadderClimbTick's ladder normal is overwritten
  and unused.

## Port deviations
- HandlePickupAck: entries past the box's end read as none; NetworkPlayerCreate: a PLAYERNAMEVAR that is no string gives
  an empty name (the ELF copies from NULL); HandlePickupEquip: the seven unused asked items are 0 (stack garbage in the
  ELF); NetworkCreate answers NULL while the pickups are closed (the ELF writes the net id through NULL);
  RemotePickupItem bounds-tests the item model slot; CZKit::PickupAmmo asks for at most 8 entries (the packet's size).

## The escortee's rescue from a walk (part 4's open check)
- Scratch hook `hook_escort2.cpp` (generated by `mk_escort2.py` from `port/test-hooks/win`, -DSOCOM_HOOK_WIN
  -DESCORT_WALK): the win flow up to Snow3's restraint, the player facing him (teleported, as the win hook does), then
  no more teleports: a walked trail (40 + 40 units by pad, the ELF's FollowTick gives up at once on a trail that still
  holds the teleports: err 572-685 > 300, CMD_HOLDPOS, seen again in zne2 / zne4), CMD_ESCORT to the fireteam (the
  captive as the reticule seal), and a pad walk into Extract along the line a routed walk had taken (waypoints).
- zne6 (tree = HEAD ae072df3 + this part): the order holds ("escort Snow3 (follows Bailey)", then the player's FOLLOW);
  the captive follows 15-311 behind over about 1,100 units, calls "wait up" (sound 47) twice; at 312.2 s, with the
  player at the last waypoint but one and the captive entering the region while following: "AI: Snow3 rescued in
  region Extract (master player)", PlayMPEG `run/movies/m8/extract.pss` (the extraction movie), the extract valve 0 ->
  1, mission_complete 0 -> 1, the debrief: "EXIT: debrief open (objectives 3/7)", MISSION SUCCESSFUL on screen. No
  code was changed for this: the ELF path (part 4's comparison) works from a walk.
- Hook findings (not game behaviour): a pad walk straight at Extract's centre sticks on the terrain north of the Bosler
  house; ai::PathPlanImmediate to Extract sometimes answers 12 points, sometimes none, from the same cell.

## Not written / left (zSeal, zInput)
- The aim-anim list (seal_env.cpp, CZSealBody::m_aim_anims): left as the ELF has it - nothing in the ELF fills it.
- Single-player gaps outside this part's brief, still marked in the source: ChooseLookDir 0x2597a0 and the idle look
  (seal_ai.cpp), the AI-state push gate (seal_aistate.cpp: the states without a Tick), DropBody's DetachBody
  (seal_body.cpp), the peek ray test 0x286f70 (seal_control.cpp), CTMap's cell flags 9 / 10 (seal_tasks.cpp), the
  _diPool destructor at exit (seal_sensors.cpp).
- Everything of this part that is network-only is untested (no network game on the demo disc).

## Runs (tree = HEAD ae072df3 + this part; screenshots under `build/port/screenshots/45-zseal/`)
- znst (part 1's stability hook with team traces, pad_fire.txt, 270 s): no STOP or exception; firing, kills, recycling
  and respawns (OutPatrol1 / 3); heap in use 23.39-23.40 MB over the last 100 s. The team: DiMone follows to the end;
  Hutchins lost FOLLOW at 169 s when an enemy grenade's blast hit him in his PURSUE / GRENADE states (all his states
  popped, no new order), a path this part does not touch (the ladder tick answers 0 in m8: anims 46-48 are the ladder
  anims; the AI log is off; the rest is network-only).
- znw2 (`port/test-hooks/win`, -DSOCOM_HOOK_WIN): Snow3 rescued in Extract, extract 0 -> 1, mission_complete 0 -> 1,
  "EXIT: debrief open (objectives 3/7)", IsMissionSuccessful (its screenshots came out black: the display was off).
- zne6 (escort walk, above): MISSION SUCCESSFUL on the debrief (escort-walk-mission-successful screenshot).
- znsr4 (`port/test-hooks/state`, -DSOCOM_HOOK_MISSIONS=8: the hook's default is 4 now): in use 18,666,708 B at return 1,
  then 18,666,804 B at returns 2-8 (flat); no STOP.
- zsndef (default build, no hooks): boots to dlgMenu at 15.8 s.
