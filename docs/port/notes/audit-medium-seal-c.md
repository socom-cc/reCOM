# Audit of list medium-seal-c (2026-11-19, socom-port-audit-mseal-c)

The 96 medium functions (36,896 bytes) of six `gamez/zSeal` files: seal_tasks.cpp (52),
seal_unit.cpp (23), seal_weapon.cpp (9), ai_target.cpp (6), seal_anim.cpp (5), seal_ik.cpp (1).
HEAD 531affea (test trees on e0270b9a + this list's files; neither commit since touches them).
Judged file by file, the file of the scan's highest-ranked function first (seal_weapon, seal_unit,
ai_target, seal_anim, seal_ik, seal_tasks); the addresses cited were taken from `ref.dis`.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 82 |
| DEFECT-FIXED | 11 (A 0, B 2, C 9) |
| DEVIATION-KEPT | 3 |
| UNJUDGED | 0 |

Defect rate 11 / 96 (11%); B 2.

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #63 (the user's rule: the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)).

## Fixes

- B #28 `CTSignal::GetSignalByName` 0x2b6f60: was the skeleton stub (always AISIG_UNKNOWN), so
  every ai::SIGNAL, also a bare one (ANIMCOMPLETE), reached `AnimSignal` as 0, which does nothing;
  written: strcasecmp against the six names of jump table 0x454560, NULL or no match 0.
- B #46 `CTLookAt::Begin` 0x2bb0b0: the seal and its controller are tested, not the AI (0x2bb134 /
  0x2bb13c), as in Tick; a seal without an AI now draws its look time.
- C #88 `CZSealBody::CanAttainAim`: the last test c.le.s / bc1f (0x2bf1e0), `!(dot <= 0)`.
- C #92 `CZSealBody::CalcAimGoal`: the z test c.lt.s / bc1t (0x2bfcdc), `!(z < 0)`.
- C #7 `CZSealBody::Post`: the smooth test c.le.s / bc1t (0x26ca04), `!(w <= 0)`.
- C #5 `CAiTarget::UpdateTarget`, #4 `SetTarget`: the entity is tested before GetPosW and the
  position read from address 0 without one (0x2ea1f8; 0x2e9cf0, 0x2e9dcc), not a call through NULL.
- C #77 `AddBreachMember`, #57 `CTFireWeapon::Tick`, #64 `CTAction::Tick`: port-only NULL tests of
  the check-cast after a successful push removed (0x2d3584; 0x2bcf04; 0x2be3dc, 0x2be4bc).

Also corrected without a verdict change: #78 `CSealUnit::UnInit`'s stale comment (the lists exist,
CreateSinglePlayerUnits is written).

## Kept deviations (reasons in the code)

- #85 `CSealUnit::CSealUnit`: start_turn, m_ambush_dir, the targets, m_follower_is_pointing and the
  valve are zeroed where the ELF leaves them as allocated.
- #17 `CTRegion::Parse`: the location starts invalid where the ELF keeps an unset stack word when
  the region is not found.
- #63 `CTDebug::Parse`: a list without values gives no record where the ELF reads a type at 0.
- #25 `CTSpecial::End`: the controller is tested before Debug (0x2b631c); the retail Debug reads
  nothing, the port's trace Debug reads its receiver. (`CTSpecial::Begin`, not a row, has the same
  test.)

ELF quirks kept (commented): #73 ACTION's name overwritten by GetSoundNameStringFromCmd; #72 the
inverted sub-unit test; #8 a part without b's pose takes b's rotation; #15 the wait drawn twice;
#27 / #63 the record type not set; #51 "reloading" -> 20; #43, #37 (and now #77, #57, #64) write
through the check-cast of a pushed state; the unused GetSealCtrlAi calls of #13, #14, #29, #33, #60.

