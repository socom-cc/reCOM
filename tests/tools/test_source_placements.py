"""User placement decisions: the decision-file parser, ``name_basis: "user"`` rows and entry decisions, ``source placements check``."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tools._socom import cli
from tools._socom.source_graph import build_source_graph
from tools._socom.source_placements import ArtifactIndex, heading_destination, normalized_sha256, parse_decisions, revision_path
from tools._socom.source_plan import validate_source_plan
from tools._socom.tracker import load_tracker

from test_source_graph import write_elf  # noqa: E402 - tests/tools is on sys.path (rootdir import mode)
from test_source_plan import MAIN, undecomposed  # noqa: E402
from test_source_plan_edit import NAMED, _report, _unnamed, unnamed_graph  # noqa: E402

DECISIONS = "build/decisions/placements.md"
DECISION_TEXT = (
    "# Placements\n"
    "\n"
    "## zfoo/zfoo_box.cpp\n"
    "Note: the CBox accessors are their own file (the user's reading of the neighbours).\n"
    "- CBox::Get()\n"
    "\n"
    "## zfoo/zfoo_empty.cpp\n"
    "- a_first\n"
    "\n"
    "## zfoo/zfoo.h\n"
    "Note: inline in CBox.\n"
    "- 0x140010  CBox::Get()\n"
    "\n"
    "## zfoo/a.cpp\n"
    "- a_first\n"
)


@pytest.fixture(scope="module")
def stage3(root: Path) -> dict:
    return undecomposed(load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json"))


def _decision(heading: str, text: str = DECISION_TEXT) -> dict:
    return {"file": DECISIONS, "sha256": normalized_sha256(text.encode("utf-8")), "heading": heading}


@pytest.fixture()
def user(tmp_path: Path, stage3: dict) -> tuple[Path, dict, dict, dict]:
    """The unnamed-object plan with its zfoo_box.cpp row named by the user's decision."""

    setup = _unnamed(tmp_path, stage3, unnamed_graph())
    root, _tracker, _graph, plan = setup
    path = root / DECISIONS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DECISION_TEXT, encoding="utf-8", newline="\n")
    plan["owners"][2].update(name_basis="user", confidence="medium", decision=_decision("zfoo/zfoo_box.cpp"),
                             evidence=["the user placed CBox::Get in zfoo_box.cpp"])
    return setup


def _row(plan: dict) -> dict:
    return plan["owners"][2]


def _problems(setup: tuple, plan: dict) -> list[str]:
    return _report(setup, plan)["problems"]


# -- name_basis user ----------------------------------------------------------------------------


def test_a_user_named_row_validates(user) -> None:
    root, _tracker, _graph, plan = user
    report = _report(user, copy.deepcopy(plan))
    assert report["ok"], report["problems"]
    # Its artifact lies in a cluster that names no unit: no review note about a cluster-less object.
    assert not any("none of its artifacts lies in a cluster" in note for note in report["review"]), report["review"]
    # The digest is of the LF-normalized bytes: a CRLF checkout of the same file still matches.
    (root / DECISIONS).write_bytes(DECISION_TEXT.replace("\n", "\r\n").encode("utf-8"))
    assert _report(user, copy.deepcopy(plan))["ok"]


