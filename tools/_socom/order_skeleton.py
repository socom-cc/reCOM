"""Stage 5 phase B round 1: the skeleton generator's inputs (``order skeleton manifest``, read-only).

The manifest reads the 46 accepted segment order plans (each plan file must
have the SHA-256 its accepted item cites, and the plan's order target and stage
4 baseline must be current), the stage 3 semantic receipt (the cached closeout
receipt or a ``ghidra receipt --scope`` export: its function-index digest must
equal the stage 3 baseline's), the closeout fingerprint (data types and type
paths; its data digest must equal the baseline's), the source cache (artifacts,
relocations, DWARF header units), DWARF 1 (variable types, class keys and
bases) and every file under ``src/`` (``cxx_scan``; the stage 4 annotation
blocks are set aside with ``source_apply.parse_blocks``).  It writes nothing
under ``src/``.  Per planned row it records:

1. **signatures** (function rows): the mangled name and its ``mw_mangle``
   structured form; each scope component's kind (``namespace`` only where
   ``src`` declares that namespace, ``anonymous-namespace``, else ``class``);
   static or instance and the return type, each with its source (``stage3``:
   the receipt's prototype; ``rule``: constructors, destructors and vtable
   slots are instance members, constructors, destructors and conversions have
   no return type; ``provisional``: the declaration ``src`` already has, matched
   by its exact mangled name; ``unproven``: instance and ``void`` per BD1);
   ``const``; ``extern "C"`` for the C-linkage rows; the in-class declaration
   and the out-of-line definition head the skeleton writes.  **S1**: the
   definition head, parsed back by ``cxx_scan`` with the scope, typedef and
   class tables of ``src``, mangles to the ELF name exactly; every failure is
   reported with its reason.
2. **declarations** (per class the planned rows need): its existing body
   (path and lines) or the header a new body goes to (DWARF header unit, else a
   provisional forward declaration, else the enclosing class's body, else the
   unit directory's module header / unit header / a new ``<unit>_local.h``), its
   key, the members to add (BD2: additive), the in-class bodies of out-of-line
   rows, its virtuals in vtable-slot order (ELF vtable relocations; own, inherited,
   thunk and pure slots; new or override against the primary base's vtable), its
   bases (RTTI base list with offsets, direct or indirect; DWARF inheritance
   for access, or as the only source of a class without RTTI), its static data
   members; and per named type whether a full definition or a forward
   declaration is needed (by value or as a scope: full).
3. **bodies**: every provisional definition under ``src/`` (namespace-scope
   definitions in ``.cpp`` files, and in-class definitions in headers of rows
   planned out of line), mapped by exact mangled name (overloads included) to
   its row, with its action: ``move-in-place``, ``cross-file-move``,
   ``move-out-of-line``, ``bd4-holding`` (copy-only, unowned or emitting helper
   code: the module's unbuilt holding file), ``bd6-declarator-rewrite`` (a
   unique planned row of that scope and name the declarator contradicts),
   ``preamble`` (inline or template helpers that emit nothing) or ``judgment``.
   Per file: its unit (or orphan), the file-scope data definitions mapped to
   data rows, and its preamble content.  The frozen snapshot
   (``build/stage5/provisional-bodies.json``: path, line span, SHA-256 and text
   of every body) is written once and then only checked; ``--refresh-snapshot``
   replaces it.
4. **data** (data rows): type and source (DWARF variable record, stage 3 data
   type of the same size, provisional declaration of the same size, else an
   access-width type flagged ``unproven``: BD5), the initializer from the ELF
   bytes (relocated words as ``&symbol``, explicit zeros, none for nobits),
   ``const`` for ``.rodata``, ``static`` for LOCAL rows, the expected section and
   the owning function of a local static.

Rows that need judgment are listed (overload ties, signature contradictions,
by-value types ``src`` does not declare, copy-only and unowned bodies, S1
failures, ambiguous owners); the counts are given per segment.  The output is
deterministic; ``manifest_sha256`` is the SHA-256 of its canonical JSON without
that field.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import struct
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any

from .cxx_scan import (
    FileScan,
    Program,
    Speller,
    builtin_node,
    chain_of,
    data_symbols,
    declaration_text,
    definition_text,
    function_symbol,
    parse_head,
    scan_text,
)
from .mw_mangle import MangleError, mangle, mangle_qualified, parse_symbol
from .util import SocomError, canonical_json, load_json, sha256_file

MANIFEST_KIND = "socom-order-skeleton-manifest"
MANIFEST_SCHEMA = 1
SNAPSHOT_KIND = "socom-provisional-bodies"
SNAPSHOT_SCHEMA = 1
SNAPSHOT_PATH = "build/stage5/provisional-bodies.json"
RECEIPT_PATH = "build/closeout-ghidra-reconstruction/receipt-stage-2.json"
FINGERPRINT_PATH = "build/closeout-ghidra-reconstruction/fp-closeout.json"
VERIFIED_CACHE = "build/cache/skeleton-stage3-digests.json"
SOURCE_SUFFIXES = (".cpp", ".c", ".cc", ".h", ".hpp", ".inc")
CODE_SUFFIXES = (".cpp", ".c", ".cc")
# Where a signature piece comes from (BD1); constructors need no return type, free functions no member kind.
SIGNATURE_SOURCES = ("stage3", "rule", "provisional", "unproven", "not-needed", "not-applicable")
BODY_ACTIONS = ("move-in-place", "cross-file-move", "move-out-of-line", "bd4-holding", "bd6-declarator-rewrite", "preamble", "judgment")
DATA_TYPE_SOURCES = ("dwarf", "stage3", "provisional", "access-width", "unproven")
JUDGMENT_KINDS = (
    "s1-failure", "overload-tie", "signature-contradiction", "by-value-undeclared", "copy-only-body", "unowned-body",
    "ambiguous-owner", "unparsed-body", "local-static-owner",
)
# The order target's region labels and the section a definition there is emitted to.
REGION_SECTIONS = {
    ".data": ".data",
    ".rodata": ".rodata",
    ".sdata": ".sdata",
    ".bss": ".bss",
    "between .rodata and .sdata from __data_end": ".sdata",
    "between .sdata and .bss from _fbss": ".sbss",
}
_SHOWN = 12


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _hex(value: int) -> str:
    return f"0x{value:x}"


# -- inputs --------------------------------------------------------------------------------


def accepted_plans(root: Path, tracker: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(every segment plan, the link plan's record): accepted, at the SHA-256 the acceptance cites."""

    from .order_plan import ORDER_LINK_ID, ORDER_SEGMENT_KIND, order_plan_path

    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    items = sorted((row for row in tracker["work_items"] if row.get("kind") == ORDER_SEGMENT_KIND), key=lambda row: row["id"])
    link = next((row for row in tracker["work_items"] if row.get("id") == ORDER_LINK_ID), None)
    if not items:
        raise SocomError("stage 5 is not decomposed: no order-plan-segment item exists")
    link_record: dict[str, Any] = {}
    for item in items + ([link] if link else []):
        relative = order_plan_path(item["id"])
        if item.get("status") != "accepted":
            problems.append(f"{item['id']} is {item.get('status')}, not accepted")
            continue
        path = root / relative
        if not path.is_file():
            problems.append(f"{relative} does not exist")
            continue
        sha = sha256_file(path)
        if not any(sha in str(line) for line in item.get("evidence") or []):
            problems.append(f"{relative} (sha256 {sha[:12]}) is not the plan {item['id']} was accepted with")
            continue
        if item is link:
            link_record = {"item": item["id"], "path": relative, "sha256": sha}
        else:
            rows.append({"item": item["id"], "path": relative, "sha256": sha, "plan": load_json(path)})
    if problems:
        raise SocomError("the skeleton manifest reads accepted order plans only: " + "; ".join(problems[:_SHOWN]))
    return rows, link_record


def stage3_facts(root: Path, tracker: dict[str, Any], receipt_path: Path, fingerprint_path: Path) -> dict[str, Any]:
    """The stage 3 prototypes, data types and type paths, checked against the stage 3 baseline."""

    stage = next((row for row in tracker.get("stages") or [] if row.get("name") == "ghidra-reconstruction"), {})
    baseline = stage.get("baseline") or {}
    if stage.get("status") != "accepted" or not baseline.get("receipt_sha256"):
        raise SocomError("stage 3 (ghidra-reconstruction) has no accepted baseline")
    for path in (receipt_path, fingerprint_path):
        if not path.is_file():
            raise SocomError(f"{path.relative_to(root).as_posix() if path.is_relative_to(root) else path} does not exist "
                             "(the stage 3 closeout receipt and fingerprint, or a `ghidra receipt --scope` export)")
    receipt = load_json(receipt_path)
    body = receipt.get("receipt") if isinstance(receipt, dict) else None
    if not isinstance(body, dict) or body.get("kind") != "socom-ghidra-receipt":
        raise SocomError(f"{receipt_path.name} is not a socom-ghidra-receipt")
    # The content digests are costly over these files: a derived cache keyed by the files' SHA-256 keeps them.
    cache_path = root / VERIFIED_CACHE
    files = {"receipt_file_sha256": sha256_file(receipt_path), "fingerprint_file_sha256": sha256_file(fingerprint_path)}
    cached = load_json(cache_path) if cache_path.is_file() else {}
    fingerprint = load_json(fingerprint_path)
    if isinstance(cached, dict) and all(cached.get(key) == value for key, value in files.items()):
        computed, data_digest = cached.get("receipt_sha256"), cached.get("fingerprint_data_sha256")
    else:
        computed, data_digest = _digest(body), _digest(fingerprint.get("data"))
        from .util import atomic_write_json

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(cache_path, {**files, "receipt_sha256": computed, "fingerprint_data_sha256": data_digest})
    wanted = baseline["indexes"]["functions"]["sha256"]
    problems = []
    if computed != receipt.get("receipt_sha256"):
        problems.append(f"the receipt's content digest {computed[:12]} is not its receipt_sha256")
    if body["indexes"]["functions"]["sha256"] != wanted:
        problems.append(f"its function index {body['indexes']['functions']['sha256'][:12]} is not the stage 3 baseline's {wanted[:12]}")
    if data_digest != baseline["indexes"]["data"]["sha256"]:
        problems.append(f"the fingerprint's data index {data_digest[:12]} is not the stage 3 baseline's")
    if problems:
        raise SocomError("the stage 3 facts do not match the stage 3 baseline: " + "; ".join(problems))
    functions = {}
    for row in body["scoped_facts"]["functions"]:
        signature = next((line[11:] for line in row.get("details") or [] if line.startswith("Signature: ")), None)
        functions[int(row["address"], 16)] = (row["name"], signature)
    data: dict[int, tuple[str, int]] = {}
    for row in fingerprint["data"]:
        data.setdefault(int(row["address"], 16), (row["type"], row["size"]))
    types: dict[str, int | None] = {}
    for text in fingerprint.get("types") or []:
        path, _, size = text.rpartition("|")
        types[path] = int(size) if size.isdigit() else None
    return {
        "functions": functions,
        "data": data,
        "types": types,
        "record": {
            "receipt": receipt_path.relative_to(root).as_posix() if receipt_path.is_relative_to(root) else receipt_path.name,
            "receipt_sha256": computed,
            "receipt_is_baseline": computed == baseline["receipt_sha256"],
            "function_index_sha256": wanted,
            "fingerprint": fingerprint_path.relative_to(root).as_posix() if fingerprint_path.is_relative_to(root) else fingerprint_path.name,
            "fingerprint_data_sha256": data_digest,
        },
    }


