"""auditscan.py: mechanical comparison of fenced port functions with the reference ELF, to say
where the correctness audit (docs/port/AUDIT_PLAN.md) should look first.

  auditscan.py [--build NAME] --list NAME     build/port/audit/scan-NAME.md for an auditlist.py list
  auditscan.py [--build NAME] --all           build/port/audit/scan-all.md, every fenced function
  auditscan.py ... --json                     also writes the rows as scan-*.json
  auditscan.py --fn 0xADDR|MANGLED [--build NAME]   one function's features and differences

Port side: a fingerprint build (fpbuild.sh <commit> <NAME>: -O2 -g with inlining, IPA cloning,
code folding and tail merging off) read from <scratch>/fp/NAME.{elf,dis,syms,commit}
(--fp DIR moves that folder; default NAME head). Each fence is mapped to its compiled symbol by
the symbol's first debug line (between the fence comment and the body's brace, same file), else
by the readable qualified name. The fences are read at the build's commit (git archive).

Features compared (compiler-independent; auditlib.features): direct calls by readable name
(both sides flattened where one side inlined a callee: a callee present on one side only is
replaced by its own features when that brings the two closer), float constant words (an ELF
word one ulp from a port word is reported as such), integer constants (|v| >= 16) and compare
immediates (a +-1 neighbour counts as the same), string literals, member accesses (offset,
load/store) through non-stack, non-global base registers and their width / signedness, stores
and loads of globals by name, float operation counts (add, sub, mul, div, sqrt, cmp, ... with
madd / adda split into their parts), indirect calls, size ratio and branch count.

Score: the weighted sum of the differences (weights in WEIGHTS, chosen on half of the audit's
ground truth, see build/port/audit/SCAN_VALIDATION.md). A score of 0 means "no difference
found", not MATCH: float sum order, an added guard, a wrong branch sense and most logic slips
leave these features unchanged.
"""
import _dev
import auditlib as L
import collections
import json
import os
import re
import sys

AUDIT = os.path.join(_dev.REPO, 'build', 'port', 'audit')
IGNORE_CALLS = re.compile(r'^(__ubsan_|memcpy$|memset$|memmove$|__builtin|_ZdlPv|abort$)')
WEIGHTS = {'call': 3.0, 'ncall': 1.0, 'str': 3.0, 'fulp': 3.0, 'fconst': 2.0, 'fint': 0.5, 'iconst': 1.0, 'cmpk': 0.5,
           'store': 2.0, 'load': 0.5, 'width': 1.0, 'gst': 2.0, 'gld': 0.25, 'fops': 0.5,
           'ind': 1.0, 'size': 1.0, 'nbr': 0.5}


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


# ---------------------------------------------------------------- the two sides
class Ref:
    def __init__(self):
        self.elf = L.ref()
        self.dis = L.ref_dis()
        self._f = {}
        self.virt = {self.key(self.elf.funcs[a][0]) for a in self.elf.virtuals('__vt__')}

    def key(self, name):
        return L.mw_key(name)

    def feat(self, start):
        if start not in self._f:
            f = self.elf.funcs.get(start)
            if not f:
                self._f[start] = None
            else:
                sz = f[1]
                self._f[start] = L.features(self.elf, self.dis.insns(start, start + sz), start, start + sz, self.key)
        return self._f[start]


