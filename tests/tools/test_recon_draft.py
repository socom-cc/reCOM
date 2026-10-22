from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tools._socom.recon_draft import _TypeIndex, check_drafted_rows, draft_function
from tools._socom.recon_facts import context


@pytest.fixture(scope="module")
def ctx(root: Path):
    return context(root)


def _types(*names: str) -> _TypeIndex:
    return _TypeIndex([{"name": name, "path": f"/project/{name}", "size": 4} for name in names])


def test_type_lookup_leaves_hashed_and_case_variants_to_a_planner() -> None:
    types = _types("CNode", "node", "Node", "EVENT@35c2195558", "event")
    assert types.resolve("CNode") == ("CNode", None)
    assert types.resolve("CGEdge")[1] == "type 'CGEdge' is absent from the live program"
    assert "ambiguous" in types.resolve("node")[1]
    assert types.resolve("EVENT") == (None, None)  # differently cased 'event' exists
    assert types.resolve("TYPE") == (None, "type 'TYPE' is absent from the live program")
    assert _types("TYPE@09b9d0502b").resolve("TYPE") == (None, None)
    assert "cannot spell" in types.resolve("pair<int,int>")[1]


def test_void_method_from_its_mangled_signature(ctx) -> None:
    row = {"address": "0x226110", "elf_names": ["SetAtomCnt__Q23zdb5CNodeFi"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "zdb::CNode::SetAtomCnt", _types("CNode"))
    assert drafted["draft_rule"] == "P-void"
    assert [p["type"] for p in drafted["prototype"]["parameters"]] == ["CNode *", "int"]
    assert drafted["prototype"]["return_type"] == "void"


def test_missing_parameter_class_is_unresolved(ctx) -> None:
    row = {"address": "0x1cff00", "elf_names": ["OnSelect__Q23zdb7CNodeExFPQ23zdb5CNodeb"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "zdb::CNodeEx::OnSelect", _types("CNodeEx"))
    assert drafted["draft_rule"] == "U-type" and drafted["prototype"] is None
    assert drafted["unresolved"] == ["parameter 1: type 'CNode' is absent from the live program"]


def test_check_catches_an_edited_drafted_row(ctx) -> None:
    row = {"address": "0x226110", "elf_names": ["SetAtomCnt__Q23zdb5CNodeFi"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "zdb::CNode::SetAtomCnt", _types("CNode"))
    draft = {"functions": [drafted]}
    plan = {"functions": [copy.deepcopy(drafted)]}
    assert check_drafted_rows(draft, plan) == []
    plan["functions"][0]["prototype"]["parameters"][1]["type"] = "uint"
    assert check_drafted_rows(draft, plan) == ["0x226110: differs from its P-void draft"]


def test_static_initializer_is_void_whatever_v0_holds(ctx) -> None:
    # __sinit_zrdr_archive.cpp ends with v0 = __register_global_object's result,
    # but the runtime calls it through the void (**)(void) .p__sinit table.
    row = {"address": "0x46b9d0", "elf_names": ["__sinit_zrdr_archive.cpp"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "__sinit_zrdr_archive.cpp", _types())
    assert drafted["draft_rule"] == "P-void"
    assert drafted["prototype"]["parameters"] == [] and drafted["prototype"]["return_type"] == "void"


def test_static_initializer_with_a_tail_jump_exit_is_void(ctx) -> None:
    # __sinit_ai_map.cpp ends `j __ct__7CAiCellFv` (a0 set in the delay slot);
    # the exit form does not change the .p__sinit table contract.
    row = {"address": "0x46a2e0", "elf_names": ["__sinit_ai_map.cpp"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "__sinit_ai_map.cpp", _types())
    assert drafted["draft_rule"] == "P-void"
    assert drafted["prototype"]["return_type"] == "void"


def test_hand_written_rows_are_checked_in_substance(ctx) -> None:
    row = {"address": "0x46b9d0", "elf_names": ["__sinit_zrdr_archive.cpp"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "__sinit_zrdr_archive.cpp", _types())
    hand = {"address": "0x46b9d0", "current_name": "__sinit_zrdr_archive.cpp",
            "prototype": {"return_type": "void", "parameters": [], "evidence": ["written before rules v3"]}}
    assert check_drafted_rows({"functions": [drafted]}, {"functions": [hand]}) == []
    hand["prototype"]["return_type"] = "int"
    assert "disagrees" in check_drafted_rows({"functions": [drafted]}, {"functions": [hand]})[0]


def test_callee_result_pass_through_is_void(ctx) -> None:
    # zVid_ZTestOnWriteSet leaves zSysSprGetPacket's result in v0 (through
    # zSysFifoKick); its only caller tail-calls it and RenderWorld overwrites v0.
    row = {"address": "0x307920", "elf_names": ["zVid_ZTestOnWriteSet__Fb"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "zVid_ZTestOnWriteSet", _types())
    assert drafted["draft_rule"] == "P-void"
    assert [p["type"] for p in drafted["prototype"]["parameters"]] == ["bool"]
    # CSealCtrlAi::AllStop can leave a callee's f0 that the virtual OnCommand
    # returns onward, and SetPosition's v0 reaches a stored callback: both open.
    for address, name, cls in ((0x264d30, "AllStop__11CSealCtrlAiFb", "CSealCtrlAi"), (0x227200, "SetPosition__Q23zdb5CNodeFfff", "CNode")):
        row = {"address": f"0x{address:x}", "elf_names": [name], "stage2": None, "thunk_target": None}
        assert draft_function(ctx, row, name, _types(cls))["draft"] == "open"


def test_scratch_value_in_f0_is_dead(ctx) -> None:
    # zdb::CVisual::NodeSetup leaves a mul.s product in f0 that it also stores
    # to m_GlobalLightScale (second decision of 2026-10-20).
    from tools._socom.recon_draft import _exits_pass_through

    assert _exits_pass_through(ctx, 0x30C6D0)[0]


def test_void_verdict_names_the_blocking_chain(ctx) -> None:
    from tools._socom.recon_draft import void_verdict

    assert "VERDICT void" in void_verdict(ctx, 0x307920)
    # PushAnim only tail-jumps to RTList::Add, which leaves v0 and f0 alone.
    assert "VERDICT void" in void_verdict(ctx, 0x1DC6A0)
    # _sceFsSigSema tail-jumps to the SignalSema syscall (v0 = kernel result); its
    # callers never read v0, and f0 is not checked through sceOpen's v0.
    assert "VERDICT void" in void_verdict(ctx, 0x15F260)
    text = void_verdict(ctx, 0x227200)  # SetPosition: v0 reaches a stored callback
    assert "VERDICT open" in text and "address is taken" in text


def test_planned_types_come_from_this_plan_first(tmp_path) -> None:
    from tools._socom.recon import _planned_types

    plan = {"functions": [{"address": "0x300c30", "prototype": {"return_type": "void", "parameters": [{"name": "this", "type": "C2D *"}]}}]}
    tracker = {"work_items": []}
    assert _planned_types(tmp_path, tracker, plan, "0x300c30") == ("void", ("C2D *",))
    assert _planned_types(tmp_path, tracker, plan, "0x300c50") is None


def test_declared_return_class_cuts_the_other_register(ctx) -> None:
    # COurGame::StartEngine is DWARF-declared to return an integer (v0), so f0
    # left by a callee dies there; v0 does not.
    from tools._socom.recon_draft import _declared_drop

    assert _declared_drop(ctx, 0x140550, True)
    assert not _declared_drop(ctx, 0x140550, False)


def test_declared_callback_types_decide_callback_returns(ctx) -> None:
    from tools._socom.recon_draft import _callback_returns, void_verdict

    callbacks = _callback_returns(ctx)
    # Passed as AddCmd's parse callback `_zanim_cmd_hdr *(*)(_zrdr *)` (a2, after
    # the receiver): returns a pointer in v0, so f0 left in it is dead.
    assert callbacks[0x1ABCF0] == "gpr"
    # Passed as zNetConnect's `void (*)(int, int, const char *)`.
    assert callbacks[0x204260] == "void"
    assert "only called through a contract (callback type or vtable slot) declared void" in void_verdict(ctx, 0x204260)
    # Ln's f0 chain ends at that pointer-returning loader.
    assert "VERDICT void" in void_verdict(ctx, 0x220750)


def test_stage2_void_with_an_explicit_dwarf_void_is_restated(ctx) -> None:
    # CHUD::SetupFiremode: its DWARF record says FT_void; a leftover in v0/f0
    # does not contradict a declared void (rules version 12).
    stage2 = {"receiver": "dwarf-this", "prototype": {"return_type": "void", "parameters": [
        {"name": "this", "type": "CHUD *"}, {"name": "seal", "type": "CZSealBody *"}]}}
    row = {"address": "0x3b7ce0", "elf_names": ["SetupFiremode__4CHUDFP10CZSealBody"], "stage2": stage2, "thunk_target": None}
    drafted = draft_function(ctx, row, "CHUD::SetupFiremode", _types("CHUD", "CZSealBody"))
    assert drafted["draft_rule"] == "P-stage2"
    assert any("explicit void return" in line for line in drafted["prototype"]["evidence"])


def test_vtable_slot_contract_from_a_dwarf_typed_override(ctx) -> None:
    from tools._socom.recon_draft import _slot_returns, void_verdict

    slots = _slot_returns(ctx)
    # CGame::StartEngine shares __vt__+0x14 with COurGame::StartEngine, whose
    # DWARF record returns uchar: callers through the vtable read v0, not f0.
    assert slots[0x20E6B0] == "gpr"
    # zSysReset's f0 chain ends there (review of group 162).
    assert "VERDICT void" in void_verdict(ctx, 0x2F49D0)


def test_destructors_follow_the_metrowerks_convention(ctx) -> None:
    # CPad::~CPad: a1 sign-extended from 16 bits, every exit returns this.
    row = {"address": "0x21b240", "elf_names": ["__dt__4CPadFv"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "CPad::~CPad", _types("CPad"))
    assert drafted["draft_rule"] == "P-dtor"
    prototype = drafted["prototype"]
    assert prototype["return_type"] == "void *"
    assert [p["type"] for p in prototype["parameters"]] == ["CPad *", "short"]


def test_declared_non_void_return_is_never_drafted_void(ctx) -> None:
    from tools._socom.recon_draft import _dwarf_returns, void_verdict

    # Any function whose DWARF record declares a struct (other) return is open.
    other = next(a for a, kind in _dwarf_returns(ctx).items() if kind == "other" and a in ctx.size)
    assert "declares a non-void return" in void_verdict(ctx, other)


def test_float_arguments_take_no_gpr_slot_in_callback_positions(ctx) -> None:
    from tools._socom.recon_draft import void_verdict

    # CVideo::Clear's f0 chain ends at fadeToEndMissionTick, passed in a2 to
    # CSched_Manager::AddTask(name, PFfPv_b, float, void *) (planner of group 183).
    assert "VERDICT void" in void_verdict(ctx, 0x307870)


def test_nested_type_must_sit_under_its_mangled_parent() -> None:
    types = _TypeIndex([
        {"name": "generic_iterator<0>", "path": "/project/std/__list_deleter<void const*, std::allocator<void const*>>/generic_iterator<0>", "size": 4},
        {"name": "CharArray", "path": "/project/std/basic_string<char, std::char_traits<char>, std::allocator<char>>/CharArray", "size": 16},
    ])
    assert not types.nested_in("generic_iterator<0>", "__list_deleter<CPnt3D, std::allocator<CPnt3D>>")
    assert types.nested_in("CharArray", "basic_string<char,std::char_traits<char>,std::allocator<char>>")
