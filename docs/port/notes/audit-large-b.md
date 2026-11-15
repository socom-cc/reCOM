# Targeted audit of the large zSeal / zAI functions, list B (2026-11-15, socom-port-large-b)

Why: the random sample audit ([audit-sample.md](audit-sample.md)) found defects in 20% of the
marked functions of 700 bytes or more, concentrated in zSeal and zAI. List B is 73 such functions
(137,724 bytes) in `seal_ai.cpp`, `seal_aievent.cpp`, `seal_aifollow.cpp`, `seal_anim.cpp`,
`seal_control.cpp`, `seal_create.cpp`, `seal_dyn.cpp`, `seal_tasks.cpp`, `seal_unit.cpp` and
`seal_weapon.cpp`, audited largest first. HEAD 24f811a3.

Method as the sample audit: each function disassembled from `support/socom.elf` (`z.sh`, raw
`dis.sh` where a delay slot or an elided line mattered, `sym.py` for jump tables, statics and
vtables, `vt.py` for the `CSealCtrlAi` / `CSealCtrl` vtables, `denum.py` for `FT_COMMAND`) and
compared with the port's body instruction by instruction: branches and their sense (delay slots
read from the raw listing), stores (offset, width, bitfields), calls and their arguments, loop
bounds, signedness, return values, vtable slots, jump tables case by case, inlined helpers against
the port's helper, float words. Every NULL guard the ELF does not have was treated as a deviation:
removed unless the port provably reaches the path where the PS2 would not. The port runs on the
same emulated EE memory map, so a read through NULL behaves as on the PS2; guards on paths whose
reachability was unclear were first traced in test builds (below). No `@socom-anchor`,
`@socom-artifact` or `@socom-skeleton` marker was added, moved or changed; no function moved file.

## Progress

Rows 1-21 of 73 judged, in size order (82,428 of the 137,724 bytes, 60%): every function of
1,736 bytes or more. Rows 22-73 (the functions from `CSealCtrl::CSealCtrl` 0x288330, 1,648 bytes,
down to `CTLookAt::Tick` 0x2badf0, 700 bytes) are left for a follow-up session; their order is the
list sorted by size (ties by address).

## Counts (rows judged so far)

| Verdict | Rows |
|---|---|
| MATCH | 11 |
| DEFECT-FIXED | 10 (A 2, B 3, C 5) |
| DEVIATION-KEPT | 0 (two recorded deviations stay inside rows 4 and 12) |
| UNJUDGED | 0 |
| total | 21 |

Defect rate so far: 10 / 21 = 48% (95% Clopper-Pearson: 26% .. 70%); grade A or B: 5 / 21 = 24%
(8% .. 47%). Four of the ten are only port NULL guards the ELF does not have (rows 3, 4 and parts
of 1, 5, 7); without them 7 / 21 (33%) rows have a code difference. By bytes: the ten defective
functions are 48,848 of the 82,428 bytes judged (59%).

By kind: delay-slot reads (rows 1, 8: a store or assignment in, or after, a branch delay slot read
the wrong way), a NULL test that was in fact a pointer before the vector (row 5), a "port: left
out" whose reason no longer held (row 7: GetRegionTypeContainer is written now; row 6: exp_tl
exists), the wrong state written after a push (row 7), an end case (row 9), an iterator kept over
an erase (row 12), left-out stores (row 19), port NULL guards (rows 1, 3, 4, 5, 7).

## Fixes (ELF addresses)

- Row 5, `CSealCtrlAi::PathFollowTick` 0x264e20 (seal_ai.cpp), **A**: the point after the target is
  `data + count - 2` (0x264f48) even with one point left; it then lies before the vector, and the
  door test only rejects NULL. So the ELF opens a shut door on the last point of an extendable
  path (path app flag 1: a follower whose goal moves) and, past the last point, calls
  `CanTravelLine` with the word before the vector. The port made `next` NULL there: the door was
  not opened (the AI walked into it until STATE_PATHRECO) and the gone-past test was skipped. Now
  as the ELF. Traced in two m8 runs: the gone-past case was reached once (OutPatrol1, no harm), the
  door case not. Also the PATHRECO state is written through NULL when the push lands below the top
  (0x265844), as the ELF (the port tested it).
