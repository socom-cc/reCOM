"""R5900 instruction helpers: decoding, the address-operand masking rule, shapes.

The masking rule decides which instruction fields are *address operands* (values
that change when the linker places code or data differently) so two builds can
be compared without them:

* ``j``/``jal``: the 26-bit target;
* ``lui``: the 16-bit immediate, but only when it can be the high half of an
  address inside the images (``ADDRESS_HI``); other ``lui`` values are constants
  (float bit patterns, masks) and are kept;
* ``$gp``-relative ``addiu``/loads/stores: the 16-bit offset;
* the low half paired with an address ``lui``: ``addiu``/``ori``/loads/stores
  whose base register may hold that ``lui`` value on some path through the
  function's own control flow (branches and delay slots followed; ``move`` and
  ``addu`` of a table index carry it; a call clobbers the caller-saved registers
  after its delay slot; tracking starts empty at the function start).

Against the prototype's relocations this rule masks every relocated field and
adds about 140 masks of integer constants that fall in the address range.

Branch offsets are PC-relative inside a function and stay unmasked, so equal
masked bytes also mean equal layout.
"""
from __future__ import annotations

import struct
import sys
from array import array

RA = 31
GP = 28
SP = 29

LOADSTORE = frozenset(range(0x20, 0x30)) | {0x31, 0x36, 0x37, 0x39, 0x3E, 0x3F, 0x1A, 0x1B, 0x1E, 0x1F}
LOADS = frozenset({0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x37, 0x1A, 0x1B, 0x1E})
# Primary opcodes the R5900 does not implement (COP3, JALX, LL/SC, LWC2/SWC2, LDC1/SDC1, ...).
INVALID_PRIMARY = frozenset({0x13, 0x1D, 0x30, 0x32, 0x34, 0x35, 0x38, 0x3A, 0x3B, 0x3C, 0x3D})
# SPECIAL function codes that are reserved on the R5900.
INVALID_SPECIAL = frozenset({0x01, 0x05, 0x0E, 0x15, 0x1C, 0x1D, 0x1E, 0x1F, 0x35, 0x37, 0x39, 0x3D})

# lui immediates treated as address highs (0x00100000 .. 0x00610000 covers both
# images' segments, heap and bss; the +1 allows a negative low half).
ADDRESS_HI = range(0x0010, 0x0062)

JR_RA = 0x03E00008


def words_of(data: bytes) -> array:
    count = len(data) // 4
    out = array("I")
    out.frombytes(data[:count * 4])
    if sys.byteorder != "little":
        out.byteswap()
    return out


def simm(word: int) -> int:
    value = word & 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def is_invalid(word: int) -> bool:
    op = word >> 26
    if op in INVALID_PRIMARY:
        return True
    if op == 0:
        return (word & 0x3F) in INVALID_SPECIAL
    return False


def branch_target(word: int, pc: int) -> int | None:
    """Target of a PC-relative conditional or unconditional branch, else None."""

    op = word >> 26
    if op in (4, 5, 6, 7, 0x14, 0x15, 0x16, 0x17):
        return pc + 4 + (simm(word) << 2)
    if op == 1 and ((word >> 16) & 0x1F) in (0, 1, 2, 3, 0x10, 0x11, 0x12, 0x13):
        return pc + 4 + (simm(word) << 2)
    if op in (0x10, 0x11, 0x12) and ((word >> 21) & 0x1F) == 8:
        return pc + 4 + (simm(word) << 2)
    return None


def is_unconditional_branch(word: int) -> bool:
    # beq $0,$0 (b) and bgez $0 (also b); bgezal $0 is bal, a call, not an exit.
    return (word >> 16) == 0x1000 or (word >> 16) == 0x0401


def jump_target(word: int, pc: int) -> int:
    return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)


def is_jal(word: int) -> bool:
    return (word >> 26) == 3


def is_j(word: int) -> bool:
    return (word >> 26) == 2


def is_jr(word: int) -> bool:
    return (word >> 26) == 0 and (word & 0x3F) == 8


def written_registers(word: int) -> tuple[int, ...]:
    """General registers an instruction writes (approximation sufficient for lui tracking)."""

    op = word >> 26
    rt = (word >> 16) & 0x1F
    rd = (word >> 11) & 0x1F
    if op == 0:
        funct = word & 0x3F
        if funct in (8, 0x0C, 0x0D, 0x18, 0x19, 0x1A, 0x1B, 0x11, 0x13):  # jr, syscall, break, mult/div, mthi/mtlo
            return (rd,) if funct in (0x18, 0x19) else ()
        return (rd,)
    if op == 3:
        return (RA,)
    if op == 1:
        return (RA,) if rt in (0x10, 0x11, 0x12, 0x13) else ()
    if op in (0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x18, 0x19) or op in LOADS:
        return (rt,)
    if op == 0x1C:  # MMI writes rd
        return (rd,)
    if op in (0x10, 0x11, 0x12) and ((word >> 21) & 0x1F) in (0, 1, 2):  # mfc/dmfc/cfc
        return (rt,)
    return ()


# Mask kinds, recorded per masked word.
M_CALL, M_JUMP, M_HI, M_LO, M_GP = "call", "jump", "hi", "lo", "gp"


CALLER_SAVED = 0
for _register in (*range(1, 16), 24, 25, RA):
    CALLER_SAVED |= 1 << _register
_ALL = (1 << 32) - 1


