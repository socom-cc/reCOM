# mod-znode notes (2026-11-14, socom-port-mod-znode): the unwritten part of the zNode module

Scratch `build/port/boot-mod-znode/` (untracked: NOTES.md, mine.txt, asm dumps, the disc's `M8.ZED` under
`disc/`, `thin.py` listing "written" fences with thin bodies). Changed files: `mine.txt` (zNode in place, the
small zVisual / zTexture / zIntersect edits below, the `znode` test hook and this note).

## Result
- `survey.py gamez/zNode`: stubs 21 -> 4 (11,944 -> 1,796 B; written 42,712 -> 52,328 B). Left: `AddShadow`,
  `AddLightMap`, the `CRenderMap` ctor / dtor (the shadow chain, below). `survey.py zVisual/(vis_texfx|vis_bands)`:
  the texture-effect and band-object files have no stub left.
- What changed in m8 (runs zn2 / zn5 / zn6, `port/test-hooks/znode`, fake pad through the state hook):
  - Level of detail: the 30 `LOD_Object` bands are read (the menus' world has 2); `CPipe::RenderVisual` already
    applied them, so 48 banded visuals a frame are tested and about 35 are not drawn (they were all drawn
    before: the band vector was empty). The view looks the same (the skipped visuals are past the fog; run zn3,
    `-DZN_NOLOD`, draws them all); the frame time stays at the 60 Hz lock (0.0167 s) either way.
  - Scrolling texture: the computer's `screenglow` (model `alaska4d_computer`) gets a texture effect; its first
    vertex's u moves 16384 (4 repeats) every 2.5 s, kept within the 20480 limit. With the test camera in front of
    the laptop (zn5) the screen region changes between shots 2 s apart while the rest of the frame is
    pixel-identical.
  - Landmarks: `alaska4d_sky` and `sun` leave the grid for the landmark pass: the sun is drawn now (top right,
    compare `zn1-120` / `zn2-120`); no node needs the far plane kept, so the far clip stays at the mid plane (600).
  - Lights: 31 lights (fireplaces, lamps, alarm / horn lights) are listed in 24 grid cells (69 entries), so
    `BuildNodeLocalLightList` finds local lights now (none before: the search never left the cells).
  - Wind: the world's wind is reset and ticked (about (0.5, 0, -11) with the random azimuth / speed walk); it was
    uninitialised memory for the particles before.
- Stability: run zn6 (HEAD f0fbe925 + mine, intro movie skipped with CROSS, briefing cameras with X): in the
  mission from 73 s to the end of the run at 251 s (178 s), no STOP, heap in use 22.06 -> 22.10 MB, flat
  within 1 KB over the last 50 s. Run znm (`port/test-hooks/state`,
  `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4`, HEAD f0fbe925 + mine): four missions (pause ABORT and the fatal
  fall, both exits and the restarts), in use at the four returns 17,210,532 / 17,210,628 / 17,210,628 /
  17,210,628 B (flat), no STOP; the only failed allocations are the game's own probes.
- Default build (`default.sh zndef`): main menu (dlgMenu) at 15.9 s.

## Survey at the start (HEAD fca019a3)
`survey.py gamez/zNode`: 21 empty stubs, 11,944 B (42,712 B written). m8's `M8.ZED` has no light list and an
empty world tree, a `LOD_Object` key (30 bands of 32 bytes), `Material_Object` (2 bands of 28 bytes) and
`TextureScroll_Object` (one band: model `alaska4d_computer`, node `screenglow`, du -1.6, dv 0).
- Skipped part of `CSaveLoad::Load` (0x22a618-0x22a884): the three band reads (zVisual stubs) and the scrolling
  textures (`find_node`, `CNode::ScrollTexture`, the whole `CTextureFX` pool in zVisual: empty stubs).
- Reached in m8 but empty: `CWind` Reset / TickGoal / Tick (the world's wind, read by every particle; was left
  uninitialised), `CRipple::Tick` / `CTextureFX::Tick` (VisualEffectsTick), `CRipple::Init` (StartEngine).
- "Written" fences that were placeholders: `CLight::Read` (`return true`), `ComputeFacadeMatrix` (empty: facade
  nodes kept their own rotation), `LandmarkList_Search` (empty) / `GenerateLandmarkList` (re-added nothing, never
  counted the nodes the far plane must not clip) / `AddLandmark` (empty), `LightList_Search` (cell test inverted:
  no light was ever listed) / `GenerateLightList` (wrote the position over the matrix, added lights to the cells'
  children), `CNode::AddChild` (the model child's `m_char_common` copy).
- Not reached in m8: `GetClosestNode` (network-only pickup / bomb code), `SetBlendMode` (zAnim blend-mode
  command), the WIND zAnim command, `CLensFlare` (type-9 nodes), the light-map node functions, `UpdateBBoxFromDI`
  and `DeleteLandmark` (virtual, no caller), `CLight::_Write`.

## Written (ELF addresses)
- node_saveload.cpp: `CSaveLoad::Load` 0x22a618-0x22a884 (band reads, scrolling textures), `find_node` 0x22af80.
- node_main.cpp: `CNode::ScrollTexture` 0x225080, `SetBlendMode` 0x224910, `SetDynamicMotion` 0x225e80,
  `AddChild` 0x227740 part, `CLightMap` ctor 0x2268e0 / dtor 0x226870 / `SetTexture` 0x226750 / `_Copy` 0x226ba0,
  `CLight` dtor 0x226ae0 (empty in the ELF).
- node_io.cpp: `CLight::Read` 0x223390, `CLight::_Write` 0x224210 (returns 0).
- node_model.cpp: `ComputeFacadeMatrix` 0x229580, `UpdateBBoxFromDI` 0x229870 (+ the inline `CBBox::Normalize`
  0x229cf0 as a file-local helper).
- node_world.cpp: `CWind` Reset 0x22c4f0, TickGoal 0x22c570, Tick 0x22c720, CmdTickWind 0x22cb30, CmdParseWind
  0x22cd40 (record `_zanim_cmd_wind`, 68 bytes, names invented); `LandmarkList_Search` 0x22f1a0,
  `GenerateLandmarkList` 0x22f090, `AddLandmark` 0x22ecd0, `DeleteLandmark` 0x22ec80, `LightList_Search`
  0x22ef50, `GenerateLightList` 0x22ed80.
- node_util.cpp: `GetClosestNode` 0x22c1a0, `DEFAULT_CLOSESTNODE_DOT` (cos 65 degrees, `__sinit_node_util`).
- node_wave.cpp: `CRipple` Init 0x232080 / Uninit 0x232050 / Tick 0x231dd0 (nothing in the ELF starts a ripple).
- node_lensflare.cpp / .h: `CLensFlare` ctor 0x231ca0 and its 224-byte layout (a vector at +0xcc).
- node_projectedmap.cpp: `CProjectedMap_Object` ctor 0x22b2d0 / dtor 0x22b260.
- zVisual/vis_bands.cpp: `CLOD_Object` / `CMaterial_Object` / `CScrollingTexture_Object` Read (0x310fa0,
  0x310d50, 0x310a80) and the five band objects' ctors / dtors (m_bandMax 256).
- zVisual/vis_texfx.cpp: `CTextureFX` Init / Uninit / Clear / InTexfxpool / Tick / InitScrollTexture /
  ScrollTexture, `LimitUVs` 0x313d30; zTexture/ztex.h: the `RTPool<T>` template (GetNext 0x228e30, Clear 0x314330,
  ctor / dtor) and the `CTextureFX` (16 bytes) / `CRipple` (56 bytes) layouts (no DWARF, names invented).
- zIntersect/zintersect.h: `CNode` a friend of `CDI` (UpdateBBoxFromDI reads the points).

## ELF quirks kept
- `CSaveLoad::Load`: a scrolling texture's node found in its model scrolls once per instance of the model (the
  same node each time; `InTexfxpool` makes the repeats no-ops). `CLOD_Object::Read` does not test its argument
  for NULL (the other two reads do).
- `CNode::ScrollTexture`: a mesh visual (vtype 1) ends the whole call, children included.
- `CTextureFX::ScrollTexture` walks index entries, so a vertex shared by several triangles moves once for each;
  `LimitUVs` tests each coordinate after the earlier steps moved it.
- `CLight::Read`: the first `m_invDeltaRange` uses the range before the read; a missing `max_range_sq` reads
  the `min_range` value.
- `CWind::Tick`: the zenith sum is clamped to +-90 although the angles are radians, and w is scaled (never
  set). `CmdParseWind`: an empty AZIMUTH / ZENITH / SPEED array reads element 0; SPEED is not converted.
- `CLightMap::SetTexture`: the camera matrix is built with a zero up vector (an all-zero bss qword).
- `UpdateBBoxFromDI` skips each DI's point 0. `ComputeFacadeMatrix` (facade 2) brings the direction round with
  a y turn whose sine and cosine are swapped. `GetClosestNode` never reads its fifth argument and tests the
  height in double. `SetBlendMode` never reads its second argument.
- `CRipple::Tick` runs on an always-empty list (nothing in the ELF starts a ripple).

## Port deviations
- The light-map defaults read `CVisual::m_lightMapTexture`'s texture only when there is one (the ELF reads it
  unchecked; it is NULL outside a mission).
