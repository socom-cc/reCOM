"""cz.py [-t reg=Class[,reg=Class...]] [-k] < disx-output: compact annotated disassembly for reading.
Drops saved-register prologue/epilogue lines and address columns (labels only on branch targets),
shortens branch/jal operands, prints float values of lui/ori constants, and names DWARF members
for offsets on the given registers (flattened layout from types.pkl). Scratch only.
-k (the audit packets): keeps every branch target's label (also on a dropped save-register line),
prints a nop in a delay slot as '| nop', and names members only while the register still holds
the typed value (argN from the start, copied by move, dropped when overwritten or by a call).
-a (with -k): the address first on every listed line, so an address can be read, not counted
(dropped save-register lines and nops outside delay slots leave a gap); a labelled nop or save
line is listed. Also with -k: bitfields are named by their bits within the accessed byte / half /
word (DWARF bit_offset counts from the unit's lowest bit), narrowed by the mask the code applies;
a pointer member loaded from a typed register types the loaded register (Class:: is then said);
-r <hex call address>=<Class>,... types v0 after those calls; -p <layouts.json> (portlay.sh)
adds the port's own member where it has none of DWARF's name or other bits, `port:` names
for a class DWARF lacks."""
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
FSIZE = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2, 21: 1, 16: 8, 17: 8}
def flat(name, base=0, pre='', out=None, depth=0, bits=None):
    """[(offset, member path)] of a class, bases flattened; with bits (a list) the bitfields are
    also collected there as (unit offset, unit bytes, lowest bit, width, path): DWARF bit_offset
    counts from the unit's lowest bit (checked: CEntity m_isAlive :1@11 is bit 3 of +0xdd)."""
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
            if sub: flat(sub, base + o, pre, out, depth + 1, bits)
            continue
        nm = pre + m['name']
        if m.get('bit_size') is not None:
            if bits is not None:
                us = m.get('byte_size') or FSIZE.get(ty.get('fund_type'), 4)
                if ty.get('fund_type') is None and not ty.get('modifiers'):
                    st = bydie.get((cu, ty.get('die_offset')))
                    us = m.get('byte_size') or (st or {}).get('byte_size') or 4
                bits.append((base + o, us, m['bit_offset'], m['bit_size'], nm))
            nm += ':%d@%d' % (m['bit_size'], m['bit_offset'])
        out.append((base + o, nm))
        if sub and sub in byname: flat(sub, base + o, nm + '.', out, depth + 1, bits)
    return out
regs = {}
args = sys.argv[1:]
KEEP = '-k' in args
lines = [l.rstrip(chr(10)) for l in sys.stdin]
ctab = {}; init = {}; btab = {}; rtypes = {}
class _Tabs(dict):
    def __missing__(self, c):
        bl_ = []
        fl_ = sorted(set(x for x in flat(c, bits=bl_) if ':' not in x[1].split('.')[-1]))
        d = {}
        for o, n in fl_: d.setdefault(o, []).append(n)
        btab[c] = bl_
        self[c] = (c, d, sorted(d))
        return self[c]
ptrs = {}
def flat_ptr(name, base=0, out=None, depth=0):
    """{offset: class} of the members of a class that point to a class (bases and member
    structures flattened)."""
    if out is None: out = {}
    t = byname.get(name)
    if t is None or depth > 6: return out
    cu = t.get('compile_unit_offset')
    for m in t.get('members') or []:
        o = off(m.get('location'))
        ty = m.get('type') or {}
        if o is None or ty.get('fund_type') is not None: continue
        st = bydie.get((cu, ty.get('die_offset')))
        if st is None or st.get('kind') not in ('structure_type', 'class_type', 'union_type'): continue
        mods = ty.get('modifiers') or []
        if not mods:
            flat_ptr(st.get('qualified_name'), base + o, out, depth + 1)
        elif mods == ['pointer_to'] and st.get('qualified_name'):
            out.setdefault(base + o, st.get('qualified_name'))
    return out
def load_type(c, o):
    if c not in ptrs: ptrs[c] = flat_ptr(c)
    return ptrs[c].get(o)
if KEEP:
    ctab = _Tabs()
if '-t' in args and KEEP:
    for kv in args[args.index('-t') + 1].split(','):
        r, c = kv.split('=')
        r = 'a' + r[3:] if r.startswith('arg') else r
        init[r] = c
if '-r' in args and KEEP:
    # -r <hex address of a call>=<Class>[,...]: the call returns a pointer to Class in v0
    for kv in args[args.index('-r') + 1].split(','):
        a_, c = kv.split('=')
        rtypes[int(a_, 16)] = c
