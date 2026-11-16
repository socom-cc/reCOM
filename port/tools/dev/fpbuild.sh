#!/bin/bash
# fpbuild.sh <commit> <name>: "fingerprint" build of a commit's src/ + port/ for auditscan.py:
# the normal port build with inlining, IPA cloning, code folding and tail merging turned off and
# debug line info on (-O2 -g -fno-inline ...), so every fenced function stays one symbol with its
# own calls, and the source line of each symbol maps it back to its fence. Not a test build:
# never booted. Tree ~/.cache/socom/tree-fp-<name> (git archive of <commit>, read-only on the
# checkout), build dir ~/.cache/socom/fp-<name>; writes to $SCRATCH/fp/:
#   <name>.elf  the linked ELF;  <name>.dis  objdump -d -l (mangled names, file:line markers);
#   <name>.syms  mangled <tab> demangled symbol names;  <name>.commit  the full commit id.
# Units that fail to compile at an old commit are reported and left out (lib.log in the build dir).
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
[ $# -ge 2 ] || { echo "usage: fpbuild.sh <commit> <name>" >&2; exit 2; }
socom_need_toolchain
C=$1; N=$2
G=(git -C "$REPO" -c safe.directory="$REPO" -c core.autocrlf=false)
ID=$("${G[@]}" rev-parse --verify "$C^{commit}") || { echo "fpbuild.sh: no commit $C" >&2; exit 1; }
T=$CACHE/tree-fp-$N; B=$CACHE/fp-$N; O=$SCRATCH/fp
mkdir -p "$O"
if [ ! -f "$T/.commit" ] || [ "$(cat "$T/.commit")" != "$ID" ]; then
  S=$T.tmp; rm -rf "$S"; mkdir -p "$S"
  "${G[@]}" archive "$ID" src port | tar -x -m -C "$S" || { echo "fpbuild.sh: git archive failed" >&2; exit 1; }
  mkdir -p "$T"
  for d in src port; do mkdir -p "$T/$d"; rsync -rc --delete "$S/$d/" "$T/$d/"; done
  rm -rf "$S"; echo "$ID" > "$T/.commit"
fi
FP="-O2 -g -DNDEBUG -fno-inline -fno-inline-small-functions -fno-ipa-cp -fno-ipa-sra -fno-ipa-icf \
-fno-partial-inlining -fno-crossjumping -fno-optimize-sibling-calls -fno-tree-loop-distribute-patterns \
-fno-unswitch-loops -fno-peel-loops -fno-tracer -fno-reorder-blocks-and-partition -fno-tree-tail-merge \
-fno-code-hoisting -fno-hoist-adjacent-loads -fno-devirtualize -fno-devirtualize-speculatively"
mkdir -p "$B"
cmake -S "$T/port" -B "$B" -DCMAKE_TOOLCHAIN_FILE="$PS2DEV/share/ps2dev.cmake" -DCMAKE_BUILD_TYPE=Release \
  "-DCMAKE_CXX_FLAGS_RELEASE=$FP" "-DCMAKE_C_FLAGS_RELEASE=$FP" > "$B/configure.log" 2>&1 \
  || { tail -20 "$B/configure.log"; exit 1; }
cmake --build "$B" --target socom_game -j"$(nproc)" -- -k > "$B/lib.log" 2>&1
echo "library: exit=$? failing units: $(grep -oE '[^ /]+\.(cpp|c):[0-9]+:[0-9]+: error' "$B/lib.log" | cut -d: -f1 | sort -u | tr '\n' ' ')"
if [ ! -f "$B/libsocom_game.a" ] || grep -q 'error:' "$B/lib.log"; then
  # an old commit may have a unit that no longer compiles with these flags: archive what built
  find "$B" -name '*.obj' -o -name '*.o' | grep -E 'socom_game.dir' > "$B/objs.txt"
  echo "fpbuild.sh: partial library from $(wc -l < "$B/objs.txt") objects"
  rm -f "$B/libsocom_game.a"; mips64r5900el-ps2-elf-ar rcs "$B/libsocom_game.a" $(cat "$B/objs.txt")
fi
cmake --build "$B" --target socom_port > "$B/link.log" 2>&1 || {
  # link the game objects alone (no entry needed) when the full link fails
  echo "fpbuild.sh: full link failed ($(grep -c 'undefined reference' "$B/link.log") undefined); linking objects with -r"
  mips64r5900el-ps2-elf-ld -r -o "$B/socom_port.elf" --whole-archive "$B/libsocom_game.a" || exit 1
}
cp "$B/socom_port.elf" "$O/$N.elf"
mips64r5900el-ps2-elf-objdump -d -l --no-show-raw-insn -m mips:5900 "$O/$N.elf" > "$O/$N.dis"
mips64r5900el-ps2-elf-nm --defined-only "$O/$N.elf" | awk 'NF == 3 {print $3}' | sort -u > "$O/$N.syms.tmp"
mips64r5900el-ps2-elf-c++filt < "$O/$N.syms.tmp" | paste "$O/$N.syms.tmp" - > "$O/$N.syms"
rm -f "$O/$N.syms.tmp"
echo "$ID" > "$O/$N.commit"
ls -la "$O/$N.elf" "$O/$N.dis"
