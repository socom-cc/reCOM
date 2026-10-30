"""Recon repairs of applied stage 3 groups, any-path dead reads and the scan fixes."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tools._socom import batch_apply
from tools._socom.batch_apply import _reads, claims_nothing, parse_signature
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.recon import (
    RECON_PLAN_KIND,
    REPAIR_APPLY_KIND,
    REPAIR_PLAN_KIND,
    build_recon_program,
    group_sha256,
    plan_digest,
    recon_groups,
    validate_recon_plan,
)
from tools._socom.recon_check import repair_limit
from tools._socom.recon_dead import GPR_NUMBERS, masked_read_problem, unreachable_read_problem
from tools._socom.recon_facts import argument_reads, context
from tools._socom.recon_scan import _RECORDED, live_contradictions
from tools._socom.tracker import (
    RECON_SEED_ID,
    add_recon_repair_items,
    audit_tracker,
    claim_work,
    decompose_reconstruction,
    record_stage_baseline,
    refresh_ready_and_stages,
    work_packet,
)
from tools._socom.util import SocomError, atomic_write_json

BZERO, FCLOSE, EXPF, DIVDI3 = "0x3defd8", "0x3e0550", "0x167600", "0x16bb50"
BZERO_LIVE = "void __stdcall bzero(void * __s, size_t __n)"


@pytest.fixture(scope="module")
def ctx(root: Path):
    return context(root)


@pytest.fixture()
def decomposed(stage2_tracker: dict, root: Path) -> dict:
    record_stage_baseline(
        stage2_tracker, "debug-metadata-import", "reviewer", ["close-out.md"], receipt_sha256="9" * 64,
        receipt={"counts": {}, "indexes": {}},
    )
    decompose_reconstruction(stage2_tracker, recon_groups(root))
    refresh_ready_and_stages(stage2_tracker)
    return stage2_tracker


def _group_of(tracker: dict, address: str) -> dict:
    return next(row for row in tracker["work_items"] if row["kind"] == "recon-plan-group" and address in row["batch"]["functions"])


def _accept_group(tracker: dict, address: str) -> dict:
    """Accept the group holding ``address`` (plan and apply, with a stored receipt)."""

    plan = _group_of(tracker, address)
    by_id = {row["id"]: row for row in tracker["work_items"]}

    def accept(item_id: str) -> None:
        item = by_id[item_id]
        if item["status"] == "accepted":
            return
        for dependency in item["dependencies"]:
            accept(dependency)
        _accept(item)

    accept(f"{plan['id']}-apply")
    return plan


def _accept(item: dict) -> None:
    item["status"] = "accepted"
    item["handoff"] = {"owner": "worker"}
    item["accepted"] = {"by": "reviewer"}
    if "ghidra-writer" in item["resources"]:
        item["ghidra_receipt"] = {
            "receipt_sha256": "a" * 64, "saved": True, "scope": {"functions": [], "types": [], "globals": []},
        }


# -- scan and facts fixes ------------------------------------------------------


def test_shift_immediates_read_only_rt(ctx) -> None:
    # 0x00ff00ff is _copyRefImage's inline clamp mask: it decodes as dsra32 zero,ra,3 with rs = a3.
    assert _reads(0x00FF00FF) == ({31}, set())
    assert _reads(0x00051080) == ({5}, set())  # sll v0,a1,2
    assert _reads(0x00A61004) == ({5, 6}, set())  # sllv v0,a2,a1 still reads both
    assert "a3" not in argument_reads(ctx, 0x154C48)


def test_masked_reads_are_proven_and_real_reads_are_not(ctx) -> None:
    reads = argument_reads(ctx, 0x16C1E8)  # __moddi3
    for register in ("a2", "a3", "t3"):
        for site in reads[register]:
            assert masked_read_problem(ctx, 0x16C1E8, GPR_NUMBERS[register], site) is None, (register, hex(site))
    assert masked_read_problem(ctx, 0x16BB50, 6, 0x16BB7C) is None  # __divdi3 a2
    assert masked_read_problem(ctx, 0x3E38B0, 5, 0x3E3908) is None  # _ulp a1, through two paths
    assert "observes" in masked_read_problem(ctx, 0x3E38B0, 4, 0x3E38B0)  # _ulp's x is used
    assert "observes" in masked_read_problem(ctx, 0x40A81C, 7, 0x40A840)  # SHA reads a3 for real
    assert "copy" in masked_read_problem(ctx, 0x16BB50, 5, 0x16BBBC)  # __divdi3's b is used


def test_unreachable_reads_need_the_declared_edge(ctx) -> None:
    for site in argument_reads(ctx, 0x167600)["a2"]:
        assert unreachable_read_problem(ctx, 0x167600, 6, site, 0x167724, "taken") is None
        assert "still reaches" in unreachable_read_problem(ctx, 0x167600, 6, site, 0x167724, "not-taken")
    assert "not a conditional branch" in unreachable_read_problem(ctx, 0x167600, 6, 0x16779C, 0x167600, "taken")


def test_recorded_wording_needs_a_contradiction() -> None:
    real = [
        "contradiction: the live signature void __stdcall __assert(char * __assertion, ...) is glibc's",
        "/stdio.h/FILE in the live signature is a different 160-byte type",
        "the live prototype's size_t has the wrong width",
        "the live signature int vfprintf(FILE * __s) names /stdio.h/FILE (160 bytes), not newlib's /project/__sFILE (88 bytes)",
        "the live signature (3 parameters, uchar * return) disagrees with the four argument reads",
    ]
    provenance = [
        "the live signature int open(char * __file, int __oflag, ...) comes from Ghidra's C library type archive and newlib declares open(const char *, int, ...)",
        "the live prototype int kill(__pid_t, int) has no evidence in the workspace (no DWARF record, no mangled name)",
    ]
    assert all(_RECORDED.search(text) for text in real)
    assert not any(_RECORDED.search(text) for text in provenance)


def test_default_signatures_claim_nothing() -> None:
    assert claims_nothing(parse_signature("undefined FUN_0020e7a0(void)"))
    assert claims_nothing(parse_signature("undefined __stdcall CGame::StartPlay(void)"))
    assert not claims_nothing(parse_signature("undefined __stdcall f(int a)"))
    assert not claims_nothing(parse_signature("void __stdcall f(void)"))


def test_scan_drops_the_triage_false_positives(root: Path, decomposed: dict) -> None:
    signatures = {
        0x154C48: "void __stdcall _copyRefImage(uint16 * dst, uint16 * src)",  # phantom a3 (shift rs)
        0x16BB50: "longlong __stdcall __divdi3(longlong a, longlong b)",  # masked merges
        0x16C1E8: "longlong __stdcall __moddi3(longlong a, longlong b)",
        0x16CDF8: "ulonglong __stdcall __umoddi3(ulonglong a, ulonglong b)",
        0x3E38B0: "double __stdcall _ulp(double x)",
        0x20E7A0: "undefined __stdcall CGame::StartPlay(void)",  # repair placeholder claims nothing
        0x402F50: "int __stdcall TRC_PowerOffHandler__FPv(int sema_id)",  # thunk of iSignalSema
        0x40A81C: "uchar * __stdcall SHA(uchar * d, size_t n, uchar * md)",  # real: a3 undeclared
    }
    result = live_contradictions(root, decomposed, signatures=signatures, type_paths={})
    listed = {row["address"] for row in result["functions"]}
    assert "0x40a81c" in listed
    assert not listed & {"0x154c48", "0x16bb50", "0x16c1e8", "0x16cdf8", "0x3e38b0", "0x20e7a0", "0x402f50"}
    assert result["explained_read_count"] >= 11 and result["thunk_count"] == 1
    # __ieee754_expf's uninitialised k stays listed until an accepted row declares it.
    expf = {0x167600: "float __stdcall __ieee754_expf(float x)"}
    assert [row["address"] for row in live_contradictions(root, decomposed, signatures=expf, type_paths={})["functions"]] == [EXPF]


# -- dead_reads rows ------------------------------------------------------------


def _group_plan(tracker: dict, address: str) -> dict:
    item = _group_of(tracker, address)
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


def test_dead_reads_rows_are_checked_and_noted(tmp_path: Path, root: Path, decomposed: dict, ctx) -> None:
    plan = _group_plan(decomposed, EXPF)
    entry = next(row for row in plan["functions"] if row["address"] == EXPF)
    entry.pop("unresolved")
    entry["prototype"] = {
        "return_type": "float", "parameters": [{"name": "x", "type": "float"}], "evidence": ["f12 read at entry"],
        "dead_reads": [
            {"register": "a2", "site": f"0x{site:x}", "kind": "unreachable", "branch": "0x167724", "direction": "taken",
             "evidence": ["bc1fl is taken only if 1e30+x <= 1.0"]}
            for site in argument_reads(ctx, 0x167600)["a2"]
        ],
    }
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "plan.json"
    atomic_write_json(path, plan)
    row = next(row for row in build_recon_program(root, decomposed, path)["functions"] if row["address"] == EXPF)
    assert sum("is dead (the taken edge of 0x167724 cannot happen)" in note for note in row["notes"]) == 4
    defects = [
        ({"direction": "not-taken"}, "still reaches"),
        ({"site": "0x167600"}, "does not list a2"),
        ({"kind": "masked"}, "not proven masked"),
        ({"kind": "guess"}, "kind is one of"),
        ({"evidence": []}, "needs evidence"),
        ({"register": "f12"}, "argument GPRs"),
    ]
    for change, message in defects:
        bad = copy.deepcopy(plan)
        next(r for r in bad["functions"] if r["address"] == EXPF)["prototype"]["dead_reads"][0].update(change)
        assert any(message in problem for problem in validate_recon_plan(root, decomposed, bad)), message


# -- recon repairs ----------------------------------------------------------------


def test_add_recon_repair_needs_applied_accepted_groups(decomposed: dict) -> None:
    with pytest.raises(SocomError, match="applied and accepted groups only"):
        add_recon_repair_items(decomposed, [BZERO])
    group = _accept_group(decomposed, BZERO)
    with pytest.raises(SocomError, match="not a function of any reconstruction group"):
        add_recon_repair_items(decomposed, [BZERO, "0x3defd9"])
    ids = add_recon_repair_items(decomposed, [BZERO])
    assert ids == ["socom:work:recon-repair-001", "socom:work:recon-repair-001-apply"]
    refresh_ready_and_stages(decomposed)
    assert audit_tracker(decomposed, strict=True) == []
    by_id = {row["id"]: row for row in decomposed["work_items"]}
    plan, apply = by_id[ids[0]], by_id[ids[1]]
    assert plan["kind"] == REPAIR_PLAN_KIND and plan["status"] == "ready" and plan["resources"] == ["build/recon-plans"]
    assert plan["dependencies"] == [f"{group['id']}-apply"] and plan["batch"]["groups"] == {BZERO: group["id"]}
    assert apply["kind"] == REPAIR_APPLY_KIND and apply["dependencies"] == [ids[0]] and apply["status"] == "blocked"
    assert "ghidra-writer" in apply["resources"] and "ghidra-writer" not in plan["resources"]
    assert set(ids) <= set(by_id[RECON_SEED_ID]["dependencies"])
    with pytest.raises(SocomError, match="unfinished repair"):
        add_recon_repair_items(decomposed, [BZERO])
    claim_work(decomposed, ids[0], "planner", 30)
    packet = work_packet(decomposed, ids[0], "planner")
    assert packet["allowed_paths"] == [
        "build/recon-plans/socom-work-recon-repair-001-evidence.json", "build/recon-plans/socom-work-recon-repair-001.json",
    ]
    assert any("preflight-batch --program build/apply/socom-work-recon-repair-001-apply.json" in line for line in packet["validation"])
    # Once the first repair is accepted a second one may list the function again, after it.
    _accept(plan)
    plan["lease"] = None
    _accept(apply)
    second = add_recon_repair_items(decomposed, [BZERO])
    assert second[0] == "socom:work:recon-repair-002"
    assert by_id[ids[1]]["id"] in {row["id"]: row for row in decomposed["work_items"]}[second[0]]["dependencies"]
    refresh_ready_and_stages(decomposed)
    assert audit_tracker(decomposed, strict=True) == []
    broken = copy.deepcopy(decomposed)
    gate = next(row for row in broken["work_items"] if row["id"] == RECON_SEED_ID)
    gate["dependencies"].remove(second[1])
    assert any("gate does not depend" in text for text in audit_tracker(broken))
    broken = copy.deepcopy(decomposed)
    next(row for row in broken["work_items"] if row["id"] == second[0])["dependencies"] = []
    assert any("applies of the groups it repairs" in text for text in audit_tracker(broken))


def _repair_plan(tracker: dict, item_id: str) -> dict:
    item = next(row for row in tracker["work_items"] if row["id"] == item_id)
    return {
        "kind": RECON_PLAN_KIND,
        "schema_version": 1,
        "work_item_id": item_id,
        "group_sha256": plan_digest(item),
        "target": {"source_sha256": REFERENCE_SHA256},
        "functions": [
            {
                "address": BZERO,
                "current_name": "bzero",
                "group": item["batch"]["groups"][BZERO],
                "repair": ["the live size_t is 8 bytes; the count is 32-bit (addiu v0,a1,-1 at 0x3defdc)"],
                "prototype": {
                    "return_type": "void",
                    "parameters": [{"name": "__s", "type": "void *"}, {"name": "__n", "type": "uint"}],
                    "evidence": ["recon void: VERDICT void"],
                    "live_signature": BZERO_LIVE,
                },
            }
        ],
        "globals": [],
    }


def test_repair_plans_validate_translate_and_refuse_defects(tmp_path: Path, root: Path, decomposed: dict) -> None:
    _accept_group(decomposed, BZERO)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [BZERO])
    plan = _repair_plan(decomposed, plan_id)
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "repair.json"
    atomic_write_json(path, plan)
    program = build_recon_program(root, decomposed, path)
    row = program["functions"][0]
    assert row["prototype"]["live_signature"] == BZERO_LIVE and "partial" not in row["prototype"]
    assert any(note.startswith("repair of socom:recon-group:") for note in row["notes"])
    assert program["receipt_scope"]["functions"] == [BZERO] and program["globals"] == []
    defects = [
        (lambda r: r.update(group="socom:recon-group:nope"), "must cite its group"),
        (lambda r: r.update(repair=[]), "needs `repair`"),
        (lambda r: r.update(prototype=None, unresolved=["x"]), "repairs nothing"),
        (lambda r: r["prototype"].pop("live_signature"), "needs prototype.live_signature"),
        (lambda r: r["prototype"].update(live_signature="void __stdcall bzero(void * __s, uint __n)"), "live signature already"),
        (lambda r: r.update(address="0x3e0550"), "is not in the repair"),
    ]
    for change, message in defects:
        bad = copy.deepcopy(plan)
        change(bad["functions"][0])
        assert any(message in problem for problem in validate_recon_plan(root, decomposed, bad)), message
    bad = copy.deepcopy(plan)
    bad["globals"] = [{"address": "0x1", "current_name": "x", "type": "int", "evidence": ["x"]}]
    assert any("globals must be empty" in problem for problem in validate_recon_plan(root, decomposed, bad))
    bad = copy.deepcopy(plan)
    bad["group_sha256"] = "0" * 64
    assert any("repair's function list" in problem for problem in validate_recon_plan(root, decomposed, bad))


WITHDRAWN_LIVE = "uchar __stdcall bzero(void * __s, uint __n)"


def _withdrawing_row(tracker: dict, item_id: str) -> dict:
    plan = _repair_plan(tracker, item_id)
    plan["functions"][0]["prototype"] = {
        "partial": True, "withdraws_return": True, "return_type": "undefined", "calling_convention": "__stdcall",
        "varargs": False,
        "parameters": [
            {"name": "__s", "type": "void *", "evidence": ["a0 read at entry"]},
            {"name": "__n", "type": "uint", "evidence": ["addiu v0,a1,-1 at 0x3defdc"]},
        ],
        "live_signature": WITHDRAWN_LIVE,
        "contradiction": ["return: the live uchar is a width the code does not prove"],
    }
    plan["functions"][0]["unresolved"] = ["return width unproven: only the callers narrow v0"]
    return plan


def test_repair_rows_may_withdraw_an_unproven_live_return(tmp_path: Path, root: Path, decomposed: dict) -> None:
    # Decision of 2026-10-24: a sub-word return that rested only on caller
    # narrowing becomes a partial row with the live parameters kept exactly.
    _accept_group(decomposed, BZERO)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [BZERO])
    plan = _withdrawing_row(decomposed, plan_id)
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "repair.json"
    atomic_write_json(path, plan)
    row = build_recon_program(root, decomposed, path)["functions"][0]
    assert row["prototype"]["withdraws_return"] is True and row["prototype"]["partial"] is True
    assert row["prototype"]["live_signature"] == WITHDRAWN_LIVE
    assert any(note.startswith("partial prototype withdrawing the unproven return") for note in row["notes"])
    assert batch_apply.expected_signature(row["prototype"], "bzero") == "undefined __stdcall bzero(void * __s, uint __n)"
    defects = [
        (lambda p: p.pop("withdraws_return"), "withdraws_return: true"),
        (lambda p: p.update(withdraws_return="yes"), "must be true or absent"),
        (lambda p: p.update(contradiction=[]), "withdraws_return needs contradiction"),
        (lambda p: p.update(live_signature="uchar __stdcall bzero(void * s, uint __n)"), "keeps the live parameters exactly"),
        (lambda p: p.update(live_signature="uchar __stdcall bzero(void * __s, int __n)"), "keeps the live parameters exactly"),
        (lambda p: p.update(live_signature="uchar __stdcall bzero(uint __n, void * __s)"), "keeps the live parameters exactly"),
        (lambda p: p.update(live_signature="uchar __stdcall bzero(void * __s, uint __n, ...)"), "keeps the live parameters exactly"),
        (lambda p: p.update(live_signature="uchar bzero(void * __s, uint __n)"), "keeps the live parameters exactly"),
        # bzero's void is proven (recon void VERDICT void), so it is not withdrawn.
        (lambda p: p.update(live_signature="void __stdcall bzero(void * __s, uint __n)"), "a proven void is not withdrawn"),
        (lambda p: p.update(live_signature="undefined4 __stdcall bzero(void * __s, uint __n)"), "claims no width to withdraw"),
        (lambda p: p.update(return_type="uchar"), "the return stays 'undefined'"),
    ]
    for change, message in defects:
        bad = copy.deepcopy(plan)
        change(bad["functions"][0]["prototype"])
        assert any(message in problem for problem in validate_recon_plan(root, decomposed, bad)), message
    # A complete row cannot carry the flag, and a group plan keeps today's rule.
    bad = copy.deepcopy(plan)
    bad["functions"][0].pop("unresolved")
    bad["functions"][0]["prototype"] = {
        "return_type": "uchar", "evidence": ["x"], "live_signature": WITHDRAWN_LIVE, "withdraws_return": True,
        "parameters": [{"name": "__s", "type": "void *"}, {"name": "__n", "type": "uint"}],
    }
    assert any("only a partial prototype carries these" in p for p in validate_recon_plan(root, decomposed, bad))
    group = _group_plan(decomposed, BZERO)
    entry = next(row for row in group["functions"] if row["address"] == BZERO)
    entry["prototype"], entry["unresolved"] = copy.deepcopy(plan["functions"][0]["prototype"]), ["x"]
    problems = validate_recon_plan(root, decomposed, group)
    assert any("only a recon repair row withdraws a live return" in p for p in problems)
    assert any("does not contradict" in p for p in problems)


def test_apply_check_reads_a_withdrawn_return_back_as_undefined() -> None:
    from tools._socom.recon_check import function_readback

    prototype = {"calling_convention": "__stdcall", "return_type": "undefined", "partial": True, "varargs": False,
                 "withdraws_return": True, "live_signature": WITHDRAWN_LIVE,
                 "parameters": [{"name": "__s", "type": "void *"}, {"name": "__n", "type": "uint"}]}
    rows = [{"address": BZERO, "name": "bzero", "prototype": prototype}]
    shown = lambda signature: [{"address": "003defd8", "details": ["Function: bzero", f"Signature: {signature}"]}]  # noqa: E731
    before = shown(WITHDRAWN_LIVE)
    assert function_readback(rows, shown("undefined __stdcall bzero(void * __s, uint __n)"), before) == []
    kept = function_readback(rows, before, before)
    assert len(kept) == 1 and "the withdrawn return reads back 'undefined'" in kept[0]
    typed = [{**rows[0], "prototype": {**prototype, "return_type": "uchar"}}]
    assert "not 'undefined'" in function_readback(typed, before, before)[0]


def test_executor_carries_the_withdrawn_return_into_the_report(tmp_path: Path, root: Path, decomposed: dict) -> None:
    _accept_group(decomposed, BZERO)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [BZERO])
    path = tmp_path / "repair.json"
    atomic_write_json(path, _withdrawing_row(decomposed, plan_id))
    program = build_recon_program(root, decomposed, path)

    class Setting(_Bridge):
        def post_json(self, endpoint, **body):
            ret, params = body["prototype"].split(" socom_prototype(", 1)
            self.signature = f"{ret} __stdcall bzero({params[:-1]})"
            return super().post_json(endpoint, **body)

    # The executor's own read-back fails while the function still shows the live return.
    with pytest.raises(batch_apply.BatchFailure, match="differ from the program"):
        batch_apply.execute_batch_program(program, _Bridge(WITHDRAWN_LIVE), type_index=lambda: [],
                                          function_names=lambda: {BZERO: "bzero"})
    bridge = Setting(WITHDRAWN_LIVE)
    result = batch_apply.execute_batch_program(
        program, bridge, type_index=lambda: [], function_names=lambda: {BZERO: "bzero"}
    )
    posts = [body["prototype"] for endpoint, body in bridge.calls if endpoint == "set_function_prototype"]
    assert posts == ["undefined socom_prototype(void * __s, uint __n)"]
    assert bridge.signature == "undefined __stdcall bzero(void * __s, uint __n)"
    assert result["functions"][0]["prototype"]["withdraws_return"] is True


class _Bridge:
    def __init__(self, signature: str) -> None:
        self.signature, self.calls = signature, []

    def request(self, endpoint, **parameters):
        self.calls.append((endpoint, parameters))
        return f"Function: bzero at 003defd8\nSignature: {self.signature}\nEntry: 003defd8"

    def post_json(self, endpoint, **body):
        self.calls.append((endpoint, body))
        return "Successfully set prototype"


def test_executor_refuses_a_repair_row_whose_live_signature_changed() -> None:
    program = {
        "kind": batch_apply.BATCH_PROGRAM_KIND, "schema_version": batch_apply.BATCH_PROGRAM_SCHEMA,
        "functions": [{
            "address": BZERO, "current_name": "bzero", "readable_name": "bzero", "rename": False, "prototype_skip": None,
            "prototype": {"calling_convention": "__stdcall", "return_type": "void", "live_signature": BZERO_LIVE,
                          "parameters": [{"name": "__s", "type": "void *"}, {"name": "__n", "type": "uint"}]},
        }],
        "globals": [],
    }
    bridge = _Bridge("void __stdcall bzero(void * __s, int __n)")
    with pytest.raises(SocomError, match="replan the row"):
        batch_apply.execute_batch_program(program, bridge, type_index=lambda: [], function_names=lambda: {BZERO: "bzero"})
    assert not any(endpoint == "set_function_prototype" for endpoint, _ in bridge.calls)
    result = batch_apply.execute_batch_program(
        program, _Bridge(BZERO_LIVE), type_index=lambda: [], function_names=lambda: {BZERO: "bzero"}, dry_run=True
    )
    assert [step["endpoint"] for step in result["steps"]] == ["set_function_prototype"]


def test_repair_limit_allows_only_the_listed_functions() -> None:
    item = {"batch": {"repair_number": 1, "functions": [BZERO, FCLOSE]}}
    program = {"globals": []}
    scope = {"functions": [BZERO, FCLOSE], "types": [], "globals": []}
    diff = {"functions": [{"address": "003defd8"}, {"address": "003e0550"}, {"address": "00140510"}]}
    summary = {"thunks": ["0x140510"], "split_targets": []}
    steps = [{"endpoint": "set_function_prototype", "body": {"function_address": value}} for value in (BZERO, FCLOSE)]
    result = {"functions": [{"address": value, "prototype": {"return_type": "void"}} for value in (BZERO, FCLOSE)]}
    name, ok, detail = repair_limit(item, program, scope, diff, summary, steps, result)
    assert name == "limit" and ok, detail
    diff["functions"].append({"address": "00150000"})
    assert repair_limit(item, program, scope, diff, summary, steps, result)[1] is False
    diff["functions"].pop()
    skipped = {"functions": [{"address": BZERO, "prototype": None}, result["functions"][1]]}
    assert "without their prototype" in repair_limit(item, program, scope, diff, summary, steps, skipped)[2]
    wide = {**scope, "globals": ["0x400000"]}
    assert "not exactly the listed functions" in repair_limit(item, program, wide, diff, summary, steps, result)[2]


# -- partial candidates -----------------------------------------------------------


def test_proven_parameters_come_from_facts_only(ctx) -> None:
    from tools._socom.recon_draft import _TypeIndex
    from tools._socom.recon_partial import proven_parameters

    types = _TypeIndex([])
    row = {"address": "0x140ee0", "elf_names": ["__nwa__FUi"], "stage2": None, "thunk_target": None}
    proven, _why = proven_parameters(ctx, row, types)
    assert proven == {"parameters": [{"name": "param_1", "type": "uint"}], "varargs": False, "source": "mangled signature __nwa__FUi"}
    assert proven_parameters(ctx, {"address": FCLOSE, "elf_names": ["fclose"]}, types)[1].startswith("no mangled signature")
    assert proven_parameters(ctx, {**row, "thunk_target": "0x1"}, types)[1].startswith("thunk")


# -- withdrawals of decisions 2026-10-29: open voids and recalled-header returns --

DELETE_CHILDREN = "0x226320"
DELETE_CHILDREN_LIVE = "void __stdcall DeleteChildren(CNode * this)"
OPEN_VERDICT = "VERDICT open: the function's address is taken or stored in a table"


def _void_withdrawal(tracker: dict, item_id: str, address: str = DELETE_CHILDREN) -> dict:
    item = next(row for row in tracker["work_items"] if row["id"] == item_id)
    return {
        "kind": RECON_PLAN_KIND, "schema_version": 1, "work_item_id": item_id, "group_sha256": plan_digest(item),
        "target": {"source_sha256": REFERENCE_SHA256},
        "functions": [{
            "address": address, "current_name": "zdb::CNode::DeleteChildren",
            "group": item["batch"]["groups"][address],
            "repair": ["the live void rests on no proof: recon void leaves it open"],
            "prototype": {
                "partial": True, "withdraws_return": True, "return_type": "undefined", "calling_convention": "__stdcall",
                "varargs": False, "parameters": [{"name": "this", "type": "CNode *", "evidence": ["a0 read at entry"]}],
                "live_signature": DELETE_CHILDREN_LIVE,
                "contradiction": [f"return: recon void {OPEN_VERDICT} (address in vtables, no slot proof)"],
            },
            "unresolved": ["return: no override or caller proves void or a width"],
        }],
        "globals": [],
    }


def test_repair_rows_may_withdraw_a_void_recon_void_leaves_open(tmp_path: Path, root: Path, decomposed: dict) -> None:
    _accept_group(decomposed, DELETE_CHILDREN)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [DELETE_CHILDREN])
    plan = _void_withdrawal(decomposed, plan_id)
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "repair.json"
    atomic_write_json(path, plan)
    row = build_recon_program(root, decomposed, path)["functions"][0]
    assert row["prototype"]["withdraws_return"] is True and row["prototype"]["live_signature"] == DELETE_CHILDREN_LIVE
    assert any(
        note.startswith("partial prototype withdrawing the unproven void return") and OPEN_VERDICT in note
        for note in row["notes"]
    )
    assert batch_apply.expected_signature(row["prototype"], "DeleteChildren") == "undefined __stdcall DeleteChildren(CNode * this)"
    defects = [
        (lambda p: p.update(contradiction=["return: the live void is unproven"]), "citing its recon void verdict"),
        (lambda p: p.update(contradiction=[f"recon void {OPEN_VERDICT}", "VERDICT void elsewhere"]), "never 'VERDICT void'"),
        (lambda p: p.update(live_signature="void __stdcall DeleteChildren(CNode * self)"), "keeps the live parameters exactly"),
    ]
    for change, message in defects:
        bad = copy.deepcopy(plan)
        change(bad["functions"][0]["prototype"])
        assert any(message in problem for problem in validate_recon_plan(root, decomposed, bad)), message


@pytest.mark.parametrize(
    ("address", "live", "message"),
    [
        ("0x46b9d0", "void __stdcall __sinit_zrdr_archive.cpp(void)", "the drafter's __sinit_ rule"),
        ("0x17cbe0", "void __stdcall LoadThreadEntry(void * param_1)", "its DWARF record declares an explicit void"),
    ],
)
def test_proven_voids_are_not_withdrawn(root: Path, decomposed: dict, address: str, live: str, message: str) -> None:
    _accept_group(decomposed, address)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [address])
    plan = _void_withdrawal(decomposed, plan_id, address)
    parsed = parse_signature(live)
    plan["functions"][0]["prototype"].update(
        live_signature=live,
        parameters=[{"name": name, "type": kind, "evidence": ["x"]} for kind, name in parsed["parameters"]],
    )
    problems = validate_recon_plan(root, decomposed, plan)
    assert any(message in problem and "a proven void is not withdrawn" in problem for problem in problems), problems


@pytest.mark.parametrize("returned", ["int", "void *", "uint"])
def test_recalled_header_returns_of_any_width_may_be_withdrawn(root: Path, decomposed: dict, returned: str) -> None:
    # Decision of 2026-10-29 (b8acf0d9, "Re-prove from asm"): an int or pointer
    # return whose only support was a recalled header is withdrawn as well.
    _accept_group(decomposed, BZERO)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [BZERO])
    plan = _withdrawing_row(decomposed, plan_id)
    plan["functions"][0]["prototype"]["live_signature"] = f"{returned} __stdcall bzero(void * __s, uint __n)"
    plan["functions"][0]["prototype"]["contradiction"] = [f"return: the live {returned} rests only on a recalled header"]
    assert validate_recon_plan(root, decomposed, plan) == []


def test_a_return_its_own_dwarf_record_declares_is_not_withdrawn(root: Path, decomposed: dict) -> None:
    address = "0x17cbe0"  # LoadThreadEntry: FT_void in DWARF, so a typed live return is DWARF's to settle
    _accept_group(decomposed, address)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [address])
    plan = _void_withdrawal(decomposed, plan_id, address)
    plan["functions"][0]["prototype"].update(
        live_signature="int __stdcall LoadThreadEntry(void * param_1)",
        parameters=[{"name": "param_1", "type": "void *", "evidence": ["x"]}],
    )
    assert any("DWARF record declares its return (void)" in p for p in validate_recon_plan(root, decomposed, plan))


def test_apply_check_reads_a_withdrawn_void_back_as_undefined() -> None:
    from tools._socom.recon_check import function_readback

    prototype = {"calling_convention": "__stdcall", "return_type": "undefined", "partial": True, "varargs": False,
                 "withdraws_return": True, "live_signature": DELETE_CHILDREN_LIVE,
                 "parameters": [{"name": "this", "type": "CNode *"}]}
    rows = [{"address": DELETE_CHILDREN, "name": "DeleteChildren", "prototype": prototype}]
    shown = lambda signature: [{"address": "00226320", "details": [f"Signature: {signature}"]}]  # noqa: E731
    before = shown(DELETE_CHILDREN_LIVE)
    assert function_readback(rows, shown("undefined __stdcall DeleteChildren(CNode * this)"), before) == []
    assert "reads back 'undefined'" in function_readback(rows, before, before)[0]
    renamed = [{**rows[0], "prototype": {**prototype, "parameters": [{"name": "self", "type": "CNode *"}]}}]
    after = shown("undefined __stdcall DeleteChildren(CNode * self)")
    assert "parameters differ from the live signature" in function_readback(renamed, after, before)[0]


# -- keep rows: a repair leaves a listed function as it is (2026-10-29) ----------

CHECK_EXTENTS = "0x2392d0"


def _keep_plan(tracker: dict, item_id: str, address: str) -> dict:
    item = next(row for row in tracker["work_items"] if row["id"] == item_id)
    return {
        "kind": RECON_PLAN_KIND, "schema_version": 1, "work_item_id": item_id, "group_sha256": plan_digest(item),
        "target": {"source_sha256": REFERENCE_SHA256},
        "functions": [{
            "address": address, "current_name": "Particle::Source::CheckExtents", "group": item["batch"]["groups"][address],
            "keep": True, "keep_reason": ["CPnt4D (16 bytes) by value: no prototype gives it its storage"],
        }],
        "globals": [],
    }


def test_keep_rows_leave_a_listed_function_as_it_is(tmp_path: Path, root: Path, decomposed: dict) -> None:
    _accept_group(decomposed, CHECK_EXTENTS)
    plan_id, _apply_id = add_recon_repair_items(decomposed, [CHECK_EXTENTS])
    plan = _keep_plan(decomposed, plan_id, CHECK_EXTENTS)
    assert validate_recon_plan(root, decomposed, plan) == []
    path = tmp_path / "keep.json"
    atomic_write_json(path, plan)
    program = build_recon_program(root, decomposed, path)
    row = program["functions"][0]
    assert row["keep"] is True and row["prototype"] is None and row["rename"] is False
    assert row["prototype_skip"].startswith("keep: CPnt4D") and any(n.startswith("kept as it is") for n in row["notes"])

    class Keeping(_Bridge):
        def request(self, endpoint, **parameters):
            self.calls.append((endpoint, parameters))
            return f"Function: Particle::Source::CheckExtents at 002392d0\nSignature: {self.signature}"

    bridge = Keeping("undefined __stdcall CheckExtents(void)")
    result = batch_apply.execute_batch_program(
        program, bridge, type_index=lambda: [], function_names=lambda: {CHECK_EXTENTS: "Particle::Source::CheckExtents"}
    )
    assert not any(endpoint in ("set_function_prototype", "rename_function_by_address") for endpoint, _ in bridge.calls)
    assert result["functions"][0]["prototype"] is None
    defects = [
        (lambda r: r.update(keep="yes"), "keep must be true or absent"),
        (lambda r: r.update(keep_reason=[]), "keep row needs keep_reason"),
        (lambda r: r.update(prototype={"return_type": "void", "parameters": [], "evidence": ["x"]}), "drop prototype"),
        (lambda r: r.update(unresolved=["x"]), "drop unresolved"),
        (lambda r: r.update(group="socom:recon-group:nope"), "must cite its group"),
    ]
    for change, message in defects:
        bad = copy.deepcopy(plan)
        change(bad["functions"][0])
        assert any(message in problem for problem in validate_recon_plan(root, decomposed, bad)), message
    bad = copy.deepcopy(plan)
    bad["functions"][0].pop("keep")
    assert any("only a keep row carries keep_reason" in p for p in validate_recon_plan(root, decomposed, bad))
    group = _group_plan(decomposed, CHECK_EXTENTS)
    entry = next(r for r in group["functions"] if r["address"] == CHECK_EXTENTS)
    entry.update(keep=True, keep_reason=["x"])
    assert any("only a recon repair row keeps" in p for p in validate_recon_plan(root, decomposed, group))


def test_limit_and_readback_treat_a_keep_row_as_listed_and_unchanged() -> None:
    from tools._socom.recon_check import function_readback

    item = {"batch": {"repair_number": 10, "functions": [BZERO, CHECK_EXTENTS]}}
    program = {"globals": [], "functions": [{"address": BZERO}, {"address": CHECK_EXTENTS, "keep": True}]}
    scope = {"functions": [BZERO, CHECK_EXTENTS], "types": [], "globals": []}
    summary = {"thunks": [], "split_targets": []}
    steps = [{"endpoint": "set_function_prototype", "body": {"function_address": BZERO}}]
    result = {"functions": [{"address": BZERO, "prototype": {"return_type": "void"}}, {"address": CHECK_EXTENTS, "prototype": None}]}
    one = {"functions": [{"address": "003defd8"}]}
    name, ok, detail = repair_limit(item, program, scope, one, summary, steps, result)
    assert name == "limit" and ok and "(1 of them kept as they are by keep rows)" in detail, detail
    changed = {"functions": [{"address": "003defd8"}, {"address": "002392d0"}]}
    assert "a keep row leaves as they are changed" in repair_limit(item, program, scope, changed, summary, steps, result)[2]
    unkept = {**program, "functions": [{"address": BZERO}, {"address": CHECK_EXTENTS}]}
    assert "without their prototype" in repair_limit(item, unkept, scope, one, summary, steps, result)[2]
    rows = [{"address": CHECK_EXTENTS, "name": "CheckExtents", "prototype": None}]
    same = [{"address": "002392d0", "details": ["Signature: undefined __stdcall CheckExtents(void)"]}]
    other = [{"address": "002392d0", "details": ["Signature: void __stdcall CheckExtents(void)"]}]
    assert function_readback(rows, same, same) == [] and "changed" in function_readback(rows, other, same)[0]


def test_validate_refuses_by_value_aggregates_over_one_gpr_slot(root: Path, decomposed: dict) -> None:
    plan = _group_plan(decomposed, CHECK_EXTENTS)
    entry = next(row for row in plan["functions"] if row["address"] == CHECK_EXTENTS)
    entry.pop("unresolved")
    entry["prototype"] = {
        "return_type": "void", "evidence": ["x"],
        "parameters": [{"name": "this", "type": "Source *"}, {"name": "extent", "type": "CPnt4D"}, {"name": "r", "type": "float"}],
    }
    problems = validate_recon_plan(root, decomposed, plan)
    assert any("parameter extent: CPnt4D is passed by value" in p for p in problems), problems
    entry["prototype"]["parameters"][1]["type"] = "CPnt4D *"
    assert not any("passed by value" in p for p in validate_recon_plan(root, decomposed, plan))
