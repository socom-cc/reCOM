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


def image(functions: dict[int, list[int]], data: dict[int, bytes], objects=(), relocations=(), memsz: int = 0x2000,
          code_relocations=None):
    raw = bytearray(4 * WORDS)
    for address, words in functions.items():
        struct.pack_into("<%dI" % len(words), raw, address - BASE, *words)
    for address, blob in data.items():
        raw[address - BASE:address - BASE + len(blob)] = blob
    words = list(struct.unpack("<%dI" % WORDS, bytes(raw)))
    symbols = [elfimage.Symbol(a, s, n, 1, 1) for a, s, n in objects]
    out = elfimage.synthetic(words, BASE, symbols=symbols, memsz=memsz)
    out.relocations = {a: 2 for a in relocations}
    out.relocations.update(code_relocations or {})
    return out


def row(p, r, size_p, size_r=None, cls="exact", flags=()):
    return {"class": cls, "flags": set(flags), "owner": "", "p": p, "r": r, "p_size": size_p,
            "r_size": size_p if size_r is None else size_r}


def run(p_image, r_image, fmap, settled=None, key_check=True):
    p_spans = datapair.Spans((x["p"], x["p"] + x["p_size"]) for x in fmap if x["p"] is not None)
    r_spans = datapair.Spans((x["r"], x["r"] + x["r_size"]) for x in fmap if x["r"] is not None)
    proto = datapair.Side(p_image, p_spans, None)
    release = datapair.Side(r_image, r_spans, None)
    objects = datapair.build_objects(p_image, p_spans, {})
    pairing = datapair.DataPairing(proto, release, objects, fmap, settled=settled, key_check=key_check)
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


# -- settled rows, the key check, code pointers, flags (the data-pairing check) ---------------------

def settled_row(release, proto, symbol, withhold=""):
    return {"release": None if release in ("-", None) else release, "prototype": proto, "symbol": symbol,
            "basis": "test", "checker": "k", "date": "2026-11-27", "decides": release != "-", "withhold": withhold}


def test_settled_file_is_read_and_checked(tmp_path):
    path = tmp_path / "settled-data.tsv"
    path.write_text("release\tprototype\tsymbol\tbasis\tchecker\tdate\twithhold\n"
                    "0x100840\t0x100800\tg_s\tby text\tk\t2026-11-27\t-\n"
                    "removed\t0x100810\t@2\tgone\tk\t2026-11-27\n"
                    "-\t0x100820\t@3\tcheck\tk\t2026-11-27\trole unclear\n", encoding="utf-8")
    rows = datapair.read_settled(path)
    assert [(r["release"], r["prototype"], r["decides"], r["withhold"]) for r in rows] == [
        (0x100840, 0x100800, True, ""), (None, 0x100810, True, ""), (None, 0x100820, False, "role unclear")]
    path.write_text("release\tprototype\tsymbol\tbasis\tchecker\tdate\n-\t0x1\tx\tb\tk\td\n", encoding="utf-8")
    with pytest.raises(datapair.SettledError):
        datapair.read_settled(path)


def test_a_settled_row_decides_and_disagreeing_evidence_is_listed():
    f_p = [*la(A0, DATA), *la(A1, DATA + 0x10), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x40), *la(A1, DATA + 0x50), JR_RA, NOP]
    p = image({BASE: f_p}, {}, [(DATA, 4, "g_a"), (DATA + 0x10, 4, "g_b")])
    r = image({BASE: f_r}, {})
    settled = [settled_row(DATA + 0x60, DATA, "g_a"), settled_row(None, DATA + 0x10, "g_b")]
    pairing = run(p, r, [row(BASE, BASE, 24)], settled=settled)
    a, b = result(pairing, DATA), result(pairing, DATA + 0x10)
    assert a.base == DATA + 0x60 and "settled" in a.evidence and "settled" in a.flags
    assert (DATA + 0x40, "operand-exact", "fn:%#x" % BASE) in a.contradictions
    assert b.cls == "removed" and "settled" in b.flags and b.contradictions
    with pytest.raises(datapair.SettledError):
        run(p, r, [row(BASE, BASE, 24)], settled=[settled_row(DATA + 0x60, DATA, "g_wrong")])


def block(string: int, target: int) -> list[int]:
    """One block of repeated code: load a name, store into a global."""

    return [*la(A0, string), *la(A1, target), sw(V0, 0, A1), NOP]


UNIQUE_A = [addiu(V0, 0, 0x111), addiu(V0, V0, 0x222), addiu(V0, V0, 0x333), addiu(V0, V0, 0x444)]
UNIQUE_B = [addiu(V0, 0, 0x555), addiu(V0, V0, 0x666), addiu(V0, V0, 0x777), addiu(V0, V0, 0x888)]
BLOCKS = 6
NAMES = [("NAME_%d" % k).encode().ljust(16, b"\0") for k in range(BLOCKS)] + [b"NAME_NEW".ljust(16, b"\0")]
GLOBALS = 0x101000  # bss


