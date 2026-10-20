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
    # SetPosition ends after an indirect call, so v0 holds that call's result: open.
    row = {"address": "0x227200", "elf_names": ["SetPosition__Q23zdb5CNodeFfff"], "stage2": None, "thunk_target": None}
    assert draft_function(ctx, row, "zdb::CNode::SetPosition", _types("CNode"))["draft"] == "open"


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


def test_hand_written_rows_are_checked_in_substance(ctx) -> None:
    row = {"address": "0x46b9d0", "elf_names": ["__sinit_zrdr_archive.cpp"], "stage2": None, "thunk_target": None}
    drafted = draft_function(ctx, row, "__sinit_zrdr_archive.cpp", _types())
    hand = {"address": "0x46b9d0", "current_name": "__sinit_zrdr_archive.cpp",
            "prototype": {"return_type": "void", "parameters": [], "evidence": ["written before rules v3"]}}
    assert check_drafted_rows({"functions": [drafted]}, {"functions": [hand]}) == []
    hand["prototype"]["return_type"] = "int"
    assert "disagrees" in check_drafted_rows({"functions": [drafted]}, {"functions": [hand]})[0]
