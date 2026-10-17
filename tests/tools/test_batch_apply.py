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


def test_function_template_arguments_are_demangled_in_readable_names() -> None:
    mangled = "__use_facet<Q23std14codecvt<w,c,i>>__3stdFRCQ23std6localeQ23std12__chooser<1>"
    assert batch_apply.readable_function_name(mangled, None) == "std::__use_facet<std::codecvt<wchar_t,char,int>>"
    assert batch_apply.readable_function_name("__use_facet<Q23std8ctype<c>>__3stdFRCQ23std6locale", None) == (
        "std::__use_facet<std::ctype<char>>"
    )


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


def test_batch_executor_dry_run_records_the_same_calls_without_writing(program: dict) -> None:
    program = copy.deepcopy(program)
    for row in program["globals"]:
        if row["address"] != "0x476f60":
            row["size"] = None
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    index = [{"name": name, "path": f"/project/{name}"} for name in ("COurGame", "CGameState", "_options", "CMission")]
    real = _FakeBridge(program, names)
    applied = batch_apply.execute_batch_program(copy.deepcopy(program), real, type_index=lambda: index, function_names=lambda: names)

    class _NoWrites(_FakeBridge):
        def post_json(self, endpoint, **body):
            raise AssertionError(f"dry run wrote {endpoint}")

    dry = batch_apply.execute_batch_program(
        copy.deepcopy(program), _NoWrites(program, names), type_index=lambda: index, function_names=lambda: names, dry_run=True
    )
    writes = [(endpoint, body) for endpoint, body in real.calls if endpoint not in ("audit_global", "get_function_by_address")]
    assert dry["dry_run"] is True and dry["bridge_call_count"] == applied["bridge_call_count"] == len(writes)
    assert [(step["endpoint"], step["body"]) for step in dry["steps"]] == writes
    assert dry["skipped"] == applied["skipped"] and dry["unchanged"] == applied["unchanged"]
    assert sum(dry["planned_calls"].values()) == len(writes)


def test_batch_scope_check_flags_writes_outside_and_scope_beyond_the_program() -> None:
    from tools._socom import cli

    program = {
        "receipt_scope": {"functions": ["0x140460", "0x140500"], "globals": ["0x476f60"]},
        "functions": [{"address": "0x140460"}],
        "globals": [{"address": "0x476f60"}],
    }
    result = {
        "steps": [
            {"endpoint": "rename_function_by_address", "body": {"function_address": "0x140460"}},
            {"endpoint": "apply_data_type", "body": {"address": "0x476f60"}},
            {"endpoint": "create_label", "body": {"address": "0x476f64"}},
        ]
    }
    assert cli._batch_scope_problems(program, result) == [
        "create_label writes 0x476f64 outside the receipt scope",
        "scope function 0x140500 is not in the program",
    ]
    program["receipt_scope"]["types"] = ["/project/A", "/project/B"]
    assert cli._batch_scope_problems(program, result, {"/project/A"})[0] == "scope type /project/B does not exist live"


def test_vtable_receivers_with_unparseable_type_names_are_skipped(root: Path, tmp_path: Path) -> None:
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    item = next(row for row in tracker["work_items"] if row["id"] == "socom:debug-batch:c433a303fc78c05392db")
    plan = build_import_plan(root, {"work_item_id": item["id"], "selection": item["selection"], **item["batch"]})
    path = tmp_path / "batch-003.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    functions = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["functions"]}
    # basic_streambuf<wchar_t>::sync has its receiver from the vtable, whose
    # class name has a comma the bridge would split the prototype at.
    sync = functions["0x145af0"]
    assert sync["receiver"].startswith("vtable:") and sync["prototype"] is None
    assert "cannot parse" in sync["prototype_skip"] and sync["rename"]
    assert not any(
        batch_apply.UNSPELLABLE.search(param["type"])
        for row in functions.values()
        if row["prototype"]
        for param in row["prototype"]["parameters"]
    )


