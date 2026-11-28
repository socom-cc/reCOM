"""Stage 3 globals: the plan's decisions, the apply, its stops and the record, against a fake bridge."""
from __future__ import annotations

import json
import struct

import pytest

import elfimage
import ghidra_bridge as gb
import globals as gl
import names
from fake_globals import FakeGlobals

HEADER = ("release_address", "release_size", "prototype_address", "prototype_size", "prototype_symbol",
          "prototype_section", "release_section", "class", "evidence", "witnesses", "flags", "withhold", "owner_file")
OWNER = "src/gamez/zTest/ztest.cpp"


def maprow(release, size, proto, psize, symbol, cls="exact", evidence="operand-exact:1", flags="-", withhold="-"):
    return {"release_address": hex(release) if release is not None else "-", "release_size": str(size),
            "prototype_address": hex(proto), "prototype_size": str(psize), "prototype_symbol": symbol,
            "prototype_section": ".data", "release_section": ".data", "class": cls, "evidence": evidence,
            "witnesses": "1", "flags": flags, "withhold": withhold, "owner_file": OWNER}


ROWS = [
    maprow(0x400000, 4, 0x300000, 4, "m_Count__4CFoo"),             # two labels, a type, a comment
    maprow(0x400010, 4, 0x300010, 4, "@123"),                       # a literal: no label; a char * type
    maprow(0x400020, 4, 0x300020, 4, "-"),                          # anonymous; a placeholder type
    maprow(0x400024, 4, 0x300024, 4, "g_ptr"),                      # a pointer into undefined bytes
    maprow(0x400030, 4, 0x300030, 4, "g_scalar"),                   # analysis undefined4 there: step C
    maprow(0x400040, 7, 0x300040, 8, "@200"),                       # the string is there already
    maprow(0x400050, "4..8", 0x300050, 4, "g_dev", "deviating", "operand-aligned:1", "single-aligned,size-unconfirmed"),
    maprow(0x400054, 4, 0x300054, 4, "g_user"),                     # a user label is there
    maprow(0x400058, 4, 0x300058, 4, "g_shared"),                   # conflicting rows
    maprow(0x400058, 4, 0x30005c, 4, "g_twin"),
    maprow(0x400070, 4, 0x300070, 4, "g_held", withhold="single aligned witness, bytes differ"),
    maprow(0x500000, 4, 0x300080, 4, "g_bss"),                      # no memory block
    maprow(0x400104, 4, 0x300090, 4, "g_infn"),                     # inside a function
    maprow(0x400180, 4, 0x3000a0, 4, "g_ininsn"),                   # an instruction
    maprow(0x400042, 1, 0x3000b0, 1, "g_offcut"),                   # inside the string item
    maprow(0x400090, 1, 0x3000c0, 1, "g_flag"),                     # a plate not written by this tool
    maprow(0x4000a0, "-", 0x3000d0, 4, "g_unsure", "unsure", "order:1"),
    maprow(0x4000b0, 4, 0x3000d4, 4, "g_ns"),                       # a release symbol in a namespace
    maprow(0x4000c0, 8, 0x3000e0, 8, "g_pnt"),                      # a structure without pointers
    maprow(0x4000d0, 4, 0x3000f0, 4, "g_case"),                     # two types of one name, case ignored
    maprow(0x4000e0, 4, 0x300100, 4, "g_pns"),                      # a prototype symbol in a namespace
    maprow(0x4000f0, 4, 0x300110, 4, "zfoo"),                       # a release function's name
]
PROTO_TYPES = {0x300000: ("int", 4), 0x300010: ("char *", 4), 0x300020: ("undefined4", 4), 0x300024: ("char *", 4),
               0x300030: ("float", 4), 0x300040: ("string", 8), 0x300050: ("int", 4), 0x3000c0: ("uchar", 1),
               0x3000e0: ("PNT2D", 8), 0x3000f0: ("Thing", 4)}


@pytest.fixture(autouse=True)
def quick_settle(monkeypatch):
    monkeypatch.setattr(names, "QUIET_SECONDS", 0.0)
    monkeypatch.setattr(names, "POLL_SECONDS", 0.0)


