# Stage 2: gamez/zAnim (2026-11-26)

List a of `gamez/zAnim` (one list) covers the owner files zanim_cmd_parse.cpp, zanim_cmd_tick.cpp,
zanim_load.cpp, anim_main.cpp, zanim_set.cpp, zanim_anim.cpp, zanim_menu.cpp, zanim_sequence.cpp
and anim.cpp. It holds 38 uncertain rows (25 new, 8 removed, 2 unsure, 1 weak pair (`slot-only`),
1 deviating row flagged `caller-mismatch` and 1 exact row flagged `identical-copy`), 15 sampled
deviating rows out of 240, and 329 exact rows. The pairing was produced by
`socom-release-compare-c1` (`python tools/release/compare.py`). It was checked by
`socom-release-check-anim`, who did not write the tool, at HEAD fa04cf2f. The check sheet
(`compare.py --sheet gamez/zAnim --list a`) was the starting point. Both images were decoded with
the release tools. Callers were found by scanning both images for `jal`/`j`, `lui`/`addiu` address
loads and data words. Ghidra was not needed.

As a guard on the committed pairs, every paired row in the owner ranges was compared with the
prototype through the map: 572 rows (322 exact, 237 deviating, 2 unsure, the rest weak). The
comparison covered their callers and address loaders, their own ordered calls and address loads,
and their data-word counts. The `AddCmd` registrations in `CZAnimMain::InitCommands` were also
compared: 99 commands keyed by name, with their parse, tick and end function pointers. So were
the 147 shared keys of the UI command table (prototype 0x439548, release 0x44a2b8; records of
name, handler and id, 12 bytes) and the 19 vtables that have a slot in these files.

