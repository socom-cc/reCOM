"""Globals in stage 3 recon repairs: ELF facts, plan-row checks and program rows.

A recon repair may list globals besides functions (``progress add-recon-repair
--globals``): sized .symtab objects that no DWARF record describes, such as
the static data members of a class without a DWARF class record
(``m_dmaChain__Q23zdb7CVisual``).  A repair row gives a global

* its readable label, the demangled qualified name stage 2 gives DWARF
  globals (``zdb::CVisual::m_dmaChain``), keeping the mangled symbol as a
  label exactly as stage 2 kept ``m_camera__Q23zdb7CVisual``; and
* a type proven from its .symtab size and the code's accesses, or ``keep``
  with the reason its current type stays.

GhidraMCP's ``rename_label`` and ``create_label`` call ``Symbol.setName`` and
``SymbolTable.createLabel(address, name, source)`` without a namespace, so a
label is created in the global namespace and its name is the qualified
spelling itself (``audit_global`` reports the primary symbol's simple name,
``zdb::CVisual::m_camera`` for the stage 2 label).  The bridge offers no
endpoint that creates a namespace for a label, so the repair labels the way
stage 2 did.

* ``global_symbol_facts`` (file-only): the .symtab objects, sizes, bindings,
  DWARF records and file-local copies at each address; the tracker refuses a
  global the repair route may not touch from these;
* ``global_facts`` and ``global_facts_text`` (``recon global-facts``,
  file-only): every code access with its width, signedness, load or store,
  the stored values (constants, typed parameters, call results) and where
  loaded values go (compares, arithmetic, dereferences, typed callee
  parameters, returns and what callers do with them), plus data relocations
  and the initial bytes;
* ``repair_global_problems`` and ``repair_global_entry``: the plan-row checks
  of ``recon validate`` and the batch-program row ``recon program`` emits.
"""

from __future__ import annotations

import re
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any

from .batch_apply import ANALYSIS_TYPES, BUILTIN_SIZES, UNDEFINED_TYPES, _base_type, _data_alias_problem, symbol_name
from .elf import Elf32File
from .mwdemangle import demangle, readable_component
from .util import SocomError, file_key

KEEP = "keep"
GLOBAL_FACTS_KIND = "socom-recon-global-facts"
# Keys a repair global row may carry.
ROW_KEYS = frozenset({"address", "symbol", "label", "live_type", "type", "keep_reason", "repair", "evidence", "notes"})
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MNEMONICS = {
    0x20: "lb", 0x24: "lbu", 0x21: "lh", 0x25: "lhu", 0x23: "lw", 0x27: "lwu", 0x37: "ld", 0x1E: "lq",
    0x31: "lwc1", 0x36: "lqc2", 0x22: "lwl", 0x26: "lwr", 0x1A: "ldl", 0x1B: "ldr",
    0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x3F: "sd", 0x1F: "sq", 0x39: "swc1", 0x3E: "sqc2",
    0x2A: "swl", 0x2E: "swr", 0x2C: "sdl", 0x2D: "sdr",
}


def _hex(value: int) -> str:
    return f"0x{value:x}"


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str) and item.strip()]
    return []


def readable_label(symbol: str | None) -> dict[str, str] | None:
    """The demangled ``{"namespace", "name"}`` of a mangled data symbol, or None."""

    parsed = demangle(symbol) if symbol else None
    if not parsed or not parsed.get("qualifier") or parsed.get("params") is not None:
        return None
    return {
        "namespace": "::".join(readable_component(part) for part in parsed["qualifier"]),
        "name": parsed["name"],
    }


def label_text(label: dict[str, str]) -> str:
    """The Ghidra symbol name of a label: ``namespace::name`` (whitespace dropped as stage 2 does)."""

    return symbol_name(f"{label['namespace']}::{label['name']}")


# -- symbol and DWARF facts --------------------------------------------------------


