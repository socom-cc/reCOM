"""The ODR header-emit check of stage 4 owner plans (``source plan emit-check``).

Reviewers kept rejecting plans one missing header emit at a time.  This check
computes the parent rulings of 2026-10-31 for every inline (binding 13) or
WEAK function copy an authored row of a plan owns, leaving out this-adjusting
thunks (``@N@...``) and MSL instances (``H-template-family`` covers those):

* units involved: the unit holding the copy (its owner row), the unit of
  every function or data artifact whose relocations reference it, and, when
  its own class's vtable references it, every unit that reads that vtable or
  calls a constructor of the class.  A unit comes from the decisions recorded
  in the plan files (every plan, so a data site counts by its own plan
  owner), else from the whole-graph draft decision; referencers neither
  decides are listed as unknown;
* an emit is expected for (a) an implicit special member (``__ct__``,
  ``__dt__``, ``__as__`` without a DWARF compile unit of its own whose ELF
  body is compiler-shaped, see below) when a header declares its class,
  (b) a copy that two or more units involve, and (c) an authored template
  instance (class-template member or function template instance), whatever
  the unit count;
* the body shape of a special member without a DWARF compile unit of its
  own, read from the ELF instructions and relocations: ``implicit`` when the
  body does only what the compiler generates (a destructor: vptr stores,
  base and member destructor calls, the delete-flag test and its operator
  delete tail; a constructor: base and member constructor calls, vptr
  stores, member zero or copy initialization; an assignment: member-wise
  copies and member ``operator=`` calls; a loop only when everything in it
  is such a copy, construction or destruction), ``user-written`` when it
  does anything else (a loop over something else, a call of another
  function, a non-zero constant or another member stored, a pointer
  deleted, a global read or written), ``unknown`` when the scan cannot tell
  (a call into library code an inlined member may have made, a value it
  does not track).  A user-written single-unit copy expects no emit; an
  unknown one is listed (``unknown_shape``), never expected;
* the header: the class's (template's) DWARF header unit, mapped to the
  workspace path (the direct ``src/<module>/<file>``, else the one file of
  that name in the module tree, else the path the plans already emit to,
  else the direct path as a new header), else the provisional header under
  ``src/`` that declares the class (``class|struct <Name>``, nested classes
  inside their enclosing scope; a ``template`` declaration for templates),
  with its line.  When (b) or (c) holds and no header is evidenced, the plan
  needs a note naming the artifact that says no header declares it;
* an existing workspace header-emit row citing ``<header>:<line>`` must cite
  a line that declares the artifact's class (or template, or free function);
* a header-emit row on a user-written special member only one unit involves
  (not a template instance) is listed as ``user_written_emits``: the rule
  places it in that unit's source file.

The check reads the source query cache, the plan files and the ELF; it
writes nothing.  ``source plan validate`` adds its counts as one review note.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Iterable

from .mwdemangle import demangle, readable_qualified, template_base
from .source_graph import path_library
from .source_plan import (
    HEADER_SUFFIXES,
    SOURCE_PLAN_KIND,
    artifact_id,
    original_module,
)
from .source_plan_edit import owner_label
from .util import SocomError, load_json

EMIT_CHECK_KIND = "socom-source-emit-check"
EMIT_CHECK_VERSION = 2
COPY_BINDINGS = frozenset({"WEAK", "13"})
MSL_NAMESPACES = frozenset({"std", "Metrowerks"})
SPECIAL_PREFIXES = ("__ct__", "__dt__", "__as__")
_THUNK = re.compile(r"^@\d+@")
_HEX = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)
# "no header declares", "no provisional header under src/ declares", ...
_NO_HEADER = re.compile(r"\bno\s+(?:[\w/.:|-]+\s+){0,4}?headers?\s+(?:[\w/.:|-]+\s+){0,4}?declares?\b", re.IGNORECASE)
_CITATION = re.compile(r"((?:[\w.-]+/)*[\w.-]+\.(?:h|hh|hpp|inc)):(\d+)\b", re.IGNORECASE)
RULE = (
    "owned authored inline (binding 13) or WEAK function copies (no @N@ thunks, no MSL): an emit is expected for an "
    "implicit special member (__ct__/__dt__/__as__ without its own DWARF compile unit whose ELF body shape is "
    "implicit: only compiler-generated work) when a header declares its "
    "class, for a copy two or more units involve (the holding unit, every referencing function or data artifact, and "
    "for a copy its class's vtable references every reader of that vtable and every caller of the class's "
    "constructors), and for an authored template instance whatever the unit count; the header is the class's "
    "(template's) DWARF header unit, else the provisional header under src/ declaring it; with no header, a note "
    "naming the artifact says no header declares it"
)
UNIT_SOURCE = (
    "the decisions recorded in build/source-plans/*.json (all plans; data sites by their own plan owner), else the "
    "whole-graph draft decision; referencers neither decides are listed as unknown"
)


# -- plans -----------------------------------------------------------------------------


def plan_files(root: Path) -> list[Path]:
    """The plan files under ``build/source-plans/`` (no ``-evidence`` or ``.prev`` copies, no scratch dirs)."""

    folder = root / "build" / "source-plans"
    if not folder.is_dir():
        return []
    return sorted(
        path for path in folder.glob("*.json")
        if path.is_file() and not path.name.endswith("-evidence.json") and ".prev" not in path.name
    )


def load_plans(root: Path, *, replace: dict[str, Any] | None = None) -> dict[str, tuple[str, dict[str, Any]]]:
    """Owner plans by work item: ``{item: (relative path, plan)}``; ``replace`` overrides one plan in memory."""

    plans: dict[str, tuple[str, dict[str, Any]]] = {}
    for path in plan_files(root):
        try:
            plan = load_json(path)
        except (OSError, ValueError, SocomError):
            continue
        if isinstance(plan, dict) and plan.get("kind") == SOURCE_PLAN_KIND and isinstance(plan.get("work_item_id"), str):
            plans.setdefault(plan["work_item_id"], (path.relative_to(root).as_posix(), plan))
    for item, value in (replace or {}).items():
        plans[item] = value
    return plans


def _row_unit(row: dict[str, Any]) -> str | None:
    if row.get("classification") == "compiler-generated":
        return None
    if row.get("translation_unit"):
        return str(row["translation_unit"])
    return owner_label(row) if row.get("classification") == "provider" else None


def plan_units(plans: dict[str, tuple[str, dict[str, Any]]]) -> dict[str, str]:
    """artifact -> the unit the plans' owner rows give it (the first plan by item when several do)."""

    units: dict[str, str] = {}
    for item in sorted(plans):
        for row in plans[item][1].get("owners") or []:
            if not isinstance(row, dict):
                continue
            unit = _row_unit(row)
            if unit is None:
                continue
            for entry in row.get("artifacts") or []:
                identity = artifact_id(entry)
                if identity:
                    units.setdefault(identity, unit)
    return units


# -- the provisional headers ----------------------------------------------------------------


