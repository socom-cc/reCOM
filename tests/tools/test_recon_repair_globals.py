"""Recon repairs of globals: ELF facts, tracker items, plan rows, program, executor, limit and read-back."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tools._socom import batch_apply
from tools._socom.constants import REFERENCE_SHA256
from tools._socom.recon import RECON_PLAN_KIND, build_recon_program, plan_digest, recon_groups, repair_sha256, validate_recon_plan
from tools._socom.recon_check import explain_recon_diff, global_readback, repair_limit
from tools._socom.recon_globals import (
    global_facts,
    global_symbol_facts,
    qualifier_globals,
    readable_label,
    repair_global_problems,
    spelled_size,
)
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

DMA_CHAIN, DMA_QWC, OPACITY, FOG_ENABLE, CAMERA, STACK_VID = (
    "0x4765f4", "0x4765f8", "0x4765fc", "0x4753f8", "0x4765d8", "0x511790",
)
APPLY_SCALE_COLOR = "0x4765ec"


@pytest.fixture(scope="module")
def decomposed_base(root: Path, census: dict) -> dict:
    from tools._socom.tracker import initialize_tracker

    tracker = initialize_tracker(root, census)
    for number, item in enumerate(row for row in tracker["work_items"] if row["stage"] == "debug-metadata-import"):
        item["status"] = "accepted"
        item["handoff"] = {"owner": "worker"}
        item["accepted"] = {"by": "reviewer"}
        if "ghidra-writer" in item["resources"]:
            item["ghidra_receipt"] = {
                "receipt_sha256": f"{number:064x}", "saved": True,
                "scope": {"functions": [f"0x{0x140000 + 16 * number:x}"], "types": [], "globals": []},
            }
    refresh_ready_and_stages(tracker)
    record_stage_baseline(
        tracker, "debug-metadata-import", "reviewer", ["close-out.md"], receipt_sha256="9" * 64,
        receipt={"counts": {}, "indexes": {}},
    )
    decompose_reconstruction(tracker, recon_groups(root))
    refresh_ready_and_stages(tracker)
    return tracker


@pytest.fixture()
def decomposed(decomposed_base: dict) -> dict:
    return copy.deepcopy(decomposed_base)


@pytest.fixture(scope="module")
def identities(root: Path) -> dict:
    return global_symbol_facts(root, [DMA_CHAIN, DMA_QWC, OPACITY, FOG_ENABLE, CAMERA, STACK_VID, APPLY_SCALE_COLOR])


def _accept(item: dict, globals_: list[str] | None = None) -> None:
    item["status"] = "accepted"
    item["handoff"] = {"owner": "worker"}
    item["accepted"] = {"by": "reviewer"}
    item["lease"] = None
    if "ghidra-writer" in item["resources"]:
        item["ghidra_receipt"] = {
            "receipt_sha256": "a" * 64, "saved": True, "scope": {"functions": [], "types": [], "globals": globals_ or []},
        }


def _accept_chain(tracker: dict, apply_id: str, globals_: list[str] | None = None) -> None:
    by_id = {row["id"]: row for row in tracker["work_items"]}

    def accept(item_id: str, scope: list[str] | None = None) -> None:
        item = by_id[item_id]
        if item["status"] == "accepted":
            return
        for dependency in item["dependencies"]:
            accept(dependency)
        _accept(item, scope)

    accept(apply_id, globals_)


# -- ELF facts ------------------------------------------------------------------------


def test_symbol_facts_name_size_dwarf_and_copies(root: Path, identities: dict) -> None:
    chain = identities[DMA_CHAIN]
    assert chain["object"] and chain["size"] == 4 and chain["names"] == ["m_dmaChain__Q23zdb7CVisual"]
    assert chain["dwarf"] == [] and chain["copies"] == [] and chain["inside_function"] is None
    assert chain["labels"]["m_dmaChain__Q23zdb7CVisual"] == {"namespace": "zdb::CVisual", "name": "m_dmaChain"}
    assert [row["tag"] for row in identities[CAMERA]["dwarf"]] == ["global_variable", "global_variable"]
    assert identities[STACK_VID]["size"] == 28
    rtti = [s.value for s in __import__("tools._socom.elf", fromlist=["Elf32File"]).Elf32File(
        root / "support" / "socom.elf").symbols() if s.name == "__RTTI__Q23zdb7CVisual"]
    copies = global_symbol_facts(root, [f"0x{rtti[0]:x}", "0x30c7c4"])
    assert copies[f"0x{rtti[0]:x}"]["copies"] == ["__RTTI__Q23zdb7CVisual"]
    assert not copies["0x30c7c4"]["object"] and copies["0x30c7c4"]["inside_function"] == "GetChainData__Q23zdb7CVisualFv"
    assert readable_label("gbMutexInitialized") is None and readable_label("m_isinfight__11CSndJukebox") == {
        "namespace": "CSndJukebox", "name": "m_isinfight",
    }
    members = qualifier_globals(root, "zdb::CVisual")
    assert int(DMA_CHAIN, 16) in members and int(CAMERA, 16) in members and len(members) == 48


def test_spelled_sizes() -> None:
    assert spelled_size("uchar") == 1 and spelled_size("float[3]") == 12 and spelled_size("_word128 *") == 4
    assert spelled_size("float *[4]") == 16 and spelled_size("CCamera") is None and spelled_size("int[2][3]") == 24


def test_global_facts_report_widths_values_and_typed_flows(root: Path) -> None:
    report = global_facts(root, [OPACITY, FOG_ENABLE, STACK_VID, DMA_CHAIN])
    rows = {row["address"]: row for row in report["globals"]}
    opacity = rows[OPACITY]["summary"]
    assert opacity["widths"] == [4] and opacity["kinds"] == ["float"] and opacity["stored_parameter_types"] == ["float"]
    assert "constant 1065353216 (0x3f800000) = 1.0f" in opacity["constants"]
    fog = rows[FOG_ENABLE]
    assert fog["summary"]["loads"] == {"lbu": 7} and fog["summary"]["stores"] == {"sb": 3}
    assert "  004753f8  01" in fog["bytes"]
    assert any("std::deque<unsigned int, std::allocator<unsigned int>> * (receiver)" in typed for typed in rows[STACK_VID]["summary"]["passed_as"])
    assert rows[DMA_CHAIN]["summary"]["passed_as"] == ["_word128*"] and "zero-initialized" in rows[DMA_CHAIN]["bytes"]
    assert report == global_facts(root, [OPACITY, FOG_ENABLE, STACK_VID, DMA_CHAIN])


# -- tracker items --------------------------------------------------------------------


def test_add_recon_repair_of_globals_refuses_dwarf_and_non_objects(root: Path, decomposed: dict, identities: dict) -> None:
    facts = global_symbol_facts(root, [DMA_CHAIN, CAMERA, "0x4765f5", "0x30c7c4"])
    with pytest.raises(SocomError, match="needs at least one function or global"):
        add_recon_repair_items(decomposed, [], [])
    with pytest.raises(SocomError, match="needs their ELF and DWARF facts"):
        add_recon_repair_items(decomposed, [], [DMA_CHAIN])
    with pytest.raises(SocomError) as failure:
        add_recon_repair_items(decomposed, [], [CAMERA, "0x4765f5", "0x30c7c4"], facts)
    text = str(failure.value)
    assert "0x4765d8 (m_camera__Q23zdb7CVisual) has DWARF records (global_variable 0xbdba4" in text
    assert "a repair may not contradict DWARF" in text and "0x4765f5 is not the start of a sized .symtab OBJECT" in text
    assert "0x30c7c4 is not the start" in text


def test_add_recon_repair_of_globals_adds_items_and_dependencies(root: Path, decomposed: dict) -> None:
    facts = global_symbol_facts(root, [DMA_CHAIN, DMA_QWC, APPLY_SCALE_COLOR])
    # The group apply that typed m_applyScaleColor is accepted with it in its receipt scope.
    group = next(row for row in decomposed["work_items"] if row["kind"] == "recon-plan-group")
    _accept_chain(decomposed, f"{group['id']}-apply", [APPLY_SCALE_COLOR])
    ids = add_recon_repair_items(decomposed, [], [DMA_QWC, DMA_CHAIN, APPLY_SCALE_COLOR], facts)
    refresh_ready_and_stages(decomposed)
    assert audit_tracker(decomposed, strict=True) == []
    by_id = {row["id"]: row for row in decomposed["work_items"]}
    plan, apply = by_id[ids[0]], by_id[ids[1]]
    assert plan["batch"]["globals"] == [APPLY_SCALE_COLOR, DMA_CHAIN, DMA_QWC] and plan["batch"]["functions"] == []
    assert plan["title"] == "Plan recon repair 001 (3 globals)" and plan["status"] == "ready"
    assert plan["dependencies"] == [f"{group['id']}-apply"] and apply["batch"] == plan["batch"]
    assert set(ids) <= set(by_id[RECON_SEED_ID]["dependencies"])
    assert plan_digest(plan) == repair_sha256(plan["batch"]) != repair_sha256({**plan["batch"], "globals": [DMA_CHAIN]})
    with pytest.raises(SocomError, match="unfinished repair"):
        add_recon_repair_items(decomposed, [], [DMA_CHAIN], facts)
    claim_work(decomposed, ids[0], "planner", 30)
    packet = work_packet(decomposed, ids[0], "planner")
    assert f"python tools/socom.py recon global-facts --item {ids[0]}" in packet["validation"]
    # An apply awaiting acceptance with the global in its receipt blocks a new repair of it.
    other = next(row for row in decomposed["work_items"] if row["kind"] == "recon-apply-group" and row["status"] != "accepted")
    other["ghidra_receipt"] = {"scope": {"functions": [], "types": [], "globals": ["0x4765fc"]}}
    other["status"] = "awaiting_acceptance"
    with pytest.raises(SocomError, match="wait for its acceptance"):
        add_recon_repair_items(decomposed, [], [OPACITY], global_symbol_facts(root, [OPACITY]))
    broken = copy.deepcopy(decomposed)
    next(row for row in broken["work_items"] if row["id"] == ids[0])["batch"]["globals"] = [DMA_QWC, DMA_CHAIN]
    assert any("must list its globals once each" in text for text in audit_tracker(broken))


def test_function_only_repairs_keep_their_batch_and_digest(decomposed: dict) -> None:
    batch = {"repair_number": 1, "functions": ["0x3defd8"], "groups": {"0x3defd8": "g"}, "graph_sha256": "f" * 64}
    from tools._socom.util import canonical_json
    import hashlib

    assert repair_sha256(batch) == hashlib.sha256(canonical_json(batch).encode("utf-8")).hexdigest()
    group = next(row for row in decomposed["work_items"] if row["kind"] == "recon-plan-group" and "0x3defd8" in row["batch"]["functions"])
    _accept_chain(decomposed, f"{group['id']}-apply")
    ids = add_recon_repair_items(decomposed, ["0x3defd8"])
    plan = next(row for row in decomposed["work_items"] if row["id"] == ids[0])
    assert "globals" not in plan["batch"] and plan["title"] == "Plan recon repair 001 (1 functions of applied groups)"


# -- plan rows and program --------------------------------------------------------------


def _rows() -> list[dict]:
    return [
        {
            "address": DMA_CHAIN,
            "symbol": "m_dmaChain__Q23zdb7CVisual",
            "label": {"namespace": "zdb::CVisual", "name": "m_dmaChain"},
            "live_type": "",
            "type": "_word128 *",
            "repair": ["mangled name only; untyped although its value is a _word128 pointer"],
            "evidence": ["VuUpdate passes it plus an index as Copy__4CSPR's _word128 * a1"],
        },
        {
            "address": DMA_QWC,
            "symbol": "m_dmaQwc__Q23zdb7CVisual",
            "label": {"namespace": "zdb::CVisual", "name": "m_dmaQwc"},
            "live_type": "",
            "type": "keep",
            "keep_reason": ["the signedness of the count is not settled"],
            "repair": ["mangled name only"],
            "evidence": ["4-byte object"],
        },
    ]


def _plan(tracker: dict, item_id: str, rows: list[dict]) -> dict:
    item = next(row for row in tracker["work_items"] if row["id"] == item_id)
    return {
        "kind": RECON_PLAN_KIND,
        "schema_version": 1,
        "work_item_id": item_id,
        "group_sha256": plan_digest(item),
        "target": {"source_sha256": REFERENCE_SHA256},
        "functions": [],
        "globals": rows,
    }


@pytest.fixture()
def repair(root: Path, decomposed: dict, tmp_path: Path) -> tuple[dict, str, Path, dict]:
    ids = add_recon_repair_items(decomposed, [], [DMA_CHAIN, DMA_QWC], global_symbol_facts(root, [DMA_CHAIN, DMA_QWC]))
    plan = _plan(decomposed, ids[0], _rows())
    path = tmp_path / "repair.json"
    atomic_write_json(path, plan)
    return decomposed, ids[0], path, plan


def test_repair_global_rows_validate_and_translate(root: Path, repair) -> None:
    tracker, plan_id, path, plan = repair
    assert validate_recon_plan(root, tracker, plan) == []
    program = build_recon_program(root, tracker, path)
    chain, qwc = program["globals"]
    assert chain == {
        "address": DMA_CHAIN, "current_name": "m_dmaChain__Q23zdb7CVisual", "readable_name": "zdb::CVisual::m_dmaChain",
        "rename": True, "type": "_word128 *", "type_skip": None, "size": 4, "replaces_accepted": False, "live_type": "",
        "notes": ["repair: mangled name only; untyped although its value is a _word128 pointer"],
    }
    assert qwc["type"] is None and qwc["type_skip"] == "keep: the signedness of the count is not settled" and qwc["rename"]
    assert program["receipt_scope"] == {"schema_version": 1, "functions": [], "types": [], "globals": [DMA_CHAIN, DMA_QWC]}
    assert program["summary"]["typed_global_count"] == 1 and program["summary"]["renamed_global_count"] == 2
    retype = copy.deepcopy(plan)
    retype["globals"][0]["live_type"] = "pointer"
    atomic_write_json(path, retype)
    assert build_recon_program(root, tracker, path)["globals"][0]["replaces_accepted"] is False
    retype["globals"][0]["live_type"] = "uint"
    atomic_write_json(path, retype)
    assert build_recon_program(root, tracker, path)["globals"][0]["replaces_accepted"] is True


def test_repair_global_row_defects(root: Path, repair, identities: dict) -> None:
    tracker, _plan_id, _path, plan = repair
    defects = [
        (lambda r: r.update(label={"namespace": "zdb", "name": "m_dmaChain"}), "label must be the demangled name"),
        (lambda r: r.update(symbol="m_dmaQwc__Q23zdb7CVisual"), "symbol must be the .symtab object name"),
        (lambda r: r.pop("live_type"), "needs live_type"),
        (lambda r: r.update(type="undefined4"), "placeholder"),
        (lambda r: r.update(type="pointer"), "placeholder"),
        (lambda r: r.update(type="float[2]"), "is 8 bytes, but the .symtab object is 4"),
        (lambda r: r.update(type="boolean"), "well-known-type"),
        (lambda r: r.update(type="keep"), "keep needs keep_reason"),
        (lambda r: r.update(type="keep", keep_reason=["x"], label=None), "changes nothing"),
        (lambda r: r.update(live_type="_word128 *"), "live type '_word128 *' already"),
        (lambda r: r.update(keep_reason=["x"]), "only a keep row carries keep_reason"),
        (lambda r: r.update(repair=[]), "needs `repair`"),
        (lambda r: r.update(evidence=[]), "needs evidence"),
        (lambda r: r.update(rename="x"), "unknown keys ['rename']"),
    ]
    for change, message in defects:
        bad = copy.deepcopy(plan)
        change(bad["globals"][0])
        assert any(message in problem for problem in validate_recon_plan(root, tracker, bad)), message
    # bool is the builtin apply_data_type resolves it to; only its width is checked.
    builtin_bool = copy.deepcopy(plan)
    builtin_bool["globals"][0]["type"] = "bool"
    problems = validate_recon_plan(root, tracker, builtin_bool)
    assert not any("well-known-type" in problem for problem in problems), problems
    assert any("is 1 bytes, but the .symtab object is 4" in problem for problem in problems), problems
    missing = copy.deepcopy(plan)
    missing["globals"].pop()
    assert f"global {DMA_QWC} is missing from the plan" in validate_recon_plan(root, tracker, missing)
    stray = copy.deepcopy(plan)
    stray["globals"].append({**_rows()[0], "address": OPACITY})
    assert f"global {OPACITY} is not in the repair" in validate_recon_plan(root, tracker, stray)
    dwarf = repair_global_problems({**_rows()[0], "address": CAMERA, "symbol": "m_camera__Q23zdb7CVisual",
                                    "label": {"namespace": "zdb::CVisual", "name": "m_camera"}}, identities[CAMERA])
    assert any("stage 2 owns its name and type" in problem for problem in dwarf)


def test_function_repairs_still_refuse_globals(root: Path, decomposed: dict) -> None:
    group = next(row for row in decomposed["work_items"] if row["kind"] == "recon-plan-group" and "0x3defd8" in row["batch"]["functions"])
    _accept_chain(decomposed, f"{group['id']}-apply")
    ids = add_recon_repair_items(decomposed, ["0x3defd8"])
    plan = _plan(decomposed, ids[0], _rows())
    assert any("this recon repair lists no globals: globals must be empty" in p for p in validate_recon_plan(root, decomposed, plan))


# -- executor -------------------------------------------------------------------------------


class _Bridge:
    """audit_global and the label/type writes over a dict of live globals."""

    def __init__(self, live: dict[str, dict]) -> None:
        self.live, self.calls = copy.deepcopy(live), []

    def request(self, endpoint, **parameters):
        self.calls.append((endpoint, parameters))
        assert endpoint == "audit_global"
        row = self.live[parameters["address"]]
        return {"address": parameters["address"][2:].zfill(8), "is_code_address": False, **row}

    def post_json(self, endpoint, **body):
        self.calls.append((endpoint, body))
        row = self.live[body["address"]]
        if endpoint == "apply_data_type":
            row.update(type=body["type_name"], length=4)
        elif endpoint == "rename_label":
            assert row["name"] == body["old_name"]
            row["name"] = body["new_name"]
        return {"status": "success"}


LIVE = {
    DMA_CHAIN: {"name": "m_dmaChain__Q23zdb7CVisual", "type": "", "length": 0},
    DMA_QWC: {"name": "m_dmaQwc__Q23zdb7CVisual", "type": "", "length": 0},
}


def _execute(program: dict, bridge: _Bridge, **options):
    return batch_apply.execute_batch_program(
        program, bridge, type_index=lambda: [{"name": "_word128"}], function_names=lambda: {}, **options
    )


def test_executor_labels_types_and_reads_back(root: Path, repair) -> None:
    tracker, _plan_id, path, _plan = repair
    program = build_recon_program(root, tracker, path)
    dry = _execute(program, _Bridge(LIVE), dry_run=True)
    assert [(step["endpoint"], step["body"].get("address")) for step in dry["steps"]] == [
        ("apply_data_type", DMA_CHAIN), ("rename_label", DMA_CHAIN), ("create_label", DMA_CHAIN),
        ("rename_label", DMA_QWC), ("create_label", DMA_QWC),
    ]
    assert dry["steps"][2]["body"]["name"] == "m_dmaChain__Q23zdb7CVisual"
    assert {"address": DMA_QWC, "action": "type", "reason": "keep: the signedness of the count is not settled"} in dry["skipped"]
    bridge = _Bridge(LIVE)
    result = _execute(program, bridge)
    assert bridge.live[DMA_CHAIN] == {"name": "zdb::CVisual::m_dmaChain", "type": "_word128 *", "length": 4}
    assert bridge.live[DMA_QWC] == {"name": "zdb::CVisual::m_dmaQwc", "type": "", "length": 0}
    assert result["globals"][1] == {"address": DMA_QWC, "name": "zdb::CVisual::m_dmaQwc", "type": None, "size": 4, "live_type": ""}
    # The apply refuses before any write when a global no longer shows its recorded name and type.
    for change in ({"type": "uint", "length": 4}, {"name": "zdb::CVisual::m_dmaQwc"}):
        moved = copy.deepcopy(LIVE)
        moved[DMA_QWC].update(change)
        refused = _Bridge(moved)
        with pytest.raises(SocomError, match="replan the row"):
            _execute(program, refused)
        assert all(endpoint == "audit_global" for endpoint, _ in refused.calls)


class _KeepBreaker(_Bridge):
    """A bridge whose rename also retypes the keep row (read-back must catch it)."""

    def post_json(self, endpoint, **body):
        response = super().post_json(endpoint, **body)
        if endpoint == "create_label" and body["address"] == DMA_QWC:
            self.live[DMA_QWC]["type"] = "undefined4"
        return response


def test_executor_read_back_holds_a_keep_rows_type(root: Path, repair) -> None:
    tracker, _plan_id, path, _plan = repair
    with pytest.raises(batch_apply.BatchFailure, match="1 applied entries differ"):
        _execute(build_recon_program(root, tracker, path), _KeepBreaker(LIVE))


def test_later_group_rows_accept_a_repair_label() -> None:
    entry = {
        "address": DMA_CHAIN, "current_name": "m_dmaChain__Q23zdb7CVisual", "readable_name": "m_dmaChain__Q23zdb7CVisual",
        "rename": False, "type": "_word128 *", "type_skip": None, "size": 4, "replaces_accepted": False,
    }
    program = {"kind": batch_apply.BATCH_PROGRAM_KIND, "schema_version": batch_apply.BATCH_PROGRAM_SCHEMA,
               "functions": [], "globals": [entry]}
    live = {DMA_CHAIN: {"name": "zdb::CVisual::m_dmaChain", "type": "_word128 *", "length": 4}}
    result = _execute(program, _Bridge(live), dry_run=True)
    assert result["steps"] == [] and {"address": DMA_CHAIN, "action": "label", "name": "zdb::CVisual::m_dmaChain"} in result["unchanged"]
    assert result["globals"] == [{"address": DMA_CHAIN, "name": "zdb::CVisual::m_dmaChain", "type": "_word128 *", "size": 4}]
    other = {DMA_CHAIN: {"name": "zdb::Other::m_dmaChain", "type": "", "length": 0}}
    with pytest.raises(SocomError, match="expected 'm_dmaChain__Q23zdb7CVisual'"):
        _execute(program, _Bridge(other), dry_run=True)


# -- limit and read-back -----------------------------------------------------------------------


def test_repair_limit_and_read_back_of_globals(root: Path, repair) -> None:
    tracker, plan_id, path, _plan = repair
    item = next(row for row in tracker["work_items"] if row["id"] == plan_id)
    program = build_recon_program(root, tracker, path)
    steps = _execute(program, _Bridge(LIVE), dry_run=True)["steps"]
    bridge = _Bridge(LIVE)
    result = _execute(program, bridge)
    scope = program["receipt_scope"]
    diff = {"functions": []}
    name, ok, detail = repair_limit(item, program, scope, diff, {"thunks": [], "split_targets": []}, steps, result)
    assert name == "limit" and ok, detail
    assert "of 2 listed globals 2 relabelled and 1 typed (1 keep their type)" in detail
    stray = steps + [{"endpoint": "apply_data_type", "body": {"address": OPACITY}}]
    assert "apply calls outside the repair: ['0x4765fc']" in repair_limit(item, program, scope, diff, {}, stray, result)[2]
    narrow = {**scope, "globals": [DMA_CHAIN]}
    assert "not exactly the listed functions and globals" in repair_limit(item, program, narrow, diff, {}, steps, result)[2]
    skipped = copy.deepcopy(result)
    skipped["globals"][0]["type"] = None
    assert "without their planned label or type: ['0x4765f4']" in repair_limit(item, program, scope, diff, {}, steps, skipped)[2]
    scoped = [{"address": f"{int(a, 16):08x}", **row} for a, row in bridge.live.items()]
    assert global_readback(result["globals"], scoped, steps) == []
    scoped[1]["type"] = "uint"
    no_label = [step for step in steps if not (step["endpoint"] == "create_label" and step["body"]["address"] == DMA_CHAIN)]
    problems = global_readback(result["globals"], scoped, no_label)
    assert any("typed 'uint', planned ''" in text for text in problems)
    assert any("no create_label call kept the mangled symbol 'm_dmaChain__Q23zdb7CVisual'" in text for text in problems)


def test_relabelled_globals_explain_their_derived_pointer_labels(root: Path) -> None:
    old, new = "m_dmaChain__Q23zdb7CVisual", "zdb::CVisual::m_dmaChain"
    diff = {
        "functions": [],
        "data": {
            "removed": [{"address": "00470000", "name": f"PTR_{old}_00470000", "type": "pointer", "size": 4}],
            "added": [{"address": "00470000", "name": f"PTR_{new}_00470000", "type": "pointer", "size": 4}],
        },
        "references": {"added": [], "removed": []},
        "types": {"added": [], "removed": []},
        "blocks_equal": True,
        "bookmarks_equal": True,
    }
    steps = [{"endpoint": "rename_label", "body": {"address": DMA_CHAIN, "old_name": old, "new_name": new}}]
    problems, _summary = explain_recon_diff(root, diff, {"functions": []}, steps, {"functions": [], "globals": []})
    assert problems == []
    problems, _summary = explain_recon_diff(root, diff, {"functions": []}, [], {"functions": [], "globals": []})
    assert any("unexplained" in text for text in problems)
