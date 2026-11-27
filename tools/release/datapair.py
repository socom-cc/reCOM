"""Pair the data objects of the release executable with the prototype's (stage 3, globals).

    python tools/release/datapair.py [--root <repo>] [--no-write] [--out DIR]

Reads ``support/socom.elf`` and ``support/SCUS_971.34`` (refusing any file whose
SHA-256 is not the pinned one), ``docs/release/function-map.tsv`` and the ``src/``
data annotations. Writes ``docs/release/data-map.tsv``, ``docs/release/DATA.md`` and
``build/release/data-map.json``. Standard library only; deterministic; nothing is
written to Ghidra and nothing is read from it.

A prototype data object is an OBJECT or NOTYPE symbol (aliases at one address grouped,
the largest size kept) outside the functions of the map. Evidence, strongest first:

* ``operand-exact``: a data address the instructions of an exact function pair compute
  at the same position (``lui``/``addiu``/``ori`` pairs, loads and stores through a high
  half, ``$gp`` offsets); one function pair is one witness;
* ``operand-aligned``: the same in a deviating pair, where the use and every instruction
  that built its address lie in aligned stretches: equal masked words in blocks of at
  least ``ALIGN_BLOCK``, the stretches between two such blocks (or a block and the
  function's start or end) when they have the same length and the same shapes, or the
  whole function for an ``imm-only`` pair;
* ``vtable``, ``named-table``: the tables the function comparison pairs (RTTI class
  name; key sets), as their containing objects;
* ``pointer``: the relocated word at offset k of a paired object whose bytes up to k+4
  are equal once pointer words are masked points into another object;
* ``content``: unique identical bytes (in both images' data, at the proto's alignment)
  of an object without pointer words;
* ``order``: between two paired neighbours of one section whose distance is the same on
  both sides, an unpaired object at the same offset (weak: it proposes; it settles only
  when the bytes there are equal and not all zero).

An address inside an object pairs the object: the vote is release address minus the
offset into the prototype object. The release start is the vote of the witnesses with
the smallest offset; when they disagree that is a ``witness-conflict``. Other witnesses
whose vote differs, or whose register-added field offset differs, are field accesses at
another offset (``offset-changed``; ``offset-outside`` when they fall outside the
prototype size).
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import dataflow  # noqa: E402
import elfimage  # noqa: E402
import functions  # noqa: E402
import mips  # noqa: E402
import pairing  # noqa: E402
import protofacts  # noqa: E402
import tables  # noqa: E402
import vtables  # noqa: E402

PROTOTYPE = Path("support/socom.elf")
RELEASE = Path("support/SCUS_971.34")
FUNCTION_MAP = Path("docs/release/function-map.tsv")
OUT_TSV = Path("docs/release/data-map.tsv")
OUT_MD = Path("docs/release/DATA.md")
OUT_JSON = Path("build/release/data-map.json")

ALIGN_BLOCK = 4  # equal masked words a block needs to align a deviating pair
MIN_CONTENT = 4  # bytes: smaller objects are not paired by content
POINTER_ROUNDS = 12
CLASSES = ("exact", "deviating", "unsure", "new", "removed")
KINDS = ("operand-exact", "vtable", "named-table", "content", "pointer", "operand-aligned", "order")
STRONG = frozenset(KINDS[:6])
TABLE_KINDS = frozenset({"vtable", "named-table"})
# Tiers: the strongest tier with witnesses decides the release start; a weaker witness that
# disagrees is listed (``contradicted`` when it points past the object), it does not vote.
# Content of 8 bytes or more (or a C string) and pointers from objects whose bytes agree up
# to the pointer outrank aligned operands of deviating functions, which repeated code can
# still shift. For a literal (@N) such content is tier 0: the release's GetCommandName is
# byte-identical but returns the previous string at every case after an inserted enum entry.
TIER = {"operand-exact": 1, "vtable": 1, "named-table": 1, "content": 2, "pointer": 2,
        "operand-aligned": 3, "order": 4}
CONTENT_STRONG = 8  # bytes: shorter unique content is tier 3, unless it is a C string


def tier_of(vote, obj) -> int:
    if vote.kind == "content":
        strong = obj.size >= CONTENT_STRONG or obj.c_string
        if strong and obj.literal:
            return 0  # a literal (@N) is its bytes: an enum shift moves the code's use, not the literal
        return 2 if strong else 3
    return TIER[vote.kind]


def is_c_string(raw: bytes) -> bool:
    """At least three printable characters and the terminating NUL (padding NULs allowed)."""

    text = raw.rstrip(b"\0")
    return len(text) >= 3 and len(text) < len(raw) and all(0x20 <= b < 0x7F or b in (9, 10, 13) for b in text)
R_MIPS_32 = 2
# Linker symbols that open a region of the prototype (FUNCTION_ORDER.md, "from <symbol>").
REGION_SYMBOLS = ("_dataStart", "__data_start", "__static_init", "__static_init_end", "__data_end",
                  "_fbss", "__bss_start")
VU_LABEL = re.compile(r"^\.(vu|vif)\.\d+$")
COLUMNS = ("release_address", "release_size", "prototype_address", "prototype_size", "prototype_symbol",
           "prototype_section", "release_section", "class", "evidence", "witnesses", "flags", "owner_file")


@dataclass
class Obj:
    """A prototype data object: the symbols at one address."""

    address: int
    size: int
    names: list[str]
    section: str = ""
    initialized: bool = True
    pointers: list[int] = field(default_factory=list)  # offsets of relocated words (R_MIPS_32)
    owner: str = ""
    owner_source: str = ""
    anonymous: bool = False
    c_string: bool = False

    @property
    def name(self) -> str:
        return self.names[0] if self.names else "-"

    @property
    def literal(self) -> bool:
        """Only Metrowerks literal labels (``@N``) name it."""

        return bool(self.names) and all(n.startswith("@") for n in self.names)

    @property
    def end(self) -> int:
        return self.address + self.size


@dataclass(frozen=True)
class Vote:
    base: int  # the release start this witness implies
    d: int  # offset of the witness's address in the prototype object
    kind: str
    witness: str  # one function pair, one data object, one table, "content", "order"
    a: int  # prototype address
    b: int  # release address
    off_p: int | None = 0  # offset a register adds after it (prototype)
    off_r: int | None = 0
    width: int = 0


@dataclass
class Result:
    obj: Obj
    base: int | None = None
    votes: list = field(default_factory=list)
    support: list = field(default_factory=list)  # votes that agree with base
    field_moves: list = field(default_factory=list)  # (p offset, r offset, witness)
    conflict: list = field(default_factory=list)  # competing release starts with their witnesses
    cls: str = ""
    flags: set = field(default_factory=set)
    size_state: str = ""
    r_size: str = "-"
    lower: int = 0
    upper: int | None = None
    content: str = "-"
    release_section: str = "-"
    witnesses: int = 0
    evidence: dict = field(default_factory=dict)
    tier: int = 0  # the evidence tier that decided the release start
    contradictions: list = field(default_factory=list)  # (release address, kind, witness) outside the object


# -- inputs -------------------------------------------------------------------------------

def read_function_map(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    out = []
    for line in lines[1:]:
        cells = dict(zip(header, line.split("\t")))
        row = {"class": cells["class"], "flags": set(f for f in cells["flags"].split(",") if f and f != "-"),
               "owner": "" if cells["owner_file"] == "-" else cells["owner_file"],
               "r": None if cells["release_address"] in ("-", "") else int(cells["release_address"], 16),
               "r_size": 0 if cells["release_size"] in ("-", "") else int(cells["release_size"]),
               "p": None if cells["prototype_address"] in ("-", "") else int(cells["prototype_address"], 16),
               "p_size": 0 if cells["prototype_size"] in ("-", "") else int(cells["prototype_size"])}
        out.append(row)
    return out


class Spans:
    """Sorted, non-overlapping function extents of one side."""

    def __init__(self, spans):
        self.spans = sorted(set(spans))
        self.starts = [s for s, _ in self.spans]

    def containing(self, address: int):
        k = bisect.bisect_right(self.starts, address) - 1
        if k >= 0 and self.spans[k][0] <= address < self.spans[k][1]:
            return self.spans[k]
        return None


def gp_of(image, words, entry_size: int) -> int | None:
    """$gp: the ``_gp`` symbol, else the value the entry function moves into $gp (``move gp, aN``)."""

    for symbol in image.symbols:
        if symbol.name == "_gp" and symbol.address:
            return symbol.address
    start = (image.entry - image.base) // 4
    count = max(1, entry_size // 4)
    states = dataflow._flow(words, start, count, image.base, None)
    for local in range(count):
        word = words[start + local]
        op = word >> 26
        if op == 0 and ((word >> 11) & 0x1F) == mips.GP and (word & 0x3F) in (0x21, 0x25, 0x2D):
            for register in ((word >> 21) & 0x1F, (word >> 16) & 0x1F):
                value = states[local].get(register)
                if register and value is not None and value[0] == "addr" and value[3] == 0:
                    return value[1]
        if op == 0x09 and ((word >> 16) & 0x1F) == mips.GP:
            value = states[local].get((word >> 21) & 0x1F)
            if value is not None and value[0] == "hi":
                return value[1] + mips.simm(word)
    return functions.find_gp(image, words)


def proto_regions(image):
    """(envelopes, linker boundaries): the input-section envelopes of the SECTION symbols."""

    by_name = defaultdict(list)
    for symbol in image.symbols:
        if symbol.kind == 3 and symbol.name.startswith(".") and symbol.address and ".DVP." not in symbol.name:
            by_name[symbol.name].extend((symbol.address, symbol.address + symbol.size))
    envelopes = sorted((min(v), max(v), name) for name, v in by_name.items())
    boundaries = sorted((s.address, s.name) for s in image.symbols if s.name in REGION_SYMBOLS and s.address)
    return envelopes, boundaries


def section_label(envelopes, boundaries, address: int) -> str:
    """The input-section envelope holding ``address``, else ``between X and Y``, plus ``from <symbol>``."""

    inside = [name for low, high, name in envelopes if low <= address < high]
    if inside:
        low = max(lo for lo, hi, name in envelopes if name == inside[0])
        base_label, opened = inside[0], low
    else:
        before = [(high, name) for low, high, name in envelopes if high <= address]
        after = [name for low, high, name in envelopes if low > address]
        base_label = "between %s and %s" % (max(before)[1] if before else "start", after[0] if after else "end")
        opened = max(before)[0] if before else 0
    k = bisect.bisect_right([a for a, _ in boundaries], address) - 1
    if not inside and k >= 0 and boundaries[k][0] >= opened:
        return "%s from %s" % (base_label, boundaries[k][1])
    return base_label


def build_objects(image, code: Spans, owners: dict[int, str]) -> list[Obj]:
    limit = image.base + image.memsz + 16
    grouped: dict[int, list] = defaultdict(list)
    for symbol in image.symbols:
        if symbol.kind not in (0, 1) or not symbol.name or not (image.base <= symbol.address < limit):
            continue
        if symbol.name.startswith(("$L", "_$")) or VU_LABEL.match(symbol.name) or code.containing(symbol.address):
            continue  # local labels, VU microcode labels (_$NAME, .vu.N, .vif.N), code
        grouped[symbol.address].append(symbol)
    envelopes, boundaries = proto_regions(image)
    pointer_words = sorted(a for a, t in image.relocations.items() if t == R_MIPS_32)
    out = []
    for address in sorted(grouped):
        symbols = sorted(grouped[address], key=lambda s: (s.kind != 1, s.name.startswith((".", "@")),
                                                          s.bind != 1, s.name))
        names = []
        for s in symbols:
            if s.name not in names:
                names.append(s.name)
        size = max(s.size for s in symbols)
        obj = Obj(address, size, names, section_label(envelopes, boundaries, address), address < image.end)
        lo = bisect.bisect_left(pointer_words, address)
        hi = bisect.bisect_left(pointer_words, address + size)
        obj.pointers = [a - address for a in pointer_words[lo:hi]]
        if obj.initialized and size and not obj.pointers and address + size <= image.end:
            obj.c_string = is_c_string(image.data[address - image.base:address - image.base + size])
        if address in owners:
            obj.owner, obj.owner_source = owners[address], "annotation"
        out.append(obj)
    return out


class Index:
    """Containing-object lookup over prototype objects (anonymous ones added on the way)."""

    def __init__(self, objects: list[Obj]):
        self.objects = sorted(objects, key=lambda o: o.address)
        self.starts = [o.address for o in self.objects]
        self.by_address = {o.address: o for o in self.objects}

    def containing(self, address: int):
        k = bisect.bisect_right(self.starts, address) - 1
        if k < 0:
            return None
        obj = self.objects[k]
        if address == obj.address or address < obj.end:
            return obj, address - obj.address
        if obj.size and address == obj.end:
            return obj, obj.size  # an end pointer
        for back in range(1, 9):
            if k - back < 0:
                break
            other = self.objects[k - back]
            if other.address <= address < other.end:
                return other, address - other.address
        return None

    def add_anonymous(self, addresses, section_of) -> int:
        added = 0
        for address in sorted(set(addresses)):
            if self.containing(address) is None and address not in self.by_address:
                obj = Obj(address, 0, [], section_of(address), anonymous=True)
                k = bisect.bisect_left(self.starts, address)
                self.objects.insert(k, obj)
                self.starts.insert(k, address)
                self.by_address[address] = obj
                added += 1
        return added


# -- code witnesses ------------------------------------------------------------------------

def occurs_once(sequence: tuple, part: tuple) -> bool:
    """``part`` occurs exactly once in ``sequence`` (overlaps counted)."""

    first = part[0]
    found = 0
    n = len(part)
    for k in range(len(sequence) - n + 1):
        if sequence[k] == first and sequence[k:k + n] == part:
            found += 1
            if found > 1:
                return False
    return found == 1


def alignment(pm: tuple, rm: tuple, ps: tuple, rs: tuple) -> dict[int, int]:
    """Prototype word index -> release word index where the alignment is certain.

    A block of equal masked words counts when it has at least ``ALIGN_BLOCK`` words and
    occurs once in each function: a repeated block (the same store of a string address in
    a table fill, one constructor after another) can align with the wrong copy.
    """

    out: dict[int, int] = {}
    blocks = [b for b in SequenceMatcher(None, pm, rm, autojunk=False).get_matching_blocks()]
    prev_a = prev_b = 0
    prev_ok = True  # the function start is an anchor
    for block in blocks:
        last = block.size == 0  # the sentinel: the function end is an anchor
        ok = last or (block.size >= ALIGN_BLOCK and occurs_once(pm, pm[block.a:block.a + block.size])
                      and occurs_once(rm, rm[block.b:block.b + block.size]))
        gap_a, gap_b = block.a - prev_a, block.b - prev_b
        if prev_ok and ok and gap_a == gap_b and gap_a > 0 and all(
                ps[prev_a + k] == rs[prev_b + k] for k in range(gap_a)):
            for k in range(gap_a):
                out[prev_a + k] = prev_b + k
        if ok:
            for k in range(block.size):
                out[block.a + k] = block.b + k
        prev_a, prev_b, prev_ok = block.a + block.size, block.b + block.size, ok
    return out


class Side:
    def __init__(self, image, spans: Spans, gp):
        self.image = image
        self.words = mips.words_of(image.data)
        self.spans = spans
        self.gp = gp
        self.limit = image.base + image.memsz + 16
        self._refs: dict[int, list] = {}

    def refs(self, start: int, size: int) -> list:
        if start not in self._refs:
            self._refs[start] = dataflow.references(self.words, (start - self.image.base) // 4, size // 4,
                                                    self.image.base, self.gp)
        return self._refs[start]

    def masked(self, start: int, size: int) -> tuple:
        masked, _ = mips.mask_function(self.words, (start - self.image.base) // 4, size // 4, self.image.base)
        return tuple(masked)

    def shapes(self, start: int, size: int) -> tuple:
        first = (start - self.image.base) // 4
        return tuple(mips.shape(w) for w in self.words[first:first + size // 4])

    def is_data(self, address: int) -> bool:
        return self.image.base <= address < self.limit and self.spans.containing(address) is None

    def bytes_at(self, address: int, size: int) -> bytes:
        """Bytes as loaded: the file's, zero past its end (bss)."""

        offset = address - self.image.base
        chunk = self.image.data[max(0, offset):max(0, offset + size)] if offset < len(self.image.data) else b""
        return chunk + bytes(size - len(chunk))


