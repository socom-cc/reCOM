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



@pytest.fixture()
def stage2_tracker(root: Path, census: dict) -> dict:
    """A fresh tracker whose debug-metadata-import work is all accepted.

    Each Ghidra writer item carries a one-function receipt scope; nothing
    records a stage baseline yet.
    """

    from tools._socom.tracker import initialize_tracker, refresh_ready_and_stages

    tracker = initialize_tracker(root, census)
    for number, item in enumerate(row for row in tracker["work_items"] if row["stage"] == "debug-metadata-import"):
        item["status"] = "accepted"
        item["handoff"] = {"owner": "worker"}
        item["accepted"] = {"by": "reviewer"}
        if "ghidra-writer" in item["resources"]:
            item["ghidra_receipt"] = {
                "receipt_sha256": f"{number:064x}",
                "saved": True,
                "scope": {"functions": [f"0x{0x140000 + 16 * number:x}"], "types": [], "globals": []},
            }
    refresh_ready_and_stages(tracker)
    return tracker
