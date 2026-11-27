"""Stage 3 signatures, group mangled: prototypes derived from the counterpart's mangled symbol."""
from __future__ import annotations

import pytest

import elfimage
import ghidra_bridge as gb
import mangledsig as ms
import names
import signatures as sg
from asm import A1, JR_RA, NOP, V0, ZERO, lw
from fake_ghidra import FakeGhidra
from test_names import image_for, make_root, row

SYMBOLS = [  # (symbol or symbols, class): release 0x200000 + 0x10 i, prototype 0x300000 + 0x10 i
    ("__ct__4CFooFi", "exact"),             # 0  constructor
    ("__dt__4CFooFv", "exact"),             # 1  destructor, its flag parameter
    ("Get__4CFooCFv", "exact"),             # 2  const member
    ("Virt__4CFooFi", "exact"),             # 3  vtable slot; return from the signed override
    ("Free__Fif", "exact"),                 # 4  free function: no this
    ("Ns__2nsFi", "exact"),                 # 5  namespace scope: no this
    ("Code__4CFooFi", "deviating"),         # 6  the release code reads a1: this
    ("Undec__4CFooFi", "exact"),            # 7  this undecided
    ("Miss__4CFooFP4CBaz", "exact"),        # 8  missing type
    ("Fp__4CFooCFPFv_v", "exact"),          # 9  function pointer
    ("Dbl__Fd", "exact"),                   # 10 double by value
    ("Big__4CFooCF5CHuge", "exact"),        # 11 class of 12 bytes by value
    ("@8@Stub__4CFooFv", "exact"),          # 12 this-adjusting stub
    ("Many__Fiiiiiiiii", "exact"),          # 13 nine GPR arguments
    ("Vargs__Fe", "exact"),                 # 14 varargs only
    ("M__7CAbsentCFv", "exact"),            # 15 receiver missing
    (["A__4CFooCFi", "A__4CFooCFf"], "exact"),  # 16 aliases that disagree
    ("cfunc", "exact"),                     # 17 no mangled symbol
    ("Live__4CFooCFv", "exact"),            # 18 the release has a signature already
    ("NoPl__4CFooCFv", "exact"),            # 19 no plate of the names step
    ("__nw__4CFooFUi", "exact"),            # 20 operator new: static
]
SIBLING = 0x300200  # CBar::Virt, signed int, the override of slot 0
ROWS = [row(0x200000 + 0x10 * i, 0x10, cls, 0x300000 + 0x10 * i, sym if isinstance(sym, str) else sym[0],
            names_=[sym] if isinstance(sym, str) else sym)
        for i, (sym, cls) in enumerate(SYMBOLS)]
READ_A1 = (0 << 26) | (A1 << 21) | (ZERO << 16) | (V0 << 11) | 0x21  # addu v0, a1, zero


def plate(i: int) -> str:
    r = ROWS[i]
    return (f"Release map: {r['class']} pair with prototype {names.hx(r['prototype_address'])} "
            f"{r['prototype_symbol']} (evidence call; flags -).\nOwner -.")


def prototype_image():
    words = {a: NOP for a in range(0x300000, 0x300400, 4)}
    symbols = []
    for r in ROWS:
        words[r["prototype_address"] + 8] = JR_RA
        symbols += [elfimage.Symbol(r["prototype_address"], 0x10, n, 2, 1) for n in r["prototype_names"]]
    words[SIBLING + 8] = JR_RA
    symbols.append(elfimage.Symbol(SIBLING, 0x10, "Virt__4CBarFi", 2, 1))
    for at, cls, slot in ((0x300380, "__vt__4CFoo", 0x300030), (0x300390, "__vt__4CBar", SIBLING)):
        words[at], words[at + 4], words[at + 8] = 0, 0, slot
        symbols.append(elfimage.Symbol(at, 12, cls, 1, 1))
    return elfimage.synthetic([words[a] for a in range(0x300000, 0x300400, 4)], base=0x300000, symbols=symbols)


def make_ghidra(read_only=False):
    g = FakeGhidra(read_only=read_only, writes=gb.SIGNATURE_WRITES)
    p, r = g.prototype, g.release
    for i, x in enumerate(ROWS):
        p.add(x["prototype_address"], x["prototype_address"] + 0xF, f"Proto{i}")
        r.add(x["release_address"], x["release_address"] + 0xF)
        if i != 19:
            r.plates[x["release_address"]] = plate(i)
    p.add(SIBLING, SIBLING + 0xF, "CBar::Virt")
    p.sign(SIBLING, "int", "__stdcall", [("CBar *", "this"), ("int", "param_2")])
    r.sign(0x200120, "int", "__stdcall", [("CFoo *", "this")])
    for program in (p, r):
        program.add_type("/project/CFoo", 8)
        program.add_type("/project/ns/Thing", 4)
        program.add_type("/project/CHuge", 12)
    r.image = image_for(ROWS, {0x200060: READ_A1})
    return g


