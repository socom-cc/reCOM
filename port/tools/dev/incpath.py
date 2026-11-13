"""incpath.py <from-header> <to-header-suffix>: include chains (src/-relative) from one header to another."""
import _dev
import re, os, sys
root = _dev.SRC
inc = {}
for d, _, fs in os.walk(root):
    for f in fs:
        if f.endswith('.h'):
            p = os.path.relpath(os.path.join(d, f), root).replace(os.sep, '/')
            inc[p] = re.findall(r'#include\s+"([^"]+)"', open(os.path.join(d, f), encoding='latin1').read())
def resolve(cur, i):
    if i in inc: return i
    c = os.path.dirname(cur) + '/' + i
    return c if c in inc else i
seen = set()
def walk(h, path):
    for i in inc.get(h, []):
        i = resolve(h, i)
        if i in seen: continue
        seen.add(i)
        if i.endswith(sys.argv[2]): print(' -> '.join(path + [i]))
        walk(i, path + [i])
walk(sys.argv[1], [sys.argv[1]])
