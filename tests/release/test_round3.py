"""One-to-one slots, unique-anchor alignment, check lists and the richer sheet."""
from __future__ import annotations

import elfimage
import lists
import pairing
import protofacts
import report
import sheets
from asm import A0, A1, A2, JR_RA, NOP, RA, SP, V0, addiu, frame, jal, lui, lw, sw, unframe
from test_pairing import BASE, body, build, match
from test_round2 import call_builder


def loads(count: int, base_register: int = A0) -> list[int]:
    return [frame()] + [lw(V0, 4 * k, base_register) for k in range(count)] + [JR_RA, unframe()]


def test_patience_blocks_align_unique_tokens_first():
    # "S" repeats; the unique "I" must line up with its own occurrence, not leave a one-sided gap
    a = ["S", "I", "S", "V"]
    b = ["S", "S", "I", "V"]
    blocks = pairing.patience_blocks(a, b)
    assert blocks[-1] == (len(a), len(b), 0)
    matched = {(i + k, j + k) for i, j, size in blocks for k in range(size)}
    assert (1, 2) in matched and (3, 3) in matched


def test_address_slot_pairs_a_rewritten_function_alone_between_anchors():
    original = body(20, 30)
    rewritten = [frame(), sw(RA, 0, SP)] + [addiu(A2, A1, 900 + k) for k in range(20)] + [lw(RA, 0, SP), JR_RA, unframe()]
    proto = [body(1), body(2), original, body(3), body(4)]
    release = [body(1), body(2), rewritten, body(3), body(4)]
    m, ps, rs = match(proto, release)
    pair = m.pairs[ps[2]]
    assert pair.r.address == rs[2] and "slot-only" in pair.evidence and pair.cls == "deviating"


def test_address_slot_refuses_functions_of_unlike_shape():
    # a truly removed table walker and a truly new tiny stub sharing a gap stay unpaired
    proto = [body(1), body(2), loads(60), body(3), body(4)]
    release = [body(1), body(2), [JR_RA, addiu(V0, 0, 1)], body(3), body(4)]
    m, ps, rs = match(proto, release)
    assert ps[2] not in m.pairs and rs[2] not in m.r_paired


def pointer_caller(slot_index: int, seed: int):
    """Registers a callback: loads the address of item ``slot_index`` between two calls of item 1."""

    def build_words(starts):
        target = starts[slot_index]
        return [frame(), sw(RA, 0, SP), addiu(A0, 0, seed), jal(starts[1]), NOP,
                lui(A1, (target + 0x8000) >> 16), addiu(A1, A1, target & 0xFFFF), jal(starts[1]), NOP,
                lw(RA, 0, SP), JR_RA, unframe()]
    return build_words


def test_reference_slot_pairs_the_only_pointer_between_the_same_anchors():
    # the registering caller changed (another argument), so only its reference list can tell
    proto = [pointer_caller(3, 5), body(6, 12), body(7), [JR_RA, addiu(V0, 0, 1)], body(8)]
    release = [pointer_caller(4, 9), body(6, 12), body(7), body(30), loads(8, A1), body(8)]
    m, ps, rs = match(proto, release)
    pair = m.pairs.get(ps[3])
    assert pair is not None and pair.r.address == rs[4]
    assert pair.evidence == {"slot-only"} and pair.cls == "deviating"


def test_small_function_operations_override_the_gram_prefilter():
    p_fn = [frame(), lw(V0, 0, A0), lw(A1, 4, A0), addiu(V0, V0, 1), JR_RA, unframe()]
    r_fn = [frame(), lw(A2, 8, A1), lw(V0, 12, A1), addiu(A2, A2, 2), JR_RA, unframe()]
    P, _ = build("p", [p_fn])
    R, _ = build("r", [r_fn])
    matcher = pairing.Matcher(P, R, P[0].address, R[0].address)
    assert pairing.jaccard(P[0].grams, R[0].grams) < pairing.GRAM_PREFILTER
    assert matcher._score(P[0], R[0]) is not None


