# Audit of the unmarked functions, list C (2026-11-15, socom-port-audit-c)

Scope: the 101 functions of list C (network, scene graph, rendering, system) that the reference ELF
has and no `@socom-skeleton` marker names, but for which a definition of that name exists in `src/`.
Each was disassembled from `support/socom.elf` and compared instruction by instruction with the
port's definition (stores, calls, loops, constants, member and base initialisation, return value).
The standard is the ELF's behaviour; ELF quirks are kept. No marker was added, moved or changed and
no function moved. Started at HEAD 86052025; final checks at HEAD 85b06ea2.

## Counts
- 101 rows: MATCH 91, FIXED 5, KEPT 4, EQUIVALENT-IMPLICIT 0, NOT LOCATED 1. None left.
  (The eleven CSealStats getters share one table row.)

## Fixes (ELF addresses)
- `init_trig_table` 0x223050 (zmath_trig.cpp): the angle step is the float 0x3cc90fdb (pi/128, lui/ori
  at 0x223080); the port's literal 0.02454369f encoded 0x3cc90fd9. Now 0.024543693f. The sin / cos
  tables move by at most one float step; nothing visible.
- `Particle::Instance::Tick` 0x237380 (zparticle.h, inline): position, velocity and the wind
  relaxation are VU0 `.xyz` operations (0x2374c8, 0x2374f0, 0x23763c-0x237654), so the w words of
  m_pos and m_vel never change. The port also integrated and relaxed w. Particle xyz motion is
  unchanged; no picture change in the runs. (`Destruction_Instance::Tick` 0x236390 uses
  sceVu0ScaleVector / AddVector, which do touch w: left as it is.)
- `zdb::CRenderMap::CRenderMap` 0x22bc30 (node_shadow.cpp): 0x22bd9c calls the light map's vtable
  slot +0x38, `CLight::UpdateBBox(false)` (`__vt__Q23zdb10CRenderMap`; +0x34 is SetActive). The port
  called `SetActive(false)`: every render map's node was switched off and its box never set. The
  same misread slot in `CRenderMap::Update` 0x22b5e8 (same file, not on this list) is fixed too. The
  player's shadow on the snow is the same picture before and after (runs rn0 / rn1b, test camera on
  the player), with one render map, one update and one frame restore per frame, range 40.
- `CVideo::Brightness` 0x307790 (zvid_video.cpp, was an empty stub): written from the ELF. It keeps
  `CVideo::m_brightness` (new static, .sdata 0x4753e0 = 128; declared in zvid.h, defined in
  zvideo_holding.cpp beside m_maxFrameRate) = 127 x the distance from 0.5 (128 at 0.5, or when it
  rounds to 0 on the dark side) and writes the brightness packet's ALPHA_1 data (+0x20: 0x46 darker,
  0x49 brighter) and sprite alpha (+0x40, << 24) through the uncached mirror. ELF quirk kept: no code
  sends `brightnesscode` (its only references are these stores), so the options brightness tuner
  changes nothing on screen, as in the ELF.
- `CPnt4D::CPnt4D()` 0x236740 (zmath.h): the ELF constructor is empty (`move v0,a0`); the port's zeroed
  x, y, z, w. Now empty, as `CPnt3D::CPnt3D()` 0x1a9160 became at HEAD 85b06ea2 (list A). Port code
  that read a fresh CPnt4D before writing it now sees what the ELF would; the final runs show no
  effect (shadow, particles, HUD, cameras as before).

## Kept differences
- `BriefingRoom(MediusChannelListResponse *)` 0x327190 and `BriefingRoomDB::Parse` 0x328490 (online
  only): the port zeroes m_channel where the ELF leaves it as allocated (NULL channel; the inline
  default constructor) and copies ROOMNAME with strncpy where the ELF copies 64 bytes past the end of
  the name. Both were already noted in the bodies.
- `zdb::CWorld::CWorld` 0x230030: every ELF store matches; the CGrid is new'd (deleted by ~CWorld)
  where the ELF holds it by value at +0x670 (recorded port layout).
- `CFileIO::Release` 0x305c50: the ELF writes -1 to the word m_file and m_cd share; the port splits
  that union (64-bit m_file on GCC) and writes m_file = -1, m_cd = NULL. Every reader tests IsOpen
  (m_file) first.
