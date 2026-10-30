"""Which vtable slot an indirect call or jump goes through (rules version 21).

The 'call through a void slot family' rule (decision of 2026-10-30) needs the
slot family an indirect ``jalr``/``jr`` reaches.  ``slot_call`` proves it from
the ELF alone, or gives None:

* the jump register is loaded (``lw t9,S(v)``) from a vtable pointer that is
  itself loaded (``lw v,P(o)``) from an object pointer ``o``, each the only
  definition reaching its use;
* ``o`` has a proven static class: the receiver ``this`` (a constructor,
  destructor, const method, a function held in a vtable slot, or one reading
  argument registers beyond its mangled parameters that ``this`` accounts
  for), a mangled class-pointer parameter, or a value reached from one of
  those through DWARF-typed members: a by-value class member or base at a
  constant offset (``addiu``), a pointer member whose DWARF type points to a
  class (``lw``), or an array of such pointers.  A member typed otherwise (an
  integer, ``void *``, ``unsigned long *`` storage) proves nothing;
* the class's own constructor or destructor stores one block of its vtable
  (``__vt__<class>`` + head) at offset ``P`` of ``this``: that is the block
  the vptr at ``P`` points to;
* ``S`` names slot ``(S - 8) / 4`` of that block, whose slot family
  (``recon_draft.slot_families``) holds every override a call through it
  can reach.

Nothing here reads the live program or decides a verdict.
"""

from __future__ import annotations

from typing import Any

from .mwdemangle import demangle
from .type_identity import CALL_CLOBBERED, MOD_POINTER_TO, MOD_REFERENCE_TO, member_offset, parse_subscr, type_ref

CLASS_TAGS = ("class_type", "structure_type")
_QUALIFIERS = (0x03, 0x04)  # const, volatile
_LW, _SW, _ADDIU, _ORI = 0x23, 0x2B, 0x09, 0x0D

_DWARF: dict[int, Any] = {}
_VTABLES: dict[int, dict[str, Any]] = {}
_VPTRS: dict[int, dict[str, dict[int, set[int]]]] = {}
_CALLS: dict[tuple[int, bool, int, int], dict[str, Any] | None] = {}


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _signed32(value: int) -> int:
    return value - (1 << 32) if value & 0x80000000 else value


def _dwarf(ctx: Any) -> Any:
    key = id(ctx)
    if key not in _DWARF:
        from pathlib import Path

        from .recon_facts import _dies_cached
        from .type_plan_evidence import _Dwarf

        path = Path(ctx.elf.path)
        st = path.stat()
        _DWARF[key] = _Dwarf(_dies_cached((str(path), st.st_size, int(st.st_mtime)), str(path)))
    return _DWARF[key]


def _complete(die: Any) -> bool:
    return die is not None and die.tag_name in CLASS_TAGS and (die.integer("byte_size") or 0) > 0


def _definitions(dw: Any, name: str) -> list[Any]:
    """Complete DWARF records of a class by its last name component."""

    return [die for die in dw.by_name.get(name.split("::")[-1], []) if _complete(die) and dw.children(die)]


def _on_class(dw: Any, name: str, die: Any, query: Any) -> Any:
    """``query(die)`` on the record itself when complete, else on every record of the name, which must agree."""

    if _complete(die) and dw.children(die):
        return query(die)
    answers = [query(record) for record in _definitions(dw, name)]
    # Records of one class in several compile units agree on everything but their DIE.
    keys = {None if answer is None else (answer[0], answer[1], answer[3]) for answer in answers}
    return answers[0] if len(keys) == 1 and None not in keys else None


def _resolve(dw: Any, ref: Any, depth: int = 0) -> tuple[int, Any] | None:
    """(pointer levels, base DIE or None for a fundamental type) of a DWARF type reference, through typedefs."""

    if ref is None or depth > 8:
        return None
    modifiers, target, _fund = ref
    if any(m not in (MOD_POINTER_TO, MOD_REFERENCE_TO) + _QUALIFIERS for m in modifiers):
        return None
    levels = sum(1 for m in modifiers if m in (MOD_POINTER_TO, MOD_REFERENCE_TO))
    if target is None:
        return levels, None
    die = dw.die(target)
    if die is None:
        return None
    if die.tag_name == "typedef":
        inner = _resolve(dw, type_ref(die), depth + 1)
        return None if inner is None else (levels + inner[0], inner[1])
    return levels, die