def scan_sources(root: Path) -> tuple[list[FileScan], dict[str, dict[str, Any]]]:
    """Every source file under src/ (authored content only) and its block facts."""

    from .source_apply import parse_blocks

    scans: list[FileScan] = []
    files: dict[str, dict[str, Any]] = {}
    source = root / "src"
    if not source.is_dir():
        return scans, files
    for path in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            _bom, blocks, authored = parse_blocks(text)
            problem = None
        except SocomError as exc:
            blocks, authored, problem = {}, text.lstrip("\ufeff"), str(exc)
        scans.append(scan_text(relative, authored))
        files[relative] = {
            "blocks": sorted(blocks),
            "authored_sha256": hashlib.sha256(authored.encode("utf-8")).hexdigest(),
            "problem": problem,
        }
    return scans, files


def _named_chains(node: dict[str, Any], found: set[tuple[str, ...]]) -> None:
    kind = node.get("t")
    if kind == "named":
        found.add(chain_of(node["name"]))
        for component in node["name"]:
            for argument in component.get("args") or []:
                if argument.get("t") != "value":
                    _named_chains(argument, found)
    elif kind in ("pointer", "reference"):
        _named_chains(node["to"], found)
    elif kind == "array":
        _named_chains(node["of"], found)
    elif kind == "function":
        for param in node["params"]:
            _named_chains(param, found)
        _named_chains(node["ret"], found)
    elif kind == "member_pointer":
        found.add(chain_of(node["class"]))
        _named_chains(node["to"], found)


def symbol_chains(symbol: dict[str, Any]) -> set[tuple[str, ...]]:
    """The class and namespace chains a structured symbol proves exist."""

    found: set[tuple[str, ...]] = set()
    kind = symbol.get("kind")
    if kind in ("function", "data") and symbol.get("scope"):
        found.add(chain_of(symbol["scope"]))
        for component in symbol["scope"]:
            for argument in component.get("args") or []:
                if argument.get("t") != "value":
                    _named_chains(argument, found)
    if kind in ("vtable", "rtti"):
        found.add(chain_of(symbol["class"]))
    if kind == "function":
        for param in symbol["params"]:
            _named_chains(param, found)
        if "conversion" in symbol["name"]:
            _named_chains(symbol["name"]["conversion"], found)
    if kind == "thunk":
        found |= symbol_chains(symbol["target"])
    return found


class _Facts:
    """Graph artifacts, names and relocations (the source cache), and the ELF image."""

    def __init__(self, root: Path, cache: Path) -> None:
        from .elf import Elf32File

        self.elf = Elf32File(root / "support" / "socom.elf")
        main = self.elf.section("main")
        self.base = main.address
        self.image = self.elf.section_data("main")
        self.rows: dict[str, dict[str, Any]] = {}
        self.by_name: dict[str, list[str]] = defaultdict(list)
        self.refs_from: dict[str, list[tuple[int, int, str | None, str, str | None]]] = defaultdict(list)
        self.refs_to: dict[str, list[tuple[int, str | None, str]]] = defaultdict(list)
        self.headers: dict[tuple[str, ...], Counter] = defaultdict(Counter)
        with closing(sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True)) as connection:
            for identity, kind, address, size, name, binding, header in connection.execute(
                "SELECT id, kind, address, size, name, binding, emitted_from_header FROM artifacts WHERE kind != 'gap'"
            ):
                self.rows[identity] = {"id": identity, "kind": kind, "address": address, "size": size, "name": name,
                                       "binding": binding, "header": header, "names": []}
            for identity, name in connection.execute("SELECT artifact, name FROM names ORDER BY artifact, symbol_index"):
                if identity in self.rows:
                    self.rows[identity]["names"].append(name)
                    self.by_name[name].append(identity)
            for site, site_artifact, target, target_artifact, kind, symbol in connection.execute(
                "SELECT site, site_artifact, target, target_artifact, type, symbol FROM refs WHERE site_artifact IS NOT NULL"
            ):
                self.refs_from[site_artifact].append((site, target, target_artifact, kind, symbol))
                if target_artifact is not None:
                    self.refs_to[target_artifact].append((site, site_artifact, kind))
        for rows in self.refs_from.values():
            rows.sort()
        for row in self.rows.values():
            if row["kind"] != "function" or not row["header"]:
                continue
            for name in row["names"]:
                symbol = parse_symbol(name)
                if symbol["kind"] == "function" and symbol.get("scope"):
                    self.headers[chain_of(symbol["scope"])][row["header"]] += 1

    def word(self, address: int) -> int | None:
        offset = address - self.base
        if offset < 0 or offset + 4 > len(self.image):
            return None
        return int.from_bytes(self.image[offset : offset + 4], "little")

    def bytes_at(self, address: int, size: int) -> bytes | None:
        offset = address - self.base
        if offset < 0 or offset + size > len(self.image):
            return None
        return bytes(self.image[offset : offset + size])

    def artifact_of(self, name: str, kind: str | None = None) -> dict[str, Any] | None:
        for identity in self.by_name.get(name, []):
            row = self.rows[identity]
            if kind is None or row["kind"] == kind:
                return row
        return None


# -- DWARF ---------------------------------------------------------------------------------

_DWARF_FUND = {
    0x0001: ["char"], 0x0002: ["signed", "char"], 0x0003: ["unsigned", "char"], 0x0004: ["short"], 0x0005: ["short"],
    0x0006: ["unsigned", "short"], 0x0007: ["int"], 0x0008: ["int"], 0x0009: ["unsigned", "int"], 0x000A: ["long"],
    0x000B: ["long"], 0x000C: ["unsigned", "long"], 0x000E: ["float"], 0x000F: ["double"], 0x0010: ["long", "double"],
    0x0014: ["void"], 0x0015: ["bool"], 0x8008: ["long", "long"], 0x8208: ["unsigned", "long", "long"],
    0xA510: ["__int128"],
}
_DWARF_KEYS = {"class_type": "class", "structure_type": "struct", "union_type": "union"}


class _Dwarf:
    def __init__(self, elf: Any) -> None:
        from .dwarf1 import Dwarf1Debug
        from .import_plan import _parent_map

        dies = Dwarf1Debug(elf.section_data(".debug")).parse(strict=False)
        parents = _parent_map(dies)
        self.by_offset = {die.offset: die for die in dies}
        self.children: dict[int, list[Any]] = defaultdict(list)
        for die in dies:
            if die.offset in parents:
                self.children[parents[die.offset]].append(die)
        self.variables: dict[int, list[Any]] = defaultdict(list)
        self.composites: dict[str, list[Any]] = defaultdict(list)
        for die in dies:
            attribute = die.attribute("location")
            value = getattr(attribute, "value", None)
            if isinstance(value, bytes) and len(value) == 5 and value[0] == 0x03 and die.tag_name in (
                "global_variable", "local_variable", "variable", "member"
            ):
                self.variables[int.from_bytes(value[1:], "little")].append(die)
            if die.tag_name in ("class_type", "structure_type", "union_type", "enumeration_type"):
                name = die.string("name")
                if name and die.integer("byte_size"):
                    self.composites[name].append(die)

    def key(self, raw: str) -> str | None:
        keys = {_DWARF_KEYS[die.tag_name] for die in self.composites.get(raw, []) if die.tag_name in _DWARF_KEYS}
        return keys.pop() if len(keys) == 1 else None

    def bases(self, raw: str) -> list[dict[str, Any]] | None:
        """The inheritance records of every complete DIE spelled ``raw``, when they all agree."""

        from .type_identity import member_offset, type_ref

        shapes = set()
        for die in self.composites.get(raw, []):
            rows = []
            for child in self.children.get(die.offset, []):
                if child.tag_name != "inheritance":
                    continue
                ref = type_ref(child)
                target = self.by_offset.get(ref[1]) if ref and ref[1] is not None else None
                access = next((name for name in ("public", "protected", "private") if child.attribute(name) is not None), None)
                virtual = child.attribute("virtual") is not None
                rows.append((target.string("name") if target else None, member_offset(child), access, virtual))
            shapes.add(tuple(rows))
        if len(shapes) != 1:
            return None
        return [{"raw": base, "offset": offset, "access": access, "virtual": virtual} for base, offset, access, virtual in shapes.pop()]

    def type_node(self, ref: Any, qualify: Any) -> tuple[dict[str, Any] | None, str | None]:
        """(the node of a DWARF type reference, why not)."""

        from .type_identity import parse_subscr, type_ref

        modifiers, target, fund = ref
        if target is None:
            words = _DWARF_FUND.get(fund)
            if words is None:
                return None, f"fundamental type 0x{fund:x}"
            node: dict[str, Any] | None = builtin_node(words)
        else:
            die = self.by_offset.get(target)
            if die is None:
                return None, "missing DIE"
            if die.tag_name in ("class_type", "structure_type", "union_type", "enumeration_type"):
                raw = die.string("name")
                if not raw or raw.startswith("@"):
                    return None, "anonymous type"  # Metrowerks names unnamed classes @class
                node = {"t": "named", "name": qualify(raw)}
            elif die.tag_name == "array_type":
                subscript = die.attribute("subscr_data")
                dims, element = parse_subscr(subscript.value if subscript and isinstance(subscript.value, bytes) else b"")
                if element is None or any(len(dim) != 4 or not isinstance(dim[3], int) for dim in dims):
                    return None, "array extent"
                node, why = self.type_node(element, qualify)
                if node is None:
                    return None, why
                for dim in reversed(dims):
                    node = {"t": "array", "size": dim[3] - dim[2] + 1, "of": node}
            elif die.tag_name == "pointer_type":
                inner = type_ref(die)
                if inner is None:
                    return None, "pointer without a type"
                node, why = self.type_node(inner, qualify)
                if node is None:
                    return None, why
                node = {"t": "pointer", "to": node}
            else:
                return None, f"{die.tag_name} DIE"
        for modifier in reversed(modifiers):
            if modifier == 0x01:
                node = {"t": "pointer", "to": node}
            elif modifier == 0x02:
                node = {"t": "reference", "to": node}
            elif modifier in (0x03, 0x04):
                node = dict(node)
                letter = "C" if modifier == 0x03 else "V"
                node["cv"] = "".join(sorted(set(node.get("cv", "") + letter), key="CV".index))
            else:
                return None, f"modifier 0x{modifier:02x}"
        return node, None


# -- types: spelling Ghidra and DWARF types, sizes -----------------------------------------

_GHIDRA_BUILTINS = {
    "void": ["void"], "bool": ["bool"], "char": ["char"], "uchar": ["unsigned", "char"], "byte": ["unsigned", "char"],
    "schar": ["signed", "char"], "sbyte": ["signed", "char"], "short": ["short"], "ushort": ["unsigned", "short"],
    "word": ["unsigned", "short"], "int": ["int"], "uint": ["unsigned", "int"], "dword": ["unsigned", "int"],
    "long": ["long"], "ulong": ["unsigned", "long"], "longlong": ["long", "long"], "ulonglong": ["unsigned", "long", "long"],
    "qword": ["unsigned", "long", "long"], "float": ["float"], "double": ["double"], "longdouble": ["long", "double"],
    "wchar_t": ["wchar_t"], "uint16": ["__int128"], "int16": ["__int128"],
}
GHIDRA_POINTER = "pointer"  # Ghidra's built-in untyped pointer: void * (const char * for a string literal), never a class
_PROVISIONAL_CATEGORIES = ("unresolved", "anonymous")
_BUILTIN_SIZES = {"v": None, "b": 1, "c": 1, "s": 2, "i": 4, "l": 8, "x": 8, "f": 4, "d": 8, "r": 8, "w": 4, "1": 16, "e": None}


