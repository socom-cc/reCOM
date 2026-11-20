# Targeted audit of the large zSeal / zAI functions, list A (2026-11-15, socom-port-large-a)

Question: the sample audit ([audit-sample.md](audit-sample.md)) found defects in 20% of the marked
functions of 700 bytes or more, mostly in zSeal and zAI. List A is every such function of
`ai_map.cpp`, `ai_mapio.cpp`, `ai_search.cpp`, `ai_vismap.cpp`, `seal_airesponse.cpp`,
`seal_aiscan.cpp`, `seal_cfg.cpp`, `seal_env.cpp`, `seal_handsig.cpp`, `seal_kit.cpp` and
`seal_sensors.cpp`: 98 functions, 138,068 bytes. They were audited largest first so that an
unfinished session covers the most code. This session judged the 57 largest (rows k = 1..57, 104,232
bytes, 75% of the list's bytes); rows k = 58..98 (41 functions of 700..964 bytes, 33,836 bytes) are
left for a follow-up worker.

Method (as the sample audit): each row disassembled from `support/socom.elf` (`z.sh`, raw `dis.sh`
where the compaction hides an address, `sym.py` for jump tables, `dw.py` / `mem.py` / `off.py` for
layouts, `denum.py` / `animenum.py` for enumerators) and compared with the port's body instruction
by instruction: branches and their sense, stores (offset, width, bitfield), calls and argument
order (stack arguments included), loop bounds, signedness, return values, vtable slots, jump
tables case by case, inlined helpers against the helper the port calls. Every float constant was
checked against the ELF word, both rounded to nearest and truncated (the pinned GCC truncates,
[float-constants.md](float-constants.md)): all were right. HEAD 24f811a3; no marker was added,
moved or changed and no function moved file.

Verdicts: MATCH; DEFECT-FIXED (A: can change what the player sees or crash; B: wrong but masked on
the demo disc; C: cosmetic); DEVIATION-KEPT (differs for a reason recorded in a comment or note);
UNJUDGED (none).

## Counts (rows k = 1..57)

| Verdict | Rows |
|---|---|
| MATCH | 33 |
| DEFECT-FIXED | 14 (A 1, B 2, C 11) |
| DEVIATION-KEPT | 10 |
| UNJUDGED | 0 |
| total | 57 |

2026-11-20 (audit-closeout follow-up): k = 21 / 37 / 41 (#28 BaseAnim_0, #79 HandleRemotePlaceExplosive, #74 UpdateAiMapLoc) are DEFECT-FIXED C, their guards removed with Lead B (part 2); k = 26 and 57 lost their guard part there and stay kept for the rest. The rates below are as first judged.

Rates (exact Clopper-Pearson 95% intervals): all defects 11 / 57 = 19.3% (10.0% .. 31.9%), the same
as the sample's 20% for functions of 700 bytes or more; grade A 1 / 57 = 1.8% (0 .. 9.4%); A or B
3 / 57 = 5.3% (1.1% .. 14.6%); grade C 8 / 57 = 14.0% (6.3% .. 25.8%). Seven of the eleven are one
kind of rounding difference (below); the others are a test the port wrote wrong, a stack argument,
a flag the port did not set and a guard the ELF does not have.

## Fixes (ELF addresses)

- k = 56, `CZSealBody::SealProcessAltitude` 0x2a2c70 (seal_env.cpp), A: the ELF keeps the old
  `m_inwater` on the stack before clearing it (0x2a2d18, sp+0xb0) and, after the hit loop, stops the
  below-water and in-water anims when the body was in water and is not any more (0x2a2ef8). The port
  tested `m_inwater && !m_inwater`, which is never true (its comment called this an ELF quirk), so a
  wading effect started by `HandleWater` kept running on a body that had walked out of the water.
  Visible on any level with water; whether m8 uses a LIQUID soil was not established, and no run
  shows a water crossing.

- k = 4, `CZKit::Fire` 0x2acd70 (seal_kit.cpp), B: both weapon `Fire` calls pass the model as NULL
  in the ELF (the ninth argument goes on the stack: `sd zero,0(sp)` at 0x2adc90 and 0x2add64). The
  port passed the projectile's model, so `CZProjectile::SetProjectile` called `SetModel` a second
  time with the model the instance already had (a name strdup / free, no visible change). Also the
  0x2aceac squared distance (C, below).
- k = 8, `CSealCtrlAi::SensorPreTick` 0x2b21e0 (seal_sensors.cpp), B: a successful STATE_CQB push
  also sets the flag that keeps STATE_AVOID from being popped after the target loop (0x2b24e4:
  `daddiu s6,zero,1`, the 1 the setup bit is or'ed with, in the register of that flag). The port
  popped STATE_AVOID after a CQB push. Masked: it needs an AI team mate of the player, avoiding him,
  that starts a knife attack in the same frame.
- Grade C, the sum order of squared lengths and dot products: the ELF computes `(x x + y y) + z z`
  (`mul`, `mul`, `adda.s`, `madd.s`); the port wrote `z z + x x + y y` (the order Ghidra prints the
  adda / madd pair in), which rounds differently by at most an ulp near a threshold. Fixed where the
  y term is not zero: k = 2 `ChangeWeapon` 0x2971bc (still <= 400), k = 3 `PostCheckDIDown` 0x29f504
  (landing speed < 400), k = 4 `Fire` 0x2aceac (threat range 550^2), k = 7 `CheckDIShoot` 0x29b004
  (prone lift length), k = 22 `HomingTick` 0x2a10cc (turn angle dot), k = 24 `CheckDIFwd1` 0x2a1d90
  (hit distance) and 0x2a20b8 (body z . wall normal, 0.65), k = 28 `PitchAnim` 0x29c88c (reticle
  distance < 900) and 0x29cb78 (fire-point . aim goal, 0.999), k = 31 `HandleSealStep` 0x291be4 /
  0x291c30 (crouch / prone speed > 0.5). Sums whose y term is exactly zero (`ImpactFront`,
  `CheckDIFwd1`'s away vector, `PostCheckDIDown`'s throttle direction) give the same word in either
  order and were left alone.

- k = 55, `CZSealBody::DropItem` 0x28e3e0 (seal_env.cpp), C: the drop anim reads the pickup's node with
  no NULL test (0x28e778); the port had added an unrecorded `pickup != NULL`. `CPickup::Create`
  returns NULL only while the pickups are closed, so no run reaches the difference.

The one grade-A fix (k = 56) needs a seal leaving water; neither B fix changes a path the demo
shows: the model was already set, and the CQB / avoid overlap needs a rare frame. The runs below
show the game unchanged.

## Kept deviations (recorded; not counted as defects)

- Data the disc does not have: k = 5 `CAiMap::Read` and k = 49 `CAiMap::read_cells` do not read map
  versions 2..18 / cell formats before 17 (every map on the disc is version 19).
- Unset stack words the ELF reads (a value the port cannot reproduce; the port uses the evident
  value, recorded): k = 6 `CAiVisMap::CheckBoxEdges` (the ring cell's map id), k = 36
  `CAiMap::UpdateVisibilityMap` (the line end's map id), k = 51 `UpdateDynamicVisMap` (the box name and,
  without a cell, the eye altitude), k = 38 `CAiSFlee::Tick` (phase 5 routes to
  the cover cell, where the ELF passes the word beside it, sp+0x54), k = 26
  `HandleGrenadeExplosion` (location 0 without fragments).
- NULL tests the ELF does not have, recorded in comments: k = 4 `Fire` and k = 37
  `HandleRemotePlaceExplosive` (the STATE_DEPLOY write, which the ELF makes through NULL + 0x54 when
  the top state is not STATE_DEPLOY), k = 8 `SensorPreTick` (the pushed state; the pickup bit vector
  and the unit), k = 21 `BaseAnim_0` (the bottom blend), k = 26 `HandleGrenadeExplosion` (the
  shooter's controller), k = 31 `HandleSealStep` (the footstep tables before a mission), k = 41
  `UpdateAiMapLoc` (the mission abort valve), k = 55 `DropItem` (the item model), k = 57
  `PickupAmmo` (the box; at most 8 entries asked).
- Writes the ELF makes out of bounds: k = 13 `HandlePickupAck` reads and clears box entry i when
  size >= i (one past the end; the port stops at the size), k = 39 `visCallback` (marks outside the
  vis box are skipped; the ELF writes past the bits on the m8 maps).

## Leads

1. The z-first sums are systematic (Ghidra's print order of adda / madd). After these fixes 50 sites
   remain in `src/` (`grep -E "\.z \* \S*\.z \+ \S*\.x \* "`): seal_env.cpp 12 (rows k > 50 and the
   exact zero-y ones), seal.cpp 9, zwep_projectile.cpp 6, seal_weapon.cpp 5, seal_kit.cpp 3,
   seal_body.cpp 3, hud_mapcompass.cpp 3, seal_ai.cpp, int_bbox.cpp, ent_target.cpp 2 each,
   zparticle_source.cpp, zmath_main.cpp, hud_main.cpp 1 each. Each is a grade-C fix when the ELF's
   function has the adda / madd order and the middle term is not zero.
2. Stack arguments: the only B defect of this kind (k = 4) was an argument that goes on the stack
   (the ninth word). Calls with eight or more argument words are worth a pass: the compacted
   listing shows the stack store far from the call.
3. Register reuse as a constant (k = 8): MW materialised the constant 1 in the register of a live
   local, which is the source setting that local. Look for `or ...,sN` with sN a local's register.
4. Comments that call a behaviour an ELF quirk can be wrong (k = 56 called a stack copy of the old
   flag a never-true test). A comment's claim is not evidence; check the quirk against the listing.
5. The kept NULL guards above (nine functions) differ from the ELF only where the ELF writes or calls
   through NULL; whether to keep them is the coordinator's decision, as for the sample audit's
   row 48.
6. Rows k = 58..98 of `build/port/unmarked/large-audit-a.md` (size order) are not audited yet.
## Runs

All boots: isolated tree (HEAD plus the three changed files; the other workers' uncommitted files
kept out), second monitor, focus kept in every run. Screenshots (untracked) in
`build/port/screenshots/59-large/`.

- st1 (fixes of rows k = 1..25, HEAD 24f811a3; zseal4's `hook_zseal1.cpp` + `pad_fire.txt`, 250 s):
  intro movie skipped with CROSS, cameras with X (61 s), 182 s in m8; no STOP, no exception; 79
  "fires at" lines, kills and recycle / respawn timers, team FOLLOWING; heap in use 23.18 MB from
  200 s to the end.
- st2 (all 57 rows, HEAD 24f811a3, same hook, 250 s): cameras skipped at 60.5 s, 189 s in m8; no
  STOP; 85 "fires at" lines; OutPatrol1 / 3 killed (alive 0 at 86 s), recycle 4.3 and respawn
  (alive 1 at 98 s); FOLLOW modes; heap 23,223,084 B from 200 s to the end (steady).
- win1 (`port/test-hooks/win`, -DSOCOM_HOOK_WIN, same tree, 265 s): Snow3 rescued in Extract at
  238.0 s, mission_complete 0 -> 1 at 242.0 s, "EXIT: debrief open (objectives 3/7)" at 243.9 s,
  MISSION SUCCESSFUL on screen (3 of 5 primary, 7 of 8 secondary).
- sr1 (`port/test-hooks/state`, -DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4, same tree): four
  missions and returns, in use 18,657,260 B at every return to the menu (flat); idle after the
  fourth.
- la-def (default build, same tree): links (no boot; the coordinator's gate runs the full check on
  the merged commit).
- sm1 (smoke run on HEAD a41588a5 plus the three files, same hook as st2): cameras skipped at
  57.7 s, 159 s in m8; no STOP, no exception; 36 "fires at" lines, OutPatrol1 killed (alive 0 at 84 s)
  and respawned (recycle 4.3, alive 1 at 98 s), team FOLLOW modes; heap 23,150,012..23,150,332 B from
  150 s to the end (steady). (An earlier 165 s run, sm1, reached the cameras only at 110 s.)

`python tools/socom.py audit independence --strict` passes.

## Result table (k = size rank in list A, # = row of large-audit-a.md)

| k | # | Address | Bytes | Function | File | Verdict | Grade | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | 27 | 0x27eda0 | 5976 | CZSealBody::ReadMotionRdr | zSeal/seal_cfg.cpp | MATCH | | set lookup, per-anim strings/reals, BodyAddAnim, ladder 0x10, Setup(10 v), callbacks (time > 1 / TrueLoopTime), flag tags, common once (NoFire/NoInterrupt 0/1, BlendTime 0.4, Normalize), blendables, refPt (new 16 pushed even NULL), objects_ready; strafe 0x100 (12,14,69,13,15,70,22,23 + "Crouch strafe left"), moving 0x20, 30 climb types 0x8, push/pop, snap, player_ |
| 2 | 54 | 0x297060 | 4900 | CZSealBody::ChangeWeapon | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x2971bc: still test is (x x + y y) + z z <= 400 (adda/madd); port summed z first. Rest matches: guards (8/top 8, 9/10, carry, stunned, 3, airborne, 6, changing/reloading, CQB), per to/from/state paths 56/57/58 with reverse flag, part moves, gear, aim nodes, m_item = to tail |
| 3 | 67 | 0x29eb00 | 4768 | CZSealBody::PostCheckDIDown | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x29f504: landing speed (x x + y y) + z z < 400; port z first. Rest matches: probe, altitude inline (= SealGetAltitude), last-altitude copy, climb exits, timers, gravity, falls 11.487 (0x4137cac0 read), material offset, touch distance, landings, JumpFall push, shadow light, hop-down probe (1: unused; 2/3: drop > 8; the ELF's speed > 20 test has identical branches) |
| 4 | 90 | 0x2acd70 | 4400 | CZKit::Fire | zSeal/seal_kit.cpp | DEFECT-FIXED | B | 0x2adc90 / 0x2add64: both weapon->Fire calls pass model NULL (sd zero to the 9th-arg slot); the port passed the model, so SetProjectile set it a second time (same model: masked). Also 0x2aceac sq order (C). Rest matches: unit notify, threat arcs (offsets 0xde9.., 0xdf0.., 0xe10..), launcher slot, net msgs, wiggle, models, tracer >= 30, reload-after-shot, 181/11 out, align, flyout/tracer/isplayer, instance setup, grenade fire anim, kick, fuses per id, M203 reload, fire anim args, stats, recoil. Kept: the deploy-state NULL+0x54 write guard (recorded in the comment) |
| 5 | 6 | 0x189390 | 3688 | CAiMap::Read | zAI/ai_mapio.cpp | DEVIATION-KEPT | | versions 2-18 not read (recorded: no such map on the disc). Version 19 (164-byte params, tables 184..232, lines/readers/routes, map ex), < 12 / < 15 / < 17 fixups, Validate/Routes/Graph as the ELF |
| 6 | 11 | 0x1a0fc0 | 2888 | CAiVisMap::CheckBoxEdges | zAI/ai_vismap.cpp | DEVIATION-KEPT | | ring cell's map id set to the box's (recorded; the ELF leaves that stack word unset and CanTravelLine reads it). Centre / closest corner (|dx| + |dy|, x unsigned / y signed), rows then columns, bounds, mark (u8), walkable (inline GetCell / soil 0,8,9,10), travel line, out map id as the ELF |
| 7 | 60 | 0x29a850 | 2788 | CZSealBody::CheckDIShoot | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x29b004: prone lift length is sqrt((x x + y y) + z z); port z first. Rest matches: AI / remote out, range max(600) / mid plane, ray, bbox globals, shootable (material, camera type 1, volumetric, liquid, 0.99 / bit 4), nearest solid (action dist follows it, quirk), action nodes, auto aim, reticules, GetAP, prone lift -10 / len, block test (binoculars 182, weapon state 1 / 18, 0.008), screen position, size max |
| 8 | 97 | 0x2b21e0 | 2748 | CSealCtrlAi::SensorPreTick | zSeal/seal_sensors.cpp | DEFECT-FIXED | B | 0x2b24e4: a successful CQB push also sets the flag that keeps STATE_AVOID (s6, the 1 or'ed into the setup bit); the port popped STATE_AVOID after a CQB push. Masked: needs an AI team mate avoiding the player while starting CQB. Rest matches: fire slot / di pool, thresholds 225 / 625 / 2500 / 200, CQB (visible, not dirty, flags & 2), aware, avoid, perception, vis rate, grenade pickups (bits, unit visibility, thrower, ally, sound 49, radius, STATE_GRENADE, STATE_EVENT delay). Kept, recorded: NULL tests of the pushed state, of the pickup bit vector and unit |
| 9 | 85 | 0x2aa7a0 | 2684 | CZKit::TickExplosives | zSeal/seal_kit.cpp | MATCH | | remote 1, no item 0, fire timer, 151 C4 / 152-154 placed / thrown, hand point, C4 probe 16 (characters off, material 1, INVISIBLE_DI, volumetric, liquid), ground 14.3, HandleRemotePlaceExplosive, last selected; throw: burst, ammo, offsets (2,0,0), peek-left hand, player (max vel, asin elev, ofs, 0.3 speed mix, quadratic -49, reach, do_adjust speed, dir, elevate, rotate, Fire), AI (transform, UpdateThrowFireParams, throw vec, flags 0xfdefffff, timeout) |
| 10 | 22 | 0x2e8590 | 2548 | CAiSShotAt::Tick | zSeal/seal_airesponse.cpp | MATCH | | jump table 0x458090 (6): hold / creep, duck (0.25 prone, 0.2 + 0.5 r), aware 3, frantic look, speed 1, cover (5 cells, route, path mode, noturn, 5 + 5 r), dodge (ChooseLookDir, 3 walkable neighbours, GetCellPos, goal 3, reversed dir, 2.5 s), cover wait 0.5, end, dodging back (underfire double compare, goal 5), walking back |
| 11 | 51 | 0x295ae0 | 2360 | CZSealBody::DamageHead | zSeal/seal_env.cpp | MATCH | | network (remote shooter out, flinch 53, report args, first hit, remote self out), single (Hit / WasHit, head shot once by non-explosive), shotgun / normal damage, inline head damage (0 / 0.5 / 0.99 levels, +3 retmods, flinch loc 0), killer |
| 12 | 95 | 0x2b1110 | 2048 | CSealCtrl::SensorTick | zSeal/seal_sensors.cpp | MATCH | | target sum, ComputeThreat inline (statics, WEP / hostile / facing x,y,z / vertical / buddy training / range), enemy max / sum / last visible, buddies (not STUNNED), di take (state 4), visibility blend, see, invisible, OnSetTargetVisible, SetTarget slot 0xa0, threat goal (outnumber factors, means, >= 0) |
| 13 | 29 | 0x28c5c0 | 1964 | CZSealBody::HandlePickupAck | zSeal/seal_env.cpp | DEVIATION-KEPT | | the ELF reads (and clears) box entry i when size >= i, one past the end; the port uses i < size (recorded). Bits 0-7 with count, weapon at bit 0, ammo entries, PendingPickupHandled, CleanupAmmoPickup as the ELF |
| 14 | 47 | 0x294210 | 1836 | CZSealBody::UpdateHealth | zSeal/seal_env.cpp | MATCH | | body 0.1/0.3/0.7/0.9 (0x3f333333 / 0x3f666666 read), head 0 / 0.5 / 0.99, limbs, (4 h + 4 b) + larm + rarm + rleg + lleg / 12, death (SetHealth 0, death anim unless remote, state 8, drop, player sound 255, hud hit), lower health hud hit |
| 15 | 96 | 0x2b1980 | 1828 | CSealCtrlAi::OnSetTargetVisible | zSeal/seal_sensors.cpp | MATCH | | dirty di, first sighting (navy seal callout / startled STATE_EVENT: cur alive, visible, 3 s), times seen, known, event reset, OnSetVisible, AIA 4, threat inline, UpdateTarget; lost sight POI 1 + 3 r (AIE 2), AIA 3. The port's NULL test of the event position cannot fire (the entity is dereferenced first) |
| 16 | 23 | 0x2e3bf0 | 1820 | CSealCtrl::ScanTick | zSeal/seal_aiscan.cpp | MATCH | | GetLookDir dropped, types 1 (minRange 10, inverse quat) / 2 / 3, bias, normalize, 0.97 threshold (x,y,z), rate draw, SetLookDir speed r_min..r_max, goal dir 1 (flags 2 / 1), look timeout to defaults, scan timer draw, angle (flag 8 / swing 0.5..1 by bias side), bias = (sin, 0, -cos) - unit_nz |
| 17 | 14 | 0x2e4ab0 | 1812 | CAiSRush::Tick | zSeal/seal_airesponse.cpp | MATCH | | target seal alive, flags 1 (time) / 2 (range_sq, x,y,z) / 4 (visible target), phases 0-3: walkable cell + route + cry 64, route failed (flag 8 -> 3), rush_threshold 4 (unsigned), straight chase (CanTravelLine, ClearRoute, AppendPathLoc), arrival, wait < 2 cells |
| 18 | 1 | 0x1853a0 | 1796 | CAiMap::GetCellRepelParams | zAI/ai_map.cpp | MATCH | | cell / link out, centre (inline GetCellPos with action offset), quadrant (x <= 0, z < 0 -> 0/2/4/6), half cell, two directions (+0, +2) % 8, bounds, blocked neighbour, along (x,y,z) > 0, overlap = half - (along + r) < 0 pushes, depth 1. The ELF leaves the neighbour's map id unset; GetCell ignores it |
| 19 | 93 | 0x2affe0 | 1744 | CSealCtrl::ComputeVisibility(di, node) | zSeal/seal_sensors.cpp | MATCH | | diNonVolCount, sorted hits, diStopper, material NULL blocks, volumes entered / left (node match, sqrt dist), opacity (particle system: GetBBox volume z (x y) x visual density x depth), solid count, saturates, open volumes to the line's end (x,y,z length), vis saturated |
| 20 | 66 | 0x29dd90 | 1724 | CZSealBody::InitLookAnims | zSeal/seal_env.cpp | MATCH | | 4 bones x 12 ComputeDeltaLookQuat calls, pairs (1,2) (5,2) (4,5) (4,1) (1,0) (3,0) (4,3) (7,8) (5,8) (4,7) (7,6) (3,6) into dQlook*/Rlook* +0x10 / +0xc; the port copies the tables first (they are not written) |
| 21 | 28 | 0x280500 | 1712 | CZSealBody::BaseAnim_0(anim, item) | zSeal/seal_cfg.cpp | DEFECT-FIXED | C | kept earlier; guard removed with Lead B (part 2, below; row corrected 2026-11-20). Earlier: the port tests the bottom blend for NULL (recorded; the ELF reads it unchecked). Item remap (Stand bottom -> rifle), pistol stance/climb types 37/35/41/47/16/36/26/18/1 -> PistolAnim, the 19 action types (separate ifs, signed 16-bit), rifle BaseAnim, fallback to anim, as the ELF |
| 22 | 69 | 0x2a0f20 | 1712 | CZSealBody::HomingTick | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x2a10cc: the turn angle's dot (norm . refvec) is (x x + y y) + z z; port z first. Rest matches: homing member test (quirk), tfrac reversed, offset, inverse quat, TrueLoopTime dropped, acos / dT clamp 2 pi, cross sign and length, drot, half-turn Exp, refpt -= vel dT, Align, VU0 rotates, quadW, hang / ladder exit height blend, step, motion, ladder entry y 0, per-axis 0.8 / dT clamps, dpos |
| 23 | 17 | 0x2e5e80 | 1688 | CAiSEvent::Tick | zSeal/seal_airesponse.cpp | MATCH | | target-seen (0x10) / underfire > 1.0 double (0x20) exits, jump table 0x457fc0 (10): react (sound 63 + flinch right/left 0.5, or sound 20), look (AIL 3, timer draw, scan 0x3eb2b8c2, next draw, stateFlags 1), look source (flags 1), route (GetLocation vec/pos, SetRoute, limit 5000), travel (path states 1/2/3 mode 1, points + complete mode 3), arrived 0.25 / next 6, waited, wait, look around (ChooseLookDir, flags 5, scan 0x3e860a92, 0.5), last look |
| 24 | 70 | 0x2a1bb0 | 1684 | CZSealBody::CheckDIFwd1 | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x2a1d90 hit distance and 0x2a20b8 body-z . normal are (x x + y y) + z z; port z first (the other z-first sums here have a zero y term, exact either way). Rest matches: jump action, root transform, probe (unused), 1.2 / 8, away (y 0, length, -1), 0.65 tests -> ctrl 3, ImpactFront, appflags 2 keeps the hit, throttles / velocities cleared |
| 25 | 81 | 0x2a8a00 | 1684 | CZKit::HandleFireWeapon | zSeal/seal_kit.cpp | MATCH | | designator (fetch when map name or anim NULL, reset, start sound), binoculars out, claymore (< 4, message), satchel, C4 (PutOnWall 65, Timer_PlaceC4 at 0.45 on m_firetime, 99), detonator, MP bomb 2.25, throwables (abort threshold, IsThrowing, BeginThrowItem), guns (burst, launcher grenade slot ammo, fire delay, firepoint_203 / firepoint, player launcher +0.15, PerturbAimVector slot 0x74, quat, Fire with velW) |
| 26 | 39 | 0x28f840 | 1644 | CZSealBody::HandleGrenadeExplosion | zSeal/seal_env.cpp | DEVIATION-KEPT | | recorded port guards: the shooter's controller NULL test before NotifyTargetDown (the ELF calls through it) and location 0 when there is no fragment (the ELF passes an unset stack byte). Sight-line walk (own nodes, nearest beyond the last, material NULL continues, particle / liquid / pickup pass), stuns by id (171/153/152/151/126/121 -> 4 2 s, 161 -> 5 100, 122 -> 3 2, 125 -> 1 3, 123 -> 0 2), player ringing (not 81-84, 1 - d2/r2, PlaySound3D slot 0x24) and wiggle (not 123), fragments, UpdateHealth(loc, 4), killer, cleanup, top state 8, as the ELF. 2026-11-20: the shooter's controller test went with Lead B (part 2); the unset location byte stays kept |
| 27 | 4 | 0x186430 | 1536 | CAiMap::ValidateCells | zAI/ai_map.cpp | MATCH | | names (ValidateName, row span, GetCell, name bit 6), empty action walk, links (dummy cell, soil 0/8/9/10) counted, whole-map region, foreach rows saturated to the scanlines, columns max/min of the span, _validate_cell stops the walk, returns the bad count |
| 28 | 63 | 0x29c620 | 1484 | CZSealBody::PitchAnim | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x29c88c reticle distance and 0x29cb78 fire-point . aim goal are (x x + y y) + z z; port z first. Rest matches: state 2 / weight out, conj spine quats, forwards, rotations, near (900, not remote), passes (lo 0.1 / hi 0.4 weight cross, Exp, Mul), aim point checks, re-aim, 0.999, at most 6 passes |
| 29 | 42 | 0x291190 | 1404 | CZSealBody::WeaponHitAnim | zSeal/seal_env.cpp | MATCH | | remote / undefined out, carry dropped in state 1, carrying (death only, DropBody), 10 / stabbed / CQB victims out, falls (death marks top 8), dying replay (single player, 0.05..0.5, < 2, loc 3), dead body death anim, death (ctrl 0, peek 2, stance change ClearStack 1/2, ladder FallBackward01, ClearToBase), state 3, stance change, 5/9 out, interruptible 0x40 / stretch-slouch pop, mirror flag 0x40 |
| 30 | 83 | 0x2a9c20 | 1384 | CZKit::Tick | zSeal/seal_kit.cpp | MATCH | | reticule / flashlight / laser, pickup wait, explosives, burst by fire mode (0 / 1,>=4 / 3 / 10000 / else 0; 1 without ammo), fire (raise dropped), empty click (not 182/186/187/183/11, direct fire, burst, trigger 1/2, sound < 2, reload or count; net pistol reload), fire delay, CurItemHasAmmo, launcher cycle, mode 0 cycle |
| 31 | 43 | 0x291b60 | 1376 | CZSealBody::HandleSealStep | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x291be4 / 0x291c30: the crouch / prone speed is sqrt((x x + y y) + z z); port z first. Kept (recorded): NULL tests of the m_sealstep / m_steptexhandles tables. Rest matches: footstep flag, moving (speed state >= 2 standing, else > 0.5 crouched / prone), top flag 0x40, frac, left (0..0.5, not airborne) / right (0.5..1), did flags, foot point, footfall anim, sound, footprint decal (not on a character's decal node, -normal, 100, 3.5, body z) |
| 32 | 44 | 0x292380 | 1376 | AnimSet::ReadFlinchAnimations | zSeal/seal_env.cpp | MATCH | | shared ReadAnimLists: tag, STAND / CROUCH / PRONE (unchecked), entries NAME / PISTOL_NAME, FindAnimType rifle then pistol pushed to damageanim / pistoldamageanim [loc][stance], SetPistolAnim on AnimSet::list[0]'s CAnimsByFP |
| 33 | 45 | 0x2928f0 | 1376 | AnimSet::ReadDeathAnimations | zSeal/seal_env.cpp | MATCH | | instruction stream identical to row 32 but deathanim / pistoldeathanim (diffed) |
| 34 | 46 | 0x292e50 | 1376 | AnimSet::ReadTeammateDeathAnimations | zSeal/seal_env.cpp | MATCH | | identical to row 32 with teammatedeathanim / teammatepistoldeathanim (diffed) |
| 35 | 21 | 0x2e8030 | 1360 | CAiSReload::Tick | zSeal/seal_airesponse.cpp | MATCH | | phase 0 (speed 1, noturn, weapon state 2, old stance, draws 0.07 / 0.25 / 0.5 with a living target, evade spot from the target's vis map (unchecked answer), |dx| + |dy| < 10 and route -> path mode), 1 (cry 61 PlayAt, evading: stand until the route is done; else crouch / prone from standing, Reload, 0.5 s), 2 end |
| 36 | 10 | 0x1a0950 | 1348 | CAiMap::UpdateVisibilityMap | zAI/ai_vismap.cpp | DEVIATION-KEPT | | the line's end cell takes the eye cell's map id (recorded; the ELF leaves that stack word unset). States 0 / 1, top / bottom rows (x to box x + dx - 1, unsigned), left / right columns (y from box y + 1 to < y + dy - 1), reset_line (MINIMUM_SLOPE 0xd8635fa9), WalkLine with visCallback, line / budget counts, state moves on when the budget runs out (quirk), 1 |
| 37 | 79 | 0x2a6ed0 | 1332 | CZKit::HandleRemotePlaceExplosive | zSeal/seal_kit.cpp | DEFECT-FIXED | C | kept earlier; guard removed with Lead B (part 2, below; row corrected 2026-11-20). Earlier: the deploy-state write is NULL-tested (recorded; the ELF writes NULL + 0x54 when the top is not STATE_DEPLOY). MP bomb (30, network RequestNewBombState 3 / mission win-loss timer), C4 5 timed, satchel (mission timer, < 0 none), claymore remote removal 10, other out; XRef instance (inactive, model, pos, rot, character, texture set 2, active), isplayer, SetProjectile (model passed), pickups 4/5/6/7, echo and HUD timer for the player's team, remote flag, list insert, ammo, detonator, HUD weapon flag |
| 38 | 16 | 0x2e5850 | 1268 | CAiSFlee::Tick | zSeal/seal_airesponse.cpp | DEVIATION-KEPT | | phase 5 routes to the cover cell FindCoverLoc found (recorded; the ELF calls SetRoute on the unset stack word beside it, sp+0x54). Jump table 0x457f70 (7): safehouse region / random loc / cry 65 at 0.75 / stand / speed / no target, plan states (unit path proximity 4 / 30), arrival, STATE_HOLD (returns at once), re-choose (rush 50 / surrender 50), cover 10 cells (5 s) or 3 s, cover route wait, stateFlags bit 0 on a change |
| 39 | 9 | 0x1a0460 | 1264 | visCallback | zAI/ai_vismap.cpp | DEVIATION-KEPT | | marks outside the box are skipped (recorded in vis_set_mark: the ELF writes them unchecked, past the bits on the m8 maps). Statics 4.5 / 9 / 18 / taxi cab, blocking soil 0/8/10 unseen + stop, altitude, rise, run 10 x dist (taxi or sqrt), eye cell seen, horizon raise (ground > top, slope), seen test (rise + 18) / run, 1 |
| 40 | 76 | 0x2a5040 | 1264 | CZKit::SniperTick | zSeal/seal_kit.cpp | MATCH | | adrenaline (1 without), heartbeat (> 0.2, not binoculars: 0.3 + 0.24 c / 0.8 + 0.64 c, rumble 0.1 / 0.16 at 20 + 100 a), kick (rate, move dist, return to baseline), wander x / y (limits 0.8 l a + 0.2 l / 0.2 l + 0.8 l a, out at <= 0.2, |pos| / limit, (0.25 + d) + (0.75 + d) r, bounce), all float words read |
| 41 | 74 | 0x2a4700 | 1260 | CZSealBody::UpdateAiMapLoc | zSeal/seal_env.cpp | DEFECT-FIXED | C | kept earlier; guard removed with Lead B (part 2, below; row corrected 2026-11-20). Earlier: the mission abort valve is NULL-tested (recorded; the ELF sets it unchecked). GetLocation, m_mapLoc, walkable cell (map NULL out), changed cell: valid loc, snake point, vis map update when asked, occupied mark when alive; last valid position; player boundary sounds (0 / 1 / 2 by GetBoundary of old and new cell, not on the network), valve set to 1 with callbacks on a change |
| 42 | 68 | 0x2a0a40 | 1244 | CZSealBody::ImpactFront | zSeal/seal_env.cpp | MATCH | | away (y 0, -1), unused cross, pos = probe tail, facing (the z-first sums here have a zero y term: exact), < 0.65 out, six climb anims or 0, edge points, foot offset height, app flags 3 (30) / 2 (ladder, 15, Rotate180 -99, down) / 5 (over) / 1 (beside true) / 4 (5..32) / else -99, AlignForClimb(down only for 2) |
| 43 | 91 | 0x2aedc0 | 1232 | CZKit::CZKit | zSeal/seal_kit.cpp | MATCH | | every store mapped to the DWARF layout (30-slot arrays, reloads 30 x 10, bitfield word bits 0-14 and m_unused 15-31, reticule 2, heartbeat on, m_sniper_prev_posx cleared twice (quirk), reserve 8, camera screen offset from the sniper position) |
| 44 | 25 | 0x27e1b0 | 1224 | CZSealBody::MixAnims | zSeal/seal_cfg.cpp | MATCH | | wt <= 0 / no set out, target |speed| 100 thr scale, up to 4 blendables (min t0 / max t1 anims, (t0, t1] picks from the top blend or the pool, Reset, SetTimeScale slot 0x14, hi / lo), none: lowest / highest at their range end (signed), RenormAnims 1 - wt, two-way split by (target - lo) / (hi - lo) with PutBack, PushAnim |
| 45 | 15 | 0x2e5290 | 1204 | CAiSPathRecover::Tick | zSeal/seal_airesponse.cpp | MATCH | | locs, GetCellCenter unused, init (same cell -> 2, goal 6 at last valid pos 3.0 + creep, else end), creep (same cell -> 2, no goal -> 4), register (path complete with points, at dest end, RegisterPathPlan -> 3), plan (wait states, points 0..n-2 inserted), complete (4) |
| 46 | 2 | 0x185b50 | 1172 | CAiMap::TransformTo | zAI/ai_map.cpp | MATCH | | other NULL out, this map's cell position (inline GetCellPos, off the map 0), the other map's GetLocation inline (x/z box, truncated grid, map id 0, grid bounds), other map id on success |
| 47 | 94 | 0x2b06b0 | 1168 | CSealCtrl::ComputeVisibility(di, target) | zSeal/seal_sensors.cpp | MATCH | | line visibility via the node version, non-seal returns it, blocked 0, range <= 0 returns the line, -1 / h^2, stance x2 / x1.5 (GetStance twice), water w_func (bbox / depth, 1 -> 0.5), (1 - w) + 2 w, fog 0.5..1 on range, cover (prone 5 / 2 x range, crouch 2.5), 1.25 + k r^2 |
| 48 | 41 | 0x290aa0 | 1128 | CZSealBody::RemoteWeaponDamageVictim | zSeal/seal_env.cpp | MATCH | | NULL shooter / victim out, first hit stats, first head hit (count, this body's head armour, levels, flinch, head shot), part damage while alive (1 rarm, 2 larm, 3 body, 4 rleg, 5 lleg), body damage again (flag always 1, quirk), victim != this: UpdateHealth(5); this: killer weapon, killer unless remote, alive clears (-1) |
| 49 | 5 | 0x188f60 | 1072 | CAiMap::read_cells | zAI/ai_mapio.cpp | DEVIATION-KEPT | | the < 17 cell formats are not converted (recorded with Read's left-out versions). < 15 count nx ny and uncompressed, malloc line 597, memset, raw read from 17, 1 |
| 50 | 62 | 0x29bff0 | 1072 | CZSealBody::HandleFallingDamage | zSeal/seal_env.cpp | MATCH | | land sound of the ground material, network non-player / invincible / network again out (0), dead or carried level 0 (still the sound), land speeds +0x30..+0x38, level 3 reads the AI map altitude and position for nothing (quirk), 2/3 sounds and full damage to every part, 1 adrenaline 0.33 (0x3ea8f5c3), UpdateHealth(3, 7) |
| 51 | 12 | 0x1a1f10 | 1004 | CAiVisMap::UpdateDynamicVisMap | zAI/ai_vismap.cpp | DEVIATION-KEPT | | recorded: the box name is zeroed (the ELF copies an unset stack name) and the eye altitude is kept when the cell is NULL (the ELF stores an unset FPU register). Map change (invalid loc, nosee_byte 0 memset, state 1 -> 2, recursion), map NULL 0, box (width / height), CenterRegion, GetCell altitude (0x3a800004 read), m_map, state 1 -> 2, 1 |
| 52 | 87 | 0x2ab530 | 984 | CZKit::Reload | zSeal/seal_kit.cpp | MATCH | | body NULL / airborne / dead / throwing / reloading out, launcher grenade slot (firemode[selected] - 3), loaded test (index < items, 10 mags), next loaded mag search with wrap, body Reload (NULL out), current mag, sound slot 0xc, network pistol refill (capacity) when none, weapon-info flag, return |
| 53 | 7 | 0x1a9590 | 980 | CAiMap::FindLookLoc | zAI/ai_search.cpp | MATCH | | shared find_spot: GetCellPos inline (off map 0), SubXZ, y 0, sqrt(x x + z z), normalise when not 0, GetClosestDir byte, find data (loc, target, dist), FloodFill(loc, (s8) dir, depth, _find_look), out |
| 54 | 8 | 0x1a9970 | 980 | CAiMap::FindCoverLoc | zAI/ai_search.cpp | MATCH | | instruction stream identical to row 53 (diffed) with _find_cover 0x1a9e40 |
| 55 | 35 | 0x28e3e0 | 976 | CZSealBody::DropItem | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x28e778: the drop anim reads the pickup's node with no NULL test; the port added an unrecorded `pickup != NULL` (Create returns NULL only while the pickups are closed). Kept (recorded): the item-model NULL test. Rest matches: network non-player out, item count, FillWeaponEnum, pistol / rifle part (m_weapons[2] / [1]), part node, world position and rotation, detach from the parent (slot 0x1c), items_avail[index + 1] taken and cleared, world child, dynamic, character, textures, DI / visuals, weapon pickup 8 (network: NetworkCreate + SendWeaponPUMessage), secondary for a pistol |
| 56 | 73 | 0x2a2c70 | 972 | CZSealBody::SealProcessAltitude | zSeal/seal_env.cpp | DEFECT-FIXED | A | 0x2a2d18 keeps the old m_inwater (sp+0xb0) before clearing it; 0x2a2ef8 stops the below-water and in-water anims when the body was in water and is not any more. The port tested m_inwater && !m_inwater (never; its comment called it an ELF quirk), so a wading effect kept running after the body left the water (grade A: visible on any level with water; whether m8 has a LIQUID soil was not established). Rest matches: volumetric list and HandleSmokeAndGas, liquids HandleWater, standing seals skipped (state 2 / 8 kept), highest within `above` else lowest, > 20 above the altitude dropped, player camera regions and region trigger |
| 57 | 78 | 0x2a6530 | 968 | CZKit::PickupAmmo(pickup) | zSeal/seal_kit.cpp | DEVIATION-KEPT | | recorded: the box NULL test and the 8-entry ask array. Request wait (cleared at <= 0, pending blocks; the ELF repeats the test on the network: no effect), entries (weapon / ammo / count read and written back), network ask for another seal's box (GetItemIndex / CanAddAmmo / IsLegalAmmo, item << 8 / ammo id, 1 s wait, SendMayIPickupMessage), single player PickupAmmo(weapon, ammo, &count). 2026-11-20: the box NULL test went with Lead B (part 2); the 8-entry ask array (network) stays kept |

# Part 2 (2026-11-15, socom-port-large-a2): rows k = 58..98

Rows k = 58..98 of the size order (41 functions of 700..964 bytes, 33,836 bytes), largest first,
with part 1's method: each ELF function disassembled (`z.sh`, raw `dis.sh` where the compaction
hides an address or a zero block, `sym.py` for jump tables, `off.py` / `mem.py` / `dw.py` /
`denum.py` / `animenum.py` for layouts and enumerators, `sym.py` for vtable slots) and compared
with the port's body instruction by instruction; float literals checked against the ELF's word with
both roundings, and the changed constant read back from the port build. Tree: HEAD 1ef7d286, later
d19a3161 (a boot-script change only), plus this part's files. No marker was added, moved or
changed and no function moved file.

## Counts (rows k = 58..98)

| Verdict | Rows |
|---|---|
| MATCH | 29 |
| DEFECT-FIXED | 8 (A 0, B 0, C 8) |
| DEVIATION-KEPT | 4 |
| UNJUDGED | 0 |
| total | 41 |

Rates (exact Clopper-Pearson 95% intervals): defects 8 / 41 = 19.5% (8.8% .. 34.9%), grade A or B
0 / 41 (0 .. 8.6%). Both parts together (98 rows): defects 19 / 98 = 19.4% (12.1% .. 28.6%), A or B
3 / 98 = 3.1% (0.6% .. 8.7%), A 1 / 98 = 1.0% (0 .. 5.6%). Four of the eight are port guards the
ELF does not have, three are rounding order and one is a constant.

## Fixes (ELF addresses), all grade C

- k = 77, `CZSealBody::CanUseKnife` 0x299d10: `KNIFE_DOT` (0x453a88) is written at run time by
  `__sinit_seal_env.cpp` (0x46cfbc) as `cosf(0x3edf66f3)`. The ELF's `cosf` (fdlibm float,
  `__kernel_cosf` 0x169580, plain `mul.s` / `add.s` / `sub.s`), emulated operation by operation with
  the R5900's rounding toward zero, gives 0x3f6803c8; the port's GCC folds `cosf` at compile time and
  built 0x3f6803c9 (its input literal `0.4363323f` was also one ulp low, 0x3edf66f2, though both
  inputs fold to the same word). The constant is now the ELF's word, `0.906307698f /* 0x3f6803c8 */`
  (read back from the port build: 0x3f6803c8). Also the victim-controller guard (below).
- k = 82, `CZKit::TickReticule` 0x2ab220: the three squared speeds (velM, velR, in-air;
  0x2ab3dc..0x2ab434) are `(x x + y y) + z z`; the port summed z first.
- k = 94, `CZKit::SetCurAccuracy` 0x2a75a0: the burst growth is `size + size * (over * slope)`
  (0x2a779c: `over * slope` first); the port wrote `size * over * slope`, which C groups as
  `(size * over) * slope`.
- k = 97, `CZSealBody::Reload` 0x298de0: the still test `(x x + y y) + z z <= 400` (0x298ec0); the
  port summed z first.
- k = 77, 81, 88, 93: guards of a seal's controller that the ELF calls through unchecked
  (`CanUseKnife` 0x299e1c, `CanUseCQB` 0x299bac, `CanUseRestraint` 0x2997d4: the victim's slot 0x38
  `GetSealCtrlAi`; `HandleDamage` 0x29bbb0: the killer's slot 0x94 `NotifyTargetDown`), recorded as
  port guards, removed under the rule of lead B below: every seal gets its controller when it is
  created.
- k = 87, `CZKit::FillAmmoPickupInstance` 0x2a5bb0: the magazines are cleared at `unwrap(i, n)` with
  no -1 test (0x2a5d5c); the port's test was dead (`i < n`), removed.

## Kept deviations (recorded)

- k = 58 `CAiSHold::Tick`: phase 1's stance byte is seeded with `m_stance` (the ELF leaves sp+0xaf
  unset; only `GetStanceFromState`'s default for a master in a non-stance state reads it).
- k = 61 `RemotePickupItem`, k = 63 `PickupItem`: the item-model slot write is bound-tested (the
  ELF writes `m_items_avail[slot + 1]` unchecked).
- k = 64 `HandleSmokeAndGas`: the cloud's source is found through `Particle::Source::list` (no
  `CParticleEx` in the port; the ELF dynamic_casts the node's `CNodeEx`).
- k = 93 `HandleDamage` also keeps its hit-node test: without a hit node the ELF compares each
  part's node with the word at EE address 0x1c (0x29ba08), which is no part's node, so no part takes
  the hit either way; reading through the NULL would be undefined for GCC.

## Lead A: the z-first three-term sums

Of the 38 sites the part 1 grep finds, the two-term sums (`int_bbox.cpp` x2, `seal.cpp` 2399,
`seal_ai.cpp` 3572, the `+ 0.0f` ones) and the sums whose y term is exactly zero (`unit_nz` or a
zeroed y: `seal_env.cpp` `CheckDIFwd1`, `ImpactFront`, `AlignForClimb`, `PostCheckDIDown`;
`hud_mapcompass.cpp` x3) give the same word in either order and were left. Every other site's
function was read in the ELF: all use `mul`, `mul`, `adda.s`, `madd.s` with z last. Fixed:
`seal_env.cpp` `SealGetIntersect`, `GetTerrainMotionFactor`, `HandleLanding`; `hud_main.cpp`
`DoRangeText`; `ent_target.cpp` `OnUpdateTargetList`, `CTarget::Update`; `zmath_main.cpp`
`CQuat::Pow`; `zparticle_source.cpp` `Source::Tick`; `zwep_projectile.cpp` `SetModelOrientation`,
`HandleIntersections` x2, `DoMiss`, `AcquireFlyout`, `CFlyoutMachine::Tick` (two sums). For the other
workers' files, edit files (srep, tested on HEAD and on the working tree): `seal_body.cpp`
`GetSpeedState`, `Stand_0`, `Jump`; `seal_weapon.cpp` `CanAttainAim` x3. All grade C.

## Lead B: part 1's nine kept NULL guards

Rule: a guard the ELF does not have goes unless the port provably reaches that path with NULL in
m8 where the original would not.

| k | Function | Guard | Decision |
|---|---|---|---|
| 4, 37 | `CZKit::Fire`, `HandleRemotePlaceExplosive` | deploy-state write (ELF: NULL + 0x54 otherwise) | removed: `AiStateIs(STATE_DEPLOY)` (0x26bb40, the top state) has just passed, so the ELF's check-cast of the same top never fails |
| 8 | `CSealCtrlAi::SensorPreTick` | the pushed AVOID / GRENADE / EVENT (and CQB) state; the pickup bit vector; the unit | removed: a successful `PushAiState` leaves the new state on top; `CPickup::Create` sizes every live pickup's bits; every seal joins a unit when created and `SealLeaveUnit` keeps `m_unit` |
| 21 | `BaseAnim_0` | the bottom blend | removed: with an empty stack both the ELF and the port read the anim type at EE address 0x30 (test trace: never empty in the run) |
| 26 | `HandleGrenadeExplosion` | the shooter's controller | removed (the ELF tests the shooter, 0x28fe08, not its controller) |
| 31 | `HandleSealStep` | the step-anim and decal tables before a mission | kept for now: the test trace never saw a NULL table (front end, load, m8); it matters only if a seal steps before the mission opens, which a trace through the other front-end screens would settle |
| 41 | `UpdateAiMapLoc` | the mission abort valve | removed: `CMission` creates "mission_abort" at every mission start |
| 55 | `DropItem` | the item model | removed: every rifle / pistol slot has one (the run's deaths drop their guns) |
| 57 | `PickupAmmo` | the box | removed: every ammo pickup is created with its box. The 8-entry ask array (network only) stays |

## Lead found here: run-time trig constants

GCC folds `cosf` / `sinf` of a constant at compile time; the ELF computes them in `__sinit` with
fdlibm float on the R5900, which can differ by an ulp (k = 77). Still to check (inputs above pi/4
need `__ieee754_rem_pio2f` and `__kernel_sinf` emulated as well): `RESTRAINT_DOT` (input 0x3fbde44e,
port 0x3db27ebd), `CQB_DOT` (0x3f91361e, port 0x3ed8616b), `seal_control.cpp` `FLASHBANG_DOT` (its
literal `0.8726646f` builds 0x3f5f66f2, the ELF's input is 0x3f5f66f3), `node_util.cpp`
`DEFAULT_CLOSESTNODE_DOT`, `seal_ai.cpp` `max_y` (`sinf`). `seal_env.cpp`'s own `FLASHBANG_DOT` and
`FALLBACK_DOT_MIN` / `MAX` have no reader in the ELF.

## Runs (part 2)

- sm1 (smoke: isolated tree d19a3161 plus this part's files and the two edit files, with a test-only
  trace of the k = 21 / 31 NULL cases; zseal4's `hook_zseal1.cpp` + `pad_fire.txt`, ended by
  `-DonePattern 'HOOK: r3600 player'`): cameras skipped at 46.6 s, 110 s in m8; no STOP, no
  exception, no NULL-case trace; 55 "fires at" lines; OutPatrol1 / 3 killed at 71.9 s and respawned
  (recycle 4.3, alive at 85.5 s); deaths drop ammo boxes and guns; heap 23,144,7xx..23,145,1xx B
  from 146 s to the end. Focus kept; portable profile, no memory card.
- la2-def: the default build of the final tree links.

## Result table (part 2)

| k | # | Address | Bytes | Function | File | Verdict | Grade | Evidence |
|---|---|---|---|---|---|---|---|---|
| 58 | 18 | 0x2e6ef0 | 964 | CAiSHold::Tick | zSeal/seal_airesponse.cpp | DEVIATION-KEPT | | phase 1's stance byte (sp+0xaf) is seeded with m_stance (recorded "ELF: left unset"; only GetStanceFromState's default for a non-stance master state reads it). Modes 2 / 4 by opts & 3, anim (s16, u8 m_state) / hand signal (s8) -> 3, cover 0x20 -> +0x240, look at m_lookPos (0x30) or ChooseLookDir from -row 2 and m_mapLocValid (0xe4) unless 8, flags 5 / scan 0x3e860a92, refused -> 4, phase 2 m_time vs +0x330, bit 0 of +0xc |
| 59 | 98 | 0x2b2ca0 | 948 | CSealCtrl::_GetTargetPerception | zSeal/seal_sensors.cpp | MATCH | | NULL, team (not player), m_isAlive (bit 11), seal AI snoozing (bit 9) / sleeping (bit 8), range^2 cut to mid plane^2, cone (0x70 / 0x90 / 0x9c), m_dot > 0 and vel x x + z z > 2500 (mula / madd), tail / tip / node, free list front or new 52 (NULL: true), state 3, index -1, time 0, owner / node / special / target, push_back, handle; refresh path |
| 60 | 20 | 0x2e7a30 | 936 | FindTraversableNeighbor | zSeal/seal_airesponse.cpp | MATCH | | GetLocation, GetMapByIndex, inline GetCell + soil 0/10/8/9, neighbours 0..7 from neighbor[] (x, y bounds unsigned), next map id from the map (+0xb0), first walkable one written to loc |
| 61 | 33 | 0x28dba0 | 936 | CZSealBody::RemotePickupItem | zSeal/seal_env.cpp | DEVIATION-KEPT | | the item-model slot write is bound-tested (recorded; the ELF writes data[slot + 1] unchecked). Slot (pistol 2 -> index or 1, rifle 1 -> index or 0), model slot cleared (bounded), m_weapons[1/2] part node out of its parent, model == part node cleared, pickup node out of the world / parent, mount rhand / hips / spinelo / rhand by m_item, "Swap rifle" unused, AddChild slot 0x18, names, SetItemByIndex (slot or GetNumItems), m_requested_item (bit 12), m_HudUpdateWeapon (bit 4), Destroy |
| 62 | 38 | 0x28f490 | 932 | CZSealBody::DamageRandomLocation | zSeal/seal_env.cpp | MATCH | | rand x 2^-31, GetDamage(pos, 0), pierce, < 0.1 head (alive, damage != 0: ResolveDamage(0xef8, 0xf28), levels 3 / 2 (0.5) / 1 (0.99) / 0, +3 retmods for 2 / 1, FindRandomDamageAnim(0) + WeaponHitAnim), < 0.4 body 3, < 0.55 larm 2, < 0.7 rarm 1, < 0.8 lleg 5, <= 1 rleg 4, spent limb -> DamageBody(projectile); all float words OK |
| 63 | 34 | 0x28df50 | 920 | CZSealBody::PickupItem | zSeal/seal_env.cpp | DEVIATION-KEPT | | the item-model slot write is bound-tested (recorded, as row 61). Network non-player -> RemotePickupItem, DropAmmo / DropItem(slot, true) (pistol 1, rifle 0), mounts, Action("Swap rifle", true, 2 x (net ? m_netid : m_id), (s16) rhand id, -1), names, model slot, SetItemByIndex, bits, Destroy (the port's trace line is port-only) |
| 64 | 71 | 0x2a2370 | 912 | CZSealBody::HandleSmokeAndGas | zSeal/seal_env.cpp | DEVIATION-KEPT | | the cloud's source is found through Particle::Source::list (recorded: no CParticleEx in the port; the ELF dynamic_casts the node's CNodeEx and reads +4 unchecked). Particle flag (bit 3 of +0x38), bbox of the first ancestor not using the parent's (3 levels, then GetBBox), Transform 2, per-axis sort (<= keeps), cloud 0 -> stun 125 + m_isingas (bit 12), 1 -> stun 122 + m_isinsmoke (bit 11); inside test pos >= min, <= max |
| 65 | 88 | 0x2ab910 | 904 | CZKit::Recoil | zSeal/seal_kit.cpp | MATCH | | player only (slot 0x2c), TargetMods(stance) knock / max / min / max, rumble high / low, zoom < 4 and != 3 (signed byte; the port's int enum compares the same), burst >= 3 kicks y, aspect y scaled (za - zf) / za when not 0 (y x d order), limits most x aspect, bump statics written never read (recorded), recoil_constscl, y / x clamps, prev size, size += knock in [min, max], recoilParam + 1 capped at 1 |
| 66 | 48 | 0x294d10 | 900 | CZSealBody::DamageBody(projectile) | zSeal/seal_env.cpp | MATCH | | single: first hit (shooter Hit, WasHit), shotgun (type 2) highest proximity else GetDamage(pos, 0), pierce, dead -> killer index + HandleKiller; network: id 0 or a local shooter (slot 0x34), report (from, m_id, 3, ..., first hit, (u8) weapon id), clear first hit, flinch 53, remote out, damage |
| 67 | 49 | 0x295250 | 900 | CZSealBody::DamageRLeg(projectile) | zSeal/seal_env.cpp | MATCH | | instruction stream identical to row 66 (diffed) but location 4, flinch 54, DamageRLeg |
| 68 | 53 | 0x296ae0 | 900 | CZSealBody::DamageRArm(projectile) | zSeal/seal_env.cpp | MATCH | | row 66's stream (diffed) with location 1 and the flinch 53 moved before the report, as the port |
| 69 | 82 | 0x2a98a0 | 892 | CZKit::WillFireWeapon | zSeal/seal_kit.cpp | MATCH | | printf(""), trigger 0 / 3 clear the burst, burst per mode (no ammo 1; 0 / 1 / >= 4 / 2 -> 3 / 3 -> 10000 / else 0), GetFireDelay dropped, down (trigger - 1 < 2 unsigned or waiting to raise, bit 10), raise wait (weight < 1, direct fire), weight test, burst count (signed), CanFire, delay <= 0, infinite ammo (bit 5 of 0xf58), launcher slot (firemode - 3), knife 186 / restraints 183 always, rounds > 0, empty but ids 182 / 186-187 / 183 / 11 |
| 70 | 72 | 0x2a2700 | 888 | CZSealBody::HandleWater | zSeal/seal_env.cpp | MATCH | | bbox as row 64, top / bottom = bbox y + pos y, depth = surface - bottom, swap, ripple node SetPosition (hit tested after the read, as the ELF), between: stop 0xfd8, big ripple[speed] into 0xfdc (not running, alive); above top by < 10 (10 + top): stop 0xfdc, small into 0xfd8; else in water = surface > top; dead stops both. Speed 3: the ELF reads the zero .bss word after each 12-byte array (no symbol there), the port NULL: same |
| 71 | 64 | 0x29d3c0 | 884 | CLook::SetLookDir | zSeal/seal_env.cpp | MATCH | | NULL -> unit_nz and 1, same goal (x, y, z ==) -> 1, cone: len = sqrt(z z + x x) (two terms: exact either order), z < 0 -> cosMinLookPitch (0xb0) else cosMax (0xac), -z / len < cosMaxLookYaw (0xb4), clamp CalcGoalDir(curr, dir, &clamped = curr, max, min, -yaw, yaw), SetDir, acos pitch / yaw, signs by y / x, pitch / max or -pitch / min, yaw / maxyaw on both sides (the ELF's two identical divides), SetEyeLookDir |
| 72 | 92 | 0x2af610 | 884 | CZKit::SetCurItemEnum | zSeal/seal_kit.cpp | MATCH | | first slot with the (u8) id, HUD weapon bit, lit flashlight (181, state & 8) off, launcher ammo: first launcher (none: old kept, 0), type 2 / 1 request unless in hand (bit 12) else UseItemModel(type, "aimnodes"), WepWait by the launcher's type, firemode = slot + 3; plain: selected = slot, with an old item: request / model by the new item, WepWait by the OLD item's type (quirk recorded), encumbrance, weaponinfoChanged (bit 2), 1 |
| 73 | 37 | 0x28ee80 | 880 | CZSealBody::FindRandomDeathAnim | zSeal/seal_env.cpp | MATCH | | mirror cleared, stance 8 -> BaseState then BodySetState(8), 10 / 9 -> stand, other non-stance -> BaseState, stunned (bit 4 of 0xf5c) -> prone, Stand2Crouch 17 / Crouch2Prone 19 / Stand2Prone 25 with tfrac (reversed 0x20: > 0.5; else < 0.5) -> 1/0, 2/1, 2/0, desired state unless dead, teammate table for a non-player of the player's team, size <= 0 -> -1, 1 -> 0, rand % n, lh |
| 74 | 24 | 0x2e4660 | 876 | CSealCtrl::SetDefaultLookParams | zSeal/seal_aiscan.cpp | MATCH | | look_rate 0.1 / 0.3 static, timer 1 + 2 r, flags 0x20, zero bias, NORMAL 0 (whole range, period 1 / 2, infinite, 6), EVENT 3 (half range, 0.5 / 2, rate 0.8 / 0, 1), BUDDY 8 (1 + 1.5 r), FRANTIC 6 (whole, 0.5 / 0x3f333334, 0.8 / 0, 0xa), DEPLOY 9 (1, 1 / 0, infinite); the ELF's range == 0 test before rand never fires (ranges 2 / 0.7); mode change: GetSealCtrlAi slot 0x38 for an AI, unused (recorded) |
| 75 | 31 | 0x28d230 | 856 | CZSealBody::CreateNetAmmoPickup | zSeal/seal_env.cpp | MATCH | | new box (3 vectors), per entry Unpack, item != 255: GetItemIndex / RemoveItemAndAmmo, else GetAmmoIndex(ammo, rounds) / RemoveAmmo, weapon / ammo / rounds pushed, YXZ rot 0, "fiftycal_box" instance at pos, dynamic, character bit 2 of 0x9a, AddTextureAssetCharacter 2, Create 9 (none: box deleted), netid, drop anim on the pickup's node; the closing debug walk has no effect |
| 76 | 50 | 0x295790 | 836 | CZSealBody::DamageLLeg(projectile) | zSeal/seal_env.cpp | MATCH | | row 67's stream (diffed): location 5, flinch 54 mirrored (a3 1), and no shotgun case in single player (recorded quirk), as the port |
| 77 | 59 | 0x299d10 | 832 | CZSealBody::CanUseKnife | zSeal/seal_env.cpp | DEFECT-FIXED | C | KNIFE_DOT (0x453a88) is stored by __sinit 0x46cfbc as cosf(0x3edf66f3); the ELF's cosf (__kernel_cosf 0x169580, emulated op by op with R5900 truncation, kcos.py) gives 0x3f6803c8; the port's GCC folded cosf(0.4363323f) to 0x3f6803c9 (read back from the build; its literal was also 1 ulp low, 0x3edf66f2): now the word 0.906307698f. Also the recorded port guard of the victim's controller removed (0x299e1c calls slot 0x38 unchecked; every seal gets a controller when created). Rest matches: alive enemy, restrained (bit 0 of 0xf59), stunned, Stab / PistolStab / Stabbed, scope, noshoot (bit 8), standing, aware 3 / 4, level facing dot (fwd normalised first) > KNIFE_DOT, victim faces away (< 0) |
| 78 | 3 | 0x186080 | 824 | CAiMap::ResetCells | zAI/ai_map.cpp | MATCH | | whole region (nx, ny), saturate y to scanline count (read twice), rows 12 bytes, x = max(start, x) .. min(end, x + dx), cells 8 bytes, action cell (bit 7) -> GetCellAction: m_type_invalid (bit 4 of +8) and m_state (bits 20-22) cleared, m_occupied (bit 5) cleared |
| 79 | 89 | 0x2ac8c0 | 820 | CZKit::SetCurItemByIndex | zSeal/seal_kit.cpp | MATCH | | unwrap (== n or n 0 -> -1, wrap), same / -1 out, zoom 0, lit flashlight off, select (>= n -> 0), flashlight 8, WepWait by type 3, type 2 / 1 request (bit 12) else UseItemModel, encumbrance, weaponinfo, zoom range of ((s8) zoom - 3) < size (else 1) > 1.5 -> SetCameraZoom(1, 0.5), zoom 0, firemode 0 -> CycleFireMode, trigger power 0, HUD, reticuletype, reticule |
| 80 | 52 | 0x2965f0 | 800 | CZSealBody::DamageLArm(projectile) | zSeal/seal_env.cpp | MATCH | | row 68's stream (diffed): network only for shooter id 0 (lookup for nothing; recorded quirk), location 2, flinch 53 mirrored after the report |
| 81 | 58 | 0x2999f0 | 800 | CZSealBody::CanUseCQB | zSeal/seal_env.cpp | DEFECT-FIXED | C | recorded port guard of the victim's controller removed (0x299bac calls slot 0x38 unchecked; every seal has a controller). Rest matches: alive enemy, stunned, own and victim's CQB / PistolCQB / falls anims, restrained, noshoot, current item with an id (!= 255), scope, GetStance(true) < 2, AI victim prone only when STATE_SURRENDER (6), level distance <= 25, dot > CQB_DOT (0x3f91361e input OK) |
| 82 | 86 | 0x2ab220 | 780 | CZKit::TickReticule | zSeal/seal_kit.cpp | DEFECT-FIXED | C | 0x2ab3dc..0x2ab434: the three squared speeds (velM, velR, in-air) are (x x + y y) + z z; the port summed z first: fixed. Rest matches: player, dynamic_cast, TargetMods(stance), knock return x dT toward 0 for x then y (the ELF's <= / < tests), goal velM^2 / 65 + 30 (5.29 velR^2) (+ air^2 / 65 when airborne, bit 21), clamp retmin 0x858 / retmax 0x854, size toward the goal at constrict x dT |
| 83 | 55 | 0x298ad0 | 772 | CZSealBody::CanFire | zSeal/seal_env.cpp | MATCH | | state 6 / 3 / 2 / 1 / 0, zooming (bit 5 of 0xf5c), top state 8, IsThrowing(false) inline (the ten throw / toss types), reloading, changing, Stab / PistolStab, ApplyRestraints x2, CQB x2 (Top re-read each time), carrying 9, overlay anim, carry, stunned, last active anim's fire_val <= tfrac (the ELF's !(t < fire)) |
| 84 | 75 | 0x2e38c0 | 772 | CZSealBody::InitHandSignals | zSeal/seal_handsig.cpp | MATCH | | 4 signals x "Signal / Crouch signal / Prone signal %s" (s16 stored as words, order follow, holdposition, fireatwill, deploy), Point / Wave / Shrug / Radio into all three stances |
| 85 | 13 | 0x1a2790 | 764 | CAiVisMap::TickVisMaps | zAI/ai_vismap.cpp | MATCH | | timed maps (-1 kept) count down, < 0: id -1, delete (inline dtor), null_vismap, count; erase(remove(null_vismap)) when any; max_lines 8 static, dynamic maps in order while lines > 0: state != 1 and map -> UpdateVisibilityMap(vm, lines) |
| 86 | 19 | 0x2e7340 | 760 | CAiSSurrender::Tick | zSeal/seal_airesponse.cpp | MATCH | | jump table 0x458040 (6): hold fire, AllStop(false), AIM_IDLE, weapon state 2, time = timer + (0.25 + 0.25 r), anims; wait; PlayAnim(anim, 0), drop callback (0x3c func, 0.65, 0) once; anim end -> "No_weapon anim set" bound + default (0x460); unit leave, team 0x20000 -> unit 17, valves, idle loop anim, restrainable (bit 7), timer + 5; 5 waits |
| 87 | 77 | 0x2a5bb0 | 760 | CZKit::FillAmmoPickupInstance | zSeal/seal_kit.cpp | DEFECT-FIXED | C | 0x2a5d5c: the magazines are cleared at unwrap(i, n) with no -1 test; the port had added one (dead: i < n). Removed. Rest matches: slot filter (-1 all), item (rifle / pistol -> NULL), m_ammo[i], rounds of the 10 mags, entry only with ammo, ammo cleared, non-gun item cleared, count = last non-NULL + 1, selection reset when count < selected or the item is NULL (weaponinfo) |
| 88 | 57 | 0x299600 | 756 | CZSealBody::CanUseRestraint | zSeal/seal_env.cpp | DEFECT-FIXED | C | recorded port guard of the victim's controller removed (0x2997d4 calls slot 0x38 unchecked). Rest matches: alive, restrainable (bit 7 of 0xf58), stunned, Receive / Apply / PistolApply restraints anims, scope, stance < 2, facing dot > RESTRAINT_DOT (0x3fbde44e input OK), surrendering AI (6) -> 1, else victim faces away |
| 89 | 65 | 0x29d740 | 748 | CZSealBody::CalcGoalDir | zSeal/seal_env.cpp | MATCH | | len sqrt(x x + z z), yaw acos(-z / len or 1) signed by x, pitch acos(len) signed by y, (x ux + y uy) + z uz > 0.8 keeps the yaw on curr's side (+- 0x40c90fdb), pitch in [min, max], yaw in [minyaw, maxyaw], inside: out = dir, 1; else ClipToBox(zero, angles, clipped, maxp, minp, maxyaw, minyaw), MakeYXRot(-x, y), Apply(unit_nz), 0 |
| 90 | 32 | 0x28d590 | 744 | CZSealBody::CreateNetWeaponPickup | zSeal/seal_env.cpp | MATCH | | not the player, slot of the (u8) item, GetItemByIndex then RemoveItemAndAmmo, NULL out (the ELF's delete after it is dead), part m_weapons[2 / 1] (unchecked) node / parent out, DeleteChild, model slot read and cleared (bounded), pos / rot when given, part node cleared when it is the model, dynamic, character, textures 2, descendant DI, Create 8, secondary = pistol (bit 8), netid, drop anim |
| 91 | 30 | 0x28cdb0 | 740 | CZSealBody::CheckForAmmoPickups | zSeal/seal_env.cpp | MATCH | | entries 0 .. weapons size, read while size >= e (quirk, recorded), per asked word: low byte == ammo id (255 none), high == item id (255 none), rounds > 0, bit e of the ack byte for e 0..7 |
| 92 | 26 | 0x27eac0 | 732 | CZSealBody::AnimSetup | zSeal/seal_cfg.cpp | MATCH | | no template: ReadMotionRdr's answer; set by name (char type's first), m_animset, reserve, per template anim: NULL -> AddAnim(NULL, i, -1), BodyAddAnim(name, looped bit 1, i), CopyValues, template ref points of anim id i copied (new 16, pushed even NULL), m_animset 0, BindAnimSet, default set, interp 0 / 0, representative wt 1, AnimPush / AnimPop, snapshot, Snap, 1 |
| 93 | 61 | 0x29b940 | 732 | CZSealBody::HandleDamage | zSeal/seal_env.cpp | DEFECT-FIXED | C | recorded port guard of the killer's controller removed (0x29bbb0 calls slot 0x94 NotifyTargetDown unchecked). Kept (recorded, reason added): the hit-node NULL test (the ELF reads EE word 0x1c, never a part node; GCC UB otherwise). Rest matches: was alive, projectile / ammo NULL out, same projectile out, explosive damage > 0 keeps it, part list copy, first part with id >= 0 on the hit node, radius > 0 explosive else non-explosive (location 0), UpdateHealth(0, 5) (network: id 0 or a local shooter), death: killer seal -> notify, index, HandleKiller; none -> stats Death |
| 94 | 80 | 0x2a75a0 | 728 | CZKit::SetCurAccuracy | zSeal/seal_kit.cpp | DEFECT-FIXED | C | 0x2a779c: the burst growth is size + size x (over x slope) (mul over x slope, then x size); the port wrote size x over x slope ((size x over) x slope): fixed. Rest matches: -1 x offset y, 5 x size, fov 640 / scrZ and x 448 / 640, scoped (>= 4 or 3): size 0, sniper drift into screen offsets and knock, aspect y, depth za / (aspect (za - zf)) or 1, GetWeapon, burst over min capped at max, FactorX / Y = (off x depth) x (tan(fov / 2) / 320 or 224), Factor = 0.707 (size x t) (0x3f34fdf4) |
| 95 | 36 | 0x28ebb0 | 712 | CZSealBody::FindRandomDamageAnim | zSeal/seal_env.cpp | MATCH | | row 73's stream (diffed) with idle 7 as standing, the stunned test after the stance-change one, the desired state skipped for 8 / 7 / 9-10 (unsigned), no teammate table (damageanim) |
| 96 | 40 | 0x28feb0 | 712 | CZSealBody::GetNumExplosiveHits | zSeal/seal_env.cpp | MATCH | | d = pos - framestartpos (0x38), (x x + y y) + z z < 400 -> 3, r draw 0.05 / 0.15 / 0.5 / 0.85 / 0.95 / <= 1 -> +1..6 (words OK), crouch -1 / prone -3, floor 0, > 900: 900 hits / d2 truncated, fraction rounded up when 0 + 1 r <= frac |
| 97 | 56 | 0x298de0 | 700 | CZSealBody::Reload | zSeal/seal_env.cpp | DEFECT-FIXED | C | the still test is (x x + y y) + z z <= 400 (adda / madd); the port summed z first: fixed. Rest matches: top, rifle (m_item == 1), changing / reloading / CQB x2 / stunned out with top, state byte, PeekBaseState prone (rifle / pistol prone reload) / crouch / stand (state 3 or moving: moving reload), other: top, -1: NULL, PushBlend(type, state, false), non-moving: active playback = rep tf / reload time when > 0 |
| 98 | 84 | 0x2aa4e0 | 700 | CZKit::TickFlashlight | zSeal/seal_kit.cpp | MATCH | | light map, flashlight 181 with state 8, dir = quat . aim goal, from = pos + 12 y, at = from + 100 dir, body node hidden (slot 0x34) for GetIntersect(from, at) and restored, hit: rest = at - hit, range sqrt((x x + y y) + z z), min 0.9 r (0x3f666666), max r, r^2, 1 / max, 1 / (max - min), UpdateBBox(false) slot 0x38, at = hit; projection translation -at, SetPosition(at) |
