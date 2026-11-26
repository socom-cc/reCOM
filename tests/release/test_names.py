"""Stage 3 names: planning, refusals, read-back failure, idempotence, thunks, batches, against a fake bridge."""
from __future__ import annotations

import json

import pytest

import ghidra_bridge as gb
import names
import report
from elfimage import PROTOTYPE_SHA256, RELEASE_SHA256
from fake_ghidra import FakeGhidra

OWNER = "src/gamez/zTest/test_main.cpp"


@pytest.fixture(autouse=True)
def quick_settle(monkeypatch):
    monkeypatch.setattr(names, "QUIET_SECONDS", 0.0)
    monkeypatch.setattr(names, "POLL_SECONDS", 0.0)


def row(release, size, cls, proto=None, symbol=None, flags=(), evidence=("call",), classification="authored",
        library="", names_=None):
    return {
        "class": cls, "evidence": list(evidence), "flags": list(flags), "found_by": ["call"], "neighbour_group": "",
        "operation_similarity": 1.0, "owner_file": OWNER, "prototype_address": proto,
        "prototype_classification": classification if proto is not None else "", "prototype_library": library,
        "prototype_names": names_ if names_ is not None else ([symbol] if symbol else []), "prototype_owner": OWNER,
        "prototype_size": size if proto is not None else None, "prototype_symbol": symbol or "",
        "prototype_unsized": False, "release_address": release, "release_size": size, "shape_similarity": 1.0,
        "similarity": 1.0, "size_delta": 0 if proto is not None else None,
    }


ROWS = [
    row(0x200000, 0x20, "exact", 0x300000, "Foo__3CFoFv"),                    # named, labelled
    row(0x200020, 0x10, "deviating", 0x300020, "Bar"),                        # created, named, no label
    row(0x200030, 0x10, "new", evidence=("settled",)),                        # comment only, settled note
    row(0x200040, 0x10, "deviating", 0x300040, "Baz__3CFoFv", flags=("name-changed",)),
    row(0x200050, 0x10, "unsure", 0x300050, "Qux__3CFoFv", flags=("low-similarity",)),
    row(0x200060, 0x10, "exact", 0x300060, "One__3CFoFv"),                    # Ghidra body too long
    row(0x200070, 0x10, "exact", 0x300070, "Two__3CFoFv"),                    # inside the one above
    row(0x200080, 0x10, "exact", 0x300080, "Three__3CFoFv"),                  # no instruction at the start
    row(0x200090, 0x10, "deviating", 0x300090, "sceLib", classification="provider", library="SCE"),
    row(0x2000a0, 0x10, "deviating", 0x3000a0, "Stub__FP13C2DAnimCmdHdrPf", flags=("stubbed",)),
    row(0x2000b0, 0x10, "exact", 0x3000b0, "Jump__3CFoFv"),                   # a default thunk of 0x200000
]
PROTO_NAMES = {0x300000: "CFo::Foo", 0x300020: "Bar", 0x300040: "CFo::Baz", 0x300050: "CFo::Qux",
               0x300060: "CFo::One", 0x300070: "CFo::Two", 0x300080: "CFo::Three", 0x300090: "sceLib",
               0x3000a0: "Stub", 0x3000b0: "CFo::Jump"}
WRITES = {"create": 1, "label": 4, "name": 5, "plate": 9}


