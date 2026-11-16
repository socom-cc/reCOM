# The frame limiter, the pad time base, the heap options (2026-11-16, socom-port-limiter)

Scratch `build/port/boot-limiter/` (untracked: NOTES.md, run logs, the measurement hook `hook_lim.cpp`, the
converters under `tools/`, the edit files). Changed files: `mine.txt` (below), and `edits/memcard.txt` for
`port/test-hooks/memcard/hook_memcard.cpp` (another worker's).

## 1. The frame limiter (`zVid_Swap`, ELF 0x307bc0)

Written from the disassembly (0x307bf0..0x307cac) in `src/gamez/zVideo/zvid_init.cpp`:

- **What it measures.** `zVid.procTime = T0_COUNT * zSys.timerScale`: the H-blanks counted by timer 0
  (`T0_MODE` 0x83, CLKS H-blank, set by `zSysInit`) since the last swap reset it, after
  `CTTY::Render`, `sceGsSyncPath` and `CMPEG::IdleTick`. The ELF converts the count as an unsigned word.
- **What it waits on.** Unless `CVideo::m_maxFrameRate` (.sdata 0x4753dc) is -1: `t = procTime`; while
  `t + 1/60 < 1 / (f32)m_maxFrameRate` it calls `sceGsSyncV(0)` (one vertical blank) and adds 1/60 to `t`
  (0x3c888889, `0.0166666676f`). T0 is not read again: each wait counts as a whole field. The cap is
  reloaded every round. `zVid.procTime` keeps the time before the waits; `SetDynamicLOD(1 / procTime)`
  and the HUD's rate readout use it.
- **The frame.** The swap's own `sceGsSyncV` follows, then T0 is read into `frameTime` (the game's dT,
  `CGame::Tick(zVid.frameTime)`) and reset. At the cap 30 a frame that ends before the next field waits
  for it, and the swap ends on the field after: 33.3 ms. A frame over 16.7 ms gets no wait; one over
  33.3 ms ends on the next field after it (50 ms ...). No catching up, no carried debt.
- **First frame, long frames.** `zVid_Sync0` (`CCoreState::Init`) waits for a field and resets T0, so a
  mission's first frame is measured from there. A long frame (a load, a hitch) only lengthens that frame;
  T0 is 16 bits (65,535 H-blanks = 4.2 s at 15,734 Hz), so a frame longer than that wraps and the limiter
  may wait up to one frame's worth of fields extra (ELF quirk, kept).
- **Who sets the cap** (`CVideo::MaxFrameRate` 0x308f20, 60 -> -1, returns the old cap): boot 30 (.sdata);
  `CCoreState::Init` 0x17d638 `m_defaultFrameRate` (30; the `-V` switch takes 60/30/20/15);
  `CCoreState::UnInit` 0x17ccb8 -1; `CCinematicState::Init` 0x17db60 -1 (old cap saved) and `UnInit`
  0x17d934 the saved cap. Nothing else (no lodLevel, no loading, no menu code). So the menus run at 30 fps
  until the first mission and uncapped (60) after it: an ELF quirk, kept. The loading screen runs under
  whatever cap is set.