def release_image():
    words = [0] * 128
    words[(0x400010 - 0x400000) // 4] = 0x400040  # the literal's pointer: a defined string
    words[(0x400024 - 0x400000) // 4] = 0x400060  # g_ptr: undefined bytes
    data = bytearray(struct.pack("<128I", *words))
    data[0x40:0x48] = b"BREACH\0\0"
    words = list(struct.unpack("<128I", bytes(data)))
    return elfimage.synthetic(words, base=0x400000)


def make_ghidra(read_only=False):
    g = FakeGlobals(read_only=read_only)
    p, r = g.prototype, g.release
    for program in (p, r):
        for path, size in (("/int", 4), ("/char *", 4), ("/float", 4), ("/uchar", 1), ("/string", None),
                           ("/undefined4", 4), ("/project/PNT2D", 8), ("/project/Thing", 4)):
            program.add_type(path, size)
        program.layouts["PNT2D"] = [(0, 4, "float"), (4, 4, "float")]
    r.add_type("/other/thing", 4)
    for row in ROWS:
        pa = int(row["prototype_address"], 16)
        if row["prototype_symbol"] not in ("-", "g_pns"):
            p.labels[pa] = [row["prototype_symbol"]]
        if pa in PROTO_TYPES:
            p.data[pa] = PROTO_TYPES[pa]
    p.labels[0x300000] = ["CFoo::m_Count", "m_Count__4CFoo"]
    p.ns_symbols[0x300100] = "Member"
    r.segments = [("SECTION4", 0x400000, 0x4001FF)]
    r.image = release_image()
    r.data = {0x400030: ("undefined4", 4), 0x400040: ("string", 7)}
    r.refs_to = {0x400000: ["From 00200000 in f [READ]"], 0x400030: ["From 00200010 in f [READ]"]}
    r.labels[0x400054] = ["UserName"]
    r.plates[0x400090] = "someone's note"
    r.ns_symbols[0x4000b0] = "Inner"
    r.add(0x400100, 0x40011F, "zfoo")
    r.code.add(0x400180)
    return g


def reader_for(g):
    reader = FakeGlobals(read_only=True)
    reader.prototype, reader.release = g.prototype, g.release
    return reader


def make_root(tmp_path, rows=ROWS):
    (tmp_path / "docs" / "release").mkdir(parents=True)
    text = "\t".join(HEADER) + "\n" + "".join("\t".join(r[c] for c in HEADER) + "\n" for r in rows)
    (tmp_path / gl.DATA_MAP).write_text(text, encoding="utf-8", newline="\n")
    return tmp_path


def plan_for(tmp_path, g):
    root = make_root(tmp_path)
    plan = gl.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image)
    return root, plan, gl.write_plan(root, plan)


def by_address(plan):
    return {(e["address"], e["symbol"]): e for e in plan["entries"]}


def entry(plan, address):
    found = [e for e in plan["entries"] if e["address"] == address]
    assert len(found) == 1, found
    return found[0]


# --- the plan ----------------------------------------------------------------------------------

def test_plan_labels_and_reasons(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    count = entry(plan, "0x400000")
    assert [(x["name"], x["kind"]) for x in count["labels"]] == [("CFoo::m_Count", gl.LABEL), ("m_Count__4CFoo", gl.MANGLED)]
    assert count["comment"]["text"] == ("Release data map: exact pair with prototype 0x300000 m_Count__4CFoo "
                                        "(evidence operand-exact:1; flags none)")
    reasons = {e["address"]: e["label_reason"] for e in plan["entries"] if e["label_reason"]}
    assert reasons["0x400010"] == "a literal (@N): no name"
    assert reasons["0x400020"].startswith("no prototype symbol")
    assert reasons["0x400054"] == "the release address already has the label UserName (not this tool's)"
    assert reasons["0x400058"].startswith("conflicting rows")
    assert reasons["0x400070"].startswith("withheld by the data map: single aligned")
    assert reasons["0x500000"].startswith("no release memory block holds 0x500000")
    assert reasons["0x400104"] == "a release function: zfoo at 0x400100"
    assert reasons["0x400180"] == "an instruction holds this address"
    assert reasons["0x400042"] == "inside the release data item string at 0x400040 (an offcut label)"
    assert reasons["0x4000b0"].startswith("the release primary symbol Inner")
    assert reasons["0x4000e0"].startswith("the prototype's symbol Member")
    assert reasons["0x4000f0"] == "the name zfoo is a release function's name"
    dev = entry(plan, "0x400050")
    assert [x["name"] for x in dev["labels"]] == ["g_dev"]
    assert "flags single-aligned, size-unconfirmed" in dev["comment"]["text"]
    assert entry(plan, "0x400090")["comment_reason"] == "a plate comment not written by this tool is there"
    assert entry(plan, "0x400090")["labels"]  # the label goes anyway
    assert plan["not_named"] == {"unsure": 1}
    assert plan["summary"]["labels_planned"] == 7 and plan["summary"]["second_labels_planned"] == 1
    # deterministic, and the summary file exists
    again = gl.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image)
    assert again["plan_sha256"] == plan["plan_sha256"]
    assert path.with_suffix(".md").is_file()


def test_plan_types_and_step_c(tmp_path):
    g = make_ghidra()
    root, plan, _ = plan_for(tmp_path, g)
    assert entry(plan, "0x400000")["type"] == {"name": "int", "path": "/int", "length": 4, "references": [],
                                               "present": False}
    literal = entry(plan, "0x400010")["type"]
    assert literal["name"] == "char *" and literal["references"] == [{"from": "0x400010", "to": "0x400040"}]
    assert entry(plan, "0x400020")["type_reason"] == "placeholder type undefined4 in the prototype (nothing to carry)"
    assert entry(plan, "0x400024")["type_reason"].startswith("the pointer at +0 holds 0x400060, undefined bytes")
    scalar = entry(plan, "0x400030")
    assert scalar["type_reason"] == "analysis defined data in the range (step C)"
    assert scalar["step_c"]["items"] == [{"address": "0x400030", "length": 4, "type": "undefined4",
                                          "kind": "untyped scalar", "references": 0, "crosses": False}]
    assert entry(plan, "0x400040")["type"]["present"] is True  # the string, 7 bytes (8 with padding in the prototype)
    assert entry(plan, "0x400050")["type_reason"] == "release size not confirmed (4..8)"
    assert entry(plan, "0x400090")["type"]["name"] == "uchar"
    assert entry(plan, "0x4000c0")["type"]["path"] == "/project/PNT2D"
    assert "case ignored" in entry(plan, "0x4000d0")["type_reason"]
    s = plan["summary"]
    assert s["types_planned"] == 4 and s["types_present"] == 1 and s["references_predicted"] == 1
    assert s["step_c"]["objects"] == 1 and s["step_c"]["items_by_kind"] == {"untyped scalar": 1}


def test_type_resolution_rules():
    table = {"int": [("/int", 4)], "CFoo": [("/project/CFoo", 4)], "cfoo": [("/x/cfoo", 4)],
             "Bar": [("/project/Bar", 4)], "long": [("/project/long", 8)], "Baz": [("/Baz", 4), ("/project/Baz", 4)]}
    assert gl.resolves_to("int", "/int", table) is None
    assert "case ignored" in gl.resolves_to("CFoo", "/project/CFoo", table)
    assert gl.resolves_to("Bar", "/project/Bar", table) is None
    assert "built-in" in gl.resolves_to("long", "/project/long", table)
    assert "root type /Baz" in gl.resolves_to("Baz", "/project/Baz", table)
    assert gl.PLACEHOLDER.match("undefined1[12]") and gl.PLACEHOLDER.match("pointer") and gl.PLACEHOLDER.match("undefined *")
    assert not gl.PLACEHOLDER.match("char *") and not gl.PLACEHOLDER.match("float")


def test_the_client_never_sends_a_clearing_write():
    g = FakeGlobals()
    with pytest.raises(gb.WriteRefused):
        g.write("apply_data_type", gb.RELEASE_PROGRAM, address="0x400000", type_name="int")
    with pytest.raises(gb.WriteRefused):
        g.write("apply_data_type", gb.RELEASE_PROGRAM, address="0x400000", type_name="int", clear_existing=True)
    for endpoint in ("set_global", "apply_data_classification", "rename_data", "save_program"):
        with pytest.raises(gb.WriteRefused):
            g.write(endpoint, gb.RELEASE_PROGRAM, address="0x400000")
    with pytest.raises(gb.WriteRefused):
        g.write("create_label", gb.PROTOTYPE_PROGRAM, address="0x400000", name="x")
    assert g.sent == []


# --- the apply ---------------------------------------------------------------------------------

def test_dry_run_sends_nothing(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    dry = FakeGlobals(read_only=True)
    dry.prototype, dry.release = g.prototype, g.release
    result = gl.apply(root, path, dry, dry_run=True)
    assert result["stopped"] is None and dry.sent == []
    first = [(w["endpoint"], w["applied"]) for w in result["would_write"] if w["address"] == "0x400000"]
    assert first == [("apply_data_type", gl.TYPE), ("create_label", gl.LABEL), ("create_label", gl.MANGLED),
                     ("set_comment", gl.COMMENT)]
    body = next(w["body"] for w in result["would_write"] if w["endpoint"] == "apply_data_type")
    assert body["clear_existing"] is False
    assert result["counts"] == {gl.COMMENT: 6, gl.TYPE: 4, gl.LABEL: 7, gl.MANGLED: 1}


def test_apply_reads_back_records_and_second_run_changes_nothing(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    r = g.release
    result = gl.apply(root, path, g, dry_run=False, today="2026-11-27")
    assert result["stopped"] is None, result["stopped"]
    assert r.labels[0x400000] == ["CFoo::m_Count", "m_Count__4CFoo"]  # the readable name is primary
    assert r.data[0x400000] == ("int", 4) and r.data[0x400010] == ("char *", 4)
    assert r.refs_from[0x400010] == [(0x400040, "DATA")]
    assert result["references_made"] == [{"from": "0x400010", "to": "0x400040", "kinds": ["DATA"]}]
    assert r.plates[0x400090] == "someone's note"  # not replaced
    assert r.plates[0x400000].startswith(gl.COMMENT_PREFIX)
    assert 0x400054 not in r.data and r.labels[0x400054] == ["UserName"]
    assert result["checks"] >= 5  # after each of the four types and at the end
    rows = names.read_record(root)
    assert rows[("0x400000", gl.TYPE)]["value"] == "int (/int, 4 bytes)"
    assert rows[("0x400000", gl.MANGLED)]["state"] == f"unsaved {result['report']}"
    assert len(rows) == len(result["written"]) == 18
    with pytest.raises(names.Refused):  # unsaved rows block another apply
        gl.apply(root, path, g, dry_run=False)
    done = gl.confirm_saved(root, root / gl.OUT / result["report"], reader_for(g), today="2026-11-28")
    assert done["confirmed"] == 18
    assert all(row["state"] == "saved 2026-11-28" for row in names.read_record(root).values())
    sent = len(g.sent)
    again = gl.apply(root, path, g, dry_run=False)
    assert again["stopped"] is None and len(g.sent) == sent and again["written"] == []
    assert again["unchanged"] == {"comment": 6, "label": 8, "type": 5}  # the string was there already


def test_batch_and_only(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    result = gl.apply(root, path, g, dry_run=False, batch=1)
    assert result["batch_full"] and result["entries_changed"] == 1
    assert {w["address"] for w in result["written"]} == {"0x400000"}
    gl.confirm_saved(root, root / gl.OUT / result["report"], reader_for(g))
    pilot = gl.apply(root, path, g, dry_run=False, only=frozenset({"0x400090"}))
    assert {w["address"] for w in pilot["written"]} == {"0x400090"}
    assert [w["applied"] for w in pilot["written"]] == [gl.TYPE, gl.LABEL]  # its plate is not this tool's


def test_only_unknown_entry_stops_before(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    result = gl.apply(root, path, g, dry_run=False, only=frozenset({"0x400999"}))
    assert result["stop_kind"] == "StopBefore" and g.sent == []


# --- the stops ---------------------------------------------------------------------------------

def test_stop_before_when_a_label_appeared(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.labels[0x400000] = ["Someone"]
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopBefore" and "has the labels ['Someone']" in result["stopped"]
    assert g.sent == [] and result["what_to_do"] == gl.AFTER_NOTHING


def test_stop_before_when_data_appeared_in_a_type_range(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.data[0x400002] = ("undefined2", 2)
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopBefore" and "undefined2 at 0x400002" in result["stopped"]
    assert g.sent == []


def test_stop_after_a_refused_type(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.refuse_types.add(0x400000)  # createData throws: a clean refusal, nothing created
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "Conflicting data" in result["stopped"]
    assert 0x400000 not in g.release.data and result["written"] == []
    assert [a["applied"] for a in result["attempted"]] == [gl.TYPE]
    assert gl.discard_unsaved(root, root / gl.OUT / result["report"], reader_for(g))["discarded"] == 0


def test_stop_after_a_label_that_is_not_primary(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)

    def secondary(p, name):  # an analysis label already primary there (not listed)
        p.labels.setdefault(0x400000, []).insert(0, "ANALYSIS_NAME") if not p.labels.get(0x400000) else None
        p.labels[0x400000].append(name)
        return {"status": "success", "message": "Created label"}

    g.label_effects[0x400000] = secondary
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "primary symbol reads 'ANALYSIS_NAME'" in result["stopped"]
    assert result["written"] == [w for w in result["written"] if w["applied"] == gl.TYPE]
    rows = names.read_record(root)
    assert set(rows) == {("0x400000", gl.TYPE)}
    # confirm after a save records the label sent before the stop, since the program holds it
    done = gl.confirm_saved(root, root / gl.OUT / result["report"], reader_for(g))
    assert done["recorded_after_a_stop"] == 1


def test_analysis_stop_when_data_is_defined_elsewhere(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.data_effects[0x400010] = lambda p: p.data.__setitem__(0x400160, ("string", 4))
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "AnalysisStop"
    assert result["analysis_changes"] == [{"data": ["0x400160", 4, "string"], "change": "added",
                                           "seen": "after the type at 0x400010"}]
    assert result["what_to_do"] == gl.AFTER_ANALYSIS
    # the writes before the stop read back and are recorded
    assert ("0x400010", gl.TYPE) in names.read_record(root)


def test_analysis_stop_when_a_bookmark_or_function_appears_at_the_end(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.label_effects[0x400090] = lambda p, name: (p.bookmarks.append((0x400060, "Analysis", "Found Code", "x")), None)[1]
    result = gl.apply(root, path, g, dry_run=False, check_every=1)
    assert result["stop_kind"] == "AnalysisStop"
    assert result["analysis_changes"][0]["bookmark"][0] == "0x400060"
    assert result["analysis_changes"][0]["seen"] == "after 0x400090"


def test_stop_before_when_the_comment_changed(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.plates[0x400000] = "a new note"
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopBefore" and "the plate comment is 'a new note' now" in result["stopped"]
    # the type and both labels of that entry were written before the comment check
    assert [w["applied"] for w in result["written"]] == [gl.TYPE, gl.LABEL, gl.MANGLED]


def test_plan_refused_when_edited_or_made_from_another_map(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["entries"][0]["labels"][0]["name"] = "Other"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(names.Refused, match="plan_sha256"):
        gl.apply(root, path, g, dry_run=True)
    gl.write_plan(root, plan)
    (root / gl.DATA_MAP).write_text((root / gl.DATA_MAP).read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(names.Refused, match="another"):
        gl.apply(root, path, g, dry_run=True)


def test_discard_refuses_while_the_program_holds_a_write(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    result = gl.apply(root, path, g, dry_run=False, only=frozenset({"0x400090"}))
    report = root / gl.OUT / result["report"]
    with pytest.raises(names.Refused, match="still in the program"):
        gl.discard_unsaved(root, report, reader_for(g))
    # after a close without saving the program no longer holds them
    del g.release.data[0x400090]
    g.release.labels.pop(0x400090)
    g.release.plates[0x400090] = "someone's note"
    assert gl.discard_unsaved(root, report, reader_for(g))["discarded"] == 2
    assert names.read_record(root) == {}


def test_stop_before_when_a_function_now_holds_the_address(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.release.add(0x400000, 0x40000F, "FUN_00400000")
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopBefore" and "holds code now" in result["stopped"] and g.sent == []


def test_stop_before_when_a_pointer_target_became_undefined(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    del g.release.data[0x400040]  # the string the literal's pointer names is gone
    result = gl.apply(root, path, g, dry_run=False, only=frozenset({"0x400010"}))
    assert result["stop_kind"] == "StopBefore" and "the pointer target 0x400040 is undefined bytes" in result["stopped"]
    assert g.sent == []


def test_stop_after_a_type_that_reads_back_otherwise(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.data_effects[0x400000] = lambda p: p.data.__setitem__(0x400000, ("int", 8))
    result = gl.apply(root, path, g, dry_run=False)
    assert result["stop_kind"] == "StopAfter" and "read back 'int' 8" in result["stopped"]
    assert result["what_to_do"] == gl.AFTER_A_WRITE and result["written"] == []


def test_stop_after_a_reference_that_is_not_made(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    g.data_effects[0x400010] = lambda p: p.refs_from.pop(0x400010)
    result = gl.apply(root, path, g, dry_run=False, only=frozenset({"0x400010"}))
    assert result["stop_kind"] == "StopAfter" and "no reference from 0x400010 to 0x400040" in result["stopped"]
