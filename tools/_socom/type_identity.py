"""Evidence-backed identities for Metrowerks DWARF 1 types.

Metrowerks DWARF 1 names types without namespaces, enclosing classes, or
template arguments, and repeats header types in every compile unit.  This
module groups type DIEs into structural classes and names them from binary
evidence, strongest first:

1. method evidence: subroutine DIEs carry their mangled linkage name
   (attribute 0x2000), so the `this` parameter and aligned parameters link
   type DIEs to demangled qualified names;
2. call-site evidence: mangled methods in `main` that pass `this + k`,
   optionally through loaded pointer members, as the instance argument of a
   mangled callee name the DIE stored at that offset in every compile-unit
   copy of the caller's class;
3. symbol inference: a bare spelling with exactly one qualified candidate
   among demangled symbols and exactly one unnamed structure;
4. spelling: the only structure with a bare name that no symbol qualifies.

Layout-identical structures can be distinct C++ types: every MSL `deque<T>`
stores `void**`, and nested types share spellings.  When a spelling is shared
(several qualified candidates, or a template base), names attach only to the
DIEs that evidence reaches.  Otherwise a name covers its whole structural
class.  Ambiguous or contradictory evidence leaves a DIE unnamed, and every
unnamed DIE receives a deterministic provisional name.
"""

from __future__ import annotations

import collections
import hashlib
import struct
from typing import Any

from .dwarf1 import TYPE_TAGS, Die
from .elf import Elf32File, Symbol
from .mwdemangle import (
    component_argument_types,
    demangle,
    readable_qualified,
    split_qualified,
    template_base,
)
from .util import SocomError

NAMED_KINDS = frozenset(
    {"class_type", "structure_type", "union_type", "enumeration_type"}
)
COMPOSITE_KINDS = frozenset({"class_type", "structure_type", "union_type"})
MANGLED_NAME_ATTRIBUTE = "attr_0x2000"
GHIDRA_ROOT = "/project"
PROVISIONAL_CATEGORY = "unresolved"
MAX_RESOLUTION_ROUNDS = 16
MAX_POINTER_LOADS = 3
SAMPLE_LIMIT = 3
AMBIGUOUS = "<ambiguous call-site receiver>"

# DWARF 1 type modifiers.
MOD_POINTER_TO = 0x01
MOD_REFERENCE_TO = 0x02
MODIFIER_NAMES = {0x01: "pointer_to", 0x02: "reference_to", 0x03: "const", 0x04: "volatile"}

# R5900 general-purpose registers and instruction classes.
REG_A0 = 4
REG_SP = 29
REG_RA = 31
CALL_CLOBBERED = frozenset(range(1, 16)) | {24, 25, REG_RA}
SAVED_REGISTERS = frozenset(range(16, 24)) | {30}
BRANCH_OPCODES = frozenset({0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17})
LIKELY_OPCODES = frozenset({0x14, 0x15, 0x16, 0x17})
REGIMM_LINK = frozenset({0x10, 0x11, 0x12, 0x13})
REGIMM_LIKELY = frozenset({0x02, 0x03, 0x12, 0x13})
STORE_OPCODES = frozenset(
    {0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3F, 0x1F, 0x39, 0x3D, 0x3E}
)
NO_GPR_OPCODES = frozenset({0x2F, 0x31, 0x33, 0x35, 0x36})
MOVE_FUNCTS = frozenset({0x21, 0x2D, 0x25})  # addu, daddu, or
# div/divu and HI/LO moves write only HI/LO; R5900 mult/multu also write rd.
HI_LO_FUNCTS = frozenset({0x11, 0x13, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F})

TypeRef = tuple[bytes, "int | None", "int | None"]


def _digest(value: Any) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()


def type_ref(die: Die) -> TypeRef | None:
    """Return (modifiers, referenced DIE offset, fundamental type code)."""

    for attribute in die.attributes:
        value = attribute.value
        if attribute.name == "user_def_type" and isinstance(value, int):
            return b"", value, None
        if attribute.name == "mod_user_def_type" and isinstance(value, bytes):
            return value[:-4], int.from_bytes(value[-4:], "little"), None
        if attribute.name == "fund_type" and isinstance(value, int):
            return b"", None, value
        if attribute.name == "mod_fund_type" and isinstance(value, bytes):
            return value[:-2], None, int.from_bytes(value[-2:], "little")
    return None


def type_descriptor(ref: TypeRef | None) -> dict[str, Any] | None:
    """Portable form of a type reference: modifiers plus a DIE or fund type."""

    if ref is None:
        return None
    modifiers, target, fund = ref
    return {
        "modifiers": [MODIFIER_NAMES.get(value, f"0x{value:02x}") for value in modifiers],
        "die_offset": target,
        "fund_type": fund,
    }