def _size(dw: Any, die: Any) -> int | None:
    """Byte size of a class record (a declaration takes its name's agreeing definitions)."""

    size = die.integer("byte_size") if die is not None else None
    if size:
        return size
    if die is None or not die.string("name"):
        return None
    sizes = {record.integer("byte_size") for record in _definitions(dw, die.string("name"))}
    return sizes.pop() if len(sizes) == 1 else None


def _array(dw: Any, die: Any) -> tuple[int, int, Any] | None:
    """(element count, pointer levels, class DIE) of an array of class pointers, else None."""

    attribute = die.attribute("subscr_data")
    data = attribute.value if attribute else None
    if not isinstance(data, bytes):
        return None
    dims, element = parse_subscr(data)
    if len(dims) != 1 or len(dims[0]) != 4 or not all(isinstance(bound, int) for bound in dims[0][2:]):
        return None
    shaped = _resolve(dw, element)
    if shaped is None or shaped[0] < 1 or not _named_class(shaped[1]):
        return None
    return dims[0][3] - dims[0][2] + 1, shaped[0], shaped[1]


def _named_class(die: Any) -> bool:
    return die is not None and die.tag_name in CLASS_TAGS and bool(die.string("name"))


def _parts(dw: Any, die: Any) -> list[tuple[int, int, str, Any, Any]]:
    """(offset, size, kind, child, type) of the bases and members holding an object or an array by value."""

    parts = []
    for child in dw.children(die):
        if child.tag_name not in ("member", "inheritance"):
            continue
        offset = member_offset(child)
        shaped = _resolve(dw, type_ref(child))
        if offset is None or shaped is None or shaped[0] or shaped[1] is None:
            continue
        target = shaped[1]
        if target.tag_name in CLASS_TAGS:
            size = _size(dw, target)
            if size and size > 1:  # empty bases occupy no storage of their own
                parts.append((offset, size, "base" if child.tag_name == "inheritance" else "member", child, target))
        elif target.tag_name == "array_type" and (array := _array(dw, target)) is not None:
            parts.append((offset, 4 * array[0], "array", child, target))
    return parts


def _containing(parts: list[tuple[int, int, str, Any, Any]], k: int) -> tuple[int, int, str, Any, Any] | None:
    found = [part for part in parts if part[0] <= k < part[0] + part[1]]
    return found[0] if len(found) == 1 else None


def _label(child: Any, target: Any) -> str:
    name = child.string("name")
    kind = target.string("name") or target.tag_name
    return f"{name}:{kind}" if name else f"base {kind}"


def field(dw: Any, die: Any, k: int, depth: int = 0) -> tuple[int, str, Any, str] | None:
    """(pointer levels, class, DIE, how) of the class pointer stored at byte ``k`` of a class record, else None."""

    if depth > 8 or k < 0:
        return None
    exact = [c for c in dw.children(die) if c.tag_name == "member" and member_offset(c) == k]
    if len(exact) > 1:
        return None  # overlapping members (bit-fields or a union)
    if exact:
        child = exact[0]
        shaped = _resolve(dw, type_ref(child))
        if shaped is None or shaped[1] is None:
            return None
        levels, target = shaped
        if levels and _named_class(target):
            return levels, target.string("name"), target, f"{child.string('name')}:{target.string('name')}{'*' * levels}"
        if levels:
            return None
        if target.tag_name == "array_type" and (array := _array(dw, target)) is not None:
            return array[1], array[2].string("name"), array[2], f"{child.string('name')}[0]:{array[2].string('name')}{'*' * array[1]}"
        if _named_class(target):
            inner = _on_class(dw, target.string("name"), target, lambda record: field(dw, record, 0, depth + 1))
            return None if inner is None else (*inner[:3], f"{child.string('name')}.{inner[3]}")
        return None
    part = _containing(_parts(dw, die), k)
    if part is None:
        return None
    offset, _size_, kind, child, target = part
    if kind == "array":
        array = _array(dw, target)
        if (k - offset) % 4:
            return None
        return array[1], array[2].string("name"), array[2], f"{child.string('name')}[{(k - offset) // 4}]:{array[2].string('name')}{'*' * array[1]}"
    inner = _on_class(dw, target.string("name"), target, lambda record: field(dw, record, k - offset, depth + 1))
    return None if inner is None else (*inner[:3], f"{_label(child, target)}.{inner[3]}")


