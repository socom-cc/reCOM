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
    """A rules version 1 draft of segment 1 (plans keep the rules they were drafted under)."""

    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    root = _root(tmp_path)
    plan = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, draft_facts(graph), rules=1, section_of=MAIN)
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


def test_rules_2_decide_a_contained_inline_copy_whoever_calls_it(tmp_path: Path, stage3: dict) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    root = _root(tmp_path)
    plan = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, draft_facts(graph), rules=2, section_of=MAIN)
    assert plan["draft"]["rules_version"] == 2 and (plan["draft"]["decided"], plan["draft"]["open"]) == (13, 2)
    owner, entry = _entries(plan)["socom:function:0x140040"]
    # b.cpp calls the inline Get copy, but it is a single copy strictly
    # between two a.cpp anchors with nothing of another unit between.
    assert (owner, entry["draft_rule"], entry["confidence"]) == ("a.cpp", "A-between", "medium")
    assert entry["basis"].startswith("inline/WEAK single copy between socom:function:0x140030 and socom:function:0x140050")
    assert check_draft(plan, plan)["problems"] == []
    # A version 1 plan is still checked under version 1, where the copy stays open.
    v1 = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, draft_facts(graph), rules=1, section_of=MAIN)
    assert "socom:function:0x140040" not in _entries(v1)
    assert any("the rules leave it open" in problem for problem in check_draft(v1, plan)["problems"])

    def redrafted(change) -> dict:
        changed = copy.deepcopy(graph)
        change({row["id"]: row for row in changed["artifacts"]})
        changed["graph_sha256"] = graph_digest(changed)
        return draft_owner_plan(root, _decompose(stage3, changed), "socom:work:source-segment-001", changed,
                                draft_facts(changed), section_of=MAIN)

    # Another copy of the same name, another unit's candidate between the
    # anchors, or a unit edge leaves it open.
    second = redrafted(lambda rows: rows["socom:function:0x140090"]["names"].append({"name": "Get__4CBoxFv", "binding": "13"}))
    assert "socom:function:0x140040" not in _entries(second)
    medium = [{"tu": "b.cpp", "strength": "medium", "via": ["cluster", "text-contiguity"], "sinit_order": None}]
    unanchor = {"signals": [], "emitted_from_header": None}
    # 0x140050 loses its anchor and has a b.cpp candidate: it lies between
    # 0x140040 and the next a.cpp anchor 0x140060.
    other = redrafted(lambda rows: rows["socom:function:0x140050"].update(**unanchor, tu_candidates=medium))
    assert "socom:function:0x140040" not in _entries(other)
    plain = redrafted(lambda rows: rows["socom:function:0x140050"].update(**unanchor))
    assert _entries(plain)["socom:function:0x140040"][0] == "a.cpp"
    edge = redrafted(lambda rows: [rows[f"socom:function:0x{address:x}"].update(**unanchor) for address in (0x140050, 0x140060)])
    assert "socom:function:0x140040" not in _entries(edge)


