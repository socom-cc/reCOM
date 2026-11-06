"""Fence-keyed carry of skeleton entries before the per-file merge (stage 5 re-apply after a stage 4 amendment).

The three-way merge of ``order_skeleton_merge`` is per file, but a new
render may move an entry to another file: a body held in a ``*_holding.cpp``
gets an owner in a new unit file, a class region moves to another header.
The functional port lane's live edits of that entry sit at its old place,
which the new render rewrites, so a per-file merge would lose them or
conflict on them.  Before the per-file merge every entry is identified by
its fence:

* an **entry** is a top-level ``/* @socom-skeleton stub|body <name> */`` up
  to the next top-level fence (trailing blank lines excluded; indented
  local-static stubs belong to their function), or a
  ``/* @socom-skeleton decl <name> */`` region through its ``end`` line;
* an entry's identity is its kind (definition or region) and name, matched
  in the same file first, then anywhere in the tree when the name is unique
  there, then by the body id of its ``/* held from <id> */`` line (the
  render's manifest gives the id of a moved body whose fence name the
  declarator rewrite changed).

For each entry the render places in the item's files, the ancestor (the
previous render) and the live text (``src/``, wherever that entry is now)
are found.  Where the live text differs from the ancestor and the entry
crossed a file or a name, the entry's text at the render's place is
``merge3(ancestor, live, render)`` (an overlap is an entry-level conflict
with both sides); the live entry's old place takes back its ancestor text
(or loses the entry) so the per-file merge sees no change there.  An entry
whose live and ancestor text sit in the same file under the same name is
left to the per-file merge, as before, unless that file still conflicts:
then the route retries it with the file's preamble (the text before its
first fence) and each such edited entry merged on their own (``entry_level``).

An entry the render moves into another item's file is recorded ``pending``
with its ancestor and live texts in the blob store; that item's re-apply
carries it from the record.  An entry carried in from another item's live
file is recorded ``merged``, and that item's later re-apply finds it carried
(``carried-by``) instead of deleting an edit.  A live entry with no ancestor
anywhere (the port lane added the fence) whose name the render places
nowhere keeps its code, its fence turned into a ``/* port: ... (no owner in
the render) */`` comment (``port-comment``).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .order_skeleton_merge import Merged, get_blob, lf, merge3, sha

FENCE_LINE = re.compile(r"^(?P<indent>[ \t]*)/\* @socom-skeleton (?P<kind>stub|body|decl|end) (?P<name>\S+) \*/[ \t]*$")
HELD_LINE = re.compile(r"^/\* held from (?P<source>\S+) \*/[ \t]*$")
PORT_COMMENT = "{indent}/* port: {kind} {name} (no owner in the render) */\n"
STATES = ("merged", "pending", "carried-by", "port-comment")

Location = tuple[str, int]


@dataclass(frozen=True)
class Entry:
    kind: str
    name: str
    start: int
    end: int
    source: str | None
    indent: str

    @property
    def key(self) -> tuple[str, str]:
        return ("decl" if self.kind == "decl" else "def", self.name)


def _lines(data: bytes | None) -> list[str]:
    return [] if data is None else lf(data).decode("utf-8", "surrogateescape").splitlines(keepends=True)  # type: ignore[union-attr]


def _bytes(lines: list[str]) -> bytes:
    return "".join(lines).encode("utf-8", "surrogateescape")


def parse_entries(lines: list[str]) -> list[Entry]:
    """The top-level entries of a file's lines (an unclosed region is no entry)."""

    entries: list[Entry] = []
    open_def: tuple[str, str, int, str] | None = None
    region: tuple[str, int, str] | None = None

    def close(start: int, stop: int) -> int:
        while stop > start + 1 and not lines[stop - 1].strip():
            stop -= 1
        return stop

    def held(start: int) -> str | None:
        found = HELD_LINE.match(lines[start + 1].rstrip("\n")) if start + 1 < len(lines) else None
        return found["source"] if found else None

    for number, line in enumerate(lines):
        found = FENCE_LINE.match(line.rstrip("\n"))
        if region is not None:
            if found and found["kind"] == "end" and found["name"] == region[0]:
                entries.append(Entry("decl", region[0], region[1], number + 1, None, region[2]))
                region = None
            continue
        if not found or found["kind"] == "end":
            continue
        if found["kind"] in ("stub", "body") and found["indent"] and open_def is not None:
            continue  # a local static or a local class member: part of its function
        if open_def is not None:
            entries.append(Entry(open_def[0], open_def[1], open_def[2], close(open_def[2], number), held(open_def[2]), open_def[3]))
            open_def = None
        if found["kind"] == "decl":
            region = (found["name"], number, found["indent"])
        else:
            open_def = (found["kind"], found["name"], number, found["indent"])
    if open_def is not None:
        entries.append(Entry(open_def[0], open_def[1], open_def[2], close(open_def[2], len(lines)), held(open_def[2]), open_def[3]))
    return entries


