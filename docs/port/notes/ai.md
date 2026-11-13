# boot-ai notes (socom-port-ai, continued by socom-port-ai2): enemy AI perception / reaction / scripts

## State / next step
- DONE: (a) perception and (b) reaction work in m8; (c) partly: the AI script anims run (startup,
  on_aware0..4, HOLD/STANCE/MACRO/PARAM/...), but ai::GOTO and route following are NOT written, so
  enemies do not patrol or move along the AI map (a GOTO command waits forever).
- Last runs: a7 (hook build, pad_a1) = detection -> targeting -> firing -> player killed 80.8 s,
  death cam, debrief, no STOP. a8 (no hook, pad_a1) = mission 56 s .. 161 s (frame 6300), no STOP.
  def (default build) = main menu, no STOP. Clip: build/port/recordings/2026-11-12_enemy-ai.mp4.
- Next (whoever continues): (c) movement = CTGoto Begin 0x2bc300 / Tick 0x2bc210 / End 0x2bc100
  (layout below), CSealCtrlAi::SetRoute x2 0x261090 / 0x260eb0, GetRouteComplete 0x2615e0,
  ClearRoute 0x261500, the planner (zAI ai_astar.cpp: PathPlan*, TickPathPlanner, CAiStar::find_path
  0x1814c0 3992 B, CAiPath plan_addleg / AppendPathLoc / PostProcess / SmoothPathLeg ...,
  CAiMaps::RegisterPathPlan 0x199870) and PathFollowTick 0x264e20 (4968 B); CAiSGoto Tick 0x2d9780.
  Then STATE_PURSUE (CAiSPursue::Tick 0x259930, 4668 B) and lift CanPushAiState's port gate.