def test_rules_2_link_a_toolchain_assembled_gnu_object_as_an_object(tmp_path: Path, stage3: dict) -> None:
    graph = draft_graph()
    graph["artifacts"][10]["signals"] = [{"signal": "dwarf-cu", "strength": "strong", "tu": "foo.s", "path": "\\usr\\local\\sce\\foo.s",
                                         "producer": "Metrowerks MW GAS R5900 Assembler", "die_offset": "0x0"}]
    graph["graph_sha256"] = graph_digest(graph)
    tracker = _decompose(stage3, graph)
    root = _root(tmp_path)
    args = (root, tracker, "socom:work:source-provider-sce", graph, draft_facts(graph))
    (owner,) = draft_owner_plan(*args, section_of=MAIN)["owners"]
    assert owner["archive_member"] == {"gnu_object": "0x1400a0", "object": None, "linked": "object"}
    assert any("Metrowerks MW GAS R5900 Assembler" in line for line in owner["evidence"])
    (v1,) = draft_owner_plan(*args, rules=1, section_of=MAIN)["owners"]
    assert v1["archive_member"] == {"gnu_object": "0x1400a0", "object": None}
    # A GNU producer is not the project's toolchain.
    graph["artifacts"][10]["signals"][0]["producer"] = "GNU C 2.95.2"
    graph["graph_sha256"] = graph_digest(graph)
    tracker = _decompose(stage3, graph)
    (gnu,) = draft_owner_plan(root, tracker, "socom:work:source-provider-sce", graph, draft_facts(graph), section_of=MAIN)["owners"]
    assert "linked" not in gnu["archive_member"]


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
    fresh = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, draft_facts(graph), rules=1, section_of=MAIN)
    result = check_draft(fresh, finished)
    assert result["problems"] == [] and result["overrides"] == []
    assert (result["drafted_entries"], result["hand_entries"], result["open_rows"]) == (12, 1, 0)
    assert result["owner_changes"] == [] and result["header_emit_changes"] == []
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
    # Rows the planner owns by hand (draft_rule removed) are listed with
    # their changed fields, so the reviewer need not redraft.
    owned = copy.deepcopy(finished)
    del owned["owners"][2]["draft_rule"]
    owned["owners"][2]["workspace_path"] = "src/gamez/zFoo/b.cpp"
    del owned["header_emits"][0]["draft_rule"]
    owned["header_emits"].append({"artifact": "socom:function:0x140040", "header": "src/gamez/zFoo/zfoo.h", "reason": "inline",
                                  "evidence": ["by hand"]})
    owned["owners"].append({"translation_unit": "c.cpp", "classification": "authored", "artifacts": []})
    del owned["owners"][1]
    result = check_draft(fresh, owned)
    assert result["problems"] == []
    assert result["owner_changes"] == [
        {"row": "authored b.cpp", "change": ["draft_rule-removed", "fields"], "draft_rule": "O-path",
         "fields": {"workspace_path": {"draft": "src/gamez/zBar/b.cpp", "plan": "src/gamez/zFoo/b.cpp"}}},
        {"row": "authored c.cpp", "change": ["hand-row"], "draft_rule": None, "fields": {}},
        {"row": "compiler-generated", "change": ["dropped"], "draft_rule": None, "fields": {}},
    ]
    assert result["header_emit_changes"] == [
        {"row": "header_emits socom:function:0x140050", "change": ["draft_rule-removed"], "draft_rule": "H-dwarf-header", "fields": {}},
        {"row": "header_emits socom:function:0x140040", "change": ["hand-row"], "draft_rule": None, "fields": {}},
    ]


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
    assert (report["rules_version"], report["decided"], report["open"]) == (3, 13, 2)
    assert report["outside_reservation"] == ["src/gamez/zBar/b.cpp"]
    assert cli.main([*base, "--item", "socom:work:source-segment-001", "--output", plan_path]) == 2
    assert "never replaces a plan" in json.loads(capsys.readouterr().out)["error"]
    assert cli.main([*base, "--check", plan_path]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["drafted_entries"] == 13 and report["open_rows"] == 2 and report["rules_version"] == 3
    assert report["owner_changes"] == [] and report["header_emit_changes"] == []
    # A version 1 draft is checked under version 1; --rules 2 shows the new decisions.
    old_path = "build/source-plans/v1.json"
    assert cli.main([*base, "--item", "socom:work:source-segment-001", "--output", old_path, "--rules", "1"]) == 0
    assert json.loads(capsys.readouterr().out)["decided"] == 12
    assert cli.main([*base, "--check", old_path]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] and report["rules_version"] == 1 and report["plan_rules_version"] == 1
    assert cli.main([*base, "--check", old_path, "--rules", "2"]) == 0
    assert any("0x140040: the rules give a.cpp" in row for row in json.loads(capsys.readouterr().out)["overrides"])
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
    assert any("linked must be one of ['archive', 'object', 'unknown']" in problem for problem in problems)


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
    with pytest.raises(SocomError, match="changes accepted stage 4 plans' slices"):
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
    assert any(
        (row["site_artifact"], row["target_artifact"], row["symbol_type"]) == ("socom:function:0x100020", "socom:function:0x100038", "FUNC")
        for row in facts["references"]
    )
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
    # Rules version 1, the version the calibration plans were drafted under.
    first = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, facts, rules=1, section_of=section_of)
    assert (first["draft"]["decided"], first["draft"]["open"]) == (88, 1)
    assert first["unresolved"][0]["artifact"] == "socom:function:0x142130"
    assert [row["translation_unit"] for row in first["owners"] if row["classification"] == "authored"] == ["main.cpp", "st_menu.cpp"]
    msl = [row for row in first["header_emits"] if row.get("library") == "MSL"]
    assert len(first["header_emits"]) == 16 and len(msl) == 6
    assert first["draft"]["outside_reservation"] == ["src/gamez/zFTS/fts_state.h", "src/gamez/zGame/zgame.h"]
    tick = draft_owner_plan(root, tracker, "socom:work:source-segment-017", graph, facts, rules=1, section_of=section_of)
    assert (tick["draft"]["decided"], tick["draft"]["open"]) == (144, 3)
    assert {row["artifact"] for row in tick["unresolved"]} == {
        "socom:function:0x1bc4a0", "socom:function:0x1bd170", "socom:function:0x1bfe80",
    }
    assert tick["draft"]["open_owner_rows"] == ["zanim_load.cpp"]
    assert tick["reservation"]["status"] == "inferred"
    crt0 = draft_owner_plan(root, tracker, "socom:work:source-provider-crt0", graph, facts, rules=1, section_of=section_of)
    (owner,) = crt0["owners"]
    assert owner["archive_member"] == {"gnu_object": "0x140008", "object": None} and owner["translation_unit"] == "crt0.s"
    # Rules version 2: the inline GetBBox and Rotate copies other units call
    # lie strictly between zanim_cmd_tick.cpp anchors (the planner's hand
    # decision), and crt0.s, assembled by MW GAS, is a linked object.
    tick2 = draft_owner_plan(root, tracker, "socom:work:source-segment-017", graph, facts, rules=2, section_of=section_of)
    assert (tick2["draft"]["rules_version"], tick2["draft"]["decided"], tick2["draft"]["open"]) == (2, 146, 1)
    copies = {
        entry["artifact"]: (row["translation_unit"], entry["draft_rule"], entry["confidence"])
        for row in tick2["owners"] for entry in row["artifacts"]
        if entry["artifact"] in ("socom:function:0x1bc4a0", "socom:function:0x1bd170")
    }
    assert set(copies.values()) == {("zanim_cmd_tick.cpp", "A-between", "medium")} and len(copies) == 2
    (owner2,) = draft_owner_plan(root, tracker, "socom:work:source-provider-crt0", graph, facts, rules=2, section_of=section_of)["owners"]
    assert owner2["archive_member"] == {"gnu_object": "0x140008", "object": None, "linked": "object"}
    first2 = draft_owner_plan(root, tracker, "socom:work:source-segment-001", graph, facts, rules=2, section_of=section_of)
    assert (first2["draft"]["decided"], first2["draft"]["open"]) == (88, 1)
    for plan in (first, tick, crt0, tick2, first2):
        assert check_draft(plan, plan)["problems"] == []
    # A v1 crt0 row owned by hand with linked: object is listed for the reviewer.
    owned = copy.deepcopy(crt0)
    owned["owners"][0].pop("draft_rule")
    owned["owners"][0]["archive_member"]["linked"] = "object"
    assert check_draft(crt0, owned)["owner_changes"] == [{
        "row": "provider crt0.s", "change": ["draft_rule-removed", "fields"], "draft_rule": "P-gnu-object",
        "fields": {"archive_member.linked": {"draft": None, "plan": "object"}},
    }]
    # The evidence of the crt0 item lists its GNU object; segment 017's lists
    # the unanchored function on its internal unit boundary.
    evidence = plan_evidence(root, tracker, "socom:work:source-provider-crt0", graph, section_of=section_of)
    assert [row["address"] for row in evidence["gnu_objects"]] == ["0x140008"] and evidence["moved_from_segments"] == [1]
    evidence = plan_evidence(root, tracker, "socom:work:source-segment-017", graph, section_of=section_of)
    assert any(
        "socom:function:0x1bfe80" in row["unanchored"] for segment in evidence["segments"] for row in segment["internal_boundaries"]
    )


