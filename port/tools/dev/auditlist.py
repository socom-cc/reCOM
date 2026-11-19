"""auditlist.py [--band large|medium|small|all] [--modules RE] [--split N | --fns N] [--out NAME] [--summary]
Lists of fenced functions for the correctness audit (docs/port/AUDIT_PLAN.md), from the fences in
src/ and the ELF's symbol sizes. Functions already judged are left out: every address in a table
row of docs/port/notes/audit-*.md counts as judged.
  --band     large = 700 bytes or more, medium = 200 to 699, small = under 200 (default large)
  --modules  regex on the module (gamez/zUI, Apps/FTS/hud, ...); default all
  --split N  N lists of about equal bytes, whole files kept together (default 1)
  --fns N    lists of about N functions each (as many as needed, equal counts), whole files kept
             together: the small band's lists, for auditpack.py --by-file
  --out      writes build/port/audit/<NAME>[-a|-b|...].md; without it prints to stdout
  --summary  per module: functions and bytes still to judge in each band; writes nothing"""
import _dev
import sys, re, struct, os, glob
import fences

BANDS = {'large': (700, 1 << 30), 'medium': (200, 700), 'small': (0, 200), 'all': (0, 1 << 30)}


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def symbols():
    elf = _dev.elf()
    e_shoff, = struct.unpack_from('<I', elf, 0x20)
    shentsize, shnum, _ = struct.unpack_from('<HHH', elf, 0x2e)
    secs = [struct.unpack_from('<IIIIIIIIII', elf, e_shoff + i * shentsize) for i in range(shnum)]
    sym = {}
    for s in secs:
        if s[1] == 2:
            strtab = secs[s[6]]
            for i in range(s[5] // 16):
                nm, val, sz, info, _, _ = struct.unpack_from('<IIIBBH', elf, s[4] + i * 16)
                n = elf[strtab[4] + nm: elf.index(b'\0', strtab[4] + nm)].decode('latin1')
                if (info & 0xf) == 2:
                    sym.setdefault(n, (val, sz))
    return sym


def judged(root):
    done = set()
    for p in glob.glob(os.path.join(root, 'docs', 'port', 'notes', 'audit-*.md')):
        for line in open(p, encoding='utf-8', errors='replace'):
            if line.startswith('|'):
                for a in re.findall(r'\|\s*`?(0x[0-9a-fA-F]{6,8})`?\s*\|', line):
                    done.add(int(a, 16))
    return done


def module(path):
    parts = path.replace('\\', '/').split('/')
    if parts[0] == 'src':
        parts = parts[1:]
    if parts[0] == 'Apps':
        return '/'.join(parts[:3]) if len(parts) > 3 else 'Apps/FTS'
    return '/'.join(parts[:2])


def main():
    root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    sym = symbols()
    done = judged(root)
    modre = re.compile(arg('--modules', '.'))
    rows = []   # (module, file, addr, size, name)
    for n, v in fences.status().items():
        a, sz = sym.get(n, (0, 0))
        if not a:
            continue
        f = v[1].replace('\\', '/')
        f = f[4:] if f.startswith('src/') else f
        rows.append((module(f), f, a, sz, n))
    if '--summary' in sys.argv:
        mods = {}
        for m, f, a, sz, n in rows:
            s = mods.setdefault(m, [0] * 8)
            b = 0 if sz >= 700 else 1 if sz >= 200 else 2
            s[6] += 1; s[7] += sz
            if a not in done:
                s[b * 2] += 1; s[b * 2 + 1] += sz
        print('%-18s %15s %15s %15s %15s' % ('to judge:', '700+ fn / B', '200-699 fn / B', '<200 fn / B', 'all fenced'))
        tot = [0] * 8
        for m, s in sorted(mods.items(), key=lambda x: -(x[1][1] + x[1][3] + x[1][5])):
            if not modre.search(m):
                continue
            print('%-18s %5d %9d %5d %9d %5d %9d %5d %9d' % ((m,) + tuple(s)))
            tot = [x + y for x, y in zip(tot, s)]
        print('%-18s %5d %9d %5d %9d %5d %9d %5d %9d' % (('TOTAL',) + tuple(tot)))
        return
    band = arg('--band', 'large')
    lo, hi = BANDS[band]
    pick = sorted((r for r in rows if modre.search(r[0]) and lo <= r[3] < hi and r[2] not in done),
                  key=lambda r: (r[1], r[2]))
    nsplit = int(arg('--split', '1'))
    # whole files per list, largest file first into the lightest list (bytes; functions with --fns)
    files = {}
    for r in pick:
        files.setdefault(r[1], []).append(r)
    weight = lambda rs: sum(r[3] for r in rs)
    if '--fns' in sys.argv:
        nsplit = max(1, -(-len(pick) // int(arg('--fns'))))
        weight = len
    lists = [[] for _ in range(nsplit)]
    for f in sorted(files, key=lambda f: -weight(files[f])):
        min(lists, key=weight).extend(files[f])
    out = arg('--out')
    for i, l in enumerate(lists):
        l.sort(key=lambda r: (r[1], r[2]))
        tag = chr(ord('a') + i) if nsplit > 1 else ''
        text = ['# Audit list %s%s' % (out or band, '-' + tag if tag else ''), '',
                '%d fenced functions (%d bytes), band %s, modules /%s/, not judged before. Grouped by file.'
                % (len(l), sum(r[3] for r in l), band, modre.pattern), '',
                '| # | Address | Bytes | Symbol | File |', '|---|---|---|---|---|']
        text += ['| %d | 0x%x | %d | `%s` | %s |' % (k + 1, r[2], r[3], r[4], r[1]) for k, r in enumerate(l)]
        if out:
            d = os.path.join(root, 'build', 'port', 'audit')
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, out + ('-' + tag if tag else '') + '.md')
            open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(text) + '\n')
            print('%s: %d functions, %d bytes, %d files' % (os.path.relpath(p, root), len(l), sum(r[3] for r in l), len(set(r[1] for r in l))))
        else:
            print('\n'.join(text))


if __name__ == '__main__':
    main()
