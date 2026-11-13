"""dw.py <name>... : compact DWARF layout (first definition) from build/port/dwarf-graph-rows.json (through _dev.types())"""
import _dev
import json, sys, pickle, os
here = os.path.dirname(os.path.abspath(__file__))
types = _dev.types()
bydie = {}
for t in types:
    ev = t.get('evidence') or {}
    if 'die_offset' in ev: bydie[(t.get('compile_unit_offset'), ev['die_offset'])] = t
FT = {1:'char',2:'schar',3:'uchar',4:'short',5:'sshort',6:'ushort',7:'int',8:'sint',9:'uint',10:'long',11:'slong',12:'ulong',13:'ptr',15:'float',16:'dbl',17:'ldbl',20:'void',21:'bool'}
def tname(cu, ty):
    if ty is None: return '?'
    mods = ''.join('*' if m=='pointer_to' else '&' if m=='reference_to' else ' const' if m=='const' else ' '+m for m in ty.get('modifiers', []))
    if ty.get('fund_type') is not None: return FT.get(ty['fund_type'], 'ft%d' % ty['fund_type']) + mods
    t = bydie.get((cu, ty.get('die_offset')))
    if t is None: return 'die%s%s' % (ty.get('die_offset'), mods)
    n = t.get('qualified_name') or t.get('kind')
    if t.get('kind') == 'array_type' and t.get('array'): n = 'array%s' % json.dumps(t['array'])[:80]
    return n + mods
def off(loc):
    if loc and loc.startswith('04') and loc.endswith('07'):
        return int.from_bytes(bytes.fromhex(loc[2:10]), 'little')
    return loc
want = sys.argv[1:]
allf = '-a' in want
want = [w for w in want if w != '-a']
for name in want:
    seen = 0
    for t in types:
        if (t.get('qualified_name') == name or t.get('raw_name') == name) and not t.get('declaration'):
            cu = t.get('compile_unit_offset')
            print('%s size %s (%s)' % (name, t.get('byte_size'), t.get('compile_unit_path')))
            for m in t.get('members') or []:
                o = off(m.get('location'))
                bits = '' if m.get('bit_size') is None else ' :%d@%d' % (m['bit_size'], m['bit_offset'])
                print('  +0x%x %s %s%s' % (o if isinstance(o, int) else -1, m.get('name') or '<' + m.get('tag') + '>', tname(cu, m.get('type')), bits))
            seen += 1
            if not allf: break
    if not seen: print(name, 'not found')