# -- rules version 3 ----------------------------------------------------------------------

MSL_PATH = "\\apps\\cw301\\PS2 Support\\Msl\\MSL_C++\\MSL_Common\\Src\\ios.cpp"
MSL = {"candidate": "provider", "library": "MSL", "evidence": []}


def mw_provider_graph() -> dict:
    """An MSL segment: ios.cpp anchors around an unanchored MSL function, and data only ios.cpp reads."""

    cluster = "socom:tu-cluster:0x140020"
    cu = {"signal": "dwarf-cu", "strength": "strong", "tu": "ios.cpp", "path": MSL_PATH, "die_offset": "0x300",
          "low_pc": "0x140000", "high_pc": "0x140010"}
    rows = [
        _row("function", 0x140000, 16, CODE, [("ios_a", "GLOBAL")], classification=MSL, tu=_strong("ios.cpp", "dwarf-cu"), signals=[cu]),
        _row("function", 0x140010, 16, CODE, [("ios_b", "GLOBAL")], classification=MSL),
        _row("function", 0x140020, 16, CODE, [("ios_c", "LOCAL")], classification=MSL, cluster=cluster, tu=_strong("ios.cpp", "cluster")),
        _row("function", 0x140030, 16, CODE, [("ios_d", "GLOBAL")], classification=MSL),
        _row("data", 0x426400, 8, DATA, [("ios_table", "GLOBAL")], classification=MSL),
    ]
    ids = [row["id"] for row in rows]
    graph = {
        "kind": "socom-source-graph", "schema_version": 1, "source_sha256": REFERENCE_SHA256, "segment_size": 200,
        "windows": [{"id": CODE, "kind": "code"}, {"id": DATA, "kind": "data"}],
        "units": [{"tu": "ios.cpp", "paths": [MSL_PATH]}],
        "clusters": [{"id": cluster, "members": [ids[2]], "units": [{"tu": "ios.cpp", "signals": ["dwarf-cu"], "artifacts": 1}], "libraries": []}],
        "gnu_objects": [],
        "artifacts": rows,
        "segments": [{
            "id": "socom:source-segment:00000000000000000001", "segment_number": 1, "window": CODE, "start": "0x140000",
            "end": "0x140040", "function_count": 4, "artifacts": ids[:4], "data": [ids[4]],
            "classification_mix": {"provider:MSL": 4}, "boundary": {}, "internal_boundaries": [], "tu_candidates": [],
        }],
        "contradictions": [],
    }
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def test_rules_3_decide_metrowerks_provider_members_by_their_unit(tmp_path: Path, stage3: dict) -> None:
    graph = mw_provider_graph()
    tracker = _decompose(stage3, graph)
    root = _root(tmp_path)
    facts = {"references": [{"site_artifact": "socom:function:0x140000", "target_artifact": "socom:data:0x426400"}], "compile_units": []}
    old = draft_owner_plan(root, tracker, "socom:work:source-provider-msl", graph, facts, rules=2, section_of=MAIN)
    assert old["owners"] == [] and old["draft"]["open"] == 5
    plan = draft_owner_plan(root, tracker, "socom:work:source-provider-msl", graph, facts, section_of=MAIN)
    assert plan["draft"]["rules_version"] == 3
    (owner,) = plan["owners"]
    assert owner["draft_rule"] == "P-mw-unit" and owner["translation_unit"] == "ios.cpp" and owner["original_path"] == MSL_PATH
    assert owner["archive_member"] == {"gnu_object": None, "object": "ios.o", "linked": "unknown"} and owner["library"] == "MSL"
    assert [(entry["artifact"], entry["draft_rule"], entry["confidence"]) for entry in owner["artifacts"]] == [
        ("socom:function:0x140000", "A-dwarf-cu", "high"),
        ("socom:function:0x140010", "A-between", "medium"),
        ("socom:function:0x140020", "A-local-block", "high"),
        ("socom:data:0x426400", "D-referenced", "medium"),
    ]
    # The function after the last anchor stays open.
    assert [row["artifact"] for row in plan["unresolved"]] == ["socom:function:0x140030"]
    plan["unresolved"] = [{"artifact": "socom:function:0x140030", "reason": "after the last ios.cpp anchor"}]
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert check_draft(draft_owner_plan(root, tracker, plan["work_item_id"], graph, facts, section_of=MAIN), plan)["problems"] == []


