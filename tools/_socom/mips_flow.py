"""Reaching-definition pairing of R5900 R_MIPS_HI16/R_MIPS_LO16 relocations.

Metrowerks does not emit each HI16 relocation next to its LO16s: HI16s of one
section symbol interleave across functions and some follow their LO16.  An
LO16 therefore pairs with the ``lui`` whose write of the LO16's base register
reaches the site.  This module builds an intra-function control-flow graph
(delay slots, branch-likely annulment, calls clobbering caller-saved
registers, jump-table targets) and searches backwards for those definitions.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from typing import Any

from .elf import Elf32File

CALL_CLOBBERED = frozenset([1, 2, 3, *range(4, 16), 24, 25, 31])
# An EE kernel call (`li v1,N; syscall`) returns its result in v0.
SYSCALL_WRITES = frozenset([2])


def is_syscall(insn: int) -> bool:
    return insn & 0xFC00003F == 0x0000000C
_ITYPE_WRITES_RT = {
    0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x18, 0x19,
    0x1A, 0x1B, 0x1E, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x37,
}
_BRANCH = {0x04: False, 0x05: False, 0x06: False, 0x07: False, 0x14: True, 0x15: True, 0x16: True, 0x17: True}
_REGIMM_BRANCH = {0x00: False, 0x01: False, 0x02: True, 0x03: True, 0x10: False, 0x11: False, 0x12: True, 0x13: True}


def _sign16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class _Code:
    def __init__(self, elf: Elf32File) -> None:
        self.segment = next(elf.load_segments())
        self.data = elf.data

    def word(self, address: int) -> int:
        offset = self.segment.offset + address - self.segment.virtual_address
        return int.from_bytes(self.data[offset : offset + 4], "little")


def decode(insn: int, address: int) -> dict[str, Any]:
    """Control flow and GPR writes of one R5900 instruction."""

    opcode = insn >> 26
    rs, rt, rd = (insn >> 21) & 0x1F, (insn >> 16) & 0x1F, (insn >> 11) & 0x1F
    result: dict[str, Any] = {"writes": frozenset(), "kind": "plain", "target": None, "likely": False}
    if opcode == 0x00:
        funct = insn & 0x3F
        if funct == 0x08:
            result["kind"] = "jr"
        elif funct == 0x09:
            result.update(kind="call", writes=frozenset([rd]))
        elif funct == 0x0C:
            # syscall: the EE kernel returns its result in v0 (its code field
            # is not a register).
            result["writes"] = SYSCALL_WRITES
        elif funct not in (0x0D, 0x0F) and rd:
            result["writes"] = frozenset([rd])
    elif opcode == 0x1C:
        if rd:
            result["writes"] = frozenset([rd])
    elif opcode == 0x01 and rt in _REGIMM_BRANCH:
        target = address + 4 + (_sign16(insn & 0xFFFF) << 2)
        result.update(kind="branch", likely=_REGIMM_BRANCH[rt], target=target)
        if rt & 0x10:
            result.update(kind="call-branch", writes=frozenset([31]))
        if rs == 0 and rt in (0x01, 0x03):
            # bgez zero: always taken, no fall-through.
            result.update(kind="jump", likely=False)
        elif rs == 0 and rt in (0x11, 0x13):
            # bal: an unconditional call.
            result.update(kind="call", likely=False, target=None)
    elif opcode in _BRANCH:
        result.update(kind="branch", likely=_BRANCH[opcode], target=address + 4 + (_sign16(insn & 0xFFFF) << 2))
        if opcode in (0x04, 0x14) and rs == rt:
            # b (beq x,x): always taken, so its delay slot never falls through.
            result.update(kind="jump", likely=False)
    elif opcode in (0x10, 0x11, 0x12) and rs == 0x08:
        result.update(kind="branch", likely=bool(rt & 0x2), target=address + 4 + (_sign16(insn & 0xFFFF) << 2))
    elif opcode in (0x10, 0x11, 0x12) and rs in (0x00, 0x01, 0x02) and rt:
        result["writes"] = frozenset([rt])
    elif opcode == 0x02:
        result.update(kind="jump", target=(address & 0xF0000000) | ((insn & 0x03FFFFFF) << 2))
    elif opcode == 0x03:
        result.update(kind="call", writes=frozenset([31]))
    elif opcode in _ITYPE_WRITES_RT and rt:
        result["writes"] = frozenset([rt])
    return result


class _Function:
    """Predecessor graph of one function; nodes are instruction addresses."""

    def __init__(self, code: _Code, start: int, end: int, table_targets: set[int]) -> None:
        self.start, self.end = start, end
        self.decoded = {address: decode(code.word(address), address) for address in range(start, end, 4)}
        # A call's delay slot runs before the callee; the callee's clobbers
        # take effect when control returns after that slot.
        self.exit_writes = {
            address: row["writes"]
            | (CALL_CLOBBERED if self.decoded.get(address - 4, {}).get("kind") in ("call", "call-branch") else frozenset())
            for address, row in self.decoded.items()
        }
        self.predecessors: dict[int, set[int]] = defaultdict(set)
        indirect = [address for address, row in self.decoded.items() if row["kind"] == "jr" and (code.word(address) >> 21) & 0x1F != 31]
        for address, row in self.decoded.items():
            successors: list[int] = []
            if row["kind"] in ("branch", "call-branch"):
                successors = [address + 4]
                if row["likely"]:
                    # The annulled path skips the delay slot.
                    successors.append(address + 8)
            elif row["kind"] in ("jump", "jr"):
                successors = [address + 4]
            elif self._in_delay_slot(address):
                owner = self.decoded[address - 4]
                if owner["kind"] in ("branch", "call-branch"):
                    successors = [owner["target"]] + ([] if owner["likely"] else [address + 4])
                elif owner["kind"] == "jump":
                    successors = [owner["target"]]
                elif owner["kind"] == "jr":
                    successors = []
                else:  # call: returns after the delay slot
                    successors = [address + 4]
            else:
                successors = [address + 4]
            for successor in successors:
                if start <= successor < end:
                    self.predecessors[successor].add(address)
        # Jump-table targets inside the function follow its indirect jumps.
        for target in table_targets:
            if start <= target < end:
                for jump in indirect:
                    self.predecessors[target].add(jump + 4)

    def _dead(self, address: int) -> bool:
        """Padding after an unconditional transfer's delay slot that nothing reaches."""

        while address > self.start and not self.predecessors.get(address):
            owner = self.decoded.get(address - 8)
            if owner and owner["kind"] in ("jump", "jr"):
                return True
            address -= 4
        return False

    def _in_delay_slot(self, address: int) -> bool:
        previous = self.decoded.get(address - 4)
        return bool(previous) and previous["kind"] in ("branch", "call-branch", "jump", "jr", "call")

    def definitions(self, site: int, register: int) -> set[Any]:
        """Instructions whose write of ``register`` reaches ``site``; 'entry' if none."""

        found: set[Any] = set()
        seen: set[int] = set()
        stack = list(self.predecessors.get(site, ()))
        if not stack:
            return {"entry"}
        while stack:
            address = stack.pop()
            if address in seen:
                continue
            seen.add(address)
            if register in self.exit_writes[address]:
                found.add(address)
                continue
            previous = self.predecessors.get(address)
            if not previous:
                if not self._dead(address):
                    found.add("entry")
                continue
            stack.extend(previous)
        return found


