#!/bin/bash
# ccm.sh [-r] <src-relative files...>: -fsyntax-only compile of src/ units with the port flags,
# errors (and missing-return warnings) only, first $N (default 12) lines per file. Compiles the
# isolated tree ($TREE, see tree.sh) when it exists, else the checkout; -r forces the checkout.
# Merged cc.sh.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
R=$TREE
if [ "${1:-}" = "-r" ] || [ ! -d "$TREE/src" ]; then R=$REPO; [ "${1:-}" = "-r" ] && shift; fi
for f in "$@"; do
  f=${f#src/}
  mips64r5900el-ps2-elf-g++ -fsyntax-only $SOCOM_DEFS -DSOCOM_PORT_TRACE_ON $SOCOM_CXXFLAGS -fsanitize=return \
    $(socom_incs "$R") -include "$R/port/include/socom_port_prefix.h" "$R/src/$f" 2>&1 \
    | grep -E "error|warning: no return" | sed "s#$R/##" | head -n "${N:-12}"
done
echo "ccm done ($R)"
