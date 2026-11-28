"""Stage 3, globals: carry the prototype's data names, then types, into the release program.

    python tools/release/globals.py --plan gamez/zSeal                 # or --plan --all
    python tools/release/globals.py --apply build/release/globals/plan-gamez-zSeal.json --dry-run
    python tools/release/globals.py --apply build/release/globals/plan-gamez-zSeal.json --yes [--batch N] [--only 0x..]
    python tools/release/globals.py --confirm-saved build/release/globals/plan-gamez-zSeal.apply-001.json
    python tools/release/globals.py --discard-unsaved build/release/globals/plan-gamez-zSeal.apply-001.json

``--plan`` reads ``docs/release/data-map.tsv`` (the checked data pairing), the release ELF and,
read-only, both Ghidra programs; it writes ``build/release/globals/plan-<module>.json`` and a summary
``.md``, deterministic, with its own digest. Nothing is written to Ghidra. ``--apply`` makes the
planned writes to ``SCUS_971.34`` only, through three ordinary bridge writes, and never saves.

What the bridge does (GhidraMCP 6.0.0 and Ghidra 12.1.4, read from the classes):

* ``create_label`` (``SymbolLabelService.createLabel``) refuses a LABEL of the same name at the
  address, then calls ``SymbolTable.createLabel(addr, name, USER_DEFINED)`` in the global
  namespace (``SymbolManager.createLabel``): no code unit is touched; a DEFAULT-named function at
  the address takes the name instead (``tryUpdatingDefaultFunction``); a dynamic primary symbol
  (``DAT_``, ``PTR_``, ``s_``...) is deleted and the new label becomes primary; otherwise the new
  label is added as a secondary one. Symbol events start no analysis (``AutoAnalysisManager``
  has no symbol task; its handler is commented out). The name is only checked for invisible or
  whitespace characters (``SymbolUtilities.validateName``).
* ``apply_data_type`` (``DataTypeService.applyDataType``) resolves ``type_name`` by name, not by
  path (``ServiceUtils.resolveDataType``: Ghidra's well-known names first, then a root type
  ``/<name>`` or ``/<lower name>``, then the first type of any category whose name equals the
  name, case ignored, then arrays and pointers built from such a name). With ``clear_existing``
  true (the plugin's default) it clears the range whenever a code unit is at the address, which is
  always; this tool sends false only (the client refuses anything else), so only
  ``Listing.createData`` runs: ``CodeManager.createCodeUnit`` throws before it changes anything
  when any instruction or defined data (an analysis ``undefinedN`` included) overlaps the range.
  The new data's pointer components get DATA references to their values, unless 0 or all ones
  (``CodeManager.addDataReferences``); the CODE_ADDED event schedules the data analyzers. The only
  one that can run here is "Data Reference" (``DataOperandReferenceAnalyzer``): for each reference
  from the new data to a target that is undefined bytes or analysis ``undefined`` data it may
  disassemble (no function, no bookmark), or define a string, a unicode string or a pointer there;
  a target that is an instruction, a string, a pointer or other defined data is left alone, and a
  target outside every memory block is skipped. "Function Start Search After Data" runs only with
  ``after="data"`` patterns, which the R5900 pattern file has none of. A primary name starting
  ``g_`` can make the naming policy refuse a type (a JSON answer ``status: rejected``, nothing
  changed); the type is written before the labels so the primary is still dynamic.
* ``set_comment`` (``CommentService.setComment``) replaces the comment of one kind at an address
  (``CodeManager.setComment``: on the code unit there, or a comment record), starts no analysis.
  The provenance comment is a one-line PLATE comment at the data start, written only where no plate
  is or this tool's own one is.
* Never sent: ``set_global`` (always ``clearCodeUnits``, errors swallowed), ``apply_data_classification``
  (clears like ``apply_data_type``), ``rename_data`` (a global naming policy, no per-call override).

The plan (per committed pair of the map; unsure, new and removed rows are counted, not named):

* **Labels** (step A): the prototype program's primary symbol at the prototype address (read with
  ``audit_global`` on ``socom.elf``, checked to be a stored label of the global namespace) and the
  map's ELF symbol as a second label where it differs. Literals (``@N``) and anonymous objects get
  none. Withheld, with the reason: a map withhold, two committed pairs at one release address
  (conflicting rows), an address no release memory block holds (the release program has no block
  for the zero-filled part of its PT_LOAD, 0x48d200..0x5d6cff), a function (entry or body), an
  instruction, an address inside a defined data item (an offcut label), a stored label at the
  address that is not a planned one (user or analysis), a release primary symbol in another
  namespace, a prototype symbol in a namespace, an invalid name, a name a release function has.
  A dynamic name (``DAT_``, ``PTR_``, ``s_``) is replaced: harmless, the data item stays.
* **Types** (step B): the prototype's data item at the prototype address when its type is not
  placeholder-like (``undefinedN``, ``undefinedN[k]``, the bare ``pointer``, ``undefined *``),
  exists in the release at the same path and size, resolves by name to exactly that type, the
  map gives a confirmed release size at least its length (deviating: the size equal), the flags
  are none of ``size-changed``, ``offset-outside``, ``size-from-release``, the release range is
  undefined bytes, in no function and no instruction, overlaps no other paired object, and every
  pointer component's value points at nothing analysis could define (an instruction, defined data
  other than ``undefined``, an address no block holds, or 0).
* **Step C** (counted, never written): the objects a real type would have to replace analysis data
  in, with items, bytes, kinds and the outgoing references a clear would drop, and how many of
  those the new type would make again.

The apply: preflight (open programs, hashes, idle analysis), plan digest and map, no unsaved
record rows; per entry in address order the type, then the labels, then the comment, each checked
before (the live state the plan saw, or this tool's own result) and read back after; a light
snapshot (function list, defined data, stored labels, bookmarks) after every type and every
``--check-every`` entries and at the end, compared with the prediction. Rows go to
``docs/release/ghidra-applied.tsv`` (kinds ``data-label``, ``data-label-mangled``, ``data-type``,
``data-comment``) as ``unsaved <report>`` until ``--confirm-saved``.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as _dt
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import elfimage  # noqa: E402
import ghidra_bridge as gb  # noqa: E402
import names  # noqa: E402
import protofacts  # noqa: E402
import signatures as sg  # noqa: E402
from names import Refused, Stop, canonical, hx, sha256_text  # noqa: E402

DATA_MAP = Path("docs/release/data-map.tsv")
SETTLED = Path("docs/release/settled-data.tsv")
OUT = Path("build/release/globals")
PLAN_KIND = "socom-release-globals-plan"
PLAN_SCHEMA = 1
COMMENT_PREFIX = "Release data map: "
CHECK_EVERY = 25  # entries between two light snapshots
COMMITTED = ("exact", "deviating")
LABEL, MANGLED, TYPE, COMMENT = "data-label", "data-label-mangled", "data-type", "data-comment"
NO_TYPE_FLAGS = ("size-changed", "offset-outside", "size-from-release")
CARRY_NAME_ONLY = "carry the name, not"  # a map withhold that keeps the name and drops the type
PLACEHOLDER = re.compile(r"^(?:undefined\d*|pointer\d*|undefined\d* \*)(?:\[\d+\])*$")
# ServiceUtils.resolveWellKnownType: name (case ignored) -> the built-in it returns
WELL_KNOWN = {
    "int": "int", "uint": "uint", "short": "short", "ushort": "ushort", "long": "long", "ulong": "ulong",
    "longlong": "longlong", "long long": "longlong", "char": "char", "uchar": "uchar", "float": "float",
    "double": "double", "bool": "bool", "boolean": "bool", "void": "void", "byte": "byte", "sbyte": "sbyte",
    "word": "word", "dword": "dword", "qword": "qword", "int8_t": "sbyte", "int8": "sbyte", "uint8_t": "byte",
    "uint8": "byte", "int16_t": "short", "int16": "short", "uint16_t": "ushort", "uint16": "ushort",
    "int32_t": "int", "int32": "int", "uint32_t": "uint", "uint32": "uint", "int64_t": "longlong",
    "int64": "longlong", "uint64_t": "ulonglong", "uint64": "ulonglong", "size_t": "uint",
    "unsigned int": "uint", "unsigned short": "ushort", "unsigned long": "ulong", "unsigned char": "uchar",
    "signed char": "sbyte"}
# Ghidra built-ins at the root that hold no pointer
SCALARS = frozenset({"char", "uchar", "schar", "sbyte", "byte", "bool", "short", "ushort", "int", "uint", "long",
                     "ulong", "longlong", "ulonglong", "float", "double", "longdouble", "word", "dword", "qword",
                     "wchar_t", "wchar16", "wchar32", "string", "TerminatedCString", "unicode", "unicode32",
                     "int3", "uint3", "int5", "uint5", "int6", "uint6", "int7", "uint7", "int16", "uint16"})
DYNAMIC_STRINGS = frozenset({"string", "TerminatedCString", "unicode", "TerminatedUnicode"})
_GLOBAL = re.compile(r"^(.*) @ ([0-9a-fA-F]+) \[(\w+)\](?: \((.*)\))? xrefs=(\d+)$")
_DATA = re.compile(r"^.* @ ([0-9a-fA-F]+) \[(.*)\] \((\d+) bytes?\)$")
_SEGMENT = re.compile(r"^(.*): ([0-9a-fA-F]+) - ([0-9a-fA-F]+)$")
_LAYOUT = re.compile(r"^\s*(\d+) \|\s*(\d+) \| (.*?)\s* \| (.*)$")

AFTER_NOTHING = ("nothing was sent for this entry and every earlier write read back as planned: save, "
                 "--confirm-saved this report, then replan")
AFTER_A_WRITE = ("the program may hold something else than planned at this entry: read it; save and "
                 "--confirm-saved this report (it records what reads back), or close without saving and "
                 "--discard-unsaved it; then replan")
AFTER_ANALYSIS = ("have the changes listed under analysis_changes checked: if they are acceptable, save and "
                  "--confirm-saved this report (it records this run's writes, not those changes); if not, close "
                  "without saving and --discard-unsaved it; then replan")
WHAT_TO_DO = {"StopBefore": AFTER_NOTHING, "StopAfter": AFTER_A_WRITE, "AnalysisStop": AFTER_ANALYSIS,
              "Stop": AFTER_A_WRITE, "BridgeError": AFTER_A_WRITE}


# --- inputs ------------------------------------------------------------------------------------

def load_data_map(root: Path) -> tuple[list[dict], str]:
    path = root / DATA_MAP
    if not path.is_file():
        raise Refused(f"{DATA_MAP.as_posix()} is missing: run python tools/release/datapair.py")
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.splitlines()
    header = lines[0].split("\t")
    need = {"release_address", "release_size", "prototype_address", "prototype_size", "prototype_symbol", "class",
            "evidence", "flags", "withhold", "owner_file"}
    if not need <= set(header):
        raise Refused(f"{DATA_MAP.as_posix()} lacks the columns {sorted(need - set(header))}")
    rows = []
    for line in lines[1:]:
        cells = dict(zip(header, line.split("\t")))
        cells["flag_set"] = sorted(f for f in cells["flags"].split(",") if f and f != "-")
        cells["module"] = protofacts.module_of("" if cells["owner_file"] == "-" else cells["owner_file"]) or "(no owner)"
        rows.append(cells)
    return rows, sha256_text(text)


def current_map_sha(root: Path) -> str:
    return sha256_text((root / DATA_MAP).read_text(encoding="utf-8").replace("\r\n", "\n"))


def committed(row: dict) -> bool:
    return row["class"] in COMMITTED and row["release_address"] not in ("-", "") and \
        row["prototype_address"] not in ("-", "")


def select(rows: list[dict], module: str | None) -> list[dict]:
    chosen = [r for r in rows if r["release_address"] not in ("-", "")]
    if module:
        chosen = [r for r in chosen if r["module"] == module]
        if not chosen:
            known = sorted({r["module"] for r in rows})
            raise Refused(f"no data-map row in module {module!r}; modules: {', '.join(known)}")
    return sorted(chosen, key=lambda r: (int(r["release_address"], 16), r["prototype_address"]))


def confirmed_size(text: str) -> int | None:
    return int(text) if text.isdigit() else None


# --- live reads --------------------------------------------------------------------------------

def read_segments(bridge, program: str) -> list[tuple[int, int, str]]:
    """Memory blocks of the default space: (start, end inclusive, name)."""

    text = bridge.get("list_segments", program, offset=0, limit=10000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"list_segments ({program}): {str(text)[:200]}")
    out = []
    for line in text.splitlines():
        match = _SEGMENT.match(line.strip())
        if match and "::" not in line:
            out.append((int(match.group(2), 16), int(match.group(3), 16), match.group(1)))
    return sorted(out)


def in_memory(segments, address: int, length: int = 1) -> bool:
    last = address + max(length, 1) - 1
    return any(lo <= address and last <= hi for lo, hi, _ in segments)


def read_data(bridge, program: str) -> list[tuple[int, int, str]]:
    """Every defined data item: (address, length, type name), sorted."""

    text = bridge.get("list_data_items", program, offset=0, limit=10000000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"list_data_items ({program}): {str(text)[:200]}")
    out = []
    for line in text.splitlines():
        if match := _DATA.match(line.strip()):
            out.append((int(match.group(1), 16), int(match.group(3)), match.group(2)))
    return sorted(out)


def is_dynamic(name: str, address: int) -> bool:
    """A dynamic symbol's name: a prefix and the address (``DAT_00464fe0``, ``s_text_00464fe0``)."""

    return bool(re.match(r"^[A-Za-z]+_", name or "")) and (name or "").endswith("_%08x" % address)


