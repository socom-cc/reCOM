"""Stage 3 signatures, group mangled: prototypes derived from the counterpart's mangled symbol."""
from __future__ import annotations

import pytest

import elfimage
import ghidra_bridge as gb
import mangledsig as ms
import names
import placeholders
import signatures as sg
from asm import A0, A1, A2, JR_RA, NOP, V0, ZERO, lw, sw
from fake_ghidra import FakeGhidra
from test_names import image_for, make_root, row

SYMBOLS = [  # (symbol or symbols, class): release 0x200000 + 0x10 i, prototype 0x300000 + 0x10 i
    ("__ct__4CFooFi", "exact"),             # 0  constructor
    ("__dt__4CFooFv", "exact"),             # 1  destructor, its flag parameter
    ("Get__4CFooCFv", "exact"),             # 2  const member
    ("Virt__4CFooFi", "exact"),             # 3  vtable slot; return from the signed override
    ("Free__Fif", "exact"),                 # 4  free function: no this
    ("Ns__3stdFi", "exact"),                # 5  namespace std: no this
    ("Code__4CFooFi", "deviating"),         # 6  the release code reads a1: this, from the code alone
    ("Undec__4CFooFi", "exact"),            # 7  this undecided
    ("Miss__4CFooFP4CBaz", "exact"),        # 8  missing type
    ("Fp__4CFooCFPFv_v", "exact"),          # 9  function pointer
    ("Dbl__Fd", "exact"),                   # 10 double by value
    ("Big__4CFooCF5CHuge", "exact"),        # 11 class by value
    ("@8@Stub__4CFooFv", "exact"),          # 12 this-adjusting stub
    ("Many__Fiiiiiiiii", "exact"),          # 13 nine GPR arguments
    ("Vargs__Fe", "exact"),                 # 14 varargs only
    ("M__7CAbsentCFv", "exact"),            # 15 receiver missing
    (["A__4CFooCFi", "A__4CFooCFf"], "exact"),  # 16 aliases that disagree
    ("cfunc", "exact"),                     # 17 no mangled symbol
    ("Live__4CFooCFv", "exact"),            # 18 the release has a signature already
    ("NoPl__4CFooCFv", "exact"),            # 19 no plate of the names step
    ("__nw__4CFooFUi", "exact"),            # 20 operator new: static
    ("__pl__6CPnt3DCFRC6CPnt3D", "exact"),  # 21 const member returning a class: reads a2 (hidden buffer in a0)
    ("__ct__4CVirFv", "exact"),             # 22 constructor with a virtual-base flag: reads a1
    ("Make__Fi", "exact"),                  # 23 DWARF: returns a structure by value
    ("Self__4CFooCFv", "exact"),            # 24 const member that hands a0 back in v0
    ("GetFirst__7CPickupFv", "exact"),      # 25 static returning a class: stores through a0 first
    ("Hand__Fbb9CAiMapLocPv", "exact"),     # 26 a class by value (no enum)
    ("Set__4CFooCF10SEAL_STATE", "exact"),  # 27 an enum the release proves, by value
    ("Tick__11CZBombStateFv", "exact"),     # 28 a class with a nested enum (category, no type): no namespace
    ("Walk__4CFooCFP3dir", "exact"),        # 29 missing dir: DIR exists, case ignored (no placeholder)
    ("Lod__4CFooCFP3LOD", "exact"),         # 30 missing LOD here: present hashed under unresolved
]
SIBLING = 0x300200  # CBar::Virt, signed int, the override of slot 0
ROWS = [row(0x200000 + 0x10 * i, 0x10, cls, 0x300000 + 0x10 * i, sym if isinstance(sym, str) else sym[0],
            names_=[sym] if isinstance(sym, str) else sym)
        for i, (sym, cls) in enumerate(SYMBOLS)]


def move(rd: int, rs: int) -> int:
    return (rs << 21) | (ZERO << 16) | (rd << 11) | 0x21  # addu rd, rs, zero


