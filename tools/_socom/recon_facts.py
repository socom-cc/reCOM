"""Compact, ELF-only function facts for stage 3 planners and reviewers.

Every planner and reviewer needs the same few facts about a function: which
argument registers it reads on some path before writing them, what sets
v0/f0 at each return, every call site with the caller's argument setup and
how the caller uses the result, the vtable/table slots and code sites that
take its address, and its disassembly.  This module derives them from the
immutable ELF (relocations, symbols, instruction decoding) and prints short
text, so agents do not rebuild decoders or page through bridge JSON.
"""

from __future__ import annotations

import bisect
from functools import lru_cache
from pathlib import Path
from typing import Any

from .batch_apply import (
    _PARTIAL_LOAD_PARTNER,
    _completed_partial_load,
    _reads,
    _writes,
)
from .elf import Elf32File
from .mips_flow import _Code, _Function
from .mwdemangle import demangle, readable_component, render_type
from .util import file_key

GPR = (
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 "
    "s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra"
).split()
ARG_GPRS = tuple(range(4, 12))
ARG_FPRS = tuple(range(12, 20))
FPR_CLOBBERED = frozenset(range(0, 20))
JR_RA = 0x03E00008

_SPECIAL = {
    0x00: "sll", 0x02: "srl", 0x03: "sra", 0x04: "sllv", 0x06: "srlv", 0x07: "srav", 0x08: "jr",
    0x09: "jalr", 0x0A: "movz", 0x0B: "movn", 0x0C: "syscall", 0x0D: "break", 0x0F: "sync",
    0x10: "mfhi", 0x11: "mthi", 0x12: "mflo", 0x13: "mtlo", 0x14: "dsllv", 0x16: "dsrlv", 0x17: "dsrav",
    0x18: "mult", 0x19: "multu", 0x1A: "div", 0x1B: "divu", 0x20: "add", 0x21: "addu", 0x22: "sub",
    0x23: "subu", 0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor", 0x28: "mfsa", 0x29: "mtsa",
    0x2A: "slt", 0x2B: "sltu", 0x2C: "dadd", 0x2D: "daddu", 0x2E: "dsub", 0x2F: "dsubu",
    0x38: "dsll", 0x3A: "dsrl", 0x3B: "dsra", 0x3C: "dsll32", 0x3E: "dsrl32", 0x3F: "dsra32",
}
_IMM = {
    0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu", 0x0C: "andi", 0x0D: "ori", 0x0E: "xori",
    0x18: "daddi", 0x19: "daddiu",
}
_MEM = {
    0x1A: "ldl", 0x1B: "ldr", 0x1E: "lq", 0x1F: "sq", 0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw",
    0x24: "lbu", 0x25: "lhu", 0x26: "lwr", 0x27: "lwu", 0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw",
    0x2C: "sdl", 0x2D: "sdr", 0x2E: "swr", 0x2F: "cache", 0x31: "lwc1", 0x33: "pref", 0x36: "lqc2",
    0x37: "ld", 0x39: "swc1", 0x3E: "sqc2", 0x3F: "sd",
}
_BRANCH = {0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz", 0x14: "beql", 0x15: "bnel", 0x16: "blezl", 0x17: "bgtzl"}
_REGIMM = {0x00: "bltz", 0x01: "bgez", 0x02: "bltzl", 0x03: "bgezl", 0x10: "bltzal", 0x11: "bgezal", 0x12: "bltzall", 0x13: "bgezall"}
_FMT_S = {
    0x00: "add.s", 0x01: "sub.s", 0x02: "mul.s", 0x03: "div.s", 0x04: "sqrt.s", 0x05: "abs.s", 0x06: "mov.s",
    0x07: "neg.s", 0x16: "rsqrt.s", 0x18: "adda.s", 0x19: "suba.s", 0x1A: "mula.s", 0x1C: "madd.s",
    0x1D: "msub.s", 0x1E: "madda.s", 0x1F: "msuba.s", 0x24: "cvt.w.s", 0x28: "max.s", 0x29: "min.s",
    0x30: "c.f.s", 0x32: "c.eq.s", 0x34: "c.lt.s", 0x36: "c.le.s",
}


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def disasm(insn: int, pc: int, label: Any = None) -> str:
    """One R5900 instruction as short text; ``label(addr)`` names call targets."""

    name = label or (lambda address: f"0x{address:x}")
    op, rs, rt, rd = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, (insn >> 11) & 31
    sa, funct, imm = (insn >> 6) & 31, insn & 0x3F, insn & 0xFFFF
    r = GPR
    if insn == 0:
        return "nop"
    if op == 0x00:
        m = _SPECIAL.get(funct)
        if m is None:
            return f".word 0x{insn:08x}"
        if funct in (0x00, 0x02, 0x03, 0x38, 0x3A, 0x3B, 0x3C, 0x3E, 0x3F):
            return f"{m} {r[rd]},{r[rt]},{sa}"
        if funct in (0x04, 0x06, 0x07, 0x14, 0x16, 0x17):
            return f"{m} {r[rd]},{r[rt]},{r[rs]}"
        if funct == 0x08:
            return "jr ra" if rs == 31 else f"jr {r[rs]}"
        if funct == 0x09:
            return f"jalr {r[rs]}" if rd == 31 else f"jalr {r[rd]},{r[rs]}"
        if funct in (0x0C, 0x0D, 0x0F):
            return m
        if funct in (0x10, 0x12, 0x28):
            return f"{m} {r[rd]}"
        if funct in (0x11, 0x13, 0x29):
            return f"{m} {r[rs]}"
        if funct in (0x18, 0x19, 0x1A, 0x1B):
            return f"{m} {r[rd]},{r[rs]},{r[rt]}" if rd else f"{m} {r[rs]},{r[rt]}"
        if funct in (0x21, 0x2D) and rt == 0:
            return f"move {r[rd]},{r[rs]}"
        if funct == 0x25 and rt == 0:
            return f"move {r[rd]},{r[rs]}"
        return f"{m} {r[rd]},{r[rs]},{r[rt]}"
    if op == 0x01:
        m = _REGIMM.get(rt)
        if m is None:
            return f".word 0x{insn:08x}"
        target = pc + 4 + (_s16(imm) << 2)
        return f"{m} {r[rs]},0x{target:x}"
    if op in (0x02, 0x03):
        target = ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)
        return f"{'j' if op == 2 else 'jal'} {name(target)}"
    if op in _BRANCH:
        target = pc + 4 + (_s16(imm) << 2)
        m = _BRANCH[op]
        if op in (0x04, 0x05, 0x14, 0x15):
            if op == 0x04 and rs == rt == 0:
                return f"b 0x{target:x}"
            return f"{m} {r[rs]},{r[rt]},0x{target:x}"
        return f"{m} {r[rs]},0x{target:x}"
    if op == 0x0F:
        return f"lui {r[rt]},0x{imm:x}"
    if op in _IMM:
        m = _IMM[op]
        if op == 0x09 and rs == 0:
            return f"li {r[rt]},{_s16(imm)}"
        if op == 0x0D and rs == 0:
            return f"li {r[rt]},0x{imm:x}"
        if op in (0x0C, 0x0D, 0x0E):
            return f"{m} {r[rt]},{r[rs]},0x{imm:x}"
        return f"{m} {r[rt]},{r[rs]},{_s16(imm)}"
    if op in _MEM:
        m = _MEM[op]
        reg = f"f{rt}" if op in (0x31, 0x39) else (f"vf{rt}" if op in (0x36, 0x3E) else r[rt])
        return f"{m} {reg},{_s16(imm)}({r[rs]})"
    if op == 0x10:
        if rs == 0x00:
            return f"mfc0 {r[rt]},${rd}"
        if rs == 0x04:
            return f"mtc0 {r[rt]},${rd}"
        if rs == 0x10 and funct == 0x18:
            return "eret"
        return f"cop0 0x{insn:08x}"
    if op == 0x11:
        fs, fd = rd, sa
        if rs == 0x00:
            return f"mfc1 {r[rt]},f{fs}"
        if rs == 0x02:
            return f"cfc1 {r[rt]},${fs}"
        if rs == 0x04:
            return f"mtc1 {r[rt]},f{fs}"
        if rs == 0x06:
            return f"ctc1 {r[rt]},${fs}"
        if rs == 0x08:
            target = pc + 4 + (_s16(imm) << 2)
            return f"bc1{'tf'[not (rt & 1)]}{'l' if rt & 2 else ''} 0x{target:x}"
        if rs == 0x10:
            m = _FMT_S.get(funct, f"cop1.s.{funct:02x}")
            if funct in (0x04,):
                return f"{m} f{fd},f{rt}"
            if funct in (0x05, 0x06, 0x07, 0x24):
                return f"{m} f{fd},f{fs}"
            if funct >= 0x30 or funct in (0x18, 0x19, 0x1A, 0x1E, 0x1F):
                return f"{m} f{fs},f{rt}"
            return f"{m} f{fd},f{fs},f{rt}"
        if rs == 0x14 and funct == 0x20:
            return f"cvt.s.w f{fd},f{fs}"
        return f"cop1 0x{insn:08x}"
    if op == 0x12:
        if rs == 0x01:
            return f"qmfc2 {r[rt]},vf{rd}"
        if rs == 0x05:
            return f"qmtc2 {r[rt]},vf{rd}"
        if rs == 0x02:
            return f"cfc2 {r[rt]},vi{rd}"
        if rs == 0x06:
            return f"ctc2 {r[rt]},vi{rd}"
        return f"cop2 0x{insn:08x}"
    if op == 0x1C:
        return f"mmi.{funct:02x} {r[rd]},{r[rs]},{r[rt]}"
    return f".word 0x{insn:08x}"


