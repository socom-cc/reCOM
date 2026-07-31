from __future__ import annotations

from pathlib import Path

from tools._socom.verify import compare_elf


def test_final_comparison_accepts_identical_reference(root: Path) -> None:
    reference = root / "support" / "socom.elf"
    report = compare_elf(reference, reference, mode="final")
    assert report["ok"] is True
    assert report["whole_file_equal"] is True
    assert all(section["ok"] for section in report["sections"])
    assert report["symbol_table_equal"] is True
    assert report["relocation_table_equal"] is True


def test_linked_comparison_reports_typed_difference(
    tmp_path: Path, root: Path
) -> None:
    reference = root / "support" / "socom.elf"
    data = bytearray(reference.read_bytes())
    data[0x80] ^= 0x01
    candidate = tmp_path / "candidate.elf"
    candidate.write_bytes(data)
    report = compare_elf(reference, candidate, mode="linked")
    assert report["ok"] is False
    main = next(section for section in report["sections"] if section["name"] == "main")
    assert main["ok"] is False
    assert main["difference"]["different_byte_count"] == 1

