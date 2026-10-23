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
    # returns onward, and SetPosition's v0 reaches a stored callback: both open
    # under rules version 17.
    for address, name, cls in ((0x264d30, "AllStop__11CSealCtrlAiFb", "CSealCtrlAi"), (0x227200, "SetPosition__Q23zdb5CNodeFfff", "CNode")):
        row = {"address": f"0x{address:x}", "elf_names": [name], "stage2": None, "thunk_target": None}
        assert draft_function(ctx, row, name, _types(cls), rules=17)["draft"] == "open"
    # Rules version 18: OnCommand's slot family is void (CSealCtrl::OnCommand
    # has an empty body), so AllStop's f0 chain ends there.
    row = {"address": "0x264d30", "elf_names": ["AllStop__11CSealCtrlAiFb"], "stage2": None, "thunk_target": None}
    assert draft_function(ctx, row, "AllStop", _types("CSealCtrlAi"))["draft_rule"] == "P-void"
    row = {"address": "0x227200", "elf_names": ["SetPosition__Q23zdb5CNodeFfff"], "stage2": None, "thunk_target": None}
    assert draft_function(ctx, row, "SetPosition", _types("CNode"))["draft"] == "open"


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


def test_destructor_callers_end_an_f0_chain(ctx) -> None:
    from tools._socom.recon_draft import void_verdict

    # zBoneUnloadAll's f0 chain ends at CScriptArchive::~CScriptArchive, which
    # returns this (void *) in v0 by the Metrowerks convention (rules
    # version 16; planner of group 188).
    assert "VERDICT void" in void_verdict(ctx, 0x1DD520)


def test_void_chains_are_followed_twelve_levels(ctx) -> None:
    from tools._socom.recon_draft import void_verdict

    # FreeCtxInfo's v0 passes through seven callers before every reader drops
    # it (planner of group 193); six levels left it open (rules version 17).
    assert "VERDICT void" in void_verdict(ctx, 0x33F260)


# -- rules version 18: vtable slot families (decision of 2026-10-23) ----------

UPDATE_UI_VAR = {
    0x393830: "UpdateUIVar__9CPlainBmpFP11CUIVariable",
    0x393b90: "UpdateUIVar__9CCheckBoxFP11CUIVariable",
    0x390f10: "UpdateUIVar__17CRenderableStringFP11CUIVariable",
    0x3853f0: "UpdateUIVar__8C2DClockFP11CUIVariable",
    0x394b20: "@136@UpdateUIVar__8C2DClockFP11CUIVariable",
}