class _Types:
    """Qualified chains for bare type names, and type sizes (Ghidra paths, DWARF)."""

    def __init__(self, program: Program, paths: dict[str, int | None], dwarf: _Dwarf) -> None:
        self.program = program
        self.dwarf = dwarf
        self.by_leaf: dict[str, set[str]] = defaultdict(set)
        self.size_of_path = paths
        for path in paths:
            if "*" in path or "[" in path or "<" in path:
                continue
            self.by_leaf[path.rsplit("/", 1)[-1]].add(path)
        self.chains_by_leaf: dict[str, set[tuple[str, ...]]] = defaultdict(set)
        for chain, kinds in program.kinds.items():
            if kinds - {"namespace"}:
                self.chains_by_leaf[chain[-1]].add(chain)

    def qualify(self, raw: str) -> list[dict[str, Any]]:
        chains = {chain for chain in self.chains_by_leaf.get(raw, set()) if not self.program.is_namespace(chain)}
        chain = next(iter(chains)) if len(chains) == 1 else (raw,)
        return [_component(base) for base in chain]

    def ghidra_node(self, text: str) -> tuple[dict[str, Any] | None, str | None]:
        match = re.fullmatch(r"\s*(.+?)((?:\s*\*)*)\s*((?:\[\d+\])*)\s*", text or "")
        if not match:
            return None, f"unparsed Ghidra type {text!r}"
        base, stars, arrays = match.group(1).strip(), match.group(2).count("*"), [int(n) for n in re.findall(r"\d+", match.group(3))]
        if base.startswith("undefined"):
            return None, "undefined"
        if base in _GHIDRA_BUILTINS:
            node: dict[str, Any] = builtin_node(_GHIDRA_BUILTINS[base])
        elif base == GHIDRA_POINTER:
            node = {"t": "pointer", "to": builtin_node(["void"])}
        else:
            if not re.fullmatch(r"[A-Za-z_@$][\w@$]*", base):
                return None, f"Ghidra type {base!r} cannot be spelled"
            paths = sorted(self.by_leaf.get(base, set()))
            written = [path for path in paths if not any(f"/project/{word}" in path for word in _PROVISIONAL_CATEGORIES)]
            if paths and not written:
                return None, f"stage 3 names the provisional type {paths[0]}"
            project = [path for path in written if path.startswith("/project/")]
            if len(project) == 1:
                chain = tuple(project[0][len("/project/") :].split("/"))
                node = {"t": "named", "name": [_component(part) for part in chain]}
            else:
                node = {"t": "named", "name": self.qualify(base)}
        for _ in range(stars):
            node = {"t": "pointer", "to": node}
        for size in reversed(arrays):
            node = {"t": "array", "size": size, "of": node}
        return node, None

    def size(self, node: dict[str, Any] | None) -> int | None:
        if node is None:
            return None
        kind = node["t"]
        if kind == "builtin":
            return _BUILTIN_SIZES.get(node["code"])
        if kind in ("pointer", "reference"):
            return 4
        if kind == "member_pointer":
            return 12 if node["to"].get("t") == "function" else 4
        if kind == "array":
            inner = self.size(node["of"])
            return None if inner is None or node.get("size") is None else inner * node["size"]
        if kind == "named":
            chain = chain_of(node["name"])
            size = self.size_of_path.get("/project/" + "/".join(chain))
            if size:
                return size
            sizes = {die.integer("byte_size") for die in self.dwarf.composites.get(chain[-1], [])}
            return sizes.pop() if len(sizes) == 1 else None
        return None


def _component(base: str) -> dict[str, Any]:
    if base.startswith("@unnamed@") and base.endswith("@"):
        return {"unnamed": base[len("@unnamed@") : -1]}
    return {"name": base}


def _split_signature(name: str, signature: str | None) -> dict[str, Any] | None:
    """Ghidra's ``<ret> [<cc>] <name>(<params>)``: return text, parameters, default prototype or not."""

    if not signature:
        return None
    text = signature[9:] if signature.startswith("noreturn ") else signature
    index = text.rfind(name + "(")
    if index < 0:
        return None
    prefix = text[:index].strip()
    match = re.match(r"^(.*) (__\w+)$", prefix)
    convention = None
    if match:
        prefix, convention = match.group(1), match.group(2)
    inner = text[index + len(name) + 1 : -1]
    params: list[str] = []
    depth, start = 0, 0
    for position, char in enumerate(inner):
        if char in "<(":
            depth += 1
        elif char in ">)":
            depth -= 1
        elif char == "," and depth == 0:
            params.append(inner[start:position].strip())
            start = position + 1
    if inner[start:].strip() and inner.strip() != "void":
        params.append(inner[start:].strip())
    default = convention is None and prefix == "undefined" and not params
    hidden = [param for param in params if param.endswith(("__dtor_flags", "__ctor_flags")) or "__in_chrg" in param]
    this = bool(params) and params[0].endswith(" this")
    rest = [param for param in params[1 if this else 0 :] if param not in hidden]
    return {"returns": prefix, "default": default, "this": this, "params": rest}


# -- the manifest --------------------------------------------------------------------------


