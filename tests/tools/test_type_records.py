"""Command records: registration-proven record layouts and record-family type plans."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools._socom.constants import REFERENCE_SHA256
from tools._socom.tracker import (
    RECON_SEED_ID,
    TYPE_PLAN_KIND,
    add_type_plan_items,
    audit_tracker,
    claim_work,
    decompose_reconstruction,
    record_stage_baseline,
    refresh_ready_and_stages,
    work_packet,
)
from tools._socom.type_layout import CallParameters, _Family, class_layout, record_key, render_layout
from tools._socom.type_plan import (
    build_type_plan_program,
    layout_sha256,
    live_type_problems,
    records_item_id,
    render_type_plan,
    validate_type_plan,
)
from tools._socom.type_records import Registry, record_class
from tools._socom.util import SocomError

RECORDS = ["DYNAMICS_ACQUIRE_CAMERA", "HUD_OFF", "HUD_ON", "VALVE", "ai::DOOR", "ai::MOVE"]


@pytest.fixture(scope="module")
def records_layout(root: Path) -> dict:
    return class_layout(root, "VALVE_CMD_DATA", records=list(RECORDS))


def _row(layout: dict, command: str) -> dict:
    return next(row for row in layout["classes"] if row["class"] == record_class(command))


def _offset(row: dict, offset: int) -> dict:
    return next(entry for entry in row["offsets"] if entry["offset"] == offset)


def _site(layout: dict, command: str, offset: int, *accesses: str) -> str:
    entry = _offset(_row(layout, command), offset)
    return next(site["site"] for site in entry["sites"] if not accesses or site["access"] in accesses)


def test_registrations_are_read_from_the_registrar_calls(root: Path) -> None:
    family = _Family(root, None, False, records=True)
    registry = Registry(family, CallParameters(family.symbols, family.receivers))
    assert registry.registrar == 0x1C4A50
    assert len(registry.registrations) == 102 and len(registry.commands) == 99
    roles = {spec["role"]: spec for spec in registry.roles}
    assert roles["parser"]["returns_record"] and roles["parser"]["record_registers"] == []
    assert roles["tick"]["record_registers"] == [4] and not roles["tick"]["returns_record"]
    assert len(registry.select(["ai::*"])) == 33
    with pytest.raises(SocomError, match="no command registered"):
        registry.select(["ai::NOPE"])
    with pytest.raises(SocomError, match="a class name"):
        _Family(root, None, False)


def test_record_rows_prove_their_pointers_sizes_and_dwarf_casts(records_layout: dict) -> None:
    layout = records_layout
    assert layout["records"] == sorted(RECORDS) and layout["registrar"]["header"] == "_zanim_cmd_hdr"
    door, move = _row(layout, "ai::DOOR"), _row(layout, "ai::MOVE")
    assert door["size_evidence"] == move["size_evidence"] == [44] and door["data_size"] == [44]
    # CTDoor::Begin tail-jumps to CTMove::Begin with its record; CTDoor::Parse tail-jumps to CTMove::Parse.
    callbacks = {(row["name"].split("(")[0], row["record"]): row["proofs"] for row in door["callbacks"]}
    assert any("passed by CTDoor::Begin" in text for text in callbacks[("CTMove::Begin", "a0")])
    assert any("tail-jumps" in text for text in callbacks[("CTMove::Parse", "return")])
    begin = next(row for row in layout["functions"] if row["function"] == "0x2b9c90")
    assert {root["class"] for root in begin["roots"]} == {"record ai::DOOR|ai::MOVE"}
    assert record_key(["ai::MOVE", "ai::DOOR"]) == ("<record>", "ai::DOOR", "ai::MOVE")
    assert [entry["offset"] for entry in door["offsets"]] == [entry["offset"] for entry in move["offsets"]]
    header = door["header"]
    assert header["members"][0] == [0, 2, "uint:16", "data_type"] and header["members"][-1] == [2, 2, "uint:14", "data_size"]
    camera = _row(layout, "DYNAMICS_ACQUIRE_CAMERA")
    assert {row["type"] for row in camera["dwarf_casts"]} == {"_camera_control_cmd"}
    assert _row(layout, "HUD_ON")["dwarf_casts"] == []
    valve = _row(layout, "VALVE")
    assert any(site.get("parameter_type") == "VALVE_CMD_DATA * (receiver)" for site in _offset(valve, 4)["sites"])
    text = render_layout(layout)
    assert "## record ai::DOOR [record]" in text and "DWARF cast: local cmd" in text and "6 zanim command records" in text


def _field(offset: int, size: int, type_name: str, name: str, evidence: list[str], **extra: object) -> dict:
    return {"offset": offset, "size": size, "type": type_name, "name": name, "provenance": "invented-provisional", "evidence": evidence, **extra}


def _records_plan(layout: dict) -> dict:
    base = [{"type": "/project/_zanim_cmd_hdr", "offset": 0, "size": 4, "evidence": [_site(layout, "VALVE", 2)]}]
    return {
        "kind": "socom-code-type-plan", "schema_version": 1,
        "work_item_id": records_item_id("zanim", "test"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "VALVE_CMD_DATA", "records": layout["records"], "family": "test", "registrar": "zanim", "sha256": layout_sha256(layout)},
        "naming_survey": ["test fixture"],
        "types": [
            {"name": "_camera_control_cmd", "kind": "dwarf", "category": "/project", "name_provenance": "dwarf",
             "name_evidence": ["0xf3cbf"], "records": ["DYNAMICS_ACQUIRE_CAMERA"]},
            {"name": "_hud_switch_cmd", "kind": "struct", "category": "/project", "name_provenance": "invented-provisional",
             "size": 8, "alignment": 4, "records": ["HUD_OFF", "HUD_ON"],
             "bases": [{"type": "/project/_zanim_cmd_hdr", "offset": 0, "size": 4, "evidence": [_site(layout, "HUD_ON", 2)]}],
             "fields": [
                 _field(4, 4, "int", "m_on", [_site(layout, "HUD_ON", 4)], bit_offset=0, bit_size=1),
                 _field(4, 4, "int", "m_off", [_site(layout, "HUD_ON", 4)], bit_offset=1, bit_size=1),
             ]},
            {"name": "VALVE_CMD_DATA", "kind": "class", "category": "/project", "name_provenance": "elf-symbol",
             "size": 12, "alignment": 4, "size_evidence": ["embedded at VALVE+4 of the 16-byte record"],
             "fields": [
                 _field(0, 4, "int", "m_left", ["0x2f834c"]), _field(4, 4, "int", "m_right", ["0x2f8620"]),
                 _field(8, 1, "uchar", "m_operator", ["0x2f83c4"]), _field(9, 1, "uchar", "m_flags", ["0x2f832c"]),
             ],
             "padding": [{"offset": 10, "size": 2, "reason": "no access"}]},
            {"name": "_valve_cmp_cmd", "kind": "struct", "category": "/project", "name_provenance": "invented-provisional",
             "size": 16, "alignment": 4, "records": ["VALVE"], "bases": base,
             "fields": [_field(4, 12, "VALVE_CMD_DATA", "m_data", [_site(layout, "VALVE", 4)])]},
            {"name": "TASK_MOVE", "kind": "struct", "category": "/project", "name_provenance": "invented-provisional",
             "size": 44, "alignment": 4, "records": ["ai::DOOR", "ai::MOVE"],
             "bases": [{"type": "/project/TASK_HDR", "offset": 0, "size": 8, "evidence": [_site(layout, "ai::MOVE", 4, "load")]}],
             "fields": [
                 _field(8, 12, "/project/CPnt3D", "m_from", [_site(layout, "ai::MOVE", 8, "load")]),
                 _field(20, 12, "/project/CPnt3D", "m_to", [_site(layout, "ai::MOVE", 20, "store")]),
                 _field(32, 4, "float", "m_speed", [_site(layout, "ai::MOVE", 32, "load")]),
                 _field(36, 4, "int", "m_node", [_site(layout, "ai::MOVE", 36, "load")]),
                 _field(40, 1, "uchar", "m_type", [_site(layout, "ai::MOVE", 40, "load")]),
             ],
             "padding": [{"offset": 41, "size": 3, "reason": "no access"}]},
        ],
    }


def test_a_records_plan_validates_programs_and_references_dwarf_records(root: Path, records_layout: dict, tmp_path: Path) -> None:
    plan = _records_plan(records_layout)
    assert validate_type_plan(root, None, plan, records_layout) == []
    from tools._socom.type_plan_evidence import TypeEvidence

    review = render_type_plan(plan, records_layout, [], TypeEvidence(root))
    assert "## Records" in review and "| `ai::DOOR` | `TASK_MOVE` | 0x2c | 0x2c |" in review
    assert "Existing DWARF record (DWARF 0xf3cbf): referenced, not created" in review and "`release`" in review
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    program = build_type_plan_program(root, None, path, records_layout)
    created = sorted(entry["path"] for entry in program["types"])
    assert created == ["/project/TASK_MOVE", "/project/VALVE_CMD_DATA", "/project/_hud_switch_cmd", "/project/_valve_cmp_cmd"]
    assert program["referenced_types"] == [{
        "type": "/project/_camera_control_cmd", "records": ["DYNAMICS_ACQUIRE_CAMERA"], "size": 8, "dwarf": ["0xf3cbf"],
        "layout": [[0, 4, "_zanim_cmd_hdr", "hdr"], [4, 1, "int:1", "release"], [4, 1, "int:1", "acquire"]],
    }]
    assert {"/project/TASK_HDR", "/project/_zanim_cmd_hdr", "/project/CPnt3D"} <= set(program["external_types"])
    assert "/project/_camera_control_cmd" not in program["receipt_scope"]["types"]
    index = [{"name": path.rsplit("/", 1)[1], "path": path} for path in program["external_types"] + ["/project/_camera_control_cmd"]]
    live = {"size": 8, "components": [[0, 4, "_zanim_cmd_hdr", "hdr"], [4, 1, "int:1", "release"], [4, 1, "int:1", "acquire"], [4, 1, "int:6", "(unnamed)"]]}
    assert live_type_problems(program, index, lambda leaf: live if leaf == "_camera_control_cmd" else None) == []
    changed = {**live, "components": [[0, 4, "_zanim_cmd_hdr", "hdr"], [4, 1, "int:1", "release"]]}
    assert any("differs from its DWARF members" in text for text in live_type_problems(program, index, lambda leaf: changed))
    assert any("referenced DWARF type" in text for text in live_type_problems(program, index[:-1]))


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda plan: plan["types"][1]["records"].remove("HUD_OFF"), "record HUD_OFF is not laid out by any plan type"),
        (lambda plan: plan["types"][0].update(kind="struct", name="_hud_camera_cmd", name_provenance="invented-provisional", size=8,
                                              alignment=4, bases=[{"type": "/project/_zanim_cmd_hdr", "offset": 0, "size": 4,
                                                                   "evidence": ["0x1e74dc"]}],
                                              padding=[{"offset": 4, "size": 4, "reason": "x"}]),
         "DWARF casts the record to _camera_control_cmd"),
        (lambda plan: plan["types"][1].update(name="tag_HUD"), "an invented record type is named"),
        (lambda plan: plan["types"][1].update(size=12, padding=[{"offset": 8, "size": 4, "reason": "x"}]), "differs from its records'"),
        (lambda plan: plan["types"][4]["bases"][0].update(size=12), "live base /project/TASK_HDR is 12 bytes"),
        (lambda plan: plan["types"][0].update(size=8), "takes its layout from DWARF"),
        (lambda plan: plan["types"][0]["records"].append("HUD_ON"), "is listed by several plan types"),
        (lambda plan: plan["layout"].update(family="Bad Family"), "lower-case slug"),
    ],
)
def test_records_plans_refuse_unmapped_recreated_or_missized_records(root: Path, records_layout: dict, mutate, expected: str) -> None:
    plan = copy.deepcopy(_records_plan(records_layout))
    mutate(plan)
    problems = validate_type_plan(root, None, plan, records_layout)
    assert any(expected in text for text in problems), problems


def test_a_header_missing_at_offset_zero_and_dwarf_types_without_casts_are_refused(root: Path, records_layout: dict) -> None:
    plan = copy.deepcopy(_records_plan(records_layout))
    hud = plan["types"][1]
    hud["bases"] = []
    hud["fields"].insert(0, _field(0, 4, "uint", "m_word", [_site(records_layout, "HUD_ON", 2)]))
    problems = validate_type_plan(root, None, plan, records_layout)
    assert any("header _zanim_cmd_hdr is not at +0x0" in text for text in problems), problems
    plan = copy.deepcopy(_records_plan(records_layout))
    plan["types"][1] = {"name": "_camera_set_regions_cmd", "kind": "dwarf", "category": "/project", "name_provenance": "dwarf",
                        "name_evidence": ["0xf2c50"], "records": ["HUD_OFF", "HUD_ON"]}
    problems = validate_type_plan(root, None, plan, records_layout)
    assert any("no DWARF parameter or local of the record's callbacks is a _camera_set_regions_cmd" in text for text in problems), problems


def test_a_float_immediate_stored_through_a_gpr_is_width_evidence_only() -> None:
    from tools._socom.type_plan import _compatible, parse_type

    site = {"access": "store", "width": 4, "kind": "int", "constant": -0x40800000}
    assert _compatible(site, parse_type("float"), 4) and _compatible(site, parse_type("int"), 4)
    assert not _compatible({"access": "load", "width": 4, "kind": "int"}, parse_type("float"), 4)


@pytest.fixture()
def decomposed(stage2_tracker: dict, root: Path) -> dict:
    from tools._socom.recon import recon_groups

    record_stage_baseline(
        stage2_tracker, "debug-metadata-import", "reviewer", ["close-out.md"],
        receipt_sha256="9" * 64, receipt={"counts": {}, "indexes": {}},
    )
    decompose_reconstruction(stage2_tracker, recon_groups(root))
    refresh_ready_and_stages(stage2_tracker)
    stage2_tracker["revision"] += 1
    return stage2_tracker


def test_records_type_plan_items_record_the_family(root: Path, decomposed: dict, records_layout: dict) -> None:
    records = ["ai::DOOR", "ai::MOVE"]
    with pytest.raises(SocomError, match="slug"):
        add_type_plan_items(decomposed, None, False, records=records, family="Task Hdr", registrar="zanim")
    with pytest.raises(SocomError, match="sorted"):
        add_type_plan_items(decomposed, None, False, records=["ai::MOVE", "ai::DOOR"], family="move", registrar="zanim")
    ids = add_type_plan_items(decomposed, None, False, records=records, family="move", registrar="zanim")
    assert ids == ["socom:work:type-plan-zanim-move", "socom:work:type-plan-zanim-move-apply"]
    refresh_ready_and_stages(decomposed)
    assert audit_tracker(decomposed, strict=True) == []
    by_id = {row["id"]: row for row in decomposed["work_items"]}
    assert by_id[ids[0]]["kind"] == TYPE_PLAN_KIND
    assert by_id[ids[0]]["batch"] == by_id[ids[1]]["batch"] == {"records": records, "family": "move", "registrar": "zanim", "with_derived": False}
    assert set(ids) <= set(by_id[RECON_SEED_ID]["dependencies"])
    claim_work(decomposed, ids[0], "planner", 30)
    packet = work_packet(decomposed, ids[0], "planner")
    assert (
        "python tools/socom.py recon layout --records ai::DOOR ai::MOVE --registrar zanim --output build/type-plans/zanim-move-layout.json"
        in packet["validation"]
    )
    broken = copy.deepcopy(decomposed)
    next(row for row in broken["work_items"] if row["id"] == ids[0])["batch"]["family"] = "other"
    assert any("records batch" in text for text in audit_tracker(broken))
    # The plan of another family's layout is refused against this item.
    plan = _records_plan(records_layout)
    plan["work_item_id"] = ids[0]
    plan["layout"]["family"] = "move"
    assert any("plans different records" in text for text in validate_type_plan(root, decomposed, plan, records_layout))
