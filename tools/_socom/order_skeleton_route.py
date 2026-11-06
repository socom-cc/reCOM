"""Stage 5 phase B round 3b: the governed skeleton route that writes ``src/``.

The skeleton writer (``order_skeleton_write``, ``order_skeleton_headers``) and
its static checks (``order_skeleton_check``) render the whole tree from the
skeleton manifest, the frozen body snapshot, the accepted order plans and the
``src/`` the manifest was built on.  This module puts that render into
``src/`` under the tracker's leases:

* ``progress add-order-skeleton-prepare`` (BD3) adds the serialized item
  ``socom:work:order-skeleton-prepare``.  It owns every header the writer
  changes or creates (and the headers a waiting by-value type would be
  defined in), the unbuilt holding files and the orphan deletions; each
  ``order-segment-NNN-apply`` then waits for it and reserves exactly its
  units' files.  The order plans and their acceptances are not touched.
* ``progress apply-order-skeleton`` writes one item's files.  The first write
  freezes the base: a copy of ``src/`` under ``build/stage5/skeleton-route/base``
  (its digest must be the manifest's).  Every apply renders the whole tree
  from that base into ``build/stage5/skeleton-route/render`` and runs the
  static checks over it (determinism, S1-S5, S7); it refuses stale inputs (the
  plan SHA-256s, the stage 4 baseline, the manifest, the snapshot, the base),
  a render that changes a file no skeleton item reserves or a file of another
  applied item, and a file of its own that changed outside the route.  It then
  writes its own files, byte for byte the render's, and records each file's
  before and after SHA-256 (LF-normalized), its stage 4 block digest, the
  write and manifest digests, the flags by kind, the derived local-static
  order conflicts and the rows still waiting.
* ``order skeleton decide`` settles one waiting row in the item's decisions
  file (``build/stage5/skeleton-decisions``), which the writer reads: a row
  nobody decides stays waiting and flagged.
* ``order skeleton apply-check`` re-renders and re-checks, and compares the
  record with ``src/``; ``progress handoff-order-skeleton`` (the worker) and
  ``progress accept-order-skeleton`` (an independent verifier, not a worker of
  any skeleton item and not a tool maintainer) both re-run it.

Stage 4 keeps its chain of custody: a file written by an accepted skeleton
item whose content is that record's "after", whose "before" is the stage 4
recorded content and whose stage 4 blocks are byte-identical counts as the
stage 4 file (``skeleton_custody``), and a stage 4 write refuses a file an
accepted or handed-off skeleton item wrote until that item is reopened.
"""

from __future__ import annotations

import copy
import hashlib
import re
import shutil
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from .order_plan import (
    ORDER_APPLY_KIND,
    ORDER_PREPARE_KIND,
    ORDER_SKELETON_KINDS,
    ORDER_SKELETON_PREPARE_ID,
    ORDER_STAGE,
    segment_item_id,
    stage4_baseline,
)
from .order_skeleton_merge import record_ancestor
from .util import SocomError, atomic_write_json, canonical_json, load_json

ROUTE_DIR = "build/stage5/skeleton-route"
BASE_DIR = f"{ROUTE_DIR}/base"
RENDER_DIR = f"{ROUTE_DIR}/render"
CHECK_DIR = f"{ROUTE_DIR}/check"
MANIFEST_PATH = "build/stage5/skeleton-manifest.json"
SNAPSHOT_PATH = "build/stage5/provisional-bodies.json"
RECORD_KIND = "socom-order-skeleton-apply"
RECORD_SCHEMA = 1
APPLY_ROUTE = "progress apply-order-skeleton"
HANDOFF_ROUTE = "progress handoff-order-skeleton"
ACCEPT_ROUTE = "progress accept-order-skeleton"
EVIDENCE_PREFIX = "order-skeleton-"
RECORD_CITATION = "order-skeleton-record-sha256:"
# A tool maintainer changes the route's own checks: it never accepts a skeleton item.
MAINTAINER_MARKER = "tool-maintainer"
PREPARE_ACTIONS = ("header", "new-header", "holding", "orphan-kept")
_SHOWN = 12


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _sha(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(_lf(data)).hexdigest()


def _shown(values: list[str]) -> str:
    return ", ".join(values[:_SHOWN]) + (f", +{len(values) - _SHOWN} more" if len(values) > _SHOWN else "")


def _by_id(tracker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in tracker.get("work_items") or [] if isinstance(row, dict) and "id" in row}


def skeleton_items(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in tracker.get("work_items") or [] if row.get("kind") in ORDER_SKELETON_KINDS]


def apply_item_id(segment: int) -> str:
    return f"{segment_item_id(segment)}-apply"


def record_sha256(record: dict[str, Any]) -> str:
    return _digest(record)


def blocks_sha256(data: bytes | None) -> str | None:
    """Digest of a file's stage 4 annotation blocks (LF-normalized), or None for no file."""

    from .source_apply import parse_blocks

    if data is None:
        return None
    _bom, blocks, _rest = parse_blocks(_lf(data).decode("utf-8", "surrogateescape"))
    return _digest(sorted(blocks.items()))


# -- the prepare item (BD3) ----------------------------------------------------------------


def prepare_reservations(rendered: dict[str, Any], inputs: Any) -> tuple[list[str], dict[str, list[str]], dict[str, int]]:
    """(the prepare item's files, each segment apply's unit files, counts) from a whole-tree render.

    The prepare owns every header the writer changes or creates, the holding
    files, the orphan files it keeps or deletes, and the header a waiting
    by-value type would be defined in once it is decided; an apply owns its
    units' files.
    """

    manifest = rendered["manifest"]
    if manifest["selection"] != {"all": True}:
        raise SocomError("the reservations come from the whole-tree render")
    units: dict[str, list[str]] = {}
    prepare: set[str] = set()
    counts: Counter = Counter()
    for row in manifest["files"]:
        if row["action"] == "unit":
            units.setdefault(apply_item_id(row["segment"]), []).append(row["path"])
        elif row["action"] in PREPARE_ACTIONS:
            prepare.add(row["path"])
            counts[row["action"]] += 1
        else:
            raise SocomError(f"{row['path']}: unknown write action {row['action']!r}")
    for row in manifest["deleted"]:
        prepare.add(row["path"])
        counts["orphan-deleted"] += 1
    unit_paths = {path for paths in units.values() for path in paths}
    for row in waiting_rows(rendered, inputs):
        where = row.get("placement")
        if row["kind"] == "type-no-record" and where and where not in unit_paths and where not in prepare:
            prepare.add(where)
            counts["decision-header"] += 1
    return (sorted(prepare, key=str.casefold), {key: sorted(value, key=str.casefold) for key, value in sorted(units.items())},
            dict(sorted(counts.items())))


# -- waiting rows and their owners -----------------------------------------------------------


def waiting_rows(rendered: dict[str, Any], inputs: Any) -> list[dict[str, Any]]:
    """The rows ``order skeleton decide`` settles, each with its key, option and the item whose files it lands in."""

    from .order_skeleton_write import DECISION_KINDS

    manifest = rendered["manifest"]
    unit_paths = {unit["unit"]: unit["workspace_path"] for _number, unit in inputs.units}
    segment_of_path = {unit["workspace_path"]: number for number, unit in inputs.units}
    functions = {(unit["unit"], row["name"]): row["artifact"] for _number, unit in inputs.units for row in unit["functions"]}
    rows: list[dict[str, Any]] = []
    for row in manifest["waiting"]:
        kind = row["kind"]
        base = {"kind": kind, "name": row.get("name"), "unit": row.get("unit"), "segment": row.get("segment"),
                "detail": row.get("detail"), "option": DECISION_KINDS.get(kind)}
        if kind == "overload-tie":
            rows.append({**base, "key": row["body"], "candidates": row.get("candidates") or [], "item": ORDER_SKELETON_PREPARE_ID})
        elif kind == "local-class-owner" and row.get("members"):
            # The default owner's row: one waiting row per member of the function-local class.
            for name in row["members"]:
                rows.append({**base, "key": functions[(row["unit"], name)], "name": name, "default_owner": row.get("name"),
                             "item": apply_item_id(row["segment"])})
        else:
            rows.append({**base, "key": row.get("artifact"), "item": apply_item_id(row["segment"])})
    types = {row.get("type"): row for row in inputs.manifest["declarations"]["types"]}
    readable = {_readable(tuple(row["chain"])): row for row in inputs.manifest["declarations"]["types"] if row.get("chain")}
    for row in (manifest.get("headers") or {}).get("waiting") or []:
        if row["kind"] != "type-no-record":
            continue
        record = readable.get(row["type"]) or types.get(row["type"]) or {}
        where = (record.get("placement") or {}).get("path")
        segment = segment_of_path.get(where)
        rows.append({"kind": "type-no-record", "key": record.get("mangled"), "name": row["type"], "units": row.get("units"),
                     "detail": row.get("detail"), "option": "type", "placement": where,
                     "item": apply_item_id(segment) if segment is not None else ORDER_SKELETON_PREPARE_ID})
    del unit_paths
    return sorted(rows, key=lambda row: (row["item"], row["kind"], str(row.get("key"))))


def _readable(chain: tuple[str, ...]) -> str:
    return "::".join("(anonymous namespace)" if part.startswith("@unnamed@") else part for part in chain)


# -- inputs, base and render -------------------------------------------------------------------


def started(tracker: dict[str, Any]) -> bool:
    """Whether any skeleton item has written src/ (a record, current or in its review history)."""

    for item in skeleton_items(tracker):
        if isinstance(item.get("order_skeleton"), dict):
            return True
        if any(isinstance(entry, dict) and "order_skeleton" in entry for entry in item.get("review_history") or []):
            return True
    return False


def base_root(root: Path) -> Path:
    return root / BASE_DIR


def _missing_base() -> SocomError:
    return SocomError(f"{BASE_DIR}/src is missing: the frozen base the skeleton items were written from is gone "
                      "(it is a frozen input like the body snapshot; restore it before any further skeleton work)")


def provisional_root(root: Path, tracker: dict[str, Any]) -> Path | None:
    """The root whose ``src/`` holds the skeleton generator's provisional inputs, for the read-only commands.

    ``order skeleton manifest``, ``write`` and ``check`` read every provisional
    input (headers, bodies, preamble, file-scope data) from the route's frozen
    base once it exists: after a skeleton write, ``src/`` holds skeletons, never
    provisional input.  Before the base exists that is ``src/`` itself (None).
    A route that has written ``src/`` without its base is refused.
    """

    base = base_root(root)
    if (base / "src").is_dir():
        return base
    if started(tracker):
        raise _missing_base()
    return None


def tree_sha256(base: Path) -> str:
    from .order_skeleton_write import tree_digest

    return tree_digest(base)


def route_inputs(root: Path, tracker: dict[str, Any], *, manifest_path: Path, snapshot_path: Path) -> tuple[Any, Path | None]:
    """(the writer's inputs, the frozen base root or None while src/ is still the base)."""

    from .order_skeleton_write import SkeletonInputs

    base = None
    if started(tracker):
        base = base_root(root)
        if not (base / "src").is_dir():
            raise _missing_base()
    inputs = SkeletonInputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path, source_root=base)
    return inputs, base


