"""Code-derived class layout evidence for classes without a DWARF record.

Stage 3 sets prototypes with types that already exist in Ghidra.  A class the
DWARF import never saw (``zdb::CVisual`` has member functions, a vtable and
RTTI but no ``class_type`` record) leaves its functions unresolved.  This
module gathers, from the immutable ELF only, the facts a reviewed type plan
needs:

* member functions by mangled qualifier, with the proof that a0 is ``this``
  (constructor/destructor, const method, vtable slot, or an argument register
  read beyond what a static function with the same parameters would take);
* the vtable's slots and RTTI, and the RTTI base list (Metrowerks
  ``type_info_base_list``: base type_info pointer and offset, null-terminated);
* allocation sites (``operator new(N)`` whose result reaches a constructor;
  the class is the most derived of that constructor's class and any family
  vtable the same function stores into the object, so an inlined derived
  constructor is not mistaken for its base);
* derived classes (their RTTI lists this class) and the this-adjustment their
  constructors pass to the base constructor;
* every access relative to a pointer proven to be the class: ``this`` in
  members, typed (mangled) pointer/reference parameters, allocation results,
  and pointers held outside the family (below).  Values are followed through
  register copies, stack spills and reloads, constant offsets, loads (a
  loaded value used as a base is a dereferenced pointer; an index added to it
  is an indexed dereference), and calls (an argument register holding the
  pointer or a loaded field is matched to the callee's mangled parameter
  type).  A loop pointer (one base at different constant offsets on joining
  paths) is that base plus an unknown index.

Holders (``_Holders``) prove class pointers stored outside the family, from
the ELF and DWARF only, every one with a cited proof:

* a 4-byte load of a DWARF member (bases and by-value members followed, all
  DWARF records of the holder class agreeing) or DWARF global whose type is a
  pointer to a class, from a pointer typed as that holder class (``this``, a
  mangled parameter, or another holder);
* an element of pointer storage whose DWARF type lost its element type (the
  ``__vector_pod`` ``data_`` of ``std::vector<T *>`` is ``unsigned int *``):
  the element class is proven when code passes that storage, plus an index,
  as a mangled ``T **`` (or ``T *&``) parameter, keyed by the innermost
  non-template DWARF record holding it (``CVisualVector+0x8``), with any
  disagreement refusing the key;
* a call result, when every exit of the callee returns NULL or a pointer of
  one proven class, or returns its entry a0 plus a constant (``data()``,
  constructors);
* a function-local static read back after the function stored a proven
  pointer in it, when the ELF references it only from that function's
  direct loads and stores.

A by-value parameter whose mangled name is a class but whose DWARF records
are only enumerations is a scalar in its register, so it settles the
registers after it.

Every call row says what the callee takes in its register: ``parameter_type``
(the mangled parameter, or the receiver), ``no_parameter`` (the parameter list
is settled and that register is not in it), or ``parameter_unknown`` with the
reason (an indirect call, a symbol without a mangled parameter list, registers
not settled past a by-value class or varargs, or an unproven receiver whose
static and member readings differ).  A member's receiver is proven by its
kind (constructor, destructor, const method, vtable slot, a member operator
other than new/delete, which C++ never makes static), a DWARF ``this`` formal
parameter, or an argument register read beyond a static function's
parameters.  DWARF parameter lists add no types: DWARF 1 lists only named
parameters, so it cannot settle registers, and all but nine DWARF
subprograms (main, thunks, C wrappers) have mangled names that list them.

Nothing is inferred from names or Ghidra: a site is listed only when the
instruction semantics prove its base.  Accesses whose base the analysis
cannot prove are counted per function as unattributed, so gaps stay visible.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from pathlib import Path
from typing import Any

from .batch_apply import OPERATORS, _reads, _writes
from .constants import REFERENCE_SHA256
from .mwdemangle import demangle, readable_qualified, render_type, split_qualified, template_base
from .recon_facts import GPR, _dies_cached, _fpr_writes, argument_reads, context
from .util import SocomError, file_key

LAYOUT_KIND = "socom-type-layout-evidence"
LAYOUT_SCHEMA = 2

# Memory opcodes: (width, kind, signed, store, fpr).  kind: int, float,
# int64, int128, vu (lqc2/sqc2 vector registers), partial (lwl/lwr/...).
_MEMORY = {
    0x20: (1, "int", True, False, False),  # lb
    0x24: (1, "int", False, False, False),  # lbu
    0x21: (2, "int", True, False, False),  # lh
    0x25: (2, "int", False, False, False),  # lhu
    0x23: (4, "int", None, False, False),  # lw (32-bit word; sign extension is the ISA's)
    0x27: (4, "int", False, False, False),  # lwu
    0x37: (8, "int64", None, False, False),  # ld
    0x1E: (16, "int128", None, False, False),  # lq
    0x31: (4, "float", None, False, True),  # lwc1
    0x36: (16, "vu", None, False, False),  # lqc2
    0x22: (4, "partial", None, False, False),  # lwl
    0x26: (4, "partial", None, False, False),  # lwr
    0x1A: (8, "partial", None, False, False),  # ldl
    0x1B: (8, "partial", None, False, False),  # ldr
    0x28: (1, "int", None, True, False),  # sb
    0x29: (2, "int", None, True, False),  # sh
    0x2B: (4, "int", None, True, False),  # sw
    0x3F: (8, "int64", None, True, False),  # sd
    0x1F: (16, "int128", None, True, False),  # sq
    0x39: (4, "float", None, True, True),  # swc1
    0x3E: (16, "vu", None, True, False),  # sqc2
    0x2A: (4, "partial", None, True, False),  # swl
    0x2E: (4, "partial", None, True, False),  # swr
    0x2C: (8, "partial", None, True, False),  # sdl
    0x2D: (8, "partial", None, True, False),  # sdr
}
_CALL_CLOBBERED_GPRS = (1, 2, 3, *range(4, 16), 24, 25, 31)
# Member operators are never static ([over.oper]); operator new/delete are.
_MEMBER_OPERATORS = frozenset(name for name in OPERATORS if name not in ("__nw", "__nwa", "__dl", "__dla"))
_SP = 29
_MAX_DEPTH = 3
_ALLOCATORS = ("__nw", "__nwa")
_SHIFTS = {
    0x00: ("sll", 0), 0x02: ("srl", 0), 0x03: ("sra", 0),
    0x38: ("dsll", 0), 0x3A: ("dsrl", 0), 0x3B: ("dsra", 0),
    0x3C: ("dsll", 32), 0x3E: ("dsrl", 32), 0x3F: ("dsra", 32),
}
# Kinds that say nothing about int versus float: a GPR store of constant
# zero (0.0f has the same bits) and a 4-byte move through an FPR that no
# float instruction reads (Metrowerks copies words with lwc1/swc1).
NEUTRAL_KINDS = frozenset({"zero", "fpr-copy", "partial"})


# -- abstract values -------------------------------------------------------
#
# A value is ``(term, k)`` (the term plus a constant byte offset) or None
# (unknown).  Terms: ("const",) with k the constant; ("sym",) with k a
# relocated address; ("sp",) the entry stack pointer; ("arg", r) / ("farg", r)
# an entry argument register; ("res", site) a call's v0; ("ld", address,
# width, kind, signed) a loaded value; ("ix", pointer) a pointer plus an
# unknown index; ("bits", source, ops) bit operations on a loaded value (kept
# only for bitfield evidence); ("hold", source, (shape, class)) a pointer a
# holder proves, where source is the ("ld", ...) term of a typed load (so
# the same load on two paths joins), ("elem", storage) for any element of a
# typed storage hold, or ("res", site) of a typed call result: shape "ptr"
# points to the class, "array" to storage of class pointers.

_ZERO = (("const",), 0)


def _const(value: int) -> tuple:
    return (("const",), value)


def _depth(value: Any) -> int:
    if value is None:
        return 0
    term = value[0]
    if term[0] in ("ld", "ix", "bits"):
        return 1 + _depth(term[1])
    return 0


def _add(value: Any, delta: Any) -> Any:
    """value + delta, where delta is an int or a value."""

    if value is None:
        return None
    if isinstance(delta, int):
        if value[0][0] == "bits":
            return None
        return (value[0], value[1] + delta)
    if delta is None:
        return None
    if delta[0] == ("const",):
        return _add(value, delta[1])
    if value[0] == ("const",):
        return _add(delta, value[1])
    return None


def _is_const(value: Any) -> bool:
    return value is not None and value[0] == ("const",)


def _pointer_candidate(value: Any) -> bool:
    return value is not None and value[0][0] in ("ld", "arg", "res", "ix", "hold")


def _index_base(value: Any) -> Any:
    """The pointer an indexed value starts from: an ix term's pointer, else the pointer value itself."""

    term = value[0]
    if term[0] == "ix":
        return term[1]
    if term[0] in ("ld", "arg", "res", "hold"):
        return value
    return None


def _widen(left: Any, right: Any) -> Any:
    """Join of two different values: one pointer at different offsets is that pointer plus an index."""

    if left is None or right is None:
        return None
    a, b = _index_base(left), _index_base(right)
    if a is None or b is None or a[0] != b[0]:
        return None
    return (("ix", (a[0], min(a[1], b[1]))), 0)


def _index(left: Any, right: Any) -> Any:
    """A pointer plus an unknown index (exactly one operand can be the pointer)."""

    candidates = [value for value in (left, right) if _pointer_candidate(value)]
    if len(candidates) != 1:
        return None
    pointer = candidates[0]
    if pointer[0][0] == "ix":
        return pointer
    return (("ix", pointer), 0)


def _bits(source: Any, op: str, operand: Any) -> Any:
    """Bit operation on a loaded value, or None."""

    if source is None:
        return None
    if source[0][0] == "ld" and source[1] == 0:
        base, ops = source, ()
    elif source[0][0] == "bits":
        base, ops = source[0][1], source[0][2]
    else:
        return None
    if len(ops) >= 6:
        return None
    return (("bits", base, ops + ((op, operand if isinstance(operand, int) else "?"),)), 0)


_MASK64 = (1 << 64) - 1


def _fold(op: str, a: int, b: int) -> int:
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    if op == "nor":
        return ~(a | b)
    if op == "sll":
        result = (a << b) & 0xFFFFFFFF
        return result - (1 << 32) if result & 0x80000000 else result
    if op == "srl":
        result = (a & 0xFFFFFFFF) >> b
        return result - (1 << 32) if result & 0x80000000 else result
    if op == "sra":
        low = a & 0xFFFFFFFF
        low = low - (1 << 32) if low & 0x80000000 else low
        return low >> b
    if op == "dsll":
        result = (a << b) & _MASK64
        return result - (1 << 64) if result >> 63 else result
    if op == "dsrl":
        return (a & _MASK64) >> b
    if op == "dsra":
        return a >> b
    raise ValueError(op)


def _logic(op: str, left: Any, right: Any) -> Any:
    if _is_const(left) and _is_const(right):
        return _const(_fold(op, left[1], right[1]))
    if op in ("and", "or", "xor"):
        for source, other in ((left, right), (right, left)):
            if source is not None and source[0][0] in ("ld", "bits"):
                return _bits(source, op, other[1] if _is_const(other) else None)
    return None


def source_bits(value: Any) -> int | None:
    """Bits of the loaded field that can reach a bit-operation result.

    Shifts move the window (logical and arithmetic right shifts alike) and a
    constant ``and`` narrows it; ``or``/``xor`` add bits that do not come from
    the field.  The answer is in the field's own bit positions.
    """

    if value is None:
        return None
    term = value[0]
    if term[0] == "ld":
        return (1 << (8 * term[2])) - 1
    if term[0] != "bits":
        return None
    width = term[1][0][2]
    mask, shift = (1 << (8 * width)) - 1, 0
    for op, arg in term[2]:
        if op in ("sll", "dsll") and isinstance(arg, int):
            limit = 0xFFFFFFFF if op == "sll" else _MASK64
            mask, shift = (mask << arg) & limit, shift + arg
        elif op in ("srl", "sra", "dsrl", "dsra") and isinstance(arg, int):
            mask, shift = mask >> arg, shift - arg
        elif op == "and" and isinstance(arg, int):
            mask &= arg & _MASK64
    result = mask >> shift if shift >= 0 else mask << -shift
    return result & ((1 << (8 * width)) - 1)


# -- class identity ---------------------------------------------------------


def mangled_qualifier(components: list[str]) -> str:
    """Metrowerks encoding of a qualified class name (no templates)."""

    for part in components:
        if not part or "<" in part:
            raise SocomError(f"cannot encode the qualifier component {part!r}")
    encoded = "".join(f"{len(part)}{part}" for part in components)
    if len(components) == 1:
        return encoded
    if len(components) < 10:
        return f"Q{len(components)}{encoded}"
    return f"Q_{len(components)}_{encoded}"


def _qualified(components: Any) -> str:
    return readable_qualified(list(components))


def _levels(value: dict[str, Any]) -> list[str]:
    return [modifier for modifier in value.get("modifiers", []) if modifier in ("P", "R")]