class _Context:
    def __init__(self, root: Path) -> None:
        from .recon import code_data_references, function_graph

        path = root / "support" / "socom.elf"
        self.elf = Elf32File(path)
        self.code = _Code(self.elf)
        self.graph = function_graph(root)
        self.functions = self.graph["functions"]
        self.starts = [row["start"] for row in self.functions]
        self.size = {row["start"]: row["size"] for row in self.functions}
        relocations = list(self.elf.relocations(".relmain"))
        self.table_targets = {self.code.word(r.offset) for r in relocations if r.type_name == "R_MIPS_32"}
        self.word32: dict[int, list[int]] = {}
        for relocation in relocations:
            if relocation.type_name == "R_MIPS_32":
                self.word32.setdefault(self.code.word(relocation.offset), []).append(relocation.offset)
        self.refs = code_data_references(root)
        self.ref_at = {int(row["site"], 16): row for row in self.refs}
        self.addr_taken: dict[int, list[int]] = {}
        for row in self.refs:
            if row["target"] is not None:
                self.addr_taken.setdefault(int(row["target"], 16), []).append(int(row["site"], 16))
        objects: dict[int, tuple[int, str]] = {}
        names: dict[int, str] = {}
        for symbol in self.elf.symbols():
            if not symbol.name:
                continue
            if symbol.type_name == "OBJECT" and symbol.size:
                if symbol.value not in objects or symbol.size > objects[symbol.value][0]:
                    objects[symbol.value] = (symbol.size, symbol.name)
            if symbol.type_name in ("FUNC", "OBJECT") and symbol.value not in names:
                names[symbol.value] = symbol.name
        self.objects = objects
        self.object_starts = sorted(objects)
        self.names = names
        self._flows: dict[int, Any] = {}

    def label(self, address: int) -> str:
        name = self.names.get(address)
        return f"{name}@0x{address:x}" if name else f"0x{address:x}"

    def owner(self, address: int) -> int | None:
        position = bisect.bisect_right(self.starts, address) - 1
        if position >= 0 and address < self.starts[position] + self.functions[position]["size"]:
            return self.starts[position]
        return None

    def object_for(self, address: int) -> str | None:
        position = bisect.bisect_right(self.object_starts, address) - 1
        if position < 0:
            return None
        start = self.object_starts[position]
        size, name = self.objects[start]
        if address >= start + size:
            return None
        return f"{name}+0x{address - start:x}"

    def flow(self, start: int) -> "_Flow":
        if start not in self._flows:
            self._flows[start] = _Flow(self, start, start + self.size[start])
        return self._flows[start]

    def text(self, pc: int) -> str:
        line = disasm(self.code.word(pc), pc, self.label)
        ref = self.ref_at.get(pc)
        if ref and ref["target"]:
            target = int(ref["target"], 16)
            line += f"  ; {self.object_for(target) or self.label(target)}"
        return line


