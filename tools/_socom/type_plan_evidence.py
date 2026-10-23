"""ELF symbol and DWARF 1 facts that code-derived type plans cite.

Three questions a type plan asks of the immutable ELF, answered here so the
validator stays file-only:

* does a qualified name exist?  A mangled ``.symtab`` name names a type when
  the type is the qualifier of a member, a parameter type, or a template
  argument of either (``name_problems``); an RTTI object names a class; a
  DWARF 1 record names a type by its leaf (DWARF 1 drops qualifiers and
  template arguments);
* which class sub-objects lie inside a by-value type?  DWARF 1 records give
  every base and by-value member at its offset, empty bases included
  (``Metrowerks::compile_assert<1>`` sits at the end of a 12-byte
  ``__vector_imp``), so a constructor call on such an address belongs to the
  enclosing object, not to the field that follows it (``nested``).  DWARF 1
  drops template arguments, so records of one name can disagree
  (``vector<T *>`` keeps ``compile_assert`` at +0xc, ``vector<CLOD_band>``
  does not); a sub-object only some of them have (``possible``) is confirmed
  from the records the DWARF import named with the full Ghidra path
  (``nested_path``, built on first use from the type identities);
* does a DWARF record of a template have the member layout a plan copies
  from a live instantiation (``layout_matches``)?

Nothing here reads Ghidra.
"""

from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from .elf import Elf32File
from .mwdemangle import component_argument_types, demangle, readable_qualified, render_type, split_qualified, template_base
from .util import file_key

COMPOSITE_TAGS = ("class_type", "structure_type", "union_type")
# C++ spellings of builtins as the demangler renders them.
CXX_BUILTINS = frozenset(
    {
        "void", "bool", "char", "signed char", "unsigned char", "short", "unsigned short", "int", "unsigned int",
        "long", "unsigned long", "long long", "unsigned long long", "float", "double", "long double", "wchar_t",
        "unsigned wchar_t", "...",
    }
)
# Ghidra builtin names the type import uses for C++ builtins (EE long is 64-bit).
GHIDRA_BUILTIN = {
    "bool": "bool", "char": "char", "signed char": "schar", "unsigned char": "uchar", "short": "short",
    "unsigned short": "ushort", "int": "int", "unsigned int": "uint", "long": "longlong",
    "unsigned long": "ulonglong", "long long": "longlong", "unsigned long long": "ulonglong", "float": "float",
    "double": "double", "wchar_t": "wchar_t",
}
# Name boundaries; a builtin is not matched inside a longer builtin ("int" in "unsigned int").
_NAME_BOUNDARY_BEFORE = r"(?<![A-Za-z0-9_:])(?<!unsigned )(?<!signed )(?<!long )"
_NAME_BOUNDARY_AFTER = r"(?![A-Za-z0-9_])(?! int)(?! long)(?! char)(?! double)"


def normalized(name: str) -> str:
    """A type name without whitespace, for comparing spellings."""

    return re.sub(r"\s+", "", name)


def leaf_name(name: str) -> str:
    return split_qualified(name)[-1]


def parameter_class(text: Any) -> str | None:
    """The class a single-level pointer/reference parameter points to, else None.

    ``layout`` renders parameter types as the demangler does
    (``zdb::CDynTexList * (receiver)``, ``std::__vector_pod<...> const&``,
    ``unsigned int*``); builtins, ``void``, function types and pointers to
    pointers do not name a class sub-object.
    """

    if not isinstance(text, str) or "(" in text.replace("(receiver)", ""):
        return None
    core = text.replace("(receiver)", "").strip()
    levels = 0
    while True:
        stripped = re.sub(r"\s*\b(const|volatile)$", "", core).rstrip()
        if stripped.endswith(("*", "&")):
            levels += 1
            core = stripped[:-1].rstrip()
            continue
        core = stripped
        break
    core = re.sub(r"^(const|volatile)\s+", "", core)
    if levels != 1 or not core or core in CXX_BUILTINS or core.endswith(("*", "&")):
        return None
    return core


