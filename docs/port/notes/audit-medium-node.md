# Audit of list medium-node (2026-11-19, socom-port-audit-mnode)

The 74 medium functions (26,172 bytes) of `gamez/zNode`: node_assetlib.cpp, node_io.cpp,
node_main.cpp, node_model.cpp, node_saveload.cpp, node_vector.cpp, node_world.cpp. HEAD 1be01c4d
(trees built on a5b1639b, which touches no zNode file). Judged file by file in the scan's rank
order, each over its whole address range; addresses cited from `ref.dis`.

## Counts

| Verdict | Rows |
|---|---|
| MATCH | 55 |
| DEFECT-FIXED | 15 (A 2, B 8, C 5) |
| DEVIATION-KEPT | 4 |
| UNJUDGED | 0 |

Defect rate 15 / 74 (20%); A 2, B 8.

2026-11-20 (audit-closeout): kept guards removed, now DEFECT-FIXED C: #48 (the user's rule: the prototype's behaviour is kept; see [audit-closeout.md](audit-closeout.md)).

## Fixes

- A #27 `CNode::SetDynamicLight` 0x225d50: sets m_dynamic_light (byte 0x5c bit 2, 0x225da0), not
  the unread m_light_dynamic (bit 26); children get SetDynamicMotion (0x225dac / 0x225e08). Run mn1:
  263 world nodes and 35 model-tree nodes now carry m_dynamic_light (the "_L" visuals of
  hookupVisuals, the mission pickups), which vis_main's local-light pass reads.
- A #16 `CNode::InheritRegionMasks` 0x224780: the children get (pmask | own bit, cmask | own mask)
  (0x224820 / 0x224830); the port swapped them. Run mn1: of 1,940 world nodes 31 masks change, all
  lights (mdlight, alarm / horn lights, ...), 1 -> 0. RenderNode skips a local light when
  (light mask & node mask) != 0 (zrndr_pipe.cpp), and 1,174 node masks are nonzero: those lights
  were skipped for most nodes, they now light them.
- B #14 `CModel::Read` 0x223f80: the defaults go into a local params block (0x223fec) and the
  model takes the file's whole flag word (0x224068); the port kept the defaults and copied only
  m_active. Runs mn1 / mn2 (new / HEAD node_io.cpp): the model roots now keep the file's bits 18
  (has_visuals_prior_to_export: gear_holster, Satchel, al_terror_pack), 21 (m_char_common:
  cigarette) and 29 (flashbangUI); hookupVisuals missed no key either way (0 DeleteVisual calls)
  and the dynamic-light counts are equal, so no visible change was measured.
- B #38 `CNode::DeleteVisuals` 0x2278e0: delete only at Release() 0 (0x227928),
  m_modified (0x22799c), m_hasMesh cleared (0x2279ac), not m_hasVisuals.
- B #39 `CNode::DeleteVisual` 0x2279d0: the visual leaves the list (0x227a48 / 0x227a5c), is
  deleted at count 0 (0x227a90) and m_hasMesh recomputed (0x227ab0); the port did none of it.
  Not called in m8 (runs mn1, mn2: 0 calls).
- B #49 `CSaveLoad::LoadPalettes_PS2` 0x22a920: the palette list emptied first (0x22a948).
- B #4 `CAssetLib::AddModel` 0x2310b0: appended (0x2312f8), not inserted first; the conflict
  path written (resolver never set in the ELF).
- B #1 `CAssetList::GetModel` 0x230b70: the cache takes the result, NULL included (0x230c18).
- B #5 / #6 `CAssetLib::AddTexture` 0x231360 / 0x231480: a texture another library holds is
  refused (0x231430); the name form returns that answer (0x23154c).
- C #37 `CNode::AddChild` 0x227720: the m_char_common copy before the own-child exit (0x22778c).
- C #15 `CModel::Create` 0x2240b0: a failed read erases, clears the cache, deletes, NULL
  (0x224198 / 0x2241b0; unreachable: Read always succeeds).
- C #52 `FilterMissionFolder` 0x22b0e0: sprintf (0x22b140), not snprintf with a limit.
- C #9 `CAssetLib::CAssetLib` 0x231940: zassetlib.h lines 86 / 87 in the allocation records.

## Kept deviations (reasons in the code)

- #72 `CWorld::DeleteChild`: the reflective pass stops after its erase (the ELF walks past the
  vector's new end).
- #65 `CWorld::DismemberWorldModel`: the emptied worldmodel is kept (decided in mod-znode).
- #67 `CWorld::GenerateLightList`: returns the list, not its first word (mod-znode; unread).
- #12 `CLight::Read`: a missing "diffuse" gives zeros, not the ELF's stack words.
- #48 `CWorld::Read`: the missing-"world_tree" test (the ELF walks a list at address 0); the
  reason is now written in the code.

