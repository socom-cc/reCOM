#!/bin/bash
# GCC compile sweep for the functional port lane (run inside the Linux side).
#   port/tools/sweep.sh units   [filter]   compile every src/ unit (not *_holding.cpp)
#   port/tools/sweep.sh headers [filter]   compile each src/ header on its own
# Logs go to $SOCOM_PORT_SWEEP (default $HOME/.cache/socom/sweep/<mode>);
# prints "total/ok/fail" and writes status.txt ("<exit> <path>") there.
set -u
MODE=${1:-units}; FILTER=${2:-}
export PS2DEV=${SOCOM_PS2DEV:-$HOME/.local/share/socom/ps2dev-v2.0.0}
export PS2SDK=$PS2DEV/ps2sdk
export PATH=$PS2DEV/ee/bin:$PS2SDK/bin:/usr/bin:/bin
REPO=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
OUT=${SOCOM_PORT_SWEEP:-$HOME/.cache/socom/sweep}/$MODE
rm -rf "$OUT"; mkdir -p "$OUT/obj" "$OUT/log" "$OUT/tu"
cd "$REPO"
case $MODE in
  units)   find src -name '*.cpp' ! -name '*_holding.cpp' ;;
  headers) find src -name '*.h' ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac | grep -- "$FILTER" | sort > "$OUT/files.txt"
compile() {
  f=$1; key=$(echo "$f" | tr '/' '_')
  src=$f
  if [ "$MODE" = headers ]; then src=$OUT/tu/$key.cpp; printf '#include "%s"\n' "${f#src/}" > "$src"; fi
  mips64r5900el-ps2-elf-g++ -std=gnu++17 -O2 -G0 -D_EE -DSOCOM_PORT -Isrc -Iport/compat/include \
    -I"$PS2SDK/ee/include" -I"$PS2SDK/common/include" \
    -include port/include/socom_port_prefix.h -fno-exceptions -fno-rtti -w -fmax-errors=50 \
    -c "$src" -o "$OUT/obj/$key.o" > "$OUT/log/$key.log" 2>&1
  echo "$? $f"
}
export -f compile; export OUT PS2SDK MODE
xargs -a "$OUT/files.txt" -P "$(nproc)" -I{} bash -c 'compile {}' | sort -k2 > "$OUT/status.txt"
echo "$MODE total $(wc -l < "$OUT/status.txt") ok $(grep -c '^0 ' "$OUT/status.txt") fail $(grep -vc '^0 ' "$OUT/status.txt")"
