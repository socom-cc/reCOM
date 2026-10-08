from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools._socom import batch_apply
from tools._socom.import_plan import build_import_plan
from tools._socom.tracker import load_tracker
from tools._socom.util import SocomError, canonical_json

BATCH_001 = "socom:debug-batch:cb1cc66c6e35fc967c25"


@pytest.fixture(scope="module")
def batch_plan_path(root: Path, tmp_path_factory) -> Path:
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    item = next(row for row in tracker["work_items"] if row["id"] == BATCH_001)
    plan = build_import_plan(root, {"work_item_id": item["id"], "selection": item["selection"], **item["batch"]})
    path = tmp_path_factory.mktemp("plans") / "batch-001.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def program(root: Path, batch_plan_path: Path) -> dict:
    return batch_apply.build_batch_program(root, batch_plan_path)


def test_readable_names_follow_metrowerks_special_names() -> None:
    name = batch_apply.readable_function_name
    assert name("__dt__10CGameStateFv", "__dt") == "CGameState::~CGameState"
    assert name("__nwa__FUi", "__nwa") == "operator_new[]"
    assert name("main", "main") == "main"
    assert name(None, "main") == "main"
    assert (
        name("__ct__Q23std59basic_string<c,Q23std14char_traits<c>,Q23std12allocator<c>>FRCQ23std12allocator<c>", "__ct")
        == "std::basic_string<char,std::char_traits<char>,std::allocator<char>>::basic_string"
    )


def test_batch_program_is_deterministic_and_fills_prototypes(root: Path, batch_plan_path: Path, program: dict) -> None:
    again = batch_apply.build_batch_program(root, batch_plan_path)
    assert canonical_json(program) == canonical_json(again)
    functions = {row["address"]: row for row in program["functions"]}
    release = functions["0x140460"]
    assert release["readable_name"] == "_zmalloc<four>::release" and release["rename"]
    assert release["prototype"]["parameters"] == [
        {"name": "this", "type": "_zmalloc<four> *"},
        {"name": "_ptr", "type": "void *"},
    ]
    # DWARF records no parameters; the vtable proves the receiver and the
    # mangled name supplies the float.
    tick = functions["0x1410a0"]
    assert tick["receiver"] == "vtable:__vt__10CGameState"
    assert tick["prototype"]["parameters"] == [
        {"name": "this", "type": "CGameState *"},
        {"name": "param_2", "type": "float"},
    ]
    dtor = functions["0x140bc0"]
    assert dtor["prototype"]["parameters"][-1] == {"name": "__dtor_flags", "type": "short"}
    assert functions["0x140d00"]["rename"] is False
    assert batch_apply.prototype_text(functions["0x140d00"]["prototype"]) == "int socom_prototype(int argc, char * * argv)"
    stl = functions["0x1410f0"]
    assert stl["prototype"] is None and "cannot parse" in stl["prototype_skip"]
    globals_ = {row["address"]: row for row in program["globals"]}
    assert globals_["0x476f60"]["type"] == "COurGame" and globals_["0x476f60"]["size"] == 528
    assert globals_["0x50eb00"]["readable_name"] == "zdb::CTexManager::m_texmanager"
    assert globals_["0x4714d0"]["type"] is None and globals_["0x4714d0"]["rename"]
    assert program["summary"]["absent_variable_count"] == 7


class _FakeBridge:
    def __init__(self, program: dict, names: dict[str, str]) -> None:
        self.functions = dict(names)
        self.signatures: dict[str, str] = {}
        self.globals = {row["address"]: {"name": row["current_name"], "type": "", "length": 0} for row in program["globals"]}
        self.code: set[str] = set()
        self.calls: list[tuple[str, dict]] = []

    def post_json(self, endpoint, **body):
        self.calls.append((endpoint, body))
        if endpoint == "rename_function_by_address":
            self.functions[body["function_address"]] = body["new_name"]
            return {"status": "success"}
        if endpoint == "create_label":
            return {"status": "success"}
        if endpoint == "set_function_prototype":
            text = body["prototype"]
            ret, rest = text.split(" socom_prototype(", 1)
            self.signatures[body["function_address"]] = (ret, rest[:-1])
            return "Successfully set prototype"
        if endpoint == "apply_data_type":
            self.globals[body["address"]]["type"] = body["type_name"]
            return "Applied"
        if endpoint == "rename_label":
            self.globals[body["address"]]["name"] = body["new_name"]
            return {"status": "success", "message": "Renamed"}
        raise AssertionError(endpoint)

    def request(self, endpoint, **parameters):
        self.calls.append((endpoint, parameters))
        address = parameters.get("address")
        if endpoint == "audit_global":
            row = self.globals[address]
            return {
                **row,
                "length": 528 if row["type"] == "COurGame" else row["length"],
                "address": address,
                "is_code_address": address in self.code,
                "is_function_entry": False,
            }
        if endpoint == "get_function_by_address":
            name = self.functions[address]
            lines = [f"Function: {name} at {int(address, 16):08x}"]
            if address in self.signatures:
                ret, params = self.signatures[address]
                lines.append(f"Signature: {ret} __stdcall {name}({params})")
            return "\n".join(lines)
        raise AssertionError(endpoint)


