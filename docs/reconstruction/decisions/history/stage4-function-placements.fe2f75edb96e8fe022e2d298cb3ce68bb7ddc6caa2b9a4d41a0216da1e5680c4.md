## Apps/FTS/game/beachball.cpp
- CBeachBall::Uninit()

## zai/ai_main.cpp
- ai::get_clock_direction(const CPnt3D *)
- ai::quadratic(float, float, float, float &, float &)
- ai::elevate(CPnt3D &, float, float)
- ai::AddNoise(CPnt3D *, const PNT2D &)
- ai::AddNoise(const CPnt3D *, CPnt3D *, const PNT2D &)
- ai::MakeNoise(CPnt3D *, const PNT2D &)
- ai::is_moving(const CPnt3D *, float)
- CAi::GetToRightXZ(const CPnt3D *, CPnt3D *, bool)
- CAi::AlignToPoint(const CMatrix *, const CPnt3D *, CMatrix *, float)
- CAi::Extrapolate(const CPnt3D *, const CPnt3D *, float, CPnt3D *)
- CAi::LeadTargetG(const CPnt3D *, const CPnt3D *, float, const CPnt3D *, const CPnt3D *, CPnt3D *)

## zbody/zbody_main.cpp
- CBody::PartInSpace(CZBodyPart *, const CPnt3D *, CPnt3D *, CQuat *) const
Note: its own zBody file, linked in the zBody slot between zArchive and zBone (0x1dc520); body.cpp links later, after the softimage files.

## zanim/zanim_sequence.cpp
- PushAnim(CActiveAnimList *, ACTIVE_ANIM *, float)
- RenormAnims(CActiveAnimList *, float)
- CSequence::Weight()
- CSequence::LinearWeight()
- CSequence::Tick(float)
- CSequence::Clear()
- CSequence::Start(float, float, float)
- PointAlongLine(const CPnt3D &, const CPnt3D &, float, CPnt3D &)
- LineIntersectPlane(float, const CPnt3D &, const CPnt3D &, const CPnt3D &)
- PlaneConstant(const CPnt3D &, const CPnt3D &)
- ClipToBox(const CPnt3D &, const CPnt3D &, CPnt3D &, float, float, float, float)
- GetFractionalRotations(const CPnt3D *, float *, float *)
- quadW(float)
- QFromRot(CQuat *, const CPnt3D *)

## zentity/ent_entity.cpp
Note: CEntity tick/position code; its own zEntity file between ent_target.cpp and ent_control.cpp (0x1f1e20-0x1f2000) - ent_main.cpp ends at 0x1ef880 with ent_target.cpp after it.
- CEntity::SetController(CEntityCtrl *)
- CEntity::UpdateNextPosition()
- CEntity::ComputeNextPosition(float)
- CEntity::PostTick(float)
- CEntity::PrePostTick(float)
- CEntity::PostPreTick(float)
- CEntity::Tick(float)
- CEntity::PreTick(float)

## zentity/ent_control.cpp
- CEntityCtrl::Tick(float)
- CEntityCtrl::PreTick(float)
- CEntityCtrl::~CEntityCtrl()
- CEntityCtrl::CEntityCtrl(int)

## zentity/zentity.h
Note: inline virtuals defined in CEntityCtrl's class (vtable slots 5-8, MW binding 13; copies emitted in ent_main.cpp and ent_entity.cpp); CSealCtrl overrides PostMortemPreTick and OnDeath, inherits the other two.
- CEntityCtrl::PostMortemPreTick(float)
- CEntityCtrl::GetRemoteControl()
- CEntityCtrl::SetThrottle(unsigned int, float)

## zreader/zrdr_main.cpp
- zrdr_finduint(const _zrdr *, const char *, unsigned int *, int)
- zrdr_findRfloat(const _zrdr *, const char *, Rfloat *)
- zrdr_findint(const _zrdr *, const char *, int *, int)
- zrdr_findreal(const _zrdr *, const char *, float *, int)
- zrdr_findstring(const _zrdr *, const char *)
- zrdr_nexttag(const _zrdr *, const char *, _zrdr *)
- _zrdr_nexttag(const _zrdr *, const char *, int, _zrdr *)
- zrdr_findtag(const _zrdr *, const char *)
- zrdr_findtag_startidx(const _zrdr *, const char *, int)
- zrdr_flat_nexttag(const _zrdr *, const char *, _zrdr *)
- zrdr_flat_findtag_startidx(const _zrdr *, const char *, int)
- _zrdr::~_zrdr()
- _zrdr::DeleteChildren()
- _zrdr::_zrdr(_zrdr *, CSTable *)

