"""Stage 4: a header move stated by owner plans (``header_moves``).

A header-emit row names the header an inline, weak or template instance is
emitted from.  When that header itself moves (a user placement decision puts
a class's header next to its implementation), every segment plan that emits
from it states the move once::

    "header_moves": [
      {"from": "src/gamez/zNode/node_action.h", "to": "src/gamez/zFTS/fts_action.h",
       "reason": "user decision ...", "evidence": ["..."]}
    ]

and names the new header in its header-emit rows.  ``source plan validate``
checks the statement (``check_header_moves``): the old header exists in the
applied state, both paths lie inside the reservation, a header-emit row names
the new header and no row names the old one, and the other plans agree
(``cross_plan``).  ``progress apply-source-plan`` performs the move as a move
(``source_apply.prepare_apply``): the file goes to the new path with its
authored content byte for byte (its include guard included) and its generated
blocks re-rendered.  The record lists it under ``moves`` with ``"kind":
"header"`` (evidence ``source-moved <from> -> <to> header``); a second apply
that states the same move finds it done and records it too.

The tools rewrite no ``#include`` line: stage 4 owns the generated blocks and
the file layout, never authored content.  ``includers`` lists every file
under ``src/`` and ``port/`` that still includes the old path, by kind:

* ``fenced``: a line a stage 5 ``@socom-skeleton decl include`` region
  generates (the item's stored render holds it there).  The skeleton
  re-apply of the file's item writes the new path (``progress
  rebase-function-order`` sends that item back);
* ``authored``: any other ``#include`` line, also one the port lane added
  inside such a region (``in_region``).  It is the worker's hand edit, and
  the checks report the edited file as drift, never as a failure.

Stage 5 follows a recorded header move (``order_reopen``): the frozen base's
copy moves with it, the body snapshot is re-keyed and the skeleton item that
reserved the old path reserves the new one.
"""

from __future__ import annotations

import os.path
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .util import SocomError, load_json

HEADER_MOVE_FIELDS = ("from", "to", "reason", "evidence")
HEADER_MOVE_KIND = "header"
# The trees whose ``#include`` lines may name a header under src/.
INCLUDER_ROOTS = ("src", "port")
INCLUDER_SUFFIXES = (".c", ".cc", ".cp", ".cpp", ".cxx", ".s", ".h", ".hh", ".hpp", ".inc")
_INCLUDE = re.compile(r'^\s*#\s*include\s*(?:"([^"]+)"|<([^>]+)>)')
_FENCE = re.compile(r"^\s*/\* @socom-skeleton (decl|end) include \*/\s*$")
_SHOWN = 12


def _shown(values: list[str]) -> str:
    return ", ".join(values[:_SHOWN]) + (f", +{len(values) - _SHOWN} more" if len(values) > _SHOWN else "")


# -- the statement ------------------------------------------------------------------------------


def plan_header_moves(plan: Any) -> list[tuple[str, str]]:
    """The (from, to) pairs a plan states, in order; malformed rows are skipped (validation reports them)."""

    rows = plan.get("header_moves") if isinstance(plan, dict) else None
    return [
        (row["from"], row["to"])
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict) and isinstance(row.get("from"), str) and isinstance(row.get("to"), str)
    ]


def emit_headers(plan: Any) -> set[str]:
    """The workspace headers a plan's header-emit rows name (provider headers excluded)."""

    return {
        row["header"]
        for row in ((plan.get("header_emits") if isinstance(plan, dict) else None) or [])
        if isinstance(row, dict) and isinstance(row.get("header"), str) and row.get("library") is None
    }


def is_header_move(row: Any) -> bool:
    """Whether a ``source_apply`` record's ``moves`` row is a header move."""

    return isinstance(row, dict) and row.get("kind") == HEADER_MOVE_KIND and bool(row.get("from")) and bool(row.get("to"))


def recorded_header_moves(tracker: dict[str, Any], applies: list[str] | None = None) -> dict[str, str]:
    """{from: to} of the header moves the current stage 4 apply records list (``applies``: only those items')."""

    from .source_plan import SOURCE_APPLY_KINDS

    found: dict[str, str] = {}
    for item in tracker.get("work_items") or []:
        record = item.get("source_apply")
        if item.get("kind") not in SOURCE_APPLY_KINDS or not isinstance(record, dict):
            continue
        if applies is not None and item.get("id") not in applies:
            continue
        for row in record.get("moves") or []:
            if is_header_move(row):
                found[str(row["from"])] = str(row["to"])
    return dict(sorted(found.items()))


