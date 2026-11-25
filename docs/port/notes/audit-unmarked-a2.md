# Audit of unmarked functions, list A2 (2026-11-15, socom-port-audit-a2)

The 52 reference-ELF functions of the character, AI, entity and mission code (nearest marked file under
`gamez/zSeal`, `zFTS`, `zEntity`, `zAI`, `zInput`, `zWeapon`, `zValve`, `zVehicle`, `zCharacter`, `zBody`,
`zGame`) that no `@socom-skeleton` fence names and whose name a search did not find in `src/`
(`build/port/unmarked/unmarked-not-found.md`), plus the four NOT LOCATED rows of list A
([audit-unmarked-a.md](audit-unmarked-a.md)), and `CStack::~CStack` 0x2148d0, handed over by the list-C2 audit: 57 rows. Each was disassembled from the reference ELF, its
callers taken from the ELF (`jal` callers and the `__sinit` address references), and compared with the port's
class definition or with the code the port folded it into. Scratch `build/port/boot-audit-a2/` (untracked:
NOTES.md, `asm.txt` with the disassembly of every row, `xref.txt` / `addrref.txt`, `buildall.sh`). HEAD
85b06ea2, final checks on 8aafdbdb; no marker was added, moved or changed and no function moved file.

## Counts

| Verdict | Rows |
|---|---|
| LOCATED-MATCH | 14 |
| LOCATED-FIXED | 1 |
| EQUIVALENT-IMPLICIT | 32 |
| WRITTEN | 7 |
| LEFT | 3 |
| total | 57 |

## Static destructors

Most of the destructor rows belong to static objects: `__sinit_<unit>` builds the object
and hands the destructor to `__register_global_object`, so they run only from `exit()`. The game never leaves
`main` (`while (true) theGame.CGame::Tick(...)`); `exit()` is called only when `testLoad` / `testUnload` fail
(`st_core.cpp`, `exit(0)`) and when a seal has no body node (`seal.cpp`, `exit(-1)`). The port's GCC statics
are destroyed on the same paths (`__cxa_atexit`), in reverse construction order within a unit as the ELF's
chain. For the list and vector classes the element type decides the frees: an MSL `list_deleter<const void *>`
or `vector_pod<Ui>` of pointers frees its nodes or buffer and never the pointees, as a GCC `std::list<T *>` /
`std::vector<T *>`; a `vector_deleter<T>` / `list_deleter<T>` of values destroys the elements, as GCC does.
Where the ELF destructor also deletes the pointees (`CZSIScriptCommon::List`, `CValvePool`, `CZWeaponList`
through the virtual `~CZFTSWeapon`, `CDiPool`), the port's had to be written or checked one by one.

## Written (ELF addresses)

