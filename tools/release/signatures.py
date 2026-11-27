"""Stage 3, step two: carry function prototypes from the prototype program to the release program.

    python tools/release/signatures.py --plan gamez/zArchive          # or --plan --all
    python tools/release/signatures.py --apply build/release/signatures/signatures-gamez-zArchive.json --dry-run
    python tools/release/signatures.py --apply build/release/signatures/signatures-gamez-zArchive.json --yes [--batch N]
    python tools/release/signatures.py --confirm-saved build/release/signatures/signatures-gamez-zArchive.apply-001.json

``--plan`` reads the function map (as ``names.py`` does) and, read-only, both Ghidra programs: for
every pair whose release function exists with the map's extent and is no thunk, the prototype
function's prototype (return type, calling convention, parameter names, types and storage,
varargs, no-return) and the release function's current one. Every type a prototype names must
exist in the release program at the same path with the same size. The plan, with its own digest,
goes to ``build/release/signatures/signatures-<module>.json`` with a summary ``.md``. A pair whose
prototype still has Ghidra's default signature joins the group ``mangled``: its prototype is
derived from the counterpart's mangled symbol (``mangledsig.py``), each decision with its
evidence, and is applied only with ``--classes exact,...,mangled``.

``--apply`` makes the planned changes to ``SCUS_971.34`` only, through ``set_function_prototype``
(and, for a pair that is not exact, ``set_comment`` for the plate flag), never saves, and takes
the exact pairs only unless ``--classes exact,deviating`` is given. Per function it writes, reads
back the whole prototype and compares it field by field; the first mismatch stops the run. A
snapshot of every release function (existence, body, name, signature, thunk flag; the signature
line carries no-return) is compared with the expected state every ``--check-every`` written
functions, whenever analysis is seen running and at the end; any change the plan did not predict
stops the run. Release thunks are never written; a thunk follows its target, as predicted.
Changes that read back go into ``docs/release/ghidra-applied.tsv`` (kind ``prototype``) as
unsaved rows of the report, with ``--confirm-saved`` and ``--discard-unsaved`` as for names.

What the bridge carries, and what it cannot (from the plugin's ``FunctionService`` and Ghidra
12.1.4's ``FunctionSignatureParser``, ``ApplyFunctionSignatureCmd`` and ``FunctionDB``):

* ``set_function_prototype`` parses the text with ``FunctionSignatureParser(dtm, null)``: type
  names are looked up by name in the release program (one match, or the built-ins), parameters
  are split at every comma and the list ends at the first ``)``, so a type or name holding
  ``( ) ,`` cannot be written. ``ApplyFunctionSignatureCmd`` then calls ``updateFunction`` with
  ``DYNAMIC_STORAGE_FORMAL_PARAMS``: storage is recomputed from the calling convention (custom
  storage is switched off and cannot be carried), varargs is set from the text, the signature
  source becomes USER_DEFINED, and a DEFAULT-named function is renamed to the name in the text
  (so the text carries the live name of a FUN_ function and a placeholder otherwise). It never
  sets or clears no-return. A ``calling_convention`` is applied afterwards in a second
  transaction: if it fails, the signature is already written. It acts on the function
  *containing* the address and, for a thunk, on the thunk's target.
* ``set_variable_storage`` changes nothing (it only describes the storage); ``set_parameter_type``,
  ``set_local_variable_type`` and ``rename_variables`` work through the decompiler and may commit
  every parameter it infers; ``set_function_no_return`` changes flow analysis at call sites;
  ``set_function_this_type`` moves the function into a class namespace. None of them is sent.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import datetime as _dt
import json
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import elfimage  # noqa: E402
import ghidra_bridge as gb  # noqa: E402
import mangledsig as ms  # noqa: E402
import mips  # noqa: E402
import names  # noqa: E402
import report  # noqa: E402
from elfimage import PROTOTYPE_SHA256, RELEASE_SHA256  # noqa: E402
from names import Refused, Stop, hx, canonical, sha256_text  # noqa: E402

OUT = Path("build/release/signatures")
PLAN_KIND = "socom-release-signatures-plan"
PLAN_SCHEMA = 1
GROUPS = ("exact", "deviating", "mangled")
PROTOTYPE_ELF = Path("support/socom.elf")
CHECK_EVERY = 10  # written functions between two full snapshots
PLACEHOLDER = "socom_prototype"  # the parse-only name sent for a function that has a name of its own
CONVENTIONS = ("__stdcall", "__thiscall", "__cdecl", "__fastcall", "__vectorcall")  # the plugin's pattern
# Ghidra's built-in types: the parser finds them without the program holding them.
BUILTIN_TYPES = frozenset({
    "void", "undefined", "bool", "byte", "char", "double", "dword", "float", "int", "long", "longdouble",
    "longlong", "qword", "sbyte", "schar", "sdword", "short", "sqword", "sword", "uchar", "uint", "ulong",
    "ulonglong", "ushort", "wchar_t", "wchar16", "wchar32", "word", "float2", "float8", "float10", "float16",
    "int3", "int5", "int6", "int7", "int16", "uint3", "uint5", "uint6", "uint7", "uint16", "pointer",
} | {f"undefined{n}" for n in range(1, 9)})
_DEFAULT_PARAM = re.compile(r"^param_\d+$")


# --- reading a prototype -------------------------------------------------------------------------

def parse_signature(text: str | None, name: str) -> dict | None:
    """The parts of a ``get_function_by_address`` Signature line, given the function's name.

    Ghidra prints ``FunctionDefinitionDataType.getPrototypeString(true)``:
    ``[noreturn ]<return> [<convention> ]<name>(<type> <name>, ...[, ...])``, ``(void)`` when
    there is no parameter. The parameter text is kept whole (``inside``); its pieces come from
    ``get_function_variables``.
    """

    if not isinstance(text, str) or not text.endswith(")"):
        return None
    noreturn = text.startswith("noreturn ")
    body = text[len("noreturn "):] if noreturn else text
    at = body.find(" " + name + "(")
    if at < 0:
        return None
    head, inside = body[:at].split(), body[at + len(name) + 2:-1]
    if not head:
        return None
    convention = head.pop() if len(head) > 1 and head[-1] in CONVENTIONS else None
    varargs = inside == "..." or inside.endswith(", ...")
    fixed = "" if inside in ("void", "...") else (inside[:-len(", ...")] if varargs else inside)
    return {"noreturn": noreturn, "return": " ".join(head), "convention": convention,
            "varargs": varargs, "inside": fixed}


def format_signature(ret: str, convention: str | None, name: str, params: list[dict], varargs: bool,
                     noreturn: bool) -> str:
    """What ``get_function_by_address`` prints for these parts (FunctionDefinitionDataType)."""

    text = ", ".join(f"{p['type']} {p['name']}" for p in params)
    if varargs:
        text += (", " if params else "") + "..."
    return (("noreturn " if noreturn else "") + f"{ret} " + (f"{convention} " if convention else "")
            + f"{name}({text or 'void'})")


def read_variables(bridge, program: str, address: int) -> list[dict]:
    """The parameters of the function starting at ``address``: name, type name, storage, in order."""

    value = bridge.get("get_function_variables", program, address=hx(address))
    if not isinstance(value, dict) or "error" in value or not isinstance(value.get("parameters"), list):
        raise gb.BridgeError(f"get_function_variables {program} {hx(address)}: {str(value)[:200]!r}")
    if int(str(value.get("function_address")), 16) != address:
        raise gb.BridgeError(f"get_function_variables {hx(address)} answered {value.get('function_address')}")
    rows = sorted(value["parameters"], key=lambda p: p["ordinal"])
    return [{"name": p["name"], "type": p["type"], "storage": p["storage"]} for p in rows]


def type_table(bridge, program: str) -> dict[str, list[tuple[str, int | None]]]:
    """Type name -> [(path, size)] of every data type the program holds (``list_data_types``)."""

    text = bridge.get("list_data_types", program, offset=0, limit=1000000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"list_data_types ({program}) answered {str(text)[:200]!r}")
    out: dict[str, list] = defaultdict(list)
    for line in text.splitlines():
        parts = line.split(" | ")
        if len(parts) != 4:
            if line.strip() and not line.startswith("No data types"):
                raise gb.BridgeError(f"list_data_types ({program}): cannot read {line[:120]!r}")
            continue
        size = re.match(r"^(\d+) bytes$", parts[2])
        out[parts[0]].append((parts[3], int(size.group(1)) if size else None))
    return {k: sorted(v) for k, v in out.items()}


# DataTypeUtilities.cPrimitiveNameMap: names DataTypeParser resolves as built-ins first.
C_PRIMITIVES = frozenset({
    "char", "signed char", "unsigned char", "short", "short int", "signed short", "signed short int",
    "unsigned short", "unsigned short int", "int", "signed", "signed int", "unsigned", "unsigned int",
    "long", "long int", "signed long", "signed long int", "unsigned long", "long long", "long long int",
    "signed long long", "signed long long int", "unsigned long long", "unsigned long long int",
    "float", "double", "long double"})
PARSER_RULE = "parser rule: "
_CONFLICT = re.compile(r"\.conflict(?:_?\d+)?$")  # DataTypeUtilities.BASE_DATATYPE_CONFLICT_PATTERN


def strip_conflict(name: str) -> str:
    return _CONFLICT.sub("", name)


def base_type(text: str) -> str:
    """The named type under pointer and array modifiers (``CKey * *`` -> ``CKey``)."""

    return re.sub(r"(?:\s*\*|\s*\[\d*\])+$", "", text).strip()


def check_type(text: str, proto_types: dict, release_types: dict) -> tuple[str | None, str | None]:
    """(reason the type cannot be carried, the missing path) or (None, None)."""

    if any(c in text for c in "(),"):
        return f"type {text} holds ( ) or , which the signature parser cannot read", None
    name = base_type(text)
    if name == "undefined":
        return None, None
    found = proto_types.get(name, [])
    if " ".join(name.split()) in C_PRIMITIVES:
        # DataTypeParser.findDataType takes a C primitive name as Ghidra's built-in before any
        # type of the program: only the built-in itself (at the root) is carried.
        other = [p for p, _ in found if p != "/" + name]
        if other:
            return f"{PARSER_RULE}C primitive name {name}: the parser takes Ghidra's built-in, not {other[0]}", None
        return None, None
    if name in BUILTIN_TYPES and name not in proto_types:
        return None, None
    if not found:
        return f"type {name} is not in the prototype's type list", None
    if len(found) > 1:
        return f"type name {name} names {len(found)} types in the prototype", None
    path, size = found[0]
    # DataTypeManagerDB.findDataTypes ignores .conflict suffixes in the name and in the matches.
    there = sorted(x for n, v in release_types.items() if strip_conflict(n) == strip_conflict(name) for x in v)
    twins = sorted(n for n in release_types if n != name and strip_conflict(n) == strip_conflict(name))
    if twins:
        return (f"{PARSER_RULE}type name {name}: the parser also finds {', '.join(twins)} in the release "
                "(it ignores .conflict suffixes)"), None
    if not there:
        if name in BUILTIN_TYPES and path == "/" + name:
            return None, None  # the parser takes Ghidra's built-in
        return f"missing type {path}", path
    if len(there) > 1:
        return f"type name {name} names {len(there)} types in the release, the parser would refuse it", None
    if there[0][0] != path:
        return f"type {name} lies at {there[0][0]} in the release, at {path} in the prototype", path
    if there[0][1] != size:
        return f"type {path} has {there[0][1]} bytes in the release, {size} in the prototype", None
    return None, None


def can_parse_name(name: str) -> bool:
    """``FunctionSignatureParser.canParseName``."""

    return bool(name) and not any(c in name for c in "()*[], ")


def is_default_signature(sig: dict) -> bool:
    """Undefined return, no parameter, no varargs: the prototype claims nothing to carry."""

    return sig["return"] == "undefined" and not sig["inside"] and not sig["varargs"]


def prototype_value(signature: str, params: list[dict]) -> str:
    """The record's value for a prototype: the Signature line and the storage of each parameter."""

    if not params:
        return signature
    return signature + " [storage " + ", ".join(f"{p['name']}={p['storage']}" for p in params) + "]"


