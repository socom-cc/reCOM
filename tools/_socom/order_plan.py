"""Stage 5 (authored-function-order) phase A2: the order-plan items and their plans.

The producer ``order-target`` (``progress decompose-stage --stage
authored-function-order``) replaces the stage 5 seed, once stage 4 is
accepted with its file baseline and no stage 4 amendment is open, with:

* one file-only ``order-plan-segment`` item per stage 4 segment that holds
  authored units (decision D6), ``socom:work:order-segment-NNN``.  A unit is
  planned once, in its ``primary_segment`` (the segment plan owning most of
  its artifacts); a unit that owns data only (no segment plan) is planned with
  its nearest authored neighbour in link order;
* the file-only link-order plan ``socom:work:order-link`` (``order link-spec``
  output, reviewed);
* phase B: one ``order-apply-segment`` per segment plan,
  ``socom:work:order-segment-NNN-apply``, which writes the units' skeleton
  source under their ``src/`` directories in the planned order (exact
  signatures, provisional bodies moved, stubs) and runs static checks only, no
  compile; each waits for its plan and for the ``capability-gate`` item
  ``socom:work:order-skeleton-route``, which a future skeleton-generator
  capability opens;
* phase C: one ``order-compile-segment`` per segment,
  ``socom:work:order-segment-NNN-compile``, which compiles the skeletons with
  the exact compiler and verifies the object order; each waits for its apply
  and for ``socom:work:order-compile-route``, the capability gate linked to the
  compiler blocker ``socom:blocker:metrowerks-flexlm-license``;
* the stage gate, over every compile item and the link plan: the stage is not
  accepted without the compiler.

No registered capability opens either route yet.  The decomposition
record's ``producer_sha256`` binds the order target, the stage 4 file
baseline and the units of every segment item.

An **order plan** (``socom-order-plan`` schema 1, ``build/order-plans/
<item>.json``) gives, per unit of its segment, the intended source order of
the unit's *definitions* (D3): ``functions`` rows in source ``position`` order
with an ``in_class`` flag (a member defined in its class body is emitted on
demand, right after its first caller, so it is outside the file's out-of-line
order), ``data`` rows per region in declaration order, the definitions
without a source position (``not_placed``), the copies and literals as
stage 7 targets only, and the ``open`` rows that need a planner's judgment.
Every row has a class (``proven``: DWARF lines; ``constrained``: the
local-static counter or the static initializer; ``hypothesis``: only the
calibrated rule) and its basis.

``order plan draft`` decides what the evidence and the rule fix and leaves
open only the judgment calls: a DWARF line against the rule (an in-class
candidate), a counter against the rule, a unit's stray artifacts outside its
main run (seal_ai's local-static copies) and the deferred stage 4 rows inside
its runs.  ``order plan decide`` settles one row as the lease holder.
``order plan validate`` checks the schema, that every definition of the
segment's units is listed exactly once, that the order the plan predicts
under the rule equals the target order (mismatches listed), the row classes
against the evidence and that the digests are current (``--check`` also fails
on open rows).  Handoff and acceptance of a plan item re-run it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any

from .order_draft import _longest_decreasing, evidence_digest, unit_draft
from .order_target import ORDER_STAGE, link_order
from .source_plan import CAPABILITY_GATE_KIND, SEGMENT_PLAN_KIND, SOURCE_SEED_ID, SOURCE_STAGE, control_characters
from .util import SocomError, canonical_json, load_json, sha256_file

ORDER_SEED_ID = "socom:work:authored-function-order-seed"
ORDER_SKELETON_ROUTE_ID = "socom:work:order-skeleton-route"
ORDER_COMPILE_ROUTE_ID = "socom:work:order-compile-route"
ORDER_ROUTE_IDS = (ORDER_SKELETON_ROUTE_ID, ORDER_COMPILE_ROUTE_ID)
ORDER_LINK_ID = "socom:work:order-link"
ORDER_SEGMENT_PREFIX = "socom:work:order-segment-"
ORDER_SEGMENT_KIND = "order-plan-segment"
ORDER_LINK_KIND = "order-plan-link"
ORDER_APPLY_KIND = "order-apply-segment"
ORDER_COMPILE_KIND = "order-compile-segment"
ORDER_PLAN_KINDS = (ORDER_SEGMENT_KIND, ORDER_LINK_KIND)
# Phase B (skeletons) and phase C (compile): no generic handoff or acceptance closes them.
ORDER_ROUTED_KINDS = (ORDER_APPLY_KIND, ORDER_COMPILE_KIND)
ORDER_ITEM_KINDS = (*ORDER_PLAN_KINDS, *ORDER_ROUTED_KINDS)
ORDER_PLAN_RESOURCES = ["build/order-plans"]
ORDER_PLAN_DIR = "build/order-plans"
ORDER_PRODUCER = "order-target"
COMPILER_BLOCKER = "socom:blocker:metrowerks-flexlm-license"
DEFAULT_GRAPH = "build/source-graph/graph.json"

ORDER_PLAN_KIND = "socom-order-plan"
ORDER_PLAN_SCHEMA = 1
ORDER_PLAN_RULES_VERSION = 1
ROW_CLASSES = ("proven", "constrained", "hypothesis")
OPEN_KINDS = ("out-of-rule", "constraint-conflict", "interleaved", "deferred-in-span")
RULE = (
    "Out-of-line function definitions are emitted in reverse source order.",
    "A member defined in its class body (in_class) is emitted on demand, right after its first caller.",
    "Data definitions are laid out in declaration order within each region.",
)
PLAN_FIELDS = frozenset(
    {"kind", "schema_version", "rules_version", "work_item_id", "segment_number", "inputs", "rule", "units", "notes"}
)
INPUT_FIELDS = ("order_sha256", "stage4_baseline_sha256", "graph_sha256", "evidence_sha256", "segment_target_sha256")
UNIT_FIELDS = frozenset(
    {"unit", "workspace_path", "dwarf_lines", "functions", "data", "not_placed", "stage7_targets", "open", "settled", "notes"}
)
FUNCTION_FIELDS = frozenset({"artifact", "name", "address", "position", "in_class", "class", "basis", "evidence", "decision"})
DATA_FIELDS = frozenset({"artifact", "name", "address", "position", "class", "basis", "evidence", "decision"})
FUNCTION_EVIDENCE = ("line", "static_counter", "literal_label")
DATA_EVIDENCE = ("static_counter", "sinit", "variable")
SKELETON_REQUIRES = (
    "a registered route that writes each unit's skeleton source under its src/ directory in the accepted order "
    "plan's order (exact signatures, provisional bodies moved into place, marked stubs) and runs the static checks "
    "(signatures mangle to the ELF names, the written order predicts the target, annotations unchanged); no compile"
)
COMPILE_REQUIRES = (
    "a registered route that compiles each unit's accepted skeleton with the exact compiler from a clean checkout "
    "and verifies the object's definition order against the order target (needs the compiler's FLEXlm license)"
)
_SHOWN = 12


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def order_plan_path(item_id: str) -> str:
    """The packet path of an order plan item's plan file."""

    return f"{ORDER_PLAN_DIR}/{item_id.replace(':', '-')}.json"


def segment_item_id(number: int) -> str:
    return f"{ORDER_SEGMENT_PREFIX}{int(number):03d}"


def _stage(tracker: dict[str, Any], name: str) -> dict[str, Any]:
    return next((row for row in tracker.get("stages") or [] if row.get("name") == name), {}) or {}


def stage4_baseline(tracker: dict[str, Any]) -> str | None:
    """The current stage 4 file baseline digest (``source-file-baseline``), or ``None``."""

    baseline = _stage(tracker, SOURCE_STAGE).get("baseline")
    return baseline.get("baseline_sha256") if isinstance(baseline, dict) else None


def _open_amendments(tracker: dict[str, Any]) -> list[str]:
    rows = _stage(tracker, SOURCE_STAGE).get("amendments") or []
    return sorted(str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("status") == "open")


# -- the units of each segment item ---------------------------------------------------------