def freeze_base(root: Path) -> Path:
    """Copy src/ into the frozen base (before the first skeleton write)."""

    base = base_root(root)
    if base.exists():
        shutil.rmtree(base)
    shutil.copytree(root / "src", base / "src")
    return base


def render_tree(root: Path, inputs: Any, base: Path | None, target: Path) -> dict[str, Any]:
    """Render the whole tree and write it (a src/ mirror and its write manifest) into ``target`` under build/."""

    from .order_skeleton_write import preview_root, render_skeletons, write_skeletons

    preview_root(root, target.relative_to(root).as_posix())
    rendered = render_skeletons(inputs, segment=None)
    write_skeletons(base if base is not None else root, target, rendered)
    return rendered


def compact_check(report: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "determinism": ("ok", "files_checked"),
        "s1": ("ok", "checked", "local_statics_checked", "failed"),
        "s2": ("ok", "units", "mismatches", "mismatches_explained", "known_conflict_count", "problem_count"),
        "s3": ("ok", "files_compared", "blocks_changed", "edges", "edge_digest_matches_baseline"),
        "s4": ("ok", "bodies_checked", "head_rewrites", "snapshot_bodies_landed", "header_bodies_replaced"),
        "s5": ("ok", "new_findings"),
        "s7": ("ok", "files", "regions", "classes_checked", "members_checked"),
    }
    shown: dict[str, Any] = {"ok": report["ok"], "failed": report["failed"], "write_sha256": report["write_sha256"]}
    for key, fields in keep.items():
        shown[key] = {field: report[key].get(field) for field in fields if field in report[key]}
    return shown


def check_tree(root: Path, tracker: dict[str, Any], target: Path, base: Path | None, *, manifest_path: Path,
               snapshot_path: Path) -> dict[str, Any]:
    from .order_skeleton_check import check_skeletons

    return check_skeletons(root, tracker, target, manifest_path=manifest_path, snapshot_path=snapshot_path, source_root=base)


# -- the scope of one item ---------------------------------------------------------------------


def file_owners(tracker: dict[str, Any]) -> dict[str, str]:
    owners: dict[str, str] = {}
    for item in skeleton_items(tracker):
        for path in item.get("resources") or []:
            owners[str(path)] = item["id"]
    return owners


def item_units(tracker: dict[str, Any], item: dict[str, Any]) -> list[str]:
    return list((item.get("batch") or {}).get("units") or []) if item.get("kind") == ORDER_APPLY_KIND else []


