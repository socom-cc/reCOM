from __future__ import annotations

import pytest

from tools._socom.toolchain import EXPECTED_FILES, toolchain_directory, verify_toolchain


def _require_toolchain(root) -> None:
    """compiler/ is not tracked: skip until `toolchain bootstrap` has installed the pinned files."""
    directory = toolchain_directory(root)
    missing = sorted(name for name in EXPECTED_FILES if not (directory / name).is_file())
    if missing:
        pytest.skip(
            "pinned Metrowerks toolchain is not installed (run `python tools/socom.py toolchain "
            f"bootstrap`); missing: {', '.join(missing)}"
        )


def test_pinned_toolchain_identity(root) -> None:
    _require_toolchain(root)
    report = verify_toolchain(root, compile_probe=False)
    assert report["identity_ok"] is True
    assert report["internal_signature_found"] is True
    assert len(report["files"]) == 4
    assert "Version 2.4 (Engineering Build 0017)" in report["version_probe"]["output"]
    assert "Version 2.4 (Engineering Build 0017)" in report["linker_version_probe"]["output"]
    assert (
        "Metrowerks Assembler Version 2.1.1 Build 0910"
        in report["assembler_version_probe"]["output"]
    )


def test_compile_readiness_is_honest(root) -> None:
    _require_toolchain(root)
    report = verify_toolchain(root, compile_probe=True)
    if report["compile_ready"]:
        assert report["compile_probe"]["deterministic"] is True
    else:
        assert report["compile_probe"]["blocked_by_license"] is True
