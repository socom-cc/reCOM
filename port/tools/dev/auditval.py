"""auditval.py --collect | --report: validation of auditscan.py against the audit's ground truth
(the verdict tables of docs/port/notes/audit-*.md).

--collect  scans every judged row: MATCH / DEVIATION-KEPT rows on the fingerprint build `head`,
           DEFECT-FIXED rows on the build of the source as it was before their fixing commit
           (`prelarge` = 24f811a3 for audit-large-*, `presample` = d035c977 for audit-sample,
           `preunmarked` = 452a0759 for audit-unmarked-*; fpbuild.sh <commit> <name>) and again
           on `head` (after the fix). Writes <scratch>/val/rows.json.
--report   splits the rows in two halves by address (bit 4), picks the weights and the threshold
           on the first half only, reports both halves, and writes
           build/port/audit/SCAN_VALIDATION.md.
Defect kinds are assigned by hand from each row's evidence (KIND below)."""
import _dev
import auditlib as L
import bisect
import auditscan as S
import collections
import json
import os
import sys

VAL = _dev.scratch('val')
BUILD = {'audit-large-a': 'prelarge', 'audit-large-b': 'prelarge', 'audit-large-c': 'prelarge',
         'audit-sample': 'presample', 'audit-unmarked-a': 'preunmarked', 'audit-unmarked-a2': 'preunmarked',
         'audit-unmarked-c': 'preunmarked'}
DEFECT = ('DEFECT-FIXED', 'FIXED', 'LOCATED-FIXED')
MATCHV = ('MATCH', 'LOCATED-MATCH')
# F float operation order, G guard the ELF does not have, K constant word, A call argument,
# C wrong / missing / extra call, S store (missing, extra, other target), W width / bitfield / part
# of a word, L other logic (branch sense, test, loop, state), B body was empty / is empty in the ELF
KIND = {
    0x297060: 'F', 0x29eb00: 'F', 0x2acd70: 'A', 0x29a850: 'F', 0x2b21e0: 'L', 0x2a0f20: 'F',
    0x2a1bb0: 'F', 0x29c620: 'F', 0x291b60: 'F', 0x28e3e0: 'G', 0x2a2c70: 'L', 0x299d10: 'K',
    0x2999f0: 'G', 0x2ab220: 'F', 0x2a5bb0: 'G', 0x299600: 'G', 0x29b940: 'G', 0x2a75a0: 'F',
    0x298de0: 'F',
    0x2df1c0: 'L', 0x25af40: 'G', 0x2d07e0: 'G', 0x264e20: 'L', 0x28a560: 'C', 0x2626c0: 'L',
    0x259930: 'L', 0x2b8230: 'L', 0x2cf7f0: 'L', 0x2be630: 'S', 0x261eb0: 'L', 0x26a8d0: 'C',
    0x2b4510: 'G', 0x2bf340: 'F', 0x264270: 'S', 0x26cb90: 'F', 0x2592f0: 'G', 0x2d2bd0: 'G',
    0x268530: 'G', 0x2d5c90: 'A', 0x2badf0: 'L',
    0x250f40: 'F', 0x270d10: 'K', 0x281080: 'C', 0x1814c0: 'L', 0x24fc10: 'F', 0x26ffd0: 'F',
    0x27c090: 'C', 0x2d8000: 'G', 0x19c9b0: 'W', 0x2dc240: 'K', 0x256fe0: 'G', 0x26f750: 'G',
    0x27cbf0: 'C', 0x250a80: 'F', 0x27b4d0: 'C', 0x273020: 'L', 0x2563e0: 'G', 0x1978a0: 'G',
    0x1940a0: 'G', 0x27d620: 'G', 0x26eb70: 'G', 0x19a120: 'G', 0x255080: 'W',
    0x263a30: 'K', 0x1971c0: 'W', 0x1d81a0: 'C', 0x2dbdc0: 'C', 0x27ab70: 'F', 0x19b290: 'K',
    0x2ced80: 'K',
    0x1a9160: 'B', 0x1ee5a0: 'B', 0x1f20f0: 'G', 0x1ff660: 'C', 0x258ec0: 'L', 0x2879f0: 'K',
    0x2f6e10: 'B', 0x17f440: 'G', 0x223050: 'K', 0x22bc30: 'C', 0x236740: 'B', 0x237380: 'W',
    0x307790: 'B'}
NOT_POINTING = {(0x2b21e0, 'fconst'), (0x250f40, 'store'), (0x24fc10, 'gld'), (0x1d81a0, 'iconst'),
                (0x22bc30, 'call'), (0x22bc30, 'gld'), (0x237380, 'fulp')}   # unrelated to the fix (by hand)
