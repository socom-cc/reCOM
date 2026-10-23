"""Code-derived type plans: reviewed layouts for classes without DWARF records.

A planner writes a plan from ``recon layout`` evidence (``type_layout``); the
plan is file-only and lives under ``build/type-plans``.  ``validate_type_plan``
regenerates the layout evidence from the ELF and checks every field, base,
vptr and padding region against it; ``render_type_plan`` prints the review
table; ``build_type_plan_program`` translates an accepted plan into the type
apply program format that ``type_apply.execute_apply_program`` executes (the
same executor, temporary names, layout read-back and final rename as the
DWARF type import).

Plan format (``kind`` socom-code-type-plan, schema 1)::

    {
      "kind": "socom-code-type-plan", "schema_version": 1,
      "work_item_id": "socom:work:type-plan-zdb-cvisual",
      "target": {"source_sha256": "<reference ELF>"},
      "layout": {"class": "zdb::CVisual", "with_derived": true, "sha256": "<recon layout JSON digest>"},
      "naming_survey": ["zdb::CNode (DWARF): m_parent, m_child, m_visual, m_name ..."],
      "types": [
        {"name": "zdb::CVisual", "kind": "class", "category": "/project/zdb",
         "name_provenance": "elf-symbol", "size": 104, "alignment": 4,
         "bases": [{"type": "zdb::tag_VIS_PARAMS", "offset": 0}],
         "vptr": {"offset": 32, "type": "zdb::CVisual_vtbl *", "evidence": ["0x30de70"]},
         "fields": [{"offset": 24, "size": 4, "type": "int", "name": "m_refCount",
                     "provenance": "invented-provisional", "evidence": ["0x30d290", "0x30d298"]}],
         "padding": [], "outside_accesses": [], "unresolved": []},
        {"name": "zdb::CVisual_vtbl", "kind": "vtable", "category": "/project/zdb",
         "name_provenance": "invented-provisional", "size": 0, "opaque": true,
         "opaque_reason": "slot return types are not encoded in the mangled names"},
        {"name": "zdb::tag_DETAIL_PARAMS", "kind": "forward", "category": "/project/zdb",
         "name_provenance": "mangled-symbol",
         "name_evidence": ["VuDetailMap__Q23zdb7CVisualFP8_word128PQ23zdb17tag_DETAIL_PARAMS"],
         "reason": "reached only through CVisual+0x60; its record layout is not planned"},
        {"name": "std::__vector_deleter<zdb::CMesh::CMeshLOD, std::allocator<zdb::CMesh::CMeshLOD>>",
         "kind": "class", "category": "/project/std", "name_provenance": "mangled-symbol",
         "name_evidence": ["data__Q23std80__vector_deleter<Q33zdb5CMesh8CMeshLOD,Q23std32allocator<Q33zdb5CMesh8CMeshLOD>>Fv"],
         "size": 12, "alignment": 4,
         "instantiation": {
           "source": "/project/std/__vector_deleter<zdb::CLOD_band, std::allocator<zdb::CLOD_band>>",
           "arguments": [{"from": "zdb::CLOD_band", "to": "zdb::CMesh::CMeshLOD"}],
           "source_size": 12,
           "source_layout": [[0, 4, "compressed_pair@30d44a8521", "capacity_"], [4, 4, "uint", "size_"],
                             [8, 4, "CLOD_band *", "data_"]]},
         "fields": [{"offset": 0, "size": 4, "type": "/project/unresolved/compressed_pair@30d44a8521",
                     "name": "capacity_", "provenance": "template-copy"}, "..."]}
      ]
    }

A plain struct named only by mangled parameter types (no member function,
vtable, RTTI or DWARF record; ``recon layout --struct``) has ``"struct": true``
in ``layout`` and in its tracker item's batch.  Its layout row lists the
naming symbols (``name_evidence``), so the plan names it ``mangled-symbol``
(never ``elf-symbol``) and cites them; caller-built objects add evidence
(``type_layout``), and its size is cited in ``size_evidence``.

A ``forward`` type is a declaration only: a qualified name proven by mangled
symbols (the type is a member qualifier, parameter type or template argument),
an RTTI object or a DWARF record, with no size, bases or fields.  It may only be
pointed to; the program creates it first, as an empty structure (as the DWARF
import created declaration-only types), and the live check refuses one whose
name already exists.

An ``instantiation`` copies the layout of an existing live instantiation of
the same template (same namespace and template name; the plan's name is the
source's with each argument ``from`` replaced by ``to``).  ``source_layout``
records the source exactly as ``get_struct_layout`` reports it; each row
becomes a base (a ``super_<identifier>`` component) or a ``template-copy``
field of the same name, offset and size, typed as the source member with the
arguments substituted (so ``CLOD_band *`` becomes ``zdb::CMesh::CMeshLOD *``).
A DWARF record of the template must have the same members and bases; the live
check compares ``source_layout`` with the live source.  Accesses inside the
instantiation are checked against the copied members like any other field.
A ``template-instantiation`` name's arguments are plan types, builtins, or
existing live types: a qualified name the ELF names (a mangled symbol or a
DWARF record), sharing its leaf with no plan type, whose live path is its
namespace category and leaf (``_word128`` is ``/project/_word128``).  The
program lists those paths (``template_arguments``) and the live check proves
each name resolves to exactly that path, as for live member types.

Type spellings: Ghidra builtins (``uint``, ``uchar``, ``longlong``, ``uint16``
...), ``undefined1/2/4/8`` only where every access is neutral, plan types by
their qualified name, and existing live types by their full Ghidra path
(``/project/std/__vector_pod<unsigned int, std::allocator<unsigned int>>``);
``*`` pointers and ``[n]`` arrays follow the base.  A field with
``bit_offset``/``bit_size`` is a bitfield (least-significant-bit position in
its little-endian storage unit at ``offset``/``size``).  ``void *`` is a
placeholder as a field type and as a template argument alike; as a template
argument (``vector<void *>``) its elements lie beyond the evidence the
validator matches, so the field records why in ``unresolved`` unless a call
passes the member as exactly that type.

The loads and stores of a compiler-style copy (``operator=``, a copy
constructor, or such a copy inlined: a same-width value moved unchanged
between the same offset of two objects) are width-only evidence: they prove
the unit's width, not int, float, sign or pointer, so a member they alone
type stays ``undefinedN``.  A bulk copy (one function's same-width chunks
tiling a whole planned object) proves neither; ``show`` labels both.  So
does a bulk zero-fill: one function's stores of the constant zero into one
object that tile an extent wholly covering more than one planned member, or
a zero store wider than the member it hits (``sq zero`` over four words),
prove only that the extent is written, not the width or type of what they
cover; a zero store exactly matching one member is still its width evidence.

A call that passes an object address as a class pointer or reference (a
constructor or method receiver) proves a sub-object of that class there.  The
validator matches each such call against the plan's sub-objects (plan types,
and the DWARF bases and members of by-value live types, empty bases at an
object's end included), so a call on a sub-object belongs to that sub-object,
and one that no sub-object explains is a problem.  DWARF records of a
template share one name; a sub-object only some of them have counts when the
records the DWARF import named with the live type's path (an instantiation's
source path) have it.  A call whose parameter type the layout could not derive
(``parameter_unknown``) is a problem unless the notes or unresolved text of a
member whose extent holds the address (its end included) cite the call site
(``0x30f454``, or a range ``0x30f450-0x30f488``); a register the callee does
not take (``no_parameter``) is not evidence.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .batch_apply import BUILTIN_SIZES
from .constants import REFERENCE_SHA256
from .mwdemangle import readable_component, split_qualified, template_base
from .type_apply import (
    ANON_FIELD_PREFIX,
    APPLY_PROGRAM_KIND,
    APPLY_PROGRAM_SCHEMA,
    C_IDENTIFIER,
    C_RESERVED,
    TEMP_PREFIX,
    _identifier,
)
from .type_layout import NEUTRAL_KINDS, class_layout
from .type_plan_evidence import (
    BULK,
    CXX_BUILTINS,
    MEMBER_WISE,
    ZERO_FILL,
    TypeEvidence,
    copy_accesses,
    leaf_name,
    normalized,
    parameter_class,
    substitute,
    void_pointer_argument,
    zero_fills,
)
from .util import SocomError, canonical_json, load_json, sha256_file

TYPE_PLAN_KIND = "socom-code-type-plan"
TYPE_PLAN_SCHEMA = 1
TYPE_PLAN_PREFIX = "socom:work:type-plan-"
TYPE_PLAN_RESOURCES = ["build/type-plans"]
INVENTED = "invented-provisional"
TEMPLATE_NAME = "template-instantiation"
TEMPLATE_COPY = "template-copy"
NAME_PROOFS = ("mangled-symbol", "rtti", "dwarf")
NAME_PROVENANCES = ("elf-symbol", *NAME_PROOFS, TEMPLATE_NAME, INVENTED)
FIELD_PROVENANCES = (INVENTED, "elf-string", "elf-symbol", TEMPLATE_COPY)
TYPE_KINDS = ("class", "struct", "vtable", "forward")
PROVENANCE_KEY = (
    ("elf-symbol", "the name of a layout class (.symtab member qualifier and RTTI)"),
    ("mangled-symbol", "named by the cited mangled ELF symbols (member qualifier, parameter type or template argument)"),
    ("rtti", "named by the cited RTTI object"),
    ("dwarf", "named by the cited DWARF record (its leaf name)"),
    (TEMPLATE_NAME, "the source instantiation's name with the plan's template arguments substituted"),
    (TEMPLATE_COPY, "a member name copied from the source instantiation"),
    ("elf-string", "a member name from an ELF string (cited in name_evidence)"),
    (INVENTED, "invented by the planner; review before use"),
)
VPTR_NAME = "__vt"
# Invented member names: m_ + lower snake_case (user rule, 2026-10-23), e.g. m_ref_count, m_vtype.
FIELD_NAME = re.compile(r"^m_[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
HELPER_NAME = re.compile(r"^tag_[A-Za-z0-9_]+$")
UNDEFINED_SIZES = {"undefined1": 1, "undefined2": 2, "undefined4": 4, "undefined8": 8}
SIZES = {name: size for name, size in BUILTIN_SIZES.items() if size} | UNDEFINED_SIZES
SIGNED = frozenset({"char", "schar", "short", "int", "longlong"})
UNSIGNED = frozenset({"uchar", "ushort", "uint", "ulonglong", "bool", "uint16"})
FLOATS = frozenset({"float", "double"})
C_SPELLING = {
    "char": "char", "schar": "signed char", "uchar": "unsigned char", "short": "short",
    "ushort": "unsigned short", "int": "int", "uint": "unsigned int", "longlong": "long long",
    "ulonglong": "unsigned long long", "float": "float", "double": "double", "uint16": "uint16",
}
DECISIONS = (
    "Types come from a reviewed code-derived plan: every field, base and vptr cites ELF layout evidence "
    "(recon layout); invented names are marked invented-provisional in the plan.",
    "A base class is a component at its RTTI base-list offset named by the bare base type name (template "
    "arguments dropped); the vtable pointer is a component named __vt.",
    "A vtable type whose slot function types are not all proven is created opaque (an empty struct) so the "
    "vptr can point to it without a void * placeholder.",
    "A forward declaration (a name proven by mangled symbols, RTTI or DWARF, without layout evidence) is "
    "created first as an empty structure, as the DWARF import created declaration-only types; it is only "
    "pointed to.",
    "A template instantiation copies the members of an existing live instantiation of the same template "
    "with the template arguments substituted; the dry run proves the source's live layout equals the copy's "
    "recorded source layout.",
    "Composites with bitfields or 128-bit members are created by one self-contained #pragma pack(1) C "
    "import, with unnamed padding for gaps; others use explicit field offsets.",
    "Existing live types are referenced by bare name; the dry run proves each resolves to exactly the "
    "plan's Ghidra path.",
)


def type_plan_slug(class_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", class_name.lower().replace("::", "-")).strip("-")


def type_plan_item_id(class_name: str) -> str:
    return f"{TYPE_PLAN_PREFIX}{type_plan_slug(class_name)}"


def layout_sha256(layout: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(layout).encode("utf-8")).hexdigest()


def plan_layout(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """Regenerate the layout evidence a plan's ``layout`` spec names (class, derived scope, plain struct)."""

    return class_layout(root, str(spec.get("class")), bool(spec.get("with_derived")), struct=bool(spec.get("struct")))


