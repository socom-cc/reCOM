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
  ``__dt__``, ``__as__`` without a DWARF compile unit of its own) when a
  header declares its class, (b) a copy that two or more units involve, and
  (c) an authored template instance (class-template member or function
  template instance), whatever the unit count;
* the header: the class's (template's) DWARF header unit, mapped to the
  workspace path (the direct ``src/<module>/<file>``, else the one file of
  that name in the module tree, else the path the plans already emit to,
  else the direct path as a new header), else the provisional header under
  ``src/`` that declares the class (``class|struct <Name>``, nested classes
  inside their enclosing scope; a ``template`` declaration for templates),
  with its line.  When (b) or (c) holds and no header is evidenced, the plan
  needs a note naming the artifact that says no header declares it;
* an existing workspace header-emit row citing ``<header>:<line>`` must cite
  a line that declares the artifact's class (or template, or free function).

The check reads the source query cache and the plan files; it writes
nothing.  ``source plan validate`` adds its counts as one review note.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable

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
EMIT_CHECK_VERSION = 1
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
    "implicit special member (__ct__/__dt__/__as__ without its own DWARF compile unit) when a header declares its "
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
            raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
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
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[line - 1].strip() if 0 < line <= len(lines) else None


# -- the check ------------------------------------------------------------------------------


class _Cache:
    """The cache rows the check reads, loaded once."""

    def __init__(self, path: Path) -> None:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
            self.graph_sha256 = (connection.execute("SELECT value FROM meta WHERE key = 'graph_sha256'").fetchone() or [None])[0]
            self.rows: dict[str, dict[str, Any]] = {}
            for identity, kind, address, binding, classification, library, header in connection.execute(
                "SELECT id, kind, address, binding, classification, library, emitted_from_header FROM artifacts"
            ):
                self.rows[identity] = {
                    "id": identity, "kind": kind, "address": address, "binding": binding, "classification": classification,
                    "library": library, "header": header, "names": [],
                }
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


def _special_shape(shape: dict[str, Any]) -> bool:
    """A destructor, default or copy constructor, or copy assignment: what the compiler may generate."""

    # ``Fv`` demangles to one void parameter: no parameters.
    params = [value for value in shape["params"] or [] if not (value.get("kind") == "builtin" and value.get("name") == "void")]
    copy = (
        len(params) == 1 and params[0].get("kind") == "class" and "R" in (params[0].get("modifiers") or [])
        and tuple(params[0].get("components") or ()) == shape["qualifier"]
    )
    if shape["name"].startswith("__dt__"):
        return not params
    if shape["name"].startswith("__ct__"):
        return not params or copy
    return shape["name"].startswith("__as__") and copy


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
) -> dict[str, Any]:
    """The emit check of one plan: missing emits, missing notes, wrong citations and undetermined copies."""

    emits = {row.get("artifact"): row for row in plan.get("header_emits") or [] if isinstance(row, dict)}
    groups = _note_groups(list(plan.get("notes") or []))
    missing_emits: list[dict[str, Any]] = []
    missing_notes: list[dict[str, Any]] = []
    undetermined: list[dict[str, Any]] = []
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
            implicit = shape["name"].startswith(SPECIAL_PREFIXES) and _special_shape(shape) and identity not in cache.dwarf
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
                basis.append("implicit special member (no DWARF compile unit of its own): its class's header")
            if len(names) >= 2:
                basis.append(f"{len(names)} units involved (ODR: a shared header)")
            wants_emit = template or len(names) >= 2 or (implicit and suggestion is not None)
            record = {
                "artifact": identity, "name": shape["name"], "class": label, "binding": sorted(_bindings(row) & COPY_BINDINGS),
                "owner": holder, "units": names, "unknown_referencers": unknown,
            }
            if vtable:
                record["via_vtable"] = vtable
            if not wants_emit:
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
        },
        "missing_emits": missing_emits,
        "missing_notes": missing_notes,
        "wrong_citations": wrong,
        "undetermined": undetermined,
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
) -> dict[str, Any]:
    """The emit check over the plans of ``items`` (``None``: every plan file).

    Every plan file supplies unit decisions; ``replace`` substitutes plans in
    memory (``source plan validate`` checks the plan it was given).
    ``graph`` (the cache's graph) enables the whole-graph draft fallback.
    """

    plans = load_plans(root, replace=replace)
    cache = _Cache(cache_path)
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
        result = check_plan(path, plan, cache=cache, index=index, headers=headers, plan_unit=units, draft_unit=fallback)
        totals.update(result["counts"])
        if plan.get("graph_sha256") != cache.graph_sha256:
            # An accepted plan may cite the graph before a refresh that kept its slice (plan_graph_sha256).
            result["plan_graph_sha256"] = plan.get("graph_sha256")
        if statuses is not None:
            result["status"] = statuses.get(item)
        report["plans"][item] = result
    report["counts"] = {"plans": len(chosen), **{key: totals[key] for key in (
        "copies_checked", "expected", "missing_emits", "missing_notes", "wrong_citations", "undetermined")}}
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