if '-t' in args and not KEEP:
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
PLAY = None
if KEEP and '-p' in args:
    import json
    try:
        PLAY = json.load(open(args[args.index('-p') + 1]))
    except (OSError, ValueError):
        PLAY = None
ptab = {}
def port_tab(c):
    """(plain table, bitfield list, {member: (offset, lowest bit, width)}) of the port's own
    layout of c (portlay.sh), bases flattened; None when the port build has no such class."""
    if c in ptab: return ptab[c]
    res = None
    if PLAY and c in PLAY:
        rows = []
        def walk(q, base, depth):
            e = PLAY.get(q)
            if not e or depth > 8: return
            for o, b in e[2]: walk(b, base + o, depth + 1)
            for o, n, lsb, w in e[1]: rows.append((base + o, n, lsb, w))
        walk(c, 0, 0)
        d = {}; bl = []; pos = {}
        for o, n, lsb, w in rows:
            if w: bl.append((o, 4, lsb, w, n))
            else: d.setdefault(o, []).append(n)
            pos.setdefault(n, (o, lsb, w))
        res = ((c, d, sorted(d)), bl, pos)
    ptab[c] = res
    return res
dtop = {}
def dwarf_top(c):
    """[(offset, top-level member)] of DWARF's layout of c, bases flattened, and {bitfield: (unit, lowest bit)}."""
    if c not in dtop:
        bl = []
        tops = sorted(set((o, n.split(':')[0]) for o, n in flat(c, bits=bl) if '.' not in n))
        dtop[c] = (tops, {nm: (u, lsb) for u, us, lsb, w, nm in bl if '.' not in nm})
    return dtop[c]
WORD = re.compile(r'[A-Za-z_]\w*(?:\.\w+)*')
def keep_note(c, o, op, ops, idx):
    """The member note of an access at +o through a register of class c: DWARF's member (bitfields
    by their bits); then the port's own member there, from the port build's layout, when the
    port has no member of DWARF's name (placed by the nearest member both name) or puts a
    bitfield at other bits; the port's alone for a class DWARF lacks."""
    tab = ctab[c]
    dn = bitnote(btab.get(c, ()), o, op, ops, idx) or member(None, o, tab)
    P = port_tab(c)
    if not P: return dn
    pt, pb, pos = P
    tops, dbits = dwarf_top(c)
    if not tops:
        pn = bitnote(pb, o, op, ops, idx) or member(None, o, pt)
        return 'port: %s' % pn if pn else ''
    if not dn: return dn
    names = [x.split('.')[0] for x in WORD.findall(re.sub(r'\+0x[0-9a-f]+', '', dn)) if x not in ('bit', 'bits', 'more')]
    got = [n for n in names if n in pos]
    if got:
        diff = []
        for n in got:
            if n in dbits and pos[n][2] and pos[n][1] != dbits[n][1] % 32 + (dbits[n][0] % 4) * 8:
                diff.append('%s at bit %d of +0x%x' % (n, pos[n][1], pos[n][0]))
        return dn + (' [port: %s]' % ', '.join(diff) if diff else '')
    prev = [(k, n) for k, n in tops if k <= o and n in pos]
    if not prev: return dn
    k, n = prev[-1]
    po = pos[n][0] + (o - k)
    pn = bitnote(pb, po, op, ops, idx) or member(None, po, pt)
    return '%s [port +0x%x: %s]' % (dn, po, pn) if pn else dn
def member(r, o, tab=None):
    c, d, ks = tab or regs[r]
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
    # nine significant digits: the fewest that always parse back to the same 32-bit float
    # (seven did not: constants copied from this output came out one or more ulps off)
    if 1e-6 < abs(f) < 1e9: return '%.9g' % f
    return None
hi = {}
prevbr = False
strip = set()
typed = {}
if KEEP and (init or rtypes):
    sys.path.insert(0, here)
    import auditlib
    seq = []; at = []; after = {}
    for i_, l_ in enumerate(lines):
        m_ = re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)', l_)
        if m_:
            if int(m_.group(1), 16) in rtypes: after[len(seq)] = {'v0': rtypes[int(m_.group(1), 16)]}
            seq.append((m_.group(2), [x.strip() for x in m_.group(3).split(';')[0].split('#')[0].split(',')] if m_.group(3).strip() else []))
            at.append(i_)
    for i_, st in zip(at, auditlib.reg_types(seq, init, after, load_type)):
        typed[i_] = st
