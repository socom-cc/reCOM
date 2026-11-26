"""Settled owners and flags, copies told apart by their references, string-only pairs."""
from __future__ import annotations

import pytest

import compare
import pairing
import report
from asm import A0, JR_RA, V0, addiu, frame, j, lw, unframe
from test_pairing import body, build, match


def test_settled_rows_with_owner_flags_and_owner_only_ranges(tmp_path):
    path = tmp_path / "settled.tsv"
    path.write_text(
        "release\tprototype\tbasis\tchecker\tdate\towner\tflags\n"
        "0x100100\t0x100200\tstatics\tchecker-x\t2026-11-26\t\tname-changed\n"
        "0x100300-0x100400\t-\towner fixed\tchecker-x\t2026-11-26\tsrc/gamez/zA/a.cpp\n"
        "0x100500\tnew\tcallers\tchecker-x\t2026-11-26\n", encoding="utf-8")
    rows = compare.read_settled(path)
    assert rows[0]["flags"] == ["name-changed"] and rows[0]["span"] is None
    assert rows[1]["span"] == (0x100300, 0x100400) and rows[1]["owner"] == "src/gamez/zA/a.cpp"
    assert rows[2]["prototype"] is None and rows[2]["owner"] == ""
    path.write_text("release\tprototype\tbasis\tchecker\tdate\towner\n0x100300\t-\towner\tchecker-x\t2026-11-26\n",
                    encoding="utf-8")
    with pytest.raises(pairing.SettledError):
        compare.read_settled(path)  # an owner-only row without an owner


def test_settled_owners_and_flags_reach_the_rows():
    rows = [{"release_address": 0x100300, "prototype_address": None, "owner_file": "src/b.cpp", "flags": ["owner-guess"]},
            {"release_address": 0x100100, "prototype_address": 0x100200, "owner_file": "src/a.cpp", "flags": []}]
    settled = [{"release": None, "prototype": None, "span": (0x100300, 0x100400), "owner": "src/a.cpp", "flags": []},
               {"release": 0x100100, "prototype": 0x100200, "span": None, "owner": "", "flags": ["name-changed"]}]
    report.apply_settled_owners(rows, settled)
    assert rows[0]["owner_file"] == "src/a.cpp" and rows[0]["flags"] == ["owner-settled"]
    assert rows[1]["flags"] == ["name-changed"]


def test_equal_thunks_are_told_apart_by_their_jump_targets():
    # two thunks with equal masked bytes jump to different functions; the release swaps their order
    def thunk(target_index):
        return lambda starts: [j(starts[target_index]), addiu(A0, A0, -272)]

    proto = [body(1, 14), body(2, 16), thunk(0), thunk(1), body(3)]
    release = [body(1, 14), body(2, 16), thunk(1), thunk(0), body(3)]
    m, ps, rs = match(proto, release)
    assert m.pairs[ps[2]].r.address == rs[3] and m.pairs[ps[3]].r.address == rs[2]
    assert m.pairs[ps[2]].evidence == {"exact-callee"} and "identical-copy" not in m.pairs[ps[2]].flags


def test_a_string_alone_does_not_pair_unlike_functions():
    loads = [frame()] + [lw(V0, 4 * k, A0) for k in range(20)] + [JR_RA, unframe()]
    P, ps = build("p", [body(1), body(9, 22), body(2)])
    R, rs = build("r", [body(1), loads, body(2)])
    m = pairing.Matcher(P, R, ps[0], rs[0])
    # the same unique string on both sides, nothing else alike
    m.P[1].strings = m.R[1].strings = frozenset({"on_corpse"})
    m.exact_unique()
    assert m.by_strings() == 0 and m.stats["string-rejected-unlike"] == 1
