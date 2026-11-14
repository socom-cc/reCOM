# boot-mod-zvehicle notes (2026-11-13, socom-port-mod-zvehicle): completing the zVehicle module

Scratch `build/port/boot-mod-zvehicle/` (untracked). Changed files: `mine.txt`. No edit files.
In-place changes outside zVehicle (free at HEAD): `zai.h` (AI_PARAMS ctor declaration), `zrdr.h` /
`zrdr_main.cpp` (zrdr_findRfloat), `zseal.h` (ai::DrawLine static), `port/test-hooks/README.md` (row).

## What the module is
`zVehicle` has nothing to do with cars. The name is a leftover from earlier games on this engine, where the
player-controlled vehicles were the character controllers. Here it holds the mission's character roster:
`CVehicleRdr` (a vector of `CVehicleRdrEntry`, read from the mission's `vehicles.rdr`) where each entry defines
one character of the mission (name, display name / call sign, character type, team mask, start locations,
flags disabled / recycle / noshoot / nofade / nosnooze / debug, and `AI_PARAMS`), plus `CTurret`: scripted gun
emplacements defined in `ai_turrets.rdr` and hooked to world nodes by name prefix.

## State
- DONE (HEAD bc3a59a3 + mine.txt). `survey.py gamez/zVehicle`: 0 stubs (was 19 fences / 11140 B); 15972 B
  written.
- zv1 (`port/test-hooks/zvehicle/build.sh`, START pad, X skips the mission cameras m8bs / m8tut1): m8 from 56 s
  to the end of the log at 218 s, no STOP / exception, heap use flat at 22.03-22.05 MB from 63 s on; team and
  enemies spawn with the traced roster values (below).
- zv2 (`-DSOCOM_HOOK_TURRET -DSOCOM_HOOK_TURRET_CAM`): a test turret in m8 runs the whole turret code: 10
  targets in its list, acquires the player and Bailey (hostile teams), turns, runs its trigger and fire timer,
  fires 38 rounds (M4A1, 5.56 x 45mm); "OBJECTIVE COMPLETED: SENTRY NEUTRALIZED" at 148 s. No STOP to 200 s.
- zv3c (`pad_armory.txt`): the armory (EQUIPMENT) shows KAHUNA's 3D model and kit (M4A1 SD, P9S, C4,
  FLASHBANG, FRAG). zvdef (`default.sh`): main menu.
- Screenshots (untracked): build/port/screenshots/42-zvehicle/.

## Survey at the start (HEAD 3f054bb6): 19 stubs, 11140 B
- vehicle_main.cpp: `__ct__11CVehicleRdrFv` 0x1a38e0 (52 B). Everything else of the roster was written
  (Load, GetEntryByName, Open, Close, AI_PARAMS Merge / Parse, Randomize, the start getters).
- veh_turret.cpp: all 18 CTurret / CTurretDef / CTurretDefVector functions (11088 B). CTurret::Init(name,
  path) is called by CMission::Init (`ai_turrets.rdr`, `data/common`), LoadTurrets by CMission::LoadVehicles:
  both reached in m8. m8 has no turret: `ai_turrets.rdr` (readerc.zar) defines demo_turret, m11_50cal_turret,
  hind_50cal_turret, m20_50cal_turret, and no m8 world, model or clutter file has a node named like them
  ("turret" / "50cal" appear nowhere), so in m8 only Init / Parse / the scan / PrefixMatch run.
- Not fenced, owned by vehicle_main.cpp: `__ct__9AI_PARAMSFv` 0x1a5270.
- Callee outside the module: `zrdr_findRfloat` 0x23d6f0 (zReader stub; also used by the CTWait / CTPlay /
  CTLookAt / CTHold / CTGoto parsers, which are still stubs in zSeal).

## Root cause found: AI parameters that nobody sets were 0
The ELF's roster vector resize (0x1a3e60) builds each entry with the inline CVehicleRdrEntry ctor, which runs
`AI_PARAMS::AI_PARAMS` 0x1a5270: mask 0 and the defaults accuracy 0.8, courage 0.6, surrender 0.2, stealth 0.5,
training 0.5, visual_sens 0.8, visual_range 400, visual_fov 60, aware_decay -0.075, thip_range 25, respawn 0,
target_delay 0.75, target_discipline 0.5. The port's AI_PARAMS had no ctor, so `resize` value-initialised the
entries to 0. CMission::LoadVehicle copies the entry's AI_PARAMS into the AI and CSealCtrlAi::Init merges it
with the character type's (`Merge(own, type)`: own when own sets it, else type's when type sets it, else own):
every value neither vehicles.rdr nor the character type sets was 0 in the port.