def indirection(modifiers: bytes) -> tuple[int, ...]:
    """Pointer (1) and reference (2) modifiers, ignoring cv-qualifiers."""

    return tuple(
        1 if modifier == MOD_POINTER_TO else 2
        for modifier in modifiers
        if modifier in (MOD_POINTER_TO, MOD_REFERENCE_TO)
    )


def parse_subscr(data: bytes) -> tuple[list[tuple[Any, ...]], TypeRef | None]:
    """Decode DWARF 1 subscript data into dimensions and the element type.

    Index types that are user-defined refer to compile-unit-local DIE offsets,
    so only their presence is retained.  Undecodable data is kept as raw bytes.
    """

    dims: list[tuple[Any, ...]] = []
    cursor = 0
    try:
        while cursor < len(data):
            fmt = data[cursor]
            cursor += 1
            if fmt == 0x8:
                encoded = int.from_bytes(data[cursor : cursor + 2], "little")
                cursor += 2
                form = encoded & 0xF
                name = encoded & 0xFFF0
                if form == 0x5:
                    value: Any = int.from_bytes(data[cursor : cursor + 2], "little")
                elif form in (0x2, 0x6):
                    value = int.from_bytes(data[cursor : cursor + 4], "little")
                elif form == 0x3:
                    size = int.from_bytes(data[cursor : cursor + 2], "little")
                    value = data[cursor + 2 : cursor + 2 + size]
                else:
                    raise ValueError(f"element form {form}")
                if name == 0x0050:
                    return dims, (b"", None, value)
                if name == 0x0070:
                    return dims, (b"", value, None)
                if name == 0x0060:
                    return dims, (value[:-2], None, int.from_bytes(value[-2:], "little"))
                if name == 0x0080:
                    return dims, (value[:-4], int.from_bytes(value[-4:], "little"), None)
                raise ValueError(f"element attribute 0x{name:x}")
            if fmt > 0x7:
                raise ValueError(f"subscript format {fmt}")
            if fmt < 0x4:
                index: tuple[Any, ...] = ("fund", int.from_bytes(data[cursor : cursor + 2], "little"))
                cursor += 2
            else:
                index = ("user",)
                cursor += 4
            bounds: list[Any] = []
            for constant in ((fmt & 0x3) in (0, 1), (fmt & 0x3) in (0, 2)):
                if constant:
                    bounds.append(
                        int.from_bytes(data[cursor : cursor + 4], "little", signed=True)
                    )
                    cursor += 4
                else:
                    size = int.from_bytes(data[cursor : cursor + 2], "little")
                    bounds.append(data[cursor + 2 : cursor + 2 + size].hex())
                    cursor += 2 + size
            dims.append((*index, *bounds))
    except (ValueError, IndexError):
        return [("raw", data.hex())], None
    return dims, None


def member_offset(member: Die) -> int | None:
    """Byte offset from a member or inheritance location `CONST k; ADD`."""

    location = member.attribute("location")
    data = location.value if location else None
    if isinstance(data, bytes) and len(data) == 6 and data[0] == 0x04 and data[5] == 0x07:
        return int.from_bytes(data[1:5], "little")
    return None


def raw_type_name(die: Die) -> str | None:
    name = die.string("name")
    return None if not name or name.startswith("@") else name


def ghidra_path(qualified_name: str) -> str:
    return GHIDRA_ROOT + "/" + "/".join(split_qualified(qualified_name))


def is_template_name(qualified_name: str) -> bool:
    return "<" in split_qualified(qualified_name)[-1]


def template_arguments(qualified_name: str) -> list[str]:
    """Readable template arguments of a name's last component."""

    last = split_qualified(qualified_name)[-1]
    if "<" not in last or not last.endswith(">"):
        return []
    inner = last[last.index("<") + 1 : -1]
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(inner):
        if char in "<(":
            depth += 1
        elif char in ">)":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(inner[start:index].strip())
            start = index + 1
    parts.append(inner[start:].strip())
    return parts


