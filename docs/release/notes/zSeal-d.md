# Stage 2: gamez/zSeal, list d (2026-11-26)

List d of `gamez/zSeal` (split 6 ways): the owner files seal_ai.cpp (release 0x2676e0–0x267730 and
0x271240–0x276f70), seal_ailines.cpp, seal_dyn.cpp, ai_target.cpp and seal_command.cpp. It holds 42
uncertain rows (3 weak pairs, all `slot-only`; 3 exact rows flagged `identical-copy`; 20 new; 16
removed), 15 sampled deviating rows out of 47, and 58 exact rows that were not checked. Pairing
produced by `socom-release-compare-c1` (`python tools/release/compare.py`); checked by
`socom-release-check-seal-d`, who did not write the tool, at HEAD bfea625a. The map copy used
(`build/release/function-map.json`) agrees row for row with the tracked `function-map.tsv` at that
commit. Both images were disassembled with the release tools' decoder; callers were found by
scanning both images for `jal`/`j`, data words and `lui`/`addiu` pairs. Ghidra was not needed.

What settled rows, in the order it was used: the vtables (the CAiState family at release
0x489ae0–0x489c2c, `__vt__11CSealCtrlAi` against release 0x489c30); the call site in a paired caller
(CAiSEvent::Tick, CSealCtrl::PostTick, PathFollowTick, SetStanceDelayed); the callers of each
template instance on both sides; byte equality searched over every function of the other image.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x2676e0 | - | new | confirmed | CAiSAction's own CanScan: the CanScan slot (release +0x24) of the CAiSAction table; the prototype CAiSAction used CAiState's |
| 0x2676f0 | - | new | confirmed | CAiSAction's own CanPushAiState: slot release +0x18 of the CAiSAction table; the prototype used CAiState's |
| - | 0x269430 `Dump__11CSealCtrlAiFv` | removed | confirmed | the Dump slot (+0x68) of the CSealCtrlAi table holds CSealCtrl's Dump (0x2735b0); the valve loop and PrintPath are gone |
| 0x2737f0 | 0x2696e0 `PlayAnim__11CSealCtrlAiFPCc10SEAL_STATE` | deviating, slot-only | confirmed | the only caller on both sides is CAiSEvent::Tick, twice at the same places; FindAnimType first; the release calls the AnimType overload where the prototype inlined it |
| 0x275ed0 | - | new | confirmed | a second state test beside AiStateIs; called only by ComputeVisibility(CTarget*); nothing in the prototype slot |
| - | 0x26bdf0 `SetAiLogEnabled__11CSealCtrlAiFbb` | removed | confirmed | its only caller process_arguments is removed; the whole CAiLog class (ctor, dtor, Create, Write) is unpaired |
| - | 0x26be30 `GetAiLog__11CSealCtrlAiFv` | removed | confirmed | the same: the AI log is gone (list c found PutAiLog removed) |
| 0x276500 | - | new | confirmed | sets the valves `snd_hutchins`, `snd_bailey`, `snd_dimone`; the strings are not in the prototype |
| - | 0x26c1a0 `get_stance__6sealaiF11SEAL_STANCE` | removed | confirmed | its only caller SetStanceDelayed passed the name to a `Debug` print, which is gone with the call |
| 0x276b60 | 0x26c5f0 `GetScriptResponse__8CAiStateCFv` | exact, identical-copy | confirmed | every release CAiState-family table holds it in the GetScriptResponse slot (release +0x2c, prototype +0x28; one slot was inserted at +0x0c) |
| 0x276ca0 | - | new, copy | confirmed | `~__list_deleter` of a new element type (A); called only by ~CAiSAnimate for its list at +0x30 |
| 0x276d10 | - | new, copy | confirmed | `~__list_deleter` of a second new element type (B); called only by ~CAiSAnimate for its list at +0x3c |
| - | 0x26c750 `CanAttack__11CAiSGrenadeCFv` | removed | confirmed | the CanAttack slot of the release CAiSGrenade table holds CAiState's CanAttack (0x276b50) |
| - | 0x26c870 `_interp<f>__2aiFRCfRCffRf` | removed | confirmed | inlined at its only call site in PathFollowTick (the same 1 − t, multiply and multiply-add on the same two globals) |
| 0x276f90 | 0x2e36b0 `erase__…<6CPnt3D…>FQ…generic_iterator<0>Q…generic_iterator<0>` | exact, identical-copy | corrected to new | erase(first, last) of list<A>; its only caller is the new dtor 0x276ca0. Its prototype twin's only caller is ~color_stack, and the release has no list<CPnt3D> at all (below) |
| - | 0x2e3440 `insert__…<6CPnt3D…>` | removed | confirmed | callers PushLineColor and `__sinit_seal_ailines.cpp`; both now use a plain two-entry CPnt3D array; no release function has its bytes |
| - | 0x2e3590 `first__…compressed_pair_imp<…number<Ui,1>,P…node,1>CFv` | removed | confirmed | called only by the removed insert |
| - | 0x2e35a0 `second__…compressed_pair_imp<RQ23std74allocator<…>…>CFv` | removed | confirmed | the same |
| - | 0x2e35b0 `__ct__…compressed_pair_imp<…number<Ui,1>,P…node,1>FRC…` | removed | confirmed | the same |
| - | 0x2e35c0 `__ct__Q23std50__list_deleter<6CPnt3D,…>Fv` | removed | confirmed | called only by the prototype `__sinit_seal_ailines.cpp`; the release one builds no list |
| - | 0x2e35e0 `__dt__Q22ai11color_stackFv` | removed | confirmed | registered only by the prototype `__sinit_seal_ailines.cpp`; the release registers no destructor for the colour stack |
| - | 0x2e3680 `__ct__…generic_iterator<0>FP…node_base` | removed | confirmed | called only by ~color_stack |
| - | 0x2e3690 `__ct__…generic_iterator<0>FP…node` | removed | confirmed | the same |
| - | 0x2e36a0 `tail__Q23std50__list_deleter<6CPnt3D,…>Fv` | removed | confirmed | the same |
| 0x277040 | 0x2e33c0 `erase__…<6CPnt3D…>FQ…generic_iterator<0>` | exact, identical-copy | corrected to new | erase(it) of list<A>; its only caller is CAiSAnimate::Tick (list at +0x30). Its prototype twin's only caller was PopLineColor, which no longer erases anything |
| 0x2770c0 | - | new | confirmed; owner seal_ai.cpp | insert of list<A>, element of 12 bytes copied float/word/word; callers CAiSGrenade::Tick (three times); no prototype insert has its bytes |
| 0x277210 | - | new, copy | confirmed; owner seal_ai.cpp | `first` accessor of list<A>: called by 0x2770c0 where the CPnt3D insert called `first` |
| 0x277220 | - | new, copy | confirmed; owner seal_ai.cpp | `second` accessor of list<A>, by the same position |
| 0x277230 | - | new, copy | confirmed; owner seal_ai.cpp | compressed-pair copy constructor of list<A>, by the same position |
| 0x277240 | - | new, copy | confirmed; owner seal_ai.cpp | erase(first, last) of list<B>; only caller the dtor 0x276d10 |
| 0x2772f0 | - | new | confirmed; owner seal_ai.cpp | insert of list<B>, element of 16 bytes (float, float, word, word); caller CAiSGrenade::Tick |
| 0x277450 | - | new, copy | confirmed; owner seal_ai.cpp | `first` of list<B> (called by 0x2772f0) |
| 0x277460 | - | new, copy | confirmed; owner seal_ai.cpp | `second` of list<B> |
| 0x277470 | - | new, copy | confirmed; owner seal_ai.cpp | compressed-pair constructor of list<B> |
| 0x28f120 | - | new, no owner | confirmed | compares the CSealCtrl menu state byte (+0x221, the byte Get/SetMenuState use) with an argument; callers CMission::Tick and the new 0x1f9210, on the player's controller |
| 0x297cc0 | - | new, no owner | confirmed | ladder test; the prototype has one caller of GetLadderByIndex (LadderClimbTick), the release three |
| 0x297d50 | - | new, no owner | confirmed | ladder release; called by CZSealBody OnDeath, PreTick, the destructor, FlingBody and PopBlend |
| 0x297df0 | - | new, no owner | confirmed | fire-readiness test; callers CSealCtrl::PreTick and CZKit::HandleFireWeapon; nothing in the prototype slot |
| - | 0x2e2f80 `second__…compressed_pair_imp<Q23std74allocator<…>,…node_base,1>Fv` | removed | confirmed | called only by the prototype `__sinit_seal_ailines.cpp` (the list's end node) |
| 0x2f83d0 | 0x2e3340 `PopLineColor__2aiFv` | deviating, slot-only | confirmed | the only caller on both sides is CSealCtrl::PostTick, after PushLineColor, the two calls 0x30 apart on both sides; now copies the saved colour back instead of erasing a list node |
| 0x2f8410 | 0x2e3380 `PushLineColor__2aiFRC6CPnt3D` | deviating, slot-only | confirmed | the same caller and place; still returns 1; now saves the current colour and stores the new one |
| 0x300940 | - | new | confirmed | a CAiTarget method (`this` is CSealCtrlAi +0x574, the receiver of CAiTarget::Tick and GetTimeSinceLastSighting); 78 call sites, among them IdleTick, which had nothing at that place |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x272170 | 0x2682e0 `GetAiNetState__11CSealCtrlAiCFv` | yes | vtable slot +0x6c of CSealCtrlAi on both sides; operations 1.000 |
| 0x2723c0 | 0x268530 `PostTick__11CSealCtrlAiFf` | yes | vtable slot +0x3c on both sides; the same call sequence plus two new calls |
| 0x2735b0 | 0x2694f0 `Dump__9CSealCtrlFv` | yes | slot +0x68 of the CSealCtrl, CSealCtrlCopy, CRemoteCtrl and CSealCtrlSquirm tables on both sides |
| 0x273890 | 0x269850 `OnStateChange__11CSealCtrlAiF10SEAL_STATE10SEAL_STATE` | yes | vtable slot +0x64 on both sides |
| 0x2738f0 | 0x2699b0 `OnDeath__11CSealCtrlAiFv` | yes | vtable slot +0x18 on both sides |
| 0x2741a0 | 0x26a0a0 `OnWeaponHit__11CSealCtrlAiFPQ23zdb15IntersectStructP12CZProjectile` | yes | vtable slot +0x4c on both sides |
| 0x274390 | 0x26a290 `OnWeaponEvent__11CSealCtrlAiFP12CZProjectileUiPv` | yes | vtable slot +0x44 on both sides |
| 0x275060 | 0x26aed0 `Initalize__11CSealCtrlAiFv` | yes | vtable slot +0x40 on both sides |
| 0x275350 | 0x26b1c0 `__ct__11CSealCtrlAiFv` | yes | the same two callers (ftsCreateSeal, AcquireRemoteAi) |
| 0x276a10 | 0x26c4b0 `get_mode__6sealaiFPCc` | yes | the same single caller (CTSetMode::Parse) |
| 0x276bd0 | 0x26c660 `CanAttack__10CAiSPursueCFv` | yes | the CanAttack slot of the CAiSPursue table (prototype +0x1c, release +0x20) |
| 0x276bf0 | 0x26c680 `__dt__11CAiSAnimateFv` | yes | the destructor slot of the CAiSAnimate table (prototype +0x2c, release +0x38) |
| 0x28dfd0 | 0x2825e0 `IssueCommand__10CZSealBodyFP10CZSealBody10FT_COMMANDPvb` | yes | the same callers (AiOrdersPacketHandler twice, CSealUnit::Tick, CSealUnit::IssueCommand, SetFormation twice, FollowTick); IssueCommand has one call site more |
| 0x2fff60 | 0x2e99e0 `OnSetVisible__9CAiTargetFb` | yes | the same caller, OnSetTargetVisible of CSealCtrlAi, twice |
| 0x3000e0 | 0x2e9ad0 `Tick__9CAiTargetFP7CEntityf` | yes | the same two callers (CSealCtrlAi::PreTick, CTurret::Tick) |

Layout, plainly shown by settled rows:

- The CAiState family's vtables have one new slot at +0x0c (between OnSignal and Tick; CAiState's
  default is 0x25f050) and two before the destructor (+0x30, +0x34); every later slot moves by 4,
  then by 12 for the destructor.