@lru_cache(maxsize=1)
def _dwarf_locations(key: tuple[str, int, int], path: str) -> dict[int, tuple[tuple[str, str, str], ...]]:
    """Static DWARF 1 locations (``DW_OP_ADDR``): address -> (DIE offset, tag, name) rows."""

    from .recon_facts import _dies_cached

    found: dict[int, list[tuple[str, str, str]]] = {}
    for die in _dies_cached(key, path):
        attribute = die.attribute("location")
        value = getattr(attribute, "value", None)
        if isinstance(value, bytes) and len(value) == 5 and value[0] == 0x03:
            address = int.from_bytes(value[1:], "little")
            found.setdefault(address, []).append((_hex(die.offset), die.tag_name, die.string("name") or ""))
    return {address: tuple(rows) for address, rows in found.items()}


def _normalized(values: list[Any]) -> list[int]:
    addresses = []
    for value in values:
        try:
            addresses.append(int(str(value), 16))
        except ValueError:
            raise SocomError(f"{value!r} is not a hex global address") from None
    return addresses


def global_symbol_facts(root: Path, addresses: list[Any]) -> dict[str, dict[str, Any]]:
    """File-only identity facts per address (``0x...``): what the repair route may touch.

    ``object`` is whether a sized .symtab OBJECT starts there; ``size`` its
    largest size; ``dwarf`` the DWARF records located there; ``copies`` the
    object names that also label other addresses (file-local copies, which
    have no canonical copy); ``inside_function`` a FUNC symbol covering it.
    """

    path = root / "support" / "socom.elf"
    elf = Elf32File(path)
    sections = {section.index: section.name for section in elf.sections}
    symbols = elf.symbols()
    at: dict[int, list[Any]] = {}
    addresses_of: dict[str, set[int]] = {}
    functions = []
    for symbol in symbols:
        if not symbol.name or not symbol.value:
            continue
        at.setdefault(symbol.value, []).append(symbol)
        if symbol.type_name == "OBJECT":
            addresses_of.setdefault(symbol.name, set()).add(symbol.value)
        if symbol.type_name == "FUNC" and symbol.size:
            functions.append((symbol.value, symbol.value + symbol.size, symbol.name))
    locations = _dwarf_locations(file_key(path), str(path))
    result = {}
    for address in _normalized(addresses):
        rows = [
            {
                "name": symbol.name,
                "type": symbol.type_name,
                "binding": symbol.binding_name,
                "size": symbol.size,
                "section": sections.get(symbol.section_index, str(symbol.section_index)),
            }
            for symbol in sorted(at.get(address, []), key=lambda value: (value.type_name, value.name))
        ]
        objects = [row for row in rows if row["type"] == "OBJECT" and row["size"]]
        names = sorted({row["name"] for row in objects})
        result[_hex(address)] = {
            "address": _hex(address),
            "symbols": rows,
            "object": bool(objects),
            "names": names,
            "size": max((row["size"] for row in objects), default=None),
            "dwarf": [{"die": die, "tag": tag, "name": name} for die, tag, name in locations.get(address, ())],
            "copies": sorted(name for name in names if len(addresses_of.get(name, ())) > 1),
            "inside_function": next((name for start, end, name in functions if start <= address < end), None),
            "labels": {name: readable_label(name) for name in names},
        }
    return result


def qualifier_globals(root: Path, qualifier: str) -> list[int]:
    """Start addresses of the sized .symtab objects whose demangled qualifier is ``qualifier``.

    Compiler-generated objects (``__vt__``, ``__RTTI__``: names starting with
    ``__``) are left out; the static data members remain.
    """

    found = set()
    for symbol in Elf32File(root / "support" / "socom.elf").symbols():
        if symbol.type_name == "OBJECT" and symbol.size and symbol.value:
            label = readable_label(symbol.name)
            if label and label["namespace"] == qualifier and not label["name"].startswith("__"):
                found.add(symbol.value)
    return sorted(found)


# -- plan rows ------------------------------------------------------------------


def spelled_size(type_name: str) -> int | None:
    """Byte size of a builtin, pointer or array-of-those spelling; None for named composites."""

    match = re.match(r"^(.*?)((?:\[\d+\])*)$", type_name.strip())
    if match is None:
        return None
    element, dims = match.group(1).strip(), re.findall(r"\[(\d+)\]", match.group(2))
    size = 4 if element.endswith("*") else BUILTIN_SIZES.get(element)
    if not isinstance(size, int):
        return None
    for count in dims:
        size *= int(count)
    return size


def _real_type(type_name: str) -> bool:
    """A live type an apply chose (not empty, Ghidra's undefined or an analysis type)."""

    return bool(type_name) and not type_name.startswith("undefined") and type_name not in ANALYSIS_TYPES


