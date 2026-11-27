"""Stage 3 signatures: planning, the apply and its guards, the record, against a fake bridge."""
from __future__ import annotations

import json

import pytest

import ghidra_bridge as gb
import names
import signatures as sg
from fake_ghidra import FakeGhidra
from test_names import image_for, make_root, row

PLATE = "Release map: deviating pair with prototype 0x300050 Dev__4CFooFv (evidence call; flags -).\nOwner -."
ROWS = [
    row(0x200000, 0x10, "exact", 0x300000, "Get__4CFooFi"),    # a clean write
    row(0x200010, 0x10, "exact", 0x300010, "Miss__4CFooFP4CBar"),  # names a type the release lacks
    row(0x200020, 0x10, "exact", 0x300020, "Dflt__4CFooFv"),   # the prototype has Ghidra's default
    row(0x200030, 0x10, "exact", 0x300030, "Tgt__4CFooFv"),    # target of the release thunk 0x200040
    row(0x200040, 0x08, "exact", 0x300040, "Thk__4CFooFv"),    # a release thunk: never written
    row(0x200050, 0x10, "deviating", 0x300050, "Dev__4CFooFv"),  # the deviating group
    row(0x200060, 0x10, "unsure", 0x300060, "Uns__4CFooFv"),   # unsure: nothing
]
PROTO = {0x300000: "CFoo::Get", 0x300010: "CFoo::Miss", 0x300020: "CFoo::Dflt", 0x300030: "CFoo::Tgt",
         0x300040: "CFoo::Thk", 0x300050: "CFoo::Dev", 0x300060: "CFoo::Uns"}
GET = "int __stdcall CFoo::Get(CFoo * this, int param_2)"


@pytest.fixture(autouse=True)
def quick_settle(monkeypatch):
    monkeypatch.setattr(names, "QUIET_SECONDS", 0.0)
    monkeypatch.setattr(names, "POLL_SECONDS", 0.0)


def make_ghidra(read_only=False):
    g = FakeGhidra(read_only=read_only, writes=gb.SIGNATURE_WRITES)
    for address, name in PROTO.items():
        g.prototype.add(address, address + 0xF, name)
    p, r = g.prototype, g.release
    p.sign(0x300000, "int", "__stdcall", [("CFoo *", "this"), ("int", "param_2")])
    p.sign(0x300010, "void", "__stdcall", [("CFoo *", "this"), ("CBar *", "bar")])
    p.sign(0x300030, "void", "__stdcall", [("CFoo *", "this")])
    p.sign(0x300050, "uchar", "__stdcall", [("CFoo *", "this"), ("short", "flags")])
    p.sign(0x300060, "int", "__stdcall", [])
    for program in (p, r):
        program.add_type("/project/CFoo", 8)
    p.add_type("/project/CBar", 4)
    for address, size in ((0x200000, 0x10), (0x200010, 0x10), (0x200020, 0x10), (0x200030, 0x10),
                          (0x200050, 0x10), (0x200060, 0x10)):
        name = PROTO[address + 0x100000]
        r.add(address, address + size - 1, None if address == 0x200030 else name)
    r.add(0x200040, 0x200047, thunk_of=0x200030)
    r.plates[0x200050] = PLATE
    r.image = image_for(ROWS)
    return g


def reader_for(g):
    reader = FakeGhidra(read_only=True)
    reader.prototype, reader.release = g.prototype, g.release
    return reader


def plan_for(tmp_path, g, module="gamez/zTest"):
    root = make_root(tmp_path, ROWS)
    plan = sg.build_plan(root, reader_for(g), module, image=g.release.image)
    return root, plan, sg.write_plan(root, plan)


def by_address(plan):
    return {e["address"]: e for e in plan["entries"]}


