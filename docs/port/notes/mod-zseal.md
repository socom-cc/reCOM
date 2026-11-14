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
