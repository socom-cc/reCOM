# boot-pickups notes (2026-11-12, socom-port-pickups)

Scratch for weapon/ammo pickups, ladders and the close-quarters action-button actions. Untracked.
Changed files: `mine.txt` (whole files laid over HEAD by tree.sh: copy.txt). Shared-file edits in
`edits/` (srep.py format, listed in `shared.txt`, applied to HEAD copies in my test tree only).

## State / next step
- (a) pickups WORK (p2.log, p2-66.png "TAKE 552", p2-76.png HUD "552 30/30"): OutPatrol4 (hook: 25
  ahead, facing away) shot -> drops ammo box (5.56x45mm 30, frag 6) + 552; player teleported by the
  hook; "TAKE 552" offered; CROSS -> M4A1 SD + its ammo box dropped, 552 into slot 0; enemy box
  walked over -> 30 rounds into the 552; swaps back and forth with later CROSS presses. No STOP.
- Since p2: grenade pickups in CZKit::Fire (sk01), trace spam cut (PickupAmmo traces only gains).
- (b) ladders: m8 has NO ladder: DI app-flag census (k1.log) 0:10758, 1:0, 2:0 (ladder), 3:0, 4:202,
  5:130. Not testable in m8.
- (c) knife WORKS (f3.log): TickVictims scan, CanUseKnife/Restraint/CQB/BodyCarry (edits/se02_cqb.txt),
  StabBuddy, DetachBody, RestrainBuddy, RestoreCameraPosition (seal_body.cpp, mine), Execute knife /
  restraint (sl01). "CQB: player stabs OutPatrol3" -> "OutPatrol3 detached ... state 8". CQB (12) and
  body carry (8) are NOT offered (port gate in PerformProximityActions: callees unwritten).
- f3 (hook, pad_f1): knife, shot enemy, TAKE 552, swap both ways, 60 rounds from two boxes, mission to
  171 s (frame 7056) no STOP. Final run fin (pk4, pad_f2) recorded the clip; default build pkd.
- DONE. Clip build/port/recordings/2026-11-12_pickups-knife.mp4 (22.5 s, opens on TAKE 552). Default build
  (default.sh pkd, dflt.log) reaches the main menu (MENU frames, attract screen at 44 s), no fake pad.
- Build: `pb.sh <build> <pad> "<-D...>"` (tree.sh + fake.sh + hook.sh with hook_pickups.cpp),
  `go.ps1 -Build <b> -Name <run> -Seconds n -Shots ...`, `default.sh <build>`. Final pad pad_f2.txt with
  `-DSOCOM_HOOK_ENEMY=25.0f -DSOCOM_HOOK_KNIFE=12.0f` (knife victim 12 ahead facing away; shooting target
  re-placed 25 ahead 180 frames after the stab; 90 frames after its death the player is put 10 from its
  weapon; after the take the hook moves him away from / back to the box).
- zmath.h: my CBits hunk is in the repo; another worker added a DistToVector hunk afterwards, so my
  test tree takes only mine (edits/zm01_zmath.txt).

## Ownership at start (HEAD ff2c53b)
- Modified by others (edit files only): pickup_main.cpp (missionexit: Close), seal_env.cpp,
  seal.cpp, seal_kit.cpp (missionexit: UnInit), zseal.h, zweapon.h, ztwod_messageq.cpp, seal_ai*.