P = re.compile(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)')
ASZ = {'lb': 1, 'lbu': 1, 'sb': 1, 'lh': 2, 'lhu': 2, 'sh': 2, 'lw': 4, 'sw': 4, 'lwl': 4, 'lwr': 4,
       'swl': 4, 'swr': 4, 'ld': 8, 'sd': 8, 'lwu': 4}
def insn(k):
    m = P.match(lines[k]) if 0 <= k < len(lines) else None
    if not m: return None, []
    return m.group(2), [x.strip() for x in m.group(3).split(';')[0].split('#')[0].split(',') if x.strip()]
def _bitset(v):
    return set(i for i in range(64) if v >> i & 1)
def li_value(reg, k0):
    """The constant a register was last set to before line k0 (li / addiu / ori from zero), or None."""
    for k in range(k0 - 1, max(-1, k0 - 16), -1):
        o, a = insn(k)
        if not a or a[0] != reg or o is None or o.startswith(('s', 'b', 'j')) and o not in ('sll', 'srl', 'sra', 'sltu', 'slt'):
            continue
        try:
            if o == 'li' and len(a) == 2: return int(a[1], 0)
            if o in ('addiu', 'ori', 'daddiu') and len(a) == 3 and a[1] == 'zero': return int(a[2], 0)
        except ValueError:
            return None
        return None
    return None
def access_bits(idx, op, ops, n):
    """The bits of a bitfield access (relative to the accessed value's bit 0) that the code tests
    or changes: a load's later andi / and with a constant / shift pair / sign test while the
    register holds the value; a store's clear mask (and / andi with a mostly-set constant) or set
    bits (ori) along the stored register's writers; None when not seen."""
    W = 8 * n
    full = (1 << W) - 1
    def mask_bits(m, k):
        m &= full
        if bin(m).count('1') * 2 > W: return _bitset(~m & full)    # a clear mask: the field written
        return _bitset(m)
    if op.startswith('l'):
        r = ops[0]
        for k in range(idx + 1, min(len(lines), idx + 14)):
            o2, a2 = insn(k)
            if o2 is None: continue
            if len(a2) == 3 and r in a2[1:]:
                try: imm = int(a2[2], 0) if a2[1] == r else None
                except ValueError: imm = None
                if o2 == 'andi' and imm is not None: return _bitset(imm)
                if o2 == 'and':
                    m = li_value(a2[2] if a2[1] == r else a2[1], k)
                    if m is not None: return mask_bits(m, k)
                if imm is not None and o2 in ('sll', 'dsll', 'dsll32', 'srl', 'dsrl', 'dsrl32'):
                    left = o2.endswith('ll') or o2.endswith('ll32')
                    s = imm + (32 if o2.endswith('32') else 0); Wr = 32 if o2 in ('sll', 'srl') else 64
                    x = a2[0]
                    for k2 in range(k + 1, min(len(lines), k + 4)):
                        o3, a3 = insn(k2)
                        if o3 is None: continue
                        if left and o3 in ('srl', 'sra', 'dsrl', 'dsra', 'dsrl32', 'dsra32') and len(a3) == 3 and a3[1] == x:
                            t = int(a3[2], 0) + (32 if o3.endswith('32') else 0)
                            Wt = 32 if o3 in ('srl', 'sra') else 64
                            w = Wt - t; lsb = Wr - s - w
                            return set(range(lsb, lsb + w)) if w > 0 and lsb >= 0 else None
                        if left and o3 in ('bltz', 'bgez', 'bltzl', 'bgezl') and a3 and a3[0] == x:
                            return {Wr - 1 - s}
                        if not left and o3 == 'andi' and len(a3) == 3 and a3[1] == x:
                            return set(b + s for b in _bitset(int(a3[2], 0)))
                        if a3 and a3[0] == x: break
                    return set(range(s, W)) if not left else None
                if o2 in ('or', 'ori', 'xori', 'xor'): continue
                return None
            if a2 and a2[0] == r and not o2.startswith(('s', 'b', 'j')): return None
        return None
    reg, setb = ops[0], set()
    for k in range(idx - 1, max(-1, idx - 16), -1):
        o2, a2 = insn(k)
        if o2 is None or not a2 or a2[0] != reg or o2.startswith(('s', 'b', 'j')) and not o2.startswith(('sll', 'srl', 'sra')):
            continue
        try:
            if o2 == 'ori' and len(a2) == 3:
                setb |= _bitset(int(a2[2], 0) & full); reg = a2[1]; continue
            if o2 == 'andi' and len(a2) == 3:
                m = int(a2[2], 0) & full
                if bin(m).count('1') * 2 > W: return _bitset(~m & full)
                break
            if o2 == 'and' and len(a2) == 3:
                for x, y in ((a2[2], a2[1]), (a2[1], a2[2])):
                    m = li_value(x, k)
                    if m is not None: return mask_bits(m, k)
                break
            if o2 == 'or' and len(a2) == 3:
                # one side is the cleared old value (and / andi), follow it
                for x in (a2[1], a2[2]):
                    for k2 in range(k - 1, max(-1, k - 12), -1):
                        o3, a3 = insn(k2)
                        if a3 and a3[0] == x and o3 is not None and not o3.startswith(('s', 'b', 'j')):
                            if o3 in ('and', 'andi'):
                                reg = x
                            break
                    if reg == x: break
                if reg in (a2[1], a2[2]): continue
                break
        except ValueError:
            return None
        break
    return setb or None