def test_executor_refuses_an_unparseable_prototype_before_writing(program: dict) -> None:
    program = copy.deepcopy(program)
    entry = next(row for row in program["functions"] if row.get("prototype"))
    entry["prototype"]["parameters"][0]["type"] = "basic_streambuf<char, std::char_traits<char>> *"
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    bridge = _FakeBridge(program, names)
    with pytest.raises(SocomError, match="cannot parse"):
        batch_apply.execute_batch_program(program, bridge, type_index=lambda: [], function_names=lambda: names)
    assert bridge.calls == []


def test_globals_typed_differently_by_an_accepted_apply_are_conflicts(program: dict) -> None:
    program = copy.deepcopy(program)
    for row in program["globals"]:
        if row["address"] != "0x476f60":
            row["size"] = None
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    index = [{"name": name, "path": f"/project/{name}"} for name in ("COurGame", "CGameState", "_options", "CMission", "COurGameOld")]

    def run(accepted: frozenset[str]) -> tuple[dict, _FakeBridge]:
        bridge = _FakeBridge(program, names)
        bridge.globals["0x476f60"]["type"] = "COurGameOld"
        result = batch_apply.execute_batch_program(
            copy.deepcopy(program), bridge, type_index=lambda: index, function_names=lambda: names,
            dry_run=True, accepted_globals=accepted,
        )
        return result, bridge

    result, _ = run(frozenset({"0x476f60"}))
    conflicts = [row for row in result["skipped"] if row["address"] == "0x476f60" and row["action"] == "type"]
    assert conflicts and "conflicts with 'COurGameOld'" in conflicts[0]["reason"]
    assert not any(step["body"].get("address") == "0x476f60" and step["endpoint"] == "apply_data_type" for step in result["steps"])
    # Outside any accepted scope, or over an undefined placeholder or a type
    # Ghidra's analysis chose, the type applies.
    result, _ = run(frozenset())
    assert any(step["body"].get("address") == "0x476f60" and step["endpoint"] == "apply_data_type" for step in result["steps"])
    bridge = _FakeBridge(program, names)
    bridge.globals["0x476f60"]["type"] = "pointer"
    result = batch_apply.execute_batch_program(
        copy.deepcopy(program), bridge, type_index=lambda: index, function_names=lambda: names,
        dry_run=True, accepted_globals=frozenset({"0x476f60"}),
    )
    assert any(step["body"].get("address") == "0x476f60" and step["endpoint"] == "apply_data_type" for step in result["steps"])


def test_accepted_scope_globals_come_from_accepted_applies_only() -> None:
    from tools._socom import cli

    batch = "debug-import-apply-batch"
    tracker = {
        "work_items": [
            {"id": "a-apply", "kind": batch, "status": "accepted", "ghidra_receipt": {"scope": {"globals": ["0x0043bf74", ".debug::10"]}}},
            {"id": "b-apply", "kind": batch, "status": "awaiting_acceptance", "ghidra_receipt": {"scope": {"globals": ["0x476f60"]}}},
            {"id": "c-apply", "kind": batch, "status": "accepted", "ghidra_receipt": {"scope": {"globals": ["0x475604"]}}},
            {"id": "zero-fill", "kind": "ghidra-memory-map", "status": "accepted", "ghidra_receipt": {"scope": {"globals": ["0x475608"]}}},
            {"id": "d", "status": "accepted"},
        ]
    }
    assert cli._accepted_scope_globals(tracker, "c-apply") == frozenset({"0x43bf74"})