class Port:
    def __init__(self, name, fpdir=None):
        d = fpdir or os.path.join(_dev.scratch(), 'fp')
        self.name = name
        self.elf = L.Elf(os.path.join(d, name + '.elf'))
        self.dis = L.Dis(os.path.join(d, name + '.dis'))
        self.commit = open(os.path.join(d, name + '.commit')).read().strip()
        self.dem = {}
        for line in open(os.path.join(d, name + '.syms'), encoding='latin1'):
            p = line.rstrip('\n').split('\t')
            if len(p) == 2:
                self.dem[p[0]] = p[1]
        self._f = {}
        self.byfile = collections.defaultdict(list)    # src path -> [(line, start, name)]
        self.bykey = collections.defaultdict(list)     # key -> [start]
        for start, (n, sz, b) in self.elf.funcs.items():
            fl = self.dis.first_line(start)
            if fl:
                i = fl[0].find('/src/')
                if i >= 0:
                    self.byfile[fl[0][i + 1:]].append((fl[1], start, n))
            self.bykey[self.key(n)].append(start)
        for v in self.byfile.values():
            v.sort()
        self.virt = {self.key(self.elf.funcs[a][0]) for a in self.elf.virtuals('_ZTV')}

    def key(self, name):
        return L.gnu_key(self.dem.get(name, name))

    def feat(self, start):
        if start not in self._f:
            f = self.elf.funcs.get(start)
            if not f:
                self._f[start] = None
            else:
                sz = f[1]
                F = L.features(self.elf, self.dis.insns(start, start + sz), start, start + sz, self.key)
                for k in [k for k in F.calls if IGNORE_CALLS.match(k)]:
                    del F.calls[k]
                self._f[start] = F
                # the port's own lambdas are pieces of this body: always folded in
                for k in [k for k in F.calls if '{lambda' in k and k in F.calladdr]:
                    sub = self.feat(F.calladdr[k]) if F.calladdr[k] != start else None
                    n = F.calls.pop(k)
                    if sub is not None:
                        for _ in range(n):
                            F.add(sub)
                        F.size += n * sub.size
        return self._f[start]

    def find(self, fence, mwname):
        """Port function start for a fence (file, fence line, brace line, end line)."""
        path, fl, bl, el = fence
        cands = [(ln, s, n) for ln, s, n in self.byfile.get(path, ()) if fl <= ln <= bl + 1]
        if not cands:
            # the first line marker can be the first statement: the earliest non-lambda symbol
            # whose first line is inside the body
            cands = [(ln, s, n) for ln, s, n in self.byfile.get(path, ())
                     if fl <= ln <= el and '{lambda' not in self.dem.get(n, n)]
            cands = cands[:1]
        if not cands:
            k = L.mw_key(mwname)
            starts = self.bykey.get(k, [])
            if len(starts) > 1:     # overloads: the one compiled from this file
                starts = [s for s in starts if any(s == x[1] for x in self.byfile.get(path, ()))]
            if len(starts) == 1:
                return starts[0], 'name'
            return None, 'none'

        def pref(c):
            n = c[2]
            m = re.search(r'([CD])([0-2])E', n)
            r = 0
            if m:
                r = {'C1': 0, 'C2': 1, 'D1': 0, 'D2': 1, 'D0': 2}.get(m.group(0)[:2], 3)
            return (r, -self.elf.funcs[c[1]][1])
        cands.sort(key=pref)
        return cands[0][1], 'line'


# ---------------------------------------------------------------- comparison
MAGIC = {0x01010101, 0x80808080, 0xfefefeff, 0x7efefeff, 0x81010100, 0x41c64e6d, 0x3039}


def _mask(v):
    """A bit mask (a contiguous run of ones, or the complement of one): bitfield code, which the
    two compilers build differently."""
    v &= 0xffffffff
    for x in (v, ~v & 0xffffffff):
        if x and ((x >> ((x & -x).bit_length() - 1)) + 1) & (x >> ((x & -x).bit_length() - 1)) == 0:
            return True
    return v in MAGIC


def _junkfloat(w):
    return w and (w >> 23) & 0xff == 0 or 0x100000 <= w < 0x600000


def _isint(f):
    return abs(f) <= 1024 and f == int(f)


def _near(v, pool, tol=1):
    return any((v + d) in pool for d in range(-tol, tol + 1))