def _rows(module_files):
    rows = []
    address = BASE
    for owner, classes in module_files:
        for cls in classes:
            rows.append({"release_address": address if cls != "removed" else None, "release_size": 16,
                         "prototype_address": None if cls == "new" else address, "prototype_size": 16,
                         "class": cls, "evidence": [], "flags": [], "owner_file": owner, "prototype_symbol": "f",
                         "prototype_classification": "authored", "prototype_library": "", "neighbour_group": ""})
            address += 16
    return rows


class _FakeMatcher:
    def __init__(self, rows):
        self.P = [type("F", (), {"address": r["prototype_address"]}) for r in rows if r["prototype_address"]]
        self.p_index = {f.address: i for i, f in enumerate(self.P)}
        self.pairs = {}


def test_lists_split_balances_work_and_samples_deterministically():
    files = [("src/gamez/zX/a.cpp", ["unsure"] * 6 + ["deviating"] * 20 + ["exact"] * 5),
             ("src/gamez/zX/b.cpp", ["new"] * 4 + ["deviating"] * 10),
             ("src/gamez/zX/c.cpp", ["removed"] * 4 + ["deviating"] * 10 + ["exact"] * 3)]
    rows = _rows(files)
    unplaced = {"release_address": rows[3]["release_address"] + 8, "release_size": 8, "prototype_address": None,
                "prototype_size": None, "class": "new", "evidence": [], "flags": [], "owner_file": "",
                "prototype_symbol": "", "prototype_classification": "", "prototype_library": "", "neighbour_group": ""}
    rows.append(unplaced)
    matcher = _FakeMatcher(rows)
    first = lists.split("gamez/zX", rows, matcher, 2, sample=5)
    second = lists.split("gamez/zX", rows, matcher, 2, sample=5)
    assert [[lists.key(r) for r in x["sample"]] for x in first] == [[lists.key(r) for r in x["sample"]] for x in second]
    minutes = sorted(x["minutes"] for x in first)
    assert minutes[1] - minutes[0] <= 12
    assert sum(len(x["uncertain"]) for x in first) == 6 + 4 + 4 + 1  # the unplaced new function joined a list
    assert all(len(x["sample"]) <= 5 for x in first)
    assert sum(x["exact"] for x in first) == 8
    text = lists.render("gamez/zX", first[0], 5)
    assert "# Check list gamez/zX-a" in text and "Exact rows in this list" in text


def test_sheet_names_data_and_shows_slots_and_full_diffs():
    original = body(20, 30)
    rewritten = [frame(), sw(RA, 0, SP)] + [addiu(A2, A1, 900 + k) for k in range(20)] + [lw(RA, 0, SP), JR_RA, unframe()]
    proto = [body(1), call_builder(1, seed=2), original, body(3), loads(40), body(4)]
    release = [body(1), call_builder(1, seed=2), rewritten, body(3), body(4), body(31, 8)]
    m, ps, rs = match(proto, release)
    facts = {a: protofacts.ProtoFunction(a, m.p_by[a].size, ["f%x" % a]) for a in ps}
    for f in facts.values():
        f.owner, f.owner_kind = "src/gamez/zTest/t.cpp", "defines"
    rows = report.build_rows(m, facts, {})
    text = sheets.module_sheet("gamez/zTest", m, rows, facts)
    assert "- slot: between" in text  # removed and new rows show their slot
    assert "* +" in text and "  +000" in text  # a full side-by-side listing, changed lines marked
    image = elfimage.synthetic([0] * 8, BASE, symbols=[elfimage.Symbol(BASE + 8, 4, "g_count", 1, 1)])
    namer = sheets.DataNamer(m, image, image)
    assert namer.proto(BASE + 8) == "g_count" and namer.proto(BASE + 10) == "g_count+0x2"