## ztexture/ztex_main.cpp
- zdb::CTexture::Init()

## ztexture/ztex_dyn.cpp
- zdb::CDynTexList::~CDynTexList()

## zseal/seal_body.cpp
- 0x26e700  CZSealBody::FindValidReticleGotoLoc(int *)
- 0x26e990  CZSealBody::AdrenalineIncr(float)
- 0x26e9f0  CZSealBody::Adrenaline()
- 0x27d510  CObjAnims::GetObjAnim(int)
- 0x27d560  CObjAnims::~CObjAnims()
- 0x27d620  CZSealBody::ConfigureAuxPartAnim(CZBodyAnim *)
- 0x27d9b0  CZSealBody::SetPartAsGear(CZBodyPart *, CCharacterGear *)

## zsystem/zsys_bench.cpp
- CBench::Reset()

## zseal/seal_ctrl.cpp
- CSealCtrl::MPBomb_TimerAvailable(bool)
- CSealCtrl::InitMPBomb()
- CSealCtrl::TickMPBomb(float)
- CSealCtrl::PerturbAimVector(CPnt3D *)
- CSealCtrl::SetViewRange(float)
- CSealCtrl::UpdateAiVisMap()
- CSealCtrl::PostMortemPreTick(float)
- CSealCtrl::GetSpeedFromThrottle(float, int)
- CSealCtrl::GetThrottleFromSpeed(float, int)
- CSealCtrl::TickRumbler(float)
- CSealCtrl::StopRumbler()

## zvideo/zvid_video.cpp
- CVideo::Brightness(float)
- CVideo::Clear(unsigned char, unsigned char, unsigned char, unsigned char)

## zvideo/zvid_main.cpp
- zVid_ZTestOnWriteSet(bool)
- zVid_ZTestOn()
- zVid_ZTestOff()

## ztwod/ztwod_main.cpp
Note: C2D's shared top-level functions (0x300bf0-0x300d10), between c2dline.cpp and ztwod_poly.cpp.
- C2D::Enable(bool)
- C2D::IsOn() const
- C2D::On()
- C2D::Off()
- C2D::Draw(zdb::CCamera *)
- C2D::~C2D()

## ztwod/ztwod_bitmap.cpp
- C2DBitmap::TickFade()
- C2DBitmap::Reset()
- C2DBitmap::MakePacket(zdb::CCamera *, zdb::CTextureRelocMgr *, const CMatrix *)
- C2DBitmap::SetPos(int, int, int, int)
- C2DBitmap::SetPos(int, int)
- C2DBitmap::Load(float, float, float, float, zdb::CTexHandle *)
- C2DBitmap::Load(float, float, zdb::CTexHandle *)
- C2DBitmap::SetUV(float, float, float, float)
- C2DBitmap::GetTrans()
- C2DBitmap::SetTrans(float)
- C2DBitmap::SetColor(float, float, float)
- C2DBitmap::Draw(const CMatrix &, zdb::CTextureRelocMgr *)
- C2DBitmap::Draw(zdb::CCamera *)
- C2DBitmap::C2DBitmap()