def reader_for(g):
    reader = FakeGhidra(read_only=True)
    reader.prototype, reader.release = g.prototype, g.release
    return reader


def plan_for(tmp_path, g):
    root = make_root(tmp_path, ROWS)
    plan = sg.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image, prototype_image=prototype_image())
    return root, plan, sg.write_plan(root, plan)


def entries(plan):
    return [e for e in plan["entries"]]


def test_derived_signatures_this_evidence_and_returns(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    by = entries(plan)
    assert all(e["group"] == "mangled" for e in by)
    want = {
        0: ("void * FUN_00200000(CFoo * this, int param_2)", "constructor"),
        1: ("void * FUN_00200010(CFoo * this, short __dtor_flags)", "destructor"),
        2: ("undefined FUN_00200020(CFoo * this)", "const member"),
        3: ("int FUN_00200030(CFoo * this, int param_2)", "slot 0 of __vt__4CFoo"),
        4: ("undefined FUN_00200040(int param_1, float param_2)", "free function"),
        5: ("undefined FUN_00200050(int param_1)", "namespace scope"),
        6: ("undefined FUN_00200060(CFoo * this, int param_2)",
            "the code reads a1 at 0x200060, the GPR after the declared ones"),
        20: ("undefined FUN_00200140(uint param_1)", "operator new (static)"),
    }
    for i, (text, evidence) in want.items():
        e = by[i]
        assert e["action"] == "write", (i, e.get("reason"))
        assert e["send"] == {"prototype": text, "calling_convention": "__stdcall"}
        assert e["mangled"]["this_evidence"] == evidence
        assert e["mangled"]["symbol"] == ROWS[i]["prototype_symbol"]
    assert by[1]["expected"]["parameters"] == [{"name": "this", "type": "CFoo *", "storage": "a0_lo:4"},
                                               {"name": "__dtor_flags", "type": "short", "storage": "a1_lo:2"}]
    assert by[4]["expected"]["parameters"][1]["storage"] == "f12:4"
    assert by[3]["mangled"]["return_evidence"] == "the signed overrides of its vtable slot"
    assert by[6]["pair_group"] == "deviating"
    # the code rule reads the release bytes; the prototype's would leave this undecided
    assert by[6]["mangled"]["prototype_bytes_this"] is None
    summary = plan["summary"]["mangled"]
    assert summary["code_rule_release_vs_prototype_bytes"]["decisions_that_differ"] == 1
    assert summary["planned"] == 8 and summary["planned_by_pair"] == {"deviating": 1, "exact": 7}
    assert plan["summary"]["planned"] == {"mangled": 8}
    # the plate clause: the symbol, the this evidence, the return
    assert by[2]["plate"]["after"] == plate(2)[:-1] + (
        "; signature derived from the mangled symbol Get__4CFooCFv: this from const member, return type unknown.")
    assert by[0]["mangled"]["clause"].endswith("return void * (a constructor returns this)")
    assert by[4]["mangled"]["clause"] == ("signature derived from the mangled symbol Free__Fif: no this "
                                          "(free function), return type unknown")
    assert sg.canonical(sg.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image,
                                      prototype_image=prototype_image())) == path.read_text(encoding="utf-8")


def test_each_withhold_reason(tmp_path):
    g = make_ghidra()
    _, plan, _ = plan_for(tmp_path, g)
    by = entries(plan)
    want = {
        7: ("mangled this", "this undecided: the code reads no GPR beyond the declared ones"),
        8: ("mangled type", "missing type /project/CBaz"),
        9: ("mangled type", "function or member pointer void (*)(void): its type is anonymous"),
        10: ("mangled type", "double by value: Metrowerks' passing is not proven"),
        11: ("mangled type", "CHuge by value has 12 bytes (only 1, 2, 4 or 8 go in one GPR)"),
        12: ("mangled this", "@[8]@ this-adjusting stub: a0 is a base part"),
        13: ("mangled storage", "more than eight GPR arguments (Metrowerks puts the rest on the stack)"),
        14: ("mangled parameter", "varargs without a fixed parameter: the parser sets varargs only after a comma"),
        15: ("mangled receiver", "receiver missing type /project/CAbsent"),
        16: ("mangled symbol", "the mangled aliases at the counterpart disagree: A__4CFooCFf, A__4CFooCFi"),
        17: ("mangled symbol", "no mangled symbol at the counterpart"),
        18: ("live", "Ghidra already gives it int __stdcall FUN_00200120(CFoo * this); a derived signature "
                     "replaces none"),
        19: ("plate", "no plate comment of the names step to carry the derived-signature clause"),
    }
    for i, (group, reason) in want.items():
        e = by[i]
        assert (e["action"], e["reason_group"], e["reason"]) == ("withheld", group, reason), i
    assert plan["summary"]["mangled"]["withheld_by_reason"] == {
        "live": 1, "mangled parameter": 1, "mangled receiver": 1, "mangled storage": 1, "mangled symbol": 2,
        "mangled this": 2, "mangled type": 4, "plate": 1}


