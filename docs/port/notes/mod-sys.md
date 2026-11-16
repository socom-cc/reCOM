# mod-sys notes (2026-11-14, socom-port-mod-sys): the small system and utility modules

Scratch `build/port/boot-mod-sys/` (untracked: NOTES.md, mine.txt, the edit definitions under `defs/` (rep.py),
asm dumps, pad_fe.txt). Changed files: `mine.txt` (the ten modules in place; outside them the small in-place edits
listed under each module, all free at HEAD). Test hook: `port/test-hooks/memcard/` (README row added).

## Result
- `survey.py`, empty fences before -> after: zConsole 34 -> 0, zUtil 21 (+4 placeholder returns) -> 0, Apps/FTS/game
  8 -> 1 (`OrdersMenu::HandleRecoCmd`), zReader 8 -> 0, zTwoD 10 -> 0, zInput 15 -> 0, zSave 10 -> 0, zSystem 9 -> 0,
  zVideo 4 -> 0, zGame 4 -> 0. Placeholder bodies written too (CTTY `Print` / `Render`, `CVideo::MaxFrameRate`,
  `zVid_Assert`, `C2D::GetZAnimCmdType`, `C2DFont` / `C2DTriFan::GetAssetLibs`, `CSaveManager::RegisterModule`,
  `CRemoteCtrl::Tick`, `InitKeyreadStuff`, the CMemCardIO returns, the zAnim memory-card commands).
- Left (and why): `OrdersMenu::HandleRecoCmd` 0x176e60 and the `port: not written` parts of `recoUnInit` / `recoInit2`
  (voice recognition: the gsapi provider is offline, recoInited never becomes 1, nothing reaches them);
  `CRemoteCtrl::PreTick` 0x2ce310 (network remote seal: needs the zSeal CSealCtrl network members at +0x1fc..+0x220);
  the zVid_Swap frame limiter (see zVideo).
- Runs: see "Runs" at the end.

## zConsole (all 34)
The DECI2 host console. `CConsole::m_console` is a static `CConsole("default console")` (`__sinit_con_ps2.cpp`) that
`CGame::Tick` ticks every frame. Written from the ELF: `CConsole` ctor 0x1ed170 / dtor 0x1ed060, `Initalize`
0x1edd30, `Tick` 0x1edbf0, `CheckEvent` 0x1eddc0, `Send` 0x1edaf0, `Disconnect` 0x1edcd0, `RecvPacket` 0x1ecba0
(ACK of FLAG_WANTACK packets, ACKs retire the waiting packet, handler by type, else by the message's first string,
then the type-4 handler, an error packet back when a handler has no callback), `OnConnect` 0x1ec8a0 (handlers msg /
ping / error), `FindHandler`, both `Debug`, `CHandler`, `CAckList`, `CPacket` (24-byte DECI2 header: length, 0xe000,
'E' -> 'H', id, flags, type, argc) and `CPacketMsg` (strings after the header). Layouts in zsys.h / zconsole.h from the
code (no DWARF; names invented).
- Nothing in the offline game opens it: `Initalize` sets the socket to -1 and the ELF never calls `sceDeci2Open` for
  it (its only caller is `sceTtyInit`) nor `OnConnect` (vtable only). Each frame `Tick` runs `CheckEvent` (no event)
  and reads nothing. It is a host-link channel (a DECI2 debugger on a development kit), not a pad console: no pad or
  keyboard input reaches it.
- ELF quirks kept: `Debug` passes the formatted text to printf as its format; a failed error-packet send leaves the
  packet allocated; `RecvPacket`'s `level` static is set and never read.
- Port deviations: `m_console` is a real `CConsole` (was an 80-byte array); inline protected ctors for the packets
  `OnRecvPacket` builds inline; `extern "C"` around ps2sdk's `deci2.h`.