- `CDIDummy` 0x1f24f0, 0x1f2500, 0x1f2510, 0x1f2520 (`zFTS/fts_main.cpp`): the class did not exist. It is a
  file-local `zdb::CDI` (no DWARF record; vtable 0x471bb0, RTTI 0x44ce88) whose `GetIntersect` and
  `GetAltitude` return 0, with a new virtual `LoadTipAndTail(DiIntersect *)` (slot +0x20, empty) and a
  compiler-style destructor (its vtable, `~CDI`, delete when asked). Its one object is `di`, the DI record that
  `ftsGetAltitudeApprox`'s AI-map hits point at (`hit.m_poly`, only the material bits written). The port had
  `static zdb::CDIPoly di` with a note that the ELF never constructs it; `__sinit_fts_main.cpp` 0x46aa50 does
  (`CDI()`, then CDIDummy's vtable). In play: the same material is answered; a virtual test on an AI-map hit's
  DI now answers "no hit" instead of running a polygon test on a DI without points.

- `CValvePool::~CValvePool` 0x2f7120 (`zValve/valve_list.cpp`, declared in the `10CValvePool` fence of
  `zvalve.h`): was implicit (the vector's buffer only), so `CValvePool::FlushNames` (list A) had no caller. Now as
  the ELF: once `Open` has made the pool, the names flushed (forced), every pooled valve deleted, the vector
  emptied, the 4096-byte name buffer deleted and its three words cleared. ELF quirk kept: the pooled valves go
  only when the name buffer exists. Port deviation: `delete[]` for the buffer `Open` makes with `new[]` (the ELF
  pairs `__nwa` with `__dl`, the same free for a `char` buffer). At exit only.
- `CZFTSWeapon::~CZFTSWeapon` 0x28d880 (`zWeapon/zweapon.h`): declared and never defined, and `~CZWeapon` was
  not virtual, so `~CZWeaponList` (which deletes every weapon through a `CZWeapon *`, as the ELF's virtual
  deleting call) ran only `~CZWeapon` and leaked the zoom-range vector. `~CZWeapon` is now virtual (vtable slot
  +8 of `__vt__8CZWeapon` and `__vt__11CZFTSWeapon`) and `~CZFTSWeapon` is the compiler-generated one, as in the
  ELF (emitted in `seal_env.cpp`'s unit): its vtable, `m_zoommode`, `~CZWeapon`. The weapon list is a static
  (`CZWeapon::m_listWeapons`), so at exit only.
- `CZSIScriptCommon::List::~List` 0x1df000 (`zAnim/zanim.h` and `zSoftImage/si_script.cpp`, both kept as edit files
  because zAnim is another worker's): `CZSIScriptCommon::list` was a plain `std::vector`; in the ELF it is a `List`
  whose destructor deletes every common still listed, each as `~CZSIScript`'s last reference does (the inline
  `~CZSIScriptCommon`: no object pointer, one common fewer in `numSiCommon`, its body-object vector), then the
  vector. At exit only.

## Fixed

- `CBits::~CBits` 0x17f440: the port folds it into `CPickup::Close` (`zEntity/pickup_main.cpp`, the pool's
  pickups deleted with the `all` argument), where it NULL-tested the bit words before `_free`. The ELF frees
  them unconditionally, then clears the pointer; the test is gone (`free(NULL)` does nothing, so no change).

## Left

- `CValveSaveManager::~CValveSaveManager` 0x1fbdc0 and its object: `theValveSaveManager` (`zFTS/fts_mission.cpp`)
  is still the 24-byte `int[6]` placeholder. In the ELF it is a `CSaveModule("CValveSaveManager",
  theMemCard.m_config)` built after `theUIVarManager` (the ctor is inline in `__sinit_fts_mission.cpp` 0x46ac0c;
  the destructor is the compiler-style one: vtable, `~CSaveModule`), so the options save and load also carry the
  persistent valves (`Serialize` / `UnSerialize` in `valve_main.cpp` have no object to run on). It was written
  and taken out again: with the memory-card layer off it changes nothing in play, but its static construction
  (the module name's `zstrdup` and the manager's list node, 48 bytes) shifts the port's heap layout, so on the
  first return to the menus the 2,598,384-byte `memalign` of `uizanim.zar` (`zar_main.cpp:394`) no longer fits a
  free block (largest 2,289,664 instead of 3,985,408), the heap grows by 2.6 MB (arena 25,677,292 instead of
  23,076,332), and on HEAD 8aafdbdb the 4th return's menu load then failed an allocation assert in `zsys_`.
  A build without the object (`-DSOCOM_HOOK_MALLOC`) was back at arena 23,076,332 / largest block 3,985,408.
  Writing it needs the menu's large buffers to stop depending on the heap layout first.
- `CStack::~CStack` 0x2148d0: a one-byte "pushed" flag; when set, the matrix stack is popped (`m_pointer` - 1,
  `m_top` - 64). Its only objects are statics (`__sinit` of grid_di, grid_clutter, zrndr_pipe, seal_env,
  seal_ailines), so it runs at exit only; the one the ELF builds pushed is `ai::ai_line_stack`
  (`__sinit_seal_ailines.cpp` pushes the identity), which the port keeps as a plain byte and does not push
  (documented in `zSeal/seal_ailines.cpp`), so there is nothing to pop. Left with that deviation.
- `action_v18::action_v18(const action_v18 &)` 0x193330: the bitfield copy (all 36 bytes) used only by the
  `vector<action_v18>` of `ReadCellTableCvt<actions_v18>`, the reader of version 17 / 18 AI maps. That path is
  left out on purpose (`zAI/ai_mapio.cpp`: every map on the disc is version 19).

Later state (2026-11-25): none of the three is left. `theValveSaveManager` is a real
`CValveSaveManager` with its destructor in `fts_mission.cpp`; the version 16-18 AI-map reader is
written and `action_v18`'s copy constructor is the compiler's memberwise one; `CStack` is as the
ELF has it (see [audit-unmarked-c2.md](audit-unmarked-c2.md)).

## Notes

- `CPnt3D::operator+` / `operator*` are declared in `zmath.h` as non-const members returning a reference and are
  never defined; the ELF's (`__pl__6CPnt3DCFRC6CPnt3D`, `__ml__6CPnt3DCFf`) are const and return by value.
  Their two ELF callers' arithmetic is in `CDynGrenade::PosAt` (`seal_control.cpp`) through `Scale` and `Add`.
  The declarations are left as they are (zMath is another worker's).
- `CPipe::tag_DelayedNode`'s implicit copy also copies `m_unk6c` (+0x6c), which the ELF copy constructor skips
  (the record's padding to 112 bytes); nothing reads it.

## Result table

| Address | Function | Verdict | Port | Evidence |
|---|---|---|---|---|
| 0x17f440 | CBits::~CBits | LOCATED-FIXED | zEntity/pickup_main.cpp CPickup::Close | `_free(m_vec)` without a NULL test, `m_vec = 0`; its only ELF caller is Close |
| 0x17fbf0 | CBits::GetWordCount | LOCATED-MATCH | inline: ai_events.cpp, pickup_main.cpp, seal_aievent.cpp | `(n >> 5) + 1` |
| 0x17fc00 | PNT3D::operator= | EQUIVALENT-IMPLICIT | zMath/zmath.h | three floats |
| 0x193330 | action_v18::action_v18(const &) | LEFT | - | only the version 17 / 18 AI-map reader, left out on purpose |
| 0x19d890 | CAiMapLocVec::CAiMapLocVec | EQUIVALENT-IMPLICIT | zAI/zai.h | empty vector (static in ai_maps.cpp) |
| 0x1a9170 | CPnt3D::operator= | EQUIVALENT-IMPLICIT | zMath/zmath.h | three floats (CLadderData vector) |
| 0x1df000 | CZSIScriptCommon::List::~List | WRITTEN | zAnim/zanim.h, zSoftImage/si_script.cpp | deletes every listed common at exit |
| 0x247230 | tag_DelayedNode::tag_DelayedNode(const &) | EQUIVALENT-IMPLICIT | zRender/zrender.h CPipe::tag_DelayedNode | matrix and +0x40..+0x68; +0x6c padding not read |
| 0x249500 | LOD::~LOD | EQUIVALENT-IMPLICIT | zRender/zrender.h | the two strings, m_name then m_file |
| 0x24a040 | CCharacterGearList::~CCharacterGearList | EQUIVALENT-IMPLICIT | zCharacter/zchar.h | list of pointers: nodes only (static) |
| 0x1eec00 | CSaferStr::CSaferStr | EQUIVALENT-IMPLICIT | zSystem/zsys.h | empty string |
| 0x1ef880 | CEntityList::~CEntityList | EQUIVALENT-IMPLICIT | zEntity/zentity.h, ent_main.cpp / ent_target.cpp lists | nodes only (statics) |
| 0x1f13b0 | CTarget::operator=(const CTarget &) | EQUIVALENT-IMPLICIT | zEntity/zentity.h | the 40 bytes (sort, vector erase / insert) |
| 0x24c280 | CCharacterModelCache::~CCharacterModelCache | EQUIVALENT-IMPLICIT | char_type.cpp m_ModelCache | pointer vector: buffer (static) |
| 0x24c380 | CCharTypeVec::~CCharTypeVec | EQUIVALENT-IMPLICIT | char_type.cpp m_char_list | pointer vector: buffer (static) |
| 0x24d640 | CPickupList::~CPickupList | EQUIVALENT-IMPLICIT | pickup_main.cpp m_list / m_pool | nodes only (statics) |
| 0x25aba0 | Rfloat::operator float | LOCATED-MATCH | RandomIn (seal_ai.cpp), SquirmDraw, turret_draw, rfloat_draw, inline draws | range 0: min; else min + range * (rand() * 2^-31) |
| 0x1f2520 | CDIDummy::~CDIDummy | WRITTEN | zFTS/fts_main.cpp | vtable, ~CDI (static `di`) |
| 0x1fbdc0 | CValveSaveManager::~CValveSaveManager | LEFT | - (theValveSaveManager is int[6]) | written, then taken out: its 48-byte static allocation fragments the port heap (see Left) |
| 0x1fbe20 | CUIVarSTable::~CUIVarSTable | EQUIVALENT-IMPLICIT | zUI/zui.h | ~CSTable (CUIVarManager's two tables) |
| 0x1fd4e0 | AI_PARAMS::operator= | EQUIVALENT-IMPLICIT | zAI/zai.h | the 15 words (CMission::LoadVehicle) |
| 0x1fe4f0 | CSpawners::~CSpawners | EQUIVALENT-IMPLICIT | zFTS/zfts.h | m_spawn (+0xc) then m_unused (+0x0); POD elements |
| 0x1ff8d0 | CNodeAction::Container::~Container | EQUIVALENT-IMPLICIT | zNode/node_action.h | nodes only (static) |
| 0x205dd0 | CZSealState::CRemoteGuyList::~CRemoteGuyList | EQUIVALENT-IMPLICIT | fts_net_seal.cpp m_RemoteGuyList | nodes only (static) |
| 0x20e560 | CPool::~CPool | EQUIVALENT-IMPLICIT | game_state.cpp m_pool | elements (empty dtor) and buffer (static) |
| 0x21b800 | CCheatList::~CCheatList | EQUIVALENT-IMPLICIT | zInput/zinput.h | pointer vector: buffer (static) |
| 0x2cdf70 | CAnimAuxData::CList::~CList | EQUIVALENT-IMPLICIT | anim.cpp CAnimAuxData::list | pointer vector: buffer (static) |
| 0x2cdfe0 | AnimSet::List::~List | EQUIVALENT-IMPLICIT | anim.cpp AnimSet::list | pointer vector: buffer (static) |
| 0x2553c0 | zdb::IntersectStruct::GetMaxRegionShift | LOCATED-MATCH | zSeal/seal.cpp MaxRegionShift | 0 for 0, else the highest set bit (CZSealBody::PostTick) |
| 0x258eb0 | zdb::DiIntersect::__defctor | LOCATED-MATCH | zIntersect/zintersect.h default argument | DiIntersect(8) for `pi_diIntersect[1]` |
| 0x259040 | CCompass::~CCompass | EQUIVALENT-IMPLICIT | zSeal/zseal.h | pointer vector: buffer (static) |
| 0x263960 | Rfloat::operator=(float) | LOCATED-MATCH | seal_ai.cpp goal timers | m_min = f, m_range = 0 (AttackTick) |
| 0x27d480 | CActiveAnimList::~CActiveAnimList | EQUIVALENT-IMPLICIT | rt/rtlist.h ~RTList | delete[] of the item pool (static newanims) |
| 0x287890 | CPnt3D::operator+ (const) | LOCATED-MATCH | seal_control.cpp CDynGrenade::PosAt | pos.Add(vel * t) |
| 0x2878e0 | CPnt3D::operator* (const) | LOCATED-MATCH | seal_control.cpp CDynGrenade::PosAt | vel.Scale(t) |
| 0x28c070 | CharacterDynamics::~CharacterDynamics | EQUIVALENT-IMPLICIT | zCharacter/zchar.h | m_cam_params (+0x1b0) vector (static) |
| 0x28d880 | CZFTSWeapon::~CZFTSWeapon | WRITTEN | zWeapon/zweapon.h | ~CZWeapon virtual; implicit dtor frees m_zoommode |
| 0x29b630 | _TransformPoint | LOCATED-MATCH | seal_ailines.cpp ai_line_transform; seal_env.cpp GetCharacterHit | the point times vf4-vf7 (the stack top / world-to-screen) |
| 0x2a46e0 | CQuat::CQuat | EQUIVALENT-IMPLICIT | zMath/zmath.h | empty (statics in seal_env.cpp) |
| 0x2b0d00 | CDiPool::dir::dir | LOCATED-MATCH | zSeal/seal_sensors.cpp | +0x0 byte, +0x20 +0x28 +0x2c +0x30 words zeroed |
| 0x2b3e40 | CDiPool::~CDiPool | LOCATED-MATCH | zSeal/seal_sensors.cpp | DiIntersects destroyed and freed, m_active nodes only, m_free's requests deleted |
| 0x2b9aa0 | CAiMap::region::GetTypeName | LOCATED-MATCH | seal_tasks.cpp regionTypeName | jump table 0x4548d0: DEFAULT, EXTRACT_ZONE, SAFE_HOUSE, WORM_HOLE, ROUTER, HUD_VISIBLE, GUARD, else UNKNOWN |
| 0x2d6b50 | CSealUnit::ulist::~ulist | EQUIVALENT-IMPLICIT | seal_unit.cpp CSealUnit::m_list | nodes only (static) |
| 0x2df0c0 | CAiDodge::CList::~CList | EQUIVALENT-IMPLICIT | zSeal/zseal.h | nodes only (static) |
| 0x2e35e0 | ai::color_stack::~color_stack | EQUIVALENT-IMPLICIT | zSeal/zseal.h | CPnt3D nodes (static) |
| 0x2e9e60 | CTarget::operator=(const CTarget *) | LOCATED-MATCH | seal/ai_target.cpp assign_target | NULL: m_ent = 0 only; else every member (CAiTarget::SetTarget) |
| 0x2f7120 | CValvePool::~CValvePool | WRITTEN | zValve/valve_list.cpp | FlushNames(true), pooled valves deleted, name buffer freed |
| 0x2f7210 | CValveList::~CValveList | EQUIVALENT-IMPLICIT | valve_list.cpp CValve::m_list | nodes only (static) |
| 0x1a2b30 | CAiVisMapList::~CAiVisMapList | EQUIVALENT-IMPLICIT | ai_vismap.cpp globalVisMap / dynamicVisMap | nodes only (statics) |
| 0x1a41b0 | CVehicleRdrEntry::operator= | EQUIVALENT-IMPLICIT | zVehicle/zvehicle.h | the 268 bytes (vector erase / insert) |
| 0x316480 | CWepCallbackList::~CWepCallbackList | EQUIVALENT-IMPLICIT | zwep_global.cpp m_callbacks | POD elements and nodes (static) |
| 0x316e50 | zdb::CWorld::GetAssetList | LOCATED-MATCH | zwep_projectile.cpp HookupReset | &CAssetMgr::m_assets |
| 0x25ab90 | CTarget::GetEntity | LOCATED-MATCH | seal_ai.cpp pursue_seen / CAiSPursue::Tick | m_ent (+0x0) |
| 0x1f24f0 | CDIDummy::GetIntersect | WRITTEN | zFTS/fts_main.cpp | 0 |
| 0x1f2500 | CDIDummy::GetAltitude | WRITTEN | zFTS/fts_main.cpp | 0 |
| 0x1f2510 | CDIDummy::LoadTipAndTail | WRITTEN | zFTS/fts_main.cpp | empty |
| 0x2148d0 | CStack::~CStack | LEFT | - (ai::ai_line_stack is a byte, never pushed) | pops the matrix stack when its flag is set; statics only, exit only |

## Runs

Final tree: HEAD b13e0497 + this audit's files; focus kept in every run except one (below); screenshots in
`build/port/screenshots/53-audit/` (`*_a2_*`).

- Stability (zseal4's scratch hook + `pad_fire.txt`, 165 s: intro movie skipped with CROSS, briefing cameras
  with X, firing): no STOP, no exception; 63 "fires at" lines (enemies at the player, the team back), OutPatrol1 /
  OutPatrol3 killed and respawned (alive again at 92.9, 97.1, 127.6 s), the team FOLLOWING / ENGAGING on the
  HUD; heap in use 22.89-23.48 MB over 100-166 s.
- `port/test-hooks/win` (-DSOCOM_HOOK_WIN, 235 s): the player in Extract at 205.1 s, mission_complete 0 -> 1 at
  209.1 s, "EXIT: debrief open (objectives 3/7)" at 211.0 s, MISSION SUCCESSFUL on screen. (A first try was
  ended from outside at 17 s with no error and was run again.)
- `port/test-hooks/state` (-DSOCOM_HOOK_MISSIONS=8): in use 18,666,948 B at return 1, then 18,667,044 B at returns 2-8, arena 23,076,332 throughout: flat. (The 240 B above the 18,666,804 of earlier HEADs come with b13e0497 / 4ceb6786: on 8aafdbdb the same files of this audit gave exactly 18,666,804, the HEAD value.)
- Default build (no hooks, no fake pad): dlgMenu at 15.6 s, the main menu on screen.
- On HEAD 8aafdbdb the same tree (and the state run, flat at 18,666,804 B from return 2, arena 23,076,332) had
  passed too; one stability run there reported "focus kept: False" (no foreground window before it started, the
  emulator window then had the focus).

None of the written destructors runs on the mission -> menus path (all are static objects' destructors, run
only from `exit()`), so the round trip is unchanged.

`python tools/socom.py audit independence --strict` passes.
