# Audit of the unlocated unmarked functions, remaining areas (2026-11-15, socom-port-audit-c2)

Scope: the rows of `build/port/unmarked/unmarked-not-found.md` (functions of the reference ELF that no
`@socom-skeleton` marker names and whose name search found no definition in `src/`) whose nearest
marked file is outside the areas of the two other audit workers (zSeal, zFTS, zEntity, zAI, zInput,
zWeapon, zValve, zVehicle, zCharacter, zBody, zGame; zUI, zTwoD, zAnim, Apps/FTS): 34 rows in
zArchive, zCamera, zGraph, zGrid, zIntersect, zNetwork, zNode, zParticle, zReader, zRender, zSave,
zSound, zSystem and zVisual. Also from list C (`audit-unmarked-c.md`): `CPnt4D::Sub` 0x236720 and
the open question on `zdb::CCamera`'s port-only `m_yaw` / `m_pitch`. Each row was disassembled
from `support/socom.elf`, its callers found (`jal`, and for the destructors with no `jal` caller
the `__register_global_object` calls of the `__sinit_*` functions), and compared with the port's
class definition. The standard is the ELF's behaviour. No marker was added, moved or changed and no
function moved. HEAD 8aafdbdb.

## Counts
- 36 rows (34 + CPnt4D::Sub + the CCamera layout): EQUIVALENT-IMPLICIT 20, LOCATED-MATCH 2,
  WRITTEN 8 (with the CCamera fix counted here as a layout change), PROVIDER 3, LEFT 3.
  LOCATED-FIXED 0.

## How the destructors are reached
Almost every destructor row has no `jal` caller: it is the destructor of a global object that its
unit's `__sinit_*` registers with `__register_global_object`, so it runs only at static destruction
(never in normal play: the port calls `exit` only when a mission fails to load). The mission ->
menus round trip does not run any of them, so none of these rows changes the heap figures.

## Written (ELF addresses)
- `CPnt4D::Sub` 0x236720 (zmath.h, inline): `sceVu0SubVector(out, this, other)`, all four
  components. `sceVu0SubVector` 0x152450 (`vsub.xyzw`) added to `port/compat/libvu0.c` /
  `libvu0.h` (the port had none). Wired to both ELF callers: `Destruction_Instance::Tick`
  (0x236660, the friction relaxation towards the wind) and `clip3DLine` (0x2ffe24 / 0x2ffea8, the
  end moved onto the plane). Both already subtracted inline with the same arithmetic, so nothing
  changes in the game; the calls now follow the ELF.
- `CAssetList::~CAssetList` 0x231b20 (node_assetlib.h, inline): `Clear()` (each library deleted,
  its slot NULLed, the nodes erased, `m_cache_model` NULL). Runs for `CAssetMgr::m_assets` and
  the recycle bin at static destruction only; the port's implicit destructor freed only the nodes.
- `Particle::Instance::List::~List` 0x2377f0 and `Particle::Source::List::~List` 0x23b8b0
  (zparticle.h, inline): every element deleted, then the nodes erased (static destruction only).
  ELF quirk not kept in the source list's destructor: it reads the next link from the node that
  `~Source` has just unlisted and freed; the port takes the next element first (as its `Uninit`).
- `CGTreePool` 0x210fd0 (graph_tree.cpp): `_pool` (0x4d6df0, 12 bytes) is a list built and
  registered by `__sinit_graph_tree.cpp` and used by nothing else; the port had a 12-byte
  placeholder. Now a `CGTreePool : std::list<const void*>` (element type unproven), whose implicit
  destructor is the ELF's (nodes erased, nothing deleted).
- `zdb::AddonPoint::AddonPoint` 0x30e750 (zvis.h): `m_uv` copied from `CPnt3D::zero`, `m_index`
  0, `m_unk0e` -1, position and normal words 0, `m_color` / `m_tri_normal` NULL (the six
  `decaldata` corners). Only `m_unk0e` differs from the zeroed static it replaces; nothing reads it.