## zUtil
- Memory card (util_memcard.cpp, all): `CMemCardIO` (a CIO on a card file: Open 0x306ad0 with the CIO mode bits as
  sceMc flags, delete-first for 8|0x10, size from sceMcGetDir; Close, fread, fwrite, fseek, ftell, fflush, IsOpen,
  GetSize) and `CMemCard : CMemCardIO` (theMemCard, 40 bytes: game / options save managers at +0x18 / +0x1c, card port
  and slot +0x20 / +0x24): ctor / dtor, Init (modules unless the IOP boot loaded them, sceMcInit, the format asked
  twice; ELF quirk: on theMemCard's card whatever `this` is), Uninit, Load/SaveGame (version 2), Load/SaveConfig
  (version 1, MEMCARD_ERROR event on failure), IsInserted / IsFormatted (two tries), Format, GetFreeSpace, Exists,
  mkdir, chdir, CreateIconFiles (icon.sys with the title "SOCOM:2002 Public Beta" in full-width Shift-JIS, the LIST /
  COPYING / DELETING icons copied from the disc; ELF quirk: returns false always), Ascii2Sjis.
- `COutput` dtor 0x304320, `zUtilUninit` 0x3044e0, `CSTable::Clear` 0x3060f0.
- Outside the module (in place): `zFTS/fts_mission.cpp` (theMemCard a `CMemCard`), `zUI/zui.h` (CUIVarManager registers
  with `theMemCard.m_config`, as `__sinit_fts_mission.cpp`), `zAnim/zanim_menu.cpp` (the memory-card UI commands,
  ListSavedGames, Load / SaveSavedGame and Load / SaveConfig call theMemCard), `zArchive/zar_main.cpp`
  (`CZAR::CreateKey` 0x1d8f70, a TODO before: the save's keys).

### The memory-card boundary
- SDK side in `port/compat/libmc.c` + `include/libmc.h` (chains to ps2sdk's libmc.h): the game's `sceMc*` calls map
  one to one onto ps2sdk's libmc (`mc*`, same arguments; `-lmc` in port/CMakeLists.txt). Chosen over a stand-in
  because ps2sdk's libmc talks to the same MCSERV RPC server the game loads. `sceMcInit` tries the newer server type
  (MC_TYPE_XMC) then the BIOS one; `sceMcSync` waits and accepts NULL out-pointers; `sceMcGetInfo` sends unwanted
  answers to scratch words.
- Result (port/test-hooks/memcard, runs sysmc5 / sysmc6): mcInit binds (either type), GetInfo sees the card (type 2,
  sync result 0 on port 0), but the free-space and format answers come back 0, so `IsFormatted` says no and nothing is
  saved. The IOP has an mcman 1.01 from the IOP image as well as the disc's 2.06. Missing: matching the disc MCSERV's
  info reply in compat (or loading the BIOS card modules instead) - then the hook's SaveConfig / LoadConfig round trip
  (a PERSISTENT UI variable restored) can run. Also: PCSX2 opens each card file in one instance only; with other
  emulators running the card is "in use" (GetInfo -11, no card), so card runs need the emulator to themselves.
- Game side above it is complete: CSaveManager (zSave), CRdrFile::Pack / Insert (zReader), CZAR writes (zArchive),
  the UI-variable Serialize / UnSerialize (zUI, written earlier).

## Apps/FTS/game
- `CBeachBall::Uninit` 0x305e40 (+ `m_init` 0x4765b0, no stage-4 owner).
- reco.cpp: `recoGrabMemory` 0x3369e0 (zSysInit: the language and the three contexts' files, ~470 KB, read at boot as
  the ELF does), `recoSetupLanguage`, `recoEnableWord`, `recoDisableAllWords`, `recoGetFirstWordID`,
  `recoGetNextWordID`, `recoGetNumHeads`, `cbrecoNotify` (energy ring, maximum, the meter's heads), `cbrecoResult`.
  The provider calls go to `port/compat/gsapi_offline.c`, which now answers each with an error.
- Port deviation: `cbrecoResult` stores at most three word ids (the ELF writes past its three-word array).

## zReader
`CRdrFile::Pack()` 0x23c7a0 (one buffer: string bytes, node offset, strings, 16-aligned nodes; the parsed arrays
freed), `Pack(_zrdr *, _zrdr *, int)` 0x23cce0, `_fixup` 0x23cb50, `Insert` 0x23c130, `zrdr_countarray` 0x23ca30 (had
no fence), `zrdr_pack` 0x241530, `zrdr_relocate` 0x2416d0, `zrdr_flat_nexttag` 0x23dd80, `~_zrdr` (nothing of its own).
The ELF unrolls one recursion level in Pack / countarray / relocate; written recursive (same result).

## zTwoD
`Draw2DLine` 0x2fff40 (gouraud GS line in window pixels, the HUD dev lines and auto-aim reticle), `Draw3DLine`
0x3001b0 (through the world camera's world-to-screen matrix, `sceVu0RotTransPers` mode 0 written out: x y z w all
12.4, z + zOffset), both `clip3DLine` (0x2ffd00 one plane, 0x2ffc20 six planes), `C2DTriFan` ctor / dtor / Draw and
GetAssetLibs (members `m_polys` +0x1c, `m_texture` +0x28 from the code), `C2DFont::GetAssetLibs` 0x2ff490,
`C2D::GetZAnimCmdType` 0x174b10 (GetUICommandType(NULL): 0x95), `~C2D` / `~C2DLine` / `C2DString::Update` (empty in
the ELF). ELF quirk kept: the GetAssetLibs add a library only when the search pointer is NULL (never).

## zInput
`CCheat::Update` / `TickAll` (button sequences pulsing a valve; nothing in the ELF adds a cheat, so the list stays
empty), `CKeyboard`, the USB keyboard reader (`GetKeyReadThisFrame`, `GetNewKeyPress`, the `sceUsbKeybd*` RPC
wrappers), `CRemoteCtrl` AllowCommand / OnCommand / GetRemoteAiState / GetRemoteAiFollowMaster / PostMortemPreTick
(members +0x240 / +0x244) / PostTick / Tick. `KeyInput`, `CCheat`, `CCheatList` layouts from the code.
- Port deviations: USBKB.IRX is offline in the port, so `sceUsbKeybdInit` does not bind (the ELF retries for ever:
  `socom_port_module_offline`, compat sce_iop.c) and the requests answer "no keyboard"; `GetNewKeyPress` does not read
  the byte before `lastKeys` when no key was held; `sceSifClientData` from compat `sifrpc.h`.

## zSave
`CSaveManager` Save 0x3f7710 / Load 0x3f72f0 / GetHeader / SaveRdr / RegisterModule / dtor, `RemoveExtension`,
`CSaveModule` dtor / SaveRdr / UnSerialize (empty). `CSaveHeader` (268 bytes: size, version, flags, description);
`CSaveModule`'s virtuals as `__vt__11CSaveModule` (Serialize pure, both UnSerialize, TestFlags); `g_KeyToilet` a
vector of the keys a save deletes after closing. ELF quirks kept: SaveRdr returns false; the module list is sorted by
pointer before a save. Port: m_pZar cleared after a save (the ELF leaves the dead stack archive).

## zSystem
`zSysLoadIRX` / `zSysUnloadIRX`, `zsys_MemoryReport` (ps2sdk's `_ftext` / `_fdata` / `_end` for the ELF's section
symbols), `CSched_Manager` ctor, the TRC power-off set (`TRC_PreparePowerOff` thread + semaphore + CD power-off
callback, `_UnPreparePowerOff`, the thread, the HDD / network-adaptor shutdown). Compat (sce_iop.c, sifdev.h):
`sceSifStopModule` / `sceSifUnloadModule` (ps2sdk Sif*), `sceDevctl` (no such devices: success), `sceCdPOffCallback`
(declared by ps2sdk, not implemented: not registered, the power-off thread waits for ever).

## zVideo
CTTY (40 x 78 lines; ctor, dtor, `Print` (was recursing into itself), `Render`), `SetDynamicLOD` 0x308070 (below
40 / 38 / 36 / 34 fps the lodLevel valve and the particle spawn / age factors step), `zVid_Uninit`,
`CVideo::MaxFrameRate` 0x308f20 (returns the previous cap; s32), `m_maxFrameRate` / `m_defaultFrameRate` 30 (ELF),
`zVid_Assert` (terminal line 12, terminal on). Compat `port/compat/libdev.c`: `sceDevFont` stand-in (the text goes to
the log, an empty DMA packet is sent).
- Not done: the zVid_Swap frame limiter (waits whole fields while the frame is under 1 / m_maxFrameRate). With it the
  missions run at the ELF's 30 fps (CCoreState sets the default cap 30): every port test and pad script is timed at
  60 fps, so it is left for a coordinated change. `zVid_Assert`'s picframecode screen (no copy of the GS packet).
- 2026-11-16: the limiter is written (0x307c24..0x307cac) and the pad scripts and hooks are timed in fields:
  [frame-limiter.md](frame-limiter.md).

## zGame
`CGame::StopEngine` 0x20e5d0 (StartEngine's systems shut down, incl. `CRipple` / `CTextureFX::Uninit`; ZAnim closed
twice as the ELF), `StopPlay`, `NetTickThreadEntry` (port: `CZNetwork::zNetTick` is void, so the sleep stays 1/20 s),
`~CGame`.

## Runs (tree = HEAD + mine.txt)
- sysm8 (state hook, one mission, intro CROSS, cameras X): in the mission 55..261 s, no STOP, in use 22.228 MB at
  80 s, 22.265 MB from 120 s to the end.
- sysmc1..6: memory-card hook (above).
- sysfe (fake pad: main menu -> OPTIONS -> audio, video, controller, presets -> main menu -> attract, 240 s): no STOP,
  no "not written" spec.
- sysrt (state hook, `-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=8`, 740 s): eight missions and eight returns, no STOP,
  no failed allocation but zsys_FullAllocAndFree's own probes; in use 17,836,436 B at every return (flat) and
  17,346,4xx B once dlgMenu is up. That is about 627 KB above HEAD's 17,210 KB: the ELF's boot-time allocations now
  made too, recoGrabMemory (~470 KB of reco data) and the CTTY font packet (0x27000 = 156 KB).
- sysdef (`default.sh`, no hooks): main menu at 16.4 s, no STOP.
