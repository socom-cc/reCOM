"""Stage 3 names: planning, refusals, read-back failure, idempotence, thunks, batches, against a fake bridge."""
from __future__ import annotations

import json

import pytest

import createflow
import elfimage
import ghidra_bridge as gb
import names
import report
from elfimage import PROTOTYPE_SHA256, RELEASE_SHA256
from asm import JR_RA, NOP, j
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
    row(0x200090, 0x10, "deviating", 0x300090, "sceLib", classification="provider", library=""),   # library unknown
    row(0x2000a0, 0x10, "deviating", 0x3000a0, "Stub__FP13C2DAnimCmdHdrPf", flags=("stubbed",)),
    row(0x2000b0, 0x10, "exact", 0x3000b0, "Jump__3CFoFv"),                   # a default thunk of 0x200000
]
PROTO_NAMES = {0x300000: "CFo::Foo", 0x300020: "Bar", 0x300040: "CFo::Baz", 0x300050: "CFo::Qux",
               0x300060: "CFo::One", 0x300070: "CFo::Two", 0x300080: "CFo::Three", 0x300090: "sceLib",
               0x3000a0: "Stub", 0x3000b0: "CFo::Jump"}
WRITES = {"create": 1, "label": 4, "name": 5, "plate": 9}


BASE, TOP = 0x200000, 0x210400
SYSCALL, LI_V1 = 0x0000000C, (9 << 26) | (3 << 16) | 0x23  # syscall; addiu v1, zero, 0x23


def image_for(rows, special=None):
    """The release image: nops, each map function ending in jr ra; nop, plus ``special`` words."""

    words = {a: NOP for a in range(BASE, TOP, 4)}
    for r in rows:
        words[r["release_address"] + r["release_size"] - 8] = JR_RA
    words.update(special or {})
    return elfimage.synthetic([words[a] for a in range(BASE, TOP, 4)], base=BASE)


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
    r.image = image_for(ROWS)
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
    plan = names.build_plan(root, reader_for(g), module, image=g.release.image)
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


def test_c_library_pairs_are_named_by_their_place():
    def lib(release, cls, proto, symbol, library="newlib", evidence=("call-deviating",), flags=()):
        return row(release, 0x10, cls, proto, symbol, classification="provider", library=library,
                   evidence=evidence, flags=flags)

    rows = [
        lib(0x400000, "exact", 0x500010, "abort"),
        lib(0x400010, "deviating", 0x500020, "atof"),          # between the same neighbours: named
        lib(0x400020, "unsure", 0x500030, "_calloc_r"),        # unsure, but in place: named
        lib(0x400030, "deviating", 0x500000, "exit", evidence=("call",)),   # moved, its callers decide: named
        lib(0x400040, "unsure", 0x500008, "quorem"),           # unsure and out of place: not named
        lib(0x400050, "deviating", 0x500004, "_dtoa_r"),       # out of place, no caller evidence: not named
        lib(0x400060, "exact", 0x500040, "fclose"),
        lib(0x400070, "deviating", 0x500050, "sceGsSyncV", library="SCE"),  # another library: its own order
        lib(0x400080, "deviating", 0x500060, "mystery", library=""),        # library unknown: exact pairs only
    ]
    placed = names.library_place(rows)
    assert placed == {0x400000, 0x400010, 0x400020, 0x400060, 0x400070}

    def decide(index):
        return names.decide_name(rows[index], {"name": rows[index]["prototype_symbol"]}, placed)

    name, label, why = decide(1)
    assert (name, label) == ("atof", None) and "same place" in why and "(deviating)" in why
    name, _, why = decide(2)
    assert name == "_calloc_r" and "(unsure)" in why
    name, _, why = decide(3)
    assert name == "exit" and "callers decide" in why
    assert decide(4) == (None, None, "unsure pair: the evidence does not settle it")
    assert decide(5)[0] is None and "exact pairs only" in decide(5)[2]
    assert decide(7)[0] == "sceGsSyncV" and "same place" in decide(7)[2]
    assert decide(8)[0] is None and "exact pairs only" in decide(8)[2]
    # Without the place (an old caller), the rule is the old one.
    assert names.decide_name(rows[1], {"name": "atof"})[0] is None
    # The plate of a function named this way says so.
    entry = {"name": "atof", "name_reason": why and decide(1)[2], "prototype": {"name": "atof"}}
    assert "named although the pair is not exact: it stands in the same place" in names.plate_text(rows[1], entry, None)


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
    assert names.canonical(names.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image)) == text  # deterministic


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


