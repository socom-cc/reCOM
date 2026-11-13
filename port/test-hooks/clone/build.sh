#!/bin/bash
# port/test-hooks/clone/build.sh: TEST BUILD ONLY - zdb::CMesh::Clone / AddLOD wraps (mesh clone traces).
# Sources: hook_clone.c. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../common/pad_start.txt}" "$D/hook_clone.c" -- "${@:3}"
