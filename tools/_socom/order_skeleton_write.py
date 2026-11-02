"""Stage 5 phase B round 2: the ``.cpp`` skeleton writer (``order skeleton write``), preview only.

The writer reads the skeleton manifest (``order skeleton manifest``: its own
digest, the frozen body snapshot it names, the ``src/`` digest it was built on
and the accepted order plans it cites must all still hold), the accepted order
plans (row order) and ``src/``.  It writes a mirror of ``src/`` under a preview
root inside ``build/`` (this round refuses every other root; round 3 adds the
governed ``src/`` route) and a write manifest beside it.

Per unit file (in the plan's order):

1. the stage 4 annotation blocks and the separator after them, byte-identical;
2. the authored preamble, untouched except that the provisional definitions and
   data definitions the skeleton replaces, moves or holds are cut out (whole
   lines where they own them; a blank line left on both sides of a cut is
   merged);
3. one fenced entry per planned row, ``/* @socom-skeleton <stub|body> <mangled> */``
   (no addresses), in an order that keeps the plan's function order and each
   region's data order: local statics and function-local classes sit inside
   their owning function, and each run of file-scope data between two local
   statics of a region goes right after the earlier static's owner (before the
   first function when no static precedes it).  Where the planned function
   order cannot keep two statics of a region in order, the pair is flagged
   ``local-static-order-conflict`` (both rows, the region, whether the plan's
   basis records it); the function order and the owners are kept.

A ``body`` entry is a provisional definition moved from the frozen snapshot,
byte-identical except for a recorded head rewrite: BD6 (the declarator becomes
the ELF signature; parameter names carried when the arity is unchanged) or an
in-class body moved out of line (the qualified head).  Constructor initializer
lists are kept.  A ``stub`` entry is the canonical text built from the manifest
signature (BD1: unproven pieces written ``void``/instance and flagged), with
its local statics in counter order and its function-local class.  Data entries
are generated from the manifest (type, ``static``, top-level ``const`` for
``.rodata``, the ELF initializer, BD5); struct, enum and nested-array
initializers are rendered from the DWARF layout.  A provisional data definition
is kept verbatim (``body``) only where the ELF initializer cannot be rendered or
it holds a dynamic initializer of a nobits object.

``--all`` also writes the unbuilt per-module holding files (BD4: copy-only,
unowned and non-ELF code, overload ties held until decided) and removes the
orphan ``.cpp`` files the moves leave empty.  Every judgment row and every
default gets a flag; rows for which any default would be fabricated are not
written and are listed as waiting.  The output is deterministic; the write
manifest carries ``write_sha256`` over its canonical JSON.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import struct
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from .cxx_scan import Program, Speller, chain_of, data_symbols, definition_text, function_symbol, tokenize
from .mw_mangle import MangleError, parse_symbol
from .order_skeleton import (
    MANIFEST_KIND,
    MANIFEST_SCHEMA,
    SNAPSHOT_KIND,
    _digest,
    accepted_plans,
    holding_file,
    scan_sources,
    symbol_chains,
)
from .util import SocomError, canonical_json, load_json

WRITE_KIND = "socom-order-skeleton-write"
WRITE_SCHEMA = 1
WRITE_MANIFEST = "skeleton-write.json"
MANIFEST_PATH = "build/stage5/skeleton-manifest.json"
SNAPSHOT_PATH = "build/stage5/provisional-bodies.json"
DEFAULT_NEWLINE = "\r\n"  # the tree's convention, for files that have no newline yet
FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)/\* @socom-skeleton (?P<kind>stub|body) (?P<name>\S+) \*/[ \t]*$")
HOLDING_NOTE = ("/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, "
                "held here by order skeleton write. */")
HELD_FROM = "/* held from {source} */"
BODY_MOVES = ("move-in-place", "cross-file-move", "move-out-of-line", "bd6-declarator-rewrite")
FLAG_KINDS = (
    "return-unproven", "member-unproven", "parameters-unproven", "member-conflict", "data-type-unproven",
    "explicit-zero", "initializer-from-dwarf", "generic-pointer", "section-unknown", "bd6-declarator-rewrite",
    "parameter-names-dropped", "out-of-line-head", "header-body-pending", "bd4-held", "bd4-held-data",
    "overload-tie-held", "unparsed-body-held", "ambiguous-owner-held", "mixed-data-statement-held",
    "provisional-data-replaced", "provisional-data-kept", "local-static-owner-hypothesis", "local-static-in-body",
    "local-static-not-in-body", "local-static-order-conflict", "local-class-owner-hypothesis", "local-class-key-unproven",
    "in-class-row", "by-value-undeclared",
)
WAIT_KINDS = ("local-static-owner", "initializer-unrenderable", "overload-tie", "local-class-owner", "type-undefined")
_ZERO_INIT = re.compile(r"^(?:0+|0x0+|0*\.0*f?|0\.0*f?|NULL|false|\{\s*0?\s*\})$", re.I)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- inputs --------------------------------------------------------------------------------


def read_source(path: Path) -> tuple[str, str]:
    """(the text with LF newlines, the file's newline); mixed newlines are refused (bytes could not stay exact)."""

    if not path.is_file():
        return "", DEFAULT_NEWLINE
    text = path.read_bytes().decode("utf-8")
    crlf = text.count("\r\n")
    lone_lf = text.count("\n") - crlf
    lone_cr = text.count("\r") - crlf
    if lone_cr or (crlf and lone_lf):
        raise SocomError(f"{path.name} mixes newline styles: the skeleton writer keeps bytes exact only for one style")
    return text.replace("\r\n", "\n"), "\r\n" if crlf else "\n" if lone_lf else DEFAULT_NEWLINE


def split_blocks(path: str, text: str) -> tuple[str, str]:
    """(the leading stage 4 blocks with BOM and separator, verbatim; the authored rest)."""

    from .source_apply import parse_blocks

    _bom, blocks, rest = parse_blocks(text)
    prefix = text[: len(text) - len(rest)] if rest else text
    if not text.endswith(rest):
        raise SocomError(f"{path}: a stage 4 annotation block is not at the top of the file")
    _b2, again, tail = parse_blocks(prefix)
    if tail.strip() or sorted(again) != sorted(blocks):
        raise SocomError(f"{path}: a stage 4 annotation block is not at the top of the file")
    return prefix, rest


def verify_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("kind") != MANIFEST_KIND or manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise SocomError(f"the skeleton manifest is not a {MANIFEST_KIND} (schema {MANIFEST_SCHEMA})")
    if manifest.get("selection") != {"all": True}:
        raise SocomError("the writer needs the manifest of every planned row (order skeleton manifest without --segment)")
    body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if _digest(body) != manifest.get("manifest_sha256"):
        raise SocomError("the skeleton manifest's content does not match its manifest_sha256")
    return manifest


def verify_snapshot(snapshot: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(snapshot, dict) or snapshot.get("kind") != SNAPSHOT_KIND:
        raise SocomError(f"the body snapshot is not a {SNAPSHOT_KIND}")
    body = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    if _digest(body) != snapshot.get("snapshot_sha256"):
        raise SocomError("the body snapshot's content does not match its snapshot_sha256")
    if snapshot["snapshot_sha256"] != manifest["inputs"]["snapshot_sha256"]:
        raise SocomError("the body snapshot is not the one the skeleton manifest was built with")
    for row in snapshot["bodies"]:
        if _sha(row["text"]) != row["sha256"]:
            raise SocomError(f"snapshot body {row['id']} does not match its SHA-256")
    return snapshot


class SkeletonInputs:
    """The verified manifest, snapshot, accepted plans and ``src/`` scan the writer and the check read."""

    def __init__(self, root: Path, tracker: dict[str, Any], *, manifest_path: Path, snapshot_path: Path) -> None:
        from .elf import Elf32File

        self.root = root
        for path, what in ((manifest_path, "skeleton manifest"), (snapshot_path, "body snapshot")):
            if not path.is_file():
                raise SocomError(f"the {what} {path.name} does not exist: run `order skeleton manifest --output {MANIFEST_PATH}`")
        self.manifest = verify_manifest(load_json(manifest_path))
        self.snapshot = verify_snapshot(load_json(snapshot_path), self.manifest)
        plans, link = accepted_plans(root, tracker)
        cited = {row["item"]: row["sha256"] for row in self.manifest["inputs"]["plans"]}
        current = {row["item"]: row["sha256"] for row in plans}
        if cited != current or (self.manifest["inputs"].get("link_plan") or {}).get("sha256") != link.get("sha256"):
            raise SocomError("the accepted order plans are not the ones the skeleton manifest cites: rebuild the manifest")
        self.plans = sorted(plans, key=lambda row: row["plan"]["segment_number"])
        scans, files = scan_sources(root)
        src_sha256 = _digest(sorted((path, row["authored_sha256"]) for path, row in files.items()))
        if src_sha256 != self.manifest["inputs"]["src_sha256"]:
            raise SocomError("src/ changed since the skeleton manifest was built: rebuild it (order skeleton manifest)")
        self.src_sha256 = src_sha256
        self.scans = {scan.path: scan for scan in scans}
        self.elf = Elf32File(root / "support" / "socom.elf")
        chains: set[tuple[str, ...]] = set()
        seen: set[str] = set()
        for symbol in self.elf.symbols():
            if symbol.name and symbol.name not in seen:
                seen.add(symbol.name)
                chains |= symbol_chains(parse_symbol(symbol.name))
        self.chains = chains
        self.program = Program(scans, chains)
        self.signatures = {row["artifact"]: row for row in self.manifest["signatures"]}
        self.data = {row["artifact"]: row for row in self.manifest["data"]}
        self.bodies = {row["id"]: row for row in self.manifest["bodies"]["definitions"]}
        self.texts = {row["id"]: row for row in self.snapshot["bodies"]}
        self.files = {row["path"]: row for row in self.manifest["bodies"]["files"]}
        self.units: list[tuple[int, dict[str, Any]]] = [
            (row["plan"]["segment_number"], unit) for row in self.plans for unit in row["plan"]["units"]
        ]
        self.body_for_row: dict[str, dict[str, Any]] = {}
        for body in self.manifest["bodies"]["definitions"]:
            if body["action"] in BODY_MOVES and body.get("row"):
                self.body_for_row[body["row"]["artifact"]] = body
        self._layouts: _Layouts | None = None
        self._data_types: dict[int, Any] | None = None

    @property
    def layouts(self) -> "_Layouts":
        if self._layouts is None:
            self._layouts = _Layouts(self.elf)
        return self._layouts

    def record(self) -> dict[str, Any]:
        return {
            "manifest_sha256": self.manifest["manifest_sha256"],
            "snapshot_sha256": self.snapshot["snapshot_sha256"],
            "src_sha256": self.src_sha256,
            "order_sha256": self.manifest["inputs"]["order_sha256"],
            "plans": self.manifest["inputs"]["plans"],
            "link_plan": self.manifest["inputs"].get("link_plan"),
        }


# -- DWARF layouts for struct, enum and nested-array initializers ---------------------------


class Unrenderable(ValueError):
    pass


class _Layouts:
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
        self.named: dict[str, list[Any]] = defaultdict(list)
        self.variables: dict[int, list[Any]] = defaultdict(list)
        for die in dies:
            if die.tag_name in ("class_type", "structure_type", "union_type", "enumeration_type", "typedef"):
                name = die.string("name")
                if name:
                    self.named[name].append(die)
            location = die.attribute("location")
            value = getattr(location, "value", None)
            if isinstance(value, bytes) and len(value) == 5 and value[0] == 0x03 and die.tag_name in (
                "global_variable", "local_variable", "variable", "member"
            ):
                self.variables[int.from_bytes(value[1:], "little")].append(die)

    def find(self, name: str, size: int | None) -> Any:
        """The DWARF type DIE spelled ``name`` (of that size): every complete record must agree in shape.

        A class, struct, union or enum record wins over a typedef of the same name.
        """

        complete = [die for die in self.named.get(name, []) if die.tag_name != "typedef" and die.integer("byte_size")]
        if size is not None:
            complete = [die for die in complete if die.integer("byte_size") == size]
        rows = complete or [die for die in self.named.get(name, []) if die.tag_name == "typedef"]
        shapes = {self._shape(die) for die in rows}
        if len(shapes) != 1:
            raise Unrenderable(f"no single DWARF record of {name}" + (f" with {size} bytes" if size is not None else ""))
        return rows[0]

    def _shape(self, die: Any) -> Any:
        from .type_identity import member_offset, type_ref

        if die.tag_name == "typedef":
            return ("typedef", type_ref(die))
        members = tuple(
            (child.tag_name, child.string("name"), member_offset(child), child.integer("bit_size"), self._ref_shape(type_ref(child)))
            for child in self.children.get(die.offset, []) if child.tag_name in ("member", "inheritance")
        )
        elements = die.attribute("element_list")
        return (die.tag_name, die.integer("byte_size"), members, getattr(elements, "value", None))

    def _ref_shape(self, ref: Any) -> Any:
        if ref is None:
            return None
        modifiers, target, fund = ref
        die = self.by_offset.get(target) if target is not None else None
        return (bytes(modifiers), fund, (die.tag_name, die.string("name"), die.integer("byte_size")) if die is not None else None)

    def size_of(self, ref: Any) -> int:
        from .type_identity import parse_subscr, type_ref

        modifiers, target, fund = ref
        if any(modifier in (0x01, 0x02) for modifier in modifiers):
            return 4
        if target is None:
            if fund == 0x000D:  # FT_pointer
                return 4
            size = _fund_size(fund)
            if size is None:
                raise Unrenderable(f"fundamental type 0x{fund:x}")
            return size
        die = self.by_offset.get(target)
        if die is None:
            raise Unrenderable("missing DIE")
        if die.tag_name == "typedef":
            inner = type_ref(die)
            if inner is None:
                raise Unrenderable("typedef without a type")
            return self.size_of(inner)
        if die.tag_name == "pointer_type":
            return 4
        if die.tag_name == "array_type":
            subscript = die.attribute("subscr_data")
            dims, element = parse_subscr(subscript.value if subscript and isinstance(subscript.value, bytes) else b"")
            if element is None or any(len(dim) != 4 or not isinstance(dim[3], int) for dim in dims):
                raise Unrenderable("array extent")
            count = 1
            for dim in dims:
                count *= dim[3] - dim[2] + 1
            return count * self.size_of(element)
        size = die.integer("byte_size")
        if not size:
            raise Unrenderable(f"{die.tag_name} without a size")
        return size

    def render_die(self, die: Any, data: bytes, offset: int, values: "_Values", *, spelled: str | None = None) -> str:
        """The initializer of a struct/class, union (refused) or enum DIE at ``offset``.

        ``spelled`` is the C++ name an enum value is cast to (a typedef's name for an unnamed enum).
        """

        from .type_identity import member_offset, type_ref

        if die.tag_name == "typedef":
            inner = type_ref(die)
            if inner is None:
                raise Unrenderable("typedef without a type")
            return self.render_ref(inner, data, offset, values, spelled=spelled or values.spell_named(die.string("name")))
        size = die.integer("byte_size") or 0
        if die.tag_name == "enumeration_type":
            # The storage's sign is not recorded (element_list constants are byte_size wide): a 4-byte enum is
            # read as int, a narrower one unsigned; either spelling stores the same bytes.
            value = int.from_bytes(data[offset : offset + size], "little", signed=size == 4)
            values.dwarf = True
            name = die.string("name")
            cast = values.spell_named(name) if name and not name.startswith("@") else spelled
            if cast is None:
                raise Unrenderable("an unnamed enum")
            return f"({cast}){value}"
        if die.tag_name == "union_type":
            raise Unrenderable("a union initializer needs a member choice")
        if die.tag_name not in ("structure_type", "class_type"):
            raise Unrenderable(f"{die.tag_name} DIE")
        members = []
        for child in self.children.get(die.offset, []):
            if child.tag_name == "inheritance":
                raise Unrenderable("a class with bases is not an aggregate")
            if child.tag_name != "member":
                continue
            if child.integer("bit_size") is not None:
                raise Unrenderable("bit-field members")
            where = member_offset(child)
            ref = type_ref(child)
            if where is None or ref is None:
                raise Unrenderable("a member without an offset or type")
            members.append((where, ref))
        members.sort(key=lambda row: row[0])
        covered = 0
        parts = []
        for where, ref in members:
            width = self.size_of(ref)
            if where < covered:
                raise Unrenderable("overlapping members")
            if any(data[offset + covered : offset + where]):
                raise Unrenderable("non-zero padding")
            parts.append(self.render_ref(ref, data, offset + where, values))
            covered = where + width
        if any(data[offset + covered : offset + size]):
            raise Unrenderable("non-zero tail padding")
        values.dwarf = True
        return "{" + ", ".join(parts) + "}"

    def render_ref(self, ref: Any, data: bytes, offset: int, values: "_Values", *, spelled: str | None = None) -> str:
        from .cxx_scan import builtin_node
        from .order_skeleton import _DWARF_FUND
        from .type_identity import parse_subscr

        modifiers, target, fund = ref
        indirect = [modifier for modifier in modifiers if modifier in (0x01, 0x02)]
        if indirect:
            return values.pointer(data, offset, reference=indirect[0] == 0x02)
        if target is None:
            if fund == 0x000D:
                return values.pointer(data, offset, reference=False)
            words = _DWARF_FUND.get(fund)
            if words is None:
                raise Unrenderable(f"fundamental type 0x{fund:x}")
            node = builtin_node(words)
            return values.scalar((node["code"], node.get("sign")), data, offset)
        die = self.by_offset.get(target)
        if die is None:
            raise Unrenderable("missing DIE")
        if die.tag_name == "pointer_type":
            return values.pointer(data, offset, reference=False)
        if die.tag_name == "array_type":
            subscript = die.attribute("subscr_data")
            dims, element = parse_subscr(subscript.value if subscript and isinstance(subscript.value, bytes) else b"")
            if element is None or any(len(dim) != 4 or not isinstance(dim[3], int) for dim in dims):
                raise Unrenderable("array extent")
            counts = [dim[3] - dim[2] + 1 for dim in dims]
            width = self.size_of(element)

            def nest(level: int, base: int) -> str:
                stride = width
                for count in counts[level + 1 :]:
                    stride *= count
                if level == len(counts) - 1:
                    return "{" + ", ".join(self.render_ref(element, data, base + index * width, values) for index in range(counts[level])) + "}"
                return "{" + ", ".join(nest(level + 1, base + index * stride) for index in range(counts[level])) + "}"

            return nest(0, offset)
        return self.render_die(die, data, offset, values, spelled=spelled)


_SCALAR_WIDTHS = {"c": 1, "b": 1, "s": 2, "i": 4, "f": 4, "d": 8, "x": 8, "l": 8}


def _fund_size(fund: int) -> int | None:
    from .cxx_scan import builtin_node
    from .order_skeleton import _DWARF_FUND

    words = _DWARF_FUND.get(fund)
    return None if words is None else _SCALAR_WIDTHS.get(builtin_node(words)["code"])


class _Values:
    """Scalar and address initializers for one data row: relocated words become ``&symbol``."""

    def __init__(self, writer: "_Writer", relocations: list[dict[str, Any]], scopes: list[tuple[str, ...]], unnamed: str | None) -> None:
        self.writer = writer
        self.by_offset = {row["offset"]: row for row in relocations}
        self.used: set[int] = set()
        self.speller = Speller(writer.inputs.program, scopes, inside_unnamed=unnamed)
        self.dwarf = False

    def spell_named(self, raw: str | None) -> str:
        if not raw:
            raise Unrenderable("an anonymous type")
        chains = sorted(chain for chain in self.writer.inputs.program.kinds if chain and chain[-1] == raw
                        and not self.writer.inputs.program.is_namespace(chain))
        components = [{"name": part} if not part.startswith("@unnamed@") else {"unnamed": part[9:-1]} for part in (chains[0] if len(chains) == 1 else (raw,))]
        return self.speller.qualified(components)

    def scalar(self, code: Any, data: bytes, offset: int) -> str:
        if code is None:
            raise Unrenderable("a fundamental type without a rendering")
        letter, sign = code if isinstance(code, tuple) else (code, None)
        if offset in self.by_offset:
            raise Unrenderable("a relocated word in a scalar member")
        width = {"c": 1, "b": 1, "s": 2, "i": 4, "f": 4, "d": 8, "x": 8, "l": 8}[letter]
        chunk = data[offset : offset + width]
        if letter == "f":
            from .order_skeleton import _float_text

            return _float_text(struct.unpack("<f", chunk)[0])
        if letter == "d":
            return repr(struct.unpack("<d", chunk)[0])
        return str(int.from_bytes(chunk, "little", signed=sign != "U" and letter != "b"))

    def pointer(self, data: bytes, offset: int, *, reference: bool, cast: str | None = None) -> str:
        """A pointer word: ``&symbol`` for a relocated one, 0, or ``(T)0x...`` for a value outside the image."""

        relocation = self.by_offset.get(offset)
        word = int.from_bytes(data[offset : offset + 4], "little")
        if relocation is None:
            if reference:
                raise Unrenderable("a reference without a relocation")
            if word == 0:
                return "0"
            if self.writer.in_image(word):
                raise Unrenderable(f"an image address without a relocation at +{offset}")
            if cast is None:
                raise Unrenderable(f"a pointer value 0x{word:x} whose type the layout does not spell")
            return f"({cast})0x{word:x}"
        self.used.add(offset)
        return self.writer.address(relocation, self.speller, reference=reference)


# -- the writer ----------------------------------------------------------------------------


def parse_fences(text: str) -> list[dict[str, Any]]:
    """Top-level fenced entries of a written file: kind, name, the line span and the entry text after the fence line."""

    lines = text.split("\n")
    starts = [index for index, line in enumerate(lines) if (match := FENCE_RE.match(line)) and not match.group("indent")]
    rows = []
    for number, start in enumerate(starts):
        end = starts[number + 1] if number + 1 < len(starts) else len(lines)
        body = lines[start + 1 : end]
        while body and not body[-1].strip():
            body.pop()
        match = FENCE_RE.match(lines[start])
        assert match is not None
        nested = []
        for offset, line in enumerate(body):
            inner = FENCE_RE.match(line)
            if inner and inner.group("indent"):
                nested.append({"kind": inner.group("kind"), "name": inner.group("name"), "line": start + 2 + offset})
        rows.append({"kind": match.group("kind"), "name": match.group("name"), "line": start + 1,
                     "end_line": start + 1 + len(body), "text": "\n".join(body), "nested": nested})
    return rows


def _scope_wrappers(scope: tuple[tuple[str, Any], ...]) -> tuple[list[str], list[str]]:
    """The namespace and ``extern "C"`` lines that reopen a definition's original scope."""

    opening, closing = [], []
    for kind, value in scope:
        if kind == "ns":
            opening.append(f"namespace {value} {{" if value else "namespace {")
            closing.insert(0, "}")
        elif kind == "externc":
            opening.append('extern "C" {')
            closing.insert(0, "}")
        else:
            raise SocomError(f"a namespace-scope definition inside {kind} {value}")
    return opening, closing


def _local_component(structured: dict[str, Any]) -> bool:
    return any("local" in component for component in structured.get("scope") or [])


class _Writer:
    def __init__(self, inputs: SkeletonInputs) -> None:
        self.inputs = inputs
        self.program = inputs.program
        self.images = [(section.address, section.address + section.size) for section in inputs.elf.sections
                       if section.address and section.size and section.flags & 0x2]
        self.unit_tags = {unit["unit"]: PurePosixPath(unit["workspace_path"]).name.replace(".", "_") for _number, unit in inputs.units}
        self.held: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.replaced: list[dict[str, Any]] = []
        self.replaced_rows: set[str] = set()
        self.waiting: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []
        self.statements: dict[str, list[dict[str, Any]]] = defaultdict(list)  # path -> statements to cut
        self.kept_data: dict[str, dict[str, Any]] = {}  # row artifact -> a provisional statement kept as its body
        self.preamble_bodies: set[str] = set()
        self._addresses: dict[str, int] | None = None
        self.address_takers = self._address_takers()
        self._plan_data_statements()
        self._plan_bodies()

    # -- facts ---------------------------------------------------------------------------

    def in_image(self, word: int) -> bool:
        return any(low <= word < high for low, high in self.images)

    def _address_takers(self) -> dict[str, set[str]]:
        """Function-local class members -> the functions whose code takes their address (``.relmain`` LO16 sites)."""

        import bisect

        local = {row["name"]: row["artifact"] for row in self.inputs.manifest["signatures"] if _local_component(row["structured"])}
        found: dict[str, set[str]] = defaultdict(set)
        if not local:
            return found
        symbols = self.inputs.elf.symbols()
        functions = sorted((symbol.value, symbol.value + symbol.size) for symbol in symbols
                           if symbol.type_name == "FUNC" and symbol.size)
        starts = [low for low, _high in functions]
        for relocation in self.inputs.elf.relocations():
            if relocation.type_name != "R_MIPS_LO16" or relocation.symbol_index >= len(symbols):
                continue
            artifact = local.get(symbols[relocation.symbol_index].name)
            if artifact is None:
                continue
            index = bisect.bisect_right(starts, relocation.offset) - 1
            if index >= 0 and relocation.offset < functions[index][1]:
                found[artifact].add(f"socom:function:0x{functions[index][0]:x}")
        return found

    def symbol_address(self, name: str) -> int | None:
        if self._addresses is None:
            self._addresses = {}
            for symbol in self.inputs.elf.symbols():
                if symbol.name and symbol.size:
                    self._addresses.setdefault(symbol.name, symbol.value)
        return self._addresses.get(name)

    def address(self, relocation: dict[str, Any], speller: Speller, *, reference: bool) -> str:
        """``&symbol`` (``symbol`` for a reference), a string literal, or an element of a typed array."""

        if relocation.get("type") != "R_MIPS_32":
            raise Unrenderable(f"a {relocation.get('type')} relocation")
        if "literal" in relocation:
            if reference or relocation.get("addend"):
                raise Unrenderable("an offset into a string literal")
            from .order_skeleton import _c_string

            return _c_string(relocation["literal"])
        target = relocation.get("target") or ""
        if not target or target.startswith(("@", "$", ".")):
            raise Unrenderable(f"the relocation target {target or '?'} has no source name")
        symbol = parse_symbol(target)
        if symbol["kind"] == "c_name":
            text = symbol["name"]
        elif symbol["kind"] in ("data", "function"):
            scope = symbol.get("scope") or []
            name = symbol["name"]["text"] if "text" in symbol["name"] else None
            if name is None or name.startswith("__"):
                raise Unrenderable(f"the relocation target {target} is a special member")
            if any("local" in component for component in scope):
                raise Unrenderable(f"the relocation target {target} is in a function-local class")
            text = f"{speller.qualified(scope)}::{name}" if scope else name
            if text.startswith("::") and scope and "unnamed" in scope[0]:
                text = text[2:]
        else:
            raise Unrenderable(f"the relocation target {target} is a {symbol['kind']}")
        addend = relocation.get("addend") or 0
        if addend:
            element = self._element_size(target)
            if element is None or addend % element:
                raise Unrenderable(f"{target} + {addend} is not an element of a typed array")
            text = f"{text}[{addend // element}]"
        elif symbol["kind"] == "function" and reference:
            raise Unrenderable("a reference to a function")
        return text if reference else f"&{text}"

    def _element_size(self, target: str) -> int | None:
        from .type_identity import parse_subscr, type_ref

        address = self.symbol_address(target)
        if address is None:
            return None
        for die in self.inputs.layouts.variables.get(address, []):
            ref = type_ref(die)
            if ref is None or ref[1] is None:
                continue
            array = self.inputs.layouts.by_offset.get(ref[1])
            if array is None or array.tag_name != "array_type":
                continue
            subscript = array.attribute("subscr_data")
            _dims, element = parse_subscr(subscript.value if subscript and isinstance(subscript.value, bytes) else b"")
            if element is not None:
                try:
                    return self.inputs.layouts.size_of(element)
                except Unrenderable:
                    return None
        return None

    # -- global pre-pass: provisional data statements and body fates ---------------------

    def _statement(self, path: str, line: int) -> Any:
        scan = self.inputs.scans[path]
        return next(row for row in scan.declarations if row.line == line and row.in_class is None)

    def _plan_data_statements(self) -> None:
        for path, record in sorted(self.inputs.files.items()):
            by_line: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for row in record["data_definitions"]:
                by_line[row["line"]].append(row)
            for line, rows in sorted(by_line.items()):
                declaration = self._statement(path, line)
                scan = self.inputs.scans[path]
                text = scan.text[declaration.start : declaration.end]
                actions = {row["action"] for row in rows}
                statement = {"path": path, "line": line, "start": declaration.start, "end": declaration.end, "text": text,
                             "scope": declaration.scope, "names": [row["name"] for row in rows], "rows": rows}
                mapped = [row for row in rows if row["action"] in ("in-place", "cross-file-move")]
                held = [row for row in rows if row["action"] in ("unowned", "no-elf-data")]
                if actions & {"preamble", "judgment"}:
                    continue  # stays in the preamble
                self.statements[path].append(statement)
                if held:
                    flag = "mixed-data-statement-held" if mapped else "bd4-held-data"
                    self.held[holding_file(path)].append({**statement, "kind": "data", "flag": flag,
                                                          "mangled": rows[0]["mangled"]})
                if len(mapped) == 1 and not held and len(rows) == 1 and self._keep(mapped[0], declaration, text):
                    self.kept_data[mapped[0]["artifact"]] = statement
                elif mapped:
                    self.replaced.append({"path": path, "line": line, "text": text, "sha256": _sha(text),
                                          "rows": sorted(row["artifact"] for row in mapped)})
                    self.replaced_rows.update(row["artifact"] for row in mapped)

    def _keep(self, row: dict[str, Any], declaration: Any, text: str) -> bool:
        """A provisional statement is kept verbatim when the ELF bytes cannot replace its initializer."""

        datum = self.inputs.data.get(row["artifact"])
        if datum is None:
            return False
        initializer = self._initializer_text(declaration, row["name"])
        if initializer is None:
            return False
        if datum["nobits"]:
            return not _ZERO_INIT.match(initializer.strip())
        if datum["initializer"]["kind"] != "bytes" or "rendered" in datum["initializer"]:
            return False
        return not self._renders(datum)

    def _renders(self, datum: dict[str, Any]) -> bool:
        """Whether the writer renders this row's ELF initializer itself (no side effects)."""

        structured = datum["structured"]
        variable = structured.get("variable") if structured["kind"] == "local_static" else (
            structured["name"]["text"] if structured["kind"] == "data" else structured.get("name", datum["name"]))
        node, _generic = self._type_node(datum, variable, self.unit_tags.get(datum["unit"], ""))
        if node is None:
            return False
        try:
            self._render(datum, node, Speller(self.program, [()]), None)
        except Unrenderable:
            return False
        return True

    @staticmethod
    def _initializer_text(declaration: Any, name: str) -> str | None:
        tokens = declaration.tokens
        for index, token in enumerate(tokens):
            if token.text == name and index + 1 < len(tokens) and tokens[index + 1].text in ("=", "(", "{"):
                follow = tokens[index + 1]
                start = follow.end if follow.text == "=" else follow.start
                return " ".join(item.text for item in tokens if item.start >= start)
        return None

    def _plan_bodies(self) -> None:
        for body in self.inputs.manifest["bodies"]["definitions"]:
            action = body["action"]
            if action == "preamble":
                self.preamble_bodies.add(body["id"])
            elif action == "bd4-holding" or action == "judgment":
                flag = {"overload-tie": "overload-tie-held", "unparsed-body": "unparsed-body-held",
                        "ambiguous-owner": "ambiguous-owner-held"}.get(body.get("judgment") or "", "bd4-held")
                target = body.get("holding_file") or holding_file(body["path"])
                self.held[target].append({"kind": "function", "path": body["path"], "line": body["span"]["start_line"],
                                          "body": body, "flag": flag, "mangled": body.get("mangled")})
                if body.get("judgment") == "overload-tie":
                    self.waiting.append({"kind": "overload-tie", "body": body["id"], "name": body.get("mangled"),
                                         "candidates": body.get("candidates") or [],
                                         "detail": "held; every candidate row gets a stub until a decision assigns the body"})

    # -- one unit file -------------------------------------------------------------------

    def unit_file(self, segment: int, unit: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        path = unit["workspace_path"]
        text, newline = read_source(self.inputs.root / path)
        prefix, rest = split_blocks(path, text)
        scan = self.inputs.scans.get(path)
        if scan is not None and scan.text != rest:
            raise SocomError(f"{path}: the authored content differs from the manifest's scan")
        existing = parse_fences(rest)
        if existing:
            raise SocomError(f"{path} already holds skeleton fences: rewriting written skeletons is the round 3 src/ route")
        preamble = cut_preamble(rest, self._cuts(path))
        entries, rows = self._entries(segment, unit)
        out = prefix + preamble
        if entries:
            if out and not out.endswith("\n"):
                out += "\n"
            if out and not out.endswith("\n\n"):
                out += "\n"
            out += "\n\n".join(entries) + "\n"
        return out.replace("\n", newline), rows

    def _cuts(self, path: str) -> list[tuple[int, int]]:
        scan = self.inputs.scans.get(path)
        if scan is None:
            return []
        cuts = []
        starts = {}
        for definition in scan.definitions:
            if definition.in_class is None:
                starts[definition.line] = definition
        for body in self.inputs.manifest["bodies"]["definitions"]:
            if body["path"] != path or body["kind"] != "definition" or body["id"] in self.preamble_bodies:
                continue
            definition = starts.get(body["span"]["start_line"])
            if definition is None or _sha(scan.text[definition.start : definition.end]) != body["sha256"]:
                raise SocomError(f"{body['id']}: the definition is not where the snapshot recorded it")
            cuts.append((definition.start, definition.end))
        for statement in self.statements.get(path, []):
            cuts.append((statement["start"], statement["end"]))
        return sorted(cuts)

    # -- entries -------------------------------------------------------------------------

    def _entries(self, segment: int, unit: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
        name = unit["unit"]
        tag = PurePosixPath(unit["workspace_path"]).name.replace(".", "_")
        functions = [row for row in unit["functions"] if not row.get("in_class")]
        in_class = [row for row in unit["functions"] if row.get("in_class")]
        local_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
        out_of_line = []
        for row in functions:
            signature = self.inputs.signatures[row["artifact"]]
            if _local_component(signature["structured"]):
                local_class["pending"].append(row)
            else:
                out_of_line.append(row)
        written_functions = {row["artifact"]: row for row in out_of_line}
        order_of = {row["artifact"]: (row["position"] if row.get("position") is not None else 10**6) for row in out_of_line}
        chain = sorted(out_of_line, key=lambda row: (order_of[row["artifact"]], row["artifact"]))
        index = {row["artifact"]: number for number, row in enumerate(chain)}
        # Local statics and local-class members: pinned to an owning function of this unit.
        owners: dict[str, str] = {}
        flags: dict[str, list[dict[str, Any]]] = defaultdict(list)
        statics: dict[str, list[dict[str, Any]]] = defaultdict(list)
        counters: dict[str, int] = {}
        hypotheses: list[tuple[dict[str, Any], dict[str, Any], list[str]]] = []
        for region in unit["data"]:
            for row in region["rows"]:
                datum = self.inputs.data[row["artifact"]]
                if datum["storage"] != "local-static":
                    continue
                counters[row["artifact"]] = datum["structured"].get("number") or 0
                owner = datum.get("owner_function") or {}
                chosen = owner.get("artifact")
                if chosen is None:
                    candidates = sorted((artifact for artifact in owner.get("candidates") or [] if artifact in written_functions),
                                        key=lambda artifact: order_of[artifact])
                    if owner.get("basis") == "several functions" and candidates:
                        hypotheses.append((region, row, candidates))
                    else:
                        self.waiting.append({"kind": "local-static-owner", "artifact": row["artifact"], "name": row["name"],
                                             "unit": name, "segment": segment, "detail": owner.get("basis")})
                    continue
                if chosen not in written_functions:
                    self.waiting.append({"kind": "local-static-owner", "artifact": row["artifact"], "name": row["name"],
                                         "unit": name, "segment": segment, "detail": "its owner is not an out-of-line row of the unit"})
                    continue
                owners[row["artifact"]] = chosen
        waiting_data = {row["artifact"] for row in self.waiting if row["kind"] == "local-static-owner"}
        variables = {artifact: self.inputs.data[artifact]["structured"].get("variable") for artifact in counters}
        undecided = {row["artifact"] for _region, row, _candidates in hypotheses}
        for region, row, candidates in hypotheses:
            undecided.discard(row["artifact"])
            chosen, fewer = _choose_owner(region, row["artifact"], candidates, owners, waiting_data | undecided, index, counters, variables)
            owners[row["artifact"]] = chosen
            detail = f"first of {len(candidates)} referencing functions in source order"
            if chosen != candidates[0]:
                first = written_functions[candidates[0]]["name"]
                reason = (f"{fewer} order conflict(s) fewer than {first}" if fewer is not None else
                          f"{first} already declares a static named {variables[row['artifact']]}")
                detail = (f"{written_functions[chosen]['name']}: of {len(candidates)} referencing functions, the one that best "
                          f"keeps the {region['label']} declaration order ({reason})")
            flags[row["artifact"]].append({"kind": "local-static-owner-hypothesis", "detail": detail})
        for region in unit["data"]:
            for row in region["rows"]:
                if row["artifact"] in owners:
                    statics[owners[row["artifact"]]].append(row)
        pending = local_class.pop("pending", [])
        if pending:
            owner = self._local_class_owner(pending, written_functions, order_of)
            if owner is None:
                for row in pending:
                    self.waiting.append({"kind": "local-class-owner", "artifact": row["artifact"], "name": row["name"],
                                         "unit": name, "segment": segment, "detail": "no referencing function of the unit is a stub"})
            else:
                artifact, detail = owner
                local_class[artifact] = pending
                self.waiting.append({"kind": "local-class-owner", "artifact": artifact, "name": written_functions[artifact]["name"],
                                     "unit": name, "segment": segment, "members": [row["name"] for row in pending],
                                     "detail": f"default owner {detail}; the true owner is unproven"})
                for row in pending:
                    owners[row["artifact"]] = artifact
        # The order: functions by position, pinned rows at their owner, file-scope data interleaved (_entry_order).
        order, placements, conflicts = _entry_order(chain, unit["data"], owners, waiting_data, counters)
        for step in conflicts:
            before, after, region = step["before"], step["after"], step["region"]
            owner_names = [written_functions[owners[row["artifact"]]]["name"] for row in (before, after)]
            if owner_names[0] != owner_names[1]:
                why = f"the planned function order puts {owner_names[1]} before {owner_names[0]}"
            elif counters[before["artifact"]] > counters[after["artifact"]]:
                why = f"the static counters of {owner_names[0]} run against the data order"
            else:
                why = f"file-scope data lie between two statics of {owner_names[0]}"
            basis = plan_basis_mentions(unit, [before["name"], after["name"]])
            self.conflicts.append({
                "kind": "local-static-order-conflict", "unit": name, "segment": segment, "region": region["label"],
                "before": {"name": before["name"], "owner": owner_names[0], "position": before.get("position")},
                "after": {"name": after["name"], "owner": owner_names[1], "position": after.get("position")},
                "between": [row["name"] for row in step["between"]],
                "plan_basis_records": bool(basis), "plan_basis": basis,
                "detail": f"{why}: the planned function order is kept and both statics stay in their owners (phase C)",
            })
            for row, other in ((before, after), (after, before)):
                flags[row["artifact"]].append({"kind": "local-static-order-conflict",
                                               "detail": f"{region['label']}: against {other['name']}"})
        rows_out: list[dict[str, Any]] = []
        entries: list[str] = []
        for kind, artifact in order:
            if kind == "f":
                text, record = self._function_entry(written_functions[artifact], tag, segment, name, statics.get(artifact, []),
                                                    local_class.get(artifact, []), flags)
            else:
                text, record = self._data_entry(self.inputs.data[artifact], tag, segment, name, flags.get(artifact, []))
                if text is None:
                    continue
                place = placements[artifact]
                record["placement"] = {
                    "rule": "after-local-static-owner" if place["after"] else "before-functions",
                    "after": written_functions[place["after"]]["name"] if place["after"] else None,
                    "local_static": self.inputs.data[place["local_static"]]["name"] if place["local_static"] else None,
                    **({"between_conflicting_statics": True} if place["conflict"] else {}),
                }
            entries.append(text)
            rows_out.append(record)
        for row in in_class:
            rows_out.append({"kind": "in-class", "name": row["name"], "artifact": row["artifact"], "unit": name,
                             "segment": segment, "position": row.get("position"),
                             "flags": [{"kind": "in-class-row", "detail": "stays in its class body (BD8); the class body is the round 3 declaration writer's"}]})
        return entries, rows_out

    def _local_class_owner(self, pending: list[dict[str, Any]], written: dict[str, dict[str, Any]],
                           order_of: dict[str, int]) -> tuple[str, str] | None:
        users: set[str] = set()
        for row in pending:
            users |= self.address_takers.get(row["artifact"], set())
        candidates = sorted((artifact for artifact in users if artifact in written and artifact not in self.inputs.body_for_row),
                            key=lambda artifact: order_of[artifact])
        if not candidates:
            return None
        names = ", ".join(written[artifact]["name"] for artifact in candidates)
        return candidates[0], f"{written[candidates[0]]['name']}, the first in source order of the stubs that take their addresses ({names})"

    # -- function entries ----------------------------------------------------------------

    def _function_entry(self, row: dict[str, Any], tag: str, segment: int, unit: str, statics: list[dict[str, Any]],
                        members: list[dict[str, Any]], flags: dict[str, list[dict[str, Any]]]) -> tuple[str, dict[str, Any]]:
        signature = self.inputs.signatures[row["artifact"]]
        body = self.inputs.body_for_row.get(row["artifact"])
        record: dict[str, Any] = {"kind": "function", "name": row["name"], "artifact": row["artifact"], "unit": unit,
                                  "segment": segment, "position": row.get("position"), "flags": []}
        nested: list[dict[str, Any]] = []
        if body is not None:
            text, extra = self._moved(body, signature, tag)
            record["flags"].extend(extra.pop("flags_", []))
            record.update(fence="body", source=body["id"], move=body["action"], **extra)
            for local in sorted(statics, key=lambda item: self.inputs.data[item["artifact"]]["structured"].get("number") or 0):
                variable = self.inputs.data[local["artifact"]]["structured"].get("variable") or local["name"]
                found = re.search(r"\bstatic\b[^;{}()]*\b" + re.escape(variable) + r"\b", text) is not None
                nested.append({"kind": "local-static", "name": local["name"], "artifact": local["artifact"], "position": local.get("position"),
                               "flags": flags.get(local["artifact"], []) + [{"kind": "local-static-in-body" if found else "local-static-not-in-body",
                                                                            "detail": variable}]})
            if members:
                raise SocomError(f"{row['name']}: a function-local class cannot be added to a moved body")
            entry = f"/* @socom-skeleton body {row['name']} */\n{text}"
        else:
            record.update(fence="stub", source="canonical-stub")
            record["flags"].extend(_signature_flags(signature))
            lines = []
            for local in sorted(statics, key=lambda item: self.inputs.data[item["artifact"]]["structured"].get("number") or 0):
                datum = self.inputs.data[local["artifact"]]
                declaration, local_flags = self._declaration(datum, tag, local=True)
                nested.append({"kind": "local-static", "name": local["name"], "artifact": local["artifact"],
                               "position": local.get("position"), "flags": flags.get(local["artifact"], []) + local_flags})
                if declaration is None:
                    continue
                lines.append(f"\t/* @socom-skeleton stub {local['name']} */")
                lines.append(f"\t{declaration}")
            if members:
                lines.extend(self._local_class(members, nested))
            head = signature["definition"]
            content = [head, "{", *lines, "}"]
            if signature.get("namespace") == "anonymous":
                content = ["namespace {", *content, "}"]
            text = "\n".join(content)
            entry = f"/* @socom-skeleton stub {row['name']} */\n{text}"
            record["stub_sha256"] = _sha(text)
        record["text_sha256"] = _sha(entry.split("\n", 1)[1])
        if nested:
            record["nested"] = nested
        return entry, record

    def _local_class(self, members: list[dict[str, Any]], nested: list[dict[str, Any]]) -> list[str]:
        first = self.inputs.signatures[members[0]["artifact"]]["structured"]
        local = next(component for component in first["scope"] if "local" in component)
        lines = [f"\tstruct {local['name']}", "\t{"]
        for row in sorted(members, key=lambda item: item.get("position") or 0):
            signature = self.inputs.signatures[row["artifact"]]
            declaration = (signature.get("declaration") or "").rstrip(";")
            lines += [f"\t\t/* @socom-skeleton stub {row['name']} */", f"\t\t{declaration}", "\t\t{", "\t\t}"]
            nested.append({"kind": "local-class-member", "name": row["name"], "artifact": row["artifact"], "position": row.get("position"),
                           "flags": _signature_flags(signature) + [
                               {"kind": "local-class-key-unproven", "detail": f"written struct {local['name']} (members public)"}]})
        lines.append("\t};")
        return lines

    def _moved(self, body: dict[str, Any], signature: dict[str, Any], tag: str) -> tuple[str, dict[str, Any]]:
        """The moved text of a snapshot body: verbatim, or with its head rewritten (BD6, out of line)."""

        snapshot = self.inputs.texts[body["id"]]
        text = snapshot["text"]
        extra: dict[str, Any] = {}
        flags: list[dict[str, Any]] = []
        scan = self.inputs.scans[body["path"]]
        definition = next((row for row in scan.definitions if row.line == body["span"]["start_line"]
                           and _sha(scan.text[row.start : row.end]) == body["sha256"]), None)
        if definition is None:
            raise SocomError(f"{body['id']}: the snapshot body is not in its file")
        rewrite = body["action"] in ("bd6-declarator-rewrite", "move-out-of-line")
        if not rewrite:
            opening, closing = _scope_wrappers(definition.scope)
            moved = "\n".join([*opening, text, *closing])
            extra["flags_"] = flags
            return moved, extra
        parsed = function_symbol(self.program, definition.tokens, definition.scope, scan.tag, klass=definition.in_class)
        names = parsed.param_names or []
        params = signature["structured"].get("params") or []
        declared = [] if params == [{"t": "builtin", "code": "v"}] else params
        carried = names if len(names) == len(declared) and any(names) else None
        returns = signature["return"]["text"]
        head, problems, namespace = definition_text(self.program, signature["structured"], returns, tag=tag, names=carried)
        plain, _p, _n = definition_text(self.program, signature["structured"], returns, tag=tag)
        if plain != signature["definition"] or problems:
            head, namespace = signature["definition"], signature.get("namespace")
            carried = None
        if signature.get("linkage") == "C":
            head = signature["definition"]
        if carried is None and declared:
            flags.append({"kind": "parameter-names-dropped",
                          "detail": f"{len(names)} written, {len(declared)} in the ELF name" if len(names) != len(declared) else "unnamed"})
        keep_from = _head_end(definition.tokens, definition.start)
        new_text = head + text[keep_from:]
        kind = "bd6-declarator-rewrite" if body["action"] == "bd6-declarator-rewrite" else "out-of-line-head"
        flags.append({"kind": kind, "detail": f"{body['declarator']} -> {head}"})
        if body["action"] == "move-out-of-line":
            flags.append({"kind": "header-body-pending", "detail": f"{body['path']}:{body['span']['start_line']} keeps its in-class body until round 3"})
        extra["head"] = {"from": text[:keep_from], "to": head}
        extra["body_sha256"] = _sha(text[keep_from:])
        opening, closing = (["namespace {"], ["}"]) if namespace == "anonymous" else ([], [])
        extra["flags_"] = flags
        return "\n".join([*opening, new_text, *closing]), extra

    # -- data entries --------------------------------------------------------------------

    def _data_entry(self, datum: dict[str, Any], tag: str, segment: int, unit: str,
                    flags: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
        record: dict[str, Any] = {"kind": "data", "name": datum["name"], "artifact": datum["artifact"], "unit": unit, "segment": segment,
                                  "position": datum.get("position"), "region": datum["region"], "flags": list(flags)}
        kept = self.kept_data.get(datum["artifact"])
        if kept is not None:
            opening, closing = _scope_wrappers(kept["scope"])
            text = "\n".join([*opening, kept["text"], *closing])
            record.update(fence="body", source=f"{kept['path']}:{kept['line']}", text_sha256=_sha(text))
            record["flags"].append({"kind": "provisional-data-kept",
                                    "detail": "nobits object with a dynamic initializer" if datum["nobits"] else "the ELF initializer cannot be rendered"})
            return f"/* @socom-skeleton body {datum['name']} */\n{text}", record
        declaration, more = self._declaration(datum, tag, local=False)
        record["flags"].extend(more)
        if declaration is None:
            return None, record
        if datum["artifact"] in self.replaced_rows:
            record["flags"].append({"kind": "provisional-data-replaced", "detail": "the provisional definition is replaced by the ELF-derived entry"})
        opening, closing = self._data_wrappers(datum)
        text = "\n".join([*opening, declaration, *closing])
        record.update(fence="stub", source="canonical-stub", stub_sha256=_sha(text), text_sha256=_sha(text))
        return f"/* @socom-skeleton stub {datum['name']} */\n{text}", record

    def _data_scope(self, datum: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """(namespace components to reopen, class components that qualify the declarator-id)."""

        structured = datum["structured"]
        if structured["kind"] != "data":
            return [], []
        components = structured["scope"]
        kinds = [row["kind"] for row in datum["scope"]]
        split = next((index for index, kind in enumerate(kinds) if kind == "class"), len(kinds))
        return components[:split], components[split:]

    def _data_wrappers(self, datum: dict[str, Any]) -> tuple[list[str], list[str]]:
        namespaces, _classes = self._data_scope(datum)
        opening = ["namespace {" if "unnamed" in component else f"namespace {component['name']} {{" for component in namespaces]
        return opening, ["}"] * len(opening)

    def _declaration(self, datum: dict[str, Any], tag: str, *, local: bool) -> tuple[str | None, list[dict[str, Any]]]:
        """``[static] T name [= init];`` for a data row, or None when it waits (with the flags)."""

        flags: list[dict[str, Any]] = []
        namespaces, classes = self._data_scope(datum)
        chain = []
        unnamed = None
        for component in namespaces:
            if "unnamed" in component:
                unnamed = component["unnamed"]
                chain.append(f"@unnamed@{unnamed}@")
            else:
                chain.append(component["name"])
        scopes = [tuple(chain[:index]) for index in range(len(chain), -1, -1)]
        speller = Speller(self.program, scopes, inside_unnamed=unnamed)
        structured = datum["structured"]
        variable = structured.get("variable") if structured["kind"] == "local_static" else (
            structured["name"]["text"] if structured["kind"] == "data" else structured.get("name", datum["name"]))
        node, generic = self._type_node(datum, variable, tag)
        if node is None:
            self.waiting.append({"kind": "type-undefined", "artifact": datum["artifact"], "name": datum["name"], "unit": datum["unit"],
                                 "segment": datum["segment"], "detail": f"the manifest type {datum.get('declaration_type')!r} does not parse"})
            return None, flags
        if generic:
            flags.append({"kind": "generic-pointer", "detail": f"Ghidra's untyped pointer written {generic}"})
        if datum["type"]["source"] in ("access-width", "unproven"):
            flags.append({"kind": "data-type-unproven", "detail": datum["type"].get("basis") or datum["type"]["source"]})
        if not datum["section_known"]:
            flags.append({"kind": "section-unknown", "detail": datum["label"]})
        if datum["const"]:
            node = _top_level_const(node)
        declarator = variable
        if classes:
            declarator = "::".join(speller.component(component) for component in classes) + "::" + variable
        try:
            text = speller.type(node, declarator)
        except (MangleError, KeyError) as exc:
            self.waiting.append({"kind": "type-undefined", "artifact": datum["artifact"], "name": datum["name"], "unit": datum["unit"],
                                 "segment": datum["segment"], "detail": f"cannot spell the type: {exc}"})
            return None, flags
        initializer = datum["initializer"]
        value: str | None = None
        if initializer["kind"] == "zero":
            value = initializer["rendered"]
            if not datum["nobits"]:
                flags.append({"kind": "explicit-zero", "detail": f"{datum['section']}: kept out of .bss by an explicit zero (C2 confirms)"})
        elif initializer["kind"] == "bytes":
            value = initializer.get("rendered") if not generic else None
            if value is None:
                try:
                    value, dwarf = self._render(datum, node, speller, unnamed)
                except Unrenderable as exc:
                    self.waiting.append({"kind": "initializer-unrenderable", "artifact": datum["artifact"], "name": datum["name"],
                                         "unit": datum["unit"], "segment": datum["segment"], "detail": str(exc)})
                    return None, flags
                if dwarf:
                    flags.append({"kind": "initializer-from-dwarf", "detail": "rendered from the DWARF layout"})
        elif initializer["kind"] == "unknown":
            self.waiting.append({"kind": "initializer-unrenderable", "artifact": datum["artifact"], "name": datum["name"],
                                 "unit": datum["unit"], "segment": datum["segment"], "detail": initializer.get("basis") or "unknown"})
            return None, flags
        storage = ""
        if local or (datum["storage"] == "static" and unnamed is None):
            storage = "static "
        return f"{storage}{text}" + (f" = {value}" if value is not None else "") + ";", flags

    def _type_node(self, datum: dict[str, Any], variable: str, tag: str) -> tuple[dict[str, Any] | None, str | None]:
        """The manifest type parsed back, and how the manifest spelled Ghidra's untyped ``pointer`` (None otherwise)."""

        text = datum.get("declaration_type") or ""
        tokens, _comments = tokenize(text + ";")
        rows = data_symbols(self.program, [token for token in tokens if token.text != ";"], (), tag)
        if len(rows) != 1 or rows[0].type is None or rows[0].name != variable:
            return None, None
        return rows[0].type, datum["type"].get("generic_pointer")

    def _render(self, datum: dict[str, Any], node: dict[str, Any], speller: Speller, unnamed: str | None) -> tuple[str, bool]:
        data = bytes.fromhex(datum["initializer"]["hex"])
        values = _Values(self, datum["initializer"].get("relocations") or [], speller.scopes, unnamed)
        text = self._render_node(node, data, 0, values, datum["size"])
        if values.used != set(values.by_offset):
            raise Unrenderable("a relocation the type does not place")
        return text, values.dwarf

    def _render_node(self, node: dict[str, Any], data: bytes, offset: int, values: _Values, size: int | None) -> str:
        kind = node["t"]
        if kind == "pointer":
            return values.pointer(data, offset, reference=False, cast=values.speller.type({key: value for key, value in node.items() if key != "cv"}))
        if kind == "reference":
            return values.pointer(data, offset, reference=True)
        if kind == "builtin":
            code = node["code"]
            if code in ("v", "e", "1", "r", "w"):
                raise Unrenderable(f"builtin {code}")
            return values.scalar((code, node.get("sign")), data, offset)
        if kind == "array":
            element = node["of"]
            width = self._size(element)
            return "{" + ", ".join(self._render_node(element, data, offset + index * width, values, width) for index in range(node["size"])) + "}"
        if kind == "named":
            raw = chain_of(node["name"])[-1]
            die = self.inputs.layouts.find(raw, size)
            return self.inputs.layouts.render_die(die, data, offset, values)
        raise Unrenderable(f"a {kind} type")

    def _size(self, node: dict[str, Any]) -> int:
        kind = node["t"]
        if kind in ("pointer", "reference"):
            return 4
        if kind == "builtin":
            width = {"b": 1, "c": 1, "s": 2, "i": 4, "f": 4, "d": 8, "x": 8, "l": 8}.get(node["code"])
            if width is None:
                raise Unrenderable(f"builtin {node['code']}")
            return width
        if kind == "array":
            return node["size"] * self._size(node["of"])
        if kind == "named":
            die = self.inputs.layouts.find(chain_of(node["name"])[-1], None)
            return self.inputs.layouts.size_of((b"", die.offset, None))
        raise Unrenderable(f"a {kind} type")


def _region_steps(region: dict[str, Any], owners: dict[str, str], skip: set[str], index: dict[str, int],
                  counters: dict[str, int]) -> Iterator[tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any] | None, bool]]:
    """A region's rows in plan order, cut at its pinned rows: ``(pinned before, file-scope run, pinned after, conflict)``.

    A pinned row (local static) is written at its owner's place, in counter
    order inside it: its slot is ``(owner index, counter)``.  Two consecutive
    pinned rows conflict when the second one's slot comes first, or when a
    run of file-scope rows lies between them and they share an owner (no
    file-scope place exists between them).  Rows in ``skip`` (not written) are
    left out.
    """

    def slot(row: dict[str, Any]) -> tuple[int, int]:
        return index[owners[row["artifact"]]], counters.get(row["artifact"], 0)

    rows = [row for row in sorted(region["rows"], key=lambda row: row.get("position") or 0)
            if row["artifact"] in owners or row["artifact"] not in skip]
    previous: dict[str, Any] | None = None
    run: list[dict[str, Any]] = []
    for row in [*rows, None]:
        if row is not None and row["artifact"] not in owners:
            run.append(row)
            continue
        conflict = previous is not None and row is not None and (
            slot(previous) > slot(row) or (bool(run) and slot(previous)[0] >= slot(row)[0]))
        yield previous, run, row, conflict
        previous, run = row, []


def _choose_owner(region: dict[str, Any], artifact: str, candidates: list[str], owners: dict[str, str], skip: set[str],
                  index: dict[str, int], counters: dict[str, int], variables: dict[str, str | None]) -> tuple[str, int | None]:
    """The owner of a local static several functions reference: ``(owner, conflicts fewer than the first candidate)``.

    ``candidates`` are in source order.  A candidate that already holds a
    static of the same variable name is passed over (one block cannot declare
    both), unless every candidate does.  Of the rest, the one with the fewest
    local-static order conflicts in the static's region (against the owners
    already fixed; ``skip`` rows are left out) wins, the first in source order
    on a tie.  The count is None when the first candidate was passed over.
    ``owners`` is restored on return.
    """

    taken = {owners[other] for other in counters
             if other != artifact and other in owners and variables.get(other) == variables.get(artifact)}
    usable = [candidate for candidate in candidates if candidate not in taken] or candidates
    counts = []
    previous = owners.get(artifact)
    for candidate in usable:
        owners[artifact] = candidate
        counts.append(sum(1 for step in _region_steps(region, owners, skip, index, counters) if step[3]))
    if previous is None:
        owners.pop(artifact, None)
    else:
        owners[artifact] = previous
    chosen = usable[counts.index(min(counts))]
    return chosen, (counts[0] - min(counts) if usable[0] == candidates[0] else None)


def _entry_order(chain: list[dict[str, Any]], regions_rows: list[dict[str, Any]], owners: dict[str, str], waiting: set[str],
                 counters: dict[str, int]) -> tuple[list[tuple[str, str]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """The unit's entry order, each file-scope datum's placement, and the local-static order conflicts.

    Out-of-line functions keep the plan's order (``chain``); a pinned row
    (local static, function-local class member) sits in its owner.  File-scope
    data are interleaved by one deterministic rule: each run of file-scope rows
    between two pinned rows of a region goes right after the earlier pinned
    row's owner, or before the first function when no pinned row precedes it
    (as early as the region's order allows).  Runs that land in one place go
    by region, then position.  Then every region's declaration order equals
    its plan (address) order, except across a conflict (``_region_steps``),
    which the planned function order forces: its run still follows the
    earlier static's owner, and one pair inside the conflict's span is out of
    order.
    """

    index = {row["artifact"]: number for number, row in enumerate(chain)}
    gaps: dict[int, list[tuple[tuple[int, int, str], str]]] = defaultdict(list)
    placements: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for rank, region in enumerate(regions_rows):
        for before, run, after, conflict in _region_steps(region, owners, waiting, index, counters):
            gap = index[owners[before["artifact"]]] + 1 if before is not None else 0
            for row in run:
                gaps[gap].append(((rank, row.get("position") or 0, row["artifact"]), row["artifact"]))
                placements[row["artifact"]] = {"after": chain[gap - 1]["artifact"] if gap else None,
                                               "local_static": before["artifact"] if before is not None else None,
                                               "conflict": conflict}
            if conflict:
                conflicts.append({"region": region, "before": before, "after": after, "between": run})
    order: list[tuple[str, str]] = []
    for gap in range(len(chain) + 1):
        order.extend(("d", artifact) for _key, artifact in sorted(gaps.get(gap, [])))
        if gap < len(chain):
            order.append(("f", chain[gap]["artifact"]))
    return order, placements, conflicts


def plan_basis_mentions(unit: dict[str, Any], names: list[str]) -> list[str]:
    """The plan rows of a unit whose recorded basis names one of ``names`` (function rows by name; settled, open rows and notes too)."""

    pattern = re.compile("|".join(re.escape(name) + r"(?![\w$])" for name in names))
    by_artifact = {row.get("artifact"): row.get("name") for row in unit.get("functions") or []}
    found: set[str] = set()
    for row in unit.get("functions") or []:
        if isinstance(row.get("basis"), str) and pattern.search(row["basis"]):
            found.add(row.get("name") or row.get("artifact"))
    for key in ("settled", "open"):
        for row in unit.get(key) or []:
            if not isinstance(row, dict):
                if isinstance(row, str) and pattern.search(row):
                    found.add(key)
            elif isinstance(row.get("basis"), str) and pattern.search(row["basis"]):
                found.add(by_artifact.get(row.get("artifact")) or row.get("artifact") or key)
    for note in unit.get("notes") or []:
        if pattern.search(note if isinstance(note, str) else canonical_json(note)):
            found.add("notes")
    return sorted(str(item) for item in found)


def _signature_flags(signature: dict[str, Any]) -> list[dict[str, Any]]:
    flags = []
    if signature.get("return", {}).get("source") == "unproven":
        flags.append({"kind": "return-unproven", "detail": "written void (BD1)"})
    if signature.get("member", {}).get("source") == "unproven":
        flags.append({"kind": "member-unproven", "detail": "written as an instance member (BD1)"})
    if signature.get("member", {}).get("conflict"):
        flags.append({"kind": "member-conflict", "detail": signature["member"]["conflict"]})
    if signature.get("linkage") == "C" and signature.get("parameters", {}).get("source") == "unproven":
        flags.append({"kind": "parameters-unproven", "detail": "C names do not encode parameters"})
    return flags


def _top_level_const(node: dict[str, Any]) -> dict[str, Any]:
    """The object itself const (``.rodata``): the pointer, the array element, or the type."""

    if node["t"] == "reference":
        return node
    if node["t"] == "array":
        return {**node, "of": _top_level_const(node["of"])}
    cv = node.get("cv", "")
    if "C" in cv:
        return node
    return {**node, "cv": "".join(sorted(set(cv + "C"), key="CV".index))}


def _head_end(tokens: list[Any], start: int) -> int:
    """Offset (from the definition's start) where the declarator ends: before a ctor-initializer, else after the head."""

    depth = 0
    closed = False
    previous = None
    for token in tokens:
        if token.kind == "punct" and token.text in ("(", "["):
            depth += 1
        elif token.kind == "punct" and token.text in (")", "]"):
            depth -= 1
            if depth == 0:
                closed = True
        elif token.kind == "punct" and token.text == ":" and depth == 0 and closed and previous is not None:
            return previous.end - start
        previous = token
    return tokens[-1].end - start


def cut_preamble(text: str, cuts: list[tuple[int, int]]) -> str:
    """The authored text without the cut spans, its trailing blank lines dropped (the entries follow).

    A cut takes whole lines where the span owns them (only blanks before it on
    its first line, only blanks after it on its last).  Where a cut leaves a
    blank line on both sides, one of them goes; the text never starts with a
    blank line it did not start with.
    """

    pieces = []
    cursor = 0
    for start, end in cuts:
        line_start = text.rfind("\n", 0, start) + 1
        if text[line_start:start].strip() == "":
            start = line_start
        line_end = text.find("\n", end)
        line_end = len(text) if line_end < 0 else line_end + 1
        if text[end:line_end].strip() == "":
            end = line_end
        pieces.append(text[cursor:start])
        cursor = end
    pieces.append(text[cursor:])
    out = ""
    for index, piece in enumerate(pieces):
        if index and piece.startswith("\n") and (out.endswith("\n\n") or out == ""):
            piece = piece[1:]
        out += piece
    if not text.startswith("\n"):
        out = out.lstrip("\n")
    lines = out.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def holding_text(items: list[dict[str, Any]], inputs: SkeletonInputs) -> tuple[str, list[dict[str, Any]]]:
    """One holding file: per donor file, its held bodies and data statements in line order."""

    parts = [HOLDING_NOTE]
    rows = []
    for item in sorted(items, key=lambda row: (row["path"], row["line"])):
        if item["kind"] == "function":
            body = item["body"]
            scan = inputs.scans[body["path"]]
            definition = next((row for row in scan.definitions if row.line == body["span"]["start_line"]
                               and _sha(scan.text[row.start : row.end]) == body["sha256"]), None)
            opening, closing = _scope_wrappers(definition.scope) if definition is not None and body["kind"] == "definition" else ([], [])
            text = "\n".join([*opening, inputs.texts[body["id"]]["text"], *closing])
            name = body.get("mangled") or f"unparsed:{body['id']}"
            source = body["id"]
        else:
            opening, closing = _scope_wrappers(item["scope"])
            text = "\n".join([*opening, item["text"], *closing])
            name = item.get("mangled") or f"unparsed:{item['path']}:{item['line']}"
            source = f"{item['path']}:{item['line']}"
        parts.append(f"/* @socom-skeleton body {name} */\n{HELD_FROM.format(source=source)}\n{text}")
        rows.append({"kind": "held-" + item["kind"], "name": name, "source": source, "flags": [{"kind": item["flag"], "detail": source}],
                     "text_sha256": _sha(text)})
    return "\n\n".join(parts) + "\n", rows


# -- the write -----------------------------------------------------------------------------


def render_skeletons(inputs: SkeletonInputs, *, segment: int | None) -> dict[str, Any]:
    """Every file the write produces ({path: bytes or None for a deletion}) and the write manifest, without writing."""

    writer = _Writer(inputs)
    selected = [(number, unit) for number, unit in inputs.units if segment is None or number == segment]
    if segment is not None and not selected:
        raise SocomError(f"segment {segment} has no accepted order plan")
    files: dict[str, bytes | None] = {}
    records: list[dict[str, Any]] = []
    file_rows: list[dict[str, Any]] = []
    for number, unit in selected:
        text, rows = writer.unit_file(number, unit)
        data = text.encode("utf-8")
        files[unit["workspace_path"]] = data
        for row in rows:
            row["path"] = unit["workspace_path"]
        records.extend(rows)
        file_rows.append({"path": unit["workspace_path"], "action": "unit", "unit": unit["unit"], "segment": number,
                          "entries": sum(1 for row in rows if row["kind"] in ("function", "data")), "sha256": hashlib.sha256(data).hexdigest()})
    deleted: list[dict[str, Any]] = []
    if segment is None:
        for path, items in sorted(writer.held.items()):
            text, rows = holding_text(items, inputs)
            data = text.replace("\n", DEFAULT_NEWLINE).encode("utf-8")
            files[path] = data
            for row in rows:
                row["path"] = path
            records.extend(rows)
            file_rows.append({"path": path, "action": "holding", "entries": len(rows), "sha256": hashlib.sha256(data).hexdigest()})
        for path, record in sorted(inputs.files.items()):
            if not record["orphan"]:
                continue
            stays = [body for body in inputs.manifest["bodies"]["definitions"] if body["path"] == path and body["id"] in writer.preamble_bodies]
            data_stays = [row for row in record["data_definitions"] if row["action"] in ("preamble", "judgment")]
            text, newline = read_source(inputs.root / path)
            _prefix, rest = split_blocks(path, text)
            remaining = cut_preamble(rest, writer._cuts(path))
            if stays or data_stays:
                data = (_prefix + remaining).replace("\n", newline).encode("utf-8")
                files[path] = data
                file_rows.append({"path": path, "action": "orphan-kept", "sha256": hashlib.sha256(data).hexdigest()})
                continue
            files[path] = None
            deleted.append({"path": path, "definitions_moved": record["definitions"], "data_moved": len(record["data_definitions"]),
                            "dropped_preamble_lines": len(remaining.splitlines()), "dropped_preamble_sha256": _sha(remaining)})
    flags = Counter(flag["kind"] for row in records for flag in row.get("flags") or [])
    for row in records:
        for inner in row.get("nested") or []:
            flags.update(flag["kind"] for flag in inner.get("flags") or [])
    judgment = judgment_defaults(inputs, writer)
    kinds = Counter(row["kind"] for row in records)
    kinds.update(inner["kind"] for row in records for inner in row.get("nested") or [])
    fences = Counter(row.get("fence") for row in records if row.get("fence"))
    summary = {
        "files_written": sum(1 for value in files.values() if value is not None),
        "unit_files": len(selected),
        "holding_files": sum(1 for row in file_rows if row["action"] == "holding"),
        "orphans_deleted": len(deleted),
        "entries": dict(sorted(kinds.items())),
        "fences": dict(sorted(fences.items())),
        "moves": dict(sorted(Counter(row.get("move") for row in records if row.get("move")).items())),
        "flags": dict(sorted(flags.items())),
        "waiting": dict(sorted(Counter(row["kind"] for row in writer.waiting).items())),
        "order_conflicts": len(writer.conflicts),
        "data_placement": dict(sorted(Counter(row["placement"]["rule"] for row in records if row.get("placement")).items())),
        "data_between_conflicting_statics": sum(1 for row in records if (row.get("placement") or {}).get("between_conflicting_statics")),
        "replaced_data_statements": len(writer.replaced),
        "judgment_defaults": dict(sorted(Counter(row["default"] for row in judgment).items())),
    }
    manifest = {
        "kind": WRITE_KIND,
        "schema_version": WRITE_SCHEMA,
        "selection": {"segment": segment} if segment is not None else {"all": True},
        "inputs": inputs.record(),
        "fence": "/* @socom-skeleton <stub|body> <mangled> */",
        "summary": summary,
        "files": sorted(file_rows, key=lambda row: row["path"]),
        "deleted": deleted,
        "entries": records,
        "judgment": judgment,
        "waiting": sorted(writer.waiting, key=lambda row: (row["kind"], str(row.get("segment")), str(row.get("name")))),
        "order_conflicts": writer.conflicts,
        "replaced_data": writer.replaced,
    }
    manifest["write_sha256"] = _digest(manifest)
    return {"files": files, "manifest": manifest}


def judgment_defaults(inputs: SkeletonInputs, writer: _Writer) -> list[dict[str, Any]]:
    """Every manifest judgment row with the writer's deterministic default, its flag and whether it waits."""

    waiting = {(row["kind"], row.get("artifact") or row.get("body")) for row in writer.waiting}
    rows = []
    for row in inputs.manifest["judgment"]:
        kind = row["kind"]
        key = row.get("artifact") or row.get("body") or row.get("type")
        if kind == "signature-contradiction":
            default, flag, waits = "bd6: the declarator is rewritten to the ELF signature, the body kept (C3 checks it)", "bd6-declarator-rewrite", False
        elif kind in ("copy-only-body", "unowned-body"):
            default, flag, waits = "bd4: held in the module's unbuilt holding file", "bd4-held", False
        elif kind == "unparsed-body":
            default, flag, waits = "bd4: held as text in the module's holding file (its orphan file is removed)", "unparsed-body-held", False
        elif kind == "overload-tie":
            default, flag, waits = "held in the holding file; each candidate row gets a stub", "overload-tie-held", True
        elif kind == "ambiguous-owner":
            default, flag, waits = "held in the holding file; the owning row gets a stub", "ambiguous-owner-held", True
        elif kind == "local-static-owner":
            waits = ("local-static-owner", row.get("artifact")) in waiting
            default = "not written: no defining function of the unit references it" if waits else \
                "declared in the referencing function that best keeps its region's declaration order (the first in source order on a tie)"
            flag = "local-static-owner" if waits else "local-static-owner-hypothesis"
        elif kind == "s1-failure":
            default, flag, waits = ("written inside the first stub (in source order) that takes its address, as a struct "
                                    "with inline members"), "local-class-owner-hypothesis", True
        elif kind == "by-value-undeclared":
            record = "DWARF record: True" in (row.get("detail") or "")
            default = "the .cpp spells the type by name; its definition is the round 3 declaration writer's" + (
                " (from its DWARF record)" if record else " (no record anywhere: a definition would be invented)")
            flag, waits = "by-value-undeclared", not record
        else:
            default, flag, waits = "listed", kind, True
        rows.append({"kind": kind, "key": key, "name": row.get("name"), "unit": row.get("unit"), "segment": row.get("segment"),
                     "default": default, "flag": flag, "waits": waits})
    return rows


def preview_root(root: Path, value: str) -> Path:
    """The preview directory: under build/ (never build/ itself or src/); an existing one must be a previous preview."""

    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    build = (root / "build").resolve()
    if path == build or not path.is_relative_to(build):
        raise SocomError("this round writes skeletons only to a preview directory under build/ (the src/ route is round 3)")
    if path.is_relative_to((root / "src").resolve()):
        raise SocomError("the skeleton preview may not be written under src/")
    if path.exists():
        if not path.is_dir():
            raise SocomError(f"{value} is not a directory")
        marker = path / WRITE_MANIFEST
        contents = [child.name for child in path.iterdir()]
        if contents and not (marker.is_file() and (load_json(marker) or {}).get("kind") == WRITE_KIND):
            raise SocomError(f"{value} is not empty and holds no previous skeleton preview: choose an empty directory")
    return path


def write_skeletons(root: Path, target: Path, rendered: dict[str, Any]) -> dict[str, Any]:
    """Replace the preview: a mirror of src/ with the rendered files, then the write manifest."""

    from .util import atomic_write_bytes, atomic_write_json

    mirror = target / "src"
    if mirror.exists():
        shutil.rmtree(mirror)
    marker = target / WRITE_MANIFEST
    if marker.exists():
        marker.unlink()
    source = root / "src"
    for path in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in rendered["files"]:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    for relative, data in sorted(rendered["files"].items()):
        if data is None:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(destination, data)
    atomic_write_json(marker, rendered["manifest"])
    return {"root": target, "write_sha256": rendered["manifest"]["write_sha256"]}


def tree_digest(target: Path) -> str:
    """SHA-256 over every file of a preview's src/ mirror (path and content digest)."""

    rows = []
    for path in sorted((target / "src").rglob("*"), key=lambda value: value.as_posix()):
        if path.is_file():
            rows.append([path.relative_to(target).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()])
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()
