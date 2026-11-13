#!/bin/bash
# port/test-hooks/spawn/build.sh: TEST BUILD ONLY - moves the player to <x> <z> at the ground altitude (AttachSeal wrap); dumps the GS texture buffers once.
# Sources: hook_spawn.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> <pad> <x> <z> [flags]
[ $# -ge 4 ] || { echo "usage: build.sh <build> <pad> <x> <z> [flags]" >&2; exit 2; }
exec bash "$HOOKSH" "$1" "$2" "$D/hook_spawn.cpp" -- -DSOCOM_HOOK_X=$3 -DSOCOM_HOOK_Z=$4 "${@:5}"
