"""A small HTTP client for the GhidraMCP bridge, for the release lane (standard library only).

Facts this client relies on were read from the installed plugin (GhidraMCP 6.0.0, its
``EndpointRegistry``, ``FunctionService``, ``CommentService``, ``SymbolLabelService``,
``DocumentationHashService``, ``ServiceUtils``, ``MultiToolProgramProvider`` and
``NamingPolicy`` classes), from Ghidra 12.1.4's ``SymbolManager``, ``FunctionSymbol`` and
``FunctionDB``, and checked with read-only probes:

* every endpoint takes ``program`` from the query string. The plugin looks a program up by
  its project path first (then by name ignoring case, path-contains, name without extension),
  so this client always sends the path (``/socom-release``, ``/socom.elf``), never a bare name
  and never an empty value (which would mean the active program);
* writes are JSON POST bodies; a GET value is URL-decoded twice, so a value holding
  ``= & % +`` is percent-encoded twice (``docs/reconstruction/GHIDRA.md``, "Bridge hazards");
* answers are HTTP 200 with JSON (``{"error": ...}`` on failure) or plain text;
* ``get_function_by_address``, ``rename_function_by_address`` and ``get_plate_comment``
  resolve an address to the function *containing* it when none starts there, so callers
  compare the reported entry with the address they asked for;
* ``create_label`` calls ``SymbolTable.createLabel``, which renames a function whose name is
  still DEFAULT (``FUN_...``, or a default thunk) instead of adding a label
  (``SymbolManager.tryUpdatingDefaultFunction``); with a user-defined function name it adds a
  separate, non-primary label. So a function is renamed before its label is added;
* a thunk whose name is DEFAULT shows its target's name (``FunctionSymbol.doGetName``);
* ``set_plate_comment`` sleeps 500 ms after each call; ``set_comment`` with ``type=plate``
  writes the same comment (``Listing.setComment(entry, PLATE)``, which is what
  ``Function.setComment`` does) without the sleep;
* ``get_function_documentation`` lists the labels in the body of the function starting at an
  address (it decompiles, so it is slow, about 0.5 s); ``get_function_labels`` lists them for
  the first function of a given name;
* ``get_function_by_address`` prints ``Function.getSignature()``, i.e.
  ``FunctionDefinitionDataType.getPrototypeString(true)``: ``[noreturn ]<return> [<convention> ]
  <name>(<type> <name>, ...)``; ``get_function_variables`` lists each parameter's name, type name
  and storage (it decompiles, about 0.2 s); ``list_data_types`` prints
  ``name | category | size bytes | path`` for every type of the program;
* ``set_function_prototype`` (signatures step only) is described in ``signatures.py``;
* no endpoint used here saves the program.

Only the GET endpoints in ``READS`` and the POST endpoints in ``WRITES`` can be sent. A
write is refused unless its program is the release program, and a read-only client
refuses every write. Every write sent is kept in ``sent`` with its answer.
"""
from __future__ import annotations

import http.client
import json
import os
import re
from urllib.parse import quote, urlsplit

DEFAULT_URL = "http://127.0.0.1:8089"
PROTOTYPE_PROGRAM = "socom.elf"
PROTOTYPE_PATH = "/socom.elf"
RELEASE_PROGRAM = "SCUS_971.34"
RELEASE_PATH = "/socom-release"
PROGRAMS = {PROTOTYPE_PROGRAM: PROTOTYPE_PATH, RELEASE_PROGRAM: RELEASE_PATH}

