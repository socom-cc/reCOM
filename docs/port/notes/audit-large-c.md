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
