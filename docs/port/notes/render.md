# boot-render notes (2026-11-06, socom-port-render, second pass)

Scratch for the EE side of world drawing. Nothing here is tracked. Tools in `t/` (copies of
boot-mission's with the extra `../`): `t/dx.sh <addr> [end|+len]` annotated disassembly,
`t/status.py`, `t/xref.py`, `t/sym.py`, `t/dw.py`. Edit scripts in `edits/` (`rep.py` replaces a
skeleton marker's body up to the next marker).

## For the player worker (CNode::_Copy) - written from the asm
- `zdb::CMesh* zdb::CMesh::Clone()` (0x30f330): `new CMesh`, memberwise `*clone = *this`,
  clone->m_ref_count = 0, this->m_ref_count++, clone->m_clone_src = this, clone->InitMatrices()
  (virtual), relocated copy of LOD 0's chain -> clone->m_lods.back() and clone->m_buffers[0].
- `zdb::CSubMesh::CSubMesh(zdb::CMesh* mesh)` (0x30ef40): vtype 2, m_render_mode 3,
  m_matrix_id 0xabcd, m_mesh = mesh. CSubMesh::Read fetches "matrix_id" then CVisual::Read.
- The instance count is `CVisual::m_ref_count` (+24, ELF). `m_instance_cnt` and `m_has_lods`
  are legacy port members kept only so node_main.cpp/node_model.cpp compile: nothing sets them.
  node_main.cpp's `visual->m_instance_cnt++` should become `m_ref_count++` (Release decrements
  m_ref_count).
- CSubMesh's ELF base is CVisual (port keeps CMesh as base while _Copy static_casts CMesh* to
  CSubMesh*; the new _Copy casts from CVisual*, so the base can become CVisual later).

## Layouts (zvis.h)
- CVisual (Ghidra 104 B): tag_VIS_PARAMS +0 (flag bits named from Ghidra; bit 1 kept as m_field1),
  m_ref_count +24, m_render_mode +28 (3; -2 vparams bit 10; CPipe sets -3), vptr +32 (MW),
  m_decals +36 (per instance), m_buffers +48 (chain header per instance), m_alloc_blocks +60,
  m_dyn_tex_list +72, m_detail_params +96, m_detail_cnt +100.
- CMesh (140 B): m_clone_src +104, m_mesh_decals +108, m_lods +112 (CMeshLOD 12 B {range_sqd,
  vertex, chain}), m_mtx_count +124, m_matrices +128.
- tag_ObjectHeader (32 B, packet qwords 1-2 = VU hdr[0..1]): light qwc, batch qwc, multipass
  qwc, flags (bit 0 setup, bit 1 GS packet), local light qwc, 3 unused words.
- tag_DETAIL_PARAMS (16 B): range_sqd, tex_cnt, resolved, chain_ofs, chain_qwc, tex* (12-byte
  tag_DETAIL_TEX entries after the records; Read links them).
- Chain header qword: u16[0] tag qwords, u8[2] relocated flag, u32[2] CVisBase*, u16[6]
  subface offset, u16[7] subface qwc. Tag types (u8[2]): 1/2/4/7 buffer-relative, 3 batch,
  5 texture VU REF, 6 texture name, 8 batch copied out (SetBuffer); mesh copies: 7/10-12
  vertex-relative, 9 matrix index (SetMeshBuffer).

## Packet contract as written (VuUpdate 0x30a900)
- Every scratchpad packet: qword 0 DMA CNT (VuExecuteState0 fills: CNT n, STCYCL 1,1, UNPACK
  V4-32 FLG of the header qwords), qwords 1-2 tag_ObjectHeader, 3.. payload, then MSCALF 0
  (in the CNT data, or after the saved texture selects m_savedTS + CNT 0/MSCALF).
- Object packet: VuObjectSetup hdr[2..18] (+ local lights) -> state 0 with matrix setup.
- Batch-program packet: VuBatchProgram entries at hdr[2..] (state 0 without setup copies them
  to VU 340), [multipass], then the instance chain copied in with CSPR::Copy (toSPR DMA),
  kicked in pieces (CSPR::Kick -> zSysFifoKick). Batches end in VIF MSCNT.
- Camera: CCamera::Update fills tag_FrameSetup at SPR 0x70003e60: CNT 24, FLUSH STCYCL UNPACK
  23 @4: VU 4-7 mtxWorldToScreen (DWARF name; the .vsm label VU1_WORLD_CLIP is a misnomer:
  MatrixSetup multiplies it by ModelToWorld and vuXForm divides by w -> screen coords),
  8-11 mtxWorldToClip, 12-15 mtxClipToScreen, 16-19 light normals, 20-23 light colours,
  24-25 fogA/B, 26 shadow GIF tag. RenderWorld kicks the 25 qwords each frame.
- Texture loads: FIFO_Insert puts VIF NOP+I-bit in the MFIFO; InterruptFromVIF1 (CPipe::Init
  installs it, INTC 5) starts the buffer's GIF chain (PATH3) and FBRST.STC restarts VIF1.

## Result (test hook)
- `-DSOCOM_PORT_VU1_TEST=ON` (port/CMakeLists.txt, port/test/vu1_test.cpp; build dir
  boot-render-vu1 via `t/vu1build.sh`): wraps zSysFifoEnd; from menu frame 121 it kicks a
  hand-built frame setup (identity VU 4-15) and draws a CVisual whose one-instance chain is
  CNT 18 (UNPACK FLG of a batch) + CNT 0/MSCNT through CVisual::Render. Screenshot
  `vu1test1-32.png`: a Gouraud triangle (red/green/blue corners at 200,110 / 440,110 /
  320,330) over the main menu. Program used: vuDecompress0, vuXForm0, vuGatherFixKick, vuSleep.
- Batch format confirmed by it: [1] GIF tag (PACKED NREG 3 ST/RGBAQ/XYZ2, PRE+PRIM; the VU
  rewrites word 0 to NLOOP 3 + EOP), [2] {tri list offset, -, vertex count, tri count},
  [3] decompress offset (added to itof4 positions), [4..] 3 qwords per vertex (int position x16,
  ST/normal, int RGBA), decompress works in pairs (pad one vertex), triangle entries
  {3*i0, 3*i1, 3*i2, flags bit 0} + plane qword.

## Not written / blockers for the real loop
- Particle::Draw/DrawPrep/DrawRange/DrawFlush are stubs; DrawPrep/DrawRange are non-void, so the
  first frame with a transparent visual STOPs in CPipe::CAlpha::Render (unowned particle code).
- VuShadowMap 0x30b860 / VuLightMap 0x30ba40 / VuBatchProgram_Decals 0x30c9c0 and the decal
  branches of VuUpdate: need CLightMap / CDecal / CMeshDecal records (unrecovered); unreachable
  while CPipe::BuildLightMapList is a stub and CDecal::AddDecal is a stub.
- CTexture::CopyTextureSelect (detail maps) stub; BuildNodeLocalLightList empty;
  SaveDelayedNode / RenderDelayedNodes stubs; CNode::GetSubMesh (void stub, node_model.cpp).
- Unknown until real data: how the chain's texture VU REF (type 5, one qword short before a
  batch) and the batch REFs combine; first real world frame will show it.
