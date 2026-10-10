"""Translate an accepted DWARF batch plan into Ghidra function and global operations.

Batch plans carry functions, compile-unit-level variables, and the type rows
they reference; the type foundation already created every named type.  The
apply therefore:

* renames functions and globals to readable demangled names when the name is
  collision-safe, and keeps the mangled symbol as a secondary label;
* sets prototypes from DWARF return and parameter records, filling parameters
  that DWARF omits from the Metrowerks mangled signature (hidden destructor
  flag included).  A receiver is implicit only when DWARF records ``this`` or
  the function's address is in its class's vtable;
* types each placed global with its DWARF type, replacing auto-analysis data;
* records, and does not apply, anything the bridge cannot spell: type names
  with commas or ``&``, names that are not unique ignoring case, member-less
  anonymous RTTI/vtable records, and functions without receiver evidence;
* folds the per-compile-unit DIEs of one global into one entry, refuses a
  plan that places or types a global as code, skips a type the live global
  already has, and keeps a global's symbol when its readable name is taken.

``build_batch_program`` is file-only and deterministic.  ``execute_batch_program``
mutates the live program under the batch apply item's ``ghidra-writer`` lease.
"""

from __future__ import annotations

import itertools
import re
from pathlib import Path
from typing import Any, Callable

from .constants import REFERENCE_SHA256
from .elf import Elf32File
from .mips_flow import decode
from .mwdemangle import demangle, readable_component
from .type_apply import FUND_TYPES, VOID_FUND, _hex10
from .util import SocomError, load_json, sha256_file

BATCH_PROGRAM_KIND = "socom-ghidra-batch-apply-program"
BATCH_PROGRAM_SCHEMA = 1
CALLING_CONVENTION = "__stdcall"
DTOR_FLAG = {"name": "__dtor_flags", "type": "short"}

# cfront-style special function names used by Metrowerks mangling.
OPERATORS = {
    "__nw": "operator new", "__nwa": "operator new[]", "__dl": "operator delete",
    "__dla": "operator delete[]", "__as": "operator=", "__eq": "operator==",
    "__ne": "operator!=", "__lt": "operator<", "__gt": "operator>",
    "__le": "operator<=", "__ge": "operator>=", "__pl": "operator+",
    "__mi": "operator-", "__ml": "operator*", "__dv": "operator/",
    "__md": "operator%", "__vc": "operator[]", "__cl": "operator()",
    "__rf": "operator->", "__apl": "operator+=", "__ami": "operator-=",
    "__amu": "operator*=", "__adv": "operator/=", "__ls": "operator<<",
    "__rs": "operator>>", "__pp": "operator++", "__mm": "operator--",
    "__nt": "operator!", "__co": "operator~", "__aa": "operator&&",
    "__oo": "operator||", "__ad": "operator&", "__or": "operator|",
    "__er": "operator^",
}
# Demangled builtin spellings -> Ghidra type names (EE long is 64-bit).
BUILTINS = {
    "void": "void", "char": "char", "signed char": "schar", "unsigned char": "uchar",
    "short": "short", "unsigned short": "ushort", "int": "int", "unsigned int": "uint",
    "long": "longlong", "unsigned long": "ulonglong", "long long": "longlong",
    "unsigned long long": "ulonglong", "float": "float", "double": "double",
    "bool": "bool",
    # Metrowerks EE wchar_t is two bytes: DWARF spells the MSL wide-char
    # parameters unsigned short where the mangled name has 'w'.
    "wchar_t": "ushort",
}
UNSPELLABLE = re.compile(r"[,&]")
# DWARF 1 modifiers spelled as one pointer level (references are pointers in
# the Metrowerks ABI); const and volatile have no rendering here.
POINTER_MODIFIERS = {"pointer_to", "reference_to"}
# Builtin widths for comparing DWARF and mangled parameter shapes.
BUILTIN_SIZES = {fund.ghidra: fund.size for fund in FUND_TYPES.values()} | {"bool": 1, "schar": 1}


def _squash(name: str) -> str:
    return re.sub(r"\s+", "", name)


def _compatible(dwarf: tuple | None, mangled: tuple | None) -> bool:
    """Whether a DWARF parameter can stand at a mangled position.

    Shapes are (pointer depth, kind, builtin name, size, class names).  An
    unknown shape on either side cannot contradict; a known mismatch does.
    """

    if dwarf is None or mangled is None:
        return True
    if dwarf[0] != mangled[0] or dwarf[1] != mangled[1]:
        return False
    if mangled[1] == "builtin":
        return dwarf[2] == mangled[2] or (dwarf[3] is not None and dwarf[3] == mangled[3])
    return mangled[4] <= dwarf[4]


def symbol_name(readable: str) -> str:
    """Ghidra symbol names cannot hold whitespace; drop it after commas, else '_'."""

    return re.sub(r"\s+", "_", re.sub(r",\s+", ",", readable))


def readable_function_name(mangled: str | None, fallback: str | None) -> str | None:
    """Readable qualified name for a Metrowerks symbol, or the C name."""

    parsed = demangle(mangled) if mangled else None
    if not parsed:
        return fallback
    qualifier = [readable_component(part) for part in parsed["qualifier"]]
    base = parsed["name"]
    class_name = qualifier[-1].split("<", 1)[0] if qualifier else None
    if base == "__ct" and class_name:
        base = class_name
    elif base == "__dt" and class_name:
        base = f"~{class_name}"
    else:
        base = OPERATORS.get(base, base)
    return symbol_name("::".join([*qualifier, base]))


