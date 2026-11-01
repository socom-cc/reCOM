"""Stage 5 (authored-function-order) phase A: order targets and the link-order specification.

``order target`` computes, from the accepted stage 4 owner plans, the source
graph and the reference ELF, the physical order each object must reproduce.
For every authored unit (the owner rows of accepted segment plans and data
reconciles, merged by translation unit) it lists the artifacts the unit owns
in each output-section region in address order, each with its order class:

* ``definition``: a function or data object the unit defines (GLOBAL or
  LOCAL, not a copy); ``generated`` marks the compiler-emitted ones
  (``__vt__``, ``__RTTI__``, ``__sinit_``, ``.p__sinit_``);
* ``copy``: a kept inline (binding 13, this-adjusting ``@N@`` thunks
  included) or WEAK copy, a header-emitted (template or inline) instance,
  or any other template instance (a function template, or a member of a
  class template, by its mangled name), since it is emitted where it is used;
* ``literal``: a data object labelled ``@N`` (the literal pool: strings,
  floats, tables);
* ``compiler-generated``: fill and padding inside one of the unit's runs.

Stage 5 orders definitions (decision D3); the other classes are recorded as
targets and verified in stage 7, when real bodies emit them.

An object's contribution to a region is made of runs: consecutive artifacts
it owns (fill and unresolved rows do not break a run).  Its main run (the
largest) places it; artifacts in other runs are strays.  The global object
order puts the authored units and the provider objects (GNU objects and MW
units of provider plans, opaque) in ``.text`` order, then inserts every
object without code right after the latest object that precedes it in any
region it shares.  Each region's object sequence is compared with the
``.text`` order, and ``order link-spec`` checks the merged order against
every region.  Findings name units interleaved with other objects in a
region (with their strays) and the deferred (unresolved) stage 4 rows inside
a unit's run, with their gate deferral.  Nothing here decides or changes
ownership.

The target carries a deterministic digest (``order_sha256``: canonical JSON
of everything else, like the source graph's) and is cached in SQLite for
``order sql``; both are disposable build products under ``build/``.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from bisect import bisect_left
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any

from .constants import REFERENCE_SHA256
from .mwdemangle import demangle
from .source_draft import SECTION_BOUNDARY_SYMBOLS
from .source_plan import (
    SOURCE_PLAN_KINDS,
    SOURCE_SEED_ID,
    SOURCE_STAGE,
    artifact_ids,
    input_section_text,
    verify_graph,
)
from .util import SocomError, _replace, canonical_json, sha256_file

ORDER_STAGE = "authored-function-order"
ORDER_TARGET_KIND = "socom-order-target"
ORDER_VIEW_KIND = "socom-order-target-view"
ORDER_TARGET_SCHEMA = 1
ORDER_RULES_VERSION = 1
LINK_ORDER_KIND = "socom-link-order"
LINK_ORDER_SCHEMA = 1
ORDER_CLASSES = ("definition", "copy", "literal", "compiler-generated")
# D3: stage 5 verifies definition order; copies, literals and fill need real bodies (stage 7).
VERIFIED_IN = {
    "definition": ORDER_STAGE,
    "copy": "authored-byte-match",
    "literal": "authored-byte-match",
    "compiler-generated": "authored-byte-match",
}
# Linker-defined symbols that open or close an output section, and the static-initializer table.
BOUNDARY_SYMBOLS = frozenset(SECTION_BOUNDARY_SYMBOLS | {"__static_init", "__static_init_end"})
# A literal-pool label; a function named @N@... is a this-adjusting thunk (binding 13: a copy).
LITERAL_NAME = re.compile(r"^@\d+$")
GENERATED_NAME = re.compile(r"^(?:__vt__|__RTTI__|__sinit_|\.p__sinit_)")
COPY_BINDINGS = frozenset({"WEAK", "13"})
COMMON_REASON = "COMMON allocations are placed by the linker after every input section, not in object order"
CACHE_RELATIVE = Path("build") / "cache" / "order-target.sqlite"
CACHE_VERSION = "1"
_SHOWN = 12


def _hex(value: int) -> str:
    return f"0x{value:x}"


def _int(value: str) -> int:
    return int(value, 16)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def order_digest(target: dict[str, Any]) -> str:
    """The digest a target stores: canonical JSON of everything but ``order_sha256``."""

    return _digest({key: value for key, value in target.items() if key != "order_sha256"})


# -- inputs -------------------------------------------------------------------------------


def boundary_symbols(root: Path) -> list[dict[str, Any]]:
    """The reference ELF's GLOBAL linker section symbols (``__data_end``, ``_fbss``, ...), by address."""

    from .elf import Elf32File

    found = {
        (symbol.value, symbol.name)
        for symbol in Elf32File(root / "support" / "socom.elf").symbols()
        if symbol.name in BOUNDARY_SYMBOLS and symbol.binding_name == "GLOBAL"
    }
    return [{"address": _hex(value), "name": name} for value, name in sorted(found)]


