#!/bin/bash
# Build and link the functional port ELF (run inside the Linux side).
#   port/tools/link.sh            configure + build socom_game + link socom_port.elf
# Build dir: $SOCOM_PORT_BUILD (default $HOME/.cache/socom/port-build). Writes there:
#   lib.log, link.log, undefined.txt (demangled, one per line), multiple.txt
set -u
export PS2DEV=${SOCOM_PS2DEV:-$HOME/.local/share/socom/ps2dev-v2.0.0}
export PS2SDK=$PS2DEV/ps2sdk
export PATH=$PS2DEV/bin:$PS2DEV/ee/bin:$PS2DEV/iop/bin:$PS2DEV/dvp/bin:$PS2SDK/bin:/usr/bin:/bin
REPO=$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)
B=${SOCOM_PORT_BUILD:-$HOME/.cache/socom/port-build}
mkdir -p "$B"
if [ ! -f "$B/CMakeCache.txt" ]; then
  cmake -S "$REPO/port" -B "$B" -DCMAKE_TOOLCHAIN_FILE="$PS2DEV/share/ps2dev.cmake" -DCMAKE_BUILD_TYPE=Release > "$B/configure.log" 2>&1 || { tail -20 "$B/configure.log"; exit 1; }
fi
cmake --build "$B" --target socom_game -j"$(nproc)" -- -k > "$B/lib.log" 2>&1
lib=$?
echo "library: exit=$lib errors=$(grep -c 'error:' "$B/lib.log") failing units=$(grep -oE '^[^ ]+\.cpp:[0-9]+:[0-9]+: error' "$B/lib.log" | cut -d: -f1 | sort -u | wc -l)"
[ $lib -ne 0 ] && exit 1
cmake --build "$B" --target socom_port > "$B/link.log" 2>&1
link=$?
grep -oE "undefined reference to \`[^']+'" "$B/link.log" | sed -E "s/undefined reference to \`//; s/'$//" | sort -u | mips64r5900el-ps2-elf-c++filt > "$B/undefined.txt"
grep -oE "multiple definition of \`[^']+'" "$B/link.log" | sed -E "s/multiple definition of \`//; s/'$//" | sort -u | mips64r5900el-ps2-elf-c++filt > "$B/multiple.txt"
echo "link: exit=$link undefined=$(wc -l < "$B/undefined.txt") multiple=$(wc -l < "$B/multiple.txt")"
[ $link -eq 0 ] && ls -la "$B/socom_port.elf"
exit $link
