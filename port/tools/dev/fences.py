"""fences.py: scan src/ skeleton fences. status(name) -> (st, file, nonvoid, line) with st W (body has
statements), S (empty stub: only fences/statics), ? (no fence). `python fences.py <regex>` lists matches.
Brace-matched, so stubs with static-local fences are classified correctly. Scratch only."""
import _dev
import os, re, glob, sys, pickle
here = os.path.dirname(os.path.abspath(__file__))
root = _dev.REPO
FENCE = re.compile(r'/\* @socom-skeleton (body|stub) (\S+) \*/')
def scan():
    out = {}
    for f in glob.glob(os.path.join(root, 'src', '**', '*.c*'), recursive=True):
        if not f.endswith(('.cpp', '.c')): continue
        lines = open(f, encoding='utf-8', errors='replace').read().split('\n')
        rel = os.path.relpath(f, os.path.join(root, 'src')).replace('\\', '/')
        i = 0
        n = len(lines)
        while i < n:
            m = FENCE.search(lines[i])
            if not m or lines[i].startswith(('\t', ' ')):
                i += 1; continue
            kind, name = m.group(1), m.group(2)
            j = i + 1
            sig = []
            while j < n and lines[j].strip() != '{' and not lines[j].rstrip().endswith(';') and j < i + 8:
                sig.append(lines[j]); j += 1
            if j >= n or lines[j].strip() != '{':
                out.setdefault(name, ('D', rel, False, i + 1))
                i += 1; continue
            s = ' '.join(sig)
            nonvoid = '(' in s and not re.match(r'\s*(static\s+|inline\s+|virtual\s+)*void\b', s) and '::~' not in s and not re.search(r'(\w+)::\1\s*\(', s)
            depth = 0
            body = []
            k = j
            while k < n:
                depth += lines[k].count('{') - lines[k].count('}')
                if k > j: body.append(lines[k])
                if depth <= 0: break
                k += 1
            rest = [l for l in body[:-1] if l.strip() and '@socom-skeleton' not in l and not l.strip().startswith('static ')]
            st = 'W' if kind == 'body' or rest else 'S'
            out[name] = (st, rel, nonvoid, i + 1)
            i = k + 1
    return out
_cache = None
def status():
    global _cache
    if _cache is None: _cache = scan()
    return _cache
if __name__ == '__main__':
    s = status()
    for k, v in sorted(s.items()):
        if re.search(sys.argv[1], k): print(v[0], 'nonvoid' if v[2] else 'void   ', '%s:%d' % (v[1], v[3]), k)
