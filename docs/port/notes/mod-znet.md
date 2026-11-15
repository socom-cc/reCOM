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

# Part 2 (2026-11-14, socom-port-mod-znet2): the rest of the Medius lobby

Scratch `build/port/boot-mod-znet2/` (untracked: NOTES.md, mine.txt, the rep.py blocks per group
`med2_states` / `med2_clan` / `med2_chat` / `med2_games` / `med2_misc` / `med2_fix1`, `fwd.py` (the
forward-declaration block), `dmereg_edit.py`, the DMERegister and PTT asm dumps, run logs). Asm read from part
1's `asm_med.txt` (`a.sh <from> <to>`).

## Result
- `survey.py gamez/zNetwork`: written 27,596 B -> 64,736 B; stub fences 122 / 37,140 B -> 0 / 0 B. zNetMedius.cpp:
  172 fences, all written. Placeholders returning a constant: 9 -> 0 (GetClan, SendClanMessage,
  RefreshGamePlayerList, CreateGame, GameIsPasswordProtected, JoinGame, JoinRoom, InvitePlayerToClan, RevokeInvite).
  Fifteen of the written fences are empty in the ELF too (`jr ra`: the five failure / success state handlers,
  cbChatToggle, cbVersionServer, cbSetGameListFilter, cbUpdateAccountStats, cbQuitClan, cbBanSelfFromGame,
  cbClanInviteRevokeHack, cbAddPlayerToClan, cbUpdateClanStats, cbBuddyGetPermission); their comments say so.
- Also written: PTT_HeartbeatPrepare 0x3f02c0 (`znetwork_holding.cpp`, libptt), the DME packet registrations of
  DMERegister 0x201920 (`fts_network_dme.cpp`) and NetSetMyClientObject in ftsNetworkPlayerInit 0x2014d0
  (`fts_network.cpp`).
- All of it is network-only: written, untested (no server). The offline path is unchanged (runs below).

## Written (ELF addresses)
- State handlers and their callbacks (0x32b300..0x32dbb0): CreateRoom (cbCreateRoom, cbFindRoomByName), JoinRoom
  (cbJoinRoom), JoinGame (cbJoinGame), CreateNewGame (cbCreateGame, cbFindGameByName), LobbyActive (player stats and
  usage policy: cbGetPlayerStats, cbGetPolicyRequest), EndSession (cbSessionEnd), SessionBegin (cbSessionBegin),
  AccountRegistration (cbFilterAcctName, cbAccountRegistration, cbAccountLoginAfterRegister), AccountLogin
  (cbAccountLogin), LobbyReadyToConnect 0x32ccc0 (its two static locals; the player and world reports every 25 s,
  NetPing), LobbyServerConnect (cbLobbyServerConnect, cbClientConnect / Disconnect), RefreshDMEJoinedCount and its
  callback, cbDMENetPingCallback.
- Clans: DisbandClan, GetClanRoster, cbGetClanMemberList, GetClanMemberRanking, cbGetClanMemberLadderPosition,
  cbGetClanMemberDescriptions, UpdateClanMemberList, GetInvitedPlayers, cbGetClanInvitationsSent,
  ClanUpdateInvitations, RevokeInvite, cbRevokePlayerInvitation, RemovePlayerFromClan, cbRemovePlayerFromClan,
  InvitePlayerToClan (two-step status) and its two callbacks, CreateClan, cbFilterClanName, cbCreateClan,
  UpdateClanStats, TransferLeadership, SendClanMessage, cbFilterClanMessage, cbSendClanMessage, cbGetMyClanMessages,
  CheckClanInvitations, cbCheckMyClanInvitations, UpdateInvitations, Accept / DeclineClanInvitation, GetClan 0x32afc0
  (the ClanCallbackExecuted poll), cbGetMyClans, QuitClan. Members of InvitationItem (ctor 0x32acb0, 248 B) and
  ClanInvitationItem (ctor 0x323890, 240 B); ClanMemberItem +0xc (ladder position); LadderItem +0x8 / +0xc.
