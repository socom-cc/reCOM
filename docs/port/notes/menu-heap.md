# Menu heap margin (2026-11-15, socom-port-heap): why the menus' 2.6 MB buffer was fragile

Scratch `build/port/boot-heap/` (untracked: NOTES.md, run logs, map dumps `*-NN.txt`, `sweep/results.txt`).
Started at HEAD d035c977, final runs on b800665b. Changed files: `src/gamez/zFTS/fts_mission.cpp`,
`src/gamez/zVehicle/vehicle_main.cpp`, `src/gamez/zValve/zvalve.h`, `port/CMakeLists.txt`,
`port/compat/port_diag.c`, `port/test-hooks/state/` (`hook_heapmap.cpp` new, `hook_state.cpp`, `build.sh`),
`port/test-hooks/README.md`, this note.

Tool: the `state` round-trip hook with the new heap mapper (`HMAP=1 build.sh <build> pad_idle.txt
-DSOCOM_HOOK_HEAPMAP ...`). It records every block's allocation site and the hook's phase (state changes seen)
in a table in bss and walks newlib's heap chunk by chunk without allocating: the free chunks of 4 KB+, the
in-use runs between them with their top sites, single blocks (pins) listed one by one, the largest hole, the
top chunk and the room left below the heap end. The old `-DSOCOM_HOOK_MALLOC` figures are not comparable: its
probes (`largest_free` mallocs and frees up to 32 MB at every trace) and the hook's own `std::string` changed
the layout they measured; the mapper and the hook now make no heap blocks of their own.

## Summary
- The heap is not smaller than the original's. The port's image is 160 KB larger, but its stack is 384 KB
  smaller, so the port has about 230 KB more heap than the ELF (27.07 MB against 26.83 MB).
- The margin was fragmentation. On the way back to the menus the mission is freed (in use 8.57 MB, 14.5 MB
  free), but a handful of small blocks made during the mission and kept afterwards (pins, 32 bytes to 11 KB)
  cut the freed memory into holes of 2.2 to 2.9 MB. The menus then load a 2,581,264-byte archive and, last,
  the 2,598,384-byte `run/uizanim.zar` buffer, which needs a 2,598,400-byte hole. At HEAD the best hole left
  was 2,291,728: the buffer went above the break (brk 0x1c17000 -> 0x1e92000, room left 1.36 MB). Which
  hole survives depends on where a few dozen bytes land, so a small change of the boot allocations flips it
  (8 of 11 sweep points collapsed, 3 did not; the "healthy" HEAD figures of earlier notes were one of the
  lucky layouts, produced by the MALLOC hook's own allocations).
- Four pins were removed (two differences from the ELF, two port-only blocks). The freed mission memory now
  stays one hole of 8.8 MB, the buffer fits a hole at every return in all 11 sweep points, and the break no
  longer moves. `theValveSaveManager` is written.

## 1. Heap budget

| | port (default build, final tree) | reference ELF |
| --- | --- | --- |
| image | 0x100000..0x60f21c (5,304,860 B) | 0x100000..0x5e7f04 (5,144,324 B; `_end`, `heap` section) |
| loaded part | 3,522,696 B (.text 3,218,160, .vutext 19,168, .rodata 170,513, .eh_frame 86,204, .data 17,060) | 3,626,496 B (one `main` section) |
| bss | 1,782,036 B | 1,517,824 B |
| stack | 128 KB at the top (ps2sdk linkfile `_stack_size` 0x20000, `_stack` -1) | 512 KB at the top (crt0 0x140150: `SetupThread(gp, -1, 0x80000, ...)`) |
| heap | `_end`..0x1fdf000 (`EndOfHeap`) = 27,065,828 B | `SetupHeap(0x5e7f04, -1)` (0x140188) .. about 0x1f7f000 = 26.83 MB (`zsys_MemoryReport` 0x2f4490 assumes 0x1f7e000) |
| allocator | newlib 4.6.0 mallocr (dlmalloc 2.6), trim threshold 128 KB, top pad 0, page 4 KB | newlib mallocr (`_malloc_r` 0x3e21a0, `malloc_extend_top` 0x3e1f48), trim threshold 0x20000 (0x43c398), top pad 0 |

The lead that the port's image is about 1.1 MB larger does not hold: the break values near 0x67e000..0x702000
in run logs come after the boot allocations (render pipe 224 KB, the two operator-new pools 819 KB, ...).

What the port's image holds (link map of a plain build, bytes): game library 3,802,430 (code 2,410,816,
bss 1,333,679); libstdc++ 753,426 (code 631,032, unwind tables 91,958); `port/compat` 261,083 (rodata 92,881,
bss 129,242: MPEG carry and scratchpad buffers); newlib libc 198,782; ps2sdk and libgcc about 230 KB.
Larger than it has to be (measured, not changed):
- `mfifoBase` (zsys_spr.cpp, 256 KB, `aligned(0x40000)` as the DMA ring requires) sits in the middle of .bss,
  so 262,116 bytes of padding are lost before it (0x58001c..0x5c0000). The ELF has it at 0x100000, before the
  code, with no gap.