class _Flow:
    """Reaching definitions over one function, for GPRs and FPRs."""

    def __init__(self, ctx: _Context, start: int, end: int) -> None:
        self.ctx, self.start, self.end = ctx, start, end
        self.fn = _Function(ctx.code, start, end, ctx.table_targets)
        self.gwrites: dict[int, frozenset[int]] = {}
        self.fwrites: dict[int, frozenset[int]] = {}
        for pc in range(start, end, 4):
            wrote_g, wrote_f = _writes(ctx.code.word(pc))
            after_call = self.fn.decoded.get(pc - 4, {}).get("kind") in ("call", "call-branch")
            self.gwrites[pc] = self.fn.exit_writes[pc]
            self.fwrites[pc] = frozenset(wrote_f) | (FPR_CLOBBERED if after_call else frozenset())

    def reachable(self, pc: int) -> bool:
        return pc == self.start or bool(self.fn.predecessors.get(pc))

    def defs(self, site: int, register: int, fpr: bool = False) -> set[Any]:
        """Definitions of the register reaching ``site`` (before it runs); 'entry' if live-in."""

        writes = self.fwrites if fpr else self.gwrites
        # The function start always has the implicit entry edge, even when a
        # loop also branches back to it.
        found: set[Any] = {"entry"} if site == self.start else set()
        seen: set[int] = set()
        stack = list(self.fn.predecessors.get(site, ()))
        if not stack:
            return {"entry"} if site == self.start or not self.fn._dead(site) else set()
        while stack:
            pc = stack.pop()
            if pc in seen:
                continue
            seen.add(pc)
            if register in writes[pc]:
                found.add(pc)
                continue
            if pc == self.start:
                found.add("entry")
            previous = self.fn.predecessors.get(pc)
            if not previous:
                if pc == self.start or not self.fn._dead(pc):
                    found.add("entry")
                continue
            stack.extend(previous)
        return found

    def after(self, site: int, register: int, fpr: bool = False) -> set[Any]:
        """Definitions live after ``site`` executes (including a preceding call's clobbers)."""

        writes = self.fwrites if fpr else self.gwrites
        if register in writes.get(site, frozenset()):
            return {site}
        return self.defs(site, register, fpr)

    def entering_callee(self, slot: int, register: int, fpr: bool = False) -> set[Any]:
        """Definitions a callee sees: the call's delay slot ran, the callee has not."""

        own_g, own_f = _writes(self.ctx.code.word(slot))
        if register in (own_f if fpr else own_g):
            return {slot}
        return self.defs(slot, register, fpr)