def thunk_signature(target: dict, thunk_name: str, thunk_before: str) -> str:
    """What a thunk shows once its target has ``target`` (FunctionDB: parameters, return and
    convention come from the target; the varargs and no-return flags are the thunk's own)."""

    own = parse_signature(thunk_before, thunk_name) or {"noreturn": False, "varargs": False}
    return format_signature(target["return"], target["convention"], thunk_name, target["parameters"],
                            own["varargs"], own["noreturn"])


# --- the plan --------------------------------------------------------------------------------

def group_of(row: dict, proto: dict | None, placed: frozenset) -> tuple[str | None, str | None]:
    """(group, None) or (None, why the pair carries no signature)."""

    if row["class"] == "exact":
        return "exact", None
    by_place = names.C_PLACE in names.decide_name(row, proto or {"name": row["prototype_symbol"]}, placed)[2]
    if row["class"] == "unsure" and not by_place:
        return None, "unsure pair"
    if row["prototype_classification"] == "provider" and not by_place:
        return None, "library pair that is not exact (C library pairs named by place count as deviating)"
    return "deviating", None


def thunk_rows(bridge, entry: dict, target_parts: dict, thunks_of: dict, live_list: dict) -> list[dict]:
    """The release thunks of an entry's function, with the signature each shows after the write."""

    rows = []
    for thunk in thunks_of.get(int(entry["address"], 16), []):
        shown = live_list[thunk]["name"]
        before = names.read_function(bridge, gb.RELEASE_PROGRAM, thunk)
        rows.append({"address": hx(thunk), "name": shown, "signature_before": before["signature"],
                     "signature_after": thunk_signature(target_parts, shown, before["signature"])})
    return rows


def plan_mangled(bridge, defaults: list, image, prototype_image, proto_types: dict, release_types: dict,
                 thunks_of: dict, live_list: dict) -> list:
    """Group mangled: derive the prototypes of the entries that reached ``default``.

    Each entry joins the group (``pair_group`` keeps exact or deviating) and is withheld with the
    derivation's reason, or gets ``send``/``expected`` and goes on like the carried ones. The code
    rule reads the release function's own bytes; ``mangled.prototype_bytes_this`` says what the
    prototype's bytes would have decided.
    """

    facts = ms.Facts(prototype_image)
    types = ms.Types(release_types, strip_conflict, C_PRIMITIVES)
    words_r, words_p = mips.words_of(image.data), mips.words_of(prototype_image.data)
    need = sorted({s for _, row, _, _ in defaults for s in ms.siblings(row["prototype_address"], facts)})
    returns = {}
    for address in need:  # the signed overrides of the same slots (their return types)
        found = names.read_function(bridge, gb.PROTOTYPE_PROGRAM, address)
        sig = parse_signature(found and found.get("signature"), found["name"]) if found else None
        if found and found["entry"] == address and sig and not is_default_signature(sig):
            returns[address] = sig["return"]

    def check_return(text: str) -> str | None:
        return check_type(text, proto_types, release_types)[0]

    out = []
    for entry, row, live, here in defaults:
        entry["pair_group"], entry["group"] = entry["group"], "mangled"
        address = row["prototype_address"]
        reads = ms.entry_reads(words_r, (row["release_address"] - image.base) // 4, row["release_size"] // 4,
                               image.base)
        proto_reads = None
        if row.get("prototype_size") and prototype_image.contains(address):
            proto_reads = ms.entry_reads(words_p, (address - prototype_image.base) // 4, row["prototype_size"] // 4,
                                         prototype_image.base)
        try:
            derived = ms.derive(address, facts, types, reads, proto_reads, returns, check_return)
        except ms.Withheld as exc:
            entry.update({"action": "withheld", "reason_group": f"mangled {exc.group}", "reason": exc.reason,
                          "mangled": exc.details})
            continue
        entry["mangled"] = {k: v for k, v in derived.items() if k != "parameters"}
        params = [{"name": p["name"], "type": p["type"], "storage": p["storage"]} for p in derived["parameters"]]
        default_name = names.is_default_name(live["name"])
        sent_name = live["name"] if default_name else PLACEHOLDER
        if default_name and not can_parse_name(sent_name):
            entry.update({"action": "withheld", "reason_group": "name",
                          "reason": f"the default name {sent_name} cannot be parsed"})
            continue
        entry["send"] = {"prototype": ms.text_of(derived["return"], sent_name, params, derived["varargs"]),
                         "calling_convention": ms.CONVENTION}
        entry["expected"] = {"signature": format_signature(derived["return"], ms.CONVENTION, live["name"], params,
                                                           derived["varargs"], here["noreturn"]),
                             "parameters": params}
        entry["differences"] = []
        entry["thunks"] = thunk_rows(bridge, entry, {"return": derived["return"], "convention": ms.CONVENTION,
                                                     "parameters": params}, thunks_of, live_list)
        out.append((entry, here, live))
    return out


