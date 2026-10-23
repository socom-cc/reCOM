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
