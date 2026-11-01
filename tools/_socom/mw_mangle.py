"""Metrowerks CodeWarrior C++ name mangling: parse, render and mangle back.

The reference was built by MW MIPS C Compiler 2.4.1.01, whose mangler is the
cfront/ARM scheme with Metrowerks extensions.  ``parse_symbol`` turns any
ELF symbol name into a structured, JSON-ready form; ``mangle`` turns that
form back into the exact name; ``render`` spells it as C++ declaration text.
``mwdemangle`` stays the readable-name helper of the Ghidra and source
tools; this module is the exact grammar the stage 5 skeleton generator
checks its signatures against.

Functions and data
------------------
``<name>__<scope><cv>F<params>`` is a function: ``<scope>`` is the class
or namespace (absent for a global function), ``C``/``V`` before ``F`` make
it a const/volatile member, and the parameters run to the end (``Fv`` is
no parameter).  ``<name>__<scope>`` without ``F`` is a static data member
or namespace-scope variable.  The return type is never encoded (the
compiler's ``#pragma new_mangler`` is off by default, so function template
instances do not carry it either), nor is ``static``/``virtual``, nor
whether the scope is a class or a namespace (``ai``, ``std`` and
``Metrowerks`` are namespaces; the form is the same).  Constructors and
destructors are ``__ct``/``__dt`` with the declared parameters only: the
hidden arguments the compiler adds (the destructor's delete flag) are not in
the name.  Operators use the cfront codes (``__as`` ``operator=``, ``__vc``
``operator[]``, ``__nw`` ``operator new``, ...); ``__op<type>`` is a
conversion operator; ``__defctor`` is the compiler's default-argument
constructor wrapper.

Names
-----
``<n><text>`` is a name of ``n`` characters; ``Q<k>`` (``Q_<k>_`` from ten)
prefixes ``k`` of them as one qualified name.  A templated name is written
literally with its arguments, ``vector<i,Q23std12allocator<i>>``: each
argument is a mangled type or an integer value, separated by commas, and
the length prefix covers the whole text.  A function template's arguments
follow its name the same way (``DrawFunc<11CDynGrenade>__2aiF...``).
``@unnamed@<file>@`` is the unnamed namespace of one source file
(``zNetMedius_cpp``); ``<name>$<n><file>`` is a class local to a function of
that file (``Local$2354zui_skb_cpp``).

Types
-----
Builtins: ``v`` void, ``b`` bool, ``c`` char, ``s`` short, ``i`` int,
``l`` long, ``x`` long long, ``f`` float, ``d`` double, ``r`` long double,
``w`` wchar_t, ``e`` the ellipsis; ``U``/``S`` before ``c s i l x`` make
them unsigned/signed.  ``1`` (not followed by a digit) is the EE's 128-bit
integer: DWARF types those parameters as fundamental type 0xA510 (unsigned
128-bit, see ``mwdemangle``) and MSL's PS2 prefix header spells the type
``unsigned __int128`` (``u_long128``), so it renders that way; no symbol
writes ``U1`` or ``S1``, and whether a plain ``__int128`` also mangles as
``1`` waits for a compiler probe.  ``C``/``V`` qualify the type that follows
(``PCc`` pointer to const char, ``CPc`` const pointer to char); ``P``
pointer, ``R`` reference, ``A<n>_<type>`` array, ``F<params>_<result>``
function, ``M<class><type>`` pointer to member.  A pointer to member
function carries two hidden leading parameters, ``PCv`` and ``this``
(``Pv``, or ``PCv`` for a const member function); the structured form
records ``member_this`` and keeps them out of ``params``.

Ambiguities kept literal: a template argument that is only digits is a
value (``compile_assert<1>``), so ``__vector_imp<1,...>``, whose ``1`` is
the 128-bit type, renders as ``1`` too; a one-character class name would
collide with the ``1`` code (the ELF has none outside a ``Q`` qualifier).

Other symbols are classified, not mangled: ``__vt__<class>`` vtables,
``__RTTI__<class>`` type descriptors, ``@<offset>@[<offset>@]<function>``
this-adjusting thunks, ``__sinit_<file>`` static initializers and their
``.p__sinit_<file>`` table words, ``__arraydtor$<n>`` array destructors,
``<name>$<n>`` and ``<name>$localstatic<n>$<function>`` local statics (an
``init`` one is the one-byte initialization flag of the static numbered
just before it), ``__init__<data>`` a template static member's flag,
``@<n>`` literal labels, ``$L<n>`` assembler labels, ``_$<name>`` VU
microcode labels, section symbols and plain C or assembler names.  Every
form still mangles back, so ``symbol_report`` round-trips every symbol.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable

BUILTINS = {
    "v": "void",
    "b": "bool",
    "c": "char",
    "s": "short",
    "i": "int",
    "l": "long",
    "x": "long long",
    "f": "float",
    "d": "double",
    "r": "long double",
    "w": "wchar_t",
    "e": "...",
}
SIGNABLE = frozenset("csilx")
SIGNS = {"U": "unsigned", "S": "signed"}
INT128_CODE = "1"
INT128_SPELLING = "unsigned __int128"
CV_WORDS = {"C": "const", "V": "volatile"}

# cfront operator codes and their C++ spelling.
OPERATORS = {
    "nw": "new",
    "nwa": "new[]",
    "dl": "delete",
    "dla": "delete[]",
    "pl": "+",
    "mi": "-",
    "ml": "*",
    "dv": "/",
    "md": "%",
    "er": "^",
    "ad": "&",
    "or": "|",
    "co": "~",
    "nt": "!",
    "as": "=",
    "lt": "<",
    "gt": ">",
    "apl": "+=",
    "ami": "-=",
    "amu": "*=",
    "adv": "/=",
    "amd": "%=",
    "aer": "^=",
    "aad": "&=",
    "aor": "|=",
    "ls": "<<",
    "rs": ">>",
    "als": "<<=",
    "ars": ">>=",
    "eq": "==",
    "ne": "!=",
    "le": "<=",
    "ge": ">=",
    "aa": "&&",
    "oo": "||",
    "pp": "++",
    "mm": "--",
    "cm": ",",
    "rm": "->*",
    "rf": "->",
    "cl": "()",
    "vc": "[]",
}
CONSTRUCTOR = "__ct"
DESTRUCTOR = "__dt"
DEFAULT_CONSTRUCTOR_WRAPPER = "__defctor"
VTABLE = "__vt"
RTTI = "__RTTI"
GUARD_NAME = "init"

REPORT_KIND = "socom-mw-demangle-report"
REPORT_SCHEMA = 1

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_VALUE = re.compile(r"-?\d+")
_LOCAL_CLASS = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\$(?P<local>\d+)(?P<file>[A-Za-z_][A-Za-z0-9_]*)")
_LABEL = re.compile(r"@(?P<number>\d+)")
_THUNK = re.compile(r"(?P<offsets>(?:@-?\d+)+)@(?=[A-Za-z_])")
_ASM_LABEL = re.compile(r"\$L(?P<number>\d+)")
_VU_LABEL = re.compile(r"_\$(?P<label>[A-Za-z0-9_]+)")
_ARRAY_DTOR = re.compile(r"__arraydtor\$(?P<number>\d+)")
_LOCAL_STATIC = re.compile(r"(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\$(?P<number>\d+)")
_SCOPED_STATIC = re.compile(r"(?P<variable>[A-Za-z_][A-Za-z0-9_]*)\$localstatic(?P<number>\d+)\$(?P<function>.+)")
_SINIT = re.compile(r"__sinit_(?P<file>.+)")
_SINIT_POINTER = re.compile(r"\.p__sinit_(?P<file>.+)")
_MEMBER_GUARD = re.compile(r"__init__(?P<target>.+)")
# A C name that resembles a mangled one: a separator followed by a scope or F.
_MANGLED_LOOKING = re.compile(r".__(?:[0-9QF]|C[0-9QF])")

PLAIN_KINDS = frozenset({"c_name", "section", "empty"})
_VOID_POINTER = {"t": "pointer", "to": {"t": "builtin", "code": "v"}}
_CONST_VOID_POINTER = {"t": "pointer", "to": {"t": "builtin", "code": "v", "cv": "C"}}


class MangleError(ValueError):
    pass


# -- parsing -------------------------------------------------------------------------------


class _Parser:
    def __init__(self, text: str, pos: int = 0):
        self.text = text
        self.pos = pos

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self, offset: int = 0) -> str:
        return self.text[self.pos + offset : self.pos + offset + 1]

    def take(self, count: int = 1) -> str:
        if self.pos + count > len(self.text):
            raise MangleError("unexpected end of mangled name")
        value = self.text[self.pos : self.pos + count]
        self.pos += count
        return value

    def expect(self, char: str) -> None:
        if self.take() != char:
            raise MangleError(f"expected {char!r} at offset {self.pos - 1}")

    def number(self) -> int:
        start = self.pos
        while self.peek().isdigit():
            self.pos += 1
        if start == self.pos:
            raise MangleError(f"expected a number at offset {start}")
        return int(self.text[start : self.pos])

    def qualified(self) -> list[dict[str, Any]]:
        if self.peek() == "Q":
            self.take()
            if self.peek() == "_":
                self.take()
                count = self.number()
                self.expect("_")
                if count < 10:
                    raise MangleError("Q_<k>_ qualifier with fewer than ten names")
            else:
                if not self.peek().isdigit():
                    raise MangleError("Q qualifier without a count")
                count = int(self.take())
                if count < 2:
                    raise MangleError("Q qualifier with fewer than two names")
            return [self.component() for _ in range(count)]
        if self.peek().isdigit():
            return [self.component()]
        raise MangleError(f"expected a qualified name at offset {self.pos}")

    def component(self) -> dict[str, Any]:
        length = self.number()
        if length < 1:
            raise MangleError("zero-length name")
        return parse_component(self.take(length))

    def type(self) -> dict[str, Any]:
        cv = ""
        while self.peek() in CV_WORDS:
            cv += self.take()
        node = self._unqualified()
        if cv:
            node["cv"] = cv
        return node

    def _unqualified(self) -> dict[str, Any]:
        code = self.peek()
        if not code:
            raise MangleError("unexpected end of mangled name")
        if code in SIGNS:
            sign = self.take()
            base = self.take()
            if base not in SIGNABLE:
                raise MangleError(f"{sign}{base} is not a signed or unsigned builtin")
            return {"t": "builtin", "code": base, "sign": sign}
        if code in BUILTINS:
            self.take()
            return {"t": "builtin", "code": code}
        if code == INT128_CODE and not self.peek(1).isdigit():
            self.take()
            return {"t": "builtin", "code": INT128_CODE}
        if code == "Q" or code.isdigit():
            return {"t": "named", "name": self.qualified()}
        self.take()
        if code == "P":
            return {"t": "pointer", "to": self.type()}
        if code == "R":
            return {"t": "reference", "to": self.type()}
        if code == "A":
            size = self.number()
            self.expect("_")
            return {"t": "array", "size": size, "of": self.type()}
        if code == "F":
            params = []
            while self.peek() != "_":
                params.append(self.type())
            self.take()
            return {"t": "function", "params": params, "ret": self.type()}
        if code == "M":
            owner = self.qualified()
            target = self.type()
            if target["t"] == "function" and "cv" not in target:
                params = target["params"]
                if len(params) >= 2 and params[0] == _CONST_VOID_POINTER and _is_this(params[1]):
                    target["member_this"] = params[1]["to"].get("cv", "")
                    target["params"] = params[2:]
            return {"t": "member_pointer", "class": owner, "to": target}
        raise MangleError(f"unknown type code {code!r} at offset {self.pos - 1}")


def _is_this(node: dict[str, Any]) -> bool:
    target = node.get("to") or {}
    return (
        node.get("t") == "pointer"
        and "cv" not in node
        and target.get("t") == "builtin"
        and target.get("code") == "v"
        and "sign" not in target
    )


def _template_arguments(text: str) -> list[dict[str, Any]]:
    """The comma-separated arguments of one template: types, or integer values."""

    if not text:
        return []
    parser = _Parser(text)
    arguments = []
    while True:
        value = _VALUE.match(text, parser.pos)
        if value and (value.end() == len(text) or text[value.end()] == ","):
            arguments.append({"t": "value", "value": value.group()})
            parser.pos = value.end()
        else:
            arguments.append(parser.type())
        if parser.at_end():
            return arguments
        parser.expect(",")


def _split_template(text: str) -> tuple[str, list[dict[str, Any]] | None]:
    if "<" not in text:
        if ">" in text or "," in text:
            raise MangleError(f"malformed name {text!r}")
        return text, None
    if not text.endswith(">"):
        raise MangleError(f"template name {text!r} does not end its arguments")
    base, arguments = text.split("<", 1)
    return base, _template_arguments(arguments[:-1])


def parse_component(text: str) -> dict[str, Any]:
    """One name of a qualified name, from the text its length prefix covers."""

    if text.startswith("@unnamed@") and text.endswith("@") and len(text) > len("@unnamed@@"):
        file = text[len("@unnamed@") : -1]
        if not _IDENTIFIER.fullmatch(file):
            raise MangleError(f"malformed unnamed namespace {text!r}")
        return {"unnamed": file}
    local = _LOCAL_CLASS.fullmatch(text)
    if local:
        return {"name": local["name"], "local": int(local["local"]), "file": local["file"]}
    base, arguments = _split_template(text)
    if not _IDENTIFIER.fullmatch(base):
        raise MangleError(f"malformed name {text!r}")
    component: dict[str, Any] = {"name": base}
    if arguments is not None:
        component["args"] = arguments
    return component


def _function_name(text: str) -> dict[str, Any]:
    base, arguments = _split_template(text)
    if not _IDENTIFIER.fullmatch(base):
        raise MangleError(f"malformed function name {text!r}")
    name: dict[str, Any] = {"text": base}
    if arguments is not None:
        name["args"] = arguments
    return name


def _separators(name: str) -> Iterable[int]:
    """Offsets of ``__`` outside template arguments, after the first character."""

    depth = 0
    for index, char in enumerate(name):
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif depth == 0 and index >= 1 and name.startswith("__", index):
            yield index


def _parse_tail(text: str) -> dict[str, Any] | None:
    """``<scope><cv>F<params>`` or ``<scope>``, or None when it is neither."""

    if not text:
        return None
    parser = _Parser(text)
    scope = parser.qualified() if parser.peek() == "Q" or parser.peek().isdigit() else None
    cv = ""
    while parser.peek() in CV_WORDS:
        cv += parser.take()
    if parser.at_end():
        if scope is None or cv:
            return None
        return {"kind": "data", "scope": scope}
    if parser.take() != "F":
        return None
    params = []
    while not parser.at_end():
        params.append(parser.type())
    if not params:
        return None
    return {"kind": "function", "scope": scope, "cv": cv, "params": params}


def _with_name(name: dict[str, Any], tail: dict[str, Any]) -> dict[str, Any]:
    if tail["kind"] == "data":
        if name.get("text") == VTABLE and "args" not in name:
            return {"kind": "vtable", "class": tail["scope"]}
        if name.get("text") == RTTI and "args" not in name:
            return {"kind": "rtti", "class": tail["scope"]}
        return {"kind": "data", "name": name, "scope": tail["scope"]}
    return {"kind": "function", "name": name, "scope": tail["scope"], "cv": tail["cv"], "params": tail["params"]}


def parse_mangled(name: str) -> dict[str, Any] | None:
    """A Metrowerks C++ function or data name, or None."""

    if name.startswith("__op"):
        parser = _Parser(name, 4)
        try:
            conversion = parser.type()
            if name.startswith("__", parser.pos):
                tail = _parse_tail(name[parser.pos + 2 :])
                if tail and tail["kind"] == "function":
                    return _with_name({"conversion": conversion}, tail)
        except MangleError:
            pass
    for index in _separators(name):
        try:
            function_name = _function_name(name[:index])
            tail = _parse_tail(name[index + 2 :])
        except MangleError:
            continue
        if tail is not None:
            return _with_name(function_name, tail)
    return None


def parse_symbol(name: str, symbol_type: str | None = None) -> dict[str, Any]:
    """The structured form of any symbol name; ``symbol_type`` is its ELF type name."""

    if name == "":
        return {"kind": "empty"}
    if symbol_type == "SECTION":
        return {"kind": "section", "name": name}
    match = _LABEL.fullmatch(name)
    if match:
        return {"kind": "label", "number": int(match["number"])}
    match = _THUNK.match(name)
    if match:
        target = parse_mangled(name[match.end() :])
        if target and target["kind"] == "function":
            offsets = [int(value) for value in match["offsets"][1:].split("@")]
            return {"kind": "thunk", "offsets": offsets, "target": target}
    match = _ASM_LABEL.fullmatch(name)
    if match:
        return {"kind": "asm_label", "number": int(match["number"])}
    match = _VU_LABEL.fullmatch(name)
    if match:
        return {"kind": "vu_label", "label": match["label"]}
    match = _ARRAY_DTOR.fullmatch(name)
    if match:
        return {"kind": "array_destructor", "number": int(match["number"])}
    match = _SCOPED_STATIC.fullmatch(name)
    if match:
        function = parse_symbol(match["function"])
        if function["kind"] in ("function", "c_name"):
            kind = "local_static_guard" if match["variable"] == GUARD_NAME else "local_static"
            return {"kind": kind, "variable": match["variable"], "number": int(match["number"]), "function": function}
    match = _LOCAL_STATIC.fullmatch(name)
    if match:
        kind = "local_static_guard" if match["variable"] == GUARD_NAME else "local_static"
        return {"kind": kind, "variable": match["variable"], "number": int(match["number"])}
    match = _SINIT_POINTER.fullmatch(name)
    if match:
        return {"kind": "static_initializer_pointer", "file": match["file"]}
    match = _SINIT.fullmatch(name)
    if match:
        return {"kind": "static_initializer", "file": match["file"]}
    match = _MEMBER_GUARD.fullmatch(name)
    if match:
        target = parse_mangled(match["target"])
        if target and target["kind"] == "data":
            return {"kind": "static_member_guard", "target": target}
    mangled = parse_mangled(name)
    if mangled:
        return mangled
    return {"kind": "c_name", "name": name}


# -- mangling ------------------------------------------------------------------------------


def _number_text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MangleError(f"expected an integer, got {value!r}")
    return str(value)


def mangle_component(component: dict[str, Any]) -> str:
    """The text a component's length prefix covers."""

    if "unnamed" in component:
        return f"@unnamed@{component['unnamed']}@"
    if "local" in component:
        return f"{component['name']}${_number_text(component['local'])}{component['file']}"
    text = component["name"]
    if "args" in component:
        text += "<" + ",".join(mangle_argument(value) for value in component["args"]) + ">"
    return text


