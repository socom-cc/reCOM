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

## Part 2: rows 22-73 (2026-11-15, socom-port-large-b2)

The remaining 52 rows of the size order (55,296 bytes, from `CSealCtrl::CSealCtrl` 0x288330, 1,648
bytes, down to `CTLookAt::Tick` 0x2badf0, 700 bytes), audited as part 1 on HEAD 7d2dca73 (part 1
committed; later HEADs up to d19a3161 changed no file of list B). Same method: `z.sh` per function,
the raw `dis.sh` listing wherever `cz.py` elided lines next to a branch or a division, `sym.py` for the
jump tables (0x451a30, 0x451e60, 0x451f90, 0x451210, 0x457170) and statics, `vt.py` for the
`CWorld` vtable (slot 0x24 FindChild), `off.py` / `dw.py` for every member offset the bodies use,
`animenum.py` / `denum.py` for enumerators. Float literals were checked by their value against the
ELF word under the pinned GCC's truncation (every literal of these rows lies on the right side of
its word; the float pass of a21865c4 had already read them back), so no constant was respelled.

### Counts (part 2)

| Verdict | Rows |
|---|---|
| MATCH | 37 |
| DEFECT-FIXED | 11 (A 0, B 2, C 9) |
| DEVIATION-KEPT | 4 (rows 23, 41, 47, 48) |
| UNJUDGED | 0 |
| total | 52 |

Defect rate in part 2: 11 / 52 = 21% (95% Clopper-Pearson: 11% .. 35%); grade A or B: 2 / 52 = 4%
(0.5% .. 13%). By bytes: the eleven defective functions are 11,324 of the 55,296 bytes (20%). Five of
the eleven are only port NULL guards the ELF does not have (rows 33, 54, 60, 62 and part of 32); four
are float sums / products in another association (rows 34, 49, 51, and the 1/dT static of 49).

The whole list B (73 rows): 21 / 73 defective = 29% (19% .. 41%); grade A or B 7 / 73 = 10% (4% ..
19%). The rate falls with size, as the sample audit suggested: 48% in the 21 largest rows, 21% below
1,700 bytes.

### Fixes (ELF addresses)

- Row 26, `CSealCtrlAi::ChooseWeapon` 0x261eb0 (seal_ai.cpp), B: the named-item test compares the
  item count with the use bit itself (0x261ed8: `andi v0,a0,0xff` of the bit, then `slt` with the
  count), not with `m_index`: with two or more items the named item is taken (an index past the end
  wraps in `GetItemByIndex`), with one item the scoring runs. The port tested `m_index < count`.
  Kept as the ELF and noted as a quirk.
- Row 73, `CTLookAt::Tick` 0x2badf0 (seal_tasks.cpp), B: the task needs the seal and its controller
  only; the ELF calls `GetSealCtrlAi` and drops the result (0x2bae74), so a seal without an AI (the
  player) is made to look too. The port returned done when there was no AI.
- Row 32, `CSealCtrlAi::InitAiBrain` 0x26a8d0 (seal_ai.cpp), C: the brain's AI-log record (type 1,
  the node name; its `strlen` taken either way) when `aiLogEnabled` was left out (0x26ad88). Two
  port NULL guards removed: the RESTRAINED setup after a successful push is written through NULL when
  the state is not on top (0x26ac40, network hostages), and the respawn's top state is not tested
  (0x26ad40).
- Row 33, `CTValve::Parse` 0x2b4510 (seal_tasks.cpp), C: the named valve's `AddValve` reads the
  valve's name without a NULL test (0x2b48dc); `ParseValveName` creates a named valve, so the port's
  guard was dead. Removed.
- Row 34, `CZSealBody::UpdateAimDir` 0x2bf340 (seal_weapon.cpp), C: the prone slope dot is
  (x x' + y y') + z z' (adda / madd at 0x2bf640) and the upper bound is `d <= 0.642`; the port summed
  z first and tested `!(0.642 < d)` (differs only for NaN). The still-body test's sum of squares was
  reordered too (no effect).
- Row 49, `CSealCtrl::SlideTick` 0x264270 (seal_ai.cpp), C: 1/dT goes to the file static `_dTI`
  (0x264280) as the ELF; the fudge velocity scale is `_dTI * (dist * frac)` (0x264470); the facing
  dot and the side test are (x x' + y y') + z z' and (gx (-fz) + gy 0) + gz fx, the side as
  `!(side < 0)` (0x2644c0). The port used a local, (dTI dist) frac, z-first sums and `>= 0`.
- Row 51, `CZSealBody::SetVertical` 0x26cb90 (seal_anim.cpp), C: the root-relative height is
  `root.y + (dy + pos.y) - 11.487` (0x26cd18); the port summed `(root.y + dy) + pos.y`.
- Row 54, `CAiSRescued::Tick` 0x2592f0 (seal_ai.cpp), C: phase 6 writes the pushed SUSPENDED state's
  options and setup through NULL when the push landed below the top (0x2595f0); the port guarded it.
