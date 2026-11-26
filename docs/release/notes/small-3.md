# Stage 2: fourteen small modules, batch 3 (2026-11-26)

One list per module (`compare.py --lists gamez/<module> --split 1`, list a) for gamez/zVehicle,
zParticle, zRender, zCharacter, zValve, zSoftImage, zMath, zBone, zSave, zReader, zIntersect, zGraph,
zGame and zConsole. Together they hold 21 uncertain rows (12 new counting the unplaced 0x239e80,
6 removed, 3 flagged `identical-copy`), 116 sampled deviating rows (all deviating rows of 10 modules,
15 of 20 or 21 in zParticle, zRender and zCharacter) and 736 owner-file rows in all, 719 of them
paired. Pairing produced by
`socom-release-compare-c1` (`python tools/release/compare.py`); checked by
`socom-release-check-small-3`, who did not write the tool, at HEAD f9354c10. Each module's sheet
(`--sheet gamez/<module> --list a`) was the starting point. Both images were decoded with the
release tools; callers were found by scanning both images for `jal`/`j`, `lui`/`addiu` address
loads, `$gp` accesses, vtable slots and data words. Ghidra was not needed.

The cross-check, run per module over all 719 paired rows of the owner files: callers, address
loaders, vtable slots and data-word counts compared with the prototype's through the map; each pair's
own ordered calls and loads compared for substitutions; the ordered calls of every paired caller of a
module function (1299 callers in all) compared; the vtables holding a module function aligned slot by
slot; each row with a byte twin on either side scored by the callers it shares with its counterpart;
and the neighbourhood of every data word pointing at a module function compared, to catch tables
the vtable finder misses.

## gamez/zVehicle (veh_turret.cpp, vehicle_main.cpp)

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x37cfc0 `GetPosW__7CTurretCFv` | removed | corrected to 0x397a00 | see the row below |
| 0x397a00 | - | new, owner guess | corrected to 0x37cfc0 `GetPosW__7CTurretCFv` (deviating) | slot 1 of the CTurret table on both sides (after the destructor, before PreTick). The base slot changed the same way: the paired CEntity::GetPosW (0x1effc0) now copies the node's position into +0x1c instead of returning a pointer to it, and CTurret's override copies its +0x290 position into +0x1c |
| 0x396d60 | 0x37cf60 `__dt__7CTurretFv` | exact, global, identical-copy, moved | confirmed | slot 0 of the CTurret table |
| 0x3979e0 | 0x37b1d0 `ComputeNextPosition__7CTurretFf` | exact, position, identical-copy | confirmed | CTurret table: prototype slot 7, release slot 8 (a new CEntity slot 7, 0x1f38f0, is inserted before it in both the CEntity and CTurret tables) |
| 0x3979f0 | 0x37b1e0 `PostTick__7CTurretFf` | exact, position, identical-copy | confirmed | slot 6 of the CTurret table |

The CTurret table (prototype 0x473090, release 0x48aaf0) has no RTTI word, and the tool's vtable
finder does not see it; that is why the three twins stayed `identical-copy`. Layout, plainly shown by
the GetPosW pair: CEntity's node pointer moved from +0x1c to +0x28, and +0x1c..+0x24 now hold a cached
position.

Sample: 14 of 14 deviating rows are the same function on both sides (shared callers or the CTurret
slots of Tick and PreTick).
Cross-check: 57 pairs; 1 caller-set difference (a coincidental word in an ascending address list at
0x44efa8), 2 call-order substitutions (sqrtf replaced by Normalize in Rotate, double-precision math
dropped from Tick), 0 of 31 caller sequences differ, the CTurret table aligned by hand. Pairs wrong: 0.
The `_saturate<Ui>` instance has no byte twin.

## gamez/zParticle (zparticle.cpp, zparticle_buf.cpp, zparticle_instance.cpp, zparticle_source.cpp)

