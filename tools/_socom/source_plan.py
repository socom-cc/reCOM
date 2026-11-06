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

An artifact the graph proves provider code of another library
(``strong_provider``) moves to that library's scope wherever it lies: crt0's
unsymbolled object gets a scope of its own, MSL takes its units' static
initializers.

A ``socom-source-owner-plan`` (schema 2; schema 1 plans stay valid) owns every artifact of one scope
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
from .source_graph import SOURCE_GRAPH_KIND, SOURCE_GRAPH_SCHEMA, TU_LIBRARY, path_library
from .source_placements import DECISION_CONFIDENCES, DecisionCheck
from .util import SocomError, canonical_json, load_json

SOURCE_STAGE = "source-correlation"
SOURCE_SEED_ID = "socom:work:source-correlation-seed"
SOURCE_APPLY_ROUTE_ID = "socom:work:source-correlation-apply-route"
SOURCE_PLAN_RESOURCES = ["build/source-plans"]
SOURCE_PLAN_KIND = "socom-source-owner-plan"
# Schema 2 adds per-artifact confidence, draft markers, linked objects and
# provider-header emits; schema 1 plans stay valid as written.
SOURCE_PLAN_SCHEMA = 2
SOURCE_PLAN_SCHEMAS = (1, 2)
SOURCE_EVIDENCE_KIND = "socom-source-plan-evidence"
DRAFT_OPEN = "open"

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
# Schema 2 only: the draft block (``source plan draft``) and the structured
# contradictions with existing provisional source.
PLAN_FIELDS_V2 = PLAN_FIELDS | {"draft", "contradictions"}
# One contradiction the ELF decides against a provisional source file: the
# artifact (in the plan's slice), the file and line that disagree, a kind
# slug and the ELF evidence lines.  ``line`` may be null for a file-level
# contradiction.
CONTRADICTION_FIELDS = ("artifact", "provisional_file", "line", "kind", "elf_evidence")
_CONTRADICTION_KIND = re.compile(r"^[a-z][a-z0-9-]*$")
# Notes that record a contradiction as text (plans written before the field).
CONTRADICTION_NOTE = "contradiction:"
# U+0000-U+001F: no plan string may hold one (a Windows path whose ``\a``
# went through a string escape holds BEL instead).
_CONTROL = re.compile(r"[\x00-\x1f]")
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
# Schema 2 only: the rule that fixed the row's identity and paths, the
# draft's "open" marker on a row whose paths the planner must still decide,
# ``name_basis``: where an authored row's unit name comes from, and the
# user ``decision`` a ``name_basis: "user"`` row cites.
OWNER_FIELDS_V2 = OWNER_FIELDS | {"draft_rule", "draft", "name_basis", "decision"}
# ``evidence`` (the default): the ELF names the unit (DWARF, __FILE__, sinit,
# a unit candidate).  For an authored object the ELF does not name (its
# cluster has no unit; user decision of 2026-10-31): ``provisional``, the one
# existing provisional file of the module that defines its functions
# (confidence at most medium), or ``invented``, a descriptive name from its
# main class (confidence low).  ``user``: a file the user named in a recorded
# decision (``decision`` {file, sha256, heading}; source_placements), at most
# medium: the user's knowledge is decision evidence, below the binary's.
NAME_BASIS_DEFAULT = "evidence"
NAME_BASIS_USER = "user"
NAME_BASES = (NAME_BASIS_DEFAULT, "provisional", "invented", NAME_BASIS_USER)
# An entry's ``decision`` cites the user's placement of that one artifact.
ARTIFACT_ENTRY_FIELDS = frozenset({"artifact", "confidence", "basis", "draft_rule", "decision"})
MEMBER_FIELDS = frozenset({"gnu_object", "object"})
# Schema 2 only: ``linked``, and the archive the member came from by file
# name (``archive``, e.g. ``liblgaud.a``, never a path) and its ``version``
# (e.g. ``1.06``) when the ELF evidences them.
MEMBER_FIELDS_V2 = MEMBER_FIELDS | {"linked", "archive", "version"}
# How a provider member reached the link: from an archive (the default when
# ``linked`` is absent), as an object file of toolchain or SDK source compiled
# with the project (crt0.s, PS2 Support gcc_wrapper.c), or ``unknown`` when
# the evidence does not say (so the archive default is not a claim).
LINKED_KINDS = ("archive", "object", "unknown")
EMIT_FIELDS = frozenset({"artifact", "header", "reason", "evidence"})
# Schema 2 only: ``library`` marks a provider header (``<string>``) whose
# template or inline body the owner's file emits by inclusion.
EMIT_FIELDS_V2 = EMIT_FIELDS | {"library", "draft_rule"}
# Schema 2: an open row may carry the drafter's ``suggest``ion, which
# ``source plan decide --accept-suggestion`` records as a hand entry.
UNRESOLVED_FIELDS_V2 = frozenset({"artifact", "reason", "draft", "suggest"})
SUGGEST_FIELDS = ("owner", "rule", "confidence", "basis")
# Plan items whose plans a unit's paths must agree with (another plan's
# accepted row is a problem, a handed-off one a review note).
CROSS_PLAN_STATUSES = ("awaiting_acceptance", "accepted")
CROSS_PLAN_FIELDS = ("classification", "workspace_path", "original_path")
_PROVIDER_HEADER = re.compile(r"^<[A-Za-z0-9_.+/-]+>$")
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


def provider_units(graph: dict[str, Any]) -> dict[str, str]:
    """Casefolded unit name -> provider library, for units a provider path or name proves."""

    found: dict[str, set[str]] = defaultdict(set)
    for unit in graph.get("units") or []:
        key = str(unit.get("tu", "")).casefold()
        if key in TU_LIBRARY:
            found[key].add(TU_LIBRARY[key])
        for path in unit.get("paths") or []:
            verdict = path_library(path)
            if verdict and verdict[0] == "provider" and verdict[1]:
                found[key].add(verdict[1])
    return {key: next(iter(libraries)) for key, libraries in found.items() if len(libraries) == 1}


