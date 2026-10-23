"""Demangle Metrowerks CodeWarrior (cfront-style) C++ symbol names.

The 128-bit type code ``1``
---------------------------
Metrowerks' R5900 compiler mangles its 128-bit integer (the EE quadword,
DWARF 1 fundamental type 0xA510) as the one-character type code ``1``.  In a
type position a ``1`` that no digit follows is that type, not the length of
a one-character class name.  Evidence in socom.elf:

- ``zSysAddDMA__FP1P1`` takes two pointers: ``lq v1,0(a1)``,
  ``sq v1,0(a0)`` and returns ``a0 + 16`` (0x2f5d20).
- ``ReplaceTextureData__Q23zdb8CVisDataFP1`` ends right after ``P1``, so no
  class name follows it; its body copies quadwords (``lq v1,0(a1)``,
  0x310730).  ``zSysSprGetPacket__FPP1`` is a pointer to a pointer.
- ``TakeDrawPacket__23CDblBufTextureRelocatorFP1Ui`` forwards a1 and a2 to
  ``zSysFifoKick__FP1Ui`` (0x3805f0): ``P1Ui`` is (quadword *, unsigned
  int), not a class ``U`` followed by ``i``.
- ``MakeChain__Q23zdb12CGSTexBufferFP1i`` is (quadword *, int): its callers
  set a2 and store its result into ``CGSTexBuffer::m_chainp``, whose DWARF
  type is a pointer to 0xA510 (0x2f9c24/0x2f9c34).
- ``std::__vector_imp<1, std::allocator<1>, 0>::resize__...FUiRC1`` steps
  its elements 16 bytes at a time (``sll v1,a2,4``, 0x2fcbb0); DWARF types
  three ``__vector_deleter`` records' ``data_`` as a pointer to 0xA510.

DWARF has no other 128-bit fundamental type and no symbol spells ``U1`` or
``S1``, so the code has one signedness: unsigned, like 0xA510.  The ELF has
no one-character global class (no ``__1X`` qualifier, no one-character
DWARF type name).  A nested one-character name sits inside a ``Q`` qualifier
and keeps its length prefix (``Q210PadBtnFunc1_`` is ``PadBtnFunc::_``), as
does a ``1`` followed by a digit (``10PadBtnFunc``, ``12CGSTexBuffer``).

The type renders as ``uint16``, the spelling the DWARF import already gives
0xA510 (``type_apply.FUND_TYPES``): the live program's 16-byte builtin
``/uint16``.  The SDK spelling ``u_long128`` and ``long128`` are not live
types, and ``_word128`` is a union class with its own mangled name
(``8_word128``).

A bare template argument ``1`` stays the literal ``1``: the type
(``__vector_imp<1, std::allocator<1>, 0>``) and the value
(``compile_assert<1>``, ``__locale_imp<1>``) are spelled the same, so
readable class names keep the mangled spelling.
"""

from __future__ import annotations

from typing import Any

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
# The 128-bit integer's type code and its project spelling (see the module
# docstring).  It is not in BUILTINS: ``1`` is also the first digit of a
# length, and ``U``/``S`` do not combine with it.
INT128_CODE = "1"
INT128_SPELLING = "uint16"
MODIFIER_SPELLINGS = {"P": "*", "R": "&", "C": " const", "V": " volatile"}


class DemangleError(ValueError):
    pass


class _Parser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def at_end(self) -> bool:
        return self.pos >= len(self.text)

    def peek(self) -> str:
        return self.text[self.pos : self.pos + 1]

    def take(self, count: int = 1) -> str:
        if self.pos + count > len(self.text):
            raise DemangleError("unexpected end of mangled name")
        value = self.text[self.pos : self.pos + count]
        self.pos += count
        return value

    def number(self) -> int:
        start = self.pos
        while not self.at_end() and self.text[self.pos].isdigit():
            self.pos += 1
        if start == self.pos:
            raise DemangleError(f"expected a length at offset {start}")
        return int(self.text[start : self.pos])

    def identifier(self) -> str:
        return self.take(self.number())

    def qualified(self) -> list[str]:
        if self.peek() == "Q":
            self.take()
            if self.peek() == "_":
                self.take()
                count = self.number()
                if self.take() != "_":
                    raise DemangleError("malformed Q_<count>_ qualifier")
            else:
                count = int(self.take())
            return [self.identifier() for _ in range(count)]
        if self.peek().isdigit():
            return [self.identifier()]
        raise DemangleError(f"expected a qualified name at offset {self.pos}")

    def type(self) -> dict[str, Any]:
        modifiers: list[str] = []
        while self.peek() in MODIFIER_SPELLINGS:
            modifiers.append(self.take())
        code = self.peek()
        if code in ("U", "S"):
            sign = self.take()
            base = self.take()
            if base not in BUILTINS:
                raise DemangleError(f"invalid signed builtin {base!r}")
            prefix = "unsigned " if sign == "U" else "signed "
            return {"modifiers": modifiers, "kind": "builtin", "name": prefix + BUILTINS[base]}
        if code in BUILTINS:
            self.take()
            return {"modifiers": modifiers, "kind": "builtin", "name": BUILTINS[code]}
        if code == INT128_CODE and not self.text[self.pos + 1 : self.pos + 2].isdigit():
            self.take()
            return {"modifiers": modifiers, "kind": "builtin", "name": INT128_SPELLING}
        if code == "Q" or code.isdigit():
            return {"modifiers": modifiers, "kind": "class", "components": self.qualified()}
        if code == "F":
            self.take()
            params = []
            while self.peek() != "_":
                params.append(self.type())
            self.take()
            return {
                "modifiers": modifiers,
                "kind": "function",
                "params": params,
                "result": self.type(),
            }
        if code == "A":
            self.take()
            count = self.number()
            if self.take() != "_":
                raise DemangleError("malformed array type")
            return {"modifiers": modifiers, "kind": "array", "count": count, "element": self.type()}
        if code == "M":
            self.take()
            owner = self.qualified()
            return {
                "modifiers": modifiers,
                "kind": "member_pointer",
                "owner": owner,
                "pointee": self.type(),
            }
        raise DemangleError(f"unknown type code {code!r} at offset {self.pos}")


