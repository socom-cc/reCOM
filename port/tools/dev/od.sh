#!/bin/bash
# od.sh <start> <end>: hex dump of support/socom.elf data (read-only); od.sh -h: section headers
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
socom_need_elf
if [ "${1:-}" = "-h" ]; then mips64r5900el-ps2-elf-objdump -h "$ELF"; exit; fi
mips64r5900el-ps2-elf-objdump -s --start-address="$1" --stop-address="$2" "$ELF" | tail -n +4
