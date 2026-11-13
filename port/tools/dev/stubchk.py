"""stubchk.py <name-regex>...: for each skeleton fence whose name matches, print file, kind and whether the body is empty."""
import _dev
import re, sys, os, glob
root = _dev.SRC
pats = [re.compile(p) for p in sys.argv[1:]]
for f in glob.glob(os.path.join(root, '**', '*.cpp'), recursive=True):
    s = open(f, encoding='utf-8', errors='replace').read()
    for m in re.finditer(r'/\* @socom-skeleton (stub|body) (\S+) \*/\n', s):
        name = m.group(2)
        if not any(p.search(name) for p in pats): continue
        i = m.end()
        j = s.find('{', i)
        sig = s[i:j].strip().split('\n')[-1][:90]
        # brace match
        d = 0; k = j
        while k < len(s):
            if s[k] == '{': d += 1
            elif s[k] == '}':
                d -= 1
                if d == 0: break
            k += 1
        body = s[j+1:k].strip()
        empty = 'EMPTY' if not body else '%d lines' % body.count('\n')
        print('%-60s %-6s %-10s %s' % (name[:60], m.group(1), empty, os.path.relpath(f, root)))