def is_likely_branch(word: int) -> bool:
    op = word >> 26
    if op in (0x14, 0x15, 0x16, 0x17):
        return True
    if op == 1 and ((word >> 16) & 0x1F) in (2, 3, 0x12, 0x13):
        return True
    return op in (0x10, 0x11, 0x12) and ((word >> 21) & 0x1F) == 8 and ((word >> 17) & 1) == 1


def _successors(words, start: int, count: int, base: int) -> list[tuple[int, ...]]:
    """Control-flow successors (local indices) of every instruction of one function."""

    first = base + start * 4

    def local_of(address: int) -> int:
        offset = address - first
        return offset // 4 if offset >= 0 and offset % 4 == 0 else -1

    succ: list[tuple[int, ...]] = []
    for local in range(count):
        word = words[start + local]
        nxt = local + 1
        out: list[int] = []
        if branch_target(word, 0) is not None:
            out.append(nxt)  # the delay slot runs first
            if is_likely_branch(word):
                out.append(local + 2)  # not taken: a likely branch skips its delay slot
        elif is_jr(word) or is_j(word):
            out.append(nxt)
        elif local:
            prev = words[start + local - 1]
            prev_pc = first + (local - 1) * 4
            prev_target = branch_target(prev, prev_pc)
            if prev_target is not None:  # this is a branch delay slot
                tloc = local_of(prev_target)
                if 0 <= tloc < count:
                    out.append(tloc)
                if not is_likely_branch(prev) and not is_unconditional_branch(prev):
                    out.append(nxt)
            elif is_j(prev):
                tloc = local_of(jump_target(prev, prev_pc))
                if 0 <= tloc < count:
                    out.append(tloc)  # an in-function j; otherwise a tail call
            elif not is_jr(prev):
                out.append(nxt)
        else:
            out.append(nxt)
        succ.append(tuple(x for x in out if x < count))
    return succ


def _transfer(word: int, state: int) -> int:
    op = word >> 26
    if op == 0x0F:
        bit = 1 << ((word >> 16) & 0x1F)
        return (state | bit) if (word & 0xFFFF) in ADDRESS_HI else (state & ~bit)
    funct = word & 0x3F
    if op == 0 and (funct in (0x21, 0x2D) or (funct == 0x25 and ((word >> 16) & 0x1F) == 0)):
        # addu/daddu (a move, or high half plus a table index) and "or rd, rs, $zero"
        # carry the high half into rd
        rd = (word >> 11) & 0x1F
        if ((state >> ((word >> 21) & 0x1F)) | (state >> ((word >> 16) & 0x1F))) & 1:
            return (state | (1 << rd)) & ~1
        return state & ~(1 << rd) & ~1
    for register in written_registers(word):
        state &= ~(1 << register)
    return state & ~1


def _is_call(word: int) -> bool:
    return (word >> 26) == 3 or ((word >> 26) == 0 and (word & 0x3F) == 9)


def mask_function(words, start: int, count: int, base: int = 0):
    """Masked words of ``count`` words from index ``start``; also the per-word mask kinds.

    ``lui`` tracking is a may-analysis over the function's own control flow and
    starts empty at ``start``, so a function's mask never depends on its
    neighbours in the image.
    """

    succ = _successors(words, start, count, base)
    # Every instruction starts at the empty state, so blocks reached only through a
    # jump table (no modelled predecessor) are still analysed straight-line.
    state_in = [0] * count
    changed = True
    while changed:
        changed = False
        for local in range(count):
            out_state = _transfer(words[start + local], state_in[local])
            if local and _is_call(words[start + local - 1]):
                out_state &= ~CALLER_SAVED  # the callee runs after the delay slot
            for nxt in succ[local]:
                merged = state_in[nxt] | out_state
                if merged != state_in[nxt]:
                    state_in[nxt] = merged
                    if nxt <= local:
                        changed = True
    out = []
    kinds = []
    for local in range(count):
        word = words[start + local]
        op = word >> 26
        masked = word
        kind = None
        if op in (2, 3):
            masked = word & 0xFC000000
            kind = M_CALL if op == 3 else M_JUMP
        elif op == 0x0F:
            if (word & 0xFFFF) in ADDRESS_HI:
                masked = word & 0xFFFF0000
                kind = M_HI
        elif op in (0x09, 0x0D) or op in LOADSTORE:
            rs = (word >> 21) & 0x1F
            if rs == GP:
                masked = word & 0xFFFF0000
                kind = M_GP
            elif (state_in[local] >> rs) & 1:
                masked = word & 0xFFFF0000
                kind = M_LO
        out.append(masked)
        kinds.append(kind)
    return out, kinds


def shape(word: int) -> int:
    """The instruction with every immediate, offset and target removed (opcode and registers kept)."""

    op = word >> 26
    if op in (2, 3):
        return word & 0xFC000000
    if op == 0 or op == 0x1C:
        return word
    if op in (0x10, 0x11, 0x12) and ((word >> 21) & 0x1F) >= 0x10:
        return word  # coprocessor operate formats carry no immediates
    if op in (0x10, 0x11, 0x12) and ((word >> 21) & 0x1F) != 8:
        return word
    return word & 0xFFFF0000


def operation(word: int) -> int:
    """The operation alone: opcode and function fields, no registers, immediates or targets."""

    op = word >> 26
    if op == 0:
        return word & 0xFC00003F
    if op == 1:
        return word & 0xFC1F0000
    if op in (0x10, 0x11, 0x12):
        fmt = (word >> 21) & 0x1F
        return word & (0xFFE0003F if fmt >= 0x10 else 0xFFE00000)
    if op == 0x1C:
        return word & 0xFC0007FF
    return word & 0xFC000000


def pack(words) -> bytes:
    return struct.pack("<%dI" % len(words), *words)
