"""Stage 3 references: the plan's decisions, the apply, its stops and the record, against a fake bridge."""
from __future__ import annotations

import json

import pytest

import elfimage
import ghidra_bridge as gb
import names
import references as rf
from asm import A0, A1, AT, GP, JR_RA, NOP, V0, addiu, addu, i_type, lui, lw, sw
from fake_references import FakeReferences

V1, A2, A3, T0, T1, T2, T3, T4, T5, T6 = 3, 6, 7, 8, 9, 10, 11, 12, 13, 14
BASE = 0x100000
HEADER = ("release_address", "release_size", "prototype_address", "prototype_size", "prototype_symbol",
          "prototype_section", "release_section", "class", "evidence", "witnesses", "flags", "withhold", "owner_file")


def ori(rt, rs, imm):
    return i_type(0x0D, rs, rt, imm)


def lwl(rt, offset, base):
    return i_type(0x22, base, rt, offset)


# function -> (entry, words); gp = 0x208000 (lui/addiu into a0, then move gp, a0)
F0 = [lui(A0, 0x21), addiu(A0, A0, -0x8000), addu(GP, A0, 0), JR_RA, NOP, NOP, NOP, NOP]
F1 = [lw(V0, 0x10, GP),            # gp-load 0x208010
      sw(V0, 0x14, GP),            # gp-store 0x208014
      lui(AT, 0x21),
      lw(V1, 0x100, AT),           # pair-load 0x210100
      sw(V1, 0x104, AT),           # pair-store 0x210104
      addiu(A0, GP, 0x20),         # gp-address 0x208020
      lw(A1, 0x18, GP),            # gp-load 0x208018: present
      JR_RA, NOP, NOP]
F2 = [lui(A0, 0x21), addiu(A0, A0, 0x200),   # pair-address 0x210200, a base
      lw(A1, 4, A0),                         # field-load: withheld
      lui(A2, 0x22), ori(A2, A2, 0x1234),    # a lui/ori constant
      addiu(A3, GP, 0),                      # gp itself
      lwl(T0, 0x23, GP),                     # the left half of an unaligned pair
      lui(T1, 0x30), lw(T2, 0x10, T1),       # 0x300010: outside every block
      lui(T3, 0x10), lw(T4, 0x24, T3),       # 0x100024: reads code
      addiu(T5, T3, 0x28),                   # 0x100028: inside a function
      addiu(T6, T3, 0x20),                   # 0x100020: a function entry
      sw(V0, 0x30, GP),                      # gp-store with another reference on it
      JR_RA, NOP]
F3 = [lui(A0, 0x21), addiu(A0, A0, 0x300), sw(A0, 0x40, GP),   # stored; the store has the reference
      lui(A1, 0x21), addiu(A1, A1, 0x400), sw(A1, 0x44, GP),   # stored; no reference anywhere
      lui(T0, 0x21), addu(T0, T0, A2), lw(T1, 0x500, T0),      # indexed: no fixed target
      JR_RA, NOP, NOP]
F4 = [JR_RA, NOP, lw(V0, 0x50, GP), NOP, JR_RA, NOP, NOP, NOP]  # words 2-3: a gap of the body
# gp addresses into the initialised block (gp - n): made only for another use, as the one reference
F5 = [addiu(A0, GP, -0x100),                   # other use, the only reference: made
      addiu(A1, GP, -0x200), lw(A2, 4, A1),    # a base: withheld (and the field access)
      addiu(A3, GP, -0x300), sw(A3, 0x60, GP),  # stored: withheld; the store into .bss is made
      addiu(T0, GP, -0x400), lw(T1, -0x400, GP),  # the load already references it: a second reference
      JR_RA, NOP, NOP]
LAYOUT = [("F0", F0), ("f_access", F1), ("f_withheld", F2), ("f_store", F3), ("f_gap", F4), ("f_init", F5)]


@pytest.fixture(autouse=True)
def quick_settle(monkeypatch):
    monkeypatch.setattr(names, "QUIET_SECONDS", 0.0)
    monkeypatch.setattr(names, "POLL_SECONDS", 0.0)


