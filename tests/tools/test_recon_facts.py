from __future__ import annotations

from pathlib import Path

import pytest

from tools._socom.recon_check import diff_note, explain_recon_diff
from tools._socom.recon_facts import argument_reads, context, disasm, function_facts, return_sources


@pytest.fixture(scope="module")
def ctx(root: Path):
    return context(root)


def test_disassembly_of_common_forms() -> None:
    assert disasm(0x00000000, 0) == "nop"
    assert disasm(0x03E00008, 0) == "jr ra"
    assert disasm(0x8C820000, 0) == "lw v0,0(a0)"
    assert disasm(0x0002102B, 0) == "sltu v0,zero,v0"
    assert disasm(0x2405FFFF, 0) == "li a1,-1"
    assert disasm(0x0C050ADC, 0x142000, lambda a: f"F{a:x}") == "jal F142b70"


def test_argument_reads_follow_every_path(ctx) -> None:
    # Reviewer-verified: sceVu0DropShadowMatrix reads f14 only after its first branch.
    reads = argument_reads(ctx, 0x152B30)
    assert {"a0", "a1", "a2", "f12", "f13", "f14"} <= set(reads)
    assert 0x152B58 in reads["f14"]
    # Completed ldl/ldr pairs are writes: sceDmaGetEnv reads only a0.
    assert set(argument_reads(ctx, 0x150018)) == {"a0"}
    # A loop branching back to the start keeps the implicit entry edge (C2DString::Load).
    assert {"a0", "f12"} <= set(argument_reads(ctx, 0x302480))


def test_return_sources_see_delay_slots(ctx) -> None:
    # CEntityCtrl::Tick is `jr ra; move v0,zero`: not void.
    assert return_sources(ctx, 0x1F2030) == ["jr ra@0x1f2030: v0<-move v0,zero@0x1f2034; f0<-entry"]


def test_facts_report_caller_narrowing_and_slots(ctx) -> None:
    text = function_facts(ctx, 0x2EF610, caller_limit=10)
    assert "call sites: 5 (0 tail)" in text
    assert "andi s3,v0,0xff@0x2b67a8" in text
    assert "a0=lw a0,12(s1)@0x2b6794" in text
    assert "__vt__11CEntityCtrl+0x10" in function_facts(ctx, 0x1F2030)


def _row(address: str, signature: str, *, thunk: bool = False, name: str = "f") -> dict:
    return {
        "address": address,
        "name": name,
        "external": False,
        "thunk": thunk,
        "details": [f"Function: {name} at {address}", f"Signature: {signature}", f"Entry: {address}", f"Body: {address} - {address}"],
    }


def test_diff_explanation_accepts_restated_and_flags_extras(root: Path) -> None:
    proto = {"calling_convention": "__stdcall", "parameters": [], "return_type": "void"}
    result = {
        "functions": [
            {"address": "0x142b70", "name": "a", "prototype": proto},
            {"address": "0x142bc0", "name": "b", "prototype": proto},
        ]
    }
    steps = [
        {"endpoint": "set_function_prototype", "body": {"function_address": "0x142b70"}},
        {"endpoint": "set_function_prototype", "body": {"function_address": "0x142bc0"}},
    ]
    before = {"functions": [_row("00142b70", "undefined a(void)", name="a"), _row("00142bc0", "void __stdcall b(void)", name="b")]}
    diff = {
        "functions": [{"address": "00142b70", "before": before["functions"][0], "after": _row("00142b70", "void __stdcall a(void)", name="a")}],
        "data": {"added": [], "removed": []},
        "types": {"added": [], "removed": []},
        "references": {"added": [], "removed": []},
        "blocks_equal": True,
        "bookmarks_equal": True,
    }
    problems, summary = explain_recon_diff(root, diff, before, steps, result)
    assert problems == []
    assert summary["restated"] == ["0x142bc0"]
    assert "1 restated prototype(s)" in diff_note(summary)
    # An unplanned function change and a non-pointer type are both problems.
    diff["functions"].append({"address": "00150000", "before": _row("00150000", "undefined x(void)"), "after": _row("00150000", "int x(void)")})
    diff["types"]["added"].append("/project/Foo|8")
    problems, _summary = explain_recon_diff(root, diff, before, steps, result)
    assert any("extra ['0x150000']" in p for p in problems)
    assert any("neither a pointer nor an array" in p for p in problems)
