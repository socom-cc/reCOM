from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._socom.census import build_census
from tools._socom.constants import ReferenceMissingError, is_reference_path
from tools._socom.elf import Elf32File

from reference_elf import REFERENCE_SKIP, reference_present, require_reference_elf


def _skip_for_missing_reference():
    """Turn the absent reference ELF's own missing-file error into a skip naming it.

    Only ``ReferenceMissingError`` and a ``FileNotFoundError`` for
    ``support/socom.elf`` are converted, and only while the workspace really
    lacks the file; with the ELF present this never fires.
    """

    try:
        return (yield)
    except (ReferenceMissingError, FileNotFoundError) as error:
        if reference_present(ROOT):
            raise
        if isinstance(error, FileNotFoundError) and not is_reference_path(error.filename):
            raise
        raise pytest.skip.Exception(REFERENCE_SKIP, _use_item_location=True) from None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item):
    """Fixtures that read the reference ELF (graphs, facts, copied workspaces)."""

    return (yield from _skip_for_missing_reference())


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item: pytest.Item):
    """Test bodies that read the reference ELF."""

    return (yield from _skip_for_missing_reference())


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def reference(root: Path) -> Elf32File:
    return Elf32File(require_reference_elf(root))


@pytest.fixture(scope="session")
def census(root: Path) -> dict:
    require_reference_elf(root)
    return build_census(root, include_rows=True)


@pytest.fixture(scope="session")
def reference_source_graph(root: Path) -> dict:
    """``source graph`` of the reference ELF, built once per session."""

    from tools._socom.source_graph import source_graph

    require_reference_elf(root)
    return source_graph(root)



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
