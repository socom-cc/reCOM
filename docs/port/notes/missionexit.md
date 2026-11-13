# boot-missionexit notes (2026-11-12, socom-port-missionexit)

Scratch for leaving a mission (death -> debrief -> TRIANGLE -> briefing) and starting it again.
Untracked. Changed files: `mine.txt`; edits of other workers' files: `edits/*.txt` (srep format).

## State / next step (latest first)
- DONE 17:48, rt3.log (me-t8 = HEAD 231c093 + mine.txt, test edits t_state/t_fire, death hook
  frames 200 and 4050): mission 1 CoreState 61.9 s -> death 65.3 -> debrief 84.9 -> TRIANGLE ->
  menu 96.0 -> (PLAY GAME, briefing, START) -> mission 2 CoreState 132.0 -> firing: 20+
  CZMarkList::AddNewMark impacts 135-194 s, footprints -> death 192.2 -> debrief 211.8 -> TRIANGLE ->
  menu 218.7 -> main menu. No STOP / TLB miss. Heap `use`: boot menu init 10.34 MB; after round
  trip 1: 7.79 MB; after round trip 2: 7.91 MB (+0.12 MB per trip, not chased). brk keeps rising
  (0x19f2000 -> 0x1ee4000 at the third menu): fragmentation; heap end 0x1fdf000.
  default.log (me-def, build_default.sh, no hooks/pad): boots to the main menu.
  Screens: build/port/screenshots/20-mission-exit/.
- Next (not done): the per-trip +0.12 MB and the brk growth; replay (X) needs ReOpen_Load.
- 17:45, HEAD 231c093 (has the _delete fix, AI movement, pickups). rt2.log (me-t7): full round trip
  works: death 59.7 s -> debrief 79.2 -> TRIANGLE -> menu 90.4 (use 7.80 MB; boot menu 10.34 MB) ->
  the fake pad's held TRIANGLE lands in the new briefing (UiBackWhere -> main menu: test artifact),
  so the pad goes PLAY GAME again (read 1450) -> briefing -> DOWN x5 + CROSS (1605) -> load ->
  mission 2 CoreState Init 126.3 s (use 21.76 MB vs 21.63 the first time) -> stable to 216 s.
  rt3 (me-t8, running): adds firing traces (edits/t_fire.txt) and a second death
  (SOCOM_HOOK_KILL_FRAME2=4050) + TRIANGLE at reads 4350/4450 for the third heap reading.
- pickup_main.cpp: my partial CPickup::Close was dropped; HEAD's full one (pickups worker) is used.
  (I restored that file with `git checkout --`; it differed from HEAD only by my include line.)
- ai_astar.cpp: the aimove worker's FlushPlannerQueue (HEAD) replaces mine and does the same.
- 2026-11-12 13:00, t25.log (me-t7: tree + edits/e08_delete.txt): ROOT CAUSE of the leaks found:
  HEAD's `_delete` (zsys_memory.cpp, 0x2f48a0) was an empty stub, so every non-pool operator delete
  leaked. Another worker has the same fix uncommitted in the working tree (not mine; my test tree
  applies it through shared.txt). With it: menu init at boot 10.34 MB, back at the menu after the
  mission 7.80 MB, briefing (dlgAlaska_mission3) up again at 104 s. Next: pad presses for START in
  the second briefing (calibrate read numbers), then 60 s in mission 2 with firing.
- Also fixed on the way: zdb::DiIntersect default ctor (zintersect.h; ELF __defctor passes 8) - the
  empty one left m_Intersects unset and ~CZSealBody freed a wild pointer (0x3f400000).
- Debug hooks (test only): hook_free.cpp (HFREE=1), hook_leak.cpp (HLEAK=1, edits/t_leak.txt).

## Older state
- t0.log (HEAD + death hook, no source changes): death 58 s, debrief 77.5 s (use 25.9 MB), TRIANGLE at
  read 1350 -> Pop(0) ExitState, Switch CoreState -> MenuState, CMenuState::Init "loading world ui"
  at use 27.66 MB (brk 0x1f7e000, heap end 0x1fdf000) -> log ends (out of heap: nothing released).
- Unload chain written (see "Written"); all held edit files are applied to the repo now (AI and
  grenades work committed: 978c1b1, ff2c53b); edits/applied/ keeps them for reference.
- t1.log: after the debrief + TRIANGLE use drops to 15.05 MB (menu init at boot: 10.57 MB), then
  TLB misses in newlib _free_r right after UnloadTheWorld (heap corruption) and CMenuState::Init hangs.
- Hunting it with hook_free.cpp (HFREE=1 build: remembers released pointers after HFREE armed in
  CCoreState::OnPush via edits/t_arm.txt, traces a second release with its caller). t5 = that run.

## Tools (this folder)
Copied from boot-decals (paths fixed to boot-missionexit / tree-missionexit); hook_death.cpp + hook.sh
from boot-deathcam (SOCOM_HOOK_KILL_FRAME, SOCOM_HOOK_KILLER). New: `build.sh <build> <-D..|-> <pad-file>
[test edits]` (tree.sh, test-only srep edits restored next build, fake.sh, hook). `go.ps1 <build> <run>
[s] [shots]`. Test edits: `edits/t_*.txt`.

## ELF path (single player, failure debrief, TRIANGLE)
1. Death -> FadeToEndMission -> _OnMissionComplete -> theGame.Push(&m_exitState).
   CCoreState::OnPush 0x17d8c0 (FIFO end, GS sync, pad bytes 12/13 = 0).