def test_composite_typedef_with_a_missing_target_fails_closed() -> None:
    types = batch_apply._Types(
        {
            "types": [
                {"kind": "typedef", "type": {"die_offset": 0x99}, "evidence": {"die_offset": 0x10}},
                {"kind": "structure_type", "evidence": {"die_offset": 0x20}},
                {"kind": "typedef", "type": {"die_offset": 0x20}, "evidence": {"die_offset": 0x30}},
                {"kind": "enumeration_type", "evidence": {"die_offset": 0x40}},
            ]
        }
    )
    assert types.composite({"die_offset": 0x10}) is True
    assert types.composite({"die_offset": 0x30}) is True
    assert types.composite({"die_offset": 0x40}) is False
    assert types.composite({"die_offset": 0x77}) is False
    assert types.composite({"die_offset": 0x30, "modifiers": ["P"]}) is False


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
    void_typedef = {
        "evidence": {"die_offset": 999_001}, "kind": "typedef", "ghidra_path": "/project/VOIDT", "byte_size": None,
        "type": {"die_offset": None, "fund_type": 0x14, "modifiers": []}, "array": None, "members": [],
    }
    unsized = {
        "evidence": {"die_offset": 999_002}, "kind": "array_type", "ghidra_path": None, "byte_size": None, "members": [],
        "array": {"dimensions": [["fund", 10, 0, 5]], "element": {"die_offset": 999_001, "fund_type": None, "modifiers": []}},
    }
    variables = [
        dict(row, type={"die_offset": 999_002, "fund_type": None, "modifiers": []}) if row is the_game else row
        for row in plan["variables"]
    ]
    path.write_text(json.dumps(dict(plan, types=[*plan["types"], void_typedef, unsized], variables=variables)), encoding="utf-8")
    unsized_row = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["globals"]}["0x476f60"]
    assert unsized_row["type"] is None and "no computable DWARF extent" in unsized_row["type_skip"]
    function_type = {
        "evidence": {"die_offset": 999_003}, "kind": "subroutine_type", "ghidra_path": None, "byte_size": None,
        "structural_class": "socom:type-class:427123976b517c446fad", "members": [], "array": None,
        "type": {"die_offset": None, "fund_type": 0x14, "modifiers": []},
    }
    for modifiers, expected in ((["pointer_to", "pointer_to"], "@subroutine@427123976b * *"), ([], None)):
        variables = [
            dict(row, type={"die_offset": 999_003, "fund_type": None, "modifiers": modifiers}) if row is the_game else row
            for row in plan["variables"]
        ]
        path.write_text(json.dumps(dict(plan, types=[*plan["types"], function_type], variables=variables)), encoding="utf-8")
        if expected is None:
            with pytest.raises(SocomError, match="as a function"):
                batch_apply.build_batch_program(root, path)
        else:
            # g_syncCallback: void (**)(), a pointer to a function pointer, is data.
            row = {item["address"]: item for item in batch_apply.build_batch_program(root, path)["globals"]}["0x476f60"]
            assert row["type"] == expected
    wide = {
        "evidence": {"die_offset": 999_004}, "kind": "array_type", "ghidra_path": None, "byte_size": None, "members": [],
        "array": {"dimensions": [["fund", 10, 0, 511]], "element": {"die_offset": None, "fund_type": 0xA510, "modifiers": []}},
    }
    variables = [
        dict(row, type={"die_offset": 999_004, "fund_type": None, "modifiers": []}) if row is the_game else row
        for row in plan["variables"]
    ]
    path.write_text(json.dumps(dict(plan, types=[*plan["types"], wide], variables=variables)), encoding="utf-8")
    wide_row = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["globals"]}["0x476f60"]
    # g_buffer (batch 35): apply_data_type would write ushort[512] over 8192 bytes.
    assert wide_row["type"] is None and "apply_data_type" in wide_row["type_skip"]
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
    nested = batch_apply._Types(
        {
            "types": [
                {
                    "evidence": {"die_offset": 4},
                    "kind": "array_type",
                    "byte_size": None,
                    "ghidra_path": None,
                    "array": {"dimensions": [["fund", 10, 0, 2]], "element": {"die_offset": None, "fund_type": 8, "modifiers": []}},
                },
                {
                    "evidence": {"die_offset": 5},
                    "kind": "array_type",
                    "byte_size": None,
                    "ghidra_path": None,
                    "array": {"dimensions": [["fund", 10, 0, 16]], "element": {"die_offset": 4, "fund_type": None, "modifiers": []}},
                },
            ]
        }
    )
    # zdb::CTexManager::TexPhase: 17 elements of int[3], spelled outer first.
    assert nested.render({"die_offset": 5, "fund_type": None, "modifiers": []}) == ("int[17][3]", None)
    assert nested.byte_size({"die_offset": 5, "fund_type": None, "modifiers": []}) == 204
    const = {"die_offset": None, "fund_type": 8, "modifiers": ["const"]}
    assert types.render(const)[0] is None and "'const'" in types.render(const)[1]
    voids = batch_apply._Types(
        {
            "types": [
                {
                    "evidence": {"die_offset": 6},
                    "kind": "array_type",
                    "byte_size": None,
                    "ghidra_path": None,
                    "array": {"dimensions": [["fund", 10, 0, 5]], "element": {"die_offset": None, "fund_type": 0x14, "modifiers": []}},
                },
            ]
        }
    )
    # c_arrStatFuncs: DWARF void[0..5] over 72 .symtab bytes (member-function pointers).
    void_array = {"die_offset": 6, "fund_type": None, "modifiers": []}
    assert voids.render(void_array, 72) == (None, "array DIE 0x6 has element type void")
    # g_buffer: DWARF u_long128 (0xA510) [0..511]. render() spells it for
    # prototypes (which resolve uint16 correctly); globals skip it, see
    # test_batch_program_folds_unit_copies_and_refuses_code_globals.
    wide = batch_apply._Types(
        {
            "types": [
                {
                    "evidence": {"die_offset": 7},
                    "kind": "array_type",
                    "byte_size": None,
                    "ghidra_path": None,
                    "array": {"dimensions": [["fund", 10, 0, 511]], "element": {"die_offset": None, "fund_type": 0xA510, "modifiers": []}},
                },
            ]
        }
    )
    assert wide.render({"die_offset": 7, "fund_type": None, "modifiers": []}, 8192) == ("uint16[512]", None)


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