# -- validation ---------------------------------------------------------------------------------


def check_header_moves(
    root: Path,
    tracker: dict[str, Any],
    item: dict[str, Any],
    plan: dict[str, Any],
    placement: dict[str, Any] | None,
    applied: dict[str, Any] | None,
    cited_files: set[str],
    problems: list[str],
    review: list[str],
) -> list[dict[str, Any]]:
    """Check a plan's ``header_moves``; the report rows ``{from, to, state, includers}``.

    ``cited_files`` holds the casefolded paths the plan's owner and
    header-emit rows cite; ``applied`` the applied state
    (``source_apply.applied_state``), whose header moves count as done.
    """

    from .source_plan import HEADER_SUFFIXES, SEGMENT_PLAN_KIND, _directories_text, _path_state, _strings, _within, _workspace_path

    rows = plan.get("header_moves")
    if rows is None:
        found: list[dict[str, Any]] = []
    elif not isinstance(rows, list):
        problems.append("header_moves must be a list")
        found = []
    else:
        found = rows
    if found and item.get("kind") != SEGMENT_PLAN_KIND:
        problems.append("only a segment plan states a header move: its apply performs it (a provider or data plan names "
                        "the new header in its rows and writes nothing)")
    done = {(str(row.get("from")), str(row.get("to"))) for row in (applied or {}).get("moves") or [] if is_header_move(row)}
    emitted = emit_headers(plan)
    report: list[dict[str, Any]] = []
    sources: set[str] = set()
    targets: set[str] = set()
    for number, row in enumerate(found, 1):
        if (not isinstance(row, dict) or set(row) != set(HEADER_MOVE_FIELDS)
                or not isinstance(row.get("from"), str) or not isinstance(row.get("to"), str)):
            problems.append(f"header_moves row {number} must be {{{', '.join(HEADER_MOVE_FIELDS)}}} with string paths")
            continue
        source, target = row["from"], row["to"]
        label = f"header_moves {source} -> {target}"
        if not isinstance(row.get("reason"), str) or not row["reason"].strip() or not _strings(row.get("evidence")):
            problems.append(f"{label} needs a reason and evidence lines")
        valid = True
        for path, what in ((source, "from"), (target, "to")):
            if not _workspace_path(path) or not path.casefold().endswith(HEADER_SUFFIXES):
                problems.append(f"{label}: {what} must be a repo-relative header path under src/")
                valid = False
        if not valid:
            continue
        if source == target:
            problems.append(f"{label}: a move needs two different paths")
            continue
        if source in sources or target in targets:
            problems.append(f"{label} is listed twice (one statement per header)")
        if source in targets or target in sources:
            problems.append(f"{label}: a header moves once (no chain of moves in one plan)")
        sources.add(source)
        targets.add(target)
        if placement is not None:
            outside = [path for path in (source, target) if not _within(path, placement["directories"])]
            if outside:
                problems.append(
                    f"{label}: {_shown(outside)} lies outside the reservation of {placement['apply_item']} "
                    f"({_directories_text(placement['directories'])}): the apply removes the old header and writes the new "
                    "one, so record the correction in reservation"
                )
        if target not in emitted:
            problems.append(f"{label}: no header-emit row names {target} (a plan states the move of a header it emits from)")
        if source.casefold() in cited_files:
            problems.append(f"{label}: an owner or header-emit row still names {source}")
        for retired in plan.get("retire_files") or []:
            if isinstance(retired, dict) and retired.get("path") in (source, target):
                problems.append(f"{label}: {retired.get('path')} is also listed in retire_files (the move removes the old "
                                "header with its content; nothing is retired)")
        case, actual = _path_state(root, target)
        if case == "case":
            problems.append(f"{label}: {target} differs in letter case from {actual} on disk")
        has_source = _path_state(root, source)[0] == "exact" and (root / source).is_file()
        has_target = (root / target).is_file()
        if (source, target) in done:
            state = "applied"
            if has_source:
                problems.append(f"{label}: the apply moved the header but {source} exists again")
            if not has_target:
                problems.append(f"{label}: the apply moved the header but {target} is missing")
        else:
            state = "pending"
            if not has_source:
                problems.append(f"{label}: {source} must name an existing header under src/ exactly")
            if has_target:
                problems.append(f"{label}: {target} exists already (a header move needs a free target)")
        report.append({"from": source, "to": target, "state": state, "includers": includers(root, tracker, source, target),
                       "own_relative_includes": own_relative_includes(root, source, target)})
    moves = [(row["from"], row["to"]) for row in report]
    cross_plan(root, tracker, item, moves, emitted, problems, review)
    for row in report:
        counts = _includer_counts(row["includers"])
        if counts:
            review.append(
                f"header_moves {row['from']} -> {row['to']}: {sum(counts.values())} #include lines still name the old path "
                f"({counts.get('fenced', 0)} generated by stage 5 include regions, rewritten by the skeleton re-apply of their items; "
                f"{counts.get('authored', 0)} authored, the worker's hand edits): "
                + _shown([f"{entry['path']}:{entry['line']}" for entry in row["includers"]])
            )
    return report


