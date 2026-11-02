"""C++ source scanning and declarator mangling for the stage 5 skeleton manifests (read-only).

``scan_text`` tokenizes one source file (comments, string and character
literals and preprocessor lines are tokens of their own) and walks its scopes:
namespaces, ``extern "C"`` blocks, class bodies with their member
declarations and in-class definitions, enums, typedefs, forward declarations,
function definitions with their exact spans, prototypes and file-scope
variables.  ``Program`` indexes the entities of every scanned file, plus the
class and namespace chains the ELF's mangled names prove, and resolves names
the way C++ lookup does for these declarations: innermost scope outwards, the
injected class name, the declarator-id's own scope for the parameters, and
typedefs substituted (``u32`` is ``unsigned int``; the MSL ``<cstdint>`` names
and ``size_t`` come from a small provider table).  ``function_symbol`` and
``data_symbol`` turn a declaration into the ``mw_mangle`` structured form, so
``mw_mangle.mangle`` gives the Metrowerks name it would get.

``definition_text`` goes the other way: the C++ declarator a skeleton writes
for a structured symbol, every name qualified so that the same lookup finds the
intended entity (a leading ``::`` where an inner scope would hide it, the
anonymous namespace left implicit).  The stage 5 S1 check is that round trip:
the written declarator, parsed back here, mangles to the ELF name.

Not modelled (each shows up as a mismatch, never as a silent match): base-class
scopes in lookup, template class members (their scope needs instance
arguments), macros used in declarators, and expressions in template arguments
other than integer literals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .mw_mangle import BUILTINS, INT128_CODE, MangleError, OPERATORS

# -- tokens --------------------------------------------------------------------------------

_TOKEN = re.compile(
    r"""
    (?P<nl>\n)
    |(?P<ws>[ \t\r\f\v]+)
    |(?P<lc>//[^\n]*)
    |(?P<bc>/\*.*?(?:\*/|\Z))
    |(?P<str>(?:L|u8|u|U)?"(?:\\.|[^"\\\n])*"?)
    |(?P<chr>(?:L|u8|u|U)?'(?:\\.|[^'\\\n])*'?)
    |(?P<id>[A-Za-z_$][A-Za-z0-9_$]*)
    |(?P<num>\.?\d(?:[eEpP][+-]|[\w.])*)
    |(?P<punct>::|->\*|->|\.\.\.|\.\*|<=|>=|==|!=|&&|\|\||\+\+|--|\+=|-=|\*=|/=|%=|&=|\|=|\^=|.)
    """,
    re.S | re.X,
)


@dataclass(frozen=True)
class Token:
    kind: str  # id num str chr pp punct
    text: str
    start: int
    end: int
    line: int


def tokenize(text: str) -> tuple[list[Token], int]:
    """(code tokens, comment line count); preprocessor lines are ``pp`` tokens."""

    tokens: list[Token] = []
    comment_lines = 0
    line = 1
    position = 0
    at_line_start = True
    length = len(text)
    while position < length:
        if at_line_start:
            spaces = position
            while spaces < length and text[spaces] in " \t":
                spaces += 1
            if spaces < length and text[spaces] == "#":
                end = spaces
                while True:
                    newline = text.find("\n", end)
                    if newline < 0:
                        end = length
                        break
                    if text[newline - 1 : newline] == "\\" or text[newline - 2 : newline] == "\\\r":
                        end = newline + 1
                        continue
                    end = newline
                    break
                tokens.append(Token("pp", text[spaces:end].strip(), spaces, end, line))
                line += text.count("\n", position, end)
                position = end
                continue
        match = _TOKEN.match(text, position)
        assert match is not None
        kind = match.lastgroup
        value = match.group()
        if kind == "nl":
            line += 1
            at_line_start = True
        elif kind == "ws":
            pass
        elif kind in ("lc", "bc"):
            comment_lines += value.count("\n") + 1
            line += value.count("\n")
        else:
            at_line_start = False
            tokens.append(Token(kind, value, match.start(), match.end(), line))
            line += value.count("\n")
        position = match.end()
    return tokens, comment_lines


def _brackets(tokens: list[Token]) -> dict[int, int]:
    """Matching bracket indices, both ways; unmatched brackets map to nothing."""

    match: dict[int, int] = {}
    stacks: dict[str, list[int]] = {"(": [], "[": [], "{": []}
    closing = {")": "(", "]": "[", "}": "{"}
    for index, token in enumerate(tokens):
        if token.kind != "punct":
            continue
        if token.text in stacks:
            stacks[token.text].append(index)
        elif token.text in closing and stacks[closing[token.text]]:
            opening = stacks[closing[token.text]].pop()
            match[opening] = index
            match[index] = opening
    return match


# -- the scan ------------------------------------------------------------------------------

CLASS_KEYS = ("class", "struct", "union")
ACCESS = ("public", "protected", "private")


@dataclass
class Definition:
    """A function definition (namespace scope, or in a class body)."""

    tokens: list[Token]  # the head: up to the body's opening brace
    scope: tuple[tuple[str, Any], ...]
    template: bool
    start: int  # offset of the first head token (template header included)
    end: int  # offset just after the closing brace
    line: int
    end_line: int
    body_start: int
    in_class: tuple[str, ...] | None = None


@dataclass
class Declaration:
    """A namespace-scope or member declaration statement (no body)."""

    tokens: list[Token]
    scope: tuple[tuple[str, Any], ...]
    start: int
    end: int
    line: int
    brace_init: bool = False
    in_class: tuple[str, ...] | None = None


@dataclass
class ClassDef:
    chain: tuple[str, ...]
    key: str
    line: int
    end_line: int
    start: int
    end: int
    template: bool
    bases: str
    members: list[Any] = field(default_factory=list)  # Declaration | Definition


@dataclass
class FileScan:
    path: str
    text: str
    tag: str  # the unnamed-namespace tag: the file name with '.' -> '_'
    tokens: list[Token]
    comment_lines: int
    classes: list[ClassDef] = field(default_factory=list)
    enums: list[tuple[str, ...]] = field(default_factory=list)
    typedefs: list[Declaration] = field(default_factory=list)
    forwards: list[tuple[str, ...]] = field(default_factory=list)
    namespaces: list[tuple[str, ...]] = field(default_factory=list)
    definitions: list[Definition] = field(default_factory=list)
    declarations: list[Declaration] = field(default_factory=list)
    preprocessor: dict[str, int] = field(default_factory=dict)
    includes: list[str] = field(default_factory=list)


def file_tag(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].replace(".", "_")


def scope_chain(scope: tuple[tuple[str, Any], ...], tag: str) -> tuple[str, ...]:
    """The entity chain of a scope stack: named namespaces and classes, ``@unnamed@<tag>@``."""

    chain = []
    for kind, value in scope:
        if kind == "ns":
            chain.append(value if value is not None else f"@unnamed@{tag}@")
        elif kind == "class":
            chain.append(value)
    return tuple(chain)


def _top_level(tokens: list[Token]) -> list[str]:
    """Token texts outside parentheses and brackets (the brackets themselves kept)."""

    texts = []
    depth = 0
    for token in tokens:
        text = token.text
        if token.kind == "punct" and text in ("(", "["):
            if depth == 0:
                texts.append(text)
            depth += 1
        elif token.kind == "punct" and text in (")", "]"):
            depth = max(0, depth - 1)
            if depth == 0:
                texts.append(text)
        elif depth == 0:
            texts.append(text)
    return texts


class _Walker:
    def __init__(self, scan: FileScan) -> None:
        self.scan = scan
        self.tokens = scan.tokens
        self.match = _brackets(self.tokens)

    def code(self, low: int, high: int) -> list[Token]:
        return [token for token in self.tokens[low:high] if token.kind != "pp"]

    def walk(self, low: int, high: int, scope: tuple[tuple[str, Any], ...]) -> None:
        index = low
        start = low
        in_class = bool(scope) and scope[-1][0] == "class"
        while index < high:
            token = self.tokens[index]
            if token.kind == "pp":
                word = re.match(r"#\s*(\w+)", token.text)
                key = word.group(1) if word else "other"
                key = "conditional" if key in ("if", "ifdef", "ifndef", "elif", "else", "endif") else key
                self.scan.preprocessor[key] = self.scan.preprocessor.get(key, 0) + 1
                included = re.match(r'#\s*include\s*[<"]([^>"]+)[>"]', token.text)
                if included:
                    self.scan.includes.append(included.group(1))
                index += 1
                if start == index - 1:
                    start = index
                continue
            text = token.text if token.kind == "punct" else None
            if in_class and token.kind == "id" and token.text in ACCESS and index + 1 < high and self.tokens[index + 1].text == ":":
                index += 2
                start = index
                continue
            if text == ";":
                self.statement(start, index, scope)
                index += 1
                start = index
            elif text == "{":
                index = self.block(start, index, scope, high)
                start = index
            elif text == "}":
                index += 1
                start = index
            elif text in ("(", "[") and index in self.match:
                index = self.match[index] + 1
            else:
                index += 1

    def _template(self, head: list[Token]) -> tuple[list[Token], bool]:
        if not head or head[0].text != "template":
            return head, False
        depth = 0
        for position, token in enumerate(head[1:], start=1):
            if token.text == "<":
                depth += 1
            elif token.text == ">":
                depth -= 1
                if depth == 0:
                    return head[position + 1 :], True
        return [], True

    def _semicolon(self, index: int, high: int) -> int:
        while index < high:
            text = self.tokens[index].text
            if text == ";" and self.tokens[index].kind == "punct":
                return index
            if text in ("(", "[", "{") and index in self.match:
                index = self.match[index]
            index += 1
        return high

    def block(self, start: int, open_index: int, scope: tuple[tuple[str, Any], ...], high: int) -> int:
        close = self.match.get(open_index)
        if close is None or close >= high:
            return high
        full = self.code(start, open_index)
        head, template = self._template(full)
        texts = _top_level(head)
        chain = scope_chain(scope, self.scan.tag)
        in_class = bool(scope) and scope[-1][0] == "class"
        if not head:
            return close + 1
        if texts[0] == "namespace" or texts[:2] == ["inline", "namespace"]:
            names = [token.text for token in head if token.kind == "id" and token.text not in ("inline", "namespace")]
            name = names[0] if names else None
            inner = scope + (("ns", name),)
            self.scan.namespaces.append(scope_chain(inner, self.scan.tag))
            self.walk(open_index + 1, close, inner)
            return close + 1
        if texts[:2] == ["extern", '"C"'] and len(texts) == 2:
            self.walk(open_index + 1, close, scope + (("externc", None),))
            return close + 1
        typedef = texts[0] == "typedef"
        body = head[1:] if typedef else head
        keys = [position for position, token in enumerate(body) if token.text in CLASS_KEYS]
        if keys and "(" not in texts and "=" not in texts:
            position = keys[0]
            key = body[position].text
            after = body[position + 1 :]
            name = after[0].text if after and after[0].kind == "id" and after[0].text != "final" else None
            bases = ""
            for offset, token in enumerate(after):
                if token.text == ":" and token.kind == "punct":
                    bases = " ".join(item.text for item in after[offset + 1 :])
                    break
            semicolon = self._semicolon(close + 1, high)
            trailing = self.code(close + 1, semicolon)
            if name is None and typedef and trailing and trailing[0].kind == "id":
                name = trailing[0].text  # typedef struct { ... } Name;
            klass = ClassDef(
                chain=chain + (name,) if name else (),
                key=key,
                line=head[0].line,
                end_line=self.tokens[close].line,
                start=full[0].start,
                end=self.tokens[close].end,
                template=template,
                bases=bases,
            )
            self.scan.classes.append(klass)
            inner = scope + (("class", name or "<anonymous>"),)
            before = len(self.scan.declarations), len(self.scan.definitions), len(self.scan.typedefs)
            self.walk(open_index + 1, close, inner)
            if name:
                klass.members = [
                    row for row in self.scan.declarations[before[0] :] + self.scan.definitions[before[1] :] if row.in_class == klass.chain
                ]
            if typedef and trailing:
                if klass.chain and trailing[0].text != klass.chain[-1]:
                    self.scan.typedefs.append(
                        Declaration([head[0]] + body[: position + 2] + trailing, scope, full[0].start,
                                    self.tokens[semicolon].end if semicolon < high else self.tokens[close].end, head[0].line)
                    )
            elif trailing and not in_class:
                # struct { ... } variable;  -- a variable of the class type
                self.scan.declarations.append(
                    Declaration(body[: position + 2] + trailing if name else trailing, scope, full[0].start,
                                self.tokens[semicolon].end if semicolon < high else self.tokens[close].end, head[0].line,
                                brace_init=False)
                )
            return semicolon + 1 if semicolon < high else close + 1
        if body and body[0].text == "enum":
            name = body[1].text if len(body) > 1 and body[1].kind == "id" and body[1].text != "class" else None
            if len(body) > 2 and body[1].text == "class" and body[2].kind == "id":
                name = body[2].text
            semicolon = self._semicolon(close + 1, high)
            trailing = self.code(close + 1, semicolon)
            if name is None and typedef and trailing and trailing[0].kind == "id":
                name = trailing[0].text
            elif name and typedef and trailing and trailing[0].text != name:
                self.scan.typedefs.append(
                    Declaration([head[0], body[0], body[1]] + trailing, scope, full[0].start,
                                self.tokens[semicolon].end if semicolon < high else self.tokens[close].end, head[0].line)
                )
            if name:
                self.scan.enums.append(chain + (name,))
            return semicolon + 1 if semicolon < high else close + 1
        if any(text == "=" and (index == 0 or texts[index - 1] != "operator") for index, text in enumerate(texts)):
            semicolon = self._semicolon(close + 1, high)
            self.statement(start, semicolon, scope, brace_init=True)
            return semicolon + 1 if semicolon < high else close + 1
        if "(" in texts:
            definition = Definition(
                tokens=full,
                scope=scope,
                template=template,
                start=full[0].start,
                end=self.tokens[close].end,
                line=full[0].line,
                end_line=self.tokens[close].line,
                body_start=self.tokens[open_index].start,
                in_class=chain if in_class else None,
            )
            self.scan.definitions.append(definition)
            return close + 1
        return close + 1

    def statement(self, start: int, end: int, scope: tuple[tuple[str, Any], ...], *, brace_init: bool = False) -> None:
        tokens = self.code(start, end)
        if not tokens:
            return
        texts = [token.text for token in tokens]
        chain = scope_chain(scope, self.scan.tag)
        in_class = bool(scope) and scope[-1][0] == "class"
        stop = self.tokens[end].end if end < len(self.tokens) else tokens[-1].end
        row = Declaration(tokens, scope, tokens[0].start, stop, tokens[0].line, brace_init=brace_init,
                          in_class=chain if in_class else None)
        if texts[0] == "typedef":
            self.scan.typedefs.append(row)
            return
        if texts[0] in ("using", "friend", "static_assert", "template", "namespace"):
            return
        if texts[0] in CLASS_KEYS and len(texts) == 2 and tokens[1].kind == "id":
            self.scan.forwards.append(chain + (texts[1],))
            return
        if texts[0] == "enum" and len(texts) >= 2 and "{" not in texts:
            return
        self.scan.declarations.append(row)


def scan_text(path: str, text: str) -> FileScan:
    tokens, comments = tokenize(text)
    scan = FileScan(path=path, text=text, tag=file_tag(path), tokens=tokens, comment_lines=comments)
    _Walker(scan).walk(0, len(tokens), ())
    return scan


# -- builtin types, provider typedefs ------------------------------------------------------

_BUILTIN_WORDS = frozenset(
    {"void", "bool", "char", "short", "int", "long", "signed", "unsigned", "float", "double", "wchar_t", "__int128"}
)
_SPECIFIERS = frozenset(
    {"static", "extern", "inline", "virtual", "explicit", "friend", "typedef", "mutable", "register", "auto", "__inline",
     "__inline__", "asm", "__asm", "constexpr"}
)
_CV = {"const": "C", "volatile": "V"}


def builtin_node(words: list[str]) -> dict[str, Any]:
    """The mw_mangle node of a builtin type spelling (``unsigned long int`` ...)."""

    unsigned = "unsigned" in words
    signed = "signed" in words
    rest = [word for word in words if word not in ("signed", "unsigned")]
    longs = rest.count("long")
    base = [word for word in rest if word not in ("long", "int")] or (["int"] if not longs or "int" in rest else [])
    name = base[0] if base else None
    if name == "__int128":
        return {"t": "builtin", "code": INT128_CODE}
    if name == "double" and longs:
        return {"t": "builtin", "code": "r"}
    if name in ("void", "bool", "float", "double", "wchar_t"):
        return {"t": "builtin", "code": {"void": "v", "bool": "b", "float": "f", "double": "d", "wchar_t": "w"}[name]}
    if name == "char":
        code = "c"
    elif name == "short":
        code = "s"
    elif longs >= 2:
        code = "x"
    elif longs == 1:
        code = "l"
    else:
        code = "i"
    node: dict[str, Any] = {"t": "builtin", "code": code}
    if unsigned:
        node["sign"] = "U"
    elif signed and code == "c":
        node["sign"] = "S"
    return node


def _b(code: str, sign: str | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"t": "builtin", "code": code}
    if sign:
        node["sign"] = sign
    return node


# The MSL/SDK typedefs provisional sources use without declaring them (``<cstdint>``, ``<stddef.h>``,
# ``<sys/types.h>``, the PS2 prefix header).  ``operator new(unsigned int)`` (``__nw__FUi``) fixes size_t.
PROVIDER_TYPEDEFS: dict[str, dict[str, Any]] = {
    "int8_t": _b("c", "S"), "uint8_t": _b("c", "U"), "int16_t": _b("s"), "uint16_t": _b("s", "U"),
    "int32_t": _b("i"), "uint32_t": _b("i", "U"), "int64_t": _b("l"), "uint64_t": _b("l", "U"),
    "intptr_t": _b("i"), "uintptr_t": _b("i", "U"), "size_t": _b("i", "U"), "ptrdiff_t": _b("i"),
    "u_char": _b("c", "U"), "u_short": _b("s", "U"), "u_int": _b("i", "U"), "u_long": _b("l", "U"),
    "u_long128": _b(INT128_CODE), "u_int128": _b(INT128_CODE),
    # newlib's stdio: the ELF spells FILE parameters P7__sFILE.
    "FILE": {"t": "named", "name": [{"name": "__sFILE"}]},
}
_STD = {"name": "std"}


def _std(name: str, args: list[dict[str, Any]]) -> dict[str, Any]:
    return {"t": "named", "name": [_STD, {"name": name, "args": args}]}


def _std_defaults(name: str, args: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """MSL's default template arguments, filled in the way the compiler mangles them."""

    if name in ("vector", "list", "deque") and len(args) == 1:
        return args + [_std("allocator", args[:1])]
    if name == "set" and 1 <= len(args) < 3:
        args = args + ([_std("less", args[:1])] if len(args) == 1 else [])
        return args + [_std("allocator", args[:1])]
    if name == "map" and 2 <= len(args) < 4:
        key = dict(args[0])
        key["cv"] = key.get("cv", "") + "C"
        args = args + ([_std("less", args[:1])] if len(args) == 2 else [])
        return args + [_std("allocator", [_std("pair", [key, args[1]])])]
    if name == "basic_string" and len(args) == 1:
        return args + [_std("char_traits", args[:1]), _std("allocator", args[:1])]
    return args


