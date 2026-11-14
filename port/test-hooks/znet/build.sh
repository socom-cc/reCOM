#!/bin/bash
# port/test-hooks/znet/build.sh: TEST BUILD ONLY - the online screens the demo menu does not reach (dlgNetConnect: the Medius lobby's offline connect failure; dlgNetConfig: the network configuration offline), opened from dlgMenu.
# Sources: hook_znet.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_znet.cpp" -- "${@:3}"
