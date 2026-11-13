#!/bin/bash
# chk.sh <build>...: number of --wrap'ed symbols, build type and fake-pad setting of port builds
# (tells a hook/fake-pad test build from a default one).
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
for b in "$@"; do
  E=$(socom_build_elf "$b"); C=$(dirname "$E")/CMakeCache.txt
  echo "$b: wraps $(mips64r5900el-ps2-elf-nm "$E" | grep -c ' __wrap_')"
  grep -E "^CMAKE_BUILD_TYPE|^SOCOM_PORT_FAKE_PAD" "$C"
done
