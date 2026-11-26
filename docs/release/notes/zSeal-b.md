# Stage 2: gamez/zSeal, list b (2026-11-26)

List b of `gamez/zSeal` split 6 ways (`build/release/lists/gamez-zSeal-b.md`): owner files
`seal_ai.cpp` (release 0x25efc0-0x2629b0 and 0x17d930), `seal_body.cpp` and `seal_ik.cpp`. It holds
48 uncertain rows (36 new, 8 removed, 2 unsure, 2 weak pairs, both `slot-only`), 15 sampled
deviating rows of 77, and 30 exact rows that were not checked. Pairing produced by
`socom-release-compare-c1` (`python tools/release/compare.py`, the function map at HEAD 8185d1bb).
Checked by `socom-release-check-seal-b`, who did not write the tool, on commit 8185d1bb.

Method: the check sheet (`compare.py --sheet gamez/zSeal --list b`) first; then both loaded images
disassembled, calls named through the map, callers found by scanning both images for `jal`/`j`,
and data words scanned for function addresses. Evidence that settled rows, in the order it was
used: vtable slots (the release CAiState vtables, matched through the paired overrides); the call
site inside a paired caller; the callback thunks (`j <body>`) passed to `AlignForPickup`; the slot
between paired neighbours; the `FindAnimType` strings stored into the `AnimTypes` globals.
Ghidra was not needed.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x25f050 | - | new | confirmed | base entry (empty) of a new CAiState virtual, release vtable slot 3 |
| 0x25f090 | - | new | corrected to 0x259220 `CAiState::CanPursue(CSealCtrlAi*) const` | release slot 10 holds the CanPursue overrides of 8 paired subclasses (prototype slot 9); 0x25f090 is the base entry; emitted after CanSwitchAiState as in the prototype |
| 0x25f0b0 | - | new | confirmed | base entry (`return 1`) of a new CAiState virtual, slot 13; no override |
| 0x25f0c0 | - | new | confirmed | pushes AI state 25 and fills it; replaces OnWeaponHit's GetAiAware/SetAiEvent/SetAiAware calls |
| 0x25f260 | - | new | confirmed | map search called by OnCommand where the prototype called ftsGetPlayer |
| 0x25fa70 | - | new | confirmed | helper of 0x25f260 only |
| 0x25fbf0 | - | new | confirmed | stuck recovery, reached from new 0x271290; pushes STATE_AVOID or STATE_PATHRECO |
| 0x260040 | - | new | confirmed | member of a new tracker record (see New) |
| 0x260070 | - | new | confirmed | same record: update |
| 0x260160 | - | new | confirmed | same record: level-1 update |
| 0x260270 | - | new | confirmed | same record: level-2 update |
| 0x2602e0 | - | new | confirmed | same record: level-4 update |
| 0x260410 | - | new | confirmed | same record: reset |
| 0x260430 | - | new | confirmed | new call in SensorPreTick after EventTick; no prototype call there |
| 0x260860 | - | new | confirmed | initialiser of a 5-word range record; called by `__sinit_seal_ai.cpp` |
| 0x262720 | - | new | corrected to 0x25ad00 `CAiSAnimate::Tick(float, CSealCtrlAi*)` | entry of vtable slot 4 (Tick) of the CAiSAnimate vtable 0x489b30; slot between OnSignal CAiSPursue and OnSignal CAiSAnimate; the same Top/PushBlend state machine |
| 0x2629a0 | - | new | confirmed | `return this` accessor (copy of 0x264240), used on CAiSAnimate +64 |
| - | 0x259230 `CSealCtrlAi::HasSniperRifle()` | removed | confirmed | no copy; the only caller (HandleEvent) lost the call; 0x2608c0 (list e) calls `CZKit::HasSniperRifle` directly |
| - | 0x259240 `CSealCtrlAi::InGuardRegion()` | removed | confirmed | no copy; HandleEvent lost the call; 0x2608c0 calls `GetRegionTypeContainer` directly |
| - | 0x25ab70 `CEntity::IsAlive() const` | removed | confirmed | inline everywhere in the release (no 20-byte copy); its use in CAiSPursue::Tick moved into 0x300940 (list f) |
| - | 0x25ab90 `CTarget::GetEntity() const` | removed | confirmed | the same site: CAiSPursue::Tick now calls 0x300940 on the target (+1212 → +1396) |
| - | 0x25ad00 `CAiSAnimate::Tick` | removed | corrected to 0x262720 | see 0x262720 |
| - | 0x25c860 `CSealCtrlAi::SetReturnVelocity(...)` | removed | confirmed | both call sites in CAiSGrenade::Tick are gone (the release calls 0x264240/0x2770c0 there); the aim block survives in 0x264600 (list d), which has a different receiver and call site |
| - | 0x25d080 `is_throwtype(EQUIP_ITEM)` | removed | corrected to 0x2667f0 | equal size and shape (`imm-only`, similarity 0.938): the range bound 6 → 7; moved before `AI_FIREPARAMS::setup`, now its only caller (0x2667f0 is a list d row) |
| 0x279bc0 | - | new | confirmed | gear placement around the "rifle" part; no prototype function in the slot |
| 0x279ff0 | 0x26eb70 `CZSealBody::RestrainBuddy(CZSealBody*)` | unsure | confirmed, deviating | the same body calls and "Restrained anim set"; reached through the new wrapper 0x27a420 and the thunk 0x27a650 (`j 0x279ff0`) |
| 0x27a420 | - | new | confirmed | restrain wrapper: AlignForPickup with callback 0x27a650; called by ExecuteAction_ApplyRestraint |
| 0x27a650 | - | new | confirmed | callback thunk `j RestrainBuddy` |
| 0x27a660 | - | new | corrected to 0x26ef00 `CZSealBody::StabBuddy(CZSealBody*)` | the same body (DropAllItems, PushBlend, SetHealth, SetPosition, ClearToBase, RestoreCameraPosition); reached through the thunk 0x27aac0 like RestrainBuddy; similarity 0.346 against 0.132 for 0x27a890 |
| 0x27a890 | 0x26ef00 `StabBuddy` | deviating (weak), slot-only | corrected to new | the knife wrapper (AlignForPickup with callback 0x27aac0); it took StabBuddy's place in ExecuteAction_KnifeAttack |
| 0x27aac0 | - | new | confirmed | callback thunk `j 0x27a660` |
| 0x27b620 | - | new | confirmed | pending weapon-change completion in Tick_0; no prototype function in the slot |
| 0x27f240 | 0x2736c0 `CZSealBody::AbortPeek()` | deviating (weak), slot-only | confirmed | callers CSealCtrl::PreTick (two sites both sides); 1-to-1 slot between PeekBaseState and LowerBinoculars; the same `peek == 3` test, the inlined clear now a ClearToBase call |
| 0x284800 | - | new | confirmed | CanProneAim gate, called by CSealCtrl::PreTick |
| 0x285760 | - | new | confirmed | anim-set restore when standing still, called by SealAnim |
| 0x285890 | - | new | confirmed | the same restore, unconditional, called by OnWeaponHit |
| - | 0x27c050 `CZSealBody::IsCurrentBlend(AnimType) const` | removed | confirmed | inline in the release (no out-of-line copy; the four new two-anim tests below inline it) |
| 0x2872c0 | - | new | confirmed | IsCurrentBlend(10) or (11) |
| 0x287350 | - | new | confirmed | IsCurrentBlend(8) or (9) |
| 0x2873e0 | - | new | confirmed | IsCurrentBlend of two AnimTypes globals ("Land forward", "Land backwards") |
| 0x287470 | - | new | confirmed | IsCurrentBlend of two AnimTypes globals ("Fall forward", "Fall backwards") |
| 0x287500 | - | new | confirmed | `return 0`; only caller 0x205e10 (fts_remote, new) |
| 0x288720 | - | new | confirmed | blend-stack search, 7 calls from IsReloading |
| 0x288780 | 0x273490 `CZSealBody::ClearToBase(bool)` | unsure | confirmed, deviating | callers PreTick, InStateCrouch, InStateStand, BindAnimSet (4 sites), WeaponHitAnim, CAiSSurrender::OnSignal on both sides, plus new ones (RestrainBuddy, StabBuddy, AbortPeek, ...) |
| 0x2b3a00 | - | new | confirmed | slot-table setter (+2092 array, index + 1) |
| 0x2b3a20 | - | new | confirmed | slot-table clear, bounded by +2088 |
| 0x2b3a50 | - | new | confirmed | slot-table getter, bounded by +2088 |
| 0x2b3a80 | - | new | confirmed | zeroes +24/+28; called by DecrZoomState |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | reason |
|---|---|---|---|
| 0x27ca30 | 0x270d10 `Recoil` | confirmed | same caller, paired neighbours both sides |
| 0x27edb0 | 0x273020 `UpdatePeek` | confirmed | same caller; previous neighbour paired |
| 0x27f310 | 0x273890 `RaiseBinoculars` | confirmed | same caller, paired neighbours |
| 0x280100 | 0x274800 `GetPutativeFirePointW` | confirmed | same caller, paired neighbours |
| 0x2813d0 | 0x275da0 `SetStanceIdle` | confirmed | paired neighbours both sides; shares the caller 0x2e7340 (one prototype caller lost the call) |
| 0x281470 | 0x275e80 `Prone_0` | confirmed | the same 4 call sites, paired neighbours |
| 0x281590 | 0x275fa0 `Prone` | confirmed | same callers, paired neighbours |
| 0x281890 | 0x2762d0 `Crouch_0` | confirmed | the same 9 call sites in 7 callers, paired neighbours |
| 0x2827c0 | 0x277300 `CheckAnim` | confirmed | same caller, paired neighbours |
| 0x284110 | 0x2790f0 `InStateHang` | confirmed | same caller, paired neighbours |
| 0x2842e0 | 0x2792e0 `InStateProne` | confirmed | same caller; previous neighbour paired |
| 0x285de0 | 0x27ab70 `InStateStand` | confirmed | same caller, paired neighbours |
| 0x287e60 | 0x27cbf0 `PopBlend` | confirmed | every release caller is a prototype caller (many prototype sites now call ClearStack/ClearToBase); PushBlend before it on both sides |
| 0x288c60 | 0x27d3e0 `GetSpeedState` | confirmed | same 3 callers, paired neighbours |
| 0x2b37c0 | 0x2a4d30 `TurnSetup` | confirmed | same 2 callers, paired neighbours |

