"""Compact planner views and single-decision edits of stage 4 owner plans.

``source plan open`` lists only what a planner still has to decide in a
drafted plan (open unresolved rows, open owner rows, open header emits and
an inferred reservation) with each open artifact's evidence from the source
query cache, so a planner never loads or rewrites the whole plan JSON.

``source plan decide`` records one decision: it moves the named artifacts
into one existing owner row (an entry ``{artifact, confidence, basis}``
without ``draft_rule``: hand-written, for the reviewer) or into an
``unresolved`` row with a real reason.  It loads and dumps the plan as JSON,
never as text, refuses control characters, and refuses to move an artifact
a draft rule decided unless ``--override`` gives the evidence (recorded as a
plan note).  The owner row's confidence follows its weakest entry, and the
annotations are re-derived when the cache holds the plan's graph.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from .source_plan import (
    CONFIDENCES,
    DRAFT_OPEN,
    INFERRED_STATUS,
    artifact_id,
    control_characters,
    derive_annotations,
)
from .util import SocomError

SHOWN_REFERENCES = 4


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
    """Record one decision for ``artifacts`` in ``plan`` (in place); the changes made."""

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
    # An owner row emptied by the moves is dropped (a row lists its artifacts).
    kept = []
    for row in owners:
        if isinstance(row, dict) and not row.get("artifacts"):
            changes.append({"row_removed": owner_label(row)})
            continue
        if isinstance(row, dict):
            _row_confidence(row)
        kept.append(row)
    plan["owners"] = kept
    if control_characters(plan):
        raise SocomError("the plan holds control characters; fix them before deciding (source plan validate lists them)")
    return changes


# -- the open view ------------------------------------------------------------------


def cache_graph(path: Path) -> str | None:
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
        row = connection.execute("SELECT value FROM meta WHERE key = 'graph_sha256'").fetchone()
    return row[0] if row else None


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


def open_view(plan: dict[str, Any], path: Path, *, limit: int = 40) -> dict[str, Any]:
    """The open rows of a drafted plan with each open artifact's evidence from the cache."""

    if not isinstance(plan, dict):
        raise SocomError("the plan must be a JSON object")
    open_rows = [row for row in plan.get("unresolved") or [] if isinstance(row, dict) and row.get("draft") == DRAFT_OPEN]
    owner_of: dict[str, str] = {}
    for row in plan.get("owners") or []:
        if isinstance(row, dict):
            for entry in row.get("artifacts") or []:
                identity = artifact_id(entry)
                if identity:
                    owner_of[identity] = owner_label(row)
    for row in plan.get("unresolved") or []:
        if isinstance(row, dict) and isinstance(row.get("artifact"), str):
            owner_of.setdefault(row["artifact"], "unresolved")
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
    return {
        "plan_graph_sha256": plan.get("graph_sha256"),
        "open_rows": len(open_rows),
        "shown": len(details),
        "artifacts": details,
        "open_owner_rows": owners_open,
        "open_header_emits": list(draft.get("open_header_emits") or []),
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
                row.get("binding"), row.get("instance"), row.get("section"), row.get("class"),
                f"gnu {row['gnu_object']}" if row.get("gnu_object") else None, f"cluster {row['cluster']}" if row.get("cluster") else None,
            )
            if value
        )
        lines.append(head)
        for key in ("tu", "callers", "calls", "file_strings"):
            if row.get(key):
                lines.append(f"  {key}: " + "; ".join(row[key]))
        for key in ("fill", "labels", "header", "missing"):
            if row.get(key):
                lines.append(f"  {key}: {row[key]}")
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