def segment_units(target: dict[str, Any]) -> tuple[dict[int, list[str]], list[dict[str, Any]]]:
    """(segment number -> its units in link order, the units placed by a link neighbour).

    A unit is planned in its ``primary_segment``.  A unit without one (it
    owns data only, through data reconciles) goes to the segment of the
    nearest authored unit before it in link order that has one, else after it.
    """

    units = sorted(target["units"], key=lambda row: row["link_position"])
    placed: dict[int, list[str]] = {}
    neighbours: list[dict[str, Any]] = []
    for index, unit in enumerate(units):
        number = unit.get("primary_segment")
        neighbour = None
        if number is None:
            before = [row for row in reversed(units[:index]) if row.get("primary_segment") is not None]
            after = [row for row in units[index + 1 :] if row.get("primary_segment") is not None]
            found = (before or after or [None])[0]
            if found is None:
                raise SocomError(f"{unit['unit']} has no segment and no authored neighbour with one")
            number, neighbour = found["primary_segment"], found["unit"]
            neighbours.append({"unit": unit["unit"], "segment": number, "neighbour": neighbour})
        placed.setdefault(int(number), []).append(unit["unit"])
    return dict(sorted(placed.items())), neighbours


def segment_target_digest(target: dict[str, Any], units: list[str]) -> str:
    """The digest of the part of the order target a segment's plan orders."""

    names = set(units)
    rows = [
        {
            "unit": unit["unit"],
            "sections": [
                {
                    "region": section["region"],
                    "artifacts": [[entry["artifact"], entry["class"]] for entry in section["artifacts"]],
                    "deferred": [row["artifact"] for row in section.get("deferred") or []],
                    "strays": [row["artifact"] for row in section.get("strays") or []],
                }
                for section in unit["sections"]
            ],
        }
        for unit in target["units"]
        if unit["unit"] in names
    ]
    return _digest(rows)


def _unit_directories(target: dict[str, Any], units: list[str]) -> list[str]:
    paths = {row["unit"]: row.get("workspace_path") for row in target["units"]}
    directories = set()
    for name in units:
        path = paths.get(name)
        if not isinstance(path, str) or not path.startswith("src/"):
            raise SocomError(f"{name} has no workspace path under src/: its skeleton has no directory to reserve")
        directories.add(str(PurePosixPath(path).parent))
    return sorted(directories, key=str.casefold)


def producer_digest(decomposition: dict[str, Any], segments: dict[str, list[str]]) -> str:
    """``producer_sha256``: the order target, the stage 4 baseline and the units of every segment item."""

    return _digest(
        {
            "producer": ORDER_PRODUCER,
            "order_sha256": decomposition.get("order_sha256"),
            "stage4_baseline_sha256": decomposition.get("stage4_baseline_sha256"),
            "segments": [[number, segments[number]] for number in sorted(segments, key=int)],
        }
    )


# -- the producer ---------------------------------------------------------------------------


def _item(item_id: str, kind: str, title: str, dependencies: list[str], resources: list[str], batch: Any) -> dict[str, Any]:
    return {
        "id": item_id,
        "stage": ORDER_STAGE,
        "kind": kind,
        "title": title,
        "status": "blocked",
        "dependencies": dependencies,
        "resources": resources,
        "selection": "units" if kind in ORDER_ITEM_KINDS and kind != ORDER_LINK_KIND else None,
        "batch": batch,
        "lease": None,
        "handoff": None,
        "evidence": [],
    }


