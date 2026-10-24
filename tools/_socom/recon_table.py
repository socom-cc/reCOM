"""Function-pointer table families: one return width for every entry of a dispatched table column.

Decision of 2026-10-24 ("Yes, with conflict check"): the entries of one
function-pointer table -- a data table of code addresses dispatched through
one call site, such as UICommandTable's handlers called by zAnimUIMenuTick --
share the column's declared function-pointer type.  The exit narrowing inside
one entry's own body (UINetCnfUninit's ``andi v0,v0,0xff`` before ``jr ra``)
therefore proves that return width for every entry, unless some entry
contradicts it: it returns a wider or unnarrowed non-constant value, a value
of the other sign extension, or reads argument registers or classes outside
the shared parameters.  Constant-only entries are consistent with any width
their constants fit.

The companion decision: a caller or dispatcher narrowing a result into its
own destination (zAnimUIMenuTick's ``andi v0,v0,0xff`` after the ``jalr``)
never proves a callee's return width, because Metrowerks narrows a byte or
halfword return inside the callee.  Dispatch sites are listed for the shared
call-site evidence only.

Everything here is derived from the immutable ELF: relocated table words,
symbols, DWARF 1 records and instruction decoding.
"""

from __future__ import annotations

import math
from typing import Any

from .batch_apply import _writes
from .mwdemangle import demangle, render_type
from .recon_facts import (
    ARG_GPRS,
    GPR,
    JR_RA,
    _is_switch,
    _SAVED_GPRS,
    _through_calls,
    _use_after_call,
    argument_reads,
    callee_preserves,
)
from .util import SocomError

# A value's extension: ("zext", bits) zero-extended, ("sext", bits) sign-extended.
WIDTH_NAMES = {("zext", 8): "uchar", ("sext", 8): "schar", ("zext", 16): "ushort", ("sext", 16): "short"}
# DWARF 1 fundamental types by return width; plain char (FT_char) is left out
# because its signedness is not settled for this compiler.
_FUND_WIDTH = {0x3: ("zext", 8), 0x5: ("sext", 16), 0x6: ("zext", 16)}
_FUND_WIDE = frozenset((0x8, 0x9, 0xB, 0xC, 0x8208, 0xA510))
_MAX_DEPTH = 6


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _s32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def _jump_target(pc: int, insn: int) -> int:
    return ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2)


# -- table layout -------------------------------------------------------------


def _resolve_table(ctx: Any, key: str) -> tuple[int, int, str]:
    """(start, size, name) of the sized OBJECT symbol named ``key`` or containing address ``key``."""

    if key.lower().startswith("0x"):
        address = int(key, 16)
        starts = [s for s in ctx.object_starts if s <= address]
        start = max(starts) if starts else None
        if start is None or address >= start + ctx.objects[start][0]:
            raise SocomError(f"{key}: not inside a sized OBJECT symbol")
        size, name = ctx.objects[start]
        return start, size, name
    matches = sorted({s.value for s in ctx.elf.symbols() if s.name == key and s.type_name == "OBJECT" and s.size})
    if not matches:
        raise SocomError(f"{key}: no sized OBJECT symbol has that name")
    if len(matches) > 1:
        raise SocomError(f"{key}: {len(matches)} objects have that name ({', '.join(f'0x{m:x}' for m in matches)}); pass an address")
    size, name = ctx.objects[matches[0]]
    return matches[0], size, name


def _words(ctx: Any, start: int, size: int) -> dict[int, tuple[str, int]]:
    """Offset -> ("fn", target) for a relocated code address, ("ref", target), or ("plain", value)."""

    rows = {}
    for offset in range(0, size - size % 4, 4):
        site = start + offset
        value = ctx.code.word(site)
        if site in ctx.reloc32:
            rows[offset] = ("fn" if value in ctx.size else "ref", value)
        else:
            rows[offset] = ("plain", value)
    return rows


def _pure(words: dict[int, tuple[str, int]], stride: int, slot: int) -> bool | None:
    """True: a function column (code addresses or null words); False: no code addresses; None: mixed."""

    kinds = {words[o][0] if words[o] != ("plain", 0) else "null" for o in words if o % stride == slot}
    if "fn" not in kinds:
        return False
    return True if kinds <= {"fn", "null"} else None


def _infer_stride(words: dict[int, tuple[str, int]], size: int) -> int | None:
    """The smallest row stride under which no column mixes code addresses with other words."""

    candidates = [s for s in range(4, size + 1, 4) if size % s == 0] or list(range(4, size + 1, 4))
    for stride in candidates:
        columns = [_pure(words, stride, slot) for slot in range(0, stride, 4)]
        if None not in columns and True in columns:
            return stride
    return None


# -- dispatch sites -----------------------------------------------------------