def subobject(dw: Any, die: Any, k: int, depth: int = 0) -> tuple[int, str, Any, str] | None:
    """(pointer levels, class, DIE, how) of the address ``this + k``: a by-value base or member object
    starting at ``k`` (one level), or an array of class pointers starting there (its element type plus one)."""

    if depth > 8 or k <= 0:
        return None
    parts = _parts(dw, die)
    exact = [part for part in parts if part[0] == k]
    if len(exact) == 1:
        _offset, _size_, kind, child, target = exact[0]
        if kind == "array":
            array = _array(dw, target)
            return array[1] + 1, array[2].string("name"), array[2], f"&{child.string('name')}[0]"
        return 1, target.string("name"), target, _label(child, target)
    if exact:
        return None
    part = _containing(parts, k)
    if part is None or part[2] == "array":
        return None
    offset, _size_, _kind, child, target = part
    inner = _on_class(dw, target.string("name"), target, lambda record: subobject(dw, record, k - offset, depth + 1))
    return None if inner is None else (*inner[:3], f"{_label(child, target)}.{inner[3]}")


# -- vtables and the vptr each constructor stores --------------------------------


def vtables(ctx: Any) -> dict[str, Any]:
    """Vtable symbols by class: their blocks (head -> (subobject, slot count)) and the classes by last name."""

    key = id(ctx)
    if key in _VTABLES:
        return _VTABLES[key]
    from .recon_draft import _symbol_class

    rtti = set()
    tables: dict[str, tuple[int, int, str]] = {}
    twice: set[str] = set()
    for symbol in ctx.elf.symbols():
        name = symbol.name or ""
        if not symbol.size:
            continue
        if name.startswith("__RTTI__"):
            rtti.add(symbol.value)
        elif name.startswith("__vt__") and (cls := _symbol_class(name, "__vt__")):
            if cls in tables and tables[cls][0] != symbol.value:
                twice.add(cls)  # two vtables spell one class: neither is provably the object's
            tables.setdefault(cls, (symbol.value, symbol.size, name))
    for cls in twice:
        del tables[cls]
    blocks: dict[str, dict[int, tuple[int, int]]] = {}
    for cls, (address, size, _name) in tables.items():
        heads = [0] + [
            offset for offset in range(8, size, 4)
            if address + offset in ctx.reloc32 and ctx.code.word(address + offset) in rtti
        ]
        blocks[cls] = {
            head: (
                -_signed32(ctx.code.word(address + head + 4)),
                max(0, ((heads[index + 1] if index + 1 < len(heads) else size) - head - 8) // 4),
            )
            for index, head in enumerate(heads)
        }
    by_last: dict[str, list[str]] = {}
    for cls in tables:
        by_last.setdefault(cls.split("::")[-1], []).append(cls)
    _VTABLES[key] = {"tables": tables, "blocks": blocks, "by_last": by_last}
    return _VTABLES[key]


def vtable_class(ctx: Any, name: str) -> str | None:
    """The one vtable class a (possibly unqualified DWARF) class name names, else None."""

    found = vtables(ctx)
    if name in found["tables"]:
        return name
    candidates = found["by_last"].get(name.split("::")[-1], [])
    return candidates[0] if len(candidates) == 1 else None


def vptr_stores(ctx: Any) -> dict[str, dict[int, set[int]]]:
    """Class -> vptr offset -> vtable block heads its own constructors and destructors store there."""

    key = id(ctx)
    if key in _VPTRS:
        return _VPTRS[key]
    from .recon_draft import _function_names, _traces_to_a0_register

    found = vtables(ctx)
    spans = sorted((address, size, cls) for cls, (address, size, _name) in found["tables"].items())
    starts = [span[0] for span in spans]
    import bisect

    result: dict[str, dict[int, set[int]]] = {}
    for row in ctx.refs:
        if row.get("target") is None:
            continue
        target = int(row["target"], 16)
        position = bisect.bisect_right(starts, target) - 1
        if position < 0 or not spans[position][0] <= target < spans[position][0] + spans[position][1]:
            continue
        address, _size, cls = spans[position]
        head = target - address
        if head not in found["blocks"][cls]:
            continue
        site = int(row["site"], 16)
        owner = ctx.owner(site)
        if owner is None:
            continue
        parsed = next((demangle(n) for n in _function_names(ctx).get(owner, ()) if demangle(n)), None)
        if not parsed or parsed.get("name") not in ("__ct", "__dt") or "::".join(parsed.get("qualifier") or []) != cls:
            continue
        insn = ctx.code.word(site)
        if insn >> 26 not in (_ADDIU, _ORI):
            continue
        register = (insn >> 16) & 0x1F
        flow = ctx.flow(owner)
        for pc in range(owner, flow.end, 4):
            word = ctx.code.word(pc)
            if word >> 26 != _SW or (word >> 16) & 0x1F != register or flow.defs(pc, register) != {site}:
                continue
            base = (word >> 21) & 0x1F
            if _traces_to_a0_register(ctx, flow, flow.defs(pc, base), base, 4):
                result.setdefault(cls, {}).setdefault(_s16(word & 0xFFFF), set()).add(head)
    _VPTRS[key] = result
    return result


# -- static classes of pointer registers -------------------------------------------


def receiver_class(ctx: Any, function: int) -> str | None:
    """The class of ``this`` when the function provably has a receiver, else None."""

    from .recon_draft import _function_names, _is_stub, _slot_receiver
    from .recon_facts import argument_reads
    from .type_layout import parameter_registers

    parsed = next((demangle(n) for n in _function_names(ctx).get(function, ()) if demangle(n)), None)
    if not parsed or not parsed.get("qualifier") or _is_stub(ctx, function):
        return None
    name = "::".join(parsed["qualifier"])
    if parsed.get("name") in ("__ct", "__dt") or parsed.get("const") or _slot_receiver(ctx, function):
        return name
    without, complete = parameter_registers(parsed.get("params"), False)
    with_this, complete_this = parameter_registers(parsed.get("params"), True)
    if not complete or not complete_this:
        return None
    reads = set(argument_reads(ctx, function))
    if reads <= {"a0"} | {register for register, _value in with_this} and not reads <= {r for r, _v in without}:
        return name
    return None


def _entry(ctx: Any, function: int, register: int) -> tuple[int, str, Any, str] | None:
    from .recon_draft import _function_names
    from .recon_facts import GPR
    from .type_layout import parameter_registers

    receiver = receiver_class(ctx, function)
    if register == 4 and receiver:
        return 1, receiver, None, f"this:{receiver}"
    parsed = next((demangle(n) for n in _function_names(ctx).get(function, ()) if demangle(n)), None)
    if not parsed or (parsed.get("qualifier") and receiver is None):
        return None  # a member whose receiver is unproven: a0 may be this or the first parameter
    for name, value in parameter_registers(parsed.get("params"), receiver is not None)[0]:
        if name != GPR[register] or value.get("kind") != "class":
            continue
        modifiers = value.get("modifiers") or []
        if any(m not in ("P", "R", "C") for m in modifiers):
            return None
        levels = sum(1 for m in modifiers if m in ("P", "R"))
        cls = "::".join(value.get("components") or [])
        return (levels, cls, None, f"{name}:{cls}{'*' * levels}") if levels and cls else None
    return None


def _copy_source(insn: int) -> int | None:
    if insn >> 26 or (insn & 0x3F) not in (0x21, 0x25, 0x2D) or (insn >> 6) & 0x1F:
        return None
    rs, rt = (insn >> 21) & 0x1F, (insn >> 16) & 0x1F
    return rs if rt == 0 else rt if rs == 0 else None


def pointer_type(
    ctx: Any, flow: Any, function: int, site: int, register: int, seen: frozenset = frozenset()
) -> tuple[int, str, Any, str] | None:
    """(pointer levels, class, DIE or None, how) of ``register`` before ``site`` runs, when every
    definition reaching it proves the same class pointer; a loop's own update adds nothing."""

    dw = _dwarf(ctx)
    found: dict[tuple[int, str], tuple[int, str, Any, str]] = {}
    for d in sorted(flow.defs(site, register), key=str):
        if d == "entry":
            typed = _entry(ctx, function, register)
        elif not isinstance(d, int):
            return None
        elif (d, register) in seen:
            continue
        else:
            typed = _defined(ctx, dw, flow, function, d, register, seen | {(d, register)})
        if typed is None:
            return None
        found.setdefault((typed[0], typed[1].split("::")[-1]), typed)
    return next(iter(found.values())) if len(found) == 1 else None


def _defined(ctx: Any, dw: Any, flow: Any, function: int, d: int, register: int, seen: frozenset) -> Any:
    insn = ctx.code.word(d)
    if flow.fn.decoded.get(d - 4, {}).get("kind") in ("call", "call-branch") and register in CALL_CLOBBERED:
        return None  # a callee's result
    source = _copy_source(insn)
    if source is not None and (insn >> 11) & 0x1F == register:
        return pointer_type(ctx, flow, function, d, source, seen)
    op, base, k = insn >> 26, (insn >> 21) & 0x1F, _s16(insn & 0xFFFF)
    if op not in (_ADDIU, _LW) or (insn >> 16) & 0x1F != register:
        return None
    typed = pointer_type(ctx, flow, function, d, base, seen)
    if typed is None:
        return None
    levels, cls, die, how = typed
    if op == _ADDIU:
        if k == 0:
            return typed
        if levels >= 2:
            return (levels, cls, die, f"{how}+{k}") if k % 4 == 0 else None
        inner = _on_class(dw, cls, die, lambda record: subobject(dw, record, k))
    else:
        if levels >= 2:
            return (levels - 1, cls, die, f"{how}[{k // 4}]") if k % 4 == 0 else None
        inner = _on_class(dw, cls, die, lambda record: field(dw, record, k))
    return None if inner is None else (*inner[:3], f"{how} {'+' if op == _ADDIU else 'lw '}0x{k:x} {inner[3]}")


def slot_call(ctx: Any, owner: int, pc: int, rules: int) -> dict[str, Any] | None:
    """The vtable slot an indirect ``jalr``/``jr`` at ``pc`` calls through, with its slot family, else None.

    Returns ``family`` (a ``recon_draft.SlotFamily``), ``vtable`` (symbol),
    ``word`` (byte offset of the slot in it), ``vptr`` (its offset in the
    object) and ``object`` (how the object's class is proven).
    """

    from .recon_draft import CONTRACT_RULES, slot_node_family

    key = (id(ctx), rules >= CONTRACT_RULES, owner, pc)
    if key in _CALLS:
        return _CALLS[key]
    _CALLS[key] = None
    insn = ctx.code.word(pc)
    target = (insn >> 21) & 0x1F
    if insn >> 26 or (insn & 0x3F) not in (0x08, 0x09) or target == 31:
        return None
    flow = ctx.flow(owner)
    loads = []
    site, register = pc, target
    for _ in range(2):
        defs = flow.defs(site, register)
        if len(defs) != 1:
            return None
        (d,) = defs
        word = ctx.code.word(d) if isinstance(d, int) else 0
        if not isinstance(d, int) or word >> 26 != _LW or (word >> 16) & 0x1F != register:
            return None
        if flow.fn.decoded.get(d - 4, {}).get("kind") in ("call", "call-branch"):
            return None
        loads.append(_s16(word & 0xFFFF))
        site, register = d, (word >> 21) & 0x1F
    slot_offset, vptr = loads
    typed = pointer_type(ctx, flow, owner, site, register)
    if typed is None or typed[0] != 1:
        return None
    cls = vtable_class(ctx, typed[1])
    heads = vptr_stores(ctx).get(cls or "", {}).get(vptr, set())
    if cls is None or len(heads) != 1:
        return None
    (head,) = heads
    subobject_offset, count = vtables(ctx)["blocks"][cls][head]
    if slot_offset < 8 or slot_offset % 4 or (slot_offset - 8) // 4 >= count:
        return None
    family = slot_node_family(ctx, rules, cls, subobject_offset, (slot_offset - 8) // 4)
    if family is None:
        return None
    _CALLS[key] = {
        "family": family,
        "vtable": vtables(ctx)["tables"][cls][2],
        "word": head + slot_offset,
        "vptr": vptr,
        "object": typed[3],
    }
    return _CALLS[key]