- Inside FIXED row 70: the cross-product axis in the CRenderMap constructor is zeroed (the ELF leaves
  two of its words as stack garbage).

## Not located
- `CPnt4D::Sub` 0x236720: the port has no such member; its two ELF callers (Destruction_Instance::Tick,
  clip3DLine) are written with the subtraction inline. Not written (for the later pass).

## Notes for later passes
- `CMatrix::Transform(CPnt3D *, int)` 0x1eb350 is a do-while in the ELF (no zero-count test); every
  port caller passes a constant >= 1, so the port's `for` behaves the same.
- `CCamera` carries port-only members m_yaw / m_pitch (not in the DWARF record, only zeroed by the
  constructor, never read).
- `CBatchRelocator::EndBatchReloc` / `CGSTexBuffer::Load`: the resize fill qword at 0x43a850 (called
  unproven in the bodies) is zero, which is what the port uses.

## Runs (final tree HEAD 85b06ea2 + these files; focus kept in every run; screenshots untracked,
## build/port/screenshots/53-audit/)
- rn2 (`port/test-hooks/render` + the state hook, `pad_fire.txt`, `-DSOCOM_HOOK_MISSIONS=1
  -DSOCOM_HOOK_PLAY_AT=999999 -DRN_CAM=1200`, 240 s): intro movie skipped with CROSS, briefing cameras
  with X (m8bs, m8tut1), mission 65.7 -> 240.7 s (175 s), 30 shots, no STOP, frame time 0.0167 s
  throughout, heap in use 23,066,404..23,067,668 B from 125 s to the end; the shadow on the snow
  under the test camera as before.
- cam2 (state hook, `-DSOCOM_HOOK_CAMS_PLAY`): m8bs plays in full (66.7 -> 87.7 s), then m8tut1
  (87.7 -> 100.7 s); no STOP.
- znet2 (`port/test-hooks/znet`): dlgNetConnect opens, the connect fails offline and the menu comes
  back to dlgMenu (in use 18,156,820 B, as at the first dlgMenu), then dlgNetConfig opens; no STOP.
