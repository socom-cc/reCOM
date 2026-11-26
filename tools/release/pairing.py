"""Pair prototype and release functions and classify them.

Order of work:

1. exact: equal masked bytes (same size, same instructions, same layout) and the
   only such pair for that byte string;
0. pairs, new and removed functions settled by a checker (an input file);
2. call-tree propagation from every pair, starting at the entry point: the k-th
   reference of an exact pair (calls, tail calls, loaded code addresses) leads
   to the callee pair; a deviating or unsure pair aligns its ordered reference
   list with its partner's (see ``call_correspondences``); a callee is paired
   when its votes have a strict majority, exact callers first;
3. many-times-found exact byte strings resolved by position between order
   anchors, then by paired callers;
4. the rest aligned by position between order anchors with a similarity score
   (monotone weighted matching), then unique shared strings anywhere, then
   mutual best matches anywhere among the remaining functions of 16+
   instructions (moved code);
5. classification: exact / deviating / unsure pair / new / removed.

Similarity is ``difflib.SequenceMatcher.ratio()`` over the masked instruction
words: 2*M/(n+m), M = instructions matched in order, the share of instructions
equal. Shape similarity is the same over instructions with every immediate
removed, so a pair with shape similarity 1.0 and equal size differs only in
immediates and offsets. Operation similarity is the same over the operations
alone (no registers, no immediates): it survives register-allocation changes.
"""
from __future__ import annotations

import bisect
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Thresholds (see COMPARISON.md for the distributions that justify them).
DEVIATING_MIN = 0.50  # a positional pair with this similarity is a deviating pair
UNSURE_MIN = 0.30  # below this a positional candidate is not a pair at all
STRONG_SIMILARITY = 0.30  # a pair with independent evidence (exact caller, strings) needs this similarity
STRONG_OPERATIONS = 0.70  # ... or this operation similarity
CALLEE_SIMILARITY = 0.20  # inside an unequal run of calls, a callee candidate needs this similarity
CALLEE_OPERATIONS = 0.50  # ... or this operation similarity
CALL_SLOT_OPERATIONS = 0.40
SMALL_FUNCTION = 256  # bytes: below this the 3-gram prefilter can be overridden ...
SMALL_OPERATIONS = 0.60  # ... by this operation similarity
SLOT_OPERATIONS = 0.25  # a 1-to-1 address slot pair needs this operation similarity ...
SLOT_SIZE_RATIO = 0.10  # ... and this size ratio (a reference slot: the size ratio and its order slot)
SLOT_CALLER_DISTANCE = 0x10000  # callers of a slot pair must lie within this distance in the prototype  # a pair referenced at the same place by a paired caller, in order
GRAM_PREFILTER = 0.15  # shape 3-gram Jaccard needed before computing a similarity
SIZE_RATIO_MIN = 0.25  # smaller/larger size ratio needed for a positional candidate
BAND = 64  # positional candidates: index distance allowed from the gap's diagonal
CALL_BLOCK = 4  # a call of a deviating pair counts only inside an equal block this long
GLOBAL_SLOT_BONUS = 0.2  # global pass: preference for a candidate between the function's own anchors
GLOBAL_SMALL = 256  # global pass: below this size (bytes) look-alikes need agreeing callers
VTABLE_RESEMBLE_SIZE = 32  # bytes: below this, slot functions are not matched by resemblance
VTABLE_RESEMBLANCE = 0.30  # ... and above it they need this resemblance
VTABLE_KEEPS = {"exact", "entry", "settled", "call"}  # pairs a vtable slot does not overrule
SMALL_GAP = 64  # positional gaps with at most this many candidate pairs skip the 3-gram prefilter
AMBIGUITY = 0.05  # an unpaired alternative this close to the chosen score makes a pair unsure


def similarity(a: tuple, b: tuple) -> float:
    if not a and not b:
        return 1.0
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def aligned_indices(a: tuple, b: tuple, min_block: int = 1) -> dict[int, int]:
    """Index map of the equal blocks (at least ``min_block`` words) of two masked word sequences."""

    out = {}
    for block in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if block.size < min_block:
            continue
        for k in range(block.size):
            out[block.a + k] = block.b + k
    return out


def patience_blocks(a: list, b: list) -> list[tuple[int, int, int]]:
    """Matching blocks (i, j, size) of two token lists, ending with a (len(a), len(b), 0) sentinel.

    Tokens that occur once in both lists are aligned first (their longest common
    order), and each stretch between two of them is aligned the same way, falling
    back to difflib only where no unique token is left. A repeated token (the same
    SDK call several times) can then no longer pull its neighbours to the wrong
    occurrence and leave a one-sided gap.
    """

    blocks: list[tuple[int, int, int]] = []

    def solve(alo: int, ahi: int, blo: int, bhi: int) -> None:
        if alo >= ahi or blo >= bhi:
            return
        count_a = Counter(a[alo:ahi])
        count_b = Counter(b[blo:bhi])
        where_b = {b[j]: j for j in range(blo, bhi) if count_b[b[j]] == 1}
        points = [(i, where_b[a[i]]) for i in range(alo, ahi) if count_a[a[i]] == 1 and a[i] in where_b]
        if not points:
            matcher = SequenceMatcher(None, a[alo:ahi], b[blo:bhi], autojunk=False)
            for block in matcher.get_matching_blocks():
                if block.size:
                    blocks.append((alo + block.a, blo + block.b, block.size))
            return
        i0, j0 = alo, blo
        for i, j in sorted(increasing_subsequence(points)):
            solve(i0, i, j0, j)
            blocks.append((i, j, 1))
            i0, j0 = i + 1, j + 1
        solve(i0, ahi, j0, bhi)

    solve(0, len(a), 0, len(b))
    merged: list[tuple[int, int, int]] = []
    for i, j, size in sorted(blocks):
        if merged and merged[-1][0] + merged[-1][2] == i and merged[-1][1] + merged[-1][2] == j:
            merged[-1] = (merged[-1][0], merged[-1][1], merged[-1][2] + size)
        else:
            merged.append((i, j, size))
    merged.append((len(a), len(b), 0))
    return merged


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter) if inter else 0.0


@dataclass
class Pair:
    p: object
    r: object
    evidence: set[str] = field(default_factory=set)
    similarity: float = 0.0
    shape_similarity: float = 0.0
    operation_similarity: float = 0.0
    cls: str = ""
    flags: set[str] = field(default_factory=set)
    call_consistent: int = 0
    call_sites: int = 0  # paired callers whose aligned references lead to this pair
    call_conflicts: list = field(default_factory=list)
    ref_mismatches: int = 0


