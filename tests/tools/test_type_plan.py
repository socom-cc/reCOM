from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from tools._socom import type_apply
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.tracker import (
    RECON_SEED_ID,
    TYPE_APPLY_KIND,
    TYPE_PLAN_KIND,
    TYPE_PLAN_PREFIX,
    add_type_plan_items,
    audit_tracker,
    claim_work,
    decompose_reconstruction,
    record_stage_baseline,
    refresh_ready_and_stages,
    work_packet,
)
from tools._socom import type_plan as plans
from tools._socom.type_layout import class_layout
from tools._socom.type_plan import (
    affected_groups,
    build_type_plan_program,
    layout_sha256,
    live_type_problems,
    parse_type,
    render_type_plan,
    type_plan_item_id,
    validate_type_plan,
)
from tools._socom.util import SocomError


# -- a synthetic layout: zdb::CTest (0x20 bytes) on base zdb::tag_TEST (8 bytes)


def _site(site: str, offset: int, access: str, **fields) -> dict:
    return {
        "offset": offset, "site": site, "access": access, "function": "0x100000",
        "function_name": "zdb::CTest::f(void)", "insn": "x", "root": "this", **fields,
    }


def _layout() -> dict:
    test_sites = [
        _site("0x100000", 0x0, "load", width=1, kind="int", signed=False),
        _site("0x100004", 0x4, "store", width=4, kind="int"),
        _site("0x100008", 0x8, "store", width=4, kind="int", vtable_store="__vt__Q23zdb5CTest+0x0"),
        _site("0x10000c", 0xC, "deref-load", pointer=True, pointee_width=4, pointee_kind="int"),
        _site("0x100010", 0x10, "load", width=4, kind="float"),
        _site("0x100014", 0x14, "store", width=4, kind="zero", constant=0),
    ]

    def offsets(sites: list[dict]) -> list[dict]:
        rows = {}
        for site in sites:
            rows.setdefault(site["offset"], []).append(site)
        return [{"offset": offset, "sites": rows[offset], "conflicts": []} for offset in sorted(rows)]

    return {
        "kind": "socom-type-layout-evidence",
        "schema_version": 1,
        "class": "zdb::CTest",
        "with_derived": False,
        "classes": [
            {
                "class": "zdb::CTest", "role": "requested", "size_evidence": [0x20],
                "bases": [{"class": "zdb::tag_TEST", "offset": 0}],
                "vtable": {"name": "__vt__Q23zdb5CTest", "size": 12, "slots": []},
                "offsets": offsets(test_sites), "object_passes": [],
            },
            {
                "class": "zdb::tag_TEST", "role": "base", "size_evidence": [], "bases": [], "vtable": None,
                "offsets": offsets([_site("0x200000", 0x4, "load", width=4, kind="int")]), "object_passes": [],
            },
        ],
    }


def _field(offset: int, size: int, type_name: str, name: str, evidence: list[str], **extra) -> dict:
    return {"offset": offset, "size": size, "type": type_name, "name": name, "provenance": "invented-provisional",
            "evidence": evidence, **extra}


def _plan(layout: dict) -> dict:
    return {
        "kind": "socom-code-type-plan",
        "schema_version": 1,
        "work_item_id": type_plan_item_id("zdb::CTest"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "zdb::CTest", "with_derived": False, "sha256": layout_sha256(layout)},
        "naming_survey": ["zdb::CNode (DWARF): m_parent, m_child"],
        "types": [
            {
                "name": "zdb::tag_TEST", "kind": "struct", "category": "/project/zdb", "name_provenance": "elf-symbol",
                "size": 8, "alignment": 4, "size_evidence": ["CTest stores its own member at 0x8"],
                "fields": [
                    _field(0, 1, "uchar", "m_flag", ["0x100000"]),
                    _field(4, 4, "int", "m_count", ["0x100004", "0x200000"]),
                ],
                "padding": [{"offset": 1, "size": 3, "reason": "no access"}],
            },
            {
                "name": "zdb::CTest", "kind": "class", "category": "/project/zdb", "name_provenance": "elf-symbol",
                "size": 0x20, "alignment": 4,
                "bases": [{"type": "zdb::tag_TEST", "offset": 0}],
                "vptr": {"offset": 8, "type": "zdb::CTest_vtbl *", "evidence": ["0x100008"]},
                "fields": [
                    _field(0xC, 4, "zdb::tag_TEST *", "m_next", ["0x10000c"]),
                    _field(0x10, 4, "float", "m_scale", ["0x100010"]),
                    _field(0x14, 4, "undefined4", "m_unknown", ["0x100014"]),
                ],
                "padding": [{"offset": 0x18, "size": 8, "reason": "no access"}],
            },
            {
                "name": "zdb::CTest_vtbl", "kind": "vtable", "category": "/project/zdb",
                "name_provenance": "invented-provisional", "size": 0, "opaque": True,
                "opaque_reason": "slot return types are not encoded in the mangled names",
            },
        ],
    }


def _types(plan: dict) -> dict:
    return {row["name"]: row for row in plan["types"]}


def test_type_spelling_parser() -> None:
    assert parse_type("uint") == {"base": "uint", "pointers": 0, "arrays": []}
    assert parse_type("zdb::CVisual * *") == {"base": "zdb::CVisual", "pointers": 2, "arrays": []}
    assert parse_type("/project/_word128 *[4]") == {"base": "/project/_word128", "pointers": 1, "arrays": [4]}
    assert parse_type("") is None
    # Template arguments stay in the base, pointer arguments included.
    assert parse_type("std::vector<zdb::CTexPalette*, std::allocator<zdb::CTexPalette*>> *") == {
        "base": "std::vector<zdb::CTexPalette*, std::allocator<zdb::CTexPalette*>>", "pointers": 1, "arrays": [],
    }
    assert parse_type("a*b") is None and parse_type("X<int") is None


def test_valid_synthetic_plan_passes_and_renders() -> None:
    layout = _layout()
    plan = _plan(layout)
    assert validate_type_plan(Path("."), None, plan, layout) == []
    text = render_type_plan(plan, layout, [])
    assert "__vt" in text and "invented-provisional" in text and "validation: ok" in text


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda plan: _types(plan)["zdb::CTest"].update(size=0x24), "differs from the allocation evidence"),
        (lambda plan: _types(plan)["zdb::tag_TEST"]["fields"][1].update(type="float"), "contradicts float"),
        (lambda plan: _types(plan)["zdb::tag_TEST"]["fields"][0].update(type="char"), "every load zero-extends"),
        (lambda plan: _types(plan)["zdb::CTest"]["padding"].append({"offset": 0x14, "size": 4}), "padding 0x14+0x4 is accessed"),
        (lambda plan: _types(plan)["zdb::CTest"].update(padding=[]), "bytes 0x18-0x1f are not covered"),
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][1].update(size=8, type="double"), "overlaps"),
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][0].update(type="void *"), "void * is dereferenced"),
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][1].update(type="undefined4"), "undefined4 is a placeholder"),
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][0].update(type="uint"), "so it is a pointer"),
        (lambda plan: _types(plan)["zdb::CTest"]["bases"][0].update(offset=4), "RTTI base list does not name"),
        (lambda plan: _types(plan)["zdb::CTest"]["vptr"].update(evidence=["0x100004"]), "is not a store of"),
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][1].update(name="scale"), "m_ followed by lower snake_case"),
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][1].update(name="m_refCount"), "m_ followed by lower snake_case"),
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][1].update(evidence=["0x999999"]), "evidence 0x999999 is not an access"),
        (lambda plan: _types(plan)["zdb::CTest"].update(category="/project"), "category must be /project/zdb"),
        (lambda plan: _types(plan)["zdb::CTest_vtbl"].update(opaque_reason=""), "opaque_reason"),
        (lambda plan: plan["layout"].update(sha256="0" * 64), "layout.sha256 differs"),
        (lambda plan: plan.update(naming_survey=[]), "naming_survey"),
    ],
)
def test_validation_rejects_unbacked_or_contradicted_layouts(mutate, expected: str) -> None:
    layout = _layout()
    plan = _plan(layout)
    mutate(plan)
    problems = validate_type_plan(Path("."), None, plan, layout)
    assert any(expected in text for text in problems), problems


def test_accesses_beyond_the_size_must_be_explained() -> None:
    layout = _layout()
    layout["classes"][0]["offsets"].append(
        {"offset": 0x24, "sites": [_site("0x100024", 0x24, "load", width=4, kind="int")], "conflicts": []}
    )
    plan = _plan(layout)
    problems = validate_type_plan(Path("."), None, plan, layout)
    assert any("outside_accesses" in text for text in problems)
    _types(plan)["zdb::CTest"]["outside_accesses"] = [{"site": "0x100024", "reason": "downcast to a derived class"}]
    assert validate_type_plan(Path("."), None, plan, layout) == []


def test_program_orders_bases_first_and_fits_the_type_executor(tmp_path: Path) -> None:
    layout = _layout()
    plan = _plan(layout)
    # A bitfield unit sends a type through the C route.
    tag = _types(plan)["zdb::tag_TEST"]
    tag["fields"][0] = _field(0, 1, "uchar", "m_on", ["0x100000"], bit_offset=0, bit_size=1)
    tag["fields"].insert(1, _field(0, 1, "uchar", "m_mode", ["0x100000"], bit_offset=2, bit_size=3))
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    program = build_type_plan_program(tmp_path, None, path, layout)
    assert program["kind"] == type_apply.APPLY_PROGRAM_KIND
    paths = [entry["path"] for entry in program["types"]]
    assert paths.index("/project/zdb/tag_TEST") < paths.index("/project/zdb/CTest")
    entries = {entry["path"]: entry for entry in program["types"]}
    assert entries["/project/zdb/CTest_vtbl"]["route"] == "empty"
    tag_entry = entries["/project/zdb/tag_TEST"]
    assert tag_entry["route"] == "c" and "unsigned char m_on : 1;" in tag_entry["c_source"]
    test_entry = entries["/project/zdb/CTest"]
    assert test_entry["route"] == "fields"
    names = [field["name"] for field in test_entry["fields"]]
    assert names[:2] == ["tag_TEST", "__vt"]
    vptr = next(field for field in test_entry["fields"] if field["name"] == "__vt")
    assert vptr["type"] == f"{entries['/project/zdb/CTest_vtbl']['temp']} *"
    assert program["receipt_scope"]["types"] == sorted(paths)
    assert program["plan"]["work_item_id"] == type_plan_item_id("zdb::CTest")

    bridge = _Bridge(program)
    result = type_apply.execute_apply_program(program, bridge, type_index=bridge.index)
    assert result["ok"] is True and result["type_count"] == 3
    endpoints = [endpoint for endpoint, _body in bridge.calls]
    assert not any("delete" in endpoint for endpoint in endpoints)
    assert {body["new_name"] for endpoint, body in bridge.calls if endpoint == "rename_data_type"} == {"tag_TEST", "CTest", "CTest_vtbl"}


def test_live_type_checks_are_read_only_and_exact() -> None:
    program = {"types": [{"path": "/project/zdb/CTest", "temp": "socom_t_0001"}], "external_types": ["/project/std/__vector_pod<int>"]}
    assert live_type_problems(program, [{"name": "__vector_pod<int>", "path": "/project/std/__vector_pod<int>"}]) == []
    problems = live_type_problems(
        program,
        [
            {"name": "CTest", "path": "/project/zdb/CTest"},
            {"name": "__vector_pod<int>", "path": "/project/std/__vector_pod<int>"},
            {"name": "__vector_pod<int>", "path": "/project/other/__vector_pod<int>"},
        ],
    )
    assert any("already exists" in text for text in problems)
    assert any("resolves to" in text for text in problems)


