#!/bin/bash
# port/test-hooks/actions/build.sh: TEST BUILD ONLY - node actions and climb walls: the player is put in front of the named action nodes / walls (targets as in the hook header); fire/mark traces, -DSOCOM_HOOK_MARKCAM=<dist> and -DSOCOM_HOOK_GLASSCAM="dx,dy,dz" test cameras, -DSOCOM_HOOK_SHARDLIFE.
# Sources: hook_actions.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> <pad> <targets> [flags]
[ $# -ge 3 ] || { echo "usage: build.sh <build> <pad> <targets> [flags]" >&2; exit 2; }
exec bash "$HOOKSH" "$1" "$2" "$D/hook_actions.cpp" -- "-DSOCOM_HOOK_TARGETS=\"$3\"" "${@:4}"
