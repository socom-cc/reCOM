# boot-aievents notes (socom-port-aievents): AI events, pursue, CAiSEvent

## State / next step
- (a) DONE: ev2/ev3 (hook_events.cpp, pad_a1, HEAD 607aa69): OutPatrol3 hears OutPatrol4's
  gunfire (AIE_WEPFIRE, "takes event ... friend", aware 3); OutPatrol4 pursues: plan -> goto ->
  hold -> target lost -> search (5) -> search_goto (6, walks to the last known position) -> seen
  again -> plan ... (ev2.log 63-105 s); 109 events, pool reused (3 pooled), heap 21.97 MB steady,
  no STOP over 56-174 s. Startled enemies run STATE_EVENT (react/look) and end it on sight.
- (b) DONE in source: WalkLine (both, ELF), SmoothPathLeg + GetLegBoundary + PointInPath +
  _SmoothLineCallback (ev3: 162 plan/arrival lines, no STOP).
- (c) ScanTick written (ev4 = HEAD 7c6dffd + ScanTick, pad_ev: 55-241 s, no STOP, heap 22.02 MB
  flat from 88 s on, 141 events). CAiSRestrained Tick/OnSignal written and STATE_RESTRAINED let
  through the gate (seal_body.cpp's restrain now stores the restrainer's team); not exercised by
  the fake pad. Not written: COMM 0x2bde00, RUSH setup, door state (STATE_ACTION), cross-map routes
  (CGraph::BuildRoute), CAiSCorpse (CORPSE still refused), GetRegionTypeContainer, PlayAiSound,
  PlayAnim(name). FOLLOW belongs to socom-port-fireteam now.
- ev5 (everything, HEAD 7c6dffd tree, hide at frame 600 with team mates): OutPatrol4 pursue
  plan -> goto -> hold (seen 0) -> search: the last known spot (450 away) has no look spot within
  the flood fill, so the state ends and the script's patrol GOTO resumes (ELF behaviour); 55-241 s
  no STOP, heap 21.93 MB flat. Default build (HEAD cc35f3e tree): main menu (def.png).
- Next: CSealCtrlAi::OnStunDamage 0x269c00 (1176 B) + CAiSStunResponse (stun reaction; the
  STUNNED state is gated), COMM, RUSH, STATE_ACTION (doors), CGraph::BuildRoute, CAiSCorpse,
  GetRegionTypeContainer, PlayAiSound/PlayAnim.
- Pads: since 7c6dffd m8 plays a 44 s intro movie; pad_ev.txt = pad_a1 + 400:CROSS.
- Builds: b.sh (no hook) / b2.sh + hook2.sh (hook_events.cpp, uses ../tools/hook_freecam.h).

## Written (ELF addresses)
- ai_events.cpp: the pool (m_pool/m_inuse/m_persist/m_callbacks as std::list): GetEventString
  0x180000, GetEventRate (enum fixed), GetEventFromString 0x17ff30, Open 0x17fe70, Close 0x17fca0,
  Acquire 0x17f9f0, Create 0x17f8f0, Release 0x17f840, Tick(f, void*) 0x17f780 (+ remove_if/_tick),
  GetFirstEvent 0x17f660, GetNextEvent 0x17f4a0, ctor 0x17f330, dtor 0x17fc20, Initalize 0x17f270,
  Tick(f) 0x17f210, MakeMaskEx 0x17f180, CAiEventQ::Create 0x17f080.
- zmath_main.cpp: CBits::Resize 0x221980.
- seal_aievent.cpp: SetAiEvent 0x2deff0, EventTick 0x2debc0, CanHearAttenuatedExplosionEvent
  0x2dea90, HandleEvent 0x2dcd60 (all 15 types).
- seal_airesponse.cpp: CAiSEvent OnSignal 0x2e6600, CanAttack 0x2e65d0, CanPursue 0x2e65c0,
  GetStatus 0x2e65b0, ComputeNextState 0x2e6520, Tick 0x2e5e80.
- seal_ai.cpp: CSealCtrl::CreateAiEvent 0x26a760, UpdateEventMask 0x26a5b0 (was a stub: no AI
  heard anything), FindPeekDir 0x25f6e0, CAiSPursue OnSignal 0x25acb0 / GetStatus 0x25ac10 /
  Tick 0x259930 / CanAttack 0x26c660 (zai.h), ChooseLookDir 0x2597a0, InGuardRegion 0x259240,
  HasSniperRifle 0x259230.
- seal_sensors.cpp: RegisterCanSee 0x2b0b40. seal_tasks.cpp: CTEvent::Tick 0x2bd5e0 (TASK_EVENT).
- ai_mapwalk.cpp: _SeeLineCallback 0x1a8460, CanSeeLine x2 0x1a8330/0x1a8340, WalkLine(loc,loc)
  0x1a7570 and (loc,pnt) 0x1a6b00 (shared walk core, replaces the interim half-cell walk),
  FloodFill 0x1a61e0, CountMapVisDir 0x1a56d0, CountMapTravelDir 0x1a5400, CAiMap::GetCellPos (inline).
