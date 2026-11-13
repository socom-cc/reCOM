"""strref.py <regex-bytes>...: strings in support/socom.elf matching, with vaddr and lui/addiu code refs (read-only)."""
import _dev
import re, sys, struct, subprocess, os
here = os.path.dirname(os.path.abspath(__file__))
d = _dev.elf()
e_shoff, = struct.unpack_from('<I', d, 0x20); shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x2e)
secs = [struct.unpack_from('<IIIIIIIIII', d, e_shoff + i * shentsize) for i in range(shnum)]
def va(off):
    for s in secs:
        if s[1] == 1 and s[4] <= off < s[4] + s[5] and s[3]: return s[3] + off - s[4]
out = []
for pat in sys.argv[1:]:
    for m in re.finditer(pat.encode(), d):
        s = d.rfind(b'\0', 0, m.start()) + 1; e = d.index(b'\0', m.start())
        v = va(s)
        if v and v < 0x500000: out.append((v, d[s:e]))
seen = set()
for v, n in out:
    if v in seen: continue
    seen.add(v); print(hex(v), n)
    r = subprocess.run([sys.executable, os.path.join(here, 'addrref.py'), hex(v)], capture_output=True, text=True).stdout
    for l in r.splitlines()[1:]: print('   ', l.strip())