def _sectioned(graph: dict) -> dict:
    """The draft graph with the SCE object's LOCAL .rodata run holding sceRef and a gap after it."""

    graph = copy.deepcopy(graph)
    graph["gnu_objects"][0]["sections"] = [
        {"name": ".rodata", "symbol_index": 30, "start": "0x426450", "end": "0x426470", "end_basis": "next section symbol"}
    ]
    gap = _row("gap", 0x426468, 8, DATA, classification={"candidate": "unknown", "library": None, "evidence": []})
    gap.update(fill="nonzero", padding=False)
    graph["artifacts"].append(gap)
    graph["segments"][1]["data"].append(gap["id"])
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def test_rules_3_place_data_and_gaps_by_their_local_section_run(tmp_path: Path, stage3: dict) -> None:
    graph = _sectioned(draft_graph())
    tracker = _decompose(stage3, graph)
    facts = draft_facts(graph)
    facts["references"].append(
        {"site_artifact": "socom:function:0x1400a0", "target_artifact": "socom:gap:0x426468", "symbol_index": 30, "symbol_type": "SECTION"}
    )
    item = "socom:work:source-provider-sce"
    old = _entries(draft_owner_plan(_root(tmp_path), tracker, item, graph, facts, rules=2, section_of=MAIN))
    assert old["socom:data:0x426460"][1]["confidence"] == "medium" and "socom:gap:0x426468" not in old
    entries = _entries(draft_owner_plan(_root(tmp_path / "v3"), tracker, item, graph, facts, section_of=MAIN))
    ref = entries["socom:data:0x426460"][1]
    assert (ref["draft_rule"], ref["confidence"]) == ("P-gnu-data", "high")
    assert ref["basis"].startswith("inside GNU object 0x1400a0's .rodata section run 0x426450-0x426470")
    gap = entries["socom:gap:0x426468"][1]
    assert (gap["draft_rule"], gap["confidence"]) == ("P-gnu-section", "high")
    # A relocation from another object (or not through the section symbol) leaves the gap open.
    facts["references"][-1]["symbol_type"] = "OBJECT"
    entries = _entries(draft_owner_plan(_root(tmp_path / "v3b"), tracker, item, graph, facts, section_of=MAIN))
    assert "socom:gap:0x426468" not in entries


