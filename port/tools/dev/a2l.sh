#!/bin/bash
# a2l.sh <build> <addr>...: symbolize addresses of a port build (function and file:line, demangled).
# Merged: fn.sh / near.sh (the function containing an address) = the first line of each pair.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
E=$(socom_build_elf "$1"); shift
mips64r5900el-ps2-elf-addr2line -f -C -e "$E" "$@" | sed "s|$REPO/||; s|$TREE/||"
