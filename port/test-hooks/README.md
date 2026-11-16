# Port test hooks

Per-feature test hooks for the functional port lane. A hook is a small C++ (or C) file linked into
a **scratch test build only**, with `-Wl,--wrap=<symbol>`: it replaces or surrounds a few game
functions to place the player, drive the pad from the game state, aim a test camera, skip mission
cameras, or trace state, so one emulator run shows a feature working. Many use
`#define private public` to reach game internals.

- Hooks are never part of a normal build: `port/CMakeLists.txt` never compiles this folder, the
  default build has no fake pad and no `--wrap`, and `port/tools/dev/default.sh` checks that.
- They are not compatibility shims (those live only in `port/compat/`) and not game source (`src/`
  must never include or depend on them).
- What a hook run shows is behaviour in the emulator, never evidence for the matching stages.

## Layout

`<feature>/` holds the hook source(s), the pad scripts (`pad_*.txt`) its runs used, and `build.sh`,
which turns the feature's arguments into `-D` flags and calls `port/tools/dev/hook.sh`.
`common/pad_start.txt` is the standard START path into mission m8 with the intro-movie skip. The
shared test camera (`hook_freecam.h`), mission-camera skip (`hook_skipcams.h`) and time base
(`hook_clock.h`) headers are in `port/tools/dev/` and on every hook's include path.

