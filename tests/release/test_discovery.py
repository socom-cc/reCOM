from __future__ import annotations

import discover
import elfimage
from asm import A0, AT, JR_RA, NOP, RA, SP, V0, addiu, addu, beq, frame, jal, jr, lui, lw, pad, sll, sltiu, sw, unframe

BASE = 0x100000


def layout(*functions):
    """Concatenate functions, each padded to 16 bytes; returns words and start addresses."""

    words: list[int] = []
    starts = []
    for body in functions:
        starts.append(BASE + 4 * len(words))
        words.extend(body)
        pad(words)
    return words, starts


def test_entry_calls_gap_sweep_and_noreturn_split():
    # f0 (entry) calls f1; f2 is never called (found by the sweep after f1's padding);
    # f3 ends with a call that never returns and f4 starts with a frame right after it.
    f0 = [frame(), sw(RA, 0, SP), jal(0), NOP, lw(RA, 0, SP), JR_RA, unframe()]
    f1 = [addiu(V0, 0, 1), JR_RA, NOP]
    f2 = [addiu(V0, 0, 2), JR_RA, NOP]
    f3 = [frame(), jal(BASE), NOP]
    f4 = [frame(), addiu(V0, 0, 4), JR_RA, unframe()]
    words, starts = layout(f0, f1, f2, f3, f4)
    words[2] = jal(starts[1])
    image = elfimage.synthetic(words, BASE, entry=starts[0])
    found = discover.Discovery(image).run()
    extents = [(f.start, f.size) for f in found]
    assert extents == [(starts[0], 28), (starts[1], 12), (starts[2], 12), (starts[3], 12), (starts[4], 16)]
    evidence = {f.start: f.evidence for f in found}
    assert "call" in evidence[starts[1]] and "sweep" in evidence[starts[2]]


def test_forward_branch_keeps_the_function_open_past_an_early_return():
    body = [beq(A0, 0, 3), NOP, JR_RA, NOP, addiu(V0, 0, 7), JR_RA, NOP]
    words, starts = layout(body)
    image = elfimage.synthetic(words, BASE, entry=starts[0])
    found = discover.Discovery(image).run()
    assert [(f.start, f.size) for f in found] == [(starts[0], 28)]


def test_jump_table_targets_extend_the_function():
    table = 0x100400
    body = [
        sltiu(AT, A0, 2),          # 0
        beq(AT, 0, 9),             # 1 -> 11 (default)
        sll(V0, A0, 2),            # 2
        lui(AT, table >> 16),      # 3
        addu(AT, AT, V0),          # 4
        lw(V0, table & 0xFFFF, AT),  # 5
        jr(V0),                    # 6
        NOP,                       # 7
        addiu(V0, 0, 1),           # 8 case 0
        JR_RA, NOP,                # 9, 10
        addiu(V0, 0, 2),           # 11 case 1 and default
        JR_RA, NOP,                # 12, 13
    ]
    words = list(body)
    pad(words)
    while BASE + 4 * len(words) < table:
        words.append(0)
    words += [BASE + 32, BASE + 44]
    image = elfimage.synthetic(words, BASE, entry=BASE)
    found = discover.Discovery(image).run()
    assert (found[0].start, found[0].size) == (BASE, 56)
    assert found[0].tables == [(table, 2)]


def test_trailing_padding_after_a_noreturn_call_is_not_part_of_the_function():
    f0 = [frame(), jal(BASE + 64), NOP, NOP]  # last nop: padding before an aligned frame
    words = list(f0)
    words += [frame(), addiu(V0, 0, 1), JR_RA, unframe()]
    pad(words)
    while len(words) < 16:
        words.append(0)
    words += [addiu(V0, 0, 0), JR_RA, NOP]
    image = elfimage.synthetic(words, BASE, entry=BASE)
    found = {f.start: f.size for f in discover.Discovery(image).run()}
    assert found[BASE] == 12
    assert found[BASE + 16] == 16


def test_data_after_code_is_not_swept_into_functions():
    words, starts = layout([addiu(V0, 0, 1), JR_RA, NOP])
    words += [0x4C4C4C4C] * 8  # text that decodes as an invalid opcode (COP3)
    image = elfimage.synthetic(words, BASE, entry=starts[0])
    found = discover.Discovery(image).run()
    assert len(found) == 1
    coverage = discover.coverage(image, found)
    assert coverage["clusters"][0]["covered"] == 12


def test_static_initialiser_table_far_from_text():
    # text: entry + helper; far away (beyond NEAR_GAP) a table of two initialisers that call the helper
    words, starts = layout([addiu(V0, 0, 1), JR_RA, NOP], [addiu(V0, 0, 2), JR_RA, NOP])
    while len(words) * 4 < discover.NEAR_GAP + 0x100:
        words.append(0x4C4C4C4C)
    pad(words)  # zero padding before the initialiser block
    words += [0, 0, 0, 0]
    init_start = BASE + 4 * len(words)
    init = [frame(), sw(RA, 0, SP), jal(starts[1]), NOP, lw(RA, 0, SP), JR_RA, unframe(), NOP]
    words += init + init
    table = BASE + 4 * len(words)
    words += [init_start, init_start + 32, 0x4C4C4C4C]
    image = elfimage.synthetic(words, BASE, entry=starts[0])
    found = {f.start: f for f in discover.Discovery(image).run()}
    assert init_start in found and init_start + 32 in found
    assert "pointer-table" in found[init_start].evidence
    assert table not in found