- Row 60, `CSealUnit::HandleSupport` 0x2d2bd0 (seal_unit.cpp), C: unit 17 is not NULL-tested
  (0x2d2d5c; both unit setups create it) and the rescued escortee's top state is not tested
  (0x2d2e8c; dead, `AiStateIs` tests the top). Both port guards removed.
- Row 62, `CSealCtrlAi::PostTick` 0x268530 (seal_ai.cpp), C: the RESCUED state set by `SetAiState`
  is written through NULL when not on top (0x268808); the port guarded it (dead in practice).
- Row 67, `CSealUnit::PrivateNotify` 0x2d5c90 (seal_unit.cpp), C: the ambush called off by the
  player's fire issues FIREATWILL with `quiet` = 1 (0x2d5d10: `t0` still holds the 1 loaded for the
  case test); the port passed 0. Only `CommandNotifyFromChild` sees the flag, and it ignores every
  order but FOLLOW, so the effect is nil.

No fix is grade A. The two B fixes change paths the m8 runs may not take (a named weapon in a
fire-mode task, a look task on a seal without an AI); the C fixes change rounding (rows 34, 49, 51),
a debug record (row 32) or nothing observable.

### Kept deviations (recorded in the comments; part 2)

- Row 23, `CSealCtrlAi::CSealCtrlAi`: the navyseal / evasive / creeping bits, the mode / idle / state
  timers, the peek goal (2), the event mask and the event queue's flag are set where the ELF leaves
  the heap block's bytes.
- Row 41, `CSealAnim::AnimPush`: the script's object list is bounds-checked; the ELF indexes it by
  part id without a bound.
- Row 47, `GetSoundNameStringFromCmd`: the default case passes the command name's fifth character
  (sign-extended) as the `%s` pointer in the ELF; the port passes the name from there.
- Row 48, `CTPlay::Tick`: a task without anims (count 0) plays index 0; the ELF divides by zero.
- Recorded within MATCH rows (no observable effect): row 37's "dbnode" lookup (the ELF's `FindChild`
  and `BuildMTW` into a local, both pure) is left out; row 30's location map id is set to 0 where the
  ELF leaves a stack byte (`GetCell` ignores it).

### Leads (part 2)

