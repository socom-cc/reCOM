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
        (lambda plan: _types(plan)["zdb::CTest"]["fields"][1].update(name="scale"), "m_ followed by camelCase"),
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