_TOKEN = re.compile(
    r"(?P<tpl>\btemplate\s*<)|(?P<decl>\b(?P<kind>class|struct|union|namespace)\s+(?P<name>[A-Za-z_]\w*))"
    r"|(?P<open>\{)|(?P<close>\})|(?P<semi>;)|(?P<call>\b(?P<callee>[A-Za-z_]\w*)\s*\()"
)
_KEYWORDS = frozenset({
    "if", "while", "for", "switch", "return", "sizeof", "operator", "catch", "defined", "decltype", "alignof", "new",
    "delete", "throw", "case", "do", "else", "static_cast", "reinterpret_cast", "const_cast", "dynamic_cast",
})
_RETURN_TYPE = re.compile(r"^(?:[A-Za-z_][\w:<>,]*[\s*&]+)+$")


class HeaderIndex:
    """Class, struct, namespace and function(-template) declarations of the headers under ``src/``.

    A deliberately small scanner: comments and string literals removed,
    braces tracked to know each declaration's enclosing scopes.  A
    declaration is a definition (``class X {``, ``class X : public Y``),
    never a forward declaration or an elaborated type.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.decls: list[dict[str, Any]] = []
        self.namespaces: set[str] = set()
        self.classes: set[str] = set()
        self.files: dict[str, list[str]] = {}
        source = root / "src"
        if source.is_dir():
            for path in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
                if path.is_file() and path.name.casefold().endswith(HEADER_SUFFIXES):
                    self._scan(path.relative_to(root).as_posix(), path)
        self.by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for decl in self.decls:
            self.by_name[decl["chain"][-1]].append(decl)
            (self.namespaces if decl["kind"] == "namespace" else self.classes if decl["kind"] != "function" else set()).add(
                decl["chain"][-1]
            )

    @staticmethod
    def _clean(lines: list[str]) -> list[str]:
        """Lines without comments and string or character literals (line numbers kept)."""

        out = []
        block = False
        for line in lines:
            text = []
            index = 0
            while index < len(line):
                if block:
                    end = line.find("*/", index)
                    if end < 0:
                        index = len(line)
                        continue
                    block = False
                    index = end + 2
                    continue
                char = line[index]
                if line.startswith("//", index):
                    break
                if line.startswith("/*", index):
                    block = True
                    index += 2
                    continue
                if char in "\"'":
                    end = index + 1
                    while end < len(line) and line[end] != char:
                        end += 2 if line[end] == "\\" else 1
                    text.append(char * 2)
                    index = end + 1
                    continue
                text.append(char)
                index += 1
            out.append("".join(text))
        return out

    def _scan(self, relative: str, path: Path) -> None:
        try:
            raw = _authored_lines(path)
        except OSError:
            return
        self.files[relative] = raw
        lines = self._clean(raw)
        # (name, kind, declaration) per open brace; kind None is a block (function body, initializer).
        stack: list[tuple[str | None, str | None, dict[str, Any] | None]] = []
        pending: tuple[str, str, dict[str, Any]] | None = None
        template_line: int | None = None
        angle = 0

        def chain() -> tuple[tuple[str, ...], tuple[str, ...]]:
            named = [(name, kind) for name, kind, _decl in stack if name]
            return tuple(name for name, _kind in named), tuple(str(kind) for _name, kind in named)

        def next_text(number: int, rest: str) -> str:
            if rest.strip():
                return rest.strip()
            for later in lines[number:number + 3]:
                if later.strip():
                    return later.strip()
            return ""

        for number, line in enumerate(lines, start=1):
            position = 0
            if angle:
                # A template parameter list spanning lines.
                for index, char in enumerate(line):
                    angle += 1 if char == "<" else -1 if char == ">" else 0
                    if angle == 0:
                        position = index + 1
                        break
                else:
                    continue
            while True:
                match = _TOKEN.search(line, position)
                if match is None:
                    break
                position = match.end()
                if match.group("tpl"):
                    template_line = number
                    angle = 1
                    for index in range(position, len(line)):
                        angle += 1 if line[index] == "<" else -1 if line[index] == ">" else 0
                        if angle == 0:
                            position = index + 1
                            break
                    else:
                        position = len(line)
                    continue
                if match.group("decl"):
                    kind, name = match.group("kind"), match.group("name")
                    rest = next_text(number, line[position:])
                    definition = rest.startswith("{") or (rest.startswith(":") and not rest.startswith("::")) or rest.startswith("final")
                    if kind == "namespace":
                        definition = rest.startswith("{")
                    if definition:
                        names, kinds = chain()
                        decl = {
                            "path": relative, "line": number, "end": None, "kind": kind, "chain": (*names, name),
                            "kinds": (*kinds, kind), "template": template_line is not None and kind != "namespace",
                            "template_line": template_line,
                        }
                        self.decls.append(decl)
                        pending = (name, kind, decl)
                        template_line = None
                    continue
                if match.group("open"):
                    # extern "C" { ... } keeps namespace scope (its literal is cleaned to "").
                    linkage = re.search(r"\bextern\s*\"\"\s*$", line[: match.start()]) is not None
                    stack.append(pending if pending else (None, "extern", None) if linkage else (None, None, None))
                    pending = None
                    template_line = None
                    continue
                if match.group("close"):
                    if stack:
                        closed = stack.pop()[2]
                        if closed is not None:
                            closed["end"] = number
                    continue
                if match.group("semi"):
                    pending = None
                    template_line = None
                    continue
                callee = match.group("callee")
                if callee in _KEYWORDS or pending is not None:
                    continue
                # A class body or a block (function body, initializer): no free declaration there.
                inside_class = any(kind not in ("namespace", "extern") for _name, kind, _decl in stack)
                before = line[: match.start()].strip()
                if template_line is not None:
                    names, kinds = chain()
                    self.decls.append({
                        "path": relative, "line": number, "end": None, "kind": "function", "chain": (*names, callee),
                        "kinds": (*kinds, "function"), "template": True, "template_line": template_line,
                    })
                    template_line = None
                elif not inside_class and before and _RETURN_TYPE.match(before + " ") and "=" not in before:
                    names, kinds = chain()
                    self.decls.append({
                        "path": relative, "line": number, "end": None, "kind": "function", "chain": (*names, callee),
                        "kinds": (*kinds, "function"), "template": False, "template_line": None,
                    })
                # Skip the rest of a declaration's parameter list.
                depth = 1
                while position < len(line) and depth:
                    depth += 1 if line[position] == "(" else -1 if line[position] == ")" else 0
                    position += 1

    def _namespace_like(self, name: str) -> bool:
        return name in self.namespaces or name not in self.classes

    def matches(self, wanted: tuple[str, ...], *, kinds: tuple[str, ...], template: bool | None = None) -> list[dict[str, Any]]:
        """Declarations of ``wanted`` (its scope chain): exact chains first, else namespaces ignored on both sides."""

        candidates = [
            decl for decl in self.by_name.get(wanted[-1], [])
            if decl["kind"] in kinds and (template is None or decl["template"] == template)
        ]
        exact = [decl for decl in candidates if decl["chain"] == wanted]
        if exact:
            return exact
        relaxed = tuple(part for part in wanted[:-1] if not self._namespace_like(part)) + (wanted[-1],)
        return [
            decl for decl in candidates
            if tuple(name for name, kind in zip(decl["chain"][:-1], decl["kinds"][:-1]) if kind != "namespace") + (decl["chain"][-1],)
            == relaxed
        ]

    def line_text(self, relative: str, line: int) -> str | None:
        lines = self.files.get(relative)
        if lines is None:
            path = self.root / relative
            if not path.is_file():
                return None
            lines = _authored_lines(path)
        return lines[line - 1].strip() if 0 < line <= len(lines) else None


def _authored_lines(path: Path) -> list[str]:
    """The file's authored lines: generated ownership blocks (stage-4 applies) do not count.

    Header citations (``zai.h:297``) name lines of the authored content, so they stay
    valid when an apply adds, rewrites or removes the generated blocks at the top.
    """

    from .source_apply import parse_blocks

    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        _bom, _blocks, text = parse_blocks(text)
    except SocomError:
        pass
    return text.splitlines()


# -- the check ------------------------------------------------------------------------------


class _Cache:
    """The cache rows the check reads, loaded once."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.shapes: dict[str, dict[str, Any]] = {}
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
            self.graph_sha256 = (connection.execute("SELECT value FROM meta WHERE key = 'graph_sha256'").fetchone() or [None])[0]
            self.rows: dict[str, dict[str, Any]] = {}
            self.functions: dict[int, dict[str, Any]] = {}
            for identity, kind, address, size, binding, classification, library, header in connection.execute(
                "SELECT id, kind, address, size, binding, classification, library, emitted_from_header FROM artifacts"
            ):
                self.rows[identity] = {
                    "id": identity, "kind": kind, "address": address, "size": size, "binding": binding,
                    "classification": classification, "library": library, "header": header, "names": [],
                }
                if kind == "function" and address is not None:
                    self.functions.setdefault(int(address), self.rows[identity])
            for identity, name, binding in connection.execute("SELECT artifact, name, binding FROM names ORDER BY artifact, symbol_index"):
                if identity in self.rows:
                    self.rows[identity]["names"].append((str(name), binding))
            self.referencers: dict[str, set[str]] = defaultdict(set)
            for site, target in connection.execute(
                "SELECT DISTINCT site_artifact, target_artifact FROM refs WHERE site_artifact IS NOT NULL AND target_artifact IS NOT NULL"
            ):
                if site != target:
                    self.referencers[target].add(site)
            self.dwarf = {value for (value,) in connection.execute("SELECT DISTINCT artifact FROM dwarf_cus WHERE artifact IS NOT NULL")}
        self.vtables: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self.constructors: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self.class_headers: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        self.family_headers: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        self.examples: dict[tuple[tuple[str, ...], str], list[str]] = defaultdict(list)
        for identity, row in self.rows.items():
            for name, _binding in row["names"]:
                value = demangle(name)
                if not value or not value["qualifier"]:
                    continue
                qualifier = tuple(value["qualifier"])
                if row["kind"] == "data" and name.startswith("__vt__") and value["params"] is None:
                    self.vtables[qualifier].append(identity)
                elif row["kind"] == "function" and name.startswith("__ct__") and value["params"] is not None:
                    self.constructors[qualifier].append(identity)
            if row["kind"] != "function" or not row["header"]:
                continue
            shape = _shape(row)
            if shape is None:
                continue
            if shape["class"]:
                self.class_headers[shape["class"]][row["header"]] += 1
                self.examples[(shape["class"], row["header"])].append(identity)
            if shape["template"]:
                self.family_headers[shape["template"]][row["header"]] += 1
                self.examples[(shape["template"], row["header"])].append(identity)
        self.vtable_ids = {identity for values in self.vtables.values() for identity in values}

    def callee(self, address: int | None, symbol: str | None) -> dict[str, Any]:
        """What a call target is, for the body shape: its name, special kind, operator delete, array helper, library."""

        row = self.functions.get(address) if address is not None else None
        names = [name for name, _binding in row["names"]] if row else [symbol] if symbol else []
        info: dict[str, Any] = {"name": names[0] if names else None}
        for name in names:
            for prefix, special in (("__dt__", "dt"), ("__ct__", "ct"), ("__as__", "as")):
                if name.startswith(prefix):
                    info["special"] = special
            if name.startswith(DELETE_PREFIXES):
                info["delete"] = True
            if name in ARRAY_HELPERS:
                info["helper"] = True
            value = demangle(name)
            if value and value["qualifier"] and template_base(value["qualifier"][0]) in MSL_NAMESPACES:
                info["provider"] = True
        if row and row.get("classification") == "provider":
            info["provider"] = True
        return info

    def body(
        self, identity: str, kind: str, word: Callable[[int], int] | None, qualifier: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        """The body shape of a special member of class ``qualifier`` (``unknown`` without the ELF), computed once."""

        if identity in self.shapes:
            return self.shapes[identity]
        row = self.rows[identity]
        if word is None or not row.get("size") or row.get("address") is None:
            result: dict[str, Any] = {"shape": "unknown", "reasons": ["no ELF instructions to read"]}
        else:
            start = int(row["address"])
            sites: dict[int, dict[str, Any]] = {}
            with closing(sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)) as connection:
                for site, target, kind_, symbol in connection.execute(
                    "SELECT site, target_artifact, type, symbol FROM refs WHERE site_artifact = ?", (identity,)
                ):
                    sites[int(site)] = {
                        "type": kind_, "symbol": symbol,
                        "target_kind": "vtable" if target in self.vtable_ids else (str(target).split(":")[1] if target else None),
                    }
            own = frozenset(
                name for table in self.vtables.get(tuple(qualifier), []) for name, _binding in self.rows[table]["names"]
            )
            try:
                result = body_shape(word, start, int(row["size"]), kind, sites, self.callee, own)
            except (IndexError, ValueError) as failure:
                result = {"shape": "unknown", "reasons": [f"the body could not be read: {failure}"]}
        self.shapes[identity] = result
        return result