ELF quirks kept (in the code or noted in the rows): #17's unread second argument, #18's dropped
grandchild results, #21's mesh visual ending the whole call, #46's swapped sine / cosine, #47's
double SetModelname, #54's unread box / bool, #63's unread library, #64's repeated adds, #66's
dropped dynamic_cast, #27's children not lit, #30's zero up vector.

Float checks: #58 and #46 VU0 sums in the ELF's order; #55 and #56 compares in the ELF's forms
(c.le / c.lt with the bc1t / bc1f sense); #12 the reciprocals' operand order; #30 the scale's
division order. No float-to-unsigned conversion in the list.

## Leads for other lists

- `CAssetLib::AddPalette` 0x231000 (small band, not listed yet): the ELF appends (0x231080) and
  returns the palette (0x231088); the port inserts first and returns NULL.
- `CStack::m_pointer` is an int counter in the ELF (+1 / -1, initial -1); the port declares a
  `CMatrix *` and steps it by 64. Consistent everywhere and never read as a number, so harmless.

## What the packets lacked

The tag_NODE_PARAMS bit order (znode.h) for the byte-0x5c..0x5f bit tests (#27 needed it to see
the wrong bit); the callers' arguments of SetDynamicLight / DeleteVisual (vis_main.cpp) and the
consumer of m_region_mask (zrndr_pipe.cpp) to grade; the `_zanim_cmd_wind` and CWind layouts
(file-local / header, read by hand); CModel::Release (inline in #43's ELF, a separate port
function); the CMatrix default constructor (#23); every cited address taken from `ref.dis`, as
the compacted listings drop instructions.

## Runs

- Default build links (`default.sh audit-mnode-def1`, 0 undefined) on the final tree (`default.sh audit-mnode-def2`, library 0 errors, link 0 undefined).
- mn1 (scratch hook `build/port/boot-audit-mnode/hook_mnode.cpp` with `state/hook_state.cpp`,
  one mission, 210 s): the counts above; mission frames to 1,800+, no STOP or exception.
- mn2 (the same with HEAD's node_io.cpp, 150 s): the model-flag comparison above; the same
  region and dynamic-light counts; mission frames to 1,800+, no STOP or exception.
- `gate.ps1 -Only roundtrip -Build audit-mnode-gate` (loading and lifetime changes): PASS, 4 returns,
  in use 18,657,916 B flat.

| # | Address | Bytes | Function | File | Verdict | Grade | What was compared, what differed |
|---|---|---|---|---|---|---|---|
| 31 | 0x226ba0 | 640 | zdb::CLightMap::_Copy(zdb::CNode*) const | node_main.cpp | MATCH | | new CLightMap (384) for a NULL target: the inlined CLight ctor and light-map defaults (unit m_worldToUV, blend word 68, shadow / reflection 0, m_dir (1, 1, 1, 1), specular fade 1, m_lightMapTexture's texture: the port's InitLightMap, its guard decided earlier) and SetDynamic(true, false) (bits 1 / 2 as the ctor's); else dynamic_cast to CLightMap; the inlined CLight::_Copy (dynamic_cast to CLight, CNode::_Copy non-virtual), the range / colour / opacity copies, m_appliedToNode 0, SetTexture(m_pTex), the matrix copy, m_dir, the two bits, the 8-byte blend mode, specular fade; returns the target. The scan's offsets are GCC's vptr placement |
| 27 | 0x225d50 | 304 | zdb::CNode::SetDynamicLight(bool, bool) | node_main.cpp | DEFECT-FIXED | A | the ELF sets m_dynamic_light (byte 0x5c bit 2, 0x225da0) and gives each child SetDynamicMotion (inlined at 0x225dac, grandchildren at 0x225e08); the port set m_light_dynamic (bit 26, read nowhere) and recursed with SetDynamicLight, so no node ever got dynamic local lighting from hookupVisuals' "_L" keys, CZKit, PrepModels or the mission pickups (vis_main reads m_dynamic_light for the local light pass). Children not lit dynamically: ELF quirk kept |
| 28 | 0x225e80 | 304 | zdb::CNode::SetDynamicMotion(bool, bool) | node_main.cpp | MATCH | | bit 1 on the node, with children bit 1 on each child (one level inlined) and SetDynamicMotion(a, children) on the grandchildren |
| 29 | 0x225fb0 | 352 | zdb::CNode::SetDynamic(bool, bool) | node_main.cpp | MATCH | | bits 1 and 2 on the node, with children on each child (inlined) and SetDynamic(a, children) on the grandchildren |
| 32 | 0x226e20 | 272 | zdb::CLight::_Copy(zdb::CNode*) const | node_main.cpp | MATCH | | new CLight (256) for a NULL target with the CLight ctor inlined (type 8, +0xc0 / +0xc8 0, diffuse 128, opacity 64, applied 0: the port's ctor), else dynamic_cast; CNode::_Copy non-virtual, the nine copies in the ELF's order, m_appliedToNode 0, the target returned |
| 42 | 0x2285c0 | 652 | zdb::CNode::CNode() | node_main.cpp | MATCH | | unit matrix (identity copy), facade cleared (InitNodeParams' default too), vptr, m_parent 0, the three vectors (CDIVector flags stop-first 1, back faces 0), name 0, m_modified / m_character cleared, count / model / modelname / vid / nodeEx / atom / atom counts 0, tick -1, opacity 1, InitNodeParams(this, NULL), m_flatten 1, frame 0, custom light -1, m_unused 0, region mask 0, both bbox corners zero, NodeUniverse->AddNode when there is one, numNodes++, UNNAMED_NODE |
| 40 | 0x227b40 | 292 | zdb::CNode::AddVisual(zdb::CVisual*) | node_main.cpp | MATCH | | NULL / Exists exits (false), ref count +0x18 +1, appended, m_modified, m_transparent for vparams bit 0 without bit 8, m_hasMesh (0x5f bit 0) for vtype (lb) 1, m_hasVisuals (0x5e bit 7), SetParentHasVisuals, true |
| 41 | 0x227c80 | 372 | zdb::CNode::SetParentHasVisuals() | node_main.cpp | MATCH | | m_hasVisuals, the parent recursed when not yet marked, dynamic_cast to CModel, a copy of the instance list (+200) walked, each non-NULL unmarked node recursed |
| 37 | 0x227720 | 356 | zdb::CNode::AddChild(zdb::CNode*) | node_main.cpp | DEFECT-FIXED | C | the m_char_common copy (model child type 7 under a type-3 parent, lhu of +0x58) comes before the own-child exit (0x22778c); the port returned first, so a re-added model child did not copy the flag again. Rest as the ELF: NULL exit, a type-3 parent keeps the child's parent / count, else DeleteChild through slot 0x1c of the old parent, parent and m_count +1, reserve(size + 100) when full above 1000, appended, m_hasVisuals from the child, m_modified |
| 38 | 0x2278e0 | 232 | zdb::CNode::DeleteVisuals() | node_main.cpp | DEFECT-FIXED | B | the ELF deletes a visual only when Release() returns 0 (0x227904 / 0x227928), sets m_modified (0x22799c) and clears m_hasMesh (0x2279ac); the port deleted every visual whatever its count, cleared m_hasVisuals and left m_modified. Masked: the only caller (Particle::ReleaseInstance) frees shard nodes whose visuals are their own (count 1) |
| 36 | 0x227650 | 204 | zdb::CNode::DeleteChild(zdb::CNode*) | node_main.cpp | MATCH | | the count read first, Exists, type 3: Remove, -1, m_modified; else m_count - 1 floored at 0, the count, Remove, parent NULL, m_modified; the count returned |
| 33 | 0x227330 | 244 | zdb::CNode::SetNodeEx(zdb::CNodeEx*, bool) | node_main.cpp | MATCH | | m_nodeEx (+0x94) on the node, with descendants on each child (one level inlined) and SetNodeEx(ex, true) below |
| 34 | 0x227430 | 224 | zdb::CNode::FindChild(zdb::CNode*, bool) | node_main.cpp | MATCH | | NULL exit, a direct child returned, then (nested) each child's FindChild through slot 0x28 until one is found; NULL otherwise |
| 35 | 0x227510 | 312 | zdb::CNode::FindChild(char const*, bool) | node_main.cpp | MATCH | | NULL exit, strlen of the name, per child strlen equal then strcmp until found, then (nested) each child's FindChild through slot 0x24 until found |
| 16 | 0x224780 | 284 | zdb::CNode::InheritRegionMasks(unsigned int, unsigned int) | node_main.cpp | DEFECT-FIXED | B | the children get (pmask \| 1 << region_shift, cmask \| m_region_mask) in that order (a1 = s4, a2 = s3 at 0x224820 / 0x224830); the port passed them swapped, so below the world's children a non-light node's mask took its parent's mask bits and a light's mask its parent's region bit. Rest as the ELF: cell (type 10) exit, the shift from bits 13-17, a light (type 8) takes the cmask form, the rest the pmask form; the walk over a copy of the child list and the count returned (children's counts, +1 for a light with a nonzero mask; the port's bool is count != 0, LoadWorld ignores it) |
| 17 | 0x224910 | 492 | zdb::CNode::SetBlendMode(zdb::BLENDMODE const&, bool, bool, bool) | node_main.cpp | MATCH | | with visuals, the 8-byte mode (ld / sd) into word 0 of every m_alloc_blocks entry of every visual (the ELF unrolls by 8); with children and a nonempty list, the same call on each child with the same four arguments; the second argument unread (ELF quirk, noted) |
| 18 | 0x224c20 | 460 | zdb::CNode::FindMeshTextures() | node_main.cpp | MATCH | | the first mesh visual's (lbu vtype 1) list at +72 returned; else per child its first mesh, and without one each grandchild's FindMeshTextures with the result dropped (ELF quirk kept); NULL |
| 19 | 0x224df0 | 316 | zdb::CNode::SetDescendantVisuals(bool) | node_main.cpp | MATCH | | NULL node false (the build keeps the test: -fno-delete-null-pointer-checks), disable: bit 23 cleared and the children disabled, false; enable: own = visuals nonempty, the children's results ORed, m_hasVisuals = own or below, that value returned |
| 20 | 0x224f30 | 324 | zdb::CNode::SetDescendantDI(bool) | node_main.cpp | MATCH | | as #19 with m_di's size and m_hasDI (byte 0x5d bit 4) |
| 21 | 0x225080 | 328 | zdb::CNode::ScrollTexture(zdb::CNode*, float, float, bool) | node_main.cpp | MATCH | | per visual: lbu vtype 1 ends the whole call (ELF quirk kept), InTexfxpool skips, GetNext(true), InitScrollTexture(du, dv, scroll, visual, instance), appended to m_texfxpool; children (nonempty) with the same arguments |
| 22 | 0x2251d0 | 464 | zdb::CNode::RemoveDecals() | node_main.cpp | MATCH | | per visual CMesh::DereferenceDecals for vtype 1 else CVisual's, with the sign-extended m_vid (lh); each child's visuals with the child's m_vid, then the grandchildren's RemoveDecals |
| 23 | 0x2253a0 | 480 | zdb::CNode::ApplyDecal(zdb::CNode*, float, CPnt3D*, CPnt3D*, CPnt3D*, zdb::CTexHandle*, float, CPnt3D*) | node_main.cpp | MATCH | | m_hasVisuals, both matrices unit (CMatrix()), BuildMTW, CalcWorldToUV with or without up (handle +0xc texture, size), per visual vparams bit 16, vtype 2 remembered (the loop goes on), else ApplyDecalRender(&mtw, instance, opacity, proj, dir, handle, &wtuv); children only without a submesh, same arguments |
| 24 | 0x225850 | 436 | zdb::CNode::SetApplyMultipassEffects(bool) | node_main.cpp | MATCH | | vparams byte 1 bit 6 (bit 14) on every visual, each child's visuals in line, the grandchildren by recursion |
| 25 | 0x225a10 | 436 | zdb::CNode::SetApplyDecals(bool) | node_main.cpp | MATCH | | as #24 with byte 2 bit 0 (bit 16) |
| 26 | 0x225bd0 | 380 | zdb::CNode::SetUseParentBBoxTree(bool) | node_main.cpp | MATCH | | byte 0x5f bit 6 (bit 30) over the subtree; the ELF unrolls two levels, the port recurses: the same nodes in the same order |
| 30 | 0x226750 | 276 | zdb::CLightMap::SetTexture(zdb::CTexture*) | node_main.cpp | MATCH | | m_pTex, unit camera, CameraMatrix(position 0x43a120, direction 0x43a130, the zero bss qword: ELF quirk kept), the scale ((1 - 1 / width (lhu)) / 0x3fb4fdf4) / (2 * m_maxRange) in that order, the matrix words (0.5 offsets, 1 at [2][2] / [3][3]), MulMatrix(worldToUV, scale, camera) |
| 39 | 0x2279d0 | 360 | zdb::CNode::DeleteVisual(zdb::CVisual*, bool) | node_main.cpp | DEFECT-FIXED | B | the ELF takes every copy of the visual out of the list (remove_copy from the first one 0x227a48, erase 0x227a5c), Release()s it (0x227a64), with the flag at count 0 deletes it through the vtable (0x227a90) and recomputes m_hasMesh from the mesh visuals left (0x227ab0 / 0x227adc), then sets m_modified and returns the count; the port left the visual in the list (still drawn with no buffer for that instance), never deleted it, cleared m_hasVisuals instead and returned true. Only caller: hookupVisuals' visuals without a buffer key |
| 56 | 0x22cb30 | 516 | CWind::CmdTickWind(_zanim_cmd_hdr*, float*) | node_world.cpp | MATCH | | the world's wind (+0x4d4): per flag bit (lhu +4) 1 / 2 / 4 the goal from +8 / +0x10 / +0x18, at once when its time is <= 0.01 (0x3c23d70a, c.le as the port), else delta = (goal - value) / time and the tick flags; bits 8 / 0x10 / 0x20 / 0x40 / 0x80 / 0x100 the offset ranges and velocities (+0x20..+0x40) to CWind +0x38 / +0x3c, +0x4c, +0x44 / +0x48, +0x50, +0x58 / +0x5c, +0x60: the port's member order; returns 1. The scan's offsets are the port's CWorld layout |
| 55 | 0x22c570 | 432 | CWind::TickGoal(float) | node_world.cpp | MATCH | | the port's file-local WindGoalStep for the ELF's three inline steps: value + delta * dT, delta <= 0: value <= goal stops, else not value < goal stops (goal written, flag cleared); m_TickGoal = any of the three |
| 74 | 0x22fbc0 | 216 | zdb::CWorld::Initalize() | node_world.cpp | MATCH | | new CCamera (1312), m_camera / CVisual::m_camera only when different, SetName("camera"), SetPosition(zero), the world's two light-update bytes (+0x660 / +0x661) 1, CTexHandle::Create(m_shadowTex[0]) into m_shadowTexH, TexPhase[15][0]'s buffer: Add(handle, true) on its list, chain pointer +0x18 NULL; true |
| 71 | 0x22f370 | 436 | zdb::CWorld::DeleteChildren() | node_world.cpp | MATCH | | pass 1: non-cells leave the grid, parent NULL, deleted (vtable +8) when Release() is 0 and the slot NULLed; pass 2: cells parent NULL, deleted, slot NULLed; size 0 (storage kept). The scan's call counts are GCC's code layout |
| 66 | 0x22e760 | 276 | zdb::CWorld::Segregate_CCells(zdb::CNode*, zdb::CNodeVector&, zdb::CNodeVector&) | node_world.cpp | MATCH | | NULL exit, the dropped dynamic_cast to CWorld (ELF quirk, noted), per child dynamic_cast to CCell: appended to cells, else to others |
| 72 | 0x22f530 | 436 | zdb::CWorld::DeleteChild(zdb::CNode*) | node_world.cpp | DEVIATION-KEPT | | the reflective pass stops after its erase (recorded in the code): the ELF erases from the match to the end, deletes the match and keeps walking past the new end. Rest as the ELF: NULL 0, a shadow caster (bit 19) through remove_if(delshadow) and erase, the reflective (bit 10) match by +0x180, not the world's child: m_count (lh), else the grid Remove for a non-cell, the child list Remove, parent NULL, Release() returned |
| 68 | 0x22ef50 | 216 | LightList_Search(zdb::CNode*, zdb::CLightList&) | node_world.cpp | MATCH | | NULL and cell (lhu type 10) exits, a light (type 8) through dynamic_cast inserted at the front, the children recursed |
| 65 | 0x22e640 | 276 | zdb::CWorld::DismemberWorldModel() | node_world.cpp | DEVIATION-KEPT | | the emptied "worldmodel" is not deleted (decided in mod-znode, recorded in the code: it stays listed in its library; the ELF calls its deleting dtor at 0x22e72c). Rest as the ELF: GetModel("worldmodel"), false without it, ReserveChildren(size) (slot 0x14), each child appended, parented and CGrid::Update, the model's size 0, true. The trace line is port-only |
| 70 | 0x22f1a0 | 312 | zdb::CWorld::LandmarkList_Search(zdb::CNode*, CStack&, zdb::CNodeVector&) | node_world.cpp | MATCH | | NULL exit, Multiply(node matrix, true), with visuals (bit 23): a landmark (bit 3) takes CStack::m_top and is appended, else without m_apply_clip (bit 31) m_numNoFarClipNodes + 1; every child searched; the pop (pointer - 1, top - 64 bytes) |
| 69 | 0x22f090 | 268 | zdb::CWorld::GenerateLandmarkList() | node_world.cpp | MATCH | | the inline CStack push of identity (pointer + 1, top + 64), m_numNoFarClipNodes 0, LandmarkList_Search(this), the count, m_landmarks size 0, AddLandmark (slot 0x40) per found node, the found list size 0, the pop, the count returned |
| 54 | 0x22c420 | 200 | SetDIBBox(zdb::CNode*, CBBox const*, bool) | node_world.cpp | MATCH | | new CDIBBox (40), ditype bits 0-1 = 3, m_box = the inline GetBBox (own, parent's, else grandparent's GetBBox), AddDI, UpdateBBox(true) through slot 0x38; the box and bool arguments unread (ELF quirk, noted) |
| 67 | 0x22ed80 | 452 | zdb::CWorld::GenerateLightList() | node_world.cpp | DEVIATION-KEPT | | returns the list where the ELF returns its first word (decided in mod-znode, recorded in the code; LoadWorld ignores it). Rest as the ELF: the list emptied, LightList_Search(this), per light TransformToWorld of (0, 0, 0) into m_WorldPosition, the square (x - r, 0, z - r) / (x + r, 0, z + r) with r = m_maxRange, SetTraversalBoundary(box, 2, false), each traversed atom's cell gets the light appended |
| 60 | 0x22dcc0 | 216 | zdb::CWorld::ClearShadowList() | node_world.cpp | MATCH | | with a nonempty list each map deleted through the vtable when not NULL and its slot cleared, size 0; then the swap with an empty vector |
| 61 | 0x22dda0 | 216 | zdb::CWorld::ClearLightMapList() | node_world.cpp | MATCH | | as #60 for m_lightMaps |
| 62 | 0x22de80 | 280 | zdb::CWorld::WipeoutTextureAssetCharacters() | node_world.cpp | MATCH | | per set: the node vector emptied and swapped away, then (non-NULL) doDelBuffer of +0x14, the inline dtor and delete; the list erased whole |
| 64 | 0x22e350 | 580 | zdb::CWorld::AddTextureAssetCharacter(zdb::CAssetLib*, zdb::CNode*) | node_world.cpp | MATCH | | the common set (FindLib(CHARSETCOMMON), no node) first when the list is empty, appended; a non-common library (lbu +0x2b != 2): FindMeshTextures, a full list (+4 size == library +0x14) dropped, else no search; the search appends the node to the set of the same library; otherwise the common handles added per handle (ELF quirk kept) and a new set (lib, node, textures) appended |
| 63 | 0x22e070 | 376 | zdb::CWorld::DeleteTextureAssetCharacter(zdb::CAssetLib*, zdb::CNode*) | node_world.cpp | MATCH | | per set the node removed; an emptied set taken from the list (remove_if equal), doDelBuffer, dtor and delete, the walk restarted at the beginning; the library argument unread (ELF quirk, noted) |
| 59 | 0x22daf0 | 340 | zdb::CTextureAssetCharacterList::TestFOV(zdb::CCamera*, zdb::CTextureAssetCharacters**) | node_world.cpp | MATCH | | *common NULL, found = end, per set its library's phase byte, TestFOV(camera) != 0: phase 2 takes *common once, else the first other set; found returned |
| 57 | 0x22d6d0 | 428 | zdb::CTextureAssetCharacters::CTextureAssetCharacters(zdb::CAssetLib*, zdb::CNode*, zdb::CDynTexList*) | node_world.cpp | MATCH | | count 0, library, buffer NULL; with a node: Exists (dropped), appended; with textures "Tex" + node name, doAddBuffer(TexBufParams[0], [1]), the buffer, SetDynTexList; else "Tex" + RootName, the buffer, Add(lib, true) |
| 58 | 0x22d880 | 612 | zdb::CTextureAssetCharacters::TestFOV(zdb::CCamera*) | node_world.cpp | MATCH | | count 0, per active node (bit 0) the box (parent's GetBBox for bit 30, else +64), the eight corners in the ELF's order (x lo lo hi hi lo lo hi hi, y lo x4 hi x4, z hi lo lo hi hi lo lo hi, w 1), the VU0 sum order ((x r0 + y r1) + z r2) + r3, TestFOV(corners, NULL, true) == 2 clears m_character_infov else sets it, counted when in view and active; the count returned |
| 73 | 0x22f6f0 | 548 | zdb::CWorld::AddChild(zdb::CNode*) | node_world.cpp | MATCH | | own child exit, the old parent's DeleteChild (slot 0x1c), CGrid::Insert, parent, reserve(size + 100) when full, appended; a type-2 node: shadow (bit 19) then reflective (bit 10) render maps (736 bytes) on m_shadowTex[size], appended; m_char_common (bit 21): SetDynamic(true, true), m_character, AddTextureAssetCharacter(FindLib(2), child) on m_world |
| 14 | 0x223f80 | 292 | zdb::CModel::Read(zdb::CSaveLoad&) | node_io.cpp | DEFECT-FIXED | B | the ELF runs InitNodeParams on a local tag_NODE_PARAMS (0x223fec), fetches "nparams" (96) into it and gives the model its matrix, box, type and the whole flag word (+0x5c stored as a word at 0x224068); the port ran InitNodeParams on the model and copied only m_active, so every other flag of a model root stayed at its default. Rest as the ELF: GetOpenKey (true without a key), "regionmask" (4) into +0xb8, CNode::Read(sload) (the one-argument member), SetName(key name), true |
| 12 | 0x223390 | 292 | zdb::CLight::Read(zdb::CSaveLoad&) | node_io.cpp | DEVIATION-KEPT | | a missing "diffuse" leaves the ELF's uninitialised stack words, the port's zeros (recorded in the code). Rest as the ELF: ReadDataBegin, "diffuse" 12 bytes, "min_range" (float fetch, 0 when missing), m_invDeltaRange = 1 / (old max - min), UpdateBBox(false) through slot 0x38, "max_range_sq" into the same value, max = sqrtf, max sq, 1 / max, 1 / (max - min), UpdateBBox(false), true |
| 11 | 0x223230 | 348 | zdb::CNode::BuildMTW(CMatrix&) | node_io.cpp | MATCH | | type 6 (grid): unit matrix, the matrix returned; else mat = MulMatrix(mat, node matrix, mat) (the ELF's argument order), a grid parent returns mat, no parent NULL, else the parent's turn: the ELF inlines three levels then recurses, the port recurses (same products in the same order) |
| 13 | 0x223a30 | 508 | zdb::CNode::ReadDataBegin(zdb::CSaveLoad&) | node_io.cpp | MATCH | | SetName(open key name), "visuals": ReserveVisuals(key size), per key OpenKey, CVisual::Create, AddVisual when made, CloseKey of the element (the key OpenKey returns), CloseKey; "di" the same with CDI::Create(sload) / AddDI; false |
| 15 | 0x2240b0 | 296 | zdb::CModel::Create(zdb::CSaveLoad&, zdb::CAssetLib*) | node_io.cpp | DEFECT-FIXED | C | a failed Read takes every copy of the model from the library (find, remove_copy, erase), clears CAssetMgr::m_assets' model cache (0x224198), deletes the model (0x2241b0) and returns NULL; the port erased the first copy (end() when absent), kept the model and returned it. Not reached: CModel::Read always returns true. Rest as the ELF: new CModel(NULL) (224), AddModel with a library, Read through slot 0x30 |
| 52 | 0x22b0e0 | 216 | FilterMissionFolder(char const*, char const*, char const*, char*) | node_saveload.cpp | DEFECT-FIXED | C | sprintf as the ELF (0x22b140 / 0x22b178 / 0x22b194); the port had snprintf with a 128-byte limit the ELF lacks (the caller's paths are shorter). Rest as the ELF: "/" for a NULL infix, strncmp "mp" 2 / "m" 1, "%s/mp/%s" / "%s/sp/%s" / "%s/%s" with (infix, postfix), the count returned |
| 50 | 0x22aa70 | 472 | zdb::CSaveLoad::LoadTextures_PS2(zdb::CAssetLib*) | node_saveload.cpp | MATCH | | "renderphase" int fetch (-1 default), 3 <= p < 11 -> 16, the low byte stored only when fetched; "textures": per key OpenKey (no CloseKey when it fails), the key name, GetTexHandle, else AddTexture(name), else new CTexture(name) (112), Read: AddTexture(texture) or the deleting dtor; CloseKey(element), CloseKey; ReleaseDataBuffer into m_texture_buffer; true |
| 49 | 0x22a920 | 324 | zdb::CSaveLoad::LoadPalettes_PS2(zdb::CAssetLib*) | node_saveload.cpp | DEFECT-FIXED | B | the ELF empties the library's palette list first (size word 0 at 0x22a948); the port kept what it held. Masked: every library comes here once, empty. Rest as the ELF: "palettes", per key OpenKey, new CTexPalette(name) (32), Read (result unused), AddPalette(palette, false), CloseKey, CloseKey; true |
| 51 | 0x22af80 | 340 | find_node(zdb::CNode*, char const*) | node_saveload.cpp | MATCH | | NULL node or name NULL, strcasecmp of the node's name, per child (a NULL child skipped) its own name then its children's find_node, the first hit; NULL. The ELF inlines one level |
| 48 | 0x22a080 | 236 | zdb::CWorld::Read(zdb::CSaveLoad&) | node_saveload.cpp | DEFECT-FIXED | C | kept earlier; guard removed 2026-11-20: the world_tree key is walked without a NULL test. Earlier: the port's test for a missing "world_tree" key (the ELF walks and closes it unchecked: a list at address 0); the reason now recorded in the code. Rest as the ELF: per element OpenKey, CNode::Read(sload, this), CloseKey(element), CloseKey(tree), true |
| 9 | 0x231940 | 204 | zdb::CAssetLib::CAssetLib(char const*) | node_assetlib.cpp | DEFECT-FIXED | C | the inline SetName records zassetlib.h lines 86 / 87 for its _free / _strdup (0x2319d4 / 0x2319e8); the port recorded this file and its own lines. Rest as the ELF: name 0, the three vectors, buffers 0, ref count 1, autoload 1, locked / gear 0, phase 0, the name freed when set (never: just cleared), strdup |
| 4 | 0x2310b0 | 640 | zdb::CAssetLib::AddModel(zdb::CModel*) | node_assetlib.cpp | DEFECT-FIXED | B | a model of a name no library holds is appended (0x2312f8) and owned (+0xd8, 0x231304); the port inserted it first, which reversed each library's model order (every m_models walk: hookups, the destructor, GetModel on duplicate names). The conflict path written as the ELF (m_conflictresolver(name, this, holder); only read in the ELF, so it stays NULL and the model is returned unadded, as the port did): this library chosen takes the holder's model out and adds here, else this library's out and adds to the holder, the cache cleared (0x231228 / 0x2312c0). Locked: NULL |
| 8 | 0x231750 | 492 | zdb::CAssetLib::~CAssetLib() | node_assetlib.cpp | MATCH | | per model m_AssetLib (+0xd8) cleared before the NULL test (written through NULL as the ELF), the deleting dtor through slot 8, the slot NULLed, size 0; the buffers freed (lines 110 / 114) and NULLed, CTexList::Free, each palette's deleting dtor, size 0, the name freed (124) and NULLed |
| 10 | 0x231a10 | 272 | zdb::EmptyAssetRecycleBin() | node_assetlib.cpp | MATCH | | every library in the bin deleted (NULL-safe) and its slot NULLed, the list erased whole, its model cache NULL |
| 1 | 0x230b70 | 204 | zdb::CAssetList::GetModel(char const*) | node_assetlib.cpp | DEFECT-FIXED | B | the search's result becomes the cache even when NULL (0x230c18); the port kept the old cache on a miss (it then answered later lookups of that old name from a model the ELF would search again). Rest as the ELF: the cache hit by strcmp with a non-NULL name, the libraries' CModelVector::GetModel in order |
| 2 | 0x230ce0 | 388 | zdb::CAssetList::FindLib(char const*) | node_assetlib.cpp | MATCH | | NULL name NULL, the first IsNamed library, else the first whose root name (after the last '/' or '\', lb tests) strcmp-equals the name |
| 3 | 0x230f10 | 232 | zdb::CAssetList::Clear() | node_assetlib.cpp | MATCH | | each library deleted (NULL-safe), its slot NULLed, the list erased whole, the cache NULL |
| 5 | 0x231360 | 284 | zdb::CAssetLib::AddTexture(zdb::CTexture*) | node_assetlib.cpp | DEFECT-FIXED | B | a texture whose name a loaded library already holds is refused (false, 0x231430), else appended and the Append handle answers; the port appended it whatever the search found and returned true. Masked: LoadTextures_PS2 only adds textures no library holds. Lock and NULL tests in the ELF's order |
| 6 | 0x231480 | 244 | zdb::CAssetLib::AddTexture(char const*) | node_assetlib.cpp | DEFECT-FIXED | B | the found handle's texture goes to AddTexture(CTexture *) and its answer is returned (0x23154c); the port returned true (and, with #5, added a texture shared with another library). Masked: LoadTextures_PS2 calls it only when GetTexHandle found nothing, so it returns false in both |
| 7 | 0x231580 | 328 | zdb::CAssetLib::IsNamed(char const*) | node_assetlib.cpp | MATCH | | strcmp(name, m_name) equal: true; else from the two ends, slashes ('/', '\') skipped on each side every round, equal characters step both, a mismatch false, one side exhausted: true only when both are (i == j) |
| 46 | 0x229580 | 616 | zdb::CNode::ComputeFacadeMatrix(CMatrix const*, CMatrix*) | node_model.cpp | MATCH | | unit turn, d = model row 3 - camera row 3 (Sub), facade bits 8-9: 1: d.y 0, Normalize, [0][0] = [2][2] = d.z, [0][2] = -d.x, [2][0] = d.x; 2: d normalised, flat = d with y 0 normalised, the turn from flat.x / flat.z, v = (d, 0) through it (VU0 x r0 + y r1 + z r2 + w r3), the turn rebuilt with flat.z / flat.x (the swapped pair: ELF quirk kept), tilt [1][1] = [2][2] = w.x, [1][2] = -w.y, [2][1] = w.y, both = MulMatrix(turn, tilt), the two copies; rows 0-2 into the model; other facades unchanged |
| 47 | 0x229dc0 | 512 | zdb::CModel::~CModel() | node_model.cpp | MATCH | | with a library: its model of this name found, every copy erased (find / remove_copy / erase: the port's remove / erase), the cache NULL, m_AssetLib NULL; per user node: types 3 / 2 (type 3 first DeleteChildren through slot 0x20) m_model NULL and SetModelname(NULL), then SetModelname(NULL) for every node (twice for 2 / 3: ELF quirk, noted); the list erased; ~CNode follows |
| 43 | 0x228fd0 | 288 | zdb::CNode::Delete(zdb::CNode*) | node_model.cpp | MATCH | | NULL 0; lhu type 4: parent and first child (or NULL) read, RemoveFromParent of the node and of the child, the parent's AddChild(child) through slot 0x18 even for NULL; type 2: the model's list loses the node and its m_parent is cleared when it was the node (the port's CModel::Release, inline in the ELF), RemoveFromParent; the deleting dtor; 0 |
| 44 | 0x229150 | 216 | zdb::CNode::CreateXRef(zdb::CModel*, CPnt3D const*, CQuat const*) | node_model.cpp | MATCH | | NULL model NULL, new CNode (192), SetPosition / SetRotation(const CQuat &) when given, type 3, SetName("XRef"), AddChild(model) through slot 0x18, the node returned |
| 45 | 0x229230 | 292 | zdb::CNode::CreateInstance(char const*, CPnt3D const*, CQuat const*) | node_model.cpp | MATCH | | NULL name and no world NULL, CWorld::GetModel, Copy, position / rotation when given, appended to the model's list, the model's m_parent = the instance only while the list holds one, m_model, SetModelname(model name), type 2 |
| 53 | 0x224350 | 208 | zdb::CNodeVector::GetNode(char const*) | node_vector.cpp | MATCH | | NULL name NULL, the first non-NULL node with a non-NULL name strcmp-equal to the name, NULL at the end |
