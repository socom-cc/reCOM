"""Constants shared by the soCOM command-line tools."""

from __future__ import annotations

from pathlib import Path

from .util import SocomError

PROJECT_NAME = "soCOM"
SCHEMA_VERSION = 6
TRACKER_ID = "socom:tracker:main"
# Ghidra's import mapped only the file-backed part of PT_LOAD 0; batch applies
# that type globals wait for the zero-fill tail to be mapped.
ZERO_FILL_MEMORY_ID = "socom:work:ghidra-zero-fill-memory"
REFERENCE_ID = "socom:binary:scus-972.05"
REFERENCE_PRODUCT_CODE = "SCUS-972.05"
# The reference executable is proprietary and untracked: each checkout
# supplies its own copy here, identified by REFERENCE_SHA256.
REFERENCE_RELATIVE_PATH = "support/socom.elf"
REFERENCE_RECORD_PATH = ".agent/REFERENCE_ELF.json"

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
    return (root or workspace_root()) / REFERENCE_RELATIVE_PATH


class ReferenceMissingError(SocomError):
    """The untracked reference executable has not been supplied."""


def is_reference_path(path: object) -> bool:
    """True when ``path`` names ``<root>/support/socom.elf`` for any root."""

    if path is None:
        return False
    return tuple(Path(str(path)).parts[-2:]) == tuple(REFERENCE_RELATIVE_PATH.split("/"))


def reference_missing_message() -> str:
    return (
        f"reference executable {REFERENCE_RELATIVE_PATH} is missing: it is not part of the "
        f"repository. Supply your own copy of the {REFERENCE_PRODUCT_CODE} executable at "
        f"{REFERENCE_RELATIVE_PATH}; its SHA-256 must be {REFERENCE_SHA256} "
        f"(recorded in {REFERENCE_RECORD_PATH})"
    )


def require_reference(root: Path | None = None) -> Path:
    """``support/socom.elf`` under ``root``, or a clean error naming where to supply it."""

    path = reference_path(root)
    if not path.is_file():
        raise ReferenceMissingError(reference_missing_message())
    return path


def tracker_path(root: Path | None = None) -> Path:
    return agent_dir(root) / "RECONSTRUCTION_PROGRESS.json"
