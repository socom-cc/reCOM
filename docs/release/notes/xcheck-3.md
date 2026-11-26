# Stage 2 cross-check 3: gamez/zSeal pairs, list c (2026-11-26)

The cross-check (brief step 4) of every committed pair of the list `gamez-zSeal-pairs-c`: the owner
files seal_cfg.cpp, seal_ctrl.cpp, seal_control.cpp, seal_create.cpp, seal_ex.cpp, seal_kit.cpp,
seal_tasks.cpp, seal_unit.cpp, seal_aimoves.cpp and seal_squirm.cpp. 399 pairs (230 deviating, 169
exact), 4 of them `settled` by `socom-release-check-seal-a` (the CSealCtrl Initalize, OnMissionEnd,
OnMissionStart and OnRecycleEntity rows). The uncertain rows of these files were settled earlier
(`zSeal-a.md` to `zSeal-f.md`) and are not re-checked; no sample was taken. Pairing produced by
`socom-release-compare-c1` (`python tools/release/compare.py`); cross-checked by
`socom-release-xcheck-3`, who did not write the tool, at HEAD 2bf42336. Both images were decoded
with the release tools; Ghidra was not used.

What was compared, all through the map:

| check | compared | with a difference |
|---|---|---|
| callers (`jal`/`j`), address loaders (`lui`/`addiu`), vtable slots, data-word counts of each pair | 399 pairs | 53 |
| each pair's own ordered calls and loads (substitutions of one paired target by another) | 399 pairs | 8 |
| ordered calls and loads of every paired caller of a list function | 388 callers | 89 |
| vtables with a slot in these files, slot by slot | 7 tables | 3 |
| vtables a pair's body loads (constructors, destructors, creators) | 9 pairs | 0 |
| zAnim command registrations by name (`AddCmd`, every function argument) | 33 `ai::` commands | 0 |
| other data words holding a list function (neighbouring words compared) | 10 pairs | 1 |
| byte twins on either side, scored by shared callers; ties by slot, registration or call order | 32 pairs | 0 beaten |
| masked body of the prototype side against new release rows and the list's other rows | 351 pairs | 17 close, 1 real |

Most differences are callers that changed: a call added in the release (TriggerPowerReset from 16
CZKit setters, GetUnitByTeam, IsUsingBinocs from CSealCtrl Pre/PostTick, GetMenuState from HUD
code), a call dropped, or a call moved into a new helper or inlined.

## Differences looked at

The ones that are not simply "caller moved, added or dropped":

| release | prototype | difference | verdict |
|---|---|---|---|
| 0x290d30 | 0x2858b0 `CanPlaceBomb__9CSealCtrlFP11CNodeAction` | callers PreTick and CActionTxtrMachine::Add instead of InitMPBomb and CanPerformAction; body 256 bytes against 176; a new row 0x290e30 has CanPlaceBomb's masked body exactly | **wrong**: it is `CanPerformAction`, see below |
| 0x293ae0, 0x293b30 | 0x288120 `OnMissionEnd`, 0x288130 `OnMissionStart` (settled) | the prototype CRemoteCtrl table inherited them at +0x5c/+0x60; the release one holds its own empty overrides 0x2e01d0/0x2e01e0 (zInput note) | settled pairs hold: the CSealCtrl, CSealCtrlCopy and CSealCtrlSquirm tables agree in every slot, these included |
| 0x2e4390 | 0x2d1e00 `__dt__10CAiSBreachFv` | slot 9 → 12 of CAiSBreach (10 → 13 slots) | uniform: the CAiState family's new slot at +0x0c and two before the destructor (zSeal-b/-d notes), plus CAiSBreach's own CanPushAiState 0x2ec8b0 replacing the inherited one |
| 0x2b37b0 | 0x2a4d20 `OnWeaponHit__7CSealEx...` | CSealEx table 7 → 3 slots | base change: CNodeEx's five On* handlers (slots 2-6) became one new slot (0x1d0770); slots 0 (this function) and 1 agree |
| 0x2cf040 | 0x2bd860 `Parse__7CTEvent` | one release data word (0x44e700) holds it | coincidental: a list of code addresses, not function starts; the `ai::EVENT` registration agrees |
| 0x291130 | `PreTick__9CSealCtrlFf` | IsUsingItem(EQUIP_ITEM) → IsUsingBinocs | both pairs confirmed by body (IsUsingBinocs the same five instructions, kit +0x814 → +0x820); the call changed |
| 0x2bb820 | `GetCurAmmoCount__5CZKitFv` | WeaponIsGrenadeLauncherMode → unwrap ×2 + IsGrenadeLauncherWeapon | inlined; 0x2b6710 is still WeaponIsGrenadeLauncherMode (bodies equal up to kit offsets, four shared callers) |
| 0x2b3ba0 | 0x2a5010 `InitializeSniperKick` | Decr/IncrZoomState no longer call it | body equal up to the kit offsets; SetCurZoomState still calls it; DecrZoomState calls new 0x2b3a80 |
| 0x2b4310, 0x2b3b30 | `SetWeaponInfoChanged`, `Binocs_Enabled` (weak) | masked similarity 0.00 / 0.11; other bit setters closer | the release bodies add a TriggerPowerReset call; callers agree (ReCreate; OnDeath, ~CZSealBody, HandleNewZoom) |
| 0x2b7100 | `GetFiremodeGraphic` | GetFiremodeName 0x2b7030 closer in body | call order in SetupFiremode agrees; only the Name calls GetName |
| 0x2e8d40, 0x2e7810, 0x2eb010 | list instances `<FT_COMMAND>`, `<CSealUnit*>` | twins of the `<const void*>` instances | call order in every shared caller agrees (174 callers); differences only in how often the `<const void*>` copy is called |
| 0x2cf330, 0x2cf340 | `Begin__6CTDoor`, `Parse__6CTDoor` | 8-byte twins | `ai::DOOR` registration: parse 0x2cf340, begin 0x2cf330 on both sides |
| 0x2f7610 … 0x2f7d50, 0x293690, 0x290850, 0x293bd0 | empty CSealCtrl / CSealCtrlSquirm virtuals | 8-byte twins | vtable slots agree |
| 0x2b6b50, 0x2befc0 | `ItemHasAmmo(EQUIP_ITEM)`, `HasItem` | TickMPBomb, PerformProximityActions, OnActionButton, AllowCommand lost their calls | those callers now call CanPerformAction 0x290d30 or new helpers 0x2e6880 / 0x2e6b70; CanPlaceBomb 0x290e30 calls both |
| 0x2be330 | `PostSetupItems` | four prototype callers dropped the call | only OnMissionStart left |
| 0x2bc720 | `Fire__5CZKit...` | GetStance/PushBlend → Reload | body changed; Reload 0x2bad60 keeps its four prototype callers |

