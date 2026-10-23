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
         "opaque_reason": "slot return types are not encoded in the mangled names"}
      ]
    }

Type spellings: Ghidra builtins (``uint``, ``uchar``, ``longlong``, ``uint16``
...), ``undefined1/2/4/8`` only where every access is neutral, plan types by
their qualified name, and existing live types by their full Ghidra path
(``/project/std/__vector_pod<unsigned int, std::allocator<unsigned int>>``);
``*`` pointers and ``[n]`` arrays follow the base.  A field with
``bit_offset``/``bit_size`` is a bitfield (least-significant-bit position in
its little-endian storage unit at ``offset``/``size``).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .batch_apply import BUILTIN_SIZES
from .constants import REFERENCE_SHA256
from .mwdemangle import split_qualified
from .type_apply import ANON_FIELD_PREFIX, APPLY_PROGRAM_KIND, APPLY_PROGRAM_SCHEMA, C_IDENTIFIER, C_RESERVED, TEMP_PREFIX
from .type_layout import NEUTRAL_KINDS, class_layout
from .util import SocomError, canonical_json, load_json, sha256_file

TYPE_PLAN_KIND = "socom-code-type-plan"
TYPE_PLAN_SCHEMA = 1
TYPE_PLAN_PREFIX = "socom:work:type-plan-"
TYPE_PLAN_RESOURCES = ["build/type-plans"]
INVENTED = "invented-provisional"
NAME_PROVENANCES = ("elf-symbol", INVENTED)
FIELD_PROVENANCES = (INVENTED, "elf-string", "elf-symbol")
VPTR_NAME = "__vt"
FIELD_NAME = re.compile(r"^m_[a-z][A-Za-z0-9]*$")
HELPER_NAME = re.compile(r"^tag_[A-Za-z0-9_]+$")
_TYPE = re.compile(r"^(?P<base>[^\[\]*]+?)\s*(?P<stars>(?:\*\s*)*)(?P<arrays>(?:\[\d+\])*)$")
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
    "A base class is a component at its RTTI base-list offset named by the bare base type name; the "
    "vtable pointer is a component named __vt.",
    "A vtable type whose slot function types are not all proven is created opaque (an empty struct) so the "
    "vptr can point to it without a void * placeholder.",
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
    if not isinstance(text, str):
        return None
    match = _TYPE.match(text.strip())
    if not match:
        return None
    base = match.group("base").strip()
    if not base:
        return None
    return {
        "base": base,
        "pointers": match.group("stars").count("*"),
        "arrays": [int(count) for count in re.findall(r"\[(\d+)\]", match.group("arrays"))],
    }


class _Plan:
    """Plan types by name, with sizes, alignments and evidence windows."""

    def __init__(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.types: dict[str, dict[str, Any]] = {}
        for row in plan.get("types") or []:
            if isinstance(row, dict) and isinstance(row.get("name"), str):
                self.types.setdefault(row["name"], row)

    def size_of(self, parsed: dict[str, Any] | None, declared: Any = None) -> int | None:
        if parsed is None:
            return None
        count = 1
        for value in parsed["arrays"]:
            count *= value
        if parsed["pointers"]:
            return 4 * count
        base = parsed["base"]
        if base in SIZES:
            return SIZES[base] * count
        if base in self.types and isinstance(self.types[base].get("size"), int):
            return self.types[base]["size"] * count
        return declared if isinstance(declared, int) else None

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
            size = self.size_of(parse_type(base.get("type")))
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
        elif (item.get("batch") or {}).get("class") != class_name or bool((item.get("batch") or {}).get("with_derived")) != bool(
            spec.get("with_derived")
        ):
            problems.append(f"{plan.get('work_item_id')} plans a different class or derived scope")
    if layout is None:
        layout = class_layout(root, class_name, bool(spec.get("with_derived")))
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
    model = _Plan(plan)
    names = [row.get("name") for row in plan.get("types") or []]
    if len(names) != len(set(names)):
        problems.append("type names repeat")
    if class_name not in model.types:
        problems.append(f"the plan does not define the requested class {class_name}")
    invented = False
    windows = model.windows(set(by_class))
    for row in plan.get("types") or []:
        name = row.get("name")
        where = f"type {name}"
        if not isinstance(name, str) or not name:
            problems.append("a type has no name")
            continue
        kind = row.get("kind")
        if kind not in ("class", "struct", "vtable"):
            problems.append(f"{where}: kind must be class, struct or vtable")
            continue
        provenance = row.get("name_provenance")
        if provenance not in NAME_PROVENANCES:
            problems.append(f"{where}: name_provenance must be one of {list(NAME_PROVENANCES)}")
        leaf = _leaf(name)
        if provenance == "elf-symbol" and name not in by_class:
            problems.append(f"{where}: elf-symbol names must be a class in the layout evidence")
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
        problems.extend(_type_problems(model, row, where, by_class, index, windows.get(name, set())))
    if invented and not plan.get("naming_survey"):
        problems.append("invented names need a naming_survey of neighbouring zdb DWARF names")
    for row in plan.get("types") or []:
        for field in row.get("fields") or []:
            parsed = parse_type(field.get("type"))
            if parsed and parsed["base"].startswith("/") and not parsed["base"].startswith("/project/"):
                problems.append(f"type {row.get('name')} field {field.get('name')}: live types are /project paths")
    return problems


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
) -> list[str]:
    problems: list[str] = []
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
    elif not row.get("size_evidence"):
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
            base_name = _leaf(str(entry.get("type", "")))
            if entry.get("name") not in (None, base_name):
                problems.append(f"{where}: the base component is named {base_name}, the bare base type name")
            names.add(base_name)
        elif role == "vptr":
            problems.extend(_vptr_problems(model, row, entry, layout_row, index, where))
            names.add(VPTR_NAME)
        elif role == "padding":
            for cls, delta in sorted(windows):
                for site_offset, site in _sites_in(index.get(cls, {}), delta + offset - 15, delta + offset + extent):
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
            problems.append(f"{label}: invented member names are m_ followed by camelCase")
        elif provenance != INVENTED and not field.get("name_evidence"):
            problems.append(f"{label}: a non-invented name cites name_evidence")
        problems.extend(_field_problems(model, field, label, index, windows))

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
    if base not in model.types:
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


