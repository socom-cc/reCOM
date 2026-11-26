# Stage 2: gamez/zSeal, list e (2026-11-26)

List e of `gamez/zSeal` split 6 ways (`build/release/lists/gamez-zSeal-e.md`): owner files
seal_ai.cpp (release 0x262a10–0x2676d0), seal_aistate.cpp, seal_ex.cpp, seal_anim.cpp,
seal_aievent.cpp and seal_ctrl.cpp. It holds 40 uncertain rows (37 new, 3 removed; no weak pairs,
no unsure rows; 9 rows flagged `copy`), 15 sampled deviating rows out of 66, and 25 exact rows that
were not checked. Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`);
checked by `socom-release-check-seal-e`, who did not write the tool, at HEAD bfea625a. The check
sheet (`compare.py --sheet gamez/zSeal --list e`) was the starting point; both images were
disassembled with the release tools, callers found by scanning both images for `jal`/`j`, data
words and `lui`/`addiu` pairs, and gp-relative statics traced. Ghidra was not needed.

What settled rows, in the order it was used: the CAiState-family vtables (CAiSGrenade, CAiSDeploy,
CAiSAction, CAiSBreach, CAiSScript, CAiSHostage, CAiSPickup, CAiSCQBAttack against the release
tables at 0x489b70, 0x489bb0, 0x489bf0, 0x489f30, 0x489f70, 0x489ff0, 0x48a030, 0x489e70); the
call site inside a paired caller; function pointers loaded by `lui`/`addiu` (callback records);
function-local statics; byte twins of template instances.

The release CAiState vtable, as the subclasses show it: prototype slots +0x08 … +0x2c map to
release +0x08, then a new slot at +0x0c (3), Tick … GetScriptResponse at +0x10 … +0x2c, two new
slots at +0x30 (12) and +0x34 (13), the destructor at +0x38. This agrees with list b.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x25c860 `SetReturnVelocity__11CSealCtrlAiFP12CZProjectileP6CPnt3Db` | removed | corrected to 0x264600 | see 0x264600 |
| 0x264240 | - | new, copy | confirmed | `return this`; called three times by CAiSGrenade::Tick on CAiSAnimate +52 (the end of the new list at +48); its 112 prototype twins are other types' members, paired elsewhere |
| 0x264250 | - | new | confirmed | callback stored by CAiSGrenade::Tick (`lui`/`addiu` at 0x263f78) in a record on CAiSAnimate's list |
| 0x2643a0 | - | new | confirmed | the same, at 0x263fb0 |
| 0x264440 | - | new | confirmed | the same, at 0x263f3c |
| 0x2644e0 | - | new | confirmed | the same, at 0x263e90 |
| 0x264600 | - | new | corrected to 0x25c860 `SetReturnVelocity__11CSealCtrlAiFP12CZProjectileP6CPnt3Db` | the same two function-local statics (80.0, 150.0, first-use guards, same order), only in this function on both sides and in the release initialized but never read; the same opening (GetEntityById of the projectile's id, the ai +0x280 bit test) and the same random-aim block (ChooseLookDir from ai +228, GetDirVec, three `rand` ±0.2/0.4, Normalize); its only prototype caller CAiSGrenade::Tick lost both calls and calls 0x264600 once. Receiver changed (below) |
| 0x265e00 | - | new | confirmed | CAiSDeploy vtable +0x18 = CanPushAiState; the prototype CAiSDeploy used the base |
| 0x267330 | - | new | confirmed | CAiSAction vtable +0x14 = GetStatus (substate names "INIT" … "FAILED"); the prototype used the base |
| 0x2675c0 | - | new | confirmed | CAiSAction override of the new slot 3 |
| 0x267650 | - | new | confirmed | CAiSAction override of the new slot 12 |
| 0x2676b0 | - | new | confirmed | CAiSAction override of the new slot 13 |
| 0x2676c0 | - | new | confirmed | CAiSAction vtable +0x20 = CanAttack; the prototype used the base |
| 0x2676d0 | - | new, copy | confirmed | CAiSAction vtable +0x28 = CanPursue (`return 0`); the slot decides it; the prototype used the base |
| 0x277ce0 | - | new | confirmed | three new calls in BlendOverlayPreTick after each CBlendOverlay::Trigger, one in 0x27b620; nothing in the slot |
| 0x277ec0 | - | new | confirmed | called only by 0x2780f0 |
| 0x2780f0 | - | new | confirmed | new call in CZSealBody::Tick after HandleWeaponIntersect; takes the blend-smoothing block (quadW, SmoothAnims) that opened the prototype's Post, which the release Post no longer has |
| - | 0x283750 `InitMPBomb__9CSealCtrlFv` | removed | confirmed | inlined: release CSealCtrl::PreTick runs its code (GetReticuleAction, the 5.0 timer, bit 0x20, CanPlaceBomb) right before TickMPBomb, where the prototype called it |
| 0x2b3a00 | - | new | confirmed | CZKit table setter (+0x82c, index + 1); receiver body +1328 (the kit) at PickupItem / RemotePickupItem |
| 0x2b3a20 | - | new | confirmed | CZKit table clear, bounded by +0x828 |
| 0x2b3a50 | - | new | confirmed | CZKit table getter, bounded by +0x828 |
| 0x2b3a80 | - | new | confirmed | zeroes kit +0x18/+0x1c; DecrZoomState calls it on body +1328 |
| - | 0x2d8b30 `__ct__Q33std46list<P8CAiState,...>19generic_iterator<1>F...` | removed | confirmed | no byte twin for CAiState* in the release (only the CAiMap* and CEntity* instances); CAiSBreach::Tick and PopToAiState no longer call it |
| 0x2ec870 | - | new | confirmed | CAiSBreach override of slot 12 (as list b found) |
| 0x2ec8b0 | - | new | confirmed | CAiSBreach vtable +0x18 = CanPushAiState; the prototype used the base |
| 0x2ed130 | - | new | confirmed | CAiSScript override of slot 3 |
| 0x2ed1b0 | - | new | confirmed | CAiSScript vtable +0x18 = CanPushAiState; the prototype used the base |
| 0x2ee9e0 | - | new | confirmed | predicate passed by StateTick (`lui`/`addiu` at 0x2ee970) to 0x2f09f0 |
| 0x2eebd0 | - | new | confirmed | new call in UpdateStackFlags; no prototype counterpart |
| 0x2ef4f0 | - | new | confirmed | called only by new 0x26bc70 |
| 0x2ef9c0 | - | new | confirmed | new call in CAiSAvoid::Tick |
| 0x2f09f0 | - | new, copy, no owner | confirmed | new call at the end of StateTick, followed by `erase`; owner seal_aistate.cpp |
| 0x2f0ae0 | - | new, copy, no owner | confirmed | CAiState::Create constructs the CAiSAnimate list at +48 with it; owner seal_aistate.cpp |
| 0x2f0b00 | - | new, copy, no owner | confirmed | the same, for the list at +60; the two twins are told apart by these call sites |
| 0x2f0b20 | - | new, copy, no owner | confirmed | called only by 0x2f09f0; its prototype twin (remove_copy_if for list<CSched_Task*>) is the exact pair 0x30b830; owner seal_aistate.cpp |
| 0x2f2f30 | - | new, copy | confirmed | two new calls in HandleEvent on map +280; its three prototype twins are exact pairs in their own files |
| 0x2f2f50 | - | new | confirmed | two new calls in HandleEvent, each before 0x2f2f30; no near twin in either image |
| 0x2f9ba0 | - | new | confirmed | new call in CSealCtrl::SensorPreTick |
| 0x2f9cb0 | - | new | confirmed | called only by new 0x25fbf0 (stuck recovery) |
| 0x2fa470 | - | new | confirmed | called by new 0x2602e0 and by SensorPreTick |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x264a70 | 0x25d0c0 `OnSignal__11CAiSGrenade…` | yes | CAiSGrenade vtable +0x08 on both sides |
| 0x265b90 | 0x25e190 `CanDeployItem__10CAiSDeploy…` | yes | same caller (CAiSDeploy::Tick); one offset differs |
| 0x266be0 | 0x25ee30 `Tick__10CAiSAction…` | yes | CAiSAction vtable Tick slot (+0x0c → +0x10) |
| 0x277570 | 0x26cae0 `GetRootPos__10CZSealBody…` | yes | paired neighbours Post and SetVertical on both sides; same callees; the call moved from PostCheckDIDown into its new helper 0x2abe70 |
| 0x28f160 | 0x2838f0 `TickMPBomb__9CSealCtrl…` | yes | same caller and call site in CSealCtrl::PreTick |
| 0x28f2e0 | 0x283c00 `PerturbAimVector__9CSealCtrl…` | yes | slot +0x74 of the same four vtables |
| 0x28f770 | 0x2840d0 `GetThrottleFromSpeed__9CSealCtrl…` | yes | the prototype's three callers, plus FollowTick |
| 0x2eb1f0 | 0x2d7bc0 `OnSignal__13CAiSCQBAttack…` | yes | CAiSCQBAttack vtable +0x08 |
| 0x2eb640 | 0x2d8000 `Tick__10CAiSBreach…` | yes | CAiSBreach vtable Tick slot |
| 0x2ecdb0 | 0x2d9130 `CanPursue__10CAiSScript…` | yes | CAiSScript vtable CanPursue slot (+0x24 → +0x28) |
| 0x2ee250 | 0x2da2d0 `Tick__11CAiSHostage…` | yes | CAiSHostage vtable Tick slot |
| 0x2ee5f0 | 0x2da910 `OnSignal__10CAiSPickup…` | yes | CAiSPickup vtable +0x08 |
| 0x2ef830 | 0x2dba40 `ClearAiState__11CSealCtrlAi…` | yes | the same six callers |
| 0x2efa10 | 0x2dbd20 `GetAiState__11CSealCtrlAiCFv` | yes | same callers; imm-only |
| 0x2efab0 | 0x2dbdc0 `Signal__8CAiState…` | yes | all seven prototype callers call it, plus CAiSBreach::Tick and CAiSGoto::Tick |

Layout, plainly shown by settled rows:

- CAiSAnimate (72 bytes, allocated in CAiState::Create) has two new lists at +48 and +60; CAiSGrenade::Tick
  fills them with callback records (function pointer, the grenade state, a time).
- CSealCtrl: the MP bomb fields +0x154 … +0x169 are at +0x15c … +0x171 (InitMPBomb's code in PreTick).

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x264600 | 0x25c860 | the same two function-local statics (80.0, 150.0, guarded, same order), used by no other function on either side; same opening (GetEntityById of the projectile id, ai +0x280 bit) and random-aim block; the only caller CAiSGrenade::Tick lost both calls and calls it once; receiver now the grenade state, ai second | socom-release-check-seal-e | 2026-11-26 |

This contradicts list b's note, which confirmed SetReturnVelocity as removed and called 0x264600 an
unlikely successor. The pair is deviating with a changed signature: `this` is the CAiSGrenade state
(the callers' s4), the CSealCtrlAi is the second argument, and the results go into the state
(direction +0x4c, velocity +0x58, flag +0x3d) instead of onto the projectile. The projectile half
(GetInstance, SetPosition, GetNode → +0x1c) moved into the callbacks 0x264250, 0x2643a0, 0x264440
and 0x2644e0, and the aimed branch no longer computes fire parameters. Stage 3 should not carry the
mangled prototype name over unchanged: its class and parameters differ.

The tool gave 0x2f09f0, 0x2f0ae0, 0x2f0b00 and 0x2f0b20 no owner; they belong to seal_aistate.cpp
(their callers are StateTick and Create, and they sit between that file's last destructor and
seal_aievent.cpp's HandleEvent). For 0x2b3a00–0x2b3a80, seal_kit.cpp, as list b proposed; the
call sites make the receiver the CZKit (body +1328), which supports it. The other rows stand as
the map has them.

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x264240 | `return this`, on CAiSAnimate +52 | guess: the end/sentinel accessor of the new callback list's type (a template member) |
| 0x264250, 0x2643a0, 0x264440 | throw callbacks registered for the "Return throw grenade" sequence: build the hand node's world matrix (BuildMTW), rotate the velocity stored at grenade state +0x58 into it, and hand it to a new CZProjectile function (0x3304d0, 0x3305c0, 0x330620 respectively); 0x264250 also sets projectile +0x1c to the body node | unnamed: grenade-throw animation callbacks (guess) |
| 0x2644e0 | the same, using the body's matrix and the projectile's own position, then 0x3304d0 and the node | unnamed, as above |
| 0x265e00 | `CanPushAiState`: status +0x10 < 4 | `CAiSDeploy::CanPushAiState(AI_STATE, CSealCtrlAi*)`, from the vtable slot |
| 0x267330 | status +0x10 → "INIT", "CREEP", "PLAN", "WAIT", "GOTO", "ORIENT", "EXECUTE", "ACTION", "COMPLETE", "FAILED", else "unknown" | `CAiSAction::GetStatus() const`, from the slot |
| 0x2675c0 | slot 3: when the id matches +0x48, kind 1 clears it, kind 6 sets flag bits in +8; either way bit 0 of ai +0x3e8 is set | the CAiSAction override of list b's `OnNotify` (guess) |
| 0x267650 | slot 12: true while status < 6; otherwise, unless the fourth argument is set, true when a 7-bit field of the third argument is 3 or 5 | the CAiSAction override of list b's `CanAccept` (guess) |
| 0x2676b0 | slot 13: status < 6 | the CAiSAction override of slot 13 (no name basis) |
| 0x2676c0 | +0x48 == 0 | `CAiSAction::CanAttack() const`, from the slot |
| 0x2676d0 | `return 0` | `CAiSAction::CanPursue(CSealCtrlAi*) const`, from the slot |
| 0x277ce0 | for 21 anim pointers of the body (+0x26c …), calls new zBody 0x1e3e80 (body +272, anim id), which resets that active anim's state | guess: `CZSealBody::ResetWeaponAnims()` |
| 0x277ec0 | the same loop with new zBody 0x1e3c20 | guess: a sibling of 0x277ce0 |
| 0x2780f0 | blend smoothing for the weights at +0x120 and +0xfa8 (quadW, SmoothAnims, 0x277ec0); the first half is the block from the prototype's Post | guess: `CZSealBody::SmoothBlendWeights()` |
| 0x2b3a00, 0x2b3a20, 0x2b3a50 | set / clear / get entry index + 1 of the CZKit table at +0x82c, bounded by +0x828 | guess: CZKit slot accessors (owner seal_kit.cpp) |
| 0x2b3a80 | zeroes kit +0x18/+0x1c | guess: a CZKit zoom-offset reset |
| 0x2ec870 | slot 12: true when a 7-bit field of the third argument is 3 or 8 | the CAiSBreach override of slot 12 (list b) |
| 0x2ec8b0 | `CanPushAiState`: true, except state 3 while the substate +0x10 is 4 … 9 | `CAiSBreach::CanPushAiState(...)`, from the slot |
| 0x2ed130 | slot 3, as list b described | the CAiSScript override of slot 3 |
| 0x2ed1b0 | `CanPushAiState`: while bit 0 of +0x28 is set, refuses states 26 and 12 | `CAiSScript::CanPushAiState(...)`, from the slot |
| 0x2ee9e0 | predicate: a state of type 3 is deleted (virtual destructor) and removed | guess: a static predicate of StateTick |
| 0x2eebd0 | AI_STATE (0 … 29) → mask by jump table; UpdateStackFlags ANDs the masks over the stack | guess: `GetStateMask(AI_STATE)` |
| 0x2ef4f0 | if the state's bit is set in ai +0x3e0, finds that state on the AI stack (+976) and tests its flags +8 against a mask | guess: `CSealCtrlAi::AiStateHasFlags(AI_STATE, unsigned) const` |
| 0x2ef9c0 | with 2 or more states on the stack, the state below the top | guess: `CSealCtrlAi::GetPrevAiState()` |
| 0x2f09f0 | `std::remove_if` over the AI stack (find, then 0x2f0b20) | the MSL `remove_if` instance for `list<CAiState*>` iterators and a predicate pointer (from the body) |
| 0x2f0ae0, 0x2f0b00 | default constructors of CAiSAnimate's lists at +48 and +60 | `__list_deleter<T>` constructors for the two callback element types (not in the prototype) |
| 0x2f0b20 | `remove_copy_if`, byte-equal to the CSched_Task* instance | the MSL `remove_copy_if` instance for `list<CAiState*>` |
| 0x2f2f30 | `vector_imp::operator[]`, 12-byte elements, on the map's scanline vector (+280) | guess: the non-const `__vc__…vector_imp<CAiMap::scanline,…>FUi`, which the prototype had only as const (0x197020 is the const one) |
| 0x2f2f50 | bounds test of a CAiMapLoc against map +0x18/+0x1c | guess: `CAiMap::IsValidLoc(const CAiMapLoc&) const`, an inline emitted out of line |
| 0x2f9ba0 | sets status +0x10 = 3, +0x24, a direction at +0x38 (scaled by 1/t or normalized) and a timer at +0x34 | guess: a CAiSAvoid set-up (it sits in the CAiSAvoid block) |
| 0x2f9cb0 | picks an avoidance goal: is_moving, `rand`, AI-map cells, CanTravelLine, SetGoalPos | guess: `CAiSAvoid` goal choice, used by the stuck recovery |
| 0x2fa470 | decides whether one seal must yield to another (is_moving on both, their controllers, AiStateIs 3, the other's avoid target) | guess: `ShouldAvoid(...)` |

Not new, though the map has it as new: 0x264600 (SetReturnVelocity, above).

Really removed: InitMPBomb (inlined into CSealCtrl::PreTick) and the `list<CAiState*>` iterator
conversion constructor (its two callers no longer convert iterators).

Corrections to list b's note: slot 13 is overridden (CAiSAction, 0x2676b0), and slot 12 twice
(CAiSBreach and CAiSAction). 0x264250–0x2644e0 are not uncalled: CAiSGrenade::Tick stores them as
callbacks.

Hints from earlier lists that point outside this list: 0x2608c0 (the inlined HasSniperRifle /
InGuardRegion test) is now in list f; 0x271290, 0x271a70 and 0x2735b0 are no longer list e rows
(the first two are settled pairs; 0x2735b0 is outside this list's ranges). None was checked here.

## Still unsure

None of this list's rows. Open points:

- The names of most new functions (guesses above), and of the new CAiState virtuals in slots 3, 12
  and 13.
- The element types of CAiSAnimate's two new lists.
- The new CZProjectile functions 0x3304d0, 0x3305c0, 0x330620 and zBody 0x1e3e80, 0x1e3c20 are
  outside the module and were not looked at.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 37 | 36 | 1: 0x264600 is SetReturnVelocity |
| removed | 3 | 2 | 1: SetReturnVelocity (0x264600) |
| copy (within the above) | 9 | 9 | 0: each is decided by a vtable slot or a call site, and no prototype twin applies |

The sample: 15 of 15 deviating rows are the same function on both sides.

What misled it on SetReturnVelocity: the function moved from CSealCtrlAi to the grenade state, its
projectile half moved into four new callbacks and its fire-parameter branch was dropped, so it
shrank from 2072 to 1124 bytes and reached a similarity of 0.21. Its call site moved too: the
release calls it at the start of the throw, where the prototype called the empty `Debug` print.
The slot held seven unpaired release functions, so the one-to-one rule did not fire. The sheet
listed 0x264600 first among the slot's candidates.

What cost the most time: SetReturnVelocity, which an earlier list had confirmed as removed. The
function-local statics decided it. Suggestions:

- Count a function-local static (a gp-relative value with a first-use guard byte) referenced by a
  single function on each side as identity evidence for that pair.
- In the sheet, show function pointers loaded by `lui`/`addiu` as callers; the four callbacks
  showed "callers 0x262a10" but no call site, which an earlier checker read as uncalled.
