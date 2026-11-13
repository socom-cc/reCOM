"""xref.py 0xADDR...: jal callers of the addresses in support/socom.elf (text words), with containing symbols."""
import _dev
import struct, sys, os, bisect
elf = _dev.elf()
e_shoff, = struct.unpack_from('<I', elf, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
funcs = []
for s in secs:
    if s[1] == 2:
        strtab = secs[s[6]]
        for i in range(s[5] // 16):
            nm, val, sz, info, oth, shn = struct.unpack_from('<IIIBBH', elf, s[4] + i * 16)
            n = elf[strtab[4] + nm: elf.index(b'\0', strtab[4] + nm)].decode('latin1')
            if (info & 0xf) == 2 and sz: funcs.append((val, sz, n))
funcs.sort()
starts = [f[0] for f in funcs]
text = secs[4]
base, off, size = text[3], text[4], 0x2f0000
for a in sys.argv[1:]:
    t = int(a, 16)
    want = 0x0c000000 | ((t >> 2) & 0x3ffffff)
    print('== callers of 0x%x' % t)
    for i in range(0, size, 4):
        w, = struct.unpack_from('<I', elf, off + i)
        if w == want:
            pc = base + i
            k = bisect.bisect_right(starts, pc) - 1
            print('  0x%x %s' % (pc, funcs[k][2] if k >= 0 and pc < funcs[k][0] + funcs[k][1] else '?'))
