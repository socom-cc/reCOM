"""User placement decisions: parse a decision file, resolve its lines to ELF artifacts, check it (read-only).

A decision file is Markdown the user writes to place artifacts the ELF does
not pin to a file (stage 4's deferred boundary functions)::

    ## zentity/ent_entity.cpp
    Note: CEntity tick/position code, between ent_target.cpp and ent_control.cpp.
    - CEntity::Tick(float)
    - 0x26e700  CZSealBody::FindValidReticleGotoLoc(int *)

* A ``## <module>/<file>`` heading names a destination.  The module maps
  case-insensitively onto ``src/gamez/<Module>/`` (``zentity`` ->
  ``src/gamez/zEntity``); a first component naming another top-level
  ``src/`` directory maps there (``rt/rtlist.h`` -> ``src/rt/rtlist.h``,
  ``Apps/FTS/...`` -> ``src/Apps/FTS/...``).  Existing directories and files
  keep their on-disk letter case.  A header heading (``zmath/zmath.h``)
  means the function is defined inline or as a template in that header:
  the binary's copy is compiler output in the file that used it.
* A list line ``- [0xADDR  ]<declaration>`` names one artifact: by its start
  address when the line has one (a declaration after it must be one of
  that artifact's), else by the readable declaration the Metrowerks
  demangler behind ``reference demangle`` gives one of its ELF names (or the
  ELF name itself), whitespace ignored.  A declaration naming several
  artifacts needs its address.
* Any other line under a heading (``Note: ...``) is the user's reasoning.

An owner plan row cites a heading with a ``decision`` object ``{file,
sha256, heading}``: the repo-relative decision file, the SHA-256 of its
bytes with CRLF normalized to LF, and the heading as written
(``source plan validate`` checks it; see ``DecisionCheck``).

A decision file is revised in place.  Before an edit its current bytes are
stored unchanged as ``history/<stem>.<sha256><suffix>`` beside it (the
LF-normalized SHA-256 in the name; see ``revision_path``), so a citation of
an earlier revision still resolves without git history.  Such a citation
holds while the current file's heading still names the same destination and
still lists every artifact the citing row or entry places from it; it is
then reported as a note, otherwise it is a problem (the plan is amended to
cite the current file).  A digest with no stored revision is a problem.

``source placements check --file`` reports every line's artifact, the
unmatched, ambiguous, mismatched and duplicate lines, each destination's
path, plan items and plan state, the contiguity of each source file's
functions in address order, the file's stored revisions, and every plan
citation of the file with the revision it cites and whether it holds.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from collections import defaultdict
from contextlib import closing
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .source_owner import readable

DECISION_FIELDS = ("file", "sha256", "heading")
HEADING_RE = re.compile(r"^##\s+(?P<heading>\S.*?)\s*$")
TITLE_RE = re.compile(r"^#(?!#)")
ITEM_RE = re.compile(r"^\s*[-*+]\s+(?P<text>.*?)\s*$")
ADDRESS_RE = re.compile(r"^(?P<address>0x[0-9a-fA-F]+)(?:\s+(?P<rest>.*))?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# Stored earlier revisions of a decision file: <dir>/history/<stem>.<LF sha256><suffix>.
HISTORY_DIRECTORY = "history"
# A decision is user knowledge: decision evidence, below binary evidence (AGENTS.md precedence).
DECISION_CONFIDENCES = ("medium", "low")
SHOWN = 3


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def normalized_sha256(data: bytes) -> str:
    """The SHA-256 of ``data`` with CRLF line ends normalized to LF (the same digest on every checkout)."""

    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def revision_path(relative: str, sha256: str) -> str:
    """The repo-relative path of a decision file's stored revision ``sha256``: ``history/<stem>.<sha256><suffix>`` beside it."""

    path = PurePosixPath(relative)
    return (path.parent / HISTORY_DIRECTORY / f"{path.stem}.{sha256}{path.suffix}").as_posix()


def stored_revisions(root: Path, relative: str) -> list[dict[str, Any]]:
    """The stored revisions of a decision file: each one's path, the digest its name gives, its own digest and ``ok``."""

    path = PurePosixPath(relative)
    directory = root / path.parent / HISTORY_DIRECTORY
    pattern = re.compile(re.escape(path.stem) + r"\.(?P<sha>[0-9a-f]{64})" + re.escape(path.suffix) + "$")
    rows = []
    for entry in sorted(directory.iterdir() if directory.is_dir() else [], key=lambda value: value.name):
        if entry.is_file() and (match := pattern.match(entry.name)):
            actual = normalized_sha256(entry.read_bytes())
            rows.append({"path": revision_path(relative, match["sha"]), "sha256": match["sha"], "content_sha256": actual,
                         "ok": actual == match["sha"]})
    return rows


# -- parsing -------------------------------------------------------------------------


