from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from tools._socom import type_apply
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.util import SocomError, canonical_json


def _loc(offset: int) -> str:
    return "04" + offset.to_bytes(4, "little").hex() + "07"


def _member(name, offset, *, fund=None, die=None, mods=(), tag="member", bit=None, width=None):
    return {
        "bit_offset": bit,
        "bit_size": width,
        "byte_size": None,
        "die_offset": 0,
        "location": _loc(offset),
        "name": name,
        "tag": tag,
        "type": {"die_offset": die, "fund_type": fund, "modifiers": list(mods)},
    }


def _row(die, kind, *, path=None, size=None, members=(), cls=None, declaration=False, raw=None, array=None, type_=None, attributes=None):
    return {
        "anonymous": path is None,
        "array": array,
        "byte_size": size,
        "declaration": declaration,
        "evidence": {"attributes": attributes or {}, "die_offset": die, "tag": kind},
        "ghidra_path": path,
        "kind": kind,
        "members": list(members),
        "raw_name": raw,
        "structural_class": cls or f"socom:type-class:{die:020x}",
        "type": type_,
    }


def _plan(tmp_path: Path) -> Path:
    enum_block = (
        (255).to_bytes(1, "little") + b"NONE\x00" + (0).to_bytes(1, "little") + b"FIRST\x00"
    ).hex()
    types = [
        _row(10, "enumeration_type", path="/project/KIND", size=1, attributes={"element_list": {"form": "block4", "value": enum_block}}),
        _row(20, "class_type", path="/project/Empty", size=1),
        _row(30, "class_type", path="/project/Vbase", size=4),
        _row(40, "class_type", path="/project/Point", size=12, members=[_member("x", 0, fund=0x0E), _member("y", 4, fund=0x0E), _member("z", 8, fund=0x0E)]),
        _row(50, "array_type", array={"dimensions": [["fund", 10, 0, 2]], "element": {"die_offset": 40, "fund_type": None, "modifiers": []}}),
        _row(60, "subroutine_type", type_={"die_offset": None, "fund_type": 0x08, "modifiers": []}),
        # Bitfields after a byte member start at an unaligned byte (C2D).
        _row(
            70,
            "class_type",
            path="/project/Flags",
            size=12,
            members=[
                _member(None, 0, die=30, tag="inheritance"),
                _member("m_byte", 4, fund=0x03),
                _member("first", 5, fund=0x09, bit=0, width=1),
                _member("second", 5, fund=0x09, bit=1, width=1),
                _member("wide", 8, fund=0x09, bit=0, width=26),
            ],
        ),
        # A pure union, a partial-overlap helper union, and an empty base.
        _row(80, "class_type", path="/project/Word", size=4, members=[_member("i", 0, fund=0x08), _member("f", 0, fund=0x0E)]),
        _row(
            90,
            "class_type",
            path="/project/Owner",
            size=48,
            members=[
                _member(None, 0, die=20, tag="inheritance"),
                _member("kind", 0, die=10),
                _member("a", 4, fund=0x08),
                _member("b", 4, die=40, mods=["pointer_to"]),
                _member("points", 8, die=50),
                _member("callback", 44, die=60, mods=["pointer_to"]),
            ],
        ),
        # Virtual base listed at 0 and placed as a member; a void extent.
        _row(
            100,
            "class_type",
            path="/project/Stream",
            size=40,
            members=[
                _member(None, 0, die=40, tag="inheritance"),
                _member("count", 4, fund=0x0B),
                _member("Point", 12, die=40),
                _member("pmf", 24, fund=0x14),
                _member("packet", 36, fund=0xA510, mods=["pointer_to"]),
            ],
        ),
        _row(110, "class_type", path="/project/Forward", declaration=True),
        # A one-byte class holding a one-byte enum (CGameName).
        _row(120, "class_type", path="/project/Byte", size=1, members=[_member("kind", 0, die=10)]),
        # float m[2][3]: the bridge parses one dimension only.
        _row(130, "array_type", array={"dimensions": [["fund", 10, 0, 1], ["fund", 10, 0, 2]], "element": {"die_offset": None, "fund_type": 0x0E, "modifiers": []}}),
        _row(140, "class_type", path="/project/Matrix", size=24, members=[_member("m", 0, die=130)]),
    ]
    plan = {
        "kind": "socom-ghidra-import-plan",
        "schema_version": 4,
        "batch": {"selection": "types", "work_item_id": "socom:work:debug-type-foundation"},
        "conflicts": [],
        "functions": [],
        "variables": [],
        "target": {"program": "socom.elf", "source_sha256": REFERENCE_SHA256},
        "receipt_scope": {
            "schema_version": 1,
            "functions": [],
            "globals": [],
            "types": sorted(row["ghidra_path"] for row in types if row["ghidra_path"]),
        },
        "types": types,
    }
    path = tmp_path / "build" / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _program(tmp_path: Path) -> dict:
    return type_apply.build_apply_program(tmp_path, _plan(tmp_path))


