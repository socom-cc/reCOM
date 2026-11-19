"""disx.py [-f]: annotate objdump output (stdin) with lui/addiu and $gp-relative symbols and strings from support/socom.elf.
-f (the audit packets): follow the branches: the lui values reaching a branch target are those of
every path to it (taken branches after their delay slot, the fall-through unless the line before is
an unconditional jump's delay slot); a register whose paths disagree is not resolved there, and a
call clobbers the argument and temporary registers. Without -f the last lui in listing order is used."""
import _dev
import sys, re, struct, os
here = os.path.dirname(os.path.abspath(__file__))
elf = _dev.elf()
e_shoff, = struct.unpack_from('<I', elf, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
syms = {}
GPV = []
for s in secs:
    if s[1] == 2:
        strtab = secs[s[6]]
        for i in range(s[5] // 16):
            nm, val, sz, info, oth, shn = struct.unpack_from('<IIIBBH', elf, s[4] + i * 16)
            n = elf[strtab[4] + nm: elf.index(b'\0', strtab[4] + nm)].decode('latin1')
            if n == '_gp': GPV.append(val)
            if n and val: syms.setdefault(val, n)
GP = GPV[0] if GPV else 0
import bisect
addrs = sorted(syms)
def cstr(a):
    for s in secs:
        if s[1] == 1 and s[3] <= a < s[3] + s[5] and a >= 0x400000:
            o = s[4] + a - s[3]
            e = elf.find(b'\0', o)
            b = elf[o:e]
            if 2 <= len(b) < 200 and all(32 <= c < 127 or c in (9, 10) for c in b):
                return b.decode('latin1')
    return None
def word(a):
    for s in secs:
        if s[1] == 1 and s[3] <= a < s[3] + s[5]:
            return struct.unpack_from('<I', elf, s[4] + a - s[3])[0]
def desc(a, isload=False):
    if a in syms:
        r = syms[a]
    else:
        i = bisect.bisect_right(addrs, a) - 1
        r = '%s+0x%x' % (syms[addrs[i]], a - addrs[i]) if i >= 0 and a - addrs[i] < 0x2000 else ''
    s = cstr(a)
    if s is not None and FLOW and a in syms and not syms[a].startswith('@') and len(s) < 4: s = None  # a variable's bytes
    if s is not None and not a in syms: r = (r + ' ' if r else '') + repr(s)
    elif s is not None: r += ' ' + repr(s)
    return '0x%x %s' % (a, r)
FLOW = '-f' in sys.argv[1:]
LINE = re.compile(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)')
def annot(hi, op, a, flow=False):
    """The note of one instruction (operands a) from the lui values hi, which it updates."""
    note = ''
    if op == 'lui' and len(a) == 2:
        hi[a[0]] = int(a[1], 0) << 16
        return note
    if op in ('addiu', 'daddiu') and len(a) == 3:
        imm = int(a[2], 0)
        if a[1] == 'gp': note = desc((GP + imm) & 0xffffffff)
        elif a[1] in hi: note = desc((hi[a[1]] + imm) & 0xffffffff)
        if a[0] in hi and a[0] != a[1]: hi.pop(a[0], None)
        elif a[0] == a[1]: hi.pop(a[0], None)
    elif op == 'ori' and len(a) == 3 and a[1] in hi:
        note = '0x%x' % (hi[a[1]] | int(a[2], 0))
        if flow: hi.pop(a[0], None)
    else:
        mm = re.match(r'(-?\w+)\((\w+)\)', a[-1]) if a else None
        if mm:
            imm = int(mm.group(1), 0)
            if mm.group(2) == 'gp': note = desc((GP + imm) & 0xffffffff)
            elif mm.group(2) in hi: note = desc((hi[mm.group(2)] + imm) & 0xffffffff)
        if flow:
            if a and op not in NOWRITE and not op.startswith('b'): hi.pop(a[0], None)
        elif a and op not in ('sw', 'sd', 'sq', 'sb', 'sh', 'swc1', 'sqc2', 'jr', 'jalr') and not op.startswith('b') and a[0] in hi:
            hi.pop(a[0], None)
    return note
NOWRITE = {'sw', 'sd', 'sq', 'sb', 'sh', 'swc1', 'sqc2', 'swl', 'swr', 'sdl', 'sdr', 'jr', 'jalr', 'jal', 'j',
           'mtc1', 'ctc1', 'dmtc1', 'qmtc2', 'ctc2', 'mthi', 'mtlo', 'mthi1', 'mtlo1', 'mtsa', 'mtsab', 'mtsah',
           'teq', 'tne', 'sync', 'sync.l', 'sync.p', 'cache', 'pref', 'nop', 'syscall', 'mtc0', 'div', 'divu',
           'div1', 'divu1', 'mult', 'multu', 'mult1', 'multu1'}
CLOB = ['v0', 'v1', 'at'] + ['a%d' % i for i in range(8)] + ['t%d' % i for i in range(10)]
LIKELY = {'beql', 'bnel', 'blezl', 'bgtzl', 'bltzl', 'bgezl', 'beqzl', 'bnezl', 'bc1tl', 'bc1fl', 'bltzall', 'bgezall'}
def args_of(rest):
    return [x.strip() for x in rest.split('#')[0].split(',')]
def flow_notes(lines):
    ins = []          # (line index, address, op, operands)
    for k, l in enumerate(lines):
        m = LINE.match(l)
        if m:
            ins.append((k, int(m.group(1), 16), m.group(2), args_of(m.group(3)), m.group(3)))
    at = {e[1]: i for i, e in enumerate(ins)}
    def target(rest):
        t = re.search(r'\b([0-9a-f]{5,8}) <', rest) or re.search(r'(?:^|,)\s*([0-9a-f]{5,8})\s*$', rest)
        return at.get(int(t.group(1), 16)) if t else None
    br = {}           # index of a branch -> (kind, target index or None)
    for i, (k, a, op, x, rest) in enumerate(ins):
        if op in ('jal', 'jalr', 'bal', 'bgezal', 'bltzal'):
            br[i] = ('call', None)
        elif op == 'jr':
            br[i] = ('end', None)
        elif op in ('b', 'j'):
            t = target(rest)
            br[i] = ('jump', t) if t is not None else ('end', None)
        elif (op.startswith('b') and op != 'break') or op.startswith('bc1'):
            br[i] = ('likely' if op in LIKELY else 'cond', target(rest))
    targets = set(t for kind, t in br.values() if t is not None)
    incoming = {}     # target index -> {source index: state}
    state_in = [None] * len(ins)
    notes = {}
    for _pass in range(8):
        changed = False
        cur, alive = {}, True
        for i, (k, a, op, x, rest) in enumerate(ins):
            if i in targets:
                sts = list(incoming.get(i, {}).values()) + ([cur] if alive else [])
                if sts:
                    m = dict(sts[0])
                    for s in sts[1:]:
                        m = {r: v for r, v in m.items() if s.get(r) == v}
                    cur = m
                else:
                    cur = {}
                alive = True
            if state_in[i] != cur:
                state_in[i] = dict(cur)
                changed = True
            before = dict(cur)
            notes[k] = annot(cur, op, x, True)
            b = br.get(i - 1)
            if b is not None:
                kind, t = b
                if kind == 'call':
                    for r in CLOB: cur.pop(r, None)
                elif kind == 'end':
                    alive = False
                elif kind == 'jump':
                    incoming.setdefault(t, {})[i - 1] = dict(cur)
                    alive = False
                elif t is not None:
                    incoming.setdefault(t, {})[i - 1] = dict(cur)
                    if kind == 'likely':
                        cur = before          # not taken: the slot is skipped
        if not changed and _pass:
            break
    return notes
lines = [l.rstrip('\n') for l in sys.stdin] if '-f' in sys.argv[1:] else None
if lines is not None:
    notes = flow_notes(lines)
    for k, line in enumerate(lines):
        note = notes.get(k, '')
        print(line + ('    ; ' + note if note else ''))
    sys.exit()
hi = {}
for line in sys.stdin:
    line = line.rstrip('\n')
    m = LINE.match(line)
    note = ''
    if m:
        note = annot(hi, m.group(2), [x.strip() for x in m.group(3).split(',')])
    print(line + ('    ; ' + note if note else ''))
