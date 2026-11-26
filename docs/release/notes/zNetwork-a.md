# Stage 2: gamez/zNetwork, list a (2026-11-26)

List a of `gamez/zNetwork` (split 3 ways): the owner files zNetMedius.cpp (release
0x33d280-0x34f040), zNetVoice.cpp (0x34f060-0x34fb50) and zNetCnf.cpp (0x404130-0x404610). It
holds 39 uncertain rows (19 removed, 8 new, 2 unsure, 3 weak pairs, all `slot-only`, and 7 exact
rows flagged `identical-copy`), 15 sampled deviating rows out of 118, and 141 exact rows that were
not checked. Pairing produced by `socom-release-compare-c1` (`python tools/release/compare.py`);
checked by `socom-release-check-net-a`, who did not write the tool, at HEAD f4f0da93. The check
sheet (`compare.py --sheet gamez/zNetwork --list a`) was the starting point. Both images were
disassembled with the release tools; callers were found by scanning both images for `jal`/`j`,
data words and `lui`/`addiu` pairs. As a guard on the committed pairs, every paired function in
the three ranges (262 rows) had its callers and its loaded function pointers compared with the
prototype's through the map; every difference found is explained below. Ghidra was not needed.

What settled rows, in the order it was used: the function pointer handed to an exact-paired
Medius call (MediusGetPolicy, MediusGetAnnouncements, MediusGetMyClanMessages, MediusConnect);
the store offsets of the lobby state-handler table that `CZOnlineLobby::Open` fills; vtable
slots (the RoomGame family has no RTTI on either side; the release tables sit in the same order
and are told apart by the constructors that store them); the call site in a paired caller; the
slot between paired neighbours; strings.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x33d2d0 | 0x322470 `GetDMEJoinedCount__13CZOnlineLobbyFv` | deviating (weak), slot-only | confirmed | same two callers (UICheckJoinMP, CLoadState::Tick); same global; the release clamps a negative count to 0 |
| 0x33ff70 | - | new, copy | confirmed | `jr ra; move v0,a0`; called on the chat vector (+28) by cbFilterChat and cbChatMessage, inside new code that drops the oldest message before the insert; the prototype slot is empty |
| 0x3408d0 | 0x325a70 `IsPersistent__8RoomGameFv` | exact, identical-copy | confirmed | slot +0x08 of the RoomGame table (0x48aa90, stored by the PersistentGame constructor before its own table, as the prototype's inline construction stores `__vt__8RoomGame`) and of the TransientGame table 0x48aa80 |
| 0x341e40 | - | new | confirmed | CZOnlineLobby method (this = theLobby) between RefreshRoomList and RefreshGameList; finds the briefing room named by uiv_LobbyWorldNameVar and calls new 0x34a7b0 for each of its games; caller a new UI command 0x1d1050 |
| 0x343b20 | - | new | confirmed | out-of-line PersistentGame constructor: stores the RoomGame table, clears the record, copies the MediusGameListResponse, then stores the PersistentGame table (0x48aa70); callers BriefingRoomDB::Parse and the BriefingRoomClone constructor, which built it inline in the prototype |
| 0x343de0 | 0x328b50 `GetKeyPair__13CZOnlineLobbyFv` | deviating (weak), slot-only | confirmed | same caller zNetInitialize; still returns the key pair's address; the release generates it on first use (KM_GenerateRSAKeyPair) |
| 0x345b10 | - | new | confirmed | requests MediusGetMyClanMessages with callback 0x345b90 (optionally "Retrieving messages from server..."); caller a new UI command 0x1d2ab0 (this = theLobby) |
| 0x3474d0 | - | new | corrected to 0x32c140 `ConnectErrorStateHandler__FQ213CZOnlineLobby16LOBBY_STATE_FLAG` | Open stores it at handler offset +8 on both sides; it sits after LobbyActiveStateHandler, where the prototype had ConnectError; the empty stub gained a body (MediusDisconnect, "Unable to connect to server.") |
| - | 0x32c180 `RegistrationFailureStateHandler__FQ213CZOnlineLobby16LOBBY_STATE_FLAG` | removed | corrected to 0x347580 | Open stores 0x347580 at offset +24, the prototype's RegistrationFailure slot; see the stub row below the list |
| - | 0x32d5d0 `cbClientDisconnect__FiiPCc` | removed | confirmed | LobbyServerConnectStateHandler now writes 0 where it stored this pointer in the MediusConnect request (+0xb4); the work (an ON_CLIENT_CONNECT UI event) is gone |
| - | 0x32d600 `cbClientConnect__FiiPCc` | removed | confirmed | the same, request field +0xb0 |
| 0x349040 | 0x32dbb0 `cbGetPolicyRequest__FiiiP23MediusGetPolicyResponse` | unsure, position | corrected to new | not a callback: called directly (this = theLobby) by a new UI command 0x1d2ae0; sets "Retrieving Usage Policy....." and sends MediusGetPolicy with callback 0x349100. The prototype sent that request inline in LobbyActiveStateHandler; the release one no longer does |
| 0x349100 | - | new | corrected to 0x32dbb0 `cbGetPolicyRequest__FiiiP23MediusGetPolicyResponse` | the pointer passed to MediusGetPolicy, as the prototype passed cbGetPolicyRequest; same status test (+0x18) and "UsagePolicy" variable, now built through CRdrEditor and "TempUsagePolicy" |
| 0x349af0 | 0x32e4b0 `BaseSrc__12BriefingRoomFv` | exact, identical-copy | confirmed | slot +0x10 of the BriefingRoom table (0x48aa50, stored by its constructor and destructor on both sides) |
| 0x349db0 | 0x32e800 `CloneIndex__12BriefingRoomFv` | exact, identical-copy | confirmed | slot +0x08 of the BriefingRoom table |
| 0x34a3b0 | - | new | confirmed | a second remove_if predicate in GetGameList (+0x2f0): resets a persistent game's id, deletes a transient one flagged at +0x208; the first remove_if (+0x10c on both sides) keeps deltrans |
| 0x34a7b0 | - | new | confirmed | sends MediusGetGameInfo (callback cbGameInfo) and MediusGetWorldSecurityLevel (callback cbGameSecurityCheck) for one game when its stamp (+0x204) is old enough; the prototype cbGameList had this inline (it alone loaded both callbacks); callers cbGameList ×2, GetGameList, 0x341e40 |
| 0x34b810 | 0x32fe40 `IsAClone__19PersistentGameCloneFv` | exact, identical-copy | confirmed | slot +0x0c of the PersistentGameClone table (0x48aa20, the last table stored by the BriefingRoomClone constructor on both sides) |
| 0x34b820 | 0x32fe50 `IsPersistent__14PersistentGameFv` | exact, identical-copy | confirmed | slot +0x08 of the PersistentGame and PersistentGameClone tables on both sides |
| 0x34b870 | 0x32fea0 `IsAClone__12BriefingRoomFv` | exact, identical-copy | confirmed | slot +0x0c of the BriefingRoom table |
| 0x34b880 | 0x32feb0 `IsAClone__14PersistentGameFv` | exact, identical-copy | confirmed | slot +0x0c of the PersistentGame table |
| - | 0x330810 `__as__34MediusLobbyWorldPlayerListResponseFRC34MediusLobbyWorldPlayerListResponse` | removed | confirmed | inlined: its four callers (sort, insert, __sort132, __selection_sort) no longer call it and grew (__selection_sort 252 → 468 bytes, __sort132 460 → 1252) |
| 0x34f1a0 | 0x333050 `Permit__10CZNetVoiceFPUi` | deviating (weak), slot-only | confirmed | same call site in RemotePersonaCreationCallback, between the Init and ServerPermit calls; the release body is empty (`jr ra; nop`), PTT_PermitWANAddress is gone |
| - | 0x401c50 `__dt__8CHNetCnfFv` | removed | confirmed | the destructor of theNetCnf's state machines; `__sinit_zNetCnf.cpp` and every CCnfStateMachine/CSM* class are gone (no "zNetCnf.cpp" string left in the release) |
| 0x4043c0 | 0x3ff0f0 `LibNETSetup__8CHNetCnfFv` | unsure, position | confirmed, deviating | directly before IOPRebootHandler on both sides; ends with LibNETSetup's sequence (msifrpc, libnetb `-decode`, sceSifMInitRpc, libnet_init on libnetCd, RegisterRebootCallback with IOPRebootHandler); reg_handler dropped, all the network IRX loads added in front; its caller is now Init (0x404640) |
| - | 0x3ff1f0 `GetIfcDisplayName__7CNetCnfFPvi` | removed | confirmed | with the whole CNetCnf configuration editor (below); its caller UINetCnfGetDispNames is removed too |
| - | 0x3ff2b0 `GetDevDisplayName__7CNetCnfFPvi` | removed | confirmed | the same |
| - | 0x3ff370 `GetNetDisplayName__7CNetCnfFPvi` | removed | confirmed | the same |
| - | 0x3ff390 `SelectCombo__7CNetCnfFPvi` | removed | confirmed | the same (caller UINetCnfSelectCombo removed) |
| - | 0x3ff3f0 `__as__15sceNetcnfifDataFRC15sceNetcnfifData` | removed | confirmed | the same: sceNetcnfif data is not used in the release (no sceNetcnfif library left) |
| - | 0x3ff810 `GetDefaultCombo__7CNetCnfFPv` | removed | confirmed | the same (caller UINetCnfCurrCombo removed) |
| - | 0x3ff820 `GetDev__7CNetCnfFPvi` | removed | confirmed | the same (caller UINetGetDevInfo removed) |
| - | 0x3ff840 `GetIFC__7CNetCnfFPvi` | removed | confirmed | the same (caller UINetGetIFCInfo removed) |
| - | 0x3ff860 `NumDevs__7CNetCnfFPv` | removed | confirmed | the same |
| - | 0x3ff870 `NumIFC__7CNetCnfFPv` | removed | confirmed | the same |
| - | 0x3ff880 `NumCombos__7CNetCnfFPv` | removed | confirmed | replaced: UINetCnfCount (paired) now calls the ezNetCnf RPC stub 0x431b88 where it called NumCombos |
| - | 0x3ff890 `Close__7CNetCnfFPv` | removed | confirmed | with the editor (caller UINetCnfClose removed) |
| - | 0x3ff8a0 `Open__7CNetCnfFPCc` | removed | confirmed | the same (caller UINetCnfOpen removed) |
| - | 0x3ff920 `OpenTick__7CNetCnfFPv` | removed | confirmed | the same |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x33e250 | 0x323410 `UpdateClanMemberList__Fv` | yes | the same four callers |
| 0x33ed00 | 0x323f30 `cbRemovePlayerFromClan__F...` | yes | the pointer loaded by RemovePlayerFromClan on both sides |
| 0x33f430 | 0x324600 `CreateClan__13CZOnlineLobbyFPCc` | yes | same caller UICreateClan |
| 0x33f680 | 0x324880 `UpdateClanStats__13CZOnlineLobbyFv` | yes | same caller UIUpdateClanStats |
| 0x342fc0 | 0x327e00 `Open__13CZOnlineLobbyFv` | yes | same caller UIInitNetwork; the same handler table |
| 0x3444c0 | 0x329080 `SetPlayerDescription__13CZOnlineLobbyFPCc` | yes | same caller UISetPlayerDescription |
| 0x344970 | 0x329530 `cbGetLadderPosition__F...` | yes | the pointer loaded by GetLadderInfo on both sides |
| 0x344c40 | 0x329820 `cbGetLadderInfo__F...` | yes | the pointer loaded by GetSurroundingLadderPosition on both sides |
| 0x3479d0 | 0x32c610 `cbAccountRegistration__F...` | yes | the pointer loaded by cbFilterAcctName on both sides |
| 0x348fc0 | 0x32db10 `QuitClan__13CZOnlineLobbyFv` | yes | same caller UIQuitClan |
| 0x3495f0 | 0x32df70 `_roomplayer_sort_aux__F...` | yes | loaded by UpdateRoomPlayerListDisplay on both sides; imm-only |
| 0x34a420 | 0x32ecb0 `deltrans__12BriefingRoomFP8RoomGame` | yes | the predicate of GetGameList's first remove_if, loaded at +0x10c on both sides; still `!IsPersistent()` |
| 0x34b1b0 | 0x32f800 `GamePassesTypeFilter__Fi` | yes | same caller GamePassesFilters |
| 0x34f1f0 | 0x3330d0 `IAmNewSessionMaster__10CZNetVoiceFv` | yes | same caller zDoClientLeavesCallback |
| 0x404610 | 0x3ff9f0 `Uninit__7CNetCnfFv` | yes | same caller UINetCnfUninit; clears m_isinit |

Just outside the list (inside its owner ranges or next to them; found by the caller and
function-pointer comparison):

| release | map | finding |
|---|---|---|
| 0x33f800 | deviating, 0x32a790 `cbGetMyClanMessages__F...` | wrong: it is `cbGetAnnouncements__FiiiP30MediusGetAnnouncementsResponse` (0x324a50). GetAnnouncements passes it to MediusGetAnnouncements on both sides; it follows GetAnnouncements on both sides; its body is the prototype cbGetAnnouncements (no sprintf, ends by sending MediusGetMyClanMessages) |
| 0x345b90 | deviating, 0x324a50 `cbGetAnnouncements__F...` | wrong: it is `cbGetMyClanMessages__F15MediusErrorCode15MediusErrorCode15MediusErrorCodeP31MediusGetMyClanMessagesResponse` (0x32a790): the pointer passed to MediusGetMyClanMessages; follows cbSendClanMessage (and new 0x345b10) as in the prototype; same body (sprintf header, CheckClanInvitations at the end) |
| 0x347550 | exact, 0x32c140 ConnectError | wrong by one: Open stores it at offset +56, so `CreateFailureStateHandler` (0x32c150) |
| 0x347560 | exact, 0x32c150 CreateFailure | wrong by one: offset +4, so `ConnectSuccessStateHandler` (0x32c160) |
| 0x347570 | exact, 0x32c160 ConnectSuccess | wrong by one: offset +40, so `LoginFailureStateHandler` (0x32c170) |
| 0x347580 | exact, 0x32c170 LoginFailure | wrong by one: offset +24, so `RegistrationFailureStateHandler` (0x32c180), which the map has as removed. With 0x3474d0 = ConnectError, the release order (ConnectError, CreateFailure, ConnectSuccess, LoginFailure, RegistrationFailure, EndSession) is the prototype's |
| 0x404640 | new, no owner | it is `Init__7CNetCnfFb` (0x3ffa40): its caller is UINetCnfInit, which called Init in the prototype; it tests and sets m_isinit (Uninit clears it on both sides); it follows Uninit on both sides; it loads the configuration-interface IRX (eznetcnf.irx where the prototype loaded the netcnfif modules) |
| 0x404130 | deviating, 0x3ffa40 `Init__7CNetCnfFb` (list b's range) | then new: no m_isinit; called only by InitFromCombo; loads the modem, inet and inetctl modules, then only the device drivers the selected configuration needs (ppp, pppoe, smap or an986: the choice the prototype InitFromCombo made inline), then the libnet setup. It sits where the prototype's removed CSM*::Cleanup run was. The other reading (0x404130 = Init, because InitFromCombo calls it first as it called Init) loses to m_isinit and position |
| 0x403f80, 0x404010 | new, no owner | in no list. Both use ezNetCtl (status poll with a message callback; DownInterface and exitEzNetCtl); callers zNetUpdate and zNetClose; they come just before InitFromCombo, so zNetCnf.cpp |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x33d2d0 | 0x322470 | same callers UICheckJoinMP and CLoadState::Tick; same global dme_joined_count | socom-release-check-net-a | 2026-11-26 |
| 0x343de0 | 0x328b50 | same caller zNetInitialize; returns the RSA key pair's address (generated on first use) | socom-release-check-net-a | 2026-11-26 |
| 0x34f1a0 | 0x333050 | same call site in RemotePersonaCreationCallback, between the CZNetVoice Init and ServerPermit calls | socom-release-check-net-a | 2026-11-26 |
| 0x349100 | 0x32dbb0 | the function pointer passed to MediusGetPolicy; same response handling ("UsagePolicy") | socom-release-check-net-a | 2026-11-26 |
| 0x349040 | new | the policy request moved out of LobbyActiveStateHandler: direct caller UI command 0x1d2ae0 (this = theLobby); sends MediusGetPolicy with 0x349100 | socom-release-check-net-a | 2026-11-26 |
| 0x3474d0 | 0x32c140 | stored at handler offset +8 by Open on both sides; after LobbyActiveStateHandler on both sides | socom-release-check-net-a | 2026-11-26 |
| 0x347550 | 0x32c150 | stored at handler offset +56 by Open on both sides (outside list a) | socom-release-check-net-a | 2026-11-26 |
| 0x347560 | 0x32c160 | stored at handler offset +4 by Open on both sides (outside list a) | socom-release-check-net-a | 2026-11-26 |
| 0x347570 | 0x32c170 | stored at handler offset +40 by Open on both sides (outside list a) | socom-release-check-net-a | 2026-11-26 |
| 0x347580 | 0x32c180 | stored at handler offset +24 by Open on both sides (outside list a) | socom-release-check-net-a | 2026-11-26 |
| 0x33f800 | 0x324a50 | the pointer GetAnnouncements passes to MediusGetAnnouncements on both sides; follows GetAnnouncements (outside list a) | socom-release-check-net-a | 2026-11-26 |
| 0x345b90 | 0x32a790 | the pointer passed to MediusGetMyClanMessages; follows cbSendClanMessage; same CheckClanInvitations tail (outside list a) | socom-release-check-net-a | 2026-11-26 |
| 0x4043c0 | 0x3ff0f0 | directly before IOPRebootHandler on both sides; LibNETSetup's libnet sequence registering IOPRebootHandler | socom-release-check-net-a | 2026-11-26 |
| 0x404640 | 0x3ffa40 | caller UINetCnfInit on both sides; m_isinit test and set; directly after Uninit on both sides (outside list a) | socom-release-check-net-a | 2026-11-26 |
| 0x404130 | new | no m_isinit; caller InitFromCombo only; loads the device drivers of the selected configuration (list b's range) | socom-release-check-net-a | 2026-11-26 |
| 0x3408d0 | 0x325a70 | slot +0x08 of the RoomGame table, stored by the PersistentGame constructor before its own table | socom-release-check-net-a | 2026-11-26 |
| 0x349af0 | 0x32e4b0 | slot +0x10 of the BriefingRoom table (stored by its constructor and destructor) | socom-release-check-net-a | 2026-11-26 |
| 0x349db0 | 0x32e800 | slot +0x08 of the BriefingRoom table | socom-release-check-net-a | 2026-11-26 |
| 0x34b810 | 0x32fe40 | slot +0x0c of the PersistentGameClone table (last table stored by the BriefingRoomClone constructor) | socom-release-check-net-a | 2026-11-26 |
| 0x34b820 | 0x32fe50 | slot +0x08 of the PersistentGame and PersistentGameClone tables | socom-release-check-net-a | 2026-11-26 |
| 0x34b870 | 0x32fea0 | slot +0x0c of the BriefingRoom table | socom-release-check-net-a | 2026-11-26 |
| 0x34b880 | 0x32feb0 | slot +0x0c of the PersistentGame table | socom-release-check-net-a | 2026-11-26 |

Rows that change together: the five handler rows (0x3474d0, 0x347550-0x347580) and the removed
RegistrationFailureStateHandler; the two crossed callbacks (0x33f800, 0x345b90); the three
zNetCnf rows (0x4043c0, 0x404640, 0x404130), which also touch list b's Init row. Owners: 0x404640,
0x403f80 and 0x404010 have none in the map and belong to zNetCnf.cpp.

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x33ff70 | returns its argument; called on the chat vector before an insert | guess: an out-of-line trivial MSL accessor, e.g. `compressed_pair_imp<allocator<MediusChatFwdMessage>,...>::first()` (same bytes as the prototype's `first__...compressed_pair_imp<...MediusLobbyWorldPlayerListResponse...>` at 0x331580) |
| 0x341e40 | refreshes the game info of every game in the current lobby world's briefing room | guess: `RefreshGameInfo__13CZOnlineLobbyFP3C2D` (between RefreshRoomList and RefreshGameList, same argument kind) |
| 0x343b20 | PersistentGame constructor | `__ct__14PersistentGameFP22MediusGameListResponse` (the vtable stores; the argument is copied with MediusGameListResponse's assignment); the signature is a guess |
| 0x345b10 | requests the player's clan messages, optionally showing "Retrieving messages from server..." | guess: `GetMyClanMessages__13CZOnlineLobbyFb` |
| 0x349040 | requests the usage policy | guess: `GetUsagePolicy__13CZOnlineLobbyFv` |
| 0x34a3b0 | remove_if predicate: persistent games get id -1 and stay, transient games flagged at +0x208 are deleted | guess: `delstale__12BriefingRoomFP8RoomGame` (beside deltrans; GetGameList sets +0x208 on every game before MediusGetGames) |
| 0x34a7b0 | sends the game-info and security-level requests for one game, at most every N seconds | guess: `RequestGameInfo__FP3C2DP8RoomGamei` |

Not new, though the map has them as new: 0x349100 (cbGetPolicyRequest), 0x3474d0
(ConnectErrorStateHandler), and outside the list 0x404640 (CNetCnf::Init).

Really removed:

- cbClientConnect and cbClientDisconnect: no longer registered in the MediusConnect request;
  their UI event is gone.
- `__as__34MediusLobbyWorldPlayerListResponse...`: inlined into its four sort/insert callers.
- The CNetCnf configuration editor: GetIfcDisplayName, GetDevDisplayName, GetNetDisplayName,
  SelectCombo, `__as__15sceNetcnfifData`, GetDefaultCombo, GetDev, GetIFC, NumDevs, NumIFC,
  NumCombos, Close, Open, OpenTick and `__dt__8CHNetCnfFv` in this list, together with the
  CCnfStateMachine/CSM* classes, `__sinit_zNetCnf.cpp`, the sceNetcnfif library and the UI commands
  that drove them. The release talks to Sony's ezNetCnf and ezNetCtl instead: eznetcnf.irx with an
  RPC client (bind 0x431a40, unload 0x431b08, a count call 0x431b88 used by UINetCnfCount),
  ezNetCtl calls in InitFromCombo, zNetUpdate (0x403f80) and zNetClose (0x404010).
- Not removed, though the map has it: RegistrationFailureStateHandler (0x347580).

Layouts, plainly shown by settled rows: RoomGame grew by 8 bytes at +0x204 (a float time stamp
written by 0x34a7b0, a byte flag at +0x208); PersistentGame's own bytes moved from +0x204 to
+0x20c, and it gained a word at +0x218.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses.
- The Init split (0x404640 Init, 0x404130 new) touches list b's Init row; the other reading is
  given above.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| deviating (weak, slot-only) | 3 | 3 | 0 |
| new | 8 | 6 | 2: 0x3474d0 is ConnectErrorStateHandler, 0x349100 is cbGetPolicyRequest |
| unsure | 2 | 1 (LibNETSetup) | 1: 0x349040 is new |
| exact, identical-copy | 7 | 7 | 0 |
| removed | 19 | 18 | 1: RegistrationFailureStateHandler is 0x347580 |

Outside the list, in its owner ranges: 2 crossed deviating pairs (0x33f800, 0x345b90), 4 exact
stubs paired one off (0x347550-0x347580), and CNetCnf::Init on the wrong half of its split.

The sample: 15 of 15 deviating rows are the same function on both sides.

What misled it:

- The state-handler stubs: five byte-identical `jr ra; nop` handlers in a row in the prototype; the
  first (ConnectError) got a body in the release, so position pairing shifted the other four by
  one. The handler table that Open fills (same offsets on both sides) decides each one.
- cbGetPolicyRequest: the request moved out of LobbyActiveStateHandler into a new function placed
  where the callback used to be, and the callback followed it; position (the tool's only
  evidence, similarity 0.299) pulled it to the request.
- The two clan/announcement callbacks: the release cbSendClanMessage now refreshes the clan
  messages directly, so it loads cbGetMyClanMessages where the prototype loaded cbGetAnnouncements;
  that shared loader and a shared global outweighed position and body.
- CNetCnf::Init: Init's work is split in two in the release; the tool took the half with the same
  first module loads (`global` evidence) over the half with Init's own flag, caller and place.

What cost the most time: the zNetCnf split (Init, LibNETSetup and 0x404130 are near twins in
shape). Suggestions:

- Pair callbacks by the exact-paired library call that receives them (MediusGetX gets cbGetX).
- Pair byte-identical stubs that are stored into one table by their store offsets.
- Show, for a function stored as a pointer, the store offset or the receiving call in the sheet.