def _linear(ctx: Any, flow: Any, site: int, register: int, depth: int = 0) -> dict[Any, int] | None:
    """A register's value at ``site`` as {leaf: coefficient} over shifts, adds and copies, else None.

    A leaf is a definition that is none of those (``lbu a1,6(s1)``), or the
    set of definitions of a register merging at a loop head (a loop counter),
    so ``sll v0,a1,1; addu v0,v0,a1; sll a0,v0,2`` is {a1: 12}.
    """

    if register == 0:
        return {}
    defs = flow.defs(site, register)
    if depth > 12:
        return None
    if len(defs) != 1:
        return {("merge", register, tuple(sorted(map(str, defs)))): 1}
    (d,) = defs
    if not isinstance(d, int):
        return {("entry", register): 1}
    insn = ctx.code.word(d)
    op, rs, rt, funct, sa = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, insn & 0x3F, (insn >> 6) & 31
    if op == 0x00 and funct in (0x00, 0x38) and insn:  # sll / dsll
        inner = _linear(ctx, flow, d, rt, depth + 1)
        return None if inner is None else {leaf: coefficient << sa for leaf, coefficient in inner.items()}
    if op == 0x00 and funct in (0x21, 0x2D) and not sa:  # addu / daddu (and copies)
        left, right = _linear(ctx, flow, d, rs, depth + 1), _linear(ctx, flow, d, rt, depth + 1)
        if left is None or right is None:
            return None
        merged = dict(left)
        for leaf, coefficient in right.items():
            merged[leaf] = merged.get(leaf, 0) + coefficient
        return merged
    if op == 0x00 and funct == 0x25 and not sa and 0 in (rs, rt):  # or copy
        return _linear(ctx, flow, d, rs or rt, depth + 1)
    return {("def", d): 1}


def _address(ctx: Any, flow: Any, site: int, register: int, start: int, size: int,
             depth: int = 0) -> tuple[set[int], list[Any]] | None:
    """(table offsets, index terms) a register holds at ``site``; None unless every definition is a table address.

    An index term is the linear form (see ``_linear``) of a register added to
    the table address, or None when it could not be traced.
    """

    if depth > 8 or register == 0:
        return None
    offsets: set[int] = set()
    terms: list[Any] = []
    for d in flow.defs(site, register):
        if not isinstance(d, int):
            return None
        insn = ctx.code.word(d)
        op, rs, rt, funct = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, insn & 0x3F
        ref = ctx.ref_at.get(d)
        if ref and ref.get("target") is not None and op in (0x09, 0x19, 0x0D):
            target = int(ref["target"], 16)
            if not start <= target < start + size:
                return None
            offsets.add(target - start)
        elif op == 0x00 and funct in (0x21, 0x2D, 0x25) and not (insn >> 6) & 0x1F:
            left = _address(ctx, flow, d, rs, start, size, depth + 1)
            right = _address(ctx, flow, d, rt, start, size, depth + 1)
            if (left is None) == (right is None):
                return None  # neither operand is a table address, or both are
            table, other = (left, rt) if left is not None else (right, rs)
            offsets |= table[0]
            terms.extend(table[1])
            if other:
                terms.append(_linear(ctx, flow, d, other))
        elif op in (0x09, 0x19) and rs:
            inner = _address(ctx, flow, d, rs, start, size, depth + 1)
            if inner is None:
                return None
            offsets |= {offset + _s16(insn & 0xFFFF) for offset in inner[0]}
            terms.extend(inner[1])
        else:
            return None
    return (offsets, terms) if offsets else None


def _dispatch_sites(ctx: Any, start: int, size: int) -> list[dict[str, Any]]:
    """Indirect calls whose target is loaded from the table.

    Each site has the table offsets it loads from (``columns``), whether a
    variable index is added to the table address (``indexed``: an array
    dispatch, not one constant slot of a struct of function pointers) and the
    index's scale in bytes when every index term is traced (``scale``).
    """

    owners = sorted({
        owner for row in ctx.refs
        if row["target"] is not None and start <= int(row["target"], 16) < start + size
        and (owner := ctx.owner(int(row["site"], 16))) is not None
    })
    sites = []
    for owner in owners:
        flow = ctx.flow(owner)
        for pc in range(owner, flow.end, 4):
            insn = ctx.code.word(pc)
            if not flow.reachable(pc) or insn >> 26 != 0x00 or insn & 0x3F != 0x09:
                continue
            register = (insn >> 21) & 31
            columns: set[int] = set()
            terms: list[Any] = []
            complete = True
            for d in flow.defs(pc, register):
                load = ctx.code.word(d) if isinstance(d, int) else 0
                if not isinstance(d, int) or load >> 26 != 0x23 or (load >> 16) & 31 != register:
                    complete = False
                    continue
                ref = ctx.ref_at.get(d)
                if ref and ref.get("target") is not None:
                    target = int(ref["target"], 16)
                    if start <= target < start + size:
                        columns.add(target - start)  # a constant slot: lw t9,%lo(table+k)(at)
                    else:
                        complete = False
                    continue
                found = _address(ctx, flow, d, (load >> 21) & 31, start, size)
                if found is None:
                    complete = False
                    continue
                columns |= {offset + _s16(load & 0xFFFF) for offset in found[0]}
                terms.extend(found[1])
            if not columns:
                continue
            indexed = any(term is None or any(term.values()) for term in terms)
            coefficients = [c for term in terms if term for c in term.values() if c]
            scale = None
            if indexed and None not in terms and coefficients:
                scale = 0
                for coefficient in coefficients:
                    scale = math.gcd(scale, abs(coefficient))
            sites.append({"owner": owner, "site": pc, "columns": sorted(columns), "complete": complete,
                          "indexed": indexed, "scale": scale})
    return sites


