# boot-player3 notes (2026-11-06)

Scratch for the player-creation tail and mission start after boot-player2. Untracked.

## Tools (this folder)
Copied from boot-player2 (paths fixed): dx.ps1, dis.sh/disx.py, sym.py, xref.py, dw.py, status.py,
lay.py/laycheck.sh/layall.sh, multi_replace.py, a2l.sh, pdis.sh, grepasm.sh, fake.sh, hook.sh/hook_clone.c
(the Clone hook is obsolete: render2 fixed CNode::GetMesh). New:
- `pnm.sh <build> <a,b,c>`: port ELF symbols (comma-separated patterns; `|` breaks through wsl.exe).
- `pword.sh <build> <addr> <n>`: port ELF words, symbolized (vtable dumps).
- `hdr*.py`: one-off header string replacements (assert exactly one match; keep CRLF).
- Run WSL scripts from PowerShell (`wsl.exe -d Ubuntu -- bash /mnt/c/...`); Git Bash mangles paths.
  Bash heredocs with quotes break the Bash tool: write edit files with the Write tool.
- Boots: `build/port/tools/pcsx2-boot.ps1` only. Twice it reported "focus kept: False" (PCSX2 took
  focus once and the run died at ~4 s); retry once if the log stops early.
- Builds: plain `boot-player3`, fake pad `boot-player3-fake` (script below), hook `boot-player3-hook`.
  Pad script: `60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS`; world m8 at ~47 s.

## Load path now (fake pad, plain build, f3.log)
CZSealBody ctor -> AnimSetup -> BindAnimSet -> PushBlend [written] ... ctor tail [SetLookDir chain,
CLook/CBlink, kit ctor, AddWeapon, AddItem, UpdateAimParams written] -> PostCreateSeal [written] ->
LoadVehicle TeleportTo (UpdateGrid fixed) -> all 41 vehicles (player + AI) -> testLoad ->
CCoreState::Init -> **STOP CCoreState::Tick (st_core.cpp:166, placeholder body)**. Nothing drawn.

## Next: CCoreState::Tick 0x17ccd0 (asm_coretick.txt)
CInput::Tick, recoTick (28 B, recoInited), CHUD::PreDITick (-> m_LensFlareFade +0x14460),
recoIsRecognizing, CHUD::PauseGame 0x3ba040 (CSealCtrl::GetMenuState of appCamera's entity, a byte
in m_pausetest +0x358, theNetwork), zTaskScheduler.Tick (entity tasks: not yet seen), appCamera
vtable +8 Tick (camera owner), CameraZoom::Tick 0x31fcf0, CCamera::Update, CHUD::PostDITick, zSysFifoEnd,
zVid_Swap (m_skip_swap), CHUD::GetAssetReport (doHud), CBench::Reset, FP-mode SetActive around
CPipe::RenderWorld, then the HUD draw phases. CBench timing statics (preTask, postTask,
postAppCamTick, postCamUpdate, inputTime, swapTime, drawTime, postHUDTick, postCompassTick, twoDTime)
and OurGameName are not declared in the port yet; RCNT0 is read as *T0_COUNT elsewhere.

## Mapped, not written (subsystems)
- AI: CreateAiEvent (CAiEvent::Acquire 0x17f9f0 pool + Create), CSealCtrl::Initalize 0x288050
  (CAiVisMap ctor/RegisterDynamicVisMap, SetSnakePathUpdate -> CAiPath::SetSnakeLength), CSealCtrlAi
  ctor/InitAiBrain, UpdateAiMapLoc.
- Collision DI: AddDIPolys (SetDIBBox/SetMaterial/ResolveMaterialIndex), CDIBBox::SetCDIBBox (3356 B).
- Shadows: CWorld::AddShadow -> CRenderMap (render). Clutter: CClutterAnimManager::RegisterEffector.
- Kit: CZKit::Init (sounds, CLightMap flashlight), SetItem/GetItemByIndex/SetItemAmmo (no weapons
  load: GetWeaponId still NONE).

## ELF facts found
- m_weapons holds the weapon CZBodyPart* by SEAL_ITEM (the ctor then clears their m_node).
- CObjAnims = vector of 8-byte {part, gear} entries; CZKit::m_items_avail holds CNode*.
- CSealAnim: one malloc'd 8464-byte pose stack (16-byte header, 8 frames x 32 part poses).
- CNode::UpdateGrid tests the PARENT's type (6) and uses CWorld::m_grid (+0x670).
- MW bitfields are LSB-first (m_am_stunned @4 = bit 4 of +0xf5c).
