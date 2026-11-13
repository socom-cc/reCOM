#!/bin/bash
# port/test-hooks/win/build.sh: TEST BUILD ONLY - scripted m8 playthrough to MISSION SUCCESS (invincible player and SEALs; -DSOCOM_HOOK_WIN, -DSOCOM_HOOK_EXITPATHS), mission cameras skipped.
# Sources: hook_win.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/pad_a1.txt}" "$D/hook_win.cpp" -- "${@:3}"