## Root causes (ai2)
1. STOP in `zdb::CCamera::GetFogVisibility` (empty non-void stub, reached by the AI visibility code).
2. Enemy scripts never started: `CMission::OnMissionStart` lacked the entity loop (0x1f4660, every
   entity's OnMissionStart), `CZSealBody::OnMissionStart` was an empty "body", and the whole chain
   (CSealCtrlAi::OnMissionStart -> SetupAnimations -> ActivateEx -> STATE_SCRIPT / CAiSScript) and
   the CZAnim sequence calls (SequenceExists/Running, Pause/Resume[Sequence]...) were stubs.
3. `CAiState::Create` left the states without their own Reset with m_state 0 (TARGETING was pushed
   again every frame); the ELF resets every state in its ctor.
4. In hold mode (ai::HOLD) an enemy cannot turn (no goal processing); the ELF turns it through
   STATE_TARGETING / STATE_PURSUE pushed by AttackTick (was not written).

## Written by ai2 (ELF addresses)
- zcam_update.cpp: CCamera::GetFogVisibility 0x1e85f0.
- anim_main.cpp: CZAnimMain Pause/ResumeSequence 0x1c3780/0x1c36c0, SequenceExists 0x1c3600,
  SequenceRunning 0x1c34f0 (the last two return unsigned char now, zanim.h).
- zanim_anim.cpp: CZAnim Activate/Stop/Pause/ResumeSequence, SequenceExists/Running (0x1cd5c0..
  0x1cd770: ZAnim's with this anim swapped in), Pause 0x1cc8f0, Resume 0x1cc820.
- seal.cpp: CZSealBody::OnMissionStart 0x257790. fts_mission.cpp: the entity loop of
  CMission::OnMissionStart. seal_cfg.cpp: CZSealBody::BindAnimSet(const char*) 0x27e9a0.
- seal_ai.cpp: sealai::get_state(const char*) 0x26c290, get_aiseq 0x26c210 (on_aware0..4/X, was
  all on_aware0), get_stance x2 0x26c1a0/0x26c0c0, OnMissionStart 0x26ae40, SetStance 0x261d00,
  SetStanceDelayed 0x261ac0, DoSetStance 0x261740, SetupAnimations 0x261660, ActivateEx 0x260830,
  AttackTick's TARGETING/PURSUE push (0x2630f0..0x2633f0).
- seal_aistate.cpp: CAiState::Signal 0x2dbdc0 (full), CanPushAiState 0x2db7c0 (mask table
  0x4576f0), PushAiState's script response part, UpdateStackFlags' critical bit, StateTick's
  response wait, Create's reset, ActivateSeq 0x2d96c0, CAiSScript ActivateSequence 0x2d9570 /
  GetStatus 0x2d94e0 / OnSignal 0x2d91a0 / CanPursue 0x2d9130 / KillResponse 0x2d9040 (artifact
  of this file; no skeleton fence existed, added beside the others) / Tick 0x2d8d50.
- seal_airesponse.cpp: CAiSTarget Tick 0x2e5db0, OnSignal 0x2e5e10.
- seal_tasks.cpp (Begin/Tick/End only: the mission anims are compiled in m8 mzanim.zar, Parse is
  never called): CTDebug::Tick 0x2bdb70, CTHold Begin/Tick/End 0x2bbf30/0x2bbe50/0x2bbda0,
  CTParam::Tick 0x2b8230, CTStance Begin/Tick/End 0x2b5f70/0x2b5de0/0x2b5eb0, CTMacro Begin/Tick
  0x2babe0/0x2baa30, CTSetMode::Tick 0x2b7250, CTSetAnimSet::Tick 0x2b7050, CTPursue Begin/Tick
  0x2b80b0/0x2b8000. Record layouts (from the Parse functions) as TASK_* structs in the file.
- zai.h: CAiSScript members (+0x28..+0x4c), KillResponse decl, CAiSPursue::m_duration (+0x28).
- seal_kit.cpp is another worker's file: CZKit::HasSniperRifle 0x2af290 is in
  `edits/s_kit.rep.txt` (rep.py format; shared.txt applies it to the test tree); zseal.h's CZKit
  declaration returns bool now (mine).
- s03 (boot-actions SetGoalPos/SetGoalDir/ClearGoal): the first worker's versions in seal_ai.cpp
  are kept (SetGoalPos returns bool, SetGoalDir returns the facing dot): AttackTick 0x2626c0 uses
  SetGoalDir's f0 as the facing dot, so the value is returned in the ELF; s03 dropped it.

## Script command ids (m8 mzanim.zar, set 2 = ai::, registration order)
1 ACTION, 2 COMM, 3 DEBUG, 4 DOOR, 5 EVENT, 6 FIREMODE, 7 FIREWEAPON, 8 GOTO, 9 HOLD, a INSTATE,
b INVIEW, c LOOKAT, d MACRO, e MAP, f MOVE, 10 PAINT, 11 PARAM, 12 PURSUE, 13 ANIMATE, 14 INRANGE,
15 INREGION, 16 SELECT, 17 SETMODE, 18 SETANIMSET, 19 SIGNAL, 1a SOUND, 1b STANCE, 1c STATE,
1d STOPALL, 1e SPECIAL, 1f TEAM, 20 VALVE, 21 WAIT. Use counts in all m8 AI scripts: GOTO 447,
HOLD 373, DEBUG 349, STANCE 251, MACRO 164, SETANIMSET 146, LOOKAT 141, ANIMATE 125, PURSUE 56,
SIGNAL 47, STATE 36, SETMODE 32, SOUND 28, PARAM 26, COMM 5. `zseq.py <zar> <anim>` dumps them;
`_t/allseq.txt` = every *_start/_ambient anim. Not written: GOTO, LOOKAT, STATE, SOUND, COMM,
VALVE, WAIT ... (their Ticks return "not done", the sequence waits there).
GOTO record: +8 speed, +0xc u16 flags (bit0 wait for arrival, bit1 armed (Begin runs only then,
End re-arms after arrival), bits 2-9 count, bit 14 several waypoints, bit 15 random spot in each
loc's region), +0x10 locs as u32 (mapid<<26 | x<<13 | y). Begin: SetRoute, speed, AIM_PATH, stand.

## Port deviations (flagged in the source)
- CanPushAiState: only UNKNOWN, SCRIPT and TARGETING may be pushed (other states' Ticks are not
  written). Because PURSUE is refused, AttackTick's 1-in-4 TARGETING draw repeats every frame, so
  an engaging enemy targets within a few frames.
- AttackTick: the guard-region test (CAiMaps::GetRegionTypeContainer, stub) counts as "not in
  one"; the unit order test reads no unit (ELF reads m_unit+0x4c unguarded).
- CTParam: inside/outside tests (9, 10: AI map cell flags) hold without testing.
- Signal: the AI log record (PutAiLog) is left out. Void returns where the ELF returns a flag no
  port caller reads (ActivateEx, ActivateSeq, SetupAnimations, BindAnimSet(name), CZAnim::Pause/
  Resume).

## ELF quirks kept
- CAiSScript::GetStatus returns the anim's name, not the status buffer.
- CAiSScript::OnSignal(3) asks SequenceRunning and drops the answer.
- ActivateEx / CTMacro write the new script state's anim through a possibly NULL pointer.
- CTParam reads the courage *value* in compares but assigns the courage *goal*.

## Tools added here
- `z.sh <start> <end|+size> [argN=Class,reg=Class]` (Git Bash) -> dis.sh | disx.py | `cz.py`:
  compact listing; `off.py <Class> <hex>...`; `vt.py <addr> <n>`; `survey.py <file-regex>`;
  `rs.py <va>...` C string at an address; `zseq.py <zar> <anim>` compiled zanim sequences;
  `default.sh` default build (~/.cache/socom/ai-default); `b.sh <build> <pad> [nohook]`;
  `_t/joinnl.py` rejoins string literals a shell layer split at "\n". asm/*.txt = listings read.
- Builds: a4 (hook: nearest enemy 40 in front of the player), a8 (fake pad, no hook).

## Survey (ELF, first worker)
- Tasks (st_core.cpp): ai_pre_tick 0.9 `CSealCtrlAi::PreTick(f,void*)` 0x2b3880 (snooze LOD),
  entity_pre_tick 1.0 -> CZSealBody::PreTick -> `CSealCtrlAi::PreTick(f)` 0x2675e0, entity_tick 4.6
  -> `Tick(f)` 0x268880, ai_direg_tick 4.7 `PrePostTick` 0x2b3600 (sight lines), diTick 5.0,
  entity_post_tick 6.0 -> `PostTick(f)` 0x268530 -> SensorTick, ai_post_tick 10.6 0x2b33b0.
- PreTick(f): m_target.Tick, UpdateViewCone, SensorPreTick (-> AttackTick, EventTick, per-target
  avoid/CQB, _GetTargetPerception), StateTick, mode switch (Idle/Hold/Path/Creep/Slide/Follow).
- Tick(f): ScanTick, reaction choice, CAiDecay ticks, aware valve, under-fire -> STATE_SHOTAT.
- Target choice (SensorTick 0x2b1110): the last visible enemy whose threat is >= the previous best
  (raised weapon 0.35, hostile 0.3, facing 0.35, fading with distance) - so an idle player can lose
  to teammates further away (seen in a3: Bailey at 105 before the player at 36).
