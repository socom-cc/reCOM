"""Stage 3 function starts: planning every case, the apply, every stop and the record, against a fake bridge.

The fake extends ``FakeGhidra`` with what the starts tool reads and writes, modelled on the plugin
and Ghidra 12.1.4: ``disassemble_bytes`` as ``DisassembleCommand`` with followFlow false (fall-
through only, existing identical instructions end a run, data or bytes that do not decode leave a
"Bad Instruction" bookmark), ``create_function`` as ``CreateFunctionCmd`` (FollowFlow over
instructions only, ``subtractBodyFromExisting``), and ``find_code_gaps``, ``list_bookmarks``,
``list_data_items`` and ``get_xrefs_to`` over that state.
"""
from __future__ import annotations

import json

import pytest

import createflow
import elfimage
import ghidra_bridge as gb
import mips
import names
import starts
from asm import JR_RA, NOP, A0, V0, addiu, b, j, jal, jr
from fake_ghidra import FakeGhidra
from test_names import make_root, row

BASE, TOP = 0x200000, 0x200400
SYSCALL, ERET, INVALID = 0x0000000C, 0x42000018, 0xC0000000  # 0x30 << 26 (ll): not an R5900 instruction
LI_V1 = addiu(3, 0, 0x23)
ADD = addiu(V0, V0, 1)


@pytest.fixture(autouse=True)
def quick_settle(monkeypatch):
    monkeypatch.setattr(names, "QUIET_SECONDS", 0.0)
    monkeypatch.setattr(names, "POLL_SECONDS", 0.0)


def body_of(p, entry):
    f = p.functions[entry]
    return {a for a in range(f["lo"], f["end"] + 1, 4) if not any(lo <= a <= hi for lo, hi in f["holes"])}


def set_body(p, entry, words):
    f = p.functions[entry]
    f["lo"], f["end"] = min(words), max(words) + 3
    holes, lo = [], None
    for a in range(f["lo"], f["end"] + 1, 4):
        if a not in words and lo is None:
            lo = a
        if a in words and lo is not None:
            holes.append((lo, a - 1))
            lo = None
    f["holes"] = holes