def test_archive_member_archive_version_and_unknown_linking(tmp_path: Path, stage3: dict) -> None:
    graph = draft_graph()
    tracker = _decompose(stage3, graph)
    root = _root(tmp_path)
    plan = draft_owner_plan(root, tracker, "socom:work:source-provider-sce", graph, draft_facts(graph), section_of=MAIN)
    plan["unresolved"] = [{"artifact": "socom:function:0x1400c0", "reason": "by hand"}]
    plan["owners"][0]["archive_member"].update(archive="libfoo.a", version="2.50", linked="unknown")
    assert validate_source_plan(root, tracker, plan, graph, section_of=MAIN)["ok"]
    for change, message in (
        ({"archive": "lib/libfoo.a"}, "archive must be the archive's file name"),
        ({"version": " "}, "version must be a non-empty string"),
        ({"linked": "maybe"}, "linked must be one of ['archive', 'object', 'unknown']"),
    ):
        broken = copy.deepcopy(plan)
        broken["owners"][0]["archive_member"].update(change)
        problems = validate_source_plan(root, tracker, broken, graph, section_of=MAIN)["problems"]
        assert any(message in problem for problem in problems), problems
    from tools._socom.source_apply import _record_lines, provider_members

    (member,) = provider_members(plan)
    assert (member["artifacts"], member["archive"], member["version"], member["linked"]) == (4, "libfoo.a", "2.50", "unknown")
    lines = _record_lines({"plan": "p", "plan_sha256": "0" * 64, "owner_map_sha256": "1" * 64, "annotations_sha256": "2" * 64,
                            "annotation_count": 0, "reservation": {"status": "none"}, "files": [], "moves": [], "created": [],
                            "retired": [], "members": [member]})
    assert lines[-1] == "source-provider-member SCE gnu_object:0x1400a0 object:- artifacts:4 archive:libfoo.a version:2.50 linked:unknown"


# -- refresh with accepted plans ------------------------------------------------------------


