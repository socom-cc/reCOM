"""Signatures derived from a prototype function's Metrowerks mangled symbol (the ``mangled`` group).

Used by ``signatures.py --plan`` for map functions whose prototype counterpart still has Ghidra's
default signature. The mangled name carries the scope and every parameter type; it does not carry
the return type or whether a member is static. Each decision keeps its evidence. The rules were
measured on the 4,311 prototype functions that have a signature and a mangled symbol (worker
``socom-release-mangle-m1``, 2026-11-27): no derived field differed from the prototype's.

Parameters. Each mangled type is spelled as the prototype program spells it (reference and pointer
``T *``, const and volatile dropped, ``wchar_t`` ``ushort``, the EE's 64-bit ``long``
``longlong``, the 128-bit ``1`` ``uint16``, pointer to array ``T[n] *``, a class or enum by the
archive name of its last component at the category ``/project/<scopes>``, ``name@<hash>`` where
DWARF repeated the name). A named type must be the one type of that name in the release (after
``.conflict``), at that category, no C primitive name, with no ``( ) , &``. Withheld: missing or
ambiguous types, function and member pointers (their types are anonymous ``@subroutine@`` ones),
arrays, classes by value of another size than 1, 2, 4 or 8 bytes, ``double``/``long double``/the
128-bit type by value (Metrowerks' passing of them is not proven against Ghidra's r5900
``__stdcall``, which puts 16-byte values on the stack), more than eight GPR or FPR arguments.

``this``, the first evidence that applies decides: constructor or destructor; const or volatile
member; a slot of a ``__vt__`` table of the prototype; no scope (a free function, none); the scope
is an archive category and no type (a namespace, none); ``operator new``/``delete`` (static); the
release function's own code reads the entry value of the GPR after the declared GPR parameters
(a0 when there is none). Otherwise undecided, and the function is withheld. ``@N@`` this-adjusting
stubs are withheld (a0 is a base part).

Return: constructors and destructors ``void *`` (they return this in v0; a destructor also takes
a last ``short __dtor_flags``); a conversion operator its type; the one return the signed
overrides of the same vtable slot (same name, parameters and slot index) agree on; else
``undefined``.

Storage is predicted the Metrowerks way: integer-class arguments in a0-a3, t0-t3 in order (this
first), floats in f12-f19, each register named as Ghidra names the part (``a0_lo:4``, ``a1:8``,
``f12:4``).
"""
from __future__ import annotations

from collections import defaultdict

import mips
import mwmangle as mw
import names

ARGS = tuple(range(4, 12))  # a0-a3, t0-t3
GPR_NAMES = ("a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3")
FPR_NAMES = tuple(f"f{n}" for n in range(12, 20))
ALL = (1 << 32) - 1
CONVENTION = "__stdcall"
NEW_DELETE = frozenset({"operator new", "operator new[]", "operator delete", "operator delete[]"})
DTOR_FLAGS = {"type": "short", "name": "__dtor_flags"}
CLAUSE_PREFIX = names.MANGLED_CLAUSE  # kept by the names step's replan (names.kept_plate)
DERIVED_MARK = " [derived from the mangled symbol]"  # ends the record value of a derived prototype

# Builtin codes -> Ghidra text. Measured on the prototype program: v b c Uc s Us i Ui Ul f w 1.
# By the compiler spec (r5900.cspec: long_size 8, GPR pentries up to 8 bytes, sign-extended) and
# the DWARF import (FT_long is 8 bytes, spelled longlong): l, Sl, x, Ux, Sx are longlong or
# ulonglong in one GPR; Sc is schar, Ss short, Si int.
BUILTIN_TEXT = {
    ("v", ""): "void", ("b", ""): "bool", ("c", ""): "char", ("c", "S"): "schar", ("c", "U"): "uchar",
    ("s", ""): "short", ("s", "U"): "ushort", ("s", "S"): "short", ("i", ""): "int", ("i", "U"): "uint",
    ("i", "S"): "int", ("l", ""): "longlong", ("l", "U"): "ulonglong", ("l", "S"): "longlong",
    ("x", ""): "longlong", ("x", "U"): "ulonglong", ("x", "S"): "longlong", ("f", ""): "float",
    ("d", ""): "double", ("w", ""): "ushort", ("1", ""): "uint16",
}
BUILTIN_SIZE = {"bool": 1, "char": 1, "schar": 1, "uchar": 1, "short": 2, "ushort": 2, "int": 4, "uint": 4,
                "longlong": 8, "ulonglong": 8, "float": 4, "double": 8, "uint16": 16}
