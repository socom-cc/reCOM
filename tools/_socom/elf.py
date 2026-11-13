"""Strict, read-only ELF32 parser for the soCOM reference binary."""

from __future__ import annotations

import dataclasses
import struct
from pathlib import Path
from typing import Iterator

from .constants import ReferenceMissingError, is_reference_path, reference_missing_message
from .util import SocomError, hex0

ELF_MAGIC = b"\x7fELF"
ELFCLASS32 = 1
ELFDATA2LSB = 1

SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_RELA = 4
SHT_NOBITS = 8
SHT_REL = 9

PT_LOAD = 1

SECTION_TYPE_NAMES = {
    SHT_NULL: "NULL",
    SHT_PROGBITS: "PROGBITS",
    SHT_SYMTAB: "SYMTAB",
    SHT_STRTAB: "STRTAB",
    SHT_RELA: "RELA",
    SHT_NOBITS: "NOBITS",
    SHT_REL: "REL",
}

SYMBOL_BINDINGS = {0: "LOCAL", 1: "GLOBAL", 2: "WEAK"}
SYMBOL_TYPES = {
    0: "NOTYPE",
    1: "OBJECT",
    2: "FUNC",
    3: "SECTION",
    4: "FILE",
}

MIPS_RELOCATION_NAMES = {
    0: "R_MIPS_NONE",
    1: "R_MIPS_16",
    2: "R_MIPS_32",
    3: "R_MIPS_REL32",
    4: "R_MIPS_26",
    5: "R_MIPS_HI16",
    6: "R_MIPS_LO16",
    7: "R_MIPS_GPREL16",
    9: "R_MIPS_GOT16",
    11: "R_MIPS_CALL16",
    12: "R_MIPS_GPREL32",
}


@dataclasses.dataclass(frozen=True)
class ElfHeader:
    elf_class: int
    data_encoding: int
    osabi: int
    elf_type: int
    machine: int
    version: int
    entry: int
    program_offset: int
    section_offset: int
    flags: int
    header_size: int
    program_entry_size: int
    program_count: int
    section_entry_size: int
    section_count: int
    section_name_index: int


@dataclasses.dataclass(frozen=True)
class ProgramHeader:
    index: int
    type: int
    offset: int
    virtual_address: int
    physical_address: int
    file_size: int
    memory_size: int
    flags: int
    alignment: int


@dataclasses.dataclass(frozen=True)
class Section:
    index: int
    name_offset: int
    name: str
    type: int
    flags: int
    address: int
    offset: int
    size: int
    link: int
    info: int
    alignment: int
    entry_size: int

    @property
    def type_name(self) -> str:
        return SECTION_TYPE_NAMES.get(self.type, f"0x{self.type:x}")

    @property
    def file_backed(self) -> bool:
        return self.type != SHT_NOBITS and self.size > 0


@dataclasses.dataclass(frozen=True)
class Symbol:
    index: int
    name_offset: int
    name: str
    value: int
    size: int
    info: int
    other: int
    section_index: int

    @property
    def binding(self) -> int:
        return self.info >> 4

    @property
    def binding_name(self) -> str:
        return SYMBOL_BINDINGS.get(self.binding, str(self.binding))

    @property
    def type(self) -> int:
        return self.info & 0xF

    @property
    def type_name(self) -> str:
        return SYMBOL_TYPES.get(self.type, str(self.type))


@dataclasses.dataclass(frozen=True)
class Relocation:
    index: int
    offset: int
    symbol_index: int
    type: int
    addend: int | None = None

    @property
    def type_name(self) -> str:
        return MIPS_RELOCATION_NAMES.get(self.type, f"R_MIPS_{self.type}")


@dataclasses.dataclass(frozen=True)
class MwcatsRecord:
    index: int
    kind: int
    flags_or_size: int
    address: int