class _Types:
    """Render plan type descriptors as Ghidra bare type names."""

    def __init__(self, plan: dict[str, Any]) -> None:
        self.by_die = {row["evidence"]["die_offset"]: row for row in plan["types"]}
        self.by_qualified = {
            row["qualified_name"]: row["ghidra_path"]
            for row in plan.get("identities", [])
            if row.get("qualified_name") and row.get("ghidra_path")
        }
        self.kinds = {
            row["qualified_name"]: row.get("kind")
            for row in plan.get("identities", [])
            if row.get("qualified_name")
        }

    def byte_size(self, descriptor: dict[str, Any] | None, extent: int | None = None) -> int | None:
        """Size in bytes, or None when the evidence does not fix it.

        ``extent`` (the .symtab size) completes an array whose outermost
        dimension DWARF leaves open ([0..-1]).
        """

        if descriptor is None:
            return None
        if descriptor.get("modifiers"):
            return 4 if all(m in POINTER_MODIFIERS for m in descriptor["modifiers"]) else None
        if descriptor.get("die_offset") is None:
            fund = FUND_TYPES.get(descriptor.get("fund_type"))
            return fund.size if fund else None
        row = self.by_die.get(descriptor["die_offset"])
        if row is None:
            return None
        if row["kind"] == "array_type" and not row.get("ghidra_path"):
            counts = self.array_counts(row, extent)
            element = self.byte_size(row["array"]["element"])
            if counts is None or element is None:
                return None
            total = element
            for count in counts:
                total *= count
            return total
        if row.get("byte_size") is not None:
            return row["byte_size"]
        if row["kind"] == "typedef":
            return self.byte_size(row.get("type"))
        return None

    def array_counts(self, row: dict[str, Any], extent: int | None = None) -> list[int] | None:
        counts = [int(dim[3]) - int(dim[2]) + 1 for dim in row["array"]["dimensions"]]
        if all(count > 0 for count in counts):
            return counts
        if counts[0] > 0 or any(count <= 0 for count in counts[1:]) or not extent:
            return None
        inner = self.byte_size(row["array"]["element"])
        if inner is None:
            return None
        for count in counts[1:]:
            inner *= count
        if inner <= 0 or extent % inner:
            return None
        return [extent // inner, *counts[1:]]

    def render(
        self, descriptor: dict[str, Any] | None, extent: int | None = None
    ) -> tuple[str | None, str | None]:
        """Return (type name, None) or (None, reason)."""

        if descriptor is None:
            return "void", None
        if descriptor.get("modifiers"):
            # The symbol's size is the pointer's, not the pointed-to array's.
            extent = None
        if descriptor.get("die_offset") is None:
            fund = FUND_TYPES.get(descriptor.get("fund_type"))
            if fund is None:
                return None, f"fundamental type {descriptor.get('fund_type')!r}"
            name = fund.ghidra
        else:
            row = self.by_die.get(descriptor["die_offset"])
            if row is None:
                return None, f"DIE 0x{descriptor['die_offset']:x} outside the plan"
            if row.get("ghidra_path"):
                name = row["ghidra_path"].rsplit("/", 1)[1]
            elif row["kind"] == "subroutine_type":
                name = f"@subroutine@{_hex10(row['structural_class'])}"
            elif row["kind"] in ("class_type", "structure_type", "union_type") and row["members"]:
                raw = row.get("raw_name") or "@" + row["kind"].removesuffix("_type")
                name = f"{raw}@{_hex10(row['structural_class'])}"
            elif row["kind"] == "array_type":
                element, reason = self.render(row["array"]["element"])
                if element is None:
                    return None, reason
                counts = self.array_counts(row, extent)
                if counts is None:
                    return None, f"array DIE 0x{row['evidence']['die_offset']:x} has an open extent the symbol does not fix"
                # C and Ghidra spell the outermost extent first: DWARF's
                # TexPhase is 17 elements of int[3], i.e. int[17][3].
                base, inner = re.match(r"^(.*?)((?:\[\d+\])*)$", element).groups()
                name = base + "".join(f"[{count}]" for count in counts) + inner
            else:
                return None, f"{row['kind']} DIE 0x{row['evidence']['die_offset']:x} has no Ghidra type"
        for modifier in descriptor.get("modifiers") or []:
            if modifier not in POINTER_MODIFIERS:
                return None, f"modifier {modifier!r} has no spelling here"
            name = f"{name} *"
        if UNSPELLABLE.search(name):
            return None, f"type name {name!r} contains characters the bridge cannot parse"
        return name, None

    def shape(self, descriptor: dict[str, Any] | None, depth: int = 0, names: frozenset = frozenset(), hops: int = 0) -> tuple | None:
        """Comparable shape of a DWARF type, following typedefs."""

        if descriptor is None:
            return (depth, "builtin", "void", 0, names)
        modifiers = descriptor.get("modifiers") or []
        if any(modifier not in POINTER_MODIFIERS for modifier in modifiers):
            return None
        depth += len(modifiers)
        if descriptor.get("die_offset") is None:
            fund = FUND_TYPES.get(descriptor.get("fund_type"))
            return (depth, "builtin", fund.ghidra, fund.size, names) if fund else None
        row = self.by_die.get(descriptor["die_offset"])
        if row is None:
            return None
        if row.get("qualified_name"):
            names = names | {_squash(str(row["qualified_name"]))}
        if row["kind"] == "typedef" and hops < 16:
            return self.shape(row.get("type"), depth, names, hops + 1)
        if row["kind"] in ("class_type", "structure_type", "union_type", "enumeration_type"):
            return (depth, "class", None, row.get("byte_size"), names)
        return None

    def composite(self, descriptor: dict[str, Any] | None, hops: int = 0) -> bool:
        """Whether a DWARF type is a class, struct or union passed by value."""

        if not descriptor or descriptor.get("modifiers") or descriptor.get("die_offset") is None:
            return False
        row = self.by_die.get(descriptor["die_offset"])
        if row is None:
            # A missing top-level row already fails rendering; a typedef whose
            # target is missing could hide a class, so fail closed.
            return hops > 0
        if row["kind"] == "typedef" and hops < 16:
            return self.composite(row.get("type"), hops + 1)
        return row["kind"] in ("class_type", "structure_type", "union_type")

    def mangled_composite(self, value: dict[str, Any]) -> bool:
        """A mangled by-value class parameter that is not known to be an enum."""

        if value.get("kind") != "class" or set(value.get("modifiers") or []) & {"P", "R"}:
            return False
        qualified = "::".join(readable_component(part) for part in value.get("components", []))
        return self.kinds.get(qualified) != "enumeration_type"

    @staticmethod
    def mangled_shape(value: dict[str, Any]) -> tuple | None:
        modifiers = value.get("modifiers") or []
        if any(modifier not in ("P", "R", "C") for modifier in modifiers):
            return None
        depth = sum(1 for modifier in modifiers if modifier in ("P", "R"))
        if value.get("kind") == "builtin":
            name = BUILTINS.get(value.get("name"))
            return (depth, "builtin", name, BUILTIN_SIZES.get(name), frozenset()) if name else None
        if value.get("kind") == "class":
            qualified = "::".join(readable_component(part) for part in value.get("components", []))
            return (depth, "class", None, None, frozenset({_squash(qualified)}))
        return None

    def render_demangled(self, value: dict[str, Any]) -> tuple[str | None, str | None]:
        modifiers = value.get("modifiers") or []
        if value.get("kind") == "builtin":
            name = BUILTINS.get(value.get("name"))
            if name is None:
                return None, f"builtin {value.get('name')!r}"
        elif value.get("kind") == "class":
            # mwdemangle reports a class parameter's name parts as components.
            qualified = "::".join(readable_component(part) for part in value.get("components", []))
            path = self.by_qualified.get(qualified)
            if path is None:
                return None, f"class {qualified!r} has no identity in the plan"
            name = path.rsplit("/", 1)[1]
        else:
            return None, f"mangled parameter kind {value.get('kind')!r}"
        for modifier in modifiers:
            if modifier in ("P", "R"):
                name = f"{name} *"
            elif modifier != "C":
                return None, f"mangled modifier {modifier!r}"
        if UNSPELLABLE.search(name):
            return None, f"type name {name!r} contains characters the bridge cannot parse"
        return name, None


def _vtable_members(elf: Elf32File, symbols: list[Any]) -> dict[int, list[str]]:
    """Map function addresses to the vtables (by mangled class) that hold them."""

    segment = next(elf.load_segments())
    raw = elf.data
    members: dict[int, list[str]] = {}
    for symbol in symbols:
        if not symbol.name.startswith("__vt__") or not symbol.size:
            continue
        start = symbol.value
        if not (segment.virtual_address <= start and start + symbol.size <= segment.virtual_address + segment.file_size):
            continue
        offset = segment.offset + start - segment.virtual_address
        for index in range(symbol.size // 4):
            word = int.from_bytes(raw[offset + 4 * index : offset + 4 * index + 4], "little")
            if word:
                members.setdefault(word, []).append(symbol.name)
    return members


def _word(elf: Elf32File, address: int) -> int:
    segment = next(elf.load_segments())
    offset = segment.offset + address - segment.virtual_address
    return int.from_bytes(elf.data[offset : offset + 4], "little")


def _canonical_rtti(elf: Elf32File, symbols: list[Any]) -> dict[str, int]:
    """`__RTTI__X` name -> the copy its class vtable's first word points to.

    Metrowerks emits a file-local RTTI copy per compile unit (24 of
    __RTTI__3C2D) but each vtable once; word 0 of `__vt__X` carries an
    R_MIPS_32 relocation to the copy the class actually uses.
    """

    relocated = {row.offset for row in elf.relocations(".relmain") if row.type_name == "R_MIPS_32"}
    addresses: dict[str, set[int]] = {}
    for symbol in symbols:
        if symbol.type_name == "OBJECT" and symbol.value:
            addresses.setdefault(symbol.name, set()).add(symbol.value)
    canonical: dict[str, int] = {}
    for name, places in addresses.items():
        if not name.startswith("__vt__") or len(places) != 1:
            continue
        table = next(iter(places))
        rtti = "__RTTI__" + name[len("__vt__") :]
        if table in relocated and _word(elf, table) in addresses.get(rtti, set()):
            canonical[rtti] = _word(elf, table)
    return canonical


_LOADS = {0x1A, 0x1B, 0x1E, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x31, 0x36, 0x37}
_STORES = {0x1F, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x3F}


def _reads(insn: int) -> tuple[set[int], set[int]]:
    """(GPRs, FPRs) an R5900 instruction reads; conservative for odd forms."""

    op, rs, rt = insn >> 26, (insn >> 21) & 31, (insn >> 16) & 31
    fs, ft = (insn >> 11) & 31, rt
    if op in (0x00, 0x1C):  # SPECIAL, MMI
        return {rs, rt} - {0}, set()
    if op in (0x01, 0x06, 0x07, 0x16, 0x17):  # REGIMM, blez/bgtz(l)
        return {rs} - {0}, set()
    if op in (0x04, 0x05, 0x14, 0x15):  # beq/bne(l)
        return {rs, rt} - {0}, set()
    if op in (0x02, 0x03, 0x0F):  # j, jal, lui
        return set(), set()
    if op in _LOADS:
        return ({rs, rt} if op in (0x22, 0x26, 0x1A, 0x1B) else {rs}) - {0}, set()
    if op in _STORES:
        return {rs, rt} - {0}, set()
    if op == 0x39:  # swc1 ft, off(base)
        return {rs} - {0}, {ft}
    if op == 0x3E:  # sqc2
        return {rs} - {0}, set()
    if op == 0x11:  # COP1
        if rs in (0x04, 0x06):  # mtc1 / ctc1 read a GPR
            return {rt} - {0}, set()
        if rs == 0x00:  # mfc1 reads fs
            return set(), {fs}
        funct = insn & 0x3F
        if rs == 0x14:  # W format: cvt.s.w fd, fs
            return set(), {fs}
        if rs == 0x10:  # S format
            if funct in (0x05, 0x06, 0x07, 0x24):  # abs/mov/neg/cvt.w: fs only
                return set(), {fs}
            if funct == 0x04:  # R5900 sqrt.s fd, ft
                return set(), {ft}
            return set(), {fs, ft}
        return set(), set()
    if op == 0x12:  # COP2 qmtc2 / ctc2
        return ({rt} if rs in (0x05, 0x06) else set()) - {0}, set()
    if 0x08 <= op <= 0x0E or op in (0x18, 0x19):  # immediate ALU
        return {rs} - {0}, set()
    return set(), set()


def _writes_f0(insn: int) -> bool:
    op, rs = insn >> 26, (insn >> 21) & 31
    if op == 0x31:  # lwc1
        return (insn >> 16) & 31 == 0
    if op == 0x11 and rs == 0x04:  # mtc1 rt -> fs
        return (insn >> 11) & 31 == 0
    if op == 0x11 and rs in (0x10, 0x14):  # fd
        return (insn >> 6) & 31 == 0
    return False


def _return_read_site(
    elf: Elf32File, calls: dict[int, list[int]], ends: dict[int, int], target: int
) -> tuple[int, int, str] | None:
    """A call site whose caller reads v0 or f0 after calling `target`.

    The scan runs from the instruction after the call's delay slot to the
    first write of the register or control transfer, so it can miss a use
    but does not invent one.
    """

    for site in calls.get(target, []):
        end = ends.get(site)
        if end is None:
            continue
        live = {"v0": True, "f0": True}
        address = site + 8
        while address < end and any(live.values()):
            insn = _word(elf, address)
            gprs, fprs = _reads(insn)
            if live["v0"] and 2 in gprs:
                return site, address, "v0"
            if live["f0"] and 0 in fprs:
                return site, address, "f0"
            kind = decode(insn, address)["kind"]
            if kind != "plain":
                break
            if 2 in decode(insn, address)["writes"]:
                live["v0"] = False
            if _writes_f0(insn):
                live["f0"] = False
            address += 4
    return None


def _thunk_target(elf: Elf32File, address: int, size: int | None) -> int | None:
    """Target of a function whose whole body is `j target` or `b target`; nop.

    Ghidra makes such a function a thunk, and a thunk shares its target's
    signature: batch 001's COurGame::StopPlay prototype rewrote
    StopPlay__5CGameFv at 0x20e790.
    """

    if size != 8:
        return None
    segment = next(elf.load_segments())
    offset = segment.offset + address - segment.virtual_address
    first = int.from_bytes(elf.data[offset : offset + 4], "little")
    second = int.from_bytes(elf.data[offset + 4 : offset + 8], "little")
    if second != 0:
        return None
    if first >> 26 == 0x02:
        return ((address + 4) & 0xF0000000) | ((first & 0x03FFFFFF) << 2)
    if first >> 26 == 0x04 and (first >> 16) & 0x3FF == 0:
        return address + 4 + ((((first & 0xFFFF) ^ 0x8000) - 0x8000) << 2)
    return None


def _vtable_class(name: str) -> str | None:
    parsed = demangle(name)
    if not parsed or parsed.get("params") is not None:
        return None
    return "::".join(readable_component(part) for part in parsed["qualifier"]) or None


def build_batch_program(root: Path, plan_path: Path) -> dict[str, Any]:
    plan = load_json(plan_path)
    if plan.get("kind") != "socom-ghidra-import-plan" or plan.get("schema_version") != 4:
        raise SocomError("batch programs require a schema 4 socom-ghidra-import-plan")
    if plan.get("conflicts"):
        raise SocomError("the import plan still has blocking conflicts")
    batch = plan.get("batch") or {}
    if batch.get("selection") != "all":
        raise SocomError("batch programs require a selection 'all' plan")
    if (plan.get("target") or {}).get("source_sha256") != REFERENCE_SHA256:
        raise SocomError("the import plan targets a different program")
    elf = Elf32File(root / "support" / "socom.elf")
    symbols = list(elf.symbols())
    vtables = _vtable_members(elf, symbols)
    types = _Types(plan)

    function_sizes = {symbol.value: symbol.size for symbol in symbols if symbol.type_name == "FUNC" and symbol.size}
    # Direct call sites and their caller's end, for return-value contradictions.
    calls: dict[int, list[int]] = {}
    ends: dict[int, int] = {}
    for start, size in sorted(function_sizes.items()):
        for site in range(start, start + size, 4):
            insn = _word(elf, site)
            if insn >> 26 == 0x03:
                calls.setdefault(((site + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2), []).append(site)
                ends[site] = start + size
    functions = []
    names: dict[str, int] = {}
    for row in sorted(plan["functions"], key=lambda item: item["low_pc"] or 0):
        if not row.get("low_pc"):
            continue
        mangled = row.get("mangled_name")
        readable = readable_function_name(mangled, row.get("name"))
        current = mangled or row.get("name")
        parsed = demangle(mangled) if mangled else None
        qualifier = (
            "::".join(readable_component(part) for part in parsed["qualifier"])
            if parsed
            else ""
        )
        notes: list[str] = []
        dwarf_params = list(row["parameters"])
        receiver = None
        if dwarf_params and dwarf_params[0]["name"] == "this":
            receiver = "dwarf-this"
        elif qualifier:
            holders = [
                name
                for name in vtables.get(row["low_pc"], [])
                if _vtable_class(name) == qualifier
            ]
            if holders:
                receiver = f"vtable:{holders[0]}"
        prototype = None
        skip = None
        if parsed is None and mangled:
            skip = "mangled name does not demangle"
        elif qualifier and receiver is None:
            skip = "no evidence whether the method has a receiver"
        else:
            params: list[dict[str, str]] = []
            if receiver and receiver.startswith("vtable:"):
                params.append({"name": "this", "type": qualifier.rsplit("::", 1)[-1] + " *", "source": "vtable"})
                class_path = types.by_qualified.get(qualifier)
                if class_path is None:
                    skip = f"class {qualifier!r} has no identity in the plan"
                else:
                    params[0]["type"] = class_path.rsplit("/", 1)[1] + " *"
            explicit = dwarf_params[1:] if receiver == "dwarf-this" else dwarf_params
            if receiver == "dwarf-this":
                name, reason = types.render(dwarf_params[0]["type"])
                if name is None:
                    skip = reason
                params.append({"name": "this", "type": name or "", "source": "dwarf"})
            mangled_params = (parsed or {}).get("params") or []
            if len(mangled_params) == 1 and mangled_params[0] == {"modifiers": [], "kind": "builtin", "name": "void"}:
                mangled_params = []
            if parsed and len(explicit) > len(mangled_params):
                skip = skip or "DWARF lists more parameters than the mangled signature"
            # Metrowerks DWARF may omit parameters anywhere in the list
            # (LoadTextures__10OrdersMenuFPQ23zdb6CWorldP7C2DFont records only
            # font). Place DWARF parameters as an ordered subsequence of the
            # mangled signature that their types allow; a parameter keeps its
            # DWARF name and type only where every placement agrees.
            owner: dict[int, int] = {}
            if parsed:
                shapes = [types.shape(item["type"]) for item in explicit]
                targets = [types.mangled_shape(value) for value in mangled_params]
                placements = [
                    combo
                    for combo in itertools.combinations(range(len(mangled_params)), len(explicit))
                    if all(_compatible(shapes[i], targets[j]) for i, j in enumerate(combo))
                ]
                if not placements:
                    skip = skip or "DWARF parameters do not align with the mangled signature"
                for index in range(len(explicit)):
                    spots = {combo[index] for combo in placements}
                    if len(spots) == 1:
                        owner[spots.pop()] = index
                if 0 < len(explicit) < len(mangled_params):
                    notes.append(f"DWARF records {len(explicit)} of {len(mangled_params)} mangled parameters")
            else:
                owner = {index: index for index in range(len(explicit))}
            for index, value in enumerate(mangled_params if parsed else explicit):
                if index in owner:
                    item = explicit[owner[index]]
                    name, reason = types.render(item["type"])
                    pname = item["name"] or f"param_{len(params) + 1}"
                    source = "dwarf"
                else:
                    name, reason = types.render_demangled(value)
                    pname = f"param_{len(params) + 1}"
                    source = "mangled"
                if name is None:
                    skip = skip or reason
                params.append({"name": pname, "type": name or "", "source": source})
            if parsed and parsed["name"] == "__dt":
                params.append({**DTOR_FLAG, "source": "metrowerks-destructor"})
                notes.append("hidden destructor flag (short) in the second argument register")
            return_type, reason = types.render(row.get("return_type"))
            if return_type is None:
                skip = skip or reason
            # Every spelling is checked here, whatever its source: a vtable
            # receiver (basic_streambuf<wchar_t, std::char_traits<wchar_t>> *)
            # is not rendered through render().
            unspellable = next((p["type"] for p in params if UNSPELLABLE.search(p["type"])), None)
            if unspellable is not None:
                skip = skip or f"type name {unspellable!r} contains characters the bridge cannot parse"
            if skip is None:
                prototype = {
                    "return_type": return_type,
                    "parameters": [{"name": p["name"], "type": p["type"]} for p in params],
                    "sources": [p["source"] for p in params],
                    "calling_convention": CALLING_CONVENTION,
                }
        if prototype is not None and (
            types.composite(row.get("return_type"))
            or any(types.composite(item["type"]) for item in dwarf_params)
            or any(types.mangled_composite(value) for value in ((parsed or {}).get("params") or []))
        ):
            # Metrowerks passes a by-value class result as a hidden pointer in
            # a0 ahead of this (every size) and does not return it in v0;
            # Ghidra's r5900 __stdcall only hides results over 8 bytes and
            # returns that pointer in v0. Neither model fits, so skip.
            prototype = None
            skip = "by-value class, struct or union return or parameter: Ghidra's storage does not match the Metrowerks ABI"
        if prototype is not None and prototype["return_type"] == "void":
            used = _return_read_site(elf, calls, ends, row["low_pc"])
            if used is not None:
                # Executed code outranks DWARF: record the contradiction and
                # write neither side (sceVu0ClipBBox returns its clip mask).
                prototype = None
                skip = (
                    f"DWARF returns void but the caller's call at 0x{used[0]:x} reads {used[2]} "
                    f"at 0x{used[1]:x}"
                )
        target = _thunk_target(elf, row["low_pc"], function_sizes.get(row["low_pc"]))
        if prototype is not None and target is not None:
            prototype = None
            skip = f"thunk of 0x{target:x}; Ghidra gives a thunk its target's signature"
        if readable:
            names[readable] = names.get(readable, 0) + 1
        functions.append(
            {
                "address": f"0x{row['low_pc']:x}",
                "current_name": current,
                "mangled_name": mangled,
                "readable_name": readable,
                "receiver": receiver,
                "prototype": prototype,
                "prototype_skip": skip,
                "notes": notes,
            }
        )
    function_copies: dict[str, set[int]] = {}
    for symbol in symbols:
        if symbol.type_name == "FUNC" and symbol.value:
            function_copies.setdefault(symbol.name, set()).add(symbol.value)
    for entry in functions:
        name = entry["readable_name"]
        entry["rename"] = bool(name and name != entry["current_name"] and names[name] == 1)
        if entry["rename"] and len(function_copies.get(entry["current_name"], set())) > 1:
            # File-local copies (IOPRebootHandler__FQ211CIOPManager... x3) have
            # no canonical copy; all keep the mangled name.
            entry["rename"] = False
            entry["rename_skip"] = "file-local copies share this name"
        if name and names[name] > 1:
            entry["notes"].append(f"readable name {name!r} is not unique in the batch")

    functions_by_start = sorted(
        (symbol.value, symbol.value + symbol.size, symbol.name)
        for symbol in symbols
        if symbol.type_name == "FUNC" and symbol.size
    )

    def inside_function(address: int) -> str | None:
        for start, end, name in functions_by_start:
            if start <= address < end:
                return name
        return None

    # Metrowerks repeats a global's DIE in each compile unit that declares
    # it; every row at one address must spell the same Ghidra type.
    labels: dict[int, list[Any]] = {}
    copies: dict[str, set[int]] = {}
    for symbol in symbols:
        if symbol.value:
            labels.setdefault(symbol.value, []).append(symbol)
        if symbol.value and symbol.type_name == "OBJECT":
            copies.setdefault(symbol.name, set()).add(symbol.value)
    canonical_rtti = _canonical_rtti(elf, symbols)
    object_sizes: dict[int, set[int]] = {}
    for symbol in symbols:
        if symbol.type_name == "OBJECT" and symbol.value and symbol.size:
            object_sizes.setdefault(symbol.value, set()).add(symbol.size)
    by_address: dict[int, list[dict[str, Any]]] = {}
    for row in sorted(plan["variables"], key=lambda item: (item["address"] or 0, item["name"])):
        if row["status"] == "present":
            by_address.setdefault(row["address"], []).append(row)
    globals_ = []
    for address, rows in by_address.items():
        row = rows[0]
        owner = inside_function(address)
        if owner is not None:
            raise SocomError(f"plan places global {row['name']!r} at 0x{address:x} inside function {owner}")
        mangled = next((name for name in row["symbols"] if demangle(name)), None)
        current = row["symbols"][0] if len(row["symbols"]) == 1 else (mangled or row["name"])
        readable = symbol_name(
            row["symbol_qualified_names"][0] if row["symbol_qualified_names"] else row["name"]
        )
        sizes = object_sizes.get(address, set())
        extent = next(iter(sizes)) if len(sizes) == 1 else None
        rendered = sorted({types.render(item["type"], extent) for item in rows}, key=repr)
        type_name, reason = rendered[0]
        if len(rendered) > 1:
            type_name, reason = None, f"DWARF rows disagree on the type: {[name or why for name, why in rendered]}"
        if type_name and type_name.startswith("@subroutine@"):
            raise SocomError(f"plan types global {row['name']!r} at 0x{address:x} as a function")
        size = None
        descriptor = row["type"]
        if descriptor and descriptor.get("die_offset") is not None and not descriptor.get("modifiers"):
            target = types.by_die[descriptor["die_offset"]]
            if target["kind"] == "array_type" and not target.get("ghidra_path"):
                size = types.byte_size(descriptor, extent)
            else:
                size = target.get("byte_size")
        if type_name and size is not None and extent is not None and size != extent:
            type_name, reason = None, f"DWARF extent {size} differs from the .symtab size {extent}"
        entry = {
            "address": f"0x{row['address']:x}",
            "dwarf_name": row["name"],
            "symbols": row["symbols"],
            "current_name": current,
            "readable_name": readable,
            "rename": readable != current,
            "type": type_name,
            "type_skip": reason,
            "size": size,
            "placement": row["placement"],
        }
        if entry["rename"] and len(copies.get(current, set())) > 1 and canonical_rtti.get(current) != address:
            # File-local copies share one mangled name; only the copy the
            # class vtable references takes the readable name.
            entry["rename"] = False
            if current in canonical_rtti:
                entry["rename_skip"] = f"file-local copy; the class vtable references 0x{canonical_rtti[current]:x}"
            elif current.startswith("__RTTI__"):
                entry["rename_skip"] = "file-local RTTI copies share this name and no vtable references one"
            else:
                entry["rename_skip"] = "file-local copies share this name"

        if address not in object_sizes and labels.get(address) and all(
            symbol.type_name == "NOTYPE" and not symbol.size for symbol in labels[address]
        ):
            # `extern void *_gp` names the linker's small-data base: only
            # zero-size labels (EER27, _gp) sit there, no data object.
            entry.update({"rename": False, "type": None, "skip": "only zero-size linker labels at this address, no data object"})
        globals_.append(entry)
    # Function objects (status function-object) describe code, not data;
    # the plan records them and the program leaves them out.
    absent = sorted(row["name"] for row in plan["variables"] if row["status"] == "absent")
    relative_plan = plan_path.resolve()
    try:
        relative_plan = relative_plan.relative_to(root.resolve())
    except ValueError:
        pass
    return {
        "kind": BATCH_PROGRAM_KIND,
        "schema_version": BATCH_PROGRAM_SCHEMA,
        "mutation_performed": False,
        "plan": {
            "path": Path(relative_plan).as_posix(),
            "sha256": sha256_file(plan_path),
            "work_item_id": batch.get("work_item_id"),
        },
        "functions": functions,
        "globals": globals_,
        "absent_variables": absent,
        "receipt_scope": plan["receipt_scope"],
        "summary": {
            "function_count": len(functions),
            "renamed_function_count": sum(1 for row in functions if row["rename"]),
            "prototype_count": sum(1 for row in functions if row["prototype"]),
            "prototype_skips": sorted({row["prototype_skip"] for row in functions if row["prototype_skip"]}),
            "global_count": len(globals_),
            "typed_global_count": sum(1 for row in globals_ if row["type"]),
            "renamed_global_count": sum(1 for row in globals_ if row["rename"]),
            "absent_variable_count": len(absent),
        },
    }


# -- live execution --------------------------------------------------------


class BatchFailure(SocomError):
    """A failed live step; the unsaved program must be reverted before retrying."""

    def __init__(self, message: str, details: list[Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or []
        self.completed_steps = 0


_FUNCTION_LINE = re.compile(r"^Function:\s+(.*?)\s+at\s+([0-9a-fA-F]+)\s*$")
_SIGNATURE_LINE = re.compile(r"^Signature:\s+(.*)$")


def _base_type(name: str) -> str:
    return re.sub(r"(\s*\*)+$", "", re.sub(r"(\[\d+\])+$", "", name)).strip()


def prototype_text(prototype: dict[str, Any]) -> str:
    """Prototype string for set_function_prototype; the name is parse-only."""

    params = ", ".join(f"{p['type']} {p['name']}" for p in prototype["parameters"]) or "void"
    return f"{prototype['return_type']} socom_prototype({params})"


def expected_signature(prototype: dict[str, Any], name: str) -> str:
    params = ", ".join(f"{p['type']} {p['name']}" for p in prototype["parameters"]) or "void"
    return f"{prototype['return_type']} {prototype['calling_convention']} {name}({params})"


def execute_batch_program(
    program: dict[str, Any],
    bridge: Any,
    *,
    type_index: Callable[[], list[dict[str, Any]]],
    function_names: Callable[[], dict[str, str]],
    global_names: Callable[[], dict[str, set[str]]] = lambda: {},
    log: Callable[[str], None] = lambda _message: None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply a batch program and verify every applied name, prototype, and type.

    With dry_run every live read and pre-write check runs, but no write is
    sent: each would-be bridge call is recorded and the read-back is skipped.
    """

    if program.get("kind") != BATCH_PROGRAM_KIND or program.get("schema_version") != BATCH_PROGRAM_SCHEMA:
        raise SocomError("not a schema 1 batch apply program")
    steps: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    def post(endpoint: str, ok: Callable[[Any], bool], **body: Any) -> Any:
        if dry_run:
            steps.append({"endpoint": endpoint, "body": body, "response": None})
            return None
        response = bridge.post_json(endpoint, **body)
        steps.append({"endpoint": endpoint, "body": body, "response": response})
        if not ok(response):
            failure = BatchFailure(f"{endpoint} failed for {body}: {response!r}")
            failure.completed_steps = len(steps) - 1
            raise failure
        return response

    def success(prefix: str) -> Callable[[Any], bool]:
        return lambda response: isinstance(response, str) and response.startswith(prefix)

    def status_ok(response: Any) -> bool:
        return isinstance(response, dict) and response.get("status") == "success"

    # Names the bridge cannot resolve unambiguously become recorded skips.
    counts: dict[str, int] = {}
    defined: set[str] = set()
    for row in type_index():
        key = row["name"].casefold()
        counts[key] = counts.get(key, 0) + 1
        defined.add(row["name"])
    builtin_names = set(BUILTINS.values()) | {fund.ghidra for fund in FUND_TYPES.values()}

    def ambiguous(type_name: str) -> str | None:
        # The bridge builds one array level from "name[count]"; deeper arrays
        # resolve only if a type of exactly that name exists.
        if type_name.count("[") > 1 and type_name not in defined:
            return f"multi-dimensional array {type_name!r} is not defined in the program"
        base = _base_type(type_name)
        if base in builtin_names:
            return None
        found = counts.get(base.casefold(), 0)
        if found != 1:
            return f"type name {base!r} resolves {found} times ignoring case"
        return None

    # The bridge splits a prototype at commas; refuse before any write.
    for entry in program["functions"]:
        prototype = entry.get("prototype")
        if not prototype:
            continue
        for type_name in (prototype["return_type"], *(param["type"] for param in prototype["parameters"])):
            if UNSPELLABLE.search(type_name):
                raise SocomError(
                    f"prototype for {entry['address']} spells {type_name!r}, which the bridge cannot parse; "
                    "regenerate the program"
                )

    existing = function_names()
    log(f"functions: {len(program['functions'])}")
    applied_functions = []
    for entry in program["functions"]:
        address = entry["address"]
        live_name = existing.get(address)
        if live_name != entry["current_name"]:
            raise SocomError(f"function at {address} is {live_name!r}, expected {entry['current_name']!r}")
        name = entry["current_name"]
        if entry.get("rename_skip"):
            skipped.append({"address": address, "action": "rename", "reason": entry["rename_skip"]})
        if entry["rename"]:
            clash = [other for other, value in existing.items() if value == entry["readable_name"] and other != address]
            if clash:
                skipped.append({"address": address, "action": "rename", "reason": f"name already used at {clash[0]}"})
            else:
                post(
                    "rename_function_by_address",
                    status_ok,
                    function_address=address,
                    new_name=entry["readable_name"],
                    strict_mode="off",
                )
                post("create_label", status_ok, address=address, name=entry["current_name"])
                name = entry["readable_name"]
        prototype = entry["prototype"]
        if prototype:
            reasons = [
                reason
                for reason in (
                    ambiguous(prototype["return_type"]),
                    *(ambiguous(param["type"]) for param in prototype["parameters"]),
                )
                if reason
            ]
            if reasons:
                skipped.append({"address": address, "action": "prototype", "reason": reasons[0]})
                prototype = None
            else:
                post(
                    "set_function_prototype",
                    success("Successfully set prototype"),
                    function_address=address,
                    prototype=prototype_text(prototype),
                    calling_convention=prototype["calling_convention"],
                )
        elif entry["prototype_skip"]:
            skipped.append({"address": address, "action": "prototype", "reason": entry["prototype_skip"]})
        applied_functions.append({"address": address, "name": name, "prototype": prototype})

    log(f"globals: {len(program['globals'])}")
    applied_globals = []
    unchanged: list[dict[str, Any]] = []
    # Names in use, by address ("0x..."), including this run's function renames.
    taken = global_names()
    for function_address, function_name in existing.items():
        taken.setdefault(function_name, set()).add(function_address)
    for applied in applied_functions:
        taken.setdefault(applied["name"], set()).add(applied["address"])
    for entry in program["globals"]:
        address = entry["address"]
        if entry.get("skip"):
            skipped.append({"address": address, "action": "global", "reason": entry["skip"]})
            continue
        audit = bridge.request("audit_global", address=address, strict_mode="off")
        if not isinstance(audit, dict):
            raise SocomError(f"audit_global failed at {address}: {audit!r}")
        if audit.get("is_code_address") or audit.get("is_function_entry"):
            raise SocomError(f"global at {address} is code in the live program")
        live_name = audit.get("name")
        # A global declared in several compile units recurs in later batches;
        # an earlier batch may already have given it its readable name.
        renamed_before = entry["rename"] and live_name == entry["readable_name"]
        if live_name != entry["current_name"] and not renamed_before:
            raise SocomError(f"global at {address} is {live_name!r}, expected {entry['current_name']!r}")
        type_name = entry["type"]
        reason = ambiguous(type_name) if type_name else None
        if reason:
            skipped.append({"address": address, "action": "type", "reason": reason})
            type_name = None
        elif entry["type_skip"]:
            skipped.append({"address": address, "action": "type", "reason": entry["type_skip"]})
        if type_name and audit.get("type") == type_name and (not entry["size"] or audit.get("length") == entry["size"]):
            unchanged.append({"address": address, "action": "type", "type": type_name})
        elif type_name:
            post(
                "apply_data_type",
                lambda response: "error" not in str(response).lower() and "fail" not in str(response).lower(),
                address=address,
                type_name=type_name,
                clear_existing=True,
                strict_mode="off",
            )
        name = entry["current_name"]
        rename = entry["rename"]
        if entry.get("rename_skip"):
            skipped.append({"address": address, "action": "rename", "reason": entry["rename_skip"]})
        if renamed_before:
            unchanged.append({"address": address, "action": "rename", "name": entry["readable_name"]})
            name = entry["readable_name"]
            rename = False
        if rename:
            holders = taken.get(entry["readable_name"], set()) - {address}
            if holders:
                skipped.append(
                    {"address": address, "action": "rename", "reason": f"name already used at {sorted(holders)[0]}"}
                )
                rename = False
        if rename:
            taken.setdefault(entry["readable_name"], set()).add(address)
            post(
                "rename_label",
                status_ok,
                address=address,
                old_name=entry["current_name"],
                new_name=entry["readable_name"],
            )
            post("create_label", status_ok, address=address, name=entry["current_name"])
            name = entry["readable_name"]
        applied_globals.append({"address": address, "name": name, "type": type_name, "size": entry["size"]})

    if dry_run:
        counts: dict[str, int] = {}
        for step in steps:
            counts[step["endpoint"]] = counts.get(step["endpoint"], 0) + 1
        return {
            "ok": True,
            "dry_run": True,
            "bridge_call_count": len(steps),
            "planned_calls": dict(sorted(counts.items())),
            "steps": steps,
            "functions": applied_functions,
            "globals": applied_globals,
            "unchanged": unchanged,
            "skipped": skipped,
        }

    log("verifying")
    mismatches: list[dict[str, Any]] = []
    for applied in applied_functions:
        text = bridge.request("get_function_by_address", address=applied["address"])
        lines = text.splitlines() if isinstance(text, str) else []
        function = next((match for line in lines if (match := _FUNCTION_LINE.match(line))), None)
        signature = next((match for line in lines if (match := _SIGNATURE_LINE.match(line))), None)
        actual_name = function.group(1) if function else None
        expected = expected_signature(applied["prototype"], applied["name"]) if applied["prototype"] else None
        if actual_name != applied["name"] or (expected and (signature is None or signature.group(1) != expected)):
            mismatches.append(
                {
                    "address": applied["address"],
                    "expected_name": applied["name"],
                    "actual_name": actual_name,
                    "expected_signature": expected,
                    "actual_signature": signature.group(1) if signature else None,
                }
            )
    for applied in applied_globals:
        audit = bridge.request("audit_global", address=applied["address"], strict_mode="off")
        if not isinstance(audit, dict) or audit.get("name") != applied["name"] or (
            applied["type"]
            and (audit.get("type") != applied["type"] or (applied["size"] and audit.get("length") != applied["size"]))
        ):
            mismatches.append({"address": applied["address"], "expected": applied, "actual": audit})
    if mismatches:
        failure = BatchFailure(f"{len(mismatches)} applied entries differ from the program", mismatches)
        failure.completed_steps = len(steps)
        raise failure
    log("applied and verified")
    return {
        "ok": True,
        "bridge_call_count": len(steps),
        "functions": applied_functions,
        "globals": applied_globals,
        "unchanged": unchanged,
        "skipped": skipped,
    }