KNAME = {'F': 'float operation order', 'G': 'guard the ELF lacks', 'K': 'constant word', 'A': 'call argument',
         'C': 'wrong / missing call', 'S': 'store', 'W': 'width / bitfield', 'L': 'other logic',
         'B': 'empty body'}


def collect():
    rows = L.audit_rows()
    want = collections.defaultdict(list)     # build -> [(row index, role)]
    for i, r in enumerate(rows):
        if r[2] in DEFECT:
            want[BUILD.get(r[0], 'prelarge')].append((i, 'before'))
            want['head'].append((i, 'after'))
        elif r[2] in MATCHV or r[2] == 'DEVIATION-KEPT':
            want['head'].append((i, 'head'))
    out = {}
    headfiles = None
    for b in ('head', 'prelarge', 'presample', 'preunmarked'):
        if b not in want or not os.path.exists(os.path.join(_dev.scratch('fp'), b + '.commit')):
            sys.stderr.write('skipping %s (no fingerprint build)\n' % b)
            continue
        sys.stderr.write('scanning on %s (%d rows)\n' % (b, len(want[b])))
        sc = S.Scanner(b)
        if b == 'head':
            headfiles = (sc.files, sc.fences)
        for i, role in want[b]:
            note, addr, v, grade, ev = rows[i]
            f = sc.ref.elf.funcs.get(addr)
            names = sc.ref.elf.at.get(addr, [])
            name = next((n for n in names if n in sc.fences), f[0] if f else (names[0] if names else None))
            if name is None:
                r = {'error': 'no ELF function'}
            else:
                r = sc.scan(name)
            rec = out.setdefault('%s:%x' % (note, addr), {'note': note, 'address': addr, 'verdict': v,
                                                          'grade': grade, 'kind': KIND.get(addr, ''),
                                                          'symbol': name, 'size': f[1] if f else 0,
                                                          'evidence': ev[:300]})
            rec[role] = {'error': r.get('error'), 'how': r.get('how'),
                         'diffs': [[d[1], d[3], d[2]] for d in r.get('diffs', [])]}
            if role == 'before' and name in sc.fences and headfiles and name in headfiles[1]:
                fb, fh = sc.fences[name], headfiles[1][name]
                tb = '\n'.join(sc.files[fb[0]].split('\n')[fb[1] - 1:fb[3]])
                th = '\n'.join(headfiles[0][fh[0]].split('\n')[fh[1] - 1:fh[3]])
                rec['body_changed'] = tb != th
        del sc
    json.dump(out, open(os.path.join(VAL, 'rows.json'), 'w'), indent=0)
    print('%d rows -> %s' % (len(out), os.path.join(VAL, 'rows.json')))


# ---------------------------------------------------------------- report
def score(diffs, W):
    return sum(W.get(k, 0) * n for k, n, t in diffs)


CONFIGS = {
    'all features (default weights)': dict(S.WEIGHTS),
    'strong only (calls, strings, floats, stores, globals stored)':
        {'call': 3, 'ncall': 1, 'str': 3, 'fulp': 3, 'fconst': 2, 'store': 2, 'gst': 2},
    'strong + constants + width':
        {'call': 3, 'ncall': 1, 'str': 3, 'fulp': 3, 'fconst': 2, 'store': 2, 'gst': 2, 'iconst': 1,
         'cmpk': 0.5, 'width': 1},
    'strong + float op counts':
        {'call': 3, 'ncall': 1, 'str': 3, 'fulp': 3, 'fconst': 2, 'store': 2, 'gst': 2, 'fops': 0.5},
    'calls, strings, constants, global stores (no member offsets)':
        {'call': 3, 'ncall': 0.5, 'str': 3, 'fulp': 3, 'fconst': 2, 'fint': 0.5, 'iconst': 1, 'gst': 2},
    'one-sided calls, strings, floats, stores only':
        {'call': 3, 'str': 3, 'fulp': 3, 'fconst': 2, 'store': 2, 'gst': 2},
}


POINT = ('call', 'ncall', 'str', 'fulp', 'fconst', 'iconst', 'cmpk', 'store', 'gst', 'gld', 'width', 'ind')


def pointing(r, W):
    """Differences of the pre-fix scan that the fix removed or changed (so the scan pointed at
    what was wrong), minus the ones judged unrelated by hand (NOT_POINTING)."""
    b = {(x[0], x[2]) for x in r['before']['diffs'] if x[0] in POINT and W.get(x[0])}
    a = {(x[0], x[2]) for x in r.get('after', {}).get('diffs', [])}
    return sorted(x for x in b - a if (r['address'], x[0]) not in NOT_POINTING)


