# Stage 2: gamez/zSeal, list c (2026-11-25)

List c of `gamez/zSeal` (split 6 ways): the owner files seal_ai.cpp (release 0x2679b0–0x2711d0),
seal_sensors.cpp, seal_tasks.cpp and seal_aifollow.cpp. It holds 50 uncertain rows (6 weak pairs,
all `slot-only`; 34 new; 10 removed), 15 sampled deviating rows out of 109, and 87 exact rows that
were not checked. Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`);
checked by `socom-release-check-seal-c`, who did not write the tool, at HEAD 8185d1bb. The check
sheet (`compare.py --sheet gamez/zSeal --list c`) was the starting point; both images were
disassembled, callers found by scanning both images for `jal`/`j`, data words and `lui`/`addiu`
pairs. Ghidra was not needed.

What settled rows, in the order it was used: the vtables (`__vt__11CSealCtrlAi`,
`__vt__9CSealCtrl`, `__vt__10CAiSFollow` against the release tables at 0x489c30, 0x489ce0 and
0x48a070, slot by slot through the map); the call site in a paired caller; a callee with one
caller on each side; the function pointer passed to `CAiMap::WalkLine`; the function pointers of
the exact `RegisterCommands` (all 90 in the same order); byte equality with prototype template
instances.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x267f60 | - | new | confirmed | new call in CTSound::Tick after the sound plays; posts a CAiEvent (type 8) at the seal |
| 0x268000 | - | new | corrected to 0x25fc90 `PlayAiSound__11CSealCtrlAiF15CHARACTER_SOUND` | vtable slot +0x24 of CSealCtrlAi; same GetCharacter / PlayAt body; slot between FindPeekDir and ConfirmAiState. The removed row is in list d |
| - | 0x260e70 `SetRouteType__11CSealCtrlAiFQ27CAiPath9PATH_TYPEf` | removed | confirmed | its only caller CAiSGoto::Tick no longer calls it after SetRoute; no SetPathType call is left there; nothing in the slot |
| 0x269ed0 | - | new | confirmed | new calls in CAiState::Signal (after SetTrigger) and CTStance Begin/End; nothing in the prototype slot |
| 0x26bc70 | - | new | confirmed | new helper of AttackTick; nothing in the slot |
| 0x26bea0 | 0x263a30 `SelectFireParams__11CSealCtrlAiFv` | deviating, slot-only | confirmed | AttackTick calls it at the same place (after FireWhenReady and both SetTrigger, before rand); the release adds a ChooseWeapon call |
| - | 0x2640d0 `SetTarget__11CSealCtrlAiFP7CTarget` | removed | corrected to 0x26c600 | see 0x26c600 |
| - | 0x264170 `Output__11CSealCtrlAiFPCce` | removed | confirmed | empty varargs debug print; every call site is gone |
| - | 0x2641a0 `Debug__11CSealCtrlAiFPCce` | removed | confirmed | the same, for Debug |
| - | 0x2641d0 `PutAiLog__11CSealCtrlAiFUiUiPCv` | removed | confirmed | its caller CAiState::Signal no longer logs; GetAiLog and CAiLog::Write are unpaired as well |
| - | 0x264250 `SetDebug__11CSealCtrlAiFb` | removed | confirmed | inlined: CTDebug::Tick writes bit 0 of +640 itself where the prototype called SetDebug |
| 0x26c600 | - | new | corrected to 0x2640d0 `SetTarget__11CSealCtrlAiFP7CTarget` | vtable slot +0xa0 of CSealCtrlAi; starts with the same CanAttack and CAiTarget::SetTarget calls; same slot (SetValve – SlideTick) |
| 0x26c890 | - | new | confirmed | looks the entity up in the seal's target list and calls the virtual SetTarget (+0xa0); callers CAiSGoto::Tick, CAiSRush::Tick |
| 0x26d1a0 | 0x264af0 `CreepTick__11CSealCtrlAiFf` | deviating, slot-only | confirmed | vtable slot +0x8c of CSealCtrlAi; same calls (CreepTick__9CSealCtrl, SetAiMode, SetGoalPos, SetGoalDir) plus the new look-ahead |
| 0x26eb20 | - | new | confirmed | target-list scan, nothing like it in the prototype |
| 0x26ecb0 | - | new | confirmed | the same |
| 0x26ee30 | - | new | confirmed | the same |
| - | 0x266320 `LadderClimbTick__11CSealCtrlAiFf` | removed | corrected to 0x26f5f0 | see 0x26f5f0 |
| 0x26f020 | 0x2661d0 `_look_ahead__FRC19MAP_LINEWALK_STRUCTPv` | deviating, slot-only | corrected to new | it is not the callback: it calls `WalkLine` and passes 0x26f210 as the callback (`lui a3,0x27; addiu a3,-3568`); similarity 0.087 |
| 0x26f210 | - | new | corrected to 0x2661d0 `_look_ahead__FRC19MAP_LINEWALK_STRUCTPv` | the function pointer passed to WalkLine, as PathFollowTick passed _look_ahead in the prototype; the first 18 instructions are the prototype's (same cell compare), then extended |
| 0x26f5f0 | - | new | corrected to 0x266320 `LadderClimbTick__11CSealCtrlAiFf` | the only AI caller of CLadderList::GetLadderByIndex on both sides; same slot (_look_ahead – ComputeTurnThrottle); same callees (Interp, GetDirVec, fabsf, SetGoalPos/Dir, _saturate); the caller moved from PathFollowTick to PreTick |
| 0x2704c0 | - | new | confirmed | the throttle ramp (fabsf ×4, `_close_enough`, accelRate, decelRate) split out of PreTick, which had it inline |
| 0x271020 | - | new | confirmed | SetGoalPos from an AI-map cell (GetCellCenter, then the SetGoalPos stores); callers are new airesponse functions |
| - | 0x2675e0 `PreTick__11CSealCtrlAiFf` | removed | corrected to 0x271290 | vtable slot +0x0c; the same call sequence (StateTick, EventTick, CAiTarget::Tick, InvalidateFollowParams, SensorPreTick, IdleTick, PathFollowTick, FollowTick, MakeCallbacks). 0x271290 is in list e |
| - | 0x267b30 `PostMortemPreTick__11CSealCtrlAiFf` | removed | corrected to 0x271a70 | vtable slot +0x14; same calls (GetNode, RecycleEntity, _saturate). 0x271a70 is in list e |
| 0x2bfcd0 | 0x2afeb0 `UpdateViewCone__9CSealCtrlFv` | deviating, slot-only | confirmed | vtable slot +0x98 of CSealCtrl |
| 0x2c0cc0 | - | new | confirmed | new callee of ComputeVisibility(CTarget*); nothing in the slot |
| 0x2c0e40 | - | new | confirmed | called only by 0x2c0cc0 |
| 0x2c2150 | 0x2b1910 `OnSetTargetVisible__9CSealCtrlFR7CTargetbPQ23zdb11DiIntersect` | deviating, slot-only | confirmed | vtable slot +0x9c of CSealCtrl |
| 0x2c2300 | 0x2b1980 `OnSetTargetVisible__11CSealCtrlAiFR7CTargetbPQ23zdb11DiIntersect` | deviating, position, slot-only | confirmed | vtable slot +0x9c of CSealCtrlAi |
| 0x2c4600 | - | new | confirmed | ring-index helper of PostTick(float, void*); no prototype counterpart |
| 0x2c52c0 | - | new, copy | confirmed | template instance (below) |
| 0x2c52d0 | - | new, copy | confirmed | template instance |
| 0x2c52e0 | - | new, copy | confirmed | template instance |
| 0x2c52f0 | - | new, copy | confirmed | template instance |
| 0x2c5300 | - | new, copy | confirmed | template instance |
| 0x2c5370 | - | new | confirmed | record initializer used twice by PreTick(float, void*) |
| 0x2c53b0 | - | new, copy | confirmed | template instance |
| 0x2c5460 | - | new, copy | confirmed | template instance |
| 0x2c54e0 | - | new, copy | confirmed | template instance (list node insert) |
| 0x2c5630 | - | new, copy | confirmed | template instance |
| 0x2c5640 | - | new, copy | confirmed | template instance |
| 0x2c5650 | - | new, copy | confirmed | template instance |
| 0x2c5660 | - | new, copy | confirmed | template instance |
| 0x2caa90 | - | new | confirmed | the out-of-line compare of CTParam::Tick (the prototype inlined it per parameter) |
| - | 0x2e1d80 `Tick__10CAiSFollowFfP11CSealCtrlAi` | removed | corrected to 0x2f67a0 | see 0x2f67a0 |
| 0x2f63c0 | - | new | confirmed | two new calls in FollowTick; nothing like it in the prototype FollowTick |
| 0x2f67a0 | - | new | corrected to 0x2e1d80 `Tick__10CAiSFollowFfP11CSealCtrlAi` | the CAiSFollow vtable slot between OnSignal and GetStatus (the release CAiState has one new virtual before it); same start, `ConfirmAiState(ai, this, 1)` then a field copy and a flag return; same slot (SetFollowMaster – GetStatus) |
| 0x2f6fc0 | - | new, no owner | confirmed | called only by 0x2f63c0; owner seal_aifollow.cpp (caller, and it sits before the squirm code) |
| 0x2f7290 | - | new, no owner | confirmed | called only by 0x2f6fc0; owner seal_aifollow.cpp, same basis |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x269100 | 0x260e30 `GetValve__11CSealCtrlAiCF10SEAL_VALVE` | yes | the same four callers; only the array offset differs |
| 0x26d680 | 0x264e20 `PathFollowTick__11CSealCtrlAiFf` | yes | callers PreTick and FollowTick on both sides; operations 0.849 |
| 0x2bfe90 | 0x2affe0 `ComputeVisibility__9CSealCtrlFPQ23zdb11DiIntersectPQ23zdb5CNode` | yes | same two callers; similarity 0.970 |
| 0x2c14a0 | 0x2b0d20 `SensorTick__11CSealCtrlAiFf` | yes | same caller (PostTick); imm-only |
| 0x2c1610 | 0x2b0e90 `EnemyCallout__11CSealCtrlAiFPC7CTargetP7CEntity` | yes | same caller (OnSetTargetVisible of CSealCtrlAi) |
| 0x2c7c70 | 0x2b63d0 `Begin__9CTSpecialFP14_zanim_cmd_hdr` | yes | the same position in RegisterCommands' function pointers |
| 0x2c8c40 | 0x2b7250 `Tick__9CTSetModeFP14_zanim_cmd_hdrPf` | yes | the same |
| 0x2c95f0 | 0x2b7ae0 `Begin__6CTPlayFP14_zanim_cmd_hdr` | yes | the same |
| 0x2c9cc0 | 0x2b80b0 `Begin__8CTPursueFP14_zanim_cmd_hdr` | yes | the same |
| 0x2cd930 | 0x2bc100 `End__6CTGotoFP14_zanim_cmd_hdr` | yes | the same |
| 0x2ce9a0 | 0x2bd1a0 `Begin__10CTFireModeFP14_zanim_cmd_hdr` | yes | the same |
| 0x2ced80 | 0x2bd5e0 `Tick__7CTEventFP14_zanim_cmd_hdrPf` | yes | the same |
| 0x2f5ba0 | 0x2e1510 `HandleFollowTickHideCheck__11CSealCtrlAiFbb9CAiMapLocPv` | yes | same caller (FollowTick); operations 0.941 |
| 0x2f6270 | 0x2e1c20 `GetFollowMaster__11CSealCtrlAiFPi` | yes | the same callers less CAiSFollow::Tick, which no longer calls it; imm-only |
| 0x2f6aa0 | 0x2e20e0 `GetSnakeFollowLoc__FR7CAiPathiiR9CAiMapLocRC6CPnt3D` | yes | FollowTick calls it at the same place (after ceilf, before GetMapByIndex / dummy_cell); the same callees in order |

Layout, plainly shown by a settled row: GetValve reads the valve array at +0x674 (prototype
+0x5bc), so CSealCtrlAi has 0xb8 more bytes before `m_valve`.

Just outside the list (found through the vtables; not settled here):

| release | map | finding |
|---|---|---|
| 0x293bd0 | exact, position, 0x288120 `OnMissionEnd__9CSealCtrlFv` | wrong identity: it is in slot +0x48 of the CSealCtrl vtable, so it is `OnRecycleEntity__9CSealCtrlFP7CEntity` (0x288140). Both are 8-byte stubs, which is why the bytes agree. The slots of the removed rows point at new release functions: Initalize (+0x40) at 0x293ac0, OnMissionStart (+0x5c) at 0x293b30, OnMissionEnd (+0x60) at 0x293ae0. For list a |
| 0x2735b0 | deviating, `Dump__9CSealCtrlFv` | consistent: the CSealCtrlAi vtable's Dump slot now holds CSealCtrl's Dump, so the removed `Dump__11CSealCtrlAiFv` is no longer overridden. For list e |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x268000 | 0x25fc90 | vtable slot +0x24 of CSealCtrlAi; slot between FindPeekDir and ConfirmAiState; GetCharacter + PlayAt body | socom-release-check-seal-c | 2026-11-25 |
| 0x26bea0 | 0x263a30 | call site in AttackTick after FireWhenReady and both SetTrigger; slot | socom-release-check-seal-c | 2026-11-25 |
| 0x26c600 | 0x2640d0 | vtable slot +0xa0 of CSealCtrlAi; slot between SetValve and SlideTick; CanAttack + CAiTarget::SetTarget | socom-release-check-seal-c | 2026-11-25 |
| 0x26d1a0 | 0x264af0 | vtable slot +0x8c of CSealCtrlAi; same callees | socom-release-check-seal-c | 2026-11-25 |
| 0x26f020 | new | calls WalkLine with 0x26f210 as the callback; callers PathFollowTick, CreepTick, 0x266be0 | socom-release-check-seal-c | 2026-11-25 |
| 0x26f210 | 0x2661d0 | function pointer passed to WalkLine (by 0x26f020); same cell compare at the start | socom-release-check-seal-c | 2026-11-25 |
| 0x26f5f0 | 0x266320 | only AI caller of GetLadderByIndex on both sides; slot between _look_ahead and ComputeTurnThrottle; caller moved PathFollowTick -> PreTick | socom-release-check-seal-c | 2026-11-25 |
| 0x271290 | 0x2675e0 | vtable slot +0x0c of CSealCtrlAi; same call sequence | socom-release-check-seal-c | 2026-11-25 |
| 0x271a70 | 0x267b30 | vtable slot +0x14 of CSealCtrlAi; same calls | socom-release-check-seal-c | 2026-11-25 |
| 0x2bfcd0 | 0x2afeb0 | vtable slot +0x98 of CSealCtrl | socom-release-check-seal-c | 2026-11-25 |
| 0x2c2150 | 0x2b1910 | vtable slot +0x9c of CSealCtrl | socom-release-check-seal-c | 2026-11-25 |
| 0x2c2300 | 0x2b1980 | vtable slot +0x9c of CSealCtrlAi | socom-release-check-seal-c | 2026-11-25 |
| 0x2f67a0 | 0x2e1d80 | CAiSFollow vtable slot between OnSignal and GetStatus; ConfirmAiState(ai, this, 1) first; slot between SetFollowMaster and GetStatus | socom-release-check-seal-c | 2026-11-25 |

All corrected and confirmed pairs are deviating. Three rows touch other lists: 0x268000 settles
list d's removed row 0x25fc90, and 0x271290 / 0x271a70 are list e's new rows. The tool gave
0x2f6fc0 and 0x2f7290 no owner; they belong to seal_aifollow.cpp. The other rows stand as the
map has them.

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x267f60 | acquires a CAiEvent (type 8), radius² = `r * r`, factor 0.5, at the seal's position, and posts it; CTSound::Tick calls it after a sound plays. PlayAiSound posts the same event with radius 250 | guess: `CSealCtrlAi::PostSoundEvent(float)`, from the body |
| 0x269ed0 | `(this, signed char, bool, float)`: when the value is 2, or the target is valid with bit 2 of +0x598 set, or the bool is set, stores the value at seal body +0x305 and sets a timer at +0x338/+0x33c/+0x340 (a `rand` spread, here always 0) | guess: `CSealCtrlAi::SetStanceTimer(...)`, from its callers (CTStance Begin/End, CAiState::Signal) |
| 0x26bc70 | for a valid target: true when the AI is in state 2 with flag 0x20, or has AI state 8 or 10 on its stack, or a target flag is set; otherwise true (and bit 1 of +0x5d2 set) once the target has been visible longer than the reaction time at +0x60c | guess: `CSealCtrlAi::CanEngageTarget()`, from the body |
| 0x26c890 | `FindTarget` of an entity in the seal's target list, then the virtual `SetTarget(CTarget*)` | guess: `SetTarget__11CSealCtrlAiFP7CEntity`, an overload that takes an entity |
| 0x26eb20 | the first live seal in a seal's target list whose AI-map cell is the given cell | guess: `FindSealAtLoc(CZSealBody*, const CAiMapLoc&)` |
| 0x26ecb0 | the first live seal in the target list within `*range` (squared and written back) whose flags +0xc4 match a mask | guess: `FindSealInRange(CZSealBody*, float*, unsigned)` |
| 0x26ee30 | the first live seal of another side (flags +0xc4) within a radius of a point, while the AI itself is alive and not of type 3 | guess: `FindEnemyNear(const CPnt3D*, float)` |
| 0x26f020 | builds the look-ahead record from the seal's AI-map cell and the path data, walks the AI map to the given cell with `_look_ahead` as the callback, then checks the end cell for another seal (0x26eb20) | guess: `CSealCtrlAi::LookAhead(const CAiMapLoc&, ..., float)`; the prototype did this inline in PathFollowTick |
| 0x2704c0 | the throttle ramp (accelRate, decelRate, `_close_enough`) | guess: `CSealCtrlAi::UpdateThrottle(float)`; the prototype had it inline in PreTick |
| 0x271020 | SetGoalPos from an AI-map cell: the cell centre goes to +0x180, the float to +0x1b4, the goal type to +0x1b0, and SetGoalDir is called when the type changes | guess: `SetGoalPos__9CSealCtrlF9GOAL_TYPERC9CAiMapLocf`, an overload of SetGoalPos |
| 0x2c0cc0 | a per-frame cached factor at +0x384 (frame stamp at +0x388): cover sampled around the cell (0x2c0e40) and two calls to 0x231930, saturated | guess: `CSealCtrl::GetConcealment(bool)`, from the body |
| 0x2c0e40 | averages two cell properties over the seal's AI-map cell and its 8 neighbours (`CAiMap::neighbor`) | guess: `SampleCellCover(const CAiMapLoc&, float*, float*)` |
| 0x2c4600 | `(ring, index)`: index −1 means the ring's current one; returns `(start + index) mod size` | guess: a ring-buffer index helper of PostTick(float, void*) |
| 0x2c5370 | initializes a record: three floats at +0x14/+0xc/+0x10, an optional point at +0x18 with a flag at +9 | guess: the constructor of the elements of PreTick's new list |
| 0x2c52c0 … 0x2c5660 (12 rows) | std::list template instances, byte-equal to MSL's `__list_deleter` members already in the prototype (iterator constructors, `tail`, `~__list_deleter`, two `erase`, the node insert with "Memory allocation failure", compressed-pair accessors); PreTick(float, void*) uses them instead of the prototype's `list<const void*>` | the matching MSL member names, for an element type that is not in the prototype (a guess: the record that 0x2c5370 fills) |
| 0x2caa90 | `(u8 op, f32 cur, f32 value)`: 1 `!=`, 2 `==`, 3 `!(<=)`, 4 `<`, 5 `!(<)`, 6 `<=`, otherwise true; jump table at 0x46ba40 | `taskParamCompare`: the static helper of the source with the same cases in the same order (the prototype inlined it, table 0x454740) |
| 0x2f63c0 | a FollowTick helper: weapon state, cached constants 100, 40, 20, 400 and a `tanf`, AI-map cells along the path, then a cone test (0x2f6fc0) | guess: `CSealCtrlAi::CheckFollowFireLane(...)`, from the body |
| 0x2f6fc0 | builds a 2D wedge from a point, a direction, a length and a tangent and tests points against it three times (0x2f7290) | guess: `InFollowCone(...)` |
| 0x2f7290 | XZ side test of a point against two edges (cross products), returns one of the cached result values | guess: `PointInWedgeXZ(...)` |

Not new, though the map has them as new: 0x268000 PlayAiSound, 0x26c600 SetTarget, 0x26f210
_look_ahead, 0x26f5f0 LadderClimbTick and 0x2f67a0 CAiSFollow::Tick. Their prototype names carry
over.

Really removed: SetRouteType (the call in CAiSGoto::Tick is gone), Output and Debug (the
varargs debug prints and every call), PutAiLog (the AI log is gone; GetAiLog and CAiLog::Write are
unpaired too), and SetDebug (inlined into CTDebug::Tick).

## Still unsure

None of the list's rows. Open points:

- The names of the new functions above are guesses.
- The element type of the new std::list in PreTick(float, void*).
- 0x231930 (called by 0x2c0cc0) is a new function outside the module; it was not looked at.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| weak pairs (slot-only) | 6 | 5 | 1: 0x26f020 is not _look_ahead |
| new | 34 | 29 | 5: 0x268000, 0x26c600, 0x26f210, 0x26f5f0, 0x2f67a0 have counterparts |
| removed | 10 | 5 | 5: SetTarget, LadderClimbTick, PreTick, PostMortemPreTick, CAiSFollow::Tick have counterparts |

Outside the list, the same kind of miss: list d's removed PlayAiSound (0x268000 here), and one
wrong exact pair in list a (0x293bd0, above).

The sample: 15 of 15 deviating rows are the same function on both sides.

What misled it:

- Four of the five missed pairs are virtual functions (PlayAiSound, SetTarget, PreTick,
  PostMortemPreTick, CAiSFollow::Tick) with no direct caller on either side. Their gaps held two
  unpaired functions on a side, so the 1-to-1 slot rule did not fire. The vtables settle all of
  them at once: the classes' vtables are paired word for word, and slot k holds the same method.
- _look_ahead: the prototype's PathFollowTick loads `_look_ahead` as a function pointer; the
  release's calls a new wrapper (0x26f020) at that place, which loads the real callback. The
  reference-list alignment paired a loaded pointer with a `jal` target and accepted a 0.087
  similarity.
- LadderClimbTick: the caller moved (PathFollowTick → PreTick, itself unpaired) and the body
  grew from 1932 to 3460 bytes. It is the only AI caller of `GetLadderByIndex` on both sides.

What cost the most time: the virtual functions (the sheet shows "callers: none" for them and
lists no vtable references), and identifying the twelve `copy` template instances, whose
prototype twins are paired elsewhere. Suggestions:

- Pair through vtables: when a release data word table matches a prototype vtable slot for slot
  through the map, pair the unpaired slots (and flag a paired function that sits in a different
  slot, as 0x293bd0 above).
- In reference-list alignment, do not pair a loaded function pointer with a call target, or
  require a minimum similarity for such a pair.
- Count a callee with exactly one caller on each side (here GetLadderByIndex in the AI) as
  identity evidence for the callers.
- In the sheet, name the prototype twin of a `copy` row and show data-word references (vtable
  slots) as callers.
