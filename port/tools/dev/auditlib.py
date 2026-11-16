"""auditlib.py: shared readers for auditpack.py and auditscan.py (imported; no command line).

Elf(path)            ELF32 little-endian reader: sections, symbols, words, C strings, functions.
Dis(path)            objdump -d text (the reference ELF's cached full disassembly, or a port
                     fingerprint .dis with -l line markers) parsed per function on demand.
ref() / ref_dis()    the reference ELF and its disassembly (support/socom.elf; the full
                     disassembly is copied once from ~/.cache/socom/full.dis by zs.sh's recipe into
                     <scratch>/ref.dis, or made with dis.sh when missing).
mw_key(name) / gnu_key(demangled)  a compiler-independent key for a function or data symbol:
                     the qualified name without parameters, spaces removed (CZKit::Fire,
                     AnimSet::~AnimSet, operator new, floorTolerance for function statics).
mw_readable(name)    readable signature of a Metrowerks symbol (tools/_socom/mwdemangle.py).
fence_spans(text)    skeleton fences of one source file: name -> (fence line, brace line, end line).
features(...)        the comparison features of one function (see auditscan.py).
audit_rows()         verdict rows of docs/port/notes/audit-*.md (the audit's ground truth).
Read-only on the reference ELF and the checkout; writes only under build/.
"""
import _dev
import bisect
import collections
import glob
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.join(_dev.REPO, 'tools'))
try:
    from _socom import mwdemangle as _mw
except Exception:  # pragma: no cover - the demangler is optional for the readers
    _mw = None


