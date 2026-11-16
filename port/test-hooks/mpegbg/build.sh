#!/bin/bash
# port/test-hooks/mpegbg/build.sh: TEST BUILD ONLY - the menus' MPEG background: boot intro movies, dlgPBMenu / dlgMISSIONSELECTION with stand-in movies for the retail looping backgrounds (not on the demo disc), a switch to an image menu and back, the Alaska cinematic skipped; heap and pictures traced.
# Sources: hook_mpegbg.cpp. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_mpegbg.cpp" -- "${@:3}"
