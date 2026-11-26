"""Pair prototype and release functions and classify them.

Order of work:

1. exact: equal masked bytes (same size, same instructions, same layout) and the
   only such pair for that byte string;
2. call-tree propagation from every pair, starting at the entry point: the k-th
   call of an exact pair (calls of a deviating pair at aligned, equal
   instructions) leads to the callee pair; votes that disagree are conflicts;
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
from collections import defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher

# Thresholds (see COMPARISON.md for the distributions that justify them).
DEVIATING_MIN = 0.50  # a positional pair with this similarity is a deviating pair
UNSURE_MIN = 0.30  # below this a positional candidate is not a pair at all
STRONG_SIMILARITY = 0.30  # a pair with independent evidence (exact caller, strings) needs this similarity
STRONG_OPERATIONS = 0.70  # ... or this operation similarity
GRAM_PREFILTER = 0.15  # shape 3-gram Jaccard needed before computing a similarity
SIZE_RATIO_MIN = 0.25  # smaller/larger size ratio needed for a positional candidate
BAND = 64  # positional candidates: index distance allowed from the gap's diagonal
CALL_BLOCK = 4  # a call of a deviating pair counts only inside an equal block this long
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


class Matcher:
    def __init__(self, proto: list, release: list, proto_entry: int, release_entry: int):
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
        self.stats: dict = defaultdict(int)

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

    # -- bookkeeping -------------------------------------------------------------
    def add(self, p, r, evidence: str) -> Pair | None:
        if p.address in self.pairs or r.address in self.r_paired:
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
        p, r = pair.p, pair.r
        if p.key == r.key:
            return [(pc[1], rc[1]) for pc, rc in zip(p.calls, r.calls)]
        mapping = aligned_indices(p.masked, r.masked, CALL_BLOCK)
        r_calls = dict(r.calls)
        out = []
        for index, target in p.calls:
            other = mapping.get(index)
            if other is not None and other in r_calls:
                out.append((target, r_calls[other]))
        return out

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
            added = 0
            for tp in sorted(votes):
                choices = votes[tp]
                if tp in self.pairs:
                    continue
                if len(choices) != 1:
                    self.stats["call-vote-disagreements"] += 1
                    continue
                (tr, voters), = choices.items()
                if tr in self.r_paired:
                    continue
                # the release callee must not be claimed by another unpaired prototype callee
                if len(claimed[tr]) > 1:
                    self.stats["call-vote-rivals"] += 1
                    continue
                exact_voter = any(self.pairs[v].p.key == self.pairs[v].r.key for v in voters if v in self.pairs)
                pair = self.add(self.p_by[tp], self.r_by[tr], "call" if exact_voter else "call-deviating")
                if pair:
                    added += 1
            added_total += added
            if not added:
                return added_total

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
    def _score(self, p, r) -> float | None:
        small, large = sorted((p.size, r.size))
        if large and small / large < SIZE_RATIO_MIN:
            return None
        if jaccard(p.grams, r.grams) < GRAM_PREFILTER:
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
            for i, p in enumerate(ps):
                centre = i * len(rs) / len(ps)
                lo = max(0, int(centre) - BAND)
                hi = min(len(rs), int(centre) + BAND + 1)
                for j in range(lo, hi):
                    value = self._score(p, rs[j])
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

    # -- 4c. moved functions -----------------------------------------------------------
    def global_leftovers(self, min_size: int = 64, prefilter: float = 0.30) -> int:
        """Mutual best matches among the remaining functions anywhere in the image (moved code)."""

        ps = [f for f in self.P if f.address not in self.pairs and f.size >= min_size]
        rs = [f for f in self.R if f.address not in self.r_paired and f.size >= min_size]
        scores: dict[tuple[int, int], float] = {}
        for p in ps:
            for r in rs:
                small, large = sorted((p.size, r.size))
                if small / large < 0.5 or jaccard(p.grams, r.grams) < prefilter:
                    continue
                value = similarity(p.masked, r.masked)
                if value >= UNSURE_MIN:
                    scores[(p.address, r.address)] = value
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
            pair = self.add(self.p_by[pa], self.r_by[ra], "global")
            if pair is None:
                continue
            added += 1
            runner_up = [v for v, _ in top_p[1:2] + top_r[1:2]]
            if runner_up and max(runner_up) >= value - AMBIGUITY:
                pair.flags.add("ambiguous")
        return added

    # -- 4b. strings anywhere ---------------------------------------------------------
    def by_strings(self) -> int:
        p_owner = defaultdict(list)
        r_owner = defaultdict(list)
        for f in self.P:
            if f.address not in self.pairs:
                for s in f.strings:
                    p_owner[s].append(f)
        for f in self.R:
            if f.address not in self.r_paired:
                for s in f.strings:
                    r_owner[s].append(f)
        votes = defaultdict(int)
        for s in sorted(p_owner):
            if len(p_owner[s]) == 1 and len(r_owner.get(s, ())) == 1:
                votes[(p_owner[s][0].address, r_owner[s][0].address)] += 1
        added = 0
        by_p = defaultdict(list)
        by_r = defaultdict(list)
        for (pa, ra), n in votes.items():
            by_p[pa].append(ra)
            by_r[ra].append(pa)
        for (pa, ra), n in sorted(votes.items()):
            if len(by_p[pa]) == 1 and len(by_r[ra]) == 1:
                if self.add(self.p_by[pa], self.r_by[ra], "string"):
                    added += 1
        return added

    # -- call-tree authority -----------------------------------------------------------
    def repair_from_exact_calls(self) -> int:
        """Re-pair callees that exact parents unanimously call, over weaker pairs."""

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
            other_p = self.r_paired.get(tr)
            other = self.pairs.get(other_p) if other_p is not None else None
            if any(x is not None and x.evidence & {"exact", "entry"} for x in (current, other)):
                continue  # never break a unique exact pair
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
                else:
                    pair.call_conflicts.append((tp, tr))
            if pair.p.key == pair.r.key:
                pair.ref_mismatches = sum(1 for a, b in zip(pair.p.refs, pair.r.refs) if a[1] != b[1])
            elif len(pair.call_conflicts) <= pair.call_consistent:
                pair.call_conflicts = []  # aligned calls of a deviating pair: the majority decides

    # -- 5. classes -----------------------------------------------------------------------
    def classify(self) -> None:
        order = {(a.p.address) for a in self.anchors()}
        for pair in self.pairs.values():
            flags = pair.flags
            if pair.p.address not in order:
                flags.add("moved")
            if pair.call_conflicts:
                flags.add("call-conflict")
            if pair.ref_mismatches:
                flags.add("ref-kind")
            exact = pair.p.key == pair.r.key
            if exact:
                if pair.call_conflicts or pair.ref_mismatches:
                    pair.cls = "unsure"
                else:
                    pair.cls = "exact"
                continue
            if pair.p.size == pair.r.size and pair.shape_similarity == 1.0:
                flags.add("imm-only")
            strong = bool(pair.evidence & {"call", "entry", "string"})
            if pair.call_conflicts or "ambiguous" in flags:
                pair.cls = "unsure"
            elif pair.similarity >= DEVIATING_MIN or "imm-only" in flags:
                pair.cls = "deviating"
            elif strong and (pair.similarity >= STRONG_SIMILARITY or pair.operation_similarity >= STRONG_OPERATIONS):
                pair.cls = "deviating"
            else:
                pair.cls = "unsure"
                flags.add("low-similarity")

    def run(self) -> None:
        self.exact_unique()
        self.stats["exact-unique"] = len(self.pairs)
        for _ in range(8):
            added = self.propagate()
            added += self.resolve_duplicates()
            if not added:
                break
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
        if added:
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