def _changed_elsewhere(graph: dict) -> dict:
    """The draft graph with sceRef out of the SCE slice: segment 1's slice is unchanged."""

    graph = copy.deepcopy(graph)
    graph["segments"][1]["data"] = [value for value in graph["segments"][1]["data"] if value != "socom:data:0x426460"]
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def _accept(tracker: dict, item_id: str) -> None:
    from tools._socom.tracker import accept_work

    claim_work(tracker, item_id, "mapper", 30)
    handoff_work(tracker, item_id, "mapper", "plan", ["plan sha"])
    accept_work(tracker, item_id, "reviewer", ["reviewed"])
    refresh_ready_and_stages(tracker)


def test_refresh_keeps_accepted_plans_whose_slices_are_unchanged(drafted) -> None:
    root, tracker, graph, plan = drafted
    plan = _finished(plan, graph)
    before = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert before["ok"], before["problems"]
    tracker = copy.deepcopy(tracker)
    _accept(tracker, "socom:work:source-segment-001")
    new = _changed_elsewhere(graph)
    record = refresh_source_correlation(tracker, new, RESERVED)
    refresh_ready_and_stages(tracker)
    tracker["revision"] += 1
    assert audit_tracker(tracker, strict=True) == []
    assert record["kept_accepted"] == ["socom:work:source-segment-001"]
    assert "socom:work:source-provider-sce" in record["slice_changed"]
    item = next(row for row in tracker["work_items"] if row["id"] == "socom:work:source-segment-001")
    assert item["status"] == "accepted" and item["accepted"]["by"] == "reviewer"
    assert (item["batch"]["graph_sha256"], item["batch"]["plan_graph_sha256"]) == (new["graph_sha256"], graph["graph_sha256"])
    # The accepted plan, which cites the earlier graph, validates as before.
    after = validate_source_plan(root, tracker, plan, new, section_of=MAIN)
    assert after["ok"] and {key: after[key] for key in ("summary", "review")} == {key: before[key] for key in ("summary", "review")}
    # A plan citing some other graph is still refused.
    stale = dict(plan, graph_sha256="f" * 64)
    assert any("the plan cites graph" in problem for problem in validate_source_plan(root, tracker, stale, new, section_of=MAIN)["problems"])
    # A second refresh keeps the digest the accepted plan cites.
    newer = copy.deepcopy(new)
    newer["segments"][1]["data"] = [value for value in newer["segments"][1]["data"] if value != "socom:data:0x426450"]
    newer["graph_sha256"] = graph_digest(newer)
    refresh_source_correlation(tracker, newer, RESERVED)
    item = next(row for row in tracker["work_items"] if row["id"] == "socom:work:source-segment-001")
    assert item["batch"]["plan_graph_sha256"] == graph["graph_sha256"]


def test_refresh_refuses_a_changed_accepted_slice(drafted) -> None:
    _root_path, tracker, graph, _plan = drafted
    tracker = copy.deepcopy(tracker)
    _accept(tracker, "socom:work:source-segment-001")
    with pytest.raises(SocomError, match="changes accepted stage 4 plans' slices.*socom:work:source-segment-001 \\(slice"):
        refresh_source_correlation(tracker, _changed(graph), RESERVED)


# -- source plan decide / open ----------------------------------------------------------------


