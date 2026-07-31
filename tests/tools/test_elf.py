from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from tools._socom.constants import (
    EXPECTED_ENTRY,
    EXPECTED_RELOCATION_COUNT,
    EXPECTED_SECTION_COUNT,
    EXPECTED_SYMBOL_COUNT,
    REFERENCE_SHA256,
)
from tools._socom.elf import Elf32File
from tools._socom.util import SocomError, sha256_file


def test_reference_identity_and_header(root: Path, reference: Elf32File) -> None:
    assert sha256_file(root / "support" / "socom.elf") == REFERENCE_SHA256
    assert reference.header.elf_class == 1
    assert reference.header.data_encoding == 1
    assert reference.header.machine == 8
    assert reference.header.entry == EXPECTED_ENTRY
    assert reference.header.section_count == EXPECTED_SECTION_COUNT
    assert reference.header.program_count == 2
    assert reference.header.flags == 0x20924000


def test_reference_sections(reference: Elf32File) -> None:
    assert [section.name for section in reference.sections] == [
        "",
        ".shstrtab",
        ".strtab",
        ".symtab",
        "main",
        ".relmain",
        "heap",
        ".mwcats",
        ".debug",
        ".line",
        ".comment",
        ".reginfo",
    ]
    main = reference.section("main")
    assert main.address == 0x100000
    assert main.offset == 0x80
    assert main.size == 3_626_496
    heap = reference.section("heap")
    assert heap.address == 0x5E7F00
    assert heap.file_backed
    assert heap.size == 4
    load = next(reference.load_segments())
    assert load.memory_size - load.file_size == 1_517_824


def test_reference_symbols_relocations_and_comments(reference: Elf32File) -> None:
    assert len(reference.symbols()) == EXPECTED_SYMBOL_COUNT
    relocations = reference.relocations()
    assert len(relocations) == EXPECTED_RELOCATION_COUNT
    counts = Counter(item.type_name for item in relocations)
    assert counts["R_MIPS_26"] == 50_827
    assert counts["R_MIPS_HI16"] == 23_750
    assert counts["R_MIPS_LO16"] == 24_231
    assert reference.comments() == (
        "MW MIPS C Compiler (2.4.1.01)",
        "PlayStation2",
    )
    assert len(reference.mwcats()) == 289


def test_rejects_bad_magic(tmp_path: Path, root: Path) -> None:
    data = bytearray((root / "support" / "socom.elf").read_bytes())
    data[0:4] = b"NOPE"
    path = tmp_path / "bad.elf"
    path.write_bytes(data)
    with pytest.raises(SocomError, match="not an ELF"):
        Elf32File(path)


def test_rejects_truncated_section_table(tmp_path: Path, root: Path) -> None:
    data = (root / "support" / "socom.elf").read_bytes()[:1024]
    path = tmp_path / "short.elf"
    path.write_bytes(data)
    with pytest.raises(SocomError, match="exceeds"):
        Elf32File(path)