All five uncertain rows are new, and confirmed: the map has no removed row near them, and no prototype
function does their work out of line.

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x2399f0 | - | new, owner guess | confirmed | builds an 11-quadword scratchpad packet (a tag then ten quadwords of 0x11000000 codes) and kicks it with zSysFifoKick; new call in Particle::Draw |
| 0x239b10 | - | new, owner guess | confirmed | stores a bool in a `$gp` byte (0x48d880), a CPnt3D scaled by 0.33 into three statics at 0x518d10 and 90.9 into 0x518d1c; called by CZKit::Apply_LensEffects (twice) and CZKit::Init |
| 0x239e80 | - | new, no owner | confirmed | adds a visual to the instance's node (+0x44), sets bit 7 of the node's +0x5c from the visual's flags, copies +0x6c to the node's +0x9c and calls the node's virtual +0x34 with 1; called by Create3Sided and CreateVisuals, which in the release call Destruction_Instance::Create and this instead of building the instance inline |
| 0x23cf30 | - | new, owner guess | confirmed | if the source's DI node (+0x100) is missing, creates it (0x23e1a0); stores a byte at +0x11c and passes it to the node's virtual +0x34; new call in zAnimParticleSourceTick |
| 0x23e1a0 | - | new, owner guess | confirmed | the "PARTICLE DI NODE" set-up (new CNode, six CDIPoly, AddDI, SetName, SetNodeEx) that the prototype Source constructor did; the release constructor (0x23dc90, 144 bytes instead of 1188) no longer does it, so the node is created on first use |

Sample: 15 of 15 sampled deviating rows are the same function on both sides (the Source constructor
by its one caller, Source::Create).
Cross-check: 108 pairs; 3 caller-set differences (callers added in new UIMapCtrl code, the
Destruction_Instance::Create call moved into Create3Sided, StopParticleSources gone), 1 substitution
(DrawXZ's fptosi calls replaced by VU0 calls), 9 of 80 caller sequences differ (the calls above), 2
vtables equal, 20 twin ties among the SequenceEntry vector instances decided by the call order in the
shared callers. Pairs wrong: 0.

## gamez/zRender (zrndr_pipe.cpp, zrndr_init.cpp)

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x249f10 | - | new, copy, owner guess | confirmed | `jr ra; move v0, a0`: returns its argument. InterruptFromVIF1 and CTexManager::DestroyBuffers pass a CGSTexBuffer's +28 and InterruptFromVIF1 reads the word it returns (the prototype read the buffer's +0x20 directly) |
| - | 0x246440 `__ct__5CPipeFv` | removed | confirmed | inlined into `__sinit_zrndr_pipe.cpp`: the release sinit calls the list_deleter constructor, malloc, the DelayedNode vector constructor, calloc and resize itself |
| - | 0x246580 `__ct__…compressed_pair_imp<…allocator<15tag_DelayedNode>,Ui,1>FUi` | removed | confirmed | its only caller was the CPipe constructor |

Hand-over (matrix stack): the release keeps the CStack destructor (0x218490, exact) and all five file
statics: `stack` in grid_di, grid_clutter, zrndr_pipe and seal_env, and `ai::ai_line_stack`, each
registered with `__register_global_object` in its sinit. The start state is unchanged: `m_pointer`
starts at -1 and `m_top` at `m_stack` - 64 (release 0x4efe30 = 0x4efe70 - 0x40; prototype 0x4d7920 =
0x4d7960 - 0x40), one slot below the base. The four plain statics are built with their flag byte 0
(no push); `ai_line_stack`'s static constructor in `__sinit_seal_ailines.cpp` (0x485120) sets its flag
to 1, raises `m_pointer` by 1 and `m_top` by 64 and copies the identity CMatrix (0x4673b0, built by
`__sinit_zmath_matrix.cpp`) into the first slot with sceVu0CopyMatrix, as the prototype did.

Sample: 15 of 15 sampled deviating rows are the same function on both sides.
Cross-check: 55 pairs; 7 caller-set differences (the CPipe constructor inlined into the sinit, two
new callers of CBBox8::Build, a new CTexManager caller of the vector_deleter clear), 0 substitutions,
6 of 52 caller sequences differ (the same), 10 twin ties among the vector_imp instances decided by the
call order in CPipe::Flush and the sinit. Pairs wrong: 0.

## gamez/zCharacter (char_type.cpp)

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x24b6c0 | - | new, owner guess | confirmed | CCharacterType getter: returns the sound handle at +0x120 + 4·index for an index 0 to 66, else 0. OnStunDamage now calls it where the prototype looked the sounds up by name (FindAnimType, CSnd::GetSoundByName) |
| 0x24bcf0 | - | new, owner guess | confirmed | a new CSnd virtual, slot 9 (the CSnd table grows from 9 to 10 slots): stores 3 into the byte at +0x24. Owner by position only |
| 0x24edd0 | - | new, owner guess | confirmed | walks `m_char_list` and, for each type whose +0 is set, clears +0 and +0x18 (once looping over `m_gear_list` with an empty body); new call in CMission::Close after CleanupTemporary |

