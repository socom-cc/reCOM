"""auditpack.py <list> [--rows 1,3-5] [--by-file] [--jobs N] [--out DIR] [--fp NAME]: ready-to-read
packets for an audit list (build/port/audit/<list>.md, made by auditlist.py), for the correctness
audit (docs/port/AUDIT_PLAN.md). Writes build/port/audit/packets/<list>/ (or DIR) and its INDEX.md:
one <row>-<address>.md per function, or with --by-file (for the small band) one f<n>-<file>.md per
source file holding all of that file's listed functions, with the facts they share (leads,
helpers, enums, the members they touch, callee declarations) once at the top; a file of more than
40 functions keeps those and its contents table in f<n>-<file>.md and the functions in
f<n>-<file>.part<k>.md.

A function's part of a packet holds:
- header: readable signature, address, size, the definition's file and lines, ELF callers
  (xref.py's jal scan: count and names);
- leads: lines of docs/port/notes/*.md that name the function's address or Class::Method;
- the port's source: the fence line, then the definition itself, found by the fence's demangled
  name (a helper or a `namespace {` between them is skipped and named), to its closing brace;
- helpers: the bodies of what the body calls, each once: same-file static, unnamed-namespace,
  inline and unfenced functions, the receiver class's header definitions, a Base::name call's
  definition, a header definition of 40 lines or fewer when it is the only one of its name (also
  through another object: two when one's class is named in the body), a definition in another
  file of a name the ELF never calls (an inlined port helper); the callees of a helper of six
  lines or fewer (a forwarder) one level further (60 lines each, 250 a packet, 400 by file; the
  cut is said);
- declarations: the receiver class's member lines whose names the body uses, and one declaration
  line per ELF callee (from the src/ headers);
- enums: every enumerator the body and its helpers name (also Enum::NAME of an enum class, a
  nested enum through its class, X::NAME through another type), and all values of an enum whose
  type name the body or the signature use: the DWARF value, the port header's value when it
  differs (or alone, marked, when DWARF has no such enum), the DWARF byte size;
- members touched: DWARF names (bitfields by name and bit within the accessed byte, half or word,
  from the mask the code applies) through a register while it holds the receiver, a
  pointer-to-class argument, a call's result (its declared return type) or a pointer member
  loaded from a typed object (Class:: said then); the port's own member where the comparison
  build's layout (portlay.sh, --fp NAME, default head) has no member of that name or puts the
  bitfield at other bits; `port:` names for a class DWARF lacks; other offsets by number only;
- return value: when the port's definition returns void (or float where the ELF uses v0, or the
  reverse) and the ELF writes v0 / $f0 before returning or its callers read them, each reading
  caller on one line;
- virtual calls: each jalr's vtable slot, resolved in the class's vtable when the object's
  register is typed, else the methods at that slot whose names the body calls;
- the ELF disassembly (disx.py -f | cz.py -k -a): the address first on every line (dropped
  save-register lines and nops outside delay slots leave a gap), a label on every branch target,
  '|' marks a delay slot, a nop in one is '| nop', lui / addiu / $gp data by symbol (data names
  demangled) and strings inline, a lui reaching a target through a delay slot followed along the
  branches; plus: call targets demangled, float words loaded from memory decoded (`= 0.5f` for a
  literal, `init` for a variable), strings of 0 and 1 characters (also a merged last character),
  the words, halves and bytes loaded from data (`= word` for a literal, `init` for a variable's
  initial value, `init 0` for a function's static), small literal objects (pointer-to-member
  constants) by their words, string pointers read from data, jump tables resolved.
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
        self.penums = port_enums(self.files, self.code, self.classes)
        self.penum_by_item = collections.defaultdict(list)
        self.penum_key = {}
        for e in self.penums:
            name, encl, p, line, iscls, items = e
            self.penum_key[id(e)] = '%s%s (%s%s:%d)' % ('%s::' % encl if encl and name else '', name or 'enum in %s' % (encl or p),
                                                     'enum class, ' if iscls else '', p.split('/')[-1], line)
            for t, v in items:
                self.penum_by_item[t].append(e)


IX = None
RET_CACHE = {}
PORTLAY = None         # <scratch>/fp/<name>.lay.json (portlay.sh): the port's own layouts


def port_layouts(name):
    """The comparison build's layout file, made by portlay.sh when missing or older than the ELF."""
    fp = os.path.join(_dev.scratch(), 'fp')
    e, j = os.path.join(fp, name + '.elf'), os.path.join(fp, name + '.lay.json')
    if not os.path.exists(e):
        sys.stderr.write('no %s: port layouts left out (run fpbuild.sh HEAD %s)\n' % (e, name))
        return None
    if not os.path.exists(j) or os.path.getmtime(j) < os.path.getmtime(e):
        wsl = os.path.join(_dev.DEV, 'wsl.ps1')
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', wsl, 'portlay.sh', name],
                           cwd=_dev.REPO) if os.name == 'nt' else \
            subprocess.run(['bash', os.path.join(_dev.DEV, 'portlay.sh'), name], cwd=_dev.REPO)
        if r.returncode or not os.path.exists(j):
            sys.stderr.write('portlay.sh failed: port layouts left out\n')
            return None
    return j