- Free: seal_control.cpp, seal_body.cpp, seal_squirm.cpp, seal_weapon.cpp, zWeapon/*.cpp,
  fts_action.cpp, hud_actionbitmap.cpp, zentity.h.

## ELF chains (survey)
### (a) Pickups
- Drop on death: UpdateHealth -> DropAllItems (W) -> DropAmmo(-1) 0x28e7b0 (688) + DropItem(i, false)
  0x28e3e0 (976, returns CPickup*). DropAmmo: CZAmmoPickupInstance (36 B: 3 vector_pod: weapons,
  ammo, counts) filled by CZKit::FillAmmoPickupInstance 0x2a5bb0 (guns keep the item, lose the ammo;
  other items move into the box), "fiftycal_box" model at the body, PU_TYPE 9. DropItem: the item in
  the hand part (m_weapons[weapon->m_type]: 1 rifle, 2 pistol), its node detached into the world,
  dynamic, PU_TYPE 8, data = the weapon, m_secondary = pistol; m_dropanim ("drop_item") unless arg.
- CPickup (DWARF 28 B): m_node, m_data, +8 m_type:7 m_locked:1 m_secondary:1 m_unused:7 m_id:16,
  +0xc m_netid, +0x10 CBits m_bits, +0x18 m_visible_by_units. Static list m_list / pool m_pool.
  Create 0x24cfe0 (static, returns the pickup), Destroy 0x24ccb0, GetFirst/GetNext x2/GetClosest/
  FindPickup/GetMPBomb/CleanupAmmoPickup/Close/Open, GetPosW (node+0x30).
- Offer: CSealCtrl::TickPickups 0x2852e0 (PreTick): ammo boxes (type 9) within 20 are taken at once
  (PickupObject, lastpickup static stops repeats); weapons (type 8): GetReticuleWeapon 0x29a050
  (reticule hit on a PICKUP material, closest weapon within 20 of the hit) else GetProximityWeapon
  0x29a2d0 (within 20 of the body); not offered while m_weapon_pickup_timer > 0 or when the kit
  has that item id -> m_curpickup_ID / secondary. Network MP bomb part not needed.
- HUD: PerformProximityActions mask 4/5 (W) -> CActionTxtrMachine::UpdateDriverPickup 0x3d7f40
  (CurrentPickup / Secondary 0x24e110 / 0x24e0e0 -> node + weapon name) -> "<TAKE> <name>".
- Take: OnActionButton (W) -> PickupObject 0x24f330 (alive; type 8 HandlePickupEquip 0x28e2f0 ->
  PickupItem 0x28df50; 9 HandlePickupAmmoInstance -> CZKit::PickupAmmo(CPickup*) 0x2a6530 ->
  PickupAmmo(w, a, int*) 0x2a6300 -> AddAmmo 0x2a5eb0; 1 grenade throwback (AI); 11 MP bomb).
  PickupItem: rifle -> DropAmmo(0)+DropItem(0, true) (swap slot 0), pistol -> slot 1; the pickup's
  node goes onto rhand / hips / spinelo by held item, "Swap rifle" anim, SetItemByIndex, kit
  m_requested_item, ctrl m_HudUpdateWeapon, Destroy. The new gun has no ammo until an ammo box.
- Unwritten callees in play: CBits::Resize (stub, ok: Create only memsets a non-NULL buffer),
  C2DMessage_Q::LastMessage / Add_Message (ammo name message in PickupAmmo), Action (seal_body,
  S: the swap anim).
### (b) Ladders
- CanClimbLadder = CanTraverse(2) (W). ImpactFront -> ClimbLadder (W); InStateClimbLadder 0x278f20
  (460, S nonvoid, seal_body.cpp), CheckDILadder 0x29ff80 / PostCheckDILadder / PreClimbLadderDown
  (seal_env.cpp, S), SlideLadderDown 0x274450 (S nonvoid). AI: LadderClimbTick, CreateLadderTable.
### (c) CQB (OnActionButton bits: 0x400 knife, 0x800 restraint, 0x1000 CQB, 0x100 carry, 0x200 drop)
- TickVictims 0x285650 (380; target scan missing) -> m_victimbody / m_corpsebody.
- Knife: CanUseKnife 0x299d10 (832) + ExecuteAction_KnifeAttack 0x24ee90 -> StabBuddy 0x26ef00 (480);
  callees written. Restraint: CanUseRestraint 0x299600 (756) + RestrainBuddy 0x26eb70 (908; AI state
  push written). CQB: CanUseCQB 0x2999f0 (800) + ExecuteAction_CQBAttack 0x24ed60 (292; CAiEvent
  unwritten). Body carry: CanUseBodyCarry 0x299170 (492) + CrouchToPickupBuddy 0x26f750 (1628) +
  PickupBuddy 0x26f530 + PutdownBuddy 0x26f350 + callbacks (largest).

## Written (ELF addresses)
- zentity.h: CPickup DWARF layout (28 B: m_node, m_data, type:7 / locked / secondary / id:16, m_netid,
  CBits, m_visible_by_units), public; PU_TYPE values (names invented); Create / GetFirst / GetNext /
  GetClosest / NetworkCreate static with returns; m_list / m_pool std::list. zmath.h: CBits members.
- pickup_main.cpp (edit pm01): Open 0x24d630, Close 0x24d4a0, Create 0x24cfe0, Destroy 0x24ccb0, GetFirst
  0x24cbe0, GetNext x2 0x24cb40 / 0x24ca00, GetClosest 0x24c840, FindPickup 0x24c7a0, CleanupAmmoPickup
  0x24c4c0, GetMPBomb 0x24c420, GetPosW 0x24c400; NetworkCreate returns NULL (network, not written).
- zseal.h (edit zh01): CZAmmoPickupInstance (36 B, 3 vectors; no DWARF, names invented); DropItem returns
  CPickup*.
- seal_env.cpp (se01): DropAmmo 0x28e7b0, DropItem 0x28e3e0, GetProximityWeapon 0x29a2d0,
  GetReticuleWeapon 0x29a050, HandlePickupEquip 0x28e2f0, HandlePickupAmmoInstance 0x28e3b0, PickupItem
  0x28df50. (se02): RESTRAINT/KNIFE/CQB_DOT = cos 85/25/65 deg (__sinit_seal_env 0x46cee0), CanUseKnife
  0x299d10, CanUseCQB 0x2999f0, CanUseRestraint 0x299600, CanUseBodyCarry 0x299170 (+ two file-local
  facing helpers: port factoring of inline code).
- seal.cpp (sl01): PickupObject 0x24f330 (types 8/9/11; type 1 AI throwback not written), CurrentPickup
  0x24e110, CurrentPickupSecondary 0x24e0e0, ExecuteAction_KnifeAttack 0x24ee90, ExecuteAction_ApplyRestraint
  0x24ed10.
- seal_kit.cpp (sk01): GetItemIndex(EQUIP_ITEM) 0x2af520, FillWeaponEnum 0x2a6e40, PickupAmmo(CPickup*)
  0x2a6530, PickupAmmo(w, a, int*) 0x2a6300, AddAmmo 0x2a5eb0, FillAmmoPickupInstance 0x2a5bb0; Fire's
  grenade pickups (types 1/2/3, 0x2ad750).
- seal_control.cpp (mine): TickPickups 0x2852e0 (network MP-bomb part not written), TickVictims 0x285650
  target scan, OnActionButton echo test; CQB / body carry not offered (port gate).
- seal_body.cpp (mine): DetachBody 0x26f0f0, RestoreCameraPosition 0x26f0e0 (empty in the ELF),
  StabBuddy 0x26ef00, RestrainBuddy 0x26eb70.
- hud_actionbitmap.cpp (mine): UpdateDriverPickup 0x3d7f40.

## ELF quirks kept
- Ammo boxes never disappear in single player (only the network ack cleans them up); with two boxes in
  range both are re-taken every frame (lastpickup remembers one); a swap drops a new box with the old
  gun's ammo; the picked gun arrives empty until a box is walked over.
- PickupItem: the swap anim id is the *dropped* pickup's id * 2; Get*Weapon: the secondary's distance
  replaces the primary's before the range test; distances are to the body, not the reticule hit.
- Close calls GetMPBomb after emptying the list. FillWeaponEnum / AddAmmo index without guards (guarded).

## Port deviations
- Guards: Create on a failed new, GetNext/GetClosest NULL node, AddAmmo NULL item, victim controllers
  in CanUse*, DetachBody's carrier, DropItem missing model, PickupAmmo box.
- PickupAmmo: no ammo-name HUD message (C2DMessage_Q::LastMessage / Add_Message unwritten).
- RestrainBuddy: the restrainer's team at CAiSRestrained +0x28 not stored (no member in zai.h).
- PerformProximityActions does not offer CQB (12) or body carry (8) (see below).

## Not written / next
- Dropped items float where the hand was: the "drop_item" anim needs zAnimObjectMotionBegin 0x1bc540
  (3108 B) / Tick 0x1bb330 (4452 B), both unwritten (zanim_cmd_tick.cpp). A weapon dropped high may be
  out of the 20 (3D) pickup range.
- CQB attack: ExecuteAction_CQBAttack 0x24ed60 needs CZAnim::ActivateEx 0x1ceee0 (468 B; args are
  command pointers, 0-terminated) for "ai_cqb_attack" + CAiEvent Acquire/Create (zAI); then lift the gate.
- Body carry: CrouchToPickupBuddy 0x26f750 (1628), PickupBuddy 0x26f530 (532), PutdownBuddy 0x26f350
  (476), CrouchToPickupBuddyCallback 0x26fdb0, PickupBuddyCallback 0x26fe40, Crouch_0 0x2762d0 (600),
  CanCrouch 0x27a1b0, AlignForPickup 0x2a0210 (312); then lift the gate.
- Restraint untested: no m8 enemy is restrainable (team bit 0x10000000 none; CAiSSurrender unwritten)
  and CanPushAiState's port gate refuses STATE_RESTRAINED (aimove's file).
- Ladders: none in m8 (no flag-2 DI). Untested: InStateClimbLadder 0x278f20, CheckDILadder 0x29ff80,
  PostCheckDILadder, PreClimbLadderDown 0x2a0350, SlideLadderDown 0x274450 are unwritten.
- Network pickups (NetworkCreate, RemotePickupItem, HandlePickupAck...), MP bomb pickups, CBits::Resize,
  DebugPickups, Set/GetVisibleByUnit (AI pickups), CAiSPickup.