def code_witnesses(pairs, proto: Side, release: Side, stats: Counter):
    """(witness id, prototype Ref, release Ref) for every aligned data use of the function pairs."""

    out = []
    for row in pairs:
        pa, ra, size_p, size_r = row["p"], row["r"], row["p_size"], row["r_size"]
        prefs, rrefs = proto.refs(pa, size_p), release.refs(ra, size_r)
        if not prefs:
            continue
        kind = None
        mapping = None
        if row["class"] == "exact" and size_p == size_r and proto.masked(pa, size_p) == release.masked(ra, size_r):
            kind = "operand-exact"
        elif row["class"] in ("exact", "deviating"):
            kind = "operand-aligned"
            if size_p == size_r and "imm-only" in row["flags"] and proto.shapes(pa, size_p) == release.shapes(ra, size_r):
                stats["imm-only pairs aligned whole"] += 1
            else:
                mapping = alignment(proto.masked(pa, size_p), release.masked(ra, size_r),
                                    proto.shapes(pa, size_p), release.shapes(ra, size_r))
        if kind is None:
            continue
        at = {ref.index: ref for ref in rrefs}
        for ref in prefs:
            j = ref.index if mapping is None else mapping.get(ref.index)
            other = at.get(j) if j is not None else None
            if other is None or other.kind != ref.kind or other.gp != ref.gp or len(other.defs) != len(ref.defs):
                stats["%s uses not aligned" % kind] += 1
                continue
            if mapping is not None and any(mapping.get(d) != e for d, e in zip(ref.defs, other.defs)):
                stats["%s uses not aligned" % kind] += 1
                continue
            if mapping is None and ref.defs != other.defs:
                stats["%s uses not aligned" % kind] += 1
                continue
            if (ref.off is None) != (other.off is None):
                stats["%s uses not aligned" % kind] += 1
                continue
            out.append((kind, "fn:%#x" % pa, ref, other))
    return out


