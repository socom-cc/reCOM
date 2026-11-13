# boot-render2 notes (2026-11-06, socom-port-render2)

Scratch for the mesh LOD fix and the draw-side work after it. Nothing here is tracked.

## Tools
- `t/` copies of boot-render's tools (dx.sh annotated ELF disassembly, sym.py, xref.py (jal only),
  dw.py DWARF layouts, status.py). `pdis.sh <build> <regex>` disassembles a port build function,
  `a2l.sh <build> addr` symbolizes a port address. `fake.sh <build> <pad>` fake-pad build.
- `hook.sh` + `hook_vehicles.c` (TEST HOOK, build boot-render2-hook): wraps CMission::LoadVehicles to
  create no seals. Result: testLoad gets player NULL and returns false, so the game restarts.
  It does not reach a game frame; keep only for reference.
- `edits/*.py` are the edit scripts used (use forward-slash paths in heredocs).
- Builds: boot-render2 (default), boot-render2-fake (pad 60:CROSS,...,185:CROSS -> m8 mission).

## Root cause of the NULL mesh LOD chain
CNode::GetMesh (node_model.cpp) tested the legacy `m_has_lods` flag, which nothing set, so it
always returned NULL. hookupVisuals(archive, model) 0x30a040 therefore never took hookupMesh, and
LOD 0 of every mesh model stayed {NULL, NULL}. ELF 0x229510: first visual with vtype 1.
After the fix, mission start passes Clone and AddLOD (boots b1-b3).

## ELF facts
- GetSubMesh 0x229490 returns the first visual when vtype 2 (__dynamic_cast); hookupVisuals ignores it.
- MW vector layout here: +4 size, +8 data (m_lods +112: size +116, data +120).
- Particle buffer: buffer[5000] x 32 B {CPnt4D colour*128, Instance*, f32, CTexture*, f32 depth};
  bufferPtr[5000] directly after it, so bufferPtr[-1] is element 4999's depth (draw-loop sentinel).
  Source +0x38 m_drawType: 0 Draw, 1 DrawRotated, 2 DrawXZ, 3 DrawStreaked (DWARF Particle::Source).
  Instance: +4 Source*, +8 CTexHandle*, +64 Props* (constructor 0x236f20).
- zqsort<T> 0x2360a0: iterative quicksort (median of 3, runs <= 9 left), then an insertion sort.
- bufferPtrCompare returns the float bits of a.depth - b.depth as int.
- CPipe::m_DelayedNodes is vector<tag_DelayedNode> (112 B); SaveDelayedNode grows by 8.
- CLightMap: CLight::m_maxRange +0xc4 is the reach; +0x160 bit 0 m_isShadow; +0x174 m_instance.
  CWorld::m_lightMaps +0x55c (CLightMapVector of CLightMap*); Exists returns bool.
- BuildNodeLocalLightList skips lights whose region mask shares a bit with the node's.
- CGrid::SetCellBoundary returns the first cell; GetNextCell returns NULL for a missing cell mid-range.
- CCamera::CanSeeRegion returns true when m_do_region_test is off (the port returned false).
- CAppCamera::AttachTo is virtual (testLoad jalr through appCamera); Ghidra has no xref.
- CBatchRelocator::TakeDrawPacket 0x2fcb40 is a tail call of zSysFifoKick (restored).

## Next blockers seen
- Plain fake-pad build: STOP seal_env.cpp:565 (other worker's chain), then AttachTo (now written).
- Load screen TLB miss in CImageSpec::CreateDisplayObj (UI, pre-existing, not ours).
- VuShadowMap / VuLightMap / VuBatchProgram_Decals unreachable: CWorld::AddLightMap and the
  CRenderMap constructor are stubs (light-map list stays empty); CDecal::AddDecal is a stub.
- GetIntersect (CDIPoly/CDIBBox/CBBox) unreachable: CGrid::GetIntersect/NodeGetIntersect stubs.
