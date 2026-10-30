"""The one-time governed repair of the ten split function boundaries.

Ghidra split ten `.symtab` functions that begin `b L; nop` into a thunk at
the start and a default-named FUN_<L> holding the rest of the extent
(`repairs.SPLIT_BOUNDARIES_REPAIR_ID`). GhidraMCP 6.0.0 has no endpoint that
sets a function body or clears a thunk, so the user allowed (2026-10-30) one
reviewed Ghidra script for exactly these ten; every other script stays
forbidden.

`repair_boundaries` checks the spec against the immutable ELF, refuses a
script whose SHA-256 is not the pinned one, and refuses unless the live
program still shows the recorded wrong state (read-only GETs). It then sends
the pinned script once to the bridge's `run_script_inline` endpoint with only
the spec's addresses, waits for auto-analysis to go idle, and reads every
function back: one non-thunk function per extent whose body is exactly the
extent, no function left inside any extent, and ten fewer functions. A dry
run stops before the script.

Facts about the endpoint (GhidraMCP 6.0.0, read from the plugin jar):
`run_script_inline` takes Java source in `code`, needs the Ghidra process
started with `GHIDRA_MCP_ALLOW_SCRIPTS=1`, names the file after the source's
`public class`, writes it to `~/ghidra_scripts`, splits `args` at whitespace,
and runs it on the Swing thread against the program named by the `program`
query (one GhidraScript transaction). It answers plain text that ends with
`=== SCRIPT COMPLETED SUCCESSFULLY ===`, or a JSON error before the script
runs.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from .batch_apply import _FUNCTION_LINE, _SIGNATURE_LINE
from .elf import Elf32File
from .repairs import REPAIRS
from .util import SocomError

SCRIPT_ENDPOINT = "run_script_inline"
SCRIPT_CLASS = "RepairSplitBoundaries"
RESULT_MARK = "SOCOM_REPAIR_BOUNDARIES_RESULT "
COMPLETED = "=== SCRIPT COMPLETED SUCCESSFULLY ==="
_RESULT_LINE = re.compile(re.escape(RESULT_MARK) + r"(\{.*\})\s*$")
_ENTRY_LINE = re.compile(r"^Entry:\s+([0-9a-fA-F]+)\s*$")
_BODY_LINE = re.compile(r"^Body:\s+([0-9a-fA-F]+)\s+-\s+([0-9a-fA-F]+)\s*$")
_PUBLIC_CLASS = re.compile(r"public\s+class\s+(\w+)")


class BoundaryFailure(SocomError):
    """A refused or failed repair; `wrote` says whether the script may have changed anything."""

    def __init__(self, message: str, *, wrote: bool, response: Any = None) -> None:
        super().__init__(message)
        self.wrote = wrote
        self.response = response


def _spec(item_id: str) -> dict[str, Any]:
    spec = REPAIRS.get(item_id)
    if spec is None:
        raise SocomError(f"{item_id} has no recorded repair")
    if spec.get("kind") != "boundaries":
        raise SocomError(f"{item_id} is not a boundary repair")
    return spec


def boundary_script(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    """The pinned script text (CRLF read as LF), its hash and the argument string."""

    path = root / spec["script"]
    data = path.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    if digest != spec["script_sha256"]:
        raise SocomError(f"{spec['script']} has SHA-256 {digest}, not the reviewed {spec['script_sha256']}")
    try:
        source = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise SocomError(f"{spec['script']} is not ASCII") from exc
    if _PUBLIC_CLASS.findall(source) != [SCRIPT_CLASS] or "extends GhidraScript" not in source:
        raise SocomError(f"{spec['script']} must declare exactly one public class {SCRIPT_CLASS} extends GhidraScript")
    arguments = " ".join(
        f"{function['address']}:{function['wrong']['thunk_target']}:{function['end']}" for function in spec["functions"]
    )
    return {
        "path": spec["script"],
        "sha256": digest,
        "endpoint": SCRIPT_ENDPOINT,
        "arguments": arguments,
        "source": source,
    }


def check_reference(root: Path, spec: dict[str, Any]) -> None:
    """Each spec row is a sized .symtab FUNC whose first instructions are `b L; nop`."""

    elf = Elf32File(root / "support" / "socom.elf")
    by_start: dict[int, list[Any]] = {}
    for symbol in elf.symbols():
        if symbol.type_name == "FUNC" and symbol.size:
            by_start.setdefault(symbol.value, []).append(symbol)
    segment = next(elf.load_segments())

    def word(address: int) -> int:
        offset = segment.offset + address - segment.virtual_address
        return int.from_bytes(elf.data[offset : offset + 4], "little")

    problems = []
    previous_end = 0
    for function in spec["functions"]:
        start = int(function["address"], 16)
        split = int(function["wrong"]["thunk_target"], 16)
        end = int(function["end"], 16)
        symbols = by_start.get(start, [])
        if [(symbol.name, symbol.size) for symbol in symbols] != [(function["symbol"], function["size"])]:
            problems.append(f"{function['address']}: .symtab has {[(s.name, s.size) for s in symbols]}")
            continue
        first = word(start)
        target = start + 4 + ((((first & 0xFFFF) ^ 0x8000) - 0x8000) << 2)
        if first >> 16 != 0x1000 or target != split or word(start + 4) != 0:
            problems.append(f"{function['address']}: does not begin `b {function['wrong']['thunk_target']}; nop`")
        if not (start + 8 < split < end == start + function["size"]) or start < previous_end:
            problems.append(f"{function['address']}: the split or end is outside the extent or out of order")
        if function["target"]["body"] != [function["address"], f"0x{end - 1:x}"]:
            problems.append(f"{function['address']}: the target body is not the .symtab extent")
        previous_end = end
    if problems:
        raise SocomError("the boundary repair spec disagrees with support/socom.elf: " + "; ".join(problems))


def _details(bridge: Any, address: int) -> dict[str, Any] | None:
    text = bridge.request("get_function_by_address", address=f"0x{address:x}")
    lines = text.splitlines() if isinstance(text, str) else []

    def first(pattern: re.Pattern[str]) -> re.Match[str] | None:
        return next((match for line in lines if (match := pattern.match(line))), None)

    function, signature, entry, body = (first(p) for p in (_FUNCTION_LINE, _SIGNATURE_LINE, _ENTRY_LINE, _BODY_LINE))
    if not (function and entry and body):
        return None
    return {
        "name": function.group(1),
        "entry": f"0x{int(entry.group(1), 16):x}",
        "signature": signature.group(1) if signature else None,
        "body": [f"0x{int(body.group(1), 16):x}", f"0x{int(body.group(2), 16):x}"],
    }


def _functions(bridge: Any) -> tuple[dict[int, dict[str, Any]], int]:
    """Every function entry (list_functions_enhanced) and the function count."""

    listing = bridge.request("list_functions_enhanced", offset=0, limit=1_000_000)
    if not isinstance(listing, dict) or not isinstance(listing.get("functions"), list):
        raise SocomError("list_functions_enhanced returned no function list")
    count = bridge.request("get_function_count")
    if not isinstance(count, dict) or count.get("function_count") != len(listing["functions"]):
        raise SocomError(f"get_function_count {count!r} disagrees with {len(listing['functions'])} listed functions")
    rows = {}
    for row in listing["functions"]:
        if row.get("isExternal"):
            continue
        rows[int(str(row["address"]), 16)] = row
    return rows, len(listing["functions"])


def _extent(function: dict[str, Any]) -> tuple[int, int, int]:
    return int(function["address"], 16), int(function["wrong"]["thunk_target"], 16), int(function["end"], 16)


def _before_state(bridge: Any, spec: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """Require the recorded wrong state for every function before the script runs."""

    listing, count = _functions(bridge)
    problems: list[str] = []
    rows = []
    for function in spec["functions"]:
        start, split, end = _extent(function)
        wrong = function["wrong"]
        at = function["address"]
        entry_row, split_row = listing.get(start), listing.get(split)
        if not entry_row or entry_row.get("name") != function["name"] or entry_row.get("isThunk") is not True:
            problems.append(f"{at}: listed as {entry_row!r}, not the thunk {function['name']!r}")
        if not split_row or split_row.get("name") != wrong["split_name"] or split_row.get("isThunk") is not False:
            problems.append(f"{wrong['thunk_target']}: listed as {split_row!r}, not {wrong['split_name']!r}")
        inside = [f"0x{address:x}" for address in sorted(listing) if start < address < end and address != split]
        if inside:
            problems.append(f"{at}: other functions start inside the extent: {inside}")
        entry = _details(bridge, start)
        expected = {"name": function["name"], "entry": at, "signature": wrong["signature"], "body": wrong["body"]}
        if entry != expected:
            problems.append(f"{at}: reads {entry!r}, not the recorded {expected!r}")
        piece = _details(bridge, split)
        expected_piece = {
            "name": wrong["split_name"],
            "entry": wrong["thunk_target"],
            "signature": wrong["split_signature"],
            "body": wrong["split_body"],
        }
        if piece != expected_piece:
            problems.append(f"{wrong['thunk_target']}: reads {piece!r}, not the recorded {expected_piece!r}")
        for address in range(start, end, 4):
            owner = _details(bridge, address)
            want = at if address < split else wrong["thunk_target"]
            if not owner or owner["entry"] != want:
                problems.append(f"0x{address:x}: resolves to {owner and owner['entry']!r}, not {want}")
        rows.append(
            {
                "address": at,
                "symbol": function["symbol"],
                "size": function["size"],
                "end": function["end"],
                "name": function["name"],
                "before": {
                    "thunk": True,
                    "body": wrong["body"],
                    "signature": wrong["signature"],
                    "split": wrong["thunk_target"],
                    "split_name": wrong["split_name"],
                    "split_body": wrong["split_body"],
                    "split_signature": wrong["split_signature"],
                },
            }
        )
    if problems:
        raise BoundaryFailure(
            "the live program is not in the recorded wrong state: " + "; ".join(problems), wrote=False
        )
    return count, rows


def _script_result(response: Any, spec: dict[str, Any], before: int) -> dict[str, Any]:
    if not isinstance(response, str):
        raise BoundaryFailure(f"{SCRIPT_ENDPOINT} did not run the script: {response!r}", wrote=False, response=response)
    results = []
    for line in response.splitlines():
        match = _RESULT_LINE.search(line)
        if match:
            try:
                results.append(json.loads(match.group(1)))
            except json.JSONDecodeError as exc:
                raise BoundaryFailure(f"unreadable script result {match.group(1)!r}", wrote=True, response=response) from exc
    if not results or any(result != results[0] for result in results):
        raise BoundaryFailure("the script printed no single result line", wrote=True, response=response)
    result = results[0]
    if result.get("ok") is not True or result.get("changed") is not True:
        raise BoundaryFailure(
            "the script refused or rolled back; nothing changed: " + "; ".join(map(str, result.get("problems", []))),
            wrote=False,
            response=response,
        )
    expected = [
        {"entry": function["address"], "split": function["wrong"]["thunk_target"], "end": function["end"], "name": function["name"]}
        for function in spec["functions"]
    ]
    if (
        COMPLETED not in response
        or result.get("program") != "/socom.elf"
        or result.get("function_count_before") != before
        or result.get("function_count_after") != before - len(expected)
        or result.get("functions") != expected
        or result.get("problems") != []
    ):
        raise BoundaryFailure(f"the script result does not match the spec: {result!r}", wrote=True, response=response)
    return result


def _wait_idle(bridge: Any, timeout: float, sleep: Callable[[float], None]) -> float:
    waited = 0.0
    while True:
        status = bridge.request("analysis_status")
        if isinstance(status, dict) and status.get("analyzing") is False:
            return waited
        if waited >= timeout:
            raise BoundaryFailure(f"auto-analysis did not go idle within {timeout:.0f}s: {status!r}", wrote=True)
        sleep(1.0)
        waited += 1.0


def _after_state(bridge: Any, spec: dict[str, Any], before: int, rows: list[dict[str, Any]]) -> int:
    listing, count = _functions(bridge)
    problems: list[str] = []
    if count != before - len(rows):
        problems.append(f"{count} functions, expected {before - len(rows)}")
    for function, row in zip(spec["functions"], rows):
        start, split, end = _extent(function)
        at = function["address"]
        listed = listing.get(start)
        if not listed or listed.get("name") != function["name"] or listed.get("isThunk") is not False:
            problems.append(f"{at}: listed as {listed!r}, not the non-thunk {function['name']!r}")
        inside = [f"0x{address:x}" for address in sorted(listing) if start < address < end]
        if inside:
            problems.append(f"{at}: functions still start inside the extent: {inside}")
        entry = _details(bridge, start)
        if not entry or entry["name"] != function["name"] or entry["entry"] != at or entry["body"] != function["target"]["body"]:
            problems.append(f"{at}: reads {entry!r}, not one function over {function['target']['body']}")
        for address in range(start, end, 4):
            owner = _details(bridge, address)
            if not owner or owner["entry"] != at:
                problems.append(f"0x{address:x}: resolves to {owner and owner['entry']!r}, not {at}")
        signature = entry["signature"] if entry else None
        row["after"] = {"thunk": False, "body": entry["body"] if entry else None, "signature": signature}
        # Not restored here: a recon repair re-applies the prototypes.
        row["lost"] = {
            "signature": row["before"]["signature"] if signature != row["before"]["signature"] else None,
            "split_signature": row["before"]["split_signature"],
        }
    if problems:
        raise BoundaryFailure("the read-back differs from the target state: " + "; ".join(problems), wrote=True)
    return count


def repair_boundaries(
    root: Path,
    item_id: str,
    bridge: Any,
    *,
    dry_run: bool = False,
    log: Callable[[str], None] = lambda _message: None,
    sleep: Callable[[float], None] = time.sleep,
    idle_timeout: float = 600.0,
) -> dict[str, Any]:
    """Rejoin each split function with the pinned script (or, dry, check everything but run nothing)."""

    spec = _spec(item_id)
    script = boundary_script(root, spec)
    check_reference(root, spec)
    before, rows = _before_state(bridge, spec)
    log(f"{len(rows)} split functions are in the recorded wrong state; {before} functions")
    summary = {key: value for key, value in script.items() if key != "source"}
    if dry_run:
        return {
            "dry_run": True,
            "script": summary,
            "source": script["source"],
            "function_count_before": before,
            "functions": rows,
            "bridge_call_count": 0,
        }
    log(f"running {script['path']} ({script['sha256']}) through {SCRIPT_ENDPOINT}")
    try:
        response = bridge.post_json(SCRIPT_ENDPOINT, code=script["source"], args=script["arguments"])
        result = _script_result(response, spec, before)
        waited = _wait_idle(bridge, idle_timeout, sleep)
        after = _after_state(bridge, spec, before, rows)
    except BoundaryFailure:
        raise
    except SocomError as failure:
        # A lost request or read-back: the script may have run.
        raise BoundaryFailure(str(failure), wrote=True) from failure
    scope = {
        "schema_version": 1,
        # load_receipt_scope's order (casefold, spelling) for 0x-prefixed hex.
        "functions": sorted(row["address"] for row in rows),
        "types": [],
        "globals": [],
    }
    return {
        "dry_run": False,
        "script": summary,
        "script_result": result,
        "analysis_wait_seconds": waited,
        "function_count_before": before,
        "function_count_after": after,
        "functions": rows,
        "lost_signatures": {row["address"]: row["lost"]["signature"] for row in rows if row["lost"]["signature"]},
        "removed_functions": {row["before"]["split"]: row["before"]["split_signature"] for row in rows},
        "receipt_scope": scope,
        "bridge_call_count": 1,
    }