def repair_global_problems(entry: dict[str, Any], fact: dict[str, Any] | None) -> list[str]:
    """Problems of one repair ``globals`` row against the global's file-only facts."""

    from .recon import _type_problem

    problems = []
    extra = sorted(set(entry) - ROW_KEYS)
    if extra:
        problems.append(f"unknown keys {extra}: a repair global row has {sorted(ROW_KEYS)}")
    if fact is None or not fact["object"]:
        return problems + ["is not the start of a sized .symtab OBJECT"]
    symbol = entry.get("symbol")
    if symbol not in fact["names"]:
        problems.append(f"symbol must be the .symtab object name at the address ({', '.join(fact['names'])}), not {symbol!r}")
    label = entry.get("label")
    if label is not None:
        derived = readable_label(symbol) if isinstance(symbol, str) else None
        if not isinstance(label, dict) or set(label) != {"namespace", "name"}:
            problems.append("label must be null or {\"namespace\": ..., \"name\": ...}")
        elif derived is None:
            problems.append(f"{symbol!r} has no demangled qualified name: label must be null")
        elif label != derived:
            problems.append(f"label must be the demangled name of {symbol}: {derived}")
        elif not _IDENTIFIER.match(str(label["name"])):
            problems.append(f"label name {label['name']!r} is not an identifier")
    live_type = entry.get("live_type")
    if not isinstance(live_type, str):
        problems.append("needs live_type: the type audit_global shows now ('' when no data is defined)")
        live_type = None
    type_name = entry.get("type")
    if type_name == KEEP:
        if not _texts(entry.get("keep_reason")):
            problems.append("type keep needs keep_reason: why the current type stays (what is unproven)")
    else:
        if entry.get("keep_reason") is not None:
            problems.append("only a keep row carries keep_reason")
        reason = _type_problem(type_name) or (_data_alias_problem(type_name) if isinstance(type_name, str) else None)
        if reason:
            problems.append(f"type: {reason} (or {KEEP!r})")
        else:
            base = _base_type(type_name)
            size = spelled_size(type_name)
            if base in UNDEFINED_TYPES or base in ANALYSIS_TYPES or (base == "void" and not type_name.rstrip().endswith("*")):
                problems.append(f"type {type_name!r} is a placeholder: prove the type or keep the current one")
            elif live_type is not None and type_name == live_type:
                problems.append(f"the type is the live type {live_type!r} already: use {KEEP!r}")
            elif size is not None and size != fact["size"]:
                problems.append(f"type {type_name!r} is {size} bytes, but the .symtab object is {fact['size']}")
    if label is None and type_name == KEEP:
        problems.append("changes nothing: give a label, a type, or both")
    if not _texts(entry.get("repair")):
        problems.append("needs `repair`: why the live state is wrong")
    if not _texts(entry.get("evidence")):
        problems.append("needs evidence")
    if fact["dwarf"]:
        problems.append(
            "DWARF records it (" + ", ".join(f"{row['tag']} {row['die']}" for row in fact["dwarf"])
            + "): stage 2 owns its name and type"
        )
    return problems


def repair_global_entry(entry: dict[str, Any], fact: dict[str, Any]) -> dict[str, Any]:
    """The batch-program row of a valid repair global row.

    ``live_type`` makes the executor refuse, before any write, unless the
    global still shows the recorded name and type; a keep row's type stays
    and is read back as it was.
    """

    label = entry.get("label")
    readable = label_text(label) if label else entry["symbol"]
    keep = entry["type"] == KEEP
    notes = ["repair: " + "; ".join(_texts(entry["repair"]))] + _texts(entry.get("notes"))
    return {
        "address": entry["address"],
        "current_name": entry["symbol"],
        "readable_name": readable,
        "rename": readable != entry["symbol"],
        "type": None if keep else entry["type"],
        "type_skip": f"{KEEP}: " + "; ".join(_texts(entry["keep_reason"])) if keep else None,
        "size": fact["size"],
        "replaces_accepted": (not keep) and _real_type(entry["live_type"]),
        "live_type": entry["live_type"],
        "notes": notes,
    }


# -- code access facts --------------------------------------------------------------


