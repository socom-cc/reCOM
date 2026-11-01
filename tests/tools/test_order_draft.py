"""Stage 5 phase A2 drafts: source-order evidence, adjacency classes and the emission-rule calibration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools._socom.order_draft import build_order_draft, draft_digest
from tools._socom.order_target import build_order_target

from test_order_target import _graph, _owner, _row
from test_source_apply import _run, ready, workspace  # noqa: F401 - ready and workspace are fixtures
from test_source_plan import stage3_tracker  # noqa: F401 - a fixture the workspace needs

# d.cpp has DWARF lines: f3..f0 out-of-line definitions in reverse source order, an in-class member (line 5)
# placed after its first user f2, a kept inline copy after the same user, and two definitions without a
# source position.  n.cpp has none: four functions with local-static counters and literal labels, its static
# initializer, and .bss data (two local statics, a guard, three objects the initializer sets up, one COMMON).
ROWS = {
    "f3": _row("function", 0x1000, 8, ".text", "f3__Fv"),
    "f2": _row("function", 0x1008, 8, ".text", "f2__Fv"),
    "copy": _row("function", 0x1010, 8, ".text", "Get__4CBoxFv", "13"),
    "inl": _row("function", 0x1018, 8, ".text", "Get__Q215@unnamed@d_cpp@4CItrFv", "LOCAL"),
    "f1": _row("function", 0x1020, 8, ".text", "f1__Fv"),
    "f0": _row("function", 0x1028, 8, ".text", "f0__Fv"),
    "arraydtor": _row("function", 0x1030, 8, ".text", "__arraydtor$12", "LOCAL"),
    "implicit": _row("function", 0x1038, 8, ".text", "__dt__Q215@unnamed@d_cpp@4CItrFv", "LOCAL"),
    "gz": _row("function", 0x1040, 8, ".text", "gz__Fv"),
    "gc": _row("function", 0x1048, 8, ".text", "gc__Fv"),
    "gb": _row("function", 0x1050, 8, ".text", "gb__Fv"),
    "ga": _row("function", 0x1058, 8, ".text", "ga__Fv"),
    "sinit": _row("function", 0x1060, 16, ".text", "__sinit_n_cpp", "LOCAL"),
    "x": _row("data", 0x9000, 4, ".bss", "x$110", "LOCAL"),
    "guard": _row("data", 0x9004, 4, ".bss", "init$111", "LOCAL"),
    "y": _row("data", 0x9008, 4, ".bss", "y$120", "LOCAL"),
    "one": _row("data", 0x900C, 4, ".bss", "g_one"),
    "two": _row("data", 0x9010, 4, ".bss", "g_two"),
    "three": _row("data", 0x9014, 4, ".bss", "g_three"),
    "common": _row("data", 0x9300, 4, [".bss", None], "g_common", common=True),
}
D_UNIT = ("f3", "f2", "copy", "inl", "f1", "f0", "arraydtor", "implicit")
N_UNIT = ("gz", "gc", "gb", "ga", "sinit", "x", "guard", "y", "one", "two", "three", "common")


def _id(key: str) -> str:
    return ROWS[key]["id"]


def _target() -> dict:
    plan = {
        "scope": {"kind": "segment", "segment_number": 1},
        "owners": [_owner("d.cpp", [ROWS[key] for key in D_UNIT]), _owner("n.cpp", [ROWS[key] for key in N_UNIT])],
        "header_emits": [],
        "unresolved": [],
    }
    plans = [{"item": "socom:work:source-segment-001", "kind": "source-plan-segment", "sha256": "1" * 64, "plan": plan}]
    return build_order_target(_graph(list(ROWS.values())), plans, deferrals=[], boundaries=[])


def _raw() -> dict:
    lines = [("f3", 30), ("f2", 20), ("inl", 5), ("f1", 10), ("f0", 8)]
    rows = [{"artifact": _id(key), "tu": "d.cpp", "address": int(ROWS[key]["address"], 16), "line": line} for key, line in lines]
    rows.append({"artifact": _id("f3"), "tu": "d.cpp", "address": 0x1004, "line": 31})  # a later row
    rows.append({"artifact": _id("gz"), "tu": "other.cpp", "address": 0x1040, "line": 7})  # another unit's line
    labels = [
        ("gz", "u$200"), ("gc", "s$300"), ("gb", "v$150"), ("ga", "t$100"),
        ("gb", "w$120"), ("gc", "w$120"),  # shared: no function's own
        ("gz", "@30"), ("gc", "@40"), ("gb", "@50"), ("ga", "@60"), ("gz", "__arraydtor$5"),
    ]
    uses = [
        ("sinit", "one", 0x1060), ("sinit", "three", 0x1064), ("sinit", "two", 0x1068),
        ("f2", "inl", 0x100C), ("f2", "copy", 0x1008),
    ]
    return {
        "lines": rows,
        "labels": [{"site_artifact": _id(site), "symbol": symbol} for site, symbol in labels],
        "uses": [{"site_artifact": _id(site), "target_artifact": _id(found), "site": at} for site, found, at in uses],
        "compile_units": [
            {"object_unit": "d.cpp", "die_offset": 1, "low_pc": 0x1000}, {"object_unit": "d.cpp", "die_offset": 2, "low_pc": 0x1008},
        ],
        "variables": [{"unit": "n.cpp", "order": 0, "artifact": _id("one")}, {"unit": "n.cpp", "order": 1, "artifact": _id("two")}],
    }


@pytest.fixture()
def draft() -> dict:
    return build_order_draft(_target(), _raw())


def _unit(draft: dict, name: str) -> dict:
    return next(row for row in draft["units"] if row["unit"] == name)


def _names(rows: list[dict]) -> list[str]:
    return [row["name"] for row in rows]


def test_dwarf_lines_prove_the_source_order_and_unplaced_definitions_are_listed_apart(draft: dict) -> None:
    d = _unit(draft, "d.cpp")
    assert d["dwarf_lines"] is True and d["functions"]["basis"] == "dwarf-lines"
    assert _names(d["functions"]["order"]) == [
        "Get__Q215@unnamed@d_cpp@4CItrFv", "f0__Fv", "f1__Fv", "f2__Fv", "f3__Fv",
    ]
    assert d["functions"]["order"][0]["file_local"] is True and d["functions"]["order"][-1]["line"] == 30
    assert {row["class"] for row in d["functions"]["adjacencies"]} == {"proven"}
    assert d["status"] == {"functions": "proven", "data": "trivial", "unit": "proven"}
    assert [(row["name"], row["reason"]) for row in d["not_placed"]] == [
        ("__arraydtor$12", "compiler-generated"), ("__dt__Q215@unnamed@d_cpp@4CItrFv", "no-dwarf-line"),
    ]


def test_without_lines_the_rule_drafts_reverse_address_order_and_counters_constrain_it(draft: dict) -> None:
    n = _unit(draft, "n.cpp")
    functions = n["functions"]
    assert functions["basis"] == "reverse-address" and _names(functions["order"]) == ["ga__Fv", "gb__Fv", "gc__Fv", "gz__Fv"]
    # The shared static w$120 is nobody's own; the lowest private N and the highest private @N count.
    assert [(row.get("static_counter"), row.get("literal_label")) for row in functions["order"]] == [
        (100, 60), (150, 50), (300, 40), (200, 30),
    ]
    adjacencies = functions["adjacencies"]
    assert [row["class"] for row in adjacencies] == ["constrained", "constrained", "hypothesis"]
    assert adjacencies[2]["conflicts"] == ["local-static-counter"]
    # Literal labels follow the emission order: they corroborate, never constrain.
    assert all(row["corroborated_by"] == ["literal-labels"] for row in adjacencies)
    assert [(row["values"], row["agrees"]) for row in functions["constraints"]] == [
        ([100, 150], True), ([150, 200], True), ([200, 300], False),
    ]
    assert functions["status"] == "constrained"
    assert [(row["name"], row["reason"]) for row in n["not_placed"]] == [
        ("__sinit_n_cpp", "generated"), ("init$111", "static-guard"), ("g_common", "common"),
    ]


def test_data_follows_address_order_with_counter_and_initializer_constraints(draft: dict) -> None:
    (bss,) = _unit(draft, "n.cpp")["data"]
    assert bss["basis"] == "address" and _names(bss["order"]) == ["x$110", "y$120", "g_one", "g_two", "g_three"]
    assert [(row.get("static_counter"), row.get("sinit"), row.get("variable")) for row in bss["order"]] == [
        (110, None, None), (120, None, None), (None, 0, 0), (None, 2, 1), (None, 1, None),
    ]
    classes = [(row["class"], row["basis"], row.get("conflicts"), row.get("corroborated_by")) for row in bss["adjacencies"]]
    assert classes == [
        ("constrained", ["local-static-counter"], None, None),
        ("hypothesis", [], None, None),
        ("constrained", ["static-initializer"], None, ["dwarf-variable-order"]),
        ("hypothesis", [], ["static-initializer"], None),
    ]
    assert [row["agrees"] for row in bss["constraints"]] == [True, True, False]
    summary = draft["summary"]
    assert summary["data"]["constraints_against_draft"] == 1 and summary["functions"]["constraints_against_draft"] == 1
    assert summary["status"]["unit"] == {"proven": 1, "constrained": 1, "hypothesis": 0, "trivial": 0}
    assert summary["not_placed"] == {"common": 1, "compiler-generated": 1, "generated": 1, "no-dwarf-line": 1, "static-guard": 1}


def test_the_calibration_measures_each_evidence_against_dwarf_lines(draft: dict) -> None:
    calibration = draft["calibration"]
    assert calibration["dwarf_units"] == {"units": 1, "units_with_3": 1, "functions": 5, "pairs": 10, "steps": 4}
    measures = {row["evidence"]: row for row in calibration["functions"]}
    reverse = measures["reverse-address"]
    assert (reverse["agree"], reverse["pairs"], reverse["steps_agree"], reverse["units_exact"]) == (8, 10, 3, 0)
    assert measures["forward-address"]["agree"] == 2
    assert calibration["counterexample_steps"] == 1 and calibration["counterexamples"][0]["before_line"] == 5
    # The in-class member is off the reverse chain, right after its first user; it explains every discordant pair.
    assert [(row["name"], row["first_user"]) for row in calibration["displaced"]] == [
        ("Get__Q215@unnamed@d_cpp@4CItrFv", "f2__Fv"),
    ]
    assert calibration["counterexamples_involving_displaced"] == {"steps": 1, "pairs": 2}
    assert [row["name"] for row in calibration["unplaced_in_dwarf_units"]] == ["__arraydtor$12", "__dt__Q215@unnamed@d_cpp@4CItrFv"]
    cross = {row["evidence"]: (row["agree"], row["pairs"]) for row in calibration["cross_checks"]}
    assert cross == {"local-static-counter": (5, 6), "literal-labels": (6, 6)}
    data = {row["evidence"]: (row["agree"], row["pairs"]) for row in calibration["data"]}
    assert data == {
        "local-static-counter": (1, 1), "static-initializer": (2, 3), "dwarf-variable-order": (1, 1), "dwarf-function-order": (1, 1),
    }
    assert calibration["copies"] == {
        "binding_13": 1, "right_after_first_user": 1, "after_first_user": 0, "before_first_user": 0, "no_user_in_unit": 0,
    }
    rules = calibration["best_rule"]
    assert len(rules) == 4 and rules[0]["measured"].startswith("8/10 DWARF pairs, 3/4 steps, 0/1 units exactly reverse")
    assert rules[1]["measured"].startswith("2/2 discordant pairs and 1/1 forward steps involve the 1 displaced functions")


def test_the_draft_is_deterministic_and_selections_keep_the_whole_calibration(draft: dict) -> None:
    assert draft["draft_sha256"] == draft_digest(draft)
    assert build_order_draft(_target(), _raw()) == draft
    one = build_order_draft(_target(), _raw(), {"unit": "N.CPP"})
    assert [row["unit"] for row in one["units"]] == ["n.cpp"] and one["selection"] == {"unit": "N.CPP"}
    assert one["calibration"] == draft["calibration"] and one["summary"]["units"] == 1
    assert one["inputs"]["evidence_sha256"] == draft["inputs"]["evidence_sha256"]
    raw = _raw()
    raw["labels"].append({"site_artifact": _id("ga"), "symbol": "q$90"})
    assert build_order_draft(_target(), raw)["inputs"]["evidence_sha256"] != draft["inputs"]["evidence_sha256"]


# -- the CLI over a synthetic stage 4 workspace -------------------------------------------------


def test_cli_draft_writes_under_build_and_selects_units(ready: tuple[Path, dict], capsys) -> None:
    root, _graph_unused = ready
    base = ["--root", str(root), "order", "draft"]
    code, report = _run(capsys, *base, "--output", "build/stage5/draft.json")
    assert code == 0 and report["mutation_performed"] is False and report["units"] == 2
    assert set(report["calibration"]) >= {"dwarf_units", "functions", "cross_checks", "data", "best_rule"}
    stored = json.loads((root / "build" / "stage5" / "draft.json").read_text(encoding="utf-8"))
    assert stored["kind"] == "socom-order-draft" and stored["draft_sha256"] == report["draft_sha256"]
    assert stored["inputs"]["order_sha256"] == report["order_sha256"]
    code, view = _run(capsys, *base, "--unit", "a.cpp")
    assert code == 0 and [row["unit"] for row in view["units"]] == ["a.cpp"]
    code, refused = _run(capsys, *base, "--output", "elsewhere.json")
    assert code == 2 and "under build/" in refused["error"]