# -- the pairing ----------------------------------------------------------------------------

class DataPairing:
    def __init__(self, proto: Side, release: Side, objects: list[Obj], fmap: list[dict]):
        self.proto = proto
        self.release = release
        self.index = Index(objects)
        self.fmap = fmap
        self.stats: Counter = Counter()
        self.fixed_votes: dict[int, list] = defaultdict(list)  # object address -> votes (code, tables)
        self.content_votes: dict[int, list] = defaultdict(list)
        self.order_votes: dict[int, list] = defaultdict(list)
        self.pointer_votes: dict[int, list] = defaultdict(list)
        self.results: dict[int, Result] = {}
        self.mismatches: list = []  # (kind, witness, prototype address, release address, why)
        self.p_func = {row["p"]: row for row in fmap if row["p"] is not None}
        self.r_func = {row["r"]: row for row in fmap if row["r"] is not None}
        self.duplicates: set[int] = set()

    # votes
    def vote(self, store, kind, witness, a, b, off_p=0, off_r=0, width=0) -> None:
        hit = self.index.containing(a)
        if hit is None:
            self.stats["votes without an object"] += 1
            return
        obj, d = hit
        store[obj.address].append(Vote(b - d, d, kind, witness, a, b, off_p, off_r, width))

    def add_code(self, witnesses) -> None:
        for kind, witness, ref, other in witnesses:
            a, b = ref.address, other.address
            if not self.proto.is_data(a):
                continue
            if not self.release.is_data(b):
                self.mismatches.append((kind, witness, a, b, "release address is code or outside the image"))
                continue
            self.vote(self.fixed_votes, kind, witness, a, b, ref.off, other.off, ref.width)

    def add_tables(self, vt_pairs, entry_pairs) -> None:
        for p, r in vt_pairs:
            self.vote(self.fixed_votes, "vtable", "vt:%#x" % p.address, p.address, r.address)
        for p, r in entry_pairs:
            self.vote(self.fixed_votes, "named-table", "tbl:%#x" % p.address, p.address, r.address)

    # resolution
    def resolve(self, use_tables: bool = True, use_pointers: bool = True) -> dict[int, Result]:
        """The release start of every object, decided by the strongest tier that has witnesses."""

        out = {}
        claims = defaultdict(list)
        for obj in self.index.objects:
            votes = [v for v in self.fixed_votes.get(obj.address, ()) if use_tables or v.kind not in TABLE_KINDS]
            if use_pointers:
                votes += self.pointer_votes.get(obj.address, [])
            votes += self.content_votes.get(obj.address, [])
            if not votes:
                votes = list(self.order_votes.get(obj.address, []))
            result = Result(obj, votes=votes)
            if votes:
                tier = min(tier_of(v, obj) for v in votes)
                deciding = [v for v in votes if tier_of(v, obj) == tier]
                dmin = min(v.d for v in deciding)
                bases = sorted({v.base for v in deciding if v.d == dmin})
                result.tier = tier
                if len(bases) == 1:
                    result.base = bases[0]
                else:
                    result.conflict = [(b, sorted({v.witness for v in deciding if v.d == dmin and v.base == b}))
                                       for b in bases]
            if result.base is not None:
                result.support = [v for v in result.votes if v.base == result.base]
                claims[result.base].append(result)
            out[obj.address] = result
        for base, held in claims.items():
            sized = [r for r in held if r.obj.size]
            if len(sized) > 1:
                # the claimant of the strongest tier keeps the start when it is alone in that tier
                best = min(r.tier for r in sized)
                keep = [r for r in sized if r.tier == best]
                for r in sized:
                    if len(keep) == 1 and r is keep[0]:
                        r.flags.add("release-shared")
                        continue
                    r.conflict = r.conflict or [(base, sorted({v.witness for v in r.support}))]
                    r.flags.add("release-shared")
        return out

    def pointer_round(self, results) -> int:
        """Pointer votes from every paired object whose bytes agree up to the pointer word."""

        votes: dict[int, list] = defaultdict(list)
        for address, result in results.items():
            obj = result.obj
            if result.base is None or result.conflict or not obj.pointers or not obj.initialized:
                continue
            if result.votes and all(v.kind == "order" for v in result.votes):
                continue
            prefix = self.equal_prefix(obj, result.base, results)
            for k in obj.pointers:
                if k + 4 > prefix:
                    break
                target = self.proto.image.word(obj.address + k)
                word = int.from_bytes(self.release.bytes_at(result.base + k, 4), "little")
                if not self.proto.is_data(target) or not self.release.is_data(word):
                    continue
                hit = self.index.containing(target)
                if hit is None:
                    continue
                other, d = hit
                votes[other.address].append(Vote(word - d, d, "pointer", "data:%#x" % obj.address, target, word))
        changed = votes != self.pointer_votes
        self.pointer_votes = votes
        return changed

    def equal_prefix(self, obj: Obj, base: int, results) -> int:
        """Bytes from the start that agree, pointer words masked (a function pointer must map)."""

        p = self.proto.bytes_at(obj.address, obj.size)
        r = self.release.bytes_at(base, obj.size)
        pointer_at = set(obj.pointers)
        k = 0
        while k < obj.size:
            if k in pointer_at and k + 4 <= obj.size:
                target = int.from_bytes(p[k:k + 4], "little")
                word = int.from_bytes(r[k:k + 4], "little")
                if not (self.release.image.base <= word < self.release.limit):
                    return k
                row = self.p_func.get(target)
                if row is not None and row["r"] is not None and row["class"] in ("exact", "deviating") and row["r"] != word:
                    return k
                k += 4
                continue
            if p[k] != r[k]:
                return k
            k += 1
        return obj.size

    # content
    def expected(self, obj: Obj, results) -> bytes | None:
        """The bytes the release object should hold: pointer words mapped through the pairs."""

        raw = self.proto.bytes_at(obj.address, obj.size)
        if not obj.pointers:
            return raw
        out = bytearray(raw)
        for k in obj.pointers:
            if k + 4 > obj.size:
                return None
            target = int.from_bytes(raw[k:k + 4], "little")
            row = self.p_func.get(target)
            if row is not None and row["r"] is not None and row["class"] in ("exact", "deviating"):
                word = row["r"]
            elif self.proto.is_data(target):
                hit = self.index.containing(target)
                held = results.get(hit[0].address) if hit else None
                if held is None or held.base is None or held.conflict:
                    return None
                word = held.base + hit[1]
            else:
                return None
            out[k:k + 4] = word.to_bytes(4, "little")
        return bytes(out)

    def content_pass(self, results) -> None:
        """Unique content: the object's bytes once in the prototype's data and once in the release's."""

        p_lo, p_hi = self.data_range(self.proto)
        r_lo, r_hi = self.data_range(self.release)
        p_data = self.proto.image.data[p_lo - self.proto.image.base:p_hi - self.proto.image.base]
        r_data = self.release.image.data[r_lo - self.release.image.base:r_hi - self.release.image.base]
        self.content_votes = defaultdict(list)
        self.duplicates = set()
        for obj in self.index.objects:
            if not obj.initialized or obj.size < MIN_CONTENT or obj.end > self.proto.image.end:
                continue
            raw = self.proto.bytes_at(obj.address, obj.size)
            if not raw.strip(b"\0") or (len(set(raw)) < 2 and obj.size < 16):
                continue
            aligned = obj.address % 4 == 0
            p_hits = occurrences(p_data, raw, p_lo, aligned, 2, self.proto)
            if len(p_hits) > 1:
                self.duplicates.add(obj.address)
                continue
            needle = self.expected(obj, results)
            if needle is None:
                continue
            r_hits = occurrences(r_data, needle, r_lo, aligned, 2, self.release)
            if len(r_hits) > 1:
                self.duplicates.add(obj.address)
                continue
            if p_hits == [obj.address] and len(r_hits) == 1:
                self.content_votes[obj.address] = [Vote(r_hits[0], 0, "content", "content", obj.address, r_hits[0])]
        self.stats["content duplicated"] = len(self.duplicates)

    @staticmethod
    def data_range(side: Side) -> tuple[int, int]:
        """From the end of the first code cluster (functions closer than 4 KB) to the end of the file."""

        spans = side.spans.spans
        if not spans:
            return side.image.base, side.image.end
        end = spans[0][1]
        for start, stop in spans[1:]:
            if start - end > 0x1000:
                break
            end = max(end, stop)
        return end, side.image.end

    # order
    def order_pass(self, results) -> None:
        by_section = defaultdict(list)
        for obj in self.index.objects:
            by_section[obj.section].append(obj)
        for section, objs in by_section.items():
            anchors = [(o.address, results[o.address].base) for o in objs
                       if results[o.address].base is not None and not results[o.address].conflict
                       and results[o.address].votes and any(v.kind != "order" for v in results[o.address].votes)]
            chain = sorted(pairing.increasing_subsequence(anchors))
            starts = [o.address for o in objs]
            for (p1, b1), (p2, b2) in zip(chain, chain[1:]):
                if p2 - p1 != b2 - b1:
                    continue
                lo = bisect.bisect_right(starts, p1)
                hi = bisect.bisect_left(starts, p2)
                for obj in objs[lo:hi]:
                    result = results[obj.address]
                    if result.base is None and not result.conflict:
                        b = b1 + (obj.address - p1)
                        self.order_votes[obj.address] = [Vote(b, 0, "order", "order", obj.address, b)]

    def settle(self, results):
        for _ in range(POINTER_ROUNDS):
            if not self.pointer_round(results):
                break
            results = self.resolve()
            self.stats["pointer rounds"] += 1
        return results

    def run(self, witnesses, vt_pairs, entry_pairs) -> None:
        self.add_code(witnesses)
        self.add_tables(vt_pairs, entry_pairs)
        results = self.settle(self.resolve())
        for _ in range(3):  # mapped pointers of new pairs can make more content unique
            before = {a: (r.base, bool(r.conflict)) for a, r in results.items()}
            self.content_pass(results)
            results = self.settle(self.resolve())
            if before == {a: (r.base, bool(r.conflict)) for a, r in results.items()}:
                break
        self.order_pass(results)
        results = self.resolve()
        self.pointer_round(results)  # order-only objects give no pointer votes
        self.results = self.resolve()


