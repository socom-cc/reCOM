from __future__ import annotations

import pytest

from tools._socom import repairs
from tools._socom.util import SocomError


class _Bridge:
    def __init__(self, wrong: bool = True) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.state = {}
        for function in repairs.REPAIRS[repairs.THUNK_REPAIR_ID]["functions"]:
            restored = not wrong
            self.state[function["address"]] = [function["name"], restored]
            self.state[function["thunk"]] = [function["thunk_name"], restored, function["address"]]

    def request(self, endpoint, **parameters):
        assert endpoint == "get_function_by_address"
        name, restored, *target = self.state[parameters["address"]]
        if target:
            restored = self.state[target[0]][1]
        signature = f"undefined __stdcall {name}(void)" if restored else f"void __stdcall {name}(COurGame * this)"
        return "\n".join([f"Function: {name} at {int(parameters['address'], 16):08x}", f"Signature: {signature}"])

    def post_json(self, endpoint, **body):
        self.calls.append((endpoint, body))
        assert endpoint == "set_function_prototype"
        assert body["prototype"] == "undefined socom_prototype(void)" and body["calling_convention"] == "__stdcall"
        self.state[body["function_address"]][1] = True
        return f"Successfully set prototype for function at {body['function_address']}"


def test_repair_restores_targets_and_thunks() -> None:
    bridge = _Bridge()
    result = repairs.repair_signatures(repairs.THUNK_REPAIR_ID, bridge)
    assert [body["function_address"] for _, body in bridge.calls] == ["0x20e790", "0x20e7a0"]
    assert result["receipt_scope"]["functions"] == ["0x140500", "0x140510", "0x20e790", "0x20e7a0"]
    first = result["functions"][0]
    assert first["before"]["0x20e790"] == "void __stdcall StopPlay__5CGameFv(COurGame * this)"
    assert first["after"]["0x140500"] == "undefined __stdcall COurGame::StopPlay(void)"


def test_repair_refuses_any_other_starting_state() -> None:
    bridge = _Bridge(wrong=False)
    with pytest.raises(SocomError, match="not the recorded wrong state"):
        repairs.repair_signatures(repairs.THUNK_REPAIR_ID, bridge)
    assert bridge.calls == []
    with pytest.raises(SocomError, match="no recorded repair"):
        repairs.repair_signatures("socom:work:unknown", bridge)


class _LabelBridge:
    def __init__(self, renamed: bool = True) -> None:
        spec = repairs.REPAIRS[repairs.COPY_NAMES_REPAIR_ID]["labels"]
        self.labels = {row["address"]: ([row["readable"], row["mangled"]] if renamed else [row["mangled"]]) for row in spec}
        self.calls: list[tuple[str, dict]] = []

    def request(self, endpoint, **parameters):
        assert endpoint == "audit_global"
        return {"name": self.labels[parameters["address"]][0], "type": "undefined8", "is_code_address": False}

    def post_json(self, endpoint, **body):
        self.calls.append((endpoint, body))
        assert endpoint == "delete_label" and body["name"]
        names = self.labels[body["address"]]
        deleted = [name for name in names if name == body["name"]]
        self.labels[body["address"]] = [name for name in names if name != body["name"]]
        return {"success": True, "deleted_count": len(deleted), "deleted_names": deleted}


def test_label_repair_deletes_only_the_readable_labels() -> None:
    bridge = _LabelBridge()
    result = repairs.repair_labels(repairs.COPY_NAMES_REPAIR_ID, bridge)
    assert len(bridge.calls) == 10
    assert all(body["name"] for _, body in bridge.calls)
    first = result["labels"][0]
    assert first == {"address": "0x444498", "before": "CGame::__RTTI", "after": "__RTTI__5CGame", "type": "undefined8"}
    assert result["receipt_scope"]["globals"][0] == "0x444498" and len(result["receipt_scope"]["globals"]) == 10


def test_label_repair_refuses_any_other_starting_state() -> None:
    bridge = _LabelBridge(renamed=False)
    with pytest.raises(SocomError, match="not the recorded"):
        repairs.repair_labels(repairs.COPY_NAMES_REPAIR_ID, bridge)
    assert bridge.calls == []
    with pytest.raises(SocomError, match="not a label repair"):
        repairs.repair_labels(repairs.THUNK_REPAIR_ID, bridge)
    with pytest.raises(SocomError, match="not a signature repair"):
        repairs.repair_signatures(repairs.COPY_NAMES_REPAIR_ID, bridge)
