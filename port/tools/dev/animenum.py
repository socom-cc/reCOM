"""enum.py <value|name>...: AnimType enumerator by value or name (src/gamez/zAnim/zanim.h)."""
import _dev
import re, sys, os
s = open(os.path.join(_dev.SRC, 'gamez', 'zAnim', 'zanim.h'), encoding='utf-8', errors='replace').read()
i = s.index('enum class AnimType'); body = s[s.index('{', i)+1:s.index('}', i)]
vals = {}; v = -1
for item in body.split(','):
    item = re.sub(r'/\*.*?\*/|//.*', '', item, flags=re.S).strip()
    if not item: continue
    if '=' in item: n, e = item.split('='); n = n.strip(); v = int(e.strip(), 0)
    else: n = item; v += 1
    vals[n] = v
inv = {}
for n, x in vals.items(): inv.setdefault(x, n)
for a in sys.argv[1:]:
    print(a, '->', inv.get(int(a, 0)) if re.match(r'^-?\d|^0x', a) else vals.get(a))
