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
