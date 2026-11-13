"""mem.py <Class> <off>... : DWARF member covering each byte offset (decimal or 0x), bases flattened,
with type and bit position. `mem.py <Class>` alone lists every flattened member. Scratch only."""
import _dev
import pickle, os, sys, json
here = os.path.dirname(os.path.abspath(__file__))
types = _dev.types()
bydie = {}
byname = {}
for t in types:
    ev = t.get('evidence') or {}
    if 'die_offset' in ev: bydie[(t.get('compile_unit_offset'), ev['die_offset'])] = t
    if not t.get('declaration') and t.get('members') is not None:
        byname.setdefault(t.get('qualified_name'), t)
FT = {1:'char',2:'schar',3:'uchar',4:'short',5:'sshort',6:'ushort',7:'int',8:'sint',9:'uint',10:'long',11:'slong',12:'ulong',13:'ptr',15:'float',16:'dbl',17:'ldbl',20:'void',21:'bool'}
def tname(cu, ty):
    if ty is None: return '?'
    mods = ''.join('*' if m=='pointer_to' else '&' if m=='reference_to' else ' const' if m=='const' else ' '+m for m in ty.get('modifiers', []))
    if ty.get('fund_type') is not None: return FT.get(ty['fund_type'], 'ft%d' % ty['fund_type']) + mods
    t = bydie.get((cu, ty.get('die_offset')))
    if t is None: return 'die%s%s' % (ty.get('die_offset'), mods)
    n = t.get('qualified_name') or t.get('kind')
    if t.get('kind') == 'array_type' and t.get('array'): n = 'array%s' % json.dumps(t['array'])[:60]
    return n + mods
def tsize(cu, ty):
    if ty is None: return 0
    if ty.get('modifiers'): return 4
    if ty.get('fund_type') is not None:
        return {1:1,2:1,3:1,4:2,5:2,6:2,7:4,8:4,9:4,10:4,11:4,12:4,13:4,15:4,16:8,17:8,21:1}.get(ty['fund_type'], 4)
    t = bydie.get((cu, ty.get('die_offset')))
    return (t or {}).get('byte_size') or 0
def off(loc):
    if loc and loc.startswith('04') and loc.endswith('07'):
        return int.from_bytes(bytes.fromhex(loc[2:10]), 'little')
    return None
rows = []
def walk(t, base, owner, depth=0):
    cu = t.get('compile_unit_offset')
    for m in t.get('members') or []:
        o = off(m.get('location'))
        if o is None: continue
        if m.get('tag') == 'inheritance':
            b = bydie.get((cu, (m.get('type') or {}).get('die_offset')))
            if b is not None and depth < 8: walk(b, base + o, b.get('qualified_name'), depth + 1)
            continue
        bits = '' if m.get('bit_size') is None else ' :%d@%d' % (m['bit_size'], m['bit_offset'])
        rows.append((base + o, tsize(cu, m.get('type')), m.get('name'), tname(cu, m.get('type')) + bits, owner))
cls = sys.argv[1]
t = byname.get(cls)
if t is None: sys.exit('no DWARF definition for ' + cls)
walk(t, 0, cls)
rows.sort(key=lambda r: r[0])
if len(sys.argv) == 2:
    for r in rows: print('+0x%04x %5d %4d %-28s %-40s %s' % (r[0], r[0], r[1], r[2], r[3][:40], r[4]))
    print('size', t.get('byte_size'))
    sys.exit()
for a in sys.argv[2:]:
    x = int(a, 0)
    hit = [r for r in rows if r[0] <= x < r[0] + max(r[1], 1)]
    if not hit:
        prev = [r for r in rows if r[0] <= x]
        hit = prev[-1:]
    for r in hit:
        print('%5d 0x%04x -> +0x%x %s %s (%s) [%s]%s' % (x, x, r[0], r[2], r[3], r[4], r[1], '' if r[0] == x else ' +%d' % (x - r[0])))