def _scope_summary(rendered: dict[str, Any], scope: set[str], units: set[str], report: dict[str, Any],
                   waiting: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    manifest = rendered["manifest"]
    flags: Counter = Counter()
    entries = 0
    for entry in manifest["entries"]:
        if entry.get("path") not in scope:
            continue
        if entry["kind"] in ("function", "data"):
            entries += 1
        flags.update(flag["kind"] for flag in entry.get("flags") or [])
        for inner in entry.get("nested") or []:
            flags.update(flag["kind"] for flag in inner.get("flags") or [])
    regions = 0
    for region in (manifest.get("headers") or {}).get("regions") or []:
        if region.get("path") not in scope:
            continue
        regions += 1
        flags.update(flag["kind"] for flag in region.get("flags") or [])
        for inner in region.get("nested") or []:
            flags.update(flag["kind"] for flag in inner.get("flags") or [])
    conflicts = [row for row in report["s2"].get("known_conflicts") or [] if row.get("unit") in units]
    own_waiting = [row for row in waiting if row["item"] == item_id]
    return {
        "entries": entries,
        "regions": regions,
        "flags": dict(sorted(flags.items())),
        "known_conflicts": conflicts,
        "waiting": own_waiting,
        "waiting_by_kind": dict(sorted(Counter(row["kind"] for row in own_waiting).items())),
    }


def _record_lines(record: dict[str, Any]) -> list[str]:
    inputs = record["inputs"]
    lines = [
        f"order-skeleton-write-sha256:{record['write_sha256']}",
        f"order-skeleton-manifest-sha256:{inputs['manifest_sha256']}",
        f"order-skeleton-snapshot-sha256:{inputs['snapshot_sha256']}",
        f"order-skeleton-base-sha256:{inputs['base_tree_sha256']}",
        f"order-skeleton-stage4-baseline-sha256:{inputs['stage4_baseline_sha256']}",
        f"order-skeleton-files-sha256:{record['files_sha256']} count:{len(record['files'])}",
        f"order-skeleton-conflicts {len(record['known_conflicts'])}",
        f"order-skeleton-waiting {len(record['waiting'])}"
        + "".join(f" {kind}:{count}" for kind, count in record["waiting_by_kind"].items()),
        "order-skeleton-flags " + " ".join(f"{kind}:{count}" for kind, count in record["flags"].items()),
    ]
    if record.get("decisions"):
        lines.append(f"order-skeleton-decisions {record['decisions']['path']} sha256:{record['decisions']['sha256']} "
                     f"count:{record['decisions']['count']}")
    if record.get("amendments"):
        lines.append(f"order-skeleton-reapply {' '.join(record['amendments'])}")
    if record.get("merges"):
        lines.append("order-skeleton-merges " + " ".join(f"{kind}:{count}" for kind, count in record["merges"].items()))
    for row in record["files"]:
        merge = f" merge:{row['merge']}" if row.get("merge") not in (None, "render", "kept", "same") else ""
        lines.append(f"order-skeleton-file {row['path']} before:{row['before_sha256'] or '-'} after:{row['after_sha256'] or '-'}{merge}")
    return lines


def _comparable(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key not in ("applied_at", "applied_by")}


def record_skeleton(item: dict[str, Any], record: dict[str, Any], applied_at: str) -> None:
    """Store an apply's record and its evidence lines; a different earlier record moves to the review history."""

    previous = item.get("order_skeleton")
    if isinstance(previous, dict) and _comparable(previous) != _comparable(record):
        item.setdefault("review_history", []).append({"replaced_at": applied_at, "order_skeleton": copy.deepcopy(previous)})
    item["order_skeleton"] = {**record, "applied_at": applied_at}
    kept = [text for text in item.get("evidence") or [] if not str(text).startswith(EVIDENCE_PREFIX)]
    item["evidence"] = sorted(set(kept) | set(_record_lines(record)))


# -- the apply -----------------------------------------------------------------------------------


def _lease(item: dict[str, Any], owner: str) -> None:
    lease = item.get("lease")
    if item.get("status") != "in_progress" or not isinstance(lease, dict):
        raise SocomError(f"{item['id']} is not actively leased")
    if lease.get("owner") != owner:
        raise SocomError(f"{item['id']} is leased by {lease.get('owner')}")


def _skeleton_item(tracker: dict[str, Any], item_id: str) -> dict[str, Any]:
    item = _by_id(tracker).get(item_id)
    if item is None or item.get("kind") not in ORDER_SKELETON_KINDS:
        raise SocomError(f"{item_id} is not a stage 5 skeleton item ({ORDER_SKELETON_PREPARE_ID} or an order-segment-NNN-apply)")
    return item


INPUT_KEYS = ("manifest_sha256", "snapshot_sha256", "src_sha256", "order_sha256", "plans", "link_plan",
              "stage4_baseline_sha256", "base_tree_sha256")


def _stale_inputs(tracker: dict[str, Any], inputs: Any, base: Path | None) -> list[str]:
    """Problems with the inputs against the tracker: stage 5's baseline, open amendments, plans on another baseline.

    A plan built on a stage 4 baseline a stage 5 rebase absorbed is current
    (``order skeleton manifest`` checked its segment's target is unchanged).
    """

    from .order_plan import absorbed_baselines

    problems: list[str] = []
    decomposition = next((row.get("decomposition") or {} for row in tracker.get("stages") or [] if row.get("name") == ORDER_STAGE), {})
    current = stage4_baseline(tracker)
    if current is None or current != decomposition.get("stage4_baseline_sha256"):
        problems.append(f"the stage 4 baseline {current} is not stage 5's ({decomposition.get('stage4_baseline_sha256')}): "
                        "progress rebase-function-order absorbs the accepted stage 4 amendments first")
    from .tracker import open_source_amendments

    if opened := [row.get("id") for row in open_source_amendments(tracker)]:
        problems.append(f"stage 4 amendments are open ({', '.join(map(str, opened))}): their plans may change the files")
    absorbed = absorbed_baselines(tracker)
    for row in inputs.plans:
        planned = (row["plan"].get("inputs") or {}).get("stage4_baseline_sha256")
        if planned != current and planned not in absorbed:
            problems.append(f"{row['path']} was planned against another stage 4 baseline")
            break
    return problems


def _changed_inputs(tracker: dict[str, Any], inputs: Any, base: Path | None, recorded: dict[str, Any]) -> list[str]:
    """The record's inputs that differ from the current ones (a carried record: its write must still render the same)."""

    now = _inputs_record(tracker, inputs, base)
    return [key for key in INPUT_KEYS if now.get(key) != recorded.get(key)]


def _inputs_record(tracker: dict[str, Any], inputs: Any, base: Path | None) -> dict[str, Any]:
    record = {key: value for key, value in inputs.record().items() if key != "decisions"}
    record["stage4_baseline_sha256"] = stage4_baseline(tracker)
    record["base_tree_sha256"] = tree_sha256(base) if base is not None else None
    return record


def _own_decisions(inputs: Any, item_id: str) -> dict[str, Any] | None:
    return next((row for row in inputs.decision_files if row["item"] == item_id), None)


def prepare_skeleton_apply(root: Path, tracker: dict[str, Any], item_id: str, owner: str, *, manifest_path: Path,
                           snapshot_path: Path, write: bool,
                           resolutions: Path | None = None) -> tuple[dict[str, Any], dict[str, bytes | None]]:
    """The record of one skeleton apply and its file changes ({path: bytes, or None to delete}); refuses what it may not do.

    With ``write`` the first write of the route freezes the base (src/ as the
    manifest was built on it) and the merge inputs go into the blob store;
    without it, nothing under src/ is touched.  Each file is merged
    (``order_skeleton_merge``): the previous render, the live file and the new
    render.  A conflict writes nothing and leaves a report under build/ unless
    ``resolutions`` holds a resolved copy of every conflicting file.
    """

    item = _skeleton_item(tracker, item_id)
    _lease(item, owner)
    by_id = _by_id(tracker)
    if item["kind"] == ORDER_APPLY_KIND:
        prepare = by_id.get(ORDER_SKELETON_PREPARE_ID)
        if prepare is None:
            raise SocomError(f"{ORDER_SKELETON_PREPARE_ID} does not exist: run progress add-order-skeleton-prepare first")
        if prepare.get("status") != "accepted" or not isinstance(prepare.get("order_skeleton"), dict):
            raise SocomError(f"{ORDER_SKELETON_PREPARE_ID} is {prepare.get('status')}: a segment apply writes after the accepted prepare")
        # The prepare's own write must still be what the current inputs render: the check of other applied items below.
    first = not started(tracker)
    inputs, base = route_inputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path)
    problems = _stale_inputs(tracker, inputs, base)
    if problems:
        raise SocomError("refused, stale inputs:\n- " + "\n- ".join(problems))
    target = root / RENDER_DIR
    rendered = render_tree(root, inputs, base, target)
    if unused := inputs.unused_decisions():
        raise SocomError("decisions that no longer apply (their rows are not waiting): "
                         + _shown([f"{row['kind']} {row['key']} ({row['item']})" for row in unused]))
    report = check_tree(root, tracker, target, base, manifest_path=manifest_path, snapshot_path=snapshot_path)
    if not report["ok"]:
        from .order_skeleton_check import headline

        shown = headline(report)
        raise SocomError(f"the static checks fail over the render ({', '.join(report['failed'])}): "
                         + canonical_json({key: shown[key] for key in report["failed"]})[:2000])
    from .order_reopen import item_amendments

    files = rendered["files"]
    owners = file_owners(tracker)
    amendments = item_amendments(tracker, item_id)
    grown: list[str] = []
    if orphaned := sorted(path for path in files if path not in owners):
        units = {row["path"] for row in rendered["manifest"]["files"] if row["action"] == "unit"}
        if item["kind"] == ORDER_PREPARE_KIND and isinstance(item.get("order_skeleton"), dict) and not (set(orphaned) & units):
            # A re-applied prepare (after a stage 4 amendment, say) reserves the headers and holding files the new render adds.
            grown = grow_prepare(tracker, item, orphaned)
        else:
            raise SocomError(f"the render writes {len(orphaned)} files no skeleton item reserves: {_shown(orphaned)}"
                             + ("" if item["kind"] == ORDER_PREPARE_KIND else
                                f" (reopen {ORDER_SKELETON_PREPARE_ID}: its re-apply for the amendment reserves new headers)"))
    # Another item's applied files must be what the current inputs give (else that item is reopened first).
    source = base if base is not None else root
    drifted = []
    for other in skeleton_items(tracker):
        record = other.get("order_skeleton")
        if other["id"] == item_id or not isinstance(record, dict) or other.get("status") not in ("awaiting_acceptance", "accepted"):
            continue
        for row in record["files"]:
            wanted = files[row["path"]] if row["path"] in files else _read(source / row["path"])
            if _sha(wanted) != record_ancestor(row):
                drifted.append(f"{row['path']} ({other['id']})")
    if drifted:
        raise SocomError(f"the current inputs change files of other applied skeleton items (reopen them): {_shown(drifted)}")
    rows, changes, blobs = _merge_scope(root, tracker, item, rendered, source, resolutions)
    no_blocks = _digest([])
    for row in rows:
        kept = row["stage4_blocks_sha256"] if row["before_sha256"] is not None else no_blocks
        if row["after_sha256"] is not None and kept != row["after_stage4_blocks_sha256"]:
            raise SocomError(f"{row['path']}: the render changes its stage 4 blocks")
    outside = sorted(path for path in changes if path not in set(item.get("resources") or []))
    if outside:
        raise SocomError(f"refused: {len(outside)} changes lie outside the resources of {item_id}: {_shown(outside)}")
    waiting = waiting_rows(rendered, inputs)
    scope = set(item.get("resources") or [])
    summary = _scope_summary(rendered, scope, set(item_units(tracker, item)), report, waiting, item_id)
    own = _own_decisions(inputs, item_id)
    record = {
        "kind": RECORD_KIND,
        "schema_version": RECORD_SCHEMA,
        "item": item_id,
        "route": APPLY_ROUTE,
        "applied_by": owner,
        "inputs": _inputs_record(tracker, inputs, base) if base is not None else {
            **_inputs_record(tracker, inputs, None), "base_tree_sha256": tree_sha256(root)},
        "decisions": own,
        "write_sha256": rendered["manifest"]["write_sha256"],
        "files": rows,
        "files_sha256": _digest(rows),
        "changed": sorted(changes, key=str.casefold),
        "merges": dict(sorted(Counter(row["merge"] for row in rows).items())),
        "check": compact_check(report),
        **summary,
    }
    if amendments:
        record["amendments"] = amendments
    if grown:
        record["reserved_added"] = grown
    if write:
        from .order_skeleton_merge import put_blob

        # The merge inputs and result of every file, so apply-check can re-run the merge and a later re-apply finds its ancestor.
        for data in blobs:
            put_blob(root, data)
    if write and first:
        freeze_base(root)
        if tree_sha256(base_root(root)) != record["inputs"]["base_tree_sha256"]:
            raise SocomError("the frozen base differs from src/ as it was rendered")
    return record, changes