Seen in passing, not in the list: the exact row 0x25f0a0 ↔ 0x259220 `CAiState::CanPursue` is
wrong. Both 0x25f090 and 0x25f0a0 are `jr ra; li v0,1`; the vtables put CanPursue at 0x25f090 and
make 0x25f0a0 the base of the new slot 12 (overridden once, by CAiSBreach 0x2ec870).

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x25f090 | 0x259220 | vtable slot 10 of the CAiState family holds the paired CanPursue overrides; 0x25f090 is the base entry | socom-release-check-seal-b | 2026-11-26 |
| 0x25f0a0 | new | base entry of new vtable slot 12 (override CAiSBreach 0x2ec870); bytes equal to CanPursue's | socom-release-check-seal-b | 2026-11-26 |
| 0x262720 | 0x25ad00 | vtable slot 4 of the CAiSAnimate vtable; slot between OnSignal CAiSPursue and OnSignal CAiSAnimate; same Top/PushBlend state machine | socom-release-check-seal-b | 2026-11-26 |
| 0x2667f0 | 0x25d080 | equal size and shape, imm-only (range bound 6 -> 7); caller now AI_FIREPARAMS::setup | socom-release-check-seal-b | 2026-11-26 |
| 0x279ff0 | 0x26eb70 | same body calls and "Restrained anim set"; reached through thunk 0x27a650 from wrapper 0x27a420 | socom-release-check-seal-b | 2026-11-26 |
| 0x27a660 | 0x26ef00 | same body calls; reached through thunk 0x27aac0 from wrapper 0x27a890 as RestrainBuddy is | socom-release-check-seal-b | 2026-11-26 |
| 0x27a890 | new | knife wrapper (AlignForPickup + callback 0x27aac0) in StabBuddy's call site | socom-release-check-seal-b | 2026-11-26 |
| 0x27f240 | 0x2736c0 | callers CSealCtrl::PreTick (two sites); 1-to-1 slot between PeekBaseState and LowerBinoculars | socom-release-check-seal-b | 2026-11-26 |
| 0x288780 | 0x273490 | same callers (PreTick, InStateCrouch, InStateStand, BindAnimSet x4, WeaponHitAnim, CAiSSurrender::OnSignal) | socom-release-check-seal-b | 2026-11-26 |