def _field_problems(
    model: _Plan, field: dict[str, Any], label: str, index: dict[str, dict[int, list[dict[str, Any]]]],
    windows: set[tuple[str, int]],
) -> list[str]:
    problems: list[str] = []
    parsed = parse_type(field.get("type"))
    offset, size = field.get("offset"), field.get("size")
    if parsed is None or parsed["base"] == "void" and not parsed["pointers"]:
        return [f"{label}: type {field.get('type')!r} is not a type spelling"]
    if not isinstance(offset, int) or not isinstance(size, int):
        return [f"{label}: offset and size are integers"]
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
    composite = model.composite(parsed) and not parsed["arrays"]
    evidence = field.get("evidence") or []
    if not evidence:
        problems.append(f"{label}: cite at least one evidence site")
    # Candidate sites: the field's extent in every window.
    candidates: list[tuple[str, int, dict[str, Any]]] = []
    for cls, delta in sorted(windows):
        for site_offset, site in _sites_in(index.get(cls, {}), delta + offset, delta + offset + size):
            candidates.append((cls, site_offset - delta, site))
    by_site: dict[str, list[tuple[str, int, dict[str, Any]]]] = defaultdict(list)
    for cls, relative, site in candidates:
        by_site[site["site"]].append((cls, relative, site))
    for cited in evidence:
        if cited not in by_site:
            problems.append(f"{label}: evidence {cited} is not an access within +{_hex(offset)}..+{_hex(offset + size - 1)}")
    if composite or parsed["arrays"]:
        return problems  # inner accesses belong to the member type; extent checks above
    exact = [(cls, relative, site) for cls, relative, site in candidates if relative == offset]
    cited_exact = [site for cls, relative, site in exact if site["site"] in evidence]
    if evidence and not cited_exact and not bitfield:
        problems.append(f"{label}: no cited evidence site accesses the field's first byte")
    width_size = size
    for cls, relative, site in candidates:
        if relative != offset:
            if not bitfield and site.get("access") != "address-passed":
                problems.append(f"{label}: {site['site']} accesses +{_hex(relative)} inside the scalar field ({cls})")
            continue
        if not _compatible(site, parsed, None if bitfield else width_size):
            problems.append(f"{label}: {site['site']} ({site.get('access')} w{site.get('width')} {site.get('kind')}) contradicts {field.get('type')}")
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
        typed = sorted({site.get("parameter_type") for site in strong if site.get("parameter_type") and "void" not in site["parameter_type"]})
        if typed:
            problems.append(f"{label}: void * is a placeholder; the evidence passes it as {typed[0]}")
        if any(site.get("access", "").startswith("deref") for site in strong) and not field.get("unresolved"):
            problems.append(f"{label}: void * is dereferenced; type the pointee or record why in unresolved")
    if not parsed["pointers"] and any(site.get("pointer") for _cls, relative, site in exact):
        problems.append(f"{label}: the evidence dereferences this field, so it is a pointer")
    return problems


# -- review table -------------------------------------------------------------