def _prior_rows(tracker: dict[str, Any], item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """{path: the record row of its last skeleton write}: the item's own previous record first, then other items' records."""

    found: dict[str, dict[str, Any]] = {}
    for other in skeleton_items(tracker):
        record = other.get("order_skeleton")
        if other["id"] != item["id"] and isinstance(record, dict):
            found.update({str(row["path"]): row for row in record.get("files") or []})
    own = item.get("order_skeleton")
    if isinstance(own, dict):
        found.update({str(row["path"]): row for row in own.get("files") or []})
    return found


def _merge_scope(root: Path, tracker: dict[str, Any], item: dict[str, Any], rendered: dict[str, Any], source: Path,
                 resolutions: Path | None) -> tuple[list[dict[str, Any]], dict[str, bytes | None], list[bytes | None]]:
    """(record rows, file changes, blobs to store) of an item's files, each merged; a conflict refuses with a report.

    The ancestor of a file is its previous render (the blob store, or the
    current render when that still has the recorded digest), or the base's
    content for a file no skeleton item wrote yet.
    """

    from .order_skeleton_merge import (
        check_merged, conflict_marker_root, get_blob, lf, load_resolutions, merge_file, write_conflict_report,
    )

    item_id = item["id"]
    files = rendered["files"]
    prior = _prior_rows(tracker, item)
    merges = []
    conflicts: dict[str, dict[str, Any]] = {}
    markers: dict[str, bytes] = {}
    for path in sorted(item.get("resources") or [], key=str.casefold):
        base_data = _read(source / path)
        theirs = files[path] if path in files else base_data
        ours = _read(root / path)
        row = prior.get(path)
        if row is None:
            ancestor_sha, ancestor = _sha(base_data), lf(base_data)
        else:
            ancestor_sha = record_ancestor(row)
            ancestor = get_blob(root, ancestor_sha)
            if ancestor is None and ancestor_sha is not None and _sha(theirs) == ancestor_sha:
                ancestor = lf(theirs)  # the current inputs still render the previous write
        try:
            merged = merge_file(ancestor_sha, ancestor, ours, theirs)
        except SocomError as failure:
            raise SocomError(f"{path}: {failure}; the ancestors are stored when the item is reopened for a stage 4 amendment "
                             "(progress reopen-order-skeleton), before its inputs change") from None
        if merged.kind == "conflict":
            conflicts[path] = {"path": path, "ancestor_sha256": ancestor_sha, "ours_sha256": _sha(ours),
                               "theirs_sha256": _sha(theirs), "reason": merged.reason, "hunks": merged.conflicts}
            if merged.marked is not None:
                markers[path] = merged.marked
        merges.append((path, base_data, theirs, ours, ancestor_sha, ancestor, merged))
    resolved = load_resolutions(root, item_id, resolutions, conflicts)
    if unresolved := sorted(path for path in conflicts if path not in resolved):
        report = write_conflict_report(root, item_id, [conflicts[path] for path in sorted(conflicts)], markers)
        hunks = sum(len(conflicts[path]["hunks"]) for path in unresolved)
        raise SocomError(
            f"refused, nothing written: {len(unresolved)} files conflict ({hunks} hunks) between src/ and the new render: "
            f"{_shown(unresolved)}. The hunks (lines, both sides) are in {report} and marker files under "
            f"{conflict_marker_root(item_id)}/; a source worker resolves each into <dir>/<path> under build/ and the apply "
            "is re-run with --resolutions <dir>"
        )
    rows: list[dict[str, Any]] = []
    changes: dict[str, bytes | None] = {}
    blobs: list[bytes | None] = []
    problems: list[str] = []
    for path, base_data, theirs, ours, ancestor_sha, ancestor, merged in merges:
        kind, after = merged.kind, merged.data
        if path in resolved:
            kind, after = "resolved", resolved[path]["data"]
        if kind in ("clean", "resolved"):
            # The port lane edits bodies; the planned order (fences) and stage 4's annotations stay the render's.
            problems.extend(check_merged(path, after, theirs))
        if kind in ("render", "clean", "resolved") and (_sha(ours) != _sha(after) or (ours is None) != (after is None)):
            changes[path] = after
        entry = {
            "path": path,
            "action": _action(rendered, path),
            "base_sha256": _sha(base_data),
            "base_content_sha256": _content(base_data),
            "before_sha256": _sha(ours),
            "before_content_sha256": _content(ours),
            "stage4_blocks_sha256": blocks_sha256(ours),
            "ancestor_sha256": ancestor_sha,
            "rendered_sha256": _sha(theirs),
            "after_sha256": _sha(after),
            "after_stage4_blocks_sha256": blocks_sha256(after),
            "merge": kind,
        }
        if path in resolved:
            entry["resolution"] = {"path": resolved[path]["path"], "sha256": resolved[path]["sha256"]}
        rows.append(entry)
        blobs.extend((ancestor, ours, theirs, after))
    if problems:
        raise SocomError("refused, the merged files break the render's structure:\n- " + "\n- ".join(problems[:_SHOWN]))
    return rows, changes, blobs


def grow_prepare(tracker: dict[str, Any], item: dict[str, Any], paths: list[str]) -> list[str]:
    """Reserve ``paths`` (new headers and holding files of a re-render) for the prepare; the audit's digest follows."""

    from .order_plan import skeleton_resources_digest

    resources = sorted(set(item.get("resources") or []) | set(paths), key=str.casefold)
    item["resources"] = list(resources)
    item.setdefault("batch", {})["files"] = list(resources)
    stage = next((row for row in tracker.get("stages") or [] if row.get("name") == ORDER_STAGE), {})
    record = (stage.get("decomposition") or {}).get("skeleton_prepare")
    if isinstance(record, dict):
        applies = [row for row in tracker.get("work_items") or [] if row.get("kind") == ORDER_APPLY_KIND]
        record["resources_sha256"] = skeleton_resources_digest(item, applies)
        record["prepare_file_count"] = len(resources)
        record.setdefault("reserved_added", []).extend(sorted(paths, key=str.casefold))
    return sorted(paths, key=str.casefold)


def _read(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _content(data: bytes | None) -> str | None:
    from .source_apply import content_sha256

    return None if data is None else content_sha256(_lf(data))


def _action(rendered: dict[str, Any], path: str) -> str:
    if path in {row["path"] for row in rendered["manifest"]["deleted"]}:
        return "orphan-deleted"
    row = next((row for row in rendered["manifest"]["files"] if row["path"] == path), None)
    return row["action"] if row is not None else "unchanged"


def commit_changes(root: Path, changes: dict[str, bytes | None]) -> dict[str, bytes | None]:
    """Write the changes (atomic per file); on failure restore every file and re-raise.  Returns the backups."""

    from .source_apply import Overlay

    overlay = Overlay(root)
    for path, data in changes.items():
        if data is None:
            overlay.delete(path)
        else:
            overlay.write(path, data)
    backups = overlay.commit()
    commit_changes.overlay = overlay  # type: ignore[attr-defined]
    return backups


def rollback_changes(root: Path, backups: dict[str, bytes | None]) -> None:
    from .source_apply import Overlay

    overlay = getattr(commit_changes, "overlay", None) or Overlay(root)
    overlay.rollback(backups)


# -- verification (apply-check), handoff and acceptance ------------------------------------------


def verify_skeleton(root: Path, tracker: dict[str, Any], item_id: str, *, manifest_path: Path, snapshot_path: Path) -> dict[str, Any]:
    """``order skeleton apply-check``: the record against fresh inputs, a fresh render and its checks, and src/."""

    return verify_skeletons(root, tracker, [item_id], manifest_path=manifest_path, snapshot_path=snapshot_path)[0]


def verify_skeletons(root: Path, tracker: dict[str, Any], item_ids: list[str], *, manifest_path: Path,
                     snapshot_path: Path) -> list[dict[str, Any]]:
    """The apply-check of each item, over one fresh render and one run of the static checks.

    The route renders the whole tree from the same inputs for every item, so
    the items share the render (under ``CHECK_DIR``: the item's own directory
    for one item, ``all`` for several) and its check; each record is then
    compared on its own.
    """

    reports: list[dict[str, Any]] = []
    shared: tuple[Any, Path | None, dict[str, Any], dict[str, Any]] | None = None
    for item_id in item_ids:
        item = _skeleton_item(tracker, item_id)
        record = item.get("order_skeleton")
        if not isinstance(record, dict):
            reports.append({"ok": False, "work_item_id": item_id, "status": item.get("status"),
                            "problems": [f"{item_id} has no skeleton record: run {APPLY_ROUTE} first"]})
            continue
        if shared is None:
            inputs, base = route_inputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path)
            target = root / CHECK_DIR / (item_id.replace(":", "-") if len(item_ids) == 1 else "all")
            target.parent.mkdir(parents=True, exist_ok=True)
            rendered = render_tree(root, inputs, base, target)
            report = check_tree(root, tracker, target, base, manifest_path=manifest_path, snapshot_path=snapshot_path)
            shared = (inputs, base, rendered, report)
        reports.append(_verify_record(root, tracker, item, record, *shared))
    return reports


def _verify_record(root: Path, tracker: dict[str, Any], item: dict[str, Any], record: dict[str, Any], inputs: Any,
                   base: Path | None, rendered: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    item_id = item["id"]
    problems: list[str] = []
    notes: list[str] = []
    if record.get("kind") != RECORD_KIND or record.get("schema_version") != RECORD_SCHEMA or record.get("item") != item_id:
        problems.append("the record is not a skeleton apply record of this item")
    problems.extend(_stale_inputs(tracker, inputs, base))
    if changed := _changed_inputs(tracker, inputs, base, record["inputs"]):
        # A record carried across a manifest rebuild or a stage 5 rebase: its write must still be what they render.
        notes.append(f"inputs changed since the apply ({', '.join(changed)}): the fresh render must still reproduce its write")
    own = _own_decisions(inputs, item_id)
    if own != record.get("decisions"):
        problems.append(f"the decisions file of {item_id} changed since the apply: re-apply")
    if sorted(row["path"] for row in record["files"]) != sorted(item.get("resources") or []):
        problems.append(f"the record's files are not {item_id}'s resources")
    if not report["ok"]:
        problems.append(f"the static checks fail over a fresh render: {', '.join(report['failed'])}")
    source = base if base is not None else root
    rendered_files = {row["path"]: rendered["files"][row["path"]] if row["path"] in rendered["files"] else _read(source / row["path"])
                      for row in record["files"]}
    found, drift = verify_written(root, record, rendered_files)
    problems.extend(found)
    return {
        "ok": not problems,
        "mutation_performed": False,
        "work_item_id": item_id,
        "status": item.get("status"),
        "record_sha256": record_sha256(record),
        "write_sha256": record.get("write_sha256"),
        "render_write_sha256": rendered["manifest"]["write_sha256"],
        "file_count": len(record["files"]),
        "changed_count": len(record.get("changed") or []),
        "merges": record.get("merges"),
        "check": compact_check(report),
        "known_conflicts": len(record.get("known_conflicts") or []),
        "waiting": record.get("waiting_by_kind"),
        "drift": drift,
        "drift_count": len(drift),
        "notes": notes,
        "problems": problems,
    }


def verify_written(root: Path, record: dict[str, Any], rendered: dict[str, bytes | None]) -> tuple[list[str], list[str]]:
    """(problems, drift) of a record's own write: the fresh render and the recorded merge reproduce it.

    The check is of what the item wrote, never of what ``src/`` holds now:
    the fresh render of each file must have the recorded render digest, and a
    merged file must come out of the recorded ancestor and live content again
    (both from the blob store) with the recorded digest; a resolved file is
    the stored resolution and keeps the render's fences and blocks.  A file
    that changed after the write (later port-lane edits) is drift, reported
    by path; a change of its stage 4 blocks is a problem, because annotations
    change only through stage 4.
    """

    from .order_skeleton_merge import check_merged, get_blob, merge_file

    problems: list[str] = []
    drift: list[str] = []
    for row in record["files"]:
        path = row["path"]
        render = rendered.get(path)
        if _sha(render) != record_ancestor(row):
            problems.append(f"{path}: a fresh render differs from the recorded write")
            continue
        kind = row.get("merge")
        if kind == "clean":
            ancestor, before = get_blob(root, row.get("ancestor_sha256")), get_blob(root, row.get("before_sha256"))
            if (row.get("ancestor_sha256") and ancestor is None) or (row.get("before_sha256") and before is None):
                problems.append(f"{path}: the recorded merge's inputs are not in the blob store")
            else:
                again = merge_file(row.get("ancestor_sha256"), ancestor, before, render)
                if again.kind != "clean" or _sha(again.data) != row["after_sha256"]:
                    problems.append(f"{path}: the recorded merge does not reproduce its write")
        elif kind == "resolved":
            resolution = get_blob(root, row.get("after_sha256"))
            if resolution is None or (row.get("resolution") or {}).get("sha256") != row.get("after_sha256"):
                problems.append(f"{path}: the recorded resolution is not in the blob store")
            else:
                problems.extend(check_merged(path, resolution, render))
        elif kind in ("kept", "same") and row.get("before_sha256") != row.get("after_sha256"):
            problems.append(f"{path}: a kept file must be written unchanged")
        elif kind in (None, "render") and row.get("after_sha256") != _sha(render):
            problems.append(f"{path}: the recorded write is not the render")
        current = _read(root / path)
        if _sha(current) != row["after_sha256"]:
            drift.append(path)
            if current is not None and row["after_sha256"] is not None and blocks_sha256(current) != row["after_stage4_blocks_sha256"]:
                problems.append(f"{path}: its stage 4 blocks changed after the write")
        elif current is not None and blocks_sha256(current) != row["after_stage4_blocks_sha256"]:
            problems.append(f"{path}: its stage 4 blocks changed")
    return problems, drift


def skeleton_workers(tracker: dict[str, Any]) -> set[str]:
    """Everyone who applied or handed off a skeleton item (review history included)."""

    names: set[str] = set()
    for item in skeleton_items(tracker):
        for entry in [item, *(item.get("review_history") or [])]:
            if not isinstance(entry, dict):
                continue
            for record in (entry.get("order_skeleton"), entry.get("handoff")):
                if isinstance(record, dict):
                    names.update(str(record[key]) for key in ("applied_by", "owner") if record.get(key))
        lease = item.get("lease")
        if isinstance(lease, dict) and lease.get("owner"):
            names.add(str(lease["owner"]))
    return names


def handoff_skeleton(tracker: dict[str, Any], item_id: str, owner: str, summary: str, evidence: list[str],
                     report: dict[str, Any]) -> None:
    from .tracker import _iso, _utc_now

    item = _skeleton_item(tracker, item_id)
    _lease(item, owner)
    if not summary.strip():
        raise SocomError("handoff summary must not be empty")
    record = item.get("order_skeleton")
    if not isinstance(record, dict):
        raise SocomError(f"{item_id} has not been applied: run {APPLY_ROUTE} first")
    if not report["ok"] or report.get("record_sha256") != record_sha256(record):
        raise SocomError(f"order skeleton apply-check fails for {item_id}: " + "; ".join(report.get("problems") or [])[:2000])
    item["status"] = "awaiting_acceptance"
    item["lease"] = None
    item["handoff"] = {"owner": owner, "summary": summary.strip(), "submitted_at": _iso(_utc_now()), "route": HANDOFF_ROUTE}
    item["evidence"] = sorted(set(item.get("evidence") or []) | set(evidence) | {f"{RECORD_CITATION}{record_sha256(record)}"})


def check_handoff(tracker: dict[str, Any], item_id: str, owner: str) -> dict[str, Any]:
    """The cheap preconditions of a handoff (before the apply-check runs)."""

    item = _skeleton_item(tracker, item_id)
    _lease(item, owner)
    if not isinstance(item.get("order_skeleton"), dict):
        raise SocomError(f"{item_id} has not been applied: run {APPLY_ROUTE} first")
    return item


def check_accepter(tracker: dict[str, Any], item_id: str, accepter: str) -> str:
    """The cheap preconditions of an acceptance: the item is under review and the accepter is independent."""

    item = _skeleton_item(tracker, item_id)
    if item.get("status") != "awaiting_acceptance":
        raise SocomError(f"{item_id} is {item.get('status')}, not awaiting_acceptance")
    name = accepter.strip()
    if not name:
        raise SocomError("accepter must not be empty")
    if MAINTAINER_MARKER in name:
        raise SocomError(f"{name} is a tool maintainer: a skeleton item is accepted by an independent socom-verifier")
    if name in skeleton_workers(tracker):
        raise SocomError(f"{name} applied or handed off skeleton work: the accepter must be an independent socom-verifier")
    return name


def accept_skeleton(tracker: dict[str, Any], item_id: str, accepter: str, evidence: list[str], report: dict[str, Any]) -> None:
    from .tracker import _iso, _utc_now

    name = check_accepter(tracker, item_id, accepter)
    item = _skeleton_item(tracker, item_id)
    record = item.get("order_skeleton")
    if not isinstance(record, dict):
        raise SocomError(f"{item_id} has no skeleton record")
    cited = f"{RECORD_CITATION}{record_sha256(record)}"
    if cited not in (item.get("evidence") or []):
        raise SocomError(f"{item_id}'s record changed since its handoff (the handoff cites another record digest)")
    if not report["ok"] or report.get("record_sha256") != record_sha256(record):
        raise SocomError(f"order skeleton apply-check fails for {item_id}: " + "; ".join(report.get("problems") or [])[:2000])
    if not [text for text in evidence if str(text).strip()]:
        raise SocomError("acceptance needs review evidence")
    item["status"] = "accepted"
    item["accepted"] = {"by": name, "at": _iso(_utc_now()), "route": ACCEPT_ROUTE}
    item["evidence"] = sorted(set(item.get("evidence") or []) | set(evidence))


def audit_skeleton_records(tracker: dict[str, Any]) -> list[str]:
    """Skeleton items in review or accepted carry their record; acceptance only through the route."""

    errors: list[str] = []
    for item in skeleton_items(tracker):
        record = item.get("order_skeleton")
        status = item.get("status")
        if record is not None:
            if not isinstance(record, dict) or record.get("kind") != RECORD_KIND or record.get("item") != item["id"]:
                errors.append(f"{item['id']} has an invalid skeleton record")
                continue
            paths = [row.get("path") for row in record.get("files") or []]
            # A reopened item's record may predate a rebase that changed its reservation; its re-apply replaces it.
            if set(paths) - set(item.get("resources") or []) and status in ("awaiting_acceptance", "accepted"):
                errors.append(f"{item['id']}'s skeleton record names files outside its resources")
            if record.get("files_sha256") != _digest([{key: value for key, value in row.items()} for row in record.get("files") or []]):
                errors.append(f"{item['id']}'s skeleton record files digest differs from its files")
        if status in ("awaiting_acceptance", "accepted"):
            if not isinstance(record, dict):
                errors.append(f"{item['id']} is {status} without a skeleton record")
            elif f"{RECORD_CITATION}{record_sha256(record)}" not in (item.get("evidence") or []):
                errors.append(f"{item['id']} is {status} but its evidence does not cite its skeleton record")
            if (item.get("handoff") or {}).get("route") != HANDOFF_ROUTE:
                errors.append(f"{item['id']} must be handed off by {HANDOFF_ROUTE}")
        if status == "accepted" and (item.get("accepted") or {}).get("route") != ACCEPT_ROUTE:
            errors.append(f"{item['id']} must be accepted by {ACCEPT_ROUTE}")
    return errors


# -- decisions -----------------------------------------------------------------------------------


def decide(root: Path, tracker: dict[str, Any], item_id: str, lease_owner: str, artifact: str, option: str, value: str,
           basis: str, *, manifest_path: Path, snapshot_path: Path) -> dict[str, Any]:
    """``order skeleton decide``: settle one waiting row of the leased item in its decisions file."""

    from .order_skeleton_write import DECISIONS_KIND, DECISIONS_SCHEMA, decisions_path, render_skeletons
    from .tracker import _iso, _utc_now

    item = _skeleton_item(tracker, item_id)
    _lease(item, lease_owner)
    if not basis.strip():
        raise SocomError("a decision needs --basis: the evidence or judgment it rests on")
    # One newline style: decision text lands in LF-hashed files (a Windows shell may hand over CRLF).
    text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise SocomError(f"--{option} must not be empty")
    inputs, _base = route_inputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path)
    rendered = render_skeletons(inputs, segment=None)
    # A row this item decided already may be decided again (the new decision replaces it).
    rows = waiting_rows(rendered, inputs) + decided_rows(inputs, item_id)
    matches = [row for row in rows if artifact in (row.get("key"), row.get("name"), *(row.get("aliases") or []))]
    if not matches:
        raise SocomError(f"{artifact} is not a waiting row (order skeleton apply-check or the write manifest lists them)")
    row = matches[0]
    if row["item"] != item_id:
        raise SocomError(f"{artifact} lands in the files of {row['item']}: decide it under that item's lease")
    if row["option"] != option:
        raise SocomError(f"{artifact} is a {row['kind']} row: settle it with --{row['option']}")
    if row["kind"] == "overload-tie" and text not in (row.get("candidates") or []):
        raise SocomError(f"--body must name one of the candidates {row.get('candidates')}")
    if row["kind"] in ("local-static-owner", "local-class-owner"):
        unit = next((unit for _number, unit in inputs.units if unit["unit"] == row.get("unit")), None)
        names = {function["name"] for function in (unit or {}).get("functions") or [] if not function.get("in_class")}
        if text not in names:
            raise SocomError(f"--owner must be the mangled name of an out-of-line function of {row.get('unit')}")
    if row["kind"] == "type-no-record":
        last = str(row.get("name") or "").split("::")[-1]
        if not re.match(rf"^(?:enum|struct|class|union)\s+{re.escape(last)}\b", text):
            raise SocomError(f"--type must be the complete definition of {last} (enum/struct/class/union {last} ...)")
    if row["kind"] == "initializer-unrenderable" and (";" in text or "\n" in text):
        raise SocomError("--initializer is the text after '=' on one line, without a ';'")
    relative = decisions_path(item_id)
    path = root / relative
    current = load_json(path) if path.is_file() else {"kind": DECISIONS_KIND, "schema_version": DECISIONS_SCHEMA,
                                                         "work_item_id": item_id, "decisions": []}
    entry = {"kind": row["kind"], "key": row["key"], "value": text, "basis": basis.strip(), "by": lease_owner,
             "at": _iso(_utc_now())}
    if row.get("name") and row["name"] != row["key"]:
        entry["name"] = row["name"]
    replaced = [old for old in current["decisions"] if (old["kind"], old["key"]) == (entry["kind"], entry["key"])]
    current["decisions"] = sorted([old for old in current["decisions"] if old not in replaced] + [entry],
                                  key=lambda old: (old["kind"], old["key"]))
    atomic_write_json(path, current)
    return {"ok": True, "mutation_performed": True, "work_item_id": item_id, "decisions": relative, "decision": entry,
            "replaced": replaced, "count": len(current["decisions"]),
            "note": f"the decision takes effect at the next {APPLY_ROUTE} of {item_id}"}


def decided_rows(inputs: Any, item_id: str) -> list[dict[str, Any]]:
    """The rows ``item_id`` decided already, named as their waiting rows were, so a re-decision finds them by either name.

    A decided type row is named by its readable type name (``ActionItem::EVENT``,
    as ``waiting_rows`` names it), with the decision's stored name and the
    mangled key's last component as aliases.
    """

    from .order_skeleton_write import DECISION_KINDS

    readable = {row["mangled"]: _readable(tuple(row["chain"])) for row in inputs.manifest["declarations"]["types"]
                if row.get("mangled") and row.get("chain")}
    rows: list[dict[str, Any]] = []
    for (kind, key), row in sorted(inputs.decisions.items()):
        if row["item"] != item_id:
            continue
        stored = row.get("name")
        if kind == "type-no-record":
            name = readable.get(key) or stored or _mangled_last_name(key)
            aliases = sorted({value for value in (stored, _mangled_last_name(key)) if value and value != name})
        else:
            name, aliases = stored or key, []
        rows.append({"kind": kind, "key": key, "item": item_id, "option": DECISION_KINDS[kind], "decided": True,
                     "candidates": _candidates(inputs, kind, key), "unit": _unit_of(inputs, kind, key), "name": name,
                     "aliases": aliases})
    return rows


def _mangled_last_name(mangled: str) -> str:
    """The last component of a mangled type name (``Q210ActionItem5EVENT`` -> ``EVENT``), else the name itself."""

    index, count = 0, 1
    if mangled.startswith("Q") and len(mangled) > 1 and mangled[1].isdigit():
        index, count = 2, int(mangled[1])
    last = mangled
    for _ in range(count):
        digits = re.match(r"\d+", mangled[index:])
        if not digits:
            return mangled
        length = int(digits.group())
        start = index + len(digits.group())
        last, index = mangled[start:start + length], start + length
    return last or mangled


def _candidates(inputs: Any, kind: str, key: str) -> list[str]:
    if kind != "overload-tie":
        return []
    body = inputs.bodies.get(key) or {}
    return list(body.get("candidates") or [])


def _unit_of(inputs: Any, kind: str, key: str) -> str | None:
    if kind in ("local-static-owner", "initializer-unrenderable"):
        return (inputs.data.get(key) or {}).get("unit")
    if kind == "local-class-owner":
        return (inputs.signatures.get(key) or {}).get("unit")
    return None


# -- stage 4 chain of custody ------------------------------------------------------------------------


def skeleton_custody(root: Path, tracker: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Files an ACCEPTED skeleton item wrote that are still its record's "after" with their stage 4 blocks unchanged.

    ``{path: {"item", "before_sha256", "before_content_sha256", "after_sha256", "states"}}``.
    Stage 4's checks take such a file as its stage 4 state when one of its
    ``states`` (``[sha256, content_sha256]`` pairs) is one stage 4 recorded:
    the content the write started from (``before``), and for a file that is
    exactly its render also the frozen base it was rendered from (a re-apply
    that leaves an unamended file as it was keeps the original custody).
    """

    found: dict[str, dict[str, Any]] = {}
    for item in skeleton_items(tracker):
        record = item.get("order_skeleton")
        if item.get("status") != "accepted" or not isinstance(record, dict):
            continue
        for row in record.get("files") or []:
            current = _read(root / str(row.get("path")))
            if _sha(current) != row.get("after_sha256"):
                continue
            if current is not None and blocks_sha256(current) != row.get("after_stage4_blocks_sha256"):
                continue
            states = [[row.get("before_sha256"), row.get("before_content_sha256")]]
            if "base_sha256" in row and row.get("after_sha256") == record_ancestor(row):
                states.append([row.get("base_sha256"), row.get("base_content_sha256")])
            found[str(row["path"])] = {"item": item["id"], **{key: row.get(key) for key in (
                "before_sha256", "before_content_sha256", "after_sha256")}, "states": states}
    return found


def skeleton_deletions(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    """The files ACCEPTED skeleton items removed (orphans whose bodies moved), as stage 4 retired-file rows."""

    rows = []
    for item in skeleton_items(tracker):
        record = item.get("order_skeleton")
        if item.get("status") != "accepted" or not isinstance(record, dict):
            continue
        for row in record.get("files") or []:
            # The base digest: a re-apply finds the orphan deleted already (its before is then absent).
            base = row.get("base_sha256", row.get("before_sha256"))
            if row.get("after_sha256") is None and base is not None:
                rows.append({"path": str(row["path"]), "sha256": base, "bytes": None, "by": item["id"]})
    return sorted(rows, key=lambda row: row["path"])


def skeleton_changes(row: dict[str, Any]) -> bool:
    """Whether the skeleton render of a record row's file differs from its frozen base (the route changes the file).

    A record from before merges has the base as its before; a merge record keeps the base digest itself.
    """

    return row.get("base_sha256", row.get("before_sha256")) != record_ancestor(row)


def skeleton_written(tracker: dict[str, Any]) -> dict[str, str]:
    """{path: item} of the files skeleton items in review or accepted wrote: stage 4 may not rewrite them."""

    found: dict[str, str] = {}
    for item in skeleton_items(tracker):
        record = item.get("order_skeleton")
        if item.get("status") in ("awaiting_acceptance", "accepted") and isinstance(record, dict):
            for row in record.get("files") or []:
                if skeleton_changes(row):
                    found[str(row["path"])] = item["id"]
    return found


def refuse_stage4_writes(tracker: dict[str, Any], paths: list[str], amendments: list[str] | None = None) -> None:
    """Stage 4 refuses to rewrite a file an accepted (or handed-off) skeleton item wrote until that item is reopened.

    A re-apply for open stage 4 ``amendments`` rewrites a skeleton-written
    file only when its skeleton item was reopened for one of them
    (``progress reopen-order-skeleton``, which stores the merge ancestors the
    later skeleton re-apply needs); a file of an item reopened otherwise, or
    for another amendment, is refused too.
    """

    written = skeleton_written(tracker)
    blocked = sorted(path for path in paths if path in written)
    if blocked:
        items = sorted({written[path] for path in blocked})
        route = (f"progress reopen-order-skeleton --amendment {amendments[0]}" if amendments else "progress work reopen")
        raise SocomError(
            f"refused: {len(blocked)} files hold stage 5 skeleton writes of {', '.join(items)} ({_shown(blocked)}); "
            f"reopen those items first ({route}), then re-apply them after this stage 4 change"
        )
    if not amendments:
        return
    from .order_reopen import reopenings

    allowed = {str(item) for row in reopenings(tracker) if row.get("status") == "open" and row.get("amendment") in amendments
               for item in row.get("items") or []}
    others: dict[str, str] = {}
    for item in skeleton_items(tracker):
        record = item.get("order_skeleton")
        if item["id"] in allowed or not isinstance(record, dict):
            continue
        for row in record.get("files") or []:
            if skeleton_changes(row):
                others[str(row["path"])] = item["id"]
    if blocked := sorted(path for path in paths if path in others):
        items = sorted({others[path] for path in blocked})
        raise SocomError(
            f"refused: {len(blocked)} files hold stage 5 skeleton writes of {', '.join(items)} ({_shown(blocked)}), which were "
            f"not reopened for {', '.join(amendments)}: reopen them with progress reopen-order-skeleton --amendment "
            f"{amendments[0]} --item <item> first"
        )