- CAiSAnimate has two new `std::list` members, at +0x30 (element A) and +0x3c (element B): its
  destructor destroys both. CAiSGrenade::Tick fills them, and CAiSAnimate::Tick calls an element's
  function pointer and then erases it from the list at +0x30.
- The line-colour stack of seal_ailines.cpp is no longer a `std::list<CPnt3D>`. It is two
  CPnt3D globals (current colour and saved colour), set to (1, 0, 0) by `__sinit_seal_ailines.cpp`
  (the prototype pushed 127). PushLineColor saves and sets the colour, and PopLineColor restores it.

Just outside the list (not settled here):

| release | map | finding |
|---|---|---|
| 0x25a8d0 / 0x25a6d0 | deviating `PostTick__10CZSealBodyFf` / new | the map is right, and list a's note is wrong on this point. CEntity::PostTickAll (release 0x1f05c0) still calls slot +0x20 in its loop where the prototype called PostTick. After that loop it runs a new second loop that calls +0x24 and then +0x0c. So +0x20 (0x25a8d0) is PostTick, and the new virtual is +0x24 (0x25a6d0), not a slot between PrePostTick and PostTick. For the seal.cpp check |
| 0x1f38f0 … 0x1f3940 | the CEntity empty virtuals | by slot (CZSealBody's PreTick 0x25bcd0 is in +0x10): 0x1f3940 PreTick, 0x1f3930 Tick, 0x1f3920 PostPreTick, 0x1f3910 PrePostTick, 0x1f3900 PostTick, 0x1f38f0 the new +0x24 virtual. The map has them one place off (0x1f3930 PreTick … 0x1f38f0 PostTick, 0x1f3940 new). The bodies are equal, so only the names are wrong. For the zEntity check |
| 0x264600 | new | the hint that it took over part of SetReturnVelocity was not tested: the row is not in this list. Its similarity to SetReturnVelocity is 0.183, and its only caller is CAiSGrenade::Tick |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x276f90 | new | erase(first, last) of a new list element type; only caller the new list dtor 0x276ca0 called by ~CAiSAnimate; the release has no list<CPnt3D> | socom-release-check-seal-d | 2026-11-26 |
| 0x277040 | new | erase(it) of the same new list; only caller CAiSAnimate::Tick (list at +0x30); PopLineColor no longer erases | socom-release-check-seal-d | 2026-11-26 |
| removed | 0x2e36b0 | list<CPnt3D>::erase(first, last): its only caller ~color_stack is gone; the colour stack is an array in the release | socom-release-check-seal-d | 2026-11-26 |
| removed | 0x2e33c0 | list<CPnt3D>::erase(it): its only caller PopLineColor no longer uses a list | socom-release-check-seal-d | 2026-11-26 |
| 0x276b60 | 0x26c5f0 | GetScriptResponse slot of every CAiState-family table (release +0x2c, prototype +0x28) | socom-release-check-seal-d | 2026-11-26 |
| 0x2737f0 | 0x2696e0 | only caller CAiSEvent::Tick on both sides, twice at the same places; FindAnimType first | socom-release-check-seal-d | 2026-11-26 |
| 0x2f83d0 | 0x2e3340 | only caller CSealCtrl::PostTick on both sides, after PushLineColor | socom-release-check-seal-d | 2026-11-26 |
| 0x2f8410 | 0x2e3380 | only caller CSealCtrl::PostTick on both sides, before PopLineColor; returns 1 on both | socom-release-check-seal-d | 2026-11-26 |

Owners the tool did not give or gave wrongly: 0x276f90 and 0x277040 belong to seal_ai.cpp, not
seal_ailines.cpp. So do 0x2770c0–0x277470, which the tool gave no owner: their callers are
CAiSAnimate and CAiSGrenade, and they sit between seal_ai.cpp's last function (0x276f70) and
seal_anim.cpp's first (0x277480). 0x28f120 sits between seal_command.cpp and seal_ctrl.cpp, and
0x297cc0, 0x297d50 and 0x297df0 sit between seal_dyn.cpp and seal_env.cpp. Both placements are
guesses: seal_ctrl.cpp for 0x28f120, beside the other menu-state accessors, and seal_env.cpp for
the three CZSealBody functions, beside CanClimbLadder.

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x2676e0 | returns whether +0x48 is 0 | `CanScan__10CAiSActionCFv` (the vtable slot and the table's class) |
| 0x2676f0 | state 25: true; state 3: whether +0x48 is 0; otherwise false | `CanPushAiState__10CAiSActionF8AI_STATEP11CSealCtrlAi` (the vtable slot and the table's class) |
| 0x275ed0 | true when the current AI state's enum (+0x0c) is the given one and its flags (+0x08) share a bit with the mask | guess: `AiStateIs__11CSealCtrlAiCF8AI_STATEUi`, an overload of the neighbouring AiStateIs |
| 0x276500 | `(CSealCtrlAi*, value)`: with no seal, sets all three teammate valves `snd_hutchins`, `snd_bailey`, `snd_dimone` to the value; otherwise only the one picked by the seal's +0x284 (1, 2, 3); calls MakeCallbacks when a valve changes. Callers OnDeath, InitAiBrain, AcquireDatabaseHandles | guess: `SetTeammateSoundValve(CSealCtrlAi*, VALVE_STATE)` |
| 0x276ca0, 0x276d10 | `~__list_deleter` for elements A and B | the MSL member name for those element types |
| 0x276f90, 0x277040, 0x2770c0, 0x277210, 0x277220, 0x277230 | list<A>: erase(first, last), erase(it), insert, `first`, `second`, the compressed-pair constructor | the MSL member names. A is 12 bytes: a float, a function pointer and its argument (the seal), as CAiSGrenade::Tick builds it and CAiSAnimate::Tick calls it; the meaning is a guess (a timed callback) |
| 0x277240, 0x2772f0, 0x277450, 0x277460, 0x277470 | list<B>: erase(first, last), insert, `first`, `second`, the compressed-pair constructor | the MSL member names; B is 16 bytes: two floats, a function pointer and its argument (a guess, as for A) |
| 0x28f120 | `this->+0x221 == arg`: the menu state test; CMission::Tick asks it of the player's controller for states 2, 3, 4 … | guess: `MenuStateIs__9CSealCtrlF10MENU_STATE` |
| 0x297cc0 | `(CZSealBody*, ladder)`: true when the seal's ladder index (+0xf8a) is valid and GetLadderByIndex of it is the given ladder | guess: `CZSealBody::IsOnLadder(CLadder*)` |
| 0x297d50 | when the ladder index is valid, decrements that ladder's count at +0x1c and resets the index | guess: `CZSealBody::ReleaseLadder()` |
| 0x297df0 | false unless the entity flag (+0xdd bit 3) is set, the top animation blend is none of ten anim types, CanFire() holds, +0xf86 bit 5 is clear and the stance (+0x11d) is not 6 | guess: `CZSealBody::IsReadyToFire()` |
| 0x300940 | the target entity is set, flagged (+0xdd bit 3) and in state 2; when its controller is an AI (virtual IsAi, then GetSealCtrlAi), neither bit 0 nor bit 1 of that AI's +0x281 is set | guess: `CAiTarget::IsTargetValid() const` |

Really removed: CSealCtrlAi::Dump (CSealCtrl's Dump is no longer overridden), SetAiLogEnabled and
GetAiLog (the AI log class is gone), sealai::get_stance(SEAL_STANCE) (only fed a removed debug
print), CAiSGrenade::CanAttack (the base is used), `ai::_interp<float>` (inlined into
PathFollowTick), and the whole `std::list<CPnt3D>` family of seal_ailines.cpp with
`ai::color_stack::~color_stack`: 12 rows (2e2f80, 2e33c0, 2e3440, 2e3590, 2e35a0, 2e35b0, 2e35c0,
2e35e0, 2e3680, 2e3690, 2e36a0, 2e36b0). The colour stack became two CPnt3D globals.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions above are guesses (except the two CAiSAction overrides).
- The element types A and B of CAiSAnimate's new lists, and the owners of 0x28f120 and
  0x297cc0–0x297df0 (file boundaries).

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| weak pairs (slot-only) | 3 | 3 | 0 |
| exact, identical-copy | 3 | 1 | 2: 0x276f90 and 0x277040 are not the list<CPnt3D> erases |
| new | 20 | 20 | 0 (owner missing on 13 rows) |
| removed | 16 | 16 | 0 |

The sample: 15 of 15 deviating rows are the same function on both sides.

What misled it: `__list_deleter::erase` compiles to the same bytes for every element type. The two
release erases matched the prototype's CPnt3D ones, which no other evidence claimed. The tool paired
them by bytes alone (`global`, flagged `ambiguous, identical-copy, moved`). Their callers decide:
the prototype twins are called only by the colour stack (PopLineColor, ~color_stack), and the
release ones only by CAiSAnimate code. The rest of that list<CPnt3D> family has no release
counterpart. Suggestions:

- Do not pair an `identical-copy` template instance when none of its callers is paired with a
  caller of the prototype twin, and when the twin's siblings in the same family (insert, ctor,
  dtor) are all removed.
- Give template instances the owner of their callers and neighbours. 9 of the 13 new rows without
  an owner (0x2770c0–0x277470) sit inside seal_ai.cpp's code, and only seal_ai.cpp calls them. The
  other 4 sit on file boundaries.

What cost the most time: settling which slot of the CZSealBody table is new (outside the list),
which needed the entity tick loop, and naming the twelve template rows, whose prototype twins are
paired elsewhere.
