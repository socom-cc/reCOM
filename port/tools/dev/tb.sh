#!/bin/bash
# tb.sh [options] <build> <pad> [<test-edit file>...] [-- <hook flag>...]: one test build, start to
# end (merges the per-worker bd.sh / tb.sh / pb.sh / pbx.sh / b*.sh / bc.sh / bv.sh / kb.sh):
#   1. files touched by earlier test edits (<tree>/.touched) are restored from HEAD;
#   2. tree.sh (HEAD + your files + your edits of shared files);
#   3. -d <spec>: diag.py trace insertions; -s: stubcmd.py (traced "return 1" command stubs);
#   4. test edits (srep.py @@@ blocks; *.rep.txt through rep.py), applied to the tree only;
#   5. fake.sh <build> <pad> (configure + link);
#   6. -k <feature|source>: the test hook: a feature folder under port/test-hooks (its build.sh,
#      given <build> <pad> and the hook flags) or a hook source file (hook.sh); repeat -k for
#      several sources. Without -k the result is a fake-pad build without hooks.
# Edit and spec files are looked up as given, then in the scratch folder. Test edits touch only the
# isolated tree, never the checkout. TEST BUILDS ONLY.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
SPEC=""; STUB=""; HOOKS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -d) SPEC=$2; shift 2;; -s) STUB=1; shift;; -k) HOOKS+=("$2"); shift 2;;
    -*) echo "tb.sh: unknown option $1" >&2; exit 2;; *) break;;
  esac
done
[ $# -ge 2 ] || { echo "usage: tb.sh [-d spec] [-s] [-k feature|source]... <build> <pad> [edits...] [-- hook flags]" >&2; exit 2; }
BUILD=$1; PAD=$2; shift 2
PD=(); for k in "${HOOKS[@]}"; do [ -d "$REPO/port/test-hooks/$k" ] && PD+=("$REPO/port/test-hooks/$k"); [ -f "$k" ] && PD+=("$(dirname "$k")"); done
PAD=$(socom_pad "$PAD" "${PD[@]}"); PAD=${PAD:--}
EDITS=(); while [ $# -gt 0 ] && [ "$1" != "--" ]; do EDITS+=("$1"); shift; done
[ "${1:-}" = "--" ] && shift
find_file() { for c in "$1" "$SCRATCH/$1"; do [ -f "$c" ] && { readlink -f "$c"; return; }; done; echo "tb.sh: not found: $1" >&2; exit 1; }
if [ -f "$TREE/.touched" ]; then
  for f in $(sort -u "$TREE/.touched"); do git -C "$REPO" -c safe.directory="$REPO" show "HEAD:$f" > "$TREE/$f"; done
  rm -f "$TREE/.touched"
fi
bash "$DEV/tree.sh" | grep -v "^ok"
[ -n "$SPEC" ] && { python3 "$DEV/diag.py" "$TREE" "$(find_file "$SPEC")" | grep -v "^ok"; }
[ -n "$STUB" ] && python3 "$DEV/stubcmd.py" "$TREE"
for e in "${EDITS[@]}"; do
  e=$(find_file "$e")
  if [ "${e%.rep.txt}" != "$e" ]; then SOCOM_REP_ROOT=$TREE python3 "$DEV/rep.py" "$e" | grep -v "^ok"
  else SREP_TOUCH=1 python3 "$DEV/srep.py" "$TREE" "$e" | grep -v "^ok"; fi
done
bash "$DEV/fake.sh" "$BUILD" "$PAD" > "$CACHE/$BUILD.fake.log" 2>&1 \
  || { grep -E "error|Error" -A3 "$CACHE/$BUILD.fake.log" | head -60; exit 1; }
tail -2 "$CACHE/$BUILD.fake.log"
if [ ${#HOOKS[@]} -gt 0 ]; then
  FEAT=$REPO/port/test-hooks/${HOOKS[0]}
  if [ ${#HOOKS[@]} -eq 1 ] && [ -f "$FEAT/build.sh" ]; then
    bash "$FEAT/build.sh" "$BUILD" "$PAD" "$@" 2>&1 | grep -E "error|undefined|TEST HOOK|hook:|link:|library:" | head -30
  else
    bash "$DEV/hook.sh" "$BUILD" "$PAD" "${HOOKS[@]}" -- "$@" 2>&1 | grep -E "error|undefined|TEST HOOK|hook:|link:|library:" | head -30
  fi
fi
ls -la "$CACHE/$BUILD/socom_port.elf"
