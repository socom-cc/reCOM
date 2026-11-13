# boot-kit notes (2026-11-13, socom-port-kit)

Scratch for the player's kit beyond rifles and frag grenades (m8). Untracked. Changed files:
`mine.txt` (= copy.txt, whole files laid over HEAD by tree.sh). No shared-file edits (shared.txt
empty). Test tree = HEAD cb07c7a + mine.

## State / next step
- DONE (HEAD cb07c7a + mine). (a) scopes / binoculars and (b) NVG already worked (no code needed);
  (c) C4, claymore + detonator and the grenade throw-power gauge written and working; (d) not
  needed (pistol draw / holster, suppressed variants work through the rifle/pistol paths; no
  laser / light attachments in the m8 kit).
- k3.log (kb.sh kit-s1 pad_k1.txt -DKIT_RUN2): armory M40A1, scope 6x/16x, pistol binoculars 9x,
  C4 put on a SNOW cliff 10 from the player ("EXPL: C4 placed ... fuse 5.0, timed"), HUD timer,
  5 s later "placed C4 detonates" -> blast 152.5 -> OutPatrol4 (12.9 away) flung and killed;
  TEST claymore + detonator: placed (PlaceClaymore anim), detonator auto-selected, R1 -> "detonator
  fires Claymore" -> OutPatrol3 killed; M67 held 5 s: gauge full (yellow), thrown, detonates.
  Mission 76 -> 232 s, no STOP, heap steady (use 22.31 MB from 140 s to the end).
- dflt.log (build_default.sh kit-dflt, no hook / fake pad): menu at 9.7 s, attract screen 58 s.
- Screens: build/port/screenshots/37-player-kit/.
- Next (not done): smoke / tear gas gameplay effect (HandleSmokeAndGas 0x2a2370, seal_env.cpp,
  needs CParticleEx volumes); claymore / MP-bomb HUD map items (UpdateExplosives 0x3c3580,
  CZClaymoreMapItem 0x3c2fd0..0x3c3450; claymores are disabled in m8); satchel action
  (HandlePlacingExlosive 0x2a94f0; no satchel site in m8); flashlight / laser designator.
