#!/bin/bash
# bitrd.sh <offset>: lbu readers of <offset>(reg) followed within 4 lines by a dsll32 shift
# (bitfield readers) in the cached full disassembly of support/socom.elf (zs.sh builds the cache).
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
[ -s "$CACHE/full.dis" ] || bash "$DEV/zs.sh" -F '@@none@@' 1 > /dev/null
awk -v pat=",$1(" '/^[0-9a-f]+ </{fn=$2} {l[NR]=$0; f[NR]=fn} END{for(i=1;i<=NR;i++) if (index(l[i],pat) && index(l[i],"lbu")) { for(j=i+1;j<=i+4;j++) if (index(l[j],"dsll32") ) {print f[i]": "l[i]" | "l[j]; break} } }' "$CACHE/full.dis"