- Also fixed: `zVid_Sync0`'s `1.0f / 60.0f` compiled to 0x3c888888 (GCC r5900 folds toward zero); now
  `0.0166666676f`, read back as 0x3c888889 (as the limiter's constant).

Measured (`hook_lim.cpp`, a `zVid_Swap` wrap tracing every 60 fields; runs `m1`, `w1`, `w0` = the
same build with the limiter off through a test edit):

| where | frame time (limiter) | frame time (no limiter) | procTime |
| --- | --- | --- | --- |
| boot movies (dlgIntroCinematic, Zipper) | 33.3 ms | 33.3 ms | 30.5 ms (IdleTick to line 480: no extra field) |
| dlgMenu / briefing, before a mission | 33.3 ms | 16.7 ms | 0.5-1 ms |
| loading screen | 50.0 ms | 50.0 ms | 33.5 ms (the load state's own pace) |
| intro movie in m8 (cap -1) | 33.3 ms | 33.3 ms | 30.5 ms |
| m8 after the cameras | 33.3 ms (30 fps) | 16.7 ms | 5-15 ms |

Game speed: the same walk (left stick up for 300 fields from 2 s after the cameras, the fake pad's
`play+120:LY=0+300`) covered 230.65 units in 5.000 s of game time with the limiter and 231.58 in 5.000 s
without: the game is dT-based (`frameTime` from T0), so 30 fps changes the step, not the speed.

## 2. The pad time base (test builds only)

Pad scripts counted pad reads from boot. A read count meant different times when the boot movies came in
(386b31a3) and halves its rate under the limiter (CPad reads every other frame). Now:

- `port/compat/libpad.c` (fake pad only): a vertical-blank interrupt counter (`INTC_VBLANK_S`, installed
  at `scePadInit`) is the clock; the script is parsed once; terms are `<anchor>[.<k>]+<fields>:<what>`
  (fields after the k-th time the game reached an anchor) or the old `<read>:<what>`. Buttons and sticks
  take `+<fields>`; a term starts at the first read at or after its time and is seen by one read at least.
  Syntax in `port/test-hooks/README.md` ("Pad scripts").
- `port/test/fake_pad_anchors.cpp` (compiled with the fake pad only, `port/CMakeLists.txt`): polled at
  every read, it names the points: `boot`, `menu`, `brief`, any dialog (`dlgAlaskaCinematic`, ...),
  `load`, `core`, `movie`, `start` (first briefing-camera frame), `play` (cameras over, 2 s quiet: m8 has
  two sequences, 21 s and 13 s, with a gap), `debrief`. Reads only, no heap blocks.
- `port/tools/dev/hook_clock.h`: `hook_fields()`, `hook_ticks()` (1/30 s: the hooks' numbers were tuned
  in reads at 60 fps), `hook_step` / `hook_field_step` (ticks / fields since the last call, at most 4,
  so time with no reads - a load - does not count, as before), `hook_anchor`, `hook_set_anchor`.
- Hooks: `hook_skipcams.h`, `state`, `win` by hand; the others' per-read and per-frame code runs once
  per tick / field elapsed (loops around the old `g_reads++` / `frame++`); `lpc10` from the menu anchor;
  `camcmd`'s delay and `actions`' glass camera in fields; `memcard` as an edit file.
- Scripts: `common/pad_start.txt`, `win/pad_a1.txt` (START path by anchors), `common/pad_fe.txt` (each
  group timed from the dialog it acts in), the per-feature scripts converted: mission terms from `start`
  (old read - old mission start) x 2 fields, the movie skip `movie+80`, death scripts' second missions
  from `debrief`, `brief.2`, `movie.2`, `start.2`; the fire scripts from `play+120`.

Every pad-script hook was built (47 builds, all link) and booted once from the converted scripts
(`build/port/boot-limiter/h-*.log`, focus kept in every run). Reaches its target:

| hook (script) | result |
| --- | --- |
| actions (`pad_arm`) | yes: the armory's equipment buttons (EquipWeaponBtn) |
| actions (`pad_b2`) | yes: m8, the targets stepped with TRIANGLE, action polys traced |
| camcmd, hudmp, render (`pad_fire`), sp (`pad_fire`), znode, zreader-style state-hook runs | yes: two missions, the cameras skipped, their traces (CAMERA_PARAMS, HOOK RN / SP / ZN, hudmp menu ticks); the fire scripts fire from `play+120` |
| clone, vehicles (`common/pad_start`) | yes: the START path into the m8 load (old diagnostic stand-ins; no traces of their own) |
| combat (`pad_ev`) | yes: fire, rush, grenade, surrender and flee tests; the first run crashed at 182 s (R5900 jump to an unmapped page) long after the tests, the second ran clean |
| death (`pad_t1`, `t0`, `cal`, `g2`) | yes: fatal fall, debrief, TRIANGLE back (t0 / t1 to the menus, cal / g2 their presses after) |
| death (`pad_rt`, `rt1`, `rt2`, `rt3`) | yes: death, debrief, briefing again, second mission started and played (`start.2`, `play.2`) |
| events, states, leftovers, pickups (`pad_c2`, `pad_f2`), shapes, kit, fireteam, orders (`o1`-`o4`), tacmap (`t1`, `t2`), jump (`j1`, `j2`, `j3`, `j5`) | yes: m8 after the cameras, each hook's tests traced (heard / seen events, door / corpse / stun states, carry, pickup offers, census, kit steps, team orders, map, DI census) |
| teamhud, voicecams (`pad_v1`) | yes: mission, debrief, menus again |
| exit (`pad_b1`) | first run no: its pause came during the cameras and was ignored. The pause is now queued 2 s after the mission's cameras end (seen by the hook itself: a REPLAY restarts the mission without a load the anchors see): rerun yes, mission 1 ABORT -> debrief X (replay) -> mission 2 pause REPLAY -> mission 3 ABORT -> debrief -> menus |
| stance (`pad_s1`) | first run no: SELECT held three reads (12 fields at 30 fps) opened the map and the game paused; `hook_skipcams.h` now holds it 2 ticks: rerun yes (crouch, prone, stand, zoom) |
| lpc10, mpegbg, zui, znet (`state/pad_idle`) | yes: LPC self-test same 1; the movies and briefing; the list / dialogs |
| memcard | not booted (another worker's hook and card); its pad timing is `edits/memcard.txt` |

## 3. Heap

**`mfifoBase` at the start of the image (on, the ELF's layout).** The pinned ps2sdk linker script starts
`.text` at 0x100000 and leaves nothing before it, so `port/CMakeLists.txt` copies that script at configure
time (`<build>/socom_port.ld`) with one change: a `.mfifo` section at 0x100000 and `.text` right after it;
`zsys_spr.cpp` puts the ring there with `section(".mfifo")` behind `SOCOM_PORT`. Result (default builds,
HEAD d416f09d): `mfifoBase` 0x5c0000 -> **0x100000**, `_ftext` 0x100000 -> 0x140000 (the ELF's code also
starts at 0x140000), `_end` 0x60f21c -> 0x5a665c: **+428,992 B of heap** (the ring's 0x40000 alignment
padded more than the 262,116 B measured before, once the bss order around it is counted). At 7a469667
the default build ends at 0x5a7b5c.

**Options (off by default, `port/CMakeLists.txt`, each a port deviation):**
- `SOCOM_PORT_HEAP_KEEP_MENU_ZAR`: the 2,598,384 B block that goes above the break is not
  `run/uizanim.zar` (1,214,352 B, as `menu-heap.md` assumed) but the briefing dialog's asset library,
  read in `CGameMenu::Init` (both through `CZAR::ReadDirectory`, zar_main.cpp:394). `st_menu.cpp` notes the
  largest such request while the menus load, takes that size again at the end of `CMenuState::UnInit`
  and holds it across the mission; `zar_main.cpp` gives it back just before the request of that exact
  size (`socom_port_menu_zar_request`), so the buffer always gets that hole. Without such a request the
  block is freed at the end of the menus' Init.
- `SOCOM_PORT_HEAP_SHRINK_TEXLIST`: after the mission's texture buffers are destroyed
  (`CCoreState` unload, st_core.cpp), the texture manager's buffer list is replaced by a tight copy.

Round trip, state hook (`-DSOCOM_HOOK_MALLOC -DSOCOM_HOOK_MISSIONS=4`), in use / largest free block
(the probe counts room above the break):

| build | main menu (first) | return 1 | return 2 | return 3 | return 4 |
| --- | --- | --- | --- | --- | --- |
| before (ring in .bss, `hv-old`) | 18,158,652 / 8,863,744 | 18,657,260 / 3,956,736 | 18,657,260 / 3,956,736 | 18,657,260 / 3,973,120 | 18,657,260 / 3,956,736 |
| default (ring at 0x100000; gate run) | 18,158,652 / 9,248,768 | 18,657,260 / 4,341,760 | 18,657,260 / 4,341,760 | 18,657,260 / 4,341,760 | 18,657,260 / 2,584,576 (buffer above the break, brk 0x1e35000) |
| + KEEP_MENU_ZAR (`hv-keep2`) | 18,158,652 / 9,248,768 | 18,657,260 / 6,508,544 | 18,657,260 / 2,576,384 | 18,657,260 / 3,448,832 | 18,657,260 / 6,369,280 |
| + SHRINK_TEXLIST (`hv-shrink`) | 18,158,652 / 9,248,768 | 18,657,132 / 8,470,528 | 18,657,132 / 8,470,528 | 18,657,132 / 8,470,528 | 18,657,132 / 8,470,528 |

- Default: the bad return still comes now and then (here return 4), as the original's own behaviour;
  the room left when it does is ~385 KB larger than before.
- KEEP_MENU_ZAR: the kept place was given back at every return (`MENU: kept archive buffer place
  (2598384 B) given back`), so that buffer never went above the break; but the missions, with 2.6 MB less
  heap, grew the break to 0x1e34000 (before 0x1ca4000), and the other blocks' holes vary (largest 2.6-6.5
  MB). All four missions loaded and ran; no request failed but `zsys_FullAllocAndFree`'s own probes.
- SHRINK_TEXLIST: the list's 272 B block no longer bounds the top, so the freed mission memory and the top
  chunk join and newlib trims the heap: brk 0x17cb000 at every return (was 0x1c18000), largest 8.47 MB.
- Unwind tables: not done (see Files).

## Found on the way: the power-off thread's stack

With the ring out of .bss every later object moved, and the m8 mission crashed at its first frame
(`Jump to unaligned address (PC 0x1)`, or a trap in `TRC_PowerOffThread_Aux`). Cause: the power-off
thread's stack `g_stack` (zsys_trc.cpp, 8 KB in .bss) had no alignment; the EE kernel saves thread
contexts with `sq`, so a stack not on 16 bytes breaks the thread. It sat at 0x5a0de8 / 0x59ebe8 in the
crashing builds and on 16-byte addresses in every build that worked (the old layout, a build with a
428,992-byte pad, a build with one more trace). Fixed: `aligned(16)` behind `SOCOM_PORT`, as
`load_thread_stack` already had. `net_init_thread_stack` (zNetMedius.cpp, online only) has the same
unaligned declaration (0x557ee8 here): not changed, left for its owner.

## Files

- Limiter: `src/gamez/zVideo/zvid_init.cpp`. Heap: `src/gamez/zSystem/zsys_spr.cpp`, `port/CMakeLists.txt`,
  `src/Apps/FTS/state/st_menu.cpp`, `st_core.cpp`; the stack fix `src/gamez/zSystem/zsys_trc.cpp`.
- Time base: `port/compat/libpad.c`, `port/test/fake_pad_anchors.cpp` (new), `port/tools/dev/hook_clock.h`
  (new), `hook_skipcams.h`, every converted hook and pad script under `port/test-hooks/`, its `README.md`.
- Gate: `port/tools/dev/gate.ps1` (own build dir per worker: `gate-<scratch name>`; its time limits and done
  patterns were not changed), `port/tools/dev/README.md`, `docs/port/WORKER_BRIEF.md`.
- Not done: dropping the unused unwind tables. The 86 KB `.eh_frame` is libstdc++'s and libgcc's own (the
  game is built without exceptions); removing it needs a linker script `/DISCARD/` of `.eh_frame`, which
  breaks crtbegin's frame registration (`__EH_FRAME_BEGIN__`) and turns any libstdc++ throw from a
  terminate into undefined behaviour: not free, so not done.
