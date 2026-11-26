"""Tables of named entries: found, paired by key, handlers paired (stubs included)."""
from __future__ import annotations

import elfimage
import functions
import mips
import pairing
import tables
from asm import A0, JR_RA, NOP, V0, addiu, lw
from test_pairing import BASE, body

STUB0 = [JR_RA, addiu(V0, 0, 0)]


def image_with_table(functions_words, entries, role, stride=12):
    """Functions at BASE, then name strings, then a table of {name, handler, id} records."""

    words, starts = [], []
    for fw in functions_words:
        starts.append(BASE + 4 * len(words))
        words.extend(fw)
        while len(words) % 4:
            words.append(0)
    name_at = {}
    for name, _, _ in entries:
        text = name.encode() + b"\0"
        text += b"\0" * (-len(text) % 4)
        name_at[name] = BASE + 4 * len(words)
        words.extend(mips.words_of(text))
    table = BASE + 4 * len(words)
    for name, index, ident in entries:
        record = [name_at[name], starts[index], ident]
        words.extend(record + [0] * (stride // 4 - 3))
    image = elfimage.synthetic(words, BASE, entry=starts[0], role=role)
    spans = [(s, s + 4 * len(fw)) for s, fw in zip(starts, functions_words)]
    fns = functions.build(role[0], image, mips.words_of(image.data), spans, None)
    return image, fns, starts, table


def test_string_keyed_tables_pair_their_handlers_and_spot_stubs():
    handler = [addiu(V0, 0, 3)] + [lw(V0, 4 * k, A0) for k in range(10)] + [JR_RA, NOP]
    proto_fns = [body(1), handler, body(2), body(3), STUB0]
    release_fns = [body(1), STUB0, body(2), body(3), STUB0]  # the handler was emptied
    p_entries = [("NetCnfInit", 0, 0x6c), ("NetCnfOpen", 1, 0x6d), ("NetCnfClose", 4, 0x6e)]
    r_entries = [("NetCnfInit", 0, 0x6c), ("NetCnfClose", 4, 0x6e), ("NetCnfOpen", 1, 0x6d), ("NewOne", 2, 0x6f)]
    pi, P, ps, pt = image_with_table(proto_fns, p_entries, "p")
    ri, R, rs, rt = image_with_table(release_fns, r_entries, "r")
    found_p = tables.find_tables(pi, {f.address for f in P}, [(f.address, f.end) for f in P])
    found_r = tables.find_tables(ri, {f.address for f in R}, [(f.address, f.end) for f in R])
    assert [(t.address, t.kind, t.stride) for t in found_p] == [(pt + 4, "string", 12)]
    pairs = tables.pair_tables(found_p, found_r)
    assert len(pairs) == 1
    correspondences = tables.entry_correspondences(pairs)
    assert {(a, b) for a, b, _ in correspondences} == {(ps[0], rs[0]), (ps[1], rs[1]), (ps[4], rs[4])}
    m = pairing.Matcher(P, R, ps[0], rs[0], None, correspondences)
    m.run()
    emptied = m.pairs[ps[1]]
    assert emptied.r.address == rs[1] and "table-entry" in emptied.evidence
    assert emptied.cls == "deviating" and "stubbed" in emptied.flags
    # the two byte-identical stubs: the entry decides which is which
    assert m.pairs[ps[4]].r.address == rs[4] and "identical-copy" not in m.pairs[ps[4]].flags


def test_id_keys_and_jaccard_threshold():
    p = tables.EntryTable(0, 8, "id", [(1, 10), (2, 11), (3, 12), (4, 13), (5, 14)])
    r = tables.EntryTable(4, 8, "id", [(1, 20), (2, 21), (3, 22), (4, 23), (5, 24), (6, 25)])
    other = tables.EntryTable(8, 8, "id", [(1, 30), (9, 31), (8, 32)])
    assert tables.pair_tables([p], [r, other]) == [(p, r)]
    assert tables.pair_tables([other], [r]) == []  # ids repeat across tables: too little in common
