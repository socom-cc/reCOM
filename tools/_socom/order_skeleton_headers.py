"""Stage 5 phase B round 3a: the header writer (part of ``order skeleton write --all``), preview only.

The declaration manifest (``order skeleton manifest``: ``declarations.classes``
and ``declarations.types``) says which classes the planned rows need, what each
existing class body lacks and where a new body goes.  This writer turns it into
fenced generated regions (BD2: additive) and runs once for the whole tree:

- an existing class body gets one region before its closing brace with the
  missing member declarations: the vtable's own virtuals in slot order (planned
  rows, and the unplanned slot targets declared like them), the other planned
  members in plan order, the in-class rows as in-class stubs, the missing static
  data members, and the nested types placed inside the class;
- a new class body (its key, its direct bases from RTTI or DWARF, the same
  members) goes to its chosen header before the include guard's ``#endif``, or,
  in the anonymous namespace, into its unit's ``.cpp`` before the entries; a
  header that does not exist yet is created with an include guard, and the
  units that define its members include it;
- a type a planned row needs complete (by value) that ``src/`` does not define
  is written from its record: enumerators, or members in offset order (DWARF),
  or an opaque array of its stage 3 size; unproven pieces are flagged.  Enums go
  to the top of their file (they cannot be declared ahead), classes to the
  bottom;
- the class types a file's generated text names but ``src/`` never declares are
  declared ahead in a ``forward`` region at the top of the file;
- the in-class bodies of rows planned out of line are replaced by their
  declarations (the body moves to the ``.cpp``).

Every region is fenced ``/* @socom-skeleton decl <name> */`` ...
``/* @socom-skeleton end <name> */`` (the class or type's mangled qualified
name, or ``forward`` / ``include``).  Header content outside the regions and the
recorded replacements stays byte-identical; the stage 4 blocks are untouched.
A region is regenerable while its text equals its recorded ``region_sha256``,
like a stub (the governed ``src/`` route applies that rule; this round refuses
a source file that already holds regions).
"""

from __future__ import annotations

import hashlib
import os.path
import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any

from .cxx_scan import ClassDef, FileScan, Program, Speller, data_symbols, function_symbol
from .mw_mangle import MangleError, mangle
from .util import SocomError