- Chat and text: GetAnnouncements, cbGetAnnouncements, SendChat, cbFilterChat, Censor, cbCensor, cbChatMessage,
  SetPlayerDescription, cbFilterPlayerDescription, RejoinRoom, JoinRoom ("RANDOM", "NONE").
- Ladders: UpdateLadderRating, GetLadderRanking, GetLadderInfo, cbGetLadderRanking / Position,
  GetSurroundingLadderPosition 0x3295e0, cbGetLadderInfo, cbGetLadderTop10, cbGetLadderTop10Descriptions,
  UpdateLadderTop10, UpdateLadderRanking (this player's row in COLOR 255 104 51).
- Game and room lists: GetGameList, cbGameList, cbGameInfo, cbGameSecurityCheck, UpdateGameListDisplay,
  GamePassesFilters, GamePassesTypeFilter, cbRoomList 0x32e050 (room clones), cbChannelInfo, cbRoomPlayerList,
  UpdateRoomPlayerListDisplay, _roomplayer_sort_aux, RefreshGamePlayerList and its callback (BSEALLISTVAR /
  BTERRLISTVAR), BanSelfFromGame; the random game: JoinGame "RANDOM", cbClearGameListFilter, cbGetRandomGameList,
  cbRandomGameInfo, cbRandomGameSecurity, DoJoinRandomGame; CreateGame, GameIsPasswordProtected.
- Unfenced (the owner plan gives them to this unit): BriefingRoom::FindGame 0x325a80, deltrans 0x32ecb0,
  BriefingRoomClone (ctor 0x32e4c0; CloneIndex / IsAClone / BaseSrc 0x32fe60..0x32fe80), PersistentGameClone::IsAClone
  0x32fe40, TransientGame (vtable 0x473020).
- MapToGameLevel 0x32f980 ("mp1".."mp10"), LookupMediusCallbackStatus 0x32fb20 (the status names), PasswordSecurity
  0x32fac0.

## Types and declarations
- RoomGame (516 B): the game list record (+0), the vptr (+0x70), the game's details (+0x74, a MediusGameInfoResponse
  of 396 B that cbGameInfo copies whole) and the security level (+0x200, -1 unknown). PersistentGame's MAXPLAYERS is
  that record's MaxPlayers (+0x98). The game uses the details' generic fields: GameLevel = friendly fire, RulesSet =
  the mission number (the map filter), GenericField1 / 2 / 3 = the room's world, the performance metric (ping), the
  clan side; the same order in MediusCreateGameRequest and MediusWorldReport.
- StoredClanInfo is the player's MediusGetMyClansResponse (368 B); part 1's `int[92]` offsets became members.
- `znet.h`: BriefingRoom::deltrans static bool, m_unknown_98 named m_lastInfoTime (cbRoomList), PTT_HeartbeatPrepare
  returns int.
- Signatures from v0: LookupMediusCallbackStatus const char *, MapToGameLevel int, GamePassesFilters /
  GamePassesTypeFilter / _roomplayer_sort_aux bool. Functions that return 0/1 in the ELF that no caller reads
  (GetClanRoster, GetInvitedPlayers, RemovePlayerFromClan, SendChat, RejoinRoom) stay void.
- The unit's free functions are forward-declared in one port block after the globals (the definitions run from
  the highest address down); the inline request preamble (memset, session key, message id) is LobbyPrepareRequest.

## Providers (offline stand-ins)
- `medius.h`: section "socom-port-mod-znet2" with every request and response the lobby builds (offsets from the
  stack frames and memset sizes) and 46 prototypes; `medius_offline.cpp`: each answers -1 and calls no callback
  (the lobby is never connected offline, so none is reached; a caller waiting on a callback stays in its state).
  Part 1's MediusConnectRequest +0xa0 / +0xa4 are typed as the client connect / disconnect callbacks, and its
  guessed MediusGameListResponse names +0x60..+0x68 are corrected to WorldStatus / GameHostType / PlayerCount.