def mangle_qualified(components: list[dict[str, Any]]) -> str:
    if not components:
        raise MangleError("empty qualified name")
    parts = "".join(f"{len(text)}{text}" for text in (mangle_component(row) for row in components))
    count = len(components)
    if count == 1:
        return parts
    return (f"Q{count}" if count < 10 else f"Q_{count}_") + parts


def mangle_argument(value: dict[str, Any]) -> str:
    if value["t"] == "value":
        if not _VALUE.fullmatch(value["value"]):
            raise MangleError(f"invalid template value {value['value']!r}")
        return value["value"]
    return mangle_type(value)


def mangle_type(node: dict[str, Any]) -> str:
    cv = node.get("cv", "")
    if any(char not in CV_WORDS for char in cv):
        raise MangleError(f"invalid cv-qualifier {cv!r}")
    kind = node["t"]
    if kind == "builtin":
        code = node["code"]
        if code not in BUILTINS and code != INT128_CODE:
            raise MangleError(f"unknown builtin {code!r}")
        return cv + node.get("sign", "") + code
    if kind == "named":
        return cv + mangle_qualified(node["name"])
    if kind == "pointer":
        return cv + "P" + mangle_type(node["to"])
    if kind == "reference":
        return cv + "R" + mangle_type(node["to"])
    if kind == "array":
        return cv + "A" + _number_text(node["size"]) + "_" + mangle_type(node["of"])
    if kind == "function":
        hidden = ""
        if "member_this" in node:
            hidden = "PCvP" + node["member_this"] + "v"
        params = "".join(mangle_type(param) for param in node["params"])
        return cv + "F" + hidden + params + "_" + mangle_type(node["ret"])
    if kind == "member_pointer":
        return cv + "M" + mangle_qualified(node["class"]) + mangle_type(node["to"])
    raise MangleError(f"unknown type node {kind!r}")