READ_A1, READ_A2 = move(V0, A1), move(V0, A2)
CODE = {0x200060: READ_A1, 0x200150: READ_A2, 0x200160: READ_A1, 0x200180: move(V0, A0),
        0x200190: sw(V0, 0, A0), 0x200194: lw(V0, 4, A0)}
DWARF = {0x300170: {"return": "composite", "params": []}}


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


def make_ghidra(read_only=False, writes=gb.SIGNATURE_WRITES):
    g = FakeGhidra(read_only=read_only, writes=writes)
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
        for path, size in (("/project/CFoo", 8), ("/project/CHuge", 12), ("/project/CPnt3D", 12),
                           ("/project/CVir", 8), ("/project/CPickup", 16), ("/project/CAiMapLoc", 4),
                           ("/project/SEAL_STATE", 1), ("/project/CZBombState/EnumBombState", 4),
                           ("/project/CAiMap/DIR", 1), ("/project/unresolved/LOD@74fd1e8283", 8)):
            program.add_type(path, size)
        program.enums |= {"SEAL_STATE", "EnumBombState", "DIR"}
    r.image = image_for(ROWS, CODE)
    return g


def reader_for(g):
    reader = FakeGhidra(read_only=True)
    reader.prototype, reader.release = g.prototype, g.release
    return reader


def plan_for(tmp_path, g):
    root = make_root(tmp_path, ROWS)
    plan = sg.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image, prototype_image=prototype_image(),
                         dwarf=DWARF)
    return root, plan, sg.write_plan(root, plan)


def test_derived_signatures_this_evidence_and_returns(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    by = plan["entries"]
    assert all(e["group"] == "mangled" for e in by)
    want = {
        0: ("void * FUN_00200000(CFoo * this, int param_2)", "constructor"),
        1: ("void * FUN_00200010(CFoo * this, short __dtor_flags)", "destructor"),
        2: ("undefined FUN_00200020(CFoo * this)", "const member"),
        3: ("int FUN_00200030(CFoo * this, int param_2)", "slot 0 of __vt__4CFoo"),
        4: ("undefined FUN_00200040(int param_1, float param_2)", "free function"),
        5: ("undefined FUN_00200050(int param_1)", "namespace scope"),
        6: ("undefined FUN_00200060(CFoo * this, int param_2)",
            "the code alone (it reads a1 at 0x200060, the GPR after the declared ones)"),
        20: ("undefined FUN_00200140(uint param_1)", "operator new (static)"),
        27: ("undefined FUN_002001b0(CFoo * this, SEAL_STATE param_2)", "const member"),
    }
    for i, (text, evidence) in want.items():
        e = by[i]
        assert e["action"] == "write", (i, e.get("reason"))
        assert e["send"] == {"prototype": text, "calling_convention": "__stdcall"}
        assert e["mangled"]["this_evidence"] == evidence
    assert by[1]["expected"]["parameters"][1] == {"name": "__dtor_flags", "type": "short", "storage": "a1_lo:2"}
    assert by[4]["expected"]["parameters"][1]["storage"] == "f12:4"
    assert by[27]["expected"]["parameters"][1]["storage"] == "a1_lo:1"
    assert by[3]["mangled"]["return_evidence"] == "the signed overrides of its vtable slot"
    assert by[6]["pair_group"] == "deviating" and by[6]["mangled"]["prototype_bytes_this"] is None
    assert by[6]["mangled"]["clause"].startswith(
        "signature derived from the mangled symbol Code__4CFooFi: this inferred from the code alone (it reads a1")
    summary = plan["summary"]["mangled"]
    assert summary["code_rule_release_vs_prototype_bytes"]["decisions_that_differ"] == 1
    assert summary["planned"] == 9 and summary["planned_by_pair"] == {"deviating": 1, "exact": 8}
    assert by[2]["plate"]["after"] == plate(2)[:-1] + (
        "; signature derived from the mangled symbol Get__4CFooCFv: this from const member, return type unknown.")
    assert by[4]["mangled"]["clause"] == ("signature derived from the mangled symbol Free__Fif: no this "
                                          "(free function), return type unknown")
    assert sg.canonical(sg.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image,
                                      prototype_image=prototype_image(), dwarf=DWARF)) == path.read_text(encoding="utf-8")