def addresses():
    out, at = {}, BASE
    for name, words in LAYOUT:
        out[name] = (at, len(words))
        at += 4 * len(words)
    return out


def image():
    return elfimage.synthetic([w for _, words in LAYOUT for w in words], base=BASE, entry=BASE, role="release")


def make_ghidra(read_only=False):
    g = FakeReferences(read_only=read_only)
    r = g.release
    r.image = image()
    where = addresses()
    for name, (at, count) in where.items():
        r.add(at, at + 4 * count - 1, None if name == "F0" else name)
        r.code.update(range(at, at + 4 * count, 4))
    gap = where["f_gap"][0]
    r.functions[gap]["holes"] = [(gap + 8, gap + 15)]
    r.segments = [("SECTION4", 0x100000, 0x207FFF), (".bss", 0x208000, 0x2FFFFF)]
    f1, f2, f3, f5 = where["f_access"][0], where["f_withheld"][0], where["f_store"][0], where["f_init"][0]
    r.refs_from = {f1 + 24: [(0x208018, "READ")], f2 + 52: [(0x2000F0, "DATA")], f3 + 8: [(0x210300, "DATA")],
                   f5 + 24: [(0x207C00, "READ")]}
    r.refs_to = {0x208018: [f"From {f1 + 24:08x} in f_access [READ]"], 0x2000F0: ["From x in f [DATA]"],
                 0x210300: [f"From {f3 + 8:08x} in f_store [DATA]"], 0x207C00: [f"From {f5 + 24:08x} in f_init [READ]"]}
    r.labels[0x208010] = ["g_count"]
    r.labels[0x208012] = ["g_half"]
    r.data[0x208012] = ("int", 4)        # 0x208014 lies inside it: g_half+2
    r.data[0x210100] = ("int[4]", 16)    # 0x210104 lies inside it: <item>[1]
    return g


def reader_for(g):
    reader = FakeReferences(read_only=True)
    reader.prototype, reader.release = g.prototype, g.release
    return reader


def make_root(tmp_path, monkeypatch, module_rows=()):
    (tmp_path / "docs" / "release").mkdir(parents=True)
    rows = [{"release_address": "0x208010", "release_size": "4", "prototype_address": "0x300010", "prototype_size": "4",
             "prototype_symbol": "g_count", "prototype_section": ".bss", "release_section": ".bss", "class": "exact",
             "evidence": "operand-exact:1", "witnesses": "1", "flags": "-", "withhold": "-", "owner_file": "-"},
            {"release_address": "0x210100", "release_size": "16..64", "prototype_address": "0x300100",
             "prototype_size": "64", "prototype_symbol": "g_obj", "prototype_section": ".bss", "release_section": ".bss",
             "class": "deviating", "evidence": "order:1", "witnesses": "1", "flags": "size-unconfirmed", "withhold": "-",
             "owner_file": "-"}]
    text = "\t".join(HEADER) + "\n" + "".join("\t".join(r[c] for c in HEADER) + "\n" for r in rows)
    (tmp_path / "docs/release/data-map.tsv").write_text(text, encoding="utf-8", newline="\n")
    (tmp_path / names.MAP_TSV).write_text("function map\n", encoding="utf-8", newline="\n")
    sha = names.sha256_text("function map\n")
    monkeypatch.setattr(names, "load_map", lambda root: (list(module_rows), [], sha))
    return tmp_path


def plan_for(tmp_path, monkeypatch, g, module=None, rows=(), **kw):
    root = make_root(tmp_path, monkeypatch, rows)
    plan = rf.build_plan(root, reader_for(g), module, image=g.release.image, **kw)
    return root, plan, rf.write_plan(root, plan)


def at(name, index):
    return names.hx(addresses()[name][0] + 4 * index)


def entry(plan, name, index):
    found = [e for e in plan["entries"] if e["from"] == at(name, index)]
    assert len(found) == 1, (name, index, found)
    return found[0]


# --- the plan --------------------------------------------------------------------------------------

