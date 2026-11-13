from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools._socom import recon_table
from tools._socom.recon_facts import context
from tools._socom.recon_table import _fits, _value, table_family, table_family_text

from reference_elf import require_reference_elf

# The UICommandTable handler rows of the 2026-10-24 narrow-return audit whose
# uchar rested only on zAnimUIMenuTick narrowing the result into its own bool.
AUDITED_HANDLERS = (
    0x1d07e0, 0x1d08f0, 0x1d0ad0, 0x1d0b30, 0x1d0b80, 0x1d0cb0, 0x1d0e20, 0x1d0e40, 0x1d13f0, 0x1d1840,
    0x1d1ed0, 0x1d1f20, 0x1d1fa0, 0x1d2020, 0x1d20e0, 0x1d2310, 0x1d23e0, 0x1d2560, 0x1d2570, 0x1d2ac0,
    0x1d2b50, 0x1d2cf0, 0x1d2df0, 0x1d2e20, 0x1d2e60, 0x1d2ea0, 0x1d2ee0, 0x1d2f20, 0x1d2f60, 0x1d2f80,
    0x1d2fa0, 0x1d2fd0, 0x1d37c0, 0x1d38a0, 0x1d3970, 0x1d3a70, 0x1d3b70, 0x1d3fc0, 0x1d3fd0, 0x1d4620,
    0x1d4700, 0x1d4720, 0x1d48d0, 0x1d4b90, 0x1d4f30, 0x1d5160, 0x1d5230, 0x1d52e0, 0x1d52f0, 0x1d5310,
    0x1d54e0, 0x1d55e0, 0x1d69c0, 0x1d6a50, 0x1d6b00, 0x1d6f00, 0x1d6f20,
)
UI_SET_MISSION = 0x1d5a60  # constant-only: li v0,1


@pytest.fixture(scope="module")
def ctx(root: Path):
    return context(root)


@pytest.fixture(scope="module")
def family(ctx):
    return table_family(ctx, "UICommandTable")


def _entries(result: dict) -> dict[str, dict]:
    return {row["address"]: row for row in result["entries"]}


def test_ui_command_table_is_a_uchar_family(family) -> None:
    assert (family["stride"], family["column"], family["stride_source"]) == (12, "+0x8", "the dispatch index scale")
    assert len(family["entries"]) == 147 and family["null_slots"] == 1
    verdict = family["verdict"]
    assert verdict["width"] == "uchar" and verdict["conflicts"] == [] and verdict["open_reasons"] == []
    assert {"entry": "0x1d20a0", "label": "UINetCnfUninit__FP13C2DAnimCmdHdrPf@0x1d20a0", "width": "uchar",
            "evidence": "narrows its own exit (andi v0,v0,0xff@0x1d20b4)"} in verdict["witnesses"]
    # Both zAnimUIMenuTick jalr sites index the +0x8 column by 12 and narrow
    # the result into their own bool, which is never a witness.
    sites = family["dispatch_sites"]
    assert [(s["site"], s["indexed"], s["scale"]) for s in sites] == [("0x1d0270", True, 12), ("0x1d02c0", True, 12)]
    assert all(s["v0_use"].startswith("andi v0,v0,0xff") for s in sites)
    assert all(w["entry"] != "0x1d0140" for w in verdict["witnesses"])
    assert family["contract"] == {"params": "C2DAnimCmdHdr*, float*", "registers": ["a0", "a1"], "complete": True,
                                  "entries_with_it": 147}
    entries = _entries(family)
    for address in AUDITED_HANDLERS:
        row = entries[f"0x{address:x}"]
        assert not row["problems"], row


def test_entry_classes_resolve_thunks_callees_and_members(family) -> None:
    entries = _entries(family)
    thunk = entries["0x1d6af0"]
    assert thunk["thunk_target"] == "UiSetSkbPurpose__FP13C2DAnimCmdHdrPf@0x3a7150"
    assert thunk["class"] == "constant-only (1)"
    member = entries["0x1d2ce0"]  # UIMediusEnabled: jr ra; lbu v0,%lo(theNetwork+0xe4)(at)
    assert member["class"] == "typed callee/member value" and member["values"][0].startswith("uchar load (lbu v0")
    callee = entries["0x1d5300"]  # UIIsMemCardInserted: j CMemCard::IsInserted, which narrows
    assert any("narrowing to uchar (andi v0,v0,0xff@0x307414) via IsInserted__8CMemCardFv" in v for v in callee["values"])
    assert entries["0x1d2120"]["class"] == "own narrowing of a returned local (uchar, zero-extended)"
    assert entries["0x1d20a0"]["class"] == "own narrowing at the exit (uchar, zero-extended)"
    text = table_family_text(family)
    assert text.splitlines()[-1].startswith("VERDICT uchar: every entry of the column returns uchar")
    assert "proves nothing" in text


