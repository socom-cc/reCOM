from __future__ import annotations

from tools._socom.dwarf1 import Attribute, Die
from tools._socom.elf import Symbol
from tools._socom.type_identity import (
    _trace_receiver_calls,
    ghidra_path,
    indirection,
    member_offset,
    parse_subscr,
    template_arguments,
)

A0, S0, SP = 4, 16, 29


def _addiu(rt: int, rs: int, imm: int) -> int:
    return (0x09 << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def _daddu(rd: int, rs: int, rt: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | 0x2D


def _lw(rt: int, offset: int, base: int) -> int:
    return (0x23 << 26) | (base << 21) | (rt << 16) | (offset & 0xFFFF)


def _jal(target: int) -> int:
    return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)


def _beq(rs: int, rt: int, words: int) -> int:
    return (0x04 << 26) | (rs << 21) | (rt << 16) | (words & 0xFFFF)


def _bnel(rs: int, rt: int, words: int) -> int:
    return (0x15 << 26) | (rs << 21) | (rt << 16) | (words & 0xFFFF)


def _mult(rd: int, rs: int, rt: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | 0x18


def _j(target: int) -> int:
    return (0x02 << 26) | ((target >> 2) & 0x03FFFFFF)


def _symbol(name: str, value: int) -> Symbol:
    return Symbol(
        index=0, name_offset=0, name=name, value=value, size=4, info=0x12, other=0, section_index=4
    )


def test_subscript_data_keeps_bounds_and_element_type_without_offsets() -> None:
    # float m_matrix[4][4] as emitted for CMatrix: FT_C_C dimensions and an
    # element user_def_type reference whose offset is compile-unit local.
    data = bytes.fromhex("000a00000000000300000008720" "0c1d10000")
    dims, element = parse_subscr(data)
    assert dims == [("fund", 0x000A, 0, 3)]
    assert element == (b"", 0xD1C1, None)
    assert parse_subscr(b"\xff") == ([("raw", "ff")], None)


def test_member_offsets_and_indirection() -> None:
    member = Die(
        offset=0x10,
        length=0,
        tag=0x000D,
        tag_name="member",
        attributes=(
            Attribute(0x0023, 0x0020, "location", 0x3, "block2", bytes.fromhex("041400000007")),
        ),
    )
    assert member_offset(member) == 0x14
    assert indirection(bytes([0x03, 0x01])) == (1,)
    assert indirection(bytes([0x02])) == (2,)


def test_receiver_tracking_follows_saved_this_offsets_and_pointer_loads() -> None:
    start, callee_address = 0x1000, 0x2000
    callee = _symbol("__dt__Q23std46vector<8AnimType,Q23std20allocator<8AnimType>>Fv", callee_address)
    words = [
        _addiu(SP, SP, -32),
        _daddu(S0, A0, 0),          # s0 = this
        _jal(callee_address),
        _addiu(A0, S0, 0x14),       # delay slot: a0 = this + 0x14
        _beq(0, 0, 1),              # branch to the next-but-one instruction
        0,
        _lw(A0, 8, S0),             # branch target: a0 = *(this + 8)
        _jal(callee_address),
        0,
        _jal(callee_address),       # a0 was clobbered by the previous call
        0,
    ]
    calls = _trace_receiver_calls(words, start, {callee_address: callee})
    assert [path for path, _ in calls] == [(0x14,), (8, 0)]
    assert all(symbol is callee for _, symbol in calls)


def test_ghidra_paths_split_only_top_level_qualifiers() -> None:
    assert ghidra_path("zdb::CCamera") == "/project/zdb/CCamera"
    assert ghidra_path("std::vector<zdb::CTexHandle*, std::allocator<zdb::CTexHandle*>>") == (
        "/project/std/vector<zdb::CTexHandle*, std::allocator<zdb::CTexHandle*>>"
    )


def test_three_operand_mult_and_branch_likely_delay_slots() -> None:
    start, callee_address = 0x1000, 0x2000
    callee = _symbol("Tick__3FooFv", callee_address)
    words = [
        _daddu(S0, A0, 0),          # s0 = this (stable)
        _addiu(A0, S0, 0x10),       # a0 = this + 0x10
        _mult(A0, 9, 10),           # R5900 mult writes rd: a0 is no longer known
        _jal(callee_address),
        0,
        _addiu(A0, S0, 0x20),       # a0 = this + 0x20
        _bnel(9, 0, 4),             # branch-likely: delay slot annulled on fall-through
        _addiu(A0, S0, 0x30),
        _jal(callee_address),       # fall-through: a0 is still this + 0x20
        0,
    ]
    calls = _trace_receiver_calls(words, start, {callee_address: callee})
    assert [path for path, _ in calls] == [(0x20,)]


def test_unconditional_branches_end_blocks_and_jump_targets_merge() -> None:
    start, callee_address = 0x1000, 0x2000
    callee = _symbol("Tick__3FooFv", callee_address)
    words = [
        _daddu(S0, A0, 0),          # s0 = this (stable)
        _addiu(A0, S0, 0x10),
        _beq(0, 0, 3),              # b: does not fall through
        0,
        _jal(callee_address),       # unreachable by fall-through: a0 unknown
        0,
        _addiu(A0, S0, 0x40),       # b target
        _j(start + 4 * 10),         # j to an intra-function target
        0,
        _addiu(A0, S0, 0x50),       # unreachable by fall-through
        _jal(callee_address),       # j target: only stable registers survive
        0,
    ]
    calls = _trace_receiver_calls(words, start, {callee_address: callee})
    assert calls == []


def test_template_arguments_respect_nested_brackets_and_parentheses() -> None:
    assert template_arguments(
        "std::queue<void (CCnfStateMachine::*)(void const*, void*), "
        "std::deque<int, std::allocator<int>>>"
    ) == [
        "void (CCnfStateMachine::*)(void const*, void*)",
        "std::deque<int, std::allocator<int>>",
    ]
    assert template_arguments("zdb::CNode") == []
