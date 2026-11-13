"""ctree.py <addr> [depth] [--all]: direct-call tree (jal targets) of an ELF function with sizes and the
port status of each callee from the src/ skeleton fences: W = body written (fence 'body' or a
non-empty stub), S = empty stub, ? = no fence found. Repeated callees are listed once; library
(provider/MSL/sce) names and already-written callees are not expanded. Read-only."""
import _dev
import os, re, struct, sys, bisect, glob
here = os.path.dirname(os.path.abspath(__file__))
root = _dev.REPO
elf = _dev.elf()
e_shoff, = struct.unpack_from('<I', elf, 0x20)
shentsize, shnum, shstrndx = struct.unpack_from('<HHH', elf, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
funcs = {}
for s in secs:
    if s[1] == 2:
        strtab = secs[s[6]]
        for i in range(s[5] // 16):
            nm, val, sz, info, oth, shn = struct.unpack_from('<IIIBBH', elf, s[4] + i * 16)
            n = elf[strtab[4] + nm: elf.index(b'\0', strtab[4] + nm)].decode('latin1')
            if (info & 0xf) == 2 and sz:
                funcs[val] = (sz, n)
text = secs[4]
def word(a):
    return struct.unpack_from('<I', elf, text[4] + a - text[3])[0]
import fences
status = {k: (v[0] + ('!' if v[0] == 'S' and v[2] else ''), v[1]) for k, v in fences.status().items()}
LIB = re.compile(r'^(sce|_|str|mem|sprintf|f[a-z]+f$|sqrtf|__|Top__|tail__|begin__|end__|insert__|second__|first__|data__|resize__|reserve__|erase__|clear__|swap|remove|find|sort)')
def callees(a):
    sz = funcs[a][0]
    out = []
    for pc in range(a, a + sz, 4):
        w = word(pc)
        if w >> 26 == 3:
            t = (pc & 0xf0000000) | ((w & 0x3ffffff) << 2)
            if t in funcs and t not in out:
                out.append(t)
    return out
seen = set()
def show(a, depth, maxd, everything):
    sz, n = funcs[a]
    st, f = status.get(n, ('?', ''))
    print('%s%s 0x%x %5d %s %s' % ('  ' * depth, st, a, sz, n[:90], f))
    if a in seen or depth >= maxd:
        return
    seen.add(a)
    for t in callees(a):
        tn = funcs[t][1]
        if LIB.match(tn) and not everything:
            continue
        tst = status.get(tn, ('?', ''))[0][0]
        if t in seen:
            continue
        if tst == 'W' and depth + 1 < maxd and not everything:
            seen.add(t)
            print('%sW 0x%x %5d %s' % ('  ' * (depth + 1), t, funcs[t][0], tn[:90]))
            continue
        show(t, depth + 1, maxd, everything)
if __name__ == '__main__':
  a = int(sys.argv[1], 16)
  d = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith('-') else 2
  show(a, 0, d, '--all' in sys.argv)