def _hex(value: int) -> str:
    return f"0x{value:x}" if value >= 0 else f"-0x{-value:x}"


def _leaf(name: str) -> str:
    if name.startswith("/"):
        return name.rsplit("/", 1)[1]
    return split_qualified(name)[-1]


def expected_category(name: str) -> str:
    """The stable project category of a qualified class name (its namespaces)."""

    parts = split_qualified(name)[:-1]
    return "/project" + "".join(f"/{part}" for part in parts)


def parse_type(text: Any) -> dict[str, Any] | None:
    """Split ``base * *[n]`` into base, pointer count and array extents (template arguments stay in the base)."""

    if not isinstance(text, str):
        return None
    rest = text.strip()
    arrays: list[int] = []
    while True:
        match = re.search(r"\[(\d+)\]\s*$", rest)
        if not match:
            break
        arrays.insert(0, int(match.group(1)))
        rest = rest[: match.start()].rstrip()
    pointers = 0
    while rest.endswith("*"):
        pointers += 1
        rest = rest[:-1].rstrip()
    depth = 0
    for char in rest:
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif char in "[]" or (char == "*" and depth == 0):
            return None
    if not rest or depth:
        return None
    return {"base": rest, "pointers": pointers, "arrays": arrays}


def _base_component_name(type_name: Any) -> str:
    """A base component's name: the bare base type name, template arguments dropped."""

    return template_base(_leaf(str(type_name)))


def _count(parsed: dict[str, Any]) -> int:
    count = 1
    for value in parsed["arrays"]:
        count *= value
    return count


