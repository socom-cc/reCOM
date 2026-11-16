# mod-final notes (2026-11-14, socom-port-mod-final): the last unwritten functions and the marker sweep

Scratch `build/port/boot-mod-final/` (untracked: NOTES.md, mine.txt, the surveys and marker lists before / after,
the disassembly dumps `asm_*.txt`, the edit scripts `fix_*.py`, `buildall.sh`). Changed files: `mine.txt` (every file
was free at HEAD 7976a660).

## State
- `survey.py Apps/FTS`: stub fences 5 -> 0 (956 -> 0 B); written 244,788 -> 245,744 B. Every module now surveys at
  zero empty functions.
- Lines under `src/` matching `port: stub`, `port: not written` or `not written`: 68 -> 0 (table below).
- All runs below on the final tree (HEAD + mine.txt): no STOP, no exception; focus kept in every run.

## Runs (screenshots under `build/port/screenshots/52-final/`)
- mfst (zseal4's scratch stability hook + `pad_fire.txt`, 210 s: intro movie skipped with CROSS, briefing cameras
  with X, firing): enemies fire at the player (36 bursts), two enemies killed, one respawned and one recycled, the
  team FOLLOWING (Hutchins 31, DiMone 151 units from the player at 148-208 s); heap in use 23.00-23.12 MB over
  60-209 s; the idle AIs' new look directions traced ("IdleTimer Expired! New Look Direction").
- mfw (`port/test-hooks/win`, -DSOCOM_HOOK_WIN): Snow3 rescued in Extract (206.5 s), mission_complete 0 -> 1,
  "EXIT: debrief open (objectives 3/7)", MISSION SUCCESSFUL on screen (run mfw3). Runs mfw / mfw2 had the same
  result but no picture: the emulator window was minimized at shot time; mfw3 used a scratch watcher that restores
  the window without activating it.
- mfsr (`port/test-hooks/state`, -DSOCOM_HOOK_MISSIONS=8): in use 18,666,708 B at return 1, then 18,666,804 B at
  returns 2-8 (flat, as at HEAD).
