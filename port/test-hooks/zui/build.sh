#!/bin/bash
# port/test-hooks/zui/build.sh: TEST BUILD ONLY - zUI controls the demo's offline menus do not reach (list boxes on dlgDebriefing / dlgPBMenu with a filled SavedGames variable; -DSOCOM_HOOK_SKB the soft keyboard), driven from the open dialog.
# Sources: hook_zui.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_zui.cpp" -- "${@:3}"
