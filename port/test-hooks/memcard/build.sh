#!/bin/bash
# port/test-hooks/memcard/build.sh: TEST BUILD ONLY - the memory-card path in one run at the title screen: init, mkdir / chdir, a PERSISTENT UI variable saved with SaveConfig and restored with LoadConfig, header, icons.
# Sources: hook_memcard.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_memcard.cpp" -- "${@:3}"