def decompose_function_order(tracker: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    """Replace the stage 5 seed with order-plan items, the link plan, phase B and C items, their routes and a gate.

    ``target`` is the order target over the tracker's accepted stage 4 plans
    (``order_target.build_order_target``); it must match the stage 4 file
    baseline.  Mutates ``tracker`` and returns the decomposition record.
    """

    stage4 = _stage(tracker, SOURCE_STAGE)
    baseline = stage4_baseline(tracker)
    gate = next((row for row in tracker["work_items"] if row["id"] == SOURCE_SEED_ID), None)
    if stage4.get("status") != "accepted" or baseline is None or (gate or {}).get("status") != "accepted":
        raise SocomError(f"decomposition needs {SOURCE_STAGE} accepted with its file baseline")
    if opened := _open_amendments(tracker):
        raise SocomError(f"decomposition waits for the open {SOURCE_STAGE} amendments: {opened} (their plans are not accepted)")
    stage = _stage(tracker, ORDER_STAGE)
    if stage.get("decomposition"):
        raise SocomError(f"{ORDER_STAGE} is already decomposed")
    items = tracker["work_items"]
    position = next((index for index, row in enumerate(items) if row["id"] == ORDER_SEED_ID), None)
    if position is None or items[position].get("kind") != "stage-seed":
        raise SocomError(f"{ORDER_SEED_ID} is not an undecomposed stage seed")
    if any(row["stage"] == ORDER_STAGE and row["id"] != ORDER_SEED_ID for row in items):
        raise SocomError(f"{ORDER_STAGE} already has work items")
    inputs = target.get("inputs") or {}
    if inputs.get("stage4_baseline_sha256") != baseline or inputs.get("changed_since_baseline"):
        raise SocomError(
            f"the order target is not the stage 4 baseline {baseline}: it cites {inputs.get('stage4_baseline_sha256')} "
            f"and plans changed since it ({inputs.get('changed_since_baseline') or []})"
        )
    if target["summary"].get("problems"):
        raise SocomError(f"the order target has {target['summary']['problems']} ownership problems: {target['problems']}")
    known = {
        int(((row.get("batch") or {}).get("scope") or {}).get("segment_number"))
        for row in items
        if row.get("kind") == SEGMENT_PLAN_KIND and ((row.get("batch") or {}).get("scope") or {}).get("segment_number") is not None
    }
    by_segment, neighbours = segment_units(target)
    if unknown := sorted(set(by_segment) - known):
        raise SocomError(f"units name segments without a stage 4 segment plan item: {unknown}")
    if not by_segment:
        raise SocomError("decomposition needs at least one authored unit")
    spec = link_order(target)
    digests = {"order_sha256": target["order_sha256"], "stage4_baseline_sha256": baseline}
    moved = {row["unit"] for row in neighbours}
    created: list[dict[str, Any]] = []
    compile_ids: list[str] = []
    for number, units in by_segment.items():
        item_id = segment_item_id(number)
        unit_rows = [row for row in target["units"] if row["unit"] in set(units)]
        batch = {
            "segment_number": number,
            "batch_number": number,
            "stage4_item": f"socom:work:source-segment-{number:03d}",
            "units": list(units),
            "units_by_neighbour": [name for name in units if name in moved],
            "definitions": sum(row["counts"]["definition"] for row in unit_rows),
            **digests,
            "segment_target_sha256": segment_target_digest(target, units),
        }
        directories = _unit_directories(target, units)
        created.append(
            _item(
                item_id, ORDER_SEGMENT_KIND,
                f"Plan the definition order of segment {number:03d} ({len(units)} units, {batch['definitions']} definitions)",
                [SOURCE_SEED_ID], list(ORDER_PLAN_RESOURCES), batch,
            )
        )
        created.append(
            _item(
                f"{item_id}-apply", ORDER_APPLY_KIND,
                f"Write the order skeletons of segment {number:03d} under src/ and check them statically (no compile)",
                [item_id, ORDER_SKELETON_ROUTE_ID], list(directories),
                {**batch, "directories": list(directories), "phase": "B", "requires": SKELETON_REQUIRES},
            )
        )
        compile_ids.append(f"{item_id}-compile")
        created.append(
            _item(
                f"{item_id}-compile", ORDER_COMPILE_KIND,
                f"Compile the order skeletons of segment {number:03d} with the exact compiler and verify the object order",
                [f"{item_id}-apply", ORDER_COMPILE_ROUTE_ID], list(directories),
                {**batch, "directories": list(directories), "phase": "C", "requires": COMPILE_REQUIRES},
            )
        )
    created.append(
        _item(
            ORDER_LINK_ID, ORDER_LINK_KIND,
            f"Review the link-order plan ({len(spec['objects'])} objects in link order)",
            [SOURCE_SEED_ID], list(ORDER_PLAN_RESOURCES),
            {"batch_number": 0, **digests, "link_order_sha256": spec["link_order_sha256"], "objects": len(spec["objects"])},
        )
    )
    skeleton = _item(
        ORDER_SKELETON_ROUTE_ID, CAPABILITY_GATE_KIND,
        "Register the stage 5 skeleton route (skeleton source under src/, static checks, no compile)", [], [], None,
    )
    skeleton["batch"] = {"capability": ORDER_STAGE, "phase": "B", "requires": SKELETON_REQUIRES}
    route = _item(
        ORDER_COMPILE_ROUTE_ID, CAPABILITY_GATE_KIND,
        "Register the stage 5 compile route (exact-compiler builds and object-order checks)", [], [], None,
    )
    route["batch"] = {"capability": ORDER_STAGE, "phase": "C", "requires": COMPILE_REQUIRES, "blocker": COMPILER_BLOCKER}
    created.extend((skeleton, route))
    seed = items[position]
    seed["kind"] = "stage-gate"
    seed["title"] = f"Review and close {ORDER_STAGE}"
    # The stage is accepted only after phase C: every segment compiled and verified with the exact compiler.
    seed["dependencies"] = [*compile_ids, ORDER_LINK_ID]
    items[position:position] = created
    blocker = next((row for row in tracker.get("blockers") or [] if row.get("id") == COMPILER_BLOCKER), None)
    if blocker is None:
        raise SocomError(f"the compiler blocker {COMPILER_BLOCKER} is missing from the tracker")
    if ORDER_STAGE not in (blocker.get("blocks") or []):
        blocker["blocks"] = [*(blocker.get("blocks") or []), ORDER_STAGE]
    decomposition: dict[str, Any] = {
        "producer": ORDER_PRODUCER,
        **digests,
        "graph_sha256": inputs.get("graph_sha256"),
        "link_order_sha256": spec["link_order_sha256"],
        "segment_count": len(by_segment),
        "segments": sorted(by_segment),
        "unit_count": sum(len(units) for units in by_segment.values()),
        "units_by_neighbour": neighbours,
        "segments_without_units": sorted(known - set(by_segment)),
        "skeleton_route": ORDER_SKELETON_ROUTE_ID,
        "compile_route": ORDER_COMPILE_ROUTE_ID,
        "compiler_blocker": COMPILER_BLOCKER,
        "tracker_revision": tracker["revision"] + 1,
    }
    decomposition["producer_sha256"] = producer_digest(decomposition, {str(key): value for key, value in by_segment.items()})
    stage["decomposition"] = decomposition
    return decomposition


def audit_function_order(tracker: dict[str, Any]) -> list[str]:
    """Structure of the stage 5 items: seed or gate, plan/apply/compile triples, the link plan, both routes and the record."""

    errors: list[str] = []
    items = [row for row in tracker.get("work_items") or [] if row.get("stage") == ORDER_STAGE]
    by_id = {row.get("id"): row for row in tracker.get("work_items") or []}
    for row in tracker.get("work_items") or []:
        if row.get("kind") in ORDER_ITEM_KINDS and row.get("stage") != ORDER_STAGE:
            errors.append(f"{row.get('id')} is a {row.get('kind')} item outside {ORDER_STAGE}")
    for row in items:
        resources = set(row.get("resources") or [])
        if "ghidra-writer" in resources or any(str(value).startswith("ghidra:") for value in resources):
            errors.append(f"{row.get('id')} owns a Ghidra resource in the file-only {ORDER_STAGE} stage")
    seed = by_id.get(ORDER_SEED_ID)
    stage = _stage(tracker, ORDER_STAGE)
    decomposition = stage.get("decomposition")
    if seed is None:
        return errors + [f"{ORDER_SEED_ID} is missing"]
    if seed.get("kind") == "stage-seed":
        if len(items) != 1 or decomposition:
            errors.append(f"{ORDER_STAGE} has order items or a decomposition but an undecomposed seed")
        return errors
    if seed.get("kind") != "stage-gate" or not isinstance(decomposition, dict):
        return errors + [f"{ORDER_SEED_ID} must be a stage seed, or the stage gate of a recorded decomposition"]
    if decomposition.get("producer") != ORDER_PRODUCER:
        errors.append(f"{ORDER_STAGE} decomposition names producer {decomposition.get('producer')!r}")
    plans = [row for row in items if row.get("kind") == ORDER_SEGMENT_KIND]
    applies = [row for row in items if row.get("kind") == ORDER_APPLY_KIND]
    compiles = [row for row in items if row.get("kind") == ORDER_COMPILE_KIND]
    links = [row for row in items if row.get("kind") == ORDER_LINK_KIND]
    routes = [row for row in items if row.get("kind") == CAPABILITY_GATE_KIND]
    others = [row["id"] for row in items if row.get("kind") not in (*ORDER_ITEM_KINDS, CAPABILITY_GATE_KIND) and row["id"] != ORDER_SEED_ID]
    if others:
        errors.append(f"{ORDER_STAGE} has unexpected items {others[:_SHOWN]}")
    if sorted(row["id"] for row in routes) != sorted(ORDER_ROUTE_IDS):
        errors.append(f"{ORDER_STAGE} needs exactly the capability gates {list(ORDER_ROUTE_IDS)}")
    if [row["id"] for row in links] != [ORDER_LINK_ID]:
        errors.append(f"{ORDER_STAGE} needs exactly one {ORDER_LINK_ID} item")
    digests = {key: decomposition.get(key) for key in ("order_sha256", "stage4_baseline_sha256")}
    if not all(isinstance(value, str) and len(value) == 64 for value in digests.values()):
        errors.append(f"{ORDER_STAGE} decomposition must record the order target and stage 4 baseline digests")
    segments: dict[str, list[str]] = {}
    for row in plans:
        batch = row.get("batch") or {}
        number = batch.get("segment_number")
        if not isinstance(number, int) or row["id"] != segment_item_id(number):
            errors.append(f"{row['id']} is not the order plan ID of its segment {number!r}")
            continue
        units = batch.get("units")
        if not isinstance(units, list) or not units or not all(isinstance(name, str) for name in units):
            errors.append(f"{row['id']} must list its units")
            continue
        segments[str(number)] = list(units)
        if row.get("dependencies") != [SOURCE_SEED_ID]:
            errors.append(f"{row['id']} must depend only on the accepted {SOURCE_STAGE} gate")
        if row.get("resources") != ORDER_PLAN_RESOURCES:
            errors.append(f"{row['id']} order plan resources are not file-only")
        if any(batch.get(key) != value for key, value in digests.items()) or len(str(batch.get("segment_target_sha256"))) != 64:
            errors.append(f"{row['id']} must cite the decomposition's digests and its segment target digest")
    for suffix, rows, route_id in (("-apply", applies, ORDER_SKELETON_ROUTE_ID), ("-compile", compiles, ORDER_COMPILE_ROUTE_ID)):
        for row in rows:
            plan_id = str(row["id"]).removesuffix(suffix)
            plan = by_id.get(plan_id)
            batch = row.get("batch") or {}
            if not str(row["id"]).endswith(suffix) or plan is None or plan.get("kind") != ORDER_SEGMENT_KIND:
                errors.append(f"{row['id']} has no matching order plan item")
                continue
            # Phase B waits for its plan, phase C for its phase B apply; each behind its own route.
            before = plan_id if suffix == "-apply" else f"{plan_id}-apply"
            if row.get("dependencies") != [before, route_id]:
                errors.append(f"{row['id']} must depend on {before} and {route_id}")
            resources = list(row.get("resources") or [])
            if not resources or resources != batch.get("directories") or not all(str(value).startswith("src/") for value in resources):
                errors.append(f"{row['id']} must reserve its units' src/ directories")
            if batch.get("units") != (plan.get("batch") or {}).get("units"):
                errors.append(f"{row['id']} plans other units than {plan_id}")
        if {f"{row['id']}{suffix}" for row in plans} != {row["id"] for row in rows}:
            errors.append(f"order plan/{suffix.removeprefix('-')} item pairing is incomplete")
    for row in links:
        if row.get("dependencies") != [SOURCE_SEED_ID] or row.get("resources") != ORDER_PLAN_RESOURCES:
            errors.append(f"{ORDER_LINK_ID} must depend only on the accepted {SOURCE_STAGE} gate and own build/order-plans")
        if any((row.get("batch") or {}).get(key) != value for key, value in digests.items()):
            errors.append(f"{ORDER_LINK_ID} must cite the decomposition's digests")
    gated = {ORDER_SKELETON_ROUTE_ID: ("order applies", applies), ORDER_COMPILE_ROUTE_ID: ("order compile items", compiles)}
    for row in routes:
        batch = row.get("batch") or {}
        if batch.get("capability") != ORDER_STAGE:
            errors.append(f"{row['id']} must name the {ORDER_STAGE} capability")
        if row["id"] == ORDER_COMPILE_ROUTE_ID and not any(
            blocker.get("id") == batch.get("blocker") for blocker in tracker.get("blockers") or []
        ):
            errors.append(f"{ORDER_COMPILE_ROUTE_ID} must name an existing compiler blocker")
        what, waiting = gated.get(row["id"], ("", []))
        if row.get("status") != "accepted" and any(entry.get("status") != "blocked" for entry in waiting):
            errors.append(f"{what} must stay blocked until {row['id']} is accepted")
    if set(seed.get("dependencies") or []) != {row["id"] for row in compiles} | {ORDER_LINK_ID}:
        errors.append(f"{ORDER_STAGE} gate does not depend on every order compile item and {ORDER_LINK_ID}")
    if seed.get("resources"):
        errors.append(f"{ORDER_SEED_ID} stage gate must not own resources")
    if decomposition.get("segment_count") != len(plans) or decomposition.get("segments") != sorted(int(key) for key in segments):
        errors.append(f"{ORDER_STAGE} decomposition record differs from its order plan items")
    elif decomposition.get("producer_sha256") != producer_digest(decomposition, segments):
        errors.append(f"{ORDER_STAGE} producer_sha256 differs from the record and its items")
    return errors


# -- plans: drafting ------------------------------------------------------------------------


def _int(value: str) -> int:
    return int(value, 16)


def _evidence(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row[field] for field in fields if field in row}


def _pairwise(rows: list[dict[str, Any]], field: str, key: str = "position") -> dict[str, bool]:
    """Per artifact carrying ``field``: whether every other carrier is ordered by ``key`` as ``field`` orders them."""

    carriers = [row for row in rows if field in (row.get("evidence") or {}) and row.get(key) is not None]
    result: dict[str, bool] = {}
    for row in carriers:
        value, at = row["evidence"][field], row[key]
        result[row["artifact"]] = all(
            other is row or other["evidence"][field] == value or (other["evidence"][field] < value) == (other[key] < at)
            for other in carriers
        ) and len(carriers) > 1
    return result


def first_users(rows: list[dict[str, Any]], users: dict[str, set[str]]) -> dict[str, str]:
    """Per function row, the earliest-emitted (lowest address) other function row of the unit that references it."""

    address = {row["artifact"]: _int(row["address"]) for row in rows}
    found = {}
    for row in rows:
        sites = [site for site in users.get(row["artifact"], ()) if site in address and site != row["artifact"]]
        if sites:
            found[row["artifact"]] = min(sites, key=lambda site: (address[site], site))
    return found


def _common_regions(target: dict[str, Any]) -> set[int]:
    return {row["region"] for row in target["regions"] if row["common"]}


def plan_unit(unit: dict[str, Any], target: dict[str, Any], derived: dict[str, Any]) -> dict[str, Any]:
    """One unit of an order plan, drafted from its evidence draft (``order_draft.unit_draft``)."""

    draft = unit_draft(unit, target, derived)
    dwarf = draft["dwarf_lines"]
    names = {row["artifact"]: row["name"] for row in draft["functions"]["order"]}
    opened: dict[str, dict[str, Any]] = {}

    def flag(artifact: str, kind: str, reason: str) -> None:
        entry = opened.setdefault(artifact, {"artifact": artifact, "kind": kind, "reason": reason})
        if reason not in entry["reason"]:
            entry["reason"] += f"; {reason}"

    functions = []
    for position, row in enumerate(draft["functions"]["order"], 1):
        functions.append(
            {
                "artifact": row["artifact"], "name": row["name"], "address": row["address"], "position": position,
                "in_class": False, "class": "hypothesis", "basis": "", "evidence": _evidence(row, FUNCTION_EVIDENCE),
            }
        )
    users = first_users(functions, derived["users"])
    for row in functions:
        if users.get(row["artifact"]):
            row["evidence"]["first_user"] = users[row["artifact"]]
    if dwarf:
        address = {row["artifact"]: _int(row["address"]) for row in functions}
        lined = sorted(functions, key=lambda row: address[row["artifact"]])
        keep = _longest_decreasing([row["evidence"]["line"] for row in lined])
        for index, row in enumerate(lined):
            row["class"], row["basis"] = "proven", f"dwarf-line {row['evidence']['line']}"
            if index in keep:
                continue
            row["in_class"] = True
            user = users.get(row["artifact"])
            if user is None:
                caller = "no caller among the unit's definitions"
            elif address[user] < address[row["artifact"]]:
                caller = f"its first caller {names[user]} is emitted before it"
            else:
                caller = f"its first caller {names[user]} is emitted after it"
            flag(row["artifact"], "out-of-rule",
                 f"DWARF line {row['evidence']['line']} places it against the reverse-order rule: drafted in_class "
                 f"(a member defined in its class body, emitted on demand); {caller}")
    else:
        consistent = _pairwise(functions, "static_counter")
        for row in functions:
            if consistent.get(row["artifact"]):
                row["class"], row["basis"] = "constrained", f"local-static-counter {row['evidence']['static_counter']}"
            else:
                row["basis"] = "reverse-address rule"
    for chain in draft["functions"]["constraints"]:
        if not chain["agrees"]:
            reason = (
                f"the local-static counter ({chain['values'][0]} < {chain['values'][1]}) orders {names[chain['before']]} "
                f"before {names[chain['after']]} in source; the drafted order does not"
            )
            flag(chain["before"], "constraint-conflict", reason)
            flag(chain["after"], "constraint-conflict", reason)

    data = []
    for region in draft["data"]:
        rows = [
            {
                "artifact": row["artifact"], "name": row["name"], "address": row["address"], "position": position,
                "class": "hypothesis", "basis": "declaration-order rule (address order)",
                "evidence": _evidence(row, DATA_EVIDENCE),
            }
            for position, row in enumerate(region["order"], 1)
        ]
        region_names = {row["artifact"]: row["name"] for row in rows}
        for field, basis in (("static_counter", "local-static-counter"), ("sinit", "static-initializer rank")):
            for artifact, agrees in _pairwise(rows, field).items():
                row = next(entry for entry in rows if entry["artifact"] == artifact)
                if agrees and row["class"] == "hypothesis":
                    row["class"], row["basis"] = "constrained", f"{basis} {row['evidence'][field]}"
        for chain in region["constraints"]:
            if not chain["agrees"]:
                reason = (
                    f"the {chain['basis']} ({chain['values'][0]} < {chain['values'][1]}) orders "
                    f"{region_names[chain['before']]} before {region_names[chain['after']]}; the address order does not"
                )
                flag(chain["before"], "constraint-conflict", reason)
                flag(chain["after"], "constraint-conflict", reason)
        data.append({"region": region["region"], "label": region["label"], "rows": rows})

    common = _common_regions(target)
    copies, literals = [], []
    for section in unit["sections"]:
        for entry in section["artifacts"]:
            if entry["class"] == "copy":
                copies.append(entry["artifact"])
            elif entry["class"] == "literal":
                literals.append(entry["artifact"])
        if section["region"] not in common:
            for stray in section.get("strays") or []:
                between = (section.get("between") or {}).get("objects", 0)
                flag(stray["artifact"], "interleaved",
                     f"a stray {stray['class']} ({stray['name']}) outside the unit's main run in {section['label']} "
                     f"({between} objects between its runs)")
        for row in section.get("deferred") or []:
            flag(row["artifact"], "deferred-in-span",
                 f"an unresolved stage 4 row ({row.get('category') or 'undeferred'}, {row.get('name')}) inside the "
                 f"unit's run in {section['label']}")
    return {
        "unit": unit["unit"],
        "workspace_path": unit["workspace_path"],
        "dwarf_lines": dwarf,
        "functions": functions,
        "data": data,
        "not_placed": [
            {key: row[key] for key in ("artifact", "name", "kind", "reason")} for row in draft["not_placed"]
        ],
        "stage7_targets": {"copies": copies, "literals": literals},
        "open": sorted(opened.values(), key=lambda row: (OPEN_KINDS.index(row["kind"]), row["artifact"])),
        "settled": [],
        "notes": [],
    }


def current_segment(target: dict[str, Any], number: int) -> list[str]:
    by_segment, _neighbours = segment_units(target)
    return list(by_segment.get(int(number), []))


def order_inputs(tracker: dict[str, Any], target: dict[str, Any], derived: dict[str, Any] | None, units: list[str]) -> dict[str, Any]:
    return {
        "order_sha256": target["order_sha256"],
        "stage4_baseline_sha256": stage4_baseline(tracker),
        "graph_sha256": target["inputs"].get("graph_sha256"),
        "evidence_sha256": evidence_digest(derived) if derived is not None else None,
        "segment_target_sha256": segment_target_digest(target, units),
    }


def plan_item(tracker: dict[str, Any], item_id: Any, kinds: tuple[str, ...] = ORDER_PLAN_KINDS) -> dict[str, Any]:
    item = next((row for row in tracker.get("work_items") or [] if row.get("id") == item_id), None)
    if item is None or item.get("kind") not in kinds:
        raise SocomError(f"{item_id} is not a {ORDER_STAGE} plan item ({', '.join(kinds)})")
    return item


def draft_order_plan(
    tracker: dict[str, Any], item: dict[str, Any], target: dict[str, Any], derived: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """(the drafted plan of a segment item, the carry-over report).

    The units are the segment's current ones.  ``previous``, an earlier plan
    of the same item, keeps its planner decisions (rows with a ``decision``,
    settled open rows, notes) wherever their artifacts remain.
    """

    number = (item.get("batch") or {}).get("segment_number")
    units = current_segment(target, number)
    if not units:
        raise SocomError(f"{item['id']}: segment {number} has no authored unit in the current order target")
    by_name = {row["unit"]: row for row in target["units"]}
    plan = {
        "kind": ORDER_PLAN_KIND,
        "schema_version": ORDER_PLAN_SCHEMA,
        "rules_version": ORDER_PLAN_RULES_VERSION,
        "work_item_id": item["id"],
        "segment_number": number,
        "inputs": order_inputs(tracker, target, derived, units),
        "rule": list(RULE),
        "units": [plan_unit(by_name[name], target, derived) for name in units],
        "notes": [],
    }
    report = {"carried": 0, "dropped": []}
    if previous is not None and previous.get("work_item_id") == item["id"]:
        report = carry_decisions(previous, plan)
    return plan, report


def _rows(unit: dict[str, Any]) -> list[tuple[str, dict[str, Any] | None, dict[str, Any]]]:
    """(scope, data region or None, row) for every function and data row of a unit."""

    found: list[tuple[str, dict[str, Any] | None, dict[str, Any]]] = [("functions", None, row) for row in unit.get("functions") or []]
    for region in unit.get("data") or []:
        found.extend(("data", region, row) for row in region.get("rows") or [])
    return found


def carry_decisions(previous: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Re-apply a previous plan's decisions to a fresh draft (final states, ascending position)."""

    carried, dropped = 0, []
    fresh = {unit["unit"]: unit for unit in plan["units"]}
    for old in previous.get("units") or []:
        unit = fresh.get(old.get("unit"))
        decided = [(scope, row) for scope, _region, row in _rows(old) if isinstance(row.get("decision"), dict)] if unit else []
        if unit is None:
            dropped.extend(row.get("artifact") for _scope, _region, row in _rows(old) if isinstance(row.get("decision"), dict))
            continue
        present = {row["artifact"]: (scope, row) for scope, _region, row in _rows(unit)}
        for scope, row in sorted(decided, key=lambda pair: (pair[1].get("position") is None, pair[1].get("position") or 0)):
            if row.get("artifact") not in present or present[row["artifact"]][0] != scope:
                dropped.append(row.get("artifact"))
                continue
            decision = row["decision"]
            # A carried decision settles nothing new: open rows the fresh draft raises stay open.
            try:
                apply_decision(
                    unit, row["artifact"], owner=str(decision.get("by")), basis=str(row.get("basis") or ""),
                    position=row.get("position"), in_class=row.get("in_class") if scope == "functions" else None,
                    klass=row.get("class"), at=decision.get("at"), settle=False,
                )
            except SocomError:
                dropped.append(row.get("artifact"))  # no longer applicable (a position or class the fresh rows refuse)
                continue
            carried += 1
        openings = {(entry["artifact"], entry["kind"]) for entry in unit["open"]}
        for entry in old.get("settled") or []:
            if (entry.get("artifact"), entry.get("kind")) in openings:
                unit["open"] = [row for row in unit["open"] if (row["artifact"], row["kind"]) != (entry["artifact"], entry["kind"])]
                unit["settled"].append(dict(entry))
                carried += 1
        unit["notes"] = list(old.get("notes") or [])
    plan["notes"] = list(previous.get("notes") or [])
    return {"carried": carried, "dropped": sorted(str(value) for value in dropped)}


# -- plans: decisions -----------------------------------------------------------------------

UNSET = object()


def _move(rows: list[dict[str, Any]], row: dict[str, Any], position: int | None) -> None:
    """Renumber ``rows`` (1..k over the rows with a position) with ``row`` at ``position`` (``None``: unplaced)."""

    ordered = sorted((entry for entry in rows if entry is not row and entry.get("position") is not None), key=lambda entry: entry["position"])
    if position is not None:
        if not 1 <= position <= len(ordered) + 1:
            raise SocomError(f"position {position} is outside 1..{len(ordered) + 1}")
        ordered.insert(position - 1, row)
    else:
        row["position"] = None
    for index, entry in enumerate(ordered, 1):
        entry["position"] = index
    # Rows stay listed in source order; unplaced in-class members last, by address.
    rows.sort(key=lambda entry: (entry.get("position") is None, entry.get("position") or 0, _int(entry["address"])))


def _settle(unit: dict[str, Any], artifact: str, basis: str, owner: str, at: str | None) -> list[dict[str, Any]]:
    """Move every open row of ``artifact`` to ``settled`` with the decision's basis."""

    openings = [row for row in unit.get("open") or [] if row.get("artifact") == artifact]
    unit["open"] = [row for row in unit.get("open") or [] if row.get("artifact") != artifact]
    for row in openings:
        unit.setdefault("settled", []).append(
            {"artifact": artifact, "kind": row["kind"], "reason": row["reason"], "basis": basis.strip(), "by": owner, "at": at or _now()}
        )
    return [{"artifact": artifact, "settled": row["kind"]} for row in openings]


def apply_decision(
    unit: dict[str, Any], artifact: str, *, owner: str, basis: str, position: Any = UNSET, in_class: bool | None = None,
    klass: str | None = None, at: str | None = None, settle: bool = True,
) -> list[dict[str, Any]]:
    """Settle one row of a unit (or the open rows of an artifact without a row); returns the changes.

    A decision on a row records ``decision`` (by, at) and its basis, and
    settles every open row of the artifact (``settle``).
    """

    if not basis.strip():
        raise SocomError("a decision needs --basis: the evidence or judgment behind it")
    found = next(((scope, region, row) for scope, region, row in _rows(unit) if row.get("artifact") == artifact), None)
    if found is None:
        openings = [row for row in unit.get("open") or [] if row.get("artifact") == artifact]
        if not openings:
            raise SocomError(f"{artifact} is neither a row nor an open row of {unit['unit']}")
        if position is not UNSET or in_class is not None or klass is not None:
            raise SocomError(f"{artifact} has no row in {unit['unit']} (it is {openings[0]['kind']}): settle it with --basis only")
        return _settle(unit, artifact, basis, owner, at)
    changes: list[dict[str, Any]] = []
    scope, region, row = found
    rows = unit["functions"] if scope == "functions" else region["rows"]
    # Every check first: a refused decision leaves the plan unchanged.
    if scope == "data" and in_class is not None:
        raise SocomError(f"{artifact} is a data definition: in_class applies to functions only")
    if klass is not None and klass not in ROW_CLASSES:
        raise SocomError(f"--class must be one of {', '.join(ROW_CLASSES)}")
    if klass == "proven" and "line" not in (row.get("evidence") or {}):
        raise SocomError(f"{artifact} has no DWARF line: it cannot be proven")
    member = row.get("in_class") if in_class is None else in_class
    wanted = row.get("position") if position is UNSET else position
    if wanted is None and (scope == "data" or not member):
        raise SocomError(f"{artifact} is {'a data' if scope == 'data' else 'an out-of-line'} definition: it needs a source position")
    if isinstance(wanted, int) and wanted != row.get("position"):
        count = sum(1 for entry in rows if entry is not row and entry.get("position") is not None)
        if not 1 <= wanted <= count + 1:
            raise SocomError(f"position {wanted} is outside 1..{count + 1}")
    if klass is not None and klass != row.get("class"):
        changes.append({"artifact": artifact, "class": [row.get("class"), klass]})
        row["class"] = klass
    if scope == "functions" and member != row.get("in_class"):
        changes.append({"artifact": artifact, "in_class": member})
        row["in_class"] = member
    if wanted != row.get("position"):
        changes.append({"artifact": artifact, "position": [row.get("position"), wanted]})
        _move(rows, row, wanted)
    row["basis"] = basis.strip()
    row["decision"] = {"by": owner, "at": at or _now()}
    if settle:
        changes.extend(_settle(unit, artifact, basis, owner, at))
    changes.append({"artifact": artifact, "decided": scope})
    return changes


def decide_order_row(plan: dict[str, Any], artifact: str, **options: Any) -> tuple[str, list[dict[str, Any]]]:
    """Settle one row in a plan (``apply_decision``); returns (unit, changes)."""

    for unit in plan.get("units") or []:
        if any(row.get("artifact") == artifact for _scope, _region, row in _rows(unit)) or any(
            row.get("artifact") == artifact for row in unit.get("open") or []
        ):
            return unit["unit"], apply_decision(unit, artifact, **options)
    raise SocomError(f"{artifact} is not in the plan")


# -- plans: validation ----------------------------------------------------------------------


def _shown(values: list[Any]) -> str:
    text = ", ".join(str(value) for value in values[:_SHOWN])
    return text + (f" (+{len(values) - _SHOWN} more)" if len(values) > _SHOWN else "")


def _schema(plan: Any) -> list[str]:
    if not isinstance(plan, dict):
        return ["the plan is not a JSON object"]
    problems = []
    if plan.get("kind") != ORDER_PLAN_KIND or plan.get("schema_version") != ORDER_PLAN_SCHEMA:
        problems.append(f"the plan is not a {ORDER_PLAN_KIND} schema {ORDER_PLAN_SCHEMA} file")
    if unknown := sorted(set(plan) - PLAN_FIELDS):
        problems.append(f"unknown plan fields {unknown}")
    if plan.get("rules_version") != ORDER_PLAN_RULES_VERSION:
        problems.append(f"the plan was drafted under rules {plan.get('rules_version')}, the current rules are {ORDER_PLAN_RULES_VERSION}")
    if not isinstance(plan.get("inputs"), dict) or set(plan["inputs"]) != set(INPUT_FIELDS):
        problems.append(f"inputs must be exactly {list(INPUT_FIELDS)}")
    if not isinstance(plan.get("units"), list) or not all(isinstance(unit, dict) for unit in plan["units"]):
        problems.append("units must be a list of objects")
        return problems
    if not isinstance(plan.get("notes"), list):
        problems.append("notes must be a list")
    problems.extend(f"control character in {path}" for path in control_characters(plan))
    for unit in plan["units"]:
        name = unit.get("unit")
        if unknown := sorted(set(unit) - UNIT_FIELDS):
            problems.append(f"{name}: unknown unit fields {unknown}")
        if not all(isinstance(unit.get(key), list) for key in ("functions", "data", "not_placed", "open", "settled", "notes")):
            problems.append(f"{name}: functions, data, not_placed, open, settled and notes must be lists")
            continue
        targets = unit.get("stage7_targets")
        if not isinstance(targets, dict) or set(targets) != {"copies", "literals"}:
            problems.append(f"{name}: stage7_targets must list copies and literals")
        for scope, region, row in _rows(unit):
            fields = FUNCTION_FIELDS if scope == "functions" else DATA_FIELDS
            where = f"{name} {row.get('artifact')}"
            if unknown := sorted(set(row) - fields):
                problems.append(f"{where}: unknown row fields {unknown}")
            if row.get("class") not in ROW_CLASSES:
                problems.append(f"{where}: class must be one of {', '.join(ROW_CLASSES)}")
            if not isinstance(row.get("basis"), str) or not row["basis"].strip():
                problems.append(f"{where}: every row needs a basis")
            if scope == "functions" and not isinstance(row.get("in_class"), bool):
                problems.append(f"{where}: in_class must be true or false")
            position = row.get("position")
            if position is not None and (not isinstance(position, int) or isinstance(position, bool)):
                problems.append(f"{where}: position must be an integer or null")
        for row in unit["open"]:
            if not isinstance(row, dict) or row.get("kind") not in OPEN_KINDS or not row.get("artifact") or not row.get("reason"):
                problems.append(f"{name}: an open row needs an artifact, a kind ({', '.join(OPEN_KINDS)}) and a reason")
        for row in unit["settled"]:
            if not isinstance(row, dict) or row.get("kind") not in OPEN_KINDS or not str(row.get("basis") or "").strip():
                problems.append(f"{name}: a settled row needs its kind and basis")
    return problems


def _positions(rows: list[dict[str, Any]], where: str, *, nullable: bool) -> list[str]:
    values = [row.get("position") for row in rows if row.get("position") is not None]
    problems = []
    if sorted(values) != list(range(1, len(values) + 1)):
        problems.append(f"{where}: positions must number the rows 1..{len(values)} once each")
    missing = [row.get("name") for row in rows if row.get("position") is None and not (nullable and row.get("in_class"))]
    if missing:
        problems.append(f"{where}: rows without a position must be in_class: {_shown(missing)}")
    return problems


def _class_problems(rows: list[dict[str, Any]], where: str, fields: tuple[str, ...]) -> list[str]:
    problems = []
    for row in rows:
        evidence = row.get("evidence") or {}
        if row.get("class") == "proven" and "line" not in evidence:
            problems.append(f"{where} {row.get('name')}: proven without a DWARF line")
    lined = [row for row in rows if row.get("class") == "proven" and "line" in (row.get("evidence") or {})]
    names = {row["artifact"]: row.get("name") for row in lined}
    for artifact, agrees in _pairwise(lined, "line").items():
        if not agrees and len(lined) > 1:
            problems.append(f"{where} {names[artifact]}: its position contradicts the DWARF lines")
    consistent = {field: _pairwise(rows, field) for field in fields}
    for row in rows:
        if row.get("class") != "constrained":
            continue
        carried = [field for field in fields if field in (row.get("evidence") or {}) and row["artifact"] in consistent[field]]
        if not any(consistent[field][row["artifact"]] for field in carried):
            problems.append(
                f"{where} {row.get('name')}: constrained, but no counter or initializer order it carries agrees with every "
                "other row's position"
            )
    return problems


def predict(unit: dict[str, Any], addresses: dict[str, int]) -> dict[str, Any]:
    """The rule's prediction against the target order: mismatches and the in-class rows it cannot place."""

    mismatches, unverified = [], []
    rows = unit.get("functions") or []
    names = {row["artifact"]: row.get("name") for row in rows}
    out = sorted((row for row in rows if not row.get("in_class") and row.get("position") is not None), key=lambda row: addresses[row["artifact"]])
    for a, b in zip(out, out[1:]):
        if not a["position"] > b["position"]:
            mismatches.append(
                {"scope": "functions", "kind": "reverse-order", "before": a["name"], "after": b["name"],
                 "positions": [a["position"], b["position"]],
                 "message": f"the target emits {a['name']} before {b['name']}, so it must come later in source "
                            f"(positions {a['position']} and {b['position']})"}
            )
    for row in rows:
        if not row.get("in_class"):
            continue
        user = (row.get("evidence") or {}).get("first_user")
        if user is None or user not in addresses:
            unverified.append(row["name"])
            continue
        here, there = addresses[row["artifact"]], addresses[user]
        between = [entry["name"] for entry in out if there < addresses[entry["artifact"]] < here]
        if here < there:
            mismatches.append({"scope": "functions", "kind": "on-demand", "row": row["name"], "first_user": names.get(user),
                               "message": f"in-class {row['name']} is emitted before its first caller {names.get(user)}"})
        elif between:
            mismatches.append({"scope": "functions", "kind": "on-demand", "row": row["name"], "first_user": names.get(user),
                               "message": f"in-class {row['name']} is not emitted right after its first caller "
                                          f"{names.get(user)}: {_shown(between)} lie between"})
    for region in unit.get("data") or []:
        ordered = sorted(region.get("rows") or [], key=lambda row: addresses[row["artifact"]])
        for a, b in zip(ordered, ordered[1:]):
            if not (a.get("position") or 0) < (b.get("position") or 0):
                mismatches.append(
                    {"scope": "data", "kind": "declaration-order", "region": region.get("label"), "before": a["name"],
                     "after": b["name"], "positions": [a.get("position"), b.get("position")],
                     "message": f"{region.get('label')}: {a['name']} lies before {b['name']}, so it must be declared first"}
                )
    return {"mismatches": mismatches, "unverified_in_class": unverified}


def validate_order_plan(
    tracker: dict[str, Any], plan: Any, target: dict[str, Any], derived: dict[str, Any], *, check: bool = False
) -> dict[str, Any]:
    """Check a segment order plan against its item, the current order target and the evidence (see the module docstring)."""

    problems = _schema(plan)
    notes: list[str] = []
    report: dict[str, Any] = {"kind": "socom-order-plan-validation", "ok": False, "problems": problems, "notes": notes}
    if not isinstance(plan, dict) or not isinstance(plan.get("units"), list):
        return report
    item_id = plan.get("work_item_id")
    report["work_item_id"] = item_id
    try:
        item = plan_item(tracker, item_id, (ORDER_SEGMENT_KIND,))
    except SocomError as failure:
        problems.append(str(failure))
        return report
    batch = item.get("batch") or {}
    number = batch.get("segment_number")
    if plan.get("segment_number") != number:
        problems.append(f"the plan names segment {plan.get('segment_number')}, {item_id} plans segment {number}")
    units = current_segment(target, number)
    expected_inputs = order_inputs(tracker, target, derived, units)
    stale = [key for key in INPUT_FIELDS if (plan.get("inputs") or {}).get(key) != expected_inputs[key]]
    if "stage4_baseline_sha256" in stale:
        problems.append(
            f"stale stage 4 baseline: the plan cites {(plan.get('inputs') or {}).get('stage4_baseline_sha256')}, the current "
            f"baseline is {expected_inputs['stage4_baseline_sha256']}: re-draft (order plan draft --item {item_id})"
        )
    other = [key for key in stale if key != "stage4_baseline_sha256"]
    if other:
        unchanged = "segment_target_sha256" not in stale
        problems.append(
            f"stale {', '.join(other)}: re-draft (order plan draft --item {item_id}; it keeps the decisions)"
            + ("; this segment's target is unchanged" if unchanged else "")
        )
    if units != batch.get("units"):
        problems.append(f"segment {number}'s units changed since decomposition: {batch.get('units')} -> {units}")
    listed = [unit.get("unit") for unit in plan["units"]]
    if listed != units:
        problems.append(f"the plan lists units {listed}; segment {number} plans {units} (in link order)")
    by_name = {row["unit"]: row for row in target["units"]}
    summary = {"units": len(listed), "functions": 0, "data": 0, "not_placed": 0, "in_class": 0, "open": 0, "settled": 0,
               "decided": 0, "classes": {klass: 0 for klass in ROW_CLASSES}, "copies": 0, "literals": 0}
    mismatches: list[dict[str, Any]] = []
    unverified: list[str] = []
    for unit in plan["units"]:
        name = unit.get("unit")
        if name not in by_name or not all(isinstance(unit.get(key), list) for key in ("functions", "data", "not_placed", "open", "settled")):
            continue
        fresh = plan_unit(by_name[name], target, derived)
        where = name
        definitions = [
            entry["artifact"] for section in by_name[name]["sections"] for entry in section["artifacts"] if entry["class"] == "definition"
        ]
        listed_rows = [row.get("artifact") for _scope, _region, row in _rows(unit)] + [row.get("artifact") for row in unit["not_placed"]]
        counts: dict[str, int] = {}
        for artifact in listed_rows:
            counts[artifact] = counts.get(artifact, 0) + 1
        if twice := sorted(str(artifact) for artifact, count in counts.items() if count > 1):
            problems.append(f"{where}: definitions listed more than once: {_shown(twice)}")
        if missing := sorted(set(definitions) - set(counts)):
            problems.append(f"{where}: definitions not listed: {_shown(missing)}")
        if extra := sorted(str(artifact) for artifact in set(counts) - set(definitions)):
            problems.append(f"{where}: rows that are not its definitions: {_shown(extra)}")
        expected_not_placed = {row["artifact"]: row["reason"] for row in fresh["not_placed"]}
        if {row.get("artifact"): row.get("reason") for row in unit["not_placed"]} != expected_not_placed:
            problems.append(f"{where}: not_placed differs from the definitions without a source position (generated, "
                            "compiler-generated, static guards, unlined members, COMMON)")
        expected_functions = {row["artifact"]: row for row in fresh["functions"]}
        if {row.get("artifact") for row in unit["functions"]} != set(expected_functions):
            problems.append(f"{where}: the function rows differ from the unit's placed function definitions")
        expected_regions = {region["region"]: {row["artifact"]: row for row in region["rows"]} for region in fresh["data"]}
        actual_regions = {region.get("region"): {row.get("artifact") for row in region.get("rows") or []} for region in unit["data"]}
        if {key: set(value) for key, value in expected_regions.items()} != actual_regions:
            problems.append(f"{where}: the data rows differ from the unit's placed data definitions per region")
        for row in unit["functions"]:
            fresh_row = expected_functions.get(row.get("artifact"))
            if fresh_row and (row.get("name"), row.get("address")) != (fresh_row["name"], fresh_row["address"]):
                problems.append(f"{where} {row.get('artifact')}: name or address differs from the target")
            if fresh_row and (row.get("evidence") or {}) != fresh_row["evidence"]:
                problems.append(f"{where} {row.get('name')}: its evidence differs from the current evidence (re-draft)")
        for region in unit["data"]:
            for row in region.get("rows") or []:
                fresh_row = expected_regions.get(region.get("region"), {}).get(row.get("artifact"))
                if fresh_row and (row.get("evidence") or {}) != fresh_row["evidence"]:
                    problems.append(f"{where} {row.get('name')}: its evidence differs from the current evidence (re-draft)")
        stage7 = unit.get("stage7_targets") or {}
        if sorted(stage7.get("copies") or []) != sorted(fresh["stage7_targets"]["copies"]) or sorted(
            stage7.get("literals") or []
        ) != sorted(fresh["stage7_targets"]["literals"]):
            problems.append(f"{where}: stage7_targets must list exactly the unit's copies and literals (verified in stage 7)")
        problems.extend(_positions(unit["functions"], f"{where} functions", nullable=True))
        for region in unit["data"]:
            problems.extend(_positions(region.get("rows") or [], f"{where} {region.get('label')}", nullable=False))
        problems.extend(_class_problems(unit["functions"], f"{where}", ("static_counter",)))
        for region in unit["data"]:
            problems.extend(_class_problems(region.get("rows") or [], f"{where} {region.get('label')}", ("static_counter", "sinit")))
        # Every judgment the drafter leaves open stays open until a decision settles it.
        decided = {row.get("artifact") for _scope, _region, row in _rows(unit) if isinstance(row.get("decision"), dict)}
        settled = {(row.get("artifact"), row.get("kind")) for row in unit["settled"]}
        still = {(row.get("artifact"), row.get("kind")) for row in unit["open"]}
        dropped = [row["artifact"] for row in fresh["open"] if (row["artifact"], row["kind"]) not in still | settled]
        if dropped:
            problems.append(f"{where}: open rows removed without a decision: {_shown(dropped)}")
        addresses = {
            entry["artifact"]: _int(entry["address"]) for section in by_name[name]["sections"] for entry in section["artifacts"]
        }
        if all(row.get("artifact") in addresses for _scope, _region, row in _rows(unit)):
            found = predict(unit, addresses)
            mismatches.extend({"unit": name, **row} for row in found["mismatches"])
            unverified.extend(f"{name}:{row}" for row in found["unverified_in_class"])
        summary["functions"] += len(unit["functions"])
        summary["data"] += sum(len(region.get("rows") or []) for region in unit["data"])
        summary["not_placed"] += len(unit["not_placed"])
        summary["in_class"] += sum(1 for row in unit["functions"] if row.get("in_class"))
        summary["open"] += len(unit["open"])
        summary["settled"] += len(unit["settled"])
        summary["decided"] += len(decided)
        summary["copies"] += len(stage7.get("copies") or [])
        summary["literals"] += len(stage7.get("literals") or [])
        for _scope, _region, row in _rows(unit):
            if row.get("class") in ROW_CLASSES:
                summary["classes"][row["class"]] += 1
    if mismatches:
        problems.append(
            f"{len(mismatches)} rows of the order the plan predicts under the rule differ from the target: "
            + "; ".join(row["message"] for row in mismatches[:_SHOWN])
        )
    if unverified:
        notes.append(f"in-class rows without a caller among their unit's definitions (on-demand position unverified until "
                     f"phase C compiles it): {_shown(unverified)}")
    if check and summary["open"]:
        opened = [f"{unit.get('unit')}:{row.get('artifact')} ({row.get('kind')})" for unit in plan["units"] for row in unit.get("open") or []]
        problems.append(f"{summary['open']} open rows remain: {_shown(opened)}")
    report.update(ok=not problems, segment_number=number, units=units, summary=summary, mismatches=mismatches,
                  unverified_in_class=unverified, inputs=expected_inputs, stale=stale)
    return report


def validate_link_plan(tracker: dict[str, Any], plan: Any, target: dict[str, Any]) -> dict[str, Any]:
    """The link-order plan must be exactly the current ``order link-spec`` output, with a clean static check."""

    problems: list[str] = []
    expected = link_order(target)
    if expected.get("stage4_baseline_sha256") != stage4_baseline(tracker):
        problems.append("the order target was not built over the current stage 4 baseline")
    if not isinstance(plan, dict) or plan.get("kind") != expected["kind"]:
        problems.append(f"the link plan is not a {expected['kind']} file")
    else:
        if plan.get("stage4_baseline_sha256") != expected["stage4_baseline_sha256"]:
            problems.append(
                f"stale stage 4 baseline: the link plan cites {plan.get('stage4_baseline_sha256')}, the current baseline is "
                f"{expected['stage4_baseline_sha256']}: re-draft (order plan draft --item {ORDER_LINK_ID})"
            )
        differing = sorted(key for key in set(plan) | set(expected) if key != "stage4_baseline_sha256" and plan.get(key) != expected.get(key))
        if differing:
            problems.append(f"the link plan differs from the current link-order specification in {differing}: re-draft")
        if not expected["check"]["ok"]:
            problems.append(f"the link order violates {expected['check']['violations']} region orders")
    return {
        "kind": "socom-order-plan-validation", "ok": not problems, "work_item_id": ORDER_LINK_ID, "problems": problems, "notes": [],
        "summary": {"objects": len(expected["objects"]), "link_order_sha256": expected["link_order_sha256"],
                    "violations": expected["check"]["violations"]},
    }


# -- the shared inputs, and the handoff and acceptance re-check -----------------------------


def order_context(root: Path, tracker: dict[str, Any], graph_path: Path | None = None, *, evidence: bool = True) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """(the order target, the derived evidence or ``None``) over the stage 4 graph file."""

    from .order_draft import derive_evidence, load_evidence
    from .order_target import build_order_target, load_inputs
    from .source_cache import ensure_source_cache

    path = graph_path or root / DEFAULT_GRAPH
    if not path.is_file():
        raise SocomError(f"{path.relative_to(root).as_posix() if path.is_relative_to(root) else path} does not exist: write it with "
                         f"`source graph --output {DEFAULT_GRAPH}`")
    graph = load_json(path)
    inputs = load_inputs(root, tracker, graph)
    target = build_order_target(
        graph, inputs["plans"], deferrals=inputs["deferrals"], boundaries=inputs["boundaries"], notes=inputs["notes"]
    )
    if not evidence:
        return target, None
    cache, _rebuilt = ensure_source_cache(root, graph_path=path)
    return target, derive_evidence(target, load_evidence(root, cache, graph))


def validate_plan_file(root: Path, tracker: dict[str, Any], plan: Any, *, check: bool, graph_path: Path | None = None) -> dict[str, Any]:
    if isinstance(plan, dict) and plan.get("kind") == "socom-link-order":
        target, _none = order_context(root, tracker, graph_path, evidence=False)
        return validate_link_plan(tracker, plan, target)
    target, derived = order_context(root, tracker, graph_path)
    return validate_order_plan(tracker, plan, target, derived or {}, check=check)


def require_valid_plan(root: Path, tracker: dict[str, Any], item_id: str, cited: list[str]) -> str:
    """The SHA-256 of an order plan item's plan, once it passes ``order plan validate --check`` and is cited.

    ``progress work handoff`` and ``progress work accept`` call this for
    ``order-plan-segment`` and ``order-plan-link`` items: the plan lives at
    its packet path, the evidence names its current SHA-256, and it validates
    with no open row.
    """

    relative = order_plan_path(item_id)
    path = root / relative
    if not path.is_file():
        raise SocomError(f"{relative} does not exist: write the plan of {item_id} first (order plan draft --item {item_id})")
    sha = sha256_file(path)
    if not any(sha in str(line) for line in cited):
        raise SocomError(f"the evidence must cite the plan's SHA-256: --evidence \"{relative} sha256:{sha}\"")
    plan = load_json(path)
    if plan.get("kind") != "socom-link-order" and plan.get("work_item_id") != item_id:
        raise SocomError(f"{relative} is not the order plan of {item_id}")
    if item_id == ORDER_LINK_ID and plan.get("kind") != "socom-link-order":
        raise SocomError(f"{relative} is not a link-order plan")
    report = validate_plan_file(root, tracker, plan, check=True)
    if not report["ok"]:
        raise SocomError(f"{relative} fails order plan validate --check: " + "; ".join(report["problems"][:_SHOWN]))
    return sha