@lru_cache(maxsize=1)
def _tools_cached(key: tuple[str, int, int], root: str) -> tuple[Any, Any, Any]:
    from .recon_facts import context
    from .type_layout import CallParameters, _Receivers, _Symbols, class_leaves, dwarf_scalars, dwarf_subprograms

    base = Path(root)
    ctx = context(base)
    symbols = _Symbols(ctx, dwarf_scalars(base, class_leaves(base)[0]))
    return ctx, symbols, CallParameters(symbols, _Receivers(ctx, symbols, dwarf_subprograms(base)))


class _Facts:
    def __init__(self, root: Path) -> None:
        path = root / "support" / "socom.elf"
        self.root = root
        self.ctx, self.symbols, self.parameters = _tools_cached(file_key(path), str(root))
        self._analyses: dict[int, Any] = {}

    def analysis(self, function: int) -> Any:
        from .type_layout import _Analysis

        if function not in self._analyses:
            self._analyses[function] = _Analysis(self.ctx, self.symbols, function)
        return self._analyses[function]

    def parameter(self, callee: int | None, register: str) -> str:
        found = self.parameters.of(callee, register)
        if "parameter_type" in found:
            return found["parameter_type"]
        if found.get("no_parameter"):
            return "no parameter in that register"
        return f"type unknown: {found.get('parameter_unknown')}"

    def address_text(self, value: Any, function: int) -> str:
        """An abstract address (a value tuple) as text."""

        if value is None:
            return "an address the dataflow does not follow"
        term, offset = value
        tail = f"+0x{offset:x}" if offset > 0 else f"-0x{-offset:x}" if offset < 0 else ""
        if term == ("sym",):
            return self.ctx.object_for(offset) or self.ctx.label(offset)
        if term == ("sp",):
            return f"stack sp{tail or '+0x0'}"
        if term[0] == "ld":
            return f"*({self.address_text(term[1], function)}){tail}"
        if term[0] == "arg":
            return f"parameter {self._gpr(term[1])} of {self.ctx.label(function)}{tail}"
        if term[0] == "res":
            return f"result of the call at 0x{term[1]:x}{tail}"
        if term[0] == "ix":
            return f"{self.address_text(term[1], function)} + index{tail}"
        return f"{term[0]}{tail}"

    @staticmethod
    def _gpr(register: int) -> str:
        from .recon_facts import GPR

        return GPR[register]

    def value_text(self, value: Any, function: int, width: int, kind: str) -> str:
        """Where a stored value comes from."""

        if value is None:
            return "unknown (paths disagree or the dataflow does not follow it)"
        term, offset = value
        if term == ("const",):
            masked = offset & ((1 << (8 * min(width, 8))) - 1) if width else offset
            text = f"constant {offset}" + (f" (0x{masked:x})" if masked > 9 or offset < 0 else "")
            if width == 4 and masked and kind in ("float", "fpr-copy"):
                text += f" = {struct.unpack('<f', masked.to_bytes(4, 'little'))[0]!r}f"
            return text
        if term == ("sym",):
            return f"the address of {self.address_text(value, function)}"
        if term[0] == "arg":
            name = self._gpr(term[1])
            return f"parameter {name} of {self.ctx.label(function)} ({self.parameter(function, name)})" + (
                f" + 0x{offset:x}" if offset else ""
            )
        if term[0] == "farg":
            return f"parameter f{term[1]} of {self.ctx.label(function)} ({self.parameter(function, f'f{term[1]}')})"
        if term[0] == "res":
            call = next((row for row in self.analysis(function).calls if row["site"] == term[1]), None)
            callee = call["callee"] if call else None
            return f"the result of {self.ctx.label(callee) if callee is not None else 'an indirect call'} at 0x{term[1]:x}" + (
                f" + 0x{offset:x}" if offset else ""
            )
        if term[0] == "ld":
            return f"a {term[2]}-byte {term[3]} load of {self.address_text(term[1], function)}" + (
                f" + 0x{offset:x}" if offset else ""
            )
        if term[0] == "bits":
            return "bit operations on a load"
        return f"{term[0]} value"


def _root_load(value: Any) -> Any:
    if value is None:
        return None
    term = value[0]
    if term[0] == "bits":
        return term[1][0]
    return term