@dataclass
class Tree:
    """The entries of a set of files, indexed by identity and by held body id."""

    lines: dict[str, list[str]] = field(default_factory=dict)
    entries: dict[str, list[Entry]] = field(default_factory=dict)
    by_key: dict[tuple[str, str], list[Location]] = field(default_factory=dict)
    by_source: dict[str, list[Location]] = field(default_factory=dict)

    def add(self, path: str, data: bytes | None, sources: dict[tuple[str, str], str] | None = None) -> None:
        if data is None or b"@socom-skeleton" not in data:
            return
        lines = _lines(data)
        entries = parse_entries(lines)
        if sources:
            entries = [entry if entry.source or entry.kind == "decl" else
                       Entry(entry.kind, entry.name, entry.start, entry.end, sources.get((path, entry.name)), entry.indent)
                       for entry in entries]
        self.lines[path], self.entries[path] = lines, entries
        for number, entry in enumerate(entries):
            self.by_key.setdefault(entry.key, []).append((path, number))
            if entry.source and entry.kind != "decl":
                self.by_source.setdefault(entry.source, []).append((path, number))

    def entry(self, location: Location) -> Entry:
        return self.entries[location[0]][location[1]]

    def text(self, location: Location) -> list[str]:
        entry = self.entry(location)
        return self.lines[location[0]][entry.start:entry.end]

    def body(self, location: Location) -> list[str]:
        entry = self.entry(location)
        return self.lines[location[0]][entry.start + 1:entry.end]

    def find(self, key: tuple[str, str], source: str | None, prefer: str) -> Location | None:
        """The one entry of this identity: in ``prefer`` first, then the tree (unique name), then by held body id."""

        found = self.by_key.get(key) or []
        same = [location for location in found if location[0] == prefer]
        if same:
            return same[0] if len(same) == 1 else None
        if len(found) == 1:
            return found[0]
        if found or not source or key[0] != "def":
            return None
        held = self.by_source.get(source) or []
        return held[0] if len(held) == 1 else None


@dataclass
class Carry:
    """The effective merge inputs of the item's files and what was carried."""

    ours: dict[str, bytes | None] = field(default_factory=dict)
    theirs: dict[str, bytes | None] = field(default_factory=dict)
    entries: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    conflicts: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    merged_here: dict[str, list[str]] = field(default_factory=dict)
    blobs: list[bytes] = field(default_factory=list)

    def note(self, path: str, row: dict[str, Any]) -> None:
        self.entries.setdefault(path, []).append(row)

    def conflict(self, path: str, row: dict[str, Any]) -> None:
        self.conflicts.setdefault(path, []).append(row)


def _text_sha(lines: list[str] | None) -> str | None:
    return None if lines is None else hashlib.sha256(_bytes(lines)).hexdigest()


def merge_entry(ancestor: list[str] | None, live: list[str], render: list[str], render_kind: str) -> Merged:
    """The body of one entry: merge3 with an ancestor; without one the live code fills a canonical stub, else a conflict."""

    if ancestor is not None:
        return merge3(ancestor, live, render)
    if live == render or render_kind == "stub":
        return Merged(lines=list(live), marked=list(live))
    return merge3([], live, render)


def _twin(tree: Tree, entry: Entry) -> Location | None:
    """The one entry of this identity anywhere in the tree (by name, else by held body id)."""

    found = tree.by_key.get(entry.key) or []
    if found:
        return found[0] if len(found) == 1 else None
    held = tree.by_source.get(entry.source or "") or [] if entry.kind != "decl" else []
    return held[0] if len(held) == 1 else None


def _known(tree: Tree, entry: Entry) -> bool:
    """Whether the tree holds an entry of this identity anywhere (by name, or by held body id)."""

    return entry.key in tree.by_key or bool(entry.source and entry.source in tree.by_source)


