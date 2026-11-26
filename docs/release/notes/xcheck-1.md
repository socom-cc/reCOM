# Stage 2 cross-check xcheck-1: zSeal (a), zArchive, zMPEG, zNetwork (zNetCnf, zNetDme) (2026-11-26)

Step 4 of the checker brief only, for four modules whose uncertain rows were settled before that step
existed: every committed pair of the pair lists `gamez-zSeal-pairs-a` (398 pairs), `gamez-zArchive-pairs-a`
(71), `gamez-zMPEG-pairs-a` (38) and `gamez-zNetwork-pairs-a` (31: zNetCnf.cpp and zNetDme.cpp), made with
`compare.py --lists <module> --pairs-only`. No uncertain rows re-checked, no sample taken. Pairing produced
by `socom-release-compare-c1` (`python tools/release/compare.py`); checked by `socom-release-xcheck-1`, who
did not write the tool, at HEAD 2bf42336. Pairs with evidence `settled` (6 zSeal, 15 zArchive, 4 zMPEG, 3
zNetwork) were compared like the rest. Both images were decoded with the release tools; Ghidra was not needed.

Method, per list (scripts in the scratch folder):

- **A, references**: callers (`jal`/`j`), `lui`/`addiu` address loaders, vtable slot words and data words of
  both sides, the prototype ones mapped to release through the map;
- **B, own sequence**: each pair's ordered calls and function/vtable address loads, prototype targets mapped
  (vtables through the RTTI table pairing), aligned; every non-equal stretch read;
- **C, callers' sequences**: the same for every paired caller or loader of a list function outside the list,
  stretches touching a list function read;
- **D, vtables**: every paired table with a slot in the list, slot by slot, and unpaired tables;
- **E, twins**: rows with byte-identical twins (jal targets masked) on either side, each release twin scored by
  the prototype side's mapped callers and slots; ties decided by the call order in the shared caller or the slot;
- **F, data**: function-pointer data words and their neighbours, mapped; plus the keyed/index tables of
  `tables.py` holding a list function (only the static-initialiser table, whose order agrees for every list sinit).

The owner-file ranges in the list headers run up to the sinit functions at 0x48xxxx and so overlap most of the
image; the pass used the list rows plus the paired rows lying between list rows without an owner of their own
(one: zArchive 0x1dc380 `end__Q23std42__list_deleter<PCv,...>CFv`). Result: **no wrong pair in any of the four
lists**. Every difference is a caller that moved, was inlined or outlined, or code added or dropped; the
prototype's list-to-vector change in zArchive and the CAiState stack rewrite in zSeal account for most of the
B rows.

## gamez/zSeal, list a

398 pairs (261 deviating, 137 exact). A: 86 pairs differ, 36 of them only by the slot index of a vtable that
gained slots. B: 119 pairs. C: 203 paired callers, 48 with a stretch touching the list. D: 12 tables, 11 differ,
all by inserted slots (CZSealBody 3 + 2 in the secondary table; every CAiS* table one at slot 1 and two at the
end) and two new overrides of `CAiState::CanPushAiState` (CAiSBreach 0x2ec8b0, CAiSScript 0x2ed1b0); no slot of a
paired function moves to another function. E: 39 twin rows, 13 ties, all decided. F: 1 (HandleFallingDamage's
address in a table of unaligned code addresses at 0x44e544, not a pointer table).

