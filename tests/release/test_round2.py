"""Reference alignment, string evidence, global guards, owner moves, settled pairs and sheets."""
from __future__ import annotations

import pytest

import compare
import elfimage
import functions
import mips
import pairing
import protofacts
import report
import sheets
from asm import A0, A1, A2, JR_RA, NOP, RA, SP, V0, addiu, frame, jal, lui, lw, sw, unframe
from test_pairing import BASE, body, match

STRING_AT = BASE + 0x4000


def call_builder(*targets, seed: int = 0, loads=()):
    """A framed function calling the given item indices in order (``("ptr", i)`` loads its address)."""

    def build(starts):
        words = [frame(), sw(RA, 0, SP), addiu(A0, 0, seed)]
        for target in targets:
            if isinstance(target, tuple):
                address = starts[target[1]]
                words += [lui(A0, (address + 0x8000) >> 16), addiu(A0, A0, address & 0xFFFF), jal(starts[0]), NOP]
            else:
                words += [jal(starts[target]), NOP]
        words += [lw(RA, 0, SP), JR_RA, unframe()]
        return words
    return build


def rewritten(seed: int, length: int):
    """A body whose operations match ``body(seed, length)`` but whose registers and offsets do not."""

    words = [frame(), sw(RA, 0, SP)]
    for k in range(length - 5):
        words.append(addiu(A2 if k % 2 else V0, A0, 7000 + seed * 64 + k))
    words += [lw(RA, 0, SP), JR_RA, unframe()]
    return words


def test_references_include_loaded_function_addresses():
    fns, starts = _build([call_builder(("ptr", 1)), body(3)])
    caller = fns[0]
    assert starts[1] in [t for _, t in caller.references()]
    assert (caller.code_refs and caller.code_refs[0][1] == starts[1])


def _build(items):
    from test_pairing import build
    return build("p", items)


def test_deviating_parent_aligns_its_reference_list():
    # the parent changed (an extra call to a new helper); its second callee was rewritten
    proto = [call_builder(1, 2, seed=1), body(4, 12), rewritten(5, 30), body(6, 12)]
    release = [call_builder(1, 3, 2, seed=1), body(4, 12), rewritten(5, 30)[:-3] + [addiu(V0, A0, 1)] + rewritten(5, 30)[-3:],
               body(40, 9), body(6, 12)]
    release[2] = [w if (w >> 26) != 9 or ((w >> 21) & 31) != A0 else addiu(A1, A0, (w & 0xFFFF) ^ 0x30)
                  for w in release[2]]
    m, ps, rs = match(proto, release)
    assert m.pairs[ps[0]].cls == "deviating"
    pair = m.pairs[ps[2]]
    assert pair.r.address == rs[2]
    assert pair.evidence & {"call", "call-deviating"}
    assert rs[3] not in m.r_paired  # the new helper stays new


def test_string_unique_over_all_functions_and_file_names_ignored():
    image_words = [0] * 0x1400
    data = b"zar_main.cpp\0only here\0"
    data += b"\0" * (-len(data) % 4)
    strings_at = len(image_words)
    image_words += list(mips.words_of(data))
    image = elfimage.synthetic(image_words, BASE)
    address = BASE + 4 * strings_at
    words = mips.words_of(image.data)
    # a debug-allocator style call: a1 = file name, a2 = line
    code = [lui(A1, (address + 0x8000) >> 16), addiu(A1, A1, address & 0xFFFF), addiu(A2, 0, 1108),
            lui(A0, (address + 13 + 0x8000) >> 16), addiu(A0, A0, (address + 13) & 0xFFFF), JR_RA, NOP]
    for k, w in enumerate(code):
        words[k] = w
    image = elfimage.synthetic(list(words), BASE)
    (fn,) = functions.build("p", image, mips.words_of(image.data), [(BASE, BASE + 4 * len(code))], None)
    assert fn.file_strings == {"zar_main.cpp"}
    assert "zar_main.cpp" not in fn.strings and "only here" in fn.strings
    assert ("zar_main.cpp", 1108) in fn.lines


def test_small_global_look_alike_needs_agreeing_callers():
    dtor = body(70, 20)
    look_alike = list(dtor)
    look_alike[6] = addiu(V0, A1, 1)
    # prototype: the destructor sits far away and nobody calls it by jal;
    # release: a look-alike called by paired callers whose partners do not call it
    proto = [body(1), call_builder(5, seed=9), body(2), body(3), body(4), body(80, 14), body(81), body(82), dtor]
    release = [body(1), call_builder(2, seed=9), look_alike, body(2), body(3), body(4), body(80, 14), body(81), body(82)]
    m, ps, rs = match(proto, release)
    assert ps[8] not in m.pairs
    assert rs[2] not in m.r_paired


