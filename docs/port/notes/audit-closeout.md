# Audit close-out (2026-11-20, socom-port-audit-closeout)

Two jobs after the correctness audit: the kept deviations that are only guards, and the
mission-win test hook's crate step. HEAD abb909ac plus the uncommitted `zmath.h` saturate edit.

## Job 1: kept guards removed

The user's rule: the prototype's behaviour is kept. A NULL test or other guard that the ELF
lacks goes, unless the port's own compatibility code needs it (an offline provider, the port's
file layer, GCC), in which case it stays with that reason in the code.

All 170 DEVIATION-KEPT rows of the `audit-*.md` notes were classed by their recorded reason:

| Class | Rows | Action |
|---|---|---|
| port need (provider, file layer, GCC, no such object in the port) | 25 | kept |
| the ELF reads freed, unset or out-of-range memory (stack / heap garbage, past an array, a freed node, past a literal) | 80 | kept |
| guard with no port need | 45 | 40 removed today; 5 had been removed already (large-a part 2, "Lead B") |
| not a guard (void return, wrap order, a hang in the ELF, left-out code, the out-of-line LoadZAR) | 20 | kept |

Two mixed rows lose their guard part and stay DEVIATION-KEPT for the rest: large-fts #7
(the ammo fields' NULL test removed; the unset positions stay) and large-hud-b #11 (the
`appCamera->m_entity` test removed; the bar end points' z / w stay).

Since `port/CMakeLists.txt` builds with `-fno-delete-null-pointer-checks`,
`-fno-isolate-erroneous-paths-dereference` and `-mno-check-zero-division`, a read through NULL
compiles to that read, as with Metrowerks: removing a guard reproduces the ELF's access (low
memory on the PS2). No guard was removed where the port reaches the NULL case and the original
would not (each case below is unreachable with the disc's data or the same in both).

Rows changed (each now `DEFECT-FIXED | C`, "kept earlier; guard removed 2026-11-20"):

| List | # | Function | Removed guard (ELF form) |
|---|---|---|---|
| large-apps | 11 | OrdersMenu::SetupContextDisplay | an unfilled entry's NULL m_display is strncpy'd (0x179038 / 0x179134) |
| large-apps | 25 | CE3Config::Parse | the first element's type read without a NULL test (0x37e130) |
| large-combat | 32 | CZProjectile::HandleBounce | the material's under-water bit read unchecked |
| large-fts | 14 | CMission::PreOpen | findSTRING's answer tested, not the pointer (0x1f8a6c) |
| large-hud-a | 19 | CZLineMap::TickWayPoints | the 33rd label written through NULL |
| large-hud-a | 16 | CLensFlareSaturate::Tick | m_LightNode's opacity stored unchecked |
| large-hud-b | 16 | CHUD::Tick | the pad passed to OrdersMenu::HandlePad unchecked |
| large-rest | 31 | CSnd::LoadCSnd | element 0's type; strlen of a missing N1 |
| large-rest | 40 | CValve::CmdParseCmp | AddValve of a failed Create's name |
| large-world | 23 | zdb::CWorld::~CWorld | m_shadowTexH unchecked (every world is initialised) |
| medium-ai | 53 | CAiMaps::GetLocationDelta | TransformTo / m_cellcount through the maps unchecked |
| medium-ai | 85 | CAiVisMap::CloseAll | an entry's id written unchecked (0x1a1e08; the list is always empty) |
| medium-anim-a | 67 | CMenuStack::PopUpDialog | strcmp / strcpy of the name (0x1d5f58, 0x1d5f80) |
| medium-anim-b | 10 | CZAnimMain::GetDatabaseNode | strcmp of the world's name (0x1c328c) |
| medium-anim-b | 12 | CZAnimMain::SequenceRunning | strcmp of GetName's answer (0x1c3540) |
| medium-anim-b | 13 | CZAnimMain::PauseSequence | the same (0x1c37c0) |
| medium-anim-b | 14 | CZAnimMain::StopSequence | the same (0x1c38d0) |
| medium-anim-b | 15 | CZAnimMain::ActivateSequence | the same (0x1c3a80) |
| medium-apps | 4 | Headset::Remove | the type byte through m_sound (0x2f2c8c) |
| medium-combat | 53 | CZDecalSet::ReadDecalEntry | a texture not found passed on (now traced: "DECAL: decal texture ... not found") |
| medium-combat | 56 | CZMarkList::ReadBloodDecals | the same ("DECAL: blood texture ... not found") |
| medium-draw | 71 | C2DString::Load | the height read through the font's texture (a NULL one traced: "2D: string ... without texture") |
| medium-node | 48 | zdb::CWorld::Read | the world_tree key walked unchecked |
| medium-rest-a | 84 | CSndInstance::AwarenessUpgrade | snd_parent_is reads a NULL parent's type (0x2efae8) |
| medium-rest-a | 85 | CSndInstance::Remove | the same helper |
| medium-rest-a | 71 | CSndGroup::LoadCSndGroup | Get(0)'s type unchecked (0x2f061c / 0x2f0734) |
| medium-rest-b | 67 | CPickup::NetworkCreate | Create's NULL takes the net id |
| medium-rest-b | 66 | CPickup::Create | a failed allocation written through |
| medium-rest-b | 64 | CPickup::GetClosest | the node's position read unchecked |
| medium-rest-b | 65 | CPickup::GetNext | the same |
| medium-seal-a | 4 | CZSealBody::NetworkPlayerCreate | a PLAYERNAMEVAR that is no string strncpy's from NULL |
| medium-seal-c | 63 | CTDebug::Parse | a list without values reads the type through NULL |
| medium-ui-b | 61 | CUIVarManager::Add | FindDormantVar's NULL used as is |
| sample | 42 | CTSetMode::Parse | the type read through NULL (0x2b7438) |
| sample | 52 | CSealCtrlAi::AnimSignal | the SUSPENDED check-cast written through (0x260d58) |
| sample | 111 | zdb::CLightMap::CLightMap | m_lightMapTexture's texture read as is (0x226990, InitLightMap) |
| small-e | 148 | zdb::CWorld::AddLightMap | the same |
| small-h | 29 | CZAnimMain::SequenceExists | strcmp of GetName's answer (0x1c3650) |
| small-h | 30 | CZAnimMain::ResumeSequence | the same (0x1c3700) |
| small-h | 65 | CZAnimSet::Anim | strcasecmp of GetName's answer (0x1c7cb4) |

Already removed before today (the rows still read DEVIATION-KEPT): large-a #28 BaseAnim_0, #39
HandleGrenadeExplosion (its unset location byte stays), #79 HandleRemotePlaceExplosive, #74
UpdateAiMapLoc, #78 PickupAmmo (its 8-entry ask array stays), as large-a part 2's Lead B decided.

Kept although it is a guard: large-combat #1 InitMultiplayerMessages (the ELF also passes NULL to
`%s`, which MSL and newlib print differently); medium-ui-b #59 CUIVarManager::UnSerialize (the
clone from NULL walks the port's `_zrdr` layout; saves come through the port's save layer).