def _reads_at(ctx: _Context, pc: int, end: int) -> tuple[set[int], set[int]]:
    insn = ctx.code.word(pc)
    read_g, read_f = _reads(insn)
    read_g = set(read_g)
    op = insn >> 26
    if op == 0x00 and insn & 0x3F in (0x0A, 0x0B):
        read_g |= {(insn >> 11) & 31} - {0}
    elif op == 0x10 and (insn >> 21) & 31 == 0x04:
        read_g |= {(insn >> 16) & 31} - {0}
    elif op == 0x2F:
        read_g |= {(insn >> 21) & 31} - {0}
    if op in _PARTIAL_LOAD_PARTNER and _completed_partial_load(ctx.elf, pc, end):
        read_g -= {(insn >> 16) & 31}
    return read_g, set(read_f)


def argument_reads(ctx: _Context, start: int) -> dict[str, list[int]]:
    """Argument registers read on some path before any write, with the first sites."""

    flow = ctx.flow(start)
    found: dict[str, list[int]] = {}
    for pc in range(start, flow.end, 4):
        if not flow.reachable(pc):
            continue
        read_g, read_f = _reads_at(ctx, pc, flow.end)
        for reg in sorted(read_g & set(ARG_GPRS)):
            if "entry" in flow.defs(pc, reg):
                found.setdefault(GPR[reg], []).append(pc)
        for reg in sorted(read_f & set(ARG_FPRS)):
            if "entry" in flow.defs(pc, reg, fpr=True):
                found.setdefault(f"f{reg}", []).append(pc)
    return found


