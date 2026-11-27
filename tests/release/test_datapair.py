"""Data pairing (tools/release/datapair.py) on small synthetic images."""
from __future__ import annotations

import struct

import pytest

import dataflow
import datapair
import elfimage
from asm import A0, A1, AT, GP, JR_RA, NOP, V0, addiu, b, beq, jal, lui, lw, sw

BASE = 0x100000
DATA = 0x100800  # data objects start here in both images
WORDS = 0x400  # 4 KB of file-backed image; bss follows


def la(register: int, address: int) -> list[int]:
    hi = (address + 0x8000) >> 16
    return [lui(register, hi), addiu(register, register, address - (hi << 16))]


def hi_of(address: int) -> int:
    return (address + 0x8000) >> 16


def lo_of(address: int) -> int:
    return address - (hi_of(address) << 16)


def image(functions: dict[int, list[int]], data: dict[int, bytes], objects=(), relocations=(), memsz: int = 0x2000):
    raw = bytearray(4 * WORDS)
    for address, words in functions.items():
        struct.pack_into("<%dI" % len(words), raw, address - BASE, *words)
    for address, blob in data.items():
        raw[address - BASE:address - BASE + len(blob)] = blob
    words = list(struct.unpack("<%dI" % WORDS, bytes(raw)))
    symbols = [elfimage.Symbol(a, s, n, 1, 1) for a, s, n in objects]
    out = elfimage.synthetic(words, BASE, symbols=symbols, memsz=memsz)
    out.relocations = {a: 2 for a in relocations}
    return out


def row(p, r, size_p, size_r=None, cls="exact", flags=()):
    return {"class": cls, "flags": set(flags), "owner": "", "p": p, "r": r, "p_size": size_p,
            "r_size": size_p if size_r is None else size_r}


def run(p_image, r_image, fmap):
    p_spans = datapair.Spans((x["p"], x["p"] + x["p_size"]) for x in fmap if x["p"] is not None)
    r_spans = datapair.Spans((x["r"], x["r"] + x["r_size"]) for x in fmap if x["r"] is not None)
    proto = datapair.Side(p_image, p_spans, None)
    release = datapair.Side(r_image, r_spans, None)
    objects = datapair.build_objects(p_image, p_spans, {})
    pairing = datapair.DataPairing(proto, release, objects, fmap)
    stats = {}
    from collections import Counter
    stats = Counter()
    pairs = [x for x in fmap if x["p"] is not None and x["r"] is not None and x["class"] in ("exact", "deviating")]
    pairing.run(datapair.code_witnesses(pairs, proto, release, stats), [], [])
    datapair.finish(pairing)
    return pairing


def result(pairing, address):
    return pairing.results[address]


# -- dataflow --------------------------------------------------------------------------------

def test_references_follow_hi_lo_pairs_register_offsets_and_gp():
    words = [*la(A0, 0x451230), lw(V0, 8, A0), lui(AT, 0x45), lw(A1, 0x1240, AT), lw(V0, 0x10, GP), JR_RA, NOP]
    refs = dataflow.references(words, 0, len(words), 0x100000, 0x470000)
    got = [(r.index, r.kind, r.address, r.off, r.defs, r.gp) for r in refs]
    assert got == [(1, "addr", 0x451230, 0, (0,), False),
                   (2, "load", 0x451230, 8, (0, 1), False),
                   (4, "load", 0x451240, 0, (3,), False),
                   (5, "load", 0x470010, 0, (), True)]


def test_a_call_clobbers_and_a_merge_of_two_values_drops_the_register():
    after_call = [lui(A0, 0x45), jal(0x100100), NOP, lw(V0, 0x10, A0), JR_RA, NOP]
    assert [r.index for r in dataflow.references(after_call, 0, 6, BASE, None)] == []
    # a0 holds 0x45xxxx on one path and 0x46xxxx on the other: the load after the join has no address
    merged = [beq(A1, 0, 3), lui(A0, 0x45), b(2), NOP, lui(A0, 0x46), lw(V0, 0x10, A0), JR_RA, NOP]
    assert [r for r in dataflow.references(merged, 0, 8, BASE, None) if r.index == 5] == []


def test_alignment_skips_repeated_blocks_and_keeps_unique_ones_and_equal_shape_gaps():
    unique = (1, 2, 3, 4)
    repeated = (7, 7, 8, 9)
    pm = unique + (50,) + repeated + repeated
    rm = unique + (51,) + repeated + (60,) + repeated
    shapes_p = tuple(range(len(pm)))
    shapes_r = tuple(range(len(rm)))
    mapping = datapair.alignment(pm, rm, shapes_p, shapes_r)
    assert all(mapping[k] == k for k in range(4))
    assert 5 not in mapping and 9 not in mapping  # the repeated block is not used
    # a stretch of equal length and equal shapes between two unique blocks aligns
    pm = (1, 2, 3, 4, 90, 5, 6, 7, 8)
    rm = (1, 2, 3, 4, 91, 5, 6, 7, 8)
    mapping = datapair.alignment(pm, rm, (0,) * 9, (0,) * 9)
    assert mapping[4] == 4


