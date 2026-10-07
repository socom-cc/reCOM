"""Constants shared by the soCOM command-line tools."""

from __future__ import annotations

from pathlib import Path

PROJECT_NAME = "soCOM"
SCHEMA_VERSION = 4
TRACKER_ID = "socom:tracker:main"
# Ghidra's import mapped only the file-backed part of PT_LOAD 0; batch applies
# that type globals wait for the zero-fill tail to be mapped.
ZERO_FILL_MEMORY_ID = "socom:work:ghidra-zero-fill-memory"
REFERENCE_ID = "socom:binary:scus-972.05"

REFERENCE_SHA256 = (
    "00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a"
)
EXPECTED_MACHINE = 8  # EM_MIPS
EXPECTED_ENTRY = 0x140010
EXPECTED_SECTION_COUNT = 12
EXPECTED_SYMBOL_COUNT = 21_894
EXPECTED_RELOCATION_COUNT = 115_142
EXPECTED_COMPILER_COMMENT = "MW MIPS C Compiler (2.4.1.01)"

# Pinned Ghidra release for the canonical soCOM program. A change requires a
# fresh import and `progress rebaseline-live-ghidra` before semantic work.
EXPECTED_GHIDRA_VERSION = "12.1.4"

TOOLCHAIN_ID = "mwcps2-2.4-001213"
TOOLCHAIN_ARCHIVE_URL = (
    "https://github.com/decompme/compilers/releases/download/compilers/"
    "mwcps2-2.4-001213.tar.gz"
)
TOOLCHAIN_ARCHIVE_SHA256 = (
    "0ebe09436b4163c3a109b0431517281501d2de1bd5a0b049d33057710a943e3e"
)
TOOLCHAIN_UPSTREAM_COMMIT = "804c712453592c7ca15732c432fee2efa13d1825"
TOOLCHAIN_BANNER = "Version 2.4 (Engineering Build 0017)"
TOOLCHAIN_INTERNAL_SIGNATURE = "2.4.1.01"

STAGES = (
    "reference-census",
    "debug-metadata-import",
    "ghidra-reconstruction",
    "source-correlation",
    "authored-function-order",
    "authored-call-contract",
    "authored-byte-match",
    "full-function-order",
    "linked-byte-match",
    "final-validation",
)

PRIMARY_STAGE_CHAIN = (
    "reference-census",
    "debug-metadata-import",
    "ghidra-reconstruction",
    "source-correlation",
    "authored-function-order",
    "authored-call-contract",
    "full-function-order",
    "linked-byte-match",
    "final-validation",
)


def workspace_root() -> Path:
    """Return the repository root from this module's location."""

    return Path(__file__).resolve().parents[2]


def agent_dir(root: Path | None = None) -> Path:
    return (root or workspace_root()) / ".agent"


def reference_path(root: Path | None = None) -> Path:
    return (root or workspace_root()) / "support" / "socom.elf"


def tracker_path(root: Path | None = None) -> Path:
    return agent_dir(root) / "RECONSTRUCTION_PROGRESS.json"
