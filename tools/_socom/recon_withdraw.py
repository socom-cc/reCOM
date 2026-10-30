"""Candidate rows for withdrawing an unproven live return (read-only).

Decisions of 2026-10-29 let a recon repair row withdraw (``withdraws_return``)
two more kinds of applied return:

* ``void``: an applied void row whose ``recon void`` verdict is open, unless
  the function's own DWARF record declares FT_void, the drafter's
  ``__sinit_`` rule proves it, or the row cites a DWARF ``subroutine_type``
  (a callback member type) that declares FT_void;
* ``header``: an applied row whose return is a type (any width, ``int`` and
  pointers included) and whose evidence cites a recalled SDK or C-library
  header declaration; a planner re-proves the return from asm and callers
  and withdraws it where nothing else proves it.

``withdrawal_candidates`` reads the tracker, the accepted plans and the ELF
only: the row each function shows is the newest recon repair whose plan and
apply are accepted, else its group's row (plan and apply accepted).  It reads
no live signature; ``recon live --item`` gives the ``live_signature`` a
repair row records.  Nothing is written to Ghidra or the tracker.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .util import SocomError, load_json

# Headers a recalled declaration came from (Sony EE libraries and the C library
# with newlib internals); Ghidra type-archive paths such as /stdio.h/FILE are
# categories, not citations, and are not matched.
SDK_HEADERS = (
    "deci2", "eekernel", "libcdvd", "libdma", "libgraph", "libipu", "libmc", "libmpeg", "libpad", "libpc", "libpkt",
    "libvu0", "sifcmd", "sifdev", "sifrpc",
)
C_LIBRARY_HEADERS = (
    "assert", "ctype", "errno", "locale", "math", "mprec", "setjmp", "signal", "stdio", "stdlib", "string", "strings",
    "time", "unistd",
)
_HEADER = re.compile(r"(?<![/\w.])(" + "|".join(SDK_HEADERS + C_LIBRARY_HEADERS) + r")\.h(?![/\w])")
# Provider wording of rows that name a library but no header (not candidates).
_PROVIDER = re.compile(r"\(provider\b|\bnewlib\b|\bfdlibm\b|\blibgcc\b|\bSony\b|\bps2sdk\b")
_SUBROUTINE_TYPE = re.compile(r"\bsubroutine_type (0x[0-9a-fA-F]+)")
KINDS = ("void", "header")
UNDEFINED = re.compile(r"^undefined\d*$")


def _texts(value: Any) -> list[str]:
    """Every string inside a row (evidence, contradictions, notes, parameter evidence)."""

    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _texts(item)]
    if isinstance(value, list):
        return [text for item in value for text in _texts(item)]
    return []


def applied_rows(root: Path, tracker: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Address -> the row its accepted applies left live, with where it comes from.

    The newest recon repair whose plan and apply are accepted supersedes its
    group's row; ``pending_repairs`` lists repairs of the function that are
    not finished (``progress add-recon-repair`` refuses those functions).
    """

    from .recon import REPAIR_PLAN_KIND, plan_path_for

    items = {row["id"]: row for row in tracker["work_items"]}

    def accepted(item: dict[str, Any]) -> bool:
        return item.get("status") == "accepted" and (items.get(f"{item['id']}-apply") or {}).get("status") == "accepted"

    def plan_rows(item: dict[str, Any]) -> dict[int, dict[str, Any]]:
        path = plan_path_for(root, item["id"])
        if not path.is_file():
            raise SocomError(f"{item['id']} is accepted but its plan {path.relative_to(root).as_posix()} is missing")
        return {int(str(row["address"]), 16): row for row in load_json(path).get("functions", [])}

    found: dict[int, dict[str, Any]] = {}
    for item in tracker["work_items"]:
        if item.get("kind") != "recon-plan-group" or not accepted(item):
            continue
        for address, row in plan_rows(item).items():
            found[address] = {
                "row": row, "source": item["id"], "group": item["id"],
                "group_number": item["batch"].get("group_number"), "pending_repairs": [],
            }
    repairs = sorted(
        (item for item in tracker["work_items"] if item.get("kind") == REPAIR_PLAN_KIND),
        key=lambda item: (item["batch"].get("repair_number") or 0, item["id"]),
    )
    for item in repairs:
        if not accepted(item):
            for value in item["batch"]["functions"]:
                if int(value, 16) in found:
                    found[int(value, 16)]["pending_repairs"].append(item["id"])
            continue
        for address, row in plan_rows(item).items():
            # A keep row leaves the function as the earlier row applied it.
            if address in found and row.get("keep") is not True:
                found[address].update(row=row, source=item["id"])
    return found


def _cited_void_types(ctx: Any, texts: list[str]) -> list[str]:
    """DWARF subroutine_type DIEs the row cites that declare an explicit void result (FT_void)."""

    from .recon_facts import _dies_cached

    wanted = {int(value, 16) for text in texts for value in _SUBROUTINE_TYPE.findall(text)}
    if not wanted:
        return []
    path = Path(ctx.elf.path)
    st = path.stat()
    dies = {die.offset: die for die in _dies_cached((str(path), st.st_size, int(st.st_mtime)), str(path))}
    return [
        f"0x{offset:x}" for offset in sorted(wanted)
        if offset in dies and dies[offset].tag_name == "subroutine_type" and dies[offset].integer("fund_type") == 0x14
    ]


def _base(row: dict[str, Any], info: dict[str, Any], address: int) -> dict[str, Any]:
    prototype = row["prototype"]
    rename = row.get("rename")
    return {
        "address": f"0x{address:x}",
        "name": rename["name"] if isinstance(rename, dict) and rename.get("name") else row.get("current_name"),
        "source": info["source"],
        "group": info["group"],
        "group_number": info["group_number"],
        "draft_rule": row.get("draft_rule"),
        "return_type": prototype.get("return_type"),
        "parameters": [{"name": p.get("name"), "type": p.get("type")} for p in prototype.get("parameters") or []],
        "varargs": prototype.get("varargs") is True,
        "pending_repairs": info["pending_repairs"],
    }