def read_labels(bridge, program: str, substring: str | None = None) -> dict[int, list[str]]:
    """Stored labels of the global namespace outside code (``list_globals``), by address, in listed order."""

    value = bridge.get("list_globals", program, offset=0, limit=10000000, filter="all", type_filter="all",
                       min_xrefs=0, include_all_sections=True, name_substring=substring or None)
    if not isinstance(value, str):
        raise gb.BridgeError(f"list_globals ({program}): {str(value)[:200]}")
    out: dict[int, list[str]] = defaultdict(list)
    for line in value.splitlines():
        match = _GLOBAL.match(line.strip())
        if not match or match.group(3) != "Label":
            continue
        address = int(match.group(2), 16)
        if not is_dynamic(match.group(1), address) and match.group(1) not in out[address]:
            out[address].append(match.group(1))
    return dict(out)


def audit(bridge, program: str, address: int) -> dict:
    value = bridge.get("audit_global", program, address=hx(address))
    if not isinstance(value, dict) or "error" in value:
        raise gb.BridgeError(f"audit_global {program} {hx(address)}: {str(value)[:200]}")
    return value


def read_comment(bridge, address: int) -> dict:
    value = bridge.get("get_comment", gb.RELEASE_PROGRAM, address=hx(address))
    if not isinstance(value, dict) or "error" in value:
        raise gb.BridgeError(f"get_comment {hx(address)}: {str(value)[:200]}")
    return {k: value.get(k) or "" for k in ("plate", "pre", "eol", "post", "repeatable")}