def test_plan_kinds_types_and_operands(tmp_path, monkeypatch):
    g = make_ghidra()
    _, plan, _ = plan_for(tmp_path, monkeypatch, g)
    assert plan["gp"] == "0x208000"
    got = {(e["from"], e["to"], e["kind"], e["ref_type"], e["operand"]) for e in plan["entries"] if e["state"] == "planned"}
    assert (at("f_access", 0), "0x208010", "gp-load", "READ", 1) in got
    assert (at("f_access", 1), "0x208014", "gp-store", "WRITE", 1) in got
    assert (at("f_access", 3), "0x210100", "pair-load", "READ", 1) in got
    assert (at("f_access", 4), "0x210104", "pair-store", "WRITE", 1) in got
    assert (at("f_access", 5), "0x208020", "gp-address", "DATA", 0) in got
    assert (at("f_withheld", 1), "0x210200", "pair-address", "DATA", 0) in got
    assert (at("f_store", 4), "0x210400", "pair-address", "DATA", 0) in got
    assert (at("f_store", 5), "0x208044", "gp-store", "WRITE", 1) in got
    assert (at("f_init", 0), "0x207f00", "gp-address", "DATA", 0) in got  # the initialised block, another use
    assert (at("f_init", 4), "0x208060", "gp-store", "WRITE", 1) in got
    assert len(got) == 10
    assert all(e["source_type"] == "ANALYSIS" for e in plan["entries"] if e["state"] == "planned")
    assert entry(plan, "f_withheld", 1)["feeds"] == ["accesses through it"]
    assert entry(plan, "f_store", 4)["feeds"] == ["a store"]
    assert entry(plan, "f_access", 3)["evidence"] == [[at("f_access", 2), "nop"], [at("f_access", 3), "nop"]]


def test_plan_target_state(tmp_path, monkeypatch):
    g = make_ghidra()
    _, plan, _ = plan_for(tmp_path, monkeypatch, g)
    t = entry(plan, "f_access", 0)["target"]
    assert t["block"] == ".bss" and t["labels"] == ["g_count"]
    assert t["map"] == {"release": "0x208010", "symbol": "g_count", "class": "exact", "offset": 0, "size": "4"}
    t = entry(plan, "f_access", 4)["target"]
    assert t["map"]["symbol"] == "g_obj" and t["map"]["offset"] == 4
    assert t["data"] == ["0x210100", 16, "int[4]", 4] and t["item_labels"] == []
    assert entry(plan, "f_access", 3)["target"]["data"] == ["0x210100", 16, "int[4]", 0]
    assert "item_labels" not in entry(plan, "f_access", 3)["target"]
    assert entry(plan, "f_access", 1)["target"]["item_labels"] == ["g_half"]


def test_plan_present_covered_and_withheld(tmp_path, monkeypatch):
    g = make_ghidra()
    _, plan, _ = plan_for(tmp_path, monkeypatch, g)
    assert entry(plan, "f_access", 6)["state"] == "present"
    covered = entry(plan, "f_store", 1)
    assert covered["state"] == "covered" and covered["reason"] == f"the store at {at('f_store', 2)} has the reference"
    reasons = {(e["from"]): rf.reason_group(e["reason"]) for e in plan["entries"] if e["state"] == "withheld"}
    assert reasons == {at("f_withheld", 2): "register-offset access", at("f_withheld", 4): "lui/ori constant",
                       at("f_withheld", 5): "gp itself", at("f_withheld", 6): "unaligned left half",
                       at("f_withheld", 8): "outside every memory block", at("f_withheld", 10): "reads or writes code",
                       at("f_withheld", 11): "points into code", at("f_withheld", 13): "other references on the instruction",
                       at("F0", 1): "gp itself", at("f_store", 2): "other references on the instruction",
                       at("f_withheld", 12): "initialised block: pair address",
                       at("f_init", 1): "initialised block: gp address, a base",
                       at("f_init", 2): "register-offset access",
                       at("f_init", 3): "initialised block: gp address, stored",
                       at("f_init", 5): "initialised block: gp address, a second reference"}
    assert "f_access at" in entry(plan, "f_withheld", 11)["reason"]
    assert at("f_init", 6) in entry(plan, "f_init", 5)["reason"]
    assert entry(plan, "f_init", 6)["state"] == "present"
    s = plan["summary"]
    assert s["uses_without_a_fixed_target"] == {"indexed-load": 1}
    assert s["uses_left_out"] == {"in no function body": 1}  # the load in the gap of f_gap
    assert s["planned"] == 10 and s["planned_by_block"] == {".bss": 9, "SECTION4": 1}
    assert s["covered_at_a_store"] == 1 and s["present"] == {"gp-load": 2}