- def2 (`default.sh`: no hooks, no fake pad): boots to dlgMenu at 16.4 s, argc 1.
- rt2 (`port/test-hooks/state`, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8`, 770 s): eight missions and eight returns, no STOP; in use at the briefing 18,666,708 B at return 1, then 18,666,804 B at returns 2-8: flat, the same figures as at HEAD 86052025 (no destructor on this list frees more or less).
- Earlier, at HEAD 86052025 + these files (CPnt4D() still zeroing): the same render, camera, znet and
  default runs, all clean; rn0 (HEAD) / rn1b (this tree) show the same shadow under the test camera
  (the render-map fix changes no picture); round trip in use 18,666,708 B at return 1, then
  18,666,804 B at returns 2-8, as at HEAD.

## Result table

| # | Address | Function | Port definition | Verdict | Evidence |
|---|---|---|---|---|---|
| 1 | 0x1e44a0 | zdb::CNode::IsCell | src/gamez/zNode/znode.h (inline) | MATCH | returns 0 |
| 2 | 0x1e7780 | zdb::CCamera::CCamera | src/gamez/zCamera/zcam_main.cpp | MATCH | every field the ELF stores matches in value and order: m_fullfrustum_points 0, Zmin/Zmax from zVid, fog bits (enabled 1, directional 0, alt 1, flags 0), fog near/far/mid from the not-yet-set m_far_plane (ELF quirk kept), fog colours, fog/landmark tops and bottoms and the fog_alt vectors (twice), regions 0/0/1, screen aspect/centre 2048/offset 0, m_screen {0x6c0, 0x720, 0x940, 0x8e0} and the integer /640 /448 constants, guard band, clip volume 320/448/Zmin/Zmax, near 1 x m_scale, far 150 x m_scale, hfov 0x3f1c61aa and its sin/cos/tan/cot/scrZ, vfov 448*hfov/640 and its sin/cos/tan/cot, m_vu 0x70003e60, fovMask 0x3f3f. The port also zeroes m_yaw / m_pitch: port-only members (not in the DWARF record, never read) |
| 3 | 0x1e8850 | CSealCtrl::IsPlayer | src/gamez/zSeal/zseal.h (inline) | MATCH | returns true |
| 4 | 0x1ea700 | zdb::CCamera::GetDynamicsControl | src/gamez/zCamera/zcam.h (inline) | MATCH | lbu of static m_dynamics_controlled |
| 5 | 0x1eb350 | CMatrix::Transform(CPnt3D*,int) | src/gamez/zMath/zmath.h (inline) | MATCH | row0*x+row1*y+row2*z+row3 in place; ELF loop is a do-while (no count==0 test), every port caller passes a constant >= 1 |
| 6 | 0x1ec560 | CPnt3D::CPnt3D(const CPnt3D&) | src/gamez/zMath/zmath.h (inline) | MATCH | copies x,y,z |
| 7 | 0x1ec580 | GetNearestIntersectCamPoint | src/gamez/zCamera/camera.cpp | MATCH | NULL without hits; sets camera_tether_intersects_something; skips m_cameratype 1 within 5 of from; nearest (<=, later wins a tie) squared distance to m_Tail |
| 8 | 0x1ed050 | CPacket::GetPacketMsg | src/gamez/zConsole/con_main.cpp | MATCH | returns NULL |
| 9 | 0x1ed4f0 | CPacketMsg::GetPacketMsg | src/gamez/zConsole/con_packet.cpp | MATCH | returns this |
| 10 | 0x1ed930 | CPacket::OnRecvPacket | src/gamez/zConsole/con_packet.cpp | MATCH | argc != 0: new CPacketMsg (16), calloc(len+1), memcpy, _counter = id, m_args calloc + string walk; else new CPacket (12) the same |
| 11 | 0x216ff0 | zdb::CCell::Copy | src/gamez/zGrid/zgrid.h (inline) | MATCH | returns NULL |
| 12 | 0x217000 | zdb::CCell::IsCell | src/gamez/zGrid/zgrid.h (inline) | MATCH | returns 1 |
| 13 | 0x218de0 | CMatrix::Multiply | src/gamez/zMath/zmath.h (inline) | MATCH | tail call sceVu0MulMatrix(out, other, this) |
| 14 | 0x21d540 | CPnt4D::CPnt4D(f,f,f,f) | src/gamez/zMath/zmath.h (inline) | MATCH | stores x,y,z,w |
| 15 | 0x21d560 | CPnt3D::CPnt3D(f,f,f) | src/gamez/zMath/zmath.h (inline) | MATCH | stores x,y,z |
| 16 | 0x21e490 | zdb::CDIPoly::CDIPoly | src/gamez/zIntersect/int_bbox.cpp | MATCH | CDI base ctor, then the CDIPoly vtable |
| 17 | 0x221980 | CBits::Resize | src/gamez/zMath/zmath_main.cpp | MATCH | malloc first time / realloc only to grow (signed word compare), clears bits m_bits..bits-1 (unrolled x8 in the ELF), stores m_bits; ELF returns 1, port void (noted in the body) |
| 18 | 0x222e90 | CPnt3D::Add | src/gamez/zMath/zmath_pnt3d.cpp | MATCH | out = this + other |
| 19 | 0x222f30 | CPnt4D::Rotate_AxisX | src/gamez/zMath/zmath_pnt4d.cpp | MATCH | y' = y*c - z*s, z' = y*s + z*c |
| 20 | 0x223050 | init_trig_table | src/gamez/zMath/zmath_trig.cpp | FIXED | step constant 0.02454369f encodes 0x3cc90fd9; the ELF loads 0x3cc90fdb (lui/ori 0x223080); sin/cos/exp order and double exp(i*10/256) match |
| 21-31 | 0x321260-0x321300 | CSealStats getters (11) | src/Apps/FTS/state/st_exit.cpp | MATCH | each a lw of the DWARF member at +0x18,+0x14,+0x3c,+0x38,+0x44,+0x40,+0x2c,+0x34,+0x30,+0x0,+0x10 |
| 32 | 0x321310 | CExitMenu::GetReaderFileName | src/Apps/FTS/state/st_exit.cpp | MATCH | returns "dlgExitState.rdr" |
| 33 | 0x321320 | CGameMenu::MyTick | src/gamez/zGame/zgame.h (inline) | MATCH | empty |
| 34 | 0x321330 | CGameMenu::PrepControls | src/gamez/zGame/zgame.h (inline) | MATCH | empty |
| 35 | 0x323890 | ClanInvitationItem::ClanInvitationItem | src/gamez/zNetwork/zNetMedius.cpp (inline in the class) | MATCH | AccountID(+0x1c)->+0, InviteMessage 200 ->+0x28, AccountName 32 ->+4, ResponseStatus(+0x108)->+0x24 |
| 36 | 0x325070 | BriefingRoomDB::FindRoom | src/gamez/zNetwork/zNetMedius.cpp | MATCH | NULL name -> NULL; first room whose LobbyName (+0x48) strcmp-equals |
| 37 | 0x325a70 | RoomGame::IsPersistent | src/gamez/zNetwork/zNetMedius.cpp | MATCH | false |
| 38 | 0x325a80 | BriefingRoom::FindGame | src/gamez/zNetwork/zNetMedius.cpp | MATCH | NULL name -> NULL; first game whose GameName (+0x20) matches |
| 39 | 0x326160 | RoomGame::UpdateInfo | src/gamez/zNetwork/zNetMedius.cpp | MATCH | struct copy of the record (member-wise in the ELF), NULL -> MediusWorldID (+0x1c) = -1 |
| 40 | 0x327190 | BriefingRoom::BriefingRoom(MediusChannelListResponse*) | src/gamez/zNetwork/zNetMedius.cpp | KEPT | vectors, LIMIT 16, +0x94..+0xa0 = 0, channel copied; the port's extra memset of m_channel on a NULL channel (ELF leaves it as allocated) is a defined value for never-read storage; the only caller passes the response |
| 41 | 0x327af0 | BriefingRoom::~BriefingRoom | src/gamez/zNetwork/zNetMedius.cpp | MATCH | plain delete of each game (RoomGame has a trivial dtor), size 0, _free(m_password, line 146), NULL, the two vector dtors, the games vector |
| 42 | 0x328490 | BriefingRoomDB::Parse | src/gamez/zNetwork/zNetMedius.cpp | KEPT | rooms list cleared without delete, room per ROOM, ROOMNAME/LIMIT/GAMELIST, inline RoomGame/PersistentGame ctors, room pushed with or without a name: match. Port deviations kept (already noted in the body): strncpy instead of the ELF's 64-byte memcpy past the name's end; inline BriefingRoom() zeroes m_channel (ELF leaves it) |
| 43 | 0x328830 | PersistentGame::Parse | src/gamez/zNetwork/zNetMedius.cpp | MATCH | "%s$~%s", MediusWorldID -1, MAXPLAYERS -> +0x98, MISSION_SEQUENCE bytes without a limit, returns 1 |
| 44 | 0x32acb0 | InvitationItem::InvitationItem | src/gamez/zNetwork/zNetMedius.cpp (inline in the class) | MATCH | ids +0x1c/+0x20, Message 200, LeaderAccountID +0xf0, name 32, ResponseStatus +0x24 |
| 45 | 0x32e4b0 | BriefingRoom::BaseSrc | src/gamez/zNetwork/zNetMedius.cpp | MATCH | this |
| 46 | 0x32e4c0 | BriefingRoomClone::BriefingRoomClone | src/gamez/zNetwork/zNetMedius.cpp | MATCH | src->m_clone = this, BaseSrc, index, MediusWorldID -1, "%s %d" (base name, CloneIndex()+1), limit, a PersistentGameClone per persistent base game ("%s$~%d", -1, MaxPlayers, 12-byte sequence); the base BriefingRoom() zeroing m_channel is the row-42 deviation |
| 47 | 0x32e800 | BriefingRoom::CloneIndex | src/gamez/zNetwork/zNetMedius.cpp | MATCH | 0 |
| 48 | 0x32ecb0 | BriefingRoom::deltrans | src/gamez/zNetwork/zNetMedius.cpp | MATCH | !game->IsPersistent() |
| 49 | 0x32fe40 | PersistentGameClone::IsAClone | src/gamez/zNetwork/zNetMedius.cpp | MATCH | true |
| 50 | 0x32fe50 | PersistentGame::IsPersistent | src/gamez/zNetwork/zNetMedius.cpp | MATCH | true |
| 51 | 0x32fe60 | BriefingRoomClone::CloneIndex | src/gamez/zNetwork/zNetMedius.cpp | MATCH | m_cloneIndex (+0xa8) |
| 52 | 0x32fe70 | BriefingRoomClone::IsAClone | src/gamez/zNetwork/zNetMedius.cpp | MATCH | m_src (+0xa4) |
| 53 | 0x32fe80 | BriefingRoomClone::BaseSrc | src/gamez/zNetwork/zNetMedius.cpp | MATCH | tail call m_src->BaseSrc() |
| 54 | 0x32fea0 | BriefingRoom::IsAClone | src/gamez/zNetwork/zNetMedius.cpp | MATCH | NULL |
| 55 | 0x32feb0 | PersistentGame::IsAClone | src/gamez/zNetwork/zNetMedius.cpp | MATCH | false |
| 56 | 0x3fe900 | CSMInterface::Start | src/gamez/zNetwork/zNetCnf.cpp | MATCH | StartState, not done, old list freed (not NULLed: ELF), sceInetGetInterfaceList 256, memalign 64 x524, per entry memset/type/flags 8/vendor 2/product 3 and installed on a vendor+product match, IdleState, true |
| 57 | 0x3fefb0 | CSMSaveCombo::Cleanup | src/gamez/zNetwork/zNetCnf.cpp | MATCH | _free(m_name, 795), NULL |
| 58 | 0x3feff0 | CSMSaveIFC::Cleanup | src/gamez/zNetwork/zNetCnf.cpp | MATCH | _free(m_name, 640), NULL |
| 59 | 0x3ff030 | CCnfStateMachine::Cleanup | src/gamez/zNetwork/zNetCnf.cpp | MATCH | empty |
| 60 | 0x3ff040 | CSMInterface::Cleanup | src/gamez/zNetwork/zNetCnf.cpp | MATCH | _free(m_list, 1230), NULL |
| 61 | 0x3ff080 | CSMOpen::Cleanup | src/gamez/zNetwork/zNetCnf.cpp | MATCH | _free ifc list (259), NULL, dev list (261), NULL |
| 62 | 0x3ff0f0 | CHNetCnf::LibNETSetup | src/gamez/zNetwork/zNetCnf.cpp | MATCH | msifrpc, libnetb "-decode" (8), sceSifMInitRpc(0), libnet_init(2048, 8192, 32), reg_handler, reboot callback; false on each failure |
| 63 | 0x3ff1b0 | CHNetCnf::IOPRebootHandler | src/gamez/zNetwork/zNetCnf.cpp | MATCH | unreg_handler, libnet_term, sceSifMExitRpc on every phase; false |
| 64 | 0x3ffc60 | CSMSaveDev::AllocMem | src/gamez/zNetwork/zNetCnf.cpp | MATCH | ENTER alloc 4928; TICK result < 0 -> error + Idle, else GetAddr |
| 65 | 0x3ffd30 | CSMSaveDev::GetAddr | src/gamez/zNetwork/zNetCnf.cpp | MATCH | ENTER GetAddr; TICK error/Idle or m_iopAddr = result.addr (+0xc), SendData |
| 66 | 0x3ffe10 | CSMSaveDev::SendData | src/gamez/zNetwork/zNetCnf.cpp | MATCH | ENTER SendIOP(m_data, m_iopAddr, 4928) -> m_dmaId; TICK DmaCheck 0 -> AddEntry |
| 67 | 0x3ffea0 | CSMSaveDev::AddEntry | src/gamez/zNetwork/zNetCnf.cpp | MATCH | ENTER "%s/%s" vendor/product, AddEntry(file, 2); TICK error if < 0, Idle; EXIT FreeWorkarea |
| 68 | 0x3fff80 | CSMAddDev::GetHWAddr | src/gamez/zNetwork/zNetCnf.cpp | MATCH | ENTER only: memset, dev_type 3/1/2 from flags 0x10/0x80, vendor/product, per-type phy/dialing/idle/chat, MAC (control 13, 16) unless a modem, Idle |
| 69 | 0x229cf0 | CBBox::Normalize | src/gamez/zNode/node_model.cpp (file-local NormalizeBox) | MATCH | per axis: min > max (not <=) swaps the two; the port's CBBox has no member, the one ELF caller (UpdateBBoxFromDI) uses the helper |
| 70 | 0x22bc30 | zdb::CRenderMap::CRenderMap | src/gamez/zNode/node_shadow.cpp | FIXED | 0x22bd9c calls the light map's vtable +0x38, CLight::UpdateBBox(false) (vt __vt__Q23zdb10CRenderMap: +0x34 is SetActive); the port called SetActive(false), which switched every render map's node off and left its box unset. Same misread fixed in CRenderMap::Update 0x22b5e8 (not on this list, same file). Everything else matches (matrices, type/node/packet/texture, shadow bit only for type 0 then forced, render_map_<n>, ranges 1/30/900, light-map registration, screen/UV scale, up vector, REF tag, the GS packet words, VU tags, shadow GIF tag). KEPT inside the row: the cross-product axis is zeroed (the ELF leaves its other two words as stack garbage) |
| 71 | 0x22c1a0 | zdb::CNode::GetClosestNode | src/gamez/zNode/node_util.cpp | MATCH | two UnitMatrix, BuildMTW NULL -> best; abs(dy) in double < maxHeight unless -1; xz distSq < best (unless -1) and < maxDistSq; xz dot > 0 then normalised dot > DEFAULT_CLOSESTNODE_DOT; 5th arg unread |
| 72 | 0x230030 | zdb::CWorld::CWorld | src/gamez/zNode/node_world.cpp | KEPT | every ELF store matches (camera/diInt NULL, wind reset, cell data NULL, overlap 2, SetName, scale 10 / 0.1, m_world, type 6, DiIntersect(256), delay 0, the normalised sun, light flags, colours, ambient, night 0, NVG and starlight lens colours, the four ShadowX_<i> textures via LoadGS(addr | 0x80000000, 256, 256, 2) from zVid.textureBaseAddr, shadow vector (1,-1,1) normalised, soil type 0 / NULL). Recorded port deviation: the CGrid is new'd (the ELF holds it by value at +0x670); ~CWorld deletes it |
| 73 | 0x231d00 | zdb::CLensFlare::~CLensFlare | src/gamez/zNode/node_lensflare.h (inline) | MATCH | vector at +0xcc destroyed, then ~CNode (port's {} body does the same through member/base destruction) |
| 74 | 0x231d80 | zdb::CVisData::~CVisData | src/gamez/zVisual/zvis.h (inline) | MATCH | empty body (deleting variant only) |
| 75 | 0x234680 | Particle::bufferPtrCompare | src/gamez/zParticle/zparticle_buf.cpp | MATCH | bits of a->+0x1c - b->+0x1c as int (quirk kept) |
| 76 | 0x2366f0 | CPnt4D::CPnt4D(const CPnt4D&) | src/gamez/zMath/zmath.h (inline) | MATCH | copies x,y,z,w |
| 77 | 0x236720 | CPnt4D::Sub | - | NOT LOCATED | the port declares no CPnt4D::Sub; its two ELF callers (Destruction_Instance::Tick, clip3DLine) are written with the subtraction inline |
| 78 | 0x236740 | CPnt4D::CPnt4D() | src/gamez/zMath/zmath.h (inline) | FIXED | the ELF constructor is empty (move v0,a0); the port's zeroed x,y,z,w. Now empty, as CPnt3D() 0x1a9160 at HEAD 85b06ea2 (list A) |
| 79 | 0x237380 | Particle::Instance::Tick | src/gamez/zParticle/zparticle.h (inline) | FIXED | the ELF moves m_pos, m_vel and the wind relaxation with VU0 vmulx.xyz/vadd.xyz/vsub.xyz (0x2374c8, 0x2374f0, 0x23763c-0x237654): w is left alone; the port also integrated and relaxed m_pos.w / m_vel.w. Frozen test, age/expiry, rotated spin stop, streak copy, exp series constants, node spin/scale all match |
| 80 | 0x23be10 | CRdrArchive::~CRdrArchive | src/gamez/zReader/zrdr_archive.cpp | MATCH | vtable, ~CZAR, delete in the deleting variant |
| 81 | 0x23ca30 | zrdr_countarray | src/gamez/zReader/zrdr_file.cpp | MATCH | 0 unless an array; count slot + recursion over elements 1..n-1 (one level unrolled in the ELF) |
| 82 | 0x241850 | zRndrInit | src/gamez/zRender/zrndr_init.cpp | MATCH | ZDB flags 0, 16 KB of VU1 data memory = 0xcd, FlushCache, data then code DMA to VIF1 with sync, two alpha packets (ALPHA_1 0x88 in the first; GIF tag NLOOP/EOP/NREG 1/A+D), CVisual::Init |
| 83 | 0x3a75a0 | _zrdr::Get | src/gamez/zReader/zrdr.h (inline) | MATCH | element offset+1 when offset < count-1 (unsigned), else NULL |
| 84 | 0x244220 | CBBox8::Build | src/gamez/zRender/zrndr_pipe.cpp | MATCH | the eight corners in the ELF's order |
| 85 | 0x3f7ce0 | CSaveManager::CSaveManager | src/gamez/zSave/zsav_manager.cpp | MATCH | list ctor, m_pFile, buffer size 0, buffer NULL (the rest unset in both) |
| 86 | 0x1dd720 | zBoneInit | src/gamez/zBone/bone_init.cpp | MATCH | sets is_init once, returns true |
| 87 | 0x1de0b0 | CZSIObject::CZSIObject | src/gamez/zSoftImage/si_object.cpp | MATCH | data pointers NULL, m_constPos / m_constRot bits cleared (m_inUse left), name NULL, numSiObject++ |
| 88 | 0x1de110 | CZSIScript::SetTimeScale | src/gamez/zAnim/zanim.h (inline) | MATCH | m_tScale (+0xc) = scale |
| 89 | 0x2f0350 | CSndGroup::~CSndGroup | src/gamez/zSound/zsnd_csndgroup.cpp | MATCH | the weights (+0x50) and sounds (+0x44) vectors, then ~CSnd; the sounds are not deleted |
| 90 | 0x2f1220 | CSndJukebox::PlayRandom | src/gamez/zSound/zsnd_jukebox.cpp | MATCH | rand * 2^-31 (0x30000000) against the running sum; weight x 0.1, NormalizeWeights, playlist bound test continues the loop; Play, release the current instance, sequence, mode |
| 91 | 0x2f5240 | CIOPManager::delflag | src/gamez/zSystem/zsys_init.cpp | MATCH | returns reg.m_flag_for_deletion (+0xc) |
| 92 | 0x2f9b70 | zdb::CBatchRelocator::EndBatchReloc | src/gamez/zTexture/ztexture_holding.cpp | MATCH | both lists empty -> return; Hookup; new chain (n*11+3 qwords, the fill qword at 0x43a850 is zero, MakeChain returns the buffer start) or RelocateAll; UpdateTextureSelects; GIF DMA sync/send/sync |
| 93 | 0x2f9ca0 | zdb::CBatchRelocator::StartBatchReloc | src/gamez/zTexture/ztexture_holding.cpp | MATCH | both lists cleared, chain NULL |
| 94 | 0x2f9cf0 | zdb::CTextureRelocMgr::PreGetSprPacket | src/gamez/zTexture/ztex.h (inline) | MATCH | empty |
| 95 | 0x305c50 | CFileIO::Release | src/gamez/zUtil/util_sonyio.cpp | KEPT | the ELF writes -1 to the one word m_file and m_cd share; the port splits that union (s64 m_file on GCC) and pairs every write: m_file = -1, m_cd = NULL. Readers test IsOpen (m_file) first |
| 96 | 0x306860 | CMemCardIO::GetMode | src/gamez/zUtil/zutil.h (inline) | MATCH | returns m_mode (+0x14) |
| 97 | 0x307790 | CVideo::Brightness | src/gamez/zVideo/zvid_video.cpp | FIXED | was an empty stub; written from the ELF: m_brightness (new static, .sdata 0x4753e0 = 128) = 127 x abs(v - 0.5) (128 at 0.5, or when 0 darker), ALPHA_1 data 0x46 / 0x49 at brightnesscode+0x20, sprite alpha << 24 at +0x40, uncached. ELF quirk: nothing sends brightnesscode, so no picture change |
| 98 | 0x30d470 | CVisBase::CVisBase | src/gamez/zVisual/vis_main.cpp | MATCH | zmalloc(size) unless external or 0, else NULL; count 0, size, ++m_instance_count, m_active = external |
| 99 | 0x30ddc0 | CVisBase::~CVisBase | src/gamez/zVisual/vis_main.cpp | MATCH | not external: free, NULL; --m_instance_count |
| 100 | 0x3134d0 | zdb::UVCompare | src/gamez/zVisual/vis_decal.cpp | MATCH | the u and v ranges of the three points against [0, 1], with the ELF's < / <= choices |
| 101 | 0x3142f0 | zdb::CTextureFX::InitScrollTexture | src/gamez/zVisual/vis_texfx.cpp | MATCH | du, dv, visual, node m_vid (+0xae) or 0, type 1 / 2 |
