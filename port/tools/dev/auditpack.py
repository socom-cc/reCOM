"""auditpack.py <list> [--rows 1,3-5] [--by-file] [--jobs N] [--out DIR]: ready-to-read packets for
an audit list (build/port/audit/<list>.md, made by auditlist.py), for the correctness audit
(docs/port/AUDIT_PLAN.md). Writes build/port/audit/packets/<list>/ (or DIR) and its INDEX.md:
one <row>-<address>.md per function, or with --by-file (for the small band) one
f<n>-<file>.md per source file holding all of that file's listed functions, with the facts they
share (helpers, enums, class members, callee declarations, leads) once at the top.

A function's part of a packet holds:
- header: readable signature, address, size, the definition's file and lines, ELF callers
  (xref.py's jal scan: count and names);
- leads: lines of docs/port/notes/*.md that name the function's address or Class::Method;
- the port's source: the fence line, then the definition itself, found by the fence's demangled
  name (a helper or a `namespace {` between them is skipped and named), to its closing brace;
- helpers: the bodies of what the body calls, one level deep, each once: same-file static,
  unnamed-namespace, inline and unfenced functions, the receiver class's header definitions, and
  a header definition of 40 lines or fewer when it is the only one of its name (60 lines each,
  250 a packet; the cut is said);
- declarations: the receiver class's member lines whose names the body uses, and one declaration
  line per ELF callee (from the src/ headers);
- enums: the DWARF value of every enumerator the body and its helpers name;
- members touched: the DWARF member names cz.py gives the offsets used through a register while
  it still holds the receiver or a pointer-to-class argument; other offsets by number only;
- virtual calls: each jalr's vtable slot, resolved in the class's vtable when the object's
  register is typed, else the methods at that slot whose names the body calls;
- the ELF disassembly as z.sh prints it (dis.sh | disx.py | cz.py -k -t arg0=<Class>,...: saved
  registers dropped, a label on every branch target, '|' marks a delay slot, a nop in one is
  '| nop', lui / addiu / $gp data by symbol and strings inline), plus: call targets demangled,
  float words loaded from memory decoded (lwc1 ... ; 0xADDR sym = 0.5f), strings of 0 and 1
  characters, the words, halves and bytes loaded from data (`= word` for a literal, `init` for a
  variable's initial value), string pointers read from data shown, jump tables resolved.
A function over 3,000 bytes gets its disassembly in parts (<row>-<address>.part<k>.md, about 2,400
bytes of code each, cut at labels = basic-block starts, each with its address range and offset).
Reads <scratch>/ref.dis (refdis.sh makes it). Read-only on the ELF and the checkout."""
import _dev
import auditlib as L
import auditscan
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
HELPER_LINES = 60
HELPERS_MAX = 250
HELPERS_MAX_FILE = 400
HEADER_INLINE = 40


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
        self.code = {p: L.strip_code(t) for p, t in self.files.items()}
        self.lines = {p: t.split('\n') for p, t in self.files.items()}
        self.clines = {p: c.split('\n') for p, c in self.code.items()}
        self.defs = {p: L.definitions(p, self.files[p], self.code[p]) for p in self.files}
        self.defs_by_name = collections.defaultdict(list)
        for ds in self.defs.values():
            for d in ds:
                self.defs_by_name[d.name].append(d)
        self.fenced_heads = collections.defaultdict(set)
        for n, f in self.fences.items():
            self.fenced_heads[f[0]].add(f[2])
        self.namespaces = set()
        for t in self.files.values():
            self.namespaces.update(re.findall(r'\bnamespace\s+([A-Za-z_]\w*)', t))
        self.vt = L.vtables(self.ref)
        self.slots = collections.defaultdict(list)     # slot offset -> [(method name, readable)]
        for cls, (n, v, sz) in self.vt.items():
            for k in range(2, sz // 4):
                w = self.ref.word(v + 4 * k)
                f = self.ref.funcs.get(w)
                if f:
                    rd = L.mw_readable(f[0])
                    self.slots[4 * k].append((L._fence_target(f[0])[0], rd))
        self.classes = {}            # last name component -> (file, first line, last line)
        self.decl = collections.defaultdict(list)    # function name -> [(file, line, text)]
        cre = re.compile(r'^\s*(?:class|struct)\s+(?:\w+\s+)*?(\w+)\s*(?:final\s*)?(?::[^{;]*)?\{?\s*$')
        for p, text in self.files.items():
            if not p.endswith(('.h', '.hpp', '.inl')):
                continue
            lines = self.lines[p]
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
                    if re.search(r'[(=.]|->|return', l[:fm.start()]):
                        continue            # a call inside a statement, not a declaration
                    self.decl[fm.group(1)].append((p, i + 1, s))


IX = None


def readable_callee(name):
    r = L.mw_readable(name)
    return r if len(r) < 110 else r[:107] + '...'


def cz(lines, types):
    """z.sh's pipeline (disx.py | cz.py -k) on objdump lines already in hand."""
    dev = _dev.DEV
    env = dict(os.environ)
    p1 = subprocess.run([sys.executable, os.path.join(dev, 'disx.py')], input='\n'.join(lines) + '\n',
                        capture_output=True, text=True, env=env)
    a = [sys.executable, os.path.join(dev, 'cz.py'), '-k']
    if types:
        a += ['-t', ','.join('%s=%s' % kv for kv in types)]
    p2 = subprocess.run(a, input=p1.stdout, capture_output=True, text=True, env=env)
    if p2.returncode:
        sys.stderr.write(p2.stderr[-2000:])
    return p2.stdout.split('\n')


def _npar(text, fn):
    m = re.search(r'\b%s\s*\(' % re.escape(fn), text)
    if not m:
        return None
    e = L._close(text, m.end() - 1)
    inner = text[m.end():e - 1] if e > 0 else ''
    if not inner.strip() or inner.strip() == 'void':
        return 0
    depth, n = 0, 1
    for c in inner:
        depth += c in '(<[' and 1 or c in ')>]' and -1 or 0
        n += c == ',' and depth == 0
    return n


def is_static(cls, fn, npar):
    """The class's declarations of fn with npar parameters (its header, else its source file's
    in-class definitions) are static."""
    if fn.startswith('__'):
        return False
    if cls in IX.classes:
        p, a, b = IX.classes[cls]
        ds = [x[2] for x in IX.decl.get(fn, []) if x[0] == p and a <= x[1] <= b]
        flags = [bool(re.match(r'(?:\w+\s+)*?static\b', s)) for s in ds if _npar(s, fn) in (npar, None)]
    else:
        ds = [d for d in IX.defs_by_name.get(fn, []) if d.cls == cls and d.in_class]
        flags = [d.static for d in ds]
    return bool(flags) and all(flags)


def class_args(name):
    """cz.py -t pairs: arg0 = the receiver's class, argN = a pointer / reference-to-class parameter."""
    if L._mw is None:
        return []
    d = L._mw.demangle(name)
    if not d:
        return []
    out = []
    shift = 0
    q = [c for c in d['qualifier'] if not c.startswith('@unnamed@')]
    # a receiver only for a class: a free function in a namespace (zdb::, an unnamed one) has none,
    # nor a member the class declares static
    if q and d['params'] is not None and (IX is None or (L._mw.template_base(q[-1]) not in IX.namespaces
                                                         and not is_static(L._mw.template_base(q[-1]), d['name'],
                                                                           L._fence_target(name)[2]))):
        out.append(('arg0', L._mw.readable_qualified(d['qualifier'])))
        shift = 1
    for i, p in enumerate(d['params'] or []):
        if p.get('kind') == 'class' and set(p.get('modifiers', [])) & {'P', 'R'} and i + shift < 8:
            c = L._mw.readable_qualified(p['components'])
            if not c.startswith('std::'):
                out.append(('arg%d' % (i + shift), c))
    return out[:4]


FL = re.compile(r';\s*(0x[0-9a-f]+)\b')


def short_str(a):
    """The text at a when it is a C string (also of 0 or 1 characters at a Metrowerks literal)."""
    ref = IX.ref
    s = ref.cstr(a)
    if s is not None:
        return s
    d = ref.data_at(a)
    if d and d[1] == 0 and d[0].startswith('@'):
        b0 = ref.word(a & ~3)
        if b0 is None:
            return None
        bs = b0.to_bytes(4, 'little')[a & 3:] + (ref.word((a & ~3) + 4) or 0).to_bytes(4, 'little')
        if bs[0] == 0:
            return ''
        if 32 <= bs[0] < 127 and bs[1] == 0:
            return chr(bs[0])
    return None


def data_value(a, op):
    """' = word 0x..' / ' init 0x..' for a load from data at a (halves and bytes by value)."""
    ref = IX.ref
    w = ref.word(a & ~3)
    if w is None:
        return ''
    if op in ('lb', 'lbu'):
        v = (w >> (8 * (a & 3))) & 0xff
        v = v - 256 if op == 'lb' and v & 0x80 else v
        val = '%d' % v
    elif op in ('lh', 'lhu'):
        v = (w >> (8 * (a & 2))) & 0xffff
        v = v - 65536 if op == 'lh' and v & 0x8000 else v
        val = '%d' % v
    else:
        if a & 3:
            return ''
        val = '0x%x' % w
        if w in ref.at:
            val += ' -> ' + ref.at[w][0]
    d = ref.data_at(a)
    lit = d and d[0].startswith('@')
    if not lit and val in ('0', '0x0'):
        return ''                      # a variable starting at zero: nothing to say
    return ' %s %s' % ('= word' if lit else 'init', val)


def annotate(lines, start, end):
    """Demangled call targets, decoded float words, short strings, data words, string pointers;
    returns (lines, jump tables)."""
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
            s = short_str(a)
            if d or s is not None:
                l += '  ; 0x%x %s%s (lui above)' % (a, d[0] if d else '', ' %r' % s[:60] if s is not None else '')
        m = re.search(r'\b(jal|j)\s+([^\s;]+)', l)
        if m and not re.match(r'L[0-9a-f]+$', m.group(2)):
            l = l.replace(m.group(2), readable_callee(m.group(2)), 1)
        m = FL.search(l)
        if m:
            a = int(m.group(1), 16)
            mo = re.match(r'^\S*\s*\|?\s*(\w+)', l)
            op = mo.group(1) if mo else ''
            if op == 'lwc1':
                w = ref.word(a)
                if w is not None:
                    l += ' = %.9gf' % ref.float_of(w)
            elif op == 'lw':
                w = ref.word(a)
                s = short_str(w) if w and ref.range[0] <= w < ref.range[1] else None
                if s is not None:
                    l += ' -> %r' % s[:60]
                else:
                    l += data_value(a, op)
            elif op in ('lb', 'lbu', 'lh', 'lhu'):
                l += data_value(a, op)
            elif op in ('addiu', 'ori'):
                if "'" not in l and '"' not in l:
                    s = short_str(a)
                    if s is not None and len(s) <= 1:
                        l += ' %r' % s
                if a not in seen:
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


MEMLINE = re.compile(r'^\S*\s*\|?\s*(l\w+|s[bhwdq]\w*)\s+[^,]+,(0x[0-9a-f]+)\((\w+)\)(?:\s+;\s*([A-Za-z_][\w.:|@]*))?')


def members(lines):
    """([(offset, member, L/S)] named by cz.py on typed registers, [other offset L/S])."""
    got = collections.OrderedDict()
    other = collections.OrderedDict()
    for l in lines:
        m = MEMLINE.match(l)
        if m and m.group(3) not in ('sp', 'gp', 'at'):
            op = m.group(1)
            if op in ('lui', 'li', 'la') or op.startswith(('sll', 'srl', 'sra', 'slt', 'sub')):
                continue
            ls = 'S' if op.startswith('s') else 'L'
            o = int(m.group(2), 16)
            note = l.split(';', 1)[1].strip() if ';' in l else ''
            if m.group(4):
                got.setdefault((o, m.group(4)), set()).add(ls)
            elif not note:              # a global's address is in the note: not a member
                other.setdefault(o, set()).add(ls)
    named = ['+0x%x %s %s' % (o, n, '/'.join(sorted(v))) for (o, n), v in sorted(got.items())]
    rest = ['+0x%x %s' % (o, '/'.join(sorted(v))) for o, v in sorted(other.items())]
    return named, rest


def vcalls(ins, types, called):
    """[text] per jalr: the vtable slot it calls, resolved when the object's register is typed."""
    seq = [(op, [x.strip() for x in ops.split(',')] if ops else []) for a, op, ops, raw in ins]
    init = {'a' + r[3:]: c for r, c in types}
    st = L.reg_types(seq, init)
    out = []
    for i, (a, op, ops, raw) in enumerate(ins):
        if op != 'jalr':
            continue
        r = seq[i][1][-1] if seq[i][1] else ''
        slot = base = None
        for j in range(i - 1, max(-1, i - 8), -1):
            o2, a2 = seq[j]
            if a2 and a2[0] == r and o2 not in L.NOWRITE:
                mm = L.MEMOP.match(a2[1]) if o2 == 'lw' and len(a2) == 2 else None
                if mm:
                    slot, vr = int(mm.group(1), 0), mm.group(2)
                    for k in range(j - 1, max(-1, j - 8), -1):
                        o3, a3 = seq[k]
                        if a3 and a3[0] == vr and o3 not in L.NOWRITE:
                            m3 = L.MEMOP.match(a3[1]) if o3 == 'lw' and len(a3) == 2 else None
                            if m3:
                                base = (int(m3.group(1), 0), m3.group(2), st[k].get(m3.group(2)))
                            break
                break
        if slot is None or base is None:
            continue
        voff, breg, cls = base
        txt = '0x%x jalr: slot +0x%x of the vtable at +0x%x(%s)' % (a, slot, voff, breg)
        hit = IX.vt.get(L._squash(cls)) if cls else None
        if hit:
            w = IX.ref.word(hit[1] + slot)
            f = IX.ref.funcs.get(w)
            txt += ' (%s): %s' % (cls, L.mw_readable(f[0]) if f else '0x%x' % (w or 0))
        else:
            names = collections.OrderedDict()
            for n, rd in IX.slots.get(slot, []):
                if n in called:
                    names.setdefault(rd, 1)
            if names:
                ns = list(names)
                txt += ', type not known; at this slot and called in the body: %s%s' % (
                    '; '.join(ns[:4]), ' (+%d more)' % (len(ns) - 4) if len(ns) > 4 else '')
            else:
                txt += ', type not known'
        out.append(txt)
    return out


def source_block(fence):
    """(path, first line, last line, numbered lines, skipped (a, b) or None)."""
    p, fl, hl, bl, el = fence
    lines = IX.lines[p]
    code = IX.clines[p]
    out = ['%5d %s' % (fl, lines[fl - 1])]
    k = fl
    while k < len(lines) and L.FENCE.match(lines[k]) and L.FENCE.match(lines[k]).group(2) == L.FENCE.match(lines[fl - 1]).group(2):
        out.append('%5d %s' % (k + 1, lines[k]))
        k += 1
    s = hl - 1
    while s - 1 >= k and not code[s - 1].strip() and lines[s - 1].strip() and not lines[s - 1].lstrip().startswith('#'):
        s -= 1             # the comment right above the head belongs to it
    skipped = None
    if s > k:
        while k < s and not lines[k].strip():
            k += 1
        if s > k:
            skipped = (k + 1, s)
            out.append('      ... line%s %s: between the fence and the definition (helpers it calls are below)'
                       % ('s' if s > k + 1 else '', '%d-%d' % skipped if s > k + 1 else k + 1))
    out += ['%5d %s' % (i + 1, lines[i]) for i in range(s, min(el, len(lines)))]
    return p, fl, el, out, skipped


def declarations(name, body, callees):
    out = []
    toks = set(re.findall(r'\b[A-Za-z_]\w*\b', body))
    d = L._mw.demangle(name) if L._mw else None
    cls = L._mw.template_base(d['qualifier'][-1]) if d and d['qualifier'] else None
    if cls and cls in IX.classes:
        p, a, b = IX.classes[cls]
        lines = IX.lines[p]
        used = []
        for i in range(a, min(b, len(lines))):
            s = lines[i].strip()
            if not s.endswith(';') or s.startswith(('//', '/*', '*')) or '(' in s:
                continue
            ids = re.findall(r'\b([A-Za-z_]\w*)\s*(?:\[[^\]]*\])*\s*(?::\s*\d+)?\s*[;,=]', s)
            if set(ids) & toks:
                used.append('%5d %s' % (i + 1, s))
        if used:
            out.append(('Members of %s the body uses (%s:%d-%d):' % (cls, p, a, b), used[:60]))
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
        out.append(('Callee declarations:', sig))
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


# ---------------------------------------------------------------- helpers, enums
def body_code(fence):
    p, fl, hl, bl, el = fence
    return '\n'.join(IX.clines[p][bl - 1:el])


def find_helpers(path, code, cls, own, exclude, callees=()):
    """[Def] the code calls, one level: same-file local or unfenced definitions, the receiver
    class's header definitions, a unique short header definition (a free or Class:: call, not
    one through another object). A name the ELF calls out of line on another class is not taken."""
    out = []
    seen = set(exclude)
    elf = collections.defaultdict(set)      # simple name -> classes the ELF calls it on
    for c in callees:
        n_, c_, p_ = L._fence_target(c)
        elf[n_].add(c_)
    for n, via, q in L.called_names(code, kinds=True):
        if n == own:
            continue
        cands = [d for d in IX.defs.get(path, []) if d.name == n and
                 (d.local or d.head not in IX.fenced_heads[path]) and (not q or d.cls == q)]
        if not cands and cls and cls in IX.classes and via in ('', 'this'):
            hp = IX.classes[cls][0]
            cands = [d for d in IX.defs.get(hp, []) if d.name == n and d.cls == cls]
        if not cands and via in ('', '::'):
            hs = [d for d in IX.defs_by_name.get(n, []) if d.path.endswith(('.h', '.hpp', '.inl'))
                  and d.lines <= HEADER_INLINE and (not q or d.cls == q)]
            if len(hs) == 1:
                cands = hs
        cands = [d for d in cands if n not in elf or d.cls in elf[n]]
        for d in cands[:3]:
            key = (d.path, d.head)
            if key not in seen:
                seen.add(key)
                out.append(d)
    return out


def helper_text(ds, cap):
    """Numbered bodies of the helpers, HELPER_LINES each, cap lines in all."""
    out = []
    left = []
    for d in ds:
        if len(out) >= cap:
            left.append('%s (%s:%d)' % (d.name, d.path, d.head))
            continue
        kind = ', '.join(x for x, f in (('static', d.static), ('unnamed namespace', d.unnamed), ('inline', d.inline),
                                         ('in class %s' % d.cls, d.in_class)) if f) or 'not fenced'
        lines = IX.lines[d.path]
        s = d.head - 1
        while s - 1 >= 0 and not IX.clines[d.path][s - 1].strip() and lines[s - 1].strip() \
                and not lines[s - 1].lstrip().startswith('#') and d.head - s < 8:
            s -= 1
        n = min(d.end - s, HELPER_LINES, max(4, cap - len(out)))
        out.append('// %s: %s:%d-%d (%s)' % (d.name, d.path, d.head, d.end, kind))
        out += ['%5d %s' % (i + 1, lines[i]) for i in range(s, s + n)]
        if s + n < d.end:
            out.append('      ... %d more lines (to %d)' % (d.end - s - n, d.end))
    if left:
        out.append('// not shown (packet cap): ' + ', '.join(left))
    return out


def enums_used(code):
    """{enum: [(name, value, size)]} for the DWARF enumerators the code names: a name written
    Enum::NAME takes that enum only; a bare name (not a call, not a member) up to three enums
    outside std::."""
    E = L.enumerators()
    got = collections.OrderedDict()
    uses = collections.OrderedDict()
    for m in re.finditer(r'(?:([A-Za-z_]\w*)\s*::\s*|(->|\.)\s*)?\b([A-Za-z_]\w*)\b(\s*\()?', code):
        t = m.group(3)
        if t in E and len(t) > 2 and not m.group(2) and not m.group(4):
            uses.setdefault(t, set()).add(m.group(1))
    words = set(re.findall(r'\b[A-Za-z_]\w*\b', code))
    for t, qs in uses.items():
        qs.discard(None)
        cands = [x for x in E[t] if x[0].split('::')[-1] in qs] if qs else \
            [x for x in E[t] if not x[0].startswith('std::')][:3]
        if not qs and t.isalpha() and t.islower():
            # a plain word (left, end) only with its enum's name in the code
            cands = [x for x in cands if x[0].split('::')[-1] in words]
        for q, v, sz in cands:
            got.setdefault(q, []).append((t, v, sz))
    return got


def enum_text(got, cap=60):
    out = []
    n = 0
    fmt = lambda t, v, sz: '%s=%d' % (t, v) if v >= 0 or sz >= 4 else '%s=%d (0x%x)' % (t, v, v & ((1 << (8 * sz)) - 1))
    for q, items in got.items():
        if n >= cap:
            out.append('- ... %d more enums' % (len(got) - len(out)))
            break
        out.append('- %s: %s' % (q, ', '.join(fmt(*x) for x in items)))
        n += len(items)
    return out


# ---------------------------------------------------------------- one function
def facts(row):
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
    F = dict(k=k, addr=addr, end=end, sym=sym, rd=rd, types=types, z=z, tables=tables, callees=callees,
             callers='ELF callers: %d%s' % (len(callers), (' (' + ', '.join('%s%s' % (n, ' x%d' % c if c > 1 else '')
                                                                           for n, c in cnames.most_common(12)) + ')') if callers else ''))
    fence = IX.fences.get(sym)
    F['fence'] = fence
    F['src'], F['port'], F['code'], F['body'] = [], 'Port: no fence for this symbol in src/.', '', ''
    F['own'] = L._fence_target(sym)[0]
    d = L._mw.demangle(sym) if L._mw else None
    F['cls'] = re.sub(r'\$.*$', '', L._mw.template_base(d['qualifier'][-1])) if d and d['qualifier'] else None
    if fence:
        p, fl, el, src, skipped = source_block(fence)
        F['src'] = src
        F['port'] = 'Port: %s lines %d-%d (definition from line %d).' % (p, fl, el, fence[2]) if skipped \
            else 'Port: %s lines %d-%d.' % (p, fl, el)
        F['code'] = body_code(fence)
        F['body'] = '\n'.join(IX.lines[p][fence[2] - 1:el])
    F['leads'] = leads(addr, sym)
    F['decl'] = declarations(sym, F['body'], callees)
    F['members'] = members(z)
    F['vcalls'] = vcalls(ins, types, set(L.called_names(F['code']))) if F['code'] else []
    return F


def fn_sections(F, level='##'):
    """The function's own sections (source, members, virtual calls, tables)."""
    text = ['%s Port source' % level, '', '```cpp'] + F['src'] + ['```', '']
    named, rest = F['members']
    if not named and all(r.startswith('+0x0 ') for r in rest):
        rest = []                       # only +0x0 through unknown registers: nothing to say
    if named or rest:
        text += ['%s Members touched (%s)' % (level, ', '.join('%s=%s' % t for t in F['types']) or 'no typed register'), '']
        if named:
            text.append(', '.join(named))
        if rest:
            text.append('Offsets through registers of unknown type: ' + ', '.join(rest[:32]) +
                        (' (+%d more)' % (len(rest) - 32) if len(rest) > 32 else ''))
        text.append('')
    if F['vcalls']:
        text += ['%s Virtual calls' % level, ''] + ['- ' + v for v in F['vcalls']] + ['']
    if F['tables']:
        text += ['%s Jump tables' % level, '']
        for a, t in F['tables']:
            text.append('- 0x%x (%d): %s' % (a, len(t), ', '.join('%d L%x' % (i, w) for i, w in enumerate(t))))
        text.append('')
    return text


def decl_text(groups):
    out = []
    for title, ls in groups:
        out.append(title)
        out += ls
    return out


def packet(row, outdir):
    F = facts(row)
    k, addr, end, rd = F['k'], F['addr'], F['end'], F['rd']
    head = ['# %d. %s' % (k, rd), '',
            '0x%x, %d bytes, `%s`. %s' % (addr, end - addr, F['sym'], F['callers']), F['port'], '']
    text = list(head)
    if F['leads']:
        text += ['## Leads (docs/port/notes)', ''] + F['leads'] + ['']
    text += fn_sections(F)
    hs = []
    if F['fence']:
        hs = find_helpers(F['fence'][0], F['code'], F['cls'], F['own'], {(F['fence'][0], F['fence'][2])}, F['callees'])
        if hs:
            text += ['## Helpers it calls (one level)', '', '```cpp'] + helper_text(hs, HELPERS_MAX) + ['```', '']
    en = enums_used(F['code'] + '\n' + '\n'.join('\n'.join(IX.clines[d.path][d.head - 1:d.end]) for d in hs))
    if en:
        text += ['## Enums (DWARF values)', ''] + enum_text(en) + ['']
    if F['decl']:
        text += ['## Declarations', ''] + decl_text(F['decl']) + ['']
    base = '%d-%x' % (k, addr)
    parts = []
    z = F['z']
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
    size = os.path.getsize(p) + sum(os.path.getsize(os.path.join(outdir, '%s.part%d.md' % (base, i + 1))) for i in range(len(parts)))
    return k, addr, end - addr, rd, base, size, len(parts)


# ---------------------------------------------------------------- one source file
def file_packet(n, path, rows, outdir, ex):
    """One packet for the listed functions of one source file, shared facts once."""
    Fs = list(ex.map(facts, rows))
    stem = re.sub(r'[^\w.-]', '_', os.path.basename(path))
    base = 'f%d-%s' % (n, stem)
    own = {(F['fence'][0], F['fence'][2]) for F in Fs if F['fence']}
    hs, en = [], collections.OrderedDict()
    seen = set(own)
    for F in Fs:
        if F['fence']:
            for d in find_helpers(F['fence'][0], F['code'], F['cls'], F['own'], seen, F['callees']):
                seen.add((d.path, d.head))
                hs.append(d)
    codes = [F['code'] for F in Fs] + ['\n'.join(IX.clines[d.path][d.head - 1:d.end]) for d in hs]
    en = enums_used('\n'.join(codes))
    decl = collections.OrderedDict()
    for F in Fs:
        for title, ls in F['decl']:
            g = decl.setdefault(title, [])
            for l in ls:
                if l not in g:
                    g.append(l)
    total = sum(F['end'] - F['addr'] for F in Fs)
    text = ['# %s: %d functions, %d bytes' % ('src/' + path if not path.startswith('src/') else path, len(Fs), total), '',
            'auditpack.py --by-file: every listed function of this file (source, then ELF disassembly), the '
            'helpers, enums and declarations they share once above them.', '',
            '| # | Address | Bytes | Function | Port lines |', '|---|---|---|---|---|']
    for F in Fs:
        text.append('| %d | 0x%x | %d | %s | %s |' % (F['k'], F['addr'], F['end'] - F['addr'], F['rd'].replace('|', '/')[:90],
                                                     '%d-%d' % (F['fence'][1], F['fence'][4]) if F['fence'] else 'no fence'))
    text.append('')
    ld = []
    for F in Fs:
        ld += ['- #%d %s' % (F['k'], x[2:]) for x in F['leads']]
    if ld:
        text += ['## Leads (docs/port/notes)', ''] + ld + ['']
    if hs:
        text += ['## Helpers the functions call (one level, each once)', '', '```cpp'] + helper_text(hs, HELPERS_MAX_FILE) + ['```', '']
    if en:
        text += ['## Enums (DWARF values)', ''] + enum_text(en, 120) + ['']
    if decl:
        text += ['## Declarations', ''] + decl_text(list(decl.items())) + ['']
    for F in Fs:
        text += ['## %d. %s' % (F['k'], F['rd']), '',
                 '0x%x, %d bytes, `%s`. %s' % (F['addr'], F['end'] - F['addr'], F['sym'], F['callers']), F['port'], '']
        text += fn_sections(F, '###')
        text += ['### ELF disassembly', '', '```'] + F['z'] + ['```', '']
    p = os.path.join(outdir, base + '.md')
    open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(text) + '\n')
    return n, path, base, Fs, os.path.getsize(p)


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
    outdir = arg('--out') or os.path.join(AUDIT, 'packets', name)
    os.makedirs(outdir, exist_ok=True)
    jobs = int(arg('--jobs', '6'))
    if '--by-file' in sys.argv:
        byf = collections.OrderedDict()
        for r in rows:
            byf.setdefault(r[4], []).append(r)
        with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
            res = [file_packet(i + 1, f, rs, outdir, ex) for i, (f, rs) in enumerate(byf.items())]
        idx = ['# Packets for audit list %s (by file)' % name, '',
               'auditpack.py --by-file: one file per source file, holding all of its listed functions. Read '
               'the packet instead of fetching the disassembly, the source and the notes one by one.', '',
               '| File | Packet | Functions | Rows | Packet KB |', '|---|---|---|---|---|']
        def spans(ks):
            out, a = [], None
            for i, k in enumerate(ks):
                if a is None:
                    a = k
                if i + 1 == len(ks) or ks[i + 1] != k + 1:
                    out.append('%d' % a if a == k else '%d-%d' % (a, k))
                    a = None
            return ', '.join(out)
        for n, path, base, Fs, b in res:
            idx.append('| %s | [%s.md](%s.md) | %d | %s | %.1f |' % (path, base, base, len(Fs),
                                                                    spans([F['k'] for F in Fs])[:160], b / 1024))
        total = sum(r[4] for r in res)
        count = sum(len(r[3]) for r in res)
    else:
        with concurrent.futures.ThreadPoolExecutor(jobs) as ex:
            res = list(ex.map(lambda r: packet(r, outdir), rows))
        idx = ['# Packets for audit list %s' % name, '',
               'auditpack.py: one file per function (ELF disassembly in parts above %d bytes). Read the '
               'packet instead of fetching the disassembly, the source and the notes one by one.' % SPLIT, '',
               '| # | Address | Bytes | Function | Packet | Packet KB | Parts |', '|---|---|---|---|---|---|---|']
        for k, a, sz, rd, base, b, np_ in res:
            idx.append('| %d | 0x%x | %d | %s | [%s.md](%s.md) | %.1f | %s |' % (k, a, sz, rd.replace('|', '/')[:80], base, base, b / 1024, np_ or ''))
        total = sum(r[5] for r in res)
        count = len(res)
    open(os.path.join(outdir, 'INDEX.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(idx) + '\n')
    print('%s: %d packets, %d functions, %.0f KB' % (os.path.relpath(outdir, _dev.REPO), len(res), count, total / 1024))


if __name__ == '__main__':
    main()