def test_apply_reads_back_marks_the_record_and_needs_the_class(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    assert sg.apply(root, path, g, dry_run=True)["skipped"] == {"group mangled not taken": 8}
    with pytest.raises(names.Refused, match="--classes"):
        sg.apply(root, path, g, dry_run=True, classes=("mangled",))
    result = sg.apply(root, path, g, dry_run=False, classes=("exact", "mangled"), today="2026-11-27")
    assert result["stopped"] is None and result["side_effects"] == [] and result["analysis_changes"] == []
    assert result["counts"] == {"plate": 8, "prototype": 8}
    assert g.release.signature(0x200010) == "void * __stdcall FUN_00200010(CFoo * this, short __dtor_flags)"
    assert g.release.plates[0x200020].endswith("this from const member, return type unknown.")
    record = names.read_record(root)
    value = record[("0x200000", "prototype")]["value"]
    assert value.endswith(ms.DERIVED_MARK) and value.startswith("void * __stdcall FUN_00200000(CFoo * this, int param_2)")
    done = sg.confirm_saved(root, root / sg.OUT / result["report"], reader_for(g), today="2026-11-27")
    assert done["confirmed"] == 16
    again = sg.apply(root, path, g, dry_run=True, classes=("exact", "mangled"))
    assert again["would_write"] == [] and again["unchanged"] == {"prototype (saved)": 8}


def test_a_storage_difference_stops_the_run(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)

    def stack(p):  # Ghidra put the parameter elsewhere than Metrowerks passes it
        p.functions[0x200000]["storage"] = ["a0_lo:4", "Stack[0x0]:4"]

    g.prototype_effects[0x200000] = [stack]
    result = sg.apply(root, path, g, dry_run=False, classes=("exact", "mangled"), today="2026-11-27")
    assert result["stop_kind"] == "StopAfter"
    assert "parameter 2 storage 'Stack[0x0]:4', expected 'a1_lo:4'" in result["stopped"]
    assert result["written"] == []


def test_the_names_replan_keeps_the_derived_clause():
    planned = plate(2)
    clause = "signature derived from the mangled symbol Get__4CFooCFv: this from const member, return type unknown"
    recorded = names.record_value(planned[:-1] + "; " + clause + ".")
    assert names.kept_plate(planned, recorded) == planned[:-1] + "; " + clause + "."
    assert names.kept_plate(planned, names.record_value(planned[:-1] + "; something else.")) == planned
    assert ms.CLAUSE_PREFIX == names.MANGLED_CLAUSE


def test_code_rule_reads_and_registers():
    words = [READ_A1, JR_RA, NOP]
    assert ms.entry_reads(words, 0, 3, 0x1000) == {A1: 0x1000}
    # a register written first is no entry read; a load's base is a read
    words = [(9 << 26) | (A1 << 16) | 1, lw(V0, 0, A1), JR_RA, NOP]  # addiu a1, zero, 1; lw v0, 0(a1)
    assert ms.entry_reads(words, 0, 4, 0x1000) == {}
    assert ms.entry_reads([lw(V0, 4, 4), JR_RA, NOP], 0, 3, 0x1000) == {4: 0x1000}


def test_placeholder_plan_lists_missing_names_and_what_they_unlock(tmp_path):
    import placeholders

    g = make_ghidra()
    _, plan, _ = plan_for(tmp_path, g)
    out = placeholders.build(plan, dict(g.release.types), prototype_image(), g.release.image)
    by = {r["name"]: r for r in out["types"]}
    assert set(by) == {"CBaz", "CAbsent"}
    assert (by["CAbsent"]["kind"], by["CAbsent"]["category"], by["CAbsent"]["uses"]) == (
        "class", "/project", {"receiver": 1})
    assert by["CBaz"]["kind"] == "struct (incomplete)" and by["CBaz"]["uses"] == {"pointer": 1}
    s = out["summary"]
    assert (s["would_create"], s["functions_unlocked"]) == (2, 1)  # M__7CAbsentCFv; Miss__ is then undecided
    assert s["functions_not_unlocked"] == {"blocked otherwise": 3, "then withheld: this": 1}
    assert by["CAbsent"]["functions_unlocked"] == 1 and by["CBaz"]["functions_unlocked"] == 0