What settled rows, in the order it was used: the `AddCmd` name string, with the parser and tick
pointers it registers; the UI command-table key; vtable slots and the virtual call sites through
`CNode::m_ex` (+0x94); the call site in a paired caller; the slot between paired neighbours;
strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1ab1b0 | - | new | confirmed | the parser registered by the release-only `AddCmd("REMOVE_SATCHELS")`; reads `LOCATION` and `RADIUS` |
| 0x1ab8d0 | 0x1aae30 `zAnimLoadTimer__FP5_zrdr` | deviating (weak), slot-only | confirmed | the parser registered for `"TIMER"` on both sides; it gained a `TEST` mode (six keywords stored at +4) |
| 0x1b8b50 | - | new | confirmed | the tick registered for `"REMOVE_SATCHELS"`; passes the location (+4) and radius (+0x10) to new 0x3373a0, which tail-calls new 0x334730 on a weapons-module global |
| - | 0x1bfd70 `zAnimTimerTick__FP14_zanim_cmd_hdrPf` | removed | corrected to 0x1c0d00 | see the next row |
| 0x1c0d00 | - | new | corrected to 0x1bfd70 `zAnimTimerTick__FP14_zanim_cmd_hdrPf` | the tick registered for `"TIMER"` on both sides; the same slot (between zAnimMessageTick and zAnimDestructorTick); still stores the time into the timer global, and now also has the parser's six test modes |
| - | 0x1c63b0 `SaveNodeStates__9CZAnimSetFv` | removed | confirmed | its only caller, `CMission::ZAnimLoad`, no longer calls it. `CZAnim::SaveNodeStates(bool)` is now called by FindClones and RestartClones, and `CZAnim::Start` calls `CZAnimSet::SaveNodeStates(_zanim_node_ref*)` itself |
| 0x1c9770 | - | new | confirmed | the `CZAnimEx` override in vtable slot +0x10 (table 0x489320); returns `m_health (+0x1c) > 0` (see 0x1d0770) |
| 0x1cc940 | 0x1cbe70 `StopSounds__6CZAnimFv` | deviating, position, caller-mismatch | confirmed | the same body (Stop, ReleaseSoundInstance, IsPlaying, TerminateOnFinish) plus FadeOut and headset calls. Its only release caller is State (0x1ccb30), which calls it in the prototype too; its other callers now call State instead |
| - | 0x1cbfe0 `StopParticleSources__6CZAnimFv` | removed | confirmed | Load, Copy, Tick, Stop, Reset and Activate called StopParticleSources, StopSounds, StopLights and StopAnims in a row; the release calls `State(this, 1)` or `State(this, 5)` there instead. The particle reset was already in State |
| - | 0x1cc080 `State__6CZAnimFi` | removed | corrected to 0x1ccb30 | see "Just outside the uncertain rows" |
| - | 0x1cfed0 `OnDelete__Q23zdb7CNodeExFPQ23zdb5CNode` | removed | confirmed | the release CNodeEx tables (CNodeEx, CNodeAction, CParticleEx, CSealEx, CZAnimEx) end after slot +0x10; slots +0x14 to +0x20 are gone |
| - | 0x1cfee0 `OnCopy__Q23zdb7CNodeExFPQ23zdb5CNodePQ23zdb5CNode` | removed | confirmed | the same |
| - | 0x1cfef0 `OnDoubleClick__Q23zdb7CNodeExFPQ23zdb5CNode` | removed | confirmed | the same |
| - | 0x1cff00 `OnSelect__Q23zdb7CNodeExFPQ23zdb5CNodeb` | removed | confirmed | the same |
| 0x1d0770 | 0x1cfec0 `OnMove__Q23zdb7CNodeExFPQ23zdb5CNode` | unsure, position | corrected to new; OnMove removed | It sits in slot +0x10, OnMove's slot, but it is another function. OnMove was `void` and was called only by the CNode setters (SetPosition, SetRotation, SetScale, SetMatrix: `m_ex->OnMove(this)`); the release setters no longer make that call. The release slot returns `bool` (base `return 0`, the bytes of OnAction), CZAnimEx overrides it (0x1c9770), and it is called with no argument by `CZKit::HandleFireWeapon`, `CZKit::TickExplosives` and `BitmapReticule::UpdateColor` |
| 0x1d0b90 | 0x1d0320 `Get2DVisual__Q23zdb7CVisualFv` | exact, identical-copy | confirmed | the last slot of the CVisual, CSubMesh and CMesh tables on both sides (+0x20 in the prototype, +0x1c in the release, where `Write` was dropped); emitted in zanim_menu.cpp on both sides |
| 0x1d1050 | - | new | confirmed | release-only table key `RefreshGameListInfo` |
| 0x1d10f0 | - | new | confirmed | release-only key `CheckTeamStatus` |
| 0x1d1840 | - | new, copy | confirmed | release-only key `FadeAllSounds` |
| 0x1d21d0 | - | new | confirmed | release-only key `ClearUIVar` |
| 0x1d2450 | - | new | confirmed | release-only key `PruneUIVarSpaces` |
| 0x1d2ab0 | - | new | confirmed | release-only key `GetClanMessages` (calls 0x345b10, which sends MediusGetMyClanMessages) |
| 0x1d2ae0 | - | new, copy | confirmed | release-only key `GetUsagePolicy` (calls 0x349040, which sends MediusGetPolicy) |
| 0x1d2d20 | - | new | confirmed | release-only key `BackgroundMPEG` |
| 0x1d2e00 | - | new | confirmed | release-only key `AutoAim` |
| 0x1d32d0 | - | new | confirmed | release-only key `PlayMPEGNoFade` |
| 0x1d36b0 | - | new | confirmed | release-only key `MC_Changed` |
| 0x1d69c0 | - | new | confirmed | the out-of-line CWrappedText constructor (stores the CWrappedText vtables, RTTI "CWrappedText"). GetPopUp and CScrollSpec::CreateDisplayObj call it where the prototype built the object inline after `CRenderableString`'s constructor |
| 0x1d7490 | - | new, copy | confirmed | release-only key `UpdateMpFinalStatsUiVars` |
| 0x1d7a30 | - | new | confirmed | called by OnListSavedGames; maps a mission prefix (`m6 `, `m8 `, `m5 `, ... `m16`) to a two-digit number, default `UU` |
| 0x1d7db0 | - | new | confirmed | release-only key `DoAllSelCharsHaveWeapon` |
| 0x1d80b0 | - | new | confirmed | the only caller is 0x1d7db0; a comma-list tokenizer step: it skips spaces and commas, then appends characters up to the next comma to the string at +8 |
| 0x1d8170 | - | new, copy | confirmed | the only caller is 0x1d7db0; the bytes of the exact `compressed_pair_imp<allocator<Ui>,Ui,1>` constructor (0x1d6400); it initialises the local one-byte vector |
| 0x1d82b0 | - | new, copy | confirmed | release-only key `CleanupMissionMemory` |
| 0x1d82d0 | - | new | confirmed | release-only key `ChooseDefaultEquipmentOnly` |
| 0x1d91e0 | - | new | confirmed | the only caller is 0x1d7db0; `vector::insert(pos, n, value)` for one-byte elements ("vector::insert length error") |
| 0x1d95b0 | - | new, copy | confirmed | the only caller is 0x1d91e0; the bytes of the neighbouring `compressed_pair_imp::swap` (0x1d91c0) |
| 0x1d9620 | 0x402060 `__dt__Q23std145deque<M16CCnfStateMachine…>Fv` | unsure, global | corrected to new; 0x402060 removed | not a deque destructor: no `tear_down`, and the buffer at +8 is freed after the trivial one-byte element loop 0x1d9740. It destroys the local vector of 0x1d7db0 (two call sites), whose elements are `GetWeaponId` results stored with `sb`. The prototype deque destructor's only caller, `__dt__8CHNetCnfFv`, is removed with zNetCnf |

