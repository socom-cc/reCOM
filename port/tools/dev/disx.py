"""disx.py: annotate objdump output (stdin) with lui/addiu and $gp-relative symbols and strings from support/socom.elf."""
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
    if s is not None and not a in syms: r = (r + ' ' if r else '') + repr(s)
    elif s is not None: r += ' ' + repr(s)
    return '0x%x %s' % (a, r)
hi = {}
for line in sys.stdin:
    line = line.rstrip('\n')
    m = re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)', line)
    note = ''
    if m:
        op, args = m.group(2), m.group(3)
        a = [x.strip() for x in args.split(',')]
        if op == 'lui' and len(a) == 2:
            hi[a[0]] = int(a[1], 0) << 16
        elif op in ('addiu', 'daddiu') and len(a) == 3:
            imm = int(a[2], 0)
            if a[1] == 'gp': note = desc((GP + imm) & 0xffffffff)
            elif a[1] in hi: note = desc((hi[a[1]] + imm) & 0xffffffff)
            if a[0] in hi and a[0] != a[1]: hi.pop(a[0], None)
            elif a[0] == a[1]: hi.pop(a[0], None)
        elif op == 'ori' and len(a) == 3 and a[1] in hi:
            note = '0x%x' % (hi[a[1]] | int(a[2], 0))
        else:
            mm = re.match(r'(-?\w+)\((\w+)\)', a[-1]) if a else None
            if mm:
                imm = int(mm.group(1), 0)
                if mm.group(2) == 'gp': note = desc((GP + imm) & 0xffffffff)
                elif mm.group(2) in hi: note = desc((hi[mm.group(2)] + imm) & 0xffffffff)
            if a and op not in ('sw', 'sd', 'sq', 'sb', 'sh', 'swc1', 'sqc2', 'jr', 'jalr') and not op.startswith('b') and a[0] in hi and not (mm and mm.group(2) == a[0] and False):
                hi.pop(a[0], None)
    print(line + ('    ; ' + note if note else ''))
