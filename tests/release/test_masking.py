from __future__ import annotations

from array import array

import mips
from asm import A0, A1, AT, GP, JR_RA, NOP, S0, V0, addiu, addu, b, beq, jal, lui, lw, sll, sw

BASE = 0x100000


def mask(words):
    data = array("I", words)
    return mips.mask_function(data, 0, len(words), BASE)


def test_call_target_and_address_lui_are_masked_constants_are_not():
    words = [jal(0x140000), NOP, lui(V0, 0x0043), lui(A0, 0x3F80), JR_RA, NOP]
    masked, kinds = mask(words)
    assert masked[0] == 0x0C000000 and kinds[0] == mips.M_CALL
    assert masked[2] == lui(V0, 0) and kinds[2] == mips.M_HI
    assert masked[3] == words[3] and kinds[3] is None  # 0x3f80 is a float constant, kept


def test_low_half_paired_with_address_lui_is_masked():
    words = [lui(A0, 0x0045), addiu(A0, A0, 0x1234), lw(V0, 8, A1), JR_RA, NOP]
    masked, kinds = mask(words)
    assert kinds[1] == mips.M_LO and masked[1] == addiu(A0, A0, 0)
    assert kinds[2] is None and masked[2] == words[2]  # a struct offset stays


def test_gp_relative_offset_is_masked():
    masked, kinds = mask([lw(V0, -0x7FF0, GP), JR_RA, NOP])
    assert kinds[0] == mips.M_GP and masked[0] == lw(V0, 0, GP)


def test_overwritten_register_is_no_longer_a_high_half():
    words = [lui(A0, 0x0045), addiu(A0, 0, 5), lw(V0, 4, A0), JR_RA, NOP]
    _, kinds = mask(words)
    assert kinds[2] is None


def test_high_half_reaches_its_use_through_a_branch():
    # lui before a branch; the delay slot clobbers v0 on the fall-through path only
    words = [
        lui(AT, 0x0044),       # 0
        beq(A0, 0, 2),         # 1 -> 4
        NOP,                   # 2 delay slot
        addiu(AT, 0, 1),       # 3 fall-through clobbers at
        lw(V0, 0x10, AT),      # 4 branch target: at may still hold the high half
        JR_RA, NOP,
    ]
    _, kinds = mask(words)
    assert kinds[4] == mips.M_LO


def test_high_half_survives_a_table_index_and_a_move():
    words = [sll(V0, A0, 2), lui(AT, 0x0044), addu(AT, AT, V0), lw(V0, 0x100, AT),
             lui(S0, 0x0045), addu(A1, S0, 0), sw(0, 0x20, A1), JR_RA, NOP]
    _, kinds = mask(words)
    assert kinds[3] == mips.M_LO
    assert kinds[6] == mips.M_LO


def test_call_clobbers_caller_saved_registers_after_its_delay_slot():
    words = [lui(A0, 0x0044), jal(0x150000), addiu(A0, A0, 0x10),  # delay slot uses the high half
             lw(V0, 0, A0), lui(S0, 0x0044), jal(0x150000), NOP, lw(V0, 4, S0), JR_RA, NOP]
    _, kinds = mask(words)
    assert kinds[2] == mips.M_LO
    assert kinds[3] is None  # a0 after the call is not the high half any more
    assert kinds[7] == mips.M_LO  # s0 is callee-saved


def test_mask_ignores_what_precedes_the_function():
    prefix = [lui(A0, 0x0044), NOP]
    body = [lw(V0, 4, A0), JR_RA, NOP]
    data = array("I", prefix + body)
    masked, kinds = mips.mask_function(data, 2, 3, BASE)
    assert kinds[0] is None and masked == [*body]


def test_unconditional_branch_has_no_fall_through():
    words = [lui(A0, 0x0044), b(2), NOP, lw(V0, 0, A0), JR_RA, NOP]
    # index 3 is unreachable straight-line from 0 (b skips it): analysed from an empty state
    _, kinds = mask(words)
    assert kinds[3] is None
