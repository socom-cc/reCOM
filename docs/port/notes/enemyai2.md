# boot-enemyai2 notes (socom-port-enemyai2): enemy combat behaviour (m8)

## State / next step
- DONE (a) shot-at / cover / dodge, reaction choice, flee; (b) RUSH (script + test); (c) enemy
  grenade throws (not the reaction to grenades); (d) surrender. RELOAD written, not exercised.
- Tree: ~/.cache/socom/tree-enemyai2 = HEAD (bf0d532) + copy.txt (= mine.txt, whole files) +
  shared.txt edit files (srep format: edits/s_zseal.txt, s_env.txt, s_zbody.txt, s_kit.txt).
- Build: `bc.sh <build> pad_ev.txt` (hook_combat.cpp via hookc.sh, fake pad); `b3.sh <build>
  <pad> nohook`; default build: default.sh (~/.cache/socom/enemyai2-default).
- Runs (all fake pad pad_ev + hook_combat, 222 s, no STOP in any):
  - ec2: OutPatrol4 shot by the player -> STATE_SHOTAT (no cover cell: dodge 3 cells, 71.0 s);
    hook RUSH OutPatrol1 runs at the player 80-87 s; SURRENDER OutPatrol5 (anims 178/179, team
    0x40000210 -> 0x4000000, restrainable at 94 s); FLEE Shed1 found a safehouse region, ran
    there, STATE_HOLD at 104.9 s.
  - ec3: natural cover: OutPatrol2 "Found Hide Location (232,232) peek -1" (97.3 s), again at
    100.5 / 102.0; script RUSH from on_aware3 ("RUSH player at cell 129,331", 98.8 s); grenade
    test: OutPatrol1 ChooseWeapon 552 -> M67, throw at 295 (power 0.49), "GREN: thrown by AI"
    92.07 s, lands on the player (first bounce on PERSON); natural grenade choice by OutPatrol2
    (Uzi -> M67, 175 s) and Help1 (212 s). Surrender Shed1 (ec3-98.png).
  - ec4/ec5/ec6: same; SEAL team mates take cover too (Hutchins "Found Hide Location" -> path);
    script RUSHes by Help1 / OutPatrol2; OutPatrol1 rush -> flee by its own reaction (187.8 s,
    ec5). ec6 (HEAD bf0d532): heap 22.25 MB (100 s) -> 22.28 (150 s) -> 22.29 (180-220 s) flat;
    9 GOTO arrivals, door action, 11 pursue, follow states, events (regressions none).
  - def (default build, HEAD bf0d532 tree): main menu (def.png), no STOP.
- Thips (OnWeaponEvent) are written but never fired in the runs: the player's test rounds ended
  on terrain / a wooden wall short of the enemy (segments 30 long), so underfire came from hits
  and grenade blasts only.

## Survey (survey.py over the AI files, HEAD b175ed7)
Empty functions by behaviour (ELF address, bytes):
- Under fire (a): CSealCtrlAi::OnWeaponHit 0x26a0a0 492 (the only m_underfire raise by a hit;
  was empty -> m_underfire never rose, STATE_SHOTAT unreachable), OnWeaponEvent 0x26a290 796
  (bullet passing within thip_range -> underfire; HELPATTACK event for the player's shots),
  CZSealBody::HandleWeaponEvent 0x293bc0 348 (seal_env.cpp: weapon event -> every seal's
  controller), ai::AddNoise x2 0x17e1b0 / 0x17e520 (zAI/ai_main.cpp), CAiSShotAt Tick 0x2e8590
  2548 / OnSignal 0x2e8f90 252, CSealCtrlAi::FindCoverLoc 0x25f460 628.
- Reaction choice (a/b): DoReaction 0x2604e0 644 (none / RUSH / FLEE / SURRENDER by the
  m_reaction weights), SetDoReaction 0x260770 192, CAiSFlee Tick 0x2e5850 1268 / CanAttack /
  OnSignal (needs safehouse regions: CAiMaps::GetClosestRegion 0x1978a0 1040, GetRandomLoc;
  without one it re-chooses RUSH / SURRENDER 50/50).
- RUSH (b): CAiSRush Tick 0x2e4ab0 1812, SetTarget 0x2e51d0, OnSignal 0x2e51f0; CTState::Tick
  0x2b5820's RUSH / FOLLOW set-up. All 36 m8 ai::STATE uses are RUSH (target "player" or
  "Snow3") in on_aware0/2/3/4 sequences.
