#!/bin/bash
# hook.sh <build> <pad> <source>... [-- <flag>...]: a fake-pad scratch build of the isolated tree
# ($TREE) plus test-hook sources (port/test-hooks/<feature>/hook_*.cpp|.c, or your own scratch
# files), linked with --wrap. TEST BUILDS ONLY: never use it for a normal build.
#   <build>   build dir ~/.cache/socom/<build>; configured with fake.sh first when it has no
#             CMake cache yet (a hook object in the linker flags breaks CMake's compiler check).
#   <pad>     as fake.sh: pad file, pad script or "-".
#   <source>  .cpp (g++ with the port flags and prefix) or .c (gcc); looked up as given, in the
#             scratch folder, then under port/test-hooks. The include path has the source's
#             folder and port/tools/dev (hook_freecam.h, hook_skipcams.h).
#   --wrap    every __wrap_<sym> an object defines adds -Wl,--wrap=<sym> (so #ifdef'd wraps follow
#             the -D flags); after "--", -D/-I/-f... flags go to the compiler, -Wl,... to the linker
#             (e.g. -Wl,--wrap=<sym> for a wrap defined elsewhere).
# Writes only under ~/.cache/socom.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
[ $# -ge 3 ] || { echo "usage: hook.sh <build> <pad> <source>... [-- <flags>]" >&2; exit 2; }
socom_need_toolchain
BUILD=$1; PADARG=$2; shift 2
SRCS=(); CXF=(); LDX=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do SRCS+=("$1"); shift; done
[ "${1:-}" = "--" ] && shift
for x in "$@"; do case "$x" in -Wl,*) LDX+=("$x");; "") ;; *) CXF+=("$x");; esac; done
B=$CACHE/$BUILD
FILES=(); DIRS=()
for s in "${SRCS[@]}"; do
  f=""
  for c in "$s" "$SCRATCH/$s" "$REPO/port/test-hooks/$s"; do [ -f "$c" ] && { f=$(readlink -f "$c"); break; }; done
  [ -n "$f" ] || { echo "hook.sh: source not found: $s" >&2; exit 1; }
  FILES+=("$f"); DIRS+=("$(dirname "$f")")
done
PAD=$(socom_pad "$PADARG" "${DIRS[@]}")
[ -d "$TREE/port" ] || { echo "hook.sh: no tree at $TREE (run tree.sh first)" >&2; exit 1; }
if [ ! -f "$B/CMakeCache.txt" ]; then
  bash "$DEV/fake.sh" "$BUILD" "${PAD:--}" > "$CACHE/$BUILD.fake.log" 2>&1 || { tail -30 "$CACHE/$BUILD.fake.log"; exit 1; }
fi
OBJS=(); WRAPS=()
for f in "${FILES[@]}"; do
  o=$B/hook-$(basename "${f%.*}").o
  INC="$(socom_incs "$TREE") -I$(dirname "$f") -I$DEV"
  case "$f" in
    *.c) mips64r5900el-ps2-elf-gcc $SOCOM_DEFS -DSOCOM_PORT_TRACE_ON -O2 -G0 $INC "${CXF[@]}" -c "$f" -o "$o" || exit 1 ;;
    *)   mips64r5900el-ps2-elf-g++ $SOCOM_DEFS -DSOCOM_PORT_TRACE_ON $SOCOM_CXXFLAGS $INC "${CXF[@]}" \
           -include "$TREE/port/include/socom_port_prefix.h" -c "$f" -o "$o" || exit 1 ;;
  esac
  OBJS+=("$o")
  WRAPS+=($(mips64r5900el-ps2-elf-nm --defined-only "$o" | awk '$3 ~ /^__wrap_/ {print substr($3, 8)}'))
done
W=""
for s in $(printf '%s\n' "${WRAPS[@]}" | sort -u); do W="$W -Wl,--wrap=$s"; done
echo "hook: ${#OBJS[@]} object(s), wraps:$(printf ' %s' $(printf '%s\n' "${WRAPS[@]}" | sort -u))"
LF="$SOCOM_BASE_LDFLAGS$W ${LDX[*]} ${OBJS[*]}"
cmake -S "$TREE/port" -B "$B" "-DSOCOM_PORT_FAKE_PAD=$PAD" "-DCMAKE_EXE_LINKER_FLAGS=$LF" > "$B/configure.log" 2>&1 \
  || { tail -20 "$B/configure.log"; exit 1; }
grep "TEST HOOK" "$B/configure.log"
rm -f "$B/socom_port.elf"
SOCOM_PORT_BUILD=$B bash "$TREE/port/tools/link.sh"
