# boot-player notes (2026-11-06)

Scratch for the player-creation stage of the functional port (after boot-mission). Untracked.

## Tools (this folder)
- From boot-mission: `dx.ps1 <start> [end|+len]` (annotated ELF disassembly), `status.py`, `xref.py`,
  `sym.py`, `dw.py`, `rdr.py`, `a2l.sh <build> addr..`, `boot.ps1 -Name x -Seconds N -Build <dir>`,
  `fake.sh <dir> "<script>"` (PowerShell: `wsl.exe -d Ubuntu -- bash /mnt/c/.../fake.sh ...`; Git Bash
  mangles the path).
- `lay.py <Class> <header>` + `laycheck.sh <name>` (or `layall.sh a b c`): DWARF vs port layout table.
  Compile errors print each member's port offset/size; rows marked `*` shift, `#` size differs,
  `!` member missing in port. GCC vptr placement, std::string (24 vs 4 bytes), CQuat/CMatrix
  16-byte alignment and 1-byte MW enums make pure shifts unavoidable; look for `!` and `#`.
- `multi_replace.py <src> <edits>`: `@@ <mangled>` sections replace skeleton fence regions (keeps
  fences, BOM, CRLF). Edits used are in `edits/`. `splice.py` replaces a file tail.
- `grepasm.sh <regex>` (full ELF disassembly cached in WSL /tmp), `pdis.sh <build> a b` (port ELF),
  `errctx.sh <build> <pattern>` (lib.log context), `incpath.py <hdr> <suffix>` (include chains).
- Mission script: `fake.sh boot-player-fake "60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS"`.
  World m8 is loaded ~45 s after boot.

## Load map after this session
CMission::Init -> CCharacterType::Open (characters reader: body_items -> BodyId, AngleUnits,
ai_settings, gear list, `characters` name [: parent] {..} -> ctor + Parse) [written].
PreOpen -> CVehicleRdr::Open/Load [rewritten from asm] -> CreateCustomCharTypes (UiCharTypeN
temporary copies) [written].
Open: materials [written] ... CNodeAction::Open .. LoadVehicles [written] -> LoadVehicle [written]
-> ftsCreateSeal [written] -> CZSealBody::Create [written] -> PreCreateSeal [written: Acquire,
CreateInstance, CreateLODs written; SetDynamic, AddTextureAssetCharacter still void stubs] ->
CZSealBody ctor [rewritten from asm] -> **stops: `SEAL: player has no seal_body or skel_root node;
exit(-1)` (~45 s)**. The model seal_A_arc has children player?/skel_root/body, but the instance made
by `zdb::CNode::_Copy` 0x227e40 (1884 B, provisional port body) has 2 children both named "NA":
_Copy(NULL) makes a bare `new CNode()` without InitNodeParams/name, and its child loop is wrong.
Next: rewrite _Copy from the asm (callees: InitNodeParams, SetModel, CMesh::Clone [stub],
CSubMesh(CMesh*), CVisualVector/CDIVector::Exists, SetParentHasVisuals, CMatrix::ToQuat [1-line
provisional], CreateInstance for INSTANCE children). (Before this session's fix CreateInstance also
inserted the instance into the model's m_child; now it goes to CModel::m_list as in the ELF.)
Then in the ctor: BodySetup/NewBodyPart/AddBodyPart/FindPart [written] ->
**AnimSetup 0x27eac0 (bool, stub -> STOP expected)**: needs CZSealBody::_player template or
ReadMotionRdr (motion.rdr: the animation system), BodyAddAnim/AddAnim, CopyValues, BindAnimSet,
m_blends RTStack, CSealAnim AnimPush/AnimPop, Snap.
After the ctor: CEntity::CreateEntity [written], PostCreateSeal 0x289d60 (1480 B, stub).

## Written (functions)
See the report. Layout fixes: CEntity (+m_mapLoc, m_mapLocValid, m_SOPList, m_max_target_range_sq),
CBody (+m_blend_pool, m_blends), CBlendOverlay, CSealCtrl (DWARF order, flag word, +m_vissens,
m_vismap, m_curMPBOMBpickup_ID), CSealCtrlAi (flag word + m_aiParams only), CZSealBody (DWARF
names: m_zoom_range, pre_thr_lr, m_projectileintersecthandle, m_projectiledi*, m_groundNormal,
m_numDeathAnimsPlayed; m_aimnodes order), CNodeEx (no CNode base), IntersectStruct (+m_poly),
CDIVector (+m_bReturnBackFaceIntersections), CAiTimer (static infinite), CCharacterType (::AI_PARAMS,
vector type list, gear/weap lists, MultiplayerMessages), CCharacterGear (+m_model_name),
CCharacterWeap fields, LODVec of LOD, CRefList of CNode*, tag_VIS_PARAMS (+m_vtype.. m_centroid,
Ghidra layout), SEAL_CONTROL_TYPE values, EQUIP_AMMO/CHARACTER_SOUND 1 byte, ZOOMSTATE_UNKNOWN=-1.

## Known gaps on the path (not faked)
- CAiMaps::ReadMapSet not written -> no AI maps -> GetLocation false -> characters start at the
  origin. CAiMap::GetLocation is a STOP stub (not reached without maps).
- CZWeapon::GetWeaponId returns NONE (provisional) -> character default weapons are dropped.
- spawners (CSpawners 0x4c5610) not declared: recycle vehicles skipped.
- CSealCtrl ClearGoal/ClearLook are void stubs (their callees SetGoalDir/SetDefaultLookParams).
- CSealCtrlAi ctor is a stub and the class has almost no members: AI characters (gopt.loadAi is 1
  by default) will need it right after the player.
- SetDynamic, AddTextureAssetCharacter, SetDescendantDI/Visuals, SetUseParentBBoxTree, AddDIPolys,
  SetArmor, SetLookDir, RotateHead, PartInSpace, UpdateAimParams, AddWeapon, AddItem, WepWaitOn,
  SetBlendPool, CZKit ctor/Init/SetBody, CSealStats::Reset, CAiPath ctor: void stubs.
- CVisual::Read: +28 (lod field) and the detail record fixup are not written.