# -- exit values --------------------------------------------------------------


def _value(kind: str, ext: str | None = None, bits: int | None = None, *, site: int | None = None, text: str = "",
           value: int | None = None) -> dict[str, Any]:
    return {"kind": kind, "ext": ext, "bits": bits, "value": value, "site": site, "text": text,
            "own": True, "direct": True, "via": []}


def _bit_length(mask: int) -> int:
    return max(1, mask.bit_length())


def _fits(value: dict[str, Any], width: tuple[str, int]) -> bool:
    """A value is one the return width can hold without further narrowing."""

    ext, bits = width
    if value["kind"] == "const":
        number = value["value"]
        return 0 <= number < (1 << bits) if ext == "zext" else -(1 << (bits - 1)) <= number < (1 << (bits - 1))
    if value["ext"] is None:
        return False
    if value["ext"] == "zext":
        return value["bits"] <= bits if ext == "zext" else value["bits"] < bits
    return ext == "sext" and value["bits"] <= bits


class _Values:
    """Classifies what v0 holds at a function's exits, following copies and callees."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self._dwarf: dict[int, Any] | None = None
        self._callees: dict[int, list[dict[str, Any]]] = {}

    def dwarf_return(self, function: int) -> Any:
        """The width a function's DWARF record declares: (ext, bits), "wide", "void", "other" or None."""

        if self._dwarf is None:
            from pathlib import Path

            from .recon_facts import _dies_cached

            found: dict[int, set[Any]] = {}
            path = getattr(self.ctx.elf, "path", None)
            if path is not None:
                st = Path(path).stat()
                for die in _dies_cached((str(path), st.st_size, int(st.st_mtime)), str(path)):
                    if die.tag_name not in ("global_subroutine", "subroutine", "member_function"):
                        continue
                    low = die.integer("low_pc")
                    if not low:
                        continue
                    fund = die.integer("fund_type")
                    if fund in _FUND_WIDTH:
                        kind: Any = _FUND_WIDTH[fund]
                    elif fund in _FUND_WIDE:
                        kind = "wide"
                    elif fund == 0x14:
                        kind = "void"
                    elif fund is None and (die.attribute("mod_fund_type") or die.attribute("mod_u_d_type")):
                        kind = "wide"  # a pointer or reference
                    else:
                        kind = "other"
                    found.setdefault(low, set()).add(kind)
            self._dwarf = {low: next(iter(kinds)) if len(kinds) == 1 else "other" for low, kinds in found.items()}
        return self._dwarf.get(function)

    def exits(self, start: int, depth: int = 0, chain: frozenset[int] = frozenset()) -> tuple[int, list[dict[str, Any]]]:
        """(number of exits, the values v0 can hold at them)."""

        ctx = self.ctx
        flow = ctx.flow(start)
        chain = chain | {start}
        exits = 0
        values: list[dict[str, Any]] = []
        for pc in range(start, flow.end, 4):
            if not flow.reachable(pc):
                continue
            insn = ctx.code.word(pc)
            if insn == JR_RA:
                exits += 1
                for d in sorted(_through_calls(ctx, flow, flow.after(pc + 4, 2), 2, False), key=str):
                    values.extend(self.classify(flow, d, 2, depth, chain, True))
            elif insn >> 26 == 0x02:
                target = _jump_target(pc, insn)
                if start <= target < flow.end:
                    continue
                exits += 1
                how = callee_preserves(ctx, target, 2, False)
                if how != "all":
                    values.extend(self.callee(target, depth, chain))
                if how != "none":
                    for d in sorted(_through_calls(ctx, flow, flow.after(pc + 4, 2), 2, False), key=str):
                        values.extend(self.classify(flow, d, 2, depth, chain, True))
            elif insn >> 26 == 0x00 and insn & 0x3F == 0x08:
                if _is_switch(ctx, flow, start, pc):
                    continue
                exits += 1
                values.append(_value("unknown", site=pc, text=f"{ctx.text(pc)}@0x{pc:x}: an indirect tail call's result"))
        unique: dict[str, dict[str, Any]] = {}
        for value in values:
            unique.setdefault(repr(sorted(value.items())), value)
        return exits, sorted(unique.values(), key=lambda v: (v["site"] or 0, v["kind"], repr(v["via"])))

    def callee(self, target: int, depth: int, chain: frozenset[int]) -> list[dict[str, Any]]:
        """What a callee's result can be, marked as not the caller's own value."""

        ctx = self.ctx
        label = ctx.label(target)
        declared = self.dwarf_return(target)
        if isinstance(declared, tuple):
            inner = [_value("typed", declared[0], declared[1], site=target,
                            text=f"DWARF declares {WIDTH_NAMES.get(declared, declared)}")]
        elif declared == "wide":
            inner = [_value("wide", site=target, text="DWARF declares a 32-bit or wider return")]
        elif declared in ("void", "other"):
            inner = [_value("unknown", site=target, text=f"DWARF declares a {declared} return")]
        elif target in chain:
            return []  # recursion: the same values again
        elif target not in ctx.size or depth >= _MAX_DEPTH:
            inner = [_value("unknown", site=target, text="callee not followed")]
        else:
            if target not in self._callees:
                # Memoized on first use; entries are visited in table order, so this is deterministic.
                self._callees[target] = self.exits(target, depth + 1, chain)[1]
            inner = self._callees[target]
        out = []
        for value in inner:
            value = dict(value)
            value.update(own=False, direct=False, via=[label] + list(value["via"]))
            out.append(value)
        return out

    def classify(self, flow: Any, d: Any, register: int, depth: int, chain: frozenset[int], direct: bool,
                 seen: frozenset[tuple[int, int]] = frozenset()) -> list[dict[str, Any]]:
        """The values one definition of ``register`` can produce."""

        ctx = self.ctx
        if d == "entry":
            if register == 2:
                return [_value("unset", text="v0 is not written on this path")]
            return [_value("wide", text=f"the entry value of {GPR[register]} (an argument passed back)")]
        if not isinstance(d, int) or (d, register) in seen or len(seen) > 32:
            return [_value("unknown", text="definition not followed")]
        seen = seen | {(d, register)}
        insn = ctx.code.word(d)
        text = f"{ctx.text(d)}@0x{d:x}"
        previous = flow.fn.decoded.get(d - 4, {})
        if d != flow.start and previous.get("kind") in ("call", "call-branch") and not (
            register in _SAVED_GPRS and register in _writes(insn)[0]
        ):
            call = ctx.code.word(d - 4)
            if register == 2 and call >> 26 == 0x03:
                return self.callee(_jump_target(d - 4, call), depth, chain)
            what = "the result of" if register == 2 else "clobbered by"
            return [_value("unknown", site=d - 4, text=f"{what} {ctx.text(d - 4)}@0x{d - 4:x}")]
        op, rs, rt, rd = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, (insn >> 11) & 31
        funct, sa, imm = insn & 0x3F, (insn >> 6) & 31, insn & 0xFFFF

        def source(reg: int, mark_copy: bool = True) -> list[dict[str, Any]]:
            if reg == 0:
                return [_value("const", site=d, text=text, value=0)]
            out = []
            for inner in sorted(_through_calls(ctx, flow, flow.defs(d, reg), reg, False), key=str):
                for value in self.classify(flow, inner, reg, depth, chain, direct and not mark_copy, seen):
                    if mark_copy:
                        value = dict(value, direct=False)
                    out.append(value)
            return out

        def unsigned_bits(values: list[dict[str, Any]]) -> int | None:
            widths = []
            for value in values:
                if value["kind"] == "const":
                    if value["value"] < 0:
                        return None
                    widths.append(_bit_length(value["value"]))
                elif value["ext"] == "zext":
                    widths.append(value["bits"])
                else:
                    return None
            return max(widths) if widths else None

        if op in (0x09, 0x19) and rs == 0:
            return [_value("const", site=d, text=text, value=_s16(imm))]
        if op == 0x0D and rs == 0:
            return [_value("const", site=d, text=text, value=imm)]
        if op == 0x0F:
            return [_value("const", site=d, text=text, value=_s32(imm << 16))]
        if op in (0x0A, 0x0B):
            return [_value("compare", "zext", 1, site=d, text=text)]
        if op == 0x0C:
            if imm in (0xFF, 0xFFFF):
                return [_value("narrow", "zext", 8 if imm == 0xFF else 16, site=d, text=text) | {"direct": direct}]
            if imm == 0:
                return [_value("const", site=d, text=text, value=0)]
            return [_value("masked", "zext", _bit_length(imm), site=d, text=text)]
        if op in (0x0D, 0x0E):  # ori / xori of a bounded unsigned value stays bounded
            bits = unsigned_bits(source(rs))
            if bits is not None:
                return [_value("compare" if max(bits, _bit_length(imm)) == 1 else "masked", "zext",
                               max(bits, _bit_length(imm)), site=d, text=text)]
            return [_value("wide", site=d, text=text)]
        if op == 0x24:
            return [_value("load", "zext", 8, site=d, text=text)]
        if op == 0x20:
            return [_value("load", "sext", 8, site=d, text=text)]
        if op == 0x25:
            return [_value("load", "zext", 16, site=d, text=text)]
        if op == 0x21:
            return [_value("load", "sext", 16, site=d, text=text)]
        if op == 0x00:
            if funct in (0x21, 0x25, 0x2D) and not sa and 0 in (rs, rt):
                if rs == rt == 0:
                    return [_value("const", site=d, text=text, value=0)]
                return source(rs or rt)  # a plain copy
            if funct in (0x2A, 0x2B):
                return [_value("compare", "zext", 1, site=d, text=text)]
            if funct in (0x0A, 0x0B):  # movz/movn: the selected value or the one kept
                kept = []
                for inner in sorted(_through_calls(ctx, flow, flow.defs(d, rd), rd, False), key=str):
                    kept.extend(dict(v, direct=False) for v in self.classify(flow, inner, rd, depth, chain, False, seen))
                return source(rs) + kept
            if funct == 0x03 and sa in (16, 24):
                shifted = [x for x in flow.defs(d, rt)]
                paired = shifted and all(
                    isinstance(x, int) and ctx.code.word(x) >> 26 == 0 and ctx.code.word(x) & 0x3F == 0x00
                    and (ctx.code.word(x) >> 6) & 31 == sa for x in shifted
                )
                kind = "narrow" if paired else "shift"
                return [_value(kind, "sext", 32 - sa, site=d, text=text) | {"direct": direct and paired}]
            if funct == 0x02 and sa:
                return [_value("shift", "zext", 32 - sa, site=d, text=text)]
            if funct == 0x24:  # and: bounded by either bounded operand
                bounds = [b for b in (unsigned_bits(source(rs)), unsigned_bits(source(rt))) if b is not None]
                if bounds:
                    return [_value("masked", "zext", min(bounds), site=d, text=text)]
            if funct in (0x25, 0x26):  # or / xor of two bounded operands
                left, right = unsigned_bits(source(rs)), unsigned_bits(source(rt))
                if left is not None and right is not None:
                    bits = max(left, right)
                    return [_value("compare" if bits == 1 else "masked", "zext", bits, site=d, text=text)]
        return [_value("wide", site=d, text=text)]


