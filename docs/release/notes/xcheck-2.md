# Stage 2 cross-check 2: gamez/zSeal pairs, list b (2026-11-26)

The cross-check (brief step 4) of every committed pair of the list `gamez-zSeal-pairs-b`: the owner
files seal_ai.cpp, seal_body.cpp, seal_airesponse.cpp, seal_sensors.cpp, seal_aifollow.cpp,
ai_target.cpp, seal_command.cpp, seal_dyn.cpp and seal_ik.cpp. 399 pairs (254 deviating, 145 exact;
evidence: call-deviating 146, vtable-slot 104, exact 67, exact-position 25, settled 24, call 22,
table-entry 5, position 5, string 1). The uncertain rows of these files were settled earlier
(`zSeal-a.md` to `zSeal-f.md`); they were not re-checked, and no sample was taken. Pairing produced by
`socom-release-compare-c1` (`python tools/release/compare.py`); checked by `socom-release-xcheck-2`,
who did not write the tool, at HEAD 2bf42336. Both images were decoded with the release tools; Ghidra
was not used.

## Method

For every pair: the callers (`jal`/`j`), the address loaders (`lui`/`addiu`), the vtable slots and the
data words that hold it, on both sides, the prototype ones mapped through the map. A caller found on
one side only was looked up in that caller's own aligned call/load sequence (both sides, prototype
mapped) to see what stands at the call site on the other side: nothing (a call added, dropped or
inlined) or another function (a replacement, the place where crossed pairs show). Every vtable with a
slot in these files was aligned slot by slot through the tool's table pairing, so a uniform insertion
shifts the slots and is not counted as a difference. Also compared: each pair's own ordered calls and
loads, the vtables each function stores (22 constructors and destructors), the scheduler
registrations and callback pointers (11 address-loaded functions), the static-init table entries (8),
and the byte twins (53 pairs with a twin, scored by shared callers; ties went to the vtable slot or the
call site).

## Results

- Pairs compared: 399. Every pair has at least one reference on some side (caller 240, vtable 136,
  loader 11, data word 8, caller and vtable 4).
- Before the slots were aligned, 139 pairs differed; 66 of those differed only by the uniform CAiState
  shift. After alignment: 73 pairs with 225 differences (214 callers, 2 loaders, 9 vtable slots).
  105 of the caller differences have a different function at the same aligned call site; all were
  looked at.
- Wrong pairs: **none**.

### Vtables

All 35 tables with a slot in these files were aligned. The CAiState family (CAiState and 28 states)
gained slot 1 (after OnSignal; base 0x25f050) and slots 10-11 (base 0x25f0a0, 0x25f0b0) before the
destructor: a uniform shift, the paired slots are the same after it. The CZSealBody CBody subobject
table (-272) gained slot 3 (new 0x25ef90, the `this - 272` thunk that jumps to 0x288ad0) and slot 6 (`BodySetState__10CZSealBodyFi`
0x288ad0): BodySetState became virtual (CBody slot 3, 0x1e3bd0), and the prototype's direct calls of
it became virtual calls. CZSealBody's own table (the entity family's insert after PostTick, and slots
11-12) holds no function of these files. The other slot differences are overrides added or dropped,
not pair changes:

| table | slot (release) | prototype | release |
|---|---|---|---|
| CAiSGrenade | 6 CanAttack | own override 0x26c750 | base CanAttack 0x276b50 (override gone) |
| CAiSAction | 1, 3, 4, 6, 7, 8, 10, 11 | base GetStatus, CanPushAiState, CanAttack, CanScan, CanPursue | new overrides 0x2675c0, 0x267330, 0x2676f0, 0x2676c0, 0x2676e0, 0x2676d0, 0x267650, 0x2676b0 |
| CAiSDeploy, CAiSBreach, CAiSScript, CAiSRestrained, CAiSSurrender | 4 CanPushAiState | base 0x25f070 | new overrides |
| CAiSBreach 10, CAiSScript 1 | new slots | - | own overrides 0x2ec870, 0x2ed130 instead of the base |
| CSealCtrlAi | 24 Dump | own 0x269430 | base `Dump__9CSealCtrlFv` 0x2735b0 |
| CRemoteCtrl | 21, 22 | base OnMissionStart/End | new overrides 0x2e01d0, 0x2e01e0 |
| CAiSCorpse | - | 0x472900 | table gone (class removed) |

The 22 constructors and destructors store the paired tables in the same order (state destructors:
own table, then CAiState).

### Differences looked at

Most of the 214 caller differences are calls that moved or were inlined: the prototype's inline
blend-stack loops (`Top` + `PopBlend`, sometimes `BodySetState`) became calls of `ClearStack` and
`ClearToBase` in about 30 body functions; the prototype's out-of-line `Debug`/`Output` and
`GetEventString` calls are gone; double-precision helper calls became `rand` or inline code; the new
target-validity helper 0x300940 appears in front of the CAiTarget getters; the removed CAiSCorpse is a
missing caller in several rows. The ones that are not plainly that:

