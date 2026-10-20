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


def test_result_use_skips_fpu_compares_and_follows_branches(ctx) -> None:
    from tools._socom.recon_facts import _fpr_writes, _use_after_call

    # c.le.s f20,f0 writes the condition flag, not f0.
    assert _fpr_writes(0x4600A03E) == frozenset()
    # Reviewer-verified read of f0 in a branch delay slot after the call at 0x2ab498.
    caller = max(start for start in ctx.size if start <= 0x2AB498)
    assert "mul.s f0,f0,f20@0x2ab4bc" in _use_after_call(ctx, caller, 0x2AB498, True)


def test_stack_and_forwarded_arguments(ctx) -> None:
    from tools._socom.recon_facts import forwarded_arguments, stack_argument_reads

    # Build_Tree_ForChinese_TreeCtx reads a ninth argument at 192(sp) with a 192-byte frame.
    assert stack_argument_reads(ctx, 0x345CD0)[0].startswith("+0x0 (lw v1,192(sp)@0x345d1c)")
    # ExtAudioGetSamples passes a0/a1 through to an indirect call.
    rows = forwarded_arguments(ctx, 0x337B90, set())
    assert rows and rows[0].startswith("a0,a1,") and "jalr v0@0x337ba4" in rows[0]


def test_diff_explanation_accepts_relocation_backed_pointer_references(root: Path) -> None:
    steps = [{"endpoint": "apply_data_type", "body": {"address": "0x44d0d0", "type_name": "char *[32]"}}]
    result = {"functions": [], "globals": [{"address": "0x44d0d0", "size": 128, "type": "char *[32]"}]}
    diff = {
        "functions": [],
        "data": {
            "added": [{"address": "0044d0d0", "name": "c", "size": 128, "type": "char *[32]"}],
            "removed": [{"address": "0044d0d0", "name": "c", "size": 128, "type": "undefined1[128]"}],
        },
        "types": {"added": ["/char *[32]|128"], "removed": []},
        # The word at 0x44d0d0 is relocated (R_MIPS_32) to 0x44ced0.
        "references": {"added": [["0044d0d0", "0x44ced0", "DATA"]], "removed": []},
        "blocks_equal": True,
        "bookmarks_equal": True,
    }
    problems, summary = explain_recon_diff(root, diff, {"functions": []}, steps, result)
    assert problems == [] and summary["derived_references"] == 1
    diff["references"]["added"].append(["0044d0d0", "0x44cee0", "DATA"])
    problems, _summary = explain_recon_diff(root, diff, {"functions": []}, steps, result)
    assert any("references/blocks/bookmarks changed" in p for p in problems)


def test_object_bytes_shows_relocated_strings(ctx) -> None:
    from tools._socom.recon_facts import object_bytes

    text = object_bytes(ctx, 0x43D7B8)
    assert "inside gpszVersion (0x43d7b8, 4 bytes)" in text
    assert "reloc 0x43d7b8 -> 0x468ab0 'rt_crypt version: 1.01.0002'" in text
    assert "string at 0x468ab0: 'rt_crypt version: 1.01.0002'" in object_bytes(ctx, 0x468AB0, 32)


def test_syscall_stubs_show_live_arguments(ctx) -> None:
    from tools._socom.recon_facts import forwarded_arguments, syscall_arguments

    assert syscall_arguments(ctx, 0x15B2C0) == ["syscall v1=-26@0x15b2c4: entry values reaching it a0,a1,a2,a3,t0,t1,t2,t3"]
    assert forwarded_arguments(ctx, 0x15C1A0, set())[0].startswith("a0,a1,a2,a3,t0,t1,t2,t3 -> jal _iEnableIntc")


def test_v0_is_traced_through_callees_that_leave_it(ctx) -> None:
    from tools._socom.recon_facts import return_sources

    # CZBodyAnimBlend::Clear's own li v0,-1 reaches its exit past a call that never writes v0.
    assert return_sources(ctx, 0x1DF920)[0].startswith("jr ra@0x1dfa28: v0<-li v0,-1@0x1df924;")
    # SetMultiplier writes v0 on some paths only: both values reach CopyValues' exit.
    row = return_sources(ctx, 0x1E1D20)[0]
    assert "lbu v0,35(a1)@0x1e1d88" in row and "ret(SetMultiplier__10CZBodyAnimFb@0x1e1bf0)" in row


def test_tail_call_exits_show_values_the_callee_leaves(ctx) -> None:
    from tools._socom.recon_facts import return_sources

    # CAiPathStats::reset tail-calls a clear() that never writes v0 or f0.
    assert return_sources(ctx, 0x1968E0) == [
        "tail j@0x196904 -> clear__Q23std58__vector_deleter<9CAiMapLoc,Q23std21allocator<9CAiMapLoc>>Fv@0x188e40: "
        "v0<-entry; f0<-entry"
    ]


def test_syscall_stubs_write_v0_and_preserving_helpers_keep_arguments(ctx) -> None:
    from tools._socom.recon_facts import argument_reads, return_sources

    # CB_DelayTh returns iSignalSema's (kernel) result, not its entry v0.
    assert return_sources(ctx, next(a for a, n in ctx.names.items() if n == "CB_DelayTh")) == [
        "jr ra@0x16e4ac: v0<-ret(iSignalSema@0x15b550); f0<-entry"
    ]
    # sceVu0RotMatrixX reads a0/a1 after jal _sceVu0ecossin, which leaves them alone.
    reads = argument_reads(ctx, 0x152688)
    assert {"f12", "a0", "a1"} <= set(reads)