def shifted_images(with_names: bool = True):
    """The release inserts a block before the old ones and drops the last, so equal-shape stretches
    align the old block k with release block k: one block off."""

    s_p = [DATA + 0x100 + 0x10 * k for k in range(BLOCKS)]
    g_p = [GLOBALS + 4 * k for k in range(BLOCKS)]
    order = ["new"] + list(range(BLOCKS - 1))
    s_r = {k: DATA + 0x200 + 0x10 * n for n, k in enumerate(order)}
    g_r = {k: GLOBALS + 0x100 + 4 * n for n, k in enumerate(order)}
    f_p = UNIQUE_A + [w for k in range(BLOCKS) for w in block(s_p[k], g_p[k])] + UNIQUE_B + [JR_RA, NOP]
    f_r = UNIQUE_A + [w for k in order for w in block(s_r[k], g_r[k])] + UNIQUE_B + [JR_RA, NOP]
    data_p = {s_p[k]: NAMES[k] for k in range(BLOCKS)} if with_names else {}
    data_r = {s_r[k]: NAMES[-1 if k == "new" else k] for k in order} if with_names else {}
    objects = [(s_p[k], 16, "@%d" % k) for k in range(BLOCKS)] + [(g_p[k], 4, "g_%d" % k) for k in range(BLOCKS)]
    p = image({BASE: f_p}, data_p, objects)
    r = image({BASE: f_r}, data_r)
    return p, r, [row(BASE, BASE, 4 * len(f_p), cls="deviating")], g_r


def test_a_whole_block_shift_is_found_by_the_key_the_block_carries():
    p, r, fmap, g_r = shifted_images()
    unchecked = run(p, r, fmap, key_check=False)
    assert result(unchecked, GLOBALS).base == g_r["new"]  # the old failure: one block off
    pairing = run(p, r, fmap)
    assert result(pairing, DATA + 0x100).base == DATA + 0x210  # the string by its text (tier 0)
    assert result(pairing, GLOBALS).base is None  # its aligned use sits next to a key that leads elsewhere
    assert any(k[0] == GLOBALS and "@0" in k[3] for k in pairing.key_rejected)


def test_repeated_code_without_a_key_does_not_vote():
    p, r, fmap, g_r = shifted_images(with_names=False)
    middle = GLOBALS + 8
    assert result(run(p, r, fmap, key_check=False), middle).base == g_r[1]  # one block off
    pairing = run(p, r, fmap)
    assert result(pairing, middle).cls in ("unsure", "removed")  # at most an order proposal on .bss
    assert any(k[0] == middle and k[3] == "repeated code, no key" for k in pairing.key_rejected)


def test_a_pointer_into_a_function_body_maps_to_the_same_offset_of_an_exact_pair():
    f = [*la(A0, DATA), NOP, NOP, JR_RA, NOP]
    table_p = struct.pack("<II", BASE + 8, BASE + 12)
    p = image({BASE: f}, {DATA: table_p}, [(DATA, 8, "@3679")], relocations=[DATA, DATA + 4])
    same = image({BASE: f}, {DATA: table_p})
    moved = image({BASE: f}, {DATA: struct.pack("<II", BASE + 8, BASE + 16)})
    assert result(run(p, same, [row(BASE, BASE, 24)]), DATA).content == "equal"
    changed = result(run(p, moved, [row(BASE, BASE, 24)]), DATA)
    assert changed.cls == "deviating" and changed.content == "changed" and "content-changed" in changed.flags


def test_single_aligned_pairs_are_flagged_and_withheld_when_their_bytes_differ():
    f_p = [*la(A0, DATA), lw(V0, 0, A0), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x20), lw(V0, 0, A0), JR_RA, NOP]
    p = image({BASE: f_p}, {DATA: b"\x01\x02\x03\x04"}, [(DATA, 4, "g_value"), (DATA + 0x10, 4, "g_next")])
    r = image({BASE: f_r}, {DATA + 0x20: b"\x09\x02\x03\x04"})
    fmap = [row(BASE, BASE, 16, cls="deviating", flags=("imm-only",))]
    got = result(run(p, r, fmap), DATA)
    assert got.base == DATA + 0x20 and "single-aligned" in got.flags
    assert got.withhold == ["single aligned witness, bytes differ"]
    withheld = run(p, r, fmap, settled=[settled_row("-", DATA, "g_value", "role unclear")])
    assert "role unclear" in result(withheld, DATA).withhold


def test_a_changed_text_takes_its_size_from_the_release():
    f = [*la(A0, DATA), JR_RA, NOP]
    p = image({BASE: f}, {DATA: b"AUTO AIM\0\0\0\0"}, [(DATA, 12, "@2861")])
    r = image({BASE: f}, {DATA: b"AIM ASSIST\0\0"})
    got = result(run(p, r, [row(BASE, BASE, 16)]), DATA)
    assert got.cls == "deviating" and "size-from-release" in got.flags


def test_constants_read_as_addresses_and_unrelocated_address_words_are_flagged():
    # g_a has a relocated use; g_ptr's use carries none and g_ptr holds &g_a without a relocation
    f_p = [*la(A0, DATA), *la(A1, DATA + 0x10), JR_RA, NOP]
    f_r = [*la(A0, DATA + 0x40), *la(A1, DATA + 0x50), JR_RA, NOP]
    relocs = {BASE: 5, BASE + 4: 6}
    p = image({BASE: f_p}, {DATA: b"\x01\x02\x03\x04", DATA + 0x10: struct.pack("<I", DATA)},
              [(DATA, 4, "g_a"), (DATA + 0x10, 4, "g_ptr")], code_relocations=relocs)
    r = image({BASE: f_r}, {DATA + 0x40: b"\x01\x02\x03\x04", DATA + 0x50: struct.pack("<I", DATA + 0x40)})
    pairing = run(p, r, [row(BASE, BASE, 24)])
    a, ptr = result(pairing, DATA), result(pairing, DATA + 0x10)
    assert "constant-as-address" not in a.flags
    assert "constant-as-address" in ptr.flags
    assert ptr.content == "equal" and "unrelocated-word" in ptr.flags and "content-changed" not in ptr.flags