class FakeStarts(FakeGhidra):
    def __init__(self, **kwargs):
        kwargs.setdefault("writes", gb.STARTS_WRITES)
        super().__init__(**kwargs)
        r = self.release
        r.data, r.bookmarks, r.xrefs = [], [], {}
        self.extra_code: dict[int, list[int]] = {}  # disassembly start -> more instructions it makes
        self.missing_code: dict[int, list[int]] = {}  # disassembly start -> instructions it does not make
        self.bookmark_after: dict[int, tuple] = {}  # create address -> a bookmark analysis adds

    def put(self, entry, words, name=None, thunk_of=None):
        self.release.add(entry, max(words) + 3, name, thunk_of=thunk_of)
        set_body(self.release, entry, set(words))
        self.release.code |= set(words)

    # reads
    def get_find_code_gaps(self, q):
        p = self.program(q["program"])
        used = set().union(*(body_of(p, e) for e in p.functions)) if p.functions else set()
        gaps, lo = [], None
        for a in range(p.image.base, p.image.end + 4, 4):
            free = a < p.image.end and a not in used
            if free and lo is None:
                lo = a
            if not free and lo is not None:
                gaps.append((lo, a - 1))
                lo = None
        entries = sorted(p.functions)
        out = []
        for lo, hi in gaps:
            before = [e for e in entries if e <= lo]
            after = [e for e in entries if e > hi]
            out.append({"start": "%08x" % lo, "end": "%08x" % hi, "size": hi - lo + 1,
                        "has_undefined_bytes": lo not in p.code and not self.in_data(p, lo),
                        "has_orphaned_instructions": any(a in p.code for a in range(lo, hi + 1, 4)),
                        "before_function_address": "%08x" % before[-1] if before else None,
                        "after_function_address": "%08x" % after[0] if after else None})
        return {"total": len(out), "offset": 0, "limit": int(q.get("limit", 100)), "gaps": out}

    @staticmethod
    def in_data(p, a):
        return any(d <= a < d + n for d, n, _ in p.data)

    def get_list_bookmarks(self, q):
        p = self.program(q["program"])
        return {"success": True, "count": len(p.bookmarks),
                "bookmarks": [{"address": "%08x" % a, "type": t, "category": c, "comment": m}
                              for a, t, c, m in p.bookmarks]}

    def get_list_data_items(self, q):
        p = self.program(q["program"])
        return "\n".join(f"DAT_{a:08x} @ {a:08x} [{t}] ({n} {'byte' if n == 1 else 'bytes'})" for a, n, t in p.data)

    def get_get_xrefs_to(self, q):
        p = self.program(q["program"])
        found = p.xrefs.get(int(q["address"], 16), [])
        return "\n".join(f"From {s:08x} [DATA]" for s in found) or f"No references found to address: {q['address']}"

    # writes
    def post_disassemble_bytes(self, p, d):
        assert d["restrict_to_execute_memory"] is False  # the plugin's followFlow argument
        start, end = int(d["start_address"], 16), int(d["end_address"], 16)
        for first in range(start, end, 4):
            pc = first
            while pc not in p.code:
                if self.in_data(p, pc) or mips.is_invalid(p.image.word(pc)):
                    p.bookmarks.append((pc, "Error", "Bad Instruction", "conflict"))
                    break
                word = p.image.word(pc)
                p.code.add(pc)
                step = 4
                if starts.has_delay(word):
                    p.code.add(pc + 4)
                    step = 8
                if not starts.falls_through(word):
                    break
                pc += step
        p.code |= set(self.extra_code.get(start, ()))
        p.code -= set(self.missing_code.get(start, ()))
        listed = sorted(a for a in p.code if start <= a < end)
        return {"success": True, "instructions": [{"address": "%08x" % a} for a in listed]}

    def post_create_function(self, p, d):
        address = int(d["address"], 16)
        assert d["disassemble_first"] is False
        if address in p.functions:
            return {"error": f"Function already exists at {d['address']}"}
        if address not in p.code:
            p.add(address, address)  # CreateFunctionCmd.getFunctionBody: a one-byte place-holder
            return {"success": True}
        flow = createflow.predict(p.image.word, p.image.contains, address, set(p.functions),
                                  {e for e, f in p.functions.items() if f["noreturn"]},
                                  is_code=lambda a: a in p.code, terminal=lambda w: w in starts.TERMINATORS)
        body = set(flow.body)
        if address in p.flow_end:
            body = set(range(address, p.flow_end[address] + 1, 4))
        for other in sorted(p.functions):
            known = body_of(p, other)
            if not known & body:
                continue
            top = max(body) + 3
            cut = {a for a in known if not (address <= a <= (top if other < address else other - 1))}
            set_body(p, other, cut)
            body -= cut
        first = p.image.word(address)
        thunk_of = None
        if len(body) == 2 and p.image.word(address + 4) == 0 and mips.is_j(first) \
                and mips.jump_target(first, address) in p.functions:
            thunk_of = mips.jump_target(first, address)
        p.add(address, max(body) + 3, self.analysis_names.get(address), thunk_of=thunk_of)
        set_body(p, address, body)
        for extra in self.analysis_creates.get(address, ()):
            p.add(extra, extra + 0xF)
        if address in self.bookmark_after:
            p.bookmarks.append(self.bookmark_after[address])
        if address in self.analysis_effects:
            self.analysis_effects[address](p)
        return {"success": True, "function_name": p.shown(address)}


def simple(at, words=None):
    """A small function: two adds, jr ra, nop (or ``words``)."""

    return dict(zip(range(at, at + 16, 4), words or [ADD, ADD, JR_RA, NOP]))


