#!/bin/bash
# tree.sh [--fresh]: the isolated source tree for your test builds ($TREE, default
# ~/.cache/socom/tree-<name>; see env.sh), so other workers' uncommitted work stays out:
#   1. HEAD's src/ and port/ (git archive; read-only on the checkout); --fresh, or a missing tree,
#      starts over, otherwise only changed files are copied (keeps the build incremental);
#   2. base.txt (optional): files from <scratch>/base/ (a snapshot of another worker's
#      uncommitted files your work builds on);
#   3. copy.txt (or mine.txt when there is no copy.txt): your whole files, copied from the checkout;
#   4. shared.txt ($SHARED overrides): one "<file> <edit file>..." per line for files other
#      workers own: the file is taken from base/ (else HEAD) and gets only your edits
#      (*.rep.txt through rep.py, anything else through srep.py), never the owner's WIP.
# Lists and edit files are read from the scratch folder ($SOCOM_SCRATCH); '#' starts a comment.
# TREE=<name> picks another tree under ~/.cache/socom (e.g. default.sh's tree-<name>-default).
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
H=$SCRATCH
G=(git -C "$REPO" -c safe.directory="$REPO" -c core.autocrlf=false)
list() { [ -f "$1" ] && grep -v '^\s*#' "$1" | tr -d '\r' | awk 'NF'; }
if [ "${1:-}" = "--fresh" ] || [ ! -d "$TREE/src" ]; then
  rm -rf "$TREE"; mkdir -p "$TREE/support"
  "${G[@]}" archive HEAD src port | tar -x -C "$TREE" || { echo "tree.sh: git archive failed in $REPO" >&2; exit 1; }
  echo "tree: $TREE = HEAD $("${G[@]}" rev-parse --short HEAD)"
fi
SF=${SHARED:-$H/shared.txt}
SH=" $(list "$SF" | awk '{print $1}' | tr '\n' ' ') "
for f in $(list "$H/base.txt"); do
  case "$SH" in *" $f "*) continue;; esac
  if ! cmp -s "$H/base/$f" "$TREE/$f"; then mkdir -p "$TREE/$(dirname "$f")"; cp "$H/base/$f" "$TREE/$f"; echo "base: $f"; fi
done
CL=$H/copy.txt; [ -f "$CL" ] || CL=$H/mine.txt
for f in $(list "$CL"); do
  case "$SH" in *" $f "*) continue;; esac
  if ! cmp -s "$REPO/$f" "$TREE/$f"; then mkdir -p "$TREE/$(dirname "$f")"; cp "$REPO/$f" "$TREE/$f"; echo "mine: $f"; fi
done
N=$TREE-shared.tmp
rm -rf "$N"; mkdir -p "$N"
list "$SF" | while read -r f e; do
  mkdir -p "$N/$(dirname "$f")"
  if [ -f "$H/base/$f" ]; then cp "$H/base/$f" "$N/$f"; else "${G[@]}" show "HEAD:$f" > "$N/$f"; fi
  for x in $e; do
    case "$x" in /*) ;; *) x=$H/$x;; esac
    if [ "${x%.rep.txt}" != "$x" ]; then SOCOM_REP_ROOT=$N python3 "$DEV/rep.py" "$x" | grep -v "^ok"
    else python3 "$DEV/srep.py" "$N" "$x" > /dev/null || echo "shared edit FAILED: $f $x"; fi
  done
  if ! cmp -s "$N/$f" "$TREE/$f"; then cp "$N/$f" "$TREE/$f"; echo "shared: $f"; fi
done
rm -rf "$N"
exit 0