- `GenerateLightList` returns the list (the ELF returns the list's first word; LoadWorld ignores it).
- `CTextureFX::ScrollTexture` takes its frame byte from `zVid.frameNumber` (DWARF +0x10). `CWind::Tick` scales
  the vector with four multiplies (sceVu0ScaleVector in the ELF). The band object destructors free their vector
  with a swap; `CBBox::Normalize` (inline) is a file-local helper.
- Layouts without DWARF (names invented): `CTextureFX`, `CRipple`, the `RTPool` template, `CLensFlare`'s
  members, `_zanim_cmd_wind`.
- `DismemberWorldModel` still keeps the emptied "worldmodel" (it stays listed in its asset library).

## Not written / next
- The shadow / light-map chain, kept unwritten together because the render side is unwritten: zNode
  `CWorld::AddShadow` 0x22f9f0, `AddLightMap` 0x22fb20, `CRenderMap` ctor 0x22bc30 / dtor 0x22bba0 /
  `Update` 0x22b310 (placeholder body), the world ctor's four shadow textures (0x2303c8), `Initalize`'s shadow
  handle, `CWorld::AddChild`'s render maps (0x22f7c8). Writing `AddLightMap` alone would put light maps in
  `CVisual::m_lightMapList` and reach the empty `VuLightMap`. Needs zVisual: `VuLightMap` 0x30ba40,
  `VuShadowMap` 0x30b860; zTexture: `LoadGS` 0x2f9510, `CTexture::CopyTextureSelect`; zRender:
  `RenderNodeShadow` 0x242b70, `RenderMeshShadow` 0x242920. The flashlight (`CZKit`, zSeal) also leaves its
  light map unmade.
- Needs zGame: `CGame::StopEngine` (stub) would call `CRipple::Uninit` / `CTextureFX::Uninit`.
- Written, not reached in m8: the WIND command, `GetClosestNode`, `SetBlendMode`, `CLensFlare`,
  `UpdateBBoxFromDI`, `DeleteLandmark`, the light-map node functions, facade 2.

## Test hook
`port/test-hooks/znode/` (`hook_znode.cpp` + `build.sh`, with `../state/hook_state.cpp`): census after
LoadWorld (bands, texture effects, landmarks, no-far-clip nodes, lights), a 150-frame trace (wind, the scrolling
effect's first UV, DrawLOD calls / hidden, frame time), `-DZN_NOLOD` (DrawLOD always draws: the "before"),
`-DZN_CAM=<frame>` (test camera on the scrolling computer screen, four sides).
