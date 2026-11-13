#!/bin/bash
# port/test-hooks/states/build.sh: TEST BUILD ONLY - AI states: door / corpse / stun tests at frames 60 / 1000 / 1700, test camera.
# Sources: hook_states.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/pad_ev.txt}" "$D/hook_states.cpp" -- "${@:3}"