def withdrawal_candidates(
    root: Path, tracker: dict[str, Any], *, kinds: tuple[str, ...] = KINDS, rules: int | None = None
) -> dict[str, Any]:
    """Applied rows a ``withdraws_return`` repair may take, with the evidence each one rests on."""

    from .recon_draft import DRAFT_RULES_VERSION, RULES_VERSIONS, _dwarf_returns, _dwarf_void, sinit_rule_void, verdict_line, verdict_proves_void, void_verdict
    from .recon_facts import context

    rules = DRAFT_RULES_VERSION if rules is None else rules
    if rules not in RULES_VERSIONS:
        raise SocomError(f"void rules version {rules} is not one of {', '.join(map(str, RULES_VERSIONS))}")
    unknown = [kind for kind in kinds if kind not in KINDS]
    if unknown:
        raise SocomError(f"unknown candidate kind {unknown[0]!r}: one of {', '.join(KINDS)}")
    ctx = context(root)
    rows = applied_rows(root, tracker)
    result: dict[str, Any] = {
        "kind": "socom-recon-withdrawal-candidates",
        "mutation_performed": False,
        "revision": tracker.get("revision"),
        "rules_version": rules,
        "applied_rows": len(rows),
        "live_signatures": "not read: recon live --item gives each repair row's live_signature",
    }
    if "void" in kinds:
        counts = {"applied_void_rows": 0, "recon_void": 0, "dwarf_void": 0, "sinit_rule": 0, "dwarf_void_type_cited": 0}
        excluded_cited = []
        found = []
        dwarf_void = _dwarf_void(ctx)
        for address in sorted(rows):
            info = rows[address]
            row = info["row"]
            prototype = row.get("prototype") or {}
            if prototype.get("return_type") != "void" or prototype.get("partial") is True:
                continue
            counts["applied_void_rows"] += 1
            if address in dwarf_void:
                counts["dwarf_void"] += 1
                continue
            line = verdict_line(void_verdict(ctx, address, rules))
            if verdict_proves_void(line):
                counts["recon_void"] += 1
                continue
            if sinit_rule_void(ctx, address, rules):
                counts["sinit_rule"] += 1
                continue
            texts = _texts(row)
            cited = _cited_void_types(ctx, texts)
            if cited:
                counts["dwarf_void_type_cited"] += 1
                excluded_cited.append({"address": f"0x{address:x}", "name": row.get("current_name"), "subroutine_types": cited})
                continue
            found.append({
                **_base(row, info, address),
                "verdict": line,
                "evidence": [str(text) for text in prototype.get("evidence") or []],
            })
        result["void"] = {
            **counts,
            "candidate_count": len(found),
            "rule": (
                "applied void rows whose recon void verdict is open; excluded: the function's own DWARF FT_void "
                "record, the drafter's __sinit_ rule, and rows citing a DWARF subroutine_type that declares FT_void"
            ),
            "excluded_cited_void_types": excluded_cited,
            "candidates": found,
        }
    if "header" in kinds:
        counts = {"applied_typed_rows": 0, "citing_rows": 0, "dwarf_declared": 0, "partial_rows_citing": 0}
        found = []
        uncited = []
        declared = _dwarf_returns(ctx)
        for address in sorted(rows):
            info = rows[address]
            row = info["row"]
            prototype = row.get("prototype") or {}
            returned = str(prototype.get("return_type") or "")
            texts = _texts(row)
            citing = [text for text in texts if _HEADER.search(text)]
            if prototype.get("partial") is True:
                counts["partial_rows_citing"] += bool(citing)
                continue
            if not prototype or returned == "void" or UNDEFINED.match(returned.replace("*", "").strip()):
                continue
            counts["applied_typed_rows"] += 1
            if not citing:
                named = next((text for text in texts if _PROVIDER.search(text)), None)
                if named is not None and address not in declared:
                    # Listed for information: a provider row whose declaration
                    # is recalled without naming a header.
                    uncited.append({
                        "address": f"0x{address:x}", "name": row.get("current_name"),
                        "return_type": returned, "source": info["source"], "names": named,
                    })
                continue
            counts["citing_rows"] += 1
            if address in declared:
                counts["dwarf_declared"] += 1
                continue
            headers = sorted({name for text in citing for name in _HEADER.findall(text)})
            libraries = sorted({"sdk" if name in SDK_HEADERS else "c-library" for name in headers})
            found.append({
                **_base(row, info, address),
                "headers": [f"{name}.h" for name in headers],
                "library": "+".join(libraries),
                "citing": citing,
                "other_evidence": [text for text in _texts(prototype.get("evidence")) if text not in citing],
            })
        by_library: dict[str, int] = {}
        for row in found:
            by_library[row["library"]] = by_library.get(row["library"], 0) + 1
        result["header"] = {
            **counts,
            "candidate_count": len(found),
            "by_library": dict(sorted(by_library.items())),
            "rule": (
                "applied rows whose return is a type (not void, not undefined*, not partial) and whose row cites a "
                "recalled SDK or C-library header declaration; excluded: a return the function's own DWARF record "
                "declares"
            ),
            "sdk_headers": [f"{name}.h" for name in SDK_HEADERS],
            "c_library_headers": [f"{name}.h" for name in C_LIBRARY_HEADERS],
            "candidates": found,
            "provider_rows_without_header_count": len(uncited),
            "provider_rows_without_header": uncited,
        }
    return result