def parse_decisions(text: str) -> dict[str, Any]:
    """The headings of a decision file, in order, with their list lines and notes.

    A heading written twice keeps one block (its lines merged, in file
    order); ``repeated`` lists the later occurrences.  A ``# title`` line
    ends the current heading; list lines outside any heading are listed in
    ``outside``.
    """

    blocks: dict[str, dict[str, Any]] = {}
    repeated: list[dict[str, Any]] = []
    outside: list[int] = []
    current: dict[str, Any] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        if match := HEADING_RE.match(line):
            heading = match["heading"]
            if heading in blocks:
                repeated.append({"heading": heading, "line": number, "first_line": blocks[heading]["line"]})
            current = blocks.setdefault(heading, {"heading": heading, "line": number, "entries": [], "notes": []})
            continue
        if TITLE_RE.match(line):
            current = None
            continue
        if match := ITEM_RE.match(line):
            if current is None:
                outside.append(number)
                continue
            body = match["text"].strip().strip("`").strip()
            entry: dict[str, Any] = {"line": number, "text": body, "address": None, "signature": body}
            if address := ADDRESS_RE.match(body):
                entry["address"] = int(address["address"], 16)
                entry["signature"] = (address["rest"] or "").strip().strip("`").strip()
            current["entries"].append(entry)
        elif line.strip() and current is not None:
            current["notes"].append(line.strip())
    return {"headings": list(blocks.values()), "repeated": repeated, "outside": outside}


def heading_destination(root: Path, heading: str) -> dict[str, Any]:
    """Where a heading places its artifacts: the repo-relative ``src/`` path in on-disk letter case.

    ``path`` is null when the heading names no ``<module>/<file>`` with a
    source or header suffix (``error`` says why).  ``known_module`` is false
    when the module directory does not exist (the path keeps the heading's
    spelling); ``exists`` says whether the file exists.
    """

    from .source_plan import HEADER_SUFFIXES, SOURCE_FILE_SUFFIXES

    row: dict[str, Any] = {"path": None, "header": False, "source": False, "known_module": False, "exists": False}
    text = heading.strip().strip("`").strip().replace("\\", "/")
    parts = [part for part in text.split("/") if part]
    if parts and parts[0].casefold() == "src":
        parts = parts[1:]
    if len(parts) < 2 or any(part in (".", "..") or ":" in part for part in parts):
        row["error"] = "names no <module>/<file> path"
        return row
    name = parts[-1].casefold()
    row["header"] = name.endswith(HEADER_SUFFIXES)
    row["source"] = name.endswith(SOURCE_FILE_SUFFIXES)
    if not (row["header"] or row["source"]):
        row["error"] = "names no source or header file"
        return row
    source = root / "src"

    def child(directory: Path, wanted: str) -> str | None:
        if not directory.is_dir():
            return None
        return next((entry.name for entry in directory.iterdir() if entry.name.casefold() == wanted.casefold()), None)

    explicit = parts[0].casefold() == "gamez"
    if explicit:
        parts = parts[1:]
        if len(parts) < 2:
            row["error"] = "names no <module>/<file> path"
            return row
    # Another top-level src/ directory (rt, Apps) first, else a src/gamez module.
    top = None if explicit else child(source, parts[0])
    if top is not None and top.casefold() != "gamez" and (source / top).is_dir():
        spelled, directory = ["src", top], source / top
    else:
        top = child(source / "gamez", parts[0])
        if top is not None and not (source / "gamez" / top).is_dir():
            top = None
        spelled, directory = ["src", "gamez", top or parts[0]], source / "gamez" / (top or parts[0])
    row["known_module"] = top is not None
    for part in parts[1:]:
        real = child(directory, part)
        spelled.append(real or part)
        directory = directory / (real or part)
    row["path"] = "/".join(spelled)
    row["exists"] = (root / row["path"]).is_file()
    return row


# -- resolution ----------------------------------------------------------------------


