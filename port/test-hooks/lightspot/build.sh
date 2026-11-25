#!/bin/bash
# port/test-hooks/lightspot/build.sh: TEST BUILD ONLY - puts the player at <x> <y> <z> (the position the game's status line shows, option -f) once the mission cameras are over, for screenshots of one spot in two builds.
# Sources: hook_lightspot.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker), e.g. -DSOCOM_HOOK_HEADING=1.57f.
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> <pad> <x> <y> <z> [flags]
[ $# -ge 5 ] || { echo "usage: build.sh <build> <pad> <x> <y> <z> [flags]" >&2; exit 2; }
exec bash "$HOOKSH" "$1" "$2" "$D/hook_lightspot.cpp" -- -DSOCOM_HOOK_X=$3 -DSOCOM_HOOK_Y=$4 -DSOCOM_HOOK_Z=$5 "${@:6}"