- mffe (fake pad, zui2's `pad_fe.txt`): main menu -> OPTIONS -> audio, video, controller selection, presets, back
  to the main menu; no STOP.
- mfdef (default build: no hooks, no fake pad): boots to dlgMenu at 15.8 s; process_arguments sees argc 1.

## Written (ELF addresses)
- `getopt` 0x173ab0 (getopt.cpp): the public-domain getopt with g-prefixed globals; `-:` / unknown option / missing
  argument answer '?' with `goptopt` and a message on stderr while `gopterr`; "--" ends the options.
- `process_arguments` 0x173e30 (options.cpp): the defaults (zSys.cdSounds 0, CZAnimMain::m_LoadFromZAR and
  gopt.LoadZAnimFromZAR 1, theVoice.m_do_voice 1), the short options `d:p:m:V:hfFaAszZR` (database, root path,
  frame rate, the HUD / status line / FPS / AI / shadow switches, ZAR loading), `SetAiEnabled(gopt.enableAi, true)`,
  Medius on, then the long options against every word (--AP, --ammo, --cdsounds, --nosounds, --displaysounds,
  --debugmusic, --ffire, --nofireanim, --noimpactanim, --nowepintersection, --ailog, --noenemy, --noalpha,
  --nobravo, --aid, --isolate <name>, --noaifilter, --player_grid[n], --noobj, --nodie, --nosee, --log, --dumplog,
  --nomenu / --menu, --invert_pitch, --pad2, --squirm, --two_player, --no_radar / --radar, --multi, --medius /
  --nomedius, --nomemcard, --voice, --voiced, --noghost, --e3seal, --e3terr, --dlgrdr, --nodi / --noalt / --noint).
  New statics with no owner annotation, placed with seal_ai.cpp's data: `CSealCtrlAi::aiDebugEnabled` 0x475d64
  (CTGoto::Begin's debug print now tests it, 0x2bc870), `CSealCtrlAi::aiCameraRangeFilter` 0x474f60 (1; only
  written), `ai::isolate_character` 0x43a370 (CMission::LoadVehicle's isolate test 0x1fd248 now written).
- `COurGame::StopEngine` 0x140520 (CGame::StopEngine, theLobby.UnInit). `COurGame::StopPlay` 0x140500 / `StartPlay`
  0x140510 are not bare returns: each is a tail jump (`j`) to CGame::StopPlay / StartPlay; written as calls.
  `ai::plot_tick` 0x17de80 is a bare return (`jr ra; nop`), written so with a comment.
- CMission::LoadVehicles 0x1fd708: the extra player copies' controllers read pad i (`m_padid`).
- zSeal: `CDiPool::~CDiPool` 0x2b3e40 (at exit); `CTParam::Tick` 9 / 10 0x2b8d1c / 0x2b8f54 (the m_inside flag of
  the seal's AI map cell); `OKToPeek` 0x286f70 (the L / R lean's ray test; zbody.h friends it); `IdleTick`'s new look
  direction 0x264c20 (ChooseLookDir was already written); `LadderClimbTick`'s `_look` static; `DestroyAimAnims`
  0x29cbf0; `CAiState::Create(STATE_LASING)` is the plain CAiState as the ELF's table 0x457810 has it; CAiSAction's
  route phase tests GetActionById's answer (0x25f06c).
- zAI: `CAiMap::GetBilinearAltitude` 0x19a820 (no fence; ai_maps.cpp, declared in zai.h; ftsGetAltitudeApprox
  0x1f2360 uses it on bilinear cells); `CAiMaps::CreateGraph`'s build 0x1981a0 (only for a set without a graph).
- zFTS: `_actionValveCallback` 0x1ff7d0 (an action valve's value becomes the AI map action's state); CMission::Close's
  network resets 0x1f71a4 / 0x1f7554; CMission::Tick's network game 0x1f6bb8; OnMissionComplete's network round end
  0x1f6240; `zNetRegister{Bomb 0x207a30, Grenade 0x206d20, Game 0x206770, Persona 0x209500, Seal 0x205930}`;
  NetFreeObject at 0x206a24 / 0x206e74 / 0x204570.
- Orders menu (orders.cpp): the vote entries 0x17b8b4, the vote sent 0x175714 / 0x175794, the network renaming of an
  order from the player's character 0x178a38.

## Outside src/
- `port/compat/dme_offline.cpp` + `include/dme.h`: offline stand-ins for NetRegisterObjectStart, NetObjectField,
  NetRegisterStructure (0, ids 0), NetFreeObject, NetSendObjectFullUpdate (not available).

## Findings
- Arguments: the PCSX2 boot passes argc 1 (argv[0] the ELF; traced by process_arguments), so getopt answers -1 at
  once and no long option matches: no option takes effect. Against what the port set by hand before, the ELF also
  sets `gopt.LoadZAnimFromZAR` 1 (nothing reads it) and `theVoice.m_do_voice` 1 (offline harmless: CZNetVoice::Init
  is network-only, UnInit returns while `m_uninited` is 1 as in the ELF, Channel is network-only); the
  SetAiEnabled(1, 1) call changes nothing (AI starts enabled).
- The AI-state push gate: the port's own gate refused only STATE_LASING; the ELF's CanPushAiState 0x2db7c0 is the
  rest of the port's function state by state (masks, SUSPENDED, the critical-section list, CQB). With LASING created
  as the ELF does, the port's gate is gone.
- SendVoteMessage 0x202660: the voted seal is marked only when found (the store follows the NULL test's delay-slot
  nop); the port had written it through NULL.
- Voice recognition never starts in the ELF: recoShouldInit 0x476844 starts 0 and its only writer stores 0, so
  recoInit2 answers 0 and the gsapi set-up after it is unreachable.
- The disc's AI map sets: RUN/SP/M8/AIMAPS.MPS (all version 19) and RUN/UI/AIMAPS.MPS (no maps): the old map
  formats have no data.

## The team mate who stopped following (Hutchins, the zSeal part 5 run)
- Original behaviour; no code changed. In that log (169.2394-169.2571) Hutchins was killed, not stunned: OutPatrol1's
  second M67 detonated 90.2 units away (radius 150, 113.2 damage at the body); HandleGrenadeExplosion's fragment
  (DamageRandomLocation 0x28f490: r in [0.1, 0.4) is the body, location 3, DamageBody) took the body's health, so the
  seal died ("dead (alive valve 0)", "killed by the blast", OutPatrol1's "tango down" callout). CSealCtrlAi::OnDeath
  0x2699b0 tells the unit (CSealUnit::Notify(seal, 1) 0x269a9c) and pops every AI state with ClearAiState(true)
  0x269aa8: grenade, pursue and follow go, and nothing orders a dead member again. The port's OnDeath and
  DamageRandomLocation match the ELF (the location thresholds 0.1 / 0.4 / 0.55 / 0.7 / 0.8, the head levels, the
  message, the forced clear).
- After his first blast in the same run (161.9 s, 120.9 units, a fragment in the right arm, stunned and recovered at
  162.9 s) the stack kept FOLLOW at its bottom: at 164.73 s his GRENADE state ended and FOLLOW resumed ("EXITING
  [grenade] ... RESUMING [follow]"), which is the recovery path for a team mate who survives a blast.

## ELF quirks kept
- process_arguments: "m:" takes an argument and has no case; -V falls through into -z (ZAR loading off, valid rate
  or not); --isolate copies the next word and the later long options test that word; --nodi / --noalt / --noint
  latch (their message repeats for every later word); --player_grid without a number gives 16.
- getopt: the "--" test also runs in the middle of a word.
- Votes: VOTE_OFF sends a vote of 1 too; the voted entity is read as a seal without a test. The order rename runs
  the message text through sprintf as its own format. CreateGraph asks a NULL map for a link past the set's end.
  The copies' m_padid store does not test the copy for a seal. ~CDiPool leaks m_active's requests. The network round
  counter compares the old 16-bit valve value with the 32-bit count.

## Port deviations
- process_arguments traces argc / argv[0] (SOCOM_PORT). DestroyAimAnims reads the untyped 12-byte m_aim_anims
  placeholder as the ELF's words (no DWARF element type; nothing fills it, in the ELF either).

## Marker sweep (68 lines -> 0)
| where | marker | what happened |
| --- | --- | --- |
| Apps/FTS/game/orders.cpp (4) | MP votes, MP order rename | written (0x17b8b4, 0x175714, 0x178a38) |
| Apps/FTS/game/reco.cpp (2) | gsapi set-up / release | reworded: unreachable in the ELF (recoShouldInit never set) |
| hud_scorepopup.cpp (2), con_main.cpp, con_packet.cpp, zrdr_archive.cpp, zsys_init.cpp (2), ztwod_holding.cpp, ztwod_poly.cpp, zNetMedius.cpp (3) | "port: stub X (no owner in the render)" | stale: all written and checked against the ELF (destructors / one-liners); reworded "no skeleton fence for X" |
| zAnim/zanim.h (2) | inline dtors | stale: reworded (base destruction only, 0x1d0030 / 0x1cff10) |
| zAnim/zanim_menu.cpp (2) | CNetCnf / lobby "not written" | stale: reworded (online-only; the providers are offline) |
| zAI/ai_mapio.cpp (5) | map versions 2-18, old cell formats | left out on purpose: no such map on the disc; the needed functions named |
| zAI/ai_maps.cpp (2) | ReadMapSet note, CreateGraph rebuild | stale note removed; CreateGraph written |
| zFTS/fts_action.cpp | _actionValveCallback | written (0x1ff7d0) |
| zFTS/fts_main.cpp | GetBilinearAltitude | written (0x19a820) |
| zFTS/fts_mission.cpp (6) | Open's comment, network Close / Tick / round end, an old fix note | written (0x1f71a4, 0x1f7554, 0x1f6bb8, 0x1f6240); comments reworded |
| zFTS/fts_net_bomb / game / grenade / persona / seal (9) | structure registrations, NetFreeObject | written (compat stand-ins added) |
| zFTS/fts_player.cpp (2) | isolate test, copies' pad id | written (0x1fd248, 0x1fd708) |
| zNode/node_io.cpp, zUI/zui_2d.cpp +0x35, zVisual vis_main.cpp, zvis.h (2) | ELF facts ("not written" = never stored) | reworded "never stored" / "never saved" |
| zRender/zrndr_pipe.cpp | CZMarkList "not written" | stale: reworded (the port guard stays) |
| zSeal (9) | ChooseLookDir / idle look, push gate, DetachBody, peek ray test, CTParam 9/10, _diPool dtor, _look, aim anims | written; DetachBody's marker stale |
| zUI/zui.cpp | MPEG background | kept out (recorded port decision); reworded with what playing it needs |
| zUI/zui_2d.cpp (P1 note), zui_spec.cpp trace | stale / misleading | reworded (the spec trace is for types the ELF does not know) |
| outside the grep: seal_ai.cpp "GetActionById is still a stub", zanim_cmd_tick.cpp "CZAnimFromToAcc::Tick is a stub" | stale | code follows the ELF (CAiSAction) / comment removed |

## Not written / left
- The zVid_Swap frame limiter (deferred by the user) and the memory-card layer (`port/compat/libmc.c`) are untouched.
- The menus' MPEG backgrounds (zui.cpp, recorded decision). The old AI map formats (no data). The reco set-up
  (unreachable in the ELF).
- 2026-11-15: the MPEG-background decision is reversed: the menus' movies play now (`docs/port/notes/mpeg-background.md`).
- Everything network-only written here is untested (no network game on the demo disc).