class ArtifactIndex:
    """ELF artifacts by start address and by name text (ELF name and squashed readable declaration)."""

    def __init__(self, rows: Iterable[tuple[str, int, str, list[str]]]) -> None:
        self.kind: dict[str, str] = {}
        self.address: dict[str, int] = {}
        self.names: dict[str, list[str]] = {}
        self._keys: dict[str, set[str]] = {}
        self._at: dict[int, list[str]] = defaultdict(list)
        self._text: dict[str, set[str]] = defaultdict(set)
        for identity, address, kind, names in rows:
            self.kind[identity], self.address[identity], self.names[identity] = kind, address, list(names)
            self._at[address].append(identity)
            keys = self._keys.setdefault(identity, set())
            for name in names:
                keys.update((name, squash(readable(name)["declaration"])))
            for key in keys:
                self._text[key].add(identity)

    @classmethod
    def from_graph(cls, graph: dict[str, Any]) -> "ArtifactIndex":
        rows = []
        for row in graph.get("artifacts") or []:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            try:
                address = int(str(row.get("address")), 16)
            except ValueError:
                continue
            names = [str(value.get("name")) for value in row.get("names") or [] if isinstance(value, dict) and value.get("name")]
            rows.append((row["id"], address, str(row.get("kind")), names))
        return cls(rows)

    @classmethod
    def from_cache(cls, connection: sqlite3.Connection) -> "ArtifactIndex":
        names: dict[str, list[str]] = defaultdict(list)
        for identity, name in connection.execute("SELECT artifact, name FROM names ORDER BY symbol_index"):
            names[identity].append(name)
        rows = connection.execute("SELECT id, address, kind FROM artifacts ORDER BY address, id").fetchall()
        return cls((identity, address, kind, names.get(identity, [])) for identity, address, kind in rows)

    def declaration(self, identity: str) -> str | None:
        names = self.names.get(identity) or []
        return readable(names[0])["declaration"] if names else None

    def resolve(self, entry: dict[str, Any]) -> dict[str, Any]:
        """``{status, artifacts}``: ``resolved`` (one artifact), ``unmatched``, ``ambiguous`` or ``mismatch``."""

        signature = squash(entry.get("signature") or "")
        address = entry.get("address")
        if address is not None:
            found = list(self._at.get(address, []))
            if not found:
                return {"status": "unmatched", "artifacts": [], "why": f"no artifact starts at 0x{address:x}"}
            if signature:
                named = [identity for identity in found if signature in self._keys.get(identity, set())]
                if not named:
                    return {"status": "mismatch", "artifacts": found,
                            "why": f"0x{address:x} is {', '.join(filter(None, map(self.declaration, found))) or found[0]}"}
                found = named
            elif len(found) > 1:
                found = [identity for identity in found if self.kind.get(identity) == "function"] or found
        else:
            found = sorted(self._text.get(signature, set()), key=lambda identity: (self.address[identity], identity))
            if not found:
                return {"status": "unmatched", "artifacts": [], "why": "no ELF artifact has this name or declaration"}
        if len(found) > 1:
            return {"status": "ambiguous", "artifacts": found, "why": f"{len(found)} artifacts: give its address"}
        return {"status": "resolved", "artifacts": found}


# -- plan validation -----------------------------------------------------------------