## zanim/zanim_cmd_tick.cpp
Note: Begin and Tick handlers are written as pairs per command in this file (binary: CameraBegin/CameraTick, WaitBegin/WaitTick, ...); zAnimCallAnimBegin precedes zAnimCallAnimTick. The provisional zanim_cmd_begin.cpp was an empty file (d4e3582) and the ELF names no such file.
- zAnimCallAnimBegin(_zanim_cmd_hdr *)
- zAnimQuadAlignTick(_zanim_cmd_hdr *, float *)
- zAnimGoToEndIf(_zanim_cmd_hdr *, float *)
- zAnimDebugTick(_zanim_cmd_hdr *, float *)
- zAnimFireWeaponTick(_zanim_cmd_hdr *, float *)
- zAnimStopSequenceTick(_zanim_cmd_hdr *, float *)
- zAnimCallSequenceTick(_zanim_cmd_hdr *, float *)
- zAnimInvalidateAnimTick(_zanim_cmd_hdr *, float *)
- zAnimResumeAnimTick(_zanim_cmd_hdr *, float *)
- zAnimPauseAnimTick(_zanim_cmd_hdr *, float *)
- zAnimStopAnimTick(_zanim_cmd_hdr *, float *)
- zAnimCallAnimTick(_zanim_cmd_hdr *, float *)
- zAnimFailTick(_zanim_cmd_hdr *, float *)
- zAnimRandomWeightTick(_zanim_cmd_hdr *, float *)
- zAnimLODTestTick(_zanim_cmd_hdr *, float *)
- zAnimHealthTestTick(_zanim_cmd_hdr *, float *)
- zAnimRangeTestTick(_zanim_cmd_hdr *, float *)
- zAnimNodeRenderedTick(_zanim_cmd_hdr *, float *)
- zAnimNodeActiveTick(_zanim_cmd_hdr *, float *)
- zAnimBreakTick(_zanim_cmd_hdr *, float *)
- zAnimEndWhileTick(_zanim_cmd_hdr *, float *)
- zAnimWhileTick(_zanim_cmd_hdr *, float *)
- zAnimEndIfTick(_zanim_cmd_hdr *, float *)
- zAnimIfTick(_zanim_cmd_hdr *, float *)

## zweapon/zwep_ammolist.cpp
- CZAmmoList::GetAmmoId(const char *)
- CZAmmoList::GetAmmo(EQUIP_AMMO)
- CZAmmoList::GetAmmo(int)
- CZAmmoList::GetAmmo(const char *)
- CZAmmoList::AddAmmo(CZAmmo *)
- CZAmmoList::~CZAmmoList()
- CZAmmoList::CZAmmoList()

## zmath/zmath.h
Note: inline in their classes (MW binding 13); each kept copy sits in a file that used it.
- 0x201650  CPnt3D::Cross(const CPnt3D *, CPnt3D *, bool) const
- CMatrix::operator const float (&)[4][4]() const
- CPnt3D::CPnt3D()
- CPnt3D::operator=(const CPnt3D &)

## ztwod/ztwod.h
Note: inline in C2DLine's class (its copy sits between c2dbitmap_poly.cpp and ztwod_font.cpp).
- C2DLine::~C2DLine()

## zreader/zrdr_local.cpp
Note: own zReader file after zrdr_edit.cpp (0x241530-0x2416d0); zrdr_relocate is static (LOCAL), called only by zrdr_pack; zrdr_pack is called from zUI (CUIVarManager::CollectGarbage), so its prototype goes in a header zUI includes.
- zrdr_pack(_zrdr *, void *, unsigned int)
- zrdr_relocate(_zrdr *, _zrdr *)

## zfts/fts_network.cpp
Note: FTS network-game init and remote-respawn alignment (0x201290-0x2016f0), linked just before fts_network_dme.cpp; findAlign is called by CZSealBody::RemoteRespawn. The CPnt3D::Cross copy in this block is inline from zmath.h.
- ftsNetworkGameUninit()
- ftsNetworkGameInit()
- ftsNetworkSealInit()
- ftsNetworkPlayerInit()
- findAlign(CZSealBody *, CPnt3D *, CMatrix *, int)

## zfts/fts_network_dme.cpp
Note: the game's DME start-up/connection wrappers (0x201800-0x201fd0), linked just before fts_remote.cpp; called from CMenuState::Init and UIInitNetwork. Not zNetDme.cpp, whose block is at 0x321340.
- DMEDisconnectFromGameServer()
- DMEJoinGameServer()
- DMEConnectToGameServer()
- DMERegister()
- DMEinit()

## zsystem/zsys_memory.cpp
Note: end of zsys_memory.cpp (0x2f48a0-0x2f4920, just after its block 0x2f4490-0x2f4830).
- _delete(void *, const char *, int)
- _free(void *, const char *, int)
- zsys_FullAllocAndFree()

## zseal/seal_cfg.cpp
Note: end of seal_cfg.cpp (0x281070, just after its block ending 0x281030; seal_command.cpp starts at 0x281080).
- CZSealBody::GetDynamics()

## zseal/seal_env.cpp
Note: end of seal_env.cpp (0x2a4700-0x2a4bf0); seal_ex.cpp's CSealEx::OnWeaponHit follows at 0x2a4d20.
- CZSealBody::UpdateAiMapLoc(bool &)
- ftmask_create(_zrdr *)