def _in(value: Any, start: int, size: int) -> bool:
    return value is not None and value[0] == ("sym",) and start <= value[1] < start + size


def _exit_values(analysis: Any) -> list[tuple[int, Any, Any]]:
    """(jr ra site, v0, f0) after each reachable return's delay slot."""

    from .recon_facts import JR_RA

    rows = []
    for pc in sorted(analysis.states):
        if analysis.ctx.code.word(pc) != JR_RA or pc + 4 not in analysis.states:
            continue
        after = analysis._transfer(pc + 4, analysis.states[pc + 4], record=False)
        rows.append((pc, after.get(2), after.get(("f", 0))))
    return rows


def _load_uses(facts: _Facts, function: int, term: Any) -> list[tuple[str, str | None]]:
    """(text, callee parameter type or None) per use of a loaded value (or call result) in its function."""

    analysis = facts.analysis(function)
    ctx = facts.ctx

    def indexed(value: Any) -> bool:
        # A pointer plus an unknown index, the index added to this value.
        return value is not None and value[0][0] == "ix" and value[0][1] is not None and value[0][1][0] == term

    uses: list[tuple[str, str | None]] = []
    for use in analysis.uses:
        if _root_load(use["value"]) == term:
            uses.append((f"{use['how']} at 0x{use['site']:x} ({ctx.text(use['site'])})", None))
    for call in analysis.calls:
        if call["pointer"] is not None and call["pointer"][0] == term:
            uses.append((f"called through at 0x{call['site']:x}", None))
        for register, value in sorted(call["arguments"].items()):
            if value[0] != term and not indexed(value):
                continue
            plus = " plus an index" if indexed(value) else f" + 0x{value[1]:x}" if value[1] else ""
            callee = call["callee"]
            target = ctx.label(callee) if callee is not None else "an indirect call"
            typed = facts.parameter(callee, register)
            uses.append((f"passed{plus} in {register} to {target} at 0x{call['site']:x} ({typed})", typed))
    for event in analysis.memory + analysis.frame:
        address = event["address"]
        what = "store" if event["store"] else "load"
        if address is not None and (address[0] == term or indexed(address)):
            where = "an index" if indexed(address) else ""
            uses.append(
                (
                    f"dereferenced: {what} {event['width']}-byte {event['kind']} at {where}{'+' if where else ''}0x{address[1]:x} "
                    f"(0x{event['site']:x}: {ctx.text(event['site'])})",
                    None,
                )
            )
        elif event["store"] and event["value"] is not None and (event["value"][0] == term or indexed(event["value"])):
            uses.append((f"stored to {facts.address_text(address, function)} at 0x{event['site']:x}", None))
    for pc, v0, f0 in _exit_values(analysis):
        for name, value in (("v0", v0), ("f0", f0)):
            if value is not None and value[0] == term:
                uses.append((f"left in {name} at the return (jr ra at 0x{pc:x})", None))
    return uses


def _address_uses(facts: _Facts, function: int, start: int, size: int) -> list[tuple[str, str | None]]:
    """Where the global's address goes besides the loads and stores through it."""

    analysis = facts.analysis(function)
    ctx = facts.ctx
    uses: list[tuple[str, str | None]] = []
    for call in analysis.calls:
        for register, value in sorted(call["arguments"].items()):
            if _in(value, start, size):
                callee = call["callee"]
                target = ctx.label(callee) if callee is not None else "an indirect call"
                typed = facts.parameter(callee, register)
                uses.append(
                    (f"address +0x{value[1] - start:x} passed in {register} to {target} at 0x{call['site']:x} ({typed})", typed)
                )
    for event in analysis.memory + analysis.frame:
        if event["store"] and _in(event["value"], start, size):
            uses.append(
                (
                    f"address +0x{event['value'][1] - start:x} stored to {facts.address_text(event['address'], function)} "
                    f"at 0x{event['site']:x}",
                    None,
                )
            )
    for pc, v0, _f0 in _exit_values(analysis):
        if _in(v0, start, size):
            uses.append((f"address +0x{v0[1] - start:x} left in v0 at the return (jr ra at 0x{pc:x})", None))
    return uses