def _mangle_name(name: dict[str, Any]) -> str:
    if "conversion" in name:
        return "__op" + mangle_type(name["conversion"])
    text = name["text"]
    if "args" in name:
        text += "<" + ",".join(mangle_argument(value) for value in name["args"]) + ">"
    return text


def mangle(symbol: dict[str, Any]) -> str:
    """The exact symbol name of a structured form."""

    kind = symbol["kind"]
    if kind == "empty":
        return ""
    if kind in ("c_name", "section"):
        return symbol["name"]
    if kind == "function":
        scope = mangle_qualified(symbol["scope"]) if symbol["scope"] else ""
        if not symbol["params"]:
            raise MangleError("a function has at least one parameter code (v for none)")
        params = "".join(mangle_type(param) for param in symbol["params"])
        return f"{_mangle_name(symbol['name'])}__{scope}{symbol['cv']}F{params}"
    if kind == "data":
        return f"{_mangle_name(symbol['name'])}__{mangle_qualified(symbol['scope'])}"
    if kind == "vtable":
        return f"{VTABLE}__{mangle_qualified(symbol['class'])}"
    if kind == "rtti":
        return f"{RTTI}__{mangle_qualified(symbol['class'])}"
    if kind == "thunk":
        return "".join(f"@{_number_text(value)}" for value in symbol["offsets"]) + "@" + mangle(symbol["target"])
    if kind == "label":
        return f"@{_number_text(symbol['number'])}"
    if kind == "asm_label":
        return f"$L{_number_text(symbol['number'])}"
    if kind == "vu_label":
        return f"_${symbol['label']}"
    if kind == "array_destructor":
        return f"__arraydtor${_number_text(symbol['number'])}"
    if kind in ("local_static", "local_static_guard"):
        if "function" in symbol:
            return f"{symbol['variable']}$localstatic{_number_text(symbol['number'])}${mangle(symbol['function'])}"
        return f"{symbol['variable']}${_number_text(symbol['number'])}"
    if kind == "static_initializer":
        return f"__sinit_{symbol['file']}"
    if kind == "static_initializer_pointer":
        return f".p__sinit_{symbol['file']}"
    if kind == "static_member_guard":
        return f"__init__{mangle(symbol['target'])}"
    raise MangleError(f"unknown symbol kind {kind!r}")


