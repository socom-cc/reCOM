"""addrref.py 0xADDR...: lui/addiu (or lui/ori) pairs in .text that build the address, with the containing function."""
import struct, sys, bisect, os
sys.argv, args = sys.argv[:1], sys.argv[1:]
import ctree
elf = ctree.elf; text = ctree.secs[4]
base, off, size = text[3], text[4], text[5]
starts = sorted(ctree.funcs)
def fn(pc):
    k = bisect.bisect_right(starts, pc) - 1
    return ctree.funcs[starts[k]][1] if k >= 0 else '?'
for a in args:
    t = int(a, 16)
    hi = (t + 0x8000) >> 16; lo = t & 0xffff
    print('== refs to 0x%x' % t)
    for i in range(0, size - 4, 4):
        w, = struct.unpack_from('<I', elf, off + i)
        if w >> 26 == 0xf and (w & 0xffff) == hi:
            rt = (w >> 16) & 31
            for j in range(1, 12):
                w2, = struct.unpack_from('<I', elf, off + i + 4 * j)
                op = w2 >> 26
                if op in (9, 13) and ((w2 >> 21) & 31) == rt and (w2 & 0xffff) == (lo if op == 9 else t & 0xffff):
                    print('  0x%x %s' % (base + i, fn(base + i))); break