- `dme.h` / `dme_offline.cpp`: NetPing (error), NetRegisterMessageStart / NetMessageField /
  NetRegisterApplicationMessage (0, as the other registrations: DMERegister runs offline from AuxInitNetwork),
  NetSetMyClientObject (error).
- `ptt.h` / `ptt_offline.cpp`: libptt's heartbeat state (g_isInitialized false offline, the semaphore, the 32 KB RPC
  buffer and client record, _PTT_HeartbeatCallback); PTT_HeartbeatPrepare answers -1 before using any of it.

## ELF quirks kept
- GetClanMemberRanking asks every unranked member's position with this player's own account id, and the last one
  asked ends in g_iLastMemberRanked. UpdateClanMemberList sorts the ladder list, not the members.
- cbRoomList asks a room's channel info whenever its last ask is under 30 s in the future (always); a clone is made
  when a room is one short of its limit. GetGameList drops the server games without deleting them.
- GamePassesFilters with LockedFilter 0 passes no game; DoJoinRandomGame ranks by MaxPlayers - MinPlayers.
- cbSendClanMessage formats a failure text and shows nothing; cbRoomPlayerList clears the pending flag only when
  the room is found; cbSessionEnd's two branches push the same state; JoinRoom / JoinGame compare the name unchecked.
- cbGameWorldPlayerListCallback leaves this player off both lists while his team is 0.

## Port deviations
- Copies past a literal's end (memcpy of 21 / 32 / 64 / 256 bytes from shorter literals) are strncpy (zero
  padded); cbFilterChat's forwarded line is zeroed first (the ELF leaves its message id unset); UpdateClanStats
  prints a non-string description as "" (the ELF passes NULL to %s).
- UpdateRoomPlayerListDisplay sorts with strcmp < 0 (std::sort needs a strict order; the ELF's comparator answers
  <= 0 and is kept as _roomplayer_sort_aux).
- LobbyVarString also answers NULL for a NULL variable (the ELF reads most of them unchecked).
- The DME packet templates are byte arrays with the ELF's field offsets (the ELF's are uninitialised stack blocks).

## Runs (tree = HEAD 487df66c + mine.txt)
- zn2a (`tb.sh -d diag1.txt -k znet zn2a -`, part 1's trace spec): dlgNetConnect: Open (8 rooms) -> the connect
  thread -> DMERegister (the new packet registrations, offline 0) -> MediusConnect -1 -> "STATE: Connect Failure",
  "STATE: Uninit Network", back to dlgMenu; dlgNetConfig: NETCNF_ERRNO 3, "(not set)"; no STOP. dlgMenu in use
  18,156,820 B after both screens, 48 B over the first dlgMenu read as in part 1.
- zn2m8 (state hook, `-DSOCOM_HOOK_MISSIONS=1 -DSOCOM_HOOK_PLAY_AT=20000`, intro CROSS, cameras X, 240 s): in the
  mission from 75 s to 241 s, no STOP, in use 23.01 -> 23.06 MB by 135 s (the AI waking), then flat.
- zn2rt (state hook, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4`, 430 s): four missions and four returns, no STOP,
  no failed allocation but zsys_FullAllocAndFree's probes; in use at the briefing after each return 18,666,708 /
  18,666,804 / 18,666,804 / 18,666,804 B (flat after the first, the same +96 B as part 1).
- zn2def (`default.sh`, no hooks): main menu at 19.3 s, no STOP.

## Not written / next
- Nothing is left empty in zNetwork. The lobby's online paths (every Medius request and callback, the DME packet
  handlers' registration, PTT_HeartbeatPrepare's RPC) have no server to run against: written, untested.
- process_arguments (options.cpp) is still mostly a placeholder (not zNetwork).
