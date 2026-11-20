# Audit of list medium-seal-a (2026-11-19, socom-port-audit-mseal-a)

101 functions (37,060 bytes) in six zSeal files: `seal.cpp` 20, `seal_aievent.cpp` 1,
`seal_cfg.cpp` 7, `seal_ctrl.cpp` 4, `seal_env.cpp` 67, `seal_squirm.cpp` 2. HEAD 1c855f56 (the
later commits up to 531affea touch no zSeal file). Judged in the scan's rank order (the small
files and the twin functions together), each over its whole address range against the packet's
disassembly; addresses quoted below and every delay slot relied on were checked in
`build/port/boot-auditkit/ref.dis`.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 82 |
| DEFECT-FIXED | 18 (A 0, B 0, C 18) |
| DEVIATION-KEPT | 1 |
| UNJUDGED | 0 |

Defect rate 18 / 101 (17.8%), all grade C: 9 rows of NaN-only compare forms, 4 rows of a body-part

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #4 (the user's rule: the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)).
slot test's signedness, 3 unrecorded controller NULL tests, 1 float sum order. None changes what
the player sees on this disc.

## Fixes

- C `CZSealBody::HandleLanding` 0x29e920 / 0x29e988 / 0x29ea08: !(wait <= 0), !(impact <= hard
  rate), !((x x + y y) + z z <= 400), as the ELF (the port had > / < forms).
- C `CZSealBody::NormalizeToTerrain` 0x24fa58 / 0x24fa78 / 0x24faa4 / 0x24fb00 / 0x24fb40: the
  terrain weight window's not-<= / not-< forms and the !(w <= 0) tilt test.
- C `CZSealBody::GetTerrainMotionFactor` 0x2a2acc / 0x2a2af4 / 0x2a2be8 / 0x2a2c38: water on
  !(depth <= 0), w kept unless w < min, slope on !(d <= 0), 1 on !(f <= 1).
- C `CZSealBody::DamageRLeg / DamageLLeg / DamageLArm / DamageRArm(float, float)` 0x295160 and the
  twins: level 2 is h <= 0.7 max (c.le.s); the port had !(0.7 max < h).
- C `CZSealBody::SetEyeLookDir` 0x29dbd8 / 0x29dc28: the second branch on pitch < 0 / yaw < 0.
- C `CZSealBody::HandleFootfallSound` 0x292150 / 0x292160: the step sound on !(throttle <= 0.5).
- C `CZSealBody::PostChangeWeapon` 0x296f80 / 0x296fb4, `ChangeToRifleMode` 0x2984b4,
  `ChangeToPistolMode` 0x2985d8, `ParentPistolToRThighAsGearCallback` 0x298764: the body-part slot
  test is lh id sltu size; the port compared (u16) id with (u16) size (no reachable difference).