# -- rendering -----------------------------------------------------------------------------


def _cv_text(node: dict[str, Any]) -> str:
    return " ".join(CV_WORDS[char] for char in node.get("cv", ""))


def render_argument(value: dict[str, Any]) -> str:
    return value["value"] if value["t"] == "value" else render_type(value)


def _arguments_text(arguments: list[dict[str, Any]]) -> str:
    text = ", ".join(render_argument(value) for value in arguments)
    # `>>` closes two template argument lists only from C++11 on.
    return f"<{text}{' ' if text.endswith('>') else ''}>"


def render_component(component: dict[str, Any]) -> str:
    if "unnamed" in component:
        return "(anonymous namespace)"
    text = component["name"]
    if "args" in component:
        text += _arguments_text(component["args"])
    return text


def render_qualified(components: list[dict[str, Any]]) -> str:
    return "::".join(render_component(row) for row in components)


def _declare(node: dict[str, Any], inner: str) -> str:
    """C++ declarator syntax: ``node`` declares ``inner``."""

    cv = _cv_text(node)
    kind = node["t"]
    if kind in ("pointer", "reference", "member_pointer"):
        if kind == "member_pointer":
            symbol = render_qualified(node["class"]) + "::*"
        else:
            symbol = "*" if kind == "pointer" else "&"
        if cv:
            symbol += cv + (" " if inner else "")
        declarator = symbol + inner
        target = node["to"]
        if target["t"] in ("function", "array"):
            declarator = f"({declarator})"
        return _declare(target, declarator)
    if kind == "array":
        return _declare(node["of"], f"{inner}[{node['size']}]")
    if kind == "function":
        suffix = ""
        if node.get("member_this"):
            suffix = " " + _cv_text({"cv": node["member_this"]})
        return _declare(node["ret"], f"{inner}({render_parameters(node['params'])}){suffix}")
    if kind == "builtin":
        code = node["code"]
        if code == INT128_CODE:
            base = INT128_SPELLING
        elif "sign" in node:
            base = f"{SIGNS[node['sign']]} {BUILTINS[code]}"
        else:
            base = BUILTINS[code]
    elif kind == "named":
        base = render_qualified(node["name"])
    else:
        raise MangleError(f"unknown type node {kind!r}")
    text = f"{cv} {base}" if cv else base
    return f"{text} {inner}" if inner else text


