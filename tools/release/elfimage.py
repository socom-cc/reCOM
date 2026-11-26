"""ELF32 little-endian MIPS images for the release comparison (standard library only).

Only the two known executables are accepted: the prototype (full symbol table,
DWARF, relocations) and the stripped release. Everything else is refused by
SHA-256 so a generated map can never describe an unknown file.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from pathlib import Path

PROTOTYPE_SHA256 = "00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a"
RELEASE_SHA256 = "5111e776f64611ae1dcdc725f0ce9db660e90e1763e897e8f5b90f7402ce30d1"
KNOWN_INPUTS = {PROTOTYPE_SHA256: "prototype", RELEASE_SHA256: "release"}

SHT_SYMTAB = 2
SHT_REL = 9
STT_FUNC = 2


class InputRefused(ValueError):
    """An input file is not one of the two pinned executables."""


@dataclass
class Symbol:
    address: int
    size: int
    name: str
    kind: int  # STT_* value
    bind: int


@dataclass
class Image:
    """One loaded segment: ``data`` holds the file-backed bytes starting at ``base``."""

    role: str
    sha256: str
    entry: int
    base: int
    data: bytes
    memsz: int
    symbols: list[Symbol] = field(default_factory=list)
    # address -> relocation type for every REL entry of the loaded section
    relocations: dict[int, int] = field(default_factory=dict)

    @property
    def end(self) -> int:
        return self.base + len(self.data)

    def word(self, address: int) -> int:
        return struct.unpack_from("<I", self.data, address - self.base)[0]

    def contains(self, address: int) -> bool:
        return self.base <= address < self.end


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, expected_role: str | None = None) -> Image:
    raw = Path(path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    role = KNOWN_INPUTS.get(digest)
    if role is None:
        raise InputRefused(f"{Path(path).name}: SHA-256 {digest} is neither the prototype nor the release")
    if expected_role and role != expected_role:
        raise InputRefused(f"{Path(path).name}: is the {role} executable, expected the {expected_role}")
    return parse(raw, role, digest)


def parse(raw: bytes, role: str, digest: str) -> Image:
    if raw[:4] != b"\x7fELF" or raw[4] != 1 or raw[5] != 1:
        raise InputRefused("not an ELF32 little-endian file")
    (_, _, _, entry, phoff, shoff, _, _, phentsize, phnum, shentsize, shnum, _) = struct.unpack_from(
        "<HHIIIIIHHHHHH", raw, 16
    )
    segment = None
    for index in range(phnum):
        p_type, p_offset, p_vaddr, _, p_filesz, p_memsz, _, _ = struct.unpack_from(
            "<IIIIIIII", raw, phoff + index * phentsize
        )
        if p_type == 1 and p_filesz and (segment is None or p_filesz > segment[2]):
            segment = (p_offset, p_vaddr, p_filesz, p_memsz)
    if segment is None:
        raise InputRefused("no loadable segment")
    offset, vaddr, filesz, memsz = segment
    image = Image(role, digest, entry, vaddr, raw[offset:offset + filesz], memsz)
    sections = [struct.unpack_from("<IIIIIIIIII", raw, shoff + i * shentsize) for i in range(shnum)]
    for section in sections:
        if section[1] == SHT_SYMTAB and section[5]:
            strtab = sections[section[6]]
            for k in range(section[5] // 16):
                name, value, size, info, _, _ = struct.unpack_from("<IIIBBH", raw, section[4] + k * 16)
                stop = raw.index(b"\0", strtab[4] + name)
                text = raw[strtab[4] + name:stop].decode("latin-1")
                image.symbols.append(Symbol(value, size, text, info & 0xF, info >> 4))
        elif section[1] == SHT_REL and section[5]:
            for k in range(section[5] // 8):
                r_offset, r_info = struct.unpack_from("<II", raw, section[4] + k * 8)
                image.relocations[r_offset] = r_info & 0xFF
    return image


def synthetic(words: list[int], base: int = 0x100000, entry: int | None = None, role: str = "test",
              symbols: list[Symbol] | None = None, memsz: int | None = None) -> Image:
    """An in-memory image for tests."""

    data = struct.pack("<%dI" % len(words), *words)
    return Image(role, "", base if entry is None else entry, base, data,
                 len(data) if memsz is None else memsz, list(symbols or []))