def test_plan_is_deterministic_and_selects_a_module(tmp_path, monkeypatch):
    g = make_ghidra()
    _, one, _ = plan_for(tmp_path / "a", monkeypatch, g)
    _, two, _ = plan_for(tmp_path / "b", monkeypatch, g)
    assert one["plan_sha256"] == two["plan_sha256"]
    row = {"release_address": addresses()["f_access"][0], "owner_file": "src/gamez/zTest/a.cpp", "class": "exact",
           "neighbour_group": "-"}
    _, mod, path = plan_for(tmp_path / "c", monkeypatch, g, "gamez/zTest", rows=[row])
    assert set(mod["functions"]) == {at("f_access", 0)} and path.name == "plan-gamez-zTest.json"
    assert {e["function"] for e in mod["entries"]} == {at("f_access", 0)}
    _, user, _ = plan_for(tmp_path / "d", monkeypatch, g, source_type="USER_DEFINED")
    assert {e["source_type"] for e in user["entries"] if e["state"] == "planned"} == {"USER_DEFINED"}
    with pytest.raises(names.Refused):
        plan_for(tmp_path / "e", monkeypatch, g, source_type="IMPORTED")


# --- the apply -------------------------------------------------------------------------------------

def run(root, path, g, **kw):
    return rf.apply(root, path, g, today="2026-11-28", **kw)


