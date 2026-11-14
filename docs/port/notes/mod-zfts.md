# boot-mod-zfts notes (2026-11-13, socom-port-mod-zfts): completing the zFTS module

Scratch `build/port/boot-mod-zfts/` (untracked). Changed files: `mine.txt`; shared-file edits: `shared.txt` +
`edits/` (srep format). Network helpers' output: `helper-remote/b/`, `helper-netstate/` (rep.py blocks;
`helper-remote/remote.rep.txt` at the folder root is an earlier helper's version, not used).
In-place changes outside zFTS (free at HEAD): zUI (debrief counters), zEntity (recycler), zNetwork, zchar.h.

## State
- DONE (HEAD fc0ed628 + mine.txt + edit files). `survey.py gamez/zFTS`: 0 stubs left (was 154 / 40452 B);
  80340 B written. Single-player functions tested; the network functions are written from the ELF, untested
  (no network game offline).
- zfw1 (`tb.sh -k win ... -- -DSOCOM_HOOK_WIN`): m8 playthrough 72-232 s, the AI-map pickups placed (4 ammo
  boxes, a 552 and an Uzi on maps 0/2/3), 1 extraction anchor, MISSION SUCCESSFUL debrief with every counter
  filled (TOTAL column, 3 OF 5 / 7 OF 8 objectives, 70 %), then dlgHype; no STOP.
- zfx1 / zfx2 (`-DSOCOM_HOOK_EXITPATHS`; zfx2 with the network code): pause ABORT -> MISSION FAILURE debrief
  (totals 0, 0 OF 5 / 0 OF 8, 0 %) -> X replay (ReOpen_Load, 41 entities incl. the 11 recycler slots) -> pause
  REPLAY -> ABORT -> debrief -> TRIANGLE -> menus (161 s); no STOP.
- zft1 (`tb.sh -k tacmap`, START pad, X skips the cameras): m8 73-240 s, no STOP / TLB, heap use flat at
  22.027 MB from 130 s on. zfdef / zfdef2 (`default.sh`): main menu.
- Screenshots (untracked): build/port/screenshots/40-zfts/.

## Survey at the start (HEAD df9c0ef; `survey.py gamez/zFTS`): 154 stubs, 40452 B
- Single player: CMission Sample_ExtractionLoc 0x1f25c0 (Open, ReOpen_Load), CreateLadderTable 0x1f5c40 +
  CLadderList GetClosestLadder 0x1f5a90 / GetLadderByIndex 0x1f5bf0, aiMapPlaceItem 0x1f5730 (+ the pickup part
  of ftsFixupAiMap), CSpawners::Tick 0x1fcb40, CMission::RecycleEntity 0x1fcc60, CftsPlayer::IsInside 0x1fdf90,
  CMission::GetGameTime 0x1f37d0 (HUD clock), CreateCustomCharTypes(_zrdr) 0x1fa8b0 (network PreOpen), the
  CftsPlayer anim-command parsers (0x1fdc20 / 0x1fdd80 / 0x1fde80), HUD_START_DEFUSE_TIMER (0x1f9760 / 0x1f9740),
  START/STOP_IMAGE_RECORDER (0x1f9e80 / 0x1f9e70 / 0x1f9e00 / 0x1f9df0), CMission Serialize / UnSerialize
  (0x1f3520 / 0x1f3460, save module).
- The debrief's COUNTER objects (zUI, not zFTS): CCounterSpec (inline ctor in GetObjectSpec 0x399e4c,
  CreateDisplayObj 0x399450), C2DCounter (Tick 0x392e40, TickZAnimCmd 0x392cf0, ParseZAnimCmd 0x392f70,
  GetZAnimCmdType 0x393160, dtor 0x394820), UiSetCounterSpeedFactor 0x393270, PlayCountSound 0x384630.
- Network / multiplayer: CZNetGame / CNetClock / CMission net functions in fts_mission.cpp (19), fts_net_seal (14),
  fts_net_persona (24), fts_net_game (7), fts_net_grenade (7), fts_net_bomb (13), fts_remote (41), fts_network (4),
  fts_network_dme (5).

