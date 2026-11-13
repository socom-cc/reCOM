# env.sh: sourced by the port/tools/dev Linux-side scripts (bash in WSL or Linux). Sets:
#   DEV      this folder;  REPO  the checkout root (derived from this file's location)
#   SCRATCH  your scratch folder: $SOCOM_SCRATCH (Linux path, Windows path or repo-relative),
#            default $REPO/build/port/dev (build/ is ignored by git)
#   NAME     short worker name: $SOCOM_NAME, default the scratch folder's name without "boot-"
#   CACHE    $HOME/.cache/socom (isolated trees and build dirs live here, on the Linux side)
#   TREE     isolated source tree: $SOCOM_TREE, else $CACHE/<$TREE or tree-$NAME>
#   ELF      reference ELF: $SOCOM_ELF, default $REPO/support/socom.elf
#   PS2DEV, PS2SDK, PATH for the pinned toolchain ($SOCOM_PS2DEV, default
#            $HOME/.local/share/socom/ps2dev-v2.0.0, as tools/_socom/port_toolchain.py)
# Helpers: socom_lpath <path> (to a Linux path), socom_need_elf, socom_pad <file|script|->.
socom_lpath() {
  case "$1" in
    [A-Za-z]:[\\/]*)
      if command -v wslpath >/dev/null 2>&1; then wslpath -u "$1"
      elif command -v cygpath >/dev/null 2>&1; then cygpath -u "$1"
      else echo "$1"; fi ;;
    /*) echo "$1" ;;
    "~"|"~/"*) echo "$HOME${1#\~}" ;;
    *) local p=${1//\\//}; echo "$REPO/${p#./}" ;;
  esac
}
DEV=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
REPO=$(cd "$DEV/../../.." && pwd)
SCRATCH=$(socom_lpath "${SOCOM_SCRATCH:-build/port/dev}")
NAME=${SOCOM_NAME:-$(basename "$SCRATCH")}
NAME=${NAME#boot-}
CACHE=$HOME/.cache/socom
if [ -n "${SOCOM_TREE:-}" ]; then TREE=$(socom_lpath "$SOCOM_TREE"); else TREE=$CACHE/${TREE:-tree-$NAME}; fi
ELF=$(socom_lpath "${SOCOM_ELF:-support/socom.elf}")
PS2DEV=${SOCOM_PS2DEV:-$HOME/.local/share/socom/ps2dev-v2.0.0}
case "$PS2DEV" in "~"/*) PS2DEV=$HOME/${PS2DEV#\~/} ;; esac
export PS2DEV PS2SDK=$PS2DEV/ps2sdk
export PATH=$PS2DEV/bin:$PS2DEV/ee/bin:$PS2DEV/iop/bin:$PS2DEV/dvp/bin:$PS2DEV/ps2sdk/bin:/usr/bin:/bin
# Port compile flags shared by the hook, layout and syntax-check scripts.
SOCOM_DEFS="-DSOCOM_PORT -D_EE -DPS2 -D__PS2__"
SOCOM_CXXFLAGS="-O2 -G0 -std=gnu++17 -fno-exceptions -Wno-changes-meaning"
socom_incs() {  # socom_incs <tree>
  echo "-I$1/src -I$1/port/compat/include -I$PS2SDK/ee/include -I$PS2SDK/common/include -I$PS2SDK/ports/include"
}
# The default linker flags of the port build (ps2dev.cmake); hook builds append wraps and objects.
SOCOM_BASE_LDFLAGS="-L$PS2SDK/ee/lib -L$PS2DEV/gsKit/lib -L$PS2SDK/ports/lib -Wl,-zmax-page-size=128 -T$PS2SDK/ee/startup/linkfile"
socom_need_elf() {
  [ -f "$ELF" ] || { echo "reference ELF not found: $ELF (put it at support/socom.elf or set SOCOM_ELF)" >&2; exit 1; }
}
socom_need_toolchain() {
  [ -x "$PS2DEV/ee/bin/mips64r5900el-ps2-elf-g++" ] || {
    echo "ps2dev toolchain not found at $PS2DEV (python tools/socom.py port toolchain bootstrap, or set SOCOM_PS2DEV)" >&2; exit 1; }
}
# socom_pad <arg> [dir...]: pad script text from a file (as given, in each dir, in $SCRATCH, in
# $REPO/port/test-hooks and its common/), "-" or "" = no fake pad, else the argument itself.
socom_pad() {
  local a=${1:-} d f; shift
  if [ -z "$a" ] || [ "$a" = "-" ]; then echo ""; return; fi
  for f in "$a" $(for d in "$@"; do echo "$d/$a"; done) "$SCRATCH/$a" "$REPO/port/test-hooks/$a" "$REPO/port/test-hooks/common/$a"; do
    if [ -f "$f" ]; then tr -d '\r' < "$f" | tr '\n' ',' | sed -e 's/,,*/,/g' -e 's/^,//' -e 's/,$//'; return; fi
  done
  echo "$a"
}
# socom_build_elf <build>: the port ELF of a build: $CACHE/<build>/socom_port.elf, or a given
# build dir / ELF path.
socom_build_elf() {
  local b=$1
  if [ -f "$b" ]; then echo "$b"; elif [ -d "$b" ]; then echo "$b/socom_port.elf"; else echo "$CACHE/$b/socom_port.elf"; fi
}