def occurrences(data: bytes, needle: bytes, base: int, aligned: bool, limit: int, side: Side) -> list[int]:
    """Up to ``limit`` places of ``needle`` in data (4-aligned when ``aligned``; never inside code)."""

    out = []
    start = 0
    while len(out) < limit:
        k = data.find(needle, start)
        if k < 0:
            break
        if (not aligned or (base + k) % 4 == 0) and side.spans.containing(base + k) is None:
            out.append(base + k)
        start = k + 1
    return out


# -- sizes, sections, classes -----------------------------------------------------------------

def finish(pairing_: DataPairing) -> None:
    results = pairing_.results
    proto, release = pairing_.proto, pairing_.release
    paired = sorted((r.base, r.obj.address) for r in results.values() if r.base is not None and not r.conflict)
    r_starts = [b for b, _ in paired]
    objs = pairing_.index.objects
    position = {o.address: k for k, o in enumerate(objs)}
    for result in results.values():
        obj = result.obj
        if result.base is None:
            continue
        base = result.base
        k = bisect.bisect_right(r_starts, base)
        while k < len(r_starts) and r_starts[k] == base:
            k += 1
        result.upper = r_starts[k] - base if k < len(r_starts) else None
        # every witness against the chosen start: the same offset, a field at another offset
        # (inside the object or the room before the next paired object), or a contradiction
        for v in result.votes:
            if v.off_p is None or v.off_r is None:
                p_off, r_off, width = v.d, v.b - base, 0
            else:
                p_off, r_off, width = v.d + v.off_p, v.b - base + v.off_r, v.width
            if p_off == r_off:
                if r_off < max(obj.size, 1):  # an access past the end in both images says nothing of the size
                    result.lower = max(result.lower, r_off + width)
                continue
            # the address of the start taken elsewhere, a string's start elsewhere: another object
            start_elsewhere = p_off == 0 and (v.width == 0 or obj.c_string or obj.literal)
            if (v.kind in ("content", "order") or obj.size == 0 or r_off < 0 or start_elsewhere
                    or (result.upper is not None and r_off >= max(result.upper, obj.size))):
                result.contradictions.append((v.b, v.kind, v.witness))
                continue
            result.lower = max(result.lower, r_off + width)
            result.field_moves.append((p_off, r_off, v.witness))
            result.flags.add("offset-changed")
            if r_off >= obj.size:
                result.flags.add("offset-outside")
        if result.contradictions:
            result.flags.add("contradicted")
        nxt = objs[position[obj.address] + 1] if position[obj.address] + 1 < len(objs) else None
        gap_equal = False
        if nxt is not None:
            other = results[nxt.address]
            gap_equal = (other.base is not None and not other.conflict
                         and other.base - base == nxt.address - obj.address)
        if obj.size == 0:
            # a label, a linker symbol or an address no symbol holds: no size to compare
            result.size_state = "none"
            result.r_size = "-" if not result.lower else "%d..%s" % (
                result.lower, "?" if result.upper is None else result.upper)
        elif gap_equal or (result.upper is not None and result.upper == obj.size):
            result.size_state = "equal"
        elif (result.upper is not None and result.upper < obj.size) or result.lower > max(obj.size, 1):
            result.size_state = "changed"
        else:
            result.size_state = "bounded"
        if result.size_state == "bounded" and obj.c_string and (result.upper is None or result.upper >= obj.size) \
                and release.bytes_at(base, obj.size) == proto.bytes_at(obj.address, obj.size):
            result.size_state = "equal"  # a C string with the same bytes, NUL included, has the same size
        if result.size_state == "none":
            pass
        elif result.size_state == "equal" and result.lower <= max(obj.size, 1):
            result.r_size = str(obj.size)
        else:
            result.r_size = "%d..%s" % (result.lower, "?" if result.upper is None else result.upper)
            if result.size_state == "equal":
                result.size_state = "changed"
        if obj.size:
            p = proto.bytes_at(obj.address, obj.size)
            r = release.bytes_at(base, obj.size)
            if obj.pointers or p != r:
                prefix = pairing_.equal_prefix(obj, base, results)
                result.content = "equal" if prefix >= obj.size else "changed"
                if result.content == "equal" and obj.pointers:
                    for k in obj.pointers:  # data pointers must lead to the paired object
                        target = proto.image.word(obj.address + k)
                        hit = pairing_.index.containing(target) if proto.is_data(target) else None
                        if hit is None:
                            continue
                        other = results.get(hit[0].address)
                        word = int.from_bytes(release.bytes_at(base + k, 4), "little")
                        if other is not None and other.base is not None and not other.conflict and other.base + hit[1] != word:
                            result.content = "changed"
                            result.flags.add("pointer-changed")
                            break
            else:
                result.content = "equal"
    # release sections from the release neighbours
    for result in results.values():
        if result.base is None:
            continue
        result.release_section = release_section(result.base, paired, results, exclude=result.obj.address)
        if result.release_section != result.obj.section:
            result.flags.add("section-changed")
    for result in results.values():
        obj = result.obj
        kinds = Counter()
        seen = set()
        for v in result.support:
            if (v.kind, v.witness) not in seen:
                seen.add((v.kind, v.witness))
                kinds[v.kind] += 1
        result.evidence = {k: kinds[k] for k in KINDS if kinds[k]}
        result.witnesses = len({v.witness for v in result.support})
        if obj.address in pairing_.duplicates:
            if result.base is None or not set(result.evidence) & STRONG:
                result.flags.add("identical-copy")
        if result.conflict:
            result.flags.add("witness-conflict")
            result.cls = "unsure"
            continue
        if result.base is None:
            result.cls = "removed"
            continue
        if set(result.evidence) == {"order"}:
            result.flags.add("order-only")
            nonzero = obj.initialized and proto.bytes_at(obj.address, obj.size).strip(b"\0")
            if not (result.content == "equal" and nonzero):
                result.cls = "unsure"
                continue
        if result.size_state == "changed":
            result.flags.add("size-changed")
        elif result.size_state == "bounded":
            result.flags.add("size-unconfirmed")
        if result.content == "changed":
            result.flags.add("content-changed")
        differs = result.flags & {"size-changed", "size-unconfirmed", "content-changed", "offset-changed",
                                  "offset-outside", "pointer-changed", "section-changed"}
        result.cls = "deviating" if differs else "exact"