The six handlers named in the zNetwork-b note (UINetCnfOpen 0x1d1f70, Close 0x1d1ef0, CurrCombo
0x1d1cb0, GetDispNames 0x1d1b90, SelectCombo 0x1d1ba0, DeleteAll 0x1d1890) are deviating pairs
in the map since round 6 (table key), and I confirm them. The key, the id and the order agree. So
do the other twelve from the zNetwork-c note. Eleven of the eighteen are now `return 0` or
`return 1` stubs. They are the same functions, because the command name, id and position still
bind them; only their bodies were emptied. The hinted 0x1d2170 = UINetCnfInit (id 0x6c) and
0x1d1e20 = UINetCnfCount (id 0x70) are right.

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x1aff40 | 0x1af1d0 `zAnimLoadStopAnim__FP5_zrdr` | yes | the parser of the same AddCmd name |
| 0x1b4e50 | 0x1b40d0 `GetBlendValueSequence__15CZAnimBlendMode…` | yes | same callers zAnimLoadObjectBlendMode and zAnimLoadLight |
| 0x1bc250 | 0x1bb330 `zAnimObjectMotionTick__FP14_zanim_cmd_hdrPf` | yes | the tick of the same AddCmd name |
| 0x1cabe0 | 0x1c9f10 `GetNodeRefName__6CZAnimFi` | yes | same two SIScript parsers call it |
| 0x1cb450 | 0x1ca780 `GetParticleSource__6CZAnimFi` | yes | same caller zAnimParticleSourceTick |
| 0x1cc140 | 0x1cb490 `GetNode__6CZAnimFib` | yes | the same 43 callers, plus new 0x1d1050; the one difference is the crossed UI-menu parsers below |
| 0x1cc810 | 0x1cbd40 `StopLights__6CZAnimFb` | yes | CZAnimSet::Stop (×2) and State call it on both sides (its other prototype callers now call State); same body |
| 0x1cdf40 | 0x1cd5c0 `SequenceRunning__6CZAnimFPCc` | yes | same four AI callers |
| 0x1cfe50 | 0x1cf5a0 `GetHealth__6CZAnimFv` | yes | same caller zAnimHealthTestTick |
| 0x1d1a20 | 0x1d1930 `UINetAddCombo__FP13C2DAnimCmdHdrPf` | yes | table key `NetAddCombo`, id 0x76; now `return 0` |
| 0x1d3a40 | 0x1d3310 `UISetStickPreset__FP13C2DAnimCmdHdrPf` | yes | table key |
| 0x1d3f50 | 0x1d37c0 `UISwitchProgressiveVideo__FP13C2DAnimCmdHdrPf` | yes | table key |
| 0x1d5b30 | 0x1d53a0 `UIJoinGameServer__FP13C2DAnimCmdHdrPf` | yes | table key |
| 0x1d6410 | 0x1d5c80 `KillPopUp__10CMenuStackFv` | yes | same caller CPopUpDialog::HandlePad |
| 0x1d77d0 | 0x1d6d70 `OnListSavedGames__24@unnamed@zanim_menu_cpp@…` | yes | table key `ListSavedGames` |

Just outside the uncertain rows (committed pairs in the owner ranges, found by the cross-check):