def _describe_def(ctx: _Context, flow: _Flow, definition: Any) -> str:
    if definition == "entry":
        return "entry"
    previous = flow.fn.decoded.get(definition - 4, {})
    if previous.get("kind") in ("call", "call-branch") and definition not in (flow.start,):
        # The definition is a call's delay slot whose exit carries the callee's
        # clobbers; unless the slot itself writes the register, the value is the
        # callee's result.
        call = ctx.code.word(definition - 4)
        callee = (
            ctx.label(((definition) & 0xF0000000) | ((call & 0x03FFFFFF) << 2))
            if call >> 26 == 0x03
            else f"indirect {disasm(call, definition - 4)}"
        )
        return f"ret({callee})"
    return f"{ctx.text(definition)}@0x{definition:x}"


def return_sources(ctx: _Context, start: int) -> list[str]:
    """What sets v0 and f0 at each exit (jr ra and tail jumps)."""

    flow = ctx.flow(start)
    rows = []
    for pc in range(start, flow.end, 4):
        insn = ctx.code.word(pc)
        if not flow.reachable(pc):
            continue
        if insn == JR_RA:
            slot = pc + 4
            v0 = sorted(_describe_def(ctx, flow, d) for d in flow.after(slot, 2))
            f0 = sorted(_describe_def(ctx, flow, d) for d in flow.after(slot, 0, fpr=True))
            rows.append(f"jr ra@0x{pc:x}: v0<-{' | '.join(v0) or '-'}; f0<-{' | '.join(f0) or '-'}")
        elif insn >> 26 == 0x02:
            target = ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)
            if not (start <= target < flow.end):
                rows.append(f"tail j@0x{pc:x} -> {ctx.label(target)}")
    return rows


def _use_after_call(ctx: _Context, caller: int, site: int, fpr: bool) -> str:
    """First use of v0 (or f0) after a call returns, scanning linearly to a transfer."""

    end = caller + ctx.size[caller]
    register = 0 if fpr else 2
    pc = site + 8
    while pc < end:
        insn = ctx.code.word(pc)
        read_g, read_f = _reads_at(ctx, pc, end)
        if (register in read_f) if fpr else (register in read_g):
            return f"{ctx.text(pc)}@0x{pc:x}"
        wrote_g, wrote_f = _writes(insn)
        if (register in wrote_f) if fpr else (register in wrote_g):
            return f"overwritten@0x{pc:x}"
        kind = ctx.flow(caller).fn.decoded[pc]["kind"]
        if kind != "plain":
            # The delay slot runs first; check it, then stop.
            slot = pc + 4
            if slot < end:
                read_g, read_f = _reads_at(ctx, slot, end)
                if (register in read_f) if fpr else (register in read_g):
                    return f"{ctx.text(slot)}@0x{slot:x} (delay slot of {ctx.text(pc)})"
            if insn == JR_RA:
                return f"returned by caller@0x{pc:x}"
            if kind == "call":
                return f"unused; clobbered by {ctx.text(pc)}@0x{pc:x}"
            return f"unused before {ctx.text(pc)}@0x{pc:x}"
        pc += 4
    return "unused"


