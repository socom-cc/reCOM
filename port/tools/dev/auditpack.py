"""auditpack.py <list> [--rows 1,3-5] [--jobs N]: one ready-to-read packet per function of an audit
list (build/port/audit/<list>.md, made by auditlist.py), for the correctness audit
(docs/port/AUDIT_PLAN.md). Writes build/port/audit/packets/<list>/<row>-<address>.md and INDEX.md.

A packet holds, for one function:
- header: readable signature, address, size, the fence's file and lines, ELF callers (xref.py's
  jal scan: count and names);
- leads: lines of docs/port/notes/*.md that name the function's address or Class::Method;
- the port's source body (fence comment to closing brace, with line numbers, working tree);
- declarations it needs: the receiver class's member lines whose names the body uses, and one
  declaration line per ELF callee (from the src/ headers);
- members touched: the DWARF member names cz.py gives the offsets used through the receiver and
  through pointer-to-class arguments (offset, name, load / store);
- the ELF disassembly as z.sh prints it (dis.sh | disx.py | cz.py -t arg0=<Class>,...: saved
  registers dropped, labels on branch targets, '|' marks a delay slot, lui / addiu / $gp data by
  symbol and strings inline), plus: call targets demangled, float words loaded from memory decoded
  (lwc1 ... ; 0xADDR sym = 0.5f), string pointers read from data shown, jump tables resolved
  case by case.
A function over 3,000 bytes gets its disassembly in parts (<row>-<address>.part<k>.md, about 2,400
bytes of code each, cut at labels = basic-block starts, each with its address range and offset).
Reads <scratch>/ref.dis (refdis.sh makes it). Read-only on the ELF and the checkout."""
import _dev
import auditlib as L
import auditscan
import bisect
import collections
import concurrent.futures
import glob
import os
import re
import subprocess
import sys

AUDIT = os.path.join(_dev.REPO, 'build', 'port', 'audit')
SPLIT = 3000
PART = 2400


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


# ---------------------------------------------------------------- one-time indexes
class Index:
    def __init__(self):
        self.ref = L.ref()
        self.dis = L.ref_dis()
        self.callers = collections.defaultdict(list)
        pat = re.compile(r'^\s*([0-9a-f]+):\s+jal\s+([0-9a-f]+)')
        for l in self.dis.lines:
            if 'jal\t' in l:
                m = pat.match(l)
                if m:
                    self.callers[int(m.group(2), 16)].append(int(m.group(1), 16))
        self.notes = []
        for p in sorted(glob.glob(os.path.join(_dev.REPO, 'docs', 'port', 'notes', '*.md'))):
            for i, l in enumerate(open(p, encoding='utf-8', errors='replace')):
                self.notes.append((os.path.basename(p), i + 1, l.rstrip('\n')))
        self.files = L.src_files()
        self.fences = L.all_fences(self.files)
        self.classes = {}            # last name component -> (file, first line, last line)
        self.decl = collections.defaultdict(list)    # function name -> [(file, line, text)]
        cre = re.compile(r'^\s*(?:class|struct)\s+(?:\w+\s+)*?(\w+)\s*(?:final\s*)?(?::[^{;]*)?\{?\s*$')
        for p, text in self.files.items():
            if not p.endswith(('.h', '.hpp', '.inl')):
                continue
            lines = text.split('\n')
            for i, l in enumerate(lines):
                m = cre.match(l)
                if m and not l.rstrip().endswith(';'):
                    j = i
                    while j < len(lines) and '{' not in lines[j] and j < i + 4:
                        j += 1
                    if j >= len(lines) or '{' not in lines[j]:
                        continue
                    depth, k = 0, j
                    while k < len(lines):
                        depth += lines[k].count('{') - lines[k].count('}')
                        if depth <= 0:
                            break
                        k += 1
                    self.classes.setdefault(m.group(1), (p, i + 1, k + 1))
                for fm in re.finditer(r'\b(~?\w+)\s*\(', l):
                    s = l.strip()
                    if s.startswith(('//', '*', '#', 'return')) or not (s.endswith((';', '{', ')')) or '{' in s):
                        continue
                    self.decl[fm.group(1)].append((p, i + 1, s))


IX = None


