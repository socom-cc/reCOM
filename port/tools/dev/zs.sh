#!/bin/bash
# zs.sh [-F] [-f <patternfile>] <pattern> [n]: search the full disassembly of support/socom.elf
# (cached in ~/.cache/socom/full.dis, rebuilt when the ELF is newer) and print each match with its
# containing function; first n matches (default 60). Default <pattern> is an awk regex, e.g.
# zs.sh '-29328\(gp\)'; -F a fixed string; -f reads the regex from a file (shell-quoting-proof).
# Merged from g.sh, ga.sh, g2.sh, grepasm.sh and gpref.sh.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
MODE=re
while [ $# -gt 0 ]; do
  case "$1" in -F) MODE=fixed; shift;; -f) MODE=re; PAT=$(tr -d '\r' < "$2"); shift 2;; *) break;; esac
done
[ -n "${PAT:-}" ] || { PAT=${1:?usage: zs.sh [-F] [-f file] <pattern> [n]}; shift; }
N=${1:-60}
socom_need_elf
D=$CACHE/full.dis
mkdir -p "$CACHE"
if [ ! -s "$D" ] || [ "$ELF" -nt "$D" ]; then
  mips64r5900el-ps2-elf-objdump -d --no-show-raw-insn -m mips:5900 "$ELF" > "$D.tmp" 2>/dev/null && mv "$D.tmp" "$D"
fi
if [ $MODE = fixed ]; then
  awk -v pat="$PAT" '/^[0-9a-f]+ </{fn=$2} index($0, pat) {print fn": "$0}' "$D" | head -n "$N"
else
  awk -v pat="$PAT" '/^[0-9a-f]+ </{fn=$2} $0 ~ pat {print fn": "$0}' "$D" | head -n "$N"
fi