| release | prototype | difference | verdict |
|---|---|---|---|
| 0x2536b0 | 0x24ee90 `ExecuteAction_KnifeAttack` | byte twin of new 0x253700 (same caller OnActionButton); calls new 0x27a890, not StabBuddy | right: 0x253700 calls CrouchToPickupBuddy (a new pick-up action); 0x27a890 aligns, then calls back 0x27aac0, which calls StabBuddy (0x27a660). The same wrapper pattern for ApplyRestraint (0x27a420 / 0x27a650 / RestrainBuddy) |
| 0x2a0e70 / 0x2a0ef0 | `GetArmDamage` / `GetLegDamage` | byte twins, `position` evidence, one shared caller | right: UpdateLocalSeal calls Leg, Leg, Arm, Arm on both sides |
| 0x2efa10 / 0x2efa60 | `GetAiState` const / non-const | byte twins; callers moved both ways | right: 11 of 11 and 30 of 34 prototype callers shared; GetDefaultRouteType switched overload |
| 0x2a5340 | `IsThrowing(bool)` (exact) | no release caller left | inlined into new 0x297df0 (HandleFireWeapon's IsThrowing + CanFire test) and new 0x2afad0 (OKToPeek) |
| 0x2a5100, 0x2a51d0 | `IsChangingWeapons`, `IsReloading` | ChangeWeapon, CanFire, Reload, CanZoom no longer call them | the tests moved into new 0x2afad0 (inlines IsChangingWeapons, calls IsReloading), called by those and the CanUse* functions |
| 0x2f33c0, 0x268820 | `SetAiEvent`, `SetAiAware(AI_AWARE, const CPnt3D*)` | CAiSGrenade::Tick, OnWeaponHit, OnWeaponEvent replace GetAiAware/SetAiEvent/SetAiAware(f,Ui) | the prototype had SetAiAware(AI_AWARE,...) inlined there (it is SetAiEvent's caller on both sides); now called, or via new 0x25f0c0 |
| 0x254500, 0x255900 | `NormalizeToTerrain`, `HandleWeaponIntersect` (`position`, caller-mismatch) | caller PostComputeNextPosition becomes PostTick / Tick | moved with their guards (Top/LinearWeight before HandleWeaponIntersect); bodies 0.80 / 0.84 alike |
| 0x2b1120 | `GetTerrainMotionFactor` | caller Tick becomes MoveControl, CrouchMoveControl | moved (sqrtf calls dropped release-wide, so the stretch aligns against them) |
| 0x2ef150, 0x2ef610, 0x2efab0, 0x2efef0, 0x2ed290, 0x2eea20 | the CAiState stack | new callers CAiSBreach/CAiSGoto::Tick, CSealCtrl::SensorPreTick | PushAiState inlined there; the CSealCtrlAi::SensorPreTick block moved to CSealCtrl::SensorPreTick; `Create` builds through new 0x2f0ae0/0x2f0b00; CAiSCorpse (vtable 0x472900) removed |
| 0x2526c0, 0x2527d0 | `DeleteAnchor`, `CreateAnchor` | five callers replaced by new 0x251770 / 0x2517a0 | the removed CompassAnchor_Hostage and its anchor code went into the two new helpers |
| 0x29cba0 | `GetMPStats` (slot-only, confirmed in zSeal-a) | 28-byte body | right, as zSeal-a says: same caller and stats offsets, copy tail-called in new 0x2532f0 |

Everything else in A–C: calls added (HandleKiller, DropMPBomb, SetWeaponState, GetWeaponState, ClearLook, ...),
dropped (Debug/Output, get_state, sqrtf, IsCurrentBlend inlined as BaseAnim reads) or moved into new helpers
(0x300940 look setup, 0x254020 damage, 0x2a3230, 0x2b89a0 for the removed ChangeItemModel). The empty 8-byte
virtuals (CanAttack, CanPursue, Tick of CAiSCQBAttack, CAiSUnknown, CAiSSuspended, CAiSBreach) are decided
by their slot after the inserted slot 1. Wrong pairs: none.

## gamez/zArchive, list a

71 pairs (39 deviating, 32 exact) plus the unowned interior row 0x1dc380. A: 20. B: 32. C: 134 callers, 11. D:
1 table (CZAR), equal. E: 24 twin rows, 5 ties, all decided. F: 0.

| release | prototype | difference | verdict |
|---|---|---|---|
| 0x1dc8d0 / 0x1dc9a0 | `Securify` / `Unsecurify` | byte twins, tie on shared callers | right: 0x1dc8d0 is called only by WriteDirectory and CKey::Write (the writers), 0x1dc9a0 also by ReadDirectory, Fetch, FetchString |
| 0x1dbce0 / 0x1dbd10 | `__as__` list_imp / list<CKey*> (settled) | byte twins, one caller | right: the call order in `vector_imp<CKey>::insert` agrees (as settled) |
| 0x1dc4e0 / 0x1dc5a0 | `first__compressed_pair_imp` (48 / 158) | byte twins, shared callers | right: call order in init and list_imp::init agrees; only 0x1dc4e0 is called by sort |
| 0x1daca0 | `data__vector_deleter<CKey>` | twin of data__vector_pod 0x172f50 | right: sole caller CreateKey on both sides |
| 0x1db0e0 | `vector_deleter<CKey>::swap` (exact-caller) | release callers Close(b), Close(), ~CZAR are the prototype callers of the removed twin `std::swap<CKey>` (0x1d9740) | right: in ~CZAR the call sits where the prototype called the member swap (the ct/clear/swap block before the inlined Close); zArchive's "std::swap inlined" stands |
| 0x1d9b50, 0x1da250, 0x1db160, 0x1dacb0 | WriteDirectory, ReadDirectory, Close, Open | Open and ~CZAR call Close instead of inlining it; ReOpen calls Open | moved/outlined |
| list helpers | `__ct__`/`__as__` list_imp, init, list_deleter ctor | now call vector_pod functions or are called by do_assign | the CKey children list became a vector (as settled) |

Wrong pairs: none.

## gamez/zMPEG, list a

38 pairs (25 deviating, 13 exact). A: 11. B: 16. C: 9 callers, 3. D: none. E: 2, no tie. F: 0. The differences
are the playback restructuring zMPEG.md describes: playPss is called from Tick, not Run; the audio
reset/delete block moved from playPss to tickPss; fillBuff and initPssAudio inlined (callbacks call
sceMpegDemuxPss directly); loadImage and new 0x3520d0 called from startPss; End called from
RestartBackgroundMPEG; IdleTick from playPss; zVid_Swap and TickMPEG reorder. Wrong pairs: none.

## gamez/zNetwork, list a (zNetCnf.cpp, zNetDme.cpp)

31 pairs (16 deviating, 15 exact). A: 5. B: 13. C: 96 callers, 4. D: none. E: 7 twin rows, no tie (the two
64-byte client-index getters score 9 vs 6 and 13 vs 6, the two 56-byte getters 2 vs 0 and 38 vs 0). F: 0.
Differences: zNetGetObject's callers NumActiveSeals/NumActiveTerrorists (removed) became six new functions;
LibNETSetup is called by CNetCnf::Init instead of InitFromCombo, which now goes through new 0x404130 (it also
loads CHNetCnf::IOPRebootHandler); CLoadState::Tick dropped zNetGetValidGameClientCount with its sprintf.
Wrong pairs: none.

## Settled pairs (tool input)

No counterpart changes. These rows had only position evidence or a twin tie; the basis below decides them.
In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x2a0e70 | 0x2949f0 | byte twin of GetLegDamage; UpdateLocalSeal calls Leg, Leg, Arm, Arm on both sides | socom-release-xcheck-1 | 2026-11-26 | | |
| 0x2a0ef0 | 0x294a70 | byte twin of GetArmDamage; UpdateLocalSeal calls Leg, Leg, Arm, Arm on both sides | socom-release-xcheck-1 | 2026-11-26 | | |
| 0x2536b0 | 0x24ee90 | byte twin of new 0x253700, which calls CrouchToPickupBuddy; this one reaches StabBuddy through new 0x27a890/0x27aac0 | socom-release-xcheck-1 | 2026-11-26 | | |
| 0x1dc8d0 | 0x1db270 | byte twin of Unsecurify; called only by WriteDirectory and CKey::Write on both sides | socom-release-xcheck-1 | 2026-11-26 | | |
| 0x2eb090 | 0x2d7a60 | empty twin; CAiSCQBAttack slot 5 -> 6 after the inserted slot 1 | socom-release-xcheck-1 | 2026-11-26 | | |
| 0x2eb270 | 0x2d7c40 | empty twin; CAiSUnknown slot 1 -> 2 after the inserted slot 1 | socom-release-xcheck-1 | 2026-11-26 | | |

## How the tool did

Cross-check (pairs compared, differences looked at, pairs wrong):

- zSeal a: 398 pairs; 86 reference, 119 own-sequence, 48 caller-sequence, 11 vtable and 13 twin-tie differences; 0 wrong.
- zArchive: 72 pairs; 20 reference, 32 own-sequence, 11 caller-sequence and 5 twin-tie differences; 0 wrong.
- zMPEG: 38 pairs; 11 reference, 16 own-sequence, 3 caller-sequence differences; 0 wrong.
- zNetwork (zNetCnf, zNetDme): 31 pairs; 5 reference, 13 own-sequence, 4 caller-sequence differences; 0 wrong.

The 28 `settled` rows of these lists all agree with the comparison, and so do the earlier notes' verdicts on
the two rows that look odd at first sight (0x1db0e0's swap twin, 0x29cba0's slot-only GetMPStats).
