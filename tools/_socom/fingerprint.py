"""Read-only full-program fingerprint of live socom.elf, with before/after diffs.

Semantic receipts bind the function, data and type indexes plus scoped facts;
they do not bind every function's signature or any reference outside a scope,
so an apply could change those unseen (batch 001's thunk prototypes rewrote
two CGame signatures). A fingerprint records every function's name, thunk
flag and `get_function_by_address` details, every defined data item, every
type, bookmarks, all memory blocks (overlays included), and every reference
into any block, each with its own digest. It is evidence alongside the
receipt and does not change receipt hashes.

Only GET endpoints and the read-only POST get_bulk_xrefs are used. The bridge
serializes requests, so the reference sweep is a single stream; about 16,000
addresses per call measured fastest sustained (~600k addresses/s; larger calls
slow down).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .ghidra import (
    GhidraBridge,
    _bookmark_profile,
    _data_index,
    _digest,
    _type_index,
    live_preflight,
)
from .util import SocomError

FINGERPRINT_KIND = "socom-ghidra-fingerprint"
FINGERPRINT_SCHEMA = 1
SWEEP_CHUNK = 16_000
_SEGMENT = re.compile(r"^(?P<name>.+?):\s+(?:(?P<space>[^:\s]+)::)?(?P<start>[0-9a-fA-F]+)\s+-\s+(?:[^:\s]+::)?(?P<end>[0-9a-fA-F]+)\s*$")
_DETAIL = ("Function:", "Signature:", "Entry:", "Body:")


def _segments(bridge: GhidraBridge) -> list[dict[str, Any]]:
    text = bridge.request("list_segments", offset=0, limit=10_000)
    rows = []
    for line in str(text).splitlines():
        match = _SEGMENT.match(line.strip())
        if match:
            rows.append(
                {
                    "name": match["name"],
                    "space": match["space"],
                    "start": int(match["start"], 16),
                    "end": int(match["end"], 16) + 1,
                }
            )
    if not rows:
        raise SocomError("list_segments returned no blocks")
    return rows


def _references(bridge: GhidraBridge, blocks: list[dict[str, Any]], log: Callable[[str], None]) -> list[list[str]]:
    rows: list[list[str]] = []
    for block in blocks:
        for first in range(block["start"], block["end"], SWEEP_CHUNK):
            last = min(first + SWEEP_CHUNK, block["end"])
            prefix = f"{block['space']}::" if block["space"] else "0x"
            requested = [f"{prefix}{address:x}" for address in range(first, last)]
            response = bridge.post_json("get_bulk_xrefs", addresses=",".join(requested))
            if not isinstance(response, dict) or len(response) != len(requested):
                raise SocomError(f"get_bulk_xrefs did not answer every address of {block['name']} at {first:x}")
            for target, references in response.items():
                for reference in references or []:
                    rows.append([str(reference.get("from")), target, str(reference.get("type"))])
        log(f"  references through {block['name']}: {len(rows)}")
    return sorted(rows)


def _functions(bridge: GhidraBridge, log: Callable[[str], None]) -> list[dict[str, Any]]:
    listing = bridge.request("list_functions_enhanced", offset=0, limit=1_000_000)
    if not isinstance(listing, dict) or not isinstance(listing.get("functions"), list):
        raise SocomError("list_functions_enhanced returned no function list")
    rows = []
    for function in listing["functions"]:
        row = {
            "address": function["address"],
            "name": function["name"],
            "thunk": bool(function.get("isThunk")),
            "external": bool(function.get("isExternal")),
        }
        if not row["external"]:
            text = bridge.request("get_function_by_address", address=f"0x{int(function['address'], 16):x}")
            row["details"] = [line for line in str(text).splitlines() if line.startswith(_DETAIL)]
        rows.append(row)
    log(f"  functions: {len(rows)}")
    return sorted(rows, key=lambda row: row["address"])


def program_fingerprint(
    root: Path,
    *,
    bridge_url: str | None = None,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    preflight = live_preflight(root, bridge_url=bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        raise SocomError("live Ghidra preflight failed:\n- " + "\n- ".join(preflight["errors"]))
    bridge = GhidraBridge(bridge_url, timeout=600.0)
    before = bridge.request("analysis_status")
    log("functions")
    functions = _functions(bridge, log)
    log("data, types, bookmarks, blocks")
    data = _data_index(bridge)
    types = sorted(f"{row['path']}|{row.get('size')}" for row in _type_index(bridge))
    bookmarks = bridge.request("list_bookmarks", limit=1_000_000)
    blocks = _segments(bridge)
    log(f"references over {len(blocks)} blocks")
    references = _references(bridge, blocks, log)
    after = bridge.request("analysis_status")
    if not (isinstance(before, dict) and before.get("analyzing") is False and before == after):
        raise SocomError(f"analysis was not idle and unchanged during the fingerprint: {before!r} -> {after!r}")
    sections = {
        "functions": functions,
        "data": data,
        "types": types,
        "bookmarks": _bookmark_profile(bookmarks),
        "blocks": [{**row} for row in blocks],
        "references": references,
    }
    digests = {name: _digest(value) for name, value in sections.items()}
    return {
        "kind": FINGERPRINT_KIND,
        "schema_version": FINGERPRINT_SCHEMA,
        "program": "socom.elf",
        "analysis": after,
        "counts": {name: len(value) if isinstance(value, list) else None for name, value in sections.items()},
        "digests": digests,
        "fingerprint_sha256": _digest(digests),
        **sections,
    }


def compare_fingerprints(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Every difference between two fingerprints, by section."""

    for value in (before, after):
        if value.get("kind") != FINGERPRINT_KIND or value.get("schema_version") != FINGERPRINT_SCHEMA:
            raise SocomError("not a schema 1 fingerprint")
    old = {row["address"]: row for row in before["functions"]}
    new = {row["address"]: row for row in after["functions"]}
    changed = []
    for address in sorted(set(old) | set(new)):
        a, b = old.get(address), new.get(address)
        if a != b:
            fields = sorted({key for key in set(a or {}) | set(b or {}) if (a or {}).get(key) != (b or {}).get(key)})
            changed.append({"address": address, "fields": fields, "before": a, "after": b})

    def rows(section: str) -> tuple[list[Any], list[Any]]:
        a = {_digest(row): row for row in before[section]}
        b = {_digest(row): row for row in after[section]}
        return [a[key] for key in sorted(a.keys() - b.keys())], [b[key] for key in sorted(b.keys() - a.keys())]

    data_removed, data_added = rows("data")
    types_removed, types_added = rows("types")
    refs_removed, refs_added = rows("references")
    return {
        "kind": "socom-ghidra-fingerprint-diff",
        "identical": before["fingerprint_sha256"] == after["fingerprint_sha256"],
        "sections_changed": sorted(name for name in before["digests"] if before["digests"][name] != after["digests"].get(name)),
        "functions": changed,
        "data": {"removed": data_removed, "added": data_added},
        "types": {"removed": types_removed, "added": types_added},
        "references": {"removed": refs_removed, "added": refs_added},
        "bookmarks_equal": before["bookmarks"] == after["bookmarks"],
        "blocks_equal": before["blocks"] == after["blocks"],
    }