All pairs are deviating except 0x25f090 ↔ 0x259220, whose bytes are equal (exact). 0x2667f0 is a
list d row and 0x25f0a0 an exact row of this list. The other rows stand as the map has them.

## Layouts seen in settled rows

- CAiState vtable: three new virtuals, at release slots 3 (after OnSignal), 12 and 13 (after
  CanPursue and GetScriptResponse); the destructor moves from slot 11 to 14.
- CAiSAnimate (Tick): the status word +20 → +16, the anim type +44 → +36, the done bit at +12
  bit 0 → +26 bit 1.
- CZSealBody: the anim set +1116 → +1124 and the current base anim +1124 → +1132 (the inlined
  IsCurrentBlend).
- CSealCtrlAi: the CTarget member +1212 → +1396 (CAiSPursue::Tick).

## New and removed

New, with proposed names (all guesses unless marked otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x25f050 | default of new CAiState virtual slot 3, empty; CAiSScript overrides it (0x2ed130: when the id matches its +36, kind 1 clears it, 2/3 set/clear a flag bit) | `CAiState::OnNotify(int, unsigned char)`, guess from the override |
| 0x25f0a0 | default of new slot 12, `return 1`; CAiSBreach's override returns 1 when a 7-bit field of its third argument is 3 or 8 | `CAiState::CanAccept(...) const`, guess |
| 0x25f0b0 | default of new slot 13, `return 1`, never overridden | unnamed: no basis |
| 0x25f0c0 | CSealCtrlAi: if the event kind's bit is set in the +1392 mask, pushes state 25 (STATE_EVENT in the prototype's numbering) and stores kind, position, source point and flags; otherwise SetAiAware 3 or 2 by flag 0x100/0x80 | `CSealCtrlAi::PushEventState(...)`, guess |
| 0x25f260 | map search for the Goto command (GetLocation of two points, map cells, GetClosestDir, the neighbour table), with 0x25fa70 | `CSealCtrlAi::FindCommandGotoLoc(...)`, guess |
| 0x25fa70 | tests one map cell (dummy_cell fallback) and records it for 0x25f260 | guess: a static cell-check helper |
| 0x25fbf0 | stuck recovery: checks the climb anims (BaseAnim 46/47/48), local static floats 2.0/2.0/2.5, pushes STATE_AVOID or STATE_PATHRECO | `CSealCtrlAi::HandleStuck()`, guess |
| 0x260040, 0x260070, 0x260160, 0x260270, 0x2602e0, 0x260410 | a new tracker record (+0 start time from the clock at 0x4d48e0, +4 value, +8 level, +16 flag, +20 location, +24 other seal, +28 byte): elapsed time; update(level, dt) returning 0/1/2; level-1 update by map cell (PathFollowTick, PostComputeNextPosition); level-2 by position; level-4 when blocked by another seal (CollidePlayers, PathFollowTick); reset | guess: a stuck/blocked monitor (`Elapsed`, `Update`, `UpdateCell`, `UpdatePos`, `UpdateBlocker`, `Reset`) |
| 0x260430 | look-around tick from SensorPreTick: FindAiState, GetClosestDir, CountMapVisDir, SetLookDirW, SetLookTimer, using a static record at 0x51ff40 | `CSealCtrlAi::LookAroundTick()`, guess |
| 0x260860 | initialises a 5-word range record (base, base + len, len, limit, overflow); called by `__sinit_seal_ai.cpp`, 0x260430, 0x271290, PostTick | guess: the record's constructor |
| 0x2629a0 | `return this`, used on a list at CAiSAnimate +64 | guess: an inline list sentinel accessor |
| 0x279bc0 | places the "rifle" part as gear (PartInSpace, quaternion, SetPartAsGear twice); called by _OnMissionComplete, CheckAnim, PopBlend | `CZSealBody::ResetGear()`, guess |
| 0x27a420 | restrain wrapper (ClearStack, PushBlend, AlignForPickup with callback 0x27a650) | `CZSealBody::AlignToRestrainBuddy(CZSealBody*)`, guess after CrouchToPickupBuddy |
| 0x27a650 | `j RestrainBuddy` | `RestrainBuddyCallback(void*, void*)`, after the prototype's PickupBuddyCallback |
| 0x27a890 | knife wrapper (AlignForPickup with callback 0x27aac0) | `CZSealBody::AlignToStabBuddy(CZSealBody*)`, guess |
| 0x27aac0 | `j StabBuddy` | `StabBuddyCallback(void*, void*)`, as above |
| 0x27b620 | when the pending item change on the +280 anim completes (0x1e2590), PostChangeWeapon(1 or 2) for items 3/4, then 0x277ce0, sets +4008 = 0.4 | `CZSealBody::FinishWeaponChange()`, guess |
| 0x284800 | false while the +3974 flag is set and +3744 > 2.0, else CanProneAim() | `CZSealBody::CanProneAimNow()`, guess |
| 0x285760 | standing still in a stand/crouch/prone base anim (1, 18, 26) with the special anim set (0x48e068) bound: rebinds the saved set (+1128), stops the +1136 anim, clears the weapon timer | `CZSealBody::CheckRestoreAnimSet()`, guess |
| 0x285890 | the same restore, unconditional | `CZSealBody::RestoreAnimSet()`, guess |
| 0x2872c0 | IsCurrentBlend(animTypeJumpLand) or (animTypeJumpLandHard) | `IsLanding()`, guess from the zanim.h enum |
| 0x287350 | IsCurrentBlend(animTypeJumpLaunch) or (animTypeJumpFall) | `IsJumping()`, guess (the prototype's `jumping` test in ComputeNextPosition) |
| 0x2873e0 | IsCurrentBlend of the AnimTypes globals found by "Land forward"/"Land backwards" (new globals) | `IsLandingFromFall()`, guess |
| 0x287470 | IsCurrentBlend(AnimTypes::FallForward01) or (FallBackward01) (strings "Fall forward"/"Fall backwards") | `IsFalling()`, guess (the prototype's `falling` test) |
| 0x287500 | `return 0` | unnamed: no basis |
| 0x288720 | true if the AnimType is anywhere on the blend stack (+304) | `CZSealBody::IsBlendInStack(AnimType) const`, guess |
| 0x2b3a00, 0x2b3a20, 0x2b3a50 | set / clear / get entry index + 1 of a table at +2092 bounded by +2088; callers PickupItem, RemotePickupItem, DropItem | guess: CZKit slot accessors |
| 0x2b3a80 | zeroes +24/+28; called by DecrZoomState | guess: a zoom-offset reset |

Owner proposals: the 12 rows 0x25f0c0-0x260860 to `seal_ai.cpp` (they sit inside its release
range, and `__sinit_seal_ai.cpp` calls 0x260860). The four rows 0x2b3a00-0x2b3a80 to
`seal_kit.cpp`, a guess: they sit between seal_ik's last function and
`CZKit::ResetScreenOffsetXY`, and the offsets fit the grown release CZKit.

Removed: HasSniperRifle and InGuardRegion (inline; the corpse-sighting test moved from
HandleEvent to 0x2608c0), IsAlive and GetEntity (inline; folded into 0x300940),
SetReturnVelocity (the grenade throw was rebuilt around 0x264240/0x2770c0/0x2772f0 and the
uncalled 0x264250-0x2644e0; its aim block is in 0x264600), IsCurrentBlend (inline everywhere).

## Still unsure

None of this list's rows. Open points:

- SetReturnVelocity ↔ 0x264600 (list d) is a possible but unlikely successor: it shares the
  ChooseLookDir/GetDirVec/rand aim block, but it has a different receiver, a different call site
  and no fire-parameter or projectile-launch part. List d's checker should look at it.
- The names of the three new CAiState virtuals and of most new functions (guesses above).
- 0x2608c0 (list e, mapped to CAiSCorpse::Tick) now sits inside seal_ai.cpp and contains the
  inlined HasSniperRifle/InGuardRegion test. That row is for list e's checker.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 36 | 33 | 3: 0x25f090 (CanPursue), 0x262720 (CAiSAnimate::Tick), 0x27a660 (StabBuddy) |
| removed | 8 | 6 | 2: CAiSAnimate::Tick (0x262720), is_throwtype (0x2667f0) |
| unsure | 2 | 2 (counterparts right; now deviating) | 0 |
| weak (slot-only) | 2 | 1 (AbortPeek) | 1: StabBuddy belongs to 0x27a660, not 0x27a890 |
| exact (not checked) | 30 | - | 1 seen in passing: 0x25f0a0 is not CanPursue |

Sample: 15 of 15 deviating rows are the same function on both sides.

What misled it:

- CanPursue (0x25f090 / 0x25f0a0): two byte-identical `return 1` functions next to each other.
  The tool chose by position (flag `ambiguous`) and took the wrong one. Only the vtable slots tell
  them apart.
- CAiSAnimate::Tick (similarity 0.237, grams 0.026): the state's fields moved, so the similarity
  was too low. The slot held two release functions against one prototype function, so it was not a
  1-to-1 gap. It has no direct callers. The CAiSAnimate vtable slot settles it.
- StabBuddy: the release added an align-then-callback wrapper. ExecuteAction_KnifeAttack calls
  the wrapper where the prototype called StabBuddy, so the call-list slot pointed at the wrapper
  (`slot-only`). The body is reached only through the thunk 0x27aac0. For RestrainBuddy the
  tool kept the body (by position), so it treated the two parallel cases differently.
- is_throwtype: equal size and shape with only immediates changed (similarity 0.938, shape 1.0),
  yet not paired. It moved about 6 KB away (after ComputeProjectileFireParams), and its only
  caller changed (SetReturnVelocity → AI_FIREPARAMS::setup), so neither slot nor caller evidence
  reached it.

What would help:

- Pair through vtables. Find each release vtable by its paired entries, and pair the unpaired
  entries slot by slot. This settles 0x262720 and 0x25f090/0x25f0a0, and it marks inserted
  slots.
- Follow `j <target>` thunks whose address is passed as a callback (here to `AlignForPickup`).
  When a caller's call moves to a new wrapper that passes such a thunk, the thunk's target is the
  old callee's body.
- Pair unpaired functions of equal size and shape (`imm-only`) anywhere in the same owner file,
  not only in the slot.

The sheet was the starting point. Its slot lines for new and removed rows pointed straight at the
CAiSAnimate pair. What was missing: no data references by function address (vtables,
callbacks), so the four corrections above needed a data scan. The "unpaired on the other side"
list for the big seal_ai gap held 59 entries and was no help there.