def _by_path(program: dict) -> dict:
    return {entry["path"]: entry for entry in program["types"]}


def test_translation_is_deterministic_and_covers_the_plan_scope(tmp_path: Path) -> None:
    program = _program(tmp_path)
    again = type_apply.build_apply_program(tmp_path, tmp_path / "build" / "plan.json")
    assert canonical_json(program) == canonical_json(again)
    assert program["plan"]["path"] == "build/plan.json"
    scope = program["receipt_scope"]["types"]
    assert scope == sorted(scope)
    assert set(_by_path(program)) == set(scope)
    assert "/project/anonymous/@subroutine@0000000000" in scope
    assert "/project/Owner/@union@0x4" in scope
    temps = [entry["temp"] for entry in program["types"]]
    assert len(set(temps)) == len(temps)
    assert all(re.fullmatch(r"socom_t_\d{4}", temp) for temp in temps)


def test_bitfields_use_absolute_lsb_positions(tmp_path: Path) -> None:
    entry = _by_path(_program(tmp_path))["/project/Flags"]
    assert entry["route"] == "c"
    vbase = _by_path(_program(tmp_path))["/project/Vbase"]["temp"]
    assert entry["expected_layout"] == [
        [0, 4, vbase, "super_Vbase"],
        [4, 1, "uchar", "m_byte"],
        [5, 1, "uint:1", "first"],
        [5, 1, "uint:1", "second"],
        [5, 1, "uint:6", "(unnamed)"],
        [6, 1, "uchar:8", "(unnamed)"],
        [7, 1, "uchar:8", "(unnamed)"],
        [8, 4, "uint:26", "wide"],
        [11, 1, "uint:6", "(unnamed)"],
    ]
    assert "#pragma pack(push, 1)" in entry["c_source"]
    assert "unsigned int first : 1;" in entry["c_source"]
    assert entry["retypes"] == [{"placeholder": "super_Vbase", "type": vbase, "name": "super_Vbase"}]


def test_overlaps_become_unions_and_bases_are_recorded(tmp_path: Path) -> None:
    program = _program(tmp_path)
    entries = _by_path(program)
    assert entries["/project/Word"]["route"] == "union"
    helper = entries["/project/Owner/@union@0x4"]
    point = entries["/project/Point"]["temp"]
    assert helper["fields"] == [
        {"name": "a", "type": "int", "size": 4},
        {"name": "b", "type": f"{point} *", "size": 4},
    ]
    owner = entries["/project/Owner"]
    fn = entries["/project/anonymous/@subroutine@0000000000"]
    assert owner["route"] == "fields"
    assert owner["expected_layout"] == [
        [0, 1, entries["/project/KIND"]["temp"], "kind"],
        [4, 4, helper["temp"], "(unnamed)"],
        [8, 36, f"{point}[3]", "points"],
        [44, 4, f"{fn['temp']} *", "callback"],
    ]
    assert fn["return_type"] == "int" and fn["parameters"] == "..."
    reasons = {(row["type"], row["reason"].split(":")[0]) for row in program["omissions"]}
    assert ("/project/Owner", "empty base shares its offset (empty-base optimization)") in reasons
    assert ("/project/Stream", "virtual base") in reasons
    stream = entries["/project/Stream"]
    assert stream["route"] == "c"
    assert [4, 8, "longlong", "count"] in stream["expected_layout"]
    assert [24, 12, "undefined1[12]", "pmf"] in stream["expected_layout"]
    assert [36, 4, "uint16 *", "packet"] in stream["expected_layout"]
    assert entries["/project/Forward"]["route"] == "empty"
    assert entries["/project/KIND"]["values"] == [["NONE", -1], ["FIRST", 0]]


