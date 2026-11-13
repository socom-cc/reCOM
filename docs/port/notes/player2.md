# boot-player2 notes (2026-11-06)

Scratch for player creation after boot-player (CNode::_Copy, animation system). Untracked.

## Tools (this folder)
Copied from boot-player (paths fixed): dx.ps1, dis.sh/disx.py, sym.py, xref.py, dw.py, status.py,
lay.py/laycheck.sh/layall.sh, multi_replace.py, a2l.sh, pdis.sh, grepasm.sh, fake.sh.
- Boots: ONLY via `build/port/tools/pcsx2-boot.ps1 -Elf <scratch>\socom_port.elf -Log .. -Seconds N
  -Shots ".." -ShotPrefix ..` after copying the ELF out of \\wsl$ (no own Start-Process, no focus).
- `hook.sh <build> <pad>`: fake-pad build plus `hook_clone.c` (TEST HOOK, scratch only): wraps
  zdb::CMesh::Clone (returns the source mesh) and CMesh::AddLOD (no-op) via CMAKE_EXE_LINKER_FLAGS
  (the toolchain -L/-T flags must be repeated there). Build dir boot-player2-hook.
- `fpgen.py` (DefineFPAnims 133 entries -> fp_entries.txt), `initgen.py` (InitializeAnimNames 157
  pairs -> init_pairs.txt), `animnames.py` (animTypeNames 0x455a50), `genanim.py` (edits/anim_gen.txt).
- Bash heredocs with quotes/backslashes break the Bash tool: write edit files with the Write tool.
- motion.zar can be read from the disc into the session scratchpad with boot-menu/iso.py (never
  into the repo); zar.py walks keys (their "size" field is 1; data is in place at the offset).

## Load path now (fake pad, m8)
CMission::Init: zBoneInit/Open/LoadAll [LoadAll written: every motion script read IN PLACE
(CreateAndReadIt -> ReadLIP -> CZSIObject::Read(Uc*,Ui,PCc)); the stream reader CZSIScript::Read is
also written but cannot parse motion.zar (packed format)] -> AnimSet::Load [written: names maps,
animset.rdr sets, InitializeAnimNames, DefineFPAnims, death/flinch lists, includes].
LoadVehicles -> ... PreCreateSeal -> CreateInstance -> CNode::_Copy [written] -> CMesh::Clone
(render worker) -> CZSealBody ctor -> SetBlendPool [written] -> AnimSetup [written] ->
ReadMotionRdr [written] -> per anim BodyAddAnim/Setup/Update/callbacks/flags [written] ->
BindAnimSet [written] -> SetMaxMotion, ClearBlendOverlay, ClearStack [written] ->
**STOP CZSealBody::PushBlend 0x27c090 (2904 B, non-void stub, seal_body.cpp:282)** (hook build).
Plain build (no hook): faults first inside the render worker's CMesh::Clone (port pc 0x1730f8,
after InitMatrices; CopyMeshLOD memcpy from NULL: the seal model mesh's LOD chain is NULL).
Next after PushBlend: CBody::PushBlend 0x1e25e0 (964), CZBodyAnimBlend::SetBlendAnims 0x1dfd00,
CActiveAnimPool::GetActiveAnim, then in ReadMotionRdr CSealAnim::AnimPush 0x26deb0 (1092) /
AnimPop 0x26ddc0 (236); ctor tail; CEntity::CreateEntity; PostCreateSeal 0x289d60 (1480).

## ELF facts found
- AnimType is 2 bytes, animTypeUndefined = -1 (port enum was off by one).
- AnimSet::list/m_animIDs/m_basetypes/m_included types; death/damage lists are vector<AnimType>[6][3].
- CAnimsByFP holds a malloc'd 300-group table indexed by the rifle AnimType.
- motion.zar key data: +0 ver, +4 loop time, +8 frames, +0xc objects, +0x18 name table off, +0x1c
  key data off, +0x20 CZSIObject[16 B] in place; names 4-aligned, padded with '-'.
- CScriptArchive in the ELF: std::list at +0, CZAR at +0xc (port keeps CZAR as base + member list).
- RTArray/RTList/RTStack bodies from the ACTIVE_ANIM/CZBodyAnimBlend instantiations.
