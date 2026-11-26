"""Vtables as evidence, identical copies, reference kinds, output folders."""
from __future__ import annotations

from pathlib import Path

import compare
import elfimage
import functions
import mips
import pairing
import vtables
from asm import A0, A1, JR_RA, NOP, RA, SP, V0, addiu, frame, jal, lui, lw, sw, unframe
from test_pairing import BASE, body

STUB = [JR_RA, NOP]  # an empty virtual: byte-identical wherever it occurs


def image_with_tables(functions_words, class_tables, role):
    """Functions laid out at BASE, then for each (class name, [function indices]) an RTTI record and a vtable."""

    words, starts = [], []
    for body_words in functions_words:
        starts.append(BASE + 4 * len(words))
        words.extend(body_words)
        while len(words) % 4:
            words.append(0)
    tables = {}
    for name, slots in class_tables:
        text = name.encode() + b"\0"
        text += b"\0" * (-len(text) % 4)
        name_at = BASE + 4 * len(words)
        words.extend(mips.words_of(text))
        record = BASE + 4 * len(words)
        words += [name_at, 0]
        table = BASE + 4 * len(words)
        words += [record, 0] + [starts[k] for k in slots]
        tables[name] = table
    image = elfimage.synthetic(words, BASE, entry=starts[0], role=role)
    spans = [(s, s + 4 * len(fw)) for s, fw in zip(starts, functions_words)]
    fns = functions.build(role[0], image, mips.words_of(image.data), spans, None)
    return image, fns, starts, tables


def matcher_for(proto_functions, proto_tables, release_functions, release_tables):
    pi, P, ps, _ = image_with_tables(proto_functions, proto_tables, "p")
    ri, R, rs, _ = image_with_tables(release_functions, release_tables, "r")
    found_p = vtables.find_tables(pi, {f.address for f in P})
    found_r = vtables.find_tables(ri, {f.address for f in R})
    pairs = vtables.pair_tables(found_p, found_r)
    m = pairing.Matcher(P, R, ps[0], rs[0], pairs)
    m.run()
    return m, ps, rs, found_p, found_r, pairs


def test_tables_are_found_and_paired_by_rtti_name():
    fns = [body(1), STUB, body(2)]
    _, _, _, found_p, found_r, pairs = matcher_for(fns, [("CThing", [1, 2]), ("COther", [0])],
                                                   fns, [("COther", [0]), ("CThing", [1, 2])])
    assert sorted(t.name for t in found_p.values()) == ["COther", "CThing"]
    assert {(p.name, r.name) for p, r in pairs} == {("CThing", "CThing"), ("COther", "COther")}
    assert all(len(p.slots) == len(r.slots) for p, r in pairs)


def test_slot_decides_between_byte_identical_stubs():
    # two empty virtuals in slots 1 and 2; the release swaps their places in the image,
    # so order alone pairs them crosswise; the slots put them right
    proto = [body(1), STUB, STUB, body(2)]
    release = [body(1), STUB, STUB, body(2)]
    m, ps, rs, *_ = matcher_for(proto, [("CSeal", [0, 1, 2, 3])], release, [("CSeal", [0, 2, 1, 3])])
    assert m.pairs[ps[1]].r.address == rs[2] and m.pairs[ps[2]].r.address == rs[1]
    assert "vtable-slot" in m.pairs[ps[1]].evidence
    assert "identical-copy" not in m.pairs[ps[1]].flags


def test_a_rewritten_virtual_without_callers_is_paired_by_its_slot():
    rewritten = [frame(), sw(RA, 0, SP)] + [lw(V0, 4 * k, A1) for k in range(14)] + [lw(RA, 0, SP), JR_RA, unframe()]
    proto = [body(1), body(5, 20), body(2), body(3)]
    release = [body(1), body(2), body(3), rewritten]
    m, ps, rs, *_ = matcher_for(proto, [("CAi", [0, 1, 2])], release, [("CAi", [0, 3, 1])])
    pair = m.pairs[ps[1]]
    assert pair.r.address == rs[3] and "vtable-slot" in pair.evidence and pair.cls == "deviating"


def test_equal_copies_without_evidence_are_flagged():
    proto = [body(1), STUB, body(2), STUB, body(3)]
    release = [body(1), STUB, body(2), STUB, body(3)]
    m, ps, rs, *_ = matcher_for(proto, [], release, [])
    assert "identical-copy" in m.pairs[ps[1]].flags and m.pairs[ps[1]].cls == "exact"
    assert "identical-copy" not in m.pairs[ps[0]].flags


def test_a_pointer_is_not_aligned_with_a_call():
    # prototype: call helper, pass callback X; release: call helper, call a new wrapper W, pass callback Y
    def caller(seed, with_wrapper):
        def build(starts):
            words = [frame(), sw(RA, 0, SP), addiu(A0, 0, seed), jal(starts[1]), NOP]
            if with_wrapper:
                words += [jal(starts[3]), NOP]
            target = starts[2]
            words += [lui(A1, (target + 0x8000) >> 16), addiu(A1, A1, target & 0xFFFF), jal(starts[1]), NOP,
                      lw(RA, 0, SP), JR_RA, unframe()]
            return words
        return build

    callback = body(40, 16)
    callback_release = list(callback)
    callback_release[4] = addiu(V0, A1, 1234)
    wrapper = [frame()] + [lw(V0, 4 * k, A0) for k in range(10)] + [JR_RA, unframe()]
    from test_pairing import match
    proto = [caller(1, False), body(6, 12), callback, body(8)]
    release = [caller(2, True), body(6, 12), callback_release, wrapper, body(8)]
    m, ps, rs = match(proto, release)
    assert m.pairs[ps[2]].r.address == rs[2]
    assert rs[3] not in m.r_paired


def test_sheet_paths_are_flat_and_outputs_follow_out(tmp_path):
    assert compare.sheet_path(tmp_path, "gamez/zSeal", "c") == tmp_path / "build/release/sheets/gamez-zSeal-c.md"
    assert compare.sheet_path(tmp_path, "gamez/zMPEG") == tmp_path / "build/release/sheets/gamez-zMPEG.md"
    assert compare.shown(tmp_path / "x.md", Path("/elsewhere")) == "x.md"