def _fresh_verdicts(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft

    monkeypatch.setitem(recon_draft._FAMILY_VERDICTS, id(ctx), {})


def test_slot_family_spans_secondary_vtables_and_stubs(ctx) -> None:
    from tools._socom.recon_draft import slot_families

    # UIVarMixin::UpdateUIVar is slot 1 of the block each derived vtable keeps
    # for its UIVarMixin part (__vt__9CPlainBmp+0x5c, __vt__8C2DClock+0x7c);
    # the @N@ stubs there join the overriders in the primary blocks.
    family = slot_families(ctx)[0x393830]
    assert set(UPDATE_UI_VAR) <= set(family.members)
    assert family.method == "UpdateUIVar"
    assert slot_families(ctx)[0x394b20] is family
    assert "@8@72@__dt" not in str(slot_families(ctx)[0x1449B0].methods)  # @N@M@ virtual-base stubs


def test_slot_family_void_gives_every_override_void(ctx) -> None:
    from tools._socom.recon_draft import slot_family_verdict, void_verdict

    verdict = slot_family_verdict(ctx, 0x390f10)
    assert verdict["void"] and 0x393830 in verdict["witnesses"] and not verdict["blockers"]
    for address in UPDATE_UI_VAR:
        assert "VERDICT void: its vtable slot family is void (rules version 18)" in void_verdict(ctx, address)
    # Rules version 17: the empty CCheckBox body gets no VERDICT line and the
    # pass-through overrides stay open on their vtable words.
    assert "VERDICT" not in void_verdict(ctx, 0x393b90, rules=17)
    old = void_verdict(ctx, 0x390f10, rules=17)
    assert "VERDICT open" in old and "address is taken" in old and "slot family" not in old


def test_slot_family_conflict_blocks_the_rule(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft

    real = recon_draft._dwarf_returns(ctx)
    monkeypatch.setattr(recon_draft, "_dwarf_returns", lambda c: {**real, 0x3853F0: "gpr"})
    _fresh_verdicts(ctx, monkeypatch)
    verdict = recon_draft.slot_family_verdict(ctx, 0x393b90)
    assert not verdict["void"]
    assert (0x3853F0, "its DWARF record declares a non-void return (gpr)") in verdict["blockers"]
    text = recon_draft.void_verdict(ctx, 0x390f10)
    assert "slot family blocked by UpdateUIVar__8C2DClockFP11CUIVariable@0x3853f0" in text
    assert "VERDICT open" in text and "VERDICT void" not in text


def test_slot_family_own_value_blocks_the_rule(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft

    real = recon_draft._exit_value_problem

    def problem(c, start, indirect_tail_calls=False):
        found, rows = real(c, start, indirect_tail_calls)
        return ("v0<-li v0,1@0x390f98 at the exit jr ra@0x390f9c", rows) if start == 0x390F10 else (found, rows)

    monkeypatch.setattr(recon_draft, "_exit_value_problem", problem)
    _fresh_verdicts(ctx, monkeypatch)
    verdict = recon_draft.slot_family_verdict(ctx, 0x393830)
    assert not verdict["void"]
    (member, reason), = verdict["blockers"]
    assert member == 0x390F10 and "its own value" in reason and "callers through the slot read it" in reason


def test_slot_family_reader_blocks_the_rule(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft

    real = recon_draft._use_after_call

    def use(c, caller, site, fpr):
        # Pretend a direct caller of C2DClock::UpdateUIVar reads v0.
        return "sltu v0,zero,v0@0x10" if not fpr and caller == 0x394b20 else real(c, caller, site, fpr)

    monkeypatch.setattr(recon_draft, "_use_after_call", use)
    monkeypatch.setattr(recon_draft, "call_sites", lambda c, f: [(0x394b20, 0x394b20, "call")] if f == 0x3853F0 else [])
    _fresh_verdicts(ctx, monkeypatch)
    verdict = recon_draft.slot_family_verdict(ctx, 0x393830)
    assert not verdict["void"]
    assert any(member == 0x3853F0 and reason.startswith("v0 read at 0x394b20") for member, reason in verdict["blockers"])


def test_slot_void_draft_rule(ctx) -> None:
    types = _types("CCheckBox", "CUIVariable", "CRenderableString", "C2DClock")
    rows = {
        address: {"address": f"0x{address:x}", "elf_names": [name], "stage2": None, "thunk_target": None}
        for address, name in UPDATE_UI_VAR.items()
    }
    # The empty CCheckBox body: its vtable slot proves the receiver.
    drafted = draft_function(ctx, rows[0x393b90], "CCheckBox::UpdateUIVar", types)
    assert drafted["draft_rule"] == "P-slot-void"
    assert drafted["prototype"]["return_type"] == "void"
    assert [p["type"] for p in drafted["prototype"]["parameters"]] == ["CCheckBox *", "CUIVariable *"]
    assert any("receiver: stored in vtable slot __vt__9CCheckBox+0x78" in line for line in drafted["prototype"]["evidence"])
    # A callee's result left in v0 (an indirect jalr) is covered by the family verdict.
    assert draft_function(ctx, rows[0x390f10], "CRenderableString::UpdateUIVar", types)["draft_rule"] == "P-slot-void"
    # A @N@ stub stays open: its receiver is the UIVarMixin part at +136.
    stub = draft_function(ctx, rows[0x394b20], "C2DClock::@136@UpdateUIVar", types)
    assert stub["draft"] == "open" and "base part at +N" in stub["open_reason"]
    # Rules version 17 leaves all of them open.
    for address, row in rows.items():
        assert draft_function(ctx, row, "x", types, rules=17)["draft"] == "open"


def test_partial_row_where_the_slot_family_decides_void_fails_the_check(ctx) -> None:
    row = {"address": "0x390f10", "elf_names": [UPDATE_UI_VAR[0x390f10]], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "CRenderableString::UpdateUIVar", _types("CRenderableString", "CUIVariable"))
    partial = {"address": "0x390f10", "current_name": "CRenderableString::UpdateUIVar",
               "prototype": {"partial": True, "return_type": "undefined", "parameters": []}}
    assert "use the drafted row" in check_drafted_rows({"functions": [drafted]}, {"functions": [partial]})[0]
    void_row = {"address": "0x390f10", "current_name": "CRenderableString::UpdateUIVar",
                "prototype": {"return_type": "void", "parameters": copy.deepcopy(drafted["prototype"]["parameters"])}}
    assert check_drafted_rows({"functions": [drafted]}, {"functions": [void_row]}) == []


def test_rules_version_must_be_known(ctx) -> None:
    from tools._socom.recon_draft import RULES_VERSIONS, void_verdict
    from tools._socom.util import SocomError

    assert RULES_VERSIONS == (17, 18)
    with pytest.raises(SocomError):
        void_verdict(ctx, 0x393b90, rules=6)