USER_DEFECTS = [
    (lambda plan: _row(plan)["decision"].update(sha256="0" * 64), "has LF-normalized SHA-256"),
    (lambda plan: _row(plan)["decision"].update(heading="zfoo/zfoo_other.cpp"), "is not a ## heading of build/decisions/placements.md"),
    (lambda plan: _row(plan).update(confidence="high"), "is named by a user decision: its confidence is at most medium"),
    (lambda plan: _row(plan).pop("decision"), "it needs decision {file, sha256, heading}"),
    (lambda plan: _row(plan).update(decision={"file": DECISIONS, "heading": "zfoo/zfoo_box.cpp"}), "decision must be an object"),
    (lambda plan: _row(plan)["decision"].update(file="../placements.md"), "must be a repo-relative path"),
    (lambda plan: _row(plan)["decision"].update(file="build/decisions/missing.md"), "missing.md does not exist"),
    (lambda plan: _row(plan).update(name_basis="invented", confidence="low"), "records a decision with name_basis invented"),
    # The heading must name this row's unit file, never a header or another file.
    (lambda plan: _row(plan).update(decision=_decision("zfoo/a.cpp")), "places its artifacts in src/gamez/zFoo/a.cpp, not unit zfoo_box.cpp"),
    (lambda plan: _row(plan).update(decision=_decision("zfoo/zfoo.h")), "names src/gamez/zFoo/zfoo.h, not a source file"),
    # Every artifact of the row is listed under the heading.
    (lambda plan: _row(plan).update(translation_unit="zfoo_empty.cpp", workspace_path="src/gamez/zFoo/zfoo_empty.cpp",
                                    decision=_decision("zfoo/zfoo_empty.cpp")),
     "socom:function:0x140010 is not listed under heading 'zfoo/zfoo_empty.cpp'"),
    # The ELF outranks a decision: a cluster naming another unit, as for provisional and invented names.
    (lambda plan: plan["owners"][0]["artifacts"].remove("socom:function:0x140000") or _row(plan)["artifacts"].append("socom:function:0x140000"),
     f"lies in cluster {NAMED}, which names a.cpp"),
    (lambda plan: plan["owners"][0]["artifacts"].remove("socom:function:0x140000") or _row(plan)["artifacts"].append("socom:function:0x140000"),
     "has the strong unit candidate a.cpp"),
    (lambda plan: _row(plan).update(translation_unit="b.cpp", workspace_path="src/gamez/zFoo/b.cpp"), "reuses unit b.cpp, which the graph knows"),
]


@pytest.mark.parametrize(("change", "message"), USER_DEFECTS)
def test_user_named_row_defects_are_refused(user, change, message: str) -> None:
    plan = copy.deepcopy(user[3])
    change(plan)
    problems = _problems(user, plan)
    assert any(message in problem for problem in problems), problems


# -- entry decisions ------------------------------------------------------------------------------


def _cite(plan: dict, owner: int, identity: str, heading: str, **fields) -> dict:
    row = plan["owners"][owner]
    entry = {"artifact": identity, "confidence": "medium", "basis": "the user placed it", "decision": _decision(heading), **fields}
    row["artifacts"] = [entry if value == identity else value for value in row["artifacts"]]
    return entry


def test_entry_decisions_validate(user) -> None:
    plan = copy.deepcopy(user[3])
    # A unit the graph knows: the entry cites the user's placement into that file.
    _cite(plan, 0, "socom:function:0x140000", "zfoo/a.cpp")
    plan["owners"][0]["confidence"] = "medium"
    # An inline copy: the header heading matches the header-emit row's header.
    _cite(plan, 2, "socom:function:0x140010", "zfoo/zfoo.h")
    report = _report(user, plan)
    assert report["ok"], report["problems"]


ENTRY_DEFECTS = [
    (lambda plan: _cite(plan, 0, "socom:function:0x140000", "zfoo/zfoo_box.cpp"),
     "decision heading 'zfoo/zfoo_box.cpp' places its artifacts in src/gamez/zFoo/zfoo_box.cpp, not unit a.cpp"),
    (lambda plan: _cite(plan, 0, "socom:function:0x140000", "zfoo/zfoo_box.cpp"), "socom:function:0x140000 is not listed under heading"),
    (lambda plan: _cite(plan, 0, "socom:function:0x140000", "zfoo/a.cpp", confidence="high"), "rests on a user decision: its confidence is at most medium"),
    (lambda plan: _cite(plan, 0, "socom:function:0x140000", "zfoo/a.cpp").pop("basis"), "cites a decision: it needs its confidence and basis"),
    (lambda plan: _cite(plan, 0, "socom:function:0x140000", "zfoo/a.cpp")["decision"].update(sha256="f" * 64), "has LF-normalized SHA-256"),
    (lambda plan: _cite(plan, 2, "socom:function:0x140010", "zfoo/zfoo.h") and plan.update(header_emits=[]),
     "a header-emit row must emit it into src/gamez/zFoo/zfoo.h"),
    (lambda plan: _cite(plan, 1, "socom:gap:0x140018", "zfoo/a.cpp"), "only an authored row's entries cite one"),
]