def substitute(text: str, arguments: list[tuple[str, str]], bare: bool = False) -> str:
    """Replace each template argument ``from`` by ``to`` in one type name.

    Qualified occurrences are replaced at name boundaries in one pass (so a
    ``to`` that contains its ``from`` is not substituted twice).  With
    ``bare`` the text is a Ghidra leaf spelling: a whole leaf equal to the
    leaf of ``from`` (``CLOD_band`` for ``zdb::CLOD_band``, ``uint`` for
    ``unsigned int``) becomes the leaf of ``to``.
    """

    if bare:
        for source, target in arguments:
            if text == _bare_leaf(source):
                return _bare_leaf(target)
    by_source = dict(arguments)
    if not by_source:
        return text
    pattern = re.compile(
        _NAME_BOUNDARY_BEFORE + "(" + "|".join(re.escape(item) for item in sorted(by_source, key=len, reverse=True)) + ")"
        + _NAME_BOUNDARY_AFTER
    )
    return pattern.sub(lambda match: by_source[match.group(1)], text)


def _bare_leaf(name: str) -> str:
    return GHIDRA_BUILTIN.get(name, leaf_name(name))


def _location(die: Any) -> int | None:
    attribute = die.attribute("location")
    value = attribute.value if attribute else None
    # DW_OP_CONST <u32> DW_OP_ADD: a constant member offset.
    if isinstance(value, bytes) and len(value) == 6 and value[0] == 0x04 and value[5] == 0x07:
        return int.from_bytes(value[1:5], "little")
    return None


class _Dwarf:
    """DWARF 1 composite records by name, with their by-value class sub-objects."""

    def __init__(self, dies: tuple[Any, ...]) -> None:
        self.dies = dies
        self.index = {die.offset: position for position, die in enumerate(dies)}
        self.by_name: dict[str, list[Any]] = defaultdict(list)
        for die in dies:
            name = die.string("name")
            if die.tag_name in COMPOSITE_TAGS and name:
                self.by_name[name].append(die)
        self._nested: dict[int, frozenset[tuple[int, str]]] = {}
        self._possible: dict[tuple[str, int | None], frozenset[tuple[int, str]]] = {}
        self._children: dict[int, list[Any]] = {}

    def die(self, offset: int) -> Any | None:
        position = self.index.get(offset)
        return None if position is None else self.dies[position]

    def children(self, die: Any) -> list[Any]:
        if die.offset in self._children:
            return self._children[die.offset]
        result = []
        sibling = die.integer("sibling")
        position = self.index[die.offset] + 1
        while sibling and position < len(self.dies) and self.dies[position].offset < sibling:
            child = self.dies[position]
            result.append(child)
            following = child.integer("sibling")
            position += 1
            if following:
                while position < len(self.dies) and self.dies[position].offset < following:
                    position += 1
        self._children[die.offset] = result
        return result

    def by_value(self, die: Any) -> Any | None:
        """The composite a member or inheritance holds by value (typedefs followed), else None."""

        target = die.integer("user_def_type")
        if target is None:
            attribute = die.attribute("mod_u_d_type")
            value = attribute.value if attribute else None
            # Only const/volatile modifiers keep the object by value.
            if isinstance(value, bytes) and len(value) >= 5 and all(byte in (3, 4) for byte in value[:-4]):
                target = int.from_bytes(value[-4:], "little")
        seen = set()
        while target is not None and target not in seen:
            seen.add(target)
            record = self.die(target)
            if record is None:
                return None
            if record.tag_name in COMPOSITE_TAGS:
                return record
            if record.tag_name != "typedef":
                return None
            target = record.integer("user_def_type")
        return None

    def is_empty(self, die: Any) -> bool:
        return (die.integer("byte_size") or 0) <= 1 and not any(child.tag_name == "member" for child in self.children(die))

    def nested_of(self, die: Any, depth: int = 0) -> frozenset[tuple[int, str]]:
        """(offset, DWARF name) of the record itself and every by-value class sub-object."""

        if die.offset in self._nested:
            return self._nested[die.offset]
        found = {(0, die.string("name") or "")}
        if depth < 24:
            for child in self.children(die):
                if child.tag_name not in ("inheritance", "member"):
                    continue
                offset = _location(child)
                target = self.by_value(child)
                if offset is None or target is None:
                    continue
                found.update((offset + inner, name) for inner, name in self.nested_of(target, depth + 1))
        result = frozenset(item for item in found if item[1])
        self._nested[die.offset] = result
        return result

    def records(self, name: str, size: int | None = None) -> list[Any]:
        return [die for die in self.by_name.get(name, []) if size is None or die.integer("byte_size") == size]

    def nested(self, name: str, size: int | None) -> frozenset[tuple[int, str]] | None:
        """Sub-objects every DWARF record ``name`` of ``size`` bytes agrees on; None without a record."""

        records = self.records(name, size)
        if not records or size is None:
            return None
        return self.common(records)

    def common(self, records: list[Any]) -> frozenset[tuple[int, str]]:
        result = None
        for die in records:
            nested = self.nested_of(die)
            result = nested if result is None else result & nested
        return result or frozenset()

    def possible(self, name: str, size: int | None) -> frozenset[tuple[int, str]]:
        """Sub-objects some, but not all, DWARF records ``name`` of ``size`` bytes have."""

        key = (name, size)
        if key not in self._possible:
            records = self.records(name, size)
            union: set[tuple[int, str]] = set()
            if len(records) > 1 and size is not None:
                for die in records:
                    union.update(self.nested_of(die))
            self._possible[key] = frozenset(union) - self.common(records) if union else frozenset()
        return self._possible[key]

    def member_layout(self, die: Any) -> tuple[frozenset[tuple[int, str]], frozenset[int]]:
        """(offset, name) of the data members and offsets of the non-empty bases of one record."""

        members, bases = set(), set()
        for child in self.children(die):
            offset = _location(child)
            if offset is None:
                continue
            if child.tag_name == "member":
                members.add((offset, child.string("name") or ""))
            elif child.tag_name == "inheritance":
                target = self.by_value(child)
                if target is not None and self.is_empty(target):
                    continue  # the type import omits empty bases
                bases.add(offset)
        return frozenset(members), frozenset(bases)