- Row 7, `CSealCtrlAi::AttackTick` 0x2626c0 (seal_ai.cpp), **A**: an engaging enemy (not a SEAL)
  standing in a guard region (type 6, `InGuardRegion` inlined at 0x263218) pushes STATE_TARGETING
  (stays and shoots) instead of STATE_PURSUE; the port left the test out as "GetRegionTypeContainer
  unwritten" (it has been written since). It also changes when the 1-in-4 `rand()` is drawn. The
  pushed TARGETING / PURSUE state is now written only when it landed on top (0x263344, 0x2633a0;
  else through NULL as the ELF); the port wrote the duration into whatever state was on top. The
  two `m_unit` NULL guards (0x2629b8, 0x263264; reason "CSpawners::Tick unwritten", stale) are
  removed; a traced run never met a unit-less attacker. Not reached in the traced runs (no
  "guard region" line): m8 may have no type-6 region in the fights the runs saw.
- Row 8, `CAiSPursue::Tick` 0x259930 (seal_ai.cpp), B: in the delay phase `li s0,1` sits in the
  delay slot of `bnez` (0x259c18), so a state whose look / cover flags (6) are already set moves
  on to plan keeping them. The port stayed in delay until the duration or the target ended. No
  traced run had preset flags.
- Row 9, `CTParam::Tick` 0x2b8230 (seal_tasks.cpp), B: a compare on parameter 0, 7 or 14 and up
  (table 0x454760 entries 0 / 7 and the bound test at 0x2b84c0) ends with v0 still 0: the task never
  completes. The port returned done.
- Row 12, `CSealUnit::Tick` 0x2cf7f0 (seal_unit.cpp), B: with no living member the escortees are
  told HOLDPOS, and the walk restarts at the list front after each one (0x2cfc64), because an
  escortee's HOLDPOS moves it to unit 17 (`SealJoinUnit` -> `SealLeaveUnit`), off the list. The
  port went on with `++it` from a node the call had just erased.
- Row 1, `CSealCtrlAi::FollowTick` 0x2df1c0 (seal_aifollow.cpp), C: COVERING stores the timer 0
  only when it is negative (0x2e0edc: the bc1f delay slot is a nop); the port stored 0 always (its
  comment claimed a delay slot). Masked: the end of the tick turns every other value into -3. The
  `m_master == NULL` return (port only) is removed: the ELF goes on after the HOLDPOS order; never
  hit in two traced runs.
- Row 3, `CAiSGrenade::Tick` 0x25af40 (seal_ai.cpp), C: guards the ELF lacks removed - the
  pickup's bit vector (0x25b32c; sized when the pickup is made) and the two CAiSAnimate writes of
  the throw-back phases (0x25c51c, 0x25c5a4; dead, `allowThrowbacks` is 0). The dead branch also
  printed "ClearRoute()..." twice (the inline `ClearRoute` prints it).
- Row 4, `CSealUnit::IssueCommand` 0x2d07e0 (seal_unit.cpp), C: guards removed - the escortee
  unit's source (0x2d0d28), ESCORT's reticle seal (0x2d0ef8), the breach order's reticle action
  (0x2d1c00 reads +0x2c); none hit in the traced runs.
- Row 6, `CharacterDynamics::Load` 0x28a560 (seal_dyn.cpp), C: `m_throtScale = 1 / (exp_tl(throt_exp)
  - 1)` (0x28a7f8); the port left out `exp_tl` (no reader of +0x11c in the ELF). The first-person
  bobbing values use their own local (sp+0x16c) and `stand_turn_factor` the shared one, which the
  tail's unconditional reads see when a key is missing.
- Row 19, `CSealCtrlAi::RegisterCommands` 0x2be630 (seal_tasks.cpp), C: every `AddCmd` result but
  SELECT's (+8) and SPECIAL's (+0xc) is stored in `ai_cmdid`'s first word (0x2be680 on), which ends
  as ai::WAIT's id - the type every Parse function gives its task header. The port left the
  stores out (headers typed 0).

## Kept deviations (recorded)

- Row 4: ESCORT into a unit without seals is skipped. The ELF then reads the first seal from the
  list sentinel (the escortee list's size word, used as a pointer); `front()` of an empty
  `std::list` is undefined in the port's library, so that read cannot be reproduced. Recorded in
  the comment.
- Row 12: with an empty dead list the escortee walk stops. The ELF takes its order source from the
  dead list's sentinel (the next member's word, not NULL); recorded in the comment.
- Kept ELF quirks (noted in the comments): FollowTick goes on with a NULL master after the HOLDPOS
  order; the escortee walk of row 12 never ends if an escortee stays on the list; PathFollowTick
  reads the word before the point vector; IssueCommand's unit-29 return is HandleSupport's v0.

