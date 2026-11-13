#!/bin/bash
# errctx.sh <build> <pattern> [n]: n lines (default 20) of the build's lib.log before the first match
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
B=$(dirname "$(socom_build_elf "$1")")
grep -n -m1 -B"${3:-20}" -- "$2" "$B/lib.log" | sed "s|$REPO/||g; s|$TREE/||g" | cut -c1-200
