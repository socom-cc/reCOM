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
            return {**row, "length": 528 if row["type"] == "COurGame" else row["length"], "address": address}
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