def test_dry_run_sends_nothing(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    reader = reader_for(g)
    result = run(root, path, reader, dry_run=True)
    assert result["stopped"] is None and result["counts"] == {"reference": 10} and not reader.sent
    assert result["would_write"][0]["body"] == {"from_address": at("f_access", 0), "to_address": "0x208010",
                                                 "ref_type": "READ", "source_type": "ANALYSIS", "operand_index": 1}
    assert not (root / names.RECORD).exists()


def test_apply_writes_reads_back_records_and_a_second_run_changes_nothing(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    result = run(root, path, g, dry_run=False, check_every=4)
    assert result["stopped"] is None, result["stopped"]
    assert [s["endpoint"] for s in g.sent] == ["add_memory_reference"] * 10
    assert (0x208010, "READ") in g.release.refs_from[addresses()["f_access"][0]]
    assert result["checks"] == 3  # after 4, after 8, at the end
    rows = names.read_record(root)
    row = rows[(at("f_access", 0), rf.REFERENCE)]
    assert row["value"] == "to 0x208010 READ operand 1 ANALYSIS (gp-load)"
    assert row["state"] == f"unsaved {result['report']}"
    assert rf.confirm_saved(root, root / rf.OUT / result["report"], reader_for(g), today="2026-11-28")["confirmed"] == 10
    again = run(root, path, g, dry_run=False)
    assert again["stopped"] is None and again["unchanged"] == 10 and len(g.sent) == 10


def test_apply_refuses_unsaved_rows_a_changed_plan_and_other_blocks(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    run(root, path, g, dry_run=False, batch=1)
    with pytest.raises(names.Refused, match="unsaved"):
        run(root, path, g, dry_run=False)
    edited = json.loads(path.read_text(encoding="utf-8"))
    edited["gp"] = "0x200000"
    path.write_text(json.dumps(edited), encoding="utf-8")
    with pytest.raises(names.Refused, match="plan_sha256"):
        run(root, path, g, dry_run=True)
    root, plan, path = plan_for(tmp_path / "b", monkeypatch, make_ghidra())
    g = make_ghidra()
    g.release.segments = g.release.segments[:1]
    with pytest.raises(names.Refused, match="memory blocks"):
        run(root, path, g, dry_run=True)


def test_batch_and_only(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    result = run(root, path, g, dry_run=False, batch=2)
    assert result["batch_full"] and len(result["written"]) == 2
    g2 = make_ghidra()
    root2, _, path2 = plan_for(tmp_path / "b", monkeypatch, g2)
    result = run(root2, path2, g2, dry_run=False, only=frozenset({at("f_store", 5)}))
    assert [w["address"] for w in result["written"]] == [at("f_store", 5)]
    root3, _, path3 = plan_for(tmp_path / "c", monkeypatch, make_ghidra())
    stop = run(root3, path3, make_ghidra(), dry_run=True, only=frozenset({at("f_withheld", 2)}))
    assert stop["stop_kind"] == "StopBefore" and "not a planned reference" in stop["stopped"]


@pytest.mark.parametrize("change, match", [
    (lambda r: r.refs_from.setdefault(addresses()["f_access"][0], []).append((0x2000F0, "DATA")), "references from it"),
    (lambda r: r.functions[addresses()["f_access"][0]].update(end=addresses()["f_access"][0] + 0x1F), "function holding"),
    (lambda r: r.data.update({0x208010: ("int", 4)}), "has type"),
])
def test_stop_before_a_write(tmp_path, monkeypatch, change, match):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    change(g.release)
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopBefore" and match in result["stopped"] and not g.sent
    assert result["what_to_do"] == rf.AFTER_NOTHING


def test_stop_after_an_error_answer(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    g.reference_answers[addresses()["f_access"][0]] = {"error": "Error adding memory reference: boom"}
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "boom" in result["stopped"]
    assert result["attempted"] and not result["written"] and result["what_to_do"] == rf.AFTER_A_WRITE


def test_stop_after_a_reference_that_is_not_primary(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    first = addresses()["f_access"][0]
    g.release.ref_ops[first] = [(0x2000F0, "DATA", 1, "ANALYSIS")]  # an operand reference the bridge cannot show
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "is_primary" in result["stopped"]


def test_stop_after_a_read_back_with_more(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    first = addresses()["f_access"][0]
    g.reference_effects[first] = lambda p: p.refs_from[first].append((0x208011, "READ"))
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "read" in result["stopped"]


def test_stop_after_a_target_that_changes(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    g.reference_effects[addresses()["f_access"][0]] = lambda p: p.data.update({0x208010: ("undefined4", 4)})
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "the target 0x208010" in result["stopped"]


@pytest.mark.parametrize("effect, key", [
    (lambda p: p.bookmarks.append((0x100020, "Analysis", "x", "y")), "bookmark"),
    (lambda p: p.data.update({0x2FF000: ("undefined4", 4)}), "data"),
    (lambda p: p.labels.update({0x2FF000: ["made"]}), "labels"),
    (lambda p: p.functions[addresses()["f_store"][0]].update(own="renamed"), "function"),
])
def test_analysis_stop(tmp_path, monkeypatch, effect, key):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    g.reference_effects[addresses()["f_access"][0] + 4] = effect
    result = run(root, path, g, dry_run=False, check_every=1)
    assert result["stop_kind"] == "AnalysisStop" and result["analysis_changes"]
    assert key in result["analysis_changes"][0] and result["analysis_changes"][0]["seen"] == f"after {at('f_access', 1)}"
    assert len(result["written"]) == 2 and result["what_to_do"] == rf.AFTER_ANALYSIS


def test_analysis_running_after_a_write_runs_a_check(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    first = addresses()["f_access"][0]
    seen = []

    def busy(p):
        p.analyzing = True
        original = g.get_analysis_status

        def status(q):
            seen.append(1)
            p.analyzing = len(seen) < 2
            return original(q)
        g.get_analysis_status = status
    g.reference_effects[first] = busy
    result = run(root, path, g, dry_run=False, check_every=1000)
    assert result["stopped"] is None and result["checks"] == 2  # the one analysis asked for, and the end


def test_a_target_changed_later_is_seen_by_the_check(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    g.reference_effects[addresses()["f_access"][0] + 4] = lambda p: p.refs_to[0x208010].append("From y in f [READ]")
    result = run(root, path, g, dry_run=False, check_every=2)
    assert result["stop_kind"] == "AnalysisStop" and result["analysis_changes"][0]["target"] == "0x208010"


def test_discard_unsaved(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    result = run(root, path, g, dry_run=False, batch=2)
    report = root / rf.OUT / result["report"]
    with pytest.raises(names.Refused, match="still in the program"):
        rf.discard_unsaved(root, report, reader_for(g))
    fresh = make_ghidra()  # closed without saving: the program as before
    assert rf.discard_unsaved(root, report, reader_for(fresh))["discarded"] == 2
    assert not names.unsaved(names.read_record(root))


def test_confirm_saved_records_a_write_that_stopped_before_its_read_back(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    first = addresses()["f_access"][0]
    g.reference_effects[first + 4] = lambda p: p.refs_from[first + 4].append((0x208099, "READ"))
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and len(result["written"]) == 1
    done = rf.confirm_saved(root, root / rf.OUT / result["report"], reader_for(g), today="2026-11-28")
    assert done == {"confirmed": 1, "recorded_after_a_stop": 1, "report": result["report"]}


# --- the client ------------------------------------------------------------------------------------

def test_client_sends_add_memory_reference_only_in_the_planned_form():
    g = FakeReferences()
    good = {"from_address": "0x100020", "to_address": "0x208010", "ref_type": "READ", "source_type": "ANALYSIS",
            "operand_index": 1}
    for bad in ({"ref_type": "UNCONDITIONAL_CALL"}, {"ref_type": "FALL_THROUGH"}, {"source_type": "DEFAULT"},
                {"operand_index": -1}, {"operand_index": "1"}):
        with pytest.raises(gb.WriteRefused):
            g.write("add_memory_reference", gb.RELEASE_PROGRAM, **dict(good, **bad))
    with pytest.raises(gb.WriteRefused):
        g.write("add_memory_reference", gb.PROTOTYPE_PROGRAM, **good)
    with pytest.raises(gb.WriteRefused):
        g.write("remove_reference", gb.RELEASE_PROGRAM, from_address="0x100020", to_address="0x208010")
    with pytest.raises(gb.WriteRefused):
        FakeReferences(read_only=True).write("add_memory_reference", gb.RELEASE_PROGRAM, **good)
    with pytest.raises(gb.WriteRefused):
        FakeReferences(writes=gb.GLOBALS_WRITES).write("add_memory_reference", gb.RELEASE_PROGRAM, **good)
    assert g.write("add_memory_reference", gb.RELEASE_PROGRAM, **good)["status"] == "success"


def test_refs_from_reads_every_form():
    g = FakeReferences(read_only=True)
    g.get_get_xrefs_from = lambda q: ("To 0048d454 to data pBuffer [READ]\nTo 00140010 to function main [DATA]\n"
                                      "To Stack[0x10] [WRITE]")
    assert rf.refs_from(g, 0x100020) == [("0x140010", "DATA"), ("0x48d454", "READ"), ("Stack[0x10]", "WRITE")]
    g.get_get_xrefs_from = lambda q: "No references found from address: 0x100020"
    assert rf.refs_from(g, 0x100020) == []
    g.get_get_xrefs_to = lambda q: "From 00141708 in FUN_001416d0 [DATA]\nFrom 00100000 [READ]"
    assert rf.refs_to(g, 0x52718D) == [("0x100000", "READ"), ("0x141708", "DATA")]


# --- target names, the snapshot's reference lists, the texts -------------------------------------

def test_offcut_names_inside_a_data_item(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    result = run(root, path, g, dry_run=False)
    assert result["stopped"] is None, result["stopped"]
    reader = reader_for(g)
    assert rf.target_state(reader, 0x208014)["name"] == "g_half+2"
    assert rf.target_state(reader, 0x210104)["name"] == "DAT_00210100[1]"
    assert rf.target_state(reader, 0x210100)["name"] == "DAT_00210100"


@pytest.mark.parametrize("name, target, ok", [
    ("g_half+2", {"data": ["0x208012", 4, "int", 2], "item_labels": ["g_half"]}, True),
    ("g_half+3", {"data": ["0x208012", 4, "int", 2], "item_labels": ["g_half"]}, False),
    ("g_half.f2", {"data": ["0x208012", 4, "int", 2], "item_labels": ["g_half"]}, False),  # an int has no fields
    ("DAT_00208012+2", {"data": ["0x208012", 4, "int", 2], "item_labels": ["g_half"]}, False),
    ("s_0123456789abcdef_0047f3bf+0x21", {"data": ["0x47f3bf", 40, "string", 0x21], "item_labels": []}, True),
    ("theNetwork.m_bSessionMaster", {"data": ["0x511e00", 400, "CZNetwork", 0xA8], "item_labels": ["theNetwork"]}, True),
    ("neighbor__6CAiMap[4]", {"data": ["0x4390a4", 32, "int[8]", 16], "item_labels": ["neighbor__6CAiMap"]}, True),
    ("other[4]", {"data": ["0x4390a4", 32, "int[8]", 16], "item_labels": ["neighbor__6CAiMap"]}, False),
    ("DAT_004390a4[4]", {"data": ["0x4390a4", 32, "int[8]", 16], "item_labels": []}, True),
    ("DAT_004390a8[4]", {"data": ["0x4390a4", 32, "int[8]", 16], "item_labels": []}, False),  # another item
    ("_zsys_public+0x1d", {"data": ["0x527170", 64, "_zsys_public", 0x1D], "item_labels": ["_zsys_public"]}, True),
])
def test_same_target_accepts_the_offcut_forms_of_that_item_only(name, target, ok):
    address = int(target["data"][0], 16) + target["data"][3]
    want = {"address": names.hx(address), "name": "", "type": "", "length": 0, "xref_count": 1, "code": False,
            "entry": False}
    assert rf.same_target(dict(want, name=name), want, target) is ok


def test_a_name_at_an_item_start_or_in_no_item_must_be_dynamic():
    want = {"address": "0x208010", "name": "", "type": "", "length": 0, "xref_count": 1, "code": False, "entry": False}
    assert rf.same_target(dict(want, name="DAT_00208010"), want, {"data": None})
    assert not rf.same_target(dict(want, name="g_half+2"), want, {"data": None})
    assert not rf.same_target(dict(want, name="DAT_00208010"), dict(want, name="g_count"), {"data": None})


def test_stop_after_a_name_the_plan_did_not_predict(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    g.reference_effects[addresses()["f_access"][0] + 4] = lambda p: p.labels.update({0x208014: ["made"]})
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "the target 0x208014" in result["stopped"]


def test_the_check_reads_the_references_from_every_planned_instruction(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    first = addresses()["f_access"][0]
    g.reference_effects[first + 4] = lambda p: p.refs_from[first].append((0x2000F0, "DATA"))
    result = run(root, path, g, dry_run=False, check_every=2)
    assert result["stop_kind"] == "AnalysisStop"
    assert [c for c in result["analysis_changes"] if c.get("references_from") == at("f_access", 0)]


def test_the_check_reads_the_reference_list_of_every_written_target(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    first = addresses()["f_access"][0]

    def retype(p):  # the same count, another type
        p.refs_to[0x208010] = [line.replace("[READ]", "[DATA]") for line in p.refs_to[0x208010]]
    g.reference_effects[first + 4] = retype
    result = run(root, path, g, dry_run=False, check_every=2)
    assert result["stop_kind"] == "AnalysisStop"
    assert [c for c in result["analysis_changes"] if c.get("references_to") == "0x208010"]


def test_stop_after_a_reference_list_that_reads_otherwise(tmp_path, monkeypatch):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, monkeypatch, g)
    first = addresses()["f_access"][0]
    g.reference_effects[first] = lambda p: p.refs_to[0x208010].__setitem__(0, f"From {first:08x} in f [DATA]")
    result = run(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "the references to 0x208010" in result["stopped"]


def test_the_stop_texts_name_the_undo_and_the_route():
    for kind in ("StopAfter", "AnalysisStop"):
        assert "Edit > Undo" in rf.WHAT_TO_DO[kind] and "--discard-unsaved" in rf.WHAT_TO_DO[kind]
    assert "Undo" not in rf.WHAT_TO_DO["StopBefore"]