def compare(E, P, ref=None, port=None, flatten=True):
    """(score, [(weight, text)]) for ELF features E and port features P."""
    if flatten and ref is not None and port is not None:
        E, P = _virt(_copy(E), _copy(P), ref, port)
        E, P = _flatten(E, P, ref, port)
    out = []
    W = WEIGHTS

    def add(kind, n, text):
        if n:
            out.append((W[kind] * n, kind, text, n))
    times = lambda n: {1: 'once', 2: 'twice'}.get(n, '%d times' % n)
    for k in sorted(set(E.calls) | set(P.calls)):
        e, p = E.calls.get(k, 0), P.calls.get(k, 0)
        if e != p and not IGNORE_CALLS.match(k):
            add('call' if not (e and p) else 'ncall', abs(e - p), 'ELF calls %s %s, port %s' % (k, times(e) if e else 'never', times(p) if p else 'never'))
    for s in sorted(set(E.strs) ^ set(P.strs)):
        add('str', 1, '%s string %r not in the %s' % ('ELF' if s in E.strs else 'port', s[:60], 'port' if s in E.strs else 'ELF'))
    # a float constant may be built in a GPR and stored as an integer on the other side
    ef = {w for w in E.fconst if not _junkfloat(w)} - {v & 0xffffffff for v in P.iconst}
    pf = {w for w in P.fconst if not _junkfloat(w)} - {v & 0xffffffff for v in E.iconst}
    eint = {v for v in E.iconst if not _mask(v) and (v & 0xffffffff) not in P.fconst}
    pint = {v for v in P.iconst if not _mask(v) and (v & 0xffffffff) not in E.fconst}
    # x / 2^n is x * 2^-n in GCC's code, x * 2 is x + x: a power of two missing on one side whose
    # reciprocal is the other side's extra, or 1 / 2 / -1 / 0.5 alone, is not reported
    recip = lambda w: (((254 - ((w >> 23) & 0xff)) & 0xff) << 23) | (w & 0x80000000)
    e0, p0 = set(ef), set(pf)
    for w in sorted(e0 - p0):
        if w & 0x7fffff == 0 and recip(w) in p0:
            ef.discard(w); pf.discard(recip(w))
    for w in sorted(p0 - e0):
        if w & 0x7fffff == 0 and recip(w) in e0:
            pf.discard(w); ef.discard(recip(w))
    for w in (0x3f800000, 0xbf800000, 0x40000000, 0x3f000000):
        if (w in ef) != (w in pf):
            ef.discard(w); pf.discard(w)
    for w in sorted(ef - pf):
        f = L.Elf.float_of(None, w)
        if _near(w, pf - ef):
            q = [x for x in pf - ef if abs(x - w) <= 1][0]
            add('fulp', 1, 'float 0x%08x (%.9g) in the ELF, 0x%08x in the port (one ulp)' % (w, f, q))
        else:
            add('fint' if _isint(f) else 'fconst', 1, 'ELF loads float 0x%08x (%.9g), port never' % (w, f))
    for w in sorted(pf - ef):
        if not _near(w, ef - pf):
            f = L.Elf.float_of(None, w)
            add('fint' if _isint(f) else 'fconst', 1, 'port loads float 0x%08x (%.9g), ELF never' % (w, f))
    for side, A, B, ai, bi in (('ELF', E, P, eint, pint), ('port', P, E, pint, eint)):
        for v in sorted(ai - bi):
            if not _near(v, bi | set(B.cmpk) | set(B.iconst)):
                add('iconst', 1, '%s constant %d (0x%x) not in the %s' % (side, v, v & 0xffffffff, 'port' if side == 'ELF' else 'ELF'))
        for v in sorted(set(A.cmpk) - set(B.cmpk)):
            if not _near(v, set(B.cmpk) | set(B.iconst)) and not _mask(v):
                add('cmpk', 1, '%s compares with %d, the %s does not' % (side, v, 'port' if side == 'ELF' else 'ELF'))
    em, pm = set(E.mem), set(P.mem)
    for (o, ls) in sorted(em ^ pm):
        side = 'ELF' if (o, ls) in em else 'port'
        add('store' if ls == 'S' else 'load', 1, '%s %s +0x%x, the %s never' % (side, 'stores' if ls == 'S' else 'reads', o, 'port' if side == 'ELF' else 'ELF'))
    ek = collections.defaultdict(set)
    pk = collections.defaultdict(set)
    for (o, k) in E.memw:
        ek[(o, k[0])].add(k)
    for (o, k) in P.memw:
        pk[(o, k[0])].add(k)
    for key in sorted(set(ek) & set(pk)):
        a, b = ek[key], pk[key]
        if not (a & b):
            add('width', 1, '+0x%x %s as %s in the ELF, %s in the port' % (key[0], 'stored' if key[1] == 'S' else 'read', '/'.join(sorted(a)), '/'.join(sorted(b))))
    for g in sorted((set(E.gst) ^ set(P.gst)) - {'#guard'}):
        side = 'ELF' if g in E.gst else 'port'
        add('gst', 1, '%s stores global %s, the %s never' % (side, g, 'port' if side == 'ELF' else 'ELF'))
    for g in sorted(set(E.gld) ^ set(P.gld)):
        side = 'ELF' if g in E.gld else 'port'
        add('gld', 1, '%s reads global %s, the %s never' % (side, g, 'port' if side == 'ELF' else 'ELF'))
    for k in sorted(set(E.fops) | set(P.fops)):
        e, p = E.fops.get(k, 0), P.fops.get(k, 0)
        d = abs(e - p) - max(0, int(0.1 * max(e, p)))
        if d > 0:
            add('fops', d, 'float %s: ELF %d, port %d' % (k, e, p))
    if E.ind != P.ind:
        add('ind', abs(E.ind - P.ind), 'indirect calls: ELF %d, port %d' % (E.ind, P.ind))
    if E.size and P.size and not (0.4 <= P.size / E.size <= 2.5):
        add('size', 1, 'size: ELF %d bytes, port %d' % (E.size, P.size))
    if max(E.nbr, P.nbr) >= 6 and abs(E.nbr - P.nbr) > 0.5 * max(E.nbr, P.nbr):
        add('nbr', 1, 'conditional branches: ELF %d, port %d' % (E.nbr, P.nbr))
    out.sort(key=lambda x: -x[0])
    return sum(x[0] for x in out), out