class _Plan:
    """Plan types by name, with sizes, alignments, evidence windows and sub-objects."""

    def __init__(self, plan: dict[str, Any], evidence: TypeEvidence | None = None) -> None:
        self.plan = plan
        self.evidence = evidence
        self.types: dict[str, dict[str, Any]] = {}
        for row in plan.get("types") or []:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                self.types.setdefault(row["name"], row)
        self.normalized_types = {normalized(name): name for name in self.types}

    def kind(self, name: str) -> Any:
        return (self.types.get(name) or {}).get("kind")

    def size_of(self, parsed: dict[str, Any] | None, declared: Any = None) -> int | None:
        if parsed is None:
            return None
        count = _count(parsed)
        if parsed["pointers"]:
            return 4 * count
        base = parsed["base"]
        if base in SIZES:
            return SIZES[base] * count
        if base in self.types and self.kind(base) != "forward" and isinstance(self.types[base].get("size"), int):
            return self.types[base]["size"] * count
        return declared if isinstance(declared, int) else None

    def bare(self, text: Any) -> str | None:
        """The spelling Ghidra's layout read-back gives a plan type spelling (leaf names, ``X *``)."""

        parsed = parse_type(text)
        if parsed is None:
            return None
        base = parsed["base"]
        if base in self.types:
            leaf = _leaf(base)
        elif base.startswith("/"):
            leaf = base.rsplit("/", 1)[1]
        else:
            leaf = base
        return leaf + " *" * parsed["pointers"] + "".join(f"[{count}]" for count in parsed["arrays"])

    def subobjects(self, text: Any, size: Any, depth: int = 0) -> tuple[list[tuple[int, str, Any]], list[tuple[int, int]]]:
        """Class sub-objects of a by-value type spelling: (offset, name, match mode), and unknown regions.

        Plan types give their bases and composite members (qualified names);
        a live type gives itself (its leaf name) and, from DWARF, every base
        and by-value member (DWARF names, template arguments dropped).  A
        sub-object only some same-named DWARF records have carries the mode
        ``("dwarf", path, size, offset)`` for ``matches`` to confirm.  A live
        type without a DWARF record is an unknown region.
        """

        parsed = parse_type(text)
        if parsed is None or parsed["pointers"] or depth > 24:
            return [], []
        base = parsed["base"]
        if parsed["arrays"]:
            count = _count(parsed)
            element = {"base": base, "pointers": 0, "arrays": []}
            stride = self.size_of(element, size // count if isinstance(size, int) and count else None)
            if not stride or count > 4096:
                return [], ([(0, size)] if isinstance(size, int) else [])
            inner, unknown = self.subobjects(base, stride, depth + 1)
            return (
                [(index * stride + offset, name, mode) for index in range(count) for offset, name, mode in inner],
                [(index * stride + low, index * stride + high) for index in range(count) for low, high in unknown],
            )
        if base in SIZES or base == "void":
            return [], []
        row = self.types.get(base)
        if row is not None:
            if row.get("kind") in ("forward", "vtable"):
                return [], []
            entries: list[tuple[int, str, str]] = [(0, base, "qualified")]
            unknown: list[tuple[int, int]] = []
            for offset, extent, role, entry in self.components(row):
                if role not in ("base", "field") or not isinstance(offset, int):
                    continue
                inner, gaps = self.subobjects(entry.get("type"), extent, depth + 1)
                entries.extend((offset + inner_offset, name, mode) for inner_offset, name, mode in inner)
                unknown.extend((offset + low, offset + high) for low, high in gaps)
            spec = row.get("instantiation")
            if isinstance(spec, dict) and self.evidence is not None:
                # Empty bases (allocator, compile_assert) are omitted from copied layouts; DWARF keeps them.
                own = row.get("size") if isinstance(row.get("size"), int) else None
                found = self.evidence.nested(_leaf(base), own)
                entries.extend((offset, name, "base") for offset, name in sorted(found or ()))
                source_size = spec.get("source_size") if isinstance(spec.get("source_size"), int) else own
                if isinstance(spec.get("source"), str):
                    entries.extend(
                        (offset, name, ("dwarf", spec["source"], source_size, offset))
                        for offset, name in sorted(self.evidence.possible(_leaf(base), own))
                    )
            return entries, unknown
        if base.startswith("/"):
            leaf = base.rsplit("/", 1)[1]
            entries = [(0, leaf, "leaf")]
            known = size if isinstance(size, int) else None
            found = self.evidence.nested(leaf, known) if self.evidence else None
            if found is None:
                return entries, ([(0, size)] if isinstance(size, int) else [])
            entries.extend((offset, name, "base") for offset, name in sorted(found))
            entries.extend((offset, name, ("dwarf", base, known, offset)) for offset, name in sorted(self.evidence.possible(leaf, known)))
            return entries, []
        return [], []

    def matches(self, target: str, name: str, mode: Any) -> bool:
        """Whether a parameter class names a sub-object entry; a DWARF-possible entry is confirmed by path."""

        if not isinstance(mode, tuple):
            return _names_match(target, name, mode)
        _kind, path, size, offset = mode
        if self.evidence is None or not _names_match(target, name, "base"):
            return False
        precise = self.evidence.nested_path(path, size)
        return precise is not None and (offset, name) in precise

    def names(self, target: str, entries: Any) -> bool:
        """Whether any (name, mode) entry matches; definite entries first, so a DWARF path is read only when needed."""

        entries = list(entries)
        ordered = [entry for entry in entries if not isinstance(entry[1], tuple)] + [entry for entry in entries if isinstance(entry[1], tuple)]
        return any(self.matches(target, name, mode) for name, mode in ordered)

    def notes_at(self, name: str, offset: int, depth: int = 0) -> list[str]:
        """Notes and unresolved text of every base or field whose extent holds ``offset`` (its end included)."""

        row = self.types.get(name)
        if row is None or depth > 24:
            return []
        texts: list[str] = []
        for start, extent, role, entry in self.components(row):
            if role not in ("base", "field") or not isinstance(start, int) or not isinstance(extent, int):
                continue
            if not start <= offset <= start + extent:
                continue
            texts.extend(_texts(entry.get("notes")) + _texts(entry.get("unresolved")))
            parsed = parse_type(entry.get("type"))
            if parsed and not parsed["pointers"] and not parsed["arrays"] and parsed["base"] in self.types:
                texts.extend(self.notes_at(parsed["base"], offset - start, depth + 1))
        return texts

    def references(self) -> dict[str, list[str]]:
        """Plan type name -> where it is named through a pointer (fields, vptrs, instantiation arguments)."""

        found: dict[str, list[str]] = defaultdict(list)
        for name, row in self.types.items():
            for field in row.get("fields") or []:
                parsed = parse_type(field.get("type"))
                if parsed and parsed["pointers"] and parsed["base"] in self.types:
                    found[parsed["base"]].append(f"{name}.{field.get('name')}")
            vptr = row.get("vptr")
            parsed = parse_type(vptr.get("type")) if isinstance(vptr, dict) else None
            if parsed and parsed["pointers"] and parsed["base"] in self.types:
                found[parsed["base"]].append(f"{name}.{VPTR_NAME}")
            spec = row.get("instantiation")
            for argument in (spec.get("arguments") or []) if isinstance(spec, dict) else []:
                target = self.normalized_types.get(normalized(str((argument or {}).get("to", ""))))
                if target:
                    found[target].append(f"{name} template argument")
        return found

    def align_of(self, parsed: dict[str, Any] | None) -> int | None:
        if parsed is None:
            return None
        if parsed["pointers"]:
            return 4
        base = parsed["base"]
        if base in SIZES:
            return 1 if base in UNDEFINED_SIZES else min(SIZES[base], 16)
        if base in self.types:
            value = self.types[base].get("alignment")
            return value if isinstance(value, int) else None
        return None

    def composite(self, parsed: dict[str, Any] | None) -> bool:
        return bool(parsed) and not parsed["pointers"] and parsed["base"] not in SIZES and parsed["base"] != "void"

    def components(self, row: dict[str, Any]) -> list[tuple[int, int, str, Any]]:
        """(offset, size, role, entry) of every base, vptr, field unit and padding."""

        result = []
        for base in row.get("bases") or []:
            size = self.size_of(parse_type(base.get("type")), base.get("size"))
            result.append((base.get("offset"), size, "base", base))
        vptr = row.get("vptr")
        if isinstance(vptr, dict):
            result.append((vptr.get("offset"), 4, "vptr", vptr))
        units: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
        for field in row.get("fields") or []:
            if "bit_size" in field or "bit_offset" in field:
                units[(field.get("offset"), field.get("size"))].append(field)
            else:
                result.append((field.get("offset"), field.get("size"), "field", field))
        for (offset, size), fields in units.items():
            result.append((offset, size, "bits", fields))
        for pad in row.get("padding") or []:
            result.append((pad.get("offset"), pad.get("size"), "padding", pad))
        return result

    def windows(self, layout_classes: set[str]) -> dict[str, set[tuple[str, int]]]:
        """Per plan type, every (layout class, offset) at which an instance of it lies."""

        windows: dict[str, set[tuple[str, int]]] = defaultdict(set)
        for name in self.types:
            if name in layout_classes:
                windows[name].add((name, 0))
        for _ in range(16):
            changed = False
            for name, row in self.types.items():
                for offset, _size, role, entry in self.components(row):
                    if role == "base":
                        target = parse_type(entry.get("type"))
                    elif role == "field":
                        target = parse_type(entry.get("type"))
                    else:
                        continue
                    if not target or target["pointers"] or target["base"] not in self.types or not isinstance(offset, int):
                        continue
                    stride = self.size_of({"base": target["base"], "pointers": 0, "arrays": []}) or 0
                    count = 1
                    for value in target["arrays"]:
                        count *= value
                    for cls, delta in list(windows.get(name, ())):
                        for index in range(count):
                            item = (cls, delta + offset + index * stride)
                            if item not in windows[target["base"]]:
                                windows[target["base"]].add(item)
                                changed = True
            if not changed:
                break
        return windows


def _site_extent(site: dict[str, Any]) -> int:
    return int(site.get("width") or 1) if not site.get("pointer") else 4


def _sites_in(index: dict[int, list[dict[str, Any]]], low: int, high: int) -> list[tuple[int, dict[str, Any]]]:
    return [(offset, site) for offset, sites in index.items() if low <= offset < high for site in sites]


def _compatible(site: dict[str, Any], parsed: dict[str, Any], size: int | None) -> bool:
    """Whether one evidence site is consistent with a scalar field type."""

    access = site.get("access", "")
    if access == "address-passed":
        return True  # the field's address: any type (its parameter type is checked separately)
    if site.get("pointer"):
        return parsed["pointers"] > 0
    width = site.get("width")
    kind = site.get("kind")
    if width is not None and size is not None and width != size:
        return False
    if kind in NEUTRAL_KINDS or kind is None:
        return True
    if parsed["pointers"]:
        return kind == "int" and width == 4
    base = parsed["base"]
    if base in UNDEFINED_SIZES:
        return False
    if base in FLOATS:
        return kind == "float"
    if size == 16:
        return kind in ("int128", "vu")
    if size == 8:
        return kind == "int64"
    return kind == "int"


_STORED_PARAMETER = re.compile(r"^entry [a-z0-9]+ \((?P<type>.+)\)$")


def _stored_parameter_type(site: dict[str, Any]) -> str | None:
    """The pointer type of a typed entry parameter stored unchanged (``entry a1 (zdb::CMesh*)``), else None."""

    match = _STORED_PARAMETER.match(str(site.get("value", ""))) if site.get("access") == "store" else None
    if not match:
        return None
    text = match.group("type").removesuffix(" this").strip()
    if "void" in text or not text.endswith(("*", "&")):
        return None
    return text


def _strength(site: dict[str, Any]) -> bool:
    """A site that says more than its width (not a neutral store or copy)."""

    return bool(site.get("pointer") or site.get("parameter_type") or (site.get("kind") not in NEUTRAL_KINDS and site.get("kind")))


def validate_type_plan(
    root: Path, tracker: dict[str, Any] | None, plan: dict[str, Any], layout: dict[str, Any] | None = None
) -> list[str]:
    problems: list[str] = []
    if plan.get("kind") != TYPE_PLAN_KIND or plan.get("schema_version") != TYPE_PLAN_SCHEMA:
        return [f"not a schema {TYPE_PLAN_SCHEMA} {TYPE_PLAN_KIND}"]
    if (plan.get("target") or {}).get("source_sha256") != REFERENCE_SHA256:
        problems.append("the plan targets a different ELF")
    spec = plan.get("layout") or {}
    class_name = spec.get("class")
    if not isinstance(class_name, str):
        return problems + ["layout.class is missing"]
    expected_id = type_plan_item_id(class_name)
    if plan.get("work_item_id") != expected_id:
        problems.append(f"work_item_id must be {expected_id}")
    if tracker is not None:
        item = next((row for row in tracker.get("work_items", []) if row.get("id") == plan.get("work_item_id")), None)
        if item is None or item.get("kind") != "recon-type-plan":
            problems.append(f"{plan.get('work_item_id')} is not a recon-type-plan item in the tracker")
        elif (
            (item.get("batch") or {}).get("class") != class_name
            or bool((item.get("batch") or {}).get("with_derived")) != bool(spec.get("with_derived"))
            or bool((item.get("batch") or {}).get("struct")) != bool(spec.get("struct"))
        ):
            problems.append(f"{plan.get('work_item_id')} plans a different class, derived scope or struct mode")
    if layout is None:
        layout = plan_layout(root, spec)
    if spec.get("sha256") != layout_sha256(layout):
        problems.append(
            f"layout.sha256 differs from the regenerated recon layout evidence ({layout_sha256(layout)}); "
            "regenerate the evidence and re-review the plan"
        )
    by_class = {row["class"]: row for row in layout["classes"]}
    index: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for row in layout["classes"]:
        offsets = {entry["offset"]: list(entry["sites"]) for entry in row["offsets"]}
        index[row["class"]] = offsets
    model = _Plan(plan, TypeEvidence(root))
    names = [row.get("name") for row in plan.get("types") or []]
    if len(names) != len(set(names)):
        problems.append("type names repeat")
    paths = [f"{row.get('category')}/{_leaf(str(row.get('name')))}".casefold() for row in plan.get("types") or []]
    if len(paths) != len(set(paths)):
        problems.append("Ghidra paths repeat (ignoring case)")
    if class_name not in model.types:
        problems.append(f"the plan does not define the requested class {class_name}")
    invented = False
    windows = model.windows(set(by_class))
    copies = _neutral_accesses(model, layout["classes"], windows)
    claims, claim_problems = _subobject_claims(model, by_class, index)
    problems.extend(claim_problems)
    references = model.references()
    for row in plan.get("types") or []:
        name = row.get("name")
        where = f"type {name}"
        if not isinstance(name, str) or not name:
            problems.append("a type has no name")
            continue
        kind = row.get("kind")
        if kind not in TYPE_KINDS:
            problems.append(f"{where}: kind must be one of {list(TYPE_KINDS)}")
            continue
        provenance = row.get("name_provenance")
        if provenance not in NAME_PROVENANCES:
            problems.append(f"{where}: name_provenance must be one of {list(NAME_PROVENANCES)}")
        leaf = _leaf(name)
        if provenance == "elf-symbol" and name not in by_class:
            problems.append(f"{where}: elf-symbol names must be a class in the layout evidence")
        if provenance == "elf-symbol" and "name_evidence" in (by_class.get(name) or {}):
            problems.append(f"{where}: a plain struct is named by mangled parameter types; cite them as mangled-symbol name_evidence")
        if provenance in NAME_PROOFS:
            problems.extend(model.evidence.name_problems(name, provenance, row.get("name_evidence"), where, forward=kind == "forward"))
        if provenance == TEMPLATE_NAME and row.get("instantiation") is None:
            problems.append(f"{where}: a {TEMPLATE_NAME} name belongs to a type with an instantiation")
        if provenance == INVENTED:
            invented = True
            if kind == "struct" and not HELPER_NAME.match(leaf):
                problems.append(f"{where}: an invented helper struct name starts with tag_")
            if kind == "class" and not leaf.startswith("C"):
                problems.append(f"{where}: an invented class name starts with C")
        if kind == "vtable":
            owner = name[: -len("_vtbl")] if name.endswith("_vtbl") else None
            if owner is None or owner not in by_class or not by_class[owner]["vtable"]:
                problems.append(f"{where}: a vtable type is named <Class>_vtbl for a layout class with a vtable")
        category = row.get("category")
        wanted = expected_category(name)
        if category != wanted:
            problems.append(f"{where}: category must be {wanted}")
        if kind == "vtable":
            problems.extend(_vtable_problems(row, by_class, where))
            continue
        if kind == "forward":
            problems.extend(_forward_problems(row, where, by_class, references))
            continue
        problems.extend(_type_problems(model, row, where, by_class, index, windows.get(name, set()), claims, copies))
        if row.get("instantiation") is not None:
            problems.extend(_instantiation_problems(model, row, where))
    if invented and not plan.get("naming_survey"):
        problems.append("invented names need a naming_survey of neighbouring zdb DWARF names")
    for row in plan.get("types") or []:
        for field in row.get("fields") or []:
            parsed = parse_type(field.get("type"))
            if parsed and parsed["base"].startswith("/") and not parsed["base"].startswith("/project/"):
                problems.append(f"type {row.get('name')} field {field.get('name')}: live types are /project paths")
    return problems


def _extents(model: _Plan, windows: dict[str, set[tuple[str, int]]]) -> dict[str, list[tuple[int, int]]]:
    """Per layout class, the (offset, size) of every planned object lying in it."""

    extents: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for name, places in windows.items():
        size = model.types[name].get("size") if name in model.types else None
        if isinstance(size, int) and size > 0:
            for cls, delta in sorted(places):
                extents[cls].append((delta, size))
    return extents


def _leaves(model: _Plan, windows: dict[str, set[tuple[str, int]]]) -> dict[str, list[tuple[int, int, int]]]:
    """Per layout class, the (offset, size, element size) of every planned leaf member.

    A leaf is a scalar, pointer, array, bitfield unit, or a by-value type
    the plan does not lay out (a live type); a by-value plan type
    contributes its own members through its windows instead.  The element
    size is an array's element's (the size otherwise).
    """

    leaves: dict[str, set[tuple[int, int, int]]] = defaultdict(set)
    for name, places in windows.items():
        row = model.types.get(name)
        if row is None or row.get("kind") not in ("class", "struct"):
            continue
        for field in row.get("fields") or []:
            offset, size = field.get("offset"), field.get("size")
            parsed = parse_type(field.get("type"))
            if not isinstance(offset, int) or not isinstance(size, int) or size <= 0 or parsed is None:
                continue
            if model.composite(parsed) and model.kind(parsed["base"]) in ("class", "struct"):
                continue  # the member type's own fields are the leaves
            count = _count(parsed)
            element = size // count if count > 1 and size % count == 0 else size
            for cls, delta in places:
                leaves[cls].add((delta + offset, size, element))
    return {cls: sorted(values) for cls, values in leaves.items()}


def _neutral_accesses(
    model: _Plan, classes: list[dict[str, Any]], windows: dict[str, set[tuple[str, int]]]
) -> dict[tuple[str, int, str, str], str]:
    """(class, offset, site, access) -> ``member-wise`` or ``bulk`` (copies) or ``zero-fill``."""

    kinds = copy_accesses(classes, _extents(model, windows))
    for key in zero_fills(classes, _leaves(model, windows)):
        kinds.setdefault(key, ZERO_FILL)
    return kinds


def _copy_key(cls: str, offset: int, site: dict[str, Any]) -> tuple[str, int, str, str]:
    return (cls, offset, site["site"], site.get("access", ""))


def _names_match(target: str, name: str, mode: str) -> bool:
    if mode == "qualified":
        return normalized(target) == normalized(name)
    if mode == "leaf":
        return normalized(leaf_name(target)) == normalized(name)
    return template_base(leaf_name(target)) == name


def _subobject_claims(
    model: _Plan, by_class: dict[str, Any], index: dict[str, dict[int, list[dict[str, Any]]]]
) -> tuple[set[tuple[str, int, str, Any]], list[str]]:
    """Match every class-typed address pass to a sub-object of the plan.

    A call that passes ``this+N`` as ``T *`` or ``T &`` (a constructor or
    method on that address) proves a ``T`` object at ``+N``.  Such a site
    is claimed by the plan's ``T`` sub-object at ``+N`` and is then not a
    field access; an empty base at the end of an object (``compile_assert``
    after a vector) is claimed by that object, not by the next field.  A
    site that no sub-object explains is a problem unless it lies inside a
    by-value live type without a DWARF record.  Returns the claimed
    (class, offset, site, register) keys and the problems.
    """

    claims: set[tuple[str, int, str, Any]] = set()
    problems: list[str] = []
    for cls in sorted(by_class):
        row = model.types.get(cls)
        if row is None or row.get("kind") not in ("class", "struct") or not isinstance(row.get("size"), int):
            continue
        size = row["size"]
        entries, unknown = model.subobjects(cls, size)
        at: dict[int, list[tuple[str, Any]]] = defaultdict(list)
        for offset, name, mode in entries:
            at[offset].append((name, mode))
        for offset, sites in sorted(index.get(cls, {}).items()):
            if offset >= size:
                continue  # beyond the size: outside_accesses
            for site in sites:
                if site.get("access") != "address-passed" or site.get("indexed") or site.get("no_parameter"):
                    continue
                if not site.get("parameter_type"):
                    if not _cites(model.notes_at(cls, offset), site["site"]):
                        problems.append(
                            f"type {cls}: {site['site']} passes this+{_hex(offset)} in {site.get('register')} to "
                            f"{site.get('callee')}, whose parameter type is not derivable "
                            f"({site.get('parameter_unknown') or 'not recorded'}); explain it in the notes of the member "
                            f"at +{_hex(offset)}, citing {site['site']}"
                        )
                    continue
                target = parameter_class(site.get("parameter_type"))
                if target is None:
                    continue
                if model.names(target, at.get(offset, ())):
                    claims.add((cls, offset, site["site"], site.get("register")))
                    continue
                if any(low <= offset <= high for low, high in unknown):
                    continue  # inside (or at the end of) a live type whose sub-objects DWARF does not give
                problems.append(
                    f"type {cls}: {site['site']} passes this+{_hex(offset)} as {site.get('parameter_type')} "
                    f"({site.get('callee')}), but the plan has no {target} sub-object at +{_hex(offset)}"
                )
    return claims, problems


def _claimed(claims: set[tuple[str, int, str, Any]], cls: str, offset: int, site: dict[str, Any]) -> bool:
    return (cls, offset, site["site"], site.get("register")) in claims


_CITATION = re.compile(r"0x([0-9a-fA-F]+)(?:\s*[-\u2013]\s*0x([0-9a-fA-F]+))?")


def _cites(texts: list[str], site: str) -> bool:
    """Whether a text cites the site address, alone or inside an address range."""

    wanted = int(site, 16)
    for text in texts:
        for match in _CITATION.finditer(text):
            low = int(match.group(1), 16)
            high = int(match.group(2), 16) if match.group(2) else low
            if low <= wanted <= high:
                return True
    return False


def _spelling_problem(model: _Plan, text: Any, label: str, *, pointer_only_forward: bool = True) -> str | None:
    """A type spelling names a builtin, a plan type or a /project live path; forwards only by pointer."""

    parsed = parse_type(text)
    if parsed is None:
        return f"{label}: type {text!r} is not a type spelling"
    base = parsed["base"]
    if base in model.types:
        if pointer_only_forward and model.kind(base) == "forward" and not parsed["pointers"]:
            return f"{label}: {base} is a forward declaration; it can only be pointed to"
        return None
    if base in SIZES or base.startswith("/project/") or (base == "void" and parsed["pointers"]):
        return None
    return (
        f"{label}: type base {base} is not a Ghidra builtin, a plan type or forward declaration, "
        "or a /project live path"
    )


def _forward_problems(row: dict[str, Any], where: str, by_class: dict[str, Any], references: dict[str, list[str]]) -> list[str]:
    problems = []
    if row.get("name_provenance") not in NAME_PROOFS:
        problems.append(f"{where}: a forward declaration's name is proven by {' / '.join(NAME_PROOFS)} name_evidence")
    layout_keys = [
        key for key in ("size", "alignment", "bases", "vptr", "fields", "padding", "outside_accesses", "instantiation", "size_evidence")
        if row.get(key) not in (None, [], {})
    ]
    if layout_keys:
        problems.append(f"{where}: a forward declaration has no layout ({', '.join(layout_keys)})")
    if not row.get("reason"):
        problems.append(f"{where}: a forward declaration records why no layout is planned (reason)")
    if row["name"] in by_class:
        problems.append(f"{where}: the layout evidence covers this class; plan its layout instead of forward-declaring it")
    if not references.get(row["name"]):
        problems.append(f"{where}: no plan member points to this forward declaration")
    return problems


def _instantiation_problems(model: _Plan, row: dict[str, Any], where: str) -> list[str]:
    spec = row["instantiation"]
    if not isinstance(spec, dict):
        return [f"{where}: instantiation is an object"]
    source = spec.get("source")
    if not isinstance(source, str) or not source.startswith("/project/") or source.count("/") < 2:
        return [f"{where}: instantiation.source is the /project path of an existing live instantiation"]
    problems: list[str] = []
    category, source_leaf = source.rsplit("/", 1)
    leaf = _leaf(row["name"])
    template = template_base(leaf)
    if category.startswith(("/project/unresolved", "/project/anonymous")):
        problems.append(f"{where}: {source} has no resolved template identity; copy a named instantiation")
    if "<" not in leaf or template_base(source_leaf) != template:
        problems.append(f"{where}: {source} is not an instantiation of the template {template}")
    if category != row.get("category"):
        problems.append(f"{where}: the source lies in {category}, not in the template's namespace {row.get('category')}")
    arguments = spec.get("arguments")
    pairs: list[tuple[str, str]] = []
    if not isinstance(arguments, list) or not arguments or not all(
        isinstance(item, dict) and isinstance(item.get("from"), str) and isinstance(item.get("to"), str)
        and item["from"] and item["to"] and item["from"] != item["to"]
        for item in arguments
    ):
        problems.append(f"{where}: instantiation.arguments lists the substituted template arguments as {{from, to}}")
    else:
        pairs = [(item["from"], item["to"]) for item in arguments]
        renamed = substitute(source_leaf, pairs)
        if renamed != leaf:
            problems.append(f"{where}: substituting the arguments into {source_leaf} gives {renamed}, not {leaf}")
    if row.get("name_provenance") not in (TEMPLATE_NAME, "mangled-symbol"):
        problems.append(f"{where}: an instantiation's name_provenance is {TEMPLATE_NAME} (or mangled-symbol)")
    if row.get("name_provenance") == TEMPLATE_NAME:
        for _source, target in pairs:
            if normalized(target) not in model.normalized_types and target not in CXX_BUILTINS:
                problem = _live_argument_problem(model, target)
                if problem:
                    problems.append(f"{where}: template argument {target} {problem}")
    size, rows = spec.get("source_size"), spec.get("source_layout")
    if size != row.get("size"):
        problems.append(f"{where}: instantiation.source_size {size} differs from the size {row.get('size')}")
    if not isinstance(rows, list) or not rows or not all(
        isinstance(item, list) and len(item) == 4 and isinstance(item[0], int) and isinstance(item[1], int)
        and isinstance(item[2], str) and isinstance(item[3], str)
        for item in rows
    ):
        return problems + [f"{where}: instantiation.source_layout lists the source's [offset, size, type, name] rows"]
    components = {offset: (extent, role, entry) for offset, extent, role, entry in model.components(row) if role != "padding"}
    members: set[tuple[int, str]] = set()
    bases: set[int] = set()
    for offset, extent, source_type, source_name in rows:
        parsed = parse_type(source_type)
        if parsed is None or re.search(r"(?<!:):(?!:)", source_type):
            problems.append(f"{where}: source member {source_name} ({source_type}) cannot be copied (bitfields are not supported)")
            continue
        expected = (
            substitute(parsed["base"], pairs, bare=True)
            + " *" * parsed["pointers"]
            + "".join(f"[{count}]" for count in parsed["arrays"])
        )
        is_base = not parsed["pointers"] and not parsed["arrays"] and source_name == "super_" + _identifier(parsed["base"])
        component = components.get(offset)
        if is_base:
            bases.add(offset)
        else:
            members.add((offset, source_name))
        if component is None:
            problems.append(f"{where}: the source's {source_name} at +{_hex(offset)} is not copied")
            continue
        found_extent, role, entry = component
        wanted_role = "base" if is_base else "field"
        if role != wanted_role or found_extent != extent:
            problems.append(f"{where}: +{_hex(offset)} copies the source's {source_name} as a {extent}-byte {wanted_role}")
            continue
        if not is_base and (entry.get("name") != source_name or entry.get("provenance") != TEMPLATE_COPY):
            problems.append(f"{where}: +{_hex(offset)} keeps the source member name {source_name} ({TEMPLATE_COPY})")
        copied = model.bare(entry.get("type"))
        if copied is None or normalized(copied) != normalized(expected):
            problems.append(
                f"{where}: +{_hex(offset)} is {entry.get('type')} ({copied}), but the source's {source_type} with the "
                f"arguments substituted is {expected}"
            )
    copied_offsets = {item[0] for item in rows}
    for offset, (_extent, role, entry) in sorted(components.items(), key=lambda item: item[0] if isinstance(item[0], int) else -1):
        if role in ("vptr", "bits"):
            problems.append(f"{where}: an instantiation copies plain members only (no {role} at {offset})")
        elif offset not in copied_offsets:
            problems.append(f"{where}: {role} {entry.get('name') or entry.get('type')} at {offset} is not in the source layout")
    if isinstance(size, int) and model.evidence is not None and not model.evidence.layout_matches(template, size, members, bases):
        problems.append(
            f"{where}: no DWARF record of {template} ({size} bytes) has the source layout's members "
            f"{sorted(members)} and bases at {sorted(bases)}"
        )
    for field in row.get("fields") or []:
        if field.get("provenance") == TEMPLATE_COPY and (field.get("offset"), field.get("name")) not in members:
            problems.append(f"{where} field {field.get('name')}: a {TEMPLATE_COPY} name is a source member at its offset")
    return problems


_NAME_COMPONENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:<.+>)?$")