NOT_BY_VALUE = {"double": "double by value: Metrowerks' passing is not proven",
                "uint16": "128-bit integer by value: Ghidra's r5900 __stdcall puts 16 bytes on the stack, "
                          "Metrowerks a 128-bit GPR"}


class Withheld(Exception):
    def __init__(self, group: str, reason: str, details: dict | None = None):
        super().__init__(reason)
        self.group, self.reason, self.details = group, reason, details


# --- the prototype's facts ------------------------------------------------------------------

class Facts:
    """Mangled FUNC symbols, sizes and vtable slots of the prototype ELF."""

    def __init__(self, image):
        self.image = image
        self.symbols: dict[int, list[str]] = defaultdict(list)
        for s in sorted(image.symbols, key=lambda s: (s.address, s.name)):
            if s.kind == 2 and s.size and image.contains(s.address) and s.name not in self.symbols[s.address]:
                self.symbols[s.address].append(s.name)
        self.slots: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for s in image.symbols:
            if s.name.startswith("__vt__") and s.size >= 12:
                for i in range(2, s.size // 4):
                    target = image.word(s.address + 4 * i)
                    if target in self.symbols:
                        self.slots[target].append((s.name, i - 2))
        self.families: dict[tuple, list[int]] = defaultdict(list)
        for address in sorted(self.slots):
            try:
                parts = self.parts(address)
            except Withheld:
                continue
            for key in family_keys(address, parts, self):
                self.families[key].append(address)

    def parts(self, address: int) -> dict:
        """``function_parts`` of the mangled symbols at ``address`` (all must agree)."""

        found = []
        for name in self.symbols.get(address, []):
            try:
                structured = mw.demangle_function(name)
            except mw.MangleError as exc:
                raise Withheld("symbol", f"the symbol {name} does not parse: {exc}") from exc
            if structured:
                parts = mw.function_parts(structured)
                parts["symbol"] = name
                found.append(parts)
        if not found:
            raise Withheld("symbol", "no mangled symbol at the counterpart")
        readings = {(repr(p["params"]), p["const"], p["volatile"], p["varargs"]) for p in found}
        if len(readings) > 1:
            raise Withheld("symbol", "the mangled aliases at the counterpart disagree: "
                           + ", ".join(p["symbol"] for p in found))
        return found[0]


def family_keys(address: int, parts: dict, facts: Facts) -> list[tuple]:
    params = repr(parts["params"]) + ("e" if parts["varargs"] else "")
    return [(parts["name"], params, parts["const"], index) for _, index in facts.slots.get(address, [])]


# --- types ----------------------------------------------------------------------------------

class Types:
    """The release program's type table (``signatures.type_table``), indexed for the rules."""

    def __init__(self, table: dict, strip_conflict, c_primitives):
        self.table = table
        self.strip = strip_conflict
        self.c_primitives = c_primitives
        self.by_category: dict[str, list[str]] = defaultdict(list)
        self.paths = set()
        for name, rows in table.items():
            for path, _ in rows:
                self.by_category[path.rsplit("/", 1)[0]].append(name)
                self.paths.add(path)
        self.categories = {p.rsplit("/", i)[0] for p in self.paths for i in range(1, p.count("/"))}

    def resolve(self, node: dict) -> tuple[str, int | None]:
        base, category = mw.type_name(node), mw.type_category(node)
        here = [n for n in self.by_category.get(category, []) if self.strip(n) == base or n.startswith(base + "@")]
        if not here:
            elsewhere = [p for n, v in self.table.items() if self.strip(n) == base for p, _ in v]
            if elsewhere:
                raise Withheld("type", f"type {category}/{base} is not in the release; its only type of that "
                                       f"name is {elsewhere[0]}")
            raise Withheld("type", f"missing type {category}/{base}")
        if len(here) > 1:
            raise Withheld("type", f"type {base} names {len(here)} types at {category}")
        name = here[0]
        twins = [p for n, v in self.table.items() if self.strip(n) == self.strip(name) for p, _ in v]
        if len(twins) > 1:
            raise Withheld("type", f"type name {name} names {len(twins)} types in the release")
        if " ".join(name.split()) in self.c_primitives:
            raise Withheld("type", f"type name {name} is a C primitive name (the parser takes the built-in)")
        if any(c in name for c in "(),&"):
            raise Withheld("type", f"type name {name} holds ( ) , or & (the signature parser cannot read it)")
        return name, self.table[name][0][1]

    def scope_kind(self, parts: dict) -> str:
        if not parts["scope_nodes"]:
            return "none"
        node = {"t": "named", "name": parts["scope_nodes"]}
        path = mw.type_category(node) + "/" + mw.type_name(node)
        if path in self.paths:
            return "class"
        if path in self.categories:
            return "namespace"
        return "unknown"


def type_text(node: dict, types: Types, top: bool = True) -> tuple[str, int]:
    """(Ghidra type text, size in bytes) of one mangled parameter type, or ``Withheld``."""

    kind = node["t"]
    if kind == "builtin":
        key = (node["code"], node.get("sign", ""))
        if key not in BUILTIN_TEXT:
            raise Withheld("type", f"no Ghidra spelling for {mw.render_type(node)}")
        text = BUILTIN_TEXT[key]
        if top and text in NOT_BY_VALUE:
            raise Withheld("type", NOT_BY_VALUE[text])
        return text, BUILTIN_SIZE.get(text, 0)
    if kind in ("pointer", "reference"):
        target = node["to"]
        if target["t"] in ("function", "member_pointer"):
            raise Withheld("type", f"function or member pointer {mw.readable_type(node)}: its type is anonymous")
        if target["t"] == "array":
            inner, _ = type_text(target["of"], types, False)
            return f"{inner}[{target['size']}] *", 4
        if target["t"] == "builtin" and target["code"] == "v":
            return "void *", 4
        inner, _ = type_text(target, types, False)
        return inner + " *", 4
    if kind == "named":
        name, size = types.resolve(node)
        if top and size not in (1, 2, 4, 8):
            raise Withheld("type", f"{name} by value has {size} bytes (only 1, 2, 4 or 8 go in one GPR)")
        return name, size or 0
    raise Withheld("type", f"a {kind} parameter ({mw.readable_type(node)})")


# --- the code rule --------------------------------------------------------------------------

def gpr_reads(word: int) -> tuple[int, ...]:
    """General registers an R5900 instruction reads (loads/stores: base and stored value)."""

    op = word >> 26
    rs = (word >> 21) & 31
    rt = (word >> 16) & 31
    if op == 0:
        funct = word & 63
        if funct in (0, 2, 3, 0x38, 0x3A, 0x3B, 0x3C, 0x3E, 0x3F):
            return (rt,)
        if funct in (8, 9, 0x11, 0x13, 0x29):  # jr, jalr, mthi, mtlo, mtsa
            return (rs,)
        if funct in (0x0C, 0x0D, 0x0F, 0x10, 0x12, 0x28):  # syscall, break, sync, mfhi, mflo, mfsa
            return ()
        return (rs, rt)
    if op in (1, 6, 7, 0x16, 0x17, 8, 9, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x18, 0x19):
        return (rs,)
    if op in (2, 3, 0x0F):
        return ()
    if op in (4, 5, 0x14, 0x15):
        return (rs, rt)
    if op in (0x10, 0x11, 0x12):  # mtc/ctc/qmtc read rt; others read no GPR
        return (rt,) if rs in (4, 5, 6) else ()
    if op == 0x1C:  # MMI
        return () if (word & 63) in (0x10, 0x12) else (rs, rt)
    if op in (0x1A, 0x1B, 0x1E, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x37, 0x31, 0x36, 0x2F, 0x33,
              0x39, 0x3E):
        return (rs,)
    return (rs, rt)  # stores: base and value


def _is_call(word: int) -> bool:
    return (word >> 26) == 3 or ((word >> 26) == 0 and (word & 0x3F) == 9)


def entry_reads(words, start: int, count: int, base: int) -> dict[int, int]:
    """Argument register (4-11) -> first address where its entry value is read on some path.

    A must-written analysis over the function's own flow (branches, delay and likely slots); a
    call clobbers the caller-saved registers after its delay slot; a register handed on to a call
    unchanged is no read; blocks without a modelled predecessor (jump-table targets) are skipped.
    """

    succ = mips._successors(words, start, count, base)
    state_in = [ALL] * count
    state_in[0] = 0
    changed = True
    while changed:
        changed = False
        for local in range(count):
            word = words[start + local]
            out = state_in[local]
            for register in mips.written_registers(word):
                out |= 1 << register
            if local and _is_call(words[start + local - 1]):
                out |= mips.CALLER_SAVED
            for nxt in succ[local]:
                merged = state_in[nxt] & out
                if nxt and merged != state_in[nxt]:
                    state_in[nxt] = merged
                    changed = True
    found: dict[int, int] = {}
    for local in range(count):
        if state_in[local] == ALL and local:
            continue
        for register in gpr_reads(words[start + local]):
            if register in ARGS and not (state_in[local] >> register) & 1 and register not in found:
                found[register] = base + (start + local) * 4
    return found


def gpr_count(params: list[dict]) -> int:
    return sum(0 if p["t"] == "builtin" and p["code"] == "f" else 1 for p in params)


def code_verdict(parts: dict, reads: dict[int, int]) -> tuple[str | None, str]:
    k = gpr_count(parts["params"])
    if parts["varargs"] or k >= 8:
        return None, "varargs or eight GPR parameters: the code cannot tell"
    highest = max((r - 4 for r in reads), default=-1)
    if highest == k:
        return "this", f"the code reads {GPR_NAMES[k]} at 0x{reads[4 + k]:06x}, the GPR after the declared ones"
    if highest > k:
        return None, f"the code reads {GPR_NAMES[highest]}, beyond the declared GPRs and this"
    return None, "the code reads no GPR beyond the declared ones"


def this_decision(address: int, parts: dict, facts: Facts, types: Types, reads: dict[int, int]) -> tuple[str | None, str]:
    """(``this``, ``static`` or None, the evidence) in the rule order of the module docstring."""

    kind = types.scope_kind(parts)
    if kind == "none":
        return "static", "free function"
    if parts["form"] in ("constructor", "destructor"):
        return "this", parts["form"]
    if parts["const"] or parts["volatile"]:
        return "this", "const member" if parts["const"] else "volatile member"
    if address in facts.slots:
        return "this", f"slot {facts.slots[address][0][1]} of {facts.slots[address][0][0]}"
    if parts["name"] in NEW_DELETE:
        return "static", parts["name"] + " (static)"
    if kind == "namespace":
        return "static", "namespace scope"
    return code_verdict(parts, reads)


# --- the derivation -------------------------------------------------------------------------

def predict_storage(params: list[dict], sizes: list[int]) -> list[str]:
    gprs, fprs, out = iter(GPR_NAMES), iter(FPR_NAMES), []
    for p, size in zip(params, sizes):
        if p["type"] == "float":
            register = next(fprs, None)
            if register is None:
                raise Withheld("storage", "more than eight float arguments")
            out.append(f"{register}:4")
            continue
        register = next(gprs, None)
        if register is None:
            raise Withheld("storage", "more than eight GPR arguments (Metrowerks puts the rest on the stack)")
        if size in (1, 2, 4):
            out.append(f"{register}_lo:{size}")
        elif size == 8:
            out.append(f"{register}:8")
        else:
            raise Withheld("storage", f"a {size}-byte argument in {register}")
    return out


def derive(address: int, facts: Facts, types: Types, release_reads: dict[int, int],
           prototype_reads: dict[int, int] | None, signed_returns: dict[int, str], check_return) -> dict:
    """The derived prototype of the prototype function at ``address``, or ``Withheld``.

    ``signed_returns``: prototype address -> return type text of the signed functions this needs
    (the overrides of the same slot); ``check_return(text)``: the reason a return type cannot be
    written, or None.
    """

    parts = facts.parts(address)
    if parts["thunk_offsets"]:
        raise Withheld("this", f"@{parts['thunk_offsets']}@ this-adjusting stub: a0 is a base part")
    params, sizes = [], []
    for node in parts["params"]:
        text, size = type_text(node, types)
        params.append(text)
        sizes.append(size)
    if parts["varargs"] and not params and parts["form"] not in ("constructor", "destructor"):
        raise Withheld("parameter", "varargs without a fixed parameter: the parser sets varargs only after a comma")
    this, this_why = this_decision(address, parts, facts, types, release_reads)
    out = {"symbol": parts["symbol"], "declaration": parts["declaration"], "form": parts["form"],
           "this": this, "this_evidence": this_why, "release_reads": sorted(GPR_NAMES[r - 4] for r in release_reads)}
    if prototype_reads is not None:
        proto_this, proto_why = this_decision(address, parts, facts, types, prototype_reads)
        out["prototype_bytes_this"] = proto_this
        out["prototype_bytes_evidence"] = proto_why
    if this is None:
        raise Withheld("this", f"this undecided: {this_why}", out)
    rows = []
    if this == "this":
        try:
            receiver, _ = types.resolve({"t": "named", "name": parts["scope_nodes"]})
        except Withheld as exc:
            raise Withheld("receiver", "receiver " + exc.reason) from exc
        rows.append({"type": receiver + " *", "name": "this"})
        sizes = [4] + sizes
    for text in params:
        rows.append({"type": text, "name": f"param_{len(rows) + 1}"})
    if parts["form"] == "destructor":
        rows.append(dict(DTOR_FLAGS))
        sizes.append(2)
    storage = predict_storage(rows, sizes)
    for row, where in zip(rows, storage):
        row["storage"] = where
    ret, ret_why = derive_return(address, parts, facts, types, signed_returns)
    if ret != "undefined":
        reason = check_return(ret)
        if reason:
            ret, ret_why = "undefined", f"return type unknown ({ret_why} gives {ret}, but {reason})"
    out.update({"return": ret, "return_evidence": ret_why, "parameters": rows, "varargs": parts["varargs"]})
    out["clause"] = (f"{CLAUSE_PREFIX}{parts['symbol']}: this from {this_why}" if this == "this"
                     else f"{CLAUSE_PREFIX}{parts['symbol']}: no this ({this_why})")
    out["clause"] += (", return type unknown" if ret == "undefined" else f", return {ret} ({ret_why})")
    if not clause_ok(out["clause"]):
        raise Withheld("plate", f"the plate clause would hold a separator: {out['clause']!r}")
    return out


def derive_return(address: int, parts: dict, facts: Facts, types: Types, signed_returns: dict[int, str]):
    if parts["form"] in ("constructor", "destructor"):
        return "void *", f"a {parts['form']} returns this"
    if parts["form"] == "conversion":
        structured = mw.demangle_function(parts["symbol"])
        try:
            text, _ = type_text(structured["name"]["conversion"], types)
            return text, "a conversion operator returns its type"
        except Withheld:
            pass
    found = set()
    for key in family_keys(address, parts, facts):
        for other in facts.families.get(key, []):
            if other != address and signed_returns.get(other, "undefined") != "undefined":
                found.add(signed_returns[other])
    if len(found) == 1:
        return found.pop(), "the signed overrides of its vtable slot"
    if found:
        return "undefined", "return type unknown (the overrides of its slot disagree)"
    return "undefined", "return type unknown"


def siblings(address: int, facts: Facts) -> list[int]:
    """Prototype functions whose signed return ``derive_return`` would read for ``address``."""

    try:
        parts = facts.parts(address)
    except Withheld:
        return []
    return sorted({o for key in family_keys(address, parts, facts) for o in facts.families.get(key, []) if o != address})


def text_of(ret: str, name: str, params: list[dict], varargs: bool) -> str:
    inside = ", ".join(f"{p['type']} {p['name']}" for p in params)
    if varargs:
        inside += (", " if inside else "") + "..."
    return f"{ret} {name}({inside or 'void'})"


def clause_ok(clause: str) -> bool:
    """A plate clause must not hold the plate's separators."""

    return "; " not in clause and "\n" not in clause and not clause.endswith(".")