def test_changes_analysis_makes_after_a_create_stop_the_run(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.analysis_creates[0x200020] = [0x2200f0]
    g.analysis_names[0x200020] = "FidName"
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert "nothing has to be removed by hand" in result["stopped"]
    changes = {(e["address"], e["change"]) for e in result["analysis_changes"]}
    assert changes == {("0x2200f0", "appeared"), ("0x200020", "named by analysis")}
    assert [w["applied"] for w in result["written"] if w["address"] == "0x200020"] == ["create"]
    assert result["remove_by_hand"] == []


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
    g.release.image = image_for(rows)
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


# --- creates whose body CreateFunctionCmd would not make the map extent -------------------------

CREATE_ROWS = [
    row(0x200100, 0x08, "exact", 0x300100, "_root"),               # addiu; syscall: falls into 0x200108
    row(0x200108, 0x10, "exact", 0x300108, "After__1AFv"),         # a create: must exist first
    row(0x200200, 0x08, "exact", 0x300200, "Fall__1AFv"),          # falls into 0x200208, no function there
    row(0x200208, 0x10, "exact", 0x300208, "NoCode__1AFv"),        # no instruction in Ghidra
    row(0x200300, 0x08, "exact", 0x300300, "Pad__1AFv"),           # falls through padding into 0x200310
    row(0x200310, 0x10, "exact", 0x300310, "Next__1AFv"),          # exists
    row(0x200400, 0x08, "exact", 0x300400, "Tail__1AFv"),          # j 0x200500 (a create): after it
    row(0x200500, 0x10, "exact", 0x300500, "Target__1AFv"),
    row(0x200600, 0x10, "exact", 0x300600, "Plain__1AFv"),         # safe
]
CREATE_SPECIAL = {0x200100: LI_V1, 0x200104: SYSCALL, 0x200200: LI_V1, 0x200204: SYSCALL,
                  0x200208: LI_V1, 0x200300: LI_V1, 0x200304: SYSCALL, 0x200400: j(0x200500), 0x200404: NOP}


def create_ghidra():
    g = FakeGhidra()
    for r in CREATE_ROWS:
        g.prototype.add(r["prototype_address"], r["prototype_address"] + r["release_size"] - 1,
                        "A::" + r["prototype_symbol"].split("__")[0])
    g.release.image = image_for(CREATE_ROWS, CREATE_SPECIAL)
    for r in CREATE_ROWS:
        if r["release_address"] not in (0x200208, 0x200310):
            g.release.code.add(r["release_address"])
    g.release.add(0x200310, 0x20031F)
    return g


def test_flow_prediction_follows_ghidra():
    img = image_for(CREATE_ROWS, CREATE_SPECIAL)
    # _root without its successor runs on to the next return: the defect seen at 0x1401d0
    alone = createflow.predict(img.word, img.contains, 0x200100, set())
    assert max(alone.body) == 0x200114
    stopped = createflow.predict(img.word, img.contains, 0x200100, {0x200108})
    assert stopped.body == {0x200100, 0x200104} and stopped.stops == {0x200108}
    tail = createflow.predict(img.word, img.contains, 0x200400, {0x200500})
    assert tail.body == {0x200400, 0x200404} and tail.stops == {0x200500}


def test_creates_are_classified_ordered_and_withheld(tmp_path):
    g = create_ghidra()
    _, plan, _ = plan_for(tmp_path, g, module=None, rows=CREATE_ROWS)
    by = {e["address"]: e for e in plan["entries"]}
    assert {k: by["0x200100"]["create"][k] for k in ("safety", "after")} == {"safety": "ordered", "after": ["0x200108"]}
    assert by["0x200108"]["create"]["first"] is True and by["0x200100"]["create"]["first"] is False
    assert by["0x200108"]["create"]["safety"] == "safe"
    assert by["0x200200"]["function"] == "create-withheld"
    assert "falls through past its end" in by["0x200200"]["create"]["reason"]
    assert by["0x200208"]["function"] == "no-instruction"
    assert by["0x200300"]["function"] == "create-withheld"  # the padding would join the body
    assert "padding" in by["0x200300"]["create"]["reason"]
    assert {k: by["0x200400"]["create"][k] for k in ("safety", "after", "thunk_of")} == {
        "safety": "ordered", "after": ["0x200500"], "thunk_of": "0x200500"}
    assert by["0x200600"]["create"]["safety"] == "safe"
    counts = plan["summary"]["creates"]
    assert (counts["safe"], counts["ordered"], counts["withheld"], counts["withheld_bytes"]) == (3, 2, 2, 16)
    assert by["0x200200"]["plate"] is None and by["0x200200"]["name"] is None


def test_apply_creates_successors_first_and_never_sends_a_withheld_create(tmp_path):
    g = create_ghidra()
    root, plan, path = plan_for(tmp_path, g, module=None, rows=CREATE_ROWS)
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] is None and result["side_effects"] == []
    creates = [s["body"]["address"] for s in result["sent"] if s["endpoint"] == "create_function"]
    assert creates.index("0x200108") < creates.index("0x200100")
    assert creates.index("0x200500") < creates.index("0x200400")
    assert "0x200200" not in creates and "0x200300" not in creates
    r = g.release
    assert {a: r.functions[a]["end"] for a in (0x200100, 0x200108, 0x200400, 0x200500, 0x200600)} == {
        0x200100: 0x200107, 0x200108: 0x200117, 0x200400: 0x200407, 0x200500: 0x20050F, 0x200600: 0x20060F}
    # the old address order would have given _root its successor's body
    old = create_ghidra()
    old.write("create_function", gb.RELEASE_PROGRAM, address="0x200100", disassemble_first=False)
    assert old.release.functions[0x200100]["end"] == 0x200117


