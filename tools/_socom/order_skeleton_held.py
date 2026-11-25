"""Stage 5: retire or move held skeleton entries in a batch (``order skeleton held-check`` / ``held-decide``).

The skeleton writer holds every body or data statement that no planned unit
owns in the module's unbuilt ``*_holding.cpp`` (BD4), rendered from the
frozen base on every apply.  A held entry leaves its holding file only
through a reviewed **held plan**: a JSON file under ``build/stage5/held-plans/`` or
``build/order-plans/held/`` (``PLAN_DIRS``; kind ``socom-order-held-plan``) listing rows, each keyed by the entry's
body id (its ``/* held from <id> */`` line)::

    {"source": "src/gamez/zNode/node_main.cpp:671", "entry": "SetActive__Q23zdb5CNodeFb",
     "holding_file": "src/gamez/zNode/znode_holding.cpp", "action": "move",
     "destination": "src/gamez/zNode/znode.h", "evidence_class": "PROVEN", "evidence": ["..."]}
    {"source": "...", "entry": "...", "holding_file": "...", "action": "retire", "reason": "duplicate",
     "of": "gamez/zCamera/camera.cpp:689 GetFirstPersonCamPos", "evidence_class": "PROVEN", "evidence": ["..."]}

* **retire** (``reason`` ``duplicate`` with ``of``, or ``no-elf-symbol``):
  the render drops the entry.  The re-apply's carry removes its live fence
  only when the live entry holds no code (comments only): the port lane
  deletes the code first, the route never drops port code.
* **move** (``destination``, optional ``fence``): the render writes the held
  text under its fence at the destination: appended to a unit file, or
  before a header's closing include guard (an inline copy; the render adds
  ``inline`` to its head).  The carry takes the live (port) text along
  unchanged, as for any entry the render moves.  ``fence`` corrects a fence
  name that differs from the ELF symbol.

A held data statement never moves (a ``no-elf-symbol`` retirement of one is
checked against the ELF's LOCAL and local-static names).  A plan moves only
what stage 5 does not order: compiler copies (Metrowerks
binding 13 or WEAK, stage 7) and code with no ELF symbol.  An ordered ELF
artifact (a strong function or any data object) moves through its stage 4
owner row and the order plans (``progress amend-source-plan``, ``progress
reopen-order-skeleton``, ``progress rebase-function-order``): the render
then moves it itself.  A copy's destination must be the file stage 4's
applied annotations place it in (``defines`` in a ``.cpp``, ``emits`` in a
header); a missing row is a stage 4 amendment first.  Code with no ELF
symbol has no stage 4 identity; its destination is a unit file or header of
the route.

``held-decide`` records the rows in the prepare's decisions file (kinds
``held-retire`` / ``held-move``) under its lease, like ``order skeleton
decide``; the writer reads them, the prepare's re-apply (and that of each
segment apply whose unit file receives a move) writes them, and an
independent ``socom-verifier`` accepts each through ``progress
accept-order-skeleton``, whose apply-check re-validates the rows.  A holding
file left without an entry is deleted by the render; its port-added
preamble (``#include`` lines, comments) goes with it, other unfenced code
is a conflict.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .util import SocomError, canonical_json, load_json

PLAN_KIND = "socom-order-held-plan"
PLAN_SCHEMA = 1
PLAN_DIR = "build/stage5/held-plans"
# Where held plans live: the stage 5 plan directory, or beside the order plans (the first real plans were kept there).
PLAN_DIRS = (PLAN_DIR, "build/order-plans/held")
RETIRE_KIND = "held-retire"
MOVE_KIND = "held-move"
HELD_KINDS = (RETIRE_KIND, MOVE_KIND)
ACTIONS = {"retire": RETIRE_KIND, "move": MOVE_KIND}
EVIDENCE_CLASSES = ("PROVEN", "LIKELY", "GUESS")
RETIRE_REASONS = ("duplicate", "no-elf-symbol")
ROW_FIELDS = {
    "retire": {"required": ("source", "entry", "holding_file", "action", "reason", "evidence_class", "evidence"),
               "optional": ("of", "note")},
    "move": {"required": ("source", "entry", "holding_file", "action", "destination", "evidence_class", "evidence"),
             "optional": ("fence", "note")},
}
HEADER_SUFFIXES = (".h", ".hh", ".hpp", ".inc")
CODE_SUFFIXES = (".c", ".cc", ".cp", ".cpp", ".cxx")
HOLDING_RETIRED = "holding-retired"
FENCE_NAME = re.compile(r"^\S+$")
# Metrowerks binding 13 (a kept inline copy) and WEAK: compiler copies, ordered in stage 7, not by the order plans.
COPY_BINDINGS = (2, 13)
_GUARD_END = re.compile(r"^\s*#\s*endif\b")
_SHOWN = 12


def _shown(values: list[str]) -> str:
    return ", ".join(values[:_SHOWN]) + (f", +{len(values) - _SHOWN} more" if len(values) > _SHOWN else "")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_header(path: str) -> bool:
    return path.casefold().endswith(HEADER_SUFFIXES)


# -- the held entries of a render ------------------------------------------------------------


def held_name(item: dict[str, Any]) -> str:
    """The fence name the writer gives a held item."""

    if item["kind"] == "function":
        return item["body"].get("mangled") or f"unparsed:{item['body']['id']}"
    return item.get("mangled") or f"unparsed:{item['path']}:{item['line']}"


def held_source(item: dict[str, Any]) -> str:
    """A held item's body id: ``path:line`` of its frozen-base definition (its ``/* held from */`` line)."""

    return item["body"]["id"] if item["kind"] == "function" else f"{item['path']}:{item['line']}"