def _argument_path(name: str) -> str:
    """The Ghidra path of a live type by its qualified name (its namespace category and leaf)."""

    return f"{expected_category(name)}/{_leaf(name)}"


def _live_argument_problem(model: _Plan, target: str) -> str | None:
    """Why a template argument that is neither a plan type nor a builtin cannot name a live type, else None.

    File-only: the name is a qualified type name (no pointer, reference or
    path), the ELF names it, and no plan type shares its leaf.  The live
    check proves it resolves to exactly ``_argument_path``.
    """

    if target.startswith("/") or not all(_NAME_COMPONENT.match(part) for part in split_qualified(target)):
        return "is neither a plan type, a builtin nor a qualified live type name"
    clash = next((name for name in model.types if _leaf(name).casefold() == _leaf(target).casefold()), None)
    if clash is not None:
        return f"shares its name with the plan type {clash}, so a bare-name reference would be ambiguous"
    if model.evidence is not None and not model.evidence.names_type(target):
        return (
            "is neither a plan type, a builtin, nor a type an ELF symbol or DWARF record names; cite a mangled "
            "symbol that names this instantiation instead"
        )
    return None


def _live_arguments(model: _Plan) -> list[dict[str, Any]]:
    """Live template arguments of template-instantiation names: name, expected path and the plan types using it."""

    found: dict[str, dict[str, Any]] = {}
    for name, row in model.types.items():
        spec = row.get("instantiation")
        if row.get("name_provenance") != TEMPLATE_NAME or not isinstance(spec, dict):
            continue
        for item in spec.get("arguments") or []:
            target = item.get("to") if isinstance(item, dict) else None
            if not isinstance(target, str) or normalized(target) in model.normalized_types or target in CXX_BUILTINS:
                continue
            entry = found.setdefault(_argument_path(target), {"name": target, "path": _argument_path(target), "types": set()})
            entry["types"].add(_path_of(row))
    return [{**found[path], "types": sorted(found[path]["types"])} for path in sorted(found)]


def _vtable_problems(row: dict[str, Any], by_class: dict[str, Any], where: str) -> list[str]:
    problems = []
    owner = row["name"][: -len("_vtbl")]
    if row.get("opaque"):
        if row.get("size") not in (0, None) or row.get("fields"):
            problems.append(f"{where}: an opaque vtable has size 0 and no fields")
        if not row.get("opaque_reason"):
            problems.append(f"{where}: an opaque vtable records why its slots are not typed (opaque_reason)")
        return problems
    table = (by_class.get(owner) or {}).get("vtable")
    if not table:
        return [f"{where}: {owner} has no vtable in the layout evidence"]
    if row.get("size") != table["size"]:
        problems.append(f"{where}: size must be the vtable object's {table['size']} bytes")
    fields = {field.get("offset"): field for field in row.get("fields") or []}
    for offset in range(0, table["size"], 4):
        field = fields.get(offset)
        if field is None:
            problems.append(f"{where}: no field at +{_hex(offset)}")
            continue
        if not field.get("evidence"):
            problems.append(f"{where}: field +{_hex(offset)} has no evidence")
        if offset >= 8 and not str(field.get("type", "")).strip().endswith("*"):
            problems.append(f"{where}: slot +{_hex(offset)} must be a function pointer type")
    return problems


