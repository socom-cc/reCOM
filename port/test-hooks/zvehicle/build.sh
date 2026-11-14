#!/bin/bash
# port/test-hooks/zvehicle/build.sh: TEST BUILD ONLY - zVehicle: X skips the m8 mission cameras, player
# trace; -DSOCOM_HOOK_TURRET puts a test turret in m8 (-DSOCOM_HOOK_TURRET_CAM: the camera watches it).
# Sources: hook_zvehicle.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../common/pad_start.txt}" "$D/hook_zvehicle.cpp" -- "${@:3}"
