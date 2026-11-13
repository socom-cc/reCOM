#!/bin/bash
# port/test-hooks/jump/build.sh: TEST BUILD ONLY - jump/climb: DI app-flag census; with <flag> the player is put <gap> in front of the <pick>-th nearest poly with those app flags; "climb" adds the DoWallStop / GetTerrainMotionFactor wraps.
# Sources: hook_jump.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> <pad> [<flag> <pick> <gap> [climb]]
[ $# -ge 2 ] || { echo "usage: build.sh <build> <pad> [<flag> <pick> <gap> [climb]]" >&2; exit 2; }
X=(); [ $# -ge 5 ] && X=(-DSOCOM_HOOK_FLAG=$3 -DSOCOM_HOOK_PICK=$4 -DSOCOM_HOOK_GAP=$5.0f)
[ "${6:-}" = climb ] && X+=(-DSOCOM_HOOK_CLIMB)
exec bash "$HOOKSH" "$1" "$2" "$D/hook_jump.cpp" -- "${X[@]}"
