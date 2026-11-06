"""``source owner``: one artifact's source owner, or why it is undecided (read-only).

An artifact is looked up by its ID (``socom:function:0x23d8c0``), an address
(``0x23d8c0``; an address inside an artifact finds that artifact), an ELF
symbol name or a readable (demangled) name or substring
(``zrdr_findint``, ``CAiSRescued::CanScan``).  Several matches are listed
briefly; full detail is shown for a single match, for the only exact match
among several, or for every match with ``--all``.

The detail gathers, changing nothing outside ``build/``:

* identity from the source graph cache (``source sql``'s
  ``build/cache/source-graph.sqlite``, rebuilt when its inputs change):
  kind, range, section, every ELF name with its binding and readable
  declaration (``mw_mangle``), classification, library, inline/weak flags;
* the ``@socom-artifact defines|emits`` annotations under ``src/`` and
  ``include/`` (one ``defines`` owner, ``emits`` headers);
* every stage 4 owner plan (``build/source-plans``) that lists it: its owner
  row and entry, or its ``unresolved`` reason, its contradictions, header
  emits and the notes that cite it, and whether the plan file's SHA-256 is
  one the tracker cites for its item (``cited_plan``'s rule: plans are
  disposable build output and may be missing or changed);
* the gate deferral in force that covers it (``effective_deferrals``);
* its unit candidates and signals from the cache;
* the stage 5 skeleton fences that hold its code: a fence naming one of its
  ELF names, or, in a fence no ELF symbol names, the same qualified name
  with another signature (provisional code held under the provisional
  spelling), whether the file is a module ``*_holding.cpp`` file, the
  ``held from`` origin, and every ``#if 0`` around the entry; for a member,
  the header region that declares its class.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from contextlib import closing
from functools import lru_cache
from pathlib import Path
from typing import Any

from .mw_mangle import MangleError, mangle_qualified, render_component
from .mw_mangle import demangle as mw_demangle

ID_RE = re.compile(r"^socom:(function|data|gap):0x([0-9a-fA-F]+)$")
ADDRESS_RE = re.compile(r"^0x([0-9a-fA-F]+)$")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FENCE_RE = re.compile(r"^(?P<indent>[ \t]*)/\* @socom-skeleton (?P<kind>body|stub) (?P<name>\S+) \*/")
DECL_RE = re.compile(r"/\* @socom-skeleton decl (?P<name>\S+) \*/")
HELD_RE = re.compile(r"/\* held from (?P<path>\S+?):(?P<line>\d+) \*/")
DIRECTIVE_RE = re.compile(r"^\s*#\s*(?P<directive>ifdef|ifndef|if|elif|else|endif)\b(?P<rest>.*)$")
ZERO_RE = re.compile(r"^(?:0|false)\b\s*")
SHA_RE = re.compile(r"sha256:([0-9a-f]{64})")
HOLDING_SUFFIX = "_holding.cpp"
ARTIFACT_COLUMNS = (
    "id", "kind", "address", "end", "size", "name", "section", "input_section", "classification", "library",
    "class_weak", "class_evidence", "weak", "inline", "common", "emitted_from_header", "segment", "item",
)
SHOWN = 8


def specs(spec: Any) -> tuple[Any, ...]:
    """Registry rows, built with the main CLI's ``_spec``."""

    return (
        spec(
            "source owner",
            "source",
            "Look up one artifact by ID, address, ELF name or readable name and show its source owner or why it is "
            "undecided: identity, names and readable declaration, classification, its @socom-artifact annotations, "
            "each stage 4 plan that lists it (owner row, unresolved reason, contradictions, header emits; whether the "
            "plan file is one the tracker cites), its gate deferral, cache candidates and signals, and the stage 5 "
            "skeleton fences that hold its code (holding files, #if 0); several matches are listed briefly.",
        ),
    )


def register(source_commands: Any) -> None:
    from .source_plan_cli import DEFAULT_GRAPH

    owner = source_commands.add_parser("owner")
    owner.add_argument("query", help="artifact ID, 0x address, ELF symbol name, or readable name / substring")
    owner.add_argument("--all", action="store_true", help="full detail for every match (up to --limit)")
    owner.add_argument("--limit", type=int, default=25, help="matches to list (default 25)")
    owner.add_argument("--graph", default=DEFAULT_GRAPH)
    owner.set_defaults(handler=_source_owner)


# -- names ---------------------------------------------------------------------------


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