def _type_problems(
    model: _Plan,
    row: dict[str, Any],
    where: str,
    by_class: dict[str, Any],
    index: dict[str, dict[int, list[dict[str, Any]]]],
    windows: set[tuple[str, int]],
    claims: set[tuple[str, int, str, Any]],
    copies: dict[tuple[str, int, str, str], str] | None = None,
) -> list[str]:
    problems: list[str] = []
    copies = copies or {}
    name = row["name"]
    size = row.get("size")
    if not isinstance(size, int) or size <= 0:
        return [f"{where}: size must be a positive integer"]
    alignment = row.get("alignment")
    if not isinstance(alignment, int) or alignment <= 0 or size % alignment:
        problems.append(f"{where}: alignment must divide the size")
    layout_row = by_class.get(name)
    if layout_row is not None:
        sizes = layout_row["size_evidence"]
        if len(sizes) > 1:
            problems.append(f"{where}: allocation sizes disagree {sizes}")
        elif sizes and sizes[0] != size:
            problems.append(f"{where}: size {_hex(size)} differs from the allocation evidence {_hex(sizes[0])}")
        elif not sizes and not row.get("size_evidence"):
            problems.append(f"{where}: no allocation proves the size; cite size_evidence")
    elif not row.get("size_evidence") and row.get("instantiation") is None:
        problems.append(f"{where}: cite size_evidence")
    if not windows:
        problems.append(f"{where}: no layout evidence reaches this type (not a layout class and not embedded in one)")

    # Coverage and overlap.
    components = model.components(row)
    covered: list[tuple[int, int, str]] = []
    natural = 1
    for offset, extent, role, entry in components:
        label = f"{role} at {_hex(offset) if isinstance(offset, int) else offset}"
        if not isinstance(offset, int) or not isinstance(extent, int) or extent <= 0:
            problems.append(f"{where}: {label} needs an integer offset and a known positive size")
            continue
        if offset < 0 or offset + extent > size:
            problems.append(f"{where}: {label} (+{_hex(extent)}) lies outside the {_hex(size)}-byte type")
        covered.append((offset, offset + extent, label))
        if role == "vptr":
            natural = max(natural, 4)
        elif role in ("base", "field"):
            align = model.align_of(parse_type(entry.get("type")))
            if align:
                natural = max(natural, align)
                if offset % align:
                    problems.append(f"{where}: {label} is not {align}-byte aligned")
        elif role == "bits":
            natural = max(natural, min(extent, 16))
    if isinstance(alignment, int) and alignment != natural and natural > 1:
        problems.append(f"{where}: alignment {alignment} differs from the members' {natural}")
    covered.sort()
    cursor = 0
    for low, high, label in covered:
        if low < cursor:
            problems.append(f"{where}: {label} overlaps the previous component")
        elif low > cursor:
            problems.append(f"{where}: bytes {_hex(cursor)}-{_hex(low - 1)} are not covered by a base, vptr, field or padding")
        cursor = max(cursor, high)
    if cursor < size:
        problems.append(f"{where}: bytes {_hex(cursor)}-{_hex(size - 1)} are not covered by a base, vptr, field or padding")

    names: set[str] = set()
    for offset, extent, role, entry in components:
        if role == "base":
            problems.extend(_base_problems(model, row, entry, by_class, where))
            base_name = _base_component_name(entry.get("type", ""))
            if entry.get("name") not in (None, base_name):
                problems.append(f"{where}: the base component is named {base_name}, the bare base type name")
            if base_name in names:
                problems.append(f"{where}: two components are named {base_name}")
            names.add(base_name)
        elif role == "vptr":
            problems.extend(_vptr_problems(model, row, entry, layout_row, index, where))
            names.add(VPTR_NAME)
        elif role == "padding":
            for cls, delta in sorted(windows):
                for site_offset, site in _sites_in(index.get(cls, {}), delta + offset - 15, delta + offset + extent):
                    if _claimed(claims, cls, site_offset, site):
                        continue  # a sub-object's own call (an empty base at its end)
                    if copies.get(_copy_key(cls, site_offset, site)) in (BULK, ZERO_FILL):
                        continue  # a bulk copy or zero-fill writes padding with the members
                    if site_offset + _site_extent(site) > delta + offset:
                        problems.append(
                            f"{where}: padding {_hex(offset)}+{_hex(extent)} is accessed at {cls}+{_hex(site_offset)} ({site['site']})"
                        )
                        break
    for field in row.get("fields") or []:
        field_name = field.get("name")
        label = f"{where} field {field_name}"
        if not isinstance(field_name, str) or field_name in names:
            problems.append(f"{label}: names must be unique and not repeat a base or __vt")
        names.add(str(field_name))
        provenance = field.get("provenance")
        if provenance not in FIELD_PROVENANCES:
            problems.append(f"{label}: provenance must be one of {list(FIELD_PROVENANCES)}")
        elif provenance == INVENTED and not FIELD_NAME.match(str(field_name)):
            problems.append(f"{label}: invented member names are m_ followed by lower snake_case")
        elif provenance == TEMPLATE_COPY:
            if row.get("instantiation") is None:
                problems.append(f"{label}: {TEMPLATE_COPY} names belong to instantiation members")
        elif provenance != INVENTED and not field.get("name_evidence"):
            problems.append(f"{label}: a non-invented name cites name_evidence")
        problems.extend(_field_problems(model, field, label, index, windows, claims, copies))

    # Every access in this type's windows lands on a component; beyond the size it is listed.
    outside = {str(entry.get("site")) for entry in row.get("outside_accesses") or [] if entry.get("reason")}
    if layout_row is not None:
        for site_offset, sites in index.get(name, {}).items():
            if site_offset < size:
                continue
            for site in sites:
                if site["site"] not in outside:
                    problems.append(f"{where}: access at +{_hex(site_offset)} ({site['site']}) lies beyond the size; list it in outside_accesses with a reason")
    return problems


def _base_problems(model: _Plan, row: dict[str, Any], entry: dict[str, Any], by_class: dict[str, Any], where: str) -> list[str]:
    problems = []
    base = entry.get("type")
    if base in model.types:
        if model.kind(base) in ("forward", "vtable"):
            problems.append(f"{where}: base {base} is a {model.kind(base)} type")
    elif isinstance(base, str) and base.startswith("/project/") and row.get("instantiation") is not None:
        if not isinstance(entry.get("size"), int):
            problems.append(f"{where}: the live base {base} needs its size")
    else:
        problems.append(f"{where}: base {base} is not a plan type")
    layout_row = by_class.get(row["name"])
    if layout_row is not None:
        listed = {(item["class"], item["offset"]) for item in layout_row["bases"]}
        if (base, entry.get("offset")) not in listed:
            problems.append(f"{where}: the RTTI base list does not name {base} at {entry.get('offset')}")
    return problems


def _vptr_problems(
    model: _Plan, row: dict[str, Any], entry: dict[str, Any], layout_row: dict[str, Any] | None,
    index: dict[str, dict[int, list[dict[str, Any]]]], where: str,
) -> list[str]:
    problems = []
    if entry.get("name") not in (None, VPTR_NAME):
        problems.append(f"{where}: the vptr member is named {VPTR_NAME}")
    parsed = parse_type(entry.get("type"))
    target = model.types.get(parsed["base"]) if parsed else None
    if not parsed or parsed["pointers"] != 1 or parsed["arrays"] or not target or target.get("kind") != "vtable":
        problems.append(f"{where}: the vptr type is a pointer to a plan vtable type")
    if layout_row is None or not layout_row["vtable"]:
        problems.append(f"{where}: a vptr needs the class's vtable in the layout evidence")
        return problems
    own = f"{layout_row['vtable']['name']}+0x0"
    stores = {site["site"] for site in index.get(row["name"], {}).get(entry.get("offset"), []) if site.get("vtable_store") == own}
    if not stores:
        problems.append(f"{where}: no constructor or destructor stores {own} at +{_hex(entry.get('offset') or 0)}")
    for site in entry.get("evidence") or []:
        if site not in stores:
            problems.append(f"{where}: vptr evidence {site} is not a store of {own}")
    if not entry.get("evidence"):
        problems.append(f"{where}: the vptr cites its vtable stores")
    return problems


def _passes_as(site: dict[str, Any], base: str, pointers: int) -> bool:
    """Whether a call passes the member (its address, or its value for a pointer) as exactly the type ``base``."""

    access = {0: "address-passed", 1: "value-passed"}.get(pointers)
    target = parameter_class(site.get("parameter_type")) if site.get("access") == access else None
    if target is None:
        return False
    if base.startswith("/"):
        return _names_match(target, base.rsplit("/", 1)[1], "leaf")
    return _names_match(target, base, "qualified")


def _field_problems(
    model: _Plan, field: dict[str, Any], label: str, index: dict[str, dict[int, list[dict[str, Any]]]],
    windows: set[tuple[str, int]], claims: set[tuple[str, int, str, Any]],
    copies: dict[tuple[str, int, str, str], str] | None = None,
) -> list[str]:
    problems: list[str] = []
    copies = copies or {}
    parsed = parse_type(field.get("type"))
    offset, size = field.get("offset"), field.get("size")
    if parsed is None or parsed["base"] == "void" and not parsed["pointers"]:
        return [f"{label}: type {field.get('type')!r} is not a type spelling"]
    spelling = _spelling_problem(model, field.get("type"), label)
    if spelling:
        problems.append(spelling)
    if not isinstance(offset, int) or not isinstance(size, int):
        return problems + [f"{label}: offset and size are integers"]
    computed = model.size_of(parsed, None)
    bitfield = "bit_size" in field or "bit_offset" in field
    if computed is not None and computed != size:
        problems.append(f"{label}: size {size} differs from {field.get('type')} ({computed})")
    if bitfield:
        bit_offset, bit_size = field.get("bit_offset"), field.get("bit_size")
        if parsed["pointers"] or parsed["arrays"] or parsed["base"] not in SIGNED | UNSIGNED:
            problems.append(f"{label}: a bitfield has an integer builtin type")
        if not isinstance(bit_offset, int) or not isinstance(bit_size, int) or bit_size <= 0 or bit_offset < 0 or bit_offset + bit_size > 8 * size:
            problems.append(f"{label}: bit_offset/bit_size must fit the {size}-byte unit")
    base = parsed["base"]
    if base.startswith("/") and not field.get("size"):
        problems.append(f"{label}: a live type needs its size")
    if void_pointer_argument(base) and field.get("provenance") != TEMPLATE_COPY and not field.get("unresolved"):
        # The elements lie beyond the matched evidence, so the placeholder is justified like a dereferenced
        # void * field (unresolved) unless a call passes the member as exactly this type.
        if not any(
            _passes_as(site, base, parsed["pointers"])
            for cls, delta in sorted(windows) for site in index.get(cls, {}).get(delta + offset, [])
        ):
            problems.append(
                f"{label}: void * as a template argument of {base} is a placeholder; type the argument or record "
                "why in unresolved"
            )
    composite = model.composite(parsed) and not parsed["arrays"]
    evidence = field.get("evidence") or []
    if not evidence and field.get("provenance") != TEMPLATE_COPY:
        problems.append(f"{label}: cite at least one evidence site")
    # Candidate sites: the field's extent in every window.  A site a sub-object
    # claims (a call on an empty base at the end of the previous member) is
    # that sub-object's, not this field's.  Each carries its copy or zero-fill kind, if any.
    candidates: list[tuple[str, int, dict[str, Any], str | None]] = []
    claimed: dict[str, dict[str, Any]] = {}
    for cls, delta in sorted(windows):
        for site_offset, site in _sites_in(index.get(cls, {}), delta + offset, delta + offset + size):
            if not composite and _claimed(claims, cls, site_offset, site):
                claimed[site["site"]] = site
                continue
            candidates.append((cls, site_offset - delta, site, copies.get(_copy_key(cls, site_offset, site))))
    by_site = {site["site"] for _cls, _relative, site, _copy in candidates}
    for cited in evidence:
        if cited in by_site:
            continue
        if cited in claimed:
            problems.append(
                f"{label}: evidence {cited} passes the address of a {parameter_class(claimed[cited].get('parameter_type'))} "
                "sub-object that lies there, not this field"
            )
        else:
            problems.append(f"{label}: evidence {cited} is not an access within +{_hex(offset)}..+{_hex(offset + size - 1)}")
    if composite or parsed["arrays"]:
        return problems  # inner accesses belong to the member type; extent checks above
    exact = [(cls, relative, site) for cls, relative, site, _copy in candidates if relative == offset]
    cited_exact = [site for cls, relative, site in exact if site["site"] in evidence]
    if evidence and not cited_exact and not bitfield:
        problems.append(f"{label}: no cited evidence site accesses the field's first byte")
    width_size = size
    for cls, relative, site, copy_kind in candidates:
        if copy_kind in (BULK, ZERO_FILL):
            continue  # a bulk copy's or zero-fill's chunks are the bulk access's, not this member's
        if relative != offset:
            if not bitfield and site.get("access") != "address-passed":
                problems.append(f"{label}: {site['site']} accesses +{_hex(relative)} inside the scalar field ({cls})")
            continue
        if copy_kind:
            # Width-only evidence: a member-wise copy moves the unit's bits, whatever its type.
            if not bitfield and site.get("width") not in (None, width_size):
                problems.append(
                    f"{label}: {site['site']} ({site.get('access')} w{site.get('width')}, a member-wise copy) "
                    f"contradicts the {width_size}-byte {field.get('type')}"
                )
            continue
        if not _compatible(site, parsed, None if bitfield else width_size):
            problems.append(f"{label}: {site['site']} ({site.get('access')} w{site.get('width')} {site.get('kind')}) contradicts {field.get('type')}")
    # Type evidence (kind, sign, pointer): the exact sites that are not copies.
    exact = [(cls, relative, site) for cls, relative, site, copy_kind in candidates if relative == offset and not copy_kind]
    loads = {site.get("signed") for _cls, relative, site in exact if site.get("access") == "load" and site.get("signed") is not None}
    if size in (1, 2) and not bitfield and base in SIGNED | UNSIGNED and not parsed["pointers"]:
        if loads == {True} and base in UNSIGNED:
            problems.append(f"{label}: every load sign-extends (lb/lh); {base} is unsigned")
        if loads == {False} and base in SIGNED:
            problems.append(f"{label}: every load zero-extends (lbu/lhu); {base} is signed")
        if loads == {True, False} and not field.get("notes"):
            problems.append(f"{label}: loads both sign- and zero-extend; explain the type in notes")
    strong = [site for _cls, relative, site in exact if _strength(site)]
    if base in UNDEFINED_SIZES and strong:
        problems.append(f"{label}: {base} is a placeholder but {strong[0]['site']} proves more")
    if base == "void" and parsed["pointers"] == 1:
        # The field's value passed as a typed parameter (an address pass types the field's storage instead).
        typed = sorted(
            {
                site["parameter_type"] for site in strong
                if site.get("access") == "value-passed" and site.get("parameter_type") and "void" not in site["parameter_type"]
            }
            | {stored for _cls, _relative, site in exact if (stored := _stored_parameter_type(site))}
        )
        if typed:
            problems.append(f"{label}: void * is a placeholder; the evidence passes or stores it as {typed[0]}")
        if any(site.get("access", "").startswith("deref") for site in strong) and not field.get("unresolved"):
            problems.append(f"{label}: void * is dereferenced; type the pointee or record why in unresolved")
    if not parsed["pointers"] and any(site.get("pointer") for _cls, relative, site in exact):
        problems.append(f"{label}: the evidence dereferences this field, so it is a pointer")
    return problems