def test_gp_is_found_where_the_entry_function_moves_it_into_gp():
    words = [*la(A0, 0x123450), (A0 << 21) | (GP << 11) | 0x25, JR_RA, NOP] + [0] * 60
    img = elfimage.synthetic(words, BASE)
    assert datapair.gp_of(img, words, 16) == 0x123450


# -- pairing ---------------------------------------------------------------------------------

STRING = b"HELLO, RELEASE\0\0"


def test_exact_operands_pair_an_object_and_its_field_not_a_new_object():
    # f loads &table and table+4: the object is paired, the field access stays inside it
    f_p = [*la(A0, DATA), lw(V0, 4, A0), lui(AT, hi_of(DATA + 8)), lw(A1, lo_of(DATA + 8), AT), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x40), lw(V0, 4, A0), lui(AT, hi_of(DATA + 0x48)), lw(A1, lo_of(DATA + 0x48), AT), JR_RA, NOP]
    p = image({BASE: f_p}, {DATA: bytes(range(16))}, [(DATA, 16, "g_table")])
    r = image({BASE: f_r}, {DATA + 0x40: bytes(range(16))})
    pairing = run(p, r, [row(BASE, BASE, 24)])
    got = result(pairing, DATA)
    assert got.base == DATA + 0x40
    assert got.evidence == {"operand-exact": 1, "content": 1} and got.witnesses == 2
    assert len(pairing.index.objects) == 1  # no object was invented at +8
    assert got.content == "equal" and "offset-changed" not in got.flags


def test_a_grown_structure_is_flagged_offset_outside_through_an_imm_only_pair():
    f_p = [*la(A0, DATA), lw(V0, 4, A0), sw(V0, 12, A0), JR_RA, NOP]
    f_r = [*la(A0, DATA), lw(V0, 4, A0), sw(V0, 20, A0), JR_RA, NOP]  # the field moved past the old end
    p = image({BASE: f_p}, {}, [(DATA, 16, "g_state"), (DATA + 0x40, 4, "g_next")])
    r = image({BASE: f_r}, {})
    pairing = run(p, r, [row(BASE, BASE, 20, cls="deviating", flags=("imm-only",))])
    got = result(pairing, DATA)
    assert got.base == DATA
    assert {"offset-changed", "offset-outside"} <= got.flags
    assert (12, 20, "fn:%#x" % BASE) in got.field_moves
    assert got.cls == "deviating"


def test_unique_content_pairs_and_duplicates_are_identical_copies():
    p = image({}, {DATA: STRING, DATA + 0x20: b"TWICE\0\0\0", DATA + 0x28: b"TWICE\0\0\0"},
              [(DATA, 16, "@1"), (DATA + 0x20, 8, "@2"), (DATA + 0x28, 8, "@3")])
    r = image({}, {DATA + 0x100: STRING, DATA + 0x140: b"TWICE\0\0\0"})
    pairing = run(p, r, [])
    assert result(pairing, DATA).base == DATA + 0x100
    assert result(pairing, DATA).evidence == {"content": 1}
    assert result(pairing, DATA + 0x20).base is None
    assert "identical-copy" in result(pairing, DATA + 0x20).flags


def test_a_pointer_in_a_paired_table_pairs_its_target():
    # f loads the table; the table's first word points to a string
    f_p = [*la(A0, DATA), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x80), JR_RA, NOP]
    p = image({BASE: f_p}, {DATA: struct.pack("<II", DATA + 0x20, 7), DATA + 0x20: b"AB\0\0"},
              [(DATA, 8, "g_names"), (DATA + 0x20, 4, "@9")], relocations=[DATA])
    r = image({BASE: f_r}, {DATA + 0x80: struct.pack("<II", DATA + 0x60, 7), DATA + 0x60: b"AB\0\0",
                            DATA + 0x70: b"AB\0\0"})
    pairing = run(p, r, [row(BASE, BASE, 16)])
    assert result(pairing, DATA).base == DATA + 0x80
    target = result(pairing, DATA + 0x20)
    assert target.base == DATA + 0x60 and target.evidence == {"pointer": 1}