def test_each_withhold_reason(tmp_path):
    g = make_ghidra()
    _, plan, _ = plan_for(tmp_path, g)
    by = plan["entries"]
    no_enum = "by value is no enum the release proves: a class by value may travel as the address of a copy or in a " \
              "register, and the name does not tell"
    want = {
        7: ("mangled this", "this undecided: the code reads no GPR beyond the declared ones"),
        8: ("mangled type", "missing type /project/CBaz"),
        9: ("mangled type", "function or member pointer void (*)(void): its type is anonymous"),
        10: ("mangled type", "double by value: Metrowerks' passing is not proven"),
        11: ("mangled type", "CHuge " + no_enum),
        12: ("mangled this", "@[8]@ this-adjusting stub: a0 is a base part"),
        13: ("mangled storage", "more than eight GPR arguments (Metrowerks puts the rest on the stack)"),
        14: ("mangled parameter", "varargs without a fixed parameter: the parser sets varargs only after a comma"),
        15: ("mangled receiver", "receiver missing type /project/CAbsent"),
        16: ("mangled symbol", "the mangled aliases at the counterpart disagree: A__4CFooCFf, A__4CFooCFi"),
        17: ("mangled symbol", "no mangled symbol at the counterpart"),
        18: ("live", "Ghidra already gives it int __stdcall FUN_00200120(CFoo * this); a derived signature "
                     "replaces none"),
        19: ("plate", "no plate comment of the names step to carry the derived-signature clause"),
        # structure return under the const-member rule: the buffer in a0 pushes this and the parameter up
        21: ("mangled hidden", "the code reads a2 beyond the predicted registers (a0_lo:4, a1_lo:4): a hidden "
                               "argument (a returned class, or a virtual-base flag) or a wrong receiver"),
        # under the constructor rule: a constructor of a class with virtual bases takes a hidden flag
        22: ("mangled hidden", "the code reads a1 beyond the predicted registers (a0_lo:4): a hidden argument "
                               "(a returned class, or a virtual-base flag) or a wrong receiver"),
        23: ("mangled hidden", "the counterpart's DWARF record returns a class, structure or union by value: a "
                               "hidden pointer to the return buffer takes a0"),
        24: ("mangled hidden", "the code copies the entry a0 to v0 at 0x200180: a returned buffer (or a member "
                               "returning this), the name does not tell"),
        25: ("mangled this", "this undecided: the code reads a0, but stores through a0 at 0x200190 before any load "
                             "through it: a0 may be a hidden return buffer"),
        26: ("mangled type", "CAiMapLoc " + no_enum),
        28: ("mangled this", "this undecided: the code reads no GPR beyond the declared ones"),
    }
    for i, (group, reason) in want.items():
        e = by[i]
        assert (e["action"], e["reason_group"], e["reason"]) == ("withheld", group, reason), (i, e.get("reason"))
    # CZBombState has a category (its nested enum) but no type: no namespace, so no "no this"
    assert plan["summary"]["mangled"]["withheld_by_reason"]["mangled hidden"] == 4


def test_the_hidden_argument_check_applies_under_every_rule():
    facts = ms.Facts(prototype_image())
    types = ms.Types({"CFoo": [("/project/CFoo", 8)]}, sg.strip_conflict, sg.C_PRIMITIVES)
    # constructor, const member, vtable slot, free function, namespace: a read past the storage withholds
    for address, register in ((0x300000, 6), (0x300020, 5), (0x300030, 6), (0x300040, 5), (0x300050, 5)):
        code = {"reads": {register: 0x1000}, "v0_from_a0": None, "a0_first_access": None}
        with pytest.raises(ms.Withheld, match="beyond the predicted registers"):
            ms.derive(address, facts, types, code, None, {}, lambda t: None)


