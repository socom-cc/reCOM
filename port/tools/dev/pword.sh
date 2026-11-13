#!/bin/bash
# pword.sh <build> <addr> [n]: dump n words (default 8) of a port build at addr, each with the
# symbol it points to (vtables, tables). Merged vt.sh.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
E=$(socom_build_elf "$1")
a=$(( $2 )); n=${3:-8}
mips64r5900el-ps2-elf-objdump -s --start-address=$a --stop-address=$(( a + 4*n )) "$E" | tail -n +5 | while read addr w1 w2 w3 w4 rest; do
  for w in $w1 $w2 $w3 $w4; do
    v=$(echo $w | sed -E 's/(..)(..)(..)(..)/\4\3\2\1/')
    echo "$addr $v $(mips64r5900el-ps2-elf-addr2line -f -C -e "$E" 0x$v | head -1)"
  done
done