def recorded_prototype(entry: dict) -> str:
    """The record's value for an entry's prototype; a derived one is marked as derived."""

    value = prototype_value(entry["expected"]["signature"], entry["expected"]["parameters"])
    return value + ms.DERIVED_MARK if entry["group"] == "mangled" else value


def holds(now: str | None, value: str) -> bool:
    """The program holds the recorded ``value`` (a derived prototype's mark is the record's own)."""

    return now == value or (now is not None and value.endswith(ms.DERIVED_MARK) and now + ms.DERIVED_MARK == value)


def build_plan(root: Path, bridge, module: str | None, progress=None, image=None, prototype_image=None) -> dict:
    check = names.preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    rows, _, map_sha = names.load_map(root)
    proto_list = names.function_list(bridge, gb.PROTOTYPE_PROGRAM)
    live_list = names.function_list(bridge, gb.RELEASE_PROGRAM)
    proto_types = type_table(bridge, gb.PROTOTYPE_PROGRAM)
    release_types = type_table(bridge, gb.RELEASE_PROGRAM)
    chosen = names.select(rows, module)
    placed = names.library_place(rows)
    image = image or elfimage.load(root / names.RELEASE_ELF, "release")
    targets = names.thunk_targets(live_list)
    for address, target in list(targets.items()):
        if target is None:
            targets[address] = names.image_thunk_target(image, address)
    thunks_of: dict[int, list[int]] = defaultdict(list)
    for thunk, target in sorted(targets.items()):
        if target is not None:
            thunks_of[target].append(thunk)

    entries, pending, defaults = [], [], []
    for row in chosen:
        address, end = row["release_address"], row["release_address"] + row["release_size"] - 1
        if row["prototype_address"] is None:
            continue  # a new function: nothing to carry
        entry = {"address": hx(address), "end": hx(end), "class": row["class"], "group": None,
                 "module": report.module_label(row), "flags": row["flags"],
                 "source_pair": f"{hx(row['prototype_address'])} {row['prototype_symbol']} ({row['class']})"}
        entries.append(entry)

        def withhold(group_code: str, reason: str, entry=entry) -> None:
            entry.update({"action": "withheld", "reason_group": group_code, "reason": reason})

        listed = proto_list.get(row["prototype_address"])
        group, why = group_of(row, listed, placed)
        entry["group"] = group
        if why:
            withhold("pair", why)
            continue
        blocked = [f for f in row["flags"] if f in names.NAME_BLOCK]
        if blocked:
            withhold("flag", f"flag {blocked[0]}: {names.NAME_BLOCK[blocked[0]]}")
            continue
        live = names.read_function(bridge, gb.RELEASE_PROGRAM, address)
        if not live:
            withhold("function", "no release function at the map start")
            continue
        if live["entry"] != address:
            withhold("function", f"inside the release function at {hx(live['entry'])}")
            continue
        if live["body_min"] != address or live["body_max"] != end:
            withhold("function", f"boundary: Ghidra's body {hx(live['body_min'])}..{hx(live['body_max'])}, "
                                 f"the map's {hx(address)}..{hx(end)}")
            continue
        if live_list.get(address, {}).get("thunk"):
            withhold("thunk", "a Ghidra thunk: it follows its target's signature and is never written")
            continue
        proto = names.read_function(bridge, gb.PROTOTYPE_PROGRAM, row["prototype_address"])
        if not listed or not proto or proto["entry"] != row["prototype_address"]:
            withhold("prototype", "no prototype function at the counterpart's address")
            continue
        if listed["thunk"]:
            withhold("prototype", "the prototype counterpart is a thunk")
            continue
        if not names.is_default_name(live["name"]) and live["name"] != proto["name"]:
            withhold("name", f"the release function is named {live['name']}, its counterpart {proto['name']}")
            continue
        sig = parse_signature(proto.get("signature"), proto["name"])
        if sig is None:
            withhold("parse", f"cannot read the prototype's signature {proto.get('signature')!r}")
            continue
        here = parse_signature(live.get("signature"), live["name"])
        if here is None:
            withhold("parse", f"cannot read the release signature {live.get('signature')!r}")
            continue
        entry["prototype"] = {"address": hx(row["prototype_address"]), "name": proto["name"],
                              "signature": proto["signature"], "return": sig["return"],
                              "convention": sig["convention"], "varargs": sig["varargs"],
                              "noreturn": sig["noreturn"], "parameters": []}
        entry["release"] = {"name": live["name"], "signature": live["signature"], "noreturn": here["noreturn"]}
        if is_default_signature(sig):
            entry.update({"action": "default", "reason_group": "default",
                          "reason": "the prototype's signature is Ghidra's default: nothing to carry"
                          + (f" (only the convention {sig['convention']} is set)" if sig["convention"] else "")})
            defaults.append((entry, row, live, here))
            continue
        pending.append((entry, sig, here, row, live))

    # Parameters, types and storage come from get_function_variables (it decompiles: ~0.2 s).
    need = sorted({int(e["prototype"]["address"], 16) for e, sig, *_ in pending if sig["inside"]})
    if progress:
        progress(f"prototype parameters of {len(need)} functions")
    proto_vars = read_many(bridge, gb.PROTOTYPE_PROGRAM, need)
    missing: Counter = Counter()
    checked: set[str] = set()  # every base type name a considered prototype names
    later = []
    for entry, sig, here, row, live in pending:
        params = proto_vars.get(int(entry["prototype"]["address"], 16), []) if sig["inside"] else []
        entry["prototype"]["parameters"] = params
        if ", ".join(f"{p['type']} {p['name']}" for p in params) != sig["inside"]:
            entry.update({"action": "withheld", "reason_group": "parse",
                          "reason": "the prototype's signature line and its parameter list disagree"})
            continue
        reason = None
        for text in [sig["return"]] + [p["type"] for p in params]:
            checked.add(base_type(text))
            reason, path = check_type(text, proto_types, release_types)
            if path:
                missing[path] += 1
            if reason:
                break
        if reason:
            entry.update({"action": "withheld", "reason_group": "parser-rule" if reason.startswith(PARSER_RULE)
                          else "type", "reason": reason})
            continue
        bad = [p["name"] for p in params if not can_parse_name(p["name"])]
        auto = [p["name"] for p in params if p["name"] == "__return_storage_ptr__"
                or (p["name"] == "this" and sig["convention"] == "__thiscall")]
        if bad or auto:
            entry.update({"action": "withheld", "reason_group": "parameter",
                          "reason": f"parameter {(bad or auto)[0]} cannot be written as text"
                          + (" (an auto-parameter the convention makes)" if auto else "")})
            continue
        if sig["varargs"] and not params:
            entry.update({"action": "withheld", "reason_group": "parameter",
                          "reason": "varargs without a fixed parameter: the parser sets varargs only after a comma"})
            continue
        if any(re.search(r"\[\d*\]$", p["type"]) for p in params):
            entry.update({"action": "withheld", "reason_group": "parameter",
                          "reason": "an array parameter: Ghidra may pass it as a pointer (settleCDataType)"})
            continue
        default_name = names.is_default_name(live["name"])
        sent_name = live["name"] if default_name else PLACEHOLDER
        if default_name and not can_parse_name(sent_name):
            entry.update({"action": "withheld", "reason_group": "name",
                          "reason": f"the default name {sent_name} cannot be parsed"})
            continue
        text = format_signature(sig["return"], None, sent_name, params, sig["varargs"], False)
        expected = format_signature(sig["return"], sig["convention"], live["name"], params, sig["varargs"],
                                    here["noreturn"])
        entry["send"] = {"prototype": text, "calling_convention": sig["convention"]}
        entry["expected"] = {"signature": expected, "parameters": params}
        entry["differences"] = ([f"no-return: prototype {sig['noreturn']}, release {here['noreturn']} "
                                 "(listed, not applied)"] if sig["noreturn"] != here["noreturn"] else [])
        target_parts = {"return": sig["return"], "convention": sig["convention"], "parameters": params}
        entry["thunks"] = thunk_rows(bridge, entry, target_parts, thunks_of, live_list)
        later.append((entry, here, live))

    # Group mangled: the defaults, derived from the counterpart's mangled symbol (mangledsig.py).
    if defaults:
        if progress:
            progress(f"mangled symbols of {len(defaults)} prototype functions with Ghidra's default signature")
        prototype_image = prototype_image or elfimage.load(root / PROTOTYPE_ELF, "prototype")
        later += plan_mangled(bridge, defaults, image, prototype_image, proto_types, release_types,
                              thunks_of, live_list)

    # A release signature that is set already: equal (then the storage decides) or replaced.
    same = sorted(int(e["address"], 16) for e, here, live in later if live["signature"] == e["expected"]["signature"])
    release_vars = read_many(bridge, gb.RELEASE_PROGRAM, same)
    for entry, here, live in later:
        address = int(entry["address"], 16)
        entry["replaces"] = None
        if address in release_vars or live["signature"] == entry["expected"]["signature"]:
            if release_vars.get(address, []) != entry["expected"]["parameters"]:
                entry.update({"action": "withheld", "reason_group": "storage",
                              "reason": "the release has this signature with another storage "
                                        f"({release_vars.get(address)})"})
                continue
            entry.update({"action": "unchanged", "reason_group": None, "reason": "the release has this prototype"})
        elif not is_default_signature(here) and entry["group"] == "mangled":
            entry.update({"action": "withheld", "reason_group": "live",
                          "reason": f"Ghidra already gives it {live['signature']}; a derived signature replaces none"})
            continue
        elif not is_default_signature(here) and entry["group"] != "exact":
            entry.update({"action": "withheld", "reason_group": "live",
                          "reason": f"Ghidra already gives it {live['signature']} and the pair is not exact"})
            continue
        elif not is_default_signature(here) and entry["prototype"]["return"] == "undefined" != here["return"]:
            entry.update({"action": "withheld", "reason_group": "live",
                          "reason": f"Ghidra already gives it {live['signature']}, whose return type the "
                                    "prototype leaves undefined"})
            continue
        else:
            entry["replaces"] = None if is_default_signature(here) else live["signature"]
            entry.update({"action": "write", "reason_group": None, "reason": None})
        if entry["group"] == "deviating":
            plate = names.read_plate(bridge, address)
            if not plate.startswith(names.PLATE_PREFIX):
                entry.update({"action": "withheld", "reason_group": "plate",
                              "reason": "no plate comment of the names step to flag"})
                continue
            first, clauses = names.plate_clauses(plate)
            after = plate if names.SIGNATURE_CLAUSE in clauses else names.join_plate(
                first, clauses + [names.SIGNATURE_CLAUSE])
            entry["plate"] = {"before": plate, "after": after}
        elif entry["group"] == "mangled":
            plate = names.read_plate(bridge, address)
            if not plate.startswith(names.PLATE_PREFIX):
                entry.update({"action": "withheld", "reason_group": "plate",
                              "reason": "no plate comment of the names step to carry the derived-signature clause"})
                continue
            clause = entry["mangled"]["clause"]
            first, clauses = names.plate_clauses(plate)
            other = [c for c in clauses if c.startswith(names.MANGLED_CLAUSE) and c != clause]
            if other:
                entry.update({"action": "withheld", "reason_group": "plate",
                              "reason": f"the plate holds another derived-signature clause: {other[0]}"})
                continue
            after = plate if clause in clauses else names.join_plate(first, clauses + [clause])
            entry["plate"] = {"before": plate, "after": after}

    plan = {
        "kind": PLAN_KIND, "schema_version": PLAN_SCHEMA, "program": gb.RELEASE_PROGRAM,
        "program_path": gb.RELEASE_PATH, "reference_program": gb.PROTOTYPE_PROGRAM,
        "release_sha256": RELEASE_SHA256, "prototype_sha256": PROTOTYPE_SHA256,
        "selection": module or "--all", "function_map_sha256": map_sha,
        "entries": entries, "missing_types": dict(sorted(missing.items())),
        # The two DataTypeParser rules (C primitive names first; .conflict ignored), over every
        # type name a considered prototype names: which of them the rules would resolve elsewhere.
        "parser_rules": {
            "type_names_checked": len(checked),
            "c_primitive_names": sorted(n for n in checked if " ".join(n.split()) in C_PRIMITIVES),
            "with_conflict_twins_in_release": sorted(
                n for n in checked if any(m != n and strip_conflict(m) == strip_conflict(n) for m in release_types)),
            "resolved_elsewhere": sorted({e["reason"] for e in entries if e.get("reason_group") == "parser-rule"}),
        },
    }
    plan["summary"] = summarize(plan)
    plan["plan_sha256"] = sha256_text(canonical(plan))
    return plan


