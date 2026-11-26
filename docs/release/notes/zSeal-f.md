# Stage 2: gamez/zSeal, list f (2026-11-26)

List f of `gamez/zSeal` (split 6 ways): the owner files seal.cpp, seal_airesponse.cpp,
seal_aimoves.cpp, seal_aiscan.cpp, seal_cfg.cpp, seal_create.cpp, seal_handsig.cpp,
seal_squirm.cpp and seal_weapon.cpp. It holds 42 uncertain rows (31 new, 6 removed, 1 unsure,
4 exact rows flagged `identical-copy`), 15 sampled deviating rows out of 133, and 103 exact rows
that were not checked. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-seal-f`, who did not write
the tool, at HEAD bfea625a. The check sheet (`compare.py --sheet gamez/zSeal --list f`) was the
starting point. Both images were disassembled with the release tools, callers were found by
scanning both images for `jal`/`j`, data words and `lui`/`addiu` pairs, and vtables were read
slot by slot (prototype `__vt__` symbols; release tables found by their RTTI class-name strings).
Ghidra was not needed.

What settled rows, in the order it was used: vtable slots (the CAiState family, CZSealBody and
its CBody sub-object table, CEntity, CTurret); the class-name strings of the RTTI records (the
release has no `CAiSCorpse`); the call site in a paired caller (HandleEvent, OnDeath, InitAiBrain,
CAiSRescued::OnSignal, SetMpStatUiVars, CRemoteCtrl::PreTick, OnCommand, PreTick); the slot
between paired neighbours; strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x24e140 `CompassAnchor_Hostage__10CZSealBodyFP14CCompassAnchor` | removed | confirmed | its callers now call two new functions: 0x2517a0 creates the hostage anchor and stores it at +0xde0 (InitAiBrain ×3, SetAiNetState), 0x251770 deletes it and clears +0xde0 (CAiSRescued::OnSignal, SetAiNetState, OnDeath) |
| 0x252a10 | - | new | confirmed | anchor point query; caller MapCompass::Tick; nothing in the slot |
| 0x252aa0 | - | new | confirmed | adds a point to the anchor's new CPnt3D vector; caller 0x2517a0 ×4 |
| - | 0x24e7d0 `GetPointsEarned__10CSealStatsCFiiif` | removed | confirmed | SetMpStatUiVars no longer computes the points: it reads a stored halfword (player +0x518, CSealStats +0x48) where the prototype called it |
| 0x253070 | - | new | confirmed | CSealStats counter (+0x24) for the online player; callers SetAiNetState, CSealCtrlAi::PostTick |
| 0x2530e0 | - | new | confirmed | CSealStats counter (+0x20) for the online player; caller ChangeBombState |
| 0x2532f0 | - | new | confirmed | packs CSealStats into a 10-byte record; caller GetMPStats |
| 0x253700 | - | new | confirmed | CrouchToPickupBuddy plus a counter; caller OnActionButton; sits among the ExecuteAction_ functions |
| - | 0x24ef60 `ResetAltitude__10CZSealBodyFf` | removed | confirmed | inlined: CRemoteCtrl::PreTick sets bit 7 of +0xdc itself where the prototype called it; its bytes occur nowhere |
| 0x254020 | - | new | confirmed | the kill message ("%s fragged %s with %s", PlayRemoteMsg 62/37/36) that the prototype built inline in OnDeath; the release OnDeath has none of it; 12 callers (the Damage* functions and others) |
| 0x2544c0 | - | new | confirmed | time since death (0 while alive); callers 0x2608c0, CTeamMateNames::Tick |
| 0x255d80 | 0x250f20 `PrePostTick__10CZSealBodyFf` | exact, identical-copy | confirmed | slot +0x1c of the CZSealBody vtable on both sides |
| 0x255d90 | 0x250f30 `PostPreTick__10CZSealBodyFf` | exact, identical-copy | confirmed | slot +0x18 of the CZSealBody vtable on both sides |
| 0x255da0 | - | new | confirmed | obstruction probe ahead of the seal (a ray 11.2 units along the facing); UpdateStance keeps the stance when it returns true |
| 0x25a6d0 | - | new | confirmed | new virtual, slot +0x24 of CZSealBody (between PostTick and ComputeNextPosition); holds the region-visibility start of the prototype PostTick |
| 0x25a800 | - | new | confirmed | returns 1 or 2 from AiStateIs(STATE_FOLLOW) / GetRemoteAiState; caller PostTick |
| 0x25efb0 | - | new, copy | corrected to 0x259150 `@272@__dt__10CZSealBodyFv` | its body is `j __dt__10CZSealBody; addiu a0,a0,-272` and it fills slot +0x08 of the CBody-in-CZSealBody table, as the prototype thunk does. See the two rows outside the list below |
| 0x25f0a0 | - | new, copy | confirmed | base entry of new CAiState slot +0x30 (already in settled-pairs.tsv) |
| 0x25f0b0 | - | new, copy | confirmed | base entry of new CAiState slot +0x34 (returns true); every CAiState table holds it except CAiSAction (0x2676b0) |
| 0x25f0c0 | - | new | confirmed | pushes STATE_EVENT and fills the event (type, position, flags), else SetAiAware 2 or 3; caller OnWeaponHit |
| 0x25f260 | - | new | confirmed | deploy-location search on the AI map (WalkLine-style walk with 0x25fa70 as callback through new 0x1a53f0); caller OnCommand, after PushAiState(STATE_DEPLOY), with FindValidReticleGotoLoc as the fallback |
| 0x25fa70 | - | new | confirmed | line-walk callback of 0x25f260 (its address is loaded, not called) |
| 0x25fbf0 | - | new | confirmed | pushes STATE_AVOID or STATE_PATHRECO when the seal is stuck; caller PreTick after SensorPreTick |
| 0x260040 | - | new | confirmed | elapsed time of a small tracker record (time at +0); caller CAiSPathRecover::Tick |
| 0x260070 | - | new | confirmed | updates that record by priority (1–4); callers 0x260160, 0x260270, 0x2602e0, CSealCtrlAi::PostTick |
| 0x260160 | - | new | confirmed | the record at an AI-map cell; callers PostComputeNextPosition, PathFollowTick |
| 0x260270 | - | new | confirmed | the record at a position (GetLocation); caller PostComputeNextPosition |
| 0x2602e0 | - | new | confirmed | the record for a blocking entity (new 0x2fa470 test); callers CollidePlayers, PathFollowTick |
| 0x260410 | - | new | confirmed | resets the record; callers CAiSAvoid::OnSignal, CAiSPathRecover::Tick |
| 0x260430 | - | new | confirmed | picks a look direction (CountMapVisDir, SetLookDirW, SetLookTimer) with a static table; caller SensorPreTick |
| 0x260860 | - | new | confirmed | initializes a 5-word range record; `__sinit_seal_ai.cpp` builds four static ones with it (the prototype sinit had none) |
| - | 0x2e6e20 `SetCorpse__10CAiSCorpseFP7CEntity` | removed | confirmed | class CAiSCorpse is gone: no `CAiSCorpse` RTTI name in the release; the corpse response is now a CAiSEvent (below) |
| - | 0x2e6e80 `OnSignal__10CAiSCorpseFQ28CAiState6SIGNALP11CSealCtrlAi` | removed | confirmed | the same |
| 0x2608c0 | 0x2e6c30 `Tick__10CAiSCorpseFfP11CSealCtrlAi` | unsure, string | corrected to new | not a virtual: one direct caller, HandleEvent. It is the corpse block that the prototype HandleEvent had inline (side test, sniper/guard-region test, push state), now pushing STATE_EVENT (25) instead of STATE_CORPSE (24) and naming the event "on_corpse" through 0x2fccb0. The shared string misled the tool. Tick__10CAiSCorpse is removed |
| 0x2f6fc0 | - | new | confirmed | wedge test; caller 0x2f63c0 only |
| 0x2f7290 | - | new | confirmed | XZ side test; caller 0x2f6fc0 only |
| 0x2fccb0 | - | new | confirmed | CAiSEvent: copies up to 16 characters of a name to +0x59 (clears it for null); caller 0x2608c0 with "on_corpse" |
| 0x2fd030 | - | new | confirmed | slot +0x18 (CanPushAiState) of CAiSRestrained: a new override; the prototype table inherited CAiState's |
| 0x2fdc90 | - | new | confirmed | slot +0x18 (CanPushAiState) of CAiSSurrender: a new override, the same way |
| 0x2ff9f0 | 0x2e93c0 `GetScriptResponse__14CAiSRestrainedCFv` | exact, identical-copy | confirmed | GetScriptResponse slot of the CAiSRestrained table (prototype +0x28, release +0x2c after the new slot +0x0c) |
| - | 0x2e9440 `__dt__10CAiSCorpseFv` | removed | confirmed | class gone (above) |
| 0x2ffb40 | 0x2e9570 `GetScriptResponse__13CAiSSurrenderCFv` | exact, identical-copy | confirmed | GetScriptResponse slot of the CAiSSurrender table |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x251a00 | 0x24d6e0 `TickHeartbeat__10CZSealBodyFv` | yes | same caller (Tick); same three callees |
| 0x2522a0 | 0x24df40 `SetCurZoomState__10CZSealBodyF9ZOOMSTATE` | yes | the same five callers, plus the destructor |
| 0x252b90 | 0x24e4a0 `ActionCommand__10CZSealBodyFUi` | yes | same two callers; the store moved by +0x24, like the other body fields |
| 0x253cb0 | 0x24f330 `PickupObject__10CZSealBodyFP7CPickup` | yes | the same four callers |
| 0x25abd0 | 0x255400 `UpdateAiEvent__10CZSealBodyFv` | yes | the only caller is PostTick on both sides |
| 0x25bcd0 | 0x2563e0 `PreTick__10CZSealBodyFf` | yes | slot +0x10 of the CZSealBody vtable on both sides |
| 0x25c3f0 | 0x256820 `UpdateLODFlags__10CZSealBodyFv` | yes | same caller (PreTick) |
| 0x2d0570 | 0x2befc0 `CanAttainAim__10CZSealBodyFR6CPnt3D` | yes | same caller (UpdateAimDir); operations 0.924 |
| 0x2d0910 | 0x2bf340 `UpdateAimDir__10CZSealBodyFb` | yes | same two callers |
| 0x2d0f20 | 0x2bf920 `UpdateAimParams__10CZSealBodyFv` | yes | same two callers; imm-only |
| 0x2d18a0 | 0x2c02c0 `WeaponsTick__10CZSealBodyFf` | yes | same caller (PreTick); imm-only |
| 0x2f9400 | 0x2e4660 `SetDefaultLookParams__9CSealCtrlF7AI_LOOK` | yes | the same six callers |
| 0x2fb2e0 | 0x2e5290 `Tick__15CAiSPathRecoverFfP11CSealCtrlAi` | yes | Tick slot of CAiSPathRecover (+0x0c → +0x10) |
| 0x2fbc10 | 0x2e5750 `GetStatus__15CAiSPathRecoverCFv` | yes | GetStatus slot (+0x10 → +0x14) |
| 0x2fcca0 | 0x2e65b0 `GetStatus__9CAiSEventCFv` | yes | GetStatus slot of CAiSEvent (+0x10 → +0x14) |

Just outside the list (found through the same vtables; not settled here):

| release | map | finding |
|---|---|---|
| 0x25efa0 | deviating, 0x259150 `@272@__dt__10CZSealBodyFv` | wrong: its body is `j GetRootPart__10CZSealBody; addiu a0,a0,-272`, slot +0x10 of the CBody sub-object table, so it is `@272@GetRootPart__10CZSealBodyCFv` (0x259140). Its dtor partner is 0x25efb0 (above) |
| 0x25ef90 | deviating, 0x259140 `@272@GetRootPart__10CZSealBodyCFv` | wrong: `j BodySetState__10CZSealBody; addiu a0,a0,-272` in a new slot +0x14 of that table; no prototype counterpart. New: `@272@BodySetState__10CZSealBodyFi` (from the thunk pattern) |
| 0x1f3940 … 0x1f38f0 | the empty CEntity virtuals | consistent with list a: they are paired one slot off. By the CEntity table (0x489450), checked against CZSealBody (0x4899f0) and CTurret (0x48aaf0): 0x1f3940 PreTick, 0x1f3930 Tick, 0x1f3920 PostPreTick, 0x1f3910 PrePostTick, 0x1f3900 PostTick, and **0x1f38f0 the new virtual** (slot +0x24). This differs from list a's note, which made 0x1f3900 the new one. The basis: the release `PostTickAll__7CEntityFfPv` calls slot +0x20 straight after the PrePostTick pass, where the prototype called PostTick, and calls +0x24 (with +0x0c) in a new pass of its own. So the map's CZSealBody PostTick at 0x25a8d0 (slot +0x20) is right and 0x25a6d0 is the new virtual. For the zEntity check |
| 0x1effc0 | new | slot +0x0c of CEntity and CZSealBody, where the prototype had `GetPosW__7CEntityCFv` (removed in the map). The bodies differ: the prototype returns the node's position pointer, the release copies the node position into the entity (+0x1c). Called per entity in the new last pass of PostTickAll. Not settled. For the zEntity check |
| 0x272750 | deviating, vtable-slot, 0x268880 `Tick__11CSealCtrlAiFf` | confirmed: slot +0x10 of the CSealCtrlAi table on both sides. The removed `Tick__11CSealCtrlAiFf` named in earlier hints is now paired; similarity 0.122 |
| 0x300940 | new (ai_target.cpp) | the hint holds in part: it reads the target's entity (`lw s1,0(a0)`, the old GetEntity) and IsAlive's bit (+0xdd), then also checks for a seal (type 2) and two controller virtuals and a flag at +0x281. So it is a larger "valid seal target" test that contains both. Callers in this list: 0x2608c0 |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x25efb0 | 0x259150 | thunk `j __dt__10CZSealBody; addiu a0,-272`; slot +0x08 of the CBody-in-CZSealBody table on both sides | socom-release-check-seal-f | 2026-11-26 |
| 0x25efa0 | 0x259140 | thunk to GetRootPart__10CZSealBody (this -272); slot +0x10 of the CBody-in-CZSealBody table (outside list f) | socom-release-check-seal-f | 2026-11-26 |
| 0x25ef90 | new | thunk to BodySetState__10CZSealBody (this -272) in a new slot +0x14 of the CBody-in-CZSealBody table (outside list f) | socom-release-check-seal-f | 2026-11-26 |
| 0x2608c0 | new | not virtual: one direct caller, HandleEvent; the corpse block that the prototype HandleEvent had inline, now pushing STATE_EVENT with "on_corpse" | socom-release-check-seal-f | 2026-11-26 |
| removed | 0x2e6c30 | class CAiSCorpse gone (no RTTI name in the release; StunResponse::OnSignal is followed by Hold::Tick); its release partner 0x2608c0 is new | socom-release-check-seal-f | 2026-11-26 |
| 0x25f0b0 | new | base entry of new CAiState vtable slot +0x34 (overridden by CAiSAction 0x2676b0); bytes equal to CanPursue's | socom-release-check-seal-f | 2026-11-26 |
| 0x255d80 | 0x250f20 | slot +0x1c of the CZSealBody vtable on both sides | socom-release-check-seal-f | 2026-11-26 |
| 0x255d90 | 0x250f30 | slot +0x18 of the CZSealBody vtable on both sides | socom-release-check-seal-f | 2026-11-26 |
| 0x2ff9f0 | 0x2e93c0 | GetScriptResponse slot of the CAiSRestrained vtable on both sides | socom-release-check-seal-f | 2026-11-26 |
| 0x2ffb40 | 0x2e9570 | GetScriptResponse slot of the CAiSSurrender vtable on both sides | socom-release-check-seal-f | 2026-11-26 |

The first three rows go together: the map has 0x25efa0 = 0x259150 and 0x25ef90 = 0x259140, so
all three change at once. Owners: 0x2608c0 belongs to seal_ai.cpp, not seal_airesponse.cpp (it
sits between `__sinit_seal_ai.cpp`'s helper 0x260860 and CAiSRescued::Tick, in seal_ai.cpp's
release range). The unowned group 0x25f0a0–0x260860 belongs to seal_ai.cpp for the same reason
(the place where the prototype had seal_ai.cpp's out-of-line inlines HasSniperRifle and
InGuardRegion, and `__sinit_seal_ai.cpp` calls 0x260860). 0x2f6fc0 and 0x2f7290 belong to
**seal_aifollow.cpp**, not seal_aimoves.cpp: they follow GetSnakeFollowLoc, the last
seal_aifollow.cpp function, and come before seal_squirm.cpp; their only caller chain starts at
0x2f63c0 (seal_aifollow.cpp, called by FollowTick); seal_aimoves.cpp's release functions are at
0x2f3410–0x2f3490, before the follow block. The map leaves both without an owner; only the list
header gives them seal_aimoves.cpp.

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x252a10 | anchor: when the current point index (+0x18) is valid, copies that point out of the vector at +0x28; returns true when the index has not changed since the last call (+0x1c) | guess: `CCompassAnchor::GetCurrentPoint(CPnt3D*)`, from the body and MapCompass::Tick |
| 0x252aa0 | anchor: returns the index of a point in its CPnt3D vector (+0x20), appending it when absent | guess: `CCompassAnchor::AddPoint(const CPnt3D&)` |
| 0x253070 | `++stats+0x24` when online and the seal is the player | guess: a new `CSealStats` counter, e.g. `Rescue(const CZSealBody&)` (callers CRemoteCtrl::SetAiNetState and CSealCtrlAi::PostTick) |
| 0x2530e0 | `++stats+0x20` the same way | guess: `CSealStats::Bomb(const CZSealBody&)` (caller ChangeBombState) |
| 0x2532f0 | memset a 10-byte record, then pack seven stats bytes, a percentage (float +0x28 × 100) and the halfword at +0x48 into it | guess: `CSealStats::Pack(MPSealStats*) const` (caller GetMPStats) |
| 0x253700 | CrouchToPickupBuddy(buddy), then `++this+0x500` | guess: `ExecuteAction_PickupBuddy__10CZSealBodyFP10CZSealBody` (its neighbours and signature) |
| 0x254020 | posts the kill message and the remote kill sounds | guess: `CZSealBody::AnnounceKill(...)`; the block came out of OnDeath |
| 0x2544c0 | `IsAlive ? 0 : now - deathTime(+0xed8)` | guess: `CZSealBody::GetTimeDead() const` |
| 0x255da0 | ray probe ahead of the seal; true when something is hit | guess: `CZSealBody::IsStanceBlocked()` (UpdateStance) |
| 0x25a6d0 | the region-visibility test from the start of the prototype PostTick, as a new virtual | guess: `CZSealBody::UpdateRegionVisibility(float)`; slot +0x24, base 0x1f38f0 |
| 0x25a800 | 0 / 1 / 2 from the follow state of the local or remote AI | guess: `CZSealBody::GetFollowState()` |
| 0x25f0b0 | CAiState default virtual, returns true | slot +0x34 of the CAiState table; name unknown |
| 0x25f0c0 | pushes a CAiSEvent for a hit (or raises awareness) | guess: `CSealCtrlAi::PushHitEvent(...)` |
| 0x25f260 | finds a deploy location by walking the AI map | guess: `CSealCtrlAi::FindDeployLoc(...)` |
| 0x25fa70 | its line-walk callback | guess: `_deploy_walk(const MAP_LINEWALK_STRUCT&, void*)` |
| 0x25fbf0 | stuck check that pushes Avoid or PathRecover | guess: `CSealCtrlAi::CheckStuck()` |
| 0x260040, 0x260070, 0x260160, 0x260270, 0x2602e0, 0x260410 | methods of a small tracker record (time, level, kind, cell, blocking entity) | guess: a "blocked" monitor: `GetAge`, `Update`, `UpdateCell`, `UpdatePos`, `UpdateEntity`, `Reset` |
| 0x260430 | chooses a look direction from the AI map's visibility counts | guess: `CSealCtrlAi::PickLookDir()` (SensorPreTick) |
| 0x260860 | `(rec, a, b, c)`: base, size and clamped position of a range record | guess: the constructor of the four static records in `__sinit_seal_ai.cpp` |
| 0x2608c0 | the corpse-sighting response (see above) | guess: `CSealCtrlAi::OnSeeCorpse(CZSealBody*)` |
| 0x2f6fc0, 0x2f7290 | wedge and XZ side tests (as list c describes them) | list c's guesses `InFollowCone`, `PointInWedgeXZ` stand |
| 0x2fccb0 | copies an event name (16 characters) into the CAiSEvent | guess: `CAiSEvent::SetName(const char*)` |
| 0x2fd030 | true when the seal's body has flag 0x20000 (+0xc4) | `CanPushAiState__14CAiSRestrainedF8AI_STATEP11CSealCtrlAi` (slot +0x18) |
| 0x2fdc90 | with that flag: true once the state's stage (+0x10) is at least 5; otherwise only STATE_RESTRAINED may be pushed | `CanPushAiState__13CAiSSurrenderF8AI_STATEP11CSealCtrlAi` (slot +0x18) |

Not new, though the map has it as new: 0x25efb0 (`@272@__dt__10CZSealBodyFv`).

Really removed: CompassAnchor_Hostage (replaced by 0x2517a0 create-and-store and 0x251770
delete-and-clear, both new and outside the list), GetPointsEarned (points stored in CSealStats
+0x48 instead), ResetAltitude (inlined into CRemoteCtrl::PreTick), and the whole CAiSCorpse class
(Tick, SetCorpse, OnSignal, destructor): the corpse response is a CAiSEvent named "on_corpse",
started from 0x2608c0.

Layouts, plainly shown by settled rows: CZSealBody fields from +0xdb4 onward moved by +0x24
(ActionCommand +0xdcc → +0xdf0; the compass anchors +0xdb4/+0xdb8/+0xdbc → +0xdd8/+0xddc/+0xde0).
The AI-state type byte that `GetAiState()` callers test moved from +0x10 to +0x0c. The CAiState
vtable has three new slots (+0x0c, +0x30, +0x34); the CEntity vtable a new slot +0x24; the CBody
sub-object table of CZSealBody a new slot +0x14.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses.
- The disagreement with list a over which empty CEntity virtual is the new one (0x1f38f0 here,
  0x1f3900 there); the evidence for this note is PostTickAll's call order (above).
- 0x1effc0 against the prototype's GetPosW (slot +0x0c): not settled, zEntity.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 31 | 30 | 1: 0x25efb0 is the dtor thunk |
| removed | 6 | 6 | 0 |
| unsure | 1 | 0 | 1: 0x2608c0 is new, not CAiSCorpse::Tick |
| exact, identical-copy | 4 | 4 | 0 |

Outside the list, the same kind of miss: 0x25efa0 and 0x25ef90 (two thunks one slot off), the
CEntity empty virtuals (one slot off).

The sample: 15 of 15 deviating rows are the same function on both sides.

What misled it:

- The thunks: three 8-byte `j X; addiu a0,a0,-272` stubs in a row, paired by position. The jump
  target names the method, and a new thunk in front shifted the pairs by one.
- 0x2608c0: the shared string "on_corpse" (sole evidence `string`, similarity 0.088). The
  prototype function is a virtual of a class that the release no longer has. A string pair whose
  prototype side is a vtable slot while the release side has a direct caller and no vtable
  reference should not be proposed.
- The CEntity stubs: equal bytes, and the new slot sits among them; only the derived tables (and
  the tick loop's call order) place it.

What cost the most time: the CEntity/CZSealBody new slot, where the tables alone cannot say
which side of PostTick the new slot is on. Suggestions:

- For an 8-byte `j target; addiu a0,a0,-N` thunk, pair by the jump target's pair and the offset.
- Treat an RTTI class name that exists only in the prototype as proof that the class's methods
  are removed.
- In the sheet, show the vtable slot of a removed virtual's class when that class has no release
  table.
