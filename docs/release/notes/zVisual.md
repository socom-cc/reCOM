# Stage 2: gamez/zVisual (2026-11-26)

The one list of `gamez/zVisual` (list a): the owner files vis_main.cpp (release
0x3203d0-0x325b60), vis_mesh.cpp (0x325dd0-0x327bb0), vis_bands.cpp (0x327c00-0x32aa00),
vis_decal.cpp (0x32aa90-0x32c7a0) and vis_texfx.cpp (0x32c8c0-0x32d300). It holds 25 uncertain
rows (21 new, 3 removed, 1 unsure; none flagged `identical-copy`, two new rows flagged `copy`),
15 sampled deviating rows out of 26, and 142 exact rows that were not checked one by one.
Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`); checked by
`socom-release-check-visual`, who did not write the tool, at HEAD 66d3acea. The check sheet
(`compare.py --sheet gamez/zVisual --list a`) was the starting point. Both images were
disassembled with the release tools; callers were found by scanning both images for `jal`/`j`,
`lui`/`addiu` pairs and data words, and the vtables with the tool's RTTI reader. As a guard on
the committed pairs, every paired row in 0x3203d0-0x32d300 (168 rows) had its callers, address
loaders, vtable slots, data words and ordered callee sequence compared with the prototype's
through the map, and so had the ordered callee sequence of each of the 115 paired callers
(inside or outside the range) of a function in the range. Ghidra was not needed.

What settled rows, in the order it was used: the call site in a paired caller (CVisual::AttachDecal,
CNode::ApplyDecal, CWorld::RemoveDecals); the callers of each new function, which form one
closed tree under CNode::ApplyDecal; the prototype's own lack of any code that creates a mesh
decal (no RTArray<zdb::CMeshDecal>::GetNext, no CMeshDecalPool::Get); the slot between paired
neighbours; the vtables.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x30d100 `Write__Q23zdb7CVisualFRQ23zar4CZAR` | removed | confirmed | slot 5 is gone from the CVisual and C2DVisual tables (and from CSubMesh and CMesh, whose Writes called it); no release caller |
| - | 0x30ee30 `Write__Q23zdb8CSubMeshFRQ23zar4CZAR` | removed | confirmed | CSubMesh table lost slot 5; the new functions in its slot (0x325ea0 0.11) are the mesh decal path, not a writer: no ZAR Insert call, no "vtype"/"matrix_id" |
| - | 0x30f0f0 `Write__Q23zdb5CMeshFRQ23zar4CZAR` | removed | confirmed | CMesh table lost slot 5 (InitMatrices moves 7 → 6); no release caller |
| 0x325ea0 | - | new | confirmed | takes a CMeshDecal from CMeshDecal::m_permPool or m_tempPool (by the sign of the life argument), links it onto the mesh's decal list (+0x6c, next at +4), calls 0x32aad0 on it, then FlushCache. The mesh counterpart of CVisual::AttachDecal. Caller 0x325fb0 (twice) |
| 0x325fb0 | - | new | confirmed | walks the mesh's vertex data (CVisData::Clear, the new CVisData walk 0x328290/0x327ee0), tests each triangle (CPnt3D::Sub, sceVu0OuterProduct, Normalize, UVCompare, fabsf ×3), collects them in the decal builder (0x32ba40 … 0x32b910) and attaches each batch (0x325ea0). The mesh counterpart of CVisual::ApplyDecal. Caller 0x3264b0 |
| 0x3264b0 | - | new | confirmed | builds the model and inverse matrices (sceVu0UnitMatrix ×2, MulMatrix, CopyMatrix, Vu0MatrixInverseWithUniformScale) and calls 0x325fb0: the mesh counterpart of CVisual::ApplyDecalRender. Caller: CNode::ApplyDecal. For a visual of type 2 (a CSubMesh), which the prototype skipped, it now calls this with the sub-mesh's m_mesh (+108) and m_matrix_id (+104). Other visuals still go to ApplyDecalRender |
| 0x327d00 | - | new | confirmed | CVisData packet walk: searches the entries of type 10 packets for the one whose halfword +6 equals the argument, else Clear. Caller 0x327df0 |
| 0x327df0 | - | new | confirmed | CVisData walk over type 9/10 packets (stores the type 9 word +0x18 at +0x54, loads the batch at a type 10), calls 0x327d00. Caller 0x32b4c0 |
| 0x327eb0 | - | new | confirmed | resumes a walk just after the position another CVisData saved at +0x58/+0x5c (packet, packet index; packet count from +4). Caller 0x32b4c0 |
| 0x327ee0 | - | new | confirmed | steps one index like NextVertex, sets a bool when it crosses a batch, and searches with 0x3280c0 instead of SearchVertex. Caller 0x325fb0 |
| 0x327fc0 | - | new | confirmed | inner search of the new walk (packet types 1, 3, 5, 11), like the inner part of SearchVertex. Caller 0x3280c0 |
| 0x3280c0 | - | new | confirmed | outer search of the new walk: type 9 packets whose +0x18 word equals +0x54, type 10 batches with mode 2; saves the position at +0x58/+0x5c; calls 0x327fc0. Callers 0x327ee0, 0x328290 |
| 0x328290 | - | new | confirmed | the same as SelectVertex (Clear, first chain of the visual, packet count, first packet) but stores its third argument at +0x54 and searches with 0x3280c0. That argument is the sub-mesh's m_matrix_id, passed down from CNode::ApplyDecal through 0x3264b0 and 0x325fb0. Caller 0x325fb0 |
| 0x32aad0 | - | new | confirmed | see "New and removed": the CMeshDecal chain builder. Caller 0x325ea0 |
| 0x32b4c0 | - | new | confirmed | opens a new group in the decal builder (count +0x2e4c, group CPnt3D set from `zero__6CPnt3D`, -1 tag), pushes indices into the group's two vectors, then walks the batch with 0x327eb0/0x327df0. Caller 0x325fb0 |
| 0x32b7d0 | - | new, copy | confirmed | `Get__Q23zdb14CMeshDecalPoolFb`: masked bytes of Get__Q23zdb10CDecalPoolFb, but it calls 0x32c600 (not RTArray<CDecal>::GetNext) and its caller 0x325ea0 passes the CMeshDecal pools; it sits between PutTempDecal and Init of the CMeshDecal group, as Get sits before Init in the CDecal group |
| 0x32b8c0 | - | new | confirmed | pushes one index onto the builder's vector at +0. Caller 0x325fb0 |
| 0x32b910 | - | new | confirmed | destroys the builder (clears its counts, `__destroy_arr` of 296 elements of 40 bytes with dtor 0x32b990, vector dtor, delete) and clears the global 0x48e544. Caller 0x325fb0 |
| 0x32b990 | - | new | confirmed | destructor of the 40-byte builder element (two vector_pod<Ui> at +16, +28). Passed to `__destroy_arr`/`__construct_array` by 0x32b910 and 0x32ba40 |
| 0x32ba20 | - | new | confirmed | resets the builder (group count +0x2e4c and vector size). Caller 0x325fb0 |
| 0x32ba40 | - | new | confirmed | creates the builder: `new` 11856 bytes, vector ctor, `__construct_array` of 296 × 40 with ctor 0x32bab0, reserve 296, stores it in the global 0x48e544. Caller 0x325fb0 |
| 0x32bab0 | - | new | confirmed | constructor of the 40-byte builder element (CPnt3D from `zero__6CPnt3D`, s16 0 and -1, two empty vectors). Passed to `__construct_array` by 0x32ba40 |
| 0x32bb60 | 0x312e80 `AddDecal__Q23zdb6CDecalFfPPQ23zdb10AddonPointUiPQ23zdb10CTexHandlePQ23zdb7CVisualUi` | unsure, call-deviating | corrected to deviating (pair confirmed) | its only caller CVisual::AttachDecal calls it at the same place as the prototype did; the same GIF/VIF tag words and the same CDecal offsets (+0x20 … +0x108) are written. The low similarity is register renaming: the release passes one more argument (a CPnt3D, stored at +0x110 … +0x118). Tick__Q23zdb6CDecal moved with it |
| 0x32bf00 | - | new | confirmed | a CDecalPool method: RecycleTick's loop (GetOldestUsed, PutBack, CVisual::RemoveDecal while the count at +0xc is not zero), then DereferenceDecals on every visual still in the array. CWorld::RemoveDecals calls it on CDecal::m_tempPool and m_permPool |
| 0x32c600 | - | new, copy | confirmed | `GetNext__27RTArray<Q23zdb10CMeshDecal>Fb`: raw bytes of RTArray<CDecal>::GetNext (0x32c390), but its one caller is CMeshDecalPool::Get (0x32b7d0), and it sits between PutBack and the destructor of RTArray<CMeshDecal>, as GetNext sits after PutBack in RTArray<CDecal> |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x3204e0 | 0x3093c0 `AttachDecal__Q23zdb7CVisual...` | yes | same caller CVisual::ApplyDecal; the two CDecal pools, CDecalPool::Get, AddDecal, FlushCache |
| 0x321030 | 0x30a040 `hookupVisuals__FPQ23zar4CZARPQ23zdb6CModel` | yes | same caller LoadWorld, same thirteen callees in order; vis_main.cpp line 116 → 115 |
| 0x3229f0 | 0x30ba40 `VuLightMap__Q23zdb7CVisualFP8_word128` | yes | same caller VuUpdate; CopyTextureSelect, SaveTextureSelect, m_lightMapList, m_WorldToModel (the CMatrix element calls are inlined now) |
| 0x3233e0 | 0x30c350 `VuObjectSetup__Q23zdb7CVisual...` | yes | same caller VuUpdate; sceVu0CopyMatrix and the same seventeen data references (CVisual statics, NoAltFogBottomV) |
| 0x323850 | 0x30c7c0 `GetChainData__Q23zdb7CVisualFv` | yes | same caller VuUpdate; the cdeque accessor and the same DMA chain statics |
| 0x3241a0 | 0x30d130 `Read__Q23zdb7CVisualFRQ23zar4CZAR` | yes | slot 4 of the CVisual and C2DVisual tables; same callers (the CSubMesh and CMesh Reads); "vparams", "detail_*" |
| 0x324560 | 0x30d4f0 `SetBuffer__Q23zdb7CVisual...` | yes | same callers Particle::CreateVisuals and hookupVisuals; same callees; "null_xmas.bmp" |
| 0x324ad0 | 0x30da60 `GetTextureSelectBlock__Q23zdb7CVisual...` | yes | same caller CTexture::SetupSpecialTextures; _calloc, vis_main.cpp line 519 → 517 |
| 0x3268f0 | 0x30f150 `__dt__Q23zdb5CMeshFv` | yes | slot 0 of the CMesh table; stores the CMesh vtable; same callees |
| 0x326ad0 | 0x30f330 `Clone__Q23zdb5CMeshFv` | yes | same caller CNode::_Copy; same callee sequence; CMesh and CVisual RTTI |
| 0x3281c0 | 0x310560 `NextVertex__Q23zdb8CVisDataFUi` | yes | the same four callers (CRipple::Tick, Particle::CreateVisuals, CVisual::ApplyDecal, ScrollTexture); calls SearchVertex |
| 0x328470 | 0x3107b0 `SearchVertex__Q23zdb8CVisDataFv` | yes | same callers NextVertex and SelectVertex; calls Clear |
| 0x32b690 | 0x312e20 `FreeMem__Q23zdb10CMeshDecalFv` | yes | same callers CMesh::DereferenceDecals and the CMesh destructor; _free, vis_decal.cpp line 518 → 534 |
| 0x32c430 | 0x3137d0 `__ct__22RTArray<Q23zdb6CDecal>FUibb` | yes | same caller CDecalPool::Init; same three callees |
| 0x32c8c0 | 0x313bc0 `ScrollTexture__Q23zdb10CTextureFXFf` | yes | same caller CTextureFX::Tick; SelectVertex, NextVertex ×3, LimitUVs; zVid, vdata |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner |
|---|---|---|---|---|---|
| 0x32bb60 | 0x312e80 | AddDecal__Q23zdb6CDecal: only caller CVisual::AttachDecal at the same call site; same GIF/VIF tag words and CDecal offsets; one argument more | socom-release-check-visual | 2026-11-26 | |

No other row changed class or counterpart.

## New and removed

The release adds a whole decal path for meshes. In the prototype, VuUpdate already draws
`CMesh::m_mesh_decals` and the pools exist, but no code creates a CMeshDecal (no
RTArray<zdb::CMeshDecal>::GetNext, no CMeshDecalPool::Get), so the list stays empty. In the
release, CNode::ApplyDecal no longer skips CSubMesh visuals: it sends them down a new branch
with their mesh and matrix id. The new functions form a
closed tree under it: every caller of each one is another of them or CNode::ApplyDecal. The
CMesh three mirror CVisual's ApplyDecalRender → ApplyDecal → AttachDecal chain. Names are
guesses unless the basis says otherwise.

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x3264b0 | builds the model/inverse matrices for a mesh decal and runs the mesh search | guess: `ApplyDecalRender__Q23zdb5CMesh...` (the mirror of CVisual::ApplyDecalRender; called where CNode::ApplyDecal calls that for a visual) |
| 0x325fb0 | finds the mesh triangles under the decal and builds decal batches from them | guess: `ApplyDecal__Q23zdb5CMesh...` (the mirror of CVisual::ApplyDecal) |
| 0x325ea0 | takes a CMeshDecal from a pool, builds it, links it onto the mesh | guess: `AttachDecal__Q23zdb5CMesh...` (the mirror of CVisual::AttachDecal: same pool choice by the life sign, FlushCache) |
| 0x32aad0 | builds one mesh decal's VIF chain. It stores the life (+0), the mesh (+8) and the texture-select qword of the texture handle (+0x20). It counts the groups and indices the builder holds, then `_malloc`s the chain (vis_decal.cpp:809, at +0x10, qword count at +0x30, chain at +0x34), and writes STCYCL/UNPACK/MSCNT codes and the vertices of each group. FreeMem and CMeshDecalPool::RecycleTick free the same +0x10 and clear +0x30/+0x34 | guess: `AddDecal__Q23zdb10CMeshDecal...` (the mirror of CDecal::AddDecal; it fills the members CMeshDecal's inline constructor clears) |
| 0x32b7d0 | takes a free CMeshDecal from a pool | `Get__Q23zdb14CMeshDecalPoolFb` (masked bytes of CDecalPool::Get; called on the CMeshDecal pools; calls 0x32c600) |
| 0x32c600 | next free entry of the CMeshDecal array | `GetNext__27RTArray<Q23zdb10CMeshDecal>Fb` (raw bytes of the CDecal instance; caller and position) |
| 0x32ba40, 0x32ba20, 0x32b910 | create, reset and destroy the decal builder: an 11856-byte object (vector_pod<Ui> at +0, 296 groups of 40 bytes at +12, group count at +0x2e4c) held in the vis_decal.cpp global 0x48e544 | guess: static helpers of vis_decal.cpp; names not known |
| 0x32b4c0, 0x32b8c0 | open a group in the builder and fill it from the vertex walk; push an index | guess: static helpers of vis_decal.cpp; names not known |
| 0x32bab0, 0x32b990 | constructor and destructor of the 40-byte builder group (CPnt3D, s16 0 and -1, two vector_pod<Ui>) | guess: the element type's `__ct`/`__dt`; its name is not known |
| 0x327d00, 0x327df0, 0x327eb0, 0x327ee0, 0x327fc0, 0x3280c0, 0x328290 | a second CVisData vertex walk over one sub-mesh's packets. It is keyed by the matrix id at +0x54, compared with the +0x18 word of each type 9 packet. It saves and restores its position at +0x58/+0x5c (fields that Clear initialises but the prototype never used): select (0x328290), next (0x327ee0), outer and inner search (0x3280c0, 0x327fc0), restore (0x327eb0) and a by-batch search (0x327df0, 0x327d00) | guess: CVisData methods, e.g. `SelectMeshVertex`, `NextMeshVertex`, `SearchMeshVertex` (the mirrors of SelectVertex, NextVertex, SearchVertex) |
| 0x32bf00 | recycles every decal of a CDecalPool and dereferences the visuals still holding one; CWorld::RemoveDecals now calls it on both CDecal pools | guess: `RemoveAll__Q23zdb10CDecalPoolFv` |

The largest new function placed by its neighbours, 0x32aad0 (2,536 bytes, after
CMeshDecalPool::Uninit in vis_decal.cpp), is therefore the CMeshDecal chain builder (above).

Really removed: the three `Write` functions (CVisual, CSubMesh, CMesh). Their vtable slot is gone
from all four tables (CVisual, C2DVisual, CSubMesh, CMesh). Nothing replaces them: the release
has no ZAR writer for visuals.

Layouts plainly shown by settled rows: the CVisual-family vtables lost slot 5 (Write); CDecal
gained a CPnt3D at +0x110 (AddDecal's new argument); CVisData's +0x54/+0x58/+0x5c are used by
the new walk.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses where marked.
- Outside the list: new 0x235620 (52 bytes, owner guess node_wave.cpp) is a VU0 helper that
  CVisual::ApplyDecal now calls three times (the prototype had that code inline). It belongs to
  another list.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 21 | 21 | 0 |
| removed | 3 | 3 | 0 |
| unsure | 1 | 1 (the candidate was right) | 0 |

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 168 pairs compared (callers, address loaders, vtable slots, data words, ordered
callee sequences), the callee sequences of their 115 paired callers, and 4 paired vtables
aligned slot by slot. 9 rows showed a difference: 7 gained new callers (the new mesh decal tree
and 0x32bf00), CMesh::InitMatrices moved from slot 7 to 6 (the uniform Write removal), and the
two RecycleTicks gained CWorld::RemoveDecals as a caller (a call it did not make before).
No crossed callee in any caller. 0 committed pairs wrong.

What misled it: only AddDecal's low similarity (0.486), which comes from register renaming
around one added argument. The call site decides.

What cost the most time: the new functions. They form one tree with no prototype counterpart,
so each had to be placed by its callers and by analogy with the CVisual decal chain.
Suggestion: when a new function has the masked bytes of a paired function, show its callees
and callers next to the twin's in the sheet. That alone settled both `copy` rows.