def _caller_uses(facts: _Facts, function: int, registers: set[str], limit: int = 6) -> list[str]:
    """What callers do with v0/f0 after calling a function that leaves the global's value (or address) there."""

    from .recon_facts import _use_after_call, call_sites

    rows = []
    for caller, site, kind in call_sites(facts.ctx, function)[:limit]:
        if kind != "call":
            rows.append(f"tail call at 0x{site:x} in {facts.ctx.label(caller)}: the result is that function's")
            continue
        parts = []
        for register in sorted(registers):
            text = f"{register}: {_use_after_call(facts.ctx, caller, site, register == 'f0')}"
            if register == "v0":
                typed = [use for use, _type in _load_uses(facts, caller, ("res", site))]
                text += f" [{'; '.join(typed[:4])}]" if typed else ""
            parts.append(text)
        rows.append(f"0x{site:x} in {facts.ctx.label(caller)}: " + " || ".join(parts))
    total = len(call_sites(facts.ctx, function))
    if total > limit:
        rows.append(f"... {total - limit} more call sites")
    return rows


def _store_source(facts: _Facts, function: int, site: int) -> str:
    """The reaching definitions of a stored register, when the must-dataflow loses the value."""

    from .recon_facts import _describe_def

    insn = facts.ctx.code.word(site)
    register, fpr = (insn >> 16) & 31, insn >> 26 == 0x39
    flow = facts.ctx.flow(function)
    definitions = sorted(flow.defs(site, register, fpr), key=lambda value: (value == "entry", str(value)))
    shown = []
    for definition in definitions[:6]:
        text = _describe_def(facts.ctx, flow, definition)
        if definition == "entry":
            name = f"f{register}" if fpr else facts._gpr(register)
            text = f"entry {name} ({facts.parameter(function, name)})"
        shown.append(text)
    return "defined by " + " | ".join(shown) if shown else "no reaching definition"


def _initial_bytes(ctx: Any, start: int, size: int) -> str:
    from .recon_facts import object_bytes

    text = object_bytes(ctx, start, min(size, 64))
    if "not in an allocated section" not in text:
        return text
    for segment in ctx.elf.load_segments():
        base = segment.virtual_address
        if base + segment.file_size <= start < base + segment.memory_size:
            return (
                f"0x{start:x}: zero-initialized (beyond the {segment.file_size:#x} file bytes of the load segment at "
                f"0x{base:x}; .bss)"
            )
    return text


