# boot-loadscreen notes (2026-11-06)

Scratch for the mission loading screen (functional port). Nothing here is tracked.

## Builds and boots
- Default: `SOCOM_PORT_BUILD=~/.cache/socom/boot-loadscreen port/tools/link.sh`.
- Fake pad: `fake.sh boot-loadscreen-fake "60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS"`.
  Timing in this run: briefing ~24 s, LOAD_SCREEN 36.5 s, world loaded ~47 s, then
  player3's seal_kit.cpp:679 STOP.
- Boot: `build/port/tools/pcsx2-boot.ps1 -Elf <scratch>\socom_port.elf -Log ... -Shots "37,40,44"`.
- The disc ZARs were read into the session temp scratchpad, not into the repo:
  `boot-menu/iso.py <bin> get RUN/LDZANIM.ZAR`, `RUN/SP/M8/READERM.ZAR`.
  `boot-input/rdr.py <zar> mission.rdr` dumps them; `boot-menu/seq.py <zar> dlgLoad.rdr <anim>`.
- `dlgLoad.txt` holds the design, `dlgLoad_seq.txt` the compiled ONSTART anims, and `asm_*.txt` the disassemblies.

## Screenshots
- `load1-37.png`: fading in. Title, description and the blueprint background are up, and the fill has started.
- `load1-40.png`: the fill is about 1/5 across, with the cursor streak at its edge and LOADING..... showing.
- `load1-44.png`: the fill is about 2/5 across, with LOADING... showing.
- `default1.png`: the default build reaches the main menu.

## How the load screen works (from the asm)
- dlgLoad.rdr (UI ZAR) sets up LittleBlack background, LoadingBackground IMAGE (UIVAR
  LoadingScreenBackground), load_progress_filling PROGRESSBAR (FILENAME_IS_UIVAR
  load_progress_texture, UIVAR Load_progress, LEADING_EDGE_NODE LeadingEdge), title and
  description TEXT (UIVARs mission_title, mission_description), LoadingText, LeadingEdge,
  Leader_follow and RedDown (loading_cursor.tif, a child of Leader_follow).
- mission.rdr UiVars for m8 (CMission::PreOpen reads them during the briefing):
  load_progress_texture ld_m8_prog.tif, LoadingScreenBackground ld_m8_back.tif,
  mission_title "GHOST TOWN", mission_description "OBTAIN CRITICAL INTEL", LOAD_PROGRESS 21.
  The textures come from LoadingScreenAssets ui/assetlib/ld/ld8 (CLoadState::Init holds it).
- **Progress is a timer, not fed by the loader.** LOAD_PROGRESS is the number of seconds to
  fill. CHProgressBar::UpdateUIVar stores it as the duration, and Tick adds dT / duration up
  to 1. Nothing in the ELF writes Load_progress (the string does not appear in the ELF). Draw
  sets the GS scissor to the filled part, draws the image, resets the scissor, and moves the
  LeadingEdge node to the fill's end.
- Scripts: Leader_follow (OBJECT_TRANSLATE_STATE AT_NODE LeadingEdge, looping) puts the
  cursor at the edge. RenderStreakDwn (OBJECT_MOTION_FROM_TO, precomputed: flag 2, velocity
  in the data) moves RedDown between y -50 and 85 every 0.1 s. Load_Anim runs UI_COMMAND
  0x96 (CRenderableString Caption) and WAIT 0.2 s to cycle the LOADING dots.
- CLoadMenu draws through g_relocBatch (CGameMenu::Init(NULL, ...)). Its textures are
  uploaded once at EndBatchReloc. render2 has fixed CBatchRelocator::TakeDrawPacket in src.
- Threads: the loader is at priority 6 and the main thread at 5. CLoadState::Tick calls
  zSysSleep(1/30 s) every frame after the fade-in, so the UI frame keeps running during the
  load (the dots and the fill advance between shots).

## Remaining gaps
- CUIVarManager::CollectGarbage is not written. It needs _Refresh (zui_var), plus
  CSTable::Clear and zrdr_pack, which are stubs outside zUI.
- CUIVarManager Serialize/UnSerialize and the CSaveModule base are not written.
- CZAnimFromToAcc (accelerated motion) and CZAnimArgList::GetPnt3D (a void stub) are not
  written. The motion and translate handlers treat the argument point as absent.
- CPlainBmp has no UIVarMixin base (the port model is m_mixin_uivar), so variable changes
  don't reach CPlainBmp or CHProgressBar through UpdateDependents. Draw still re-reads string
  variables every frame.
- The PrepControls bitmaps Menu220/210 (enabled by Tick) show nothing on screen. Whether
  their textures are in the loaded libraries is unverified.
