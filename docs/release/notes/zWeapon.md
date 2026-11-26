# Stage 2: gamez/zWeapon (2026-11-26)

The one list of `gamez/zWeapon` (list a): the owner files zwep_weaponlist.cpp, zwep_ammolist.cpp,
zwep_explosive.cpp, zwep_ftsweapon.cpp, zwep_global.cpp, zwep_projectile.cpp,
zwep_projectilelist.cpp, zwep_weapon.cpp and zwep_ammo.cpp (release 0x32d670-0x33a850). It holds 35
uncertain rows (30 new, 2 removed, 2 deviating pairs by position flagged `caller-mismatch`, 1 weak
pair (`position`, `slot-only`)), 15 sampled deviating rows out of 91, and 192 exact rows that were
not checked one by one. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-weapon`, who did not write the
tool, at HEAD 66d3acea. The check sheet (`compare.py --sheet gamez/zWeapon --list a`) was the
starting point. Both images were disassembled with the release tools; callers were found by
scanning both images for `jal`/`j`, data words and `lui`/`addiu` pairs. Ghidra was not needed.

As the guard on the committed pairs, all 284 paired rows of the range had their callers and
address-loaders compared with the prototype's through the map, and their ordered calls and loads
compared for substitutions; the 7 constructors and destructors that store a vtable had the stored
table compared (by RTTI name); the 4 vtables with a slot in the range were aligned slot by slot;
the 8 functions anywhere that load the address of a zWeapon function had their ordered pointer
loads compared; the stored neighbours of each zWeapon function found in data were compared.

What settled rows, in the order it was used: the call site in a paired caller (GetWeaponAccuracy
and PerturbAimVector, Recoil and SetCurAccuracy, HandleRemotePlaceExplosive, the PostTicks, the
three `new CZAmmoPickupInstance` sites); the slot between paired neighbours; the reader keys of
ZWepReader::Read; strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x32e400 | - | new, no owner | confirmed; owner zwep_explosive.cpp | PlacedExplosive method: stores a node at +0xbc and a matrix (identity when NULL) at +0xd0; PostTick rebuilds the instance matrix from that node every tick. Sole caller HandleRemotePlaceExplosive, on the new PlacedExplosive |
| 0x32e430 | - | new, no owner | confirmed; owner zwep_explosive.cpp | PlacedExplosive method: stores a node at +0xc0, which PostTick walks up (parents +0x64) to set +0xb8 for ids 151/153; same caller, right after 0x32e400 |
| 0x32eac0 | - | new, owner guess | confirmed | CTargetMods setter of a new float at +0x50; ZWepReader::Read calls it after fetching "KES(%d)" |
| 0x32ead0 | - | new, owner guess | confirmed | CTargetMods setter of a new int at +0x4c; Read, after fetching "KC(%d)" |
| 0x32eae0 | - | new, owner guess | confirmed | getter of +0x50; caller CZKit::Recoil |
| 0x32eaf0 | - | new, owner guess | confirmed | getter of +0x4c; caller Recoil. The release CTargetMods constructor initialises +0x4c = 3 and +0x50 = 1.0 |
| 0x32eb20 | - | new, owner guess | confirmed | tests the weapon id (+0x60) for 176-179; caller FindNextGrenadeLauncherAmmo; sits before IsGrenadeLauncherAmmo |
| 0x32ef20 | - | new, owner guess | confirmed | `lwc1 f0,0x20(a0)`: the getter of the field SetTarget_DilateUponFire writes, in the getter run after GetTarget_DilateUponMovement; caller Recoil |
| 0x32f180 | 0x315e70 `AccuracyBurstCnt_Max__11CZFTSWeaponCFv` | deviating, position, caller-mismatch | confirmed | its calls moved from SetCurAccuracy into Recoil in the same order (Min, Max, Max); reads +0x1c4, where the setter AccuracyBurstCnt_Max(int) now writes (+0x18, like every CZFTSWeapon field after the CTargetMods) |
| 0x32f190 | 0x315e80 `AccuracyBurstCnt_Min__11CZFTSWeaponCFv` | deviating, position, caller-mismatch | confirmed | the same; reads +0x1c0, written by AccuracyBurstCnt_Min(int) |
| 0x3304b0 | - | new, owner guess | confirmed | CZProjectile method: sets bit 3 of +4 (DoMiss now tests it: state 7 instead of 6); caller zAnimFireWeaponTick, after Fire |
| 0x3304d0 | - | new, owner guess | confirmed | CZProjectile method: sets the position (+0x4c, +0x40, node SetPosition) and then does SetVelW's work; callers new AI grenade callbacks 0x264250 and 0x2644e0 |
| 0x3305c0 | - | new, owner guess | confirmed | sets the position only; caller new 0x2643a0 |
| 0x330620 | - | new, owner guess | confirmed | sets the position and a zero velocity; caller new 0x264440. The four callbacks are loaded by CAiSGrenade::Tick; the prototype SetReturnVelocity called GetInstance, SetRotation and SetVelW itself |
| - | 0x317cd0 `HandleDetonateExplosion__12CZProjectileFv` | removed | confirmed | its mark (GetAltitude, GetRegion, AddNewMark) is inline in the release HandleDelayedDetonate (its only caller); its loop over the proximity hits is replaced by 0x331280/0x331340/0x331550, one hit per tick |
| 0x331280 | - | new, owner guess | confirmed | dispatches one proximity hit (index in the low 7 bits of +5, node handler +0x94 slot 2) when 0x331550 allows it; caller PlacedExplosive::PostTick |
| 0x331340 | - | new, owner guess | confirmed | registers a direct-fire line test (+0x28) from the blast point to the next hit node's box centre; callers both PreTicks (PlacedExplosive, CZProjectile) |
| 0x331550 | - | new, owner guess | confirmed | walks that line test's hits and reduces the explosion radius by each material's factor (+0x20); returns whether the target is still reached; callers 0x331280 and CZProjectile::PostTick |
| 0x334440 | - | new, no owner | confirmed; owner zwep_projectilelist.cpp | CZProjectileList method (the +4/+8/+0xc placed list and the +0/+0x10/+0x18 projectile array): counts the owner's (+0xa4) placed and active projectiles whose weapon type is 120, 150 or 170; caller CZKit::WillFireWeapon |
| 0x334620 | - | new, no owner | confirmed; owner zwep_projectilelist.cpp | walks the same two lists calling only GetName (debug output compiled out); caller CMission::Close |
| 0x334730 | - | new, no owner | confirmed; owner zwep_projectilelist.cpp | removes the placed explosives of id 152 within a radius of a point (ReportGrenadeStatus, CPickup::Destroy, delete, erase, as RemoveExplosive does); sole caller 0x3373a0 |
| 0x3354a0 | - | new, owner guess | confirmed | sets bit 0 of +6 on every placed and active projectile (both PreTicks return early on it); caller _OnMissionComplete |
| 0x336e70 | - | new, copy, no owner | confirmed; owner guess zwep_projectilelist.cpp | `jr ra; lw v0,0x24(a0)`: CZAmmoPickupInstance getter of the new +0x24; caller CPickup::Destroy |
| 0x336e80 | - | new, copy, no owner | confirmed; owner guess the same | setter of +0x24; caller DropAmmo |
| 0x336e90 | - | new, no owner | confirmed; owner guess the same | erases the entries whose count is 0 from the three vectors; caller CleanupAmmoPickup |
| 0x336f40 | - | new, no owner | confirmed; owner guess the same | zeroes entry i of the three vectors; caller HandlePickupAck |
| 0x337020 | - | new, no owner | confirmed; owner guess the same | counts the entries with a non-zero count; seven callers (pickup, kit, seal body, find_closest_ammo) |
| 0x337060 | - | new, no owner | confirmed; owner guess the same | copies entry i out (item, ammo, count); returns whether it exists; the same seven callers |
| 0x337180 | - | new, no owner | confirmed; owner guess the same | writes entry i; caller PickupAmmo |
| 0x337280 | - | new, no owner | confirmed; owner guess the same | appends one entry to the three vectors; callers ftsFixupAiMap, CreateNetAmmoPickup, FillAmmoPickupInstance |
| 0x337320 | - | new, no owner | confirmed; owner guess the same | the CZAmmoPickupInstance constructor: called after `new(40)` at the three sites that built the 36-byte record inline in the prototype (ftsFixupAiMap, CreateNetAmmoPickup, DropAmmo) |
| 0x3373a0 | - | new, no owner | confirmed; owner guess zwep_weapon.cpp | `j 0x334730` with CZWeapon::m_pProjectilelist: a CZWeapon static wrapper, directly before TimerCleared; caller new zAnim tick 0x1b8b50 (point +4, radius +0x10) |
| - | 0x31cb50 `GetAccuracy__Q28CZWeapon9AI_PARAMSCFf` | removed | corrected to 0x3375b0 | see the row below |
| 0x3375b0 | - | new, owner guess | corrected to 0x31cb50 `GetAccuracy__Q28CZWeapon9AI_PARAMSCFf` | the same two callers (PerturbAimVector, GetWeaponAccuracy) call it at the same place with the same receiver (weapon + 84); the slot between SetDefaults and Close on both sides. The prototype body was a stub returning 1.0; the release computes the accuracy from the range |
| 0x338c80 | 0x31e140 `GetWeaponName__8CZWeaponF10EQUIP_ITEM` | deviating (weak), position, slot-only, caller-mismatch | confirmed | still the wrapper of CZWeaponList::GetWeaponName on m_listWeapons, between GetWeaponUIName and GetWeaponId on both sides; it now returns "falling damage" for id 253. Its prototype caller OnDeath had the kill-message code that moved into new 0x254020 (just before OnDeath); CHUD::Tick also calls it |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x32e440 | 0x315420 `PreTick__15PlacedExplosiveFf` | yes | slot +0x8 of the PlacedExplosive vtable on both sides |
| 0x32ea20 | 0x3157a0 `__ct__11CTargetModsFv` | yes | same caller, the CZFTSWeapon constructor |
| 0x32ed60 | 0x315a50 `GetRumbleHigh_Time__11CZFTSWeaponCFv` | yes | same caller Recoil, same call order; +0x18 like its neighbours |
| 0x32ed70 | 0x315a60 `GetRumbleHigh_Enable__11CZFTSWeaponCFv` | yes | the same |
| 0x330d80 | 0x317800 `GetDamage__12CZProjectileFPC6CPnt3Df` | yes | the same ten callers |
| 0x3316f0 | 0x317df0 `HandleDelayedDetonate__12CZProjectileFv` | yes | same callers, the two PostTicks |
| 0x331a10 | 0x3180d0 `Cleanup__12CZProjectileFv` | yes | the same six callers |
| 0x3327f0 | 0x318d70 `DoMiss__12CZProjectileFfP6CPnt3D` | yes | same caller HandleIntersections |
| 0x333540 | 0x319850 `PreTick__12CZProjectileFf` | yes | slot +0x8 of the CZProjectile vtable |
| 0x333e70 | 0x319ff0 `SetProjectile__12CZProjectile...` | yes | the same three callers |
| 0x3342a0 | 0x31a3a0 `__ct__12CZProjectileFv` | yes | same callers; stores the CZProjectile vtable |
| 0x334d00 | 0x31a950 `RemoveProjectile__16CZProjectileListFP12CZProjectile` | yes | the same three Fire callers |
| 0x334f90 | 0x31ac00 `PostTick__16CZProjectileListFf` | yes | same caller CZWeapon::PostTick |
| 0x335110 | 0x31ad80 `PreTick__16CZProjectileListFf` | yes | same caller CZWeapon::PreTick |
| 0x3391b0 | 0x31e640 `SetDecalSetName__8CZWeaponFPCc` | yes | same caller Read; zwep_weapon.cpp lines 803/805 -> 806/808 |

The cross-check found no wrong committed pair outside the list's rows.

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x3375b0 | 0x31cb50 | the same callers PerturbAimVector and GetWeaponAccuracy at the same call site (receiver weapon + 84); slot between SetDefaults and Close on both sides | socom-release-check-weapon | 2026-11-26 | | |
| 0x338c80 | 0x31e140 | wrapper of CZWeaponList::GetWeaponName on m_listWeapons; slot between GetWeaponUIName and GetWeaponId; OnDeath's call moved into new 0x254020 | socom-release-check-weapon | 2026-11-26 | | |
| 0x32f180 | 0x315e70 | its calls moved from SetCurAccuracy to Recoil in the same order; reads the field AccuracyBurstCnt_Max(int) writes | socom-release-check-weapon | 2026-11-26 | | |
| 0x32f190 | 0x315e80 | the same; reads the field AccuracyBurstCnt_Min(int) writes | socom-release-check-weapon | 2026-11-26 | | |
| 0x32e400 | - | owner: PlacedExplosive method (+0xbc, +0xd0 read by PostTick); directly before PreTick__15PlacedExplosiveFf | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_explosive.cpp | |
| 0x32e430 | - | owner: PlacedExplosive method (+0xc0 read by PostTick); directly before PreTick__15PlacedExplosiveFf | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_explosive.cpp | |
| 0x334440 | - | owner: CZProjectileList method (list layout of RemoveExplosive); directly before AcquireProjectile | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | |
| 0x334620 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | |
| 0x334730 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | |
| 0x336e70 | - | owner: CZAmmoPickupInstance method, after ZWepReader at the end of the file's range (position only) | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x336e80 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x336e90 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x336f40 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x337020 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x337060 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x337180 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x337280 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x337320 | - | owner: the same | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_projectilelist.cpp | guess |
| 0x3373a0 | - | owner: CZWeapon static (m_pProjectilelist), directly before TimerCleared__8CZWeaponFv | socom-release-check-weapon | 2026-11-26 | src/gamez/zWeapon/zwep_weapon.cpp | guess |

Rows that change together: 0x3375b0 and the removed 0x31cb50 (one row once paired).

## New and removed

New in the list (names are guesses unless the basis says otherwise; the prototype's naming
patterns are followed):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x32e400 | attaches a placed explosive to a node with a relative matrix | guess: `SetAttachNode__15PlacedExplosiveFPQ23zdb5CNodePC7CMatrix` |
| 0x32e430 | records the node the explosive was placed on | guess: `SetPlacedOnNode__15PlacedExplosiveFPQ23zdb5CNode` |
| 0x32eac0, 0x32ead0, 0x32eae0, 0x32eaf0 | set/get two new CTargetMods fields (+0x50 float "KES", +0x4c int "KC") | guess: `SetKickEndScale__11CTargetModsFf`, `SetKickCount__11CTargetModsFi`, `GetKickEndScale__11CTargetModsCFv`, `GetKickCount__11CTargetModsCFv` (the reader keys "KES(%d)" and "KC(%d)"; the expansions are guesses) |
| 0x32eb20 | is the weapon one of ids 176-179 (GL_HE ... GL_FRAG in the prototype enum) | guess: `IsGrenadeLauncherGrenade__11CZFTSWeaponFv` |
| 0x32ef20 | reads the DilateUponFire field | `GetTarget_DilateUponFire__11CTargetModsCFv` (the field its setter writes; the getter run) |
| 0x3304b0 | sets a projectile flag (bit 3 of +4) after a scripted fire | guess: `SetAnimFired__12CZProjectileFb` |
| 0x3304d0, 0x3305c0, 0x330620 | set a projectile's position (with a velocity, alone, with zero velocity) | guess: `SetPosVelW__12CZProjectileFPC6CPnt3DPC6CPnt3D`, `SetPosW__12CZProjectileFPC6CPnt3D`, `SetPosWStopped__12CZProjectileFPC6CPnt3D` (next to SetVelW's pattern) |
| 0x331280 | applies the explosion to one proximity hit per tick | guess: `HandleProximityHit__12CZProjectileFv` |
| 0x331340 | registers the line-of-sight test to the next proximity hit | guess: `RegBlastLineOfSight__12CZProjectileFv` |
| 0x331550 | does the blast reach the target through the materials on the line | guess: `BlastReaches__12CZProjectileFPQ23zdb11DiIntersect` |
| 0x334440 | counts a player's live grenades and explosives | guess: `GetNumActiveExplosives__16CZProjectileListFi` (next to GetNumRemoteExplosives(int)) |
| 0x334620 | walks the projectiles (debug dump, output compiled out) | guess: `Dump__16CZProjectileListFv` |
| 0x334730 | removes the placed explosives of id 152 within a radius | guess: `RemoveExplosivesInRadius__16CZProjectileListFPC6CPnt3Df` |
| 0x3354a0 | freezes every projectile at the end of a mission | guess: `FreezeAll__16CZProjectileListFv` |
| 0x336e70 ... 0x337320 | CZAmmoPickupInstance, now a class with out-of-line members: get/set +0x24, compact, clear entry, count, get entry, set entry, add entry, constructor | `__ct__20CZAmmoPickupInstanceFv` for 0x337320 (the `new` sites); the rest guesses: `GetOwner`/`SetOwner` (+0x24, meaning unknown), `Compact`, `ClearEntry(int)`, `GetNumEntries`, `GetEntry(int, ...)`, `SetEntry(int, ...)`, `AddEntry(...)` |
| 0x3373a0 | static wrapper of 0x334730 on the global projectile list | guess: `RemoveExplosivesInRadius__8CZWeaponFPC6CPnt3Df` |

Not new, though the map has it as new: 0x3375b0 (`GetAccuracy__Q28CZWeapon9AI_PARAMSCFf`).

Really removed:

- HandleDetonateExplosion: its mark is inline in HandleDelayedDetonate; its hit loop became the
  per-tick 0x331280 with the line-of-sight test 0x331340/0x331550.
- Not removed, though the map has it: GetAccuracy__Q28CZWeapon9AI_PARAMSCFf (0x3375b0).

Layouts, plainly shown by settled rows: CTargetMods gained an int at +0x4c and a float at +0x50
(so the CZFTSWeapon fields after its CTargetMods move by +0x18); CZAmmoPickupInstance grew from 36
to 40 bytes (an int at +0x24); PlacedExplosive gained +0xbc, +0xc0 and a matrix at +0xd0.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses, except GetTarget_DilateUponFire and the
  CZAmmoPickupInstance constructor.
- The owner of the CZAmmoPickupInstance members (0x336e70-0x337320) and of 0x3373a0 is by position
  only; the class is declared in zseal.h and could have a file of its own.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 30 | 29 | 1: 0x3375b0 is GetAccuracy__Q28CZWeapon9AI_PARAMSCFf |
| removed | 2 | 1 (HandleDetonateExplosion) | 1: GetAccuracy is 0x3375b0 |
| deviating, position, caller-mismatch | 2 | 2 | 0 |
| deviating (weak), position, slot-only | 1 | 1 | 0 |

Owners: of the 15 owner-less rows, five belong by class to zwep_explosive.cpp (2) and
zwep_projectilelist.cpp (3); the other ten are placed by position (guess). The tool's owner guesses
held.

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 284 paired rows compared (callers and address-loaders through the map, ordered
calls), 7 vtable stores, 4 vtables slot by slot, 8 pointer loaders, 8 stored functions' neighbours.
Differences looked at: 32 caller sets, 2 call-order substitutions, 3 data neighbourhoods. All are
callers added in the release, callers that moved (SetCurAccuracy to Recoil; OnDeath to new
0x254020; SetReturnVelocity to the new AI grenade callbacks; HandleSealStep to new 0x29ddb0),
inlining (HandleDetonateExplosion into HandleDelayedDetonate), debug calls compiled out
(ChooseWeapon's GetName), one changed test (setup__13AI_FIREPARAMS calls is_throwtype where it
called IsM203Weapon), a reordered body (HandleBounce) and one data word that is not a pointer
(IsPrimary's address in a table of unaligned code addresses at 0x44eb40).
Pairs wrong: 0.

What misled it:

- GetAccuracy: the prototype body was a 16-byte stub (`return 1.0`), so no similarity was possible;
  the release body is 172 bytes. Its callers and its slot are unchanged and decide it.

What cost the most time: the CZAmmoPickupInstance group (nine new members of a header class, with
no owner from the tool) and reading the new explosion line-of-sight code. Suggestion:

- Pair a removed and a new function that share the same slot and the same caller set even when the
  bodies have nothing in common (a stub replaced by a real body).