Roster as loaded for m8 (`VEH:` trace in CVehicleRdr::Load, 41 entries): player / Hutchins / Bailey / DiMone
(Kahuna, Boomer, Jester, Spectre; arctic_A8..D8; teams 0x80000006 / 0x8000000a), 37 enemies (m8_*terror*,
m8_Kola; teams 0x40000xxx), mask 0 except Snow3 (courage -1, surrender 1), Help1 / Help2 / Wait1 / Wait2
(respawn 2 / 1 / 3 / 3). Flags: Snow3 noshoot, Leader nosnooze, 13 recycle entries.

What changed for the player (brain trace, CSealCtrlAi::Init): enemies `delay 0 ms` -> `delay 750 ms` (they no
longer fire the instant a target is visible: target_delay); not in the trace but now the ELF's: aware_decay
-0.075 (was 0: enemy awareness never decayed), thip_range 25 (was 0: rounds passing by never raised
"under fire"), training 0.5 (buddy threat weighting) and surrender 0.2, each where the character type does not set it. Range,
FOV, sensitivity, accuracy and courage come from the character types and are unchanged (enemies range 500 fov
60 sens 60% acc 20%; seals 569 / 60 / 150% / 100%).

## Written (ELF addresses)
- vehicle_main.cpp: CVehicleRdr ctor 0x1a38e0 (the vector base only); AI_PARAMS ctor 0x1a5270 (new fence,
  declaration in zai.h); a `VEH:` trace per loaded entry (SOCOM_PORT_TRACE_ON builds only).
- zrdr_main.cpp: zrdr_findRfloat 0x23d6f0 (bool: one value -> {v, 0}, two -> {min, max - min}); declared in
  zrdr.h.
- veh_turret.cpp (layouts from the asm, no DWARF; names invented, offsets in zvehicle.h):
  CTurretDef (400 B) ctor 0x37ccf0 / dtor 0x37cca0 / Parse 0x37c550 (PARTS, LIMITS YAW / PITCH in degrees,
  ACTIVATE, EFFECT, TEAM, TRIGGER up_time / dn_time, ai_params, HEALTH, WEAPON NAME / AMMO, DESTROY_ANIM);
  CTurretDefVector (vector<CTurretDef>) PrefixMatch 0x37c480; CTurret (CEntity, 784 B) Init(name, path)
  0x37c2e0, LoadTurrets 0x37c250 (landmarks, then the world), ScanForTurretDefinitionHookups 0x37b8c0 (int),
  ctor 0x37be30, Init(node, def) 0x37b9e0, _is_active 0x37b7e0, PreTick 0x37b5d0, Tick 0x37b1f0, PostTick /
  ComputeNextPosition (empty), SampleDynamics 0x37b070, Fire 0x37ae70, Rotate 0x37a9b0, AcquireTarget
  0x37a360 (with the visibility test it inlines twice), SetTarget 0x37a2a0, GetPosW 0x37cfc0 (header).
- zseal.h: `ai::DrawLine` declared static (CTurret::Tick calls it without an object; the body is a zSeal stub).

## ELF quirks kept
- Init(node, def) tests the ACTIVATE array's address, so the "healthy" default is never used.
- The view cone's FOV is stored into the turret's AI_PARAMS visual_fov in radians (from the limits), saturated
  only for the tan.
- Rotate clamps yaw and pitch by comparing sines: limits beyond +-90 degrees (demo_turret's +-179.9) clamp
  almost every direction to the limit's sine; m_aimdot is the barrel's axis dotted with the unnormalised aim
  vector (values far outside -1..1 in the trace).
- AcquireTarget's fallback looks up the target's current entity, not the remembered one; SetTarget looks up
  the old entity and ignores the result. CTurret's ctor leaves m_active and m_aimdot unset (PreTick / Rotate
  set them before Tick reads them). Init transforms the aim by a still-unit matrix. The trigger's timer is
  summed in double (MW), as the port does.
- CVehicleRdr::Load quirks are as before (team list, setup count saturated but not the loop).

## Port deviations
- CTurretDefVector derives from std::vector (MSL vector in the ELF); the inline Rfloat draw and trigger re-arm
  are file-local helpers.
- zrdr_findRfloat returns bool (the old stub was void and undeclared).

## Test hook
`port/test-hooks/zvehicle/`: X (CROSS) skips each m8 mission camera while it plays; a player trace every 600
reads. `-DSOCOM_HOOK_TURRET` puts a demo_turret (hostile to the player) on the nearest world node having a child
with a child, 300+ units away, and traces it; in zv2 that was an enemy's leg bones (lcalf / lfoot), whose
rounds most likely killed their own host (OutPatrol4, the sentry, dead at 148 s; the fire point stopped moving
then). `pad_armory.txt`: main menu -> briefing -> EQUIPMENT -> KAHUNA.

## Not written / next
- Nothing left in zVehicle. Real turrets cannot appear on the demo disc (only m8, no turret nodes).
- The zSeal task parsers that read Rfloats (CTWait / CTPlay / CTLookAt / CTHold / CTGoto::Parse) can now use
  zrdr_findRfloat.
