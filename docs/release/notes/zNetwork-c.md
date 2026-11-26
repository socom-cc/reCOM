# Stage 2: gamez/zNetwork, list c (2026-11-26)

List c of `gamez/zNetwork` (split 3 ways): the owner files zNetDme.cpp and zNetCnf.cpp. It holds
36 uncertain rows (1 new, 35 removed), 10 sampled deviating rows out of 10, and 15 exact rows
that were not checked. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-net-c`, who did not write
the tool, at HEAD f4f0da93. The check sheet (`compare.py --sheet gamez/zNetwork --list c`) was
the starting point. Both images were disassembled with the release tools; callers were found by
scanning both images for `jal`/`j`, data words, `lui`/`addiu` pairs and `$gp` loads. Ghidra was
not needed.

What settled rows: the UI command table of zanim_menu.cpp (prototype 0x439a30, release
0x44a7a0: the same command ids 0x6c–0x8b and name strings on both sides), which shows what became
of every caller of the removed CNetCnf functions; the call sites in paired callers (zNetInitEx,
the CZNetVoice functions); strings (`network.rdr` and its keys, the zNetCnf.cpp line tokens and
the class names are absent from the release; the release has the ezNetCnf library's own
messages); the `$gp` reads of `MediusWorldID`.

The picture for zNetCnf.cpp: the prototype's in-game network-configuration editor (CNetCnf's
Add/Save/Delete functions, driven by CCnfStateMachine and its CSM* states through a
`std::queue`/`std::deque` of member-function pointers built by `__sinit_zNetCnf.cpp`) is gone.
In the release, the editor's UI commands are one-instruction stubs, and the commands that remain
useful (open, list, select, save the default combination) call SCE's ezNetCnf library
(`libezcnf.c`, new at 0x431a40–0x431ed0) and ezNetCtl instead. This is consistent with the full
game using the standard network configuration file instead of its own editor; that reading is
mine, the code facts are above.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x33d270 | - | new, copy | confirmed | `return MediusWorldID` (`lw v0,-0x60a0(gp)`, the zNetMedius.cpp unnamed-namespace static); callers are the release CZNetVoice functions (IAmNewSessionMaster, WorkerThread, Init), called with theLobby in a0, result passed to PTTServer_Start; the prototype voice code never reads MediusWorldID. Equal bytes elsewhere are other one-load getters |
| - | 0x322190 `zNetInit__9CZNetworkFv` | removed | confirmed | replaced inline: the release zNetInitEx no longer calls it and instead strcpy's "socom2002-prod.pdonline.scea.com" to +79 and "10075" to +143, the two fields zNetInit filled from `network.rdr` (medius_ip, medius_port) when online. `network.rdr`, server_ip, personal_id and connection_id occur nowhere in the release |
| - | 0x3fd330 `DeleteAllTick__7CNetCnfFPv` | removed | confirmed | sole caller UINetCnfDeleteAll; the release handler of that command (id 0x8a, 0x1d1890) is `return 0` |
| - | 0x3fd590 `push__Q23std221queue<M16CCnfStateMachine…>` | removed | confirmed | state-machine queue helper; every caller is a removed CNetCnf function or InitFromCombo, and the release InitFromCombo (0x404050) uses ezNetCtl directly and pushes nothing |
| - | 0x3fd5a0 `__vc__Q210Metrowerks148cdeque<PM16CCnfStateMachine…>` | removed | confirmed | the same: callers are the removed Tick functions, OpenTick and InitFromCombo |
| - | 0x3fd5b0 `DeleteAll__7CNetCnfFPv` | removed | confirmed | caller UINetCnfDeleteAll (stub, above) |
| - | 0x3fd630 `GetComboData__7CNetCnfFPv` | removed | confirmed | caller UINetSaveCombo; the release handler of that command (id 0x79, 0x1d18a0) picks an entry of a 104-byte table and calls ezNetCnfSetDefault (0x431e08) |
| - | 0x3fd640 `SaveComboTick__7CNetCnfFPv` | removed | confirmed | replaced by ezNetCnfSetDefault in the same handler |
| - | 0x3fd8a0 `SaveCombo__7CNetCnfFPvP15sceNetcnfifDataPCc` | removed | confirmed | the same; its zNetCnf.cpp:805/806 allocator calls have no release counterpart (no "zNetCnf.cpp" string in the release) |
| - | 0x3fd990 `AddComboTick__7CNetCnfFPv` | removed | confirmed | caller UINetAddCombo; release handler (id 0x76, 0x1d1a20) is `return 0` |
| - | 0x3fdac0 `AddCombo__7CNetCnfFPv` | removed | confirmed | the same |
| - | 0x3fdb50 `SaveIFCTick__7CNetCnfFPv` | removed | confirmed | caller UINetSaveIfc; release handler (id 0x78, 0x1d19f0) is `return 0` |
| - | 0x3fddb0 `SaveIFC__7CNetCnfFPvP15sceNetcnfifDataPCc` | removed | confirmed | the same |
| - | 0x3fdea0 `SaveDevTick__7CNetCnfFPv` | removed | confirmed | caller UINetSaveDev; release handler (id 0x77, 0x1d1a10) is `return 0` |
| - | 0x3fe100 `SaveDev__7CNetCnfFPv` | removed | confirmed | the same |
| - | 0x3fe1c0 `GetDevIndex__7CNetCnfFPv` | removed | confirmed | caller UINetGetDevIndex; release handler (id 0x7d, 0x1d1a00) is `return 1` |
| - | 0x3fe270 `GetMACAddr__7CNetCnfFPvPci` | removed | confirmed | caller UINetAddDev; release handler (id 0x74, 0x1d1a40) is `return 0`; its MAC format string is absent from the release |
| - | 0x3fe310 `GetEnvData__7CNetCnfFPv` | removed | confirmed | caller UINetSaveIfc (stub, above) |
| - | 0x3fe320 `AddIFCTick__7CNetCnfFPv` | removed | confirmed | caller UINetAddIfc; release handler (id 0x75, 0x1d1a30) is `return 0` |
| - | 0x3fe450 `AddIFC__7CNetCnfFPv` | removed | confirmed | the same |
| - | 0x3fe4e0 `AddDevTick__7CNetCnfFPv` | removed | confirmed | caller UINetAddDev (stub, above) |
| - | 0x3fe610 `AddDev__7CNetCnfFPvPCc` | removed | confirmed | the same |
| - | 0x3fe760 `GetInterfaceEntry__7CNetCnfFPvi` | removed | confirmed | callers UINetUpdateIFCVars and UINetSaveIfc (release: stubs) and UINetGetInterfaceList, whose release handler (id 0x73, 0x1d1a50) reads the entries from its own stack array filled by 0x403e30 |
| - | 0x3fe790 `InterfaceCount__7CNetCnfFPv` | removed | confirmed | the same handler uses 0x403e30's return value as the count |
| - | 0x3fe7a0 `ReadInterfaceListTick__7CNetCnfFPv` | removed | confirmed | the polling half of the list read; the release read (0x403e30) is synchronous |
| - | 0x3fe8d0 `ReadInterfaceList__7CNetCnfFPv` | removed | confirmed | replaced by new 0x403e30, called from the same command handler with the same limit 6; not paired: different signature (array, count) and no CSMInterface object |
| - | 0x3fe900 `Start__12CSMInterfaceFiP15sceNetcnfifData` | removed | confirmed | its work is in 0x403e30: the same sceInetGetInterfaceList call and the same three sceInetInterfaceControl calls per interface (codes 8/4, 2/256, 3/256), without the memalign, the strcmp filter and the state push |
| - | 0x4020e0 `__ct__16CCnfStateMachineFv` | removed | confirmed | sole caller `__sinit_zNetCnf.cpp`, removed; no CCnfStateMachine name in the release |
| - | 0x4021d0 `__ct__7CSMOpenFv` | removed | confirmed | the same; no CSMOpen name in the release |
| - | 0x402350 `tear_down__Q23std145deque<M16CCnfStateMachine…>` | removed | confirmed | template helper of the state machine's deque; callers are the two removed constructors and the deque destructor (see 0x1d9620 below) |
| - | 0x402500 `__ct__…deque<…>FRCQ23std145deque<…>` | removed | confirmed | callers are the two removed constructors |
| - | 0x4026f0 `__pp__…deque<…>14const_iteratorFv` | removed | confirmed | sole caller the deque copy constructor, removed |
| - | 0x4027a0 `__ct__…deque<…>FRCQ23std70allocator<…>` | removed | confirmed | callers are the two removed constructors |
| - | 0x4027d0 `make_iterator__…deque<…>CFUi` | removed | confirmed | sole caller the deque copy constructor, removed |
| - | 0x4028f0 `make_iterator__…deque<…>FUi` | removed | confirmed | sole caller tear_down, removed |
| - | 0x402a10 `destroy__…deque<…>` | removed | confirmed | sole caller tear_down, removed |

No release function resembles any removed deque helper (best similarity 0.38 over the 389 new
functions in the slot); the closest new functions near the CNetCnf rows are the ezNetCtl
helpers below, which do other work.

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x33c300 | 0x321440 `zNetSendApplicationMessage__9CZNetworkFciiiiPUcb` | yes | the same 19 callers; imm-only (line 856 → 936) |
| 0x33c410 | 0x321550 `zNetLeaveAndDisconnect__9CZNetworkFv` | yes | same caller (DMEDisconnectFromGameServer), same callees |
| 0x33c4f0 | 0x321630 `zNetConnect__9CZNetworkFPFiiPCc_vPFiiPCc_v` | yes | same caller (DMEConnectToGameServer), same callees plus NetDisconnect |
| 0x33c7d0 | 0x321900 `zNetClose__9CZNetworkFv` | yes | the same three callers; NetClose plus new 0x404010 |
| 0x33c8b0 | 0x3219e0 `zNetTick__9CZNetworkFv` | yes | same caller (NetTickThreadEntry); the tail call to NetTick became a call plus error recovery and the lobby tick |
| 0x33c910 | 0x3219f0 `zNetUpdate__9CZNetworkFv` | yes | same caller (CGame::Tick), same callee sequence plus new 0x403f80 |
| 0x33cbd0 | 0x321ca0 `zNetInitialize__9CZNetworkFv` | yes | same caller (zNetInitEx), same callees plus NetSetBufferSize and NetClose |
| 0x33ccb0 | 0x321d60 `zNetInitEx__9CZNetworkFv` | yes | the same two callers; zNetInit's call replaced (above) |
| 0x33cda0 | 0x321e20 `zNetLoadIRX__9CZNetworkFv` | yes | same caller (zNetInitEx), the same IRX sequence; netcnf.irx with icons added |
| 0x33d120 | 0x322150 `IOPRebootHandler__FQ211CIOPManager11RebootPhaseQ211CIOPManager10RebootModePv` | yes | its address is loaded by zNetLoadIRX on both sides |

Just outside the list (found through the same callers; not settled here):

| release | map | finding |
|---|---|---|
| 0x1d1f70, 0x1d1ef0, 0x1d1cb0, 0x1d1b90, 0x1d1a50, 0x1d1a40, 0x1d1a30, 0x1d1a20, 0x1d1a10, 0x1d19f0, 0x1d18a0, 0x1d19d0, 0x1d19c0, 0x1d19b0, 0x1d1a00, 0x1d1ba0, 0x1d1740, 0x1d1890 | new (zanim_menu.cpp) | the command table pairs them, by id 0x6e–0x7e, 0x88 and 0x8a, with the removed UINetCnfOpen, UINetCnfClose, UINetCnfCurrCombo, UINetCnfGetDispNames, UINetGetInterfaceList, UINetAddDev, UINetAddIfc, UINetAddCombo, UINetSaveDev, UINetSaveIfc, UINetSaveCombo, UINetUpdateIFCVars, UINetGetDevInfo, UINetGetIFCInfo, UINetGetDevIndex, UINetCnfSelectCombo, UIRebootIOP and UINetCnfDeleteAll, in that order. Eleven of them are now `return 0` or `return 1` stubs. Whether a handler that became a stub counts as the same function is for the zAnim check. The table also confirms the unsure 0x1d2170 = UINetCnfInit (id 0x6c) and 0x1d1e20 = UINetCnfCount (id 0x70) |
| 0x1d9620 | unsure, 0x402060 `__dt__…deque<M16CCnfStateMachine…>` (zAnim-a) | doubtful: the release has no other function of that deque and no user of CCnfStateMachine; it calls a 64-byte new 0x1d9740 where the prototype destructor calls the 420-byte tear_down; its callers are a new zanim_menu.cpp function (0x1d7db0). Probably the destructor of another container. For the zAnim-a check |
| 0x431a40–0x431ed0 | 8 × new, no owner | SCE ezNetCnf library (`libezcnf.c`, RPC service "eznetcnf"), named by its own messages: 0x431b88 ezNetCnfGetCount, 0x431c48 ezNetCnfGetCombinationList, 0x431d08 ezNetCnfGetCombination, 0x431d88 ezNetCnfGetDefault, 0x431e08 ezNetCnfSetDefault, 0x431ed0 ezNetCnfGetNetcnfifData; 0x431a40 binds the RPC (guess ezNetCnfInit), 0x431b08 stops and unloads the module (guess ezNetCnfExit). Provider SCE, beside ezNetCtl |
| 0x403e30, 0x403f80, 0x404010, 0x404640 | new, no owner | zNetCnf.cpp by position (between CInGameWeaponSel's constructor and InitFromCombo, and after Uninit); described below |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x33d270 | new | getter of the zNetMedius.cpp static MediusWorldID ($gp load); callers only the release CZNetVoice functions; the prototype voice code never reads it; equal bytes elsewhere are other one-load getters | socom-release-check-net-c | 2026-11-26 |

No other row changed class or counterpart. Owner: 0x33d270 belongs to zNetMedius.cpp (it reads
that file's unnamed-namespace static and comes directly before SendEndGameReport, the first
zNetMedius.cpp function), not zNetDme.cpp.

## New and removed

New (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x33d270 | returns MediusWorldID; called with theLobby as `this` | guess: `CZOnlineLobby::GetMediusWorldID()` (receiver from the call sites, field from the `$gp` load) |
| 0x403e30 | (array, max): sceInetGetInterfaceList, then per interface a 576-byte record: id and three sceInetInterfaceControl reads; returns the count | guess: `CNetCnf::ReadInterfaceList(…, int)`, the synchronous successor of ReadInterfaceList + CSMInterface::Start (outside the list) |
| 0x403f80 | when ezNetCtl is up, reads ezNetCtlGetStatus and on some states calls a stored callback with "MP_MEDIUS_ERROR"; called from zNetUpdate | guess: `CNetCnf::CheckStatus()` (outside the list) |
| 0x404010 | when ezNetCtl is up: ezNetCtlDownInterface(0), clear the flag, exitEzNetCtl; called from zNetClose | guess: `CNetCnf::DownInterface()` (outside the list) |
| 0x404640 | once: LibNETSetup, load `run/irx/eznetcnf.irx`, then ezNetCnfInit (0x431a40); called from UINetCnfInit | guess: `CNetCnf::EzNetCnfSetup()` (outside the list) |

Really removed, in this list: zNetInit (its server name and port are hard-coded in zNetInitEx;
`network.rdr` is gone), and the CNetCnf editor with its state machine: the Add/Save/Delete
functions and their Tick partners (their UI commands are stubs), the interface-list functions
(replaced by 0x403e30), SaveCombo (replaced by ezNetCnfSetDefault), the CCnfStateMachine and
CSMOpen constructors (with `__sinit_zNetCnf.cpp`), and the deque/queue template helpers of the
state machine.

Layouts: none shown plainly by these rows.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses, except the six ezNetCnf functions named by their
  own messages.
- 0x1d9620 (zAnim-a) and the eighteen command handlers paired through the table: for the zAnim
  check.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| new | 1 | 1 | 0 |
| removed | 35 | 35 | 0 |

The sample: 10 of 10 deviating rows are the same function on both sides.

Nothing in the list misled the tool. Outside it, the same kind of miss as before: handlers
reached only through a data table (the zanim_menu.cpp command table: a name string, a function
pointer and an id per entry) were left as removed/new pairs, as vtable slots were before the
tool read vtables. Suggestion: pair the function pointers of any table whose entries carry equal
name strings or equal ids on both sides, as for vtable slots.

What cost the most time: finding where the removed CNetCnf functions' callers went; the
command table answered it at once.