def refs_from(bridge, address: int) -> list[tuple[int, str]]:
    text = bridge.get("get_xrefs_from", gb.RELEASE_PROGRAM, address=hx(address), offset=0, limit=1000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"get_xrefs_from {hx(address)}: {str(text)[:200]}")
    return sorted((int(a, 16), kind) for a, kind in re.findall(r"^To ([0-9a-fA-F]+)\b.*\[(\w+)\]$", text, re.M))


def function_at(bridge, address: int) -> dict | None:
    """The release function whose body holds ``address`` (or starts there), else None."""

    return names.read_function(bridge, gb.RELEASE_PROGRAM, address)


def parallel(bridge, items, read):
    """``read(client, item)`` over items with the bridge's three read clients."""

    items = list(items)
    clients = bridge.clones(3)
    if len(clients) == 1 or len(items) < 64:
        return {item: read(bridge, item) for item in items}
    parts = [items[i::len(clients)] for i in range(len(clients))]
    out = {}
    with ThreadPoolExecutor(len(clients)) as pool:
        for part in pool.map(lambda p: {item: read(p[0], item) for item in p[1]}, zip(clients, parts)):
            out.update(part)
    return out


class DataIndex:
    """Defined data items of one program, by start, with containing and overlap lookups."""

    def __init__(self, items):
        self.items = sorted(items)
        self.starts = [d[0] for d in self.items]
        self.at = {d[0]: d for d in self.items}

    def overlapping(self, address: int, length: int) -> list[tuple]:
        end = address + max(length, 1)
        k = max(bisect.bisect_right(self.starts, address) - 1, 0)
        out = []
        while k < len(self.items) and self.items[k][0] < end:
            d = self.items[k]
            if d[0] + d[1] > address:
                out.append(d)
            k += 1
        return out

    def containing(self, address: int):
        k = bisect.bisect_right(self.starts, address) - 1
        if k >= 0 and self.items[k][0] <= address < self.items[k][0] + self.items[k][1]:
            return self.items[k]
        return None


# --- types -------------------------------------------------------------------------------------

def resolves_to(name: str, path: str, release_types: dict) -> str | None:
    """None when ``apply_data_type`` with this name resolves to the type at ``path``; else the reason."""

    well = WELL_KNOWN.get(name.lower())
    if well is not None:
        return None if (well == name and path == "/" + name) else \
            f"the plugin resolves {name} as the built-in {well}, not {path}"
    rows = [(n, p) for n, found in release_types.items() for p, _ in found]
    roots = [p for n, p in rows if p in ("/" + name, "/" + name.lower())]
    if any(p != path for p in roots):
        return f"the plugin takes the root type {roots[0]} for {name}"
    same = sorted({p for n, p in rows if n.lower() == name.lower()})
    if same != [path]:
        return f"{len(same)} release types are named {name} with case ignored; the plugin takes the first"
    return None


class TypeInfo:
    """Pointer components of release types, read through ``get_struct_layout`` and ``get_enum_values``."""

    def __init__(self, bridge, release_types: dict):
        self.bridge, self.types = bridge, release_types
        self.cache: dict[str, tuple] = {}

    def size_of(self, name: str) -> int | None:
        found = self.types.get(name, [])
        return found[0][1] if len(found) == 1 else None

    def pointers(self, name: str, depth: int = 0) -> tuple[list[int] | None, str | None]:
        """(offsets of the pointer components, None) or (None, the reason they are not known)."""

        if name in self.cache:
            return self.cache[name]
        result = self._pointers(name.strip(), depth)
        self.cache[name] = result
        return result

    def _pointers(self, name: str, depth: int):
        if depth > 12:
            return None, f"{name}: nested too deep"
        if name.endswith("*") or re.fullmatch(r"pointer\d*", name):
            return [0], None
        array = re.fullmatch(r"(.*)\[(\d+)\]", name)
        if array:
            element, count = array.group(1).strip(), int(array.group(2))
            inner, why = self.pointers(element, depth + 1)
            if inner is None:
                return None, why
            if not inner:
                return [], None
            size = 4 if element.endswith("*") else self.size_of(element)
            if not size:
                return None, f"element {element} has no known size"
            return [k * size + o for k in range(count) for o in inner], None
        found = self.types.get(name, [])
        if name in SCALARS and (not found or found[0][0] == "/" + name):
            return [], None
        if re.fullmatch(r"undefined\d*", name):
            return [], None
        if len(found) != 1:
            return None, f"{name}: {len(found)} release types of that name"
        enum = self.bridge.get("get_enum_values", gb.RELEASE_PROGRAM, enum_name=name)
        if isinstance(enum, str) and enum.startswith("Enumeration:"):
            if enum.splitlines()[0][len("Enumeration:"):].strip() != name:
                return None, f"get_enum_values {name} answered another enumeration"
            return [], None
        layout = self.bridge.get("get_struct_layout", gb.RELEASE_PROGRAM, struct_name=name)
        if not isinstance(layout, str) or not layout.startswith("Structure: "):
            return None, f"the layout of {name} is not readable through the bridge (union, typedef or other)"
        if layout.splitlines()[0][len("Structure: "):].strip() != name:
            return None, f"get_struct_layout {name} answered another structure"
        out = []
        for line in layout.splitlines():
            match = _LAYOUT.match(line)
            if not match:
                continue
            offset, component = int(match.group(1)), match.group(3).strip()
            inner, why = self.pointers(component, depth + 1)
            if inner is None:
                return None, f"{name}+{offset}: {why}"
            out += [offset + o for o in inner]
        return sorted(out), None


def string_length(image, address: int) -> int | None:
    """A C string's length with its NUL, read from the release bytes."""

    if not image.contains(address):
        return None
    stop = image.data.find(b"\0", address - image.base)
    return None if stop < 0 else stop - (address - image.base) + 1


def data_kind(type_name: str) -> str:
    if type_name in DYNAMIC_STRINGS or "string" in type_name.lower() or type_name.startswith(("unicode", "char[")):
        return "string"
    if type_name.endswith("*") or re.fullmatch(r"pointer\d*(?:\[\d+\])*", type_name):
        return "pointer"
    if re.fullmatch(r"undefined\d*(?:\[\d+\])*", type_name):
        return "untyped scalar"
    return "other"


# --- the plan ----------------------------------------------------------------------------------

def comment_text(row: dict) -> str:
    flags = ", ".join(row["flag_set"]) or "none"
    return (f"{COMMENT_PREFIX}{row['class']} pair with prototype {row['prototype_address']} "
            f"{row['prototype_symbol']} (evidence {row['evidence']}; flags {flags})")


def source_pair(row: dict) -> str:
    return f"p {row['prototype_address']} {row['prototype_symbol']} ({row['class']})"


