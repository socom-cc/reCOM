"""ed.py <edit-file>: apply old/new block edits to repo files (scratch tool).
Edit file format:
=== FILE <repo-relative path>
<<< OLD
...lines...
>>> NEW
...lines...
<<< END
(repeatable). Each OLD block must occur exactly once. CRLF/LF of the target is kept.
SOCOM_REP_ROOT=<dir> edits a test tree instead of the repo."""
import _dev
import os, sys
root = os.environ.get('SOCOM_REP_ROOT') or _dev.REPO
lines = open(sys.argv[1], encoding='utf-8').read().split('\n')
edits = []
cur = None
mode = None
buf = []
for ln in lines:
    if ln.startswith('=== FILE '):
        cur = ln[9:].strip()
        continue
    if ln == '<<< OLD':
        mode = 'old'; buf = []; continue
    if ln == '>>> NEW':
        old = '\n'.join(buf); mode = 'new'; buf = []; continue
    if ln == '<<< END':
        edits.append((cur, old, '\n'.join(buf))); mode = None; continue
    if mode:
        buf.append(ln)
ok = True
files = {}
for f, old, new in edits:
    p = os.path.join(root, f)
    if p not in files:
        files[p] = open(p, encoding='utf-8', newline='').read()
    s = files[p]
    nl = '\r\n' if '\r\n' in s else '\n'
    o = old.replace('\n', nl); n = new.replace('\n', nl)
    c = s.count(o)
    if c != 1:
        print('FAIL %s: %d matches for %r' % (f, c, old[:70])); ok = False; continue
    files[p] = s.replace(o, n, 1)
    print('ok %s' % f)
if ok:
    for p, s in files.items():
        open(p, 'w', encoding='utf-8', newline='').write(s)
else:
    print('nothing written')
    sys.exit(1)
