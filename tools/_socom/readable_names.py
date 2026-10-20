"""Readable names for functions whose mangled names were never renamed.

Stage 2 gave DWARF functions readable qualified names.  The other functions
with Metrowerks mangled names still carry them (SetPosition__Q23zdb5CNodeFfff).
This builds a deterministic batch program, from the ELF alone, that renames
each to the same readable form stage 2 uses (zdb::CNode::SetPosition) and keeps
the mangled name as a label:

* a function with a demangled mangled name gets ``readable_function_name``;
* a mangled name that labels several addresses (file-local copies, one per
  compile unit) has no canonical copy and is left alone;
* overloads share their readable name (``shared_names``); each keeps its own
  mangled label, and the signatures tell them apart;
* a function already showing its readable name is recorded as unchanged;
* a thunk (whole body ``j target; nop``) is left alone: Ghidra derives a
  thunk's identity from its target.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from .batch_apply import BATCH_PROGRAM_KIND, BATCH_PROGRAM_SCHEMA, _thunk_target, readable_function_name
from .constants import REFERENCE_SHA256
from .elf import Elf32File
from .mwdemangle import demangle
from .util import canonical_json

READABLE_NAMES_REPAIR_ID = "socom:work:ghidra-repair-readable-function-names"


def readable_names_program(root: Path) -> dict[str, Any]:
    elf = Elf32File(root / "support" / "socom.elf")
    names_at: dict[int, set[str]] = defaultdict(set)
    addresses_of: dict[str, set[int]] = defaultdict(set)
    for symbol in elf.symbols():
        if symbol.type_name == "FUNC" and symbol.size and symbol.name:
            names_at[symbol.value].add(symbol.name)
            addresses_of[symbol.name].add(symbol.value)
    sizes = {symbol.value: symbol.size for symbol in elf.symbols() if symbol.type_name == "FUNC" and symbol.size}
    functions = []
    copies = []
    thunks = []
    for address in sorted(names_at):
        mangled = sorted(name for name in names_at[address] if demangle(name))
        if not mangled:
            continue
        current = mangled[0]
        if len(addresses_of[current]) > 1:
            copies.append(f"0x{address:x}")
            continue
        if _thunk_target(elf, address, sizes.get(address)) is not None:
            thunks.append(f"0x{address:x}")
            continue
        readable = readable_function_name(current, None)
        if not readable or readable == current:
            continue
        functions.append(
            {
                "address": f"0x{address:x}",
                "current_name": current,
                "readable_name": readable,
                "rename": True,
                "prototype": None,
                "prototype_skip": None,
                "notes": [],
            }
        )
    shared: dict[str, int] = defaultdict(int)
    for row in functions:
        shared[row["readable_name"]] += 1
    scope = sorted({row["address"] for row in functions}, key=lambda value: (value.casefold(), value))
    body = {
        "kind": BATCH_PROGRAM_KIND,
        "schema_version": BATCH_PROGRAM_SCHEMA,
        "mutation_performed": False,
        "source_sha256": REFERENCE_SHA256,
        "work_item_id": READABLE_NAMES_REPAIR_ID,
        "shared_names": True,
        "functions": functions,
        "globals": [],
        "absent_variables": [],
        "receipt_scope": {"schema_version": 1, "functions": scope, "types": [], "globals": []},
        "summary": {
            "function_count": len(functions),
            "shared_name_count": sum(1 for count in shared.values() if count > 1),
            "file_local_copies_skipped": copies,
            "thunks_skipped": thunks,
        },
    }
    body["program_sha256"] = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
    return body