## Runs

All on HEAD 24f811a3 plus the five changed source files (isolated tree; the other workers'
uncommitted files kept out). Focus kept in every run. Logs and screenshots are untracked
(`build/port/screenshots/59-large/`, files tagged `large-b`).

- Guard traces (test-only edits printing a line wherever a removed or changed guard's case
  occurs; `hook_zseal1.cpp` of zseal4 + `pad_fire.txt`, 230-240 s, two runs): only the row-5
  "gone past the last point" case occurred (OutPatrol1, once); FollowTick's NULL master, the
  unit-17 / ESCORT / breach guards, the PATHRECO write, a unit-less attacker, a guard-region
  engagement, a pursuit with preset flags, a never-ending param task and the door on the last
  point did not. Both runs stable (83 / 32 "fires at" lines, recycling, team following).
- Smoke run on the final tree (same hook and pad, 235 s): intro skipped at 76.9 s, 160 s in the
  mission; 25 "fires at" lines, 57 recycle / respawn lines, 34 follow-mode changes; no STOP, no
  exception; heap in use 23,102,844 .. 23,103,420 B from 200 s to the end (steady).
- Scripted win (`port/test-hooks/win`, -DSOCOM_HOOK_WIN): the first run (270 s) was slowed by
  another emulator running at the same time; an enemy sounded the klaxon alarm (SOBJ9 BRAVO COVER
  DREDGE failed), the C4 of the second crate was cut off by its cinematic and the 270 s limit ended
  the run at the hostage step. The rerun (380 s limit) went as before: three caches destroyed,
  Snow3 rescued in Extract at 209.0 s, "EXIT: debrief open (objectives 3/7)" at 214.9 s,
  `IsMissionSuccessful` asked by the debrief (the screenshots fell after the debrief, on a
  minimized window). The alarm of the first run is not reproducible run to run; the test script
  was not changed.
