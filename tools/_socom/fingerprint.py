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
offers no unfiltered reference iterator (list_data_items_by_xrefs and
list_globals walk ReferenceManager destinations but drop every one, since
getPrimarySymbol returns a dynamic symbol for any referenced address), so the
sweep asks get_bulk_xrefs for every address of every block in 16,000-address
calls; the three 32 MiB IOP RAM and RAM mirror blocks are most of it. The GUI
bridge serves requests on a pool of three HTTP threads, so the default
"concurrent" mode keeps three of the same calls (and of the per-function
get_function_by_address reads) in flight, each worker on its own keep-alive
connection, and consumes the answers in request order. "legacy" issues them
one at a time through GhidraBridge, as before. Both send identical requests
and produce identical output.
"""

from __future__ import annotations

import json
import re
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from http.client import HTTPConnection, HTTPException, HTTPSConnection, RemoteDisconnected
from typing import Any, Callable, Iterable, Iterator, TypeVar
from urllib.parse import urlencode, urlsplit

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
SWEEP_WORKERS = 3
SWEEP_MODES = ("concurrent", "legacy")
_SEGMENT = re.compile(r"^(?P<name>.+?):\s+(?:(?P<space>[^:\s]+)::)?(?P<start>[0-9a-fA-F]+)\s+-\s+(?:[^:\s]+::)?(?P<end>[0-9a-fA-F]+)\s*$")
_DETAIL = ("Function:", "Signature:", "Entry:", "Body:")
_Item = TypeVar("_Item")
_Result = TypeVar("_Result")


def _in_order(call: Callable[[_Item], _Result], items: Iterable[_Item], workers: int) -> Iterator[_Result]:
    """Yield call(item) for each item, in item order.

    With one worker every call runs on this thread, one at a time. Otherwise
    up to `workers` calls run at once and at most twice that many are queued,
    so the first failure stops the sweep after the calls already in flight.
    """

    if workers <= 1:
        for item in items:
            yield call(item)
        return
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="socom-fingerprint") as pool:
        pending: deque[Future[_Result]] = deque()
        try:
            for item in items:
                pending.append(pool.submit(call, item))
                if len(pending) >= 2 * workers:
                    yield pending.popleft().result()
            while pending:
                yield pending.popleft().result()
        finally:
            for future in pending:
                future.cancel()


class _PersistentBridge:
    """GhidraBridge's GET request and post_json over one keep-alive connection per thread.

    GhidraBridge opens and closes a connection for every call. At the
    concurrent rate (about 9,700 function reads in ten seconds) Windows wraps
    its 16,384 client ports while the bridge still holds their server-side
    TIME_WAIT, and a connect times out (WinError 10060). URLs, bodies and
    answer parsing are GhidraBridge's; a call that finds its idle connection
    closed is resent once on a new one (every call is a read).
    """

    _STALE = (RemoteDisconnected, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)

    def __init__(self, bridge: GhidraBridge) -> None:
        self.base_url = bridge.base_url
        self.program = bridge.program
        self.timeout = bridge.timeout
        parts = urlsplit(self.base_url)
        self._factory = HTTPSConnection if parts.scheme == "https" else HTTPConnection
        self._netloc = parts.netloc
        self._local = threading.local()
        self._lock = threading.Lock()
        self._open: list[HTTPConnection] = []

    def _connection(self, fresh: bool) -> HTTPConnection:
        connection = getattr(self._local, "connection", None)
        if connection is not None and not fresh:
            return connection
        if connection is not None:
            connection.close()
        connection = self._factory(self._netloc, timeout=self.timeout)
        self._local.connection = connection
        with self._lock:
            self._open.append(connection)
        return connection

    def _send(self, url: str, method: str, body: bytes | None, headers: dict[str, str]) -> Any:
        parts = urlsplit(url)
        target = parts.path + (f"?{parts.query}" if parts.query else "")
        for attempt in (0, 1):
            connection = self._connection(fresh=attempt > 0)
            try:
                connection.request(method, target, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read()
            except self._STALE as exc:
                if attempt == 0:
                    continue
                raise SocomError(f"Ghidra bridge request failed: {url}: {exc}") from exc
            except (OSError, HTTPException) as exc:
                connection.close()
                self._local.connection = None
                raise SocomError(f"Ghidra bridge request failed: {url}: {exc}") from exc
            if not 200 <= response.status < 300:
                raise SocomError(f"Ghidra bridge request failed: {url}: HTTP Error {response.status}: {response.reason}")
            text = payload.decode("utf-8")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        raise AssertionError("unreachable")

    def request(self, endpoint: str, **parameters: object) -> Any:
        query = {key: value for key, value in parameters.items() if value is not None}
        if "program" not in query:
            query["program"] = self.program
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if query:
            url += "?" + urlencode(query)
        return self._send(url, "GET", None, {})

    def post_json(self, endpoint: str, **body: object) -> Any:
        url = f"{self.base_url}/{endpoint.lstrip('/')}?" + urlencode({"program": self.program})
        payload = json.dumps({"program": self.program, **body}).encode("utf-8")
        return self._send(url, "POST", payload, {"Content-Type": "application/json"})

    def close(self) -> None:
        with self._lock:
            connections, self._open = self._open, []
        for connection in connections:
            connection.close()


def _workers(mode: str) -> int:
    if mode not in SWEEP_MODES:
        raise SocomError(f"unknown fingerprint sweep mode {mode!r}; expected one of {', '.join(SWEEP_MODES)}")
    return 1 if mode == "legacy" else SWEEP_WORKERS


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


def _references(
    bridge: GhidraBridge | _PersistentBridge,
    blocks: list[dict[str, Any]],
    log: Callable[[str], None],
    *,
    workers: int = 1,
) -> list[list[str]]:
    def chunks() -> Iterator[tuple[int, int, int]]:
        for index, block in enumerate(blocks):
            for first in range(block["start"], block["end"], SWEEP_CHUNK):
                yield index, first, min(first + SWEEP_CHUNK, block["end"])

    def sweep(chunk: tuple[int, int, int]) -> tuple[int, bool, list[list[str]]]:
        index, first, last = chunk
        block = blocks[index]
        prefix = f"{block['space']}::" if block["space"] else "0x"
        requested = [f"{prefix}{address:x}" for address in range(first, last)]
        response = bridge.post_json("get_bulk_xrefs", addresses=",".join(requested))
        if not isinstance(response, dict) or len(response) != len(requested):
            raise SocomError(f"get_bulk_xrefs did not answer every address of {block['name']} at {first:x}")
        found = [
            [str(reference.get("from")), target, str(reference.get("type"))]
            for target, references in response.items()
            for reference in references or []
        ]
        return index, last == block["end"], found

    rows: list[list[str]] = []
    for index, block_done, found in _in_order(sweep, chunks(), workers):
        rows.extend(found)
        if block_done:
            log(f"  references through {blocks[index]['name']}: {len(rows)}")
    return sorted(rows)


def _functions(bridge: GhidraBridge | _PersistentBridge, log: Callable[[str], None], *, workers: int = 1) -> list[dict[str, Any]]:
    listing = bridge.request("list_functions_enhanced", offset=0, limit=1_000_000)
    if not isinstance(listing, dict) or not isinstance(listing.get("functions"), list):
        raise SocomError("list_functions_enhanced returned no function list")

    def describe(function: dict[str, Any]) -> dict[str, Any]:
        row = {
            "address": function["address"],
            "name": function["name"],
            "thunk": bool(function.get("isThunk")),
            "external": bool(function.get("isExternal")),
        }
        if not row["external"]:
            text = bridge.request("get_function_by_address", address=f"0x{int(function['address'], 16):x}")
            row["details"] = [line for line in str(text).splitlines() if line.startswith(_DETAIL)]
        return row

    rows = list(_in_order(describe, listing["functions"], workers))
    log(f"  functions: {len(rows)}")
    return sorted(rows, key=lambda row: row["address"])


def program_fingerprint(
    root: Path,
    *,
    bridge_url: str | None = None,
    log: Callable[[str], None] = lambda _message: None,
    sweep_mode: str = "concurrent",
) -> dict[str, Any]:
    workers = _workers(sweep_mode)
    preflight = live_preflight(root, bridge_url=bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        raise SocomError("live Ghidra preflight failed:\n- " + "\n- ".join(preflight["errors"]))
    bridge = GhidraBridge(bridge_url, timeout=600.0)
    reader = _PersistentBridge(bridge) if workers > 1 else bridge
    try:
        before = bridge.request("analysis_status")
        log(f"functions ({sweep_mode}: {workers} request{'s' if workers > 1 else ''} in flight)")
        functions = _functions(reader, log, workers=workers)
        log("data, types, bookmarks, blocks")
        data = _data_index(bridge)
        types = sorted(f"{row['path']}|{row.get('size')}" for row in _type_index(bridge))
        bookmarks = bridge.request("list_bookmarks", limit=1_000_000)
        blocks = _segments(bridge)
        log(f"references over {len(blocks)} blocks")
        references = _references(reader, blocks, log, workers=workers)
        after = bridge.request("analysis_status")
    finally:
        if isinstance(reader, _PersistentBridge):
            reader.close()
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