def build_plan(root: Path, bridge, module: str | None, image=None, progress=None) -> dict:
    say = progress or (lambda message: None)
    rows, map_sha = load_data_map(root)
    chosen = select(rows, module)
    image = image or elfimage.load(root / names.RELEASE_ELF, "release")
    say("reading both programs")
    segments = read_segments(bridge, gb.RELEASE_PROGRAM)
    rel_data = DataIndex(read_data(bridge, gb.RELEASE_PROGRAM))
    pro_data = DataIndex(read_data(bridge, gb.PROTOTYPE_PROGRAM))
    rel_labels = read_labels(bridge, gb.RELEASE_PROGRAM)
    pro_labels = read_labels(bridge, gb.PROTOTYPE_PROGRAM)
    rel_functions = names.function_list(bridge, gb.RELEASE_PROGRAM)
    function_names = {f["name"] for f in rel_functions.values()}
    rel_types = sg.type_table(bridge, gb.RELEASE_PROGRAM)
    pro_types = sg.type_table(bridge, gb.PROTOTYPE_PROGRAM)
    types = TypeInfo(bridge, rel_types)
    every = [r for r in rows if committed(r) and (r["withhold"] == "-" or CARRY_NAME_ONLY in r["withhold"])]
    by_release: dict[int, list[dict]] = defaultdict(list)
    for r in every:
        by_release[int(r["release_address"], 16)].append(r)
    starts = sorted(by_release)
    picked = [r for r in chosen if committed(r)]
    say(f"{len(picked)} committed pairs selected; reading per address")
    addresses = sorted({int(r["release_address"], 16) for r in picked})
    rel_audit = parallel(bridge, addresses, lambda c, a: audit(c, gb.RELEASE_PROGRAM, a))
    words = sorted({a & ~3 for a in addresses} - set(addresses))
    rel_audit.update(parallel(bridge, words, lambda c, a: audit(c, gb.RELEASE_PROGRAM, a)))
    rel_function = parallel(bridge, addresses, lambda c, a: function_at(c, a))
    pro_audit = parallel(bridge, sorted({int(r["prototype_address"], 16) for r in picked}),
                         lambda c, a: audit(c, gb.PROTOTYPE_PROGRAM, a))
    in_module = [r for r in rows if not module or r["module"] == module]
    entries, not_named = [], Counter(r["class"] for r in in_module if not committed(r))
    later_comments, type_candidates = [], []
    for row in picked:
        r, p = int(row["release_address"], 16), int(row["prototype_address"], 16)
        entry = {"address": hx(r), "prototype": hx(p), "symbol": row["prototype_symbol"], "class": row["class"],
                 "evidence": row["evidence"], "flags": row["flag_set"], "module": row["module"],
                 "release_size": row["release_size"], "prototype_size": row["prototype_size"],
                 "source_pair": source_pair(row), "labels": [], "label_reason": None, "comment": None,
                 "comment_reason": None, "type": None, "type_reason": None, "step_c": None}
        state = rel_audit[r]
        here = rel_data.containing(r)
        entry["live"] = {"primary": state.get("name") or "", "stored": rel_labels.get(r, []),
                         "data": [hx(here[0]), here[1], here[2]] if here else None,
                         "xref_count": state.get("xref_count")}
        withhold = row["withhold"]
        shared = [x["prototype_symbol"] for x in by_release.get(r, []) if x is not row]
        fn = rel_function.get(r)
        code = bool(rel_audit[r & ~3].get("is_code_address")) or bool(state.get("is_code_address"))
        common = None  # a reason that stops both the labels and the type
        if withhold != "-" and CARRY_NAME_ONLY not in withhold:
            common = f"withheld by the data map: {withhold}"
        elif shared:
            common = f"conflicting rows: the release address is also paired with {', '.join(shared)}"
        elif not in_memory(segments, r):
            common = f"no release memory block holds {hx(r)} (the program has none for the PT_LOAD's zero-filled part)"
        elif fn is not None:
            common = f"a release function: {fn['name']} at {hx(fn['entry'])}"
        elif code:
            common = "an instruction holds this address"
        entry["label_reason"] = common or decide_labels(entry, row, here, state, pro_audit[p], pro_labels.get(p, []),
                                                       rel_labels.get(r, []), function_names)
        if entry["labels"]:
            later_comments.append((entry, row))
        if common or CARRY_NAME_ONLY in withhold:
            entry["type_reason"] = common or "the data map carries the name, not the entries"
        else:
            type_candidates.append((entry, row))
        entries.append(entry)
    say(f"comments for {len(later_comments)} entries")
    comments = parallel(bridge, [int(e["address"], 16) for e, _ in later_comments], lambda c, a: read_comment(c, a))
    for entry, row in later_comments:
        decide_comment(entry, comments[int(entry["address"], 16)], row)
    say(f"types for {len(type_candidates)} entries")
    for entry, row in type_candidates:
        decide_type(entry, row, bridge, image, segments, rel_data, pro_data, pro_types, rel_types, types, starts)
    plan = {
        "kind": PLAN_KIND, "schema_version": PLAN_SCHEMA, "program": gb.RELEASE_PROGRAM,
        "selection": module or "--all", "data_map_sha256": map_sha,
        "segments": [[hx(lo), hx(hi), name] for lo, hi, name in segments],
        "entries": entries, "not_named": dict(sorted(not_named.items())),
    }
    plan["summary"] = summarize(plan)
    plan["plan_sha256"] = sha256_text(canonical(plan))
    return plan


def decide_labels(entry, row, here, state, pro_state, pro_stored, rel_stored, function_names) -> str | None:
    """Fill ``entry['labels']``, or return the reason no label is planned."""

    r = int(entry["address"], 16)
    symbol = row["prototype_symbol"]
    if symbol in ("", "-"):
        return "no prototype symbol (an anonymous object)"
    if symbol.startswith("@"):
        return "a literal (@N): no name"
    if here is not None and here[0] < r:
        return f"inside the release data item {here[2]} at {hx(here[0])} (an offcut label)"
    p = int(row["prototype_address"], 16)
    primary = pro_state.get("name") or ""
    readable = None
    if primary and not is_dynamic(primary, p):
        if primary not in pro_stored:
            return f"the prototype's symbol {primary} is not a label of the global namespace"
        # an assembler-local label (.dma.1, .vu.6, $L12) names a place, not the object: the ELF symbol does
        readable = None if primary.startswith((".", "$")) else primary
    planned = [readable] if readable else []
    if symbol != readable:
        planned.append(symbol)
    for name in planned:
        # SymbolUtilities.validateName: not empty, at most 2000 characters, no blank or invisible character
        if not name or len(name) > 2000 or any(ch.isspace() or not ch.isprintable() for ch in name):
            return f"the name {name!r} is no valid Ghidra label"
        if name in function_names:
            return f"the name {name} is a release function's name"
    other = [n for n in rel_stored if n not in planned]
    if other:
        return f"the release address already has the label {other[0]} (not this tool's)"
    live_primary = state.get("name") or ""
    if live_primary and not is_dynamic(live_primary, r) and live_primary not in rel_stored:
        return f"the release primary symbol {live_primary} is not a label of the global namespace"
    entry["labels"] = [{"name": n, "kind": LABEL if i == 0 else MANGLED, "present": n in rel_stored}
                       for i, n in enumerate(planned)]
    return None


def decide_comment(entry: dict, current: dict, row: dict) -> None:
    text = comment_text(row)
    plate = current["plate"]
    if plate and plate != text and not plate.startswith(COMMENT_PREFIX):
        entry["comment_reason"] = "a plate comment not written by this tool is there"
        return
    entry["comment"] = {"text": text, "type": "plate", "before": plate}


