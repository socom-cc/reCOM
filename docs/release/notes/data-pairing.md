# Data pairing: second-agent check

Checked by `socom-release-data-check-k1` on 2026-11-27, at commit 22bdbc9a. The pairing was produced by
`socom-release-data-d1` (`tools/release/datapair.py`, `dataflow.py`, `datareport.py`; output
`docs/release/data-map.tsv`, `DATA.md`, `build/release/data-map.json`). All 9,553 committed pairs (8,977
exact, 576 deviating) were cross-checked by code written for this check, not by rerunning the author's code:
the prototype's own relocations (HI16/LO16, GPREL16, 32-bit words) and symbols give every prototype use of
every object; each use in a paired function was found again in the release function by a separate alignment
(instruction shapes, the use and its HI16 partner both aligned) and by an alignment-free search of the
release function, and every initialised word was compared once pointers were mapped through the function
map and the data map. Literal strings were then checked by their text, and the functions whose repeated
code can shift an alignment by whole blocks (name lookups, field registrations, static initialisers) were
read by their semantic keys (the name string looked up, the member offset registered, the destructor record
registered). Scratch, scripts and outputs: `build/release/data-check-k1/`. Ghidra was not used.

## Findings

### Wrong pairs: 71

Every one rests on a single `operand-aligned` witness in a deviating function, except one literal
(`operand-exact`). 59 are classed deviating, 12 exact. The right counterparts are in the table below.

- **`__ct__14CUIListBoxSpecFP5_zrdr` (p 0x3966b0) event names, 29 literals `@3403`..`@3431`
  (0x462078..0x462350).** The function compares a name against a long chain of event strings, one block per
  name. The release inserted 14 blocks; the tool aligned prototype block k with release block k+14, so
  `@3424` "MP_LEADERSHIP_TRANSFER_SUCCESS" was paired with 0x479218 "ONFOCUS" while the same function
  references "MP_LEADERSHIP_TRANSFER_SUCCESS" at 0x4790d0. Content could not decide: each string exists three
  times in the prototype (`identical-copy`). Right: every prototype string to the release string of the same
  text that the paired function references (0x478ea8..0x479180); release 0x4791a0..0x4792b0 and 0x4792c0
  ("SPEED") are new strings.
- **`AnimTypes` statics, 12 pairs** (`Stabbed`, `ReceiveRestraints`, `BuddyCarriedStand`, `BuddyCarryBody`,
  `BuddyCarriedWalk`, `BuddyCarriedStep`, `DiveForward01`, `LandBackward01`, `GetupForward01`,
  `GetupBackward01`, `PistolLadder2Slide`, `PistolLadderSlide`). `InitializeAnimNames__Fv` (p 0x2c7ef0)
  looks every name up by its string and stores the result into the static; keyed by that string, the
  release inserted 11 to 12 entries before `Stab`, and the tool's pairs from there on sit 0x2c to 0x30 bytes
  low. Three of them are classed exact.
- **`CZSealState` net field IDs, 16 pairs** (`ThrottleFB`, `ThrottleLR`, `WeaponState`, `PeekState`, the
  six `*Health`, `KillerIndex`, `FireModeSelect`, `WeaponSelect`, `AimElevation`, `FireTriggerCount`,
  `RoundStats`). `zNetRegisterSeal` (p 0x205930) registers each ID with its member offset, size and flags.
  Read that way the release inserted one 2-byte field at offset 136 (its ID 0x48d608 is new), every later
  offset is +2, `RoundStats` shrank from 12 to 10 bytes so `GameStats` keeps 167, and the release IDs lie in
  registration order in one block 0x48d5a8..0x48d624. The tool put `ThrottleFB`, `ThrottleLR`,
  `WeaponState`, `AimElevation`, `FireTriggerCount` and `RoundStats` outside that block (0x48d634..0x48d6a0,
  IDs that `zNetRegisterSeal` does not register) and the others two slots off.
- **`__sinit_hud_scorepopup.cpp` destructor records `@2604`..`@2607`.** Each global is constructed and then
  registered with `__register_global_obj(object, destructor, &record)`; the tool paired the last four
  records with the first four (0x58b110..0x58b2c0, already held by `@2596`..`@2599`). Right:
  0x58b590, 0x58b6d0, 0x58b760, 0x58c740.