def render_type_plan(plan: dict[str, Any], layout: dict[str, Any], problems: list[str]) -> str:
    sites: dict[str, dict[str, Any]] = {}
    for cls in layout["classes"]:
        for row in cls["offsets"]:
            for site in row["sites"]:
                sites.setdefault(site["site"], site)
    model = _Plan(plan)
    lines = [
        f"# code-derived type plan {plan.get('work_item_id')}",
        f"layout {plan.get('layout', {}).get('class')} (with derived: {bool(plan.get('layout', {}).get('with_derived'))}) "
        f"sha256 {plan.get('layout', {}).get('sha256')}",
        "provenance: elf-symbol = name from .symtab/RTTI; invented-provisional = invented, review before use",
    ]
    for survey in plan.get("naming_survey") or []:
        lines.append(f"naming survey: {survey}")
    for row in plan.get("types") or []:
        lines.append("")
        lines.append(
            f"## {row.get('name')} [{row.get('kind')}] {row.get('category')}/{_leaf(str(row.get('name')))} "
            f"size {_hex(row['size']) if isinstance(row.get('size'), int) else row.get('size')} align {row.get('alignment')} "
            f"name {row.get('name_provenance')}"
        )
        for text in row.get("size_evidence") or []:
            lines.append(f"  size evidence: {text}")
        if row.get("kind") == "vtable" and row.get("opaque"):
            lines.append(f"  opaque: {row.get('opaque_reason')}")
        lines.append("  offset  size  type                                      name                      provenance             evidence  sample sites")
        rows = []
        for offset, extent, role, entry in model.components(row):
            if role == "base":
                rows.append((offset, extent, entry.get("type"), _leaf(str(entry.get("type"))), "rtti base", entry.get("evidence") or []))
            elif role == "vptr":
                rows.append((offset, 4, entry.get("type"), VPTR_NAME, "user decision", entry.get("evidence") or []))
            elif role == "padding":
                rows.append((offset, extent, "(padding)", "", "no access", []))
            elif role == "bits":
                for field in sorted(entry, key=lambda item: item.get("bit_offset", 0)):
                    bits = f"{field.get('type')}:{field.get('bit_size')}@bit{field.get('bit_offset')}"
                    rows.append((offset, extent, bits, field.get("name"), field.get("provenance"), field.get("evidence") or []))
            else:
                rows.append((offset, extent, entry.get("type"), entry.get("name"), entry.get("provenance"), entry.get("evidence") or []))
        for offset, extent, type_name, name, provenance, evidence in sorted(rows, key=lambda item: (item[0] if isinstance(item[0], int) else -1, str(item[3]))):
            samples = []
            for site in evidence[:3]:
                found = sites.get(site)
                samples.append(f"{site} {found['insn']}" if found else f"{site} (not in evidence)")
            lines.append(
                f"  {_hex(offset) if isinstance(offset, int) else offset!s:>6}  {_hex(extent) if isinstance(extent, int) else extent!s:>4}  "
                f"{str(type_name):<40}  {str(name):<24}  {str(provenance):<21}  {len(evidence):>8}  {'; '.join(samples)}"
            )
        for entry in row.get("outside_accesses") or []:
            lines.append(f"  outside access {entry.get('site')}: {entry.get('reason')}")
        for text in row.get("unresolved") or []:
            lines.append(f"  unresolved: {text}")
    lines.append("")
    lines.append(f"validation: {'ok' if not problems else f'{len(problems)} problem(s)'}")
    lines.extend(f"  - {text}" for text in problems)
    return "\n".join(lines) + "\n"


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

    # By-value dependencies first (bases and composite members); pointers do not order.
    dependencies: dict[str, set[str]] = {name: set() for name in model.types}
    for name, row in model.types.items():
        for _offset, _size, role, entry in model.components(row):
            if role in ("base", "field"):
                parsed = parse_type(entry.get("type"))
                if parsed and not parsed["pointers"] and parsed["base"] in model.types:
                    dependencies[name].add(parsed["base"])
    order: list[str] = []
    remaining = {name: set(values) for name, values in dependencies.items()}
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
        if row["kind"] == "vtable" and row.get("opaque"):
            entry.update(route="empty", size=None, expected_layout=[])
            entries.append(entry)
            continue
        members = []
        for offset, extent, role, item in model.components(row):
            if role == "base":
                members.append({"offset": offset, "size": extent, "name": _leaf(item["type"]), "type": render(item["type"])})
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
        "omissions": [],
        "receipt_scope": {"schema_version": 1, "functions": [], "types": sorted(entry["path"] for entry in entries), "globals": []},
        "summary": {
            "type_count": len(entries),
            "routes": dict(sorted(routes.items())),
            "external_type_count": len(external),
            "category_count": len(categories),
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


def live_type_problems(program: dict[str, Any], type_index: list[dict[str, Any]]) -> list[str]:
    """Read-only checks before an apply: targets absent, live references unique and at their paths."""

    problems = []
    by_name: dict[str, list[str]] = defaultdict(list)
    paths = set()
    for row in type_index:
        by_name[row["name"]].append(row["path"])
        paths.add(row["path"])
    for entry in program["types"]:
        if entry["path"] in paths:
            problems.append(f"{entry['path']} already exists")
        if by_name.get(entry["temp"]):
            problems.append(f"temporary name {entry['temp']} already exists")
    for path in program.get("external_types", []):
        leaf = path.rsplit("/", 1)[1]
        found = by_name.get(leaf, [])
        if found != [path]:
            problems.append(f"live type {leaf} resolves to {found or 'nothing'}, not exactly {path}")
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
    wanted = {tuple(split_qualified(name)) for name in classes}
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
        if tuple(parsed.get("qualifier") or ()) in wanted:
            mentions.add("receiver")
        for value in _flatten(parsed.get("params") or []):
            if value.get("kind") == "class" and tuple(value.get("components") or ()) in wanted:
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
    return sorted(row["name"] for row in plan.get("types") or [] if row.get("kind") in ("class", "struct") and row.get("name_provenance") == "elf-symbol")


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