1. NULL writes after a push: rows 32, 54, 62 (and part 1's rows 5, 7) are the same pattern - a
   state pushed or set, then its fields written through `top->m_state == X ? top : NULL`. The
   remaining ones in other zSeal files ("port: NULL-tested") are worth one grep.
2. `CRemoteCtrl` (zinput.h) is `CSealCtrl` + two words (0x248 bytes); `CreateRemoteSeal` allocates
   592. No `CRemoteCtrl` code reads past +0x244, so the gap is the 16-byte rounding of the class; a
   sizeof probe would settle whether the port's class is 592 too (heap only, network only).
3. Inline `SetAiAware(AIA_DIRECTION)` (row 66) and inline `SetGoalPos` (row 35) were compared with the
   port's out-of-line versions, which behave the same here; other inline copies of the two are not
   checked.
4. Delay slots and kept registers: row 67's defect was an argument register left from a compare
   (`t0`), not a delay slot; `cz.py` shows such loads far above the call. Worth reading the full
   argument set of every virtual call in the unit files.
5. Rows 59 and 64 transform with the VU0 macro sequence inline (`vmulax` ... `vmaddw`); the port's
   `CMatrix::Transform` is assumed to give the same words.

### Runs (part 2)

All on HEAD 1ef7d286 plus the five changed source files (isolated tree; the other workers'
uncommitted files kept out). Focus kept in every run.

- Default build (no hooks, no fake pad) of the final tree links (0 errors, 0 undefined).
- Smoke run with test-only traces (zseal4's `hook_zseal1.cpp` + `pad_fire.txt`, 220 s; the trace edit
  prints a line wherever a part-2 fix's case occurs: a named weapon in `ChooseWeapon`, a LOOKAT task
  on a seal without an AI, a state written through NULL in rows 32 / 54 / 62, an ambush called off
  by fire): cameras skipped at 44 s, 178 s in the mission; 74 "fires at" lines, 72 recycle /
  respawn lines, team following throughout; no STOP, no exception; heap in use 23.36 .. 23.47 MB
  over the last 70 s (combat and recycling). None of the traced cases occurred in m8's opening
  fights, so the two B fixes are not exercised by this run (as the grades say: masked on the demo).
  A first run (lgb2s) on the portable emulator profile logged nothing from the game (the profile's
  console logging was off; fixed in `pcsx2-boot.ps1` by the coordinator) and is not counted.
- No constructor, destructor or per-mission allocation changed (rows 22 and 23 have no fix), so the
  menus round trip was left to the coordinator's full check.

`python tools/socom.py audit independence --strict` passes.

### Result table (part 2, size order; k = audit order, list = row of the list)

| k | list | Address | Bytes | Function | File | Verdict | Grade | Evidence |
|---|---|---|---|---|---|---|---|---|
| 22 | 42 | 0x288330 | 1648 | CSealCtrl::CSealCtrl | seal_control.cpp | MATCH | | every field in the ELF's order (look rate, scan angle/timer reset, cone 1/1/0/1, four decays, net state, goal / weapon timers, unit, vismap, bitfields of +0x168 LSB-first, trigger, pad / readings / memset 40, zoom, HUD 255 / -1 x3, aim pitch, rumble, menu, input, hot swaps, scan limits, ClearGoal / ClearLook(-1), victim, FOV, decay values 1000 / 1 / 1, wep period 5, event times memset 60, fudge vels, MP bomb). Fields the ELF leaves (aim yaw, corpse, trigger power, throwwait, cam state, goal dir/pos, remote goal) are left by the port too (no in-class initialisers). The dead rand branch of the timer reset (range just zeroed) multiplies (range * rand) * 2^-31 where the ELF has range * (2^-31 * rand): never executed |
| 23 | 23 | 0x26b1c0 | 1560 | CSealCtrlAi::CSealCtrlAi | seal_ai.cpp | DEVIATION-KEPT | | as the ELF field by field (peek timer, fire params reset, reaction 1/0/0/0, AI params, four decays, trigger up/dn draws with the double sum, bitfields of +0x280: 0, 2, 5-11 cleared, 12 set, 13-31 cleared, speed, last action / close door from invalid, deploy pos, spray / aware / stuck timers, FOV 0x3f490fdb, range 400, follow fields, padid 1, ladder, scan limits 0x3f860a92, hold cover, valve / task memsets, UpdateStackFlags, stance, underfire, handle). Recorded deviations kept (comments): navyseal / evasive / creeping bits and mode / idle / state timers, peek goal (2), event mask, queue flag set where the ELF leaves heap bytes |
| 24 | 39 | 0x286950 | 1560 | CSealCtrl::ThrottlesPreTick | seal_control.cpp | MATCH | | menus 2..5 or input off: throttles 0 / 2 / 1 via slot 0x20, trigger released (3->0, 2/1->3), weapon state 2, rumble (strength zeroed when the time is out), pickups, victims, 1; else analog: turn -rot x yaw 1.15, pitch hack x dilated x 1.05, piecewise (off) with CD +0xf8/+0xfc/+0x100/+0x104, 1/zoom (0 kept), move speed, scope/binocs 0.2, bob (player, zoom 1/2, stance < 3, prone rate/amp index, 0.5(|f|+|s|), fangle wrap 2pi), throttles with -0 -> 0, TickAimPitch, 0 |
| 25 | 57 | 0x2bc300 | 1552 | CTGoto::Begin | seal_tasks.cpp | MATCH | | select seal / ctrl / slot 0x38, armed bit, count bits 2-9, waypoints bit 14, random bit 15; single: rand % count when >= 2, random spot of the region (GetRandomLoc result ignored), invalid (0) test on x / y only, SetRoute; waypoints >= 2: reserve, push spots / locs, SetRoute(data, size); debug bit + aiDebugEnabled -> Debug + PrintPath; speed saturated 0..1, AIM 3, stance 0, disarm |
| 26 | 12 | 0x261eb0 | 1524 | CSealCtrlAi::ChooseWeapon | seal_ai.cpp | DEFECT-FIXED | B | 0x261ed8: the named-item test compares the count with the use bit (1), not with m_index (the ELF takes the named item whenever the kit holds >= 2, an index past the end wrapping; with one item it scores); the port tested m_index < count. Rest matches: scoring (accuracy, quiet / auto / burst / quiet-again penalties, > 0 tests, saturate 0..1, best by !(s <= best)), loop until 1, Debug lines, SetTrigger(false); void for the unread 1 is recorded |
| 27 | 35 | 0x284560 | 1500 | CSealCtrl::OnActionButton | seal_control.cpp | MATCH | | display off: delayed jump + pending; mask bits in the ELF's order (0/1 cancel + masks, 13 reticule action via CanPerformAction (inline at 0x28462c: MP bomb states 2 / 1,3 / other -> satchel test) not type 4, 17 satchel (item 152, valve 0) + HandlePlacingExlosive(1, 0.2) + valve Set(1) = state 1 on change, 2 climb, 3 nothing, 4/5 pickups (timer 3 in the delay slot, MP bomb type 11 without echo), 6 drop bomb (4 s), 8 corpse, 9 put down, 10-12 victim, 14/15 unit 17 FOLLOW / HOLDPOS via slots 0xc / 0x8, 16 ladder), pending cleared unless climb, masks |
| 28 | 45 | 0x289d60 | 1480 | CZSealBody::PostCreateSeal | seal_create.cpp | MATCH | | view-cone bit, SetNodeEx, box (-10,0,-10)-(10,20,10), controller, AI event, select, debug_uberii, gear list, MP bomb gear, eyes, gear, kit "null" models, weapons (SetItem fail skips the index, model by type 1 rifle / 2 pistol / else grenade, ammo by count x mags), reticule, trigger / round / elevation, aim unit_nz, left game, slot 0x40 Initalize, clutter (world +0x698 = port m_grid->..., bbox up to two parent hops, radius max(|x|, z) via the ELF's bool-to-float trick, x0.5, matrix row 3, velW), shadows (player and one entity, maxShadow), cached reticule seal |
| 29 | 43 | 0x288cb0 | 1456 | CZSealBody::RemoteRespawn | seal_create.cpp | MATCH | | network only; packed weapons for non-hostage non-0x10000000 non-player; pos / matrix / both 84-byte stats blocks kept across ReCreate; group round ? (0x100 ? 3 : 1) : (0x100 ? 2 : 0); PostSetupItems; player findAlign + row 3 + slot 0x34 + UpdateLocalSeal; AI (slot 0x30) vehicle entry (index < size, 268-byte entries) start matrix, teleport, InitAiBrain, UpdateLocalSeal; remote (slot 0x34) with index != 0; Revive via m_unit; RefreshTeamValves; respawn flag |
| 30 | 9 | 0x25f6e0 | 1448 | FindPeekDir | seal_ai.cpp | MATCH | | ahead cell (neighbor table, signed / unsigned bounds, GetCell inline with dummy_cell) not soil 0/10/8/9 -> 2; right (dir+9)&7 not 0/8/10 -> 1, left (dir+7)&7 -> -1 (wins) |
| 31 | 17 | 0x2675e0 | 1360 | CSealCtrlAi::PreTick | seal_ai.cpp | MATCH | | _dT / _dTI (0 for dT <= 0), log frame record (Write 0, 0, 4, &dT once per frame), SUSPENDED: StateTick, ends unless asleep and aiEnabled; dead -> 1; asleep: counts, EventTick, 0; active: count, last pos (slot 0xc), target tick, follow params, slot 0x98 view cone, creeping 0, SensorPreTick unless SURRENDER (6), StateTick, mode table 0x451e60 (0 none, 1 idle, 2 spinner, 3 path, 4 slot 0x8c, 5 slot 0x90, 6 follow), mode timer, throttle ramp (decel 0x43a3a0 when |goal| <= |thr|, accel 0x43a390, x dT, sign, clamp to delta, close_enough eps), shot-at valve countdown with callbacks 1 / 2 |
| 32 | 22 | 0x26a8d0 | 1304 | CSealCtrlAi::InitAiBrain | seal_ai.cpp | DEFECT-FIXED | C | 0x26ad88: the brain record (AI log type 1: the node name, strlen taken always) when aiLogEnabled was left out; two port NULL guards removed: the RESTRAINED setup write after a successful push (0x26ac40, written through NULL when not on top, network hostages) and the respawn top state (0x26ad40). Rest matches (aware 0, alive valve, ClearLook / states / route inline, idle, SEAL: navyseal, hold-fire valve 1, nofade, nosnooze, player's invincibility, team 26, handle D 3 / B 2 / H 1; enemy: valve 0, binoculars, handle 0; aimap collide; event mask; Merge; courage / discipline / FOV deg / range / sens; 0x10000000 restrainable; hostage network restrained + unit 17, offline 0x80000000 restrainable; ESCORTEE anchor type 4 once; respawn OnMissionStart + on_respawn 3) |
| 33 | 47 | 0x2b4510 | 1240 | CTValve::Parse | seal_tasks.cpp | DEFECT-FIXED | C | 0x2b48dc: the named valve's AddValve is not NULL-tested (ParseValveName creates the valve, so the port's guard was dead): removed. Rest matches (count, get_valve 5 -> none, calloc 24 / header, which byte, count 1 op 1, count 2 operator, operand: string -> ParseValveName index or anim valve, bits 2 (input) / 3 / 4; number int / real fptosi / else 0, bits 2-4 clear) |
| 34 | 73 | 0x2bf340 | 1240 | CZSealBody::UpdateAimDir | seal_weapon.cpp | DEFECT-FIXED | C | 0x2bf640: the prone slope test's dot is (x x' + y y') + z z' (adda / madd); the port summed z first, and tested !(0.642 < d) where the ELF has d <= 0.642 (NaN only); the still-body test's sum reordered too (no effect: a sum of squares). Rest matches (aim point bit, weapon slot, aimpoint / firepoint / firepoint_203 / attach offsets + pos (slot 0xc), inverse quat, prone crouch + desired state 1, unattainable: previous aim / norm / reticle / norm bit, CalcAimGoal) |
| 35 | 8 | 0x25ee30 | 1228 | CAiSAction::Tick | seal_ai.cpp | MATCH | | setup / action / valve value tests; table 0x451a30 case by case (0 stand point: SetGoalPos inline (refused above GOAL_MOVE) + timer 0.25 + slide; 1 wait; 2 GetActionById / SetRoute / Confirm, tolerance 20; 3 path states 1-3 wait, points + COMPLETE -> smooth + path mode; 4 travel; 5 none; 6 ExecuteAction(opt & 0xf), push SCRIPT (NULL write kept), 7; 7 clear setup), substate word |
| 36 | 36 | 0x284d20 | 1224 | CSealCtrl::PerformProximityActions | seal_control.cpp | MATCH | | single player victim kept when reticule seal / team mate / visible target (bit 2 of +0x24); CQB 12, restraint 11, knife 10 (AI victim nobindanimset), body carry 8; reticule action (CanPerformAction inline) 7 / 17 / 13 + pending cleared; pickups 4 / 5; defusal 7 (status 3, owner valve 1 seals / 2 others); MP bomb drop 6 (item 154, aim goal y < -0.5); void for the unread v0 recorded |
| 37 | 56 | 0x2bb1c0 | 1212 | CTLookAt::Parse | seal_tasks.cpp | MATCH | | entity name (size rounded to 4 + 48, mode 2, unknownId -3 / invalidId), rate 0.85, pos (mode 1), region centre (copied loc) cell centre, dbnode (ELF: FindChild slot 0x24 + BuildMTW into a local, both pure: the port's omission is recorded), net / node location cell centre, dir (mode 4), wait Rfloat, rate |
| 38 | 20 | 0x269c00 | 1176 | CSealCtrlAi::OnStunDamage | seal_ai.cpp | MATCH | | SEAL or stunned (28): refresh m_time when set up; head - from normalized (dist = length), dot (x x + y y) + z z; table 0x451f90 (0 flashbang: range x0.1, discipline x0.6, hearing 0, courage x0.5, cower by stance 0 / 1 (rand <= 0.5) / 2 ProneCover when facing or within 15; 1 gas Cough_stagger + SND_COUGH; 3 smoke Cough; 4 hearing x0.1; 2, 5, 6 none); grenade setup dropped (port's non-const GetAiState returns the shared unknown state, never NULL: same result); push 28 (NULL write kept) with time, type, anim, 0.15 / 0.25, sound, setup |
| 39 | 58 | 0x2bc910 | 1108 | CTGoto::Parse | seal_tasks.cpp | MATCH | | speed 1, timer read and dropped, node list (GetLocation), else region list (GetRegion, random), waypts tag, none -> NULL; size (n-1)*4+20, wait / count / armed / speed / unused / locs packed / waypoints / random |
| 40 | 15 | 0x2646a0 | 1096 | CSealCtrl::CreepTick | seal_ai.cpp | MATCH | | _dTI, valid bits, goal timer (infinite) expiry clears both goals; forward XZ normalized; to goal XZ, length, unit; ahead / aside sums (the ELF's extra 0 * y terms are exact zeros), move_tolerance 25, GetThrottleFromSpeed 0 / 1 saturated by speed / rateStrafeMax, tolerance clears pos; turn (ComputeTurnThrottle, close to 0 within 0.1 clears dir); slot 0x20 x3. @3531 is a zero vector only read here |
| 41 | 34 | 0x26deb0 | 1092 | CSealAnim::AnimPush | seal_anim.cpp | DEVIATION-KEPT | | frame at the depth (anim, wt), ids -1, keep 1 for 0..24, 0 for hips / root / biceps / shoulder weights and 25..31, per part: hips or keep 0 -> script pos (raw when interpolating), else node row 3; rotation raw / fast; id; depth + 1. Recorded deviation kept: the script object list is bounds-checked (the ELF indexes it unbounded) |
| 42 | 41 | 0x287450 | 1080 | CSealCtrl::PostTick | seal_control.cpp | MATCH | | SensorTick; step_count / throwing / not just threw; reach by state, GetThrowAnim, ComputeMaxVel, asin elev saturated 0..0x3f75be0b (statics only read), ElevOfs, speed 0.3 m (1-p) + m p, quadratic -49 max root, dist, do_adjust re-aim (dist^2 + (x^2 + z^2) + 2 dist z, saturate 0..max), dir, elevate, Rotate / Transform, vel, tland, impact pos (unused), colour 0.78 / 0.78 / 0 (0x3f47ae14), opacity 0.75 -> 0.1, DrawFunc(-1, tland x 2, 100) |
| 43 | 25 | 0x2debc0 | 1064 | CSealCtrlAi::EventTick | seal_aievent.cpp | MATCH | | event tick, seen (alive + visible bit 2 of +0x4e0), every other frame by id parity (lwu, 64-bit frame), stale (dead or unseen > 3 s) -> ClearLook 7, else target pos (seen or < 2 s, slot 0xc) / last pos; in-use events (class 0, index / id / mask into the iterator, audio factor) until handled; asleep -> return; persistent (class 1) unless handled; seen -> return; own event look 3 until expired (NoExpire) |
| 44 | 59 | 0x2bde00 | 1060 | CTComm::Tick | seal_tasks.cpp | MATCH | | select seal / slot 0x38; 0: done; 26 (AI with a living target): team AIs (type 2, 1 << team bit, slot 0x30) Debug + AIA_GENERAL, target passed; 27: team AIs SetSleeping(false); IssueCommand slot 0x8 (seal, cmd, target, 0); dT 0, 1 |
| 45 | 50 | 0x2b6840 | 1032 | CTSound::Parse | seal_tasks.cpp | MATCH | | name / NAME array, string count and bytes, entity, size rounded + 20, entity first, names walked from the first m_names values (quirk kept), names bits 9-16 of +8, count bits 1-8 of +0xa, blocking / sitrep / broadcast bits 0-2 |
| 46 | 61 | 0x2cf330 | 1004 | PlayRemoteMsg | seal_unit.cpp | MATCH | | display name (+0x14) or "unknown"; 47-51 SOUP (msg - 46) needs an entity; else the controller entity's character messages (id, text, sound name, cached sound fetched once), sprintf; sound by name when none; PlaySound(NULL, 255) + TerminateOnFinish; empty line returns; < 53 Add_Message(255, 210, 0) (same both sides), else plain |
| 47 | 64 | 0x2d2730 | 988 | GetSoundNameStringFromCmd | seal_unit.cpp | DEVIATION-KEPT | | "unknown" (20 bytes, zero tail), unit name, table 0x457170 case by case (1 DEFAULT_ACTION ... 25 CLEARAREA, 13 GOTO, 0 / >= 26 default) as the port's verbs; recorded deviation kept: the default case passes the command name's 5th character (sign-extended) as the %s pointer, the port the name from there |
| 48 | 51 | 0x2b7640 | 976 | CTPlay::Tick | seal_tasks.cpp | DEVIATION-KEPT | | prewait / postwait timers (0 re-plays), count bits 1-8, rand % count, -1 skips, Debug, negative -> 1, 64/65/67/68 blend unless on top, CQB falls (select 0's FindDeathAnimTypeCQB unchecked, nobind, DropBody, ClearStack(1, 1), invincible state 0, else 8 + SetHealth(0, CQB) + HUD + DropAllItems + cqb sound slot 0x24 (pos, 1, 1.0, 0, 0, 255)), CQB / PistolCQB blend in the stance, else SetStanceIdle; recorded deviation kept: count 0 draws index 0 (the ELF divides by zero) |
| 49 | 14 | 0x264270 | 968 | CSealCtrl::SlideTick | seal_ai.cpp | DEFECT-FIXED | C | 0x264280: 1/dT goes to the file static _dTI (the port kept a local); 0x264470 the scale is _dTI * (dist * frac) (port (dTI * dist) * frac); 0x2644c0 the facing dot and side test are (x x' + y y') + z z' and (gx (-fz) + gy 0) + gz fx with !(side < 0) (port: z first, >= 0). Rest matches (valid bits, timer / expiry, frac = dT / left unless left < dT, forward XZ, goal XZ unit, pos valid cleared at frac 1, acos x frac x _dTI, sign by side, goals cleared) |
| 50 | 29 | 0x2e20e0 | 948 | GetSnakeFollowLoc | seal_aifollow.cpp | MATCH | | snake length, point index < size, map by id, best / cur from the point, 0.5 accumulators + dir.z / dir.x, fptosi offsets, PointInPath, map bounds (y, x) + scanline cell (dummy outside the span), walkable (not 0/10/8/9), best kept, out = best, 1 |
| 51 | 30 | 0x26cb90 | 944 | CZSealBody::SetVertical | seal_anim.cpp | DEFECT-FIXED | C | 0x26cd18: the root-relative height is root.y + (dy + pos.y) - 11.487; the port summed (root.y + dy) + pos.y. Rest matches (UseVelY off: used bit 0, skeleton fix, new altitude bit, lift and saved pos, SetPosition at the altitude; hang-jump-down tfrac > 0.2 / stand2ladder flag 0x20 -> altitude; ladder slide -descent dT else velM.y dT; used / climb-off paths; falls set the altitude; root pinned 0x4137cac0) |
| 52 | 48 | 0x2b5820 | 944 | CTState::Tick | seal_tasks.cpp | MATCH | | select AI (slot 0x38), push critical; FOLLOW (9): named type-2 master, offset +0x18, setup (NULL write kept); RUSH (29): time, flag 1 / 2 by time / range (squared), flags |= +0xc, named seal else the AI's living target (type 2 or NULL), setup; dT 0, 1 |
| 53 | 44 | 0x289480 | 920 | CZSealBody::CreateRemoteSeal | seal_create.cpp | MATCH | | new(592) CSealCtrl + CRemoteCtrl vtable + 0.001 / 2 (inline ctor), GetByNameMod, units 17 / 28 as is, else "netchar%d" Create + temporary (not NULL-tested) + UnPack; PreCreateSeal, new body, CreateEntity, PostCreateSeal, player camera_effects (never for remote), id / client / PostSetupItems / joined bit / vehicle / display name. Lead: the port's sizeof(CRemoteCtrl) is 0x248 + padding (ELF 592; no CRemoteCtrl code reads past +0x244) |
| 54 | 1 | 0x2592f0 | 904 | CAiSRescued::Tick | seal_ai.cpp | DEFECT-FIXED | C | 0x2595f0: the pushed SUSPENDED state is written through NULL when the push landed below the top, as the ELF; the port guarded it. Rest matches (table 0x451210: 0 join unit 17 (not NULL-tested), 1 option bit 0 -> 3, 2 fade by 0.75 dT clamped (constants 0 / 1), SetActive slot 0x34, 3 valve >= 2, 4 3 s + ClearRoute inline + region location route, 5 path done + timer -> valve 3 with callbacks, 6 push SUSPENDED options | 0xe) |
| 55 | 11 | 0x261740 | 892 | CSealCtrlAi::DoSetStance | seal_ai.cpp | MATCH | | delay 0, same stance ok, stand / crouch desired state 0 / 1, prone: visible living target without hold fire (valve 0) with y^2 / dist^2 over 0.07 or dist^2 < 62500, inside (bit 2 of +0xf5c), hurt non-SEAL; allowed by a grenade state or (top not FOLLOW and restrained stacked) (non-const GetAiState is never NULL: same); denied -> crouch + Debug, else desired 2 + Debug; goal / stance / delay; other stances 0 |
| 56 | 37 | 0x2852e0 | 880 | CSealCtrl::TickPickups | seal_control.cpp | MATCH | | ammo boxes (type 9, 20) once each (lastpickup), cleared when none; reticule / proximity weapon + secondary: timer counts down (twice with both), type 8 weapon id offered unless held (lb +0x60); network: bomb timer, MP bomb node GetClosestNode(row 3, -row 2, 1024, 20, 0, -1), proximity bomb (type 11, none offered, item 154) taken with 4 s |
| 57 | 10 | 0x261090 | 872 | CSealCtrlAi::SetRoute | seal_ai.cpp | MATCH | | invalid goal -> ClearRoute inline, 0; own cell (+0xe4) -> ClearRoute inline, ok; else map / bounds / scanline cell walkable + RegisterPathPlan; ok: path mode, bias then type, type bias when set, search limit 0, tolerance 0, last loc |
| 58 | 66 | 0x2d31d0 | 872 | CSealUnit::SetFormation | seal_unit.cpp | MATCH | | source, statics 25 / -25 / 1.5 / 1, offset, seals but the source (FOLLOW, x stepped out by sign, z + Zoff), escortees once after the first seal (x - Xoff, z - Zoff (1 - E), back + Xoff / + Zoff, x restored), sub-units after the first member (z + Zoff U, x by sign Xoff U / -Xoff U, slot 0x8), offset written back, source |
| 59 | 40 | 0x286f70 | 868 | OKToPeek | seal_control.cpp | MATCH | | states 0-3, top blend, interruptible unless 3, airborne bit, throwing, blend states 4 / 5 / 7; head part y + 1 at the axis, side +-dist (LEFT -1 / RIGHT 1), both transformed (VU0 inline = Transform), node inactive, camera collide flag, GetIntersect, active restored, ok when no hit or camera type 1 (bits 2-3 of poly +0x1a), flag cleared |
| 60 | 65 | 0x2d2bd0 | 868 | CSealUnit::HandleSupport | seal_unit.cpp | DEFECT-FIXED | C | two port NULL guards the ELF lacks removed: unit 17 (0x2d2d5c, read through NULL when missing; both unit setups create it) and the rescued top state (0x2d2e8c; dead: AiStateIs tests the top). Rest matches (BOMB team_airsupport, EXTRACT hostage_rescue valve (temp), extraction region (type 1) at the source's cell, rescued escortees inside get the valve, escortee_extract ActivateArg(1, 4, valve, 0) else Activate; v0 0 recorded) |
| 61 | 70 | 0x2d57f0 | 848 | CSealUnit::Notify | seal_unit.cpp | MATCH | | 1 / 2 private; 0 / 3: grandparent (or this) is the list front -> its sub-units' DistributeNotify + PrivateNotify, else this unit's; others nothing |
| 62 | 18 | 0x268530 | 840 | CSealCtrlAi::PostTick | seal_ai.cpp | DEFECT-FIXED | C | 0x268808: the RESCUED state after SetAiState is written through NULL when not on top, as the ELF; the port guarded it (dead: SetAiState leaves it on top). Rest matches (SensorTick unless SURRENDER, stuck timer (moved^2 (x, y, z) < 0.6 (speed x terrain x dT)^2), delayed stance, peek timer -> desired peek / goal 2, escortee in FOLLOW inside a type-1 region -> RESCUED with region and master id) |
| 63 | 27 | 0x2e1510 | 840 | CSealCtrlAi::HandleFollowTickHideCheck | seal_aifollow.cpp | MATCH | | snakeStateData[handle * 6 + 4] hide flag, not hiding 0, arrived 1; front seal / Hutchins (1): goal^2 <= 4200 (1600 for Hutchins) or master^2 <= saved -> stay, else mode 0 + hold-up cleared; others: timer -1 without hold-up -> mode 0, else -2 -> -1, -3 -> -2, -4 -> -3 |
| 64 | 6 | 0x25e360 | 820 | CSealCtrlAi::ComputeThrowFireParams | seal_ai.cpp | MATCH | | hand (5, 10, 0) transformed, target (extrapolated 1.5 s with flag 2), level dir / dist, look dir, reach (+0x19c) test, apex 10 (+ dy when up), sqrt(196 h), quadratic -49 max root, vx nominal 100 (flag 1) or dist / t, throw vec, power max(abort, dist / reach) via _max(&low, &power), aim -z, stance 0, flags 0x7080000 |
| 65 | 49 | 0x2b64b0 | 812 | CTSound::Tick | seal_tasks.cpp | MATCH | | pending bit, entity name, rand pick 1..count, names < pick -> done without clearing pending, named seal (type 2) else select, AI awareness <= m_aware (bits 3-6), sitrep +0x20 = 2, broadcast slot 0xc (0, id) else slot 0x14 (pos, 1, 0, 0, id), pending cleared, wait -> IsPlaying |
| 66 | 21 | 0x26a290 | 796 | CSealCtrlAi::OnWeaponEvent | seal_ai.cpp | MATCH | | awake + alive, shooter of another team, DistToVector of the frame segment, player's shot within 70 -> the player's HELPATTACK (12, 0.5, 1500, id), within thip_range: shot-at valve 2, underfire += delta (1 - d / thip), pos, shooter, SetAiAware(DIRECTION) inline (goal floor, POINT event below SPECIFIC, value max - 0.001 via SetAiAware(f, 1)); helpattack_range unread |
| 67 | 71 | 0x2d5c90 | 792 | CSealUnit::PrivateNotify | seal_unit.cpp | DEFECT-FIXED | C | 0x2d5d10: the ambush is called off with IssueCommand(NULL, FIREATWILL, NULL, quiet = 1) (t0 still 1 from the case test); the port passed 0 (only CommandNotifyFromChild differs, a no-op for FIREATWILL). Rest matches (0: members that know the entity mark it, AI without a live target take it (slot 0xa0); the caller holding fire points (leader data +0x20 for index 0, follower +0xc), 10 s, pointer-difference dir quirk, 2 ticks; 1 member died; 2 issue follow; 3 sub-units notified) |
| 68 | 31 | 0x26cf40 | 776 | CZSealBody::ConfigureWeaponAnim | seal_anim.cpp | MATCH | | rifle (item 1) / pistol (2) part; anim object for the held part -> parts[held] = held, parts[weapon] = 0; else object for the weapon part -> parts[held] = 0, parts[weapon] = held; bounds as the ELF |
| 69 | 7 | 0x25e7b0 | 764 | CSealCtrlAi::ComputeProjectileFireParams | seal_ai.cpp | MATCH | | LeadTargetG with flag 2 (pos, velW, muzzle), dir / dist; direct: aim point, look, aim -z, 0x600000; arced (0x20000): reach v^2 / g (g the float 98 in an int static), y = (0 (1 - r) + 0.707 r) + dir.y saturated 0..sin(50 deg), aim (0, y, -sqrt(1 - y^2)), look, 0x1480000; item 152: clear 0x400000 + 0x1000000, else 0x800000 |
| 70 | 32 | 0x26d250 | 764 | CSealAnim::AnimOverlay | seal_anim.cpp | MATCH | | top / below frames, wt < 0 -> top's weight, f = wt / ((1 - wt) + wt), ids copied (the below -1 test reads the id just stored: quirk), keep-0 positions (rest 0: copy; wt 0: keep; else rest b + wt t), rotations (below -1 or f >= 0.999: copy; f > 0.001: Slerp with min(f, 1)), depth - 1 |
| 71 | 28 | 0x2e18b0 | 740 | CZSealBody::UpdateFollowParams | seal_aifollow.cpp | MATCH | | once a frame, follower distance next -> current, SetSnakePathUpdate(1, 75), level velocity / forward, velsquared, > 800: cant, dot > 0.82 counts the clock (fptosi 1000 dT) past 2000 -> formation dir = saved = velocity, else clock 0; not steady: saved or forward; statics shuffled (quirk), look dir, flags |
| 72 | 53 | 0x2b93d0 | 712 | CTParam::Parse | seal_tasks.cpp | MATCH | | count >= 3, name, operator, value (real / int / 0), entity (4 values: the 5th; more: "entity"), get_param after, size rounded + 20, param / op halfwords, value, entity, select 0 + "ai" |
| 73 | 55 | 0x2badf0 | 700 | CTLookAt::Tick | seal_tasks.cpp | DEFECT-FIXED | B | 0x2bae74: the ELF tests the seal and its controller and drops GetSealCtrlAi's result, so a seal without an AI (the player) also looks; the port returned done without an AI. Rest matches (modes 1 pos / 2 entity (unknownId: by name, else "player" = entity 0, id cached; else by id) / 4 dir / 3 none, look 5, rate + flags 1 when set, endless: timer 3 s + done, else countdown, expiry clears all looks) |