def test_decide_records_one_decision_through_json(drafted) -> None:
    from tools._socom.source_plan_edit import decide

    root, tracker, graph, plan = drafted
    plan = copy.deepcopy(plan)
    changes = decide(plan, ["socom:function:0x140070"], owner="b.cpp", confidence="medium", basis="calls b_two (R_MIPS_26)")
    assert changes == [{"artifact": "socom:function:0x140070", "from": "unresolved (draft open)", "to": "authored b.cpp"}]
    owner, entry = _entries(plan)["socom:function:0x140070"]
    assert owner == "b.cpp" and entry == {"artifact": "socom:function:0x140070", "confidence": "medium", "basis": "calls b_two (R_MIPS_26)"}
    row = next(row for row in plan["owners"] if row.get("translation_unit") == "b.cpp")
    assert row["confidence"] == "medium"
    # A drafted entry moves only with --override and evidence, kept as a note.
    with pytest.raises(SocomError, match="decided by draft rule A-dwarf-cu"):
        decide(plan, ["socom:function:0x140000"], owner="b.cpp", confidence="low", basis="x")
    with pytest.raises(SocomError, match="needs --evidence"):
        decide(plan, ["socom:function:0x140000"], owner="b.cpp", confidence="low", basis="x", override=True)
    decide(plan, ["socom:function:0x140000"], unresolved="disputed", override=True, evidence="the CU range is stale")
    assert plan["notes"][-1].startswith("override socom:function:0x140000: the draft gave authored a.cpp (A-dwarf-cu)")
    assert {"artifact": "socom:function:0x140000", "reason": "disputed"} in plan["unresolved"]
    for kwargs, message in (
        ({"owner": "nope.cpp", "confidence": "low", "basis": "x"}, "names 0 owner rows"),
        ({"owner": "b.cpp", "confidence": "low", "basis": "bad\x07path"}, "control characters"),
        ({"owner": "b.cpp", "confidence": "sure", "basis": "x"}, "--confidence must be one of"),
        ({}, "give --owner"),
    ):
        with pytest.raises(SocomError, match=message):
            decide(copy.deepcopy(plan), ["socom:function:0x140040"], **kwargs)
    with pytest.raises(SocomError, match="is not listed"):
        decide(copy.deepcopy(plan), ["socom:function:0x999999"], unresolved="x")
    # The decided plan still validates once its annotations are re-derived.
    finished = _finished(plan, graph)
    report = validate_source_plan(root, tracker, finished, graph, section_of=MAIN)
    assert report["ok"], report["problems"]