def _pointee_class(value: dict[str, Any]) -> tuple[str, ...] | None:
    """The class a single-level pointer or reference parameter points to."""

    if value.get("kind") != "class" or len(_levels(value)) != 1:
        return None
    return tuple(value["components"])


def _by_value_aggregate(value: dict[str, Any]) -> bool:
    return value.get("kind") in ("class", "array", "member_pointer") and not _levels(value)


def _float_param(value: dict[str, Any]) -> bool:
    return value.get("kind") == "builtin" and value.get("name") == "float" and not _levels(value)


def parameter_registers(
    params: list[dict[str, Any]] | None, has_this: bool, scalars: frozenset[tuple[str, ...]] = frozenset()
) -> tuple[list[tuple[str, dict]], bool]:
    """(register, mangled type) per parameter under the EE convention.

    Floats take f12-f19 and everything else the next of a0-t3.  Mapping stops
    (complete=False) at a by-value class, an array, varargs, or when the
    registers run out, because those parameters' registers are not settled.
    ``scalars`` are mangled class names proven to be enumerations (DWARF),
    which take one GPR like any integer.
    """

    values = list(params or [])
    if values == [{"modifiers": [], "kind": "builtin", "name": "void"}]:
        values = []
    gpr, fpr = (1 if has_this else 0), 0
    rows: list[tuple[str, dict]] = []
    for value in values:
        if value.get("kind") == "builtin" and value.get("name") == "...":
            return rows, False
        if _by_value_aggregate(value) and not (value.get("kind") == "class" and tuple(value["components"]) in scalars):
            return rows, False
        if _float_param(value):
            if fpr >= 8:
                return rows, False
            rows.append((f"f{12 + fpr}", value))
            fpr += 1
        else:
            if gpr >= 8:
                return rows, False
            rows.append((GPR[4 + gpr], value))
            gpr += 1
    return rows, True


class _Symbols:
    """Function and object symbols with their demangled identities."""

    def __init__(self, ctx: Any, scalars: frozenset[tuple[str, ...]] = frozenset()) -> None:
        self.ctx = ctx
        self.scalars = scalars
        self.functions: dict[int, dict[str, Any]] = {}
        self.objects: list[dict[str, Any]] = []
        for symbol in ctx.elf.symbols():
            if not symbol.name:
                continue
            parsed = demangle(symbol.name)
            if symbol.type_name == "FUNC" and symbol.size:
                row = self.functions.setdefault(symbol.value, {"address": symbol.value, "size": symbol.size, "names": []})
                row["names"].append(symbol.name)
                if parsed and parsed.get("params") is not None and "parsed" not in row:
                    row["parsed"] = parsed
                    row["mangled"] = symbol.name
            elif symbol.type_name == "OBJECT":
                self.objects.append({"address": symbol.value, "size": symbol.size, "name": symbol.name, "parsed": parsed})
        for row in self.functions.values():
            row["names"].sort()
            row.setdefault("mangled", None)
            row.setdefault("parsed", None)
        self.objects.sort(key=lambda row: (row["address"], row["name"]))

    def parsed(self, address: int | None) -> dict[str, Any]:
        if address is None:
            return {}
        return (self.functions.get(address) or {}).get("parsed") or {}

    def readable(self, address: int | None) -> str:
        if address is None:
            return "indirect call"
        row = self.functions.get(address)
        if not row:
            return self.ctx.label(address)
        parsed = row.get("parsed")
        if not parsed:
            return row["names"][0] if row["names"] else f"0x{address:x}"
        qualifier = _qualified(parsed["qualifier"])
        params = parsed.get("params") or []
        rendered = ", ".join(render_type(value) for value in params)
        return f"{qualifier + '::' if qualifier else ''}{parsed['name']}({rendered}){' const' if parsed['const'] else ''}"


def _encoded(components: list[str]) -> str:
    try:
        return mangled_qualifier(list(components))
    except SocomError:
        return ""


def dwarf_subprograms(root: Path) -> dict[int, bool]:
    """Entry address of every DWARF subprogram -> whether its first formal parameter is ``this``.

    DWARF 1 omits unnamed (and some unused) parameters, so a missing ``this``
    proves nothing; a present one proves a non-static member.
    """

    from .type_plan_evidence import TypeEvidence

    dwarf = TypeEvidence(root).dwarf
    found: dict[int, bool] = {}
    for die in dwarf.dies:
        if die.tag_name not in ("subroutine", "global_subroutine") or not die.integer("low_pc"):
            continue
        first = next((child for child in dwarf.children(die) if child.tag_name == "formal_parameter"), None)
        found[die.integer("low_pc")] = found.get(die.integer("low_pc"), False) or (
            first is not None and first.string("name") == "this"
        )
    return found


class _Receivers:
    """Proof that a member function's a0 is ``this``."""

    def __init__(self, ctx: Any, symbols: _Symbols, dwarf: dict[int, bool] | None = None) -> None:
        self.ctx = ctx
        self.symbols = symbols
        self.dwarf = dwarf or {}
        self.vtable_slots: dict[int, list[str]] = defaultdict(list)
        for row in symbols.objects:
            if row["name"].startswith("__vt__") and row["size"]:
                for offset in range(0, row["size"], 4):
                    site = row["address"] + offset
                    if site in ctx.reloc32:
                        target = ctx.code.word(site)
                        if target in symbols.functions:
                            self.vtable_slots[target].append(f"{row['name']}+0x{offset:x}")
        self._cache: dict[int, str | None] = {}

    def proof(self, address: int | None) -> str | None:
        if address is None:
            return None
        if address in self._cache:
            return self._cache[address]
        parsed = self.symbols.parsed(address)
        result: str | None = None
        if parsed and parsed.get("qualifier"):
            own = f"__vt__{_encoded(parsed['qualifier'])}+"
            slots = sorted(self.vtable_slots.get(address, []), key=lambda slot: (not slot.startswith(own), slot))
            if parsed["name"] in ("__ct", "__dt"):
                result = "constructor" if parsed["name"] == "__ct" else "destructor"
            elif parsed.get("const"):
                result = "const method"
            elif slots:
                result = f"virtual: slot {slots[0]}"
            else:
                static_rows, complete = parameter_registers(parsed.get("params"), False, self.symbols.scalars)
                if complete:
                    static_gprs = {name for name, _value in static_rows if not name.startswith("f")}
                    reads = argument_reads(self.ctx, address)
                    beyond = sorted(
                        (name for name in reads if not name.startswith("f") and name not in static_gprs),
                        key=GPR.index,
                    )
                    if beyond:
                        result = (
                            f"reads {beyond[0]} at 0x{min(reads[beyond[0]]):x}, beyond the {len(static_gprs)} GPR "
                            "parameter(s) a static function with this signature takes"
                        )
            if result is None and parsed["name"] in _MEMBER_OPERATORS:
                result = f"member {OPERATORS[parsed['name']]} (C++ member operators other than new/delete are never static)"
            if result is None and self.dwarf.get(address):
                result = "DWARF formal parameter this"
        self._cache[address] = result
        return result


class CallParameters:
    """What a callee takes in each argument register, from its mangled signature and receiver proof.

    A proven member or a free function has one register reading.  A member
    whose receiver is unproven has two (member and static); a register's
    type is derivable only where they agree.
    """

    UNSETTLED = "parameter registers are not settled past a by-value class, array, varargs or the last argument register"

    def __init__(self, symbols: _Symbols, receivers: _Receivers) -> None:
        self.symbols = symbols
        self.receivers = receivers
        self._cache: dict[int, tuple[list[tuple[dict[str, str], bool]], str | None]] = {}
        self._values: dict[int, list[dict[str, dict]]] = {}

    def readings(self, callee: int | None) -> tuple[list[tuple[dict[str, str], bool]], str | None]:
        """[(register -> type, complete)] per reading, or [] and why no reading exists."""

        if callee is None:
            return [], "indirect call: the callee is not known"
        if callee in self._cache:
            return self._cache[callee]
        parsed = self.symbols.parsed(callee)
        if not parsed or parsed.get("params") is None:
            result: tuple[list[tuple[dict[str, str], bool]], str | None] = (
                [],
                "no mangled parameter list; its DWARF subprogram lists only named parameters"
                if callee in self.receivers.dwarf
                else "no mangled parameter list or DWARF subprogram",
            )
        else:
            qualified = bool(parsed.get("qualifier"))
            proven = qualified and self.receivers.proof(callee) is not None
            readings = []
            values: list[dict[str, dict]] = []
            for has_this in ((True,) if proven else (True, False) if qualified else (False,)):
                rows, complete = parameter_registers(parsed["params"], has_this, self.symbols.scalars)
                types = {register: render_type(value) for register, value in rows}
                if has_this:
                    types["a0"] = f"{_qualified(parsed['qualifier'])} * (receiver)"
                readings.append((types, complete))
                values.append({register: value for register, value in rows})
            self._values[callee] = values
            result = (readings, None)
        self._cache[callee] = result
        return result

    def value_of(self, callee: int | None, register: str) -> dict[str, Any] | None:
        """The mangled parameter type every reading gives ``register``, else None."""

        readings, missing = self.readings(callee)
        if missing:
            return None
        found = [values.get(register) for values in self._values.get(callee, [])]
        if not found or any(value is None or value != found[0] for value in found):
            return None
        return found[0]

    def of(self, callee: int | None, register: str) -> dict[str, Any]:
        """``{"parameter_type": T}``, ``{"no_parameter": True}`` or ``{"parameter_unknown": reason}``."""

        readings, missing = self.readings(callee)
        if missing:
            return {"parameter_unknown": missing}
        outcomes = []
        for types, complete in readings:
            if register in types:
                outcomes.append(("type", types[register]))
            else:
                outcomes.append(("none" if complete else "unsettled", ""))
        if len(set(outcomes)) == 1:
            kind, text = outcomes[0]
            if kind == "type":
                return {"parameter_type": text}
            if kind == "none":
                return {"no_parameter": True}
            return {"parameter_unknown": self.UNSETTLED}
        member, static = (
            text if kind == "type" else "no parameter" if kind == "none" else "not settled" for kind, text in outcomes
        )
        return {"parameter_unknown": f"receiver unproven: {member} if a member, {static} if static"}


# -- per-function dataflow -------------------------------------------------


def _join(left: dict | None, right: dict) -> dict:
    """Values every path agrees on; a pointer met at different offsets becomes that pointer plus an index."""

    if left is None:
        return dict(right)
    result = {}
    for key, value in left.items():
        other = right.get(key)
        if value is None or other is None:
            continue
        if other == value:
            result[key] = value
        elif isinstance(key, tuple) and key[0] in ("s", "g"):
            if value[1] == other[1]:
                widened = _widen(value[0], other[0])
                if widened is not None:
                    result[key] = (widened, value[1])
        else:
            widened = _widen(value, other)
            if widened is not None:
                result[key] = widened
    return result


