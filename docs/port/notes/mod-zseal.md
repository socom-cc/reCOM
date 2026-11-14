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