def strong_provider(row: dict[str, Any], unit_library: dict[str, str]) -> str | None:
    """The provider library the graph proves for an artifact, or ``None``.

    A non-weak provider classification, or, for a compiler-generated or
    unclassified artifact, a strong primary unit candidate that is a
    provider unit (``provider_units``).
    """

    classification = row.get("classification") or {}
    if classification.get("candidate") == "provider" and not classification.get("weak"):
        return classification.get("library")
    if classification.get("candidate") in ("compiler-generated", "unknown"):
        candidates = row.get("tu_candidates") or []
        if candidates and candidates[0].get("strength") == "strong":
            return unit_library.get(str(candidates[0].get("tu")).casefold())
    return None


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

    def provider_entry(library: str) -> dict[str, Any]:
        entry = providers.get(library)
        if entry is None:
            entry = providers[library] = {
                "scope": {"kind": "provider", "library": library},
                "segments": [],
                "artifacts": [],
                "moved_from": [],
            }
            entries.append(entry)
        return entry

    unit_library = provider_units(graph)
    for segment, ids in zip(segments, slices):
        family, library = segment_family(segment)
        if family == "provider":
            assert library is not None
            entry = provider_entry(library)
            entry["segments"].append(segment)
        else:
            entry = {
                "scope": {"kind": "segment", "segment_id": segment["id"], "segment_number": segment["segment_number"]},
                "segments": [segment],
                "artifacts": [],
            }
            entries.append(entry)
        # An artifact the graph proves provider code of another library
        # (crt0's unsymbolled object, a provider unit's static initializer
        # in the authored __sinit window) is planned by that library's item.
        here = library if family == "provider" else None
        for identity in ids:
            other = strong_provider(rows[position[identity]], unit_library)
            if other is None or other == here:
                entry["artifacts"].append(identity)
                continue
            target = provider_entry(other)
            target["artifacts"].append(identity)
            if segment["segment_number"] not in target["moved_from"]:
                target["moved_from"].append(segment["segment_number"])
    # Address order of their first artifact (a scope made only of moved
    # artifacts takes its place among the others).
    entries.sort(key=lambda entry: min((position[identity] for identity in entry["artifacts"]), default=len(rows)))
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
            moved = sorted(entry.get("moved_from") or [])
            batch.update(
                batch_number=segments[0]["segment_number"] if segments else moved[0],
                segment_numbers=[segment["segment_number"] for segment in segments],
                ranges=[[segment["start"], segment["end"]] for segment in segments],
                classification_mix=dict(sorted(mix.items())),
            )
            if moved:
                # Artifacts of this library the graph proves inside other segments.
                batch["moved_from_segments"] = moved
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

    def unit_places(unit: str) -> tuple[set[str], bool]:
        """(directories, whether an original ELF path gives them)."""

        modules = [module for module in map(original_module, paths.get(unit.casefold(), [])) if module]
        if modules:
            return {directories.get(module.casefold(), module) for module in modules}, True
        return set(by_basename.get(unit.casefold(), ())), False

    def unit_directories(unit: str) -> set[str]:
        return unit_places(unit)[0]

    segments = graph["segments"]
    evidenced: dict[str, list[str]] = {}
    by_name: dict[str, tuple[list[str], list[str]]] = {}
    for segment in segments:
        if segment_family(segment)[0] == "authored":
            found: set[str] = set()
            from_paths: set[str] = set()
            clauses: list[str] = []
            for candidate in segment["tu_candidates"]:
                places, from_path = unit_places(candidate["tu"])
                found.update(places)
                if from_path:
                    from_paths.update(places)
                elif places:
                    clauses.append(
                        f"{candidate['tu']} has no original ELF path; only a provisional file of that name lies in "
                        f"{_directories_text(sorted(places, key=str.casefold))}"
                    )
            evidenced[segment["id"]] = sorted(found, key=str.casefold)
            if found - from_paths:
                by_name[segment["id"]] = (sorted(found - from_paths, key=str.casefold), clauses)

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
        if found and segment["id"] in by_name:
            # A directory that rests only on a provisional file's name is an
            # inference the plan must confirm (user decision of 2026-10-31).
            _named, clauses = by_name[segment["id"]]
            result[scope_key(scope)] = {
                "directories": found,
                "inferred": True,
                "basis": "provisional-name",
                "reason": "inferred by name: " + "; ".join(clauses),
            }
            continue
        if found:
            result[scope_key(scope)] = {"directories": found, "inferred": False, "basis": "path", "reason": None}
            continue
        inferred, reason = infer(segment) if segment["tu_candidates"] else ([], "the segment has no unit candidates")
        if inferred:
            result[scope_key(scope)] = {"directories": inferred, "inferred": True, "basis": "neighbour-prefix", "reason": reason}
        else:
            result[scope_key(scope)] = {
                "directories": ["src"],
                "inferred": False,
                "basis": "fallback",
                "reason": f"fallback to all of src: {reason}",
            }
    return result


def plan_path(item_id: str) -> str:
    """The repo-relative path of a plan item's owner plan (its packet's path)."""

    return f"build/source-plans/{str(item_id).removesuffix('-apply').replace(':', '-')}.json"


def decomposed_directories(apply: dict[str, Any]) -> list[str]:
    """The ``src/`` directories an apply item was decomposed with.

    ``progress apply-source-plan`` re-reserves a plan's corrected directories
    on the item (``resources`` and ``batch.directories``) and keeps the
    decomposed ones in ``batch.reservation_correction.from``.
    """

    correction = (apply.get("batch") or {}).get("reservation_correction")
    if isinstance(correction, dict) and isinstance(correction.get("from"), list):
        return list(correction["from"])
    return list(apply.get("resources") or [])


def apply_reservation(tracker: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
    """The decomposed reservation of a segment plan item's apply item, or ``None``."""

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
        "directories": sorted(decomposed_directories(apply), key=str.casefold),
        "inferred": batch.get("resource_inferred") is True,
        "reason": batch.get("resource_reason"),
    }


def within(path: str, directories: list[str]) -> bool:
    """Whether a repo-relative path lies inside one of ``directories``."""

    return _within(path, directories)


def _within(path: str, directories: list[str]) -> bool:
    return any(path.startswith(f"{directory}/") for directory in directories)


# -- artifacts ------------------------------------------------------------------


def named(row: dict[str, Any]) -> bool:
    """A function or data artifact with a name the compiler did not invent."""

    return row.get("kind") != "gap" and any(
        item.get("name") and not _COMPILER_NAME.match(item["name"]) for item in row.get("names") or []
    )


def artifact_id(entry: Any) -> str | None:
    """The artifact ID of an owner row's ``artifacts`` entry (a string, or a schema 2 object)."""

    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and isinstance(entry.get("artifact"), str):
        return entry["artifact"]
    return None