# SPECIAL addu/daddu/or copy or combine registers; an indexed access adds an
# index to the %hi register before the %lo load (lui; addu; lw %lo(base)).
_COMBINE_FUNCTS = {0x21, 0x2D, 0x25}


def _resolve(
    function: "_Function",
    code: _Code,
    hi16: dict[int, int],
    hi16_symbol: dict[int, int],
    symbol: int,
    site: int,
    register: int,
    depth: int,
) -> tuple[set[int], set[int], str | None]:
    """HI16 values of ``symbol`` reaching ``register`` at ``site``."""

    uppers: set[int] = set()
    sources: set[int] = set()
    for definition in function.definitions(site, register):
        if definition == "entry":
            return set(), set(), "the base register is live on function entry"
        if definition in hi16:
            if hi16_symbol[definition] != symbol:
                return set(), set(), f"HI16 at 0x{definition:x} relocates a different symbol"
            uppers.add(hi16[definition])
            sources.add(definition)
            continue
        insn = code.word(definition)
        opcode, funct = insn >> 26, insn & 0x3F
        rs, rt = (insn >> 21) & 0x1F, (insn >> 16) & 0x1F
        if depth < 4 and opcode == 0x00 and funct in _COMBINE_FUNCTS:
            # Exactly one operand may carry the %hi value; the other is an index.
            carriers = []
            for operand in {rs, rt} - {0}:
                found, found_sources, _reason = _resolve(
                    function, code, hi16, hi16_symbol, symbol, definition, operand, depth + 1
                )
                if found:
                    carriers.append((found, found_sources))
            if len(carriers) == 1:
                uppers |= carriers[0][0]
                sources |= carriers[0][1]
                continue
        return set(), set(), f"base register defined at 0x{definition:x} without an HI16 relocation"
    return uppers, sources, None


