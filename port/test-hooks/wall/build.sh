#!/bin/bash
# port/test-hooks/wall/build.sh: TEST BUILD ONLY - puts the player <gap> in front of the nearest wall within <range> (36 level rays), facing it (HOOK_BACK=1: facing away); optional start <x> <z> and node-name filter.
# Sources: hook_wall.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> <pad> <gap> <range> [<x> <z> [<node-name-part>]]   (HOOK_BACK=1: face away)
[ $# -ge 4 ] || { echo "usage: build.sh <build> <pad> <gap> <range> [<x> <z> [<name>]]" >&2; exit 2; }
X=(-DSOCOM_HOOK_GAP=$3.0f -DSOCOM_HOOK_RANGE=$4.0f)
[ $# -ge 6 ] && X+=(-DSOCOM_HOOK_X=$5.0f -DSOCOM_HOOK_Z=$6.0f)
[ $# -ge 7 ] && X+=("-DSOCOM_HOOK_NAME=\"$7\"")
[ -n "${HOOK_BACK:-}" ] && X+=(-DSOCOM_HOOK_BACK)
exec bash "$HOOKSH" "$1" "$2" "$D/hook_wall.cpp" -- "${X[@]}"
