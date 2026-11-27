"""The prototype ELF's DWARF 1 ``.debug`` records, read for the return types of its subroutines.

Standard library only (the release tools do not import ``tools/_socom``). DWARF 1 (Unix
International, 1992): a ``.debug`` section is a chain of entries ``<length:4><tag:2><attributes>``;
an entry shorter than 8 bytes is padding. Each attribute is ``<name:2>`` whose low four bits are
its form: 1 address and 2 reference (4 bytes), 3 block with a 2-byte length, 4 block with a 4-byte
length, 5, 6, 7 data of 2, 4, 8 bytes, 8 a NUL-terminated string. A type is ``fund_type`` (2-byte
code), ``mod_fund_type`` (modifier bytes, then the code), ``user_def_type`` (reference to a type
entry) or ``mod_u_d_type`` (modifier bytes, then the reference); modifiers are 1 pointer to,
2 reference to, 3 const, 4 volatile. A subroutine without a type returns void.
"""
from __future__ import annotations

import struct
from pathlib import Path

TAG_CLASS, TAG_ENUM, TAG_GLOBAL_SUB, TAG_STRUCT, TAG_SUB, TAG_TYPEDEF, TAG_UNION = 0x02, 0x04, 0x06, 0x13, 0x14, 0x16, 0x17
TAG_FORMAL = 0x05
AT_NAME, AT_FUND, AT_MOD_FUND, AT_USER, AT_MOD_USER, AT_LOW_PC, AT_SIBLING = 0x0038, 0x0055, 0x0063, 0x0072, 0x0083, 0x0111, 0x0012
COMPOSITES = frozenset({TAG_CLASS, TAG_STRUCT, TAG_UNION})
TYPE_ATTRIBUTES = (AT_FUND, AT_MOD_FUND, AT_USER, AT_MOD_USER)


def debug_section(raw: bytes) -> bytes:
    """The bytes of the section named ``.debug`` of an ELF32 little-endian file."""

    shoff, = struct.unpack_from("<I", raw, 0x20)
    shentsize, shnum, shstrndx = struct.unpack_from("<HHH", raw, 0x2E)
    headers = [struct.unpack_from("<IIIIIIIIII", raw, shoff + i * shentsize) for i in range(shnum)]
    strtab = headers[shstrndx]
    for h in headers:
        start = strtab[4] + h[0]
        name = raw[start:raw.index(b"\0", start)]
        if name == b".debug":
            return raw[h[4]:h[4] + h[5]]
    raise ValueError("no .debug section")


def entries(data: bytes) -> dict[int, dict]:
    """Offset -> {tag, attributes {name: value}, children [offsets]} of every entry.

    Children are the entries between an entry and its ``sibling`` reference.
    """

    out: dict[int, dict] = {}
    pos = 0
    while pos + 4 <= len(data):
        length, = struct.unpack_from("<I", data, pos)
        if length < 8:
            pos += max(length, 4)
            continue
        end = pos + length
        tag, = struct.unpack_from("<H", data, pos + 4)
        attrs: dict[int, object] = {}
        at = pos + 6
        while at < end:
            name, = struct.unpack_from("<H", data, at)
            at += 2
            form = name & 0xF
            if form in (1, 2):
                value, = struct.unpack_from("<I", data, at)
                at += 4
            elif form == 3:
                size, = struct.unpack_from("<H", data, at)
                value, at = data[at + 2:at + 2 + size], at + 2 + size
            elif form == 4:
                size, = struct.unpack_from("<I", data, at)
                value, at = data[at + 4:at + 4 + size], at + 4 + size
            elif form == 5:
                value, = struct.unpack_from("<H", data, at)
                at += 2
            elif form == 6:
                value, = struct.unpack_from("<I", data, at)
                at += 4
            elif form == 7:
                value, = struct.unpack_from("<Q", data, at)
                at += 8
            elif form == 8:
                stop = data.index(b"\0", at)
                value, at = data[at:stop].decode("latin-1"), stop + 1
            else:
                raise ValueError(f"DWARF 1 entry at 0x{pos:x}: attribute 0x{name:04x} has unknown form {form}")
            attrs[name] = value
        out[pos] = {"tag": tag, "attributes": attrs}
        pos = end
    return out


def type_kind(table: dict[int, dict], attrs: dict, depth: int = 0) -> str:
    """``void``, ``fundamental``, ``pointer`` (pointer or reference), ``enum``, ``composite``
    (class, structure or union by value) or ``other`` for the type an entry's attributes name."""

    if AT_FUND in attrs:
        return "fundamental"
    if AT_MOD_FUND in attrs:
        mods = attrs[AT_MOD_FUND][:-2]
        return "pointer" if any(m in (1, 2) for m in mods) else "fundamental"
    if AT_USER in attrs or AT_MOD_USER in attrs:
        if AT_MOD_USER in attrs:
            block = attrs[AT_MOD_USER]
            if any(m in (1, 2) for m in block[:-4]):
                return "pointer"
            ref, = struct.unpack_from("<I", block, len(block) - 4)
        else:
            ref = attrs[AT_USER]
        target = table.get(ref)
        if target is None:
            return "other"
        if target["tag"] in COMPOSITES:
            return "composite"
        if target["tag"] == TAG_ENUM:
            return "enum"
        if target["tag"] == TAG_TYPEDEF and depth < 8:
            return type_kind(table, target["attributes"], depth + 1)
        return "other"
    return "void"


def subroutines(path: Path) -> dict[int, dict]:
    """Low pc -> {return: kind, params: [(name, kind)]} of every DWARF subroutine record (kinds
    as ``type_kind``; the parameters are the formal_parameter entries before its sibling)."""

    table = entries(debug_section(Path(path).read_bytes()))
    offsets = sorted(table)
    out: dict[int, dict] = {}
    for index, offset in enumerate(offsets):
        entry = table[offset]
        attrs = entry["attributes"]
        if entry["tag"] not in (TAG_GLOBAL_SUB, TAG_SUB) or AT_LOW_PC not in attrs:
            continue
        sibling = attrs.get(AT_SIBLING, offset + 1)
        params = []
        for child in offsets[index + 1:]:
            if child >= sibling:
                break
            if table[child]["tag"] == TAG_FORMAL:
                params.append((table[child]["attributes"].get(AT_NAME), type_kind(table, table[child]["attributes"])))
        out[attrs[AT_LOW_PC]] = {"return": type_kind(table, attrs), "params": params}
    return out


def subroutine_returns(path: Path) -> dict[int, str]:
    """Low pc -> the kind of type its DWARF subroutine record returns (``type_kind``)."""

    return {pc: row["return"] for pc, row in subroutines(path).items()}