# ---------------------------------------------------------------- ELF
class Elf:
    def __init__(self, path=None, data=None):
        self.data = data if data is not None else open(path, 'rb').read()
        d = self.data
        shoff, = struct.unpack_from('<I', d, 0x20)
        shentsize, shnum, shstrndx = struct.unpack_from('<HHH', d, 0x2e)
        self.secs = [struct.unpack_from('<IIIIIIIIII', d, shoff + i * shentsize) for i in range(shnum)]
        st = self.secs[shstrndx]
        self.secname = [d[st[4] + s[0]:d.index(b'\0', st[4] + s[0])].decode('latin1') for s in self.secs]
        self.load = sorted((s[3], s[3] + s[5], s[4], s[1], self.secname[i]) for i, s in enumerate(self.secs)
                           if s[3] and s[1] in (1, 8) and s[2] & 2)
        self._lstarts = [x[0] for x in self.load]
        self.syms = []          # (name, value, size, bind, type)
        self.at = {}            # value -> [names]
        self.funcs = {}         # value -> (name, size, bind) first sized function symbol
        self.byname = {}
        self.gp = 0
        for s in self.secs:
            if s[1] != 2:
                continue
            strtab = self.secs[s[6]]
            for i in range(s[5] // 16):
                nm, val, sz, info, _, shn = struct.unpack_from('<IIIBBH', d, s[4] + i * 16)
                n = d[strtab[4] + nm:d.index(b'\0', strtab[4] + nm)].decode('latin1')
                if not n:
                    continue
                b, t = info >> 4, info & 15
                self.syms.append((n, val, sz, b, t))
                self.byname.setdefault(n, (val, sz, b, t))
                if n == '_gp':
                    self.gp = val
                if val and t in (0, 1, 2) and not n.startswith('$'):
                    self.at.setdefault(val, []).append(n)
                if t == 2 and sz and val not in self.funcs:
                    self.funcs[val] = (n, sz, b)
        self._fstarts = sorted(self.funcs)
        self._data = sorted((v, sz, n) for n, v, sz, b, t in self.syms if t in (0, 1) and v and sz)
        self._dstarts = [x[0] for x in self._data]
        lo = min(x[0] for x in self.load) if self.load else 0
        hi = max(x[1] for x in self.load) if self.load else 0
        self.range = (lo, hi)

    def _sec(self, a):
        i = bisect.bisect_right(self._lstarts, a) - 1
        if i >= 0 and a < self.load[i][1]:
            return self.load[i]
        return None

    def word(self, a):
        s = self._sec(a)
        if s is None or s[3] == 8 or a + 4 > s[1]:
            return None
        return struct.unpack_from('<I', self.data, s[2] + a - s[0])[0]

    def cstr(self, a):
        s = self._sec(a)
        if s is None or s[3] == 8:
            return None
        o = s[2] + a - s[0]
        e = self.data.find(b'\0', o, o + 400)
        if e < 0:
            return None
        b = self.data[o:e]
        if 2 <= len(b) < 300 and all(32 <= c < 127 or c in (9, 10) for c in b):
            return b.decode('latin1')
        return None

    def func_at(self, a):
        """(start, name, size) of the sized function symbol containing a, or None."""
        i = bisect.bisect_right(self._fstarts, a) - 1
        if i >= 0:
            v = self._fstarts[i]
            n, sz, b = self.funcs[v]
            if a < v + sz:
                return v, n, sz
        return None

    def data_at(self, a):
        """(name, offset) of the sized data symbol containing a (or the symbol exactly at a)."""
        if a in self.at:
            names = [n for n in self.at[a] if n in self.byname and self.byname[n][3] != 2] or self.at[a]
            return names[0], 0
        i = bisect.bisect_right(self._dstarts, a) - 1
        if i >= 0:
            v, sz, n = self._data[i]
            if a < v + sz:
                return n, a - v
        return None

    def virtuals(self, prefix):
        """Starts of the functions named in the vtables (symbols starting with prefix)."""
        out = set()
        for n, v, sz, b, t in self.syms:
            if n.startswith(prefix) and sz:
                for k in range(sz // 4):
                    w = self.word(v + 4 * k)
                    if w in self.funcs:
                        out.add(w)
        return out

    def float_of(self, w):
        return struct.unpack('<f', struct.pack('<I', w))[0]


# ---------------------------------------------------------------- objdump text
INSN = re.compile(r'^\s*([0-9a-f]+):\s+(\S+)\s*(.*)$')
HEAD = re.compile(r'^([0-9a-f]{8}) <(.+)>:$')
LINE = re.compile(r'^(/\S+?):(\d+)(?: \(discriminator \d+\))?$')


class Dis:
    def __init__(self, path):
        self.lines = open(path, encoding='latin1').read().split('\n')
        self.heads = []
        for i, l in enumerate(self.lines):
            if l and l[0] in '0123456789abcdef':
                m = HEAD.match(l)
                if m:
                    self.heads.append((int(m.group(1), 16), i))
        self.heads.sort()
        self._hk = [h[0] for h in self.heads]
        self._cache = {}

    def first_line(self, start):
        """(file, line) of the first -l marker of the function at start."""
        i = bisect.bisect_left(self._hk, start)
        if i >= len(self._hk) or self._hk[i] != start:
            return None
        k = self.heads[i][1] + 1
        for l in self.lines[k:k + 6]:
            m = LINE.match(l)
            if m:
                return m.group(1), int(m.group(2))
            if INSN.match(l):
                break
        return None

    def insns(self, start, end):
        """[(addr, mnemonic, operands-without-comment, raw line)] in [start, end)."""
        key = (start, end)
        if key in self._cache:
            return self._cache[key]
        i = bisect.bisect_right(self._hk, start) - 1
        out = []
        k = self.heads[i][1] if i >= 0 else 0
        n = len(self.lines)
        while k < n:
            l = self.lines[k]
            k += 1
            if not l or l[0] != ' ':
                continue
            m = INSN.match(l)
            if not m:
                continue
            a = int(m.group(1), 16)
            if a < start:
                continue
            if a >= end:
                break
            ops = m.group(3).split('#')[0].strip()
            out.append((a, m.group(2), ops, l))
        if len(self._cache) > 4000:
            self._cache.clear()
        self._cache[key] = out
        return out


_ref = None
_refdis = None


def ref():
    global _ref
    if _ref is None:
        _ref = Elf(data=_dev.elf())
    return _ref


def ref_dis_path():
    return os.path.join(_dev.scratch(), 'ref.dis')


def ensure_ref_dis():
    """<scratch>/ref.dis: the reference ELF's full disassembly (objdump -d --no-show-raw-insn,
    made in WSL by refdis.sh when missing)."""
    p = ref_dis_path()
    if not os.path.exists(p) or os.path.getmtime(p) < os.path.getmtime(_dev.elf_path()):
        wsl = os.path.join(_dev.DEV, 'wsl.ps1')
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', wsl, 'refdis.sh'],
                           cwd=_dev.REPO) if os.name == 'nt' else \
            subprocess.run(['bash', os.path.join(_dev.DEV, 'refdis.sh')], cwd=_dev.REPO)
        if r.returncode or not os.path.exists(p):
            sys.exit('could not make %s (run port/tools/dev/refdis.sh)' % p)
    return p


def ref_dis():
    global _refdis
    if _refdis is None:
        _refdis = Dis(ensure_ref_dis())
    return _refdis


# ---------------------------------------------------------------- names
MW_OPS = {'__nw': 'operator new', '__dl': 'operator delete', '__nwa': 'operator new[]',
          '__dla': 'operator delete[]', '__as': 'operator=', '__eq': 'operator==', '__ne': 'operator!=',
          '__pl': 'operator+', '__mi': 'operator-', '__ml': 'operator*', '__dv': 'operator/',
          '__md': 'operator%', '__apl': 'operator+=', '__ami': 'operator-=', '__amu': 'operator*=',
          '__adv': 'operator/=', '__vc': 'operator[]', '__cl': 'operator()', '__rf': 'operator->',
          '__lt': 'operator<', '__gt': 'operator>', '__le': 'operator<=', '__ge': 'operator>=',
          '__nt': 'operator!', '__co': 'operator~', '__aa': 'operator&&', '__oo': 'operator||',
          '__ad': 'operator&', '__or': 'operator|', '__er': 'operator^', '__ls': 'operator<<',
          '__rs': 'operator>>', '__pp': 'operator++', '__mm': 'operator--', '__aad': 'operator&=',
          '__aor': 'operator|=', '__aer': 'operator^=', '__als': 'operator<<=', '__ars': 'operator>>='}


def _squash(s):
    s = re.sub(r'\(anonymous namespace\)::', '', s)
    s = re.sub(r'@unnamed@[^:]*@::', '', s)
    return s.replace(' ', '')


def _mw_name(d):
    q = [c for c in d['qualifier'] if not c.startswith('@unnamed@')]
    n = d['name']
    base = _mw.template_base(q[-1]) if q else ''
    if n == '__ct':
        n = base
    elif n == '__dt':
        n = '~' + base
    elif n in MW_OPS:
        n = MW_OPS[n]
    elif n.startswith('__op'):
        n = 'operator ' + n[4:]
    return q, n


def mw_key(name):
    """Key of a Metrowerks symbol (function or data)."""
    if name.startswith('init$'):    # the guard flag of a function-local static
        return '#guard'
    if '$' in name:                     # function / file statics: name$1234, name$localstatic3$func
        return name.split('$', 1)[0]
    if _mw is not None:
        d = _mw.demangle(name)
        if d:
            q, n = _mw_name(d)
            return _squash('::'.join([_mw.readable_qualified(q), n] if q else [n]))
    return name


def mw_readable(name):
    if _mw is None:
        return name
    d = _mw.demangle(name)
    if not d:
        return name
    q, n = _mw_name(d)
    s = '::'.join([_mw.readable_qualified(q), n] if q else [n])
    if d['params'] is None:
        return s
    ps = [_mw.render_type(p) for p in d['params']]
    if ps == ['void']:
        ps = []
    return '%s(%s)%s' % (s, ', '.join(ps), ' const' if d['const'] else '')


def _strip_params(s):
    s = s.strip()
    if s.endswith(' const'):
        s = s[:-6]
    if s.endswith(')') and not s.endswith('operator()'):
        depth = 0
        for i in range(len(s) - 1, -1, -1):
            c = s[i]
            if c == ')':
                depth += 1
            elif c == '(':
                depth -= 1
                if depth == 0:
                    s = s[:i]
                    break
    elif s.endswith('operator()()'):
        s = s[:-2]
    # template functions carry their return type: keep the last top-level word
    depth = 0
    cut = 0
    for i, c in enumerate(s):
        if c in '<(':
            depth += 1
        elif c in '>)':
            depth -= 1
        elif c == ' ' and depth == 0 and not s[:i].endswith('operator'):
            cut = i + 1
    return s[cut:]


def gnu_key(dem):
    """Key of a demangled GCC symbol: function statics keep their own name only."""
    if dem.startswith('guard variable'):
        return '#guard'
    if dem.startswith(('typeinfo', 'vtable for', 'VTT for')):
        return dem
    m = re.search(r'\)(?: const)?::([A-Za-z_]\w*)$', dem)
    if m:                               # Func(args)::local_static
        return m.group(1)
    return _squash(_strip_params(dem))


# ---------------------------------------------------------------- source fences
FENCE = re.compile(r'^/\* @socom-skeleton (body|stub) (\S+) \*/')


def fence_spans(text):
    """name -> (fence line, brace line, end line), 1-based, for one source file's text."""
    lines = text.split('\n')
    out = {}
    i, n = 0, len(lines)
    while i < n:
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        name = m.group(2)
        j = i + 1
        while j < n and j < i + 10 and lines[j].strip() != '{' and not lines[j].rstrip().endswith((';', '{')):
            j += 1
        if j >= n or not (lines[j].strip() == '{' or lines[j].rstrip().endswith('{')) or lines[j].rstrip().endswith(';'):
            i += 1
            continue
        depth = 0
        k = j
        while k < n:
            depth += lines[k].count('{') - lines[k].count('}')
            if depth <= 0 and k >= j and '{' in ''.join(lines[j:k + 1]):
                break
            k += 1
        out.setdefault(name, (i + 1, j + 1, k + 1))
        i = k + 1
    return out


def src_files(commit=None):
    """{repo-relative path: text} of src/ (working tree, or a commit through git archive)."""
    out = {}
    if commit is None:
        for f in glob.glob(os.path.join(_dev.SRC, '**', '*'), recursive=True):
            if f.endswith(('.cpp', '.c', '.h', '.hpp', '.inl')):
                rel = os.path.relpath(f, _dev.REPO).replace('\\', '/')
                out[rel] = open(f, encoding='utf-8', errors='replace').read().replace('\r\n', '\n')
        return out
    import io
    import tarfile
    data = subprocess.run(['git', '-C', _dev.REPO, 'archive', '--format=tar', commit, 'src'],
                          capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        for m in t.getmembers():
            if m.isfile() and m.name.endswith(('.cpp', '.c', '.h', '.hpp', '.inl')):
                out[m.name] = t.extractfile(m).read().decode('utf-8', 'replace').replace('\r\n', '\n')
    return out


def all_fences(files):
    """mangled fence name -> (file, fence line, brace line, end line) over {path: text}."""
    out = {}
    for p, text in files.items():
        if p.endswith(('.cpp', '.c')) and '@socom-skeleton' in text:
            for n, sp in fence_spans(text).items():
                out.setdefault(n, (p,) + sp)
    return out


# ---------------------------------------------------------------- features
STORES = {'sb': 'S1', 'sh': 'S2', 'sw': 'S4', 'sd': 'S8', 'sq': 'S16', 'swc1': 'S4f', 'sqc2': 'S16v',
          'swl': 'S4', 'swr': 'S4', 'sdl': 'S8', 'sdr': 'S8'}
LOADS = {'lb': 'L1s', 'lbu': 'L1u', 'lh': 'L2s', 'lhu': 'L2u', 'lw': 'L4', 'lwu': 'L4', 'ld': 'L8',
         'lq': 'L16', 'lwc1': 'L4f', 'lqc2': 'L16v', 'lwl': 'L4', 'lwr': 'L4', 'ldl': 'L8', 'ldr': 'L8'}
NOWRITE = set(STORES) | {'j', 'jr', 'jal', 'jalr', 'b', 'bal', 'mtc1', 'ctc1', 'mthi', 'mtlo', 'mthi1',
                         'mtlo1', 'teq', 'tne', 'sync', 'sync.l', 'sync.p', 'cache', 'nop', 'break',
                         'syscall', 'qmtc2', 'ctc2', 'mtsa', 'mtsab', 'mtsah', 'ei', 'di', 'eret', 'mtc0',
                         'pref', 'ssnop', 'div', 'divu', 'div1', 'divu1'}
CALL_CLOBBER = ('v0', 'v1', 'a0', 'a1', 'a2', 'a3', 'a4', 'a5', 'a6', 'a7', 't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
                't8', 't9', 'at')
FOPS = {'add.s': ('add',), 'sub.s': ('sub',), 'mul.s': ('mul',), 'div.s': ('div',), 'sqrt.s': ('sqrt',),
        'rsqrt.s': ('div', 'sqrt'), 'abs.s': ('abs',), 'neg.s': ('neg',), 'madd.s': ('mul', 'add'),
        'msub.s': ('mul', 'sub'), 'madda.s': ('mul', 'add'), 'msuba.s': ('mul', 'sub'), 'mula.s': ('mul',),
        'adda.s': ('add',), 'suba.s': ('sub',), 'max.s': ('max',), 'min.s': ('min',),
        'cvt.s.w': ('cvt',), 'cvt.w.s': ('cvt',), 'trunc.w.s': ('cvt',)}
GPR = set(['zero', 'at', 'v0', 'v1', 'gp', 'sp', 'fp', 's8', 'ra'] + ['a%d' % i for i in range(8)] +
          ['t%d' % i for i in range(10)] + ['s%d' % i for i in range(8)] + ['k0', 'k1'])
MEMOP = re.compile(r'^(-?(?:0x)?[0-9a-f]+)\((\w+)\)$')
TARGET = re.compile(r'^([0-9a-f]+)(?: <(.+)>)?$')


# runtime helpers of the two compilers under one name; '#cvt' = a float / int conversion (an
# instruction in GCC's code, a call in Metrowerks'), None = left out (port-only tracing)
CALLMAP = {'sqrtf': '#sqrt', 'fabsf': '#abs', 'operatordelete': None, 'operatordelete[]': None,
           'fptosi': '#cvt', 'fptoui': '#cvt', 'sitofp': '#cvt', 'uitofp': '#cvt',
           'dpmul': 'double*', '__muldf3': 'double*', 'dpadd': 'double+', '__adddf3': 'double+',
           'dpsub': 'double-', '__subdf3': 'double-', 'dpdiv': 'double/', '__divdf3': 'double/',
           'dpcmp': 'double<>', '__eqdf2': 'double<>', '__nedf2': 'double<>', '__ltdf2': 'double<>',
           '__ledf2': 'double<>', '__gtdf2': 'double<>', '__gedf2': 'double<>', '__unorddf2': 'double<>',
           'fptodp': 'float->double', '__extendsfdf2': 'float->double', 'dptofp': 'double->float',
           '__truncdfsf2': 'double->float', 'litodp': 'int->double', '__floatsidf': 'int->double',
           '__floatdidf': 'int->double', 'dptoli': 'double->int', '__fixdfsi': 'double->int',
           'socom_port_trace': None, 'socom_port_tracef': None}


def _imm(s):
    return int(s, 0)


class Feat:
    """Comparison features of one function. Counters: calls (callee key), fconst (float word),
    iconst (integer constants, |v| >= 16), cmpk (compare immediates), strs (string text), mem
    ((offset, 'L'|'S') through non-stack, non-global base registers), memw ((offset, kind)), gst
    (global stores by key), gld (global loads), fops (float operation kinds); scalars size, nbr
    (conditional branches), ind (indirect calls), callees (callee start addresses for flattening)."""

    def __init__(self):
        C = collections.Counter
        self.calls, self.fconst, self.iconst, self.cmpk, self.strs = C(), C(), C(), C(), C()
        self.mem, self.memw, self.gst, self.gld, self.fops = C(), C(), C(), C(), C()
        self.size = self.nbr = self.ind = 0
        self.callees = collections.Counter()   # key -> start address (first seen)
        self.calladdr = {}

    def add(self, o, sign=1):
        for k in ('calls', 'fconst', 'iconst', 'cmpk', 'strs', 'mem', 'memw', 'gst', 'gld', 'fops'):
            a, b = getattr(self, k), getattr(o, k)
            for x, v in b.items():
                a[x] += sign * v
                if a[x] <= 0:
                    del a[x]
        self.nbr += sign * o.nbr
        self.ind += sign * o.ind
        self.calladdr.update(o.calladdr)


def features(elf, insns, start, end, keyof, skip_calls=()):
    """Features of the instructions insns (Dis.insns) of the function [start, end) of elf.
    keyof(name) gives the compiler-independent key of a symbol name."""
    F = Feat()
    F.size = end - start
    known = {}          # reg -> ('hi', v) | ('addr', v) | ('const', v) | ('stack',)
    lastlui = {}        # reg -> the last lui value written to it
    lo, hi = elf.range
    gp = elf.gp

    def symkey(a):
        d = elf.data_at(a)
        if d is None or d[0].startswith('@'):
            return None             # an unnamed address means nothing across two images
        n, off = d
        k = keyof(n)
        return k if not off else '%s+0x%x' % (k, off)

    def lit(s):
        # a string literal, not data that happens to be printable, not a build path (__FILE__)
        return s is not None and (len(s) >= 4 or s.isalnum()) and not s.startswith('/') and \
            sum(c.isalnum() or c in ' _%.' for c in s) >= 0.6 * len(s)

    def note_addr(a):
        s = elf.cstr(a)
        s = s if lit(s) else None
        d = elf.data_at(a)
        if s is not None and (d is None or d[0].startswith('@')):
            F.strs[s] += 1
            return True
        if s is None and d is not None and d[1] == 0:
            # a table of string pointers (names[] = {"a", "b"}): its strings count as used here
            sz = elf.byname.get(d[0], (0, 0))[1]
            for k in range(min(sz // 4, 128)):
                w = elf.word(a + 4 * k)
                s2 = elf.cstr(w) if w and lo <= w < hi else None
                if lit(s2):
                    F.strs[s2] += 1
        return False

    # a call's delay slot runs before the call clobbers the argument registers
    seq = list(insns)
    i = 0
    while i < len(seq) - 1:
        if seq[i][1] in ('jal', 'jalr', 'bal'):
            seq[i], seq[i + 1] = seq[i + 1], seq[i]
            i += 1
        i += 1
    for a, op, ops, raw in seq:
        args = [x.strip() for x in ops.split(',')] if ops else []
        if op in ('jal', 'j', 'bal') and args:
            m = TARGET.match(args[-1])
            t = int(m.group(1), 16) if m else None
            if t is not None and (op != 'j' or not (start <= t < end)):
                f = elf.func_at(t)
                name = f[1] if f and f[0] == t else (m.group(2) or '0x%x' % t)
                k = keyof(name)
                k = CALLMAP.get(k, k)
                if k and k.startswith('#'):
                    F.fops[k[1:]] += 1
                elif k and not k.startswith('std::') and k not in skip_calls:
                    F.calls[k] += 1
                    F.calladdr.setdefault(k, t)
            for r in CALL_CLOBBER:
                known.pop(r, None)
            continue
        if op == 'jalr':
            F.ind += 1
            for r in CALL_CLOBBER:
                known.pop(r, None)
            continue
        if op.startswith('b') and op not in ('b', 'bal', 'break') or op in ('bc1t', 'bc1f', 'bc1tl', 'bc1fl'):
            F.nbr += 1
            continue
        if op in FOPS:
            for x in FOPS[op]:
                F.fops[x] += 1
        elif op.startswith('c.') and op.endswith('.s'):
            F.fops['cmp'] += 1
        if op == 'lui' and len(args) == 2:
            known[args[0]] = ('hi', (_imm(args[1]) << 16) & 0xffffffff)
            lastlui[args[0]] = known[args[0]][1]
            continue
        if op == 'li' and len(args) == 2:
            v = _imm(args[1])
            lastlui.pop(args[0], None)
            known[args[0]] = ('const', v & 0xffffffff)
            if abs(v) >= 16 and v not in (0xff, 0xffff, -1):
                F.iconst[v] += 1
            continue
        if op in ('addiu', 'daddiu', 'ori') and len(args) == 3:
            b = args[1]
            imm = _imm(args[2])
            if b == 'sp' or (b in known and known[b][0] == 'stack'):
                known[args[0]] = ('stack',)
                continue
            if b == 'gp' and gp:
                v = (gp + imm) & 0xffffffff
                known[args[0]] = ('addr', v)
                note_addr(v)
                continue
            if b in lastlui and b == args[0] and (b not in known or known[b][0] == 'addr') and op != 'ori':
                # Metrowerks puts one lui in many delay slots: "addiu a0,a0,lo" after a label
                # reuses the lui, not the address an earlier addiu built
                v = (lastlui[b] + imm) & 0xffffffff
                if elf.cstr(v) is not None or v in elf.at:
                    known[b] = ('addr', v)
                    note_addr(v)
                    continue
            if b in known and known[b][0] in ('hi', 'addr', 'const'):
                base = known[b][1]
                v = (base | imm) if op == 'ori' else (base + imm) & 0xffffffff
                if known[b][0] == 'hi' or known[b][0] == 'addr':
                    if lo <= v < hi:
                        known[args[0]] = ('addr', v)
                        note_addr(v)
                    else:
                        known[args[0]] = ('const', v)
                        sv = v - (1 << 32) if v & 0x80000000 else v
                        if abs(sv) >= 16:
                            F.iconst[sv] += 1
                    continue
            known.pop(args[0], None)
            lastlui.pop(args[0], None)
            continue
        if op in ('slti', 'sltiu') and len(args) == 3:
            v = _imm(args[2])
            if abs(v) >= 2:
                F.cmpk[v] += 1
            known.pop(args[0], None)
            lastlui.pop(args[0], None)
            continue
        if op == 'mtc1' and len(args) == 2:
            r = args[0]
            if r in known and known[r][0] in ('hi', 'const', 'addr'):
                v = known[r][1] & 0xffffffff
                if v:
                    F.fconst[v] += 1
                    sv = v - (1 << 32) if v & 0x80000000 else v
                    if known[r][0] != 'hi' and F.iconst.get(sv):
                        F.iconst[sv] -= 1
                        if not F.iconst[sv]:
                            del F.iconst[sv]
            continue
        if op in ('move',) and len(args) == 2:
            if args[1] in known:
                known[args[0]] = known[args[1]]
            elif args[1] == 'sp':
                known[args[0]] = ('stack',)
            else:
                known.pop(args[0], None)
            lastlui.pop(args[0], None)
            continue
        kind = STORES.get(op) or LOADS.get(op)
        if kind and len(args) == 2:
            m = MEMOP.match(args[1])
            if m:
                imm, b = _imm(m.group(1)), m.group(2)
                ls = kind[0]
                if b == 'sp' or (b in known and known[b][0] == 'stack'):
                    pass
                elif (b == 'gp' and gp) or (b in known and known[b][0] in ('hi', 'addr')):
                    v = ((gp if b == 'gp' else known[b][1]) + imm) & 0xffffffff
                    if op == 'lwc1':
                        # a literal (no symbol, a Metrowerks @n, a 4- / 8-byte named constant) is
                        # a float constant; a member of a larger global object is a global read
                        d = elf.data_at(v)
                        w = elf.word(v)
                        if w and (d is None or d[0].startswith('@') or
                                  (d[1] == 0 and elf.byname.get(d[0], (0, 0))[1] in (4, 8))):
                            F.fconst[w] += 1
                        if symkey(v):
                            F.gld[symkey(v)] += 1
                    elif ls == 'S':
                        if symkey(v):
                            F.gst[symkey(v)] += 1
                    else:
                        if symkey(v):
                            F.gld[symkey(v)] += 1
                        dv = elf.data_at(v)
                        if op == 'lw' and dv and dv[0].startswith('@'):   # Metrowerks: a literal's pointer in data
                            w = elf.word(v)
                            s = elf.cstr(w) if w else None
                            if lit(s):
                                F.strs[s] += 1
                elif imm >= 0:
                    F.mem[(imm, ls)] += 1
                    F.memw[(imm, kind)] += 1
            if kind[0] == 'L' and args[0] in GPR:
                known.pop(args[0], None)
                lastlui.pop(args[0], None)
            continue
        if args and op not in NOWRITE and args[0] in GPR:
            known.pop(args[0], None)
            lastlui.pop(args[0], None)
    return F


# ---------------------------------------------------------------- ground truth
def audit_rows():
    """[(note, address, verdict, grade, evidence)] from the verdict tables of the audit notes."""
    rows = []
    for p in sorted(glob.glob(os.path.join(_dev.REPO, 'docs', 'port', 'notes', 'audit-*.md'))):
        note = os.path.basename(p)[:-3]
        cols = None
        for line in open(p, encoding='utf-8', errors='replace'):
            if not line.startswith('|'):
                cols = None
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            low = [c.lower() for c in cells]
            if 'verdict' in low and 'address' in low:
                cols = {c: i for i, c in enumerate(low)}
                continue
            if cols is None or set(line.strip()) <= set('|-: '):
                continue
            try:
                addr = int(re.search(r'0x[0-9a-fA-F]+', cells[cols['address']]).group(0), 16)
            except (AttributeError, IndexError):
                continue
            verdict = cells[cols['verdict']] if cols['verdict'] < len(cells) else ''
            grade = cells[cols['grade']] if 'grade' in cols and cols['grade'] < len(cells) else ''
            m = re.match(r'\W*(MATCH|DEFECT-FIXED|DEFECT|DEVIATION-KEPT|UNJUDGED|WRITTEN|NEW)\W*([ABC])?', verdict.upper())
            v = m.group(1) if m else verdict.upper()
            if not grade and m and m.group(2):
                grade = m.group(2)
            ev = cells[cols['evidence']] if 'evidence' in cols and cols['evidence'] < len(cells) else ' '.join(cells)
            rows.append((note, addr, v, grade.strip('*` '), ev))
    return rows
