# mod-render notes (2026-11-14, socom-port-mod-render): the rendering-side small modules and the shadow chain

Scratch `build/port/boot-mod-render/` (untracked: NOTES.md, mine.txt, `survey0.txt` / `survey1.txt`, asm dumps,
the edit scripts `e_*.py`, run logs and screenshots). Changed files: `mine.txt` (the ten modules and zNode in
place, `zVideo/zvid_init.cpp` (zVid_FrameRestore), the `render` test hook, its README row and this note).

## Result
- `survey.py gamez/<module>/`, stubs before -> after: zParticle 4 -> 0, zGraph 16 -> 0, zVisual 8 -> 0,
  zIntersect 3 -> 0, zRender 5 -> 0, zTexture 5 -> 0, zMath 5 -> 0, zBone 2 -> 0, zCamera 2 -> 0, zSoftImage 1 -> 0
  (51 functions, 21.9 KB); zNode 4 -> 0 (the shadow chain).
- Character shadows in m8: the player's seal casts a shadow on the snow along the world's shadow vector (1, -1, 1)
  (legs, body and rifle silhouette; it follows the stance and animation). Run rn1 / rn2 / rn3 (HEAD c89e1c63 + mine +
  the edit files, `port/test-hooks/render`): `AddShadow player` -> one render map (`render_map_0` into `ShadowX_0`),
  one `CRenderMap::Update` and one `zVid_FrameRestore` per frame, the map's range 40 (twice the box), frame time
  at the 60 Hz lock (0.0167 s) as before. Before / after with the test camera on the player while firing: run rn0b
  (`-DRN_NOSHADOW -DRN_NOLIGHTMAP`) has no shadow, rn3 the shadow (untracked screenshots
  `build/port/screenshots/49-render/`). Team-mates get none (PostCreateSeal's maxShadow).
- Light maps: each shot adds the weapon's `muzzle_light_most` light map (LIGHT command, texture `light_map.tif`,
  range 100) to the world's list (was dropped: `AddLightMap` was empty) and BuildLightMapList / `VuLightMap` take it
  for the nodes it reaches; it lives one flash. No difference shows on the snow in the screenshots (rn0b-100 /
  rn3-100); the light maps of the LIGHT command are traced, not shown.
