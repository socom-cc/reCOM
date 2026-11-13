#!/bin/bash
# laycheck.sh [-a] <name>...: compile <scratch>/lay/<name>.cpp (written by lay.py) -fsyntax-only
# with the port flags against the isolated tree ($TREE, else the checkout) and tabulate each DWARF
# member: DWARF offset/size vs port offset/size. Rows whose DWARF size (distance to the next
# member) differs from the port's (#), or whose shift changes (*), are marked; -a prints every
# row. Several names run one after another (was layall.sh).
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
ALL=""; [ "${1:-}" = "-a" ] && { ALL=-a; shift; }
R=$TREE; [ -d "$R/src" ] || R=$REPO
L=$SCRATCH/lay
for n in "$@"; do
[ $# -gt 1 ] && echo "== $n"
mips64r5900el-ps2-elf-g++ -fsyntax-only -fmax-errors=0 $SOCOM_DEFS $SOCOM_CXXFLAGS \
  $(socom_incs "$R") -include "$R/port/include/socom_port_prefix.h" "$L/$n.cpp" > "$L/$n.log" 2>&1
python3 - "$L/$n.log" "$L/$n.json" "$ALL" "$R/" <<'PY'
import re, sys, json
t = open(sys.argv[1]).read()
d = json.load(open(sys.argv[2]))
allrows = sys.argv[3] == '-a'
got = {}
for i, o, s in re.findall(r"'LAY<(-?\d+), (\d+), (\d+)> lay_", t):
    got[int(i)] = (int(o), int(s))
rows = d['rows']
prev = None
for i, (o, n, owner, bits) in enumerate(rows):
    nxt = rows[i + 1][0] if i + 1 < len(rows) else d['size']
    dsz = nxt - o
    if bits:
        if allrows: print('  0x%04x      %-34s (bitfield)' % (o, n))
        continue
    if i not in got:
        print('! 0x%04x %4d %-34s MISSING in port (%s)' % (o, dsz, n, owner))
        continue
    po, ps = got[i]
    shift = po - o
    mark = ' '
    if prev is not None and shift != prev: mark = '*'
    if ps != dsz and not (ps < dsz and dsz - ps < 16): mark = '#'
    if mark != ' ' or allrows:
        print('%s 0x%04x %4d  port 0x%04x %4d  shift %+5d  %s' % (mark, o, dsz, po, ps, shift, n))
    prev = shift
if -1 in got: print('  sizeof dwarf 0x%x port 0x%x' % (d['size'], got[-1][1]))
other = [l for l in t.split('\n') if 'error' in l and 'LAY<' not in l and 'incomplete type' not in l]
for l in other[:25]: print(l.replace(sys.argv[4], ''))
PY
done