class TypeIdentities:
    """Structural classes and evidence-backed names for one DWARF graph."""

    def __init__(self, elf: Elf32File, dies: tuple[Die, ...], parents: dict[int, int]):
        self.elf = elf
        self.by_offset = {die.offset: die for die in dies}
        self.children: dict[int, list[Die]] = collections.defaultdict(list)
        for die in dies:
            if die.offset in parents:
                self.children[parents[die.offset]].append(die)
        self.type_dies = [die for die in dies if die.tag in TYPE_TAGS]
        self.declaration = {
            die.offset: die.tag_name in COMPOSITE_KINDS
            and die.integer("byte_size") in (None, 0)
            and not any(
                child.tag_name in ("member", "inheritance")
                for child in self.children[die.offset]
            )
            for die in self.type_dies
        }
        self.structural_class = self._partition()
        self.classes: dict[str, list[Die]] = collections.defaultdict(list)
        for die in self.type_dies:
            if (
                die.tag_name in NAMED_KINDS
                and raw_type_name(die)
                and not self.declaration[die.offset]
            ):
                self.classes[self.structural_class[die.offset]].append(die)
        self.by_raw: dict[str, list[str]] = collections.defaultdict(list)
        for key in sorted(self.classes):
            self.by_raw[raw_type_name(self.classes[key][0]) or ""].append(key)
        self._layouts: dict[int, list[tuple[int, str, int]]] = {}
        self.symbol_exact, self.symbol_template = self._symbol_candidates()
        # A spelling is shared when demangled symbols qualify it more than one
        # way or use it as a template base; layout then does not determine
        # identity, so names attach only to DIEs that evidence reaches.
        self.shared_spelling = {
            raw
            for raw in set(self.by_raw) | {raw_type_name(d) or "" for d in self.type_dies}
            if len(self.symbol_exact.get(raw, ())) > 1 or raw in self.symbol_template
        }
        self.method_evidence, self.method_samples, self.receivers = self._method_evidence()
        # Method evidence that lands on a forward declaration names the unique
        # complete structure with that spelling, when the spelling is unshared.
        self.declaration_evidence: dict[str, set[str]] = collections.defaultdict(set)
        for offset, names in self.method_evidence.items():
            if self.declaration[offset]:
                raw = raw_type_name(self.by_offset[offset]) or ""
                self.declaration_evidence[raw].update(names)
        self.calls = self._call_records()
        self._resolve()

    # ------------------------------------------------------------ structure
    def _edge(self, ref: TypeRef, via_pointer: bool) -> tuple[tuple[Any, ...], int | None]:
        modifiers, target, fund = ref
        pointer = via_pointer or bool(indirection(modifiers))
        if target is None:
            return (modifiers.hex(), "fund", fund), None
        die = self.by_offset.get(target)
        if die is None:
            return (modifiers.hex(), "missing"), None
        name = raw_type_name(die)
        # Pointees are compared by name: a pointer to a forward declaration and
        # a pointer to the complete type are the same member type.
        if pointer and name and die.tag_name in NAMED_KINDS:
            return (modifiers.hex(), "pointee", die.tag_name, name), None
        return (modifiers.hex(), "type"), target

    def _partition(self) -> dict[int, str]:
        local: dict[int, tuple[Any, ...]] = {}
        edges: dict[int, list[int]] = {}
        for die in self.type_dies:
            features: list[Any] = [
                die.tag_name,
                raw_type_name(die),
                die.integer("byte_size"),
                self.declaration[die.offset],
            ]
            targets: list[int] = []
            ref = type_ref(die)
            if ref:
                feature, target = self._edge(ref, die.tag_name == "pointer_type")
                features.append(feature)
                if target is not None:
                    targets.append(target)
            if die.tag_name == "array_type":
                subscript = die.attribute("subscr_data")
                dims, element = parse_subscr(
                    subscript.value if subscript and isinstance(subscript.value, bytes) else b""
                )
                features.append(tuple(dims))
                if element:
                    feature, target = self._edge(element, False)
                    features.append(feature)
                    if target is not None:
                        targets.append(target)
            if die.tag_name == "enumeration_type":
                elements = die.attribute("element_list")
                features.append(elements.value.hex() if elements and isinstance(elements.value, bytes) else None)
            for child in self.children[die.offset]:
                if child.tag_name in ("member", "inheritance"):
                    location = child.attribute("location")
                    child_ref = type_ref(child)
                    feature, target = self._edge(child_ref, False) if child_ref else ((), None)
                    features.append(
                        (
                            child.tag_name,
                            child.string("name"),
                            location.value.hex() if location and isinstance(location.value, bytes) else None,
                            child.integer("bit_offset"),
                            child.integer("bit_size"),
                            feature,
                        )
                    )
                    if target is not None:
                        targets.append(target)
                elif child.tag_name == "formal_parameter" and die.tag_name == "subroutine_type":
                    child_ref = type_ref(child)
                    feature, target = self._edge(child_ref, True) if child_ref else ((), None)
                    features.append(("parameter", feature))
                    if target is not None:
                        targets.append(target)
            local[die.offset] = tuple(features)
            edges[die.offset] = targets

        color = {offset: _digest(features) for offset, features in local.items()}
        count = len(set(color.values()))
        for _ in range(len(color) + 1):
            refined = {
                offset: _digest((color[offset], tuple(color.get(t, "missing") for t in edges[offset])))
                for offset in color
            }
            refined_count = len(set(refined.values()))
            color = refined
            if refined_count == count:
                break
            count = refined_count
        return {offset: f"socom:type-class:{value[:20]}" for offset, value in color.items()}

    def _named_target(self, offset: int | None, seen: tuple[int, ...] = ()) -> int | None:
        """Follow by-value typedefs to a named type DIE."""

        die = self.by_offset.get(offset) if offset is not None else None
        if die is None or die.offset in seen:
            return None
        if die.tag_name in NAMED_KINDS:
            return die.offset
        if die.tag_name == "typedef":
            ref = type_ref(die)
            if ref and ref[1] is not None and not indirection(ref[0]):
                return self._named_target(ref[1], (*seen, die.offset))
        return None

    def _complete(self, offset: int | None) -> int | None:
        """A complete DIE for a named type; declarations need a unique spelling."""

        target = self._named_target(offset)
        if target is None:
            return None
        if not self.declaration[target]:
            return target
        raw = raw_type_name(self.by_offset[target]) or ""
        keys = self.by_raw.get(raw, [])
        if raw in self.shared_spelling or len(keys) != 1:
            return None
        return min(die.offset for die in self.classes[keys[0]])

    def _layout(self, offset: int) -> list[tuple[int, str, int]]:
        """(offset, 'value'|'pointer', named DIE) entries of one DIE's members."""

        if offset not in self._layouts:
            entries = []
            for child in self.children[offset]:
                if child.tag_name not in ("member", "inheritance"):
                    continue
                start = member_offset(child)
                ref = type_ref(child)
                if start is None or not ref or ref[1] is None:
                    continue
                target = self._named_target(ref[1])
                if target is None:
                    continue
                pointer = indirection(ref[0])
                if not pointer and not self.declaration[target]:
                    entries.append((start, "value", target))
                elif pointer == (1,):
                    entries.append((start, "pointer", target))
            self._layouts[offset] = entries
        return self._layouts[offset]

    def _dies_at(self, offset: int, position: int, depth: int = 0) -> list[int]:
        """Named DIEs whose storage starts exactly at `position` inside `offset`."""

        found = [offset] if position == 0 else []
        if depth >= 16:
            return found
        for start, kind, target in self._layout(offset):
            if kind != "value":
                continue
            size = self.by_offset[target].integer("byte_size") or 1
            if start <= position < start + size:
                found.extend(self._dies_at(target, position - start, depth + 1))
        return found

    # ------------------------------------------------------------- evidence
    def _method_evidence(
        self,
    ) -> tuple[dict[int, collections.Counter[str]], dict[int, list[str]], dict[int, bool]]:
        evidence: dict[int, collections.Counter[str]] = collections.defaultdict(collections.Counter)
        samples: dict[int, list[str]] = collections.defaultdict(list)
        receivers: dict[int, bool] = {}

        def record(offset: int | None, name: str, mangled: str) -> None:
            target = self._named_target(offset)
            if target is None:
                return
            evidence[target][name] += 1
            if len(samples[target]) < SAMPLE_LIMIT and mangled not in samples[target]:
                samples[target].append(mangled)

        for die in self.by_offset.values():
            if die.tag_name not in ("global_subroutine", "subroutine"):
                continue
            mangled = die.string(MANGLED_NAME_ATTRIBUTE)
            parsed = demangle(mangled) if mangled else None
            if not parsed or parsed["params"] is None:
                continue
            parameters = [
                child for child in self.children[die.offset] if child.tag_name == "formal_parameter"
            ]
            receiver = [child for child in parameters if child.string("name") == "this"]
            others = [child for child in parameters if child.string("name") != "this"]
            low_pc = die.integer("low_pc")
            if low_pc is not None:
                receivers[low_pc] = bool(receiver)
            if receiver and parsed["qualifier"]:
                ref = type_ref(receiver[0])
                if ref and ref[1] is not None and indirection(ref[0]) == (1,):
                    record(ref[1], readable_qualified(parsed["qualifier"]), mangled)
            declared = [
                param
                for param in parsed["params"]
                if not (param["kind"] == "builtin" and param["name"] == "void" and not param["modifiers"])
            ]
            if len(declared) != len(others):
                continue
            for parameter, value in zip(others, declared):
                ref = type_ref(parameter)
                if not ref or ref[1] is None or value["kind"] != "class":
                    continue
                expected = tuple(1 if m == "P" else 2 for m in value["modifiers"] if m in "PR")
                if indirection(ref[0]) == expected:
                    record(ref[1], readable_qualified(value["components"]), mangled)
        return evidence, samples, receivers

    def _symbol_candidates(self) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        exact: dict[str, set[str]] = collections.defaultdict(set)
        templated: dict[str, set[str]] = collections.defaultdict(set)
        for symbol in self.elf.symbols():
            parsed = demangle(symbol.name) if symbol.name else None
            if not parsed:
                continue
            pending_names = [parsed["qualifier"]] if parsed["qualifier"] else []
            stack = list(parsed["params"] or [])
            seen: set[tuple[str, ...]] = set()
            while stack or pending_names:
                while stack:
                    value = stack.pop()
                    if value["kind"] == "class":
                        pending_names.append(value["components"])
                    elif value["kind"] == "function":
                        stack.extend([*value["params"], value["result"]])
                    elif value["kind"] == "array":
                        stack.append(value["element"])
                    elif value["kind"] == "member_pointer":
                        pending_names.append(value["owner"])
                        stack.append(value["pointee"])
                if not pending_names:
                    break
                components = pending_names.pop()
                if tuple(components) in seen:
                    continue
                seen.add(tuple(components))
                for depth in range(1, len(components) + 1):
                    component = components[depth - 1]
                    name = readable_qualified(components[:depth])
                    if "<" in component:
                        templated[template_base(component)].add(name)
                        # Template arguments qualify names too, e.g.
                        # std::__red_black_tree<1>::anchor inside a pair.
                        stack.extend(component_argument_types(component))
                    else:
                        exact[component].add(name)
        return exact, templated

    def _call_records(self) -> list[tuple[str, tuple[int, ...], str, str, str]]:
        """(owner, this-relative path, callee class, callee base, caller symbol)."""

        main = self.elf.section("main")
        code = self.elf.section_data(main)
        functions = sorted(
            (
                symbol
                for symbol in self.elf.symbols()
                if symbol.type_name == "FUNC"
                and symbol.size
                and main.address <= symbol.value < main.address + len(code)
            ),
            key=lambda symbol: (symbol.value, symbol.name),
        )
        by_address: dict[int, Symbol] = {}
        for symbol in functions:
            by_address.setdefault(symbol.value, symbol)
        records = []
        for symbol in functions:
            parsed = demangle(symbol.name)
            if not parsed or parsed["params"] is None or not parsed["qualifier"]:
                continue
            # DWARF proves some qualified functions take no `this`.
            if self.receivers.get(symbol.value) is False:
                continue
            owner = readable_qualified(parsed["qualifier"])
            start = symbol.value - main.address
            end = min(start + symbol.size, len(code))
            words = [
                struct.unpack_from("<I", code, offset)[0]
                for offset in range(start, end - 3, 4)
            ]
            for path, callee in _trace_receiver_calls(words, symbol.value, by_address):
                callee_parsed = demangle(callee.name)
                if not callee_parsed or callee_parsed["params"] is None or not callee_parsed["qualifier"]:
                    continue
                if self.receivers.get(callee.value) is False:
                    continue
                records.append(
                    (
                        owner,
                        path,
                        readable_qualified(callee_parsed["qualifier"]),
                        template_base(callee_parsed["qualifier"][-1]),
                        symbol.name,
                    )
                )
        return records

    def _call_evidence(
        self, names: dict[int, str]
    ) -> tuple[dict[int, collections.Counter[str]], dict[int, list[str]], dict[int, set[str]]]:
        owners: dict[str, list[int]] = collections.defaultdict(list)
        for offset, name in names.items():
            owners[name].append(offset)
        evidence: dict[int, collections.Counter[str]] = collections.defaultdict(collections.Counter)
        samples: dict[int, list[str]] = collections.defaultdict(list)
        ambiguous: dict[int, set[str]] = collections.defaultdict(set)
        for owner, path, callee, callee_base, caller in self.calls:
            for owner_die in owners.get(owner, ()):
                current: int | None = owner_die
                for load_offset in path[:-1]:
                    pointee = next(
                        (
                            target
                            for start, kind, target in self._layout(current)
                            if kind == "pointer" and start == load_offset
                        ),
                        None,
                    )
                    current = self._complete(pointee)
                    if current is None:
                        break
                if current is None:
                    continue
                candidates = [
                    offset
                    for offset in self._dies_at(current, path[-1])
                    if raw_type_name(self.by_offset[offset]) == callee_base
                    and not (len(path) == 1 and offset == owner_die)
                ]
                if len(candidates) == 1:
                    evidence[candidates[0]][callee] += 1
                    sample = f"{caller} -> {callee}"
                    if len(samples[candidates[0]]) < SAMPLE_LIMIT and sample not in samples[candidates[0]]:
                        samples[candidates[0]].append(sample)
                elif candidates:
                    for offset in candidates:
                        ambiguous[offset].add(callee)
        return evidence, samples, ambiguous

    # ----------------------------------------------------------- resolution
    def _resolve(self) -> None:
        names: dict[int, str] = {}
        basis: dict[int, str] = {}
        contradictions: dict[int, list[str]] = {}
        converged = False
        for _ in range(MAX_RESOLUTION_ROUNDS):
            calls, call_samples, ambiguous = self._call_evidence(names)
            new_names: dict[int, str] = {}
            new_basis: dict[int, str] = {}
            new_contradictions: dict[int, list[str]] = {}
            pending: set[str] = set()

            def proven(offset: int) -> set[str]:
                return set(self.method_evidence.get(offset, ())) | set(calls.get(offset, ()))

            for key, rows in sorted(self.classes.items()):
                raw = raw_type_name(rows[0]) or ""
                offsets = [die.offset for die in rows]
                class_names = set().union(*(proven(offset) for offset in offsets))
                declared = set()
                if raw not in self.shared_spelling and len(self.by_raw[raw]) == 1:
                    declared = self.declaration_evidence.get(raw, set())
                    class_names |= declared
                per_die = raw in self.shared_spelling or any(
                    is_template_name(name) for name in class_names
                )
                if per_die:
                    for offset in offsets:
                        found = proven(offset)
                        if offset in ambiguous or len(found) > 1:
                            new_contradictions[offset] = sorted(
                                found | ({AMBIGUOUS} if offset in ambiguous else set())
                            )
                        elif found:
                            new_names[offset] = next(iter(found))
                            new_basis[offset] = (
                                "method" if offset in self.method_evidence else "call-site"
                            )
                    continue
                if any(offset in ambiguous for offset in offsets) or len(class_names) > 1:
                    candidates = sorted(
                        class_names
                        | ({AMBIGUOUS} if any(offset in ambiguous for offset in offsets) else set())
                    )
                    for offset in offsets:
                        new_contradictions[offset] = candidates
                elif class_names:
                    name = next(iter(class_names))
                    method = bool(declared) or any(
                        offset in self.method_evidence for offset in offsets
                    )
                    for offset in offsets:
                        new_names[offset] = name
                        new_basis[offset] = "method" if method else "call-site"
                else:
                    pending.add(key)

            for raw, keys in self.by_raw.items():
                if raw in self.shared_spelling:
                    continue
                unnamed = [key for key in keys if key in pending]
                if len(unnamed) != 1:
                    continue
                used = {
                    new_names[die.offset]
                    for key in keys
                    for die in self.classes[key]
                    if die.offset in new_names
                }
                exact = self.symbol_exact.get(raw, set()) - used
                if len(exact) == 1:
                    name, resolution = next(iter(exact)), "symbol"
                elif not exact and not used and len(keys) == 1:
                    name, resolution = raw, "spelling"
                else:
                    continue
                for die in self.classes[unnamed[0]]:
                    new_names[die.offset] = name
                    new_basis[die.offset] = resolution

            stable = new_names == names and new_contradictions == contradictions
            names, basis, contradictions = new_names, new_basis, new_contradictions
            if stable:
                converged = True
                break
        if not converged:
            raise SocomError(
                f"type identity resolution did not converge in {MAX_RESOLUTION_ROUNDS} rounds"
            )
        self.call_evidence, self.call_samples, self.ambiguous = calls, call_samples, ambiguous
        self.die_names, self.die_basis, self.contradictions = names, basis, contradictions
        self._build_identities()
        self.conflicts = self._identity_conflicts() + self._template_argument_conflicts()

    def _final(self, offset: int) -> tuple[str, str]:
        if offset in self.die_names:
            return self.die_names[offset], self.die_basis[offset]
        key = self.structural_class[offset]
        raw = raw_type_name(self.by_offset[offset]) or ""
        return f"{raw}@{key.rsplit(':', 1)[-1][:10]}", "provisional"

    def _build_identities(self) -> None:
        groups: dict[tuple[str, str], list[int]] = collections.defaultdict(list)
        bases: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
        for key, rows in self.classes.items():
            for die in rows:
                name, resolution = self._final(die.offset)
                groups[(key, name)].append(die.offset)
                bases[(key, name)].add(resolution)
        self.identities: list[dict[str, Any]] = []
        for (key, name), offsets in sorted(groups.items()):
            # One identity per class and name; report its strongest basis.
            resolution = next(
                basis
                for basis in ("method", "call-site", "symbol", "spelling", "provisional")
                if basis in bases[(key, name)]
            )
            first = self.by_offset[offsets[0]]
            raw = raw_type_name(first) or ""
            method: collections.Counter[str] = collections.Counter()
            calls: collections.Counter[str] = collections.Counter()
            method_samples: list[str] = []
            call_samples: list[str] = []
            contradiction: set[str] = set()
            for offset in offsets:
                method.update(self.method_evidence.get(offset, {}))
                calls.update(self.call_evidence.get(offset, {}))
                method_samples.extend(self.method_samples.get(offset, []))
                call_samples.extend(self.call_samples.get(offset, []))
                contradiction.update(self.contradictions.get(offset, []))
                contradiction.update(self.ambiguous.get(offset, set()))
            path = (
                f"{GHIDRA_ROOT}/{PROVISIONAL_CATEGORY}/{name}"
                if resolution == "provisional"
                else ghidra_path(name)
            )
            self.identities.append(
                {
                    "structural_class": key,
                    "raw_name": raw,
                    "kind": first.tag_name,
                    "byte_size": first.integer("byte_size"),
                    "die_count": len(offsets),
                    "qualified_name": name,
                    "ghidra_path": path,
                    "resolution": resolution,
                    "shared_spelling": raw in self.shared_spelling,
                    "evidence": {
                        "method": dict(sorted(method.items())),
                        "method_samples": sorted(set(method_samples))[:SAMPLE_LIMIT],
                        "call_site": dict(sorted(calls.items())),
                        "call_site_samples": sorted(set(call_samples))[:SAMPLE_LIMIT],
                        "symbol_candidates": sorted(
                            self.symbol_exact.get(raw, set()) | self.symbol_template.get(raw, set())
                        )[:8],
                        "contradiction": sorted(contradiction),
                    },
                }
            )

    def _identity_conflicts(self) -> list[dict[str, Any]]:
        by_name: dict[str, set[str]] = collections.defaultdict(set)
        for identity in self.identities:
            by_name[identity["qualified_name"]].add(identity["structural_class"])
        return [
            {
                "qualified_name": name,
                "reason": "distinct structures share one qualified identity",
                "structural_classes": sorted(keys),
            }
            for name, keys in sorted(by_name.items(), key=lambda item: (item[0].casefold(), item[0]))
            if len(keys) > 1
        ]

    def _template_argument_conflicts(self) -> list[dict[str, Any]]:
        """By-value members or bases that contradict their owner's arguments."""

        found: dict[str, set[str]] = collections.defaultdict(set)
        classes: dict[str, set[str]] = collections.defaultdict(set)
        for offset, owner in self.die_names.items():
            arguments = template_arguments(owner)
            if not arguments:
                continue
            bases = {
                template_base(split_qualified(argument)[-1]): argument for argument in arguments
            }
            for _, kind, target in self._layout(offset):
                if kind != "value" or target not in self.die_names:
                    continue
                raw = raw_type_name(self.by_offset[target]) or ""
                member = self.die_names[target]
                if raw in bases and member not in arguments:
                    found[owner].add(member)
                    classes[owner].update(
                        {self.structural_class[offset], self.structural_class[target]}
                    )
        return [
            {
                "qualified_name": owner,
                "reason": "member or base contradicts owner template arguments",
                "contradicting_members": sorted(members),
                "structural_classes": sorted(classes[owner]),
            }
            for owner, members in sorted(found.items(), key=lambda item: (item[0].casefold(), item[0]))
        ]

    # --------------------------------------------------------------- lookup
    def die_identity(self, offset: int) -> dict[str, Any] | None:
        """Identity of a named type DIE, including forward declarations."""

        die = self.by_offset[offset]
        raw = raw_type_name(die)
        if die.tag_name not in NAMED_KINDS or not raw:
            return None
        if not self.declaration[offset]:
            name, resolution = self._final(offset)
            return {
                "structural_class": self.structural_class[offset],
                "qualified_name": name,
                "ghidra_path": (
                    f"{GHIDRA_ROOT}/{PROVISIONAL_CATEGORY}/{name}"
                    if resolution == "provisional"
                    else ghidra_path(name)
                ),
                "resolution": resolution,
                "declaration": False,
            }
        direct = set(self.method_evidence.get(offset, ()))
        if len(direct) == 1:
            name = next(iter(direct))
            return self._declaration(name, ghidra_path(name), "declaration-method")
        keys = self.by_raw.get(raw, [])
        if raw not in self.shared_spelling and len(keys) == 1:
            name, resolution = self._final(min(d.offset for d in self.classes[keys[0]]))
            path = (
                f"{GHIDRA_ROOT}/{PROVISIONAL_CATEGORY}/{name}"
                if resolution == "provisional"
                else ghidra_path(name)
            )
            return self._declaration(name, path, "declaration")
        exact = self.symbol_exact.get(raw, set())
        if not keys and len(exact) == 1 and raw not in self.shared_spelling:
            name = next(iter(exact))
            return self._declaration(name, ghidra_path(name), "declaration-symbol")
        if not keys and not exact and raw not in self.shared_spelling:
            return self._declaration(raw, ghidra_path(raw), "declaration-spelling")
        name = f"{raw}@opaque"
        return self._declaration(
            name, f"{GHIDRA_ROOT}/{PROVISIONAL_CATEGORY}/{name}", "provisional-declaration"
        )

    @staticmethod
    def _declaration(name: str, path: str, resolution: str) -> dict[str, Any]:
        return {
            "structural_class": None,
            "qualified_name": name,
            "ghidra_path": path,
            "resolution": resolution,
            "declaration": True,
        }