class _Analysis:
    """Forward must-dataflow over one function: proven values per register.

    Registers are GPR numbers and ("f", n) for FPRs; ("s", offset) is a
    stack slot relative to the entry sp, holding (value, width).  A join
    keeps a value only when every visited predecessor agrees.
    """

    def __init__(self, ctx: Any, symbols: _Symbols, start: int, env: Any = None) -> None:
        self.ctx = ctx
        self.symbols = symbols
        self.start = start
        # Holder typing (``_Holders``): typed loads, typed call results and
        # private statics.  ``holds`` records where each hold term came from.
        self.env = env
        self.holds: dict[tuple, tuple] = {}
        self.flow = ctx.flow(start)
        self.fn = self.flow.fn
        self.end = self.flow.end
        successors: dict[int, set[int]] = defaultdict(set)
        for target, sources in self.fn.predecessors.items():
            for source in sources:
                successors[source].add(target)
        self.successors = successors
        entry: dict[Any, Any] = {0: _ZERO, _SP: (("sp",), 0)}
        for register in range(4, 12):
            entry[register] = (("arg", register), 0)
        for register in range(12, 20):
            entry[("f", register)] = (("farg", register), 0)
        self.states: dict[int, dict] = {start: entry}
        self.calls: list[dict[str, Any]] = []
        self.memory: list[dict[str, Any]] = []
        self.uses: list[dict[str, Any]] = []
        self.unattributed: list[int] = []
        self._run()
        self._mark_copies()

    def _get(self, state: dict, register: int) -> Any:
        if register == 0:
            return _ZERO
        return state.get(register)

    def _set(self, state: dict, register: Any, value: Any) -> None:
        if register == 0:
            return
        if value is None or _depth(value) > _MAX_DEPTH:
            state.pop(register, None)
        else:
            state[register] = value

    def _call_kind(self, pc: int) -> str | None:
        """Whether ``pc`` is the delay slot of a call or of an outgoing tail jump."""

        if pc - 4 < self.start:
            return None
        owner = self.fn.decoded.get(pc - 4)
        if not owner:
            return None
        if owner["kind"] in ("call", "call-branch"):
            return "call"
        if owner["kind"] == "jump" and owner["target"] is not None and not (self.start <= owner["target"] < self.end):
            return "tail"
        return None

    def _call_target(self, site: int, before: dict) -> tuple[int | None, Any]:
        insn = self.ctx.code.word(site)
        if insn >> 26 in (0x02, 0x03):
            return ((site + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2), None
        if insn >> 26 == 0x00 and insn & 0x3F == 0x09:
            return None, before.get((insn >> 21) & 31)
        return None, None

    def _transfer(self, pc: int, before: dict, record: bool) -> dict:
        ctx = self.ctx
        insn = ctx.code.word(pc)
        state = dict(before)
        op, rs, rt, rd = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, (insn >> 11) & 31
        sa, funct = (insn >> 6) & 31, insn & 0x3F
        imm = insn & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        ref = ctx.ref_at.get(pc)
        target = int(ref["target"], 16) if ref and ref.get("target") else None
        if record:
            self._record_uses(pc, insn, before)
        handled = True
        if op == 0x00:
            a, b = self._get(before, rs), self._get(before, rt)
            if insn == 0:
                pass
            elif funct in (0x21, 0x2D):  # addu / daddu
                if rs == 0 or rt == 0:
                    self._set(state, rd, b if rs == 0 else a)
                else:
                    added = _add(a, b)
                    self._set(state, rd, added if added is not None else _index(a, b))
            elif funct == 0x25:  # or
                self._set(state, rd, b if rs == 0 else a if rt == 0 else _logic("or", a, b))
            elif funct in (0x23, 0x2F):  # subu / dsubu
                self._set(state, rd, _add(a, -b[1]) if _is_const(b) else None)
            elif funct in (0x24, 0x26, 0x27):
                self._set(state, rd, _logic({0x24: "and", 0x26: "xor", 0x27: "nor"}[funct], a, b))
            elif funct in _SHIFTS:
                name, extra = _SHIFTS[funct]
                amount = sa + extra
                self._set(state, rd, _const(_fold(name, b[1], amount)) if _is_const(b) else _bits(b, name, amount))
            elif funct in (0x0A, 0x0B):  # movz / movn: rd keeps or takes rs
                current = self._get(before, rd)
                self._set(state, rd, current if current == a else None)
            else:
                handled = False
        elif op in (0x08, 0x09, 0x18, 0x19):  # addi(u) / daddi(u)
            if target is not None:
                self._set(state, rt, (("sym",), target))
            else:
                self._set(state, rt, _add(self._get(before, rs), simm))
        elif op == 0x0F:  # lui
            self._set(state, rt, _const((imm << 16) - (1 << 32) if imm & 0x8000 else imm << 16))
        elif op in (0x0C, 0x0D, 0x0E):  # andi / ori / xori
            name = {0x0C: "and", 0x0D: "or", 0x0E: "xor"}[op]
            self._set(state, rt, _logic(name, self._get(before, rs), _const(imm)))
        elif op in _MEMORY:
            self._memory(pc, insn, before, state, target, record)
        elif op == 0x11 and rs == 0x04:  # mtc1
            self._set(state, ("f", rd), self._get(before, rt))
        elif op == 0x11 and rs == 0x00:  # mfc1
            self._set(state, rt, before.get(("f", rd)))
        elif op == 0x11 and rs == 0x10 and funct == 0x06:  # mov.s
            self._set(state, ("f", sa), before.get(("f", rd)))
        elif op == 0x1C and funct == 0x29 and sa == 0x12 and rt == 0:  # por rd, rs, zero (128-bit move)
            self._set(state, rd, self._get(before, rs))
        else:
            handled = False
        if not handled:
            gprs, _fprs = _writes(insn)
            for register in gprs:
                self._set(state, register, None)
            for register in _fpr_writes(insn):
                self._set(state, ("f", register), None)
        kind = self._call_kind(pc)
        if kind:
            site = pc - 4
            callee, pointer = self._call_target(site, self.states.get(site, {}))
            if record:
                self._record_call(site, callee, pointer, state, kind)
            self._clobber(state, site, callee)
        return state

    def _clobber(self, state: dict, site: int, callee: int | None) -> None:
        escaped = [
            state[register][1]
            for register in range(4, 12)
            if state.get(register) is not None and state[register][0] == ("sp",)
        ]
        if escaped:
            # The callee may write through a stack address it receives.
            low = min(escaped)
            for key in [key for key in state if isinstance(key, tuple) and key[0] == "s" and key[1] + state[key][1] > low]:
                del state[key]
        for key in [key for key in state if isinstance(key, tuple) and key[0] == "g"]:
            del state[key]  # the callee may write a static (a recursive call writes its own)
        a0 = state.get(4)
        for register in _CALL_CLOBBERED_GPRS:
            state.pop(register, None)
        for register in range(0, 20):
            state.pop(("f", register), None)
        fact = self.env.returns.get(callee) if self.env is not None and callee is not None else None
        parsed = self.symbols.parsed(callee)
        if fact is not None and fact[0] == "this" and a0 is not None and _add(a0, fact[1]) is not None:
            # Every exit of the callee returns its entry a0 plus a constant.
            state[2] = _add(a0, fact[1])
        elif fact is not None and fact[0] == "type":
            term = ("hold", ("res", site), fact[1])
            self.holds[term] = ("return", site, callee)
            state[2] = (term, 0)
        elif parsed.get("name") == "__ct" and a0 is not None and callee in self.ctx.size and _ctor_returns_this(self.ctx, callee):
            # A Metrowerks constructor returns this (every exit returns the entry a0).
            state[2] = a0
        else:
            state[2] = (("res", site), 0)

    def _memory(self, pc: int, insn: int, before: dict, state: dict, target: int | None, record: bool) -> None:
        op, rs, rt = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31
        width, kind, signed, store, fpr = _MEMORY[op]
        imm = insn & 0xFFFF
        simm = imm - 0x10000 if imm & 0x8000 else imm
        dest = ("f", rt) if fpr else rt
        base = self._get(before, rs)
        address = (("sym",), target) if target is not None else _add(base, simm)
        private = (
            address is not None and address[0] == ("sym",) and self.env is not None
            and self.env.private_static(self.start, address[1])
        )
        if store:
            value = before.get(dest) if fpr else self._get(before, rt)
            if address is not None and (address[0] == ("sp",) or private):
                space = "s" if address[0] == ("sp",) else "g"
                low, high = address[1], address[1] + width
                for key in [key for key in state if isinstance(key, tuple) and key[0] == space]:
                    if key[1] < high and key[1] + state[key][1] > low:
                        del state[key]
                if kind != "partial" and value is not None and _depth(value) <= _MAX_DEPTH:
                    state[(space, low)] = (value, width)
            if record:
                if not fpr and rt == 0:
                    kind = "zero"
                self._record_memory(pc, address, width, kind, signed, True, value, None)
            return
        loaded: Any = None
        if address is not None and (address[0] == ("sp",) or private) and (
            slot := before.get(("s" if address[0] == ("sp",) else "g", address[1]))
        ) is not None:
            if slot[1] == width and kind != "partial":
                loaded = slot[0]
        elif address is not None and address[0] == ("sp",):
            pass
        elif address is not None and kind not in ("partial", "vu"):
            source = ("ld", address, width, kind, signed)
            desc = self.env.load(self.start, address, width, kind) if self.env is not None and not fpr else None
            if desc is not None:
                # Every element of one typed storage is the same value class, whatever its index: a loop
                # pointer's first pass (storage + 0) and its widened passes (storage + index) then agree.
                storage = address[0][1][0] if address[0][0] == "ix" else address[0]
                term = ("hold", ("elem", storage) if storage[0] == "hold" and storage[2][0] == "array" else source, desc)
                if record:
                    sites = self.holds.get(term, ("load", (), address))[1]
                    self.holds[term] = ("load", tuple(sorted(set(sites) | {pc})), address)
                loaded = (term, 0)
            else:
                loaded = (source, 0)
        if kind != "vu":
            self._set(state, dest, loaded)
        if record:
            self._record_memory(pc, address, width, kind, signed, False, None, loaded)

    def _record_memory(
        self, pc: int, address: Any, width: int, kind: str, signed: Any, store: bool, value: Any, loaded: Any
    ) -> None:
        if address is None:
            self.unattributed.append(pc)
            return
        if address[0] in (("sp",), ("sym",), ("const",)):
            return
        self.memory.append(
            {"site": pc, "address": address, "width": width, "kind": kind, "signed": signed, "store": store,
             "value": value, "loaded": loaded}
        )

    def _record_uses(self, pc: int, insn: int, state: dict) -> None:
        op, rs = insn >> 26, (insn >> 21) & 31
        if op in _MEMORY:
            return  # the memory record carries the base and the stored value
        gprs, fprs = _reads(insn)
        values = [(register, state.get(register)) for register in sorted(gprs)]
        values += [(("f", register), state.get(("f", register))) for register in sorted(fprs)]
        for register, value in values:
            if value is None or value[0][0] not in ("ld", "bits"):
                continue
            raw = value[0][0] == "ld"
            if op == 0x00 and insn & 0x3F == 0x09 and register == rs:
                how = "call-target"
            elif op == 0x00 and insn & 0x3F == 0x08:
                how = "jump-target"
            elif op in (0x01, 0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17, 0x0A, 0x0B) or (
                op == 0x00 and insn & 0x3F in (0x2A, 0x2B)
            ):
                how = "compare"
            elif op == 0x0C:
                how = f"mask 0x{insn & 0xFFFF:x}"
            elif op == 0x11 and rs == 0x00:
                how = "fpr-to-gpr"
            elif op == 0x11 and rs == 0x04:
                how = "gpr-to-fpr"
            elif op == 0x11:
                how = "float-op"
            else:
                how = "int-op"
            if not raw and how not in ("compare", "call-target", "jump-target"):
                continue  # intermediate bit operations; the compare carries the window
            self.uses.append({"site": pc, "value": value, "how": how})

    def _record_call(self, site: int, callee: int | None, pointer: Any, state: dict, kind: str) -> None:
        arguments = {}
        for register in range(4, 12):
            value = state.get(register)
            if value is not None:
                arguments[GPR[register]] = value
        for register in range(12, 20):
            value = state.get(("f", register))
            if value is not None:
                arguments[f"f{register}"] = value
        self.calls.append({"site": site, "callee": callee, "pointer": pointer, "arguments": arguments, "kind": kind})

    def _run(self) -> None:
        work = [self.start]
        queued = {self.start}
        while work:
            pc = work.pop()
            queued.discard(pc)
            out = self._transfer(pc, self.states[pc], record=False)
            for successor in sorted(self.successors.get(pc, ())):
                if not (self.start <= successor < self.end):
                    continue
                current = self.states.get(successor)
                joined = _join(current, out)
                if current is None or joined != current:
                    self.states[successor] = joined
                    if successor not in queued:
                        queued.add(successor)
                        work.append(successor)
        for pc in sorted(self.states):
            self._transfer(pc, self.states[pc], record=True)

    def _mark_copies(self) -> None:
        """A word moved through an FPR that no float instruction reads is a copy."""

        float_used = {use["value"][0] for use in self.uses if use["how"] in ("float-op", "compare", "fpr-to-gpr")}
        for call in self.calls:
            for register, value in call["arguments"].items():
                if register.startswith("f") and value[0][0] == "ld":
                    float_used.add(value[0])
        for event in self.memory:
            if event["kind"] != "float":
                continue
            if not event["store"] and event["loaded"] is not None and event["loaded"][0] not in float_used:
                event["kind"] = "fpr-copy"
            elif (
                event["store"]
                and event["value"] is not None
                and event["value"][0][0] == "ld"
                and event["value"][0] not in float_used
            ):
                event["kind"] = "fpr-copy"


_RETURNS_THIS: dict[int, bool] = {}


def _ctor_returns_this(ctx: Any, address: int) -> bool:
    from .recon_draft import _returns_this

    if address not in _RETURNS_THIS:
        _RETURNS_THIS[address] = _returns_this(ctx, address)
    return _RETURNS_THIS[address]


def _hex(value: int) -> str:
    return f"0x{value:x}" if value >= 0 else f"-0x{-value:x}"


def _string_at(ctx: Any, address: int) -> str | None:
    data = []
    for index in range(256):
        try:
            word = ctx.code.word((address + index) & ~3)
        except (IndexError, ValueError):  # pragma: no cover - outside the image
            return None
        byte = (word >> (8 * ((address + index) & 3))) & 0xFF
        if byte == 0:
            return bytes(data).decode("latin-1")
        if byte < 0x20 or byte > 0x7E:
            return None
        data.append(byte)
    return None


def dwarf_sizes(root: Path) -> dict[str, list[int]]:
    """DWARF 1 class/struct/union byte sizes by name (DWARF 1 names drop template arguments)."""

    path = root / "support" / "socom.elf"
    sizes: dict[str, set[int]] = defaultdict(set)
    for die in _dies_cached(file_key(path), str(path)):
        if die.tag_name in ("class_type", "structure_type", "union_type"):
            name = die.string("name")
            size = die.integer("byte_size")
            if name and size is not None:
                sizes[name].add(size)
    return {name: sorted(values) for name, values in sizes.items()}


# -- family -------------------------------------------------------------------


class _Family:
    """The classes whose layout evidence is collected."""

    def __init__(self, root: Path, name: str, with_derived: bool) -> None:
        self.root = root
        self.ctx = context(root)
        self.leaves, self.templates = class_leaves(root)
        self.symbols = _Symbols(self.ctx, dwarf_scalars(root, self.leaves))
        self.receivers = _Receivers(self.ctx, self.symbols, dwarf_subprograms(root))
        components = tuple(split_qualified(name))
        mangled_qualifier(list(components))
        self.requested = components
        self.rtti = self._rtti_index()
        members = self._members_by_class()
        if not members.get(components) and components not in self.rtti["by_class"]:
            raise SocomError(f"{name}: no member function or RTTI record has that qualifier")
        classes: dict[tuple[str, ...], str] = {components: "requested"}
        pending = [components]
        while pending:
            current = pending.pop()
            for base, _offset in self.bases(current):
                if base not in classes:
                    classes[base] = "base"
                    pending.append(base)
        if with_derived:
            for candidate in sorted(self.rtti["by_class"]):
                if candidate not in classes and any(base == components for base, _offset in self.bases(candidate)):
                    classes[candidate] = "derived"
        self.classes = classes
        self.members = {cls: members.get(cls, []) for cls in classes}
        self.vtable_class: dict[int, tuple[str, ...]] = {}
        for cls in classes:
            table = self.vtable_object(cls)
            if table is not None:
                self.vtable_class[table["address"]] = cls

    # RTTI: type_info_struct {char *tname; type_info_base_list *baselist;}
    # and type_info_base_list {type_info_struct *baseti; int offset;},
    # terminated by a null baseti (Metrowerks runtime MWRTTI.cpp).
    def _rtti_index(self) -> dict[str, Any]:
        by_address: dict[int, tuple[str, ...]] = {}
        by_class: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for row in self.symbols.objects:
            if row["name"].startswith("__RTTI__") and row["parsed"] and row["parsed"].get("params") is None:
                cls = tuple(row["parsed"]["qualifier"])
                by_address[row["address"]] = cls
                by_class[cls].append(row["address"])
        return {"by_address": by_address, "by_class": {key: sorted(value) for key, value in by_class.items()}}

    def _word(self, address: int) -> int:
        return self.ctx.code.word(address)

    def rtti_records(self, cls: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for address in self.rtti["by_class"].get(cls, []):
            name_ptr = self._word(address) if address in self.ctx.reloc32 else None
            bases_ptr = self._word(address + 4) if address + 4 in self.ctx.reloc32 else None
            bases = []
            if bases_ptr:
                cursor = bases_ptr
                for _ in range(64):
                    if cursor not in self.ctx.reloc32:
                        break
                    base_rtti = self._word(cursor)
                    offset = self._word(cursor + 4)
                    base_cls = self.rtti["by_address"].get(base_rtti)
                    bases.append(
                        {
                            "rtti": _hex(base_rtti),
                            "class": _qualified(base_cls) if base_cls else None,
                            "components": list(base_cls) if base_cls else None,
                            "offset": offset & 0x7FFFFFFF,
                            "ambiguous": bool(offset & 0x80000000),
                            "entry": _hex(cursor),
                        }
                    )
                    cursor += 8
            rows.append(
                {
                    "address": _hex(address),
                    "name": self.ctx.label(address).split("@")[0],
                    "type_name": _string_at(self.ctx, name_ptr) if name_ptr else None,
                    "base_list": _hex(bases_ptr) if bases_ptr else None,
                    "bases": bases,
                }
            )
        return rows

    def bases(self, cls: tuple[str, ...]) -> list[tuple[tuple[str, ...], int]]:
        """Every (transitive) base the RTTI base lists name, with its offset."""

        found: set[tuple[tuple[str, ...], int]] = set()
        for record in self.rtti_records(cls):
            for base in record["bases"]:
                if base["components"] is not None and not base["ambiguous"]:
                    found.add((tuple(base["components"]), base["offset"]))
        return sorted(found)

    def derives(self, derived: tuple[str, ...], base: tuple[str, ...]) -> bool:
        return derived == base or any(cls == base for cls, _offset in self.bases(derived))

    def _members_by_class(self) -> dict[tuple[str, ...], list[int]]:
        rows: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for address, row in self.symbols.functions.items():
            parsed = row.get("parsed")
            if parsed and parsed.get("qualifier"):
                rows[tuple(parsed["qualifier"])].append(address)
        return {key: sorted(value) for key, value in rows.items()}

    def vtable_object(self, cls: tuple[str, ...]) -> dict[str, Any] | None:
        name = f"__vt__{mangled_qualifier(list(cls))}"
        rows = [row for row in self.symbols.objects if row["name"] == name and row["size"]]
        return rows[0] if rows else None

    def vtable(self, cls: tuple[str, ...]) -> dict[str, Any] | None:
        row = self.vtable_object(cls)
        if row is None:
            return None
        words = []
        for offset in range(0, row["size"], 4):
            site = row["address"] + offset
            word = self._word(site)
            entry: dict[str, Any] = {"offset": offset, "word": _hex(word), "relocated": site in self.ctx.reloc32}
            if site in self.ctx.reloc32:
                if word in self.symbols.functions:
                    entry["function"] = _hex(word)
                    entry["function_name"] = self.symbols.readable(word)
                    entry["mangled"] = self.symbols.functions[word]["mangled"]
                else:
                    entry["target"] = self.ctx.label(word).split("@")[0]
            words.append(entry)
        return {
            "name": row["name"],
            "address": _hex(row["address"]),
            "size": row["size"],
            # RTTIVTableHeader {type_info_struct *type_info_ptr; int complete_offset;}
            "header": {"type_info": words[0] if words else None, "complete_offset": words[1] if len(words) > 1 else None},
            "slots": [{**entry, "slot": (entry["offset"] - 8) // 4} for entry in words[2:]],
        }


# -- holders: class pointers stored outside the family -----------------------

_JR_RA = 0x03E00008
_POINTER, _CONST, _VOLATILE = 1, 3, 4


def _dwarf_address(die: Any) -> int | None:
    attribute = die.attribute("location")
    value = attribute.value if attribute else None
    # DW_OP_ADDR <u32>: a static location.
    if isinstance(value, bytes) and len(value) == 5 and value[0] == 0x03:
        return int.from_bytes(value[1:5], "little")
    return None


def class_leaves(root: Path) -> tuple[dict[str, frozenset[tuple[str, ...]]], frozenset[str]]:
    """(leaf name -> qualified classes the mangled symbols name, leaf names of templates).

    DWARF 1 names drop qualifiers and template arguments, so a DWARF record
    names a class only through its leaf, and only when exactly one mangled
    class has that leaf and no template does.
    """

    from .type_plan_evidence import _mentioned_cached

    path = root / "support" / "socom.elf"
    leaves: dict[str, set[tuple[str, ...]]] = defaultdict(set)
    templates: set[str] = set()
    for name in _mentioned_cached(file_key(path), str(path)):
        components = tuple(split_qualified(name))
        for part in components:
            if "<" in part:
                templates.add(template_base(part))
        if components:
            leaves[components[-1]].add(components)
    return {leaf: frozenset(values) for leaf, values in leaves.items()}, frozenset(templates)


def dwarf_scalars(root: Path, leaves: dict[str, frozenset[tuple[str, ...]]]) -> frozenset[tuple[str, ...]]:
    """Mangled class names whose every DWARF record of that leaf is an enumeration (no composite).

    A typedef names an enumeration when it refers to one (``typedef enum {...} NAME``); a typedef of
    anything else counts against the name.
    """

    from .type_plan_evidence import COMPOSITE_TAGS, TypeEvidence

    dwarf = TypeEvidence(root).dwarf
    enums, composites = set(), set()
    for die in dwarf.dies:
        name = die.string("name")
        if not name:
            continue
        if die.tag_name == "typedef":
            target = dwarf.die(die.integer("user_def_type")) if die.integer("user_def_type") is not None else None
            (enums if target is not None and target.tag_name == "enumeration_type" else composites).add(name)
        elif die.tag_name == "enumeration_type":
            enums.add(name)
        elif die.tag_name in COMPOSITE_TAGS:
            composites.add(name)
    found = set()
    for leaf in enums - composites:
        names = leaves.get(leaf, frozenset())
        if len(names) == 1:
            found.update(names)
    return frozenset(found)


def _class_text(cls: tuple[str, ...]) -> str:
    return _qualified(cls)


def _hold_site(info: tuple) -> int:
    """The first load site of a typed load, or the call site of a typed result."""

    return info[1][0] if info[0] == "load" else info[1]


def _copy_source(insn: int, register: int) -> int | None:
    """The source GPR when ``insn`` copies one GPR into ``register`` unchanged (move/addu/daddu/or/por with zero)."""

    op, rs, rt, rd = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, (insn >> 11) & 31
    if rd != register:
        return None
    if op == 0x00 and insn & 0x3F in (0x21, 0x2D, 0x25) and (insn >> 6) & 31 == 0 and 0 in (rs, rt) and (rs, rt) != (0, 0):
        return rt if rs == 0 else rs
    if op == 0x1C and insn & 0x3F == 0x29 and (insn >> 6) & 31 == 0x12 and rt == 0 and rs != 0:
        return rs
    return None


class _Holders:
    """Class pointers held outside the family, each with its proof (see the module docstring).

    A type is ``(shape, class)``: shape "ptr" points to the class, "array"
    to storage of pointers to it.  Classes are qualified tuples; a DWARF
    record names one by its leaf (``class_ref``).
    """

    def __init__(self, family: _Family, parameters: CallParameters) -> None:
        from .type_plan_evidence import TypeEvidence

        self.family = family
        self.ctx = family.ctx
        self.symbols = family.symbols
        self.receivers = family.receivers
        self.parameters = parameters
        self.dwarf = TypeEvidence(family.root).dwarf
        self.leaves, self.templates = family.leaves, family.templates
        # (DWARF record, offset) of pointer storage -> element class and proofs.
        self.elements: dict[tuple[str, int], dict[str, Any]] = {}
        self.element_conflicts: dict[tuple[str, int], dict[str, list[str]]] = {}
        # function -> ("this", k) or ("type", (shape, class)); the proof text of each typed return.
        self.returns: dict[int, tuple] = {}
        self.return_proofs: dict[int, str] = {}
        self._entries: dict[int, dict[int, tuple[tuple[str, ...], str]]] = {}
        self._members: dict[tuple[str, int], Any] = {}
        self._private: dict[tuple[int, int], bool] = {}
        self._ref_targets = sorted(self.ctx.addr_taken)
        self._data_targets = sorted(self.ctx.word32)
        globals_at: dict[int, list[Any]] = defaultdict(list)
        for die in self.dwarf.dies:
            if die.tag_name == "global_variable":
                address = _dwarf_address(die)
                if address is not None:
                    globals_at[address].append(die)
        self._globals = dict(globals_at)
        objects = []
        for address, dies in sorted(self._globals.items()):
            records = {self._composite(die.integer("user_def_type")) for die in dies}
            if len(records) == 1 and None not in records:
                record = records.pop()
                cls = self.class_ref(record.string("name") or "")
                size = record.integer("byte_size") or 0
                if cls is not None and size > 0:
                    objects.append((address, address + size, cls, dies[0]))
        self._objects = objects
        self._object_starts = [row[0] for row in objects]

    # -- classes ---------------------------------------------------------

    def class_ref(self, leaf: str) -> tuple[str, ...] | None:
        """The class a DWARF leaf name denotes, or None when templates or several classes share it."""

        if not leaf or "<" in leaf or leaf in self.templates:
            return None
        names = self.leaves.get(leaf)
        if not names:
            return (leaf,)  # a DWARF-only class
        if len(names) != 1:
            return None
        only = next(iter(names))
        return None if any("<" in part for part in only) else only

    def dwarf_leaf(self, cls: tuple[str, ...]) -> str | None:
        """The DWARF leaf of a holder class with complete records (never a family class)."""

        if not cls or cls in self.family.classes or self.class_ref(cls[-1]) != tuple(cls):
            return None
        return cls[-1] if any((die.integer("byte_size") or 0) > 0 for die in self.dwarf.records(cls[-1])) else None

    def _composite(self, offset: int | None) -> Any:
        from .type_plan_evidence import COMPOSITE_TAGS

        seen = set()
        while offset is not None and offset not in seen:
            seen.add(offset)
            record = self.dwarf.die(offset)
            if record is None:
                return None
            if record.tag_name in COMPOSITE_TAGS:
                return record
            if record.tag_name != "typedef":
                return None
            offset = record.integer("user_def_type")
        return None

    def _pointer(self, die: Any, depth: int = 0) -> tuple[str, Any] | None:
        """("class", leaf) / ("fund", code) when the DWARF type of ``die`` is a single-level pointer."""

        for name, width in (("mod_user_def_type", 4), ("mod_fund_type", 2)):
            attribute = die.attribute(name)
            value = attribute.value if attribute else None
            if isinstance(value, bytes) and len(value) > width:
                modifiers = value[:-width]
                if modifiers.count(_POINTER) != 1 or any(item not in (_POINTER, _CONST, _VOLATILE) for item in modifiers):
                    return None
                target = int.from_bytes(value[-width:], "little")
                if width == 2:
                    return ("fund", target)
                record = self._composite(target)
                return ("class", record.string("name")) if record is not None and record.string("name") else None
        target = die.integer("user_def_type")
        if target is not None and depth < 8:
            record = self.dwarf.die(target)
            if record is not None and record.tag_name == "typedef":
                return self._pointer(record, depth + 1)
        return None

    # -- DWARF members -----------------------------------------------------

    def _walk(self, die: Any, offset: int, depth: int = 0) -> list[tuple[tuple, tuple]]:
        from .type_plan_evidence import _location

        name = die.string("name") or ""
        hits = []
        for child in self.dwarf.children(die):
            if child.tag_name not in ("member", "inheritance") or child.attribute("bit_size") is not None:
                continue
            location = _location(child)
            if location is None or location > offset:
                continue
            target = self.dwarf.by_value(child)
            label = child.string("name") if child.tag_name == "member" else f"<base {target.string('name') if target else '?'}>"
            if child.tag_name == "member" and location == offset:
                pointer = self._pointer(child)
                if pointer is not None:
                    hits.append((((name, label, offset),), pointer))
                    continue
            if target is not None and depth < 16 and location <= offset < location + (target.integer("byte_size") or 0):
                for path, pointer in self._walk(target, offset - location, depth + 1):
                    hits.append((((name, label, offset),) + path, pointer))
        return hits

    def member(self, cls: tuple[str, ...], offset: int | None) -> dict[str, Any] | None:
        """The pointer member at ``offset`` of a holder class, when every DWARF record of it agrees."""

        leaf = self.dwarf_leaf(cls) if offset is not None and offset >= 0 else None
        if leaf is None:
            return None
        key = (leaf, offset)
        if key not in self._members:
            found = set()
            for die in self.dwarf.records(leaf):
                if (die.integer("byte_size") or 0) <= 0:
                    continue
                hits = self._walk(die, offset)
                found.add(hits[0] if len(hits) == 1 else None)
            result = None
            if len(found) == 1 and None not in found:
                path, pointer = found.pop()
                storage = next(
                    ((record, inner) for record, _label, inner in reversed(path) if record not in self.templates),
                    (path[0][0], path[0][2]),
                )
                result = {"path": path, "pointer": pointer, "storage": storage}
            self._members[key] = result
        return self._members[key]

    def member_text(self, cls: tuple[str, ...], offset: int, hit: dict[str, Any]) -> str:
        names = ".".join(label for _record, label, _offset in hit["path"] if not label.startswith("<base "))
        storage = hit["storage"]
        inner = f" ({storage[0]}+{_hex(storage[1])})" if hit["pointer"][0] == "fund" and storage != (cls[-1], offset) else ""
        return f"DWARF {_class_text(cls)}+{_hex(offset)} {names}{inner}"

    # -- statics -------------------------------------------------------------

    def global_pointer(self, address: int) -> tuple[str, tuple[str, ...]] | None:
        dies = self._globals.get(address, [])
        found = {self._pointer(die) for die in dies}
        if len(found) != 1 or None in found:
            return None
        kind, leaf = found.pop()
        cls = self.class_ref(leaf) if kind == "class" else None
        return ("ptr", cls) if cls is not None else None

    def global_object(self, address: int) -> tuple[tuple[str, ...], int, Any] | None:
        """(class, start, DWARF record) of the DWARF global object of class type containing ``address``."""

        position = bisect.bisect_right(self._object_starts, address) - 1
        if position >= 0:
            start, end, cls, die = self._objects[position]
            if address < end:
                return cls, start, die
        return None

    def private_static(self, function: int, address: int) -> bool:
        """A static the ELF references only from ``function``'s direct loads and stores (no data relocation)."""

        position = bisect.bisect_right(self.ctx.object_starts, address) - 1
        if position < 0:
            return False
        start = self.ctx.object_starts[position]
        size = self.ctx.objects[start][0]
        if address >= start + size:
            return False
        key = (function, start)
        if key not in self._private:
            low = bisect.bisect_left(self._ref_targets, start)
            high = bisect.bisect_left(self._ref_targets, start + size)
            sites = [site for target in self._ref_targets[low:high] for site in self.ctx.addr_taken[target]]
            data = bisect.bisect_left(self._data_targets, start) < bisect.bisect_left(self._data_targets, start + size)
            self._private[key] = bool(sites) and not data and all(
                self.ctx.owner(site) == function and self.ctx.code.word(site) >> 26 in _MEMORY for site in sites
            )
        return self._private[key]

    # -- typing ----------------------------------------------------------------

    def entry(self, function: int) -> dict[int, tuple[tuple[str, ...], str]]:
        """Entry registers holding a class pointer: the proven receiver and single-level pointer parameters."""

        if function not in self._entries:
            parsed = self.symbols.parsed(function)
            rows: dict[int, tuple[tuple[str, ...], str]] = {}
            if parsed and parsed.get("params") is not None:
                qualified = bool(parsed.get("qualifier"))
                proof = self.receivers.proof(function) if qualified else None
                if not qualified or proof is not None:
                    if proof is not None:
                        rows[4] = (tuple(parsed["qualifier"]), f"this ({proof})")
                    registers, _complete = parameter_registers(parsed.get("params"), proof is not None, self.symbols.scalars)
                    for register, value in registers:
                        cls = _pointee_class(value)
                        if cls is not None and not register.startswith("f"):
                            rows.setdefault(GPR.index(register), (cls, f"parameter {register} ({render_type(value)})"))
            self._entries[function] = rows
        return self._entries[function]

    def type_of(self, function: int, value: Any) -> tuple[tuple[str, tuple[str, ...]], int | None] | None:
        """((shape, class), offset) of a pointer value, or None; an array element's offset is None when indexed."""

        if value is None:
            return None
        term, k = value
        if term[0] == "arg":
            row = self.entry(function).get(term[1])
            return (("ptr", row[0]), k) if row else None
        if term[0] == "hold":
            return term[2], k
        if term[0] == "ix":
            inner = self.type_of(function, term[1])
            return (inner[0], None) if inner is not None and inner[0][0] == "array" else None
        if term == ("sym",):
            found = self.global_object(k)
            return (("ptr", found[0]), k - found[1]) if found else None
        return None

    def load(self, function: int, address: Any, width: int, kind: str) -> tuple[str, tuple[str, ...]] | None:
        """The type a 4-byte load from ``address`` holds, or None (family objects keep their own loads)."""

        if width != 4 or kind != "int" or address is None:
            return None
        if address[0] == ("sym",):
            typed = self.global_pointer(address[1])
            if typed is not None:
                return typed
        found = self.type_of(function, address)
        if found is None:
            return None
        (shape, cls), offset = found
        if shape == "array":
            return ("ptr", cls) if offset is None or (offset >= 0 and offset % 4 == 0) else None
        hit = self.member(cls, offset)
        if hit is None:
            return None
        kind_, target = hit["pointer"]
        if kind_ == "class":
            ref = self.class_ref(target)
            return ("ptr", ref) if ref is not None else None
        fact = self.elements.get(hit["storage"])
        return ("array", fact["class"]) if fact is not None else None

    # -- element facts -----------------------------------------------------------

    def storage(self, function: int, value: Any) -> tuple[tuple[str, int], str] | None:
        """Pointer storage (DWARF pointer-to-fundamental member) a value points into, with its description."""

        term, k = value
        pointer, aligned = (term[1], k % 4 == 0) if term[0] == "ix" else (value, True)
        inner, offset = pointer
        if inner[0] != "ld" or inner[2] != 4 or inner[3] != "int" or not aligned or offset % 4 or (term[0] != "ix" and k < 0):
            return None
        found = self.type_of(function, inner[1])
        if found is None or found[0][0] != "ptr" or found[1] is None:
            return None
        cls, member_offset = found[0][1], found[1]
        hit = self.member(cls, member_offset)
        if hit is None or hit["pointer"][0] != "fund":
            return None
        index = "an index" if term[0] == "ix" else _hex(k + offset)
        return hit["storage"], f"{self.member_text(cls, member_offset, hit)} + {index}"

    def discover_elements(self, analyses: dict[int, _Analysis]) -> None:
        """Element classes of pointer storage passed as a mangled ``T **`` / ``T *&`` parameter."""

        found: dict[tuple[str, int], dict[tuple[str, ...], set[str]]] = defaultdict(lambda: defaultdict(set))
        for function, analysis in sorted(analyses.items()):
            for call in analysis.calls:
                for register, value in sorted(call["arguments"].items(), key=lambda item: _register_order(item[0])):
                    if register.startswith("f"):
                        continue
                    mangled = self.parameters.value_of(call["callee"], register)
                    if not mangled or mangled.get("kind") != "class" or len(_levels(mangled)) != 2 or _levels(mangled)[-1] != "P":
                        continue
                    located = self.storage(function, value)
                    if located is None:
                        continue
                    key, text = located
                    found[key][tuple(mangled["components"])].add(
                        f"{text} passed as {register} ({render_type(mangled)}) of {self.symbols.readable(call['callee'])} "
                        f"@0x{call['site']:x} in {self.symbols.readable(function)}"
                    )
        for key, classes in sorted(found.items()):
            if len(classes) == 1:
                cls, proofs = next(iter(classes.items()))
                self.elements[key] = {"class": cls, "proofs": sorted(proofs)}
            else:
                self.element_conflicts[key] = {_class_text(cls): sorted(proofs) for cls, proofs in sorted(classes.items())}

    # -- returns -------------------------------------------------------------------

    def compute_return(self, function: int, analysis: _Analysis, roots: dict[Any, tuple]) -> None:
        """Record what every exit of ``function`` returns: its entry a0 plus k, or NULL / one proven class."""

        flow = analysis.flow
        exits = []
        for pc in range(function, analysis.end, 4):
            row = flow.fn.decoded.get(pc) or {}
            if not flow.reachable(pc):
                continue
            insn = self.ctx.code.word(pc)
            if insn == _JR_RA:
                exits.append(pc)
            elif row.get("kind") == "jr" or (
                row.get("kind") == "jump" and row.get("target") is not None and not (function <= row["target"] < analysis.end)
            ):
                return  # a tail transfer returns what another function returns
        if not exits:
            return
        values: list[Any] = []
        for pc in exits:
            found = self._values(analysis, flow.after(pc + 4, 2), 2)
            if found is None:
                return
            values.extend(found)
        offsets = {value[1] for value in values if value[0] == ("arg", 4)}
        if all(value[0] == ("arg", 4) for value in values) and len(offsets) == 1:
            self.returns[function] = ("this", offsets.pop())
            return
        typed: list[tuple[tuple[str, tuple[str, ...]], str]] = []
        nulls = False
        for value in values:
            if value == _ZERO:
                nulls = True
            elif value[1] == 0 and value[0] in roots:
                typed.append((("ptr", roots[value[0]][0]), roots[value[0]][2]))
            else:
                found = self.type_of(function, value)
                if found is None or found[1] != 0:
                    return
                typed.append((found[0], self.value_proof(function, analysis, value)))
        if not typed:
            return
        shapes = {item[0] for item in typed}
        if len(shapes) > 1:
            classes = {cls for shape, cls in shapes}
            if {shape for shape, _cls in shapes} != {"ptr"} or not classes <= set(self.family.classes):
                return
            common = [cls for cls in classes if all(self.family.derives(other, cls) for other in classes)]
            if len(common) != 1:
                return
            shapes = {("ptr", common[0])}
        shape = shapes.pop()
        proofs = sorted({proof for _shape, proof in typed})
        self.returns[function] = ("type", shape)
        self.return_proofs[function] = (
            f"{self.symbols.readable(function)} returns {'NULL or ' if nulls else ''}"
            + ("a pointer into storage of " if shape[0] == "array" else "a ")
            + f"{_class_text(shape[1])}* at every exit: "
            + "; ".join(proofs)
        )

    def _values(self, analysis: _Analysis, definitions: set[Any], register: int, depth: int = 0) -> list[Any] | None:
        """Every value ``register`` can hold given its reaching definitions, or None if one is unknown.

        A definition whose proven value the joins lost, but which is a plain
        register copy, contributes the values of its source's reaching
        definitions (paths meeting with different allocations, say).
        """

        values: list[Any] = []
        for definition in sorted(definitions, key=str):
            if definition == "entry" or definition not in analysis.states:
                return None
            value = analysis._transfer(definition, analysis.states[definition], record=False).get(register)
            if value is None:
                source = _copy_source(self.ctx.code.word(definition), register)
                if source is None or depth >= 8 or analysis._call_kind(definition):
                    return None
                inner = self._values(analysis, analysis.flow.defs(definition, source), source, depth + 1)
                if inner is None:
                    return None
                values.extend(inner)
            else:
                values.append(value)
        return values

    # -- proofs ----------------------------------------------------------------------

    def value_proof(self, function: int, analysis: _Analysis, value: Any, depth: int = 0) -> str:
        """Why a pointer value has the type ``type_of`` gives it."""

        term = value[0]
        if depth > 12:
            return "..."
        if term[0] == "arg":
            row = self.entry(function).get(term[1])
            return row[1] if row else f"entry {GPR[term[1]]}"
        if term[0] == "ix":
            return self.value_proof(function, analysis, term[1], depth + 1)
        if term == ("sym",):
            found = self.global_object(value[1])
            return f"DWARF global {found[2].string('name')} ({_class_text(found[0])}) @0x{found[1]:x}" if found else "static"
        if term[0] == "hold":
            return self.hold_proof(function, analysis, term, depth + 1)
        return "unknown"

    def hold_proof(self, function: int, analysis: _Analysis, term: tuple, depth: int = 0) -> str:
        """Why a hold term has its type: the typed member, element storage, global or call, and its base."""

        info = analysis.holds.get(term)
        shape, cls = term[2]
        if info is None:
            return f"{shape} {_class_text(cls)}"
        if info[0] == "return":
            return f"result of {self.symbols.readable(info[2])} @0x{info[1]:x} [{self.return_proofs.get(info[2], '?')}]"
        at = "/".join(f"0x{pc:x}" for pc in info[1])
        address = info[2]
        if address[0] == ("sym",) and self.global_pointer(address[1]) is not None:
            names = sorted({die.string("name") or "?" for die in self._globals.get(address[1], [])})
            return f"DWARF global {'/'.join(names)} ({_class_text(cls)}*) loaded @{at}"
        found = self.type_of(function, address)
        if found is None:
            return f"{shape} {_class_text(cls)} loaded @{at}"
        (base_shape, base_cls), offset = found
        base = self.value_proof(function, analysis, address, depth + 1)
        if base_shape == "array":
            return f"element {_class_text(cls)}* loaded @{at} from [{base}]"
        hit = self.member(base_cls, offset)
        what = self.member_text(base_cls, offset, hit) if hit else f"{_class_text(base_cls)}+{_hex(offset or 0)}"
        if shape == "array":
            fact = self.elements.get(hit["storage"]) if hit else None
            elements = (
                f"; elements {_class_text(cls)}* because {fact['proofs'][0]}"
                + (f" (+{len(fact['proofs']) - 1} more)" if len(fact["proofs"]) > 1 else "")
                if fact else ""
            )
            return f"{what} (storage of {_class_text(cls)}*{elements}) loaded @{at} from [{base}]"
        return f"{what} ({_class_text(cls)}*) loaded @{at} from [{base}]"


# -- attribution -------------------------------------------------------------


def _register_order(name: str) -> tuple[int, int]:
    return (1, int(name[1:])) if name.startswith("f") else (0, GPR.index(name))


def _path_text(path: list[Any]) -> str:
    text = ""
    for step in path:
        text += "[i]" if step == "[i]" else f"+{_hex(step)}->"
    return text


class _Collector:
    """Runs the dataflow over the family's functions and attributes events."""

    def __init__(self, family: _Family) -> None:
        self.family = family
        self.ctx = family.ctx
        self.symbols = family.symbols
        self.receivers = family.receivers
        self.calls_by_site: dict[int, int | None] = {}
        self.analyses: dict[int, _Analysis] = {}
        self.roots: dict[int, dict[Any, tuple[tuple[str, ...], str, str]]] = {}
        self.param_types: dict[int, dict[str, str]] = {}
        self.parameters = CallParameters(self.symbols, self.receivers)
        self.unresolved: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        self.allocations: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        self.constructions: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        self.sites: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        self.object_passes: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
        self.functions: dict[int, dict[str, Any]] = {}
        self._select()
        self._attribute()

    def _select(self) -> None:
        classes = set(self.family.classes)
        entry_roots: dict[int, dict[Any, tuple[tuple[str, ...], str, str]]] = defaultdict(dict)
        for cls in sorted(classes):
            for address in self.family.members[cls]:
                proof = self.receivers.proof(address)
                if proof is None:
                    self.unresolved[cls].append(
                        {
                            "function": _hex(address),
                            "name": self.symbols.readable(address),
                            "reason": "receiver unproven: not a constructor, destructor, const method or vtable "
                            "slot, and no argument register is read beyond a static function's parameters",
                        }
                    )
                    continue
                entry_roots[address][("arg", 4)] = (cls, "this", f"this ({proof})")
        for address, row in sorted(self.symbols.functions.items()):
            parsed = row.get("parsed")
            if not parsed or not any(_pointee_class(value) in classes for value in parsed.get("params") or []):
                continue
            has_this = bool(parsed.get("qualifier")) and self.receivers.proof(address) is not None
            if parsed.get("qualifier") and not has_this:
                owner = _qualified(parsed["qualifier"])
                for value in parsed.get("params") or []:
                    if _pointee_class(value) in classes:
                        self.unresolved[_pointee_class(value)].append(
                            {
                                "function": _hex(address),
                                "name": self.symbols.readable(address),
                                "reason": f"typed parameter not mapped: the receiver of this {owner} member is "
                                "unproven, so its argument registers are not settled",
                            }
                        )
                continue
            rows, _complete = parameter_registers(parsed.get("params"), has_this, self.symbols.scalars)
            for register, value in rows:
                cls = _pointee_class(value)
                if cls in classes and not register.startswith("f"):
                    entry_roots[address].setdefault(
                        ("arg", GPR.index(register)),
                        (cls, f"param {register}", f"parameter {register} ({render_type(value)})"),
                    )
        targets = set(entry_roots)
        self.ctor_class = {
            address: cls
            for cls in classes
            for address in self.family.members[cls]
            if self.symbols.parsed(address).get("name") == "__ct"
        }
        for ctor in sorted(self.ctor_class):
            targets.update(self.ctx.graph["callers"].get(ctor, ()))
        self.entry_roots = entry_roots
        self.targets = targets
        self.holders = _Holders(self.family, self.parameters)
        # Element classes of pointer storage first: every typed load below depends on them.
        two_level = sorted(
            address for address, row in self.symbols.functions.items()
            if any(value.get("kind") == "class" and len(_levels(value)) == 2 for value in (row.get("parsed") or {}).get("params") or [])
        )
        callers = sorted({caller for callee in two_level for caller in self.ctx.graph["callers"].get(callee, ())})
        self.holders.discover_elements(
            {address: _Analysis(self.ctx, self.symbols, address, self.holders) for address in callers if address in self.ctx.size}
        )
        # Every function, callees first, so a caller sees what its callees return.
        graph = self.ctx.graph
        order = sorted(range(len(graph["components"])), key=lambda number: (graph["height"][number], graph["components"][number][0]))
        for number in order:
            for address in sorted(graph["components"][number]):
                if address not in self.ctx.size:
                    continue
                analysis = _Analysis(self.ctx, self.symbols, address, self.holders)
                roots = self._roots(address, analysis)
                self.holders.compute_return(address, analysis, roots)
                if address in targets or roots:
                    analysis.states = {}
                    self.analyses[address] = analysis
                    self.roots[address] = roots
                    for call in analysis.calls:
                        self.calls_by_site[call["site"]] = call["callee"]

    def _roots(self, address: int, analysis: _Analysis) -> dict[Any, tuple[tuple[str, ...], str, str]]:
        """Typed roots of one function: entry roots, constructed allocations, and family pointers holders prove."""

        roots = dict(self.entry_roots.get(address, {}))
        for call in analysis.calls:
            if call["callee"] not in self.ctor_class:
                continue
            a0 = call["arguments"].get("a0")
            if a0 is None or a0[1] != 0 or a0[0][0] != "res":
                continue
            self._construction(address, analysis, roots, call, a0[0])
        for term, info in sorted(analysis.holds.items(), key=lambda item: (_hold_site(item[1]), str(item[0]))):
            shape, cls = term[2]
            if shape == "ptr" and cls in self.family.classes and term not in roots:
                short = f"{'held' if info[0] == 'load' else 'return'}@0x{_hold_site(info):x}"
                roots[term] = (cls, short, self.holders.hold_proof(address, analysis, term))
        return roots

    def param_type(self, function: int, register: str) -> str | None:
        if function not in self.param_types:
            parsed = self.symbols.parsed(function)
            types: dict[str, str] = {}
            if parsed:
                has_this = bool(parsed.get("qualifier")) and self.receivers.proof(function) is not None
                if not parsed.get("qualifier") or has_this:
                    rows, _complete = parameter_registers(parsed.get("params"), has_this, self.symbols.scalars)
                    types = {name: render_type(value) for name, value in rows}
                    if has_this:
                        types["a0"] = f"{_qualified(parsed['qualifier'])} * this"
            self.param_types[function] = types
        return self.param_types[function].get(register)

    def _locate(self, function: int, address: Any) -> tuple[tuple[str, ...], int, tuple, list[Any]] | None:
        """(class, offset, root, path) for an address value, or None.

        An empty path is a direct access.  Each int in the path is a class
        (or pointee) offset a pointer was loaded from; "[i]" marks an unknown
        index added to the pointer before the access.
        """

        if address is None:
            return None
        term, k = address
        root = self.roots.get(function, {}).get(term)
        if root is not None:
            return root[0], k, root, []
        if term[0] == "ld":
            inner = self._locate(function, term[1])
            if inner is not None:
                cls, offset, how, path = inner
                return cls, k, how, path + [offset]
        if term[0] == "ix":
            inner = self._locate(function, term[1])
            if inner is not None:
                cls, offset, how, path = inner
                return cls, offset + k, how, path + ["[i]"]
        return None

    def where(self, address: Any, function: int) -> str:
        located = self._locate(function, address)
        if located is None:
            return _describe(address, self, function)
        cls, offset, _root, path = located
        return f"{_qualified(cls)}{_path_text(path)}+{_hex(offset)}"

    def _attribute(self) -> None:
        for address, analysis in sorted(self.analyses.items()):
            for event in analysis.memory:
                self._memory_site(address, event)
            for call in analysis.calls:
                self._call_sites(address, call)
            for use in analysis.uses:
                self._use_site(address, use)
            roots = self.roots.get(address, {})
            self.functions[address] = {
                "function": _hex(address),
                "name": self.symbols.readable(address),
                "roots": sorted(
                    (
                        {
                            "register": GPR[term[1]] if term[0] == "arg" else short if term[0] == "hold" else f"call@0x{term[1]:x}",
                            "class": _qualified(cls),
                            "proof": how,
                        }
                        for term, (cls, short, how) in roots.items()
                    ),
                    key=lambda row: (row["register"], row["class"]),
                ),
                "unattributed_accesses": [_hex(site) for site in analysis.unattributed],
            }

    def _construction(self, function: int, analysis: _Analysis, roots: dict, call: dict[str, Any], term: tuple) -> None:
        """Type a call result that reaches a family constructor."""

        site = term[1]
        ctor_cls = self.ctor_class[call["callee"]]
        candidates = {ctor_cls}
        stored = []
        for event in analysis.memory:
            value = event["value"]
            if event["store"] and event["address"][0] == term and value is not None and value[0] == ("sym",):
                cls = self.family.vtable_class.get(value[1])
                if cls is not None:
                    candidates.add(cls)
                    stored.append(f"{self.ctx.object_for(value[1])} at +{_hex(event['address'][1])} @0x{event['site']:x}")
        most = [cls for cls in candidates if all(self.family.derives(cls, other) for other in candidates)]
        allocation = next((row for row in analysis.calls if row["site"] == site), None)
        allocator = self.symbols.parsed(allocation["callee"]) if allocation else {}
        is_new = allocator.get("name") in _ALLOCATORS and not allocator.get("qualifier")
        size_value = allocation["arguments"].get("a0") if allocation and is_new else None
        size = size_value[1] if _is_const(size_value) else None
        record = {
            "function": _hex(function),
            "function_name": self.symbols.readable(function),
            "allocation_site": _hex(site),
            "allocator": self.symbols.readable(allocation["callee"]) if allocation else None,
            "size": size,
            "constructor_site": _hex(call["site"]),
            "constructor": self.symbols.readable(call["callee"]),
            "vtable_stores": sorted(stored),
        }
        if len(most) != 1:
            self.unresolved[ctor_cls].append(
                {
                    "function": _hex(function),
                    "name": self.symbols.readable(function),
                    "reason": f"object at call @0x{site:x} is constructed as {_qualified(ctor_cls)} but receives "
                    f"vtables of unrelated classes ({', '.join(sorted(_qualified(cls) for cls in candidates))})",
                }
            )
            return
        cls = most[0]
        record["class"] = _qualified(cls)
        if term in roots and roots[term][0] != cls and self.family.derives(roots[term][0], cls):
            return
        roots[term] = (
            cls,
            f"new@0x{site:x}" if is_new else f"call@0x{site:x}",
            f"{record['allocator']}({_hex(size) if size is not None else '?'}) @0x{site:x} constructed by "
            f"{record['constructor']} @0x{call['site']:x}" + (f", vtable {', '.join(sorted(stored))}" if stored else ""),
        )
        if is_new and allocator.get("name") == "__nw" and size is not None:
            self.allocations[cls].append(record)
        else:
            self.constructions[cls].append(record)

    def _site_row(self, function: int, site: int, root: tuple, **fields: Any) -> dict[str, Any]:
        row = {
            "function": _hex(function),
            "function_name": self.symbols.readable(function),
            "site": _hex(site),
            "insn": self.ctx.text(site).split("  ;")[0],
            "root": root[1],
        }
        row.update({key: value for key, value in fields.items() if value is not None})
        return row

    def _add(self, cls: tuple[str, ...], offset: int, row: dict[str, Any]) -> None:
        self.sites[cls].append({"offset": offset, **row})

    def _memory_site(self, function: int, event: dict[str, Any]) -> None:
        located = self._locate(function, event["address"])
        if located is None:
            return
        cls, offset, root, path = located
        value = event["value"]
        fields: dict[str, Any] = {"access": "store" if event["store"] else "load"}
        if event["store"]:
            fields["value"] = _describe(value, self, function)
            if (
                value is not None
                and value[0][0] == "bits"
                and value[0][1][0][1] == event["address"]
                and value[0][1][0][2] == event["width"]
            ):
                fields["bitfield"] = _bitfield(value)
            if value is not None and value[0] == ("sym",):
                obj = self.ctx.object_for(value[1]) or ""
                if obj.startswith("__vt__"):
                    fields["vtable_store"] = obj
            if _is_const(value):
                fields["constant"] = value[1]
            if value is not None and value[0][0] == "ld" and value[1] == 0:
                source = self._locate(function, value[0][1])
                if source is not None and not source[3]:
                    fields["copy_of"] = f"{_qualified(source[0])}+{_hex(source[1])}"
        if path and isinstance(path[0], int):
            fields.update(
                access=f"deref-{fields['access']}",
                through=_path_text(path[1:]) + f"+{_hex(offset)}",
                pointee_width=event["width"],
                pointee_kind=event["kind"],
            )
            self._add(cls, path[0], {**self._site_row(function, event["site"], root, **fields), "pointer": True})
            return
        fields.update(width=event["width"], kind=event["kind"], signed=event["signed"])
        if path:  # this + index: an element of an array inside the object
            fields.update(indexed=True, access=f"indexed-{fields['access']}")
        self._add(cls, offset, self._site_row(function, event["site"], root, **fields))

    def _call_sites(self, function: int, call: dict[str, Any]) -> None:
        callee = call["callee"]
        callee_name = self.symbols.readable(callee) if callee is not None else "indirect"
        tail = True if call["kind"] == "tail" else None
        pointer = call["pointer"]
        if pointer is not None and callee is None:
            located = self._locate(function, pointer)
            if located is not None and located[3] and isinstance(located[3][0], int):
                cls, offset, root, path = located
                self._add(
                    cls,
                    path[0],
                    {
                        **self._site_row(
                            function, call["site"], root, access="indirect-call",
                            through=_path_text(path[1:]) + f"+{_hex(offset)}",
                        ),
                        "pointer": True,
                    },
                )
        for register, value in sorted(call["arguments"].items(), key=lambda item: _register_order(item[0])):
            parameter = self.parameters.of(callee, register)
            located = None if value[0][0] == "ld" and value[1] == 0 else self._locate(function, value)
            if located is not None:
                cls, offset, root, path = located
                fields = {"callee": callee_name, "register": register, **parameter, "tail": tail}
                if path and isinstance(path[0], int):
                    fields.update(access="pointer-passed", through=_path_text(path[1:]) + f"+{_hex(offset)}")
                    self._add(cls, path[0], {**self._site_row(function, call["site"], root, **fields), "pointer": True})
                elif not path and offset == 0:
                    fields["access"] = "object-passed"
                    self.object_passes[cls].append(self._site_row(function, call["site"], root, **fields))
                else:
                    fields["access"] = "address-passed"
                    if path:
                        fields["indexed"] = True
                    self._add(cls, offset, self._site_row(function, call["site"], root, **fields))
                continue
            if value[0][0] != "ld" or value[1] != 0:
                continue
            loaded = self._locate(function, value[0][1])
            if loaded is None:
                continue
            cls, offset, root, path = loaded
            term = value[0]
            fields = {"access": "value-passed", "callee": callee_name, "register": register, **parameter, "tail": tail}
            if path and isinstance(path[0], int):
                fields.update(through=_path_text(path[1:]) + f"+{_hex(offset)}", pointee_width=term[2], pointee_kind=term[3])
                self._add(cls, path[0], {**self._site_row(function, call["site"], root, **fields), "pointer": True})
            else:
                fields.update(width=term[2], kind=term[3], signed=term[4])
                self._add(cls, offset, self._site_row(function, call["site"], root, **fields))

    def _use_site(self, function: int, use: dict[str, Any]) -> None:
        value = use["value"]
        term = value[0]
        source = term if term[0] == "ld" else term[1][0]
        located = self._locate(function, source[1])
        if located is None:
            return
        cls, offset, root, path = located
        fields: dict[str, Any] = {"access": "use", "use": use["how"]}
        if term[0] == "bits":
            fields["bits"] = " ".join(f"{op} {_hex(arg) if isinstance(arg, int) else arg}" for op, arg in term[2])
            window = source_bits(value)
            if window is not None and window != (1 << (8 * source[2])) - 1:
                fields["field_bits"] = _hex(window)  # a whole-field window is a plain value use
        elif use["how"].startswith("mask "):
            fields["field_bits"] = _hex(int(use["how"].split()[1], 16) & ((1 << (8 * source[2])) - 1))
        if path and isinstance(path[0], int):
            fields.update(through=_path_text(path[1:]) + f"+{_hex(offset)}", pointee_width=source[2], pointee_kind=source[3])
            self._add(cls, path[0], {**self._site_row(function, use["site"], root, **fields), "pointer": True})
            return
        fields.update(width=source[2], kind=source[3], signed=source[4])
        if path:
            fields["indexed"] = True
        self._add(cls, offset, self._site_row(function, use["site"], root, **fields))


def _describe(value: Any, collector: _Collector, function: int) -> str:
    if value is None:
        return "unknown"
    term, k = value
    suffix = f"+{_hex(k)}" if k else ""
    if term == ("const",):
        return f"const {_hex(k)}" if not -10 <= k <= 10 else f"const {k}"
    if term == ("sym",):
        return f"&{collector.ctx.object_for(k) or collector.ctx.label(k)}"
    if term == ("sp",):
        return f"stack sp{'+' if k >= 0 else '-'}0x{abs(k):x}"
    if term[0] == "arg":
        typed = collector.param_type(function, GPR[term[1]])
        return f"entry {GPR[term[1]]}" + (f" ({typed})" if typed else "") + suffix
    if term[0] == "farg":
        typed = collector.param_type(function, f"f{term[1]}")
        return f"entry f{term[1]}" + (f" ({typed})" if typed else "")
    if term[0] == "res":
        return f"result of {collector.symbols.readable(collector.calls_by_site.get(term[1]))} @0x{term[1]:x}" + suffix
    if term[0] == "hold":
        shape, cls = term[2]
        what = "pointer into storage of" if shape == "array" else "typed"
        if term[1][0] == "res":
            source = f"result of {collector.symbols.readable(collector.calls_by_site.get(term[1][1]))} @0x{term[1][1]:x}"
        elif term[1][0] == "elem":
            source = f"element of {_describe((term[1][1], 0), collector, function)}"
        else:
            source = f"loaded from {collector.where(term[1][1], function)}"
        return f"{what} {_qualified(cls)}* ({source})" + suffix
    if term[0] == "ld":
        return f"loaded {term[2]}-byte {term[3]} from {collector.where(term[1], function)}" + (f", {suffix}" if k else "")
    if term[0] == "ix":
        return f"indexed from {_describe(term[1], collector, function)}" + suffix
    if term[0] == "bits":
        ops = " ".join(f"{op} {_hex(arg) if isinstance(arg, int) else arg}" for op, arg in term[2])
        return f"bits of ({_describe(term[1], collector, function)}): {ops}"
    return "unknown"


def _bitfield(value: Any) -> dict[str, Any]:
    term = value[0]
    width = term[1][0][2]
    full = (1 << (8 * width)) - 1
    cleared = 0
    set_bits = 0
    dynamic = False
    for op, arg in term[2]:
        if op == "and" and isinstance(arg, int):
            cleared |= ~arg & full
        elif op == "or" and isinstance(arg, int):
            set_bits |= arg & full
        else:
            dynamic = True
    return {
        "ops": " ".join(f"{op} {_hex(arg & full) if isinstance(arg, int) else arg}" for op, arg in term[2]),
        "field_mask": _hex(cleared | set_bits),
        "set": _hex(set_bits),
        "dynamic": dynamic,
    }


# -- report -----------------------------------------------------------------


DIRECT_ACCESSES = ("load", "store", "use", "value-passed", "indexed-load", "indexed-store")


def _subobjects(rows: list[dict[str, Any]], sizes: dict[str, list[int]]) -> list[tuple[int, int, str]]:
    """(offset, size, type) of objects whose address is passed to a typed callee.

    The size is the DWARF byte_size of the parameter's class name (template
    arguments dropped, as DWARF 1 names them) when every record agrees.
    """

    found = set()
    for row in rows:
        if row["access"] != "address-passed" or row.get("indexed") or not row.get("parameter_type"):
            continue
        text = row["parameter_type"].replace(" * (receiver)", "").replace(" const", "").rstrip("*& ")
        name = template_base(text).split("::")[-1]
        known = sizes.get(name)
        if known and len(known) == 1 and known[0] > 0:
            found.add((row["offset"], known[0], text))
    return sorted(found)


def _summaries(rows: list[dict[str, Any]], sizes: dict[str, list[int]], size: int | None = None) -> list[dict[str, Any]]:
    by_offset: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_offset[row["offset"]].append(row)
    extents = sorted(
        {(row["offset"], row["width"]) for row in rows if row.get("width") and row["access"] in DIRECT_ACCESSES and not row.get("indexed")}
    )
    subobjects = _subobjects(rows, sizes)
    result = []
    for offset in sorted(by_offset):
        sites = sorted(
            by_offset[offset],
            key=lambda row: (int(row["function"], 16), int(row["site"], 16), row["access"], row.get("register", "")),
        )
        direct = [row for row in sites if row["access"] in DIRECT_ACCESSES]
        widths = sorted({row["width"] for row in direct if row.get("width")})
        kinds = sorted({row["kind"] for row in direct if row.get("kind")})
        typed_kinds = {kind for kind in kinds if kind not in NEUTRAL_KINDS}
        inside = sorted(f"{text}@{_hex(start)}/{_hex(size)}" for start, size, text in subobjects if start < offset < start + size)
        conflicts = []
        if len(widths) > 1:
            conflicts.append(f"widths {widths}")
        if len(typed_kinds) > 1:
            conflicts.append(f"kinds {sorted(typed_kinds)}")
        overlaps = sorted({f"{_hex(other)}+{width}" for other, width in extents if other < offset < other + width})
        if overlaps:
            conflicts.append(f"inside wider access {overlaps}")
        if size is not None and offset >= size:
            conflicts.append(f"beyond the allocation size {_hex(size)}")
        result.append(
            {
                "offset": offset,
                "widths": widths,
                "kinds": kinds,
                "signed": sorted({str(row["signed"]).lower() for row in direct if row.get("signed") is not None}),
                "pointer": any(row.get("pointer") for row in sites),
                "indexed": any(row.get("indexed") for row in sites),
                "parameter_types": sorted({row["parameter_type"] for row in sites if row.get("parameter_type")}),
                "constants": sorted({row["constant"] for row in sites if "constant" in row}),
                "vtable_stores": sorted({row["vtable_store"] for row in sites if "vtable_store" in row}),
                "bitfield_masks": sorted(
                    {row["bitfield"]["field_mask"] for row in sites if "bitfield" in row}
                    | {row["field_bits"] for row in sites if "field_bits" in row}
                ),
                "inside_subobject": inside,
                "conflicts": conflicts,
                "site_count": len(sites),
                "sites": sites,
            }
        )
    return result


def class_layout(root: Path, name: str, with_derived: bool = False) -> dict[str, Any]:
    """Deterministic layout evidence for ``name``, its RTTI bases and (optionally) derived classes."""

    family = _Family(root, name, with_derived)
    collector = _Collector(family)
    sizes = dwarf_sizes(root)
    classes = []
    order = {"requested": 0, "base": 1, "derived": 2}
    for cls, role in sorted(family.classes.items(), key=lambda item: (order[item[1]], item[0])):
        members = []
        for address in family.members[cls]:
            row = family.symbols.functions[address]
            members.append(
                {
                    "address": _hex(address),
                    "size": row["size"],
                    "mangled": row["mangled"],
                    "name": family.symbols.readable(address),
                    "receiver": family.receivers.proof(address),
                    "virtual_slots": sorted(family.receivers.vtable_slots.get(address, [])),
                }
            )
        statics = [
            {"address": _hex(row["address"]), "size": row["size"], "name": row["name"]}
            for row in family.symbols.objects
            if row["parsed"] and row["parsed"].get("params") is None and tuple(row["parsed"]["qualifier"]) == cls
            and not row["name"].startswith(("__vt__", "__RTTI__"))
        ]
        base_calls = []
        for address in family.members[cls]:
            if family.symbols.parsed(address).get("name") != "__ct" or address not in collector.analyses:
                continue
            for call in collector.analyses[address].calls:
                a0 = call["arguments"].get("a0")
                if call["callee"] in collector.ctor_class and call["callee"] != address and a0 is not None and a0[0] == ("arg", 4):
                    base_calls.append(
                        {
                            "constructor": _hex(address),
                            "site": _hex(call["site"]),
                            "calls": family.symbols.readable(call["callee"]),
                            "class": _qualified(collector.ctor_class[call["callee"]]),
                            "this_adjustment": a0[1],
                        }
                    )
        allocations = sorted(collector.allocations.get(cls, []), key=lambda row: (row["function"], row["allocation_site"]))
        allocated = sorted({row["size"] for row in allocations})
        offsets = _summaries(collector.sites.get(cls, []), sizes, allocated[0] if len(allocated) == 1 else None)
        classes.append(
            {
                "class": _qualified(cls),
                "components": list(cls),
                "mangled_qualifier": mangled_qualifier(list(cls)),
                "role": role,
                "size_evidence": allocated,
                "allocations": allocations,
                "constructions": sorted(collector.constructions.get(cls, []), key=lambda row: (row["function"], row["allocation_site"])),
                "rtti": family.rtti_records(cls),
                "bases": [{"class": _qualified(base), "offset": offset} for base, offset in family.bases(cls)],
                "base_constructor_calls": sorted(base_calls, key=lambda row: (row["constructor"], row["site"])),
                "vtable": family.vtable(cls),
                "members": members,
                "statics": statics,
                "object_passes": sorted(
                    collector.object_passes.get(cls, []),
                    key=lambda row: (int(row["function"], 16), int(row["site"], 16), row.get("register", "")),
                ),
                "offsets": offsets,
                "conflicts": [{"offset": row["offset"], "conflicts": row["conflicts"]} for row in offsets if row["conflicts"]],
                "unresolved": sorted(collector.unresolved.get(cls, []), key=lambda row: (row["function"], row["reason"])),
            }
        )
    analyzed = [collector.functions[address] for address in sorted(collector.functions)]
    holders = collector.holders
    return {
        "kind": LAYOUT_KIND,
        "schema_version": LAYOUT_SCHEMA,
        "target": {"source_sha256": REFERENCE_SHA256},
        "class": _qualified(family.requested),
        "with_derived": with_derived,
        "classes": classes,
        "functions": analyzed,
        "holders": {
            "element_storage": [
                {"storage": f"{record}+{_hex(offset)}", "element": f"{_qualified(row['class'])}*", "proofs": row["proofs"]}
                for (record, offset), row in sorted(holders.elements.items())
            ],
            "element_conflicts": [
                {"storage": f"{record}+{_hex(offset)}", "elements": row}
                for (record, offset), row in sorted(holders.element_conflicts.items())
            ],
            "typed_returns": [
                {
                    "function": _hex(address),
                    "name": family.symbols.readable(address),
                    "returns": f"{_qualified(fact[1][1])}*",
                    "proof": holders.return_proofs[address],
                }
                for address, fact in sorted(holders.returns.items())
                if fact[0] == "type" and fact[1][0] == "ptr" and fact[1][1] in family.classes
            ],
        },
        "summary": {
            "class_count": len(classes),
            "function_count": len(analyzed),
            "site_count": sum(row["site_count"] for cls in classes for row in cls["offsets"]),
            "unattributed_access_count": sum(len(row["unattributed_accesses"]) for row in analyzed),
            "conflict_offsets": {cls["class"]: [_hex(row["offset"]) for row in cls["conflicts"]] for cls in classes},
        },
        "method": [
            "a0 is this only in members whose receiver is proven (constructor, destructor, const, vtable slot, "
            "an argument register read beyond a static function's parameters, a member operator other than "
            "new/delete, or a DWARF this parameter)",
            "every call row records the callee's parameter_type for its register, no_parameter when the settled "
            "parameter list does not use the register, or parameter_unknown with the reason (an unproven receiver "
            "is typed only where its member and static readings agree)",
            "typed roots: single-level pointer/reference parameters of a family class in the mangled signature; "
            "call results passed to a family constructor, typed as the most derived of that constructor's class "
            "and any family vtable the function stores into the object",
            "holder roots (held@load site, return@call site; each function row gives the proof): a 4-byte load "
            "of a DWARF member or global typed as a pointer to a family class, from a pointer typed as its holder "
            "class (this, a mangled parameter or another holder; every DWARF record of the holder agreeing); an "
            "element of pointer storage whose DWARF type lost the element type (std::vector<T *> data_ is "
            "unsigned int *), typed by code passing that storage plus an index as a mangled T ** or T *& "
            "parameter (holders.element_storage; disagreeing proofs refuse the storage); a call result when every "
            "exit of the callee returns NULL or a pointer of one proven class (holders.typed_returns); a "
            "function-local static read back after a store, when only that function's direct loads and stores "
            "reference it",
            "every function is analyzed, callees first; loads from family objects keep their own attribution",
            "values follow register copies, constant offsets, stack spills and reloads (a call that receives a "
            "stack address forgets the slots at or above it), loads, and calls (EE ABI clobbers; a call returns "
            "the caller's a0 plus k when every exit of the callee returns its entry a0 plus k)",
            "a by-value parameter whose mangled class is a DWARF enumeration (no composite record of that name) "
            "takes one GPR, so it settles the registers after it",
            "joins keep a value only when every path agrees, except that one pointer at different offsets "
            "becomes that pointer plus an index; an access whose base is unknown is unattributed",
            "kind 'zero' is a GPR store of constant 0 and 'fpr-copy' a word moved through an FPR that no float "
            "instruction reads: neither proves int or float",
            "object-passed rows pass the object pointer itself (offset 0, no load); they are listed per class, "
            "not as field evidence",
        ],
    }


def _site_text(site: dict[str, Any]) -> str:
    detail = [site["access"]]
    for key in ("width", "kind", "pointee_width", "pointee_kind"):
        if site.get(key) is not None:
            detail.append(f"{key}={site[key]}")
    if site.get("signed") is not None:
        detail.append(f"signed={str(site['signed']).lower()}")
    for key in ("through", "value", "copy_of", "use", "bits", "field_bits", "register", "parameter_type", "parameter_unknown"):
        if site.get(key):
            detail.append(f"{key}={site[key]}")
    if site.get("no_parameter"):
        detail.append("no_parameter")
    if str(site.get("access", "")).endswith("passed"):
        detail.append(f"callee={site['callee']}")
    if site.get("bitfield"):
        detail.append(f"bitfield={site['bitfield']['ops']} mask={site['bitfield']['field_mask']}")
    if site.get("tail"):
        detail.append("tail")
    return f"{site['site']} {site['insn']} | {' '.join(detail)} | {site['root']} in {site['function_name']}"


def render_layout(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# code-derived layout evidence: {report['class']}" + (" (with derived classes)" if report["with_derived"] else ""),
        f"functions analyzed {summary['function_count']}, attributed sites {summary['site_count']}, "
        f"unattributed accesses {summary['unattributed_access_count']}",
    ]
    lines.extend(f"method: {text}" for text in report["method"])
    for cls in report["classes"]:
        lines.append("")
        lines.append(f"## {cls['class']} [{cls['role']}] mangled {cls['mangled_qualifier']}")
        lines.append(f"size evidence: {', '.join(_hex(size) for size in cls['size_evidence']) or 'none'}")
        for row in cls["allocations"]:
            lines.append(
                f"  allocation {row['allocator']}({_hex(row['size'])}) @{row['allocation_site']} -> {row['constructor']} "
                f"@{row['constructor_site']} in {row['function_name']}"
                + (f"; vtable {', '.join(row['vtable_stores'])}" if row["vtable_stores"] else "")
            )
        for row in cls["constructions"]:
            lines.append(
                f"  construction: result of {row['allocator'] or 'unknown'} @{row['allocation_site']} -> {row['constructor']} "
                f"@{row['constructor_site']} in {row['function_name']}"
            )
        for record in cls["rtti"]:
            bases = ", ".join(
                f"{base['class'] or base['rtti']}@{_hex(base['offset'])}{' (ambiguous)' if base['ambiguous'] else ''}"
                for base in record["bases"]
            ) or "none"
            lines.append(f"rtti {record['name']} {record['address']} name {record['type_name']!r} base list {record['base_list']}: {bases}")
        for row in cls["base_constructor_calls"]:
            adjustment = f"+{_hex(row['this_adjustment'])}" if row["this_adjustment"] else ""
            lines.append(f"base constructor call: {row['calls']} with a0 = this{adjustment} @{row['site']} in {row['constructor']}")
        vtable = cls["vtable"]
        if vtable:
            header = vtable["header"]
            type_info = header["type_info"] or {}
            lines.append(
                f"vtable {vtable['name']} {vtable['address']} ({vtable['size']} bytes): +0x0 type_info "
                f"{type_info.get('target', type_info.get('word'))}, +0x4 complete_offset {(header['complete_offset'] or {}).get('word')}"
            )
            for slot in vtable["slots"]:
                lines.append(f"  +{_hex(slot['offset'])} slot {slot['slot']}: {slot.get('function_name', slot['word'])} {slot.get('function', '')}")
        lines.append(f"members ({len(cls['members'])}):")
        for member in cls["members"]:
            lines.append(f"  {member['address']} {member['name']} receiver: {member['receiver'] or 'UNPROVEN'}")
        if cls["statics"]:
            lines.append(
                f"static members ({len(cls['statics'])}): "
                + ", ".join(f"{row['name']}@{row['address']}/{row['size']}" for row in cls["statics"])
            )
        lines.append(f"offsets ({len(cls['offsets'])}):")
        for row in cls["offsets"]:
            facts = []
            if row["widths"]:
                facts.append("w" + "/".join(str(width) for width in row["widths"]))
            if row["kinds"]:
                facts.append("/".join(row["kinds"]))
            if row["signed"]:
                facts.append("signed=" + "/".join(row["signed"]))
            if row["pointer"]:
                facts.append("pointer")
            if row["indexed"]:
                facts.append("indexed")
            if row["vtable_stores"]:
                facts.append("vptr<-" + ",".join(row["vtable_stores"]))
            if row["constants"]:
                facts.append("const " + ",".join(_hex(value) for value in row["constants"][:8]))
            if row["bitfield_masks"]:
                facts.append("bits " + ",".join(row["bitfield_masks"]))
            if row["parameter_types"]:
                facts.append("typed " + "; ".join(row["parameter_types"][:6]))
            if row["inside_subobject"]:
                facts.append("inside " + "; ".join(row["inside_subobject"]))
            if row["conflicts"]:
                facts.append("CONFLICT " + "; ".join(row["conflicts"]))
            lines.append(f"  +{_hex(row['offset'])} [{row['site_count']} sites] " + " ".join(facts))
            lines.extend(f"      {_site_text(site)}" for site in row["sites"])
        if cls["object_passes"]:
            lines.append(f"object passed whole ({len(cls['object_passes'])}):")
            lines.extend(f"      {_site_text(site)}" for site in cls["object_passes"])
        if cls["unresolved"]:
            lines.append(f"unresolved ({len(cls['unresolved'])}):")
            lines.extend(f"  {row['function']} {row['name']}: {row['reason']}" for row in cls["unresolved"])
    holders = report.get("holders") or {}
    lines.append("")
    lines.append("## holders")
    for row in holders.get("element_storage", []):
        lines.append(f"element storage {row['storage']}: {row['element']}")
        lines.extend(f"      because {proof}" for proof in row["proofs"])
    for row in holders.get("element_conflicts", []):
        lines.append(f"element storage {row['storage']}: REFUSED, proofs disagree")
        for element, proofs in row["elements"].items():
            lines.extend(f"      {element}*: {proof}" for proof in proofs)
    for row in holders.get("typed_returns", []):
        lines.append(f"typed return {row['function']} {row['name']} -> {row['returns']}: {row['proof']}")
    lines.append("")
    lines.append("## functions analyzed")
    for row in report["functions"]:
        roots = "; ".join(f"{root['register']}={root['class']} ({root['proof']})" for root in row["roots"]) or "no family root"
        gaps = row["unattributed_accesses"]
        lines.append(f"  {row['function']} {row['name']}: {roots}" + (f"; unattributed {len(gaps)}: {', '.join(gaps)}" if gaps else ""))
    return "\n".join(lines) + "\n"


def site_index(report: dict[str, Any]) -> dict[str, dict[int, list[dict[str, Any]]]]:
    """class name -> offset -> sites; object passes are listed under offset 0."""

    index: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for cls in report["classes"]:
        rows = {row["offset"]: list(row["sites"]) for row in cls["offsets"]}
        if cls["object_passes"]:
            rows[0] = rows.get(0, []) + list(cls["object_passes"])
        index[cls["class"]] = rows
    return index
