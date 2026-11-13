"""reach.py <addr>... [--depth N]: ELF jal graph from the roots through port-written (W)
functions; lists the empty non-void stubs (S!) and void stubs (S) reached, with one caller each.
Over-approximates (port bodies may skip calls). Scratch only."""
import sys, re
sys.argv, args = sys.argv[:1], sys.argv[1:]
import ctree
depth = 6
if '--depth' in args:
    i = args.index('--depth'); depth = int(args[i + 1]); del args[i:i + 2]
roots = [int(a, 16) for a in args]
LIB = ctree.LIB
seen = {}
frontier = [(r, None, 0) for r in roots]
nv, vs = {}, {}
while frontier:
    a, parent, d = frontier.pop(0)
    if a in seen: continue
    seen[a] = parent
    sz, n = ctree.funcs[a]
    st = ctree.status.get(n, ('?', ''))[0]
    if st.startswith('S'):
        (nv if st == 'S!' else vs).setdefault(n, (a, parent))
        continue
    if st == '?' and a not in roots: continue
    if d >= depth: continue
    for t in ctree.callees(a):
        tn = ctree.funcs[t][1]
        if LIB.match(tn): continue
        if t not in seen: frontier.append((t, a, d + 1))
def nm(a): return ctree.funcs[a][1][:60] if a else '-'
print('== non-void stubs')
for n, (a, p) in sorted(nv.items(), key=lambda x: x[1][0]):
    print('S! 0x%x %5d %-70s <- %s' % (a, ctree.funcs[a][0], n[:70], nm(p)))
if '-v' in sys.argv or True:
    print('== void stubs: %d' % len(vs))
