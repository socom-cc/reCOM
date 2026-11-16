#!/bin/bash
# port/test-hooks/camcmd/build.sh: TEST BUILD ONLY - the camera animation commands' text parsers
# (zcam_main.cpp: DYNAMICS_RELEASE / ACQUIRE_CAMERA, CAMERA_INDOORS, SET / GET_CAMERA_REGION_TEST,
# CAMERA_PARAMS): a text file served from memory goes through CZAnimMain::AnimParseCmd once the
# mission cameras are done, each record dumped and given to its begin / tick; with
# ../state/hook_state.cpp driving the game (menus, intro movie, briefing cameras, heap trace).
# Sources: hook_camcmd.cpp + ../state/hook_state.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker). Pass -DSOCOM_HOOK_MISSIONS=1
# -DSOCOM_HOOK_PLAY_AT=999999 to stay in the mission; -DSOCOM_CAMCMD_DELAY=<HUD ticks> after the cameras.
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_camcmd.cpp" "$D/../state/hook_state.cpp" -- "${@:3}"
