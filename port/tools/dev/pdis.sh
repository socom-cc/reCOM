#!/bin/bash
# pdis.sh <build> <start> <end> | <build> <symbol-regex>: disassemble a port build (demangled),
# by address range or every function whose symbol line matches the regex (merged pdis2.sh).
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
E=$(socom_build_elf "$1")
if [ $# -ge 3 ]; then
  mips64r5900el-ps2-elf-objdump -d -C --no-show-raw-insn -m mips:5900 --start-address="$2" --stop-address="$3" "$E" | tail -n +7
else
  mips64r5900el-ps2-elf-objdump -d -C --no-show-raw-insn -m mips:5900 "$E" | awk -v re="$2" '$0 ~ "^[0-9a-f]+ <" { p = ($0 ~ re) } p'
fi