def test_batch_executor_refuses_bridge_aliased_global_types(program: dict) -> None:
    program = copy.deepcopy(program)
    for row in program["globals"]:
        if row["address"] == "0x476f60":
            row["type"] = "uint16[2]"
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    with pytest.raises(SocomError, match="apply_data_type would resolve"):
        batch_apply.execute_batch_program(
            program, _FakeBridge(program, names), type_index=lambda: [], function_names=lambda: names
        )


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


def test_mangled_wchar_t_matches_dwarf_unsigned_short() -> None:
    shape = batch_apply._Types.mangled_shape({"modifiers": ["P"], "kind": "builtin", "name": "wchar_t"})
    assert shape == (1, "builtin", "ushort", 2, frozenset())
    assert batch_apply._compatible((1, "builtin", "ushort", 2, frozenset()), shape)
    assert batch_apply._compatible((0, "builtin", "schar", 1, frozenset()), batch_apply._Types.mangled_shape({"modifiers": [], "kind": "builtin", "name": "signed char"}))


def test_thunk_prototypes_are_skipped(program: dict) -> None:
    functions = {row["address"]: row for row in program["functions"]}
    # COurGame::StopPlay is `j StopPlay__5CGameFv; nop`: a Ghidra thunk whose
    # signature is its target's.
    stop = functions["0x140500"]
    assert stop["prototype"] is None and stop["prototype_skip"].startswith("thunk of 0x20e790")
    assert stop["rename"] is True


def test_only_the_vtable_rtti_copy_takes_the_readable_name(program: dict) -> None:
    globals_ = {row["address"]: row for row in program["globals"]}
    # __RTTI__10CGameState has six file-local copies; __vt__10CGameState's
    # first word points at 0x444578.
    assert globals_["0x444578"]["rename"] and "rename_skip" not in globals_["0x444578"]
    cgame = globals_["0x444498"]
    assert not cgame["rename"] and cgame["rename_skip"] == "file-local copy; the class vtable references 0x44ee28"
    # A single copy keeps its readable name.
    assert globals_["0x4444b0"]["rename"]


def test_by_value_class_returns_are_skipped(root: Path, tmp_path: Path) -> None:
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    item = next(row for row in tracker["work_items"] if row["id"] == "socom:debug-batch:e168f5ec330b2d69ef33")
    plan = build_import_plan(root, {"work_item_id": item["id"], "selection": item["selection"], **item["batch"]})
    path = tmp_path / "batch-017.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    functions = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["functions"]}
    # CAppCamera::GetThirdPersonCamPos returns CPnt3D: Metrowerks passes the
    # result pointer in a0 ahead of this; Ghidra would model it differently.
    third = functions["0x1ead60"]
    assert third["prototype"] is None and third["prototype_skip"].startswith("by-value class")
    assert third["rename"]
    assert functions["0x1eafc0"]["prototype"] is None
    # Pointer returns and enum returns are unaffected.
    assert functions["0x1ec580"]["prototype"]["return_type"] == "IntersectStruct *"


