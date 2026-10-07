from __future__ import annotations

import collections

import pytest

from tools._socom.import_plan import build_import_plan, decode_location, parameter_storage
from tools._socom.type_identity import is_template_name


@pytest.fixture(scope="module")
def plan(root) -> dict:
    return build_import_plan(root)


def test_import_plan_is_read_only_and_targets_expected_program(plan) -> None:
    assert plan["kind"] == "socom-ghidra-import-plan"
    assert plan["schema_version"] == 4
    assert plan["mutation_performed"] is False
    assert plan["target"]["project"] == "soCOM"
    assert plan["target"]["program"] == "socom.elf"
    assert plan["target"]["language"] == "r5900:LE:32:default"
    assert plan["receipt_scope"]["schema_version"] == 1
    assert plan["summary"]["type_count"] > 16_000
    synthetic = next(row for row in plan["types"] if row["anonymous"])
    assert synthetic["compile_unit_offset"] is not None
    assert synthetic["parent_die_offset"] is not None
    assert synthetic["identity"].startswith("cu@")
    assert synthetic["structural_class"].startswith("socom:type-class:")


def test_dwarf_names_are_qualified_from_binary_evidence(plan) -> None:
    cnode = next(
        row
        for row in plan["types"]
        if row["raw_name"] == "CNode" and not row["declaration"]
    )
    assert cnode["qualified_name"] == "zdb::CNode"
    assert cnode["scope_path"] == ["zdb"]
    assert cnode["ghidra_path"] == "/project/zdb/CNode"
    assert cnode["identity_resolution"] == "method"
    assert any(member["name"] == "m_child" for member in cnode["members"])
    camera = {
        row["qualified_name"]
        for row in plan["types"]
        if row["raw_name"] == "CCamera"
    }
    assert camera == {"zdb::CCamera"}


def test_import_plan_has_no_blocking_conflicts_and_distinct_identities(plan) -> None:
    assert plan["summary"]["blocking_conflict_count"] == 0
    assert plan["conflicts"] == []
    by_name = collections.defaultdict(set)
    for identity in plan["identities"]:
        by_name[identity["qualified_name"]].add(identity["structural_class"])
    assert all(len(keys) == 1 for keys in by_name.values())


def test_unresolved_structures_get_distinct_provisional_identities(plan) -> None:
    provisional = [
        identity
        for identity in plan["identities"]
        if identity["resolution"] == "provisional"
    ]
    assert provisional
    assert plan["summary"]["provisional_identity_count"] == len(provisional)
    for identity in provisional:
        assert identity["qualified_name"].startswith(identity["raw_name"] + "@")
        assert identity["ghidra_path"].startswith("/project/unresolved/")
    vectors = [
        identity for identity in plan["identities"] if identity["raw_name"] == "vector"
    ]
    assert len({identity["qualified_name"] for identity in vectors}) == len(vectors) > 1


def test_template_names_come_only_from_evidence_reaching_each_die(plan) -> None:
    # Review finding F1/F2: a sole .symtab candidate does not prove a template
    # instantiation, because inlined instantiations never reach the symbols.
    assert not [
        identity["qualified_name"]
        for identity in plan["identities"]
        if identity["resolution"] in ("symbol", "spelling")
        and is_template_name(identity["qualified_name"])
    ]
    queues = [identity for identity in plan["identities"] if identity["raw_name"] == "queue"]
    assert queues and all(identity["resolution"] == "provisional" for identity in queues)
    # Review finding F3: layout-identical deque instantiations share one
    # structural class, so the LOBBY_STATE name covers only reached DIEs.
    lobby = next(
        identity
        for identity in plan["identities"]
        if identity["qualified_name"]
        == "std::deque<CZOnlineLobby::LOBBY_STATE, std::allocator<CZOnlineLobby::LOBBY_STATE>>"
    )
    assert lobby["resolution"] == "call-site"
    siblings = [
        identity
        for identity in plan["identities"]
        if identity["structural_class"] == lobby["structural_class"]
    ]
    assert any(identity["resolution"] == "provisional" for identity in siblings)


def test_type_references_keep_modifiers_and_array_elements(plan) -> None:
    cnode = next(
        row
        for row in plan["types"]
        if row["qualified_name"] == "zdb::CNode" and not row["declaration"]
    )
    model = next(member for member in cnode["members"] if member["name"] == "m_model")
    assert model["type"]["modifiers"] == ["pointer_to"]
    assert model["type"]["die_offset"] is not None
    assert all(member["type"] is not None for row in plan["types"] for member in row["members"])
    array = next(row for row in plan["types"] if row["kind"] == "array_type")
    assert array["array"]["dimensions"]
    assert array["array"]["element"] is not None


def test_types_only_selection_has_no_function_receipt_scope(root) -> None:
    plan = build_import_plan(root, {"selection": "types"})
    assert plan["functions"] == []
    assert plan["variables"] == []
    assert plan["receipt_scope"]["functions"] == []
    assert "/project/zdb/CNode" in plan["receipt_scope"]["types"]


def test_locations_decode_registers_frames_and_addresses() -> None:
    assert decode_location("0110000000") == {"kind": "register", "register": 16, "register_name": "s0"}
    assert decode_location("021d000000042800000007") == {
        "kind": "frame", "register": 29, "register_name": "sp", "offset": 40,
    }
    assert decode_location("03606f4700") == {"kind": "address", "address": 0x476F60}
    assert decode_location("ff") == {"kind": "invalid", "raw": "ff"}
    assert decode_location(None) is None


def test_parameter_storage_rejects_impossible_entry_registers() -> None:
    def param(register):
        return {"storage": {"kind": "register", "register": register}}

    assert parameter_storage([param(2), param(2)]) == "conflicting"
    assert parameter_storage([param(2)]) == "not-entry-storage"
    assert parameter_storage([param(16), param(17)]) == "recorded"
    assert parameter_storage([]) == "recorded"


def test_functions_and_variables_carry_decoded_evidence(plan) -> None:
    functions = {row["low_pc"]: row for row in plan["functions"] if row["low_pc"]}
    release = functions[0x140460]
    assert release["qualified_name"] == "_zmalloc<four>::release"
    assert release["dwarf_qualified_name"] == "release"
    assert release["mangled_name"] == "release__15_zmalloc<4four>FPv"
    assert release["parameter_storage"] == "conflicting"
    start = functions[0x140550]
    assert start["qualified_name"] == "COurGame::StartEngine"
    time = next(row for row in start["locals"] if row["name"] == "time")
    assert time["storage"] == {"kind": "frame", "register": 29, "register_name": "sp", "offset": 40}
    assert time["block"] == [0x140550, 0x140680]
    # Function locals stay with their function, never as free variables.
    variables = {row["name"]: row for row in plan["variables"]}
    assert "time" not in variables and "ptr" not in variables
    assert variables["theGame"]["status"] == "present"
    assert variables["theGame"]["placement"] == {"segment": 0, "initialized": False}
    assert variables["gopt"]["placement"]["initialized"] is True
    assert variables["__RTTI__8CZWeapon"]["status"] == "absent"
    assert "0x476f60" in plan["receipt_scope"]["globals"]
    assert "0x0" not in plan["receipt_scope"]["globals"]


def test_import_plan_has_dependency_safe_application_order(plan) -> None:
    assert plan["application_order"][:3] == [
        "forward_declarations",
        "typedefs_and_indirections",
        "composite_definitions",
    ]
    assert plan["application_order"][-2:] == [
        "reanalyze_and_review",
        "save_program_through_live_handoff",
    ]