def _includer_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    return counts


# (path, mtime, size) -> (header-emit headers, header moves) of a plan file: the gate validates every plan against
# every other one, and only these two facts of the other plans are read.
_PLAN_FACTS: dict[tuple[str, int, int], tuple[frozenset[str], tuple[tuple[str, str], ...]] | None] = {}


def _plan_facts(path: Path) -> tuple[frozenset[str], tuple[tuple[str, str], ...]] | None:
    """(the headers a plan file's header-emit rows name, its header moves), or None for an unreadable plan."""

    try:
        stat = path.stat()
    except OSError:
        return None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _PLAN_FACTS:
        try:
            plan = load_json(path)
        except SocomError:
            plan = None
        _PLAN_FACTS[key] = (frozenset(emit_headers(plan)), tuple(plan_header_moves(plan))) if isinstance(plan, dict) else None
    return _PLAN_FACTS[key]


def _other_plans(root: Path, tracker: dict[str, Any], item_id: str) -> list[dict[str, Any]]:
    """The other plans a header move must agree with: accepted, awaiting acceptance, or under an open amendment."""

    from .source_plan import CROSS_PLAN_STATUSES, SEGMENT_PLAN_KIND, SOURCE_PLAN_KINDS, plan_path
    from .tracker import open_source_amendments

    amended = {str(row.get("item")): str(row.get("id")) for row in open_source_amendments(tracker)}
    found: list[dict[str, Any]] = []
    for item in tracker.get("work_items") or []:
        if item.get("kind") not in SOURCE_PLAN_KINDS or item.get("id") == item_id:
            continue
        status = item.get("status")
        if status not in CROSS_PLAN_STATUSES and item["id"] not in amended:
            continue
        facts = _plan_facts(root / plan_path(item["id"]))
        if facts is None:
            continue  # a missing or unreadable plan file: the unit check notes it
        found.append({
            "item": item["id"], "status": status, "segment": item.get("kind") == SEGMENT_PLAN_KIND,
            "amendment": amended.get(item["id"]) if status not in CROSS_PLAN_STATUSES else None,
            "emits": set(facts[0]), "moves": list(facts[1]),
        })
    return found


def pair_conflicts(
    moves: list[tuple[str, str]], emits: set[str], segment: bool,
    other_moves: list[tuple[str, str]], other_emits: set[str], other_segment: bool, other: str,
) -> list[str]:
    """What one plan's header moves and emits contradict in another plan's (``other`` names it)."""

    found: list[str] = []
    for source, target in moves:
        if source in other_emits:
            found.append(f"header_moves {source} -> {target}: {other} still names {source} in a header-emit row; it must "
                         f"name {target}" + (" and state the same move" if other_segment else ""))
        if other_segment and target in other_emits and (source, target) not in other_moves:
            found.append(f"header_moves {source} -> {target}: {other} emits into {target} without stating the move")
        for theirs_source, theirs_target in other_moves:
            if (source, target) == (theirs_source, theirs_target):
                continue
            if source == theirs_source or target == theirs_target or source == theirs_target or target == theirs_source:
                found.append(f"header_moves {source} -> {target} contradicts {other}'s {theirs_source} -> {theirs_target}")
    for source, target in other_moves:
        if source in emits:
            found.append(f"{other} moves {source} to {target}: this plan's header-emit rows still name {source}; name "
                         f"{target}" + (" and state the same move" if segment else ""))
        if segment and target in emits and (source, target) not in moves:
            found.append(f"{other} moves {source} to {target}: this plan emits into {target} without stating the move")
    return found


