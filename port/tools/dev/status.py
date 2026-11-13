"""status.py <mangled>... | -f <asmfile>: port status of functions (skeleton marker + whether the body is empty)."""
import _dev
import sys, os, re, glob
root = _dev.SRC
files = glob.glob(os.path.join(root, '**', '*.cpp'), recursive=True)
idx = {}
for f in files:
    t = open(f, encoding='latin1').read()
    for m in re.finditer(r'@socom-skeleton (stub|body) (\S+) \*/\n', t):
        # body text: from the first '{' after the marker to its matching '}'
        i = t.find('{', m.end())
        depth = 0; j = i
        while j < len(t):
            if t[j] == '{': depth += 1
            elif t[j] == '}':
                depth -= 1
                if depth == 0: break
            j += 1
        body = t[i + 1:j]
        code = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S).strip()
        lines = len([l for l in code.split('\n') if l.strip()])
        idx[m.group(2)] = (m.group(1), lines, os.path.relpath(f, root), body.count('port: stub') + body.count('not written'))
names = sys.argv[1:]
if names and names[0] == '-f':
    names = []
    for line in open(sys.argv[2], encoding='utf-8-sig'):
        m = re.search(r'jal\s+\w+ <([^>+]+)>', line)
        if m and m.group(1) not in names: names.append(m.group(1))
for n in names:
    s = idx.get(n)
    if s is None: print('%-70s  (no skeleton marker)' % n[:70])
    else: print('%-70s  %s %3d lines%s  %s' % (n[:70], s[0], s[1], ' NOTE' if s[3] else '', s[2]))