def test_definition_order_puts_by_value_dependencies_first(tmp_path: Path) -> None:
    program = _program(tmp_path)
    order = [entry["path"] for entry in program["types"]]
    assert order.index("/project/Point") < order.index("/project/Owner")
    assert order.index("/project/Owner/@union@0x4") < order.index("/project/Owner")


def test_translation_fails_closed(tmp_path: Path) -> None:
    path = _plan(tmp_path)
    plan = json.loads(path.read_text(encoding="utf-8"))
    broken = copy.deepcopy(plan)
    broken["types"][3]["members"][0]["type"]["fund_type"] = 0x1234
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(SocomError, match="unsupported fundamental type"):
        type_apply.build_apply_program(tmp_path, path)
    broken = copy.deepcopy(plan)
    broken["types"][3]["members"][1]["location"] = _loc(2)
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(SocomError, match="not a plain union"):
        type_apply.build_apply_program(tmp_path, path)
    broken = copy.deepcopy(plan)
    broken["conflicts"] = [{"id": "x"}]
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(SocomError, match="conflicts"):
        type_apply.build_apply_program(tmp_path, path)


def test_layout_parsers_read_bridge_text() -> None:
    layout = type_apply.parse_struct_layout(
        "Structure: X\nSize: 8 bytes\nAlignment: 1\n\nLayout:\n"
        "Offset | Size | Type | Name\n-------|------|------|-----\n"
        "     0 |    4 | char *               | m_b\n"
        "     4 |    1 | uint:1               | (unnamed)\n"
    )
    assert layout == {"size": 8, "components": [[0, 4, "char *", "m_b"], [4, 1, "uint:1", "(unnamed)"]]}
    assert type_apply.parse_struct_layout("Data type is not a structure: U") is None
    values = type_apply.parse_enum_values(
        "Enumeration: E\nSize: 1 bytes\n\nValues:\nName | Value\n-----|------\n"
        "NONE                 | -1 (0xFFFFFFFFFFFFFFFF)\nFIRST                | 0 (0x0)\n"
    )
    assert values == {"size": 1, "values": [["FIRST", 0], ["NONE", -1]]}


class _FakeBridge:
    """Echoes the program's expectations; records every call."""

    def __init__(self, program: dict, existing: list[dict]) -> None:
        self.entries = {entry["temp"]: entry for entry in program["types"]}
        self.types = {row["name"]: dict(row) for row in existing}
        self.calls: list[tuple[str, dict]] = []

    def post_json(self, endpoint: str, **body):
        self.calls.append((endpoint, body))
        if endpoint == "create_struct":
            self.types[body["name"]] = {"name": body["name"], "category": "builtin", "size": 1, "path": "/" + body["name"]}
            return f"Successfully created structure '{body['name']}'"
        if endpoint == "create_union":
            entry = self.entries[body["name"]]
            self.types[body["name"]] = {"name": body["name"], "category": "builtin", "size": entry["size"], "path": "/" + body["name"]}
            return f"Union '{body['name']}' created successfully"
        if endpoint in ("create_enum", "resize_struct", "create_data_type_category"):
            if endpoint == "create_enum":
                self.types[body["name"]] = {"name": body["name"], "category": "builtin", "size": body["size"], "path": "/" + body["name"]}
            if endpoint == "resize_struct":
                self.types[body["name"]]["size"] = body["new_size"]
            return {"status": "success"}
        if endpoint == "create_function_signature":
            self.types[body["name"]] = {"name": body["name"], "category": "builtin", "size": "variable", "path": "/" + body["name"]}
            return "Successfully created function signature"
        if endpoint == "import_data_types":
            name = re.search(r"(?:struct|union) (socom_t_\d+)", body["source"]).group(1)
            self.types[name] = {"name": name, "category": "builtin", "size": self.entries[name]["size"], "path": "/" + name}
            return {"parse_succeeded": True, "error": ""}
        if endpoint == "move_data_type_to_category":
            row = self.types[body["type_name"]]
            row["path"] = f"{body['category_path']}/{row['name']}"
            row["category"] = body["category_path"].rsplit("/", 1)[-1]
            return "Successfully moved data type"
        if endpoint == "rename_data_type":
            row = self.types.pop(body["old_name"])
            row["name"] = body["new_name"]
            row["path"] = row["path"].rsplit("/", 1)[0] + "/" + body["new_name"]
            self.types[body["new_name"] + "@" + row["path"]] = row
            return "Successfully renamed data type"
        if endpoint == "remove_struct_field":
            return "Successfully removed field"
        if endpoint == "create_array_type":
            return f"Successfully created array type: {body['base_type']}"
        if endpoint == "add_struct_field":
            return "Successfully added field"
        if endpoint == "modify_struct_field":
            return "Successfully modified field"
        raise AssertionError(endpoint)

    def request(self, endpoint: str, **parameters):
        self.calls.append((endpoint, parameters))
        if endpoint == "get_struct_layout":
            entry = self.entries[parameters["struct_name"]]
            rows = "".join(f"{o} | {s} | {t} | {n}\n" for o, s, t, n in entry["expected_layout"])
            size = entry["size"] if isinstance(entry["size"], int) and entry["size"] > 0 else 1
            return f"Structure: x\nSize: {size} bytes\n\nLayout:\nOffset | Size | Type | Name\n-------|------|------|-----\n{rows}"
        if endpoint == "get_enum_values":
            entry = self.entries[parameters["enum_name"]]
            rows = "".join(f"{n} | {v} (0x0)\n" for n, v in entry["values"])
            return f"Enumeration: x\nSize: {entry['size']} bytes\n\nValues:\nName | Value\n-----|------\n{rows}"
        raise AssertionError(endpoint)

    def index(self) -> list[dict]:
        return [dict(row) for row in self.types.values()]


