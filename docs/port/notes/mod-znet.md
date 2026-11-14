# mod-znet notes (2026-11-14, socom-port-mod-znet): the zNetwork module, first part

Scratch `build/port/boot-mod-znet/` (untracked: NOTES.md, mine.txt, asm dumps `asm_cnf.txt` / `asm_dme.txt` /
`asm_med.txt` / `asm_voice.txt`, the rep.py blocks of each group, the trace spec `diag1.txt`, test edits under
`edits/`, the disc's online dialogs dumped under `disc/`). Test hook: `port/test-hooks/znet/` (README row added).

## Result
- `survey.py gamez/zNetwork`: written 6,808 B -> 27,596 B; stub fences 220 / 58,452 B -> 122 / 37,140 B (all left
  in zNetMedius.cpp). Not counted by the survey (no fences; the owner plan gives them to these units): the
  network-configuration state machines (~13 KB, all written) and the lobby's room / list types.
- Placeholders (bodies returning a constant): zNetMedius 16 -> 9 (Login, Register, RefreshGameList, RefreshRoomList,
  RefreshRoomPlayerList, OnCorrectClanTeam, IsLeaderOfClan written; Init was partial); zNetDme's
  `zNetUpdate` (returned false) written; zGame's `NetTickThreadEntry` workaround (zNetTick was void) removed.
- Groups: CNetCnf complete; DME (zNetDme.cpp) complete; voice (zNetVoice.cpp) complete; the Medius lobby's core
  (open / tick / close / bail out / the connect thread / room list / mission sequence / game clock / end report)
  written, its clan, ladder, chat, game-list and
  state-handler bodies not yet (below).
- Offline path (run zn5, `tb.sh -d diag1.txt -k znet znet4 -`; the demo's dlgMenu has no multiplayer entry - its
  multiplayer_button is OPTIONS - so the hook opens the disc's online screens): dlgNetConnect's ONSTART runs
  INITNETWORK -> `CZOnlineLobby::Open` (mp_rooms.rdr read: 8 rooms) -> the connect thread -> `AuxInitNetwork` ->
  DME init (`zNetLoadIRX` -> `CNetCnf::InitFromCombo`: no configuration, false) -> `MediusConnect` fails ->
  CONNECT_ERROR, socom_online_state 2. The player sees CONNECTING with "STATE: Connect Failure", then "STATE:
  Uninit Network", and the screen goes back to the main menu. dlgNetConfig: NetCnfInit / NetCnfOpen "mc0:" ->
  the configuration state machine -> `sceNetcnfifGetCount` answers -3 -> NETCNF_ERRNO 3 ("file open error");
  the screen shows COMBINATION 1 with hardware and provider "(not set)"; back to the menu, then attract. No STOP;
  in use at dlgMenu 18,060,372 B before and after both screens.

## Root cause found on the way
- Loading the real NETCNF.IRX (CNetCnf::Init, from the connect thread) reset the emulated machine ("# Restart").
  `port/compat/sce_iop.c` loaded every module first and fell back to the offline pseudo id only when the load
  failed; now a module on the offline list is never loaded (its comment and `socom_port_module_offline` already
  said so). This also stops USBD / USBKB / DEV9 being loaded at boot (offline subsystems: USB keyboard, HDD /
  network adaptor); the keyboard code already treats USBKB as offline.

## Written (ELF addresses)
- zNetCnf.cpp (whole file): CNetCnf Init 0x3ffa40 (modules; without `noIfc` netcnfif + libnet), Uninit, Open /
  OpenTick / Close, the lists and display names, SelectCombo (struct copy, sceNetcnfifData's `__as__` 0x3ff3f0),
  InitFromCombo 0x3feb80, ReadInterfaceList(Tick), AddDev / AddIFC / AddCombo (Tick), Save* (Tick), GetMACAddr,
  GetDevIndex, DeleteAll(Tick), SignalNetCnfError 0x401270. Unfenced: CCnfStateMachine (ctor 0x4020e0,
  StartState / IdleState, a member-pointer state queue; port name of the state argument: ENTER / TICK / EXIT),
  CSMOpen (ctor 0x4021d0, GetComboCount .. GetEntry 0x400820..0x4010d0, Cleanup), CSMInterface::Start 0x3fe900,
  CSMAddDev::GetHWAddr 0x3fff80, CSMSaveDev / CSMSaveIFC / CSMSaveCombo states, CSMDeleteAll::DeleteAll,
  CHNetCnf (ctor in `__sinit_zNetCnf.cpp`, dtor 0x401c50, LibNETSetup 0x3ff0f0, IOPRebootHandler 0x3ff1b0).
  No DWARF for any of these: layouts from the code (offsets in the comments).
- zNetDme.cpp (all 23 + IOPRebootHandler): zNetInit 0x322190 (network.rdr), zNetLoadIRX 0x321e20, zNetInitEx,
  zNetInitialize, zNetUpdate 0x3219f0, zNetTick, AddToFixList, zNetClose, the object / client getters, zNetConnect,
  zNetJoin, zNetLeaveAndDisconnect, zNetSendApplicationMessage (queued copies), the remote-object callbacks,
  CZBroadcastSchedule's ctor.
- zNetVoice.cpp (all): Init 0x3337a0, UnInit, PreTick / Tick (rewritten from the ELF: RotateThreadReadyQueue and the
  heartbeat time), WorkerThread 0x3332f0, RemoteSMUpdateCallback, IAmNewSessionMaster, Channel, Permit,
  ServerPermit, HandleNewIPBuf.
- zNetMedius.cpp: CZOnlineLobby Init 0x3289f0, Open 0x327e00, Tick 0x327c50, Close, UnInit, ReleaseUIResources
  0x327340, dtor 0x32f8c0, Bailout, Logout, Login, Register, RecoverFromNetError 0x322510, SetConnectionInfo,
  GetKeyPair, ForceStatusReport, Get*LadderPosition, Advance / Reset / Set / GetMissionSequence 0x322700..0x322940,
  SyncGameClock 0x322480, SendEndGameReport 0x322420, RefreshGameList, RefreshRoomList, RefreshRoomPlayerList 0x326c40, OnCorrectClanTeam 0x325430,
  IsLeaderOfClan 0x3229e0; AuxInitNetwork 0x328b90, NetInitThreadEntry, cbConnect,
  cbErrorMessage, GetRoomList 0x32dfa0, UpdateRoomListDisplay 0x32e920; BriefingRoom (ctors, dtor 0x327af0,
  CloneIndex / IsAClone / BaseSrc, LastClone 0x32fdd0), BriefingRoomDB::Parse 0x328490 (mp_rooms.rdr),
  BriefingRoomDB::FindRoom 0x325070, PersistentGame::Parse 0x328830, RoomGame::UpdateInfo 0x326160, the list DBs' dtors.
- Declarations: znet.h CZOnlineLobby laid out as DWARF (state handlers, event handlers, state, state queue,
  open / init flags, socom_online_state, mission sequence; nested LOBBY_STATE / LOBBY_STATE_FLAG, the global
  duplicates removed); CZNetwork's inline ctor (`__sinit_zNetDme.cpp`: WorldID 10, ClientIndex 256, 12 objects,
  2 streams, m_bNetCnfRequired 1, m_charType "0"); return types from the callers (zNetInitEx / zNetInitialize /
  zNetTick / zNetUpdate int, zNetGetClient a record, InitFromCombo bool, GetKeyPair a pointer), MP_CONNECTION one
  byte, the callback lists typed.

## Providers (offline stand-ins in port/compat; prototypes in compat headers)
- libnetcnfif (`netcnfif.h`, `netcnfif_offline.c`): requests complete at once; file requests on mc0: answer -3
  "file open error" (no memory card: the card layer stays off), work-area requests -2 "no space for memory";
  CNetCnf's states then raise NETCNF_ERROR and go idle.
- libnet / inet / ezNetCtl (`libnet.h`, `eznetctl.h`, `libnet_offline.c`): reg_handler -1 (no libnet server; no
  reboot callback, LibNETSetup false), 0 network interfaces, name lookup -1.
- DME (`dme.h`, `dme_offline.cpp`): NetInitialize / NetConnect / NetJoin fail (error 1), getters fail (the
  wrappers answer NULL / -1 / 0), NetTick / NetUpdate 0.
- Medius (`medius.h`, `medius_offline.cpp`): MediusConnect -1 without a callback (the lobby's CONNECT_ERROR),
  requests fail without callbacks, MediusUpdate 0.
- libptt (`ptt.h`, `ptt_offline.cpp`): -1 everywhere (PTT_Init's failure turns voice off), heartbeat 0.
  PTT_HeartbeatPrepare stays in `znetwork_holding.cpp` (held there before this work).
- NetGetBandwidthInfo is `net_bandwidth_offline.c` (another worker's).

## Outside the module (small in-place edits, free at HEAD)
- `src/Apps/FTS/options.cpp`: process_arguments turns Medius on (0x1740bc; the rest of that function is still a
  placeholder: --medius / --nomedius / --nomemcard not parsed).
- `src/gamez/zAnim/zanim_menu.cpp`: UILobbyLogout reads `m_current_state` (was a cast of the old `started`).
- `src/gamez/zGame/game_main.cpp`: NetTickThreadEntry's whole-second sleep when zNetTick answers nonzero.
- `port/compat/sce_iop.c`: offline modules never loaded (above).

## ELF quirks kept
- GetIfcDisplayName searches over the device count; GetComboList's index from "Combination<n>" is not range-checked
  (and reads past a short name); GetDevList with no device skips AllocMem but GetEntry frees the work area;
  SaveDev / SaveIFC do not free the work area on a failed request (SaveCombo does); InitFromCombo never finishes
  if eznetctl.irx cannot be loaded; Close returns 1 and ignores its handle; Open ignores the file name.
- zNetInit copies a missing server_ip / server_port unchecked (DME without Medius); zNetCreateObject reads this
  client's index and drops it; zNetLoadIRX's unknown connection type copies nothing.
- Lobby: Open's thread runs at priority 0; AuxInitNetwork ticks the lobby from that thread; RecoverFromNetError's
  two branches are the same; BriefingRoomDB::Parse drops the old rooms without deleting them; a room without a
  ROOMNAME is still added; Login / Register copy 256 bytes of a shorter literal (port: zero-padded).
- Voice: the worker gets a 128000-byte stack it is told is 8000 bytes (never freed); a failed join is retried at
  once; the outer loop spins while voice is off.

## Port deviations
- CHNetCnf and the CSM* machines use GCC member pointers and std::queue (the ELF's 12-byte member pointers in an
  MSL deque); the handle stays opaque to the UI commands. sceNetcnfifList entries are 520 bytes in the port (576,
  64-aligned, in the ELF).
- Fixes freed with `delete` (the ELF `_free`s the `new`ed record); the voice thread enters through a static
  trampoline (the ELF passes the member function itself); copies past a string's end are bounded.
- Names of every SDK record member, every CSM / lobby list member and the state argument are the port's.

## Runs (tree = HEAD c1b25067 + mine.txt)
- zn5: the online screens above. znm8 (state hook, one mission, intro CROSS, cameras X): in the mission from 66 s
  to the end at 260 s, no STOP, in use 22.96 MB from 100 s on (flat).
- znfe (fake pad `pad_fe.txt` of the zUI notes: main menu -> OPTIONS -> audio, video, controller selection,
  presets -> main menu -> attract, 240 s): no STOP, no "not written" spec.
- znrt (state hook, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8`, 760 s): eight missions and eight returns, no STOP,
  no failed allocation but zsys_FullAllocAndFree's probes; in use 18,570,628 B at return 1, 18,570,724 B at returns
  2-8 (flat; about 6 KB above the 18,564,4xx B of HEAD before this work: the network objects' queues and lists made
  at static construction).
- znetdef3 (`default.sh`, no hooks): main menu at 15.4 s, no STOP.

## Not written / next
- zNetMedius.cpp, 128 fences (38 KB): the state handlers' bodies (CreateRoom, JoinRoom, JoinGame, CreateNewGame,
  LobbyActive, EndSession, SessionBegin, AccountRegistration, AccountLogin, LobbyServerConnect,
  LobbyReadyToConnect; offline only their REGISTER, which does nothing, runs) and their Medius callbacks; clans
  (GetClan, Create / Disband / Quit, invitations, roster, messages, leadership), ladders, chat / censor,
  announcements, game list / filters / random game (GetGameList is still empty, so RefreshGameList asks for
  nothing), UpdateClanStats,
  BanSelfFromGame, the room / game player lists, MapToGameLevel, LookupMediusCallbackStatus,
  PasswordSecurity, and the 9 constant placeholders (GetClan, SendClanMessage, RefreshGamePlayerList, CreateGame, GameIsPasswordProtected, JoinGame, JoinRoom, InvitePlayerToClan,
  RevokeInvite). Each needs its Medius request / response record laid out from the code (medius.h is
  append-only) and a stand-in.
- InvitationItem / ClanInvitationItem members (their ctors 0x32acb0 / 0x323890); BriefingRoom::FindGame / deltrans and BriefingRoomClone are declared or missing.
- process_arguments (options.cpp) is still mostly a placeholder.