def bitnote(bl, o, op, ops, idx):
    """The bitfields of bl (flat(bits=)) an access at +o touches, with their bit numbers in the accessed
    byte / half / word."""
    n = ASZ.get(op)
    if not n: return ''
    fs = []
    for u, us, lsb, w, nm in bl:
        if u <= o < u + us or o <= u < o + n:
            st = (u - o) * 8 + lsb
            if st + w > 0 and st < 8 * n:
                fs.append((max(st, 0), min(st + w, 8 * n) - 1, nm))
    if not fs: return ''
    bits = access_bits(idx, op, ops, n)
    hit = [f for f in fs if bits and any(f[0] <= b <= f[1] for b in bits)]
    sp = lambda f: 'bit %d' % f[0] if f[0] == f[1] else 'bits %d-%d' % (f[0], f[1])
    if hit:
        return ', '.join('%s (%s)' % (f[2], sp(f)) for f in hit[:4]) + (' +%d' % (len(hit) - 4) if len(hit) > 4 else '')
    fs.sort()
    return 'bits: ' + ', '.join('%s %s' % (f[0] if f[0] == f[1] else '%d-%d' % (f[0], f[1]), f[2]) for f in fs[:8]) + \
        (' +%d more' % (len(fs) - 8) if len(fs) > 8 else '')
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
ADDR = '-a' in args and KEEP
_print = print
def print(s=''):
    # -a: every listed line starts with its address (dropped lines leave a visible gap)
    if ADDR and s.strip():
        s = '%6x %s' % (cur_a, s)
    _print(s.rstrip() if ADDR else s)
cur_a = 0
for idx, l in enumerate(lines):
    m = re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)', l)
    if not m:
        if l.strip(): _print(l)
        continue
    a = int(m.group(1), 16); op = m.group(2); rest = m.group(3)
    cur_a = a
    note = ''
    if ';' in rest:
        rest, note = rest.split(';', 1); rest = rest.rstrip(); note = note.strip()
    if idx in strip and not (KEEP and prevbr) and not (ADDR and a in targets):
        # -k: a save-register line in a delay slot stays; -a: a labelled one too
        if KEEP and a in targets: print('L%x:' % a)
        continue
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
        if KEEP:
            c_ = typed.get(idx, {}).get(r)
            if c_ and o >= 0:
                n = keep_note(c_, o, op, ops, idx)
                if n and c_ not in init.values():
                    # a register typed by a pointer member or a call's result: say the class
                    n = '%s%s%s' % (c_.split('::')[-1], ' ' if n.startswith(('port', 'bits:')) else '::', n)
                if n: note = (n + ' ' + note).strip()
        elif r in regs and o >= 0:
            n = member(r, o)
            if n: note = (n + ' ' + note).strip()
    lab = ('L%x:' % a) if a in targets else ''
    ds = prevbr
    prevbr = (op.startswith('b') or op in ('j', 'jal', 'jr', 'jalr')) and op not in ('break',)
    if KEEP and op == 'nop':
        if ADDR and (lab or ds): print('%-9s%snop' % (lab, '| ' if ds else ''))
        elif lab or ds: print(('%-9s%s' % (lab, '| nop' if ds else '')).rstrip())
        continue
    if op == 'nop' and not lab: continue
    if len(note) > 60 and '|' in note: note = note.split('|')[0]
    if op == 'nop': print(lab); continue
    print('%-9s%s%s %s%s' % (lab, '| ' if ds else '', op, rest, ('  ; ' + note) if note else ''))