- Stability / heap / default build: run rn9 (HEAD 0266b548 + mine, render hook, firing every second for 28 s):
  mission 58 -> 246 s (188 s), 29 muzzle flashes, no STOP or GIF stall, heap in use 22,790,612..22,790,900 B over
  the last 30 s. Run rnm3 (`port/test-hooks/state`, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4`, 0266b548 + mine):
  in use at the four returns 17,838,308 / 17,838,404 / 17,838,404 / 17,838,404 B (flat; about 1.9 KB over that
  HEAD's figure: the world's four render-map textures and their handle), no STOP. Default build (`default.sh`,
  HEAD e06077e4 + mine): main menu (dlgMenu) at 16.4 s.
  Run rn10 (HEAD e06077e4 + mine, render hook, firing): mission 58 -> 245 s (187 s), 29 flashes, no STOP or GIF
  stall, the shadow drawn, heap in use 22,799,956..22,800,388 B over the last 30 s.

## Survey at the start (HEAD 2c3f092f)
Callers from `xref.py` (jal) and `addrref.py` (vtables, static destructors).
- zParticle: BufferElement `DrawRotated` 0x234c90 / `DrawXZ` 0x235260 / `DrawStreaked` 0x235780 (Source draw types
  1-3, from DrawRange / DrawFlush / DrawOne), `Source::GetBBox` 0x238af0 (RenderBBox, every Draw / DrawPrep: m8).
  Placeholder: the Source constructor's box DI node (needed the CDIPoly constructor).
- zGraph: `CGraph` FindEdge / DeleteNode / dtor, `CGRoute` (5), the graph tree (`BuildRoute` 0x20fa60, `BuildTree`
  0x210010, `PopulateTree`, `CGTree` FindNode / RemoveChild / dtor / Destroy, `_release_tree`). Cross-map AI
  routes only (zAI's RegisterPathPlan / plan_addleg, still "port: not written" there): not reached in m8.
- zVisual: `VuShadowMap` 0x30b860 / `VuLightMap` 0x30ba40 (multipass entries of VuUpdate), `GetTextureSelectBlock`
  0x30da60 (render-map textures), the three `Write`s, `UpdateCentroid`, `ComputeBBox` (vtable; no caller).
- zIntersect: `CDIBBox::SetCDIBBox` 0x21c7f0 (CMission::Init, CZSealBody ctor: m8), `CDI::SetEdgeVecsAndNorm`
  0x21d840 (Source::GetBBox), `CDIPoly` ctor 0x21e490 (CDI::Create, Source ctor: m8).
- zRender: `RenderMeshShadow` 0x242920 / `RenderNodeShadow` 0x242b70 (RenderWorld's render maps),
  `RenderLineWorld` 0x245930 (ai debug lines), `CPipe::Uninit` 0x245fa0 (CGame::StopEngine, a stub), `~CPipe`
  (static destructor: never on the PS2).
- zTexture: `SetName`, `SetupSpecialTextures` 0x2f92a0, `LoadGS` 0x2f9510, `po2` (the world's render-map textures);
  `CTexManager::WipePktBuf` 0x2fafa0 (CGameMenu::SwitchMenu: menus).
- zMath: `CFRect` ctor (CGrid ctor), `CQuat` Ln / Div (SoftImage frame data), ToEuler (network), `exp_tl` 0x222f90
  (CharacterDynamics::Load: m8). zBone: `~CScriptArchive`, `zBoneUnloadAll` (static destructor). zCamera: `~CCamera`,
  `UpdateDirectionalFog` 0x1e7e60. zSoftImage: `~CZSIObject`.
- Placeholders in written fences: zCamera `CAppCamera::APLookAt` (empty), the CAMERA_PARAMS command (parse / begin /
  tick), the other camera command parsers; zMath `init_trig_table`'s exp table; zNode the shadow chain parts.

## Written (ELF addresses)
- zMath: `CQuat::Ln` 0x220750, `Div` 0x220eb0, `ToEuler` 0x2212f0, `CFRect` 0x220590, `exp_tl` 0x222f90; fixed
  `init_trig_table` 0x223050 (the exp table is exp(10 i / 256) in double, i before the step; was exp(10 (i + 1)) / 256).
- zBone: `~CScriptArchive` 0x1dd420, `zBoneUnloadAll` 0x1dd520 (declared in zbone.h). zSoftImage: `~CZSIObject` 0x1dddd0.
- zCamera: `~CCamera` 0x1e76e0 (compiler-generated parts only), `UpdateDirectionalFog` 0x1e7e60,
  `CAppCamera::APLookAt` 0x1ea200.
- zTexture: `CTexture::SetName` 0x2f8d30, `LoadGS` 0x2f9510 (returns the 64-word block count now),
  `SetupSpecialTextures` 0x2f92a0 (the "ShadowX_" / "ReflectionX_" select block: TEX0 / TEX1 / TEXA / CLAMP /
  ALPHA), `po2` 0x2f9600, `CTexManager::WipePktBuf` 0x2fafa0.
- zIntersect: `CDIBBox::SetCDIBBox` 0x21c7f0 (the six unit-cube faces; `bbox_poly` is `CDIPoly*[6]`),
  `CDI::SetEdgeVecsAndNorm` 0x21d840, `CDIPoly` ctor 0x21e490 (CDIBBox is a friend of CDI).
- zParticle: `DrawRotated` 0x234c90, `DrawXZ` 0x235260, `DrawStreaked` 0x235780 (two-triangle textured quads,
  file-local packet helpers), `Source::GetBBox` 0x238af0; the Source ctor 0x23a0d0's box DI node ("PARTICLE DI
  NODE", six CDIPolys, a `CParticleEx` (defined in zparticle.h) pointing back) and the dtor's deletes.
- zVisual: `VuShadowMap` 0x30b860, `VuLightMap` 0x30ba40, `GetTextureSelectBlock` 0x30da60, `Write` 0x30d100 /
  0x30ee30 / 0x30f0f0 (bool now), `UpdateCentroid` 0x30d270, `ComputeBBox` 0x30d280 (empty in the ELF).
- zRender: `RenderNodeShadow` 0x242b70, `RenderMeshShadow` 0x242920, `RenderLineWorld` 0x245930 (declared in zrender.h), `Uninit`
  0x245fa0, `~CPipe` 0x2462e0.
- zGraph: `CGRoute` ctor / dtor / Append / Clear / PostProcess (0x20f7d0-0x20f910; a node list), `CGraph::FindEdge`
  0x20e7c0, `DeleteNode` 0x20eb10, `~CGraph` 0x20ed10, `BuildRoute` 0x20fa60 (bool), `BuildTree` 0x210010 (Dijkstra
  on a cost-sorted list; returns the tree), `PopulateTree` 0x20fdb0, `CGTree` FindNode 0x210720 (returns the
  entry) / RemoveChild 0x210860 / dtor 0x2108b0 / Destroy 0x210950 (static) / `_release_tree` 0x210b90. Layouts
  (no DWARF, names invented): CGRoute (12 bytes), CGTree (20: children, parent, node), CGNode +0x1c `m_prev` /
  +0x20 `m_cost`.
- zNode: `CRenderMap` ctor 0x22bc30 / dtor 0x22bba0 / `Update` 0x22b310 and its 736-byte layout (node_shadow.h, no
  DWARF: camera / screen / UV matrices, the VU tags, the 13-qword GS packet from `shadowTemplate`), `CWorld::AddShadow`
  0x22f9f0, `AddLightMap` 0x22fb20, the world ctor's four 256 x 256 render-map textures (0x2303c8),
  `Initalize`'s shadow texture handle in the TexShadow buffer (0x22fc48), `AddChild`'s render maps (0x22f7c8).

## How the shadows work (from the asm)
- `CZSealBody::PostCreateSeal` (zSeal, already written) calls `CWorld::AddShadow` for the player: a `CRenderMap`
  into `ShadowX_<n>` (PSMCT16, 256 x 256, at the start of the texture area: the TexShadow buffer). Its light map
  (itself, a shadow map) joins the world's light maps.
- Each frame `CPipe::RenderWorld` runs `CRenderMap::Update` (box, range twice the box's largest side, a camera at the
  box centre looking along the shadow vector; the GS packet points FRAME at the texture and clears it; VU 4-7 the
  render matrix, VU 26 the shadow GIF tag) and draws the caster with `RenderMeshShadow` / `RenderNodeShadow` in the
  render-map state (`CVisual::m_renderMap`: VuUpdate's `vuGatherFixKickShadow` path), then `zVid_FrameRestore`
  sends the frame setup packet again.
- `CPipe::BuildLightMapList` puts the shadow maps that reach a node into `CVisual::m_shadowMapList`; `VuShadowMap`
  adds the multipass entries (select block, world-to-UV times model-to-world, position, direction, range, colour)
  that the VU1 `MP_SHADOW_MAP` commands draw over the ground. The caster's own node is skipped.

## ELF quirks kept
- zMath: `CQuat::Div` writes w first and reads `this` again (aliasing). `exp_tl` at 10 reads one entry past the
  table (multiplied by 0).
- zBone: `~CScriptArchive` empties the script list before `zBoneUnloadAll`, which then deletes no script.
- zTexture: `SetupSpecialTextures` stores the select block in `m_loadimage` (the destructor frees it through it).
- zParticle: `DrawRotated` tests the screen edges with max(a, b) (signed); its XRate / YRate statics are never read.
  `DrawStreaked` gives both ends the tail's z and writes 1.5 times it; a zero screen direction is (dx, -1).
  The box DI node's polys hold no points until the first GetBBox.
- zGraph: `BuildRoute` returns true with an empty route when the tree does not reach the goal; `DeleteNode` does not
  NULL-test the edge's other end; `BuildTree` clears the edges' top flag nibble and never reads it, and ignores its
  float argument.
- zNode: every render map is a shadow map (m_isShadow is set again after the type test); `AddShadow` does not bound
  the four textures; `Update` does not widen min.y by boxAdjust, starts the view box at the origin, and writes the
  light map's world-to-UV row 3 before overwriting it. `RenderNodeShadow` ends the walk at a node without visuals.
- zCamera: `APLookAt` does not read its entity argument.

## Port deviations
- `VuLightMap` does not call `SaveTextureSelect` (the ELF queues the light map's select so VuExecuteState0 unpacks
  the texture's current TEX0 and the ALPHA qword over the copy). With it, on HEAD 0266b548 the first muzzle-flash
  light map jammed the GIF path in PCSX2 ("GS packet size exceeded VU memory size", then `sceGsSyncPath: path
  stuck`; run rn5 froze, rn7 stuck 4 times); with it skipped (test run rn8, then the code) 30 flashes ran clean.
  The light map's data were sane (rn7 dump: ranges 16..100, 64 x 64 texture, 6-qword select, blend 0x44); the
  queue / VuExecuteState0 code matches the ELF; the cause is not found. The copied select already carries the
  blend mode; only a texture relocated later in the frame would draw from a stale TEX0.
- `CRenderMap::Update` builds the caster's view-space corners in a local array (the ELF uses the scratchpad's first
  128 bytes). The ctor zeroes the up-vector axis before setting its one component.
- `AddLightMap` NULL-tests `CVisual::m_lightMapTexture` (as the CLightMap ctor already did). The world dtor's handle
  guard stays for a world that was never initialised.
- `~CScriptArchive` does not free the word after the archive (+0xb0: not modelled in the port's layout).
- `exp_tl`'s table index and the Write functions' bool returns follow the ELF; `LoadGS` returns its count
  (the port declared void).

## Outside the modules (in place, after the files were committed clean)
- zVideo/zvid_init.cpp: `zVid_FrameRestore` 0x307b60 (was empty: after the render maps the frame would stay on the
  shadow texture) + the zsys_spr.h include.
- port/test-hooks/README.md: the `render` hook row.

## Not written / next
- zCamera: the CAMERA_PARAMS command (`CmdParseParams` 0x1e6300, `CmdBeginParams` 0x1e61c0, `CmdTickParams`
  0x1e5570: 3148 bytes of keyframe tracks for fields of view, planes, fog ranges / heights, range scale, with the
  saved parameters restored at the end) and the other camera command parsers (loaders, never run on retail data).
  m8 uses CAMERA_PARAMS (set0 #51, 36 times); writing Begin alone would leave fog switched, so all three stay empty.
- zAI: the cross-map routes can now use `CGraph::BuildRoute` / `FindEdge` / `DeleteNode` / `CGRoute`
  (CAiMaps::RegisterPathPlan, CAiPath::plan_addleg: "port: not written" there; zAI's files).
- Only the player gets a shadow in m8 (PostCreateSeal's maxShadow); reflection maps (type 1) are written, untested.

## Test hook
`port/test-hooks/render/` (`hook_render.cpp` + `build.sh`, with `../state/hook_state.cpp`; `pad_fire.txt`):
AddShadow / AddLightMap traces, a 150-frame census (render maps, light maps, updates and frame restores per frame,
the player's map range, frame time, heap), `-DRN_NOSHADOW` (the "before"), `-DRN_CAM=<frame>` / `-DRN_CAMD=<d>`
(test camera on the player, three views; `-DRN_CAMLEN` frames each), `-DRN_NOLIGHTMAP` (plain light maps
skipped), `-DRN_LMDUMP` (the last plain light map's fields for three frames).