def increasing_subsequence(points: list[tuple[int, int]]) -> set[tuple[int, int]]:
    """Longest strictly increasing (in both coordinates) subsequence; deterministic."""

    points = sorted(points)
    tails: list[int] = []
    tail_index: list[int] = []
    parent = [-1] * len(points)
    for index, (_, y) in enumerate(points):
        k = bisect.bisect_left(tails, y)
        if k == len(tails):
            tails.append(y)
            tail_index.append(index)
        else:
            tails[k] = y
            tail_index[k] = index
        parent[index] = tail_index[k - 1] if k else -1
    out = set()
    index = tail_index[-1] if tail_index else -1
    while index >= 0:
        out.add(points[index])
        index = parent[index]
    return out


def weighted_monotone_matching(candidates: list[tuple[int, int, float]]) -> list[tuple[int, int, float]]:
    """Maximum-weight set of candidates strictly increasing in both indices."""

    if not candidates:
        return []
    ys = sorted({c[1] for c in candidates})
    rank = {y: i + 1 for i, y in enumerate(ys)}
    size = len(ys)
    tree_val = [0.0] * (size + 1)
    tree_arg = [-1] * (size + 1)

    def query(position: int):
        best, arg = 0.0, -1
        while position > 0:
            if tree_val[position] > best:
                best, arg = tree_val[position], tree_arg[position]
            position -= position & -position
        return best, arg

    def update(position: int, value: float, arg: int):
        while position <= size:
            if value > tree_val[position]:
                tree_val[position] = value
                tree_arg[position] = arg
            position += position & -position

    ordered = sorted(range(len(candidates)), key=lambda i: (candidates[i][0], candidates[i][1]))
    score = [0.0] * len(candidates)
    parent = [-1] * len(candidates)
    position = 0
    while position < len(ordered):
        group_end = position
        x = candidates[ordered[position]][0]
        while group_end < len(ordered) and candidates[ordered[group_end]][0] == x:
            group_end += 1
        group = ordered[position:group_end]
        for i in group:
            best, arg = query(rank[candidates[i][1]] - 1)
            score[i] = best + candidates[i][2]
            parent[i] = arg
        for i in group:
            update(rank[candidates[i][1]], score[i], i)
        position = group_end
    end = max(range(len(candidates)), key=lambda i: (score[i], -candidates[i][0], -candidates[i][1]))
    out = []
    while end >= 0:
        out.append(candidates[end])
        end = parent[end]
    return sorted(out)


class SettledError(ValueError):
    """A settled pair that contradicts the images."""