# Read-only GET endpoints (each checked in the plugin: no transaction, no save).
READS = frozenset({
    "list_open_programs", "analysis_status", "get_program_options", "list_functions_enhanced",
    "get_function_by_address", "get_plate_comment", "get_function_labels", "audit_global",
    "get_function_documentation", "get_xrefs_from",
    # signatures step: DataTypeService.listDataTypes walks the data type manager;
    # FunctionService.getFunctionVariables reads the parameters (and decompiles, read-only)
    "list_data_types", "get_function_variables",
    # function starts step (tools/release/starts.py): ProgramScriptService.listBookmarks,
    # AnalysisService.findCodeGaps (invokeAndWait, no transaction), ListingService.listDefinedData,
    # FunctionService.disassembleFunction (instructions from the entry to the body's end),
    # XrefCallGraphService getXrefsTo; none opens a transaction
    "list_bookmarks", "find_code_gaps", "list_data_items", "disassemble_function", "get_xrefs_to",
    # group mangled (signatures.py): DataTypeService.getEnumValues finds a type by name, case
    # ignored, in every category (ServiceUtils.findDataTypeByNameInAllCategories) and prints an
    # enum's name, size and values; no transaction
    "get_enum_values",
    # globals step (tools/release/globals.py), each read in the plugin: ListingService.listGlobals
    # (the stored symbols of the global namespace), ListingService.listSegments (the memory blocks),
    # CommentService.getComment (every comment kind at any address), DataTypeService.getStructLayout
    # (a structure's defined components); none opens a transaction
    "list_globals", "list_segments", "get_comment", "get_struct_layout",
})
NO_PROGRAM = frozenset({"list_open_programs"})
# The only writes the names step sends; none of them saves.
WRITES = frozenset({"create_function", "create_label", "rename_function_by_address", "set_comment"})
# The only writes the signatures step sends (tools/release/signatures.py); none of them saves.
SIGNATURE_WRITES = frozenset({"set_function_prototype", "set_comment"})
# The only writes the function starts step sends (tools/release/starts.py); none of them saves.
# disassemble_bytes is always sent with restrict_to_execute_memory false: the plugin passes that
# flag to DisassembleCommand as its followFlow argument (FunctionService.disassembleBytes).
STARTS_WRITES = frozenset({"disassemble_bytes", "create_function"})
# The only writes the globals step sends (tools/release/globals.py); none of them saves or clears.
# apply_data_type is sent only with clear_existing false (DataTypeService.applyDataType then does
# Listing.createData alone, which refuses any overlap with an instruction or defined data); the
# client refuses any other form. set_global, apply_data_classification and rename_data are in no
# set: the first two clear code units, the last applies a global naming policy.
GLOBALS_WRITES = frozenset({"create_label", "apply_data_type", "set_comment"})
# The only write the references step sends (tools/release/references.py); it saves nothing.
# add_memory_reference (XrefCallGraphService.addMemoryReference) runs ReferenceManager.addMemoryReference
# in one transaction; the client sends it only with a data type (READ, WRITE, DATA: a flow type could
# change fall-through), an explicit source (ANALYSIS or USER_DEFINED) and an operand of 0 or more.
REFERENCE_WRITES = frozenset({"add_memory_reference"})
REFERENCE_TYPES = frozenset({"READ", "WRITE", "DATA"})
REFERENCE_SOURCES = frozenset({"ANALYSIS", "USER_DEFINED"})

_FUNCTION = re.compile(r"^Function: (.*) at ([0-9a-fA-F]+)$")
_BODY = re.compile(r"^Body: ([0-9a-fA-F]+) - ([0-9a-fA-F]+)$")
_LABEL = re.compile(r"^Address: ([0-9a-fA-F]+), Name: (.*), Source: (\w+)$")
_SPECIAL = re.compile(r"[=&%+]")


class BridgeError(RuntimeError):
    """The bridge could not be reached or answered something unexpected."""


class WriteRefused(BridgeError):
    """A write this client must not send."""


def _value(value) -> str:
    text = str(value).lower() if isinstance(value, bool) else str(value)
    encoded = quote(text, safe="")
    return quote(encoded, safe="") if _SPECIAL.search(text) else encoded