## zseal/seal_ik.cpp
Note: foot IK during turns (0x2a4d30-0x2a4dd0), between seal_ex.cpp (0x2a4d20) and seal_kit.cpp (0x2a4f70); TurnSetup calls FootInSpace, StandTurning/InStateCrouch use them.
- CZSealBody::TurnSetup(int)
- CZSealBody::FootInSpace(CZBodyAnim *, CPnt3D *, CPnt3D *, float, float, bool)

## znode/node_world.cpp
Note: start of node_world.cpp (0x22c3c0-0x22c420, just before its block; node_util.cpp precedes them).
- SetMaterial(zdb::CNode *, int)
- SetDIBBox(zdb::CNode *, const CBBox *, bool)

## ztwod/ztwod_init.cpp
Note: the 2D system's start-up, called once by CGame::StartEngine (0x303c10-0x303c60, after the C2DBitmap code, before zUtil/util_bufio.cpp).
- C2D::Open()
- C2D::Init()

## rt/rtlist.h
Note: RTList<T> template (DWARF has RTList beside RTArray and RTStack, which live in src/rt/); these RTList<ACTIVE_ANIM> member copies were instantiated in zanim_sequence.cpp.
- RTList<ACTIVE_ANIM>::Begin()
- RTList<ACTIVE_ANIM>::Next()
- RTList<ACTIVE_ANIM>::Add(ACTIVE_ANIM *)

## zai/ai_cell.cpp
- CAiCell::CAiCell()

## zai/ai_map.cpp
Note: end of ai_map.cpp (0x188e90, just before ai_mapio.cpp's read_cells at 0x188f60); called only by CAiMap::Read.
- CAiMap::read_scanlines(CFileIO &)

## zgraph/graph_edge.cpp
- CGEdge::~CGEdge()
- CGEdge::Delete(CGEdge *)
- CGEdge::CGEdge(CGNode *, CGNode *, float)

## zgraph/graph_route.cpp
- CGRoute::PostProcess()
- CGRoute::Clear()
- CGRoute::Append(CGNode *)
- CGRoute::~CGRoute()
- CGRoute::CGRoute()

## znode/node_projectedmap.cpp
- zdb::CProjectedMap_Object::~CProjectedMap_Object()
- zdb::CProjectedMap_Object::CProjectedMap_Object()

## zfts/fts_objectivecam.cpp
Note: start of fts_objectivecam.cpp (0x20a750-0x20a830, just before its CMissionObjectiveCam block at 0x20a8d0); fts_missioncam.cpp comes after it.
- CMissionObjectiveCamList::Reset()
- CMissionObjectiveCamList::ClearValves()

## zai/ai_search.cpp
Note: map flood-fill searches for look/cover locations (0x1a9590-0x1a9e40), the last zAI code, after ai_log.cpp and before zAnim/zanim_cmd_parse.cpp.
- CAiMap::FindLookLoc(const CAiMapLoc &, const CPnt3D *, CAiMapLoc &, CAiMap::DIR &, int)
- CAiMap::FindCoverLoc(const CAiMapLoc &, const CPnt3D *, CAiMapLoc &, CAiMap::DIR &, int)
- _find_look(MAP_FLOODFILL_STRUCT &, void *)
- _find_cover(MAP_FLOODFILL_STRUCT &, void *)

## znode/node_vector.cpp
Note: one unbroken run of container classes (0x224260-0x224700) between node_io.cpp and node_main.cpp, in the order node vectors, CNodeUniverse, CLightMapVector; pairs with node_vector.h.
- zdb::CDIVector::Exists(const zdb::CDI *)
- zdb::CVisualVector::Exists(const zdb::CVisual *)
- zdb::CModelVector::GetModel(const char *)
- zdb::CNodeVector::Remove(const zdb::CNode *)
- zdb::CNodeVector::Exists(const zdb::CNode *)
- zdb::CNodeVector::GetNode(const char *)
- zdb::CLightMapVector::Exists(const zdb::CLightMap *)
- zdb::CNodeUniverse::GetElement(int)
- zdb::CNodeUniverse::GetIndex(zdb::CNode *)
- zdb::CNodeUniverse::RemoveNode(zdb::CNode *)
- zdb::CNodeUniverse::AddNode(zdb::CNode *)