def decide_type(entry, row, bridge, image, segments, rel_data, pro_data, pro_types, rel_types, types, starts):
    r, p = int(entry["address"], 16), int(entry["prototype"], 16)
    flagged = [f for f in NO_TYPE_FLAGS if f in row["flag_set"]]
    if flagged:
        entry["type_reason"] = f"the map flags {', '.join(flagged)}: no type from the prototype"
        return
    item = pro_data.at.get(p)
    if item is None:
        entry["type_reason"] = "no prototype data item starts at the prototype address (nothing to carry)"
        return
    name, length = item[2], item[1]
    if PLACEHOLDER.match(name):
        entry["type_reason"] = f"placeholder type {name} in the prototype (nothing to carry)"
        return
    size = confirmed_size(row["release_size"])
    if size is None:
        entry["type_reason"] = f"release size not confirmed ({row['release_size']})"
        return
    if row["class"] == "deviating" and str(size) != row["prototype_size"]:
        entry["type_reason"] = f"deviating pair: release size {size}, prototype size {row['prototype_size']}"
        return
    found = pro_types.get(name, [])
    if len(found) != 1:
        entry["type_reason"] = f"{len(found)} prototype types are named {name}"
        return
    path, type_size = found[0]
    there = [x for x in rel_types.get(name, []) if x[0] == path]
    if not there:
        # applying it would add the type to the release type table (createData resolves it there)
        entry["type_reason"] = f"the release has no type {path} (applying it would add the type to the release)"
        return
    if there[0][1] != type_size:
        entry["type_reason"] = f"{path} has {there[0][1]} bytes in the release, {type_size} in the prototype"
        return
    why = resolves_to(name, path, rel_types)
    if why:
        entry["type_reason"] = why
        return
    over = rel_data.overlapping(r, length)
    if over and over[0][0] == r and over[0][2] == name:
        if over[0][1] == length or name in DYNAMIC_STRINGS:
            entry["type"] = {"name": name, "path": path, "length": over[0][1], "references": [], "present": True}
            return
    if name in DYNAMIC_STRINGS:
        # TerminatedCString ends at the NUL; the prototype's analysis item may include the alignment padding
        made = string_length(image, r) if name in ("string", "TerminatedCString") else None
        if made is None or made > length:
            entry["type_reason"] = f"{name} would be {made} bytes from the release bytes, {length} in the prototype"
            return
        length = made
        over = rel_data.overlapping(r, length)
    if length > size:
        entry["type_reason"] = f"the type is {length} bytes, the release object {size}"
        return
    inside = [hx(a) for a in starts if r < a < r + length]
    if inside:
        entry["type_reason"] = f"overlaps the paired object at {inside[0]}"
        return
    if not in_memory(segments, r, length):
        entry["type_reason"] = "the range leaves the release memory block"
        return
    if over:
        entry["type_reason"] = "analysis defined data in the range (step C)"
        entry["step_c"] = step_c(bridge, r, length, name, over, types)
        return
    words = [a for a in range(r & ~3, r + length, 4)]
    for w in words:
        if audit(bridge, gb.RELEASE_PROGRAM, w).get("is_code_address"):
            entry["type_reason"] = f"an instruction at {hx(w)} in the range"
            return
        fn = function_at(bridge, w)
        if fn is not None:
            entry["type_reason"] = f"the range reaches the function {fn['name']} at {hx(fn['entry'])}"
            return
    offsets, why = types.pointers(name)
    if offsets is None:
        entry["type_reason"] = why
        return
    references = []
    for k in offsets:
        if (r + k) % 4 or k + 4 > length:
            entry["type_reason"] = f"a pointer component at +{k} is not word aligned"
            return
        value = image.word(r + k) if image.contains(r + k) else 0
        if value in (0, 0xFFFFFFFF):
            continue
        risk = pointer_risk(bridge, value, segments, rel_data)
        if risk:
            entry["type_reason"] = f"the pointer at +{k} holds {hx(value)}, {risk}: Data Reference analysis may define data or code there"
            return
        references.append({"from": hx(r + k), "to": hx(value)})
    entry["type"] = {"name": name, "path": path, "length": length, "references": references, "present": False}


def pointer_risk(bridge, value: int, segments, rel_data) -> str | None:
    """Why analysis could act at a pointer's target, or None (an instruction, defined data, no block)."""

    if not in_memory(segments, value):
        return None  # "Data Reference" skips a target no block holds; the reference is still made
    there = rel_data.containing(value)
    if there is not None:
        return f"analysis {there[2]} data at {hx(there[0])}" if there[2].startswith("undefined") else None
    if audit(bridge, gb.RELEASE_PROGRAM, value & ~3).get("is_code_address"):
        return None
    return "undefined bytes"


def step_c(bridge, r: int, length: int, name: str, over, types) -> dict:
    """What replacing the analysis items of the range with the real type would drop and re-create."""

    offsets, _ = types.pointers(name)
    keep = {r + k for k in offsets} if offsets is not None else None
    items, lost, again = [], Counter(), Counter()
    for a, n, t in over:
        kind = data_kind(t)
        places = range(a, a + n, 4) if kind == "pointer" and n > 4 else [a]
        refs = [(w, target, ref) for w in places for target, ref in refs_from(bridge, w)]
        lost[kind] += len(refs)
        if keep is not None:
            again[kind] += sum(1 for w, _, _ in refs if w in keep)
        items.append({"address": hx(a), "length": n, "type": t, "kind": kind, "references": len(refs),
                      "crosses": a < r or a + n > r + length})
    return {"type": name, "bytes": length, "items": items, "references_lost": dict(lost),
            "references_recreated": dict(again) if keep is not None else None}


def summarize(plan: dict) -> dict:
    entries = plan["entries"]
    labels = [l for e in entries for l in e["labels"]]
    c = [e["step_c"] for e in entries if e["step_c"]]
    items = [i for x in c for i in x["items"]]
    lost, again = Counter(), Counter()
    unknown = 0
    for x in c:
        lost.update(x["references_lost"])
        if x["references_recreated"] is None:
            unknown += 1
        else:
            again.update(x["references_recreated"])
    return {
        "committed_pairs": len(entries), "not_named_rows": plan["not_named"],
        "labels_planned": sum(1 for l in labels if l["kind"] == LABEL and not l["present"]),
        "second_labels_planned": sum(1 for l in labels if l["kind"] == MANGLED and not l["present"]),
        "labels_present": sum(1 for l in labels if l["present"]),
        "entries_named": sum(1 for e in entries if e["labels"]),
        "single_aligned_named": sum(1 for e in entries if e["labels"] and "single-aligned" in e["flags"]),
        "deviating_named": sum(1 for e in entries if e["labels"] and e["class"] == "deviating"),
        "comments_planned": sum(1 for e in entries if e["comment"] and e["comment"]["before"] != e["comment"]["text"]),
        "comments_withheld": dict(Counter(e["comment_reason"] for e in entries if e["comment_reason"])),
        "types_planned": sum(1 for e in entries if e["type"] and not e["type"]["present"]),
        "types_present": sum(1 for e in entries if e["type"] and e["type"]["present"]),
        "types_planned_by_name": dict(sorted(Counter(e["type"]["name"] for e in entries
                                                     if e["type"] and not e["type"]["present"]).items())),
        "references_predicted": sum(len(e["type"]["references"]) for e in entries if e["type"] and not e["type"]["present"]),
        "labels_withheld": dict(sorted(Counter(withheld_group(e["label_reason"]) for e in entries
                                               if e["label_reason"]).items())),
        "types_withheld": dict(sorted(Counter(withheld_group(e["type_reason"]) for e in entries
                                              if e["type_reason"]).items())),
        "step_c": {"objects": len(c), "bytes": sum(x["bytes"] for x in c), "items": len(items),
                   "items_by_kind": dict(sorted(Counter(i["kind"] for i in items).items())),
                   "items_crossing_the_object": sum(1 for i in items if i["crosses"]),
                   "references_lost": dict(sorted(lost.items())), "references_recreated": dict(sorted(again.items())),
                   "objects_whose_layout_is_unknown": unknown},
    }


def withheld_group(reason: str) -> str:
    for prefix, group in (("withheld by the data map", "map withhold"), ("conflicting rows", "conflicting rows"),
                          ("no release memory block", "outside release memory"),
                          ("a release function", "function"), ("an instruction", "instruction"),
                          ("no prototype symbol", "anonymous"), ("a literal", "literal"),
                          ("inside the release data item", "inside a data item"),
                          ("the release address already has", "existing label"),
                          ("the release primary symbol", "other namespace (release)"),
                          ("the prototype's symbol", "other namespace (prototype)"),
                          ("the name", "name"), ("the map flags", "size flag"),
                          ("no prototype data item", "no prototype data item"),
                          ("placeholder type", "placeholder type"), ("release size not confirmed", "size unconfirmed"),
                          ("deviating pair", "deviating size"), ("analysis defined data", "step C"),
                          ("the data map carries the name", "name only"), ("overlaps", "overlap"),
                          ("the pointer at", "pointer target"), ("the layout of", "layout unknown"),
                          ("the release has no type", "type missing"), ("the range", "code or block")):
        if reason.startswith(prefix):
            return group
    return "type resolution" if "type" in reason or "plugin" in reason else "other"


