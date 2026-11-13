#!/bin/bash
# port/test-hooks/death/build.sh: TEST BUILD ONLY - the player's fatal fall at SOCOM_HOOK_KILL_FRAME (-DSOCOM_HOOK_KILLER: nearest enemy as killer); HFREE=1 adds the use-after-free checker hook_free.cpp, HLEAK=1 the leak tracker hook_leak.cpp.
# Sources: hook_death.cpp, hook_free.cpp, hook_leak.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]   (HFREE=1 / HLEAK=1 add the heap checkers)
S=("$D/hook_death.cpp"); [ -n "${HFREE:-}" ] && S+=("$D/hook_free.cpp"); [ -n "${HLEAK:-}" ] && S+=("$D/hook_leak.cpp")
exec bash "$HOOKSH" "$1" "${2:-$D/pad_t1.txt}" "${S[@]}" -- "${@:3}"