def readable_callee(name):
    r = L.mw_readable(name)
    return r if len(r) < 110 else r[:107] + '...'


def cz(lines, types):
    """z.sh's pipeline (disx.py | cz.py) on objdump lines already in hand."""
    dev = _dev.DEV
    env = dict(os.environ)
    p1 = subprocess.run([sys.executable, os.path.join(dev, 'disx.py')], input='\n'.join(lines) + '\n',
                        capture_output=True, text=True, env=env)
    a = [sys.executable, os.path.join(dev, 'cz.py')]
    if types:
        a += ['-t', ','.join('%s=%s' % kv for kv in types)]
    p2 = subprocess.run(a, input=p1.stdout, capture_output=True, text=True, env=env)
    return p2.stdout.split('\n')


def class_args(name):
    """cz.py -t pairs: arg0 = the receiver's class, argN = a pointer / reference-to-class parameter."""
    if L._mw is None:
        return []
    d = L._mw.demangle(name)
    if not d:
        return []
    out = []
    shift = 0
    if d['qualifier'] and d['params'] is not None:
        out.append(('arg0', L._mw.readable_qualified(d['qualifier'])))
        shift = 1
    for i, p in enumerate(d['params'] or []):
        if p.get('kind') == 'class' and set(p.get('modifiers', [])) & {'P', 'R'} and i + shift < 8:
            c = L._mw.readable_qualified(p['components'])
            if not c.startswith('std::'):
                out.append(('arg%d' % (i + shift), c))
    return out[:4]


FL = re.compile(r';\s*(0x[0-9a-f]+)\b')


def annotate(lines, start, end):
    """Demangled call targets, decoded float words, string pointers; returns (lines, jump tables)."""
    ref = IX.ref
    out = []
    tables = []
    seen = set()
    lui = {}
    for l in lines:
        if not l.strip():
            continue
        mu = re.search(r'\blui (\w+),0x([0-9a-f]+)', l)
        if mu:
            lui[mu.group(1)] = int(mu.group(2), 16) << 16
        ma = re.search(r'\baddiu (\w+),(\w+),(-?\d+)\s*$', l)
        if ma and ma.group(1) == ma.group(2) and ma.group(1) in lui:
            # Metrowerks shares one lui across delay slots; disx.py resolves only the first use
            a = (lui[ma.group(1)] + int(ma.group(3))) & 0xffffffff
            d = ref.data_at(a)
            s = ref.cstr(a)
            if d or s:
                l += '  ; 0x%x %s%s (lui above)' % (a, d[0] if d else '', ' %r' % s[:60] if s else '')
        m = re.search(r'\b(jal|j)\s+([^\s;]+)', l)
        if m and not re.match(r'L[0-9a-f]+$', m.group(2)):
            l = l.replace(m.group(2), readable_callee(m.group(2)), 1)
        m = FL.search(l)
        if m:
            a = int(m.group(1), 16)
            if re.search(r'\blwc1\b', l):
                w = ref.word(a)
                if w is not None:
                    l += ' = %.9gf' % ref.float_of(w)
            elif re.search(r'\blw\b', l):
                w = ref.word(a)
                s = ref.cstr(w) if w else None
                if s is not None:
                    l += ' -> %r' % s[:60]
            elif re.search(r'\b(addiu|ori)\b', l) and a not in seen:
                seen.add(a)
                t = []
                for k in range(256):
                    w = ref.word(a + 4 * k)
                    if w is None or not (start <= w < end):
                        break
                    t.append(w)
                if len(t) >= 2:
                    tables.append((a, t))
        out.append(l)
    return out, tables


def members(lines):
    """(offset, member, L/S) named by cz.py on typed registers."""
    got = collections.OrderedDict()
    for l in lines:
        m = re.match(r'^\S*\s*\|?\s*(l\w+|s[bhwdq]\w*)\s+[^,]+,(0x[0-9a-f]+)\((\w+)\)\s+;\s*([A-Za-z_][\w.:|@]*)', l)
        if m and m.group(3) not in ('sp', 'gp'):
            op = m.group(1)
            ls = 'S' if op.startswith('s') and not op.startswith(('sll', 'srl', 'sra', 'slt', 'sub')) else 'L'
            key = (int(m.group(2), 16), m.group(4))
            got.setdefault(key, set()).add(ls)
    return ['+0x%x %s %s' % (o, n, '/'.join(sorted(v))) for (o, n), v in sorted(got.items())]