SPECIAL = {
    **simple(0x200000),                                   # F0, existing
    **simple(0x200020, [jal(0x200030), NOP, JR_RA, NOP]),  # S1 calls S2: S2 first
    **simple(0x200030),                                   # S2
    **simple(0x200040),                                   # F3, existing
    0x200050: LI_V1, 0x200054: SYSCALL,                   # S4: falls through 8 bytes of padding into F5
    0x200060: ADD, 0x200064: ADD, 0x200068: j(0x200070), 0x20006c: ADD,   # F5, Ghidra's body takes X6
    **simple(0x200070),                                   # X6, inside F5
    **simple(0x200080, [jal(0x200090), NOP, JR_RA, NOP]),  # S7 and S8 call each other
    **simple(0x200090, [jal(0x200080), NOP, JR_RA, NOP]),
    **simple(0x2000a0, [jal(0x200300), NOP, JR_RA, NOP]),  # S9 calls what is no function
    **simple(0x2000b0, [ADD, INVALID, JR_RA, NOP]),       # S10: bytes that do not decode
    0x2000c0: b(2), 0x2000c4: NOP, 0x2000c8: ADD, 0x2000cc: JR_RA, 0x2000d0: NOP,  # T11: thunk split
    0x2000e0: ADD, 0x2000e4: jal(0x200000), 0x2000e8: NOP, 0x2000ec: NOP,          # B12: padding in the body
    0x2000f0: ADD, 0x2000f4: ERET, 0x2000f8: JR_RA, 0x2000fc: NOP,                 # U13: unreachable tail
    0x200100: JR_RA, **simple(0x200104, [ADD, JR_RA, NOP, NOP]),                   # D14: its delay slot is F15
    0x200110: b(2), 0x200114: NOP, 0x200118: ADD, 0x20011c: JR_RA, 0x200120: NOP,  # H16: a dead word
    **simple(0x200140, [ADD, ADD, j(0x20016c), NOP]),     # P17 jumps into Q19 across S18
    **simple(0x200150),                                   # S18
    0x200160: ADD, 0x200164: JR_RA, 0x200168: NOP, 0x20016c: ADD, 0x200170: JR_RA, 0x200174: NOP,  # Q19
    0x200180: LI_V1, 0x200184: SYSCALL,                   # C20: code without a function, padding, F21
    **simple(0x200190),                                   # F21
    0x2001c0: jr(V0), 0x2001c4: NOP, 0x2001c8: ADD, 0x2001cc: JR_RA, 0x2001d0: NOP,  # W22: a switch
}
ROWS = [row(a, n, "new", evidence=("settled",)) for a, n in (
    (0x200000, 16), (0x200020, 16), (0x200030, 16), (0x200040, 16), (0x200050, 8), (0x200060, 16),
    (0x200070, 16), (0x200080, 16), (0x200090, 16), (0x2000a0, 16), (0x2000b0, 16), (0x2000c0, 20),
    (0x2000e0, 12), (0x2000f0, 16), (0x200100, 4), (0x200104, 12), (0x200110, 20), (0x200140, 16),
    (0x200150, 16), (0x200160, 24), (0x200180, 8), (0x200190, 16), (0x2001c0, 20))]


def make_program(special=SPECIAL, rows=ROWS):
    g = FakeStarts()
    words = {a: NOP for a in range(BASE, TOP, 4)}
    words.update(special)
    g.release.image = elfimage.synthetic([words[a] for a in range(BASE, TOP, 4)], base=BASE)
    r = g.release
    for at in (0x200000, 0x200040, 0x200190):
        g.put(at, range(at, at + 16, 4))
    g.put(0x200060, range(0x200060, 0x200080, 4))                    # F5 with X6 in its body
    g.put(0x2000c0, [0x2000c0, 0x2000c4], thunk_of=None)              # T11 as Ghidra split it
    g.put(0x2000cc, [0x2000cc, 0x2000d0])
    r.functions[0x2000c0]["thunk_of"] = 0x2000cc
    r.code.add(0x2000c8)
    g.put(0x2000e0, range(0x2000e0, 0x2000f0, 4))                    # B12 with its padding
    g.put(0x2000f0, [0x2000f0, 0x2000f4])                             # U13 ends at the eret
    g.put(0x200104, range(0x200104, 0x200110, 4))
    g.put(0x200140, range(0x200140, 0x200150, 4))
    g.put(0x200160, range(0x200160, 0x200178, 4))
    r.code |= set(range(0x200180, 0x200190, 4))                      # C20: instructions, no function
    r.data.append((0x200300, 16, "string"))
    return g