- Round trip (`port/test-hooks/state`, -DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4): in use
  18,657,260 B at all four returns (flat; HEAD's level, see menu-heap.md: 18,655,872 / 18,657,248);
  largest free block 3,956,736 B at returns 1-2, 4,214,784 at return 3, 2,584,576 at return 4 where
  the menu buffer went above the break (brk 0x1e93000, the original's behaviour); 2,994,176 /
  2,998,272 B at each mission start; no STOP.
- Default build (no hooks, no fake pad) of the final tree links; its boot was left to the
  coordinator's gate run (testing was lightened during the session).

`python tools/socom.py audit independence --strict` passes.

## Leads

1. Delay slots: two of the defects are a store or an assignment read on the wrong side of a branch
   (rows 1, 8). `cz.py` marks real delay slots with `|`; an instruction after a nop slot has no
   mark. The port comments that cite "delay slot" are worth a grep against the raw listing.
2. "port: ... unwritten / left out" comments (rows 6, 7): the reason may have gone away since
   (GetRegionTypeContainer, exp_tl, CSpawners::Tick). Grep the remaining ones and check the callee
   exists now.
3. Port NULL guards: many remain in the other zSeal files ("port: NULL-tested"). The runs here
   never met the guarded case; the same treatment applies.
4. `taskSeal` / `ai_cmdid`: with row 19 the task headers carry ai::WAIT's id at parse time; the
   zAnim parser's handling of a task header's type (overwritten or not after Parse) was not
   checked here.
5. The win-script runs (below): the playthrough timing varies with the emulator's load (other
   emulators running at the same time).

## Result table (size order; k = audit order, list = row of the list)

| k | list | Address | Bytes | Function | File | Verdict | Grade | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | 26 | 0x2df1c0 | 7944 | CSealCtrlAi::FollowTick | seal_aifollow.cpp | DEFECT-FIXED | C | 0x2e0edc: COVERING (case 8) stores timer 0 only when timer < 0 (bc1f delay slot is a nop); port stored 0 always (the comment claimed a delay slot). Masked: the end-of-tick quirk sets -3 anyway. Rest matches: escortee give-up (bit 3 of +0xdd, threshold), masterComing dot > 0.3, trail goal (GetCellPos inline), ahead goal with the turned offset, close / arrived, wait-up call (handle 0, slot 0x24 sound 47), walkable types, last valid goal, |dx|+|dy| < 2, path flag 8, table 0x457c30 case by case, Debug names, end timer quirk, CreepTick slot 0x8c. The m_master NULL guard (port return) removed: the ELF goes on with the NULL master; never hit in two traced m8 runs. |
| 2 | 24 | 0x2dcd60 | 7464 | CSealCtrlAi::HandleEvent | seal_aievent.cpp | MATCH |  | own/marked/lower type, friendly, visible handle states 0-3 (autosee 10000, front, CanSeeLine, cone + RegisterCanSee), table 0x457ae0 (15) case by case, inlined stale/push/take/mark helpers, constants and Debug/Output args |
| 3 | 3 | 0x25af40 | 6428 | CAiSGrenade::Tick | seal_ai.cpp | DEFECT-FIXED | C | port NULL guards the ELF lacks: pickup m_bits.m_vec (0x25b32c; sized at pickup creation, never NULL live) and the KickGrenade / Return-throw CAiSAnimate writes (0x25c51c, 0x25c5a4; dead, allowThrowbacks 0): removed; the dead branch also printed "ClearRoute()..." twice. Rest matches: gone timers, phases table 0x451530 (13), throw types 0x451510, flee look / flood cover, phase 2 fuse stretch, 9 -> 10/11 |
| 4 | 63 | 0x2d07e0 | 5664 | CSealUnit::IssueCommand | seal_unit.cpp | DEFECT-FIXED | C | guards the ELF lacks removed (never hit in the traced m8 runs; the port runs on the same EE memory map): unit-17 source NULL (0x2d0d28), ESCORT reticle seal NULL (0x2d0ef8), breach action NULL (reads +0x2c, 0x2d1c00). Kept (recorded): ESCORT into an empty unit (the ELF reads the first seal from the list sentinel, undefined for std::list). logic matches case by case (fireteam -> Bravo set, net radio units 26/31/30/24, 29 HandleSupport, command list sets, notify, unit 17 reticle, ambush clear set, switch: ESCORT inline EscorteeJoinUnit, ACTION, FOLLOW, AMBUSH, REGROUP point [4], moving orders packed loc, LASE/DEPLOY, COVER, breach template). Guards the ELF lacks: unit-17 source NULL (0x2d0d28), ESCORT reticle seal NULL + empty unit (0x2d0ef8), breach action NULL (0x2d1c00 reads +0x2c): to trace. Unit 29 returns HandleSupport's v0 (recorded) |
| 5 | 16 | 0x264e20 | 4968 | CSealCtrlAi::PathFollowTick | seal_ai.cpp | DEFECT-FIXED | A | 0x264f48: `next` is data + count - 2 even with one point left (before the vector; only NULL is tested), so a door on the last point of an extendable path (app flag 1) is opened (STATE_ACTION) and the gone-past test calls CanTravelLine with that word; the port made next NULL (door skipped, walked into). Also the PATHRECO state NULL guard (0x265844, the ELF writes through NULL) removed. Rest matches (planning creep, door / close-door, speeds, minTurnAngle quirk, advance, lookahead 30, stuck 1.5, fwd/side, DistToVector z-slot quirk, strafe / turn throttles, slots 0x20) |
| 6 | 46 | 0x28a560 | 4948 | CharacterDynamics::Load | seal_dyn.cpp | DEFECT-FIXED | C | 0x28a7f8: m_throtScale = 1 / (exp_tl(throt_exp) - 1); the port left out exp_tl (no reader of +0x11c in the ELF: dead). Bobbing reads use their own local (sp+0x16c), stand_turn_factor the shared one (sp+0x168): only matters for absent keys. All keys, offsets, deg->rad, cosines, camera params (zeroed, aim default (0,20,0), inserted at the end), tail scaling as the ELF |
| 7 | 13 | 0x2626c0 | 4760 | CSealCtrlAi::AttackTick | seal_ai.cpp | DEFECT-FIXED | A | 0x263218: an engaging enemy in a guard region (type 6, InGuardRegion inlined) pushes STATE_TARGETING (stays) instead of PURSUE; the port left the test out as "GetRegionTypeContainer unwritten" (it is written). 0x263344 / 0x2633a0: the pushed TARGETING / PURSUE state is written only when it is on top (else through NULL); the port wrote into whatever state was on top. m_unit NULL guards (0x2629b8, 0x263264; the reason "CSpawners::Tick unwritten" was stale, never hit in a traced run) removed. Rest matches (spray, StopAttack inline, rest state, hint bits, reload / no ammo, hold-fire valve, target delay, dot cone, fire params flags, throw working, SelectFireParams) |
| 8 | 2 | 0x259930 | 4668 | CAiSPursue::Tick | seal_ai.cpp | DEFECT-FIXED | B | 0x259c18: in delay, phase 1 is set in the bnez delay slot, so a state whose look / cover flags (6) are already set goes on to plan keeping them; the port stayed in delay (stalled until the duration or the target ended). Rest matches: timeout, look on unseen, plan look/cover (FindLook/CoverLoc depth 10, FindPeekDir, spray 0.25-1.5 s), goto, hold (underfire, pursuitTime/Hold, peek 1.5), panic, search (last pos, 0.35 speed, pathShortLimit), search_goto (status), search_pause (scan 85 deg, rate), PURSUIT Debug, timer reset |
| 9 | 52 | 0x2b8230 | 4500 | CTParam::Tick | seal_tasks.cpp | DEFECT-FIXED | B | 0x2b84c0: a compare op (not 7) on parameter 0, 7 or >= 14 reaches the end with v0 = 0 (table 0x454760 entries 0 / 7 -> 0x2b93a0), so the task never ends; the port returned done. Rest matches: entity / select seal (no seal: true, dT kept), setters table 0x4547a0 (courage goal +0x564, SetHealth, speed sat, accuracy, sleeping, aware (u8), weapon-ready / corpse bits 3 / 4 of +0x281, spray), per-parameter op tables (!=, ==, >, <, >=, <=; op 0 / >= 7 true), no AI: false, inside / outside (cell byte 3) |
| 10 | 5 | 0x25d110 | 4220 | CAiSDeploy::Tick | seal_ai.cpp | MATCH |  | ranges (1000 / 60 thrown / effective / 10, designator 50), cells|dx|+|dy|, table 0x4519a0 (12) case by case: can-deploy, see-from-here (hit test), route, travel 20/30/6 s with 152 exceptions, line-of-fire intersect ratio 1.11, ClearRoute inline, prefire (setup, option 4 -> flag 1, throw / projectile), FireWhenReady 5 s, designator 30 s, lase name table anim, fuse (option 0x10 / 8, smoke 122 3 s), complete. The unused CAiVisMap (no side effect) and the preset hit slot are recorded |
| 11 | 38 | 0x285af0 | 3676 | CSealCtrl::PreTick | seal_control.cpp | MATCH |  | wep 1 on targets / zoom without binoculars, slide (slot 0x90) / ThrottlesPreTick exits, jump (5) / action (0) states 1/2/3, shared jump-action rules, ActionCommand 3 / 2 on pad left / right, MP bomb bits 4 / 5 of +0x169, hot swaps 9 / 10, zoom pad down / up with the carried item's opacity, triangle single / double click stance cycles, peek (pressure / 255 > 0.03, OKToPeek 12), reload 6, fire mode 3, throw pressure ring of 10, trigger machine (UP 0 / DOWN 1 / FALLING 2 / RISING 3), weapon timer, accuracy, both screen offsets to camera y (quirk), rumble, pickups, victims |
| 12 | 62 | 0x2cf7f0 | 3000 | CSealUnit::Tick | seal_unit.cpp | DEFECT-FIXED | B | 0x2cfc64: when no member lives, the escortee HOLDPOS walk restarts at the list front after each escortee (HOLDPOS moves an escortee to unit 17, off the list); the port went on with ++it from an escortee OnCommand had just erased (use of a freed node). Port deviation recorded: an empty dead list stops the walk (the ELF reads its order source from the sentinel). Rest matches: dead to m_dead_guys, unit 17 flag (not NULL-tested), follow flags (FOLLOW / unit 0, sub-units), dead source -> GetTail, units 0-3 only, FOLLOW re-issue (+-30 offsets, sub-units), sub ticks, leader corpse state, point timers, compass anchor |
| 13 | 19 | 0x268880 | 2968 | CSealCtrlAi::Tick | seal_ai.cpp | MATCH |  | scan when CanScan (slot 0x20), reaction (offline, not SEAL, not reacting; courage -1 -> aware level 4, else courage <= threat; player's team excluded; flee 15 / surrender 6 states), reaction weights (0/1/0.25/0.25 x (1 - surrender)), seven decays in order (_decay = goal + (v - goal) exp(rate dT); linear -rate dT, eps 0.005), aware valve (u16, callbacks 1/2, AwarenessUpgrade on a rise, Debug), under-fire (double compare) -> STATE_SHOTAT with eventNoise outside the cone, UpdateLocalSeal |
| 14 | 69 | 0x2d4a40 | 2852 | CSealUnit::CreateMultiPlayerUnits | seal_unit.cpp | MATCH |  | once (m_created_units_test); units 0, 28, 17, 31, 30, 26, 25, 24 found or made (164 bytes, appended), radio valve 0, unit 24 "mp_radio_channel_valve" type 1; SealJoinUnit inlined (escortee path returns): team 0x10000000 -> 28, 0x20000 -> 17, else ftsGetPlayer() dropped; player -> 0 |
| 15 | 67 | 0x2d3750 | 2796 | CSealUnit::CreateSinglePlayerUnits | seal_unit.cpp | MATCH |  | Create inlined for 1, 2, 3, 28, 17, 4, 29 (valve 0); Able / Bravo under the fireteam (m_parent +0x3c); Bravo anchor "BRAVOTEAM" type 8 once; enemy sub-units 5..15 (Create inline with the unit-24 valve test); InitalizeSealUnit per seal entity; fireteam HOLDFIRE quiet; theMission +0xb8 order: HOLDPOS -> Bravo HOLDPOS (option 8) + Able FOLLOW, else the fireteam; flag set |
| 16 | 4 | 0x25c860 | 2072 | CSealCtrlAi::SetReturnVelocity | seal_ai.cpp | MATCH |  | SEAL with a thrower: own grenade -> last deploy point, fire params (weapon, target, zero vel, 0x10000, throw types|0x60000), throw / projectile compute, aim dir and (1 - 0.25 (r - 0.5)) x muzzle, else half the distance along the line (y += x quirk), kick x0.8 past 100; others: look dir with rand scatter (-0.2/+0.4/-0.2 + 0.4 r), kick x0.8; scales y, x, z (vScale 80 / hScale 150), identity rotation, SetVelW, dir negated, start 10 up into the three positions, owner node offline |
| 17 | 68 | 0x2d4250 | 2024 | CSealUnit::InitalizeSealUnit | seal_unit.cpp | MATCH |  | team & 8 -> 3, & 4 -> 2, 0x10000000 -> 28, 0x20000 -> 17, first of bits 5..15 -> that unit, else 4; SealJoinUnit inlined per branch (escortee path, follow source when the unit was empty, m_unit), GetUnitByTeam not NULL-tested; each branch returns |
| 18 | 54 | 0x2b9c90 | 2000 | CTMove::Begin | seal_tasks.cpp | MATCH |  | modes (+0x28 & 0xf): 1 anim node (GetNode, BuildMTW, transform, xz away from it at m_dist, facing), 2 own space m_pos x m_dist, 3 a seal (m_pos non-zero: its space, facing reversed; else m_dist beyond it facing it), 4 m_dir rotated (no translation); GOAL_MOVE pos tolerance 3 then +0x1ac = 1, goal timer 0.4, AI -> AIM_SLIDE (5); the dropped GetSealCtrlAi call is recorded |
| 19 | 60 | 0x2be630 | 1968 | CSealCtrlAi::RegisterCommands | seal_tasks.cpp | DEFECT-FIXED | C | 0x2be680...: every AddCmd result but SELECT's (+8) and SPECIAL's (+0xc) is stored (sw) in ai_cmdid's first word, which ends as ai::WAIT's id - the type the Parse functions give their task headers (task_alloc); the port left those stores out (headers typed 0). The 33 commands, names, handlers and order match |
| 20 | 33 | 0x26d6d0 | 1772 | CSealAnim::AnimBlend | seal_anim.cpp | MATCH |  | count < 2: depth; positions of keep-0 parts = weighted sum over the top count frames (id copied when not -1), dropped[10], three passes x 30 pairings (flag 0x100 frames, unflagged, any; CombineRotations, second dropped; scan from frame 0, quirk), survivor = first not dropped, its rotations into the lowest frame, depth = base + 1 |
| 21 | 72 | 0x2d6bf0 | 1736 | CSealUnit::AllowCommand | seal_unit.cpp | MATCH |  | fireteam -> Bravo set (slot 0xc), network radio units 24-26 / 30-31 with a living source, members' controls (slot 0x28, first that allows), EXTRACT (can_run_anim inline with its run_once static, extraction region type 1, a rescued (17) escortee of unit 17 inside), BOMB, AMBUSH (seals), sub-units, unit 17 reticle escortee of another unit |