def _describe(value: dict[str, Any]) -> str:
    kind = value["kind"]
    width = WIDTH_NAMES.get((value["ext"], value["bits"])) if value["ext"] else None
    if kind == "const":
        head = f"constant {value['value']}"
    elif kind == "compare":
        head = "0/1 compare result"
    elif kind == "narrow":
        head = "narrowing to " + (width or f"{value['ext']}{value['bits']}")
    elif kind == "load":
        head = f"{width} load"
    elif kind == "typed":
        head = f"typed {width}"
    elif kind in ("masked", "shift"):
        head = f"{kind} to {value['bits']} bits ({value['ext']})"
    elif kind == "unset":
        head = "no value"
    elif kind == "wide":
        head = "unnarrowed 32-bit value"
    else:
        head = "unknown value"
    where = f" ({value['text']})" if value["text"] else ""
    via = f" via {' -> '.join(value['via'])}" if value["via"] else ""
    return head + where + via


def _width_text(ext: str, bits: int) -> str:
    name = WIDTH_NAMES.get((ext, bits), f"{bits} bits")
    return f"{name}, {'zero' if ext == 'zext' else 'sign'}-extended"


def _entry_class(exits: int, values: list[dict[str, Any]]) -> str:
    """One label: own narrowing (width and sign), constant-only, 0/1 compare, typed callee/member, unnarrowed."""

    if not exits:
        return "never returns"
    kinds = {v["kind"] for v in values}
    if "unset" in kinds:
        return "no value at some exit (v0 unset)"
    if kinds & {"wide", "unknown"}:
        return "unnarrowed or unknown value"
    own = [v for v in values if v["own"] and v["kind"] == "narrow"]
    if any(v["direct"] for v in own):
        w = next(v for v in own if v["direct"])
        return f"own narrowing at the exit ({_width_text(w['ext'], w['bits'])})"
    if own:
        return f"own narrowing of a returned local ({_width_text(own[0]['ext'], own[0]['bits'])})"
    if all(v["own"] for v in values) and kinds == {"const"}:
        return "constant-only (" + ", ".join(str(n) for n in sorted({v["value"] for v in values})) + ")"
    if all(v["own"] for v in values) and kinds <= {"const", "compare"}:
        return "0/1 compare or constant"
    return "typed callee/member value"


