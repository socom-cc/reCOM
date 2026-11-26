# Stage 2: gamez/zNetwork, list b (2026-11-26)

List b of `gamez/zNetwork` (split 3 ways): 35 uncertain rows, all owned by zNetCnf.cpp (34
removed, 1 unsure). It has no deviating rows to sample and no exact rows. Pairing produced by
`socom-release-compare-c1` (`python tools/release/compare.py`); checked by
`socom-release-check-net-b`, who did not write the tool, at HEAD f4f0da93. The check sheet
(`compare.py --sheet gamez/zNetwork --list b`) was the starting point. Both images were
disassembled with the release tools. Callers were found by scanning both images for `jal`/`j`,
data words and `lui`/`addiu` pairs. Strings were searched byte for byte in both images. Each
removed row was also compared by opcode shape with every release function of 0.6 to 1.6 times
its size. Ghidra was not needed.

## zNetCnf.cpp's configuration code is gone from the release

The 34 removed rows are the prototype's memory-card network-configuration state machines
(`CCnfStateMachine` and its subclasses `CSMOpen`, `CSMSaveCombo`, `CSMSaveIFC`, `CSMSaveDev`,
`CSMAddDev`, `CSMDeleteAll`, `CSMInterface`), their error reporter `SignalNetCnfError`, and the
`std::deque` of state-handler member pointers that drives them. The evidence (called A below):

- **Strings**: the release has none of `mc0:/BWNETCNF/BWNETCNF`, `zNetCnf.cpp`,
  `run/irx/netcnfif.irx` or `Unknown NetCnf Error`. It also lacks the netcnf error texts
  (checked: "no space for memory", "can't get individual ID", "invalid usr_name",
  "Sting too long"). None of the class-name strings `CCnfStateMachine`, `CSMOpen`, `CSMSetInit`,
  `CSMDeleteAll`, `CSMSaveCombo`, `CSMAddCombo`, `CSMSaveIFC`, `CSMAddIFC`, `CSMSaveDev`,
  `CSMAddDev` or `CSMInterface` is in it (prototype 0x468330 to 0x4684c0).
- **Callees**: the map has the whole EE `sceNetcnfif` library as removed (21 functions,
  prototype 0x425280 to 0x425e9c). Every handler in the list calls into it, except the deque
  templates, the `Cleanup`s, the two empty states and `GetHWAddr` (which calls
  `sceInetInterfaceControl`).
