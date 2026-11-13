#!/bin/bash
# dis.sh [-z] [-r] <start> <end>: disassemble support/socom.elf (read-only) with the ps2dev objdump.
#   -z also disassembles zero blocks (nop runs); -r keeps the raw instruction words (was rawdis.sh).
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
Z=""; RAW="--no-show-raw-insn"
while [ $# -gt 0 ]; do case "$1" in -z) Z="-z"; shift;; -r) RAW=""; shift;; *) break;; esac; done
[ $# -ge 2 ] || { echo "usage: dis.sh [-z] [-r] <start> <end>" >&2; exit 2; }
socom_need_elf
mips64r5900el-ps2-elf-objdump -d $Z $RAW -m mips:5900 --start-address="$1" --stop-address="$2" "$ELF" | tail -n +7