def read_many(bridge, program: str, addresses: list[int]) -> dict[int, list[dict]]:
    """``read_variables`` for many functions on three read-only connections."""

    if not addresses:
        return {}
    clients = bridge.clones(3)
    chunks = [addresses[i::len(clients)] for i in range(len(clients))]
    with ThreadPoolExecutor(len(clients)) as pool:
        parts = pool.map(lambda pair: [(a, read_variables(pair[0], program, a)) for a in pair[1]],
                         zip(clients, chunks))
    return dict(item for part in parts for item in part)


def summarize(plan: dict) -> dict:
    entries = plan["entries"]
    by = Counter(f"{e['group'] or '-'} / {e['action']}" for e in entries)
    withheld = Counter(e["reason_group"] for e in entries if e["action"] == "withheld")
    reasons = Counter(re.sub(r"0x[0-9a-f]+", "0x..", e["reason"]) for e in entries if e["action"] == "withheld")
    defaults = [e for e in entries if e["action"] == "default"]
    writes = [e for e in entries if e["action"] == "write"]
    return {
        "pairs": len(entries),
        "by_group_and_action": dict(sorted(by.items())),
        "planned": dict(sorted(Counter(e["group"] for e in writes).items())),
        "unchanged": sum(1 for e in entries if e["action"] == "unchanged"),
        "withheld_by_reason": dict(sorted(withheld.items())),
        "withheld_reasons": dict(sorted(reasons.items())),
        "default_prototype_signatures": len(defaults),
        "default_with_convention_only": sum(1 for e in defaults if e["prototype"]["convention"]),
        "missing_types": len(plan["missing_types"]),
        "parser_rules": (f"{plan['parser_rules']['type_names_checked']} type names checked; C primitive names "
                         f"{len(plan['parser_rules']['c_primitive_names'])} (all Ghidra's built-in unless listed); "
                         f".conflict twins {len(plan['parser_rules']['with_conflict_twins_in_release'])}; "
                         f"resolved elsewhere, withheld {sum(1 for e in entries if e.get('reason_group') == 'parser-rule')}"),
        "replaces_a_live_signature": sum(1 for e in writes if e.get("replaces")),
        "thunks_that_follow": sum(len(e["thunks"]) for e in writes),
        "plate_flags": sum(1 for e in entries if e.get("plate") and e["plate"]["after"] != e["plate"]["before"]),
        "no_return_differences": sum(1 for e in writes if e["differences"]),
        "with_convention": dict(sorted(Counter(e["send"]["calling_convention"] or "none" for e in writes).items())),
        "mangled": mangled_summary(entries),
    }