def make_root(tmp_path, rows=ROWS):
    data = {"rows": rows, "inputs": {"release": {"sha256": RELEASE_SHA256}, "prototype": {"sha256": PROTOTYPE_SHA256}},
            "settled": [{"release": 0x200030, "prototype": None, "checker": "check-t", "basis": "-", "date": "-",
                         "flags": [], "owner": "", "span": None}]}
    (tmp_path / "build/release").mkdir(parents=True)
    (tmp_path / "docs/release/notes").mkdir(parents=True)
    (tmp_path / "build/release/function-map.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "docs/release/function-map.tsv").write_text(report.write_tsv(rows), encoding="utf-8", newline="\n")
    (tmp_path / "docs/release/notes/zTest.md").write_text("checked by check-t: 0x200030 is new\n", encoding="utf-8")
    return tmp_path


def make_ghidra(**kwargs):
    g = FakeGhidra(**kwargs)
    for address, name in PROTO_NAMES.items():
        g.prototype.add(address, address + 0xF, name)
    g.prototype.functions[0x300000]["end"] = 0x30001F
    g.prototype.functions[0x300000]["noreturn"] = True
    r = g.release
    r.add(0x200000, 0x20001F)
    r.code.add(0x200020)
    r.flow_end[0x200020] = 0x20002F
    for a in (0x200030, 0x200040, 0x200050, 0x200090, 0x2000a0):
        r.add(a, a + 0xF)
    r.add(0x200060, 0x20007F)  # swallows 0x200070
    r.add(0x2000b0, 0x2000b7, thunk_of=0x200000)  # shows thunk_FUN_00200000 until its target is renamed
    r.functions[0x2000b0]["end"] = 0x2000bf
    r.add(0x2100f0, 0x2100ff)  # Ghidra has it, the map does not (outside the selection)
    return g


def reader_for(g):
    reader = FakeGhidra(read_only=True)
    reader.prototype, reader.release = g.prototype, g.release
    return reader


def plan_for(tmp_path, g, module="gamez/zTest", rows=ROWS):
    root = make_root(tmp_path, rows)
    plan = names.build_plan(root, reader_for(g), module)
    return root, plan, names.write_plan(root, plan)


def test_name_rules():
    proto = {"name": "CFo::Foo"}
    assert names.decide_name(ROWS[0], proto) == ("CFo::Foo", "Foo__3CFoFv", "the prototype program's name and its mangled label")
    assert names.decide_name(ROWS[1], {"name": "Bar"})[:2] == ("Bar", None)
    assert names.decide_name(ROWS[2], None)[0] is None
    assert "name-changed" in names.decide_name(ROWS[3], {"name": "CFo::Baz"})[2]
    assert names.decide_name(ROWS[4], {"name": "CFo::Qux"})[0] is None
    assert "exact pairs only" in names.decide_name(ROWS[8], {"name": "sceLib"})[2]
    assert names.decide_name(ROWS[9], {"name": "Stub"})[0] == "Stub"
    assert names.decide_name(ROWS[0], {"name": "FUN_00300000"})[0] is None


def test_plan(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    by = {e["address"]: e for e in plan["entries"]}
    assert by["0x200000"]["function"] == "exists" and by["0x200000"]["name"] == "CFo::Foo"
    assert by["0x200000"]["label"] == "Foo__3CFoFv" and by["0x200000"]["prototype"]["noreturn"] is True
    assert "no-return: prototype True, release False" in by["0x200000"]["differences"]
    assert by["0x200020"]["function"] == "create" and by["0x200020"]["label"] is None
    assert by["0x200030"]["name"] is None and "settled: docs/release/notes/zTest.md" in by["0x200030"]["plate"]
    assert by["0x200040"]["name"] is None and "prototype name CFo::Baz not applied" in by["0x200040"]["plate"]
    assert by["0x200050"]["name"] is None
    assert by["0x200060"]["function"] == "boundary" and by["0x200060"]["boundary"]["delta"] == 0x10
    assert by["0x200070"]["function"] == "inside" and by["0x200070"]["plate"] is None
    assert by["0x200080"]["function"] == "no-instruction"
    assert by["0x200090"]["name"] is None
    thunk = by["0x2000b0"]
    assert thunk["live"]["thunk_target"] == "0x200000" and thunk["live"]["default_thunk"] is True
    assert thunk["name"] == "CFo::Jump" and thunk["previous_name"] is None and "Ghidra thunk of 0x200000" in thunk["plate"]
    assert all(e["plate"].startswith(names.PLATE_PREFIX) for e in plan["entries"] if e["plate"])
    text = path.read_text(encoding="utf-8")
    assert str(tmp_path) not in text and ":\\" not in text and "executable_path" not in text
    assert names.canonical(names.build_plan(root, reader_for(g), "gamez/zTest")) == text  # deterministic


def test_plan_reports_ghidra_only_and_collisions(tmp_path):
    g = make_ghidra()
    g.release.functions[0x2100f0]["own"] = "CFo::Foo"  # one holder in the prototype, two in the release
    _, plan, _ = plan_for(tmp_path, g, module=None)
    assert [x["address"] for x in plan["ghidra_only"]] == ["0x2100f0"]
    assert plan["collisions"] and plan["collisions"][0]["name"] == "CFo::Foo"
    assert {e["address"]: e["name"] for e in plan["entries"]}["0x200000"] is None


def test_create_label_on_a_default_name_renames_the_function():
    # The Ghidra behaviour the order guards against, as the fake reproduces it.
    g = make_ghidra()
    g.write("create_label", gb.RELEASE_PROGRAM, address="0x200000", name="Foo__3CFoFv")
    assert g.release.shown(0x200000) == "Foo__3CFoFv" and g.release.labels.get(0x200000) == []
    g.write("rename_function_by_address", gb.RELEASE_PROGRAM, function_address="0x200040", new_name="X",
            strict_mode="off")
    g.write("create_label", gb.RELEASE_PROGRAM, address="0x200040", name="x_label")
    assert g.release.shown(0x200040) == "X" and g.release.labels[0x200040] == ["x_label"]


def test_apply_renames_before_labelling_and_is_idempotent(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] is None and result["saved"] is False and result["side_effects"] == []
    assert result["counts"] == WRITES
    r = g.release
    assert r.shown(0x200000) == "CFo::Foo" and r.labels[0x200000] == ["Foo__3CFoFv"]
    assert r.shown(0x2000b0) == "CFo::Jump" and r.labels[0x2000b0] == ["Jump__3CFoFv"]
    assert r.shown(0x200020) == "Bar" and r.functions[0x200020]["end"] == 0x20002F
    assert r.shown(0x200040) == "FUN_00200040"  # name-changed: comment only
    assert r.functions[0x200060]["end"] == 0x20007F  # boundary differences are not fixed
    endpoints = [s["endpoint"] for s in result["sent"]]
    assert endpoints.index("rename_function_by_address") < endpoints.index("create_label")
    assert set(endpoints) <= gb.WRITES and all(s["program"] == gb.RELEASE_PATH for s in result["sent"])
    assert not any("save" in e for _, e in g.requests)
    record = (root / names.RECORD).read_text(encoding="utf-8").splitlines()
    assert record[0] == "\t".join(names.RECORD_COLUMNS) and len(record) == 1 + sum(WRITES.values())
    assert ("0x200000\tname\tCFo::Foo\t0x300000 Foo__3CFoFv (exact)\t2026-11-26\tunsaved "
            + result["report"]) in record
    # the record holds unsaved rows: no new apply until they are confirmed
    with pytest.raises(names.Refused, match="unsaved"):
        names.apply(root, path, g, dry_run=False)
    names.confirm_saved(root, root / names.OUT / result["report"], g, today="2026-11-27")
    saved = (root / names.RECORD).read_text(encoding="utf-8")
    assert "unsaved" not in saved and "\tsaved 2026-11-27" in saved
    sent = len(g.sent)
    again = names.apply(root, path, g, dry_run=False, today="2026-11-28")
    assert again["stopped"] is None and again["written"] == [] and len(g.sent) == sent
    assert (root / names.RECORD).read_text(encoding="utf-8") == saved


def test_dry_run_sends_nothing(tmp_path):
    g = make_ghidra(read_only=True)
    root, plan, path = plan_for(tmp_path, g)
    result = names.apply(root, path, g, dry_run=True)
    assert g.sent == [] and not any(m == "POST" for m, _ in g.requests)
    assert result["counts"] == WRITES
    assert not (root / names.RECORD).exists()


def test_read_back_failure_stops_and_reports_every_write_sent(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.ignore_renames = True
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] and "rename 0x200000 read back" in result["stopped"]
    assert result["written"] == [] and not (root / names.RECORD).exists()
    assert [(s["endpoint"], s["response"]["status"]) for s in result["sent"]] == [
        ("rename_function_by_address", "success")]
    saved = json.loads((root / names.OUT / result["report"]).read_text(encoding="utf-8"))
    assert saved["sent"] == result["sent"]


def test_batches_stop_cleanly_and_unsaved_rows_can_be_discarded(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    first = names.apply(root, path, g, dry_run=False, today="2026-11-26", batch=2)
    assert first["batch_full"] and first["entries_changed"] == 2 and first["stopped"] is None
    assert {w["address"] for w in first["written"]} == {"0x200000", "0x200020"}
    # the program is closed without saving: the changes are gone, so the rows may be dropped
    fresh = make_ghidra()
    with pytest.raises(names.Refused, match="still in the program"):
        names.discard_unsaved(root, root / names.OUT / first["report"], g)
    names.discard_unsaved(root, root / names.OUT / first["report"], fresh)
    assert (root / names.RECORD).read_text(encoding="utf-8").count("\n") == 1
    # and a save cannot be confirmed for changes the program does not hold
    names.update_record(root, first["written"], "2026-11-26", first["report"])
    with pytest.raises(names.Refused, match="do not read back"):
        names.confirm_saved(root, root / names.OUT / first["report"], fresh)


def test_side_effects_of_analysis_are_reported(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.analysis_creates[0x200020] = [0x2200f0]
    g.analysis_names[0x200020] = "FidName"
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] is None
    changes = {(e["address"], e["change"]) for e in result["side_effects"]}
    assert ("0x2200f0", "appeared") in changes and ("0x200020", "named by analysis") in changes
    assert g.release.shown(0x200020) == "Bar"  # the planned name replaces Function ID's


def test_refusals(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    assert names.main(["--root", str(root), "--apply", str(path)]) == 2  # no --yes
    with pytest.raises(SystemExit):
        names.main(["--root", str(root), "--plan", "gamez/zTest", "--all"])
    with pytest.raises(SystemExit):
        names.main(["--root", str(root), "--plan"])
    with pytest.raises(gb.WriteRefused):
        g.write("rename_function_by_address", gb.PROTOTYPE_PROGRAM, function_address="0x300000", new_name="x")
    with pytest.raises(gb.WriteRefused):
        FakeGhidra(read_only=True).write("set_comment", gb.RELEASE_PROGRAM, address="0x200000", comment="x")
    with pytest.raises(gb.WriteRefused):
        g.write("save_program", gb.RELEASE_PROGRAM)
    with pytest.raises(gb.BridgeError):
        g.get("save_program", gb.RELEASE_PROGRAM)
    with pytest.raises(gb.BridgeError):
        g.get("get_function_by_address", None, address="0x200000")
    other = dict(plan, program=gb.PROTOTYPE_PROGRAM)
    (tmp_path / "other.json").write_text(names.canonical(other), encoding="utf-8")
    with pytest.raises(names.Refused, match="writes go to"):
        names.apply(root, tmp_path / "other.json", g, dry_run=True)
    edited = json.loads(path.read_text(encoding="utf-8"))
    edited["entries"][0]["name"] = "Something::Else"
    (tmp_path / "edited.json").write_text(names.canonical(edited), encoding="utf-8")
    with pytest.raises(names.Refused, match="plan_sha256"):
        names.apply(root, tmp_path / "edited.json", g, dry_run=True)
    wrong = make_ghidra(release_sha="0" * 64)
    with pytest.raises(names.Refused, match="Executable SHA256"):
        names.apply(root, path, wrong, dry_run=False)
    crowded = make_ghidra()
    crowded.extra_programs.append({"name": "other.elf", "path": "/other.elf"})
    with pytest.raises(names.Refused, match="open programs"):
        names.apply(root, path, crowded, dry_run=False)
    busy = make_ghidra()
    busy.release.analyzing = True
    with pytest.raises(names.Refused, match="analysis"):
        names.apply(root, path, busy, dry_run=False)
    assert wrong.sent == crowded.sent == busy.sent == []
    # a plan made from another map
    (root / "docs/release/function-map.tsv").write_text(report.write_tsv(ROWS[:3]), encoding="utf-8")
    with pytest.raises(names.Refused, match="another"):
        names.apply(root, path, g, dry_run=True)


def test_stale_map_is_refused(tmp_path):
    root = make_root(tmp_path)
    (root / "docs/release/function-map.tsv").write_text("release_address\n", encoding="utf-8")
    with pytest.raises(names.Refused, match="does not reproduce"):
        names.load_map(root)


def test_state_change_since_the_plan_stops_before_any_write(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.functions[0x200000]["own"] = "SomeoneElse"
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] and "replan" in result["stopped"]
    assert result["written"] == [] and result["sent"] == []


def test_shared_names_read_labels_by_address_and_foreign_plates_are_kept(tmp_path):
    rows = [row(0x200000, 0x10, "exact", 0x300000, "Fetch__1A"), row(0x200010, 0x10, "exact", 0x300010, "Fetch__1B"),
            row(0x200020, 0x10, "exact", 0x300020, "Foo__3CFoFv")]
    g = FakeGhidra()
    for a in (0x300000, 0x300010):
        g.prototype.add(a, a + 0xF, "A::Fetch")  # the prototype holds the name twice: no collision
    g.prototype.add(0x300020, 0x30002F, "CFo::Foo")
    for a in (0x200000, 0x200010, 0x200020):
        g.release.add(a, a + 0xF)
    g.release.plates[0x200020] = "a comment someone wrote"
    root, plan, path = plan_for(tmp_path, g, module=None, rows=rows)
    first = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert first["stopped"] is None and first["skipped"] == [
        {"address": "0x200020", "reason": "a plate comment not written by this tool"}]
    assert g.release.plates[0x200020] == "a comment someone wrote"
    assert [g.release.shown(a) for a in (0x200000, 0x200010)] == ["A::Fetch", "A::Fetch"]
    assert g.release.labels[0x200010] == ["Fetch__1B"]  # read back by address, not by the shared name
    assert ("GET", "get_function_documentation") in g.requests
    names.confirm_saved(root, root / names.OUT / first["report"], g)
    sent = len(g.sent)
    second = names.apply(root, path, g, dry_run=False, today="2026-11-27")
    assert second["stopped"] is None and second["written"] == [] and len(g.sent) == sent


def test_get_values_with_specials_are_encoded_twice():
    g = make_ghidra()
    g.release.add(0x220000, 0x22000F, "CFo::operator=")
    g.release.labels[0x220000] = ["__as__3CFoFRC3CFo"]
    assert names.read_labels(g, "CFo::operator=") == [(0x220000, "__as__3CFoFRC3CFo")]