def reader(g):
    out = FakeStarts(read_only=True)
    out.prototype, out.release = g.prototype, g.release
    return out


def plan_for(tmp_path, g, rows=ROWS):
    root = make_root(tmp_path, rows)
    names_plan = names.build_plan(root, reader(g), None, image=g.release.image)
    names.write_plan(root, names_plan)
    plan = starts.build_plan(root, reader(g), image=g.release.image)
    return root, plan, starts.write_plan(root, plan)


def by(plan):
    return {e["address"]: e for e in plan["entries"]}


def test_every_case_is_planned_or_withheld_with_its_reason(tmp_path):
    g = make_program()
    _, plan, _ = plan_for(tmp_path, g)
    e = by(plan)
    assert e["0x200030"]["decision"] == "planned" and e["0x200020"]["decision"] == "planned"
    assert plan["order"].index("0x200030") < plan["order"].index("0x200020")  # callee first
    assert e["0x200020"]["after"] == ["0x200030"]
    s2 = e["0x200030"]["steps"]
    assert [s["kind"] for s in s2] == ["disassemble", "create"]
    assert s2[0]["instructions"] == [["0x200030", "0x20003f"]] and s2[1]["body"] == [["0x200030", "0x20003f"]]
    assert s2[1]["signature"] == "undefined FUN_00200030(void)" and s2[1]["accepted"] is None
    s4 = e["0x200050"]["steps"]  # syscall falls through: the padding is disassembled and accepted
    assert s4[0]["end_exclusive"] == "0x200060" and s4[0]["padding"] == [["0x200058", "0x20005f"]]
    assert s4[1]["accepted"]["kind"] == "padding" and s4[1]["body_highest"] == "0x20005f"
    x6 = e["0x200070"]["steps"]
    assert [s["kind"] for s in x6] == ["create"]
    assert x6[0]["cuts"] == [{"function": "0x200060", "before": [["0x200060", "0x20007f"]],
                              "after": [["0x200060", "0x20006f"]]}]
    assert x6[0]["overrides"] == [{"at": "0x200068", "to": "0x200070"}]
    assert e["0x200060"]["decision"] == "fixed-by-create" and e["0x200060"]["fixed_by"] == "0x200070"
    assert "a cycle" in e["0x200080"]["reason"] and "a cycle" in e["0x200090"]["reason"]
    assert "no function and no map start" in e["0x2000a0"]["reason"]
    assert "do not decode" in e["0x2000b0"]["reason"]
    assert e["0x2000c0"]["decision"] == "cannot" and "thunk" in e["0x2000c0"]["reason"]
    assert e["0x2000e0"]["decision"] == "accept" and e["0x2000e0"]["accepted"]["kind"] == "padding"
    assert e["0x2000f0"]["decision"] == "accept" and e["0x2000f0"]["accepted"]["kind"] == "unreachable"
    assert "delay slot" in e["0x200100"]["reason"]
    h16 = e["0x200110"]["steps"][1]
    assert h16["accepted"]["kind"] == "unreachable" and h16["accepted"]["ranges"] == [["0x200118", "0x20011b"]]
    assert "Shared Return" in e["0x200150"]["reason"] and "0x20016c" in e["0x200150"]["reason"]
    c20 = e["0x200180"]
    assert c20["case"] == "create-withheld" and c20["decision"] == "planned"
    assert [s["kind"] for s in c20["steps"]] == ["create"] and c20["steps"][0]["accepted"]["kind"] == "padding"
    assert "switch analysis" in e["0x2001c0"]["reason"]
    assert plan["summary"]["by_decision"] == {"accept": 2, "cannot": 1, "fixed-by-create": 1, "planned": 6,
                                              "withheld": 7}


