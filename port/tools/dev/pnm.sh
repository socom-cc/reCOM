#!/bin/bash
# pnm.sh [-m] <build> <a,b,c>: port build symbols matching any comma-separated regex (demangled;
# -m: mangled defined symbols of the game library, was nmgrep.sh). Merged nm.sh / nm2.sh.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
if [ "${1:-}" = "-m" ]; then
  shift; B=$(dirname "$(socom_build_elf "$1")")
  L=$(find "$B" -name '*.a' | grep -i game | head -1)
  mips64r5900el-ps2-elf-nm --defined-only "$L" 2>/dev/null | grep -E "${2//,/|}" | awk '{print $3}' | sort -u
else
  mips64r5900el-ps2-elf-nm -C "$(socom_build_elf "$1")" | grep -E "${2//,/|}"
fi