| pair (release <- prototype) | difference | reading |
|---|---|---|
| 0x266250 <- 0x25e6a0 UpdateThrowFireParams, 0x265e10 <- 0x25e360 ComputeThrowFireParams | AttackTick +0x111c calls Update where the prototype (+0x10ec) called Compute and FireWhenReady | code change: the first Compute call (+0x1018 / +0xff4) and FireWhenReady (+0x113c) still line up; sizes differ (0x130 / 0x440) |
| 0x269d20 <- 0x261ac0 SetStanceDelayed, 0x269eb0 <- 0x261d00 SetStance | CAiSGoto::OnSignal (both calls) and the second call of CAiSRestrained::Tick use SetStanceDelayed where the prototype used SetStance | code change: SetStance is an exact pair and keeps its other callers |
| 0x2683b0 <- 0x260000 GetAiAware, 0x268990 <- 0x260420 SetAiAware(f,Ui), 0x268820 <- 0x2602d0 SetAiAware(AI_AWARE,pnt) | the prototype's GetAiAware + SetAiEvent + SetAiAware(f,Ui) blocks in CAiSGrenade::Tick, OnWeaponEvent and OnWeaponHit became one call (SetAiAware(AI_AWARE,pnt), FindTarget, new 0x25f0c0); SetAiAware(AI_AWARE,pnt) and AcquireAiAware now call SetAiAware(f,Ui) where the prototype inlined it | refactor; 0x268990 is the prototype body (masks 1/2/4, `_saturate` into +0xc0 and +0xc4) behind a new guard |
| 0x287e60 <- 0x27cbf0 CZSealBody::PopBlend | ~CZSealBody calls CBody::PopBlend 0x1e3440 where the prototype called CZSealBody::PopBlend | code change; PopBlend's own calls line up (22 of 23) |
| 0x273670 <- 0x2695d0 PlayAnim(AnimType) | PlayAnim(const char*) calls it instead of inlining it | inlining change |
| 0x2696e0 <- 0x261460 GetDefaultRouteType | the second GetAiState call is the non-const 0x2efa60 | code change in the caller, not a pair issue |
| 0x27b0e0 <- 0x26f750 CrouchToPickupBuddy | the prototype's caller OnActionButton now calls new 0x253700, which calls it | new wrapper; the body's 23 calls and its three callback loads (PickupBuddyCallback, CrouchToPickupBuddyCallback) line up |
| 0x300260 <- 0x2e9b90 GetTimeVisible | AttackTick calls new 0x26bc70, which calls it; the body calls new 0x300940 | the prototype's inline validity test (+0 to +0x20) moved into 0x300940; the rest matches |
| 0x2fd120 <- 0x2e6930 CAiSStunResponse::Tick, 0x17d930 <- 0x25aba0 `Rfloat::operator float` | the release calls the Rfloat conversion where the prototype inlined `rand` | inlining change |
| 0x271290 <- 0x2675e0 CSealCtrlAi::PreTick | calls LadderClimbTick (the prototype's PathFollowTick did) | the move settled in zSeal-b/f |
| 0x2ef610 CanPushAiState (outside the list) | no longer calls GetAiStateEnum 0x275fb0 | inlined |

### Twins

53 pairs have a byte twin. None is beaten by another twin on shared callers. Ties: the empty and
one-instruction virtuals (CanAttack, CanScan, CanPursue, GetScriptResponse, IsPlayer, OnActionButton,
the Perform*Actions, ...) are each decided by their vtable slot, and all slots agree after alignment;
the std list/deleter constructors and destructors (0x275290, 0x276f70, 0x2c41c0) by their callers;
OnSignal of CAiSNoAmmo / CAiSHostage by slot 0 of their tables. The four 64-byte CSTable static
initializers of these files (seal_command, seal_ik, seal_aifollow, seal_airesponse) differ only in
their static's address; their objects and the init-table entries are in the same order on both sides.

## Wrong pairs

None.

## Settled pairs (tool input)

The four pairs the tool made by position alone, now with a basis:

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x268990 | 0x260420 | same body (masks 1/2/4, _saturate into +0xc0/+0xc4) behind a new guard; now called by SetAiAware(AI_AWARE,pnt), AcquireAiAware and OnDeath where the prototype inlined it | socom-release-xcheck-2 | 2026-11-26 | src/gamez/zSeal/seal_ai.cpp | |
| 0x27b0e0 | 0x26f750 | 23 aligned calls and the PickupBuddyCallback / CrouchToPickupBuddyCallback loads; its caller OnActionButton now goes through new 0x253700 | socom-release-xcheck-2 | 2026-11-26 | src/gamez/zSeal/seal_body.cpp | |
| 0x288ad0 | 0x27d240 | calls CBody::BodySetState as before; now virtual (slot 6 of the CZSealBody CBody subobject table, after CBody gained slot 3) | socom-release-xcheck-2 | 2026-11-26 | src/gamez/zSeal/seal_body.cpp | |
| 0x300260 | 0x2e9b90 | same body after the validity test moved into new 0x300940; AttackTick reaches it through new 0x26bc70 | socom-release-xcheck-2 | 2026-11-26 | src/gamez/zSeal/ai_target.cpp | |

## Still unsure

- 0x485320 <- 0x46dc20 `__sinit_seal_airesponse.cpp` (flagged ambiguous) and the new 0x485360: byte
  twins (CSTable constructor and registration; objects 0x522150 and 0x522180), both linked after
  seal_aiscan and before ai_target, where the prototype has only seal_airesponse. The CAiSAvoid block
  at 0x2f98b0-0x2fa760, which moved out of seal_aistate.cpp, is seal_airesponse's own code, not a new
  unit: its constants sit in seal_airesponse's two small-data pools (0x48e2ec-0x48e2f8 and
  0x48cee0-0x48cee8), continuing them in the unit's reverse order. So the new initializer belongs to a
  unit with no code of its own, and nothing tells whether it is linked before or after
  seal_airesponse. Twins undecidable: only the name is in doubt. The pair stands by position.

## How the tool did

- All 399 committed pairs hold. The five `position` rows are right: four are settled above and the
  fifth is the undecidable twin.
- Cross-check: 399 pairs compared, 225 differences looked at (73 pairs), 0 pairs wrong.