@lru_cache(maxsize=None)
def readable(name: str) -> dict[str, Any]:
    """A name's demangled kind, declaration and qualified forms.

    ``qualified`` is ``scope::name`` as rendered; ``key`` drops unnamed
    namespaces (a provisional definition may sit outside the file's
    ``@unnamed@`` namespace) and ``base`` is the mangled name text a fence
    of the same function or datum must contain.
    """

    row = mw_demangle(name)
    kind = row.get("kind")
    rendered = row.get("rendered") or {}
    structured = row.get("structured") or {}
    if kind in ("function", "data"):
        scope = rendered.get("scope")
        qualified = f"{scope}::{rendered['name']}" if scope else rendered["name"]
        named_scope = [render_component(part) for part in structured.get("scope") or [] if "unnamed" not in part]
        return {
            "kind": kind,
            "declaration": rendered["declaration"],
            "qualified": qualified,
            "key": "::".join([*named_scope, rendered["name"]]),
            "base": (structured.get("name") or {}).get("text"),
            "class_region": _class_region(structured.get("scope")),
        }
    if kind == "c_name":
        return {"kind": kind, "declaration": name, "qualified": name, "key": name, "base": name, "class_region": None}
    text = rendered.get("text") or name
    return {"kind": kind, "declaration": text, "qualified": text, "key": None, "base": None, "class_region": None}


def _class_region(scope: Any) -> str | None:
    """The mangled qualified name a header's ``decl`` region uses for a member's class."""

    if not scope or any("unnamed" in part or "local" in part for part in scope):
        return None
    try:
        return mangle_qualified(scope)
    except MangleError:
        return None


def _name_match(query: str, name: str, folded: bool) -> str | None:
    """``exact`` or ``substring`` when ``query`` names ``name``, else ``None``."""

    forms = readable(name)
    wanted = _squash(query)
    whole = [name, _squash(forms["declaration"]), _squash(forms["qualified"]), _squash(forms["key"] or "")]
    if folded:
        wanted = wanted.casefold()
        whole = [value.casefold() for value in whole]
    if wanted in whole:
        return "exact"
    if wanted in whole[0] or wanted in whole[1]:
        return "substring"
    return None


# -- lookup --------------------------------------------------------------------------


def _artifact(connection: sqlite3.Connection, identity: str) -> dict[str, Any] | None:
    columns = ", ".join(f'"{column}"' for column in ARTIFACT_COLUMNS)
    row = connection.execute(f"SELECT {columns} FROM artifacts WHERE id = ?", (identity,)).fetchone()
    return dict(zip(ARTIFACT_COLUMNS, row)) if row else None