def cross_plan(
    root: Path, tracker: dict[str, Any], item: dict[str, Any], moves: list[tuple[str, str]], emits: set[str],
    problems: list[str], review: list[str],
) -> None:
    """One header moves once whichever plans emit from it: compare with the other plans.

    A disagreement with an accepted plan is a problem.  With a plan awaiting
    acceptance, or one an open amendment sent back for revision (its file is
    still the plan being revised), it is a review note: the gate checks of
    ``progress accept-source-amendment`` hold every accepted plan to it.
    """

    from .source_plan import SEGMENT_PLAN_KIND

    segment = item.get("kind") == SEGMENT_PLAN_KIND
    others = _other_plans(root, tracker, str(item.get("id")))
    if not moves and not any(row["moves"] for row in others):
        return
    for other in others:
        where = f"{other['item']} ({other['status']}" + (f", amended by {other['amendment']}" if other["amendment"] else "") + ")"
        found = pair_conflicts(moves, emits, segment, other["moves"], other["emits"], other["segment"], where)
        (problems if other["status"] == "accepted" else review).extend(found)


def header_move_conflicts(plans: list[tuple[str, dict[str, Any], bool]]) -> list[str]:
    """The gate's cross-plan check over every accepted plan ``(item, plan, is a segment plan)``: each problem once."""

    rows = [(item_id, plan_header_moves(plan), emit_headers(plan), segment) for item_id, plan, segment in plans]
    if not any(moves for _item, moves, _emits, _segment in rows):
        return []
    problems: list[str] = []
    for item_id, moves, _emits, segment in rows:
        if not moves:
            continue
        for other_id, other_moves, other_emits, other_segment in rows:
            if other_id == item_id:
                continue
            # From the stating plan's side only (no emits of its own): the other plan's statements are its own rows.
            found = pair_conflicts(moves, set(), segment, other_moves, other_emits, other_segment, other_id)
            problems.extend(f"{item_id}: {text}" for text in found if " contradicts " not in text or item_id < other_id)
    return problems


def unrecorded_moves(plan: dict[str, Any], record: dict[str, Any]) -> list[str]:
    """The plan's header moves its apply record does not list (``source apply-check``)."""

    recorded = {(str(row.get("from")), str(row.get("to"))) for row in record.get("moves") or [] if is_header_move(row)}
    return [f"the plan's header move {source} -> {target} is not recorded: re-apply"
            for source, target in plan_header_moves(plan) if (source, target) not in recorded]


# -- includers ----------------------------------------------------------------------------------


def include_spelling(header: str, includer: str) -> str:
    """How ``includer`` names ``header``: its bare name in the same directory, else its path from src/."""

    if PurePosixPath(header).parent == PurePosixPath(includer).parent:
        return PurePosixPath(header).name
    return header[len("src/"):] if header.startswith("src/") else header


def _resolves(included: str, includer: str, quoted: bool) -> set[str]:
    found = {f"src/{included}"}
    if quoted:
        directory = PurePosixPath(includer).parent.as_posix()
        found.add(os.path.normpath(f"{directory}/{included}").replace("\\", "/"))
    return found


def include_lines(text: str, includer: str, header: str) -> list[tuple[int, str, bool]]:
    """(line number, line, inside a stage 5 include region) of each ``#include`` in ``text`` that names ``header``."""

    found: list[tuple[int, str, bool]] = []
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        fence = _FENCE.match(line)
        if fence:
            fenced = fence.group(1) == "decl"
            continue
        match = _INCLUDE.match(line)
        if match and header in _resolves(match.group(1) or match.group(2), includer, match.group(1) is not None):
            found.append((number, line.strip(), fenced))
    return found


def stored_renders(root: Path, tracker: dict[str, Any] | None) -> dict[str, tuple[str, bytes | None]]:
    """{path: (skeleton item, the stored render of its last skeleton write or None)} of every skeleton-written file.

    The render is the record row's (``order_skeleton_merge.record_ancestor``),
    read from the blob store: what stage 5 generated for the file, whatever
    ``src/`` holds now.
    """

    if tracker is None:
        return {}
    from .order_skeleton_merge import get_blob, record_ancestor
    from .order_skeleton_route import current_rows, skeleton_items, stage4_created

    created = stage4_created(tracker)
    found: dict[str, tuple[str, bytes | None]] = {}
    for item in skeleton_items(tracker):
        record = item.get("order_skeleton")
        if isinstance(record, dict):
            for row in current_rows(record, created):
                found[str(row.get("path"))] = (item["id"], get_blob(root, record_ancestor(row)))
    return found


def generated_include(text: str, includer: str, header: str) -> bool:
    """Whether a render's stage 5 include region names ``header``."""

    return any(fenced for _line, _text, fenced in include_lines(text, includer, header))