| release | map | finding |
|---|---|---|
| 0x1ccb30 | deviating, 0x1cbb60 `StopAnims__6CZAnimFv` | wrong: it is `State__6CZAnimFi` (0x1cc080), which the map has as removed. It makes State's calls in State's order (StateRunning, Particle::Source::Reset, StopSounds, StopLights, Running, Stop, ExecuteSpecialSequence) and none of StopAnims' calls (GetAnimSet, TaskScheduler, RemoveTask); 732 bytes against State's 700 and StopAnims' 472. Its callers are State's (ActivateBegin ×2, NewAnim, Unload, Reset), plus the old StopAnims call sites, which now pass a mode (`State(this, 1)` in Load, `State(this, 5)` in Tick and Stop). It sits where State was, after DeleteParticleSources and before Tick. StopAnims is then removed: no release function calls TaskScheduler and RemoveTask together outside Unload and Stop, which call them on both sides |
| 0x1d0ba0 | deviating, 0x1d04b0 `zAnimLoadUIMenu__FP5_zrdr` | wrong, crossed with the next row: it is `zAnimLoadUIAppMenu__FP5_zrdr` (0x1d0330). `AddCmd("ui::UI_APP_COMMAND")` registers it on both sides; both are 380 bytes with the same calls (calloc, findstring, strcasecmp on UICommandTable, strcpy, AddName); it comes first of the two on both sides |
| 0x1d0d20 | deviating, 0x1d0330 `zAnimLoadUIAppMenu__FP5_zrdr` | wrong: it is `zAnimLoadUIMenu__FP5_zrdr` (0x1d04b0). `AddCmd("ui::UI_COMMAND")` registers it on both sides; both are 600 bytes and have the same eleven calls in order (findtag, LoadNodeNames, Refresh, GetNode, GetFirstVisual, ...). The two ticks (0x1d09b0, 0x1d09a0) are paired right |
| 0x1d9740 | new, no owner, in no list | the trivial element-destroy loop of the one-byte vector (callers 0x1d91e0 and 0x1d9620); it comes right after zanim_menu.cpp's last template and before zArchive, so its owner is zanim_menu.cpp |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner |
|---|---|---|---|---|---|
| 0x1ccb30 | 0x1cc080 | State's callees in order and State's callers (ActivateBegin, NewAnim, Unload); the old StopAnims call sites now call it with a mode; after DeleteParticleSources as in the prototype | socom-release-check-anim | 2026-11-26 | |
| removed | 0x1cbb60 | StopAnims: its call sites now call State(1/5); no release function makes its GetAnimSet/TaskScheduler/RemoveTask sequence | socom-release-check-anim | 2026-11-26 | |
| 0x1d0ba0 | 0x1d0330 | the parser AddCmd("ui::UI_APP_COMMAND") registers on both sides; 380 bytes, same calls | socom-release-check-anim | 2026-11-26 | |
| 0x1d0d20 | 0x1d04b0 | the parser AddCmd("ui::UI_COMMAND") registers on both sides; 600 bytes, same calls in order | socom-release-check-anim | 2026-11-26 | |
| 0x1c0d00 | 0x1bfd70 | the tick AddCmd("TIMER") registers on both sides; same slot between zAnimMessageTick and zAnimDestructorTick | socom-release-check-anim | 2026-11-26 | |
| 0x1ab8d0 | 0x1aae30 | the parser AddCmd("TIMER") registers on both sides | socom-release-check-anim | 2026-11-26 | |
| 0x1cc940 | 0x1cbe70 | same sound-instance calls; called by State on both sides | socom-release-check-anim | 2026-11-26 | |
| 0x1d0b90 | 0x1d0320 | last slot of the CVisual, CSubMesh and CMesh tables on both sides | socom-release-check-anim | 2026-11-26 | |
| 0x1d0770 | new | slot +0x10 now returns bool, overridden by CZAnimEx and called by CZKit/BitmapReticule; the CNode setters no longer call it | socom-release-check-anim | 2026-11-26 | |
| removed | 0x1cfec0 | OnMove: the CNode setters' `m_ex->OnMove(this)` calls are gone; its slot holds a new query | socom-release-check-anim | 2026-11-26 | |
| 0x1d9620 | new | destructor of 0x1d7db0's local one-byte vector (no tear_down; element loop 0x1d9740) | socom-release-check-anim | 2026-11-26 | |
| removed | 0x402060 | the CCnfStateMachine deque destructor; its only caller __dt__8CHNetCnfFv is removed | socom-release-check-anim | 2026-11-26 | |
| 0x1c9770 | new | CZAnimEx's override of the new CNodeEx slot +0x10 (table 0x489320) | socom-release-check-anim | 2026-11-26 | src/gamez/zAnim/zanim_anim.cpp |
| 0x1d9740 | new | element-destroy loop called by 0x1d91e0 and 0x1d9620; after zanim_menu.cpp's last template | socom-release-check-anim | 2026-11-26 | src/gamez/zAnim/zanim_menu.cpp |