DECL_FENCE = "/* @socom-skeleton decl {name} */"
END_FENCE = "/* @socom-skeleton end {name} */"
REGION_RE = re.compile(r"^(?P<indent>[ \t]*)/\* @socom-skeleton (?P<kind>decl|end) (?P<name>\S+) \*/[ \t]*$")
FORWARD = "forward"
INCLUDE = "include"
TAIL = 1 << 40  # the offset recorded for a unit file's tail (after its preamble, before its entries)
HEADER_FLAG_KINDS = (
    "unplanned-virtual", "virtual-slot-order", "virtual-slot-unnamed", "key-unproven", "base-access-unproven", "bases-unknown",
    "bases-not-in-body", "type-from-dwarf", "type-from-stage3", "type-unproven", "forward-key-unproven", "in-class-stub",
    "static-member-conflict", "new-header", "header-body-replaced", "inline-dropped", "include-added", "declaration-from-signature",
)
HEADER_WAIT_KINDS = (
    "provider-declaration", "function-local-class", "type-no-record", "type-unplaced", "class-unplaced",
    "declaration-unspelled", "nested-in-unwritten-class",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _component(base: str) -> dict[str, Any]:
    if base.startswith("@unnamed@") and base.endswith("@"):
        return {"unnamed": base[len("@unnamed@") : -1]}
    return {"name": base}


def _chain(text: str) -> tuple[str, ...]:
    return tuple(text.split("::")) if text else ()


def _readable(chain: tuple[str, ...]) -> str:
    return "::".join("(anonymous namespace)" if part.startswith("@unnamed@") else part for part in chain)


def _mangle(symbol: dict[str, Any] | None) -> str | None:
    if symbol is None:
        return None
    try:
        return mangle(symbol)
    except (MangleError, KeyError, TypeError):
        return None


# -- regions in a written file ----------------------------------------------------------------


def parse_regions(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Top-level generated regions of a file (0-based first and last line) and the fence problems.

    A ``decl`` fence opens a region and the ``end`` fence of the same name closes it.
    """

    regions: list[dict[str, Any]] = []
    problems: list[str] = []
    stack: list[dict[str, Any]] = []
    for number, line in enumerate(text.split("\n")):
        match = REGION_RE.match(line)
        if not match:
            continue
        if match.group("kind") == "decl":
            stack.append({"name": match.group("name"), "start": number, "indent": match.group("indent"), "depth": len(stack)})
            continue
        if not stack or stack[-1]["name"] != match.group("name"):
            problems.append(f"line {number + 1}: end fence {match.group('name')} closes no open region")
            continue
        row = stack.pop()
        row["end"] = number
        if row["depth"] == 0:
            regions.append(row)
    problems.extend(f"line {row['start'] + 1}: region {row['name']} is never closed" for row in stack)
    return regions, problems


def strip_regions(text: str, regions: list[dict[str, Any]], splits: set[int]) -> str:
    """The text without its top-level regions (whole lines); a region whose index is in ``splits`` had split a line."""

    lines = text.split("\n")
    out: list[str] = []
    starts = {row["start"]: (number, row) for number, row in enumerate(regions)}
    index = 0
    join = False
    while index < len(lines):
        if index in starts:
            number, row = starts[index]
            index = row["end"] + 1
            join = number in splits
            continue
        if join and out:
            out[-1] += lines[index]
        else:
            out.append(lines[index])
        join = False
        index += 1
    return "\n".join(out)


def in_class_declaration(scan: FileScan, definition: Any) -> tuple[str, bool]:
    """The declaration an in-class body leaves: its head to the declarator's end and ``;`` (``inline`` dropped)."""

    from .order_skeleton_write import _head_end

    head = scan.text[definition.start : definition.start + _head_end(definition.tokens, definition.start)].rstrip()
    stripped = re.sub(r"(^|(?<=\s))inline\s+", "", head, count=1)
    return stripped + ";", stripped != head


def replacement_declaration(program: Program, scan: FileScan, definition: Any, signature: dict[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    """What an in-class body of a row planned out of line leaves in its class, and its flags.

    Its own head (to the declarator's end, ``inline`` dropped) while that agrees
    with the row's signature, which the ``.cpp`` head is written from; where its
    return type or ``static`` contradicts the signature, the signature's
    declaration (the two would not compile together).
    """

    declaration, dropped = in_class_declaration(scan, definition)
    flags: list[dict[str, Any]] = []
    if dropped:
        flags.append({"kind": "inline-dropped", "detail": "the declaration drops inline: the definition is out of line"})
    if not signature or not signature.get("declaration"):
        return declaration, flags
    parsed = function_symbol(program, definition.tokens, definition.scope, scan.tag, klass=definition.in_class)
    try:
        returns = Speller(program, [()]).type(parsed.returns) if parsed.returns is not None else None
    except (MangleError, KeyError):
        returns = "?"
    want = signature["return"]["text"]
    static = "static" in parsed.specifiers
    if (want is not None and returns != want) or static != (signature["member"]["kind"] == "static"):
        flags.append({"kind": "declaration-from-signature", "detail": f"{declaration} contradicts the signature's "
                      f"{signature['declaration']} ({signature['return']['source']} return): the signature's is written"})
        return signature["declaration"], flags
    return declaration, flags


def class_member_names(program: Program, scan: FileScan, klass: ClassDef) -> list[tuple[str, int, str]]:
    """(mangled name, line, kind) of every function and static data member a class body declares or defines."""

    rows = []
    for member in klass.members:
        if hasattr(member, "body_start"):
            name = _mangle(function_symbol(program, member.tokens, member.scope, scan.tag, klass=klass.chain).symbol)
            if name:
                rows.append((name, member.line, "definition"))
            continue
        texts = [token.text for token in member.tokens]
        if "(" in texts and not member.brace_init:
            parsed = function_symbol(program, member.tokens, member.scope, scan.tag, klass=klass.chain)
            if parsed.symbol is not None:
                name = _mangle(parsed.symbol)
                if name:
                    rows.append((name, member.line, "function"))
                continue
        for parsed in data_symbols(program, member.tokens, member.scope, scan.tag):
            if parsed.symbol is None or "static" not in parsed.specifiers:
                continue
            name = _mangle(parsed.symbol)
            if name:
                rows.append((name, member.line, "static-data"))
    return rows


def _insert(text: str, offset: int, lines: list[str]) -> tuple[str, bool]:
    """Region lines inserted at ``offset``: whole lines at a line start, else the line is split (recorded)."""

    if offset == 0 or text[offset - 1] == "\n":
        return "".join(line + "\n" for line in lines), False
    return "\n" + "\n".join(lines) + ("\n" if offset < len(text) else ""), True


def _included(path: str, scan: FileScan | None) -> set[str]:
    """The files a source file includes directly, as tree paths (its own directory, or from src/)."""

    directory = PurePosixPath(path).parent.as_posix()
    found = set()
    for included in (scan.includes if scan is not None else []):
        found.add(os.path.normpath(f"{directory}/{included}").replace("\\", "/"))
        found.add(f"src/{included}")
    return found


def _top_offset(scan: FileScan) -> int:
    """After the leading preprocessor lines (include guard, includes) that precede the first declaration."""

    offset = 0
    for token in scan.tokens:
        if token.kind != "pp" or not re.match(r"#\s*(?:include|define|ifndef|pragma)\b", token.text):
            break
        end = scan.text.find("\n", token.end)
        offset = len(scan.text) if end < 0 else end + 1
    return offset


def _bottom_offset(scan: FileScan) -> int:
    """Before the include guard's closing ``#endif`` (the file's last token), else the end of the file."""

    tokens = scan.tokens
    if tokens and tokens[-1].kind == "pp" and re.match(r"#\s*endif\b", tokens[-1].text):
        first = next((token for token in tokens if token.kind == "pp"), None)
        if first is not None and re.match(r"#\s*(?:ifndef|if\s+!\s*defined)\b", first.text):
            return scan.text.rfind("\n", 0, tokens[-1].start) + 1
    return len(scan.text)


def apply_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    out = []
    cursor = 0
    for start, end, insert in sorted(edits, key=lambda row: (row[0], row[1])):
        if start < cursor:
            raise SocomError("two generated edits overlap")
        out.append(text[cursor:start])
        out.append(insert)
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


# -- the writer ------------------------------------------------------------------------------


class HeaderWriter:
    """Every generated region and replacement of the tree; ``render`` gives header texts and unit-file additions."""

    def __init__(self, inputs: Any, *, newline: str) -> None:
        self.inputs = inputs
        self.program: Program = inputs.program
        self.newline = newline
        declarations = inputs.manifest["declarations"]
        self.classes: dict[tuple[str, ...], dict[str, Any]] = {tuple(row["chain"]): row for row in declarations["classes"]}
        self.types: dict[tuple[str, ...], dict[str, Any]] = {tuple(row["chain"]): row for row in declarations["types"]}
        self.unit_paths = {unit["workspace_path"]: unit for _number, unit in inputs.units}
        self.unit_of_name = {unit["unit"]: unit for _number, unit in inputs.units}
        self.waiting: list[dict[str, Any]] = []
        self.files: list[dict[str, Any]] = []  # header and new-header rows
        self.regions: list[dict[str, Any]] = []
        self.replacements: list[dict[str, Any]] = []
        self.bodies: dict[tuple[str, ...], tuple[str, ClassDef]] = {}
        self.nested: dict[tuple[str, ...], list[tuple[str, tuple[str, ...]]]] = defaultdict(list)
        self.top: dict[str, list[tuple[str, ...]]] = defaultdict(list)  # path -> enums at the top
        self.bottom: dict[str, list[tuple[str, ...]]] = defaultdict(list)  # path -> classes and other types at the bottom
        self.new_headers: dict[str, set[str]] = defaultdict(set)  # header -> the units that include it
        self.written: set[tuple[str, ...]] = set()
        self.skipped: set[tuple[str, ...]] = set()
        self.homes: dict[tuple[str, ...], str] = {}
        self.declared_in = self._declared_in()
        self._mentions: set[str] = set()
        self._nested_rows: list[dict[str, Any]] = []
        self._plan()

    # -- planning ----------------------------------------------------------------------------

    def _local(self, record: dict[str, Any]) -> bool:
        for member in record["members_to_add"]:
            structured = (self.inputs.signatures.get(member["artifact"]) or {}).get("structured") or {}
            if any("local" in component for component in structured.get("scope") or []):
                return True
        return False

    def _plan(self) -> None:
        for chain, record in sorted(self.classes.items()):
            if chain[0] == "std":
                self.skipped.add(chain)
                self.waiting.append({"kind": "provider-declaration", "type": record["class"],
                                     "detail": "std is the MSL provider's namespace: its declarations come from the MSL headers"})
            elif self._local(record):
                self.skipped.add(chain)
                self.waiting.append({"kind": "function-local-class", "type": record["class"],
                                     "detail": "a function-local class: the .cpp writer declares it inside its owner's stub"})
            elif record["body"] and not self._writable(record["body"]["path"]):
                self.skipped.add(chain)
                self.waiting.append({"kind": "class-unplaced", "type": record["class"],
                                     "detail": f"its body is in {record['body']['path']}, which is neither a header nor a planned unit file"})
            elif record["body"]:
                body = record["body"]
                klass = next((row for row in self.inputs.scans[body["path"]].classes if row.line == body["line"] and row.chain == chain), None)
                if klass is None:
                    raise SocomError(f"{body['path']}:{body['line']}: the body of {record['class']} is not where the manifest recorded it")
                self.bodies[chain] = (body["path"], klass)
        for chain, record in sorted(self.classes.items()):
            if chain not in self.skipped and not record["body"]:
                self._place(chain, "class", (record.get("header") or {}).get("path"))
        for chain, row in sorted(self.types.items()):
            if chain in self.classes or row.get("provider") or row["src"] not in ("undeclared", "forward-only"):
                continue
            if row.get("definition") is None:
                decision = self.inputs.decision("type-no-record", row.get("mangled")) if row["need"] == "full" and row["by_value"] else None
                if decision is not None:
                    # Decided (order skeleton decide --type): the lease holder's definition text, written verbatim.
                    text = decision["value"].replace("\r\n", "\n").replace("\r", "\n").strip()
                    if not re.match(rf"^(?:enum|struct|class|union)\s+{re.escape(chain[-1])}\b", text):
                        raise SocomError(f"the decided definition of {_readable(chain)} does not define {chain[-1]}: {text[:60]!r}")
                    self.types[chain] = {**row, "definition": {"kind": "enum" if text.startswith("enum") else "decided",
                                                               "source": "decision", "text": text, "members": [], "decision": decision}}
                    self._place(chain, "type", (row.get("placement") or {}).get("path"))
                    continue
                if row["need"] == "full" and row["by_value"]:
                    self.waiting.append({"kind": "type-no-record", "type": _readable(chain), "units": row["units"],
                                         "detail": f"by value as {' and '.join(row['by_value'])}; {row['record']['basis']}: "
                                                   "a definition would be invented"})
                continue
            self._place(chain, "type", (row.get("placement") or {}).get("path"))

    def _host(self, chain: tuple[str, ...]) -> bool:
        """Whether this writer writes or extends the class body (so nested content can go into it)."""

        if chain in self.skipped:
            return False
        if chain in self.bodies or chain in self.written:
            return True
        bodies = [(path, klass) for path, klass in self.program.class_defs.get(chain) or [] if not klass.template and self._writable(path)]
        if bodies and chain not in self.classes:
            self.bodies[chain] = sorted(bodies, key=lambda item: (not item[0].endswith((".h", ".hpp")), item[0], item[1].line))[0]
            return True
        return False

    def _writable(self, path: str) -> bool:
        """A header, or a planned unit file (whose preamble the write keeps); never an orphan or holding source."""

        return path.endswith((".h", ".hpp", ".inc")) or path in self.unit_paths

    def _enum(self, chain: tuple[str, ...]) -> bool:
        return chain not in self.classes and ((self.types.get(chain) or {}).get("definition") or {}).get("kind") == "enum"

    def _place(self, chain: tuple[str, ...], kind: str, path: str | None) -> None:
        if chain in self.written:
            return
        parent = chain[:-1]
        unplaced = "class-unplaced" if kind == "class" else "type-unplaced"
        if parent and not self.program.is_namespace(parent):
            if parent in self.classes and parent not in self.skipped and not self.classes[parent]["body"]:
                self._place(parent, "class", (self.classes[parent].get("header") or {}).get("path"))
            if not self._host(parent):
                self.waiting.append({"kind": "nested-in-unwritten-class", "type": _readable(chain),
                                     "detail": f"its enclosing class {_readable(parent)} has no body this writer can extend"})
                return
            self.nested[parent].append((kind, chain))
            self.written.add(chain)
            return
        if not path or path.startswith("<"):
            self.waiting.append({"kind": unplaced, "type": _readable(chain), "detail": f"no header for it ({path or 'none'})"})
            return
        code = path.endswith((".cpp", ".c", ".cc"))
        if code and path not in self.unit_paths:
            self.waiting.append({"kind": unplaced, "type": _readable(chain), "detail": f"{path} is not a planned unit file"})
            return
        if not code and not (self.inputs.source_root / path).is_file():
            users = set((self.classes.get(chain) or {}).get("units") or {}) | set((self.types.get(chain) or {}).get("units") or [])
            self.new_headers[path] |= users
        (self.top if self._enum(chain) else self.bottom)[path].append(chain)
        self.homes[chain] = path
        self.written.add(chain)

    def _home(self, chain: tuple[str, ...]) -> str | None:
        """The file that defines a class or type in the written tree (a nested one: its enclosing class's)."""

        if chain in self.homes:
            return self.homes[chain]
        if chain in self.bodies:
            return self.bodies[chain][0]
        if chain in self.written and len(chain) > 1:
            return self._home(chain[:-1])
        return self.declared_in.get(chain)

    def _declared_in(self) -> dict[tuple[str, ...], str]:
        """Where src/ defines each class, enum and typedef (headers first)."""

        from .cxx_scan import scope_chain, typedef_names

        found: dict[tuple[str, ...], str] = {}
        for path, scan in sorted(self.inputs.scans.items(), key=lambda item: (not item[0].endswith((".h", ".hpp")), item[0])):
            for klass in scan.classes:
                if klass.chain and not klass.template:
                    found.setdefault(tuple(klass.chain), path)
            for chain in scan.enums:
                found.setdefault(tuple(chain), path)
            for row in scan.typedefs:
                for name in typedef_names(row):
                    found.setdefault(scope_chain(row.scope, scan.tag) + (name,), path)
        return found

    # -- text ----------------------------------------------------------------------------------

    def _speller(self, chain: tuple[str, ...]) -> Speller:
        unnamed = chain[0][len("@unnamed@") : -1] if chain and chain[0].startswith("@unnamed@") else None
        return Speller(self.program, [chain[:index] for index in range(len(chain), -1, -1)], inside_unnamed=unnamed)

    def _base_list(self, chain: tuple[str, ...], record: dict[str, Any] | None, definition: dict[str, Any] | None,
                   flags: list[dict[str, Any]]) -> str:
        rows: list[dict[str, Any]] = []
        source = None
        if record is not None and record["bases"]["source"] in ("rtti", "dwarf") and record["bases"]["bases"]:
            source = record["bases"]["source"]
            rows = [row for row in record["bases"]["bases"] if row.get("direct", True) and row.get("class")]
        elif definition is not None and definition.get("bases"):
            source = "dwarf"
            rows = definition["bases"]
        elif record is not None and record["bases"]["source"] == "unknown":
            flags.append({"kind": "bases-unknown", "detail": record["bases"].get("note") or "no RTTI and no DWARF record"})
        if not rows:
            return ""
        speller = self._speller(chain[:-1])
        parts = []
        for row in sorted(rows, key=lambda item: item.get("offset") or 0):
            access = row.get("access")
            if access is None:
                access = "public"
                flags.append({"kind": "base-access-unproven", "detail": f"{row['class']} written public ({source} gives no access)"})
            text = speller.qualified(row.get("components") or [_component(part) for part in _chain(row["class"])])
            parts.append(("virtual " if row.get("virtual") else "") + f"{access} {text}")
        return " : " + ", ".join(parts)

    def _record_flags(self, definition: dict[str, Any], basis: str, flags: list[dict[str, Any]], what: str) -> None:
        kind = "type-from-dwarf" if definition["source"] == "dwarf" else "type-from-stage3"
        flags.append({"kind": kind, "detail": f"{what} from its {definition['source']} record ({basis}, {definition['size']} bytes)"})
        for problem in definition.get("unproven") or []:
            flags.append({"kind": "type-unproven", "detail": problem})
        for member in definition.get("members") or []:
            self._mentions.update(member.get("mentions") or [])

    def _definition_lines(self, chain: tuple[str, ...], flags: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
        """(lines, function members, static data members) of a new class body or a type definition, unwrapped."""

        record = self.classes.get(chain)
        row = self.types.get(chain) or {}
        definition = row.get("definition")
        name = chain[-1]
        if record is None and definition.get("source") == "decision":
            flags.append(self.inputs.decided_flag(definition["decision"]))
            return definition["text"].split("\n"), [], []
        if record is None:
            self._record_flags(definition, row["record"]["basis"], flags, f"the {definition['kind'] or 'type'}")
            if definition["kind"] == "enum":
                values = definition["enumerators"]
                body = [f"\t{item[0]} = {item[1]}" + ("," if index + 1 < len(values) else "") for index, item in enumerate(values)]
                return [f"enum {name}", "{", *body, "};"], [], []
            key = definition.get("key") or "struct"
            if definition["source"] == "stage3":
                flags.append({"kind": "type-unproven", "detail": "its kind and members are unknown: a struct holding an opaque byte array"})
            head = f"{key} {name}" + self._base_list(chain, None, definition, flags)
            return [head, "{", *(["public:"] if key == "class" else []), *self._data_member_lines(definition), "};"], [], []
        key = record["key"]
        if record["key_source"] == "default":
            flags.append({"kind": "key-unproven", "detail": "neither src/ nor DWARF gives the class key: written class"})
        lines = [f"{key} {name}" + self._base_list(chain, record, definition, flags), "{", *(["public:"] if key == "class" else [])]
        if definition is not None and row.get("by_value") and definition.get("source") in ("dwarf", "stage3"):
            self._record_flags(definition, row["record"]["basis"], flags, "the data members of a by-value class")
            lines.extend(self._data_member_lines(definition))
        inner, members, statics = self._member_lines(chain, record, flags)
        return lines + inner + ["};"], members, statics

    @staticmethod
    def _data_member_lines(definition: dict[str, Any]) -> list[str]:
        if definition["source"] == "stage3":
            return [f"\tunsigned char _opaque[{definition['size']}];"]
        lines = []
        for member in definition.get("members") or []:
            if member["text"] is not None:
                lines.append(f"\t{member['text']};")
            elif member.get("placeholder_size"):
                valid = member["name"] and re.fullmatch(r"[A-Za-z_]\w*", member["name"])
                name = member["name"] if valid else f"_unspelled_{member['offset']:x}"
                lines.append(f"\tunsigned char {name}[{member['placeholder_size']}];")
        return lines

    def _member_lines(self, chain: tuple[str, ...], record: dict[str, Any], flags: list[dict[str, Any]]) -> tuple[list[str], list[str], list[str]]:
        """Indented members (nested types first), and the function and static member names they declare."""

        lines = self._nested_lines(chain, flags)
        names: list[str] = []
        statics: list[str] = []
        to_add = {row["name"]: row for row in record["members_to_add"]}
        written: set[str] = set()
        vtable = record.get("vtable") or {}
        virtuals = sorted(enumerate(vtable.get("declare_virtual") or []),
                          key=lambda item: (item[1]["group"], item[1]["slot"] if item[1]["slot"] is not None else 1 << 20, item[0]))
        for _index, row in virtuals:
            member = row["member"]
            planned = to_add.get(member)
            if row.get("declared") or member in written or (planned is not None and planned.get("in_class")):
                continue
            text = planned["declaration"] if planned is not None else row.get("declaration")
            if not text:
                self.waiting.append({"kind": "declaration-unspelled", "type": record["class"], "name": member,
                                     "detail": "a vtable slot's member whose declaration cannot be spelled"})
                continue
            if planned is None:
                flags.append({"kind": "unplanned-virtual", "detail": f"{member} (slot {row['slot']}): declared to keep the slot order"})
            self._mentions.update((planned or row).get("mentions") or [])
            lines.append("\t" + text)
            names.append(member)
            written.add(member)
        unnamed = vtable.get("unnamed_new_slots") or []
        if unnamed:
            flags.append({"kind": "virtual-slot-unnamed", "detail": f"{len(unnamed)} new slot(s) name no member: "
                          + ", ".join(f"{row['slot']} ({row['kind']})" for row in unnamed[:4])})
        for row in record["members_to_add"]:
            member = row["name"]
            if member in written:
                continue
            if not row.get("declaration"):
                self.waiting.append({"kind": "declaration-unspelled", "type": record["class"], "name": member,
                                     "detail": "the planned member has no declaration text"})
                continue
            self._mentions.update(row.get("mentions") or [])
            if row.get("in_class"):
                lines.extend(["\t" + row["declaration"].rstrip(";").rstrip(), "\t{", "\t}"])
                flags.append({"kind": "in-class-stub", "detail": f"{member}: defined in its class body (BD8)"})
            else:
                lines.append("\t" + row["declaration"])
            names.append(member)
            written.add(member)
        seen: dict[str, str] = {}
        for row in record["static_data_members"]:
            if row["declared"]:
                continue
            if row["name"] in seen:
                if row.get("declaration") != seen[row["name"]]:
                    flags.append({"kind": "static-member-conflict",
                                  "detail": f"{row['name']}: {row.get('declaration')} against {seen[row['name']]} (the first is kept)"})
                continue
            if not row.get("declaration"):
                self.waiting.append({"kind": "declaration-unspelled", "type": record["class"], "name": row["name"],
                                     "detail": "the static data member's type cannot be spelled"})
                continue
            seen[row["name"]] = row["declaration"]
            self._mentions.update(row.get("mentions") or [])
            lines.append("\t" + self._static_text(row))
            statics.append(row["name"])
        return lines, names, statics

    def _static_text(self, row: dict[str, Any]) -> str:
        """A static data member's declaration; a ``.rodata`` row's object is const, as its definition is."""

        from .cxx_scan import tokenize
        from .order_skeleton_write import _top_level_const

        datum = self.inputs.data.get(row["artifact"]) or {}
        if not datum.get("const") or not datum.get("declaration_type"):
            return row["declaration"]
        structured = datum["structured"]
        variable = structured["name"]["text"] if structured.get("kind") == "data" else None
        tag = PurePosixPath((self.unit_of_name.get(datum["unit"]) or {}).get("workspace_path") or "").name.replace(".", "_")
        tokens, _comments = tokenize(datum["declaration_type"] + ";")
        parsed = data_symbols(self.program, [token for token in tokens if token.text != ";"], (), tag)
        if len(parsed) != 1 or parsed[0].type is None or parsed[0].name != variable:
            return row["declaration"]
        try:
            return f"static {Speller(self.program, [()]).type(_top_level_const(parsed[0].type), variable)};"
        except (MangleError, KeyError):
            return row["declaration"]

    def _nested_lines(self, chain: tuple[str, ...], flags: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for inner in self._forward_candidates(self._class_mentions(chain)):
            if inner[:-1] == chain and inner not in self.written:
                lines.append(f"\t{self._forward_key(inner, flags)} {inner[-1]};")
        items = self.nested.get(chain, [])
        enums = [chain_ for kind, chain_ in items if self._enum(chain_)]
        others = self._sorted([chain_ for kind, chain_ in items if chain_ not in enums])
        for inner in sorted(enums) + others:
            sub_flags: list[dict[str, Any]] = []
            body, members, statics = self._definition_lines(inner, sub_flags)
            lines.extend("\t" + line for line in body)
            self._nested_rows.append({"class": _readable(inner), "chain": list(inner), "kind": "class" if inner in self.classes else "type",
                                      "members": members, "static_members": statics, "flags": sub_flags})
        return lines

    def _class_mentions(self, chain: tuple[str, ...]) -> set[str]:
        found: set[str] = set()
        record = self.classes.get(chain)
        if record is not None:
            for row in record["members_to_add"] + record["static_data_members"] + ((record.get("vtable") or {}).get("declare_virtual") or []):
                found.update(row.get("mentions") or [])
        return found

    def _sorted(self, chains: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
        """Definitions after their in-group bases and member types (otherwise by name)."""

        group = set(chains)
        out: list[tuple[str, ...]] = []
        state: set[tuple[str, ...]] = set()

        def deps(chain: tuple[str, ...]) -> list[tuple[str, ...]]:
            found: set[tuple[str, ...]] = set()
            record = self.classes.get(chain)
            if record is not None:
                found |= {_chain(row["class"]) for row in record["bases"]["bases"] if row.get("class")}
            definition = (self.types.get(chain) or {}).get("definition") or {}
            found |= {_chain(row["class"]) for row in definition.get("bases") or []}
            for member in definition.get("members") or []:
                found |= {_chain(name) for name in member.get("mentions") or []}
            return sorted((found & group) - {chain})

        def visit(chain: tuple[str, ...]) -> None:
            if chain in state:
                return
            state.add(chain)
            for dep in deps(chain):
                visit(dep)
            out.append(chain)

        for chain in sorted(group, key=lambda value: "::".join(value)):
            visit(chain)
        return out

    def _forward_key(self, chain: tuple[str, ...], flags: list[dict[str, Any]]) -> str:
        record = self.classes.get(chain)
        if record is not None and record["key_source"] != "default":
            return record["key"]
        defs = [klass for _path, klass in self.program.class_defs.get(chain) or [] if not klass.template]
        if defs:
            return defs[0].key
        key = (self.types.get(chain) or {}).get("key")
        if key in ("class", "struct", "union"):
            return key
        flags.append({"kind": "forward-key-unproven", "detail": f"{_readable(chain)} declared class (no record gives its key)"})
        return "class"

    def _forward_candidates(self, names: set[str]) -> list[tuple[str, ...]]:
        """Class types to declare ahead: named, never declared in src/, not provider types, not enums."""

        found = []
        for name in sorted(names):
            chain = _chain(name)
            if not chain or chain[0] == "std" or chain in self.skipped:
                continue
            if self.program.kind_of(chain) & {"class", "template", "enum", "typedef", "forward", "namespace"}:
                continue
            row = self.types.get(chain) or {}
            if self._enum(chain) or row.get("key") == "enum" or (row.get("record") or {}).get("kind") == "enum":
                continue
            found.append(chain)
        return found

    # -- regions -----------------------------------------------------------------------------

    @staticmethod
    def _wrap(scope: tuple[str, ...], lines: list[str]) -> list[str]:
        """Reopen a scope's namespaces around top-level lines (the anonymous one as ``namespace {``)."""

        opening = ["namespace {" if part.startswith("@unnamed@") else f"namespace {part} {{" for part in scope]
        return [*opening, *lines, *(["}"] * len(opening))]

    def _region(self, path: str, name: str, kind: str, lines: list[str], *, offset: int, sequence: int, indent: str = "",
                chain: tuple[str, ...] | None = None, members: list[str] | None = None, statics: list[str] | None = None,
                flags: list[dict[str, Any]] | None = None, nested: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        text = [indent + DECL_FENCE.format(name=name), *lines, indent + END_FENCE.format(name=name)]
        row = {
            "path": path, "name": name, "kind": kind, "class": _readable(chain) if chain else None, "chain": list(chain) if chain else None,
            "members": members or [], "static_members": statics or [], "nested": nested or [], "flags": flags or [],
            "region_sha256": _sha("\n".join(text)), "lines": len(text), "offset": offset, "sequence": sequence, "split": False,
            "text": text,
        }
        self.regions.append(row)
        return row

    def _forward_region(self, path: str, names: set[str], *, offset: int, sequence: int,
                        visible: set[str] | None = None) -> dict[str, Any] | None:
        """Forward declarations of the named class types src/ never declares; with ``visible`` (a unit file), also of
        the classes src/ defines in headers the file does not include."""

        flags: list[dict[str, Any]] = []
        groups: dict[tuple[str, ...], set[str]] = defaultdict(set)
        anonymous = "@unnamed@" + PurePosixPath(path).name.replace(".", "_") + "@" if path in self.unit_paths else None
        chains = self._forward_candidates(names)
        if visible is not None:
            for name in sorted(names):
                chain = _chain(name)
                kinds = self.program.kind_of(chain)
                home = self._home(chain)
                if (chain and chain[0] != "std" and "class" in kinds and not kinds & {"template", "typedef", "enum"}
                        and home is not None and home not in visible and home != path and chain not in chains):
                    chains.append(chain)
        for chain in sorted(chains):
            parent = chain[:-1]
            if parent and not self.program.is_namespace(parent):
                continue  # nested: only its enclosing class can declare it
            if parent and parent[0].startswith("@unnamed@") and parent[0] != anonymous:
                continue
            groups[parent].add(f"{self._forward_key(chain, flags)} {chain[-1]};")
        lines: list[str] = []
        for parent in sorted(groups, key=lambda value: "::".join(value)):
            body = sorted(groups[parent], key=lambda text: text.split(" ", 1)[1])
            lines.extend(self._wrap(parent, body))
        if not lines:
            return None
        return self._region(path, FORWARD, "forward", lines, offset=offset, sequence=sequence, flags=flags)

    def _definition_region(self, path: str, chain: tuple[str, ...], *, offset: int, sequence: int) -> dict[str, Any]:
        flags: list[dict[str, Any]] = []
        self._nested_rows = []
        body, members, statics = self._definition_lines(chain, flags)
        record = self.classes.get(chain)
        name = (record or self.types[chain])["mangled"]
        return self._region(path, name, "class" if record is not None else "type", self._wrap(chain[:-1], body), offset=offset,
                            sequence=sequence, chain=chain, members=members, statics=statics, flags=flags, nested=list(self._nested_rows))

    def _members_region(self, path: str, chain: tuple[str, ...], scan: FileScan, klass: ClassDef) -> dict[str, Any] | None:
        record = self.classes.get(chain)
        flags: list[dict[str, Any]] = []
        self._nested_rows = []
        indent = self._indent(scan, klass)
        if record is not None:
            inner, members, statics = self._member_lines(chain, record, flags)
            self._slot_order(record, scan, klass, flags)
            direct = [row["class"] for row in record["bases"]["bases"] if row.get("direct", True) and row.get("class")]
            if direct and not klass.bases.strip():
                flags.append({"kind": "bases-not-in-body", "detail": f"the body names no base; {record['bases']['source']} gives "
                              + ", ".join(direct) + " (the class head is not regenerated, BD2)"})
        else:
            inner, members, statics = self._nested_lines(chain, flags), [], []
        if not inner:
            return None
        lines = ["public:", *((indent + line[1:]) if line.startswith("\t") else line for line in inner)]
        name = record["mangled"] if record is not None else "::".join(chain)
        close = klass.end - 1
        line_start = scan.text.rfind("\n", 0, close) + 1
        offset = line_start if not scan.text[line_start:close].strip() else close
        return self._region(path, name, "members", lines, offset=offset, sequence=0, indent=indent, chain=chain, members=members,
                            statics=statics, flags=flags, nested=list(self._nested_rows))

    @staticmethod
    def _indent(scan: FileScan, klass: ClassDef) -> str:
        for member in klass.members:
            line_start = scan.text.rfind("\n", 0, member.start) + 1
            prefix = scan.text[line_start : member.start]
            if prefix and not prefix.strip():
                return prefix
        return "\t"

    def _slot_order(self, record: dict[str, Any], scan: FileScan, klass: ClassDef, flags: list[dict[str, Any]]) -> None:
        """Flag a body whose declared new virtuals, followed by the region's, do not give the vtable's slot order."""

        new = {row["member"]: row["slot"] for row in (record.get("vtable") or {}).get("declare_virtual") or []
               if row.get("new") and row["slot"] is not None}
        if not new:
            return
        lines = {name: line for name, line, _kind in class_member_names(self.program, scan, klass)}
        declared = [name for _line, name in sorted((lines[name], name) for name in new if name in lines)]
        added = [name for _slot, name in sorted((slot, name) for name, slot in new.items() if name not in lines)]
        if declared + added != sorted(new, key=lambda name: new[name]):
            flags.append({"kind": "virtual-slot-order", "detail": "the body's virtual declarations, then the region's, do not follow "
                          "the vtable's slot order (existing declarations are not moved, BD2)"})

    # -- files -------------------------------------------------------------------------------

    def render(self) -> dict[str, Any]:
        """{"headers": {path: {prefix, text, newline, action}}, "units": {path: {"inserts": [(offset, text)], "tail": text}}}."""

        by_path: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        for chain, (path, _klass) in self.bodies.items():
            by_path[path].append(chain)
        moved = {body["path"] for body in self.inputs.manifest["bodies"]["definitions"] if body["action"] == "move-out-of-line"}
        paths = sorted(set(by_path) | set(self.top) | set(self.bottom) | set(self.new_headers) | moved)
        includes = self._includes()
        headers: dict[str, dict[str, Any]] = {}
        units: dict[str, dict[str, Any]] = {}
        for path in sorted(set(paths) | set(includes) | set(self.unit_paths)):
            if path in self.unit_paths:
                units[path] = self._unit(path, by_path.get(path, []), includes.get(path, {}))
            else:
                headers[path] = self._header(path, by_path.get(path, []))
        self.regions.sort(key=lambda row: (row["path"], row["offset"], row["sequence"]))
        for row in self.regions:
            row.pop("text", None)
        return {"headers": headers, "units": units}

    def _includes(self) -> dict[str, dict[str, str]]:
        """Per unit file: the headers it does not include yet that define what its rows need ({header: why}).

        That is every class its rows are members of, and every type its rows need
        complete (by value, or as a scope): the header holding the class body
        (src/'s, or the one this writer places it in), the enum or the typedef.
        """

        wanted: dict[str, dict[str, str]] = defaultdict(dict)

        def need(unit_name: str, chain: tuple[str, ...], why: str) -> None:
            unit = self.unit_of_name.get(unit_name)
            home = self._home(chain)
            if unit is None or home is None or not home.endswith((".h", ".hpp", ".inc")) or chain in self.skipped:
                return
            wanted[unit["workspace_path"]].setdefault(home, why)

        for chain, record in sorted(self.classes.items()):
            for unit_name in sorted(record.get("units") or {}):
                need(unit_name, chain, f"it defines members of {record['class']}")
        for chain, row in sorted(self.types.items()):
            if row["need"] == "full" and not row.get("provider"):
                for unit_name in row["units"]:
                    need(unit_name, chain, f"it needs {_readable(chain)} complete")
        result: dict[str, dict[str, str]] = {}
        for path, headers in wanted.items():
            present = _included(path, self.inputs.scans.get(path))
            rows = {header: why for header, why in headers.items() if header not in present and header != path}
            if rows:
                result[path] = rows
        return result

    @staticmethod
    def _include_line(header: str, unit_path: str) -> str:
        """The tree's two conventions: a bare name in the unit's directory, else the path from src/."""

        if PurePosixPath(header).parent == PurePosixPath(unit_path).parent:
            return f'#include "{PurePosixPath(header).name}"'
        return f'#include "{header[len("src/"):] if header.startswith("src/") else header}"'

    def _header(self, path: str, chains: list[tuple[str, ...]]) -> dict[str, Any]:
        from .order_skeleton_write import read_source, split_blocks

        exists = (self.inputs.source_root / path).is_file()
        if exists:
            raw, newline = read_source(self.inputs.source_root / path)
            prefix, rest = split_blocks(path, raw)
            scan = self.inputs.scans[path]
            if scan.text != rest:
                raise SocomError(f"{path}: the authored content differs from the manifest's scan")
            if parse_regions(rest)[0]:
                raise SocomError(f"{path} already holds generated declaration regions: rewriting them is the governed src/ route")
        else:
            prefix, rest, newline, scan = "", "", self.newline, None
        self._mentions = set()
        edits: list[tuple[int, int, str]] = []
        for chain in sorted(chains, key=lambda value: self.bodies[value][1].start):
            row = self._members_region(path, chain, scan, self.bodies[chain][1])
            if row is not None:
                text, row["split"] = _insert(rest, row["offset"], row["text"])
                edits.append((row["offset"], row["offset"], text))
        if exists:
            for body in self.inputs.manifest["bodies"]["definitions"]:
                if body["action"] == "move-out-of-line" and body["path"] == path:
                    edits.append(self._replacement(path, scan, body))
        top_offset = _top_offset(scan) if exists else 0
        bottom_offset = _bottom_offset(scan) if exists else 0
        # Sequences order regions that share an insertion point (an empty header: the top's before the bottom's).
        bottom = [self._definition_region(path, chain, offset=bottom_offset, sequence=1000 + index)
                  for index, chain in enumerate(self._sorted(self.bottom.get(path, [])), start=1)]
        top = [self._definition_region(path, chain, offset=top_offset, sequence=index)
               for index, chain in enumerate(sorted(self.top.get(path, [])), start=1)]
        forward = self._forward_region(path, set(self._mentions), offset=top_offset, sequence=0)
        top = ([forward] if forward else []) + top
        if exists:
            for rows, offset in ((top, top_offset), (bottom, bottom_offset)):
                if rows:
                    text, split = _insert(rest, offset, [line for row in rows for line in row["text"]])
                    for row in rows:
                        row["split"] = split
                    edits.append((offset, offset, text))
            out = apply_edits(rest, edits)
            action = "header"
        else:
            guard = re.sub(r"\W", "_", PurePosixPath(path).name).upper()
            out = "\n".join([f"#ifndef {guard}", f"#define {guard}", *(line for row in top + bottom for line in row["text"]), "#endif"]) + "\n"
            action = "new-header"
        record = {"path": path, "action": action, "regions": sum(1 for row in self.regions if row["path"] == path),
                  "replacements": sum(1 for row in self.replacements if row["path"] == path)}
        if action == "new-header":
            record["guard"] = guard
            record["included_by"] = sorted(self.new_headers.get(path, set()))
        self.files.append(record)
        return {"prefix": prefix, "text": out, "newline": newline, "action": action}

    def _replacement(self, path: str, scan: FileScan, body: dict[str, Any]) -> tuple[int, int, str]:
        definition = next((row for row in scan.definitions if row.in_class is not None and row.line == body["span"]["start_line"]
                           and _sha(scan.text[row.start : row.end]) == body["sha256"]), None)
        if definition is None:
            raise SocomError(f"{body['id']}: the in-class body is not where the snapshot recorded it")
        signature = self.inputs.signatures.get((body.get("row") or {}).get("artifact"))
        declaration, more = replacement_declaration(self.program, scan, definition, signature)
        flags = [{"kind": "header-body-replaced", "detail": f"the body moves out of line to {body.get('recipient')}"}, *more]
        self.replacements.append({"path": path, "body": body["id"], "name": body["mangled"], "line": body["span"]["start_line"],
                                  "removed_sha256": body["sha256"], "declaration": declaration, "flags": flags})
        return definition.start, definition.end, declaration

    def _unit(self, path: str, chains: list[tuple[str, ...]], includes: dict[str, str]) -> dict[str, Any]:
        scan = self.inputs.scans.get(path)
        self._mentions = set()
        inserts: list[tuple[int, str]] = []
        for chain in sorted(chains, key=lambda value: self.bodies[value][1].start):
            row = self._members_region(path, chain, scan, self.bodies[chain][1])
            if row is not None:
                text, row["split"] = _insert(scan.text, row["offset"], row["text"])
                inserts.append((row["offset"], text))
        sequence = 2
        definitions = []
        for chain in sorted(self.top.get(path, [])) + self._sorted(self.bottom.get(path, [])):
            definitions.append(self._definition_region(path, chain, offset=TAIL, sequence=sequence))
            sequence += 1
        unit = self.unit_paths[path]
        names = set(self._mentions)
        for function in unit["functions"]:
            names.update((self.inputs.signatures.get(function["artifact"]) or {}).get("mentions") or [])
        for region in unit["data"]:
            for item in region["rows"]:
                names.update((self.inputs.data.get(item["artifact"]) or {}).get("mentions") or [])
        rows = []
        if includes:
            flags = [{"kind": "include-added", "detail": f"{header}: {why}"} for header, why in sorted(includes.items())]
            lines = sorted({self._include_line(header, path) for header in includes})
            rows.append(self._region(path, INCLUDE, "include", lines, offset=TAIL, sequence=0, flags=flags))
        # The unit's stubs name classes its includes may not declare: declare them ahead (src/'s key), never twice.
        forward = self._forward_region(path, names, offset=TAIL, sequence=1, visible=set(includes) | _included(path, scan))
        rows += ([forward] if forward else []) + definitions
        tail = "\n".join(line for row in rows for line in row["text"])
        return {"inserts": inserts, "tail": tail + "\n" if tail else ""}

    # -- the record ----------------------------------------------------------------------------

    def record(self) -> dict[str, Any]:
        from collections import Counter

        flags = Counter(flag["kind"] for row in self.regions for flag in row["flags"])
        flags.update(flag["kind"] for row in self.regions for inner in row["nested"] for flag in inner["flags"])
        flags.update(flag["kind"] for row in self.replacements for flag in row["flags"])
        members = sum(len(row["members"]) + sum(len(inner["members"]) for inner in row["nested"]) for row in self.regions)
        statics = sum(len(row["static_members"]) + sum(len(inner["static_members"]) for inner in row["nested"]) for row in self.regions)
        classes = {row["class"] for row in self.regions if row["kind"] in ("class", "members")}
        classes |= {inner["class"] for row in self.regions for inner in row["nested"] if inner["kind"] == "class"}
        summary = {
            "files": len(self.files) + len({row["path"] for row in self.regions if row["path"] in self.unit_paths}),
            "headers": sum(1 for row in self.files if row["action"] == "header"),
            "new_headers": sum(1 for row in self.files if row["action"] == "new-header"),
            "regions": dict(sorted(Counter(row["kind"] for row in self.regions).items())),
            "new_class_bodies": sum(1 for row in self.regions if row["kind"] == "class")
            + sum(1 for row in self.regions for inner in row["nested"] if inner["kind"] == "class"),
            "type_definitions": sum(1 for row in self.regions if row["kind"] == "type")
            + sum(1 for row in self.regions for inner in row["nested"] if inner["kind"] == "type"),
            "classes_extended": sum(1 for row in self.regions if row["kind"] == "members"),
            "classes_written": len(classes),
            "member_declarations": members,
            "static_member_declarations": statics,
            "replacements": len(self.replacements),
            "flags": dict(sorted(flags.items())),
            "waiting": dict(sorted(Counter(row["kind"] for row in self.waiting).items())),
        }
        return {"summary": summary, "files": sorted(self.files, key=lambda row: row["path"]), "regions": self.regions,
                "replacements": sorted(self.replacements, key=lambda row: (row["path"], row["line"])),
                "waiting": sorted(self.waiting, key=lambda row: (row["kind"], str(row.get("type")), str(row.get("name"))))}
