#!/bin/bash
# port/test-hooks/aimapio/build.sh: TEST BUILD ONLY - the AI map loader (CAiMap::Read): a summary
# line per real map read (counts and sums, to compare two builds on the disc's maps); with
# -DAIMAPIO_SELFTEST the old map versions 2-18 (and 0, 1, 19, 20) from synthetic files.
# Sources: hook_aimapio.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../common/pad_start.txt}" "$D/hook_aimapio.cpp" -- "${@:3}"