- `zdb::tag_GlobalLight::tag_GlobalLight` 0x30e8a0 (zvis.h): `CVisual::m_customGlobalLight`
  (0x511580) is four 128-byte `tag_GlobalLight`, each two unit matrices (the ELF's two
  `sceVu0UnitMatrix` calls = the implicit constructor of two `CMatrix` members); the port had
  `unsigned char[512]`. Nothing in the ELF reads it.
- `zdb::CCamera`: the DWARF record (1312 bytes) ends with `m_fovMask` +0x514; the port-only
  `m_yaw` / `m_pitch` (zeroed by the constructor, never read) are removed (zcam.h, zcam_main.cpp).
  The other members keep their port order (it differs from DWARF; every access is by name).

## Provider
- `_PTT_HeartbeatCallback` 0x3f0290, `_PTT_SyncCallback` 0x3f0ae0 (libptt client, between
  `PTT_Destroy` and `PTT_Sync`) and `_PTTServer_SyncCallback` 0x3f6b00 (libptt server, beside
  `PTTServer_Sync`): the end-of-RPC callbacks of the push-to-talk voice library (they signal the
  library's semaphore and call the user's sync callback with the RPC buffer). Not the LPC-10 codec.
  Stand-ins: `port/compat/ptt_offline.cpp` (`PTT_Sync` / `PTTServer_Sync` answer -1 without an RPC;
  `_PTT_HeartbeatCallback` is an empty stand-in, never reached offline: the ELF's signals
  `g_heartbeatSemaphore`, which `PTT_HeartbeatPrepare` waits on).

## Left
- `CStack::~CStack` 0x2148d0: pops the matrix stack when the object's byte (+0) is set. The port's
  `CStack` has only static members and no such byte. The five `CStack` globals the ELF registers:
  four (grid_di, grid_clutter, zrndr_pipe, seal_env) are zeroed by their `__sinit` and never
  written, so their destructor does nothing; `ai::ai_line_stack` (seal_ailines.cpp, zSeal) is built
  pushed (byte 1, identity pushed at static init) and is a plain byte in the port (its comment says
  so). Nothing to pop in the port.
- `zrdr_sym::~zrdr_sym` 0x23f260 (frees the two strings at +0 / +4, zrdr_parse.cpp lines 240 /
  242): unreachable. `zrdr_symbols` is never filled in the ELF (only `__sinit_zrdr_parse.cpp` and
  `_eval_defined`, which reads it, refer to it); the list's destructor runs at exit on an empty
  list. The port's list holds `char*` and is never filled either.
- `CFileStack::~CFileStack` 0x23fa70: the ELF's file stack holds `CBufferIO` by value (insert
  copies, each erase runs `~CBufferIO` and `~CFileIO`, both closing); the port's holds
  `CBufferIO*`. `fstack` is erased at the end of `zrdr_read`, so at exit it is empty in both.

Later state (2026-11-25): none of the three is left. `CStack` has its flag byte, both
constructors and the destructor (inline in `zrender.h`); `ai::ai_line_stack` is a real `CStack`
built with the identity, `seal_env.cpp`'s `_stack` is a `CStack`, `CStack::m_top` starts one
below `m_stack` (0x4d7920, as the ELF's data has it) and `m_pointer` is the `int` depth index.
`zrdr_sym::~zrdr_sym` is written in `zrdr_parse.cpp`, and `CFileStack` holds `CBufferIO` by
value, so its implicit destructor is the ELF's.

## Findings for a later pass (marked functions, not changed here)
- `CFileStack::pop` (zrdr_parse.cpp) erases the whole stack; the ELF's 0x23f6e0 closes or
  releases the front file and erases only that element (`erase(begin())`). With a nested
  `#include` in a reader file the port would lose the outer file.
- `_eval_defined` (zrdr_parse.cpp): `while (fstack.size() > 2);` has an empty body (a spin when
  more than two files are open) and the body that follows does not follow the ELF's 0x23f0d0 (an
  identifier is gathered while reads succeed, then looked up by name in `zrdr_symbols`; the result
  is 1 only when found).
