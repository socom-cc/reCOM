# boot-mission notes (2026-11-06)

Scratch for the mission-load stage of the functional port. Nothing here is tracked.

## Tools in this folder
- `dx.ps1 <start> [end|+len]` - annotated disassembly of support/socom.elf with the ps2dev
  objdump (`dis.sh`, `-m mips:5900`) piped through `disx.py` (lui/addiu, `$gp`-relative symbols
  and strings). End defaults to the symbol size. Fast and offline; Ghidra not needed for asm.
- `status.py <mangled>... | -f <asmfile>` - port status of functions (skeleton marker, body lines)
  - `-f` lists every `jal` callee of a disassembly file. Use it to size a call tree.
- `xref.py 0xADDR` - `jal` callers in the ELF. `sym.py`, `dw.py` (DWARF layouts), `rdr.py` as before.
- `vu.sh` - dvp-objdump disassembles the VU1 microcode: `dvp-objdump -b binary -m dvp:vu -D`.
- `boot.ps1 -Name x -Seconds N -Build <dir> [-Shots "a,b"]`, `fake.sh <dir> "<read>:<BTN>,..."`.
- Briefing + START script: `fake.sh boot-mission-fake "60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS"`
  (PLAY GAME, then 5x DOWN from OVERVIEW to the START/deploy button, CROSS -> LoadMission).
  Briefing is up ~23 s, LOAD_SCREEN ~33 s, world m8 loaded ~44 s.