class DecisionCheck:
    """The decisions an owner plan's rows cite, each file revision read once and the index built on first use.

    ``heading(decision, where, problems)`` checks one ``{file, sha256,
    heading}`` object: the file is repo-relative and exists, the cited
    LF-normalized SHA-256 is the current file's or a stored revision's
    (``revision_path``, whose content has that digest), and the heading is
    one of that revision's ``##`` headings.  It returns the heading's block
    with its ``destination`` and ``listed`` (each artifact a line under it
    resolves to, with that line), or ``None`` after adding the problems.  A
    block of an earlier revision also carries ``revision`` (``{cited,
    current}``) and ``current``, the current file's block of the heading
    (empty when it has none).

    ``placed(block, where, identities, problems)`` checks the artifacts the
    citing row or entry places from the heading: each is listed under it,
    and for an earlier revision the current heading still names the same
    destination and still lists each of them.  Then the citation holds and a
    note goes to ``notes``; otherwise each difference is a problem.
    """

    def __init__(
        self, root: Path, graph: dict[str, Any] | None = None, *, index: ArtifactIndex | None = None,
        notes: list[str] | None = None,
    ) -> None:
        self.root = root
        self.graph = graph or {}
        self.notes: list[str] = notes if notes is not None else []
        self._files: dict[str, tuple[str, dict[str, Any]] | str] = {}
        self._revisions: dict[tuple[str, str], dict[str, Any] | str] = {}
        self._index = index
        self._blocks: dict[tuple[str, str, str], dict[str, Any]] = {}

    @property
    def index(self) -> ArtifactIndex:
        if self._index is None:
            self._index = ArtifactIndex.from_graph(self.graph)
        return self._index

    def _load(self, relative: str) -> tuple[str, dict[str, Any]] | str:
        path = self.root / relative
        if not path.is_file():
            return "does not exist"
        data = path.read_bytes()
        try:
            return normalized_sha256(data), parse_decisions(data.decode("utf-8-sig"))
        except UnicodeDecodeError:
            return "is not UTF-8 text"

    def _read(self, relative: str) -> tuple[str, dict[str, Any]] | str:
        if relative not in self._files:
            self._files[relative] = self._load(relative)
        return self._files[relative]

    def _revision(self, relative: str, cited: str) -> dict[str, Any] | str:
        """The parsed stored revision ``cited`` of ``relative``, or why there is none."""

        key = (relative, cited)
        if key not in self._revisions:
            stored = revision_path(relative, cited)
            read = self._load(stored)
            if read == "does not exist":
                self._revisions[key] = f"no stored revision {stored} exists"
            elif isinstance(read, str):
                self._revisions[key] = f"its stored revision {stored} {read}"
            elif read[0] != cited:
                self._revisions[key] = f"its stored revision {stored} has LF-normalized SHA-256 {read[0]}, not its name's"
            else:
                self._revisions[key] = read[1]
        return self._revisions[key]

    def _block(self, relative: str, sha: str, parsed: dict[str, Any], heading: str) -> dict[str, Any]:
        key = (relative, sha, heading)
        if key not in self._blocks:
            block = next((row for row in parsed["headings"] if row["heading"] == heading), None)
            if block is None:
                self._blocks[key] = {}
            else:
                listed: dict[str, int] = {}
                unresolved: list[int] = []
                for entry in block["entries"]:
                    result = self.index.resolve(entry)
                    if result["status"] == "resolved":
                        listed.setdefault(result["artifacts"][0], entry["line"])
                    else:
                        unresolved.append(entry["line"])
                self._blocks[key] = {
                    **block,
                    "file": relative,
                    "sha256": sha,
                    "destination": heading_destination(self.root, heading),
                    "listed": listed,
                    "unresolved_lines": unresolved,
                }
        return self._blocks[key]

    def heading(self, decision: Any, where: str, problems: list[str]) -> dict[str, Any] | None:
        if not isinstance(decision, dict) or set(decision) != set(DECISION_FIELDS) or not all(
            isinstance(decision.get(key), str) and decision[key].strip() for key in DECISION_FIELDS
        ):
            problems.append(f"{where} decision must be an object {{{', '.join(DECISION_FIELDS)}}} of non-empty strings")
            return None
        relative, cited, heading = decision["file"], decision["sha256"], decision["heading"].strip()
        parts = relative.split("/")
        if "\\" in relative or ":" in relative or relative.startswith("/") or any(part in ("", ".", "..") for part in parts):
            problems.append(f"{where} decision file {relative!r} must be a repo-relative path")
            return None
        if not SHA_RE.match(cited):
            problems.append(f"{where} decision sha256 must be 64 lowercase hex digits")
            return None
        read = self._read(relative)
        if isinstance(read, str):
            problems.append(f"{where} decision file {relative} {read}")
            return None
        actual, parsed = read
        revision = None
        if actual == cited:
            block = self._block(relative, actual, parsed, heading)
        else:
            # An earlier revision, stored unchanged under history/ before the file was revised.
            stored = self._revision(relative, cited)
            if isinstance(stored, str):
                problems.append(
                    f"{where} decision file {relative} has LF-normalized SHA-256 {actual}, not the cited {cited}, and {stored}"
                )
                return None
            block = self._block(relative, cited, stored, heading)
            revision = {"cited": cited, "current": actual}
        if not block:
            problems.append(
                f"{where} decision heading {heading!r} is not a ## heading of {relative}"
                + (f" (revision {cited})" if revision else "")
            )
            return None
        if block["destination"]["path"] is None:
            problems.append(f"{where} decision heading {heading!r} {block['destination']['error']}")
            return None
        if revision is None:
            return block
        return {**block, "revision": revision, "current": self._block(relative, actual, parsed, heading)}

    def placed(self, block: dict[str, Any], where: str, identities: Iterable[str], problems: list[str]) -> bool:
        """Whether the cited heading lists each of ``identities`` (and, for an earlier revision, the current file still does)."""

        identities = list(identities)
        missing = [identity for identity in identities if identity not in block["listed"]]
        problems.extend(self.not_listed(block, where, identity) for identity in missing)
        revision = block.get("revision")
        if revision is None or missing:
            return not missing
        cited = f"{where} cites revision {revision['cited']} of {block['file']}; current {revision['current']}"
        current = block["current"]
        if not current:
            problems.append(f"{cited}: the current file has no heading {block['heading']!r}; amend the plan to cite it")
            return False
        if current["destination"]["path"] != block["destination"]["path"]:
            problems.append(
                f"{cited}: heading {block['heading']!r} now names {current['destination']['path']}, not "
                f"{block['destination']['path']}; amend the plan to cite the current file"
            )
            return False
        gone = [identity for identity in identities if identity not in current["listed"]]
        problems.extend(
            f"{cited}: heading {block['heading']!r} no longer lists {identity}; amend the plan to cite the current file"
            for identity in gone
        )
        if not gone:
            self.notes.append(f"{cited}; this heading's placements for the row unchanged")
        return not gone

    def not_listed(self, block: dict[str, Any], where: str, identity: str) -> str:
        text = f"{where} {identity} is not listed under heading {block['heading']!r} of {block['file']}"
        if block.get("revision"):
            text += f" (revision {block['revision']['cited']})"
        if block["unresolved_lines"]:
            lines = ", ".join(map(str, block["unresolved_lines"][:SHOWN]))
            text += f" (lines {lines} name no single artifact: source placements check --file {block['file']} lists them)"
        return text