Rows that change together: 0x1ccb30 with State, StopAnims and StopParticleSources; the two
crossed UI-menu parsers; 0x1d0770 with OnMove and 0x1c9770; 0x1d9620 with 0x402060 (zNetwork's
CCnfStateMachine deque).

## New and removed

New (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x1ab1b0 | parses REMOVE_SATCHELS (LOCATION, RADIUS) | `zAnimLoadRemoveSatchels__FP5_zrdr` (the AddCmd name; the zAnimLoad<Command> pattern) |
| 0x1b8b50 | REMOVE_SATCHELS tick: removes satchels within the radius of the location | `zAnimRemoveSatchelsTick__FP14_zanim_cmd_hdrPf` (the AddCmd name; the <Command>Tick pattern) |
| 0x1d0770 | new CNodeEx virtual, base `return false` | guess: `IsAlive__Q23zdb7CNodeExFv` (its override tests health > 0; callers aim and fire at nodes) |
| 0x1c9770 | CZAnimEx override: `m_health > 0` | guess: `IsAlive__8CZAnimExFv` |
| 0x1d1050, 0x1d10f0, 0x1d1840, 0x1d21d0, 0x1d2450, 0x1d2ab0, 0x1d2ae0, 0x1d2d20, 0x1d2e00, 0x1d32d0, 0x1d36b0 | UI command handlers (keys above) | `UI<Key>__FP13C2DAnimCmdHdrPf`, e.g. `UIRefreshGameListInfo` (the key; every handler among the UI* functions is named UI + key) |
| 0x1d7490, 0x1d7db0, 0x1d82b0, 0x1d82d0 | UI command handlers in the unnamed-namespace part of the file | guess: `OnUpdateMpFinalStatsUiVars`, `OnDoAllSelCharsHaveWeapon`, `OnCleanupMissionMemory`, `ExecuteChooseDefaultEquipmentOnly` (beside `ExecuteChooseDefaultEquipment`), all `__24@unnamed@zanim_menu_cpp@FP13C2DAnimCmdHdrPf` |
| 0x1d69c0 | CWrappedText constructor | `__ct__12CWrappedTextFv` (the vtables it stores; signature a guess) |
| 0x1d7a30 | mission prefix to two-digit number for the save list | guess: `GetMissionNumber__24@unnamed@zanim_menu_cpp@FPCc` |
| 0x1d80b0 | next token of a comma list | guess: a member of a local tokenizer class in DoAllSelCharsHaveWeapon |
| 0x1d8170, 0x1d95b0 | MSL compressed_pair constructor and swap for the one-byte vector | guess: the `compressed_pair_imp<allocator<10EQUIP_ITEM>,…>` instances (element type from GetWeaponId's result) |
| 0x1d91e0 | `vector::insert(pos, n, value)` | guess: `insert__Q23std…__vector_imp<10EQUIP_ITEM,…>` |
| 0x1d9620 | the vector's destructor | guess: `__dt__Q23std…__vector_deleter<10EQUIP_ITEM,…>Fv` |
| 0x1d9740 | the vector's element-destroy loop | guess: an MSL destroy helper of the same vector |

Not new, though the map has them as new: 0x1c0d00 (zAnimTimerTick).

Really removed:

- StopParticleSources and StopAnims: their call sites (Load, Copy, Tick, Stop, Reset,
  Activate) call `State(mode)` instead of the four Stop* calls.
- `CZAnimSet::SaveNodeStates()`: CMission::ZAnimLoad no longer saves node states; FindClones,
  RestartClones and Start do it per anim.
- `CNodeEx::OnMove`, `OnDelete`, `OnCopy`, `OnDoubleClick`, `OnSelect`: the editor callbacks are
  gone from every CNodeEx table; the CNode setters no longer call OnMove.
- `__dt__…deque<M16CCnfStateMachine…>` (0x402060): with CHNetCnf (zNetwork).
- Not removed, though the map has them: zAnimTimerTick (0x1c0d00) and State (0x1ccb30).

Layouts, plainly shown by settled rows: the CNodeEx vtable has three virtual slots in the release
(OnWeaponHit, OnAction, the new +0x10 query) where the prototype had seven; zdb::CVisual,
CSubMesh and CMesh lost their `Write` slot (+0x1c); the C2D/CPlainBmp tables gained a slot at
+0x20 (0x173940, outside this module).

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses, except those taken from a command key.
- 0x1c9770 sits between zanim_set.cpp's last template and zanim_anim.cpp's first function; the
  owner zanim_anim.cpp is a guess (CZAnimEx's vtable is among that file's tables).
- For zFTS (fts_mission.cpp), found by the AddCmd comparison: `AddCmd("HUD_START_DEFUSE_TIMER")`
  registers parser 0x1fc0b0 and tick 0x1fc080 in the release, but the map has 0x1fbff0 as
  `HUDStartDefuseTimerTick` (0x1f9740) and the parser `HUDStartDefuseTimerParse` (0x1f9760) as
  removed. 0x1fc080 calls `hudStartDefuseTimer` as the prototype tick does. 0x1fbff0 calls
  `CZWeapon::ClearTimer` and is the tick of the release-only `HUD_STOP_DEFUSE_TIMER` (parser
  0x1fc010). So it is likely 0x1fc080 = 0x1f9740, 0x1fc0b0 = 0x1f9760, and 0x1fbff0 new. This is
  not settled here.
- For another module: `UIHaveBeenBannedFromGame` (0x1d2780, paired by key) now tail-calls
  0x20ae80. The map has 0x20ae80 as unsure `NumActiveTerrorists__14CZPersonaStateFv`, but it is a
  500-byte team-balance test (counts team members against NumActiveSeals), not that function's
  loop.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 25 | 24 | 1: 0x1c0d00 is zAnimTimerTick |
| removed | 8 | 6 | 2: zAnimTimerTick is 0x1c0d00, State is 0x1ccb30 |
| unsure | 2 | 0 | 2: 0x1d0770 and 0x1d9620 are new (OnMove and the deque destructor are removed) |
| deviating (weak, slot-only) | 1 | 1 | 0 |
| deviating, caller-mismatch | 1 | 1 | 0 |
| exact, identical-copy | 1 | 1 | 0 |

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 572 paired rows compared (callers and address loaders, ordered calls and loads,
data-word counts), plus 99 AddCmd commands (198 function pointers), 147 UI-table keys and 19
vtables.

Differences looked at: 56 rows with differing callers or loaders, 5 with a substitution in their
ordered calls or loads, 5 differing AddCmd pointers and 10 differing vtables. All are explained
by the corrections above (State, the crossed parsers, OnMove, SaveNodeStates, zAnimTimerTick,
REMOVE_SATCHELS), by UI handlers that became stubs, by inlined callees
(`VALVE_CMD_DATA::GetValue`, `process_arguments`), by dropped vtable slots, or by callers in
other modules that were added, dropped or moved. The one exception is outside this module: two
of the five AddCmd differences show a likely wrong zFTS pair (HUD_START_DEFUSE_TIMER, under
"Still unsure").

Pairs wrong: 3 (0x1ccb30, 0x1d0ba0, 0x1d0d20). No table key and no vtable slot was wrong: the
81 handlers that only the key decided all look right.

What misled it:

- State/StopAnims: the old StopAnims call sites now call State, so the call evidence pulled
  State to StopAnims at similarity 0.266. The body (State's callees in order) and the slot point
  the other way.
- The UI-menu parsers: two near-twin parsers sit next to each other on both sides, and the tool
  paired them crossed (0.694 each; `global` and `call-deviating` evidence). The AddCmd
  registration decides them, and so do the sizes (600 and 380 on both sides once uncrossed).
- zAnimTimerTick: it grew from 24 to 276 bytes, so it lost the similarity test; the AddCmd tick
  pointer decides it.
- OnMove: position kept a removed void stub on a new bool virtual in the same slot.
- The deque destructor: the shape of a container destructor matched (0.842) across different
  templates.

What cost the most time: the CNodeEx slot +0x10 question, settled by finding the virtual call
sites through `m_ex` (+0x94) on both sides. Suggestions:

- Pair a command's parse, tick and end functions by the AddCmd name string, as the UI table is
  paired by key.
- Weigh a candidate's own callee sequence above its callers when a caller set has been replaced.
