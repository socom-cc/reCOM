#!/bin/bash
# port/test-hooks/hud/build.sh: TEST BUILD ONLY - stand-ins for unwritten non-void stubs the HUD tick reaches (wraps follow the hook); add ai/hook_ai.cpp as an extra source for the AI override.
# Sources: hook_hud.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> <pad> [extra hook sources...]
[ $# -ge 2 ] || { echo "usage: build.sh <build> <pad> [extra sources...]" >&2; exit 2; }
exec bash "$HOOKSH" "$1" "$2" "$D/hook_hud.cpp" "${@:3}"