def test_a_wrong_extent_names_the_function_to_remove_and_the_record_copes(tmp_path):
    g = create_ghidra()
    root, plan, path = plan_for(tmp_path, g, module=None, rows=CREATE_ROWS)
    g.release.flow_end[0x200108] = 0x20011F  # Ghidra does something the prediction did not
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert "remove the function FUN_00200108 at 0x200108 by hand" in result["stopped"]
    assert result["remove_by_hand"] == [{"address": "0x200108", "name": "FUN_00200108",
                                         "body": "0x200108..0x20011f", "planned": "0x200108..0x200117"}]
    assert [s["body"]["address"] for s in result["sent"]] == ["0x200108"]
    assert result["written"] == [] and not (root / names.RECORD).exists()
    # the user removes it: nothing of the run is left, and a replan plans the create again
    del g.release.functions[0x200108]
    names.discard_unsaved(root, root / names.OUT / result["report"], g)
    root2 = tmp_path / "again"
    root2.mkdir()
    _, again, _ = plan_for(root2, g, module=None, rows=CREATE_ROWS)
    assert {e["address"]: e["function"] for e in again["entries"]}["0x200108"] == "create"


def test_plan_assuming_a_removal_is_refused_until_it_happened(tmp_path):
    g = create_ghidra()
    g.release.add(0x200100, 0x200117)  # the wrong function, still there
    root = make_root(tmp_path, CREATE_ROWS)
    plan = names.build_plan(root, reader_for(g), None, image=g.release.image, assumed=frozenset({0x200100}))
    by = {e["address"]: e for e in plan["entries"]}
    assert by["0x200100"]["create"]["safety"] == "ordered" and by["0x200108"]["function"] == "create"
    path = names.write_plan(root, plan)
    with pytest.raises(names.Refused, match="assumes the function at 0x200100 was removed"):
        names.apply(root, path, g, dry_run=True)
    del g.release.functions[0x200100]
    assert names.apply(root, path, g, dry_run=True)["stopped"] is None