def elf_words(root: Path) -> Callable[[int], int] | None:
    """A reader of the reference ELF's loaded words (``None`` when ``support/socom.elf`` is absent)."""

    from .elf import Elf32File
    from .mips_flow import _Code

    path = root / "support" / "socom.elf"
    if not path.is_file():
        return None
    return _Code(Elf32File(path)).word


def _bindings(row: dict[str, Any]) -> set[Any]:
    return {binding for _name, binding in row["names"]} | {row.get("binding")}


def _shape(row: dict[str, Any]) -> dict[str, Any] | None:
    """A function's mangled shape: name, qualifier, class chain and template chain (bases, no arguments)."""

    for name, _binding in row["names"]:
        value = demangle(name)
        if not value or value["params"] is None:
            continue
        qualifier = tuple(value["qualifier"])
        bases = tuple(template_base(part) for part in qualifier)
        template, kind = None, None
        for index, part in enumerate(qualifier):
            if "<" in part:
                template, kind = bases[: index + 1], "class"
                break
        if template is None and "<" in value["name"]:
            template, kind = (*bases, template_base(value["name"])), "function"
        return {
            "name": name, "base": value["name"], "qualifier": qualifier, "class": bases or None, "template": template,
            "template_kind": kind, "params": value["params"],
        }
    return None


def _params(shape: dict[str, Any]) -> list[dict[str, Any]]:
    # ``Fv`` demangles to one void parameter: no parameters.
    return [value for value in shape["params"] or [] if not (value.get("kind") == "builtin" and value.get("name") == "void")]


def _special_shape(shape: dict[str, Any]) -> bool:
    """A destructor, default or copy constructor, or copy assignment: what the compiler may generate."""

    params = _params(shape)
    copy = (
        len(params) == 1 and params[0].get("kind") == "class" and "R" in (params[0].get("modifiers") or [])
        and tuple(params[0].get("components") or ()) == shape["qualifier"]
    )
    if shape["name"].startswith("__dt__"):
        return not params
    if shape["name"].startswith("__ct__"):
        return not params or copy
    return shape["name"].startswith("__as__") and copy