@pytest.mark.parametrize(("change", "message"), ENTRY_DEFECTS)
def test_entry_decision_defects_are_refused(user, change, message: str) -> None:
    plan = copy.deepcopy(user[3])
    plan["owners"][0]["confidence"] = "medium"
    change(plan)
    problems = _problems(user, plan)
    assert any(message in problem for problem in problems), problems


def test_schema_1_rows_cannot_cite_a_decision(user) -> None:
    root, tracker, graph, plan = user
    plan = copy.deepcopy(plan)
    plan["schema_version"] = 1
    _row(plan).pop("name_basis")
    report = validate_source_plan(root, tracker, plan, graph, section_of=MAIN)
    assert any("unknown fields ['decision']" in problem for problem in report["problems"]), report["problems"]


# -- parsing and resolution ---------------------------------------------------------------------


def test_decision_files_parse_headings_lines_and_notes() -> None:
    parsed = parse_decisions(
        "- stray line\n"
        "## zfoo/a.cpp\n"
        "Note: why\n"
        "- 0x140000  a_first\n"
        "* `CBox::Get()`\n"
        "- 0x140010\n"
        "# Title ends the heading\n"
        "- outside again\n"
        "## zfoo/a.cpp\n"
        "- b_main\n"
    )
    (block,) = parsed["headings"]
    assert block["heading"] == "zfoo/a.cpp" and block["notes"] == ["Note: why"]
    assert [(row["line"], row["address"], row["signature"]) for row in block["entries"]] == [
        (4, 0x140000, "a_first"), (5, None, "CBox::Get()"), (6, 0x140010, ""), (10, None, "b_main"),
    ]
    assert parsed["outside"] == [1, 8]
    assert parsed["repeated"] == [{"heading": "zfoo/a.cpp", "line": 9, "first_line": 2}]


def test_headings_map_onto_src_in_on_disk_case(tmp_path: Path) -> None:
    for directory in ("src/gamez/zEntity", "src/gamez/zMath", "src/rt", "src/Apps/FTS/game"):
        (tmp_path / directory).mkdir(parents=True)
    (tmp_path / "src/gamez/zEntity/ent_main.cpp").write_text("", encoding="utf-8")
    expect = {
        "zentity/ent_entity.cpp": ("src/gamez/zEntity/ent_entity.cpp", False, True, False),
        "ZENTITY/Ent_Main.cpp": ("src/gamez/zEntity/ent_main.cpp", True, True, False),
        "zmath/zmath.h": ("src/gamez/zMath/zmath.h", False, True, True),
        "rt/rtlist.h": ("src/rt/rtlist.h", False, True, True),
        "apps/fts/game/beachball.cpp": ("src/Apps/FTS/game/beachball.cpp", False, True, False),
        "src/gamez/zentity/ent_control.cpp": ("src/gamez/zEntity/ent_control.cpp", False, True, False),
        "`znew/znew_main.cpp`": ("src/gamez/znew/znew_main.cpp", False, False, False),
    }
    for heading, (path, exists, known, header) in expect.items():
        row = heading_destination(tmp_path, heading)
        assert (row["path"], row["exists"], row["known_module"], row["header"]) == (path, exists, known, header), heading
    for heading in ("Inline in their class headers", "zentity/README.md", "zentity/../x.cpp"):
        row = heading_destination(tmp_path, heading)
        assert row["path"] is None and row["error"], heading


def test_lines_resolve_by_address_or_declaration() -> None:
    index = ArtifactIndex([
        ("socom:function:0x10", 0x10, "function", ["Get__4CBoxFv"]),
        ("socom:function:0x20", 0x20, "function", ["Get__4CBoxFv"]),
        ("socom:function:0x30", 0x30, "function", ["Run__4CDirFv", "Run_alias"]),
        ("socom:data:0x30", 0x30, "data", ["@12"]),
    ])
    resolve = lambda text, address=None: index.resolve({"signature": text, "address": address})  # noqa: E731
    assert resolve("CBox::Get()")["status"] == "ambiguous"
    assert resolve("CBox :: Get ( )", 0x20) == {"status": "resolved", "artifacts": ["socom:function:0x20"]}
    assert resolve("CDir::Run()")["artifacts"] == ["socom:function:0x30"]
    assert resolve("Run_alias")["artifacts"] == ["socom:function:0x30"]  # an ELF name matches as written
    assert resolve("", 0x30)["artifacts"] == ["socom:function:0x30"]  # an address alone prefers the function
    assert resolve("CDir::Stop()")["status"] == "unmatched"
    assert resolve("", 0x40)["status"] == "unmatched"
    assert resolve("CBox::Get()", 0x30)["status"] == "mismatch"


