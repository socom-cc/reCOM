#!/bin/bash
# port/test-hooks/orders/build.sh: TEST BUILD ONLY - OrdersMenu from the fake pad, team trace every 2 s, test camera.
# Sources: hook_orders.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/pad_o1.txt}" "$D/hook_orders.cpp" -- "${@:3}"
