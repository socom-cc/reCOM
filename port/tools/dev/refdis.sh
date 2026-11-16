#!/bin/bash
# refdis.sh: the reference ELF's full disassembly (objdump -d --no-show-raw-insn, the cache zs.sh
# keeps in ~/.cache/socom/full.dis, rebuilt when the ELF is newer) copied to $SCRATCH/ref.dis for
# the Windows-side readers (auditlib.py: auditpack.py, auditscan.py). Read-only on the ELF.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
socom_need_elf
D=$CACHE/full.dis
mkdir -p "$CACHE" "$SCRATCH"
if [ ! -s "$D" ] || [ "$ELF" -nt "$D" ]; then
  mips64r5900el-ps2-elf-objdump -d --no-show-raw-insn -m mips:5900 "$ELF" > "$D.tmp" 2>/dev/null && mv "$D.tmp" "$D"
fi
cp "$D" "$SCRATCH/ref.dis" && ls -la "$SCRATCH/ref.dis"
