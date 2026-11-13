"""lay.py <Class> <header> [<header>...]: write <scratch>/lay/<Class>.cpp, a test unit
whose compile errors print the port offset and size of every named DWARF member (bases recursed,
offsets added) and sizeof; laycheck.sh compiles it and tabulates port vs DWARF. Scratch only."""
import _dev
import json, sys, pickle, os, re
here = os.path.dirname(os.path.abspath(__file__))
types = _dev.types()
bydie = {}
byname = {}
for t in types:
    ev = t.get('evidence') or {}
    if 'die_offset' in ev: bydie[(t.get('compile_unit_offset'), ev['die_offset'])] = t
    if not t.get('declaration') and t.get('members') is not None:
        byname.setdefault(t.get('qualified_name'), t)
def off(loc):
    if loc and loc.startswith('04') and loc.endswith('07'):
        return int.from_bytes(bytes.fromhex(loc[2:10]), 'little')
    return None
cls = sys.argv[1]
headers = sys.argv[2:]
out = []
out.append('#define private public\n#define protected public\n#include <cstddef>\n')
for h in headers: out.append('#include "%s"\n' % h)
out.append('#pragma GCC diagnostic ignored "-Winvalid-offsetof"\n')
out.append('template<int I, unsigned O, unsigned S> struct LAY;\n')
rows = []
seen = set()
def walk(t, base, depth, owner):
    cu = t.get('compile_unit_offset')
    for m in t.get('members') or []:
        o = off(m.get('location'))
        if o is None: continue
        if m.get('tag') == 'inheritance':
            ty = m.get('type') or {}
            b = bydie.get((cu, ty.get('die_offset')))
            if b is not None and depth < 6:
                walk(b, base + o, depth + 1, b.get('qualified_name'))
            continue
        n = m.get('name')
        if not n: continue
        bits = m.get('bit_size') is not None
        if n in seen: continue
        seen.add(n)
        rows.append((base + o, n, owner, bits))
t = byname.get(cls)
if t is None:
    sys.exit('no DWARF definition for ' + cls)
walk(t, 0, 0, cls)
for i, (o, n, owner, bits) in enumerate(rows):
    if bits:
        continue
    out.append('LAY<%d, offsetof(%s, %s), sizeof(((%s*)0)->%s)> lay_%d;\n' % (i, cls, n, cls, n, i))
out.append('LAY<-1, 0, sizeof(%s)> lay_size;\n' % cls)
os.makedirs(os.path.join(_dev.scratch(), 'lay'), exist_ok=True)
name = re.sub(r'\W', '_', cls)
open(os.path.join(_dev.scratch(), 'lay', name + '.cpp'), 'w').write(''.join(out))
json.dump({'size': t.get('byte_size'), 'rows': rows}, open(os.path.join(_dev.scratch(), 'lay', name + '.json'), 'w'))
print('lay/%s.cpp: %d members' % (name, len(rows)))