class Bridge:
    """Keep-alive client; ``read_only`` refuses every write (dry runs and plans)."""

    def __init__(self, url: str | None = None, *, read_only: bool = True, timeout: float = 120.0,
                 writes: frozenset = WRITES):
        self.url = (url or os.environ.get("SOCOM_GHIDRA_URL") or DEFAULT_URL).rstrip("/")
        parts = urlsplit(self.url)
        if parts.scheme != "http" or not parts.hostname:
            raise BridgeError(f"bridge URL must be http://host:port, not {self.url!r}")
        self.host, self.port = parts.hostname, parts.port or 80
        self.read_only = read_only
        self.writes = writes  # the write endpoints this client may send (WRITES or SIGNATURE_WRITES)
        self.timeout = timeout
        self.sent: list[dict] = []  # every write sent, in order, with its answer
        self._conn: http.client.HTTPConnection | None = None

    def _send(self, method: str, path: str, body: bytes | None = None):
        headers = {"Content-Type": "application/json"} if body is not None else {}
        for attempt in (0, 1):
            if self._conn is None:
                self._conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
            try:
                self._conn.request(method, path, body=body, headers=headers)
                response = self._conn.getresponse()
                text = response.read().decode("utf-8")
                break
            except (OSError, http.client.HTTPException) as exc:
                self._conn.close()
                self._conn = None
                # A GET is retried once on a fresh connection; a write never is.
                if attempt or method != "GET":
                    raise BridgeError(f"bridge request failed: {method} {path.split('?')[0]}: {exc}") from exc
        if response.status != 200:
            raise BridgeError(f"bridge answered HTTP {response.status} to {method} {path.split('?')[0]}: {text[:200]}")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def clones(self, count: int) -> list["Bridge"]:
        """Read-only clients on their own connections (the bridge serves three requests at once)."""

        return [Bridge(self.url, read_only=True, timeout=self.timeout) for _ in range(count)]

    def get(self, endpoint: str, program: str | None = None, **params):
        if endpoint not in READS:
            raise BridgeError(f"{endpoint} is not a read this tool may send")
        if endpoint not in NO_PROGRAM:
            if program not in PROGRAMS:
                raise BridgeError(f"{endpoint} needs program= one of {sorted(PROGRAMS)}, not {program!r}")
            params["program"] = PROGRAMS[program]
        query = "&".join(f"{quote(k, safe='')}={_value(v)}" for k, v in params.items() if v is not None)
        return self._send("GET", f"/{endpoint}" + (f"?{query}" if query else ""))

    def write(self, endpoint: str, program: str, **body):
        if self.read_only:
            raise WriteRefused(f"read-only bridge: {endpoint} not sent")
        if endpoint not in self.writes:
            raise WriteRefused(f"{endpoint} is not a write this tool may send")
        if program != RELEASE_PROGRAM or "program" in body:
            raise WriteRefused(f"writes go to {RELEASE_PROGRAM} only, not {program!r}")
        if endpoint == "apply_data_type" and body.get("clear_existing") is not False:
            # the plugin's default is true: it would clear the code units in the range first
            raise WriteRefused("apply_data_type is sent only with clear_existing false")
        if endpoint == "add_memory_reference" and not (
                body.get("ref_type") in REFERENCE_TYPES and body.get("source_type") in REFERENCE_SOURCES
                and isinstance(body.get("operand_index"), int) and body["operand_index"] >= 0):
            raise WriteRefused("add_memory_reference is sent only with ref_type READ, WRITE or DATA, source_type "
                               "ANALYSIS or USER_DEFINED and an operand index of 0 or more")
        path = PROGRAMS[program]
        payload = json.dumps({"program": path, **body}, sort_keys=True).encode("utf-8")
        record = {"endpoint": endpoint, "program": path, "body": body, "response": None}
        self.sent.append(record)
        try:
            record["response"] = self._send("POST", f"/{endpoint}?program={_value(path)}", payload)
        except BridgeError as exc:
            record["response"] = {"transport_error": str(exc)}
            raise
        return record["response"]


# --- parsers -------------------------------------------------------------------------------

def parse_function(text) -> dict | None:
    """``get_function_by_address`` text: name, entry, body min/max, signature; None if none."""

    if not isinstance(text, str) or not text.startswith("Function: "):
        return None
    out: dict = {}
    for line in text.splitlines():
        if match := _FUNCTION.match(line):
            out["name"] = match.group(1)
        elif line.startswith("Entry: "):
            out["entry"] = int(line[7:].strip(), 16)
        elif line.startswith("Signature: "):
            out["signature"] = line[11:].strip()
        elif match := _BODY.match(line):
            out["body_min"], out["body_max"] = int(match.group(1), 16), int(match.group(2), 16)
    if not {"name", "entry", "body_min", "body_max"} <= out.keys():
        raise BridgeError(f"cannot parse get_function_by_address answer: {text[:200]!r}")
    out["noreturn"] = out.get("signature", "").startswith("noreturn ")
    return out


def parse_labels(text) -> list[tuple[int, str]]:
    """``get_function_labels`` text: (address, name) of each label in the body."""

    if not isinstance(text, str):
        raise BridgeError(f"get_function_labels answered {text!r}")
    out = []
    for line in text.splitlines():
        if match := _LABEL.match(line.strip()):
            out.append((int(match.group(1), 16), match.group(2)))
    return out


def parse_documentation_labels(value, address: int) -> list[tuple[int, str]]:
    """``get_function_documentation``: (address, name) of each label of the function at ``address``."""

    if not isinstance(value, dict) or "error" in value or not isinstance(value.get("labels"), list):
        raise BridgeError(f"get_function_documentation {address:#x}: {str(value)[:200]!r}")
    if int(str(value.get("source_address")), 16) != address:
        raise BridgeError(f"get_function_documentation {address:#x} answered {value.get('source_address')}")
    return [(address + int(row["relative_offset"]), row["name"]) for row in value["labels"]]


def ok_status(response) -> bool:
    return isinstance(response, dict) and response.get("status") == "success"


def ok_create(response) -> bool:
    return isinstance(response, dict) and response.get("success") is True


def program_option(response, name: str):
    if not isinstance(response, dict) or not isinstance(response.get("options"), list):
        raise BridgeError("get_program_options answer is not an option list")
    return next((row.get("value") for row in response["options"] if row.get("name") == name), None)