Sample: 15 of 15 sampled deviating rows are the same function on both sides.
Cross-check: 64 pairs; 12 caller-set differences (new callers in zSeal and FTS code, CAiSReload::Tick
no longer plays the sound, the node_wave sinit no longer instantiates the list<PCv> pieces now that
RTPool<CRipple> is gone, and the list assignments that became vector assignments in the settled
zArchive pairs 0x1dbce0/0x1dbd10), 1 substitution (do_assign calls `init` instead of `alloc`), 8 of 66
caller sequences differ, 1 vtable differs (CSnd, the new slot), 6 twin ties. The twin scorer ranked
`second__…compressed_pair_imp<…158…>` (0x176a10, called in 320 places) above the paired `alloc` of
list_deleter<PCv> (0x2503c0); the `__sinit_char_type.cpp` call order decides it: both sides call the
compressed_pair constructor, alloc, the allocator constructor, the compressed_pair_imp constructor and
`second` in that order at the same offsets, so the pairs of 0x2503a0 to 0x2503d0 are right. Pairs
wrong: 0.

## gamez/zValve (valve_main.cpp, valve_list.cpp)

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x2f8600 `GetValue__14VALVE_CMD_DATAFv` | removed | confirmed | inlined into its only caller VALVE_CMD_DATA::Compare, which now calls GetValve (CZAnimArgList and CZAnim) twice itself |
| - | 0x2f8730 `debugValve__FP6CValveb` | removed | confirmed | the valve-watch debug hook; MakeCallbacks, CmdParseCmp (four calls) and Compare dropped their calls |

Sample: 5 of 5 deviating rows are the same function on both sides.
Cross-check: 33 pairs; 4 caller-set differences (callers added or dropped in network, HUD and menu
code), 0 substitutions, 30 of 148 caller sequences differ, none by a crossed pair of valve functions,
1 tie (Uninit) decided by its shared caller. Pairs wrong: 0.

## gamez/zSoftImage (si_object.cpp, si_script.cpp)

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1e02f0 | - | new, owner guess | confirmed | shares the script at an index of `boneArchive` into this script (through new zBone 0x1dea00) and keeps the result in bit 0 of +4, which it returns; called by BodyAddAnim next to its call of Load(const char*, bool) |

The tie of SetTimeScale (0x1df880) is decided by slot 3 of the CZSIScript table on both sides.

