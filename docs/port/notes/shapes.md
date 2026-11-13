# boot-shapes notes (2026-11-07, socom-port-shapes)

Scratch for character collision shapes, weapon damage on characters, target lists and
player-vs-character collision. Untracked. Changed files: `mine.txt`.

## Result (h3.log, hook build, HEAD 1a38b80 + mine.txt)
- Every seal gets 25 box DIs (AddDIPolys: one CDIBBox per body part over the part node's
  bbox, PERSON material); the part nodes follow the skeleton, so the boxes do too. Rays now
  take characters (DiIntersect ctor: m_IntersectCharacters / m_ProximityCharacters = 1).
- Aim ray / reticle: GetReticuleSeal reports OutPatrol4 (lthigh) on the enemy, Hutchins
  ("Boomer", green reticle + name) on the teammate. The enemy reticle stays yellow: red needs
  the player's target m_visible (perception, unwritten).
- Shots: HandleImpact -> CSealEx -> OnWeaponHit -> HandleDamage -> part (thigh/spine/head...)
  -> Damage* -> UpdateHealth: 1.0 -> 0.938 -> 0.875 -> 0.625 -> 0 (leg spent, then body),
  flinch anims (FlinchRLeg 54 / mirrored, damage table anims), death (OnDeath, death anim,
  HandleKiller, CSealStats), dead-body hits replay death anims (twice at most).
- Target lists (UpdateTargetList / OnUpdateTargetList, round robin sort): player 29 targets;
  UpdateLODFlags sets m_check_player_collision; CollidePlayers stops the player 6.4 from the
  teammate he walks into (held stick 5 s); releasing, the rifle-point push moves him to ~10.
- Camera: chord rays take characters now; a teammate 12 behind stays below the chord (no clip).
- d1.log: default build (HEAD + mine.txt, no hooks) boots to the main menu.
- Screenshots: build/port/screenshots/12-collision-shapes/2026-11-07_1604_*.png.
- Weapon-switch freeze (coordinator priority, committed 72789a5): wep2.log, HEAD + seal_body.cpp,
  moving switches/reloads through AddBlendOverlay, no STOP; 11-weapons/2026-11-07_1540_*.png.

## Tools
Copied from boot-weapons (paths fixed): dis.sh/dx.ps1/disx.py, sym.py, xref.py, ctree.py
(`--all` expands written callees), fences.py, stubchk.py, rep.py (SOCOM_REP_ROOT=<tree> to edit
a test tree), ccm.sh, lay.py/laycheck.sh, ga.sh (pattern from a file). New:
- tree.sh (TREE=/LIST= for other trees; skips `#` lines), sync.sh (tree.sh + edits/b01 if the
  repo lacks it), fake.sh / hook.sh -> ~/.cache/socom/tree-shapes.
- hook_shapes.cpp + hook.sh `<build> <pad> '<-D...>'`: AttachSeal wrap (census, enemy
  SOCOM_HOOK_ENEMY ahead, teammate ahead/right, SOCOM_HOOK_BEHIND teammate behind),
  GetReticuleSeal wrap (trace), GetTerrainMotionFactor wrap (teammate moved in front at
  SOCOM_HOOK_MOVE_FRAME; per-15-frame player/teammate/enemy trace).
- diag.py `<tree> <spec>`: inserts trace statements at the start of fenced functions in a
  test tree only (diag_wep.txt, diag_dmg.txt). tree.sh/sync.sh restore the repo text.
- Pad (h3): `...185:CROSS,480:R1,520:R1,560:R1,600:R1,630:R1,660:R1,690:R1,720:R1,
  760:RX=255+8,900:LY=0+150`, hook `-DSOCOM_HOOK_MOVE_FRAME=840 -DSOCOM_HOOK_BEHIND=12.0f`.

## Not written / next
- Death camera: GetDeadCamPoints 0x1e8fc0 (nonvoid stub) / UpdateDeathCamState 0x1e9620.
  The player can die now (fall damage levels 2/3 reach the real UpdateHealth) -> STOP.
- Perception: target m_visible / m_known (seal_sensors.cpp, AI) - enemy reticle colour/name.
- DropAmmo / DropItem (pickups), DetachBody (carrying), HandleDamageExplosive, team valves
  (InitalizeTeamValves / RefreshTeamValves / DecrementTeamValves), CSealCtrlAi::OnWeaponHit,
  UpdateAiMapLoc, CDIBBox::SetCDIBBox (bbox_poly: 6 unit-cube CDIPolys nothing reads).