def plan_markdown(plan: dict) -> str:
    s = plan["summary"]
    lines = [f"# Globals plan: {plan['selection']}", "",
             f"Data map `{plan['data_map_sha256'][:16]}`; plan sha256 `{plan['plan_sha256']}`.", "",
             f"- committed pairs: {s['committed_pairs']}; rows not named (not committed): {s['not_named_rows']}",
             f"- labels planned: {s['labels_planned']}; second (mangled) labels: {s['second_labels_planned']}; "
             f"already present: {s['labels_present']}; entries named: {s['entries_named']} "
             f"({s['deviating_named']} deviating, {s['single_aligned_named']} single-aligned, flagged in the comment)",
             f"- comments planned: {s['comments_planned']}; withheld: {s['comments_withheld']}",
             f"- labels withheld: {s['labels_withheld']}",
             f"- types planned: {s['types_planned']} {s['types_planned_by_name']}; already present: "
             f"{s['types_present']}; references the new types make: {s['references_predicted']}",
             f"- types withheld: {s['types_withheld']}",
             f"- step C (not built, for the user's decision): {s['step_c']}", ""]
    planned = [e for e in plan["entries"] if e["type"] and not e["type"]["present"]]
    if planned:
        lines += ["## Types planned", "", "| Release | Prototype | Symbol | Type | Length | References |",
                  "|---|---|---|---|---|---|"]
        lines += [f"| {e['address']} | {e['prototype']} | `{e['symbol']}` | `{e['type']['path']}` | {e['type']['length']} | "
                  f"{', '.join(x['to'] for x in e['type']['references']) or '-'} |" for e in planned]
        lines.append("")
    c = [e for e in plan["entries"] if e["step_c"]]
    if c:
        lines += ["## Step C: real types that would replace analysis data", "",
                  "| Release | Symbol | Type | Bytes | Items | References lost / re-created |", "|---|---|---|---|---|---|"]
        for e in c:
            x = e["step_c"]
            lines.append(f"| {e['address']} | `{e['symbol']}` | `{x['type']}` | {x['bytes']} | "
                         f"{', '.join(i['type'] for i in x['items'])} | {x['references_lost']} / {x['references_recreated']} |")
    return "\n".join(lines) + "\n"


def plan_stem(selection: str) -> str:
    return "plan-" + ("all" if selection == "--all" else re.sub(r"[^A-Za-z0-9._-]+", "-", selection).strip("-"))


def write_plan(root: Path, plan: dict) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    stem = plan_stem(plan["selection"])
    (out / f"{stem}.json").write_text(canonical(plan), encoding="utf-8", newline="\n")
    (out / f"{stem}.md").write_text(plan_markdown(plan), encoding="utf-8", newline="\n")
    return out / f"{stem}.json"


