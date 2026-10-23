"""Dead argument-register reads a stage 3 plan may declare on any path.

``recon facts`` lists every argument register some path reads before any
write (``argument_reads``).  Two kinds of such reads never reach a result:

* ``masked``: the read keeps part of the incoming value (a keep-half
  ``and``) and every path clears or discards those bits before anything
  observes them, as in the 64-bit word-insert idiom of libgcc's
  ``__divdi3`` and newlib's ``_ulp``;
* ``unreachable``: the read lies only on a path through one direction of a
  branch that cannot be taken that way (fdlibm's uninitialised ``k`` in
  ``__ieee754_expf``).

``masked_read_problem`` proves the first kind from the instructions alone:
it tracks which bits of the register still hold incoming data along every
path from the read, through constant masks, merges, shifts and narrow
stores, until they are gone.  ``unreachable_read_problem`` proves that
removing the declared branch edge leaves no path from the entry to the read.
Why that direction is impossible is the reviewer's to check.
``dead_read_problems`` checks a plan's ``dead_reads`` rows; the
contradiction scan drops their sites.  Everything here reads only the ELF.
"""

from __future__ import annotations

from typing import Any

from .batch_apply import _SHIFT_IMMEDIATE as _SHIFTS, _reads, _writes

M64 = (1 << 64) - 1
LOW32 = 0xFFFFFFFF
HIGH32 = M64 ^ LOW32
DEAD_READ_KINDS = ("masked", "unreachable")
GPR_NUMBERS = {"a0": 4, "a1": 5, "a2": 6, "a3": 7, "t0": 8, "t1": 9, "t2": 10, "t3": 11}
_STORE_WIDTH = {0x28: 0xFF, 0x29: 0xFFFF, 0x2B: LOW32, 0x3F: M64}  # sb, sh, sw, sd


def _sext32(value: int) -> int:
    value &= LOW32
    return value | HIGH32 if value & 0x80000000 else value


