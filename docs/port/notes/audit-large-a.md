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
| DEFECT-FIXED | 11 (A 1, B 2, C 8) |
| DEVIATION-KEPT | 13 |
| UNJUDGED | 0 |
| total | 57 |

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
| 21 | 28 | 0x280500 | 1712 | CZSealBody::BaseAnim_0(anim, item) | zSeal/seal_cfg.cpp | DEVIATION-KEPT | | the port tests the bottom blend for NULL (recorded; the ELF reads it unchecked). Item remap (Stand bottom -> rifle), pistol stance/climb types 37/35/41/47/16/36/26/18/1 -> PistolAnim, the 19 action types (separate ifs, signed 16-bit), rifle BaseAnim, fallback to anim, as the ELF |
| 22 | 69 | 0x2a0f20 | 1712 | CZSealBody::HomingTick | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x2a10cc: the turn angle's dot (norm . refvec) is (x x + y y) + z z; port z first. Rest matches: homing member test (quirk), tfrac reversed, offset, inverse quat, TrueLoopTime dropped, acos / dT clamp 2 pi, cross sign and length, drot, half-turn Exp, refpt -= vel dT, Align, VU0 rotates, quadW, hang / ladder exit height blend, step, motion, ladder entry y 0, per-axis 0.8 / dT clamps, dpos |
| 23 | 17 | 0x2e5e80 | 1688 | CAiSEvent::Tick | zSeal/seal_airesponse.cpp | MATCH | | target-seen (0x10) / underfire > 1.0 double (0x20) exits, jump table 0x457fc0 (10): react (sound 63 + flinch right/left 0.5, or sound 20), look (AIL 3, timer draw, scan 0x3eb2b8c2, next draw, stateFlags 1), look source (flags 1), route (GetLocation vec/pos, SetRoute, limit 5000), travel (path states 1/2/3 mode 1, points + complete mode 3), arrived 0.25 / next 6, waited, wait, look around (ChooseLookDir, flags 5, scan 0x3e860a92, 0.5), last look |
| 24 | 70 | 0x2a1bb0 | 1684 | CZSealBody::CheckDIFwd1 | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x2a1d90 hit distance and 0x2a20b8 body-z . normal are (x x + y y) + z z; port z first (the other z-first sums here have a zero y term, exact either way). Rest matches: jump action, root transform, probe (unused), 1.2 / 8, away (y 0, length, -1), 0.65 tests -> ctrl 3, ImpactFront, appflags 2 keeps the hit, throttles / velocities cleared |
| 25 | 81 | 0x2a8a00 | 1684 | CZKit::HandleFireWeapon | zSeal/seal_kit.cpp | MATCH | | designator (fetch when map name or anim NULL, reset, start sound), binoculars out, claymore (< 4, message), satchel, C4 (PutOnWall 65, Timer_PlaceC4 at 0.45 on m_firetime, 99), detonator, MP bomb 2.25, throwables (abort threshold, IsThrowing, BeginThrowItem), guns (burst, launcher grenade slot ammo, fire delay, firepoint_203 / firepoint, player launcher +0.15, PerturbAimVector slot 0x74, quat, Fire with velW) |
| 26 | 39 | 0x28f840 | 1644 | CZSealBody::HandleGrenadeExplosion | zSeal/seal_env.cpp | DEVIATION-KEPT | | recorded port guards: the shooter's controller NULL test before NotifyTargetDown (the ELF calls through it) and location 0 when there is no fragment (the ELF passes an unset stack byte). Sight-line walk (own nodes, nearest beyond the last, material NULL continues, particle / liquid / pickup pass), stuns by id (171/153/152/151/126/121 -> 4 2 s, 161 -> 5 100, 122 -> 3 2, 125 -> 1 3, 123 -> 0 2), player ringing (not 81-84, 1 - d2/r2, PlaySound3D slot 0x24) and wiggle (not 123), fragments, UpdateHealth(loc, 4), killer, cleanup, top state 8, as the ELF |
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
| 37 | 79 | 0x2a6ed0 | 1332 | CZKit::HandleRemotePlaceExplosive | zSeal/seal_kit.cpp | DEVIATION-KEPT | | the deploy-state write is NULL-tested (recorded; the ELF writes NULL + 0x54 when the top is not STATE_DEPLOY). MP bomb (30, network RequestNewBombState 3 / mission win-loss timer), C4 5 timed, satchel (mission timer, < 0 none), claymore remote removal 10, other out; XRef instance (inactive, model, pos, rot, character, texture set 2, active), isplayer, SetProjectile (model passed), pickups 4/5/6/7, echo and HUD timer for the player's team, remote flag, list insert, ammo, detonator, HUD weapon flag |
| 38 | 16 | 0x2e5850 | 1268 | CAiSFlee::Tick | zSeal/seal_airesponse.cpp | DEVIATION-KEPT | | phase 5 routes to the cover cell FindCoverLoc found (recorded; the ELF calls SetRoute on the unset stack word beside it, sp+0x54). Jump table 0x457f70 (7): safehouse region / random loc / cry 65 at 0.75 / stand / speed / no target, plan states (unit path proximity 4 / 30), arrival, STATE_HOLD (returns at once), re-choose (rush 50 / surrender 50), cover 10 cells (5 s) or 3 s, cover route wait, stateFlags bit 0 on a change |
| 39 | 9 | 0x1a0460 | 1264 | visCallback | zAI/ai_vismap.cpp | DEVIATION-KEPT | | marks outside the box are skipped (recorded in vis_set_mark: the ELF writes them unchecked, past the bits on the m8 maps). Statics 4.5 / 9 / 18 / taxi cab, blocking soil 0/8/10 unseen + stop, altitude, rise, run 10 x dist (taxi or sqrt), eye cell seen, horizon raise (ground > top, slope), seen test (rise + 18) / run, 1 |
| 40 | 76 | 0x2a5040 | 1264 | CZKit::SniperTick | zSeal/seal_kit.cpp | MATCH | | adrenaline (1 without), heartbeat (> 0.2, not binoculars: 0.3 + 0.24 c / 0.8 + 0.64 c, rumble 0.1 / 0.16 at 20 + 100 a), kick (rate, move dist, return to baseline), wander x / y (limits 0.8 l a + 0.2 l / 0.2 l + 0.8 l a, out at <= 0.2, |pos| / limit, (0.25 + d) + (0.75 + d) r, bounce), all float words read |
| 41 | 74 | 0x2a4700 | 1260 | CZSealBody::UpdateAiMapLoc | zSeal/seal_env.cpp | DEVIATION-KEPT | | the mission abort valve is NULL-tested (recorded; the ELF sets it unchecked). GetLocation, m_mapLoc, walkable cell (map NULL out), changed cell: valid loc, snake point, vis map update when asked, occupied mark when alive; last valid position; player boundary sounds (0 / 1 / 2 by GetBoundary of old and new cell, not on the network), valve set to 1 with callbacks on a change |
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
| 57 | 78 | 0x2a6530 | 968 | CZKit::PickupAmmo(pickup) | zSeal/seal_kit.cpp | DEVIATION-KEPT | | recorded: the box NULL test and the 8-entry ask array. Request wait (cleared at <= 0, pending blocks; the ELF repeats the test on the network: no effect), entries (weapon / ammo / count read and written back), network ask for another seal's box (GetItemIndex / CanAddAmmo / IsLegalAmmo, item << 8 / ammo id, 1 s wait, SendMayIPickupMessage), single player PickupAmmo(weapon, ammo, &count) |