def plan_citations(plan: Any) -> list[tuple[str, Any, list[str]]]:
    """Every decision an owner plan cites: ``(where, decision, the artifacts it places from the heading)``.

    An entry's decision places its artifact; a ``user`` row's places the
    row's artifacts whose entries cite no decision of their own (as
    ``source plan validate`` checks them, with its labels).
    """

    from .source_plan import artifact_id

    found: list[tuple[str, Any, list[str]]] = []
    owners = plan.get("owners") if isinstance(plan, dict) else None
    for number, owner in enumerate(owners if isinstance(owners, list) else [], 1):
        if not isinstance(owner, dict):
            continue
        label = f"owner {number} ({owner.get('translation_unit') or owner.get('library') or owner.get('classification')})"
        decided: set[str] = set()
        artifacts: list[str] = []
        for entry in owner.get("artifacts") or []:
            identity = artifact_id(entry)
            if identity is None:
                continue
            artifacts.append(identity)
            if isinstance(entry, dict) and "decision" in entry:
                decided.add(identity)
                found.append((f"{label} entry {identity}", entry["decision"], [identity]))
        if "decision" in owner:
            found.append((label, owner["decision"], [identity for identity in artifacts if identity not in decided]))
    return found


# -- placements check ----------------------------------------------------------------


def _owner_edges(root: Path) -> dict[str, str]:
    """Each artifact's owner file under ``src/``: its one ``defines`` edge, else its one source-file ``emits`` edge."""

    from .source import _OWNER_SOURCE_SUFFIXES, source_artifacts

    defines: dict[str, set[str]] = defaultdict(set)
    emits: dict[str, set[str]] = defaultdict(set)
    for row in source_artifacts(root)["artifacts"]:
        if not str(row["path"]).startswith("src/"):
            continue
        if row["relation"] == "defines":
            defines[row["artifact_id"]].add(row["path"])
        elif row["relation"] == "emits" and str(row["path"]).lower().endswith(_OWNER_SOURCE_SUFFIXES):
            emits[row["artifact_id"]].add(row["path"])
    owners = {}
    for identity in set(defines) | set(emits):
        paths = defines.get(identity) or emits.get(identity) or set()
        if len(paths) == 1:
            owners[identity] = next(iter(paths))
    return owners


def _plan_states(root: Path, items: set[str]) -> dict[str, dict[str, Any]]:
    """Each plan item's plan file (``path``, null when missing or unreadable) and the state of each artifact it lists.

    The state is ``unresolved`` or ``owned by <unit, library or classification>``.
    """

    from .source_plan import artifact_id, plan_path
    from .util import SocomError, load_json

    states: dict[str, dict[str, Any]] = {}
    for item in sorted(items):
        path = root / plan_path(item)
        found: dict[str, str] = {}
        states[item] = {"path": None, "artifacts": found}
        try:
            plan = load_json(path) if path.is_file() else None
        except (SocomError, UnicodeDecodeError, ValueError):
            plan = None
        if not isinstance(plan, dict):
            continue
        states[item]["path"] = plan_path(item)
        for owner in plan.get("owners") or []:
            if not isinstance(owner, dict):
                continue
            label = owner.get("translation_unit") or owner.get("library") or owner.get("classification") or "owner"
            for entry in owner.get("artifacts") or []:
                if identity := artifact_id(entry):
                    found[identity] = f"owned by {label}"
        for row in plan.get("unresolved") or []:
            if isinstance(row, dict) and isinstance(row.get("artifact"), str):
                found[row["artifact"]] = "unresolved"
    return states


def _citations(root: Path, index: ArtifactIndex, relative: str, sha256: str, items: set[str]) -> list[dict[str, Any]]:
    """Every citation of decision file ``relative`` in the plans of ``items``, checked as ``source plan validate`` checks it.

    ``revision`` is ``current`` (the current file's digest), ``stored`` (an
    earlier revision under ``history/``) or ``unknown``; ``holds`` says
    whether the citation still validates (for a stored revision: the current
    heading still names the destination and lists the row's artifacts).
    """

    from .source_plan import plan_path
    from .util import SocomError, load_json

    check = DecisionCheck(root, index=index)
    rows: list[dict[str, Any]] = []
    for item in sorted(items):
        path = root / plan_path(item)
        try:
            plan = load_json(path) if path.is_file() else None
        except (SocomError, UnicodeDecodeError, ValueError):
            plan = None
        for where, decision, identities in plan_citations(plan):
            if not isinstance(decision, dict) or decision.get("file") != relative:
                continue
            cited = decision.get("sha256")
            problems: list[str] = []
            check.notes.clear()
            block = check.heading(decision, where, problems)
            if block is not None:
                check.placed(block, where, identities, problems)
            stored = isinstance(cited, str) and SHA_RE.match(cited) and (root / revision_path(relative, cited)).is_file()
            rows.append({
                "item": item,
                "plan": plan_path(item),
                "where": where,
                "heading": decision.get("heading"),
                "sha256": cited,
                "revision": "current" if cited == sha256 else ("stored" if stored else "unknown"),
                "artifacts": identities,
                "holds": not problems,
                "notes": list(check.notes),
                "problems": problems,
            })
    return rows