def test_the_plan_is_deterministic_and_refuses_a_stale_names_plan(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    again = starts.build_plan(root, reader(g), image=g.release.image)
    assert again["plan_sha256"] == plan["plan_sha256"]
    g.put(0x200200, [0x200200, 0x200204])  # a function the names plan does not know
    with pytest.raises(names.Refused, match="names plan does not describe"):
        starts.build_plan(root, reader(g), image=g.release.image)


def test_apply_makes_exactly_the_prediction_and_records_it(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    result = starts.apply(root, path, g, dry_run=False, today="2026-11-27", image=g.release.image)
    assert result["stopped"] is None and result["side_effects"] == [] and result["analysis_changes"] == []
    sent = [(s["endpoint"], s["body"].get("address") or s["body"].get("start_address")) for s in result["sent"]]
    assert sent.index(("create_function", "0x200030")) < sent.index(("disassemble_bytes", "0x200020"))
    assert all(s["body"]["restrict_to_execute_memory"] is False for s in result["sent"]
               if s["endpoint"] == "disassemble_bytes")
    r = g.release
    assert body_of(r, 0x200060) == set(range(0x200060, 0x200070, 4))  # the container cut back
    assert body_of(r, 0x200070) == set(range(0x200070, 0x200080, 4))
    assert body_of(r, 0x200050) == set(range(0x200050, 0x200060, 4))
    assert result["counts"] == {"create": 6, "cut-by-analysis": 1, "disassemble": 4, "extent-accepted": 3}
    assert result["checked"]["accepted as is"] == 2
    record = names.read_record(root)
    assert record[("0x200060", "cut-by-analysis")]["state"] == f"unsaved {result['report']}"
    assert record[("0x200030", "disassemble")]["value"] == "0x200030-0x20003f"
    assert record[("0x200050", "extent-accepted")]["value"].startswith("0x200050-0x20005f: padding")
    report = root / starts.OUT / result["report"]
    done = names.confirm_saved(root, report, reader(g), today="2026-11-28", reads_back=starts.reads_back)
    assert done["confirmed"] == 14
    # names then plans the new functions as existing ones
    names_plan = names.build_plan(root, reader(g), None, image=r.image)
    actions = {e["address"]: e["function"] for e in names_plan["entries"]}
    assert actions["0x200030"] == actions["0x200020"] == actions["0x200070"] == actions["0x200060"] == "exists"
    assert actions["0x200110"] == "exists" and actions["0x200050"] == "boundary"  # padding: accepted, recorded


def test_dry_run_sends_nothing_and_lists_the_writes(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    ro = reader(g)
    result = starts.apply(root, path, ro, dry_run=True, image=g.release.image)
    assert result["stopped"] is None and ro.sent == []
    kinds = Counter_of(result["would_write"])
    assert kinds == {"create": 6, "disassemble": 4}


def Counter_of(items):
    out = {}
    for item in items:
        out[item["applied"]] = out.get(item["applied"], 0) + 1
    return out


def test_a_changed_program_stops_before_any_write(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    g.release.bookmarks.append((0x200000, "Note", "x", "y"))
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image)
    assert result["stop_kind"] == "before" and g.sent == [] and "baseline" in result["stopped"]
    assert "replan" in result["what_to_do"]


def test_other_instructions_than_predicted_stop_after_the_write(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    g.missing_code[0x200030] = [0x200038]  # the disassembly left a word out
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image)
    assert result["stop_kind"] == "after" and "disassemble" not in result["counts"]
    assert "--discard-unsaved" in result["what_to_do"] and len(result["attempted"]) == 1
    report = root / starts.OUT / result["report"]
    with pytest.raises(names.Refused, match="no unsaved rows"):
        names.confirm_saved(root, report, reader(make_program()), reads_back=starts.reads_back)


def test_disassembly_elsewhere_stops_the_run(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    g.extra_code[0x200030] = [0x200240]  # outside the range: the operand-reference analyzer, say
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image)
    assert result["stop_kind"] == "analysis" and result["counts"] == {"disassemble": 1}
    assert any(c.get("change") == "orphans" or c.get("change") == "unexpected" for c in result["analysis_changes"])


def test_a_create_with_another_body_names_the_function_to_remove(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    g.release.flow_end[0x200030] = 0x200037
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image)
    assert result["stop_kind"] == "after" and result["remove_by_hand"][0]["address"] == "0x200030"
    report = root / starts.OUT / result["report"]
    with pytest.raises(names.Refused, match="remove it"):
        names.confirm_saved(root, report, reader(g), reads_back=starts.reads_back)


def test_a_function_analysis_adds_stops_the_run(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    g.analysis_creates[0x200030] = [0x200250]
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image)
    assert result["stop_kind"] == "analysis"
    assert {"address": "0x200250", "change": "appeared", "name": "FUN_00200250",
            "after": "create 0x200030"} in result["analysis_changes"]
    record = names.read_record(root)
    assert ("0x200030", "create") in record and ("0x200020", "disassemble") not in record


def test_a_bookmark_after_a_create_stops_the_run(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    g.bookmark_after[0x200030] = (0x200030, "Analysis", "Found Code", "Found code from operand reference")
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image)
    assert result["stop_kind"] == "analysis"
    assert any("bookmark" in c for c in result["analysis_changes"])


def test_a_changed_neighbour_stops_the_run(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    g.analysis_effects[0x200030] = lambda p: p.functions[0x200040].update(noreturn=True)
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image)
    assert result["stop_kind"] == "analysis"
    assert any(c.get("address") == "0x200040" and c["change"] == "noreturn" for c in result["analysis_changes"])


def test_batches_and_discard(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    result = starts.apply(root, path, g, dry_run=False, batch=1, image=g.release.image)
    assert result["batch_full"] and result["entries_done"] == 1 and result["stopped"] is None
    with pytest.raises(names.Refused, match="unsaved"):
        starts.apply(root, path, g, dry_run=False, image=g.release.image)
    report = root / starts.OUT / result["report"]
    with pytest.raises(names.Refused, match="still in the program"):
        names.discard_unsaved(root, report, reader(g), reads_back=starts.reads_back)
    closed = make_program()  # the program closed without saving
    done = names.discard_unsaved(root, report, reader(closed), reads_back=starts.reads_back)
    assert done["discarded"] == 2  # S2's disassembly and create
    assert names.unsaved(names.read_record(root)) == []


def test_a_pilot_takes_its_entries_only_and_needs_their_dependencies(tmp_path):
    g = make_program()
    root, plan, path = plan_for(tmp_path, g)
    refused = starts.apply(root, path, reader(g), dry_run=True, image=g.release.image, only={"0x200020"})
    assert refused["stop_kind"] == "before" and "needs 0x200030 first" in refused["stopped"]
    result = starts.apply(root, path, g, dry_run=False, image=g.release.image, only={"0x200070", "0x200110"})
    assert result["stopped"] is None and result["entries_done"] == 2
    assert {s["body"]["address"] for s in result["sent"] if s["endpoint"] == "create_function"} == {"0x200070",
                                                                                                    "0x200110"}


def test_the_bridge_sends_only_the_two_writes_to_the_release_program():
    g = make_program()
    with pytest.raises(gb.WriteRefused):
        g.write("delete_function", gb.RELEASE_PROGRAM, address="0x200000")
    with pytest.raises(gb.WriteRefused):
        g.write("disassemble_bytes", gb.PROTOTYPE_PROGRAM, start_address="0x200000")
    with pytest.raises(gb.WriteRefused):
        FakeStarts(read_only=True).write("create_function", gb.RELEASE_PROGRAM, address="0x200000")


def test_disassembly_and_flow_rules():
    g = make_program()
    model = starts.Model(g.release.image, {}, {}, set(), [{"start": BASE, "end": TOP - 1, "undefined": True,
                                                           "orphans": False, "before": None, "after": None}],
                         [(0x200300, 16, "string")], lambda a: False)
    done = starts.simulate_disassembly(model, 0x200050, 0x200058)
    assert done["overrun"] == list(range(0x200058, 0x200100, 4))[:len(done["overrun"])] or done["error"]
    assert "do not decode" in starts.simulate_disassembly(model, 0x2000b0, 0x2000c0)["error"]
    assert not starts.falls_through(ERET) and starts.falls_through(SYSCALL) and not starts.falls_through(b(2))
    assert starts.lui_references(lambda a: {0: (15 << 26) | (A0 << 16) | 0x20, 4: addiu(A0, A0, 0x300)}[a], 0, 8) \
        == [(4, 0x200300)]