def artifact_ids(owner: dict[str, Any]) -> list[str]:
    """The artifact IDs an owner row lists, in order; consumers of plans read entries through this."""

    entries = owner.get("artifacts") if isinstance(owner, dict) else None
    return [value for value in map(artifact_id, entries if isinstance(entries, list) else []) if value is not None]


def owned_files(plan: Any) -> set[str]:
    """The source files the plan's authored rows own: each row's ``provisional_file`` and ``workspace_path``.

    A contradiction about an artifact outside the plan's slice is allowed
    only in one of these files (the plan owns what that file defines).
    """

    found: set[str] = set()
    for row in (plan.get("owners") if isinstance(plan, dict) else None) or []:
        if isinstance(row, dict) and row.get("classification") == "authored":
            found.update(row[field] for field in ("provisional_file", "workspace_path") if isinstance(row.get(field), str))
    return found


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


def control_characters(value: Any, path: str = "$") -> list[str]:
    """Every string of a JSON value (keys included) holding a U+0000-U+001F character, by JSON path."""

    found: list[str] = []

    def text(string: str) -> str:
        codes = ", ".join(sorted({f"U+{ord(char):04X}" for char in _CONTROL.findall(string)}))
        shown = string if len(string) <= 80 else string[:77] + "..."
        return f"{codes} in {shown!r}"

    if isinstance(value, str):
        if _CONTROL.search(value):
            found.append(f"{path}: {text(value)}")
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and _CONTROL.search(key):
                found.append(f"{path} key: {text(key)}")
            found.extend(control_characters(item, f"{path}.{key}" if _FILE_NAME.match(str(key)) else f"{path}[{str(key)!r}]"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(control_characters(item, f"{path}[{index}]"))
    return found


def _overlaps(first: str, second: str) -> bool:
    first, second = first.casefold(), second.casefold()
    return first == second or first.startswith(f"{second}/") or second.startswith(f"{first}/")


def reservation_sharing(tracker: dict[str, Any], apply_id: str, directories: list[str]) -> dict[str, list[str]]:
    """For each directory, the other segment applies whose ``src/`` reservation overlaps it.

    Applies that reserve one directory (or one inside the other) write the
    same files' directories, so the coordinator runs them one at a time.
    Each apply's current ``resources`` are read (a corrected plan
    re-reserves them when it is applied).
    """

    others = [
        (row["id"], [value for value in row.get("resources") or [] if isinstance(value, str)])
        for row in tracker.get("work_items", [])
        if row.get("kind") == SEGMENT_APPLY_KIND and row.get("id") != apply_id
    ]
    return {
        directory: sorted(item for item, resources in others if any(_overlaps(directory, value) for value in resources))
        for directory in directories
    }


def _shown(values: list[str]) -> str:
    head = ", ".join(values[:_SHOWN])
    return head + (f", +{len(values) - _SHOWN} more" if len(values) > _SHOWN else "")


def plan_item(tracker: dict[str, Any], item_id: Any) -> dict[str, Any]:
    item = next((row for row in tracker.get("work_items", []) if row.get("id") == item_id), None)
    if item is None or item.get("kind") not in SOURCE_PLAN_KINDS:
        raise SocomError(f"{item_id!r} is not a source-correlation plan item")
    return item


def plan_graph_digests(batch: dict[str, Any]) -> set[Any]:
    """The graph digests a plan of this batch may cite.

    The batch's own ``graph_sha256``, and for an item whose plan was
    accepted before a graph refresh that left its slice byte-identical, the
    earlier digest that plan cites (``plan_graph_sha256``).
    """

    digests = {batch.get("graph_sha256")}
    if isinstance(batch.get("plan_graph_sha256"), str):
        digests.add(batch["plan_graph_sha256"])
    return digests


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
    """The annotation targets the plan's owner and header-emit rows imply.

    A named artifact of an authored row is defined in the row's workspace
    file, and a header-emit row adds an ``emits`` edge in its header.  A
    provider-header row (schema 2: ``library`` set, header ``<name>``) has
    no workspace header: the owner's file emits the instance by including
    the provider header, so its ``defines`` edge becomes ``emits``.
    """

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

    included = {
        emit.get("artifact")
        for emit in plan.get("header_emits") or []
        if isinstance(emit, dict) and emit.get("library") is not None
    }
    for owner in plan.get("owners") or []:
        if isinstance(owner, dict) and owner.get("classification") == "authored":
            for identity in artifact_ids(owner):
                add(identity, "emits" if identity in included else "defines", owner.get("workspace_path"))
    for emit in plan.get("header_emits") or []:
        if isinstance(emit, dict) and emit.get("library") is None:
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


def suggestion_problems(suggest: Any) -> list[str]:
    """What is wrong with an open row's ``suggest`` object ``{owner, rule, confidence, basis}``."""

    if not isinstance(suggest, dict):
        return [f"must be an object {{{', '.join(SUGGEST_FIELDS)}}}"]
    found = []
    if unknown := sorted(set(suggest) - set(SUGGEST_FIELDS)):
        found.append(f"has unknown fields {unknown}")
    for key in ("owner", "rule", "basis"):
        if not isinstance(suggest.get(key), str) or not suggest[key].strip():
            found.append(f"needs {key}")
    if suggest.get("confidence") not in CONFIDENCES:
        found.append(f"confidence must be one of {list(CONFIDENCES)}")
    return found


def _cluster_names(cluster: dict[str, Any]) -> list[str]:
    """The unit and library names a graph cluster carries."""

    units = [str(value.get("tu")) if isinstance(value, dict) else str(value) for value in cluster.get("units") or []]
    return sorted(units) + sorted(str(value) for value in cluster.get("libraries") or [])


def _decision_destination(block: dict[str, Any], unit: str | None, workspace: Any) -> str | None:
    """Why a cited decision heading does not place its artifacts in this row's unit file, or ``None``."""

    destination = block["destination"]
    path = destination["path"]
    if not destination["source"]:
        return f"names {path}, not a source file"
    if not unit or PurePosixPath(path).name.casefold() != unit.casefold():
        return f"places its artifacts in {path}, not unit {unit}"
    if isinstance(workspace, str) and workspace.casefold() != path.casefold():
        return f"places its artifacts in {path}, not workspace_path {workspace}"
    return None


def _check_entry_decisions(
    owner: dict[str, Any],
    label: str,
    classification: Any,
    unit: str | None,
    entries: list[Any],
    header_emits: list[Any],
    decisions: DecisionCheck,
    problems: list[str],
) -> set[str]:
    """Check each artifact entry's ``decision`` (schema 2) and return the artifacts whose entries cite one.

    The entry cites a heading of a user decision file (as a ``name_basis:
    "user"`` row does) that lists its artifact; it has its confidence (at most
    medium) and basis.  The heading is the row's unit file, or a header the
    plan's header-emit row emits the artifact into (an inline or template
    copy the compiler emitted in this file).
    """

    decided: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or "decision" not in entry:
            continue
        identity = artifact_id(entry)
        if identity is None:
            continue
        decided.add(identity)
        where = f"{label} entry {identity}"
        if classification != "authored":
            problems.append(f"{where} cites a decision: only an authored row's entries cite one")
            continue
        if "confidence" not in entry or "basis" not in entry:
            problems.append(f"{where} cites a decision: it needs its confidence and basis")
        elif entry["confidence"] not in DECISION_CONFIDENCES:
            problems.append(f"{where} rests on a user decision: its confidence is at most medium")
        block = decisions.heading(entry["decision"], where, problems)
        if block is None:
            continue
        if identity not in block["listed"]:
            problems.append(decisions.not_listed(block, where, identity))
        destination = block["destination"]
        if destination["header"]:
            emitted = {
                str(row.get("header")).casefold()
                for row in header_emits
                if isinstance(row, dict) and row.get("artifact") == identity
            }
            if destination["path"].casefold() not in emitted:
                problems.append(
                    f"{where} cites header heading {block['heading']!r}: a header-emit row must emit it into {destination['path']}"
                )
        elif why := _decision_destination(block, unit, owner.get("workspace_path")):
            problems.append(f"{where} decision heading {block['heading']!r} {why}")
    return decided


def _check_name_basis(
    owner: dict[str, Any],
    label: str,
    classification: Any,
    unit: str | None,
    artifacts: list[str],
    entries: list[Any],
    graph_units: set[str],
    clusters: dict[str, dict[str, Any]],
    rows: dict[str, dict[str, Any]],
    v2: bool,
    header_emits: list[Any],
    decisions: DecisionCheck,
    problems: list[str],
    review: list[str],
) -> None:
    """Check where an owner row's unit name comes from (``name_basis``, schema 2).

    ``evidence`` (the default): an authored row names a unit the graph knows
    (a schema 2 plan that names another records the name's basis; a schema 1
    plan gets a review note).  ``provisional``, ``invented`` and ``user`` name
    an authored object the ELF does not name: the name is no unit the graph
    knows, and the row's artifacts lie in no cluster that names a unit or
    library and have no strong or medium unit candidate (the ELF outranks a
    name).  An object with no LOCAL cluster of its own (or whose clusters
    lie outside the slice, such as its RTTI in ``.rodata``) is allowed: when
    none of the row's artifacts lies in a cluster, a review note says so.
    ``invented`` is confidence low; ``provisional`` cites the provisional
    file it is named after and is at most medium; ``user`` cites the
    heading of a user decision file that names its unit file and lists its
    artifacts (``decision``; an artifact whose entry cites its own decision
    is checked there) and is at most medium.  Any entry may cite a decision
    (``_check_entry_decisions``).  Paths, reservation and annotations are
    checked as for any authored row.
    """

    decided = _check_entry_decisions(owner, label, classification, unit, entries, header_emits, decisions, problems)
    basis = owner.get("name_basis", NAME_BASIS_DEFAULT)
    if basis not in NAME_BASES:
        problems.append(f"{label} name_basis must be one of {list(NAME_BASES)}")
        return
    if "decision" in owner and basis != NAME_BASIS_USER:
        problems.append(f"{label} records a decision with name_basis {basis}: a row cites one only with name_basis user")
    if basis == NAME_BASIS_DEFAULT:
        if classification == "authored" and unit and unit.casefold() not in graph_units:
            message = (
                f"{label} names unit {unit}, which the graph does not know: record name_basis provisional, invented or user"
            )
            (problems if v2 else review).append(message)
        return
    if classification != "authored":
        problems.append(f"{label} name_basis {basis}: only an authored row names an object the ELF does not name")
        return
    if not unit:
        return  # refused above: an authored row names a source unit
    if unit.casefold() in graph_units:
        problems.append(f"{label} name_basis {basis} reuses unit {unit}, which the graph knows: its row has name_basis evidence")
    confidence = owner.get("confidence")
    if basis == "invented":
        if confidence != "low":
            problems.append(f"{label} has an invented name: its confidence must be low")
    elif basis == NAME_BASIS_USER:
        if confidence not in DECISION_CONFIDENCES:
            problems.append(f"{label} is named by a user decision: its confidence is at most medium")
        if "decision" not in owner:
            problems.append(f"{label} name_basis user cites the user's decision: it needs decision {{file, sha256, heading}}")
        elif (block := decisions.heading(owner["decision"], label, problems)) is not None:
            if why := _decision_destination(block, unit, owner.get("workspace_path")):
                problems.append(f"{label} decision heading {block['heading']!r} {why}")
            for identity in artifacts:
                if identity not in decided and identity not in block["listed"]:
                    problems.append(decisions.not_listed(block, label, identity))
    else:
        provisional = owner.get("provisional_file")
        if not isinstance(provisional, str) or PurePosixPath(provisional).name.casefold() != unit.casefold():
            problems.append(f"{label} is named after a provisional file: provisional_file must be that file ({unit})")
        if confidence not in ("medium", "low"):
            problems.append(f"{label} is named after a provisional file: its confidence is at most medium")
    in_object = False
    for identity in artifacts:
        row = rows.get(identity)
        if row is None:
            continue  # outside the slice: refused above
        cluster_id = row.get("cluster")
        cluster = clusters.get(cluster_id) if isinstance(cluster_id, str) else None
        if cluster is not None:
            if names := _cluster_names(cluster):
                problems.append(
                    f"{label} {identity} lies in cluster {cluster_id}, which names {', '.join(names)}: an unnamed "
                    "object's artifacts lie in clusters with no unit or library"
                )
            else:
                in_object = True
        for value in row.get("tu_candidates") or []:
            if value.get("strength") in ("strong", "medium") and value.get("tu"):
                problems.append(
                    f"{label} {identity} has the {value['strength']} unit candidate {value['tu']}: the ELF names its unit"
                )
                break
    if not in_object:
        # No LOCAL cluster in the slice (none at all, or only outside it): the
        # row rests on its other evidence, which the scrutinizer confirms.
        review.append(f"{label} name_basis {basis}: none of its artifacts lies in a cluster of the slice")


def cross_plan_units(root: Path, tracker: dict[str, Any], item_id: Any) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    """The units of the other handed-off and accepted plans, by casefolded name, and notes on unreadable plans.

    Each plan is read at its packet path (``plan_path``); only authored and
    provider rows that name a unit count.
    """

    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    notes: list[str] = []
    for item in tracker.get("work_items", []):
        if item.get("kind") not in SOURCE_PLAN_KINDS or item.get("id") == item_id:
            continue
        status = item.get("status")
        if status not in CROSS_PLAN_STATUSES:
            continue
        relative = plan_path(item["id"])
        path = root / relative
        if not path.is_file():
            notes.append(f"{item['id']} is {status} but {relative} is missing: its units were not compared")
            continue
        try:
            other = load_json(path)
        except SocomError:
            other = None
        if not isinstance(other, dict):
            notes.append(f"{relative} is not a plan object: its units were not compared")
            continue
        for owner in other.get("owners") or []:
            if not isinstance(owner, dict) or owner.get("classification") not in ("authored", "provider"):
                continue
            unit = owner.get("translation_unit")
            if isinstance(unit, str) and unit:
                found[unit.casefold()].append(
                    {"item": item["id"], "status": status, **{field: owner.get(field) for field in CROSS_PLAN_FIELDS}}
                )
    return found, notes


def _check_cross_plan(
    root: Path,
    tracker: dict[str, Any],
    item_id: Any,
    row_units: list[tuple[dict[str, Any], str, str]],
    problems: list[str],
    review: list[str],
) -> list[dict[str, Any]]:
    """Compare each unit with the same unit in the other handed-off and accepted plans; the shared units.

    One unit is one file whichever plans own its artifacts, so its
    classification, ``workspace_path`` and ``original_path`` must agree.  A
    disagreement with an accepted plan is a problem; with a plan still
    awaiting acceptance it is a review note (whichever is accepted first
    decides, and the other then fails).  An ``original_path`` that only one
    of the two rows cites (the other null) names no other file: a review
    note either way.
    """

    if not row_units:
        return []
    others, notes = cross_plan_units(root, tracker, item_id)
    review.extend(notes)
    shared = []
    for owner, label, unit in row_units:
        for other in others.get(unit.casefold(), []):
            differs = [field for field in CROSS_PLAN_FIELDS if owner.get(field) != other[field]]
            uncited = [
                field for field in differs if field == "original_path" and (owner.get(field) is None or other[field] is None)
            ]
            conflicts = [field for field in differs if field not in uncited]
            shared.append({"unit": unit, "item": other["item"], "status": other["status"], "agrees": not differs})
            where = f"{other['item']} ({other['status']}) on {unit}"
            if conflicts:
                text = "; ".join(f"{field} {owner.get(field)!r} there {other[field]!r}" for field in conflicts)
                message = f"{label} disagrees with {where}: {text}; one unit is one file"
                (problems if other["status"] == "accepted" else review).append(message)
            if uncited:
                review.append(
                    f"{label} and {where} differ in citing the unit's original_path "
                    f"({owner.get('original_path')!r} here, {other['original_path']!r} there): cite it in both"
                )
    return shared


def validate_source_plan(
    root: Path,
    tracker: dict[str, Any],
    plan: Any,
    graph: dict[str, Any],
    *,
    section_of: Callable[[int], str | None] | None = None,
    applied: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check one owner plan against its work item and the graph it cites.

    ``applied`` holds the moves, creates and retired files the recorded
    source applies did (``source_apply.applied_state``: this plan's own
    apply only when its record names this plan file's SHA-256, and any
    other plan's apply, since a unit shared by several plans keeps one
    file).  Those files are checked in their applied state (moved and
    created files exist, moved-from and retired files are gone) instead of
    the state the plan was written against.  Every other check is the same,
    and without any apply record nothing changes.
    """

    problems: list[str] = []
    applied = applied if isinstance(applied, dict) else None
    moved_from = {
        str(row.get("from")): str(row.get("to"))
        for row in (applied or {}).get("moves") or []
        if isinstance(row, dict)
    }
    written_by_apply = set(moved_from.values()) | {str(path) for path in (applied or {}).get("created") or []}
    retired_by_apply = {str(row.get("path")) for row in (applied or {}).get("retired") or [] if isinstance(row, dict)}
    report: dict[str, Any] = {"problems": problems, "summary": {}, "review": []}

    def done() -> dict[str, Any]:
        report["ok"] = not problems
        return report

    if not isinstance(plan, dict):
        problems.append("the plan must be a JSON object")
        return done()
    schema = plan.get("schema_version")
    if plan.get("kind") != SOURCE_PLAN_KIND or schema not in SOURCE_PLAN_SCHEMAS or isinstance(schema, bool):
        problems.append(
            f"the plan is not a {SOURCE_PLAN_KIND} schema {' or '.join(map(str, SOURCE_PLAN_SCHEMAS))} document"
        )
    v2 = schema == 2
    if unknown := sorted(set(plan) - (PLAN_FIELDS_V2 if v2 else PLAN_FIELDS)):
        problems.append(f"the plan has unknown fields {unknown}")
    # A control character is corrupted evidence (a path's ``\apps`` read as
    # BEL + ``pps``), never a fact: refuse it wherever it lies.
    controls = control_characters(plan)
    for found in controls[:_SHOWN]:
        problems.append(f"control character in a plan string at {found}")
    if len(controls) > _SHOWN:
        problems.append(f"{len(controls) - _SHOWN} more plan strings hold control characters")
    if "draft" in plan and not isinstance(plan["draft"], dict):
        problems.append("draft must be an object (written by source plan draft)")
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
    if plan.get("graph_sha256") not in plan_graph_digests(batch):
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
        # The other applies reserving the same directories: they apply one at a time.
        report["reservation_shared_with"] = reservation_sharing(tracker, placement["apply_item"], placement["directories"])

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
    graph_units = {str(unit.get("tu", "")).casefold() for unit in graph["units"]}
    clusters = {row["id"]: row for row in graph.get("clusters") or [] if isinstance(row, dict) and "id" in row}
    # User decisions the rows cite: each file read once, the name index built on first use.
    decisions = DecisionCheck(root, graph)
    header_emits = plan.get("header_emits") if isinstance(plan.get("header_emits"), list) else []
    row_units: list[tuple[dict[str, Any], str, str]] = []

    scope = item["batch"]["scope"]
    review: list[str] = report["review"]
    provider_rows_elsewhere: list[str] = []
    owners = plan.get("owners")
    if not isinstance(owners, list):
        problems.append("owners must be a list")
        owners = []
    for number, owner in enumerate(owners, 1):
        if not isinstance(owner, dict):
            problems.append(f"owner {number} must be an object")
            continue
        label = f"owner {number} ({owner.get('translation_unit') or owner.get('library') or owner.get('classification')})"
        if unknown := sorted(set(owner) - (OWNER_FIELDS_V2 if v2 else OWNER_FIELDS)):
            problems.append(f"{label} has unknown fields {unknown}")
        if "draft" in owner:
            if owner["draft"] == DRAFT_OPEN:
                problems.append(f"{label} is still open in the draft: decide its paths, then remove \"draft\"")
            else:
                problems.append(f"{label} draft must be {DRAFT_OPEN!r} or absent")
        if "draft_rule" in owner and (not isinstance(owner["draft_rule"], str) or not owner["draft_rule"].strip()):
            problems.append(f"{label} draft_rule must name a rule")
        classification = owner.get("classification")
        if classification not in CLASSIFICATIONS:
            problems.append(f"{label} classification must be one of {list(CLASSIFICATIONS)}")
        if owner.get("confidence") not in CONFIDENCES:
            problems.append(f"{label} confidence must be one of {list(CONFIDENCES)}")
        if not _strings(owner.get("evidence")):
            problems.append(f"{label} needs evidence lines")
        entries = owner.get("artifacts")
        if not isinstance(entries, list) or not entries:
            problems.append(f"{label} must list its artifacts")
            entries = entries if isinstance(entries, list) else []
        artifacts = []
        explicit: list[str] = []
        for entry in entries:
            identity = artifact_id(entry)
            if identity is None or (isinstance(entry, dict) and not v2):
                problems.append(f"{label} artifacts must be artifact IDs" + (" or schema 2 entry objects" if v2 else ""))
                continue
            artifacts.append(identity)
            if isinstance(entry, dict):
                if unknown := sorted(set(entry) - ARTIFACT_ENTRY_FIELDS):
                    problems.append(f"{label} entry {identity} has unknown fields {unknown}")
                has_confidence, has_basis = "confidence" in entry, "basis" in entry
                if has_confidence != has_basis:
                    problems.append(f"{label} entry {identity} needs both confidence and basis")
                if has_confidence:
                    if entry["confidence"] not in CONFIDENCES:
                        problems.append(f"{label} entry {identity} confidence must be one of {list(CONFIDENCES)}")
                    else:
                        explicit.append(entry["confidence"])
                if has_basis and (not isinstance(entry["basis"], str) or not entry["basis"].strip()):
                    problems.append(f"{label} entry {identity} needs a basis line")
                if "draft_rule" in entry and (not isinstance(entry["draft_rule"], str) or not entry["draft_rule"].strip()):
                    problems.append(f"{label} entry {identity} draft_rule must name a rule")
        if explicit and owner.get("confidence") in CONFIDENCES:
            # The row's confidence is its weakest artifact's.
            weakest = max(explicit, key=CONFIDENCES.index)
            if CONFIDENCES.index(owner["confidence"]) < CONFIDENCES.index(weakest):
                problems.append(f"{label} confidence {owner['confidence']} is stronger than its weakest artifact's ({weakest})")
            elif len(explicit) == len(artifacts) and owner["confidence"] != weakest:
                problems.append(f"{label} confidence must be its weakest artifact's ({weakest})")
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
                elif workspace in written_by_apply:
                    if state != "exact" or not (root / workspace).is_file():
                        problems.append(f"{label} workspace_path {workspace} was written by the apply but is missing")
                elif state == "exact" and provisional != workspace:
                    problems.append(f"{label} workspace_path {workspace} exists: cite it as provisional_file")
            if provisional is not None:
                if not _workspace_path(provisional):
                    problems.append(f"{label} provisional_file must be a repo-relative path under src/")
                elif moved_from.get(provisional) == workspace and provisional != workspace:
                    # The apply moved it to its workspace path.
                    cited_files.add(provisional.casefold())
                    if (root / provisional).exists():
                        problems.append(f"{label} provisional_file {provisional} was moved by the apply but exists again")
                    if provisional in provisionals:
                        problems.append(f"{label} cites provisional_file {provisional} already cited by {provisionals[provisional]}")
                    provisionals.setdefault(provisional, label)
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
            elif scope.get("kind") == "provider" and library != scope.get("library"):
                problems.append(f"{label} names library {library!r}; this plan's scope is {scope.get('library')!r}")
            elif scope.get("kind") != "provider":
                provider_rows_elsewhere.append(f"{library} ({label})")
            if isinstance(member, dict) and "linked" in member and (not v2 or member["linked"] not in LINKED_KINDS):
                problems.append(f"{label} archive_member linked must be one of {list(LINKED_KINDS)} (schema 2)")
            if isinstance(member, dict) and "archive" in member and (
                not v2 or not isinstance(member["archive"], str) or not _FILE_NAME.match(member["archive"])
            ):
                problems.append(f"{label} archive_member archive must be the archive's file name, never a path (schema 2)")
            if isinstance(member, dict) and "version" in member and (
                not v2 or not isinstance(member["version"], str) or not member["version"].strip()
            ):
                problems.append(f"{label} archive_member version must be a non-empty string (schema 2)")
            if (
                not isinstance(member, dict)
                or set(member) - (MEMBER_FIELDS_V2 if v2 else MEMBER_FIELDS)
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
        _check_name_basis(
            owner, label, classification, unit, artifacts, entries, graph_units, clusters, rows, v2, header_emits,
            decisions, problems, review,
        )
        if unit and classification in ("authored", "provider"):
            row_units.append((owner, label, unit))

    unresolved = plan.get("unresolved")
    if not isinstance(unresolved, list):
        problems.append("unresolved must be a list")
        unresolved = []
    still_open: list[str] = []
    for number, row in enumerate(unresolved, 1):
        allowed = UNRESOLVED_FIELDS_V2 if v2 else {"artifact", "reason"}
        if (
            not isinstance(row, dict)
            or not {"artifact", "reason"} <= set(row) <= allowed
            or not isinstance(row.get("artifact"), str)
        ):
            problems.append(f"unresolved row {number} must be {{artifact, reason}}" + (" (+ draft)" if v2 else ""))
            continue
        reason = row.get("reason")
        if "draft" in row:
            # The draft left it for the planner: own it, or keep it with a real reason.
            if row["draft"] == DRAFT_OPEN:
                still_open.append(row["artifact"])
            else:
                problems.append(f"unresolved {row['artifact']} draft must be {DRAFT_OPEN!r} or absent")
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"unresolved {row['artifact']} needs a reason")
        elif reason.strip() == SKELETON_REASON:
            problems.append(f"unresolved {row['artifact']} still has the skeleton reason {SKELETON_REASON!r}")
        if "suggest" in row:
            # The drafter's suggestion may stay on a row the planner keeps unresolved (the reviewer sees it).
            for found in suggestion_problems(row["suggest"]):
                problems.append(f"unresolved {row['artifact']} suggest {found}")
        holders[row["artifact"]].append("unresolved")
    if still_open:
        problems.append(
            f"{len(still_open)} artifacts are still open in the draft (own them or give a reason and drop \"draft\"): "
            + _shown(still_open)
        )

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
            or not EMIT_FIELDS <= set(emit) <= (EMIT_FIELDS_V2 if v2 else EMIT_FIELDS)
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
        provider_header = emit.get("library")
        if provider_header is not None:
            # A provider header (MSL <string>): the owner's file emits the
            # instance by including it; no workspace header is written.
            if not isinstance(provider_header, str) or not provider_header.strip():
                problems.append(f"{label}: a provider header needs its library")
            if not _PROVIDER_HEADER.match(header):
                problems.append(f"{label}: a provider header is spelled <name>, as the owner's file includes it")
        elif not _workspace_path(header) or not header.casefold().endswith(HEADER_SUFFIXES):
            problems.append(f"{label}: header must be a repo-relative header path under src/ (or a <provider> header with its library)")
        else:
            cited_files.add(header.casefold())
            state, actual = _path_state(root, header)
            if state == "case":
                problems.append(f"{label}: header {header} differs in letter case from {actual} on disk")
            if placement is not None and not _within(header, placement["directories"]):
                # The apply writes the emits annotation into the header.
                problems.append(
                    f"{label}: header {header} lies outside the reservation of {placement['apply_item']} "
                    f"({_directories_text(placement['directories'])}): place it inside or record the correction in reservation"
                )
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
        if "draft_rule" in emit and (not isinstance(emit["draft_rule"], str) or not emit["draft_rule"].strip()):
            problems.append(f"{label} draft_rule must name a rule")

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
        if path in retired_by_apply and _workspace_path(path):
            if (root / path).exists():
                problems.append(f"retire_files {path} was retired by the apply but exists again")
            elif path.casefold() in cited_files:
                problems.append(f"retire_files {path} is cited by an owner or header-emit row")
        elif not _workspace_path(path) or _path_state(root, path)[0] != "exact" or not (root / path).is_file():
            problems.append(f"retire_files {path!r} must name an existing file under src/ exactly")
        elif path.casefold() in cited_files:
            problems.append(f"retire_files {path} is cited by an owner or header-emit row")
        if path in retired:
            problems.append(f"retire_files {path} is listed twice")
        retired.add(path)
        if not isinstance(row.get("reason"), str) or not row["reason"].strip() or not _strings(row.get("evidence")):
            problems.append(f"retire_files {path} needs a reason and evidence lines")

    notes = plan.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(value, str) for value in notes):
        problems.append("notes must be a list of strings")
        notes = []
    contradictions = _check_contradictions(
        root,
        plan.get("contradictions"),
        in_slice,
        moved_from,
        retired_by_apply,
        problems,
        graph_ids={row["id"] for row in graph["artifacts"]},
        files=owned_files(plan),
        review=review,
    )
    report["shared_units"] = _check_cross_plan(root, tracker, item["id"], row_units, problems, review)
    noted = [value for value in notes if value.strip().casefold().startswith(CONTRADICTION_NOTE)]
    if noted:
        # Plans written before the field keep their text notes; they stay valid.
        review.append(
            f"{len(noted)} notes record contradictions as text; a new plan lists them in contradictions "
            f"[{{{', '.join(CONTRADICTION_FIELDS)}}}]"
        )

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
    unknown_owned = sorted(
        (identity for identity in owner_of if rows.get(identity, {}).get("classification", {}).get("candidate") == "unknown"),
        key=_address,
    )
    if unknown_owned:
        review.append(f"{len(unknown_owned)} owned artifacts have no graph classification candidate (unknown): {_shown(unknown_owned)}")
    if provider_rows_elsewhere:
        review.append(
            f"this {scope.get('kind')} plan owns provider rows ({', '.join(provider_rows_elsewhere)}): its apply records "
            "them in tracker evidence as a provider apply does, and writes nothing for them under src/"
        )
    # An inline (binding 13) or WEAK instance is usually a header's body: the
    # scrutinizer confirms the unit defines it when no header emits it.
    unemitted = sorted(
        (
            identity
            for identity, owner in owner_of.items()
            if owner.get("classification") == "authored"
            and identity not in emitted
            and rows.get(identity, {}).get("kind") == "function"
            and _instance_bindings(rows[identity]) & {"13", "WEAK"}
        ),
        key=_address,
    )
    if unemitted:
        review.append(
            f"{len(unemitted)} owned inline or WEAK functions have no header-emit row (their owner's file defines "
            f"them): {_shown(unemitted)}"
        )
    report["summary"] = {
        "slice_artifacts": len(slice_ids),
        "owned": sum(1 for identity in slice_ids if identity in owner_of),
        "unresolved": len(unresolved),
        "owners": dict(sorted(Counter(str(owner.get("classification")) for owner in owners if isinstance(owner, dict)).items())),
        "annotations": dict(sorted(Counter(row["relation"] for row in expected).items())),
        "header_emits": len(header_emits),
        "retire_files": len(retire),
        "schema_version": schema,
        "draft_open": len(still_open),
    }
    if "contradictions" in plan:
        report["summary"]["contradictions"] = contradictions
    report["applied"] = applied is not None
    return done()


def _instance_bindings(row: dict[str, Any]) -> set[Any]:
    return {item.get("binding") for item in row.get("names") or []} | {row.get("binding")}


def _line_count(path: Path) -> int:
    with open(path, "rb") as handle:
        return sum(1 for _line in handle)


def _frozen_base_lines(root: Path, relative: str) -> int | None:
    """Line count of ``relative`` in the stage 5 skeleton route's frozen base (the pre-skeleton src/), or None."""

    from .order_skeleton_route import base_root

    path = base_root(root) / relative
    return _line_count(path) if path.is_file() else None


def _check_contradictions(
    root: Path,
    rows: Any,
    in_slice: set[str],
    moved_from: dict[str, str],
    retired_by_apply: set[str],
    problems: list[str],
    *,
    graph_ids: set[str] | None = None,
    files: set[str] | None = None,
    review: list[str] | None = None,
) -> int:
    """Check the plan's structured contradictions with provisional source; their count.

    Each row names an artifact of the slice, an existing provisional file
    under ``src/`` (in its applied state: a file the apply moved is checked
    at its new path, a retired one is accepted), a line in it (or null), a
    kind slug and ELF evidence lines.  An artifact outside the slice is
    allowed when it is an artifact of the graph and the file is one an
    authored row of this plan owns (``files``: its provisional or workspace
    path), such as an owned file defining a function the ELF places in
    another segment; the review notes such rows.
    """

    if rows is None:
        return 0
    if not isinstance(rows, list):
        problems.append("contradictions must be a list")
        return 0
    seen: set[tuple[Any, ...]] = set()
    elsewhere: list[str] = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != set(CONTRADICTION_FIELDS):
            problems.append(f"contradictions row {number} must be {{{', '.join(CONTRADICTION_FIELDS)}}}")
            continue
        identity, path, line, kind = row["artifact"], row["provisional_file"], row["line"], row["kind"]
        label = f"contradiction {number} ({identity})"
        if not isinstance(identity, str):
            problems.append(f"{label}: its artifact must lie in the scope's slice")
        elif identity not in in_slice:
            if identity not in (graph_ids or ()):
                problems.append(f"{label}: its artifact is not an artifact of the graph")
            elif not isinstance(path, str) or path not in (files or ()):
                problems.append(
                    f"{label}: its artifact lies outside the scope's slice, so its provisional_file must be one this "
                    "plan's authored rows own (provisional_file or workspace_path)"
                )
            else:
                elsewhere.append(f"{identity} in {path}")
        if not isinstance(kind, str) or not _CONTRADICTION_KIND.match(kind):
            problems.append(f"{label}: kind must be a lowercase slug such as defined-elsewhere")
        if not _strings(row["elf_evidence"]):
            problems.append(f"{label} needs elf_evidence lines")
        if line is not None and (not isinstance(line, int) or isinstance(line, bool) or line < 1):
            problems.append(f"{label}: line must be a positive line number or null")
            line = None
        if not _workspace_path(path):
            problems.append(f"{label}: provisional_file must be a repo-relative path under src/")
        elif path in retired_by_apply:
            pass  # retired by the apply: the contradiction is historical
        else:
            target = moved_from.get(path, path)
            state, actual = _path_state(root, target)
            if state != "exact" or not (root / target).is_file():
                problems.append(
                    f"{label}: provisional_file {path} must name an existing file exactly" + (f" (on disk: {actual})" if actual else "")
                )
            elif line is not None:
                count = _line_count(root / target)
                # The line quotes the provisional file as stage 4 saw it. Once a later stage rewrote the file
                # (stage 5 skeletons, the functional port lane), that content is the skeleton route's frozen base.
                frozen = _frozen_base_lines(root, target) if line > count else None
                if line > count and (frozen is None or line > frozen):
                    problems.append(f"{label}: {path} has {count} lines, not {line}")
                elif line > count and review is not None:
                    review.append(f"{label}: line {line} is in the frozen skeleton base's {target} ({frozen} lines); "
                                  f"src/ has {count} lines after later stages")
        key = (repr(identity), repr(path), line, repr(kind))
        if key in seen:
            problems.append(f"{label} is listed twice")
        seen.add(key)
    if elsewhere and review is not None:
        review.append(
            f"{len(elsewhere)} contradictions concern artifacts outside the slice in files this plan owns: {_shown(elsewhere)}"
        )
    return len(rows)


# -- evidence and skeleton ------------------------------------------------------


def input_section_text(row: dict[str, Any]) -> str:
    """The input section of an artifact, or where it lies between two of them."""

    section = row.get("input_section") or {}
    if section.get("name"):
        return section["name"]
    before, after = (list(section.get("between") or []) + [None, None])[:2]
    return f"between {before or 'start'} and {after or 'end'}"


def _compact(row: dict[str, Any], section_of: Callable[[int], str | None]) -> dict[str, Any]:
    classification = row["classification"]
    out: dict[str, Any] = {
        "id": row["id"],
        "kind": row["kind"],
        "address": row["address"],
        "end": row["end"],
        "size": row["size"],
        "section": section_of(int(row["address"], 16)),
        "input_section": input_section_text(row),
        "named": named(row),
        "classification": {
            "candidate": classification.get("candidate"),
            "library": classification.get("library"),
            "weak": classification.get("weak") is True,
            "evidence": list(classification.get("evidence") or []),
        },
        "tu_candidates": [{key: candidate[key] for key in ("tu", "strength", "via")} for candidate in row["tu_candidates"]],
    }
    if row["kind"] == "gap":
        out.update(fill=row.get("fill"), padding=row.get("padding"), labels=row.get("labels"))
    else:
        out["binding"] = row.get("binding")
        out["names"] = [{"name": item["name"], "binding": item.get("binding")} for item in row.get("names") or []]
        bindings = {item.get("binding") for item in row.get("names") or []} | {row.get("binding")}
        # WEAK or Metrowerks binding 13 (inline): an instance a header may emit.
        out["weak"] = "WEAK" in bindings
        out["inline"] = "13" in bindings
        if row.get("common"):
            # A COMMON allocation after every input section (``source graph``).
            out["common"] = True
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
    segment_keys = (
        "id", "segment_number", "start", "end", "function_count", "classification_mix", "tu_candidates", "boundary",
        "internal_boundaries",
    )
    evidence = {
        "kind": SOURCE_EVIDENCE_KIND,
        "schema_version": 1,
        "work_item_id": item["id"],
        "scope": item["batch"]["scope"],
        "graph_sha256": graph["graph_sha256"],
        "slice_sha256": entry["slice_sha256"],
        "artifact_count": len(rows),
        "segments": [{key: segment[key] for key in segment_keys if key in segment} for segment in entry["segments"]],
        "moved_from_segments": list(item["batch"].get("moved_from_segments") or []),
        "units": [unit for unit in graph["units"] if unit["tu"].casefold() in units],
        # Every GNU object one of whose functions or gaps (crt0's code) lies in the slice.
        "gnu_objects": [
            row for row in graph["gnu_objects"] if wanted & set(row["functions"]) | wanted & set(row.get("gaps") or [])
        ],
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