def test_executor_applies_without_deleting_and_verifies(tmp_path: Path) -> None:
    program = _program(tmp_path)
    existing = [{"name": "undefined1[12]", "category": "builtin", "size": 12, "path": "/undefined1[12]"}]
    bridge = _FakeBridge(program, existing)
    result = type_apply.execute_apply_program(program, bridge, type_index=bridge.index)
    assert result["ok"] is True and result["type_count"] == len(program["types"])
    endpoints = [endpoint for endpoint, _ in bridge.calls]
    assert not any("delete" in endpoint for endpoint in endpoints)
    assert endpoints.index("import_data_types") > endpoints.index("create_function_signature")
    assert endpoints.index("move_data_type_to_category") > max(
        index for index, endpoint in enumerate(endpoints) if endpoint == "get_struct_layout"
    )
    assert {row["path"] for row in bridge.index()} >= set(program["receipt_scope"]["types"])
    temps = {entry["path"]: entry["temp"] for entry in program["types"]}
    resized = {body["name"]: body["new_size"] for endpoint, body in bridge.calls if endpoint == "resize_struct"}
    # A one-byte layout with fields is resized; an empty one-byte class is not.
    assert resized[temps["/project/Byte"]] == 1
    assert temps["/project/Empty"] not in resized
    assert resized[temps["/project/Vbase"]] == 4
    matrix = _by_path(program)["/project/Matrix"]
    assert matrix["expected_layout"] == [[0, 24, "float[2][3]", "m"]]
    arrays = [body for endpoint, body in bridge.calls if endpoint == "create_array_type"]
    assert arrays == [{"base_type": "float[3]", "length": 2}]
    add = next(
        index
        for index, (endpoint, body) in enumerate(bridge.calls)
        if endpoint == "add_struct_field" and body["field_type"] == "float[2][3]"
    )
    assert bridge.calls[add - 1][0] == "create_array_type"


def test_executor_refuses_pre_existing_temporary_or_target_types(tmp_path: Path) -> None:
    program = _program(tmp_path)
    clash = [{"name": "Point", "category": "project", "size": 12, "path": "/project/Point"}]
    bridge = _FakeBridge(program, clash)
    with pytest.raises(SocomError, match="target type already exists"):
        type_apply.execute_apply_program(program, bridge, type_index=bridge.index)
    leftover = [{"name": "socom_t_9999", "category": "builtin", "size": 1, "path": "/socom_t_9999"}]
    bridge = _FakeBridge(program, leftover)
    with pytest.raises(SocomError, match="temporary apply types"):
        type_apply.execute_apply_program(program, bridge, type_index=bridge.index)
    assert not bridge.calls