def global_facts(root: Path, addresses: list[Any]) -> dict[str, Any]:
    """Facts a planner types a global from, per address (file-only, deterministic)."""

    from .recon_facts import dwarf_entries
    from .type_layout import _MEMORY

    facts = _Facts(root)
    ctx = facts.ctx
    identities = global_symbol_facts(root, addresses)
    rows = []
    for key, identity in identities.items():
        start = int(key, 16)
        size = identity["size"] or 1
        reloc_sites = {
            int(row["site"], 16): row
            for row in ctx.refs
            if row["target"] is not None and start <= int(row["target"], 16) < start + size
        }
        owners = sorted({owner for site in reloc_sites if (owner := ctx.owner(site)) is not None})
        accesses = []
        returned_by: dict[int, set[str]] = {}
        passed: set[str] = set()
        for function in owners:
            analysis = facts.analysis(function)
            seen_sites = set()
            first_load: dict[Any, int] = {}
            for event in sorted(analysis.frame, key=lambda row: row["site"]):
                if not _in(event["address"], start, size):
                    continue
                site = event["site"]
                seen_sites.add(site)
                insn = ctx.code.word(site)
                row = {
                    "site": _hex(site),
                    "function": ctx.label(function),
                    "offset": event["address"][1] - start,
                    "instruction": ctx.text(site),
                    "relocation": reloc_sites[site]["relocation"] if site in reloc_sites else "through a formed address",
                    "access": "store" if event["store"] else "load",
                    "mnemonic": _MNEMONICS.get(insn >> 26, f"opcode 0x{insn >> 26:02x}"),
                    "width": event["width"],
                    "kind": event["kind"],
                    "signed": event["signed"],
                }
                value = event["value"]
                if event["store"]:
                    row["value"] = (
                        facts.value_text(value, function, event["width"], event["kind"])
                        if value is not None
                        else _store_source(facts, function, site)
                    )
                    if value is not None and value[0] == ("const",):
                        row["constant"] = value[1]
                        row["constant_text"] = row["value"]
                    if value is not None and value[0][0] in ("arg", "farg"):
                        name = facts._gpr(value[0][1]) if value[0][0] == "arg" else f"f{value[0][1]}"
                        row["parameter_type"] = facts.parameter(function, name)
                    if value is not None and value[0][0] == "res":
                        call = next((c for c in analysis.calls if c["site"] == value[0][1]), None)
                        row["call_result_of"] = ctx.label(call["callee"]) if call and call["callee"] is not None else None
                elif event["loaded"] is not None:
                    term = event["loaded"][0]
                    if term in first_load:
                        row["same_value_as"] = _hex(first_load[term])
                    else:
                        first_load[term] = site
                        uses = _load_uses(facts, function, term)
                        row["uses"] = [text for text, _type in uses]
                        passed.update(typed for _text, typed in uses if typed)
                        for text, _type in uses:
                            if text.startswith("left in "):
                                returned_by.setdefault(function, set()).add(text.split()[2])
                accesses.append(row)
            for site, reference in sorted(reloc_sites.items()):
                if ctx.owner(site) != function or site in seen_sites:
                    continue
                insn = ctx.code.word(site)
                row = {
                    "site": _hex(site),
                    "function": ctx.label(function),
                    "offset": int(reference["target"], 16) - start,
                    "instruction": ctx.text(site),
                    "relocation": reference["relocation"],
                    "access": "address" if reference["access"] == "DATA" else reference["access"].lower(),
                }
                if insn >> 26 in _MEMORY:
                    width, kind, signed, _store, _fpr = _MEMORY[insn >> 26]
                    row.update(
                        {"mnemonic": _MNEMONICS.get(insn >> 26), "width": width, "kind": kind, "signed": signed,
                         "note": "the dataflow does not reach this access"}
                    )
                accesses.append(row)
            address_uses = _address_uses(facts, function, start, size)
            if address_uses:
                accesses.append(
                    {
                        "site": None,
                        "function": ctx.label(function),
                        "access": "address-use",
                        "uses": [text for text, _type in address_uses],
                    }
                )
                passed.update(f"address: {typed}" for _text, typed in address_uses if typed)
                if any("left in v0" in text for text, _type in address_uses):
                    returned_by.setdefault(function, set()).add("v0")
        outside = sorted(_hex(site) for site in reloc_sites if ctx.owner(site) is None)
        pointing = sorted(
            (site, target) for target, sites in ctx.word32.items() for site in sites if start <= target < start + size
        )
        inside = sorted(site for site in ctx.reloc32 if start <= site < start + size)
        loads = [row for row in accesses if row.get("access") == "load" and row.get("width")]
        stores = [row for row in accesses if row.get("access") == "store" and row.get("width")]
        summary = {
            "widths": sorted({row["width"] for row in loads + stores}),
            "loads": _counts(row["mnemonic"] for row in loads),
            "stores": _counts(row["mnemonic"] for row in stores),
            "kinds": sorted({row["kind"] for row in loads + stores}),
            "offsets": sorted({row["offset"] for row in accesses if "offset" in row}),
            "constants": sorted({row["constant_text"] for row in stores if "constant_text" in row}),
            "stored_parameter_types": sorted({row["parameter_type"] for row in stores if "parameter_type" in row}),
            "stored_call_results": sorted({row["call_result_of"] for row in stores if row.get("call_result_of")}),
            "passed_as": sorted(passed),
            "dereferenced": any(use.startswith("dereferenced") for row in accesses for use in row.get("uses", [])),
            "returned_by": sorted(f"{ctx.label(function)} ({'/'.join(sorted(names))})" for function, names in returned_by.items()),
        }
        rows.append(
            {
                **identity,
                "accesses": accesses,
                "accesses_outside_functions": outside,
                "relocated_words_pointing_here": [
                    {"site": _hex(site), "in": ctx.object_for(site) or ctx.label(site), "target_offset": target - start}
                    for site, target in pointing
                ],
                "relocated_words_inside": [
                    {"offset": site - start, "target": ctx.label(ctx.code.word(site))} for site in inside
                ],
                "bytes": _initial_bytes(ctx, start, size),
                "dwarf_text": dwarf_entries(root, [], 0, None, [start]) if identity["dwarf"] else None,
                "callers_of_returning_functions": {
                    ctx.label(function): _caller_uses(facts, function, returned_by[function]) for function in sorted(returned_by)
                },
                "summary": summary,
            }
        )
    return {"kind": GLOBAL_FACTS_KIND, "schema_version": 1, "mutation_performed": False, "globals": rows}