## Written (single player; ELF addresses)
- Debrief counters (zUI, in place): CCounterSpec(_zrdr*) (inline, 52 B: StartTime, ValVar, EndTime or Duration),
  GetObjectSpec COUNTER branch, CreateDisplayObj 0x399450 (the ValVar UI variable's int value at creation),
  C2DCounter (inline ctor; m_startTime / m_isDuration / m_endTime / m_target / m_elapsed / m_shown at +0xac..+0xc0)
  Tick 0x392e40 (counts from the start time to the target over the span, each new number "%d" + the teletype
  sound), TickZAnimCmd 0x392cf0 (Start = count from now; Finish = target at once; Caption), GetZAnimCmdType
  0x393160, ParseZAnimCmd 0x392f70, dtor 0x394820; UiSetCounterSpeedFactor 0x393270; PlayCountSound 0x384630.
  The debrief's counters are made with StartTime 1e6 and Duration 1: the dialog's NODE Start command starts them.
- fts_mission.cpp: Sample_ExtractionLoc 0x1f25c0 (extraction regions of AI map 0 -> "EXTRACTION LOC" compass
  anchors, type 5); CreateLadderTable 0x1f5c40 + CLadderData (DWARF, 40 B) + CMission::m_ladders (+0x580; Close
  deletes it); CLadderList GetClosestLadder 0x1f5a90 (int: index | LADDER_MASK) / GetLadderByIndex 0x1f5bf0;
  ftsFixupAiMap's ladder ids and pickup part (0x1f481c: WEAPON / AMMO readers -> model instances, weapon (8) and
  ammo-box (9) pickups); aiMapPlaceItem 0x1f5730; GetGameTime 0x1f37d0 (int); CreateCustomCharTypes(_zrdr)
  0x1fa8b0 (network); HUDStartDefuseTimer Parse/Tick 0x1f9760/0x1f9740; Start/StopImageRecorder Parse/Tick;
  Serialize 0x1f3520 / UnSerialize 0x1f3460 (save module; the memory-card save path itself stays unused);
  TickInFirefight 0x1f2b30 rewritten (the old body told the jukebox "no fight" every frame: `=-` typo).
- fts_player.cpp: CSpawners (members from the asm: m_spawn list of {slot, vehicle entry}, m_pending, m_timer)
  Tick 0x1fcb40 / Clear 0x1fcb00; LoadVehicles' recycle entries (0x1fd620: CreateRecycler slot + spawn entry);
  RefreshTeamValves' spawner team bits (0x1fcff0); CMission::RecycleEntity 0x1fcc60; CftsPlayer::IsInside
  0x1fdf90 (bool); CmdParseIndoorsTest 0x1fde80 / CmdParseControls 0x1fdd80 / CmdParseIsPlayerNode 0x1fdc20.
- zEntity (in place, the spawners need it): the recycler (0x4bc400: placeholder entity of type ENT_TYPE_RECYCLE
  holding free m_list slots) - CreateRecycler 0x1ef430, RecycleEntity(entity) 0x1ef620, RecycleEntity(slot,
  entity, include) 0x1ef540, DoRecycleEntity 0x1ef240, CloseRecycler 0x1ef7a0, RemoveAll's recycler branches
  0x1ef010, ReplaceTargetList 0x1f0930; CftsPlayer::IsInside declared bool.
- Edit files (other owners): edits/hud_clock.txt (hud_main.cpp: CHUD::Tick's mission clock 0x3b9ba4 from
  GetGameTime), edits/recycle_seal.txt (seal.cpp CZSealBody::OnRecycleEntity 0x257720), edits/recycle_ai.txt
  (seal_ai.cpp CSealCtrlAi::OnRecycleEntity 0x267590).

## Written (network / multiplayer; untested)
- From two helpers' rep.py blocks (helper-remote/b, helper-netstate/part_*), applied by the worker; spot
  checks against the ELF (CNetClock::Tick, MyMajorGameState, ResetScores, CreateNetGame) agree.
- fts_mission.cpp: CZNetGame OnSealTeam (bool), DecrementRoundClockSec (unsigned, guess: nobody reads it),
  TenSecondLaunch (bool), SetE3Index, ResetScores, LateJoiner, My/MP major / minor game states, NetworkTeam,
  SetE3RoundCount, UnInitialize, MasterStartGame 0x1f3910 (its old body was empty); CNetClock Tick /
  SetInitialRead; CMission Create/DestroyNetGame, (_)RecoverFromNetError; CMission::m_e3_team (+0x660).
