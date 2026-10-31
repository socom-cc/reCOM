"""Stage 4 owner-plan drafts, schema 2 validation, the graph refresh and the source query cache."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from tools._socom import cli, source_plan_cli
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.source_cache import ensure_source_cache, load_facts, query
from tools._socom.source_draft import check_draft, compare_plans, draft_owner_plan
from tools._socom.source_graph import build_source_graph
from tools._socom.source_plan import (
    SOURCE_SEED_ID,
    SOURCE_STAGE,
    apply_reservations,
    derive_annotations,
    graph_digest,
    loaded_section_lookup,
    plan_evidence,
    validate_source_plan,
)
from tools._socom.source_refresh import refresh_source_correlation
from tools._socom.tracker import (
    audit_tracker,
    claim_work,
    decompose_source_correlation,
    handoff_work,
    refresh_ready_and_stages,
)
from tools._socom.util import SocomError

from test_source_graph import write_elf  # noqa: E402 - tests/tools is on sys.path (rootdir import mode)
from test_source_plan import undecomposed  # noqa: E402

MAIN = lambda address: "main"  # noqa: E731
CODE, DATA = "socom:window:0x140000", "socom:window:0x426400"
AUTHORED = {"candidate": "authored", "library": None, "evidence": []}
GENERATED = {"candidate": "compiler-generated", "library": None, "evidence": []}
SCE = {"candidate": "provider", "library": "SCE", "evidence": []}
A_PATH, B_PATH = "Z:\\dev\\gamez\\zFoo\\a.cpp", "Z:\\dev\\gamez\\zBar\\b.cpp"
# An MSL include path, without its drive prefix (as test_source_graph spells provider paths).
VECTOR = "\\apps\\cw301\\PS2 Support\\Msl\\MSL_C++\\MSL_Common\\Include\\vector"
SEGMENT_1 = "segment:socom:source-segment:00000000000000000001"
RESERVED = {SEGMENT_1: {"directories": ["src/gamez/zFoo"], "inferred": False, "basis": "path", "reason": None}}


def _row(kind: str, address: int, size: int, window: str, names=(), classification=AUTHORED, **fields) -> dict:
    row = {
        "id": f"socom:{kind}:0x{address:x}",
        "kind": kind,
        "address": f"0x{address:x}",
        "end": f"0x{address + size:x}",
        "size": size,
        "window": window,
        "input_section": {"basis": "section-symbol envelope", "name": ".text" if window == CODE else ".rodata"},
        "cluster": fields.pop("cluster", None),
        "tu_candidates": fields.pop("tu", []),
        "signals": fields.pop("signals", []),
        "classification": classification,
    }
    if kind == "gap":
        row.update(fill="zero", padding=True, labels=[])
    else:
        row.update(binding=names[0][1], names=[{"name": name, "binding": binding} for name, binding in names])
    row.update(fields)
    return row


def _strong(unit: str, *via: str) -> list[dict]:
    return [{"tu": unit, "strength": "strong", "via": list(via), "sinit_order": None}]


def draft_graph() -> dict:
    """Ten authored functions of a.cpp and b.cpp, three SCE functions, data of both."""

    c1, c2 = "socom:tu-cluster:0x140000", "socom:tu-cluster:0x1400a0"
    cu = {"signal": "dwarf-cu", "strength": "strong", "tu": "a.cpp", "path": A_PATH, "die_offset": "0x100",
          "low_pc": "0x140000", "high_pc": "0x140010"}
    rows = [
        _row("function", 0x140000, 16, CODE, [("a_first", "GLOBAL")], cluster=c1, tu=_strong("a.cpp", "cluster", "dwarf-cu"), signals=[cu]),
        _row("gap", 0x140010, 16, CODE, classification=GENERATED),
        _row("function", 0x140020, 16, CODE, [("a_mid", "GLOBAL")]),
        _row("function", 0x140030, 16, CODE, [("a_local", "LOCAL")], cluster=c1, tu=_strong("a.cpp", "cluster")),
        _row("function", 0x140040, 16, CODE, [("Get__4CBoxFv", "13")]),
        _row("function", 0x140050, 16, CODE, [("Inl__4CBoxFv", "13")], emitted_from_header="Z:\\dev\\gamez\\zFoo\\zfoo.h",
             signals=[{"signal": "dwarf-cu-header", "strength": "hint", "path": "Z:\\dev\\gamez\\zFoo\\zfoo.h", "die_offset": "0x200"}]),
        _row("function", 0x140060, 16, CODE, [("insert__Q23std9vector<i>Fv", "WEAK")], emitted_from_header=VECTOR,
             signals=[{"signal": "dwarf-cu-header", "strength": "hint", "path": VECTOR, "die_offset": "0x210"}]),
        _row("function", 0x140070, 16, CODE, [("boundary", "GLOBAL")]),
        _row("function", 0x140080, 16, CODE, [("Helper__13@unnamed@b_cpp@Fv", "GLOBAL")], tu=_strong("b.cpp", "unnamed-namespace"),
             signals=[{"signal": "unnamed-namespace", "strength": "strong", "tu": "b.cpp", "symbol": "Helper__13@unnamed@b_cpp@Fv"}]),
        _row("function", 0x140090, 16, CODE, [("b_two", "GLOBAL")]),
        _row("function", 0x1400a0, 16, CODE, [("sceFooInit", "GLOBAL")], classification=SCE, cluster=c2, gnu_object="0x1400a0"),
        _row("function", 0x1400b0, 16, CODE, [("sceFooHelper", "GLOBAL")], classification=SCE, cluster=c2, gnu_object="0x1400a0"),
        _row("function", 0x1400c0, 16, CODE, [("sceOther", "GLOBAL")], classification=SCE),
        _row("data", 0x426400, 8, DATA, [("@12", "LOCAL")], classification=GENERATED),
        _row("data", 0x426410, 8, DATA, [("@13", "LOCAL")], classification=GENERATED, tu=_strong("b.cpp", "file-string"),
             signals=[{"signal": "file-string", "strength": "strong", "tu": "b.cpp", "text": "b.cpp", "literal": True,
                       "string": "0x426410", "referenced_by": ["socom:function:0x140090"]}]),
        _row("data", 0x426420, 4, DATA, [("g_shared", "GLOBAL")]),
        _row("data", 0x426430, 8, DATA, [("__vt__4CBox", "GLOBAL")], classification=GENERATED),
        _row("data", 0x426440, 8, DATA, [("__RTTI__4CBox", "LOCAL")], classification=GENERATED),
        _row("data", 0x426450, 8, DATA, [("sceTable", "LOCAL")], classification=SCE, cluster=c2),
        _row("data", 0x426460, 8, DATA, [("sceRef", "GLOBAL")], classification=SCE),
    ]
    ids = [row["id"] for row in rows]

    def segment(number, members, data, mix, units):
        return {
            "id": f"socom:source-segment:{number:020x}", "segment_number": number, "window": CODE,
            "start": rows[members[0]]["address"], "end": rows[members[-1]]["end"], "function_count": sum(mix.values()),
            "artifacts": [ids[index] for index in members], "data": [ids[index] for index in data],
            "classification_mix": mix, "boundary": {}, "internal_boundaries": [],
            "tu_candidates": [{"tu": unit, "functions": 1, "strongest": "strong", "sinit_order": None} for unit in units],
        }

    graph = {
        "kind": "socom-source-graph",
        "schema_version": 1,
        "source_sha256": REFERENCE_SHA256,
        "segment_size": 200,
        "windows": [{"id": CODE, "kind": "code"}, {"id": DATA, "kind": "data"}],
        "units": [{"tu": "a.cpp", "paths": [A_PATH]}, {"tu": "b.cpp", "paths": [B_PATH]}],
        "clusters": [
            {"id": c1, "members": [ids[0], ids[3]], "units": [{"tu": "a.cpp", "signals": ["dwarf-cu"], "artifacts": 2}], "libraries": []},
            {"id": c2, "members": [ids[10], ids[11], ids[18]], "units": [], "libraries": ["libfoo"]},
        ],
        "gnu_objects": [{"address": "0x1400a0", "anchor": [{"name": "gcc2_compiled.", "symbol_index": 9}], "gcc_compiled": True,
                         "functions": [ids[10], ids[11]], "gaps": [], "end_basis": "next GNU anchor", "library": "SCE",
                         "library_basis": "__ps2_libinfo__ libfoo"}],
        "artifacts": rows,
        "segments": [
            segment(1, list(range(10)), [13, 14, 15, 16, 17], {"authored": 10}, ["a.cpp", "b.cpp"]),
            segment(2, [10, 11, 12], [18, 19], {"provider:SCE": 3}, []),
        ],
        "contradictions": [],
    }
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def draft_facts(graph: dict) -> dict:
    ids = {row["names"][0]["name"]: row["id"] for row in graph["artifacts"] if row["kind"] != "gap"}
    pairs = [
        ("a_first", "@12"), ("a_first", "g_shared"), ("b_two", "@13"), ("b_two", "g_shared"), ("b_two", "Get__4CBoxFv"),
        ("a_local", "__vt__4CBox"), ("__vt__4CBox", "__RTTI__4CBox"), ("sceFooHelper", "sceRef"), ("sceFooInit", "sceTable"),
    ]
    return {
        "references": [{"site_artifact": ids[site], "target_artifact": ids[target]} for site, target in pairs],
        "compile_units": [{"die_offset": "0x200", "object_unit": "a.cpp"}, {"die_offset": "0x210", "object_unit": "a.cpp"}],
    }


def _root(tmp_path: Path) -> Path:
    (tmp_path / "src" / "gamez" / "zFoo").mkdir(parents=True)
    (tmp_path / "src" / "gamez" / "zBar").mkdir(parents=True)
    (tmp_path / "src" / "gamez" / "zFoo" / "a.cpp").write_text("// provisional\n", encoding="utf-8")
    (tmp_path / "src" / "gamez" / "zFoo" / "zfoo.h").write_text("", encoding="utf-8")
    return tmp_path


@pytest.fixture(scope="module")
def stage3(root: Path) -> dict:
    from tools._socom.tracker import load_tracker

    return undecomposed(load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json"))


def _decompose(stage3: dict, graph: dict, reservations: dict | None = None) -> dict:
    tracker = copy.deepcopy(stage3)
    decompose_source_correlation(tracker, graph, reservations or RESERVED)
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    return tracker


@pytest.fixture()
def drafted(tmp_path: Path, stage3: dict) -> tuple[Path, dict, dict, dict]:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    root = _root(tmp_path)
    plan = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, draft_facts(graph), section_of=MAIN)
    return root, tracker, graph, plan


def _entries(plan: dict) -> dict[str, tuple[str, dict]]:
    return {
        entry["artifact"]: (owner.get("translation_unit") or owner.get("library") or owner["classification"], entry)
        for owner in plan["owners"]
        for entry in owner["artifacts"]
    }


# -- the rules -------------------------------------------------------------------


def test_draft_decides_what_the_rules_settle(drafted) -> None:
    _root_path, _tracker, _graph, plan = drafted
    assert plan["schema_version"] == 2 and plan["draft"]["rules_version"] == 1
    decided = {identity: (owner, entry["draft_rule"], entry["confidence"]) for identity, (owner, entry) in _entries(plan).items()}
    assert decided == {
        "socom:function:0x140000": ("a.cpp", "A-dwarf-cu", "high"),
        "socom:gap:0x140010": ("compiler-generated", "C-fill", "high"),
        "socom:function:0x140020": ("a.cpp", "A-between", "medium"),
        "socom:function:0x140030": ("a.cpp", "A-local-block", "high"),
        "socom:function:0x140050": ("a.cpp", "A-dwarf-header", "high"),
        "socom:function:0x140060": ("a.cpp", "A-dwarf-header", "high"),
        "socom:function:0x140080": ("b.cpp", "A-unnamed", "high"),
        "socom:function:0x140090": ("b.cpp", "A-file-string", "high"),
        "socom:data:0x426400": ("a.cpp", "D-referenced", "medium"),
        "socom:data:0x426410": ("b.cpp", "A-file-string", "high"),
        "socom:data:0x426430": ("a.cpp", "D-referenced", "medium"),
        "socom:data:0x426440": ("a.cpp", "D-referenced", "medium"),
    }
    reasons = {row["artifact"]: row["reason"] for row in plan["unresolved"]}
    assert all(row["draft"] == "open" for row in plan["unresolved"])
    # The inline instance b.cpp also calls, the function between two units
    # and data both units read stay open.
    assert reasons["socom:function:0x140040"].startswith("WEAK/inline instance between a.cpp anchors")
    assert reasons["socom:function:0x140070"].startswith("boundary function between a.cpp")
    assert "not all decided for one unit" in reasons["socom:data:0x426420"]
    assert plan["draft"]["decided"] == 12 and plan["draft"]["open"] == 3


def test_draft_rows_paths_header_emits_and_annotations(drafted) -> None:
    _root_path, _tracker, graph, plan = drafted
    a, fill, b = plan["owners"]
    assert (a["translation_unit"], a["draft_rule"], a["workspace_path"], a["provisional_file"], a["original_path"]) == (
        "a.cpp", "O-provisional", "src/gamez/zFoo/a.cpp", "src/gamez/zFoo/a.cpp", A_PATH,
    )
    assert a["confidence"] == "medium"  # the weakest of its entries
    assert (b["draft_rule"], b["workspace_path"], b["provisional_file"]) == ("O-path", "src/gamez/zBar/b.cpp", None)
    assert fill["classification"] == "compiler-generated" and fill["confidence"] == "high"
    assert plan["header_emits"] == [
        {"artifact": "socom:function:0x140050", "header": "src/gamez/zFoo/zfoo.h", "reason": "inline",
         "evidence": ["dwarf-cu-header Z:\\dev\\gamez\\zFoo\\zfoo.h"], "draft_rule": "H-dwarf-header"},
        {"artifact": "socom:function:0x140060", "header": "<vector>", "library": "MSL", "reason": "template",
         "evidence": [f"dwarf-cu-header {VECTOR}"], "draft_rule": "H-dwarf-header"},
    ]
    # The MSL template body is emitted in a.cpp by inclusion: an emits edge
    # there, not a defines edge.
    edges = {(row["artifact"], row["relation"], row["path"]) for row in plan["annotations"]}
    assert ("socom:function:0x140060", "emits", "src/gamez/zFoo/a.cpp") in edges
    assert ("socom:function:0x140060", "defines", "src/gamez/zFoo/a.cpp") not in edges
    assert ("socom:function:0x140050", "emits", "src/gamez/zFoo/zfoo.h") in edges
    assert plan["annotations"] == derive_annotations(plan, graph, MAIN)
    assert plan["draft"]["outside_reservation"] == ["src/gamez/zBar/b.cpp"]


def test_a_finished_draft_validates_and_checks(drafted) -> None:
    root, tracker, graph, plan = drafted
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert any("3 artifacts are still open in the draft" in problem for problem in report["problems"])
    assert any("lies outside the reservation" in problem for problem in report["problems"])
    # The planner resolves the open rows by hand and corrects the reservation.
    finished = copy.deepcopy(plan)
    finished["unresolved"] = [
        {"artifact": "socom:function:0x140070", "reason": "between a.cpp and b.cpp; nothing discriminates"},
        {"artifact": "socom:data:0x426420", "reason": "read by a.cpp and b.cpp; data reconcile decides"},
    ]
    finished["owners"][0]["artifacts"].append("socom:function:0x140040")
    finished["reservation"] = {"directories": ["src/gamez/zBar", "src/gamez/zFoo"], "status": "corrected",
                               "reason": "b.cpp's Z:\\dev module", "evidence": [B_PATH]}
    finished["annotations"] = derive_annotations(finished, graph, MAIN)
    report = validate_source_plan(root, tracker, finished, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    fresh = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, draft_facts(graph), section_of=MAIN)
    result = check_draft(fresh, finished)
    assert result["problems"] == [] and result["overrides"] == []
    assert (result["drafted_entries"], result["hand_entries"], result["open_rows"]) == (12, 1, 0)
    # A drafted entry the planner edited is refused; a hand move is an override.
    tampered = copy.deepcopy(finished)
    tampered["owners"][0]["artifacts"][1]["confidence"] = "high"
    assert any("differs from its A-between draft" in problem for problem in check_draft(fresh, tampered)["problems"])
    moved = copy.deepcopy(finished)
    entry = next(value for value in moved["owners"][0]["artifacts"] if isinstance(value, dict) and value["artifact"] == "socom:data:0x426400")
    moved["owners"][0]["artifacts"].remove(entry)
    moved["owners"][2]["artifacts"].append("socom:data:0x426400")
    result = check_draft(fresh, moved)
    assert result["problems"] == [] and result["overrides"][0].startswith("socom:data:0x426400: the rules give a.cpp")
    claimed = copy.deepcopy(finished)
    claimed["owners"][0]["artifacts"][-1] = {"artifact": "socom:function:0x140040", "confidence": "medium", "basis": "x",
                                             "draft_rule": "A-between"}
    assert any("the rules leave it open" in problem for problem in check_draft(fresh, claimed)["problems"])
    edited = copy.deepcopy(finished)
    edited["owners"][2]["workspace_path"] = "src/gamez/zFoo/b.cpp"
    assert any("differs from its O-path draft" in problem for problem in check_draft(fresh, edited)["problems"])
    assert compare_plans(fresh, finished)["agree"] == 12


def test_provider_draft_owns_gnu_objects_and_leaves_the_rest(tmp_path: Path, stage3: dict) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    plan = draft_owner_plan(_root(tmp_path), tracker, "socom:work:source-provider-sce", graph, draft_facts(graph), section_of=MAIN)
    (owner,) = plan["owners"]
    assert owner["archive_member"] == {"gnu_object": "0x1400a0", "object": None} and owner["library"] == "SCE"
    assert [(entry["artifact"], entry["draft_rule"], entry["confidence"]) for entry in owner["artifacts"]] == [
        ("socom:function:0x1400a0", "P-gnu-object", "high"),
        ("socom:function:0x1400b0", "P-gnu-object", "high"),
        ("socom:data:0x426450", "P-gnu-data", "high"),
        ("socom:data:0x426460", "P-gnu-data", "medium"),
    ]
    assert owner["confidence"] == "medium"
    assert [row["artifact"] for row in plan["unresolved"]] == ["socom:function:0x1400c0"]
    assert "reservation" not in plan and plan["annotations"] == []


def test_draft_refuses_unknown_rules_and_existing_outputs(tmp_path: Path, stage3: dict, root: Path, capsys, monkeypatch) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    with pytest.raises(SocomError, match="rules version 9"):
        draft_owner_plan(_root(tmp_path), tracker, "socom:work:source-segment-001", graph, draft_facts(graph), rules=9, section_of=MAIN)
    workspace = _root(tmp_path / "cli")
    (workspace / ".agent").mkdir()
    (workspace / ".agent" / "RECONSTRUCTION_PROGRESS.json").write_text(json.dumps(tracker), encoding="utf-8")
    (workspace / "support").mkdir()
    shutil.copyfile(root / "support" / "socom.elf", workspace / "support" / "socom.elf")
    (workspace / "build" / "source-graph").mkdir(parents=True)
    (workspace / "build" / "source-graph" / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    monkeypatch.setattr(source_plan_cli, "_facts", lambda _root, graph, _path: draft_facts(graph))
    base = ["--root", str(workspace), "source", "plan", "draft"]
    plan_path = "build/source-plans/socom-work-source-segment-001.json"
    assert cli.main([*base, "--item", "socom:work:source-segment-001", "--output", plan_path]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["decided"], report["open"], report["outside_reservation"]) == (12, 3, ["src/gamez/zBar/b.cpp"])
    assert cli.main([*base, "--item", "socom:work:source-segment-001", "--output", plan_path]) == 2
    assert "never replaces a plan" in json.loads(capsys.readouterr().out)["error"]
    assert cli.main([*base, "--check", plan_path]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["drafted_entries"] == 12 and report["open_rows"] == 3
    assert cli.main([*base, "--output", plan_path]) == 2


# -- schema 2 validation -------------------------------------------------------------


V2_DEFECTS = [
    (lambda plan: plan["owners"][0]["artifacts"][0].pop("basis"), "needs both confidence and basis"),
    (lambda plan: plan["owners"][0]["artifacts"][0].update(confidence="certain"), "confidence must be one of"),
    (lambda plan: plan["owners"][0]["artifacts"][0].update(extra=1), "has unknown fields"),
    (lambda plan: plan["owners"][0].update(confidence="high"), "stronger than its weakest artifact's (medium)"),
    (lambda plan: plan["owners"][2].update(draft="maybe"), "draft must be 'open'"),
    (lambda plan: plan["owners"][2].update(draft="open"), "still open in the draft"),
    (lambda plan: plan["header_emits"][1].update(header="vector"), "spelled <name>"),
    (lambda plan: plan["header_emits"][1].update(library=""), "needs its library"),
    (lambda plan: plan.pop("draft") and plan.update(schema_version=1), "artifact IDs"),
    (lambda plan: plan.update(schema_version=1), "unknown fields ['draft']"),
    (lambda plan: plan.update(schema_version=3), "schema 1 or 2"),
]


def _finished(plan: dict, graph: dict) -> dict:
    finished = copy.deepcopy(plan)
    finished["unresolved"] = [{"artifact": row["artifact"], "reason": "open by hand"} for row in plan["unresolved"]]
    finished["reservation"] = {"directories": ["src/gamez/zBar", "src/gamez/zFoo"], "status": "corrected",
                               "reason": "b.cpp's module", "evidence": [B_PATH]}
    finished["annotations"] = derive_annotations(finished, graph, MAIN)
    return finished


@pytest.mark.parametrize(("change", "message"), V2_DEFECTS)
def test_schema_2_defects_are_refused(drafted, change, message: str) -> None:
    root, tracker, graph, plan = drafted
    plan = _finished(plan, graph)
    assert validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["ok"]
    change(plan)
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert any(message in problem for problem in report["problems"]), report["problems"]


def test_header_emits_must_lie_in_the_reservation(drafted) -> None:
    root, tracker, graph, plan = drafted
    plan = _finished(plan, graph)
    plan["reservation"]["directories"] = ["src/gamez/zBar"]
    plan["owners"][0]["workspace_path"] = plan["owners"][0]["provisional_file"] = None
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert any(
        "header src/gamez/zFoo/zfoo.h lies outside the reservation" in problem for problem in report["problems"]
    ), report["problems"]


def test_provider_rows_name_their_scope_library_and_may_be_linked_objects(tmp_path: Path, stage3: dict) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    root = _root(tmp_path)
    plan = draft_owner_plan(root, tracker, "socom:work:source-provider-sce", graph, draft_facts(graph), section_of=MAIN)
    plan["unresolved"] = []
    # Toolchain source compiled with the project: an object, no archive.
    plan["owners"].append({
        "translation_unit": "other.c", "classification": "provider", "workspace_path": None, "original_path": None,
        "provisional_file": None, "library": "SCE", "archive_member": {"gnu_object": None, "object": "other.o", "linked": "object"},
        "confidence": "medium", "evidence": ["sceOther"], "artifacts": ["socom:function:0x1400c0"],
    })
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    plan["owners"][1]["library"] = "MSL"
    problems = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["problems"]
    assert any("names library 'MSL'; this plan's scope is 'SCE'" in problem for problem in problems)
    plan["owners"][1].update(library="SCE", archive_member={"object": "other.o", "linked": "shared"})
    problems = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["problems"]
    assert any("linked must be one of ['archive', 'object']" in problem for problem in problems)


def test_review_notes_for_unknown_candidates_and_provider_rows_in_segments(drafted) -> None:
    root, tracker, graph, plan = drafted
    graph = copy.deepcopy(graph)
    graph["artifacts"][7]["classification"] = {"candidate": "unknown", "library": None, "evidence": []}
    graph["graph_sha256"] = graph_digest(graph)
    tracker = copy.deepcopy(tracker)
    for item in tracker["work_items"]:
        if item.get("stage") == SOURCE_STAGE and isinstance(item.get("batch"), dict) and "graph_sha256" in item["batch"]:
            item["batch"]["graph_sha256"] = graph["graph_sha256"]
    plan = _finished(plan, graph)
    plan["graph_sha256"] = graph["graph_sha256"]
    plan["unresolved"] = [row for row in plan["unresolved"] if row["artifact"] != "socom:function:0x140070"]
    plan["owners"].append({
        "translation_unit": None, "classification": "provider", "workspace_path": None, "original_path": None,
        "provisional_file": None, "library": "SCE", "archive_member": {"gnu_object": None, "object": "x.o"},
        "confidence": "low", "evidence": ["by hand"], "artifacts": ["socom:function:0x140070"],
    })
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert any("no graph classification candidate (unknown): socom:function:0x140070" in note for note in report["review"])
    assert any("this segment plan owns provider rows (SCE" in note for note in report["review"])


# -- refresh ----------------------------------------------------------------------------


def _changed(graph: dict) -> dict:
    """The draft graph with sceOther moved into segment 1 and one more provider segment gone."""

    graph = copy.deepcopy(graph)
    graph["segments"][0]["data"] = graph["segments"][0]["data"][:-1]
    graph["segments"][1]["data"].append("socom:data:0x426440")
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def test_refresh_rebuilds_batches_and_returns_handoffs_to_planning(tmp_path: Path, stage3: dict) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    claim_work(tracker, "socom:work:source-segment-001", "mapper", 30)
    handoff_work(tracker, "socom:work:source-segment-001", "mapper", "plan", ["plan sha"])
    refresh_ready_and_stages(tracker)
    new = _changed(graph)
    record = refresh_source_correlation(tracker, new, RESERVED)
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    assert audit_tracker(tracker, strict=True) == []
    by_id = {row["id"]: row for row in tracker["work_items"]}
    item = by_id["socom:work:source-segment-001"]
    assert item["status"] == "ready" and item["handoff"] is None and item["batch"]["graph_sha256"] == new["graph_sha256"]
    note = item["review_history"][-1]
    assert note["reason"] == f"graph refreshed {graph['graph_sha256']} -> {new['graph_sha256']}; replan"
    assert note["slice"] == "changed" and note["handoff"]["owner"] == "mapper"
    assert record["replan"] == ["socom:work:source-segment-001"]
    assert set(record["slice_changed"]) >= {"socom:work:source-segment-001", "socom:work:source-provider-sce"}
    assert record["added"] == [] and record["removed"] == []
    decomposition = next(row for row in tracker["stages"] if row["name"] == SOURCE_STAGE)["decomposition"]
    assert decomposition["graph_sha256"] == new["graph_sha256"] and decomposition["refreshes"] == [record]
    # Nothing changed since: nothing to refresh.
    with pytest.raises(SocomError, match="nothing to refresh"):
        refresh_source_correlation(tracker, new, RESERVED)


def test_refresh_adds_and_removes_scopes(stage3: dict) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    smaller = copy.deepcopy(graph)
    # Segment 2 becomes authored: the SCE provider items are gone, a segment item appears.
    smaller["segments"][1]["classification_mix"] = {"authored": 3}
    for row in smaller["artifacts"]:
        if row["classification"] == SCE:
            row["classification"] = AUTHORED
    smaller["graph_sha256"] = graph_digest(smaller)
    reservations = {**RESERVED, "segment:socom:source-segment:00000000000000000002":
                    {"directories": ["src/gamez/zFoo"], "inferred": False, "basis": "path", "reason": None}}
    record = refresh_source_correlation(tracker, smaller, reservations)
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    assert audit_tracker(tracker, strict=True) == []
    assert record["added"] == ["socom:work:source-segment-002", "socom:work:source-segment-002-apply"]
    assert [row["id"] for row in record["removed"]] == ["socom:work:source-provider-sce", "socom:work:source-provider-sce-apply"]
    gate = next(row for row in tracker["work_items"] if row["id"] == SOURCE_SEED_ID)
    assert "socom:work:source-segment-002-apply" in gate["dependencies"]


def test_refresh_preconditions(stage3: dict) -> None:
    graph = draft_graph()
    with pytest.raises(SocomError, match="not decomposed"):
        refresh_source_correlation(copy.deepcopy(stage3), graph, RESERVED)
    tracker = _decompose(stage3, graph)
    leased = copy.deepcopy(tracker)
    claim_work(leased, "socom:work:source-segment-001", "mapper", 30)
    with pytest.raises(SocomError, match="are leased"):
        refresh_source_correlation(leased, _changed(graph), RESERVED)
    accepted = copy.deepcopy(tracker)
    next(row for row in accepted["work_items"] if row["id"] == "socom:work:source-segment-001")["status"] = "accepted"
    with pytest.raises(SocomError, match="may not replace accepted plans"):
        refresh_source_correlation(accepted, _changed(graph), RESERVED)
    tampered = _changed(graph)
    tampered["units"] = []
    with pytest.raises(SocomError, match="valid source graph"):
        refresh_source_correlation(copy.deepcopy(tracker), tampered, RESERVED)


def test_cli_refresh_dry_run_writes_nothing(tmp_path: Path, stage3: dict, capsys, monkeypatch) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    (tmp_path / ".agent").mkdir()
    state = tmp_path / ".agent" / "RECONSTRUCTION_PROGRESS.json"
    state.write_text(json.dumps(tracker), encoding="utf-8")
    before = state.read_bytes()
    monkeypatch.setattr(cli, "source_graph", lambda _root: _changed(graph))
    monkeypatch.setattr(cli, "apply_reservations", lambda _root, _graph: RESERVED)
    base = ["--root", str(tmp_path), "progress", "decompose-stage", "--expected-revision", str(tracker["revision"])]
    assert cli.main([*base, "--stage", SOURCE_STAGE, "--refresh", "--dry-run"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["errors"] == [] and report["dry_run"]
    assert report["decomposition"]["refresh"]["to_graph_sha256"] == _changed(graph)["graph_sha256"]
    assert report["decomposition"]["refreshes"][-1]["slice_changed"]
    assert state.read_bytes() == before
    assert cli.main([*base, "--stage", "ghidra-reconstruction", "--refresh", "--dry-run"]) == 2
    assert "re-decomposes only" in json.loads(capsys.readouterr().out)["error"]


# -- the query cache ------------------------------------------------------------------------


def test_source_cache_tables_rebuild_and_refuse_writes(tmp_path: Path) -> None:
    (tmp_path / "support").mkdir()
    elf = write_elf(tmp_path / "support" / "socom.elf")
    graph = build_source_graph(elf)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.cpp").write_text("", encoding="utf-8")
    path, rebuilt = ensure_source_cache(tmp_path, graph=graph)
    assert rebuilt and path == tmp_path / "build" / "cache" / "source-graph.sqlite"
    assert ensure_source_cache(tmp_path, graph=graph) == (path, False)
    result = query(path, "SELECT id, tu, tu_strength, item FROM artifacts WHERE kind = 'function' ORDER BY address LIMIT 2")
    assert result["rows"][0] == ["socom:function:0x100000", "a.cpp", "strong", "socom:work:source-segment-001"]
    refs = query(path, "SELECT site_artifact, target_artifact, symbol, symbol_binding FROM refs WHERE type = 'R_MIPS_26'")
    assert refs["rows"] == [["socom:function:0x100020", "socom:function:0x100038", "a_assist", "LOCAL"]]
    units = query(path, "SELECT path, kind, low_pc FROM dwarf_cus")["rows"]
    assert units == [["Z:\\dev\\x\\c.cpp", "function", 0x100060]]
    assert query(path, "SELECT line FROM dwarf_lines")["rows"] == [[12]]
    assert query(path, "SELECT path FROM provisional_files")["rows"] == [["src/a.cpp"]]
    assert query(path, "SELECT count(*) FROM local_symbols")["rows"][0][0] >= 9
    facts = load_facts(path)
    assert {"site_artifact": "socom:function:0x100020", "target_artifact": "socom:function:0x100038"} in facts["references"]
    with pytest.raises(SocomError, match="single SELECT"):
        query(path, "DELETE FROM artifacts")
    with pytest.raises(SocomError, match="single SELECT"):
        query(path, "SELECT 1; SELECT 2")
    with pytest.raises(SocomError, match="query failed"):
        query(path, "SELECT nope FROM artifacts")
    # A src/ change rebuilds the cache.
    (tmp_path / "src" / "b.cpp").write_text("", encoding="utf-8")
    assert ensure_source_cache(tmp_path, graph=graph)[1] is True


def test_source_sql_cli_reads_the_graph_file(tmp_path: Path, capsys) -> None:
    (tmp_path / "support").mkdir()
    graph = build_source_graph(write_elf(tmp_path / "support" / "socom.elf"))
    (tmp_path / "build" / "source-graph").mkdir(parents=True)
    (tmp_path / "build" / "source-graph" / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    base = ["--root", str(tmp_path), "source", "sql"]
    assert cli.main([*base, "SELECT count(*) AS n FROM segments", "--format", "json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["columns"] == ["n"] and report["rows"] == [[len(graph["segments"])]] and report["rebuilt"]
    assert cli.main([*base, "SELECT number, family FROM segments ORDER BY number"]) == 0
    text = capsys.readouterr().out.splitlines()
    assert text[0] == "number\tfamily" and text[1] == "1\tauthored"
    assert cli.main([*base, "UPDATE meta SET value = 1"]) == 2


# -- the reference --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reference_draft_inputs(root: Path, stage3: dict, reference_source_graph: dict) -> tuple[dict, dict]:
    from tools._socom.source_facts import source_facts

    graph = reference_source_graph
    tracker = _decompose(stage3, graph, apply_reservations(root, graph))
    return tracker, source_facts(root, graph)


def test_reference_drafts_of_the_calibration_items(root: Path, reference_source_graph: dict, reference_draft_inputs) -> None:
    tracker, facts = reference_draft_inputs
    graph = reference_source_graph
    section_of = loaded_section_lookup(root)
    first = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, facts, section_of=section_of)
    assert (first["draft"]["decided"], first["draft"]["open"]) == (88, 1)
    assert first["unresolved"][0]["artifact"] == "socom:function:0x142130"
    assert [row["translation_unit"] for row in first["owners"] if row["classification"] == "authored"] == ["main.cpp", "st_menu.cpp"]
    msl = [row for row in first["header_emits"] if row.get("library") == "MSL"]
    assert len(first["header_emits"]) == 16 and len(msl) == 6
    assert first["draft"]["outside_reservation"] == ["src/gamez/zFTS/fts_state.h", "src/gamez/zGame/zgame.h"]
    tick = draft_owner_plan(root, tracker, "socom:work:source-segment-017", graph, facts, section_of=section_of)
    assert (tick["draft"]["decided"], tick["draft"]["open"]) == (144, 3)
    assert {row["artifact"] for row in tick["unresolved"]} == {
        "socom:function:0x1bc4a0", "socom:function:0x1bd170", "socom:function:0x1bfe80",
    }
    assert tick["draft"]["open_owner_rows"] == ["zanim_load.cpp"]
    assert tick["reservation"]["status"] == "inferred"
    crt0 = draft_owner_plan(root, tracker, "socom:work:source-provider-crt0", graph, facts, section_of=section_of)
    (owner,) = crt0["owners"]
    assert owner["archive_member"] == {"gnu_object": "0x140008", "object": None} and owner["translation_unit"] == "crt0.s"
    for plan in (first, tick, crt0):
        assert check_draft(plan, plan)["problems"] == []
    # The evidence of the crt0 item lists its GNU object; segment 017's lists
    # the unanchored function on its internal unit boundary.
    evidence = plan_evidence(root, tracker, "socom:work:source-provider-crt0", graph, section_of=section_of)
    assert [row["address"] for row in evidence["gnu_objects"]] == ["0x140008"] and evidence["moved_from_segments"] == [1]
    evidence = plan_evidence(root, tracker, "socom:work:source-segment-017", graph, section_of=section_of)
    assert any(
        "socom:function:0x1bfe80" in row["unanchored"] for segment in evidence["segments"] for row in segment["internal_boundaries"]
    )