def test_disagreeing_exact_witnesses_are_a_conflict_not_a_vote():
    f1_p, f1_r = [*la(A0, DATA), JR_RA, NOP], [*la(A0, DATA + 0x10), JR_RA, NOP]
    f2_p, f2_r = [*la(A1, DATA), JR_RA, NOP], [*la(A1, DATA + 0x20), JR_RA, NOP]
    p = image({BASE: f1_p, BASE + 0x20: f2_p}, {}, [(DATA, 4, "g_x")])
    r = image({BASE: f1_r, BASE + 0x20: f2_r}, {})
    pairing = run(p, r, [row(BASE, BASE, 16), row(BASE + 0x20, BASE + 0x20, 16)])
    got = result(pairing, DATA)
    assert got.base is None and got.cls == "unsure" and "witness-conflict" in got.flags
    assert [b for b, _ in got.conflict] == [DATA + 0x10, DATA + 0x20]


def test_a_literal_is_its_bytes_and_the_shifted_code_use_is_listed():
    # the exact function now uses the string before it (an enum entry was inserted)
    f_p = [*la(A0, DATA + 0x10), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x10), JR_RA, NOP]
    p = image({BASE: f_p}, {DATA + 0x10: b"CMD_ONOFF\0\0\0\0\0\0\0"}, [(DATA + 0x10, 16, "@3643")])
    r = image({BASE: f_r}, {DATA + 0x10: b"CMD_RESET\0\0\0\0\0\0\0", DATA + 0x20: b"CMD_ONOFF\0\0\0\0\0\0\0"})
    pairing = run(p, r, [row(BASE, BASE, 16)])
    got = result(pairing, DATA + 0x10)
    assert got.base == DATA + 0x20 and got.tier == 0
    assert "contradicted" in got.flags and got.contradictions == [(DATA + 0x10, "operand-exact", "fn:%#x" % BASE)]


def test_order_proposes_and_settles_only_on_equal_nonzero_bytes():
    f_p = [*la(A0, DATA), *la(A1, DATA + 0x30), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x100), *la(A1, DATA + 0x130), JR_RA, NOP]
    blob = b"\x01\x02\x03\x04"
    p = image({BASE: f_p}, {DATA + 0x10: blob, DATA + 0x14: blob}, [
        (DATA, 4, "g_a"), (DATA + 0x10, 4, "g_mid"), (DATA + 0x14, 4, "g_twin"), (DATA + 0x20, 4, "g_zero"),
        (DATA + 0x30, 4, "g_b")])
    r = image({BASE: f_r}, {DATA + 0x110: blob, DATA + 0x114: blob})
    pairing = run(p, r, [row(BASE, BASE, 24)])
    mid = result(pairing, DATA + 0x10)
    assert mid.base == DATA + 0x110 and mid.cls == "exact" and "order-only" in mid.flags
    zero = result(pairing, DATA + 0x20)
    assert zero.base == DATA + 0x120 and zero.cls == "unsure"  # zeros prove nothing


def test_tsv_is_deterministic_and_has_the_columns():
    f_p = [*la(A0, DATA), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x40), JR_RA, NOP]
    p = image({BASE: f_p}, {DATA: STRING}, [(DATA, 16, "g_s")])
    r = image({BASE: f_r}, {DATA + 0x40: STRING})
    texts = []
    for _ in range(2):
        pairing = run(p, r, [row(BASE, BASE, 16)])
        texts.append(datapair.write_tsv(datapair.tsv_rows(pairing, [])))
    assert texts[0] == texts[1]
    header, line = texts[0].splitlines()
    assert tuple(header.split("\t")) == datapair.COLUMNS
    cells = dict(zip(datapair.COLUMNS, line.split("\t")))
    assert cells["release_address"] == "%#x" % (DATA + 0x40) and cells["class"] == "exact"
    assert cells["evidence"] == "operand-exact:1,content:1" and cells["witnesses"] == "2"


def test_section_labels_follow_envelopes_and_linker_symbols():
    envelopes = [(0x100, 0x200, ".data"), (0x300, 0x400, ".bss")]
    boundaries = [(0x220, "_fbss")]
    assert datapair.section_label(envelopes, boundaries, 0x150) == ".data"
    assert datapair.section_label(envelopes, boundaries, 0x210) == "between .data and .bss"
    assert datapair.section_label(envelopes, boundaries, 0x230) == "between .data and .bss from _fbss"


def test_unknown_input_is_refused(tmp_path):
    (tmp_path / "support").mkdir()
    (tmp_path / "support" / "socom.elf").write_bytes(b"\x7fELF not really")
    (tmp_path / "support" / "SCUS_971.34").write_bytes(b"\x7fELF not really")
    with pytest.raises(elfimage.InputRefused):
        datapair.run(tmp_path, write=False)