def render_type(node: dict[str, Any]) -> str:
    """A C++ type-id."""

    return _declare(node, "")


def render_parameters(params: list[dict[str, Any]]) -> str:
    if len(params) == 1 and params[0] == {"t": "builtin", "code": "v"}:
        return ""
    return ", ".join(render_type(param) for param in params)


def _class_name(scope: list[dict[str, Any]] | None) -> str:
    if not scope or "unnamed" in scope[-1]:
        raise MangleError("a constructor or destructor needs a class scope")
    return scope[-1]["name"]


def _render_name(name: dict[str, Any], scope: list[dict[str, Any]] | None) -> tuple[str, str | None]:
    if "conversion" in name:
        return f"operator {render_type(name['conversion'])}", "conversion"
    text = name["text"]
    special = None
    if text == CONSTRUCTOR:
        text, special = _class_name(scope), "constructor"
    elif text == DESTRUCTOR:
        text, special = "~" + _class_name(scope), "destructor"
    elif text == DEFAULT_CONSTRUCTOR_WRAPPER:
        special = "compiler-generated"
    elif text.startswith("__") and text[2:] in OPERATORS:
        symbol = OPERATORS[text[2:]]
        text = f"operator {symbol}" if symbol[0].isalpha() else f"operator{symbol}"
        special = "operator"
    if "args" in name:
        text += _arguments_text(name["args"])
        special = special or "function-template"
    return text, special