- **Single strings** where the paired release function references the prototype text elsewhere:
  `@11431` "sleep" (tool 0x4697f8 "climb"), `@3596` "WAIT" (tool "BANG"), `@3032` "HN" (tool "PRIORITY"),
  `@1391` "RUN\IRX\MCSERV.IRX" (tool "MCMAN"), `@9196` "UsagePolicy" (tool "TempUsagePolicy"), `@1929`
  "STICK_DEADZONE" (tool "STICK_INERTIA"), `@2235` "run/irx/msifrpc.irx" (tool "eznetcnf"), and `@1928`
  "STICK_ACCELERATION", which by order in `InitSystemTuners` became "STICK_INERTIA" (0x479dd8, a text change,
  deviating), not "STICK_SENSITIVITY". `@6468` "Empty Slot" has no counterpart: the release
  `OnListSavedGames` dropped it (removed).
- **`@2438` "BREACH"** (operand-exact): the exact function now uses "ACT_BREACH" at 0x4664b8, while "BREACH"
  itself is at 0x4663d8, where `UISTR_ACT_BREACH` points. By the tool's own rule that a literal is its bytes
  the pair is 0x4663d8.

### Settled conflicts and unsure objects: 108

- `AnimTypes`: 36 witness conflicts settled by the name string (`FireStand` ... `PistolLadderSlideLand`;
  the last one is 0x48ce58, read by hand: the release appends six new anim names after it). The tool's
  `ClimbMedium` pair (contradicted) is right.
- Field IDs: `ThrottleST`, `StanceState`, `ActionState`, `AIState`, `UnitID`, `GameStats` (CZSealState) and
  `MaxGameTime`, `InitialClock`, `Flags` (CZGameState; `Flags` shrank from 8 to 4 bytes) by member offset.
- `__sinit_hud_scorepopup.cpp`: `@2596`..`@2603` (release-shared, order) are right; also
  `MultiplayerMsgStrings` of that unit 0x58b0f0, `g_oSeals2Ds` 0x58b770, `g_oTerrs2Ds` 0x58c750 (7 aligned
  uses in 3 functions agree with the sinit), `g_bmpTeamDivider` 0x58b6e0 (its users take that address; the
  release builds a new object at 0x58b630 before it).
- 17 others by text or by agreeing uses (`@5005`, `@3077`, `@3349`, `@3598`, `@3436`, `libnetCd__7CNetCnf`,
  `m_listenerIsValid__4CSnd`, `g_iBoxTopY`, `PacketTypeAiOrders`, `adren_incr2$2814`, `init$2815`,
  `init$2658`, the three `Global*Filter`, and the identical-copy twins `@2178`, `@8981`); those marked
  medium rest on a majority of aligned uses.
- 34 removed or unsure strings: the release text is there and the paired release function references it.
- The 136 contradicted pairs: the deciding side is right in every case. 122 are literals whose release text
  is the prototype text (the contradicting witness is a shifted block or the enum shift of `GetCommandName`);
  the 13 named ones are confirmed by many aligned uses or by content and vtable; `@2438` is above.

Left unsure, with the reason: `zon_writeon_dmaref` (one function, two offsets), `radius$3465`, `@9953`,
`_pDialogTuner`, `@1220`, `@1119`, `@2212`, `@1185`, `@3676`, `__RTTI__8CAiState` (pointer witnesses
disagree), the four `c_szCornerBoxesTx` (the release keeps one copy for four units), `PacketTypeReady`, and
the CZGameState IDs `RoundWinner`, `Score00`, `Score08`, `RoundIndex`: the release has six one-byte fields at
offsets 60..65 where the prototype has four at 64..67, and neither the member offsets nor the update callback
tell which four are the old ones.

### Pairs to withhold from the apply

1. The 71 wrong pairs until the table below is fed to the tool.
2. Unconfirmed pairs: `RoundWinner` (0x475a68) and `Score00` (0x475a6c) of CZGameState; the
   `InitSystemTuners` group (`_pStickAccelerationTuner` 0x476928, `_pStickDeadZoneTuner` 0x47692c,
   `_pMusicTuner`, `_pDialogTuner`, `__vt__23CStickAccelerationTuner`: the release creates more tuners,
   repeats the STICK_* names and has no STICK_ACCELERATION); `@6469` and `@6470` (texts changed, roles unclear);
   `@3348` (text changed).