# -- the family ---------------------------------------------------------------


def _thunk_target(ctx: Any, function: int) -> int | None:
    """Target of an 8-byte `j target` (or `b target`) with a nop delay slot: a Ghidra thunk."""

    if ctx.size.get(function) != 8 or ctx.code.word(function + 4) != 0:
        return None
    insn = ctx.code.word(function)
    if insn >> 26 == 0x02:
        target = _jump_target(function, insn)
    elif insn >> 26 == 0x04 and (insn >> 16) & 0x3FF == 0:
        target = function + 4 + (_s16(insn & 0xFFFF) << 2)
    else:
        return None
    return target if target in ctx.size else None


def _mangled_params(names: dict[int, list[str]], function: int) -> tuple[list[dict[str, Any]] | None, str | None]:
    """The demangled parameter list of a function's mangled name, and its rendering."""

    for name in names.get(function, ()):
        parsed = demangle(name)
        if parsed and parsed.get("params") is not None:
            params = list(parsed["params"])
            if params == [{"modifiers": [], "kind": "builtin", "name": "void"}]:
                params = []
            return params, ", ".join(render_type(p) for p in params)
    return None, None


def _register_order(name: str) -> tuple[int, int]:
    return (1, int(name[1:])) if name.startswith("f") and name[1:].isdigit() else (0, GPR.index(name))