def source_block(fence):
    p, fl, bl, el = fence
    lines = IX.files[p].split('\n')
    return p, fl, el, ['%5d %s' % (i + 1, lines[i]) for i in range(fl - 1, min(el, len(lines)))]


def declarations(name, body, callees):
    out = []
    toks = set(re.findall(r'\b[A-Za-z_]\w*\b', body))
    d = L._mw.demangle(name) if L._mw else None
    cls = L._mw.template_base(d['qualifier'][-1]) if d and d['qualifier'] else None
    if cls and cls in IX.classes:
        p, a, b = IX.classes[cls]
        lines = IX.files[p].split('\n')
        used = []
        for i in range(a, min(b, len(lines))):
            s = lines[i].strip()
            if not s.endswith(';') or s.startswith(('//', '/*', '*')) or '(' in s:
                continue
            ids = re.findall(r'\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*(?::\s*\d+)?\s*[;,=]', s)
            if set(ids) & toks:
                used.append('%5d %s' % (i + 1, s))
        if used:
            out.append('Members of %s the body uses (%s:%d-%d):' % (cls, p, a, b))
            out += used[:60]
    sig = []
    for c in callees:
        dd = L._mw.demangle(c) if L._mw else None
        fn = dd['name'] if dd else c
        q = L._mw.template_base(dd['qualifier'][-1]) if dd and dd['qualifier'] else None
        if fn == '__ct':
            fn = q
        elif fn == '__dt':
            fn = '~' + (q or '')
        if not fn:
            continue
        cands = IX.decl.get(fn, [])
        if q and q in IX.classes:
            p, a, b = IX.classes[q]
            inq = [x for x in cands if x[0] == p and a <= x[1] <= b]
            cands = inq or [x for x in cands if q in x[2]]
        if cands:
            p, ln, s = cands[0]
            sig.append('%s:%d: %s%s' % (p, ln, s[:150], '' if not q or q in s else '   [%s]' % q))
    if sig:
        out.append('Callee declarations:')
        out += sig
    return out


def leads(addr, name):
    rd = L.mw_readable(name)
    short = rd.split('(')[0]
    pats = [re.compile(r'0x0*%x\b' % addr, re.I)]
    if '::' in short:
        pats.append(re.compile(r'(?<![\w:])%s(?![\w])' % re.escape(short)))
    out = []
    for n, ln, l in IX.notes:
        if any(p.search(l) for p in pats):
            out.append('- %s:%d: %s' % (n, ln, l.strip()[:300]))
    if len(out) > 10:
        out = out[:10] + ['- ... %d more lines' % (len(out) - 10)]
    return out