| feature | sources | `build.sh` arguments | what it does |
| --- | --- | --- | --- |
| `actions` | `hook_actions.cpp` | `<build> <pad> <targets> [flags]` | player in front of action nodes / climb walls (targets in the header); TRIANGLE = next target; mark/glass cameras |
| `ai` | `hook_ai.cpp` | `<build> <pad> <ai> [extra sources]` | `CMission::Open` AI override; `PROF=1` live-heap profiler |
| `aimapio` | `hook_aimapio.cpp` | `<build> [pad] [flags]` | the AI map loader (`CAiMap::Read`): one line per real map read (version, sizes, table counts, FNV-1a sums of cells and tables) to compare two builds on the disc's maps (all version 19); `-DAIMAPIO_SELFTEST`: after the first map, the old versions from synthetic files the hook writes from the layouts in `zai.h` (`cell_v2`, `cell_v3`, `action_v15`, `action_v18`, `region_v4`): for 0-18 `read_cells` on a 2 x 2 map, for 0-20 the whole `Read` (result, parameters, converted cells / actions / regions, links, spores, lines, scanlines, map extra bytes, bytes consumed), PASS / FAIL per test and a total |
| `camcmd` | `hook_camcmd.cpp` + `../state/hook_state.cpp` | `<build> [pad] [flags]` | the camera animation commands' text parsers (the disc's anims are compiled, so they never run on it): `SOCOM_CAMCMD_DELAY` HUD ticks (default 300) after the mission cameras, a reader file served from memory (`CBufferIO::Open` wrap) goes through `CZAnimMain::AnimParseCmd` command by command (DYNAMICS_RELEASE / ACQUIRE_CAMERA, CAMERA_INDOORS, SET_CAMERA_REGION_TEST ON / OFF, GET_CAMERA_REGION_TEST, CAMERA_PARAMS with SAVE and six key tracks, then RESTORE); each record dumped (header, flags, tracks, keys) and given to its begin / tick, the camera switches and the world camera's fields of view, planes, fog and range scale traced after each, the switches put back |
| `clone` | `hook_clone.c` | `<build> [pad]` | traces `zdb::CMesh::Clone` / `AddLOD` |
| `combat` | `hook_combat.cpp` | `<build> [pad] [flags]` | enemy combat set-up, mission cameras skipped, test camera |
| `death` | `hook_death.cpp`, `hook_free.cpp`, `hook_leak.cpp` | `<build> [pad] [flags]` | fatal fall at `SOCOM_HOOK_KILL_FRAME` (`-DSOCOM_HOOK_KILLER`); `HFREE=1` / `HLEAK=1` heap checkers |
| `events` | `hook_events.cpp` | `<build> [pad] [flags]` | AI hearing/sight events with placed enemies, test camera |
| `exit` | `hook_exit.cpp` | `<build> [pad] [flags]` | mission exit round trip driven from the game's top state |
| `fireteam` | `hook_fireteam.cpp` | `<build> [pad] [flags]` | fire-team orders on the mission clock, team trace |
| `hud` | `hook_hud.cpp` | `<build> <pad> [extra sources]` | stand-ins for unwritten non-void stubs the HUD tick reaches |
| `hudmp` | `hook_hudmp.cpp` + `../state/hook_state.cpp` | `<build> [pad] [flags]` | network-only HUD elements in single-player m8: floating team-mate names, the respawn loadout menu driven by a test pad (`-DSOCOM_HOOK_LENSCAM`: test camera on the lens-flare light); the state hook drives menus, movie, cameras, heap |
| `jump` | `hook_jump.cpp` | `<build> <pad> [<flag> <pick> <gap> [climb]]` | DI app-flag census; player before a chosen poly; climb wraps |
| `kit` | `hook_kit.cpp` | `<build> [pad] [flags]` | weapon kit step table: zoom, fire, scopes, binoculars |
| `leftovers` | `hook_leftovers.cpp` | `<build> [pad] [flags]` | scePadRead-driven carry / CQB checks (`-DSOCOM_HOOK_CQB`) |
| `lpc10` | `hook_lpc10.c` | `<build> [pad] [flags]` | offline self-test of the LPC-10 voice codec (`port/compat/lpc10/`) `SOCOM_HOOK_LPC_AT` ticks (1/30 s, default 200) after the main menu came up: synthetic 8 kHz silence, a 100 Hz formant-filtered pulse train, white noise and a voiced / noise switch (`SOCOM_LPC_FR` frames each, default 30) through `lpc10_encode` and, step by step, `prepro_` / `analys_` / `encode_` / `chanwr_` (bits compared), then `lpc10_decode`; per frame the bits, analysis and decoded voicing / pitch / RMS / RC1-3 and the input / output RMS; per-segment summary, non-finite count, and a second run on fresh states compared by checksum |
| `memcard` | `hook_memcard.cpp` | `<build> <pad> [flags]` | the game's own memory-card scripts, which the demo's screens never start: from dlgOptions_Menu the hook activates UIIntro's `intro_onstart` (format questions, `FormatMemCard`, `Ensure_MC_Dirs`: directory, icons, `SaveConfig`) and UIMemCardAnim's `load_initial_config` / `save_and_leave`, answers their pop-ups with the pad and changes MUSIC_VOLUME on the audio screen; `-DSOCOM_HOOK_MC_PLAN=0` probe / `1` format and save / `2` load, `-DSOCOM_HOOK_MC_FORMAT=1` lets the layer format (an unformatted card only; the dedicated test card only, `pcsx2-boot.ps1 -MemCard`), `-DSOCOM_HOOK_MC_ICONS` (icons written again), `-DSOCOM_HOOK_MC_FIOTEST` (disc file reads); traces every `CMemCard` call, the persistent variables saved / loaded, the card directory and the poll timings (`docs/port/notes/memcard.md`) |
| `mpegbg` | `hook_mpegbg.cpp` | `<build> [pad] [flags]` | the menus' MPEG backgrounds driven from the open dialog: the boot intro movies, dlgPBMenu / dlgMISSIONSELECTION with stand-in movies for the retail looping backgrounds the demo disc lacks (`SOCOM_HOOK_LOOP_MOVIE`, `SOCOM_HOOK_RADAR_MOVIE`), a switch to an image menu and back, the Alaska cinematic skipped with CROSS; `CMPEG` Run / Loop / End, pictures, frame time and heap traced (`-DSOCOM_HOOK_DIAG=n`: IPU / DMAC watchdog) |
| `orders` | `hook_orders.cpp` | `<build> [pad] [flags]` | OrdersMenu from the fake pad, team trace, test camera |
| `pickups` | `hook_pickups.cpp`, `hook_pickstance.cpp` | `<build> [pad] [flags]` | dropped-weapon pickup (`-DSOCOM_HOOK_DROPCAM`); `HOOK=pickstance` variant |
| `render` | `hook_render.cpp` + `../state/hook_state.cpp` | `<build> [pad] [flags]` | character shadows (render maps) and light maps in m8: AddShadow / AddLightMap trace, per-150-frame render-map and light-map counts, render-map updates and frame restores per frame, heap; `-DRN_NOSHADOW` / `-DRN_NOLIGHTMAP` / `-DRN_LMDUMP` (no shadow / no plain light maps: the "before"), `-DRN_CAM=<frame>` (test camera on the player, three views; `-DRN_CAMD=<distance>`, `-DRN_CAMLEN=<frames>`); `pad_fire.txt` fires once a second from 2 s after the mission cameras (`play+120`) for 30 s |
| `shapes` | `hook_shapes.cpp` | `<build> [pad] [flags]` | character census, enemy (`-DSOCOM_HOOK_ENEMY`) / team-mate placed ahead |
| `sp` | `hook_sp.cpp` + `../state/hook_state.cpp` | `<build> [pad] [flags]` | the last single-player gaps in m8: CAMERA_PARAMS begin / tick and the world camera's field of view, planes, fog and range scale per change (`-DSP_NOPARAMS`: the command off, the "before"; the state hook's `-DSOCOM_HOOK_CAMS_PLAY` lets the briefing cameras play); AI map set census and cross-map routes (`-DSP_ROUTE_AT` / `_MAP` / `_LEN` / `_PLACE`, `-DSP_NOROUTE`); muzzle-flash light-map count and heap (`-DSP_SLOWMO=<flash>`: 1/50 speed with the test camera on the player); `-DSP_GOPT=<flag>` / `-DSP_VISINFO`: a `CHUD::StatusLine` debug readout on; `pad_fire.txt` fires once a second from 2 s after the mission cameras (`play+120`) for 61 s |
| `spawn` | `hook_spawn.cpp` | `<build> <pad> <x> <z> [flags]` | player moved to x/z at ground level; GS texture buffer dump |
| `stance` | `hook_stance.cpp`, `hook_stance_s2.cpp` | `<build> [pad] [flags]` | enemy SetStance test (`CTStance::Begin`); `HOOK=stance_s2` variant |
| `state` | `hook_state.cpp`, `hook_heapmap.cpp` | `<build> [pad] [flags]` | game-state round trips (menus, m8, pause ABORT / fatal fall, debrief) driven by top state and open dialog; heap per change (`-DSOCOM_HOOK_MALLOC`: failed / break-growing requests with file:line; `HLEAK=1` + `-DSOCOM_HOOK_LEAK`: survivors and a heap walk with the pins at the menus' world load). `HMAP=1` + `-DSOCOM_HOOK_HEAPMAP` (instead of both): heap maps that allocate nothing (every free chunk of 4 KB+, the in-use runs between them with their sites and the hook's phase, the largest hole, top and room) at the first main menu, the first two mission starts and returns and before every 2 MB+ request (`-DSOCOM_HMAP_MAPS=<n>`, default 4), 256 KB+ blocks made / freed, newlib's own long-lived blocks (`_Balloc`, lazily made mutexes); `-DSOCOM_HMAP_NOTAG`: no site table (small bss, the default build's heap end); `-DSOCOM_HMAP_XSIZE=<bytes>` / `_XCOUNT` / `_XAT=0\|1`: a test-only boot allocation (before the global constructors, or where the ELF builds `theValveSaveManager`); `-DSOCOM_HMAP_LOG`: every allocator call as one line |
| `states` | `hook_states.cpp` | `<build> [pad] [flags]` | AI door / corpse / stun state tests, test camera |
| `tacmap` | `hook_tacmap.cpp` | `<build> [pad] [flags]` | tactical map runs: health kept full, position trace |
| `teamhud` | `hook_th.cpp` | `<build> [pad] [flags]` | team HUD rows, state-driven pad |
| `vehicles` | `hook_vehicles.c` | `<build> [pad]` | traces `CMission::LoadVehicles` |
| `voicecams` | `hook_vc.cpp` | `<build> [pad] [flags]` | voice cameras, state-driven pad |
| `wall` | `hook_wall.cpp` | `<build> <pad> <gap> <range> [<x> <z> [<name>]]` | player before the nearest wall (`HOOK_BACK=1`: facing away) |
| `znet` | `hook_znet.cpp` | `<build> [pad] [flags]` | the online screens the demo menu does not reach, opened from dlgMenu: dlgNetConnect (the Medius lobby's offline connect failure, back to dlgMenu) and dlgNetConfig (the network configuration offline); traces the lobby state and the socom_online_state / NETCNF_ERRNO valves |
| `zreader` | `hook_zreader.cpp` + `../state/hook_state.cpp` | `<build> [pad] [flags]` | the text reader's file stack and preprocessor (no disc reader uses them): at the first reader read a self-test parses the hook's own text files (served from memory through a `CBufferIO::Open` wrap: nested `#include` to depth 3, `#ifdef` / `#else` / `#endif`, a quoted include, a `#define`) and dumps the result with the stack depth and symbol count; every raw `.rdr` open and `zrdr_read` traced, `e3config.rdr` (read raw by `CLoadState::Init`) dumped; a diag spec on `pop__10CFileStackFb` traces the pops |
| `zvehicle` | `hook_zvehicle.cpp` | `<build> [pad] [flags]` | X skips the m8 mission cameras, player trace; `-DSOCOM_HOOK_TURRET` test turret on a world node (`_CAM`: camera on it); `pad_armory.txt` |
| `znode` | `hook_znode.cpp` + `../state/hook_state.cpp` | `<build> [pad] [flags]` | zNode in m8: census after LoadWorld (level-of-detail / material / scrolling-texture bands, texture effects, landmarks, no-far-clip nodes, lights), 150-frame trace (wind, scrolling UV, DrawLOD calls / hidden, frame time); `-DZN_NOLOD` (DrawLOD always draws), `-DZN_CAM=<frame>` (test camera on the scrolling computer screen) |
| `zui` | `hook_zui.cpp` | `<build> [pad] [flags]` | zUI controls the demo's offline menus do not reach, driven from the open dialog: the SavedGames list box on dlgDebriefing and dlgPBMenu (variable filled with `SOCOM_HOOK_ROWS` rows, shown, DOWN / UP scroll, TRIANGLE), then dlgNotEnoughSpace (wrapped text); list state traced. `-DSOCOM_HOOK_SKB` (instead of the lists): the soft keyboard raised by dlgNetPlayerName's own anims (name button: SetSkbPurpose + GetTextInput on MPPLAYERNAME), driven with the pad (R1 Caps Lock, LEFT / RIGHT, CROSS types, SQUARE backspace, CIRCLE accepts, TRIANGLE cancels); keyboard node, skb_done, typed text and PLAYERNAMEVAR traced |
| `win` | `hook_win.cpp` | `<build> [pad] [flags]` | scripted m8 playthrough to MISSION SUCCESS (`-DSOCOM_HOOK_WIN`, `-DSOCOM_HOOK_EXITPATHS`) |

`[pad]` defaults to the feature's first pad; `[flags]` are passed to `hook.sh` after `--` (`-D...`
to the compiler, `-Wl,...` to the linker). Each hook's header comment lists its own `SOCOM_HOOK_*`
switches.