def test_batch_executor_renames_types_and_verifies(program: dict) -> None:
    program = copy.deepcopy(program)
    # Keep the fake length model simple: only theGame carries a size.
    for row in program["globals"]:
        if row["address"] != "0x476f60":
            row["size"] = None
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    bridge = _FakeBridge(program, names)
    index = [{"name": name, "path": f"/project/{name}"} for name in ("COurGame", "CGameState", "_zmalloc<four>", "_zmalloc<twelve>", "_options", "CSTable", "CMission", "CTexManager", "_zvid_public", "CZOnlineLobby", "_reent@1aa0a63ac4")]
    result = batch_apply.execute_batch_program(program, bridge, type_index=lambda: index, function_names=lambda: names)
    assert result["ok"] is True
    endpoints = [endpoint for endpoint, _ in bridge.calls]
    assert "delete_label" not in endpoints and not any("delete" in endpoint for endpoint in endpoints)
    assert bridge.functions["0x140bc0"] == "CGameState::~CGameState"
    labels = [body["name"] for endpoint, body in bridge.calls if endpoint == "create_label"]
    assert "__dt__10CGameStateFv" in labels and "m_texmanager__Q23zdb11CTexManager" in labels
    reasons = {(row["address"], row["action"]) for row in result["skipped"]}
    assert ("0x1410f0", "prototype") in reasons and ("0x4714d0", "type") in reasons


def test_batch_executor_skips_ambiguous_types_and_refuses_drift(program: dict) -> None:
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    bridge = _FakeBridge(program, names)
    index = [{"name": "COurGame"}, {"name": "courgame"}]
    result = batch_apply.execute_batch_program(
        copy.deepcopy(program), bridge, type_index=lambda: index, function_names=lambda: names
    )
    reasons = [row["reason"] for row in result["skipped"] if row["address"] == "0x476f60"]
    assert reasons and "resolves 2 times" in reasons[0]
    drifted = dict(names, **{"0x140460": "something_else"})
    with pytest.raises(SocomError, match="expected 'release__15_zmalloc<4four>FPv'"):
        batch_apply.execute_batch_program(
            copy.deepcopy(program), _FakeBridge(program, drifted), type_index=lambda: index, function_names=lambda: drifted
        )


def test_batch_executor_skips_identical_types_and_taken_names_and_refuses_code(program: dict) -> None:
    program = copy.deepcopy(program)
    for row in program["globals"]:
        if row["address"] != "0x476f60":
            row["size"] = None
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    index = [{"name": "COurGame"}, {"name": "CGameState"}, {"name": "CMission"}]
    bridge = _FakeBridge(program, names)
    bridge.globals["0x476f60"]["type"] = "COurGame"  # a previous batch typed theGame
    result = batch_apply.execute_batch_program(
        copy.deepcopy(program),
        bridge,
        type_index=lambda: index,
        function_names=lambda: names,
        global_names=lambda: {"CGameState::__vt": {"0x999990"}},
    )
    assert {"address": "0x476f60", "action": "type", "type": "COurGame"} in result["unchanged"]
    assert not any(body.get("address") == "0x476f60" for endpoint, body in bridge.calls if endpoint == "apply_data_type")
    clash = [row for row in result["skipped"] if row["address"] == "0x4714d0" and row["action"] == "rename"]
    assert clash and clash[0]["reason"] == "name already used at 0x999990"
    assert bridge.globals["0x4714d0"]["name"] == "__vt__10CGameState"
    code = _FakeBridge(program, names)
    code.code.add("0x4bc600")
    with pytest.raises(SocomError, match="0x4bc600 is code"):
        batch_apply.execute_batch_program(
            copy.deepcopy(program), code, type_index=lambda: index, function_names=lambda: names
        )


def test_batch_program_folds_unit_copies_and_refuses_code_globals(root: Path, batch_plan_path: Path, tmp_path: Path) -> None:
    plan = json.loads(batch_plan_path.read_text(encoding="utf-8"))
    the_game = next(row for row in plan["variables"] if row["name"] == "theGame")
    same = copy.deepcopy(the_game)
    same["evidence"] = dict(same["evidence"], die_offset=999_999)
    path = tmp_path / "same.json"
    path.write_text(json.dumps(dict(plan, variables=[*plan["variables"], same])), encoding="utf-8")
    folded = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["globals"]}
    assert folded["0x476f60"]["type"] == "COurGame"
    other = dict(copy.deepcopy(the_game), type={"die_offset": None, "fund_type": 7, "modifiers": []})
    path.write_text(json.dumps(dict(plan, variables=[*plan["variables"], other])), encoding="utf-8")
    disagree = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["globals"]}["0x476f60"]
    assert disagree["type"] is None and "disagree" in disagree["type_skip"]
    inside = dict(copy.deepcopy(the_game), address=0x140464, name="bogus")
    path.write_text(json.dumps(dict(plan, variables=[*plan["variables"], inside])), encoding="utf-8")
    with pytest.raises(SocomError, match="inside function"):
        batch_apply.build_batch_program(root, path)