- Flanking / combat moves: none in the ELF. seal_aimoves.cpp holds only CAiDodge (Destroy,
  list dtor; nothing creates a dodge). RUSH is the only charge behaviour.
- Ammo: CAiSReload Tick 0x2e8030 1360, CAiSNoAmmo Tick 0x2e77f0 568 + FindTraversableNeighbor
  0x2e7a30 936 + ai::find_closest_ammo 0x2e7e30 500; ChooseWeapon 0x261eb0 1524.
- Grenades (c): ChooseWeapon (picks the thrown item), ComputeThrowFireParams 0x25e360 820,
  UpdateThrowFireParams 0x25e6a0 264 (CZKit::TickExplosives' AI release 0x2ab0c4), CTFireMode
  Begin 0x2bd1a0 / Tick 0x2bd100 (m8: 2 uses in on_aware4; Tick was "not done" -> those
  sequences hung); the reaction: SensorPreTick's live-grenade pickup walk (0x2b26d4..) ->
  CAiSGrenade Tick 0x25af40 6428 (run / throw back: SetReturnVelocity 0x25c860 2072).
- Surrender (d): CAiSSurrender Tick 0x2e7340 760 / OnSignal 0x2e7640 416, delayed_dropitems,
  ClearTeamMask 0x2e9090. Routes: CAiMap::TransformTo 0x185b50 1172, CGraph::BuildRoute.
  Hostages: CAiSHostage 0x2da2d0 380, CAiSRescued 0x2592f0 904 (m8 has an "EXTRACT CAPTIVE"
  objective and unit 17 escortees).
- Others still empty: CAiSAvoid 0x2da4a0 544, CAiSPathRecover 0x2e5290 1204, CAiSPickup
  0x2da750, CAiSAnimate 0x25ad00 476, CAiSBreach 0x2d8000 2860, CAiSCQBAttack 0x2d7a70 324,
  AnimSignal 0x2609a0 1028, OnDeath 0x2699b0 504, vis maps (ai_vismap.cpp 9.4 KB), ai_lines.
- CanPushAiState's port gate at HEAD refused: AVOID, DEPLOY, LASING, SURRENDER, BREACH, ANIMATE,
  CQB, FLEE, PATHRECO, RESCUED, SUSPENDED, SHOTAT, RELOAD, NOAMMO, PICKUP, HOSTAGE, GRENADE, RUSH.
  Now passed too: SHOTAT, FLEE, RUSH, SURRENDER, RELOAD.

## Written (ELF addresses)
- seal_ai.cpp: OnWeaponEvent 0x26a290, OnWeaponHit 0x26a0a0, Tick's SHOTAT fill (0x269350),
  DoReaction 0x2604e0, SetDoReaction 0x260770, FindCoverLoc 0x25f460 (bool), ChooseWeapon
  0x261eb0, AttackTick's ChooseWeapon call (0x262d50) and throw parts (0x2636b4, 0x263730),
  UpdateThrowFireParams 0x25e6a0 / ComputeThrowFireParams 0x25e360 (bool).
- seal_airesponse.cpp: CAiSShotAt Tick/OnSignal, CAiSFlee Tick/CanAttack/OnSignal, CAiSRush
  Tick/SetTarget/OnSignal, CAiSSurrender Tick/OnSignal, delayed_dropitems, ClearTeamMask,
  CAiSReload Tick/OnSignal.
- seal_tasks.cpp: CTState::Tick's FOLLOW / RUSH set-up, CTFireMode Begin/Tick (TASK_FIREMODE).
- seal_aistate.cpp: gate (+SHOTAT, FLEE, RUSH, SURRENDER, RELOAD), Create makes CAiSReload.
- zAI: ai_main.cpp AddNoise x2, CAi::Extrapolate 0x17ee60; ai_maps.cpp GetClosestRegion
  0x1978a0 (returns the region now), GetRandomLoc 0x197340; ai_mapdata.cpp region::GetCenter
  0x19e690; zai.h layouts of CAiSShotAt / CAiSFlee / CAiSRush / CAiSSurrender.
- Edit files (shared): zseal.h (FindCoverLoc / throw params bool, CAiWepHint members, CAiSReload
  members), seal_env.cpp (HandleWeaponEvent 0x293bc0), zbody.h (friend CAiSSurrender),
  seal_kit.cpp (TickExplosives' AI release 0x2ab0c4).

## Key facts
- MW CAiState vtable: +8 OnSignal, +0xc Tick, +0x10 GetStatus, +0x14 CanPushAiState, +0x18
  CanSwitchAiState, +0x1c CanAttack, +0x20 CanScan, +0x24 CanPursue, +0x28 GetScriptResponse.
- CSealCtrlAi vtable +0x24 PlayAiSound, +0x44 OnWeaponEvent, +0x4c OnWeaponHit, +0xa0 SetTarget.
- Sizes (Create): ShotAt 64, Flee 52, Rush 52, Surrender 60, Grenade 68, NoAmmo 48, Reload 48.
- CAiWepHint (8 B): byte 0 = four 2-bit preferences (quiet, quiet again, full auto, burst);
  byte 1 bit 0 score by accuracy, bit 1 + bits 2-5 a kit index; +4 range. AttackTick's hint is
  0x58 (prefer auto + burst) with the target range; m8's FIREMODE: kit item 0, 0.2 / 3.5 s.
- GETDOWN / SURRENDER events from an enemy only lower courage (HandleEvent); with DoReaction now
  written a low enough courage (<= the target threat) makes the enemy rush / flee / surrender.
  EXPLOSION makes it aware (3) and look (STATE_EVENT); a live grenade's own reaction (STATE_GRENADE)
  is the unwritten pickup walk + CAiSGrenade.

## ELF quirks kept
- A reaction RUSH (DoReaction) has no target (OnSignal 4 sets invalidId), so its Tick ends it at
  once; only a script's ai::STATE RUSH (target "player") charges.
- DoReaction copies a zero vector to an unused local. OnWeaponHit without a shooter seal keeps
  -100 x the projectile velocity as the shot position. ChooseWeapon applies the quiet penalty a
  second time for hint bits 2-3 without testing the weapon. CAiSRush ignores the route after a
  straight chase (re-appended each frame). OnWeaponEvent's helpattack_range is set but unused.

## Port deviations (flagged in source)
- CAiSFlee phase 5 routes to the cover cell FindCoverLoc found (the ELF passes an unset stack
  word next to it). CAiSFlee: CSealUnit::CheckPathProximity not called (nothing sets m_unit).
- GetClosestRegion: the centre cell takes the region's map id (ELF: unset); unknown-map corners
  skipped. CAiSReload: no vis maps (CSealCtrl::m_vismap is NULL) -> no evade move.
- SetDoReaction / ChooseWeapon void (ELF returns 0/1, unread).

## Not written / next
- CAiSGrenade (6428 B) + SetReturnVelocity + SensorPreTick's live-grenade walk (enemies do not
  run from / throw back grenades); CAiSNoAmmo (+ ammo pickups); CAiSDeploy; CAiSAvoid,
  CAiSPathRecover, CAiSHostage / CAiSRescued, CAiMap::TransformTo, CGraph::BuildRoute.

## Coordinator question (R1 after the cameras)
- Not a weapon problem: the SELECT that skips the mission camera (hook_skipcams.h holds it 3
  reads) is still down when the camera ends, so the tactical map opens full screen and the game
  pauses (ec1.log 59.79 "MAP: full screen", ec1-102.png). hook_combat.cpp closes it with
  TRIANGLE when the player's m_menustate is stateFullScreenMapMenu; after that R1 fires (ec2:
  OutPatrol4 hit by the player's rounds at 70.85 s).

## Tools
- Copied from boot-aistates (paths -> boot-enemyai2 / tree-enemyai2). New: hook_combat.cpp
  (fire / rush / grenade / surrender / flee tests, census, kit list, tactical map close), bc.sh,
  hookc.sh, edits/parts/*.cpp + d_resp_*.py (the sources applied to seal_airesponse.cpp).