def test_void_returns_contradicted_by_a_caller_are_detected(root: Path) -> None:
    from tools._socom.elf import Elf32File

    elf = Elf32File(root / "support" / "socom.elf")
    # TestFOV calls sceVu0ClipBBox (DWARF void) and stores v0 into *clipWord.
    assert batch_apply._return_read_site(elf, {0x1E87E0: [0x1E4D5C]}, {0x1E4D5C: 0x1E4E00}, 0x1E87E0) == (
        0x1E4D5C,
        0x1E4D64,
        "v0",
    )
    # After OrdersMenu::ScrollBack the caller runs mov.s $f12,$f20: ft is an
    # unused 0, not a read of f0.
    assert batch_apply._return_read_site(elf, {0x174E40: [0x176C58]}, {0x176C58: 0x176CE0}, 0x174E40) is None
    assert batch_apply._reads(0x4600A306) == (set(), {20})
    assert batch_apply._reads(0xAE620000) == ({2, 19}, set())


def test_functions_with_file_local_copies_keep_mangled_names(root: Path, batch_plan_path: Path, tmp_path: Path) -> None:
    plan = json.loads(batch_plan_path.read_text(encoding="utf-8"))
    mangled = "IOPRebootHandler__FQ211CIOPManager11RebootPhaseQ211CIOPManager10RebootModePv"
    row = dict(
        copy.deepcopy(next(f for f in plan["functions"] if f["low_pc"] == 0x140D00)),
        low_pc=0x2EE360,
        mangled_name=mangled,
        name="IOPRebootHandler",
        parameters=[],
    )
    path = tmp_path / "copies.json"
    path.write_text(json.dumps(dict(plan, functions=[*plan["functions"], row])), encoding="utf-8")
    entry = {f["address"]: f for f in batch_apply.build_batch_program(root, path)["functions"]}["0x2ee360"]
    assert entry["rename"] is False and entry["rename_skip"] == "file-local copies share this name"


def test_globals_renamed_by_an_earlier_batch_are_unchanged(program: dict) -> None:
    program = copy.deepcopy(program)
    for row in program["globals"]:
        if row["address"] != "0x476f60":
            row["size"] = None
    names = {row["address"]: row["current_name"] for row in program["functions"]}
    bridge = _FakeBridge(program, names)
    # zdb::CTexManager::m_texmanager was renamed when its first unit applied.
    bridge.globals["0x50eb00"]["name"] = "zdb::CTexManager::m_texmanager"
    index = [{"name": "COurGame"}, {"name": "CGameState"}, {"name": "CTexManager"}]
    result = batch_apply.execute_batch_program(program, bridge, type_index=lambda: index, function_names=lambda: names)
    assert {"address": "0x50eb00", "action": "rename", "name": "zdb::CTexManager::m_texmanager"} in result["unchanged"]
    assert not any(
        body.get("address") == "0x50eb00" for endpoint, body in bridge.calls if endpoint in ("rename_label", "create_label")
    )
    with pytest.raises(SocomError, match="expected 'gopt'"):
        drifted = _FakeBridge(program, names)
        drifted.globals["0x438750"]["name"] = "something_else"
        batch_apply.execute_batch_program(program, drifted, type_index=lambda: index, function_names=lambda: names)


def test_linker_labels_are_not_typed_as_globals(root: Path, batch_plan_path: Path, tmp_path: Path) -> None:
    plan = json.loads(batch_plan_path.read_text(encoding="utf-8"))
    gp = dict(
        copy.deepcopy(next(row for row in plan["variables"] if row["name"] == "theGame")),
        name="_gp",
        address=0x47CBF0,
        symbols=["EER27", "_gp"],
        symbol_qualified_names=[],
        type={"die_offset": None, "fund_type": 20, "modifiers": ["pointer_to"]},
    )
    path = tmp_path / "gp.json"
    path.write_text(json.dumps(dict(plan, variables=[*plan["variables"], gp])), encoding="utf-8")
    entry = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["globals"]}["0x47cbf0"]
    assert entry["skip"].startswith("only zero-size linker labels") and not entry["rename"] and entry["type"] is None


