"""Stage 5 phase A: order targets, the global object order, the link-order specification and its cache."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools._socom.order_target import (
    build_order_target,
    link_order,
    link_order_text,
    order_class,
    order_digest,
    order_regions,
    select_units,
)
from tools._socom.source_plan import graph_digest
from tools._socom.util import SocomError

from test_source_apply import _run, ready, workspace  # noqa: F401 - ready and workspace are fixtures
from test_source_plan import stage3_tracker  # noqa: F401 - a fixture the workspace needs

CODE, DATA = "socom:window:0x1000", "socom:window:0x9000"


def _row(kind: str, address: int, size: int, section: str | list, name: str | None = None, binding: str = "GLOBAL",
         window: str | None = None, **fields) -> dict:
    row = {
        "id": f"socom:{kind}:0x{address:x}",
        "kind": kind,
        "address": f"0x{address:x}",
        "end": f"0x{address + size:x}",
        "size": size,
        "window": window or (CODE if kind == "function" else DATA),
        "input_section": {"name": section} if isinstance(section, str) else {"between": section},
    }
    if kind == "gap":
        row.update(fill=fields.pop("fill", "zero"), padding=True, labels=fields.pop("labels", []))
    else:
        row.update(binding=binding, names=[{"name": name, "binding": binding}])
    row.update(fields)
    return row


def _graph(rows: list[dict]) -> dict:
    graph = {"windows": [{"id": CODE, "kind": "code"}, {"id": DATA, "kind": "data"}], "artifacts": rows}
    graph["graph_sha256"] = graph_digest(graph)
    return graph


def _owner(unit: str | None, artifacts: list[dict], classification: str = "authored", member: dict | None = None) -> dict:
    return {
        "translation_unit": unit,
        "classification": classification,
        "workspace_path": f"src/x/{unit}" if classification == "authored" else None,
        "original_path": None,
        "library": "SCE" if classification == "provider" else None,
        "archive_member": member,
        "artifacts": [{"artifact": row["id"]} for row in artifacts],
    }


ROWS = {
    "a_first": _row("function", 0x1000, 8, ".text", "a_first"),
    "a_fill": _row("gap", 0x1008, 8, ".text", window=CODE),
    "a_copy": _row("function", 0x1010, 8, ".text", "Get__4CBoxFv", "13"),
    "sce": _row("function", 0x1020, 16, ".text", "sceFoo"),
    "b_main": _row("function", 0x1030, 8, ".text", "b_main"),
    "b_thunk": _row("function", 0x1038, 8, ".text", "@8@__dt__1BFv", "13"),
    "b_find": _row("function", 0x1040, 8, ".text", "find<i>__3stdFPiPi", "LOCAL"),
    "b_sinit": _row("function", 0x1048, 8, ".text", "__sinit_b_cpp", "LOCAL"),
    "b_inline": _row("function", 0x1050, 8, ".text", "Inline__1BFv"),
    "a_lit1": _row("data", 0x9000, 8, ".rodata", "@12", "LOCAL"),
    "b_lit": _row("data", 0x9008, 8, ".rodata", "@13", "LOCAL"),
    "a_lit2": _row("data", 0x9010, 8, ".rodata", "@14", "LOCAL"),
    "deferred": _row("data", 0x9018, 8, ".rodata", "tbl", "LOCAL"),
    "a_lit3": _row("data", 0x9020, 8, ".rodata", "@15", "LOCAL"),
    "b_data": _row("data", 0x9100, 4, ".data", "g_b"),
    "c_data": _row("data", 0x9104, 4, ".data", "g_shared"),
    "c_bss": _row("data", 0x9204, 4, ".bss", "g_cz"),
    "a_bss": _row("data", 0x9208, 4, ".bss", "g_zero"),
    "b_common": _row("data", 0x9300, 4, [".bss", None], "g_common", common=True),
}


def _plans() -> list[dict]:
    r = ROWS
    segment = {
        "scope": {"kind": "segment", "segment_number": 1},
        "owners": [
            _owner("a.cpp", [r["a_first"], r["a_copy"], r["a_lit1"], r["a_lit2"], r["a_lit3"], r["a_bss"]]),
            _owner("b.cpp", [r["b_main"], r["b_thunk"], r["b_find"], r["b_sinit"], r["b_inline"], r["b_lit"], r["b_data"]]),
            _owner(None, [r["a_fill"]], "compiler-generated"),
        ],
        "header_emits": [{"artifact": r["b_inline"]["id"], "header": "src/x/b.h", "reason": "inline"}],
        "unresolved": [{"artifact": r["deferred"]["id"], "reason": "two definers fit"}],
    }
    provider = {
        "scope": {"kind": "provider", "library": "SCE"},
        "owners": [_owner(None, [r["sce"]], "provider", {"gnu_object": "0x1020", "object": None})],
        "header_emits": [],
        "unresolved": [],
    }
    data = {
        "scope": {"kind": "data", "data_kind": "bss"},
        "owners": [_owner("c.cpp", [r["c_data"], r["c_bss"]]), _owner("b.cpp", [r["b_common"]])],
        "header_emits": [],
        "unresolved": [],
    }
    return [
        {"item": "socom:work:source-segment-001", "kind": "source-plan-segment", "sha256": "1" * 64, "plan": segment},
        {"item": "socom:work:source-provider-sce", "kind": "source-plan-provider", "sha256": "2" * 64, "plan": provider},
        {"item": "socom:work:source-data-bss", "kind": "source-data-reconcile", "sha256": "3" * 64, "plan": data},
    ]


DEFERRALS = [{"id": "data-link-order", "artifacts": [ROWS["deferred"]["id"]], "issue": None, "approval": None}]


@pytest.fixture()
def target() -> dict:
    return build_order_target(_graph(list(ROWS.values())), _plans(), deferrals=DEFERRALS, boundaries=[])


def _unit(target: dict, name: str) -> dict:
    return next(row for row in target["units"] if row["unit"] == name)


def _section(unit: dict, label: str) -> dict:
    return next(row for row in unit["sections"] if row["label"] == label)


def test_order_classes_tell_definitions_from_copies_literals_and_fill() -> None:
    r = ROWS
    assert order_class(r["a_first"]) == "definition"
    assert order_class(r["a_copy"]) == "copy"  # binding 13
    assert order_class(r["b_thunk"]) == "copy"  # @N@ is a this-adjusting thunk, not a literal
    assert order_class(r["b_find"]) == "copy"  # a function template instance
    assert order_class(r["b_inline"], "src/x/b.h") == "copy"  # a header emit
    assert order_class(r["a_lit1"]) == "literal"
    assert order_class(r["a_fill"]) == "compiler-generated"
    assert order_class(_row("data", 0x9400, 4, ".data", "id__Q23std8ctype<c>")) == "copy"  # a class template member
    assert order_class(_row("function", 0x1100, 4, ".text", "__ct__1AFQ23std7vector<i>")) == "definition"


def test_units_list_their_artifacts_by_region_with_classes_runs_strays_and_deferrals(target: dict) -> None:
    a = _unit(target, "a.cpp")
    text = _section(a, ".text")
    # The fill between two of a.cpp's functions is inside its run; the class counts follow.
    assert [row["class"] for row in text["artifacts"]] == ["definition", "compiler-generated", "copy"]
    assert a["counts"] == {"definition": 2, "copy": 1, "literal": 3, "compiler-generated": 1, "generated_definitions": 0}
    rodata = _section(a, ".rodata")
    # Two runs: @12 alone, then @14..@15 around the deferred row; the larger run places a.cpp.
    assert (rodata["runs"], rodata["contiguous"], rodata["start"], rodata["first"]) == (2, False, "0x9010", "0x9000")
    assert rodata["strays"] == [{"artifact": ROWS["a_lit1"]["id"], "name": "@12", "class": "literal"}]
    assert rodata["deferred"] == [
        {"artifact": ROWS["deferred"]["id"], "kind": "data", "name": "tbl", "category": "data-link-order",
         "item": "socom:work:source-segment-001"}
    ]
    b = _unit(target, "b.cpp")
    entries = {row["name"]: row for row in _section(b, ".text")["artifacts"]}
    assert entries["__sinit_b_cpp"]["generated"] is True and entries["Inline__1BFv"]["header"] == "src/x/b.h"
    assert b["counts"]["generated_definitions"] == 1 and b["counts"]["copy"] == 3
    assert "note" in _section(b, "between .bss and end")  # COMMON is linker-placed
    kinds = sorted((row["kind"], row["unit"]) for row in target["findings"])
    assert kinds == [("deferred-in-span", "a.cpp"), ("interleaved", "a.cpp"), ("object-order", None)]
    interleaved = next(row for row in target["findings"] if row["kind"] == "interleaved")
    assert interleaved["stray_classes"] == {"literal": 1} and interleaved["intruders"] == ["b.cpp"]


def test_global_order_and_region_checks(target: dict) -> None:
    order = [row["object"] for row in target["objects"]]
    # .text order, then the data-only c.cpp after b.cpp, which precedes it in .data.
    assert order == ["a.cpp", "SCE:gnu@0x1020", "b.cpp", "c.cpp"]
    assert [row["text_position"] for row in target["objects"]] == [1, 2, 3, None]
    assert [row["primary_segment"] for row in target["objects"]] == [1, None, 1, None]
    checks = {row["label"]: row for row in target["checks"]}
    assert (checks[".rodata"]["drops"], checks[".rodata"]["link_violations"]) == (1, 1)  # b.cpp's run before a.cpp's
    assert checks[".rodata"]["examples"][0]["before"] == "b.cpp"
    assert (checks[".data"]["drops"], checks[".data"]["link_violations"]) == (0, 0)
    assert (checks[".bss"]["compared"], checks[".bss"]["link_violations"]) == (1, 1)  # c.cpp before a.cpp contradicts .data
    assert checks["between .bss and end"]["checked"] is False
    summary = target["summary"]
    assert (summary["units"], summary["provider_objects"], summary["object_order_disagreements"]) == (3, 1, 1)
    assert (summary["link_violations"], summary["split_contributions"], summary["deferred_in_spans"]) == (2, 1, 1)
    assert summary["unresolved_by_category"] == {"data-link-order": 1} and summary["unplanned_artifacts"] == 0
    spec = link_order(target)
    assert spec["check"]["ok"] is False and spec["check"]["violations"] == 2
    assert link_order_text(spec).splitlines()[3:] == ["src/x/a.cpp", "SCE(gnu@0x1020)", "src/x/b.cpp", "src/x/c.cpp"]


def test_the_digest_is_deterministic_and_follows_the_inputs(target: dict) -> None:
    assert target["order_sha256"] == order_digest(target)
    again = build_order_target(_graph(list(ROWS.values())), _plans(), deferrals=DEFERRALS, boundaries=[])
    assert again == target
    plans = _plans()
    plans[0]["sha256"] = "4" * 64
    changed = build_order_target(_graph(list(ROWS.values())), plans, deferrals=DEFERRALS, boundaries=[])
    assert changed["order_sha256"] != target["order_sha256"]
    assert [row["unit"] for row in select_units(target, segment=1)] == ["a.cpp", "b.cpp"]
    assert [row["unit"] for row in select_units(target, unit="C.CPP")] == ["c.cpp"]
    with pytest.raises(SocomError, match="no authored unit"):
        select_units(target, unit="z.cpp")


def test_double_ownership_is_a_problem() -> None:
    plans = _plans()
    plans[2]["plan"]["owners"][0]["artifacts"].append({"artifact": ROWS["a_first"]["id"]})
    found = build_order_target(_graph(list(ROWS.values())), plans, deferrals=[], boundaries=[])
    assert found["summary"]["problems"] == 1 and "owned twice" in found["problems"][0]


def test_regions_split_at_linker_symbols_zero_fill_and_windows() -> None:
    other = "socom:window:0x9800"
    rows = [
        _row("data", 0x9000, 4, ".data", "x"),
        _row("data", 0x9004, 4, ".data", "y"),
        _row("gap", 0x9008, 8, ".data"),
        _row("gap", 0x9010, 16, ".bss", fill="nobits"),
        _row("data", 0x9020, 4, ".bss", "z"),
        _row("gap", 0x9024, 4, ".bss", fill="nobits", labels=["__bss_start"]),
        _row("data", 0x9800, 4, ".bss", "w", window=other),
    ]
    graph = {"windows": [{"id": DATA, "kind": "data"}, {"id": other, "kind": "data"}], "artifacts": rows}
    regions, region_of = order_regions(graph, [{"address": "0x9004", "name": "__data_end"}])
    assert [row["label"] for row in regions] == [
        ".data", ".data from __data_end", ".bss", ".bss from __bss_start", ".bss #2",
    ]
    assert [row["nobits"] for row in regions] == [False, False, True, True, False]
    assert region_of[rows[2]["id"]] == 2


# -- the CLI over a synthetic stage 4 workspace -------------------------------------------------


def test_cli_target_selections_link_spec_and_sql(ready: tuple[Path, dict], capsys) -> None:
    root, graph = ready
    base = ["--root", str(root), "order"]
    code, report = _run(capsys, *base, "target", "--output", "build/stage5/target.json")
    assert code == 0 and report["mutation_performed"] is False
    assert (report["units"], report["provider_objects"], report["classes"]["copy"]) == (2, 1, 1)
    stored = json.loads((root / "build" / "stage5" / "target.json").read_text(encoding="utf-8"))
    assert stored["order_sha256"] == report["order_sha256"] and stored["inputs"]["stage4_baseline_sha256"] is None
    assert [row["object"] for row in stored["objects"]] == ["a.cpp", "SCE:gnu@0x140020", "b.cpp"]
    code, view = _run(capsys, *base, "target", "--unit", "a.cpp")
    assert code == 0 and view["kind"] == "socom-order-target-view" and [row["unit"] for row in view["units"]] == ["a.cpp"]
    code, view = _run(capsys, *base, "target", "--segment", "3")
    assert code == 0 and [row["unit"] for row in view["units"]] == ["b.cpp"]
    code, refused = _run(capsys, *base, "target", "--segment", "2")
    assert code == 2 and "no accepted authored owner plan" in refused["error"]
    code, refused = _run(capsys, *base, "target", "--output", "elsewhere.json")
    assert code == 2 and "under build/" in refused["error"]
    code, spec = _run(capsys, *base, "link-spec", "--output", "build/stage5/link.json")
    assert code == 0 and spec["ok"] and spec["objects"] == 3 and spec["text"] == "build/stage5/link.txt"
    lines = (root / "build" / "stage5" / "link.txt").read_text(encoding="utf-8").splitlines()
    assert lines[3:] == ["src/gamez/zBar/a.cpp", "SCE(gnu@0x140020)", "src/gamez/zBaz/b.cpp"]
    body = json.loads((root / "build" / "stage5" / "link.json").read_text(encoding="utf-8"))
    assert body["kind"] == "socom-link-order" and body["link_order_sha256"] == spec["link_order_sha256"]
    statement = "SELECT unit, class, count(*) FROM targets GROUP BY unit, class ORDER BY unit, class"
    code, result = _run(capsys, *base, "sql", statement, "--format", "json")
    assert code == 0 and result["rebuilt"] is True
    assert ["a.cpp", "copy", 1] in result["rows"] and ["b.cpp", "definition", 3] in result["rows"]
    code, result = _run(capsys, *base, "sql", statement, "--format", "json")
    assert code == 0 and result["rebuilt"] is False
    code, refused = _run(capsys, *base, "sql", "DELETE FROM targets")
    assert code == 2 and "order sql accepts" in refused["error"]


def test_cli_refuses_another_graph(ready: tuple[Path, dict], capsys) -> None:
    root, graph = ready
    changed = copy.deepcopy(graph)
    changed["segment_size"] = 100
    changed["graph_sha256"] = graph_digest(changed)
    (root / "build" / "source-graph" / "other.json").write_text(json.dumps(changed), encoding="utf-8")
    code, refused = _run(capsys, "--root", str(root), "order", "target", "--graph", "build/source-graph/other.json")
    assert code == 2 and "is not stage 4's decomposition graph" in refused["error"]


def test_cli_needs_accepted_plans(workspace: tuple[Path, dict], capsys) -> None:
    root, _graph_unused = workspace
    code, refused = _run(capsys, "--root", str(root), "order", "target")
    assert code == 2 and "no accepted source-correlation owner plans" in refused["error"]