- C `CZSealBody::SetHealth` 0x24f634 / 0x24f6b0, `OnWeaponHit` 0x29c54c, `DropAllItems` 0x28eb28:
  the controller is called unchecked; the port's unrecorded `m_control != NULL` tests removed
  (every caller's seal has a controller, as audit-large-a did for CanUseKnife / CanUseCQB).
- C `DrawAutoReticle` 0x29b7d0: the first tick's far end is y + (distOff + retLen).

## Kept deviations

- `CZSealBody::NetworkPlayerCreate` 0x24db80: PLAYERNAMEVAR found but no string gives an empty
  name where the ELF strncpy's from NULL (already recorded in the code).
- `CZSealBody::CanPickupNetItem` 0x28d0a0: 0x28d1ec tests the entity, not the seal, so a non-seal
  asker would get HandlePickupAck on NULL; the port tests the seal (reason now in the code).

## Leads for other lists

- `CZSealBody::ChangeWeapon` 0x297060 (seal_env.cpp, audit-large-a) and
  `ParentPistolToRHandCallback` (seal_env.cpp, not listed): the body-part slot tests are lh id sltu
  size in the ELF (0x2972bc, 0x2972f0, ...) but the port has (u16) id < (u16) size, as fixed here
  in rows 68-71 (no reachable difference).
- `CZSealBody::UpdateHealth` 0x294210 (audit-large-a): the level-2 tests are c.le.s h, 0.7 max
  (0x2942c4, 0x294488, ...) while the port writes !(0.7 max < h) (seal_env.cpp, the body level and
  the limb lambda): a NaN-only form, as fixed here in rows 64-67.
- The `seal_control.cpp` `m_screenOffset.y` lead: none of this list's functions stores it twice;
  SetCurZoomState writes +0x450 then +0x454 as the ELF.

## What the packets lacked

- Enumerator values of port-named enums the body uses: STUN_TYPE (#62, #63), ACTION_TYPE (#30),
  EQUIP_ITEM C4 (#61), VALVE_TYPE (#17); and bitfield positions of the structures written through
  other registers: CAiEvent m_type (#14), SealAiNetState (#2, #3), CZProjectile flags (#83),
  CAiCell m_inside (#22), CEntity m_isAlive (#18) - all read from the headers.
- Helper bodies past the first level or in other files: CSealCtrl::CanPerformAction (#30), the
  Get*Damage level helpers (#45-#48), CZSealBody::GetAnimByType (#26), CNode::SetActive's return
  (#97, #99), CZWeapon::PackItemAndAmmoEnums (#37).
- How the callers use a return value the port declares differently (PickupObject, BindAnimSet(name),
  CreateMPBombPickup, PostMortemPreTick): from ref.dis.
- The member labels on CZSealBody bitfield bytes are misleading (+0xdd shown as
  m_update_targetlist for m_isAlive, +0xf5a as m_was_turning for m_airborne); the offsets were right.

## Runs

- The default build links (`default.sh audit-mseal-a-default`, HEAD + this list's files) after the
  first fixes and on the final tree.
- Smoke (bodies that run in a mission; SetHealth / DropAllItems / HandleKiller on the death path):
  run `mseal-death` (`tb.sh -k death`, -DSOCOM_HOOK_KILLER, pad_t1, 160 s): in m8 at the hook's
  frame 300 the nearest enemy is made the killer (HandleKiller), the real fatal fall kills the player
  (UpdateHealth -> SetHealth(0) -> OnDeath, now without the controller tests), DropAllItems drops the
  ammo box and both guns, the mission ends to the debrief and dlgHype at 143 s; no STOP or exception.

## Verdicts

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 62 | 0x293f30 | 336 | CZSealBody::HandleStunDamage | zSeal/seal_env.cpp | MATCH | | index (u8) < 8 out, running = !(val <= 0), m_stunned 1, raise to amount, controller slot 0x50 (type, the new value, position), table 0..6: -10 / -6 / -3 / -3 / - / - / -3 on m_retmods when not running (STUN_* values checked in zseal.h) |
| 7 | 0x24df40 | 408 | CZSealBody::SetCurZoomState | zSeal/seal.cpp | MATCH | | same state out, prev / state / echo, TriggerPowerReset, node +0x9c 255 / 0, IsPlayer (slot 0x2c) -> m_iszooming, not 1st person: camera m_screenOffset x / y 0, ranges 1 / 1.5 / 1.5 / 9 + sniper kick, weapon modes: index state - 3 < m_zoommode size (+0x1c4) -> GetZoomRange, kick unless prev 5 |
| 53 | 0x2919a0 | 440 | CZSealBody::HandleBloodDrip | zSeal/seal_env.cpp | MATCH | | health < 1, network out, timer !(<= 0) -= dT, 3 x (2^-31 r) (word 0x30000000), size 0 out, one handle or rand % size (signed div, rand >= 0), 12-byte defs, visual node of m_last_altitude's node, -norm, size min + r (max - max) (quirk), GetDecalNode, ApplyDecal(decal, 100, pos, -norm, projDirDown, tex, size, NULL) |
| 95 | 0x2a0350 | 668 | CZSealBody::PreClimbLadderDown | zSeal/seal_env.cpp | MATCH | | top refpt info invalid, IsRemote twice, remote: homing all zero, not ClimbOffLadder (48): ClearStack(1, 1), goal read before Representative, y - 1.412, norm negated in place, refpt (0x3eb1a9fc, -1.412 - 11.487 = 0xc14e624d either rounding, 0x404ccccd), norm, int, refvec unit_z / target (0, 8, 0) after the overwritten unit_nz / zero (quirk) |
| 39 | 0x28e7b0 | 688 | CZSealBody::DropAmmo | zSeal/seal_env.cpp | MATCH | | network non-player out, new 36-byte box (3 vectors), FillAmmoPickupInstance (both branches identical), zero through m_quat + GetPosW, YXZ 0, "fiftycal_box", no node: box deleted, dynamic, character bit 2 of 0x9a, textures 2, NetworkCreate(m_id, 9) + FillNetworkAmmoPickupValues + SendAmmoPUMessage(count, items, rounds, netid +0xc, pos) or Create(9), drop anim (1, 3, node, 0) when both set |
| 91 | 0x29e8f0 | 516 | CZSealBody::HandleLanding | zSeal/seal_env.cpp | DEFECT-FIXED | C | NaN-only forms: 0x29e920 !(wait <= 0), 0x29e988 !(impact <= hard rate), 0x29ea08 !((x x + y y) + z z <= 400); the port had > / < forms: fixed. Rest matches: JumpLandHard 11 / JumpLand 10 out, falling damage, (u8) damage 3 -> LandForward01 state 8, 2 / 1 / 0 -> 11, soft: 10 unless fast with strafe then fb not close to 0, carry out, snapshot flag saved / set / restored, BodySetState(8 -> 0) |
| 94 | 0x2a0210 | 312 | CZSealBody::AlignForPickup | zSeal/seal_env.cpp | MATCH | | top (unchecked), refpt BuddyPickupRefpoint and target zero copied first, dir negated in place, homing blend, refpt, norm = -dir, int = pos, refvec unit_nz, target zero twice (quirk) |
| 100 | 0x2e2c50 | 324 | CSealCtrlSquirm::Initalize | zSeal/seal_squirm.cpp | MATCH | | on 1, +0x260 8 / 0, kit (entity + 0x520, tested) item 0 / fire mode 3, hold 5 / 0, wait 1 / 0, the wait's test compares 0 with 0 (quirk: always the minimum), hold drawn unless range == 0 (r 2^-31), m_until = double(timer) + double(hold) |
| 101 | 0x2e2e00 | 372 | CSealCtrlSquirm::CSealCtrlSquirm | zSeal/seal_squirm.cpp | MATCH | | CSealCtrl base, +0x240 0, on 0, wait 0x3dcccccd / 0x3ecccccd, hold 0.5 / 0x3f333334, timer = draw(wait) then draw(hold), until in double, +0x260 / +0x264 0, +0x268 = draw (Rfloat operator inline: range == 0 -> min) |
| 93 | 0x29ff80 | 580 | CZSealBody::CheckDILadder | zSeal/seal_env.cpp | MATCH | | root part (slot 0x64) node translation, GetPosW, ahead (0, 0, -8), y += ClimbOffLadder (48) refpoint y, x == 0 and z == 0: unrotated, else rows 0-2 VU0 (x m0 + y m1) + z m2, + posw; p + ahead rotated unconditionally, + posw; SealGetIntersect != NULL |
| 83 | 0x29bdd0 | 544 | CZSealBody::HandleDamageExplosive | zSeal/seal_env.cpp | MATCH | | GetDamage(posw, 0), !(<= 0): network non-player out, ammo explosion damage / radius else 10 / 30, FlingBody(framestartpos); else network and not m_isplayer (bit 2 of +4) out; m_isfirsthit (bit 1) 0, temp projectile, old DI deleted, new DiIntersect(64), head PartInSpace, m_quat Apply, + posw, RegIntersectDelayed(framestartpos, head), RegIgnoreNodeDelayed(node) |
| 89 | 0x29e450 | 580 | GetLookQuat | zSeal/seal_env.cpp | MATCH | | fabsf both, close_enough(pitch, @3114 0, @3115 0x3c23d70a), yaw < 0 -> axis 6 else 2, Scale(0.5 x abs yaw), Exp, flat -> out = qy, pitch < 0 -> axis 9 else 3, 0.5 x abs pitch, Exp, qy.Mul(qp, out); the ELF's four unrolled paths are the same calls |
| 26 | 0x27e010 | 416 | CZSealBody::SetMaxMotion | zSeal/seal_cfg.cpp | MATCH | | set SetMaxMotion, set re-read once, GetAnimByType inline (set NULL -> NULL) for ProneCrawl 27 (+0x20 / +0x24, velocity called twice), ProneRStrafe +0x28, ProneLStrafe +0x2c, ClimbLadder 47 +0x30; vel x thr_scale, 0 without anim |
| 14 | 0x24ed60 | 292 | CZSealBody::ExecuteAction_CQBAttack | zSeal/seal.cpp | MATCH | | NULL victim false, victim SetHudHitFlag, GetAnim("ai_cqb_attack", NULL), ActivateEx(2, own m_select, victim m_select, NULL), started: m_num_cqb_used++, event (owner m_id, victim GetPosW, rangeSq 4, 0x3dcccccd, type bits 17-31 of +0x18 = AIE_WEPHIT 5), Create; true |
| 68 | 0x296e70 | 452 | CZSealBody::PostChangeWeapon | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x296f80 / 0x296fb4: the body-part slot test is lh id (signed) sltu size; the port compared (u16) id with (u16) size: now (u32)(s32) id < size (no reachable difference). Rest matches: (u8) item 2: rifle node out of its parent (slot 0x1c of the node vtable at +0x60), to m_spinelo, AddChild (0x18), blendme 0, rifle as gear; 1: ReParentToRifle, to m_rhand, slot = rifle, blendme 0, weapon slot NULL, m_item 1, RePose(1), pistol as gear; aimpoint / firepoint nodes |
| 41 | 0x28f220 | 200 | CZSealBody::SetupDefaultArmor | zSeal/seal_env.cpp | MATCH | | each of the six m_armor < 0 -> 0 (the ELF's order 0, 3, 2, 1, 4, 5: independent) |
| 42 | 0x28f2f0 | 204 | CZSealBody::SetupKevlarArmor | zSeal/seal_env.cpp | MATCH | | as row 41 with m_armor[3] < 30 -> 30 |
| 43 | 0x28f3c0 | 204 | CZSealBody::SetupKevlarInsertArmor | zSeal/seal_env.cpp | MATCH | | as row 41 with m_armor[3] < 60 -> 60 |
| 85 | 0x29cdf0 | 312 | CZSealBody::ApplyLookAnim | zSeal/seal_env.cpp | MATCH | | head, then +0x20 parents: GetLookQuat(Rlookhead / neck / spinehi / spinelo, yaw, pitch, q), rot.Mul(q, r), rot = r (operator= then w) |
| 1 | 0x24d6e0 | 280 | CZSealBody::TickHeartbeat | zSeal/seal.cpp | MATCH | | adrenaline value or 1, < 0x3ea8f5c3 -> 0, < 0x3f28f5c3 -> 1, else 2; playing and other index: Stop, Release, NULL, sound[index] slot 0xc (NULL, 255) unchecked (quirk), index; none playing: sound tested, play, index |
| 18 | 0x24f590 | 320 | CZSealBody::SetHealth | zSeal/seal.cpp | DEFECT-FIXED | C | 0x24f634 / 0x24f6b0 call OnSetHealth (slot 0x54) unchecked; the port's two unrecorded m_control NULL tests removed (every caller's seal has a controller). Rest matches: same health returns it, invincible (bit 3 of 0xf58) <= 0 -> 0x3dcccccd, m_isAlive (bit 3 of 0xdd), dead and > 0: notify (health, old), alive, target list; alive and <= 0: death type byte, OnDeath (slot 0x4c); else notify; returns m_health |
| 82 | 0x29bc20 | 428 | CZSealBody::HandleDamageNonExplosive | zSeal/seal_env.cpp | MATCH | | network and not m_isplayer out; head / neck -> DamageHead + last projectile, lbicep / lforearm -> LArm, rbicep / rforearm -> RArm, spinehi / spinelo / hips -> Body + last, lthigh / lcalf and rthigh / rcalf: m_rleg_health <= 0 -> body (quirk for the left leg) else LLeg / RLeg; body afterwards |
| 84 | 0x29c430 | 488 | CZSealBody::OnWeaponHit | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x29c54c calls the controller's OnWeaponHit (slot 0x4c) unchecked; the port's unrecorded NULL test removed. Rest matches: invincible out, network friendly fire (id != 0, flag, seal shooter, team overlap, not hostage 0x20000, not self) out, alive and node active (bit 0 of +0x5c): adrenaline 0x3f7d70a4, m_wephit pos / norm / node or node NULL, HandleDamage; else FindRandomDeathAnim(3) + WeaponHitAnim(anim, 8, false) |
| 30 | 0x283750 | 404 | CSealCtrl::InitMPBomb | zSeal/seal_ctrl.cpp | MATCH | | GetReticuleAction(true) first, defusal node -> mpbomb node, 5, engaged bit 5 of 0x169; NULL action out; CanPerformAction inline (type 6 / 4: bomb state 2 CanPlaceBomb, 1 / 3 no, else entity, item 152 HasItem / ItemHasAmmo, valve +0x18 value (u16 +4) 0; others yes) and type 4 (ACT_MPBOMB): last reticule node, 5, engaged |
| 23 | 0x27dab0 | 256 | CZSealBody::SetupEyes | zSeal/seal_cfg.cpp | MATCH | | FindAuxNode(right_eyeball / left_eyeball / right_lid / left_lid, true), NewBodyPart(node, m_head) or NULL into +0x2e0..+0x2ec |
| 24 | 0x27dc60 | 232 | CZSealBody::AddItem | zSeal/seal_cfg.cpp | MATCH | | CreateInstance(name), NULL false, AttachAuxNode(node, parts[partid], +28 offset, +40 rotation), id (s16) BodyId(name), node SetName, blendme 0, new 8-byte OBJ_ANIM (part, gear) when allocated, pushed even NULL, true |
| 25 | 0x27dd50 | 216 | CZSealBody::AddDIPolys | zSeal/seal_cfg.cpp | MATCH | | ResolveMaterialIndex("PERSON"), every body part not NULL / rifle / pistol / grenade / weapon: SetDIBBox(node, node +64 bbox, true), SetMaterial |
| 27 | 0x27e7b0 | 492 | CZSealBody::BindAnimSet(AnimSet*) | zSeal/seal_cfg.cpp | MATCH | | NULL / same out, carrying: root parent set -> state 10 both ClearToBase(false), DetachBody; else state 9 the same, carry DetachBody; old set: s16 types < GetAnimTypeMax, AnimId >= 0, anim type -1; new set, types; SetMaxMotion, ClearBlendOverlay, ClearStack(0, 1), PushBlend(1, 0, 0), top representative wt 1, Snap |
| 28 | 0x27e9a0 | 216 | CZSealBody::BindAnimSet(const char*) | zSeal/seal_cfg.cpp | MATCH | | AnimSet::list walk, strcmp(name, set name), first match bound; the ELF's bool return is ignored by its only caller (CTSetAnimSet::Tick 0x2b70ec), so the port's void is harmless |
| 29 | 0x280eb0 | 380 | BodyId | zSeal/seal_cfg.cpp | MATCH | | map filled once from the table (32-byte names), find -> value, count < 64 (signed) and strlen < 32 (unsigned): map[name] = count, strcpy, count++, id; else 0 |
| 31 | 0x283c00 | 512 | CSealCtrl::PerturbAimVector | zSeal/seal_ctrl.cpp | MATCH | | up (0, 1, 0), dir x up -> right, right x dir -> top (no normalise), r = (rand - 0x3fffffff) x 2^-30 (0x30800000), signed square, right x (FactorX + Factor r), second draw, top x (FactorY + Factor r), dir = (dir + right) + top |
| 32 | 0x283f20 | 248 | CSealCtrl::PostMortemPreTick | zSeal/seal_ctrl.cpp | MATCH | | pad of m_padid < 2 (unchecked after), ThrottlesPreTick, advance / retreat camera = RIGHT / LEFT rising (state 3) and menu != 1, network: theVoice block talk, else SELECT + CROSS -> needs respawn; the ELF's return 1 is not used (void in the port's virtual) |
| 33 | 0x284180 | 216 | CSealCtrl::TickRumbler | zSeal/seal_ctrl.cpp | MATCH | | pad of m_padid < 2, NULL out, !(rumble time <= 0): act[1] = (u8) fptosi(strength), time -= dT; else strength 0, act[1] 0; !(high time <= 0): act[0] 1, time -= dT; else 0 |
| 22 | 0x2dea90 | 300 | CanHearAttenuatedExplosionEvent | zSeal/seal_aievent.cpp | MATCH | | m_inside (bit 24, byte 3 bit 0) of each cell (NULL false), both: dist <= 40000 x 1 else x 16, one: x 4, none x 1, left = (range - dist s) / range, <= 0 false, 0 + 1 x (2^-31 r) <= left |
| 2 | 0x24d8f0 | 316 | CZSealBody::UnMakeGhost | zSeal/seal.cpp | MATCH | | node opacity 1, SetActive(true) (slot 0x34 of the vtable at +0x60), zeroed state, active (bit 0 of +0x5c) and !(opacity <= 0): fptoui(floorf(15 (1 - op))) into bits 24-27 (argument >= 0), else 15; ghost bit 30 0; SetAiNetState (slot 0x70) with the word |
| 3 | 0x24da30 | 324 | CZSealBody::MakeGhost | zSeal/seal.cpp | MATCH | | SetHealth(0, 6), opacity 0, SetActive(false), transparency as row 2 (15 here), ghost bit 30 1, SetAiNetState |
| 4 | 0x24db80 | 312 | CZSealBody::NetworkPlayerCreate | zSeal/seal.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: a PLAYERNAMEVAR that is no string strncpy's from NULL. Earlier: recorded: PLAYERNAMEVAR found but no string (type != 3) gives an empty name where the ELF strncpy's from NULL. Rest matches: m_oktocallinit, strncpy 31 / "Player%d" of the client index, name[30] 0, GetByNameMod(net char type), squirm (ftsGetSquirm) or plain controller (the ELF's 624 / 576 bytes are its sizes; the port's own sizeof), Create, ftsSetPlayer, node name, team mask of m_pNetGame +0x90, vehicle index 0, display name |
| 5 | 0x24dcc0 | 240 | CZSealBody::DecrZoomState | zSeal/seal.cpp | MATCH | | table 0x450e10: 0 stays, 1 -> 0, 2 -> 1, 3 -> 1 + sniper kick, 4..11: weapon NULL stays, state - 4 < 1 -> night 2 else 1, else < zoom mode count (signed) -> state - 1; SetCurZoomState, returned |
| 6 | 0x24ddb0 | 396 | CZSealBody::IncrZoomState | zSeal/seal.cpp | MATCH | | table 0x450e40: 0 -> 1; 1: night -> 2, else 3, weapon with >= 2 modes -> 4; 2 / 3: >= 2 modes -> 4, two sniper kicks (quirk); 4..10: state - 2 < count (unsigned) -> state + 1, two kicks each unless prev 5; 11 stays; SetCurZoomState, returned |
| 8 | 0x24e1a0 | 240 | CCompass::DeleteAnchor | zSeal/seal.cpp | MATCH | | NULL out, m_compass walk: match -> swap with the last (size >= 2, not last), size-- and the walk goes on, name _free("seal.cpp", 4901) and cleared, delete; the ELF's bool return is not read (recorded) |
| 9 | 0x24e290 | 428 | CCompass::CreateAnchor | zSeal/seal.cpp | MATCH | | new 24 bytes: enabled bit 0 1, arrow / name / echo bits 1-3 0, type bits 4-19 0, unused bits 20-31 0, pos zero, name / map loc NULL, pos, name freed if set, _strdup(name, "seal.cpp", 4906) when given, push_back |
| 10 | 0x24e6c0 | 260 | CSealStats::Shot | zSeal/seal.cpp | MATCH | | shots++, network non-player out, hit percent (f32) hits / shots, again out, (s16) (kills + (tied + 2 won)) from the low halves, << 8 + (hits << 8) / shots (0 without shots), sh |
| 11 | 0x24e900 | 236 | CSealStats::Kill | zSeal/seal.cpp | MATCH | | network non-player out, kills++, again out, MVP as row 10 |
| 12 | 0x24e9f0 | 260 | CSealStats::Hit | zSeal/seal.cpp | MATCH | | hits++, then as row 10 |
| 13 | 0x24eb70 | 236 | CSealStats::DeductKill | zSeal/seal.cpp | MATCH | | as row 11 with kills-- |
| 15 | 0x24f050 | 304 | CZSealBody::RetreatPiggyBack | zSeal/seal.cpp | MATCH | | camera entity index, i = start - 1 until start: < 0 wraps to the list count - 1, seal of index (type 2) else player and i--, alive (bit 3 of 0xdd) or the player, team overlap -> found; AttachTo (slot 0xc) unless back at the start |
| 16 | 0x24f180 | 288 | CZSealBody::AdvancePiggyBack | zSeal/seal.cpp | MATCH | | as row 15 forward: i = start + 1, no seal at i -> player and i = 0 |
| 17 | 0x24f330 | 392 | CZSealBody::PickupObject | zSeal/seal.cpp | MATCH | | alive / NULL out, type (bits 0-6 of +8) 10 -> 0, 11 MPBomb, 9 ammo instance, 8 equip, 1: "ai_pickup_grenade", temp valve (2) + callback(1, _rethrow_grenade, pickup), projectile SetVelW(NULL), unit matrix, AlignToPoint(node matrix, pickup pos, mat, 0), SetMatrix, ActivateArg(1, 3, node, 1, m_select, 4, valve, 0); the ELF returns the anim pointer, its callers test it with beqz (the port's bool is equivalent) |
| 19 | 0x24f9a0 | 612 | CZSealBody::NormalizeToTerrain | zSeal/seal.cpp | DEFECT-FIXED | C | NaN-only forms: the ELF sets the weight 1 on !(t <= b) (0x24fa58), takes the rising window on !(b <= a) (0x24fa78), 1 on !(t < b) (0x24faa4), 0 on !(t < a) (0x24fb00) and tilts on !(w <= 0) (0x24fb40); the port had b < t, a < b, b <= t, a <= t, w > 0: fixed. Rest matches: airborne (top state 8 else out) 0x3f4ccccd / 0x3f7d70a4, else the representative's terrnorm0 / 1 (+0x1c / +0x20, called twice), t = tfrac, (t - a) / (b - a), 1 - (t - b) / (a - b), conjugate m_quat Apply(last altitude norm), Align(unit_y, n), Pow(w, root part rot) |
| 20 | 0x256c80 | 516 | CZSealBody::UpdateStance | zSeal/seal.cpp | MATCH | | top flag 0x40 or Stand2Crouch 17 / Crouch2Prone 19 / Stand2Prone 25 current, (u8) desired: 0 (top not 19): state 1 / 2 -> m_stancechanged, Stand(1), SetStance(0); 1: state 0 / 2 -> Crouch, SetStance(1); 2 (top not 17): state 0 / 1 -> Prone, SetStance(2) |
| 21 | 0x256e90 | 336 | CZSealBody::AddWeapon | zSeal/seal.cpp | MATCH | | new CNode (NULL tested) appended to m_deallocList, (u8) item 3 rhand "grenade", 2 rhand if current else hips "pistol", 1 rhand if current else spinelo "rifle", other: parent NULL and no name, AddBodyPart, m_weapons[item] unbounded (port sized), part != NULL |
| 80 | 0x29a540 | 356 | CZSealBody::GetReticuleAction | zSeal/seal_env.cpp | MATCH | | reticule action node else reticule node, GetAction inline (dynamic_cast of +0x94 to CNodeAction, the parent once, then the call), NULL out, valve (unchecked) value 99 or type 7 -> action, unit matrix, BuildMTW, translation SubXZ posw, x x + z z (mula / madd), in range: !(d <= range^2) -> NULL |
| 73 | 0x2990a0 | 208 | CZSealBody::AimWeapon | zSeal/seal_env.cpp | MATCH | | (u8) item 2 pistol / 1 rifle: PartInSpace(part, NULL, pos, rot), rot Apply(unit_x) into m_aim_dir; else unit_nz |
| 49 | 0x290990 | 252 | CZSealBody::SetBodyDamage | zSeal/seal_env.cpp | MATCH | | GetBodyDamage(health, max) == level out, 4 0x3dcccccd / 3 0x3e99999a / 2 0x3f333333 / 1 0x3f666666 / else 1, f max - 0x3c23d70a, UpdateHealth(3, 5) |
| 48 | 0x290850 | 320 | CZSealBody::SetHeadDamage | zSeal/seal_env.cpp | MATCH | | inline head levels (<= 0: 3, <= 0.5 max: 2, <= 0x3f7d70a4 max: 1), 4 0.7 (quirk) / 3 0 / 2 0.5 / 1 0x3f7d70a4 / else 1, f max - 0.01, UpdateHealth(0, 3) |
| 45 | 0x290430 | 352 | CZSealBody::SetLLegDamage | zSeal/seal_env.cpp | MATCH | | inline limb levels (0.3 / 0.7 / 0.9 of max), 4 and 3 0x3e99999a / 2 0.7 / 1 0.9 / else 1, f max - 0.01, UpdateHealth(5, 0) |
| 46 | 0x290590 | 352 | CZSealBody::SetRArmDamage | zSeal/seal_env.cpp | MATCH | | row 45's stream (diffed) on +0xf10 / +0xf14, location 1 |
| 47 | 0x2906f0 | 352 | CZSealBody::SetLArmDamage | zSeal/seal_env.cpp | MATCH | | row 45's stream (diffed) on +0xf08 / +0xf0c, location 2 |
| 35 | 0x28c470 | 208 | CZSealBody::RemoteDropMPBomb | zSeal/seal_env.cpp | MATCH | | item 154 index, != -1 RemoveItemAndAmmo, GetPosW copy, CreateMPBombPickup(pos, false), FindAuxNode("Satchel", false) SetActive(false) when found, PerformAction(PlaceClaymore, 0), controller bit 4 of +0x168 |
| 52 | 0x2917f0 | 224 | CZSealBody::GetHeadParams | zSeal/seal_env.cpp | MATCH | | PartInSpace(m_head, NULL, pos, NULL), node matrix Transform (VU0 inline, w 1) in place, Rotate(look +0x10 curr dir, dir, 1) |
| 63 | 0x294080 | 252 | CZSealBody::HandleStunRecovery | zSeal/seal_env.cpp | MATCH | | m_am_stunned (bit 4 of 0xf5c) 0, (u8) type < 7 table: +10 / +6 / +3 / +3 / - / HandleStunDamage(6, 20, NULL) / +3 on m_retmods |
| 60 | 0x293d20 | 268 | CZSealBody::TickStun | zSeal/seal_env.cpp | MATCH | | stunned out, cleared, 7 timers: running = !(v <= 0), running and char type: v -= (f32) s32 recovery factor x dT, !(v <= 0) -> stunned, running and now <= 0 -> HandleStunRecovery(i) |
| 61 | 0x293e30 | 244 | CZSealBody::HandleStunFromHit | zSeal/seal_env.cpp | MATCH | | (u8) item 171 / 153 / 152 / 151 / 126 / 121 -> stun 4 for 2, 161 -> 5 for 100, 122 -> 3 for 2, 125 -> 1 for 3, 123 -> 0 for 2, position passed |
| 81 | 0x29b650 | 632 | DrawAutoReticle | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x29b7d0: the first tick's far end is y + (distOff + retLen); the port summed (y + distOff) + retLen: fixed. Rest matches: world-to-screen (camera +0x3c0 + 32) on (p, 1) xyzw ((m0 x + m1 y) + m2 z) + m3, (s / w - 2048) + 320 / 224 with 1 / w, colours (1, 0, 0, 0x3e4ccccd) / (1, 0, 0, 1), up, down (- 2 d, - 2 (d + r)), right (x + d, x + (d + r), y), left; no w test (quirk) |
| 96 | 0x2a15d0 | 632 | CZSealBody::PlaceLaterally | zSeal/seal_env.cpp | MATCH | | not centre: level distances of both side points to the hit (y 0: the z-first sum is exact), neither < 3 -> false, edge dir sides[1] - sides[0] level normalised, only d0 < 3: sides[0] + 3 dir, only d1 < 3: sides[1] - 3 dir, true; both or centre: (sides[0] + sides[1]) x 0.5; third point unused |
| 98 | 0x2a2a80 | 492 | CZSealBody::GetTerrainMotionFactor | zSeal/seal_env.cpp | DEFECT-FIXED | C | NaN-only forms: water on !(depth <= 0) (0x2a2acc), w kept unless w < min (0x2a2af4), slope on !(d <= 0) (0x2a2be8), 1 on !(f <= 1) (0x2a2c38); the port had > 0 / min <= w / > 0 / > 1: fixed. Rest matches: airborne 1, 1 - depth x slope factor (+0x10c), min (+0x108), cycling top (0x40): node z axis (VU0 rows), (nx zx + ny zy) + nz zz, sqrtf(1 - d d), water x slope, < 0 -> 1 |
| 38 | 0x28da30 | 368 | CZSealBody::HandleKiller | zSeal/seal_env.cpp | MATCH | | same killer out, seal of the id, last killer stored, hostage bit 0x20000 read first, self or team overlap -> DeductKill, else Kill (no overlap), hostage: net game valve by side (0x100 terrorists +0x38, 1 SEALs +0x34), u16 value + 1 (32-bit compare: state 1), callbacks, killer m_hostages++ (+0x4dc); own Death |
| 69 | 0x298390 | 424 | CZSealBody::ChangeToRifleMode | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x2984b4: the pistol's slot test is lh id sltu size; the port compared (u16) with (u16) size: now (u32)(s32) (no reachable difference; the rifle and weapon tests were already so). Rest matches: ReParentToRifle, rifle to m_rhand (slot 0x1c / 0x18 of the node vtable at +0x60), slot = rifle, blendme 0; holster: pistol to m_rthigh, slot NULL, blendme 0, pistol as gear; weapon slot NULL; m_item 1 |
| 70 | 0x298540 | 408 | CZSealBody::ChangeToPistolMode | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x2985d8: the pistol slot test, as row 69: fixed. Rest matches: ReParentToPistol, draw and pistol node: to m_rhand, slot = pistol, blendme 0; rifle to m_spinelo, slot = rifle, blendme 0; weapon slot NULL; m_item 2 |
| 71 | 0x2986e0 | 208 | ParentPistolToRThighAsGearCallback | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x298764: the pistol slot test, as row 69: fixed. Rest matches: pistol node: out of its parent, to m_rthigh, AddChild, slot NULL, blendme 0; SetPartAsGear(m_pistol, m_pistol_as_gear) |
| 64 | 0x2950a0 | 432 | CZSealBody::DamageRLeg(ff) | zSeal/seal_env.cpp | DEFECT-FIXED | C | NaN-only form: level 2 is h <= 0x3f333333 max (c.le.s 0x295160); the port had !(0.7 max < h): fixed. Rest matches: damage == 0 false, spent leg (<= 0): flinch 4 + WeaponHitAnim(anim, GetStance(false), mirror) false, ResolveDamage(rleg, m_armor[4], damage, pierce), levels <= 0x3e99999a / 0.7 / 0x3f666666 of max, 3 / 2 -> m_limp (bit 2 of 0xf59), flinch 4, true |
| 65 | 0x2955e0 | 432 | CZSealBody::DamageLLeg(ff) | zSeal/seal_env.cpp | DEFECT-FIXED | C | row 64's stream (diffed) on lleg / m_armor[5] / location 5, with the same level-2 compare fix |
| 66 | 0x296420 | 460 | CZSealBody::DamageLArm(ff) | zSeal/seal_env.cpp | DEFECT-FIXED | C | as row 64 (level-2 compare fixed) on larm / m_armor[2] / location 2, retmods +10 for level 3, +3 for 2 and 1 |
| 67 | 0x296910 | 460 | CZSealBody::DamageRArm(ff) | zSeal/seal_env.cpp | DEFECT-FIXED | C | row 66's stream (diffed) on rarm / m_armor[1] / location 1, the same fix |
| 58 | 0x293910 | 680 | CZSealBody::InitDecalHandles | zSeal/seal_env.cpp | MATCH | | mission decals rdr (+0x59c), _calloc(4, material count, "seal_env.cpp", 8329), FOOTSTEP_DECALS: array count - 1 entries (Get bounded), MATERIALNAME / TEXTURENAME, ResolveMaterialIndex then GetTexHandle into the table (unbounded); BLOOD_DRIP_DECALS: reserve(count), TEXTURENAME tex (NULL skipped), MIN_SIZE / MAX_SIZE (zeroed first), {min, max, tex} appended |
| 59 | 0x293bc0 | 348 | CZSealBody::HandleWeaponEvent | zSeal/seal_env.cpp | MATCH | | static callback: entity list walk, seals (type 2) -> controller slot 0x44 OnWeaponEvent(projectile, event, data) unchecked |
| 86 | 0x29cf30 | 328 | CBlink::BlinkTick | zSeal/seal_env.cpp | MATCH | | done: next -= dT, < 0 -> 0; else frac += dT / deltaT, !(frac < 1) -> 1 and done, LookTick inline (0.5 x quadW(frac) on m_cross, Exp, quat0 Mul, Apply(unit_nz) into curr), done: org 1 -> 0, then (done, org 0) org -1 + SetDir(unit_nz, curr, 1.5), done cleared; else org 0 |
| 87 | 0x29d1f0 | 460 | CLook::SetDir | zSeal/seal_env.cpp | MATCH | | same goal (x, y, z ==) out, quat0 Align(unit_nz, curr), quat1 Align(unit_nz, goal), rate x 0x40c90fdb, rate == 0: frac 1 done; else frac 0, deltaT = acosf((gx cx + gy cy) + gz cz) / m_rate, goal, cross = curr x goal (sceVu0OuterProduct) |
| 88 | 0x29db50 | 464 | CZSealBody::SetEyeLookDir | zSeal/seal_env.cpp | DEFECT-FIXED | C | NaN-only forms: the ELF picks the second branch on pitch < 0 / yaw < 0 (0x29dbd8, 0x29dc28); the port had pitch >= 0 / yaw >= 0: fixed. Rest matches: both eyeballs, right or left node Rendered, X rot pitch x 0x3e0efa35 / 0xbe7a35de, Y rot yaw x 0xbe97e9d9 both ways (quirk), qx Mul qy, Apply(unit_nz), CalcGoalDir(curr, dir, goal, 0x3e0efa35, 0xbe7a35de, 0xbe97e9d9, 0x3e97e9d9), SetDir(goal, curr, 1.5 rate) |
| 97 | 0x2a2250 | 288 | CZSealBody::SealGetAltitude | zSeal/seal_env.cpp | MATCH | | node active bit kept (the ELF reads bit 0 of +0x5c; the port takes SetActive's old-state return, the same value), SetActive(false), world DI's character bit (bit 1 of +2) kept and set when m_QueryCharacterAltitude, GetAltitudes(pos, 10000), bit restored, SetActive(old), SealProcessAltitude(hits, pos, above) |
| 74 | 0x299170 | 492 | CZSealBody::CanUseBodyCarry | zSeal/seal_env.cpp | MATCH | | NULL / alive corpse, corpse state 9 / 10, corpse restrained (bit 0 of 0xf59), own m_am_stunned, corpse node inactive or opacity < 1, scope, own state 3 or top state 3, own 9 / 10, carrying, (x x + y y) + z z <= 300 |
| 50 | 0x291040 | 328 | CZSealBody::ReportWeaponHitDamage | zSeal/seal_env.cpp | MATCH | | network only, seal of the shooter id, seal: SendHitMessage(shooter, victim, (u8) location, damage, pierce, first, weapon), first: shooter Hit (seal) + own WasHit, (u8) location 0 and headhits <= 0: shooter HeadShot (seal), headhits++ |
| 40 | 0x28ea60 | 336 | CZSealBody::DropAllItems | zSeal/seal_env.cpp | DEFECT-FIXED | C | 0x28eb28 asks the controller's GetSealCtrlAi (slot 0x38) unchecked; the port's unrecorded NULL test removed. Rest matches: single player: AI navy SEAL (bit 1 of +0x280) out; network: non-player out, MPBOMB held -> RequestNewBombState(m_id, 1, posw), Satchel aux node SetActive(false); DropAmmo(-1), DropItem(i, false) for each item |
| 34 | 0x28c230 | 432 | CZSealBody::CreateMPBombPickup | zSeal/seal_env.cpp | MATCH | | pickups closed: delayed flag and point, 0; YXZ 0, GetWeapon(154) unused (quirk), "Satchel" instance, NULL 0, name MPFootBomb, world AddChild (slot 0x18), dynamic, character bit, textures 2, descendant DI / visuals, unless nopickup: Create(11, node, NULL), player (unchecked) BOMB_GROUND anchor type 1 (bits 4-19), CompassAnchor_MPBomb, DeleteAnchor(mpbase), MPBase(NULL); m_mpbombnode; the ELF returns the pickup, its callers test it with beqz |
| 51 | 0x291710 | 212 | CZSealBody::CheckForRegionTrigger | zSeal/seal_env.cpp | MATCH | | changed mask: bits 0-30 "OnEnterRegion%d" GetAnim / Activate(NULL), none set: "OnEnterRegion0"; last region stored always |
| 92 | 0x29fea0 | 220 | CZSealBody::Slide | zSeal/seal_env.cpp | MATCH | | conjugate m_quat Apply(hit norm), x -1, dot (nx vx + ny vy) + nz vz with m_velM, Scale(dot), m_velM -= n |
| 75 | 0x2993e0 | 532 | CZSealBody::CanZoom | zSeal/seal_env.cpp | MATCH | | alive, state 6 / 3 / 2 / 1 / 0 (9 and others false), top state 8, IsThrowing(false) inline (the ten throw / toss types), IsChangingWeapons, top type PistolStab / Stab, ApplyRestraints / PistolApplyRestraints, CQB / PistolCQB (Top re-read each time), overlay anim NULL |
| 99 | 0x2a3040 | 604 | CZSealBody::SealGetIntersect | zSeal/seal_env.cpp | MATCH | | node active kept, SetActive(false), GetIntersects(from, to), restored (as row 97), hits +0x34 count, 32-byte entries +0x44: material clamped to the list (0), ex and hit set, poly camera type (bits 2-3 of +0x1a) != 1, not volumetric / liquid (bits 0 / 1 of +0x38), penetration < 0x3f7d70a4 or pickup (bit 4), (x x + y y) + z z from from, first or < best |
| 77 | 0x29a050 | 640 | CZSealBody::GetReticuleWeapon | zSeal/seal_env.cpp | MATCH | | last reticule material clamped, ex NULL or not pickup (bit 4 of +0x38) NULL, d 0x461c3c00, GetClosest(hit pos, 20, 8, secondary ? &second : NULL), body distance (x x + y y) + z z, second and out: its distance replaces d (quirk), < 400 -> *out, network: bomb (11) closer -> it, !(d <= 400) -> NULL |
| 78 | 0x29a2d0 | 372 | CZSealBody::GetProximityWeapon | zSeal/seal_env.cpp | MATCH | | as row 77 from the body position, no material test and no bomb |
| 79 | 0x29a450 | 228 | CZSealBody::GetProximityMPBomb | zSeal/seal_env.cpp | MATCH | | network only, GetClosest(posw, 20, 11, NULL), (x x + y y) + z z < 400 -> bomb |
| 54 | 0x2920c0 | 260 | CZSealBody::HandleFootfallSound | zSeal/seal_env.cpp | DEFECT-FIXED | C | NaN-only forms: the step sound is taken on !(throttle <= 0.5) for either throttle (0x292150 / 0x292160); the port had 0.5 < t: fixed. Rest matches: m_onMaterial < count (signed) else out, clamp (unsigned), material NULL out, prone (u8 2) crawl +0x10, step +0x8, stealth +0xc, PlaySound3D (slot 0x14) (pos, 1, 0, NULL, 255) |
| 72 | 0x298930 | 224 | CZSealBody::IsReloading | zSeal/seal_env.cpp | MATCH | | Top twice (quirk), the seven reload types, overlay anim and its anim (+0x1a) MovingRifleReload / MovingPistolReload |
| 76 | 0x299900 | 228 | CZSealBody::FindDeathAnimTypeCQB | zSeal/seal_env.cpp | MATCH | | victim facing = -(row 2) with y 0, d = own translation - victim's with y 0, (dx fx + dy fy) + dz fz < 0 -> CQBVictimFallForwards else Backwards; no NULL tests (quirk) |
| 37 | 0x28d900 | 304 | CZSealBody::FillNetworkAmmoPickupValues | zSeal/seal_env.cpp | MATCH | | count = weapons size, per entry: !(size < i) reads weapon / ammo / count (quirk), rounds (u16), Pack(weapon id lb +0x60 or 255, ammo id lb +0x20 or 255) (Pack masks to bytes: the sign is harmless) |
| 36 | 0x28d0a0 | 396 | CZSealBody::CanPickupNetItem | zSeal/seal_env.cpp | DEVIATION-KEPT | | 0x28d1ec tests the entity, not the seal, so a non-seal asker would get HandlePickupAck on NULL; the port tests the seal (now recorded in the code). Rest matches: FindNetPickup((u16) netid), none: DebugPickups + empty ack, count times (quirk): type 9 CheckForAmmoPickups(count, data, items, &ack), 8: items[0] == (u8) weapon id -> bit 0; SendPickupAckMessage(count, netid, asker, ack), asker's HandlePickupAck(count, netid, &ack) |
| 90 | 0x29e6a0 | 288 | ComputeDeltaLookQuat | zSeal/seal_env.cpp | MATCH | | QFromRot both, conj(from) Mul(to) into dq, dq Apply(unit_nz), sceVu0OuterProduct((nz, 1), (r, 1)) into axis xyz |
| 44 | 0x290180 | 324 | CZSealBody::FindHighestProximityDamage | zSeal/seal_env.cpp | MATCH | | "player" node name -> 0, copy of m_body_parts, parts with node and id >= 0 (lh): PartInSpace(part, zero, local, rot), m_quat Apply, + posw, GetDamage(world, 0), !(d <= best) keeps |
| 55 | 0x293430 | 244 | AnimSet::InitDeathAndFlinchAnimations | zSeal/seal_env.cpp | MATCH | | 6 x 3: reserve(8) on deathanim, pistoldeathanim, teammatedeathanim, teammatepistoldeathanim, damageanim, pistoldamageanim in that order |
| 56 | 0x293530 | 424 | AnimSet::ReadDeathAndFlinchAnims | zSeal/seal_env.cpp | MATCH | | zrdr_read("damanim.rdr", "data/common", 0), the six death, six teammate death and six flinch tags with locations 0-5 in the ELF's order, zrdr_free |
| 57 | 0x2936e0 | 536 | CZSealBody::ReInitDatabaseHandles | zSeal/seal_env.cpp | MATCH | | InitHandSignals, AddWeaponEventCallback(HandleWeaponEvent, 1, NULL), the six ripple anims and drop_item, _calloc(4, material count, "seal_env.cpp", 8419), per material (clamped): NULL then "seal_footfall_%s" of +0 name, SND_RIFLE_BUTT, SND_BONE_BREAK_CRUNCH_01, Close / OpenHeartbeatSounds; the ELF reads the count after the callback registration (no difference) |