def test_entry_argument_reads_contradict_undeclared_parameters(root: Path) -> None:
    from tools._socom.elf import Elf32File

    elf = Elf32File(root / "support" / "socom.elf")
    # @8@72@__dt__Q23std39basic_ostream<c,...>Fv adjusts this: lw t9,0x48(a0);
    # addiu a0,a0,-8; j dtor; addu a0,a0,t9. DWARF calls it void(void).
    assert batch_apply._entry_argument_reads(elf, 0x14CA80, 16) == ({4}, set())
    # CAppCamera::TickCameraWiggle(this, float dT, CCamera *cam): a0, a1, f12.
    assert batch_apply._entry_argument_reads(elf, 0x1EA710, 64) == ({4, 5}, {12})
    prototype = {"parameters": [{"type": "CAppCamera *"}, {"type": "float"}, {"type": "CCamera *"}]}
    assert batch_apply._declared_argument_registers(prototype) == ({4, 5}, {12})
    assert batch_apply._declared_argument_registers({"parameters": []}) == (set(), set())


def test_entry_read_model_handles_vu_loads_regimm_and_conditional_moves() -> None:
    # lqc2 vf1, 0(a0) loads a VU register: no general register is written.
    assert batch_apply._writes(0xD8810000) == (set(), set())
    # mtsab t5, 0 (REGIMM rt=0x18) is not a branch; bltz/bgezal are.
    assert not batch_apply._is_control_transfer(0x05B80000)
    assert batch_apply._is_control_transfer(0x04800004)  # bltz a0
    assert batch_apply._is_control_transfer(0x04910004)  # bgezal a0 (links ra)
    assert batch_apply._writes(0x04910004) == ({31}, set())
    # movz v0, a1, a2 may keep v0: no definite write.
    assert batch_apply._writes(0x00A6100A) == (set(), set())


def test_adjustor_thunks_with_void_dwarf_are_skipped(root: Path, tmp_path: Path) -> None:
    tracker = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    item = next(row for row in tracker["work_items"] if row["id"] == "socom:debug-batch:b6704b7329debaa2ba1f")
    plan = build_import_plan(root, {"work_item_id": item["id"], "selection": item["selection"], **item["batch"]})
    path = tmp_path / "batch-008.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    functions = {row["address"]: row for row in batch_apply.build_batch_program(root, path)["functions"]}
    for address in ("0x14ca80", "0x14ca90", "0x14caa0", "0x14cab0"):
        assert functions[address]["prototype"] is None
        assert functions[address]["prototype_skip"] == "the entry block reads a0, which the prototype does not declare"
    # A full DWARF prototype that reads exactly its parameters still applies.
    assert functions["0x14cc70"]["prototype"]["return_type"] == "void *"


def test_thunk_target_needs_a_bare_jump_and_nop(root: Path) -> None:
    from tools._socom.elf import Elf32File

    elf = Elf32File(root / "support" / "socom.elf")
    assert batch_apply._thunk_target(elf, 0x140500, 8) == 0x20E790
    # BitmapReticule::Off: a DWARF-backed thunk a later batch would reach.
    assert batch_apply._thunk_target(elf, 0x3CE4C0, 8) is not None
    # C2D::GetZAnimCmdType tail-calls with a0 set in its delay slot.
    assert batch_apply._thunk_target(elf, 0x174B10, 8) is None
    assert batch_apply._thunk_target(elf, 0x140500, 12) is None


def test_data_alias_problem_covers_the_bridge_well_known_table() -> None:
    # apply_data_type maps these through GhidraMCP's well-known-type table.
    for name in ("uint16[512]", "int16", "uint16 *", "uint16_t", "size_t", "BOOL", "WORD *", "Bool[3]", "qword"):
        assert batch_apply._data_alias_problem(name), name
    # The builtins batch programs mean resolve to themselves; project types are untouched.
    for name in ("int", "uint", "char *", "uchar", "ushort[2]", "float[180]", "double", "void *", "longlong", "ulonglong", "CSTable", "PNT2D"):
        assert batch_apply._data_alias_problem(name) is None, name
