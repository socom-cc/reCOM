"""cz.py [-t reg=Class[,reg=Class...]] < disx-output: compact annotated disassembly for reading.
Drops saved-register prologue/epilogue lines and address columns (labels only on branch targets),
shortens branch/jal operands, prints float values of lui/ori constants, and names DWARF members
for offsets on the given registers (flattened layout from types.pkl). Scratch only."""
import _dev
import sys, re, struct, os, pickle
here = os.path.dirname(os.path.abspath(__file__))
types = _dev.types()
bydie = {}; byname = {}
for t in types:
    ev = t.get('evidence') or {}
    if 'die_offset' in ev: bydie[(t.get('compile_unit_offset'), ev['die_offset'])] = t
    if not t.get('declaration') and t.get('members') is not None and t.get('byte_size'):
        byname.setdefault(t.get('qualified_name'), t)
def off(loc):
    if loc and loc.startswith('04') and loc.endswith('07'):
        return int.from_bytes(bytes.fromhex(loc[2:10]), 'little')
    return None
def flat(name, base=0, pre='', out=None, depth=0):
    if out is None: out = []
    t = byname.get(name)
    if t is None or depth > 6: return out
    cu = t.get('compile_unit_offset')
    for m in t.get('members') or []:
        o = off(m.get('location'))
        if o is None: continue
        ty = m.get('type') or {}
        sub = None
        if not ty.get('modifiers') and ty.get('fund_type') is None:
            st = bydie.get((cu, ty.get('die_offset')))
            if st is not None and st.get('kind') in ('structure_type', 'class_type', 'union_type') :
                sub = st.get('qualified_name')
                if st.get('declaration') or st.get('members') is None: pass
        if m.get('tag') == 'inheritance' or m.get('name') is None:
            if sub: flat(sub, base + o, pre, out, depth + 1)
            continue
        nm = pre + m['name']
        if m.get('bit_size') is not None:
            nm += ':%d@%d' % (m['bit_size'], m['bit_offset'])
        out.append((base + o, nm))
        if sub and sub in byname: flat(sub, base + o, nm + '.', out, depth + 1)
    return out
regs = {}
args = sys.argv[1:]
lines = [l.rstrip(chr(10)) for l in sys.stdin]
if '-t' in args:
    for kv in args[args.index('-t') + 1].split(','):
        r, c = kv.split('=')
        if r.startswith('arg'):
            src = 'a' + r[3:]
            r = src
            for l in lines[:40]:
                mm = re.search(r'\bmove\s+(s\d),' + src + r'\b', l)
                if mm: r = mm.group(1); break
        fl = sorted(set(flat(c)))
        d = {}
        for o, n in fl: d.setdefault(o, []).append(n)
        regs[r] = (c, d, sorted(d))
import bisect
def member(r, o):
    c, d, ks = regs[r]
    i = bisect.bisect_right(ks, o) - 1
    if i < 0: return ''
    k = ks[i]
    names = d[k]
    # prefer deepest (longest path) non-bitfield names
    n = names[-1] if len(names) == 1 else '|'.join(x for x in names[-3:])
    return n if k == o else '%s+0x%x' % (names[-1], o - k)
targets = set()
for l in lines:
    m = re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)', l)
    if m and (m.group(2).startswith('b') or m.group(2) == 'j'):
        t = re.search(r'([0-9a-f]{5,8}) <', m.group(3))
        if t: targets.add(int(t.group(1), 16))
elf = _dev.elf()
e_shoff, = struct.unpack_from('<I', elf, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
def word(a):
    for s_ in secs:
        if s_[1] == 1 and s_[3] <= a < s_[3] + s_[5]:
            return struct.unpack_from('<I', elf, s_[4] + a - s_[3])[0]
    return None
alla = [int(m.group(1), 16) for m in (re.match(r'\s*([0-9a-f]+):', l) for l in lines) if m]
if alla:
    lo, hi_ = min(alla), max(alla)
    for l in lines:
        m = re.search(r'addiu.*;\s*0x(4[0-9a-f]{5})\b', l)
        if m:
            a = int(m.group(1), 16)
            for k in range(64):
                w = word(a + 4 * k)
                if w is None or not (lo <= w <= hi_): break
                targets.add(w)
SAVE = re.compile(r'^(sq|lq|sd|ld|swc1|lwc1)\s+(s[0-7]|ra|fp|\$f2[0-9]|\$f3[01]),-?\d+\(sp\)')
def fl(v):
    f = struct.unpack('<f', struct.pack('<I', v))[0]
    if v == 0: return None
    if 1e-6 < abs(f) < 1e9: return '%.7g' % f
    return None
hi = {}
prevbr = False
strip = set()
P = re.compile(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)')
def isave(l, loads):
    m = P.match(l)
    if not m: return False
    x = m.group(2) + ' ' + m.group(3).split(';')[0].strip()
    if not SAVE.match(x): return False
    return (m.group(2) in ('lq', 'ld', 'lwc1')) == loads
for i, l in enumerate(lines):
    m = P.match(l)
    if m and m.group(2) == 'addiu' and m.group(3).startswith('sp,sp,-'):
        k = i + 1; n = 0
        while k < len(lines) and n < 40:
            if isave(lines[k], False): strip.add(k)
            n += 1; k += 1
            m2 = P.match(lines[k]) if k < len(lines) else None
            if m2 and (m2.group(2).startswith('b') or m2.group(2).startswith('j')): break
    if m and m.group(2) == 'jr' and m.group(3).startswith('ra'):
        k = i - 1
        while k >= 0 and isave(lines[k], True): strip.add(k); k -= 1
for idx, l in enumerate(lines):
    m = re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)', l)
    if not m:
        if l.strip(): print(l)
        continue
    a = int(m.group(1), 16); op = m.group(2); rest = m.group(3)
    note = ''
    if ';' in rest:
        rest, note = rest.split(';', 1); rest = rest.rstrip(); note = note.strip()
    if idx in strip: continue
    rest = re.sub(r'([0-9a-f]{5,8}) <([^>+]+)\+0x[0-9a-f]+>', lambda k: 'L' + k.group(1), rest)
    rest = re.sub(r'[0-9a-f]{5,8} <([^>]+)>', lambda k: k.group(1), rest)
    ops = [x.strip() for x in rest.split(',')]
    if op == 'lui' and len(ops) == 2:
        v = int(ops[1], 0) << 16; hi[ops[0]] = v
        f = fl(v)
        if f and not note: note = f + 'f?'
    elif op == 'ori' and note.startswith('0x'):
        try:
            f = fl(int(note.split()[0], 16))
            if f: note += ' ' + f + 'f'
        except ValueError: pass
    mm = re.search(r'(-?\d+)\((\w+)\)', rest)
    if mm:
        o = int(mm.group(1)); r = mm.group(2)
        if r != 'sp' or True:
            rest = rest.replace(mm.group(0), '%s0x%x(%s)' % ('-' if o < 0 else '', abs(o), r))
        if r in regs and o >= 0:
            n = member(r, o)
            if n: note = (n + ' ' + note).strip()
    lab = ('L%x:' % a) if a in targets else ''
    ds = prevbr
    prevbr = (op.startswith('b') or op in ('j', 'jal', 'jr', 'jalr')) and op not in ('break',)
    if op == 'nop' and not lab: continue
    if len(note) > 60 and '|' in note: note = note.split('|')[0]
    if op == 'nop': print(lab); continue
    print('%-9s%s%s %s%s' % (lab, '| ' if ds else '', op, rest, ('  ; ' + note) if note else ''))