@lru_cache(maxsize=2)
def _dwarf_cached(key: tuple[str, int, int], path: str) -> _Dwarf:
    from .recon_facts import _dies_cached

    return _Dwarf(_dies_cached(key, path))


@lru_cache(maxsize=2)
def _records_by_path(key: tuple[str, int, int]) -> dict[str, tuple[int, ...]]:
    """Normalized Ghidra path -> offsets of the complete composite DIEs the DWARF import names so.

    The type identities (method, call-site and symbol evidence) take tens
    of seconds, so callers ask only when records of one DWARF name disagree.
    """

    from .import_plan import _debug_model

    _elf, dies, _parents, _by_offset, identities = _debug_model(key)
    found: dict[str, list[int]] = defaultdict(list)
    for die in dies:
        if die.tag_name not in COMPOSITE_TAGS or not die.string("name"):
            continue
        identity = identities.die_identity(die.offset)
        if identity and not identity["declaration"]:
            found[normalized(identity["ghidra_path"])].append(die.offset)
    return {path: tuple(offsets) for path, offsets in found.items()}


@lru_cache(maxsize=2)
def _symbols_cached(key: tuple[str, int, int], path: str) -> dict[str, Any]:
    return {symbol.name: demangle(symbol.name) for symbol in Elf32File(Path(path)).symbols() if symbol.name}


def _mentions(parsed: dict[str, Any] | None) -> list[tuple[str, str]]:
    """(normalized name, role) of every type a demangled symbol names."""

    found: list[tuple[str, str]] = []

    def components(parts: list[str], role: str) -> None:
        found.append((normalized(readable_qualified(parts)), role))
        for part in parts:
            for argument in component_argument_types(part):
                visit(argument, "template argument")

    def visit(value: dict[str, Any], role: str) -> None:
        kind = value.get("kind")
        if kind == "class":
            components(value["components"], role)
        elif kind == "function":
            for item in value.get("params") or []:
                visit(item, role)
            visit(value["result"], role)
        elif kind == "array":
            visit(value["element"], role)
        elif kind == "member_pointer":
            components(value["owner"], role)
            visit(value["pointee"], role)

    if not parsed:
        return found
    if parsed.get("qualifier"):
        components(list(parsed["qualifier"]), "qualifier")
    for value in parsed.get("params") or []:
        visit(value, "parameter")
    return found


