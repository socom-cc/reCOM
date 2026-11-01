from __future__ import annotations

from tools._socom.census import verify_census


def test_census_reference_invariants(census: dict) -> None:
    assert verify_census(census) == []
    assert census["symbol_summary"]["count"] == 21_894
    assert census["symbol_summary"]["local_cutoff"] == 11_803
    assert census["relocation_summary"]["count"] == 115_142
    assert census["relocation_summary"]["hi16_lo16_group_count"] == 23_656
    assert census["debug"]["source_path_count"] == 114
    # The source-correlation summary counts src/: the stage-4 applies created 38 files (2026-11-01).
    assert census["source_correlation"]["exact_relative_path_count"] == 19
    assert census["source_correlation"]["requires_correlation_count"] == 33


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

