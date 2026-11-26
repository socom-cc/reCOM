# Stage 2: gamez/zSeal, list a (2026-11-26)

List a of `gamez/zSeal` split 6 ways (owner files seal_env.cpp, seal_control.cpp, seal_kit.cpp,
seal_unit.cpp). It holds 50 uncertain rows (32 new, 10 removed, 5 weak deviating pairs
`slot-only`, 3 unsure), 15 sampled deviating rows of 279, and 130 exact rows that were not
checked. Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`, the
function map at HEAD 8185d1bb). Checked by `socom-release-check-seal-a`, who did not write the
tool, on that commit. Ghidra was not used: both loaded images were listed with calls named
through the map and `$gp` operands resolved, callers were found by scanning both images for
`jal`/`j`, and virtual functions were placed through their vtables (prototype `__vt__` symbols;
the release table is the one whose entries match the mapped slots).

What settled rows, in the order it was used: vtable slots (7 rows; none of these functions has a
direct caller); the call site in a paired caller; the slot between paired neighbours; operation
similarity against every unpaired function of the other side; strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x28faa0 | - | new | confirmed | see New |
| - | 0x2844a0 `GetThrowAverage__9CSealCtrlFv` | removed | confirmed | PreTick no longer averages the throw ring buffer: it smooths the pressure inline with three local statics; the buffer is still cleared (+252, index +296) |
| 0x2936a0 | 0x287bd0 `PlayAiSound__9CSealCtrlF15CHARACTER_SOUND` | deviating, slot-only | confirmed | CSealCtrl vtable slot 0x24; same two calls; the position vcall is inlined (body +28) |
| - | 0x288050 `Initalize__9CSealCtrlFv` | removed | corrected to 0x293ac0 | CSealCtrl vtable slot 0x40; same constant store (+304 → +308) and `SetSnakePathUpdate(body, 1, 75)`; the CAiVisMap creation is gone |
| 0x293ac0 | - | new | corrected to 0x288050 `Initalize` | see above |
| 0x293ae0 | - | new | corrected to 0x288120 `OnMissionEnd__9CSealCtrlFv` | vtable slot 0x60 (also in the CSealCtrlCopy and CSealCtrlSquirm tables); was empty, now `ClearGoal(0)` and clears bit 3 of +369 |
| 0x293b30 | - | new | corrected to 0x288130 `OnMissionStart__9CSealCtrlFv` | vtable slot 0x5c; was empty, now clears goal 0, notifies unit 24 in network games, sets body +772 and bit 3 of +369 |
| - | 0x288130 `OnMissionStart__9CSealCtrlFv` | removed | corrected to 0x293b30 | see above |
| - | 0x288140 `OnRecycleEntity__9CSealCtrlFP7CEntity` | removed | corrected to 0x293bd0 | vtable slot 0x48 holds 0x293bd0, still empty (`jr ra; nop`); the map gives 0x293bd0 to OnMissionEnd as an exact row, which is wrong |
| 0x298220 | - | new | confirmed | see New |
| - | 0x28cd70 `__vc__…vector_imp<i,…>` | removed | confirmed | its only caller HandlePickupAck no longer uses the three parallel vectors (now calls new 0x337060 / 0x336f40); every release function with its bytes is paired elsewhere |
| - | 0x28cd80 `__vc__…vector_imp<P6CZAmmo,…>` | removed | confirmed | the same |
| - | 0x28cd90 `__vc__…vector_imp<P11CZFTSWeapon,…>` | removed | confirmed | the same |
| - | 0x28cda0 `size__…vector<P11CZFTSWeapon,…>` | removed | confirmed | the same |
| 0x29b3c0 | 0x28f840 `HandleGrenadeExplosion__10CZSealBodyFv` | deviating, slot-only | confirmed | the same reference list in order and the unique string `SND_RINGING_EARS`; caller is 0x25a8d0, which took the second half of the prototype PostTick (see Outside) |
| 0x29cba0 | 0x290fb0 `GetMPStats__10CZSealBodyFP11MPSealStatsb` | deviating, slot-only | confirmed | same caller UpdateLocalSeal; same `bool` choice of the stats block (+1132/+1216 → +1148/+1232); the copy moved into new 0x2532f0, tail-called |
| 0x29db40 | - | new | confirmed | CZSealBody vtable slot 0x38, a new virtual (see New) |
| 0x29dc10 | - | new | confirmed | CZSealBody vtable slot 0x34, a new virtual (see New) |
| 0x29dce0 | 0x2918d0 `GetTargetPosW__10CZSealBodyFP6CPnt3D` | unsure, ambiguous | confirmed, deviating | vtable slot right after UpdateNextPosition in both; the same part +660 (`m_spinehi`); the two look-alikes read +652/+656 and sit in the two new slots |
| 0x29ddb0 | - | new | confirmed | see New |
| 0x29e090 | 0x291b60 `HandleSealStep__10CZSealBodyFv` | deviating, slot-only | confirmed | same per-foot sequence (GetSpeedState, PartInSpace, Apply, Add, ActivateArg, HandleFootfallSound) twice; the decal code is now 0x29ddb0; same caller as HandleGrenadeExplosion |
| 0x2a3230 | - | new | confirmed | see New |
| 0x2a5000 | - | new | confirmed | see New |
| 0x2a5800 | - | new | confirmed | see New |
| - | 0x29b650 `DrawAutoReticle__FP6CPnt3D` | removed | still unsure | not in zSeal any more; candidate 0x3f0130 in hud (see Still unsure) |
| 0x2a8700 | - | new | confirmed | see New; not DrawAutoReticle (other calls, other caller) |
| 0x2a97a0 | - | new | confirmed | see New |
| 0x2abe70 | - | new | confirmed | see New |
| 0x2ad0e0 | - | new | confirmed | see New |
| 0x2ad2a0 | - | new | confirmed | see New |
| 0x2ad2d0 | - | new | confirmed | see New |
| 0x2ae7a0 | - | new | confirmed | a second homing routine beside HomingTick (see New) |
| 0x2aed50 | 0x2a0f20 `HomingTick__10CZSealBodyFv` | unsure, ambiguous | confirmed, deviating | the same call site in Tick_0 (last call before Animate, when +80 of the homing record is set); operations 0.873 (0x2ae7a0: 0.735); gained a second argument (0 here) |
| 0x2afad0 | - | new | confirmed | see New |
| 0x2b1750 | - | new | confirmed | see New |
| 0x2b1a30 | - | new | confirmed | see New |
| 0x2b1d10 | - | new | confirmed | see New |
| 0x2b3b30 | 0x2a4ff0 `Binocs_Enabled__5CZKitFb` | deviating, slot-only | confirmed | same bit 5 of byte 0; same callers (~CZSealBody, HandleNewZoom, and the release OnDeath); now calls TriggerPowerReset when binoculars go off |
| 0x2b6670 | - | new | confirmed | see New |
| 0x2b7500 | - | new | confirmed | see New |
| 0x2b7f40 | - | new | confirmed | see New |
| 0x2b89a0 | 0x2acc70 `ChangeItemModel__5CZKitFiiib` | unsure, low-similarity | corrected to new + removed | it is PreTick's first-tick block (under bit 0 of byte 0) made a function: ChangeItemModel's `first` branch inlined, then CycleFireMode, the fire-mode restore, clearing bit 0; it reads no arguments. Same place in PreTick, but the prototype name and signature do not carry over |
| - | 0x2acc70 `ChangeItemModel__5CZKitFiiib` | (unsure above) | removed | inlined into 0x2b89a0, its only caller's block; no release function resembles it (best 0.47) |
| 0x2ba780 | - | new | confirmed | see New |
| 0x2bf820 | - | new, copy | confirmed | see New |
| - | 0x2cf180 `GetAwareCounter__9CSealUnitCFv` | removed | confirmed | no release function resembles it (best 0.44); its only caller CHUD::StatusLine is itself unpaired, so where the work went is for the hud check |
| 0x2e5150 | - | new | confirmed | see New |
| 0x2e6620 | - | new | confirmed | see New |
| 0x2e6880 | - | new | confirmed | see New |
| 0x2e6b70 | - | new | confirmed | see New |
| 0x2ea6e0 | - | new | confirmed | see New |

Sampled deviating rows (same function on both sides?):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x2938f0 | `OnStunDamage__9CSealCtrl…` | yes | CSealCtrl vtable slot 0x50; FLASHBANG_DOT; same calls less SetGroupVolTemp |
| 0x298900 | `CheckForAmmoPickups__10CZSealBody…` | yes | only caller CanPickupNetItem at the same place |
| 0x2990c0 | `CreateNetWeaponPickup__10CZSealBody…` | yes | only caller WeaponPUPacketHandler; CPickup::Create, ActivateArg tail |
| 0x299250 | `FillNetworkAmmoPickupValues__10CZSealBody…` | yes | only caller DropAmmo; PackItemAndAmmoEnums |
| 0x29af50 | `SetupKevlarInsertArmor__10CZSealBodyFv` | yes | imm-only; caller PostSetupItems |
| 0x2a03b0 | `HandleStunDamage__10CZSealBody…` | yes | imm-only; the same three callers |
| 0x2a0620 | `HudUpdateViewCone__10CZSealBodyFv` | yes | imm-only; caller CZNewHudMap::HudTick |
| 0x2a0fe0 | `DamageBody__10CZSealBodyFff` | yes | imm-only; the same three callers and four callees |
| 0x2a1190 | `DamageBody__10CZSealBodyFP12CZProjectile` | yes | the same 22 references in order (+ OnDeath); same two callers |
| 0x2a8200 | `GetCharacterHit__FP10CZSealBody…` | yes | only caller CheckDIShoot; IsUsingScope, CopyMatrix, _TransformPoint, GetZ ×2 |
| 0x2b3ae0 | `IncrScreenOffsetY__5CZKitFf` | yes | imm-only (+72 → +84); caller ThrottlesPreTick; no X sibling exists |
| 0x2b40e0 | `IsUsingItem__5CZKitFi` | yes | imm-only; caller IsUsingItem(EQUIP_ITEM) |
| 0x2b4660 | `RemoveAmmo__5CZKitFi` | yes | imm-only; caller CreateNetAmmoPickup |
| 0x2b4d20 | `CanAddAmmo__5CZKitFii` | yes | imm-only; callers PickupAmmo, find_closest_ammo |
| 0x2b7100 | `GetFiremodeGraphic__5CZKitFi` | yes | only caller CHUD::SetupFiremode; IsGrenadeLauncherAmmo |

## Settled pairs (tool input)

Rows whose class or counterpart differs from the map, or that the map left unsure. The rows are
in the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x293ac0 | 0x288050 | CSealCtrl vtable slot 0x40 (release table 0x489ce0, the other 35 mapped slots agree); same +308 store and SetSnakePathUpdate(body,1,75) | socom-release-check-seal-a | 2026-11-26 |
| 0x293ae0 | 0x288120 | CSealCtrl vtable slot 0x60, also in the CSealCtrlCopy and CSealCtrlSquirm tables | socom-release-check-seal-a | 2026-11-26 |
| 0x293b30 | 0x288130 | CSealCtrl vtable slot 0x5c, also in the CSealCtrlCopy and CSealCtrlSquirm tables | socom-release-check-seal-a | 2026-11-26 |
| 0x293bd0 | 0x288140 | CSealCtrl vtable slot 0x48, also in the CSealCtrlCopy and CSealCtrlSquirm tables; empty body (was paired exact with OnMissionEnd) | socom-release-check-seal-a | 2026-11-26 |
| 0x29dce0 | 0x2918d0 | CZSealBody vtable slot after UpdateNextPosition (release table 0x4899f0); same body part +660 | socom-release-check-seal-a | 2026-11-26 |
| 0x2aed50 | 0x2a0f20 | call site in Tick_0: last call before Animate; operations 0.873 | socom-release-check-seal-a | 2026-11-26 |
| 0x2b89a0 | new | PreTick's first-tick block made a function (ChangeItemModel's first branch inlined, CycleFireMode, fire-mode restore); takes no arguments | socom-release-check-seal-a | 2026-11-26 |
| removed | 0x2acc70 | inlined into 0x2b89a0; only caller PreTick; no release look-alike | socom-release-check-seal-a | 2026-11-26 |

The four vtable pairs and the two unsure rows are deviating (0x293bd0 is equal in bytes). The
other rows of the list stand as the map has them. DrawAutoReticle stays removed until the hud
check decides 0x3f0130 (Still unsure).

## New and removed

New in the list (29 confirmed, plus 0x2b89a0 from the split). Names are guesses unless the basis
says otherwise.

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x28faa0 | takes the controller's pad (index +232, pad table at `$gp`−32144), flushes it and sets PAD_TRIANGLE/CIRCLE/SQUARE/CROSS to state 0; called by CCinematicState::UnInit and CZHudMissionCams::CleanupCamera | `CSealCtrl::ClearPadButtons()`, a guess from the body |
| 0x298220 | deletes the MP bomb pickup node (new 0x250b80), then the player's compass anchor (+3544) and `CompassAnchor_MPBomb(NULL)`; called by CZBombState::RemoteBombDeletionCallback | `CZSealBody::DeleteMPBombPickup()`, a guess (slot between CreateMPBombPickup and DropMPBomb) |
| 0x29db40 | world position of body part +656 (`m_neck`), like GetTargetPosW; CZSealBody vtable slot 0x38 | `CZSealBody::GetNeckPosW(CPnt3D*)`, a guess; CEntity's own version is 0x1efcd0 |
| 0x29dc10 | the same for part +652 (`m_head`); vtable slot 0x34 | `CZSealBody::GetHeadPosW(CPnt3D*)`, a guess; CEntity's version 0x1efcf0 |
| 0x29ddb0 | applies a footprint decal at the last altitude hit (+864), texture from the per-material table at 0x48de04, size 3.5; called by HandleSealStep for each foot | `CZSealBody::ApplyFootDecal(CPnt3D*)`, a guess; the prototype HandleSealStep had this inline twice |
| 0x2a3230 | when the current anim is Rifle2Pistol/CrouchRifle2Pistol/ProneRifle2Pistol, switches back to rifle mode, re-poses, restores gear parts and the aim/fire points (`aimpoint`, `firepoint`), returns the active anim; called by FlingBody and WeaponHitAnim | `CZSealBody::AbortWeaponChange()`, a guess |
| 0x2a5000 | true if the current anim is one of six (ClimbCrate, Stand2Hang, Stand2Ladder and three `$gp` anim ids); called by CZKit::Reload | `CZSealBody::IsClimbing()`, a guess |
| 0x2a5800 | false unless bit 3 of +221, state +285 ≠ 6, not jumping or landing, speed² ≤ 49; then CanFire(); called by CSealCtrl::TickPickups | `CZSealBody::CanUsePickup()`, a guess |
| 0x2a8700 | casts two segments with the seal's node ignored (two static DiIntersects at 0x521210/0x521270, one GetIntersectBatch) and keeps the nearest hit whose material flag +56 is 1; called by new 0x255da0 | `CZSealBody::GetNearestHit2(...)`, a guess |
| 0x2a97a0 | true unless the node is a seal without bit 3 of +221; called by CZMarkList::AddNewMark | `CanMarkNode(zdb::CNode*)`, a guess |
| 0x2abe70 | falling step: integrates the vertical speed (+3780/+4064/+3784), lands on the altitude hit plus the material's height offset; called by PostCheckDIDown (which shrank 4768 → 3968 bytes) | `CZSealBody::ApplyFall(...)`, a guess; split out of PostCheckDIDown |
| 0x2ad0e0 | reads this seal's queued altitude result (SealProcessAltitude, material); called by PostTick after 0x2ad2a0 | `CZSealBody::ProcessQueuedAltitude()`, a guess |
| 0x2ad2a0 | runs the queued intersect batch (`GetIntersectBatch(world, list 0x48de14, count 0x48de1c)`) and clears the count; called at the start of PostTick | `CZSealBody::FlushAltitudeBatch()`, a guess |
| 0x2ad2d0 | when bit 7 of +220 is set, builds a downward segment at the seal and queues it, growing the batch (`_realloc`, seal_env.cpp:2880; new DiIntersect); called by 0x25a8d0 | `CZSealBody::QueueAltitudeCheck()`, a guess |
| 0x2ae7a0 | homing variant used when bit 0x40 of the homing record's +44 is set: computes the correction into an out vector (clamped to ±30) and returns the remaining distance; Tick_0 drops the record when it exceeds 28 | `CZSealBody::HomingStep(CPnt3D*)`, a guess; shares most of HomingTick's calls |
| 0x2afad0 | large predicate on an action kind (u8): flags +221, state +285, anim tests, reload, M203 mode; called by OKToPeek, ChangeWeapon, Reload, CanChangeItem, CanUseRestraint, CanUseCQB, CanUseKnife, CanTraverse, CZKit::Reload | `CZSealBody::CanDoAction(u8)`, a guess from the callers |
| 0x2b1750 | destroys every DiIntersect of the batch and frees it (seal_env.cpp:475); called by CCoreState::UnInit, CMission::ReOpen_Unload1, CMPExitState::Init | `CZSealBody::FreeAltitudeBatch()`, a guess |
| 0x2b1a30 | recursive node walk: multiplies the matrix stack, transforms the node's box corners (+64) and accumulates them; recurses into the children (+104) | `AccumulateWorldBounds(zdb::CNode*, ...)`, a guess |
| 0x2b1d10 | pushes identity on the matrix stack (0x48c930/0x48c92c), calls 0x2b1a30, pops; called by zdb::CRenderMap::Update | `GetWorldBounds(zdb::CNode*, ...)`, a guess |
| 0x2b6670 | true if the item after the current one is a grenade launcher whose count (+1780) is ≥ 4; called by CZSealBody::Reload | `CZKit::GrenadeLauncherFull()`, a guess |
| 0x2b7500 | `GetReticuleByIndex(m_curReticule)` (+2068); called by CheckDIShoot | `CZKit::GetCurReticule()`, a guess (slot before SetCurReticule) |
| 0x2b7f40 | iterative aim solve with local statics (98.0, 0.85, 12 steps, tolerance 0.025 via `_close_enough<float>`); called by HandleFireWeapon before firing | `CZKit::SolveLobAim(...)`, a guess |
| 0x2b89a0 | PreTick's first-tick setup (see Checked rows) | `CZKit::FirstTickSetup()`, a guess |
| 0x2ba780 | ground point under a body part (PartInSpace, GetAltitudes, material); called by TickExplosives | `CZKit::GetPlacementPos(...)`, a guess |
| 0x2bf820 | returns the float 16.0 at 0x48cb10 (bytes equal another getter, hence `copy`); called by CAiSDeploy::Tick and CSealCtrlAi::OnCommand | a static getter, name unknown (guess `GetDeployRange()`) |
| 0x2e5150 | picks a unit member through the leader and tail lists (GetSealCtrlAi on each) and has it play the sound passed (CSealCtrlAi vtable +0x24); called by IssueCommand, OrdersMenu::HandleRecoCmd and new 0x26c600 | `CSealUnit::PlayUnitResponse(CHARACTER_SOUND)`, a guess |
| 0x2e6620 | fills a command record and its position from an AiMaps action (cell centre plus direction vector); called by IssueCommand | `SetupActionCommand(...)`, a guess |
| 0x2e6880 | checks whether a deploy (EQUIP_ITEM 123 or 121, CanDeploy) fits the AiMaps action cell; called by CSealCtrlAi::AllowCommand | `CanDeployAtAction(...)`, a guess |
| 0x2e6b70 | node-action check (type ≥ 2, flag +32, distance ≥ 0.5, player or AI), then the AiMaps action's direction; called by CSealCtrl::OnActionButton and new 0x266be0 | `CanUseNodeAction(...)`, a guess |
| 0x2ea6e0 | when the `escortee_extract` anim is available, finds the unit of type 17 in `CSealUnit::m_list` and checks its members' AI state and map distance; called by HandleSupport and AllowCommand, which both shrank | `CSealUnit::CanExtractEscortee(CZSealBody*)`, a guess (string) |

Not new, though the map has them as new: 0x293ac0 Initalize, 0x293ae0 OnMissionEnd and 0x293b30
OnMissionStart. Their prototype names carry over.

Removed, confirmed: GetThrowAverage (replaced by inline smoothing in PreTick), the four vector
helpers of HandlePickupAck (its three parallel vectors are gone), GetAwareCounter (caller
unpaired), ChangeItemModel (inlined into 0x2b89a0). DrawAutoReticle: see below.

## Still unsure

- DrawAutoReticle (0x29b650) against hud 0x3f0130 (912 bytes, new, owner-guess
  hud_bitmapreticule.cpp): the same projection (sceVu0CopyMatrix of a camera matrix, constants 1.0
  and 224.0) and Draw2DLine lines, operations 0.642, nothing else above 0.30. But it draws six
  lines instead of four, takes the seal (reads the kit +1328), starts with `CHUD::IsOn`, and is
  called by BitmapReticule::HudTick instead of CheckDIShoot. A rewritten successor in the HUD,
  probably; whether it is the same function (and whether the old name carries over) is for the hud
  check. Until then DrawAutoReticle is removed from zSeal.
- The names of every new function (all guesses above).

Outside the list, found while settling it (not settled here):

- The CEntity vtable (release 0x489450) has a new slot between PrePostTick and PostTick and two new
  slots after GetTargetPosW. The empty CEntity virtuals are therefore paired one place off:
  by slot, 0x1f3940 is PreTick, 0x1f3930 Tick, 0x1f3920 PostPreTick, 0x1f3910 PrePostTick and
  0x1f3900 the new virtual (the map: 0x1f3930 PreTick … 0x1f3900 PrePostTick, 0x1f3940 new). The
  bodies are equal, so only the names are wrong. 0x1efd10 (new) is CEntity::GetTargetPosW by slot.
  For the zEntity check.
- CZSealBody: 0x25a8d0 (new) fills the new slot between PrePostTick and PostTick and holds the
  second half of the prototype PostTick (UpdateAiEvent … HandleBloodDrip); 0x25a6d0 keeps
  PostTick's slot and first half. The map's PostTick pair is right by slot. For the seal.cpp check.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| deviating (weak, slot-only) | 5 | 5 | 0 |
| unsure | 3 | 2 (counterparts right; now deviating) | 1: ChangeItemModel is not 0x2b89a0's identity (split) |
| new | 32 | 29 | 3: 0x293ac0, 0x293ae0, 0x293b30 have counterparts |
| removed | 10 | 6, 1 open (DrawAutoReticle) | 3: Initalize, OnMissionStart, OnRecycleEntity |
| exact (not checked) | 130 | - | 1 found in passing: 0x293bd0 is OnRecycleEntity, not OnMissionEnd |

Sample: 15 of 15 same function.

Owner attribution was right for every row of the list. What misled it:

- The three CSealCtrl rows and the exact 0x293bd0: these are virtual functions with no direct
  caller, so only position and bodies were left. The prototype has three equal empty bodies
  (OnMissionEnd, OnMissionStart, OnRecycleEntity); the release has one empty body and two filled
  ones. Position matched the one empty body to the first empty prototype function (OnMissionEnd),
  and the filled ones had nothing to match. Initalize lost 180 of its 208 bytes. The vtable decides
  all four at once: the tool does not read vtables, and here they were the only evidence. Reading
  the tables (prototype `__vt__` symbols, release table found by its mapped entries) and pairing
  slot by slot would also fix the CEntity rows above.
- GetTargetPosW (`ambiguous`): two new look-alikes of the same size read other body parts; the
  vtable and the part offset settle it.
- HomingTick (`ambiguous`): split into two routines; the call site before Animate settles it.
- ChangeItemModel: the call site agrees, but the release function is the caller's block, not the
  callee. The tool's low similarity was right to hold it.

Cost: the 32 new rows took most of the time (about 3 minutes each to describe and name). The
vtables saved the most: once the CSealCtrl table was dumped, seven rows settled together. The
sheet's slot lines and "unpaired on the other side" pointed straight at Initalize. Still missing
from the sheet: vtable slots for virtual functions, and a ranked list of the other side's
unpaired functions by operation similarity for each new and removed row (that settled
DrawAutoReticle's candidate and ruled out the rest).