## Wrong pairs

**0x290d30 is `CanPerformAction__9CSealCtrlFP11CNodeAction` (0x2857d0), not CanPlaceBomb.** Its body is
CanPerformAction's: the switch on the action type at +0x20 (6, then 4; for 4, a global byte equal
to 2 sends it to the one call, and the values 1 and 3 decide the rest), then
`HasItem(kit, 152)` and `ItemHasAmmo(kit, 152)` and the halfword test at +4 of the record at +0x18.
The release adds a type-5 case that returns 0, and the kit is at +1328 instead of +1312.
CActionTxtrMachine::Add calls it, as it called CanPerformAction in the prototype. The real
CanPlaceBomb is the "new" row 0x290e30 (176 bytes): CanPlaceBomb's 44 instructions, differing only
in the two globals' addresses and the kit offset. It is called from 0x290d30 at the place where
CanPerformAction calls CanPlaceBomb. The two are adjacent on both sides in the same order
(0x2857d0 + 224 = 0x2858b0; 0x290d30 + 256 = 0x290e30). The release callers PreTick (the inlined
InitMPBomb), TickMPBomb, PerformProximityActions and OnActionButton, which called CanPlaceBomb in the
prototype, now call CanPerformAction, which hands bomb actions on. That change of callers is what
misled the tool: it paired by callers and slot (`call-and-slot`, similarity 0.35). The prototype
CanPerformAction (removed in the map) and 0x290e30 (new) are in no earlier note. One correction
follows for `zSeal-e.md`: the InitMPBomb code in the release PreTick calls CanPerformAction, not
CanPlaceBomb.

No other committed pair is wrong. The four settled pairs agree with every table that holds them.

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x290d30 | 0x2857d0 | body: CanPerformAction's action-type switch (6, 4), HasItem/ItemHasAmmo(152) and the +0x18 halfword test, plus a type-5 case; caller CActionTxtrMachine::Add as in the prototype | socom-release-xcheck-3 | 2026-11-26 | | |
| 0x290e30 | 0x2858b0 | body: CanPlaceBomb's 44 instructions, only the two globals and the kit offset (1312 → 1328) differ; called by 0x290d30 where CanPerformAction calls CanPlaceBomb; adjacent in the same order | socom-release-xcheck-3 | 2026-11-26 | | |

## How the tool did

- Cross-check: 399 pairs compared; 53 with a caller, loader, slot or data-word difference and 8
  with an ordered-call substitution, plus 89 of 388 paired callers, 3 of 7 vtables, 1 of 10 data-word
  sets and 17 close body rivals looked at; 1 pair wrong (0x290d30, a `call-and-slot` pair whose
  callers had moved to the function it calls).
- Settled pairs: 4 included, 4 hold.
- Scripts and outputs: `build/release/check-xcheck-3/` (xcheck, xseq, vtcheck, vtstore, cmds,
  tabcheck, twins, order, bodyrival, who).