def _pending(records: dict[str, dict[str, Any]], mine: str, path: str, name: str) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for item_id, record in sorted(records.items()):
        if item_id == mine:
            continue
        for row in record.get("carried") or []:
            if isinstance(row, dict) and row.get("state") == "pending" and row.get("to") == path and row.get("name") == name:
                found.append((item_id, row))
    return found


def _carried_by(record: dict[str, Any] | None, path: str, name: str, origin: str) -> dict[str, Any] | None:
    for row in (record or {}).get("carried") or []:
        if isinstance(row, dict) and row.get("state") == "merged" and row.get("to") == path and row.get("name") == name \
                and row.get("from") == origin:
            return row
    return None


def carry_entries(item_id: str, paths: list[str], ancestors: dict[str, bytes | None], live: dict[str, bytes | None],
                  render: dict[str, bytes | None], render_sources: dict[tuple[str, str], str], owners: dict[str, str],
                  records: dict[str, dict[str, Any]], root: Any, entry_level: set[str] | None = None) -> Carry:
    """Carry the live text of every entry that crossed a file or a name into the render's place (see the module).

    In the files of ``entry_level`` (those the plain per-file merge could not
    merge) an edited entry that stays in its file is merged on its own too.
    """

    mine = set(paths)
    old, now, new = Tree(), Tree(), Tree()
    for path, data in ancestors.items():
        old.add(path, data)
    for path, data in live.items():
        now.add(path, data)
    for path, data in render.items():
        new.add(path, data, render_sources)
    links: dict[Location, tuple[Location | None, Location | None]] = {}
    claims: dict[Location, list[Location]] = {}
    for path in sorted(new.entries):
        for number, entry in enumerate(new.entries[path]):
            here = (path, number)
            before, current = old.find(entry.key, entry.source, path), now.find(entry.key, entry.source, path)
            links[here] = (before, current)
            if current is not None:
                claims.setdefault(current, []).append(here)
    claimed = {current: found[0] for current, found in claims.items() if len(found) == 1}

    # Files whose render changed (port-only entries move to the render's side there) and the files whose edited
    # entries are merged one by one, so an edit next to a block the render moves is no conflict.
    changed = {path for path in mine if sha(render.get(path)) != sha(ancestors.get(path))}
    single = set(entry_level or ()) & changed

    def legacy(here: Location) -> bool:
        """The entry stays in its file under its name: the per-file merge decides, unless edited in a changed file."""

        before, current = links[here]
        name = new.entry(here).name
        same = (before is not None and current is not None and before[0] == current[0] == here[0]
                and old.entry(before).name == now.entry(current).name == name)
        return same and (here[0] not in single or now.body(current) == old.body(before))  # type: ignore[arg-type]

    result = Carry()
    ours_edits: dict[str, list[tuple[int, int, list[str]]]] = {}
    removals: dict[str, list[tuple[int, int]]] = {}
    theirs_edits: dict[str, list[tuple[int, int, list[str]]]] = {}
    previous = records.get(item_id) or {}

    # The render's entries in the item's files: carry the live text in.
    for path in sorted(mine & set(new.entries)):
        for number, entry in enumerate(new.entries[path]):
            here = (path, number)
            if legacy(here):
                continue
            before, current = links[here]
            ancestor = old.body(before) if before is not None else None
            origin, via = None, None
            if current is not None and claimed.get(current) == here:
                body, origin = now.body(current), current[0]
            else:
                found = _pending(records, item_id, path, entry.name)
                if not found:
                    continue
                if len(found) > 1:
                    result.conflict(path, {"entry": entry.name, "to": path, "reason": "several items carry this entry here: "
                                           + ", ".join(sorted(item for item, _row in found))})
                    continue
                via, row = found[0]
                stored = get_blob(root, row.get("live_sha256"))
                ancestor_blob = get_blob(root, row.get("ancestor_sha256")) if row.get("ancestor_sha256") else None
                if stored is None or (row.get("ancestor_sha256") and ancestor_blob is None):
                    result.conflict(path, {"entry": entry.name, "to": path, "via": via,
                                           "reason": "the carried entry's text is not in the blob store"})
                    continue
                body, origin = _lines(stored), row.get("from")
                ancestor = _lines(ancestor_blob) if ancestor_blob is not None else None
            rendered = new.body(here)
            if (ancestor is not None and body == ancestor) or body == rendered:
                continue
            merged = merge_entry(ancestor, body, rendered, entry.kind)
            note = {"name": entry.name, "kind": entry.kind, "from": origin, "to": path, "to_item": item_id,
                    "live_name": now.entry(current).name if current is not None and claimed.get(current) == here else entry.name,
                    "ancestor_sha256": _text_sha(ancestor), "live_sha256": _text_sha(body), "render_sha256": _text_sha(rendered)}
            if via:
                note["via"] = via
            if merged.conflicts:
                result.conflict(path, {**note, "entry": entry.name, "hunks": merged.conflicts})
                theirs_edits.setdefault(path, []).append((entry.start + 1, entry.end, merged.marked))
                continue
            if origin == path and note["live_name"] == entry.name:
                result.merged_here.setdefault(path, []).append(entry.name)  # an edited entry that stayed: no carry
            else:
                note.update(state="merged", merged_sha256=_text_sha(merged.lines))
                result.note(path, note)
            theirs_edits.setdefault(path, []).append((entry.start + 1, entry.end, merged.lines))

    # The live entries in the item's files: give back the ancestor text of what moved, carry out to other items.
    for path in sorted(mine & set(now.entries)):
        for number, entry in enumerate(now.entries[path]):
            here = (path, number)
            target = claimed.get(here)
            if target is not None and legacy(target):
                continue
            if target is None and here not in claims and (twin := _twin(new, entry)) is not None and twin[0] not in mine:
                # Another item's re-apply already carried this entry from here (its live copy now claims the render's).
                destination, name = twin[0], new.entry(twin).name
                done = _carried_by(records.get(owners.get(destination, "")), destination, name, path)
                if done is not None:
                    own = old.find(entry.key, entry.source, path)
                    if own is not None and own[0] == path:
                        ours_edits.setdefault(path, []).append((entry.start, entry.end, old.text(own)))
                    else:
                        removals.setdefault(path, []).append((entry.start, entry.end))
                    note = {"name": name, "kind": new.entry(twin).kind, "from": path, "to": destination,
                            "to_item": owners.get(destination), "live_name": entry.name, "live_sha256": _text_sha(now.body(here))}
                    if done.get("live_sha256") == note["live_sha256"]:
                        result.note(path, {**note, "state": "carried-by"})
                    else:
                        result.conflict(path, {**note, "entry": name, "reason": f"{owners.get(destination)} carried this entry "
                                               f"to {destination} before its later edit here: reopen and re-apply that item"})
                    continue
            if target is None:
                if entry.kind == "decl" or here in claims or _known(old, entry) or _known(new, entry):
                    continue  # the per-file merge decides: an entry the render dropped or places ambiguously
                comment = PORT_COMMENT.format(indent=entry.indent, kind=entry.kind, name=entry.name)
                if path in changed and path in new.lines:
                    # Next to blocks the render moves away an in-place insertion would conflict: the code goes into the
                    # render's side, after the live entry before it that the render keeps (else before the next one).
                    removals.setdefault(path, []).append((entry.start, entry.end))
                    theirs_edits.setdefault(path, []).append(_anchored(now, new, path, number, [comment, *now.body(here)]))
                else:
                    ours_edits.setdefault(path, []).append((entry.start, entry.start + 1, [comment]))
                result.note(path, {"name": entry.name, "kind": entry.kind, "from": path, "to": None, "state": "port-comment",
                                   "live_sha256": _text_sha(now.body(here))})
                continue
            before = links[target][0]
            body = now.body(here)
            if before is not None and before[0] == path:
                ours_edits.setdefault(path, []).append((entry.start, entry.end, old.text(before)))
            else:
                removals.setdefault(path, []).append((entry.start, entry.end))
            destination = target[0]
            if destination in mine:
                continue
            ancestor = old.body(before) if before is not None else None
            rendered = new.body(target)
            if (ancestor is not None and body == ancestor) or body == rendered:
                continue
            name = new.entry(target).name
            note = {"name": name, "kind": new.entry(target).kind, "from": path, "to": destination,
                    "to_item": owners.get(destination), "live_name": entry.name, "ancestor_sha256": _text_sha(ancestor),
                    "live_sha256": _text_sha(body), "render_sha256": _text_sha(rendered)}
            done = _carried_by(records.get(owners.get(destination, "")), destination, name, path)
            if done is not None and done.get("live_sha256") == note["live_sha256"]:
                result.note(path, {**note, "state": "carried-by"})
            elif done is not None:
                result.conflict(path, {**note, "entry": name, "reason": f"{owners.get(destination)} carried this entry to "
                                       f"{destination} before its later edit here: reopen and re-apply that item"})
            else:
                result.blobs.extend(_bytes(text) for text in (ancestor, body) if text is not None)
                result.note(path, {**note, "state": "pending"})

    # Pending carries of the item's previous record whose destination has not carried them yet stay pending.
    listed = {(row["name"], row["to"]) for rows in result.entries.values() for row in rows}
    for row in previous.get("carried") or []:
        if not isinstance(row, dict) or row.get("state") != "pending" or (row.get("name"), row.get("to")) in listed:
            continue
        destination = owners.get(str(row.get("to")))
        if _carried_by(records.get(destination or ""), str(row.get("to")), str(row.get("name")), str(row.get("from"))) is None \
                and row.get("from") in mine:
            result.note(str(row["from"]), dict(row))

    # A file merged entry by entry merges its preamble (the text before the first fence) on its own as well.
    floors: dict[str, int] = {}
    for path in sorted(single & set(now.entries) & set(old.entries) & set(new.entries)):
        firsts = [(tree.entries[path][0].start if tree.entries[path] else len(tree.lines[path])) for tree in (old, now, new)]
        before, current, rendered = (tree.lines[path][:first] for tree, first in zip((old, now, new), firsts))
        if current == before:
            continue
        merged = merge3(before, current, rendered)
        if merged.conflicts:
            continue  # the per-file merge reports it
        floors[path] = firsts[1]
        ours_edits.setdefault(path, []).append((0, firsts[1], before))
        theirs_edits.setdefault(path, []).append((0, firsts[2], merged.lines))
        result.merged_here.setdefault(path, []).append("(preamble)")
    for path, ranges in removals.items():
        ours_edits.setdefault(path, []).extend(_removals(now.lines[path], ranges, floors.get(path, 0)))
    for path, edits in ours_edits.items():
        result.ours[path] = _apply(now.lines[path], edits)
    for path, edits in theirs_edits.items():
        result.theirs[path] = _apply(new.lines[path], edits)
    return result


