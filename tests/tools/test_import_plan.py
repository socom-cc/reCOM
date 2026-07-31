from __future__ import annotations

from tools._socom.import_plan import build_import_plan


def test_import_plan_is_read_only_and_targets_expected_program(root) -> None:
    plan = build_import_plan(root)
    assert plan["kind"] == "socom-ghidra-import-plan"
    assert plan["mutation_performed"] is False
    assert plan["target"]["project"] == "soCOM"
    assert plan["target"]["program"] == "socom.elf"
    assert plan["target"]["language"] == "r5900:LE:32:default"
    assert plan["receipt_scope"]["schema_version"] == 1
    assert plan["summary"]["type_count"] > 16_000
    assert any(row["qualified_name"] == "CNode" for row in plan["types"])
    cnode = next(row for row in plan["types"] if row["qualified_name"] == "CNode")
    assert any(member["name"] == "m_child" for member in cnode["members"])
    assert plan["summary"]["blocking_conflict_count"] > 0
    assert all(
        not row["qualified_name"].startswith("@") for row in plan["conflicts"]
    )
    synthetic = next(row for row in plan["types"] if row["anonymous"])
    assert synthetic["compile_unit_offset"] is not None
    assert synthetic["parent_die_offset"] is not None
    assert synthetic["identity"].startswith("cu@")


def test_import_plan_has_dependency_safe_application_order(root) -> None:
    plan = build_import_plan(root)
    assert plan["application_order"][:3] == [
        "forward_declarations",
        "typedefs_and_indirections",
        "composite_definitions",
    ]
    assert plan["application_order"][-2:] == [
        "reanalyze_and_review",
        "save_program_through_live_handoff",
    ]