def test_fits_is_width_and_sign_aware() -> None:
    uchar, schar, short = ("zext", 8), ("sext", 8), ("sext", 16)
    const = lambda n: _value("const", value=n)  # noqa: E731
    assert _fits(const(255), uchar) and not _fits(const(256), uchar) and not _fits(const(-1), uchar)
    assert _fits(const(-1), schar) and not _fits(const(128), schar)
    assert _fits(_value("compare", "zext", 1), schar) and _fits(_value("load", "zext", 8), uchar)
    assert not _fits(_value("load", "zext", 8), schar)  # an lbu value is not a signed char
    assert not _fits(_value("load", "sext", 8), uchar)  # an lb value is not an unsigned char
    assert _fits(_value("load", "sext", 8), short) and not _fits(_value("narrow", "zext", 16), uchar)
    assert not _fits(_value("wide"), uchar) and not _fits(_value("unset"), uchar)


def _patched_exits(monkeypatch, address: int, extra: dict) -> None:
    real = recon_table._Values.exits

    def exits(self, start, depth=0, chain=frozenset()):
        count, values = real(self, start, depth, chain)
        return (count, values + [extra]) if start == address and depth == 0 else (count, values)

    monkeypatch.setattr(recon_table._Values, "exits", exits)


@pytest.mark.parametrize(
    ("extra", "problem"),
    [
        (_value("wide", site=0x1d5a64, text="lw v0,0(a0)@0x1d5a64"), "unnarrowed 32-bit value (lw v0,0(a0)@0x1d5a64)"),
        (_value("load", "sext", 8, site=0x1d5a64, text="lb v0,4(a0)@0x1d5a64"), "schar load (lb v0,4(a0)@0x1d5a64)"),
        (_value("const", site=0x1d5a64, text="li v0,-1@0x1d5a64", value=-1), "constant -1 (li v0,-1@0x1d5a64)"),
        (_value("unset", text="v0 is not written on this path"), "no value (v0 is not written on this path)"),
    ],
)
def test_a_contradicting_entry_blocks_the_rule(ctx, monkeypatch, extra, problem) -> None:
    _patched_exits(monkeypatch, UI_SET_MISSION, extra)
    result = table_family(ctx, "UICommandTable")
    assert result["verdict"]["width"] is None
    assert result["verdict"]["conflicts"] == [f"0x{UI_SET_MISSION:x}"]
    assert problem in _entries(result)[f"0x{UI_SET_MISSION:x}"]["problems"]
    assert table_family_text(result).splitlines()[-1] == "VERDICT open: 1 conflicting entries (0x1d5a60)"


def test_extra_argument_reads_block_the_rule(ctx, monkeypatch) -> None:
    real = recon_table.argument_reads
    monkeypatch.setattr(
        recon_table, "argument_reads",
        lambda c, start: {**real(c, start), "a2": [start]} if start == UI_SET_MISSION else real(c, start),
    )
    result = table_family(ctx, "UICommandTable")
    assert result["verdict"]["conflicts"] == [f"0x{UI_SET_MISSION:x}"]
    assert _entries(result)["0x1d5a60"]["problems"] == ["reads a2 beyond the shared parameters (a0, a1)"]


def test_witnesses_of_different_widths_leave_it_open(ctx, monkeypatch) -> None:
    _patched_exits(monkeypatch, UI_SET_MISSION, _value("narrow", "zext", 16, site=0x1d5a64, text="andi v0,v0,0xffff@0x1d5a64"))
    verdict = table_family(ctx, "UICommandTable")["verdict"]
    assert verdict["width"] is None
    assert "the witnesses prove different widths: uchar, ushort" in verdict["open_reasons"]


def test_a_struct_of_function_pointers_is_not_a_family(ctx) -> None:
    # Each _LangVirtualTable slot is its own member; no indexed call reads it.
    verdict = table_family(ctx, "_LangVirtualTable")["verdict"]
    assert verdict["width"] is None
    assert verdict["open_reasons"][0].startswith("no indexed call loads its target from this column")


def test_cli_prints_json_on_request(root: Path) -> None:
    require_reference_elf(root)
    completed = subprocess.run(
        [sys.executable, "tools/socom.py", "recon", "table-family", "--table", "0x439548", "--json"],
        cwd=root, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["verdict"]["width"] == "uchar" and result["table"]["name"] == "UICommandTable"
