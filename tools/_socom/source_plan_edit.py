"""Compact planner views and single-decision edits of stage 4 owner plans.

``source plan open`` lists only what a planner still has to decide in a
drafted plan (open unresolved rows, open owner rows, open header emits and
an inferred reservation) with each open artifact's evidence from the source
query cache, so a planner never loads or rewrites the whole plan JSON.

``source plan decide`` records one decision: it moves the named artifacts
into one existing owner row (an entry ``{artifact, confidence, basis}``
without ``draft_rule``: hand-written, for the reviewer) or into an
``unresolved`` row with a real reason, accepts the drafter's ``suggest``ion
of an open row as such a hand entry, adds (or with ``--override`` replaces)
a ``contradictions`` or ``header_emits`` row, or removes a contradiction.
It loads and dumps the plan as JSON, never as text, refuses control
characters, and refuses to move an artifact a draft rule decided, or to
replace a header-emit or contradiction row, unless ``--override`` gives the
evidence (recorded as a plan note).  An owner row a move empties is
dropped; one already empty (added by hand) is kept.  The owner row's
confidence follows its weakest entry, an artifact moved into an authored
row takes the draft's ``open_row_header_emits`` row, and the annotations
are re-derived when the cache holds the plan's graph.  Only the holder of
the plan item's lease decides (``require_plan_lease``).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from .source_plan import (
    _CONTRADICTION_KIND,
    _PROVIDER_HEADER,
    CONFIDENCES,
    DRAFT_OPEN,
    EMIT_REASONS,
    HEADER_SUFFIXES,
    INFERRED_STATUS,
    _path_state,
    _workspace_path,
    artifact_id,
    control_characters,
    derive_annotations,
    owned_files,
    suggestion_problems,
)
from .util import SocomError

SHOWN_REFERENCES = 4
# Functions scanned on each side of an open function for its flanking anchors.
FLANK_SCAN = 256
# Runs of copies shown per flank (consecutive copies of one holder are one run).
SHOWN_COPIES = 6


def owner_keys(owner: dict[str, Any]) -> list[str]:
    """The ``--owner`` spellings that name an owner row (casefolded)."""

    keys = []
    unit = owner.get("translation_unit")
    if isinstance(unit, str) and unit:
        keys.append(unit)
    member = owner.get("archive_member") if isinstance(owner.get("archive_member"), dict) else {}
    if member.get("gnu_object"):
        keys.append(str(member["gnu_object"]))
    if member.get("object"):
        keys.append(str(member["object"]))
        keys.append(f"{owner.get('library')}:{member['object']}")
    if owner.get("classification") == "compiler-generated" and not unit:
        keys.append("compiler-generated")
    return [key.casefold() for key in keys]


def owner_label(owner: dict[str, Any]) -> str:
    member = owner.get("archive_member") if isinstance(owner.get("archive_member"), dict) else {}
    name = owner.get("translation_unit") or member.get("gnu_object") or member.get("object")
    return f"{owner.get('classification')} {name}" if name else str(owner.get("classification"))


def _holders(plan: dict[str, Any]) -> dict[str, tuple[str, int, int]]:
    """artifact -> ("owner", row, entry) or ("unresolved", row, -1)."""

    found: dict[str, tuple[str, int, int]] = {}
    for number, owner in enumerate(plan.get("owners") or []):
        if not isinstance(owner, dict):
            continue
        for position, entry in enumerate(owner.get("artifacts") or []):
            identity = artifact_id(entry)
            if identity is not None:
                found.setdefault(identity, ("owner", number, position))
    for number, row in enumerate(plan.get("unresolved") or []):
        if isinstance(row, dict) and isinstance(row.get("artifact"), str):
            found.setdefault(row["artifact"], ("unresolved", number, -1))
    return found


def _row_confidence(owner: dict[str, Any]) -> None:
    """Keep the row's confidence its weakest entry's (validation's rule)."""

    entries = owner.get("artifacts") or []
    explicit = [entry["confidence"] for entry in entries if isinstance(entry, dict) and entry.get("confidence") in CONFIDENCES]
    if not explicit:
        return
    weakest = max(explicit, key=CONFIDENCES.index)
    current = owner.get("confidence")
    if len(explicit) == len(entries) or current not in CONFIDENCES:
        owner["confidence"] = weakest
    elif CONFIDENCES.index(current) < CONFIDENCES.index(weakest):
        owner["confidence"] = weakest


def require_plan_lease(tracker: dict[str, Any], item_id: Any, owner: Any, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """The plan item, when ``owner`` holds its active lease; refuses otherwise.

    ``source plan decide`` edits a plan only for the worker that claimed its
    item (``progress work claim``): another worker's lease, an expired one or
    an unclaimed item is refused.
    """

    if not isinstance(owner, str) or not owner.strip():
        raise SocomError("--lease-owner must name the worker holding the plan item's lease")
    if not isinstance(item_id, str):
        raise SocomError("the plan has no work_item_id: its item's lease cannot be checked")
    item = next((row for row in tracker.get("work_items") or [] if isinstance(row, dict) and row.get("id") == item_id), None)
    if item is None:
        raise SocomError(f"{item_id} is not a work item of the tracker")
    lease = item.get("lease")
    if item.get("status") != "in_progress" or not isinstance(lease, dict):
        raise SocomError(f"{item_id} is {item.get('status')} and not leased: claim it (progress work claim) before deciding")
    try:
        expires = dt.datetime.fromisoformat(str(lease.get("expires_at")).replace("Z", "+00:00"))
    except ValueError as failure:
        raise SocomError(f"{item_id}'s lease has no readable expiry") from failure
    if expires <= (now or dt.datetime.now(dt.timezone.utc)):
        raise SocomError(f"{item_id}'s lease by {lease.get('owner')} expired at {lease.get('expires_at')}: claim it again")
    if lease.get("owner") != owner:
        raise SocomError(f"{item_id} is leased by {lease.get('owner')}, not {owner}")
    return item


def _open_row_emit(plan: dict[str, Any], identity: str) -> dict[str, Any] | None:
    """The draft's ``open_row_header_emits`` row of an artifact (rules 6), if any."""

    draft = plan.get("draft") if isinstance(plan.get("draft"), dict) else {}
    return next(
        (row for row in draft.get("open_row_header_emits") or [] if isinstance(row, dict) and row.get("artifact") == identity),
        None,
    )


def _sync_open_row_emits(plan: dict[str, Any], identities: list[str]) -> list[dict[str, Any]]:
    """Copy (or drop) each artifact's ``open_row_header_emits`` row as its new owner row requires.

    An artifact now owned by an authored row gets the draft's open-row emit
    when no header-emit row records one (``source plan draft --check`` proves
    the copied row by its ``draft_rule``); one that leaves the authored rows
    loses that copied row again.  Other header-emit rows are left alone.
    """

    authored = {
        identity
        for row in plan.get("owners") or []
        if isinstance(row, dict) and row.get("classification") == "authored"
        for identity in map(artifact_id, row.get("artifacts") or [])
        if identity
    }
    changes = []
    for identity in identities:
        emit = _open_row_emit(plan, identity)
        if emit is None:
            continue
        emits = plan.get("header_emits")
        if not isinstance(emits, list):
            emits = plan["header_emits"] = []
        existing = [number for number, row in enumerate(emits) if isinstance(row, dict) and row.get("artifact") == identity]
        if identity in authored and not existing:
            emits.append(dict(emit))
            changes.append({"artifact": identity, "header_emit": emit.get("header"), "draft_rule": emit.get("draft_rule"),
                            "copied": "draft.open_row_header_emits"})
        elif identity not in authored:
            for number in reversed(existing):
                if emits[number] == emit:
                    del emits[number]
                    changes.append({"artifact": identity, "header_emit_removed": emit.get("header"), "draft_rule": emit.get("draft_rule")})
    return changes


def decide(
    plan: dict[str, Any],
    artifacts: list[str],
    *,
    owner: str | None = None,
    confidence: str | None = None,
    basis: str | None = None,
    unresolved: str | None = None,
    override: bool = False,
    evidence: str | None = None,
) -> list[dict[str, Any]]:
    """Record one decision for ``artifacts`` in ``plan`` (in place); the changes made.

    An artifact the decision puts in an authored row also gets the draft's
    ``open_row_header_emits`` row (rules 6), unless a header-emit row records
    one already; leaving the authored rows removes that copied row.
    """

    if not isinstance(plan, dict) or plan.get("schema_version") != 2:
        raise SocomError("source plan decide edits schema 2 plans only (its entries carry confidence and basis)")
    if (owner is None) == (unresolved is None):
        raise SocomError("give --owner with --confidence and --basis, or --unresolved <reason>")
    if owner is not None:
        if confidence not in CONFIDENCES:
            raise SocomError(f"--confidence must be one of {list(CONFIDENCES)}")
        if not isinstance(basis, str) or not basis.strip():
            raise SocomError("--basis needs the evidence line for the decision")
    if unresolved is not None and not unresolved.strip():
        raise SocomError("--unresolved needs a real reason")
    if override and (not isinstance(evidence, str) or not evidence.strip()):
        raise SocomError("--override needs --evidence: why the draft rule is wrong here")
    texts = [value for value in (basis, unresolved, evidence, owner) if isinstance(value, str)]
    if control_characters(texts):
        raise SocomError("a decision may not hold control characters (U+0000-U+001F)")
    owners = plan.get("owners")
    if not isinstance(owners, list):
        raise SocomError("the plan has no owners list")
    # Rows already empty (added by hand, still to be decided into) are kept.
    empty_before = {id(row) for row in owners if isinstance(row, dict) and not row.get("artifacts")}
    target = None
    if owner is not None:
        matches = [number for number, row in enumerate(owners) if isinstance(row, dict) and owner.casefold() in owner_keys(row)]
        if len(matches) != 1:
            known = sorted({key for row in owners if isinstance(row, dict) for key in owner_keys(row)})
            raise SocomError(
                f"--owner {owner!r} names {len(matches)} owner rows; add the row first, or use one of: {', '.join(known)}"
            )
        target = matches[0]
    changes = []
    for identity in artifacts:
        holders = _holders(plan)
        if identity not in holders:
            raise SocomError(f"{identity} is not listed in this plan (owned or unresolved)")
        where, row_number, position = holders[identity]
        before = None
        if where == "owner":
            current = owners[row_number]
            entry = current["artifacts"][position]
            rule = entry.get("draft_rule") if isinstance(entry, dict) else None
            if rule and not override:
                raise SocomError(
                    f"{identity} is decided by draft rule {rule} for {owner_label(current)}: pass --override with --evidence"
                )
            before = f"{owner_label(current)}" + (f" ({rule})" if rule else "")
            del current["artifacts"][position]
            if rule:
                plan.setdefault("notes", []).append(f"override {identity}: the draft gave {before}; {evidence.strip()}")
        else:
            row = plan["unresolved"][row_number]
            before = "unresolved" + (" (draft open)" if row.get("draft") == DRAFT_OPEN else "")
            del plan["unresolved"][row_number]
        if target is not None:
            receiving = owners[target]
            receiving.setdefault("artifacts", []).append({"artifact": identity, "confidence": confidence, "basis": basis.strip()})
            _row_confidence(receiving)
            after = owner_label(receiving)
        else:
            plan.setdefault("unresolved", []).append({"artifact": identity, "reason": unresolved.strip()})
            after = "unresolved"
        changes.append({"artifact": identity, "from": before, "to": after})
    # An owner row this call emptied is dropped (a row lists its artifacts);
    # one that was already empty stays for the planner to decide into.
    kept = []
    for row in owners:
        if isinstance(row, dict) and not row.get("artifacts") and id(row) not in empty_before:
            changes.append({"row_removed": owner_label(row)})
            continue
        if isinstance(row, dict):
            _row_confidence(row)
        kept.append(row)
    plan["owners"] = kept
    changes.extend(_sync_open_row_emits(plan, artifacts))
    if control_characters(plan):
        raise SocomError("the plan holds control characters; fix them before deciding (source plan validate lists them)")
    return changes


def _require_v2(plan: Any, what: str) -> None:
    if not isinstance(plan, dict) or plan.get("schema_version") != 2:
        raise SocomError(f"source plan decide {what} edits schema 2 plans only")


def _lines(values: list[str] | None, flag: str) -> list[str]:
    lines = [value.strip() for value in values or [] if isinstance(value, str) and value.strip()]
    if not lines:
        raise SocomError(f"{flag} needs at least one evidence line")
    return lines


def accept_suggestions(plan: dict[str, Any], artifacts: list[str]) -> list[dict[str, Any]]:
    """Record each open row's ``suggest``ion ``{owner, rule, confidence, basis}`` as a hand entry.

    The entry copies the suggestion's confidence and basis and carries no
    ``draft_rule``: the reviewer reviews it like any hand-written entry.  An
    artifact without a suggestion, or whose suggested owner row does not
    exist, is refused.
    """

    _require_v2(plan, "--accept-suggestion")
    changes = []
    for identity in artifacts:
        where, number, _position = _holders(plan).get(identity, (None, -1, -1))
        if where is None:
            raise SocomError(f"{identity} is not listed in this plan (owned or unresolved)")
        suggest = plan["unresolved"][number].get("suggest") if where == "unresolved" else None
        if suggest is None:
            raise SocomError(f"{identity} has no suggestion: only an unresolved row the drafter suggested an owner for")
        if found := [text for text in suggestion_problems(suggest) if not text.startswith("has unknown fields")]:
            raise SocomError(f"{identity} suggest {'; '.join(found)}")
        for change in decide(plan, [identity], owner=suggest["owner"], confidence=suggest["confidence"], basis=suggest["basis"]):
            if change.get("artifact") == identity:
                change["suggestion"] = suggest["rule"]
            changes.append(change)
    return changes


def _contradiction_place(provisional_file: Any, line: Any) -> None:
    if not _workspace_path(provisional_file):
        raise SocomError("--provisional-file must be a repo-relative path under src/")
    if line is not None and (isinstance(line, bool) or not isinstance(line, int) or line < 1):
        raise SocomError("--line must be a positive line number (omit it for a file-level contradiction)")


def _contradiction_rows(plan: dict[str, Any]) -> list[Any]:
    rows = plan.setdefault("contradictions", [])
    if not isinstance(rows, list):
        raise SocomError("the plan's contradictions must be a list")
    return rows


def _at(row: Any, identity: str, provisional_file: str, line: int | None) -> bool:
    """Whether a contradictions row is the one of ``identity`` at that file and line (any kind)."""

    return isinstance(row, dict) and (row.get("artifact"), row.get("provisional_file"), row.get("line")) == (
        identity,
        provisional_file,
        line,
    )


def add_contradictions(
    plan: dict[str, Any],
    artifacts: list[str],
    *,
    kind: str,
    provisional_file: str,
    line: int | None,
    elf_evidence: list[str] | None,
    root: Path | None = None,
    in_graph: Callable[[str], bool] | None = None,
    override: bool = False,
    override_evidence: str | None = None,
) -> list[dict[str, Any]]:
    """Add one ``contradictions`` row per artifact: provisional source the ELF decides against.

    The artifact must be listed in the plan, or be an artifact of the graph
    (``in_graph``) outside it when ``provisional_file`` is a file this plan's
    authored rows own (an owned file defining a function the ELF places in
    another segment).  ``provisional_file`` must name an existing file under
    ``src/`` exactly (checked when ``root`` is given) and ``line`` one of its
    lines, or be ``None`` for a file-level contradiction.  With ``override``
    (and its evidence, kept as a plan note) the new row replaces the
    artifact's rows at that file and line, whatever their kind.
    """

    _require_v2(plan, "--contradiction")
    if not isinstance(kind, str) or not _CONTRADICTION_KIND.match(kind):
        raise SocomError("--contradiction needs a lowercase kind slug such as defined-elsewhere or signature")
    _contradiction_place(provisional_file, line)
    lines = _lines(elf_evidence, "--contradiction --elf-evidence")
    if override and (not isinstance(override_evidence, str) or not override_evidence.strip()):
        raise SocomError("--override needs --evidence: why the existing contradiction row is wrong")
    if control_characters([kind, provisional_file, *lines, override_evidence or ""]):
        raise SocomError("a contradiction may not hold control characters (U+0000-U+001F)")
    if root is not None:
        state, actual = _path_state(root, provisional_file)
        if state != "exact" or not (root / provisional_file).is_file():
            raise SocomError(
                f"--provisional-file {provisional_file} must name an existing file exactly" + (f" (on disk: {actual})" if actual else "")
            )
        if line is not None:
            with open(root / provisional_file, "rb") as handle:
                count = sum(1 for _line in handle)
            if line > count:
                raise SocomError(f"{provisional_file} has {count} lines, not {line}")
    rows = _contradiction_rows(plan)
    holders = _holders(plan)
    owned = owned_files(plan)
    changes = []
    for identity in artifacts:
        if identity not in holders:
            if provisional_file not in owned:
                raise SocomError(
                    f"{identity} is not listed in this plan: a contradiction about an artifact outside the plan must "
                    f"lie in a file this plan's authored rows own (provisional_file or workspace_path), not {provisional_file}"
                )
            if in_graph is None or not in_graph(identity):
                raise SocomError(f"{identity} is neither listed in this plan nor an artifact of the graph (--graph)")
        row = {"artifact": identity, "provisional_file": provisional_file, "line": line, "kind": kind, "elf_evidence": list(lines)}
        change: dict[str, Any] = {"artifact": identity, "contradiction": kind, "provisional_file": provisional_file, "line": line}
        if identity not in holders:
            change["outside_plan"] = True
        existing = [number for number, other in enumerate(rows) if _at(other, identity, provisional_file, line)]
        if override:
            if not existing:
                raise SocomError(
                    f"{identity} has no contradiction in {provisional_file} at line {line} to replace: drop --override"
                )
            replaced = [str(rows[number].get("kind")) for number in existing]
            place = f"{provisional_file}:{line}" if line is not None else provisional_file
            plan.setdefault("notes", []).append(
                f"override contradiction {identity} in {place}: the plan gave {', '.join(replaced)}; {override_evidence.strip()}"
            )
            rows[existing[0]] = row
            for number in reversed(existing[1:]):
                del rows[number]
            change["replaced"] = replaced
        elif any(rows[number].get("kind") == kind for number in existing):
            raise SocomError(
                f"{identity} already has this {kind} contradiction in {provisional_file}: pass --override with --evidence "
                "to replace it, or --remove-contradiction"
            )
        else:
            rows.append(row)
        changes.append(change)
    return changes


def remove_contradictions(
    plan: dict[str, Any], artifacts: list[str], *, provisional_file: str, line: int | None
) -> list[dict[str, Any]]:
    """Remove each artifact's ``contradictions`` rows at that file and line (``None``: its file-level rows).

    Contradiction rows are the planner's own, so removing one needs no
    evidence; an artifact with no such row is refused.
    """

    _require_v2(plan, "--remove-contradiction")
    _contradiction_place(provisional_file, line)
    rows = _contradiction_rows(plan)
    changes = []
    for identity in artifacts:
        existing = [number for number, other in enumerate(rows) if _at(other, identity, provisional_file, line)]
        if not existing:
            raise SocomError(f"{identity} has no contradiction in {provisional_file} at line {line}")
        for number in reversed(existing):
            changes.append(
                {"artifact": identity, "contradiction_removed": rows[number].get("kind"), "provisional_file": provisional_file, "line": line}
            )
            del rows[number]
    return changes


def add_header_emits(
    plan: dict[str, Any],
    artifacts: list[str],
    *,
    header: str,
    reason: str,
    evidence: list[str] | None,
    library: str | None = None,
    override: bool = False,
    override_evidence: str | None = None,
) -> list[dict[str, Any]]:
    """Add one hand ``header_emits`` row per artifact (no ``draft_rule``).

    The artifact must be owned by an authored row of the plan.  ``header`` is
    a header under ``src/`` or, with ``library``, a provider header
    ``<name>``.  An artifact that already has a header-emit row is replaced
    only with ``override`` and its evidence, kept as a plan note.  Binding,
    letter case and reservation are checked by ``source plan validate``.
    """

    _require_v2(plan, "--header-emit")
    if reason not in EMIT_REASONS:
        raise SocomError(f"--reason must be one of {list(EMIT_REASONS)}")
    if library is not None:
        if not library.strip():
            raise SocomError("--library must name the provider library")
        if not _PROVIDER_HEADER.match(header):
            raise SocomError("a provider header is spelled <name>, as the owner's file includes it")
    elif not _workspace_path(header) or not header.casefold().endswith(HEADER_SUFFIXES):
        raise SocomError("--header-emit must be a repo-relative header path under src/ (or <name> with --library)")
    lines = _lines(evidence, "--header-emit --emit-evidence")
    if override and (not isinstance(override_evidence, str) or not override_evidence.strip()):
        raise SocomError("--override needs --evidence: why the existing header-emit row is wrong")
    if control_characters([header, reason, library or "", *lines, override_evidence or ""]):
        raise SocomError("a header-emit row may not hold control characters (U+0000-U+001F)")
    emits = plan.setdefault("header_emits", [])
    if not isinstance(emits, list):
        raise SocomError("the plan's header_emits must be a list")
    owned = {
        identity
        for row in plan.get("owners") or []
        if isinstance(row, dict) and row.get("classification") == "authored"
        for identity in map(artifact_id, row.get("artifacts") or [])
        if identity
    }
    changes = []
    for identity in artifacts:
        if identity not in owned:
            raise SocomError(f"{identity} is not owned by an authored row of this plan: decide its owner first")
        row: dict[str, Any] = {"artifact": identity, "header": header, "reason": reason, "evidence": list(lines)}
        if library is not None:
            row["library"] = library.strip()
        existing = [number for number, other in enumerate(emits) if isinstance(other, dict) and other.get("artifact") == identity]
        change: dict[str, Any] = {"artifact": identity, "header_emit": header, "reason": reason}
        if existing:
            before = emits[existing[0]]
            rule = before.get("draft_rule")
            if not override:
                raise SocomError(
                    f"{identity} already has a header-emit row ({before.get('header')}"
                    + (f", draft rule {rule}" if rule else "")
                    + "): pass --override with --evidence to replace it"
                )
            plan.setdefault("notes", []).append(
                f"override header emit {identity}: the plan gave {before.get('header')}"
                + (f" ({rule})" if rule else "")
                + f"; {override_evidence.strip()}"
            )
            change["replaced"] = before.get("header")
            emits[existing[0]] = row
            for number in reversed(existing[1:]):
                del emits[number]
        else:
            emits.append(row)
        changes.append(change)
    return changes


# -- the open view ------------------------------------------------------------------


def cache_graph(path: Path) -> str | None:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        row = connection.execute("SELECT value FROM meta WHERE key = 'graph_sha256'").fetchone()
    return row[0] if row else None


def cache_has_artifact(path: Path, identity: str) -> bool:
    """Whether the cache's graph has the artifact (a contradiction may name one outside the plan)."""

    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        return connection.execute("SELECT 1 FROM artifacts WHERE id = ?", (identity,)).fetchone() is not None


def refresh_annotations(plan: dict[str, Any], path: Path, section_of: Callable[[int], str | None]) -> bool:
    """Re-derive the plan's annotations from the cache's artifact rows; whether they changed."""

    identities = sorted(
        (
            {artifact_id(entry) for row in plan.get("owners") or [] if isinstance(row, dict) for entry in row.get("artifacts") or []}
            | {row.get("artifact") for row in plan.get("header_emits") or [] if isinstance(row, dict)}
        )
        - {None}
    )
    rows = []
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        for start in range(0, len(identities), 500):
            chunk = identities[start : start + 500]
            marks = ",".join("?" * len(chunk))
            names: dict[str, list[dict[str, Any]]] = {}
            for artifact, name, binding in connection.execute(
                f"SELECT artifact, name, binding FROM names WHERE artifact IN ({marks}) ORDER BY symbol_index", chunk
            ):
                names.setdefault(artifact, []).append({"name": name, "binding": binding})
            for identity, kind, address in connection.execute(f"SELECT id, kind, address FROM artifacts WHERE id IN ({marks})", chunk):
                rows.append({"id": identity, "kind": kind, "address": f"0x{address:x}", "names": names.get(identity, [])})
    annotations = derive_annotations(plan, {"artifacts": rows}, section_of)
    changed = plan.get("annotations") != annotations
    plan["annotations"] = annotations
    return changed


def _unit_name(row: dict[str, Any]) -> str | None:
    """The unit an owner row stands for: its translation unit, else a provider row's member label."""

    if row.get("classification") == "compiler-generated":
        return None
    if row.get("translation_unit"):
        return str(row["translation_unit"])
    return owner_label(row) if row.get("classification") == "provider" else None


def _short(name: Any, width: int = 40) -> str:
    text = str(name or "")
    return text if len(text) <= width else text[: width - 3] + "..."


def open_view(plan: dict[str, Any], path: Path, *, limit: int = 40) -> dict[str, Any]:
    """The open rows of a drafted plan with each open artifact's evidence from the cache.

    Besides the cache evidence, each open function shows its flanks: on each
    side, the nearest function a unit owns that is not a WEAK or binding-13
    copy (the plan's owner, or outside the plan a strong unit candidate),
    with the WEAK and binding-13 copies between it and the open function and
    who holds them, so a planner sees whether the row lies before or after
    the copies a unit emits.  An open WEAK or binding-13 copy also lists the
    units that reference it and, when they are one unit, that sole unit.
    The drafter's ``suggest``ion of a row is shown as it stands.
    """

    if not isinstance(plan, dict):
        raise SocomError("the plan must be a JSON object")
    open_rows = [row for row in plan.get("unresolved") or [] if isinstance(row, dict) and row.get("draft") == DRAFT_OPEN]
    owner_of: dict[str, str] = {}
    plan_unit: dict[str, str | None] = {}
    for row in plan.get("owners") or []:
        if isinstance(row, dict):
            for entry in row.get("artifacts") or []:
                identity = artifact_id(entry)
                if identity:
                    owner_of[identity] = owner_label(row)
                    plan_unit[identity] = _unit_name(row)
    for row in plan.get("unresolved") or []:
        if isinstance(row, dict) and isinstance(row.get("artifact"), str):
            owner_of.setdefault(row["artifact"], "open" if row.get("draft") == DRAFT_OPEN else "unresolved")
            plan_unit.setdefault(row["artifact"], None)
    shown = open_rows[: max(limit, 0)]
    details = []
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row

        def label(identity: str | None) -> str:
            if not identity:
                return "?"
            hit = connection.execute("SELECT name, item FROM artifacts WHERE id = ?", (identity,)).fetchone()
            name = hit["name"] if hit and hit["name"] else ""
            where = owner_of.get(identity) or (f"item {hit['item']}" if hit and hit["item"] else "no item")
            return f"{identity.rsplit(':', 1)[-1]} {name} [{where}]".replace("  ", " ")

        def unit_of(identity: str, tu: Any, strength: Any) -> str | None:
            """The plan's unit for an artifact, or outside the plan its strong unit candidate."""

            if identity in plan_unit:
                return plan_unit[identity]
            return str(tu) if tu and strength == "strong" else None

        def holder(identity: str, tu: Any, strength: Any) -> str:
            unit = unit_of(identity, tu, strength)
            if unit:
                return unit
            if identity in owner_of:
                return owner_of[identity]
            return f"{tu} {strength}" if tu else "?"

        def flank(hit: sqlite3.Row, side: str) -> dict[str, Any]:
            operator, order = ("<", "DESC") if side == "before" else (">", "ASC")
            found = connection.execute(
                f'SELECT id, address, name, weak, inline, tu, tu_strength FROM artifacts WHERE "window" = ? AND kind = \'function\' '
                f"AND address {operator} ? ORDER BY address {order} LIMIT ?",
                (hit["window"], hit["address"], FLANK_SCAN),
            ).fetchall()
            copies: list[tuple[int, str, str, str]] = []
            unanchored = 0
            anchor = unit = None
            for other in found:
                if other["weak"] or other["inline"]:
                    tag = "WEAK" if other["weak"] else "13"
                    copies.append((other["address"], tag, str(other["name"] or ""), holder(other["id"], other["tu"], other["tu_strength"])))
                    continue
                unit = unit_of(other["id"], other["tu"], other["tu_strength"])
                if unit:
                    anchor = f"{unit} 0x{other['address']:x} {_short(other['name'])}"
                    break
                unanchored += 1
            copies.sort()
            # Consecutive copies one holder holds collapse into one run.
            runs: list[list[tuple[int, str, str, str]]] = []
            for instance in copies:
                if runs and runs[-1][-1][3] == instance[3]:
                    runs[-1].append(instance)
                else:
                    runs.append([instance])
            texts = []
            for run in runs:
                tags = "/".join(sorted({value[1] for value in run}, reverse=True))
                if len(run) == 1:
                    texts.append(f"{tags} 0x{run[0][0]:x} {_short(run[0][2])} [{run[0][3]}]")
                else:
                    texts.append(f"{tags} x{len(run)} 0x{run[0][0]:x}..0x{run[-1][0]:x} [{run[0][3]}]")
            shown_runs = texts[:SHOWN_COPIES] if side == "after" else texts[-SHOWN_COPIES:]
            hidden = len(texts) - len(shown_runs)
            more = [f"+{hidden} runs"] if hidden else []
            return {
                "anchor": anchor or f"none within {FLANK_SCAN} functions",
                "unit": unit if anchor else None,
                "copies": more + shown_runs if side == "before" else shown_runs + more,
                "copy_count": len(copies),
                "unanchored": unanchored,
            }

        for row in shown:
            identity = row["artifact"]
            hit = connection.execute("SELECT * FROM artifacts WHERE id = ?", (identity,)).fetchone()
            if hit is None:
                details.append({"artifact": identity, "reason": row.get("reason"), "missing": "not in the cache's graph"})
                continue
            candidates = connection.execute(
                "SELECT tu, strength, via FROM tu_candidates WHERE artifact = ? ORDER BY rank LIMIT 3", (identity,)
            ).fetchall()
            callers = [value for (value,) in connection.execute(
                "SELECT DISTINCT site_artifact FROM refs WHERE target_artifact = ? AND site_artifact IS NOT NULL AND site_artifact != ? ORDER BY site",
                (identity, identity),
            )]
            calls = [value for (value,) in connection.execute(
                "SELECT DISTINCT target_artifact FROM refs WHERE site_artifact = ? AND target_artifact IS NOT NULL AND target_artifact != ? ORDER BY site",
                (identity, identity),
            )]
            strings = [value for (value,) in connection.execute(
                "SELECT DISTINCT text FROM file_strings WHERE artifact = ? OR referenced_by = ?", (identity, identity)
            )]
            detail = {
                "artifact": identity,
                "kind": hit["kind"],
                "size": hit["size"],
                "names": hit["names"] or None,
                "binding": hit["binding"],
                "section": hit["input_section"],
                "class": f"{hit['classification']}{':' + hit['library'] if hit['library'] else ''}{' (weak)' if hit['class_weak'] else ''}",
                "tu": [f"{tu} {strength} {via}" for tu, strength, via in candidates],
                "gnu_object": f"0x{hit['gnu_object']:x}" if hit["gnu_object"] is not None else None,
                "cluster": hit["cluster"],
                "reason": row.get("reason"),
                "callers": [label(value) for value in callers[:SHOWN_REFERENCES]] + ([f"+{len(callers) - SHOWN_REFERENCES}"] if len(callers) > SHOWN_REFERENCES else []),
                "calls": [label(value) for value in calls[:SHOWN_REFERENCES]] + ([f"+{len(calls) - SHOWN_REFERENCES}"] if len(calls) > SHOWN_REFERENCES else []),
            }
            if hit["kind"] == "gap":
                detail.update(fill=hit["fill"], labels=hit["labels"])
            if hit["inline"] or hit["weak"]:
                detail["instance"] = "inline" if hit["inline"] else "weak"
                # Who references the copy: one unit alone is the usual owner of an inline body.
                referencing: Counter[str] = Counter()
                units: set[str | None] = set()
                for value in callers:
                    other = connection.execute("SELECT tu, tu_strength FROM artifacts WHERE id = ?", (value,)).fetchone()
                    tu, strength = (other["tu"], other["tu_strength"]) if other else (None, None)
                    referencing[holder(value, tu, strength)] += 1
                    units.add(unit_of(value, tu, strength))
                detail["referencing_units"] = [f"{name} {count}" for name, count in sorted(referencing.items())]
                if len(units) == 1 and None not in units:
                    detail["sole_referencing_unit"] = next(iter(units))
            if hit["kind"] == "function":
                detail["flank_before"] = flank(hit, "before")
                detail["flank_after"] = flank(hit, "after")
            if isinstance(row.get("suggest"), dict):
                detail["suggest"] = dict(row["suggest"])
            if strings:
                detail["file_strings"] = strings[:3]
            if hit["emitted_from_header"]:
                detail["header"] = hit["emitted_from_header"]
            details.append({key: value for key, value in detail.items() if value not in (None, [], "")})
    owners_open = [
        {"row": owner_label(row), "evidence": list(row.get("evidence") or [])[:3]}
        for row in plan.get("owners") or []
        if isinstance(row, dict) and row.get("draft") == DRAFT_OPEN
    ]
    draft = plan.get("draft") if isinstance(plan.get("draft"), dict) else {}
    reservation = plan.get("reservation") if isinstance(plan.get("reservation"), dict) else None
    emitted = {row.get("artifact") for row in plan.get("header_emits") or [] if isinstance(row, dict)}
    return {
        "plan_graph_sha256": plan.get("graph_sha256"),
        "open_rows": len(open_rows),
        "shown": len(details),
        "artifacts": details,
        "open_owner_rows": owners_open,
        # The draft's unresolved header emits that no header-emit row records yet.
        "open_header_emits": [value for value in draft.get("open_header_emits") or [] if value not in emitted],
        "outside_reservation": list(draft.get("outside_reservation") or []),
        "reservation": reservation if reservation and reservation.get("status") == INFERRED_STATUS else None,
        "owner_keys": sorted({key for row in plan.get("owners") or [] if isinstance(row, dict) for key in owner_keys(row)}),
    }


def open_text(view: dict[str, Any]) -> str:
    """The open view as compact lines."""

    lines = [f"open rows {view['open_rows']} (shown {view['shown']}); plan graph {str(view['plan_graph_sha256'])[:12]}"]
    for row in view["artifacts"]:
        head = " ".join(
            str(value)
            for value in (
                row["artifact"], row.get("kind"), f"{row.get('size')}B" if row.get("size") is not None else None, row.get("names"),
                f"binding {row['binding']}" if row.get("binding") else None, row.get("instance"), row.get("section"), row.get("class"),
                f"gnu {row['gnu_object']}" if row.get("gnu_object") else None, f"cluster {row['cluster']}" if row.get("cluster") else None,
            )
            if value
        )
        lines.append(head)
        for key in ("tu", "callers", "calls", "referencing_units", "file_strings"):
            if row.get(key):
                lines.append(f"  {key}: " + "; ".join(row[key]))
        for key in ("sole_referencing_unit", "fill", "labels", "header", "missing"):
            if row.get(key):
                lines.append(f"  {key}: {row[key]}")
        for side in ("before", "after"):
            flank = row.get(f"flank_{side}")
            if not flank:
                continue
            chain = [flank["anchor"], *flank["copies"], "this"] if side == "before" else ["this", *flank["copies"], flank["anchor"]]
            unanchored = f" ({flank['unanchored']} unanchored between)" if flank["unanchored"] else ""
            lines.append(f"  {side}: " + " < ".join(chain) + unanchored)
        if row.get("suggest"):
            suggest = row["suggest"]
            lines.append(
                f"  suggest: {suggest.get('owner')} {suggest.get('confidence')} ({suggest.get('rule')}): {suggest.get('basis')}"
            )
        lines.append(f"  open: {row.get('reason')}")
    for row in view["open_owner_rows"]:
        lines.append(f"open owner row {row['row']}: " + " | ".join(row["evidence"]))
    if view["open_header_emits"]:
        lines.append("open header emits: " + ", ".join(view["open_header_emits"]))
    if view["outside_reservation"]:
        lines.append("outside reservation: " + ", ".join(view["outside_reservation"]))
    if view["reservation"]:
        reservation = view["reservation"]
        lines.append(f"reservation inferred {', '.join(reservation.get('directories') or [])}: {reservation.get('reason')}")
    lines.append("owners: " + ", ".join(view["owner_keys"]))
    return "\n".join(lines) + "\n"
