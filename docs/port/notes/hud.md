# boot-hud notes (2026-11-07, socom-port-hud)

Scratch for the in-game HUD (CHUD and its C2D elements). Untracked.

## Tools (this folder)
Copied from boot-spawn (paths fixed): dx.ps1, dis.sh/disx.py, sym.py, xref.py, dw.py, status.py, ctree.py,
lay.py/laycheck.sh/layall.sh, fake.sh, hookai.sh, cc.sh/ccs.sh, grepasm.sh. New:
- `edits/splice_tail.py <file> <marker> <new.txt> [<end-marker>]`: replace a file from a fence marker (to the
  end or another marker) with an edit file; keeps CRLF/LF. `edits/*_new.txt` = the bodies written.
- `nmgrep.sh <build> <regex>`: GCC-mangled names in the build's game library (for --wrap lists).
- `hookhud.sh <build> <pad>` + `hook_hud.cpp` + `hookwraps.txt`: TEST HOOK, wraps the non-void stubs the HUD
  used to reach in other workers' files. Not needed any more (see "Deviations"); kept for later tests.
- Builds: `boot-hud` (default), `boot-hud-fake` (pad script below, no wraps), `boot-hud-hook` (pad + wraps).
  Pad: `60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,170:DOWN,185:CROSS,560:RX=0+45,760:START`;
  HUD Init ~49 s, START (pause menu) ~63 s.

## Screenshots
- f1-58.png = screenshots/2026-11-07_0153_m8-hud-over-world-compass-reticule-boxes.png (default code, all
  characters): HUD over the textured world: compass (compass_lo.tif turned to the heading), sidearm reticule
  (circle + 4 floating ticks), weapon box with the fire-mode bullets, team box with 4 health dots, the weapon
  name string "00" at 150,150 (no weapon loaded).
- f1-66.png = ..._m8-hud-pause-menu-letterbox.png: START pause menu (RESUME pulsing, ABORT, INVERT PITCH: OFF,
  REPLAY, AUTO AIM: ON) over the dark background, letterbox bars in.
- f1-20.png = ..._menu-still-boots-hud-build.png: title menu.
- h1-*.png: before the z-test fix (HUD hidden behind the world); h2-57: z-test fixed, reticule flips missing.

## How the HUD draws (from the asm)
CCoreState::Tick: StatusLine, zVid_ZTestOff (REF 5 -> ztest_off_vif: TEST 0, ZMSK), CHUD::Tick, DrawPhase(12)
and DrawPhase(14) between the texture-buffer FIFO_Signals (m_phase[0] / m_phase[2]; m_phase[1] = HUDSET2 is
never drawn), MapCompass::Draw, CFlashFXVector Tick (unless paused) / Draw, CZPauseTest::Draw, zVid_ZTestOn.
CHUD::Add2D(c, -1): the first textured asset library's render phase 12/13/14 -> 0/1/2, else 2 (strings).
Bitmaps draw through a stack CBatchRelocator (textures are resident in the HUD buffers); C2DPoly kicks its
TRIANGLE straight into the MFIFO. gopt.doRadar is 0 in the ELF's defaults, so the compass-mode radar
(CZNewHudMap) neither ticks nor draws: only the full-screen map (SELECT) uses it.

## ELF quirks kept
C2DBitmap/C2DPoly/C2DBitmapPoly::GetAssetLibs add the library only when the search result is a NULL pointer
(a list never allocated); C2DPoly::Load sets vertices only with a texture; Rotate_Zaxis centre
(a-b)/2+max(a,b); zVid_ZTestOnWriteSet loads zon_writeon_dmaref in both branches; DrawPhase no range test;
BitmapReticule::Draw with type -1 reads m_rettype through m_reticuleTex[-1]; UpdateAccuracy indexes
m_floatingreticule[type] past the array for types 4-8; CHUD::Tick's byte compare of the item id (< 400);
CLetterBox leaves m_slidedir unset; PoseBitmap first loads its text at the unset m_textposx/y; SetOpacity
gives the order texts the raw opacity; CTeamNames::Tick test-and-clear of m_order_flag; ZoomIn prints into
ZoomOut's zoomtext (port: own buffer).

## Deviations (port) to undo when the owners write these
Not called / inlined because their bodies are unwritten non-void stubs (STOP): CZKit::GetCurItem (inlined:
m_item[m_selected_item]); OrdersMenu::HandlePad (not called); CZWeapon::TimerCleared/TimerRegistered (their
static flags read); CZSealBody::GetReticuleSeal (NULL); CSealUnit::GetUnitByTeam (NULL, no units).
Declared void in zseal.h/zfts.h where the ELF returns a value (calls kept, result paths not taken):
CSealCtrl::UpdateHudWeapon, CZKit::WeaponInfoChanged, CZKit::CurReticuleTypeChanged, CZSealBody::StanceChanged,
CZSealBody::GetHudHitFlag, CMission::GetGameTime. CBody::m_state is protected (UpdateAccuracy's state 9
term left out). CPnt3D::Normalize() is void (MapCompass computes the length). zon_writeon_dmaref has no port
definition (built inline). C2DLine::SetTrans missing (CZNewHudMap ctor).

## Mapped, not written
CZActionBitmap Init/HudTick + CActionTxtrMachine (action icons near ladders/pickups; SP-reachable but needs
ActionAvailableMask/ActionCommand/SampleActionAvailable), CWeaponSel/CInGameWeaponSel (weapon menu),
SetupAmmoCount/SetupFiremode (with an item), SetGBarVal (throwables), CZNewHudMap full-screen map
(InitMap, RefreshBackground, CalcNewMatrix, Draw body, TickFullScreenMap, SwitchMapToFullScreen) +
CZPlayerMapItem + CZLineMap + CZObjectiveList, CLensFlareSaturate (LoadRdr/Init/PreDITick/Tick), CFlashFX
(flashbangs, CHUD::Flash), StatusLine's debug readouts (gopt flags off), CZHudMissionCams PlayCamera /
CleanupCamera, multiplayer: score popup box, radio bitmaps, team mate names, piggy-back texts.
