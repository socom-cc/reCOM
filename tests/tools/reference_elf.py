"""Skip support for tests that read the untracked reference executable.

``support/`` is not tracked: a fresh clone has no ``support/socom.elf`` until
its user supplies a copy. Tests that read it skip, naming the missing file,
instead of failing; with the file present nothing here changes a result.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools._socom.constants import REFERENCE_RECORD_PATH, REFERENCE_RELATIVE_PATH, REFERENCE_SHA256, reference_path

ROOT = Path(__file__).resolve().parents[2]

REFERENCE_SKIP = (
    f"reference executable {REFERENCE_RELATIVE_PATH} is not part of the repository and has not been "
    f"supplied (expected SHA-256 {REFERENCE_SHA256}, recorded in {REFERENCE_RECORD_PATH}); "
    f"missing: {REFERENCE_RELATIVE_PATH}"
)


def reference_present(root: Path = ROOT) -> bool:
    return reference_path(root).is_file()


def require_reference_elf(root: Path = ROOT) -> Path:
    """The reference ELF's path; skip the calling test when it has not been supplied."""

    path = reference_path(root)
    if not path.is_file():
        pytest.skip(REFERENCE_SKIP)
    return path