def includers(root: Path, tracker: dict[str, Any] | None, header: str, target: str | None = None) -> list[dict[str, Any]]:
    """Every ``#include`` line under ``src/`` and ``port/`` that names ``header``, in path and line order.

    ``{path, line, text, kind}``.  ``kind`` is ``fenced`` for a line a stage 5
    ``@socom-skeleton decl include`` region generates: ``item`` names the
    skeleton item that reserves the file, whose re-apply rewrites the line.
    A line inside a region counts as generated when the item's stored render
    holds the include there (or when no render is stored to tell).  Every
    other line is ``authored``, a hand edit; ``in_region`` marks one the port
    lane added inside a region.  With ``target`` each row also suggests the
    new spelling.
    """

    owners: dict[str, str] = {}
    renders: dict[str, tuple[str, bytes | None]] = {}
    if tracker is not None:
        from .order_skeleton_route import file_owners

        owners = file_owners(tracker)
        renders = stored_renders(root, tracker)
    name = PurePosixPath(header).name.encode("utf-8", "surrogateescape")
    rows: list[dict[str, Any]] = []
    for top in INCLUDER_ROOTS:
        base = root / top
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in INCLUDER_SUFFIXES:
                continue
            data = path.read_bytes()
            if name not in data:
                continue
            relative = path.relative_to(root).as_posix()
            render = (renders.get(relative) or (None, None))[1]
            generated = render is None or generated_include(render.decode("utf-8", "surrogateescape"), relative, header)
            for number, line, fenced in include_lines(data.decode("utf-8", "surrogateescape"), relative, header):
                row: dict[str, Any] = {"path": relative, "line": number, "text": line,
                                       "kind": "fenced" if fenced and generated else "authored"}
                if fenced and generated:
                    row["item"] = owners.get(relative)
                elif fenced:
                    row["in_region"] = True  # the port lane's line inside the region: the render does not generate it
                if target is not None:
                    row["suggested"] = f'#include "{include_spelling(target, relative)}"'
                rows.append(row)
    return rows


def own_relative_includes(root: Path, source: str, target: str) -> list[dict[str, Any]]:
    """The moved header's own quoted includes that resolve from its old directory only; ``[{line, text, suggested}]``.

    The header's authored content moves byte for byte, so an include spelled
    relative to the old directory (``#include "znode.h"``) no longer resolves
    from the new one: a hand edit, like the include guard.
    """

    path = root / target if (root / target).is_file() else root / source
    if not path.is_file():
        return []
    old, new = PurePosixPath(source).parent.as_posix(), PurePosixPath(target).parent.as_posix()
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_bytes().decode("utf-8", "surrogateescape").splitlines(), 1):
        match = _INCLUDE.match(line)
        if not match or match.group(1) is None:
            continue
        included = match.group(1)
        beside = os.path.normpath(f"{old}/{included}").replace("\\", "/")
        if not (root / beside).is_file() or (root / "src" / included).is_file():
            continue
        if (root / os.path.normpath(f"{new}/{included}")).is_file():
            continue
        rows.append({"line": number, "text": line.strip(),
                     "suggested": f'#include "{beside[len("src/"):] if beside.startswith("src/") else beside}"'})
    return rows


def header_move_report(root: Path, tracker: dict[str, Any], moves: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Per header move: where the files are, and the ``#include`` lines that still name the old path.

    The report of ``progress apply-source-plan`` and ``source apply-check``.
    A stale include is never a stage 4 failure (authored content, or a stage
    5 region); it is listed until the hand edit or the skeleton re-apply.
    """

    from .order_reopen import held_items

    held = held_items(tracker)
    report = []
    for source, target in moves:
        rows = includers(root, tracker, source, target)
        fenced = [row for row in rows if row["kind"] == "fenced"]
        items = sorted({str(row.get("item")) for row in fenced if row.get("item")})
        report.append({
            "from": source,
            "to": target,
            "from_exists": (root / source).is_file(),
            "to_exists": (root / target).is_file(),
            "authored_content": "moved byte for byte; the include guard and the header's own relative includes are "
                                "authored content and stay as written (hand edits, reported as drift)",
            "own_relative_includes": own_relative_includes(root, source, target),
            "stale_includers": rows,
            "stale_authored": sorted({row["path"] for row in rows if row["kind"] == "authored"}),
            "stale_fenced": sorted({row["path"] for row in fenced}),
            "fenced_items": [{"item": item_id, "held_by": held.get(item_id)} for item_id in items],
        })
    return report