- The build type is Release, so `-O3` follows `-O2`: an `-O2` link of the same tree has 371,724 bytes less
  code (.text 3,134,227 against 3,505,951).
- Thread-safe statics: 51 guard calls (`__cxa_guard_acquire`) in the game; now 4 (libstdc++'s own).
- `-fsanitize=return` and the trace strings were not measured separately; there are no large trace buffers.

## 2. The heap at a return (HEAD, map `m2-09.txt`: the mission freed, before the menus' first archive)

In use 8,572,000 B, free 14,528,400 B. From the bottom:
- 0x70f218..0xf02708, 8.3 MB in 12,372 blocks, boot: the 3.58 MB boot archive, reader files 1.45 MB, the
  operator-new pools 819 KB (main.cpp:76), render pipe 224 KB, recognition data 456 KB, the TTY font packet
  160 KB, two CSTables 64 KB, ... Class (a).
- Free 1,607,376 at 0xf02708, then small runs and holes of 86..341 KB, split by 32..48-byte blocks made in
  the first menu session (the `CTexManager` handle and palette vectors' buffers, a string) and the debrief's
  own reads (2..3 KB, freed with the debrief). Class (b), harmless (all holes there are under 2 MB anyway).
- 0x113e768: 2,080 B in 54 blocks, `CCharacterType::InitMultiplayerMessages` strings (the character type
  cache: the ELF keeps the types too, `Release` 0x2485f0 never deletes). Class (b).
- Free 2,261,376 | **32 B `_Balloc` (newlib Bigint), made at the mission load** | free 325,232.
- 0x13b6798 75 KB character types (`CCharacterType::Open`), 0x13db358 153 KB `ZuiInit` tables: (b).
- Free 688,656 | 144 B `CCharacterType::CreateLODs` (type cache, (b)) | free **2,910,544** |
  **144 B `CMission::Open`: `m_objanchor_vec.reserve(16)`** | free 2,171,136 |
  **10,992 B `vector<CVehicleRdrEntry>` (41 entries, `CVehicleRdr::Load`)** | free 2,291,728 |
  **32 B pthread mutex (`__cxa_guard_acquire`, first lock at the mission load)** | free 292,368 |
  **144 B + 32 B `_Balloc` (the Bigint free list and a Bigint)** | free 47,584 + 1,114,800 |
  272 B `vector<CDynTexList*>` (the texture manager's buffer list, grown during the mission load) | top 504,
  then 3.95 MB room (default build).

Classes of the pins in bold: the objective-anchor and vehicle vectors are (b) port leaks (the ELF frees both,
see 4.); the mutex and the Bigints are (c) port-only (MW guards local statics with a flag; the first float a
`socom_port_trace` line prints makes newlib's Bigint cache, which is never freed). The 272 B vector is (b),
grown in the ELF too; it bounds the top chunk (the break stays at its end). Without the five bold pins the
region 0x14a8ba8..0x1d16ce8 is one 8.8 MB hole.

Then the menus load (CMenuState::Init, the core state's UnInit has just freed the mission): a 2,581,280 B
archive (best fit: the 2.91 MB hole), readerc 498 KB / 336 KB, the ui world's keys 791 KB and archive 1.21 MB,
grid buffers, textures, then the 2,598,400 B `uizanim.zar` buffer: largest hole left 2,291,728 (m1 map
`m1-before_memalign_2598384_zar_main_cpp_394_8.txt`), so it goes on top.

## 3. Why 48 bytes matter: the sweep

A test-only boot allocation in the hook (`-DSOCOM_HMAP_XSIZE/_XCOUNT`, made right after the `CSaveModule
("CMission")` constructor where the ELF builds `theValveSaveManager`, or with `_XAT=0` before the global
constructors), one boot to the first return per point, builds with no site table (`-DSOCOM_HMAP_NOTAG`, the
default build's heap end). "Best hole" is the largest hole when the 2,598,384 B buffer is asked for; "on top"
means it did not fit and the break grew.

| extra boot allocation | HEAD: best hole | HEAD: buffer | HEAD: largest at return 1 | fixed: best hole | fixed: largest at return 1 |
| --- | --- | --- | --- | --- | --- |
| none | 2,291,728 | on top (brk 0x1e92000) | 2,291,728 (room 1,363,968) | 6,782,608 | 3,965,448 |
| 2 x 24 B (the valve manager's two blocks) | 2,291,472 | on top | 2,291,472 | 7,340,176 | 3,965,384 |
| 2 x 24 B before the constructors | 2,291,472 | on top | 2,291,472 | 7,340,176 | 3,965,384 |
| 1 x 16 B | 4,541,408 | hole | 3,965,400 | 7,574,944 | 3,965,416 |
| 1 x 200 B | 2,289,104 | on top | 2,289,104 | 3,119,904 | 3,965,240 |
| 1 x 1000 B | 2,289,136 | on top | 2,289,136 | 6,676,032 | 3,964,440 |
| 1 x 4000 B | 4,203,776 | hole | (run ended before) | 6,655,168 | 3,961,432 |
| 1 x 64 KB | 4,162,400 | hole | 3,899,880 | 6,675,744 | 3,899,896 |
| 24 x 32 B | 2,291,728 | on top | 2,291,728 | 6,782,608 | 3,964,296 |
| 12 x 512 B | 2,291,472 | on top | 2,291,472 | 7,340,176 | 3,959,112 |
| 4 x 16 KB | 2,291,472 | on top | 2,291,472 | 7,340,176 | 3,899,848 |

Mechanism: the buffer needs one hole of 2,598,400 B in memory the mission has just freed. At HEAD the pins
above leave holes of 2.17, 2.29 and 2.91 MB; the menus' first 2.58 MB archive takes the 2.91 MB one, and
whether anything of 2.6 MB is left depends on which hole each of the menus' other blocks (the ui world, the
reader archives) is put in, which a shift of a few bytes at boot changes: the current layout was not lucky,
the collapsed one is the typical one (8 of 11). When the buffer goes on top the break rises by 2.6 MB and the
room left below the heap end falls from 3.96 to 1.36 MB for the rest of the session; the next mission load
then has to fit in what is left. With the fixes no point puts the buffer on top and the smallest best hole is
3.12 MB.

## 4. What the original does

- Same allocator (newlib mallocr, same trim threshold and top pad) and the same request: `CZAR::ReadDirectory`
  0x1d87b0 asks `_memalign__FUiUiPCci(64, size, "zar_main.cpp", 394)` for the data when `m_memalign` is set,
  as the port does; no compaction, no fixed buffer, no separate arena.
- Same order: one state command per frame (`CGame::Tick`), so the debrief's Pop runs `CExitState::UnInit`
  first, then the core-to-menu switch runs `CCoreState::UnInit` (the mission close) and then
  `CMenuState::Init` 0x3793e0, whose calls are in the port's order (readerc.zar, `LoadWorld("ui")`, uisk and
  font libraries, the menu, the two relocator buffers, uisounds, sounds, `OpenZAR("run/uizanim.zar")`, the
  menu's Init).
- Differences found, both frees the port lacked: `CMission::Close` 0x1f7180 ends with three swaps with empty
  temporaries (+0x80 extraction anchors, +0x8c nav points, +0x98 objective anchors after `clear`,
  0x1f7670..0x1f7698); the port had the first two. `CVehicleRdr::Close` 0x1a3810 clears and then swaps the
  vector with an empty `vector_deleter` that is destroyed; the port only cleared. `ReOpen_Unload1` 0x1f7c60
  has no swap (as the port). `CCharacterType::Release` 0x2485f0 keeps the type (as the port).
- `CGameMenu::Clear` was not compared call by call (no pin traced back to the menus).
- Running the original from the disc through the same round trip was not practical: the batch boots have no
  pad driver or hook for the original ELF and no scripted memory dump, so its in-use and largest block were
  not measured.

## Fixes

| fix | kind | what it frees / moves |
| --- | --- | --- |
| `CMission::Close`: `m_objanchor_vec.clear()` and swap with an empty vector (0x1f7670) | ELF difference | the 144 B buffer between the 2.91 and 2.17 MB holes |
| `CVehicleRdr::Close`: `clear()` and swap with an empty vector (0x1a3810) | ELF difference | the 10,992 B buffer between the 2.17 and 2.29 MB holes |
| `-fno-threadsafe-statics` (port/CMakeLists.txt) | port-only | the 32 B guard mutex made at the mission load; 47 guard calls fewer; MW's statics have no lock either |
| dtoa warm-up in `socom_port_ctors_begin` (port/compat/port_diag.c) | port-only | newlib's Bigint free list and Bigints (144 + 32 + 32 B) are made at boot, with the boot blocks |

In use at a return: 18,666,896 -> 18,655,728 B (-11,168). Largest hole when the mission has been freed:
2,910,544 -> 8,838,928 B.

`theValveSaveManager` is now the ELF's object: `CValveSaveManager("CValveSaveManager", theMemCard.m_config)`
after `theUIVarManager` (inline in `__sinit_fts_mission.cpp` 0x46ac0c; an inline constructor in `zvalve.h`),
and `~CValveSaveManager` 0x1fbdc0 is the compiler-style one (vtable, `~CSaveModule`), defined in
fts_mission.cpp. With the memory-card layer off it changes nothing in play; its two blocks are the
"2 x 24 B" sweep point.

## Options not implemented (port deviations or build-policy changes: the user's decision)

- Place `mfifoBase` at the start of the image as the ELF does (a port linker script, or a section attribute in
  zsys_spr.cpp behind `SOCOM_PORT`): +262,116 B of heap.
- Build with `-O2` instead of Release's `-O3`: +371,724 B of heap; the frame time and any code that behaves
  differently under the other optimiser are unmeasured.
- Shrink the texture manager's grown buffer list after a mission (the 272 B block that bounds the top): the
  top chunk and the hole below it would join (2.9 + 3.96 MB). A deviation (the ELF keeps it).
- Keep the menu archive buffer allocated across a mission, or carve the archive buffers from a separate
  arena at the top of the heap: removes the dependence on holes altogether, costs 2.6 MB during missions
  (in use at a mission start is 22.9 MB of 27.07) or a second allocator.
- libstdc++ is 753 KB (92 KB unwind tables although the game is built without exceptions); section garbage
  collection or a smaller C++ library would give some back.

## Run-to-run spread (one ELF, several boots)

- The first round trip is reproducible: three boots of the HEAD baseline gave the same best hole (2,291,728)
  and in use (18,666,896) at return 1, three boots of the fixed tree the same 6,782,608 / 18,655,728.
- Later rounds are not. The types worker's two boots of one ELF (`build/port/boot-types/trt.log`,
  `trt2.log`, identical binaries) were byte-equal at return 1 (collapsed, brk 0x1e92000) but parted in
  mission 2: the hook saw the load finish one or two pad reads apart (mission 2 start at read 1795 / 1794,
  exit at 2753 / 2751), so its presses (ABORT, the fall, the debrief) landed on other game frames and the
  mission allocated differently. In `trt` the menus' first 2,581,264 B archive found no hole at return 2 either
  and went on top (brk 0x1c17000 -> 0x1e8e000); the 2,598,384 B buffer then had neither a hole nor room and
  `_memalign` asserted (198.5 s). `trt2` passed eight returns, every one collapsed.
- Sources of the variation: the mission load runs on a thread (`CCoreState::Load`, `load_thread_stack`) while
  the main loop draws the loading screen, so how many frames the load takes, and the order of the two
  threads' allocations, follow the CD / IOP read completion; the hook and a fake pad count frames, so they
  act at other game moments from then on. The game also seeds `rand` from the real-time clock
  (`COurGame::StartEngine` 0x140604 in the ELF, `sceCdReadClock` -> `srand`, port main.cpp), so AI and effects
  differ from boot to boot; at the first return this did not show in the heap (the hook aborts mission 1
  early), it can in longer play.
- Fixed tree, one boot, eight returns (`v8.log`): the best hole for the 2,598,384 B buffer was 6,654,720 to
  6,656,000 B, the largest hole left at the return 2,671,056 to 2,698,304 B (it moves by up to 27 KB from
  round to round), the largest block 3,965,400 B (the top) at every return.
  A second boot of the same ELF (`v8b.log`): best hole 6,654,976 to 6,655,232 B, holes at the returns
  2,672,480 to 2,694,768 B, largest block 3,965,400 B and in use 18,655,872 B at every return. Over the 16
  returns of the two boots the buffer's best hole never fell below 6.65 MB (2.5 times the request), so the
  round-to-round and boot-to-boot variation (tens of KB) is far inside the margin. At HEAD the same variation
  decides between "buffer in a hole" and "buffer on top", and between surviving and asserting at the next
  return.

## Results (final tree: HEAD b800665b + the files above)

- 8-return round trip (`heap-v8`, state hook, `-DSOCOM_HMAP_NOTAG -DSOCOM_HOOK_MISSIONS=8`, 740 s, focus
  kept): in use 18,655,776 B at return 1 and 18,655,872 B at returns 2-8, free 4,444,544 B, largest block
  3,965,400 B at every return (holes 2.67-2.70 MB), the menu buffer in a hole every time, the break at
  0x1c17000 throughout (was 0x1e92000 at HEAD), no STOP or assert; idles in the menus to 740 s.
- m8 (`heap-vm8`, the same hook with one mission and no ABORT: intro movie skipped with CROSS, briefing
  cameras with X): 179 s in the mission, no STOP, in use 22.96-23.06 MB, steady at 23,055,564-23,057,052 B
  from 120 s on, break 0x1d02000 throughout.
- Options front end (`heap-vfe`, fake pad `pad_fe.txt` of the zUI work): main menu -> OPTIONS -> audio ->
  video -> controller selection -> presets -> main menu -> attract, no STOP.
- Default build (`heap-vdef`, no hook, no fake pad): main menu at 15.7 s, attract at 44 s.
- Image growth the margin tolerates: the highest break of all these runs is 0x1d5d000 (the intro movie at a
  mission start); the heap ends at 0x1fdf000, so about 2.6 MB (2,629,632 B) of image growth still leaves the
  mission start and every return working. The holes the menu buffer goes into are relative to the heap start
  and do not shrink when the image grows; the room above the break does, one for one (3.96 MB at a return).
  The heap mapper's own 0.8-1.0 MB of bss (tagged builds) ran two rounds with the same results.

## Hook

`port/test-hooks/state/hook_heapmap.cpp` (new) with `hook_state.cpp` (map points, the hook's phase, the dialog
name in a fixed buffer instead of a `std::string`) and `build.sh` (`HMAP=1`); switches in the hook's header
comment and in `port/test-hooks/README.md`. The scratch sweep scripts are in `build/port/boot-heap/`.
