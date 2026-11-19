#!/bin/bash
# Entry point of the port build image (port/docker/Dockerfile): configure and build the
# functional port from the repository mounted at $SOCOM_SRC, in $SOCOM_PORT_BUILD, and copy the
# ELF to $SOCOM_OUT (default: <repository>/build/port/docker). Arguments go to the CMake
# configure step (for example -DSOCOM_PORT_HEAP_SHRINK_TEXLIST=ON) and are remembered by the build
# directory; "--fresh" as the first argument forgets them. The same commands as
# port/tools/link.sh.
set -eu
SRC=${SOCOM_SRC:-/src}
B=${SOCOM_PORT_BUILD:-/build}
OUT=${SOCOM_OUT:-$SRC/build/port/docker}
export PS2DEV=${SOCOM_PS2DEV:?SOCOM_PS2DEV is not set}
export PS2SDK=$PS2DEV/ps2sdk
export PATH=$PS2DEV/bin:$PS2DEV/ee/bin:$PS2DEV/iop/bin:$PS2DEV/dvp/bin:$PS2SDK/bin:/usr/bin:/bin

[ -f "$SRC/port/CMakeLists.txt" ] || { echo "build-port: no repository at $SRC (mount the checkout there: -v <checkout>:$SRC)" >&2; exit 2; }
if [ "${1:-}" = "--fresh" ]; then shift; rm -rf "$B/CMakeCache.txt" "$B/CMakeFiles"; fi
mkdir -p "$B"
# Configure on every run: it is quick when nothing changed, it applies options given on this
# run, and it repairs a build directory whose first configure was cut short (a cache without a
# Makefile, as a failed first attempt leaves behind).
cmake -S "$SRC/port" -B "$B" -DCMAKE_TOOLCHAIN_FILE="$PS2DEV/share/ps2dev.cmake" -DCMAKE_BUILD_TYPE=Release "$@"
cmake --build "$B" --target socom_port -j"$(nproc)"
mkdir -p "$OUT"
cp "$B/socom_port.elf" "$OUT/socom_port.elf"
echo "build-port: $(sha256sum "$OUT/socom_port.elf" | cut -c1-16)  $(stat -c %s "$OUT/socom_port.elf") bytes  $OUT/socom_port.elf"