The full table of the 170 rows is in the scratch file `build/port/boot-audit-closeout/kept.md`.

## Job 2: the win hook's crate step

The failed gate run (c182c48f) lost the second supply cache: an enemy's CQB attack on the player
(Help1, 136.0 s) came just before the R1 on the one face that works there, the put-on-wall action
never started, the hook moved on after its four faces, cratecount stopped at 2 and the mission
never ended. The hook's placement test never saw a charge either: placed charges are
`PlacedExplosive`s in `CZProjectileList::m_explosives` (shooter = the body's id), not in
`m_projectiles`, so every crate got all four faces.

Now (step 7 of `port/test-hooks/win/hook_win.cpp`): the placement is seen in `m_explosives`; a
crate group is left only when its destruction is seen (cratecount, the mission's own count, rises
about 10 s after the charge); its faces are tried in turn, at most 8 tries a pass, a charge waited
for 450 ticks before the next try; a group still standing after the first pass is visited again in
a second pass before step 8. Bounded (2 passes, step 7 ends at 7200 ticks), so a real defect still
fails the run. The pass condition, the pad script and the player's and enemies' behaviour are
unchanged; step 0 also traces the lens flare's light node (for Job 1's #16).

## Runs

Final tree = HEAD abb909ac + this work's files + the `zmath.h` edit; silent, portable profile,
second monitor, focus kept, no memory card.

- Default build links (`default.sh`).
- `gate.ps1 -Only win -Build audit-closeout-gate`, five runs: 4 PASS (debrief at 194.2, 197.2,
  194.8, 197.2 s, objectives 3/7), 1 FAIL (run 3, no debrief). In all five the three crate groups
  were destroyed in pass 1, after 1 or 2 tries each (the second face where the first has no wall).
  No "still standing" / "no destruction" line, no "DECAL: ... not found" or "2D: ... without
  texture" trace; the lens flare is inactive in m8 (light node NULL, so #16's path is not reached).
- Run 3's failure is outside the crate step and outside the changed functions: at the restraint
  (step 8) Snow3 was hit and detached (169.99 s, state 0) while the player's ApplyRestraints blend
  was still on; `CZSealBody::CheckAnim` then reads `m_carry` (NULL) for the blend's partner, as the
  ELF does unchecked (0x277880..0x2778c8), and PCSX2 stops on the TLB miss at 0x520.
- `gate.ps1 -Only roundtrip`: PASS, 4 returns, in use 18,642,780 B flat at every return.

## Open questions

- Rows kept for a GCC reason that the CMake flags have since removed: medium-seal-d #31 Hang_0,
  #33 Prone_0, #13 Action, #98 sealSaveFireModes ("a literal NULL traps under GCC -O3": now
  `-fno-isolate-erroneous-paths-dereference`) and medium-seal-a #36 CanPickupNetItem ("a member
  call on NULL is undefined in GCC"). By the user's rule they would go too; not changed here.
- Five rows of large-a still read DEVIATION-KEPT though Lead B removed their guards.
- PCSX2 reports a TLB miss for a read below 0x80000 in the port (run 3), so a read through NULL
  stops the port rather than reading low memory; the guards removed here are not reached in the
  runs, but any of them that is reached stops the port as the ELF's read would.
- The restraint crash of run 3 (ELF-faithful NULL `m_carry` in CheckAnim after a hit detaches the
  captive): the hook could restrain Snow3 only when no enemy is engaging, but that changes the
  test's conditions; left for a decision.