2. CExitState::Init 0x320740: ReOpen_Unload1 0x1f7c60, SetRoundStatUiVars, ReOpen_Unload2 0x1f7c10.
3. TRIANGLE -> ExitOnTriangle (CurrentMission 8 -> CloseAndSwitch dlgAlaska_mission3.rdr):
   OnCloseAndSwitch 0x1d70a0: m_DefaultMenu, Pop(0), Switch(&m_menuState).
   Pop: CExitState::UnInit 0x3205c0, CCoreState::OnPop(0) 0x17d7f0 (HUD tex buffers, m_skip_swap 2;
   index 1 = replay: ReOpen_Load ...).
   Switch: CCoreState::UnInit 0x17cc70 -> auxUnload 0x17c850 (tasks, projectiles, testUnload 0x1735e0
   = CMission::Close 0x1f7180 + UnloadTheWorld 0x1728e0, MarkList UnInit, DestroyBuffers, ReleaseHUD,
   player NULL, projectile/mark lists, readerm.zar), CValve::Reset, ClearFreeList, MaxFrameRate(-1).
   Then CMenuState::Init.

## Stubs on the path (stubchk/fences/ctree at the start) and what became of them
Written (ELF address; file):
- CCoreState OnPush 0x17d8c0, OnPop 0x17d7f0, UnInit 0x17cc70, Unload 0x17ca80, auxUnload 0x17c850
  (st_core.cpp); testUnload 0x1735e0 (database.cpp, was `return false` -> auxUnload would exit(0)).
- CMission Close 0x1f7180, ReOpen_Unload1 0x1f7c60, ReOpen_Unload2 0x1f7c10 (fts_mission.cpp).
- CValve Close 0x2f6410 / Reset 0x2f6530 (valve_list.cpp; identical bodies in the ELF: temporary
  valves back to the pool, name buffer rewound when no pooled name is left).
- CHUD::ReleaseHUD 0x3bc010 (hud_main.cpp); C2DMessage_Q::Clear_Messages 0x200920.
- CEntity RemoveAll 0x1ef010, ~CEntity 0x1ee7b0 (ent_main.cpp); ~CZSealBody 0x256fe0 (seal.cpp);
  DeleteCameraEffectsNode 0x289830 (seal_create.cpp); CBody::Destroy 0x1df610, ~CBody 0x1df870,
  ~CZBodyPart 0x1e3850, CZBodyAnimCallbackList::Clear 0x1df300 (body.cpp); ~CZSIScript 0x1de430
  (si_script.cpp); CZKit::UnInit 0x2ae910 (seal_kit.cpp).
- CZSealBody UninitDatabaseHandles 0x292210 / Uninit_ReInitDatabaseHandles 0x2921d0 /
  DestroyAimAnims 0x29cbf0 (seal_env.cpp); CSealCtrlAi::ReleaseDatabaseHandles 0x26c030
  (seal_ai.cpp); CSealUnit::UnInit 0x2d5570; ClearBodyPartNames_Map 0x280e80;
  CCharacterType::ClearMultiplayerMessageSounds 0x247bb0.
- CWorld ClearLightMapList 0x22dda0, ClearShadowList 0x22dcc0, DeleteLightMap 0x22fa80,
  WipeoutTextureAssetCharacters 0x22de80, DeleteTextureAssetCharacter x3 (0x22e070/0x22e1f0/0x22e240).
- CTexManager::ClearPktBufs 0x2fa130; ~CMissionCam 0x20afc0, ~CMissionObjectiveCam 0x20ab90,
  CMissionObjectiveCamList::ClearValves 0x20a830.
- AI maps: CAiMaps Close 0x19d4e0 / FreeTables 0x19d570, ~CAiMap 0x186c20, CAiMap FreeEx 0x19f330 /
  DestroyGraph 0x19dca0, ~readers 0x19e5c0, ai::FlushPlannerQueue 0x1811c0 (cell validation part).
- CPickup::Close 0x24d4a0 (bomb node part).
- Signature fixes: CZWeapon::RemoveWeaponEventCallback, CAiDodge::Destroy, CZSealBody::DestroyAimAnims
  are static (the ELF passes no object); DiIntersect(s32 count = 8) (__defctor 0x258eb0).
Bodies with a "port: not written" note (placeholder lists never filled in the port): CAiEvent::Close
(bit_count + CloseAll written), CAiVisMap::CloseAll, CTextureFX::Clear, CSpawners::Clear,
CAiDodge::Destroy, DestroyAimAnims; CMission members m_navpoints/m_objanchor_vec/m_ladders/
m_missioncams are not declared (their loaders are unwritten).
Still stubs (reached, harmless calls): CZAnimSet GarbageCollect/Reset (+CZAnim/CZAnimSetSave/
CZAnimExVector/CZAnimEx Reset; zAnim files were another worker's), CClutterAnimManager ClearEffectors/
ClearAnimations/UnRegisterEffector (guarded: the manager is never made), CSealCtrlAi::CloseDiPool,
CCompass::DeleteAnchor/Close (declared members, ELF static; nothing creates anchors), network
branches (ftsNetworkGameUninit, DMEDisconnect...). Replay (X): ReOpen_Load 0x1f79a0 unwritten.

## ELF quirks kept
- PERM/PERSIST valves survive CValve::Close/Reset (only TEMP ones go back to the pool).
- ClearBodyPartNames_Map keeps the names table and count; DeleteTextureAssetCharacter ignores its
  library argument; CZBodyAnimCallbackList::Clear swaps the global; CBody::Destroy reads Top once.
- Front-end music: m_num_streams_used goes to -1 when the first menu's theme is refused (max 0) and
  released, after which streams play without VAG streaming (same accounting in the ELF).

## Port deviations
- Guards: ~CZSealBody / ReOpen_Unload1 skip the clutter manager when NULL; CAiEvent::Release only
  with an event (Acquire unwritten).
- DeleteAnchor called through CZSealBody::m_compass (declared member; ELF static).
