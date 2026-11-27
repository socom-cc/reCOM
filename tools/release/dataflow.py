"""Data addresses a function's instructions compute, with the instructions that build each one.

A must-analysis over the function's own control flow (``mips._successors``: branches,
delay slots, likely branches) tracks, per general register, a constant address:

* ``hi``: ``lui r, H`` with ``H`` in ``mips.ADDRESS_HI`` (the high half of an address),
  optionally plus an unknown index (``addu`` of an unknown register);
* ``addr``: a high half plus its low half (``addiu``/``ori``), or ``$gp`` plus an offset:
  the address of an object, optionally moved by a later ``addiu`` (``off``) or by an
  unknown index (``off`` None).

A value survives a merge only when every path brings the same one (unreached blocks,
such as jump-table targets, start empty); a call clobbers the caller-saved registers
after its delay slot. Every use is a :class:`Ref`:

* ``addr``: the address taken (``addiu``/``ori`` on a high half, ``addiu r, $gp, n``);
* ``load``/``store``: a memory access through a high half (``lw t, lo(at)``: the low
  half is the instruction's own offset), through ``$gp``, or through an ``addr``
  register (``off`` is then the field offset added to it).

``address`` is the address the linker resolved (high plus low half, or ``$gp`` plus
offset; it includes a field offset the compiler folded into the relocation); ``off``
is what a register adds after it. ``defs`` are the instruction indices that built
``address`` (the ``lui``, the low half, pointer arithmetic), so an aligned pair of
functions can check that every instruction behind a use aligns, not only the use.
"""
from __future__ import annotations

from dataclasses import dataclass

import mips

WIDTH = {0x20: 1, 0x21: 2, 0x22: 4, 0x23: 4, 0x24: 1, 0x25: 2, 0x26: 4, 0x27: 4,
         0x28: 1, 0x29: 2, 0x2A: 4, 0x2B: 4, 0x2C: 8, 0x2D: 8, 0x2E: 4,
         0x31: 4, 0x36: 16, 0x37: 8, 0x39: 4, 0x3E: 16, 0x3F: 8,
         0x1A: 8, 0x1B: 8, 0x1E: 16, 0x1F: 16}
STORES = frozenset({0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x39, 0x3E, 0x3F, 0x1F})
CALLER_SAVED = tuple(r for r in range(32) if (mips.CALLER_SAVED >> r) & 1)


@dataclass(frozen=True)
class Ref:
    index: int  # word index of the use inside the function
    kind: str  # addr | load | store
    address: int  # the address the linker resolved (a folded field offset included)
    off: int | None  # offset a register adds after it; None: an unknown index
    width: int  # bytes accessed (0 for addr)
    defs: tuple  # word indices that built ``address`` (lui, low half, pointer arithmetic)
    gp: bool = False


def is_call(word: int) -> bool:
    return (word >> 26) == 3 or ((word >> 26) == 0 and (word & 0x3F) == 9) or (
        (word >> 26) == 1 and ((word >> 16) & 0x1F) in (0x10, 0x11, 0x12, 0x13))


def _step(word: int, local: int, state: dict, gp: int | None) -> dict:
    """The register state after one instruction (the call clobber is applied by the caller)."""

    op = word >> 26
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    if op == 0x0F:
        out = dict(state)
        out.pop(rt, None)
        if rt and (word & 0xFFFF) in mips.ADDRESS_HI:
            out[rt] = ("hi", (word & 0xFFFF) << 16, (local,), 0)
        return out
    if op in (0x09, 0x0D):
        src = state.get(rs)
        out = dict(state)
        out.pop(rt, None)
        if not rt:
            return out
        imm = mips.simm(word) if op == 0x09 else word & 0xFFFF
        if rs == mips.GP and gp is not None and op == 0x09:
            out[rt] = ("addr", gp + imm, (local,), 0)
        elif src is not None and src[0] == "hi" and src[3] == 0:
            out[rt] = ("addr", src[1] + imm, src[2] + (local,), 0)
        elif src is not None and src[0] == "addr" and op == 0x09:
            out[rt] = ("addr", src[1], src[2] + (local,), None if src[3] is None else src[3] + imm)
        return out
    if op == 0:
        funct = word & 0x3F
        rd = (word >> 11) & 0x1F
        if funct in (0x21, 0x2D, 0x25):
            a, b = state.get(rs), state.get(rt)
            out = dict(state)
            out.pop(rd, None)
            if not rd or (funct == 0x25 and rs and rt):
                return out
            if rt == 0 and a is not None:
                out[rd] = a  # a move
            elif rs == 0 and b is not None:
                out[rd] = b
            elif funct != 0x25 and (a is None) != (b is None):
                known = a if a is not None else b
                out[rd] = (known[0], known[1], known[2] + (local,), None)  # plus an unknown index
            return out
    written = mips.written_registers(word)
    if not any(r in state for r in written):
        return state
    out = dict(state)
    for register in written:
        out.pop(register, None)
    return out


def _flow(words, start: int, count: int, base: int, gp: int | None) -> list:
    succ = mips._successors(words, start, count, base)
    state_in: list = [None] * count
    pending: list[int] = []
    root = 0
    while True:
        while root < count and state_in[root] is not None:
            root += 1
        if root >= count:
            return state_in
        state_in[root] = {}
        pending.append(root)
        while pending:
            local = pending.pop()
            out = _step(words[start + local], local, state_in[local], gp)
            if local and is_call(words[start + local - 1]) and out:
                out = {r: v for r, v in out.items() if not (mips.CALLER_SAVED >> r) & 1}
            for nxt in succ[local]:
                old = state_in[nxt]
                if old is None:
                    state_in[nxt] = out
                    pending.append(nxt)
                elif old:
                    merged = {r: v for r, v in old.items() if out.get(r) == v}
                    if len(merged) != len(old):
                        state_in[nxt] = merged
                        pending.append(nxt)


def references(words, start: int, count: int, base: int, gp: int | None) -> list[Ref]:
    """Every data-address use of the ``count`` words from index ``start`` (image base ``base``)."""

    state_in = _flow(words, start, count, base, gp)
    out = []
    for local in range(count):
        word = words[start + local]
        state = state_in[local]
        op = word >> 26
        rs = (word >> 21) & 0x1F
        if op in (0x09, 0x0D):
            if not (word >> 16) & 0x1F:
                continue
            src = state.get(rs)
            imm = mips.simm(word) if op == 0x09 else word & 0xFFFF
            if rs == mips.GP and gp is not None and op == 0x09:
                out.append(Ref(local, "addr", gp + imm, 0, 0, (), True))
            elif src is not None and src[0] == "hi" and src[3] == 0:
                out.append(Ref(local, "addr", src[1] + imm, 0, 0, src[2]))
        elif op in WIDTH:
            kind = "store" if op in STORES else "load"
            imm = mips.simm(word)
            src = state.get(rs)
            if rs == mips.GP and gp is not None:
                out.append(Ref(local, kind, gp + imm, 0, WIDTH[op], (), True))
            elif src is not None and src[0] == "hi":
                out.append(Ref(local, kind, src[1] + imm, src[3], WIDTH[op], src[2]))
            elif src is not None and src[0] == "addr":
                out.append(Ref(local, kind, src[1], None if src[3] is None else src[3] + imm, WIDTH[op], src[2]))
    return out
