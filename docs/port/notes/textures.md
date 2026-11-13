# boot-textures notes (2026-11-06, socom-port-textures)

Scratch for world textures and characters. Untracked. Tools copied from boot-gameloop (paths fixed):
dx.ps1/dis.sh/disx.py, sym.py, xref.py, dw.py, status.py, a2l.sh, pdis.sh, grepasm.sh, multi_replace.py,
fake.sh, hook.sh, lg.sh. `edits/*.txt` = multi_replace edit files used.

## Builds
- `boot-textures` (default, no hooks): menus boot (d1.png), no TLB/STOP.
- `boot-textures-hook`: fake pad (m8 START script) + `hook_spawn.cpp` (TEST HOOK, scratch only, built with
  `-fno-access-control`). Wraps: CameraZoom::AttachSeal (dumps GS buffers TEXB/TEXW/TEXL and character sets
  CHAR, moves the player to 1680/2800 only for the town view), CPipe::RenderWorld (CHARF/LIGHT every
  300/600 frames), CCharacterType::GetByNameMod (returns NULL for "m8_*" asked by CMission::LoadVehicle:
  the port runs out of heap at the ~18th of 41 vehicles, see below).

## Screenshots
- t1-62.png (= screenshots/2026-11-06_220500_m8-world-textures.png): terrain snow texture, pole wood.
- t3-64.png (= ..._222000_m8-player-character-drawn.png): real spawn (AI maps), player drawn, black.
- t4-64.png (= ..._222700_m8-textured-world-and-lit-seal.png): buildings textured (planks, stone chimney,
  "HOSLER MINING CO." sign), SEAL textured and lit (bind pose: anims not mine).

## Root causes (all from the asm)
1. World buffer never filled: LoadWorld's texture section (0x172c48-0x17324c, 0x1733d0) missing and
   CGSTexBuffer::Add(CAssetLib*,bool) 0x2fb420 empty, so the per-frame world upload (CCoreState::Tick
   FIFO_Signal) sent nothing; selects pointed at stale GS memory (red/blue checker).
2. CSaveLoad::LoadTextures_PS2 0x22aa70 fetched "renderphase" and dropped it: every library was phase 0,
   all 390 textures went to TexWorld:B (9659 blocks for 3887) and the buildings' were skipped.
3. Characters: CWorld::AddTextureAssetCharacter* / CTextureAssetCharacters ctor+TestFOV /
   CNode::FindMeshTextures stubs -> no character sets -> RenderWorld never renders characters.
   CAssetList::FindLib(const char*) second loop compared the whole path ("clib" never matched).
4. Black characters: CWorld::Update 0x22f2e0 empty: the global light normals/colours never reached the
   camera's VU frame packet (VU 16-23); libvu0 sceVu0NormalLightMatrix/LightColorMatrix/TransposeMatrix
   missing from port/compat.

## Facts
- Buffers: lib -> phase per jump table 0x448510: 0/1/14 one buffer; 2/11/12/13 both slots; 3-10/16 the
  three TexCustomCS (overflow check off); 15 none; fonts -> world, HUDSmall, both HUD1 (no Hookup for HUD1).
- renderphase 3..10 -> 16 at load. m8 libs: m8/effects/ui/uisk/junkyard 0, alpha_fx 11, hudweaps 12,
  hud 14, weapons 2 (CHARSETCOMMON), clib 16, flib 2, font 1.
- A character node with a mesh using only part of its library gets its own set and GS buffer
  "Tex<node name>" over [P0,P1) holding the mesh's textures + m_TextureCharacterCommon (the light map).
- CWorld: m_TextureAssetCharacters +0x6b9c, m_TextureCharacterCommon +0x6ba8, m_TextureDecals +0x6bb4.
- VU frame packet: mtxLightNormal = transpose of rows normalize(-dir_i) + (0,0,0,1); mtxLightColor rows
  col0..2, ambient. m8: dir0 (0.47,-0.3,0.47), col0 0.67, col1 0.18, ambient 0.12.

## Next blockers
- Heap: the port runs out at the ~18th of 41 vehicles (brk 0x1fd1000, heap end 0x1fdf000). The ELF heap is
  ~25.6 MB (image end 0x5e7f00, 512 KB stack) vs the port's 28.2 MB, yet menu-time use is ~22 MB:
  CMenuState::UnInit 0x378cd0 (220 B: delete menu, ReleaseLibRef(g_pSkbLib), UnloadTheWorld 0x1728e0,
  FlushHistory, zUISchedulerClear, DestroyBuffers, CloseZAR) and CLoadState::UnInit 0x37e5a0 are empty,
  so the menu stays resident. Same cause keeps //ui/assetlib/ui, uisk, //ui/junkyard (phase 0) in
  TexWorld:B (176 textures, 129 fit; the world's own fit because they come first).
- Landmarks never collected: GenerateLandmarkList 0x22f090 / LandmarkList_Search 0x22f1a0 /
  AddLandmark 0x22ecd0 / RemoveFromParent 0x2278a0 (parent's virtual DeleteChild: CWorld 0x22f530 removes
  render maps, grid entry, Release()s; CNode 0x227650). Port DeleteChild declarations disagree
  (CNode non-virtual s32, CWorld virtual short stub) - needs a decision before landmarks.
- CRenderMap ctor / shadows, CAlpha::Render, particles: not needed for the above.