- Earlier runs:
- k2.log: binoculars WORK (pistol: 1st person -> state 3, 9x, reticule 6 ret_binocs, k2-98.png);
  claymore placed (PlaceClaymore anim, "EXPL: Claymore placed ... remote"); C4 not placed because
  the hook's wall finder picked a team-mate (PERSON) -> fixed (characters ignored); the detonator was
  not in the test kit (the ELF's SetCurItemEnum only selects one the kit has) -> run k3 adds it.
  Mission to 232 s, no STOP.
- Also written: BitmapReticule::SetGBarVal 0x3cd490 / UpdateGBarColor 0x3cd320 (the grenade
  throw-power gauge; was a stub) - k3 holds R1 with the M67 for 5 s.
- hud_bitmapreticule.cpp: SetGBarVal 0x3cd490 (the type-4 grenade reticule as a power gauge:
  half bitmaps, two fill polys, two back polys) and UpdateGBarColor 0x3cd320 (grey up to 0.15,
  brown for the underhand toss, else yellow, x val).

## Tools
Copied from boot-stance / boot-grenades (paths -> boot-kit / tree-kit), plus survey.py
(boot-missionwin), zar.py (boot-menu), rdr.py (boot-weaponsel), iso.py. New:
- `kb.sh <build> <pad> [-D...]`: tree.sh + fake.sh (configure once) + hook.sh with hook_kit.cpp and
  `--wrap=_ZN15CCinematicState4TickEf` (that wrap never fires: the state's vtable is in the same
  unit; the hook instead presses CROSS every 40 reads between the census and the mission cameras,
  which skips the mission-start movie, and CROSS during the cameras).
- `hook_kit.cpp`: a step table (wait frames, op, args): zoom UP/DOWN, R1 / held R1 with full
  pressure (rdata[17]), select slot, TEST SetItem+SetItemAmmo into a slot (items the default kit
  lacks), night flag, find a wall (72 level rays, |n.y| < 0.3) and put the player facing it, put
  the nearest enemy next to the spot, camera on the last placed explosive / on a throw, traces of
  kit, zoom, reticule type, HUD mode, NVG/lens, scope poly, zoom/range text. -DKIT_RUN2 = run 2
  list; default = the survey list.
- `wepdump.py <zar tree dump> table|ammo|keys`: zweapon.zar summary.
- Pad `pad_k1.txt`: the weaponsel armory path (EQUIPMENT, KAHUNA, PRIMARY, RIGHT = M40A1, choose,
  START). The armory still works at cb07c7a: "seal kit 5 items, slot 0 M40A1".

## Survey
### What m8 offers (mission.rdr Enable_* = 1; zweapon.zar 59 weapons / 30 ammo)
- PRIMARY: MP5SD (33), M40A1 (102, remington700, zoom 1.5/6/16, bolt: ReloadAfterShot), M60E3 (91),
  SR-25 (106) and SR-25 SD (105) (zoom 1.5/8), M4A1 SD (62, zoom 1.5/2.5).
- SECONDARY: Mark 23 (2), Mark 23SD (3), P226 (6), P9S (8). All zoom 1.5 only.
- EQUIPMENT: Double Ammo Load (188), M67 frag (121), AN-M8 smoke (122), Mark141 flashbang (123),
  Satchel (152), C4 (151), HE (126). Disabled in m8: claymore, laser designator, M203s, M79/MGL.
- Default player kit: M4A1 SD, P9S, C4 x4, Mark141 x6, M67 x6. Other kit items in the zar but
  never in a kit here: Knife, Flashlight, Binoculars, Restraints, Detonator (given by a claymore).
- m8.rdr NightMission 0, LensFX_NVG (0.2 0.9 0.2), LensFX_StarlightScope (0.3 0.5 0.95).

### Status before this work (s1.log, survey list; screenshots s1-*.png)
| item | select | aim / zoom | use | effect | HUD |
| --- | --- | --- | --- | --- | --- |
| M40A1 (armory) | yes | 1st person, 6x, 16x scope (ret 5 ret_scope.tif, black outside, ZOOM: 16.0X) | shot | yes | yes |
| SR-25 / SD | yes | 8x scope | shot | yes | yes |
| M4A1 SD | yes | 2.5x: the same scope overlay (ELF: any zoom > 1.5 is reticule 5) | yes | yes | yes |
| MP5SD, M60E3 | not run (same rifle path as M4A1 SD; one zoom: 1st person -> binoculars) | | | | |
| pistols | yes | 1st person (binoculars step: run 2) | yes | yes | yes |
| NVG | night missions only | UP from 1st person = ZOOMSTATE_NVG | - | green tint, nvg lens, green weapon box, range text "13.9M" (forced night flag, s1-171.png) | yes |
| M67 / Mark141 | worked (boot-grenades, boot-fx2) | | | | |
| AN-M8 smoke | yes | throw | yes | smoke cloud anim (s1-183.png); no gameplay effect (HandleSmokeAndGas unwritten) | ammo 2/3 |
| HE | yes | throw | yes | blast radius 100, OutPatrol1/Help1 reached but shielded | yes |
| C4 | yes | - | NO: HandleFireWeapon C4 branch a placeholder (fire time 99, nothing) | - | - |
| Detonator | (test) | - | nothing (DetonateRemoteExplosives empty) | - | - |
| Satchel | not selectable (ELF isSelectableItem); placed only by a satchel action (none in m8 actions.rdr) | | test select + R1: STOP (PerformAction stub) | | |
| Double Ammo | Setup2XAmmo written (load time) | | | | |

### Missing, by ELF function (sizes)
- seal_body.cpp: PerformAction 0x272dc0 (148, S nonvoid: the STOP).
- seal_kit.cpp: HandleRemotePlaceExplosive 0x2a6ed0 (1332), SetCurItemEnum 0x2af610 (884),
  TickExplosives 0x2aa7a0 placement part, HandleFireWeapon C4 branch, DetonateRemoteExplosives
  0x2a96c0 (260), Timer_PlaceC4 0x2a9340 (20); not needed in m8: HandlePlacingExlosive 0x2a94f0
  (456, satchel action / MP bomb), TickFlashlight 0x2aa4e0 (700), TickLaserDesignator 0x2a90a0 (672),
  SetupBinocular 0x2ae4f0 (164), FetchLaseTarget.
- zwep_explosive.cpp: PlacedExplosive ctor 0x315710, dtor 0x315660, RemoteDetonate 0x315650,
  PreTick 0x315420, PostTick 0x315490 (800 together).
- zwep_projectilelist.cpp: RemoveExplosive 0x31a8c0 (136). zwep_projectile.cpp: IsInRange 0x317550 (188).
- Smoke / gas effect: CZSealBody::HandleSmokeAndGas 0x2a2370 (912, seal_env.cpp, shared).
- HUD: BitmapReticule::UpdateGBarColor 0x3cd320 (356, the grenade bar colour); the claymore /
  MP-bomb map items (hud_claymoremapitem.cpp, hud_bombmapitem.cpp).

## ELF facts (placed explosives)
- C4 is a TIMED charge in this build: HandleRemotePlaceExplosive gives it a 5 s fuse (HUD timer
  via CZWeapon::RegisterTimer for the player's team); only the claymore is remote (the
  detonator, auto-selected after placing; 10 s removal after its blast). Satchel: the mission's
  m_satcheltimer (none if < 0). MP bomb: 30 (sets theMission.m_winlosstimer).
- C4 use: PerformAction(animTypePutOnWall 65, stand) with the blend callback Timer_PlaceC4 at
  0.45 (user data &m_firetime -> 0); TickExplosives then probes 16 units level along the aim from
  the right hand (characters ignored); no hit / material 1 / INVISIBLE_DI / volumetric / liquid:
  nothing placed (the round is kept). Claymore / satchel / MP bomb: ground within 14.3 below the hand.
- The instance is an XRef node with the weapon's model, m_character set, in the character
  texture sets (phase 2); a pickup type 4 C4 / 5 satchel / 6 claymore / 7 MP bomb.
- PlacedExplosive::PostTick: fuse runs (network: local only), out -> Detonate (state 3) ->
  PreTick registers the blast proximity (state 4) -> PostTick HandleDelayedDetonate (state 5)
  -> removal time (none: at once) -> state 6 -> the list destroys it.

## Written (ELF addresses)
- seal_body.cpp: PerformAction 0x272dc0.
- seal_kit.cpp: HandleRemotePlaceExplosive 0x2a6ed0, SetCurItemEnum 0x2af610, TickExplosives
  0x2aa7a0 placement part, HandleFireWeapon 0x2a8a00 C4 branch, DetonateRemoteExplosives 0x2a96c0,
  Timer_PlaceC4 0x2a9340.
- zwep_explosive.cpp: PlacedExplosive ctor / dtor / RemoteDetonate / PreTick / PostTick.
- zwep_projectilelist.cpp: RemoveExplosive. zwep_projectile.cpp + zweapon.h: IsInRange (-> bool).
- Traces (SOCOM_PORT): "EXPL: ..." C4 action, not placed (why), placed (fuse / removal / kind),
  detonator fires, placed charge detonates.

- hud_bitmapreticule.cpp: SetGBarVal 0x3cd490, UpdateGBarColor 0x3cd320 (see State).

## Notes from the runs
- The C4 blast (radius 152.5 world units) also flings and damages team-mates within it (DiMone,
  Bailey at 88-96: SPECTRE's dot went red): ELF damage path, not changed.
- The test camera (freecam) did not hold in k3 for the explosive view (the follow camera shows the
  scene anyway); the throw camera did work in s1.

## ELF quirks kept
- SetCurItemEnum: a plain item's raise timing (WepWaitOn/Off) follows the OLD item's type.
- DetonateRemoteExplosives selects the claymore afterwards (SetCurItemEnum(CLAYMORE)) and builds an
  unused local vector.
- The C4 / ground placement uses the body's rotation, not the wall normal.

## Port deviations
- HandleRemotePlaceExplosive: the AI deploy state's charge (+0x54 of the STATE_DEPLOY state; the
  ELF writes through NULL+0x54 for another state) is not stored: CAiSDeploy has no members
  declared and the player never deploys through the AI.
- SetCurItemEnum stays void (ELF 0/1; no caller tests it; zseal.h is shared).