def table_family(ctx: Any, key: str, column: int | None = None, stride: int | None = None) -> dict[str, Any]:
    """The table-family return-width verdict for one function-pointer column of a data table."""

    from .type_layout import parameter_registers

    start, size, name = _resolve_table(ctx, key)
    words = _words(ctx, start, size)
    sites = _dispatch_sites(ctx, start, size)
    indexed = [site for site in sites if site["indexed"]]
    scales = sorted({site["scale"] for site in indexed if site["scale"]})
    if stride is None:
        if len(scales) == 1 and scales[0] % 4 == 0:
            stride, stride_source = scales[0], "the dispatch index scale"
        else:
            stride, stride_source = _infer_stride(words, size), "the smallest stride keeping code addresses apart"
            if stride is None:
                raise SocomError(f"{name}: no row stride keeps code addresses apart from other words; pass --stride")
    elif stride <= 0 or stride % 4:
        raise SocomError("--stride must be a positive multiple of 4")
    else:
        stride_source = "--stride"
    function_columns = [slot for slot in range(0, stride, 4) if _pure(words, stride, slot)]
    dispatched = sorted({c % stride for site in indexed for c in site["columns"]})
    if column is not None:
        column %= stride
    elif len(set(dispatched) & set(function_columns)) == 1:
        column = (set(dispatched) & set(function_columns)).pop()
    elif not dispatched and len(function_columns) == 1:
        column = function_columns[0]
    else:
        raise SocomError(
            f"{name}: give --column: function columns {[f'+0x{c:x}' for c in function_columns]}, "
            f"dispatched columns {[f'+0x{c:x}' for c in dispatched]} (stride {stride})"
        )
    purity = _pure(words, stride, column)
    if purity is None:
        raise SocomError(f"{name}: column +0x{column:x} mixes code addresses with other words (stride {stride})")
    if not purity:
        raise SocomError(f"{name}: column +0x{column:x} holds no code addresses (stride {stride})")
    column_sites = [site for site in sites if any(c % stride == column for c in site["columns"])]
    scale_problems = sorted({
        site["scale"] for site in column_sites if site["indexed"] and site["scale"] and site["scale"] % stride
    })

    values = _Values(ctx)
    names = {row["start"]: row["names"] for row in ctx.functions}
    entries: dict[int, dict[str, Any]] = {}
    nulls = 0
    for offset in sorted(o for o in words if o % stride == column):
        kind, target = words[offset]
        if kind != "fn":
            nulls += 1
            continue
        if target in entries:
            entries[target]["slots"].append(offset)
            continue
        body, hops = target, []
        while (inner := _thunk_target(ctx, body)) is not None and len(hops) < 4:
            hops.append(inner)
            body = inner
        exits, found = values.exits(body)
        params, rendered = _mangled_params(names, target)
        body_params, body_rendered = _mangled_params(names, body) if body != target else (params, rendered)
        entries[target] = {
            "address": target, "label": ctx.label(target), "slots": [offset],
            "thunk_target": body if hops else None, "body": body,
            "exits": exits, "values": found,
            # The planners' contract: argument registers read before written on some path.
            "reads": sorted(argument_reads(ctx, body), key=_register_order),
            "params": rendered, "body_params": body_rendered if body != target else None,
            "_params": params if params is not None else body_params,
            "declared": values.dwarf_return(body),
            "other_tables": sorted({
                (ctx.object_for(site) or f"0x{site:x}").split("+")[0]
                for site in ctx.word32.get(target, ()) if not start <= site < start + size
            }),
        }

    # The shared parameters: the most common mangled parameter list.
    counted: dict[str, int] = {}
    for entry in entries.values():
        for text in {entry["params"], entry["body_params"]} - {None}:
            counted[text] = counted.get(text, 0) + 1
    contract_text = max(sorted(counted), key=lambda text: counted[text]) if counted else None
    contract_registers: list[str] | None = None
    contract_complete = False
    if contract_text is not None:
        params = next(e["_params"] for e in entries.values() if contract_text in (e["params"], e["body_params"]))
        mapped, contract_complete = parameter_registers(params, False)
        contract_registers = [register for register, _value in mapped]

    witnesses = []
    for entry in entries.values():
        declared = entry["declared"]
        if isinstance(declared, tuple):
            witnesses.append({"entry": entry["address"], "width": declared, "site": entry["body"],
                              "evidence": f"its DWARF record declares {WIDTH_NAMES.get(declared)}"})
        for value in entry["values"]:
            if value["own"] and value["direct"] and value["kind"] == "narrow":
                witnesses.append({"entry": entry["address"], "width": (value["ext"], value["bits"]),
                                  "site": value["site"], "evidence": f"narrows its own exit ({value['text']})"})
    widths = sorted({tuple(w["width"]) for w in witnesses})
    width = widths[0] if len(widths) == 1 else None

    conflicts = []
    for entry in entries.values():
        problems = []
        declared = entry["declared"]
        if declared in ("wide", "void", "other"):
            problems.append(f"its DWARF record declares a {declared} return")
        elif isinstance(declared, tuple) and width and declared != width:
            problems.append(f"its DWARF record declares {WIDTH_NAMES.get(declared)}")
        if width:
            for value in entry["values"]:
                if not _fits(value, width):
                    problems.append(_describe(value))
        elif entry["exits"] and any(v["kind"] in ("unset", "wide", "unknown") for v in entry["values"]):
            problems.extend(_describe(v) for v in entry["values"] if v["kind"] in ("unset", "wide", "unknown"))
        if contract_text is not None:
            for text in {entry["params"], entry["body_params"]} - {None}:
                if text != contract_text:
                    problems.append(f"mangled parameters ({text}) differ from the family's ({contract_text})")
            extra = [r for r in entry["reads"] if r not in (contract_registers or [])]
            if extra:
                problems.append(
                    "reads " + ", ".join(extra) + " beyond the shared parameters ("
                    + (", ".join(contract_registers or []) or "none") + ")"
                    + ("" if contract_complete else "; the mangled parameters do not settle every register")
                )
        entry["class"] = _entry_class(entry["exits"], entry["values"])
        entry["problems"] = problems[:4] + ([f"{len(problems) - 4} more"] if len(problems) > 4 else [])
        if problems:
            conflicts.append(entry["address"])

    reasons = []
    if not any(site["indexed"] for site in column_sites):
        reasons.append(
            "no indexed call loads its target from this column (an array dispatch, not one constant slot), "
            "so the shared call site is unproven"
        )
    if scale_problems:
        reasons.append(
            f"a dispatch index scale ({', '.join(map(str, scale_problems))}) is not a multiple of the stride ({stride})"
        )
    if contract_text is None:
        reasons.append("no entry has a mangled signature, so the shared argument registers are unproven")
    if not witnesses:
        reasons.append("no entry narrows its own exit (or has a DWARF-declared width)")
    elif len(widths) > 1:
        reasons.append("the witnesses prove different widths: " + ", ".join(WIDTH_NAMES.get(w, str(w)) for w in widths))
    if conflicts:
        reasons.append(f"{len(conflicts)} conflicting entries")
    verdict = {
        "width": WIDTH_NAMES.get(width) if width and not reasons else None,
        "ext": width[0] if width and not reasons else None,
        "bits": width[1] if width and not reasons else None,
        "witnesses": [
            {"entry": f"0x{w['entry']:x}", "label": ctx.label(w["entry"]), "width": WIDTH_NAMES.get(tuple(w["width"])),
             "evidence": w["evidence"]}
            for w in witnesses
        ],
        "conflicts": [f"0x{address:x}" for address in conflicts],
        "open_reasons": reasons,
    }
    dispatch = []
    for site in column_sites:
        flow = ctx.flow(site["owner"])
        setup = []
        for register in contract_registers or [GPR[r] for r in ARG_GPRS[:4]]:
            fpr = register.startswith("f") and register[1:].isdigit()
            index = int(register[1:]) if fpr else GPR.index(register)
            defs = sorted(
                f"{ctx.text(d)}@0x{d:x}" if isinstance(d, int) else str(d)
                for d in flow.entering_callee(site["site"] + 4, index, fpr)
            )
            setup.append(f"{register}={'|'.join(defs)}")
        dispatch.append({
            "owner": ctx.label(site["owner"]), "site": f"0x{site['site']:x}",
            "columns": [f"+0x{c:x}" for c in site["columns"]], "complete": site["complete"],
            "indexed": site["indexed"], "scale": site["scale"],
            "arguments": setup, "v0_use": _use_after_call(ctx, site["owner"], site["site"], fpr=False),
        })
    rows = []
    for entry in sorted(entries.values(), key=lambda e: e["slots"][0]):
        rows.append({
            "address": f"0x{entry['address']:x}", "label": entry["label"],
            "slots": [f"+0x{s:x}" for s in entry["slots"]],
            "thunk_target": ctx.label(entry["thunk_target"]) if entry["thunk_target"] else None,
            "class": entry["class"], "exits": entry["exits"],
            "values": [_describe(v) for v in entry["values"]],
            "reads": entry["reads"], "params": entry["params"], "other_tables": entry["other_tables"],
            "problems": entry["problems"],
        })
    return {
        "table": {"name": name, "address": f"0x{start:x}", "size": size},
        "stride": stride, "stride_source": stride_source, "column": f"+0x{column:x}",
        "function_columns": [f"+0x{c:x}" for c in function_columns],
        "null_slots": nulls,
        "dispatch_sites": dispatch,
        "contract": {
            "params": contract_text, "registers": contract_registers, "complete": contract_complete,
            "entries_with_it": counted.get(contract_text, 0) if contract_text else 0,
        },
        "entries": rows,
        "verdict": verdict,
    }