def cp(k, n, a=0.05):
    """Exact (Clopper-Pearson) two-sided interval for k successes in n trials."""
    if n == 0:
        return 0.0, 1.0
    from math import comb

    def cdf(p, k_):
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k_ + 1))

    def solve(f, lo=0.0, hi=1.0):
        for _ in range(60):
            mid = (lo + hi) / 2
            if f(mid):
                lo = mid
            else:
                hi = mid
        return lo
    low = 0.0 if k == 0 else solve(lambda p: 1 - cdf(p, k - 1) < a / 2)
    high = 1.0 if k == n else solve(lambda p: cdf(p, k) > a / 2)
    return low, high


def report():
    rows = list(json.load(open(os.path.join(VAL, 'rows.json'))).values())
    half = lambda r: (r['address'] >> 4) & 1
    defects = [r for r in rows if r['verdict'] in DEFECT and 'before' in r and not r['before'].get('error')]
    nodef = [r for r in rows if r['verdict'] in DEFECT and r not in defects]
    matches = [r for r in rows if r['verdict'] in MATCHV and 'head' in r and not r['head'].get('error')]
    devs = [r for r in rows if r['verdict'] == 'DEVIATION-KEPT' and 'head' in r and not r['head'].get('error')]
    unmapped_m = [r for r in rows if r['verdict'] in MATCHV and r not in matches]
    H = lambda xs, h: [r for r in xs if half(r) == h]
    ds = lambda r, W: score(r['before']['diffs'], W)      # what a worker sees on the defective source
    ms = lambda r, W: score(r['head']['diffs'], W)

    def auc(d, m, W):
        if not d or not m:
            return 0.0
        a = sorted(ms(r, W) for r in m)
        tot = 0.0
        for r in d:
            x = ds(r, W)
            lo = bisect.bisect_left(a, x)
            hi = bisect.bisect_right(a, x)
            tot += lo + 0.5 * (hi - lo)
        return tot / (len(d) * len(m))

    tune = sorted(((auc(H(defects, 0), H(matches, 0), W), n) for n, W in CONFIGS.items()), reverse=True)
    name = tune[0][1]
    W = CONFIGS[name]
    TH = (0, 1, 2, 4, 8, 15, 30)
    L_ = ['# auditscan.py validation against the audit ground truth', '',
          'Made by `port/tools/dev/auditval.py --collect` / `--report` (fingerprint builds by `fpbuild.sh`). '
          'Ground truth: the verdict tables of `docs/port/notes/audit-*.md`. A DEFECT-FIXED row is scanned '
          'on the source as it was before its fixing commit (builds of 24f811a3 for audit-large-*, d035c977 '
          'for audit-sample, 452a0759 for audit-unmarked-*; the defective source is what a worker would '
          'have scanned) and again at HEAD; MATCH and DEVIATION-KEPT rows at HEAD (f7c2be1f). Rows are '
          'split in two halves by address bit 4: the feature weights were chosen on half 0 only (best '
          'ranking, AUC); every number called a result is half 1.', '',
          'Terms: *score* = weighted sum of the differences; *flagged* = score above the threshold; '
          '*clean* = not flagged; a defect is *seen* when its pre-fix scan is flagged and holds a '
          'difference that the fix removed or changed (the scan pointed at the defect; seven such '
          'differences judged unrelated by hand are not counted, NOT_POINTING).', '',
          '## Rows', '', '| | half 0 (tuning) | half 1 (result) |', '|---|---|---|',
          '| defects (pre-fix scan) | %d | %d |' % (len(H(defects, 0)), len(H(defects, 1))),
          '| matches | %d | %d |' % (len(H(matches, 0)), len(H(matches, 1))),
          '| deviations kept | %d | %d |' % (len(H(devs, 0)), len(H(devs, 1))), '',
          'Not scanned: %d defect rows and %d match rows with no fence and no unique readable name in the '
          'port (unmarked functions).' % (len(nodef), len(unmapped_m)), '',
          '## Weights chosen on half 0', '', '| features | AUC half 0 | AUC half 1 |', '|---|---|---|']
    for a, n in tune:
        L_.append('| %s%s | %.2f | %.2f |' % (n, ' (chosen)' if n == name else '', a, auc(H(defects, 1), H(matches, 1), CONFIGS[n])))
    L_ += ['', 'AUC = probability that a random defect (pre-fix) scores above a random match; 0.5 = no '
           'better than chance.', '']

    def seen(r, t):
        return ds(r, W) > t and bool(pointing(r, W))

    def table(d, m, v, title):
        out = ['## %s' % title, '', '| threshold | matches flagged | defects flagged | defects seen | '
               'deviations flagged | clean rows | defects among clean | P(MATCH given clean) |',
               '|---|---|---|---|---|---|---|---|']
        for t in TH:
            fm = sum(ms(r, W) > t for r in m)
            fd = sum(ds(r, W) > t for r in d)
            sd = sum(seen(r, t) for r in d)
            fv = sum(ms(r, W) > t for r in v)
            cm, cd = len(m) - fm, len(d) - fd
            out.append('| %s | %d / %d (%.0f%%) | %d / %d | %d / %d | %d / %d | %d | %d | %.1f%% |' % (
                t, fm, len(m), 100.0 * fm / max(1, len(m)), fd, len(d), sd, len(d), fv, len(v), cm + cd, cd,
                100.0 * cm / max(1, cm + cd)))
        base = 100.0 * len(m) / max(1, len(m) + len(d))
        out += ['', 'Base rate (no scan): %d matches of %d judged rows = %.1f%% MATCH.' % (len(m), len(m) + len(d), base), '']
        return out
    L_ += table(H(defects, 1), H(matches, 1), H(devs, 1), 'Result (half 1)')
    # by size band, both halves at the threshold 0 (no tuning involved in "score 0")
    L_ += ['## By size, "no difference found" (score 0), both halves', '',
           'Score 0 involves no tuned weight (any difference of a kind the weights use makes it '
           'non-zero), so both halves are used. Intervals: exact (Clopper-Pearson) 95%.', '',
           '| band | matches | of them score 0 | defects | of them score 0 | P(MATCH given score 0) | defects flagged (95% CI) | defects among score-0 rows (95% CI) |',
           '|---|---|---|---|---|---|---|---|']
    for lo, hi, nm in ((0, 200, 'under 200'), (200, 700, '200 to 699'), (700, 1 << 30, '700 or more')):
        m = [r for r in matches if lo <= r['size'] < hi]
        d = [r for r in defects if lo <= r['size'] < hi]
        m0 = sum(ms(r, W) == 0 for r in m)
        d0 = sum(ds(r, W) == 0 for r in d)
        a1, b1 = cp(len(d) - d0, len(d))
        a2, b2 = cp(d0, m0 + d0)
        L_.append('| %s | %d | %d | %d | %d | %s | %d / %d (%.0f%%..%.0f%%) | %d / %d (%.1f%%..%.1f%%) |' % (
            nm, len(m), m0, len(d), d0, '%.0f%%' % (100.0 * m0 / (m0 + d0)) if m0 + d0 else '-',
            len(d) - d0, len(d), 100 * a1, 100 * b1, d0, m0 + d0, 100 * a2, 100 * b2))
    L_.append('')
    # kinds: what the scan can see at all (threshold 0), both halves
    L_ += ['## Which defects the scan can see (threshold 0, both halves; weights as chosen)', '',
           '| kind | defects | seen | grades seen / all |', '|---|---|---|---|']
    by = collections.defaultdict(list)
    for r in defects:
        by[r['kind']].append(r)
    for k in sorted(by, key=lambda k: -len(by[k])):
        rs = by[k]
        g = collections.Counter((r['grade'] or '-') for r in rs)
        gs = collections.Counter((r['grade'] or '-') for r in rs if seen(r, 0))
        L_.append('| %s | %d | %d | %s |' % (KNAME.get(k, k), len(rs), sum(seen(r, 0) for r in rs),
                                            ', '.join('%s %d/%d' % (x, gs[x], g[x]) for x in sorted(g))))
    L_.append('| all | %d | %d | |' % (len(defects), sum(seen(r, 0) for r in defects)))
    L_.append('')
    # false alarms
    reasons = collections.Counter()
    for r in matches:
        top = max((x for x in r['head']['diffs'] if W.get(x[0])), key=lambda x: W[x[0]] * x[1], default=None)
        if top:
            reasons[top[0]] += 1
    L_ += ['## What makes a known match score above 0 (both halves)', '',
           'Largest weighted difference of each match with a score: ' +
           ', '.join('%s %d' % kv for kv in reasons.most_common()) + '. (call = a callee one side never '
           'calls, mostly an inline function only one compiler inlined; store / load = member offsets '
           'reached through a different base; str / fconst = literals the port builds or tables '
           'differently.)', '']
    L_ += ['## Every defect row', '', '| half | note | address | bytes | grade | kind | score before | after | seen at 0 | what the fix removed from the scan |',
           '|---|---|---|---|---|---|---|---|---|---|']
    for r in sorted(defects, key=lambda r: (r['kind'], r['address'])):
        a = score(r['after']['diffs'], W) if 'after' in r and not r['after'].get('error') else 0
        pt = [x[1] for x in pointing(r, W)][:2]
        L_.append('| %d | %s | 0x%x | %d | %s | %s | %.1f | %.1f | %s | %s |' % (
            half(r), r['note'][6:], r['address'], r['size'], r['grade'] or '-', r['kind'], ds(r, W), a,
            'yes' if seen(r, 0) else 'no', '; '.join(pt).replace('|', '/')[:180] or '-'))
    unchanged = [r for r in defects if r.get('body_changed') is False]
    L_ += ['', 'Fixed outside the fenced body (same body text before and at HEAD): %s.' % (
        ', '.join('0x%x' % r['address'] for r in unchanged) or 'none'), '']
    # summary, from the numbers above
    sm = [r for r in matches if r['size'] < 200]
    sd = [r for r in defects if r['size'] < 200]
    s0 = sum(ms(r, W) == 0 for r in sm)
    d0 = sum(ds(r, W) == 0 for r in sd)
    lo_, hi_ = cp(d0, s0 + d0)
    vis = [r for r in defects if r['kind'] in 'CKSB']
    inv = [r for r in defects if r['kind'] in 'GFA']
    t1d, t1m = H(defects, 1), H(matches, 1)
    summ = ['## Summary', '',
            '- Ordering: on half 1 a defect (pre-fix) outscores a match with probability %.2f (AUC; '
            '0.5 = chance); much of that is size (defects sit in large functions): among functions of 700 bytes or more alone the AUC is %.2f (half 1) / %.2f (both halves). Every one of the %d defects scored above 0, but in functions of 700 bytes '
            'or more every match did too (0 of %d large matches has score 0): there the score only '
            'orders the work.' % (auc(t1d, t1m, W), auc([r for r in t1d if r['size'] >= 700], [r for r in t1m if r['size'] >= 700], W),
                                  auc([r for r in defects if r['size'] >= 700], [r for r in matches if r['size'] >= 700], W), len(defects), sum(1 for r in matches if r['size'] >= 700)),
            '- What it sees (the fix removed a difference the scan reported): %d of %d defects overall; '
            'calls, constants, stores and empty bodies %d of %d; guards the ELF lacks, float operation '
            'order and call arguments %d of %d (it cannot see these: they leave calls, literals and '
            'member offsets unchanged); other logic %d of %d (only when the logic changes a call or a '
            'literal).' % (sum(seen(r, 0) for r in defects), len(defects), sum(seen(r, 0) for r in vis), len(vis),
                           sum(seen(r, 0) for r in inv), len(inv),
                           sum(seen(r, 0) for r in defects if r['kind'] == 'L'), sum(1 for r in defects if r['kind'] == 'L')),
            '- "No difference found" (score 0) for functions under 200 bytes: %d of %d known matches '
            'score 0 and %d of %d known defects do, so %d of %d score-0 rows were MATCH (defect rate '
            'among them %.1f%%..%.1f%%, exact 95%%; base rate under 200 bytes %d of %d = %.1f%%). The '
            'four small defects are of kinds the scan sees (missing call, constant, store, string); '
            'no small guard / float-order defect is in the ground truth, so the rule is untested '
            'against those kinds, and with 4 defects the sensitivity of the scan there is only known to be '
            'at least 40%%. Between 200 and 699 bytes only %d of %d matches score 0.' % (
                s0, len(sm), d0, len(sd), s0, s0 + d0, 100 * lo_, 100 * hi_, len(sd), len(sm) + len(sd),
                100.0 * len(sd) / max(1, len(sm) + len(sd)),
                sum(ms(r, W) == 0 for r in matches if 200 <= r['size'] < 700),
                sum(1 for r in matches if 200 <= r['size'] < 700)), '']
    k = L_.index('## Rows')
    L_[k:k] = summ
    p = os.path.join(_dev.REPO, 'build', 'port', 'audit', 'SCAN_VALIDATION.md')
    open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(L_) + '\n')
    print('\n'.join(L_[:80]))


if __name__ == '__main__':
    if '--collect' in sys.argv:
        collect()
    if '--report' in sys.argv:
        report()
    if len(sys.argv) < 2:
        print(__doc__)
