"""A few R5900 encoders for synthetic test images."""
from __future__ import annotations

SP, RA, GP, ZERO, V0, A0, A1, AT, S0 = 29, 31, 28, 0, 2, 4, 5, 1, 16
NOP = 0
JR_RA = 0x03E00008


def i_type(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def addiu(rt: int, rs: int, imm: int) -> int:
    return i_type(0x09, rs, rt, imm)


def lui(rt: int, imm: int) -> int:
    return i_type(0x0F, 0, rt, imm)


def lw(rt: int, offset: int, base: int) -> int:
    return i_type(0x23, base, rt, offset)


def sw(rt: int, offset: int, base: int) -> int:
    return i_type(0x2B, base, rt, offset)


def sltiu(rt: int, rs: int, imm: int) -> int:
    return i_type(0x0B, rs, rt, imm)


def beq(rs: int, rt: int, offset_words: int) -> int:
    return i_type(0x04, rs, rt, offset_words)


def bne(rs: int, rt: int, offset_words: int) -> int:
    return i_type(0x05, rs, rt, offset_words)


def b(offset_words: int) -> int:
    return beq(0, 0, offset_words)


def jal(target: int) -> int:
    return (3 << 26) | ((target >> 2) & 0x03FFFFFF)


def j(target: int) -> int:
    return (2 << 26) | ((target >> 2) & 0x03FFFFFF)


def jr(rs: int) -> int:
    return (rs << 21) | 0x08


def addu(rd: int, rs: int, rt: int) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | 0x21


def sll(rd: int, rt: int, shift: int) -> int:
    return (rt << 16) | (rd << 11) | (shift << 6)


def frame(size: int = 16) -> int:
    return addiu(SP, SP, -size)


def unframe(size: int = 16) -> int:
    return addiu(SP, SP, size)


def leaf(*body: int) -> list[int]:
    """A leaf function: body, jr ra, nop."""

    return [*body, JR_RA, NOP]


def pad(words: list[int], align_words: int = 4) -> list[int]:
    while len(words) % align_words:
        words.append(0)
    return words
