#!/bin/bash
# default.sh <build>: the default build (no test hook, no fake pad, no test edits) of your work:
# a fresh tree ~/.cache/socom/tree-<name>-default (tree.sh --fresh: HEAD + your files + your
# shared-file edits; <scratch>/shared_default.txt replaces shared.txt when present), then a plain
# link into ~/.cache/socom/<build>. Check it boots to the main menu before you report.
# Merges the per-worker default.sh / build_default.sh.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
[ $# -ge 1 ] || { echo "usage: default.sh <build>" >&2; exit 2; }
socom_need_toolchain
SD=""; [ -f "$SCRATCH/shared_default.txt" ] && SD=$SCRATCH/shared_default.txt
DT=$CACHE/tree-$NAME-default
SHARED=${SD:-${SHARED:-}} SOCOM_TREE=$DT bash "$DEV/tree.sh" --fresh > /dev/null || exit 1
if [ -f "$CACHE/$1/CMakeCache.txt" ]; then  # a reused build dir: drop any fake pad / hook flags
  cmake -S "$DT/port" -B "$CACHE/$1" -DSOCOM_PORT_FAKE_PAD= "-DCMAKE_EXE_LINKER_FLAGS=$SOCOM_BASE_LDFLAGS" \
    > "$CACHE/$1/configure.log" 2>&1 || { tail -20 "$CACHE/$1/configure.log"; exit 1; }
fi
SOCOM_PORT_BUILD=$CACHE/$1 bash "$DT/port/tools/link.sh" 2>&1 | tail -3
grep -E "^SOCOM_PORT_FAKE_PAD|^CMAKE_EXE_LINKER_FLAGS:" "$CACHE/$1/CMakeCache.txt"
ls -la "$CACHE/$1/socom_port.elf"
