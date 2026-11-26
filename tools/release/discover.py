"""Find functions in an image without symbols.

Starts come from: the entry point; ``jal`` targets in discovered code; frame
prologues that follow a call or exit (``addiu sp, sp, -N`` at an 8-aligned
address whose preceding instruction, after zero padding, ends a function or
calls one that never returns); code addresses built by ``lui``/``addiu`` in
discovered code and code pointers stored in data, when they land in a gap
between functions; runs of stored code pointers to code that calls known
functions or has a frame (static initialiser tables); starts supplied from
outside; and the linear sweep of the gaps between functions after the zero
padding the compiler leaves.

A function's extent is found by sweeping forward from its start: it ends after
the delay slot of an exit (``jr``, a ``j`` that leaves the function, an
unconditional backward branch) once no branch or jump-table entry seen so far
points beyond it, or at the next known start; trailing zero padding that is not
a delay slot is trimmed.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass, field

import mips

MAX_FUNCTION = 0x20000  # longest sweep accepted (bytes); the prototype's largest is 0x5f4c
NEAR_GAP = 0x10000  # a pointer into a gap at most this long between functions is accepted alone


@dataclass
class Found:
    start: int
    end: int  # exclusive: after the last delay slot
    evidence: set[str] = field(default_factory=set)
    calls: list[int] = field(default_factory=list)
    code_refs: list[int] = field(default_factory=list)
    tables: list[tuple[int, int]] = field(default_factory=list)  # (address, entries) of switch tables
    has_frame: bool = False
    ends_with_return: bool = False

    @property
    def size(self) -> int:
        return self.end - self.start


def is_frame_alloc(word: int) -> bool:
    return (word >> 16) == 0x27BD and bool(word & 0x8000)


ERET = 0x42000018


def ends_flow(word: int) -> bool:
    """An instruction after which the next instruction (beyond a delay slot) need not run."""

    return word == ERET or (mips.is_jal(word) or mips.is_jr(word) or mips.is_j(word) or mips.is_unconditional_branch(word)
            or ((word >> 26) == 0 and (word & 0x3F) in (0x09, 0x0C)))


class Discovery:
    def __init__(self, image, extra_starts: dict[int, str] | None = None):
        self.image = image
        self.words = mips.words_of(image.data)
        self.base = image.base
        self.limit = image.end
        self.starts: dict[int, set[str]] = {}
        self.rejected: dict[int, set[str]] = {}
        self.extra = dict(extra_starts or {})
        self.functions: list[Found] = []
        self._cache: dict = {}
        self._found: dict[int, Found] = {}
        self._table_at = 0
        self._pointer_runs: list[list[int]] = []
        self.prologues = self._prologue_starts()

    # -- words -------------------------------------------------------------------
    def word(self, address: int) -> int:
        return self.words[(address - self.base) >> 2]

    def inside(self, address: int) -> bool:
        return self.base <= address < self.limit and address % 4 == 0

    def _prologue_starts(self) -> set[int]:
        out = set()
        words = self.words
        for index in range(4, len(words)):
            if not is_frame_alloc(words[index]) or index % 2:
                continue
            k = index - 1
            while k > 0 and words[k] == 0 and index - k < 4:
                k -= 1
            # the last non-zero word is a delay slot after a call or exit, or itself a
            # call or exit whose delay slot is a nop, or a syscall
            if k >= 1 and (ends_flow(words[k - 1]) or (k < index - 1 and ends_flow(words[k])) or (words[k] & 0xFC00003F) == 0x0C):
                out.add(self.base + 4 * index)
        return out

    # -- one function ----------------------------------------------------------
    def _jump_table(self, pc: int, start: int, register: int) -> list[int]:
        """Targets of the switch table read into ``register`` just before ``jr register`` at ``pc``."""

        table = None
        bound = None
        load_base = None
        for back in range(1, 17):
            address = pc - 4 * back
            if address < start:
                break
            word = self.word(address)
            op = word >> 26
            if load_base is None and op == 0x23 and ((word >> 16) & 0x1F) == register:
                load_base = ((word >> 21) & 0x1F, mips.simm(word))
                continue
            if load_base and table is None and op == 0x0F and ((word >> 16) & 0x1F) == load_base[0]:
                table = ((word & 0xFFFF) << 16) + load_base[1]
            if op == 0x0B and bound is None:  # sltiu: the case count
                bound = word & 0xFFFF
        if table is None or not self.inside(table):
            return []
        out = []
        self._table_at = table
        count = bound if bound and bound < 4096 else 4096
        for index in range(count):
            entry_address = table + 4 * index
            if not self.inside(entry_address):
                break
            value = self.word(entry_address)
            if not (start <= value < start + MAX_FUNCTION and value % 4 == 0):
                break
            out.append(value)
        return out

    def sweep(self, start: int, stops) -> Found | None:
        """Extent of the function at ``start``; None when the bytes are not code."""

        if not self.inside(start) or self.word(start) == 0:
            return None
        reach = start
        pc = start
        calls: list[int] = []
        refs: list[int] = []
        tables: list[tuple[int, int]] = []
        hi: dict[int, int] = {}
        limit = min(self.limit, start + MAX_FUNCTION)
        nxt = stops(start)
        if nxt is not None:
            limit = min(limit, nxt)
        end = None
        while pc < limit:
            if pc != start and pc in self.prologues:
                end = pc
                break
            word = self.word(pc)
            if mips.is_invalid(word):
                return None
            op = word >> 26
            target = mips.branch_target(word, pc)
            if target is not None:
                if target > reach:
                    reach = target
                exit_ = mips.is_unconditional_branch(word) and target <= pc
            elif op == 3:
                calls.append(mips.jump_target(word, pc))
                exit_ = False
            elif op == 2:
                jt = mips.jump_target(word, pc)
                if start <= jt <= pc:
                    exit_ = True  # backward in-function jump: a loop end
                elif pc < jt < limit and jt - pc < 0x1000 and jt <= reach:
                    exit_ = False
                else:
                    exit_ = True  # tail call
            elif op == 0 and (word & 0x3F) == 0x0C and pc + 4 < limit and self.word(pc + 4) == 0:
                exit_ = False  # a syscall followed by padding never returns (_exit and the like)
                if pc + 4 > reach:
                    end = pc + 4
                    break
            elif mips.is_jr(word):
                rs = (word >> 21) & 0x1F
                if rs != mips.RA:
                    entries = self._jump_table(pc, start, rs)
                    if entries:
                        tables.append((self._table_at, len(entries)))
                    for value in entries:
                        if value > reach:
                            reach = value
                exit_ = True
            else:
                exit_ = False
                if op == 0x0F:
                    hi[(word >> 16) & 0x1F] = (word & 0xFFFF) << 16
                elif op == 0x09 and ((word >> 21) & 0x1F) in hi:
                    value = hi[(word >> 21) & 0x1F] + mips.simm(word)
                    if self.inside(value):
                        refs.append(value)
            if exit_ and pc + 8 > reach:
                end = min(pc + 8, limit)
                break
            pc += 4
        if end is None:
            if not (nxt is not None and pc >= nxt and pc == limit and reach <= limit):
                return None
            end = limit  # ran into the next known start
        # trailing zero words that are not a delay slot are padding
        while end - 8 >= start and self.word(end - 4) == 0 and not self._is_control(self.word(end - 8)):
            end -= 4
        if end <= start:
            return None
        last = self.word(end - 8) if end - 8 >= start else 0
        return Found(start, end, calls=calls, code_refs=refs, tables=tables,
                     has_frame=is_frame_alloc(self.word(start)) or is_frame_alloc(self.word(start + 4)),
                     ends_with_return=mips.is_jr(last) or mips.is_j(last))

    @staticmethod
    def _is_control(word: int) -> bool:
        return (mips.branch_target(word, 0) is not None or mips.is_jal(word) or mips.is_j(word)
                or mips.is_jr(word) or ((word >> 26) == 0 and (word & 0x3F) == 0x09))

    # -- whole image -----------------------------------------------------------
    def _next_start_fn(self):
        ordered = sorted(self.starts)

        def nxt(address: int):
            index = bisect.bisect_right(ordered, address)
            return ordered[index] if index < len(ordered) else None

        return nxt

    def _add(self, address: int, why: str) -> bool:
        if not self.inside(address):
            return False
        if address in self.starts:
            self.starts[address].add(why)
            return False
        if address in self.rejected:
            self.rejected[address].add(why)
            return False
        self.starts[address] = {why}
        return True

    def _closure(self) -> None:
        """Sweep every start; add the jal targets found; repeat until nothing new appears."""

        while True:
            nxt = self._next_start_fn()
            added = False
            bad = []
            found: dict[int, Found] = {}
            for start in sorted(self.starts):
                key = (start, nxt(start))
                if key not in self._cache:
                    self._cache[key] = self.sweep(start, nxt)
                result = self._cache[key]
                if result is None:
                    bad.append(start)
                    continue
                found[start] = result
                for target in result.calls:
                    added |= self._add(target, "call")
            for start in bad:
                evidence = self.starts.pop(start)
                if "entry" in evidence or "match" in evidence:
                    # keep authoritative starts even if the sweep fails: one-word extent
                    self.starts[start] = evidence
                    found[start] = Found(start, start + 4)
                else:
                    self.rejected.setdefault(start, set()).update(evidence)
                    added = True
            self._found = found
            # prologues inside found functions split them (no-return calls before them)
            for start, result in list(found.items()):
                for address in range(start + 8, result.end, 8):
                    if address in self.prologues:
                        added |= self._add(address, "prologue")
            if not added:
                return

    def _covering(self):
        spans = sorted((f.start, f.end) for f in self._found.values())
        starts = [s for s, _ in spans]

        def covered(address: int) -> bool:
            index = bisect.bisect_right(starts, address) - 1
            return index >= 0 and spans[index][0] <= address < spans[index][1]

        return spans, covered

    def _boundary_ok(self, address: int) -> bool:
        """The address follows padding or the delay slot of an exit."""

        if address - 4 < self.base:
            return True
        if self.word(address - 4) == 0 or address in self.prologues:
            return True
        return address - 8 >= self.base and ends_flow(self.word(address - 8))

    def _strong(self, result: Found) -> bool:
        """Code that cannot plausibly be data: it calls a known function or has a frame and returns."""

        if any(target in self._found for target in result.calls):
            return True
        return result.has_frame and result.ends_with_return

    def _pointer_candidates(self) -> list[tuple[int, str]]:
        """Near code addresses that are not yet starts; also collects runs of stored pointers."""

        spans, covered = self._covering()
        starts = [s for s, _ in spans]

        def near(address: int) -> bool:
            index = bisect.bisect_right(starts, address)
            if index == 0 or index >= len(spans):
                return False
            return spans[index][0] - spans[index - 1][1] <= NEAR_GAP

        table_words = set()
        for found in self._found.values():
            for table, count in found.tables:
                table_words.update(range(table, table + 4 * count, 4))
        candidates: dict[int, str] = {}
        for found in self._found.values():
            for ref in found.code_refs:
                if ref not in self._found and not covered(ref) and near(ref):
                    candidates.setdefault(ref, "code-ref")
        words = self.words
        base = self.base
        lo, hi = self.base, self.limit
        run: list[int] = []
        runs: list[list[int]] = []
        for index in range(len(words)):
            value = words[index]
            address = base + index * 4
            pointer = (lo <= value < hi and not value & 3 and address not in table_words
                       and not covered(address) and (value in self._found or not covered(value)))
            if pointer:
                run.append(value)
                if value not in self._found and near(value):
                    candidates.setdefault(value, "data-pointer")
                continue
            if len(run) >= 2:
                runs.append(run)
            run = []
        if len(run) >= 2:
            runs.append(run)
        self._pointer_runs = runs
        return sorted(candidates.items())

    def _accept(self, address: int, nxt, strong: bool) -> Found | None:
        if not self._boundary_ok(address):
            return None
        result = self.sweep(address, nxt)
        if result is None or not result.ends_with_return:
            return None
        if strong and not self._strong(result):
            return None
        return result

    def _table_candidates(self, nxt) -> list[int]:
        """Starts from runs of stored code pointers whose every target is strong code."""

        out = []
        for run in self._pointer_runs:
            fresh = sorted({v for v in run if v not in self._found})
            if not fresh:
                continue
            accepted = [v for v in fresh if self._accept(v, nxt, True)]
            if len(accepted) + (len(set(run)) - len(fresh)) >= 2:
                out.extend(accepted)
        return sorted(set(out))

    def _gap_fill(self) -> int:
        """Sweep gaps from their first non-zero word.

        A gap whose every non-zero word is a valid instruction is filled as far as
        the sweeps succeed; a gap holding invalid words (data follows) only while
        the functions found are strong code.
        """

        spans, _ = self._covering()
        added = 0
        bounds = list(zip([e for _, e in spans], [s for s, _ in spans[1:]] + [self.limit]))
        for e0, s1 in bounds:
            if s1 <= e0:
                continue
            clean = True
            for address in range(e0, s1, 4):
                if mips.is_invalid(self.word(address)):
                    clean = False
                    break
            address = e0
            while True:
                while address < s1 and self.word(address) == 0:
                    address += 4
                if address >= s1 or not self._boundary_ok(address):
                    break
                result = self.sweep(address, lambda _a, s1=s1: s1 if s1 < self.limit else None)
                if result is None or result.end > s1:
                    break
                if not clean and not (result.ends_with_return and self._strong(result)):
                    break
                added += self._add(address, "sweep")
                address = result.end
        return added

    def _fill_all(self) -> int:
        total = 0
        while True:
            filled = self._gap_fill()
            if not filled:
                return total
            total += filled
            self._closure()

    def run(self) -> list[Found]:
        self._add(self.image.entry, "entry")
        for address, why in sorted(self.extra.items()):
            self._add(address, why)
        self._closure()
        self._fill_all()
        tried: set[int] = set()
        for _ in range(64):
            added = 0
            nxt = self._next_start_fn()
            for address, why in self._pointer_candidates():
                if address in tried:
                    continue
                tried.add(address)
                if self._accept(address, nxt, False):
                    added += self._add(address, why)
            for address in self._table_candidates(nxt):
                added += self._add(address, "pointer-table")
            if added:
                self._closure()
            added += self._fill_all()
            if not added:
                break
        self.functions = []
        for start in sorted(self._found):
            found = self._found[start]
            found.evidence = set(self.starts[start])
            self.functions.append(found)
        return self.functions


def coverage(image, functions: list[Found], cluster_gap: int = NEAR_GAP) -> dict:
    """Code clusters, covered bytes, zero padding and unexplained gaps."""

    words = mips.words_of(image.data)
    spans = sorted((f.start, f.end) for f in functions)
    clusters = []
    current = None
    for start, end in spans:
        if current and start - current["end"] <= cluster_gap:
            current["gaps"].append((current["end"], start))
            current["end"] = max(current["end"], end)
            current["spans"].append((start, end))
        else:
            current = {"start": start, "end": end, "spans": [(start, end)], "gaps": []}
            clusters.append(current)
    out = []
    for cluster in clusters:
        covered = sum(e - s for s, e in cluster["spans"])
        padding = 0
        unexplained = []
        for g0, g1 in cluster["gaps"]:
            if g1 <= g0:
                continue
            nonzero = [a for a in range(g0, g1, 4) if words[(a - image.base) >> 2] != 0]
            padding += (g1 - g0) - 4 * len(nonzero)
            if nonzero:
                unexplained.append({"start": nonzero[0], "end": g1, "nonzero_bytes": 4 * len(nonzero)})
        out.append({
            "start": cluster["start"], "end": cluster["end"],
            "functions": len(cluster["spans"]), "covered": covered, "padding": padding,
            "unexplained": unexplained,
        })
    return {"clusters": out}