class _Builder:
    def __init__(self, root: Path, tracker: dict[str, Any], *, graph_path: Path, receipt_path: Path, fingerprint_path: Path) -> None:
        from .order_plan import order_context, stage4_baseline
        from .source_cache import ensure_source_cache
        from .source_emit_check import _Headers

        self.root = root
        self.plans, self.link = accepted_plans(root, tracker)
        self.target, _derived = order_context(root, tracker, graph_path, evidence=False)
        baseline = stage4_baseline(tracker)
        stale = [
            row["item"] for row in self.plans
            if row["plan"].get("inputs", {}).get("order_sha256") != self.target["order_sha256"]
            or row["plan"].get("inputs", {}).get("stage4_baseline_sha256") != baseline
        ]
        if stale:
            raise SocomError(
                f"{len(stale)} accepted order plans are stale against the current order target or stage 4 baseline "
                f"({', '.join(stale[:_SHOWN])}): reopen and re-draft them first"
            )
        self.stage3 = stage3_facts(root, tracker, receipt_path, fingerprint_path)
        cache, _rebuilt = ensure_source_cache(root, graph_path=graph_path)
        self.facts = _Facts(root, cache)
        self.dwarf = _Dwarf(self.facts.elf)
        self.scans, self.files = scan_sources(root)
        chains: set[tuple[str, ...]] = set()
        self.parsed: dict[str, dict[str, Any]] = {}
        for symbol in self.facts.elf.symbols():
            if symbol.name and symbol.name not in self.parsed:
                structured = parse_symbol(symbol.name)
                self.parsed[symbol.name] = structured
                chains |= symbol_chains(structured)
        self.program = Program(self.scans, chains)
        self.types = _Types(self.program, self.stage3["types"], self.dwarf)
        self.headers = _Headers(root, {})
        self.scan_by_path = {scan.path: scan for scan in self.scans}
        # Units: the plan rows, the order target's classes.
        self.units: dict[str, dict[str, Any]] = {}
        self.unit_of_path: dict[str, str] = {}
        self.segment_of_unit: dict[str, int] = {}
        for row in self.plans:
            for unit in row["plan"]["units"]:
                self.units[unit["unit"]] = unit
                self.unit_of_path[unit["workspace_path"]] = unit["unit"]
                self.segment_of_unit[unit["unit"]] = row["plan"]["segment_number"]
        self.entries: dict[str, dict[str, Any]] = {}
        self.owner: dict[str, str] = {}
        for unit in self.target["units"]:
            for section in unit["sections"]:
                for entry in section["artifacts"]:
                    self.entries[entry["artifact"]] = entry | {"unit": unit["unit"], "region": section["region"], "label": section["label"]}
                    self.owner[entry["artifact"]] = unit["unit"]
        self.function_rows: list[dict[str, Any]] = []
        self.data_rows: list[dict[str, Any]] = []
        for unit_name, unit in sorted(self.units.items(), key=lambda item: (self.segment_of_unit[item[0]], item[0])):
            for row in unit["functions"]:
                self.function_rows.append(row | {"unit": unit_name, "segment": self.segment_of_unit[unit_name]})
            for region in unit["data"]:
                for row in region["rows"]:
                    self.data_rows.append(
                        row | {"unit": unit_name, "segment": self.segment_of_unit[unit_name], "region": region["region"],
                               "label": region["label"]}
                    )
        self.planned_functions = {row["name"]: row for row in self.function_rows}
        self.rows_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.function_rows:
            self.rows_by_name[row["name"]].append(row)
        self.data_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.data_rows:
            self.data_by_name[row["name"]].append(row)
        self.vtable_targets: set[str] = set()
        for row in self.facts.rows.values():
            if row["kind"] == "data" and any(name.startswith("__vt__") for name in row["names"]):
                for _site, _target, target_artifact, kind, _symbol in self.facts.refs_from.get(row["id"], []):
                    if target_artifact and kind == "R_MIPS_32":
                        self.vtable_targets.add(target_artifact)
        # Provisional declarations of every function and data symbol, by mangled name.
        self.declared: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.class_members: dict[tuple[str, ...], set[str]] = defaultdict(set)
        self.inline_bodies: list[dict[str, Any]] = []
        # The return types of BD6 bodies: provisional evidence for the row their declarator contradicts.
        self.rewritten_returns: dict[str, tuple[dict[str, Any], str]] = {}
        self._index_declarations()

    # -- provisional declarations ---------------------------------------------------------

    def _index_declarations(self) -> None:
        for scan in self.scans:
            for klass in scan.classes:
                if not klass.chain or klass.template:
                    continue
                for member in klass.members:
                    if hasattr(member, "body_start"):
                        parsed = function_symbol(self.program, member.tokens, member.scope, scan.tag, klass=klass.chain)
                        if parsed.symbol is None:
                            continue
                        name = self._mangle(parsed.symbol)
                        if name:
                            self.class_members[klass.chain].add(name)
                            self.declared[name].append({"path": scan.path, "line": member.line, "parsed": parsed, "where": "class-body", "inline": True})
                            self.inline_bodies.append({"scan": scan, "definition": member, "mangled": name, "parsed": parsed})
                        continue
                    texts = [token.text for token in member.tokens]
                    if "(" in texts and not member.brace_init:
                        parsed = function_symbol(self.program, member.tokens, member.scope, scan.tag, klass=klass.chain)
                        if parsed.symbol is not None:
                            name = self._mangle(parsed.symbol)
                            if name:
                                self.class_members[klass.chain].add(name)
                                self.declared[name].append({"path": scan.path, "line": member.line, "parsed": parsed, "where": "class-body"})
                            continue
                    for parsed in data_symbols(self.program, member.tokens, member.scope, scan.tag):
                        if parsed.symbol is None or "static" not in parsed.specifiers:
                            continue
                        name = self._mangle(parsed.symbol)
                        if name:
                            self.class_members[klass.chain].add(name)
                            self.declared[name].append({"path": scan.path, "line": member.line, "parsed": parsed, "where": "class-body"})
            for row in scan.declarations:
                if row.in_class is not None:
                    continue
                for parsed in data_symbols(self.program, row.tokens, row.scope, scan.tag):
                    if parsed.error == "prototype":
                        symbol = function_symbol(self.program, row.tokens, row.scope, scan.tag)
                        name = self._mangle(symbol.symbol) if symbol.symbol else None
                        if name:
                            self.declared[name].append({"path": scan.path, "line": row.line, "parsed": symbol, "where": "prototype"})
                        break
                    if parsed.symbol is None:
                        continue
                    name = self._mangle(parsed.symbol)
                    if name:
                        self.declared[name].append(
                            {"path": scan.path, "line": row.line, "parsed": parsed, "where": "extern" if "extern" in parsed.specifiers else "definition"}
                        )

    @staticmethod
    def _mangle(symbol: dict[str, Any] | None) -> str | None:
        if symbol is None:
            return None
        try:
            return mangle(symbol)
        except (MangleError, KeyError, TypeError):
            return None

    # -- signatures -----------------------------------------------------------------------

    def scope_kinds(self, scope: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        chain = chain_of(scope)
        for index, component in enumerate(scope):
            prefix = chain[: index + 1]
            if "unnamed" in component:
                kind = "anonymous-namespace"
            elif "namespace" in self.program.kind_of(prefix):
                kind = "namespace"
            else:
                kind = "class"
            rows.append({"name": chain[index], "kind": kind})
        return rows

    def _site(self, symbol: dict[str, Any], unit: str) -> Speller:
        scope = symbol.get("scope") or []
        unnamed = scope[0]["unnamed"] if scope and "unnamed" in scope[0] else None
        site = [(f"@unnamed@{unnamed}@",), ()] if unnamed else [()]
        return Speller(self.program, site, inside_unnamed=unnamed)

    def signature(self, row: dict[str, Any]) -> dict[str, Any]:
        name = row["name"]
        unit = row["unit"]
        tag = PurePosixPath(self.units[unit]["workspace_path"]).name.replace(".", "_")
        structured = self.parsed.get(name) or parse_symbol(name)
        entry: dict[str, Any] = {
            "artifact": row["artifact"], "name": name, "unit": unit, "segment": row["segment"],
            "position": row.get("position"), "in_class": bool(row.get("in_class")), "structured": structured,
        }
        address = int(row["address"], 16)
        facts = self.stage3["functions"].get(address)
        prototype = _split_signature(facts[0], facts[1]) if facts else None
        if prototype and prototype["default"]:
            prototype = None
        provisional = [rec for rec in self.declared.get(name, []) if rec["parsed"].symbol is not None]
        if structured["kind"] == "c_name":
            entry["linkage"] = "C"
            entry["scope"] = []
            entry["member"] = {"kind": "free", "source": "not-applicable"}
            speller = self._site({"scope": None}, unit)
            returns, source = self._returns(prototype, provisional, structured, speller)
            params = prototype["params"] if prototype else None
            entry["return"] = {"text": returns, "source": source}
            entry["parameters"] = {"text": params, "source": "stage3" if prototype else "unproven"}
            spelled_params = []
            for text in _strip_names(params or []):
                node, _why = self.types.ghidra_node(text)
                spelled_params.append(speller.type(node) if node is not None else text)
            spelled = ", ".join(spelled_params) or "void"
            entry["definition"] = f'extern "C" {returns} {name}({spelled})'
            entry["declaration"] = None
            entry["namespace"] = None
            entry["const"] = False
            entry["virtual"] = False
            entry["s1"] = {"ok": True, "mangled": name, "check": "C linkage: the name is the declarator-id", "problems": []}
            if not prototype:
                entry["s1"]["problems"].append("parameters unproven (C names do not encode them)")
            return entry
        entry["linkage"] = "C++"
        if structured["kind"] != "function":
            entry["s1"] = {"ok": False, "mangled": None, "problems": [f"{structured['kind']} is not a function form"]}
            return entry
        scope = structured.get("scope") or []
        kinds = self.scope_kinds(scope)
        entry["scope"] = kinds
        special = structured["name"].get("text") if "text" in structured["name"] else "conversion"
        member_of_class = bool(kinds) and kinds[-1]["kind"] == "class"
        virtual = row["artifact"] in self.vtable_targets
        entry["virtual"] = virtual
        entry["const"] = "C" in structured.get("cv", "")
        if not member_of_class:
            member = {"kind": "free", "source": "not-applicable"}
        elif special in ("__ct", "__dt"):
            member = {"kind": "instance", "source": "rule", "basis": "constructor or destructor"}
        elif prototype and prototype["this"]:
            member = {"kind": "instance", "source": "stage3", "basis": "explicit this"}
        elif prototype and len(prototype["params"]) == len(_declared_params(structured)):
            member = {"kind": "static", "source": "stage3", "basis": "no this, parameters as mangled"}
        elif virtual:
            member = {"kind": "instance", "source": "rule", "basis": "a vtable slot"}
        else:
            found = next((rec for rec in provisional if rec["where"] == "class-body"), None)
            if found is not None:
                kind = "static" if "static" in found["parsed"].specifiers else "instance"
                member = {"kind": kind, "source": "provisional", "basis": f"{found['path']}:{found['line']}"}
            else:
                member = {"kind": "instance", "source": "unproven"}
        if virtual and member["kind"] == "static":
            member["conflict"] = "a vtable slot names a member stage 3 types as static"
        entry["member"] = member
        speller = self._site(structured, unit)
        if special in ("__ct", "__dt") or "conversion" in structured["name"]:
            returns, source = None, "not-needed"
        else:
            returns, source = self._returns(prototype, provisional, structured, speller)
        entry["return"] = {"text": returns, "source": source}
        static = member["kind"] == "static"
        entry["declaration"] = (
            declaration_text(self.program, structured, returns, static=static, virtual=virtual) if member_of_class else None
        )
        head, problems, namespace = definition_text(self.program, structured, returns, tag=tag)
        entry["definition"] = head
        entry["namespace"] = namespace
        back = parse_head(self.program, head, tag=tag, namespace=namespace)
        mangled = self._mangle(back.symbol)
        s1_problems = list(problems)
        if back.error:
            s1_problems.append(f"the declarator does not parse: {back.error}")
        if any("local" in component for component in scope):
            s1_problems.append("a function-local class: its members cannot be defined out of line")
        if structured["name"].get("text") == "__defctor":
            s1_problems.append("a compiler-generated default-argument constructor wrapper")
        entry["s1"] = {"ok": mangled == name and not s1_problems, "mangled": mangled, "problems": s1_problems}
        if mangled != name and not s1_problems:
            entry["s1"]["problems"].append(f"mangles to {mangled}")
        return entry

    def _returns(self, prototype: dict[str, Any] | None, provisional: list[dict[str, Any]], structured: dict[str, Any],
                 speller: Speller) -> tuple[str, str]:
        if prototype is not None:
            node, _why = self.types.ghidra_node(prototype["returns"])
            if node is not None:
                return speller.type(node), "stage3"
        nodes = [rec["parsed"].returns for rec in provisional]
        rewritten = self.rewritten_returns.get(mangle(structured)) if structured.get("kind") == "function" else None
        if rewritten is not None:
            nodes.append(rewritten[0])
        for node in nodes:
            if node is not None:
                try:
                    return speller.type(node), "provisional"
                except (MangleError, KeyError):
                    continue
        return "void", "unproven"

    # -- declarations ---------------------------------------------------------------------

    def classes(self, signatures: list[dict[str, Any]], data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        wanted: dict[tuple[str, ...], dict[str, Any]] = {}

        def want(scope: list[dict[str, Any]]) -> dict[str, Any]:
            chain = chain_of(scope)
            return wanted.setdefault(chain, {"components": scope, "members": [], "static_data": [], "units": Counter(), "vtable": None})

        for entry in signatures:
            kinds = entry.get("scope") or []
            if kinds and kinds[-1]["kind"] == "class":
                row = want(entry["structured"]["scope"])
                row["members"].append(entry)
                row["units"][entry["unit"]] += 1
        for entry in data:
            if entry.get("static_member"):
                row = want(entry["structured"]["scope"])
                row["static_data"].append(entry)
                row["units"][entry["unit"]] += 1
        for unit_name, unit in self.units.items():
            for row in unit["not_placed"]:
                symbol = self.parsed.get(row["name"]) or parse_symbol(row["name"])
                if symbol["kind"] == "vtable":
                    record = want(symbol["class"])
                    record["vtable"] = row
                    record["units"][unit_name] += 1
        # The units whose signatures or data name a class: a class one unit uses is local to it.
        self.type_units: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for entry in signatures:
            for chain in symbol_chains(entry["structured"]):
                self.type_units[chain].add(entry["unit"])
        for entry in data:
            found: set[tuple[str, ...]] = set()
            if entry["type"].get("node") is not None:
                _named_chains(entry["type"]["node"], found)
            for chain in found:
                self.type_units[chain].add(entry["unit"])
        result = []
        for chain in sorted(wanted, key=lambda value: "::".join(value)):
            result.append(self._class(chain, wanted[chain]))
        return result

    def _class(self, chain: tuple[str, ...], info: dict[str, Any]) -> dict[str, Any]:
        components = info["components"]
        readable = "::".join("(anonymous namespace)" if part.startswith("@unnamed@") else part for part in chain)
        defs = self.program.class_defs.get(chain, [])
        bodies = sorted(
            ({"path": path, "line": klass.line, "end_line": klass.end_line, "key": klass.key} for path, klass in defs),
            key=lambda row: (not row["path"].endswith((".h", ".hpp")), row["path"], row["line"]),
        )
        raw = chain[-1]
        record: dict[str, Any] = {"class": readable, "chain": list(chain), "mangled": mangle_qualified(components)}
        record["key"] = bodies[0]["key"] if bodies else (self.dwarf.key(raw) or "class")
        record["key_source"] = "src" if bodies else ("dwarf" if self.dwarf.key(raw) else "default")
        record["body"] = bodies[0] if bodies else None
        if len(bodies) > 1:
            record["other_bodies"] = bodies[1:]
        record["header"] = None if bodies else self._placement(chain, info)
        declared = self.class_members.get(chain, set())
        members = sorted(info["members"], key=lambda entry: (entry["unit"], entry["position"] or 0, entry["name"]))
        record["members_declared"] = sum(1 for entry in members if entry["name"] in declared)
        record["members_to_add"] = [
            {"artifact": entry["artifact"], "name": entry["name"], "unit": entry["unit"], "declaration": entry["declaration"],
             "member": entry["member"]["kind"], "member_source": entry["member"]["source"], "return_source": entry["return"]["source"]}
            for entry in members if entry["name"] not in declared
        ]
        planned_out_of_line = {entry["name"] for entry in members if not entry["in_class"]}
        record["in_class_bodies_to_move"] = sorted(
            ({"path": body["scan"].path, "line": body["definition"].line, "end_line": body["definition"].end_line, "name": body["mangled"]}
             for body in self.inline_bodies if body["mangled"] in planned_out_of_line and body["definition"].in_class == chain),
            key=lambda row: (row["path"], row["line"]),
        )
        record["static_data_members"] = [
            {"artifact": entry["artifact"], "name": entry["name"], "declared": entry["name"] in declared,
             "declaration": f"static {entry['declaration_type']};" if entry.get("declaration_type") else None,
             "type_source": entry["type"]["source"]}
            for entry in sorted(info["static_data"], key=lambda entry: entry["name"])
        ]
        record["vtable"] = self._vtable(chain, components)
        record["bases"] = self._bases(chain, components)
        record["units"] = dict(sorted(info["units"].items()))
        return record

    def _placement(self, chain: tuple[str, ...], info: dict[str, Any]) -> dict[str, Any]:
        if chain[0].startswith("@unnamed@"):
            tag = chain[0][len("@unnamed@") : -1]
            unit = next((name for name, unit in sorted(self.units.items()) if PurePosixPath(unit["workspace_path"]).name.replace(".", "_") == tag), None)
            path = self.units[unit]["workspace_path"] if unit else None
            return {"path": path, "how": "the anonymous namespace of its unit's source file", "exists": path is not None}
        counts = self.facts.headers.get(chain)
        if counts:
            header, _count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
            mapped = self.headers.workspace(header)
            if mapped.get("header"):
                return {"path": mapped["header"], "how": f"DWARF header unit ({mapped['how']})", "exists": mapped.get("exists"),
                        "dwarf_header": header}
        for scan in self.scans:
            if scan.path.endswith((".h", ".hpp")) and chain in scan.forwards:
                return {"path": scan.path, "how": "provisional forward declaration", "exists": True}
        if len(chain) > 1 and not self.program.is_namespace(chain[:-1]) and self.program.class_defs.get(chain[:-1]):
            path, klass = sorted(self.program.class_defs[chain[:-1]], key=lambda item: item[0])[0]
            return {"path": path, "how": f"inside the body of {'::'.join(chain[:-1])} (line {klass.line})", "exists": True}
        unit = sorted(info["units"].items(), key=lambda item: (-item[1], item[0]))[0][0] if info["units"] else None
        if unit is None:
            return {"path": None, "how": "no unit", "exists": False}
        users = set(info["units"]) | self.type_units.get(chain, set())
        directory = PurePosixPath(self.units[unit]["workspace_path"]).parent.as_posix()
        local = sorted(path for path in self.scan_by_path if PurePosixPath(path).parent.as_posix() == directory and path.endswith("_local.h"))
        if len(users) == 1 and len(local) == 1:
            return {"path": local[0], "how": "convention: its directory's _local.h (one unit uses the class)", "exists": True}
        module = self._module_header(directory)
        if module is not None:
            return {"path": module, "how": "convention: the header its directory's sources include most", "exists": True}
        name = PurePosixPath(directory).name.lower()
        return {"path": f"{directory}/{name}.h", "how": "convention: a new module header", "exists": False}

    def _module_header(self, directory: str) -> str | None:
        headers = {PurePosixPath(path).name: path for path in self.scan_by_path
                   if PurePosixPath(path).parent.as_posix() == directory and path.endswith((".h", ".hpp")) and not path.endswith("_local.h")}
        if not headers:
            return None
        counts: Counter = Counter()
        for scan in self.scans:
            if PurePosixPath(scan.path).parent.as_posix() == directory and scan.path.endswith(CODE_SUFFIXES):
                for included in set(scan.includes):
                    name = PurePosixPath(included).name
                    if name in headers:
                        counts[name] += 1
        best = sorted(headers, key=lambda name: (-counts[name], len(name), name))[0]
        return headers[best]

    def _vtable(self, chain: tuple[str, ...], components: list[dict[str, Any]]) -> dict[str, Any] | None:
        row = self.facts.artifact_of(f"__vt__{mangle_qualified(components)}", "data")
        if row is None:
            return None
        rtti = f"__RTTI__{mangle_qualified(components)}"
        relocations = {site - row["address"]: (target_artifact, symbol) for site, _t, target_artifact, kind, symbol in self.facts.refs_from.get(row["id"], [])
                       if kind == "R_MIPS_32"}
        slots = []
        group = -1
        offset = 0
        size = row["size"] or 0
        while offset + 4 <= size:
            target, symbol = relocations.get(offset, (None, None))
            if symbol == rtti or (offset == 0):
                group += 1
                delta = self.facts.word(row["address"] + offset + 4)
                slots.append({"group": group, "offset": offset, "kind": "rtti", "this_delta": None if delta is None else struct.unpack("<i", struct.pack("<I", delta))[0]})
                offset += 8
                continue
            names = self.facts.rows[target]["names"] if target in self.facts.rows else ([symbol] if symbol else [])
            name = next((value for value in names if parse_symbol(value)["kind"] in ("function", "thunk")), names[0] if names else None)
            slot: dict[str, Any] = {"group": group, "offset": offset, "target": name}
            if name is None:
                slot["kind"] = "null" if not self.facts.word(row["address"] + offset) else "unrelocated"
            else:
                symbol_form = parse_symbol(name)
                if symbol_form["kind"] == "thunk":
                    owner = chain_of(symbol_form["target"].get("scope") or [])
                    slot["kind"] = "thunk-own" if owner == chain else "thunk"
                    slot["member"] = mangle(symbol_form["target"])
                elif symbol_form["kind"] == "function":
                    owner = chain_of(symbol_form.get("scope") or [])
                    slot["kind"] = "own" if owner == chain else "inherited"
                    slot["member"] = name
                else:
                    slot["kind"] = "pure" if "pure" in name.lower() else "other"
            slots.append(slot)
            offset += 4
        primary = [slot for slot in slots if slot["group"] == 0 and slot["kind"] != "rtti"]
        base = self._primary_base(chain, components)
        inherited_slots = None
        if base is not None:
            base_table = self._vtable_size(base)
            inherited_slots = base_table
        declare = []
        seen = set()
        for slot in (slot for slot in slots if slot["kind"] in ("own", "thunk-own")):
            member = slot["member"]
            if member in seen:
                continue
            seen.add(member)
            position = primary.index(slot) if slot in primary else None
            new = position is not None and (inherited_slots is None or position >= inherited_slots)
            declare.append({"member": member, "slot": position, "group": slot["group"], "new": new})
        return {"artifact": row["id"], "name": f"__vt__{mangle_qualified(components)}", "size": size, "slots": slots,
                "primary_slots": len(primary), "base_slots": inherited_slots, "declare_virtual": declare}

    def _vtable_size(self, components: list[dict[str, Any]]) -> int | None:
        row = self.facts.artifact_of(f"__vt__{mangle_qualified(components)}", "data")
        if row is None:
            return None
        rtti = f"__RTTI__{mangle_qualified(components)}"
        count = 0
        for offset in range(8, row["size"] or 0, 4):
            symbol = next((symbol for site, _t, _a, kind, symbol in self.facts.refs_from.get(row["id"], []) if site - row["address"] == offset), None)
            if symbol == rtti:
                break
            count += 1
        return count

    def _rtti_bases(self, components: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        row = self.facts.artifact_of(f"__RTTI__{mangle_qualified(components)}", "data")
        if row is None:
            return None
        refs = {site - row["address"]: target_artifact for site, _t, target_artifact, kind, _s in self.facts.refs_from.get(row["id"], [])}
        table = self.facts.rows.get(refs.get(4)) if refs.get(4) else None
        if table is None:
            return []
        entries = {site - table["address"]: symbol for site, _t, _a, kind, symbol in self.facts.refs_from.get(table["id"], [])}
        bases = []
        for offset in range(0, (table["size"] or 0) - 4, 8):
            symbol = entries.get(offset)
            if symbol is None:
                break
            form = parse_symbol(symbol)
            delta = self.facts.word(table["address"] + offset + 4) or 0
            if form["kind"] != "rtti":
                break
            bases.append({"components": form["class"], "offset": struct.unpack("<i", struct.pack("<I", delta))[0]})
        return bases

    def _bases(self, chain: tuple[str, ...], components: list[dict[str, Any]]) -> dict[str, Any]:
        rtti = self._rtti_bases(components)
        dwarf = self.dwarf.bases(chain[-1])
        if rtti is not None:
            indirect: set[tuple[str, ...]] = set()
            for base in rtti:
                for inner in self._rtti_bases(base["components"]) or []:
                    indirect.add(chain_of(inner["components"]))
            rows = []
            for base in sorted(rtti, key=lambda row: row["offset"]):
                base_chain = chain_of(base["components"])
                access = next((row["access"] for row in dwarf or [] if row["raw"] == base_chain[-1]), None)
                rows.append({"class": "::".join(base_chain), "offset": base["offset"], "direct": base_chain not in indirect,
                             "access": access, "source": "rtti" + ("+dwarf" if access else "")})
            return {"source": "rtti", "bases": rows}
        if dwarf is not None:
            rows = [{"class": "::".join(chain_of(self.types.qualify(row["raw"]))) if row["raw"] else None, "offset": row["offset"],
                     "direct": True, "access": row["access"], "virtual": row["virtual"], "source": "dwarf"} for row in dwarf]
            return {"source": "dwarf" if self.dwarf.composites.get(chain[-1]) else "none", "bases": rows}
        return {"source": "unknown", "bases": [], "note": "no RTTI and no consistent DWARF record"}

    def _primary_base(self, chain: tuple[str, ...], components: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
        rtti = self._rtti_bases(components) or []
        direct = [row for row in rtti if row["offset"] == 0]
        if not direct:
            return None
        indirect = set()
        for base in direct:
            for inner in self._rtti_bases(base["components"]) or []:
                indirect.add(chain_of(inner["components"]))
        candidates = [row for row in direct if chain_of(row["components"]) not in indirect]
        return candidates[0]["components"] if candidates else None

    def type_needs(self, signatures: list[dict[str, Any]], data: list[dict[str, Any]], classes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        needs: dict[tuple[str, ...], dict[str, Any]] = {}

        def blank() -> dict[str, Any]:
            return {"uses": 0, "by_value": set(), "scope": False, "units": set()}

        def note(node: dict[str, Any], *, by_value: str | None, unit: str) -> None:
            kind = node.get("t")
            if kind == "named":
                row = needs.setdefault(chain_of(node["name"]), blank())
                row["uses"] += 1
                if by_value:
                    row["by_value"].add(by_value)
                row["units"].add(unit)
                for component in node["name"]:
                    for argument in component.get("args") or []:
                        if argument.get("t") != "value":
                            note(argument, by_value=None, unit=unit)
            elif kind in ("pointer", "reference"):
                note(node["to"], by_value=None, unit=unit)
            elif kind == "array":
                note(node["of"], by_value=by_value, unit=unit)
            elif kind == "function":
                for param in node["params"]:
                    note(param, by_value=None, unit=unit)
            elif kind == "member_pointer":
                note({"t": "named", "name": node["class"]}, by_value=None, unit=unit)

        for entry in signatures:
            structured = entry["structured"]
            if structured.get("kind") != "function":
                continue
            for param in structured["params"]:
                note(param, by_value="parameter", unit=entry["unit"])
            kinds = entry.get("scope") or []
            if kinds and kinds[-1]["kind"] == "class":
                row = needs.setdefault(chain_of(structured["scope"]), blank())
                row["scope"] = True
                row["units"].add(entry["unit"])
        for entry in data:
            if entry["type"].get("node") is not None:
                note(entry["type"]["node"], by_value="data", unit=entry["unit"])
        result = []
        for chain in sorted(needs, key=lambda value: "::".join(value)):
            row = needs[chain]
            kinds = self.program.kind_of(chain)
            if chain and chain[-1].startswith("@unnamed@"):
                continue
            if self.program.class_defs.get(chain):
                state = "class-body"
            elif "enum" in kinds:
                state = "enum"
            elif "typedef" in kinds:
                state = "typedef"
            elif "namespace" in kinds:
                state = "namespace"
            elif "forward" in kinds:
                state = "forward-only"
            else:
                state = "undeclared"
            dwarf = bool(self.dwarf.composites.get(chain[-1]))
            result.append({
                "type": "::".join(chain), "uses": row["uses"], "by_value": sorted(row["by_value"]), "as_scope": row["scope"],
                "src": state, "dwarf_record": dwarf, "need": "full" if row["by_value"] or row["scope"] else "forward",
                "units": sorted(row["units"]),
            })
        return result

    # -- bodies ---------------------------------------------------------------------------

    def bodies(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """(body rows, file rows, snapshot rows)."""

        bodies: list[dict[str, Any]] = []
        snapshot: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        candidates: list[tuple[FileScan, Any, Any, str]] = []
        for scan in self.scans:
            if scan.path.endswith(CODE_SUFFIXES):
                for definition in scan.definitions:
                    if definition.in_class is not None:
                        continue
                    parsed = function_symbol(self.program, definition.tokens, definition.scope, scan.tag)
                    candidates.append((scan, definition, parsed, "definition"))
        planned_out_of_line = {row["name"] for row in self.function_rows if not row.get("in_class")}
        for body in self.inline_bodies:
            if body["mangled"] in planned_out_of_line:
                candidates.append((body["scan"], body["definition"], body["parsed"], "in-class"))
        claimed: set[str] = set()
        records = []
        for scan, definition, parsed, kind in candidates:
            mangled = self._mangle(parsed.symbol)
            text = scan.text[definition.start : definition.end]
            record = {
                "id": f"{scan.path}:{definition.line}",
                "path": scan.path,
                "kind": kind,
                "span": {"start_line": definition.line, "end_line": definition.end_line},
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "declarator": " ".join(token.text for token in definition.tokens),
                "mangled": mangled,
                "template": definition.template,
                "inline": "inline" in parsed.specifiers,
                "static": "static" in parsed.specifiers,
            }
            if parsed.error and parsed.symbol is None:
                record["parse_error"] = parsed.error
            file_unit = self.unit_of_path.get(scan.path)
            record["file_unit"] = file_unit
            record["file_segment"] = self.segment_of_unit.get(file_unit) if file_unit else None
            snapshot.append({"id": record["id"], "path": scan.path, "span": record["span"], "sha256": record["sha256"], "text": text})
            records.append((record, parsed))
        # Pass 1: exact mangled names.
        for record, _parsed in records:
            mangled = record["mangled"]
            rows = self.rows_by_name.get(mangled or "", [])
            if not rows:
                continue
            own_unit = self.unit_of_path.get(record["path"])
            own = [row for row in rows if row["unit"] == own_unit]
            chosen = own[0] if own else rows[0] if len(rows) == 1 else None
            if chosen is None:
                record["action"] = "judgment"
                record["judgment"] = "ambiguous-owner"
                record["candidates"] = sorted(row["unit"] for row in rows)
                continue
            claimed.add(chosen["artifact"])
            record["row"] = {"artifact": chosen["artifact"], "unit": chosen["unit"], "segment": chosen["segment"]}
            recipient = self.units[chosen["unit"]]["workspace_path"]
            if record["kind"] == "in-class":
                record["action"] = "move-out-of-line"
                record["recipient"] = recipient
            elif recipient == record["path"]:
                record["action"] = "move-in-place"
            else:
                record["action"] = "cross-file-move"
                record["recipient"] = recipient
        # Pass 2: what the rest are.
        by_scope_name: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for row in self.function_rows:
            symbol = self.parsed.get(row["name"]) or parse_symbol(row["name"])
            if symbol["kind"] == "function":
                by_scope_name[(chain_of(symbol.get("scope") or []), _name_key(symbol))].append(row)
        for record, parsed in records:
            if "action" in record:
                continue
            mangled = record["mangled"]
            artifact = self.facts.artifact_of(mangled, "function") if mangled else None
            if parsed.symbol is None:
                record["action"] = "judgment"
                record["judgment"] = "unparsed-body"
                continue
            if artifact is not None:
                entry = self.entries.get(artifact["id"])
                if entry is not None and entry["class"] == "copy":
                    record["action"] = "bd4-holding"
                    record["reason"] = "copy-only"
                    record["judgment"] = "copy-only-body"
                else:
                    record["action"] = "bd4-holding"
                    record["reason"] = "unowned" if entry is None else f"owned by {entry['unit']} as {entry['class']}"
                    record["judgment"] = "unowned-body"
                record["artifact"] = artifact["id"]
                record["holding_file"] = holding_file(record["path"])
                continue
            symbol = parsed.symbol
            key = (chain_of(symbol.get("scope") or []), _name_key(symbol)) if symbol.get("kind") == "function" else None
            pool = [row for row in by_scope_name.get(key, []) if row["artifact"] not in claimed] if key else []
            own_unit = self.unit_of_path.get(record["path"])
            own = [row for row in pool if row["unit"] == own_unit]
            choice = own if own else pool
            if len(choice) == 1:
                row = choice[0]
                claimed.add(row["artifact"])
                record["action"] = "bd6-declarator-rewrite"
                record["judgment"] = "signature-contradiction"
                record["row"] = {"artifact": row["artifact"], "unit": row["unit"], "segment": row["segment"]}
                record["rewrite"] = {"from": record["declarator"], "to": row["name"]}
                if parsed.returns is not None:
                    self.rewritten_returns[row["name"]] = (parsed.returns, record["id"])
                recipient = self.units[row["unit"]]["workspace_path"]
                if recipient != record["path"]:
                    record["recipient"] = recipient
                continue
            if len(choice) > 1:
                record["action"] = "judgment"
                record["judgment"] = "overload-tie"
                record["candidates"] = sorted(row["name"] for row in choice)
                continue
            if record["inline"] or record["template"]:
                record["action"] = "preamble"
                record["reason"] = "no ELF function; inline or template code emits nothing on its own"
            else:
                record["action"] = "bd4-holding"
                record["reason"] = "no ELF function; the definition would emit one"
                record["holding_file"] = holding_file(record["path"])
        for record, _parsed in records:
            bodies.append(record)
        bodies.sort(key=lambda row: (row["path"], row["span"]["start_line"]))
        snapshot.sort(key=lambda row: (row["path"], row["span"]["start_line"]))
        by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in bodies:
            by_path[record["path"]].append(record)
        for scan in self.scans:
            if not scan.path.endswith(CODE_SUFFIXES):
                continue
            unit = self.unit_of_path.get(scan.path)
            data = self._file_data(scan)
            moving = [row for row in by_path.get(scan.path, []) if row["kind"] == "definition"]
            stays = [row for row in moving if row["action"] in ("move-in-place", "preamble")
                     or (row["action"] == "bd6-declarator-rewrite" and "recipient" not in row)]
            data_stays = [row for row in data if row.get("action") in ("in-place", "preamble")]
            files.append({
                "path": scan.path,
                "unit": unit,
                "orphan": unit is None,
                "blocks": self.files[scan.path]["blocks"],
                "authored_sha256": self.files[scan.path]["authored_sha256"],
                "definitions": len(moving),
                "actions": dict(sorted(Counter(row["action"] for row in moving).items())),
                "data_definitions": data,
                "preamble": {
                    "includes": scan.preprocessor.get("include", 0),
                    "defines": scan.preprocessor.get("define", 0),
                    "conditionals": scan.preprocessor.get("conditional", 0),
                    "pragmas": scan.preprocessor.get("pragma", 0),
                    "comment_lines": scan.comment_lines,
                    "class_bodies": sum(1 for klass in scan.classes if klass.chain),
                    "typedefs": len(scan.typedefs),
                    "declarations": sum(1 for row in scan.declarations if row.in_class is None) - len(data),
                },
                "empty_after_moves": unit is None and not stays and not data_stays,
                **({"problem": self.files[scan.path]["problem"]} if self.files[scan.path]["problem"] else {}),
            })
        return bodies, files, snapshot

    def _file_data(self, scan: FileScan) -> list[dict[str, Any]]:
        rows = []
        own_unit = self.unit_of_path.get(scan.path)
        for declaration in scan.declarations:
            if declaration.in_class is not None:
                continue
            for parsed in data_symbols(self.program, declaration.tokens, declaration.scope, scan.tag):
                if parsed.symbol is None or "extern" in parsed.specifiers or "typedef" in parsed.specifiers:
                    continue
                mangled = self._mangle(parsed.symbol)
                record: dict[str, Any] = {"line": declaration.line, "name": parsed.name, "mangled": mangled}
                planned = self.data_by_name.get(mangled or "", [])
                own = [row for row in planned if row["unit"] == own_unit]
                chosen = own[0] if own else planned[0] if len(planned) == 1 else None
                if chosen is not None:
                    record["artifact"] = chosen["artifact"]
                    record["unit"] = chosen["unit"]
                    record["action"] = "in-place" if chosen["unit"] == own_unit else "cross-file-move"
                elif planned:
                    record["action"] = "judgment"
                    record["candidates"] = sorted(row["unit"] for row in planned)
                elif mangled and self.facts.artifact_of(mangled, "data"):
                    record["action"] = "unowned"
                    record["artifact"] = self.facts.artifact_of(mangled, "data")["id"]
                else:
                    record["action"] = "preamble" if "const" in str(parsed.type) or "static" in parsed.specifiers else "no-elf-data"
                rows.append(record)
        return rows

    # -- data -----------------------------------------------------------------------------

    def datum(self, row: dict[str, Any]) -> dict[str, Any]:
        name = row["name"]
        address = int(row["address"], 16)
        entry_info = self.entries.get(row["artifact"], {})
        size = entry_info.get("size")
        if size is None:
            size = (self.facts.rows.get(row["artifact"]) or {}).get("size")
        binding = entry_info.get("binding") or (self.facts.rows.get(row["artifact"]) or {}).get("binding")
        structured = self.parsed.get(name) or parse_symbol(name)
        label = row["label"]
        region = next((region for region in self.target["regions"] if region["region"] == row["region"]), {})
        nobits = bool(region.get("nobits"))
        section = REGION_SECTIONS.get(label)
        entry: dict[str, Any] = {
            "artifact": row["artifact"], "name": name, "address": row["address"], "size": size, "unit": row["unit"],
            "segment": row["segment"], "region": row["region"], "label": label, "position": row.get("position"),
            "structured": structured, "binding": binding, "nobits": nobits,
            "section": section or label, "section_known": section is not None,
            "const": label == ".rodata",
        }
        kind = structured["kind"]
        entry["static_member"] = False
        if kind == "data":
            kinds = self.scope_kinds(structured["scope"])
            entry["scope"] = kinds
            entry["static_member"] = kinds[-1]["kind"] == "class"
        elif kind in ("local_static", "local_static_guard"):
            entry["scope"] = []
            entry["owner_function"] = self._owner_function(row)
        else:
            entry["scope"] = []
        entry["storage"] = "static" if binding == "LOCAL" and not entry["static_member"] and kind not in ("local_static", "local_static_guard") else (
            "local-static" if kind in ("local_static", "local_static_guard") else "external")
        entry["type"] = self._data_type(row, address, size, structured, entry)
        if entry["type"].get("generic_pointer") and not nobits:
            # Ghidra's untyped pointer at a string literal is a const char * (anything else stays void *).
            relocations = self._initializer(address, size, nobits, entry["type"]["node"]).get("relocations") or []
            if any("literal" in relocation and relocation["offset"] == 0 for relocation in relocations):
                entry["type"]["node"] = {"t": "pointer", "to": {**builtin_node(["char"]), "cv": "C"}}
                entry["type"]["generic_pointer"] = "const char * (it points at a string literal)"
        node = entry["type"].get("node")
        variable = structured["variable"] if kind in ("local_static", "local_static_guard") else (
            structured["name"]["text"] if kind == "data" else structured.get("name", name))
        if node is not None:
            speller = Speller(self.program, [()])
            try:
                text = speller.type(node, variable)
            except (MangleError, KeyError):
                text = None
            entry["type"]["text"] = text
            if entry["const"] and text and not text.startswith("const "):
                entry["type"]["const_text"] = "const " + text
            entry["declaration_type"] = text
        entry["initializer"] = self._initializer(address, size, nobits, node)
        return entry

    def _owner_function(self, row: dict[str, Any]) -> dict[str, Any]:
        users = sorted({site for _s, site, _k in self.facts.refs_to.get(row["artifact"], []) if site and site.startswith("socom:function:")})
        in_unit = [site for site in users if self.owner.get(site) == row["unit"] and self.entries.get(site, {}).get("class") == "definition"]
        if len(in_unit) == 1:
            names = (self.facts.rows.get(in_unit[0]) or {}).get("names") or []
            return {"artifact": in_unit[0], "name": names[0] if names else None, "basis": "the only defining function of the unit that references it"}
        return {"artifact": None, "candidates": in_unit or users[:_SHOWN], "basis": "several functions" if in_unit else "no defining function of the unit references it"}

    def _data_type(self, row: dict[str, Any], address: int, size: int | None, structured: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        from .type_identity import type_ref

        for die in self.dwarf.variables.get(address, []):
            ref = type_ref(die)
            if ref is None:
                continue
            node, why = self.dwarf.type_node(ref, self.types.qualify)
            if node is not None:
                found = self.types.size(node)
                if found is None or size is None or found == size:
                    return {"source": "dwarf", "node": node, "basis": f"DIE 0x{die.offset:x}", **({"size_checked": False} if found is None else {})}
        ghidra = self.stage3["data"].get(address)
        if ghidra and (size is None or ghidra[1] == size):
            node, _why = self.types.ghidra_node(ghidra[0])
            if node is not None and self.types.size(node) in (None, size):
                found = {"source": "stage3", "node": node, "basis": ghidra[0]}
                if re.fullmatch(rf"\s*{GHIDRA_POINTER}\s*", ghidra[0]):
                    found["generic_pointer"] = "void *"
                return found
        for record in self.declared.get(row["name"], []):
            node = record["parsed"].type
            if node is None or record["parsed"].error:
                continue
            if self.types.size(node) == size:
                return {"source": "provisional", "node": node, "basis": f"{record['path']}:{record['line']}"}
        return self._access_width(row, address, size)

    _ACCESS = {
        0x20: (1, "S"), 0x24: (1, "U"), 0x28: (1, None), 0x21: (2, "S"), 0x25: (2, "U"), 0x29: (2, None),
        0x23: (4, "S"), 0x27: (4, "U"), 0x2B: (4, None), 0x31: (4, "F"), 0x39: (4, "F"), 0x37: (8, None),
        0x3F: (8, None), 0x1E: (16, None), 0x1F: (16, None),
    }

    def _access_width(self, row: dict[str, Any], address: int, size: int | None) -> dict[str, Any]:
        widths: Counter = Counter()
        for site, _site_artifact, kind in self.facts.refs_to.get(row["artifact"], []):
            if kind not in ("R_MIPS_LO16", "R_MIPS_GPREL16"):
                continue
            word = self.facts.word(site)
            if word is None:
                continue
            found = self._ACCESS.get(word >> 26)
            if found is None:
                continue
            widths[found] += 1
        if not size:
            return {"source": "unproven", "node": None, "basis": "no size"}
        sized = {width for (width, _sign) in widths}
        if len(sized) == 1:
            width = sized.pop()
            signs = {sign for (w, sign) in widths if w == width}
            if size % width == 0:
                if "F" in signs and width == 4:
                    node: dict[str, Any] = {"t": "builtin", "code": "f"}
                else:
                    code = {1: "c", 2: "s", 4: "i", 8: "l", 16: "1"}[width]
                    node = {"t": "builtin", "code": code}
                    if code != "1" and ("U" in signs or (code == "c" and "S" not in signs)):
                        node["sign"] = "U"
                    elif code == "c":
                        node["sign"] = "S"
                if size > width:
                    node = {"t": "array", "size": size // width, "of": node}
                return {"source": "access-width", "node": node, "basis": f"{sum(widths.values())} direct accesses of {width} bytes", "unproven": True}
        node = {"t": "builtin", "code": "c", "sign": "U"}
        if size > 1:
            node = {"t": "array", "size": size, "of": node}
        basis = "no direct access" if not widths else f"mixed access widths {sorted(sized)}"
        return {"source": "unproven", "node": node, "basis": f"{basis}: a byte array of its size", "unproven": True}

    def _initializer(self, address: int, size: int | None, nobits: bool, node: dict[str, Any] | None) -> dict[str, Any]:
        if nobits:
            return {"kind": "none"}
        if not size:
            return {"kind": "unknown", "basis": "no size"}
        data = self.facts.bytes_at(address, size)
        if data is None:
            return {"kind": "unknown", "basis": "outside the image"}
        relocations = []
        artifact = next(iter(self._data_index().get(address, [])), None)
        for site, target, target_artifact, kind, symbol in self.facts.refs_from.get(artifact or "", []):
            if not address <= site < address + size:
                continue
            target_row = self.facts.rows.get(target_artifact) if target_artifact else None
            name = (target_row["names"][0] if target_row and target_row["names"] else None) or symbol
            addend = target - target_row["address"] if target_row and target is not None and target_row.get("address") is not None else 0
            relocation = {"offset": site - address, "type": kind, "target": name, "addend": addend}
            if name and name.startswith("@") and target_row and target_row.get("size"):
                text = self.facts.bytes_at(target_row["address"], target_row["size"]) or b""
                if text.endswith(b"\x00") and all(32 <= byte < 127 or byte in (9, 10, 13) for byte in text[:-1]):
                    relocation["literal"] = text[:-1].decode("ascii")
            relocations.append(relocation)
        if not any(data) and not relocations:
            return {"kind": "zero", "explicit": True, "rendered": "{0}" if size > 8 or (node or {}).get("t") == "array" else "0"}
        result: dict[str, Any] = {"kind": "bytes", "hex": data.hex(), "relocations": relocations}
        rendered = self._render(data, relocations, node)
        if rendered is not None:
            result["rendered"] = rendered
        return result

    def _data_index(self) -> dict[int, list[str]]:
        if not hasattr(self, "_data_at"):
            index: dict[int, list[str]] = defaultdict(list)
            for row in self.facts.rows.values():
                if row["kind"] == "data" and row["address"] is not None:
                    index[row["address"]].append(row["id"])
            self._data_at = index
        return self._data_at

    def _render(self, data: bytes, relocations: list[dict[str, Any]], node: dict[str, Any] | None) -> str | None:
        """A C initializer for scalar and array-of-scalar types; None when the type needs a layout."""

        if node is None:
            return None
        element = node
        count = None
        if node["t"] == "array":
            element, count = node["of"], node["size"]
            if element["t"] == "array":
                return None
        width = self.types.size(element)
        if width is None or width * (count or 1) != len(data):
            return None
        by_offset = {row["offset"]: row for row in relocations}
        values = []
        for index in range(count or 1):
            chunk = data[index * width : (index + 1) * width]
            relocation = by_offset.get(index * width)
            if element["t"] == "pointer":
                if relocation is not None:
                    if "literal" in relocation:
                        values.append(_c_string(relocation["literal"]))
                    elif relocation["target"] and not relocation["target"].startswith("@"):
                        values.append(f"&{relocation['target']}" + (f" + {relocation['addend']}" if relocation["addend"] else ""))
                    else:
                        return None
                elif not any(chunk):
                    values.append("0")
                else:
                    return None
            elif element["t"] == "builtin" and relocation is None:
                code = element["code"]
                if code == "f":
                    values.append(_float_text(struct.unpack("<f", chunk)[0]))
                elif code == "d":
                    values.append(repr(struct.unpack("<d", chunk)[0]))
                elif code in ("c", "s", "i", "l", "x", "b", "w"):
                    signed = element.get("sign") != "U" and code != "b"
                    values.append(str(int.from_bytes(chunk, "little", signed=signed)))
                else:
                    return None
            else:
                return None
        return values[0] if count is None else "{" + ", ".join(values) + "}"


def _c_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r") + '"'


def _float_text(value: float) -> str:
    text = repr(value)
    if text in ("nan", "inf", "-inf"):
        return text
    return (text if ("." in text or "e" in text) else text + ".0") + "f"


def _declared_params(structured: dict[str, Any]) -> list[dict[str, Any]]:
    params = structured.get("params") or []
    return [] if params == [{"t": "builtin", "code": "v"}] else params


def _name_key(symbol: dict[str, Any]) -> str:
    name = symbol["name"]
    return "@conversion" if "conversion" in name else name["text"]


def _strip_names(params: list[str]) -> list[str]:
    """Ghidra parameter declarations without their names (``int argc`` -> ``int``)."""

    out = []
    for param in params:
        text = re.sub(r"\s*\b[A-Za-z_]\w*$", "", param.strip())
        out.append(text or param)
    return out


def holding_file(path: str) -> str:
    """The unbuilt per-module holding file BD4 moves a body to."""

    directory = PurePosixPath(path).parent
    return f"{directory.as_posix()}/{directory.name.lower()}_holding.cpp"


# -- judgment, counts, assembly ------------------------------------------------------------


def _judgments(signatures: list[dict[str, Any]], bodies: list[dict[str, Any]], types: list[dict[str, Any]],
               data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entry in signatures:
        if not entry["s1"]["ok"]:
            rows.append({"kind": "s1-failure", "artifact": entry["artifact"], "name": entry["name"], "unit": entry["unit"],
                         "segment": entry["segment"], "detail": "; ".join(entry["s1"]["problems"])})
    for body in bodies:
        if body.get("judgment"):
            detail = body.get("reason") or (", ".join(body.get("candidates") or []) or body.get("rewrite", {}).get("to") or body.get("parse_error") or "")
            row = body.get("row") or {}
            rows.append({"kind": body["judgment"], "body": body["id"], "name": body["mangled"],
                         "unit": row.get("unit") or body.get("file_unit"),
                         "segment": row.get("segment") or body.get("file_segment"), "detail": detail})
    for row in types:
        if row["by_value"] and row["src"] in ("undeclared", "forward-only"):
            rows.append({"kind": "by-value-undeclared", "type": row["type"], "units": row["units"],
                         "detail": f"by value as {' and '.join(row['by_value'])}; src: {row['src']}; DWARF record: {row['dwarf_record']}"})
    for entry in data:
        owner = entry.get("owner_function")
        if owner is not None and owner.get("artifact") is None:
            rows.append({"kind": "local-static-owner", "artifact": entry["artifact"], "name": entry["name"], "unit": entry["unit"],
                         "segment": entry["segment"], "detail": owner["basis"]})
    order = {kind: index for index, kind in enumerate(JUDGMENT_KINDS)}
    rows.sort(key=lambda row: (order.get(row["kind"], 99), str(row.get("segment") or ""), str(row.get("name") or row.get("type") or "")))
    return rows


def _segment_counts(signatures: list[dict[str, Any]], data: list[dict[str, Any]], bodies: list[dict[str, Any]],
                    classes: list[dict[str, Any]], judgments: list[dict[str, Any]], segment_of_unit: dict[str, int]) -> list[dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}

    def row(number: int) -> dict[str, Any]:
        return rows.setdefault(number, {
            "segment": number, "units": set(), "functions": 0, "s1_ok": 0, "s1_failed": 0, "member": Counter(), "return": Counter(),
            "data": 0, "data_type": Counter(), "bodies": Counter(), "members_to_add": 0, "judgment": 0,
        })

    for entry in signatures:
        record = row(entry["segment"])
        record["units"].add(entry["unit"])
        record["functions"] += 1
        record["s1_ok" if entry["s1"]["ok"] else "s1_failed"] += 1
        record["member"][entry.get("member", {}).get("source", "unproven")] += 1
        record["return"][entry.get("return", {}).get("source", "unproven")] += 1
    for entry in data:
        record = row(entry["segment"])
        record["units"].add(entry["unit"])
        record["data"] += 1
        record["data_type"][entry["type"]["source"]] += 1
    for body in bodies:
        unit = (body.get("row") or {}).get("unit")
        number = segment_of_unit.get(unit) if unit else None
        if number is not None:
            row(number)["bodies"][body["action"]] += 1
    for klass in classes:
        for member in klass["members_to_add"]:
            number = segment_of_unit.get(member["unit"])
            if number is not None:
                row(number)["members_to_add"] += 1
    for judgment in judgments:
        if judgment.get("segment") is not None:
            row(judgment["segment"])["judgment"] += 1
    result = []
    for number in sorted(rows):
        record = rows[number]
        record["units"] = len(record["units"])
        for key in ("member", "return", "data_type", "bodies"):
            record[key] = dict(sorted(record[key].items()))
        result.append(record)
    return result


def _snapshot(rows: list[dict[str, Any]], files: dict[str, dict[str, Any]]) -> dict[str, Any]:
    body = {
        "kind": SNAPSHOT_KIND,
        "schema_version": SNAPSHOT_SCHEMA,
        "coordinates": "lines of each file's authored content (source_apply.parse_blocks: the stage 4 blocks removed), newlines as LF",
        "src_sha256": _digest(sorted((path, row["authored_sha256"]) for path, row in files.items())),
        "bodies": rows,
    }
    body["snapshot_sha256"] = _digest({key: value for key, value in body.items() if key != "snapshot_sha256"})
    return body


def _compare_snapshot(stored: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    old = {row["id"]: row["sha256"] for row in stored.get("bodies") or []}
    new = {row["id"]: row["sha256"] for row in fresh["bodies"]}
    return {
        "missing": sorted(set(old) - set(new))[:_SHOWN],
        "added": sorted(set(new) - set(old))[:_SHOWN],
        "changed": sorted(key for key in set(old) & set(new) if old[key] != new[key])[:_SHOWN],
        "missing_count": len(set(old) - set(new)),
        "added_count": len(set(new) - set(old)),
        "changed_count": sum(1 for key in set(old) & set(new) if old[key] != new[key]),
    }


def build_manifest(
    root: Path,
    tracker: dict[str, Any],
    *,
    graph_path: Path,
    receipt_path: Path | None = None,
    fingerprint_path: Path | None = None,
    segment: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(the skeleton manifest, the fresh provisional-body snapshot)."""

    builder = _Builder(
        root, tracker, graph_path=graph_path, receipt_path=receipt_path or root / RECEIPT_PATH,
        fingerprint_path=fingerprint_path or root / FINGERPRINT_PATH,
    )
    if segment is not None and segment not in set(builder.segment_of_unit.values()):
        raise SocomError(f"segment {segment} has no accepted order plan")
    bodies_all, files_all, snapshot_rows = builder.bodies()
    signatures_all = [builder.signature(row) for row in builder.function_rows]
    data_all = [builder.datum(row) for row in builder.data_rows]
    classes_all = builder.classes(signatures_all, data_all)
    types_all = builder.type_needs(signatures_all, data_all, classes_all)
    written = {row["name"]: row.get("definition") for row in signatures_all}
    for body in bodies_all:
        if "rewrite" in body:
            body["rewrite"]["declarator"] = written.get(body["rewrite"]["to"])
    judgments_all = _judgments(signatures_all, bodies_all, types_all, data_all)
    if segment is None:
        signatures, data, classes, types, bodies, files, judgments = (
            signatures_all, data_all, classes_all, types_all, bodies_all, files_all, judgments_all)
    else:
        units = {unit for unit, number in builder.segment_of_unit.items() if number == segment}
        paths = {builder.units[unit]["workspace_path"] for unit in units}
        signatures = [row for row in signatures_all if row["segment"] == segment]
        data = [row for row in data_all if row["segment"] == segment]
        classes = [row for row in classes_all if set(row["units"]) & units]
        types = [row for row in types_all if set(row["units"]) & units]
        bodies = [row for row in bodies_all if row["path"] in paths or (row.get("row") or {}).get("unit") in units]
        files = [row for row in files_all if row["path"] in paths]
        judgments = [row for row in judgments_all if row.get("segment") == segment or set(row.get("units") or []) & units]
    for entry in data:
        entry["type"] = {key: value for key, value in entry["type"].items() if key != "node"}
    selected_units = set(builder.segment_of_unit) if segment is None else {
        unit for unit, number in builder.segment_of_unit.items() if number == segment
    }
    snapshot = _snapshot(snapshot_rows, builder.files)
    s1 = {
        "checked": len(signatures),
        "ok": sum(1 for row in signatures if row["s1"]["ok"]),
        "failed": sum(1 for row in signatures if not row["s1"]["ok"]),
        "failures": [{"name": row["name"], "unit": row["unit"], "problems": row["s1"]["problems"]} for row in signatures if not row["s1"]["ok"]],
    }
    manifest: dict[str, Any] = {
        "kind": MANIFEST_KIND,
        "schema_version": MANIFEST_SCHEMA,
        "selection": {"segment": segment} if segment is not None else {"all": True},
        "inputs": {
            "plans": [{"item": row["item"], "sha256": row["sha256"]} for row in builder.plans],
            "link_plan": builder.link,
            "order_sha256": builder.target["order_sha256"],
            "stage3": builder.stage3["record"],
            "graph_sha256": builder.target["inputs"].get("graph_sha256"),
            "src_sha256": snapshot["src_sha256"],
            "snapshot_sha256": snapshot["snapshot_sha256"],
        },
        "summary": {
            "segments": len({row["segment"] for row in signatures} | {row["segment"] for row in data}),
            "units": len({row["unit"] for row in signatures} | {row["unit"] for row in data}),
            "functions": len(signatures),
            "data": len(data),
            "classes": len(classes),
            "classes_with_body": sum(1 for row in classes if row["body"]),
            "classes_new_body": sum(1 for row in classes if not row["body"]),
            "members_to_add": sum(1 for row in classes for member in row["members_to_add"] if member["unit"] in selected_units),
            "static_data_members": sum(len(row["static_data_members"]) for row in classes),
            "virtual_declarations": sum(len((row["vtable"] or {}).get("declare_virtual") or []) for row in classes),
            "member_kind": dict(sorted(Counter(row["member"]["source"] for row in signatures if "member" in row).items())),
            "return_type": dict(sorted(Counter(row["return"]["source"] for row in signatures if "return" in row).items())),
            "data_type": dict(sorted(Counter(row["type"]["source"] for row in data).items())),
            "initializers": dict(sorted(Counter(row["initializer"]["kind"] for row in data).items())),
            "bodies": len(bodies),
            "body_actions": dict(sorted(Counter(row["action"] for row in bodies).items())),
            "orphan_files": sum(1 for row in files if row["orphan"]),
            "orphan_files_empty_after_moves": sum(1 for row in files if row["orphan"] and row["empty_after_moves"]),
            "types_needed": dict(sorted(Counter(f"{row['need']}:{row['src']}" for row in types).items())),
            "judgment": dict(sorted(Counter(row["kind"] for row in judgments).items())),
        },
        "s1": s1,
        "segments": [row for row in _segment_counts(signatures, data, bodies, classes, judgments, builder.segment_of_unit)
                     if segment is None or row["segment"] == segment],
        "judgment": judgments,
        "signatures": signatures,
        "declarations": {"classes": classes, "types": types},
        "bodies": {"definitions": bodies, "files": files, "holding_files": sorted({row["holding_file"] for row in bodies if row.get("holding_file")})},
        "data": data,
    }
    manifest["manifest_sha256"] = _digest(manifest)
    return manifest, snapshot


def settle_snapshot(path: Path, fresh: dict[str, Any], *, refresh: bool) -> dict[str, Any]:
    """Write the snapshot once; afterwards only compare (``refresh`` replaces it)."""

    from .util import atomic_write_json

    if path.is_file() and not refresh:
        stored = load_json(path)
        if isinstance(stored, dict) and stored.get("snapshot_sha256") == fresh["snapshot_sha256"]:
            return {"status": "current", "snapshot_sha256": fresh["snapshot_sha256"]}
        return {"status": "stale", "stored_sha256": (stored or {}).get("snapshot_sha256"), "fresh_sha256": fresh["snapshot_sha256"],
                **_compare_snapshot(stored if isinstance(stored, dict) else {}, fresh)}
    atomic_write_json(path, fresh)
    return {"status": "refreshed" if refresh else "written", "snapshot_sha256": fresh["snapshot_sha256"]}


def headline(manifest: dict[str, Any]) -> dict[str, Any]:
    """The printed report: S1 and judgment first, then the counts."""

    summary = manifest["summary"]
    return {
        "s1": {key: manifest["s1"][key] for key in ("checked", "ok", "failed", "failures")},
        "judgment_counts": summary["judgment"],
        "judgment": [
            {key: value for key, value in row.items() if key in ("kind", "name", "type", "unit", "segment", "detail", "body")}
            for row in manifest["judgment"]
        ],
        "summary": summary,
        "segments": [
            {key: row[key] for key in ("segment", "units", "functions", "s1_failed", "data", "members_to_add", "judgment")}
            | {"bodies": sum(row["bodies"].values())}
            for row in manifest["segments"]
        ],
        "manifest_sha256": manifest["manifest_sha256"],
    }