def special_kind(shape: dict[str, Any]) -> str | None:
    """``dtor``, ``ctor`` (default), ``copy`` (copy constructor) or ``assign`` (copy assignment); else ``None``."""

    if not shape["name"].startswith(SPECIAL_PREFIXES) or not _special_shape(shape):
        return None
    if shape["name"].startswith("__dt__"):
        return "dtor"
    if shape["name"].startswith("__as__"):
        return "assign"
    return "copy" if _params(shape) else "ctor"


# -- the body shape of a special member --------------------------------------------------------

SHAPES = ("implicit", "user-written", "unknown")
DELETE_PREFIXES = ("__dl__", "__dla__")
ARRAY_HELPERS = frozenset({"__construct_array", "__destroy_arr"})
_CLOBBERED = (1, 2, 3, *range(4, 16), 24, 25, 31)
_LOADS = frozenset({0x1A, 0x1B, 0x1E, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x37})
_STORES = frozenset({0x1F, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3F})
_SHIFTS = frozenset({0x00, 0x02, 0x03, 0x38, 0x3A, 0x3B, 0x3C, 0x3E, 0x3F})
_BRANCHES = frozenset({0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17})
_GLOBAL_RELOCATIONS = frozenset({"R_MIPS_LO16", "R_MIPS_GPREL16"})
_OTHER: tuple[Any, ...] = ("other",)
_FLAG: tuple[Any, ...] = ("flag",)


def _s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