# --- batch 1 findings: label clashes, holes and jumps, created thunks, the record ------------------

def small_ghidra(rows, special=None):
    g = FakeGhidra()
    for r in rows:
        if r["prototype_address"] is not None:
            g.prototype.add(r["prototype_address"], r["prototype_address"] + r["release_size"] - 1,
                            PROTO.get(r["prototype_address"], r["prototype_symbol"]))
    g.release.image = image_for(rows, special)
    return g


PROTO = {}


def test_a_planned_name_that_is_a_label_at_the_entry_is_not_renamed(tmp_path):
    rows = [row(0x200000, 0x10, "exact", 0x300000, "Sys2"), row(0x200010, 0x10, "exact", 0x300010, "Sys")]
    g = small_ghidra(rows)
    g.release.add(0x200000, 0x20000F, "Sys")  # the syscall analysis named it and left the label Sys2
    g.release.labels[0x200000] = ["Sys2"]
    g.release.add(0x200010, 0x20001F)
    # the refusal the plan has to foresee
    assert "already exists at this address" in g.write(
        "rename_function_by_address", gb.RELEASE_PROGRAM, function_address="0x200000", new_name="Sys2",
        strict_mode="off")["error"]
    root, plan, path = plan_for(tmp_path, g, module=None, rows=rows)
    by = {e["address"]: e for e in plan["entries"]}
    assert by["0x200000"]["label_clash"] and by["0x200000"]["name"] is None
    assert "already a label at this entry" in by["0x200000"]["plate"]
    assert plan["summary"]["renames_skipped_for_label"] == 1
    assert by["0x200010"]["name"] == "Sys"  # 0x200000 keeps Sys only because of the clash; it does not block
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] is None
    renames = [(s["body"]["function_address"], s["body"]["new_name"]) for s in result["sent"]
               if s["endpoint"] == "rename_function_by_address"]
    assert renames == [("0x200000", "Sys2"), ("0x200010", "Sys")]  # the refused demonstration, then 0x200010 only
    assert g.release.shown(0x200000) == "Sys" and g.release.labels[0x200000] == ["Sys2"]


def test_a_create_in_a_gap_of_a_body_is_withheld_and_jump_holders_are_listed(tmp_path):
    rows = [row(0x200000, 0x10, "exact", 0x300000, "F__1AFv"), row(0x200010, 0x10, "exact", 0x300010, "C__1AFv"),
            row(0x200020, 0x10, "exact", 0x300020, "T__1AFv")]
    g = small_ghidra(rows, {0x200008: j(0x200020), 0x20000c: NOP})
    g.release.add(0x200000, 0x20002F)  # F followed its jump to T; C lies in the gap
    g.release.functions[0x200000]["holes"] = [(0x200010, 0x20001F)]
    g.release.code.add(0x200010)
    _, plan, _ = plan_for(tmp_path, g, module=None, rows=rows)
    by = {e["address"]: e for e in plan["entries"]}
    assert by["0x200000"]["function"] == "boundary" and by["0x200020"]["function"] == "inside"
    assert by["0x200010"]["function"] == "create-withheld"
    assert by["0x200010"]["create"]["reason"].startswith("jump-neighbour: lies in a gap of the body of the function at 0x200000")
    assert plan["jump_holders"] == [{"function": "0x200000", "at": "0x200008", "target": "0x200020"}]
    assert plan["summary"]["creates"]["withheld_by_group"] == {"jump-neighbour": 1}