def render(symbol: dict[str, Any]) -> dict[str, Any]:
    """C++ declaration text (functions and data) or a description (other kinds)."""

    kind = symbol["kind"]
    if kind == "function":
        scope = symbol["scope"]
        name, special = _render_name(symbol["name"], scope)
        params = render_parameters(symbol["params"])
        cv = _cv_text(symbol)
        member = f"{name}({params}){' ' + cv if cv else ''}"
        scope_text = render_qualified(scope) if scope else None
        return {
            "kind": kind,
            "scope": scope_text,
            "name": name,
            "special": special,
            "params": [render_type(param) for param in symbol["params"]] if params else [],
            "cv": cv or None,
            "member_declaration": member,
            "declaration": f"{scope_text}::{member}" if scope_text else member,
        }
    if kind == "data":
        name, _ = _render_name(symbol["name"], symbol["scope"])
        scope_text = render_qualified(symbol["scope"])
        return {"kind": kind, "scope": scope_text, "name": name, "declaration": f"{scope_text}::{name}"}
    if kind == "vtable":
        return {"kind": kind, "text": f"virtual table of {render_qualified(symbol['class'])}"}
    if kind == "rtti":
        return {"kind": kind, "text": f"RTTI descriptor of {render_qualified(symbol['class'])}"}
    if kind == "thunk":
        offsets = ", ".join(str(value) for value in symbol["offsets"])
        target = render(symbol["target"])["declaration"]
        return {"kind": kind, "text": f"this-adjusting thunk ({offsets}) to {target}", "target": target}
    if kind in ("local_static", "local_static_guard"):
        what = "initialization flag" if kind == "local_static_guard" else "local static"
        text = f"{what} {symbol['variable']} (#{symbol['number']})"
        if "function" in symbol:
            function = symbol["function"]
            owner = render(function)["declaration"] if function["kind"] == "function" else function["name"]
            text += f" of {owner}"
        return {"kind": kind, "text": text}
    if kind == "static_member_guard":
        return {"kind": kind, "text": f"initialization flag of {render(symbol['target'])['declaration']}"}
    descriptions = {
        "static_initializer": lambda: f"static initializer of {symbol['file']}",
        "static_initializer_pointer": lambda: f"static initializer table entry of {symbol['file']}",
        "array_destructor": lambda: f"array destructor #{symbol['number']}",
        "label": lambda: f"literal label @{symbol['number']}",
        "asm_label": lambda: f"assembler label $L{symbol['number']}",
        "vu_label": lambda: f"VU microcode label {symbol['label']}",
        "section": lambda: f"section symbol {symbol['name']}",
        "c_name": lambda: f"C or assembler name {symbol['name']}",
        "empty": lambda: "the null symbol",
    }
    return {"kind": kind, "text": descriptions[kind]()}