class _Body:
    """One pass over a special member's instructions in address order, tracking what each register holds.

    Values: ``("this", offset)``, ``("src", offset)`` (the copied object),
    ``("stack", offset)``, ``("const", value)``, ``("flag",)`` (the
    destructor's delete flag), ``("vtable", symbol)``, ``("addr", symbol)``,
    ``("member", offset)`` and ``("srcval", offset)`` (loaded from this or
    the source), ``("ret", callee)`` and ``("other",)``.  Every store and call
    is an event: ``ok`` (what the compiler generates), ``user`` or ``unsure``.
    Events that are not the member's own are not judged: the deleting tail
    after the delete-flag test, up to its target (operator delete, called or
    inlined), and an inlined base destructor or constructor, which starts
    with the store of a vtable not the class's own (``own_vtables``): in a
    destructor up to the delete-flag test, in a constructor up to the
    store of the class's own vptr.
    """

    def __init__(
        self,
        word: Callable[[int], int],
        start: int,
        size: int,
        kind: str,
        sites: dict[int, dict[str, Any]],
        callee: Callable[[int | None, str | None], dict[str, Any]],
        own_vtables: frozenset[str] = frozenset(),
    ) -> None:
        self.word, self.start, self.end, self.kind, self.sites, self.callee = word, start, start + size, kind, sites, callee
        self.own_vtables = own_vtables
        self.inlined: list[list[int]] = []
        self.slot_of: int | None = None
        self.gpr: list[tuple[Any, ...]] = [_OTHER] * 32
        self.gpr[0], self.gpr[28], self.gpr[29], self.gpr[4] = ("const", 0), ("gp",), ("stack", 0), ("this", 0)
        self.gpr[5] = _FLAG if kind == "dtor" else ("src", 0) if kind in ("copy", "assign") else _OTHER
        self.fpr: dict[int, tuple[Any, ...]] = {}
        self.vfr: dict[int, tuple[Any, ...]] = {}
        self.stack: dict[int, tuple[Any, ...]] = {}
        self.events: list[tuple[int, str, str]] = []
        self.loops: list[tuple[int, int]] = []
        self.deleting: list[tuple[int, int]] = []

    # -- events ------------------------------------------------------------------------------

    def _deleting(self, pc: int) -> bool:
        return any(low <= pc < high for low, high in self.deleting)

    def _not_own(self, pc: int) -> bool:
        return self._deleting(pc) or any(low <= pc < high for low, high in self.inlined)

    def _event(self, pc: int, verdict: str, text: str) -> None:
        if not self._not_own(pc):
            self.events.append((pc, verdict, f"0x{pc:x} {text}"))

    def _close_inlined(self, pc: int) -> None:
        if self.inlined and self.inlined[-1][1] > pc:
            self.inlined[-1][1] = pc

    def _vptr(self, pc: int, symbol: str) -> None:
        """A vptr store: a base's vtable opens an inlined base destructor or constructor, the own one closes the latter."""

        # A store in a call's delay slot runs before that call.
        at = self.slot_of if self.slot_of is not None else pc
        own = symbol in self.own_vtables
        if self.kind in ("ctor", "copy") and own:
            self._close_inlined(at)
        elif not own and self.own_vtables and not self._not_own(at):
            self.inlined.append([at, self.end])

    def _set(self, register: int, value: tuple[Any, ...]) -> None:
        if register:
            self.gpr[register] = value

    @staticmethod
    def _mixed(*values: tuple[Any, ...]) -> tuple[Any, ...]:
        """A computed value: bits of the source object (a bitfield copy) when an operand holds some, else untracked."""

        return ("srcval", None) if any(value[0] == "srcval" for value in values) else _OTHER

    def _load(self, pc: int, base: tuple[Any, ...], offset: int) -> tuple[Any, ...]:
        if base[0] == "stack":
            return self.stack.get(base[1] + offset, _OTHER)
        if base[0] == "this":
            return ("member", base[1] + offset)
        if base[0] == "src":
            return ("srcval", base[1] + offset)
        if base[0] == "gp":
            self._event(pc, "user", "reads a global")
            return _OTHER
        return ("deref",)

    def _store(self, pc: int, base: tuple[Any, ...], offset: int, value: tuple[Any, ...]) -> None:
        if base[0] == "stack":
            self.stack[base[1] + offset] = value
            return
        if base[0] != "this":
            if base[0] == "src":
                self._event(pc, "user", "writes to the source object")
            elif base[0] in ("member", "deref", "ret", "gp"):
                self._event(pc, "user", f"writes through a pointer ({base[0]})")
            else:
                self._event(pc, "unsure", "writes through an untracked pointer")
            return
        where = f"this+0x{base[1] + offset:x}"
        tag = value[0]
        if tag == "vtable":
            self._event(pc, "unsure" if self.kind == "assign" else "ok", f"stores the vptr {value[1]} to {where}")
            if self.kind != "assign":
                self._vptr(pc, str(value[1]))
        elif tag == "const" and value[1] == 0:
            ok = self.kind in ("ctor", "copy")
            self._event(pc, "ok" if ok else "user", f"stores 0 to {where}" + ("" if ok else f" in a {self.kind}"))
        elif tag == "srcval" and self.kind in ("copy", "assign"):
            what = "bits of the source" if value[1] is None else f"source+0x{value[1]:x}"
            self._event(pc, "ok", f"copies {what} to {where}")
        elif tag == "const":
            self._event(pc, "user", f"stores the constant 0x{value[1] & 0xFFFFFFFF:x} to {where}")
        elif tag in ("addr", "src", "member"):
            what = {"addr": f"the address of {value[1]}", "src": "a pointer to the source", "member": "another member"}[tag]
            self._event(pc, "user", f"stores {what} to {where}")
        elif tag == "this":
            self._event(pc, "unsure", f"stores a pointer into this to {where}")
        elif tag == "ret":
            self._event(pc, "unsure", f"stores the result of {value[1]} to {where}")
        else:
            self._event(pc, "unsure", f"stores an untracked value to {where}")

    def _call(self, pc: int, target: int | None, symbol: str | None) -> None:
        info = self.callee(target, symbol)
        name = info.get("name") or (f"0x{target:x}" if target is not None else "an unknown target")
        a0, a1 = self.gpr[4], self.gpr[5]
        if self._not_own(pc):
            return
        if info.get("delete"):
            if a0 == ("this", 0) and self.kind == "dtor":
                self._event(pc, "ok", f"calls {name} on this")
            else:
                self._event(pc, "user", f"calls {name} on {a0[0]}, not this")
            return
        special = info.get("special")
        if not special and not info.get("helper"):
            if info.get("provider"):
                self._event(pc, "unsure", f"calls library code {name}")
            else:
                self._event(pc, "user", f"calls {name}")
            return
        if a0[0] != "this":
            if a0[0] in ("stack", "other"):
                self._event(pc, "unsure", f"calls {name} on an untracked object ({a0[0]})")
            else:
                self._event(pc, "user", f"calls {name} on {a0[0]}, not a base or member")
            return
        allowed = {"dtor": ("dt",), "ctor": ("ct",), "copy": ("ct",), "assign": ("as",)}[self.kind]
        if info.get("helper"):
            self._event(pc, "ok", f"calls {name} on this+0x{a0[1]:x}")
        elif special not in allowed:
            self._event(pc, "user", f"calls {name} in a {self.kind}")
        elif special == "dt" and a1[0] == "const" and a1[1] > 0:
            self._event(pc, "user", f"destroys and deletes this+0x{a0[1]:x} ({name})")
        else:
            self._event(pc, "ok", f"calls {name} on this+0x{a0[1]:x}")

    # -- instructions ------------------------------------------------------------------------

    def _plain(self, pc: int) -> None:
        insn = self.word(pc)
        if insn == 0:
            return
        op, rs, rt, rd = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, (insn >> 11) & 31
        sa, funct, imm = (insn >> 6) & 31, insn & 0x3F, insn & 0xFFFF
        site = self.sites.get(pc)
        gpr = self.gpr
        if op == 0x00:
            if funct in (0x21, 0x2D, 0x25) and (rt == 0 or rs == 0):
                self._set(rd, gpr[rs if rt == 0 else rt])
            elif funct in _SHIFTS:
                self._set(rd, _FLAG if gpr[rt] == _FLAG else self._mixed(gpr[rt]))
            elif funct == 0x0C:
                self._event(pc, "user", "a system call")
            elif funct not in (0x0D, 0x0F, 0x11, 0x13, 0x18, 0x19, 0x1A, 0x1B):
                self._set(rd, self._mixed(gpr[rs], gpr[rt]))
        elif op == 0x0F:
            self._set(rt, ("hi",) if site else ("const", imm << 16))
        elif op in (0x08, 0x09, 0x18, 0x19):
            base = gpr[rs]
            if site and site.get("type") in _GLOBAL_RELOCATIONS:
                self._set(rt, ("vtable" if site.get("target_kind") == "vtable" else "addr", site.get("symbol")))
            elif base[0] == "const":
                self._set(rt, ("const", base[1] + _s16(imm)))
            elif base[0] in ("this", "src", "stack"):
                self._set(rt, (base[0], base[1] + _s16(imm)))
            else:
                self._set(rt, _OTHER)
        elif op == 0x0D:
            self._set(rt, ("const", gpr[rs][1] | imm) if gpr[rs][0] == "const" else self._mixed(gpr[rs]))
        elif op in (0x0A, 0x0B, 0x0C, 0x0E):
            self._set(rt, self._mixed(gpr[rs]))
        elif op in _LOADS or op in (0x31, 0x36):
            if site and site.get("type") in _GLOBAL_RELOCATIONS:
                self._event(pc, "user", f"reads the global {site.get('symbol')}")
                value: tuple[Any, ...] = _OTHER
            else:
                value = self._load(pc, gpr[rs], _s16(imm))
            if op == 0x31:
                self.fpr[rt] = value
            elif op == 0x36:
                self.vfr[rt] = value
            else:
                self._set(rt, value)
        elif op in _STORES or op in (0x39, 0x3E):
            if site and site.get("type") in _GLOBAL_RELOCATIONS:
                self._event(pc, "user", f"writes the global {site.get('symbol')}")
                return
            value = self.fpr.get(rt, _OTHER) if op == 0x39 else self.vfr.get(rt, _OTHER) if op == 0x3E else gpr[rt]
            self._store(pc, gpr[rs], _s16(imm), value)
        elif op == 0x11:
            if rs == 0x04:  # mtc1
                self.fpr[rd] = gpr[rt] if gpr[rt][0] == "const" else _OTHER
            elif rs in (0x00, 0x02):  # mfc1, cfc1
                self._set(rt, _OTHER)
            elif rs == 0x10 and funct == 0x06:  # mov.s
                self.fpr[sa] = self.fpr.get(rd, _OTHER)
            elif rs != 0x06:
                self._event(pc, "user", "floating-point arithmetic")
        elif op == 0x1C:
            # por rd,rs,zero moves 128 bits; other MMI operations compute.
            self._set(rd, gpr[rs] if funct == 0x29 and sa == 0x12 and rt == 0 else _OTHER)
        elif op == 0x12:
            if rs == 0x05:  # qmtc2
                self.vfr[rd] = gpr[rt]
            elif rs in (0x01, 0x02):  # qmfc2, cfc2
                self._set(rt, self.vfr.get(rd, _OTHER) if rs == 0x01 else _OTHER)
            elif rs != 0x06:
                self._event(pc, "user", "VU0 arithmetic")
        else:
            self._event(pc, "unsure", f"an unrecognized instruction 0x{insn:08x}")

    def _returned(self, name: str | None) -> None:
        for register in _CLOBBERED:
            self.gpr[register] = _OTHER
        self.gpr[2] = ("ret", name)
        self.fpr.clear()
        self.vfr.clear()

    def run(self) -> dict[str, Any]:
        pc = self.start
        while pc < self.end:
            insn = self.word(pc)
            op, rs, rt, funct, imm = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31, insn & 0x3F, insn & 0xFFFF
            site = self.sites.get(pc) or {}
            if op == 0x03 or (op == 0x00 and funct in (0x08, 0x09)) or op == 0x02:
                # A call or jump: its delay slot runs first.
                self.slot_of = pc
                self._plain(pc + 4)
                self.slot_of = None
                target = ((pc + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2) if op in (0x02, 0x03) else None
                if op == 0x03 or (op == 0x02 and target is not None and not self.start <= target < self.end):
                    self._call(pc, target, site.get("symbol"))
                    self._returned(self.callee(target, site.get("symbol")).get("name"))
                elif op == 0x02 and target is not None and target <= pc:
                    self.loops.append((target, pc + 8))
                elif op == 0x00 and funct == 0x09:
                    self._event(pc, "user", "an indirect (virtual) call")
                    self._returned(None)
                elif op == 0x00 and rs != 31:
                    self._event(pc, "unsure", "an indirect jump")
                pc += 8
                continue
            if op in _BRANCHES or (op == 0x01 and rt in (0x00, 0x01, 0x02, 0x03)) or (op == 0x11 and rs == 0x08):
                target = pc + 4 + (_s16(imm) << 2)
                flag_test = op in (0x06, 0x16) and self.gpr[rs] == _FLAG or op in (0x04, 0x14) and (
                    (self.gpr[rs] == _FLAG and rt == 0) or (self.gpr[rt] == _FLAG and rs == 0))
                self.slot_of = pc
                self._plain(pc + 4)
                self.slot_of = None
                if target <= pc and not self._not_own(pc):
                    self.loops.append((target, pc + 8))
                elif self.kind == "dtor" and flag_test and target > pc:
                    self._close_inlined(pc)
                    self.deleting.append((pc + 8, target))
                pc += 8
                continue
            self._plain(pc)
            pc += 4
        for low, high in self.loops:
            if self._not_own(low):
                continue
            if not any(low <= event[0] < high for event in self.events):
                # Stores or calls in a loop are judged one by one; a loop of neither (a count, a search) may be either.
                self.events.append((low, "unsure", f"0x{high - 8:x} a loop (back to 0x{low:x}) that stores and calls nothing"))
        user = [text for _pc, verdict, text in sorted(self.events) if verdict == "user"]
        unsure = [text for _pc, verdict, text in sorted(self.events) if verdict == "unsure"]
        shape = "user-written" if user else "unknown" if unsure else "implicit"
        return {"shape": shape, "reasons": (user or unsure)[:4]}


def body_shape(
    word: Callable[[int], int],
    start: int,
    size: int,
    kind: str,
    sites: dict[int, dict[str, Any]],
    callee: Callable[[int | None, str | None], dict[str, Any]],
    own_vtables: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """The body shape of one special member: ``{shape, reasons}`` (the first user-written or unsure events).

    ``sites``: relocation site address -> ``{type, symbol, target_kind}``
    (``vtable`` for a class's ``__vt__`` table).  ``callee(address, symbol)``
    -> ``{name, special ('dt'|'ct'|'as'), delete, helper, provider}``.
    ``own_vtables``: the class's own vtable symbols (another class's opens an
    inlined base destructor or constructor).
    """

    return _Body(word, start, size, kind, sites, callee, own_vtables).run()


def _emit_reason(row: dict[str, Any]) -> str:
    """The header-emit reason ``source plan validate`` accepts for the symbol (as the draft writes it)."""

    if any("<" in name for name, _binding in row["names"]):
        return "template"
    return "weak" if "WEAK" in _bindings(row) else "inline"


def _excluded(row: dict[str, Any], shape: dict[str, Any] | None) -> str | None:
    if any(_THUNK.match(name) for name, _binding in row["names"]):
        return "thunk"
    if row.get("classification") == "provider" and row.get("library") == "MSL":
        return "msl"
    if shape is not None and shape["qualifier"] and template_base(shape["qualifier"][0]) in MSL_NAMESPACES:
        return "msl"
    return None


class _Headers:
    """Maps DWARF header paths to workspace headers, the way the plans write them."""

    def __init__(self, root: Path, plans: dict[str, tuple[str, dict[str, Any]]]) -> None:
        self.root = root
        self.directories: dict[str, str] = {}
        self.by_folded: dict[str, list[str]] = defaultdict(list)
        source = root / "src"
        if source.is_dir():
            for path in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
                relative = path.relative_to(root).as_posix()
                if path.is_dir():
                    self.directories.setdefault(relative.casefold(), relative)
                elif path.is_file():
                    self.by_folded[path.name.casefold()].append(relative)
        self.used: Counter[str] = Counter(
            str(row.get("header"))
            for _path, plan in plans.values()
            for row in plan.get("header_emits") or []
            if isinstance(row, dict) and isinstance(row.get("header"), str) and row["header"].startswith("src/")
        )

    def workspace(self, header: str) -> dict[str, Any]:
        """The workspace header a DWARF header path names: ``{header, library?, exists, how}``."""

        name = PureWindowsPath(header.replace("/", "\\")).name
        verdict = path_library(header)
        if verdict and verdict[0] == "provider":
            return {"header": f"<{name}>", "library": verdict[1], "exists": None, "how": "provider header"}
        module = original_module(header)
        if module is None:
            return {"header": None, "exists": False, "how": f"{header} is no Z:\\dev path"}
        spelled = self.directories.get(module.casefold(), module)
        direct = f"{spelled}/{name}"
        if (self.root / direct).is_file():
            return {"header": direct, "exists": True, "how": "direct"}
        tree = [path for path in self.by_folded.get(name.casefold(), []) if path.casefold().startswith(spelled.casefold() + "/")]
        if len(tree) == 1:
            return {"header": tree[0], "exists": True, "how": "by file name in the module tree"}
        used = sorted(
            (path for path in self.used if PureWindowsPath(path).name.casefold() == name.casefold()
             and path.casefold().startswith(spelled.casefold() + "/")),
            key=lambda path: (-self.used[path], path),
        )
        if used:
            return {"header": used[0], "exists": (self.root / used[0]).is_file(), "how": "the path the plans emit to"}
        return {"header": direct, "exists": False, "how": "direct (a new header)"}


def _units(identities: Iterable[str], plan_unit: dict[str, str], draft_unit: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    found: dict[str, str] = {}
    unknown = []
    for identity in identities:
        unit = plan_unit.get(identity) or draft_unit.get(identity)
        if unit:
            found.setdefault(unit.casefold(), unit)
        else:
            unknown.append(identity)
    return found, unknown


def _note_groups(notes: list[Any]) -> list[tuple[set[int], bool]]:
    """Each note split into groups: (addresses named, says no header declares it).

    A note is split into clauses at ``;`` and sentence ends; a clause naming
    no address joins the group before it (a leading one the group after).
    """

    groups: list[tuple[set[int], bool]] = []
    for note in notes:
        if not isinstance(note, str):
            continue
        current: list[tuple[set[int], bool]] = []
        leading = False
        for clause in re.split(r";\s+|\.\s+(?=[A-Z])", note):
            addresses = {int(value, 16) for value in _HEX.findall(clause)}
            says = bool(_NO_HEADER.search(clause))
            if addresses:
                current.append((addresses, says or leading))
                leading = False
            elif current:
                current[-1] = (current[-1][0], current[-1][1] or says)
            else:
                leading = leading or says
        groups.extend(current)
    return groups


def _citations(row: dict[str, Any], index: HeaderIndex) -> list[tuple[str, int, str]]:
    """``(workspace path, line, as cited)`` for each ``<header>:<line>`` an emit row's evidence cites."""

    found = []
    header = str(row.get("header") or "")
    for text in row.get("evidence") or []:
        if not isinstance(text, str):
            continue
        for match in _CITATION.finditer(text):
            cited, line = match.group(1), int(match.group(2))
            if cited.startswith("src/"):
                path = cited
            elif PureWindowsPath(header).name.casefold() == PureWindowsPath(cited).name.casefold():
                path = header
            else:
                named = [value for value in index.files if PureWindowsPath(value).name.casefold() == PureWindowsPath(cited).name.casefold()]
                if len(named) != 1:
                    continue
                path = named[0]
            found.append((path, line, match.group(0)))
    return found


def _subject(shape: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...], bool | None, str]:
    """What a header must declare for a copy: (chain, declaration kinds, template?, label)."""

    if shape["template"]:
        kinds = ("function",) if shape["template_kind"] == "function" else ("class", "struct", "union")
        return shape["template"], kinds, True, readable_qualified(list(shape["template"]))
    if shape["class"]:
        return shape["class"], ("class", "struct", "union"), None, readable_qualified(list(shape["class"]))
    return (template_base(shape["base"]),), ("function",), None, template_base(shape["base"])


def _declarations(index: HeaderIndex, shape: dict[str, Any]) -> list[dict[str, Any]]:
    """The header declarations of a copy's class (template, free function); a nested class falls back to its enclosing class."""

    chain, kinds, template, _label = _subject(shape)
    found = index.matches(chain, kinds=kinds, template=template)
    if not found and shape["class"] and not shape["template"]:
        # A namespace-qualified free function: its declaration inside the namespace.
        found = index.matches((*shape["class"], template_base(shape["base"])), kinds=("function",))
        # A nested class no header declares by itself is declared inside its enclosing class.
        enclosing = chain[:-1]
        while not found and enclosing and not index._namespace_like(enclosing[-1]):
            found = [decl | {"via": "enclosing class"} for decl in index.matches(enclosing, kinds=kinds)]
            enclosing = enclosing[:-1]
    return found


def check_plan(
    plan_path: str,
    plan: dict[str, Any],
    *,
    cache: _Cache,
    index: HeaderIndex,
    headers: _Headers,
    plan_unit: dict[str, str],
    draft_unit: dict[str, str],
    word: Callable[[int], int] | None = None,
) -> dict[str, Any]:
    """The emit check of one plan: missing emits, missing notes, wrong citations and undetermined copies.

    ``word`` reads the ELF's loaded words for the body shape of special
    members (``None``: every body shape is ``unknown``).
    """

    emits = {row.get("artifact"): row for row in plan.get("header_emits") or [] if isinstance(row, dict)}
    groups = _note_groups(list(plan.get("notes") or []))
    missing_emits: list[dict[str, Any]] = []
    missing_notes: list[dict[str, Any]] = []
    undetermined: list[dict[str, Any]] = []
    unknown_shape: list[dict[str, Any]] = []
    user_written_emits: list[dict[str, Any]] = []
    special_members: dict[str, dict[str, Any]] = {}
    shapes: Counter[str] = Counter()
    checked = expected = 0
    for owner in plan.get("owners") or []:
        if not isinstance(owner, dict) or owner.get("classification") != "authored":
            continue
        holder = _row_unit(owner)
        for entry in owner.get("artifacts") or []:
            identity = artifact_id(entry)
            row = cache.rows.get(identity or "")
            if row is None or row["kind"] != "function" or not _bindings(row) & COPY_BINDINGS:
                continue
            shape = _shape(row)
            if _excluded(row, shape) or shape is None:
                continue
            checked += 1
            sites = set(cache.referencers.get(identity, ()))
            vtable = None
            if shape["qualifier"]:
                tables = [value for value in cache.vtables.get(shape["qualifier"], []) if value in sites]
                if tables:
                    readers = {site for table in tables for site in cache.referencers.get(table, ())} - set(tables)
                    builders = {
                        site for constructor in cache.constructors.get(shape["qualifier"], [])
                        for site in cache.referencers.get(constructor, ()) if site != constructor
                    }
                    vtable = {"vtables": sorted(tables), "readers": len(readers), "constructor_callers": len(builders)}
                    sites |= readers | builders
            sites.discard(identity)
            units, unknown = _units(sorted(sites), plan_unit, draft_unit)
            if holder:
                units.setdefault(holder.casefold(), holder)
            names = sorted(units.values(), key=str.casefold)
            # A special member without a DWARF compile unit of its own is implicit only when its body is compiler-shaped.
            kind = special_kind(shape) if identity not in cache.dwarf else None
            body = cache.body(identity, kind, word, shape["qualifier"]) if kind else None
            if body is not None:
                shapes[body["shape"]] += 1
            implicit = body is not None and body["shape"] == "implicit"
            template = shape["template"] is not None
            chain, _kinds, _template, label = _subject(shape)
            # The header: own or the class's (template's) DWARF header unit, else a provisional declaration.
            dwarf: Counter[str] = Counter()
            if row["header"]:
                dwarf[row["header"]] += 1000
            key = shape["template"] or shape["class"]
            if key:
                dwarf.update((cache.family_headers if template else cache.class_headers).get(key, Counter()))
            dwarf = Counter({path: count for path, count in dwarf.items() if (path_library(path) or ("",))[0] in ("authored", "provider")})
            suggestion = None
            if dwarf:
                chosen = sorted(dwarf, key=lambda path: (-dwarf[path], path.casefold()))[0]
                mapped = headers.workspace(chosen)
                if mapped["header"]:
                    members = sorted(set(cache.examples.get((key, chosen), [])) - {identity}) if key else []
                    suggestion = {
                        "header": mapped["header"], "line": None, "source": "dwarf-header-unit", "dwarf_header": chosen,
                        "mapped": mapped["how"], "exists": mapped["exists"],
                        "evidence": ("its own header compile unit" if row["header"] == chosen else
                                     f"header compile units of {label} members ({len(members)}, e.g. {', '.join(members[:3])})"),
                    }
                    if mapped.get("library"):
                        suggestion["library"] = mapped["library"]
                    if len(dwarf) > 1:
                        suggestion["other_dwarf_headers"] = sorted(path for path in dwarf if path != chosen)
            if suggestion is None:
                found = _declarations(index, shape)
                if found:
                    first = sorted(found, key=lambda decl: (decl["path"], decl["line"]))
                    suggestion = {
                        "header": first[0]["path"], "line": first[0]["line"], "source": "provisional",
                        "evidence": f"{first[0]['path']}:{first[0]['line']}: {index.line_text(first[0]['path'], first[0]['line'])}"
                                    + (" (its enclosing class)" if first[0].get("via") else ""),
                    }
                    if len(first) > 1:
                        suggestion["other_declarations"] = [f"{decl['path']}:{decl['line']}" for decl in first[1:]]
            basis = []
            if template:
                basis.append("authored template instance: the template's header must be visible where it is instantiated")
            if implicit:
                basis.append("implicit special member (no DWARF compile unit of its own, compiler-shaped body): its class's header")
            if len(names) >= 2:
                basis.append(f"{len(names)} units involved (ODR: a shared header)")
            wants_emit = template or len(names) >= 2 or (implicit and suggestion is not None)
            record = {
                "artifact": identity, "name": shape["name"], "class": label, "binding": sorted(_bindings(row) & COPY_BINDINGS),
                "owner": holder, "units": names, "unknown_referencers": unknown,
            }
            if vtable:
                record["via_vtable"] = vtable
            if body is not None:
                record["body_shape"] = body["shape"]
                if body["reasons"]:
                    record["body_reasons"] = body["reasons"]
                special_members[identity] = {"shape": body["shape"], "units": len(names), "unknown_referencers": len(unknown)}
            if not wants_emit:
                if body is not None and body["shape"] == "unknown" and suggestion is not None:
                    # Implicit, it would want an emit; user-written, none: not expected either way until decided.
                    unknown_shape.append(record | {"has_emit": identity in emits, "header": suggestion["header"]})
                elif body is not None and body["shape"] == "user-written" and identity in emits and not unknown:
                    user_written_emits.append(record | {"header": emits[identity].get("header")})
                if unknown and len(names) == 1:
                    undetermined.append(record | {"reason": f"one known unit; {len(unknown)} referencers have no unit yet"})
                continue
            expected += 1
            if identity in emits:
                continue
            if suggestion is not None:
                missing_emits.append(record | {"basis": basis, "suggested": suggestion, "reason": _emit_reason(row)})
                continue
            address = int(identity.rsplit(":", 1)[-1], 16)
            if any(address in addresses and says for addresses, says in groups):
                continue
            missing_notes.append(record | {
                "basis": basis,
                "note": f"{identity} {shape['name']}: used by {len(names)} unit{'s' if len(names) != 1 else ''} "
                        f"({', '.join(names)}); no header declares {label}",
            })
    wrong: list[dict[str, Any]] = []
    for row in plan.get("header_emits") or []:
        if not isinstance(row, dict) or not str(row.get("header") or "").startswith("src/"):
            continue
        cached = cache.rows.get(str(row.get("artifact")))
        shape = _shape(cached) if cached else None
        if shape is None:
            continue
        citations = _citations(row, index)
        if not citations:
            continue
        found = _declarations(index, shape)
        valid = {(decl["path"], decl["line"]) for decl in found} | {
            (decl["path"], decl["template_line"]) for decl in found if decl.get("template_line")
        }
        if any((path, line) in valid for path, line, _cited in citations):
            # Other citations may argue from bases or siblings; one line declaring the class is enough.
            continue
        _chain, _kinds, _template, label = _subject(shape)
        cited_lines = []
        for path, line, cited in citations:
            text = index.line_text(path, line)
            inside = any(decl["path"] == path and decl.get("end") and decl["line"] < line <= decl["end"] for decl in found)
            # A member's line inside the class body, a line declaring something else, or no such line.
            kind = "member line" if inside else "no such line" if text is None else "another line"
            cited_lines.append({"citation": cited, "line_text": text, "kind": kind})
        wrong.append({
            "artifact": row.get("artifact"), "name": shape["name"], "class": label, "header": row.get("header"),
            "citations": cited_lines,
            "declared_at": [f"{decl['path']}:{decl['line']}" for decl in sorted(found, key=lambda decl: (decl["path"], decl["line"]))],
        })
    return {
        "plan": plan_path,
        "counts": {
            "copies_checked": checked, "expected": expected, "missing_emits": len(missing_emits),
            "missing_notes": len(missing_notes), "wrong_citations": len(wrong), "undetermined": len(undetermined),
            **{f"shape_{shape.replace('-', '_')}": shapes[shape] for shape in SHAPES},
            "unknown_shape": len(unknown_shape), "user_written_emits": len(user_written_emits),
        },
        "missing_emits": missing_emits,
        "missing_notes": missing_notes,
        "wrong_citations": wrong,
        "undetermined": undetermined,
        "unknown_shape": unknown_shape,
        "user_written_emits": user_written_emits,
        # Every special member without its own DWARF unit the plan owns: its body shape and unit counts.
        "special_members": special_members,
    }


def draft_units(root: Path, graph: dict[str, Any] | None, cache_path: Path) -> dict[str, str]:
    """The whole-graph draft decision: artifact -> unit (rules version the draft defaults to)."""

    if graph is None:
        return {}
    from .source_cache import load_facts
    from .source_draft import DRAFT_RULES_VERSION, _Draft, _Workspace

    draft = _Draft(graph, load_facts(cache_path), _Workspace(root), DRAFT_RULES_VERSION)
    return {identity: value[0] for identity, value in draft.decided.items() if value and value[0]}


def emit_check(
    root: Path,
    cache_path: Path,
    *,
    items: list[str] | None = None,
    graph: dict[str, Any] | None = None,
    replace: dict[str, tuple[str, dict[str, Any]]] | None = None,
    statuses: dict[str, str] | None = None,
    word: Callable[[int], int] | None = None,
) -> dict[str, Any]:
    """The emit check over the plans of ``items`` (``None``: every plan file).

    Every plan file supplies unit decisions; ``replace`` substitutes plans in
    memory (``source plan validate`` checks the plan it was given).
    ``graph`` (the cache's graph) enables the whole-graph draft fallback.
    ``word`` reads loaded ELF words for body shapes (default: ``support/socom.elf``).
    """

    plans = load_plans(root, replace=replace)
    cache = _Cache(cache_path)
    if word is None:
        word = elf_words(root)
    index = HeaderIndex(root)
    headers = _Headers(root, plans)
    units = plan_units(plans)
    fallback = draft_units(root, graph, cache_path)
    chosen = sorted(plans) if items is None else items
    report: dict[str, Any] = {
        "kind": EMIT_CHECK_KIND,
        "version": EMIT_CHECK_VERSION,
        "graph_sha256": cache.graph_sha256,
        "rule": RULE,
        "unit_source": UNIT_SOURCE + ("" if graph is not None else " (no graph given: no draft fallback)"),
        "plans_read": len(plans),
        "counts": {},
        "plans": {},
    }
    totals: Counter[str] = Counter()
    for item in chosen:
        if item not in plans:
            raise SocomError(f"no plan of {item} under build/source-plans/")
        path, plan = plans[item]
        result = check_plan(
            path, plan, cache=cache, index=index, headers=headers, plan_unit=units, draft_unit=fallback, word=word
        )
        totals.update(result["counts"])
        if plan.get("graph_sha256") != cache.graph_sha256:
            # An accepted plan may cite the graph before a refresh that kept its slice (plan_graph_sha256).
            result["plan_graph_sha256"] = plan.get("graph_sha256")
        if statuses is not None:
            result["status"] = statuses.get(item)
        report["plans"][item] = result
    report["counts"] = {"plans": len(chosen), **{key: totals[key] for key in (
        "copies_checked", "expected", "missing_emits", "missing_notes", "wrong_citations", "undetermined",
        "shape_implicit", "shape_user_written", "shape_unknown", "unknown_shape", "user_written_emits")}}
    report["body_shape_source"] = (
        "support/socom.elf instructions and the cache's relocations" if word is not None else "no ELF: every body shape unknown"
    )
    report["counts"]["plans_with_findings"] = sum(
        1 for result in report["plans"].values()
        if any((result.get("counts") or {}).get(key) for key in ("missing_emits", "missing_notes", "wrong_citations"))
    )
    return report


def review_note(result: dict[str, Any], plan: str) -> str | None:
    """The one ``source plan validate`` review line for a plan's emit check (``None`` when clean)."""

    counts = result.get("counts") or {}
    found = [counts.get(key, 0) for key in ("missing_emits", "missing_notes", "wrong_citations")]
    if not any(found):
        return None
    shown = ", ".join(
        f"{row['artifact'].rsplit(':', 1)[-1]}" for key in ("missing_emits", "missing_notes", "wrong_citations") for row in result[key][:4]
    )
    return (
        f"emit check: {found[0]} missing header emits, {found[1]} missing 'no header declares' notes, {found[2]} wrong "
        f"header citations ({shown}); `source plan emit-check --plan {plan}` lists them"
    )
