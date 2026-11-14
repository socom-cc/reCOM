#!/bin/bash
# port/test-hooks/sp/build.sh: TEST BUILD ONLY - the last single-player gaps in m8 (CAMERA_PARAMS,
# cross-map AI routes, muzzle-flash light maps, HUD debug readouts), with ../state/hook_state.cpp
# driving the game (menus, intro movie, briefing cameras, heap trace).
# Sources: hook_sp.cpp + ../state/hook_state.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker). Pass -DSOCOM_HOOK_MISSIONS=1
# -DSOCOM_HOOK_PLAY_AT=999999 to stay in the mission; the hook's switches are in its header.
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_sp.cpp" "$D/../state/hook_state.cpp" -- "${@:3}"