def placements_report(root: Path, cache: Path, decision_file: Path) -> dict[str, Any]:
    """Check one decision file against the ELF artifacts, the plans and the ``src/`` owners (read-only)."""

    data = decision_file.read_bytes()
    try:
        parsed = parse_decisions(data.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        from .util import SocomError

        raise SocomError(f"{decision_file} is not UTF-8 text") from exc
    try:
        shown_file, inside = decision_file.resolve().relative_to(root.resolve()).as_posix(), True
    except ValueError:
        shown_file, inside = str(decision_file), False
    with closing(sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True)) as connection:
        index = ArtifactIndex.from_cache(connection)
        artifacts = {
            identity: {"end": end, "item": item, "cluster": cluster}
            for identity, end, item, cluster in connection.execute('SELECT id, "end", item, cluster FROM artifacts')
        }
        clusters = {
            identity: [value for value in (units or "").split(",") + (libraries or "").split(",") if value]
            for identity, units, libraries in connection.execute("SELECT id, units, libraries FROM clusters")
        }
        candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for identity, unit, strength in connection.execute(
            "SELECT artifact, tu, strength FROM tu_candidates WHERE strength IN ('strong', 'medium') ORDER BY artifact, rank"
        ):
            candidates[identity].append((unit, strength))
        graph_units = {str(unit).casefold() for (unit,) in connection.execute("SELECT tu FROM units")}
        plan_items = {str(item) for (item,) in connection.execute("SELECT DISTINCT item FROM artifacts WHERE item IS NOT NULL")}

    def brief(identity: str) -> dict[str, Any]:
        return {"id": identity, "address": f"0x{index.address[identity]:x}", "declaration": index.declaration(identity)}

    seen: dict[str, dict[str, Any]] = {}
    unmatched, ambiguous, mismatched, duplicates = [], [], [], []
    destinations = []
    for block in parsed["headings"]:
        destination = heading_destination(root, block["heading"])
        row: dict[str, Any] = {
            "heading": block["heading"],
            "line": block["line"],
            **{key: destination.get(key) for key in ("path", "exists", "header", "known_module")},
            "new": destination["path"] is not None and not destination["exists"],
            "known_unit": destination["path"] is not None and destination["path"].rsplit("/", 1)[-1].casefold() in graph_units,
            "notes": block["notes"],
            "artifacts": [],
        }
        if destination.get("error"):
            row["error"] = destination["error"]
        for entry in block["entries"]:
            result = index.resolve(entry)
            where = {"line": entry["line"], "heading": block["heading"], "text": entry["text"]}
            if result["status"] == "unmatched":
                unmatched.append({**where, "why": result["why"]})
            elif result["status"] == "ambiguous":
                ambiguous.append({**where, "artifacts": [brief(identity) for identity in result["artifacts"]]})
            elif result["status"] == "mismatch":
                mismatched.append({**where, "why": result["why"]})
            else:
                identity = result["artifacts"][0]
                if identity in seen:
                    first = seen[identity]
                    duplicates.append({**where, "artifact": identity, "first_line": first["line"], "first_heading": first["heading"]})
                    continue
                seen[identity] = where
                row["artifacts"].append({"line": entry["line"], **brief(identity), "kind": index.kind[identity],
                                         "item": artifacts[identity]["item"]})
        destinations.append(row)

    # Stage 4 plan items and each placed artifact's state in its item's plan.
    states = _plan_states(root, {row["item"] for destination in destinations for row in destination["artifacts"] if row["item"]})
    by_item: dict[str, dict[str, Any]] = {}
    for destination in destinations:
        items: dict[str, int] = defaultdict(int)
        for row in destination["artifacts"]:
            item = row["item"]
            if item is None:
                row["plan"] = "in no plan slice"
                continue
            items[item] += 1
            state = states[item]
            row["plan"] = state["artifacts"].get(row["id"]) or ("not listed by its plan" if state["path"] else "plan file missing or unreadable")
            entry = by_item.setdefault(item, {"item": item, "plan": state["path"], "artifacts": 0, "destinations": []})
            entry["artifacts"] += 1
            where = destination["path"] or destination["heading"]
            if where not in entry["destinations"]:
                entry["destinations"].append(where)
        destination["items"] = [{"item": item, "artifacts": count} for item, count in sorted(items.items())]
        destination["placed"] = len(destination["artifacts"])

    # Contiguity: the src/ owners with the placements laid over them (a header placement owns nothing).
    owners = _owner_edges(root)
    reassigned = []
    for destination in destinations:
        for row in destination["artifacts"]:
            before = owners.get(row["id"])
            if destination["header"]:
                owners.pop(row["id"], None)
            elif destination["path"]:
                owners[row["id"]] = destination["path"]
            if before and destination["path"] and before.casefold() != destination["path"].casefold():
                reassigned.append({"id": row["id"], "from": before, "to": destination["path"]})
    functions = sorted((index.address[identity], identity) for identity, kind in index.kind.items() if kind == "function")
    conflicted = 0
    for destination in destinations:
        destination["conflicts"], destination["unowned_inside"] = [], []
        path = destination["path"]
        if not path or not destination["artifacts"] or destination["header"]:
            continue
        mine = [address for address, identity in functions if (owners.get(identity) or "").casefold() == path.casefold()]
        if not mine:
            continue
        low, high = min(mine), max(mine)
        destination["run"] = [f"0x{low:x}", f"0x{high:x}"]
        for address, identity in functions:
            if not low < address < high:
                continue
            owner = owners.get(identity)
            if owner is None:
                destination["unowned_inside"].append(brief(identity))
            elif owner.casefold() != path.casefold():
                destination["conflicts"].append({**brief(identity), "owner": owner})
        conflicted += bool(destination["conflicts"])

    # A file the graph does not know is a user-named unit (name_basis user): the ELF may still name another.
    objections = 0
    for destination in destinations:
        destination["elf_objections"] = []
        if not destination["path"] or destination["header"] or destination["known_unit"]:
            continue
        for row in destination["artifacts"]:
            reasons = []
            cluster = artifacts[row["id"]]["cluster"]
            if cluster and clusters.get(cluster):
                reasons.append(f"cluster {cluster} names {', '.join(clusters[cluster])}")
            if candidates.get(row["id"]):
                unit, strength = candidates[row["id"]][0]
                reasons.append(f"{strength} unit candidate {unit}")
            if reasons:
                destination["elf_objections"].append({"id": row["id"], "address": row["address"], "why": "; ".join(reasons)})
        objections += len(destination["elf_objections"])

    # The stored earlier revisions of the file and every plan citation of it (a revision it cites, whether it holds).
    sha256 = normalized_sha256(data)
    revisions = stored_revisions(root, shown_file) if inside else []
    citations = _citations(root, index, shown_file, sha256, plan_items) if inside else []

    invalid = [{"heading": row["heading"], "line": row["line"], "error": row["error"]} for row in destinations if row.get("error")]
    placed = sum(row["placed"] for row in destinations)
    summary = {
        "headings": len(destinations),
        "destinations": sum(1 for row in destinations if row["path"] and row["placed"]),
        "new_files": sum(1 for row in destinations if row["new"] and row["placed"]),
        "lines": sum(len(block["entries"]) for block in parsed["headings"]),
        "placed": placed,
        "placed_unresolved": sum(1 for row in destinations for entry in row["artifacts"] if entry.get("plan") == "unresolved"),
        "unmatched": len(unmatched),
        "ambiguous": len(ambiguous),
        "mismatched": len(mismatched),
        "duplicates": len(duplicates),
        "outside_heading": len(parsed["outside"]),
        "invalid_headings": len(invalid),
        "contiguity_conflicts": sum(len(row["conflicts"]) for row in destinations),
        "destinations_with_conflicts": conflicted,
        "elf_objections": objections,
        "reassigned": len(reassigned),
        "plan_items": len(by_item),
        "stored_revisions": len(revisions),
        "bad_revisions": sum(1 for row in revisions if not row["ok"]),
        "citations": len(citations),
        "citing_plans": len({row["item"] for row in citations}),
        "citations_current": sum(1 for row in citations if row["revision"] == "current" and row["holds"]),
        "citations_on_revision": sum(1 for row in citations if row["revision"] != "current" and row["holds"]),
        "broken_citations": sum(1 for row in citations if not row["holds"]),
    }
    failures = ("unmatched", "ambiguous", "mismatched", "duplicates", "outside_heading", "invalid_headings",
                "contiguity_conflicts", "elf_objections", "bad_revisions", "broken_citations")
    return {
        "ok": not any(summary[key] for key in failures),
        "mutation_performed": False,
        "file": shown_file,
        "sha256": sha256,
        "summary": summary,
        "destinations": destinations,
        "items": sorted(by_item.values(), key=lambda row: row["item"]),
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "mismatched": mismatched,
        "duplicates": duplicates,
        "outside_heading": parsed["outside"],
        "repeated_headings": parsed["repeated"],
        "invalid_headings": invalid,
        "reassigned": reassigned,
        "revisions": revisions,
        "citations": citations,
    }


