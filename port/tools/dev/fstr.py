"""fstr.py 0xADDR [nbytes]: strings and symbols referenced by lui/addiu|ori|lw pairs and $gp offsets inside a
function (size from the symbol table unless nbytes is given; read-only, support/socom.elf). Merged from strs.py."""
import _dev
import sys, os, struct
here = os.path.dirname(os.path.abspath(__file__))
elf = _dev.elf()
e_shoff, = struct.unpack_from('<I', elf, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
syms = {}
GP = 0
for s in secs:
    if s[1] == 2:
        st = secs[s[6]]
        for i in range(s[5] // 16):
            nm, val, sz, info, oth, shn = struct.unpack_from('<IIIBBH', elf, s[4] + i * 16)
            syms.setdefault(val, (sz, elf[st[4] + nm: elf.index(b'\0', st[4] + nm)].decode('latin1')))
def off(a):
    for s in secs:
        if s[1] in (1, 8) and s[3] <= a < s[3] + s[5]: return None if s[1] == 8 else s[4] + a - s[3]
def word(a):
    o = off(a); return struct.unpack_from('<I', elf, o)[0] if o is not None else None
def cstr(a):
    o = off(a)
    if o is None: return None
    e = elf.index(b'\0', o); b = elf[o:e]
    if 0 < len(b) < 200 and all(32 <= c < 127 or c in (9, 10) for c in b): return b.decode()
start = int(sys.argv[1], 16)
n = int(sys.argv[2], 0) if len(sys.argv) > 2 else syms.get(start, (0x400,))[0]
hi = {}
for a in range(start, start + n, 4):
    w = word(a); op = w >> 26; rs = (w >> 21) & 31; rt = (w >> 16) & 31; imm = w & 0xffff; simm = imm - 0x10000 if imm & 0x8000 else imm
    if op == 0xf: hi[rt] = imm << 16; continue
    if op in (9, 0xd, 0x23, 0x24, 0x25, 0x21, 0x31, 0x37) and rs in hi:
        t = (hi[rs] + (imm if op == 0xd else simm)) & 0xffffffff
        s = cstr(t)
        nm = syms.get(t, (0, ''))[1]
        print('%08x -> %08x %s %s' % (a, t, nm, repr(s) if s is not None else ''))
    elif op in (9, 0x23, 0x24, 0x25, 0x21, 0x31) and rs == 28 and GP:
        t = (GP + simm) & 0xffffffff
        s = cstr(t)
        nm = syms.get(t, (0, ''))[1]
        print('%08x -> %08x gp %s %s' % (a, t, nm, repr(s) if s is not None else ''))
