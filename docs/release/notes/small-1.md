# Stage 2: six small modules, batch small-1 (2026-11-26)

One list (a) for each of `Apps/FTS` (the top level: main.cpp, options.cpp, getopt.cpp, aidemo.cpp),
`gamez/zEntity`, `gamez/zSound`, `gamez/zVideo`, `gamez/zSystem` and `gamez/zBody`, each made with
`compare.py --lists <module> --split 1` and checked from its sheet (`--sheet <module> --list a`).
Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`); checked by
`socom-release-check-small-1`, who did not write the tool, at HEAD f9354c10. Both images were decoded
with the release tools; callers were found by scanning both images for `jal`/`j`, `lui`/`addiu`
address loads, vtable slots and data words. Ghidra was not needed.

The guard on the committed pairs, per module: every paired row of the owner files, and every row
inside the list's owner-file address ranges whatever its owner (446 pairs in all), had its callers,
address loaders, vtable slots and data-word counts compared with the prototype's through the map, and
its own ordered calls and address loads compared for substitutions; the ordered calls of every paired
caller of those rows were compared; every vtable with a slot in the ranges was aligned slot by slot;
every paired row with a byte twin was scored by shared callers, and ties with callers were decided by
the call position in the shared caller. The range pass found two of the four wrong committed pairs below:
their rows have no owner or another module's owner, so an owner-only pass misses them.

## Apps/FTS

List a: 13 uncertain rows (4 removed, 9 new), 15 sampled deviating rows of 20, 18 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x140460 `release__15_zmalloc<4four>FPv` | removed | confirmed | inlined: the release string reserve and destructor call `__dl__` and the state destructors carry four inline pool-range checks (the four pools at 0x48ee20/40/60/80) |
| - | 0x1404b0 `release__17_zmalloc<6twelve>FPv` | removed | confirmed | the same |
| 0x140760 | - | new | confirmed | `__dt__12CRebootStateFv`: slot 0 of the table the release RTTI names CRebootState (0x48c600); its constructor 0x43d500 is called by `__sinit_main.cpp` at COurGame+556 |
| 0x140980 | - | new | confirmed | `__dt__14CShutdownStateFv`: slot 0 of CShutdownState (0x48c5d0); constructor 0x432810 called by `__sinit_main.cpp` at COurGame+548. The hand-over holds |
| 0x1416d0 | - | new | confirmed | reboot to the disc executable: new 0x30c310 (IOP shutdown), CPipe::Uninit, scePadEnd, sceCdInit(5), sceSifExitCmd, LoadExecPS2 of "cdrom0:\SCUS_971.34;1" or "host0:./ftsd0.elf" by a zSys flag; callers zVid_Assert and CGameMenu::SwitchMenu |
| 0x142480 | - | new | confirmed | constructor of a new 16-byte pool (stores 16 at +0xc, calls 0x1424c0); `__sinit_main.cpp` builds it with 12500 |
| 0x1424c0 | - | new | confirmed | its init_page: calloc(16, n) at main.cpp:106 |
| 0x142560 | - | new | confirmed | constructor of a new 20-byte pool (stores 20, calls 0x1425a0); built with 4700 |
| 0x1425a0 | - | new | confirmed | its init_page: calloc(20, n) at main.cpp:106 |
| 0x142cf0 | - | new | confirmed | acquire of the 20-byte pool: malloc(20) at main.cpp:136; `allocate<c>`'s size-20 branch with the pool at 0x48ee20 |
| 0x142ea0 | - | new | corrected to 0x141710 `acquire__15_zmalloc<4four>FUi` | malloc(4); `allocate<c>`'s size-4 branch, with the pool object (0x48ee80) that `__ct__15_zmalloc<4four>` builds in `__sinit_main.cpp` |
| - | 0x173e30 `process_arguments__FiPPc` | removed | corrected to 0x1735e0 | the same call site, main's second call after mwInit; the same prologue (init$2590 guard, opt_string, m_LoadFromZAR set) and getopt loop; only the `-m` switch is left |
| - | 0x17de80 `plot_tick__2aiFfb` | removed | confirmed | its only caller CHUD::StatusLine is removed |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x1401e0 | 0x1401e0 `__dt__8COurGameFv` | yes | slot 0 of COurGame; shared caller `__sinit_main.cpp` |
| 0x140610 | 0x140550 `StartEngine__8COurGameFv` | yes | slot 3 of COurGame; shared caller main |
| 0x140ba0 | 0x140680 `__dt__12CMPExitStateFv` | yes | slot 0 of CMPExitState |
| 0x140dd0 | 0x1407e0 `__dt__10CExitStateFv` | yes | slot 0 of CExitState |
| 0x141000 | 0x140940 `__dt__10CMenuStateFv` | yes | slot 0 of CMenuState |
| 0x141240 | 0x140ab0 `__dt__9CSaferStrFv` | yes | 10 shared callers |
| 0x141420 | 0x140bc0 `__dt__10CGameStateFv` | yes | slot 0 of CGameState |
| 0x141780 | 0x140e10 `__dl__FPv` | yes | 11 shared callers |
| 0x141cb0 | 0x1410f0 `reserve__...basic_string...FUi` | yes | shared callers CGameMenu ctor, ZuiInit |
| 0x141f60 | 0x141410 `__dt__...basic_string...Fv` | yes | dozens of shared callers |
| 0x142300 | 0x141870 `init_page__15_zmalloc<4four>Fv` | yes | called by the 4four constructor; calloc(4, n) |
| 0x1423e0 | 0x141930 `init_page__17_zmalloc<6twelve>Fv` | yes | called by the 6twelve constructor; calloc(12, n) |
| 0x1429a0 | 0x141d00 `reserve__...CharArrayFUi` | yes | shared caller CMenuState ctor |
| 0x142d80 | 0x141710 `acquire__15_zmalloc<4four>FUi` | **no** | malloc(16): the acquire of the new 16-byte pool (`allocate<c>`'s size-16 branch, pool 0x48ee40 built by 0x142480). The 4four acquire is 0x142ea0 |
| 0x142e10 | 0x1417a0 `acquire__17_zmalloc<6twelve>FUi` | yes | malloc(12); size-12 branch; pool built by the 6twelve constructor |

### Settled pairs (tool input)

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x142ea0 | 0x141710 | malloc(4); allocate<c>'s size-4 branch with the pool built by __ct__15_zmalloc<4four> in __sinit_main.cpp | socom-release-check-small-1 | 2026-11-26 | | |
| 0x142d80 | new | malloc(16); allocate<c>'s size-16 branch with the pool built by new ctor 0x142480 (12500) | socom-release-check-small-1 | 2026-11-26 | src/Apps/FTS/main.cpp | |
| 0x1735e0 | 0x173e30 | main's call after mwInit; init$2590/opt_string prologue and getopt loop; only -m left | socom-release-check-small-1 | 2026-11-26 | src/Apps/FTS/options.cpp | |

Rows that change together: 0x142ea0 and 0x142d80 (the 4four counterpart moves from the second to the
first).

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x140760 | CRebootState destructor | `__dt__12CRebootStateFv` (RTTI-named table, slot 0) |
| 0x140980 | CShutdownState destructor | `__dt__14CShutdownStateFv` (the same) |
| 0x1416d0 | shuts the IOP and pad down and LoadExecs the disc (or host) executable | guess: `Reboot__Fv` |
| 0x142480 / 0x142560 | constructors of new 16- and 20-byte zmalloc pools | guess: `__ct__18_zmalloc<7sixteen>FUi`, `__ct__17_zmalloc<6twenty>FUi` (template family, by element size) |
| 0x1424c0 / 0x1425a0 | their init_page | guess: `init_page__18_zmalloc<7sixteen>Fv`, `init_page__17_zmalloc<6twenty>Fv` |
| 0x142d80 / 0x142cf0 | their acquire | guess: `acquire__18_zmalloc<7sixteen>FUi`, `acquire__17_zmalloc<6twenty>FUi` |

Removed: the two zmalloc `release` instances (inlined into the string and state code). `plot_tick`:
its caller is gone. Not removed, though the map has it: process_arguments (0x1735e0).

`__sinit_main.cpp` also builds the two new states; the pools shrank (6twelve 0x10000 -> 8000, 4four
8192 -> 11350) and COurGame's state members moved (+448 -> +464 for CExitState).

## gamez/zEntity

List a: 11 uncertain rows (10 new, 1 removed), 15 sampled deviating rows of 35, 62 exact rows. The
hand-overs were tested.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1efcd0 | - | new | confirmed | CEntity slot 12 (+0x38), a new virtual: copies the cached position (+0x1c) to a1. CZSealBody overrides it with new 0x29db40, the world position of the body part at +0x290 |
| 0x1efcf0 | - | new | confirmed | CEntity slot 11 (+0x34), the same body; CZSealBody override 0x29dc10 uses the part at +0x28c. 0x1efd10, 0x1efcf0 and 0x1efcd0 are byte twins told apart by slot (10, 11, 12) |
| 0x1f1100 | - | new | confirmed | CEntity static: `m_list.erase(remove_if(begin, end, 0x1f1210), end)`, then renumbers the list (entity +8); caller CMPExitState::Tick |
| 0x1f1210 | - | new | confirmed | its predicate: an entity whose id (+4) is -1 is deleted (virtual slot 0 with 1) and removed |
| 0x1f1310 | - | new | confirmed | `remove_if` over a `list<CEntity*>` with a function predicate (byte twin of the CSched_Task instance 0x30b740) |
| 0x1f1470 | - | new | confirmed | the matching `remove_copy_if` (twin of 0x30b830) |
| - | 0x1ef980 `Update__7CTargetFP7CEntityP7CEntity` | removed | confirmed | inlined into its only caller UpdateTargetList, which now subtracts the two cached positions (+0x1c) directly |
| 0x1f38f0 | - | new | confirmed | CEntity slot 7 (+0x24), empty; the hand-over holds (0x1f3940 PreTick ... 0x1f3900 PostTick, then this). PostTickAll calls it with dt in a third loop, after PostTick and before slot 1 (0x1effc0); CZSealBody overrides it with new 0x25a6d0 |
| 0x250b80 | - | new | confirmed | deletes the MP bomb node (m_mpbombnode): parent notified, texture asset character deleted, node deleted, pointer cleared; caller new 0x298220 |
| 0x250c90 | - | new | confirmed | (point, dt): walks the pickups of types 8 and 9, ages their timer, and destroys those farther than 300 from the point; caller CMission::Tick |
| 0x250e30 | - | new | confirmed | the bomb-node delete of 0x250b80 behind a bool (0x48d904) which it clears; callers CMission::Tick and ftsNetworkGameUninit |

Sampled deviating rows: all 15 are the same function on both sides.

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x1efea0 | `TeleportTo__7CEntityFPC7CMatrix` | yes | CEntity slot 14 (prototype 11, three slots inserted before it); shared caller CZSealBody::TeleportTo |
| 0x1f00c0 | `GetNode__7CEntityFv` | yes | 9+ shared callers |
| 0x1f00d0 | `__dt__7CEntityFv` | yes | slot 0; shared callers ~CZSealBody, ~CTurret |
| 0x1f0190 | `__ct__7CEntityFQ27CEntity4TYPEPQ23zdb5CNode` | yes | four shared callers |
| 0x1f05c0 | `PostTickAll__7CEntityFfPv` | yes | shared caller CCoreState::Init; the PrePostTick and PostTick loops |
| 0x1f1610 | `GetRange__7CTargetFv` | yes | four shared callers |
| 0x1f1f70 | `OnUpdateTargetList__7CEntityFbb` | yes | shared caller UpdateTargetList |
| 0x1f37e0 | `ComputeNextPosition__7CEntityFf` | yes | CEntity slot 8 (prototype 7) |
| 0x250520 | `CleanupAmmoPickup__7CPickupFP7CPickup` | yes | shared caller HandlePickupAck |
| 0x250740 | `FindPickup__7CPickupFUi` | yes | five shared callers |
| 0x250be0 | `DestroyNetPickups__7CPickupFUc` | yes | shared caller CZSealBody::OnMissionEnd |
| 0x2511f0 | `Create__7CPickupF...` | yes | eight shared callers |
| 0x251400 | `GetVisibleByUnit__7CPickupFUi` | yes | shared caller SensorPreTick |
| 0x251420 | `NetworkCreate__7CPickupF...` | yes | shared callers DropItem, DropAmmo |
| 0x251550 | `Close__7CPickupFb` | yes | three shared callers |

Found by the range pass, outside the list's rows:

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1effc0 | 0x177290 `GetPosW__7CEntityCFv` (owner orders.cpp) | deviating, vtable-slot | corrected to new | the slot is the same (CEntity and CZSealBody slot 1), the function is not. The prototype getter returned the node's translation (node +0x1c, +0x30). The release body returns nothing (v0 unset) and writes: it copies the node's translation (the node pointer is now at +0x28) into the entity's +0x1c..+0x24. PostTickAll calls it after every PostTick; GetTargetPosW, the two new slot-11/12 virtuals and the inlined CTarget::Update read that cache. GetPosW is gone as a function: its readers use the cached +0x1c inline |

### Settled pairs (tool input)

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x1effc0 | new | CEntity slot 1 is now a void update that caches the node translation at +0x1c; no return value; called by PostTickAll after PostTick | socom-release-check-small-1 | 2026-11-26 | src/gamez/zEntity/ent_main.cpp | |
| removed | 0x177290 | GetPosW's readers read the cached position at +0x1c inline (GetTargetPosW, UpdateTargetList); no release getter | socom-release-check-small-1 | 2026-11-26 | | |

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x1effc0 | caches the node's world translation at +0x1c | guess: `UpdatePosW__7CEntityFv` |
| 0x1f38f0 | empty third post-tick phase, slot 7 | guess: `PostPostTick__7CEntityFf` |
| 0x1efcf0 / 0x1efcd0 | slot 11 / 12: a position, the entity's by default, a body part's (+0x28c / +0x290) for CZSealBody | guess: `GetHeadPosW__7CEntityFP6CPnt3D` / `GetNeckPosW__7CEntityFP6CPnt3D` (if the release keeps the prototype's part order, m_head +0x28c, m_neck +0x290; not checked) |
| 0x1f1100 | removes and deletes the entities with id -1, renumbers the list | guess: `PurgeInvalid__7CEntityFv` |
| 0x1f1210 | its predicate | guess: `IsInvalid__7CEntityFP7CEntity` |
| 0x1f1310 / 0x1f1470 | `remove_if` / `remove_copy_if` instances over `list<CEntity*>` | the template names, by the twins' symbols |
| 0x250b80 | deletes the MP bomb node | guess: `DestroyMPBombNode__7CPickupFv` |
| 0x250c90 | expires far dropped pickups of types 8 and 9 | guess: `TickDroppedPickups__7CPickupFPC6CPnt3Df` |
| 0x250e30 | the bomb-node delete behind its flag | guess: `CleanupMPBomb__7CPickupFv` |

Removed: CTarget::Update (inlined); CEntity::GetPosW (above).

Layouts, plainly shown by settled rows: CEntity holds a cached world position at +0x1c and its node
pointer moved from +0x1c to +0x28 (UpdateNextPosition writes +0x38.. where the prototype wrote +0x2c..);
the CEntity vtable grew from 18 to 21 slots (+0x24, +0x34, +0x38 inserted).

## gamez/zSound

List a: 11 uncertain rows (6 new, 1 unsure, 3 weak pairs (2 `slot-only`, 1 `role-only`), 1 removed),
15 sampled deviating rows of 53, 77 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x302a20 | - | new | confirmed | ticks the group-volume fade timer (0x48e374) by dt and calls ResetGroupVolTemp when it runs out; caller CMenuState::Tick |
| 0x302ab0 | 0x2ebdb0 `SetGroupVolTemp__4CSndFffiiiiiii` | unsure, position, caller-mismatch | confirmed (deviating) | the same statics (fade time, fade percentage, the seven fade groups, the old volumes) and the same snd_GetMasterVolume / snd_SetMasterVolume loop over seven groups; it now calls ResetGroupVolTemp first. Its caller changed: OnStunDamage dropped it, HandleGrenadeExplosion and StreamSoundVolPan call it |
| 0x306200 | 0x2ef190 `ResumeAllSounds__12CSndInstanceFv` | deviating (weak), slot-only | confirmed | shared caller ClosePauseMenu; the list walk became one call to new snd 0x301ad0 |
| 0x306230 | 0x2ef260 `PauseAllSounds__12CSndInstanceFv` | deviating (weak), slot-only | confirmed | shared caller OpenPauseMenu; new snd 0x301b00, still sets m_allpaused |
| 0x306400 | 0x2ef540 `UIStopAllSounds__12CSndInstanceFv` | deviating (weak), role-only | confirmed | shared caller the UIStopAllSounds anim command; new snd 0x301b30 |
| 0x306430 | - | new | confirmed | for every instance: stores 1.5 at +0x20 and calls 0x306bf0(0.0, 1.5), a fade-out of everything; caller 0x1d1840, a command handler in the table at 0x44a954 |
| - | 0x2efa80 `AwarenessUpgrade__12CSndInstanceFUi` | removed | corrected to 0x3068b0 | see the range pass below |
| 0x306bf0 | - | new | confirmed | (vol, time): waits for the instance's handle (snd_FlushSoundCommands, up to 500 times) and calls snd_AutoVol(handle, vol x 1024 x master, time x 240, 2) |
| 0x307140 | - | new | confirmed | an empty walk over m_instancelist (the body compiled away); caller CMission::Close |
| 0x307350 | - | new | confirmed | CSndGroup slot 9 (+0x2c), new: calls slot 9 on every member sound (vector at +0x4c/+0x50). CSnd's slot 9 is new 0x24bcf0, which writes 3 to byte +0x24 |
| 0x308640 | - | new | confirmed | the jukebox's queue and fade step, split out of CSndJukebox::Tick (which called Play where it now calls IsFading/FadeOut and this); caller Tick |

Sampled deviating rows: all 15 are the same function on both sides.

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x302cc0 | `SetReverbDepth__4CSndFPCf` | yes | shared caller CMission::PreOpen |
| 0x303340 | `StreamSoundVolPan__4CSndFiiP12CSndInstance` | yes | three shared callers |
| 0x303720 | `CalcVolPan__4CSndFPC6CPnt3DfPiPi` | yes | shared caller CSndInstance::Tick |
| 0x303920 | `PlaySound3D__4CSndF...` | yes | slot 7 of CSnd and CSndGroup |
| 0x304920 | `LoadBank__4CSndFPCc` | yes | shared caller LoadSounds |
| 0x304bc0 | `LoadSounds__4CSndFPCcPCc` | yes | four shared callers |
| 0x3050d0 | `Open__4CSndFv` | yes | shared caller CMission::OnMissionStart |
| 0x3051b0 | `NetOpen__4CSndFv` | yes | the same |
| 0x306260 | `StopAllSounds__12CSndInstanceF10SOUND_MODE` | yes | shared caller OnListenerDeath |
| 0x3064e0 | `IsPlaying__12CSndInstanceFv` | yes | five shared callers |
| 0x306540 | `FadeOut__12CSndInstanceFf` | yes | three shared callers |
| 0x3068e0 | `Remove__12CSndInstanceFUibb` | yes | four shared callers |
| 0x3079e0 | `PlaySoundVolPanPitch__9CSndGroupF...` | yes | slot 4 of CSndGroup |
| 0x308010 | `NormalizeWeights__11CSndJukeboxF10MUSIC_MODE` | yes | shared caller PlayRandom |
| 0x308e80 | `FadeOut__17CSndSequenceEntryFv` | yes | shared caller CSndSequence::FadeOut |

Found by the range pass, outside the list's rows:

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x3068b0 | 0x142140 `_dpfgt` (MW runtime, no owner) | deviating, call-deviating | corrected to 0x2efa80 `AwarenessUpgrade__12CSndInstanceFUi` | a CSndInstance wrapper, `if (!m_isDisabled) Remove(id, true, false)`, between PostTick and Remove where AwarenessUpgrade was. Its one caller, CSealCtrlAi::Tick, calls it right after CValve::MakeCallbacks, AwarenessUpgrade's call site; the debug block that called `_dpfgt` there is gone. `_dpfgt` (a double compare) has no release copy: the release has `_dpflt` (0x142f40) only, and `_dpfgt`'s other prototype callers (Dilate, CAiSPursue::Tick, CAiSEvent::Tick, _store_frame_data) do not call 0x3068b0 |

### Settled pairs (tool input)

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x3068b0 | 0x2efa80 | AwarenessUpgrade's call site in CSealCtrlAi::Tick (after MakeCallbacks); slot between PostTick and Remove; body Remove(id, true, false) | socom-release-check-small-1 | 2026-11-26 | src/gamez/zSound/zsnd_csndinstance.cpp | |
| removed | 0x142140 | _dpfgt: no release copy (only _dpflt); its callers' debug and double compares are gone | socom-release-check-small-1 | 2026-11-26 | | |
| 0x302ab0 | 0x2ebdb0 | the same fade statics and seven-group master-volume loop; callers moved to HandleGrenadeExplosion and StreamSoundVolPan | socom-release-check-small-1 | 2026-11-26 | | |
| 0x306200 | 0x2ef190 | shared caller ClosePauseMenu | socom-release-check-small-1 | 2026-11-26 | | |
| 0x306230 | 0x2ef260 | shared caller OpenPauseMenu | socom-release-check-small-1 | 2026-11-26 | | |
| 0x306400 | 0x2ef540 | shared caller the UIStopAllSounds anim command (0x1d1860) | socom-release-check-small-1 | 2026-11-26 | | |

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x302a20 | ticks the group-volume fade timer | guess: `TickGroupVolTemp__4CSndFf` |
| 0x306430 | fades every instance out over 1.5 s | guess: `FadeOutAllSounds__12CSndInstanceFv` |
| 0x306bf0 | fades one instance to a volume over a time | guess: `FadeTo__12CSndInstanceFff` |
| 0x307140 | empty instance-list walk (debug body removed) | guess: `DumpInstances__12CSndInstanceFv` |
| 0x307350 | CSndGroup override of the new slot 9 | unnamed: slot 9 writes 3 to CSnd byte +0x24 (perhaps m_soundmode); name not guessed |
| 0x308640 | the jukebox's queue and fade step | guess: `ProcessQueue__11CSndJukeboxFv` |

Removed: `_dpfgt` (above). Not removed, though the map has it: AwarenessUpgrade (0x3068b0).

Layouts: the CSnd and CSndGroup vtables grew from 9 to 10 slots (+0x2c).

## gamez/zVideo

List a: 10 uncertain rows (1 weak pair, 2 new, 3 committed rows flagged `caller-mismatch`, 4 removed),
all 10 deviating rows sampled, 13 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x31ee50 | 0x307a40 `zVid_Assert__FbUiPci` | deviating (weak), slot-only | confirmed | the seven debug allocators (`_strdup` ... `_new`) call it on both sides. On a failed assert it now calls new 0x1416d0 (reboot) instead of printing through CTTY |
| 0x31f630 | - | new | confirmed | (x, y, w, h): writes an offset and a limit pair, built from 2048-centred 12.4 coordinates, into two GS register words of a static packet at 0x44bc60 (uncached); callers CCinematicState::Init and UnInit |
| 0x31f6c0 | - | new | confirmed | (a, b, c, d): packs four 12.4 coordinates into the two words before them; the same callers |
| 0x31fa40 | 0x308590 `zVid_Open__Fv` | exact, caller-mismatch | confirmed | equal bytes; the video start-up moved from CGame::StartEngine into CIOPManager::RebootIOP, which calls zVid_Init, zSysReset, zVid_Open, RestoreImage and zVid_Swap in a row (the prototype StartEngine: zVid_Init, zSysReset, zVid_Open) |
| 0x31fb20 | 0x308690 `zVid_Init__F10_zvid_mode` | deviating, position, caller-mismatch | confirmed | similarity 0.892; the same move; it still calls zvid_SetVideoMode; the CTTY constructor call is gone |
| 0x3200b0 | 0x308c20 `RestoreImage__6CVideoFPc` | deviating, position, caller-mismatch | confirmed | similarity 0.988, `imm-only`; moved from COurGame::StartEngine into RebootIOP |
| - | 0x308f40 `Render__4CTTYFv` | removed | confirmed | callers zVid_Assert and zVid_Swap no longer call it |
| - | 0x309030 `Print__4CTTYFPci` | removed | confirmed | only caller zVid_Assert |
| - | 0x309180 `__dt__4CTTYFv` | removed | confirmed | only caller zVid_Uninit, now empty |
| - | 0x309200 `__ct__4CTTYFv` | removed | confirmed | only caller zVid_Init, which dropped it |

Sampled deviating rows: all 10 are the same function on both sides.

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x31eb90 | `Brightness__6CVideoFf` | yes | shared caller CBrightnessTuner::UpdateUIVar |
| 0x31ed90 | `zVid_ZTestOn__Fv` | yes | shared caller CCoreState::Tick |
| 0x31edf0 | `zVid_ZTestOff__Fv` | yes | the same |
| 0x31ee70 | `zVid_FrameRestore__Fv` | yes | shared caller CPipe::RenderWorld |
| 0x31eed0 | `zVid_Swap__Fb` | yes | seven shared callers |
| 0x31f730 | `zvid_MpegReset__Fv` | yes | shared caller zVid_Swap |
| 0x31fb10 | `zVid_Uninit__Fv` | yes | the same call position (18) in CGame::StopEngine among its empty byte twins; the body is empty now (CTTY gone) |
| 0x31fb20 | `zVid_Init__F10_zvid_mode` | yes | above |
| 0x31fc50 | `zvid_SetVideoMode__F10_zvid_modeb` | yes | shared callers zVid_Swap, zVid_Init |
| 0x3200b0 | `RestoreImage__6CVideoFPc` | yes | above |

### Settled pairs (tool input)

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x31ee50 | 0x307a40 | the seven debug allocators call it on both sides | socom-release-check-small-1 | 2026-11-26 | | |
| 0x31fa40 | 0x308590 | equal bytes; video start-up moved from CGame::StartEngine to CIOPManager::RebootIOP | socom-release-check-small-1 | 2026-11-26 | | |
| 0x31fb20 | 0x308690 | the same move (zVid_Init, zSysReset, zVid_Open order kept); still calls zvid_SetVideoMode | socom-release-check-small-1 | 2026-11-26 | | |
| 0x3200b0 | 0x308c20 | imm-only, similarity 0.988; moved from COurGame::StartEngine to RebootIOP | socom-release-check-small-1 | 2026-11-26 | | |

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x31f630 | sets a GS offset/limit pair in a static packet | guess: `zVid_SetOffset__Fiiii` |
| 0x31f6c0 | sets a GS rectangle in the same packet | guess: `zVid_SetScissorRect__Fiiii` |

Removed: the whole CTTY class (Render, Print, constructor, destructor): its only users were
zVid_Assert, zVid_Swap, zVid_Init and zVid_Uninit, which dropped it.

## gamez/zSystem

List a: 9 uncertain rows (5 removed, 3 new, 1 committed row flagged `caller-mismatch`), 15 sampled
deviating rows of 19, 41 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x2f3730 `Reset__6CBenchFv` | removed | confirmed | its only caller CCoreState::Tick dropped the call (the hand-over holds). Nothing is left of CBench: the release CCoreState::Tick no longer stores the ten bench timers, and the seven render functions that bumped its counters (CClutter::Render, RenderUiNodeRecursive, CAlpha::Render and Add, RenderVisual, RenderMesh, RenderNode) no longer do; their reader CHUD::StatusLine is removed |
| - | 0x2f4070 `GetTask__14CSched_ManagerFUi` | removed | confirmed | only caller CHUD::StatusLine, removed |
| - | 0x2f4490 `zsys_MemoryReport__Fv` | removed | confirmed | only caller RebootIOP dropped the call |
| 0x30be90 | - | new | confirmed | converts a float rate to an integer (0x527190) and stores its reciprocal (0x527194); caller zvid_SetVideoMode |
| 0x30bf10 | 0x2f49d0 `zSysReset__Fv` | deviating, position, caller-mismatch | confirmed | similarity 0.995; moved with the video start-up from CGame::StartEngine into RebootIOP (see zVideo) |
| 0x30c310 | - | new | confirmed | RebootIOP(theIOPManager, 5), then the headset-audio shutdown 0x30ad00; callers 0x1416d0 (reboot) and slot 2 of CShutdownState and CRebootState |
| - | 0x2f5280 `InterruptDmacBusError__Fi` | removed | confirmed | zSysInit loaded it for AddDmacHandler; the release zSysInit has no AddDmacHandler/EnableIntc (and its BuildTOC moved to RebootIOP) |
| 0x30d120 | - | new | confirmed | a bool setter (0x48e404) that zSysFifoKick reads; CMenuState::Init sets it, UnInit clears it |
| - | 0x402e10 `TRC_PowerOffThread__FPv` | removed | corrected to 0x404800 | see the sampled row 0x404800 |

Sampled deviating rows:

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x30ad40 | `__dt__11CSched_TaskFv` | yes | shared callers ClearFreeList, Clear |
| 0x30b210 | `_task_cleanup__FP11CSched_Task` | yes | shared caller ClearFreeList |
| 0x30b280 | `Clear__14CSched_ManagerFv` | yes | three shared callers |
| 0x30b4f0 | `AddTask__14CSched_ManagerF...` | yes | six shared callers |
| 0x30b9e0 | `_strdup__FPCcPCci` | yes | many shared callers |
| 0x30ba70 | `_calloc__FUiUiPCci` | yes | many shared callers |
| 0x30bb60 | `_memalign__FUiUiPCci` | yes | six shared callers |
| 0x30bbd0 | `_malloc__FUiPCci` | yes | many shared callers |
| 0x30bc40 | `_new_vec__FUiPCci` | yes | shared caller `__nwa__` |
| 0x30bcf0 | `_new__FUiPCci` | yes | shared callers `__nw__`, allocate<c> |
| 0x30bf10 | `zSysReset__Fv` | yes | above |
| 0x30c360 | `zSysInit__Fv` | yes | shared caller main |
| 0x30d130 | `zSysFifoEnd__Fv` | yes | ten shared callers |
| 0x4046b0 | `TRC_PreparePowerOff` | yes | shared caller RebootIOP |
| 0x404800 | 0x402e50 `TRC_PowerOffThread_Aux__Fv` | **no** | it is the thread entry `TRC_PowerOffThread__FPv` (0x402e10) with Aux inlined: TRC_PreparePowerOff stores its address in the thread parameter's entry field where the prototype stored TRC_PowerOffThread; it takes the semaphore in a0, WaitSemas on it and loops for ever, like TRC_PowerOffThread; Aux's body (three sceDevctl, sceCdPowerOff, now also the headset-audio shutdown) follows inline. The tool's callee-check moved the pair from the entry to Aux because the call lists match Aux's |

### Settled pairs (tool input)

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x404800 | 0x402e10 | the thread entry TRC_PreparePowerOff stores (prototype: TRC_PowerOffThread); semaphore in a0, WaitSema loop; Aux inlined | socom-release-check-small-1 | 2026-11-26 | | |
| removed | 0x402e50 | TRC_PowerOffThread_Aux inlined into its only caller TRC_PowerOffThread (0x404800) | socom-release-check-small-1 | 2026-11-26 | | |
| 0x30bf10 | 0x2f49d0 | similarity 0.995; moved with zVid_Init/zVid_Open from CGame::StartEngine into RebootIOP, order kept | socom-release-check-small-1 | 2026-11-26 | | |

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x30be90 | sets an integer rate and its reciprocal from a float | guess: `zSysSetFrameRate__Fv` |
| 0x30c310 | shuts the IOP down (RebootIOP mode 5) and the headset audio | guess: `zSysShutdown__Fv` |
| 0x30d120 | sets the bool zSysFifoKick reads | guess: `zSysFifoSetMenuMode__Fb` |

Not in the list but in the CBench slot of the prototype's zsys_bench.cpp block, after ftsGetHeadset
(0x30ac30, confirmed by four shared callers): two new headset-audio helpers with no owner,
0x30ad30 (sets a flag, tail-calls lgAudInit) and 0x30ad00 (if the flag is set, calls 0x3d6350 and
clears it; callers 0x30c310, RebootIOP, TRC_PowerOffThread). Guess names `ftsHeadsetAudInit__Fv` and
`ftsHeadsetAudShutdown__Fv`; owner guess the file of ftsGetHeadset (src/Apps/FTS/game/headset.cpp).

Removed: CBench::Reset, CSched_Manager::GetTask, zsys_MemoryReport, InterruptDmacBusError,
TRC_PowerOffThread_Aux (inlined). Not removed, though the map has it: TRC_PowerOffThread (0x404800).

## gamez/zBody

List a: 7 uncertain rows (2 weak pairs, 5 new), all 15 deviating rows sampled, 72 exact rows.

### Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1e2590 | 0x1e1210 `Tick__13CBlendOverlayFP5CBodyf` | deviating (weak), position, slot-only | confirmed | the same opening (direction at +0xc, time at +8, the anim's loop flag and frame count) and calls (RTStack Top, RTArray PutBack); its frame arithmetic moved into new 0x1e29d0. Its caller moved too: CZSealBody::Tick_0's overlay step is now new 0x27b620 |
| 0x1e27c0 | 0x1e1700 `Trigger__13CBlendOverlayFP5CBodyb` | deviating (weak), slot-only | confirmed | shared caller BlendOverlayPreTick at the same three call positions; the same checks and direction store; the rest of the body is gone (84 bytes instead of 332) |
| 0x1e29d0 | - | new | confirmed | (time): wraps the time into [0, 1), stores it (+0x10), scales by the frame count, floors to the current and next frame (+0x1c, +0x1e) and the fraction (+0x18), clamped at the last frame unless looping; callers Synch, Reset, CBlendOverlay::Tick |
| 0x1e3b70 | - | new | confirmed | CBody: PopBlend until the blend stack is down to a depth; caller CZSealBody::PushBlend |
| 0x1e3c20 | - | new | confirmed | interpolates a pose (Scale, Add, Slerp); caller new 0x277ec0 |
| 0x1e3dd0 | - | new | confirmed | CBody: sets every part's node position and rotation from the part's stored pose (part vector at +0x34/+0x38); caller CSealCtrlAi::SetAiEnabled |
| 0x1e3e80 | - | new | confirmed | CBody: copies part i's position and rotation into its second pose slot (+0x28, +0x40); caller new 0x277ce0 |

Sampled deviating rows: all 15 are the same function on both sides.

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x1e10b0 | `Clear__15CZBodyAnimBlendFv` | yes | the same call positions in PopBlend and PushBlend as against Reset |
| 0x1e1720 | `ThisFoot__15CZBodyAnimBlendFv` | yes | five shared callers |
| 0x1e1920 | `Synch__15CZBodyAnimBlendFP5CBody` | yes | shared caller Tick_0, the same positions |
| 0x1e1a90 | `Propagate__15CZBodyAnimBlendFfb` | yes | shared callers Tick, Tick_0 |
| 0x1e1c90 | `IsDone__15CZBodyAnimBlendFf` | yes | shared callers CheckAnim, CanInterrupt |
| 0x1e1f40 | `CallbackTick__15CZBodyAnimBlendF...` | yes | shared caller Tick_0 |
| 0x1e2190 | `Reset__15CZBodyAnimBlendFv` | yes | shared callers PopBlend, PushBlend, positions as above |
| 0x1e2440 | `CallbackTick__13CBlendOverlayFPvf` | yes | shared caller Tick_0 |
| 0x1e24b0 | `IsTriggerTime__13CBlendOverlayFff` | yes | shared caller CBlendOverlay::CallbackTick |
| 0x1e2c20 | `TrueLoopTime__10CZBodyAnimFv` | yes | five shared callers |
| 0x1e3030 | `Setup__10CZBodyAnimFiff` | yes | shared caller ReadMotionRdr |
| 0x1e3440 | `PopBlend__5CBodyFv` | yes | shared callers Destroy, CZSealBody::PopBlend |
| 0x1e36e0 | `PushBlend__5CBodyFiiib` | yes | shared callers RePose, CZSealBody::PushBlend |
| 0x1e40c0 | `BodyAddAnim__5CBodyFPCcbi` | yes | shared callers AnimSetup, ReadMotionRdr |
| 0x1e57a0 | `__ct__26RTArray<15CZBodyAnimBlend>FUibb` | yes | shared caller SetBlendPool |

### Settled pairs (tool input)

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x1e2590 | 0x1e1210 | the same opening and calls; frame arithmetic moved to new 0x1e29d0; caller split out of Tick_0 into new 0x27b620 | socom-release-check-small-1 | 2026-11-26 | | |
| 0x1e27c0 | 0x1e1700 | shared caller BlendOverlayPreTick, the same three call positions; the same opening checks | socom-release-check-small-1 | 2026-11-26 | | |

### New and removed

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x1e29d0 | sets an anim's time and its frame pair | guess: `SetTime__11ACTIVE_ANIMFf` (slot between ACTIVE_ANIM::ClearOverlays and Clear) |
| 0x1e3b70 | pops blends down to a depth | guess: `PopBlendTo__5CBodyFUi` |
| 0x1e3c20 | interpolates a part pose | guess: `BlendPose__5CBodyFif` |
| 0x1e3dd0 | applies the stored part poses to the nodes | guess: `ApplyPose__5CBodyFv` |
| 0x1e3e80 | saves a part's pose into its second slot | guess: `SavePose__5CBodyFi` |

None removed.

Layouts, plainly shown by settled rows: BodySetState became virtual: the CBody vtable holds it at +0x14
(the prototype's had a zero there), and CZSealBody's CBody-part table gained BodySetState__10CZSealBodyFi.

## Still unsure

None of the six lists' rows. Open points:

- The names of the new functions are guesses, except the two state destructors.
- 0x1effc0 (CEntity slot 1) is settled as new on the evidence of its contract (no return, writes the
  cache). If the release kept the name GetPosW for a changed virtual, only the name differs; the
  prototype getter has no release body either way.
- 0x404800 is a merge of TRC_PowerOffThread and its Aux; it is paired with the entry by the pointer
  rule. Pairing it with Aux would be the body-majority reading.
- The part names behind CZSealBody's +0x28c/+0x290 (slots 11/12) assume the prototype layout there.

## How the tool did

| module | class | rows | right | wrong |
|---|---|---|---|---|
| Apps/FTS | removed | 4 | 3 | 1: process_arguments is 0x1735e0 |
| Apps/FTS | new | 9 | 8 | 1: 0x142ea0 is acquire<4four> |
| zEntity | new | 10 | 10 | 0 |
| zEntity | removed | 1 | 1 | 0 |
| zSound | new | 6 | 6 | 0 |
| zSound | unsure | 1 | 1 (the candidate was right) | 0 |
| zSound | weak (slot-only, role-only) | 3 | 3 | 0 |
| zSound | removed | 1 | 0 | 1: AwarenessUpgrade is 0x3068b0 |
| zVideo | weak (slot-only) | 1 | 1 | 0 |
| zVideo | new | 2 | 2 | 0 |
| zVideo | committed, caller-mismatch | 3 | 3 | 0 |
| zVideo | removed | 4 | 4 | 0 |
| zSystem | removed | 5 | 4 | 1: TRC_PowerOffThread is 0x404800 |
| zSystem | new | 3 | 3 | 0 |
| zSystem | committed, caller-mismatch | 1 | 1 | 0 |
| zBody | weak (slot-only) | 2 | 2 | 0 |
| zBody | new | 5 | 5 | 0 |

The sample: 83 of 85 sampled deviating rows are the same function on both sides (Apps/FTS 14 of 15,
zEntity 15 of 15, zSound 15 of 15, zVideo 10 of 10, zSystem 14 of 15, zBody 15 of 15). Wrong:
0x142d80 (the 16-byte pool's acquire, not acquire<4four>) and 0x404800 (the thread entry, not Aux).

The cross-check: 446 paired rows compared (Apps/FTS 39, zEntity 98, zSound 135, zVideo 24, zSystem 61,
zBody 89, rows in the ranges with other or no owners included); the ordered calls of 2266 paired
callers; 21 vtables slot by slot plus 2 new unpaired ones (CShutdownState, CRebootState); 87 rows with
byte twins. Differences looked at: 105 caller/loader sets, 203 caller call sequences, 10 call-order
substitutions, 9 vtables, 10 twin ties with callers. They are callers moved, added or dropped (the
video and system start-up moved from CGame::StartEngine into CIOPManager::RebootIOP; debug code
dropped from CCoreState::Tick, CSealCtrlAi::Tick and zSysInit; CZSealBody::Tick_0 split), the
inserted CEntity, CSnd and CSndGroup slots, inlined helpers (zmalloc release, CTarget::Update,
TRC_PowerOffThread_Aux, list and vector code), the string code calling `__nw__`/`__dl__` instead of the
zmalloc pools, and table boundaries misread at CZSealBody's secondary table. The twin ties are decided
by vtable slot (the empty CEntity, CGameState and COurGame virtuals), by the load order in
`__sinit_zsnd_csnd.cpp` and `__sinit_zsnd_jukebox.cpp` (exact), and by the call position in the shared
caller (SetupJukebox and InitDatabaseHandles in CMission::Open; the compressed_pair accessors in the map
destructor and destroy; zVid_Uninit and its empty twins in CGame::StopEngine; the two GetNext in
PushBlend).
Pairs wrong: 4 (0x142d80 and 0x404800, also in the sample; 0x3068b0 and 0x1effc0, rows with no owner
or another module's owner, found only by the range pass).

What misled it:

- acquire<4four>: the four acquire instances are byte-equal up to the malloc size and share their one
  caller, `allocate<c>`; the tool took the one at the old instance's place (`imm-only`, `moved`). The
  size immediate (4 / 12 / 16 / 20) and the pool object the caller loads decide.
- AwarenessUpgrade: its release body is a two-call wrapper with nothing in common with the old one,
  and its caller also called `_dpfgt`, a small runtime function, in the same block. The tool paired the
  wrapper with `_dpfgt` on the shared caller across sections (runtime to sound code).
- TRC_PowerOffThread: the release merged the entry with its helper; callee-check preferred the
  helper's call list over the entry pointer the tool had first used.
- GetPosW: the slot survived with a different contract; the tool paired by slot (`vtable-slot`) and the
  low similarity (0.18) did not stop it.

What cost the most time: the zmalloc family in main.cpp (four template instances with byte-equal
bodies) and telling the merged power-off thread apart. Suggestions:

- For template families whose instances differ only in immediates, pair by the immediates the
  instance's own constructor stores or the caller's branch constant, not by position.
- Do not let a pair between a runtime provider function and an authored-file slot stand on one shared
  caller; flag it `caller-mismatch` when the prototype side's other callers do not call the release
  side.
- In callee-check, keep a pair whose release side is still loaded at the prototype side's pointer slot.