# -- the program index and lookup ----------------------------------------------------------


class Unresolvable(ValueError):
    pass


def _component_base(component: dict[str, Any]) -> str:
    return f"@unnamed@{component['unnamed']}@" if "unnamed" in component else component["name"]


def chain_of(components: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(_component_base(row) for row in components)


def _component(base: str) -> dict[str, Any]:
    if base.startswith("@unnamed@") and base.endswith("@"):
        return {"unnamed": base[len("@unnamed@") : -1]}
    return {"name": base}


class Program:
    """Every scanned file's entities, and C++ lookup over them."""

    def __init__(self, scans: Iterable[FileScan], elf_chains: Iterable[tuple[str, ...]] = ()) -> None:
        self.scans = list(scans)
        self.kinds: dict[tuple[str, ...], set[str]] = {}
        self.typedefs: dict[tuple[str, ...], tuple[Declaration, str]] = {}
        self._typedef_types: dict[tuple[str, ...], dict[str, Any] | None] = {}
        self.class_defs: dict[tuple[str, ...], list[tuple[str, ClassDef]]] = {}
        for scan in self.scans:
            for chain in scan.namespaces:
                self._add(chain, "namespace")
            for klass in scan.classes:
                if klass.chain:
                    self._add(klass.chain, "template" if klass.template else "class")
                    self.class_defs.setdefault(klass.chain, []).append((scan.path, klass))
            for chain in scan.enums:
                self._add(chain, "enum")
            for chain in scan.forwards:
                self._add(chain, "forward")
        for scan in self.scans:
            for row in scan.typedefs:
                for name in typedef_names(row):
                    chain = scope_chain(row.scope, scan.tag) + (name,)
                    if chain not in self.kinds or self.kinds[chain] <= {"forward"}:
                        self._add(chain, "typedef")
                        self.typedefs.setdefault(chain, (row, scan.tag))
        for chain in elf_chains:
            for index in range(1, len(chain) + 1):
                self.kinds.setdefault(chain[:index], set()).add("elf")

    def _add(self, chain: tuple[str, ...], kind: str) -> None:
        self.kinds.setdefault(chain, set()).add(kind)

    def is_namespace(self, chain: tuple[str, ...]) -> bool:
        return "namespace" in self.kinds.get(chain, ()) or (bool(chain) and chain[-1].startswith("@unnamed@"))

    def kind_of(self, chain: tuple[str, ...]) -> set[str]:
        return self.kinds.get(chain, set())

    def lookup(self, name: str, scopes: list[tuple[str, ...]]) -> tuple[str, ...] | None:
        for scope in scopes:
            if scope and scope[-1] == name and not self.is_namespace(scope):
                return scope  # the injected class name
            candidate = scope + (name,)
            if candidate in self.kinds:
                return candidate
        return None

    def typedef_type(self, chain: tuple[str, ...]) -> dict[str, Any] | None:
        if chain in self._typedef_types:
            return self._typedef_types[chain]
        self._typedef_types[chain] = None  # cycle guard
        row, tag = self.typedefs[chain]
        try:
            parser = _Parser(row.tokens[1:], self, scopes_of(row.scope, tag), tag)
            _specifiers, base = parser.decl_specifiers()
            found = None
            while True:
                name, node = parser.declarator(base)
                if name is not None and name.components and name.components[-1][0] == chain[-1]:
                    found = node
                    break
                if not parser.accept(","):
                    break
        except (Unresolvable, MangleError, IndexError):
            found = None
        self._typedef_types[chain] = found
        return found


def scopes_of(scope: tuple[tuple[str, Any], ...], tag: str) -> list[tuple[str, ...]]:
    chain = scope_chain(scope, tag)
    return [chain[:index] for index in range(len(chain), -1, -1)]


def typedef_names(row: Declaration) -> list[str]:
    """The names a typedef declares, read syntactically (no lookup)."""

    try:
        parser = _Parser(row.tokens[1:], None, [()], "")
        _specifiers, base = parser.decl_specifiers()
        names = []
        while True:
            name, _node = parser.declarator(base)
            if name is not None and name.components and len(name.components) == 1:
                names.append(name.components[0][0])
            if not parser.accept(","):
                break
        return names
    except (Unresolvable, MangleError, IndexError):
        return []


# -- declarations --------------------------------------------------------------------------


@dataclass
class QualifiedName:
    components: list[tuple[str, list[Any] | None]]  # (base, template arguments) per component
    rooted: bool = False
    special: str | None = None  # destructor, operator, conversion
    operator: str | None = None  # the mw_mangle operator code
    conversion: dict[str, Any] | None = None


_OPERATOR_CODES = {symbol: code for code, symbol in OPERATORS.items()}


class _Parser:
    """Recursive descent over one declaration's tokens; ``program`` None reads syntax only."""

    def __init__(self, tokens: list[Token], program: Program | None, scopes: list[tuple[str, ...]], tag: str, *, klass: tuple[str, ...] | None = None) -> None:
        self.tokens = [token for token in tokens if token.kind != "pp"]
        self.position = 0
        self.program = program
        self.scopes = scopes
        self.tag = tag
        self.klass = klass
        self.declarator_scope: tuple[str, ...] | None = None
        self.in_parameters = 0
        self.data_context = False  # a variable's ``(`` may open a direct initializer
        self.parameter_names: list[str | None] | None = None  # the first outermost parameter list's names

    # token helpers
    def peek(self, offset: int = 0) -> str:
        index = self.position + offset
        return self.tokens[index].text if index < len(self.tokens) else ""

    def kind(self, offset: int = 0) -> str:
        index = self.position + offset
        return self.tokens[index].kind if index < len(self.tokens) else ""

    def take(self) -> str:
        if self.position >= len(self.tokens):
            raise Unresolvable("unexpected end of declaration")
        text = self.tokens[self.position].text
        self.position += 1
        return text

    def accept(self, text: str) -> bool:
        if self.peek() == text:
            self.position += 1
            return True
        return False

    def expect(self, text: str) -> None:
        if not self.accept(text):
            raise Unresolvable(f"expected {text!r} at {self.peek()!r}")

    def at_end(self) -> bool:
        return self.position >= len(self.tokens)

    def _adjacent(self, offset: int) -> bool:
        first = self.position + offset
        return first + 1 < len(self.tokens) and self.tokens[first].end == self.tokens[first + 1].start

    # names
    def _template_arguments(self) -> list[Any]:
        self.expect("<")
        arguments: list[Any] = []
        if self.accept(">"):
            return arguments
        while True:
            if self.kind() == "num" or (self.peek() == "-" and self.kind(1) == "num"):
                value = self.take()
                if value == "-":
                    value += self.take()
                arguments.append({"t": "value", "value": str(int(value.rstrip("uUlL"), 0))})
            elif self.peek() in ("true", "false"):
                arguments.append({"t": "value", "value": "1" if self.take() == "true" else "0"})
            else:
                arguments.append(self.type_id())
            if self.accept(">"):
                return arguments
            self.expect(",")

    def qualified_name(self) -> QualifiedName:
        name = QualifiedName(components=[])
        if self.accept("::"):
            name.rooted = True
        while True:
            if self.peek() == "~":
                self.take()
                name.components.append(("~" + self.take(), None))
                name.special = "destructor"
                return name
            if self.peek() == "operator":
                self.take()
                self._operator(name)
                return name
            if self.kind() != "id":
                raise Unresolvable(f"expected a name at {self.peek()!r}")
            base = self.take()
            arguments = None
            if self.peek() == "<" and self._template_follows():
                arguments = self._template_arguments()
            name.components.append((base, arguments))
            if self.peek() == "::" and self.peek(1) != "*":
                self.take()
                continue
            return name

    def _template_follows(self) -> bool:
        """Whether ``<`` opens template arguments: its ``>`` comes before ``;``, a brace or an unopened ``)``."""

        depth = 0
        paren = 0
        for index in range(self.position, len(self.tokens)):
            text = self.tokens[index].text
            if text == "(":
                paren += 1
            elif text == ")":
                if paren == 0:
                    return False
                paren -= 1
            elif paren == 0 and text == "<":
                depth += 1
            elif paren == 0 and text == ">":
                depth -= 1
                if depth == 0:
                    return True
            elif text in (";", "{", "}"):
                return False
        return False

    def _operator(self, name: QualifiedName) -> None:
        text = self.peek()
        if text in ("new", "delete"):
            self.take()
            if self.peek() == "[" and self.peek(1) == "]":
                self.take(), self.take()
                text += "[]"
            symbol = text
        elif text == "(" and self.peek(1) == ")":
            self.take(), self.take()
            symbol = "()"
        elif text == "[" and self.peek(1) == "]":
            self.take(), self.take()
            symbol = "[]"
        elif self.kind() == "punct" and text not in ("(",):
            symbol = self.take()
            # The tokenizer splits << and >>: join adjacent punctuation of one operator.
            while self.position < len(self.tokens) and self.tokens[self.position - 1].end == self.tokens[self.position].start \
                    and (symbol + self.peek()) in _OPERATOR_CODES and self.peek() != "(":
                symbol += self.take()
        else:
            name.special = "conversion"
            specifiers, base = self.decl_specifiers(conversion=True)
            node = base
            while self.peek() in ("*", "&"):
                kind = "pointer" if self.take() == "*" else "reference"
                node = {"t": kind, "to": node}
                cv = self.cv()
                if cv:
                    node["cv"] = cv
            name.conversion = node
            name.components.append(("operator", None))
            return
        code = _OPERATOR_CODES.get(symbol)
        if code is None:
            raise Unresolvable(f"unknown operator {symbol!r}")
        name.special = "operator"
        name.operator = code
        name.components.append(("operator" + symbol, None))

    # types
    def cv(self) -> str:
        found = ""
        while self.peek() in _CV:
            found += _CV[self.take()]
        return found

    def _ctor_name_follows(self) -> bool:
        """Whether a constructor, destructor or conversion declarator-id starts here (no return type)."""

        if self.peek() == "~" or self.peek() == "operator":
            return True
        mark = self.position
        try:
            name = self.qualified_name()
        except (Unresolvable, MangleError):
            self.position = mark
            return False
        follows = self.peek() == "("
        self.position = mark
        if not follows or name.special in ("destructor", "operator", "conversion"):
            return follows
        bases = [base for base, _args in name.components]
        if len(bases) >= 2 and bases[-1] == bases[-2]:
            return True
        return self.klass is not None and len(bases) == 1 and bases[0] == self.klass[-1]

    def decl_specifiers(self, *, conversion: bool = False) -> tuple[set[str], dict[str, Any] | None]:
        specifiers: set[str] = set()
        cv = ""
        words: list[str] = []
        named: dict[str, Any] | None = None
        while not self.at_end():
            text = self.peek()
            if text in _SPECIFIERS and not conversion:
                specifiers.add(self.take())
            elif self.kind() == "str" and "extern" in specifiers and named is None and not words:
                if self.take() == '"C"':
                    specifiers.add('extern "C"')  # a linkage specification on one declaration
            elif text in _CV:
                cv += _CV[self.take()]
            elif text in _BUILTIN_WORDS and named is None:
                words.append(self.take())
            elif text in CLASS_KEYS + ("enum", "typename") and named is None and not words:
                self.take()
                if self.peek() == "class":
                    self.take()
                named = self.named_type(self.qualified_name())
            elif (self.kind() == "id" or text == "::") and named is None and not words and text not in ("operator",):
                if not conversion and not self.in_parameters and self._ctor_name_follows():
                    break
                named = self.named_type(self.qualified_name())
            else:
                break
        if words:
            base: dict[str, Any] | None = builtin_node(words)
        else:
            base = named
        if base is not None and cv:
            base = dict(base)
            base["cv"] = "".join(sorted(set(base.get("cv", "") + cv), key="CV".index))
        return specifiers, base

    def type_id(self) -> dict[str, Any]:
        _specifiers, base = self.decl_specifiers()
        if base is None:
            raise Unresolvable(f"expected a type at {self.peek()!r}")
        _name, node = self.declarator(base, abstract=True)
        return node

    def named_type(self, name: QualifiedName) -> dict[str, Any]:
        """The node of a written type name: resolved, typedefs substituted."""

        if name.special:
            raise Unresolvable("an operator or destructor is not a type")
        bases = [base for base, _args in name.components]
        if self.program is None:
            return {"t": "named", "name": [{"name": base} for base in bases]}
        program = self.program
        scopes = self._lookup_scopes()
        first = () if name.rooted else program.lookup(bases[0], scopes)
        if first is None or name.rooted:
            prefix: tuple[str, ...] = ()
            first = (bases[0],)
        else:
            prefix = first[:-1]
        chain = first + tuple(bases[1:])
        last_args = name.components[-1][1]
        if chain in program.typedefs and last_args is None:
            node = program.typedef_type(chain)
            if node is None:
                raise Unresolvable(f"typedef {'::'.join(chain)} does not resolve")
            return node
        if not program.kinds.get(chain) and len(chain) == 1 and chain[0] in PROVIDER_TYPEDEFS:
            return dict(PROVIDER_TYPEDEFS[chain[0]])
        if chain == ("std", "string") and last_args is None:
            return _std("basic_string", _std_defaults("basic_string", [_b("c")]))
        components = [_component(base) for base in prefix]
        for index, (base, arguments) in enumerate(name.components):
            row = _component(base)
            if arguments is not None:
                if len(prefix) + index == 1 and chain[0] == "std":
                    arguments = _std_defaults(base, arguments)
                row["args"] = arguments
            components.append(row)
        return {"t": "named", "name": components}

    def _lookup_scopes(self) -> list[tuple[str, ...]]:
        if self.declarator_scope is None:
            return self.scopes
        chain = self.declarator_scope
        first = [chain[:index] for index in range(len(chain), 0, -1)]
        return first + [scope for scope in self.scopes if scope not in first]

    def resolve_scope(self, components: list[tuple[str, list[Any] | None]], rooted: bool) -> list[dict[str, Any]]:
        """The full scope chain of a declarator-id's qualifier."""

        bases = [base for base, _args in components]
        if self.program is None:
            return [{"name": base} for base in bases]
        first = None if rooted else self.program.lookup(bases[0], self.scopes)
        prefix = first[:-1] if first else ()
        rows = [_component(base) for base in prefix]
        for base, arguments in components:
            row = _component(base)
            if arguments is not None:
                row["args"] = arguments
            rows.append(row)
        return rows

    def declarator(self, base: dict[str, Any] | None, *, abstract: bool = False) -> tuple[QualifiedName | None, dict[str, Any]]:
        """(the declarator-id or None, the declared type) for one declarator over ``base``."""

        pointers: list[tuple[str, Any, str]] = []
        while True:
            if self.peek() == "*":
                self.take()
                pointers.append(("pointer", None, self.cv()))
            elif self.peek() == "&":
                self.take()
                self.cv()
                pointers.append(("reference", None, ""))
            elif self._member_pointer_follows():
                owner = self.qualified_name()
                self.expect("::")
                self.expect("*")
                owner_node = self.named_type(owner) if self.program is not None else {"t": "named", "name": [{"name": b} for b, _ in owner.components]}
                pointers.append(("member_pointer", owner_node["name"], self.cv()))
            else:
                break
        name: QualifiedName | None = None
        inner: tuple[int, int] | None = None
        if self.peek() == "(" and self._nested_declarator():
            open_at = self.position
            depth = 0
            for index in range(self.position, len(self.tokens)):
                if self.tokens[index].text == "(":
                    depth += 1
                elif self.tokens[index].text == ")":
                    depth -= 1
                    if depth == 0:
                        inner = (open_at + 1, index)
                        self.position = index + 1
                        break
            if inner is None:
                raise Unresolvable("unbalanced declarator")
        elif self.kind() == "id" or self.peek() in ("::", "~", "operator"):
            name = self.qualified_name()
            if len(name.components) > 1 or name.rooted:
                scope = self.resolve_scope(name.components[:-1], name.rooted)
                self.declarator_scope = chain_of(scope)
                name.scope_nodes = scope  # type: ignore[attr-defined]
        suffixes: list[tuple[str, Any, str]] = []
        while True:
            if self.peek() == "(":
                mark = self.position
                self.take()
                try:
                    params = self.parameters()
                except Unresolvable:
                    if not self.data_context or suffixes:
                        raise
                    self.position = mark  # CFoo g_foo(1, 2): a direct initializer
                    break
                cv = self.cv()
                if self.peek() == "throw":
                    self.take()
                    if self.peek() == "(":
                        self._skip_balanced()
                suffixes.append(("function", params, cv))
            elif self.peek() == "[":
                self.take()
                size_text = []
                while not self.at_end() and self.peek() != "]":
                    size_text.append(self.take())
                self.expect("]")
                size = int(size_text[0].rstrip("uUlL"), 0) if len(size_text) == 1 and size_text[0][:1].isdigit() else None
                suffixes.append(("array", size, ""))
            else:
                break
        node = base
        for kind, extra, cv in pointers:
            node = self._wrap(kind, extra, cv, node)
        for kind, extra, cv in reversed(suffixes):
            node = self._wrap(kind, extra, cv, node)
        if inner is not None:
            saved = self.position
            sub = _Parser(self.tokens[inner[0] : inner[1]], self.program, self.scopes, self.tag, klass=self.klass)
            name, node = sub.declarator(node, abstract=abstract)
            self.declarator_scope = sub.declarator_scope or self.declarator_scope
            self.position = saved
        return name, node

    def _skip_balanced(self) -> None:
        depth = 0
        while not self.at_end():
            text = self.take()
            if text == "(":
                depth += 1
            elif text == ")":
                depth -= 1
                if depth == 0:
                    return

    def _member_pointer_follows(self) -> bool:
        if self.kind() != "id" and self.peek() != "::":
            return False
        depth = 0
        for index in range(self.position, len(self.tokens) - 1):
            text = self.tokens[index].text
            if text == "<":
                depth += 1
            elif text == ">":
                depth -= 1
            elif depth == 0 and text == "::" and self.tokens[index + 1].text == "*":
                return True
            elif depth == 0 and not (self.tokens[index].kind == "id" or text == "::"):
                return False
        return False

    def _nested_declarator(self) -> bool:
        """``(`` starts a nested declarator (``(*f)(int)``), not a parameter list."""

        following = self.peek(1)
        if following in ("*", "&"):
            return True
        if following == "(":
            return True
        if self.kind(1) == "id" and self.peek(2) == ")" and following not in _BUILTIN_WORDS and following not in _CV:
            # ``void (fixup)(int)``: a parenthesized name, unless it names a type (``f(T)``).
            known = self.program is not None and (self.program.lookup(following, self._lookup_scopes()) is not None
                                                  or following in PROVIDER_TYPEDEFS)
            return not known
        mark = self.position
        self.position += 1
        nested = self._member_pointer_follows()
        self.position = mark
        return nested

    def _wrap(self, kind: str, extra: Any, cv: str, node: dict[str, Any] | None) -> dict[str, Any]:
        if kind == "function":
            params = extra
            wrapped: dict[str, Any] = {"t": "function", "params": params, "ret": node}
        elif kind == "array":
            wrapped = {"t": "array", "size": extra, "of": node}
        elif kind == "member_pointer":
            target = node
            if isinstance(target, dict) and target.get("t") == "function":
                # A member function pointer: mw_mangle records its hidden this (const for a const member).
                target = dict(target)
                target["member_this"] = target.pop("cv", "")
            wrapped = {"t": "member_pointer", "class": extra, "to": target}
        else:
            wrapped = {"t": kind, "to": node}
        if cv:
            wrapped["cv"] = cv
        return wrapped

    def parameters(self) -> list[dict[str, Any]]:
        params: list[dict[str, Any]] = []
        names: list[str | None] = []
        outermost = self.in_parameters == 0 and self.parameter_names is None
        empty = self.accept(")")
        if not empty and self.peek() == "void" and self.peek(1) == ")":
            self.take(), self.take()
            empty = True
        if empty:
            if outermost:
                self.parameter_names = names
            return params
        self.in_parameters += 1
        try:
            while True:
                if self.accept("..."):
                    params.append({"t": "builtin", "code": "e"})
                    names.append(None)
                else:
                    _specifiers, base = self.decl_specifiers()
                    if base is None:
                        raise Unresolvable(f"expected a parameter type at {self.peek()!r}")
                    saved = self.declarator_scope, self.data_context
                    self.data_context = False
                    name, node = self.declarator(base, abstract=True)
                    self.declarator_scope, self.data_context = saved
                    params.append(adjust_parameter(node))
                    names.append(name.components[-1][0] if name is not None and name.components else None)
                    if self.accept("="):
                        self._skip_default()
                if self.accept(")"):
                    if outermost:
                        self.parameter_names = names
                    return params
                self.expect(",")
        finally:
            self.in_parameters -= 1

    def _skip_default(self) -> None:
        depth = 0
        while not self.at_end():
            text = self.peek()
            if depth == 0 and text in (",", ")"):
                return
            if text in ("(", "[", "{"):
                depth += 1
            elif text in (")", "]", "}"):
                depth -= 1
            self.take()


def adjust_parameter(node: dict[str, Any]) -> dict[str, Any]:
    """A parameter's type in the function type: arrays and functions decay, top-level cv drops."""

    if node.get("t") == "array":
        node = {"t": "pointer", "to": node["of"]}
    elif node.get("t") == "function":
        node = {"t": "pointer", "to": node}
    if "cv" in node:
        node = {key: value for key, value in node.items() if key != "cv"}
    return node


# -- declarations to structured symbols ----------------------------------------------------


@dataclass
class Parsed:
    symbol: dict[str, Any] | None  # mw_mangle structured form
    specifiers: set[str]
    returns: dict[str, Any] | None  # the return type node (functions)
    type: dict[str, Any] | None  # the declared type (data)
    name: str  # the declarator-id as written
    error: str | None = None
    pure: bool = False
    param_names: list[str | None] | None = None  # the declarator's parameter names as written (functions)


def _function_name(name: QualifiedName) -> dict[str, Any]:
    base, arguments = name.components[-1]
    if name.special == "conversion":
        return {"conversion": name.conversion}
    if name.special == "operator":
        return {"text": "__" + str(name.operator)}
    if name.special == "destructor":
        return {"text": "__dt"}
    row: dict[str, Any] = {"text": base}
    if arguments is not None:
        row["args"] = arguments
    return row


def _scope_rows(program: Program, scope: tuple[tuple[str, Any], ...], tag: str) -> list[dict[str, Any]]:
    return [_component(base) for base in scope_chain(scope, tag)]


def function_symbol(program: Program, tokens: list[Token], scope: tuple[tuple[str, Any], ...], tag: str, *,
                    klass: tuple[str, ...] | None = None) -> Parsed:
    """The structured symbol a function declaration or definition head declares."""

    parser = _Parser(tokens, program, scopes_of(scope, tag), tag, klass=klass)
    written = " ".join(token.text for token in tokens)
    try:
        specifiers, base = parser.decl_specifiers()
        name, node = parser.declarator(base)
        if name is None or node.get("t") != "function":
            return Parsed(None, specifiers, None, None, written, error="not a function declarator")
        pure = parser.peek() == "=" and parser.peek(1) == "0"
        returns = node["ret"]
        qualifier = getattr(name, "scope_nodes", None)
        if qualifier is None:
            qualifier = _scope_rows(program, scope, tag)
        params = node["params"] or [{"t": "builtin", "code": "v"}]
        base_name = name.components[-1][0]
        in_c = any(kind == "externc" for kind, _value in scope) or 'extern "C"' in specifiers
        if not qualifier and (in_c or (base_name == "main" and name.special is None)):
            symbol: dict[str, Any] = {"kind": "c_name", "name": base_name}
        else:
            function_name = _function_name(name)
            last = qualifier[-1] if qualifier else None
            if name.special is None and last is not None and "name" in last and base_name == last["name"] and (
                klass is not None or getattr(name, "scope_nodes", None) is not None
            ):
                function_name = {"text": "__ct"}
            symbol = {"kind": "function", "name": function_name, "scope": qualifier or None, "cv": node.get("cv", ""),
                      "params": params}
        return Parsed(symbol, specifiers, returns, None, "::".join(base for base, _ in name.components), pure=pure,
                      param_names=parser.parameter_names)
    except (Unresolvable, MangleError, IndexError, KeyError, TypeError, ValueError) as exc:
        return Parsed(None, set(), None, None, written, error=str(exc) or type(exc).__name__)


def data_symbols(program: Program, tokens: list[Token], scope: tuple[tuple[str, Any], ...], tag: str) -> list[Parsed]:
    """The variables (or prototypes) one namespace-scope declaration statement declares."""

    parser = _Parser(tokens, program, scopes_of(scope, tag), tag)
    parser.data_context = True
    written = " ".join(token.text for token in tokens)
    found: list[Parsed] = []
    try:
        specifiers, base = parser.decl_specifiers()
        while not parser.at_end():
            parser.declarator_scope = None
            name, node = parser.declarator(base)
            if name is None:
                break
            if node.get("t") == "function":
                found.append(Parsed(None, specifiers, node.get("ret"), node, name.components[-1][0], error="prototype"))
            else:
                qualifier = getattr(name, "scope_nodes", None) or _scope_rows(program, scope, tag)
                text = name.components[-1][0]
                in_c = any(kind == "externc" for kind, _value in scope) or 'extern "C"' in specifiers
                if qualifier and not in_c:
                    symbol: dict[str, Any] = {"kind": "data", "name": {"text": text}, "scope": qualifier}
                else:
                    symbol = {"kind": "c_name", "name": text}
                found.append(Parsed(symbol, specifiers, None, node, text))
            if parser.accept("="):
                parser._skip_default()
            elif parser.peek() == "(":
                parser._skip_balanced()
            if not parser.accept(","):
                break
    except (Unresolvable, MangleError, IndexError, KeyError, TypeError, ValueError) as exc:
        found.append(Parsed(None, set(), None, None, written, error=str(exc) or type(exc).__name__))
    return found


# -- spelling structured symbols as C++ ----------------------------------------------------


class Speller:
    """C++ text for types and declarator-ids, qualified for one lookup context."""

    def __init__(self, program: Program, scopes: list[tuple[str, ...]], *, inside_unnamed: str | None = None) -> None:
        self.program = program
        self.scopes = scopes
        self.inside_unnamed = inside_unnamed
        self.problems: list[str] = []

    def qualified(self, components: list[dict[str, Any]], scopes: list[tuple[str, ...]] | None = None) -> str:
        scopes = scopes if scopes is not None else self.scopes
        rows = list(components)
        if rows and "unnamed" in rows[0]:
            if rows[0]["unnamed"] != self.inside_unnamed:
                self.problems.append(f"names {'::'.join(chain_of(rows))} from another file's anonymous namespace")
            rows = rows[1:]
            if not rows:
                return ""
        if any("unnamed" in row or "local" in row for row in rows):
            self.problems.append(f"cannot spell {'::'.join(chain_of(components))}")
        text = "::".join(self.component(row) for row in rows)
        want = chain_of(components)
        found = self.program.lookup(_component_base(rows[0]), scopes)
        resolved = (found[:-1] if found else ()) + chain_of(rows)
        if resolved != want:
            text = "::" + text
            if components and "unnamed" in components[0]:
                self.problems.append(f"{text} is hidden inside the anonymous namespace")
        return text

    def component(self, row: dict[str, Any]) -> str:
        if "unnamed" in row:
            return "(anonymous namespace)"
        if "local" in row:
            return row["name"]
        text = row["name"]
        if "args" in row:
            arguments = ", ".join(value["value"] if value.get("t") == "value" else self.type(value) for value in row["args"])
            text += f"<{arguments}{' ' if arguments.endswith('>') else ''}>"
        return text

    def type(self, node: dict[str, Any], inner: str = "", scopes: list[tuple[str, ...]] | None = None) -> str:
        cv = " ".join({"C": "const", "V": "volatile"}[char] for char in node.get("cv", ""))
        kind = node["t"]
        if kind in ("pointer", "reference", "member_pointer"):
            if kind == "member_pointer":
                symbol = self.qualified(node["class"], scopes) + "::*"
            else:
                symbol = "*" if kind == "pointer" else "&"
            if cv:
                symbol += cv + (" " if inner else "")
            declarator = symbol + inner
            target = node["to"]
            if target["t"] in ("function", "array"):
                declarator = f"({declarator})"
            return self.type(target, declarator, scopes)
        if kind == "array":
            return self.type(node["of"], f"{inner}[{node['size']}]", scopes)
        if kind == "function":
            suffix = ""
            if node.get("member_this"):
                suffix = " " + " ".join({"C": "const", "V": "volatile"}[c] for c in node["member_this"])
            return self.type(node["ret"], f"{inner}({self.parameters(node['params'], scopes)}){suffix}", scopes)
        if kind == "builtin":
            code = node["code"]
            if code == INT128_CODE:
                base = "unsigned __int128"
            elif "sign" in node:
                base = f"{'unsigned' if node['sign'] == 'U' else 'signed'} {BUILTINS[code]}"
            else:
                base = BUILTINS[code]
        elif kind == "named":
            base = self.qualified(node["name"], scopes)
        else:
            raise MangleError(f"unknown type node {kind!r}")
        text = f"{cv} {base}" if cv else base
        return f"{text} {inner}" if inner else text

    def parameters(self, params: list[dict[str, Any]], scopes: list[tuple[str, ...]] | None = None,
                   names: list[str | None] | None = None) -> str:
        if len(params) == 1 and params[0] == {"t": "builtin", "code": "v"}:
            return ""
        if names is None or len(names) != len(params):
            names = [None] * len(params)
        return ", ".join(self.type(param, name or "", scopes) for param, name in zip(params, names))


OPERATOR_SPELLING = {code: (f"operator {symbol}" if symbol[0].isalpha() else f"operator{symbol}") for code, symbol in OPERATORS.items()}


def member_name(symbol: dict[str, Any], speller: Speller) -> str:
    """The unqualified declarator-id of a function symbol (``Tick``, ``~CFoo``, ``operator+``)."""

    name = symbol["name"]
    scope = symbol.get("scope") or []
    if "conversion" in name:
        return "operator " + speller.type(name["conversion"])
    text = name["text"]
    if text == "__ct":
        return scope[-1]["name"]
    if text == "__dt":
        return "~" + scope[-1]["name"]
    if text.startswith("__") and text[2:] in OPERATORS:
        return OPERATOR_SPELLING[text[2:]]
    if "args" in name:
        arguments = ", ".join(value["value"] if value.get("t") == "value" else speller.type(value) for value in name["args"])
        text += f"<{arguments}{' ' if arguments.endswith('>') else ''}>"
    return text


def definition_text(program: Program, symbol: dict[str, Any], returns: str | None, *, tag: str,
                    names: list[str | None] | None = None) -> tuple[str, list[str], str | None]:
    """(the out-of-line definition head a skeleton writes, spelling problems, the enclosing namespace).

    A symbol in the anonymous namespace is written inside ``namespace { }`` of
    its unit (the third value is then ``"anonymous"``); every other one at file
    scope with its full qualification.  ``names`` (one per declared parameter)
    names the parameters; by default they are unnamed.
    """

    scope = list(symbol.get("scope") or [])
    unnamed = scope[0]["unnamed"] if scope and "unnamed" in scope[0] else None
    site = [(f"@unnamed@{unnamed}@",), ()] if unnamed else [()]
    speller = Speller(program, site, inside_unnamed=unnamed)
    if unnamed is not None and unnamed != tag:
        speller.problems.append(f"the anonymous namespace of {unnamed} is not this unit's ({tag})")
    if symbol["kind"] == "c_name":
        head = f"{returns or 'void'} {symbol['name']}()"
        return head, speller.problems, None
    written_scope = scope[1:] if unnamed else scope
    member = member_name(symbol, speller)
    chain = chain_of(scope)
    param_scopes = [chain[:index] for index in range(len(chain), 0, -1)] + site
    params = speller.parameters(symbol["params"], param_scopes, names)
    cv = " ".join({"C": "const", "V": "volatile"}[char] for char in symbol.get("cv", ""))
    qualifier = speller.qualified(scope) if written_scope else ""
    declarator = f"{qualifier}::{member}" if qualifier else member
    declarator += f"({params})" + (f" {cv}" if cv else "")
    head = f"{returns} {declarator}" if returns else declarator
    return head, speller.problems, "anonymous" if unnamed else None


def declaration_text(program: Program, symbol: dict[str, Any], returns: str | None, *, static: bool, virtual: bool) -> str:
    """The in-class member declaration (``virtual void Tick(float);``)."""

    scope = symbol.get("scope") or []
    chain = chain_of(scope)
    scopes = [chain[:index] for index in range(len(chain), -1, -1)]
    unnamed = scope[0]["unnamed"] if scope and "unnamed" in scope[0] else None
    speller = Speller(program, scopes, inside_unnamed=unnamed)
    member = member_name(symbol, speller)
    params = speller.parameters(symbol["params"])
    cv = " ".join({"C": "const", "V": "volatile"}[char] for char in symbol.get("cv", ""))
    text = f"{member}({params})" + (f" {cv}" if cv else "")
    if returns:
        text = f"{returns} {text}"
    if static:
        text = "static " + text
    elif virtual:
        text = "virtual " + text
    return text + ";"


def parse_head(program: Program, text: str, *, tag: str, namespace: str | None) -> Parsed:
    """Parse a definition head written by ``definition_text`` back to its structured symbol."""

    tokens, _comments = tokenize(text)
    scope: tuple[tuple[str, Any], ...] = (("ns", None),) if namespace == "anonymous" else ()
    return function_symbol(program, tokens, scope, tag)
