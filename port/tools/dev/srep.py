"""srep.py <root> <editfile>: literal replacements for scratch test trees. Edit file blocks:
@@@ <src-relative file>
<old text>
@@=
<new text>
@@@ ...   (old must occur exactly once). Scratch only."""
import sys, re, os
root, ed = sys.argv[1], sys.argv[2]
t = open(ed, encoding='utf-8-sig').read().replace('\r\n', '\n')
parts = re.split(r'^@@@ (\S+)\n', t, flags=re.M)
ok = True
for i in range(1, len(parts), 2):
    f = os.path.join(root, parts[i]); body = parts[i + 1]
    old, new = body.split('@@=\n', 1)
    old = old.rstrip('\n'); new = new.rstrip('\n')
    raw = open(f, 'rb').read().decode('utf-8'); crlf = '\r\n' in raw
    s = raw.replace('\r\n', '\n')
    n = s.count(old)
    if n != 1:
        print('FAIL %s: %d matches for %r' % (parts[i], n, old[:60])); ok = False; continue
    s = s.replace(old, new)
    if crlf: s = s.replace('\n', '\r\n')
    open(f, 'wb').write(s.encode('utf-8')); print('ok   %s' % parts[i])
    if os.environ.get('SREP_TOUCH'): open(os.path.join(root, '.touched'), 'a').write(parts[i] + chr(10))
sys.exit(0 if ok else 1)