def call_sites(ctx: _Context, target: int) -> list[tuple[int, int, str]]:
    """Every jal/j to ``target`` from a sized function: (caller, site, kind)."""

    rows = []
    for caller in ctx.graph["callers"].get(target, ()):
        for site in ctx.graph["call_sites"].get((caller, target), ()):
            kind = "call" if ctx.code.word(site) >> 26 == 0x03 else "tail"
            rows.append((caller, site, kind))
    return sorted(rows, key=lambda row: row[1])


def _demangled(names: list[str]) -> str | None:
    for name in names:
        parsed = demangle(name)
        if parsed:
            qualifier = "::".join(readable_component(part) for part in parsed["qualifier"])
            params = parsed["params"]
            rendered = "" if params is None else "(" + ", ".join(render_type(p) for p in params) + ")"
            return f"{qualifier + '::' if qualifier else ''}{parsed['name']}{rendered}{' const' if parsed['const'] else ''}"
    return None


def _evidence_lines(evidence: dict[str, Any] | None) -> list[str]:
    """DWARF, stage 2 and data-reference facts from a group's evidence row, compactly."""

    if not evidence:
        return []
    lines = []
    if evidence.get("compile_unit"):
        lines.append(f"cu: {evidence['compile_unit']['path']}")
    dwarf = evidence.get("dwarf")
    if dwarf:
        params = ", ".join(p.get("name") or "?" for p in dwarf.get("parameters") or [])
        lines.append(f"dwarf: {dwarf.get('qualified_name')}({params}) storage={dwarf.get('parameter_storage')}")
    stage2 = evidence.get("stage2")
    if stage2:
        prototype = stage2.get("prototype")
        if prototype:
            params = ", ".join(f"{p['type']} {p['name']}" for p in prototype["parameters"])
            lines.append(f"stage2 prototype: {prototype['return_type']} ({params}) receiver={stage2.get('receiver')}")
        elif stage2.get("prototype_skip"):
            lines.append(f"stage2 skip: {stage2['prototype_skip']}")
    refs = evidence.get("data_references") or []
    if refs:
        shown = [
            f"{(r.get('object') or {}).get('names', ['?'])[0]}+0x{(r.get('object') or {}).get('offset', 0):x} {r['access']}"
            if r.get("object") else f"{r.get('target')} {r['access']}"
            for r in refs[:10]
        ]
        lines.append(f"data refs ({len(refs)}): " + ", ".join(shown) + (" ..." if len(refs) > 10 else ""))
    return lines


def function_facts(ctx: _Context, start: int, caller_limit: int = 24, evidence: dict[str, Any] | None = None) -> str:
    if start not in ctx.size:
        return f"0x{start:x}: not a sized FUNC symbol"
    row = ctx.functions[bisect.bisect_left(ctx.starts, start)]
    lines = [f"## 0x{start:x} {' = '.join(row['names'])} [{row['size']} bytes]"]
    if (text := _demangled(row["names"])):
        lines.append(f"demangled: {text}")
    lines.extend(_evidence_lines(evidence))
    reads = argument_reads(ctx, start)
    lines.append(
        "args read before write (any path): "
        + (", ".join(f"{reg}@" + ",".join(f"0x{pc:x}" for pc in sites[:3]) for reg, sites in reads.items()) or "none")
    )
    exits = return_sources(ctx, start)
    lines.extend(f"exit {text}" for text in exits)
    sets_f0 = any("f0<-" in text and "f0<-entry" not in text for text in exits)
    slots = [f"{ctx.object_for(site) or f'0x{site:x}'}" for site in ctx.word32.get(start, ())]
    if slots:
        lines.append(f"word refs ({len(slots)}): " + ", ".join(slots[:40]) + (f" ... ({len(slots) - 40} more)" if len(slots) > 40 else ""))
    taken = ctx.addr_taken.get(start, ())
    if taken:
        lines.append(
            f"address taken ({len(taken)}): "
            + "; ".join(f"{ctx.text(pc)}@0x{pc:x} in {ctx.label(ctx.owner(pc)) if ctx.owner(pc) else '?'}" for pc in taken[:8])
        )
    sites = call_sites(ctx, start)
    regs = sorted({reg for reg in reads if reg.startswith(("a", "t"))} | {"a0"}, key=lambda r: GPR.index(r))
    fregs = sorted({reg for reg in reads if reg.startswith("f")}, key=lambda r: int(r[1:]))
    lines.append(f"call sites: {len(sites)} ({sum(1 for s in sites if s[2] == 'tail')} tail)")
    for caller, site, kind in sites[:caller_limit]:
        flow = ctx.flow(caller)
        slot = site + 4
        setup = []
        for reg in regs:
            defs = sorted(
                f"{ctx.text(d)}@0x{d:x}" if d == slot else _describe_def(ctx, flow, d)
                for d in flow.entering_callee(slot, GPR.index(reg))
            )
            setup.append(f"{reg}={'|'.join(defs)}")
        for reg in fregs:
            defs = sorted(
                f"{ctx.text(d)}@0x{d:x}" if d == slot else _describe_def(ctx, flow, d)
                for d in flow.entering_callee(slot, int(reg[1:]), fpr=True)
            )
            setup.append(f"{reg}={'|'.join(defs)}")
        use = "tail call" if kind == "tail" else _use_after_call(ctx, caller, site, fpr=False)
        fuse = "" if kind == "tail" or not sets_f0 else _use_after_call(ctx, caller, site, fpr=True)
        lines.append(
            f"  0x{site:x} in {ctx.label(caller)}: {'; '.join(setup)} || v0: {use}"
            + (f" || f0: {fuse}" if fuse else "")
        )
    if len(sites) > caller_limit:
        lines.append(f"  ... {len(sites) - caller_limit} more (use --callers {len(sites)})")
    return "\n".join(lines)


