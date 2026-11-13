"""survey.py [file-regex]: per file list of fences with ELF address/size and status (W/S). Scratch."""
import _dev
import sys, re, struct, os
import fences
here = os.path.dirname(os.path.abspath(__file__))
elf = _dev.elf()
e_shoff, = struct.unpack_from('<I', elf, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
sym = {}
for s in secs:
    if s[1] == 2:
        strtab = secs[s[6]]
        for i in range(s[5] // 16):
            nm, val, sz, info, oth, shn = struct.unpack_from('<IIIBBH', elf, s[4] + i * 16)
            n = elf[strtab[4] + nm: elf.index(b'\0', strtab[4] + nm)].decode('latin1')
            if (info & 0xf) == 2: sym.setdefault(n, (val, sz))
pat = re.compile(sys.argv[1]) if len(sys.argv) > 1 else None
st = fences.status()
byfile = {}
for n, v in st.items():
    if pat and not pat.search(v[1]): continue
    byfile.setdefault(v[1], []).append((sym.get(n, (0, 0)), n, v[0], v[2]))
tw = ts = 0
for f in sorted(byfile):
    rows = sorted(byfile[f])
    w = sum(r[0][1] for r in rows if r[2] == 'W'); s = sum(r[0][1] for r in rows if r[2] == 'S')
    tw += w; ts += s
    print('## %s  written %d B (%d fn), stub %d B (%d fn)' % (f, w, sum(1 for r in rows if r[2]=='W'), s, sum(1 for r in rows if r[2]=='S')))
    if '-q' not in sys.argv:
        for (a, sz), n, s_, nv in rows:
            print('  %08x %5d %s%s %s' % (a, sz, s_, '!' if nv and s_ == 'S' else ' ', n))
print('total written %d stub %d' % (tw, ts))
