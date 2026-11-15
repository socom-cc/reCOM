#!/bin/bash
# port/test-hooks/lpc10/build.sh: TEST BUILD ONLY - an offline self-test of the LPC-10 voice codec (port/compat/lpc10/) at the title screen: synthetic silence / vowel / noise / voiced-unvoiced input through lpc10_encode and lpc10_decode, traced per frame.
# Sources: hook_lpc10.c. Runs in the Linux side (WSL); see port/test-hooks/README.md.
# <pad> is a pad file (pad_*.txt here or in ../common) or a pad script; [flags] go to hook.sh
# after "--" (-D... to the compiler, -Wl,... to the linker).
set -u
D=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
HOOKSH=$D/../../tools/dev/hook.sh
# build.sh <build> [pad] [flags]
exec bash "$HOOKSH" "$1" "${2:-$D/../state/pad_idle.txt}" "$D/hook_lpc10.c" -- "${@:3}"