def _split_function(mangled: str) -> tuple[str, str] | None:
    """Split `name__<qualifier><F...>` at the first top-level separator."""

    depth = 0
    for index in range(1, len(mangled) - 1):
        char = mangled[index]
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif depth == 0 and mangled.startswith("__", index):
            rest = mangled[index + 2 :]
            if rest and (rest[0].isdigit() or rest[0] in "QFC"):
                return mangled[:index], rest
    return None


def demangle(mangled: str) -> dict[str, Any] | None:
    """Return the base name, qualifier, constness, and parameters of a symbol.

    `params` is None for data symbols such as static members.  Names that are
    not Metrowerks C++ symbols return None.
    """

    split = _split_function(mangled)
    if split is None:
        return None
    name, rest = split
    parser = _Parser(rest)
    try:
        qualifier: list[str] = []
        if parser.peek() == "Q" or parser.peek().isdigit():
            qualifier = parser.qualified()
        const = False
        if parser.peek() == "C":
            parser.take()
            const = True
        if parser.at_end():
            if not qualifier:
                return None
            return {"name": name, "qualifier": qualifier, "const": const, "params": None}
        if parser.take() != "F":
            return None
        params = []
        while not parser.at_end():
            params.append(parser.type())
    except DemangleError:
        return None
    return {"name": name, "qualifier": qualifier, "const": const, "params": params}


def _template_arguments(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(text):
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def template_base(component: str) -> str:
    """Return a qualifier component without its template argument list."""

    return component.split("<", 1)[0]


def component_argument_types(component: str) -> list[dict[str, Any]]:
    """Parsed type arguments of a templated qualifier component."""

    if not (component.endswith(">") and "<" in component):
        return []
    arguments = component.split("<", 1)[1][:-1]
    result = []
    for argument in _template_arguments(arguments):
        if argument.lstrip("-").isdigit():
            continue
        parser = _Parser(argument)
        try:
            value = parser.type()
        except DemangleError:
            continue
        if parser.at_end():
            result.append(value)
    return result


def readable_component(component: str) -> str:
    if not (component.endswith(">") and "<" in component):
        return component
    base, arguments = component.split("<", 1)
    rendered = []
    for argument in _template_arguments(arguments[:-1]):
        if argument.lstrip("-").isdigit():
            rendered.append(argument)
            continue
        parser = _Parser(argument)
        try:
            value = parser.type()
            if not parser.at_end():
                raise DemangleError("trailing template argument text")
            rendered.append(render_type(value))
        except DemangleError:
            rendered.append(argument)
    return f"{base}<{', '.join(rendered)}>"


def readable_qualified(components: list[str]) -> str:
    return "::".join(readable_component(component) for component in components)


def _modifier_suffix(modifiers: list[str]) -> str:
    suffix = ""
    for modifier in modifiers:
        suffix = MODIFIER_SPELLINGS[modifier] + suffix
    return suffix


def _render_function(value: dict[str, Any], declarator: str) -> str:
    params = ", ".join(render_type(param) for param in value["params"])
    result = render_type(value["result"])
    if declarator:
        return f"{result} ({declarator})({params})"
    return f"{result} ({params})"


def render_type(value: dict[str, Any]) -> str:
    """Render a demangled type as a C++ type-id, using declarator syntax for
    pointers to functions and pointers to members."""

    kind = value["kind"]
    suffix = _modifier_suffix(value["modifiers"])
    if kind == "function":
        return _render_function(value, suffix.lstrip())
    if kind == "member_pointer":
        declarator = f"{readable_qualified(value['owner'])}::*{suffix}"
        pointee = value["pointee"]
        if pointee["kind"] == "function" and not pointee["modifiers"]:
            return _render_function(pointee, declarator)
        return f"{render_type(pointee)} {declarator}"
    if kind == "builtin":
        core = value["name"]
    elif kind == "class":
        core = readable_qualified(value["components"])
    else:
        core = f"{render_type(value['element'])}[{value['count']}]"
    return core + suffix


def split_qualified(name: str) -> list[str]:
    """Split a readable qualified name on `::` outside template arguments."""

    parts: list[str] = []
    depth = 0
    start = 0
    index = 0
    while index < len(name):
        char = name[index]
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        elif depth == 0 and name.startswith("::", index):
            parts.append(name[start:index])
            index += 2
            start = index
            continue
        index += 1
    parts.append(name[start:])
    return parts
