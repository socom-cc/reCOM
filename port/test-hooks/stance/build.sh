#!/bin/bash
# port/test-hooks/stance/build.sh: TEST BUILD ONLY - state-driven enemy SetStance test (CTStance::Begin wrap), mission cameras skipped; HOOK=stance_s2 builds the second variant.
# Sources: hook_stance.cpp, hook_stance_s2.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]   (HOOK=stance_s2: the second variant)
exec bash "$HOOKSH" "$1" "${2:-$D/pad_s1.txt}" "$D/hook_${HOOK:-stance}.cpp" -- "${@:3}"
