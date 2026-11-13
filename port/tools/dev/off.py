"""off.py <Class> <hex-offset>...: DWARF member(s) at the offsets (flattened, bases included). Scratch."""
import sys, io
sys.argv, a = [sys.argv[0]], sys.argv[1:]
sys.stdin = io.StringIO('')
import cz
fl = sorted(set(cz.flat(a[0])))
for x in a[1:]:
    o = int(x, 16)
    ms = [n for k, n in fl if k == o]
    if not ms:
        prev = [(k, n) for k, n in fl if k < o][-1:]
        ms = ['%s+0x%x' % (n, o - k) for k, n in prev]
    print('0x%x: %s' % (o, ' | '.join(ms)))