def test_batch_types_complete_open_arrays_from_symbol_sizes(program: dict) -> None:
    types = batch_apply._Types(
        {
            "types": [
                {"evidence": {"die_offset": 1}, "kind": "enumeration_type", "byte_size": 1, "ghidra_path": "/project/EQUIP_ITEM"},
                {
                    "evidence": {"die_offset": 2},
                    "kind": "array_type",
                    "byte_size": None,
                    "ghidra_path": None,
                    "array": {"dimensions": [["fund", 10, 0, -1]], "element": {"die_offset": 1, "fund_type": None, "modifiers": []}},
                },
                {
                    "evidence": {"die_offset": 3},
                    "kind": "array_type",
                    "byte_size": None,
                    "ghidra_path": None,
                    "array": {"dimensions": [["fund", 10, 0, 3]], "element": {"die_offset": None, "fund_type": 1, "modifiers": ["pointer_to"]}},
                },
            ]
        }
    )
    open_array = {"die_offset": 2, "fund_type": None, "modifiers": []}
    # aiDeployList__11CSealCtrlAi: DWARF EQUIP_ITEM[0..-1], .symtab size 11.
    assert types.render(open_array, 11) == ("EQUIP_ITEM[11]", None)
    assert types.byte_size(open_array, 11) == 11
    assert types.render(open_array)[0] is None and "open extent" in types.render(open_array)[1]
    # extern EQUIP_ITEM (*p)[]: the 4-byte symbol is the pointer, not the array.
    pointer_to_open = dict(open_array, modifiers=["pointer_to"])
    assert types.render(pointer_to_open, 4)[0] is None
    pointers = {"die_offset": 3, "fund_type": None, "modifiers": []}
    assert types.render(pointers) == ("char *[4]", None) and types.byte_size(pointers) == 16
    const = {"die_offset": None, "fund_type": 8, "modifiers": ["const"]}
    assert types.render(const)[0] is None and "'const'" in types.render(const)[1]


def test_batch_executor_skips_undefined_multidimensional_arrays(program: dict) -> None:
    program = copy.deepcopy(program)
    for row in program["globals"]:
        row["size"] = None
        if row["address"] == "0x476f60":
            row["type"] = "COurGame[2][3]"
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    index = [{"name": "COurGame"}, {"name": "CGameState"}]
    result = batch_apply.execute_batch_program(
        program, _FakeBridge(program, names), type_index=lambda: index, function_names=lambda: names
    )
    reasons = [row["reason"] for row in result["skipped"] if row["address"] == "0x476f60"]
    assert reasons and "multi-dimensional" in reasons[0]


BATCH_11 = "socom:debug-batch:1c9907d6eef3a9fccef6"


def test_parameter_shapes_compare_depth_kind_and_names() -> None:
    compatible = batch_apply._compatible
    font = (1, "class", None, 52, frozenset({"C2DFont"}))
    assert compatible(font, (1, "class", None, None, frozenset({"C2DFont"})))
    assert not compatible(font, (1, "class", None, None, frozenset({"zdb::CWorld"})))
    assert not compatible(font, (0, "class", None, None, frozenset({"C2DFont"})))
    # DWARF spells bool as a one-byte fundamental.
    assert compatible((0, "builtin", "uchar", 1, frozenset()), (0, "builtin", "bool", 1, frozenset()))
    assert not compatible((1, "builtin", "char", 1, frozenset()), (0, "builtin", "int", 4, frozenset()))
    assert compatible(None, font) and compatible(font, None)


def test_partial_dwarf_parameters_align_to_the_mangled_signature(root: Path, tmp_path: Path) -> None:
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    item = next(row for row in tracker["work_items"] if row["id"] == BATCH_11)
    plan = build_import_plan(root, {"work_item_id": item["id"], "selection": item["selection"], **item["batch"]})
    path = tmp_path / "batch-011.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    functions = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["functions"]}
    # LoadTextures__10OrdersMenuFPQ23zdb6CWorldP7C2DFont: DWARF records only font.
    load = functions["0x1772a0"]["prototype"]["parameters"]
    assert [(p["name"], p["type"]) for p in load] == [("this", "OrdersMenu *"), ("param_2", "CWorld *"), ("font", "C2DFont *")]
    # HandleRecoCmd__10OrdersMenuFiiiiPc: three of four ints recorded, so
    # only lastString has one possible position.
    reco = functions["0x176e60"]["prototype"]["parameters"]
    assert [p["type"] for p in reco] == ["OrdersMenu *", "int", "int", "int", "int", "char *"]
    assert [p["name"] for p in reco][1:] == ["param_2", "param_3", "param_4", "param_5", "lastString"]
    # A class named only by the mangled signature reaches the plan.
    parse = functions["0x174a70"]["prototype"]["parameters"]
    assert parse[1]["type"] == "_zrdr *"