def test_plan_groups_reasons_and_determinism(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    by = by_address(plan)
    get = by["0x200000"]
    assert (get["group"], get["action"]) == ("exact", "write")
    assert get["send"] == {"prototype": "int socom_prototype(CFoo * this, int param_2)", "calling_convention": "__stdcall"}
    assert get["expected"]["signature"] == GET
    assert get["expected"]["parameters"] == [{"name": "this", "type": "CFoo *", "storage": "a0_lo:4"},
                                             {"name": "param_2", "type": "int", "storage": "a1_lo:4"}]
    miss = by["0x200010"]
    assert miss["action"] == "withheld" and miss["reason"] == "missing type /project/CBar"
    assert plan["missing_types"] == {"/project/CBar": 1} and plan["summary"]["missing_types"] == 1
    assert by["0x200020"]["action"] == "default" and plan["summary"]["default_prototype_signatures"] == 1
    target = by["0x200030"]
    assert target["send"]["prototype"] == "void FUN_00200030(CFoo * this)"  # a default name is sent as it is
    assert target["thunks"] == [{"address": "0x200040", "name": "thunk_FUN_00200030",
                                 "signature_before": "undefined thunk_FUN_00200030(void)",
                                 "signature_after": "void __stdcall thunk_FUN_00200030(CFoo * this)"}]
    assert by["0x200040"]["action"] == "withheld" and by["0x200040"]["reason_group"] == "thunk"
    dev = by["0x200050"]
    assert (dev["group"], dev["action"]) == ("deviating", "write")
    assert dev["plate"]["after"] == PLATE[:-1] + "; " + names.SIGNATURE_CLAUSE + "."
    assert by["0x200060"]["reason"] == "unsure pair"
    assert plan["summary"]["planned"] == {"deviating": 1, "exact": 2}
    text = path.read_text(encoding="utf-8")
    assert str(tmp_path) not in text and ":\\" not in text
    assert sg.canonical(sg.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image)) == text
    assert "missing type" in path.with_suffix(".md").read_text(encoding="utf-8")


def test_clean_apply_thunk_follows_record_confirm_and_rerun(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    result = sg.apply(root, path, g, dry_run=False, today="2026-11-27")
    assert result["stopped"] is None and result["side_effects"] == [] and result["analysis_changes"] == []
    assert result["counts"] == {"prototype": 2} and result["skipped"] == {"group deviating not taken": 1}
    assert {s["endpoint"] for s in result["sent"]} == {"set_function_prototype"}
    assert all(s["program"] == gb.RELEASE_PATH for s in result["sent"])
    assert not any("save" in e for _, e in g.requests)
    r = g.release
    assert r.signature(0x200000) == GET and r.shown(0x200000) == "CFoo::Get"
    assert r.signature(0x200030) == "void __stdcall FUN_00200030(CFoo * this)"  # not renamed by the text
    assert r.signature(0x200040) == "void __stdcall thunk_FUN_00200030(CFoo * this)"  # followed, predicted
    assert result["checkpoints"] and result["checkpoints"][-1]["changes"] == 0
    record = (root / names.RECORD).read_text(encoding="utf-8")
    assert (f"0x200000\tprototype\t{GET} [storage this=a0_lo:4, param_2=a1_lo:4]\t0x300000 Get__4CFooFi (exact)"
            f"\t2026-11-27\tunsaved {result['report']}") in record
    with pytest.raises(names.Refused, match="unsaved"):
        sg.apply(root, path, g, dry_run=False)
    done = sg.confirm_saved(root, root / sg.OUT / result["report"], g, today="2026-11-28")
    assert done["confirmed"] == 2
    saved = (root / names.RECORD).read_text(encoding="utf-8")
    assert "unsaved" not in saved
    sent = len(g.sent)
    again = sg.apply(root, path, g, dry_run=False, today="2026-11-29")
    assert again["stopped"] is None and again["written"] == [] and len(g.sent) == sent
    assert again["unchanged"] == {"prototype": 2}
    assert (root / names.RECORD).read_text(encoding="utf-8") == saved
    replan = sg.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image)
    assert {e["address"]: e["action"] for e in replan["entries"]}["0x200000"] == "unchanged"


