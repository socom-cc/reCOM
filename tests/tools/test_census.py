from __future__ import annotations

from pathlib import Path

from tools._socom.census import verify_census


def test_census_reference_invariants(census: dict, root: Path) -> None:
    assert verify_census(census) == []
    assert census["symbol_summary"]["count"] == 21_894
    assert census["symbol_summary"]["local_cutoff"] == 11_803
    assert census["relocation_summary"]["count"] == 115_142
    assert census["relocation_summary"]["hi16_lo16_group_count"] == 23_656
    assert census["debug"]["source_path_count"] == 114
    # The source-correlation summary counts src/, which the stage 4 applies and the stage 5 skeleton route change
    # (`reference census --write` refreshes the stored census): the expectations come from the tree. The 52 original
    # Z:\dev paths are ELF evidence.
    summary = census["source_correlation"]
    files = [path for path in (root / "src").rglob("*") if path.is_file()]
    present = {path.relative_to(root / "src").as_posix().casefold() for path in files}
    exact = sum(1 for row in summary["rows"] if row["expected_relative_path"].removeprefix("src/").casefold() in present)
    assert summary["original_z_dev_path_count"] == len(summary["rows"]) == 52
    assert summary["current_source_file_count"] == len(files)
    assert summary["exact_relative_path_count"] == exact
    assert summary["requires_correlation_count"] == 52 - exact


def test_census_ids_are_stable(census: dict) -> None:
    assert census["sections"][4]["id"] == census["sections"][4]["id"]
    assert len({row["id"] for row in census["symbols"]}) == 21_894
    assert len({row["id"] for row in census["relocations"]}) == 115_142


def test_mips_hi_lo_groups_reference_valid_indices(census: dict) -> None:
    count = census["relocation_summary"]["count"]
    for group in census["relocation_summary"]["hi16_lo16_groups"]:
        assert group["hi16_indices"]
        assert all(0 <= index < count for index in group["hi16_indices"])
        assert 0 <= group["lo16_index"] < count