def _virt(E, P, ref, port):
    """A virtual function called directly on one side (the compiler knew the object's type) and
    through the vtable on the other counts as the same call."""
    for A, B, ctx in ((P, E, port), (E, P, ref)):
        for k in sorted(A.calls):
            extra = A.calls[k] - B.calls.get(k, 0)
            spare = B.ind - A.ind
            if extra > 0 and spare > 0 and k in ctx.virt:
                m = min(extra, spare)
                A.calls[k] -= m
                if A.calls[k] <= 0:
                    del A.calls[k]
                A.ind += m
    return E, P


def _cost(E, P):
    return compare(E, P, flatten=False)[0]


def _copy(F):
    G = L.Feat()
    G.add(F)
    G.size = F.size
    return G


def _flatten(E, P, ref, port, rounds=12):
    """Replace a callee that only one side calls by its body's features when that lowers the cost
    (the other compiler, or the other source, inlined it)."""
    E, P = _copy(E), _copy(P)
    # a callee only one side calls that is a tiny leaf (an accessor, an empty or field-setting
    # constructor) was inlined by the other compiler: folded in without a cost test
    for A, B, ctx in ((P, E, port), (E, P, ref)):
        for k in [k for k in A.calls if k not in B.calls and k in A.calladdr]:
            sub = ctx.feat(A.calladdr[k])
            if sub is not None and sub.size <= 64 and not sub.calls and not sub.ind:
                n = A.calls.pop(k)
                for _i in range(n):
                    A.add(sub)
    best = _cost(E, P)
    for _ in range(rounds):
        moved = False
        cands = []
        for k in set(P.calls) - set(E.calls):
            if k in P.calladdr:
                cands.append(('P', k))
        for k in set(E.calls) - set(P.calls):
            if k in E.calladdr:
                cands.append(('E', k))
        for k in set(P.calls) & set(E.calls):
            if P.calls[k] != E.calls[k]:
                cands.append(('P' if P.calls[k] > E.calls[k] else 'E', k))
        for side, k in sorted(cands):
            A = P if side == 'P' else E
            ctx = port if side == 'P' else ref
            sub = ctx.feat(A.calladdr[k])
            if sub is None or sub.size > 1200:
                continue
            T = _copy(A)
            n = T.calls[k] if side == 'P' and k not in E.calls or side == 'E' and k not in P.calls else abs(P.calls[k] - E.calls.get(k, 0)) if side == 'P' else abs(E.calls[k] - P.calls.get(k, 0))
            n = max(1, min(n, T.calls[k]))
            for _i in range(n):
                T.add(sub)
            T.calls[k] -= n
            if T.calls[k] <= 0:
                del T.calls[k]
            c = _cost(E, T) if side == 'P' else _cost(T, P)
            if c < best:
                best = c
                if side == 'P':
                    P = T
                else:
                    E = T
                moved = True
                break
        if not moved:
            break
    return E, P


# ---------------------------------------------------------------- driver
class Scanner:
    def __init__(self, build='head', fpdir=None):
        self.ref = Ref()
        self.port = Port(build, fpdir)
        self.files = L.src_files(self.port.commit)
        self.fences = L.all_fences(self.files)

    def scan(self, mwname):
        """dict(score, diffs, how, port) for one fenced function, or None when unmapped."""
        r = self.ref.elf.byname.get(mwname)
        if not r or r[0] not in self.ref.elf.funcs:
            return {'error': 'no ELF function'}
        fence = self.fences.get(mwname)
        if fence is None:
            # no fence (an unmarked function): the readable qualified name, when it is unique
            starts = self.port.bykey.get(L.mw_key(mwname), [])
            start, how = (starts[0], 'name') if len(starts) == 1 else (None, 'none')
            if start is None:
                return {'error': 'no fence'}
        else:
            start, how = self.port.find(fence, mwname)
        if start is None:
            return {'error': 'no port symbol'}
        E = self.ref.feat(r[0])
        P = self.port.feat(start)
        score, diffs = compare(E, P, self.ref, self.port)
        return {'score': round(score, 2), 'diffs': diffs, 'how': how, 'port': self.port.elf.funcs[start][0],
                'fence': fence}