class Elf32File:
    """Parse enough ELF32 to make project acceptance independent of LLVM."""

    def __init__(self, path: Path, data: bytes | None = None):
        """Parse ``path``, or ``data`` when given (an archive member; ``path`` only names it)."""

        self.path = path
        if data is not None:
            self.data = bytes(data)
        else:
            try:
                self.data = path.read_bytes()
            except FileNotFoundError as exc:
                if is_reference_path(path):
                    raise ReferenceMissingError(reference_missing_message()) from exc
                raise SocomError(f"ELF does not exist: {path}") from exc
        self.header = self._parse_header()
        self.program_headers = self._parse_program_headers()
        self.sections = self._parse_sections()

    def _require_range(self, offset: int, size: int, what: str) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise SocomError(
                f"{what} range {hex0(offset)}+{hex0(size)} exceeds "
                f"{len(self.data)}-byte file"
            )

    def _parse_header(self) -> ElfHeader:
        if len(self.data) < 52:
            raise SocomError("ELF is shorter than an ELF32 header")
        ident = self.data[:16]
        if ident[:4] != ELF_MAGIC:
            raise SocomError("reference is not an ELF file")
        if ident[4] != ELFCLASS32:
            raise SocomError(f"expected ELF32, got class {ident[4]}")
        if ident[5] != ELFDATA2LSB:
            raise SocomError(f"expected little-endian ELF, got encoding {ident[5]}")
        values = struct.unpack_from("<HHIIIIIHHHHHH", self.data, 16)
        return ElfHeader(
            elf_class=ident[4],
            data_encoding=ident[5],
            osabi=ident[7],
            elf_type=values[0],
            machine=values[1],
            version=values[2],
            entry=values[3],
            program_offset=values[4],
            section_offset=values[5],
            flags=values[6],
            header_size=values[7],
            program_entry_size=values[8],
            program_count=values[9],
            section_entry_size=values[10],
            section_count=values[11],
            section_name_index=values[12],
        )

    def _parse_program_headers(self) -> tuple[ProgramHeader, ...]:
        header = self.header
        if header.program_count and header.program_entry_size < 32:
            raise SocomError("ELF32 program-header entry is shorter than 32 bytes")
        size = header.program_entry_size * header.program_count
        self._require_range(header.program_offset, size, "program-header table")
        result = []
        for index in range(header.program_count):
            offset = header.program_offset + index * header.program_entry_size
            values = struct.unpack_from("<IIIIIIII", self.data, offset)
            item = ProgramHeader(index, *values)
            if item.file_size:
                self._require_range(item.offset, item.file_size, f"segment {index}")
            if item.memory_size < item.file_size:
                raise SocomError(f"segment {index} has p_memsz smaller than p_filesz")
            result.append(item)
        return tuple(result)

    def _parse_sections(self) -> tuple[Section, ...]:
        header = self.header
        if header.section_count and header.section_entry_size < 40:
            raise SocomError("ELF32 section-header entry is shorter than 40 bytes")
        size = header.section_entry_size * header.section_count
        self._require_range(header.section_offset, size, "section-header table")
        raw = []
        for index in range(header.section_count):
            offset = header.section_offset + index * header.section_entry_size
            raw.append(struct.unpack_from("<IIIIIIIIII", self.data, offset))
        if header.section_name_index >= len(raw):
            raise SocomError("section-name string-table index is out of range")
        names_raw = raw[header.section_name_index]
        self._require_range(names_raw[4], names_raw[5], "section-name string table")
        names = self.data[names_raw[4] : names_raw[4] + names_raw[5]]
        result = []
        for index, values in enumerate(raw):
            name = self._cstring(names, values[0], f"section {index} name")
            item = Section(index, values[0], name, *values[1:])
            if item.file_backed:
                self._require_range(item.offset, item.size, f"section {index} ({name})")
            result.append(item)
        return tuple(result)

    @staticmethod
    def _cstring(data: bytes, offset: int, what: str) -> str:
        if offset < 0 or offset >= len(data):
            if offset == 0 and not data:
                return ""
            raise SocomError(f"{what} offset {offset} is out of range")
        end = data.find(b"\0", offset)
        if end < 0:
            raise SocomError(f"{what} is not NUL terminated")
        return data[offset:end].decode("utf-8", errors="replace")

    def section(self, name: str) -> Section:
        for section in self.sections:
            if section.name == name:
                return section
        raise SocomError(f"ELF has no section named {name!r}")

    def section_data(self, section: Section | str) -> bytes:
        item = self.section(section) if isinstance(section, str) else section
        if item.type == SHT_NOBITS:
            return b""
        return self.data[item.offset : item.offset + item.size]

    def symbols(self, section_name: str = ".symtab") -> tuple[Symbol, ...]:
        table = self.section(section_name)
        if table.type != SHT_SYMTAB:
            raise SocomError(f"{section_name} is not SHT_SYMTAB")
        entry_size = table.entry_size or 16
        if entry_size < 16 or table.size % entry_size:
            raise SocomError(f"{section_name} has an invalid entry size")
        if table.link >= len(self.sections):
            raise SocomError(f"{section_name} links to an invalid string table")
        names = self.section_data(self.sections[table.link])
        raw = self.section_data(table)
        result = []
        for index, offset in enumerate(range(0, len(raw), entry_size)):
            values = struct.unpack_from("<IIIBBH", raw, offset)
            result.append(
                Symbol(
                    index=index,
                    name_offset=values[0],
                    name=self._cstring(names, values[0], f"symbol {index} name"),
                    value=values[1],
                    size=values[2],
                    info=values[3],
                    other=values[4],
                    section_index=values[5],
                )
            )
        return tuple(result)

    def relocations(self, section_name: str = ".relmain") -> tuple[Relocation, ...]:
        section = self.section(section_name)
        if section.type not in (SHT_REL, SHT_RELA):
            raise SocomError(f"{section_name} is not a relocation section")
        default_size = 8 if section.type == SHT_REL else 12
        entry_size = section.entry_size or default_size
        if entry_size < default_size or section.size % entry_size:
            raise SocomError(f"{section_name} has an invalid entry size")
        raw = self.section_data(section)
        result = []
        for index, offset in enumerate(range(0, len(raw), entry_size)):
            relocation_offset, info = struct.unpack_from("<II", raw, offset)
            addend = (
                struct.unpack_from("<i", raw, offset + 8)[0]
                if section.type == SHT_RELA
                else None
            )
            result.append(
                Relocation(
                    index=index,
                    offset=relocation_offset,
                    symbol_index=info >> 8,
                    type=info & 0xFF,
                    addend=addend,
                )
            )
        return tuple(result)

    def mwcats(self) -> tuple[MwcatsRecord, ...]:
        raw = self.section_data(".mwcats")
        if len(raw) % 8:
            raise SocomError(".mwcats is not an integral sequence of 8-byte records")
        return tuple(
            MwcatsRecord(index, *struct.unpack_from("<HHI", raw, offset))
            for index, offset in enumerate(range(0, len(raw), 8))
        )

    def comments(self) -> tuple[str, ...]:
        raw = self.section_data(".comment")
        return tuple(
            part.decode("ascii", errors="replace")
            for part in raw.split(b"\0")
            if part
        )

    def load_segments(self) -> Iterator[ProgramHeader]:
        return (item for item in self.program_headers if item.type == PT_LOAD)