def readable_callee(name):
    r = L.mw_readable(name)
    return r if len(r) < 110 else r[:107] + '...'


def cz(lines, types, rets=()):
    """z.sh's pipeline (disx.py -f | cz.py -k -a) on objdump lines already in hand; rets =
    [(call address, class its v0 points to)]."""
    dev = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ)
    env['PYTHONPATH'] = os.pathsep.join([_dev.DEV, env.get('PYTHONPATH', '')])
    p1 = subprocess.run([sys.executable, os.path.join(dev, 'disx.py'), '-f'], input='\n'.join(lines) + '\n',
                        capture_output=True, text=True, env=env)
    a = [sys.executable, os.path.join(dev, 'cz.py'), '-k', '-a']
    if PORTLAY:
        a += ['-p', PORTLAY]
    if types:
        a += ['-t', ','.join('%s=%s' % kv for kv in types)]
    if rets:
        a += ['-r', ','.join('%x=%s' % kv for kv in rets)]
    p2 = subprocess.run(a, input=p1.stdout, capture_output=True, text=True, env=env)
    if p1.returncode or p2.returncode:
        raise RuntimeError('disx.py / cz.py failed:\n' + (p1.stderr + p2.stderr)[-2000:])
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
# a line of cz.py -k -a: address, label of a branch target, '| ' in a delay slot, mnemonic
ZOP = re.compile(r'^([0-9a-f]+) +(?:L[0-9a-f]+: *)?(?:\| *)?([\w.]+)')


def short_str(a):
    """The text at a when it is a C string (also of 0 or 1 characters at a Metrowerks literal)."""
    ref = IX.ref
    s = ref.cstr(a)
    if s is not None:
        return s
    d = ref.data_at(a)
    b0 = ref.word(a & ~3)
    if b0 is None:
        return None
    bs = b0.to_bytes(4, 'little')[a & 3:] + (ref.word((a & ~3) + 4) or 0).to_bytes(4, 'little')
    if d and d[1] == 0 and d[0].startswith('@'):
        if bs[0] == 0:
            return ''
        if 32 <= bs[0] < 127 and bs[1] == 0:
            return chr(bs[0])
    elif d and d[1] and d[0].startswith('@') and 32 <= bs[0] < 127 and bs[1] == 0:
        # the last character of a longer literal (the linker merged a one-character string)
        p = ref.word((a - 1) & ~3)
        if p is not None and 32 <= (p >> (8 * ((a - 1) & 3))) & 0xff < 127:
            return chr(bs[0])
    return None