def gate_deferrals(tracker: dict[str, Any]) -> list[dict[str, Any]]:
    """The stage 4 gate's recorded deferrals (``id`` is the deferral category), or none."""

    gate = next((row for row in tracker.get("work_items") or [] if row.get("id") == SOURCE_SEED_ID), None)
    record = (gate or {}).get("source_gate")
    rows = record.get("deferrals") if isinstance(record, dict) else None
    return [
        {"id": str(row.get("id")), "artifacts": sorted(str(value) for value in row.get("artifacts") or []),
         "issue": row.get("issue"), "approval": (row.get("approval") or {}).get("at")}
        for row in rows or []
        if isinstance(row, dict)
    ]


def accepted_plans(root: Path, tracker: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(every accepted stage 4 owner plan, as cited by its item; input notes).

    Each plan comes through ``source_apply.cited_plan`` (its current SHA-256
    is one the accepted item cites).  The notes name the stage 4 file
    baseline and every plan whose SHA-256 differs from the one it records.
    """

    from .source_apply import cited_plan

    stage = next((row for row in tracker.get("stages") or [] if row.get("name") == SOURCE_STAGE), {}) or {}
    plans = []
    for item in sorted(tracker.get("work_items") or [], key=lambda row: str(row.get("id"))):
        if item.get("stage") != SOURCE_STAGE or item.get("kind") not in SOURCE_PLAN_KINDS or item.get("status") != "accepted":
            continue
        plan, relative, sha = cited_plan(root, tracker, item["id"])
        plans.append({"item": item["id"], "kind": item["kind"], "path": relative, "sha256": sha, "plan": plan})
    if not plans:
        raise SocomError(f"no accepted {SOURCE_STAGE} owner plans: the order target needs stage 4's plans")
    baseline = stage.get("baseline") if isinstance(stage.get("baseline"), dict) else None
    recorded = {row.get("item"): row.get("plan_sha256") for row in ((baseline or {}).get("state") or {}).get("plans") or []}
    notes = {
        "graph_sha256": (stage.get("decomposition") or {}).get("graph_sha256"),
        "stage4_baseline_sha256": (baseline or {}).get("baseline_sha256"),
        "changed_since_baseline": sorted(row["item"] for row in plans if baseline and recorded.get(row["item"]) != row["sha256"]),
    }
    return plans, notes


def load_inputs(root: Path, tracker: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    """Every input of ``build_order_target``, read and checked (the graph must be stage 4's)."""

    problems = verify_graph(graph)
    if problems:
        raise SocomError(f"the source graph is unusable: {'; '.join(problems)}")
    plans, notes = accepted_plans(root, tracker)
    wanted = notes["graph_sha256"]
    if wanted and graph.get("graph_sha256") != wanted:
        raise SocomError(
            f"the source graph {graph.get('graph_sha256')} is not stage 4's decomposition graph {wanted}: "
            "regenerate it (source graph --output build/source-graph/graph.json)"
        )
    return {"plans": plans, "notes": notes, "deferrals": gate_deferrals(tracker), "boundaries": boundary_symbols(root)}


# -- classes and objects --------------------------------------------------------------------


def _bindings(row: dict[str, Any]) -> set[str]:
    found = {str(item.get("binding")) for item in row.get("names") or [] if item.get("binding") is not None}
    if row.get("binding") is not None:
        found.add(str(row["binding"]))
    return found


def _names(row: dict[str, Any]) -> list[str]:
    return [str(item["name"]) for item in row.get("names") or [] if item.get("name")]


def order_class(row: dict[str, Any], header: str | None = None) -> str:
    """An owned artifact's order class (see the module docstring)."""

    if row["kind"] == "gap":
        return "compiler-generated"
    names = _names(row)
    if row["kind"] == "data" and any(LITERAL_NAME.match(name) for name in names):
        return "literal"
    if header is not None or _bindings(row) & COPY_BINDINGS or any(template_instance(name) for name in names):
        return "copy"
    return "definition"


def template_instance(name: str) -> bool:
    """Whether a mangled name is a template instance: a function template or a member of a class template."""

    value = demangle(name)
    return value is not None and ("<" in value["name"] or any("<" in component for component in value["qualifier"]))


def object_identity(owner: dict[str, Any]) -> tuple[str, str] | None:
    """(kind, object ID) of an owner row: an authored unit, a provider object, or ``None`` (fill)."""

    if owner.get("classification") == "authored" and owner.get("translation_unit"):
        return "authored", str(owner["translation_unit"])
    if owner.get("classification") == "provider":
        member = owner.get("archive_member") or {}
        name = member.get("object") or (f"gnu@{member['gnu_object']}" if member.get("gnu_object") else None)
        name = name or owner.get("translation_unit")
        if name:
            return "provider", f"{owner.get('library') or 'provider'}:{name}"
    return None


def link_entry(row: dict[str, Any]) -> str:
    """An object's line in the plain link-order list: its source path, or ``library(member)``."""

    if row["kind"] == "authored":
        return str(row.get("workspace_path") or row["object"])
    member = row.get("archive_member") or {}
    name = member.get("object") or (f"gnu@{member['gnu_object']}" if member.get("gnu_object") else row["object"].split(":", 1)[-1])
    return f"{row.get('library') or 'provider'}({name})"


# -- regions --------------------------------------------------------------------------------


def _nobits_starts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Window -> where its file bytes end (the zero-fill tail), as ``source_draft.data_regions`` finds it."""

    first: dict[str, int] = {}
    for row in rows:
        if row["kind"] == "gap" and row.get("fill") == "nobits":
            first.setdefault(row["window"], _int(row["address"]))
    ends: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        limit = first.get(row["window"])
        end = _int(row["address"]) + int(row.get("size") or 0)
        if row["kind"] == "gap" and row.get("fill") in ("zero", "nonzero") and limit is not None and end <= limit:
            ends[row["window"]].append(end)
    return {window: max(ends[window], default=limit) for window, limit in first.items()}


def order_regions(graph: dict[str, Any], boundaries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """(output-section regions in address order, artifact -> region number).

    A region is a run of artifacts with one window, one input-section
    envelope (``.data``, or ``between .rodata and .sdata``) and one fill kind
    (file bytes or the window's zero-fill tail); a linker section symbol
    (``__data_end``, ``_fbss``, ``__bss_start``, ``__static_init_end``, ...)
    opens a new one at the artifact that holds or follows it.  The label is
    the envelope text, ``from <symbol>`` when a symbol opened it, and ``#N``
    when it would repeat.  A region holding COMMON data is ``common``.
    """

    rows = sorted(graph["artifacts"], key=lambda row: _int(row["address"]))
    kinds = {row.get("id"): row.get("kind") for row in graph.get("windows") or []}
    nobits = _nobits_starts(rows)
    marks = sorted((_int(row["address"]), row["name"]) for row in boundaries)
    regions: list[dict[str, Any]] = []
    region_of: dict[str, int] = {}
    previous = None
    pending = 0
    for row in rows:
        address, end = _int(row["address"]), _int(row["end"])
        opened: set[str] = set()
        while pending < len(marks) and marks[pending][0] < max(end, address + 1):
            opened.add(marks[pending][1])
            pending += 1
        opened |= (set(_names(row)) | set(row.get("labels") or [])) & BOUNDARY_SYMBOLS
        zero = row["window"] in nobits and address >= nobits[row["window"]]
        key = (row["window"], input_section_text(row), zero)
        if key != previous or opened:
            regions.append(
                {
                    "region": len(regions) + 1,
                    "base": key[1],
                    "window": row["window"],
                    "window_kind": kinds.get(row["window"]),
                    "nobits": zero,
                    "opened_by": sorted(opened),
                    "start": address,
                    "end": end,
                    "common": False,
                    "counts": Counter(),
                    "rows": [],
                }
            )
            previous = key
        region = regions[-1]
        region["end"] = max(region["end"], end)
        region["counts"][row["kind"]] += 1
        region["common"] = region["common"] or bool(row.get("common"))
        region["rows"].append(row)
        region_of[row["id"]] = region["region"]
    seen: Counter = Counter()
    for region in regions:
        label = region["base"] + (f" from {'/'.join(region['opened_by'])}" if region["opened_by"] else "")
        seen[label] += 1
        region["label"] = label if seen[label] == 1 else f"{label} #{seen[label]}"
    return regions, region_of


def _lis_length(values: list[int]) -> int:
    tails: list[int] = []
    for value in values:
        index = bisect_left(tails, value)
        if index == len(tails):
            tails.append(value)
        else:
            tails[index] = value
    return len(tails)


# -- the target -----------------------------------------------------------------------------


def _ownership(plans: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    owner_of: dict[str, str] = {}
    plan_of: dict[str, str] = {}
    fill: set[str] = set()
    objects: dict[str, dict[str, Any]] = {}
    headers: dict[str, str] = {}
    unresolved: dict[str, dict[str, str]] = {}
    problems: list[str] = []
    for entry in plans:
        plan, item = entry["plan"], entry["item"]
        for row in plan.get("header_emits") or []:
            if isinstance(row, dict) and row.get("artifact") and row.get("header"):
                headers[str(row["artifact"])] = str(row["header"])
        for row in plan.get("unresolved") or []:
            if isinstance(row, dict) and row.get("artifact"):
                unresolved[str(row["artifact"])] = {"item": item, "reason": str(row.get("reason", ""))}
        for owner in plan.get("owners") or []:
            if not isinstance(owner, dict):
                continue
            identity = object_identity(owner)
            if identity is not None:
                kind, name = identity
                found = objects.setdefault(
                    name,
                    {"object": name, "kind": kind, "library": owner.get("library"), "plans": set(), "segments": Counter(),
                     "workspace_path": None, "original_path": None, "archive_member": None},
                )
                found["plans"].add(item)
                scope = plan.get("scope") or {}
                if scope.get("kind") == "segment" and scope.get("segment_number") is not None:
                    found["segments"][scope["segment_number"]] += len(artifact_ids(owner))
                for field in ("workspace_path", "original_path"):
                    found[field] = found[field] or owner.get(field)
                if kind == "provider":
                    member = owner.get("archive_member") or {}
                    found["archive_member"] = found["archive_member"] or {
                        "library": owner.get("library"), "object": member.get("object"),
                        "gnu_object": member.get("gnu_object"), "translation_unit": owner.get("translation_unit"),
                    }
            for artifact in artifact_ids(owner):
                if artifact not in by_id:
                    problems.append(f"{item} owns {artifact}, which is not a graph artifact")
                    continue
                if artifact in owner_of or artifact in fill:
                    problems.append(f"{artifact} is owned twice ({plan_of.get(artifact)} and {item})")
                plan_of[artifact] = item
                if identity is None:
                    fill.add(artifact)
                else:
                    owner_of[artifact] = identity[1]
    return {
        "owner_of": owner_of, "plan_of": plan_of, "fill": fill, "objects": objects, "headers": headers,
        "unresolved": unresolved, "problems": problems,
    }


def _entry(row: dict[str, Any], klass: str, plan: str | None, header: str | None) -> dict[str, Any]:
    names = _names(row)
    entry: dict[str, Any] = {
        "artifact": row["id"],
        "kind": row["kind"],
        "address": row["address"],
        "size": int(row.get("size") or 0),
        "name": names[0] if names else None,
        "binding": ",".join(sorted(_bindings(row))) or None,
        "class": klass,
        "plan": plan,
    }
    if klass == "definition" and any(GENERATED_NAME.match(name) for name in names):
        entry["generated"] = True
    if header is not None:
        entry["header"] = header
    return entry


def build_order_target(
    graph: dict[str, Any],
    plans: list[dict[str, Any]],
    *,
    deferrals: list[dict[str, Any]],
    boundaries: list[dict[str, Any]],
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The order target over every accepted plan (``plans``: ``{item, kind, sha256, plan}`` rows)."""

    by_id = {row["id"]: row for row in graph["artifacts"]}
    owned = _ownership(plans, by_id)
    owner_of, plan_of, objects, headers, unresolved = (
        owned["owner_of"], owned["plan_of"], owned["objects"], owned["headers"], owned["unresolved"],
    )
    category = {artifact: row["id"] for row in deferrals for artifact in row["artifacts"]}
    regions, _region_of = order_regions(graph, boundaries)
    code_windows = [region["window"] for region in regions if region["window_kind"] == "code"]
    text_window = code_windows[0] if code_windows else (regions[0]["window"] if regions else None)
    unplanned = sorted(
        (row for row in graph["artifacts"] if row["id"] not in plan_of and row["id"] not in unresolved),
        key=lambda row: _int(row["address"]),
    )

    # Per region: each object's runs (consecutive owned artifacts; fill and unresolved rows do not
    # break a run), its main run (the largest, the first of equals) and the sequence of objects by
    # main-run start.  Artifacts outside the main run are strays, reported with the interleaving.
    placement: dict[int, dict[str, Any]] = {}
    for region in regions:
        runs: dict[str, list[list[int]]] = defaultdict(list)
        last = None
        for index, row in enumerate(region["rows"]):
            name = owner_of.get(row["id"])
            if name is None:
                continue
            if name != last:
                runs[name].append([index, index, 0])
                last = name
            runs[name][-1][1] = index
            runs[name][-1][2] += 1
        main = {name: max(found, key=lambda run: (run[2], -run[0])) for name, found in runs.items()}
        sequence = sorted(runs, key=lambda name: main[name][0])
        placement[region["region"]] = {"runs": runs, "main": main, "sequence": sequence}

    def start(region: dict[str, Any], name: str) -> str:
        return region["rows"][placement[region["region"]]["main"][name][0]]["address"]

    # The .text order: objects by main-run start in the first code window.
    text_rank: dict[str, int] = {}
    for region in regions:
        if region["window"] == text_window and region["window_kind"] == "code":
            for name in placement[region["region"]]["sequence"]:
                text_rank.setdefault(name, len(text_rank))
    # The global order: .text, then every object without code, in address order of its first
    # appearance, right after the latest object that precedes it in any region it shares.
    order = sorted(text_rank, key=text_rank.get)
    placed = set(order)
    appearance: dict[str, tuple[bool, int]] = {}
    for region in regions:
        for name in placement[region["region"]]["sequence"]:
            if name not in placed:
                key = (region["common"], _int(start(region, name)))
                appearance[name] = min(appearance.get(name, key), key)
    for name in sorted(appearance, key=lambda name: (appearance[name], name)):
        position = {other: index for index, other in enumerate(order)}
        before = -1
        for region in regions:
            sequence = placement[region["region"]]["sequence"]
            if name not in sequence:
                continue
            index = sequence.index(name)
            before = max([before] + [position[other] for other in sequence[:index] if other in position])
        if before < 0:
            # Nothing precedes it anywhere: before the earliest object that follows it.
            after = [
                position[other]
                for region in regions
                if name in placement[region["region"]]["sequence"]
                for other in placement[region["region"]]["sequence"][placement[region["region"]]["sequence"].index(name) + 1 :]
                if other in position
            ]
            order.insert(min(after) if after else len(order), name)
        else:
            order.insert(before + 1, name)
        placed.add(name)
    for name in sorted(set(objects) - placed):
        order.append(name)  # owns nothing that lies in a region (cannot happen with a complete graph)
    link_index = {name: index for index, name in enumerate(order)}

    # Region checks: against the .text order and against the merged link order.
    checks = []
    for region in regions:
        info = placement[region["region"]]
        sequence = info["sequence"]
        row: dict[str, Any] = {
            "region": region["region"], "label": region["label"], "objects": len(sequence),
            "split_objects": sum(1 for name in sequence if len(info["runs"][name]) > 1),
        }
        if region["common"]:
            row.update(checked=False, reason=COMMON_REASON, compared=0, drops=0, out_of_order=0, examples=[],
                       link_violations=0, link_examples=[])
            checks.append(row)
            continue
        compared = [name for name in sequence if name in text_rank]
        drops = [(a, b) for a, b in zip(compared, compared[1:]) if text_rank[a] > text_rank[b]]
        violations = [(a, b) for a, b in zip(sequence, sequence[1:]) if link_index[a] > link_index[b]]
        row.update(
            checked=True,
            compared=len(compared),
            drops=len(drops),
            out_of_order=len(compared) - _lis_length([text_rank[name] for name in compared]),
            examples=[
                {"before": a, "at": start(region, a), "after": b, "after_at": start(region, b)} for a, b in drops[:_SHOWN]
            ],
            link_violations=len(violations),
            link_examples=[
                {"before": a, "at": start(region, a), "after": b, "after_at": start(region, b)} for a, b in violations[:_SHOWN]
            ],
        )
        checks.append(row)

    # Objects (authored units and opaque provider objects) in link order.
    object_rows = []
    for name in order:
        found = objects[name]
        sections = []
        for region in regions:
            info = placement[region["region"]]
            if name not in info["runs"]:
                continue
            found_runs = info["runs"][name]
            sections.append(
                {
                    "region": region["region"], "label": region["label"], "start": start(region, name),
                    "first": region["rows"][found_runs[0][0]]["address"], "end": region["rows"][found_runs[-1][1]]["end"],
                    "count": sum(run[2] for run in found_runs), "runs": len(found_runs),
                }
            )
        object_rows.append(
            {
                "position": link_index[name] + 1,
                "object": name,
                "kind": found["kind"],
                "library": found["library"],
                "workspace_path": found["workspace_path"],
                "original_path": found["original_path"],
                "archive_member": found["archive_member"],
                "plans": sorted(found["plans"]),
                "segments": sorted(found["segments"]),
                # The segment plan owning most of its artifacts (the lowest of equals): where it is planned once.
                "primary_segment": min(found["segments"], key=lambda number: (-found["segments"][number], number))
                if found["segments"] else None,
                "text_position": text_rank[name] + 1 if name in text_rank else None,
                "sections": sections,
            }
        )

    # Authored units: owned artifacts with their class, the fill and deferred rows inside their runs,
    # and the interleaving (strays outside the main run, the objects between the runs).
    units = []
    findings: list[dict[str, Any]] = []
    inside_span: set[str] = set()
    for object_row in object_rows:
        if object_row["kind"] != "authored":
            continue
        name = object_row["object"]
        sections = []
        counts: Counter = Counter()
        generated = 0
        for region in regions:
            info = placement[region["region"]]
            found_runs = info["runs"].get(name)
            if not found_runs:
                continue
            rows = region["rows"]
            main = info["main"][name]
            entries, deferred, strays = [], [], []
            for low, high, _count in found_runs:
                for index in range(low, high + 1):
                    row = rows[index]
                    identity = row["id"]
                    if owner_of.get(identity) == name:
                        entry = _entry(row, order_class(row, headers.get(identity)), plan_of.get(identity), headers.get(identity))
                        entries.append(entry)
                        if low != main[0]:
                            strays.append(entry)
                    elif identity in unresolved:
                        inside_span.add(identity)
                        deferred.append(
                            {"artifact": identity, "kind": row["kind"], "name": (_names(row) or [None])[0],
                             "category": category.get(identity), "item": unresolved[identity]["item"]}
                        )
                    elif row["kind"] == "gap" and identity in owned["fill"]:
                        entries.append(_entry(row, "compiler-generated", plan_of.get(identity), None))
            between = Counter(
                owner_of[rows[index]["id"]]
                for index in range(found_runs[0][0], found_runs[-1][1] + 1)
                if owner_of.get(rows[index]["id"]) not in (None, name)
            )
            section_counts = Counter(entry["class"] for entry in entries)
            counts.update(section_counts)
            generated += sum(1 for entry in entries if entry.get("generated"))
            section: dict[str, Any] = {
                "region": region["region"],
                "label": region["label"],
                "start": rows[main[0]]["address"],
                "first": rows[found_runs[0][0]]["address"],
                "last": rows[found_runs[-1][1]]["address"],
                "end": rows[found_runs[-1][1]]["end"],
                "count": len(entries),
                "counts": {klass: section_counts[klass] for klass in ORDER_CLASSES if section_counts[klass]},
                "runs": len(found_runs),
                "contiguous": len(found_runs) == 1,
                "artifacts": entries,
                "deferred": deferred,
            }
            if len(found_runs) > 1:
                section["strays"] = [{key: entry[key] for key in ("artifact", "name", "class")} for entry in strays]
                section["between"] = {
                    "objects": len(between),
                    "artifacts": sum(between.values()),
                    "shown": [other for other, _ in sorted(between.items(), key=lambda item: (-item[1], item[0]))[:_SHOWN]],
                }
            if region["common"]:
                section["note"] = COMMON_REASON
            sections.append(section)
            if len(found_runs) > 1 and not region["common"]:
                findings.append(
                    {"kind": "interleaved", "unit": name, "region": region["region"], "label": region["label"],
                     "runs": len(found_runs), "artifact": strays[0]["artifact"] if strays else None,
                     "stray_classes": dict(sorted(Counter(entry["class"] for entry in strays).items())),
                     "intruders": section["between"]["shown"], "intruder_count": section["between"]["objects"]}
                )
            for row in deferred:
                findings.append(
                    {"kind": "deferred-in-span", "unit": name, "region": region["region"], "label": region["label"],
                     "artifact": row["artifact"], "category": row["category"], "item": row["item"]}
                )
        units.append(
            {
                "unit": name,
                "workspace_path": object_row["workspace_path"],
                "original_path": object_row["original_path"],
                "plans": object_row["plans"],
                "segments": object_row["segments"],
                "primary_segment": object_row["primary_segment"],
                "link_position": object_row["position"],
                "text_position": object_row["text_position"],
                "counts": {**{klass: counts[klass] for klass in ORDER_CLASSES}, "generated_definitions": generated},
                "sections": sections,
            }
        )
    for row in checks:
        if row["checked"] and row["drops"]:
            findings.append(
                {"kind": "object-order", "unit": None, "region": row["region"], "label": row["label"],
                 "drops": row["drops"], "out_of_order": row["out_of_order"]}
            )

    deferred_categories = Counter(category.get(artifact) or "undeferred" for artifact in unresolved)
    outside = Counter(category.get(artifact) or "undeferred" for artifact in unresolved if artifact not in inside_span)
    class_counts = Counter()
    for unit in units:
        class_counts.update({klass: unit["counts"][klass] for klass in ORDER_CLASSES})
    kinds = Counter(row["kind"] for row in object_rows)
    summary = {
        "units": len(units),
        "provider_objects": kinds["provider"],
        "objects": len(object_rows),
        "regions": len(regions),
        "classes": {klass: class_counts[klass] for klass in ORDER_CLASSES},
        "generated_definitions": sum(unit["counts"]["generated_definitions"] for unit in units),
        "interleaved_units": len({row["unit"] for row in findings if row["kind"] == "interleaved"}),
        "interleaving_findings": sum(1 for row in findings if row["kind"] == "interleaved"),
        "interleaving_definition_findings": sum(
            1 for row in findings if row["kind"] == "interleaved" and row["stray_classes"].get("definition")
        ),
        "deferred_in_spans": sum(1 for row in findings if row["kind"] == "deferred-in-span"),
        "deferred_in_spans_by_category": dict(sorted(Counter(row["category"] or "undeferred" for row in findings if row["kind"] == "deferred-in-span").items())),
        "unresolved": len(unresolved),
        "unresolved_by_category": dict(sorted(deferred_categories.items())),
        "unresolved_outside_spans": dict(sorted(outside.items())),
        "object_order_disagreements": sum(1 for row in checks if row["checked"] and row["drops"]),
        "object_order_drops": sum(row["drops"] for row in checks if row["checked"]),
        "link_violations": sum(row["link_violations"] for row in checks if row["checked"]),
        "split_contributions": sum(row["split_objects"] for row in checks if row["checked"]),
        "unplanned_artifacts": len(unplanned),
        "problems": len(owned["problems"]),
    }
    target = {
        "kind": ORDER_TARGET_KIND,
        "schema_version": ORDER_TARGET_SCHEMA,
        "rules_version": ORDER_RULES_VERSION,
        "inputs": {
            "source_sha256": graph.get("source_sha256", REFERENCE_SHA256),
            "graph_sha256": graph.get("graph_sha256"),
            "plans": [{"item": row["item"], "sha256": row["sha256"]} for row in sorted(plans, key=lambda row: row["item"])],
            "deferrals_sha256": _digest(deferrals),
            "boundary_symbols": boundaries,
            **{key: value for key, value in (notes or {}).items() if key != "graph_sha256"},
        },
        "classes": {klass: {"verified_in": VERIFIED_IN[klass]} for klass in ORDER_CLASSES},
        "text_window": text_window,
        "regions": [
            {
                "region": region["region"], "label": region["label"], "window": region["window"],
                "window_kind": region["window_kind"], "start": _hex(region["start"]), "end": _hex(region["end"]),
                "nobits": region["nobits"], "common": region["common"], "opened_by": region["opened_by"],
                "counts": dict(sorted(region["counts"].items())),
            }
            for region in regions
        ],
        "objects": object_rows,
        "units": sorted(units, key=lambda unit: unit["link_position"]),
        "checks": checks,
        "findings": findings,
        "unplanned": [row["id"] for row in unplanned[:_SHOWN]],
        "problems": owned["problems"][:_SHOWN],
        "summary": summary,
    }
    target["order_sha256"] = order_digest(target)
    return target


# -- views ----------------------------------------------------------------------------------


def select_units(target: dict[str, Any], *, unit: str | None = None, segment: int | None = None) -> list[dict[str, Any]]:
    """The units a selection names: one unit (exact, else case-insensitive) or every unit of a segment plan."""

    units = target["units"]
    if unit is not None:
        found = [row for row in units if row["unit"] == unit] or [row for row in units if row["unit"].casefold() == unit.casefold()]
        if not found:
            raise SocomError(f"no authored unit {unit!r} in the accepted owner plans")
        return found
    if segment is not None:
        found = [row for row in units if segment in row["segments"]]
        if not found:
            raise SocomError(f"segment {segment} has no accepted authored owner plan")
        return found
    return units


def order_view(target: dict[str, Any], units: list[dict[str, Any]], selection: dict[str, Any]) -> dict[str, Any]:
    """A selection of the target: its units, the regions they touch and their findings."""

    names = {row["unit"] for row in units}
    touched = {section["region"] for row in units for section in row["sections"]}
    return {
        "kind": ORDER_VIEW_KIND,
        "schema_version": ORDER_TARGET_SCHEMA,
        "order_sha256": target["order_sha256"],
        "selection": selection,
        "inputs": {key: target["inputs"][key] for key in ("graph_sha256", "deferrals_sha256")},
        "classes": target["classes"],
        "regions": [row for row in target["regions"] if row["region"] in touched],
        "units": units,
        "findings": [row for row in target["findings"] if row["unit"] in names],
    }


def counts(target: dict[str, Any]) -> dict[str, Any]:
    return {"order_sha256": target["order_sha256"], **target["summary"]}


# -- link order -----------------------------------------------------------------------------


def link_order(target: dict[str, Any]) -> dict[str, Any]:
    """The link-order specification (``socom-link-order``) with its static check against every region."""

    objects = [
        {
            "position": row["position"],
            "object": row["object"],
            "kind": row["kind"],
            "source": row["workspace_path"] if row["kind"] == "authored" else None,
            "archive_member": row["archive_member"],
            "original_path": row["original_path"],
            "entry": link_entry(row),
            "sections": [section["label"] for section in row["sections"]],
        }
        for row in target["objects"]
    ]
    violations = [
        {"region": row["region"], "label": row["label"], "count": row["link_violations"], "examples": row["link_examples"]}
        for row in target["checks"]
        if row["checked"] and row["link_violations"]
    ]
    splits = [
        {"region": row["region"], "label": row["label"], "objects": row["split_objects"]}
        for row in target["checks"]
        if row["checked"] and row["split_objects"]
    ]
    body = {
        "kind": LINK_ORDER_KIND,
        "schema_version": LINK_ORDER_SCHEMA,
        "order_sha256": target["order_sha256"],
        "graph_sha256": target["inputs"]["graph_sha256"],
        "objects": objects,
        "check": {
            "ok": not violations,
            "regions_checked": sum(1 for row in target["checks"] if row["checked"]),
            "regions_skipped": [{"region": row["region"], "label": row["label"], "reason": row["reason"]} for row in target["checks"] if not row["checked"]],
            "violations": sum(row["count"] for row in violations),
            "violation_regions": violations,
            "split_contributions": sum(row["objects"] for row in splits),
            "split_regions": splits,
        },
    }
    body["link_order_sha256"] = _digest([[row["position"], row["object"], row["entry"]] for row in objects])
    return body


def link_order_text(body: dict[str, Any]) -> str:
    lines = [
        f"# {LINK_ORDER_KIND} schema {LINK_ORDER_SCHEMA}: {len(body['objects'])} objects in link order",
        f"# link_order_sha256 {body['link_order_sha256']}",
        f"# order_sha256 {body['order_sha256']}",
    ]
    lines.extend(row["entry"] for row in body["objects"])
    return "\n".join(lines) + "\n"


# -- the SQLite cache -----------------------------------------------------------------------

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
-- Output-section regions in address order (see order_regions).
CREATE TABLE regions (
  region INTEGER PRIMARY KEY, label TEXT, "window" TEXT, window_kind TEXT, start INTEGER, "end" INTEGER,
  nobits INTEGER, common INTEGER, opened_by TEXT, functions INTEGER, data INTEGER, gaps INTEGER);
-- Authored units and provider objects in link order; text_position: rank in .text order.
CREATE TABLE objects (
  position INTEGER PRIMARY KEY, object TEXT, kind TEXT, library TEXT, workspace_path TEXT, original_path TEXT,
  member TEXT, entry TEXT, plans TEXT, segments TEXT, primary_segment INTEGER, text_position INTEGER);
-- Each object's contribution to a region: first address, end, owned artifacts, runs (1 = contiguous).
CREATE TABLE contributions (
  object TEXT, position INTEGER, region INTEGER, label TEXT, first INTEGER, "end" INTEGER, count INTEGER, runs INTEGER);
-- Every artifact an authored unit owns (and its interior fill), with its order class.
-- ordinal: position in the unit's region list; address/size integers.
CREATE TABLE targets (
  artifact TEXT, unit TEXT, region INTEGER, label TEXT, ordinal INTEGER, address INTEGER, size INTEGER,
  kind TEXT, name TEXT, binding TEXT, class TEXT, generated INTEGER, header TEXT, plan TEXT);
-- interleaved, deferred-in-span and object-order findings.
CREATE TABLE findings (
  kind TEXT, unit TEXT, region INTEGER, label TEXT, artifact TEXT, category TEXT, item TEXT, runs INTEGER,
  intruders TEXT, drops INTEGER, out_of_order INTEGER);
-- Per-region object-order checks against .text and the merged link order.
CREATE TABLE checks (
  region INTEGER PRIMARY KEY, label TEXT, checked INTEGER, objects INTEGER, compared INTEGER, drops INTEGER,
  out_of_order INTEGER, link_violations INTEGER, split_objects INTEGER, reason TEXT);
CREATE INDEX targets_unit ON targets(unit);
CREATE INDEX targets_artifact ON targets(artifact);
CREATE INDEX contributions_object ON contributions(object);
"""
TABLES = ("meta", "regions", "objects", "contributions", "targets", "findings", "checks")


def cache_fingerprint(root: Path, tracker: dict[str, Any], graph_path: Path) -> dict[str, str]:
    """What the cache depends on, cheaply: the graph file, the cited plans and the gate deferrals."""

    plans, notes = accepted_plans(root, tracker)
    return {
        "cache_version": CACHE_VERSION,
        "schema_sha256": hashlib.sha256(SCHEMA.encode("utf-8")).hexdigest(),
        "rules_version": str(ORDER_RULES_VERSION),
        "graph_file_sha256": sha256_file(graph_path),
        "plans_sha256": _digest([[row["item"], row["sha256"]] for row in plans]),
        "deferrals_sha256": _digest(gate_deferrals(tracker)),
        "stage4_baseline_sha256": str(notes.get("stage4_baseline_sha256")),
    }


def _stored(path: Path) -> dict[str, str] | None:
    if not path.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as connection:
            return dict(connection.execute("SELECT key, value FROM meta"))
    except sqlite3.Error:
        return None


def cache_fresh(path: Path, fingerprint: dict[str, str]) -> bool:
    stored = _stored(path)
    return stored is not None and all(stored.get(key) == value for key, value in fingerprint.items())


def write_cache(path: Path, target: dict[str, Any], fingerprint: dict[str, str]) -> None:
    """(Re)build the order cache from a target, atomically."""

    regions = [
        (row["region"], row["label"], row["window"], row["window_kind"], _int(row["start"]), _int(row["end"]),
         int(row["nobits"]), int(row["common"]), "/".join(row["opened_by"]) or None,
         row["counts"].get("function", 0), row["counts"].get("data", 0), row["counts"].get("gap", 0))
        for row in target["regions"]
    ]
    objects, contributions = [], []
    for row in target["objects"]:
        member = row.get("archive_member") or {}
        objects.append(
            (row["position"], row["object"], row["kind"], row["library"], row["workspace_path"], row["original_path"],
             member.get("object") or member.get("gnu_object"), link_entry(row), ",".join(row["plans"]),
             ",".join(str(number) for number in row["segments"]) or None, row["primary_segment"], row["text_position"])
        )
        for section in row["sections"]:
            contributions.append(
                (row["object"], row["position"], section["region"], section["label"], _int(section["first"]),
                 _int(section["end"]), section["count"], section["runs"])
            )
    targets = [
        (entry["artifact"], unit["unit"], section["region"], section["label"], ordinal, _int(entry["address"]), entry["size"],
         entry["kind"], entry["name"], entry["binding"], entry["class"], int(bool(entry.get("generated"))), entry.get("header"),
         entry["plan"])
        for unit in target["units"]
        for section in unit["sections"]
        for ordinal, entry in enumerate(section["artifacts"])
    ]
    findings = [
        (row["kind"], row.get("unit"), row["region"], row["label"], row.get("artifact"), row.get("category"), row.get("item"),
         row.get("runs"), ",".join(row.get("intruders") or []) or None, row.get("drops"), row.get("out_of_order"))
        for row in target["findings"]
    ]
    checks = [
        (row["region"], row["label"], int(row["checked"]), row["objects"], row["compared"], row["drops"], row["out_of_order"],
         row["link_violations"], row["split_objects"], row.get("reason"))
        for row in target["checks"]
    ]
    meta = {**fingerprint, "order_sha256": target["order_sha256"], "graph_sha256": str(target["inputs"]["graph_sha256"])}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    with closing(sqlite3.connect(temporary)) as connection:
        connection.executescript(SCHEMA)
        connection.executemany("INSERT INTO meta VALUES (?, ?)", sorted(meta.items()))
        for table, rows in (
            ("regions", regions), ("objects", objects), ("contributions", contributions), ("targets", targets),
            ("findings", findings), ("checks", checks),
        ):
            if rows:
                connection.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        connection.commit()
    try:
        _replace(temporary, path)
    except PermissionError:
        temporary.unlink(missing_ok=True)
        if not cache_fresh(path, fingerprint):
            raise