# -- review table -------------------------------------------------------------


def _cell(text: Any) -> str:
    """Free text for a Markdown table cell: pipes escaped, line breaks kept, ``<`` not read as HTML."""

    value = str(text).replace("\\", "\\\\").replace("|", "\\|").replace("<", "\\<")
    return "<br>".join(part.strip() for part in value.splitlines()) if value else ""


def _code(text: Any) -> str:
    """Inline code for a Markdown table cell."""

    value = str(text).replace("|", "\\|")
    if not value:
        return ""
    return f"``{value}``" if "`" in value else f"`{value}`"


def _texts(value: Any) -> list[str]:
    if value is None or value == "" or value == []:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def _sample_cell(
    evidence: list[str], sites: dict[str, dict[str, Any]], limit: int = 3, copied: dict[str, str] | None = None
) -> str:
    samples = []
    for site in evidence[:limit]:
        found = sites.get(site)
        if found:
            kind = (copied or {}).get(site)
            samples.append(
                f"{_code(site)} {_code(found.get('insn', ''))} in {_code(found.get('function_name', ''))}"
                + (f" ({kind})" if kind == ZERO_FILL else f" ({kind} copy)" if kind else "")
            )
        else:
            samples.append(f"{_code(site)} (not in the evidence)")
    if len(evidence) > limit:
        samples.append(f"+{len(evidence) - limit} more")
    return "<br>".join(samples)


def _name_evidence_cell(row: dict[str, Any], evidence: TypeEvidence | None) -> str:
    items = []
    for text in _texts(row.get("name_evidence")):
        readable = evidence.readable(text) if evidence is not None and row.get("name_provenance") == "mangled-symbol" else None
        items.append(_code(text) + (f" = {_code(readable)}" if readable and readable != text else ""))
    return "<br>".join(items)


def _path_of(row: dict[str, Any]) -> str:
    return f"{row.get('category')}/{_leaf(str(row.get('name')))}"


def render_type_plan(
    plan: dict[str, Any], layout: dict[str, Any], problems: list[str], evidence: TypeEvidence | None = None
) -> str:
    """The plan as a Markdown review: overview, forward declarations, invented names, one table per type.

    With ``evidence`` (the reference ELF), mangled name evidence is shown
    demangled and calls an empty base at a member's end receives are noted
    on that member.
    """

    sites: dict[str, dict[str, Any]] = {}
    for cls in layout.get("classes") or []:
        for row in cls["offsets"]:
            for site in row["sites"]:
                sites.setdefault(site["site"], site)
    model = _Plan(plan, evidence)
    spec = plan.get("layout") or {}
    types = [row for row in plan.get("types") or [] if isinstance(row, dict)]
    forwards = [row for row in types if row.get("kind") == "forward"]
    defined = [row for row in types if row.get("kind") != "forward"]
    instantiations = [row for row in defined if row.get("instantiation") is not None]
    end_claims = _end_claims(model, layout) if evidence is not None else {}
    copy_notes, copy_kinds = _copy_notes(model, layout)
    live_arguments = {(path, item["name"]) for item in _live_arguments(model) for path in item["types"]}
    lines = [
        f"# Code-derived type plan `{plan.get('work_item_id')}`",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Layout evidence | {_code(spec.get('class'))}{' with its derived classes' if spec.get('with_derived') else ''}"
        f"{' (plain struct)' if spec.get('struct') else ''}, "
        f"sha256 {_code(spec.get('sha256'))} |",
        f"| Validation | {'**ok**' if not problems else f'**{len(problems)} problem(s)**, listed under Validation'} |",
        f"| Types | {len(defined)} defined ({len(instantiations)} template instantiations), {len(forwards)} forward declarations |",
        "",
        "Name provenance:",
        "",
    ]
    lines.extend(f"- `{key}`: {text}" for key, text in PROVENANCE_KEY)
    if plan.get("naming_survey"):
        lines += ["", "## Naming survey", ""]
        lines.extend(f"- {_cell(text)}" for text in plan["naming_survey"])

    lines += ["", "## Forward declarations", ""]
    if forwards:
        lines += [
            "| Type | Ghidra path | Name proof | Name evidence | Pointed to by | Why no layout |",
            "|---|---|---|---|---|---|",
        ]
        references = model.references()
        for row in forwards:
            pointed = "<br>".join(_code(text) for text in references.get(str(row.get("name")), []))
            lines.append(
                f"| {_code(row.get('name'))} | {_code(_path_of(row))} | {_code(row.get('name_provenance'))} | "
                f"{_name_evidence_cell(row, evidence)} | {pointed} | {_cell(row.get('reason', ''))} |"
            )
    else:
        lines.append("None.")

    lines += ["", "## Invented provisional names", ""]
    invented = []
    for row in types:
        if row.get("name_provenance") == INVENTED:
            invented.append((_code(row.get("name")), f"{row.get('kind')} name", "", _cell("; ".join(_texts(row.get("notes"))))))
        for field in row.get("fields") or []:
            if field.get("provenance") != INVENTED:
                continue
            where = f"+{_hex(field['offset'])}" if isinstance(field.get("offset"), int) else str(field.get("offset"))
            if "bit_offset" in field:
                where += f" bit {field.get('bit_offset')}:{field.get('bit_size')}"
            notes = "; ".join(_texts(field.get("notes")) + _texts(field.get("unresolved")))
            invented.append((_code(field.get("name")), f"member of {_code(row.get('name'))} at {where}", _code(field.get("type")), _cell(notes)))
    if invented:
        lines += ["| Name | Where | Type | Notes |", "|---|---|---|---|"]
        lines.extend(f"| {name} | {where} | {type_text} | {notes} |" for name, where, type_text, notes in invented)
    else:
        lines.append("None.")

    lines += ["", "## Types"]
    for row in defined:
        lines += ["", f"### {_code(row.get('name'))} ({row.get('kind')})", ""]
        size = row.get("size")
        lines.append(
            f"- Ghidra path {_code(_path_of(row))}, size {_hex(size) if isinstance(size, int) else size}, "
            f"alignment {row.get('alignment')}, name {_code(row.get('name_provenance'))}"
        )
        if row.get("name_evidence"):
            lines.append(f"- Name evidence: {_name_evidence_cell(row, evidence).replace('<br>', '; ')}")
        for text in row.get("size_evidence") or []:
            lines.append(f"- Size evidence: {_cell(text)}")
        if row.get("kind") == "vtable" and row.get("opaque"):
            lines.append(f"- Opaque: {_cell(row.get('opaque_reason'))}")
        for text in _texts(row.get("notes")):
            lines.append(f"- Note: {_cell(text)}")
        copied = row.get("instantiation")
        if isinstance(copied, dict):
            arguments = ", ".join(
                f"{_code(item.get('from'))} → {_code(item.get('to'))}"
                + (
                    f" (live {_code(_argument_path(str(item.get('to'))))})"
                    if (_path_of(row), item.get("to")) in live_arguments else ""
                )
                for item in copied.get("arguments") or [] if isinstance(item, dict)
            )
            lines.append(f"- Copied from {_code(copied.get('source'))} ({copied.get('source_size')} bytes), arguments {arguments}")
            if isinstance(copied.get("source_layout"), list):
                lines += ["", "| Source offset | Size | Source type | Source name |", "|---:|---:|---|---|"]
                for item in copied["source_layout"]:
                    if isinstance(item, list) and len(item) == 4:
                        offset = _hex(item[0]) if isinstance(item[0], int) else item[0]
                        lines.append(f"| {offset} | {item[1]} | {_code(item[2])} | {_code(item[3])} |")
        if row.get("kind") == "vtable" and row.get("opaque"):
            continue
        lines += [
            "",
            "| Offset | Size | Type | Name | Provenance | Evidence | Sample sites | Notes |",
            "|---:|---:|---|---|---|---:|---|---|",
        ]
        table = []
        for offset, extent, role, entry in model.components(row):
            if role == "base":
                notes = _texts(entry.get("notes")) + end_claims.get((str(row.get("name")), offset), [])
                name = _base_component_name(entry.get("type", ""))
                table.append((offset, extent, entry.get("type"), name, "base", entry.get("evidence") or [], notes))
            elif role == "vptr":
                table.append((offset, 4, entry.get("type"), VPTR_NAME, "vptr", entry.get("evidence") or [], _texts(entry.get("notes"))))
            elif role == "padding":
                table.append((offset, extent, "(padding)", "", "no access", [], _texts(entry.get("reason")) + _texts(entry.get("notes"))))
            elif role == "bits":
                for field in sorted(entry, key=lambda item: item.get("bit_offset", 0)):
                    bits = f"{field.get('type')}:{field.get('bit_size')} @ bit {field.get('bit_offset')}"
                    notes = _texts(field.get("notes")) + [f"unresolved: {text}" for text in _texts(field.get("unresolved"))]
                    notes += copy_notes.get((str(row.get("name")), offset), [])
                    table.append((offset, extent, bits, field.get("name"), field.get("provenance"), field.get("evidence") or [], notes))
            else:
                notes = (
                    _texts(entry.get("notes"))
                    + [f"unresolved: {text}" for text in _texts(entry.get("unresolved"))]
                    + end_claims.get((str(row.get("name")), offset), [])
                    + copy_notes.get((str(row.get("name")), offset), [])
                )
                table.append((offset, extent, entry.get("type"), entry.get("name"), entry.get("provenance"), entry.get("evidence") or [], notes))
        for offset, extent, type_text, name, provenance, cited, notes in sorted(
            table, key=lambda item: (item[0] if isinstance(item[0], int) else -1, str(item[3]))
        ):
            lines.append(
                f"| {_hex(offset) if isinstance(offset, int) else offset} | {_hex(extent) if isinstance(extent, int) else extent} | "
                f"{_code(type_text)} | {_code(name)} | {provenance or ''} | {len(cited)} | {_sample_cell(list(cited), sites, copied=copy_kinds)} | "
                f"{'<br>'.join(_cell(text) for text in notes)} |"
            )
        outside = row.get("outside_accesses") or []
        if outside:
            lines += ["", "Accesses beyond the size:", ""]
            lines.extend(f"- {_code(entry.get('site'))}: {_cell(entry.get('reason'))}" for entry in outside)
        unresolved = _texts(row.get("unresolved"))
        if unresolved:
            lines += ["", "Unresolved:", ""]
            lines.extend(f"- {_cell(text)}" for text in unresolved)

    held = _holder_proofs(plan, layout)
    if held:
        lines += [
            "",
            "## Holder proofs",
            "",
            "Cited sites whose object pointer is held outside the class family, with the proof `recon layout` "
            "gives for the root (typed DWARF member or global, typed pointer storage, or typed call result):",
            "",
        ]
        lines.extend(
            f"- {_code(site)} in {_code(function)}, root {_code(root)}: {_cell(proof)}" for site, function, root, proof in held
        )

    lines += ["", "## Validation", ""]
    lines.append("validation: ok" if not problems else f"validation: {len(problems)} problem(s)")
    if problems:
        lines.append("")
        lines.extend(f"- {_cell(text)}" for text in problems)
    return "\n".join(lines) + "\n"