def _evidence_kind(text: str) -> str:
    text = re.sub(r"^slot \d+ of \S+$", "vtable slot", text)
    text = re.sub(r"^the code reads \w+ at 0x[0-9a-f]+, ", "code: ", text)
    return re.sub(r"the code reads \w+, beyond", "the code reads a GPR beyond", text)


def mangled_summary(entries: list[dict]) -> dict:
    """Group mangled: planned by module and pair class, withheld by reason, the evidence used."""

    group = [e for e in entries if e["group"] == "mangled"]
    planned = [e for e in group if e["action"] in ("write", "unchanged")]
    withheld = [e for e in group if e["action"] == "withheld"]
    derived = [e for e in group if e.get("mangled")]
    changed = [e for e in derived if e["mangled"].get("prototype_bytes_this", e["mangled"]["this"]) != e["mangled"]["this"]]
    return {
        "entries": len(group),
        "planned": len(planned),
        "planned_by_pair": dict(sorted(Counter(e["pair_group"] for e in planned).items())),
        "planned_by_module": dict(sorted(Counter(e["module"] for e in planned).items())),
        "with_a_return_type": sum(1 for e in planned if e["mangled"]["return"] != "undefined"),
        "withheld_by_reason": dict(sorted(Counter(e["reason_group"] for e in withheld).items())),
        "withheld_reasons": dict(Counter(re.sub(r"0x[0-9a-f]+", "0x..", re.sub(r" /project\S*", " <type>", e["reason"]))
                                         for e in withheld).most_common(40)),
        "this_evidence": dict(sorted(Counter(_evidence_kind(e["mangled"]["this_evidence"]) for e in planned).items())),
        "return_evidence": dict(sorted(Counter(e["mangled"]["return_evidence"] for e in planned).items())),
        "code_rule_release_vs_prototype_bytes": {
            "decisions_that_differ": len(changed),
            "examples": [f"{e['address']} {e['mangled']['symbol']}: release {e['mangled']['this']}, prototype bytes "
                         f"{e['mangled']['prototype_bytes_this']} ({e['pair_group']})" for e in changed[:20]]},
    }


def plan_markdown(plan: dict) -> str:
    s = plan["summary"]
    lines = [f"# Signatures plan: {plan['selection']}", "",
             f"Program `{plan['program']}`; function map sha256 `{plan['function_map_sha256'][:16]}`; "
             f"plan sha256 `{plan['plan_sha256']}`.", "",
             f"- pairs considered: {s['pairs']}; planned: {s['planned']}; unchanged: {s['unchanged']}",
             f"- by group and action: {s['by_group_and_action']}",
             f"- withheld by reason: {s['withheld_by_reason']}",
             f"- default prototype signatures (nothing to carry): {s['default_prototype_signatures']} "
             f"({s['default_with_convention_only']} with only a convention set)",
             f"- parser rules (C primitive names first, .conflict ignored): {s['parser_rules']}",
             f"- missing types: {s['missing_types']}; live signatures replaced: {s['replaces_a_live_signature']}; "
             f"thunks that follow: {s['thunks_that_follow']}; plate flags: {s['plate_flags']}; "
             f"no-return differences (not applied): {s['no_return_differences']}",
             f"- calling conventions sent: {s['with_convention']}",
             "", "The deviating group is applied only with `--classes exact,deviating`; the mangled group "
             "(signatures derived from the counterpart's mangled symbol) only with `--classes exact,...,mangled`.",
             "", "## Group mangled", "",
             f"- planned: {s['mangled']['planned']} of {s['mangled']['entries']} "
             f"(by pair {s['mangled']['planned_by_pair']}; {s['mangled']['with_a_return_type']} with a return type)",
             f"- withheld by reason: {s['mangled']['withheld_by_reason']}",
             f"- this evidence: {s['mangled']['this_evidence']}",
             f"- return evidence: {s['mangled']['return_evidence']}",
             f"- code rule, release bytes against prototype bytes: "
             f"{s['mangled']['code_rule_release_vs_prototype_bytes']['decisions_that_differ']} decisions differ",
             "", "Planned by module:", ""]
    lines += [f"- {m}: {n}" for m, n in s["mangled"]["planned_by_module"].items()]
    lines += ["", "## Withheld, by reason", ""]
    lines += [f"- {count}: {reason}" for reason, count in sorted(s["withheld_reasons"].items(), key=lambda kv: (-kv[1], kv[0]))]
    if plan["missing_types"]:
        lines += ["", "## Missing types (prototype path: signatures that name it)", ""]
        lines += [f"- `{path}`: {count}" for path, count in plan["missing_types"].items()]
    replaced = [e for e in plan["entries"] if e["action"] == "write" and e.get("replaces")]
    if replaced:
        lines += ["", "## Live signatures replaced (exact pairs)", ""]
        lines += [f"- {e['address']}: `{e['replaces']}` -> `{e['expected']['signature']}`" for e in replaced]
    diffs = [e for e in plan["entries"] if e["action"] == "write" and e["differences"]]
    if diffs:
        lines += ["", "## No-return differences (listed, not applied)", ""]
        lines += [f"- {e['address']} {e['release']['name']}: {'; '.join(e['differences'])}" for e in diffs]
    thunks = [(e, t) for e in plan["entries"] if e["action"] == "write" for t in e["thunks"]]
    if thunks:
        lines += ["", "## Thunks predicted to follow their target", ""]
        lines += [f"- {t['address']} -> {e['address']}: `{t['signature_after']}`" for e, t in thunks]
    return "\n".join(lines) + "\n"


def plan_stem(selection: str) -> str:
    return "signatures-" + ("all" if selection == "--all" else re.sub(r"[^A-Za-z0-9._-]+", "-", selection).strip("-"))


def write_plan(root: Path, plan: dict) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    stem = plan_stem(plan["selection"])
    (out / f"{stem}.json").write_text(canonical(plan), encoding="utf-8", newline="\n")
    (out / f"{stem}.md").write_text(plan_markdown(plan), encoding="utf-8", newline="\n")
    return out / f"{stem}.json"