def report_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"{report['file']} (LF sha256 {report['sha256']}): placed {summary['placed']} artifacts from {summary['lines']} lines "
        f"under {summary['headings']} headings; {summary['placed_unresolved']} unresolved in their plans; "
        f"{summary['destinations']} destinations ({summary['new_files']} new), {summary['plan_items']} plan items",
    ]
    for row in report["destinations"]:
        if not row["placed"] and not row.get("error"):
            continue
        state = "header" if row["header"] else ("NEW" if row["new"] else "existing")
        flags = [state] + ([] if row["known_module"] else ["module folder not found"])
        items = ", ".join(f"{entry['item'].removeprefix('socom:work:')}" + (f" x{entry['artifacts']}" if entry["artifacts"] > 1 else "")
                          for entry in row.get("items") or [])
        lines.append(f"  {row['placed']:3}  {row['path'] or row['heading']}  [{'; '.join(flags)}]" + (f"  {items}" if items else ""))
        if row.get("error"):
            lines.append(f"        INVALID heading (line {row['line']}): {row['error']}")
        for conflict in row["conflicts"][:SHOWN]:
            lines.append(f"        CONFLICT: {conflict['owner']}'s {conflict['declaration']} at {conflict['address']} lies inside this file's run")
        if len(row["conflicts"]) > SHOWN:
            lines.append(f"        ... {len(row['conflicts']) - SHOWN} more conflicts (--json lists all)")
        for objection in row["elf_objections"][:SHOWN]:
            lines.append(f"        ELF: {objection['address']} {objection['why']}")
        if len(row["elf_objections"]) > SHOWN:
            lines.append(f"        ... {len(row['elf_objections']) - SHOWN} more ELF objections (--json lists all)")
    for key, title in (("unmatched", "unmatched"), ("ambiguous", "ambiguous"), ("mismatched", "mismatched"), ("duplicates", "duplicate")):
        lines.append(f"{title} lines: {len(report[key])}")
        for row in report[key]:
            why = row.get("why") or (f"also line {row['first_line']} ({row['first_heading']})" if key == "duplicates" else
                                     ", ".join(value["address"] for value in row.get("artifacts", [])))
            lines.append(f"  line {row['line']} ({row['heading']}): {row['text']}  ->  {why}")
    if report["outside_heading"]:
        lines.append(f"list lines outside a heading: {', '.join(map(str, report['outside_heading']))}")
    for row in report["repeated_headings"]:
        lines.append(f"heading {row['heading']!r} repeated at line {row['line']} (first at {row['first_line']}; merged)")
    if report["reassigned"]:
        lines.append(f"placements that move an annotated artifact: {len(report['reassigned'])}")
        lines.extend(f"  {row['id']}: {row['from']} -> {row['to']}" for row in report["reassigned"][:SHOWN])
    for row in report["revisions"]:
        if not row["ok"]:
            lines.append(f"stored revision {row['path']} has LF-normalized SHA-256 {row['content_sha256']}, not its name's")
    if report["citations"]:
        lines.append(
            f"plan citations: {summary['citations']} in {summary['citing_plans']} plans; {summary['citations_current']} of "
            f"the current file, {summary['citations_on_revision']} of a stored earlier revision that still hold, "
            f"{summary['broken_citations']} broken"
        )
        older: dict[str, set[str]] = defaultdict(set)
        for row in report["citations"]:
            if row["revision"] != "current" and row["holds"]:
                older[row["sha256"]].add(row["item"].removeprefix("socom:work:"))
        for sha, items in sorted(older.items()):
            lines.append(f"  revision {sha} (placements unchanged): {', '.join(sorted(items))}")
        for row in report["citations"]:
            for problem in row["problems"][:SHOWN]:
                lines.append(f"  BROKEN {row['item'].removeprefix('socom:work:')}: {problem}")
    lines.append("ok" if report["ok"] else "NOT OK")
    return "\n".join(lines)


