"""Stage 4 owner plans: unnamed objects, cross-plan units, suggestions and the decide/open edits."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools._socom import cli
from tools._socom.source_graph import build_source_graph
from tools._socom.source_plan import derive_annotations, graph_digest, validate_source_plan
from tools._socom.source_plan_edit import accept_suggestions, add_contradictions, add_header_emits
from tools._socom.tracker import load_tracker
from tools._socom.util import SocomError

from test_source_graph import write_elf  # noqa: E402 - tests/tools is on sys.path (rootdir import mode)
from test_source_plan import DIRECTORIES, MAIN, _workspace, decompose, segment_plan, synthetic_graph, undecomposed  # noqa: E402

UNNAMED = "socom:tu-cluster:0x140010"
NAMED = "socom:tu-cluster:0x140000"


@pytest.fixture(scope="module")
def stage3(root: Path) -> dict:
    return undecomposed(load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json"))


def unnamed_graph() -> dict:
    """The synthetic graph with Get__4CBoxFv in a cluster that names no unit."""

    graph = synthetic_graph()
    rows = graph["artifacts"]
    rows[0]["cluster"] = NAMED
    rows[1].update(cluster=UNNAMED, tu_candidates=[])
    graph["clusters"] = [
        {"id": NAMED, "members": [rows[0]["id"]], "units": [{"tu": "a.cpp", "signals": ["dwarf-cu"], "artifacts": 1}], "libraries": []},
        {"id": UNNAMED, "members": [rows[1]["id"]], "units": [], "libraries": []},
    ]
    graph["graph_sha256"] = graph_digest(graph)
    return graph


@pytest.fixture()
def unnamed(tmp_path: Path, stage3: dict) -> tuple[Path, dict, dict, dict]:
    graph = unnamed_graph()
    tracker = decompose(stage3, graph, DIRECTORIES)
    root = _workspace(tmp_path)
    ids = [row["id"] for row in graph["artifacts"]]
    plan = segment_plan(graph)
    plan["schema_version"] = 2
    plan["owners"][0]["artifacts"].remove(ids[1])
    plan["owners"].append(
        {
            "translation_unit": "zfoo_box.cpp",
            "classification": "authored",
            "workspace_path": "src/gamez/zFoo/zfoo_box.cpp",
            "original_path": None,
            "provisional_file": None,
            "library": None,
            "archive_member": None,
            "confidence": "low",
            "name_basis": "invented",
            "evidence": ["cluster 0x140010 names no unit; CBox is its main class"],
            "artifacts": [ids[1]],
        }
    )
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    return root, tracker, graph, plan


def _report(unnamed: tuple, plan: dict) -> dict:
    root, tracker, graph, _plan = unnamed
    plan["annotations"] = derive_annotations(plan, graph, MAIN)
    return validate_source_plan(root, tracker, plan, graph, section_of=MAIN)


# -- unnamed objects ----------------------------------------------------------------------------


def test_an_invented_owner_row_validates(unnamed) -> None:
    root, tracker, graph, plan = unnamed
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert report["ok"], report["problems"]
    assert {"artifact": "socom:function:0x140010", "relation": "defines", "section": "main",
            "path": "src/gamez/zFoo/zfoo_box.cpp"} in plan["annotations"]
    # A provisional file of the module named after the object: confidence at most medium.
    (root / "src" / "gamez" / "zFoo" / "zfoo_box.cpp").write_text("// provisional\n", encoding="utf-8")
    row = plan["owners"][2]
    row.update(name_basis="provisional", provisional_file="src/gamez/zFoo/zfoo_box.cpp", confidence="medium")
    assert _report(unnamed, plan)["ok"], _report(unnamed, plan)["problems"]


def _invented(plan: dict) -> dict:
    return plan["owners"][2]


NAME_DEFECTS = [
    (lambda plan, ids: _invented(plan).update(confidence="medium"), "invented name: its confidence must be low"),
    (lambda plan, ids: _invented(plan).update(translation_unit="b.cpp", workspace_path="src/gamez/zFoo/b.cpp"),
     "reuses unit b.cpp, which the graph knows"),
    (lambda plan, ids: plan["owners"][0]["artifacts"].remove(ids[0]) or _invented(plan)["artifacts"].append(ids[0]),
     f"lies in cluster {NAMED}, which names a.cpp"),
    (lambda plan, ids: plan["owners"][0]["artifacts"].remove(ids[0]) or _invented(plan)["artifacts"].append(ids[0]),
     "has the strong unit candidate a.cpp"),
    (lambda plan, ids: plan["owners"][0]["artifacts"].extend([ids[1]]) or plan["owners"][0]["artifacts"].remove(ids[7])
     or _invented(plan).update(artifacts=[ids[7]]), "none of its artifacts lies in a cluster with no unit name"),
    (lambda plan, ids: _invented(plan).update(name_basis="guessed"), "name_basis must be one of"),
    (lambda plan, ids: _invented(plan).update(name_basis="provisional", confidence="high"), "provisional_file must be that file"),
    (lambda plan, ids: _invented(plan).update(name_basis="provisional", confidence="high"), "its confidence is at most medium"),
    (lambda plan, ids: plan["owners"][1].update(name_basis="invented"), "only an authored row names an object"),
    (lambda plan, ids: _invented(plan).pop("name_basis"), "zfoo_box.cpp, which the graph does not know"),
    # The path stays inside the reservation as for any owner row.
    (lambda plan, ids: _invented(plan).update(workspace_path="src/gamez/zBar/zfoo_box.cpp"), "lies outside the reservation"),
]


@pytest.mark.parametrize(("change", "message"), NAME_DEFECTS)
def test_unnamed_object_defects_are_refused(unnamed, change, message: str) -> None:
    _root, _tracker, graph, plan = unnamed
    plan = copy.deepcopy(plan)
    change(plan, [row["id"] for row in graph["artifacts"]])
    report = _report(unnamed, plan)
    assert any(message in problem for problem in report["problems"]), report["problems"]


def test_schema_1_plans_cannot_record_a_name_basis(unnamed) -> None:
    _root, _tracker, _graph, plan = unnamed
    plan = copy.deepcopy(plan)
    plan["schema_version"] = 1
    report = _report(unnamed, plan)
    assert any("unknown fields ['name_basis']" in problem for problem in report["problems"]), report["problems"]
    # A schema 1 row naming a unit the graph does not know is a review note, not a refusal.
    _invented(plan).pop("name_basis")
    report = _report(unnamed, plan)
    assert report["ok"], report["problems"]
    assert any("zfoo_box.cpp, which the graph does not know" in note for note in report["review"])


# -- cross-plan units ---------------------------------------------------------------------------


def _other_plan(root: Path, workspace: str, original: str | None = "Z:\\dev\\gamez\\zFoo\\a.cpp") -> Path:
    path = root / "build" / "source-plans" / "socom-work-source-segment-003.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"translation_unit": "a.cpp", "classification": "authored", "workspace_path": workspace,
           "original_path": original, "artifacts": []}
    path.write_text(json.dumps({"work_item_id": "socom:work:source-segment-003", "owners": [row]}), encoding="utf-8")
    return path


def test_a_unit_must_agree_with_handed_off_and_accepted_plans(tmp_path: Path, stage3: dict) -> None:
    graph = synthetic_graph()
    tracker = decompose(stage3, graph, DIRECTORIES)
    root = _workspace(tmp_path)
    plan = segment_plan(graph)
    other = next(row for row in tracker["work_items"] if row["id"] == "socom:work:source-segment-003")
    path = _other_plan(root, "src/gamez/zFoo/a.cpp")

    def validate() -> dict:
        return validate_source_plan(root, tracker, plan, graph, section_of=MAIN)

    other["status"] = "accepted"
    report = validate()
    assert report["ok"], report["problems"]
    assert report["shared_units"] == [
        {"unit": "a.cpp", "item": "socom:work:source-segment-003", "status": "accepted", "agrees": True}
    ]
    # An original path only one row cites names no other file: a review note.
    _other_plan(root, "src/gamez/zFoo/a.cpp", None)
    report = validate()
    assert report["ok"] and report["shared_units"][0]["agrees"] is False
    assert any("differ in citing the unit's original_path" in note for note in report["review"]), report["review"]
    _other_plan(root, "src/gamez/zFoo/a.cpp", "Z:\\dev\\gamez\\zBar\\a.cpp")
    assert any("original_path 'Z:\\\\dev\\\\gamez\\\\zFoo\\\\a.cpp' there 'Z:\\\\dev\\\\gamez\\\\zBar\\\\a.cpp'" in problem
               for problem in validate()["problems"])
    _other_plan(root, "src/gamez/zBar/a.cpp")
    report = validate()
    assert any(
        "disagrees with socom:work:source-segment-003 (accepted) on a.cpp: workspace_path 'src/gamez/zFoo/a.cpp' there "
        "'src/gamez/zBar/a.cpp'" in problem
        for problem in report["problems"]
    ), report["problems"]
    # A plan still awaiting acceptance: a review note (whichever is accepted first decides).
    other["status"] = "awaiting_acceptance"
    report = validate()
    assert report["ok"] and any("disagrees with socom:work:source-segment-003 (awaiting_acceptance)" in note for note in report["review"])
    other["status"] = "ready"
    assert validate()["shared_units"] == []
    other["status"] = "accepted"
    path.unlink()
    report = validate()
    assert report["ok"] and any("socom-work-source-segment-003.json is missing" in note for note in report["review"])


# -- suggestions --------------------------------------------------------------------------------


def test_a_kept_suggestion_must_be_well_formed(unnamed) -> None:
    _root, _tracker, graph, plan = unnamed
    ids = [row["id"] for row in graph["artifacts"]]
    plan = copy.deepcopy(plan)
    plan["owners"][0]["artifacts"].remove(ids[7])
    suggest = {"owner": "a.cpp", "rule": "S-literal", "confidence": "medium", "basis": "read only by a_first"}
    plan["unresolved"].append({"artifact": ids[7], "reason": "two readers in the next segment", "suggest": suggest})
    assert _report(unnamed, plan)["ok"], _report(unnamed, plan)["problems"]
    plan["unresolved"][0]["suggest"] = {"owner": "a.cpp", "confidence": "sure", "extra": 1}
    problems = _report(unnamed, plan)["problems"]
    for message in ("suggest has unknown fields ['extra']", "suggest needs rule", "suggest needs basis", "suggest confidence must be one of"):
        assert any(message in problem for problem in problems), (message, problems)


def test_accept_suggestions_records_hand_entries(unnamed) -> None:
    _root, _tracker, graph, plan = unnamed
    ids = [row["id"] for row in graph["artifacts"]]
    plan = copy.deepcopy(plan)
    plan["owners"][0]["artifacts"].remove(ids[7])
    plan["unresolved"].append({"artifact": ids[7], "reason": "open", "draft": "open",
                               "suggest": {"owner": "a.cpp", "rule": "S-literal", "confidence": "medium", "basis": "read by a_first"}})
    changes = accept_suggestions(plan, [ids[7]])
    assert changes == [{"artifact": ids[7], "from": "unresolved (draft open)", "to": "authored a.cpp", "suggestion": "S-literal"}]
    assert plan["owners"][0]["artifacts"][-1] == {"artifact": ids[7], "confidence": "medium", "basis": "read by a_first"}
    assert plan["owners"][0]["confidence"] == "medium" and plan["unresolved"] == []
    with pytest.raises(SocomError, match="has no suggestion"):
        accept_suggestions(plan, [ids[0]])
    plan["owners"][0]["artifacts"].pop()
    plan["unresolved"].append({"artifact": ids[7], "reason": "open", "draft": "open",
                               "suggest": {"owner": "c.cpp", "rule": "S-x", "confidence": "low", "basis": "x"}})
    with pytest.raises(SocomError, match="names 0 owner rows"):
        accept_suggestions(plan, [ids[7]])
    plan["unresolved"][-1]["suggest"] = {"owner": "a.cpp", "rule": "S-x", "confidence": "sure", "basis": "x"}
    with pytest.raises(SocomError, match="confidence must be one of"):
        accept_suggestions(plan, [ids[7]])


# -- contradictions and header emits ------------------------------------------------------------


def test_contradiction_and_header_emit_rows(unnamed) -> None:
    root, tracker, graph, plan = unnamed
    ids = [row["id"] for row in graph["artifacts"]]
    plan = copy.deepcopy(plan)
    plan["header_emits"] = []
    changes = add_contradictions(plan, [ids[0]], kind="defined-elsewhere", provisional_file="src/gamez/zFoo/a.cpp", line=1,
                                 elf_evidence=["dwarf-cu a.cpp covers 0x140000"], root=root)
    assert changes == [{"artifact": ids[0], "contradiction": "defined-elsewhere", "provisional_file": "src/gamez/zFoo/a.cpp", "line": 1}]
    assert plan["contradictions"] == [{"artifact": ids[0], "provisional_file": "src/gamez/zFoo/a.cpp", "line": 1,
                                       "kind": "defined-elsewhere", "elf_evidence": ["dwarf-cu a.cpp covers 0x140000"]}]
    for kwargs, message in (
        ({"line": 1}, "already has this defined-elsewhere contradiction"),
        ({"line": 2}, "has 1 lines, not 2"),
        ({"line": 0}, "positive line number"),
        ({"provisional_file": "src/gamez/zFoo/A.cpp"}, "must name an existing file exactly"),
        ({"kind": "Elsewhere"}, "lowercase kind slug"),
        ({"elf_evidence": [" "]}, "needs at least one evidence line"),
    ):
        arguments = {"kind": "defined-elsewhere", "provisional_file": "src/gamez/zFoo/a.cpp", "line": None,
                     "elf_evidence": ["x"], "root": root, **kwargs}
        with pytest.raises(SocomError, match=message):
            add_contradictions(plan, [ids[0]], **arguments)
    add_header_emits(plan, [ids[1]], header="src/gamez/zFoo/zfoo.h", reason="inline", evidence=["binding 13 instance"])
    assert plan["header_emits"] == [{"artifact": ids[1], "header": "src/gamez/zFoo/zfoo.h", "reason": "inline",
                                     "evidence": ["binding 13 instance"]}]
    with pytest.raises(SocomError, match="already has a header-emit row"):
        add_header_emits(plan, [ids[1]], header="<vector>", library="MSL", reason="template", evidence=["x"])
    with pytest.raises(SocomError, match="needs --evidence"):
        add_header_emits(plan, [ids[1]], header="<vector>", library="MSL", reason="inline", evidence=["x"], override=True)
    change = add_header_emits(plan, [ids[1]], header="<CBox>", library="CBox lib", reason="inline", evidence=["x"],
                              override=True, override_evidence="the class lives in a provider header")
    assert change[0]["replaced"] == "src/gamez/zFoo/zfoo.h" and plan["header_emits"][0]["library"] == "CBox lib"
    assert plan["notes"][-1].startswith(f"override header emit {ids[1]}: the plan gave src/gamez/zFoo/zfoo.h;")
    for kwargs, message in (
        ({"artifacts": [ids[2]]}, "not owned by an authored row"),
        ({"header": "src/gamez/zFoo/a.cpp"}, "repo-relative header path"),
        ({"header": "src/x.h", "library": "MSL"}, "spelled <name>"),
        ({"reason": "static"}, "--reason must be one of"),
        ({"evidence": []}, "needs at least one evidence line"),
    ):
        arguments = {"artifacts": [ids[0]], "header": "src/gamez/zFoo/zfoo.h", "reason": "inline", "evidence": ["x"], **kwargs}
        with pytest.raises(SocomError, match=message):
            add_header_emits(plan, arguments.pop("artifacts"), **arguments)
    schema_1 = copy.deepcopy(plan)
    schema_1["schema_version"] = 1
    with pytest.raises(SocomError, match="schema 2 plans only"):
        add_header_emits(schema_1, [ids[0]], header="src/gamez/zFoo/zfoo.h", reason="inline", evidence=["x"])
    # The edited plan validates (the provider-header emit makes its edge an emits edge in the owner's file).
    plan["header_emits"][0].update(header="src/gamez/zFoo/zfoo.h", reason="inline")
    plan["header_emits"][0].pop("library")
    report = _report(unnamed, plan)
    assert report["ok"], report["problems"]
    assert report["summary"]["contradictions"] == 1


# -- the CLI ------------------------------------------------------------------------------------


WEAK_COPIES = ("a_middle", "a_third", "a_assist")


def _cli_workspace(tmp_path: Path) -> tuple[list[str], Path]:
    """A workspace on the synthetic ELF whose a_middle, a_third and a_assist are WEAK copies."""

    (tmp_path / "support").mkdir()
    graph = build_source_graph(write_elf(tmp_path / "support" / "socom.elf"))
    for row in graph["artifacts"]:
        if row.get("names") and row["names"][0]["name"] in WEAK_COPIES:
            row["binding"] = "WEAK"
            for name in row["names"]:
                name["binding"] = "WEAK"
    graph["graph_sha256"] = graph_digest(graph)
    (tmp_path / "build" / "source-graph").mkdir(parents=True)
    (tmp_path / "build" / "source-graph" / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.cpp").write_text("// a\n// b\n", encoding="utf-8")

    def row(unit: str, *artifacts: str) -> dict:
        return {"translation_unit": unit, "classification": "authored", "workspace_path": f"src/{unit}", "original_path": None,
                "provisional_file": None, "library": None, "archive_member": None, "confidence": "high", "evidence": ["x"],
                "artifacts": [{"artifact": value, "confidence": "high", "basis": "x", "draft_rule": "A-dwarf-cu"} for value in artifacts]}

    plan = {
        "kind": "socom-source-owner-plan", "schema_version": 2, "work_item_id": "socom:work:source-segment-001",
        "graph_sha256": graph["graph_sha256"],
        "owners": [row("a.cpp", "socom:function:0x100000", "socom:function:0x100020"), row("b.cpp", "socom:function:0x100040")],
        "header_emits": [], "annotations": [], "notes": [],
        "unresolved": [
            {"artifact": "socom:function:0x100010", "reason": "between anchors", "draft": "open"},
            {"artifact": "socom:function:0x100038", "reason": "static copy", "draft": "open",
             "suggest": {"owner": "a.cpp", "rule": "S-sole-caller", "confidence": "medium", "basis": "only a_third calls it"}},
        ],
        "draft": {"rules_version": 3, "open_header_emits": ["socom:function:0x100020"], "outside_reservation": []},
    }
    path = tmp_path / "build" / "source-plans" / "plan.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(plan), encoding="utf-8")
    return ["--root", str(tmp_path), "source", "plan"], path


def test_open_shows_flanks_referencing_units_and_suggestions(tmp_path: Path, capsys) -> None:
    base, _path = _cli_workspace(tmp_path)
    assert cli.main([*base, "open", "--plan", "build/source-plans/plan.json", "--format", "json"]) == 0
    view = json.loads(capsys.readouterr().out)
    middle, assist = view["artifacts"]
    assert middle["binding"] == "WEAK" and middle["instance"] == "weak"
    assert middle["flank_before"] == {"anchor": "a.cpp 0x100000 a_first", "unit": "a.cpp", "copies": [], "copy_count": 0,
                                      "unanchored": 0}
    assert middle["flank_after"]["copies"] == ["WEAK 0x100020 a_third [a.cpp]", "WEAK 0x100038 a_assist [open]"]
    assert middle["flank_after"]["unit"] == "b.cpp" and "referencing_units" not in middle
    assert assist["flank_before"]["copies"] == ["WEAK 0x100010 a_middle [open]", "WEAK 0x100020 a_third [a.cpp]"]
    assert assist["referencing_units"] == ["a.cpp 1"] and assist["sole_referencing_unit"] == "a.cpp"
    assert assist["suggest"]["rule"] == "S-sole-caller"
    assert view["open_header_emits"] == ["socom:function:0x100020"]
    assert cli.main([*base, "open", "--plan", "build/source-plans/plan.json"]) == 0
    text = capsys.readouterr().out
    assert "  before: a.cpp 0x100000 a_first < WEAK 0x100010 a_middle [open] < WEAK 0x100020 a_third [a.cpp] < this" in text
    assert "  sole_referencing_unit: a.cpp" in text
    assert "  suggest: a.cpp medium (S-sole-caller): only a_third calls it" in text
    # --output writes the view under build/ and prints a summary.
    assert cli.main([*base, "open", "--plan", "build/source-plans/plan.json", "--output", "build/source-plans/open.txt"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["open_rows"] == 2 and summary["mutation_performed"] is False
    assert (tmp_path / "build" / "source-plans" / "open.txt").read_text(encoding="utf-8").startswith("open rows 2 (shown 2)")
    assert cli.main([*base, "open", "--plan", "build/source-plans/plan.json", "--output", "src/open.txt"]) == 2
    assert "only be written under build/" in json.loads(capsys.readouterr().out)["error"]


def test_decide_cli_accepts_suggestions_and_adds_rows(tmp_path: Path, capsys) -> None:
    base, path = _cli_workspace(tmp_path)
    decide = [*base, "decide", "--plan", "build/source-plans/plan.json"]
    assert cli.main([*decide, "--artifact", "socom:function:0x100038", "--accept-suggestion"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["changes"][0]["suggestion"] == "S-sole-caller" and report["open_rows"] == 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["owners"][0]["artifacts"][-1] == {"artifact": "socom:function:0x100038", "confidence": "medium",
                                                   "basis": "only a_third calls it"}
    assert cli.main([*decide, "--artifact", "socom:function:0x100010", "--accept-suggestion"]) == 2
    assert "has no suggestion" in json.loads(capsys.readouterr().out)["error"]
    assert cli.main([*decide, "--artifact", "socom:function:0x100000", "--contradiction", "signature",
                     "--provisional-file", "src/a.cpp", "--line", "2", "--elf-evidence", "a_first reads $a0"]) == 0
    assert json.loads(capsys.readouterr().out)["changes"][0]["contradiction"] == "signature"
    assert cli.main([*decide, "--artifact", "socom:function:0x100020", "--header-emit", "src/a.h", "--reason", "weak",
                     "--emit-evidence", "WEAK copy of an inline body"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["annotations"] == "re-derived"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["contradictions"] == [{"artifact": "socom:function:0x100000", "provisional_file": "src/a.cpp", "line": 2,
                                        "kind": "signature", "elf_evidence": ["a_first reads $a0"]}]
    assert saved["header_emits"] == [{"artifact": "socom:function:0x100020", "header": "src/a.h", "reason": "weak",
                                      "evidence": ["WEAK copy of an inline body"]}]
    assert {"artifact": "socom:function:0x100020", "relation": "emits", "section": "main", "path": "src/a.h"} in saved["annotations"]
    # The open view no longer lists the header emit the plan now records.
    assert cli.main([*base, "open", "--plan", "build/source-plans/plan.json", "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["open_header_emits"] == []
    for extra, message in (
        (["--owner", "a.cpp", "--unresolved", "x"], "give exactly one of"),
        (["--accept-suggestion", "--confidence", "high"], "do not apply to --accept-suggestion"),
        (["--contradiction", "signature", "--reason", "weak"], "do not apply to --contradiction"),
        (["--contradiction", "signature", "--elf-evidence", "x"], "needs --provisional-file"),
        (["--header-emit", "src/a.h", "--emit-evidence", "x"], "needs --reason"),
        (["--unresolved", "x", "--provisional-file", "src/a.cpp"], "do not apply to --unresolved"),
    ):
        assert cli.main([*decide, "--artifact", "socom:function:0x100010", *extra]) == 2
        assert message in json.loads(capsys.readouterr().out)["error"]
