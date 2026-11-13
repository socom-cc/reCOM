#!/bin/bash
# port/test-hooks/exit/build.sh: TEST BUILD ONLY - mission exit round trip: drives the pad from the game's top state (scePadRead wrap), OnMissionStart, mission cameras.
# Sources: hook_exit.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/pad_b1.txt}" "$D/hook_exit.cpp" -- "${@:3}"
