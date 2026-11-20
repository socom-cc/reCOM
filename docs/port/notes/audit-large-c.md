# Targeted audit of the large zSeal / zAI functions, list C (2026-11-15, socom-port-large-c)

Question: the random sample audit ([audit-sample.md](audit-sample.md)) found defects in 20% of the
marked functions of 700 bytes or more, mostly in zSeal and zAI; list C holds 77 such functions
(137,916 bytes) of `ai_astar.cpp`, `ai_main.cpp`, `ai_maps.cpp`, `ai_mapwalk.cpp`, `ai_path.cpp`,
`seal.cpp`, `seal_aistate.cpp`, `seal_body.cpp`, `seal_command.cpp`, `seal_ctrl.cpp` and
`seal_squirm.cpp`. The rows were audited largest first. This session judged the 21 largest
(79,052 bytes, 57% of the list's code); rows 22-77 are left for a follow-up (below).

Method as in the sample audit: each row disassembled from `support/socom.elf` (`z.sh`, raw `dis.sh`
where the compaction elides words, `sym.py` for jump tables, strings and vtables, `dw.py` /
`off.py` / `mem.py` for layouts, `animenum.py` / `denum.py` for enumerators) and compared with the
port's body instruction by instruction, helpers the port calls instead of the ELF's inline code
included (`walk_line`, `GetCellPos`, `map_cell_at`, `smooth_point_ok`, `ClearStack`,
`BreachSetValve`, `decay`). Float constants were compared as words, the port's word computed with
the pinned compiler's truncation (`fconv.py` in the scratch folder) and, for the one table that was
wrong, read back from the compiled object. HEAD 24f811a3; no marker was added, moved or changed and
no function moved file.

Verdicts: MATCH; DEFECT-FIXED (A: can change what the player sees or crash; B: wrong but masked on
the demo disc; C: cosmetic, rounding or heap only); DEVIATION-KEPT (differs for a reason recorded in
a comment or note that must stay); UNJUDGED (none).

## Counts (rows 1-21 of the size order)

| Verdict | Rows |
|---|---|
| MATCH | 7 |
| DEFECT-FIXED | 10 (A 0, B 5, C 5) |
| DEVIATION-KEPT | 4 |
| UNJUDGED | 0 |
| total | 21 |

Defects in 10 of 21 functions (48%; A or B 5 of 21, 24%), above the sample's 20% for this size
class. Half are rounding order only (grade C). By kind:

- Sums of three products summed z first where the ELF sums (x x + y y) + z z (rows 1, 6: ten
  sites in `ComputeNextPosition` and `PostComputeNextPosition`, six of them compared to a
  threshold) and one product grouping (row 8). The port's bodies were apparently written from a
  decompiler view that lists the z term first; more sites of the same shape remain in `seal.cpp`
  (see the leads).
- A float table missed by the float-constant pass (row 2): 175 of the 792 `Recoil` table literals
  were `%.9g` decimals the pinned GCC truncates one ulp low.
- A wrong bit field: `GetLocation` tested a whole byte where the ELF tests one bit (row 15).
- A wrong overload: `PushBlend` called `CZSealBody::BodySetState` where the ELF calls `CBody`'s,
  telling the controller of a ladder slide twice (row 10).
- A left-out call (row 4: the network join message) and port-only NULL guards the ELF does not
  have (rows 4 and 11: nine guards removed).
- Unreachable-path differences (row 5) and allocation sizes of two AI state classes (row 20).

## Fixes (ELF addresses)

- Row 2, `CZSealBody::Recoil` 0x270d10 (seal_body.cpp), B: the per-stance kick table (generated
  from the ELF's six straight-line branches) held 175 inexact literals written as nine-digit
  decimals below the word's exact value, which the pinned GCC truncates one ulp low (e.g. the
  standing rifle root offset 0x3bb020c5 built as 0x3bb020c4). All respelled rounded up (the rule of
  [float-constants.md](float-constants.md)); every one of the 132 x 6 values compared with a fresh
  symbolic run of the branches and read back from the compiled object (0 differences). The table
  sits outside any fence and is read by index, so the float-constant pass did not see it.
- Row 4, `CSealCtrlAi::OnCommand` 0x281080 (seal_command.cpp), B: a FOLLOW order that makes an
  escortee join the source's unit also sends `PlayRemoteMsg(source, 40)` in a network game
  (0x282140); the port had left it out ("ELF: ...") although `PlayRemoteMsg` is written. Network
  only. Also four port-only NULL tests removed (GETDOWN 0x282080, ACTION 0x282474, DEPLOY 0x281ab8,
  LASETARGET 0x2812e4): the ELF writes through the state cast right after a successful push.
- Row 10, `CZSealBody::PushBlend` 0x27c090 (seal_body.cpp), B: for a ladder slide the ELF tells
  the controller (`OnStateChange(state, 5)` when the state differs) and then calls
  `CBody::BodySetState(5)` (0x27c90c); the port called `CZSealBody::BodySetState`, which tells the
  controller a second time. No ladders in the m8 demo.
- Row 11, `CAiSBreach::Tick` 0x2d8000 (seal_aistate.cpp), B: five port-only NULL tests removed
  (the breach valve of a dead leader 0x2d80ec and its value test 0x2d8120, NULL only with invalid
  parameters; the leader's state stack 0x2d8160; the door-open and throw state casts 0x2d8468,
  0x2d8550). The port is an EE program as the ELF is, so a NULL access now does what the ELF's does.
- Row 15, `CAiMaps::GetLocation` 0x19c9b0 (ai_maps.cpp), B: whether the later maps of the set are
  searched for a closer floor is the first map's cell bit `m_mes` (bit 5 of the third byte,
  0x19ccb4); the port took the whole third byte (the altitude's high bits, the boundary and shadow
  bits too), so it searched for nearly every position more than half a unit off its cell's
  altitude. A later map wins only when its cell lies closer below; the run below counts how often
  the old flag moved a position to another map.
- Row 1, `CZSealBody::ComputeNextPosition` 0x250f40, C: three sums in the ELF order (the prone
  chord lift 0x2531fc, the facing / move-direction threshold 0x253408, facing . reach 0x253564).
- Row 6, `CZSealBody::PostComputeNextPosition` 0x24fc10, C: seven sums in the ELF order (moved >
  0.0002 0x24fdfc, wall depth 0x24ffa4, in-air loss 0x2500a0, ahead > 0.01 0x250118, side . ahead
  0x250274, slide depth 0x2505b0, nearest hit 0x250740).
- Row 8, `CZSealBody::Tick_0` 0x26ffd0, C: the lean into turns is `MakeZRot(yaw * (-0.000375 *
  fwd))` (0x270c48), not `(yaw * fwd) * -0.000375`.
- Row 5, `CAiStar::find_path` 0x1814c0 (ai_astar.cpp), C: the path walk builds the next location
  only for an on-map neighbour and goes on from the one built before otherwise (0x182200); the
  points take the map's id (0x182060). Both unreachable in practice (a parent never points off the
  map; the ids are equal).
- Row 20, `CAiState::Create` 0x2dc240, C (edit files for the owners' headers, not in the checkout):
  `new(128)` for STATE_SUSPENDED (0x2dc938), whose matrix is quadword-aligned at +0x30 with the
  flags at +0x70, where the port's class was 108 bytes (`edits/zai_suspended.txt`: pads); `new(48)`
  for STATE_RELOAD (0x2dc718) where the port's was 44 (`edits/zseal_reload.txt`: one word, a guess,
  unread). Heap only.

No fix is grade A. No fix changes a path the demo's m8 runs other than by rounding (rows 1, 6, 8),
the GetLocation flag (row 15) and the Recoil table (row 2, one ulp).

## Kept deviations (recorded; not counted as defects)

- Row 3, `CZSealBody::CZSealBody`: the LOD flags of +0xdc are cleared (`#ifdef SOCOM_PORT`) where
  the ELF leaves the heap block's bytes until the first UpdateLODFlags.
- Row 9, `CZSealBody::Tick`: the ELF `sprintf`s the memory-marker counter into an unused local every
  10 s; left out, no effect.
- Row 12, `CAiMap::WalkLine(loc, pnt)`: a start off the map returns false where the ELF walks on from
  an unset stack position (0x1a6bb8).
- Row 16, `CZSealBody::SetStance`: void where the ELF returns 0 / 1; no caller reads it (UpdateStance
  passes it on, PreTick 0x2566ac drops it; CSealCtrlSquirm::PreTick 0x2e284c..0x2e286c drops it).
- Recorded within rows counted otherwise: Recoil without a stance table uses identity kicks where the
  ELF applies unset stack quaternions (row 2); find_path skips an open cell missing from the open
  list where the ELF writes past its end (row 5).

## Leads

1. Z-first sums elsewhere: the pattern of rows 1 and 6 (`a.z * b.z + a.x * b.x + a.y * b.y` where the
   ELF has (x x + y y) + z z) is common in `seal.cpp` and the other zSeal files; two more are in
   rows 31 / 33's functions (`bool moved = dpos.z * dpos.z + ...`). Each needs its ELF order checked
   (`zfirst.py` in the scratch folder rewrites a line range once checked).
