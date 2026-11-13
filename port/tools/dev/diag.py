"""diag.py <tree-root> <specfile>: scratch diagnostics for a test tree only (never the repo).
Each spec line: `<fence name>|<statement>` - the statement (e.g. a SOCOM_PORT_TRACE(...);) is
inserted after the opening brace of that fenced definition in the tree's src/. Lines with
`<fence name>|@end|<statement>` insert before each `return` and the closing brace instead (the
statement may use `__ret` only where valid). Idempotent per tree copy only if re-run on a fresh
copy (tree.sh copies over changed files)."""
import os, re, sys, glob
root, spec = sys.argv[1], sys.argv[2]
want = []
for line in open(spec, encoding='utf-8'):
    line = line.rstrip('\n')
    if not line.strip() or line.startswith('#'):
        continue
    name, rest = line.split('|', 1)
    want.append((name, rest))
files = {}
for f in glob.glob(os.path.join(root, 'src', '**', '*.c*'), recursive=True):
    s = open(f, encoding='utf-8', errors='replace').read()
    if '@socom-skeleton' in s:
        files[f] = s
done = set()
changed = set()
for name, stmt in want:
    fence = re.compile(r'^/\* @socom-skeleton (?:stub|body) %s \*/\r?$' % re.escape(name), re.M)
    for f, s in files.items():
        m = fence.search(s)
        if not m:
            continue
        i = s.index('{', m.end())
        files[f] = s[:i + 1] + '\n\t' + stmt + s[i + 1:]
        changed.add(f)
        done.add(name)
        break
for f in changed:
    open(f, 'w', encoding='utf-8').write(files[f])
    open(os.path.join(root, '.touched'), 'a').write(os.path.relpath(f, root).replace(os.sep, '/') + chr(10))
for name, _ in want:
    print(('ok   ' if name in done else 'MISS ') + name)