def load_plan(path: Path, root: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("kind") != PLAN_KIND or plan.get("schema_version") != PLAN_SCHEMA:
        raise Refused(f"{path.name} is not a schema {PLAN_SCHEMA} globals plan")
    if plan.get("program") != gb.RELEASE_PROGRAM:
        raise Refused(f"the plan targets {plan.get('program')!r}; writes go to {gb.RELEASE_PROGRAM} only")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if sha256_text(canonical(body)) != plan.get("plan_sha256"):
        raise Refused(f"{path.name} does not match its plan_sha256: regenerate it instead of editing it")
    if plan.get("data_map_sha256") != current_map_sha(root):
        raise Refused(f"{path.name} was made from another {DATA_MAP.as_posix()}: replan")
    return plan


# --- the apply ---------------------------------------------------------------------------------

def light(bridge) -> dict:
    """What analysis could change after these writes, cheaply: functions, data, labels, bookmarks."""

    functions = names.function_list(bridge, gb.RELEASE_PROGRAM)
    return {"functions": {a: (f["name"], f["thunk"]) for a, f in functions.items()},
            "data": set(read_data(bridge, gb.RELEASE_PROGRAM)),
            "labels": {a: set(v) for a, v in read_labels(bridge, gb.RELEASE_PROGRAM).items()},
            "bookmarks": set(sg_bookmarks(bridge))}


def sg_bookmarks(bridge) -> list[tuple]:
    value = bridge.get("list_bookmarks", gb.RELEASE_PROGRAM)
    if not isinstance(value, dict) or not isinstance(value.get("bookmarks"), list):
        raise gb.BridgeError(f"list_bookmarks: {str(value)[:200]}")
    return sorted((int(b["address"], 16), b.get("type"), b.get("category"), b.get("comment")) for b in value["bookmarks"])


def ok_label(answer) -> bool:
    return isinstance(answer, dict) and answer.get("status") == "success"


def ok_type(answer, entry) -> bool:
    expected = f"Successfully applied data type '{entry['type']['name']}' at {entry['address']} " \
               f"(size: {entry['type']['length']} bytes)"
    return isinstance(answer, str) and answer.startswith(expected)


class Applier:
    def __init__(self, bridge, plan: dict, image, dry_run: bool, batch: int | None = None, only=frozenset(),
                 check_every: int = CHECK_EVERY, recorded=frozenset()):
        self.bridge, self.plan, self.image, self.dry_run = bridge, plan, image, dry_run
        self.batch, self.only, self.check_every = batch, set(only), max(1, check_every)
        self.recorded = set(recorded)
        self.written: list[dict] = []
        self.attempted: list[dict] = []
        self.would: list[dict] = []
        self.unchanged: Counter = Counter()
        self.skipped: list[dict] = []
        self.analysis_changes: list[dict] = []
        self.references: list[dict] = []
        self.changed_entries = 0
        self.batch_full = False
        self.checks = 0
        self.after_stop: list[dict] = []

    def item(self, entry, applied, value, **extra) -> dict:
        return dict({"address": entry["address"], "applied": applied, "value": value,
                     "source_pair": entry["source_pair"]}, **extra)

    def send(self, item: dict, endpoint: str, ok, **body):
        if self.dry_run:
            self.would.append(dict(item, endpoint=endpoint, body=body))
            return None
        self.attempted.append(item)
        answer = self.bridge.write(endpoint, gb.RELEASE_PROGRAM, **body)
        if not ok(answer):
            raise sg.StopAfter(f"{endpoint} at {item['address']} answered {str(answer)[:300]!r}: {AFTER_A_WRITE}")
        return answer

    def run(self) -> None:
        self.before = light(self.bridge)
        self.expected = {"data": set(self.before["data"]), "labels": {a: set(v) for a, v in self.before["labels"].items()}}
        entries = sorted(self.plan["entries"], key=lambda e: int(e["address"], 16))
        if self.only:
            unknown = sorted(self.only - {e["address"] for e in entries})
            if unknown:
                raise sg.StopBefore(f"--only {unknown[0]}: not an entry of the plan")
            entries = [e for e in entries if e["address"] in self.only]
        since = 0
        try:
            for entry in entries:
                if not (entry["labels"] or entry["type"] or entry["comment"]):
                    continue
                if self.batch and self.changed_entries >= self.batch:
                    self.batch_full = True
                    break
                if self.entry(entry):
                    self.changed_entries += 1
                    since += 1
                if since >= self.check_every and not self.dry_run:
                    self.check(f"after {entry['address']}")
                    since = 0
        except Stop:
            if not self.dry_run and self.bridge.sent and not self.analysis_changes:
                # what else the program shows after the stop, for the coordinator (not a second stop)
                try:
                    self.after_stop = self.differences("after the stop")
                except (Stop, gb.BridgeError) as exc:
                    self.after_stop = [{"error": str(exc)}]
            raise
        if not self.dry_run and self.bridge.sent:
            self.check("at the end")

    def check(self, when: str) -> None:
        """Compare a light snapshot with the prediction; any difference stops the run."""

        changes = self.differences(when)
        if changes:
            self.analysis_changes = [dict(c, seen=when) for c in changes]
            raise sg.AnalysisStop(f"the program differs from the prediction {when} ({len(changes)} differences, "
                                  f"listed under analysis_changes): {AFTER_ANALYSIS}")

    def differences(self, when: str) -> list[dict]:
        names.settle(self.bridge)
        now = light(self.bridge)
        self.checks += 1
        changes = []
        for a in sorted(set(now["functions"]) | set(self.before["functions"])):
            if now["functions"].get(a) != self.before["functions"].get(a):
                changes.append({"function": hx(a), "before": self.before["functions"].get(a),
                                "after": now["functions"].get(a)})
        for d in sorted(now["data"] ^ self.expected["data"]):
            changes.append({"data": [hx(d[0]), d[1], d[2]], "change": "added" if d in now["data"] else "missing"})
        for a in sorted(set(now["labels"]) | set(self.expected["labels"])):
            got, want = now["labels"].get(a, set()), self.expected["labels"].get(a, set())
            if got != want:
                changes.append({"labels": hx(a), "added": sorted(got - want), "missing": sorted(want - got)})
        for b in sorted(now["bookmarks"] ^ self.before["bookmarks"]):
            changes.append({"bookmark": [hx(b[0]), b[1], b[2], b[3]],
                            "change": "added" if b in now["bookmarks"] else "removed"})
        return changes

    def entry(self, entry: dict) -> bool:
        address = int(entry["address"], 16)
        writes = len(self.would) + len(self.bridge.sent)
        state = audit(self.bridge, gb.RELEASE_PROGRAM, address)
        if state.get("is_code_address") or state.get("is_function_entry"):
            raise sg.StopBefore(f"{entry['address']} holds code now: {AFTER_NOTHING}")
        if function_at(self.bridge, address) is not None:
            raise sg.StopBefore(f"{entry['address']} lies in a function now: {AFTER_NOTHING}")
        # The labels there: those the plan saw, or this tool's own (an earlier, saved run).
        stored = set(self.expected["labels"].get(address, set()))
        planned = {label["name"] for label in entry["labels"]}
        extra = stored - planned - set(entry["live"]["stored"])
        if extra:
            raise sg.StopBefore(f"{entry['address']} has the labels {sorted(stored)} now, the plan saw "
                                f"{entry['live']['stored']}: {AFTER_NOTHING}")
        primary = state.get("name") or ""
        if entry["labels"] and primary and not is_dynamic(primary, address) and primary not in stored:
            raise sg.StopBefore(f"{entry['address']}: the primary symbol is {primary!r} now: {AFTER_NOTHING}")
        if entry["type"]:
            self.type(entry, state)
        for label in entry["labels"]:
            self.label(entry, label, stored)
        if entry["comment"]:
            self.comment(entry)
        return len(self.would) + len(self.bridge.sent) > writes

    def type(self, entry: dict, state: dict) -> None:
        address, t = int(entry["address"], 16), entry["type"]
        want = (address, t["length"], t["name"])
        if state.get("type") == t["name"] and state.get("length") == t["length"]:
            self.unchanged["type"] += 1
            return
        rel_data = DataIndex(read_data(self.bridge, gb.RELEASE_PROGRAM))
        live = rel_data.overlapping(address, t["length"])
        if live:
            raise sg.StopBefore(f"{entry['address']}: defined data {live[0][2]} at {hx(live[0][0])} lies in the range "
                                f"now: {AFTER_NOTHING}")
        for w in range(address & ~3, address + t["length"], 4):
            if audit(self.bridge, gb.RELEASE_PROGRAM, w).get("is_code_address") or \
                    function_at(self.bridge, w) is not None:
                raise sg.StopBefore(f"{entry['address']}: code at {hx(w)} in the range now: {AFTER_NOTHING}")
        segments = [(int(lo, 16), int(hi, 16), n) for lo, hi, n in self.plan["segments"]]
        for ref in t["references"]:
            risk = pointer_risk(self.bridge, int(ref["to"], 16), segments, rel_data)
            if risk:
                raise sg.StopBefore(f"{entry['address']}: the pointer target {ref['to']} is {risk} now: {AFTER_NOTHING}")
        value = f"{t['name']} ({t['path']}, {t['length']} bytes)"
        item = self.item(entry, TYPE, value, type_name=t["name"], length=t["length"])
        if self.send(item, "apply_data_type", lambda a: ok_type(a, entry), address=entry["address"],
                     type_name=t["name"], clear_existing=False, strict_mode="off") is None:
            self.expected["data"].add(want)
            return
        names.settle(self.bridge)
        back = audit(self.bridge, gb.RELEASE_PROGRAM, address)
        if back.get("type") != t["name"] or back.get("length") != t["length"]:
            raise sg.StopAfter(f"apply_data_type {entry['address']} read back {back.get('type')!r} "
                               f"{back.get('length')!r}: {AFTER_A_WRITE}")
        if back.get("xref_count") != state.get("xref_count"):
            raise sg.StopAfter(f"{entry['address']}: references to it went from {state.get('xref_count')} to "
                               f"{back.get('xref_count')}: {AFTER_A_WRITE}")
        for ref in t["references"]:
            made = refs_from(self.bridge, int(ref["from"], 16))
            if not any(target == int(ref["to"], 16) for target, _ in made):
                raise sg.StopAfter(f"{entry['address']}: no reference from {ref['from']} to {ref['to']}: {AFTER_A_WRITE}")
            self.references.append(dict(ref, kinds=sorted({k for target, k in made if target == int(ref["to"], 16)})))
        self.written.append(item)
        self.expected["data"].add(want)
        self.check(f"after the type at {entry['address']}")

    def label(self, entry: dict, label: dict, stored: set) -> None:
        address, name = int(entry["address"], 16), label["name"]
        if name in stored:
            self.unchanged["label"] += 1
            return
        before = audit(self.bridge, gb.RELEASE_PROGRAM, address)
        item = self.item(entry, label["kind"], name)
        if self.send(item, "create_label", ok_label, address=entry["address"], name=name) is None:
            self.expected["labels"].setdefault(address, set()).add(name)
            return
        back = audit(self.bridge, gb.RELEASE_PROGRAM, address)
        first = entry["labels"][0]["name"]
        if back.get("name") != first:
            raise sg.StopAfter(f"create_label {name} at {entry['address']}: the primary symbol reads "
                               f"{back.get('name')!r}, expected {first!r}: {AFTER_A_WRITE}")
        for key in ("type", "length", "xref_count", "is_code_address", "is_function_entry"):
            if back.get(key) != before.get(key):
                raise sg.StopAfter(f"create_label {name} at {entry['address']} changed {key} from "
                                   f"{before.get(key)!r} to {back.get(key)!r}: {AFTER_A_WRITE}")
        if name not in read_labels(self.bridge, gb.RELEASE_PROGRAM, substring=name).get(address, []):
            raise sg.StopAfter(f"label {name} at {entry['address']} does not read back: {AFTER_A_WRITE}")
        self.written.append(item)
        stored.add(name)
        self.expected["labels"].setdefault(address, set()).add(name)

    def comment(self, entry: dict) -> None:
        address, c = int(entry["address"], 16), entry["comment"]
        current = read_comment(self.bridge, address)
        if current["plate"] == c["text"]:
            self.unchanged["comment"] += 1
            return
        if current["plate"] != c["before"]:
            raise sg.StopBefore(f"{entry['address']}: the plate comment is {current['plate']!r} now, the plan saw "
                                f"{c['before']!r}: {AFTER_NOTHING}")
        item = self.item(entry, COMMENT, c["text"])
        if self.send(item, "set_comment", gb.ok_status, address=entry["address"], comment=c["text"],
                     type="plate") is None:
            return
        back = read_comment(self.bridge, address)
        if back["plate"] != c["text"] or {k: v for k, v in back.items() if k != "plate"} != \
                {k: v for k, v in current.items() if k != "plate"}:
            raise sg.StopAfter(f"set_comment {entry['address']} read back {back!r}: {AFTER_A_WRITE}")
        self.written.append(item)


def reads_back(bridge, item: dict) -> bool:
    """Does the program hold a row of this tool?"""

    address = int(item["address"], 16)
    if item["applied"] in (LABEL, MANGLED):
        return item["value"] in read_labels(bridge, gb.RELEASE_PROGRAM, substring=item["value"]).get(address, [])
    if item["applied"] == TYPE:
        state = audit(bridge, gb.RELEASE_PROGRAM, address)
        return state.get("type") == item["type_name"] and state.get("length") == item["length"]
    return read_comment(bridge, address)["plate"] == item["value"]


def next_report(root: Path, stem: str) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    used = [int(m.group(1)) for p in out.glob(f"{stem}.apply-*.json") if (m := re.search(r"\.apply-(\d+)\.json$", p.name))]
    return out / f"{stem}.apply-{max(used, default=0) + 1:03d}.json"


def apply(root: Path, plan_path: Path, bridge, *, dry_run: bool, batch: int | None = None, only=frozenset(),
          check_every: int = CHECK_EVERY, today: str | None = None, image=None) -> dict:
    plan = load_plan(plan_path, root)
    if not dry_run:
        pending = names.unsaved(names.read_record(root))
        if pending:
            reports = sorted({row["state"].split(" ", 1)[1] for row in pending})
            raise Refused(f"{names.RECORD.as_posix()} holds {len(pending)} unsaved changes ({', '.join(reports)}): "
                          "save and --confirm-saved (or --discard-unsaved) first")
    check = names.preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    segments = read_segments(bridge, gb.RELEASE_PROGRAM)
    if [[hx(lo), hx(hi), n] for lo, hi, n in segments] != plan["segments"]:
        raise Refused("the release program's memory blocks differ from the plan's: replan")
    out = (root / OUT / f"{plan_path.stem}.dry-run.json") if dry_run else next_report(root, plan_path.stem)
    applier = Applier(bridge, plan, image, dry_run, batch, only, check_every, recorded=set(names.read_record(root)))
    stopped = kind = None
    try:
        applier.run()
    except (Stop, gb.BridgeError) as exc:
        stopped, kind = str(exc), type(exc).__name__
    finally:
        if not dry_run and applier.written:
            names.update_record(root, applier.written, today or _dt.date.today().isoformat(), out.name)
    result = {
        "plan": plan_path.name, "plan_sha256": plan["plan_sha256"], "selection": plan["selection"],
        "dry_run": dry_run, "stopped": stopped, "stop_kind": kind, "what_to_do": WHAT_TO_DO.get(kind) if kind else None,
        "saved": False, "batch": batch, "batch_full": applier.batch_full, "only": sorted(only),
        "entries_changed": applier.changed_entries, "checks": applier.checks,
        "sent": [] if dry_run else bridge.sent, "written": applier.written, "would_write": applier.would,
        "attempted": [] if dry_run else applier.attempted, "remove_by_hand": [],
        "counts": dict(sorted(Counter(w["applied"] for w in (applier.would if dry_run else applier.written)).items())),
        "unchanged": dict(sorted(applier.unchanged.items())), "skipped": applier.skipped,
        "analysis_changes": applier.analysis_changes, "differences_after_the_stop": applier.after_stop,
        "references_made": applier.references,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical(result), encoding="utf-8", newline="\n")
    result["report"] = out.name
    return result


def confirm_saved(root: Path, report_path: Path, bridge, today: str | None = None) -> dict:
    return names.confirm_saved(root, report_path, bridge, today, reads_back=reads_back)


def discard_unsaved(root: Path, report_path: Path, bridge) -> dict:
    """After closing without a save: refused while the program holds any write the report sent."""

    result = json.loads(report_path.read_text(encoding="utf-8"))
    present = [f"{i['address']} {i['applied']}" for i in result.get("attempted", []) if reads_back(bridge, i)]
    if present:
        raise Refused(f"{len(present)} writes of {report_path.name} are still in the program "
                      f"({', '.join(present[:10])}): save and --confirm-saved instead")
    rows = names.read_record(root)
    kept = {k: r for k, r in rows.items() if r["state"] != f"unsaved {report_path.name}"}
    names.write_record(root, kept)
    return {"discarded": len(rows) - len(kept), "report": report_path.name}


# --- command line ------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", nargs="?", const="", metavar="MODULE")
    mode.add_argument("--apply", type=Path, metavar="PLAN")
    mode.add_argument("--confirm-saved", type=Path, metavar="REPORT")
    mode.add_argument("--discard-unsaved", type=Path, metavar="REPORT")
    parser.add_argument("--all", action="store_true", help="with --plan: every committed pair")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--batch", type=int, metavar="N", help="with --apply: stop after N changed entries")
    parser.add_argument("--only", action="append", default=[], metavar="0xADDR",
                        help="with --apply: this entry only (repeatable), for a pilot")
    parser.add_argument("--check-every", type=int, default=CHECK_EVERY, metavar="N",
                        help="with --apply: entries between two snapshots (1 names the write exactly)")
    parser.add_argument("--url")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.plan is not None:
            if bool(args.plan) == args.all:
                parser.error("--plan takes either a module or --all")
            bridge = gb.Bridge(args.url, read_only=True)
            check = names.preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            plan = build_plan(root, bridge, args.plan or None, progress=lambda m: print(m, file=sys.stderr))
            path = write_plan(root, plan)
            print(json.dumps(plan["summary"], indent=1))
            print(f"wrote {path.relative_to(root).as_posix()} (plan sha256 {plan['plan_sha256']})")
            return 0
        if args.all:
            parser.error("--all goes with --plan")
        if args.confirm_saved or args.discard_unsaved:
            bridge = gb.Bridge(args.url, read_only=True)
            check = names.preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            done = (confirm_saved(root, args.confirm_saved.resolve(), bridge) if args.confirm_saved
                    else discard_unsaved(root, args.discard_unsaved.resolve(), bridge))
            print(json.dumps(done))
            return 0
        if args.dry_run == args.yes:
            print("refused: --apply needs exactly one of --dry-run and --yes", file=sys.stderr)
            return 2
        only = frozenset(hx(int(a, 16)) for a in args.only)
        bridge = gb.Bridge(args.url, read_only=args.dry_run, writes=gb.GLOBALS_WRITES)
        result = apply(root, args.apply.resolve(), bridge, dry_run=args.dry_run, batch=args.batch, only=only,
                       check_every=args.check_every)
        print(json.dumps({k: result[k] for k in ("report", "dry_run", "stopped", "stop_kind", "counts", "unchanged",
                                                 "batch_full", "entries_changed", "checks")}, indent=1))
        if result["what_to_do"]:
            print(f"what to do: {result['what_to_do']}")
        return 1 if result["stopped"] else 0
    except (Refused, gb.BridgeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
