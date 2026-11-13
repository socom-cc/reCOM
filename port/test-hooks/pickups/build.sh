#!/bin/bash
# port/test-hooks/pickups/build.sh: TEST BUILD ONLY - character census, enemy/teammate placed in front of the player, dropped-weapon camera (-DSOCOM_HOOK_DROPCAM); HOOK=pickstance builds hook_pickstance.cpp (kill by UpdateHealth, CROSS take, -DSOCOM_HOOK_TAKECAM).
# Sources: hook_pickups.cpp, hook_pickstance.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]   (HOOK=pickstance: the pickup + stance variant)
exec bash "$HOOKSH" "$1" "${2:-$D/pad_f2.txt}" "$D/hook_${HOOK:-pickups}.cpp" -- "${@:3}"