def _counts(values: Any) -> dict[str, int]:
    found: dict[str, int] = {}
    for value in values:
        found[value] = found.get(value, 0) + 1
    return dict(sorted(found.items()))


def global_facts_text(report: dict[str, Any]) -> str:
    """The facts as compact text, one block per global."""

    blocks = []
    for row in report["globals"]:
        names = ", ".join(row["names"]) or "no sized OBJECT symbol"
        lines = [f"## {row['address']} {names} [{row['size'] or '?'} bytes]"]
        for symbol in row["symbols"]:
            lines.append(
                f"symtab: {symbol['name']} {symbol['binding']} {symbol['type']} size {symbol['size']} in {symbol['section']}"
            )
        for name, label in row["labels"].items():
            lines.append(f"readable label of {name}: " + (label_text(label) if label else "none (not a mangled member)"))
        if row["copies"]:
            lines.append(f"file-local copies share the name(s) {row['copies']}: no copy is canonical")
        if row["inside_function"]:
            lines.append(f"inside function {row['inside_function']}")
        lines.append("DWARF: " + ("; ".join(f"{d['tag']} {d['die']} {d['name']}" for d in row["dwarf"]) or "no record is located here"))
        if row["dwarf_text"]:
            lines.extend("  " + text for text in row["dwarf_text"].splitlines())
        lines.extend(row["bytes"].splitlines())
        if row["relocated_words_pointing_here"]:
            lines.append(
                "relocated words pointing here: "
                + "; ".join(f"{w['site']} ({w['in']}) -> +0x{w['target_offset']:x}" for w in row["relocated_words_pointing_here"][:16])
            )
        if row["relocated_words_inside"]:
            lines.append(
                "relocated words inside: "
                + "; ".join(f"+0x{w['offset']:x} -> {w['target']}" for w in row["relocated_words_inside"][:16])
            )
        if row["accesses_outside_functions"]:
            lines.append(f"code references outside sized functions: {row['accesses_outside_functions']}")
        summary = row["summary"]
        lines.append(
            f"summary: widths {summary['widths']}, loads {summary['loads']}, stores {summary['stores']}, kinds {summary['kinds']}, "
            f"offsets {[f'+0x{value:x}' for value in summary['offsets']]}"
        )
        if summary["constants"]:
            lines.append(f"  constants stored: {summary['constants']}")
        if summary["stored_parameter_types"]:
            lines.append(f"  stored from parameters typed: {summary['stored_parameter_types']}")
        if summary["passed_as"]:
            lines.append(f"  passed as: {summary['passed_as']}")
        if summary["dereferenced"]:
            lines.append("  its value is dereferenced (a pointer)")
        if summary["returned_by"]:
            lines.append(f"  left in a result register at a return by: {summary['returned_by']}")
        lines.append(f"accesses ({sum(1 for a in row['accesses'] if a.get('site'))}):")
        for access in row["accesses"]:
            if access["access"] == "address-use":
                lines.append(f"  {access['function']}: " + "; ".join(access["uses"]))
                continue
            head = f"  {access['site']} {access['function']} +0x{access['offset']:x} {access['access']}"
            if access.get("width"):
                sign = {True: " signed", False: " unsigned"}.get(access.get("signed"), "")
                head += f" {access['width']}-byte {access['kind']}{sign} ({access['mnemonic']})"
            head += f": {access['instruction']} [{access['relocation']}]"
            if access.get("value"):
                head += f"; value: {access['value']}"
            if access.get("note"):
                head += f"; {access['note']}"
            lines.append(head)
            for use in access.get("uses", [])[:8]:
                lines.append(f"      -> {use}")
            if len(access.get("uses", [])) > 8:
                lines.append(f"      -> ... {len(access['uses']) - 8} more")
        for function, uses in row["callers_of_returning_functions"].items():
            lines.append(f"callers of {function}:")
            lines.extend(f"  {use}" for use in uses)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