- fts_net_seal / persona / game / grenade / bomb.cpp: every CZSealState, CZPersonaState, CZGameState,
  CZGrenadeState, CZBombState function, with the network structures (TypeSealState 152 B, TypePersonaState
  724 B, TypeGameState 64 B, TypeGrenadeState 36 B, TypeBombState 16 B; names after the field ids, no DWARF)
  and m_RemoteGuyList / m_PersonaList as MSL lists.
- fts_remote.cpp (41: packet handlers / senders, client connect / join / leave callbacks), fts_network.cpp
  (ftsNetworkGameUninit, ftsNetworkSealInit, ftsNetworkPlayerInit, findAlign; ftsNetworkGameInit rewritten:
  it read CMission::netGame, the ELF reads m_pNetGame), fts_network_dme.cpp (DMEinit, DMERegister, DME
  Connect / Join / Disconnect; the DME SDK calls NetRegisterMessageStart / NetMessageField /
  NetRegisterApplicationMessage / NetSetMyClientObject are left out, flagged `port: not written`).
- Flagged guesses kept in the source: the packet struct names and fields, AckUnion / R_SEND_TO meanings,
  the PacketType* globals and CZSealBody::m_oktocallinit (defined in fts_remote.cpp / fts_network.cpp: no
  owner annotation), NetObjectRec / NetClientRec (znet.h, only the fields read), TypeRTimeFixStruct's tail,
  m_event_handler's second parameter.
- zNetwork (in place, free at HEAD): znet.h (CZNetGame::m_late_joiner +0x94, 1-byte MP enums, return types of
  zNetCreateObject / zNetGetObject / zNetGetGameClient / zNetConnect / zNetJoin / MediusConnectionIndex,
  TypeRTimeFixStruct, CZOnlineLobby m_event_handler / m_net_error_handler, friend CZPersonaState),
  zNetDme.cpp (signatures; stubs stay stubs), zNetMedius.cpp (MediusConnectionIndex). zchar.h:
  KorusGetPackedWeapons static.
- Edit files for other owners: edits/net_zseal_h.txt (m_TriggerCount u8, SetCurItemEnum bool,
  m_oktocallinit), edits/net_seal_kit.txt (CZKit::SetCurItemEnum returns bool), edits/net_zanim_h.txt
  (m_network_activation_callback(void *, int), CAnimAuxData::Get static), edits/net_anim_cpp.txt
  (CAnimAuxData::Get body). edits/dep_zai_h.txt + dep_ai_maps.txt are test-tree only (CAiMaps::
  GetSporeLocation as bool, which socom-port-mod-zai writes): not to be merged.

## ELF quirks kept
- CreateLadderTable / aiMapPlaceItem set the unit matrix twice; CreateLadderTable takes one ladder DI per node and
  skips a node off the grid. aiMapPlaceItem finds the lowest corner along `axis` but subtracts it from y.
- ftsFixupAiMap: m_ladders is not NULL-tested; the ammo box is created at an unset position (the matrix is set
  right after); its entries' first two fields are read without a length test (port: skipped when missing).
- CSpawners::Tick: an empty spawn list still uses up a due spawn. C2DCounter's Start returns 2 (true).
- GetGameTime in single player is the win/loss timer (-1 off): CHUD::Tick then clears the (hidden) timer text
  every frame, as the ELF does.

## Port deviations
- CftsPlayer::IsInside reads the ftsPlayer global (the port's ftsPlayer is the body; the ELF's is an 8-byte
  object whose first word is the body).
- ftsFixupAiMap's pickup position starts at 0 for a reader cell off the map (ELF: unset).
- CCounterSpec::Copy / GetType and the other spec Copy functions stay unwritten (declared void; nothing calls them).

## Not written / next
- CSealCtrlAi::PostMortemPreTick 0x267b30 (zSeal, 752 B, stub) is the only caller of CMission::RecycleEntity:
  dead AIs are not recycled, so m8's recycle entries (LeaderBud1, AlarmPop1-3, ... 11 slots) stay waiting
  placeholders and never spawn. With it written, spawners and the recycler run as the ELF does.
- The debrief's RESTRAINED stat (zSeal: CSealStats m_num_restrained is never counted in single player).
- Ladders: written, untestable on the demo disc (m8 has no flag-2 DI).