# -- source placements check --------------------------------------------------------------------


CHECK_TEXT = (
    "# Placements\n"
    "- a_first\n"
    "\n"
    "## zdir/dir_new.cpp\n"
    "Note: the user's reason.\n"
    "- a_first\n"
    "- 0x100020  a_third\n"
    "\n"
    "## ZDIR/zdir.h\n"
    "- CDir::Run()\n"
    "\n"
    "## rt/rtlist.h\n"
    "- 0x100058\n"
    "\n"
    "## apps/fts/game/fts_thing.cpp\n"
    "- sceFooInit\n"
    "\n"
    "## zdir/dir_main.cpp\n"
    "- 0x100038\n"
    "- nonexistent_function()\n"
    "- a_first\n"
    "- 0x100040  a_middle\n"
    "- 0x100099\n"
    "\n"
    "## zdir/b.cpp\n"
    "- Helper__13@unnamed@b_cpp@Fv\n"
    "\n"
    "## zunknown/x.cpp\n"
    "- __sinit_a.cpp\n"
    "\n"
    "## not a path\n"
    "- a_middle\n"
)


def _check_workspace(root: Path) -> None:
    (root / "support").mkdir()
    graph = build_source_graph(write_elf(root / "support" / "socom.elf"))
    for relative, text in {
        "build/source-graph/graph.json": json.dumps(graph),
        "src/gamez/zDir/dir_main.cpp": "/* @socom-artifact defines main socom:function:0x100010 */\nvoid a_middle() {}\n",
        "src/rt/rtarray.h": "",
        "src/Apps/FTS/game/fts_game.cpp": "",
        "build/decisions/check.md": CHECK_TEXT,
        "build/source-plans/socom-work-source-segment-001.json": json.dumps({
            "owners": [{"translation_unit": "a.cpp", "artifacts": ["socom:function:0x100010", {"artifact": "socom:function:0x100038"}]}],
            "unresolved": [{"artifact": "socom:function:0x100000", "reason": "x"}, {"artifact": "socom:function:0x100020", "reason": "x"}],
        }),
    }.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def test_placements_check_reports_lines_destinations_items_and_contiguity(tmp_path: Path, capsys) -> None:
    _check_workspace(tmp_path)
    code = cli.main(["--root", str(tmp_path), "source", "placements", "check", "--file", "build/decisions/check.md", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 1 and report["ok"] is False and report["mutation_performed"] is False
    assert report["file"] == "build/decisions/check.md" and report["sha256"] == normalized_sha256(CHECK_TEXT.encode())
    destinations = {row["heading"]: row for row in report["destinations"]}
    new = destinations["zdir/dir_new.cpp"]
    assert (new["path"], new["new"], new["known_module"], new["known_unit"]) == ("src/gamez/zDir/dir_new.cpp", True, True, False)
    assert [(row["address"], row["plan"]) for row in new["artifacts"]] == [("0x100000", "unresolved"), ("0x100020", "unresolved")]
    assert new["items"] == [{"item": "socom:work:source-segment-001", "artifacts": 2}]
    assert new["notes"] == ["Note: the user's reason."]
    # a_middle, owned by dir_main.cpp, lies between the new file's two functions; and the reverse.
    assert [(row["address"], row["owner"]) for row in new["conflicts"]] == [("0x100010", "src/gamez/zDir/dir_main.cpp")]
    main = destinations["zdir/dir_main.cpp"]
    assert main["exists"] and main["run"] == ["0x100010", "0x100038"]
    assert [(row["address"], row["owner"]) for row in main["conflicts"]] == [("0x100020", "src/gamez/zDir/dir_new.cpp")]
    assert [(row["address"], row["plan"]) for row in main["artifacts"]] == [("0x100038", "owned by a.cpp")]
    # A file the graph does not know (a user-named unit) whose artifacts a cluster or a strong candidate place
    # in another unit; a known unit (b.cpp) and a header are not checked.
    assert [row["why"] for row in new["elf_objections"]] == ["cluster socom:tu-cluster:0x100000 names a.cpp; strong unit candidate a.cpp"] * 2
    assert len(main["elf_objections"]) == 1 and destinations["zdir/b.cpp"]["known_unit"] is True
    assert destinations["zdir/b.cpp"]["elf_objections"] == [] and destinations["zdir/b.cpp"]["artifacts"][0]["plan"] == "not listed by its plan"
    header = destinations["ZDIR/zdir.h"]
    assert (header["path"], header["header"], header["conflicts"], header["elf_objections"]) == ("src/gamez/zDir/zdir.h", True, [], [])
    assert header["artifacts"][0]["plan"] == "plan file missing or unreadable"
    assert destinations["rt/rtlist.h"]["path"] == "src/rt/rtlist.h"
    thing = destinations["apps/fts/game/fts_thing.cpp"]
    assert thing["path"] == "src/Apps/FTS/game/fts_thing.cpp" and thing["items"] == [{"item": "socom:work:source-provider-sce", "artifacts": 1}]
    assert thing["conflicts"] == [] and "libfoo" in thing["elf_objections"][0]["why"]
    unknown = destinations["zunknown/x.cpp"]
    assert unknown["known_module"] is False and unknown["path"] == "src/gamez/zunknown/x.cpp" and unknown["placed"] == 1
    assert unknown["items"] == [{"item": "socom:work:source-segment-004", "artifacts": 1}]
    assert report["invalid_headings"] == [{"heading": "not a path", "line": 31, "error": "names no <module>/<file> path"}]
    assert [(row["line"], row["why"]) for row in report["unmatched"]] == [
        (20, "no ELF artifact has this name or declaration"), (23, "no artifact starts at 0x100099"),
    ]
    assert [(row["line"], row["first_line"]) for row in report["duplicates"]] == [(21, 6)]
    assert [row["line"] for row in report["mismatched"]] == [22]
    assert report["outside_heading"] == [2]
    assert {row["item"]: row["destinations"] for row in report["items"]}["socom:work:source-segment-001"] == [
        "src/gamez/zDir/dir_new.cpp", "src/gamez/zDir/dir_main.cpp", "src/gamez/zDir/b.cpp", "not a path",
    ]
    summary = report["summary"]
    assert (summary["placed"], summary["unmatched"], summary["duplicates"], summary["mismatched"]) == (9, 2, 1, 1)
    assert (summary["contiguity_conflicts"], summary["destinations_with_conflicts"], summary["invalid_headings"]) == (2, 2, 1)
    assert (summary["elf_objections"], summary["placed_unresolved"], summary["plan_items"]) == (5, 2, 4)
    # The text form names the conflicts and the bad lines.
    assert cli.main(["--root", str(tmp_path), "source", "placements", "check", "--file", "build/decisions/check.md"]) == 1
    text = capsys.readouterr().out
    assert "CONFLICT: src/gamez/zDir/dir_main.cpp's a_middle at 0x100010" in text and "line 20 (zdir/dir_main.cpp)" in text
    assert text.rstrip().endswith("NOT OK")


def test_placements_check_passes_a_clean_file(tmp_path: Path, capsys) -> None:
    _check_workspace(tmp_path)
    (tmp_path / "build/decisions/clean.md").write_text("## zdir/zdir.h\n- CDir::Run()\n\n## rt/rtlist.h\n- fooHelper\n", encoding="utf-8")
    code = cli.main(["--root", str(tmp_path), "source", "placements", "check", "--file", "build/decisions/clean.md", "--json"])
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report["ok"], report["summary"]
    assert report["summary"]["placed"] == 2 and report["summary"]["destinations"] == 2


# -- revisions of a decision file -----------------------------------------------------------------


def _revise(root: Path, text: str, *, store: bool = True) -> None:
    """Store the current decision file as its revision under history/ (unless ``store`` is false), then write ``text``."""

    path = root / DECISIONS
    if store:
        old = path.read_bytes()
        stored = root / revision_path(DECISIONS, normalized_sha256(old))
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(old)
    path.write_text(text, encoding="utf-8", newline="\n")


def _entry_cited(user) -> dict:
    """The user-named plan with an entry decision too: a_first placed by the user into a.cpp."""

    plan = copy.deepcopy(user[3])
    _cite(plan, 0, "socom:function:0x140000", "zfoo/a.cpp")
    plan["owners"][0]["confidence"] = "medium"
    return plan


def test_revision_paths_sit_in_history_beside_the_file() -> None:
    assert revision_path("docs/reconstruction/decisions/placements.md", "ab" * 32) == (
        "docs/reconstruction/decisions/history/placements." + "ab" * 32 + ".md"
    )


def test_a_stored_earlier_revision_with_unchanged_placements_holds_with_a_note(user) -> None:
    root = user[0]
    plan = _entry_cited(user)
    cited = normalized_sha256(DECISION_TEXT.encode("utf-8"))
    # The user adds a heading and a note, and moves a line the plan's citations do not place.
    revised = DECISION_TEXT.replace("## zfoo/zfoo_empty.cpp\n- a_first\n", "## zfoo/zfoo_empty.cpp\nNote: reconsidered.\n") + (
        "\n## zfoo/zfoo_later.cpp\n- a_first\n"
    )
    _revise(root, revised)
    report = _report(user, copy.deepcopy(plan))
    assert report["ok"], report["problems"]
    current = normalized_sha256(revised.encode("utf-8"))
    notes = [note for note in report["review"] if "cites revision" in note]
    assert len(notes) == 2 and report["decision_revisions"] == notes and report["summary"]["decision_revisions"] == 2
    assert notes[0] == (
        f"owner 1 (a.cpp) entry socom:function:0x140000 cites revision {cited} of {DECISIONS}; current {current}; "
        "this heading's placements for the row unchanged"
    )
    assert notes[1].startswith("owner 3 (zfoo_box.cpp) cites revision")
    # Citing the current file needs no note.
    current_plan = copy.deepcopy(plan)
    for owner in current_plan["owners"]:
        for value in [owner.get("decision")] + [entry.get("decision") for entry in owner["artifacts"] if isinstance(entry, dict)]:
            if value:
                value["sha256"] = current
    report = _report(user, current_plan)
    assert report["ok"] and report["decision_revisions"] == [] and "decision_revisions" not in report["summary"]
    # A CRLF checkout of the stored revision is still that revision.
    (root / revision_path(DECISIONS, cited)).write_bytes(DECISION_TEXT.replace("\n", "\r\n").encode("utf-8"))
    assert _report(user, copy.deepcopy(plan))["ok"]


_BOX = "## zfoo/zfoo_box.cpp\nNote: the CBox accessors are their own file (the user's reading of the neighbours).\n- CBox::Get()\n"
REVISION_DEFECTS = [
    # The row's artifact moved to another heading: the plan must be amended.
    (DECISION_TEXT.replace(_BOX, "## zfoo/zfoo_box.cpp\n").replace("## zfoo/zfoo_empty.cpp\n", "## zfoo/zfoo_empty.cpp\n- CBox::Get()\n"),
     "heading 'zfoo/zfoo_box.cpp' no longer lists socom:function:0x140010; amend the plan to cite the current file"),
    # The entry's heading is gone.
    (DECISION_TEXT.replace("## zfoo/a.cpp\n- a_first\n", ""), "the current file has no heading 'zfoo/a.cpp'; amend the plan to cite it"),
]


@pytest.mark.parametrize(("revised", "message"), REVISION_DEFECTS)
def test_a_stored_revision_whose_placements_changed_is_a_problem(user, revised: str, message: str) -> None:
    plan = _entry_cited(user)
    _revise(user[0], revised)
    report = _report(user, plan)
    assert not report["ok"] and any(message in problem for problem in report["problems"]), report["problems"]
    cited = normalized_sha256(DECISION_TEXT.encode("utf-8"))
    assert all(f"cites revision {cited}" in problem for problem in report["problems"] if message in problem)


def test_an_unstored_or_tampered_revision_is_a_problem(user) -> None:
    root = user[0]
    plan = _entry_cited(user)
    cited = normalized_sha256(DECISION_TEXT.encode("utf-8"))
    _revise(root, DECISION_TEXT + "\nNote: a later thought.\n", store=False)
    problems = _report(user, copy.deepcopy(plan))["problems"]
    assert any(f"not the cited {cited}, and no stored revision {revision_path(DECISIONS, cited)} exists" in problem
               for problem in problems), problems
    # A stored file whose content is not the revision its name gives is no revision.
    stored = root / revision_path(DECISIONS, cited)
    stored.parent.mkdir(parents=True, exist_ok=True)
    stored.write_text(DECISION_TEXT + "- edited\n", encoding="utf-8")
    problems = _report(user, copy.deepcopy(plan))["problems"]
    assert any("has LF-normalized SHA-256" in problem and "not its name's" in problem for problem in problems), problems


def test_placements_check_lists_the_file_revisions_and_plan_citations(tmp_path: Path, capsys) -> None:
    _check_workspace(tmp_path)
    relative = "build/decisions/clean.md"
    first = "## zdir/zdir.h\n- CDir::Run()\n\n## rt/rtlist.h\n- fooHelper\n"
    (tmp_path / relative).write_text(first, encoding="utf-8")

    def check(*extra: str) -> tuple[int, Any]:
        code = cli.main(["--root", str(tmp_path), "source", "placements", "check", "--file", relative, *extra])
        out = capsys.readouterr().out
        return code, (json.loads(out) if extra else out)

    code, report = check("--json")
    assert code == 0 and report["citations"] == [] and report["revisions"] == []
    placed = {row["heading"]: row["artifacts"][0] for row in report["destinations"]}
    item = placed["rt/rtlist.h"]["item"]
    plan_file = tmp_path / "build" / "source-plans" / f"{item.replace(':', '-')}.json"
    plan = json.loads(plan_file.read_text(encoding="utf-8")) if plan_file.is_file() else {"owners": []}
    cite = {"file": relative, "sha256": normalized_sha256(first.encode()), "heading": "rt/rtlist.h"}
    plan["owners"].append({"translation_unit": "rtlist.cpp", "name_basis": "user", "decision": cite,
                           "artifacts": [placed["rt/rtlist.h"]["id"]]})
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    code, report = check("--json")
    assert code == 0 and [(row["revision"], row["holds"]) for row in report["citations"]] == [("current", True)]

    # The revision is stored, then the file revised keeping the cited placements: the citation holds, with a note.
    stored = tmp_path / revision_path(relative, cite["sha256"])
    stored.parent.mkdir(parents=True)
    stored.write_text(first, encoding="utf-8")
    (tmp_path / relative).write_text(first + "\n## zdir/zdir_more.cpp\nNote: later.\n", encoding="utf-8")
    code, report = check("--json")
    assert code == 0, report["summary"]
    assert report["revisions"] == [
        {"path": revision_path(relative, cite["sha256"]), "sha256": cite["sha256"], "content_sha256": cite["sha256"], "ok": True}
    ]
    (row,) = report["citations"]
    assert (row["revision"], row["holds"], row["item"]) == ("stored", True, item)
    assert row["notes"] and row["notes"][0].endswith("this heading's placements for the row unchanged")
    summary = report["summary"]
    assert (summary["citations_on_revision"], summary["broken_citations"], summary["citing_plans"]) == (1, 0, 1)
    code, text = check()
    assert code == 0 and f"revision {cite['sha256']} (placements unchanged): {item.removeprefix('socom:work:')}" in text

    # A revision that moves the cited artifact breaks the citation; a tampered stored revision is reported.
    (tmp_path / relative).write_text("## zdir/zdir.h\n- CDir::Run()\n- fooHelper\n\n## rt/rtlist.h\nNote: moved.\n", encoding="utf-8")
    code, report = check("--json")
    assert code == 1 and report["summary"]["broken_citations"] == 1 and "no longer lists" in report["citations"][0]["problems"][0]
    stored.write_text(first + "- edited\n", encoding="utf-8")
    code, text = check()
    assert code == 1 and "not its name's" in text and "BROKEN" in text and text.rstrip().endswith("NOT OK")
