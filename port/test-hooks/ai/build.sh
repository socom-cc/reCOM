#!/bin/bash
# port/test-hooks/ai/build.sh: TEST BUILD ONLY - CMission::Open AI override (-DSOCOM_HOOK_AI=<ai>) and, with PROF=1, the live-heap profiler.
# Sources: hook_ai.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> <pad> <ai> [extra hook sources...]   (PROF=1: heap profiler)
[ $# -ge 3 ] || { echo "usage: build.sh <build> <pad> <ai> [extra sources...]" >&2; exit 2; }
P=(); [ -n "${PROF:-}" ] && P=(-DSOCOM_HOOK_PROF)
exec bash "$HOOKSH" "$1" "$2" "$D/hook_ai.cpp" "${@:4}" -- "-DSOCOM_HOOK_AI=$3" "${P[@]}"