# -- CLI -----------------------------------------------------------------------------


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "source placements check",
            "source",
            "Check a user placement decision file (## <module>/<file> headings, [0xADDR] <declaration> lines) read-only: "
            "every line resolved to exactly one ELF artifact by address or readable declaration, unmatched, ambiguous, "
            "mismatched and duplicate lines, each heading's src/ path in on-disk letter case (new or existing, header), "
            "the stage 4 plan items and plan state of its artifacts, the contiguity of each source file's functions "
            "(its src/ owners plus the placed ones, no function another file owns in between) and, for a file the graph "
            "does not know, clusters or strong/medium unit candidates naming another unit; the file's stored earlier "
            "revisions (history/<stem>.<sha256><suffix>, each named by its content's digest) and every plan citation of "
            "the file with the revision it cites and whether it still holds (a stored revision's: the current heading "
            "names the same destination and lists the citing row's artifacts).",
        ),
    )


def register(source_commands: Any) -> None:
    from .source_plan_cli import DEFAULT_GRAPH

    placements = source_commands.add_parser("placements")
    commands = placements.add_subparsers(dest="source_placements_command", required=True)
    check = commands.add_parser("check")
    check.add_argument("--file", required=True, help="the decision file (Markdown)")
    check.add_argument("--graph", default=DEFAULT_GRAPH)
    check.set_defaults(handler=_source_placements_check)


def _source_placements_check(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .source_cache import ensure_source_cache
    from .util import SocomError, atomic_write_json

    root = _root(arguments)
    decision_file = Path(arguments.file)
    if not decision_file.is_absolute():
        decision_file = root / decision_file
    if not decision_file.is_file():
        raise SocomError(f"decision file {arguments.file} does not exist")
    graph_path = Path(arguments.graph)
    if not graph_path.is_absolute():
        graph_path = root / graph_path
    if not graph_path.is_file():
        # The graph JSON is disposable build output, written once as `source sql` does.
        from .source_graph import source_graph

        atomic_write_json(_build_path(root, arguments.graph, "source graphs"), source_graph(root))
    cache, rebuilt = ensure_source_cache(root, graph_path=graph_path)
    report = placements_report(root, cache, decision_file)
    report["cache"] = cache.relative_to(root).as_posix()
    report["rebuilt"] = rebuilt
    if arguments.json:
        _emit(report)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(report_text(report))
    return 0 if report["ok"] else 1
