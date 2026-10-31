"""Stage 4 (source-correlation): planning scopes and source-owner plans.

The stage is decomposed from ``source graph`` (``source_graph.py``).  Every
artifact of the graph lies in exactly one planning scope:

* an authored segment: the segment's artifacts, the code gaps between it and
  the next segment of its window, and its data slice;
* a provider library: the same, for every segment whose functions are mostly
  that library's (a strict majority of the segment's functions);
* a data kind (``rodata``, ``data``, ``bss``): every artifact that no segment
  slice holds, by the input section that holds it (or, outside every section
  envelope, the one after it).

A ``socom-source-owner-plan`` (schema 1) owns every artifact of one scope
exactly once, through an owner row, or lists it unresolved with a reason.
Owner rows are translation units (authored, with a workspace path), archive
members (provider, with library and GNU object or object name, no source
body) or compiler/linker output that no unit defines.  Headers never own:
they emit template, inline and weak instances through header-emit rows.  The
plan lists the annotation targets of its named artifacts, and the validator
derives the same set from the owner rows: one ``defines`` edge in the owning
source file per named artifact of an authored row, plus one ``emits`` edge in
the header of each header-emit row.  Compiler-generated artifacts (``@N``
literals, RTTI, vtables, static-init words, padding) are owned through the
owner row's artifact list only.

Plans cite the graph and the slice digests the work item was decomposed with;
a plan or graph with another digest is refused.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

from .constants import REFERENCE_SHA256
from .source_graph import SOURCE_GRAPH_KIND, SOURCE_GRAPH_SCHEMA
from .util import SocomError, canonical_json

SOURCE_STAGE = "source-correlation"
SOURCE_SEED_ID = "socom:work:source-correlation-seed"
SOURCE_APPLY_ROUTE_ID = "socom:work:source-correlation-apply-route"
SOURCE_PLAN_RESOURCES = ["build/source-plans"]
SOURCE_PLAN_KIND = "socom-source-owner-plan"
SOURCE_PLAN_SCHEMA = 1
SOURCE_EVIDENCE_KIND = "socom-source-plan-evidence"

SEGMENT_PLAN_KIND = "source-plan-segment"
SEGMENT_APPLY_KIND = "source-apply-segment"
PROVIDER_PLAN_KIND = "source-plan-provider"
PROVIDER_APPLY_KIND = "source-apply-provider"
DATA_RECONCILE_KIND = "source-data-reconcile"
CAPABILITY_GATE_KIND = "capability-gate"
SOURCE_PLAN_KINDS = (SEGMENT_PLAN_KIND, PROVIDER_PLAN_KIND, DATA_RECONCILE_KIND)
SOURCE_APPLY_KINDS = (SEGMENT_APPLY_KIND, PROVIDER_APPLY_KIND)
PLAN_KIND_BY_SCOPE = {"segment": SEGMENT_PLAN_KIND, "provider": PROVIDER_PLAN_KIND, "data": DATA_RECONCILE_KIND}
APPLY_KIND_BY_PLAN = {SEGMENT_PLAN_KIND: SEGMENT_APPLY_KIND, PROVIDER_PLAN_KIND: PROVIDER_APPLY_KIND}

SEGMENT_PREFIX = "socom:work:source-segment-"
PROVIDER_PREFIX = "socom:work:source-provider-"
DATA_PREFIX = "socom:work:source-data-"

DATA_KINDS = ("rodata", "data", "bss")
ZERO_FILL_SECTIONS = frozenset({".bss", ".sbss", ".vubss"})
SKELETON_REASON = "not yet planned"
CLASSIFICATIONS = ("authored", "provider", "compiler-generated")
CONFIDENCES = ("high", "medium", "low")
EMIT_REASONS = ("template", "inline", "weak")
SOURCE_FILE_SUFFIXES = (".c", ".cc", ".cp", ".cpp", ".cxx", ".s")
HEADER_SUFFIXES = (".h", ".hh", ".hpp", ".inc")

PLAN_FIELDS = frozenset(
    {
        "kind",
        "schema_version",
        "work_item_id",
        "scope",
        "graph_sha256",
        "slice_sha256",
        "target",
        "owners",
        "header_emits",
        "annotations",
        "unresolved",
        "retire_files",
        "notes",
        "reservation",
    }
)
RESERVATION_FIELDS = frozenset({"directories", "status", "reason", "evidence"})
RESERVATION_STATUSES = ("confirmed", "corrected")
INFERRED_STATUS = "inferred"
OWNER_FIELDS = frozenset(
    {
        "translation_unit",
        "classification",
        "workspace_path",
        "original_path",
        "provisional_file",
        "library",
        "archive_member",
        "confidence",
        "evidence",
        "artifacts",
    }
)
ANNOTATION_FIELDS = ("artifact", "relation", "section", "path")
_COMPILER_NAME = re.compile(r"^(?:@\d+(?:@.*)?|__RTTI__.*|__vt__.*|__sinit_.*|\.p__sinit_.*)$")
_FILE_NAME = re.compile(r"^[A-Za-z0-9_.+-]+$")
_SHOWN = 12


# -- graph and scopes -----------------------------------------------------------


def graph_digest(graph: dict[str, Any]) -> str:
    """The digest ``source graph`` stores: canonical JSON of everything else."""

    body = {key: value for key, value in graph.items() if key != "graph_sha256"}
    return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()


def verify_graph(graph: Any) -> list[str]:
    """Problems that make a graph unusable as planning evidence."""

    if not isinstance(graph, dict):
        return ["the source graph must be a JSON object"]
    problems = []
    if graph.get("kind") != SOURCE_GRAPH_KIND or graph.get("schema_version") != SOURCE_GRAPH_SCHEMA:
        problems.append(f"not a {SOURCE_GRAPH_KIND} schema {SOURCE_GRAPH_SCHEMA} document")
    if graph.get("source_sha256") != REFERENCE_SHA256:
        problems.append("the source graph was not built from the reference ELF")
    if not problems and graph_digest(graph) != graph.get("graph_sha256"):
        problems.append("the source graph's content differs from its graph_sha256")
    return problems


def library_slug(library: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", library.casefold()).strip("-")
    if not slug:
        raise SocomError(f"library {library!r} has no usable slug")
    return slug


def segment_family(segment: dict[str, Any]) -> tuple[str, str | None]:
    """("provider", library) when one library holds most functions, else ("authored", None).

    Segments already cut at every classification change, so a segment holds
    at most one family besides the neutral compiler-generated and unknown
    functions.  A segment of mostly compiler-generated functions (the
    static-initializer window) is planned like an authored segment: its units
    own what they emit.
    """

    mix = segment.get("classification_mix") or {}
    total = sum(mix.values())
    providers = sorted((key, count) for key, count in mix.items() if key.startswith("provider:"))
    if providers:
        key, count = max(providers, key=lambda row: row[1])
        if 2 * count > total:
            return "provider", key.split(":", 1)[1]
    return "authored", None


def data_kind(row: dict[str, Any]) -> str:
    """The reconcile kind of an artifact outside every segment slice."""

    section = row.get("input_section") or {}
    name = section.get("name")
    if name is None:
        before, after = (list(section.get("between") or []) + [None, None])[:2]
        name = after or before
    if name == ".rodata":
        return "rodata"
    if name in ZERO_FILL_SECTIONS:
        return "bss"
    return "data"


def slice_sha256(artifacts: list[str]) -> str:
    return hashlib.sha256(canonical_json(list(artifacts)).encode("utf-8")).hexdigest()


def scope_key(scope: Any) -> str:
    if not isinstance(scope, dict):
        raise SocomError(f"unknown planning scope {scope!r}")
    kind = scope.get("kind")
    if kind == "segment":
        return f"segment:{scope.get('segment_id')}"
    if kind == "provider":
        return f"provider:{scope.get('library')}"
    if kind == "data":
        return f"data:{scope.get('data_kind')}"
    raise SocomError(f"unknown planning scope {scope!r}")


def scope_item_id(scope: dict[str, Any]) -> str:
    kind = scope.get("kind")
    if kind == "segment":
        return f"{SEGMENT_PREFIX}{int(scope['segment_number']):03d}"
    if kind == "provider":
        return f"{PROVIDER_PREFIX}{library_slug(str(scope['library']))}"
    if kind == "data":
        return f"{DATA_PREFIX}{scope['data_kind']}"
    raise SocomError(f"unknown planning scope {scope!r}")


def planning_scopes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Every planning scope of the graph with its slice, in address order.

    The slices partition the graph's artifacts.  Each entry holds the
    ``scope``, the graph ``segments`` it covers, its ``artifacts`` in graph
    order and their ``slice_sha256``.
    """

    rows = graph["artifacts"]
    position = {row["id"]: index for index, row in enumerate(rows)}
    segments = graph["segments"]
    slices: list[list[str]] = []
    for number, segment in enumerate(segments):
        ids = list(segment["artifacts"])
        following = segments[number + 1] if number + 1 < len(segments) else None
        if following is not None and following["window"] == segment["window"]:
            # The code gaps between two segments of one window (alignment
            # fill after a function) go with the segment before them.
            for index in range(position[ids[-1]] + 1, position[following["artifacts"][0]]):
                row = rows[index]
                if row["kind"] != "gap" or row["window"] != segment["window"]:
                    raise SocomError(f"{row['id']} lies between two segments but is not a code gap")
                ids.append(row["id"])
        ids.extend(segment["data"])
        slices.append(ids)

    entries: list[dict[str, Any]] = []
    providers: dict[str, dict[str, Any]] = {}
    for segment, ids in zip(segments, slices):
        family, library = segment_family(segment)
        if family == "provider":
            assert library is not None
            entry = providers.get(library)
            if entry is None:
                entry = providers[library] = {"scope": {"kind": "provider", "library": library}, "segments": [], "artifacts": []}
                entries.append(entry)
            entry["segments"].append(segment)
            entry["artifacts"].extend(ids)
        else:
            entries.append(
                {
                    "scope": {"kind": "segment", "segment_id": segment["id"], "segment_number": segment["segment_number"]},
                    "segments": [segment],
                    "artifacts": ids,
                }
            )
    held: set[str] = set()
    for entry in entries:
        for identity in entry["artifacts"]:
            if identity in held:
                raise SocomError(f"{identity} lies in two planning scopes")
            held.add(identity)
    data: dict[str, list[str]] = {kind: [] for kind in DATA_KINDS}
    for row in rows:
        if row["id"] not in held:
            data[data_kind(row)].append(row["id"])
    for kind in DATA_KINDS:
        if data[kind]:
            entries.append({"scope": {"kind": "data", "data_kind": kind}, "segments": [], "artifacts": data[kind]})
    for entry in entries:
        entry["artifacts"].sort(key=position.__getitem__)
        entry["slice_sha256"] = slice_sha256(entry["artifacts"])
    return entries


