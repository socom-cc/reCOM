# Stage 2: gamez/zInput (2026-11-26)

The one list of `gamez/zInput` (list a): the owner files zin_main.cpp, zin_keyboard.cpp,
zin_cheats.cpp and remote_control.cpp (release 0x21d190-0x21f980, 0x2e0120-0x2e0830 and
0x43d808-0x43dcf0). It holds 20 uncertain rows (9 new, 9 removed, 2 unsure), 15 sampled deviating
rows out of 23, and 23 exact rows that were not checked one by one. Pairing produced by
`socom-release-compare-c1` (`python tools/release/compare.py`); checked by
`socom-release-check-input-state`, who did not write the tool, at HEAD 293696c3. The check sheet
(`compare.py --sheet gamez/zInput --list a`) was the starting point. Both images were disassembled
with the release tools; callers were found by scanning both images for `jal`/`j`, data words and
`lui`/`addiu` pairs. Ghidra was not needed.

As the guard on the committed pairs, all 48 paired rows of the ranges had their callers and
address-loaders compared with the prototype's through the map, and their ordered calls and loads
compared for substitutions; the CRemoteCtrl vtable was aligned slot by slot (34 slots); the one
function that loads the address of a zInput function (CInput::Init, IOPRebootHandler) had its
pointer loads compared.

