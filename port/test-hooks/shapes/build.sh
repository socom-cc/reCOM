#!/bin/bash
# port/test-hooks/shapes/build.sh: TEST BUILD ONLY - character census, enemy (-DSOCOM_HOOK_ENEMY) / teammate placed in front of the player, reticle seal trace.
# Sources: hook_shapes.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/pad_t9.txt}" "$D/hook_shapes.cpp" -- "${@:3}"