def _signed(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def _shifted(funct: int, sa: int, value: int) -> int:
    """A shift-immediate's 64-bit result for a 64-bit source ``value``."""

    if funct == 0x00:  # sll
        return _sext32(value << sa)
    if funct == 0x02:  # srl
        return _sext32((value & LOW32) >> sa)
    if funct == 0x03:  # sra
        return _sext32(_signed(value, 32) >> sa)
    amount = sa + (32 if funct in (0x3C, 0x3E, 0x3F) else 0)
    if funct in (0x38, 0x3C):  # dsll, dsll32
        return (value << amount) & M64
    if funct in (0x3A, 0x3E):  # dsrl, dsrl32
        return (value & M64) >> amount
    return (_signed(value, 64) >> amount) & M64  # dsra, dsra32


def _stale_after_shift(funct: int, sa: int, stale: int) -> int:
    """Bits of a shift's result that come from the source's ``stale`` bits."""

    if funct == 0x00:
        moved = (stale & ((1 << (32 - sa)) - 1)) << sa
        return moved | HIGH32 if moved & 0x80000000 else moved
    if funct in (0x02, 0x03):
        moved = (stale & LOW32) >> sa
        if funct == 0x03 and stale & 0x80000000:
            moved |= M64 ^ ((1 << (32 - sa)) - 1)
        elif funct == 0x02 and sa == 0 and moved & 0x80000000:
            moved |= HIGH32
        return moved
    amount = sa + (32 if funct in (0x3C, 0x3E, 0x3F) else 0)
    if funct in (0x38, 0x3C):
        return (stale << amount) & M64
    moved = stale >> amount
    if funct in (0x3B, 0x3F) and stale >> 63:
        moved |= M64 ^ ((1 << (64 - amount)) - 1)
    return moved


class _Constants:
    """64-bit constant values of registers, from reaching definitions."""

    def __init__(self, ctx: Any, flow: Any) -> None:
        self.ctx, self.flow = ctx, flow
        self.memo: dict[tuple[int, int], int | None] = {}

    def before(self, site: int, register: int, depth: int = 12) -> int | None:
        """The register's value before ``site`` runs, when every definition agrees."""

        if register == 0:
            return 0
        if depth <= 0:
            return None
        defs = self.flow.defs(site, register)
        if not defs or "entry" in defs:
            return None
        values = {self.written(pc, register, depth - 1) for pc in defs}
        return values.pop() if len(values) == 1 and None not in values else None

    def written(self, pc: int, register: int, depth: int) -> int | None:
        key = (pc, register)
        if key not in self.memo:
            self.memo[key] = None  # a cycle through this definition is not constant
            self.memo[key] = self._evaluate(pc, register, depth)
        return self.memo[key]

    def _evaluate(self, pc: int, register: int, depth: int) -> int | None:
        insn = self.ctx.code.word(pc)
        decoded = self.flow.fn.decoded
        if register not in _writes(insn)[0] or decoded[pc]["kind"] != "plain":
            return None
        if decoded.get(pc - 4, {}).get("kind") in ("call", "call-branch"):
            return None  # the call after this delay slot clobbers it
        op, rs, rt = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31
        imm = insn & 0xFFFF
        if op == 0x0F:  # lui
            return _sext32(imm << 16)
        if op in (0x09, 0x19, 0x0C, 0x0D, 0x0E):
            source = self.before(pc, rs, depth)
            if source is None:
                return None
            if op == 0x09:  # addiu
                return _sext32(source + _signed(imm, 16))
            if op == 0x19:  # daddiu
                return (source + _signed(imm, 16)) & M64
            return {0x0C: source & imm, 0x0D: source | imm, 0x0E: source ^ imm}[op]
        if op != 0x00:
            return None
        funct, sa = insn & 0x3F, (insn >> 6) & 31
        if funct in _SHIFTS:
            source = self.before(pc, rt, depth)
            return None if source is None else _shifted(funct, sa, source)
        if funct not in (0x21, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2D, 0x2F):
            return None
        left, right = self.before(pc, rs, depth), self.before(pc, rt, depth)
        if left is None or right is None:
            return None
        return {
            0x21: lambda: _sext32(left + right),  # addu
            0x23: lambda: _sext32(left - right),  # subu
            0x24: lambda: left & right,  # and
            0x25: lambda: left | right,  # or
            0x26: lambda: left ^ right,  # xor
            0x27: lambda: ~(left | right) & M64,  # nor
            0x2D: lambda: (left + right) & M64,  # daddu
            0x2F: lambda: (left - right) & M64,  # dsubu
        }[funct]()


def _extra_reads(insn: int) -> set[int]:
    """Reads ``_reads`` leaves out, as recon facts counts them."""

    op = insn >> 26
    if op == 0x00 and insn & 0x3F in (0x0A, 0x0B):  # movz/movn keep rd
        return {(insn >> 11) & 31} - {0}
    if op == 0x10 and (insn >> 21) & 31 == 0x04:  # mtc0 reads rt
        return {(insn >> 16) & 31} - {0}
    if op == 0x2F:  # cache reads its base
        return {(insn >> 21) & 31} - {0}
    return set()


def _step(constants: _Constants, pc: int, insn: int, register: int, stale: int) -> tuple[int | None, str]:
    """The register's stale bits after ``insn``, or None (with why) when it observes them."""

    reads = set(_reads(insn)[0]) | _extra_reads(insn)
    if register not in reads:
        return (0 if register in _writes(insn)[0] else stale), ""
    op, rs, rt, rd = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, (insn >> 11) & 31
    imm, funct, sa = insn & 0xFFFF, insn & 0x3F, (insn >> 6) & 31
    if op == 0x00 and funct == 0x24:  # and
        other = rt if rs == register else rs
        mask = stale if other == register else constants.before(pc, other)
        if mask is None:
            return None, "an and whose other operand is not a constant"
        return _narrowed(rd, register, stale, stale & mask)
    if op == 0x0C and rs == register:  # andi
        return _narrowed(rt, register, stale, stale & imm)
    if op == 0x00 and funct in (0x25, 0x26) and rd == register:  # or / xor into itself
        other = rt if rs == register else rs
        mask = constants.before(pc, other) if funct == 0x25 and other != register else None
        return (stale & ~mask & M64 if mask is not None else stale), ""
    if op in (0x0D, 0x0E) and rs == register and rt == register:  # ori / xori into itself
        return (stale & ~imm & M64 if op == 0x0D else stale), ""
    if op == 0x00 and funct in _SHIFTS and rt == register:
        return _narrowed(rd, register, stale, _stale_after_shift(funct, sa, stale))
    if op in _STORE_WIDTH and rt == register and rs != register:
        return (stale, "") if not stale & _STORE_WIDTH[op] else (None, "a store of the incoming bits")
    return None, "an instruction that observes the incoming bits"


def _narrowed(destination: int, register: int, stale: int, result: int) -> tuple[int | None, str]:
    if destination == register:
        return result, ""
    if destination == 0 or not result:
        return stale, ""
    return None, "a copy of the incoming bits into another register"


def _successors(flow: Any) -> dict[int, set[int]]:
    successors: dict[int, set[int]] = {}
    for target, sources in flow.fn.predecessors.items():
        for source in sources:
            successors.setdefault(source, set()).add(target)
    return successors


def masked_read_problem(ctx: Any, start: int, register: int, site: int) -> str | None:
    """Why the ELF does not prove the incoming bits read at ``site`` dead, or None.

    From ``site`` (all 64 bits incoming), every path must clear the bits
    still holding incoming data before an instruction observes them: a
    constant ``and``/``andi`` narrows them, an ``or``/``xor`` into the same
    register or a shift moves them, a narrow store or a shift into another
    register may ignore them, and a write without a read ends them.  They
    may not be live across a call or a tail jump (the callee may read the
    argument register) or past the end of the body; a ``jr ra`` ends them,
    since no argument register is a return register.
    """

    flow = ctx.flow(start)
    decoded = flow.fn.decoded
    if site not in decoded or not flow.reachable(site):
        return f"0x{site:x} is not a reachable instruction of 0x{start:x}"
    constants = _Constants(ctx, flow)
    successors = _successors(flow)
    seen: dict[int, int] = {}
    work = [(site, M64)]
    while work:
        pc, stale = work.pop()
        if pc in seen and (stale & ~seen[pc]) == 0:
            continue
        stale |= seen.get(pc, 0)
        seen[pc] = stale
        after, why = _step(constants, pc, ctx.code.word(pc), register, stale)
        if after is None:
            return f"{why} at 0x{pc:x} ({ctx.text(pc)})"
        if not after:
            continue
        owner = decoded.get(pc - 4) if pc > start else None
        if owner and owner["kind"] in ("call", "call-branch"):
            return f"incoming bits {after:#x} are live across the call at 0x{pc - 4:x}"
        if owner and owner["kind"] == "jr":
            if (ctx.code.word(pc - 4) >> 21) & 31 == 31:
                continue  # returned: the caller never reads an argument register
        if owner and owner["kind"] in ("jump", "branch") and not start <= (owner["target"] or -1) < flow.end:
            return f"incoming bits {after:#x} are live where 0x{pc - 4:x} leaves the body"
        following = successors.get(pc, set())
        if not following:
            return f"incoming bits {after:#x} are live where the path ends at 0x{pc:x}"
        work.extend((target, after) for target in sorted(following))
    return None


def _excluded_edges(flow: Any, branch: int, direction: str) -> set[tuple[int, int]] | str:
    row = flow.fn.decoded.get(branch)
    if row is None or row["kind"] != "branch":
        return f"0x{branch:x} is not a conditional branch of the function"
    target, slot = row["target"], branch + 4
    if direction not in ("taken", "not-taken"):
        return "direction is 'taken' or 'not-taken'"
    if row["likely"]:
        # The annulled path skips the delay slot; the taken path runs it.
        return {(branch, slot)} if direction == "taken" else {(branch, branch + 8)}
    return {(slot, target)} if direction == "taken" else {(slot, branch + 8)}


def unreachable_read_problem(ctx: Any, start: int, register: int, site: int, branch: int, direction: str) -> str | None:
    """Why removing the branch edge still lets the entry value reach ``site``, or None."""

    flow = ctx.flow(start)
    excluded = _excluded_edges(flow, branch, direction)
    if isinstance(excluded, str):
        return excluded
    # The search of recon facts' reaching definitions, without the excluded edge.
    def entry_at(pc: int) -> bool:
        return pc == start or (not flow.fn.predecessors.get(pc) and not flow.fn._dead(pc))

    if entry_at(site):
        return f"0x{site:x} is reached from the entry directly"
    stack = [(previous, site) for previous in flow.fn.predecessors.get(site, ())]
    seen: set[int] = set()
    while stack:
        pc, after = stack.pop()
        if (pc, after) in excluded or pc in seen:
            continue
        seen.add(pc)
        if register in flow.gwrites[pc]:
            continue
        if entry_at(pc):
            return f"the entry value still reaches 0x{site:x} through 0x{pc:x} without the {direction} edge of 0x{branch:x}"
        stack.extend((previous, pc) for previous in flow.fn.predecessors.get(pc, ()))
    return None


def dead_read_problems(ctx: Any, start: int, rows: Any, reads: dict[str, list[int]]) -> tuple[dict[str, set[int]], list[str]]:
    """({register: dead sites}, problems) for a prototype's ``dead_reads`` rows.

    Each row names an argument register, a ``site`` where recon facts lists
    it read before any write, its ``kind`` and evidence: ``masked`` rows are
    proven here; ``unreachable`` rows name the ``branch`` and the
    ``direction`` that cannot happen, and removing that edge must leave no
    path from the entry to the read.
    """

    dead: dict[str, set[int]] = {}
    problems: list[str] = []
    if rows is None:
        return dead, problems
    if not isinstance(rows, list):
        return dead, ["dead_reads must be a list"]
    for row in rows:
        row = row if isinstance(row, dict) else {}
        register, kind = str(row.get("register", "")), row.get("kind")
        where = f"dead read {register!r} at {row.get('site')!r}"
        try:
            site = int(str(row.get("site", "")), 16)
        except ValueError:
            problems.append(f"{where} needs a hex site")
            continue
        if not row.get("evidence"):
            problems.append(f"{where} needs evidence")
        if register not in GPR_NUMBERS:
            problems.append(f"{where}: dead_reads covers the argument GPRs a0-t3")
            continue
        if site not in reads.get(register, []):
            problems.append(f"{where}: recon facts does not list {register} read before any write there")
            continue
        if site in dead.get(register, set()):
            problems.append(f"{where} appears twice")
            continue
        if kind == "masked":
            if why := masked_read_problem(ctx, start, GPR_NUMBERS[register], site):
                problems.append(f"{where} is not proven masked: {why}")
                continue
        elif kind == "unreachable":
            try:
                branch = int(str(row.get("branch", "")), 16)
            except ValueError:
                problems.append(f"{where} needs the hex branch whose direction cannot happen")
                continue
            if why := unreachable_read_problem(
                ctx, start, GPR_NUMBERS[register], site, branch, str(row.get("direction", ""))
            ):
                problems.append(f"{where} is not explained by the {row.get('direction')} edge of {row.get('branch')}: {why}")
                continue
        else:
            problems.append(f"{where}: kind is one of {', '.join(DEAD_READ_KINDS)}")
            continue
        dead.setdefault(register, set()).add(site)
    return dead, problems


def dead_read_note(row: dict[str, Any]) -> str:
    """The program note recording one dead_reads row."""

    evidence = row.get("evidence")
    text = "; ".join(evidence) if isinstance(evidence, list) else str(evidence)
    how = f"the {row.get('direction')} edge of {row.get('branch')} cannot happen" if row.get("kind") == "unreachable" else "masked before use"
    return f"read of {row.get('register')} at {row.get('site')} is dead ({how}): {text}"