def _signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _written_register(word: int) -> int | None:
    """General-purpose register written by an R5900 instruction, if any."""

    opcode = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    if opcode == 0x00:
        funct = word & 0x3F
        if funct == 0x08 or funct in HI_LO_FUNCTS:
            return None
        return rd or None
    if opcode == 0x1C:
        return rd or None
    if opcode == 0x01:
        return REG_RA if rt in REGIMM_LINK else None
    if opcode == 0x02 or opcode in BRANCH_OPCODES:
        return None
    if opcode == 0x03:
        return REG_RA
    if opcode in (0x10, 0x11, 0x12):
        return (rt or None) if rs in (0x00, 0x01, 0x02) else None
    if opcode in STORE_OPCODES or opcode in NO_GPR_OPCODES:
        return None
    return rt or None


def _branch(word: int) -> str | None:
    """'likely', 'unconditional', 'call', or 'branch' for R5900 branches."""

    opcode = word >> 26
    rs, rt = (word >> 21) & 31, (word >> 16) & 31
    if opcode in BRANCH_OPCODES:
        if opcode == 0x04 and rs == 0 and rt == 0:
            return "unconditional"
        return "likely" if opcode in LIKELY_OPCODES else "branch"
    if opcode == 0x01:
        if rt in REGIMM_LINK:
            return "call"
        if rt == 0x01 and rs == 0:
            return "unconditional"
        return "likely" if rt in REGIMM_LIKELY else "branch"
    if opcode in (0x10, 0x11, 0x12) and rs == 0x08:
        return "likely" if rt in (0x02, 0x03) else "branch"
    return None