def test_decide_and_open_cli(tmp_path: Path, capsys) -> None:
    (tmp_path / "support").mkdir()
    graph = build_source_graph(write_elf(tmp_path / "support" / "socom.elf"))
    (tmp_path / "build" / "source-graph").mkdir(parents=True)
    (tmp_path / "build" / "source-graph" / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    plan = {
        "kind": "socom-source-owner-plan", "schema_version": 2, "work_item_id": "socom:work:source-segment-001",
        "graph_sha256": graph["graph_sha256"], "owners": [{
            "translation_unit": "a.cpp", "classification": "authored", "workspace_path": "src/a.cpp", "original_path": None,
            "provisional_file": None, "library": None, "archive_member": None, "confidence": "high", "evidence": ["x"],
            "artifacts": [{"artifact": "socom:function:0x100000", "confidence": "high", "basis": "cu", "draft_rule": "A-dwarf-cu"}],
        }],
        "header_emits": [], "annotations": [], "notes": [],
        "unresolved": [{"artifact": "socom:function:0x100010", "reason": "between anchors", "draft": "open"},
                       {"artifact": "socom:function:0x100020", "reason": "kept", "draft": "open"}],
        "draft": {"rules_version": 3, "open_header_emits": [], "outside_reservation": []},
    }
    path = tmp_path / "build" / "source-plans" / "plan.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(plan), encoding="utf-8")
    base = ["--root", str(tmp_path), "source", "plan"]
    assert cli.main([*base, "open", "--plan", "build/source-plans/plan.json", "--limit", "1", "--format", "json"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["open_rows"] == 2 and view["shown"] == 1 and view["owner_keys"] == ["a.cpp"]
    (row,) = view["artifacts"]
    assert row["artifact"] == "socom:function:0x100010" and row["reason"] == "between anchors" and row["kind"] == "function"
    assert cli.main([*base, "open", "--plan", "build/source-plans/plan.json"]) == 0
    text = capsys.readouterr().out
    assert text.startswith("open rows 2 (shown 2)") and "  open: between anchors" in text
    decide = [*base, "decide", "--plan", "build/source-plans/plan.json", "--artifact", "socom:function:0x100010",
              "--artifact", "socom:function:0x100020", "--owner", "a.cpp", "--confidence", "medium", "--basis", "between a.cpp anchors"]
    assert cli.main(decide) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mutation_performed"] and report["open_rows"] == 0 and report["annotations"] == "re-derived"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert [entry["artifact"] for entry in saved["owners"][0]["artifacts"]] == [
        "socom:function:0x100000", "socom:function:0x100010", "socom:function:0x100020",
    ]
    assert saved["owners"][0]["confidence"] == "medium" and len(saved["annotations"]) == 3
    assert cli.main([*base, "decide", "--plan", "build/source-plans/plan.json", "--artifact", "socom:function:0x100000",
                     "--unresolved", "x"]) == 2
    assert "draft rule A-dwarf-cu" in json.loads(capsys.readouterr().out)["error"]


def test_source_cache_lists_object_section_runs(tmp_path: Path) -> None:
    (tmp_path / "support").mkdir()
    graph = build_source_graph(write_elf(tmp_path / "support" / "socom.elf"))
    path, _rebuilt = ensure_source_cache(tmp_path, graph=graph)
    rows = query(path, "SELECT printf('0x%x', gnu_object), name, printf('0x%x', start), end_basis, room_for_member FROM object_sections")["rows"]
    assert rows == [["0x100048", ".rodata", "0x100110", "next section symbol", 0]]
    columns = query(path, "SELECT data_only, data_count, segment_library FROM gnu_objects")["rows"]
    assert columns == [[0, 0, None]]
    facts = load_facts(path)
    assert any(row["symbol_type"] == "SECTION" for row in facts["references"])


def test_commands_json_has_no_byte_order_mark(root: Path) -> None:
    import os
    import subprocess
    import sys

    environment = dict(os.environ, PYTHONIOENCODING="utf-8-sig")
    output = subprocess.run(
        [sys.executable, str(root / "tools" / "socom.py"), "commands", "--json"], capture_output=True, env=environment, check=True
    ).stdout
    assert not output.startswith(b"\xef\xbb\xbf") and output.startswith(b"[")
    rows = json.loads(output)
    assert any(row["command"] == "source plan decide" and row["mutates"] for row in rows)
    assert any(row["command"] == "source plan open" and not row["mutates"] for row in rows)


def test_commands_output_writes_the_registry_without_a_bom(tmp_path: Path, capsys) -> None:
    assert cli.main(["--root", str(tmp_path), "commands", "--json", "--output", "build/commands.json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    written = (tmp_path / "build" / "commands.json").read_bytes()
    assert not written.startswith(b"\xef\xbb\xbf") and json.loads(written) == printed
    assert cli.main(["--root", str(tmp_path), "commands", "--output", "elsewhere.json"]) == 2


def test_reference_rules_3_on_the_provider_plans(root: Path, reference_source_graph: dict, reference_draft_inputs) -> None:
    tracker, facts = reference_draft_inputs
    graph = reference_source_graph
    section_of = loaded_section_lookup(root)
    counts = {}
    plans = {}
    for name in ("989snd", "msl", "newlib"):
        for rules in (2, 3):
            plan = draft_owner_plan(root, tracker, f"socom:work:source-provider-{name}", graph, facts, rules=rules, section_of=section_of)
            counts[(name, rules)] = (plan["draft"]["decided"], plan["draft"]["open"])
            plans[(name, rules)] = plan
    assert counts == {
        ("989snd", 2): (26, 84), ("989snd", 3): (84, 26),
        ("msl", 2): (133, 396), ("msl", 3): (525, 4),
        ("newlib", 2): (428, 24), ("newlib", 3): (449, 3),
    }
    # 989snd.c is one Metrowerks-compiled member: its anchors, the functions
    # between them and the data only they read.
    (member,) = [row for row in plans[("989snd", 3)]["owners"] if row["classification"] == "provider"]
    assert (member["translation_unit"], member["draft_rule"]) == ("989snd.c", "P-mw-unit")
    assert member["archive_member"] == {"gnu_object": None, "object": "989snd.o", "linked": "unknown"}
    # newlib: LOCAL section containment before "referenced only by".
    owner = {
        entry["artifact"]: (row["archive_member"] or {}).get("gnu_object")
        for row in plans[("newlib", 3)]["owners"] for entry in row["artifacts"]
    }
    assert owner["socom:data:0x43c398"] == "0x3e1f48"  # __malloc_trim_threshold: mallocr.o, not freer.o
    assert owner["socom:data:0x466f78"] == "0x3e2d58"  # __mprec_tinytens: mprec.o, not strtod.o
    assert owner["socom:data:0x447c00"] == "0x447c00"  # __infinity: the data-only s_infconst.o
    rules = plans[("newlib", 3)]["draft"]["rules"]
    assert rules["P-gnu-section"] == 20
