"""Partial prototypes (decision of 2026-10-22) and the live contradictions scan."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tools._socom import batch_apply
from tools._socom.batch_apply import expected_signature, parse_signature, prototype_text
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.recon import (
    RECON_PLAN_KIND,
    build_recon_program,
    group_sha256,
    noreturn_problem,
    recon_groups,
    validate_recon_plan,
    _functions,
)
from tools._socom.recon_draft import check_drafted_rows
from tools._socom.recon_scan import contradictions_text, live_contradictions
from tools._socom.tracker import decompose_reconstruction, record_stage_baseline, refresh_ready_and_stages
from tools._socom.util import SocomError, atomic_write_json
from tools._socom.elf import Elf32File

ASSERT_LIVE = "void __stdcall __assert(char * __assertion, char * __file, int __line)"


@pytest.fixture()
def decomposed(stage2_tracker: dict, root: Path) -> dict:
    record_stage_baseline(
        stage2_tracker, "debug-metadata-import", "reviewer", ["close-out.md"], receipt_sha256="9" * 64,
        receipt={"counts": {}, "indexes": {}},
    )
    decompose_reconstruction(stage2_tracker, recon_groups(root))
    refresh_ready_and_stages(stage2_tracker)
    return stage2_tracker


def _plan_with(tracker: dict, address: str) -> dict:
    item = next(row for row in tracker["work_items"] if row["kind"] == "recon-plan-group" and address in row["batch"]["functions"])
    return {
        "kind": RECON_PLAN_KIND,
        "schema_version": 1,
        "work_item_id": item["id"],
        "group_sha256": group_sha256(item["batch"]),
        "target": {"source_sha256": REFERENCE_SHA256},
        "functions": [
            {"address": value, "current_name": f"FUN_{value[2:]}", "prototype": None, "unresolved": ["test"]}
            for value in item["batch"]["functions"]
        ],
        "globals": [],
    }


def _assert_row(**changes) -> tuple[dict, list[str]]:
    prototype = {
        "partial": True,
        "return_type": "undefined",
        "calling_convention": "__stdcall",
        "varargs": False,
        "noreturn": True,
        "parameters": [
            {"name": "file", "type": "char *", "evidence": ["move a3,a0 at 0x3def4c: the second %s"]},
            {"name": "line", "type": "int", "evidence": ["move t0,a1 at 0x3def44: the %d"]},
            {"name": "failedexpr", "type": "char *", "evidence": ["a2 is the first %s"]},
        ],
        "live_signature": ASSERT_LIVE,
        "contradiction": ["glibc order: a1 is the line, a2 the expression"],
        "noreturn_evidence": ["no jr; tail-jumps to abort, which loops"],
    }
    prototype.update(changes)
    return prototype, ["return: never returns, so no value is observable"]


def test_parse_signature_reads_ghidra_forms() -> None:
    assert parse_signature("noreturn void abort(void)") == {
        "noreturn": True, "return_type": "void", "calling_convention": None, "name": "abort",
        "parameters": [], "varargs": False, "default": False,
    }
    assert parse_signature("undefined FUN_00140000(void)")["default"] is True
    vararg = parse_signature("int __stdcall printf(char * __format, ...)")
    assert vararg["varargs"] and vararg["parameters"] == [("char *", "__format")]
    assert parse_signature("char * * __stdcall CFoo::operator()(char * * x, int y)")["parameters"] == [("char * *", "x"), ("int", "y")]
    assert parse_signature("void __stdcall f(Map<int, int> m)") is None


def test_prototype_text_and_signature_keep_complete_rows_and_spell_partial_ones() -> None:
    complete = {"calling_convention": "__stdcall", "return_type": "void", "parameters": []}
    assert prototype_text(complete) == "void socom_prototype(void)"
    assert expected_signature(complete, "f") == "void __stdcall f(void)"
    partial = {"calling_convention": "__stdcall", "return_type": "undefined", "varargs": True, "live_noreturn": True,
               "parameters": [{"name": "fmt", "type": "char *"}]}
    assert prototype_text(partial) == "undefined socom_prototype(char * fmt, ...)"
    assert expected_signature(partial, "g") == "noreturn undefined __stdcall g(char * fmt, ...)"


def test_noreturn_is_proven_from_the_elf(root: Path) -> None:
    elf = Elf32File(root / "support" / "socom.elf")
    sizes = {row["start"]: row["size"] for row in _functions(elf)}
    assert noreturn_problem(elf, sizes, 0x3def00) is None  # abort: raise, _exit, b back
    assert noreturn_problem(elf, sizes, 0x3def38) is None  # __assert: j abort
    assert "jr ra" in noreturn_problem(elf, sizes, 0x3e8c90)  # vfprintf returns


def test_partial_rows_validate_translate_and_refuse_defects(tmp_path: Path, root: Path, decomposed: dict) -> None:
    plan = _plan_with(decomposed, "0x3def38")
    entry = next(row for row in plan["functions"] if row["address"] == "0x3def38")
    entry["prototype"], entry["unresolved"] = _assert_row()
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "plan.json"
    atomic_write_json(path, plan)
    program = build_recon_program(root, decomposed, path)
    row = next(row for row in program["functions"] if row["address"] == "0x3def38")
    assert row["prototype"]["partial"] and row["prototype"]["live_signature"] == ASSERT_LIVE
    assert row["prototype"]["noreturn_proven"] and row["prototype_skip"] is None
    assert row["return_unresolved"].startswith("return: never returns")
    assert any("not applied" in note for note in row["notes"])
    assert program["summary"]["partial_prototype_count"] == 1
    assert prototype_text(row["prototype"]) == "undefined socom_prototype(char * file, int line, char * failedexpr)"

    defects = [
        ({"return_type": "int"}, "the return stays 'undefined'"),
        ({"live_signature": "void __stdcall __assert(char * file, int line, char * x)"}, "does not contradict"),
        ({"contradiction": []}, "needs the contradiction"),
        ({"varargs": None}, "varargs true or false"),
        ({"noreturn_evidence": []}, "needs noreturn_evidence"),
    ]
    for change, message in defects:
        bad = copy.deepcopy(plan)
        row = next(row for row in bad["functions"] if row["address"] == "0x3def38")
        row["prototype"].update(change)
        assert any(message in problem for problem in validate_recon_plan(root, decomposed, bad)), message
    bad = copy.deepcopy(plan)
    row = next(row for row in bad["functions"] if row["address"] == "0x3def38")
    row["prototype"]["parameters"][0]["evidence"] = []
    row["unresolved"] = []
    problems = validate_recon_plan(root, decomposed, bad)
    assert any("'file' needs evidence" in problem for problem in problems)
    assert any("reasons its return stays unresolved" in problem for problem in problems)
    # Ghidra's default (with or without a convention) claims nothing: a partial row
    # may replace it without a contradiction, but only with every parameter typed
    # (decision of 2026-10-22, "Yes, extend it").
    for default in ("undefined __assert(void)", "undefined __stdcall __assert(void)"):
        replaced = copy.deepcopy(plan)
        row = next(row for row in replaced["functions"] if row["address"] == "0x3def38")
        row["prototype"]["live_signature"] = default
        del row["prototype"]["contradiction"]
        assert validate_recon_plan(root, decomposed, replaced) == []
        path = tmp_path / "default.json"
        atomic_write_json(path, replaced)
        translated = next(r for r in build_recon_program(root, decomposed, path)["functions"] if r["address"] == "0x3def38")
        assert translated["prototype"]["live_signature"] == default
        row["prototype"]["parameters"][2]["type"] = "undefined4"
        assert any("needs every parameter typed" in p for p in validate_recon_plan(root, decomposed, replaced))


def test_partial_only_fields_and_unknown_types_stay_out_of_complete_rows(root: Path, decomposed: dict) -> None:
    plan = _plan_with(decomposed, "0x3def38")
    entry = next(row for row in plan["functions"] if row["address"] == "0x3def38")
    entry["unresolved"] = []
    entry["prototype"] = {
        "return_type": "undefined",
        "parameters": [{"name": "a", "type": "char *"}, {"name": "b", "type": "undefined4"}, {"name": "c", "type": "char *"}],
        "evidence": ["x"],
        "noreturn": False,
    }
    problems = validate_recon_plan(root, decomposed, plan)
    assert any("only a partial prototype carries these" in problem for problem in problems)
    assert any("'undefined4' is Ghidra's unknown type" in problem for problem in problems)


def test_varargs_rows_need_a_fixed_parameter_and_cover_the_variadic_registers(root: Path, decomposed: dict) -> None:
    # open (0x15bbe0) spills a2/a3 for its variadic mode argument.
    plan = _plan_with(decomposed, "0x15bbe0")
    entry = next(row for row in plan["functions"] if row["address"] == "0x15bbe0")
    entry["prototype"] = {
        "partial": True, "return_type": "undefined", "calling_convention": "__stdcall", "varargs": True,
        "parameters": [{"name": "path", "type": "char *", "evidence": ["x"]}, {"name": "flags", "type": "int", "evidence": ["x"]}],
        "live_signature": "int __stdcall open(char * __file, int __oflag)",
        "contradiction": ["the live signature lacks '...'"], "varargs_evidence": ["a2 spilled for the mode"],
    }
    entry["unresolved"] = ["return width unproven"]
    problems = validate_recon_plan(root, decomposed, plan)
    assert not any("open" in problem or "0x15bbe0" in problem for problem in problems), problems
    entry["prototype"]["parameters"] = []
    problems = validate_recon_plan(root, decomposed, plan)
    assert any("varargs needs a fixed parameter" in problem for problem in problems)


def test_a_complete_row_may_be_varargs_when_its_return_is_decided(tmp_path: Path, root: Path, decomposed: dict) -> None:
    # Decision of 2026-10-22 (fprintf: no caller reads v0): the return is decided,
    # so the row is complete and carries the varargs flag.
    plan = _plan_with(decomposed, "0x15bbe0")
    entry = next(row for row in plan["functions"] if row["address"] == "0x15bbe0")
    entry.pop("unresolved")
    entry["prototype"] = {
        "return_type": "int", "evidence": ["x"], "varargs": True, "varargs_evidence": ["a2 spilled for the mode"],
        "parameters": [{"name": "path", "type": "char *"}, {"name": "flags", "type": "int"}],
    }
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "plan.json"
    atomic_write_json(path, plan)
    row = next(row for row in build_recon_program(root, decomposed, path)["functions"] if row["address"] == "0x15bbe0")
    assert row["prototype"]["varargs"] is True and "partial" not in row["prototype"]
    assert prototype_text(row["prototype"]) == "int socom_prototype(char * path, int flags, ...)"
    assert expected_signature(row["prototype"], "open") == "int __stdcall open(char * path, int flags, ...)"
    entry["prototype"].pop("varargs_evidence")
    assert any("varargs needs varargs_evidence" in p for p in validate_recon_plan(root, decomposed, plan))
    entry["prototype"]["varargs"] = "yes"
    assert any("varargs must be true or false" in p for p in validate_recon_plan(root, decomposed, plan))
    # A U-vararg draft accepts the complete varargs row; a P- draft is still binding.
    draft = {"functions": [{"address": "0x15bbe0", "current_name": "open", "draft_rule": "U-vararg", "prototype": None, "unresolved": ["x"]}]}
    entry["prototype"]["varargs"] = True
    assert check_drafted_rows(draft, plan) == []
    entry["prototype"]["varargs"] = False
    assert any("disagrees with its U-vararg draft" in p for p in check_drafted_rows(draft, plan))


class _Bridge:
    def __init__(self, signature: str) -> None:
        self.signature = signature
        self.calls: list[tuple[str, dict]] = []

    def request(self, endpoint, **parameters):
        self.calls.append((endpoint, parameters))
        assert endpoint == "get_function_by_address"
        return f"Function: __assert at 003def38\nSignature: {self.signature}\nEntry: 003def38"

    def post_json(self, endpoint, **body):
        self.calls.append((endpoint, body))
        assert endpoint == "set_function_prototype"
        ret, params = body["prototype"].split(" socom_prototype(", 1)
        prefix = "noreturn " if self.signature.startswith("noreturn ") else ""
        self.signature = f"{prefix}{ret} __stdcall __assert({params[:-1]})"
        return "Successfully set prototype"


def _program(signature: str) -> dict:
    prototype, _unresolved = _assert_row(live_signature=signature)
    return {
        "kind": batch_apply.BATCH_PROGRAM_KIND,
        "schema_version": batch_apply.BATCH_PROGRAM_SCHEMA,
        "functions": [
            {
                "address": "0x3def38", "current_name": "__assert", "readable_name": "__assert", "rename": False,
                "prototype": {
                    "calling_convention": "__stdcall",
                    "parameters": [{"name": p["name"], "type": p["type"]} for p in prototype["parameters"]],
                    "return_type": "undefined", "sources": ["recon-plan"], "partial": True, "varargs": False,
                    "live_signature": signature, "noreturn_proven": True,
                },
                "prototype_skip": None, "notes": [],
            }
        ],
        "globals": [],
    }


@pytest.mark.parametrize("signature", [ASSERT_LIVE, "noreturn " + ASSERT_LIVE])
def test_executor_applies_partial_rows_and_reads_back_the_live_noreturn_flag(signature: str) -> None:
    bridge = _Bridge(signature)
    result = batch_apply.execute_batch_program(
        _program(signature), bridge, type_index=lambda: [], function_names=lambda: {"0x3def38": "__assert"}
    )
    assert result["ok"] and not result["skipped"]
    posts = [body for endpoint, body in bridge.calls if endpoint == "set_function_prototype"]
    assert [body["prototype"] for body in posts] == ["undefined socom_prototype(char * file, int line, char * failedexpr)"]
    assert bridge.signature.endswith("undefined __stdcall __assert(char * file, int line, char * failedexpr)")
    assert bool(result["functions"][0]["prototype"].get("live_noreturn")) == signature.startswith("noreturn ")
    assert not any(endpoint == "set_function_no_return" for endpoint, _ in bridge.calls)


def test_executor_refuses_a_partial_row_whose_live_signature_changed() -> None:
    bridge = _Bridge("void __stdcall __assert(char * a, int b, char * c)")
    with pytest.raises(SocomError, match="replan the row"):
        batch_apply.execute_batch_program(
            _program(ASSERT_LIVE), bridge, type_index=lambda: [], function_names=lambda: {"0x3def38": "__assert"}
        )
    assert not any(endpoint == "set_function_prototype" for endpoint, _ in bridge.calls)


def test_draft_check_allows_partial_rows_only_where_the_draft_is_unresolved() -> None:
    prototype, unresolved = _assert_row()
    plan = {"functions": [{"address": "0x1", "current_name": "f", "prototype": prototype, "unresolved": unresolved}]}
    unresolved_draft = {"functions": [{"address": "0x1", "current_name": "f", "draft_rule": "U-vararg", "prototype": None, "unresolved": ["x"]}]}
    assert check_drafted_rows(unresolved_draft, plan) == []
    decided = {"functions": [{"address": "0x1", "current_name": "f", "draft_rule": "P-void",
                              "prototype": {"return_type": "void", "parameters": []}}]}
    assert any("use the drafted row" in problem for problem in check_drafted_rows(decided, plan))


def test_contradictions_scan_reports_register_and_mangled_shape_conflicts(root: Path, decomposed: dict) -> None:
    signatures = {
        0x3def38: "void __stdcall __assert(char * __assertion)",  # reads a1 (a2 passes through untouched)
        0x402f50: "int __stdcall TRC_PowerOffHandler(int sema_id)",  # mangled FPv
        0x3def00: "noreturn void abort(void)",  # agrees with the code
        0x154c48: "undefined FUN_00154c48(void)",  # Ghidra's default claims nothing
    }
    result = live_contradictions(root, decomposed, signatures=signatures, type_paths={})
    rows = {row["address"]: row for row in result["functions"]}
    # 0x402f50 is a thunk (j iSignalSema): it shows its target's signature, so it
    # is listed apart, not checked against its own mangled name.
    assert set(rows) == {"0x3def38"} and result["with_live_claims"] == 2
    assert [text.split(" is read")[0] for text in rows["0x3def38"]["contradictions"] if text.startswith("registers")] == ["registers: a1"]
    assert result["thunk_count"] == 1 and [row["address"] for row in result["thunks"]] == ["0x402f50"]
    assert any("pointer depth 0 vs 1" in text for text in result["thunks"][0]["would_flag"])
    assert not rows["0x3def38"]["applied"] and result["applied_count"] == 0
    assert contradictions_text(result).startswith("# recon contradictions --groups all: 1 of 2")
    assert live_contradictions(root, decomposed, groups="applied", signatures=signatures, type_paths={})["scanned"] == 0


def test_apply_check_explains_a_partial_row_and_its_builtin_unknown(root: Path) -> None:
    from tools._socom.recon_check import explain_recon_diff

    prototype = {"calling_convention": "__stdcall", "return_type": "undefined", "partial": True, "varargs": False,
                 "parameters": [{"name": "fp", "type": "undefined8"}], "live_signature": "int __stdcall f(FILE * s)"}
    signature = "Signature: " + expected_signature(prototype, "f")
    row = lambda details: {"name": "f", "thunk": False, "details": ["Function: f at 003e8c90", *details, "Entry: 003e8c90"]}  # noqa: E731
    diff = {
        "functions": [{"address": "003e8c90", "before": row(["Signature: int __stdcall f(FILE * s)"]), "after": row([signature])}],
        "data": {"added": [], "removed": []},
        "references": {"added": [], "removed": []},
        "types": {"added": ["/undefined8|8"], "removed": []},
        "blocks_equal": True,
        "bookmarks_equal": True,
    }
    before = {"functions": [{"address": "003e8c90", **row(["Signature: int __stdcall f(FILE * s)"])}]}
    steps = [{"endpoint": "set_function_prototype", "body": {"function_address": "0x3e8c90"}}]
    result = {"functions": [{"address": "0x3e8c90", "name": "f", "prototype": prototype}], "globals": []}
    problems, summary = explain_recon_diff(root, diff, before, steps, result)
    assert problems == [] and summary["builtins_added"] == ["undefined8"]
    complete = {**result, "functions": [{**result["functions"][0], "prototype": {**prototype, "partial": False}}]}
    problems, _summary = explain_recon_diff(root, diff, before, steps, complete)
    assert any("neither a pointer nor an array" in problem for problem in problems)