def find_matches(connection: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    """Artifacts the query names, exact matches first, then by address."""

    text = query.strip()
    found: dict[str, dict[str, Any]] = {}
    if match := ID_RE.match(text):
        identity = f"socom:{match[1]}:0x{int(match[2], 16):x}"
        if _artifact(connection, identity):
            found[identity] = {"id": identity, "how": "id", "exact": True}
    elif match := ADDRESS_RE.match(text):
        value = int(match[1], 16)
        rows = connection.execute("SELECT id FROM artifacts WHERE address = ?", (value,)).fetchall()
        how = "address"
        if not rows:
            rows = connection.execute('SELECT id FROM artifacts WHERE address <= ? AND "end" > ?', (value, value)).fetchall()
            how = "contains"
        for (identity,) in rows:
            found[identity] = {"id": identity, "how": how, "exact": True}
    else:
        tokens = sorted({token.casefold() for token in TOKEN_RE.findall(text)}, key=len, reverse=True)
        names = connection.execute("SELECT artifact, name FROM names ORDER BY symbol_index").fetchall()
        candidates = [row for row in names if all(token in row[1].casefold() for token in tokens)] if tokens else []
        # Readable spellings (operator=, const, (anonymous namespace)) are not in the mangled text.
        for pool in (candidates, names) if candidates else (names,):
            for folded in (False, True):
                for identity, name in pool:
                    how = _name_match(text, name, folded)
                    if how is None:
                        continue
                    best = found.get(identity)
                    if best is None or (how == "exact" and not best["exact"]):
                        found[identity] = {"id": identity, "how": "name" if how == "exact" else "substring",
                                           "name": name, "exact": how == "exact"}
                if found:
                    break
            if found:
                break
        key = readable(text)["key"]
        if not found and key and key != text:
            # A mangled name no ELF symbol has (a holding fence's provisional spelling): the same qualified name.
            for identity, name in names:
                if readable(name)["key"] == key and identity not in found:
                    found[identity] = {"id": identity, "how": "same-name", "name": name, "exact": False}
    rows = []
    for row in found.values():
        artifact = _artifact(connection, row["id"]) or {}
        primary = row.get("name") or artifact.get("name")
        rows.append(
            {
                **row,
                "kind": artifact.get("kind"),
                "address": f"0x{artifact['address']:x}" if artifact.get("address") is not None else None,
                "name": primary,
                "declaration": readable(primary)["declaration"] if primary else None,
                "classification": artifact.get("classification"),
                "item": artifact.get("item"),
                "_address": artifact.get("address") or 0,
            }
        )
    rows.sort(key=lambda row: (not row["exact"], row["_address"], row["id"]))
    for row in rows:
        row.pop("_address")
    return rows


# -- plans ---------------------------------------------------------------------------


def plan_records(root: Path, tracker: dict[str, Any]) -> list[dict[str, Any]]:
    """Every stage 4 plan item with its plan file, read once: present, missing or changed since the tracker cited it."""

    from .source_plan import SOURCE_PLAN_KINDS, plan_path
    from .util import SocomError, load_json, sha256_file

    items = {row.get("id"): row for row in tracker.get("work_items", []) if isinstance(row, dict)}
    records = []
    for identity in sorted(key for key, row in items.items() if isinstance(key, str) and row.get("kind") in SOURCE_PLAN_KINDS):
        item = items[identity]
        relative = plan_path(identity)
        path = root / relative
        cited = [
            text
            for text in list(item.get("evidence") or []) + list((item.get("handoff") or {}).get("evidence") or [])
            if isinstance(text, str)
        ]
        recorded = sorted({sha for text in cited if relative in text or "plan sha256:" in text for sha in SHA_RE.findall(text)})
        record: dict[str, Any] = {
            "item": identity,
            "kind": item.get("kind"),
            "status": item.get("status"),
            "path": relative,
            "file": "missing",
            "sha256": None,
            "recorded_sha256": recorded,
            "plan": None,
        }
        apply = items.get(f"{identity}-apply")
        if isinstance(apply, dict):
            applied = (apply.get("source_apply") or {}).get("plan_sha256")
            record["apply"] = {"item": apply.get("id"), "status": apply.get("status"), "plan_sha256": applied}
        if path.is_file():
            sha = sha256_file(path)
            record["sha256"] = sha
            # cited_plan's rule: the file is the reviewed plan when the item's evidence cites its digest.
            record["file"] = "unchanged" if any(sha in text for text in cited) else "changed"
            if "apply" in record and record["apply"]["plan_sha256"]:
                record["apply"]["plan_matches"] = record["apply"]["plan_sha256"] == sha
            try:
                plan = load_json(path)
            except (SocomError, UnicodeDecodeError) as exc:  # a broken disposable file is reported, not fatal
                record["file"], record["error"] = "unreadable", str(exc)
            else:
                record["plan"] = plan if isinstance(plan, dict) else None
        records.append(record)
    return records


def _mentions(identity: str) -> re.Pattern[str]:
    return re.compile(re.escape(identity) + r"(?![0-9a-fA-F])")


def plan_findings(records: list[dict[str, Any]], identity: str, scope_item: str | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(plans that list or scope the artifact, plans that could not be read: the scope's first).

    A plan that is missing or unreadable may list the artifact too; only its
    item is known.
    """

    from .source_plan import artifact_id

    cited = _mentions(identity)
    found, unread = [], []
    for record in records:
        plan = record["plan"]
        if plan is None:
            unread.append(
                {key: record.get(key) for key in ("item", "status", "path", "file", "error") if record.get(key) is not None}
                | {"in_scope": record["item"] == scope_item}
            )
            continue
        row: dict[str, Any] = {key: value for key, value in record.items() if key != "plan"}
        row["in_scope"] = record["item"] == scope_item
        listed = False
        for owner in plan.get("owners") or []:
            if not isinstance(owner, dict):
                continue
            for entry in owner.get("artifacts") or []:
                if artifact_id(entry) == identity:
                    row["owner"] = {key: value for key, value in owner.items() if key != "artifacts"}
                    row["owner"]["entry"] = {key: value for key, value in entry.items() if key != "artifact"} if isinstance(entry, dict) else {}
                    listed = True
        for key in ("unresolved", "contradictions", "header_emits", "annotations"):
            rows = [
                {name: value for name, value in item.items() if name != "artifact"}
                for item in plan.get(key) or []
                if isinstance(item, dict) and item.get("artifact") == identity
            ]
            if rows:
                row[key] = rows[0] if key == "unresolved" else rows
                listed = listed or key == "unresolved"
        notes = [text for text in plan.get("notes") or [] if isinstance(text, str) and cited.search(text)]
        if notes:
            row["notes"] = notes
        reason = ((plan.get("draft") or {}).get("open_header_emit_reasons") or {}).get(identity)
        if reason:
            row["open_header_emit_reason"] = reason
        row["lists"] = listed
        if listed or row["in_scope"] or any(key in row for key in ("contradictions", "header_emits", "annotations", "notes")):
            found.append(row)
    found.sort(key=lambda row: (not row["in_scope"], not row["lists"], row["item"]))
    unread.sort(key=lambda row: (not row["in_scope"], row["item"]))
    return found, unread


# -- source --------------------------------------------------------------------------


def _directive_comment(rest: str) -> str | None:
    text = ZERO_RE.sub("", rest.strip(), count=1).strip()
    text = text.removeprefix("//").removeprefix("/*").removesuffix("*/").strip()
    return text or None


def if0_regions(lines: list[str]) -> list[dict[str, Any]]:
    """Every ``#if 0`` (or ``#if false``) region: its first line, the line that ends it and its comment."""

    stack: list[list[Any]] = []
    regions = []
    for number, line in enumerate(lines, 1):
        match = DIRECTIVE_RE.match(line)
        if not match:
            continue
        directive, rest = match["directive"], match["rest"]
        if directive in ("if", "ifdef", "ifndef"):
            zero = directive == "if" and ZERO_RE.match(rest.strip()) is not None
            stack.append([number, zero, _directive_comment(rest) if zero else None])
        elif directive in ("elif", "else"):
            if stack and stack[-1][1]:
                regions.append({"line": stack[-1][0], "end_line": number, "comment": stack[-1][2]})
                stack[-1][1] = False
        elif stack:
            start, zero, comment = stack.pop()
            if zero:
                regions.append({"line": start, "end_line": number, "comment": comment})
    regions.extend({"line": start, "end_line": len(lines), "comment": comment} for start, zero, comment in stack if zero)
    return sorted(regions, key=lambda row: row["line"])


def code_locations(root: Path, names: list[str], known: Any) -> dict[str, Any]:
    """The skeleton fences under ``src/`` that hold an artifact with these ELF names, and its class's ``decl`` regions.

    ``known(name)`` says whether a name is an ELF symbol: a fence that names
    another ELF symbol belongs to that artifact, so only fences no ELF symbol
    names can hold this one's code under another signature.
    """

    from .source import annotation_files

    exact = set(names)
    forms = [readable(name) for name in names]
    keys = {row["key"] for row in forms if row["key"]}
    bases = {row["base"] for row in forms if row["base"]}
    regions = {row["class_region"] for row in forms if row["class_region"]}
    fences, declarations = [], []
    for path in annotation_files(root):
        relative = path.relative_to(root).as_posix()
        if not relative.startswith("src/"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "@socom-skeleton" not in text:
            continue
        lines = text.splitlines()
        tops = [number for number, line in enumerate(lines, 1) if (fence := FENCE_RE.match(line)) and not fence["indent"]]
        regions_if0: list[dict[str, Any]] | None = None
        for number, line in enumerate(lines, 1):
            if "@socom-skeleton" not in line:
                continue
            fence = FENCE_RE.match(line)
            if fence is None:
                declared = DECL_RE.search(line)
                if declared and declared["name"] in regions:
                    declarations.append({"path": relative, "line": number, "region": declared["name"]})
                continue
            name = fence["name"]
            if name in exact:
                how = "exact"
            elif any(base in name for base in bases) and readable(name)["key"] in keys and not known(name):
                how = "other-signature"
            else:
                continue
            following = next((value for value in tops if value > number), len(lines) + 1) - 1
            row: dict[str, Any] = {
                "path": relative,
                "line": number,
                "kind": fence["kind"],
                "name": name,
                "match": how,
                "holding": relative.endswith(HOLDING_SUFFIX),
                "nested": bool(fence["indent"]),
            }
            held = HELD_RE.search(lines[number]) if number < len(lines) else None
            if held:
                row["held_from"] = f"{held['path']}:{held['line']}"
            if regions_if0 is None:
                regions_if0 = if0_regions(lines)
            around = [
                {**region, "encloses_fence": region["line"] < number <= region["end_line"]}
                for region in regions_if0
                if region["line"] < number <= region["end_line"] or number < region["line"] <= following
            ]
            if around:
                row["if0"] = around
            fences.append(row)
    fences.sort(key=lambda row: (row["match"] != "exact", row["path"], row["line"]))
    return {"fences": fences, "declarations": declarations}


def _owner_label(owner: dict[str, Any]) -> str:
    if owner.get("translation_unit"):
        where = owner.get("workspace_path")
        return f"{owner['translation_unit']} -> {where}" if where else str(owner["translation_unit"])
    if owner.get("classification") == "provider":
        member = owner.get("archive_member") or {}
        parts = [owner.get("library"), member.get("archive"), member.get("object")]
        if member.get("gnu_object"):
            parts.append(f"GNU object {member['gnu_object']}")
        return "provider " + " ".join(str(part) for part in parts if part)
    return str(owner.get("classification") or "owner row")


def verdict(annotations: list[dict[str, Any]], plans: list[dict[str, Any]], deferrals: list[dict[str, Any]]) -> dict[str, Any]:
    """The owner the source records, else what the plans say: annotated, planned, unresolved or unplanned."""

    from .source import _OWNER_SOURCE_SUFFIXES

    defines = [row for row in annotations if row["relation"] == "defines"]
    edges = defines or [row for row in annotations if row["relation"] == "emits" and row["path"].lower().endswith(_OWNER_SOURCE_SUFFIXES)]
    owned = [row for row in plans if row.get("owner")]
    unresolved = [row for row in plans if row.get("unresolved")]
    if len(edges) == 1:
        relation = "defines" if defines else "emits"
        return {"status": "annotated", "path": edges[0]["path"], "summary": f"{edges[0]['path']} ({relation} annotation)"}
    if len(edges) > 1:
        paths = ", ".join(row["path"] for row in edges)
        return {"status": "conflict", "path": None, "summary": f"{len(edges)} defining edges: {paths}"}
    if owned:
        owner = owned[0]["owner"]
        return {
            "status": "planned",
            "path": owner.get("workspace_path"),
            "summary": f"{_owner_label(owner)} per {owned[0]['item']}, no defines annotation",
        }
    if unresolved:
        deferred = f"; deferred ({', '.join(row['id'] for row in deferrals)})" if deferrals else ""
        return {"status": "unresolved", "path": None, "summary": f"undecided: unresolved in {unresolved[0]['item']}{deferred}"}
    return {"status": "unplanned", "path": None, "summary": "undecided: no owner plan lists it"}


# -- report --------------------------------------------------------------------------


class _Lookup:
    """Everything one invocation reads, each source loaded once."""

    def __init__(self, root: Path, connection: sqlite3.Connection) -> None:
        self.root = root
        self.connection = connection
        self._tracker: dict[str, Any] | None = None
        self._plans: list[dict[str, Any]] | None = None
        self._annotations: list[dict[str, Any]] | None = None
        self._deferrals: list[dict[str, Any]] | None = None
        self.problems: list[str] = []

    @property
    def tracker(self) -> dict[str, Any]:
        if self._tracker is None:
            from .constants import tracker_path
            from .tracker import load_tracker

            path = tracker_path(self.root)
            if path.is_file():
                self._tracker = load_tracker(path)
            else:
                self._tracker = {}
                self.problems.append("the tracker is missing: no plan status or deferral is known")
        return self._tracker

    @property
    def plans(self) -> list[dict[str, Any]]:
        if self._plans is None:
            self._plans = plan_records(self.root, self.tracker)
        return self._plans

    @property
    def annotations(self) -> list[dict[str, Any]]:
        if self._annotations is None:
            from .source import source_artifacts

            self._annotations = source_artifacts(self.root)["artifacts"]
        return self._annotations

    @property
    def deferrals(self) -> list[dict[str, Any]]:
        if self._deferrals is None:
            from .source_amend import effective_deferrals

            self._deferrals, problems = effective_deferrals(self.tracker)
            self.problems.extend(problems)
        return self._deferrals

    def known(self, name: str) -> bool:
        return self.connection.execute("SELECT 1 FROM names WHERE name = ? LIMIT 1", (name,)).fetchone() is not None

    def detail(self, identity: str) -> dict[str, Any]:
        artifact = _artifact(self.connection, identity)
        if artifact is None:
            raise KeyError(identity)
        names = [
            {"name": name, "binding": binding, "symbol_index": index, "kind": readable(name)["kind"], "declaration": readable(name)["declaration"]}
            for name, binding, index in self.connection.execute(
                "SELECT name, binding, symbol_index FROM names WHERE artifact = ? ORDER BY symbol_index", (identity,)
            )
        ]
        candidates = [
            {"rank": rank, "tu": tu, "strength": strength, "via": via.split(",") if via else [], "sinit_order": order}
            for rank, tu, strength, via, order in self.connection.execute(
                "SELECT rank, tu, strength, via, sinit_order FROM tu_candidates WHERE artifact = ? ORDER BY rank", (identity,)
            )
        ]
        signals = [
            {key: value for key, value in (("signal", signal), ("strength", strength), ("tu", tu), ("path", path), ("text", text), ("json", body)) if value is not None}
            for signal, strength, tu, path, text, body in self.connection.execute(
                "SELECT signal, strength, tu, path, text, json FROM signals WHERE artifact = ? ORDER BY rowid", (identity,)
            )
        ]
        annotations = sorted(
            ({key: row[key] for key in ("relation", "section", "path", "line")} for row in self.annotations if row["artifact_id"] == identity),
            key=lambda row: (row["relation"] != "defines", row["path"], row["line"]),
        )
        plans, unread = plan_findings(self.plans, identity, artifact["item"])
        deferrals = [
            {key: row.get(key) for key in ("id", "reason", "issue", "approval")} for row in self.deferrals if identity in row.get("artifacts", [])
        ]
        return {
            "id": identity,
            "kind": artifact["kind"],
            "address": f"0x{artifact['address']:x}",
            "end": f"0x{artifact['end']:x}",
            "size": artifact["size"],
            "section": artifact["section"],
            "input_section": artifact["input_section"],
            "names": names,
            "declaration": names[0]["declaration"] if names else None,
            "classification": artifact["classification"],
            "library": artifact["library"],
            "class_weak": bool(artifact["class_weak"]),
            "class_evidence": artifact["class_evidence"] or None,
            "weak": bool(artifact["weak"]),
            "inline": bool(artifact["inline"]),
            "common": bool(artifact["common"]),
            "emitted_from_header": artifact["emitted_from_header"],
            "segment": artifact["segment"],
            "item": artifact["item"],
            "owner": verdict(annotations, plans, deferrals),
            "annotations": annotations,
            "plans": plans,
            "plans_unread": unread,
            "deferrals": deferrals,
            "candidates": candidates,
            "signals": signals,
            "code": code_locations(self.root, [row["name"] for row in names], self.known),
        }


def owner_report(root: Path, cache: Path, query: str, *, show_all: bool = False, limit: int = 25) -> dict[str, Any]:
    """The matches of ``query`` and the detail of the ones to show (see the module docstring)."""

    with closing(sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True)) as connection:
        matches = find_matches(connection, query)
        exact = [row for row in matches if row["exact"]]
        if show_all:
            chosen, shown = matches[:limit], "all"
        elif len(matches) == 1:
            chosen, shown = matches, "single"
        elif len(exact) == 1:
            chosen, shown = exact, "exact"
        else:
            chosen, shown = [], "list"
        lookup = _Lookup(root, connection)
        details = [lookup.detail(row["id"]) for row in chosen]
    report: dict[str, Any] = {
        "ok": bool(matches),
        "mutation_performed": False,
        "query": query,
        "match_count": len(matches),
        "matches": matches[:limit],
        "truncated": len(matches) > limit,
        "shown": shown if matches else None,
        "details": details,
    }
    if not matches:
        report["error"] = f"no artifact matches {query!r} (try an artifact ID, a 0x address, an ELF name or a readable name)"
        # Provisional code with no ELF counterpart: where a fence of exactly this name holds it.
        report["fences"] = code_locations(root, [query.strip()], lambda name: True)["fences"]
    if lookup.problems:
        report["problems"] = sorted(set(lookup.problems))
    return report


# -- text ----------------------------------------------------------------------------


def _shown(rows: list[str], limit: int = SHOWN) -> list[str]:
    return rows[:limit] + ([f"... +{len(rows) - limit} more (--json lists all)"] if len(rows) > limit else [])


def _brief(row: dict[str, Any]) -> str:
    where = f" [{row['item'].removeprefix('socom:work:')}]" if row.get("item") else ""
    mark = "*" if row["exact"] else " "
    declaration = row.get("declaration") or row.get("name") or ""
    return f"{mark} {row['id']}  {row.get('classification') or '-'}  {declaration}{where}"


def _plan_text(plan: dict[str, Any]) -> list[str]:
    files = {
        "unchanged": "plan file matches the SHA-256 the tracker cites",
        "changed": "PLAN FILE CHANGED: its SHA-256 is not one the tracker cites"
        + (f" (cited {', '.join(sha[:12] for sha in plan['recorded_sha256'])})" if plan["recorded_sha256"] else ""),
    }
    state = files.get(plan["file"], plan["file"])
    apply = plan.get("apply")
    if apply and apply.get("plan_matches") is False:
        state += f"; {apply['item'].removeprefix('socom:work:')} applied another plan version"
    if plan.get("owner"):
        owner = plan["owner"]
        entry = owner.get("entry") or {}
        confidence = entry.get("confidence") or owner.get("confidence")
        rule = entry.get("draft_rule") or owner.get("draft_rule")
        verdict_text = f"owned by {_owner_label(owner)} ({owner.get('classification')}, {confidence}{', ' + rule if rule else ''})"
    elif plan.get("unresolved"):
        verdict_text = "unresolved"
    elif plan["in_scope"]:
        verdict_text = "its slice holds it, but the plan does not list it"
    else:
        verdict_text = "mentions it"
    lines = [f"plan {plan['item']} ({plan['status']}; {state}): {verdict_text}"]
    if plan.get("owner") and (plan["owner"].get("entry") or {}).get("basis"):
        lines.append(f"  basis: {plan['owner']['entry']['basis']}")
    if plan.get("unresolved"):
        lines.append(f"  reason: {plan['unresolved'].get('reason')}")
        suggest = plan["unresolved"].get("suggest")
        if isinstance(suggest, dict):
            lines.append(f"  suggestion: {suggest.get('owner')} ({suggest.get('rule')}, {suggest.get('confidence')}): {suggest.get('basis')}")
    for row in plan.get("contradictions") or []:
        at = row.get("provisional_file") or "?"
        at += f":{row['line']}" if row.get("line") else ""
        lines.append(f"  contradiction {row.get('kind')} at {at}: {'; '.join(row.get('elf_evidence') or [])}")
    for row in plan.get("header_emits") or []:
        lines.append(f"  header emit {row.get('header')} ({row.get('reason')}): {'; '.join(row.get('evidence') or [])}")
    if plan.get("open_header_emit_reason"):
        lines.append(f"  open header emit: {plan['open_header_emit_reason']}")
    lines.extend(f"  note: {text}" for text in plan.get("notes") or [])
    return lines


def _signal_text(row: dict[str, Any]) -> str:
    extra = row.get("tu") or row.get("path") or row.get("text")
    if extra is None and row.get("json"):
        body = json.loads(row["json"])
        extra = next((str(value) for key, value in sorted(body.items()) if key not in ("signal", "strength") and isinstance(value, (str, int))), None)
    return " ".join(str(value) for value in (row["signal"], row.get("strength"), extra) if value)


def _fence_text(row: dict[str, Any]) -> str:
    flags = ["holding file" if row["holding"] else "unit file"]
    if row["match"] != "exact":
        flags.append("other signature")
    if row.get("nested"):
        flags.append("nested")
    if row.get("held_from"):
        flags.append(f"held from {row['held_from']}")
    for region in row.get("if0") or []:
        where = "around the fence" if region["encloses_fence"] else "inside the entry"
        comment = f": {region['comment']}" if region.get("comment") else ""
        flags.append(f"#if 0 {where} at {region['line']}-{region['end_line']}{comment}")
    return f"  {row['path']}:{row['line']}  {row['kind']} {row['name']}  [{'; '.join(flags)}]"


def detail_text(detail: dict[str, Any]) -> list[str]:
    flags = [flag for flag in ("weak", "inline", "common") if detail[flag]]
    lines = [
        f"{detail['id']}  {detail['kind']}  {detail['address']}-{detail['end']}  {detail['size']} bytes  {detail['section'] or '-'}"
        + (f"  ({', '.join(flags)})" if flags else "")
    ]
    for row in detail["names"]:
        same = row["declaration"] == row["name"]
        lines.append(f"  {row['name']}  {row['binding']}" + ("" if same else f"  {row['declaration']}"))
    classification = detail["classification"] or "-"
    if detail["library"]:
        classification += f" {detail['library']}"
    if detail["class_weak"] and detail["class_evidence"]:
        classification += f" (weak candidate: {detail['class_evidence']})"
    scope = f"; slice {detail['item']}" if detail["item"] else "; in no plan slice"
    lines.append(f"  {classification}{scope}" + (f"; emitted from {detail['emitted_from_header']}" if detail["emitted_from_header"] else ""))
    lines.append(f"owner: {detail['owner']['summary']}")
    if detail["annotations"]:
        lines.extend(f"  {row['relation']} {row['section']}  {row['path']}:{row['line']}" for row in detail["annotations"])
    else:
        lines.append("  no @socom-artifact annotation under src/")
    for plan in detail["plans"]:
        lines.extend(_plan_text(plan))
    unread = detail["plans_unread"]
    for row in unread[:1] if unread and unread[0]["in_scope"] else []:
        lines.append(f"plan {row['item']} ({row.get('status')}; its slice holds it): {row['path']} is {row['file']}")
    others = [row for row in unread if not row["in_scope"]]
    if others:
        lines.append(f"{len(others)} other plan files are missing or unreadable and may list it (--json names them)")
    if not detail["plans"] and not detail["plans_unread"]:
        lines.append("plans: none lists it")
    for row in detail["deferrals"]:
        basis = row["issue"] or ("user approval " + str((row.get("approval") or {}).get("at")))
        lines.append(f"deferral {row['id']} ({basis}): {row['reason']}")
    candidates = [
        f"{row['tu']} {row['strength']}" + (f" ({','.join(row['via'])})" if row["via"] else "") for row in detail["candidates"]
    ]
    lines.append("candidates: " + ("; ".join(_shown(candidates)) if candidates else "none"))
    signals = [_signal_text(row) for row in detail["signals"]]
    lines.append("signals: " + ("; ".join(_shown(signals)) if signals else "none"))
    code = detail["code"]
    if code["fences"]:
        lines.append("code:")
        lines.extend(_fence_text(row) for row in code["fences"])
    else:
        lines.append("code: no skeleton fence under src/")
    lines.extend(f"  class declared at {row['path']}:{row['line']} (decl {row['region']})" for row in code["declarations"])
    return lines


def report_text(report: dict[str, Any]) -> str:
    if not report["matches"]:
        held = [_fence_text(row) for row in report.get("fences") or []]
        if held:
            return "\n".join([f"{report['error']}; no ELF symbol has this name or qualified name, but src/ holds it:", *held])
        return report["error"]
    lines: list[str] = []
    if report["shown"] != "single":
        lines.append(f"{report['match_count']} artifacts match {report['query']!r} (* exact):")
        lines.extend(f"  {_brief(row)}" for row in report["matches"])
        if report["truncated"]:
            lines.append("  ... (--limit shows more)")
        if not report["details"]:
            exact = sum(1 for row in report["matches"] if row["exact"])
            why = f"{exact} exact matches" if exact else "no exact match"
            lines.append(f"{why}: query an artifact ID or an ELF name, or pass --all for every detail")
    elif report["matches"][0]["how"] == "contains":
        lines.append(f"{report['query']} lies inside {report['matches'][0]['id']}")
    elif report["matches"][0]["how"] == "same-name":
        lines.append(f"{report['query']} is not an ELF name; same qualified name, other signature: {report['matches'][0]['name']}")
    for detail in report["details"]:
        if lines and report["shown"] != "single":
            lines.append("")
        lines.extend(detail_text(detail))
    lines.extend(f"problem: {text}" for text in report.get("problems") or [])
    return "\n".join(lines)


# -- CLI -----------------------------------------------------------------------------


def _source_owner(arguments: argparse.Namespace) -> int:
    from .cli import _build_path, _emit, _root
    from .source_cache import ensure_source_cache
    from .util import SocomError, atomic_write_json

    root = _root(arguments)
    if arguments.limit < 1:
        raise SocomError("--limit must be positive")
    graph_path = Path(arguments.graph)
    if not graph_path.is_absolute():
        graph_path = root / graph_path
    if not graph_path.is_file():
        # The graph JSON is disposable build output, written once as `source sql` does.
        from .source_graph import source_graph

        atomic_write_json(_build_path(root, arguments.graph, "source graphs"), source_graph(root))
    cache, rebuilt = ensure_source_cache(root, graph_path=graph_path)
    report = owner_report(root, cache, arguments.query, show_all=arguments.all, limit=arguments.limit)
    report["cache"] = cache.relative_to(root).as_posix()
    report["rebuilt"] = rebuilt
    if arguments.json:
        _emit(report)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(report_text(report))
    return 0 if report["ok"] else 1
