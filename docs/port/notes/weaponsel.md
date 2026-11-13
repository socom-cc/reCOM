# boot-weaponsel notes (2026-11-07, socom-port-weaponsel)

Scratch for the armory (briefing EQUIPMENT screens) and the in-mission R2 weapon menu. Untracked.
Changed files: `mine.txt`. Edit batches: `edits/e01..e10` (`=== <fence name>` blocks, applied with `rep.py`).

## Tools here
- Copied from boot-weapons/boot-mission: sym.py, xref.py, ctree.py, fences.py, status.py, dw.py, laytool/,
  rep.py (now honours `REP_ROOT`), ccm.sh, fake.sh, dis.sh/disx.py. New: `dx.sh <hex> [len]` (bash objdump
  helper), `symsize.py`, `strref.py <regex>` (strings + lui/addiu code refs), `addrref.py`.
- `tree.sh` (working-tree copy, rsync --checksum) / `tree2.sh` (HEAD + my files: `mine_exclusive.txt` copied,
  shared files = HEAD + `shared_edits.py`), `hook.py <tree> <hooks.txt>` (trace insertions after anchor
  lines, copy only), `fakehook.sh <build> <hooks|-> "<pad>"` (`TREE=tree2.sh` for the HEAD-based tree).
- Designs: `dlg_equipment_main.txt` (armory, 11.6k lines), `dlgEquipmentSelection.txt`. Mission rdr dumps
  and the disc ZARs were read into the session scratchpad (not the repo).

## Pad scripts (fake pad, ~30 reads/s; reads continue during loading)
- Armory: `60:CROSS,130:DOWN,140:DOWN,150:DOWN,160:DOWN,175:CROSS` (EQUIPMENT; armory up ~37 s), then
  `240:DOWN,250:DOWN,270:CROSS` (KAHUNA), `300:CROSS` (PRIMARY: weapon list, MP5 SD), `390:RIGHT` (M40A1),
  `480:CROSS` (choose), `570..610:DOWN x5,630:CROSS` (START -> LOAD_SCREEN; mission ~70 s).
- R2 menu after that: `970:R2` (~75 s), `1030:DOWN`, `1090:DOWN`, `1150:R2` (equips, closes).
- Standard START path + R2: `...,170:DOWN,185:CROSS,620:R2,680:DOWN,740:R2` (mission ~55 s).

## Results (f1 = clean fake-pad build of the working tree; screenshots/15-weapon-select/)
- Armory: per-character loadout texts (CharN*Descr UI vars), 3D weapon models (MODELS section instanced
  into the menu's "ui" world) and 3D character models, fireteam/element/character selection, PRIMARY /
  SECONDARY / EQUIPMENT lists cycling the mission's Enable_* weapons, ChooseEquipment replaces the primary
  (M4A1 SD -> M40A1 "MODEL 700"), DEFAULT restores. GHOST TOWN title now shows (mission UI vars).
- Mission: `LOAD: vehicle player character UiCharType1` -> `seal kit 5 items, slot 0 M40A1`; HUD M40A1 5/5.
- R2: opens (states 0->1->2->3), shows prev/current/next icons, name, ammo "5/5", "2 MAGS", hot swap
  label, arrows; UP/DOWN scroll (4/5), R2/CROSS equips (SetCurItemByIndex) and closes (6->7->0); HUD shows
  the new item (Mark141 6/6).

## Engine bugs fixed (port)
- The valve system: `CValvePool::Acquire` returned `front()` without removing it (every pooled valve was
  one object) and never named it; `FreeName` freed pooled names and kept heap ones; `AssignName`,
  `SetName` empty; ctor stored VTYPE_NONE; `Open` set the pool's valves to value 1 and never made the name
  buffer; `Create(name, value, type)` returned NULL (mission.rdr Valves never existed). The armory's
  valve-driven scripts (UiSelectedCharacter, UiWeapon, Enable_*) could not work.
- `CSealCtrlAi::get_valve(const char*)`: missing breaks (every name read "error").
- Consequence handled: with real valves the mission scripts see the team/AI valves, so
  InitalizeTeamValves / RefreshTeamValves / DecrementTeamValves and CSealCtrlAi::Initalize (the
  "<node>_valve_alive" etc. valves, alive = 1) are written - otherwise m8's objectives (started by the
  deathcam worker's OnMissionStart change) fail the mission 5 s in ("player_valve_alive == 0",
  "Snow3_valve_alive == 0").
- `UIPlayMPEG` (non-void stub, STOP at mission start: objectives plays run/movies/0122.pss while
  ReplayMissionMusic is 0): written; the cinematic push is skipped (no MPEG player).

## ELF quirks kept
CCharacterWeapList::AddWeapon ignores its item; LoadModels stores ROTX/ROTY/ROTZ all to the first rotation;
PrepModels' USEMODELUIVAR default name ""; OnOpen reads GetSelectedItemNum before the owner NULL test;
OnScrollUp/Down reload slot 1's highlight with slot 0's texture; PlaceHotSwapLabels leaves both labels on
with old text when L1 and L2 hold the same item; AfterClose doesn't test the pad pointer; GetMaxAmmoCount
indexes m_item[fire mode - 3]; CValve::Create(NULL, ...) acquires a nameless valve; UpdateCharWeaponUiVars'
name table is a local array copied from data 0x439c30.

## Port deviations
- GetCustomCharTypeName keeps its own copy of the UiCharType1..32 table (the ELF's
  c_arrCustomCharTypeNames$2822 is shared by three functions; C++ can't share a function-local static).
- UIPlayMPEG: theGame.Push(&m_cinematicSubState) skipped (CMPEG / CCinematicState unwritten).
- SetItemPos: per-slot placement factored into a file-local `PlaceSlot` helper (the ELF repeats it).
- RefreshTeamValves: the CSpawners spawn_map entities are not counted (no list modelled).
- CSealCtrlAi::Initalize: m_mode (+0x30c) = AIM_IDLE not set (member not declared).
- CSelectedCharsItr gets an inline ctor (the ELF inlines it).

## Layout changes
CWeaponSel m_weaponnum[4], m_selectionbacktex[4] (DWARF); CGameMenu _vecModelInstances (+0x878);
CDlgDesignModel 36 bytes (no DWARF); CValvePool name-buffer fields; CSelectedCharsItr (no DWARF);
CSealCtrlAi m_valve[4] (DWARF +0x5bc, port offset differs: class only partly declared).

## Not written / next
- Armory stat bars (VOLUME/ACCURACY/...) show full: OBJECT_MOTION_FROM_TO SCALE on menu C2D nodes is not
  honoured by the UI renderer.
- "2 MAGS" and "BUTTON:L1" share a row and overlap (ELF positions; the port font is wide or the ELF font
  maps the label). CWeaponSel's slot highlight is off in state 3 (ELF: AfterOpenSecond turns them off).
- CValve::MakeCallbacks is still empty (valve callbacks never fire); CValve::Destroy, Close, Reset stubs.
- MPEG / cinematic state; CInGameWeaponSel (MP respawn menu) unwritten.