Sample: 9 of 9 deviating rows are the same function on both sides.
Cross-check: 30 pairs; 2 caller-set differences (a new caller of Share, new callers of
vector_pod<Ui>::erase), 1 substitution (CreateAndReadIt's list calls became vector calls), 2 of 39
caller sequences differ, 2 vtables equal. Pairs wrong: 0.

## gamez/zMath (zmath_main.cpp, zmath_matrix.cpp, zmath_pnt3d.cpp, zmath_pnt4d.cpp, zmath_trig.cpp)

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x220610 `Pow__5CQuatFfP5CQuat` | removed | confirmed | its only caller, CZSealBody::NormalizeToTerrain, no longer calls it; it interpolates the vectors with CPnt3D::Interp before Align instead |

Hand-over (small templates): no instance is given to the wrong twin. `_saturate<i>`, `<Ui>` and `<f>`
(owned by zAI and zVehicle) and the `_min`/`_max` instances have no byte twin on either side. The only
zMath rows with byte twins are the CFRect and CMatrix default constructors, each with one caller that
corresponds (CMatrix's is `__sinit_zmath_matrix.cpp`). The 92-byte `swap<vector>` instances (zVehicle,
zRender, zGame) are byte twins of each other; every one is decided by its single caller.

Sample: 15 of 15 deviating rows are the same function on both sides.
Cross-check: 48 pairs; 17 caller-set differences, all callers of the small CPnt3D/CQuat helpers that
were added, moved or dropped in zSeal, zAI and FTS code, 1 substitution (fabs replaced by fabsf in
CMatrix::ToEuler), 37 of 311 caller sequences differ, none by a swap of two zMath functions. Pairs
wrong: 0.

## gamez/zBone (bone_archive.cpp, bone_init.cpp)

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x1dea00 | - | new, owner guess | confirmed | CScriptArchive method: takes the script at an index of the archive's array (+8) and, if there is one, shares it into the given script with CZSIScript::Share; returns whether it found one. Only caller zSoftImage 0x1e02f0 |

Sample: 5 of 5 deviating rows are the same function on both sides.
Cross-check: 8 pairs; no differences in callers; 2 substitutions (Fetch and the destructor use
vector_pod<Ui> where the prototype used list<PCv>: the archive's script list is an array now). Pairs
wrong: 0.

## gamez/zSave (zsav_manager.cpp, zsav_module.cpp)

No uncertain rows. Sample: 3 of 3 deviating rows are the same function on both sides.
Cross-check: 15 pairs, no differences; the two empty UnSerialize overloads are decided by their slots
in the four CSaveModule-derived tables. Pairs wrong: 0.

## gamez/zReader (zrdr_archive, zrdr_edit, zrdr_file, zrdr_local, zrdr_main, zrdr_parse)

No uncertain rows. Sample: 8 of 8 deviating rows are the same function on both sides (the low
similarities of zrdr_findint, zrdr_findIPNT2D and zrdr_toINT come with 37, 9 and 2 shared callers).
Cross-check: 100 pairs; 19 caller-set differences (the network-config code that is gone, and new
callers of the reader and CRdrEditor in UI and online code), 0 substitutions, 42 of 313 caller
sequences differ, none by a swap of two reader functions, 5 twin ties decided by call order. Pairs
wrong: 0.

## gamez/zIntersect (int_bbox.cpp, int_main.cpp, int_material.cpp)

No uncertain rows. Sample: 10 of 10 deviating rows are the same function on both sides.
Cross-check: 62 pairs; 7 caller-set differences (new and dropped zSeal callers, the CZSealBody
constructor now allocates its DiIntersect, Particle::Source's CDIPoly set-up moved to 0x23e1a0), 0
substitutions, 6 of 105 caller sequences differ. The one table difference is the tool's: it reads the
release CDI table as 3 slots because slots 3 and 4 are zero, while the words of all three CDI tables
are the same on both sides (Read in slot 5). The tie of CDIBBox::GetAltitude is decided by slot 4.
Pairs wrong: 0.

## gamez/zGraph (graph_edge, graph_graph, graph_node, graph_route, graph_tree)

No uncertain rows. Sample: 1 of 1 deviating row is the same function on both sides.
Cross-check: 50 pairs; 1 difference (two coincidental prototype data words), 1 substitution
(BuildTree's double-precision math dropped), 3 twin ties decided by call order. Pairs wrong: 0.

## gamez/zGame (game_engine, game_main, game_state)

No uncertain rows. Sample: 1 of 1 deviating row (StartEngine, slot 3 of the CGame table) is the same
function on both sides.
Cross-check: 52 pairs; 17 caller-set differences, all prototype callers in the removed network-config
state machine (the CCnfStateMachine deque) or menu code that moved. Pairs wrong: 0.

## gamez/zConsole

No uncertain rows, no deviating rows.
Cross-check: 37 pairs, no differences. The twins are decided by their slots (GetPacketMsg in the
CPacket and CPacketMsg tables, OnDisconnect and OnDestroy in slots 2 and 3 of CConsole) or by their
loads in CConsole::OnConnect (_on_ping at +0xb0/+0xd4, _on_error at +0x134/+0x158 on both sides).
Pairs wrong: 0.

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x397a00 | 0x37cfc0 | slot 1 of the CTurret table (no RTTI word) on both sides; the base CEntity::GetPosW changed the same way (stores the position at +0x1c) | socom-release-check-small-3 | 2026-11-26 | | |
| 0x396d60 | 0x37cf60 | slot 0 of the CTurret table | socom-release-check-small-3 | 2026-11-26 | | |
| 0x3979f0 | 0x37b1e0 | slot 6 of the CTurret table | socom-release-check-small-3 | 2026-11-26 | | |
| 0x3979e0 | 0x37b1d0 | CTurret table slot 7 (prototype) / 8 (release, after the new CEntity slot 0x1f38f0) | socom-release-check-small-3 | 2026-11-26 | | |
| 0x239e80 | new | adds a visual to a Destruction_Instance's node; callers Create3Sided and CreateVisuals; first function of the instance file's range | socom-release-check-small-3 | 2026-11-26 | src/gamez/zParticle/zparticle_instance.cpp | |

Rows that change together: 0x397a00 and the removed 0x37cfc0 (one row once paired).

## New and removed

New (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x2399f0 | sends a VIF flush packet before the particle draw | guess: `Flush__8ParticleFv` (its caller Particle::Draw) |
| 0x239b10 | sets the lens-effect tint (a bool and a colour scaled by 0.33) | guess: `SetLensTint__8ParticleFbRC6CPnt3D` (callers in CZKit's lens effects) |
| 0x239e80 | attaches a visual to the instance's node | guess: `AddVisual__Q28Particle20Destruction_InstanceFPQ23zdb7CVisual` (receiver layout, callers) |
| 0x23cf30 | creates the source's DI node on first use and switches it on or off | guess: `SetActive__Q28Particle6SourceFb` (the virtual +0x34 with a byte) |
| 0x23e1a0 | the source's DI node set-up, moved out of the constructor | guess: `CreateDINode__Q28Particle6SourceFv` (string "PARTICLE DI NODE") |
| 0x249f10 | returns its argument; a reference accessor of a CGSTexBuffer member at +28 | guess: an out-of-line header inline; owner zrndr_pipe.cpp by position only |
| 0x24b6c0 | a character type's sound handle by index | guess: `GetSound__14CCharacterTypeCF15CHARACTER_SOUND` (index range 0..66, the enum's use in PlayAt) |
| 0x24bcf0 | new CSnd virtual (slot 9): sets the byte at +0x24 to 3 | guess: a CSnd state setter; owner char_type.cpp by position only |
| 0x24edd0 | clears the loaded state of every character type at mission close | guess: `ResetAll__14CCharacterTypeFv` (caller CMission::Close) |
| 0x1e02f0 | loads a script by sharing an entry of the bone archive | guess: `Load__10CZSIScriptFi` (next to Load(const char*, bool), same caller) |
| 0x1dea00 | shares the archive's script at an index into another script | guess: `Fetch__14CScriptArchiveFiP10CZSIScript` (next to Fetch(const char*, CZSIScript*, bool)) |

Not new, though the map has it as new: 0x397a00 (`GetPosW__7CTurretCFv`).

Really removed:

- CPipe's constructor and the compressed_pair_imp constructor it called: inlined into
  `__sinit_zrndr_pipe.cpp`.
- VALVE_CMD_DATA::GetValue: inlined into Compare. debugValve: the debug hook's calls are gone.
- CQuat::Pow: its one caller interpolates instead.
- Not removed, though the map has it: CTurret::GetPosW (0x397a00).

## Still unsure

None of the rows. Open points:

- The names of the new functions are guesses.
- The owners of 0x249f10 and 0x24bcf0 are by position only; both look like header inlines (a
  CGSTexBuffer member accessor and a CSnd virtual).

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| removed | 6 | 5 | 1: CTurret::GetPosW is 0x397a00 |
| new | 12 | 11 | 1: 0x397a00 is CTurret::GetPosW |
| exact, identical-copy | 3 | 3 (the counterparts were right) | 0 |

The sample: 116 of 116 sampled deviating rows are the same function on both sides.

The cross-check: 719 paired rows compared (callers, address loaders, vtable slots, data words, own
ordered calls and loads), the ordered calls of 1299 paired callers, 21 vtables slot by slot plus the
CTurret table by hand, 177 rows with byte twins scored by shared callers, and the data-word
neighbourhoods of every row with a data word. Differences looked at: 90 caller sets, 143 caller call
sequences, 9 call-order substitutions, 2 vtables, 60 twin ties and 1 twin flagged as beaten. They are
callers added, moved or dropped in the release (zSeal, FTS, UI and online code), the removed
network-config code, inlined constructors and helpers, list-to-vector changes (CScriptArchive,
CZSIScript::CreateAndReadIt, zArchive's settled pairs), dropped double-precision math and coincidental
data words. The ties and the flagged twin are decided by vtable slots, by the call order in the shared
caller or by the load offsets in the loader.
Pairs wrong: 0.

What misled it:

- CTurret::GetPosW: the release changed the slot's contract (store the position at +0x1c, no
  return value) and the body shrank to a load/store copy; the tool does not see the CTurret table,
  which has no RTTI word, so the slot could not pair it. The same blind spot left the table's three
  byte-identical entries as `identical-copy`.
- The release CDI table is read as 3 slots (two zero slots end it), the prototype's as 6 from its
  symbol size; the slot comparison then reports a dropped Read slot that is not dropped.

What cost the most time: the template twins in `__sinit_char_type.cpp`, where the twin scorer prefers
a generic accessor with 320 callers. Suggestions:

- Let the vtable finder accept a table whose RTTI word is 0 when the following words are function
  starts (the CTurret table).
- Do not end a release table at zero words when the paired prototype table has slots past them.