def test_moved_template_instance_takes_its_release_neighbours_owner():
    # prototype: a.cpp defines f0 and emits the template t; b.cpp defines b1..b3.
    # release: t is emitted between b1 and b2, so b.cpp emits it now.
    proto = [body(1), body(50, 16), body(2), body(3), body(4)]
    release = [body(1), body(2), body(50, 16), body(3), body(4)]
    m, ps, rs = match(proto, release)
    owners = ["src/a.cpp", "src/a.cpp", "src/b.cpp", "src/b.cpp", "src/b.cpp"]
    facts = {}
    for k, address in enumerate(ps):
        facts[address] = protofacts.ProtoFunction(address, m.p_by[address].size, ["f%d" % k])
        facts[address].owner = owners[k]
        facts[address].owner_kind = "emits" if k == 1 else "defines"
    rows = {r["release_address"]: r for r in report.build_rows(m, facts, {}) if r["release_address"]}
    moved = rows[rs[2]]
    assert moved["prototype_address"] == ps[1]
    assert moved["owner_file"] == "src/b.cpp" and "owner-moved" in moved["flags"]
    assert moved["prototype_owner"] == "src/a.cpp"
    assert "owner-moved" not in rows[rs[1]]["flags"]


def test_settled_pairs_are_applied_first_and_checked(tmp_path):
    proto = [body(1), body(2, 14), body(3)]
    release = [body(1), body(9, 14), body(3), body(8)]
    m, ps, rs = match(proto, release)
    assert ps[1] in m.pairs  # positional pair without the file
    from test_pairing import build
    P, _ = build("p", proto)
    R, _ = build("r", release)
    settled = pairing.Matcher(P, R, ps[0], rs[0])
    settled.run([(rs[1], None), (None, ps[1]), (rs[3], ps[2])])
    assert ps[1] not in settled.pairs and rs[1] not in settled.r_paired
    assert settled.pairs[ps[2]].r.address == rs[3] and "settled" in settled.pairs[ps[2]].evidence
    assert settled.pairs[ps[2]].cls == "deviating"
    with pytest.raises(pairing.SettledError):
        pairing.Matcher(P, R, ps[0], rs[0]).run([(rs[1] + 4, ps[1])])
    path = tmp_path / "settled.tsv"
    path.write_text("release\tprototype\tbasis\tchecker\tdate\n0x%x\tnew\tcallers\tchecker-x\t2026-11-25\n"
                    "removed\t0x%x\tinlined\tchecker-x\t2026-11-25\n" % (rs[1], ps[1]), encoding="utf-8")
    rows = compare.read_settled(path)
    assert rows[0]["release"] == rs[1] and rows[0]["prototype"] is None
    assert rows[1]["release"] is None and rows[1]["prototype"] == ps[1]
    path.write_text("release\tprototype\tbasis\tchecker\tdate\nremoved\tnew\tx\ty\tz\n", encoding="utf-8")
    with pytest.raises(pairing.SettledError):
        compare.read_settled(path)
    assert compare.read_settled(tmp_path / "absent.tsv") == []


def test_template_family_and_sheet():
    assert sheets.family("__ct__Q23std42__list_deleter<PCv,Q23std14allocator<PCv>>FRCQ23std14allocator<PCv>") \
        == "__list_deleter"
    assert sheets.family("NewKey__Q23zar4CZARFPCc") == ""
    assert sheets.family("__dt__10CCheatListFv") == ""
    proto = [call_builder(1, seed=1), body(4, 12), body(6)]
    changed = [w if (w >> 26) != 9 or ((w >> 21) & 31) != A1 else (w & 0xFFFF0000) | ((w + 0x10) & 0xFFFF)
               for w in body(4, 12)]
    release = [call_builder(1, seed=1), changed, body(6)]
    m, ps, rs = match(proto, release)
    deltas = sheets.immediate_deltas(m.p_by[ps[1]], m.r_by[rs[1]])
    assert deltas == ["a1: +0x10 x7"]
    facts = {a: protofacts.ProtoFunction(a, m.p_by[a].size, ["f%x" % a]) for a in ps}
    for f in facts.values():
        f.owner, f.owner_kind = "src/gamez/zTest/t.cpp", "defines"
    rows = report.build_rows(m, facts, {})
    text = sheets.module_sheet("gamez/zTest", m, rows, facts)
    assert "# Check sheet: gamez/zTest" in text and "immediate deltas: a1: +0x10 x7" in text
    assert sheets.disassemble(addiu(V0, A0, -4), 0) == "addiu v0, a0, -4"
    assert sheets.disassemble(jal(0x100100), 0x100000, lambda t: "callee") == "jal callee"
