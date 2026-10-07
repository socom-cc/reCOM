"""Explicitly targeted access to the live soCOM Ghidra program."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .constants import EXPECTED_ENTRY, EXPECTED_GHIDRA_VERSION, REFERENCE_SHA256
from .type_apply import parse_enum_values, parse_struct_layout
from .util import SocomError, canonical_json, load_json, sha256_file

DEFAULT_GHIDRA_URL = "http://127.0.0.1:8089"
SOCOM_PROJECT = "soCOM"
SOCOM_PROGRAM = "socom.elf"
SOCOM_PROGRAM_PATH = "/socom.elf"
EXPECTED_LANGUAGE = "r5900:LE:32:default"
EXPECTED_COMPILER = "default"
EXPECTED_IMAGE_BASE = "00100000"
EXPECTED_ADDRESS_SIZE = 32
PROGRAM_INFORMATION_GROUP = "Program Information"
EXECUTABLE_SHA256_OPTION = "Executable SHA256"
BASELINE_FUNCTION_COUNT = 9_715
BASELINE_SYMBOL_COUNT = 24_194
BASELINE_DATA_TYPE_COUNT = 210
BASELINE_MEMORY_BLOCK_COUNT = 27
EXPECTED_SENTINEL = (
    "addiu sp,sp,-0x30",
    "sd ra,0x20(sp)",
    "sq s1,0x10(sp)",
    "sq s0,0x0(sp)",
    "move s1,a0",
    "jal 0x00144890",
)

_FUNCTION_RE = re.compile(r"^(.*?)\s+at\s+([0-9a-fA-F]+)$")
_DATA_RE = re.compile(
    r"^(.*?)\s+@\s+((?:[^:]+::)?[0-9a-fA-F]+)\s+\[(.*)\]\s+"
    r"\((\d+)\s+bytes?\)$"
)
_TYPE_RE = re.compile(
    r"^(.*?)\s+\|\s+(.*?)\s+\|\s+(\d+|variable)\s+bytes?\s+\|\s+(.*)$"
)
_DISASSEMBLY_RE = re.compile(
    r"^((?:[^:]+::)?[0-9a-fA-F]+):\s+(.*?)\s*$"
)
_FUNCTION_DETAILS_RE = re.compile(
    r"^Function:\s+(.*?)\s+at\s+((?:[^:]+::)?[0-9a-fA-F]+)\s*$"
)


def _portable_address(value: str) -> str:
    text = value.strip()
    if "::" in text:
        space, raw = text.split("::", 1)
        return f"{space}::{int(raw, 16):08x}"
    return f"{int(text.removeprefix('0x'), 16):08x}"


def _bridge_address(value: str) -> str:
    """Render a canonical receipt address for a bridge request."""

    if "::" in value:
        space, raw = value.split("::", 1)
        return f"{space}::{int(raw, 16):x}"
    return f"0x{int(value, 0):x}"


def _address_spaces(bridge: "GhidraBridge") -> list[dict[str, Any]]:
    value = bridge.request("get_address_spaces")
    if not isinstance(value, dict) or not isinstance(value.get("address_spaces"), list):
        raise SocomError("Ghidra address-space response is not an object")
    return [row for row in value["address_spaces"] if isinstance(row, dict)]


def _validate_qualified_addresses(
    bridge: "GhidraBridge", scope: dict[str, list[str]]
) -> None:
    qualified = [
        value
        for key in ("functions", "globals")
        for value in scope[key]
        if "::" in value
    ]
    if not qualified:
        return
    names = {
        str(row.get("name"))
        for row in _address_spaces(bridge)
        if row.get("name") is not None
    }
    unknown = sorted(
        {value.split("::", 1)[0] for value in qualified} - names,
        key=lambda value: (value.casefold(), value),
    )
    if unknown:
        raise SocomError(
            "receipt scope contains unknown or mis-cased address spaces: "
            + repr(unknown)
        )


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _nonempty_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _local_profile_versions() -> list[str]:
    roots = (
        Path.home() / ".ghidra",
        Path(os.environ.get("APPDATA", "")) / "ghidra",
    )
    versions: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("ghidra_*_PUBLIC"):
            match = re.fullmatch(r"ghidra_(.+)_PUBLIC", path.name)
            if match:
                versions.add(match.group(1))
    return sorted(versions)


class GhidraBridge:
    """Small HTTP client which supplies the soCOM program on every program call."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        program: str = SOCOM_PROGRAM,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("SOCOM_GHIDRA_URL") or DEFAULT_GHIDRA_URL
        ).rstrip("/")
        self.program = program
        self.timeout = timeout

    def request(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        include_program: bool = True,
        **parameters: object,
    ) -> Any:
        normalized = endpoint.lstrip("/")
        query = {key: value for key, value in parameters.items() if value is not None}
        if include_program and "program" not in query:
            query["program"] = self.program
        url = f"{self.base_url}/{normalized}"
        data = None
        if method.upper() == "GET":
            if query:
                url += "?" + urlencode(query)
        else:
            data = urlencode(query).encode("utf-8")
        try:
            request = Request(url, data=data, method=method.upper())
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
        except Exception as exc:
            raise SocomError(f"Ghidra bridge request failed: {url}: {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def post_json(self, endpoint: str, **body: object) -> Any:
        """POST a JSON body; some endpoints read the program from the body."""

        url = f"{self.base_url}/{endpoint.lstrip('/')}?" + urlencode(
            {"program": self.program}
        )
        payload = json.dumps({"program": self.program, **body}).encode("utf-8")
        try:
            request = Request(
                url,
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
        except Exception as exc:
            raise SocomError(f"Ghidra bridge request failed: {url}: {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def schema(self) -> dict[str, Any]:
        value = self.request("mcp/schema", include_program=False)
        if not isinstance(value, dict) or not isinstance(value.get("tools"), list):
            raise SocomError("Ghidra /mcp/schema response is not a tool schema")
        return value

    def project_files(self) -> dict[str, Any]:
        value = self.request("list_project_files", include_program=False, folder="/")
        if not isinstance(value, dict):
            raise SocomError("Ghidra project-file response is not an object")
        return value

    def save_program(self) -> Any:
        return self.request("save_program")

    def paged_text(
        self,
        endpoint: str,
        *,
        page_size: int = 1_000,
        max_pages: int = 1_000,
        **parameters: object,
    ) -> list[str]:
        rows: list[str] = []
        offset = 0
        for _ in range(max_pages):
            value = self.request(
                endpoint, offset=offset, limit=page_size, **parameters
            )
            if not isinstance(value, str):
                raise SocomError(f"Ghidra /{endpoint} response is not text")
            page = _nonempty_lines(value)
            if len(page) == 1 and page[0].startswith("No "):
                return rows
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += len(page)
        raise SocomError(f"Ghidra /{endpoint} exceeded {max_pages} pages")


def _parse_functions(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in _nonempty_lines(text):
        match = _FUNCTION_RE.match(line)
        if not match:
            raise SocomError(f"cannot parse Ghidra function row: {line!r}")
        rows.append(
            {
                "address": _portable_address(match.group(2)),
                "name": match.group(1),
            }
        )
    return sorted(rows, key=lambda row: (row["address"], row["name"]))


def _parse_data_in_order(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines:
        match = _DATA_RE.match(line)
        if not match:
            raise SocomError(f"cannot parse Ghidra data row: {line!r}")
        address = _portable_address(match.group(2))
        rows.append(
            {
                "address": address,
                "name": match.group(1),
                "type": match.group(3),
                "size": int(match.group(4)),
            }
        )
    return rows


def _parse_data(lines: list[str]) -> list[dict[str, Any]]:
    return sorted(
        _parse_data_in_order(lines),
        key=lambda row: (row["address"], row["name"], row["type"], row["size"]),
    )


def _parse_types(lines: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in lines:
        match = _TYPE_RE.match(line)
        if not match:
            raise SocomError(f"cannot parse Ghidra data-type row: {line!r}")
        rows.append(
            {
                "name": match.group(1),
                "category": match.group(2),
                "size": (
                    int(match.group(3))
                    if match.group(3).isdigit()
                    else match.group(3)
                ),
                "path": match.group(4),
            }
        )
    return sorted(
        rows, key=lambda row: (row["path"], row["name"], str(row["size"]))
    )


def _disassembly_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in _nonempty_lines(text):
        match = _DISASSEMBLY_RE.match(line)
        if match:
            rows.append(
                {
                    "address": _portable_address(match.group(1)),
                    "instruction": match.group(2).strip(),
                }
            )
    return rows


def _bookmark_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("bookmarks"), list):
        raise SocomError("Ghidra bookmark response is not an object")
    bookmarks = [row for row in value["bookmarks"] if isinstance(row, dict)]
    by_type = Counter(str(row.get("type", "")) for row in bookmarks)
    by_category = Counter(str(row.get("category", "")) for row in bookmarks)
    return {
        "count": len(bookmarks),
        "by_type": dict(sorted(by_type.items())),
        "by_category": dict(sorted(by_category.items())),
        "error_or_warning_count": sum(
            count
            for name, count in by_type.items()
            if name.casefold() in {"error", "warning"}
        ),
    }


def _program_option(value: Any, name: str) -> Any:
    if not isinstance(value, dict) or not isinstance(value.get("options"), list):
        raise SocomError("Ghidra program-option response is not an object")
    return next(
        (
            row.get("value")
            for row in value["options"]
            if isinstance(row, dict) and row.get("name") == name
        ),
        None,
    )


def _baseline_required(root: Path) -> bool:
    path = root / ".agent" / "RECONSTRUCTION_PROGRESS.json"
    if not path.is_file():
        return False
    try:
        tracker = load_json(path)
    except Exception:
        return False
    target = next(
        (
            row
            for row in tracker.get("verification_targets", [])
            if row.get("id") == "socom:verification:ghidra-program"
        ),
        {},
    )
    return target.get("status") == "bootstrap-r5900"


def live_preflight(
    root: Path,
    *,
    bridge_url: str | None = None,
    strict_baseline: bool | None = None,
) -> dict[str, Any]:
    """Verify the project, program, architecture, analysis, and sentinel bytes."""

    bridge = GhidraBridge(bridge_url)
    errors: list[str] = []
    try:
        schema = bridge.schema()
        project = bridge.project_files()
        programs = bridge.request("list_open_programs", include_program=False)
        info = bridge.request("get_current_program_info")
        options = bridge.request(
            "get_program_options", group=PROGRAM_INFORMATION_GROUP
        )
        analysis = bridge.request("analysis_status")
        entries = bridge.request("get_entry_points")
        bookmarks = bridge.request("list_bookmarks")
        disassembly = bridge.request(
            "disassemble_function", address=f"0x{EXPECTED_ENTRY + 0xcf0:08x}"
        )
    except SocomError as exc:
        return {
            "ok": False,
            "project": SOCOM_PROJECT,
            "program": SOCOM_PROGRAM,
            "program_path": SOCOM_PROGRAM_PATH,
            "errors": [str(exc)],
        }

    if not isinstance(info, dict):
        errors.append("program information is unavailable")
        info = {}
    if not isinstance(programs, dict):
        errors.append("open-program inventory is unavailable")
        programs = {}
    if not isinstance(analysis, dict):
        errors.append("analysis status is unavailable")
        analysis = {}
    if not isinstance(entries, str):
        errors.append("entry-point listing is unavailable")
        entries = ""
    if not isinstance(disassembly, str):
        errors.append("sentinel disassembly is unavailable")
        disassembly = ""

    files = project.get("files", []) if isinstance(project, dict) else []
    if project.get("project_name") != SOCOM_PROJECT:
        errors.append(
            f"project is {project.get('project_name')!r}, expected {SOCOM_PROJECT!r}"
        )
    if not any(
        isinstance(row, dict)
        and row.get("name") == SOCOM_PROGRAM
        and row.get("path") == SOCOM_PROGRAM_PATH
        and row.get("content_type") == "Program"
        for row in files
    ):
        errors.append(f"{SOCOM_PROGRAM_PATH} is not a Program in project {SOCOM_PROJECT}")
    open_rows = programs.get("programs", [])
    if not any(
        isinstance(row, dict)
        and row.get("name") == SOCOM_PROGRAM
        and row.get("path") == SOCOM_PROGRAM_PATH
        for row in open_rows
    ):
        errors.append(f"{SOCOM_PROGRAM_PATH} is not open")

    expected_source = root / "support" / "socom.elf"
    source_hash = sha256_file(expected_source) if expected_source.is_file() else None
    if source_hash != REFERENCE_SHA256:
        errors.append(
            f"reference SHA-256 is {source_hash}, expected {REFERENCE_SHA256}"
        )
    # Ghidra records the image hash at import. The recorded import path names
    # whichever machine imported the project, so it is not identity evidence.
    try:
        program_hash = _program_option(options, EXECUTABLE_SHA256_OPTION)
    except SocomError as exc:
        errors.append(str(exc))
        program_hash = None
    if not isinstance(program_hash, str) or program_hash.casefold() != REFERENCE_SHA256:
        errors.append(
            f"program executable SHA-256 is {program_hash!r}, "
            f"expected {REFERENCE_SHA256}"
        )
    expected_fields = {
        "name": SOCOM_PROGRAM,
        "path": SOCOM_PROGRAM_PATH,
        "language": EXPECTED_LANGUAGE,
        "compiler": EXPECTED_COMPILER,
        "address_size": EXPECTED_ADDRESS_SIZE,
        "image_base": EXPECTED_IMAGE_BASE,
    }
    for key, expected in expected_fields.items():
        if info.get(key) != expected:
            errors.append(f"{key} is {info.get(key)!r}, expected {expected!r}")
    entry_address = f"{EXPECTED_ENTRY:08x}"
    if not any(
        line.startswith(("ENTRYPOINT ", "_start ", "entry "))
        and f"@ {entry_address} " in line
        for line in _nonempty_lines(entries)
    ):
        errors.append(f"entry point {entry_address} is unavailable")
    if analysis.get("analyzed") is not True or analysis.get("analyzing") is not False:
        errors.append("auto-analysis is incomplete or still running")

    try:
        bookmark_profile = _bookmark_profile(bookmarks)
    except SocomError as exc:
        errors.append(str(exc))
        bookmark_profile = {
            "count": -1,
            "by_type": {},
            "by_category": {},
            "error_or_warning_count": -1,
        }
    if bookmark_profile["error_or_warning_count"] != 0:
        errors.append("Ghidra contains Error or Warning bookmarks")

    sentinel_rows = _disassembly_rows(disassembly)
    sentinel = tuple(row["instruction"] for row in sentinel_rows[: len(EXPECTED_SENTINEL)])
    if sentinel != EXPECTED_SENTINEL:
        errors.append(
            "main sentinel disassembly differs from the R5900 import baseline"
        )

    local_versions = _local_profile_versions()
    if EXPECTED_GHIDRA_VERSION not in local_versions:
        errors.append(
            f"Ghidra {EXPECTED_GHIDRA_VERSION} user profile is unavailable"
        )

    enforce_counts = (
        _baseline_required(root) if strict_baseline is None else strict_baseline
    )
    baseline = {
        "function_count": BASELINE_FUNCTION_COUNT,
        "symbol_count": BASELINE_SYMBOL_COUNT,
        "data_type_count": BASELINE_DATA_TYPE_COUNT,
        "memory_block_count": BASELINE_MEMORY_BLOCK_COUNT,
    }
    if enforce_counts:
        for key, expected in baseline.items():
            if info.get(key) != expected:
                errors.append(
                    f"bootstrap {key} is {info.get(key)!r}, expected {expected}"
                )

    return {
        "ok": not errors,
        "mutation_performed": False,
        "project": project.get("project_name"),
        "program": info.get("name"),
        "program_path": info.get("path"),
        "source_sha256": source_hash,
        "program_executable_sha256": program_hash,
        "language": info.get("language"),
        "compiler": info.get("compiler"),
        "address_size": info.get("address_size"),
        "image_base": info.get("image_base"),
        "entry_point": entry_address,
        "analysis": {
            "analyzed": analysis.get("analyzed"),
            "analyzing": analysis.get("analyzing"),
        },
        "counts": {
            key: info.get(key)
            for key in (
                "function_count",
                "symbol_count",
                "data_type_count",
                "memory_block_count",
            )
        },
        "baseline_counts_enforced": enforce_counts,
        "bookmark_profile": bookmark_profile,
        "sentinel": sentinel_rows[: len(EXPECTED_SENTINEL)],
        "schema_tool_count": len(schema["tools"]),
        "required_ghidra_version": EXPECTED_GHIDRA_VERSION,
        "local_profile_versions": local_versions,
        "explicit_program_required": True,
        "active_ui_program_required": False,
        "errors": errors,
    }


def _function_index(bridge: GhidraBridge) -> list[dict[str, str]]:
    value = bridge.request("list_functions")
    if not isinstance(value, str):
        raise SocomError("Ghidra function inventory is not text")
    return _parse_functions(value)


def _type_index(bridge: GhidraBridge) -> list[dict[str, Any]]:
    # The extension treats an explicitly empty category as "all categories".
    return _parse_types(
        bridge.paged_text("list_data_types", category="", page_size=1_000)
    )


def _data_index(bridge: GhidraBridge) -> list[dict[str, Any]]:
    return _parse_data(bridge.paged_text("list_data_items"))


def load_receipt_scope(path: Path) -> dict[str, list[str]]:
    value = load_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise SocomError("receipt scope must be a schema_version 1 object")
    allowed = {"schema_version", "functions", "types", "globals"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise SocomError(f"receipt scope has unknown fields: {unknown}")
    result: dict[str, list[str]] = {}
    for key in ("functions", "types", "globals"):
        rows = value.get(key, [])
        if not isinstance(rows, list) or not all(
            isinstance(row, str) and row.strip() for row in rows
        ):
            raise SocomError(f"receipt scope {key} must be a string list")
        if key in {"functions", "globals"}:
            try:
                normalized = [
                    (
                        f"0x{int(row, 0):x}"
                        if "::" not in row
                        else f"{row.split('::', 1)[0]}::"
                        f"{int(row.split('::', 1)[1], 16):x}"
                    )
                    for row in rows
                ]
            except ValueError as exc:
                raise SocomError(
                    f"receipt scope {key} contains an invalid address"
                ) from exc
        else:
            normalized = [row.strip() for row in rows]
        # Exact spelling breaks casefold ties so receipts are reproducible
        # across processes.
        result[key] = sorted(set(normalized), key=lambda value: (value.casefold(), value))
    if not any(result.values()):
        raise SocomError(
            "receipt scope must name at least one function, type, or global"
        )
    return result


def _reported_name(text: Any) -> str | None:
    if not isinstance(text, str) or ": " not in text:
        return None
    return text.splitlines()[0].split(": ", 1)[1].strip()


def _scoped_type_facts(
    bridge: GhidraBridge, row: dict[str, Any], name_counts: Counter
) -> dict[str, Any]:
    """Add component layout or enum values only when the read-back is exact.

    The bridge resolves bare names, ignores case, and truncates names at
    ``&``.  A name that is not unique ignoring case is marked
    ``ambiguous-name``; a read-back whose reported name or size differs is
    ``mismatched-readback``; an unresolvable name is ``unreadable-name``;
    unions and function definitions are ``no-component-readback``.
    """

    facts = dict(row)
    if name_counts[row["name"].casefold()] != 1:
        facts["detail"] = "ambiguous-name"
        return facts
    layout_text = bridge.request("get_struct_layout", struct_name=row["name"])
    layout = parse_struct_layout(layout_text)
    if layout is not None:
        if _reported_name(layout_text) == row["name"] and layout["size"] == row["size"]:
            facts["layout"] = layout
        else:
            facts["detail"] = "mismatched-readback"
        return facts
    enum_text = bridge.request("get_enum_values", enum_name=row["name"])
    values = parse_enum_values(enum_text)
    if values is not None:
        if _reported_name(enum_text) == row["name"] and values["size"] == row["size"]:
            facts["enum"] = values
        else:
            facts["detail"] = "mismatched-readback"
        return facts
    if (
        isinstance(layout_text, str)
        and layout_text.startswith("Data type is not a structure")
        and isinstance(enum_text, str)
        and enum_text.startswith("Data type is not an enumeration")
    ):
        facts["detail"] = "no-component-readback"
    else:
        facts["detail"] = "unreadable-name"
    return facts


def semantic_receipt(
    root: Path,
    *,
    bridge_url: str | None = None,
    scope: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Create a deterministic semantic receipt without saving the program."""

    preflight = live_preflight(root, bridge_url=bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        raise SocomError(
            "live Ghidra preflight failed:\n- " + "\n- ".join(preflight["errors"])
        )
    bridge = GhidraBridge(bridge_url)
    functions = _function_index(bridge)
    types = _type_index(bridge)
    data = _data_index(bridge)
    canonical_scope = scope or {"functions": [], "types": [], "globals": []}
    _validate_qualified_addresses(bridge, canonical_scope)

    types_by_name: dict[str, list[dict[str, Any]]] = {}
    for row in types:
        for key in {row["name"], row["path"], row["path"].lstrip("/")}:
            types_by_name.setdefault(key, []).append(row)

    scoped_functions = []
    for value in canonical_scope["functions"]:
        address = _bridge_address(value)
        disassembly = bridge.request(
            "disassemble_function", address=address
        )
        details = bridge.request(
            "get_function_by_address", address=address
        )
        if not isinstance(disassembly, str) or not isinstance(details, str):
            raise SocomError(f"function evidence is unavailable: {value}")
        detail_lines = _nonempty_lines(details)
        detail_match = next(
            (
                _FUNCTION_DETAILS_RE.match(line)
                for line in detail_lines
                if _FUNCTION_DETAILS_RE.match(line)
            ),
            None,
        )
        if detail_match is None:
            raise SocomError(f"receipt scope function is undefined: {value}")
        scoped_functions.append(
            {
                "address": _portable_address(value),
                "name": detail_match.group(1),
                "details": detail_lines,
                "disassembly": _disassembly_rows(disassembly),
            }
        )

    name_counts = Counter(row["name"].casefold() for row in types)
    scoped_types = []
    for value in canonical_scope["types"]:
        matches = types_by_name.get(value, [])
        if len(matches) != 1:
            raise SocomError(
                f"receipt scope type must resolve exactly once: {value} "
                f"(matches={len(matches)})"
            )
        scoped_types.append(_scoped_type_facts(bridge, matches[0], name_counts))

    scoped_globals = []
    for value in canonical_scope["globals"]:
        row = bridge.request(
            "audit_global", address=_bridge_address(value), strict_mode="off"
        )
        if not isinstance(row, dict) or not row.get("address"):
            raise SocomError(f"receipt scope global is undefined: {value}")
        scoped_globals.append(
            {
                "address": _portable_address(str(row["address"])),
                "name": row.get("name"),
                "type": row.get("type"),
                "length": row.get("length"),
                "comment": row.get("plate_comment", ""),
                "xref_count": row.get("xref_count"),
            }
        )

    semantic = {
        "kind": "socom-ghidra-receipt",
        "schema_version": 1,
        "target": {
            "project": SOCOM_PROJECT,
            "program": SOCOM_PROGRAM,
            "program_path": SOCOM_PROGRAM_PATH,
            "source_sha256": REFERENCE_SHA256,
            "language": EXPECTED_LANGUAGE,
            "compiler": EXPECTED_COMPILER,
            "ghidra_version": EXPECTED_GHIDRA_VERSION,
            "image_base": EXPECTED_IMAGE_BASE,
            "entry_point": f"{EXPECTED_ENTRY:08x}",
        },
        "analysis": preflight["analysis"],
        "counts": preflight["counts"],
        "bookmark_profile": preflight["bookmark_profile"],
        "sentinel": preflight["sentinel"],
        "indexes": {
            "functions": {"count": len(functions), "sha256": _digest(functions)},
            "types": {"count": len(types), "sha256": _digest(types)},
            "data": {"count": len(data), "sha256": _digest(data)},
        },
        "scope": canonical_scope,
        "scoped_facts": {
            "functions": scoped_functions,
            "types": scoped_types,
            "globals": scoped_globals,
        },
    }
    return {
        "ok": True,
        "mutation_performed": False,
        "receipt_sha256": _digest(semantic),
        "receipt": semantic,
    }


def data_overlaps(
    root: Path,
    *,
    bridge_url: str | None = None,
    addresses: tuple[str, ...] = (),
    limit: int = 40,
) -> dict[str, Any]:
    """Report ambiguous interior data roots without modifying Ghidra."""

    preflight = live_preflight(root, bridge_url=bridge_url, strict_baseline=False)
    if not preflight["ok"]:
        return {
            "ok": False,
            "mutation_performed": False,
            "preflight": preflight,
            "item_count": 0,
            "finding_count": 0,
            "findings": [],
        }
    bridge = GhidraBridge(bridge_url)
    rows = _parse_data_in_order(bridge.paged_text("list_data_items"))
    ranges = []
    previous_address = -1
    overlay_data_started = False
    excluded_overlay_item_count = 0
    for row in rows:
        if "::" in row["address"] or row["size"] <= 0:
            continue
        start = int(row["address"], 16)
        if not overlay_data_started and previous_address >= 0 and start < previous_address:
            overlay_data_started = True
        previous_address = start
        # The bulk endpoint enumerates default-space items first and then
        # overlays, but strips the qualifiers.  The first strict decrease is
        # therefore the only safe boundary. Equal addresses before it remain
        # physical aliases and must still be checked for overlap.
        if not overlay_data_started:
            ranges.append({**row, "start": start, "end": start + row["size"]})
        else:
            excluded_overlay_item_count += 1
    address_spaces = _address_spaces(bridge)
    overlay_address_space_count = sum(
        1 for row in address_spaces if row.get("is_overlay") is True
    )
    probes = {int(value, 0) for value in addresses}
    findings: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    for inner in sorted(
        ranges, key=lambda row: (row["start"], -row["end"], row["name"])
    ):
        active = [outer for outer in active if outer["end"] > inner["start"]]
        for outer in active:
            if not (outer["start"] < inner["start"] < outer["end"]):
                continue
            if probes and not any(
                inner["start"] <= probe < inner["end"]
                or outer["start"] <= probe < outer["end"]
                for probe in probes
            ):
                continue
            findings.append(
                {
                    "inner": {
                        key: inner[key] for key in ("address", "size", "name", "type")
                    },
                    "outer": {
                        key: outer[key] for key in ("address", "size", "name", "type")
                    },
                    "offset": inner["start"] - outer["start"],
                }
            )
        active.append(inner)
    cap = max(1, limit)
    return {
        "ok": not findings,
        "mutation_performed": False,
        "preflight": preflight,
        "item_count": len(rows),
        "physical_item_count": len(ranges),
        "excluded_overlay_item_count": excluded_overlay_item_count,
        "overlay_address_space_count": overlay_address_space_count,
        "finding_count": len(findings),
        "findings": findings[:cap],
        "omitted": max(0, len(findings) - cap),
        "note": (
            "Interior roots are ambiguous semantic evidence and must be repaired "
            "or independently resolved before acceptance."
        ),
    }
