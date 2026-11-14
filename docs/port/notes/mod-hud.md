# boot-mod-hud notes (2026-11-14, socom-port-mod-hud): the unwritten part of the in-game HUD

Scratch `build/port/boot-mod-hud/` (untracked: NOTES.md, mine.txt, asm dumps, logs, screenshots). Changed files:
`mine.txt` (`src/Apps/FTS/hud/*` in place, the small in-place edits outside it listed below, the new test hook
`port/test-hooks/hudmp/`, its row in `port/test-hooks/README.md`, and this note). No edit files.

## State
- DONE. `survey.py Apps/FTS/hud`: 0 stubs (was 47 / 37,044 B); written 172,228 B. The `port: not written`
  placeholders inside written functions are written too, except StatusLine's debug readouts (below).
- What a player sees in single-player m8 did not change much: almost all of the unwritten part is network-only
  (the respawn loadout menu, floating team-mate names, the SELECT score box, the radio icons, the client count,
  the spectator / dead-player HUD) or data m8 does not have (`lensflare.rdr`: the lens-flare saturation reads it
  and stays off in m8). Single-player changes: `~CHUD` and the member destructors run as the ELF does at every
  mission exit, `~MapCompass` frees the nav-point buffer, placed explosives (C4 / claymores / satchels from
  `CZWeapon::m_pProjectilelist`) get map icons when the HUD weapon changes (written; no run placed one), and
  `hudTurnOffScorePopup` runs on a replay.
- The task brief expected the in-game weapon selector in m8: in the ELF `CHUD::Tick` runs
  `CInGameWeaponSel::HudTick` only when `theNetwork.m_bNetwork` and the camera's seal is the dead player (the
  "Press the R2 button to select weapons for the next round" respawn menu); the single-player R2 menu is
  `CWeaponSel` (written earlier, `weaponsel.md`). Both are shown working below.

## Survey (HEAD 0206141b; ELF callers with `xref.py`)
| element | functions | caller / trigger | m8 offline |
| --- | --- | --- | --- |
| HUD teardown | `~CHUD` 0x3bb420 (body: `m_actionbitmap.UnInit`, `theHUD = 0`; the rest member dtors), `~MapCompass` 0x3cbd80, `~CZHudMissionCams` 0x4042c0, `~CZObjectiveList` 0x3bf730, `~CFlashFX` 0x402f60, `COverlayLine` 0x3c6d60 / 0x3c6cf0 | `ReleaseHUD` (mission exit), `__sinit_hud_newhudmap.cpp` | yes |
| lens-flare saturation | `CLensFlareSaturate` ctor 0x3be4a0, `Init` 0x3bdba0, `LoadRdr` 0x3bdcc0, `PreDITick` 0x3bdb50, `Tick` 0x3bd640 | `CHUD::Init` / `PreDITick` / `PostDITick` | runs; m8 has no `lensflare.rdr` (inactive) |
| map explosives | `CZClaymoreMapItem` 0x3c2fd0..0x3c33c0, `CZMPBombMapItem` 0x3c6dc0..0x3c7170, `CZNewHudMap::UpdateExplosives` 0x3c3580 | `CHUD::Tick` when `UpdateHudWeapon` | claymore items: with a placed explosive; bomb: network |
| respawn loadout menu | `CInGameWeaponSel`, 30 functions 0x3f8000..0x3fd030 (21 KB) | ctor / `Init` / `UnInit` every mission; `HudTick` network + dead | Init / UnInit only |
| team-mate names | `CTeamMateNames::Tick` 0x3de6a0 | `CHUD::Tick` (network) | no |
| score box | hud_scorepopup.cpp (`SetupTeam` 0x421140, `AddRow` 0x421510, `Draw` 0x421760, `SetupBackgroundBox` 0x421920, `hudTurnOffScorePopup` 0x421d40, `GetTeamMembers` 0x422140, the SELECT part of `hudTickScorePopup` 0x421ee0) | SELECT in a network game; `ReInit_Uninit` | TurnOff only |
| radio icons | `CZStaticRadioBitmap::HudTick` 0x3d5644, `CZDynamicRadioBitmap::HudTick` 0x3d5394 parts | `CHUD::Tick` (network) | no |
| client count / dead player | `CHUD::Init` 0x3bae38, `CHUD::Tick` 0x3b9578 / 0x3b9618 / 0x3b9c7c | network | no |
| debug | `DrawTaskLine` 0x3db5f0, `GetAssetReport` 0x3db860 (empty in the ELF) | gopt debug flags | no |

