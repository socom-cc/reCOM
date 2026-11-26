"""Per-function facts both sides share: masked words, shapes, calls, data references, strings.

Strings that are source-file names (the ``__FILE__`` argument of the debug
allocators) are kept apart from the identity strings: many functions share one.
With the line number loaded into the next argument register they form a
(file, line) token, which is identity evidence.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field

import mips

PRINTABLE = set(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}
MIN_STRING = 4
SOURCE_NAME = re.compile(r"^[A-Za-z0-9_./\\:-]*\.(?:c|cc|cpp|cxx|h|hpp|inl|s)$", re.IGNORECASE)


@dataclass
class Fn:
    side: str  # "p" prototype, "r" release
    address: int
    size: int
    words: tuple
    masked: tuple
    shape: tuple
    calls: list[tuple[int, int]]  # (word index, target)
    refs: list[tuple[int, str]]  # (word index, region kind) for every masked data operand
    strings: frozenset
    code_refs: list[tuple[int, int]] = field(default_factory=list)  # (word index, code address)
    tail_calls: list[tuple[int, int]] = field(default_factory=list)  # (word index, j target outside)
    file_strings: frozenset = frozenset()
    lines: frozenset = frozenset()  # (file, line) of debug-allocator calls
    data_refs: list[tuple[int, int]] = field(default_factory=list)  # (word index, data address)
    key: bytes = b""
    grams: frozenset = frozenset()
    ops: tuple = ()

    @property
    def end(self) -> int:
        return self.address + self.size

    def references(self) -> list[tuple[int, int]]:
        """Calls, tail calls and loaded code addresses in instruction order: (word index, target)."""

        return sorted(self.calls + self.tail_calls + self.code_refs)

    def typed_references(self) -> list[tuple[int, int, str]]:
        """References with their kind: ``call`` (jal or tail call) or ``ptr`` (a loaded code address)."""

        out = [(i, t, "call") for i, t in self.calls + self.tail_calls] + [(i, t, "ptr") for i, t in self.code_refs]
        return sorted(out)


GP_PSEUDO = 0x7F800000  # stands in for an unknown $gp: data_refs then hold GP_PSEUDO + offset


def find_gp(image, words) -> int | None:
    """$gp: the ``_gp`` symbol when the image has one, else what crt0 loads near the entry point."""

    for symbol in image.symbols:
        if symbol.name == "_gp" and symbol.address:
            return symbol.address

    start = (image.entry - image.base) // 4
    hi = None
    for index in range(max(0, start - 64), min(len(words), start + 256)):
        word = words[index]
        op = word >> 26
        if op == 0x0F and ((word >> 16) & 0x1F) == mips.GP:
            hi = (word & 0xFFFF) << 16
        elif hi is not None and op in (0x09, 0x0D) and ((word >> 16) & 0x1F) == mips.GP and ((word >> 21) & 0x1F) == mips.GP:
            return hi + (mips.simm(word) if op == 0x09 else word & 0xFFFF)
    return None


class Regions:
    """Region kind of an address: code (a function), data (file-backed), bss (memory only), other."""

    def __init__(self, image, spans):
        self.image = image
        self.spans = sorted(spans)
        self.starts = [s for s, _ in self.spans]

    def kind(self, address: int) -> str:
        index = bisect.bisect_right(self.starts, address) - 1
        if index >= 0 and self.spans[index][0] <= address < self.spans[index][1]:
            return "code"
        if self.image.base <= address < self.image.end:
            return "data"
        if self.image.base <= address < self.image.base + self.image.memsz:
            return "bss"
        return "other"

    def string_at(self, address: int) -> str | None:
        image = self.image
        if not (image.base <= address < image.end):
            return None
        offset = address - image.base
        stop = image.data.find(b"\0", offset, offset + 512)
        if stop < 0 or stop - offset < MIN_STRING:
            return None
        chunk = image.data[offset:stop]
        if all(b in PRINTABLE for b in chunk):
            return chunk.decode("latin-1")
        return None


def grams_of(shape: tuple) -> frozenset:
    if len(shape) < 3:
        return frozenset(shape)
    return frozenset(zip(shape, shape[1:], shape[2:]))


def build(side: str, image, words, spans, gp: int | None) -> list[Fn]:
    """Facts for every (start, end) span of one image."""

    regions = Regions(image, spans)
    out = []
    for start, end in sorted(spans):
        first = (start - image.base) // 4
        count = (end - start) // 4
        raw = tuple(words[first:first + count])
        masked, kinds = mips.mask_function(words, first, count, image.base)
        calls = []
        tail_calls = []
        refs = []
        code_refs = []
        strings = set()
        file_strings = set()
        file_loads = []  # (word index, register, file name)
        data_refs = []  # (word index, data address) of lui/low-half and $gp operands
        hi: dict[int, int] = {}
        last_hi: dict[int, int] = {}
        for index, (word, kind) in enumerate(zip(raw, kinds)):
            op = word >> 26
            if kind == mips.M_CALL:
                calls.append((index, mips.jump_target(word, start + 4 * index)))
            elif kind == mips.M_JUMP:
                target = mips.jump_target(word, start + 4 * index)
                if not start <= target < end:
                    tail_calls.append((index, target))
            elif kind == mips.M_HI:
                hi[(word >> 16) & 0x1F] = (word & 0xFFFF) << 16
                last_hi[(word >> 16) & 0x1F] = (word & 0xFFFF) << 16
            elif kind == mips.M_LO:
                base_register = (word >> 21) & 0x1F
                # the flow analysis said a high half reaches here; the latest lui of the
                # register stands in when it came through a branch
                value = hi.get(base_register, last_hi.get(base_register))
                if value is not None:
                    value += mips.simm(word) if op != 0x0D else (word & 0xFFFF)
                    region = regions.kind(value)
                    refs.append((index, region))
                    if region != "code":
                        data_refs.append((index, value))
                    if region == "code":
                        code_refs.append((index, value))
                    elif op == 0x09:
                        text = regions.string_at(value)
                        if text is not None and SOURCE_NAME.match(text):
                            file_strings.add(text)
                            file_loads.append((index, (word >> 16) & 0x1F, text))
                        elif text is not None:
                            strings.add(text)
                else:
                    refs.append((index, "unknown"))
            elif kind == mips.M_GP:
                # $gp operands are one kind on both sides; without a known $gp the offset itself
                # (moved to GP_PSEUDO) still names the variable within one image
                refs.append((index, "gp"))
                data_refs.append((index, (gp if gp is not None else GP_PSEUDO) + mips.simm(word)))
            if kind != mips.M_HI and op == 0x0F:
                hi.pop((word >> 16) & 0x1F, None)
        lines = set()
        for index, register, name in file_loads:
            # the line number: a small constant loaded into the next argument register nearby
            for other in range(max(0, index - 8), min(len(raw), index + 9)):
                word = raw[other]
                if (word >> 26) in (0x09, 0x0D) and ((word >> 21) & 0x1F) == 0 and ((word >> 16) & 0x1F) == register + 1:
                    lines.add((name, word & 0xFFFF))
                    break
        shape = tuple(mips.shape(w) for w in raw)
        fn = Fn(side, start, end - start, raw, tuple(masked), shape, calls, refs, frozenset(strings), code_refs,
                tail_calls, frozenset(file_strings), frozenset(lines), data_refs)
        fn.key = mips.pack(masked)
        fn.grams = grams_of(shape)
        fn.ops = tuple(mips.operation(w) for w in raw)
        out.append(fn)
    return out