- The `#include` path of the reader pushes the address of a local `CBufferIO` (the ELF copies it).
- `ai::ai_line_stack` (zSeal): the ELF's static constructor pushes the identity onto the matrix
  stack; the port does not (noted in its comment).

## Runs (final tree: HEAD 8aafdbdb + these files + the c2dline.cpp edit; focus kept in every run;
## screenshots untracked, build/port/screenshots/53-audit/, `*_c2-*`)
- rn (`port/test-hooks/render` + the state hook, `pad_fire.txt`, `-DSOCOM_HOOK_MISSIONS=1
  -DSOCOM_HOOK_PLAY_AT=999999 -DRN_CAM=1200`, 240 s): intro movie skipped with CROSS, briefing
  cameras with X, 28 rounds fired; in the mission from 76.3 s to the end at 241 s (165 s), no STOP,
  frame time 0.0167 s (one 0.0169 sample), in use 23,118,804..23,119,940 B from 125 s to the end
  (steady). Its level differs from list C's rn2 (23.067 MB) by the run-to-run spread of the firing
  window: list C's own rn1 reached 23.108 MB at the same frame.
- cam (state hook, `-DSOCOM_HOOK_CAMS_PLAY`): m8bs plays in full (64.6 -> 85.7 s), then m8tut1
  (85.7 -> 100.5 s); no STOP.
- znet (`port/test-hooks/znet`): dlgNetConnect opens, the connect fails offline and the menu comes
  back to dlgMenu (in use 18,156,788 B, as at the first dlgMenu), then dlgNetConfig opens and
  returns; no STOP.
