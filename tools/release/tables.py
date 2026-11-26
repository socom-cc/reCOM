"""Tables of named entries: arrays of fixed-size records in data holding a function pointer and a key.

The command tables of the animation and UI code are the known case: per entry a
name string, a handler and an id. A table is a run of at least MIN_ENTRIES
function pointers in data at a constant stride (8 to 32 bytes); its key is the
field at a fixed distance from the pointer that holds a string in every entry
(a string key), or else a small integer distinct across the entries (an id key).
Tables are paired by their key sets; entries with the same key pair their
handlers. A table with no key (state tables, callback tables) keys its entries
by position (kind ``index``); such tables pair later, through handlers already
paired by other evidence (see ``pairing.Matcher.index_table_correspondences``).
"""
from __future__ import annotations

import bisect
from collections import Counter
from dataclasses import dataclass, field

import mips

MIN_ENTRIES = 3
STRIDES = (8, 12, 16, 20, 24, 28, 32)
MAX_ID = 0x10000
STRING_PAIR_MIN = 0.5  # Jaccard of the string keys for two tables to pair
ID_PAIR_MIN = 0.8  # ... of the id keys (ids repeat across tables, so more is needed)


@dataclass
class EntryTable:
    address: int  # first pointer word
    stride: int
    kind: str  # "string" or "id"
    entries: list[tuple[object, int]] = field(default_factory=list)  # (key, handler)

    @property
    def keys(self) -> set:
        return {k for k, _ in self.entries}


def read_name(image, address: int) -> str | None:
    if not (image.base <= address < image.end):
        return None
    offset = address - image.base
    stop = image.data.find(b"\0", offset, offset + 128)
    if stop <= offset:
        return None
    chunk = image.data[offset:stop]
    if all(0x20 <= b < 0x7F for b in chunk):
        return chunk.decode("latin-1")
    return None


def find_tables(image, starts: set[int], spans: list[tuple[int, int]], skip: set[int] = frozenset()) -> list[EntryTable]:
    """Tables of one image; ``skip`` holds data words not to read as entries (vtable slots)."""

    words = mips.words_of(image.data)
    spans = sorted(spans)
    begins = [s for s, _ in spans]

    def in_code(address: int) -> bool:
        k = bisect.bisect_right(begins, address) - 1
        return k >= 0 and spans[k][0] <= address < spans[k][1]

    pointers = {}
    for index, value in enumerate(words):
        if value in starts:
            address = image.base + 4 * index
            if address not in skip and not in_code(address):
                pointers[address] = value
    used: set[int] = set()
    out = []
    for address in sorted(pointers):
        if address in used:
            continue
        for stride in STRIDES:
            run = [address]
            while run[-1] + stride in pointers:
                run.append(run[-1] + stride)
            if len(run) < MIN_ENTRIES:
                continue
            table = _keyed(image, words, run, stride, pointers)
            if table is None:
                table = EntryTable(run[0], stride, "index", [(k, pointers[a]) for k, a in enumerate(run)])
            out.append(table)
            used.update(run)
            break
    return out


def _keyed(image, words, run, stride, pointers):
    def word(address):
        index = (address - image.base) >> 2
        return words[index] if 0 <= index < len(words) else None

    best = None
    for delta in range(-stride + 4, stride, 4):
        if delta == 0:
            continue
        values = [word(a + delta) for a in run]
        if any(v is None for v in values):
            continue
        names = [read_name(image, v) for v in values]
        if all(names) and len(set(names)) == len(names):
            return EntryTable(run[0], stride, "string", [(n, pointers[a]) for n, a in zip(names, run)])
        if best is None and all(v < MAX_ID for v in values) and len(set(values)) == len(values):
            best = EntryTable(run[0], stride, "id", [(v, pointers[a]) for v, a in zip(values, run)])
    return best


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def pair_tables(proto: list[EntryTable], release: list[EntryTable]) -> list[tuple[EntryTable, EntryTable]]:
    """Mutual best pairs by key sets: string tables with string tables, id tables with id tables."""

    scores = {}
    for p in proto:
        for r in release:
            if p.kind != r.kind or p.kind == "index":
                continue
            value = jaccard(p.keys, r.keys)
            if value >= (STRING_PAIR_MIN if p.kind == "string" else ID_PAIR_MIN):
                scores[(p.address, r.address)] = value
    best_p, best_r = {}, {}
    for (pa, ra), value in scores.items():
        if value > best_p.get(pa, (0, 0))[0] or (value == best_p.get(pa, (0, 0))[0] and ra < best_p[pa][1]):
            best_p[pa] = (value, ra)
        if value > best_r.get(ra, (0, 0))[0] or (value == best_r.get(ra, (0, 0))[0] and pa < best_r[ra][1]):
            best_r[ra] = (value, pa)
    by_p = {t.address: t for t in proto}
    by_r = {t.address: t for t in release}
    out = []
    for pa, (_, ra) in sorted(best_p.items()):
        if best_r.get(ra, (0, None))[1] == pa:
            out.append((by_p[pa], by_r[ra]))
    return out


def entry_correspondences(pairs) -> list[tuple[int, int, tuple]]:
    """(prototype handler, release handler, (p table, r table, key)) for keys present once on each side."""

    out = []
    for p, r in pairs:
        count_p = Counter(k for k, _ in p.entries)
        count_r = Counter(k for k, _ in r.entries)
        release = {k: h for k, h in r.entries}
        for key, handler in p.entries:
            if count_p[key] == 1 and count_r.get(key) == 1:
                out.append((handler, release[key], (p, r, key)))
    return out