def small_object(a):
    """' {w0, w1, ...}' for the address of a small Metrowerks literal object that is not a string
    (a pointer-to-member constant, a short constant table): its words, pointers by name."""
    ref = IX.ref
    d = ref.data_at(a)
    if not d or d[1] != 0 or not d[0].startswith('@'):
        return ''
    sz = ref.byname.get(d[0], (0, 0))[1]
    if not 4 <= sz <= 16 or sz % 4:
        return ''
    ws = [ref.word(a + 4 * k) for k in range(sz // 4)]
    if None in ws:
        return ''
    f = lambda w: '0x%x %s' % (w, L.mw_readable(ref.funcs[w][0]).split('(')[0]) if w in ref.funcs else \
        '0x%x %s' % (w, ref.at[w][0]) if w in ref.at and w >= 0x100000 else '0x%x' % w
    return ' = {%s}' % ', '.join(f(w) for w in ws)


MANGLED = re.compile(r'(;\s*0x[0-9a-f]+ )([A-Za-z_][\w@$]*__\w+)')


def readable_data(l):
    """A mangled data symbol in a line's note as Class::name."""
    def rep(m):
        r = L.mw_readable(m.group(2))
        return m.group(1) + (r if r != m.group(2) and '(' not in r else m.group(2))
    return MANGLED.sub(rep, l, count=1)


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
        # a variable starting at zero: said only for a function's static (name$..)
        return ' init 0' if d and '$' in d[0] and not d[0].startswith('init$') else ''
    return ' %s %s' % ('= word' if lit else 'init', val)


def annotate(lines, start, end):
    """Demangled call targets, decoded float words, short strings, data words, string pointers;
    returns (lines, jump tables)."""
    ref = IX.ref
    out = []
    tables = []
    seen = set()
    for l in lines:
        if not l.strip():
            continue
        # (a lui shared across delay slots is resolved by disx.py -f along the branches)
        m = re.search(r'\b(jal|j)\s+([^\s;]+)', l)
        if m and not re.match(r'L[0-9a-f]+$', m.group(2)):
            l = l.replace(m.group(2), readable_callee(m.group(2)), 1)
        m = FL.search(l)
        if m:
            a = int(m.group(1), 16)
            mo = ZOP.match(l)
            op = mo.group(2) if mo else ''
            if op == 'lwc1':
                w = ref.word(a)
                if w is not None:
                    d = ref.data_at(a)
                    lit = not d or d[0].startswith('@')
                    l += ' %s %.9gf' % ('=' if lit else 'init', ref.float_of(w))
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
                    elif s is None:
                        l += small_object(a)
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
            l = readable_data(l)
        out.append(l)
    return out, tables


MEMLINE = re.compile(r'^[0-9a-f]+ +(?:L[0-9a-f]+: *)?(?:\| *)?(l\w+|s[bhwdq]\w*)\s+[^,]+,(0x[0-9a-f]+)\((\w+)\)'
                     r'(?:\s+;\s*([A-Za-z_][^;]*?))?\s*$')


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


_SCALAR = {'void', 'int', 'char', 'short', 'long', 'float', 'double', 'bool', 'unsigned', 'signed', 'u8', 'u16', 'u32',
           'u64', 's8', 's16', 's32', 's64', 'f32', 'f64', 'scalar', 'size_t', 'uint', 'BOOL'}


def ret_type(name):
    """(return type text, class it points to or None) of a function from its src/ declaration
    (the class's header first), else (None, None)."""
    dd = L._mw.demangle(name) if L._mw else None
    if not dd or dd['name'] in ('__ct', '__dt'):
        return None, None
    fn = dd['name'] if not dd['name'].startswith('__') else None
    if not fn:
        return None, None
    q = L._mw.template_base(dd['qualifier'][-1]) if dd['qualifier'] else None
    cands = IX.decl.get(fn, [])
    if q and q in IX.classes:
        p, a, b = IX.classes[q]
        cands = [x for x in cands if x[0] == p and a <= x[1] <= b] or [x for x in cands if q + '::' in x[2]]
    elif q:
        cands = [x for x in cands if q + '::' in x[2]] or cands
    for p, ln, s in cands[:3]:
        m = re.search(r'(?<![\w~:])(?:\w+\s*::\s*)*%s\s*\(' % re.escape(fn), s)
        if not m:
            continue
        pre = re.sub(r'\b(?:virtual|static|inline|extern|explicit|friend|struct|class|enum|typename)\b', ' ', s[:m.start()])
        pre = re.sub(r'/\*.*?\*/', ' ', pre).strip()
        if not pre or re.search(r'[;{}()=,]', pre):
            continue
        rt = ' '.join(pre.split())
        cm = re.match(r'(?:const\s+)?((?:\w+::)*\w+)\s*(?:const\s*)?[*&]$', rt.replace(' *', '*').replace(' &', '&'))
        cls = cm.group(1) if cm and cm.group(1).split('::')[-1] not in _SCALAR else None
        return rt, cls
    return None, None


def def_ret(fence, own):
    """The return type written in the port's definition head ('' for a constructor / destructor)."""
    p, fl, hl, bl, el = fence
    head = ' '.join(IX.clines[p][hl - 1:bl])
    m = re.search(r'(?<![\w~])(?:[\w<>]+\s*::\s*)*%s\s*\(' % re.escape(own), head)
    if not m or own.startswith('~') or own.startswith('operator'):
        return None
    pre = re.sub(r'\b(?:virtual|static|inline|extern|explicit|friend|struct|class|enum|typename)\b', ' ', head[:m.start()])
    pre = re.sub(r'\btemplate\s*<[^>]*>', ' ', pre)
    return ' '.join(pre.split()) or None


def _reads(op, args, reg):
    if not args:
        return False
    if op in ('mtc1', 'dmtc1', 'ctc1'):
        return args[0] == reg
    if op.startswith(('s', 'b')) and not op.startswith(('sll', 'srl', 'sra', 'slt', 'sub', 'seq', 'sne')) or \
            op.startswith('c.') or op in ('mtc1', 'jr', 'jalr', 'mthi', 'mtlo', 'teq', 'tne', 'mult', 'multu', 'div', 'divu'):
        return any(reg == a or ('(%s)' % reg) in a for a in args)
    return any(reg == a or ('(%s)' % reg) in a for a in args[1:])


def _writes(op, args, reg):
    if op in ('mtc1', 'dmtc1') and len(args) == 2:
        return args[1] == reg
    if not args or op.startswith(('s', 'b', 'j', 'c.')) and not op.startswith(('sll', 'srl', 'sra', 'slt', 'sub', 'seq', 'sne')):
        return False
    return args[0] == reg and op not in ('mtc1', 'mthi', 'mtlo', 'teq', 'tne', 'mult', 'multu', 'div', 'divu')


def result_use(addr, end, callers):
    """(the ELF's own return registers [(reg, address)] written in the last lines before a
    jr ra, [(call site, caller, reg, instruction)] of the callers that read v0 / $f0 after it)."""
    ins = IX.dis.insns(addr, end)
    sets = []
    for i, (a, op, ops, raw) in enumerate(ins):
        if op == 'jr' and ops.strip() == 'ra':
            for reg in ('v0', '$f0'):
                # the last write before the return, unless a later line reads it (a temporary)
                for j in range(min(i + 1, len(ins) - 1), max(-1, i - 4), -1):
                    o2, a2 = ins[j][1], [x.strip() for x in ins[j][2].split(',')] if ins[j][2] else []
                    if _writes(o2, a2, reg):
                        if all(r != reg for r, x in sets):
                            sets.append((reg, ins[j][0]))
                        break
                    if _reads(o2, a2, reg):
                        break
    reads = []
    for c in callers:
        g = IX.ref.func_at(c)
        if not g:
            continue
        seq = IX.dis.insns(c + 8, min(c + 8 + 40, g[0] + g[2]))
        hit = None
        live = {'v0', '$f0'}
        for a, op, ops, raw in seq:
            args = [x.strip() for x in ops.split(',')] if ops else []
            hit = next(((reg, '%s %s' % (op, ops)) for reg in sorted(live) if _reads(op, args, reg)), None)
            if hit:
                break
            live -= set(r for r in ('v0', '$f0') if _writes(op, args, r))
            if not live or op in ('jal', 'jalr', 'j', 'jr') or op.startswith('b') and op != 'break':
                break
        if hit:
            reads.append((c, L.mw_readable(g[1]).split('(')[0], hit[0], hit[1]))
    return sets, reads


def return_text(F):
    """Lines for the function's result when the port's return type and the ELF's use of v0 / $f0
    disagree: the port void and the ELF setting or its callers reading a result, or a float / int
    mismatch; the reading callers one line each."""
    rt = F.get('ret')
    if rt is None:
        return []
    sets, reads = F['retuse']
    isvoid = rt == 'void'
    isfloat = bool(re.search(r'\b(?:float|f32|scalar|double)\b', rt)) and '*' not in rt and '&' not in rt
    regs = set(r for r, x in sets) | set(r for c, n, r, i in reads)
    bad = (isvoid and regs) or (isfloat and 'v0' in regs and '$f0' not in regs) or \
        (not isvoid and not isfloat and '$f0' in regs and 'v0' not in regs)
    if not bad:
        return []
    out = ['Port returns `%s`; the ELF %s; %d of %d ELF callers read the result:' % (
        rt, 'writes %s before its return' % ', '.join('%s (0x%x)' % s for s in sets) if sets else 'writes neither v0 nor $f0 before its return',
        len(reads), len(IX.callers.get(F['addr'], [])))]
    out += ['- 0x%x %s: %s' % (c, n, i) for c, n, r, i in reads[:12]]
    if len(reads) > 12:
        out.append('- ... %d more' % (len(reads) - 12))
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


HDR = ('.h', '.hpp', '.inl')
FORWARDER = 6           # a helper of at most this many lines gets its own callees (level 2)
HELPER_OF = {}          # (path, head) of a level-2 helper -> the helper that calls it


def find_helpers(path, code, cls, own, exclude, callees=(), level=1):
    """[Def] the code calls, one level: same-file local or unfenced definitions, the receiver
    class's header definitions, a Base::name call's definition (any file), a unique short header
    definition (a call through another object too: several only when one's class is named in the
    code), and a definition in another file of a name the ELF never calls (the ELF inlined it);
    then, once, the helpers of a helper of FORWARDER lines or fewer (a forwarder). A name the ELF
    calls out of line on another class is not taken."""
    out = []
    seen = set(exclude)
    elf = collections.defaultdict(set)      # simple name -> classes the ELF calls it on
    for c in callees:
        n_, c_, p_ = L._fence_target(c)
        elf[n_].add(c_)
    words = set(re.findall(r'\b[A-Za-z_]\w*\b', code))
    for n, via, q in L.called_names(code, kinds=True):
        if n == own or n in ('sizeof', 'offsetof'):
            continue
        cands = [d for d in IX.defs.get(path, []) if d.name == n and
                 (d.local or d.head not in IX.fenced_heads[path]) and (not q or d.cls == q)]
        if not cands and cls and cls in IX.classes and via in ('', 'this'):
            hp = IX.classes[cls][0]
            cands = [d for d in IX.defs.get(hp, []) if d.name == n and d.cls == cls]
        if not cands and via == '::' and q:
            qs = [d for d in IX.defs_by_name.get(n, []) if d.cls == q]
            cands = sorted(qs, key=lambda d: not d.path.endswith(HDR))[:1] \
                if n not in elf or q not in elf[n] or (qs and qs[0].lines <= 15) else []
        if not cands and via in ('', '::', 'obj'):
            hs = [d for d in IX.defs_by_name.get(n, []) if d.path.endswith(HDR)
                  and d.lines <= HEADER_INLINE and (not q or d.cls == q)]
            if via == 'obj' and len(hs) > 1:
                hs = [d for d in hs if d.cls in words]
            if len(hs) == 1 or (via == 'obj' and len(hs) == 2):
                cands = hs
        if not cands and n not in elf and not n.startswith(('sce', 'socom_port', 'mem', 'str')):
            # the port calls it, the ELF does not: a helper the ELF inlined, from another file
            os_ = [d for d in IX.defs_by_name.get(n, []) if d.lines <= HELPER_LINES and (not q or d.cls == q)]
            if via == 'obj' and len(os_) > 1:
                os_ = [d for d in os_ if d.cls in words]
            if 1 <= len(os_) <= 2:
                cands = os_
        cands = [d for d in cands if n not in elf or d.cls in elf[n] or via == '::']
        for d in cands[:3]:
            key = (d.path, d.head)
            if key not in seen:
                seen.add(key)
                out.append(d)
    if level == 1:
        for d in list(out):
            if d.lines <= FORWARDER:
                sub = find_helpers(d.path, '\n'.join(IX.clines[d.path][d.head - 1:d.end]), d.cls, d.name, seen,
                                   callees, 2)
                for s in sub:
                    seen.add((s.path, s.head))
                    HELPER_OF[(s.path, s.head)] = d.name
                    out.append(s)
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
        if (d.path, d.head) in HELPER_OF:
            kind += '; called by %s' % HELPER_OF[(d.path, d.head)]
        n = min(d.end - s, HELPER_LINES, max(4, cap - len(out)))
        out.append('// %s%s: %s:%d-%d (%s)' % (d.cls + '::' if d.cls and not d.in_class else '', d.name, d.path, d.head, d.end, kind))
        out += ['%5d %s' % (i + 1, lines[i]) for i in range(s, s + n)]
        if s + n < d.end:
            out.append('      ... %d more lines (to %d)' % (d.end - s - n, d.end))
    if left:
        out.append('// not shown (packet cap): ' + ', '.join(left))
    return out


ENUM_RE = re.compile(r'\benum\s+(?:class\s+|struct\s+)?([A-Za-z_]\w*)?\s*(?::\s*[\w\s]+?)?\s*\{([^{}]*)\}')


def _enum_value(expr, known):
    """The value of an enumerator's initialiser: literals, earlier enumerators, | & << >> + - * ~ ( )."""
    e = re.sub(r"'(\\?.)'", lambda m: str(ord(m.group(1)[-1])), expr)
    e = re.sub(r'\b(0x[0-9a-fA-F]+|\d+)[uUlL]+\b', r'\1', e)
    e = re.sub(r'\(\s*(?:unsigned\s+)?(?:int|char|short|long|u8|u16|u32|s8|s16|s32)\s*\)', '', e)
    e = re.sub(r'\b[A-Za-z_]\w*(?:::\w+)*\b', lambda m: str(known[m.group(0).split('::')[-1]])
               if m.group(0).split('::')[-1] in known else 'X', e)
    if 'X' in e or not re.fullmatch(r'[\s0-9a-fA-Fx+\-*/|&~<>()^]*', e):
        return None
    try:
        return int(eval(e.replace('/', '//'), {'__builtins__': {}}, {}))
    except Exception:
        return None


def port_enums(files, code, classes):
    """[(enum name or '', enclosing class or None, path, line, is enum class, [(name, value)])] of
    the enums defined in src/ (values computed; None where an initialiser is not understood)."""
    out = []
    glob_known = {}
    spans = collections.defaultdict(list)
    for cls, (p, a, b) in classes.items():
        spans[p].append((a, b, cls))
    for p, c in code.items():
        if 'enum' not in c:
            continue
        for m in ENUM_RE.finditer(c):
            line = c.count('\n', 0, m.start()) + 1
            known, items, v = {}, [], -1
            for part in m.group(2).split(','):
                part = part.strip()
                if not part:
                    continue
                nm, _, ex = part.partition('=')
                nm = nm.strip()
                if not re.fullmatch(r'[A-Za-z_]\w*', nm):
                    continue
                if ex.strip():
                    v = _enum_value(ex.strip(), dict(glob_known, **known))
                else:
                    v = None if v is None else v + 1
                known[nm] = v
                items.append((nm, v))
            glob_known.update({k: x for k, x in known.items() if x is not None})
            encl = [cls for a, b, cls in spans.get(p, []) if a < line <= b]
            out.append((m.group(1) or '', encl[-1] if encl else None, p, line,
                        bool(re.match(r'enum\s+(class|struct)\b', c[m.start():m.start() + 20])), items))
    return out


def enums_used(code, sigs=''):
    """{display name: [(enumerator, DWARF value or None, port value or None, size)]}: the
    enumerators the code names (DWARF's and the port headers'), a name written X::NAME taking the
    enum X or the enums nested in class X; and the whole of each enum (up to 24) whose type name
    the code or the signatures sigs use. A bare plain-word name (left, end) only with its enum's
    name in the code."""
    E = L.enumerators()
    PE = IX.penum_by_item
    uses = collections.OrderedDict()
    for m in re.finditer(r'(?:([A-Za-z_]\w*)\s*::\s*|(->|\.)\s*)?\b([A-Za-z_]\w*)\b(\s*\()?', code):
        t = m.group(3)
        if (t in E or t in PE) and len(t) > 2 and not m.group(2) and not m.group(4):
            uses.setdefault(t, set()).add(m.group(1))
    words = set(re.findall(r'\b[A-Za-z_]\w*\b', code + '\n' + sigs))
    got = collections.OrderedDict()
    base = lambda q: re.sub(r'@[0-9a-f]+$', '', q)

    def add(key, t, dv, pv, sz):
        lst = got.setdefault(key, [])
        if all(x[0] != t for x in lst):
            lst.append((t, dv, pv, sz))
    for t, qs in uses.items():
        qs.discard(None)
        pc = [e for e in PE.get(t, []) if not qs or e[0] in qs or e[1] in qs]
        dc = [x for x in E.get(t, []) if not x[0].startswith('std::')]
        if qs:
            dc = [x for x in dc if set(base(x[0]).split('::')) & qs] or \
                 [x for x in dc if any(base(x[0]).split('::')[-1] == e[0] for e in pc)]
        if not qs and t.isalpha() and t.islower():
            dc = [x for x in dc if base(x[0]).split('::')[-1] in words]
            pc = [e for e in pc if e[0] in words]
        for e in pc[:3]:
            key = IX.penum_key[id(e)]
            dmatch = [x for x in dc if base(x[0]).split('::')[-1] == e[0]] or (dc if len(dc) == 1 else [])
            pv = dict(e[5]).get(t)
            add(key, t, dmatch[0][1] if dmatch else None, pv, dmatch[0][2] if dmatch else 0)
            dc = [x for x in dc if x not in dmatch]
        for q, v, sz in dc[:3] if not pc else dc[:1]:
            add(base(q), t, v, None, sz)
    # enums named as types (parameters, locals, casts, members): all of their values
    for e in IX.penums:
        if e[0] and e[0] in words and len(e[5]) <= 24:
            key = IX.penum_key[id(e)]
            if key in got and len(got[key]) >= len(e[5]):
                continue
            dv = {}
            for t, pv in e[5]:
                d = [x for x in E.get(t, []) if base(x[0]).split('::')[-1] == e[0]]
                dv[t] = d[0] if d else None
            for t, pv in e[5]:
                add(key, t, dv[t][1] if dv[t] else None, pv, dv[t][2] if dv[t] else 0)
    for k in got:
        got[k].sort(key=lambda x: (x[1] if x[1] is not None else x[2] if x[2] is not None else 1 << 40))
    return got


def enum_text(got, cap=60):
    out = []
    n = 0

    def fmt(t, dv, pv, sz):
        if dv is None:
            return '%s=%s' % (t, '?' if pv is None else pv)
        s = '%s=%d' % (t, dv) if dv >= 0 or sz >= 4 else '%s=%d (0x%x)' % (t, dv, dv & ((1 << (8 * sz)) - 1))
        return s if pv is None or pv == dv else s + ' (port %d)' % pv
    for q, items in got.items():
        if n >= cap:
            out.append('- ... %d more enums' % (len(got) - len(out)))
            break
        szs = sorted(set(x[3] for x in items if x[3]))
        tag = ' [no DWARF enum: port header values]' if all(x[1] is None for x in items) else \
            ' [DWARF %d byte%s]' % (szs[0], '' if szs[0] == 1 else 's') if len(szs) == 1 else ''
        out.append('- %s%s: %s' % (q, tag, ', '.join(fmt(*x) for x in items)))
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
    rets = []
    for a, op, ops, raw in ins:
        if op == 'jal':
            m = L.TARGET.match(ops.split(',')[-1].strip())
            if m and m.group(2) and '+' not in m.group(2):
                if m.group(2) not in RET_CACHE:
                    RET_CACHE[m.group(2)] = ret_type(m.group(2))
                c = RET_CACHE[m.group(2)][1]
                if c and re.fullmatch(r'[\w:]+', c):
                    rets.append((a, c))
    z = cz([x[3] for x in ins], types, rets)
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
    F['sig'] = rd
    F['ret'], F['retuse'] = None, ([], [])
    F['own'] = L._fence_target(sym)[0]
    d = L._mw.demangle(sym) if L._mw else None
    F['cls'] = re.sub(r'\$.*$', '', L._mw.template_base(d['qualifier'][-1])) if d and d['qualifier'] else None
    if fence:
        p, fl, el, src, skipped = source_block(fence)
        F['src'] = src
        F['port'] = 'Port: %s lines %d-%d (definition from line %d).' % (p, fl, el, fence[2]) if skipped \
            else 'Port: %s lines %d-%d.' % (p, fl, el)
        F['code'] = body_code(fence)
        F['sig'] = F['rd'] + '\n' + '\n'.join(IX.clines[p][fence[2] - 1:fence[3]])
        F['body'] = '\n'.join(IX.lines[p][fence[2] - 1:el])
        F['ret'] = def_ret(fence, F['own'])
        F['retuse'] = result_use(addr, end, callers) if F['ret'] is not None else ([], [])
    F['leads'] = leads(addr, sym)
    F['decl'] = declarations(sym, F['body'], callees)
    F['members'] = members(z)
    F['vcalls'] = vcalls(ins, types, set(L.called_names(F['code']))) if F['code'] else []
    return F


def fn_sections(F, level='##', members=True):
    """The function's own sections (source, members, return value, virtual calls, tables); without
    members (by file) the named members go to the file's shared section and only the offsets
    through untyped registers stay here, on one line."""
    text = ['%s Port source' % level, '', '```cpp'] + F['src'] + ['```', '']
    named, rest = F['members']
    if not named and all(r.startswith('+0x0 ') for r in rest):
        rest = []                       # only +0x0 through unknown registers: nothing to say
    if members and (named or rest):
        text += ['%s Members touched (%s)' % (level, ', '.join('%s=%s' % t for t in F['types']) or 'no typed register'), '']
        if named:
            text.append(', '.join(named))
        if rest:
            text.append('Offsets through registers of unknown type: ' + ', '.join(rest[:32]) +
                        (' (+%d more)' % (len(rest) - 32) if len(rest) > 32 else ''))
        text.append('')
    elif rest:
        text += ['Offsets through registers of unknown type: ' + ', '.join(rest[:24]) +
                 (' (+%d more)' % (len(rest) - 24) if len(rest) > 24 else ''), '']
    rt = return_text(F)
    if rt:
        text += ['%s Return value' % level, ''] + rt + ['']
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
    en = enums_used(F['code'] + '\n' + '\n'.join('\n'.join(IX.clines[d.path][d.head - 1:d.end]) for d in hs), F['sig'])
    if en:
        text += ['## Enums (DWARF values)', ''] + enum_text(en) + ['']
    if F['decl']:
        text += ['## Declarations', ''] + decl_text(F['decl']) + ['']
    base = '%d-%x' % (k, addr)
    parts = []
    z = F['z']
    if end - addr > SPLIT:
        cur, cur_a = [], addr
        for l in z:
            lab = re.match(r'^[0-9a-f]+ +L([0-9a-f]+):', l)
            if lab and int(lab.group(1), 16) - cur_a >= PART:
                parts.append((cur_a, int(lab.group(1), 16), cur))
                cur, cur_a = [], int(lab.group(1), 16)
            cur.append(l)
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
FILE_PART = 40          # by file: more functions than this go into part files of this many


def file_packet(n, path, rows, outdir, ex):
    """One packet for the listed functions of one source file, the facts they share once at the
    top (leads, helpers, enums, the members they touch by typed register, declarations); a file
    of more than FILE_PART functions keeps those and the contents in <base>.md and the
    functions in <base>.part<k>.md."""
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
    en = enums_used('\n'.join(codes), '\n'.join(F['sig'] for F in Fs))
    decl = collections.OrderedDict()
    for F in Fs:
        for title, ls in F['decl']:
            g = decl.setdefault(title, [])
            for l in ls:
                if l not in g:
                    g.append(l)
    mem = collections.OrderedDict()     # typed registers -> {member text: [rows]}
    for F in Fs:
        key = ', '.join('%s=%s' % t for t in F['types']) or 'registers typed by results and pointer members'
        for x in F['members'][0]:
            what, _, ls = x.rpartition(' ')
            e = mem.setdefault(key, collections.OrderedDict()).setdefault(what, [set(), []])
            e[0].update(ls.split('/'))
            e[1].append(F['k'])
    total = sum(F['end'] - F['addr'] for F in Fs)
    nparts = (len(Fs) + FILE_PART - 1) // FILE_PART if len(Fs) > FILE_PART else 0
    chunk = (len(Fs) + nparts - 1) // nparts if nparts else len(Fs)     # parts of equal counts
    pname = lambda i: '%s.part%d.md' % (base, i + 1)
    where = {F['k']: (pname(i // chunk) if nparts else None) for i, F in enumerate(Fs)}

    def notes(F):
        ns = []
        if return_text(F):
            ns.append('return differs')
        if F['vcalls']:
            ns.append('%d virtual' % len(F['vcalls']))
        if F['tables']:
            ns.append('jump table')
        if F['leads']:
            ns.append('%d lead%s' % (len(F['leads']), '' if len(F['leads']) == 1 else 's'))
        if not F['fence']:
            ns.append('no fence')
        return ', '.join(ns)
    text = ['# %s: %d functions, %d bytes' % ('src/' + path if not path.startswith('src/') else path, len(Fs), total), '',
            'auditpack.py --by-file: the facts the functions share (leads, helpers, enums, the members they touch, '
            'declarations) once here, then per function its header line, port source, own notes and ELF disassembly '
            '(the address on every line).' + (' The functions are in %d part files (see Part).' % nparts if nparts else ''),
            '', '| # | Address | Bytes | Function | Port lines | Notes |%s' % (' Part |' if nparts else ''),
            '|---|---|---|---|---|---|%s' % ('---|' if nparts else '')]
    for F in Fs:
        text.append('| %d | 0x%x | %d | %s | %s | %s |%s' % (
            F['k'], F['addr'], F['end'] - F['addr'], F['rd'].replace('|', '/')[:90],
            '%d-%d' % (F['fence'][1], F['fence'][4]) if F['fence'] else 'no fence', notes(F),
            ' [%d](%s) |' % (Fs.index(F) // chunk + 1, where[F['k']]) if nparts else ''))
    text.append('')
    ld = []
    for F in Fs:
        ld += ['- #%d %s' % (F['k'], x[2:]) for x in F['leads']]
    if ld:
        text += ['## Leads (docs/port/notes)', ''] + ld + ['']
    if hs:
        text += ['## Helpers the functions call (one level, and the callees of a forwarder; each once)', '', '```cpp'] + \
            helper_text(hs, HELPERS_MAX_FILE) + ['```', '']
    if en:
        text += ['## Enums (DWARF values; port header values where they differ or DWARF has none)', ''] + enum_text(en, 160) + ['']
    if mem:
        text += ['## Members touched (DWARF names, bitfields by bit; [port ...] where the port\'s layout differs)', '']
        for key, d in mem.items():
            text.append('- %s: %s' % (key, ', '.join('%s %s (#%s)' % (x, '/'.join(sorted(ls)), ', #'.join(str(k) for k in ks[:6]) +
                                                                 (' +%d' % (len(ks) - 6) if len(ks) > 6 else ''))
                                                    for x, (ls, ks) in sorted(d.items(), key=lambda kv: int(kv[0].split()[0][1:], 16)))))
        text.append('')
    if decl:
        text += ['## Declarations', ''] + decl_text(list(decl.items())) + ['']
    parts = [[] for _ in range(max(nparts, 1))]
    for i, F in enumerate(Fs):
        sec = ['## %d. %s' % (F['k'], F['rd']), '',
               '0x%x, %d bytes, `%s`. %s' % (F['addr'], F['end'] - F['addr'], F['sym'], F['callers']), F['port'], '']
        sec += fn_sections(F, '###', members=False)
        sec += ['### ELF disassembly', '', '```'] + F['z'] + ['```', '']
        parts[i // chunk if nparts else 0] += sec
    size = 0
    if nparts:
        text += ['## Parts', ''] + ['- [%s](%s): #%d-#%d' % (pname(i), pname(i), Fs[i * chunk]['k'],
                                                             Fs[min(len(Fs), (i + 1) * chunk) - 1]['k']) for i in range(nparts)] + ['']
        for i, sec in enumerate(parts):
            q = os.path.join(outdir, pname(i))
            open(q, 'w', encoding='utf-8', newline='\n').write('\n'.join(
                ['# %s: part %d of %d (the shared facts are in %s.md)' % (path, i + 1, nparts, base), ''] + sec) + '\n')
            size += os.path.getsize(q)
    else:
        text += parts[0]
    p = os.path.join(outdir, base + '.md')
    open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(text) + '\n')
    return n, path, base, Fs, os.path.getsize(p) + size, nparts


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
    global PORTLAY
    PORTLAY = port_layouts(arg('--fp', 'head'))
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
               'auditpack.py --by-file: one file per source file, holding all of its listed functions (more than %d: '
               'the shared facts in the file, the functions in its part files). Read the packet instead of fetching '
               'the disassembly, the source and the notes one by one.' % FILE_PART, '',
               '| File | Packet | Functions | Rows | Packet KB | Parts |', '|---|---|---|---|---|---|']
        def spans(ks):
            out, a = [], None
            for i, k in enumerate(ks):
                if a is None:
                    a = k
                if i + 1 == len(ks) or ks[i + 1] != k + 1:
                    out.append('%d' % a if a == k else '%d-%d' % (a, k))
                    a = None
            return ', '.join(out)
        for n, path, base, Fs, b, np_ in res:
            idx.append('| %s | [%s.md](%s.md) | %d | %s | %.1f | %s |' % (path, base, base, len(Fs),
                                                                         spans([F['k'] for F in Fs])[:160], b / 1024, np_ or ''))
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