class Matcher:
    def __init__(self, proto: list, release: list, proto_entry: int, release_entry: int,
                 table_pairs: list | None = None):
        self.P = sorted(proto, key=lambda f: f.address)
        self.R = sorted(release, key=lambda f: f.address)
        self.p_by = {f.address: f for f in self.P}
        self.r_by = {f.address: f for f in self.R}
        self.p_index = {f.address: i for i, f in enumerate(self.P)}
        self.r_index = {f.address: i for i, f in enumerate(self.R)}
        self.p_entry = self._containing(self.P, proto_entry)
        self.r_entry = self._containing(self.R, release_entry)
        self.pairs: dict[int, Pair] = {}  # proto address -> pair
        self.r_paired: dict[int, int] = {}  # release address -> proto address
        self.r_by_key: dict[bytes, list] = defaultdict(list)
        self.p_by_key: dict[bytes, list] = defaultdict(list)
        for f in self.R:
            self.r_by_key[f.key].append(f)
        for f in self.P:
            self.p_by_key[f.key].append(f)
        self.p_callers = self._callers(self.P, self.p_by)
        self.r_callers = self._callers(self.R, self.r_by)
        self.p_referrers = self._referrers(self.P, self.p_by)
        self.r_referrers = self._referrers(self.R, self.r_by)
        self.stats: dict = defaultdict(int)
        self.table_pairs = list(table_pairs or [])  # (prototype Table, release Table)
        self.vt_confirmed: set[int] = set()  # prototype addresses whose pair a vtable slot confirms
        self.vt_slots: dict[int, list] = defaultdict(list)  # prototype address -> [(p table, r table, p off, r off)]
        self._resemblance: dict[tuple[int, int], float] = {}
        self._slot_refs: set[tuple[int, int]] = set()
        self._anchor_cache = None
        self.allow_reference_slots = False
        self._token_counts = None  # (prototype, release) targets of 1-to-1 reference slots
        self.blocked_p: set[int] = set()  # settled as removed
        self.blocked_r: set[int] = set()  # settled as new

    @staticmethod
    def _containing(functions, address):
        for f in functions:
            if f.address <= address < f.end:
                return f
        return None

    @staticmethod
    def _callers(functions, by):
        out = defaultdict(set)
        for f in functions:
            for _, target in f.calls:
                if target in by:
                    out[target].add(f.address)
        return out

    @staticmethod
    def _referrers(functions, by):
        """Functions that call, tail-call or load the address of each function (not itself)."""

        out = defaultdict(set)
        for f in functions:
            for _, target in f.references():
                if target in by and target != f.address:
                    out[target].add(f.address)
        return out

    def shares_unique_token(self, pair: Pair) -> bool:
        """The pair shares a string or (file, line) token no other function on either side uses."""

        if self._token_counts is None:
            counts_p, counts_r = Counter(), Counter()
            for f in self.P:
                counts_p.update(f.strings | f.lines)
            for f in self.R:
                counts_r.update(f.strings | f.lines)
            self._token_counts = (counts_p, counts_r)
        counts_p, counts_r = self._token_counts
        shared = (pair.p.strings | pair.p.lines) & (pair.r.strings | pair.r.lines)
        return any(counts_p[t] == 1 and counts_r[t] == 1 for t in shared)

    def agreeing_callers(self, pair: Pair) -> int:
        """Paired functions that reference the pair on both sides."""

        r_side = self.r_referrers.get(pair.r.address, set())
        return sum(1 for c in self.p_referrers.get(pair.p.address, ())
                   if c in self.pairs and self.pairs[c].r.address in r_side)

    # -- bookkeeping -------------------------------------------------------------
    def add(self, p, r, evidence: str) -> Pair | None:
        if p.address in self.pairs or r.address in self.r_paired:
            return None
        if p.address in self.blocked_p or r.address in self.blocked_r:
            return None
        pair = Pair(p, r, {evidence})
        if p.key == r.key:
            pair.similarity = pair.shape_similarity = pair.operation_similarity = 1.0
        else:
            pair.similarity = similarity(p.masked, r.masked)
            pair.shape_similarity = similarity(p.shape, r.shape)
            pair.operation_similarity = similarity(p.ops, r.ops)
        self.pairs[p.address] = pair
        self.r_paired[r.address] = p.address
        return pair

    def remove(self, pair: Pair) -> None:
        del self.pairs[pair.p.address]
        del self.r_paired[pair.r.address]

    # -- 0. settled by a checker ------------------------------------------------------
    def apply_settled(self, settled: list[tuple[int | None, int | None]]) -> None:
        """Pairs, new and removed functions settled by a checker; applied before any pairing.

        Each entry is (release address or None for removed, prototype address or None
        for new). An address that is not a function start of its image is an error.
        """

        for release, proto in settled:
            if release is not None and release not in self.r_by:
                raise SettledError("settled release address 0x%x is not a release function start" % release)
            if proto is not None and proto not in self.p_by:
                raise SettledError("settled prototype address 0x%x is not a prototype function start" % proto)
            if release is not None and proto is not None:
                if proto in self.pairs or release in self.r_paired:
                    raise SettledError("settled pair 0x%x/0x%x repeats an address" % (release, proto))
                self.add(self.p_by[proto], self.r_by[release], "settled")
            elif release is not None:
                self.blocked_r.add(release)
            elif proto is not None:
                self.blocked_p.add(proto)
        self.stats["settled"] = len(settled)

    # -- vtables --------------------------------------------------------------------
    def vtable_correspondences(self) -> list[tuple[int, int, tuple]]:
        """(prototype function, release function, place) for the slots of every paired table.

        A slot is placed by anchors: slots whose functions are already paired by
        other evidence (not by order alone among equal copies, not by a slot). A
        class's primary table starts with its bases' tables, so the anchors of every
        ancestor and descendant table count for a table too, inside its own length.
        The longest consistent set of anchors fixes the slots; between two anchors a
        run of equal length on both sides maps slot for slot; what is left over is an
        inserted (release) or dropped (prototype) virtual.
        """

        def reliable(t):
            pair = self.pairs.get(t)
            if pair is None or pair.evidence <= {"vtable-slot"}:
                return None
            if pair.p.key == pair.r.key and (len(self.p_by_key[pair.p.key]) > 1 or len(self.r_by_key[pair.r.key]) > 1) \
                    and not pair.evidence & {"settled", "call", "exact-caller"}:
                return None
            return pair.r.address

        own: dict[str, set] = {}
        primary = {}
        for pt, rt in self.table_pairs:
            if pt.offset or rt.offset:
                continue
            primary[pt.name] = (pt, rt)
            where_r = defaultdict(list)
            for j, t in enumerate(rt.slots):
                where_r[t].append(j)
            anchors = set()
            for i, t in enumerate(pt.slots):
                partner = reliable(t)
                if partner is not None and len(where_r.get(partner, ())) == 1:
                    anchors.add((i, where_r[partner][0]))
            own[pt.name] = anchors
        related = defaultdict(set)  # class -> ancestors and descendants with primary tables
        for name, (pt, _) in primary.items():
            for base in pt.bases:
                if base in primary:
                    related[name].add(base)
                    related[base].add(name)
        # families: classes joined by inheritance share slot numbers
        family = {}
        for name in sorted(primary):
            if name in family:
                continue
            stack = [name]
            while stack:
                current = stack.pop()
                if current in family:
                    continue
                family[current] = name
                stack.extend(sorted(related[current]))

        def chain_of(pt, rt):
            a, b = pt.slots, rt.slots
            if pt.offset or rt.offset or pt.name not in own:
                anchors = set()
                where_r = defaultdict(list)
                for j, t in enumerate(b):
                    where_r[t].append(j)
                for i, t in enumerate(a):
                    partner = reliable(t)
                    if partner is not None and len(where_r.get(partner, ())) == 1:
                        anchors.add((i, where_r[partner][0]))
            else:
                anchors = set(own[pt.name])
                for other in related[pt.name]:
                    anchors.update((i, j) for i, j in own[other] if i < len(a) and j < len(b))
            return sorted(increasing_subsequence(sorted(anchors)))

        def gaps(chain, a, b):
            previous = (-1, -1)
            for i, j in chain + [(len(a), len(b))]:
                yield list(range(previous[0] + 1, i)), list(range(previous[1] + 1, j)), (i, j)
                previous = (i, j)

        chains = {}
        known_inserted = defaultdict(set)  # family -> release slot numbers that are new virtuals
        known_dropped = defaultdict(set)  # family -> prototype slot numbers that are gone
        for pt, rt in self.table_pairs:
            chain = chains[(pt.address, rt.address)] = chain_of(pt, rt)
            fam = family.get(pt.name) if not (pt.offset or rt.offset) else None
            if fam is None:
                continue
            for gap_a, gap_b, _ in gaps(chain, pt.slots, rt.slots):
                if gap_b and not gap_a:
                    known_inserted[fam].update(gap_b)
                if gap_a and not gap_b:
                    known_dropped[fam].update(gap_a)
        out = []
        inserted = dropped = 0
        for pt, rt in self.table_pairs:
            a, b = pt.slots, rt.slots
            chain = chains[(pt.address, rt.address)]
            fam = family.get(pt.name) if not (pt.offset or rt.offset) else None
            if len(a) == len(b) and all(i == j for i, j in chain):
                places = list(zip(range(len(a)), range(len(b))))
            else:
                places = []
                for gap_a, gap_b, (i, j) in gaps(chain, a, b):
                    if len(gap_a) != len(gap_b) and fam is not None:
                        # a slot another table of the family shows as added (or dropped) is one here too
                        trimmed_b = [y for y in gap_b if y not in known_inserted[fam]]
                        trimmed_a = [x for x in gap_a if x not in known_dropped[fam]]
                        if len(trimmed_a) == len(trimmed_b):
                            inserted += len(gap_b) - len(trimmed_b)
                            dropped += len(gap_a) - len(trimmed_a)
                            gap_a, gap_b = trimmed_a, trimmed_b
                    if len(gap_a) == len(gap_b):
                        places.extend(zip(gap_a, gap_b))
                    else:
                        # what clearly resembles, in order; small or equal copies cannot be told apart
                        candidates = []
                        for x, ia in enumerate(gap_a):
                            for y, jb in enumerate(gap_b):
                                if a[ia] in self.p_by and b[jb] in self.r_by:
                                    pf, rf = self.p_by[a[ia]], self.r_by[b[jb]]
                                    if min(pf.size, rf.size) < VTABLE_RESEMBLE_SIZE:
                                        continue
                                    weight = self.callee_resemblance(a[ia], b[jb])
                                    if weight >= VTABLE_RESEMBLANCE:
                                        candidates.append((x, y, weight))
                        chosen = weighted_monotone_matching(candidates)
                        places.extend((gap_a[x], gap_b[y]) for x, y, _ in chosen)
                        dropped += len(gap_a) - len(chosen)
                        inserted += len(gap_b) - len(chosen)
                    if i < len(a):
                        places.append((i, j))
            for i, j in places:
                if a[i] in self.p_by and b[j] in self.r_by:
                    out.append((a[i], b[j], (pt, rt, 8 + 4 * i, 8 + 4 * j)))
        self.stats["vtable-slots-inserted"] = inserted
        self.stats["vtable-slots-dropped"] = dropped
        return out

    def vtable_pass(self, repair: bool) -> int:
        """Pair (or, with ``repair``, re-pair) functions that fill the same slot of paired tables."""

        correspondences = self.vtable_correspondences()
        votes_p: dict[int, Counter] = defaultdict(Counter)
        votes_r: dict[int, Counter] = defaultdict(Counter)
        places = defaultdict(list)
        for tp, tr, place in correspondences:
            votes_p[tp][tr] += 1
            votes_r[tr][tp] += 1
            places[tp].append(place)
        self.vt_slots = places

        def winner(votes: Counter):
            # the place most tables agree on; a minority is a class that overrides it differently
            ranked = votes.most_common()
            if len(ranked) == 1 or ranked[0][1] > sum(c for _, c in ranked[1:]):
                return ranked[0][0]
            return None

        changed = 0
        for tp in sorted(votes_p):
            tr = winner(votes_p[tp])
            if tr is None or winner(votes_r[tr]) != tp:
                self.stats["vtable-slot-disagreements"] += 1
                continue
            current = self.pairs.get(tp)
            if current is not None and current.r.address == tr:
                self.vt_confirmed.add(tp)
                continue
            if tp in self.blocked_p or tr in self.blocked_r:
                continue
            other_p = self.r_paired.get(tr)
            other = self.pairs.get(other_p) if other_p is not None else None
            if current is not None or other is not None:
                if not repair:
                    continue
                if any(x is not None and x.evidence & VTABLE_KEEPS for x in (current, other)):
                    self.stats["vtable-slot-conflicts-kept"] += 1
                    continue
                for x in (current, other):
                    if x is not None:
                        if x.p.key == x.r.key:
                            self.stats["vtable-reassigned-exact"] += 1
                        self.remove(x)
                pair = self.add(self.p_by[tp], self.r_by[tr], "vtable-slot")
                if pair:
                    pair.flags.add("repaired")
                    self.stats["vtable-reassigned"] += 1
                    self.vt_confirmed.add(tp)
                    changed += 1
                continue
            if self.add(self.p_by[tp], self.r_by[tr], "vtable-slot"):
                self.stats["vtable-created"] += 1
                self.vt_confirmed.add(tp)
                changed += 1
        return changed

    # -- 1. exact ------------------------------------------------------------------
    def exact_unique(self) -> None:
        for key, ps in sorted(self.p_by_key.items(), key=lambda kv: kv[1][0].address):
            rs = self.r_by_key.get(key, [])
            if len(ps) == 1 and len(rs) == 1:
                self.add(ps[0], rs[0], "exact")
        if self.p_entry and self.r_entry:
            self.add(self.p_entry, self.r_entry, "entry")

    # -- 2. call tree ----------------------------------------------------------------
    def call_correspondences(self, pair: Pair) -> list[tuple[int, int]]:
        """(prototype target, release target) for the references of a pair.

        References are calls, tail calls and loaded code addresses (function
        pointers), in instruction order. An exact pair maps them position for
        position. Any other pair aligns the two ordered lists: targets already
        paired with each other (and self-references) anchor the alignment, and
        between two anchors, runs of equal length are mapped one for one.
        """

        p, r = pair.p, pair.r
        pr = [(i, t, k) for i, t, k in p.typed_references() if t in self.p_by]
        rr = [(i, t, k) for i, t, k in r.typed_references() if t in self.r_by]
        if p.key == r.key:
            rd = {i: t for i, t, _ in rr}
            return [(t, rd[i]) for i, t, _ in pr if i in rd]
        return self.align_references([t for _, t, _ in pr], [t for _, t, _ in rr], p.address, r.address,
                                     [k for _, _, k in pr], [k for _, _, k in rr])

    def align_references(self, a: list[int], b: list[int], pa: int, ra: int,
                         kinds_a: list[str] | None = None, kinds_b: list[str] | None = None) -> list[tuple[int, int]]:
        """Align two ordered reference lists; a call only meets a call, a function pointer a pointer."""

        kinds_a = kinds_a or ["call"] * len(a)
        kinds_b = kinds_b or ["call"] * len(b)

        def token_p(target, kind):
            if target == pa:
                return ("self", kind)
            pair = self.pairs.get(target)
            return ("r", pair.r.address, kind) if pair else ("p", target, kind)

        def token_r(target, kind):
            return ("self", kind) if target == ra else ("r", target, kind)

        ta = [token_p(t, k) for t, k in zip(a, kinds_a)]
        tb = [token_r(t, k) for t, k in zip(b, kinds_b)]

        def one_sided(blocks) -> int:
            gaps = 0
            ia = ib = 0
            for i, j, size in blocks:
                open_a = any(ta[x][0] == "p" for x in range(ia, i))
                open_b = any(b[y] not in self.r_paired and b[y] != ra for y in range(ib, j))
                gaps += open_a != open_b
                ia, ib = i + size, j + size
            return gaps

        plain = [(x.a, x.b, x.size) for x in SequenceMatcher(None, ta, tb, autojunk=False).get_matching_blocks()]
        unique = patience_blocks(ta, tb)
        # the alignment that leaves fewer one-sided gaps (an open target with nothing opposite),
        # then the one that matches more targets
        chosen = min((plain, unique), key=lambda blocks: (one_sided(blocks), -sum(x[2] for x in blocks)))
        out = []
        ia = ib = 0
        for block in chosen:
            for kind in ("call", "ptr"):
                gap_a = [x for x in range(ia, block[0]) if kinds_a[x] == kind]
                gap_b = [y for y in range(ib, block[1]) if kinds_b[y] == kind]
                open_a = [x for x in gap_a if ta[x][0] == "p"]
                open_b = [y for y in gap_b if b[y] not in self.r_paired and b[y] != ra]
                if len({a[x] for x in open_a}) == 1 and len({b[y] for y in open_b}) == 1:
                    # one unpaired target of this kind on each side between the same two anchors
                    out.append((a[open_a[0]], b[open_b[0]]))
                    self._slot_refs.add((a[open_a[0]], b[open_b[0]]))
                elif gap_a and gap_b:
                    # between anchors: map the unpaired targets that resemble each other, in order
                    # (also for runs of equal length: a changed caller may call other functions)
                    candidates = []
                    for i, x in enumerate(gap_a):
                        if ta[x][0] != "p":
                            continue
                        for j, y in enumerate(gap_b):
                            if b[y] in self.r_paired or b[y] == ra:
                                continue
                            weight = self.callee_resemblance(a[x], b[y])
                            if weight:
                                candidates.append((i, j, weight))
                    for i, j, _ in weighted_monotone_matching(candidates):
                        out.append((a[gap_a[i]], b[gap_b[j]]))
            out.extend((a[block[0] + k], b[block[1] + k]) for k in range(block[2]))
            ia, ib = block[0] + block[2], block[1] + block[2]
        return out

    def callee_resemblance(self, pa: int, ra: int) -> float:
        """Weight of a callee candidate inside an unequal run of a paired caller; 0 when unlike."""

        key = (pa, ra)
        cached = self._resemblance.get(key)
        if cached is not None:
            return cached
        p, r = self.p_by[pa], self.r_by[ra]
        small, large = sorted((p.size, r.size))
        value = 0.0
        if large and small / large >= SIZE_RATIO_MIN:
            masked = similarity(p.masked, r.masked)
            operations = similarity(p.ops, r.ops)
            if masked >= CALLEE_SIMILARITY or operations >= CALLEE_OPERATIONS:
                value = max(masked, 0.8 * operations)
        self._resemblance[key] = value
        return value

    def propagate(self) -> int:
        """Pairs implied by the calls of current pairs, entry point first; returns how many were added."""

        added_total = 0
        while True:
            votes: dict[int, dict[int, set]] = defaultdict(lambda: defaultdict(set))
            order = self._bfs_order()
            for pair in order:
                for tp, tr in self.call_correspondences(pair):
                    if tp in self.p_by and tr in self.r_by:
                        votes[tp][tr].add(pair.p.address)
            claimed = defaultdict(set)
            for tp, choices in votes.items():
                if tp not in self.pairs:
                    for tr in choices:
                        claimed[tr].add(tp)
            def exact_parent(voters):
                return any(v in self.pairs and self.pairs[v].p.key == self.pairs[v].r.key for v in voters)

            added = 0
            for tp in sorted(votes):
                choices = votes[tp]
                if tp in self.pairs:
                    continue
                free = {tr: voters for tr, voters in choices.items() if tr not in self.r_paired}
                if not free:
                    continue
                tr = self._majority(free)
                if tr is None:
                    self.stats["call-vote-disagreements"] += 1
                    continue
                voters = free[tr]
                # the release callee must not be claimed as strongly by another prototype callee
                rivals = {other: votes[other][tr] for other in claimed[tr]}
                if len(rivals) > 1 and self._majority(rivals) != tp:
                    self.stats["call-vote-rivals"] += 1
                    continue
                p_fn, r_fn = self.p_by[tp], self.r_by[tr]
                if p_fn.key == r_fn.key and not exact_parent(voters):
                    open_copies = [f for f in self.p_by_key[p_fn.key] if f.address not in self.pairs]
                    if len(open_copies) > 1:
                        continue  # several equal copies still open: position decides, not a changed caller
                exact_voter = any(self.pairs[v].p.key == self.pairs[v].r.key for v in voters if v in self.pairs)
                if (tp, tr) in self._slot_refs and not exact_voter and self.callee_resemblance(tp, tr) == 0:
                    if not self.allow_reference_slots:
                        continue  # later: positional and global pairs come first
                    small, large = sorted((p_fn.size, r_fn.size))
                    if small / large < SLOT_SIZE_RATIO or not self.in_window(p_fn, r_fn):
                        self.stats["slot-rejected-shape-or-order"] += 1
                        continue
                    if not self.slot_plausible(p_fn, r_fn):
                        self.stats["slot-rejected-callers"] += 1
                        continue
                    evidence = "slot-only"  # only the 1-to-1 place in a caller's references
                else:
                    evidence = "call" if exact_voter else "call-deviating"
                pair = self.add(self.p_by[tp], self.r_by[tr], evidence)
                if pair:
                    added += 1
            added_total += added
            if not added:
                return added_total

    def _majority(self, options: dict) -> object:
        """The option whose voters outnumber all other voters together, exact-pair voters first."""

        def exact_count(voters):
            return sum(1 for v in voters if v in self.pairs and self.pairs[v].p.key == self.pairs[v].r.key)

        for count in (exact_count, len):
            ranked = sorted(options, key=lambda k: (-count(options[k]), k))
            best = ranked[0]
            rest = sum(count(options[k]) for k in ranked[1:])
            if count(options[best]) > rest:
                return best
            if count is exact_count and count(options[best]) and rest:
                return None  # exact callers disagree
        return None

    def _bfs_order(self) -> list[Pair]:
        """Pairs in breadth-first call-tree order from the entry pair, then the rest by address."""

        seen = set()
        out = []
        queue = []
        if self.p_entry and self.p_entry.address in self.pairs:
            queue.append(self.p_entry.address)
            seen.add(self.p_entry.address)
        while queue:
            nxt = []
            for address in queue:
                out.append(self.pairs[address])
                for _, target in self.p_by[address].calls:
                    if target in self.pairs and target not in seen:
                        seen.add(target)
                        nxt.append(target)
            queue = nxt
        for address in sorted(self.pairs):
            if address not in seen:
                out.append(self.pairs[address])
        return out

    # -- order anchors -------------------------------------------------------------
    def anchors(self) -> list[Pair]:
        points = [(self.p_index[a], self.r_index[pr.r.address]) for a, pr in self.pairs.items()]
        keep = increasing_subsequence(points)
        out = [self.pairs[self.P[i].address] for i, _ in sorted(keep)]
        return out

    def _window(self, anchors_p: list[int], anchors_r: list[int], p_position: int) -> tuple[int, int]:
        k = bisect.bisect_left(anchors_p, p_position)
        lo = anchors_r[k - 1] if k > 0 else -1
        hi = anchors_r[k] if k < len(anchors_p) else len(self.R)
        return lo, hi

    # -- 3. many-times-found ---------------------------------------------------------
    def resolve_duplicates(self) -> int:
        added = 0
        anchors = self.anchors()
        anchors_p = [self.p_index[a.p.address] for a in anchors]
        anchors_r = [self.r_index[a.r.address] for a in anchors]
        for f in self.P:
            if f.address in self.pairs:
                continue
            candidates = [r for r in self.r_by_key.get(f.key, []) if r.address not in self.r_paired]
            if not candidates:
                continue
            lo, hi = self._window(anchors_p, anchors_r, self.p_index[f.address])
            inside = [r for r in candidates if lo < self.r_index[r.address] < hi]
            if len(inside) == 1:
                rivals = [p for p in self.p_by_key[f.key] if p.address not in self.pairs and p is not f
                          and self._window(anchors_p, anchors_r, self.p_index[p.address]) == (lo, hi)]
                if not rivals:
                    if self.add(f, inside[0], "exact-position"):
                        added += 1
                    continue
            # by callers: paired prototype callers whose release partners call the candidate
            scores = []
            for r in candidates:
                score = 0
                for caller in self.p_callers.get(f.address, ()):
                    pair = self.pairs.get(caller)
                    if pair and pair.r.address in self.r_callers.get(r.address, ()):
                        score += 1
                scores.append((score, r))
            scores.sort(key=lambda x: (-x[0], x[1].address))
            if scores and scores[0][0] > 0 and (len(scores) == 1 or scores[1][0] < scores[0][0]):
                if self.add(f, scores[0][1], "exact-caller"):
                    added += 1
        return added

    # -- 4. positional --------------------------------------------------------------
    def _score(self, p, r, prefilter: bool = True) -> float | None:
        small, large = sorted((p.size, r.size))
        if large and small / large < SIZE_RATIO_MIN:
            return None
        if prefilter and jaccard(p.grams, r.grams) < GRAM_PREFILTER:
            # a small function's 3-grams say little: a high operation similarity may stand in
            if max(p.size, r.size) > SMALL_FUNCTION or similarity(p.ops, r.ops) < SMALL_OPERATIONS:
                return None
        value = similarity(p.masked, r.masked)
        if p.strings and r.strings:
            value = max(value, 0.5 * value + 0.5 * jaccard(p.strings, r.strings))
        if value >= UNSURE_MIN:
            return value
        # rewritten code keeps its operations even when registers and offsets change:
        # such a candidate may still be proposed, as an unsure pair with a low weight
        if min(p.size, r.size) >= 64 and similarity(p.ops, r.ops) >= STRONG_OPERATIONS:
            return max(value, 0.05)
        return None

    def positional(self) -> int:
        anchors = self.anchors()
        cuts = [(-1, -1)] + [(self.p_index[a.p.address], self.r_index[a.r.address]) for a in anchors]
        cuts.append((len(self.P), len(self.R)))
        added = 0
        for (p0, r0), (p1, r1) in zip(cuts, cuts[1:]):
            ps = [f for f in self.P[p0 + 1:p1] if f.address not in self.pairs]
            rs = [f for f in self.R[r0 + 1:r1] if f.address not in self.r_paired]
            if not ps or not rs:
                continue
            candidates = []
            # a small gap is cheap to score in full: no 3-gram prefilter there
            prefilter = len(ps) * len(rs) > SMALL_GAP
            for i, p in enumerate(ps):
                centre = i * len(rs) / len(ps)
                lo = max(0, int(centre) - BAND)
                hi = min(len(rs), int(centre) + BAND + 1)
                for j in range(lo, hi):
                    value = self._score(p, rs[j], prefilter)
                    if value is not None:
                        candidates.append((i, j, value))
            chosen = weighted_monotone_matching(candidates)
            used_i = {i for i, _, _ in chosen}
            used_j = {j for _, j, _ in chosen}
            for i, j, value in chosen:
                pair = self.add(ps[i], rs[j], "position")
                if pair is None:
                    continue
                added += 1
                # an alternative left unpaired that scores as well: order did not settle it
                for i2, j2, v2 in candidates:
                    if v2 >= value - AMBIGUITY and ((i2 == i and j2 != j and j2 not in used_j)
                                                    or (j2 == j and i2 != i and i2 not in used_i)):
                        pair.flags.add("ambiguous")
                        break
        return added

    def null_distribution(self, limit: int = 4000, min_size: int = 0) -> list[float]:
        """Similarity of functions against their pair's release neighbours (not their pair)."""

        out = []
        for address in sorted(self.pairs):
            pair = self.pairs[address]
            if ("position" not in pair.evidence and "call" not in pair.evidence) or pair.p.size < min_size:
                continue
            j = self.r_index[pair.r.address]
            for other in (j - 2, j + 2):
                if 0 <= other < len(self.R):
                    r = self.R[other]
                    small, large = sorted((pair.p.size, r.size))
                    if large and small / large >= SIZE_RATIO_MIN and min(pair.p.size, r.size) >= min_size:
                        out.append(similarity(pair.p.masked, r.masked))
            if len(out) >= limit:
                break
        return out

    def callers_agree(self, pa: int, ra: int, small: bool = False) -> bool:
        """A look-alike found anywhere must share a paired caller when both sides have paired callers."""

        p_callers = self.p_callers.get(pa, set())
        r_callers = self.r_callers.get(ra, set())
        mapped = {self.pairs[c].r.address for c in p_callers if c in self.pairs}
        r_paired_callers = {c for c in r_callers if c in self.r_paired}
        if mapped and r_paired_callers:
            return bool(mapped & r_callers)
        if small:
            # a small look-alike needs its callers to agree; one side's paired callers alone do not
            return not mapped and not r_paired_callers
        return True  # nothing to contradict the match

    # -- 4c. moved functions -----------------------------------------------------------
    def global_leftovers(self, min_size: int = 64, prefilter: float = 0.30) -> int:
        """Mutual best matches among the remaining functions anywhere in the image (moved code)."""

        ps = [f for f in self.P if f.address not in self.pairs and f.size >= min_size]
        rs = [f for f in self.R if f.address not in self.r_paired and f.size >= min_size]
        anchors = self.anchors()
        anchors_p = [self.p_index[a.p.address] for a in anchors]
        anchors_r = [self.r_index[a.r.address] for a in anchors]
        scores: dict[tuple[int, int], float] = {}
        similarities: dict[tuple[int, int], float] = {}
        slotted: set[tuple[int, int]] = set()
        for p in ps:
            lo, hi = self._window(anchors_p, anchors_r, self.p_index[p.address])
            for r in rs:
                small, large = sorted((p.size, r.size))
                if small / large < 0.5 or jaccard(p.grams, r.grams) < prefilter:
                    continue
                value = similarity(p.masked, r.masked)
                if value >= UNSURE_MIN:
                    similarities[(p.address, r.address)] = value
                    # a candidate in the prototype function's own slot is preferred
                    in_slot = lo < self.r_index[r.address] < hi
                    if in_slot:
                        slotted.add((p.address, r.address))
                    scores[(p.address, r.address)] = value + (GLOBAL_SLOT_BONUS if in_slot else 0)
        best_p: dict[int, list] = defaultdict(list)
        best_r: dict[int, list] = defaultdict(list)
        for (pa, ra), value in scores.items():
            best_p[pa].append((value, ra))
            best_r[ra].append((value, pa))
        added = 0
        for (pa, ra), value in sorted(scores.items()):
            top_p = sorted(best_p[pa], key=lambda x: (-x[0], x[1]))
            top_r = sorted(best_r[ra], key=lambda x: (-x[0], x[1]))
            if top_p[0][1] != ra or top_r[0][1] != pa:
                continue
            p_fn, r_fn = self.p_by[pa], self.r_by[ra]
            same_shape = p_fn.size == r_fn.size and p_fn.shape == r_fn.shape
            small = p_fn.size < GLOBAL_SMALL and (pa, ra) not in slotted and not same_shape
            if not self.callers_agree(pa, ra, small):
                self.stats["global-rejected-callers"] += 1
                continue
            pair = self.add(self.p_by[pa], self.r_by[ra], "global")
            if pair is None:
                continue
            added += 1
            runner_up = [v for v, _ in top_p[1:2] + top_r[1:2]]
            if runner_up and max(runner_up) >= value - AMBIGUITY:
                pair.flags.add("ambiguous")
        return added

    # -- 4d. one-to-one slots ------------------------------------------------------------
    def slot_plausible(self, p, r) -> bool:
        """A slot pair must not contradict its callers: paired callers on both sides lie together."""

        p_callers = self.p_callers.get(p.address, set())
        r_callers = self.r_callers.get(r.address, set())
        mapped = [self.r_paired[c] for c in r_callers if c in self.r_paired]
        if not p_callers or not mapped:
            return True
        return any(abs(m - c) <= SLOT_CALLER_DISTANCE for m in mapped for c in p_callers)

    def in_window(self, p, r) -> bool:
        """The release function lies between the release partners of the prototype function's anchors."""

        anchors = self._anchor_cache
        if anchors is None or anchors[0] != len(self.pairs):
            current = self.anchors()
            anchors = (len(self.pairs), [self.p_index[a.p.address] for a in current],
                       [self.r_index[a.r.address] for a in current])
            self._anchor_cache = anchors
        lo, hi = self._window(anchors[1], anchors[2], self.p_index[p.address])
        return lo < self.r_index[r.address] < hi

    def address_slots(self) -> int:
        """Pair the single unpaired function on each side between two consecutive order anchors."""

        anchors = self.anchors()
        cuts = [(self.p_index[a.p.address], self.r_index[a.r.address]) for a in anchors]
        added = 0
        for (p0, r0), (p1, r1) in zip(cuts, cuts[1:]):
            ps = [f for f in self.P[p0 + 1:p1] if f.address not in self.pairs]
            rs = [f for f in self.R[r0 + 1:r1] if f.address not in self.r_paired]
            if len(ps) != 1 or len(rs) != 1:
                continue
            p, r = ps[0], rs[0]
            if p.address in self.blocked_p or r.address in self.blocked_r:
                continue
            small, large = sorted((p.size, r.size))
            if small / large < SLOT_SIZE_RATIO or similarity(p.ops, r.ops) < SLOT_OPERATIONS:
                self.stats["slot-rejected-shape"] += 1
                continue
            if not self.slot_plausible(p, r):
                self.stats["slot-rejected-callers"] += 1
                continue
            if self.add(p, r, "slot-only"):
                added += 1
        return added

    # -- 4b. strings anywhere ---------------------------------------------------------
    def by_strings(self) -> int:
        """Pairs from strings and (file, line) tokens that exactly one function on each side uses.

        Uniqueness is counted over all functions, paired or not; file-name strings
        alone are not identity evidence (many functions pass the same __FILE__).
        """

        p_owner = defaultdict(list)
        r_owner = defaultdict(list)
        for f in self.P:
            for token in f.strings | f.lines:
                p_owner[token].append(f)
        for f in self.R:
            for token in f.strings | f.lines:
                r_owner[token].append(f)
        votes = defaultdict(int)
        for token in sorted(p_owner, key=repr):
            if len(p_owner[token]) == 1 and len(r_owner.get(token, ())) == 1:
                p, r = p_owner[token][0], r_owner[token][0]
                if (p.address not in self.pairs and r.address not in self.r_paired
                        and p.address not in self.blocked_p and r.address not in self.blocked_r):
                    votes[(p.address, r.address)] += 1
        added = 0
        by_p = defaultdict(list)
        by_r = defaultdict(list)
        for (pa, ra) in votes:
            by_p[pa].append(ra)
            by_r[ra].append(pa)
        for (pa, ra) in sorted(votes):
            if len(by_p[pa]) == 1 and len(by_r[ra]) == 1:
                if self.add(self.p_by[pa], self.r_by[ra], "string"):
                    added += 1
        return added

    # -- call-tree authority -----------------------------------------------------------
    def repair_from_exact_calls(self) -> int:
        """Re-pair callees that exact parents unanimously reference, over weaker pairs."""

        votes: dict[int, set] = defaultdict(set)
        for pair in list(self.pairs.values()):
            if pair.p.key != pair.r.key:
                continue
            for tp, tr in self.call_correspondences(pair):
                if tp in self.p_by and tr in self.r_by:
                    votes[tp].add(tr)
        claimed: dict[int, set] = defaultdict(set)
        for tp, trs in votes.items():
            for tr in trs:
                claimed[tr].add(tp)
        changed = 0
        for tp in sorted(votes):
            if len(votes[tp]) != 1:
                continue
            (tr,) = votes[tp]
            if len(claimed[tr]) != 1:
                continue
            current = self.pairs.get(tp)
            if current is not None and current.r.address == tr:
                continue
            if tp in self.blocked_p or tr in self.blocked_r:
                continue
            other_p = self.r_paired.get(tr)
            other = self.pairs.get(other_p) if other_p is not None else None
            if any(x is not None and x.evidence & {"exact", "entry", "settled"} for x in (current, other)):
                continue  # never break a unique exact, entry or settled pair
            for x in (current, other):
                if x is not None:
                    self.remove(x)
            pair = self.add(self.p_by[tp], self.r_by[tr], "call")
            if pair:
                pair.flags.add("repaired")
                changed += 1
        return changed

    # -- consistency -------------------------------------------------------------------
    def check(self) -> None:
        for pair in self.pairs.values():
            pair.call_sites = 0
        for pair in self.pairs.values():
            pair.call_consistent = 0
            pair.call_conflicts = []
            for tp, tr in self.call_correspondences(pair):
                other = self.pairs.get(tp)
                if other is None:
                    if tr in self.r_paired:
                        pair.call_conflicts.append((tp, tr))
                    continue
                if other.r.address == tr:
                    pair.call_consistent += 1
                    if other is not pair:
                        other.call_sites += 1
                else:
                    pair.call_conflicts.append((tp, tr))
            if pair.p.key == pair.r.key:
                pair.ref_mismatches = sum(1 for a, b in zip(pair.p.refs, pair.r.refs) if a[1] != b[1])
            elif len(pair.call_conflicts) <= pair.call_consistent:
                pair.call_conflicts = []  # aligned calls of a deviating pair: the majority decides

    # -- 5. classes -----------------------------------------------------------------------
    def classify(self) -> None:
        anchors = self.anchors()
        order = {a.p.address for a in anchors}
        # pairs alone between their two neighbouring anchors on both sides (a 1-to-1 slot)
        alone = set()
        for before, pair, after in zip(anchors, anchors[1:], anchors[2:]):
            if (self.p_index[after.p.address] - self.p_index[before.p.address] == 2
                    and self.r_index[after.r.address] - self.r_index[before.r.address] == 2):
                alone.add(pair.p.address)
        for pair in self.pairs.values():
            flags = pair.flags
            in_order = pair.p.address in order
            if not in_order:
                flags.add("moved")
            if pair.call_conflicts:
                flags.add("call-conflict")
            if pair.ref_mismatches:
                flags.add("ref-kind")
            exact = pair.p.key == pair.r.key
            if exact and (len(self.p_by_key[pair.p.key]) > 1 or len(self.r_by_key[pair.r.key]) > 1):
                decided = (pair.p.address in self.vt_confirmed or pair.evidence & {"settled", "call", "exact-caller"}
                           or self.agreeing_callers(pair) > 0)
                if not decided:
                    flags.add("identical-copy")  # equal bytes elsewhere: only order chose this copy
            if "settled" in pair.evidence or "vtable-slot" in pair.evidence:
                plain = exact and not pair.call_conflicts and not pair.ref_mismatches
                pair.cls = "exact" if plain else "deviating"
                continue
            if exact:
                if pair.ref_mismatches:
                    pair.cls = "unsure"
                elif pair.call_conflicts:
                    # equal bytes calling other functions: the callee was replaced. Sure only
                    # when the pair itself is in order (a copy found elsewhere could be another's).
                    pair.cls = "deviating" if in_order else "unsure"
                    flags.add("callee-changed")
                else:
                    pair.cls = "exact"
                continue
            if pair.p.size == pair.r.size and pair.shape_similarity == 1.0:
                flags.add("imm-only")
            strong = bool(pair.evidence & {"call", "entry", "string"}) or self.shares_unique_token(pair)
            agreeing = self.agreeing_callers(pair)
            called = bool(pair.evidence & {"call", "call-deviating"}) or pair.call_sites > 0 or agreeing > 0
            if pair.call_conflicts:
                # calls of a changed function lead elsewhere: callees replaced, not a contradiction
                flags.add("callee-changed")
            if "ambiguous" in flags:
                pair.cls = "unsure"
            elif "slot-only" in pair.evidence:
                pair.cls = "deviating"  # only the 1-to-1 place: weak, and said so by its evidence
            elif pair.similarity >= DEVIATING_MIN or "imm-only" in flags:
                pair.cls = "deviating"
            elif strong and (pair.similarity >= STRONG_SIMILARITY or pair.operation_similarity >= STRONG_OPERATIONS):
                pair.cls = "deviating"
            elif called and (in_order and (pair.operation_similarity >= CALL_SLOT_OPERATIONS
                                           or pair.p.address in alone or agreeing >= 2) or agreeing >= 3):
                # referenced at the place of the prototype function by a paired caller, in its slot
                pair.cls = "deviating"
                flags.add("call-and-slot")
            elif "call" in pair.evidence and in_order:
                # an exact caller references it at the same place: the same role, rewritten body;
                # the prototype's name may not carry over
                pair.cls = "deviating"
                flags.add("role-only")
            elif in_order and pair.p.address in alone:
                # alone between its two neighbouring anchors on both sides: the 1-to-1 slot is the evidence
                pair.cls = "deviating"
                pair.evidence.add("slot-only")
            else:
                pair.cls = "unsure"
                flags.add("low-similarity")

    def run(self, settled: list | None = None) -> None:
        self.apply_settled(settled or [])
        self.exact_unique()
        self.stats["exact-unique"] = len(self.pairs)
        for _ in range(8):
            added = self.propagate()
            added += self.resolve_duplicates()
            if not added:
                break
        if self.table_pairs:
            self.vtable_pass(repair=False)
            self.propagate()
        self.stats["after-exact-and-calls"] = len(self.pairs)
        for _ in range(4):
            added = self.positional()
            added += self.propagate()
            added += self.by_strings()
            added += self.resolve_duplicates()
            if not added:
                break
        added = self.global_leftovers()
        self.stats["global"] = added
        self.allow_reference_slots = True
        self.propagate()  # now the 1-to-1 reference slots may pair what order and resemblance left
        for _ in range(4):
            added = self.address_slots()
            self.stats["address-slots"] += added
            if not added:
                break
            self.propagate()
        for _ in range(3):
            if not self.table_pairs or not self.vtable_pass(repair=True):
                break
            self.propagate()
        for _ in range(4):
            repaired = self.repair_from_exact_calls()
            self.stats["repaired"] += repaired
            if not repaired:
                break
            self.propagate()
        self.stats["paired"] = len(self.pairs)
        self.check()
        self.classify()
