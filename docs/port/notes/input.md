# boot-input notes (2026-11-06)

- Default build: `SOCOM_PORT_BUILD=~/.cache/socom/boot-input port/tools/link.sh`; boot with
  `boot.ps1 -Name x -Seconds 25 [-Shots "18,24,40"] [-Build boot-input-fake]`.
- Test hook build: `fake.sh boot-input-fake "60:DOWN,120:CROSS"` (configures
  -DSOCOM_PORT_FAKE_PAD; reads are counted on pad 0, the pad is read every other frame;
  dlgMenu is up from read ~0 (frame 3) and attract mode starts near read ~220).
- dlgMenu.rdr IS the demo's main menu: Demo_pane IMAGE + new_game_button (PLAY GAME ->
  UiprepMission1 -> dlgAlaskaCinematic -> dlgAlaska_mission3 briefing) and
  multiplayer_button (OPTIONS -> goto_menu dlgOptions_Menu.rdr).
- rdr.py dumps compiled zReader files out of a ZAR (array offsets are relative to the root
  array, string offsets to the table at +8).
- PCSX2 pad port 0 reaches state 6 (stable) on its own; port 1 reports 0 (disconnected).
- CMenuState SelectionSound is NULL at runtime, so PlaySelectionSound never reaches the
  unwritten CSnd::PlaySound chain.
