# boot-stance notes (2026-11-13, socom-port-stance)

Scratch for (a) stances (player + AI), (b) zoom heartbeat + scope wander, (c) weapon pickup anim.
Untracked. Changed files: `mine.txt` (= copy.txt, whole files laid over HEAD by tree.sh). Shared
files (zseal.h, seal.cpp, seal_ai.cpp, seal_env.cpp): edit files in `edits/` (srep format), listed
in `shared.txt` (= shared_default.txt). Test tree refreshed to HEAD 6ab484e (edits apply clean).

## State / next step
- DONE. (a), (b), (c) written and working at HEAD 6ab484e + mine + edits.
- s3.log (sab.sh stc-a, pad_s1, mission cams skipped by SELECT): crouch 64.9 s, crouch walk (half
  stick: anim 20, speed 14.8), crouched sneak (full stick: anim 2, 63), prone 72.9, crawl (anim 27, 11),
  stand, double click stand -> prone, team-mates crouch / prone with him (Hutchins st 2 at 18 away),
  scope at 96.5 s: heartbeat loop 2 -> 1 (98.3) -> 0 (101.1); enemy OutPatrol1 SetStance(crouch) ->
  st 1 / anim 17 -> 18 (114 s; then killed by the team, so the prone step showed nothing).
  Mission 56 -> 191 s, no STOP. c5.log (pkb.sh stc-c, pad_c2): pickup swap anim (see (c)), no STOP.
  dflt.log (default.sh stc-dflt, no hook / fake pad): main menu 9.7 s, attract 46 s, no STOP.
- Screens: build/port/screenshots/30-stance/.

## (a) Stances - WORKS
- Input was already written: CSealCtrl::PreTick (TRIANGLE single click: stand -> crouch -> prone ->
  stand; double click: stand -> prone -> crouch -> stand) sets m_desiredState. Missing was the body.
- Written (seal.cpp edit): UpdateStance 0x256c80 (from a cycling top or during a transition:
  Stand(1) / Crouch / Prone + SetStance, stance-changed flag).
- Written (seal_body.cpp): SetStance 0x276960, StanceChanged 0x2772d0 (bool), Crouch 0x276530,
  Prone 0x275fa0, Prone_0 0x275e80, InStateProne 0x2792e0, ProneControl 0x278230 (crawl / prone
  strafe, the turn via TurnControl), Adrenaline 0x26e9f0, Action 0x26ea00 (c).
- seal_weapon.cpp: CanProneAim 0x2bf240 (bool; zseal.h edit). hud_posebitmap.cpp: PoseBitmap::Tick
  0x3d93a0 (HUD word stand / crouch / prone at full alpha, fades out; s2-72.png "prone").
- AI: CSealCtrlAi::OnStateChange 0x269850 (seal_ai.cpp edit: the AI stance follows the body state,
  "fixing" trace). CSealCtrlAi::SetStance / DoSetStance / SetStanceDelayed / follow stance matching
  were already written; they only set m_desiredState, which nothing acted on before UpdateStance.
- AI sight of crouched / prone targets (CSealCtrl::ComputeVisibility -> CAiMaps::ComputeLineVisibility
  0x19a120 STOPped in s1): written CAiMaps::ComputeLineVisibility (ai_maps.cpp), CAiMap::
  ComputeLineVisibility 0x1a8280 and _VisLineCallback 0x1a8360 (bool; cover: grass 0.1 / brush 0.22 /
  forest 0.4, shadow table 1 / 0.9 / 0.5 / 0.33) (ai_mapwalk.cpp).
- Speed / collision / camera height per stance come from code already written (GetMaxZMotion reads
  m_desiredState, the camera follows the head: trace "cam y +26 stand, +20 crouch, +17 prone").
- ai::STANCE: CTStance::Begin (written) -> CSealCtrlAi::SetStance -> DoSetStance -> m_desiredState ->
  UpdateStance: same path. m8 never ran an ai::STANCE in 135 s (CTStance::Begin wrap: 0 calls), so
  s3 calls the enemy's CSealCtrlAi::SetStance from the hook (phase 11) the way Begin does.

## (b) Heartbeat + scope wander - WORKS
- Driver: the adrenaline (CAiDecay m_adrenaline, 1 at spawn): Tick (written) raises it with the
  throttles (AdrenalineIncr) and decays it at the stance's sniper decay rate (CTargetMods by GetStance).
- Written (seal.cpp edit): Open/CloseHeartbeatSounds 0x24d8a0 / 0x24d840 (SND_HEARTBEAT_SLOW /
  MEDIUM / FAST_LOOP; m_heartbeat_sound typed CSnd*[3], zseal.h edit), TickHeartbeat 0x24d6e0 (loop
  by adrenaline: < 0.33 slow, < 0.66 medium, else fast; runs only scoped, kit m_heartbeat_enabled).
