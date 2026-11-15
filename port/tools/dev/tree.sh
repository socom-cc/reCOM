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
  # HEAD's src/ and port/ go to a staging copy first and are then synced into the tree by
  # content (rsync -c, no -t): a file whose bytes did not change keeps its time stamp, so a
  # build dir that already built this tree recompiles only what really changed since. (A plain
  # re-extraction gave every file the new commit's time and every build started from scratch.)
  # --delete also removes anything an earlier mine.txt / base / shared edit left behind.
  S=$TREE.head.tmp
  rm -rf "$S"; mkdir -p "$S" "$TREE/support"
  "${G[@]}" archive HEAD src port | tar -x -m -C "$S" || { echo "tree.sh: git archive failed in $REPO" >&2; rm -rf "$S"; exit 1; }
  if command -v rsync >/dev/null 2>&1; then
    for d in src port; do
      mkdir -p "$TREE/$d"
      rsync -rc --delete "$S/$d/" "$TREE/$d/" || { echo "tree.sh: rsync failed" >&2; rm -rf "$S"; exit 1; }
    done
  else
    rm -rf "$TREE/src" "$TREE/port"; mv "$S/src" "$S/port" "$TREE/"
  fi
  rm -rf "$S"
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
# Check: every file of copy.txt / mine.txt that is not a shared-edit file must now be identical
# to the checkout's. A tree without your files builds HEAD and tests nothing of yours.
BAD=0
for f in $(list "$CL"); do
  case "$SH" in *" $f "*) continue;; esac
  [ -e "$REPO/$f" ] || { echo "tree.sh: listed but not in the checkout: $f" >&2; continue; }
  if ! cmp -s "$REPO/$f" "$TREE/$f"; then echo "tree.sh: NOT IN THE TREE: $f" >&2; BAD=1; fi
done
[ "$BAD" = 0 ] || { echo "tree.sh: the tree does not hold your files; run it again and do not build from this tree" >&2; exit 1; }
exit 0
