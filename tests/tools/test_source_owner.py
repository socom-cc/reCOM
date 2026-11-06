"""``source owner``: one artifact's owner, plan status, deferral and fenced code (synthetic workspace)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools._socom import cli
from tools._socom.source_graph import build_source_graph
from tools._socom.source_owner import if0_regions, readable
from tools._socom.source_plan import SOURCE_SEED_ID, plan_path

from test_source_graph import write_elf  # noqa: E402 - tests/tools is on sys.path (rootdir import mode)

RUN = "socom:function:0x100060"  # Run__4CDirFv, alone in segment 003
FIRST = "socom:function:0x100000"  # a_first, segment 001
SEGMENT_1 = "socom:work:source-segment-001"
SEGMENT_3 = "socom:work:source-segment-003"
REASON = "between the a.cpp run and the static initializer: a.cpp's tail or an unnamed object; nothing places the cut"


def _owner_row(unit: str, artifact: str) -> dict:
    return {
        "translation_unit": unit, "classification": "authored", "workspace_path": f"src/{unit}", "original_path": None,
        "provisional_file": f"src/{unit}", "library": None, "archive_member": None, "confidence": "high",
        "evidence": ["x"], "artifacts": [{"artifact": artifact, "confidence": "high", "basis": "a.cpp's DWARF unit", "draft_rule": "A-dwarf-cu"}],
    }


def _plan(item: str, **rows) -> dict:
    return {"kind": "socom-source-owner-plan", "schema_version": 2, "work_item_id": item, "owners": [], "unresolved": [],
            "contradictions": [], "header_emits": [], "annotations": [], "notes": [], **rows}


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _workspace(root: Path) -> dict[str, Path]:
    """The synthetic ELF, its graph, a src/ tree, two plans and a tracker that cites them."""

    (root / "support").mkdir()
    graph = build_source_graph(write_elf(root / "support" / "socom.elf"))
    _write(root, "build/source-graph/graph.json", json.dumps(graph))
    _write(root, "src/a.cpp", (
        "/* socom-owner-annotations begin socom:work:source-segment-001\n"
        f" * @socom-artifact defines main {FIRST}\n"
        " * socom-owner-annotations end socom:work:source-segment-001 */\n"
        "\n/* @socom-skeleton stub a_first */\nvoid a_first()\n{\n}\n"
    ))
    _write(root, "src/a.h", f"/* @socom-artifact emits main {FIRST} */\nclass CDir\n{{\n\t/* @socom-skeleton decl 4CDir */\n\tvoid Run();\n\t/* @socom-skeleton end 4CDir */\n}};\n")
    _write(root, "src/zdir/zdir_holding.cpp", (
        "/* Unbuilt holding file (stage 5 BD4) */\n"
        "\n/* @socom-skeleton body Run__4CDirFi */\n/* held from src/zdir/dir.cpp:3 */\n"
        "#if 0 /* port: duplicate of src/zdir/dir.cpp */\nvoid CDir::Run(int)\n{\n}\n#endif\n"
        "\n/* @socom-skeleton body tacmap_polys */\n/* held from src/zdir/dir.cpp:9 */\nint tacmap_polys;\n"
    ))
    plans = {
        SEGMENT_1: _plan(SEGMENT_1, owners=[_owner_row("a.cpp", FIRST)],
                         header_emits=[{"artifact": FIRST, "header": "src/a.h", "reason": "inline", "evidence": ["two units"]}]),
        SEGMENT_3: _plan(
            SEGMENT_3,
            unresolved=[{"artifact": RUN, "reason": REASON}],
            contradictions=[{"artifact": RUN, "kind": "signature", "provisional_file": "src/zdir/dir.cpp", "line": 3,
                             "elf_evidence": ["Run__4CDirFv takes no argument; the provisional definition takes int"]}],
            notes=[f"override {RUN}: the draft gave a.cpp", "socom:function:0x1000600 is another artifact"],
        ),
    }
    paths = {}
    items = []
    for item, plan in plans.items():
        paths[item] = _write(root, plan_path(item), json.dumps(plan))
        sha = hashlib.sha256(paths[item].read_bytes()).hexdigest()
        items.append({"id": item, "kind": "source-plan-segment", "stage": "source-correlation", "status": "accepted",
                      "evidence": [f"plan {plan_path(item)} sha256:{sha}; validate --check ok"]})
        items.append({"id": f"{item}-apply", "kind": "source-apply-segment", "stage": "source-correlation", "status": "accepted",
                      "source_apply": {"plan_sha256": sha}})
    deferral = {"id": "boundary-functions", "artifacts": [RUN], "reason": "two cuts equally consistent",
                "issue": "socom:workspace-issue:0123456789abcdef0123", "approval": None}
    items.append({"id": SOURCE_SEED_ID, "kind": "stage-gate", "stage": "source-correlation", "status": "accepted",
                  "source_gate": {"deferrals": [deferral]}})
    _write(root, ".agent/RECONSTRUCTION_PROGRESS.json", json.dumps({"work_items": items, "stages": []}))
    return paths


def _owner(capsys, root: Path, *arguments: str) -> tuple[int, dict]:
    code = cli.main(["--root", str(root), "source", "owner", *arguments, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_unresolved_artifact_shows_reason_contradiction_deferral_and_held_code(tmp_path: Path, capsys) -> None:
    _workspace(tmp_path)
    code, report = _owner(capsys, tmp_path, "CDir::Run")
    assert code == 0 and report["ok"] and report["mutation_performed"] is False and report["shown"] == "single"
    (detail,) = report["details"]
    assert detail["id"] == RUN and detail["declaration"] == "CDir::Run()" and detail["classification"] == "authored"
    assert detail["names"] == [{"name": "Run__4CDirFv", "binding": "GLOBAL", "symbol_index": detail["names"][0]["symbol_index"],
                                "kind": "function", "declaration": "CDir::Run()"}]
    assert detail["owner"]["status"] == "unresolved" and detail["annotations"] == []
    (plan,) = detail["plans"]
    assert (plan["item"], plan["file"], plan["in_scope"], plan["lists"]) == (SEGMENT_3, "unchanged", True, True)
    assert plan["unresolved"] == {"reason": REASON} and plan["apply"]["plan_matches"] is True
    assert [row["kind"] for row in plan["contradictions"]] == ["signature"]
    # A note citing the artifact is shown; one citing a longer address is not.
    assert plan["notes"] == [f"override {RUN}: the draft gave a.cpp"]
    assert [row["id"] for row in detail["deferrals"]] == ["boundary-functions"]
    (fence,) = detail["code"]["fences"]
    assert fence["path"] == "src/zdir/zdir_holding.cpp" and fence["kind"] == "body" and fence["match"] == "other-signature"
    assert fence["holding"] is True and fence["held_from"] == "src/zdir/dir.cpp:3"
    assert fence["if0"] == [{"line": 5, "end_line": 9, "comment": "port: duplicate of src/zdir/dir.cpp", "encloses_fence": False}]
    assert detail["code"]["declarations"] == [{"path": "src/a.h", "line": 4, "region": "4CDir"}]
    # The text block prints the reason in full and the holding fence.
    assert cli.main(["--root", str(tmp_path), "source", "owner", "Run__4CDirFv"]) == 0
    text = capsys.readouterr().out
    assert f"reason: {REASON}" in text and "deferral boundary-functions" in text
    assert "contradiction signature at src/zdir/dir.cpp:3" in text
    assert "src/zdir/zdir_holding.cpp:3  body Run__4CDirFi  [holding file; other signature; held from src/zdir/dir.cpp:3; #if 0" in text


def test_owned_artifact_by_address_shows_annotations_plan_row_and_exact_fence(tmp_path: Path, capsys) -> None:
    _workspace(tmp_path)
    code, report = _owner(capsys, tmp_path, "0x100000")
    assert code == 0 and report["matches"][0]["how"] == "address"
    (detail,) = report["details"]
    assert detail["owner"] == {"status": "annotated", "path": "src/a.cpp", "summary": "src/a.cpp (defines annotation)"}
    assert [(row["relation"], row["path"], row["line"]) for row in detail["annotations"]] == [
        ("defines", "src/a.cpp", 2), ("emits", "src/a.h", 1)
    ]
    (plan,) = detail["plans"]
    assert plan["owner"]["translation_unit"] == "a.cpp" and plan["owner"]["entry"]["draft_rule"] == "A-dwarf-cu"
    assert plan["header_emits"][0]["header"] == "src/a.h"
    assert detail["code"]["fences"] == [
        {"path": "src/a.cpp", "line": 5, "kind": "stub", "name": "a_first", "match": "exact", "holding": False, "nested": False}
    ]
    # An address inside an artifact finds it; so does its ID.
    _code, inside = _owner(capsys, tmp_path, "0x100064")
    assert [(row["id"], row["how"]) for row in inside["matches"]] == [(RUN, "contains")]
    _code, by_id = _owner(capsys, tmp_path, "socom:function:0x100000")
    assert by_id["details"][0]["id"] == FIRST


def test_a_changed_or_missing_plan_is_reported(tmp_path: Path, capsys) -> None:
    paths = _workspace(tmp_path)
    plan = json.loads(paths[SEGMENT_3].read_text(encoding="utf-8"))
    plan["notes"].append("edited after acceptance")
    paths[SEGMENT_3].write_text(json.dumps(plan), encoding="utf-8")
    _code, report = _owner(capsys, tmp_path, RUN)
    (row,) = report["details"][0]["plans"]
    assert row["file"] == "changed" and row["recorded_sha256"] and row["sha256"] not in row["recorded_sha256"]
    assert row["apply"]["plan_matches"] is False
    assert cli.main(["--root", str(tmp_path), "source", "owner", RUN]) == 0
    assert "PLAN FILE CHANGED" in capsys.readouterr().out
    paths[SEGMENT_3].unlink()
    _code, report = _owner(capsys, tmp_path, RUN)
    detail = report["details"][0]
    assert detail["plans"] == [] and detail["owner"]["status"] == "unplanned"
    assert detail["plans_unread"][0] == {"item": SEGMENT_3, "status": "accepted", "path": plan_path(SEGMENT_3), "file": "missing", "in_scope": True}


def test_several_matches_are_listed_and_all_shows_each(tmp_path: Path, capsys) -> None:
    _workspace(tmp_path)
    code, report = _owner(capsys, tmp_path, "a_")
    assert code == 0 and report["shown"] == "list" and report["details"] == []
    assert [row["name"] for row in report["matches"]] == ["a_first", "a_middle", "a_third", "a_assist"]
    assert not any(row["exact"] for row in report["matches"])
    _code, report = _owner(capsys, tmp_path, "a_", "--all", "--limit", "2")
    assert report["shown"] == "all" and [row["id"] for row in report["details"]] == [FIRST, "socom:function:0x100010"]
    assert report["truncated"] is True
    # A provisional mangled spelling finds the artifact with its qualified name.
    _code, report = _owner(capsys, tmp_path, "Run__4CDirFi")
    assert [(row["id"], row["how"], row["exact"]) for row in report["matches"]] == [(RUN, "same-name", False)]
    assert report["shown"] == "single"


def test_no_match_lists_fences_of_that_name(tmp_path: Path, capsys) -> None:
    _workspace(tmp_path)
    code, report = _owner(capsys, tmp_path, "tacmap_polys")
    assert code == 1 and report["ok"] is False and report["matches"] == []
    assert [(row["path"], row["line"], row["held_from"]) for row in report["fences"]] == [
        ("src/zdir/zdir_holding.cpp", 11, "src/zdir/dir.cpp:9")
    ]


def test_if0_regions_and_readable_forms() -> None:
    lines = ["#if 0 // off", "a", "#else", "b", "#endif", "#ifdef X", "#if false", "#endif", "#endif", "#if 0x1", "#endif", "#if 0"]
    assert if0_regions(lines) == [
        {"line": 1, "end_line": 3, "comment": "off"},
        {"line": 7, "end_line": 8, "comment": None},
        {"line": 12, "end_line": 12, "comment": None},
    ]
    unnamed = readable("Helper__15@unnamed@b_cpp@Fv")
    assert unnamed["declaration"] == "(anonymous namespace)::Helper()" and unnamed["key"] == "Helper"
    assert readable("CanScan__11CAiSRescuedCFv")["class_region"] == "11CAiSRescued"
    assert readable("@1")["key"] is None
