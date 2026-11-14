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
`common/pad_start.txt` is the standard START path into mission m8 with the intro-movie skip at
read 400. The shared test camera (`hook_freecam.h`) and mission-camera skip (`hook_skipcams.h`)
headers are in `port/tools/dev/` and on every hook's include path.

| feature | sources | `build.sh` arguments | what it does |
| --- | --- | --- | --- |
| `actions` | `hook_actions.cpp` | `<build> <pad> <targets> [flags]` | player in front of action nodes / climb walls (targets in the header); TRIANGLE = next target; mark/glass cameras |
| `ai` | `hook_ai.cpp` | `<build> <pad> <ai> [extra sources]` | `CMission::Open` AI override; `PROF=1` live-heap profiler |
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
| `orders` | `hook_orders.cpp` | `<build> [pad] [flags]` | OrdersMenu from the fake pad, team trace, test camera |
| `pickups` | `hook_pickups.cpp`, `hook_pickstance.cpp` | `<build> [pad] [flags]` | dropped-weapon pickup (`-DSOCOM_HOOK_DROPCAM`); `HOOK=pickstance` variant |
| `shapes` | `hook_shapes.cpp` | `<build> [pad] [flags]` | character census, enemy (`-DSOCOM_HOOK_ENEMY`) / team-mate placed ahead |
| `spawn` | `hook_spawn.cpp` | `<build> <pad> <x> <z> [flags]` | player moved to x/z at ground level; GS texture buffer dump |
| `stance` | `hook_stance.cpp`, `hook_stance_s2.cpp` | `<build> [pad] [flags]` | enemy SetStance test (`CTStance::Begin`); `HOOK=stance_s2` variant |
| `state` | `hook_state.cpp` | `<build> [pad] [flags]` | game-state round trips (menus, m8, pause ABORT / fatal fall, debrief) driven by top state and open dialog; heap per change (`-DSOCOM_HOOK_MALLOC`: failed / break-growing requests with file:line; `HLEAK=1` + `-DSOCOM_HOOK_LEAK`: survivors and a heap walk with the pins at the menus' world load) |
| `states` | `hook_states.cpp` | `<build> [pad] [flags]` | AI door / corpse / stun state tests, test camera |
| `tacmap` | `hook_tacmap.cpp` | `<build> [pad] [flags]` | tactical map runs: health kept full, position trace |
| `teamhud` | `hook_th.cpp` | `<build> [pad] [flags]` | team HUD rows, state-driven pad |
| `vehicles` | `hook_vehicles.c` | `<build> [pad]` | traces `CMission::LoadVehicles` |
| `voicecams` | `hook_vc.cpp` | `<build> [pad] [flags]` | voice cameras, state-driven pad |
| `wall` | `hook_wall.cpp` | `<build> <pad> <gap> <range> [<x> <z> [<name>]]` | player before the nearest wall (`HOOK_BACK=1`: facing away) |
| `zvehicle` | `hook_zvehicle.cpp` | `<build> [pad] [flags]` | X skips the m8 mission cameras, player trace; `-DSOCOM_HOOK_TURRET` test turret on a world node (`_CAM`: camera on it); `pad_armory.txt` |
| `zui` | `hook_zui.cpp` | `<build> [pad] [flags]` | zUI controls the demo's offline menus do not reach, driven from the open dialog: the SavedGames list box on dlgDebriefing and dlgPBMenu (variable filled with `SOCOM_HOOK_ROWS` rows, shown, DOWN / UP scroll, TRIANGLE), then dlgNotEnoughSpace (wrapped text); list state traced |
| `win` | `hook_win.cpp` | `<build> [pad] [flags]` | scripted m8 playthrough to MISSION SUCCESS (`-DSOCOM_HOOK_WIN`, `-DSOCOM_HOOK_EXITPATHS`) |

`[pad]` defaults to the feature's first pad; `[flags]` are passed to `hook.sh` after `--` (`-D...`
to the compiler, `-Wl,...` to the linker). Each hook's header comment lists its own `SOCOM_HOOK_*`
switches.

## Pad scripts

One line of comma-separated `<read>:<BUTTON>` presses at pad-read counts (about 30 reads per
second in a mission), plus `<read>:<AXIS>=<0..255>[+<reads>]` stick terms (`LX LY RX RY`), e.g.
`60:CROSS,130:DOWN,...,185:CROSS,400:CROSS` = START path into m8 and skip the intro movie. The
syntax is defined by `SOCOM_PORT_FAKE_PAD` in `port/CMakeLists.txt` (`port/compat/libpad.c`).
Several hooks also press buttons themselves from the game state (scePadRead wraps).

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