## Written (ELF addresses)
- hud_main.cpp: `~CHUD` 0x3bb420; the network parts of `Init` (client count "%dm" / "%d", 0x3bae38) and `Tick`
  (spectating 0x3b9578, the dead player's own view 0x3b9618, the client count 0x3b9c7c) through a file-local
  `hud_num_connected_text`.
- hud_lensflare.cpp (whole file): `lensflare.rdr` "active", "max_angle", "light_source" (landmark or world
  child, its world position, node opacity range), "light_glare" (the full-screen bitmap: colour, max
  brightness), "lens_flare" (a model or world child made dynamic and added to the world: distance, opacity and
  scale ranges). Tick: view-cone value from the camera's -z axis and the camera -> light direction; the glare
  eases at 3/s to value x max (0 when the delayed DI ray camera -> light has hits); the flare model faces back
  along the view (yaw then pitch, `sceVu0MulMatrix`), scaled, `m_LensFlareDistance` towards the light.
- hud_ingame_weaponsel.cpp (whole file): the respawn loadout menu over `CZWeapon::m_listWeapons`;
  `CanSelectWeapon` maps 40 weapon ids to their "Enable_*" valves (0x467ad8..); Action puts a primary in loadout
  slot 0, a sidearm in slot 1, toggles equipment in slots 2..5 (`SelectEquipment`, `RePackEquipment`); SELECTED
  marks, "Selected Weapons:" list at 300,182; Inventory closes it and `UpdateCharacter` writes the loadout into
  the seal's `CCharacterType`.
- hud_teammatenames.cpp: `CTeamMateNames::Tick` (head + 3 projected with `mtxWorldToScreen`, kept on screen,
  pushed down 5 px while overlapping an earlier name, faded by `m_TimeSpentDead`).
- hud_scorepopup.cpp: the SELECT score box (nine-piece `newweapnbkrnd.tif` frame, SEALs / TERRORISTS title bars
  with the team score through `CZNetGame::GetE3ScoreTeam00/08`, FRAGS / DEATHS per member), `hudTurnOffScorePopup`.
- hud_claymoremapitem.cpp, hud_bombmapitem.cpp (whole files; DWARF members added in hud.h), hud_newhudmap.cpp
  (`UpdateExplosives`, `COverlayLine`), hud_mapcompass.cpp (`~MapCompass`), hud_actionbitmap.cpp (radio icons),
  hud_devtext.cpp (`DrawTaskLine`, `GetAssetReport`), hud_missioncams.cpp / hud_objectives.cpp / hud_fader.cpp
  (member-only destructors).

## Outside the HUD (small in-place edits, free at HEAD)
- zNode/node_world.cpp: `CWorld::FindLandmark` 0x22ebf0 (was an empty non-void stub; `LoadRdr` calls it).
- zNetwork/znet.h: inline `CZNetGame::GetE3ScoreTeam00` 0x4220c0 / `GetE3ScoreTeam08` 0x4220b0 (emitted in
  hud_scorepopup.cpp's unit, the score box's pointer-to-member arguments); `CZStaticRadioBitmap` /
  `CZDynamicRadioBitmap` friends of `CZNetVoice` (the radio icons read its channel and talk flags).

## Results
- hm1 (`port/test-hooks/hudmp/build.sh hm1 pad_idle.txt -DSOCOM_HOOK_MISSIONS=1 -DSOCOM_HOOK_PLAY_AT=999999
  -DSOCOM_HOOK_LENSCAM`, 240 s; the state hook skips the intro movie with CROSS and the briefing cameras with X):
  in the mission from 70 s to the end of the run, no STOP, heap in use 22.05-22.09 MB from 78 s on.
  `LENSFLARE: no lensflare.rdr` (m8 has none: the effect stays inactive, as in the ELF).
  The respawn loadout menu opened from the hook (59 weapons listed; Action = CROSS, Inventory = R2): states
  1 -> 2 -> 3 (background column, arrows, "MARK 23", "12/12", "2 MAGS"); DOWN, DOWN scroll to Double Ammo Load,
  C4 ("4/4"); Action on C4 takes it out of the loadout (it came from the character), DOWN to Satchel Charge,
  Action adds it (SELECTED marks, "Selected Weapons:" list M4A1 SD, P9S, Mark141, M67, Satchel Charge); UP;
  R2 closes it (6 -> 7 -> 0) and writes the 6 loadout entries into the player's character.
  The floating team-mate names (ticked from the hook) follow the named seals on screen (2 at a time, pushed
  apart, a dead one fading 100 -> 27 over its first 5 s dead).
- zr1 (`port/test-hooks/state/build.sh zr1 pad_idle.txt -DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8`, 720 s; seven
  returns fitted in the run): in use at the returns 17,209,396 then 17,209,492 bytes six times (flat; 4.3 KB less
  than mod-zui's 17,213,8xx), largest free block 6.24 / 3.64 MB as before; the only failed allocations are
  `zsys_FullAllocAndFree`'s probes; no STOP. Every return runs `~CHUD` and the written member destructors.
- hdef1 (`default.sh`): links; boots to the main menu (PLAY GAME / OPTIONS) at 40 s.
- Screenshots (untracked): build/port/screenshots/46-hud/ (the loadout menu over m8 with the names; the
  SELECTED satchel and the loadout list; the default build's main menu).

## ELF quirks kept
- `~CHUD` clears `theHUD` before the members are destroyed. `CLensFlareSaturate::Tick` stores the glare
  brightness before clamping it; the flare model and the DI hit count are used unchecked.
- `CInGameWeaponSel`: `OnOpen`'s slot-1 highlight is 1 px wider than every other placement; `OnScrollDown`
  loads the incoming icon without switching it on; both scrolls reload slot 1's highlight with slot 0's
  texture (as `CWeaponSel`); `PlaceWeaponText` returns at the first loadout id with no weapon (the rest of
  the list keeps its old text); `CanSelectWeapon` / `SelectWeapon` / `UpdateCharacter` do not NULL-test the
  list entry or the owner; `AfterClose` holds TRIANGLE down without testing the pad; `GetPrevItem` /
  `GetNextItem` recurse (forever when nothing can be selected) and fetch a name they drop.
- `CTeamMateNames::Tick` tests the right edge with the half length added to the left edge; a name whose
  seal has team bit 0x20000 keeps the old text; team membership is bit 0 of `m_team` (in the single-player test run the
  names showed over Iron Brotherhood terrorists, not over the SEAL team).
- Score box: a member list sorted with the ELF comparison (scores decide only when the current pick is alive
  and the other dead). `CZStaticRadioBitmap::HudTick` masks the channel with 3 and then tests 4 (the
  dead-zone icon is never shown). `CZMPBombMapItem::Tick` tests `m_node` only for the demolition check.
- `CZClaymoreMapItem::Tick` NULL-tests the projectile only for `WasDetonated`.

## Port deviations
- `LoadRdr` returns when `lensflare.rdr` is missing (the ELF goes on to `zrdr_findtag(NULL, ...)`), and a tag
  with no value reads as no string (the ELF reads the type of a NULL value); `Tick` NULL-tests `m_LightNode`.
- `DrawTaskLine`: the points' z / w are 0 (the ELF leaves them unset).
- File-local helpers for inlined code: `lf_tagstring` (hud_lensflare.cpp), `ClaymorePlace` / `BombPlace`,
  `IgwsLoadHighlight` / `IgwsPlaceSlot` (hud_ingame_weaponsel.cpp), `hud_num_connected_text` (hud_main.cpp,
  writes `tempstr$3060`'s text into its own 32-byte buffer; the ELF buffer's size is unknown). The inlined
  `GetPrevItem` / `GetNextItem` calls are written as calls.
- `SetupBackgroundBox` has a forward declaration in its anonymous namespace (hudTickScorePopup calls it first).
- The stale `CInGameWeaponSel` declarations (`HudTick(f32)`, `Init(CWorld*)`, `SelectEquipment()`, a const
  `bool CanSelectWeapon`) were removed from hud.h.

## Not written / next
- `CHUD::StatusLine`'s debug readouts (0x3d98a8 on, ~6 KB: timing, small status, asset, task and render
  reports and their SELECT+SQUARE / SELECT+TRIANGLE toggles): gopt's debug flags are all off in the ELF's
  defaults; `DrawTaskLine` (the task report's bars) is written.
- Network-only code is written from the ELF and untested (no network game offline); the lens flare needs a
  mission with `lensflare.rdr`.
