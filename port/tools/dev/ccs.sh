#!/bin/bash
# ccs.sh <file.cpp> [tree]: compile one unit (a scratch probe or a src/ file) to assembly on stdout
# with the port flags (directive noise removed), to see what GCC makes of a construct.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
R=${2:-$REPO}
mips64r5900el-ps2-elf-g++ -S -o - $SOCOM_DEFS $SOCOM_CXXFLAGS $(socom_incs "$R") \
  -include "$R/port/include/socom_port_prefix.h" "$1" 2>&1 \
  | grep -vE '^\s+\.(loc|cfi|file|section|align|globl|type|ent|frame|mask|fmask|set|size|end)|^\$'
