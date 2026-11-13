# boot-deathcam notes (2026-11-07, socom-port-deathcam)

Scratch for the death camera and the single-player end of mission after the player dies.
Untracked. Changed files: `mine.txt` (three shared files carry only my hunks: edits/e04-e06, r04).

## Result (h1.log, hook build = HEAD 5fc02e8 + mine.txt + hunks + test-tree patches)
Fatal fall at player frame 200 (real HandleFallingDamage(300): level 3, every part's health,
UpdateHealth -> SetHealth(0) -> OnDeath, death anim 157), nearest enemy OutPatrol4 made the killer
first (real HandleKiller). Then, all from the ELF code:
- 0-2.5 s tether on the dying body (init_dying -> tether_initial_dying), HUD "KILLED BY: Iron Brother".
- black flash 0.2/0.2/0.2, camera follows the killer 3.2 s (tether_killer), flash 0.3/0.2/0.2,
  back on the body (auto_rotate_body): eye orbits the body at 0.8725 rad/s (r ~17.8, y 20.1),
  flashes 0.9/0.1/0.5, stuck darkening 0.8 (fade-in -0.1), 1.1/0.2/0.5, stuck 0.4.
- FadeToEndMission(0.01, 0) at +18.8 s -> MissionFadeToEnd task: long black flash (0.8/5/0.8),
  1.1 s later _OnMissionComplete, black screen, flashes deleted, ResetDeathCam,
  theGame.Push(&m_exitState).
- CExitState::Init: debrief dlgExitState.rdr (readerx.zar, extzanim.zar) "MISSION FAILURE",
  stats teletype (DIED 1 for Kahuna), MUS_FAILURE. Stable >90 s, no STOP (h2.log).
- d1.log: default build (fresh tree HEAD + mine + hunks, no hooks) boots to the main menu.
- Screenshots: build/port/screenshots/13-death/2026-11-07_1814_*.png (= h1-63/65/67/71/79/100).

## Test-tree-only patches (diag.sh: stubcmd.py from boot-fx + diag.py; never in the repo)
- HEAD STOPs at the m8 start: the objectives anim runs UI_COMMAND PlayMPEG run/movies/0122.pss
  (UIPlayMPEG nonvoid stub), then HUDTriggerMissionCamTick, CmdTickIsPlayerNode (same seen by
  boot-fx d7 and boot-weaponsel h3). stubcmd returns 1; UIPlayMPEG held at 0.
- With those, all four end valves + nofade read 1 within 3 frames (h1 first runs: mission
  "complete" 2 / aborted 4 at once -> debrief). The repo's OnMissionComplete is now the ELF one,
  so this would end the mission at once in a real build: HEAD's valve/zAnim code (fx worker's
  rewrite in progress) must not set them. diag.py makes CMission::Tick ignore the end valves.
- GetDeadCamPoints trace every 30 calls (DIAG: deadcam).

## Tools
Copied from boot-shapes (paths fixed). New: build.sh <build> <-D...|-> [pad] (sync + diag + fake +
hook), build_default.sh <build> (fresh clean tree + hunks, plain link), sync.sh (tree.sh + the
shared-file hunks over HEAD copies), hook.sh + hook_death.cpp (GetTerrainMotionFactor wrap:
SOCOM_HOOK_KILL_FRAME, SOCOM_HOOK_KILLER), edits/ed.py (old/new blocks, SOCOM_REP_ROOT),
edits/ed2rep.py, disc/ (readerx.zar, m8 mzanim.zar from the user's disc image; scratch only).

## Not written / next
- Debrief buttons do nothing (h2: X at reads 1300-1600, TRIANGLE 2500-2700, no anim):
  CGameMenu::HandlePad 0x382f00 -> ZAnim.GetAnim("ExitOnCross", NULL) does not find the dialog's
  own anims in the port (zUI/zAnim, other workers' area). ExitOnStart (event) runs.
- Replay (X): OnReplayMission -> Pop(1) -> CCoreState::OnPop 0x17d7f0 (stub): reload texture
  phases, m_wait_before_falling 10, CameraZoom::SetGoal(1), CMission::ReOpen_Load 0x1f79a0 (624 B:
  CreateSinglePlayerUnits 2796 B, ftsFixupAiMap 3680 B, Sample_ExtractionLoc, valves ...),
  OnMissionStart, AttachSeal(player), CHUD::ReInit_Init. Today it would resume the dead
  mission (death camera again -> debrief again).
- ReOpen_Unload1 0x1f7c60 (740 B, ~40 calls: compass anchors, decals, tasks, AI, anim sets,
  DestroyAimAnims S!, units, valves, HUD, particles, CPipe::Flush, ClearPktBufs) and
  ReOpen_Unload2 0x1f7c10 (RemoveAll, AiEvent, lights/shadows, GarbageCollect): stubs (nothing
  is freed; the debrief costs +0.5 MB).
- Briefing (TRIANGLE): OnCloseAndSwitch -> Pop(0) + Switch(m_menuState): CCoreState::UnInit /
  auxUnload (core teardown) unwritten.
- CCinematicState (UIPlayMPEG's movie state), UiSetCounterSpeedFactor (zui_2d void stub),
  CSealUnit::Notify, DoRespawn / piggy-back (stubs reached only by SELECT+X / multiplayer).