What settled rows, in the order it was used: the call sites in the paired GetKeyReadThisFrame and
InitKeyreadStuff; the RPC function numbers and the library's own messages; the CRemoteCtrl vtable
slots; the call sites in UISetStickPreset, UIStoreOptions and CZPauseTest::HudTick.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x21b020 `GetAcceleration__4CPadFi` | removed | confirmed | at its call sites in UISetStickPreset and UIStoreOptions the release reads the stick's new +0x1c field inline (`1.0 - pad+0x1ec` for stick 1) |
| - | 0x21b0f0 `SetAcceleration__4CPadFif` | removed | confirmed | its one caller, CStickAccelerationTuner::UpdateUIVar, is removed; the CStickInertiaTuner that replaces it writes the pad field itself (zUI note) |
| - | 0x21b610 `Update__6CCheatFfP4CPad` | removed | confirmed | the cheat system is gone: only caller TickAll (removed) |
| - | 0x21b780 `TickAll__6CCheatFfP4CPad` | removed | confirmed | its one call, in CZPauseTest::HudTick, is gone from the release HudTick |
| - | 0x21b800 `__dt__10CCheatListFv` | removed | confirmed | registered only by `__sinit_zin_cheats.cpp`, which is removed too |
| 0x2e01d0 | - | new, copy, owner guess | confirmed | `jr ra`: slot +0x5c of the CRemoteCtrl vtable, which in the prototype held the inherited `OnMissionStart__9CSealCtrlFv`; the vtable decides the twin |
| 0x2e01e0 | - | new, copy, owner guess | confirmed | `jr ra`: slot +0x60, the inherited `OnMissionEnd__9CSealCtrlFv` in the prototype. Both CSealCtrl bodies are no longer empty in the release |
| - | 0x21b9b0 `sceUsbKeybdGetInfo__FPUc` | removed | confirmed | replaced by the SCE library function 0x43d808 (see below) |
| - | 0x21ba10 `sceUsbKeybdInit__Fv` | removed | confirmed | InitKeyreadStuff now calls the library's init 0x43d578 (bind 0x80000211, semaphore, interrupt handler) |
| - | 0x21ba90 `GetNewKeyPress__FPUc` | removed | confirmed | the release GetKeyReadThisFrame (352 bytes, was 624) reads the library's key-code buffer directly; no comparison with the last keys is left |
| 0x43d808 | 0x21b950 `sceUsbKeybdRead__FUiPUc` | unsure, call-deviating | corrected to new; 0x21b950 removed | `sceUsbKbGetInfo` of `libusbkb.a` (its message "sceUsbKbGetInfo: sceSifCallRpc", RPC function 1). By role it is GetInfo, not Read (the prototype Read is RPC 2), and it is the SCE library, not the zin_keyboard.cpp wrapper |
| 0x43d8a8 | - | new, owner guess | confirmed; owner provider | `sceUsbKbRead` (message, RPC 2); called by GetKeyReadThisFrame where the prototype called sceUsbKeybdRead |
| 0x43d978 | - | new, owner guess | confirmed; owner provider | `sceUsbKbGetLocation` (message, RPC 3); no caller (the prototype's GetLocation call is gone) |
| 0x43da48 | - | new, owner guess | confirmed; owner provider | `sceUsbKbSetLEDStatus` (message, RPC 4); no caller |
| 0x43db18 | - | new, owner guess | confirmed; owner provider | `sceUsbKbSetLEDMode` (message, RPC 5); no caller |
| 0x43dc08 | - | new, owner guess | confirmed; owner provider | writes two values (+0x18, +0x1c) of a keyboard record; no caller |
| 0x43dc50 | - | new, owner guess | confirmed; owner provider | writes a 2-valued mode at +0x4 of keyboard record `no`; caller InitKeyreadStuff (0, 0) |
| 0x43dca0 | - | new, owner guess | confirmed; owner provider | writes a 3-valued mode at +0x8 of keyboard record `no`; no caller |
| - | 0x21b8f0 `sceUsbKeybdGetLocation__FiPUc` | removed | confirmed | replaced by the library's 0x43d978, which nothing calls |
| 0x43dcf0 | 0x21b870 `sceUsbKeybdSync__Fi` | unsure, call-deviating | corrected to new; 0x21b870 removed | `sceUsbKbSync(mode, &result)` of the library (semaphore and the result dispatch 0x43dd90); the prototype's one-argument wrapper is removed |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x21d190 | 0x2194e0 `DeletePad__6CInputFUi` | yes | the same callers StopEngine and ClosePadIO |
| 0x21d450 | 0x219770 `IOPRebootHandler__6CInputF...` | yes | its address is loaded by CInput::Init on both sides |
| 0x21d5b0 | 0x219850 `UpdateButton__4CPadF10PAD_BUTTONUi` | yes | same caller CPad::Tick |
| 0x21d720 | 0x2199a0 `SetButtonState__4CPadF10PAD_BUTTON9KEY_STATE` | yes | the same seven callers, plus two release ones |
| 0x21d7d0 | 0x219a50 `GetSingleClick__4CPadF10PAD_BUTTON` | yes | same caller CSealCtrl::PreTick |
| 0x21ec70 | 0x21aa50 `Dilate__4CPadFRfRfi` | yes | same caller Tick; the same statics init$650, which_dilation$649 |
| 0x21ee00 | 0x21ac30 `CheckStickVelocity__4CPadFRfRfi` | yes | same caller Tick |
| 0x21f060 | 0x21ae80 `ReadControlFile__10CStickTypeFi` | yes | same caller, the CPad constructor |
| 0x21f140 | 0x21af40 `SetPreset__4CPadFii` | yes | same callers UISetStickPreset and UIStoreOptions |
| 0x21f260 | 0x21b1d0 `GetSensitivity__4CPadFi` | yes | the same two callers, at the same call site |
| 0x21f300 | 0x21b210 `SetSensitivity__4CPadFif` | yes | same caller CStickSensitivityTuner::UpdateUIVar |
| 0x21f380 | 0x21b240 `__dt__4CPadFv` | yes | the same three callers |
| 0x21f3f0 | 0x21b2b0 `Flush__4CPadFv` | yes | same callers OrdersMenu::HandlePad and CInput::Flush |
| 0x21f8e0 | 0x21be90 `InitKeyreadStuff__Fv` | yes | same caller CInput::Init |
| 0x2e02f0 | 0x2ce310 `PreTick__11CRemoteCtrlFf` | yes | slot +0xc of the CRemoteCtrl vtable |

The cross-check found no wrong committed pair outside the list's rows.

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x43d808 | new | sceUsbKbGetInfo of libusbkb.a (own message, RPC 1); not the prototype's zin_keyboard.cpp wrapper sceUsbKeybdRead (RPC 2) | socom-release-check-input-state | 2026-11-26 | provider:SCE libusbkb | |
| removed | 0x21b950 | sceUsbKeybdRead: the zin_keyboard.cpp RPC wrapper is replaced by libusbkb's sceUsbKbRead (0x43d8a8) at its call site in GetKeyReadThisFrame | socom-release-check-input-state | 2026-11-26 | | |
| 0x43dcf0 | new | sceUsbKbSync of libusbkb.a (two arguments, semaphore, result dispatch 0x43dd90) | socom-release-check-input-state | 2026-11-26 | provider:SCE libusbkb | |
| removed | 0x21b870 | sceUsbKeybdSync: the zin_keyboard.cpp wrapper is replaced by libusbkb's sceUsbKbSync (0x43dcf0) | socom-release-check-input-state | 2026-11-26 | | |
| 0x43d578-0x43dd90 | - | SCE USB keyboard library (libusbkb.a, its own messages), appended at the end of the text with the release's other new libraries | socom-release-check-input-state | 2026-11-26 | provider:SCE libusbkb | |

Rows that change together: the four rows above split the two unsure pairs; the range row moves
the owner of 0x43d8a8-0x43dca0 (and of 0x43d578, 0x43d760, 0x43dd80, 0x43dd90, which had none)
from zin_keyboard.cpp to the provider. zin_keyboard.cpp then owns only 0x21f780-0x21f980 in the
release, and zin_cheats.cpp owns nothing (its range 0x21f760-0x21f760 is a position artefact: that
address is OpenPadIO of zin_main.cpp).

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x2e01d0 | empty override | `OnMissionStart__11CRemoteCtrlFv` (vtable slot +0x5c, the inherited CSealCtrl virtual of the prototype) |
| 0x2e01e0 | empty override | `OnMissionEnd__11CRemoteCtrlFv` (vtable slot +0x60, the same) |
| 0x43d808 | RPC 1, keyboard info | `sceUsbKbGetInfo` (own message) |
| 0x43d8a8 | RPC 2, read keyboard `no` | `sceUsbKbRead` (own message) |
| 0x43d978 | RPC 3 | `sceUsbKbGetLocation` (own message) |
| 0x43da48 | RPC 4 | `sceUsbKbSetLEDStatus` (own message) |
| 0x43db18 | RPC 5 | `sceUsbKbSetLEDMode` (own message) |
| 0x43dc08 | sets two non-negative values of a keyboard | guess: `sceUsbKbSetRepeat` (start time, interval) |
| 0x43dc50 | sets a mode < 2 of a keyboard; InitKeyreadStuff sets 0 for keyboard 0 | guess: `sceUsbKbSetReadMode` or `sceUsbKbSetCodeType` |
| 0x43dca0 | sets a mode < 3 of a keyboard | guess: `sceUsbKbSetArrangement` (three layouts) |
| 0x43dcf0 | waits for or polls the last RPC and post-processes its result | `sceUsbKbSync` (the library's API; the prototype wrapper's name) |

Outside the list, the same library: 0x43d578 `sceUsbKbInit` (messages "libusbkb : bind errr",
"CreateSema Error"), 0x43d760 `sceUsbKbEnd` (messages "RemoveIntcHandler() --> error",
"DeleteSema() --> error"), 0x43dd80 the RPC end callback (iSignalSema), 0x43dd90 the result
dispatch through the table at 0x456c28.

Really removed:

- The zin_keyboard.cpp copies of the USB keyboard RPC wrappers (Init, GetInfo, Read, GetLocation,
  Sync): their work is done by libusbkb.a. GetNewKeyPress: dropped; GetKeyReadThisFrame takes the
  key codes from the library's read buffer.
- GetAcceleration and SetAcceleration: the acceleration setting became the stick inertia (the zUI
  note's CStickInertiaTuner); its getter is inline at the old call sites.
- The cheat system: CCheat::Update, CCheat::TickAll, the CCheatList destructor and
  `__sinit_zin_cheats.cpp`; CZPauseTest::HudTick no longer ticks cheats.

Layout, plainly shown by settled rows: the CPad stick record grew from 32 to 40 bytes, with a
float at +0x1c (the inertia that SetPreset now writes and the old GetAcceleration call sites read).

## Still unsure

None of the list's rows. Open points:

- Reading libusbkb as new and removed rather than as deviating pairs with the old wrappers is a
  judgement: the prototype functions are authored C++ wrappers in zin_keyboard.cpp, the release
  ones the SCE C library with another calling contract (Sync takes two arguments).
- The map has no rows for the rest of libusbkb: the result handlers in the table at 0x456c28
  (0x43ddf8, 0x43de50, 0x43e3c8, 0x43e418, 0x43e438), the interrupt handler 0x43e458 that
  sceUsbKbInit registers, and the code up to about 0x43ea1c. For the tool (discovery).
- The names of 0x43dc08, 0x43dc50 and 0x43dca0 are guesses.

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| removed | 9 | 9 | 0 |
| new | 9 | 9 (owner wrong for 7) | 0 |
| unsure, call-deviating | 2 | 0 | 2: both are libusbkb functions; 0x43d808 is GetInfo by role, not Read |

Owners: the 7 new rows at 0x43d8a8-0x43dca0 belong to the SCE library, not zin_keyboard.cpp. The
owner guesses for the two CRemoteCtrl overrides held.

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 48 paired rows compared (callers and address-loaders through the map, ordered
calls), the CRemoteCtrl vtable slot by slot, 1 pointer loader. Differences looked at: 8 caller
sets and 4 call-order substitutions. All are callers added in the release (playPss calls
CInput::Tick, CGameMenu::HandlePad calls GetKeyReadThisFrame, hudTickScorePopup and new 0x28faa0
call SetButtonState and Flush, new 0x25a800 calls GetRemoteAiState), calls dropped (GetTwoButtons
from CSealCtrl::PostMortemPreTick and the two CHUD::StatusLine, Flush from
CZHudMissionCams::CleanupCamera), the double-precision `fabs` sequences that became `fabsf`
(CPad::Tick, Dilate, CRemoteCtrl::PreTick), and the unsure keyboard rows themselves.
Pairs wrong: 0.

What misled it:

- 0x43d808 and 0x43dcf0: the two library functions have the same callers as two prototype
  wrappers (GetKeyReadThisFrame), so call evidence paired them; for 0x43d808 the wrapper it chose
  was the wrong one of the four candidates, because GetInfo has the same caller as Read. The RPC
  function number (the `a1` of sceSifCallRpc) and the library's messages decide the role; the
  owner `libusbkb.a` is in its messages.

What cost the most time: telling the library from the old wrappers and finding its extent past
the map's last row. Suggestion:

- Treat a function whose strings name an SCE library (`libusbkb.a`, `sceUsbKb...`) as a provider
  and do not pair it with an authored prototype function by callers alone.