2. Data tables outside fences: the float-constant pass attributed literals to the fence above them,
   so a table read by index after a fence (Recoil's) was not compared with the function that reads
   it. A scan of `static const` float tables outside fences against their readers is worth one pass.
3. `BodySetState` overloads: the ELF calls `CBody::BodySetState` in places where an unqualified call in
   the port resolves to `CZSealBody::BodySetState` (which also notifies the controller). Calls marked
   "inline in the ELF" are the CZSealBody version inlined; unmarked ones need a look.
4. Port-only NULL guards ("port: NULL-tested"): nine removed here; more remain in zSeal (grep the
   comment). Most guard a cast that cannot be NULL right after a successful push.
5. Class sizes: the sizeof probe (`probe/sizes.cpp`) compared all 29 AI state classes with
   `CAiState::Create`'s allocations; the same probe is cheap for other factories.
6. Rows 22-77 of the size order (58,864 bytes) are not yet audited; `order.tsv` in the scratch
   folder lists them.

## Runs

All on HEAD 24f811a3 plus the six changed source files and the two shared-header edits (isolated
tree; the other workers' uncommitted files kept out). Focus kept in every run. Screenshots
(untracked) in `build/port/screenshots/59-large/`.

- lfst (zseal4's stability hook `hook_zseal1.cpp` + `pad_fire.txt`, 260 s, plus a test-only trace in
  `GetLocation`): intro movie skipped with CROSS, briefing cameras with X, in the mission from 67 s;
  no STOP, no exception. Combat: 66 "fires at" lines; kills (Sniper1 / Sniper2 95.7 s, OutPatrol4
  113.6 s, OutPatrol1 127.8 s and again 182.1 s after its respawn: recycle timers 4.4 .. 9.9, respawn
  counts 2 -> 1 -> 0); the team following (FOLLOW orders at 66.5 s, follow modes to the end). Heap in
  use 23.37 .. 23.38 MB from 190 s to the end (steady). The `GetLocation` trace: 172,033 positions had
  the old whole-byte flag set where `m_mes` is clear; in none did the old search pick another map
  (moved 0), so on m8 the row 15 fix changes no location (grade B confirmed).
- lfw (`port/test-hooks/win`, -DSOCOM_HOOK_WIN, 300 s): Snow3 rescued in Extract (227.1 s),
  mission_complete 0 -> 1 (231.1 s), "EXIT: debrief open (objectives 3/7)" at 233.0 s. A second run
  (lfw2, its screenshots taken in a working window state) reached the debrief at 274.3 s with
  MISSION SUCCESSFUL on screen (11 kills). The lfst / lfw screenshots came out as 160 x 28 images
  (the window minimized at shot time, the environment issue noted in audit-sample.md).
- lfsr (`port/test-hooks/state`, -DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4): four missions and
  returns; in use 18,657,260 B at every return (flat; 1,376 B above the reference 18,655,884), largest
  free block 3,956,736 / 3,956,736 / 4,214,784 / 2,584,576 B (the menu buffer's own variation,
  [menu-heap.md](menu-heap.md)); no STOP.
- lfdef (default build: no hooks, no fake pad): dlgMenu at 15.7 s, the main menu on screen.

`python tools/socom.py audit independence --strict` passes.

## Result table (k = size rank, # = list row)

| k | # | Address | Bytes | Function | File | Verdict | Grade | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | 30 | 0x250f40 | 12780 | CZSealBody::ComputeNextPosition | zSeal/seal.cpp | DEFECT-FIXED | C | sums of three products in the ELF order (x x + y y) + z z: prone chord lift length (0x2531fc), facing . move-dir threshold vs limit (0x253408), facing . reach (0x253564); the port summed z first. Rest matches: blend/fudge velocities, UseVelY / flag 0x40, Exp spin, air (8/9 + falls), in-air bleed 150/s, still 0.0005 / turn 0.001 / Weight, chord fan (stance sizes, side 0.3/1.2, prone strafe 9.55), falling 7 / dying 5 / player 5 / other 1 chords, 50-chord exits, numChords, UseVelY altitude |
| 2 | 50 | 0x270d10 | 8360 | CZSealBody::Recoil | zSeal/seal_body.cpp | DEFECT-FIXED | B | the per-stance table (from the ELF's six straight-line branches) had 175 of its inexact literals spelled with %.9g, which the pinned GCC truncates one ulp low (e.g. stand0 root ofs 0x3bb020c5 built as 0x3bb020c4); all respelled rounded up (tabfix.py), all 132 x 6 values compared with a fresh symbolic run of the branches (recoil_cmp.py: 0 bad). The float-constant pass missed the table (read by index, outside a fence). Rest matches: recoilParam run-down, bit 5 of 0xdc, t^2 < 0.01, dilation sqrt, 0.5, stance/desired, item 1, 22 parts in the ELF order, Mul / Normalize / Add. Kept (recorded): stance none -> identity where the ELF applies unset stack quats |
| 3 | 40 | 0x2577d0 | 5828 | CZSealBody::CZSealBody | zSeal/seal.cpp | DEVIATION-KEPT | | every store, call and order checked (member ctors implicit in the port): desired stand / peek 2, unit_nz dirs, stats, accuracy tanf(0) * 0.707, sealEx, drop-weapons bit, chords / dpos, altitude bit, CBody::BodySetState(0), threat arrays, CAiDecay (0, 0, LINEAR then 0 / 1.0), seal_body / skel_root / exit(-1), 25 FindPart name -> member pairs, 6 weapons, item 1 + AddWeapon 1 2 3, weapon node, rifle_out, look / fire / blink / turnip objects, AnimSetup false -> return, bbox -10 -2 -10 / 10 20 10 through three use_parent hops, weapon parts' nodes NULL, CHit / IntersectStruct, armor 0 3 1 2 5 4 from +0x30..+0x44, 12 health copies, ~50 bitfields, foot points 1.09, zoom 0 / -1, UpdateAimParams, projectiledi delete. Kept (recorded, #ifdef SOCOM_PORT): the LOD flags of +0xdc cleared where the ELF leaves heap bytes |
| 4 | 72 | 0x281080 | 5444 | CSealCtrlAi::OnCommand | zSeal/seal_command.cpp | DEFECT-FIXED | B | FOLLOW: a network join also sends PlayRemoteMsg(source, 40) (0x282140); the port had left it out ("ELF: ...") though PlayRemoteMsg exists (seal_unit.cpp); network only. Four port-only NULL guards removed (GETDOWN hostage 0x282080, ACTION 0x282474, DEPLOY 0x281ab8, LASETARGET deploy 0x2812e4): the ELF writes through the state cast without a test (never NULL right after the push). Rest matches: jump table 0x4528d0 (28 entries vs the cases), hold fire 6, HOLDPOS/COVERTARGET (pops 7 / 6, hold 2, flags 0x20 / buffer & 8, CanSeeLine sound 52, team 0x20000 -> unit 17, look dir AIL 5 + timer 10, front-seal sound 53, stance 1), FOLLOW bits, GOTO family (hold + goto 8, flags 8/4/2/1/0), GETDOWN range 10000 (x x + y y) + z z, ACTION valve == 0, DEPLOY 151-153 -> 15 s, LASETARGET (x unsigned / y signed deltas, 24-byte names, centre, item 11, distance float, 100 steps of 10, walkable soils), AWARE (slot 0xa0), AWAKE, breach |
| 5 | 1 | 0x1814c0 | 3992 | CAiStar::find_path | zAI/ai_astar.cpp | DEFECT-FIXED | C | path walk: the next location is built only for an on-map neighbour (0x182200), off the map the ELF goes on from the one built before; the port built it from the raw x / y. The points take m_map's id (0x182060). Both unreachable in practice (parents never point off the map, map ids equal). Rest matches: stats, INQUEUE seed (g 0, h dist slot 0xc, f / g in the cell), bias, slice test RCNT0 - offset < limit (unsigned), pop_heap greater, closed, goal x/y, 200 ticks -> 2, limit < searched -> 3, action dirs (d, d+4, then +9 +7 / +9 +7 / +10 +6 unless a door), occupied & flag 0x10, door entry, g = g + (int)(10 fcost), new / cheaper open cell (nodes_searched per visit), status 4 over 2/3 (quirk), 5 leaves state alone, COMPLETE 4, path_cost g, nodes_left / visited. Kept (recorded): an open cell not found in the open list is skipped where the ELF writes past the end |
| 6 | 28 | 0x24fc10 | 3696 | CZSealBody::PostComputeNextPosition | zSeal/seal.cpp | DEFECT-FIXED | C | seven sums of products in the ELF order (x x + y y) + z z, the port summed z first: moved > 0.0002 (0x24fdfc), wall depth (0x24ffa4), in-air into-wall (0x2500a0), ahead > 0.01 (0x250118), side . ahead (0x250274), slide depth (0x2505b0), nearest-hit distance (0x250740); four compare to a threshold. Rest matches: hit collection (64 per chord, 32-byte hits), floor-like drop (slope / volumetric) with swap-remove, push per axis by |out|, in-air loss, side 3.5, ahead 11.46 / 5.25, probe from body or first hit (reach 2), step height, SetActive restore, slide sign rule / stop when prone or crouch-turning, first three chords' nearest, SetWallHit, pi_diTail, fwdhit node, weapon intersect, repel radius 5, SetVertical unless 10, matrix, velW / my |
| 7 | 20 | 0x1a7570 | 3332 | CAiMap::WalkLine(loc, loc) | zAI/ai_mapwalk.cpp | MATCH | | port GetCellPos + walk_line helper (both checked against the inlined ELF code): record init (invalid loc, 0 / NULL), both positions (bounds, x dx + 0.5 dx, altitude 0x3a800004 scale, cell not NULL-tested for the action bit, offset_length along the action offset), length sqrt(x x + z z), step 1 / (len / (0.2 dx)), lerp points, bounds / map / scanline exits false, vftoi0 cells (map id 0), new-cell callback (prev, t len, cell, loc), end point at t = 1 (bounds only), return the last answer. The ELF also normalises the x/z delta, unused |
| 8 | 49 | 0x26ffd0 | 3308 | CZSealBody::Tick_0 | zSeal/seal_body.cpp | DEFECT-FIXED | C | lean into turns: MakeZRot(yaw * (-0.000375 * fwd)) (0x270c48); the port multiplied yaw * fwd first (rounding order). Rest matches: overlay tick + PostChangeWeapon 3 / 4, the cycling / plain overlay loops (two reuse slots, GpAnim, FirePosAnim of BaseAnim_0 rifle at the fire weight, PutBack), ctrl 3 / 2 / else (Slide on fwdhit node, carried tfrac, velocityFactor), stunned zero, callback trigger + clear, CallbackTicks, Rotate180, homing, Animate, the early returns (carried, Stabbed, ReceiveRestraints, CQB falls zero root x/z), skel root delta for steps 16 / 21 / 28 / BuddyCarryStep with was_turning, animate_me, look / eye look / blink (6 rand), pitch, Recoil |
| 9 | 36 | 0x255870 | 2928 | CZSealBody::Tick | zSeal/seal.cpp | DEVIATION-KEPT | | recorded: the ELF sprintf's the memory-marker counter into an unused local every 10 s (left out, no effect). Rest matches: post-tick flag, footbomb pickup, debug timer statics, lastprojectile, alive / dead time, ctrl Tick slot 0x10, state 8, GetRootPart quirk, the wall checks per state (action bit 0x168 b2, 4 Stand(-1), 5 ladder pop / push 48, 7 altitude + idlehack Stand(1), DoWallStop), PostCheckDIDown, terrain < 0.99, interrupt rule (CanInterrupt && blend state != 8, or prev 56), throttle > 0.1, CheckAnim, Stand2Crouch carry, SealAnim, moving reload / swap overlays (-4 trigger), cycling zeroing, Propagate / BlendOverlayPreTick, lr zero for 45 44 11 10 9 8 38 37 35, strafe zero for 46 125 48 126, turn rate, adrenaline (_decay = zmath decay, linear step, eps max(step, 0.005)), scope / binocs SniperTick, heartbeat, fixed foot, Tick_0(-velR.y), ComputeNextPosition slot 0x24 |
| 10 | 69 | 0x27c090 | 2904 | CZSealBody::PushBlend | zSeal/seal_body.cpp | DEFECT-FIXED | B | LadderSlide: after telling the controller (m_state != 5) the ELF calls CBody::BodySetState(5) (0x27c90c); the port called CZSealBody::BodySetState, which tells the controller a second time. Ladders only (none in m8). Rest matches: early returns (state 8 outside 10, stunned, no anim, Slide, id < 0, CQB during CQB), overlay anims, ClearStack depths per type (18 26 36 47 -> 1; 17 25 46 rev 1 / 2; 19 35 -> 2; 37 38 LadderSlide -> 1; 48 rev 2 / 1; StepUp 44 ClimbMedium by state + desired crouch), CBody::PushBlend, current type, ReverseDir, aux parts, ladder tfrac 0, jump launch (playback distance / speed / tf, timers 0.1 / 0.4, impulse jf (-0.4 g), in-air vel), pistol swap callbacks 0.72 / 0.82 / 0.62, NetSendPushBlend unless remote |
| 11 | 41 | 0x2d8000 | 2860 | CAiSBreach::Tick | zSeal/seal_aistate.cpp | DEFECT-FIXED | B | five port-only NULL guards removed, the ELF has none: the breach valve on a dead leader (0x2d80ec) and its value-3 test (0x2d8120, NULL when the parameters were invalid), the leader's state stack walk (0x2d8160), the door-open STATE_ACTION (0x2d8468) and the throw STATE_DEPLOY (0x2d8550) casts. Rest matches: breachTimeout 10, setup bit, invalid parameters -> 11, valve Create(cell name, 0, TEMP), leader dead -> valve 3, opener fallback, jump table 0x4573a0 (1 and 7 default), route to locEx[index] (speed 1), count down (MakeCallbacks 1 / 2), creep + deploy look, wait / 10 s, door type 1 valve 0 / 1 / moving, flashbang 123 fuse 1 / frag 121 fuse 2 (offset 0 0 100, flags 0x34, phase 4), opener's deploy wait, entry behind the leader (substate word >= 9), locEx[index + 3], shouts 5 / 6 every 0.5-1 s, end valve 2, abort, substate word compare |
| 12 | 19 | 0x1a6b00 | 2660 | CAiMap::WalkLine(loc, pnt) | zAI/ai_mapwalk.cpp | DEVIATION-KEPT | | recorded: a start off the map returns false where the ELF walks on from an unset stack position (0x1a6bb8 -> 0x1a6e00). Rest matches: m_end / m_loc invalid, the start position as row 7, p1 = *to, and the walk code from the sqrtf on is instruction-identical to row 7's (diffed, stack offsets aside), i.e. walk_line |
| 13 | 66 | 0x279740 | 2660 | CZSealBody::InStateCrouch | zSeal/seal_body.cpp | MATCH | | CanCrouch inline (18 / 87, water 8.5) and its stand-up tail (desired 0, changed bit, ClearStack 1 + Stand_0), UpdateQuadrant(strafe, fb), ThisFoot, IsStopped(fb, strafe, lr), turnV, crouch-strafe weight (sum in the delay slot, mirror flag), last foot (0.6 / turning / 17..47), crouch push after one pop, idle flags + rep weight 1, crouch step (tfrac 0.5 on the left foot, TurnSetup, turnip 0.8 / 3000 / 0.4, currT), TurnControl, 14.8 (14.8 (s s + f f)) < 107.33, OKToStand, SmoothXZThrottles on the raw copies, sneak push unless 2 / 3 / 4, MoveControl(z, x), crouch walk (pops to 1 / 18 / 26, ctrl 0, peek 2, push 20), CrouchMoveControl(1, fb, strafe), flag 0x40 cleared |
| 14 | 44 | 0x2d9780 | 2632 | CAiSGoto::Tick | zSeal/seal_aistate.cpp | MATCH | | setup, point-out (UpdatePointOutState, turn dir look AIL 5 + timer 10, hand signal 4, mode 1, speed 0), mode 3, plan (mode 2, cover FindCoverLoc(.., 5) else invalid, stealth route type 2, confirm / refuse), path states 1 2 3 wait, points + COMPLETE, option 0x20 within m_dist (x unsigned / y signed), route complete, leading: the statics (0.65f / 0.3f widened, 35 25 70 50 90), cells(at, dest) < cells(his, dest), resets / calls 1 2 0, speed (double) GetSpeedFromThrottle(his throttle) * 0.65 -> throttle, min 0.3, follower slowdown (25), stance 1, substate byte |
| 15 | 14 | 0x19c9b0 | 2564 | CAiMaps::GetLocation | zAI/ai_maps.cpp | DEFECT-FIXED | B | the multi-floor search flag is the first map's cell bit m_mes (bit 5 of byte 2, 0x19ccb4); the port took the whole byte 2 (altitude high bits, boundary, shadow too), so it searched the later maps for nearly every position off its cell's altitude by 0.5 (a later map wins only when its cell lies closer below; see the run trace). Rest matches: floorTolerance -10, empty set, map bounds / vftoi0 / nx ny / scanline, soil 10 skipped, map id = index, altitude 0x3a800004 scale, +-0.5 settles, d > -10 and _close_enough(d, 0, |diff|), out only when found. (The ELF reads the flag before the scanline test, from the dummy cell when the row misses: same while the dummy cell's m_mes is 0) |
| 16 | 58 | 0x276960 | 2412 | CZSealBody::SetStance | zSeal/seal_body.cpp | DEVIATION-KEPT | | recorded: void where the ELF returns 0 / 1; unread by every caller (UpdateStance 0x256d54..0x256e6c returns it on, but PreTick 0x2566ac drops UpdateStance's v0; CSealCtrlSquirm::PreTick 0x2e284c..6c drops it). Rest matches: OnStateChange slot 0x64 on a change, CBody::BodySetState (0x1e29b0: sb m_state unconditionally), the (m_state, state) switch read after the set, so only the equal pairs are reached and no transition runs (quirk, reproduced) |
| 17 | 18 | 0x1a61e0 | 2216 | CAiMap::FloodFill | zAI/ai_mapwalk.cpp | MATCH | | fill record (map, start, loc, dir), limit (2 depth)^2, region cleared + loc, queue, pop front + count, cell in bounds, state 1 callback (0 stops), 8 neighbours (bounds, map id, NULL / rtflag skipped, next_dir, callback, mark, Union, state 2 stops, else queued), cleanup over the region's rows (_saturate 0..ny, u16 max / min with the row span, _reset_rtflag stops), returns stop. The ELF's direction table from dir is built and unused (recorded, left out); the port also clears m_cell / m_next_dir / m_state up front where the ELF leaves them until set |
| 18 | 11 | 0x199870 | 2212 | CAiMaps::RegisterPathPlan | zAI/ai_maps.cpp | MATCH | | GetMapByIndex inline (index < size, list walk), start and goal cells walkable (soils 0 10 8 9 refused), PathPlanBegin, same-map leg (answer untested), cross-map: graph NULL -> fail, "start" / "end" nodes, edges to every located node on the start's / goal's map (length (f32)(int)(dx unsigned + dy signed), edge not NULL-tested), BuildRoute + non-empty, route walk (a node without a location stands for the goal, legs between same-map points, map not NULL-tested), nodes deleted, from = goal, Abort / Execute |
| 19 | 24 | 0x194700 | 2176 | CAiPath::SmoothPathLeg | zAI/ai_path.cpp | MATCH | | leg -1 -> m_planleg, map from m_maps when < m_legcount, GetLegBoundary(first, last), < 3 points left, anchor / mid / mid-1 point tests inline (smooth_point_ok: door action type 1 refused; stealth type 2: shadowed walkable or soils 2 4 12 5 refused, cell not NULL-tested there), WalkLine(anchor, mid-1, _SmoothLineCallback), dropped point -> invalid + changed, else new anchor, while last < mid |
| 20 | 46 | 0x2dc240 | 2120 | CAiState::Create | zSeal/seal_aistate.cpp | DEFECT-FIXED | C | allocation sizes (edit files for the owners' headers): STATE_SUSPENDED new(128) (0x2dc938) vs the port's 108-byte CAiSSuspended (its matrix is quadword-aligned at +0x30 in the ELF, flags +0x70: pads added, zai_suspended.txt), STATE_RELOAD new(48) (0x2dc718) vs 44 (a word +0x2c added, guess, zseal_reload.txt); heap only. Rest matches: jump table 0x457810 (30 entries; 0 / 5 / >= 30 the plain CAiState), every class and vtable, Reset(state) through CAiState (direct call), member inits (breach 0x54..0x5c + Rfloat {0,0} = 0 without rand, event 0x44 / 0x48, stun 0x38..0x40, suspended unit matrix, path recover CAiPath), the other 27 sizes equal (sizeof probe) |
| 21 | 32 | 0x2545e0 | 1968 | CZSealBody::CollidePlayers | zSeal/seal.cpp | MATCH | | query bit cleared, alive + collision bit, cylinders 8 / 6, 5.5 / 15, 3.5 / 19.1, player reach fx fx + fz fz, upright (blend state != 8, state 0 / 1 / 9), 40-byte targets (seal type 2), low = state 2 / 8, inactive / carrier / carried skipped, query bit over low seals, distSq < 2.5 (near + reach), player fire point push (gap at the other's height, (x x + y y) + z z, away normalised in x/z), distSq < near, x / z extents both signs, collideCylinders argument order, dpos and in-air velocity lose their parts into the normal (ELF order), hit |

## Part 2: rows 22-77 (2026-11-15, socom-port-large-c2)

The remaining 56 rows of the size order (58,864 bytes, 43% of the list's code), largest first, by
the method of part 1 (`z.sh` / raw `dis.sh`, `sym.py` for jump tables, strings and tables, `off.py` /
`mem.py` / `dw.py` for layouts, `animenum.py` / `denum.py` for enumerators, float words computed
with the pinned compiler's truncation). Jump tables were compared entry by entry (GetCommandName's
66 entries and their strings by script). Where a NULL test was in question the port's code was also
compiled to assembly (`ccs.sh`) to see what GCC makes of it (see lead 1). HEAD 1ef7d286; no marker
was added, moved or changed and no function moved file.

### Counts (rows 22-77)

| Verdict | Rows |
|---|---|
| MATCH | 40 |
| DEFECT-FIXED | 13 (A 0, B 2, C 11) |
| DEVIATION-KEPT | 3 |
| UNJUDGED | 0 |
| total | 56 |

Defects in 13 of 56 functions (23%; A or B 2 of 56, 4%), close to the sample's 20% overall but with
far fewer behaviour changes than part 1's larger rows. Eight of the eleven grade-C rows are port-only
NULL tests the ELF does not have (removed); the others are rounding order (eight z-first sums in one
function), a doubled, idempotent controller notification and an unreachable peek value. Over both
parts: 23 of 77 functions (30%) had a defect, 7 (9%) of grade A or B.

### Fixes (ELF addresses)

- Row 35, `CZSealBody::SealAnim` 0x27b4d0 (seal_body.cpp), B: whether a popped climb-over turns
  into a fall compares the current blend type with the raw `AnimTypes::ClimbOver` (0x27b574); the
  port compared it with `m_animset->BaseAnim(ClimbOver)`. The run trace shows both m8 anim sets map
  ClimbOver to itself, so the demo is unaffected.
- Row 63, `CZSealBody::PostTick` 0x255080 (seal.cpp), B: a carrier gives its carried body its own
  region shift (0x2550fc: this node's bits 13-17 into the carried node's); the port assigned the
  carried node's shift to itself (a no-op) and called that an ELF quirk. Body carry only.
- Row 30, `CZSealBody::PopBlend` 0x27cbf0, C: a popped-to peek blend re-enters the peek state with
  `CZSealBody::BodySetState(3)` inline (0x27cc88: the controller told once, then CBody's); the port
  told the controller and then called the CZSealBody overload, which told it again. Harmless:
  `CSealCtrlAi::OnStateChange` only sets the stance from the new state. No other explicit
  OnStateChange in list C is followed by the CZSealBody overload (part 1 lead 3 closed).
- Row 34, `CZSealBody::HandleWeaponIntersect` 0x250a80, C: eight sums of three products in the ELF
  order (x x + y y) + z z where the port summed z first; three compare to a threshold (moved >
  0.0002 twice, normal . dir > 0.2).
- Row 37, `CZSealBody::UpdatePeek` 0x273020, C: peeking with a desired peek outside -1..2 the ELF
  keeps the peek (0x2730e4); unreachable.
- Port-only NULL tests removed, the ELF has none (C; each pointer is set on every path that reaches
  it): `~CZSealBody` `CAiEvent::Release(m_aiEvent)` (0x257484; the old reason, Acquire unwritten, is
  stale), `CrouchToPickupBuddy` the buddy's controller (0x26fd50), `PreTick` `m_wephit` (0x2567d8),
  `CAiMaps::GetClosestRegion` the corner's region (0x197a54), `CAiPath::UpdatePointFlags` the leg's
  map (0x194268), `ConfigureAuxPartAnim` the leaving part's gear (0x27d82c), `RestrainBuddy` the
  victim's controller and the top state (0x26ec50, 0x26ecb8), `CAiMaps::ComputeLineVisibility` the
  other end's map (0x19a2f8, 0x19a428). The assembly of each file was checked: GCC loads through
  these pointers as the ELF does (no trap, lead 1).

### Kept deviations (recorded; not counted as defects)

- Row 67, `CSealCtrlAi::StateTick`: the state under a waiting state is read without an end test in
  the ELF (0x2daa6c; a lone state would read the list sentinel's data, `m_stateTimer`, as a state).
  `std::list`'s sentinel is different memory, so the end test stays; the record was added in this
  pass. A waiting state always lies above its script state.
- Rows 76 / 77, `CAiMap::CountMapTravelDir` / `CountMapVisDir`: void where the ELF returns 1; the one
  caller (`ChooseLookDir` 0x259814 / 0x259830) overwrites v0.
- Recorded within rows counted otherwise: `RestrainBuddy` skips a top state that is not
  STATE_RESTRAINED, which the ELF writes through NULL (+4, +0x28, +0xc); written that way the pinned
  GCC emits `teq $0,$0` (a probe compile shows it), so the port skips (always restrained right after
  the push). `CrouchToPickupBuddy` keeps its NULL-blend return, the pair of `Crouch_0`'s recorded
  guard; `GetClosestRegion`'s centre cell takes the region's map id where the ELF's `GetCenter`
  leaves an unset stack word; `UpdatePointFlags` starts its boundary zeroed where the ELF reads an
  unset local; `plan_addleg`'s `cur` starts at the start; `collideCylinders` uses FLT_MAX for the
  PS2 FPU's 1 / 0; `Prone` relies on `Prone_0`'s recorded NULL guard.

### Leads

1. NULL paths and GCC -O3: the port is built with -O3 and without
   `-fno-isolate-erroneous-paths-dereference` / `-fno-delete-null-pointer-checks`. Where a pointer
   that may be a literal NULL (a `? : NULL`, a guard's NULL branch) is dereferenced, GCC replaces
   that path with `teq $0,$0`, an unconditional trap, where the ELF reads or writes low memory and
   goes on. Pointers loaded from memory compile to plain loads. Compiling list C's files today shows
   such traps in `CSealCtrlAi::OnCommand` (6), `CAiSBreach::Tick` (2; part 1 noted the breach valve
   can be NULL with invalid parameters) and `ai_astar.cpp` (`CAiPlanner::fcost`, `~CAiStar`,
   `find_path`: 4). They fire only on the NULL paths, but there the port now stops where the PS2
   runs on. Either the flags above for the game library or a look at each trapping site.
2. Z-first sums outside the rows: `seal_body.cpp` `GetSpeedState`, `Stand_0` and `Jump` still sum
   `m_velM` z first (part 1's `zfirst.py` rewrites them once the ELF order is checked); other
   workers' files hold more (`seal_env.cpp` 11, `seal_weapon.cpp` 3, `seal_ai.cpp` 1).
3. `Crouch_0` and `Prone_0` (not rows) return NULL where the ELF writes through
   `Representative(NULL)`; kept, as the faithful form would trap (lead 1).

### Runs (part 2)

On HEAD 1ef7d286 plus the five changed source files (isolated tree); focus kept.

- Default build (`default.sh`): links (no hooks, no fake pad).
- c2st (zseal4's stability hook `hook_zseal1.cpp` + `pad_fire.txt`, 175 s, plus a test-only trace in
  `SealAnim` and `PostTick`): in the mission from about 58 s, no STOP, no exception; 54 "fires at"
  lines from 94.7 s (enemies at the player, the team at OutPatrol1), the team following to the end
  (follow modes to 130 s, BOOMER / JESTER / SPECTRE "FOLLOWING" on the HUD), heap in use about 23.1
  MB steady. The trace: both m8 anim sets give BaseAnim(ClimbOver 194) = 194, so row 35's fix changes
  nothing on the demo; no body was carried (row 63 not exercised).

### Result table, part 2 (k = size rank, # = list row)

| k | # | Address | Bytes | Function | File | Verdict | Grade | Evidence |
|---|---|---|---|---|---|---|---|---|
| 22 | 21 | 0x1a8630 | 1940 | CAiMap::GetLocationWidth | zAI/ai_mapwalk.cpp | MATCH | | rings r = 1..max: x-r / y-r < 0 -> r, x+r / y+r unsigned vs nx / ny -> r, top+bottom rows i in [x0, x1) at y0 and y1, side columns j in [y0+1, y1-1) at x0 and x1 (quirks kept), walkable_at = 13-bit loc (map id 0), y < ny, x < nx, scanline cell / dummy, soils 0 10 8 9 refused; max+1 |
| 23 | 17 | 0x1a59a0 | 1884 | CAiMap::Tile | zAI/ai_mapwalk.cpp | MATCH | | record {value, flags, 0} from @971, whole-map region zeroed then GetMapRegion when NULL, flag 4 _tile_soil / else 8 _tile_boundary through the inlined ForEach (rows saturated 0..rows by @707 / @709 = 0, columns max(start, x) .. min(end, x+dx), callback 0 stops), else 0x10 shadow: value != cell shadow -> value & 3 + changed; returns changed |
| 24 | 39 | 0x256fe0 | 1840 | CZSealBody::~CZSealBody | zSeal/seal.cpp | DEFECT-FIXED | C | port-only guard removed: the ELF calls CAiEvent::Release(m_aiEvent) without a test (0x257484); the guard's reason (Acquire unwritten) is stale: PostCreateSeal gives every seal its event before any delete (Create / ReCreate / CreateRemoteSeal). Rest matches: carry let go, player_ NULL, IsPlayer (slot 0x2c) lens / NVG / binocs off + heartbeat + ClearTimer + m_iszooming, zoom 0 / -1 / 0 / 1.0, m_respawning (0xf59 b5), network IsRemote 0x34 -> RemoveNetSeal(id, IsPlayer) + deletedId / SealDeleteCleanup, control deleted, clutter effector, PopBlend loop, refpoints, kit UnInit, adrenaline, anchors 0xdb4 0xdb8 0xdbc, grids / clib / flib / parent slot 0x1c / camera effects / model Release / node, eye parts 0x2e0 0x2e8 0x2e4 0x2ec, rifle pistol grenade slots (lh id, unsigned vs size), projectiledi, weapon slot, 29..31, weapons swap, char type, select _free(786), the nine helpers (plain delete), dealloc list |
| 25 | 77 | 0x2e24f0 | 1800 | CSealCtrlSquirm::PreTick | zSeal/seal_squirm.cpp | MATCH | | pad id < 2, CROSS falling (m_on + 1) % 3, L1 down + TRIANGLE falling -> new CSealCtrl(576) + SetController + m_entity, return 1; _hackPitchFactor 1 * dilated pitch, TickAimPitch; aim unit_nz, weapon state 1, fire = !(until <= timer), until -= dT, SetTrigger; until <= 0 -> wait / hold draws (2^-31 rand), (double) sum; stance timer vs CAiTimer::infinite, rand % 3 -> SetStance 2 / 1 / 0; empty kit + no reload: m_on 0, ++item_index, 0.2 / 0.1 (words equal), the zero == zero quirk; star 0.5; throttles slot 0x20 (0 2 1 / 0.2 0.2 0 / sin cos * 0.5) |
| 26 | 59 | 0x277300 | 1644 | CZSealBody::CheckAnim | zSeal/seal_body.cpp | MATCH | | IsDone(m_dT), flags 0x10, ctrl 1 -> 2, 2 -> 0; reversed (0x20) -> PostChangeWeapon rifle else pistol for 58 57 56, Stand2Ladder 46 fwdhit node NULL; action node (DeleteChild slot 0x1c, PartInSpace(part, 0, &local, 0), m_quat Apply, + pos, y = pos y, SetPosition, MakeXRot 0x3fc90fdb, SetActive 0x34, AddChild 0x18, m_modified, both NULLs); Ladder2Slide -> m_airborne; PostFall; Land* && stunned; BuddyCarryPickup (pop carried, reversed -> inline CZSealBody::BodySetState(10) + Detach), BuddyCarriedPickup 0; Stab 8 + Detach / Stabbed 0; ApplyRestraints (pop, Detach) / Receive 0; callback 0x3c(this, 0x40), cleared, returns next / 1 |
| 27 | 48 | 0x26f750 | 1628 | CZSealBody::CrouchToPickupBuddy | zSeal/seal_body.cpp | DEFECT-FIXED | C | port-only guard removed: the buddy's controller is not NULL-tested before GetSealCtrlAi (slot 0x38, 0x26fd50); every seal has one. Kept (recorded): blend NULL -> Top() return, the pair of Crouch_0's recorded guard (Crouch_0 0x2762d0 from a hang / other state gives NULL and the ELF writes through Representative(NULL)). Rest matches: buddy NULL, (x x + y y) + z z <= 64, root through the full node matrix, spinelo PartInSpace quat, unit_x, y 0, Normalize, Scale -1, dir by the 3x3, z-row copy overwritten (quirk), crouch: 0.8 (1 - (dx m20 + dy m21) + dz m22), min 0.2, refpoint excess sqrt / 30, tfrac + delay / TrueLoopTime, wrap; 17 / 19 && m_state 1: GetStance(1) == crouch -> CrouchToPickupBuddyCallback else PickupBuddy, 0.99, flags & 0xfffb; else desired crouch + changed, CanCrouch false -> stand + Stand_0(state, 1) after ClearStack(1, 1) unless state / top 0; true -> Crouch_0(state, top t) unless 1; m_carry, AlignForPickup(root, dir), zoomout, m_nofade 2026-11-20 (after the close-out): guard the ELF lacks, found 2026-11-20 after the close-out: the blend NULL -> Top() return removed, Crouch_0's answer takes the callback unchecked (0x26fce8..0x26fd14). |
| 28 | 26 | 0x195b90 | 1524 | CAiPath::plan_addleg | zAI/ai_path.cpp | MATCH | | start / goal cells walkable (bounds, scanline / dummy, soils 0 10 8 9), flag 0x20 cleared while splitting: graph, GetRegionContaining(.., 4, 0) both, different, nodes by node ex, BuildRoute + size, walk first->next: FindEdge / left region / edge route NULL -> fail, route points forward when the left region's loc x / y equal the route's first region else reversed, plan_addleg(prev, cur) each, prev = cur; then (cur, goal) unused answer + split; flag restored (also when graph NULL); split -> 1, failed -> 0, else push start, goal, map, legcount++. Recorded: cur starts at start where the ELF's is unset (only read with no route points) |
| 29 | 54 | 0x274ae0 | 1520 | CZSealBody::GetThrowAnim | zSeal/seal_body.cpp | MATCH | | toss = power < throw_params +0xc && aim_goal.y < +0x10; frac / offset 0; moving (x x + y y) + z z > 225; state 0 toss / throw, 1 crouch throw unless moving (stand throw), 2 prone toss / throw, 3 peek right 30 / 32, left 29 / 31, else 0; all 21 offset words equal to the ELF's (tz read back with fconv); default 0. (Comment typo of peek_left z's word 0x40cf5c29 -> 0xc0cf5c29 fixed) |
| 30 | 70 | 0x27cbf0 | 1480 | CZSealBody::PopBlend | zSeal/seal_body.cpp | DEFECT-FIXED | C | a popped-to blend in the peek state (m_state 3): the ELF runs CZSealBody::BodySetState inline (0x27cc88: OnStateChange once when the state differs, then CBody::BodySetState(3)); the port told the controller explicitly and then called the CZSealBody overload, which told it again. CSealCtrlAi::OnStateChange is idempotent (stance from the new state, a Debug line), so effect-free. Rest matches: reversed flag 0x20 of the old top, CBody::PopBlend, ConfigureAuxPartAnim(rep), current = BaseAnim or -1, ClimbOver (skel y = pos y + root y, fix bit, alt = last altitude y), ClimbOffLadder reversed 0.95 / else node to alt, Stand2Ladder !reversed (15.3 + alt) - 11.487 (words 0x4174cccc / 0x4137cac0, tz equal), Ladder2Slide alt = pos y, ClimbCrate 11.4 / ClimbMedium 11.5 / Hang2Climb 10.73 / StepUp 10.45 settle (node to alt, root saved y), Rotate180 PreClimbLadderDown |
| 31 | 73 | 0x2826d0 | 1340 | CSealCtrlAi::AllowCommand | zSeal/seal_command.cpp | MATCH | | entity / m_isAlive, jump table 0x452940 (26 entries vs FT_COMMAND: 0 8 9 11 21 22 25 -> 0, 7 13-17 23 -> 1); ACTION source / reticle action / GetActionById, type 0 when m_type_invalid (byte 8 b4) else halfword 6 bits 7-11, 1..3; DEPLOY no data: CanPushAiState(4) then aiDeployList to 0xff with CanDeploy; data: action type (lb 0x20, 7 without), HasItem + ItemHasAmmo, 152 only at 6, then CanPushAiState; FIREATWILL / HOLDFIRE valve 0 m_value; FOLLOW / HOLDPOS; RESTRAIN reticle seal twice, m_restrainable; ESCORT team 0x20000, restrained, ai slot 0x38 AiStateIs(17), always_allow static, network, IsMemberOfUnit(3, seal, 1); breach m_locExValid (byte 7 b4), item 123; LASETARGET AiMaps names[3] anims state 1 |
| 32 | 62 | 0x278230 | 1224 | CZSealBody::ProneControl | zSeal/seal_body.cpp | MATCH | | in water deeper than 1.5: desired crouch + changed, then the inline Crouch (port Crouch(): CanCrouch false -> stand + Stand_0(state, 1) / true -> Crouch_0); rate max(|fb|, |strafe|), share |strafe| / sqrt(fb fb + s s) clamped 0..1, < 1 and not ProneCrawl 27 -> push (pop while top + 1 > 2 unsigned, ctrl 0, peek 2, PushBlend(type, 2, 0)), > 0 -> L / R strafe by strafe < 0; rep weight 1; quadrant change -> Snap + interp1 / 2 = blendtime; fb < 0 negates; SetTimeScale slot 0x14 rate * thr_scale |
| 33 | 31 | 0x254130 | 1192 | CZSealBody::HandleSliding | zSeal/seal.cpp | MATCH | | airborne: Slide popped (snapshot 1, CZSealBody::BodySetState(top state)), descent 0; normal.y >= maxSlopeCos (+0x18): Slide popped, descent > landFallRate (+0xc) and state not 9 / 10 -> HandleLanding(descent), 0; sliding: down = (n.x, 0, n.z) normalised, uphill parts of dpos and in-air vel out ((x x + y y) + z z order, already the ELF's), descent += (1 - n.y) (g dT), step = descent dT, dpos x / z = step n.y n.x / n.z, search scale 1 += 0.1 (0x3dcccccd) < 10 with SealGetAltitude(at, step), dpos.y = hit y - pos y, |dy| <= step or hit above at -> alt + get-new-altitude, descent > 0.25 g and not Slide / 10 / 9 -> PushBlend(Slide, 6, 0) under snapshot |
| 34 | 29 | 0x250a80 | 1176 | CZSealBody::HandleWeaponIntersect | zSeal/seal.cpp | DEFECT-FIXED | C | eight sums of three products in the ELF order (x + y) + z, the port summed z first: moved > 0.0002 (0x250ac4, again 0x250cd0 after the strip), aim normal . (tip - aim point) < 0 (0x250ba0), dpos . flat (0x250c4c), air vel . flat (0x250d04), push dot both ways (0x250e18 / 0x250dac), normal . dir > 0.2 (0x250e6c); three compare to a threshold. Rest matches: m_have_aim_norm / do_aimap_collide, moved + normal.y >= maxSlopeCos -> 1, fire / aim = firepos / aimpos + pos, PointAlongLine(aim, fire, 1.1 0x3f8ccccd), PlaneConstant / LineIntersectPlane, 0 < t <= 1, flat normal strip of dpos and air vel, barrel = firepos - aimpos, moving -dpos (t - 1) dot / still node z row -((t - 1) dot), push < 0 -> dpos -= dir push; returns 1 |
| 35 | 68 | 0x27b4d0 | 1160 | CZSealBody::SealAnim | zSeal/seal_body.cpp | DEFECT-FIXED | B | the climb-over-into-a-fall test compares the current blend type with the raw AnimTypes::ClimbOver value (0x27b574), the port with m_animset->BaseAnim(ClimbOver): different whenever the set's base for ClimbOver is another type. Rest matches: top NULL -> 0; next: dying in the air keeps the top, PopBlend NULL -> 0, climb over ending above the altitude -> JumpFall 9 (6, 0) + state 6 inline + root blendme 0 + descent 0, peek top -> state 3 inline else the old top's state inline (6 -> then the new top's), flag 0x40 clear -> top, state 6 -> alt = node m[3][1]; else top's state inline; jump table 0x452570 (11: 3 / 8 return the top, 7 rep weight 1 + time scale 1, 9 Carrying, 10 Carried), args (fb, lr, strafe), default pop to 1, ctrl 0, peek 2, state 0 inline |
| 36 | 56 | 0x275630 | 1140 | CZSealBody::Climb | zSeal/seal_body.cpp | MATCH | | stack to 1 blend standing else 2 (ctrl 0, peek 2 = ClearStack(.., 1)), <= 5 NULL; <= 10 StepUp (0, 0) / prone Crouch2Prone (1, 1) + rep flags & ~4 + desired crouch; <= 12 ClimbCrate 44 / prone the same; <= 26.5 BlendedClimb / prone Stand2Crouch (1, 0) + BlendedClimb + Crouch2Prone (1, 1); <= 28 ClimbMedium / prone 17, ClimbMedium, 19; <= 32 Hang 36 (4, 0) + Stand2Hang 35 (4, 0), prone none; other states NULL |
| 37 | 51 | 0x273020 | 1124 | CZSealBody::UpdatePeek | zSeal/seal_body.cpp | DEFECT-FIXED | C | peeking with a desired peek outside -1..2 the ELF keeps the peek (0x2730e4 -> return), the port went on to pop it; unreachable (m_desiredPeek holds the four enumerators). Rest matches: peek state, flag 0x10 in / 0x20 out, keep sets (-1: 31 29 PronePeekLeft; 0: 34 33; 1: 32 30 PronePeekRight), 2 straight to the pop test, jump table 0x452540 (29..34 all pop) + prone peeks: PopBlend, state 3 inline, ctrl 0; other tops ctrl 0; not peeking: none desired -> nothing, last foot 2, -1 / 0 / 1 anims by stance (crouch 31 34 32, prone ppl 33 ppr, else 29 33 30), first push in (1 / 2 except up / 0, 1), second (3, 0), state 3, ctrl 1, state 3 again; other values state 3 |
| 38 | 38 | 0x256820 | 1120 | CZSealBody::UpdateLODFlags | zSeal/seal.cpp | MATCH | | distances squared 6400 / 62500 / 250000 (64 / 625 / 2500 x 100), 40-byte targets, seal type 2; rendered: interpolate, blink (zoomed < 62500 sets only, else < 6400), lean + recoil < 250000; unrendered the four cleared; footsteps < 250000; IsPlayer (slot 0x2c, NULL -> 0): < 6400 collision + seen, else cleared; not player: set; own collision when seen or not player; own rendered four set; own footsteps |
| 39 | 52 | 0x273bd0 | 1108 | CZSealBody::FlingBody | zSeal/seal_body.cpp | MATCH | | pos.y + root y, dir = pos - from normalised, dist < radius, falloff 1 - d^2 / r^2, damage falloff >= 2; carrying: carried detached, ClearStack(1, 1), FallForward01 (8, 0), its in-air vel = velW, m_carry NULL; pop until 1 / 18 / 26 base or one blend; ctrl 0, peek 2, Top read again; inverse quat (-x -y -z w) Apply; prone "Prone cover" (state, 0), local.z > 0 FallBackward01 else FallForward01; push g / 98.1 (0x42c43334, tz equal) x (damage x D2N) x falloff / mass, max 150; in-air vel = velW + dir push; up push: descent = -y max(1, 3 (1 - dir.y)); single player stunned |
| 40 | 65 | 0x2792e0 | 1108 | CZSealBody::InStateProne | zSeal/seal_body.cpp | MATCH | | in water deeper than 2 or !CanProneAim (not called in deep water) -> desired crouch + changed + inline Crouch; UpdateQuadrant(&strafe, &fb, 1), ThisFoot, IsStopped(fb, strafe, lr); moving: moving 1 / turning 0, ProneControl(fb, lr, strafe); stopped + _close_enough(lr, @2728 = 0, turnV): two blends (ctrl 0, peek 2), not Prone 26 -> one pop when >= 2 + PushBlend(26, 2, 0), flags 0, weight 1; turning: not ProneTurn 28 -> two blends + push + last foot (17..47 -> 32 else 2), turning 1, TurnControl(fb, lr) |
| 41 | 37 | 0x2563e0 | 1088 | CZSealBody::PreTick | zSeal/seal.cpp | DEFECT-FIXED | C | port-only guard removed: m_wephit is read without a NULL test (0x2567d8; the ctor makes it). Rest matches: m_dT, fix_skel_y 0, animate_me 1, !m_stunned -> am_stunned 0, appCamera entity -> UpdateLODFlags, no control -> return, dead: ctrl PostMortemPreTick slot 0x14, !IsRemote -> TickRumbler, body slot 0x68; ctrl PreTick slot 0xc -> doPostTick, carried -> the carrier's control, dead-anim when !isAlive (FindRandomDeathAnim(3) -> WeaponHitAnim(.., 8, 0)), carry > 28 ((x x + y y) + z z <= 784): both ClearToBase(0), root parent -> own else carried DetachBody, not dying: UpdateStance / UpdatePeek / WeaponsTick, throttles lr = [2], fb = [0], strafe = [1], zeroed (dying, stunned, 6, buddy pickups), crouched carrier: callback -> zero else carry let go, ladder 5 lr + strafe, 9 / 10 strafe, !CanTurn lr, HandleWepHit, PreCheckDIDown |
| 42 | 61 | 0x277d10 | 1084 | CZSealBody::MoveControl | zSeal/seal_body.cpp | MATCH | | newanims cleared, |fb| <= stoppedV -> 0, speed sqrt(fb fb + s s), discarded fabsf, frac |s| / speed, share 1 / 0 / asin * 0.636619747 (0x3f22f983, tz equal) clamped, speed max 1, velocityFactor 1 / sqrt(s s + (1 - s)^2), fb anims (0x64 / 0x68 at -speed + AnimsScaleTS -1, weight 1) when |fb| > stoppedV and share < 1, strafe anims (0x70 / 0x6c, weight share) when |s| > stoppedV and share > 0; none: one blend, ctrl 0, peek 2, Top; strafe set members' m_dfrac 0; SetBlendAnims(CBody, list) |
| 43 | 7 | 0x1978a0 | 1040 | CAiMaps::GetClosestRegion | zAI/ai_maps.cpp | DEFECT-FIXED | C | port-only guard removed: a NULL region (corner on an unknown map) was skipped; the ELF reads it (0x197a54); every corner of the region lists is a region of a known map. Kept (recorded): the centre cell takes the region's map id where the ELF's GetCenter (0x19e690, writes x / y only) leaves an unset stack word. Rest matches: here = GetCellCenter of the location (map by index inline, NULL map skipped), m_regions[type] (0x84 + 12 type), GetRegion on the corner's map, !inside skips a region holding the location (dx / dy signed in [0, extent)), centre cell, dsq x x + z z, first or smaller wins |
| 44 | 55 | 0x275170 | 996 | CZSealBody::PostFall | zSeal/seal_body.cpp | MATCH | | Top read unused, FallBackward01 / FallForward01 base else 1, airborne 0, ClearToBase(true) inline (pop to 1 / 18 / 26 base, one more, ctrl 0 without a test, peek 2), Top again, alive: Getup (0, 0) then Land (0, 0) + desired stand; dead: Land (8, 0); root blendme 0; 0 |
| 45 | 10 | 0x199220 | 984 | CAiMaps::ExtendPath | zAI/ai_maps.cpp | MATCH | | no points 0, goal end (points[0]) map id differs 0, same cell 1, map + CanTravelLine(end, goal, NULL) -> AppendPathLoc(goal, NULL), flag 1 SmoothPath, IncrementPathId, 1; flag 8 + template: PointInPath of end then goal, step by to < from, template points [size - i - 1] with their maps, then the goal with its map, 1; SmoothPath + UpdateTurnAngles on every template path (also when not found) |
| 46 | 75 | 0x283350 | 984 | CSealCtrl::AllowCommandFOLLOW | zSeal/seal_command.cpp | MATCH | | source NULL / IsPlayer 0; ok = escortee (0x20000) && restrained && reticle; AI: state, GetFollowMaster(0), single player !ok -> team & 2; remote (slot 0x34): slot 0x1c GetRemoteAiState / GetRemoteAiFollowMaster; ok && state != RESCUED 17 && !team 0x10000000; non-escortee: state != FOLLOW 9; escortee: unit 17 or (single player) unit 3 -> |dx| (unsigned) + |dy| (signed) < 50; else master, != source, FOLLOW, source sq < 0.9 (0x3f666666) master sq ((x x + y y) + z z) and < 250000 |
| 47 | 67 | 0x27a7a0 | 968 | CZSealBody::StandStill | zSeal/seal_body.cpp | MATCH | | ThisFoot; not Stand: strafe side weights of the strafe set (R for strafe >= 0, else L), any mirrored (flag 0x40) negates, L negates, last = rep flag 0x40 ? 32 : 2, one blend (ctrl 0, peek 2), > 0.6 -> 2, < -0.6 -> 32, turning -> last, else foot 17..47 -> 32 / 2, still not Stand -> pop + Stand (0, 0); turnip Clear, turning / moving 0 twice, weight 1, rep flags & ~0x40. (Comment word of -0.6 corrected to 0xbf19999a) |
| 48 | 23 | 0x1940a0 | 964 | CAiPath::UpdatePointFlags | zAI/ai_path.cpp | DEFECT-FIXED | C | port-only guard removed: the leg's map is not NULL-tested before the cell lookup (0x194268; NULL only for a path without legs or past the last boundary, never hit: the last boundary is points[0]); GCC loads through it as the ELF (no trap, asm checked). Kept (recorded): the boundary starts zeroed where the ELF reads an unset local without legs. Rest matches: < 3 points, walk from the end, map / boundary of leg 0 (waypts[1]), boundary hit: flag 2 on both, leg++, map and boundary [2 leg + 1] when < legcount; action cell bit (byte 0 b7) -> 1 on prev; shadowed walkable or soil 2 4 12 5 -> 4 |
| 49 | 35 | 0x255400 | 948 | CZSealBody::UpdateAiEvent | zSeal/seal.cpp | MATCH | | event NULL -> return (the ELF tests too); alive: speed |vz| + |vx| when |t0| + |t1| > 0.15, 1.8 (0.5 + v)^2, GetStance(1) jump table 0x450f00 (0 none, 1 0.67, 2 0.33, 3..8 and >= 9 x 1), ground material (bits 10-17, >= size -> 0) 1.5 - stealth factor, 1 (1 - s) + 0 s saturated by @2874 0.01 / @2875 1, invisible 0.01, pos, range^2, ENTITY 3, unseen; dead: type 0 stays, CORPSE 6, 160000, visible, pos + 10 y; all static words equal |
| 50 | 22 | 0x193930 | 924 | CAiPath::AddSnakePoint | zAI/ai_path.cpp | MATCH | | snake len 0 -> return; empty: reserve(len) + push (loc, width / flags / unused 0, angle 0); else oldest same map -> city-block (x unsigned, y signed) as float > m_length -> m_length, resize(n + 1) when n < len, memmove min(n, len - 1) points up one, new point at 0; GetMapByIndex -> width GetLocationWidth(loc, 5); pathId++ |
| 51 | 60 | 0x277970 | 924 | CZSealBody::CrouchMoveControl | zSeal/seal_body.cpp | MATCH | | newanims cleared, |fb| <= stoppedV -> 0, discarded fabsf, share |s| / sqrt(fb fb + s s) clamped; share < 1: back set 0x78 (fb, 1) / crouch walk 20 from the pool timed fb thr_scale + PushAnim 1 / no anim: PutBack + set 0x74; share > 0: strafe-R set 0x80 (strafe, share); none: two blends, ctrl 0, peek 2, Top; strafe anims dfrac 0.5; SetBlendAnims; quadrant snap + interp; fb < 0 AnimsScaleTS(0x78, -1) |
| 52 | 71 | 0x27d620 | 912 | CZSealBody::ConfigureAuxPartAnim | zSeal/seal_body.cpp | DEFECT-FIXED | C | port-only guard removed: a part leaving for another part is set as gear without testing the gear (0x27d82c: SetPartAsGear reads address 0x1c when the part's entry has none); GCC emits a plain load, no trap (asm checked). Rest matches: anim NULL, slots 29..31 (data() unchecked), the slot part's obj-anim entry + gear (lh id), the anim's objects_for_body[i] (< size), no object: SetPartAsGear inline when part + gear, slot cleared; object: entry by the object's byte 0xb id, its part, slot = part (< size) |
| 53 | 47 | 0x26eb70 | 908 | CZSealBody::RestrainBuddy | zSeal/seal_body.cpp | DEFECT-FIXED | C | port-only guards removed: the victim's controller (GetSealCtrlAi slot 0x38, 0x26ec50) and the top state (0x26ecb8) are not NULL-tested. Kept, now recorded as a port deviation: a top state that is not STATE_RESTRAINED the ELF writes through NULL (+4 +0x28 +0xc); written that way GCC -O3 emits teq $0,$0 (a trap: probe compiled), so the port skips it (always restrained right after the push). Rest matches: "Restrained anim set" by strcmp over AnimSet::list, BindAnimSet + default set, not restrainable, m_nobindanimset, PushAiState(7, 1), option 2 / team / setup, victim one blend, 26 (2, 0), ReceiveRestraints (2, 0), carry links, restrained, DropAllItems, root parent, node to this node's position, own one blend, ApplyRestraints (0, 0), state 0 inline, FP camera + zoom != 1 -> RestoreCameraPosition callback |
| 54 | 3 | 0x17e520 | 892 | ai::AddNoise(pnt, out, range) | zAI/ai_main.cpp | MATCH | | MakeNoise inline into out (row 57's sequence: per component the sign draw Rfloat {0, 1} <= 0.5 -> +1 else -1, then the magnitude min + span (2^-31 rand) unless span 0, (double) product), then out = out + pnt |
| 55 | 2 | 0x17e1b0 | 880 | ai::AddNoise(pnt, range) | zAI/ai_main.cpp | MATCH | | the same noise into a local, pnt = pnt + noise |
| 56 | 13 | 0x19bc60 | 864 | CAiMaps::GetCellCenter | zAI/ai_maps.cpp | MATCH | | GetMapByIndex inline, NULL -> NULL, y < ny && x < nx else NULL, x = min.x + (x dx + 0.5 dx), z likewise with dy / min.z, y = min.y + ((max.y - min.y) 0x3a800004 (tz equal)) altitude (10 bits) with a cell else 0, action bit read without a cell test (as the ELF), action offset != 8 -> GetDirVec, offset_length Scale, Add; returns out |
| 57 | 4 | 0x17e8a0 | 864 | ai::MakeNoise | zAI/ai_main.cpp | MATCH | | min / span, per x y z: sign (0 + 1 (2^-31 rand)) <= 0.5 -> 1 else -1, magnitude min or min + span (2^-31 rand), (f32)((double) mag (double) sign); returns out |
| 58 | 12 | 0x19a120 | 860 | CAiMaps::ComputeLineVisibility | zAI/ai_maps.cpp | DEFECT-FIXED | C | port-only guards removed: the other end's map is not NULL-tested before TransformTo (0x19a2f8 / 0x19a428; the comment called it an ELF quirk with a port guard). Rest matches: same map -> its ComputeLineVisibility (1 without the map), from on map 0: to moved onto map 0 (GetMapByIndex(0): NULL when no maps) and measured, else 1; to on map 0: from moved; other pairs 1 |
| 59 | 64 | 0x278bc0 | 856 | CZSealBody::InStateCarrying | zSeal/seal_body.cpp | MATCH | | UpdateQuadrant(&strafe, &fb, 1), ThisFoot, IsStopped(fb, strafe, lr); stopped + _close_enough(lr, @2778 = 0, turnV): two blends, flags 0, weight 1; turning: BuddyCarryStep (9, 0) once after two blends + last foot (17..47 -> 32 else 2), turning, TurnControl(fb, lr); moving: fb != 0 and not BuddyCarryWalk -> two blends + walk (9, 0), moving, weight 1, SetTimeScale(fb thr_scale) |
| 60 | 74 | 0x282d40 | 848 | CSealCtrl::GetCommandName | zSeal/seal_command.cpp | MATCH | | jump table 0x452ef0: all 66 entries mapped to their strings and compared with the port's table by script (0 differences; the ELF's code order differs from the enum, the table does not); >= 66 "BOGUS COMMAND" |
| 61 | 43 | 0x2d91a0 | 832 | CAiSScript::OnSignal | zSeal/seal_aistate.cpp | MATCH | | signals by (u8): 0 entered (critical 0, aware / seq 255, first tick, timer 0, anim set NULL), 1 popped (anim Stop unless keep && alive, default set unless m_nobindanimset), 2 covered (Debug with the name or "", mode saved from ctrl +0x30c, Pause, set saved + default bound), 3 uncovered (SetAiMode, response killed as KillResponse inline: SequenceRunning dropped, get_aiseq(seq), first tick 0, Stop / Resume sequence, critical 0, Debug, response ""; flag 4 cleared; first tick, Resume; saved set bound when alive, cleared), 4 reset (all fields); others nothing |
| 62 | 25 | 0x195590 | 824 | CAiPath::AppendPathLoc | zAI/ai_path.cpp | MATCH | | states INQUEUE 1 / PLANNING 2 / ABORT 3 -> 0; no points: point (loc, 0, 0, angle 0) pushed, COMPLETE 4; COMPLETE + points[0] on the location's map: point inserted at the front, no waypoints or the last on another map -> loc twice + map + legcount++, else the last waypoint = loc; pathId++, flag 0x40 PrintPath |
| 63 | 34 | 0x255080 | 824 | CZSealBody::PostTick | zSeal/seal.cpp | DEFECT-FIXED | B | carrying (state 9): the ELF gives the carried body's node the carrier's region shift (0x2550fc: this node's bits 13-17 into the carried node's); the port assigned the carried node's shift to itself (a no-op) and called that an ELF quirk. Body carry only. Rest matches: camera region from m_last_altitude, PlayerCanSeeRegion -> region shift = GetMaxRegionShift(GetPlayerCanSeeRegion()), m_doCZSealBodyPostTick, carried / Stabbed / ReceiveRestraints follow the carrier (PartInSpace(root, 0, &pos, &rot) into the root, SetMatrix of the carrier node, next quat = carrier quat, position), UpdateAiEvent, PostComputeNextPosition, Post, hostage anchor pos, prev aim point / norm / reticle / have-norm bit, UpdateAimParams, ctrl PostTick slot 0x3c, grenades, kit, stun, step, blood |
| 64 | 57 | 0x275fa0 | 812 | CZSealBody::Prone | zSeal/seal_body.cpp | MATCH | | deep water (> 2) or !CanProneAim -> desired crouch + changed + inline Crouch; speed sqrt((x x + y y) + z z) > 2 -> desired stand + changed, top; state or top state 2 -> top; ClearStack(1, 1) inline; Prone_0 inline (stand Prone 26 + Stand2Prone 25 (2, 0), crouch 26 + Crouch2Prone 19, hang Prone_0(0) + Stand_0(4, -1), last foot 2, rep flags & ~0x40; the hang / other-state NULL write is Prone_0's recorded guard, not a row) |
| 65 | 5 | 0x196e60 | 796 | CAiMaps::SetOccupied | zAI/ai_maps.cpp | MATCH | | from cell (map by index inline, bounds, scanline / dummy) m_occupied (byte 0 b5) 0, to cell 1; maps NULL-tested in the ELF too; the id unused |
| 66 | 6 | 0x197340 | 788 | CAiMaps::GetRandomLoc | zAI/ai_maps.cpp | MATCH | | 8 tries: x = dx - 1 ? rand() % dx : 0, y likewise (signed div), loc = corner + (x, y) with the region's map id, map NULL / off / unwalkable (0 10 8 9) -> next; true on a walkable cell |
| 67 | 45 | 0x2da980 | 784 | CSealCtrlAi::StateTick | zSeal/seal_aistate.cpp | DEVIATION-KEPT | | the state under a waiting state is read without an end test in the ELF (0x2daa6c: a lone state would take the list sentinel's data, m_stateTimer, as a state); std::list's sentinel differs, the end test stays, now recorded in a comment (a waiting state always lies above its script). Rest matches: front or _unknown, Tick slot 0xc, timer += dT, ticked 0, kept: stack flag 1 -> UpdateStackFlags(0), m_response (+0xc b2), script under (type 1), paused anim -> response cleared, else response[0] && SequenceRunning, not running -> KillResponse(this, 0) + Pause + cleared; popped (PopTop): order flag, signal 1, delete + erase, new front signal 3 + timer 0 + UpdateStackFlags, Debug "PopAiState" |
| 68 | 63 | 0x2788b0 | 780 | CZSealBody::InStateCarried | zSeal/seal_body.cpp | MATCH | | IsStopped(fb, strafe, lr); stopped + _close_enough(lr, @2794 = 0): two blends (tracked top), ctrl 0, peek 2, weight 1, SetTimeScale(fb thr_scale), flags untouched (quirk); turning: BuddyCarriedStep (10, 0) once, turning, TurnControl(fb, lr); moving: fb != 0 and not BuddyCarriedWalk -> two blends + walk (10, 0), moving, weight 1, time scale |
| 69 | 76 | 0x2838f0 | 772 | CSealCtrl::TickMPBomb | zSeal/seal_ctrl.cpp | MATCH | | engaged node NULL -> return; dropped bomb node GetClosestNode(pos, -z row, 1024, 20, 0, -1), -1 -> NULL defusal node; timer -= dT at the defusal node (d != -1) and at the reticle action's node; timer >= 0 -> return (engaged kept); defusal node + bomb state 3 -> pickup timer 1, AttemptBombDefuse, node NULL; else reticle action + CanPerformAction (inline in the ELF: satchel 6 / MP bomb 4 by state 2 CanPlaceBomb, 1 / 3 no, others the satchel test) + type 4: state != 3 -> ExecuteAction(seal, 0) + HandlePlacingExlosive(154, 1, 0.2), bTimerEngaged (0x168 b13) 0; engaged node NULL |
| 70 | 8 | 0x198a00 | 772 | CAiMaps::GetSporeLocation | zAI/ai_maps.cpp | MATCH | | run of the id in the sorted table (12-bit id at +4 bits 4-15: below skipped, first, above -> last = i - 1), last -1 -> count - 1, none 0, run <= 0 -> 0, n >= run -> n % run (unsigned), GetMapByIndex + GetCellCenter (NULL -> 0), direction table 0x4494d0 (8 entries = GetDirVec, default N), negated (-0 y as the ELF); 1 |
| 71 | 9 | 0x198d10 | 764 | CAiMaps::UpdateNameTables | zAI/ai_maps.cpp | MATCH | | types 1..5, table cleared, count of the maps' names of the type (byte +0x17), reserve, copies (loc, +4, the 15 name bytes, type) with the map's index as map id pushed, SortByNames for every type |
| 72 | 33 | 0x254d90 | 748 | collideCylinders | zSeal/seal.cpp | MATCH | | register / stack argument map checked (o f12-f16, s f17-f19 + srad / sheight / d on the stack); dy 0: both span tests, [0, 1]; else 1 / dy, t0 / t1 by the sign of dy ((oy - sy) - sh, (oy + oh) - sy), t1 < 0 / t0 > 1 out, clamps; a = dx dx + dz dz, b = ex dx + ez dz, c = (ex ex + ez ez) - sum^2, b b - a c < 0 out, roots inv (b -+ root) (recorded: 1 / 0 = FLT_MAX as the PS2 FPU), t0 <= hi, t1 >= lo, t = max(lo, t0), at = s + t d, normal (at.x - ox, 0, at.z - oz) normalised |
| 73 | 42 | 0x2d8d50 | 744 | CAiSScript::Tick | zSeal/seal_aistate.cpp | MATCH | | setup + anim, GetName, !Running -> Debug + setup 0 + 0; response running -> setup; KillResponse(ctrl, 0); first tick -> cleared, Debug, 1; aware (u8) same -> timer += dT; critical -> Debug, 1; get_aiseq(old / new), SequenceExists: 0 -> 1 pause + activate, 1 -> 0 stop + resume, else stop + activate (the four Debug strings checked), timer 0, seq = aware; missing: Debug + timer 5; aware stored; 1 |
| 74 | 53 | 0x274800 | 732 | CZSealBody::GetPutativeFirePointW | zSeal/seal_body.cpp | MATCH | | thrown: stance of the first non-peek blend from the top (0 when none), stand: peek state -> l / r toss by desired peek -1, speed > 20 with |vx / vz| < 0.5 (vz != 0) -> running rifle (item 1) / pistol throw, else toss / throw; crouch, prone toss / throw; others CPnt3D::zero; all nine table addresses checked; point through the node matrix (VU0 order); else firepos (firept NULL -> zero) + pos |
| 75 | 27 | 0x24f6d0 | 720 | CZSealBody::OnDeath | zSeal/seal.cpp | MATCH | | CEntity::OnDeath, SetOccupied(mapLocValid, invalid, id), time of death = mission timer, local player (IsPlayer && !IsRemote, NULL -> 0): OnListenerDeath, kit lens / NVG / binocs off, zoom state 0, StopRumbler + low 0.18 (0x3e3851ec) / 175 + high 0.04 (0x3d23d70a, tz equal); single player DecrementTeamValves; network: shift 8 unless team bit 0, escortee 62, else killer by id (seal type 2) "%s fragged %s with %s" (255, 74, 8), not the player: GetAiNetState bit 30 clear -> 37 when the player's team has the bit else 36; RefreshTeamValves |
| 76 | 15 | 0x1a5400 | 716 | CAiMap::CountMapTravelDir | zAI/ai_mapwalk.cpp | DEVIATION-KEPT | | recorded: void where the ELF returns 1; its one caller (ChooseLookDir 0x259814) overwrites v0. Rest matches: 8 directions, ends = loc / counts 0, up to depth steps through the neighbour table (x / y signed >= 0, unsigned < nx / ny, map id, cell, walkable 0 10 8 9) = GetNeighbor(.., true), count then end |
| 77 | 16 | 0x1a56d0 | 716 | CAiMap::CountMapVisDir | zAI/ai_mapwalk.cpp | DEVIATION-KEPT | | recorded: void where the ELF returns 1 (caller 0x259830 overwrites v0). Rest matches: neighbour off the map or no cell -> counts = depth when the map id is not 0, stop; soil 0 / 8 / 10 stops; end then count |