def table_family_text(result: dict[str, Any]) -> str:
    """Short text for `recon table-family`."""

    table = result["table"]
    contract = result["contract"]
    verdict = result["verdict"]
    lines = [
        f"## {table['name']}@{table['address']} [{table['size']} bytes]: column {result['column']} of "
        f"{result['stride']}-byte rows (stride from {result['stride_source']}), {len(result['entries'])} entries, "
        f"{result['null_slots']} null slots"
        + (f"; other function columns {', '.join(c for c in result['function_columns'] if c != result['column'])}"
           if len(result["function_columns"]) > 1 else "")
    ]
    for site in result["dispatch_sites"]:
        shape = (
            (f"indexed, scale {site['scale']}" if site["scale"] else "indexed, scale not traced")
            if site["indexed"] else "one constant slot: not an array dispatch"
        )
        lines.append(
            f"dispatch {site['site']} in {site['owner']} (column {', '.join(site['columns'])}; {shape}"
            f"{'' if site['complete'] else '; not every target definition is a table load'}): "
            f"{'; '.join(site['arguments'])} || v0: {site['v0_use']} "
            "(the dispatcher's own destination width; Metrowerks narrows inside the callee, so this proves nothing)"
        )
    if not result["dispatch_sites"]:
        lines.append("dispatch: no indirect call loads its target from this column")
    if contract["params"] is not None:
        lines.append(
            f"shared parameters: ({contract['params']}) -> {', '.join(contract['registers'] or []) or 'none'} "
            f"({contract['entries_with_it']} entries' mangled names)"
            + ("" if contract["complete"] else "; not every register is settled")
        )
    for entry in result["entries"]:
        head = f"  {entry['slots'][0]} {entry['label']}"
        if entry["thunk_target"]:
            head += f" -> thunk of {entry['thunk_target']}"
        text = f"{head}: {entry['class']}"
        shown = [v for v in entry["values"] if not v.startswith("constant ")][:2]
        if shown:
            text += "; " + "; ".join(shown)
        text += f"; reads {', '.join(entry['reads']) or 'none'}"
        if entry["other_tables"]:
            text += f"; also stored in {', '.join(entry['other_tables'])}"
        if entry["problems"]:
            text += " || CONFLICT: " + "; ".join(entry["problems"])
        lines.append(text)
    for witness in verdict["witnesses"][:4]:
        lines.append(f"witness {witness['label']}: {witness['evidence']}")
    if verdict["width"]:
        lines.append(
            f"VERDICT {verdict['width']}: every entry of the column returns {verdict['width']} "
            f"({len(verdict['witnesses'])} witnesses; no entry contradicts it; table-family rule, decision of 2026-10-24)"
        )
    else:
        lines.append("VERDICT open: " + "; ".join(verdict["open_reasons"])
                     + (f" ({', '.join(verdict['conflicts'][:12])}{' ...' if len(verdict['conflicts']) > 12 else ''})"
                        if verdict["conflicts"] else ""))
    return "\n".join(lines)