def test_a_neighbour_changed_by_analysis_stops_the_run(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)

    def follow_up(program):  # the jump turned into a call: a function at the target, the jumper cut back
        program.functions[0x200060]["end"] = 0x20006F
        program.add(0x200070, 0x20007F)

    g.analysis_effects[0x200020] = follow_up
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert isinstance(result["stopped"], str) and "nothing has to be removed by hand" in result["stopped"]
    assert {(c["address"], c["change"]) for c in result["analysis_changes"]} == {("0x200070", "appeared"),
                                                                                  ("0x200060", "hi")}
    assert result["remove_by_hand"] == []


def test_a_created_thunk_follows_its_target_and_the_label_still_reads_back(tmp_path):
    rows = [row(0x200000, 0x08, "new"), row(0x200100, 0x10, "exact", 0x300100, "T__1AFv")]
    PROTO[0x300100] = "A::T"
    g = small_ghidra(rows, {0x200000: j(0x200100), 0x200004: NOP})
    g.release.code.add(0x200000)
    g.release.add(0x200100, 0x20010F)
    root, plan, path = plan_for(tmp_path, g, module=None, rows=rows)
    by = {e["address"]: e for e in plan["entries"]}
    assert by["0x200000"]["create"]["thunk_of"] == "0x200100" and by["0x200000"]["name"] is None
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] is None and result["side_effects"] == []
    assert g.release.shown(0x200000) == "A::T" == g.release.shown(0x200100)  # the thunk shows its target's name
    assert g.release.labels[0x200100] == ["T__1AFv"]
    assert ("GET", "get_function_documentation") in g.requests  # the shared name was read by address


def test_a_write_whose_read_back_stopped_the_run_is_recorded_at_confirm(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.drop_plate_read_after_set = True
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"].startswith("plate 0x200000 read back")
    assert [w["applied"] for w in result["written"]] == ["name", "label"]
    assert [a["applied"] for a in result["attempted"]] == ["name", "label", "plate"]
    done = names.confirm_saved(root, root / names.OUT / result["report"], g, today="2026-11-27")
    assert done == {"confirmed": 2, "recorded_after_a_stop": 1, "report": result["report"]}
    record = (root / names.RECORD).read_text(encoding="utf-8")
    assert "0x200000\tplate\tRelease map:" in record and "unsaved" not in record


def test_confirm_refuses_while_a_function_to_remove_by_hand_exists(tmp_path):
    g = create_ghidra()
    root, plan, path = plan_for(tmp_path, g, module=None, rows=CREATE_ROWS)
    g.release.flow_end[0x200108] = 0x20011F
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    with pytest.raises(names.Refused, match="remove it, save, then confirm"):
        names.confirm_saved(root, root / names.OUT / result["report"], g)


def test_a_planned_create_analysis_already_made_gets_its_own_row(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.add(0x200020, 0x20002F)  # made by analysis between the plan and the apply
    result = names.apply(root, path, g, dry_run=False, today="2026-11-26")
    assert result["stopped"] is None
    assert ("0x200020", "create-by-analysis") in {(w["address"], w["applied"]) for w in result["written"]}
    assert "0x200020\tcreate-by-analysis\t0x200020-0x20002f" in (root / names.RECORD).read_text(encoding="utf-8")


def test_a_named_thunk_gets_its_target_from_the_jump():
    img = image_for([row(0x200000, 0x08, "exact", 0x300000, "X")], {0x200000: j(0x200100), 0x200004: NOP})
    assert names.image_thunk_target(img, 0x200000) == 0x200100
    assert names.image_thunk_target(img, 0x200004) is None