class _Bridge:
    """Records calls and echoes each entry's expected layout."""

    def __init__(self, program: dict) -> None:
        self.entries = {entry["temp"]: entry for entry in program["types"]}
        self.types: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []

    def post_json(self, endpoint: str, **body):
        self.calls.append((endpoint, body))
        if endpoint == "create_struct":
            self.types[body["name"]] = {"name": body["name"], "size": 1, "path": "/" + body["name"]}
            return "Successfully created structure"
        if endpoint == "import_data_types":
            name = re.search(r"struct (socom_t_\d+)", body["source"]).group(1)
            self.types[name]["size"] = self.entries[name]["size"]
            return {"parse_succeeded": True, "error": ""}
        if endpoint == "resize_struct":
            self.types[body["name"]]["size"] = body["new_size"]
            return {"status": "success"}
        if endpoint == "create_data_type_category":
            return {"status": "success"}
        if endpoint == "move_data_type_to_category":
            row = self.types[body["type_name"]]
            row["path"] = f"{body['category_path']}/{row['name']}"
            return "Successfully moved data type"
        if endpoint == "rename_data_type":
            row = self.types.pop(body["old_name"])
            row["name"] = body["new_name"]
            row["path"] = row["path"].rsplit("/", 1)[0] + "/" + body["new_name"]
            self.types[row["path"]] = row
            return "Successfully renamed data type"
        if endpoint == "remove_struct_field":
            return "Successfully removed field"
        if endpoint == "add_struct_field":
            return "Successfully added field"
        if endpoint == "modify_struct_field":
            return "Successfully modified field"
        raise AssertionError(endpoint)

    def request(self, endpoint: str, **parameters):
        self.calls.append((endpoint, parameters))
        entry = self.entries[parameters["struct_name"]]
        rows = "".join(f"{o} | {s} | {t} | {n}\n" for o, s, t, n in entry["expected_layout"])
        size = entry["size"] if isinstance(entry["size"], int) and entry["size"] > 0 else 1
        return f"Structure: x\nSize: {size} bytes\n\nLayout:\nOffset | Size | Type | Name\n-------|------|------|-----\n{rows}"

    def index(self) -> list[dict]:
        return [dict(row) for row in self.types.values()]


# -- the real ELF: a plan for zdb::tag_VIS_PARAMS alone validates end to end


@pytest.fixture(scope="module")
def vis_params(root: Path) -> dict:
    return class_layout(root, "zdb::tag_VIS_PARAMS")


def test_real_layout_plan_validates_against_regenerated_evidence(root: Path, vis_params: dict) -> None:
    offsets = {row["offset"]: [site["site"] for site in row["sites"]] for row in vis_params["classes"][0]["offsets"]}
    fields = [_field(0, 4, "uint", "m_word", offsets[0])]
    fields += [_field(offset, 1, "uchar", f"m_byte{offset}", offsets[offset]) for offset in (4, 5, 6, 7)]
    fields += [_field(8, 4, "uint", "m_pair", offsets[8])]
    fields += [_field(offset, 4, "float", f"m_value{offset}", offsets[offset]) for offset in (12, 16, 20)]
    plan = {
        "kind": "socom-code-type-plan",
        "schema_version": 1,
        "work_item_id": type_plan_item_id("zdb::tag_VIS_PARAMS"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "zdb::tag_VIS_PARAMS", "with_derived": False, "sha256": layout_sha256(vis_params)},
        "naming_survey": ["test fixture"],
        "types": [
            {
                "name": "zdb::tag_VIS_PARAMS", "kind": "struct", "category": "/project/zdb", "name_provenance": "elf-symbol",
                "size": 24, "alignment": 4, "size_evidence": ["operator= copies 0x0-0x17"], "fields": fields,
            }
        ],
    }
    assert validate_type_plan(root, None, plan, vis_params) == []
    # Without a layout argument the evidence is regenerated from the ELF.
    assert validate_type_plan(root, None, copy.deepcopy(plan)) == []


# -- tracker items -----------------------------------------------------------


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


def test_type_plan_items_join_the_stage_gate(decomposed: dict) -> None:
    assert plans.TYPE_PLAN_PREFIX == TYPE_PLAN_PREFIX
    ids = add_type_plan_items(decomposed, "zdb::CVisual", True)
    assert ids == ["socom:work:type-plan-zdb-cvisual", "socom:work:type-plan-zdb-cvisual-apply"]
    refresh_ready_and_stages(decomposed)
    assert audit_tracker(decomposed, strict=True) == []
    by_id = {row["id"]: row for row in decomposed["work_items"]}
    plan, apply = by_id[ids[0]], by_id[ids[1]]
    assert plan["kind"] == TYPE_PLAN_KIND and plan["resources"] == ["build/type-plans"] and plan["status"] == "ready"
    assert apply["kind"] == TYPE_APPLY_KIND and apply["dependencies"] == [ids[0]] and apply["status"] == "blocked"
    assert "ghidra-writer" in apply["resources"] and "ghidra-writer" not in plan["resources"]
    assert set(ids) <= set(by_id[RECON_SEED_ID]["dependencies"])
    with pytest.raises(SocomError):
        add_type_plan_items(decomposed, "zdb::CVisual", True)
    claim_work(decomposed, ids[0], "planner", 30)
    packet = work_packet(decomposed, ids[0], "planner")
    assert packet["role"] == "socom-recon-planner"
    assert packet["allowed_paths"] == [
        "build/type-plans/zdb-cvisual-layout.json", "build/type-plans/zdb-cvisual-layout.txt", "build/type-plans/zdb-cvisual.json",
    ]
    assert any("recon layout --class zdb::CVisual --with-derived" in line for line in packet["validation"])


def test_struct_type_plan_items_record_struct_mode(decomposed: dict) -> None:
    with pytest.raises(SocomError, match="no derived classes"):
        add_type_plan_items(decomposed, "tag_ObjectHeader", True, struct=True)
    ids = add_type_plan_items(decomposed, "tag_ObjectHeader", False, struct=True)
    assert ids == ["socom:work:type-plan-tag-objectheader", "socom:work:type-plan-tag-objectheader-apply"]
    refresh_ready_and_stages(decomposed)
    assert audit_tracker(decomposed, strict=True) == []
    by_id = {row["id"]: row for row in decomposed["work_items"]}
    plan, apply = by_id[ids[0]], by_id[ids[1]]
    assert plan["batch"] == apply["batch"] == {"class": "tag_ObjectHeader", "with_derived": False, "struct": True}
    assert (plan["kind"], apply["kind"], apply["dependencies"]) == (TYPE_PLAN_KIND, TYPE_APPLY_KIND, [ids[0]])
    assert plan["title"] == "Plan the code-derived layout of the plain struct tag_ObjectHeader"
    assert set(ids) <= set(by_id[RECON_SEED_ID]["dependencies"])
    claim_work(decomposed, ids[0], "planner", 30)
    packet = work_packet(decomposed, ids[0], "planner")
    assert (
        "python tools/socom.py recon layout --class tag_ObjectHeader --struct --output build/type-plans/tag-objectheader-layout.json"
        in packet["validation"]
    )
    broken = copy.deepcopy(decomposed)
    next(row for row in broken["work_items"] if row["id"] == ids[0])["batch"]["with_derived"] = True
    assert any("plain struct with derived classes" in text for text in audit_tracker(broken))


def _struct_layout() -> dict:
    sites = [
        _site("0x30c340", 0x4, "store", width=4, kind="int", root="param a2"),
        _site("0x30ae58", 0x8, "store", width=4, kind="int", root="built@0x30adf4"),
        _site("0x30c6a4", 0xC, "store", width=4, kind="zero", constant=0, root="param a2"),
    ]
    return {
        "kind": "socom-type-layout-evidence", "schema_version": 2, "class": "tag_ObjectHeader", "with_derived": False,
        "struct": True,
        "classes": [{
            "class": "tag_ObjectHeader", "role": "requested", "size_evidence": [], "bases": [], "vtable": None,
            "offsets": [{"offset": site["offset"], "sites": [site], "conflicts": []} for site in sites], "object_passes": [],
            "name_evidence": ["VuObjectSetup__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader"],
        }],
    }


def _struct_plan(layout: dict, provenance: str = "mangled-symbol") -> dict:
    return {
        "kind": "socom-code-type-plan", "schema_version": 1,
        "work_item_id": type_plan_item_id("tag_ObjectHeader"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "tag_ObjectHeader", "with_derived": False, "struct": True, "sha256": layout_sha256(layout)},
        "naming_survey": ["test fixture"],
        "types": [{
            "name": "tag_ObjectHeader", "kind": "struct", "category": "/project", "name_provenance": provenance,
            "name_evidence": ["VuObjectSetup__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader"],
            "size": 0x20, "alignment": 4, "size_evidence": ["caller-built region bound 0x20 (a1 = header + 0x20)"],
            "fields": [
                _field(4, 4, "uint", "m_program_qwc", ["0x30c340"]),
                _field(8, 4, "uint", "m_extra_qwc", ["0x30ae58"]),
                _field(0xC, 4, "uint", "m_flags", ["0x30c6a4"]),
            ],
            "padding": [{"offset": 0, "size": 4, "reason": "test"}, {"offset": 0x10, "size": 0x10, "reason": "test"}],
        }],
    }


def test_struct_plans_name_the_struct_by_its_mangled_parameters(root: Path, decomposed: dict) -> None:
    layout = _struct_layout()
    plan = _struct_plan(layout)
    add_type_plan_items(decomposed, "tag_ObjectHeader", False, struct=True)
    assert validate_type_plan(root, decomposed, plan, layout) == []
    problems = validate_type_plan(root, decomposed, _struct_plan(layout, "elf-symbol"), layout)
    assert any("a plain struct is named by mangled parameter types" in text for text in problems)
    not_struct = copy.deepcopy(decomposed)
    next(row for row in not_struct["work_items"] if row["id"] == plan["work_item_id"])["batch"].pop("struct")
    assert any("different class, derived scope or struct mode" in text for text in validate_type_plan(root, not_struct, plan, layout))
    assert "(plain struct)" in render_type_plan(plan, layout, [], None)


def test_audit_rejects_broken_type_plan_items(decomposed: dict) -> None:
    ids = add_type_plan_items(decomposed, "zdb::CVisual", False)
    broken = copy.deepcopy(decomposed)
    next(row for row in broken["work_items"] if row["id"] == ids[0])["resources"] = ["ghidra-writer"]
    assert any("type plan resources" in text for text in audit_tracker(broken))
    broken = copy.deepcopy(decomposed)
    broken["work_items"] = [row for row in broken["work_items"] if row["id"] != ids[1]]
    gate = next(row for row in broken["work_items"] if row["id"] == RECON_SEED_ID)
    gate["dependencies"] = [dep for dep in gate["dependencies"] if dep != ids[1]]
    assert any("type plan/apply item pairing" in text for text in audit_tracker(broken))
    broken = copy.deepcopy(decomposed)
    gate = next(row for row in broken["work_items"] if row["id"] == RECON_SEED_ID)
    gate["dependencies"] = [dep for dep in gate["dependencies"] if dep not in ids]
    assert any("gate does not depend" in text for text in audit_tracker(broken))


def test_affected_groups_name_the_groups_to_replan(root: Path, decomposed: dict, tmp_path: Path) -> None:
    report = affected_groups(root, decomposed, ["zdb::CVisual", "zdb::CMesh"], plans_dir=tmp_path)
    functions = {row["function"]: row for row in report["functions"]}
    assert "receiver" in functions["0x30de40"]["mentions"]
    assert "parameter" in functions["0x227b40"]["mentions"]  # zdb::CNode::AddVisual(zdb::CVisual*)
    group = functions["0x30de40"]["group"]
    slug = group.replace(":", "-")
    (tmp_path / f"{slug}.json").write_text(
        json.dumps({"functions": [{"address": "0x30de40", "prototype": None, "unresolved": ["receiver type zdb::CVisual is absent from the live program"]}]}),
        encoding="utf-8",
    )
    report = affected_groups(root, decomposed, ["zdb::CVisual", "zdb::CMesh"], plans_dir=tmp_path)
    row = next(item for item in report["functions"] if item["function"] == "0x30de40")
    assert row["plan_row"] == "unresolved-for-type"
    assert group in report["replan_candidates"]