def test_dry_run_sends_nothing(tmp_path):
    g = make_ghidra(read_only=True)
    root, plan, path = plan_for(tmp_path, g)
    result = sg.apply(root, path, g, dry_run=True, classes=("exact", "deviating"))
    assert g.sent == [] and not any(m == "POST" for m, _ in g.requests)
    assert result["counts"] == {"plate": 1, "prototype": 3}
    assert not (root / names.RECORD).exists()


def test_deviating_pairs_need_the_class_and_flag_the_plate_and_discard_restores(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    names.update_record(root, [{"address": "0x200050", "applied": "plate", "value": PLATE,
                                "source_pair": "0x300050 Dev__4CFooFv (deviating)"}], "2026-11-26", "names.json")
    rows = names.read_record(root)
    for row_ in rows.values():
        row_["state"] = "saved 2026-11-26"
    names.write_record(root, rows)
    with pytest.raises(names.Refused, match="--classes"):
        sg.apply(root, path, g, dry_run=True, classes=("deviating",))
    result = sg.apply(root, path, g, dry_run=False, classes=("exact", "deviating"), today="2026-11-27")
    assert result["stopped"] is None and result["counts"] == {"plate": 1, "prototype": 3}
    assert g.release.signature(0x200050) == "uchar __stdcall CFoo::Dev(CFoo * this, short flags)"
    assert g.release.plates[0x200050].endswith(names.SIGNATURE_CLAUSE + ".")
    record = names.read_record(root)
    assert record[("0x200050", "plate")]["state"] == f"unsaved {result['report']}"
    # closed without saving: the names step's plate row comes back
    fresh = make_ghidra()
    done = sg.discard_unsaved(root, root / sg.OUT / result["report"], fresh)
    assert done["restored"] == 1
    record = names.read_record(root)
    assert record[("0x200050", "plate")]["value"] == names.record_value(PLATE)
    assert record[("0x200050", "plate")]["state"] == "saved 2026-11-26"
    assert ("0x200000", "prototype") not in record


def test_a_read_back_mismatch_stops_at_the_first_function(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.mangle_prototype = True
    result = sg.apply(root, path, g, dry_run=False, today="2026-11-27")
    assert result["stopped"].startswith("prototype 0x200000 read back wrong: parameter 1 name 'param_1'")
    assert [s["body"]["function_address"] for s in result["sent"]] == ["0x200000"]
    assert result["written"] == [] and not (root / names.RECORD).exists()
    assert [a["applied"] for a in result["attempted"]] == ["prototype"]
    assert {(c["address"], c["change"]) for c in result["side_effects"]} == {("0x200000", "signature")}


def test_storage_the_parser_cannot_carry_stops_the_run(tmp_path):
    g = make_ghidra()
    g.prototype.functions[0x300000]["storage"] = ["a0_lo:4", "t0_lo:4"]  # custom storage in the prototype
    root, plan, path = plan_for(tmp_path, g)
    result = sg.apply(root, path, g, dry_run=False, today="2026-11-27")
    assert "parameter 2 storage 'a1_lo:4', expected 't0_lo:4'" in result["stopped"]


def test_an_unplanned_change_elsewhere_stops_the_run(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.prototype_effects[0x200000] = [lambda p: p.sign(0x200060, "int", "__stdcall", [])]  # a caller retyped
    result = sg.apply(root, path, g, dry_run=False, check_every=1, today="2026-11-27")
    assert "the program changed beyond the plan" in result["stopped"]
    assert [(c["address"], c["change"], c["window"]) for c in result["analysis_changes"]] == [
        ("0x200060", "signature", ["0x200000"])]
    assert [w["address"] for w in result["written"]] == ["0x200000"]  # read back before the snapshot


def test_a_function_analysis_creates_stops_the_run(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.prototype_effects[0x200030] = [lambda p: p.add(0x2000f0, 0x2000ff)]
    result = sg.apply(root, path, g, dry_run=False, today="2026-11-27")  # caught by the snapshot at the end
    assert {(c["address"], c["change"]) for c in result["analysis_changes"]} == {("0x2000f0", "appeared")}
    assert result["analysis_changes"][0]["window"] == ["0x200000", "0x200030"]


def test_a_thunk_that_does_not_follow_as_predicted_stops(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.functions[0x200040]["varargs"] = True  # the thunk's own flag: it would print ", ..."
    result = sg.apply(root, path, g, dry_run=False, today="2026-11-27")
    assert result["stopped"].startswith("the thunk 0x200040 of 0x200030 shows "
                                        "'void __stdcall thunk_FUN_00200030(CFoo * this, ...)', predicted")


def test_state_changed_since_the_plan_stops_before_a_write(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.sign(0x200000, "void", "__stdcall", [])
    result = sg.apply(root, path, g, dry_run=False)
    assert "replan" in result["stopped"] and result["sent"] == []


def test_a_live_signature_is_replaced_for_an_exact_pair_unless_it_says_more(tmp_path):
    g = make_ghidra()
    g.release.sign(0x200000, "void", "__stdcall", [("int", "x")])   # set by Ghidra's analysis
    g.release.sign(0x200030, "void", "__stdcall", [])
    g.prototype.sign(0x300030, "undefined", "__stdcall", [("CFoo *", "this")])
    g.release.sign(0x200050, "int", "__stdcall", [])
    _, plan, _ = plan_for(tmp_path, g)
    by = by_address(plan)
    assert by["0x200000"]["action"] == "write" and by["0x200000"]["replaces"] == "void __stdcall CFoo::Get(int x)"
    assert by["0x200030"]["action"] == "withheld" and "leaves undefined" in by["0x200030"]["reason"]
    assert by["0x200050"]["action"] == "withheld" and "the pair is not exact" in by["0x200050"]["reason"]


def test_refusals(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    assert sg.main(["--root", str(root), "--apply", str(path)]) == 2  # no --yes
    with pytest.raises(gb.WriteRefused):
        g.write("set_function_prototype", gb.PROTOTYPE_PROGRAM, function_address="0x300000", prototype="x")
    with pytest.raises(gb.WriteRefused):
        g.write("create_function", gb.RELEASE_PROGRAM, address="0x200000")  # not a signatures write
    with pytest.raises(gb.WriteRefused):
        FakeGhidra(read_only=True, writes=gb.SIGNATURE_WRITES).write(
            "set_function_prototype", gb.RELEASE_PROGRAM, function_address="0x200000", prototype="x")
    edited = json.loads(path.read_text(encoding="utf-8"))
    edited["entries"][0]["send"]["prototype"] = "int x(void)"
    (tmp_path / "edited.json").write_text(sg.canonical(edited), encoding="utf-8")
    with pytest.raises(names.Refused, match="plan_sha256"):
        sg.apply(root, tmp_path / "edited.json", g, dry_run=True)
    names_plan = dict(edited, kind=names.PLAN_KIND)
    (tmp_path / "names.json").write_text(sg.canonical(names_plan), encoding="utf-8")
    with pytest.raises(names.Refused, match="signatures plan"):
        sg.apply(root, tmp_path / "names.json", g, dry_run=True)


def test_signature_lines_parse_and_format_as_ghidra_prints_them():
    line = "noreturn int __stdcall std::sort<A*,bool_(*)(A,A)>(char * fmt, ...)"
    parts = sg.parse_signature(line, "std::sort<A*,bool_(*)(A,A)>")
    assert parts == {"noreturn": True, "return": "int", "convention": "__stdcall", "varargs": True,
                     "inside": "char * fmt"}
    assert sg.format_signature("int", "__stdcall", "f", [{"type": "char *", "name": "fmt"}], True, True) == \
        "noreturn int __stdcall f(char * fmt, ...)"
    assert sg.format_signature("undefined", None, "f", [], False, False) == "undefined f(void)"
    assert sg.is_default_signature(sg.parse_signature("undefined __stdcall f(void)", "f"))
    types = {"CFoo": [("/project/CFoo", 8)], "node": [("/a/node", 4), ("/b/node", 8)], "bool": [("/bool", 1)]}
    assert sg.check_type("CFoo * *", types, {"CFoo": [("/project/CFoo", 8)]}) == (None, None)
    assert sg.check_type("bool", types, {}) == (None, None)  # Ghidra's built-in
    assert "names 2 types" in sg.check_type("node *", types, types)[0]
    assert "has 4 bytes" in sg.check_type("CFoo", types, {"CFoo": [("/project/CFoo", 4)]})[0]
    assert "( ) or ," in sg.check_type("map<int, int> *", types, types)[0]


# --- the two names defects seen in the whole-map replan ---------------------------------------------

def test_a_default_thunk_showing_its_targets_name_is_no_collision(tmp_path):
    rows = [row(0x200000, 0x10, "exact", 0x300000, "Foo__3CFoFv"), row(0x200100, 0x08, "new")]
    g = FakeGhidra()
    g.prototype.add(0x300000, 0x30000F, "CFo::Foo")
    g.release.add(0x200000, 0x20000F, "CFo::Foo")
    g.release.add(0x200100, 0x200107, thunk_of=0x200000)  # shows CFo::Foo
    g.release.image = image_for(rows)
    root = make_root(tmp_path, rows)
    plan = names.build_plan(root, reader_for(g), None, image=g.release.image)
    assert plan["collisions"] == [] and by_address(plan)["0x200000"]["name"] == "CFo::Foo"


def test_a_replan_keeps_the_replaced_analysis_name_and_the_signature_flag(tmp_path):
    rows = [row(0x200000, 0x10, "exact", 0x300000, "Foo__3CFoFv"), row(0x200010, 0x10, "deviating", 0x300010, "Bar")]
    g = FakeGhidra()
    g.prototype.add(0x300000, 0x30000F, "CFo::Foo")
    g.prototype.add(0x300010, 0x30001F, "Bar")
    g.release.add(0x200000, 0x20000F, "AnalysisName")
    g.release.add(0x200010, 0x20001F)
    g.release.image = image_for(rows)
    root = make_root(tmp_path, rows)
    first = names.build_plan(root, reader_for(g), None, image=g.release.image)
    plate = by_address(first)["0x200000"]["plate"]
    assert plate.endswith("replaces the analysis name AnalysisName.")
    path = names.write_plan(root, first)
    applied = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    names.confirm_saved(root, root / names.OUT / applied["report"], g)
    # the signatures step flags the deviating plate afterwards (its record row replaces the names row)
    flagged = g.release.plates[0x200010][:-1] + "; " + names.SIGNATURE_CLAUSE + "."
    g.release.plates[0x200010] = flagged
    names.update_record(root, [{"address": "0x200010", "applied": "plate", "value": flagged, "source_pair": "x"}],
                        "2026-11-27", "sig.json")
    rows_ = names.read_record(root)
    rows_[("0x200010", "plate")]["state"] = "saved 2026-11-27"
    names.write_record(root, rows_)
    again = names.build_plan(root, reader_for(g), None, image=g.release.image)
    by = by_address(again)
    assert by["0x200000"]["plate"] == plate and by["0x200000"]["previous_name"] == "AnalysisName"
    assert by["0x200010"]["plate"] == flagged
    dry = names.apply(root, names.write_plan(root, again), g, dry_run=True)
    assert dry["would_write"] == [] and dry["stopped"] is None