# -- reports -------------------------------------------------------------------------------


def demangle(name: str, symbol_type: str | None = None) -> dict[str, Any]:
    """One symbol: its structured form, rendering, mangled form and round trip."""

    row: dict[str, Any] = {"symbol": name}
    try:
        structured = parse_symbol(name, symbol_type)
        row["kind"] = structured["kind"]
        row["structured"] = structured
        row["rendered"] = render(structured)
        row["mangled"] = mangle(structured)
        row["round_trip"] = row["mangled"] == name
    except MangleError as exc:
        row.setdefault("kind", "error")
        row["round_trip"] = False
        row["error"] = str(exc) or type(exc).__name__
    if row.get("kind") == "c_name" and _MANGLED_LOOKING.search(name):
        row["resembles_mangling"] = True
    return row


def function_form(structured: dict[str, Any]) -> str:
    """ordinary, constructor, destructor, operator, conversion, function-template or compiler-generated."""

    _, special = _render_name(structured["name"], structured["scope"])
    return special or "ordinary"


def symbol_report(
    symbols: Iterable[tuple[str, str, str]],
    *,
    include_rows: bool = False,
    examples: int = 3,
) -> dict[str, Any]:
    """Round-trip every ``(name, ELF type, binding)`` symbol, counted by category."""

    rows = list(symbols)
    by_name: dict[tuple[str, str | None], dict[str, Any]] = {}
    categories: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"symbols": 0, "names": 0, "identical": 0, "failed": 0, "examples": []}
    )
    functions: Counter[str] = Counter()
    forms: Counter[str] = Counter()
    failures: list[dict[str, Any]] = []
    resembling: list[str] = []
    for name, symbol_type, binding in rows:
        key = (name, "SECTION" if symbol_type == "SECTION" else None)
        first = key not in by_name
        if first:
            by_name[key] = demangle(name, key[1])
        result = by_name[key]
        category = categories[result["kind"]]
        category["symbols"] += 1
        if symbol_type == "FUNC":
            functions["func_symbols"] += 1
            functions[f"{result['kind']}_symbols"] += 1
            if result["kind"] == "function":
                functions[f"function_{binding.lower()}_symbols"] += 1
            if result["round_trip"]:
                functions["round_trip_identical_symbols"] += 1
        if not first:
            continue
        category["names"] += 1
        if result["round_trip"]:
            category["identical"] += 1
        else:
            category["failed"] += 1
            failures.append({"symbol": name, "kind": result["kind"], "error": result.get("error", "mangled form differs")})
        if len(category["examples"]) < examples:
            category["examples"].append(name)
        if result["kind"] == "function":
            forms[function_form(result["structured"])] += 1
        if result.get("resembles_mangling"):
            resembling.append(name)
    names = list(by_name.values())
    structured = [row for row in names if row["kind"] not in PLAIN_KINDS and row["kind"] != "error"]
    report: dict[str, Any] = {
        "kind": REPORT_KIND,
        "schema_version": REPORT_SCHEMA,
        "ok": not failures,
        "symbol_count": len(rows),
        "name_count": len(names),
        "parsed_names": len(structured),
        "plain_names": len(names) - len(structured) - sum(1 for row in names if row["kind"] == "error"),
        "round_trip_identical_names": sum(1 for row in names if row["round_trip"]),
        "failed_names": len(failures),
        "categories": {key: categories[key] for key in sorted(categories)},
        "function_symbols": dict(sorted(functions.items())),
        "function_forms": dict(sorted(forms.items())),
        "failures": failures,
        "c_names_resembling_mangling": sorted(resembling),
    }
    if include_rows:
        report["rows"] = names
    return report
