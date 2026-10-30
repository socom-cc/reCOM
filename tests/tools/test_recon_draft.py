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

    assert RULES_VERSIONS == (17, 18, 19, 20)
    with pytest.raises(SocomError):
        void_verdict(ctx, 0x393b90, rules=6)


# -- rules version 19: more chain-ending contracts (decision of 2026-10-24) ----


def test_check_keeps_the_rules_a_plan_was_drafted_under() -> None:
    from tools._socom.recon_draft import check_rules_version

    # Accepted plans drafted before version 19 stay checked under version 18.
    assert check_rules_version({"draft": {"rules_version": 19}}) == 19
    assert check_rules_version({"draft": {"rules_version": 20}}) == 20
    for recorded in (18, 17, 6, None, True):
        assert check_rules_version({"draft": {"rules_version": recorded}}) == 18
    assert check_rules_version({}) == 18


def _row(address: int, name: str) -> dict:
    return {"address": f"0x{address:x}", "elf_names": [name], "stage2": None, "thunk_target": None}


def _fresh_contracts(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft, recon_table

    monkeypatch.setattr(recon_table, "_CONTRACTS", {})
    monkeypatch.setattr(recon_draft, "_FAMILY_VERDICTS", {})


def test_integer_table_family_entries_end_f0_chains(ctx) -> None:
    from tools._socom.recon_draft import void_verdict
    from tools._socom.recon_table import table_contracts

    contracts = table_contracts(ctx)
    # UICommandTable +0x8 (VERDICT uchar): every reference is a word of that column.
    for entry in (0x1D0870, 0x1D4230, 0x1D6C10, 0x1D5490, 0x1D4CB0, 0x1D08D0, 0x1D1B10):
        assert contracts[entry] == "uchar"
    # UpdateCharWeaponUiVars' f0 reaches the dispatcher only through OnRemoveEquipment.
    old = void_verdict(ctx, 0x1FA2B0, rules=18)
    assert "VERDICT open: f0 passed on by OnRemoveEquipment" in old and "stored in a table" in old
    assert "VERDICT void" in void_verdict(ctx, 0x1FA2B0)
    drafted = draft_function(ctx, _row(0x1FA2B0, "UpdateCharWeaponUiVars__Fi"), "UpdateCharWeaponUiVars", _types())
    assert drafted["draft_rule"] == "P-void" and [p["type"] for p in drafted["prototype"]["parameters"]] == ["int"]
    assert draft_function(ctx, _row(0x1FA2B0, "UpdateCharWeaponUiVars__Fi"), "x", _types(), rules=18)["draft"] == "open"
    # SendGameSignalMessage's chain ends at UISetMenuState the same way.
    assert "VERDICT void" in void_verdict(ctx, 0x2022C0)


def test_table_contract_keeps_its_conflict_checks(ctx, monkeypatch) -> None:
    from tools._socom import recon_table
    from tools._socom.recon_draft import void_verdict

    # An entry also stored outside the column is called through another type too.
    _fresh_contracts(ctx, monkeypatch)
    monkeypatch.setitem(ctx.word32, 0x1D6C10, list(ctx.word32[0x1D6C10]) + [0x10])
    assert 0x1D6C10 not in recon_table.table_contracts(ctx)
    assert "VERDICT open: f0 passed on by OnRemoveEquipment" in void_verdict(ctx, 0x1FA2B0)
    # A column without an integer verdict gives no contract.
    _fresh_contracts(ctx, monkeypatch)
    monkeypatch.setitem(ctx.word32, 0x1D6C10, list(ctx.word32[0x1D6C10])[:-1])
    real = recon_table.table_family

    def open_family(c, key, column=None, stride=None):
        result = real(c, key, column=column, stride=stride)
        result["verdict"] = dict(result["verdict"], width=None, ext=None, bits=None)
        return result

    monkeypatch.setattr(recon_table, "table_family", open_family)
    assert recon_table.table_contracts(ctx) == {}


def test_constructors_returning_this_end_f0_chains(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft
    from tools._socom.recon_draft import _is_constructor, void_verdict

    # CSaveModule::CSaveModule returns its entry a0 (move v0,s1; s1 = a0) and
    # is referenced only by direct calls (issue bab16750).
    assert _is_constructor(ctx, 0x3F70B0)
    old = void_verdict(ctx, 0x3F7B20, rules=18)
    assert "__ct__11CSaveModuleFPCcP12CSaveManager@0x3f70b0 -> __sinit_fts_mission.cpp@0x46aab0" in old
    assert "VERDICT void" in void_verdict(ctx, 0x3F7B20)
    row = _row(0x3F7B20, "RegisterModule__12CSaveManagerFP11CSaveModule")
    drafted = draft_function(ctx, row, "CSaveManager::RegisterModule", _types("CSaveManager", "CSaveModule"))
    assert drafted["draft_rule"] == "P-void"
    assert [p["type"] for p in drafted["prototype"]["parameters"]] == ["CSaveManager *", "CSaveModule *"]
    # A constructor whose address is formed in code, or that does not return this, has no contract.
    monkeypatch.setitem(ctx.addr_taken, 0x3F70B0, [0x10])
    assert not _is_constructor(ctx, 0x3F70B0)
    monkeypatch.delitem(ctx.addr_taken, 0x3F70B0)
    monkeypatch.setattr(recon_draft, "_returns_this", lambda c, start: False)
    assert not _is_constructor(ctx, 0x3F70B0)
    assert "VERDICT open" in void_verdict(ctx, 0x3F7B20)


def test_null_arguments_fit_any_callback_parameter(ctx) -> None:
    from tools._socom.recon_draft import _callback_returns, void_verdict

    # CZWeapon::PreTick goes in a2 to AddTask(const char *, PFfPv_b, float, void *)
    # with a3 = 0: the null void * no longer rejects the reading (the v11 gap).
    assert 0x31E570 not in _callback_returns(ctx, 18)
    assert _callback_returns(ctx, 19)[0x31E570] == "gpr"
    old = void_verdict(ctx, 0x31AD80, rules=18)
    assert "f0 passed on by PreTick__8CZWeaponFfPv@0x31e570, whose address is taken" in old
    assert "VERDICT void" in void_verdict(ctx, 0x31AD80)
    # Every decision of the earlier reading stands.
    old_map, new_map = _callback_returns(ctx, 18), _callback_returns(ctx, 19)
    assert all(new_map[f] == kind for f, kind in old_map.items())


RELOCATOR_TYPES = _TypeIndex([
    {"name": "CDblBufTextureRelocator", "path": "/project/CDblBufTextureRelocator", "size": 4},
    {"name": "CTexHandle", "path": "/project/zdb/CTexHandle", "size": 4},
])


def test_slot_family_joined_through_a_base_without_a_vtable(ctx) -> None:
    from tools._socom.recon_draft import slot_families, void_verdict

    # zdb::CTextureRelocMgr has no vtable; its PreGetSprPacket fills slot +0x10 of
    # __vt__Q23zdb15CBatchRelocator, and CDblBufTextureRelocator overrides it.
    assert 0x2F9CF0 not in slot_families(ctx, 18)[0x380600].members
    family = slot_families(ctx, 19)[0x380600]
    assert set(family.members) == {0x2F9CF0, 0x380600} and family.method == "PreGetSprPacket"
    text = void_verdict(ctx, 0x380600)
    assert "joined through a base class without a vtable of its own" in text and "VERDICT void" in text
    assert "VERDICT open: the function's address is taken" in void_verdict(ctx, 0x380600, rules=18)
    name = "PreGetSprPacket__23CDblBufTextureRelocatorFPQ23zdb10CTexHandle"
    drafted = draft_function(ctx, _row(0x380600, name), "CDblBufTextureRelocator::PreGetSprPacket", RELOCATOR_TYPES)
    assert drafted["draft_rule"] == "P-slot-void"
    assert [p["type"] for p in drafted["prototype"]["parameters"]] == ["CDblBufTextureRelocator *", "CTexHandle *"]
    # The other base slots join the same way; TakeDrawPacket stays open on its own values.
    assert {0x3030A0, 0x2F9B20} == set(slot_families(ctx, 19)[0x3030A0].members)
    assert "VERDICT open" in void_verdict(ctx, 0x3805F0)


def test_joined_slot_family_keeps_its_conflict_check(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft

    real = recon_draft._dwarf_returns(ctx)
    monkeypatch.setattr(recon_draft, "_dwarf_returns", lambda c: {**real, 0x380600: "gpr"})
    _fresh_verdicts(ctx, monkeypatch)
    verdict = recon_draft.slot_family_verdict(ctx, 0x2F9CF0)
    assert not verdict["void"] and verdict["joined"]
    assert (0x380600, "its DWARF record declares a non-void return (gpr)") in verdict["blockers"]
    # Rules version 18 keeps the base method alone, still void.
    assert recon_draft.slot_family_verdict(ctx, 0x2F9CF0, 18)["void"]


# -- rules version 20: DWARF-declared void slot families (decision of 2026-10-29) --

C2D_DRAW = 0x300C70
C2D_TYPES = _TypeIndex([
    {"name": "C2D", "path": "/project/C2D", "size": 76},
    {"name": "CCamera", "path": "/project/zdb/CCamera", "size": 4},
])


def test_dwarf_declared_void_override_proves_its_slot_family(ctx) -> None:
    from tools._socom.recon_draft import slot_family_verdict, verdict_line, void_verdict

    # C2D::Draw's v0 reaches VisualGratification and CCycleButton::Draw (both
    # address-taken) through C2DString::Draw; 9 of the 18 Draw overrides in
    # slot +0xc have DWARF records declaring FT_void.
    old = slot_family_verdict(ctx, C2D_DRAW, 19)
    assert not old["void"] and "by_declaration" not in old
    new = slot_family_verdict(ctx, C2D_DRAW, 20)
    assert new["void"] and new["by_declaration"] and 0x17C3A0 in new["declared"] and len(new["declared"]) == 9
    assert new["handoffs"] == new["blockers"] and all("whose address is taken" in r for _m, r in new["handoffs"])
    text = void_verdict(ctx, C2D_DRAW)
    assert "slot family declared void" in text and "hand-off not followed" in text
    assert verdict_line(text).startswith("VERDICT void: its vtable slot family is declared void (rules version 20)")
    assert verdict_line(void_verdict(ctx, C2D_DRAW, rules=19)).startswith("VERDICT open: v0 passed on by VisualGratification")
    # A member the earlier rules already prove keeps its verdict wording.
    assert verdict_line(void_verdict(ctx, 0x17C3A0)) == verdict_line(void_verdict(ctx, 0x17C3A0, rules=19))
    drafted = draft_function(ctx, _row(C2D_DRAW, "Draw__3C2DFPQ23zdb7CCamera"), "C2D::Draw", C2D_TYPES)
    assert drafted["draft_rule"] == "P-slot-void" and drafted["prototype"]["return_type"] == "void"
    assert [p["type"] for p in drafted["prototype"]["parameters"]] == ["C2D *", "CCamera *"]
    assert any("rules version 20" in line and "FT_void" in line for line in drafted["prototype"]["evidence"])
    assert draft_function(ctx, _row(C2D_DRAW, "Draw__3C2DFPQ23zdb7CCamera"), "C2D::Draw", C2D_TYPES, rules=19)["draft"] == "open"


def test_p_void_through_a_declared_slot_contract_says_how_it_is_referenced(ctx) -> None:
    # C2DTriFan::Draw is stored only at __vt__9C2DTriFan+0xc, a slot whose
    # DWARF-typed overrides declare void: P-void admits it, and its evidence
    # names that word instead of claiming there are no word refs.
    types = _TypeIndex([
        {"name": "C2DTriFan", "path": "/project/C2DTriFan", "size": 4},
        {"name": "CCamera", "path": "/project/zdb/CCamera", "size": 4},
    ])
    drafted = draft_function(ctx, _row(0x300E90, "Draw__9C2DTriFanFPQ23zdb7CCamera"), "C2DTriFan::Draw", types)
    assert drafted["draft_rule"] == "P-void"
    evidence = drafted["prototype"]["evidence"]
    assert "no word refs or address-taken sites" not in evidence
    assert evidence[-1].startswith("stored only in vtable slots (__vt__9C2DTriFan+0xc)")
    # A function nothing references keeps the old line.
    from tools._socom.recon_draft import _reference_evidence

    unreferenced = next(a for a in sorted(ctx.size) if not ctx.word32.get(a) and not ctx.addr_taken.get(a))
    assert _reference_evidence(ctx, unreferenced, 20, []) == "no word refs or address-taken sites"


def test_declared_slot_rule_needs_a_declaration_and_only_handoffs(ctx, monkeypatch) -> None:
    from tools._socom import recon_draft

    assert recon_draft._unfollowed_handoff("v0 passed on by X@0x1, whose address is taken or stored in a table (chain: X)")
    assert recon_draft._unfollowed_handoff("chain deeper than twelve levels: a -> b")
    assert not recon_draft._unfollowed_handoff("v0 read at 0x10 in X@0x1: sltu (chain: X)")
    assert not recon_draft._unfollowed_handoff("an exit holds its own value (v0<-li): computed only to be returned")
    # Without a DWARF-declared override the family stays open.
    monkeypatch.setitem(recon_draft._DWARF_VOID, id(ctx), frozenset())
    _fresh_verdicts(ctx, monkeypatch)
    assert not recon_draft.slot_family_verdict(ctx, C2D_DRAW, 20)["void"]
    monkeypatch.undo()
    # A caller that reads the value blocks it.
    real = recon_draft._use_after_call

    def use(c, caller, site, fpr):
        return "sltu v0,zero,v0@0x10" if not fpr and caller == 0x302C50 else real(c, caller, site, fpr)

    monkeypatch.setattr(recon_draft, "_use_after_call", use)
    _fresh_verdicts(ctx, monkeypatch)
    verdict = recon_draft.slot_family_verdict(ctx, C2D_DRAW, 20)
    assert not verdict["void"] and not verdict["by_declaration"]
    assert any(reason.startswith("v0 read at") for _m, reason in verdict["blockers"])


def test_void_proof_names_dwarf_recon_void_and_the_sinit_rule(ctx) -> None:
    from tools._socom.recon_draft import sinit_rule_void, void_proof

    assert sinit_rule_void(ctx, 0x46B9D0) and sinit_rule_void(ctx, 0x46A2E0)
    assert not sinit_rule_void(ctx, 0x226320)
    assert void_proof(ctx, 0x46B9D0)[0].startswith("the drafter's __sinit_ rule")
    assert void_proof(ctx, 0x17CBE0)[0].startswith("its DWARF record declares")  # LoadThreadEntry: FT_void, open
    assert void_proof(ctx, 0x3DEFD8)[0].startswith("recon void (rules version 20): VERDICT void")  # bzero
    assert void_proof(ctx, 0x226320) == (None, "VERDICT open: the function's address is taken or stored in a table")


def test_sinit_rule_matches_the_drafter_on_every_static_initializer(ctx) -> None:
    from tools._socom.recon_draft import _function_names, sinit_rule_void

    starts = [start for start, names in _function_names(ctx).items() if any(n.startswith("__sinit_") for n in names)]
    assert len(starts) > 100
    for start in starts:
        names = _function_names(ctx)[start]
        drafted = draft_function(ctx, _row(start, names[0]), names[0], _types())
        assert sinit_rule_void(ctx, start) == (drafted.get("draft_rule") == "P-void"), hex(start)


# -- by-value class parameters over one GPR slot (coordinator, 2026-10-29) -----


def test_by_value_aggregates_over_one_gpr_slot_stay_unresolved(ctx) -> None:
    from tools._socom.recon_byvalue import by_value_problem

    # CPnt4D (16 bytes) travels as its address (lwc1 0..12(a1)); PNT2D (8) in a1.
    assert "Metrowerks passes an aggregate over 8 bytes" in by_value_problem(ctx, "CPnt4D")
    assert by_value_problem(ctx, "PNT2D") is None and by_value_problem(ctx, "CPnt4D *") is None
    assert by_value_problem(ctx, "EVENT@35c2195558") is None  # an enumeration
    assert by_value_problem(ctx, "NoSuchType") is None and "live type is 24 bytes" in by_value_problem(ctx, "NoSuchType", 24)
    types = _TypeIndex([
        {"name": "Source", "path": "/project/Particle/Source", "size": 64},
        {"name": "CPnt4D", "path": "/project/CPnt4D", "size": 16},
    ])
    row = _row(0x2392D0, "CheckExtents__Q28Particle6SourceF6CPnt4Df")
    for rules in (18, 19, 20):
        drafted = draft_function(ctx, row, "Particle::Source::CheckExtents", types, rules=rules)
        assert drafted["draft_rule"] == "U-byvalue" and drafted["prototype"] is None
        assert drafted["unresolved"][0].startswith("parameter 1: CPnt4D is passed by value")
    # An 8-byte aggregate still drafts: C2DBitmapPoly::SetCenterPos(PNT2D, float, float).
    pnt = _TypeIndex([{"name": "C2DBitmapPoly", "path": "/project/C2DBitmapPoly", "size": 300},
                      {"name": "PNT2D", "path": "/project/PNT2D", "size": 8}])
    drafted = draft_function(ctx, _row(0x2FE4A0, "SetCenterPos__13C2DBitmapPolyF5PNT2Dff"), "x", pnt)
    assert drafted["draft_rule"] == "P-void"


def test_small_by_value_classes_follow_their_callers(ctx) -> None:
    # The copy decides, not the size: CAiMapLoc (4 bytes, user copy
    # constructor) and list::iterator (generic_iterator<0>) arrive as stack
    # addresses; PNT2D and list::const_iterator (generic_iterator<1>) as values.
    from tools._socom.recon_byvalue import address_passing, by_value_parameters

    assert "addiu a3,sp,568" in address_passing(ctx, 0x2E1510, 7)
    assert "addiu a1,sp," in address_passing(ctx, 0x1D8470, 5)
    assert address_passing(ctx, 0x197190, 5) is None  # lw a1,N(sp) values
    assert address_passing(ctx, 0x2FE4A0, 5) is None  # ld a1 values

    def proto(*types: str) -> dict:
        return {"parameters": [{"name": f"p{index}", "type": t} for index, t in enumerate(types)]}

    found = by_value_parameters(ctx, proto("CSealCtrlAi *", "bool", "bool", "CAiMapLoc", "void *"), 0x2E1510)
    assert [(row["position"], row["kind"]) for row in found] == [(4, "by-address")]
    assert by_value_parameters(ctx, proto("C2DBitmapPoly *", "PNT2D", "float", "float"), 0x2FE4A0) == []
    # va_list is a typedef whose value is itself a stack address: not checked.
    assert by_value_parameters(ctx, proto("FILE *", "char *", "__gnuc_va_list"), 0x3E8C90) == []
    # A decided prototype the callers contradict is never drafted.
    types = _types("CSealCtrlAi", "CAiMapLoc")
    drafted = draft_function(ctx, _row(0x2E1510, "HandleFollowTickHideCheck__11CSealCtrlAiFbb9CAiMapLocPv"), "x", types)
    assert not (drafted.get("prototype") or {}).get("parameters")


def test_storage_follows_metrowerks_float_overflow(ctx) -> None:
    from tools._socom.recon_byvalue import storage_problems

    def proto(*types: str) -> dict:
        return {"parameters": [{"name": f"p{index}", "type": t} for index, t in enumerate(types, 1)]}

    assert storage_problems(proto(*["float"] * 8, *["int"] * 10)) == []  # ints 9+ go to the stack in both
    rows = storage_problems(proto(*["float"] * 13, "CPnt3D *", "CPnt3D *"))
    assert [(row["position"], row["problem"].split(",")[0]) for row in rows][:2] == [
        (9, "Metrowerks passes it in stack+0x0"), (10, "Metrowerks passes it in stack+0x8")
    ]
    assert len(rows) == 7
    # With the GPRs already full, Ghidra puts the ninth float on the stack too.
    assert storage_problems(proto(*["int"] * 8, *["float"] * 9)) == []