def _trace_receiver_calls(
    words: list[int], start: int, functions: dict[int, Symbol]
) -> list[tuple[tuple[int, ...], Symbol]]:
    """Calls whose `a0` is `this` plus offsets, through pointer-member loads.

    A path `(k0, k1, ..., kn)` means: add k0 to `this`, load a pointer, add k1,
    and so on; the last element is the final offset.  Saved registers that are
    written once, by a move from `a0`, keep `this` across merge points.
    Branch-likely delay slots are annulled on the fall-through path.
    """

    end = start + 4 * len(words)
    writes: collections.Counter[int] = collections.Counter()
    receiver_copies: set[int] = set()
    merge_points: set[int] = set()
    for index, word in enumerate(words):
        address = start + index * 4
        opcode = word >> 26
        rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
        written = _written_register(word)
        is_restore = opcode in (0x23, 0x37, 0x1E) and rs == REG_SP
        if written is not None and not is_restore:
            writes[written] += 1
        if opcode == 0x00 and (word & 0x3F) in MOVE_FUNCTS and REG_A0 in (rs, rt) and 0 in (rs, rt):
            receiver_copies.add(rd)
        if _branch(word) is not None:
            merge_points.add(address + 4 + (_signed16(word & 0xFFFF) << 2))
        elif opcode == 0x02:
            target = (address & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
            if start <= target < end:
                merge_points.add(target)
    stable = {
        register
        for register in receiver_copies
        if register in SAVED_REGISTERS and writes[register] == 1
    }

    registers: dict[int, tuple[int, ...]] = {REG_A0: (0,)}

    def keep_stable() -> None:
        for register in list(registers):
            if register not in stable:
                del registers[register]

    def clobber_call() -> None:
        for register in CALL_CLOBBERED:
            registers.pop(register, None)

    def step(word: int) -> None:
        opcode = word >> 26
        rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
        if opcode == 0x00 and (word & 0x3F) in MOVE_FUNCTS and 0 in (rs, rt) and rd:
            source = rs if rt == 0 else rt
            if source in registers:
                registers[rd] = registers[source]
                return
        elif opcode in (0x09, 0x19) and rt and rs in registers:
            path = registers[rs]
            registers[rt] = (*path[:-1], path[-1] + _signed16(word & 0xFFFF))
            return
        elif opcode == 0x23 and rt and rs in registers:
            path = registers[rs]
            if len(path) <= MAX_POINTER_LOADS:
                registers[rt] = (*path[:-1], path[-1] + _signed16(word & 0xFFFF), 0)
                return
        written = _written_register(word)
        if written is not None:
            registers.pop(written, None)

    calls: list[tuple[tuple[int, ...], Symbol]] = []
    index = 0
    while index < len(words):
        address = start + index * 4
        if index and address in merge_points:
            keep_stable()
        word = words[index]
        opcode = word >> 26
        funct = word & 0x3F
        delay = words[index + 1] if index + 1 < len(words) else 0
        kind = _branch(word)
        if opcode == 0x03:
            step(delay)
            callee = functions.get((address & 0xF0000000) | ((word & 0x03FFFFFF) << 2))
            if callee is not None and REG_A0 in registers:
                calls.append((registers[REG_A0], callee))
            clobber_call()
            index += 2
            continue
        if (opcode == 0x00 and funct == 0x09) or kind == "call":
            step(delay)
            clobber_call()
            index += 2
            continue
        if opcode == 0x02 or (opcode == 0x00 and funct == 0x08) or kind == "unconditional":
            step(delay)
            keep_stable()
            index += 2
            continue
        if kind == "likely":
            # The delay slot executes only when the branch is taken, and the
            # taken path starts at a merge point.
            index += 2
            continue
        step(word)
        index += 1
    return calls