## Pad scripts

Comma-separated terms `<when>:<what>` (newlines count as commas), read by the fake pad
(`SOCOM_PORT_FAKE_PAD`, `port/compat/libpad.c`):

- `<when>` is `<anchor>[.<k>]+<fields>`: that many 60 Hz fields (vertical blanks, 1/60 s of real
  time) after the k-th time (default the first) the game reached the anchor. Times do not depend on
  the boot length or the frame rate (the missions run at the ELF's 30 fps cap, the menus at 30 fps
  before the first mission and 60 after it). The old form `<read>` (a pad-read count from boot)
  still works, but its meaning moves with both; no script here uses it except `state/pad_idle.txt`.
- Anchors (`port/test/fake_pad_anchors.cpp`, polled at every pad read; each is traced as
  `PAD: anchor <name>.<k> at field <n>`): `boot`; `menu` (dlgMenu opened); `brief` (the m8 briefing
  dlgAlaska_mission3); any dialog by its file name without `.rdr` (`dlgAlaskaCinematic`,
  `dlgOptions_Menu`, ...); `load`; `core` (a mission reached); `movie` (a cinematic on top);
  `start` (the mission's play begins after its intro movie: the first briefing-camera frame);
  `play` (the briefing cameras over: known 2 s after the last camera frame, which is its time);
  `debrief` (the exit state on top). A hook can add its own (`hook_set_anchor`, `hook_clock.h`).
- `<what>` is a button `START SELECT UP DOWN LEFT RIGHT CROSS CIRCLE SQUARE TRIANGLE L1 L2 R1 R2 L3
  R3` with an optional `+<fields>` hold (default 6 = the old three reads at 60 fps), or
  `<AXIS>=<0..255>[+<fields>]` for a stick (`LX LY RX RY`, 128 centred, `LY=0` fully up) or a held
  button's pressure (`CROSSP`, `R1P`, ...). A term starts at the first pad read at or after its time
  and is seen by that read at least; a term due while the game reads no pad (a load) starts at the
  next read.

The START path into m8 (`common/pad_start.txt`): `menu+120:CROSS` (PLAY GAME),
`dlgAlaskaCinematic+60:CROSS` (skip the cinematic), `brief+180..260:DOWN` x5, `brief+300:CROSS`
(deploy), `movie+80:CROSS` (skip the intro movie). Mission terms are timed from `start` (or `play`
after the cameras); a second mission uses `brief.2`, `movie.2`, `start.2`. The per-feature scripts
were converted from read counts (one read was 1/30 s in a mission at 60 fps: two fields).

Hooks keep their own times in `port/tools/dev/hook_clock.h` units: `hook_ticks()` (1/30 s, so the
numbers tuned in pad reads at 60 fps keep their meaning) and `hook_fields()`; per-read and per-frame
code that tests exact counts runs once per tick / field (`hook_step`, `hook_field_step`). Several
hooks also press buttons themselves from the game state (scePadRead wraps).

## Building and running one

On the Linux side (from PowerShell through `port/tools/dev/wsl.ps1`):

```powershell
$env:SOCOM_SCRATCH = 'build\port\boot-mywork'                  # your scratch folder
.\port\tools\dev\wsl.ps1 tree.sh --fresh                        # isolated tree = HEAD + your files
.\port\tools\dev\wsl.ps1 port\test-hooks\stance\build.sh stc1   # fake pad + hook, links stc1
.\port\tools\dev\run.ps1 -Build stc1 -Name stc1 -Seconds 90     # boot once; stc1.log, stc1-90.png
```

or in one step with test edits: `wsl.ps1 tb.sh -k stance stc1 pad_s1.txt [edits...]`.
`hook.sh` derives the `--wrap` list from the `__wrap_*` symbols each object defines, so wraps that
a hook enables with `#ifdef` follow the `-D` flags. A new hook: copy the closest feature folder,
keep the test-only header comment, and include `hook_freecam.h` / `hook_skipcams.h` rather than
rewriting them.
