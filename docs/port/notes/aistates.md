# boot-aistates notes (socom-port-aistates): door state, stun response, corpse, (COMM, RUSH, routes)

## State / next step
- HEAD 2f8b0e3 (fireteam committed). My edit files for seal_ai.cpp, zseal.h, zai.h,
  seal_airesponse.cpp, seal.cpp, ai_maps.cpp were applied to the repo files (now in mine.txt,
  edited in place; the edit files are kept in edits/applied/). zbody.h needed nothing (HEAD has
  `friend class CSealCtrlAi`). Only fts_mission.cpp (socom-port-leftovers) stays an edit file:
  edits/e_mission.rep.txt (ftsFixupAiMap). seal_aistate.cpp's gate keeps FOLLOW and HOLD.
- DONE (a) door, (b) stun, (c) corpse + PlayAiSound/PlayAnim/GetRegionTypeContainer, (d) COMM
  (+ SetSleeping), (e) checked (no port bug). Not done: RUSH setup (CTState's RUSH part and
  CAiSRush::Tick 0x2e4ab0 1812 B unwritten; STATE_RUSH still gated), CGraph::BuildRoute
  (+ the graph tree, ~3.9 KB; cross-map routes still fail), the ftsFixupAiMap pickup part.
- Runs (pad_ev = pad_a1 + 400:CROSS movie skip; hook_states.cpp via b3.sh):
  - as1 (5b5aab3 + door state, no hook): first mission run of cc35f3e + 7c6dffd + 5b5aab3:
    movie skipped, mission from ~56 s, no STOP, heap 21.6 -> 21.87 MB.
  - as3: corpse + stun work (door untested: AI map action ids were all invalid because
    ftsFixupAiMap is an empty stub -> written, e_mission.rep.txt).
  - as6 (HEAD 2f8b0e3 + everything): 56..201 s no STOP, heap 21.88 -> 21.91 MB flat from ~90 s.
    Door: OutPatrol5 routed through door_depot01 (id 2): STATE_ACTION -> singleDoor anim (valve
    0 -> 1), walks through, "Attempting to close door!" -> shuts it (1 -> 0), continues; its own
    patrol later crosses back (opens / shuts again) (59.4-71.7 s). Corpse: OutPatrol1 walks to
    OutPatrol2's body, crouches, looks 1 s, on_corpse (73-78 s). Stun: OutPatrol3 cower anim 174
    86.7-91.2 s. 52 GOTO arrivals, team follow commands issued (fireteam).
  - def (default build, HEAD 2f8b0e3 tree): main menu (def.png), no STOP.
- Behaviour change to know: SetSleeping is real now, so 21 of 30 m8 enemies (ai::PARAM sleeping)
  are switched off at mission start, as in the ELF, until a COMM 27 (team 8) or a script wakes
  them; no COMM ran in the 145 s test (not exercised). CZSealBody::UpdateAiEvent makes every seal's
  footstep noise an ENTITY event (enemies can hear a moving player).
- Screenshots: build/port/screenshots/28-ai-states/ (door shut / opened, stun cower, corpse).

## Written (ELF addresses)
- (a) door: CAiSAction Tick 0x25ee30 / OnSignal 0x25f300 (e_ai.rep.txt), PathFollowTick's two
  STATE_ACTION pushes fill the state (s_ai.txt: open: door, value 1, flags 16, m_close_door /
  m_last_action for a relaxed enemy; close: cell centre, value 0), CAiSAction layout (s_zai.txt),
  gate lifted (seal_aistate.cpp). ftsFixupAiMap action ids (e_mission.rep.txt).
- (d) COMM: CTComm::Tick 0x2bde00 + TASK_COMM (seal_tasks.cpp; Parse not written: anims come
  compiled), CSealCtrlAi::SetSleeping 0x266eb0.
- (b) stun: CSealCtrlAi::OnStunDamage 0x269c00, PlayAnim x2 0x2695d0 / 0x2696e0, AnimIsPlaying
  0x269800 (e_ai.rep.txt; zseal.h returns bool: s_zseal.txt; zbody.h friend: s_zbody.txt),
  CAiSStunResponse Tick 0x2e6930 / OnSignal 0x2e6b70 (e_resp.rep.txt), layout (s_zai.txt),
  Create (STATE_STUNNED -> CAiSStunResponse) + gate (seal_aistate.cpp).
- (c) corpse: CAiSCorpse Tick 0x2e6c30 / SetCorpse 0x2e6e20 / OnSignal 0x2e6e80 (e_resp.rep.txt),
  layout (s_zseal.txt), Create + gate; CZSealBody CreateAiEvent 0x2557c0 / UpdateAiEvent 0x255400
  (e_seal.rep.txt: alive = ENTITY noise event by speed/stance/material/stealth, dead = visible
  CORPSE event range 400); PlayAiSound(CHARACTER_SOUND) 0x25fc90 (e_ai.rep.txt);
  CCharacterType::PlayAt 0x247a70 + AcquireSoundHandles 0x247fc0 (char_type.cpp);
  CAiMaps::GetRegionTypeContainer 0x1976d0 (e_maps.rep.txt), CAiMap::GetRegion(loc) 0x19eb30.

## ELF quirks kept
- CAiSCorpse phase 0 runs on into phase 1 in the same tick (a failed route ends in phase 2).
- OnStunDamage flashbang: cower only when the head faces away or within 15 of the blast.
- PlayAnim types 79/82/83 kill the seal (SetHealth 0, death 2).

## Port deviations
- CAiSAction phase 2: CAiMaps::GetActionById unwritten (loc stays invalid -> "Failed to
  GetActionId"); the PathFollowTick pushes carry flag 0x10 and skip it.
- GetRegionTypeContainer: a region on an unknown map is skipped (ELF reads NULL).
- ftsFixupAiMap: pickup part not written; ladders get no id (GetClosestLadder unwritten / void).
- _actionValveCallback (valve -> AI map action m_state) still unwritten.

## Files
- mine.txt (in place): seal_aistate.cpp, char_type.cpp, ai_mapdata.cpp, seal_tasks.cpp, zai.h,
  zseal.h, seal_ai.cpp, seal_airesponse.cpp, seal.cpp, ai_maps.cpp.
- Edit file: fts_mission.cpp (edits/e_mission.rep.txt, shared.txt). Applied ones: edits/applied/.
- Tools: copied from boot-aievents (paths fixed); srep.py / rep.py read utf-8-sig (a BOM made the
  first block silently miss). b3.sh / hook3.sh = hook_states.cpp build (door / corpse / stun
  tests at frames 60 / 1000 / 1700, test camera via ../tools/hook_freecam.h).