def _anchored(now: Tree, new: Tree, path: str, number: int, text: list[str]) -> tuple[int, int, list[str]]:
    """An insertion of ``text`` into the render of ``path`` beside the live neighbours of live entry ``number``."""

    def place(entry: Entry) -> Entry | None:
        found = [row for row in new.entries.get(path) or [] if row.key == entry.key]
        return found[0] if len(found) == 1 else None

    live = now.entries[path]
    for before in reversed(live[:number]):
        if (kept := place(before)) is not None:
            return (kept.end, kept.end, ["\n", *text])
    for after in live[number + 1:]:
        if (kept := place(after)) is not None:
            return (kept.start, kept.start, [*text, "\n"])
    lines = new.lines[path]
    return (len(lines), len(lines), ["\n", *text])


def _removals(lines: list[str], ranges: list[tuple[int, int]], floor: int = 0) -> list[tuple[int, int, list[str]]]:
    """Edits that remove entries with one blank separator: runs of entries apart only by blank lines go together.

    A run followed by more code takes the blank line after it; a run at the
    end of the file takes the blank line before it, so the file ends as the
    entries had never been there.
    """

    runs: list[list[int]] = []
    for start, stop in sorted(ranges):
        if runs and all(not line.strip() for line in lines[runs[-1][1]:start]):
            runs[-1][1] = stop
        else:
            runs.append([start, stop])
    edits = []
    for start, stop in runs:
        after = stop
        while after < len(lines) and not lines[after].strip():
            after += 1
        if after < len(lines):
            stop = stop + 1 if stop < after else stop
        else:
            stop = len(lines)
            start = start - 1 if start > floor and not lines[start - 1].strip() else start
        edits.append((start, stop, []))
    return edits


def _apply(lines: list[str], edits: list[tuple[int, int, list[str]]]) -> bytes:
    out = list(lines)
    for start, stop, replacement in sorted(edits, key=lambda edit: edit[0], reverse=True):
        out[start:stop] = [text if text.endswith("\n") else text + "\n" for text in replacement]
    return _bytes(out)


def carry_sha256(ours: bytes | None, theirs: bytes | None) -> str:
    return hashlib.sha256(f"{sha(ours)}:{sha(theirs)}".encode()).hexdigest()