def test_selection_says_which_pairs_it_takes(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    result = sg.apply(root, path, g, dry_run=True, classes=("exact", "mangled-exact"))
    assert result["skipped"] == {"group mangled-deviating not taken": 1}
    assert result["taken"] == {"mangled-exact": 8}
    result = sg.apply(root, path, g, dry_run=True, classes=("exact", "mangled"))
    assert result["taken"] == {"mangled-deviating": 1, "mangled-exact": 8} and result["skipped"] == {}
    with pytest.raises(names.Refused, match="--classes"):
        sg.apply(root, path, g, dry_run=True, classes=("exact", "mangled-all"))


def test_apply_reads_back_marks_the_record_and_needs_the_class(tmp_path):
    g = make_ghidra()
    root, plan, path = plan_for(tmp_path, g)
    assert sg.apply(root, path, g, dry_run=True)["skipped"] == {"group mangled-deviating not taken": 1,
                                                                "group mangled-exact not taken": 8}
    with pytest.raises(names.Refused, match="--classes"):
        sg.apply(root, path, g, dry_run=True, classes=("mangled",))
    result = sg.apply(root, path, g, dry_run=False, classes=("exact", "mangled"), today="2026-11-27")
    assert result["stopped"] is None and result["side_effects"] == [] and result["analysis_changes"] == []
    assert result["counts"] == {"plate": 9, "prototype": 9}
    assert g.release.signature(0x200010) == "void * __stdcall FUN_00200010(CFoo * this, short __dtor_flags)"
    assert g.release.plates[0x200020].endswith("this from const member, return type unknown.")
    record = names.read_record(root)
    value = record[("0x200000", "prototype")]["value"]
    assert value.endswith(ms.DERIVED_MARK) and value.startswith("void * __stdcall FUN_00200000(CFoo * this, int param_2)")
    done = sg.confirm_saved(root, root / sg.OUT / result["report"], reader_for(g), today="2026-11-27")
    assert done["confirmed"] == 18
    again = sg.apply(root, path, g, dry_run=True, classes=("exact", "mangled"))
    assert again["would_write"] == [] and again["unchanged"] == {"prototype (saved)": 9}


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


def test_code_facts():
    words = [READ_A1, JR_RA, NOP]
    assert ms.entry_reads(words, 0, 3, 0x1000) == {A1: 0x1000}
    words = [(9 << 26) | (A1 << 16) | 1, lw(V0, 0, A1), JR_RA, NOP]  # addiu a1, zero, 1; lw v0, 0(a1)
    assert ms.entry_reads(words, 0, 4, 0x1000) == {}
    facts = ms.entry_facts([sw(V0, 0, A0), move(V0, A0), JR_RA, NOP], 0, 4, 0x1000)
    assert facts["a0_first_access"] == ("store", 0x1000) and facts["v0_from_a0"] == 0x1004
    facts = ms.entry_facts([lw(V0, 0, A0), sw(V0, 4, A0), JR_RA, NOP], 0, 4, 0x1000)
    assert facts["a0_first_access"] == ("load", 0x1000) and facts["v0_from_a0"] is None


def test_enums_are_proven_by_the_release_program():
    g = make_ghidra()
    table = sg.type_table(g, gb.RELEASE_PROGRAM)
    assert sg.proven_enums(g, {"SEAL_STATE", "CAiMapLoc", "Nope"}, table) == {"SEAL_STATE": 1}


# -- placeholder types -----------------------------------------------------------------------


def placeholder_plan(tmp_path, g):
    _, plan, _ = plan_for(tmp_path, g)
    return placeholders.build(plan, dict(g.release.types), prototype_image(), g.release.image, {}, DWARF)


def test_placeholder_plan_lists_missing_names_and_what_they_unlock(tmp_path):
    g = make_ghidra()
    out = placeholder_plan(tmp_path, g)
    by = {r["name"]: r for r in out["types"]}
    assert set(by) == {"CBaz", "CAbsent", "dir"}  # LOD exists hashed: not missing
    assert by["dir"]["create"] == "no: a type name of the program is the same, case ignored"
    assert (by["CAbsent"]["kind"], by["CAbsent"]["path"], by["CAbsent"]["uses"]) == (
        "class", "/project/CAbsent", {"receiver": 1})
    assert by["CBaz"]["kind"] == "struct (incomplete)" and by["CBaz"]["uses"] == {"pointer": 1}
    s = out["summary"]
    assert (s["would_create"], s["functions_unlocked"]) == (2, 1)  # M__7CAbsentCFv; Miss__ is then undecided
    assert s["functions_not_unlocked"] == {"blocked otherwise": 5, "needs a type that is not created": 1,
                                           "then withheld: this": 1}
    assert "packing off" in s["later_layout"] and ".conflict" in s["later_layout"]


def test_placeholder_names_that_collide_or_exist_in_another_spelling_are_left_out():
    table = {"DIR": [("/project/CAiMap/DIR", 1)], "LOD@74fd1e8283": [("/project/unresolved/LOD@74fd1e8283", 8)]}
    present, every = placeholders.spellings(table)
    assert "LOD" in present and "dir" not in present and "dir" in every  # LOD exists hashed; dir collides with DIR, case ignored


def test_placeholder_apply_reads_back_records_confirms_and_stops_on_a_side_effect(tmp_path):
    g = make_ghidra(writes=placeholders.WRITES)
    root = make_root(tmp_path, ROWS)
    plan = sg.build_plan(root, reader_for(g), "gamez/zTest", image=g.release.image,
                         prototype_image=prototype_image(), dwarf=DWARF)
    out = placeholders.build(plan, sg.type_table(g, gb.RELEASE_PROGRAM), prototype_image(), g.release.image, {}, DWARF)
    path = root / placeholders.OUT / "placeholders-plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sg.canonical(out), encoding="utf-8")
    dry = placeholders.apply(root, path, g, dry_run=True)
    assert [w["type_path"] for w in dry["would_write"]] == ["/project/CAbsent", "/project/CBaz"] and g.sent == []
    result = placeholders.apply(root, path, g, dry_run=False, today="2026-11-28")
    assert result["stopped"] is None and len(result["written"]) == 2
    assert g.release.types["CAbsent"] == [("/project/CAbsent", 1)] and g.release.types["CBaz"] == [("/project/CBaz", 1)]
    assert [s["endpoint"] for s in g.sent] == ["import_data_types", "move_data_type_to_category"] * 2
    record = placeholders.read_record(root)
    assert record[("/project/CBaz", placeholders.APPLIED)]["state"] == f"unsaved {result['report']}"
    assert placeholders.confirm_saved(root, root / placeholders.OUT / result["report"], g)["confirmed"] == 2
    again = placeholders.apply(root, path, g, dry_run=True)
    assert again["would_write"] == [] and again["unchanged"] == {"placeholder (saved)": 2}
    # a write that changes another type stops the run at once
    fresh = make_ghidra(writes=placeholders.WRITES)
    fresh.import_side_effect = lambda p: p.types.__setitem__("CFoo", [("/project/CFoo", 12)])
    root2 = make_root(tmp_path / "second", ROWS)
    path2 = root2 / placeholders.OUT / "placeholders-plan.json"
    path2.parent.mkdir(parents=True, exist_ok=True)
    path2.write_text(sg.canonical(out), encoding="utf-8")
    stopped = placeholders.apply(root2, path2, fresh, dry_run=False)
    assert stopped["stop_kind"] == "StopAfter" and stopped["written"] == []
    assert {"unexpected": ["CFoo", "/project/CFoo", 12]} in stopped["table_difference"]
    with pytest.raises(names.Refused, match="still in the program"):
        placeholders.discard_unsaved(root2, root2 / placeholders.OUT / stopped["report"], fresh)