- Written (seal_kit.cpp): CZKit::SniperTick 0x2a5040: heartbeat rumble (beats 0.3 + 0.24(1-a) /
  0.8 + 0.64(1-a) s apart, low rumble 20 + 100a) above adrenaline 0.2 (not binoculars); the rifle kick
  (aim pitch up at the kick rate, back at the return rate); the scope wander: screen offsets x / y move
  at the stance's per-frame distance and bounce at 0.2 + 0.8a of the stance's limit (camera
  m_screenOffset via SetCurAccuracy).
- s2.log: zoom 4 at 85.6 s -> "heartbeat start, loop 2 (adrenaline 0.991)", loop 1 at 0.655, loop 0
  at 0.328; KIT trace offsets 2.5/2.3, 5.3/-3.5, 2.1/2.4, -0.2/-0.9, -2.7/-1.0, then frozen at -0.36/0.26
  once the adrenaline is under 0.2 (ELF). Sound start is traced (CSnd::PlaySound instance), not heard.

## (c) Weapon pickup animation - the ELF has one; the port skipped it (now written, WORKS)
- CZSealBody::PickupItem 0x28df50: FindAnimType("Swap rifle") (0x28e144, string 0x453ae0) then
  CZSealBody::Action 0x26ea00 (call 0x28e184; args reversed = true, node id = the DROPPED gun's pickup
  id * 2, part = the right hand, result -1). Action was an empty stub (and GetAnimationNode 0x28c180,
  CBody::FindBodyPart 0x1e3110), so nothing played.
- Action: the dropped gun's node goes onto the right hand as the "rifle_out" object part, the anim is
  pushed in the current state carrying it; CheckAnim (written) lays the gun in the world at the hand at
  the end. c5.log: "SEAL: player action anim 272 (reversed 1) carries node rifle in part 18", anim 272
  for 1.1 s (f235-f300), the old M4A1 SD is offered as a pickup afterwards. c5-66.png: the player
  kneels with the gun (the swap anim) over the body.
- Written: Action (seal_body.cpp), GetAnimationNode (seal_env.cpp edit), CBody::FindBodyPart (body.cpp).

## ELF quirks kept
- SetStance: the transition switch reads m_state after setting it: only equal pairs, nothing runs.
- Prone while moving faster than 2: the wanted state goes back to stand but UpdateStance still sets
  state 2; SealAnim puts the state back to the top blend's. A follower told to go prone while still
  walking flips 0/1 <-> 2 each frame (OnStateChange "fixing" + DoSetStance spam) until it stops.
- CanProneAim uses the camera's view axis (row 2 of the world camera matrix) for every seal; a steep
  camera (camera clip on the prone player) makes the player rise to crouch (s2 f1050).
- SniperTick: step (0.25 + d) + (0.75 + d) |offset| / limit with the signed per-frame distance d;
  offsets freeze (not recentre) at adrenaline <= 0.2; the y limit's "< 0.1 -> 0" is unreachable.
- TickHeartbeat: on a loop change the new sound is not NULL-tested.
- Action: the node is added to the hand, deleted from its (new) parent, added again.
- ComputeLineVisibility: the shadow step indexes a 4-entry table unbounded.

## Port deviations
- Prone_0 / Prone from a hang or another state: the ELF writes the representative of NULL (guarded).
- Action: the object part entry is NULL-tested. CAiMaps::ComputeLineVisibility: the other map is
  NULL-tested before TransformTo.
- SetStance / Action / StanceChanged signatures: void / void / bool as declared (ELF 0/1 returns).

## Not written / next
- CAiMap::TransformTo 0x185b50 (1172 B, empty stub): reached only by line visibility between map 0
  and another map (a crouched/prone target on another map) - would STOP. m8 runs did not reach it.
- Hang_0 (dead SetStance path only), RaiseBinoculars / LowerBinoculars, PerformAction.

## Tools
Copied from boot-leftovers (paths -> boot-stance / tree-stance). New: hook_stance.cpp (state-driven
pad: TRIANGLE / double click / stick value / UP / DOWN; traces player + team-mates; side test camera;
enemy SetStance test; CTStance::Begin wrap), hook_pickstance.cpp (= boot-pickups' hook + kill by
UpdateHealth, CROSS take, side camera -DSOCOM_HOOK_TAKECAM), hook_skipcams.h (SELECT skips the 6ab484e
mission cameras; scripts wait for them), sab.sh / pkb.sh (the two test builds), chk.sh (wrap count +
fake pad of builds), rawdis.sh (objdump with raw words), cpasm.sh (copy the cached full ELF
disassembly out of WSL). Build dirs stc-a / stc-c / stc-dflt (pk1 / st1 were other workers' names).