3. `init$localstatic4$next__7CAiPathFv` at 0x475600: only its alias `_fbss` is witnessed (the entry
   function's bss start, release 0x48d200); carry `_fbss`, not the local static.
4. Single-witness `operand-aligned` pairs whose bytes differ from the prototype's: 67 pairs, 38 of them shown
   wrong. Withhold all 67 except those in the table below.
5. Literal strings whose release text differs: the 16 real text changes (`DmeVersionString`,
   "AUTO AIM" -> "AIM ASSIST", "SND_THUNK" -> "SND_THUNK08_WAV", ...) are right pairs, but their size and type
   come from the release bytes, not from the prototype.
6. Order-only pairs whose neighbours are not confirmed (20, mostly MSL math constants such as `huge`,
   `ln2_hi`, `C1`..`C5`) and order-only pairs whose paired function no longer references them (`@2401`,
   `@2406`, `@1923`, `@3084`).
7. `@3679` (0x452ef0, the jump table of the `GetCommandName` switch) is classed exact but 33 of its 66 entries
   differ: the tool compares only pointers to function starts, not pointers into a body. The pair is right;
   its class is deviating, and its entries must not be carried.

What can go through: every other exact and deviating pair. Each was confirmed by my cross-check (a use at
the same offset in a paired function, equal content with pointers mapped, or a matching pointer from a
paired object) and none of the semantic-key checks contradicted it. The residual risk is in the single
`operand-aligned` pairs on bss or on bytes that occur more than once (1,331 pairs besides the wrong
ones): my positional checks repeat an alignment and cannot see a whole-block shift, and 32 of the wrong pairs above were of that kind,
found only by the keys. A plate flag "single aligned witness" on those names would keep them visible.

### Real layout changes seen (for stage 4)

- `CZSealState`: a 2-byte member inserted at offset 136; the round stats block 12 -> 10 bytes.
  `CZGameState`: the flags 8 -> 4 bytes, six one-byte fields before the round block where there were four.
- C2D widget vtables (`C2DClock`, `CTickerTapeText`, `CScrollText`, `CTeleType`, `CWrappedText`,
  `CRenderableString`, `C2DCounter`: +0x7c -> +0x80; `CPopUpDialog`, `CHProgressBar`, `CUIListBox`,
  `CPlainBmp`, `CycleItem`, `CBmpWithNode`: +0x5c -> +0x60; `CCheckBox`, `CSliderBar`: +0x68 -> +0x6c): one
  virtual added in a common base. `CZSealBody` +0x50 -> +0x5c. Ten 36- or 68-byte vtables (`CNodeEx`,
  `CZAnimEx`, `CNodeAction`, `CLightMap`, `CLight`, `CRenderMap`, `CSealEx`, `CVisual`, `CSubMesh`,
  `C2DVisual`) end 4 bytes earlier, with changed content: probably one slot fewer; `CParticleEx` 36 -> 24.
- `theMission`, `theGame`, `zVid`, `ActionTxtrPool`, `ActionTxtrMachine_HUD`, `thePipe`, `archive`,
  `boneArchive`, `breachState$3368`, the HUD bracket strings (+0x50 -> +0x54...): members moved, consistent
  across many uses. `g_MenuStack` +0x410 -> +0x820 (the stack doubled), `_colorEntNoBlock` and
  `_colorPlayerNoSee` 12 -> 16 bytes (a fourth component), the `@N` switch tables that grew by a case.
- Artefacts, not layout: lower bounds past the size from `ldl`/`ldr` and `sdl`/`sdr` pairs, which access 8
  bytes at offset +7 (`gConfig` 15..8, `g_lhNullHandle`, `MyAddressInfo`, `NetLocalServerIpBinary`,
  `pubKey.0`/`priKey.1` 71..); the size changes of the wrong string pairs above; `zero__6CPnt3D` +0x0 -> +0x4
  (some uses fold the y component); `g_relocDblBuf` (+0x8 -> +0x1c, +0xc -> +0x8) is not explained.

## Settled data pairs

One row per pair whose counterpart or class this check changed or settled. Columns: release address (or
`removed`), prototype address, symbol, the tool's class and release address, basis, checker, date.

| release | prototype | symbol | tool | basis | by | date |
|---|---|---|---|---|---|---|
| removed | 0x44c600 | `@6468` | deviating 0x4640b0 | wrong: text 'Empty Slot' absent from the release; OnListSavedGames dropped it | socom-release-data-check-k1 | 2026-11-27 |
| 0x4663d8 | 0x44e5b8 | `@2438` | deviating 0x4664b8 | wrong by the literal rule: 'BREACH' is at this address (UISTR_ACT_BREACH points here); the exact function now uses 'ACT_BREACH' | socom-release-data-check-k1 | 2026-11-27 |
| 0x4697f0 | 0x451db8 | `@11431` | deviating 0x4697f8 | wrong: string text; the paired release function references the same text here | socom-release-data-check-k1 | 2026-11-27 |
| 0x46e6b8 | 0x4573e8 | `@3596` | deviating 0x46e6c8 | wrong: string text; the paired release function references the same text here | socom-release-data-check-k1 | 2026-11-27 |
| 0x46f4f0 | 0x458610 | `@3032` | deviating 0x46f4e0 | wrong: string text; the paired release function references the same text here | socom-release-data-check-k1 | 2026-11-27 |
| 0x46f8b0 | 0x458a40 | `@1391` | deviating 0x46f890 | wrong: string text; the paired release function references the same text here | socom-release-data-check-k1 | 2026-11-27 |
| 0x472178 | 0x45b578 | `@9196` | deviating 0x4721b0 | wrong: string text; the paired release function references the same text here | socom-release-data-check-k1 | 2026-11-27 |
| 0x478ea8 | 0x462078 | `@3403` | deviating 0x478fd0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478eb8 | 0x462088 | `@3404` | deviating 0x478ff0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478ec8 | 0x462098 | `@3405` | deviating 0x479010 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478ed8 | 0x4620a8 | `@3406` | deviating 0x479020 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478ef0 | 0x4620c0 | `@3407` | deviating 0x479038 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478f08 | 0x4620d8 | `@3408` | deviating 0x479050 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478f20 | 0x4620f0 | `@3409` | deviating 0x479070 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478f40 | 0x462110 | `@3410` | deviating 0x479090 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478f60 | 0x462130 | `@3411` | deviating 0x4790b0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478f80 | 0x462150 | `@3412` | deviating 0x4790d0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478fa0 | 0x462170 | `@3413` | deviating 0x4790f0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478fb0 | 0x462180 | `@3414` | deviating 0x479100 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478fd0 | 0x4621a0 | `@3415` | deviating 0x479118 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x478ff0 | 0x4621c0 | `@3416` | deviating 0x479128 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479010 | 0x4621e0 | `@3417` | deviating 0x479140 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479020 | 0x4621f0 | `@3418` | deviating 0x479160 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479038 | 0x462208 | `@3419` | deviating 0x479180 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479050 | 0x462220 | `@3420` | deviating 0x4791a0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479070 | 0x462240 | `@3421` | deviating 0x4791c0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479090 | 0x462260 | `@3422` | deviating 0x4791e0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x4790b0 | 0x462280 | `@3423` | deviating 0x479200 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x4790d0 | 0x4622a0 | `@3424` | deviating 0x479218 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x4790f0 | 0x4622c0 | `@3425` | deviating 0x479220 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479100 | 0x4622d0 | `@3426` | deviating 0x479240 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479118 | 0x4622e8 | `@3427` | deviating 0x479258 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479128 | 0x4622f8 | `@3428` | deviating 0x479268 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479140 | 0x462310 | `@3429` | deviating 0x479278 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479160 | 0x462330 | `@3430` | deviating 0x479290 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479180 | 0x462350 | `@3431` | deviating 0x4792b0 | wrong: string text; __ct__14CUIListBoxSpec (p 0x3966b0) references the same text here (tool's alignment off by 14 blocks) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479dd8 | 0x462e70 | `@1928` | deviating 0x479dc0 | wrong: InitSystemTuners order SENSITIVITY, ACCELERATION->INERTIA, DEADZONE; text changed (deviating) | socom-release-data-check-k1 | 2026-11-27 |
| 0x479de8 | 0x462e88 | `@1929` | deviating 0x479dd8 | wrong: string text; the paired release function references the same text here | socom-release-data-check-k1 | 2026-11-27 |
| 0x47e220 | 0x468020 | `@2235` | deviating 0x47e260 | wrong: string text; the paired release function references the same text here | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdb8 | 0x47527c | `Stabbed__9AnimTypes` | deviating 0x48cd8c | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdcc | 0x475290 | `ReceiveRestraints__9AnimTypes` | deviating 0x48cda0 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cde4 | 0x4752a4 | `BuddyCarriedStand__9AnimTypes` | exact 0x48cdb4 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cde8 | 0x4752a8 | `BuddyCarryBody__9AnimTypes` | deviating 0x48cdb8 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdf4 | 0x4752b4 | `BuddyCarriedWalk__9AnimTypes` | deviating 0x48cdc4 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce0c | 0x4752cc | `BuddyCarriedStep__9AnimTypes` | deviating 0x48cddc | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce18 | 0x4752d8 | `DiveForward01__9AnimTypes` | deviating 0x48cde8 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce20 | 0x4752e0 | `LandBackward01__9AnimTypes` | exact 0x48cdf0 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce24 | 0x4752e4 | `GetupForward01__9AnimTypes` | exact 0x48cdf4 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce28 | 0x4752e8 | `GetupBackward01__9AnimTypes` | deviating 0x48cdf8 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce48 | 0x475308 | `PistolLadder2Slide__9AnimTypes` | deviating 0x48ce18 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce50 | 0x475310 | `PistolLadderSlide__9AnimTypes` | deviating 0x48ce20 | wrong: InitializeAnimNames stores this after looking up the same name string (tool off by 11-12 slots) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5bc | 0x4759e8 | `m_ThrottleFBFieldID__11CZSealState` | exact 0x48d634 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5c0 | 0x4759ec | `m_ThrottleLRFieldID__11CZSealState` | deviating 0x48d638 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5c8 | 0x4759f4 | `m_WeaponStateFieldID__11CZSealState` | deviating 0x48d640 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5d0 | 0x4759fc | `m_PeekStateFieldID__11CZSealState` | deviating 0x48d5c8 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5d8 | 0x475a04 | `m_HeadHealthFieldID__11CZSealState` | exact 0x48d5d0 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5dc | 0x475a08 | `m_BodyHealthFieldID__11CZSealState` | exact 0x48d5d4 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5e0 | 0x475a0c | `m_LLegHealthFieldID__11CZSealState` | exact 0x48d5d8 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5e4 | 0x475a10 | `m_RLegHealthFieldID__11CZSealState` | exact 0x48d5dc | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5e8 | 0x475a14 | `m_LArmHealthFieldID__11CZSealState` | exact 0x48d5e0 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5ec | 0x475a18 | `m_RArmHealthFieldID__11CZSealState` | exact 0x48d5e4 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5f0 | 0x475a1c | `m_KillerIndexFieldID__11CZSealState` | exact 0x48d5e8 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5f4 | 0x475a20 | `m_FireModeSelectFieldID__11CZSealState` | deviating 0x48d5ec | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5fc | 0x475a24 | `m_WeaponSelectFieldID__11CZSealState` | deviating 0x48d608 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d60c | 0x475a34 | `m_AimElevationFieldID__11CZSealState` | deviating 0x48d680 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d610 | 0x475a38 | `m_FireTriggerCountFieldID__11CZSealState` | exact 0x48d6a0 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d620 | 0x475a48 | `m_RoundStatsFieldID__11CZSealState` | deviating 0x48d688 | wrong: zNetRegisterSeal registers it with the same member offset (+2 after offset 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b590 | 0x5ae5b0 | `@2604` | deviating 0x58b110 | wrong: __sinit_hud_scorepopup registers this destructor record for the paired global | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b6d0 | 0x5ae640 | `@2605` | deviating 0x58b1a0 | wrong: __sinit_hud_scorepopup registers this destructor record for the paired global | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b760 | 0x5ae6d0 | `@2606` | deviating 0x58b230 | wrong: __sinit_hud_scorepopup registers this destructor record for the paired global | socom-release-data-check-k1 | 2026-11-27 |
| 0x58c740 | 0x5af640 | `@2607` | deviating 0x58b2c0 | wrong: __sinit_hud_scorepopup registers this destructor record for the paired global | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cc20 | 0x475110 | `Rotate180__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ccf0 | 0x4751e0 | `StepUp__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ccf4 | 0x4751e4 | `PistolStepUp__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ccfc | 0x4751ec | `PistolClimbMedium__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cd00 | 0x4751f0 | `ClimbOver__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cd04 | 0x4751f4 | `PistolClimbOver__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdb0 | 0x475274 | `Stab__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdb4 | 0x475278 | `PistolStab__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdbc | 0x475280 | `CQB__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdc0 | 0x475284 | `PistolCQB__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdc4 | 0x475288 | `CQBVictimFallBackwards__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdc8 | 0x47528c | `CQBVictimFallForwards__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdd0 | 0x475294 | `ApplyRestraints__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdd4 | 0x475298 | `PistolApplyRestraints__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cddc | 0x47529c | `BuddyCarryStand__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cde0 | 0x4752a0 | `PistolBuddyCarryStand__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdec | 0x4752ac | `BuddyCarryWalk__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdf0 | 0x4752b0 | `PistolBuddyCarryWalk__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdf8 | 0x4752b8 | `BuddyCarryPickup__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48cdfc | 0x4752bc | `PistolBuddyCarryPickup__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce00 | 0x4752c0 | `BuddyCarriedPickup__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce04 | 0x4752c4 | `BuddyCarryStep__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce08 | 0x4752c8 | `PistolBuddyCarryStep__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce10 | 0x4752d0 | `FallForward01__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce14 | 0x4752d4 | `FallBackward01__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce1c | 0x4752dc | `LandForward01__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce2c | 0x4752ec | `DefuseBombBegin__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce30 | 0x4752f0 | `PistolDefuseBombBegin__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce34 | 0x4752f4 | `DefuseBombLoop__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce38 | 0x4752f8 | `PistolDefuseBombLoop__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce3c | 0x4752fc | `DefuseBombEnd__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce40 | 0x475300 | `PistolDefuseBombEnd__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce44 | 0x475304 | `Ladder2Slide__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce4c | 0x47530c | `LadderSlide__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce54 | 0x475314 | `LadderSlideLand__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48ce58 | 0x475318 | `PistolLadderSlideLand__9AnimTypes` | unsure - | settled: InitializeAnimNames stores it after looking up its name string | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5c4 | 0x4759f0 | `m_ThrottleSTFieldID__11CZSealState` | unsure - | settled: zNetRegisterSeal member offset (+2 after 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5cc | 0x4759f8 | `m_StanceStateFieldID__11CZSealState` | removed - | settled: zNetRegisterSeal member offset (+2 after 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5d4 | 0x475a00 | `m_ActionStateFieldID__11CZSealState` | unsure - | settled: zNetRegisterSeal member offset (+2 after 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d604 | 0x475a2c | `m_AIStateFieldID__11CZSealState` | unsure - | settled: zNetRegisterSeal member offset (+2 after 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d5f8 | 0x475a30 | `m_UnitIDFieldID__11CZSealState` | unsure 0x48d608 | settled: zNetRegisterSeal member offset (+2 after 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d624 | 0x475a4c | `m_GameStatsFieldID__11CZSealState` | unsure - | settled: zNetRegisterSeal member offset (+2 after 136), size and flags | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d6a8 | 0x475a54 | `m_MaxGameTimeFieldID__11CZGameState` | unsure - | settled: zNetRegisterGame member offset and order (Flags 8 -> 4 bytes) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d6ac | 0x475a58 | `m_InitialClockFieldID__11CZGameState` | unsure - | settled: zNetRegisterGame member offset and order (Flags 8 -> 4 bytes) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d6b8 | 0x475a64 | `m_FlagsFieldID__11CZGameState` | unsure - | settled: zNetRegisterGame member offset and order (Flags 8 -> 4 bytes) | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b0f0 | 0x5ae110 | `MultiplayerMsgStrings` | unsure 0x58b0f0 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b110 | 0x5ae130 | `@2596` | unsure 0x58b110 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b1a0 | 0x5ae1c0 | `@2597` | unsure 0x58b1a0 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b230 | 0x5ae250 | `@2598` | unsure 0x58b230 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b2c0 | 0x5ae2e0 | `@2599` | unsure 0x58b2c0 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b350 | 0x5ae370 | `@2600` | unsure 0x58b350 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b3e0 | 0x5ae400 | `@2601` | unsure 0x58b3e0 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b470 | 0x5ae490 | `@2602` | unsure 0x58b470 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b500 | 0x5ae520 | `@2603` | unsure 0x58b500 | settled: __sinit_hud_scorepopup constructs/registers it in the same order | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b6e0 | 0x5ae650 | `g_bmpTeamDivider__28@unnamed@hud_scorepopup_cpp@` | unsure - | settled: its three users (p 0x421760, 0x421df0) take this address; the sinit builds a new object at 0x58b630 before it | socom-release-data-check-k1 | 2026-11-27 |
| 0x58b770 | 0x5ae6e0 | `g_oSeals2Ds__28@unnamed@hud_scorepopup_cpp@` | unsure - | settled: 7 aligned uses in 3 functions and the sinit array construction agree | socom-release-data-check-k1 | 2026-11-27 |
| 0x58c750 | 0x5af650 | `g_oTerrs2Ds__28@unnamed@hud_scorepopup_cpp@` | unsure - | settled: 7 aligned uses in 3 functions and the sinit array construction agree | socom-release-data-check-k1 | 2026-11-27 |
| 0x463c28 | 0x44c248 | `@5005` | unsure - | settled: text STICK_DEADZONE, referenced by both paired functions | socom-release-data-check-k1 | 2026-11-27 |
| 0x464320 | 0x44c770 | `@2178` | unsure - | settled (medium): identical-copy twins; 2 of 3 uses | socom-release-data-check-k1 | 2026-11-27 |
| 0x4647a8 | 0x44cb40 | `@3077` | unsure - | settled: text, referenced by the paired functions (3 uses) | socom-release-data-check-k1 | 2026-11-27 |
| 0x466160 | 0x44e300 | `@8981` | unsure - | settled (medium): identical-copy twins; 4 of 6 uses | socom-release-data-check-k1 | 2026-11-27 |
| 0x466968 | 0x44ea78 | `@3349` | unsure - | settled (medium): text '%s', referenced by both functions | socom-release-data-check-k1 | 2026-11-27 |
| 0x46e6c8 | 0x4573f8 | `@3598` | unsure 0x46e6e0 | settled: text BANG, GetStatus__10CAiSBreach references it | socom-release-data-check-k1 | 2026-11-27 |
| 0x47d348 | 0x466068 | `@3436` | unsure 0x47d360 | settled: text, referenced by the paired function | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d570 | 0x47599c | `PacketTypeAiOrders` | unsure - | settled (medium): 2 aligned uses | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d93c | 0x475ce8 | `adren_incr2$2814` | unsure - | settled (medium): 2 aligned uses, next to init$2815 | socom-release-data-check-k1 | 2026-11-27 |
| 0x48d940 | 0x475cec | `init$2815` | unsure - | settled (medium): 2 aligned uses, next to adren_incr2$2814 | socom-release-data-check-k1 | 2026-11-27 |
| 0x48df80 | 0x476150 | `init$2658` | unsure - | settled (medium): 2 aligned uses | socom-release-data-check-k1 | 2026-11-27 |
| 0x48e354 | 0x476444 | `m_listenerIsValid__4CSnd` | unsure - | settled (medium): 4 aligned uses in 2 functions | socom-release-data-check-k1 | 2026-11-27 |
| 0x48e5fc | 0x476704 | `GlobalMapFilter__24@unnamed@zNetMedius_cpp@` | unsure - | settled (medium): 2 functions against 1 (p 0x32ea80 is one slot off for all three filters) | socom-release-data-check-k1 | 2026-11-27 |
| 0x48e600 | 0x476708 | `GlobalPlayerFilter__24@unnamed@zNetMedius_cpp@` | unsure - | settled (medium): as GlobalMapFilter | socom-release-data-check-k1 | 2026-11-27 |
| 0x48e604 | 0x47670c | `GlobalSpeedFilter__24@unnamed@zNetMedius_cpp@` | unsure - | settled (medium): as GlobalMapFilter | socom-release-data-check-k1 | 2026-11-27 |
| 0x48eb74 | 0x476d20 | `g_iBoxTopY__28@unnamed@hud_scorepopup_cpp@` | unsure - | settled (medium): 5 aligned uses in 2 functions against 1 | socom-release-data-check-k1 | 2026-11-27 |
| 0x57f040 | 0x576e40 | `libnetCd__7CNetCnf` | unsure - | settled: 5 aligned uses in 4 functions | socom-release-data-check-k1 | 2026-11-27 |
| 0x44c4a0 | 0x43bc78 | `@2605` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x463988 | 0x44c040 | `@4519` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x465970 | 0x44db98 | `@5658` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x4660c8 | 0x44e278 | `@7759` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x4691b0 | 0x4514f0 | `@6611` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x4699f8 | 0x452508 | `@4265` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x460dd0 | 0x454cf0 | `@9675` | unsure 0x460dd0 | settled: string text, referenced by the paired function; the release keeps one copy, shared with `@6589` (0x449500) | socom-release-data-check-k1 | 2026-11-27 |
| 0x460df0 | 0x454d10 | `@9752` | unsure 0x460df0 | settled: string text, referenced by the paired function; the release keeps one copy, shared with `@6923` (0x449520) | socom-release-data-check-k1 | 2026-11-27 |
| 0x46ecd0 | 0x457f00 | `@3298` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x46f890 | 0x458a20 | `@1390` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x46fce0 | 0x458f80 | `@3820` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x4710a8 | 0x45a2b8 | `@3242` | unsure 0x471018 | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x4710a0 | 0x45a340 | `@3254` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x4710e8 | 0x45a378 | `@3275` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x471f60 | 0x45b470 | `@8441` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x472118 | 0x45b4f8 | `@8941` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x477ad0 | 0x460e70 | `@2770` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x478320 | 0x461548 | `@8388` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x479428 | 0x4624b8 | `@4067` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x479dc0 | 0x462e50 | `@1927` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47c078 | 0x464e40 | `@3004` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47c268 | 0x465058 | `@4232` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47c278 | 0x465078 | `@4234` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47cfa0 | 0x465cb0 | `@2980` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47d000 | 0x465d20 | `@4002` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47d008 | 0x465d28 | `@4003` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47d010 | 0x465d30 | `@4202` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47d020 | 0x465d40 | `@4203` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47d058 | 0x465d78 | `@4207` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47d6c8 | 0x466398 | `@2694` | unsure 0x47d658 | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47e040 | 0x467ac0 | `@2491` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47e020 | 0x467ef0 | `@4775` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47e070 | 0x467f28 | `@4779` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |
| 0x47e240 | 0x468040 | `@2236` | removed - | settled: string text, referenced by the paired release function | socom-release-data-check-k1 | 2026-11-27 |

## How the tool did

| evidence (committed pairs it supports) | wrong found | rate |
|---|---|---|
| `operand-aligned`, single witness (1,464) | 70 | 4.8 % (57 % where the bytes differ: 38 of 67) |
| `operand-aligned` with other witnesses | 0 | - |
| `operand-exact` (3,293) | 1 (a literal whose function changed its string) | 0.03 % |
| `content` (4,294) | 0 | - |
| `pointer` (1,878) | 0 | - |
| `vtable`, `named-table` (228) | 0 | - |
| `order` (172 committed) | 0 (24 unconfirmed) | - |

Per class: exact 12 wrong of 8,977, deviating 59 of 576. Of the 190 unsure, 77 are settled here (36
`AnimTypes`, 8 field IDs, 33 others: sinit objects, strings, conflicts); of the 684 `refs-unaligned` removed,
31 (30 strings, 1 field ID). A further 111 bss objects among the removed and unsure have one agreeing
release start from my aligned uses (61 removed, 50 unsure); they are candidates for the next pass, not
settled.

Cross-check totals: 27,156 prototype uses in paired functions; my alignment re-found 25,090, of which 24,275
at the paired object and the same offset; the alignment-free search found the expected address in the paired
release function for 26,260. 7,247 pairs with code uses agree in every referring function, 145 lose the
reference in some deviating function, 50 in all (references removed or moved: `GetSoilByName` now uses a
table, `__ct__Q28Particle6Source` no longer inlines the `CParticleEx` constructor, ...). Content: 6,613 equal
with pointers mapped, 188 differ (all deviating except `@3679`), 2,179 bss, 573 without size; 4,654 pointer
words map, 1,342 differ (moved vtable slots, `IrxFiles`, `UICommandTable`, the RTTI words of the grown
vtables).

What misled it:

- Repeated code in deviating functions. A block of four or more equal words "occurs once" because an
  immediate or a register differs, but the true alignment is shifted by whole blocks after an insertion in
  the release: name-compare chains, `NetObjectField` registrations, name lookups in `InitializeAnimNames`,
  `__register_global_obj` sequences, and the string chains of parsers that gained an entry (`get_mode`,
  `GetStatus__10CAiSBreach`, `LoadCSnd`, `RebootIOP`). All 70 wrong aligned pairs sit in such code;
  anchors next to the use do not help, they shift with it.
- `release-shared`: a misaligned witness of a stronger tier keeps a start that the right owner then loses
  (`@2604` took `@2596`'s 0x58b110, `@2605`..`@2607` likewise).
- Pointers into a function body (jump tables) are not compared, so `@3679` reads exact.
- Alias groups: a linker symbol grouped with a real object lends it its witness (`_fbss`).

The dataflow itself: on the prototype my relocation-derived targets and `dataflow.py` differ at 4 uses
(`sceCdMmode` 0x16f7a0, `SendPendingMessages` 0x411dac and 0x411db4, `RemoveMessageFromReSendBuffer`
0x412c7c), all where an HI16 record is emitted out of order in the relocation table; at 0x16f7a0 the
register flow is right, so these are relocation-pairing ambiguities rather than dataflow errors. 11 code
witnesses have no relocation behind them (integer constants read as addresses, such as 0x123456 against
`mfifoBase`); only two pairs rest on them alone, `__exception_table_end__` and `_end`, both linker symbols and
right. The release `$gp` 0x494670 is consistent: of 5,932 prototype GPREL16 uses re-found in the release with
it, 5,827 land on the paired object at the same offset, 46 on the wrong pairs above, 9 at another
offset inside the paired object, and 50 elsewhere (43 where my own alignment is off and the expected
address is still referenced, 7 where the reference moved). A `lui` in a delay slot misleads a linear scan (my first
alignment-free search), not the tool's flow analysis.

## What could not be checked

- The single `operand-aligned` pairs on bss or on non-unique bytes without a semantic key (about 1,300):
  my cross-check confirms them positionally, as the tool does, and cannot exclude a whole-block shift.
- The 1,418 `new` rows and the 532 removed objects with no candidate.
- The candidates from agreeing aligned uses for removed and unsure objects (111), and the network-library
  strings that moved into `LibNETSetup__8CHNetCnf` (`netcnf.irx`, `inet.irx`, `inetctl.irx`, `smap.irx`,
  `an986.irx`, release 0x47e150..0x47e200).
- The CZGameState round fields and the `InitSystemTuners` group (above).
- Nothing was read from Ghidra.