def lo16_targets(elf: Elf32File) -> dict[int, dict[str, Any]]:
    """Map each R_MIPS_LO16 site to its proven target or an unresolved reason."""

    code = _Code(elf)
    symbols = list(elf.symbols())
    functions = sorted((s.value, s.value + s.size) for s in symbols if s.type_name == "FUNC" and s.size)
    starts = [row[0] for row in functions]
    # Hand-written startup code (crt0's _start) has only unsized NOTYPE
    # labels; such sites use the span between neighbouring code labels.
    executable_end = code.segment.virtual_address + code.segment.file_size
    labels = sorted(
        {
            s.value
            for s in symbols
            if s.type_name in ("FUNC", "NOTYPE") and s.name and code.segment.virtual_address <= s.value < executable_end
        }
    )
    relocations = list(elf.relocations(".relmain"))
    hi16: dict[int, int] = {}
    hi16_symbol: dict[int, int] = {}
    for relocation in relocations:
        if relocation.type_name == "R_MIPS_HI16":
            hi16[relocation.offset] = code.word(relocation.offset) & 0xFFFF
            hi16_symbol[relocation.offset] = relocation.symbol_index
    table_targets = {code.word(r.offset) for r in relocations if r.type_name == "R_MIPS_32"}
    cache: dict[tuple[int, int], _Function] = {}
    results: dict[int, dict[str, Any]] = {}
    for relocation in relocations:
        if relocation.type_name != "R_MIPS_LO16":
            continue
        site = relocation.offset
        insn = code.word(site)
        base = (insn >> 21) & 0x1F
        index = bisect.bisect_right(starts, site) - 1
        if index >= 0 and functions[index][0] <= site < functions[index][1]:
            bounds = functions[index]
        else:
            position = bisect.bisect_right(labels, site) - 1
            if position < 0 or position + 1 >= len(labels):
                results[site] = {"target": None, "reason": "outside every code label span"}
                continue
            bounds = (labels[position], labels[position + 1])
        function = cache.get(bounds)
        if function is None:
            function = cache[bounds] = _Function(code, bounds[0], bounds[1], table_targets)
        uppers, sources, reason = _resolve(function, code, hi16, hi16_symbol, relocation.symbol_index, site, base, 0)
        definitions = sources
        if reason is None and len(uppers) == 1:
            upper = uppers.pop()
            results[site] = {
                "target": ((upper << 16) + _sign16(insn & 0xFFFF)) & 0xFFFFFFFF,
                "hi16": sorted(d for d in definitions if d != "entry"),
            }
        else:
            results[site] = {"target": None, "reason": reason or f"reaching HI16 values differ: {sorted(uppers)}"}
    return results