def function_asm(ctx: _Context, start: int) -> str:
    if start not in ctx.size:
        return f"0x{start:x}: not a sized FUNC symbol"
    end = start + ctx.size[start]
    lines = [f"## 0x{start:x} {ctx.label(start)} [{end - start} bytes]"]
    for pc in range(start, end, 4):
        lines.append(f"{pc:x}: {ctx.text(pc)}")
    return "\n".join(lines)


@lru_cache(maxsize=2)
def _context_cached(key: tuple[str, int, int], root: str) -> _Context:
    return _Context(Path(root))


def context(root: Path) -> _Context:
    return _context_cached(file_key(root / "support" / "socom.elf"), str(root))


# -- live reads (read-only bridge GETs) ---------------------------------------


def live_signatures(addresses: list[int], bridge_url: str | None = None) -> str:
    """Live name and signature of each function, one line each."""

    from .batch_apply import _FUNCTION_LINE, _SIGNATURE_LINE
    from .ghidra import GhidraBridge

    bridge = GhidraBridge(bridge_url)
    lines = []
    for address in addresses:
        text = bridge.request("get_function_by_address", address=f"0x{address:x}")
        rows = text.splitlines() if isinstance(text, str) else []
        function = next((m for line in rows if (m := _FUNCTION_LINE.match(line))), None)
        signature = next((m for line in rows if (m := _SIGNATURE_LINE.match(line))), None)
        lines.append(
            f"0x{address:x} {function.group(1) if function else '<no live function>'} :: "
            f"{signature.group(1) if signature else '-'}"
        )
    return "\n".join(lines)


def type_matches(names: list[str], bridge_url: str | None = None) -> str:
    """For each type name: every live type of that name (ignoring case), with path and size."""

    from .ghidra import GhidraBridge, _type_index

    rows = _type_index(GhidraBridge(bridge_url, timeout=300.0))
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_name.setdefault(row["name"].casefold(), []).append(row)
    lines = []
    for name in names:
        base = name.strip().rstrip("*").strip()
        found = by_name.get(base.casefold(), [])
        verdict = "unique" if len(found) == 1 else ("missing" if not found else f"AMBIGUOUS x{len(found)}")
        lines.append(
            f"{name}: {verdict}" + ("" if not found else " - " + "; ".join(f"{r['path']} ({r['size']})" for r in found[:6]))
        )
    return "\n".join(lines)
