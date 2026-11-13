"""rep.py <defs-file> [--dry]: replace whole function definitions by skeleton fence name.
The defs file holds blocks:
    === <mangled fence name>
    <new definition: signature line(s), then the braced body>
Each fence `/* @socom-skeleton (stub|body) <name> */` must occur once at column 0 in src/; the
old definition (the lines after the fence through the brace that closes the body) is replaced.
Every inner `@socom-skeleton` line of the old body (static-local fences) must reappear verbatim
(modulo indentation) in the new text, else the block is refused. Keeps LF/CRLF. Scratch only."""
import _dev
import os, re, sys, glob
here = os.path.dirname(os.path.abspath(__file__))
root = os.environ.get('SOCOM_REP_ROOT') or os.environ.get('REP_ROOT') or _dev.REPO
text = open(sys.argv[1], encoding='utf-8-sig').read().replace('\r\n', '\n')
dry = '--dry' in sys.argv
blocks = re.split(r'^=== (\S+)\n', text, flags=re.M)
defs = []
for i in range(1, len(blocks), 2):
    defs.append((blocks[i], blocks[i + 1].rstrip('\n') + '\n'))
files = {}
index = {}
for f in glob.glob(os.path.join(root, 'src', '**', '*.c*'), recursive=True):
    if not f.endswith(('.cpp', '.c')): continue
    s = open(f, encoding='utf-8', newline='').read()
    if '@socom-skeleton' not in s: continue
    for m in re.finditer(r'^/\* @socom-skeleton (?:stub|body) (\S+) \*/$', s.replace('\r\n', '\n'), re.M):
        index.setdefault(m.group(1), []).append(f)
bad = False
for name, new in defs:
    fl = index.get(name, [])
    if len(fl) != 1:
        print('FAIL %s: %d fences' % (name, len(fl))); bad = True; continue
    f = fl[0]
    if f not in files:
        raw = open(f, encoding='utf-8', newline='').read()
        files[f] = [raw.replace('\r\n', '\n'), '\r\n' in raw]
    s = files[f][0]
    lines = s.split('\n')
    fence = '/* @socom-skeleton stub %s */' % name
    fence2 = '/* @socom-skeleton body %s */' % name
    at = [i for i, l in enumerate(lines) if l == fence or l == fence2]
    if len(at) != 1:
        print('FAIL %s: fence lines %d' % (name, len(at))); bad = True; continue
    i = at[0]
    j = i + 1
    while j < len(lines) and lines[j].strip() != '{' and j < i + 10: j += 1
    if lines[j].strip() != '{':
        print('FAIL %s: no body' % name); bad = True; continue
    depth = 0; k = j
    while k < len(lines):
        depth += lines[k].count('{') - lines[k].count('}')
        if depth <= 0: break
        k += 1
    old = lines[i + 1:k + 1]
    inner = [l.strip() for l in old if '@socom-skeleton' in l]
    newn = [l.strip() for l in new.split('\n')]
    miss = [x for x in inner if x not in newn]
    if miss:
        print('FAIL %s: inner fences missing: %s' % (name, miss)); bad = True; continue
    lines[i + 1:k + 1] = new.rstrip('\n').split('\n')
    files[f][0] = '\n'.join(lines)
    print('ok %s -> %s' % (name, os.path.relpath(f, root)))
if bad:
    print('nothing written'); sys.exit(1)
if not dry:
    for f, (s, crlf) in files.items():
        if crlf: s = s.replace('\n', '\r\n')
        open(f, 'w', encoding='utf-8', newline='').write(s)
