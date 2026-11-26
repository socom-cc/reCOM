from __future__ import annotations

import pytest

import elfimage
import functions
import mips
import pairing
import report
from asm import A0, A1, JR_RA, NOP, RA, SP, V0, addiu, frame, jal, lw, pad, sw, unframe

BASE = 0x100000


def body(seed: int, length: int = 10) -> list[int]:
    """A distinctive framed function of ``length`` words."""

    words = [frame(), sw(RA, 0, SP)]
    for k in range(length - 5):
        words.append(addiu(V0 if k % 2 else A0, A1, seed * 64 + k))
    words += [lw(RA, 0, SP), JR_RA, unframe()]
    return words


def caller(callee_index: int, seed: int):
    def build(starts):
        return [frame(), sw(RA, 0, SP), addiu(A0, 0, seed), jal(starts[callee_index]), NOP,
                lw(RA, 0, SP), JR_RA, unframe()]
    return build


TINY = [JR_RA, NOP]


def build(side: str, items) -> list:
    """Lay functions out padded to 16 bytes and return their facts; items are lists or builders."""

    sizes = []
    for item in items:
        sizes.append(len(item if isinstance(item, list) else item([0] * len(items))))
    starts = []
    address = BASE
    for size in sizes:
        starts.append(address)
        address += ((size + 3) // 4) * 16
    words: list[int] = []
    for item in items:
        part = list(item if isinstance(item, list) else item(starts))
        words.extend(pad(part))
    image = elfimage.synthetic(words, BASE, entry=starts[0])
    spans = [(s, s + 4 * n) for s, n in zip(starts, sizes)]
    return functions.build(side, image, mips.words_of(image.data), spans, None), starts


def match(proto_items, release_items):
    P, ps = build("p", proto_items)
    R, rs = build("r", release_items)
    matcher = pairing.Matcher(P, R, ps[0], rs[0])
    matcher.run()
    return matcher, ps, rs


def cls(matcher, proto_address):
    pair = matcher.pairs.get(proto_address)
    return pair.cls if pair else "removed"


def test_exact_call_tree_duplicates_new_and_removed():
    c = body(3, 12)
    c_changed = list(c)
    c_changed[4] = addiu(V0, A1, 999)
    c_changed.insert(6, addiu(A0, A1, 1000))
    proto = [caller(2, 1), TINY, c, TINY, body(5), body(6)]
    release = [caller(3, 1), body(9), TINY, c_changed, TINY, body(5)]
    m, ps, rs = match(proto, release)
    assert m.pairs[ps[0]].r.address == rs[0] and cls(m, ps[0]) == "exact"
    assert m.pairs[ps[2]].r.address == rs[3]
    assert cls(m, ps[2]) == "deviating" and "call" in m.pairs[ps[2]].evidence
    # the two identical tiny functions are told apart by their position between anchors
    assert m.pairs[ps[1]].r.address == rs[2] and m.pairs[ps[3]].r.address == rs[4]
    assert "exact-position" in m.pairs[ps[1]].evidence
    assert m.pairs[ps[4]].r.address == rs[5] and cls(m, ps[4]) == "exact"
    assert cls(m, ps[5]) == "removed"
    assert rs[1] not in m.r_paired  # new


def test_exact_bytes_with_a_replaced_callee_are_deviating_in_order():
    target = body(7)
    other = body(8, 14)
    proto = [caller(1, 2), target, body(11)]
    release = [caller(2, 2), target, other, body(11)]
    m, ps, rs = match(proto, release)
    pair = m.pairs[ps[0]]
    assert pair.p.key == pair.r.key
    assert m.pairs[ps[1]].r.address == rs[1]
    assert pair.cls == "deviating" and {"call-conflict", "callee-changed"} <= pair.flags


def test_exact_bytes_with_a_replaced_callee_are_unsure_when_moved():
    target = body(7)
    other = body(8, 14)
    proto = [caller(1, 2), target, body(11), body(12), body(13)]
    release = [target, other, body(11), body(12), body(13), caller(1, 2)]
    m, ps, rs = match(proto, release)
    pair = m.pairs[ps[0]]
    assert pair.r.address == rs[5] and "moved" in pair.flags
    assert pair.cls == "unsure"


@pytest.mark.parametrize("changes,expected", [(1, "deviating"), (24, "unsure"), (40, "new")])
def test_positional_pair_class_follows_similarity(changes, expected):
    original = body(20, 40)
    changed = list(original)
    for k in range(min(changes, 34)):
        changed[2 + k] = addiu(V0, A0, 5000 + k)  # other register, other immediate
    if changes >= 40:
        changed = [frame()] + [lw(V0, 4 * k, A0) for k in range(37)] + [JR_RA, unframe()]
    proto = [body(1), original, body(2)]
    release = [body(1), changed, body(2)]
    m, ps, rs = match(proto, release)
    if expected == "new":
        assert ps[1] not in m.pairs and rs[1] not in m.r_paired
    else:
        assert m.pairs[ps[1]].r.address == rs[1]
        assert m.pairs[ps[1]].cls == expected
        assert "position" in m.pairs[ps[1]].evidence


def test_moved_function_is_found_anywhere():
    moved = body(40, 30)
    moved_changed = list(moved)
    moved_changed[5] = addiu(V0, A0, 77)
    proto = [body(1), moved, body(2), body(3), body(4)]
    release = [body(1), body(2), body(3), body(4), moved_changed]
    m, ps, rs = match(proto, release)
    pair = m.pairs[ps[1]]
    assert pair.r.address == rs[4] and pair.cls == "deviating"
    assert "global" in pair.evidence and "moved" in pair.flags


def test_imm_only_flag_when_only_offsets_change():
    original = body(30, 12)
    changed = [mips.shape(w) | ((w & 0xFFFF) ^ 0x10 if (w >> 26) == 9 and ((w >> 21) & 31) == A1 else w & 0xFFFF)
               for w in original]
    proto = [body(1), original, body(2)]
    release = [body(1), changed, body(2)]
    m, ps, _ = match(proto, release)
    pair = m.pairs[ps[1]]
    assert pair.cls == "deviating" and "imm-only" in pair.flags


def test_weighted_monotone_matching_prefers_weight_and_order():
    chosen = pairing.weighted_monotone_matching([(0, 0, 0.5), (0, 1, 0.9), (1, 0, 0.9), (1, 1, 0.4)])
    assert chosen in ([(0, 1, 0.9)], [(1, 0, 0.9)]) or chosen == [(0, 0, 0.5), (1, 1, 0.4)]
    assert pairing.weighted_monotone_matching([(0, 0, 0.6), (1, 1, 0.6), (2, 1, 0.9)]) == [(0, 0, 0.6), (2, 1, 0.9)]
    assert pairing.increasing_subsequence([(0, 5), (1, 1), (2, 2), (3, 3)]) == {(1, 1), (2, 2), (3, 3)}


def test_tsv_is_deterministic_and_complete():
    loads = [frame()] + [lw(V0, 4 * k, A0) for k in range(14)] + [JR_RA, unframe()]
    m, ps, rs = match([caller(1, 1), body(4), body(5)], [caller(1, 1), body(4), loads])
    rows_a = report.build_rows(m, {}, {})
    rows_b = report.build_rows(m, {}, {})
    text = report.write_tsv(rows_a)
    assert text == report.write_tsv(rows_b)
    lines = text.splitlines()
    assert lines[0].split("\t") == list(report.TSV_COLUMNS)
    assert all(len(line.split("\t")) == len(report.TSV_COLUMNS) for line in lines)
    classes = [line.split("\t")[2] for line in lines[1:]]
    assert classes.count("exact") == 2 and "removed" in classes and "new" in classes


def test_unknown_input_is_refused(tmp_path):
    path = tmp_path / "other.elf"
    path.write_bytes(b"\x7fELF" + bytes(60))
    with pytest.raises(elfimage.InputRefused):
        elfimage.load(path)
