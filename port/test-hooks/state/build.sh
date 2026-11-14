#!/bin/bash
# port/test-hooks/state/build.sh: TEST BUILD ONLY - game-state round trips (menus -> m8 -> pause ABORT / fatal fall -> debrief -> menus, SOCOM_HOOK_MISSIONS times), driven from the top state and the open dialog; heap traced at each change (-DSOCOM_HOOK_MALLOC: failed allocations too).
# Sources: hook_state.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
# HLEAK=1 adds the leak tracker ../death/hook_leak.cpp (with -DSOCOM_HOOK_LEAK, not -DSOCOM_HOOK_MALLOC)
S=("$D/hook_state.cpp"); [ -n "${HLEAK:-}" ] && S+=("$D/../death/hook_leak.cpp")
exec bash "$HOOKSH" "$1" "${2:-$D/pad_idle.txt}" "${S[@]}" -- "${@:3}"