def test_apply_command_checks_the_contract_then_runs_the_type_executor(
    root: Path, decomposed: dict, vis_params: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib
    import shutil

    from tools._socom import cli, ghidra

    work = tmp_path / "root"
    (work / "support").mkdir(parents=True)
    (work / ".agent").mkdir()
    (work / "build" / "type-plans").mkdir(parents=True)
    try:
        import os

        os.link(root / "support" / "socom.elf", work / "support" / "socom.elf")
    except OSError:
        shutil.copyfile(root / "support" / "socom.elf", work / "support" / "socom.elf")
    plan_id, apply_id = add_type_plan_items(decomposed, "zdb::tag_VIS_PARAMS", False)
    offsets = {row["offset"]: [site["site"] for site in row["sites"]] for row in vis_params["classes"][0]["offsets"]}
    fields = [_field(0, 4, "uint", "m_word", offsets[0])]
    fields += [_field(offset, 1, "uchar", f"m_byte{offset}", offsets[offset]) for offset in (4, 5, 6, 7)]
    fields += [_field(8, 4, "uint", "m_pair", offsets[8])]
    fields += [_field(offset, 4, "float", f"m_value{offset}", offsets[offset]) for offset in (12, 16, 20)]
    plan = {
        "kind": "socom-code-type-plan", "schema_version": 1, "work_item_id": plan_id,
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "zdb::tag_VIS_PARAMS", "with_derived": False, "sha256": layout_sha256(vis_params)},
        "naming_survey": ["test fixture"],
        "types": [{
            "name": "zdb::tag_VIS_PARAMS", "kind": "struct", "category": "/project/zdb", "name_provenance": "elf-symbol",
            "size": 24, "alignment": 4, "size_evidence": ["operator= copies 0x0-0x17"], "fields": fields,
        }],
    }
    plan_path = work / "build" / "type-plans" / "zdb-tag-vis-params.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    by_id = {row["id"]: row for row in decomposed["work_items"]}
    by_id[plan_id].update(status="accepted", handoff={"owner": "planner", "evidence": [f"plan-sha256:{digest}"]}, accepted={"by": "reviewer"})
    by_id[apply_id].update(status="in_progress", lease={"owner": "writer", "expires_at": "2099-01-01T00:00:00Z"})
    (work / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(json.dumps(decomposed), encoding="utf-8")

    def run(*argv: str) -> tuple[int, dict]:
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--root", str(work), *argv])
        return code, json.loads(out.getvalue())

    code, result = run("recon", "type-plan", "validate", "--plan", "build/type-plans/zdb-tag-vis-params.json")
    assert code == 0 and result["ok"], result
    code, result = run("recon", "type-plan", "program", "--plan", "build/type-plans/zdb-tag-vis-params.json", "--output", "build/apply/tvp.json")
    assert code == 0
    program = json.loads((work / "build" / "apply" / "tvp.json").read_text(encoding="utf-8"))
    bridges: list[_Bridge] = []

    def bridge_factory(url, timeout=0.0):
        bridges.append(_Bridge(program))
        return bridges[-1]

    monkeypatch.setattr(ghidra, "GhidraBridge", bridge_factory)
    monkeypatch.setattr(ghidra, "live_preflight", lambda root, bridge_url=None, strict_baseline=None: {"ok": True})
    monkeypatch.setattr(ghidra, "_type_index", lambda bridge: bridge.index())
    common = (
        "--program", "build/apply/tvp.json", "--item", apply_id, "--owner", "writer",
        "--scope-output", "build/receipts/tvp-scope.json", "--report-output", "build/apply/tvp-report.json",
    )
    code, result = run("ghidra", "apply-type-plan", *common, "--dry-run")
    assert code == 0 and result["ok"] and result["writes"] == 0 and not bridges[-1].calls
    code, result = run("ghidra", "apply-type-plan", *common, "--owner", "someone-else")
    assert code == 2 and "leased by writer" in result["error"]
    code, result = run("ghidra", "apply-type-plan", *common)
    assert code == 0 and result["ok"] and result["result"]["type_count"] == 1
    scope = json.loads((work / "build" / "receipts" / "tvp-scope.json").read_text(encoding="utf-8"))
    assert scope["types"] == ["/project/zdb/tag_VIS_PARAMS"]
    # An edited program is refused before any bridge call.
    program["types"][0]["size"] = 28
    (work / "build" / "apply" / "tvp.json").write_text(json.dumps(program), encoding="utf-8")
    calls = len(bridges)
    code, result = run("ghidra", "apply-type-plan", *common)
    assert code == 2 and "stale or edited" in result["error"] and len(bridges) == calls


# -- forward declarations, sub-object attribution, template instantiations ------

DETAIL = "zdb::tag_DETAIL_PARAMS"
DETAIL_SYMBOLS = [
    "VuDetailMap__Q23zdb7CVisualFP8_word128PQ23zdb17tag_DETAIL_PARAMS",
    "VuBatchProgram__Q23zdb7CVisualFP8_word128P16tag_ObjectHeaderPQ23zdb17tag_DETAIL_PARAMS",
]
LOD = "zdb::CMesh::CMeshLOD"
VEC = f"std::vector<{LOD}, std::allocator<{LOD}>>"
IMP = f"std::__vector_imp<{LOD}, std::allocator<{LOD}>, 0>"
DEL = f"std::__vector_deleter<{LOD}, std::allocator<{LOD}>>"
SEQ = "Particle::SequenceEntry<float>"


def _forward(name: str = DETAIL, symbols: list[str] | None = None, **extra) -> dict:
    return {
        "name": name, "kind": "forward", "category": plans.expected_category(name), "name_provenance": "mangled-symbol",
        "name_evidence": list(DETAIL_SYMBOLS if symbols is None else symbols), "reason": "no layout evidence", **extra,
    }


def _forward_plan(layout: dict) -> dict:
    plan = _plan(layout)
    _types(plan)["zdb::CTest"]["fields"][0]["type"] = f"{DETAIL} *"
    plan["types"].append(_forward())
    return plan


def test_forward_declarations_are_proven_pointer_targets_created_first(root: Path, tmp_path: Path) -> None:
    layout = _layout()
    plan = _forward_plan(layout)
    assert validate_type_plan(root, None, plan, layout) == []

    def problems(mutate) -> list[str]:
        broken = copy.deepcopy(plan)
        mutate(broken)
        return validate_type_plan(root, None, broken, layout)

    expected = [
        (lambda p: _types(p)["zdb::CTest"]["fields"][0].update(type=DETAIL), "can only be pointed to"),
        (lambda p: _types(p)[DETAIL].update(name_evidence=["Init__Q23zdb14CMeshDecalPoolFUiUi"]), "does not name zdb::tag_DETAIL_PARAMS"),
        (lambda p: _types(p)[DETAIL].update(name_evidence=["NoSuchSymbol__Fv"]), "is not an ELF symbol"),
        (lambda p: _types(p)[DETAIL].update(name_provenance="invented-provisional"), "a forward declaration's name is proven"),
        (lambda p: _types(p)[DETAIL].update(size=16, fields=[]), "has no layout (size)"),
        (lambda p: _types(p)[DETAIL].pop("reason"), "records why no layout is planned"),
        (lambda p: _types(p)["zdb::CTest"]["fields"][0].update(type="zdb::tag_TEST *"), "no plan member points to"),
        (lambda p: p["types"].remove(_types(p)[DETAIL]), "type base zdb::tag_DETAIL_PARAMS is not a Ghidra builtin"),
    ]
    for mutate, text in expected:
        found = problems(mutate)
        assert any(text in item for item in found), (text, found)

    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    program = build_type_plan_program(root, None, path, layout)
    first = program["types"][0]
    assert first["path"] == "/project/zdb/tag_DETAIL_PARAMS" and first["declaration"] is True
    assert first["route"] == "empty" and first["size"] is None and first["expected_layout"] == []
    assert program["summary"]["forward_declaration_count"] == 1
    test_entry = next(entry for entry in program["types"] if entry["path"] == "/project/zdb/CTest")
    assert next(field for field in test_entry["fields"] if field["name"] == "m_next")["type"] == f"{first['temp']} *"
    bridge = _Bridge(program)
    assert type_apply.execute_apply_program(program, bridge, type_index=bridge.index)["ok"] is True
    created = [body["name"] for endpoint, body in bridge.calls if endpoint == "create_struct"]
    assert created[0] == first["temp"]  # created first, as an empty structure

    # Live: the name must not exist anywhere, nor as an identity-unresolved variant.
    assert live_type_problems(program, []) == []
    for row in ({"name": "tag_DETAIL_PARAMS", "path": "/project/other/tag_DETAIL_PARAMS"},
                {"name": "tag_DETAIL_PARAMS@0123456789", "path": "/project/unresolved/tag_DETAIL_PARAMS@0123456789"}):
        assert any("tag_DETAIL_PARAMS" in text for text in live_type_problems(program, [row])), row


def _subobject_layout() -> dict:
    """zdb::CTest (0x20): a CDynTexList at +0x4 whose second vector's empty compile_assert base ends at +0x1c."""

    sites = [
        _site("0x100000", 0x0, "load", width=4, kind="int"),
        _site("0x100004", 0x4, "address-passed", register="a0", parameter_type="zdb::CDynTexList * (receiver)",
              callee="zdb::CDynTexList::Add(zdb::CTexHandle*, bool)"),
        _site("0x100008", 0x10, "address-passed", register="a0", parameter_type="Metrowerks::compile_assert<1> * (receiver)",
              callee="Metrowerks::compile_assert<1>::__ct(void)"),
        _site("0x10000c", 0x1c, "address-passed", register="a0", parameter_type="Metrowerks::compile_assert<1> * (receiver)",
              callee="Metrowerks::compile_assert<1>::__ct(void)"),
        _site("0x100010", 0x1c, "load", width=4, kind="int"),
        _site("0x100014", 0x1c, "deref-load", pointer=True, pointee_width=2, pointee_kind="int", through="+0x8"),
    ]
    rows: dict[int, list[dict]] = {}
    for site in sites:
        rows.setdefault(site["offset"], []).append(site)
    return {
        "kind": "socom-type-layout-evidence", "schema_version": 1, "class": "zdb::CTest", "with_derived": False,
        "classes": [{
            "class": "zdb::CTest", "role": "requested", "size_evidence": [0x20], "bases": [], "vtable": None,
            "offsets": [{"offset": offset, "sites": rows[offset], "conflicts": []} for offset in sorted(rows)], "object_passes": [],
        }],
    }


def _subobject_plan(layout: dict, pointer: str = f"{DETAIL} *") -> dict:
    return {
        "kind": "socom-code-type-plan", "schema_version": 1, "work_item_id": type_plan_item_id("zdb::CTest"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "zdb::CTest", "with_derived": False, "sha256": layout_sha256(layout)},
        "naming_survey": ["test fixture"],
        "types": [
            {
                "name": "zdb::CTest", "kind": "class", "category": "/project/zdb", "name_provenance": "elf-symbol",
                "size": 0x20, "alignment": 4,
                "fields": [
                    _field(0, 4, "uint", "m_flags", ["0x100000"]),
                    _field(4, 0x18, "/project/zdb/CDynTexList", "m_lists", ["0x100004"]),
                    _field(0x1c, 4, pointer, "m_detail", ["0x100010", "0x100014"], unresolved="pointee not planned"),
                ],
            },
            _forward(),
        ],
    }


def test_a_call_on_an_empty_base_at_an_objects_end_belongs_to_that_object(root: Path) -> None:
    from tools._socom.type_plan_evidence import TypeEvidence

    # DWARF: CDynTexList (24 bytes) holds two 12-byte vectors whose __vector_imp has an
    # empty compile_assert base at +0xc, so one lies at +0x18, the object's end.
    nested = TypeEvidence(root).nested("CDynTexList", 24)
    assert {(0, "CDynTexList"), (0xC, "compile_assert"), (0x18, "compile_assert")} <= nested
    layout = _subobject_layout()
    plan = _subobject_plan(layout)
    # Regression: the compile_assert<1> constructor at +0x1c (0x10000c) was attributed to the
    # pointer field m_detail, which then failed against the receiver type.
    assert validate_type_plan(root, None, plan, layout) == []
    problems = validate_type_plan(root, None, _subobject_plan(layout, "void *"), layout)
    assert not any("compile_assert" in text for text in problems), problems
    # Citing the claimed call as the field's evidence is refused.
    cited = copy.deepcopy(plan)
    _types(cited)["zdb::CTest"]["fields"][2]["evidence"].append("0x10000c")
    assert any("sub-object that lies there, not this field" in text for text in validate_type_plan(root, None, cited, layout))
    # Without the CDynTexList the calls on +0x4, +0x10 and +0x1c have no sub-object and are problems.
    flat = copy.deepcopy(plan)
    _types(flat)["zdb::CTest"]["fields"][1] = _field(4, 0x18, "undefined4[6]", "m_words", ["0x100004"])
    problems = validate_type_plan(root, None, flat, layout)
    for offset in ("0x4", "0x10", "0x1c"):
        assert any(f"passes this+{offset} as" in text and "sub-object" in text for text in problems), (offset, problems)
    rendered = render_type_plan(plan, layout, [], TypeEvidence(root))
    assert "0x10000c" in rendered and "calls this member's empty Metrowerks::compile_assert\\<1> at its end (+0x18)" in rendered


def test_an_address_pass_without_a_derivable_parameter_type_must_be_explained(root: Path) -> None:
    layout = _subobject_layout()
    untyped = _site("0x100018", 0x10, "address-passed", register="a1", callee="indirect",
                    parameter_unknown="indirect call: the callee is not known")
    layout["classes"][0]["offsets"][2]["sites"].append(untyped)
    plan = _subobject_plan(layout)
    problems = validate_type_plan(root, None, plan, layout)
    assert any(
        "0x100018 passes this+0x10 in a1 to indirect, whose parameter type is not derivable "
        "(indirect call: the callee is not known)" in text for text in problems
    ), problems
    # A note of the member that holds +0x10 citing the site (or a range holding it) explains it.
    for note in ("0x100018 passes the inner vector to a function pointer", "copied at 0x100010-0x10001c"):
        explained = copy.deepcopy(plan)
        _types(explained)["zdb::CTest"]["fields"][1]["notes"] = note
        assert validate_type_plan(root, None, explained, layout) == [], note
    # A register the callee does not take is not evidence.
    untyped.pop("parameter_unknown")
    untyped["no_parameter"] = True
    plan["layout"]["sha256"] = layout_sha256(layout)
    assert validate_type_plan(root, None, plan, layout) == []


VECTOR_POD = "/project/std/__vector_pod<unsigned int, std::allocator<unsigned int>>"
POINTER_VECTOR = "/project/std/vector<zdb::CTexPalette *, std::allocator<zdb::CTexPalette *>>"


def _vector_layout() -> dict:
    """zdb::CTest (0x14): a uint, a 12-byte vector at +0x4 assigned member-wise, then a uint at +0x10."""

    sites = [
        _site("0x100000", 0x0, "load", width=4, kind="int"),
        _site("0x100004", 0x4, "address-passed", register="a1", parameter_type="std::__vector_pod<unsigned int, std::allocator<unsigned int>> const&",
              callee="std::__vector_pod<unsigned int, std::allocator<unsigned int>>::__as(std::__vector_pod<unsigned int, std::allocator<unsigned int>> const&)"),
        _site("0x100008", 0x10, "address-passed", register="a1", parameter_type="Metrowerks::compile_assert<1> const&",
              callee="Metrowerks::compile_assert<1>::__as(Metrowerks::compile_assert<1> const&)"),
        _site("0x10000c", 0x10, "load", width=4, kind="int"),
    ]
    rows: dict[int, list[dict]] = {}
    for site in sites:
        rows.setdefault(site["offset"], []).append(site)
    return {
        "kind": "socom-type-layout-evidence", "schema_version": 1, "class": "zdb::CTest", "with_derived": False,
        "classes": [{
            "class": "zdb::CTest", "role": "requested", "size_evidence": [0x14], "bases": [], "vtable": None,
            "offsets": [{"offset": offset, "sites": rows[offset], "conflicts": []} for offset in sorted(rows)], "object_passes": [],
        }],
    }


def _vector_plan(layout: dict, vector: str) -> dict:
    return {
        "kind": "socom-code-type-plan", "schema_version": 1, "work_item_id": type_plan_item_id("zdb::CTest"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "zdb::CTest", "with_derived": False, "sha256": layout_sha256(layout)},
        "naming_survey": ["test fixture"],
        "types": [{
            "name": "zdb::CTest", "kind": "class", "category": "/project/zdb", "name_provenance": "elf-symbol",
            "size": 0x14, "alignment": 4,
            "fields": [
                _field(0, 4, "uint", "m_flags", ["0x100000"]),
                _field(4, 12, vector, "m_items", ["0x100004"]),
                _field(0x10, 4, "uint", "m_count", ["0x10000c"]),
            ],
        }],
    }


def test_a_pointer_vector_owns_the_compile_assert_at_its_end_by_dwarf_path(root: Path) -> None:
    from tools._socom.type_plan_evidence import TypeEvidence

    evidence = TypeEvidence(root)
    # DWARF 1 names every vector instantiation "vector": the 12-byte records disagree, so the
    # empty compile_assert<1> at +0xc is only possible by name, and the import's path decides.
    assert (0xC, "compile_assert") in evidence.possible("vector", 12)
    assert (0xC, "compile_assert") not in evidence.nested("vector", 12)
    assert (0xC, "compile_assert") in evidence.nested_path(POINTER_VECTOR, 12)
    assert (0xC, "compile_assert") not in evidence.nested_path(
        "/project/std/__vector_imp<zdb::CLOD_band, std::allocator<zdb::CLOD_band>, 0>", 12
    )
    layout = _vector_layout()
    plan = _vector_plan(layout, POINTER_VECTOR)
    assert validate_type_plan(root, None, plan, layout) == []
    rendered = render_type_plan(plan, layout, [], evidence)
    assert "calls this member's empty Metrowerks::compile_assert\\<1> at its end (+0xc)" in rendered
    # Regression: a __vector_pod has no compile_assert<1>, so the member-wise assignment's call
    # on the vector's end is a problem rather than unchecked.
    problems = validate_type_plan(root, None, _vector_plan(layout, VECTOR_POD), layout)
    assert any(
        "0x100008 passes this+0x10 as Metrowerks::compile_assert<1> const&" in text
        and "no Metrowerks::compile_assert<1> sub-object at +0x10" in text
        for text in problems
    ), problems


def _instantiation_layout() -> dict:
    """zdb::CTest (0x10): a uint, then std::vector<zdb::CMesh::CMeshLOD> at +0x4."""

    sites = [
        _site("0x100000", 0x0, "load", width=4, kind="int"),
        _site("0x100004", 0x4, "address-passed", register="a0", parameter_type=f"{IMP} * (receiver)", callee=f"{IMP}::reserve(unsigned int)"),
        _site("0x100008", 0x4, "address-passed", register="a0", callee="first(void)",
              parameter_type=f"Metrowerks::details::compressed_pair_imp<std::allocator<{LOD}>, unsigned int, 1> * (receiver)"),
        _site("0x10000c", 0x8, "load", width=4, kind="int"),
        _site("0x100010", 0xC, "deref-load", pointer=True, pointee_width=4, pointee_kind="int", through="+0x4"),
    ]
    rows: dict[int, list[dict]] = {}
    for site in sites:
        rows.setdefault(site["offset"], []).append(site)
    return {
        "kind": "socom-type-layout-evidence", "schema_version": 1, "class": "zdb::CTest", "with_derived": False,
        "classes": [{
            "class": "zdb::CTest", "role": "requested", "size_evidence": [0x10], "bases": [], "vtable": None,
            "offsets": [{"offset": offset, "sites": rows[offset], "conflicts": []} for offset in sorted(rows)], "object_passes": [],
        }],
    }


def _instantiation_plan(layout: dict) -> dict:
    copy_field = lambda offset, type_name, name, evidence: {  # noqa: E731
        "offset": offset, "size": 4, "type": type_name, "name": name, "provenance": "template-copy", "evidence": evidence,
    }
    return {
        "kind": "socom-code-type-plan", "schema_version": 1, "work_item_id": type_plan_item_id("zdb::CTest"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "zdb::CTest", "with_derived": False, "sha256": layout_sha256(layout)},
        "naming_survey": ["test fixture"],
        "types": [
            {
                "name": "zdb::CTest", "kind": "class", "category": "/project/zdb", "name_provenance": "elf-symbol",
                "size": 0x10, "alignment": 4,
                "fields": [_field(0, 4, "uint", "m_flags", ["0x100000"]), _field(4, 12, VEC, "m_lods", ["0x100004"])],
            },
            {
                "name": VEC, "kind": "class", "category": "/project/std", "name_provenance": "template-instantiation",
                "size": 12, "alignment": 4, "bases": [{"type": IMP, "offset": 0}],
                "instantiation": {
                    "source": f"/project/std/vector<{SEQ}, std::allocator<{SEQ}>>", "arguments": [{"from": SEQ, "to": LOD}],
                    "source_size": 12,
                    "source_layout": [[0, 12, f"__vector_imp<{SEQ}, std::allocator<{SEQ}>, 0>",
                                       "super_vector_imp_Particle_SequenceEntry_float_std_allocator_Particle_SequenceEntry_float_0"]],
                },
            },
            {
                "name": IMP, "kind": "class", "category": "/project/std", "name_provenance": "mangled-symbol",
                "name_evidence": ["reserve__Q23std78__vector_imp<Q33zdb5CMesh8CMeshLOD,Q23std32allocator<Q33zdb5CMesh8CMeshLOD>,0>FUi"],
                "size": 12, "alignment": 4, "bases": [{"type": DEL, "offset": 0}],
                "instantiation": {
                    "source": "/project/std/__vector_imp<zdb::CLOD_band, std::allocator<zdb::CLOD_band>, 0>",
                    "arguments": [{"from": "zdb::CLOD_band", "to": LOD}], "source_size": 12,
                    "source_layout": [[0, 12, "__vector_deleter<zdb::CLOD_band, std::allocator<zdb::CLOD_band>>",
                                       "super_vector_deleter_zdb_CLOD_band_std_allocator_zdb_CLOD_band"]],
                },
            },
            {
                "name": DEL, "kind": "class", "category": "/project/std", "name_provenance": "mangled-symbol",
                "name_evidence": ["data__Q23std80__vector_deleter<Q33zdb5CMesh8CMeshLOD,Q23std32allocator<Q33zdb5CMesh8CMeshLOD>>Fv"],
                "size": 12, "alignment": 4,
                "instantiation": {
                    "source": "/project/std/__vector_deleter<zdb::CLOD_band, std::allocator<zdb::CLOD_band>>",
                    "arguments": [{"from": "zdb::CLOD_band", "to": LOD}], "source_size": 12,
                    "source_layout": [[0, 4, "compressed_pair@30d44a8521", "capacity_"], [4, 4, "uint", "size_"], [8, 4, "CLOD_band *", "data_"]],
                },
                "fields": [
                    copy_field(0, "/project/unresolved/compressed_pair@30d44a8521", "capacity_", []),
                    copy_field(4, "uint", "size_", ["0x10000c"]),
                    copy_field(8, f"{LOD} *", "data_", ["0x100010"]),
                ],
            },
            _forward(LOD, ["insert__Q23std78__vector_imp<Q33zdb5CMesh8CMeshLOD,Q23std32allocator<Q33zdb5CMesh8CMeshLOD>,0>FPQ33zdb5CMesh8CMeshLODUiRCQ33zdb5CMesh8CMeshLOD"]),
        ],
    }


def test_template_instantiations_copy_a_live_layout_with_substituted_arguments(root: Path, tmp_path: Path) -> None:
    layout = _instantiation_layout()
    plan = _instantiation_plan(layout)
    assert validate_type_plan(root, None, plan, layout) == []

    def problems(mutate) -> list[str]:
        broken = copy.deepcopy(plan)
        mutate(broken)
        return validate_type_plan(root, None, broken, layout)

    def rename_member(p: dict) -> None:
        _types(p)[DEL]["instantiation"]["source_layout"][1][3] = "count_"
        _types(p)[DEL]["fields"][1]["name"] = "count_"

    def flatten(p: dict) -> None:
        _types(p)["zdb::CTest"]["fields"][1:] = [
            _field(4, 4, "uint", "m_capacity", ["0x100004"]), _field(8, 4, "uint", "m_count", ["0x10000c"]),
            _field(12, 4, f"{LOD} *", "m_data", ["0x100010"]),
        ]
        p["types"] = [row for row in p["types"] if not row["name"].startswith("std::")]

    expected = [
        (flatten, f"passes this+0x4 as {IMP} * (receiver)"),
        (rename_member, "no DWARF record of __vector_deleter (12 bytes)"),
        (lambda p: _types(p)[DEL]["fields"][2].update(type="/project/zdb/CLOD_band *"), "with the arguments substituted is CMeshLOD *"),
        (lambda p: _types(p)[DEL]["fields"][1].update(type="float"), "contradicts float"),
        (lambda p: _types(p)[VEC]["instantiation"]["arguments"][0].update(to="zdb::CMesh::COther"), "gives vector<zdb::CMesh::COther"),
        (lambda p: _types(p)[VEC]["instantiation"].update(source="/project/std/__vector_imp<zdb::CLOD_band, std::allocator<zdb::CLOD_band>, 0>"),
         "is not an instantiation of the template vector"),
        (lambda p: _types(p)[DEL]["fields"][1].update(provenance="invented-provisional", name="m_size"), "keeps the source member name size_"),
        (lambda p: _types(p)[IMP]["bases"][0].update(name=DEL), "named __vector_deleter, the bare base type name"),
    ]
    for mutate, text in expected:
        found = problems(mutate)
        assert any(text in item for item in found), (text, found)

    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    program = build_type_plan_program(root, None, path, layout)
    entries = {entry["path"]: entry for entry in program["types"]}
    vector = entries[f"/project/std/vector<{LOD}, std::allocator<{LOD}>>"]
    assert [field["name"] for field in vector["fields"]] == ["__vector_imp"]
    assert [source["source"] for source in program["layout_sources"]] == [
        "/project/std/__vector_deleter<zdb::CLOD_band, std::allocator<zdb::CLOD_band>>",
        "/project/std/__vector_imp<zdb::CLOD_band, std::allocator<zdb::CLOD_band>, 0>",
        f"/project/std/vector<{SEQ}, std::allocator<{SEQ}>>",
    ]
    bridge = _Bridge(program)
    assert type_apply.execute_apply_program(program, bridge, type_index=bridge.index)["ok"] is True

    # Live: each source resolves exactly once and its read-back equals the recorded layout.
    index = [{"name": source["source"].rsplit("/", 1)[1], "path": source["source"]} for source in program["layout_sources"]]
    index.append({"name": "compressed_pair@30d44a8521", "path": "/project/unresolved/compressed_pair@30d44a8521"})
    recorded = {source["source"].rsplit("/", 1)[1]: {"size": source["size"], "components": source["layout"]} for source in program["layout_sources"]}
    assert live_type_problems(program, index, recorded.get) == []
    changed = dict(recorded)
    changed[index[0]["name"]] = {"size": 12, "components": [[0, 12, "x", "y"]]}
    assert any("differs from the plan's source layout" in text for text in live_type_problems(program, index, changed.get))
    assert any("resolves to nothing" in text for text in live_type_problems(program, index[1:], recorded.get))


def test_void_pointer_placeholders_for_stored_typed_parameters_are_refused() -> None:
    layout = _layout()
    layout["classes"][0]["offsets"].append(
        {"offset": 0x18, "sites": [_site("0x100018", 0x18, "store", width=4, kind="int", value="entry a1 (zdb::CMesh*)")], "conflicts": []}
    )
    plan = _plan(layout)
    test = _types(plan)["zdb::CTest"]
    test["padding"] = [{"offset": 0x1C, "size": 4, "reason": "no access"}]
    test["fields"].append(_field(0x18, 4, "void *", "m_mesh", ["0x100018"]))
    assert any("stores it as zdb::CMesh*" in text for text in validate_type_plan(Path("."), None, plan, layout))


def test_show_is_a_markdown_review_with_notes_samples_forwards_and_invented_names(root: Path) -> None:
    layout = _layout()
    for row in layout["classes"][0]["offsets"]:
        for site in row["sites"]:
            site["insn"] = f"insn-{site['site']}"
    plan = _forward_plan(layout)
    test = _types(plan)["zdb::CTest"]
    test["fields"][1]["notes"] = "scale for vector<T> | proven by 0x100010"
    test["fields"][0]["unresolved"] = "the pointee record layout is not planned"
    test["unresolved"] = ["the meaning of m_unknown is not proven"]
    text = render_type_plan(plan, layout, [])
    assert "## Forward declarations" in text and "| `zdb::tag_DETAIL_PARAMS` | `/project/zdb/tag_DETAIL_PARAMS` |" in text
    assert "`zdb::CTest.m_next`" in text
    assert "## Invented provisional names" in text and "| `m_scale` | member of `zdb::CTest` at +0x10 | `float` |" in text
    assert "| Offset | Size | Type | Name | Provenance | Evidence | Sample sites | Notes |" in text
    assert "`0x100010` `insn-0x100010` in `zdb::CTest::f(void)`" in text
    assert "scale for vector\\<T> \\| proven by 0x100010" in text
    assert "unresolved: the pointee record layout is not planned" in text
    assert "- the meaning of m_unknown is not proven" in text
    assert text.rstrip().endswith("validation: ok")
    # With the ELF, mangled name evidence is shown demangled.
    from tools._socom.type_plan_evidence import TypeEvidence

    assert "zdb::CVisual::VuDetailMap(_word128*, zdb::tag_DETAIL_PARAMS*)" in render_type_plan(plan, layout, [], TypeEvidence(root))


def test_evidence_helpers_parse_parameters_and_substitute_arguments() -> None:
    from tools._socom.type_plan_evidence import parameter_class, substitute

    assert parameter_class("zdb::CDynTexList * (receiver)") == "zdb::CDynTexList"
    assert parameter_class("std::__vector_pod<unsigned int, std::allocator<unsigned int>> const&") == (
        "std::__vector_pod<unsigned int, std::allocator<unsigned int>>"
    )
    assert parameter_class("unsigned int*") is None and parameter_class("void*") is None
    assert parameter_class("zdb::CTexHandle**") is None and parameter_class("void (*)(int)") is None
    pairs = [(SEQ, LOD)]
    assert substitute(f"__vector_imp<{SEQ}, std::allocator<{SEQ}>, 0>", pairs) == f"__vector_imp<{LOD}, std::allocator<{LOD}>, 0>"
    assert substitute("CLOD_band", [("zdb::CLOD_band", LOD)], bare=True) == "CMeshLOD"
    assert substitute("uint", [("unsigned int", "zdb::CKey")], bare=True) == "CKey"
    # A builtin is not replaced inside a longer builtin.
    assert substitute("vector<unsigned int, std::allocator<unsigned int>>", [("int", "short")]) == "vector<unsigned int, std::allocator<unsigned int>>"


@pytest.fixture(scope="module")
def cvisual_alone(root: Path) -> dict:
    return class_layout(root, "zdb::CVisual")


def test_real_compile_assert_call_after_the_dyn_tex_list_is_not_the_detail_pointer(root: Path, cvisual_alone: dict) -> None:
    """Regression: CVisual::__ct's compile_assert<1> call at +0x60 (0x30df0c) is m_dynTexList's end."""

    from tools._socom.type_plan import _Plan, _subobject_claims
    from tools._socom.type_plan_evidence import TypeEvidence

    plan = {
        "types": [
            {"name": "zdb::tag_VIS_PARAMS", "kind": "struct", "size": 24, "alignment": 4, "fields": []},
            {
                "name": "zdb::CVisual", "kind": "class", "size": 0x68, "alignment": 4,
                "bases": [{"type": "zdb::tag_VIS_PARAMS", "offset": 0}],
                "fields": [
                    {"offset": 0x48, "size": 0x18, "type": "/project/zdb/CDynTexList", "name": "m_dynTexList"},
                    {"offset": 0x60, "size": 4, "type": f"{DETAIL} *", "name": "m_detailParams"},
                ],
            },
        ]
    }
    by_class = {row["class"]: row for row in cvisual_alone["classes"]}
    index = {row["class"]: {entry["offset"]: list(entry["sites"]) for entry in row["offsets"]} for row in cvisual_alone["classes"]}
    claims, problems = _subobject_claims(_Plan(plan, TypeEvidence(root)), by_class, index)
    assert ("zdb::CVisual", 0x60, "0x30df0c", "a0") in claims
    assert ("zdb::CVisual", 0x54, "0x30def4", "a0") in claims
    assert not any("+0x60" in text or "+0x54" in text or "+0x48" in text for text in problems), problems


# -- live template arguments, void * template arguments, copy evidence ---------

PALETTE = "zdb::CTexPalette"


def _pointer_vector_rows(argument: str) -> list[dict]:
    """vector<argument*> and its __vector_imp, copied from the live CTexPalette* instantiations."""

    vec, imp = f"std::vector<{argument}*, std::allocator<{argument}*>>", f"std::__vector_imp<{argument}*, std::allocator<{argument}*>, 1>"
    common = {"kind": "class", "category": "/project/std", "name_provenance": "template-instantiation", "size": 12, "alignment": 4}
    return [
        {
            "name": vec, **common, "bases": [{"type": imp, "offset": 0}],
            "instantiation": {
                "source": f"/project/std/vector<{PALETTE}*, std::allocator<{PALETTE}*>>", "arguments": [{"from": PALETTE, "to": argument}],
                "source_size": 12,
                "source_layout": [[0, 12, f"__vector_imp<{PALETTE}*, std::allocator<{PALETTE}*>, 1>",
                                   "super_vector_imp_zdb_CTexPalette_std_allocator_zdb_CTexPalette_1"]],
            },
        },
        {
            "name": imp, **common, "bases": [{"type": VECTOR_POD, "offset": 0, "size": 12}],
            "instantiation": {
                "source": f"/project/std/__vector_imp<{PALETTE}*, std::allocator<{PALETTE}*>, 1>", "arguments": [{"from": PALETTE, "to": argument}],
                "source_size": 12,
                "source_layout": [[0, 12, "__vector_pod<unsigned int, std::allocator<unsigned int>>",
                                   "super_vector_pod_unsigned_int_std_allocator_unsigned_int"]],
            },
        },
    ]


def _pointer_vector_plan(layout: dict, argument: str) -> dict:
    plan = _vector_plan(layout, f"std::vector<{argument}*, std::allocator<{argument}*>>")
    plan["types"] += _pointer_vector_rows(argument)
    return plan


def test_a_live_type_is_a_template_argument_when_it_resolves_to_exactly_one_path(root: Path, tmp_path: Path) -> None:
    layout = _vector_layout()
    plan = _pointer_vector_plan(layout, "_word128")
    # Regression: _word128 (a live type, /project/_word128) was refused as neither a plan type nor a builtin.
    assert validate_type_plan(root, None, plan, layout) == []
    missing = validate_type_plan(root, None, _pointer_vector_plan(layout, "_word129"), layout)
    assert any("template argument _word129 is neither a plan type, a builtin, nor a type an ELF symbol" in text for text in missing), missing
    pointer = validate_type_plan(root, None, _pointer_vector_plan(layout, "_word128*"), layout)
    assert any("template argument _word128* is neither a plan type, a builtin nor a qualified live type name" in text for text in pointer), pointer
    clash = copy.deepcopy(plan)
    clash["types"].append(_forward("zdb::_word128", ["SetBuffer__Q23zdb7CVisualFP8_word128UiP8CVisBase"]))
    assert any("shares its name with the plan type zdb::_word128" in text for text in validate_type_plan(root, None, clash, layout))

    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    program = build_type_plan_program(root, None, path, layout)
    assert program["template_arguments"] == [{
        "name": "_word128", "path": "/project/_word128",
        "types": ["/project/std/__vector_imp<_word128*, std::allocator<_word128*>, 1>", "/project/std/vector<_word128*, std::allocator<_word128*>>"],
    }]
    assert program["summary"]["template_argument_count"] == 1

    # Live: the same rule as a live member type, exactly one live path and the expected one.
    def argument_problems(*paths: str) -> list[str]:
        index = [{"name": "_word128", "path": value} for value in paths]
        return [text for text in live_type_problems(program, index) if text.startswith("template argument")]

    assert argument_problems("/project/_word128") == []
    assert any("resolves to nothing, not exactly /project/_word128" in text for text in argument_problems())
    assert argument_problems("/project/_word128", "/project/sdk/_word128")  # ambiguous
    assert argument_problems("/project/sdk/_word128")  # another type of that name


def test_void_pointer_template_arguments_need_the_void_pointer_justification(root: Path) -> None:
    from tools._socom.type_plan_evidence import void_pointer_argument

    assert void_pointer_argument("/project/std/vector<void *, std::allocator<void *>>")
    assert void_pointer_argument("X<int, Y<const void*>>") and not void_pointer_argument("X<int*>")
    assert not void_pointer_argument("void *") and not void_pointer_argument("X<void (*)(int, void*)>")
    layout = _vector_layout()
    plan = _pointer_vector_plan(layout, "void")
    # Regression: a vector<void*> member passed although void * as a field type needs justification.
    problems = validate_type_plan(root, None, plan, layout)
    assert problems == [
        "type zdb::CTest field m_items: void * as a template argument of std::vector<void*, std::allocator<void*>> "
        "is a placeholder; type the argument or record why in unresolved"
    ], problems
    justified = copy.deepcopy(plan)
    _types(justified)["zdb::CTest"]["fields"][1]["unresolved"] = "the element type is not proven: nothing reads the elements"
    assert validate_type_plan(root, None, justified, layout) == []
    # A call that passes the member as exactly vector<void*> proves the argument.
    layout["classes"][0]["offsets"][1]["sites"].append(
        _site("0x100020", 0x4, "address-passed", register="a0", callee="std::vector<void*, std::allocator<void*>>::clear(void)",
              parameter_type="std::vector<void*, std::allocator<void*>> * (receiver)")
    )
    plan["layout"]["sha256"] = layout_sha256(layout)
    assert validate_type_plan(root, None, plan, layout) == []


def _copy_layout(sites: list[dict], size: int = 8) -> dict:
    rows: dict[int, list[dict]] = {}
    for site in sites:
        rows.setdefault(site["offset"], []).append(site)
    return {
        "kind": "socom-type-layout-evidence", "schema_version": 1, "class": "zdb::CTest", "with_derived": False,
        "classes": [{
            "class": "zdb::CTest", "role": "requested", "size_evidence": [size], "bases": [], "vtable": None,
            "offsets": [{"offset": offset, "sites": rows[offset], "conflicts": []} for offset in sorted(rows)], "object_passes": [],
        }],
    }


def _copy(site: str, offset: int, access: str, width: int, **fields) -> dict:
    """A load from the source (a1) or a store into this (a0) in zdb::CTest::operator=."""

    extra = {"root": "param a1"} if access == "load" else {
        "copy_of": f"zdb::CTest+{offset:#x}", "value": f"loaded {width}-byte int from zdb::CTest+{offset:#x}",
    }
    return _site(site, offset, access, width=width, kind="int", function="0x200000",
                 function_name="zdb::CTest::__as(zdb::CTest const&)", **extra, **fields)


def _copy_plan(layout: dict, fields: list[dict], padding: list[dict]) -> dict:
    return {
        "kind": "socom-code-type-plan", "schema_version": 1, "work_item_id": type_plan_item_id("zdb::CTest"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "zdb::CTest", "with_derived": False, "sha256": layout_sha256(layout)},
        "naming_survey": ["test fixture"],
        "types": [{
            "name": "zdb::CTest", "kind": "class", "category": "/project/zdb", "name_provenance": "elf-symbol",
            "size": layout["classes"][0]["size_evidence"][0], "alignment": 4, "fields": fields, "padding": padding,
        }],
    }


def test_member_wise_copies_are_width_only_evidence() -> None:
    from tools._socom.type_plan_evidence import copy_accesses

    sites = [
        _site("0x100000", 0x0, "store", width=4, kind="zero", constant=0),
        _site("0x100004", 0x4, "store", width=1, kind="zero", constant=0),
        _site("0x100010", 0x4, "load", width=1, kind="int", signed=True),
        _copy("0x200000", 0x0, "load", 4), _copy("0x200004", 0x0, "store", 4),
        _copy("0x200008", 0x4, "load", 1, signed=False), _copy("0x20000c", 0x4, "store", 1),
    ]
    layout = _copy_layout(sites)
    fields = [
        _field(0, 4, "undefined4", "m_word", ["0x100000", "0x200004"]),
        _field(4, 1, "char", "m_kind", ["0x100004", "0x100010", "0x20000c"]),
    ]
    padding = [{"offset": 5, "size": 3, "reason": "no access"}]
    plan = _copy_plan(layout, fields, padding)
    # Regression: operator='s lw/sw made m_word int-typed (no undefined4) and its lbu a zero-extending load of m_kind.
    assert validate_type_plan(Path("."), None, plan, layout) == []
    moved = _copy_layout([{**site, "copy_of": None} if site["access"] == "store" else site for site in sites])
    problems = validate_type_plan(Path("."), None, _copy_plan(moved, fields, padding), moved)
    assert any("undefined4 is a placeholder but 0x200000 proves more" in text for text in problems), problems
    assert any("loads both sign- and zero-extend" in text for text in problems), problems
    # The width still counts: a member-wise word copy contradicts a 2-byte member.
    halves = copy.deepcopy(plan)
    _types(halves)["zdb::CTest"]["fields"][0:1] = [
        _field(0, 2, "undefined2", "m_low", ["0x100000"]), _field(2, 2, "undefined2", "m_high", ["0x100000"]),
    ]
    assert any("0x200004 (store w4, a member-wise copy) contradicts the 2-byte undefined2" in text
               for text in validate_type_plan(Path("."), None, halves, layout))
    # A load whose value the copy function also uses is not a copy load.
    used = sites + [_site("0x200010", 0x0, "use", width=4, kind="int", root="param a1", function="0x200000")]
    keys = copy_accesses(_copy_layout(used)["classes"], {"zdb::CTest": [(0, 8)]})
    assert ("zdb::CTest", 0, "0x200004", "store") in keys and ("zdb::CTest", 0, "0x200000", "load") not in keys
    # show keeps the copies visible.
    text = render_type_plan(plan, layout, [])
    assert "member-wise copy (width-only evidence): 0x200000 load, 0x200004 store" in text
    assert "`0x200004` `x` in `zdb::CTest::__as(zdb::CTest const&)` (member-wise copy)" in text


def test_bulk_copies_of_a_whole_object_prove_neither_width_nor_type() -> None:
    sites = [
        _site("0x100000", 0x0, "load", width=1, kind="int", signed=False),
        _site("0x100001", 0x1, "load", width=1, kind="int", signed=False),
        _site("0x100002", 0x2, "load", width=2, kind="int", signed=False),
        _site("0x100004", 0x4, "load", width=4, kind="int"),
        _copy("0x200000", 0x0, "load", 4), _copy("0x200004", 0x0, "store", 4),
        _copy("0x200008", 0x4, "load", 4), _copy("0x20000c", 0x4, "store", 4),
    ]
    layout = _copy_layout(sites)
    fields = [
        _field(0, 1, "uchar", "m_a", ["0x100000"]), _field(1, 1, "uchar", "m_b", ["0x100001"]),
        _field(2, 2, "ushort", "m_c", ["0x100002"]), _field(4, 4, "uint", "m_d", ["0x100004"]),
    ]
    plan = _copy_plan(layout, fields, [])
    # Two word chunks tile the whole 8-byte object: a bulk copy, whose width is not m_a's.
    assert validate_type_plan(Path("."), None, plan, layout) == []
    assert "bulk copy (neither width nor type evidence): 0x200000 load, 0x200004 store" in render_type_plan(plan, layout, [])
    # Copying only the first word is a member-wise copy, whose width contradicts the 1-byte m_a.
    partial = _copy_layout(sites[:6])
    problems = validate_type_plan(Path("."), None, _copy_plan(partial, fields, []), partial)
    assert any("0x200004 (store w4, a member-wise copy) contradicts the 1-byte uchar" in text for text in problems), problems


# -- zero-fill evidence ------------------------------------------------------

_CLEAR = {"kind": "zero", "constant": 0, "value": "const 0"}


def _zero(site: str, offset: int, width: int, function: str, **fields) -> dict:
    """A store of the constant zero (``sq/sd/sw/sh zero``) into this."""

    return _site(site, offset, "store", width=width, function=function, function_name=f"zdb::CTest::Clear{function}(void)",
                 **{**_CLEAR, **fields})


def _not_zero(sites: list[dict], names: set[str]) -> list[dict]:
    """The same sites with the named zero stores turned into stores of an unknown int."""

    changed = []
    for site in sites:
        if site["site"] in names:
            site = {key: value for key, value in site.items() if key not in ("constant",)} | {"kind": "int", "value": "unknown"}
        changed.append(site)
    return changed


def test_zero_fills_prove_only_that_the_extent_is_written() -> None:
    from tools._socom.type_plan_evidence import zero_fills

    typed = [_site(f"0x1000{offset:02x}", offset, "load", width=4, kind="int") for offset in (0x0, 0x4, 0x8, 0xC, 0x10)]
    fills = [
        _zero("0x300000", 0x0, 16, "0x300000"),  # sq zero over four words
        _zero("0x300004", 0x10, 8, "0x300000"),  # sd zero over a word and the tail padding
        _zero("0x300104", 0x4, 4, "0x300100"),  # sw zero exactly matching a word: width evidence
        _zero("0x300108", 0x8, 2, "0x300100"), _zero("0x30010a", 0xA, 2, "0x300100"),  # sh zero tiling two words
        _zero("0x30010c", 0xC, 2, "0x300100"), _zero("0x30010e", 0xE, 2, "0x300100"),
    ]
    layout = _copy_layout(typed + fills, size=0x18)
    fields = [_field(offset, 4, "uint", f"m_word{offset:x}", [f"0x1000{offset:02x}"]) for offset in (0x0, 0x4, 0x8, 0xC, 0x10)]
    padding = [{"offset": 0x14, "size": 4, "reason": "only the zero-fill writes it"}]
    plan = _copy_plan(layout, fields, padding)
    # Regression: the 16- and 8-byte clears contradicted the 4-byte members they cover, and the sd its padding.
    assert validate_type_plan(Path("."), None, plan, layout) == []
    leaves = {"zdb::CTest": [(offset, 4, 4) for offset in (0x0, 0x4, 0x8, 0xC, 0x10)]}
    assert zero_fills(layout["classes"], leaves) == {
        ("zdb::CTest", offset, site, "store")
        for offset, site in ((0x0, "0x300000"), (0x10, "0x300004"), (0x8, "0x300108"), (0xA, "0x30010a"),
                             (0xC, "0x30010c"), (0xE, "0x30010e"))
    }
    # A zeroed register is a zero store too; a store of another constant is not.
    zeroed = _site("0x300200", 0x0, "store", width=8, kind="int", constant=0, function="0x300200")
    other = _site("0x300300", 0x0, "store", width=8, kind="int", constant=1, function="0x300300")
    assert zero_fills(_copy_layout([zeroed, other])["classes"], leaves) == {("zdb::CTest", 0, "0x300200", "store")}
    # Halfword clears of the elements of a two-halfword array are member-wise, not a fill; of a word they are one.
    halfwords = _copy_layout([_zero("0x300600", 0x0, 2, "0x300600"), _zero("0x300602", 0x2, 2, "0x300600"),
                              _zero("0x300604", 0x4, 4, "0x300600")])
    assert zero_fills(halfwords["classes"], {"zdb::CTest": [(0, 4, 2), (4, 4, 4)]}) == set()
    assert zero_fills(halfwords["classes"], {"zdb::CTest": [(0, 4, 4), (4, 4, 4)]}) == {
        ("zdb::CTest", 0, "0x300600", "store"), ("zdb::CTest", 2, "0x300602", "store"),
    }
    # Without the zero, the wide stores are width evidence again.
    moved = _copy_layout(_not_zero(typed + fills, {"0x300000", "0x300004"}), size=0x18)
    problems = validate_type_plan(Path("."), None, _copy_plan(moved, fields, padding), moved)
    assert any("m_word0: 0x300000 (store w16 int) contradicts uint" in text for text in problems), problems
    assert any("m_word10: 0x300004 (store w8 int) contradicts uint" in text for text in problems), problems
    assert any("padding 0x14+0x4 is accessed at zdb::CTest+0x10 (0x300004)" in text for text in problems), problems
    # A narrower zero store is still width evidence unless its fill wholly covers more than one member.
    halves = _copy_layout(typed + [_zero("0x300400", 0x10, 2, "0x300400"), _zero("0x300402", 0x12, 2, "0x300400")], size=0x18)
    problems = validate_type_plan(Path("."), None, _copy_plan(halves, fields, padding), halves)
    assert any("m_word10: 0x300400 (store w2 zero) contradicts uint" in text for text in problems), problems
    assert any("0x300402 accesses +0x12 inside the scalar field" in text for text in problems), problems
    # A zero store of the padding alone is an access of the padding.
    alone = _copy_layout(typed + [_zero("0x300500", 0x14, 4, "0x300500")], size=0x18)
    problems = validate_type_plan(Path("."), None, _copy_plan(alone, fields, padding), alone)
    assert any("padding 0x14+0x4 is accessed at zdb::CTest+0x14 (0x300500)" in text for text in problems), problems
    # show keeps the zero-fills visible; the exact clear is not one.
    cited = copy.deepcopy(plan)
    _types(cited)["zdb::CTest"]["fields"][0]["evidence"].append("0x300000")
    _types(cited)["zdb::CTest"]["fields"][1]["evidence"].append("0x300104")
    text = render_type_plan(cited, layout, [])
    assert "zero-fill (neither width nor type evidence): 0x300000 store" in text
    assert "zero-fill (neither width nor type evidence): 0x300108 store, 0x30010a store" in text
    assert "zero-fill (neither width nor type evidence): 0x30010c store, 0x30010e store" in text
    assert "`0x300000` `x` in `zdb::CTest::Clear0x300000(void)` (zero-fill)" in text
    assert "`0x300104` `x` in `zdb::CTest::Clear0x300100(void)` |" in text


def _object_header_layout(sites: list[dict] | None = None) -> dict:
    return {
        "kind": "socom-type-layout-evidence", "schema_version": 2, "class": "tag_ObjectHeader", "with_derived": False,
        "struct": True,
        "classes": [{
            "class": "tag_ObjectHeader", "role": "requested", "size_evidence": [], "bases": [], "vtable": None,
            "offsets": [
                {"offset": offset, "sites": [site for site in sites if site["offset"] == offset], "conflicts": []}
                for offset in sorted({site["offset"] for site in sites})
            ],
            "object_passes": [], "name_evidence": ["VuObjectSetup__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader"],
        }],
    }


def _object_header_sites() -> list[dict]:
    """The tag_ObjectHeader evidence: VuUpdate clears each header with two ``sq zero``, then fills it in."""

    update = {"function": "0x30a900", "function_name": "zdb::CVisual::VuUpdate(float)"}
    setup = {"function": "0x30c350", "function_name": "zdb::CVisual::VuObjectSetup(_word128*, tag_ObjectHeader*)",
             "root": "param a2"}
    first, second = {"root": "built@0x30a978", **update}, {"root": "built@0x30ac78", **update}
    return [
        _site("0x30a968", 0x0, "store", width=16, insn="sq zero,16(v0)", **first, **_CLEAR),
        _site("0x30a96c", 0x10, "store", width=16, insn="sq zero,32(v0)", **first, **_CLEAR),
        _site("0x30ac68", 0x0, "store", width=16, insn="sq zero,16(v0)", **second, **_CLEAR),
        _site("0x30ac6c", 0x10, "store", width=16, insn="sq zero,32(v0)", **second, **_CLEAR),
        _site("0x30acc0", 0x0, "store", width=4, insn="sw zero,0(s2)", **second, **_CLEAR),
        _site("0x30aa94", 0x4, "store", width=4, kind="int", insn="sw v0,4(s0)", value="unknown", **first),
        _site("0x30ae50", 0x8, "load", width=4, kind="int", insn="lw v1,8(s3)", root="built@0x30adf4", **update),
        _site("0x30c6a4", 0xC, "store", width=4, insn="sw zero,12(s2)", **setup, **_CLEAR),
        _site("0x30c6a8", 0xC, "load", width=1, kind="int", signed=False, insn="lbu a1,12(s2)", **setup),
        _site("0x30c6b4", 0xC, "store", width=1, kind="int", insn="sb v1,12(s2)", **setup,
              bitfield={"dynamic": False, "field_mask": "0x1", "ops": "and 0xfe or 0x1", "set": "0x1"}),
        _site("0x30ada0", 0x10, "store", width=4, kind="int", insn="sw v1,16(s2)", value="unknown", **second),
    ]


def _object_header_plan(layout: dict, unit: int) -> dict:
    """Four-byte members; the flag bit at +0xc in a ``unit``-byte (4: uint, 1: uchar) storage unit."""

    flag = _field(0xC, unit, "uint" if unit == 4 else "uchar", "m_flag", ["0x30c6a4", "0x30c6b4"], bit_offset=0, bit_size=1)
    padding = [{"offset": 0xC + unit, "size": 4 - unit, "reason": "test"}] if unit < 4 else []
    return {
        "kind": "socom-code-type-plan", "schema_version": 1,
        "work_item_id": type_plan_item_id("tag_ObjectHeader"),
        "target": {"source_sha256": REFERENCE_SHA256},
        "layout": {"class": "tag_ObjectHeader", "with_derived": False, "struct": True, "sha256": layout_sha256(layout)},
        "naming_survey": ["test fixture"],
        "types": [{
            "name": "tag_ObjectHeader", "kind": "struct", "category": "/project", "name_provenance": "mangled-symbol",
            "name_evidence": ["VuObjectSetup__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader"],
            "size": 0x20, "alignment": 4, "size_evidence": ["caller-built region bound 0x20 (a1 = header + 0x20)"],
            "fields": [
                _field(0x0, 4, "uint", "m_word", ["0x30acc0", "0x30a968"]),
                _field(0x4, 4, "uint", "m_program_qwc", ["0x30aa94"]),
                _field(0x8, 4, "uint", "m_extra_qwc", ["0x30ae50"]),
                flag,
                _field(0x10, 4, "uint", "m_light_count", ["0x30ada0"]),
            ],
            "padding": padding + [{"offset": 0x14, "size": 0xC, "reason": "only VuUpdate's sq zero clear writes it"}],
        }],
    }


def test_the_object_header_clear_is_a_zero_fill_not_member_widths(root: Path) -> None:
    sites = _object_header_sites()
    layout = _object_header_layout(sites)
    for unit in (4, 1):
        # Regression: VuUpdate's sq zero clears gave widths [4, 16] at +0x0/+0x10 (and [1, 4] at +0xc).
        assert validate_type_plan(root, None, _object_header_plan(layout, unit), layout) == [], unit
    clears = {"0x30a968", "0x30a96c", "0x30ac68", "0x30ac6c", "0x30c6a4"}
    moved = _object_header_layout(_not_zero(sites, clears))
    problems = validate_type_plan(root, None, _object_header_plan(moved, 1), moved)
    for text in (
        "m_word: 0x30a968 (store w16 int) contradicts uint",
        "m_word: 0x30ac68 (store w16 int) contradicts uint",
        "m_light_count: 0x30a96c (store w16 int) contradicts uint",
        "padding 0xd+0x3 is accessed at tag_ObjectHeader+0x0 (0x30a968)",
        "padding 0x14+0xc is accessed at tag_ObjectHeader+0x10 (0x30a96c)",
    ):
        assert any(text in problem for problem in problems), (text, problems)
    # The word clear at +0xc is wider than a 1-byte flag unit: a fill, unless it stores something other than zero.
    moved = _object_header_layout(_not_zero(sites, {"0x30c6a4"}))
    problems = validate_type_plan(root, None, _object_header_plan(moved, 1), moved)
    assert problems == ["type tag_ObjectHeader: padding 0xd+0x3 is accessed at tag_ObjectHeader+0xc (0x30c6a4)"], problems
    # A word clear over two halfwords is wider than the member it hits: a fill, not a contradiction.
    halves = _object_header_plan(layout, 4)
    _types(halves)["tag_ObjectHeader"]["fields"][0:1] = [
        _field(0x0, 2, "ushort", "m_low", ["0x30acc0"]), _field(0x2, 2, "ushort", "m_high", ["0x30acc0"]),
    ]
    problems = validate_type_plan(root, None, halves, layout)
    assert not any("0x30acc0 (store w4 zero) contradicts" in text for text in problems), problems  # wider: a fill
    text = render_type_plan(_object_header_plan(layout, 1), layout, [])
    assert "zero-fill (neither width nor type evidence): 0x30a968 store, 0x30ac68 store" in text
    assert "zero-fill (neither width nor type evidence): 0x30a96c store, 0x30ac6c store" in text
    assert "zero-fill (neither width nor type evidence): 0x30c6a4 store" in text
    assert "`0x30a968` `sq zero,16(v0)` in `zdb::CVisual::VuUpdate(float)` (zero-fill)" in text
    assert "`0x30acc0` `sw zero,0(s2)` in `zdb::CVisual::VuUpdate(float)`<br>" in text
    assert "zero-fill (neither width nor type evidence): 0x30c6a4" not in render_type_plan(_object_header_plan(layout, 4), layout, [])


def test_show_prints_the_holder_proof_of_each_cited_outside_site() -> None:
    proof = "element zdb::CTest* loaded @0xfc from [DWARF zdb::CHolder+0x8 m_items.data_ (storage of zdb::CTest*)]"
    layout = {
        "classes": [
            {
                "class": "zdb::CTest",
                "offsets": [
                    {
                        "offset": 4,
                        "sites": [
                            {"site": "0x100", "function": "0x200", "function_name": "Outside(zdb::CHolder*)", "root": "held@0xfc"},
                            {"site": "0x104", "function": "0x300", "function_name": "zdb::CTest::Get(void)", "root": "this"},
                            {"site": "0x108", "function": "0x200", "function_name": "Outside(zdb::CHolder*)", "root": "held@0xfc"},
                        ],
                    }
                ],
                "object_passes": [],
            }
        ],
        "functions": [{"function": "0x200", "roots": [{"register": "held@0xfc", "class": "zdb::CTest", "proof": proof}]}],
    }
    plan = {"types": [{"name": "zdb::CTest", "fields": [{"name": "m_x", "evidence": ["0x104", "0x100"]}]}]}
    # Only cited sites with a holder root are listed (0x108 is not cited, 0x104 is reached through this).
    assert plans._holder_proofs(plan, layout) == [("0x100", "Outside(zdb::CHolder*)", "held@0xfc", proof)]


# -- narrowing conversion reads -------------------------------------------------


def _narrow_plan(layout: dict, field: dict, alignment: int = 4) -> dict:
    size = layout["classes"][0]["size_evidence"][0]
    plan = _copy_plan(layout, [field], [])
    row = _types(plan)["zdb::CTest"]
    row["alignment"] = alignment
    end = field["offset"] + field["size"]
    row["padding"] = [{"offset": 0, "size": field["offset"], "reason": "no access"}] if field["offset"] else []
    if end < size:
        row["padding"].append({"offset": end, "size": size - end, "reason": "no access"})
    return plan


_TICK = {"function": "0x300000", "function_name": "CTSetMode::Tick(void)", "root": "record a0"}


def _setmode_like(offset: int = 8, store: bool = True) -> list[dict]:
    """A word written by sw whose low byte one function reads with lbu, compares and passes as a 1-byte type."""

    sites = [
        _site("0x300004", offset, "load", width=1, kind="int", signed=False, insn="lbu a1,8(s2)", **_TICK),
        _site("0x300008", offset, "use", width=1, kind="int", signed=False, use="compare", **_TICK),
        _site("0x30000c", offset, "value-passed", width=1, kind="int", signed=False, parameter_type="AI_MODE",
              callee="f(AI_MODE)", register="a1", **_TICK),
    ]
    if store:
        sites.append(_site("0x200000", 8, "store", width=4, kind="int", constant=1, value="const 1", function="0x200000"))
    return sites


def _verdict(narrowing: bool, uses: tuple[str, ...] = (), full: tuple[str, ...] = ()) -> dict:
    return {"width": 1, "signed": False, "uses": list(uses), "full": list(full), "narrowing": narrowing}


def test_a_narrowing_conversion_read_is_neither_width_nor_type_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools._socom.type_plan_evidence import TypeEvidence

    asked: list[tuple[int, int, int]] = []
    verdicts = {0x300004: _verdict(True, ("compared (0x300008)", "passed as AI_MODE (1 byte) to f(AI_MODE) (0x30000c)"))}

    def narrowing_read(self, function: int, site: int, field_size: int) -> dict | None:
        asked.append((function, site, field_size))
        return verdicts.get(site)

    monkeypatch.setattr(TypeEvidence, "narrowing_read", narrowing_read)
    layout = _copy_layout(_setmode_like(), 12)
    plan = _narrow_plan(layout, _field(8, 4, "int", "m_mode", ["0x200000", "0x300004"]))
    assert validate_type_plan(Path("."), None, plan, layout) == []
    assert asked == [(0x300000, 0x300004, 4)]
    text = render_type_plan(plan, layout, [], TypeEvidence(Path(".")))
    assert (
        "narrowing read (neither width nor type evidence): 0x300004 `lbu a1,8(s2)` in CTSetMode::Tick(void) reads the low "
        "1 byte of the 4-byte field; its value is only compared (0x300008); passed as AI_MODE (1 byte) to f(AI_MODE) (0x30000c)"
    ) in text
    assert "`0x300004` `lbu a1,8(s2)` in `CTSetMode::Tick(void)` (narrowing read)" in text
    contradictions = [
        "m_mode: 0x300004 (load w1 int) contradicts int",
        "m_mode: 0x300008 (use w1 int) contradicts int",
        "m_mode: 0x30000c (value-passed w1 int) contradicts int",
    ]
    # A full-width use of the loaded value keeps the load (and its uses) width evidence.
    verdicts[0x300004] = _verdict(False, ("compared (0x300008)",), ("passed as int to g(int) (0x30000c)",))
    problems = validate_type_plan(Path("."), None, plan, layout)
    assert all(any(text in problem for problem in problems) for text in contradictions), problems
    assert "narrowing read" not in render_type_plan(plan, layout, problems, TypeEvidence(Path(".")))
    verdicts[0x300004] = _verdict(True, ("compared (0x300008)",))
    # Not the low-order byte: a read of the word's second byte is never a conversion read.
    asked.clear()
    shifted = _copy_layout(_setmode_like(offset=9), 12)
    problems = validate_type_plan(Path("."), None, _narrow_plan(shifted, _field(8, 4, "int", "m_mode", ["0x200000"])), shifted)
    assert any("0x300004 accesses +0x9 inside the scalar field (zdb::CTest)" in text for text in problems), problems
    assert asked == []
    # Nothing proves the member wider than the read: the narrow load stays a contradiction.
    alone = _copy_layout(_setmode_like(store=False), 12)
    problems = validate_type_plan(Path("."), None, _narrow_plan(alone, _field(8, 4, "int", "m_mode", ["0x300004"])), alone)
    assert all(any(text in problem for problem in problems) for text in contradictions), problems
    assert asked == []
    # A placeholder stays refused: the word stores prove int, and undefined4 takes no conversion reads.
    problems = validate_type_plan(Path("."), None, _narrow_plan(layout, _field(8, 4, "undefined4", "m_mode", ["0x200000"])), layout)
    assert any("undefined4 is a placeholder but 0x300004 proves more" in text for text in problems), problems
    assert any("0x300004 (load w1 int) contradicts undefined4" in text for text in problems), problems
    # The conversion's sign is not the member's: an lb of a ushort's low byte is no sign-extending load of it.
    signed = [
        _site("0x300004", 8, "load", width=1, kind="int", signed=True, insn="lb a1,8(s2)", **_TICK),
        _site("0x200000", 8, "store", width=2, kind="int", constant=1, value="const 1", function="0x200000"),
    ]
    halfword = _copy_layout(signed, 12)
    plan = _narrow_plan(halfword, _field(8, 2, "ushort", "m_kind", ["0x200000", "0x300004"]), alignment=2)
    assert validate_type_plan(Path("."), None, plan, halfword) == []
    verdicts[0x300004] = _verdict(False, full=("returned in v0 (0x300010)",))
    problems = validate_type_plan(Path("."), None, plan, halfword)
    assert any("every load sign-extends (lb/lh); ushort is unsigned" in text for text in problems), problems


def _real(site: str, offset: int, access: str, function: str, name: str, **fields) -> dict:
    return {"offset": offset, "site": site, "access": access, "function": function, "function_name": name,
            "kind": "int", "root": "record a0", **fields}


_SETMODE_TICK = ("0x2b7250", "CTSetMode::Tick(_zanim_cmd_hdr*, float*)")
_SETMODE_PARSE = ("0x2b73a0", "CTSetMode::Parse(_zrdr*)")
_STANCE_BEGIN = ("0x2b5f70", "CTStance::Begin(_zanim_cmd_hdr*)")
_STANCE_PARSE = ("0x2b6010", "CTStance::Parse(_zrdr*)")
_EVENT_TICK = ("0x2bd5e0", "CTEvent::Tick(_zanim_cmd_hdr*, float*)")
_EVENT_PARSE = ("0x2bd860", "CTEvent::Parse(_zrdr*)")


def _setmode_rows() -> list[dict]:
    """The zAnim TASK_SETMODE record's +0x8 rows (``recon layout --records``)."""

    return [
        _real("0x2b72f4", 8, "load", *_SETMODE_TICK, insn="lbu a1,8(s2)", signed=False, width=1),
        _real("0x2b72f8", 8, "use", *_SETMODE_TICK, insn="bne a1,zero,0x2b7314", signed=False, use="compare", width=1),
        _real("0x2b7314", 8, "value-passed", *_SETMODE_TICK, callee="CSealCtrlAi::SetAiMode(AI_MODE)",
              insn="jal SetAiMode__11CSealCtrlAiF7AI_MODE@0x266bf0", parameter_type="AI_MODE", register="a1", signed=False,
              width=1),
        _real("0x2b7324", 8, "load", *_SETMODE_TICK, insn="lw v1,8(s2)", width=4),
        _real("0x2b732c", 8, "use", *_SETMODE_TICK, insn="bne v1,v0,0x2b7378", use="compare", width=4),
        _real("0x2b7400", 8, "store", *_SETMODE_PARSE, constant=1, insn="sw a0,8(v0)", value="const 1", width=4,
              root="record@0x2b73c4"),
        _real("0x2b7464", 8, "store", *_SETMODE_PARSE, insn="sw v0,8(s0)", value="unknown", width=4, root="record@0x2b73c4"),
    ]


def _stance_rows() -> list[dict]:
    """The TASK_STANCE record's +0xc rows."""

    return [
        _real("0x2b5fe4", 12, "value-passed", *_STANCE_BEGIN, callee="CSealCtrlAi::SetStance(SEAL_STANCE)",
              insn="jal SetStance__11CSealCtrlAiF11SEAL_STANCE@0x261d00",
              parameter_unknown="receiver unproven: SEAL_STANCE if a member, no parameter if static", register="a1",
              signed=True, width=1),
        _real("0x2b5fe8", 12, "load", *_STANCE_BEGIN, insn="lb a1,12(s1)", signed=True, width=1),
        _real("0x2b6130", 12, "store", *_STANCE_PARSE, insn="sw v1,12(v0)", value="unknown", width=4, root="record@0x2b60e8"),
    ]


def _event_rows() -> list[dict]:
    """The TASK_EVENT record's +0x20 rows."""

    return [
        _real("0x2bd800", 0x20, "load", *_EVENT_TICK, insn="lb v1,32(s0)", signed=True, width=1),
        _real("0x2bd814", 0x20, "use", *_EVENT_TICK, field_bits="0xff", insn="andi v1,v1,0x7fff", signed=True,
              use="mask 0x7fff", width=1),
        _real("0x2bd8f0", 0x20, "store", *_EVENT_PARSE, constant=1, insn="sh v1,32(v0)", value="const 1", width=2,
              root="record@0x2bd884"),
        _real("0x2bd910", 0x20, "store", *_EVENT_PARSE, insn="sh v0,32(s0)", value="unknown", width=2, root="record@0x2bd884"),
    ]


_PATTERNS = {
    # rows, record size, field, alignment, the problems the rule removes, the narrowing note
    "SETMODE": (
        _setmode_rows, 12, _field(8, 4, "int", "m_mode", ["0x2b7400", "0x2b7464", "0x2b7324", "0x2b72f4"]), 4,
        ["m_mode: 0x2b72f4 (load w1 int) contradicts int", "m_mode: 0x2b72f8 (use w1 int) contradicts int",
         "m_mode: 0x2b7314 (value-passed w1 int) contradicts int"],
        "narrowing read (neither width nor type evidence): 0x2b72f4 `lbu a1,8(s2)` in CTSetMode::Tick(_zanim_cmd_hdr*, "
        "float*) reads the low 1 byte of the 4-byte field; its value is only compared (0x2b72f8); passed as AI_MODE "
        "(1 byte) to CSealCtrlAi::SetAiMode(AI_MODE) (0x2b7314)",
    ),
    "STANCE": (
        _stance_rows, 16, _field(12, 4, "int", "m_stance", ["0x2b6130", "0x2b5fe8"]), 4,
        ["m_stance: 0x2b5fe4 (value-passed w1 int) contradicts int", "m_stance: 0x2b5fe8 (load w1 int) contradicts int"],
        "narrowing read (neither width nor type evidence): 0x2b5fe8 `lb a1,12(s1)` in CTStance::Begin(_zanim_cmd_hdr*) "
        "reads the low 1 byte of the 4-byte field; its value is only passed in a1 to CSealCtrlAi::SetStance(SEAL_STANCE): "
        "SEAL_STANCE (1 byte) if a member, no parameter if static (0x2b5fe4)",
    ),
    "EVENT": (
        _event_rows, 0x22, _field(0x20, 2, "short", "m_type", ["0x2bd8f0", "0x2bd910", "0x2bd800"]), 2,
        ["m_type: 0x2bd800 (load w1 int) contradicts short", "m_type: 0x2bd814 (use w1 int) contradicts short"],
        "narrowing read (neither width nor type evidence): 0x2bd800 `lb v1,32(s0)` in CTEvent::Tick(_zanim_cmd_hdr*, "
        "float*) reads the low 1 byte of the 2-byte field; its value is only masked 0x7fff (0x2bd814); merged into "
        "another value (0x2bd820)",
    ),
}


@pytest.mark.parametrize("pattern", sorted(_PATTERNS))
def test_zanim_task_records_read_their_wider_members_through_narrowing_conversions(
    root: Path, pattern: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools._socom.type_plan_evidence import TypeEvidence

    rows, size, field, alignment, removed, note = _PATTERNS[pattern]
    layout = _copy_layout(rows(), size)
    plan = _narrow_plan(layout, field, alignment)
    # Regression: the sw/sh-proven member's low-byte conversion read contradicted its width.
    assert validate_type_plan(root, None, plan, layout) == []
    text = render_type_plan(plan, layout, [], TypeEvidence(root))
    assert note in text, text
    monkeypatch.setattr(TypeEvidence, "narrowing_read", lambda self, function, site, field_size: None)
    assert validate_type_plan(root, None, plan, layout) == [f"type zdb::CTest field {text}" for text in removed]


def test_narrowing_reads_follow_every_use_of_the_loaded_value(root: Path) -> None:
    from tools._socom.type_plan_evidence import TypeEvidence

    evidence = TypeEvidence(root)
    setmode = evidence.narrowing_read(0x2B7250, 0x2B72F4, 4)
    assert setmode == {
        "width": 1, "signed": False, "narrowing": True, "full": [],
        "uses": ["compared (0x2b72f8)", "passed as AI_MODE (1 byte) to CSealCtrlAi::SetAiMode(AI_MODE) (0x2b7314)"],
    }
    assert evidence.narrowing_read(0x2BD5E0, 0x2BD800, 2)["uses"] == ["masked 0x7fff (0x2bd814)", "merged into another value (0x2bd820)"]
    assert evidence.narrowing_read(0x2B5F70, 0x2B5FE8, 4)["narrowing"]
    # Not narrower than the member, or not a narrow load: no verdict.
    assert evidence.narrowing_read(0x2B7250, 0x2B72F4, 1) is None
    assert evidence.narrowing_read(0x2B7250, 0x2B7324, 8) is None
    # Full-width uses: an int parameter, a word store, and a mask that extracts bits (a bitfield, not a conversion).
    for function, site, full in (
        (0x1B7C90, 0x1B7D04, "passed as int to CZAnim::GetName(int) (0x1b7d08)"),
        (0x1BEE80, 0x1BF7CC, "`sw v0,68(s1)` stores it at 4 bytes (0x1bf7d0)"),
        (0x2B9C90, 0x2B9D30, "`andi a0,a0,0xf` extracts bits 0xf of it (0x2b9d38)"),
    ):
        verdict = evidence.narrowing_read(function, site, 4)
        assert not verdict["narrowing"] and verdict["full"] == [full], verdict
    # The parameter widths: builtins, pointers, and DWARF enumerations (a composite name is not a scalar).
    widths = {text: evidence.scalar_width(text) for text in (
        "AI_MODE", "SEAL_STANCE", "CAiEvent::EVENT", "unsigned char", "short", "int", "zdb::CVisual*",
        "zdb::CVisual * (receiver)", "CVisual",
    )}
    assert widths == {
        "AI_MODE": 1, "SEAL_STANCE": 1, "CAiEvent::EVENT": 1, "unsigned char": 1, "short": 2, "int": 4, "zdb::CVisual*": 4,
        "zdb::CVisual * (receiver)": 4, "CVisual": None,
    }
    # In the validator: an int-parameter use keeps the low-byte load a contradiction of the int member.
    rows = [
        _real("0x1b7d04", 4, "load", "0x1b7c90", "zAnimFireWeaponTick(_zanim_cmd_hdr*, float*)", insn="lbu a1,6(s1)",
              signed=False, width=1),
        _real("0x1b7d00", 4, "store", "0x1b7c90", "zAnimFireWeaponTick(_zanim_cmd_hdr*, float*)", insn="sw zero,0(v0)",
              width=4),
    ]
    layout = _copy_layout(rows, 8)
    problems = validate_type_plan(root, None, _narrow_plan(layout, _field(4, 4, "int", "m_node", ["0x1b7d00", "0x1b7d04"])), layout)
    assert problems == ["type zdb::CTest field m_node: 0x1b7d04 (load w1 int) contradicts int"], problems