Float checks: the compare forms of #88, #92, #7 (fixed), #89, #95, #96, #13, #18, #22, #52, #53,
#66 as the ELF; the sums of #88, #89, #18 and the CalcAimGoal length in (x x + y y) + z z order; the
VU0 transforms of #88, #93, #94, #60 as ((r0 x + r1 y) + r2 z) [+ r3]; the literal words 0x3f8ccccd
(#88), 0x3f7d70a4 (#96), 0x3f245a1d (#89), 0x3f350481 / 0x3f5db22d (#86), 0x3a83126f / 0x3f7fbe77
(#8), 0x3dcccccd / 0x3f4ccccd (#59), 0x447a0000 (#19) and 0x30000000 (`4.656613e-10f` and
`1 / 2147483648` both give it). No float-to-unsigned conversion in the list (the one conversion,
#63's dead real branch, is fptosi).

## Leads for other lists

- `CTSpecial::Begin` 0x2b63d0 (not in this list) keeps the same controller test as #25.
- The `taskSeal` helper reads ai_cmdid+8 as a half word where every handler's ELF loads the word
  (`lw`); the same while AddCmd's ids stay below 0x10000.
- `GetSignalByName` was a stub with a `body` fence; `stubchk.py` does not see such bodies. A grep for
  `@socom-skeleton body` fences whose body is a single `return` would find others.

## What the packets lacked

The CharacterDynamics offsets (#92: `mem.py CharacterDynamics`), the CSealUnit and UnitPointData
layouts (#85: `dw.py`), the CAiTrigger and CSealCtrl goal-timer offsets (#58, #31: `mem.py`), the
TASK_* record layouts (file-local structs between fences: read from the source), the AI_STATE values
(port enum, no DWARF), the port's `CNodeAction::GetAction` and `_zrdr::Get` bodies (header inlines
called through another object), and CTLookAt::Tick's tests (to grade #46).

## Runs

On e0270b9a plus this list's five changed files (isolated tree):
- Default build (`default.sh audit-mseal-c-default`): links, 0 undefined.
- One fake-pad m8 run (`tb.sh audit-mseal-c-fake pad_start.txt t_trace.txt`, 170 s, run msc1) with
  test-only traces in GetSignalByName, CTSignal::Tick, CTLookAt::Begin (no AI) and UpdateTarget (no
  entity): no STOP, no exception; the patrols went aware (on_aware0 / on_aware4), 23 GOTO arrivals,
  2 "fires at" lines, the team FOLLOWING, heap 22.88 -> 23.07 MB. None of the four traces fired: m8's
  loaded scripts parse no ai::SIGNAL in this run and no LOOKAT ran on a seal without an AI, so both
  B fixes stay masked on this disc as far as the run shows.

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 91 | 0x2bfa80 | 280 | CZSealBody::SetAimPointW(CPnt3D const*, CPnt3D const*, bool) | seal_weapon.cpp | MATCH | | point copied to m_aim_point, valid bit (0xf58 bit 2) set, reticle copied unless keep_reticle, normal copied and m_have_aim_norm (0xf5b bit 1) set or cleared, UpdateAimDir(keep_reticle); NULL point clears both bits and CalcAimGoal(&m_aim_dir, unit_nz, &m_aim_goal), returns 0. Scan differences are the port's layout |
| 88 | 0x2befc0 | 584 | CZSealBody::CanAttainAim(CPnt3D&) | seal_weapon.cpp | DEFECT-FIXED | C | guards (norm bit, do_aimap_collide, state 2 / LinearWeight == 0, rifle / pistol), base = aimpos + PosW, (x+y)+z dots, VU0 rotation order row0 x + row1 y + row2 z, 1.1f word 0x3f8ccccd, PointAlongLine args. Last compare is c.le.s / bc1f (0x2bf1e0): the port's `> 0` gave false for a NaN dot; now `!(dot <= 0)` |
| 93 | 0x2bfed0 | 460 | CZSealBody::GetNodePos(zdb::CNode const*, CPnt3D&, bool) | seal_weapon.cpp | MATCH | | NULL node, weapon slot, BodyWepPart and part node tests; PartInSpace of the node's translation row (+0x30); the two VU0 forms (with / without row 3) as ((r0 x + r1 y) + r2 z) [+ r3]. Scan differences are the inline Transform |
| 92 | 0x2bfba0 | 696 | CZSealBody::CalcAimGoal(CPnt3D const*, CPnt3D const*, CPnt3D*) | seal_weapon.cpp | DEFECT-FIXED | C | peek base state, the four aim states, CharacterDynamics offsets 0x94..0xa8 / 0x58..0x6c (mem.py), len = sqrt(x x + z z), yaw cos 1 at len 0, CalcGoalDir(maxpitch, minpitch, -maxyaw, maxyaw), attainable bit 0xf5b bit 3. The z test is c.lt.s / bc1t (0x2bfcdc): the port's `z >= 0` sent a NaN z to the min-pitch test; now `!(z < 0)` |
| 94 | 0x2c0140 | 376 | CZSealBody::GetFirepointPos(CPnt3D&, char const*) | seal_weapon.cpp | MATCH | | weapon slot, BodyWepPart / node, FindChild(name, false) only with a name (slot +0x24), PartInSpace offset NULL or child row 3, then the node matrix with translation |
| 95 | 0x2c02c0 | 452 | CZSealBody::WeaponsTick(float) | seal_weapon.cpp | MATCH | | transition bit 0x10 and the & 0xef / & 0xff state cases 2, 1, 4, 16; Tick(dT) / Clear on currT <= 0; hold = downT + waitT with c.le.s; settled states' Weight() == 0 / 1 tests and the state words 1 / 2 stored before SetWeaponState(2 / 1); UpdateAimDir(false), AimWeapon, kit PreTick(dT) |
| 90 | 0x2bf920 | 340 | CZSealBody::UpdateAimParams() | seal_weapon.cpp | MATCH | | each node found once: weapon slot, BodyWepPart, part node (a NULL node stores NULL), FindChild("aimpoint" / "firepoint", false); GetNodePos of both without translation |
| 96 | 0x2c0490 | 388 | CZSealBody::SetWeaponState(WEAPON_STATE) | seal_weapon.cpp | MATCH | | same-state return on (state & ~0x10) & 0xff, t = sumT - currT unless currT <= 0, lower: min(LinearWeight, 0.99 = 0x3f7d70a4) (LinearWeight called twice as in the ELF) x downT, state 0x12; raise: state 0x11, at t == 0 Start(up, wait, down) unless no item or BINOCULARS (182), else up <= t < up + wait drops bit 0x10; 4 / 16 / other return |
| 89 | 0x2bf240 | 244 | CZSealBody::CanProneAim() | seal_weapon.cpp | MATCH | | velocity (x x + y y) + z z == 0 test, camera matrix row 2 scaled by -1, dot with the ground normal (x+y)+z, -0.642 (0xbf245a1d) c.lt.s and 0.642 c.le.s |
| 73 | 0x2d2030 | 624 | CSealUnit::ConfirmCommand(CZSealBody*, FT_COMMAND, char*) | seal_unit.cpp | MATCH | | ShouldConfirmVoiceCommands, leader handle & 0xff, the 26-entry jump table (0x456c80): 2 DEPLOY, 13-17 / 24 the place orders with their verbs, 1 ACTION falling into GetSoundNameStringFromCmd (quirk kept), the rest and >= 26 GetSoundNameStringFromCmd; formats and arguments; PlaySoundVol(1.0, NULL, 255) through slot +0x10. Scan differences are the trace and the inlined strcpy of "unknown" |
| 77 | 0x2d3540 | 520 | AddBreachMember(CAiSBreach*, CSealCtrlAi*) | seal_unit.cpp | DEFECT-FIXED | C | push STATE_BREACH (10, true), check-cast, member copy +0x4..+0x5c (the port's default assignment), first member leads and opens with a new VTYPE_TEMP valve and index 0, the second opens (also in the leader's breach state), index = template index++, count + 1 in 32 bits (change always 1), m_setup bit. A port-only NULL test of the cast (0x2d3584: cannot fail after a successful push) is removed |
| 75 | 0x2d24e0 | 588 | GetWeaponNameStringFromSRString(char*, char*) | seal_unit.cpp | MATCH | | the 12 strcasecmp names and outputs in ELF order (0x456d68..0x456e40), sprintf(out, name) on a hit, else sprintf(out, "%s", sr). Scan differences are the port's table loop |
| 74 | 0x2d22c0 | 544 | GetNodeNameStringFromSRString(char*, char*) | seal_unit.cpp | MATCH | | the 11 strcasecmp names and outputs in ELF order (0x456ce8..0x456d58, "X-RAY" -> "XRAY"), fallback "%s". Scan differences are the port's table loop |
| 85 | 0x2d6a20 | 304 | CSealUnit::CSealUnit(unsigned int) | seal_unit.cpp | DEVIATION-KEPT | | every ELF store compared with the DWARF layout (UnitPointData start_anim / in_point / dirW = unit_z / timer at +0xc and +0x20, unit num, parent, the 5 lists, +0x7c..+0x7f, follow source, hold up, unit in point, point ticks, compass anchor). The port also zeroes start_turn, m_ambush_dir, the targets, m_follower_is_pointing and the valve, which the ELF leaves as allocated; the reason is now in the code |
| 84 | 0x2d68e0 | 320 | CSealUnit::SealJoinUnit(CZSealBody*) | seal_unit.cpp | MATCH | | SealLeaveUnit, escortee test (team & 0x20000, not unit 17) into the inlined EscorteeJoinUnit (second SealLeaveUnit, unit 17 recursion, escortee push, control m_unit, front command FOLLOW or unit 0 -> m_issue_unit_follow), first member of a unit other than 17 becomes the follow source, push_back, control m_unit. On an empty command list the ELF reads the byte after the sentinel (m_issue_unit_follow, 0 or 1), never FOLLOW: same as the port's CMD_UNKNOWN |
| 83 | 0x2d67a0 | 308 | CSealUnit::EscorteeJoinUnit(CZSealBody*) | seal_unit.cpp | MATCH | | the mirror of row 84 (SealJoinUnit inlined for unit 17, with its escortee recursion), escortee push, control m_unit, FOLLOW / unit 0 test |
| 66 | 0x2cead0 | 504 | CZSealBody::CheckPathProximity(CAiPath const&, int, float) const | seal_unit.cpp | MATCH | | empty / state COMPLETE (4) test, walk struct (map loc from m_mapLocValid bitfields, cells, range, dist 0), legs from the last point to points 1..n-1 with the same 6-bit map id, WalkLine with _check_proximity, first failed walk returns dist < range (c.lt.s), else false |
| 65 | 0x2ce8d0 | 504 | CSealUnit::CheckPathProximity(CAiPath const&, int, float) const | seal_unit.cpp | MATCH | | members (+0x40) then sub-units (+0x58), first true returns 1, args (path, cells, range) |
| 87 | 0x2d7620 | 280 | CSealUnit::Create(unsigned int) | seal_unit.cpp | MATCH | | the inlined GetUnitByTeam search of m_list, new(164) + ctor + insert at the end when missing, unit 24 gets CValve::Create("mp_radio_channel_valve", 1), every other unit NULL (also an existing one) |
| 76 | 0x2d2f40 | 648 | CSealUnit::VoiceHandSignal(CZSealBody*, FT_COMMAND, void*, bool) | seal_unit.cpp | MATCH | | empty unit / NULL source return, signals 17/16/15/14 -> 0, 3 -> 2, 5 -> 1, FOLLOW -> 0 unless the front order is FOLLOW (an empty list reads m_issue_unit_follow, never 4: same as the port), 24 / 2 -> 3; player test through slot +0x2c with a NULL control false; Bravo (3): CanSeeLine(source loc, front seal loc, NULL) or no signal; DoHandSignal |
| 71 | 0x2d0620 | 440 | CSealUnit::CommandNotifyFromChild(CSealUnit*, CZSealBody*, FT_COMMAND, void*) | seal_unit.cpp | MATCH | | FOLLOW only; AI members (control non-NULL, IsAi slot +0x30) with FindAiState(9 = STATE_FOLLOW) set `some`, else clear `all`; sub-units whose front order is FOLLOW set `some` unless the child, else clear `all`; all -> some = 0 and m_issue_unit_follow, some -> m_issue_sub_unit_follow |
| 72 | 0x2d1f00 | 304 | CSealUnit::GetUnitLeaderHandle() | seal_unit.cpp | MATCH | | first member whose GetSealCtrlAi (slot +0x38) is non-NULL gives its handle (+0x284; the ELF's lb sign-extension is masked by every caller); the inverted sub-unit test (searched only with no sub-units and none found) kept as an ELF quirk |
| 82 | 0x2d6570 | 560 | CSealUnit::SealLeaveUnit(CZSealBody*) | seal_unit.cpp | MATCH | | the control's m_unit (+0xdc) NULL return, the first match erased from each of seals, escortees, dead, follow source replaced by the front seal (NULL when empty), then FOLLOW front order or unit 0 sets m_issue_unit_follow when a follow source exists |
| 67 | 0x2cf010 | 244 | CSealUnit::GetMyPointOutTurnDir(CZSealBody*, CPnt3D**) | seal_unit.cpp | MATCH | | m_navyseal bit (+0x280 bit 1), m_unit_in_point, front seal -> leader start_turn (+0x21) / dirW (+0x24), second node -> follower start_turn (+0xd) / dirW (+0x10), each cleared once used. The ELF reads the front / second node without an end test, where the data word is m_escortees' size, never the seal: same as the port's tests |
| 81 | 0x2d63a0 | 460 | CSealUnit::Revive(CZSealBody*) | seal_unit.cpp | MATCH | | alive bit (+0xdd bit 3), dead-list search and erase, escortee (team & 0x20000, not unit 17) or member push_back; the ELF's empty member / escortee walks after a miss do nothing |
| 80 | 0x2d61b0 | 492 | CSealUnit::IsMemberOfUnit(unsigned int, CZSealBody*, bool) | seal_unit.cpp | MATCH | | inlined GetUnitByTeam and member test (seals, escortees, then with deep the sub-units' IsMemberOfUnit(seal, true)); the port calls the two functions, whose bodies are the same |
| 86 | 0x2d7340 | 588 | CSealUnit::GetMyLookDir(CPnt3D*, CPnt3D*, CZSealBody*) | seal_unit.cpp | MATCH | | ambush dir, copy of dir, player follow source: Bravo front seal (c x - c z, 0, c x + c z), Bravo other (-z, 0, x), Able non-front (c x + c z, 0, -c x + c z); two members: the 60-degree pair; else (x, 0, z). The mula / madd / msub operand orders, 0.7071 = 0x3f350481, 0.866 = 0x3f5db22d (GCC gives the same words) |
| 68 | 0x2cf180 | 432 | CSealUnit::GetAwareCounter() const | seal_unit.cpp | MATCH | | sum of the members' +0xd8 words, then the sub-units' recursive counts |
| 69 | 0x2d03b0 | 308 | CSealUnit::GetTail() | seal_unit.cpp | MATCH | | the last sub-unit's tail (its own sub-unit recursion, seals, escortees, dead backs inlined), then this unit's seals / escortees / dead backs (+0x44 / +0x50 / +0x68 prev nodes) |
| 70 | 0x2d04f0 | 296 | CSealUnit::GetLeader() const | seal_unit.cpp | MATCH | | front seal, else the first sub-unit's front seal, else its first sub-unit's (two levels inlined, then the call) |
| 78 | 0x2d5570 | 504 | CSealUnit::UnInit() | seal_unit.cpp | MATCH | | each unit erased from m_list, then (non-NULL) the inlined dtor: anchor DeleteAnchor and NULL, sub-units and seals cleared, the five lists destroyed, operator delete; m_created_units_test = 0. The port's implicit dtor destroys the same lists. A stale comment (lists not declared, CreateSinglePlayerUnits unwritten) is corrected |
| 79 | 0x2d5b40 | 332 | CSealUnit::DistributeNotify(CZSealBody*, UNIT_MESSAGE, void*) | seal_unit.cpp | MATCH | | for each sub-unit: its sub-units' DistributeNotify, then its PrivateNotify; then this unit's PrivateNotify; arguments passed through |
| 5 | 0x2ea020 | 680 | CAiTarget::UpdateTarget(CTarget*, float) | ai_target.cpp | DEFECT-FIXED | C | inlined compare_target and CTarget::operator=(const CTarget*) (NULL clears only the entity; else every member and the +0x24 bit word), threat stored also for NULL, m_targeted bit exchange (+0x5c bit 2 / +0x24 bit 4) by `changed`. The ELF tests the entity before GetPosW (0x2ea1f8) and reads the position at address 0 without one; the port called through the NULL entity. Now the ELF form |
| 4 | 0x2e9ca0 | 448 | CAiTarget::SetTarget(CTarget*, float) | ai_target.cpp | DEFECT-FIXED | C | compare_target, operator=, threat, last pos and m_targeted exchange as row 5, acquisition clocks from theMission's timer on a change, last pos again and the lost-sight time, reset_aim 1, first_aim = changed. The same two entity tests (0x2e9cf0, 0x2e9dcc) as row 5: now the ELF form |
| 3 | 0x2e99e0 | 232 | CAiTarget::OnSetVisible(bool) | ai_target.cpp | MATCH | | entity and alive bit (+0xdd bit 3) test, last pos from GetPosW, last vel from the entity's velocity (+0x2c), visible: visible time, reset_aim 1, first_aim 0; else lost-sight time |
| 2 | 0x2e9900 | 212 | CAiTarget::ModifyAimDir(CPnt3D*, float, float) | ai_target.cpp | MATCH | | spread = angle (1 - accuracy), noise {0, 0} (0x4763f0, both words 0), first aim x = 0.75 spread, y = spread, MakeNoise(&m_aim_noise, noise), first_aim 0 and reset_aim 1 rewritten, noise z = 0 (in the Add delay slot), Add and Normalize |
| 6 | 0x2ea2d0 | 304 | CAiTarget::CAiTarget() | ai_target.cpp | MATCH | | CTarget ctor, threat 0, noise / last pos / last vel = CPnt3D::zero, the three clocks 0, the +0x5c bits end as reset 1, first 0, targeted 0 (the ELF writes first_aim 1 then 0), m_unused 0 |
| 1 | 0x2e96d0 | 552 | ai::CheckLineOfFire(CEntity const*, CTarget const*, float) | ai_target.cpp | MATCH | | NULL target / entity -> true, height 18 and offset (0, 0.5 height, 0) set once, tail / tip = PosW + offset, the 40-byte target list (+0xcc) walked: the target's entity -> true, dead or other team skipped, DistToVector and dist < radius (c.lt.s) -> false, end -> false. The list entity is read without a NULL test as in the ELF |
| 11 | 0x26e5e0 | 276 | CSealAnim::CSealAnim() | seal_anim.cpp | MATCH | | _malloc("seal_anim.cpp", 56) of the pose stack, depth 0, per frame weight 0, anim NULL and the 32 part ids -1. The ELF block is 8464 bytes (16-byte aligned quaternions); the port's SEALANIM_STACK is 8264 with its own offsets, used only through the struct |
| 7 | 0x26c930 | 428 | CZSealBody::Post() | seal_anim.cpp | DEFECT-FIXED | C | snapshot flag, interp guards (c.le.s), interp1 -= dT clamped at 0, quadW(interp1 / interp2), w == 0 sets m_blendme (+0x26) of root, rifle, pistol, weapon; Snap at interp1 <= 0; parts with id >= 0 and a node get SetPosition / SetRotation. The smooth test is c.le.s / bc1t (0x26ca04): the port's `w > 0` skipped a NaN weight; now `!(w <= 0)` |
| 10 | 0x26e300 | 628 | CZSealBody::Animate() | seal_anim.cpp | MATCH | | m_animate_me (0xf5b bit 7), Top, snapshot 0, depth 0, swap test (IsCurrentBlend 56, 57, 58, overlay anim type == AnimTypes::MovingRifle2Pistol), per active anim ConfigureWeaponAnim unless swapping, AnimPush, count, its overlay chain (+0xc) pushed with AnimOverlay(wt +0x4); AnimBlend(count); the blend overlay (anim set, state +0xc != 0) pushed with AnimOverlay(1.0); the inlined AnimPop (row 9's body) |
| 8 | 0x26d550 | 376 | CSealAnim::CombineRotations(int, int) | seal_anim.cpp | MATCH | | frame addresses, sum = a + b, w = b / sum, per part: a id -1 skipped, b id -1 copies b's rotation (quirk kept), w <= 0.001 (0x3a83126f) keeps, !(w < 0.999) (0x3f7fbe77) copies, else Slerp(b, w) in place; a's weight = sum. The ELF's return of `a` is unused by its three callers in AnimBlend |
| 9 | 0x26ddc0 | 236 | CSealAnim::AnimPop(CBody*) | seal_anim.cpp | MATCH | | top frame (depth - 1), 32 part poses with id >= 0 to the body part of that id (non-NULL): position and the four quaternion words; depth - 1 returned |
| 12 | 0x2a4dd0 | 404 | CZSealBody::FootInSpace(CZBodyAnim*, CPnt3D*, CPnt3D*, float, float, bool) | seal_ik.cpp | MATCH | | foot choice by notMirrored (rotA on the left foot unmirrored, else the right), each non-zero rot (c.eq.s, same for NaN) MakeXRot(-rot), q.Mul(&part rot, &r) copied back, then each non-NULL out gets PartInSpace(foot, (seal_foot_bone, 0, 0), out, NULL) |
| 28 | 0x2b6f60 | 240 | CTSignal::GetSignalByName(char const*) | seal_tasks.cpp | DEFECT-FIXED | B | the port's body was the skeleton stub (always AISIG_UNKNOWN), so every ai::SIGNAL task, also a bare one (AISIG_ANIMCOMPLETE), sent signal 0, which CSealCtrlAi::AnimSignal ignores: a script state never forgot its finished anim, no critical section, no SUSPEND / RELEASE. Written from the ELF: NULL -> 0, strcasecmp against the six names of the jump table 0x454560 in order, the index on a match, else 0 |
| 27 | 0x2b6d60 | 500 | CTSignal::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "signal" / "entity", the single string value when neither (array count 1, element 1 of type 3), a bare command -> "AISIG_ANIMCOMPLETE", no signal -> NULL; entity length rounded up to 4, + 16, _calloc, data_size (type not set: quirk kept), the signal word GetSignalByName & 0xff, entity copied or "" |
| 15 | 0x2b4300 | 328 | CTWait::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "wait" Rfloat {0, 0}, none -> NULL; _calloc(20), header half (size 20 << 2 in +0x2, type ai_cmdid), the timer drawn twice (quirk kept) as min + range (2^-31 rand) (0x30000000; `4.656613e-10f` and `1/2147483648` both give that word), min alone at range 0 |
| 58 | 0x2bd1a0 | 500 | CTFireMode::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | select seal and its AI (no controller test), ChooseWeapon(hint); trigger bit: up / dn mins (task +0x14 / +0x10 to CAiTrigger +0x0 / +0x8, ranges 0), marker = draw(up), timer = (double) marker + (double) draw(dn) (fptodp / dpadd); SetHoldFire(false); auto == 3 -> fire mode 3, else burst == 3 -> 2, on the AI entity's kit |
| 57 | 0x2bcd70 | 560 | CTFireWeapon::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | DEFECT-FIXED | C | no AI or not armed -> done; armed cleared; position from the task (bit 1), the cell centre (bit 3, GetCellCenter non-NULL) or the living target; PushAiState(DEPLOY 4, true), the state's option 1, target, zero offset, +0x40 = 0, item, setup bit; dT = 0. A port-only NULL test of the check-cast (0x2bcf04: cannot fail after a successful push) is removed |
| 60 | 0x2bd5e0 | 620 | CTEvent::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | select seal (GetSealCtrlAi called, result dropped), Acquire, duration (bit 2) or NoExpire, range bit 1 -> rangeSq = r r, visible bit 0, position: zero, the node's MTW transform ((r0 x + r1 y) + r2 z) + r3 (GetNode(m_node, false); a NULL node leaves zero) or the task's; owner id, type as (s8) & 0x7fff in the 15-bit field, Create; returns 1 without touching dT |
| 40 | 0x2ba460 | 684 | CTMove::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc(44), header (44 << 2), mode 0 / bit 5 cleared, pos zero, dist 0, dir unit_nz, target 0; "node" LoadNodeNames(NULL, node, 0, 1) mode 1, "relseal" toINT mode 3, "self" mode 2; "pos" else "ofs", "offset" else "dist", "dir" with mode 3 -> 4, "blocking" bit 5, "ai" select index (0 first) |
| 50 | 0x2bbb00 | 364 | CTInState::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "entity", "state", "stack" tag, get_state_fixup & 0xff == 0 -> NULL; length rounded to 4 + 16, header, the state in the low 31 bits of +0x8 (pads zero), anywhere bit 7 of +0xb, entity or "" |
| 36 | 0x2b7dd0 | 424 | CTPlay::Create(int, unsigned int*, float, float) | seal_tasks.cpp | MATCH | | size (count - 1) 4 + 40, header, quad_align, count in bits 1-8 of +0x20, the anim words copied (count > 0; the ELF's unrolled copy), +0x20 bits 9-16 cleared, prewait / postwait {w, 0} |
| 31 | 0x2b7250 | 328 | CTSetMode::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | select seal, its control, GetSealCtrlAi; no seal or control -> dT 0; AI: mode byte 0 -> SetSleeping(true), else SetAiMode(byte), true without touching dT; player with mode word 2: SetGoalPos(3, PosW, 3.0), on success tolerance -1 (+0x1ac), goal timer 1.5 / period {1.5, 0} (+0x1b8 / +0x1b0, mem.py) |
| 23 | 0x2b6010 | 320 | CTStance::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "stance", "peek", "delay" (0), get_stance, peek strcmp "left" -1 / "right" 1 / "up" 0 / else 2, _calloc(24), header (24 << 2), delay, peek and stance as sign-extended bytes |
| 43 | 0x2baa30 | 420 | CTMacro::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | no AI -> dT 0; ActivateArg(1, 1, seal +0x318 select, 3, GetNode(), 0) of the task's anim; with a handle: nobind bit (+0x280 bit 6) saved and set, PushAiState(SCRIPT, false), script anim (+0x28) and setup bit (written through the check-cast as the ELF), nobind restored; dT 0. Scan differences are the trace |
| 29 | 0x2b7050 | 220 | CTSetAnimSet::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | select seal and control (the ELF's GetSealCtrlAi call, result unused, is not made), no seal / control -> dT 0; BindAnimSet(name +0xc), default bit -> m_default_animset (+0x460) = m_animset (+0x45c); true without touching dT |
| 33 | 0x2b7a10 | 200 | CTPlay::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | select seal and control, keep-state bit (+0x20 bit 0) clear -> m_desiredState (+0x304) = stand (0) |
| 41 | 0x2ba710 | 400 | CTMap::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | mode byte 1: CNodeAction::GetAction(root, true) (the ELF inlines two levels of its dynamic_cast walk), GetActionById(id +0x2c, loc, &act), act invalid bit 4 of +0x8, valve value 99 with MakeCallbacks(1) when it changed; mode 2: GetRegion(&loc), SetRegionType(region, type byte); dT 0 |
| 55 | 0x2bc100 | 268 | CTGoto::End(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | select seal, control, AI, GetRouteComplete, Debug("CTGoto::End()\n"), armed bit 1 of +0xc. Scan differences are the trace |
| 13 | 0x2b4030 | 344 | CTWait::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | (the ELF's select lookup and GetSealCtrlAi call have no effect) timer == infinite (-1, c.eq.s) -> not done; else timer -= dT, done = timer != -1 && timer <= 0, then redrawn min + range (2^-31 rand) or min; dT 0, returns done |
| 14 | 0x2b4230 | 204 | CTWait::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | the timer drawn: min at range 0 (c.eq.s), else min + range (2^-31 rand); the unused lookups as row 13 |
| 21 | 0x2b5bd0 | 520 | CTState::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "push" (none -> NULL), get_state & 0xff == 0 -> NULL, "entity" for RUSH (29) and FOLLOW (9), FOLLOW without one -> NULL; length rounded + 40, header, state word, entity at +0x24 or ""; RUSH: "timer" (+0x14), "range" (+0x18), "contact" flag 4 (+0xc); FOLLOW: offset (0, 0, 20) then "offset" |
| 48 | 0x2bb800 | 444 | CTInView::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "viewer", "target", "equip", ParseTeamBlock("team"); no viewer, or neither target nor teams -> NULL; size = rounded viewer + 20 + rounded target, the viewer's name at +0x10 and the target's after its terminator (or ""), item GetWeaponId & 0xff or 0, teams |
| 19 | 0x2b55d0 | 296 | CTRange::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "entity", "range" (1000 = 0x447a0000), rounded length + 20, header, range squared, entity id unknownId (-3) with a name else invalidId, name or "" at +0x10 |
| 18 | 0x2b53f0 | 472 | CTRange::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | select seal and control (no seal / control -> dT 0, true), the inlined entity lookup (invalidId none, -3: GetEntity(name), else "player" -> index 0, id stored; else GetEntityById), no entity -> false; d = seal PosW - entity PosW, (x x + y y) + z z <= range (c.le.s) |
| 35 | 0x2b7c40 | 396 | CTPlay::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "anim" (none -> NULL), count = array count - 1, Create(count, NULL, 0, 0), each element (Get: element i + 1) of type 3 -> (s16) FindAnimType, else -1; "prewait", "postwait" Rfloats, "ai" (0 first) |
| 61 | 0x2bd860 | 448 | CTEvent::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc(36), header (36 << 2), pos zero, type 1 then (s8) GetEventFromString(type, 1), "pos", "node" -> LoadNodeNames(NULL, node, 0, 1) + bit 3, "range" bit 1, "duration" bit 2, "vis" bit 0 |
| 63 | 0x2bdc90 | 360 | CTDebug::Parse(_zrdr*) | seal_tasks.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: a list without values reads the type through NULL. Earlier: first value: integer -> enable and "Enabling DEBUG" / "Disabling DEBUG info" (the real branch of the inlined GetInt is dead), string -> text with enable -1, else NULL; rounded length + 16, _calloc, data_size only (type not set: quirk kept), text, enable. A list without values: the ELF reads the value's type at address 0; the port returns no record (reason in the code) |
| 32 | 0x2b74b0 | 212 | CTSelect::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc(16), header (16 << 2, type ai_cmdid +8), seal / AI NULL, GetEntity(element 1's string, no type test), type 2 -> seal and its GetSealCtrlAi, else both NULL |
| 42 | 0x2ba8a0 | 392 | CTMap::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "clear_action" present -> _calloc(20), header, mode 1; else "region" (none -> NULL), GetRegion(its "name", loc) (none -> NULL), "set_type" (none -> NULL), the type 1..6 whose GetTypeName matches (strcasecmp; the port's regionTypeName is that table), else 0; mode 2, loc, type word |
| 17 | 0x2b5260 | 400 | CTRegion::Parse(_zrdr*) | seal_tasks.cpp | DEVIATION-KEPT | | "entity", "region", "weapon", "team" (0), GetRegion(region, loc), rounded length + 28, header, loc, region NULL, team byte, pickup 0 then GetWeaponId & 0xff, entity unknownId / invalidId, cookie 0, name or "". The ELF's loc is an unset stack word when the region is not found; the port starts it invalid (reason in the code) |
| 59 | 0x2bd3a0 | 564 | CTFireMode::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc(28), header (28 << 2), dn 0.1 (0x3dcccccd) / up 0.8 (0x3f4ccccd), hint bits quiet 0, again 2, auto 1, burst 1, accuracy 0, range 0, use_index 0; "weapon" -> index & 0xf and use_index; "trigger" PNT2D -> bit 0, dn x, up y; "fullauto" -> auto 3, else "burst" -> burst 3 |
| 25 | 0x2b62d0 | 252 | CTSpecial::End(_zanim_cmd_hdr*) | seal_tasks.cpp | DEVIATION-KEPT | | select's AI Debug("CTSpecial::COMPLETE\n"), the argument commands from index 1 memset to 10 over data_size and _free("seal_tasks.cpp", 2768) until GetCmd is NULL, index 1, phase 0. The ELF calls Debug on a NULL controller (the player's select); the retail Debug reads nothing, the port's trace Debug reads its receiver: the port's test is kept, reason now in the code |
| 24 | 0x2b6150 | 376 | CTSpecial::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | GetCmd(index byte), GetCmdEntry(type), no entry -> done; phase 0: begin (if any), phase 1; phase 1: tick (if any) true -> 2; phase 2: end (if any), phase 0, index + 1; dT 0, returns done |
| 39 | 0x2b98d0 | 452 | CTPaint::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "region" + GetRegion (either missing -> NULL), _calloc(20), header, loc, value 0, mask 1, mode / +0x13 0; "soil" -> mode 1, (u8) GetSoilByName, mask | 4; else "boundary" < 3 -> mode 2, value, mask | 8; else "reg_type" -> mode 3, type 1..6 or 0, mask 0 |
| 64 | 0x2be2f0 | 552 | CTAction::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | DEFECT-FIXED | C | no AI -> dT 0; FindActionByValve(GetValve(m_valve)); auto_return: PushAiState(GOTO 8, true), dest = the AI entity's m_mapLocValid, setup; PushAiState(ACTION 11, true), action (+0x28), value u16 state (+0x2c), setup; dT 0. Two port-only NULL tests of the check-casts (0x2be3dc, 0x2be4bc: cannot fail after a successful push) are removed |
| 34 | 0x2b7ae0 | 348 | CTPlay::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | select seal and control (no seal / control: nothing), pre timer (+0x18) and post timer (+0x1c) each min at range 0 (c.eq.s), else min + range (2^-31 rand) |
| 37 | 0x2b80b0 | 228 | CTPursue::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | select AI, PushAiState(PURSUE 12, true), the state's duration (+0x28) and setup bit written through the check-cast as the ELF |
| 16 | 0x2b4b40 | 260 | CTTeam::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "join" 0, "leave" 1, "ismember" 2 (first found), none -> NULL; _calloc(16), header, op (+0xc), mask = ftmask_create(tag) (+0x8) |
| 20 | 0x2b5750 | 208 | CTStopAll::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | zrdr_tobool (default true), "inactive" tag, _calloc(12), header, flags byte bit 0 off, bit 1 inactive |
| 30 | 0x2b7130 | 276 | CTSetAnimSet::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "name" (none -> NULL), "default" (false), rounded length + 16, header, default bit, name at +0xc |
| 45 | 0x2bacd0 | 276 | CTMacro::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | "anim" (none -> NULL), "blocking" tag, rounded length + 20, header, anim NULL, blocking bit, name at +0x10 |
| 54 | 0x2bc030 | 208 | CTHold::Parse(_zrdr*) | seal_tasks.cpp | MATCH | | _calloc(20), header, wait {-1, 0}, timer 0, "wait" Rfloat, a bare true / false -> {-1 / 0, 0} |
| 49 | 0x2bb9c0 | 312 | CTInState::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | select seal and its AI (no controller test), a named entity of type 2 replaces both (else NULL), no seal or AI -> false; anywhere bit -> FindAiState(state) != NULL, else AiStateIs(state); dT untouched |
| 26 | 0x2b6c50 | 272 | CTSignal::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | select AI (no controller test), a named entity of type 2 gives its AI, any other name NULL; AnimSignal(ZAnim.m_CurAnim, signal byte); dT 0, true |
| 44 | 0x2babe0 | 232 | CTMacro::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | select AI tested, GetAnim(name, NULL) into +0x8 (the ELF's skip over 0 earlier strings is empty) |
| 53 | 0x2bbf30 | 256 | CTHold::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | MATCH | | select AI tested, timer min at range 0 else min + range (2^-31 rand), stored, a non-zero time (c.eq.s / bc1t) -> SetAiMode(2) |
| 22 | 0x2b5de0 | 208 | CTStance::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | no AI -> dT 0, true; timer (+0x14) -= dT, dT 0, timer <= 0 (c.le.s) |
| 46 | 0x2bb0b0 | 264 | CTLookAt::Begin(_zanim_cmd_hdr*) | seal_tasks.cpp | DEFECT-FIXED | B | the ELF tests the seal and its controller and drops GetSealCtrlAi's result (0x2bb134 / 0x2bb13c), as Tick does (audit-large-b row 73); the port also required an AI, so a seal without one (the player in an action anim) kept a stale look timer that Tick then counts down. Now the ELF's tests; the draw min / min + range (2^-31 rand) compared |
| 52 | 0x2bbe50 | 224 | CTHold::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | no AI -> dT 0, true; done = timer <= 0 (c.le.s), else timer -= dT; dT 0 |
| 56 | 0x2bc210 | 240 | CTGoto::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | no seal / control / AI -> dT 0, true; GetRouteComplete, dT 0, the wait bit (+0xc bit 0) returns it, else true |
| 62 | 0x2bdb70 | 280 | CTDebug::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | no seal / control -> dT 0, true; no AI -> true; enable word 1 / 0 -> SetDebug(true / false), Debug("%s\n", text) |
| 47 | 0x2bb680 | 372 | CTInView::Tick(_zanim_cmd_hdr*, float*) | seal_tasks.cpp | MATCH | | viewer GetEntity(names) of type 2, item 0 or IsUsingItem(item & 0xff); no teams: FindTarget(GetEntity(second name)) visible (+0x24 bit 2); teams: the first 40-byte target whose entity's team & mask with the visible bit; dT 0 |
| 38 | 0x2b96a0 | 380 | get_param(char const*) | seal_tasks.cpp | MATCH | | NULL -> 0, the 12 strcmp names in ELF order with 1, 2, 3, 5, 6, 8, 7, 9..13, else 0 |
| 51 | 0x2bbc70 | 292 | get_state_fixup(char const*) | seal_tasks.cpp | MATCH | | get_state first (NULL name or non-zero byte returns it), then the 8 strcasecmp names -> 9, 3, 10, 4, 2, 20, 20 ("reloading": quirk kept), 29, else get_state's answer |
