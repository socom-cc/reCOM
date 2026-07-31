from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._socom.census import build_census
from tools._socom.elf import Elf32File


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def reference(root: Path) -> Elf32File:
    return Elf32File(root / "support" / "socom.elf")


@pytest.fixture(scope="session")
def census(root: Path) -> dict:
    return build_census(root, include_rows=True)