- def (`default.sh`: no hooks, no fake pad): boots to dlgMenu at 15.6 s, argc 1.
- rt (`port/test-hooks/state`, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8`, 770 s): eight
  missions and eight returns, no STOP; in use at the briefing 18,666,676 B at return 1, then
  18,666,772 B at returns 2-8: flat, 32 B under HEAD's 18,666,708 / 18,666,804 (the smaller
  CCamera). None of the written destructors runs on this path.

## Result table

| # | Address | Function | Verdict | Port | Evidence |
|---|---|---|---|---|---|
| 1 | 0x1d9e10 | zar::CKeyRing::~CKeyRing | EQUIVALENT-IMPLICIT | src/gamez/zArchive/zar.h (`CKeyRing : std::list<CKey*>`) | erase(begin, end) of a `list<const void*>`, then delete when deleting; no element deleted (caller: `__vector_deleter<CKey>` dtor, a CKey is a CKeyRing); GCC's implicit `~list` frees the nodes only |
| 2 | 0x1e45f0 | CMatrix::__cl (operator()(r, c) const) | LOCATED-MATCH | src/gamez/zMath/zmath.h (inline `operator()`) | this + r*16 + c*4 |
| 3 | 0x210670 | CGQueueAtom::CGQueueAtom(const CGQueueAtom&) | EQUIVALENT-IMPLICIT | src/gamez/zGraph/graph_tree.cpp (POD {node, cost}) | copies the word at +0 and the float at +4 (BuildTree's queue inserts) |
| 4 | 0x210fd0 | CGTreePool::~CGTreePool | WRITTEN | src/gamez/zGraph/graph_tree.cpp (`_pool`) | `_pool` 0x4d6df0 built and registered by `__sinit_graph_tree.cpp`, no other reference; was a 12-byte placeholder, now a `std::list<const void*>` class whose implicit dtor is the ELF's (nodes only) |
| 5 | 0x2148d0 | CStack::~CStack | LEFT | src/gamez/zRender/zrender.h (no byte member, no dtor) | pops m_pointer / m_top when +0 is set; the four zeroed globals make it a no-op; only `ai::ai_line_stack` (zSeal) is built pushed, and it is a byte in the port |
| 6 | 0x2174d0 | zdb::CDynTexList::~CDynTexList | EQUIVALENT-IMPLICIT | src/gamez/zTexture/ztex.h | the palette vector (+0xc) then the texture vector (+0) freed, elements not owned; the same members in the same order |
| 7 | 0x21d510 | PNT4D::__as | EQUIVALENT-IMPLICIT | src/gamez/zMath/zmath.h (POD of four floats) | x, y, z, w copied |
| 8 | 0x322320 | CZNetwork::~CZNetwork | EQUIVALENT-IMPLICIT | src/gamez/zNetwork/znet.h (two `std::list<void*>`) | the lists at +0x1258 then +0x124c erased, elements not deleted (static destruction, `__sinit_zNetDme.cpp`); online only: compared, untested |
| 9 | 0x322d00 | ClanMemberItem::~ClanMemberItem | EQUIVALENT-IMPLICIT | src/gamez/zNetwork/zNetMedius.cpp | the strings at +4 then +0; the callers (cbDisbandClan, GetClanRoster, cbRemovePlayerFromClan, ReleaseUIResources, ~ClanMemberDB) delete through typed vectors; online only |
| 10 | 0x327100 | MediusGameListResponse::__as | EQUIVALENT-IMPLICIT | port/compat/include/medius.h | memberwise: 21 chars, +0x18, +0x1c, 64 chars at +0x20, +0x60, +0x64, +0x68, +0x6c (cbGameList's record copy); the port's struct assignment copies the same members; online only |
| 11 | 0x3279d0 | LadderItem::~LadderItem | EQUIVALENT-IMPLICIT | src/gamez/zNetwork/zNetMedius.cpp | the strings at +4 then +0 (ReleaseUIResources, GetSurroundingLadderPosition, cbGetLadderInfo, ~LadderRankingDB); online only |
| 12 | 0x3f0290 | _PTT_HeartbeatCallback | PROVIDER | port/compat/ptt_offline.cpp | libptt client: iSignalSema(g_heartbeatSemaphore); the stand-in is empty, never reached offline |
| 13 | 0x3f0ae0 | _PTT_SyncCallback | PROVIDER | port/compat/ptt_offline.cpp (`PTT_Sync` -1) | libptt client: iSignalSema(g_syncSemaphore), then the sync callback with (reason, g_buffer, calldata) |
| 14 | 0x3ff3f0 | sceNetcnfifData::__as | EQUIVALENT-IMPLICIT | port/compat/include/netcnfif.h | memberwise copy of the 4928-byte record; no caller in the ELF |
| 15 | 0x223170 | CMatrix::__opRA4_A4_Cf (operator float(*)[4]() const) | LOCATED-MATCH | folded: callers use `m_matrix` | returns this; ComputeFacadeMatrix and CLensFlareSaturate::Tick pass the matrix's own address |
| 16 | 0x228eb0 | zdb::CTickLightList::~CTickLightList | EQUIVALENT-IMPLICIT | src/gamez/zNode/node_assetlib.h (`std::vector<CTickLight>`) | `__vector_deleter<CTickLight>` dtor; CTickLight is POD (CLight* not owned) |
| 17 | 0x2304b0 | zdb::CLightMapVector::~CLightMapVector | EQUIVALENT-IMPLICIT | src/gamez/zNode/node_assetlib.h (`std::vector<CLightMap*>`) | `__vector_pod` dtor, elements not owned (the three CVisual lists) |
| 18 | 0x231b20 | zdb::CAssetList::~CAssetList | WRITTEN | src/gamez/zNode/node_assetlib.h (inline `~CAssetList() { Clear(); }`) | each library deleted (CAssetLib dtor with delete), slot NULLed, nodes erased, +0xc NULL, then ~list; static destruction of m_assets and the recycle bin only |
| 19 | 0x236380 | Particle::BufferElement::BufferElement | EQUIVALENT-IMPLICIT | src/gamez/zParticle/zparticle.h | empty (`jr ra`), as the port's implicit ctor (CPnt4D() is empty too) |
| 20 | 0x2377f0 | Particle::Instance::List::~List | WRITTEN | src/gamez/zParticle/zparticle.h (inline) | each instance deleted (~Instance with delete), then the nodes erased; static destruction only |
| 21 | 0x23b8b0 | Particle::Source::List::~List | WRITTEN | src/gamez/zParticle/zparticle.h (inline) | each source deleted, then the nodes erased; quirk not kept: the ELF reads the next link from the freed node |
| 22 | 0x23bfa0 | CRdrArchiveList::~CRdrArchiveList | EQUIVALENT-IMPLICIT | src/gamez/zReader/zrdr.h (`std::list<zar::CZAR*>`) | nodes erased, archives not deleted (CRdrArchive::m_list) |
| 23 | 0x23f260 | zrdr_sym::~zrdr_sym | LEFT | - | _free of +0 (line 240) and +4 (line 242); unreachable: zrdr_symbols is never filled |
| 24 | 0x23fa70 | CFileStack::~CFileStack | LEFT | src/gamez/zUtil/util_stack.h (`std::list<CBufferIO*>`) | the ELF erases CBufferIO values (each closed by ~CBufferIO / ~CFileIO); the port holds pointers; fstack is empty at exit in both |
| 25 | 0x246cf0 | tag_DelayedNode::__as | EQUIVALENT-IMPLICIT | src/gamez/zRender/zrender.h | sceVu0CopyMatrix, then +0x40..+0x68 memberwise; +0x6c is not copied (tail padding of the 16-aligned record); the port also copies its m_unk6c, which nothing reads |
| 26 | 0x3f6b00 | _PTTServer_SyncCallback | PROVIDER | port/compat/ptt_offline.cpp (`PTTServer_Sync` -1) | libptt server: as row 13 with the server's semaphore, buffer and callback |
| 27 | 0x2f0250 | CSndInstanceVec::~CSndInstanceVec | EQUIVALENT-IMPLICIT | src/gamez/zSound/zsnd.h (`std::vector<CSndInstance*>`) | `__vector_pod` dtor of m_sound_instance_pool, instances not deleted |
| 28 | 0x2f4390 | CSched_Manager::~CSched_Manager | EQUIVALENT-IMPLICIT | src/gamez/zSystem/zsys.h | m_FreeList (+0x14) then the base list erased, tasks not deleted (zTaskScheduler, zUIScheduler) |
| 29 | 0x2f56d0 | CIOPManager::~CIOPManager | EQUIVALENT-IMPLICIT | src/gamez/zUtil/zutil.h | `__vector_deleter<CRegistrant>` dtor (POD registrants) |
| 30 | 0x30e750 | zdb::AddonPoint::AddonPoint | WRITTEN | src/gamez/zVisual/zvis.h | CPnt3D::zero copied to +0..+8, +12 = 0, +14 = -1, +16..+24, +32..+40, +28, +44 = 0 (decaldata's six) |
| 31 | 0x30e7b0 | zdb::CProjectedMapVector::~CProjectedMapVector | EQUIVALENT-IMPLICIT | src/gamez/zVisual/zvis.h (`std::vector<CPnt3D*>`) | `__vector_pod` dtor of m_projectedMapList |
| 32 | 0x30e8a0 | zdb::tag_GlobalLight::tag_GlobalLight | WRITTEN | src/gamez/zVisual/zvis.h, vis_main.cpp | two sceVu0UnitMatrix (+0, +0x40) for each of the four m_customGlobalLight entries; was unsigned char[512] |
| 33 | 0x30f690 | zdb::tag_VIS_PARAMS::__as | EQUIVALENT-IMPLICIT | src/gamez/zVisual/zvis.h | flag word, four bytes, +8 word, three floats (CMesh::Clone) |
| 34 | 0x311e90 | zdb::CLOD_band::__as | EQUIVALENT-IMPLICIT | src/gamez/zRender/zrender.h | six floats, the bitfield word, +0x1c (vector<CLOD_band> insert / erase) |
| 35 | 0x236720 | CPnt4D::Sub | WRITTEN | src/gamez/zMath/zmath.h (inline); sceVu0SubVector in port/compat/libvu0.c | tail call sceVu0SubVector(out, this, other); called from Destruction_Instance::Tick and clip3DLine as in the ELF |
| 36 | - | zdb::CCamera m_yaw / m_pitch | WRITTEN (layout) | src/gamez/zCamera/zcam.h, zcam_main.cpp | not in the DWARF record (last member m_fovMask +0x514, size 0x520); zeroed, never read: removed |