def held_index(held: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """{source: facts} of every held item of a render, before any held decision applies."""

    found: dict[str, dict[str, Any]] = {}
    for path, items in sorted(held.items()):
        for item in items:
            source = held_source(item)
            row: dict[str, Any] = {"source": source, "name": held_name(item), "holding_file": path, "kind": item["kind"],
                                   "flag": item.get("flag")}
            if item["kind"] == "function":
                body = item["body"]
                row.update(artifact=body.get("artifact"), reason=body.get("reason"), judgment=body.get("judgment"))
            else:
                artifacts = sorted({str(entry.get("artifact")) for entry in item.get("rows") or [] if entry.get("artifact")})
                row.update(artifact=artifacts[0] if len(artifacts) == 1 else None, artifacts=artifacts,
                           reason=",".join(sorted({str(entry.get("action")) for entry in item.get("rows") or []})),
                           names=sorted({str(entry.get("mangled") or entry.get("name")) for entry in item.get("rows") or []
                                         if entry.get("mangled") or entry.get("name")}))
            found[source] = row
    return found


# -- the plan --------------------------------------------------------------------------------


def plan_path(root: Path, value: str) -> Path:
    """A held plan in one of the plan directories (``PLAN_DIRS``; repo-relative or absolute inside the workspace)."""

    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    if not any(path.is_relative_to((root / directory).resolve()) for directory in PLAN_DIRS) or path.suffix != ".json":
        raise SocomError(f"a held plan is a .json file under {' or '.join(f'{directory}/' for directory in PLAN_DIRS)}: {value}")
    if not path.is_file():
        raise SocomError(f"the held plan {value} does not exist")
    return path


def load_plan(path: Path) -> dict[str, Any]:
    plan = load_json(path)
    if not isinstance(plan, dict) or plan.get("kind") != PLAN_KIND or plan.get("schema_version") != PLAN_SCHEMA:
        raise SocomError(f"{path.name} is not a {PLAN_KIND} (schema {PLAN_SCHEMA})")
    if not isinstance(plan.get("rows"), list) or not plan["rows"]:
        raise SocomError(f"{path.name}: rows must be a non-empty list")
    if not str(plan.get("reason") or "").strip():
        raise SocomError(f"{path.name}: the plan needs a reason (why this batch)")
    return plan


def plan_sha256(plan: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()


def row_shape(row: Any, number: int) -> list[str]:
    """Problems with one plan row's fields (before any check against the render)."""

    label = f"row {number}"
    if not isinstance(row, dict):
        return [f"{label} must be an object"]
    action = row.get("action")
    if action not in ROW_FIELDS:
        return [f"{label}: action must be retire or move"]
    fields = ROW_FIELDS[action]
    problems = []
    missing = [key for key in fields["required"] if key not in row]
    if missing:
        problems.append(f"{label} ({action}) lacks {', '.join(missing)}")
    if extra := sorted(set(row) - set(fields["required"]) - set(fields["optional"])):
        problems.append(f"{label} ({action}) has unknown fields {', '.join(extra)}")
    for key in ("source", "entry", "holding_file"):
        if key in row and (not isinstance(row[key], str) or not row[key].strip()):
            problems.append(f"{label}: {key} must be a non-empty string")
    if "evidence_class" in row and row["evidence_class"] not in EVIDENCE_CLASSES:
        problems.append(f"{label}: evidence_class must be one of {', '.join(EVIDENCE_CLASSES)}")
    evidence = row.get("evidence")
    if "evidence" in row and (not isinstance(evidence, list) or not evidence
                              or not all(isinstance(text, str) and text.strip() for text in evidence)):
        problems.append(f"{label}: evidence must be a non-empty list of lines")
    if action == "retire":
        if "reason" in row and row["reason"] not in RETIRE_REASONS:
            problems.append(f"{label}: reason must be duplicate (with of) or no-elf-symbol")
        if row.get("reason") == "duplicate" and not str(row.get("of") or "").strip():
            problems.append(f"{label}: a duplicate names what it duplicates (of)")
    else:
        destination = row.get("destination")
        if "destination" in row and (not isinstance(destination, str) or not destination.startswith("src/")
                                     or ".." in PurePosixPath(destination).parts or "\\" in destination
                                     or not destination.casefold().endswith(HEADER_SUFFIXES + CODE_SUFFIXES)):
            problems.append(f"{label}: destination must be a repo-relative source or header path under src/")
        if "fence" in row and (not isinstance(row["fence"], str) or not FENCE_NAME.match(row["fence"])):
            problems.append(f"{label}: fence must be one mangled name")
    return problems


def decision_rows(plan: dict[str, Any], relative: str, by: str, at: str) -> list[dict[str, Any]]:
    """The decisions-file rows of a plan (kind, key = source, value = retire or the destination, basis, by, at, the row)."""

    digest = plan_sha256(plan)
    rows = []
    for row in plan["rows"]:
        kind = ACTIONS[row["action"]]
        value = "retire" if kind == RETIRE_KIND else row["destination"]
        basis = f"{row['evidence_class']}: " + "; ".join(text.strip() for text in row["evidence"])
        entry = {"kind": kind, "key": row["source"], "value": value, "basis": basis, "by": by, "at": at,
                 "name": row["entry"], "holding_file": row["holding_file"], "evidence_class": row["evidence_class"],
                 "evidence": [text.strip() for text in row["evidence"]], "plan": relative, "plan_sha256": digest}
        for key in ("reason", "of", "fence", "note"):
            if key in row:
                entry[key] = row[key].strip() if isinstance(row[key], str) else row[key]
        rows.append(entry)
    return sorted(rows, key=lambda row: (row["kind"], row["key"]))


def plan_from_decisions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The plan rows a decisions file's held rows came from (for re-validation)."""

    found = []
    for row in rows:
        entry = {"source": row["key"], "entry": row.get("name"), "holding_file": row.get("holding_file"),
                 "action": "retire" if row["kind"] == RETIRE_KIND else "move", "evidence_class": row.get("evidence_class"),
                 "evidence": row.get("evidence")}
        if row["kind"] == RETIRE_KIND:
            entry["reason"] = row.get("reason")
            if row.get("of"):
                entry["of"] = row["of"]
        else:
            entry["destination"] = row["value"]
            if row.get("fence"):
                entry["fence"] = row["fence"]
        found.append(entry)
    return found


# -- validation against the render, the ELF and stage 4 --------------------------------------


class _Symbols:
    def __init__(self, elf: Any) -> None:
        self.by_name: dict[str, list[Any]] = {}
        for symbol in elf.symbols():
            if symbol.name:
                self.by_name.setdefault(symbol.name, []).append(symbol)

    def find(self, name: str) -> Any:
        rows = [symbol for symbol in self.by_name.get(name, []) if symbol.type in (1, 2) and symbol.size]
        return rows[0] if len(rows) == 1 else None

    def data_like(self, names: list[str]) -> list[str]:
        """ELF data symbols that are these names: exact, an unnamed-namespace (LOCAL) ``name__N@unnamed@...`` or a
        function-local static ``name$N``."""

        found = []
        for name in names:
            plain = name if "@unnamed@" in name else re.sub(r"(?<=.)__(?:\d|Q|F).*$", "", name)
            for symbol_name, symbols in self.by_name.items():
                if not any(symbol.type == 1 for symbol in symbols):
                    continue
                if symbol_name == name or (symbol_name.startswith(f"{plain}__") and "@unnamed@" in symbol_name
                                           and symbol_name[len(plain) + 2:].lstrip("0123456789").startswith("@unnamed@")) \
                        or re.fullmatch(rf"{re.escape(plain)}\$\d+", symbol_name):
                    found.append(symbol_name)
        return sorted(set(found))


def _artifact_id(symbol: Any) -> str:
    return f"socom:{'function' if symbol.type == 2 else 'data'}:0x{symbol.value:x}"


def _edges(root: Path, source_root: Path | None) -> set[tuple[str, str, str]]:
    from .source import source_artifacts

    base = source_root if source_root is not None else root
    return {(row["relation"], row["artifact_id"], row["path"]) for row in source_artifacts(base)["artifacts"]}


def check_rows(root: Path, inputs: Any, index: dict[str, dict[str, Any]], rows: list[dict[str, Any]], *,
               decided: dict[str, str] | None = None) -> tuple[list[str], list[dict[str, Any]]]:
    """(problems, per-row report) of held-plan rows against the render's held entries, the ELF and stage 4's annotations.

    ``index`` is ``held_index`` of the render before any held decision;
    ``decided`` maps a source to the item whose decisions file decides it
    already (another item may not).  The checks:

    * the entry is held: its source is a held entry of the named holding
      file under the named fence name;
    * one row per entry; a retirement as ``no-elf-symbol`` has no ELF
      artifact;
    * a move's destination is a unit file of the accepted order plans or a
      header of the route (the base or the render holds it), never a holding
      file, and a header receives functions only;
    * a move of an ELF artifact (the held entry's own, or the ELF symbol a
      corrected ``fence`` names) moves a compiler copy only (binding 13 or
      WEAK), into the file stage 4's applied annotations place it in
      (``defines`` in a ``.cpp``, ``emits`` in a header).
    """

    problems: list[str] = []
    report: list[dict[str, Any]] = []
    units = {unit["workspace_path"] for _number, unit in inputs.units}
    holding = {row["holding_file"] for row in index.values()}
    symbols: _Symbols | None = None
    edges: set[tuple[str, str, str]] | None = None
    seen: set[str] = set()
    for number, row in enumerate(rows, 1):
        shape = row_shape(row, number)
        if shape:
            problems.extend(shape)
            continue
        source = row["source"]
        label = f"row {number} ({row['entry']}, {source})"
        if source in seen:
            problems.append(f"{label}: the entry is listed twice")
            continue
        seen.add(source)
        entry = index.get(source)
        if entry is None or entry["holding_file"] != row["holding_file"] or entry["name"] != row["entry"]:
            where = f" (held as {entry['name']} in {entry['holding_file']})" if entry is not None else ""
            problems.append(f"{label}: not a held entry of {row['holding_file']} under that fence name{where}")
            continue
        if decided and decided.get(source):
            problems.append(f"{label}: {decided[source]} decides this entry already")
        result: dict[str, Any] = {"row": number, "source": source, "entry": row["entry"], "action": row["action"],
                                  "holding_file": row["holding_file"], "kind": entry["kind"],
                                  "evidence_class": row["evidence_class"], "artifact": entry.get("artifact")}
        if row["action"] == "retire":
            if row["reason"] == "no-elf-symbol" and entry.get("artifact"):
                problems.append(f"{label}: it has the ELF artifact {entry['artifact']}: retire it as a duplicate (of)")
            elif row["reason"] == "no-elf-symbol" and entry["kind"] == "data":
                # A held data statement's rows name its provisional spelling: the ELF may hold the object as a LOCAL
                # (unnamed-namespace) symbol or a function-local static under the same name.
                symbols = symbols or _Symbols(inputs.elf)
                if found := symbols.data_like(entry.get("names") or [entry["name"]]):
                    problems.append(f"{label}: the ELF has {', '.join(found[:3])}: retire it as a duplicate (of)")
            report.append(result)
            continue
        destination = row["destination"]
        result["destination"] = destination
        if entry["kind"] == "data":
            problems.append(f"{label}: a held data statement does not move: a data object the ELF has reaches its unit only "
                            "through its stage 4 owner row and the order plans (where that row exists, the held statement is a "
                            "stale copy: retire it as a duplicate); one the ELF lacks is retired (no-elf-symbol)")
            report.append(result)
            continue
        if destination in holding or destination.endswith("_holding.cpp"):
            problems.append(f"{label}: {destination} is a holding file")
            report.append(result)
            continue
        header = is_header(destination)
        exists = (inputs.source_root / destination).is_file()
        if header and not exists:
            problems.append(f"{label}: {destination} is outside the plan: no header of the route at that path")
        elif not header and destination not in units:
            problems.append(f"{label}: {destination} is outside the plan: not a unit file of the accepted order plans")
        if header and entry["kind"] != "function":
            problems.append(f"{label}: a header receives inline functions only (data moves through its stage 4 owner row)")
        artifact, copy = entry.get("artifact"), entry.get("reason") == "copy-only"
        if row.get("fence") and row["fence"] != entry["name"]:
            symbols = symbols or _Symbols(inputs.elf)
            symbol = symbols.find(row["fence"])
            if symbol is None:
                problems.append(f"{label}: the corrected fence {row['fence']} is no single ELF function or object symbol")
            else:
                found = _artifact_id(symbol)
                if artifact and artifact != found:
                    problems.append(f"{label}: the corrected fence {row['fence']} is {found}, the held entry is {artifact}")
                artifact, copy = found, symbol.binding in COPY_BINDINGS
                result["fence"] = row["fence"]
        elif entry.get("artifact") and entry["kind"] == "function" and not copy:
            symbols = symbols or _Symbols(inputs.elf)
            symbol = symbols.find(entry["name"])
            copy = symbol is not None and symbol.binding in COPY_BINDINGS
        result["artifact"] = artifact
        if artifact:
            if entry["kind"] != "function" or not copy:
                problems.append(f"{label}: {artifact} is an ordered ELF artifact, which a held plan does not move: it reaches "
                                "its unit only through its stage 4 owner row and the order plans (progress amend-source-plan, "
                                "reopen-order-skeleton, rebase-function-order); where that owner row exists already, the held "
                                "body is a stale copy and its route is retirement (retire it as a duplicate)")
            else:
                edges = edges if edges is not None else _edges(root, inputs.source_root)
                relation = "emits" if header else "defines"
                result["stage4"] = f"{relation} {artifact} {destination}"
                if (relation, artifact, destination) not in edges:
                    placed = sorted(f"{edge[0]} {edge[2]}" for edge in edges if edge[1] == artifact)
                    problems.append(f"{label}: stage 4 does not place {artifact} in {destination} (@socom-artifact {relation}; "
                                    f"it has {', '.join(placed) or 'no annotation'}): amend the stage 4 plan first "
                                    "(progress amend-source-plan)")
        else:
            result["stage4"] = None  # no ELF symbol: no stage 4 identity
        report.append(result)
    return problems, report


# -- the writer ------------------------------------------------------------------------------


def held_decisions(inputs: Any) -> list[dict[str, Any]]:
    return [row for (kind, _key), row in sorted(inputs.decisions.items()) if kind in HELD_KINDS]


def _head(text: str) -> tuple[str, dict[str, str] | None]:
    """A header copy's text with ``inline`` before its declarator (and the S4 head record), unless it has one."""

    stripped = text.lstrip()
    if re.match(r"(?:inline|template)\b", stripped) or re.match(r"(?:static\s+)?inline\b", stripped):
        return text, None
    return "inline " + text, {"from": "", "to": "inline "}


def dispose(inputs: Any, writer: Any, held_text: Any) -> dict[str, Any] | None:
    """Apply the held decisions to ``writer.held`` (retired and moved items leave it); returns what moved where.

    ``held_text(item)`` gives (wrappers opening, the definition text,
    wrappers closing).  Returns None without held decisions, else ``{"index",
    "retired", "moved": {destination: [entry]}, "emptied", "rows"}``.  A
    decision whose entry the render does not hold refuses the render.
    """

    rows = held_decisions(inputs)
    index = held_index(writer.held)
    if not rows:
        return None
    before = {path: list(items) for path, items in writer.held.items()}
    by_source = {held_source(item): (path, item) for path, items in before.items() for item in items}
    retired: list[str] = []
    moved: dict[str, list[dict[str, Any]]] = {}
    leaving: set[str] = set()
    for row in rows:
        found = by_source.get(row["key"])
        if found is None or (row.get("holding_file") and found[0] != row["holding_file"]):
            raise SocomError(f"{row['kind']} {row['key']} ({row['item']}): the render holds no such entry"
                             + (f" in {row.get('holding_file')}" if row.get("holding_file") else ""))
        path, item = found
        flag = inputs.decided_flag(row)
        leaving.add(row["key"])
        if row["kind"] == RETIRE_KIND:
            retired.append(row["key"])
            continue
        destination = row["value"]
        opening, text, closing = held_text(item)
        head = None
        if is_header(destination):
            text, head = _head(text)
        name = row.get("fence") or held_name(item)
        source = held_source(item)
        body = "\n".join([*opening, text, *closing])
        block = f"/* @socom-skeleton body {name} */\n/* held from {source} */\n{body}"
        flags = [{"kind": "held-moved", "detail": f"{row['evidence_class']}: from {path} ({row['item']})"}, flag]
        if row.get("evidence_class") == "GUESS":
            flags.append({"kind": "held-guess", "detail": row.get("basis", "")})
        entry = {"kind": "held-" + item["kind"], "name": name, "source": source, "flags": flags, "text_sha256": _sha(body),
                 "moved_from": path, "lines": block.count("\n") + 1, "block": block}
        if head is not None:
            entry["head"] = head
            entry["body_sha256"] = _sha(inputs.texts[source]["text"]) if source in inputs.texts else _sha(text[len(head["to"]):])
        if row.get("fence") and row["fence"] != held_name(item):
            entry["fence_from"] = held_name(item)
        moved.setdefault(destination, []).append(entry)
    emptied = []
    for path, items in before.items():
        kept = [item for item in items if held_source(item) not in leaving]
        if kept:
            writer.held[path] = kept
        else:
            del writer.held[path]
            emptied.append(path)
    symbols: _Symbols | None = None
    for destination, entries in moved.items():
        entries.sort(key=lambda entry: entry["source"])
        if is_header(destination):
            continue  # an inline copy in a header: emitted per unit, its place there says nothing about the ELF
        # Into a unit file: the copies with an ELF symbol in the ELF's address order, each in a slot the held-from
        # order gives the moved entries (an entry with no ELF symbol keeps its slot).
        symbols = symbols or _Symbols(inputs.elf)
        addresses = {entry["source"]: _address(index.get(entry["source"]) or {}, entry["name"], symbols) for entry in entries}
        slots = [number for number, entry in enumerate(entries) if addresses[entry["source"]] is not None]
        placed = sorted((entries[number] for number in slots), key=lambda entry: addresses[entry["source"]])
        for number, entry in zip(slots, placed):
            entries[number] = entry
    return {"index": index, "retired": sorted(retired), "moved": moved, "emptied": sorted(emptied), "rows": rows}


def _address(entry: dict[str, Any], name: str, symbols: "_Symbols") -> int | None:
    """The ELF address of a moved entry: its held artifact's, else that of the ELF symbol its (corrected) fence names."""

    artifact = entry.get("artifact")
    if isinstance(artifact, str) and re.fullmatch(r"socom:(?:function|data):0x[0-9a-f]+", artifact):
        return int(artifact.rsplit(":", 1)[1], 16)
    symbol = symbols.find(name)
    return symbol.value if symbol is not None else None


def append_entries(text: str, entries: list[dict[str, Any]]) -> str:
    """A unit file's LF text with the moved entries after its last line (one blank line before each)."""

    blocks = "\n\n".join(entry["block"] for entry in entries)
    if not text:
        return blocks + "\n"
    return text.rstrip("\n") + "\n\n" + blocks + "\n"


def insert_entries(text: str, entries: list[dict[str, Any]]) -> str:
    """A header's LF text with the moved entries before its closing include-guard ``#endif`` (else at its end).

    Each entry is followed by one blank line, so ``strip_entries`` gives the
    text back exactly.
    """

    lines = text.split("\n")
    trailing = len(lines)
    while trailing > 0 and not lines[trailing - 1].strip():
        trailing -= 1
    if trailing and _GUARD_END.match(lines[trailing - 1]):
        at = trailing - 1
        block = [line for entry in entries for line in (*entry["block"].split("\n"), "")]
    else:
        # No closing guard (#pragma once): after the last line, each entry after one blank line.
        at = trailing
        block = [line for entry in entries for line in ("", *entry["block"].split("\n"))]
    return "\n".join(lines[:at] + block + lines[at:])


def strip_entries(text: str, entries: list[dict[str, Any]]) -> str:
    """The inverse of ``insert_entries`` / ``append_entries`` for a render: each moved entry and its separator removed."""

    lines = text.split("\n")
    for entry in entries:
        fence = f"/* @socom-skeleton body {entry['name']} */"
        start = next((index for index, line in enumerate(lines) if line == fence), None)
        if start is None:
            continue
        stop = start + int(entry["lines"])
        if stop < len(lines) and not lines[stop].strip():
            stop += 1
        elif start > 0 and not lines[start - 1].strip():
            start -= 1
        del lines[start:stop]
    result = "\n".join(lines)
    return result


def manifest_record(disposed: dict[str, Any] | None) -> dict[str, Any] | None:
    """The write manifest's ``held`` record (only with held decisions, so other renders keep their digests)."""

    if disposed is None:
        return None
    return {
        "retired": disposed["retired"],
        "moved": sorted(({"source": entry["source"], "name": entry["name"], "from": entry["moved_from"], "to": destination}
                         for destination, entries in disposed["moved"].items() for entry in entries),
                        key=lambda row: (row["to"], row["source"])),
        "files_retired": disposed["emptied"],
        "decisions": len(disposed["rows"]),
    }


# -- the carry: what a retirement may drop -----------------------------------------------------


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"//[^\n]*")


def code_lines(lines: list[str], *, preamble: bool = False) -> list[str]:
    """The lines that hold code once comments are removed (``preamble``: ``#include`` / ``#pragma`` lines are no code)."""

    text = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub(" ", "".join(lines)))
    found = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if preamble and re.match(r"#\s*(?:include|pragma)\b", stripped):
            continue
        found.append(stripped)
    return found


def plan_report(problems: list[str], report: list[dict[str, Any]], owners: dict[str, str], prepare: str) -> dict[str, Any]:
    """The summary of a checked plan: counts, the items whose files change (to reopen), the rows."""

    moves = [row for row in report if row["action"] == "move"]
    destinations = sorted({row["destination"] for row in moves})
    items = sorted({owners.get(path, prepare) for path in destinations} | {prepare})
    holding = sorted({row["holding_file"] for row in report})
    return {
        "ok": not problems,
        "rows": len(report),
        "retire": sum(1 for row in report if row["action"] == "retire"),
        "move": len(moves),
        "by_evidence_class": {name: sum(1 for row in report if row["evidence_class"] == name) for name in EVIDENCE_CLASSES},
        "holding_files": holding,
        "destinations": destinations,
        "items_to_reopen": items,
        "unowned_destinations": sorted(path for path in destinations if path not in owners),
        "problems": problems,
        "report": report,
    }