HOLDER_ROOTS = ("held@", "return@")


def _cited_sites(value: Any) -> set[str]:
    """Every site string any ``evidence`` list of the plan cites."""

    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence" and isinstance(item, list):
                found.update(text for text in item if isinstance(text, str))
            else:
                found |= _cited_sites(item)
    elif isinstance(value, list):
        for item in value:
            found |= _cited_sites(item)
    return found


def _holder_proofs(plan: dict[str, Any], layout: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """(site, function, root, proof) of each cited site whose root is a holder (``held@`` / ``return@``)."""

    proofs = {
        (row["function"], root["register"]): root["proof"]
        for row in layout.get("functions") or [] for root in row.get("roots") or []
    }
    cited = _cited_sites(plan.get("types") or [])
    rows = set()
    for cls in layout.get("classes") or []:
        rows_of_class = [site for entry in cls.get("offsets") or [] for site in entry.get("sites") or []]
        for site in rows_of_class + list(cls.get("object_passes") or []):
            root = str(site.get("root", ""))
            if site.get("site") in cited and root.startswith(HOLDER_ROOTS):
                proof = proofs.get((site.get("function"), root), "proof missing from the layout's function roots")
                rows.add((site["site"], str(site.get("function_name", "")), root, proof))
    return sorted(rows, key=lambda row: (int(row[0], 16), row[1], row[2]))


def _end_claims(model: _Plan, layout: dict[str, Any]) -> dict[tuple[str, int], list[str]]:
    """(plan type, component offset) -> calls that an empty base at the component's end receives."""

    by_class = {row["class"]: row for row in layout.get("classes") or []}
    index = {row["class"]: {entry["offset"]: list(entry["sites"]) for entry in row["offsets"]} for row in layout.get("classes") or []}
    claims, _problems = _subobject_claims(model, by_class, index)
    if not claims:
        return {}
    sites = {
        (cls, offset, site["site"], site.get("register")): site
        for cls, offsets in index.items() for offset, rows in offsets.items() for site in rows
    }
    windows = model.windows(set(by_class))
    notes: dict[tuple[str, int], set[str]] = defaultdict(set)
    for name, row in model.types.items():
        if row.get("kind") not in ("class", "struct"):
            continue
        for offset, extent, role, entry in model.components(row):
            if role not in ("base", "field") or not isinstance(offset, int) or not isinstance(extent, int):
                continue
            if not model.composite(parse_type(entry.get("type"))):
                continue
            inner, _unknown = model.subobjects(entry.get("type"), extent)
            at_end = [(inner_name, mode) for inner_offset, inner_name, mode in inner if inner_offset == extent]
            if not at_end:
                continue
            for cls, delta in windows.get(name, ()):
                for key in claims:
                    if key[0] != cls or key[1] != delta + offset + extent:
                        continue
                    site = sites[key]
                    target = parameter_class(site.get("parameter_type"))
                    if target and model.names(target, at_end):
                        notes[(name, offset)].add(
                            f"{site['site']} ({site.get('callee')}) calls this member's empty {target} at its end "
                            f"(+{_hex(extent)}), not the next member"
                        )
    return {key: sorted(values) for key, values in notes.items()}


def _copy_notes(model: _Plan, layout: dict[str, Any]) -> tuple[dict[tuple[str, int], list[str]], dict[str, str]]:
    """(plan type, member offset) -> notes naming the copies and zero-fills inside the member, and site -> kind."""

    classes = layout.get("classes") or []
    windows = model.windows({row["class"] for row in classes})
    copies = _neutral_accesses(model, classes, windows)
    copied: dict[str, str] = {}
    by_place: dict[tuple[str, int], list[tuple[str, str, str]]] = defaultdict(list)
    for (cls, offset, site, access), kind in copies.items():
        copied[site] = kind if copied.get(site, kind) == kind else MEMBER_WISE
        by_place[(cls, offset)].append((site, access, kind))
    notes: dict[tuple[str, int], list[str]] = {}
    for name, row in model.types.items():
        if row.get("kind") not in ("class", "struct"):
            continue
        for offset, extent, role, entry in model.components(row):
            if role not in ("field", "bits") or not isinstance(offset, int) or not isinstance(extent, int):
                continue
            if role == "field" and model.composite(parse_type(entry.get("type"))) and not parse_type(entry.get("type"))["arrays"]:
                continue  # the member type's own rows show its copies
            found: dict[str, set[str]] = defaultdict(set)
            for cls, delta in windows.get(name, ()):
                for position in range(delta + offset, delta + offset + extent):
                    for site, access, kind in by_place.get((cls, position), ()):
                        found[kind].add(f"{site} {access}")
            texts = [
                (kind if kind == ZERO_FILL else f"{kind} copy")
                + f" ({'width-only evidence' if kind == MEMBER_WISE else 'neither width nor type evidence'}): "
                + ", ".join(sorted(found[kind]))
                for kind in sorted(found)
            ]
            if texts:
                notes[(name, offset)] = texts
    return notes, copied


# -- program ------------------------------------------------------------------


def _ghidra_path(model: _Plan, name: str) -> str:
    row = model.types[name]
    return f"{row['category']}/{_leaf(name)}"


def build_type_plan_program(
    root: Path, tracker: dict[str, Any] | None, plan_path: Path, layout: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Translate a valid plan into the type apply program format (file-only, deterministic)."""

    plan = load_json(plan_path)
    problems = validate_type_plan(root, tracker, plan, layout)
    if problems:
        raise SocomError(f"the type plan is not valid ({len(problems)} problems): {problems[:3]}")
    model = _Plan(plan)
    paths = {name: _ghidra_path(model, name) for name in model.types}
    order_names = sorted(model.types, key=lambda name: paths[name])
    temps = {name: f"{TEMP_PREFIX}{index:04d}" for index, name in enumerate(order_names, start=1)}
    external: set[str] = set()

    def render(text: str) -> str:
        parsed = parse_type(text)
        assert parsed is not None
        base = parsed["base"]
        if base in model.types:
            spelled = temps[base]
        elif base.startswith("/"):
            external.add(base)
            spelled = base.rsplit("/", 1)[1]
        else:
            spelled = base
        if parsed["pointers"]:
            spelled += " " + " ".join("*" for _ in range(parsed["pointers"]))
        return spelled + "".join(f"[{count}]" for count in parsed["arrays"])

    # Forward declarations first; then by-value dependencies first (bases and
    # composite members); pointers do not order.
    forwards = sorted((name for name in model.types if model.kind(name) == "forward"), key=lambda name: paths[name])
    dependencies: dict[str, set[str]] = {name: set() for name in model.types if name not in forwards}
    for name, row in model.types.items():
        if name in forwards:
            continue
        for _offset, _size, role, entry in model.components(row):
            if role in ("base", "field"):
                parsed = parse_type(entry.get("type"))
                if parsed and not parsed["pointers"] and parsed["base"] in model.types:
                    dependencies[name].add(parsed["base"])
    order: list[str] = list(forwards)
    remaining = {name: set(values) - set(forwards) for name, values in dependencies.items()}
    while remaining:
        ready = sorted((name for name, values in remaining.items() if not values), key=lambda name: paths[name])
        if not ready:
            raise SocomError("by-value type dependencies contain a cycle")
        for name in ready:
            order.append(name)
            del remaining[name]
        for values in remaining.values():
            values.difference_update(ready)

    entries = []
    for name in order:
        row = model.types[name]
        category, leaf = row["category"], _leaf(name)
        entry: dict[str, Any] = {
            "temp": temps[name],
            "path": paths[name],
            "category": category,
            "name": leaf,
            "kind": "struct",
            "structural_class": None,
        }
        if row["kind"] == "forward":
            entry.update(route="empty", size=None, expected_layout=[], declaration=True)
            entries.append(entry)
            continue
        if row["kind"] == "vtable" and row.get("opaque"):
            entry.update(route="empty", size=None, expected_layout=[])
            entries.append(entry)
            continue
        members = []
        for offset, extent, role, item in model.components(row):
            if role == "base":
                members.append({"offset": offset, "size": extent, "name": _base_component_name(item["type"]), "type": render(item["type"])})
            elif role == "vptr":
                members.append({"offset": offset, "size": 4, "name": VPTR_NAME, "type": render(item["type"])})
            elif role == "field":
                members.append({"offset": offset, "size": extent, "name": item["name"], "type": render(item["type"])})
            elif role == "bits":
                members.append({"offset": offset, "size": extent, "bits": sorted(item, key=lambda field: field["bit_offset"])})
        members.sort(key=lambda member: member["offset"])
        needs_c = any("bits" in member for member in members) or any(
            member.get("size") == 16 and not str(member.get("type", "")).endswith("*") for member in members
        )
        if needs_c:
            source, retypes, expected = _c_struct(temps[name], row["size"], members)
            entry.update(route="c", size=row["size"], c_source=source, retypes=retypes, expected_layout=expected)
        else:
            entry.update(
                route="fields",
                size=row["size"],
                fields=[{"offset": member["offset"], "name": member["name"], "type": member["type"], "size": member["size"]} for member in members],
                expected_layout=[[member["offset"], member["size"], member["type"], member["name"]] for member in members],
            )
        entries.append(entry)

    categories: set[str] = set()
    for entry in entries:
        parts = entry["category"].strip("/").split("/")
        for count in range(1, len(parts) + 1):
            categories.add("/" + "/".join(parts[:count]))
    relative = plan_path.resolve()
    try:
        relative = relative.relative_to(root.resolve())
    except ValueError:
        pass
    routes: dict[str, int] = defaultdict(int)
    for entry in entries:
        routes[entry["route"]] += 1
    layout_sources = sorted(
        (
            {
                "type": paths[name],
                "source": row["instantiation"]["source"],
                "size": row["instantiation"]["source_size"],
                "layout": row["instantiation"]["source_layout"],
            }
            for name, row in model.types.items()
            if row.get("instantiation") is not None
        ),
        key=lambda item: item["type"],
    )
    template_arguments = _live_arguments(model)
    return {
        "kind": APPLY_PROGRAM_KIND,
        "schema_version": APPLY_PROGRAM_SCHEMA,
        "mutation_performed": False,
        "source": TYPE_PLAN_KIND,
        "plan": {
            "path": relative.as_posix() if isinstance(relative, Path) else str(relative),
            "sha256": sha256_file(plan_path),
            "work_item_id": plan["work_item_id"],
        },
        "target": {"source_sha256": REFERENCE_SHA256, "program": "socom.elf"},
        "decisions": list(DECISIONS),
        "categories": sorted(categories, key=lambda path: (path.count("/"), path)),
        "types": entries,
        "external_types": sorted(external),
        "template_arguments": template_arguments,
        "layout_sources": layout_sources,
        "omissions": [],
        "receipt_scope": {"schema_version": 1, "functions": [], "types": sorted(entry["path"] for entry in entries), "globals": []},
        "summary": {
            "type_count": len(entries),
            "routes": dict(sorted(routes.items())),
            "external_type_count": len(external),
            "category_count": len(categories),
            "forward_declaration_count": len(forwards),
            "instantiation_count": len(layout_sources),
            "template_argument_count": len(template_arguments),
        },
    }


def _c_struct(temp: str, size: int, members: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], list[list[Any]]]:
    """A #pragma pack(1) C definition: direct builtins, placeholders for named types, LSB-first bitfields."""

    lines: list[str] = []
    retypes: list[dict[str, Any]] = []
    expected: list[list[Any]] = []
    cursor = 0

    def filler(until: int) -> None:
        nonlocal cursor
        while cursor < until:
            lines.append("  unsigned char : 8;")
            expected.append([cursor, 1, "uchar:8", "(unnamed)"])
            cursor += 1

    for member in members:
        filler(member["offset"])
        if "bits" in member:
            unit = member["size"]
            ghidra = member["bits"][0]["type"]
            c_type = C_SPELLING[ghidra]
            position = 0

            def pad(start: int, width: int) -> None:
                while width > 0:
                    step = min(width, unit * 8)
                    lines.append(f"  {c_type} : {step};")
                    expected.append(_bit_line(cursor, start, step, ghidra, "(unnamed)"))
                    start += step
                    width -= step

            for field in member["bits"]:
                if field["type"] != ghidra:
                    raise SocomError(f"{temp}: bitfields sharing a unit at {member['offset']} use one type")
                if not C_IDENTIFIER.match(field["name"]) or field["name"] in C_RESERVED:
                    raise SocomError(f"{temp}: bitfield name {field['name']!r} is not a C identifier")
                pad(position, field["bit_offset"] - position)
                lines.append(f"  {c_type} {field['name']} : {field['bit_size']};")
                expected.append(_bit_line(cursor, field["bit_offset"], field["bit_size"], ghidra, field["name"]))
                position = field["bit_offset"] + field["bit_size"]
            pad(position, unit * 8 - position)
            cursor += unit
            continue
        parsed = parse_type(member["type"])
        direct = parsed is not None and parsed["base"] in C_SPELLING and not parsed["arrays"]
        if direct and C_IDENTIFIER.match(member["name"]) and member["name"] not in C_RESERVED:
            stars = "*" * parsed["pointers"]
            lines.append(f"  {C_SPELLING[parsed['base']]} {stars}{member['name']};")
        else:
            placeholder = member["name"] if C_IDENTIFIER.match(member["name"]) and member["name"] not in C_RESERVED else f"{ANON_FIELD_PREFIX}{member['offset']:x}"
            lines.append(f"  unsigned char {placeholder}[{member['size']}];")
            retypes.append({"placeholder": placeholder, "type": member["type"], "name": member["name"]})
        expected.append([member["offset"], member["size"], member["type"], member["name"]])
        cursor += member["size"]
    filler(size)
    source = "#pragma pack(push, 1)\n" f"struct {temp} {{\n" + "\n".join(lines) + "\n};\n#pragma pack(pop)\n"
    return source, retypes, expected


def _bit_line(offset: int, bit: int, width: int, type_name: str, name: str) -> list[Any]:
    return [offset + bit // 8, (bit % 8 + width + 7) // 8, f"{type_name}:{width}", name]


def live_type_problems(
    program: dict[str, Any],
    type_index: list[dict[str, Any]],
    layout_of: Any = None,
) -> list[str]:
    """Read-only checks before an apply.

    Targets are absent and no live type shares a target's name (ignoring
    case), so later bare-name references stay unambiguous; a forward
    declaration's name also has no identity-unresolved ``<name>@<hash>``
    variant.  Live references, live template arguments and instantiation
    sources resolve to exactly their paths, and ``layout_of(leaf)`` (the
    parsed ``get_struct_layout`` read-back) of each source equals the
    recorded source layout.
    """

    problems = []
    by_name: dict[str, list[str]] = defaultdict(list)
    by_folded: dict[str, list[str]] = defaultdict(list)
    paths = set()
    for row in type_index:
        by_name[row["name"]].append(row["path"])
        by_folded[row["name"].casefold()].append(row["path"])
        paths.add(row["path"])
    for entry in program["types"]:
        if entry["path"] in paths:
            problems.append(f"{entry['path']} already exists")
        if by_name.get(entry["temp"]):
            problems.append(f"temporary name {entry['temp']} already exists")
        folded = (entry.get("name") or entry["path"].rsplit("/", 1)[1]).casefold()
        elsewhere = sorted(path for path in by_folded.get(folded, []) if path != entry["path"])
        if elsewhere:
            problems.append(f"{entry['path']}: live types of the same name exist at {elsewhere}")
        if entry.get("declaration"):
            variants = sorted(path for name, found in by_folded.items() if name.startswith(folded + "@") for path in found)
            if variants:
                problems.append(f"forward declaration {entry['path']}: identity-unresolved live variants {variants} exist; reference one instead")
    for path in program.get("external_types", []):
        leaf = path.rsplit("/", 1)[1]
        found = by_name.get(leaf, [])
        if found != [path]:
            problems.append(f"live type {leaf} resolves to {found or 'nothing'}, not exactly {path}")
    for argument in program.get("template_arguments", []):
        # The same rule as a live member type: the name resolves to exactly one live path, the expected one.
        found = sorted(by_name.get(argument["path"].rsplit("/", 1)[1], []))
        if found != [argument["path"]]:
            problems.append(
                f"template argument {argument['name']} of {', '.join(argument['types'])} resolves to "
                f"{found or 'nothing'}, not exactly {argument['path']}"
            )
    for source in program.get("layout_sources", []):
        leaf = source["source"].rsplit("/", 1)[1]
        found = sorted(by_folded.get(leaf.casefold(), []))
        if found != [source["source"]]:
            problems.append(f"instantiation source {leaf} resolves to {found or 'nothing'} (ignoring case), not exactly {source['source']}")
            continue
        if "&" in leaf:
            problems.append(f"instantiation source {leaf}: the bridge truncates names at '&', so its layout cannot be read back")
            continue
        if layout_of is None:
            continue
        live = layout_of(leaf)
        recorded = {"size": source["size"], "components": source["layout"]}
        if live != recorded:
            problems.append(f"instantiation source {source['source']}: the live layout {live} differs from the plan's source layout {recorded}")
    if any(name.startswith(TEMP_PREFIX) for name in by_name):
        problems.append("the program already contains temporary apply types")
    return problems


# -- affected reconstruction groups --------------------------------------------


def affected_groups(root: Path, tracker: dict[str, Any], classes: list[str], plans_dir: Path | None = None) -> dict[str, Any]:
    """Functions whose mangled receiver or parameters name the classes, by recon group.

    For each function the group's plan row tells whether it was left
    unresolved and whether the reason names one of the classes, so groups
    whose prototypes were skipped for want of these types can be re-planned
    after the type apply.
    """

    from .recon_facts import context
    from .type_layout import _Symbols

    ctx = context(root)
    symbols = _Symbols(ctx)

    def readable_key(components: Any) -> tuple[str, ...]:
        # Readable components without spaces: template instantiations compare with their mangled spelling.
        return tuple(normalized(readable_component(part)) for part in components or ())

    wanted = {tuple(normalized(part) for part in split_qualified(name)) for name in classes}
    readable = {name: name for name in classes}
    group_of: dict[str, dict[str, Any]] = {}
    for item in tracker.get("work_items", []):
        if item.get("kind") == "recon-plan-group":
            for address in (item.get("batch") or {}).get("functions", []):
                group_of[f"0x{int(address, 16):x}"] = item
    by_id = {item["id"]: item for item in tracker.get("work_items", [])}
    rows: dict[str, dict[str, Any]] = {}
    for address, row in sorted(symbols.functions.items()):
        parsed = row.get("parsed")
        if not parsed:
            continue
        mentions = set()
        if readable_key(parsed.get("qualifier")) in wanted:
            mentions.add("receiver")
        for value in _flatten(parsed.get("params") or []):
            if value.get("kind") == "class" and readable_key(value.get("components")) in wanted:
                mentions.add("parameter")
        if not mentions:
            continue
        key = f"0x{address:x}"
        group = group_of.get(key)
        entry = {
            "function": key,
            "name": symbols.readable(address),
            "mentions": sorted(mentions),
            "group": group["id"] if group else None,
        }
        if group:
            slug = group["id"].replace(":", "-")
            plan_path = (plans_dir or root / "build" / "recon-plans") / f"{slug}.json"
            entry["plan_status"] = group.get("status")
            entry["apply_status"] = (by_id.get(f"{group['id']}-apply") or {}).get("status")
            if plan_path.is_file():
                plan = load_json(plan_path)
                prow = next((item for item in plan.get("functions", []) if f"0x{int(item.get('address', '0'), 16):x}" == key), None)
                if prow is None:
                    entry["plan_row"] = "missing"
                elif prow.get("prototype"):
                    entry["plan_row"] = "prototype"
                else:
                    reasons = [str(text) for text in prow.get("unresolved") or []]
                    names = {_leaf(name) for name in readable} | set(readable)
                    named = any(
                        re.search(rf"(?<![A-Za-z0-9_:]){re.escape(name)}(?![A-Za-z0-9_])", text) for text in reasons for name in names
                    )
                    entry["plan_row"] = "unresolved-for-type" if named else "unresolved-other"
                    entry["reasons"] = reasons
            else:
                entry["plan_row"] = "no-plan-file"
        rows[key] = entry
    groups: dict[str, dict[str, Any]] = {}
    for entry in rows.values():
        if not entry["group"]:
            continue
        group = groups.setdefault(
            entry["group"],
            {"group": entry["group"], "plan_status": entry["plan_status"], "apply_status": entry["apply_status"], "functions": []},
        )
        group["functions"].append(entry["function"])
    replan = sorted({entry["group"] for entry in rows.values() if entry.get("plan_row") == "unresolved-for-type"})
    unplanned = sorted({entry["group"] for entry in rows.values() if entry.get("plan_row") == "no-plan-file"} - set(replan))
    for group in groups.values():
        rows_in = [rows[key] for key in group["functions"]]
        group["unresolved_for_type"] = sorted(row["function"] for row in rows_in if row.get("plan_row") == "unresolved-for-type")
        # An applied group is corrected by a governed repair or a later plan; a planned one can be reopened.
        group["route"] = (
            "unplanned" if group["group"] in unplanned
            else "replan" if group["group"] in replan and group["apply_status"] in ("blocked", "ready")
            else "after-apply" if group["group"] in replan
            else "none"
        )
    return {
        "kind": "socom-type-plan-affected-groups",
        "classes": sorted(classes),
        "functions": [rows[key] for key in sorted(rows, key=lambda value: int(value, 16))],
        "groups": [groups[key] for key in sorted(groups)],
        "replan_candidates": replan,
        "unplanned_groups": unplanned,
        "summary": {
            "function_count": len(rows),
            "group_count": len(groups),
            "unresolved_for_type": sum(1 for entry in rows.values() if entry.get("plan_row") == "unresolved-for-type"),
            "replan_candidate_count": len(replan),
            "unplanned_group_count": len(unplanned),
        },
    }


def _flatten(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for value in values:
        result.append(value)
        if value.get("kind") == "function":
            result.extend(_flatten(value.get("params") or []))
            result.extend(_flatten([value["result"]]))
        elif value.get("kind") == "array":
            result.extend(_flatten([value["element"]]))
        elif value.get("kind") == "member_pointer":
            result.extend(_flatten([value["pointee"]]))
    return result


def plan_classes(plan: dict[str, Any]) -> list[str]:
    """Proven (not invented) names of the plan's classes, structs and forward declarations."""

    return sorted(
        row["name"]
        for row in plan.get("types") or []
        if row.get("kind") in ("class", "struct", "forward") and row.get("name_provenance") in ("elf-symbol", *NAME_PROOFS)
    )


__all__ = [
    "TYPE_PLAN_KIND",
    "TYPE_PLAN_PREFIX",
    "TYPE_PLAN_RESOURCES",
    "affected_groups",
    "build_type_plan_program",
    "layout_sha256",
    "live_type_problems",
    "plan_classes",
    "render_type_plan",
    "type_plan_item_id",
    "type_plan_slug",
    "validate_type_plan",
]