- Heredocs through the Bash tool turn `\\` into `\`: python edits writing `'\0'` produced raw NUL
  bytes (`fixnul.py <file>` repairs `'<NUL>'` literals). Use the Edit tool for C text with escapes.

## Screenshots
- `tty1-48.png` - Mission Briefing with the teletype overview typed out (cursor block at the end).
- `load4-42.png` - load screen (black: CLoadMenu::PrepControls not written, background LittleBlack).

## Mission load sequence (single player, from the asm) and status
1. Briefing ONSTART `CallMusic`: UI_COMMAND SetMission 'm8' -> `UISetMission` 0x1d5a60 [written]:
   CMenuState Halt/RestartBackgroundMPEG [written; CGameMenu MPEG ones stay stubs],
   `database` = name, `CMission::PreOpen` 0x1f8750 [rewritten from asm]: UpdateMissionArchive
   0x1fa090 [written] (readerm.zar <- run/sp/m8), mission.rdr: LoadingScreenAssets, UiVars,
   Valves, Read, WEAPON_MODEL_POSTFIX, vehicle rdr, CreateCustomCharTypes [stubs],
   LoadMissionMapVisibilities [stub], TacMapZoom, Reverb [CSnd setters stubs], DBNAME.
2. START button (deploy_button, CROSS) -> anim LoadMission: StopAllSounds (0x8e) [written:
   CSndInstance::UIStopAllSounds 0x2ef540 + snd_StopSound shim], fade, SwitchMenu LOAD_SCREEN ->
   `theGame.Switch(&m_loadState)`.
3. `CLoadState::Init` 0x37f550 [written]: loading-screen lib ref, `new CLoadMenu` (5 CPlainBmp,
   3 CRenderableString), ldzanim.zar + dlgLoad.rdr, e3config.rdr, recoInit [written], zVid_Sync0.
   CLoadMenu::PrepControls 0x37fa30 (images Menu220/210/214/215/213, 'XXX' strings) NOT written;
   MyTick 0x37f940 written; PROGRESSBAR object spec not written.
4. `CLoadState::Tick` 0x37e940 [written, SP path]: fade in 0.5 s, then once
   `CSnd::UnloadAllSounds` [stub] and `CCoreState::Load(true)` 0x17ca90 [written]: thread
   `LoadThreadEntry` 0x17cbe0 [written] at priority 6 on load_thread_stack (main is 5; the main
   loop calls `zSysSleep` [written, alarm + SleepThread] so the loader runs).
5. Loader thread: sky colour, `CTexManager::doSetupBuffers` 0x2fa3c0 [written; buffer list below],
   `testLoad` 0x173610 [written]:
   - `LoadWorld("m8")` [existing body, runs: world 0xa625c0, camera, 17 asset libs, ~9 s,
     heap +8 MB].
   - CZWeapon::CreateProjectileList(100)/CreateMarkList [stubs: CZProjectileList, mark list],
     CreateWeaponList [written: returns true].
   - `CMission::Open` 0x1f7f50 [written, control flow]: readerm.zar, scheduler tasks (diTick,
     Mission, visual effects), CSnd::LoadSounds x10 / groups / jukebox [stubs], then
     **STOP at `CMaterialExArray::ResolveMaterialIndex` 0x21f2c0** (non-void stub; materials:
     ReadMaterials 0x21e730 1544 B, SetDefaultMaterial 0x21e4d0). After it, in order: valves
     [written], InitalizeTeamValves, CAiMaps::ReadMapSet, CreateCompassNavPoints, Particle::Open,
     ZAnimLoad, LoadObjectiveCams, LoadMissionCams, CNodeAction::Open, CreateLadderTable,
     CZWeapon::OpenDecals, InitDecalHandles, **LoadVehicles 0x1fd570** (creates every character,
     the player too), AcquireSoundHandles, CZWeapon::Open, AcquireDatabaseHandles,
     SignalSema(m_CharLoadSem), InitDatabaseHandles, CAiEvent::Open, CPickup::Open,
     CSealUnit::CreateSinglePlayerUnits 0x2d3750, RefreshTeamValves, ftsFixupAiMap per map,
     world InitDescendantsDI/Visuals, Sample_ExtractionLoc - all stubs.
   - appCamera->AttachTo(player) [NULL guard written], CSnd::m_listener, player cheat bits.
   - **testLoad returns player != NULL; NULL makes LoadThreadEntry call exit(0).**
6. Loader done (m_coreState.m_loading = false) -> CLoadState fades out 0.5 s ->
   `Switch(&m_coreState)` -> CCoreState::Init 0x17d2e0 (896 B; port body is an old unverified
   decomp) / Tick 0x17ccd0 (1496 B; port body only swaps) -> world rendering. Not reached.

### The player (next control-flow blocker)
`ftsPlayer` (0x475980) is set only by `ftsCreateSeal` 0x1fdfc0 (and NetworkPlayerCreate for MP).
Single-player path: CMission::LoadVehicles 0x1fd570 (1056 B) -> LoadVehicle 0x1fd160 (888 B;
CVehicleRdrEntry start pos/dir, CAiMaps locations, CCharacterType::GetByNameMod) ->
ftsCreateSeal (CSealCtrl/CSealCtrlAi/CSealCtrlSquirm ctors) -> CZSealBody::Create 0x2899c0 ->
PreCreateSeal 0x28a440, `new CZSealBody` ctor 0x2577d0 (5828 B; port has an unverified 119-line
body), CEntity::CreateEntity, PostCreateSeal 0x289d60 (1480 B). That is the character/body
subsystem (models, skeleton, anims, controllers): the next large write.

## 3D path (how the game builds textured triangles), from the asm
- Frame: CCoreState::Tick -> CPipe::RenderWorld 0x244780 [written] -> grid traversal ->
  RenderAtom 0x245810 (288 B) -> RenderNode 0x243730 -> RenderMesh 0x2431a0 (1420 B) ->
  RenderVisual 0x2424f0 (1060 B: LOD band, alpha sort `CPipe::CAlpha::Add`, texture list
  `CDynTexList::Add`, `CVisual::NodeSetup` 0x30c6d0 (object matrix, inverse), local lights) ->
  virtual `CVisual::Render` 0x30c990 -> `CVisual::VuUpdate` 0x30a900 (3624 B).
  Port bodies of RenderNode/RenderVisual/RenderMesh are old provisional code; RenderAtom,
  FIFO_Insert 0x246160, FIFO_Signal 0x246010/0x2460a0, CAlpha::Render 0x241d30 are stubs.
- `VuUpdate`: per mesh chain (`GetChainData` 0x30c7c0) builds a scratchpad packet
  (`zSysSprGetPacket`): `VuObjectSetup` 0x30c350 (object header: matrices/params for VU1),
  `VuBatchProgram` 0x30bda0 (1452 B: which VU1 program/state per batch; detail/shadow/light-map
  variants `VuDetailMap` 0x30bc00, `VuShadowMap` 0x30b860, `VuLightMap` 0x30ba40, decals
  `VuBatchProgram_Decals` 0x30c9c0), `VuExecuteState0` 0x30b740 (closes the header: DMA CNT +
  VIF STCYCL 1,1 + UNPACK V4-32 (FLG, TOPS-relative) + VIF MSCNT 0x15000000; flushes the saved
  texture state m_savedTS 0x511340 first), then `CSPR::Copy`/`CSPR::Kick` to the MFIFO. The
  vertex data stays in the model buffers (models.zar, hooked by LoadWorld) and is pulled by DMA
  REF tags; texture selects come from `CVisual::m_dmaRefVu` (REF + STCYCL + UNPACK to VU1, see
  boot-2d/GS_NOTES.md). All Vu* helpers are stubs in the port.
- **The triangles are made by VU1 microcode**: transform, lighting (`_$VU1_INITLIGHT_LOOP`,
  `_$VU1_COLORFLOAT_LOOP`), clipping (`_$VU1_TRI_CLIPPER`, `_$VU1_LINE_CLIPPER`), XGKICK to the
  GS. `vu1_CodeSegment1` 0x4272e0: DMA END qwc 0x3bb, VIF MPG chunks, 15264 bytes of code
  (~1908 instruction pairs); `vu1_DataSegment1`/.dma.202 0x42aea0: DMA END qwc 11, VIF BASE 0x1a8,
  OFFSET 0x12c, UNPACK constants. `zRndrInit` 0x241850 (600 B, port stub) fills a buffer with
  0xcdcdcdcd, FlushCache, `sceDmaSend(VIF1, 0x42aea0)` + sync (and the code segment).
  The port has no microcode: nothing 3D can draw until it exists in source.
  Feasibility checked: ps2dev `dvp-objdump -m dvp:vu` disassembles it (vu.sh), so it can be
  reconstructed as dvp-as source and verified byte-for-byte; it has no stage-4 source owner
  (`progress find vu1_CodeSegment1` shows only the symbol) - needs an ownership decision first.

## GS texture buffers (doSetupBuffers 0x2fa3c0)
dyntex.rdr `boundaries` x -> P0 = x, P1 = x + (1-x)/2, P2 = P0 + (P1-P0)/2, P3 = P1 + (1-P1)/2.
Buffers (name: range -> TexPhase slot): TexShadow:A [0,P0) -> [15][0]; TexHUD0/1:B1 [P0,P1),
B2 [P1,1) -> [12|13][0|1]; TexHUDSmall:A [0,P0) -> [14][0]; TexCommonCS:B1/B2 -> [2][0|1];
TexAlpha:B1/B2 -> [11][0|1]; TexWorld:B [P0,1) -> [0][0]; TexCustomCS:0..2 [0,0.001) -> [16][0..2].
They are appended after the UI's buffers (m_texmanager[0] stays the UI buffer).

## Written this session (see the report for the full list)
TELETYPE (CTtySpec, CTeleType), UI commands, C2DString::NewLine / virtual SetString,
CBatchRelocator (was corrupting memory), CGSTexBuffer::Setup/RelocateAll, doSetupBuffers,
zSysSleep, the load state, the loader thread, testLoad, PreOpen, Open.

## Known gaps on the executed path (not faked)
- Sounds: all CSnd loading/playing stubs (offline by decision); CTeleType guards m_sound.
- CLoadMenu::PrepControls, PROGRESSBAR spec: load screen draws nothing.
- CZWeapon projectile/mark lists; CZWeapon::m_pMarklist is not declared.
- CMission m_objanchor_vec (+0x98) is not declared (Open's reserve(16) skipped).
- CEntity::m_list first word passed to CAiEvent/CPickup::Open taken as size() (port: guess).
