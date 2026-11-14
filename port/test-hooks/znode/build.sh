#!/bin/bash
# port/test-hooks/znode/build.sh: TEST BUILD ONLY - the zNode scene-graph pieces in m8 (level-of-detail,
# material and scrolling-texture bands, texture effects, landmarks, lights, wind), with
# ../state/hook_state.cpp driving the game (menus, intro movie, briefing cameras, heap trace).
# Sources: hook_znode.cpp + ../state/hook_state.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker). Pass -DSOCOM_HOOK_MISSIONS=1
# -DSOCOM_HOOK_PLAY_AT=999999 to stay in the mission; -DZN_NOLOD, -DZN_CAM=<frame> (see the hook).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_znode.cpp" "$D/../state/hook_state.cpp" -- "${@:3}"
