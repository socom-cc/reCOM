"""Virtual function tables on both sides, found and paired through their RTTI.

A Metrowerks vtable is ``{RTTI record, this-offset, slot, slot, ...}`` and the
RTTI record starts with a pointer to the class name (``"CSealCtrlAi"``,
``"std::bad_cast"``). The release keeps its RTTI, so a table is found where a
word points to a record whose first word points to a printable name and the
words after the offset are function starts; tables are paired by class name and
this-offset (secondary tables of one class by the order of their offsets).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import functions
import mips


@dataclass
class Table:
    address: int
    name: str
    offset: int  # the this-adjustment word, signed
    slots: list[int] = field(default_factory=list)  # slot targets, from +0x8
    bases: list[str] = field(default_factory=list)  # base class names from the RTTI record, offset 0 only

    @property
    def key(self) -> tuple[str, int]:
        return (self.name, self.offset)


def find_tables(image, starts: set[int], sizes: dict[int, int] | None = None) -> dict[int, Table]:
    """Tables of one image; ``sizes`` (prototype ``__vt__`` symbol sizes) fixes a table's length."""

    regions = functions.Regions(image, [])
    words = mips.words_of(image.data)
    out: dict[int, Table] = {}
    for index in range(len(words) - 2):
        record = words[index]
        if record & 3 or not (image.base <= record < image.end) or words[index + 2] not in starts:
            continue
        name = class_name(image, image.word(record))
        if not name:
            continue
        address = image.base + 4 * index
        offset = words[index + 1]
        offset = offset - (1 << 32) if offset & 0x80000000 else offset
        end = index + 2
        if sizes and address in sizes and sizes[address] >= 12:
            end = index + sizes[address] // 4
        else:
            while end < len(words) and words[end] in starts:
                end += 1
        out[address] = Table(address, name, offset, list(words[index + 2:end]), base_names(image, regions, record))
    return out


NAME_CHARACTERS = set("_:<>, @*&")


def class_name(image, address: int) -> str | None:
    """A NUL-terminated class name at ``address``: letters, digits and the punctuation of C++ names."""

    if not (image.base <= address < image.end):
        return None
    offset = address - image.base
    stop = image.data.find(b"\0", offset, offset + 256)
    if stop <= offset:
        return None
    text = image.data[offset:stop].decode("latin-1")
    if not (text[0].isalpha() or text[0] in "_@"):
        return None
    if not all(c.isalnum() or c in NAME_CHARACTERS for c in text):
        return None
    return text


def base_names(image, regions, record: int) -> list[str]:
    """Names of the bases an RTTI record lists at this-offset 0 ({base record, offset}..., 0)."""

    out = []
    bases = image.word(record + 4)
    if not (image.base <= bases < image.end):
        return out
    for k in range(32):
        address = bases + 8 * k
        if address + 8 > image.end:
            break
        base, offset = image.word(address), image.word(address + 4)
        if not base or not (image.base <= base < image.end):
            break
        name = class_name(image, image.word(base))
        if name and offset == 0:
            out.append(name)
    return out


def pair_tables(proto: dict[int, Table], release: dict[int, Table]) -> list[tuple[Table, Table]]:
    """Tables with the same class name; several of one class by equal offset, then by offset order."""

    by_name_p = defaultdict(list)
    by_name_r = defaultdict(list)
    for table in proto.values():
        by_name_p[table.name].append(table)
    for table in release.values():
        by_name_r[table.name].append(table)
    out = []
    for name in sorted(set(by_name_p) & set(by_name_r)):
        ps = sorted(by_name_p[name], key=lambda t: (-t.offset, t.address))
        rs = sorted(by_name_r[name], key=lambda t: (-t.offset, t.address))
        same = {t.offset for t in ps} & {t.offset for t in rs}
        for offset in sorted(same, reverse=True):
            p = next(t for t in ps if t.offset == offset)
            r = next(t for t in rs if t.offset == offset)
            out.append((p, r))
            ps.remove(p)
            rs.remove(r)
        out.extend(zip(ps, rs))  # the rest by offset order (a base moved inside the class)
    return sorted(out, key=lambda pr: pr[0].address)


def slot_of(tables: dict[int, Table]) -> dict[int, list[tuple[Table, int]]]:
    """Function address -> the (table, slot offset) places it fills."""

    out = defaultdict(list)
    for table in tables.values():
        for k, target in enumerate(table.slots):
            out[target].append((table, 8 + 4 * k))
    return out