def scope_batches(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """The tracker batch of every planning scope, in item order."""

    rows = {row["id"]: row for row in graph["artifacts"]}
    count = len(graph["segments"])
    batches = []
    for entry in planning_scopes(graph):
        scope = entry["scope"]
        kinds = Counter(rows[identity]["kind"] for identity in entry["artifacts"])
        batch: dict[str, Any] = {
            "scope": dict(scope),
            "graph_sha256": graph["graph_sha256"],
            "slice_sha256": entry["slice_sha256"],
            "artifact_count": len(entry["artifacts"]),
            "function_count": kinds.get("function", 0),
            "data_count": kinds.get("data", 0),
            "gap_count": kinds.get("gap", 0),
            "named_count": sum(1 for identity in entry["artifacts"] if named(rows[identity])),
        }
        if scope["kind"] == "data":
            batch["batch_number"] = count + 1 + DATA_KINDS.index(scope["data_kind"])
        else:
            segments = entry["segments"]
            mix: Counter[str] = Counter()
            for segment in segments:
                mix.update(segment["classification_mix"])
            batch.update(
                batch_number=segments[0]["segment_number"],
                segment_numbers=[segment["segment_number"] for segment in segments],
                ranges=[[segment["start"], segment["end"]] for segment in segments],
                classification_mix=dict(sorted(mix.items())),
            )
            if scope["kind"] == "segment":
                batch["tu_candidates"] = [row["tu"] for row in segments[0]["tu_candidates"]]
        batches.append(batch)
    return batches


def original_module(path: str) -> str | None:
    """The workspace module directory an original ``Z:\\dev`` source path names."""

    pure = PureWindowsPath(path)
    parts = pure.parts
    if pure.drive.casefold() != "z:" or len(parts) < 4 or parts[1].casefold() != "dev":
        return None
    return "/".join(("src", *parts[2:-1]))


def tu_prefix(unit: str) -> str:
    """The module prefix of a unit name: its stem up to the first ``_``.

    ``zui_skb.cpp`` and ``zui.cpp`` both have the prefix ``zui``.
    """

    return PurePosixPath(unit).stem.split("_", 1)[0].casefold()


def _directories_text(directories: list[str]) -> str:
    return ", ".join(directories)


def apply_reservations(root: Path, graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The ``src/`` reservation of each authored-segment apply item, by scope key.

    Each value holds the ``directories`` the apply reserves, whether they are
    ``inferred``, and the ``reason`` for an inference or the fallback.

    A unit's directory is the existing workspace spelling of its original
    ``Z:\\dev`` module (placement keeps ``src/<Apps|gamez>/<module>/``), else
    the directory of a provisional file of the same name.  A segment reserves
    its units' directories.  When none of its units has such evidence, the
    directory is inferred from its neighbours: for each unit, the nearest
    segments of the same window (by distance in segment order, both sides,
    authored segments with evidence only) whose units share the unit's
    TU-name prefix (``tu_prefix``) give the directories those units resolve
    to.  The plan must confirm or correct an inference.  Only a segment with
    no inference reserves all of ``src``.  Provider applies reserve nothing:
    they write no file under ``src/``.
    """

    directories: dict[str, str] = {}
    by_basename: dict[str, set[str]] = defaultdict(set)
    source = root / "src"
    if source.is_dir():
        for path in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
            relative = path.relative_to(root).as_posix()
            if path.is_dir():
                directories.setdefault(relative.casefold(), relative)
            elif path.is_file():
                by_basename[path.name.casefold()].add(path.parent.relative_to(root).as_posix())
    paths = {unit["tu"].casefold(): unit["paths"] for unit in graph["units"]}

    def unit_directories(unit: str) -> set[str]:
        modules = [module for module in map(original_module, paths.get(unit.casefold(), [])) if module]
        if modules:
            return {directories.get(module.casefold(), module) for module in modules}
        return set(by_basename.get(unit.casefold(), ()))

    segments = graph["segments"]
    evidenced: dict[str, list[str]] = {}
    for segment in segments:
        if segment_family(segment)[0] == "authored":
            found: set[str] = set()
            for candidate in segment["tu_candidates"]:
                found.update(unit_directories(candidate["tu"]))
            evidenced[segment["id"]] = sorted(found, key=str.casefold)

    def infer(segment: dict[str, Any]) -> tuple[list[str], str]:
        window = [row for row in segments if row["window"] == segment["window"]]
        position = next(index for index, row in enumerate(window) if row["id"] == segment["id"])
        inferred: set[str] = set()
        clauses: list[str] = []
        lacking: list[str] = []
        for candidate in segment["tu_candidates"]:
            unit = candidate["tu"]
            prefix = tu_prefix(unit)
            hits: list[tuple[int, str, list[str]]] = []
            for distance in range(1, len(window)):
                for index in (position - distance, position + distance):
                    if not 0 <= index < len(window) or not evidenced.get(window[index]["id"]):
                        continue
                    for other in window[index]["tu_candidates"]:
                        if other["tu"].casefold() == unit.casefold() or tu_prefix(other["tu"]) != prefix:
                            continue
                        if found := sorted(unit_directories(other["tu"]), key=str.casefold):
                            hits.append((window[index]["segment_number"], other["tu"], found))
                if hits:
                    break
            if not hits:
                lacking.append(unit)
                continue
            places = sorted({value for _number, _unit, found in hits for value in found}, key=str.casefold)
            inferred.update(places)
            support = "; ".join(
                f"segment {number:03d} {name}" for number, name, _found in sorted(hits, key=lambda row: (row[0], row[1]))
            )
            clauses.append(
                f"{unit} has no path or provisional-file evidence; the nearest units with its TU-name prefix "
                f"{prefix!r} ({support}) lie in {_directories_text(places)}"
            )
        if lacking:
            clauses.append(f"no neighbouring unit shares the TU-name prefix of {', '.join(lacking)}")
        return sorted(inferred, key=str.casefold), "; ".join(clauses)

    result: dict[str, dict[str, Any]] = {}
    for entry in planning_scopes(graph):
        scope = entry["scope"]
        if scope["kind"] != "segment":
            continue
        segment = entry["segments"][0]
        found = evidenced[segment["id"]]
        if found:
            result[scope_key(scope)] = {"directories": found, "inferred": False, "reason": None}
            continue
        inferred, reason = infer(segment) if segment["tu_candidates"] else ([], "the segment has no unit candidates")
        if inferred:
            result[scope_key(scope)] = {"directories": inferred, "inferred": True, "reason": reason}
        else:
            result[scope_key(scope)] = {
                "directories": ["src"],
                "inferred": False,
                "reason": f"fallback to all of src: {reason}",
            }
    return result


def apply_reservation(tracker: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    """The reservation of a segment plan item's apply item, or ``None``."""

    if item.get("kind") != SEGMENT_PLAN_KIND:
        return None
    apply_id = f"{item['id']}-apply"
    apply = next((row for row in tracker.get("work_items", []) if row.get("id") == apply_id), None)
    if apply is None or apply.get("kind") != SEGMENT_APPLY_KIND:
        return {"apply_item": apply_id, "missing": True, "directories": [], "inferred": False, "reason": None}
    batch = apply.get("batch") or {}
    return {
        "apply_item": apply_id,
        "missing": False,
        "directories": sorted(apply.get("resources") or [], key=str.casefold),
        "inferred": batch.get("resource_inferred") is True,
        "reason": batch.get("resource_reason"),
    }


def _within(path: str, directories: list[str]) -> bool:
    return any(path.startswith(f"{directory}/") for directory in directories)


# -- artifacts ------------------------------------------------------------------


def named(row: dict[str, Any]) -> bool:
    """A function or data artifact with a name the compiler did not invent."""

    return row.get("kind") != "gap" and any(
        item.get("name") and not _COMPILER_NAME.match(item["name"]) for item in row.get("names") or []
    )


def _address(identity: str) -> int:
    try:
        return int(identity.rsplit(":", 1)[1], 16)
    except (IndexError, ValueError):
        return -1


def loaded_section_lookup(root: Path) -> Callable[[int], str | None]:
    """Address -> the census section that opens the load segment holding it.

    Zero-fill memory past ``main``'s file bytes still belongs to ``main``'s
    load segment, so its artifacts annotate against ``main``.
    """

    from .elf import Elf32File

    elf = Elf32File(root / "support" / "socom.elf")
    ranges = []
    for segment in elf.load_segments():
        opener = next(
            (section.name for section in elf.sections if section.flags & 0x2 and section.address == segment.virtual_address),
            None,
        )
        if opener:
            ranges.append((segment.virtual_address, segment.virtual_address + segment.memory_size, opener))

    def lookup(address: int) -> str | None:
        return next((name for low, high, name in ranges if low <= address < high), None)

    return lookup


def evidenced_paths(graph: dict[str, Any]) -> set[str]:
    """Every original path the graph's evidence quotes."""

    paths = {path for unit in graph["units"] for path in unit["paths"]}
    for row in graph["artifacts"]:
        for item in row["signals"]:
            if item.get("path"):
                paths.add(item["path"])
            paths.update(item.get("paths") or ())
            text = item.get("text")
            if isinstance(text, str) and ("\\" in text or "/" in text):
                paths.add(text)
    return paths


# -- workspace paths ------------------------------------------------------------


def _workspace_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.startswith("src/") or "\\" in value or ":" in value:
        return False
    parts = value.split("/")
    return all(part and part not in (".", "..") for part in parts)


def _path_state(root: Path, relative: str) -> tuple[str, str | None]:
    """("exact" | "case" | "missing", spelling on disk) of a repo-relative path.

    ``case`` means some component exists only in another letter case;
    ``missing`` means the first component that differs does not exist at all.
    """

    current = root
    parts = relative.split("/")
    for index, part in enumerate(parts):
        try:
            names = os.listdir(current)
        except (FileNotFoundError, NotADirectoryError):
            return "missing", None
        if part in names:
            current = current / part
            continue
        folded = sorted(name for name in names if name.casefold() == part.casefold())
        if folded:
            return "case", "/".join([*parts[:index], folded[0], *parts[index + 1 :]])
        return "missing", None
    return "exact", relative


# -- plans ------------------------------------------------------------------------


def _strings(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) and item.strip() for item in value)


def _shown(values: list[str]) -> str:
    head = ", ".join(values[:_SHOWN])
    return head + (f", +{len(values) - _SHOWN} more" if len(values) > _SHOWN else "")


def plan_item(tracker: dict[str, Any], item_id: Any) -> dict[str, Any]:
    item = next((row for row in tracker.get("work_items", []) if row.get("id") == item_id), None)
    if item is None or item.get("kind") not in SOURCE_PLAN_KINDS:
        raise SocomError(f"{item_id!r} is not a source-correlation plan item")
    return item


def scope_entry(graph: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    """The item's planning scope regenerated from ``graph``; refuses a stale graph."""

    batch = item.get("batch") or {}
    if problems := verify_graph(graph):
        raise SocomError("; ".join(problems))
    if graph["graph_sha256"] != batch.get("graph_sha256"):
        raise SocomError(
            f"stale graph: {item['id']} was decomposed from graph {batch.get('graph_sha256')}, "
            f"this graph is {graph['graph_sha256']}"
        )
    key = scope_key(batch.get("scope"))
    entry = next((row for row in planning_scopes(graph) if scope_key(row["scope"]) == key), None)
    if entry is None:
        raise SocomError(f"the graph has no planning scope {key}")
    if entry["slice_sha256"] != batch.get("slice_sha256"):
        raise SocomError(f"{item['id']}: the slice regenerated from the graph differs from the decomposed slice")
    return entry


def derive_annotations(
    plan: dict[str, Any], graph: dict[str, Any], section_of: Callable[[int], str | None]
) -> list[dict[str, Any]]:
    """The annotation targets the plan's owner and header-emit rows imply."""

    rows = {row["id"]: row for row in graph["artifacts"]}
    found: dict[tuple[str, str, str], dict[str, Any]] = {}

    def add(identity: Any, relation: str, path: Any) -> None:
        row = rows.get(identity) if isinstance(identity, str) else None
        if row is None or not named(row) or not isinstance(path, str):
            return
        found[(identity, relation, path)] = {
            "artifact": identity,
            "relation": relation,
            "section": section_of(int(row["address"], 16)),
            "path": path,
        }

    for owner in plan.get("owners") or []:
        if isinstance(owner, dict) and owner.get("classification") == "authored":
            for identity in owner.get("artifacts") or []:
                add(identity, "defines", owner.get("workspace_path"))
    for emit in plan.get("header_emits") or []:
        if isinstance(emit, dict):
            add(emit.get("artifact"), "emits", emit.get("header"))
    return sorted(found.values(), key=lambda row: (_address(row["artifact"]), row["relation"], row["path"]))


def _annotation_key(row: Any) -> tuple[Any, ...] | None:
    if not isinstance(row, dict) or set(row) != set(ANNOTATION_FIELDS):
        return None
    if not all(isinstance(row[field], str) for field in ANNOTATION_FIELDS):
        return None
    return tuple(row[field] for field in ANNOTATION_FIELDS)


def _check_reservation(
    root: Path, tracker: dict[str, Any], item: dict[str, Any], reservation: Any, problems: list[str]
) -> dict[str, Any] | None:
    """Check a plan's ``reservation`` row; the directories its owners must lie in.

    Only a segment plan has one: its apply item reserves ``src/``
    directories.  A plan confirms the reservation (the same directories) or
    corrects it (other directories, with a reason and evidence).  An
    inferred reservation must be confirmed or corrected.  Returns ``None``
    when the plan has no apply reservation to place owners in.
    """

    reserved = apply_reservation(tracker, item)
    if reserved is None:
        if reservation is not None:
            problems.append("only a segment plan records a reservation: provider and data plans write nothing under src/")
        return None
    apply_id = reserved["apply_item"]
    if reserved["missing"]:
        problems.append(f"{item['id']} has no {SEGMENT_APPLY_KIND} item {apply_id}")
        return None
    placement = {
        "apply_item": apply_id,
        "reserved": reserved["directories"],
        "inferred": reserved["inferred"],
        "status": None,
        "directories": reserved["directories"],
    }
    if reservation is None:
        if reserved["inferred"]:
            problems.append(
                f"{apply_id} reserves {_directories_text(reserved['directories'])} by inference "
                f"({reserved['reason']}): the plan must confirm or correct it in reservation"
            )
        return placement
    if not isinstance(reservation, dict) or set(reservation) != RESERVATION_FIELDS:
        problems.append(f"reservation must be {{{', '.join(sorted(RESERVATION_FIELDS))}}}")
        return placement
    status = reservation.get("status")
    directories = reservation.get("directories")
    if status == INFERRED_STATUS:
        problems.append("the reservation is still the decomposition's inference: confirm or correct it")
    elif status not in RESERVATION_STATUSES:
        problems.append(f"reservation status must be one of {list(RESERVATION_STATUSES)}")
    if not isinstance(reservation.get("reason"), str) or not reservation["reason"].strip():
        problems.append("the reservation needs a reason")
    if not _strings(reservation.get("evidence")) and status in RESERVATION_STATUSES:
        problems.append("the reservation needs evidence lines")
    if (
        not isinstance(directories, list)
        or not directories
        or not all(value == "src" or _workspace_path(value) for value in directories)
        or len(set(directories)) != len(directories)
    ):
        problems.append("reservation directories must be distinct src/ directories")
        return placement
    for directory in directories:
        state, actual = _path_state(root, directory)
        if state == "case":
            problems.append(f"reservation directory {directory} differs in letter case from {actual} on disk")
        elif state == "exact" and not (root / directory).is_dir():
            problems.append(f"reservation directory {directory} is a file")
    ordered = sorted(directories, key=str.casefold)
    placement["status"] = status
    if status == "confirmed" and ordered != reserved["directories"]:
        problems.append(
            f"a confirmed reservation must equal {apply_id}'s {_directories_text(reserved['directories'])}; "
            "record status corrected instead"
        )
    elif status == "corrected":
        if ordered == reserved["directories"]:
            problems.append(f"a corrected reservation must differ from {apply_id}'s; record status confirmed instead")
        placement["directories"] = ordered
    return placement


def validate_source_plan(
    root: Path,
    tracker: dict[str, Any],
    plan: Any,
    graph: dict[str, Any],
    *,
    section_of: Callable[[int], str | None] | None = None,
) -> dict[str, Any]:
    """Check one owner plan against its work item and the graph it cites."""

    problems: list[str] = []
    report: dict[str, Any] = {"problems": problems, "summary": {}, "review": []}

    def done() -> dict[str, Any]:
        report["ok"] = not problems
        return report

    if not isinstance(plan, dict):
        problems.append("the plan must be a JSON object")
        return done()
    if plan.get("kind") != SOURCE_PLAN_KIND or plan.get("schema_version") != SOURCE_PLAN_SCHEMA:
        problems.append(f"the plan is not a {SOURCE_PLAN_KIND} schema {SOURCE_PLAN_SCHEMA} document")
    if unknown := sorted(set(plan) - PLAN_FIELDS):
        problems.append(f"the plan has unknown fields {unknown}")
    if (plan.get("target") or {}).get("source_sha256") != REFERENCE_SHA256:
        problems.append("the plan's target is not the reference ELF")
    try:
        item = plan_item(tracker, plan.get("work_item_id"))
    except SocomError as failure:
        problems.append(str(failure))
        return done()
    batch = item.get("batch") or {}
    if plan.get("scope") != batch.get("scope"):
        problems.append(f"the plan's scope differs from {item['id']}'s {batch.get('scope')}")
    if plan.get("graph_sha256") != batch.get("graph_sha256"):
        problems.append(
            f"the plan cites graph {plan.get('graph_sha256')}, {item['id']} was decomposed from {batch.get('graph_sha256')}"
        )
    if plan.get("slice_sha256") != batch.get("slice_sha256"):
        problems.append(f"the plan cites slice {plan.get('slice_sha256')}, {item['id']}'s slice is {batch.get('slice_sha256')}")
    try:
        entry = scope_entry(graph, item)
    except SocomError as failure:
        problems.append(str(failure))
        return done()
    if problems:
        return done()
    if section_of is None:
        section_of = loaded_section_lookup(root)
    placement = _check_reservation(root, tracker, item, plan.get("reservation"), problems)
    if placement is not None:
        report["reservation"] = placement

    slice_ids = entry["artifacts"]
    in_slice = set(slice_ids)
    rows = {row["id"]: row for row in graph["artifacts"] if row["id"] in in_slice}
    gnu_objects = {row["address"]: row for row in graph["gnu_objects"]}
    known_paths = evidenced_paths(graph)
    holders: dict[str, list[str]] = defaultdict(list)
    owner_of: dict[str, dict[str, Any]] = {}
    units: dict[str, str] = {}
    workspaces: dict[str, str] = {}
    provisionals: dict[str, str] = {}
    members: dict[tuple[str, str], str] = {}
    cited_files: set[str] = set()

    owners = plan.get("owners")
    if not isinstance(owners, list):
        problems.append("owners must be a list")
        owners = []
    for number, owner in enumerate(owners, 1):
        if not isinstance(owner, dict):
            problems.append(f"owner {number} must be an object")
            continue
        label = f"owner {number} ({owner.get('translation_unit') or owner.get('library') or owner.get('classification')})"
        if unknown := sorted(set(owner) - OWNER_FIELDS):
            problems.append(f"{label} has unknown fields {unknown}")
        classification = owner.get("classification")
        if classification not in CLASSIFICATIONS:
            problems.append(f"{label} classification must be one of {list(CLASSIFICATIONS)}")
        if owner.get("confidence") not in CONFIDENCES:
            problems.append(f"{label} confidence must be one of {list(CONFIDENCES)}")
        if not _strings(owner.get("evidence")):
            problems.append(f"{label} needs evidence lines")
        artifacts = owner.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts or not all(isinstance(value, str) for value in artifacts):
            problems.append(f"{label} must list its artifacts")
            artifacts = [value for value in artifacts if isinstance(value, str)] if isinstance(artifacts, list) else []
        for identity in artifacts:
            holders[identity].append(label)
            owner_of.setdefault(identity, owner)

        unit = owner.get("translation_unit")
        workspace = owner.get("workspace_path")
        original = owner.get("original_path")
        provisional = owner.get("provisional_file")
        library = owner.get("library")
        member = owner.get("archive_member")
        if unit is not None and not (isinstance(unit, str) and _FILE_NAME.match(unit)):
            problems.append(f"{label} translation_unit must be a file name")
            unit = None
        if original is not None:
            if not isinstance(original, str) or original not in known_paths:
                problems.append(f"{label} original_path {original!r} is not quoted by the graph's evidence")
            elif unit and PureWindowsPath(original).name.casefold() != unit.casefold():
                problems.append(f"{label} original_path {original} names another unit than {unit}")
        if classification in ("authored", "compiler-generated") and unit:
            key = f"{classification}:{unit.casefold()}"
            if key in units:
                problems.append(f"{label} repeats {units[key]}: one owner row per translation unit")
            units.setdefault(key, label)
        if classification == "authored":
            if not unit or not unit.casefold().endswith(SOURCE_FILE_SUFFIXES):
                problems.append(f"{label} needs a source translation unit; headers only declare or emit")
            if library is not None or member is not None:
                problems.append(f"{label} is authored: library and archive_member must be null")
            if not _workspace_path(workspace):
                problems.append(f"{label} workspace_path must be a repo-relative path under src/")
            else:
                cited_files.add(workspace.casefold())
                if not workspace.casefold().endswith(SOURCE_FILE_SUFFIXES):
                    problems.append(f"{label} workspace_path {workspace} is not a source file; headers only declare or emit")
                if unit and PurePosixPath(workspace).name.casefold() != unit.casefold():
                    problems.append(f"{label} workspace_path {workspace} must keep the unit's file name {unit}")
                if workspace.casefold() in workspaces:
                    problems.append(f"{label} shares workspace_path {workspace} with {workspaces[workspace.casefold()]}")
                workspaces.setdefault(workspace.casefold(), label)
                state, actual = _path_state(root, workspace)
                if state == "case":
                    problems.append(f"{label} workspace_path {workspace} differs in letter case from {actual} on disk")
                elif state == "exact" and provisional != workspace:
                    problems.append(f"{label} workspace_path {workspace} exists: cite it as provisional_file")
            if provisional is not None:
                if not _workspace_path(provisional):
                    problems.append(f"{label} provisional_file must be a repo-relative path under src/")
                else:
                    cited_files.add(provisional.casefold())
                    state, actual = _path_state(root, provisional)
                    if state != "exact" or not (root / provisional).is_file():
                        problems.append(
                            f"{label} provisional_file {provisional} must name an existing file exactly"
                            + (f" (on disk: {actual})" if actual else "")
                        )
                    if not provisional.casefold().endswith(SOURCE_FILE_SUFFIXES):
                        problems.append(f"{label} provisional_file {provisional} is a header; headers cannot own")
                    if provisional in provisionals:
                        problems.append(f"{label} cites provisional_file {provisional} already cited by {provisionals[provisional]}")
                    provisionals.setdefault(provisional, label)
            if placement is not None:
                # The apply writes (and moves from) only the directories it reserves.
                checked = [("workspace_path", workspace)]
                if provisional != workspace:
                    checked.append(("provisional_file", provisional))
                for field, path in checked:
                    if _workspace_path(path) and not _within(path, placement["directories"]):
                        problems.append(
                            f"{label} {field} {path} lies outside the reservation of {placement['apply_item']} "
                            f"({_directories_text(placement['directories'])}): place it inside or record the "
                            "correction in reservation"
                        )
        elif classification == "provider":
            if not isinstance(library, str) or not library.strip():
                problems.append(f"{label} is a provider: it needs its library")
            if (
                not isinstance(member, dict)
                or set(member) - {"gnu_object", "object"}
                or not any(isinstance(member.get(key), str) and member.get(key) for key in ("gnu_object", "object"))
            ):
                problems.append(f"{label} is a provider: archive_member needs gnu_object and/or object")
            else:
                gnu = member.get("gnu_object")
                if gnu is not None and gnu not in gnu_objects:
                    problems.append(f"{label} archive_member gnu_object {gnu} is not a GNU object of the graph")
                # A GNU object is one archive member whatever library a row names.
                key = ("gnu", str(gnu)) if gnu is not None else (str(library).casefold(), str(member.get("object")).casefold())
                if key in members:
                    problems.append(f"{label} repeats {members[key]}: one owner row per archive member")
                members.setdefault(key, label)
            if workspace is not None or provisional is not None:
                problems.append(f"{label} is a provider without a source body: workspace_path and provisional_file must be null")
        elif classification == "compiler-generated":
            if any(owner.get(field) is not None for field in ("workspace_path", "provisional_file", "library", "archive_member", "original_path")):
                problems.append(
                    f"{label} is compiler-generated output no unit defines: it carries no path, library or archive member"
                )

    unresolved = plan.get("unresolved")
    if not isinstance(unresolved, list):
        problems.append("unresolved must be a list")
        unresolved = []
    for number, row in enumerate(unresolved, 1):
        if not isinstance(row, dict) or set(row) != {"artifact", "reason"} or not isinstance(row.get("artifact"), str):
            problems.append(f"unresolved row {number} must be {{artifact, reason}}")
            continue
        reason = row.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"unresolved {row['artifact']} needs a reason")
        elif reason.strip() == SKELETON_REASON:
            problems.append(f"unresolved {row['artifact']} still has the skeleton reason {SKELETON_REASON!r}")
        holders[row["artifact"]].append("unresolved")

    outside = sorted(identity for identity in holders if identity not in in_slice)
    if outside:
        problems.append(f"{len(outside)} listed artifacts are outside the scope's slice: {_shown(outside)}")
    repeated = [identity for identity in slice_ids if len(holders.get(identity, ())) > 1]
    for identity in repeated[:_SHOWN]:
        problems.append(f"{identity} is listed {len(holders[identity])} times ({', '.join(holders[identity])})")
    if len(repeated) > _SHOWN:
        problems.append(f"{len(repeated) - _SHOWN} more artifacts are listed more than once")
    missing = [identity for identity in slice_ids if identity not in holders]
    if missing:
        problems.append(f"{len(missing)} slice artifacts are neither owned nor unresolved: {_shown(missing)}")

    # A GNU object's functions belong to the archive-member row naming it.
    review: list[str] = report["review"]
    for identity in slice_ids:
        gnu = rows[identity].get("gnu_object")
        owner = owner_of.get(identity)
        if gnu is None or owner is None or len(holders[identity]) > 1:
            continue
        if owner.get("classification") == "provider" and (owner.get("archive_member") or {}).get("gnu_object") == gnu:
            continue
        message = f"{identity} belongs to GNU object {gnu}: its owner must be the provider row of that archive member"
        if "uncertain" in str(gnu_objects.get(gnu, {}).get("end_basis")):
            review.append(message + " (the object's end is uncertain)")
        else:
            problems.append(message)

    header_emits = plan.get("header_emits")
    if not isinstance(header_emits, list):
        problems.append("header_emits must be a list")
        header_emits = []
    emitted: set[str] = set()
    for number, emit in enumerate(header_emits, 1):
        if (
            not isinstance(emit, dict)
            or set(emit) != {"artifact", "header", "reason", "evidence"}
            or not all(isinstance(emit[key], str) for key in ("artifact", "header", "reason"))
        ):
            problems.append(f"header_emits row {number} must be {{artifact, header, reason, evidence}} with string values")
            continue
        identity, header, reason = emit["artifact"], emit["header"], emit["reason"]
        label = f"header_emits {identity}"
        owner = owner_of.get(identity) if isinstance(identity, str) else None
        if owner is None or owner.get("classification") != "authored":
            problems.append(f"{label}: an emitted artifact must be owned by an authored unit of this plan")
        if identity in emitted:
            problems.append(f"{label} is listed twice")
        emitted.add(identity)
        if not _workspace_path(header) or not header.casefold().endswith(HEADER_SUFFIXES):
            problems.append(f"{label}: header must be a repo-relative header path under src/")
        else:
            cited_files.add(header.casefold())
            state, actual = _path_state(root, header)
            if state == "case":
                problems.append(f"{label}: header {header} differs in letter case from {actual} on disk")
        if reason not in EMIT_REASONS:
            problems.append(f"{label}: reason must be one of {list(EMIT_REASONS)}")
        elif isinstance(identity, str) and identity in rows:
            names = rows[identity].get("names") or []
            bindings = {row.get("binding") for row in names} | {rows[identity].get("binding")}
            if reason == "weak" and "WEAK" not in bindings:
                problems.append(f"{label}: a weak instance needs WEAK binding")
            if reason == "inline" and not bindings & {"13", "WEAK"}:
                problems.append(f"{label}: an inline instance needs Metrowerks binding 13 or WEAK")
            if reason == "template" and not any("<" in str(row.get("name")) for row in names):
                problems.append(f"{label}: a template instance needs template arguments in its name")
        if not _strings(emit.get("evidence")):
            problems.append(f"{label} needs evidence lines")

    retire = plan.get("retire_files", [])
    if not isinstance(retire, list):
        problems.append("retire_files must be a list")
        retire = []
    retired: set[str] = set()
    for number, row in enumerate(retire, 1):
        if not isinstance(row, dict) or set(row) != {"path", "reason", "evidence"} or not isinstance(row["path"], str):
            problems.append(f"retire_files row {number} must be {{path, reason, evidence}}")
            continue
        path = row["path"]
        if not _workspace_path(path) or _path_state(root, path)[0] != "exact" or not (root / path).is_file():
            problems.append(f"retire_files {path!r} must name an existing file under src/ exactly")
        elif path.casefold() in cited_files:
            problems.append(f"retire_files {path} is cited by an owner or header-emit row")
        if path in retired:
            problems.append(f"retire_files {path} is listed twice")
        retired.add(path)
        if not isinstance(row.get("reason"), str) or not row["reason"].strip() or not _strings(row.get("evidence")):
            problems.append(f"retire_files {path} needs a reason and evidence lines")

    if not isinstance(plan.get("notes", []), list) or not all(isinstance(value, str) for value in plan.get("notes", [])):
        problems.append("notes must be a list of strings")

    expected = derive_annotations(plan, graph, section_of)
    for row in expected:
        if row["section"] is None:
            problems.append(f"{row['artifact']} lies in no loaded section")
    listed = plan.get("annotations")
    if not isinstance(listed, list):
        problems.append("annotations must be a list")
        listed = []
    keys = [_annotation_key(row) for row in listed]
    if None in keys:
        problems.append(f"every annotation must be exactly {{{', '.join(ANNOTATION_FIELDS)}}}")
    listed_keys = Counter(key for key in keys if key is not None)
    wanted = {_annotation_key(row) for row in expected}
    absent = sorted(f"{key[1]} {key[0]} in {key[3]}" for key in wanted - set(listed_keys))
    extra = sorted(f"{key[1]} {key[0]} in {key[3]}" for key in set(listed_keys) - wanted)
    if absent:
        problems.append(f"{len(absent)} annotation targets the owner rows imply are not listed: {_shown(absent)}")
    if extra:
        problems.append(f"{len(extra)} listed annotations no owner row implies: {_shown(extra)}")
    if any(count > 1 for count in listed_keys.values()):
        problems.append("annotations repeat a target")

    # Disagreements with the graph's candidates are for the reviewer.
    disagreements = []
    for identity, owner in owner_of.items():
        row = rows.get(identity)
        if row is None:
            continue
        candidate = row["classification"]["candidate"]
        if candidate in ("authored", "provider") and owner.get("classification") in ("authored", "provider"):
            if candidate != owner["classification"] or (
                candidate == "provider" and row["classification"]["library"] != owner.get("library")
            ):
                disagreements.append(identity)
    if disagreements:
        review.append(
            f"{len(disagreements)} owned artifacts differ from the graph's classification candidate: "
            + _shown(sorted(disagreements, key=_address))
        )
    report["summary"] = {
        "slice_artifacts": len(slice_ids),
        "owned": sum(1 for identity in slice_ids if identity in owner_of),
        "unresolved": len(unresolved),
        "owners": dict(sorted(Counter(str(owner.get("classification")) for owner in owners if isinstance(owner, dict)).items())),
        "annotations": dict(sorted(Counter(row["relation"] for row in expected).items())),
        "header_emits": len(header_emits),
        "retire_files": len(retire),
    }
    return done()


# -- evidence and skeleton ------------------------------------------------------


def _compact(row: dict[str, Any], section_of: Callable[[int], str | None]) -> dict[str, Any]:
    section = row.get("input_section") or {}
    out: dict[str, Any] = {
        "id": row["id"],
        "kind": row["kind"],
        "address": row["address"],
        "end": row["end"],
        "size": row["size"],
        "section": section_of(int(row["address"], 16)),
        "input_section": section.get("name") or "..".join(str(value) for value in section.get("between") or []),
        "named": named(row),
        "classification": {key: row["classification"].get(key) for key in ("candidate", "library", "weak") if key in row["classification"]},
        "tu_candidates": [{key: candidate[key] for key in ("tu", "strength", "via")} for candidate in row["tu_candidates"]],
    }
    if row["kind"] == "gap":
        out.update(fill=row.get("fill"), padding=row.get("padding"), labels=row.get("labels"))
    else:
        out["binding"] = row.get("binding")
        out["names"] = [{"name": item["name"], "binding": item.get("binding")} for item in row.get("names") or []]
    for key in ("cluster", "gnu_object", "emitted_from_header"):
        if row.get(key):
            out[key] = row[key]
    paths = sorted({item["path"] for item in row["signals"] if item.get("path")})
    if paths:
        out["paths"] = paths
    return out


def plan_evidence(
    root: Path,
    tracker: dict[str, Any],
    item_id: str,
    graph: dict[str, Any],
    *,
    section_of: Callable[[int], str | None] | None = None,
) -> dict[str, Any]:
    """The slice of one plan item with the graph evidence a planner needs."""

    item = plan_item(tracker, item_id)
    entry = scope_entry(graph, item)
    if section_of is None:
        section_of = loaded_section_lookup(root)
    wanted = set(entry["artifacts"])
    rows = [row for row in graph["artifacts"] if row["id"] in wanted]
    units = {candidate["tu"].casefold() for row in rows for candidate in row["tu_candidates"]}
    provisional = []
    source = root / "src"
    if source.is_dir():
        provisional = sorted(
            (
                {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size}
                for path in source.rglob("*")
                if path.is_file() and path.name.casefold() in units
            ),
            key=lambda row: row["path"].casefold(),
        )
    functions = {row["id"] for row in rows if row["kind"] == "function"}
    evidence = {
        "kind": SOURCE_EVIDENCE_KIND,
        "schema_version": 1,
        "work_item_id": item["id"],
        "scope": item["batch"]["scope"],
        "graph_sha256": graph["graph_sha256"],
        "slice_sha256": entry["slice_sha256"],
        "artifact_count": len(rows),
        "segments": [
            {key: segment[key] for key in ("id", "segment_number", "start", "end", "function_count", "classification_mix", "tu_candidates", "boundary")}
            for segment in entry["segments"]
        ],
        "units": [unit for unit in graph["units"] if unit["tu"].casefold() in units],
        "gnu_objects": [row for row in graph["gnu_objects"] if functions & set(row["functions"])],
        "provisional_files": provisional,
        "artifacts": [_compact(row, section_of) for row in rows],
    }
    reservation = apply_reservation(tracker, item)
    if reservation is not None:
        evidence["reservation"] = {key: reservation[key] for key in ("apply_item", "directories", "inferred", "reason")}
    return evidence


def plan_skeleton(tracker: dict[str, Any], item_id: str, graph: dict[str, Any]) -> dict[str, Any]:
    """A plan that lists every slice artifact unresolved, for the planner to fill."""

    item = plan_item(tracker, item_id)
    entry = scope_entry(graph, item)
    skeleton = {
        "kind": SOURCE_PLAN_KIND,
        "schema_version": SOURCE_PLAN_SCHEMA,
        "work_item_id": item["id"],
        "scope": item["batch"]["scope"],
        "graph_sha256": graph["graph_sha256"],
        "slice_sha256": entry["slice_sha256"],
        "target": {"source_sha256": REFERENCE_SHA256},
        "owners": [],
        "header_emits": [],
        "annotations": [],
        "unresolved": [{"artifact": identity, "reason": SKELETON_REASON} for identity in entry["artifacts"]],
        "retire_files": [],
        "notes": [],
    }
    reservation = apply_reservation(tracker, item)
    if reservation is not None and reservation["inferred"]:
        # The planner confirms or corrects the inference; validation refuses it as is.
        skeleton["reservation"] = {
            "directories": list(reservation["directories"]),
            "status": INFERRED_STATUS,
            "reason": reservation["reason"],
            "evidence": [],
        }
    return skeleton