def read_list(name):
    p = os.path.join(AUDIT, name + '.md')
    rows = []
    for line in open(p, encoding='utf-8'):
        m = re.match(r'\|\s*(\d+)\s*\|\s*(0x[0-9a-f]+)\s*\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*(\S+)\s*\|', line)
        if m:
            rows.append((int(m.group(1)), int(m.group(2), 16), int(m.group(3)), m.group(4), m.group(5)))
    return rows


def short(diffs, n=3, width=240):
    s = '; '.join(d[2] for d in diffs[:n])
    if len(diffs) > n:
        s += '; +%d more' % (len(diffs) - n)
    return s[:width].replace('|', '/')


def main():
    sc = Scanner(arg('--build', 'head'), arg('--fp'))
    if '--fn' in sys.argv:
        a = arg('--fn')
        name = sc.ref.elf.funcs[int(a, 16)][0] if a.startswith('0x') else a
        r = sc.scan(name)
        print(L.mw_readable(name), {k: v for k, v in r.items() if k != 'diffs'})
        for w, k, t, n in r.get('diffs', []):
            print('  %5.2f %-6s %s' % (w, k, t))
        return
    if '--list' in sys.argv:
        name = arg('--list')
        rows = read_list(name)
        out = 'scan-' + name
        title = 'Scan of audit list %s' % name
    elif '--all' in sys.argv:
        rows = []
        for n, f in sorted(sc.fences.items(), key=lambda x: (x[1][0], x[1][1])):
            r = sc.ref.elf.byname.get(n)
            if r and r[0] in sc.ref.elf.funcs:
                rows.append((len(rows) + 1, r[0], sc.ref.elf.funcs[r[0]][1], n, f[0][4:]))
        out = 'scan-all'
        title = 'Scan of every fenced function'
    else:
        print(__doc__)
        return
    res = []
    for k, a, size, n, f in rows:
        r = sc.scan(n)
        res.append((k, a, size, n, f, r))
    ok = [x for x in res if 'score' in x[5]]
    ok.sort(key=lambda x: (-x[5]['score'], x[0]))
    bad = [x for x in res if 'score' not in x[5]]
    text = ['# %s' % title, '',
            'auditscan.py on fingerprint build `%s` (commit %s). %d functions, %d compared, %d not mapped. '
            'Score = weighted differences (see SCAN_VALIDATION.md for what a score means); 0 = no '
            'difference found, which does not prove MATCH. Ranked, highest first.'
            % (sc.port.name, sc.port.commit[:8], len(res), len(ok), len(bad)), '',
            '| rank | # | Address | Bytes | Function | Score | Differences |', '|---|---|---|---|---|---|---|']
    n_diff = 3 if out != 'scan-all' else 2
    for i, (k, a, size, n, f, r) in enumerate(ok):
        text.append('| %d | %d | 0x%x | %d | %s | %.1f | %s |' % (i + 1, k, a, size, L.mw_readable(n).replace('|', '/')[:70],
                                                              r['score'], short(r['diffs'], n_diff)))
    if bad:
        text += ['', 'Not compared:', '']
        text += ['- %d 0x%x `%s`: %s' % (k, a, n, r['error']) for k, a, size, n, f, r in bad]
    if out != 'scan-all':
        text += ['', '## All differences', '']
        for i, (k, a, size, n, f, r) in enumerate(ok):
            if r['diffs']:
                text.append('- #%d 0x%x %s (%.1f): %s' % (k, a, L.mw_readable(n), r['score'], '; '.join(d[2] for d in r['diffs'])))
    os.makedirs(AUDIT, exist_ok=True)
    p = os.path.join(AUDIT, out + '.md')
    open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(text) + '\n')
    if '--json' in sys.argv:
        json.dump([{'row': k, 'address': '0x%x' % a, 'bytes': size, 'symbol': n, 'file': f,
                    'score': r.get('score'), 'error': r.get('error'),
                    'diffs': [[d[0], d[1], d[2]] for d in r.get('diffs', [])]} for k, a, size, n, f, r in res],
                  open(os.path.join(AUDIT, out + '.json'), 'w'), indent=0)
    print('%s: %d functions, %d compared, %d with no difference' % (os.path.relpath(p, _dev.REPO), len(res), len(ok),
                                                                   sum(1 for x in ok if x[5]['score'] == 0)))


if __name__ == '__main__':
    main()