def packet(row, name, outdir):
    k, addr, size, sym, f = row
    ref = IX.ref
    fn = ref.funcs.get(addr)
    end = addr + (fn[1] if fn else size)
    ins = IX.dis.insns(addr, end)
    types = class_args(sym)
    z = cz([x[3] for x in ins], types)
    z, tables = annotate(z, addr, end)
    callers = IX.callers.get(addr, [])
    cnames = collections.Counter()
    for c in callers:
        g = ref.func_at(c)
        cnames[L.mw_readable(g[1]).split('(')[0] if g else '0x%x' % c] += 1
    callees = []
    for a, op, ops, raw in ins:
        if op in ('jal', 'j'):
            m = L.TARGET.match(ops.split(',')[-1].strip())
            if m and m.group(2) and '+' not in m.group(2) and m.group(2) not in callees:
                callees.append(m.group(2))
    rd = L.mw_readable(sym)
    head = ['# %d. %s' % (k, rd), '',
            '0x%x, %d bytes, `%s`. ELF callers: %d%s' % (addr, end - addr, sym, len(callers),
                                                           (' (' + ', '.join('%s%s' % (n, ' x%d' % c if c > 1 else '')
                                                                             for n, c in cnames.most_common(12)) + ')') if callers else '')]
    fence = IX.fences.get(sym)
    body_text = ''
    if fence:
        p, fl, el, src = source_block(fence)
        st = 'W'
        head.append('Port: %s lines %d-%d.' % (p, fl, el))
        body_text = '\n'.join(src)
    else:
        src = []
        head.append('Port: no fence for this symbol in src/.')
    text = head + ['']
    ld = leads(addr, sym)
    if ld:
        text += ['## Leads (docs/port/notes)', ''] + ld + ['']
    text += ['## Port source', '', '```cpp'] + src + ['```', '']
    dc = declarations(sym, body_text, callees)
    if dc:
        text += ['## Declarations', ''] + dc + ['']
    mem = members(z)
    if mem:
        text += ['## Members touched (%s)' % ', '.join('%s=%s' % t for t in types), ''] + [', '.join(mem)] + ['']
    if tables:
        text += ['## Jump tables', '']
        for a, t in tables:
            text.append('- 0x%x (%d): %s' % (a, len(t), ', '.join('%d L%x' % (i, w) for i, w in enumerate(t))))
        text.append('')
    base = '%d-%x' % (k, addr)
    parts = []
    if end - addr > SPLIT:
        cur, cur_n, cur_a = [], 0, addr
        for l in z:
            lab = re.match(r'^L([0-9a-f]+):', l)
            if lab and cur_n * 4 >= PART:
                parts.append((cur_a, int(lab.group(1), 16), cur))
                cur, cur_n, cur_a = [], 0, int(lab.group(1), 16)
            cur.append(l)
            if not l.startswith('L') or len(l.split()) > 1:
                cur_n += 1
        parts.append((cur_a, end, cur))
        text += ['## ELF disassembly: %d parts' % len(parts), '']
        for i, (a, b, ls) in enumerate(parts):
            pn = '%s.part%d.md' % (base, i + 1)
            text.append('- [%s](%s): 0x%x-0x%x (+0x%x)' % (pn, pn, a, b, a - addr))
            open(os.path.join(outdir, pn), 'w', encoding='utf-8', newline='\n').write(
                '\n'.join(['# %d. %s: part %d of %d, 0x%x-0x%x (+0x%x..+0x%x)' % (k, rd, i + 1, len(parts), a, b, a - addr, b - addr),
                           '', '```'] + ls + ['```']) + '\n')
    else:
        text += ['## ELF disassembly', '', '```'] + z + ['```']
    p = os.path.join(outdir, base + '.md')
    open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(text) + '\n')
    return k, addr, end - addr, rd, base, os.path.getsize(p) + sum(os.path.getsize(os.path.join(outdir, '%s.part%d.md' % (base, i + 1))) for i in range(len(parts))), len(parts)


def main():
    global IX
    if len(sys.argv) < 2 or sys.argv[1].startswith('-'):
        print(__doc__)
        return
    name = sys.argv[1]
    rows = auditscan.read_list(name)
    if '--rows' in sys.argv:
        want = set()
        for part in arg('--rows').split(','):
            a, _, b = part.partition('-')
            want.update(range(int(a), int(b or a) + 1))
        rows = [r for r in rows if r[0] in want]
    IX = Index()
    outdir = os.path.join(AUDIT, 'packets', name)
    os.makedirs(outdir, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(int(arg('--jobs', '6'))) as ex:
        res = list(ex.map(lambda r: packet(r, name, outdir), rows))
    idx = ['# Packets for audit list %s' % name, '',
           'auditpack.py: one file per function (ELF disassembly in parts above %d bytes). Read the '
           'packet instead of fetching the disassembly, the source and the notes one by one.' % SPLIT, '',
           '| # | Address | Bytes | Function | Packet | Packet KB | Parts |', '|---|---|---|---|---|---|---|']
    for k, a, sz, rd, base, b, np_ in res:
        idx.append('| %d | 0x%x | %d | %s | [%s.md](%s.md) | %.1f | %s |' % (k, a, sz, rd.replace('|', '/')[:80], base, base, b / 1024, np_ or ''))
    open(os.path.join(outdir, 'INDEX.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(idx) + '\n')
    print('%s: %d packets, %.0f KB' % (os.path.relpath(outdir, _dev.REPO), len(res), sum(r[5] for r in res) / 1024))


if __name__ == '__main__':
    main()