- **Callers**: the handlers were reached only through member-pointer records (`@1248` and the
  others, pushed onto the machine's queue and called by `__ptmf_scall`) and through vtable slot
  +0x08 (`Cleanup`). Everything that pushed or ran them is removed in the map too: the `*Tick`
  functions, `push`, and the `CCnfStateMachine` and `CSMOpen` constructors. The release
  `InitFromCombo` (below) has no queue push, no `__ptmf_scall` and no virtual call. Its prototype
  ended by calling slot +0x08 on the ten machines inside `theNetCnf`.
- **No surviving copy**: the best release shape match for each removed row is weak (at most 0.88,
  and that only for the small `_free` wrappers against unrelated code), except for the four deque
  templates. The release copies that match those templates (0x34c7c0, 0x34e380, 0x34ea20, 0x24adb0,
  0x24b000, 0x210e40) are each an exact pair already, with other instantiations (the zNetMedius
  `LOBBY_STATE` deque, the zrndr_pipe `deque<Ui>`, game_state). The counts add up: each
  prototype instantiation outside zNetCnf has its release copy, and the three zNetCnf ones have
  none.

What replaced it:

- **The release reads the configurations through eznetcnf.** It has `run/irx/eznetcnf.irx` and
  an EE RPC client for it at 0x431a40 to 0x431ed0: eight new, unowned functions next to the
  ezNetCtl library, with strings such as "could not bind to eznetcnf service",
  "ezNetCnfGetCount returned %d" and "ezNetCnfGetNetcnfifData returned %d". The new function
  0x404640 calls `LibNETSetup`, loads `eznetcnf.irx`, binds the client (0x431a40) and sets a
  `$gp` flag. Its caller is `UINetCnfInit` (0x1d2170), where the prototype called
  `Init__7CNetCnfFb`. The release `Uninit` (0x404610) calls the client's 0x431b08.
- **The menu commands keep their names.** NetCnfOpen, NetCnfClose, NetCnfCurrCombo,
  NetCnfGetDispNames, NetCnfSelectCombo and NetCnfDeleteAll keep their places in the command
  table. Their handlers are new rows in the map (0x1d1f70, 0x1d1ef0, 0x1d1cb0, 0x1d1b90,
  0x1d1ba0, 0x1d1890), and they call the eznetcnf client (0x431b88, 0x431c48, 0x431d88,
  0x431e08, 0x431ed0) instead of starting a state machine.
- **Editing moved out of the game.** New code builds a state named "ShutdownState": its
  constructor 0x432810 runs from `__sinit_main.cpp`, and its vtable is at 0x48c5d0. Its slot
  +0x10 (0x432780) shuts down the pads, the CD and SIF, then calls
  `LoadExecPS2("cdrom0:\NTGUI.ELF;1", 3, ...)`, or `host0:./ntguihost.elf` when a flag is clear.
  The string `dlgReturnFromNTGUI2.rdr` is also in the data. So the save, add and delete machines
  for the memory card have no counterpart in the executable. The disc's separate set-up program
  edits the configurations, and the game only lists and selects them.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x404050 | 0x3feb80 `InitFromCombo__7CNetCnfFPci` | unsure, string | confirmed (deviating) | its only caller, `zNetLoadIRX`, calls it at the same place on both sides: after `CSnd::Close`, the +0xe5 test, the result stored in a `$gp` byte. Both start with `Init__7CNetCnf` and end with the same eznetctl tail: load `run/irx/eznetctl.irx`, then `initEzNetCtl`, `ezNetCtlSetProperties`, `ezNetCtlUpInterface`, return 1. The release dropped the combo selection, the ppp/pppoe/smap/an986 IRX loads and the state-machine queue, so similarity is 0.174. The caller passes no arguments now |
| - | 0x3fefb0 `Cleanup__12CSMSaveComboFv` | removed | confirmed | A; class gone (no RTTI name) |
| - | 0x3feff0 `Cleanup__10CSMSaveIFCFv` | removed | confirmed | A; class gone |
| - | 0x3ff030 `Cleanup__16CCnfStateMachineFv` | removed | confirmed | A; base class gone; slot +0x08 of seven machine vtables, none in the release |
| - | 0x3ff040 `Cleanup__12CSMInterfaceFv` | removed | confirmed | A; class gone |
| - | 0x3ff080 `Cleanup__7CSMOpenFv` | removed | confirmed | A; class gone |
| - | 0x3ffc60 `AllocMem__10CSMSaveDev...` | removed | confirmed | A; sceNetcnfif callees gone |
| - | 0x3ffd30 `GetAddr__10CSMSaveDev...` | removed | confirmed | A |
| - | 0x3ffe10 `SendData__10CSMSaveDev...` | removed | confirmed | A |
| - | 0x3ffea0 `AddEntry__10CSMSaveDev...` | removed | confirmed | A; `BWNETCNF` path absent |
| - | 0x3fff80 `GetHWAddr__9CSMAddDev...` | removed | confirmed | A; see New and removed |
| - | 0x400140 `DeleteAll__12CSMDeleteAll...` | removed | confirmed | A |
| - | 0x4001f0 `AllocMem__12CSMSaveCombo...` | removed | confirmed | A |
| - | 0x4002d0 `GetAddr__12CSMSaveCombo...` | removed | confirmed | A |
| - | 0x4003c0 `SendToIOP__12CSMSaveCombo...` | removed | confirmed | A |
| - | 0x400450 `AddEntry__12CSMSaveCombo...` | removed | confirmed | A |
| - | 0x400510 `AllocMem__10CSMSaveIFC...` | removed | confirmed | A |
| - | 0x4005e0 `GetAddr__10CSMSaveIFC...` | removed | confirmed | A |
| - | 0x4006c0 `SendData__10CSMSaveIFC...` | removed | confirmed | A |
| - | 0x400750 `AddEntry__10CSMSaveIFC...` | removed | confirmed | A |
| - | 0x400820 `GetComboCount__7CSMOpen...` | removed | confirmed | A |
| - | 0x400900 `GetComboList__7CSMOpen...` | removed | confirmed | A; `zNetCnf.cpp` line tokens absent |
| - | 0x400b60 `GetIfcCount__7CSMOpen...` | removed | confirmed | A |
| - | 0x400c40 `GetIfcList__7CSMOpen...` | removed | confirmed | A |
| - | 0x400db0 `GetDevCount__7CSMOpen...` | removed | confirmed | A |
| - | 0x400e90 `GetDevList__7CSMOpen...` | removed | confirmed | A |
| - | 0x401000 `AllocMem__7CSMOpen...` | removed | confirmed | A |
| - | 0x4010d0 `GetEntry__7CSMOpen...` | removed | confirmed | A |
| - | 0x401270 `SignalNetCnfError__Fi` | removed | confirmed | A; all 18 callers removed; its error texts absent |
| - | 0x401480 `StartState__16CCnfStateMachine...` | removed | confirmed | A; reached only through the member-pointer records |
| - | 0x401490 `IdleState__16CCnfStateMachine...` | removed | confirmed | A; the same |
| - | 0x4014d0 `pop_front__...deque<M16CCnfStateMachine...>` | removed | confirmed | A; its callers are removed except `InitFromCombo`, and the release version of that no longer calls it; the equal-shape release copy 0x34c7c0 is zNetMedius's `LOBBY_STATE` copy (exact, call) |
| - | 0x4015b0 `push_back__...deque<M16CCnfStateMachine...>` | removed | confirmed | A; all 36 callers removed |
| - | 0x4017e0 `grow_buf_back__...deque<M16CCnfStateMachine...>` | removed | confirmed | A; caller push_back removed; the look-alikes 0x24adb0 and 0x34e380 are paired elsewhere |
| - | 0x401a40 `do_assign<...M16CCnfStateMachine...>` | removed | confirmed | A; caller grow_buf_back removed; the three equal-shape release copies are paired elsewhere |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date |
|---|---|---|---|---|
| 0x404050 | 0x3feb80 | the only caller, zNetLoadIRX, calls it at the same place (after CSnd::Close, the +0xe5 test); the same Init__7CNetCnf start and eznetctl.irx / initEzNetCtl / ezNetCtlSetProperties / ezNetCtlUpInterface tail | socom-release-check-net-b | 2026-11-26 |

The 34 removed rows stay as the map has them.

## New and removed

There are no new rows in the list.

Really removed: all 34 removed rows. Their work went to three places, described in the first
section. Listing and selecting the configurations goes through the eznetcnf IRX and its client.
Editing them goes to the separate `NTGUI.ELF`. Reading the interface hardware data, the job of
`GetHWAddr__9CSMAddDev`, is done by the new 0x403e30: it calls `sceInetGetInterfaceList` and then
`sceInetInterfaceControl` three times per interface, and its caller is the new handler 0x1d1a50
of the menu command NetGetInterfaceList.

Just outside the list (not settled here):

| release | map | finding |
|---|---|---|
| 0x403e30, 0x403f80, 0x404010, 0x404640 | new, no owner, in no list | they belong to **zNetCnf.cpp**. They lie in its release range, which runs 0x403e30 to 0x4046a0: from just after the `CInGameWeaponSel` constructor up to `TRC_PreparePowerOff`, the same bounds as in the prototype. 0x403e30 lists interfaces (caller 0x1d1a50, guess `CNetCnf::GetInterfaceList`). 0x403f80 polls `ezNetCtlGetStatus` and calls a callback (caller `zNetUpdate`, guess `CNetCnf::PollStatus`). 0x404010 runs `ezNetCtlDownInterface` and `exitEzNetCtl` (caller `zNetClose`, guess `CNetCnf::Close`). 0x404640 is the eznetcnf start-up described above (guess `CNetCnf::InitEzNetCnf`). All names are guesses |
| 0x431a40 to 0x431ed0 | 8 new, no owner | the EE client of the eznetcnf IRX, a provider library next to ezNetCtl. 0x431a40 binds the RPC (`sceSifSearchModuleByName`, `sceSifBindRpc`) |
| 0x1d1f70, 0x1d1ef0, 0x1d1cb0, 0x1d1b90, 0x1d1ba0, 0x1d1890 | new (zAnim lists a and c) | they fill the command-table entries of the removed `UINetCnfOpen`, `Close`, `CurrCombo`, `GetDispNames`, `SelectCombo` and `DeleteAll` (release table at 0x44a7a0: name, then handler, 12 bytes per entry). The zAnim checkers should decide whether these are deviating pairs with changed bodies or new functions |
| 0x432780, 0x432810 | new, no owner | "ShutdownState", which launches NTGUI.ELF (above) |

## Still unsure

None of the list's rows. Open points:

- The four unowned zNetCnf.cpp functions and the eznetcnf client above are in no check list.
- The guessed names above.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| removed | 34 | 34 | 0 |
| unsure | 1 | 1 (pair confirmed) | 0 |

The sample: no deviating rows in this list.

Nothing misled the tool in this list. Its only weak row was right. The `string` evidence
(`run/irx/eznetctl.irx`) and the same caller agree, and the low similarity is the code the
release removed.

What cost the most time was ruling out surviving copies of the deque templates, because
equal-shape instantiations of other types exist. The map's `call` evidence on those copies
settled it. Suggestions:

- When a file's name string, its RTTI class names and its main library are all absent from the
  release, present its removed rows as one group with that evidence and not row by row.
- Give unowned new functions the owner of the file range they sit in, the way the
  zNetCnf.cpp range 0x403e30 to 0x4046a0 would assign the four functions above.