- ai_search.cpp: _find_cover 0x1a9e40, _find_look 0x1a9d50, FindCoverLoc 0x1a9970, FindLookLoc 0x1a9590.
- ai_map.cpp: GetDirDelta 0x187a70, GetClosestDir(lo,hi,vec) 0x187680 (no fence), (pnt) 0x187890,
  (loc,pnt) 0x187330, _reset_rtflag 0x186bf0. ai_mapdata.cpp: region::InflateRegion 0x19e7e0,
  Union 0x19e710. ai_maps.cpp: CAiMaps::CanSeeLine 0x19a480 (GetRegionTypeContainer returns NULL).
- seal_aistate.cpp: gate lifted for PURSUE and EVENT. seal_sensors.cpp: the startle push
  (OnSetTargetVisible 0x2b1b4c) now fills its STATE_EVENT (GENERIC, 0.25 s looks, option 8).
- seal_airesponse.cpp: CAiSRestrained Tick 0x2e66f0 / OnSignal 0x2e6870 (zai.h m_team +0x28).
- ai_path.cpp: GetLegBoundary 0x196210, _SmoothLineCallback 0x194f80, SmoothPathLeg 0x194700,
  PointInPath 0x193540. seal_aiscan.cpp: ScanTick 0x2e3bf0.
- zWeapon edit files: AIE_WEPFIRE in the three CZWeapon::Fire (0x31f06c/0x31f204/0x31f388),
  AIE_WEPHIT in HandleImpact (0x3183c0), AIE_EXPLOSION in HandleDelayedDetonate (0x317e40).

## Key facts
- CAiEvent::EVENT (GetEventString's jump table 0x449010): 0 UNKNOWN 1 GENERIC 2 POINT 3 ENTITY
  4 VOICE 5 WEPHIT 6 CORPSE 7 DOOR 8 WEPFIRE 9 EXPLOSION 10 SURRENDER 11 GETDOWN 12 HELPATTACK
  13 ALARM 14 LIGHTSOFF, 15 = any (iterator). The port enum had a spurious AIE_NONE (fixed; the
  two SetAiEvent callers pass 2 = POINT as before).
- STATE_PURSUE 12, STATE_CORPSE 24, STATE_EVENT 25. CAiSEvent 88 B, CAiSPursue 52 B, CAiSCorpse 56 B.
- CAiState +0x08 a float -> m_time (CAiSTarget duration, CAiSPursue deadline); +0x14 the phase
  -> m_substate. CAiSEvent's m_look_time is an Rfloat (+0x44).
- Event mask (UpdateEventMask): asleep -> only WEPHIT/WEPFIRE/EXPLOSION; SEALs ignore 0, 1.
- Seals' event handles (m_eventQueue) are only pruned on death (OnDeath 0x269b58): one per
  visible event id seen.

## ELF quirks kept
- Open drops in-use events without pooling them; Close leaves the persistent list.
- CBits::Resize: shrink keeps the words; a fresh buffer is cleared only from the old count on.
- HandleEvent: SURRENDER/GETDOWN from a team mate reads the owner's control without a NULL test.
- FindPeekDir: soil 9 counts as open for the side cells. FloodFill: the start cell is never marked.
- WalkLine: m_loc starts at CAiMapLoc::invalid (0,0,0); its walk locs have map id 0.
- CAiSPursue: the target's GetPosW is called and dropped; seen in search ends the state.

## Port deviations
- CanPushAiState still refuses CORPSE (CAiSCorpse not created by CAiState::Create, Tick
  unwritten) and the other unwritten states.
- ChooseLookDir: counts start at 0 off the map (ELF: unset). WalkLine(loc,pnt): false for an
  off-map start (ELF walks from an unset point). GetRegionTypeContainer returns NULL (unwritten).
- The FloodFill direction-order table (built, unused in the ELF) is left out.
- PlayAiSound / PlayAnim("Flinch ...") are still stubs (no sound/flinch).

## Fences changed in shared-interest files (for socom-port-fireteam / fx edit files)
- seal_ai.cpp: CreateAiEvent__9CSealCtrl, UpdateEventMask__11CSealCtrlAi, FindPeekDir (+ static
  peek_cell before it), OnSignal/GetStatus/Tick__10CAiSPursue (+ static pursue_* helpers before
  Tick), ChooseLookDir, InGuardRegion, HasSniperRifle; AttackTick (comment, t->m_time);
  SetAiAware (SetAiEvent AIE_POINT); InitAiBrain untouched.
- zseal.h: CSealCtrl::CreateAiEvent -> bool; CSealCtrlAi InGuardRegion/HasSniperRifle/
  HandleEvent/RegisterCanSee -> bool.
- zai.h: CAiEvent (enum, statics, iterator), CAiEventCallback, CAiState m_time/m_substate,
  CAiSEvent/CAiSPursue/CAiSRestrained members, CAiEventQ::Create, CAiMap (GetCellPos, FloodFill/
  WalkLine/Find*Loc/CanSeeLine bool, GetDirDelta/_reset_rtflag static), CAiPath (GetLegBoundary,
  SmoothPathLeg, PointInPath bool), CAiMaps::GetRegionTypeContainer, MAP_FLOODFILL_STRUCT.

## Test hook
- hook_events.cpp (b2.sh/hook2.sh): nearest enemy 70 in front, the next 190 out to the side
  facing away; player and both enemies invincible; at SOCOM_HOOK_HIDE frames the player (and
  living team mates) are moved 450 away and the test camera (tools/hook_freecam.h, CheckDIShoot
  wrap) follows the first enemy for 1500 frames; e1/e2 AI state traced every 30 frames.