def load_plan(path: Path, root: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("kind") != PLAN_KIND or plan.get("schema_version") != PLAN_SCHEMA:
        raise Refused(f"{path.name} is not a schema {PLAN_SCHEMA} signatures plan")
    if plan.get("program") != gb.RELEASE_PROGRAM:
        raise Refused(f"the plan targets {plan.get('program')!r}; writes go to {gb.RELEASE_PROGRAM} only")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if sha256_text(canonical(body)) != plan.get("plan_sha256"):
        raise Refused(f"{path.name} does not match its plan_sha256: regenerate it instead of editing it")
    if plan.get("function_map_sha256") != names.current_map_sha(root):
        raise Refused(f"{path.name} was made from another {names.MAP_TSV.as_posix()}: replan")
    return plan


# --- the snapshot ----------------------------------------------------------------------------

def snapshot(bridge) -> dict[int, dict]:
    """Every release function: name, thunk flag, body lowest and highest address, signature line.

    One ``list_functions_enhanced`` and one ``get_function_by_address`` per function (about 3 s
    for 9,493 functions); no cheaper read gives a signature or a body.
    """

    out = {}
    for address, fn in names.function_list(bridge, gb.RELEASE_PROGRAM).items():
        detail = names.read_function(bridge, gb.RELEASE_PROGRAM, address)
        if not detail or detail["entry"] != address:
            raise gb.BridgeError(f"function {hx(address)} is listed but does not read back")
        out[address] = {"name": detail["name"], "thunk": fn["thunk"], "lo": detail["body_min"],
                        "hi": detail["body_max"], "signature": detail.get("signature", "")}
    return out


def diff_states(expected: dict, now: dict) -> list[dict]:
    """Every difference between the state the run expects and the live one."""

    changes = []
    for address in sorted(set(expected) | set(now)):
        old, new = expected.get(address), now.get(address)
        if old is None:
            changes.append({"address": hx(address), "change": "appeared", "name": new["name"],
                            "body": f"{hx(new['lo'])}-{hx(new['hi'])}"})
        elif new is None:
            changes.append({"address": hx(address), "change": "vanished", "name": old["name"]})
        else:
            for key in ("name", "thunk", "lo", "hi", "signature"):
                if old[key] != new[key]:
                    show = hx if key in ("lo", "hi") else str
                    changes.append({"address": hx(address), "change": key, "expected": show(old[key]),
                                    "now": show(new[key])})
    return changes


# --- the apply -------------------------------------------------------------------------------

# What the coordinator does after each kind of stop (the report repeats it under what_to_do).
AFTER_NOTHING = ("nothing was sent for this function and every earlier write read back as planned: save, "
                 "--confirm-saved this report, then replan")
AFTER_A_WRITE = ("the program may hold another prototype there: save and --confirm-saved this report (it "
                 "records what the program really holds, marked as not the planned prototype, and lists it), "
                 "or close without saving and --discard-unsaved it; then replan")
AFTER_ANALYSIS = ("have the changes listed under analysis_changes checked: if they are acceptable, save and "
                  "--confirm-saved this report (it records this run's writes, not those changes); if not, close "
                  "without saving and --discard-unsaved it; then replan")


class StopBefore(Stop):
    """Stopped before a write to this function."""


class StopAfter(Stop):
    """Stopped after a write was sent: the function may hold something else than planned."""


class AnalysisStop(Stop):
    """The program changed beyond what the plan predicted."""


def compare(entry: dict, live: dict | None, params: list[dict]) -> list[str]:
    """Field-by-field differences between the planned prototype and the one read back."""

    out = []
    address = int(entry["address"], 16)
    if not live or live["entry"] != address:
        return [f"no function starts at {entry['address']} any more"]
    want = parse_signature(entry["expected"]["signature"], entry["release"]["name"])
    got = parse_signature(live.get("signature"), live["name"])
    if live["name"] != entry["release"]["name"]:
        out.append(f"name {live['name']!r}, expected {entry['release']['name']!r}")
    if got is None:
        return out + [f"signature {live.get('signature')!r} does not parse"]
    for key in ("return", "convention", "varargs", "noreturn"):
        if want[key] != got[key]:
            out.append(f"{key} {got[key]!r}, expected {want[key]!r}")
    wanted = entry["expected"]["parameters"]
    if len(params) != len(wanted):
        out.append(f"{len(params)} parameters, expected {len(wanted)}")
    for index, (p, w) in enumerate(zip(params, wanted), 1):
        for key in ("name", "type", "storage"):
            if p[key] != w[key]:
                out.append(f"parameter {index} {key} {p[key]!r}, expected {w[key]!r}")
    if not out and live.get("signature") != entry["expected"]["signature"]:
        out.append(f"signature {live.get('signature')!r}, expected {entry['expected']['signature']!r}")
    return out


class Applier:
    def __init__(self, bridge, plan: dict, dry_run: bool, classes=("exact",), batch=None,
                 check_every: int = CHECK_EVERY, recorded: dict | None = None):
        self.bridge, self.plan, self.dry_run = bridge, plan, dry_run
        self.recorded = recorded or {}  # the record's rows: a function saved as planned is not re-read in full
        self.classes, self.batch, self.check_every = tuple(classes), batch, max(1, check_every)
        self.written: list[dict] = []
        self.attempted: list[dict] = []
        self.would: list[dict] = []
        self.unchanged: Counter = Counter()
        self.skipped: Counter = Counter()
        self.analysis_changes: list[dict] = []
        self.side_effects: list[dict] = []
        self.checkpoints: list[dict] = []
        self.changed = 0
        self.batch_full = False
        self.window: list[str] = []  # entries written since the last clean snapshot
        self.clean = True

    def send(self, entry: dict, applied: str, value: str, before: str, endpoint: str, ok, **body) -> bool:
        """``before``: what the function held, so that --confirm-saved can tell what a stopped write left."""

        item = {"address": entry["address"], "applied": applied, "value": value, "before": before,
                "source_pair": entry["source_pair"], "end": entry["end"]}
        if self.dry_run:
            self.would.append(item)
            return False
        self.attempted.append(item)
        self.clean = False
        try:
            response = self.bridge.write(endpoint, gb.RELEASE_PROGRAM, **body)
        except gb.BridgeError as exc:
            raise StopAfter(f"{endpoint} at {entry['address']}: {exc}: {AFTER_A_WRITE}") from exc
        if not ok(response):
            raise StopAfter(f"{endpoint} at {entry['address']} failed: {response!r}"
                            + (" (the signature is committed before the convention, so it may be there)"
                               if endpoint == "set_function_prototype" else "") + f": {AFTER_A_WRITE}")
        return True

    def checkpoint(self, why: str) -> None:
        names.settle(self.bridge)
        now = snapshot(self.bridge)
        changes = diff_states(self.expected, now)
        self.checkpoints.append({"after": why, "functions": len(now), "changes": len(changes)})
        if changes:
            self.analysis_changes = [dict(c, window=list(self.window)) for c in changes]
            self.expected = now
            self.order = sorted(now)
            raise AnalysisStop(
                f"the program changed beyond the plan ({len(changes)} changes, listed in the report under "
                f"analysis_changes) after writing {', '.join(self.window) or 'nothing'} ({why}): {AFTER_ANALYSIS}")
        self.window = []
        self.clean = True

    def run(self) -> None:
        self.before = snapshot(self.bridge)
        self.expected = copy.deepcopy(self.before)
        self.order = sorted(self.expected)
        ordered = sorted((e for e in self.plan["entries"] if e["action"] in ("write", "unchanged")),
                         key=lambda e: int(e["address"], 16))
        try:
            for entry in ordered:
                if entry["group"] not in self.classes:
                    self.skipped[f"group {entry['group']} not taken"] += 1
                    continue
                if self.batch and self.changed >= self.batch:
                    self.batch_full = True
                    break
                if self.entry(entry):
                    self.changed += 1
                    if self.window and len(self.window) >= self.check_every:
                        self.checkpoint(f"{self.changed} functions")
            if not self.dry_run and not self.clean:
                self.checkpoint("the end of the run")
        finally:
            if not self.dry_run and not self.clean:
                try:  # a stop between snapshots: report what else changed, without stopping again
                    names.settle(self.bridge)
                    self.side_effects = diff_states(self.expected, snapshot(self.bridge))
                except (Stop, gb.BridgeError) as exc:
                    self.side_effects = [{"change": "no final snapshot", "detail": str(exc)}]

    def saved_as_planned(self, entry: dict) -> bool:
        """The record holds this entry's prototype (and plate flag) as planned, saved."""

        def saved(applied, value):
            row = self.recorded.get((entry["address"], applied))
            return bool(row) and row["value"] == names.record_value(value) and row["state"].startswith("saved ") \
                and "not the planned" not in row["state"]

        value = recorded_prototype(entry)
        return saved("prototype", value) and (not entry.get("plate") or saved("plate", entry["plate"]["after"]))

    def thunk_now(self, address: int) -> bool:
        """The live thunk flag of this function alone (``list_functions_enhanced`` at its index).

        The plugin skips the functions before ``offset`` without classifying them, so one row is
        cheap. A function at another index means the function list changed: the snapshot says how.
        """

        index = bisect.bisect_left(self.order, address)
        value = self.bridge.get("list_functions_enhanced", gb.RELEASE_PROGRAM, offset=index, limit=1)
        rows = value.get("functions") if isinstance(value, dict) else None
        if not rows or int(rows[0]["address"], 16) != address:
            if not self.dry_run:
                self.checkpoint(f"the function list moved before {hx(address)}")
            raise StopBefore(f"{hx(address)} is not where the function list had it: {AFTER_NOTHING}")
        return bool(rows[0].get("isThunk"))

    def entry(self, entry: dict) -> bool:
        address = int(entry["address"], 16)
        state = self.expected.get(address)
        live = names.read_function(self.bridge, gb.RELEASE_PROGRAM, address)
        if not live or live["entry"] != address or state is None:
            raise StopBefore(f"{entry['address']}: the planned function is gone: {AFTER_NOTHING}")
        if (live["body_min"], live["body_max"], live["name"]) != (address, int(entry["end"], 16), entry["release"]["name"]):
            raise StopBefore(f"{entry['address']} is now {live['name']} {hx(live['body_min'])}..{hx(live['body_max'])}: "
                             f"{AFTER_NOTHING}")
        if live.get("signature") == entry["expected"]["signature"] and self.saved_as_planned(entry):
            # an earlier batch wrote and saved it: the signature line is checked, the full read-back
            # (storage, ~0.25 s) was made then and is in the record; the snapshots still cover it
            self.unchanged["prototype (saved)"] += 1
            return False
        if self.thunk_now(address):
            raise StopBefore(f"{entry['address']} is a thunk now (a write would go to its target): {AFTER_NOTHING}")
        expected = entry["expected"]["signature"]
        if live.get("signature") == expected:
            params = read_variables(self.bridge, gb.RELEASE_PROGRAM, address)
            if params != entry["expected"]["parameters"]:
                raise StopBefore(f"{entry['address']} has the planned signature with another storage: {AFTER_NOTHING}")
            self.unchanged["prototype"] += 1
            return self.plate(entry)
        if entry["action"] != "write" or live.get("signature") != entry["release"]["signature"]:
            raise StopBefore(f"{entry['address']} now has the signature {live.get('signature')!r}, the plan saw "
                             f"{entry['release']['signature']!r}: {AFTER_NOTHING}")
        if entry.get("plate"):
            current = names.read_plate(self.bridge, address)
            if current not in (entry["plate"]["before"], entry["plate"]["after"]):
                raise StopBefore(f"{entry['address']}: its plate comment changed since the plan: {AFTER_NOTHING}")
        before = live_value(self.bridge, {"address": entry["address"], "applied": "prototype"}, live)
        value = recorded_prototype(entry)
        body = {"function_address": entry["address"], "prototype": entry["send"]["prototype"]}
        if entry["send"]["calling_convention"]:
            body["calling_convention"] = entry["send"]["calling_convention"]
        if self.send(entry, "prototype", value, before, "set_function_prototype",
                     lambda r: isinstance(r, str) and r.startswith("Successfully set prototype"), **body):
            self.window.append(entry["address"])
            back = names.read_function(self.bridge, gb.RELEASE_PROGRAM, address)
            params = read_variables(self.bridge, gb.RELEASE_PROGRAM, address) if back and back["entry"] == address else []
            wrong = compare(entry, back, params)
            if wrong:
                raise StopAfter(f"prototype {entry['address']} read back wrong: {'; '.join(wrong)}: {AFTER_A_WRITE}")
            self.written.append({"address": entry["address"], "applied": "prototype", "value": value, "before": before,
                                 "source_pair": entry["source_pair"], "end": entry["end"]})
            self.expected[address] = dict(self.expected[address], signature=back["signature"])
            for thunk in entry["thunks"]:
                t = int(thunk["address"], 16)
                seen = names.read_function(self.bridge, gb.RELEASE_PROGRAM, t)
                if not seen or seen["entry"] != t or seen.get("signature") != thunk["signature_after"]:
                    raise AnalysisStop(f"the thunk {thunk['address']} of {entry['address']} shows "
                                       f"{seen and seen.get('signature')!r}, predicted {thunk['signature_after']!r} "
                                       f"(the write itself read back as planned): {AFTER_ANALYSIS}")
                self.expected[t] = dict(self.expected[t], signature=thunk["signature_after"])
        self.plate(entry)
        if not self.dry_run:
            status = self.bridge.get("analysis_status", gb.RELEASE_PROGRAM)
            if not (isinstance(status, dict) and status.get("analyzing") is False):
                self.checkpoint(f"analysis seen running after {entry['address']}")
        return True

    def plate(self, entry: dict) -> bool:
        if not entry.get("plate"):
            return False
        address = int(entry["address"], 16)
        current = names.read_plate(self.bridge, address)
        after = entry["plate"]["after"]
        if current == after:
            self.unchanged["plate"] += 1
            return False
        if current != entry["plate"]["before"]:
            raise StopBefore(f"{entry['address']}: its plate comment changed since the plan: {AFTER_NOTHING}")
        if self.send(entry, "plate", after, current, "set_comment", gb.ok_status,
                     address=entry["address"], comment=after, type="plate"):
            self.window.append(entry["address"] + " (plate)")
            if names.read_plate(self.bridge, address) != after:
                raise StopAfter(f"plate {entry['address']} did not read back: {AFTER_A_WRITE}")
            self.written.append({"address": entry["address"], "applied": "plate", "value": after, "before": current,
                                 "source_pair": entry["source_pair"], "end": entry["end"]})
        return True


# --- the record ------------------------------------------------------------------------------

def live_value(bridge, item: dict, live: dict | None = None) -> str | None:
    """What the release function holds now, in the record's terms (None: no function starts there)."""

    address = int(item["address"], 16)
    if item["applied"] == "plate":
        return names.read_plate(bridge, address)
    live = live or names.read_function(bridge, gb.RELEASE_PROGRAM, address)
    if not live or live["entry"] != address:
        return None
    here = parse_signature(live.get("signature"), live["name"])
    params = read_variables(bridge, gb.RELEASE_PROGRAM, address) if here is None or here["inside"] else []
    return prototype_value(live.get("signature", ""), params)


def reads_back(bridge, item: dict) -> bool:
    if item["applied"] not in ("prototype", "plate"):
        return names.reads_back(bridge, item)
    return holds(live_value(bridge, item), item["value"])


def stopped_writes(bridge, result: dict) -> tuple[list, list, list]:
    """The writes a stop left behind: (as planned, something else, nothing), read from the program.

    A write that was sent but is not in ``written`` holds the planned value, another value (the
    convention transaction failed, or the read-back found a mismatch), or what it held before.
    """

    written = {(w["address"], w["applied"]) for w in result["written"]}
    planned, other, untouched = [], [], []
    for item in result.get("attempted", []):
        if (item["address"], item["applied"]) in written:
            continue
        now = live_value(bridge, item)
        if holds(now, item["value"]):
            planned.append(item)
        elif now != item.get("before"):
            other.append(dict(item, value=now if now is not None else "(no function starts here)",
                              planned=item["value"]))
        else:
            untouched.append(item)
    return planned, other, untouched


def not_planned_state(day: str, item: dict, report_name: str) -> str:
    return f"saved {day}, not the planned {item['applied']} ({report_name})"


def next_report(root: Path, stem: str) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    used = [int(m.group(1)) for p in out.glob(f"{stem}.apply-*.json")
            if (m := re.search(r"\.apply-(\d+)\.json$", p.name))]
    return out / f"{stem}.apply-{max(used, default=0) + 1:03d}.json"


def apply(root: Path, plan_path: Path, bridge, *, dry_run: bool, classes=("exact",), batch: int | None = None,
          check_every: int = CHECK_EVERY, today: str | None = None) -> dict:
    plan = load_plan(plan_path, root)
    unknown = [c for c in classes if c not in GROUPS]
    if unknown or "exact" not in classes:
        raise Refused(f"--classes takes exact, plus deviating and/or mangled, not {','.join(classes)}")
    if not dry_run:
        pending = names.unsaved(names.read_record(root))
        if pending:
            reports = sorted({row["state"].split(" ", 1)[1] for row in pending})
            raise Refused(f"{names.RECORD.as_posix()} holds {len(pending)} unsaved changes ({', '.join(reports)}): "
                          "save and --confirm-saved (or --discard-unsaved) first")
    check = names.preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    out = (root / OUT / f"{plan_path.stem}.dry-run.json") if dry_run else next_report(root, plan_path.stem)
    record_before = names.read_record(root)
    applier = Applier(bridge, plan, dry_run, classes, batch, check_every, recorded=record_before)
    stopped, stop_kind = None, None
    replaced: list[dict] = []
    try:
        applier.run()
    except (Stop, gb.BridgeError) as exc:
        stopped, stop_kind = str(exc), type(exc).__name__
    finally:
        # Rows of the names step (plates) that this run's rows replace now or at --confirm-saved;
        # --discard-unsaved puts them back.
        replaced = [record_before[k] for k in sorted({(w["address"], w["applied"]) for w in applier.attempted})
                    if k in record_before]
        if not dry_run and applier.written:
            names.update_record(root, applier.written, today or _dt.date.today().isoformat(), out.name)
    what_to_do = {"StopBefore": AFTER_NOTHING, "StopAfter": AFTER_A_WRITE, "AnalysisStop": AFTER_ANALYSIS}.get(
        stop_kind, AFTER_A_WRITE if stopped else None)
    done = applier.would if dry_run else applier.written
    result = {
        "plan": plan_path.name, "plan_sha256": plan["plan_sha256"], "selection": plan["selection"],
        "dry_run": dry_run, "classes": list(classes), "stopped": stopped, "stop_kind": stop_kind,
        "what_to_do": what_to_do, "saved": False, "batch": batch,
        "batch_full": applier.batch_full, "entries_changed": applier.changed, "check_every": applier.check_every,
        "sent": [] if dry_run else bridge.sent, "written": applier.written, "would_write": applier.would,
        "counts": dict(sorted(Counter(w["applied"] for w in done).items())),
        "unchanged": dict(sorted(applier.unchanged.items())), "skipped": dict(sorted(applier.skipped.items())),
        "checkpoints": applier.checkpoints, "analysis_changes": applier.analysis_changes,
        "side_effects": applier.side_effects, "attempted": [] if dry_run else applier.attempted,
        "remove_by_hand": [], "replaced_rows": [] if dry_run else replaced,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical(result), encoding="utf-8", newline="\n")
    result["report"] = out.name
    return result


def confirm_saved(root: Path, report_path: Path, bridge, today: str | None = None) -> dict:
    """After the coordinator saved: re-read the report's writes and make the record say what is there.

    Rows that read back are marked saved. A write the run sent without recording it (a stop) is
    recorded as it reads now: saved as planned, or, when the function holds something else than
    before the run and than planned, with a state that says it is not the planned one.
    """

    result = json.loads(report_path.read_text(encoding="utf-8"))
    rows = names.read_record(root)
    mine = [k for k, row in rows.items() if row["state"] == f"unsaved {report_path.name}"]
    failed = [f"{w['address']} {w['applied']}" for w in result["written"] if not reads_back(bridge, w)]
    if failed:
        raise Refused(f"{len(failed)} changes do not read back ({', '.join(failed[:10])}); nothing marked saved")
    planned, other, untouched = stopped_writes(bridge, result)
    if not mine and not planned and not other:
        raise Refused(f"the record holds no unsaved rows of {report_path.name} and its stopped writes left nothing")
    day = today or _dt.date.today().isoformat()
    for key in mine:
        rows[key]["state"] = f"saved {day}"
    for item in planned:
        rows[(item["address"], item["applied"])] = {
            "release_address": item["address"], "applied": item["applied"], "value": names.record_value(item["value"]),
            "source_pair": item["source_pair"], "date": day, "state": f"saved {day}"}
    for item in other:
        rows[(item["address"], item["applied"])] = {
            "release_address": item["address"], "applied": item["applied"], "value": names.record_value(item["value"]),
            "source_pair": item["source_pair"], "date": day, "state": not_planned_state(day, item, report_path.name)}
    names.write_record(root, rows)
    return {"confirmed": len(mine), "recorded_after_a_stop": len(planned),
            "not_as_planned": [{"address": i["address"], "applied": i["applied"], "holds": i["value"],
                                "planned": i["planned"]} for i in other],
            "sent_but_not_there": [f"{i['address']} {i['applied']}" for i in untouched], "report": report_path.name}


def discard_unsaved(root: Path, report_path: Path, bridge) -> dict:
    """After a close without saving: drop the report's rows and restore those they replaced.

    Refused while the program still holds any write of the report, recorded or not.
    """

    result = json.loads(report_path.read_text(encoding="utf-8"))
    present = [f"{w['address']} {w['applied']}" for w in result["written"] if reads_back(bridge, w)]
    planned, other, _ = stopped_writes(bridge, result)
    present += [f"{i['address']} {i['applied']}" for i in planned + other]
    if present:
        raise Refused(f"{len(present)} changes of {report_path.name} are still in the program "
                      f"({', '.join(present[:10])}): save and --confirm-saved instead")
    rows = names.read_record(root)
    kept = {k: r for k, r in rows.items() if r["state"] != f"unsaved {report_path.name}"}
    for row in result.get("replaced_rows", []):
        kept.setdefault((row["release_address"], row["applied"]), row)
    names.write_record(root, kept)
    return {"discarded": sum(1 for r in rows.values() if r["state"] == f"unsaved {report_path.name}"),
            "restored": len(result.get("replaced_rows", [])), "report": report_path.name}


# --- command line ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", nargs="?", const="", metavar="MODULE",
                      help="plan one module of the map (e.g. gamez/zArchive), or every pair with --all")
    mode.add_argument("--apply", type=Path, metavar="PLAN")
    mode.add_argument("--confirm-saved", type=Path, metavar="REPORT")
    mode.add_argument("--discard-unsaved", type=Path, metavar="REPORT")
    parser.add_argument("--all", action="store_true", help="with --plan: every pair")
    parser.add_argument("--dry-run", action="store_true", help="with --apply: reads and checks only")
    parser.add_argument("--yes", action="store_true", help="with --apply: really write")
    parser.add_argument("--classes", default="exact", help="with --apply: exact (default), plus deviating and/or mangled (exact,deviating,mangled)")
    parser.add_argument("--batch", type=int, metavar="N", help="with --apply: stop after N changed functions")
    parser.add_argument("--check-every", type=int, default=CHECK_EVERY, metavar="N",
                        help=f"with --apply: full snapshot after every N written functions (default {CHECK_EVERY})")
    parser.add_argument("--url", help="bridge URL (default SOCOM_GHIDRA_URL or http://127.0.0.1:8089)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.plan is not None:
            if bool(args.plan) == args.all:
                parser.error("--plan takes either a module or --all")
            plan = build_plan(root, gb.Bridge(args.url, read_only=True), args.plan or None,
                              progress=lambda m: print(m, file=sys.stderr))
            path = write_plan(root, plan)
            print(json.dumps(plan["summary"], indent=1))
            print(f"wrote {path.relative_to(root).as_posix()} (plan sha256 {plan['plan_sha256']})")
            return 0
        if args.all:
            parser.error("--all goes with --plan")
        if args.confirm_saved or args.discard_unsaved:
            bridge = gb.Bridge(args.url, read_only=True)
            check = names.preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            done = (confirm_saved(root, args.confirm_saved.resolve(), bridge) if args.confirm_saved
                    else discard_unsaved(root, args.discard_unsaved.resolve(), bridge))
            print(json.dumps(done, indent=1))
            for item in done.get("not_as_planned", []):
                print(f"NOT AS PLANNED, recorded as it is: {item['address']} {item['applied']} holds {item['holds']!r}, "
                      f"planned {item['planned']!r}")
            return 0
        if not args.dry_run and not args.yes:
            print("refused: --apply writes to the release program; pass --yes (or --dry-run)", file=sys.stderr)
            return 2
        if args.dry_run and args.yes:
            parser.error("--dry-run and --yes exclude each other")
        bridge = gb.Bridge(args.url, read_only=args.dry_run, writes=gb.SIGNATURE_WRITES)
        classes = tuple(c.strip() for c in args.classes.split(",") if c.strip())
        result = apply(root, args.apply.resolve(), bridge, dry_run=args.dry_run, classes=classes,
                       batch=args.batch, check_every=args.check_every)
        print(json.dumps({k: result[k] for k in ("report", "dry_run", "classes", "stopped", "stop_kind", "what_to_do",
                                                 "counts", "unchanged", "skipped", "saved", "batch_full",
                                                 "entries_changed")}, indent=1))
        print(f"sent: {len(result['sent'])}; snapshots: {len(result['checkpoints'])}; analysis changes: "
              f"{len(result['analysis_changes'])}; side effects: {len(result['side_effects'])}")
        if result["batch_full"]:
            print("batch complete: save through the bridge, then --confirm-saved the report, then rerun")
        return 1 if result["stopped"] or result["side_effects"] else 0
    except (Refused, gb.BridgeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
