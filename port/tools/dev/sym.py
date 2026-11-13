"""sym.py name-substring | 0xADDR [nwords]: symbol lookup and word dump from support/socom.elf (read-only)."""
import _dev
import struct, sys, os, re
elf = _dev.elf()
e_shoff, = struct.unpack_from('<I', elf, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
syms = []
for s in secs:
    if s[1] == 2:
        strtab = secs[s[6]]
        for i in range(s[5] // 16):
            nm, val, sz, info, oth, shn = struct.unpack_from('<IIIBBH', elf, s[4] + i * 16)
            n = elf[strtab[4] + nm: elf.index(b'\0', strtab[4] + nm)].decode('latin1')
            syms.append((val, sz, n))
byaddr = {}
for v, sz, n in syms: byaddr.setdefault(v, []).append(n)
def word(a):
    for s in secs:
        if s[1] == 1 and s[3] <= a < s[3] + s[5]:
            return struct.unpack_from('<I', elf, s[4] + a - s[3])[0]
    return None
arg = sys.argv[1]
def cstr(a):
    for s in secs:
        if s[1] == 1 and s[3] <= a < s[3] + s[5]:
            o = s[4] + a - s[3]
            return elf[o:elf.index(b'\0', o)].decode('latin1')
if arg == '-s':
    for x in sys.argv[2:]: print(x, repr(cstr(int(x, 16))))
    sys.exit()
if arg.startswith('0x'):
    a = int(arg, 16); n = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    for i in range(n):
        w = word(a + 4 * i)
        print('%08x: %08x %s' % (a + 4 * i, w if w is not None else 0, ','.join(byaddr.get(w, []))[:120] if w else ''))
else:
    for v, sz, n in sorted(syms):
        if re.search(arg, n): print('%08x %5d %s' % (v, sz, n))
