#!/bin/bash
# fake.sh <build> <pad>: configure the scratch build dir ~/.cache/socom/<build> from the isolated
# tree ($TREE, see tree.sh) with the fake-pad test hook, then link (port/tools/link.sh of that tree).
#   <pad>: a pad script file (pad_*.txt, looked up as given, in the scratch folder, then under
#   port/test-hooks), or the script itself ("60:CROSS,130:DOWN,..."), or "-" for no fake pad
#   (a plain default build). See port/CMakeLists.txt SOCOM_PORT_FAKE_PAD for the syntax.
# Linker flags left in the cache by an earlier hook.sh run are reset, so the result never carries a
# test hook it was not asked for. Writes only under ~/.cache/socom.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
[ $# -ge 2 ] || { echo "usage: fake.sh <build> <pad-file|pad-script|->" >&2; exit 2; }
socom_need_toolchain
B=$CACHE/$1
PAD=$(socom_pad "$2")
[ -d "$TREE/port" ] || { echo "fake.sh: no tree at $TREE (run tree.sh first)" >&2; exit 1; }
mkdir -p "$B"
if [ ! -f "$B/CMakeCache.txt" ]; then
  cmake -S "$TREE/port" -B "$B" -DCMAKE_TOOLCHAIN_FILE="$PS2DEV/share/ps2dev.cmake" -DCMAKE_BUILD_TYPE=Release \
    "-DSOCOM_PORT_FAKE_PAD=$PAD" > "$B/configure.log" 2>&1 || { tail -20 "$B/configure.log"; exit 1; }
else
  LF=()
  grep -q '^CMAKE_EXE_LINKER_FLAGS:.*--wrap' "$B/CMakeCache.txt" && LF=("-DCMAKE_EXE_LINKER_FLAGS=$SOCOM_BASE_LDFLAGS")
  cmake -S "$TREE/port" -B "$B" "-DSOCOM_PORT_FAKE_PAD=$PAD" "${LF[@]}" > "$B/configure.log" 2>&1 || { tail -20 "$B/configure.log"; exit 1; }
fi
grep "TEST HOOK" "$B/configure.log"
SOCOM_PORT_BUILD=$B bash "$TREE/port/tools/link.sh"