def release_section(address: int, paired, results, exclude: int | None = None) -> str:
    """The section of the nearest paired release neighbours below and above (itself excluded)."""

    starts = [b for b, _ in paired]
    k = bisect.bisect_left(starts, address)
    below = above = None
    j = k - 1
    while j >= 0 and below is None:
        if paired[j][1] != exclude:
            below = results[paired[j][1]].obj.section
        j -= 1
    j = k
    while j < len(paired) and above is None:
        if paired[j][1] != exclude and paired[j][0] >= address:
            above = results[paired[j][1]].obj.section
        j += 1
    own = results[exclude].obj.section if exclude is not None else None
    if own is not None and (own in (below, above) or below is None or above is None):
        return own  # a missing neighbour cannot contradict the section
    if below == above and below is not None:
        return below
    return "(%s)..(%s)" % (below or "start", above or "end")


# -- release-only addresses and owners ---------------------------------------------------------

def release_only(pairing_: DataPairing, fmap) -> tuple[list[dict], dict]:
    """Release data addresses code references that no paired object covers."""

    results = pairing_.results
    release = pairing_.release
    extents = sorted((r.base, r.base + max(r.obj.size, r.lower, 1)) for r in results.values()
                     if r.base is not None and not r.conflict)
    starts = [s for s, _ in extents]
    reach_end = []  # running maximum end, for nested extents
    top = 0
    for _, e in extents:
        top = max(top, e)
        reach_end.append(top)

    def covered(address: int) -> bool:
        k = bisect.bisect_right(starts, address) - 1
        return k >= 0 and reach_end[k] >= address and (address < reach_end[k] or address == extents[k][1])

    referrers: dict[int, set] = defaultdict(set)
    total = set()
    for row in fmap:
        if row["r"] is None:
            continue
        for ref in release.refs(row["r"], row["r_size"]):
            if release.is_data(ref.address):
                total.add(ref.address)
                if not covered(ref.address):
                    referrers[ref.address].add(row["r"])
    stats = {"release referenced addresses": len(total),
             "covered by a paired object": sum(1 for a in total if covered(a))}
    paired = sorted((r.base, r.obj.address) for r in results.values() if r.base is not None and not r.conflict)
    rows = []
    for address in sorted(referrers):
        callers = sorted(referrers[address])
        classes = {pairing_.r_func[c]["class"] for c in callers}
        flags = ["ref-by-new"] if classes == {"new"} else []
        owners = Counter(pairing_.r_func[c]["owner"] for c in callers if pairing_.r_func[c]["owner"])
        owner = sorted(owners.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if owners else ""
        rows.append({"release": address, "section": release_section(address, paired, results), "callers": callers,
                     "flags": flags, "owner": owner})
    return rows, stats


def referrer_owners(pairing_: DataPairing, fmap) -> dict[int, set]:
    """Prototype object address -> prototype functions that reference it (every class)."""

    out: dict[int, set] = defaultdict(set)
    for row in fmap:
        if row["p"] is None:
            continue
        for ref in pairing_.proto.refs(row["p"], row["p_size"]):
            if not pairing_.proto.is_data(ref.address):
                continue
            hit = pairing_.index.containing(ref.address)
            if hit is not None:
                out[hit[0].address].add(row["p"])
    return out


# -- outputs -------------------------------------------------------------------------------

def tsv_rows(pairing_: DataPairing, new_rows: list[dict]) -> list[dict]:
    rows = []
    for result in pairing_.results.values():
        obj = result.obj
        rows.append({
            "release_address": result.base, "release_size": result.r_size if result.base is not None else "-",
            "prototype_address": obj.address, "prototype_size": obj.size if not obj.anonymous else "-",
            "prototype_symbol": obj.name, "prototype_section": obj.section, "release_section": result.release_section,
            "class": result.cls, "evidence": ",".join("%s:%d" % kv for kv in result.evidence.items()) or "-",
            "witnesses": result.witnesses, "flags": ",".join(sorted(result.flags)) or "-",
            "owner_file": obj.owner or "-"})
    for row in new_rows:
        rows.append({
            "release_address": row["release"], "release_size": "-", "prototype_address": None, "prototype_size": "-",
            "prototype_symbol": "-", "prototype_section": "-", "release_section": row["section"], "class": "new",
            "evidence": "code:%d" % len(row["callers"]), "witnesses": len(row["callers"]),
            "flags": ",".join(row["flags"]) or "-", "owner_file": row["owner"] or "-"})
    rows.sort(key=lambda r: (r["release_address"] is None, r["release_address"] or 0,
                             r["prototype_address"] if r["prototype_address"] is not None else -1))
    return rows


def write_tsv(rows: list[dict]) -> str:
    out = ["\t".join(COLUMNS)]
    for row in rows:
        cells = []
        for column in COLUMNS:
            value = row[column]
            if column in ("release_address", "prototype_address"):
                value = "-" if value is None else "%#x" % value
            cells.append(str(value))
        out.append("\t".join(cells))
    return "\n".join(out) + "\n"


def run(root: Path, write: bool = True, out: Path | None = None) -> dict:
    out = out or root
    proto_image = elfimage.load(root / PROTOTYPE, "prototype")
    release_image = elfimage.load(root / RELEASE, "release")
    fmap = read_function_map(root / FUNCTION_MAP)
    p_spans = Spans((r["p"], r["p"] + r["p_size"]) for r in fmap if r["p"] is not None)
    r_spans = Spans((r["r"], r["r"] + r["r_size"]) for r in fmap if r["r"] is not None)
    p_words = mips.words_of(proto_image.data)
    r_words = mips.words_of(release_image.data)
    entry_p = next((r["p_size"] for r in fmap if r["p"] == proto_image.entry), 448)
    entry_r = next((r["r_size"] for r in fmap if r["r"] == release_image.entry), 448)
    proto = Side(proto_image, p_spans, gp_of(proto_image, p_words, entry_p))
    release = Side(release_image, r_spans, gp_of(release_image, r_words, entry_r))

    owners = protofacts.data_annotations(root)
    objects = build_objects(proto_image, p_spans, owners)
    data_pairing = DataPairing(proto, release, objects, fmap)
    envelopes, boundaries = proto_regions(proto_image)

    # every prototype data address code reaches gets an object (anonymous when no symbol holds it)
    referenced = []
    for row in fmap:
        if row["p"] is not None:
            referenced.extend(ref.address for ref in proto.refs(row["p"], row["p_size"]) if proto.is_data(ref.address))
    anonymous = data_pairing.index.add_anonymous(referenced, lambda a: section_label(envelopes, boundaries, a))

    stats = Counter()
    pairs = [r for r in fmap if r["p"] is not None and r["r"] is not None and r["class"] in ("exact", "deviating")]
    witnesses = code_witnesses(pairs, proto, release, stats)

    starts_p = {r["p"] for r in fmap if r["p"] is not None}
    starts_r = {r["r"] for r in fmap if r["r"] is not None}
    sizes = {s.address: s.size for s in proto_image.symbols if s.name.startswith("__vt__")}
    proto_vt = vtables.find_tables(proto_image, starts_p, sizes)
    release_vt = vtables.find_tables(release_image, starts_r)
    vt_pairs = vtables.pair_tables(proto_vt, release_vt)
    slot = lambda tabs: {a for t in tabs.values() for a in range(t.address + 8, t.address + 8 + 4 * len(t.slots), 4)}
    p_entry = tables.find_tables(proto_image, starts_p, p_spans.spans, slot(proto_vt))
    r_entry = tables.find_tables(release_image, starts_r, r_spans.spans, slot(release_vt))
    entry_pairs = tables.pair_tables(p_entry, r_entry)

    data_pairing.run(witnesses, vt_pairs, entry_pairs)
    finish(data_pairing)
    refs_by = referrer_owners(data_pairing, fmap)
    for address, result in data_pairing.results.items():
        callers = refs_by.get(address, set())
        obj = result.obj
        if not obj.owner and callers:
            owners_ = Counter(data_pairing.p_func[c]["owner"] for c in callers if data_pairing.p_func[c]["owner"])
            if owners_:
                obj.owner = sorted(owners_.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
                obj.owner_source = "referrers"
        if result.cls == "removed":
            classes = {data_pairing.p_func[c]["class"] for c in callers}
            if not callers:
                result.flags.add("unreached")
            elif classes == {"removed"}:
                result.flags.add("refs-removed")
            else:
                result.flags.add("refs-unaligned")
    new_rows, coverage = release_only(data_pairing, fmap)
    rows = tsv_rows(data_pairing, new_rows)

    import datareport

    data = datareport.collect(data_pairing, rows, new_rows, coverage, stats, witnesses, vt_pairs, entry_pairs,
                              refs_by, anonymous)
    data["inputs"] = {"prototype": proto_image.sha256, "release": release_image.sha256,
                      "prototype_gp": proto.gp, "release_gp": release.gp,
                      "function_map_rows": len(fmap), "objects": len(data_pairing.index.objects)}
    if write:
        for relative, text in ((OUT_TSV, write_tsv(rows)), (OUT_MD, datareport.markdown(data)),
                               (OUT_JSON, json.dumps(datareport.json_copy(data_pairing, data), indent=1,
                                                     sort_keys=True) + "\n")):
            path = out / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
    data["rows"] = rows
    data["pairing"] = data_pairing
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=HERE.parent.parent)
    parser.add_argument("--no-write", action="store_true", help="compute without writing the map")
    parser.add_argument("--out", type=Path, metavar="DIR",
                        help="write every output under DIR (same relative paths) instead of the repository")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    out = (root / arguments.out).resolve() if arguments.out else root
    try:
        data = run(root, write=not arguments.no_write, out=out)
    except elfimage.InputRefused as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print("missing input: %s" % Path(error.filename).name, file=sys.stderr)
        return 2
    counts = Counter(row["class"] for row in data["rows"])
    print(" ".join("%s=%d" % (c, counts[c]) for c in CLASSES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