class TypeEvidence:
    """Lazily loaded ELF symbols and DWARF records of the reference ELF under ``root``."""

    def __init__(self, root: Path) -> None:
        self.path = root / "support" / "socom.elf"
        self._dwarf: _Dwarf | None = None
        self._symbols: dict[str, Any] | None = None

    @property
    def dwarf(self) -> _Dwarf:
        if self._dwarf is None:
            self._dwarf = _dwarf_cached(file_key(self.path), str(self.path))
        return self._dwarf

    @property
    def symbols(self) -> dict[str, Any]:
        if self._symbols is None:
            self._symbols = _symbols_cached(file_key(self.path), str(self.path))
        return self._symbols

    def readable(self, symbol: str) -> str:
        parsed = self.symbols.get(symbol)
        if not parsed:
            return symbol
        qualifier = readable_qualified(list(parsed.get("qualifier") or []))
        name = f"{qualifier}::{parsed['name']}" if qualifier else parsed["name"]
        if parsed.get("params") is None:
            return name
        return f"{name}({', '.join(render_type(value) for value in parsed['params'])})"

    def name_problems(self, name: str, provenance: str, evidence: Any, where: str, forward: bool = False) -> list[str]:
        """Whether ``name_evidence`` proves the qualified ``name`` (mangled symbol, RTTI or DWARF)."""

        if not isinstance(evidence, list) or not evidence or not all(isinstance(item, str) for item in evidence):
            return [f"{where}: name_provenance {provenance} cites name_evidence (a list of strings)"]
        problems = []
        wanted = normalized(name)
        if provenance == "mangled-symbol":
            for symbol in evidence:
                if symbol not in self.symbols:
                    problems.append(f"{where}: name evidence {symbol} is not an ELF symbol")
                elif wanted not in {mention for mention, _role in _mentions(self.symbols[symbol])}:
                    problems.append(f"{where}: {symbol} ({self.readable(symbol)}) does not name {name}")
        elif provenance == "rtti":
            from .type_layout import mangled_qualifier
            from .util import SocomError

            try:
                expected = "__RTTI__" + mangled_qualifier(split_qualified(name))
            except SocomError:
                return [f"{where}: no RTTI symbol can name the template {name}"]
            if expected not in evidence or expected not in self.symbols:
                problems.append(f"{where}: rtti provenance cites the RTTI object {expected}, which must exist")
        elif provenance == "dwarf":
            wanted_leaf = template_base(leaf_name(name))
            for text in evidence:
                try:
                    die = self.dwarf.die(int(text, 16))
                except ValueError:
                    die = None
                if die is None or die.tag_name not in COMPOSITE_TAGS or die.string("name") != wanted_leaf:
                    problems.append(f"{where}: name evidence {text} is not a DWARF class/struct/union record named {wanted_leaf}")
                elif forward and die.integer("byte_size") and self.dwarf.children(die):
                    problems.append(
                        f"{where}: DWARF {text} defines {wanted_leaf} ({die.integer('byte_size')} bytes); plan or import "
                        "its layout instead of a forward declaration"
                    )
        else:
            problems.append(f"{where}: {provenance} is not a name proof")
        return problems

    def nested(self, name: str, size: int | None) -> frozenset[tuple[int, str]] | None:
        """DWARF sub-objects of a type by its DWARF name (template arguments and ``@hash`` dropped)."""

        return self.dwarf.nested(template_base(name).split("@", 1)[0], size)

    def possible(self, name: str, size: int | None) -> frozenset[tuple[int, str]]:
        """Sub-objects only some DWARF records of that name have (see ``nested_path``)."""

        return self.dwarf.possible(template_base(name).split("@", 1)[0], size)

    def nested_path(self, path: str, size: int | None) -> frozenset[tuple[int, str]] | None:
        """DWARF sub-objects of the records the DWARF import named ``path`` (a /project Ghidra path); None without one."""

        offsets = _records_by_path(file_key(self.path)).get(normalized(path), ())
        records = [
            die for offset in offsets
            if (die := self.dwarf.die(offset)) is not None and (size is None or die.integer("byte_size") == size)
        ]
        return self.dwarf.common(records) if records else None

    def layout_matches(self, template: str, size: int, members: set[tuple[int, str]], bases: set[int]) -> list[int]:
        """Offsets of DWARF records ``template`` of ``size`` bytes with exactly these members and bases."""

        found = []
        for die in self.dwarf.records(template, size):
            die_members, die_bases = self.dwarf.member_layout(die)
            if die_members == members and die_bases == bases:
                found.append(die.offset)
        return found


__all__ = [
    "CXX_BUILTINS",
    "GHIDRA_BUILTIN",
    "TypeEvidence",
    "leaf_name",
    "normalized",
    "parameter_class",
    "substitute",
]
