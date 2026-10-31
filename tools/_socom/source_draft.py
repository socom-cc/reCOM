"""Draft stage 4 owner plans: decide what fixed rules settle, leave the rest open.

``source plan draft`` writes a schema 2 ``socom-source-owner-plan`` for one
plan item.  Every artifact a rule decides sits in an owner row as an entry
``{artifact, confidence, basis, draft_rule}``; every other artifact is an
``unresolved`` row marked ``"draft": "open"`` that the planner must own or
keep with a real reason.  ``source plan draft --check`` re-runs the rules
and proves each entry, owner row and header-emit row that still carries a
``draft_rule`` equals what the rules give, so a reviewer reviews only the
rows without one.  Each rule is conservative: when its conditions are not
all met the artifact stays open.

Rules version 1 (decision of 2026-10-31).  Unit anchors (high):

A-dwarf-cu      a DWARF compile unit with a source path covers the artifact.
A-dwarf-header  a header compile unit covers the function; it lies in the
                ``.debug`` contribution of one object's unit
                (``source_facts``: per-object DWARF order).
A-sinit         ``__sinit_<file>`` / ``.p__sinit_<file>``.
A-unnamed       an ``@unnamed@<file>@`` tag in a symbol name.
A-dwarf-static  a DWARF static (local_variable) of one unit's CU.
A-file-string   a ``__FILE__`` literal of the unit, or a function whose
                relocations reach one.
A-local-block   the artifact's object cluster (LOCAL relocations, section
                symbols, LOCAL symbol order) names exactly that one unit and
                the graph's primary candidate is that unit, strong.

Anchors that name different units leave the artifact open.

A-between       (medium) an unanchored function strictly between the nearest
                anchored functions of its code window, both of one unit, with
                no GNU object starting in between and no strong or medium
                candidate of another unit.  A WEAK or binding-13 (inline)
                instance qualifies only when every artifact referencing it is
                anchored to that unit.
D-referenced    (medium) unanchored data every referencing function of which
                (followed through referencing data) is decided for one unit.
C-fill          (high) zero or zero-fill alignment padding (the graph's
                ``padding``): the compiler-generated row.
P-gnu-object    a function or gap of a GNU object whose library is the
                plan's provider library (any library outside provider plans):
                one provider row per object.  High at the object's anchor or
                when the object ends at the next GNU anchor, else medium.
P-gnu-data      data in the object cluster of one GNU object's functions
                (high), or referenced only by them (medium).

Rows.  An authored unit's row takes its paths from:

O-provisional   exactly one file under ``src/`` has the unit's exact name:
                ``provisional_file`` and ``workspace_path``;
O-path          else, when no file has that name in any letter case, the
                unit's single ``Z:\\dev`` source path names an existing
                ``src/`` module directory: ``workspace_path`` there.

Otherwise the row is ``"draft": "open"`` with null paths.  ``original_path``
is the unit's single quoted source path, if any.  A provider unit (a
provider path) never gets an authored row: its artifacts stay open unless a
GNU object rule decides them.

H-dwarf-header  a decided authored function whose header compile unit names a
                ``Z:\\dev`` header that exists under the unit's module
                directory (``header`` there), or a provider header
                (``<name>`` and its library): reason ``template`` (template
                arguments), ``weak`` (WEAK) or ``inline`` (binding 13).

Rules version 2 (the default; a plan is checked under the version it was
drafted with) changes two rules and keeps every other one:

A-between       a WEAK or binding-13 instance whose referrers are not all
                anchored to the unit is decided too when it is a single copy
                (no other function carries one of its names) and nothing of
                another unit lies between the two anchors: no GNU object
                start, no provider-proven function and no function with a
                strong or medium candidate of another unit.  On the
                reference graph ``837c03c4`` every one of the 172 inline or
                WEAK copies that DWARF places in an authored unit and that
                sits strictly between two anchors of one unit is that
                unit's; the 22 at a unit edge stay open.
P-gnu-object    the provider row of a GNU object one of whose DWARF compile
                units was produced by the project's toolchain (a Metrowerks
                producer, e.g. ``Metrowerks MW GAS R5900 Assembler`` for
                crt0.s) records ``archive_member.linked: "object"``: the
                object was assembled or compiled with the project, not taken
                from an archive.
"""

from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath
from typing import Any, Callable

from .constants import REFERENCE_SHA256
from .source_facts import header_contributions
from .source_graph import _is_source, path_library
from .source_plan import (
    CONFIDENCES,
    DRAFT_OPEN,
    INFERRED_STATUS,
    SOURCE_FILE_SUFFIXES,
    SOURCE_PLAN_KIND,
    SOURCE_PLAN_SCHEMA,
    apply_reservation,
    artifact_id,
    derive_annotations,
    original_module,
    plan_item,
    provider_units,
    scope_entry,
    strong_provider,
)
from .util import SocomError

DRAFT_RULES_VERSION = 2
RULES_VERSIONS = (1, 2)
# The version a plan without a recorded (known) draft rules version is checked under.
UNVERSIONED_RULES = 1
ANCHOR_ORDER = ("A-dwarf-cu", "A-dwarf-header", "A-sinit", "A-unnamed", "A-dwarf-static", "A-file-string", "A-local-block")
FILL_ROW = "compiler-generated"
# A DWARF producer of the project's own (Metrowerks) toolchain.
TOOLCHAIN_PRODUCER = re.compile(r"^(?:Metrowerks|MW)\b")


def _hex_int(value: str) -> int:
    return int(value, 16)


class _Workspace:
    """Files and directories under ``src/`` as the draft's path rules read them."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.by_name: dict[str, list[str]] = defaultdict(list)
        self.by_folded: dict[str, list[str]] = defaultdict(list)
        self.directories: dict[str, str] = {}
        source = root / "src"
        if source.is_dir():
            for path in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
                relative = path.relative_to(root).as_posix()
                if path.is_dir():
                    self.directories.setdefault(relative.casefold(), relative)
                elif path.is_file():
                    self.by_name[path.name].append(relative)
                    self.by_folded[path.name.casefold()].append(relative)

    def exact_file(self, relative: str) -> bool:
        current = self.root
        for part in relative.split("/"):
            try:
                if part not in os.listdir(current):
                    return False
            except (FileNotFoundError, NotADirectoryError):
                return False
            current = current / part
        return current.is_file()


class _Draft:
    def __init__(
        self, graph: dict[str, Any], facts: dict[str, Any], workspace: _Workspace, rules: int = DRAFT_RULES_VERSION
    ) -> None:
        self.rules = rules
        self.graph = graph
        self.rows = graph["artifacts"]
        self.by_id = {row["id"]: row for row in self.rows}
        self.position = {row["id"]: index for index, row in enumerate(self.rows)}
        self.clusters = {row["id"]: row for row in graph.get("clusters") or []}
        self.gnu = {row["address"]: row for row in graph.get("gnu_objects") or []}
        self.gnu_starts = {_hex_int(row["address"]) for row in graph.get("gnu_objects") or []}
        self.units = {row["tu"].casefold(): row for row in graph.get("units") or []}
        self.unit_library = provider_units(graph)
        self.contributions = header_contributions(facts.get("compile_units") or [])
        self.workspace = workspace
        self.users: dict[str, set[str]] = defaultdict(set)
        self.uses: dict[str, set[str]] = defaultdict(set)
        for reference in facts.get("references") or []:
            site, target = reference.get("site_artifact"), reference.get("target_artifact")
            if site and target and site != target:
                self.users[target].add(site)
                self.uses[site].add(target)
        # How many function artifacts carry each symbol name (a single copy has 1).
        self.copies: Counter[str] = Counter(
            item["name"] for row in self.rows if row["kind"] == "function" for item in row.get("names") or [] if item.get("name")
        )
        self.anchor = {row["id"]: self._anchors(row) for row in self.rows if row["kind"] != "gap"}
        self.decided: dict[str, tuple[str, str, str, str]] = {}
        for identity, found in self.anchor.items():
            units = {unit.casefold() for unit, _rule, _basis in found}
            if len(units) == 1:
                unit, rule, basis = min(found, key=lambda row: ANCHOR_ORDER.index(row[1]))
                self.decided[identity] = (self._spelling(unit), rule, basis, "high")
        self._between()

    # -- anchors -------------------------------------------------------------

    def _spelling(self, unit: str) -> str:
        known = self.units.get(unit.casefold())
        return known["tu"] if known else unit

    def _anchors(self, row: dict[str, Any]) -> list[tuple[str, str, str]]:
        found: list[tuple[str, str, str]] = []
        for item in row.get("signals") or []:
            signal, strength, unit = item.get("signal"), item.get("strength"), item.get("tu")
            if signal == "dwarf-cu" and unit:
                found.append((unit, "A-dwarf-cu", f"dwarf-cu {item.get('path')} pc {item.get('low_pc')}-{item.get('high_pc')} (die {item.get('die_offset')})"))
            elif signal == "dwarf-cu-header" and row["kind"] == "function":
                owner = self.contributions.get(item.get("die_offset"))
                if owner:
                    found.append((owner, "A-dwarf-header", f"header CU {item.get('path')} (die {item.get('die_offset')}) lies in the .debug contribution of {owner}"))
            elif signal == "sinit" and unit:
                found.append((unit, "A-sinit", f"static-initializer symbol {item.get('symbol')}"))
            elif signal == "unnamed-namespace" and unit:
                found.append((unit, "A-unnamed", f"@unnamed@ tag in {item.get('symbol')}"))
            elif signal == "dwarf-variable" and strength == "strong" and unit:
                found.append((unit, "A-dwarf-static", f"DWARF static {item.get('variable')} (die {item.get('die_offset')}) in {item.get('path')}"))
            elif signal == "file-string" and strength == "strong" and unit:
                found.append((unit, "A-file-string", f"__FILE__ literal {item.get('text')!r}"))
        if row["kind"] == "function":
            for target in sorted(self.uses.get(row["id"], ()), key=self.position.__getitem__):
                for item in self.by_id[target].get("signals") or []:
                    if item.get("signal") == "file-string" and item.get("strength") == "strong" and item.get("tu"):
                        found.append((item["tu"], "A-file-string", f"references the __FILE__ literal {item.get('text')!r} ({target})"))
        cluster = self.clusters.get(row.get("cluster") or "")
        candidates = row.get("tu_candidates") or []
        if cluster and len(cluster.get("units") or []) == 1 and candidates:
            unit = cluster["units"][0]["tu"]
            primary = candidates[0]
            if primary["tu"].casefold() == unit.casefold() and primary["strength"] == "strong":
                found.append((unit, "A-local-block", f"object cluster {cluster['id']} of {unit} (LOCAL relocations and symbol order)"))
        return found

    def conflict(self, identity: str) -> list[str]:
        return sorted({unit for unit, _rule, _basis in self.anchor.get(identity, ())}, key=str.casefold)

    @staticmethod
    def bindings(row: dict[str, Any]) -> set[Any]:
        return {item.get("binding") for item in row.get("names") or []} | {row.get("binding")}

    def _between(self) -> None:
        windows: dict[str, list[str]] = defaultdict(list)
        for row in self.rows:
            if row["kind"] == "function":
                windows[row["window"]].append(row["id"])
        self.windows = dict(windows)
        self.window_order = {identity: order for functions in windows.values() for order, identity in enumerate(functions)}
        high = dict(self.decided)
        for functions in windows.values():
            marks = []
            for identity in functions:
                if identity in self.decided:
                    marks.append(self.decided[identity][0].casefold())
                elif len(self.conflict(identity)) > 1:
                    marks.append("?")
                else:
                    marks.append(None)
            for order, identity in enumerate(functions):
                if marks[order] is not None:
                    continue
                left = next((k for k in range(order - 1, -1, -1) if marks[k] is not None), None)
                right = next((k for k in range(order + 1, len(functions)) if marks[k] is not None), None)
                if left is None or right is None or marks[left] != marks[right] or marks[left] == "?":
                    continue
                unit = marks[left]
                if any(_hex_int(self.by_id[functions[k]]["address"]) in self.gnu_starts for k in range(left + 1, right + 1)):
                    continue
                row = self.by_id[identity]
                if strong_provider(row, self.unit_library) is not None:
                    continue
                if any(
                    candidate["tu"].casefold() != unit and candidate["strength"] in ("strong", "medium")
                    for candidate in row.get("tu_candidates") or []
                ):
                    continue
                spelled = self._spelling(self.decided[functions[left]][0])
                basis = f"between {functions[left]} and {functions[right]}, both {spelled}, with no other anchor or GNU object between"
                if self.bindings(row) & {"WEAK", "13"}:
                    referrers = self.users.get(identity, set())
                    if any((high.get(other) or ("",))[0].casefold() != unit for other in referrers):
                        # Rules 2: a single copy that nothing of another unit
                        # separates from both anchors is that unit's, whoever
                        # else calls it.
                        if self.rules < 2 or not self._contained_copy(row, functions[left + 1 : right], unit):
                            continue
                        basis = (
                            f"inline/WEAK single copy between {functions[left]} and {functions[right]}, both {spelled}, "
                            "with no other unit, provider function or GNU object between (other units call it)"
                        )
                self.decided[identity] = (spelled, "A-between", basis, "medium")

    def _contained_copy(self, row: dict[str, Any], between: list[str], unit: str) -> bool:
        """Rules 2: an inline/WEAK single copy with nothing of another unit between its two anchors."""

        if any(self.copies[item["name"]] != 1 for item in row.get("names") or [] if item.get("name")):
            return False
        for identity in between:
            other = self.by_id[identity]
            if strong_provider(other, self.unit_library) is not None:
                return False
            if any(
                candidate["tu"].casefold() != unit and candidate["strength"] in ("strong", "medium")
                for candidate in other.get("tu_candidates") or []
            ):
                return False
        return True

    def toolchain_producer(self, gnu: dict[str, Any]) -> str | None:
        """The project-toolchain DWARF producer of a GNU object's functions or gaps, if any."""

        for identity in [*(gnu.get("functions") or []), *(gnu.get("gaps") or [])]:
            for item in (self.by_id.get(identity) or {}).get("signals") or []:
                producer = item.get("producer")
                if item.get("signal") == "dwarf-cu" and isinstance(producer, str) and TOOLCHAIN_PRODUCER.match(producer):
                    return producer
        return None

    # -- data ------------------------------------------------------------------

    def function_users(self, identity: str) -> tuple[set[str], bool]:
        """(functions referencing ``identity`` through data, whether any site is a gap)."""

        functions: set[str] = set()
        seen = {identity}
        pending = [identity]
        gap = False
        while pending:
            current = pending.pop()
            for site in self.users.get(current, ()):
                kind = self.by_id[site]["kind"]
                if kind == "function":
                    functions.add(site)
                elif kind == "gap":
                    gap = True
                elif site not in seen:
                    seen.add(site)
                    pending.append(site)
        return functions, gap

    def gnu_of_cluster(self, row: dict[str, Any]) -> set[str]:
        cluster = self.clusters.get(row.get("cluster") or "")
        if not cluster:
            return set()
        return {self.by_id[member].get("gnu_object") for member in cluster["members"] if self.by_id[member].get("gnu_object")}


def _entry(identity: str, confidence: str, basis: str, rule: str) -> dict[str, Any]:
    return {"artifact": identity, "confidence": confidence, "basis": basis, "draft_rule": rule}


def _weakest(entries: list[dict[str, Any]]) -> str:
    return max((entry["confidence"] for entry in entries), key=CONFIDENCES.index)


def _emit_reason(row: dict[str, Any]) -> str | None:
    if any("<" in str(item.get("name")) for item in row.get("names") or []):
        return "template"
    bindings = _Draft.bindings(row)
    if "WEAK" in bindings:
        return "weak"
    if "13" in bindings:
        return "inline"
    return None


def draft_owner_plan(
    root: Path,
    tracker: dict[str, Any],
    item_id: str,
    graph: dict[str, Any],
    facts: dict[str, Any],
    *,
    rules: int = DRAFT_RULES_VERSION,
    section_of: Callable[[int], str | None],
) -> dict[str, Any]:
    """The rule-decided owner plan of one plan item (schema 2)."""

    if rules not in RULES_VERSIONS:
        raise SocomError(f"source draft rules version {rules} is not one of {', '.join(map(str, RULES_VERSIONS))}")
    item = plan_item(tracker, item_id)
    entry = scope_entry(graph, item)
    scope = item["batch"]["scope"]
    draft = _Draft(graph, facts, _Workspace(root), rules)
    workspace = draft.workspace

    owners: dict[tuple[str, str | None], dict[str, Any]] = {}
    entries: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
    open_rows: list[dict[str, Any]] = []
    rule_counts: Counter[str] = Counter()

    def place(key: tuple[str, str | None], value: dict[str, Any], row: dict[str, Any]) -> None:
        owners.setdefault(key, row)
        entries[key].append(value)
        rule_counts[value["draft_rule"]] += 1

    def leave(identity: str, reason: str) -> None:
        open_rows.append({"artifact": identity, "reason": reason, "draft": DRAFT_OPEN})

    def provider_row(gnu: dict[str, Any], identity: str) -> dict[str, Any]:
        library = gnu.get("library") or "unidentified GNU object"
        unit, original = None, None
        for item in draft.by_id[identity].get("signals") or []:
            if item.get("signal") == "dwarf-cu" and (path_library(item.get("path") or "") or ("",))[0] == "provider":
                unit, original = item.get("tu"), item.get("path")
        member: dict[str, Any] = {"gnu_object": gnu["address"], "object": None}
        evidence = [f"GNU object at {gnu['address']} ({', '.join(row['name'] for row in gnu.get('anchor') or []) or 'anchor'}); "
                    f"library {library} by {gnu.get('library_basis') or 'no library evidence'}; end: {gnu.get('end_basis')}"]
        producer = draft.toolchain_producer(gnu) if draft.rules >= 2 else None
        if producer is not None:
            # Rules 2: assembled or compiled by the project's toolchain (crt0.s).
            member["linked"] = "object"
            evidence.append(f"DWARF producer {producer}: built with the project's toolchain, linked as an object, not an archive member")
        return {
            "translation_unit": unit,
            "classification": "provider",
            "workspace_path": None,
            "original_path": original,
            "provisional_file": None,
            "library": library,
            "archive_member": member,
            "draft_rule": "P-gnu-object",
            "evidence": evidence,
        }

    library = scope.get("library") if scope["kind"] == "provider" else None
    for identity in entry["artifacts"]:
        row = draft.by_id[identity]
        kind = row["kind"]
        if kind == "gap" and row.get("padding"):
            place((FILL_ROW, None), _entry(identity, "high", f"{row.get('fill')} alignment padding, {row['size']} bytes", "C-fill"), {
                "translation_unit": None, "classification": "compiler-generated", "workspace_path": None,
                "original_path": None, "provisional_file": None, "library": None, "archive_member": None,
                "evidence": ["alignment padding the graph marks padding (zero or zero-fill, under 16 bytes, no labels); no unit defines it"],
            })
            continue
        gnu = draft.gnu.get(row.get("gnu_object") or "")
        if gnu is not None:
            gnu_library = gnu.get("library") or "unidentified GNU object"
            if library is not None and gnu_library != library:
                leave(identity, f"GNU object {gnu['address']} has library {gnu_library}, this plan's scope is {library}")
                continue
            if draft.anchor.get(identity) and any(
                draft.unit_library.get(unit.casefold()) != gnu_library for unit, _rule, _basis in draft.anchor[identity]
            ):
                leave(identity, f"GNU object {gnu['address']} member with unit anchors {', '.join(draft.conflict(identity))}")
                continue
            certain = _hex_int(row["address"]) == _hex_int(gnu["address"]) or kind == "gap" or gnu.get("end_basis") == "next GNU anchor"
            place(("provider", gnu["address"]), _entry(
                identity, "high" if certain else "medium",
                f"{kind} of GNU object {gnu['address']} (end: {gnu.get('end_basis')})", "P-gnu-object",
            ), provider_row(gnu, identity))
            continue
        if kind == "data":
            objects = {value for value in draft.gnu_of_cluster(row) if value in draft.gnu}
            users, via_gap = draft.function_users(identity)
            user_objects = {draft.by_id[user].get("gnu_object") for user in users}
            target, confidence, basis = None, None, None
            if len(objects) == 1:
                target = next(iter(objects))
                confidence, basis = "high", f"object cluster {row.get('cluster')} of GNU object {target}"
            elif users and not via_gap and len(user_objects) == 1 and None not in user_objects:
                target = next(iter(user_objects))
                confidence, basis = "medium", f"referenced only by functions of GNU object {target} ({len(users)})"
            if target is not None and not draft.anchor.get(identity):
                gnu = draft.gnu[target]
                gnu_library = gnu.get("library") or "unidentified GNU object"
                if library is not None and gnu_library != library:
                    leave(identity, f"data of GNU object {target} (library {gnu_library}), this plan's scope is {library}")
                    continue
                place(("provider", target), _entry(identity, confidence, basis, "P-gnu-data"), provider_row(gnu, gnu["functions"][0] if gnu["functions"] else identity))
                continue
        if library is not None:
            leave(identity, "no GNU object rule decides it: a provider plan names its archive member by hand")
            continue
        if kind == "gap":
            leave(identity, f"{row.get('fill')} fill of {row['size']} bytes" + (f" with labels {', '.join(row.get('labels') or [])}" if row.get("labels") else "") + " is not alignment padding")
            continue
        decided = draft.decided.get(identity)
        if decided is None and kind == "data" and len(draft.conflict(identity)) <= 1 and strong_provider(row, draft.unit_library) is None:
            users, via_gap = draft.function_users(identity)
            units = {(draft.decided.get(user) or ("",))[0].casefold() for user in users}
            if users and not via_gap and len(units) == 1 and "" not in units:
                spelled = draft.decided[next(iter(users))][0]
                decided = (spelled, "D-referenced", f"referenced only by {len(users)} function(s) of {spelled}", "medium")
        if decided is None:
            conflict = draft.conflict(identity)
            if len(conflict) > 1:
                leave(identity, f"anchors name several units: {', '.join(conflict)}")
            elif kind == "function":
                leave(identity, _open_function_reason(draft, identity))
            else:
                leave(identity, "no unit anchor, and its referencing functions are not all decided for one unit")
            continue
        unit, rule, basis, confidence = decided
        if not unit.casefold().endswith(SOURCE_FILE_SUFFIXES) or unit.casefold() in draft.unit_library:
            leave(identity, f"its unit {unit} is not an authored source unit (provider or header unit)")
            continue
        place(("authored", unit.casefold()), _entry(identity, confidence, basis, rule), {"translation_unit": unit})

    out_owners = []
    for key in sorted(owners, key=lambda key: min(draft.position[value["artifact"]] for value in entries[key])):
        row = dict(owners[key])
        values = entries[key]
        if key[0] == "authored":
            row = _authored_row(draft, workspace, row["translation_unit"])
        row["confidence"] = _weakest(values)
        evidence = list(row.pop("evidence", []))
        counts = Counter(value["draft_rule"] for value in values)
        evidence.append("draft rules " + ", ".join(f"{name} {count}" for name, count in sorted(counts.items())))
        row["evidence"] = evidence
        row["artifacts"] = sorted(values, key=lambda value: draft.position[value["artifact"]])
        out_owners.append(row)

    header_emits, open_emits = _header_emits(draft, workspace, out_owners)
    plan: dict[str, Any] = {
        "kind": SOURCE_PLAN_KIND,
        "schema_version": SOURCE_PLAN_SCHEMA,
        "work_item_id": item["id"],
        "scope": scope,
        "graph_sha256": graph["graph_sha256"],
        "slice_sha256": entry["slice_sha256"],
        "target": {"source_sha256": REFERENCE_SHA256},
        "owners": out_owners,
        "header_emits": header_emits,
        "annotations": [],
        "unresolved": open_rows,
        "retire_files": [],
        "notes": [],
    }
    plan["annotations"] = derive_annotations(plan, graph, section_of)
    reservation = apply_reservation(tracker, item)
    outside: list[str] = []
    if reservation is not None and not reservation["missing"]:
        directories = reservation["directories"]
        for row in out_owners:
            for field in ("workspace_path", "provisional_file"):
                value = row.get(field)
                if isinstance(value, str) and not any(value.startswith(f"{directory}/") for directory in directories):
                    outside.append(value)
        outside.extend(
            emit["header"] for emit in header_emits
            if emit.get("library") is None and not any(emit["header"].startswith(f"{directory}/") for directory in directories)
        )
        if reservation["inferred"]:
            plan["reservation"] = {
                "directories": list(directories),
                "status": INFERRED_STATUS,
                "reason": reservation["reason"],
                "evidence": [],
            }
    plan["draft"] = {
        "rules_version": rules,
        "graph_sha256": graph["graph_sha256"],
        "decided": sum(len(values) for values in entries.values()),
        "open": len(open_rows),
        "rules": dict(sorted(rule_counts.items())),
        "open_owner_rows": sorted(row["translation_unit"] for row in out_owners if row.get("draft") == DRAFT_OPEN),
        "open_header_emits": open_emits,
        "outside_reservation": sorted(set(outside)),
    }
    return plan


def _open_function_reason(draft: _Draft, identity: str) -> str:
    row = draft.by_id[identity]
    functions = draft.windows[row["window"]]
    order = draft.window_order[identity]
    left = next((functions[k] for k in range(order - 1, -1, -1) if functions[k] in draft.decided), None)
    right = next((functions[k] for k in range(order + 1, len(functions)) if functions[k] in draft.decided), None)
    a = draft.decided[left][0] if left else None
    b = draft.decided[right][0] if right else None
    if a and b and a.casefold() != b.casefold():
        return f"boundary function between {a} ({left}) and {b} ({right})"
    if a and b and draft.bindings(row) & {"WEAK", "13"}:
        if draft.rules >= 2:
            return (
                f"WEAK/inline instance between {a} anchors, referenced from outside {a}, and not a contained single "
                "copy (another function has its name, or a GNU object, provider function or another unit's "
                "candidate lies between)"
            )
        return f"WEAK/inline instance between {a} anchors, referenced from outside {a}"
    if a and b:
        return f"between {a} anchors, but a GNU object, another unit's candidate or a provider classification intervenes"
    return "no unit anchor on one side in its code window"


def _authored_row(draft: _Draft, workspace: _Workspace, unit: str) -> dict[str, Any]:
    known = draft.units.get(unit.casefold()) or {}
    sources = sorted({path for path in known.get("paths") or [] if _is_source(path)})
    original = sources[0] if len(sources) == 1 else None
    row: dict[str, Any] = {
        "translation_unit": unit,
        "classification": "authored",
        "workspace_path": None,
        "original_path": original,
        "provisional_file": None,
        "library": None,
        "archive_member": None,
    }
    evidence = []
    if original:
        evidence.append(f"original path {original}")
    elif len(sources) > 1:
        evidence.append(f"several original paths: {', '.join(sources)}")
    exact = workspace.by_name.get(unit, [])
    folded = workspace.by_folded.get(unit.casefold(), [])
    if len(exact) == 1 and len(folded) == 1:
        row.update(workspace_path=exact[0], provisional_file=exact[0], draft_rule="O-provisional")
        evidence.append(f"provisional file {exact[0]} has the unit's exact name")
    elif not folded and original and (module := original_module(original)) and module.casefold() in workspace.directories:
        path = f"{workspace.directories[module.casefold()]}/{unit}"
        row.update(workspace_path=path, draft_rule="O-path")
        evidence.append(f"no provisional file; {original} names module directory {workspace.directories[module.casefold()]}")
    else:
        row["draft"] = DRAFT_OPEN
        if folded:
            evidence.append(f"provisional files of that name in another letter case or several places: {', '.join(folded)}")
        else:
            evidence.append("no provisional file and no existing module directory from an original path: choose the workspace path")
    row["evidence"] = evidence
    return row


def _header_emits(draft: _Draft, workspace: _Workspace, owners: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    emits = []
    undecided = []
    for owner in owners:
        if owner.get("classification") != "authored":
            continue
        for value in owner["artifacts"]:
            identity = artifact_id(value)
            row = draft.by_id[identity]
            header = row.get("emitted_from_header")
            if row["kind"] != "function" or not header:
                continue
            reason = _emit_reason(row)
            name = PureWindowsPath(header.replace("/", "\\")).name
            verdict = path_library(header)
            evidence = [f"dwarf-cu-header {header}"]
            if reason is None:
                undecided.append(identity)
                continue
            if verdict and verdict[0] == "provider" and verdict[1]:
                emits.append({"artifact": identity, "header": f"<{name}>", "library": verdict[1], "reason": reason,
                              "evidence": evidence, "draft_rule": "H-dwarf-header"})
                continue
            module = original_module(header) if not verdict or verdict[0] == "authored" else None
            spelled = workspace.directories.get(module.casefold()) if module else None
            path = f"{spelled}/{name}" if spelled else None
            if path and workspace.exact_file(path):
                emits.append({"artifact": identity, "header": path, "reason": reason, "evidence": evidence,
                              "draft_rule": "H-dwarf-header"})
            else:
                undecided.append(identity)
    return emits, undecided


# -- check -----------------------------------------------------------------------


def _owner_key(owner: dict[str, Any]) -> tuple[str, str | None]:
    classification = owner.get("classification")
    if classification == "provider":
        member = owner.get("archive_member") or {}
        return ("provider", member.get("gnu_object") or f"{owner.get('library')}:{member.get('object')}")
    if classification == "authored":
        return ("authored", str(owner.get("translation_unit") or "").casefold())
    return (str(classification), str(owner.get("translation_unit") or "").casefold() or None)


ROW_FIELDS = ("translation_unit", "classification", "workspace_path", "original_path", "provisional_file", "library", "archive_member")
EMIT_ROW_FIELDS = ("header", "reason", "library")


def _flat(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """The compared fields of a row, an ``archive_member`` object spread to ``archive_member.<key>``."""

    out: dict[str, Any] = {}
    for field in fields:
        value = row.get(field)
        if isinstance(value, dict):
            for key in sorted(value):
                out[f"{field}.{key}"] = value[key]
        else:
            out[field] = value
    return out


def _field_changes(draft: dict[str, Any], plan: dict[str, Any], fields: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    before, after = _flat(draft, fields), _flat(plan, fields)
    return {
        key: {"draft": before.get(key), "plan": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def _owner_label(owner: dict[str, Any]) -> str:
    member = owner.get("archive_member") if isinstance(owner.get("archive_member"), dict) else {}
    name = owner.get("translation_unit") or member.get("gnu_object") or member.get("object")
    return f"{owner.get('classification')} {name}" if name else str(owner.get("classification"))


def _row_changes(fresh: dict[str, Any], plan: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Owner and header-emit rows of the plan that differ from the fresh draft's, for the reviewer.

    A row the plan keeps with its ``draft_rule`` is proven (or a problem)
    and is not listed.  Listed: a row whose ``draft_rule`` the plan removed,
    a row the draft left open that the plan decided, a row whose compared
    fields differ, a plan row the draft has no row for (``hand-row``) and a
    draft row the plan dropped (``dropped``).  ``fields`` maps each changed
    field to its draft and plan value.
    """

    def changes(fresh_rows: dict[Any, dict[str, Any]], plan_rows: list[tuple[Any, dict[str, Any]]], fields, label):
        found = []
        kept = set()
        for key, row in plan_rows:
            kept.add(key)
            if row.get("draft_rule"):
                continue
            draft = fresh_rows.get(key)
            if draft is None:
                found.append({"row": label(row), "change": ["hand-row"], "draft_rule": None, "fields": {}})
                continue
            changed = _field_changes(draft, row, fields)
            kinds = []
            if draft.get("draft_rule"):
                kinds.append("draft_rule-removed")
            if draft.get("draft") == DRAFT_OPEN:
                kinds.append("decided-open-row")
            if changed:
                kinds.append("fields")
            if changed or draft.get("draft_rule"):
                found.append({"row": label(row), "change": kinds, "draft_rule": draft.get("draft_rule"), "fields": changed})
        for key, draft in fresh_rows.items():
            if key not in kept:
                found.append({"row": label(draft), "change": ["dropped"], "draft_rule": draft.get("draft_rule"), "fields": {}})
        return found

    fresh_owners = {_owner_key(row): row for row in fresh.get("owners") or []}
    plan_owners = [(_owner_key(row), row) for row in plan.get("owners") or [] if isinstance(row, dict)]
    fresh_emits = {row["artifact"]: row for row in fresh.get("header_emits") or []}
    plan_emits = [(row.get("artifact"), row) for row in plan.get("header_emits") or [] if isinstance(row, dict)]
    return (
        changes(fresh_owners, plan_owners, ROW_FIELDS, _owner_label),
        changes(fresh_emits, plan_emits, EMIT_ROW_FIELDS, lambda row: f"header_emits {row.get('artifact')}"),
    )


def check_draft(fresh: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Compare a plan's drafted rows with a fresh draft of the same rules.

    Problems: an entry, owner row or header-emit row that carries a
    ``draft_rule`` but differs from what the rules give (or that the rules
    leave open).  Overrides (for the reviewer, not problems): artifacts the
    rules decide that the plan places by hand elsewhere.  Hand-decided
    entries without a ``draft_rule`` are what the reviewer reviews.
    ``owner_changes`` and ``header_emit_changes`` list the rows that differ
    from the fresh draft's (``_row_changes``), so a reviewer need not
    regenerate the draft by hand.
    """

    problems: list[str] = []
    expected: dict[str, tuple[tuple[str, str | None], dict[str, Any]]] = {}
    fresh_rows = {}
    for owner in fresh.get("owners") or []:
        key = _owner_key(owner)
        fresh_rows[key] = owner
        for value in owner["artifacts"]:
            expected[value["artifact"]] = (key, value)
    drafted = hand = 0
    overrides = []
    for owner in plan.get("owners") or []:
        if not isinstance(owner, dict):
            continue
        key = _owner_key(owner)
        if owner.get("draft_rule"):
            other = fresh_rows.get(key)
            if other is None or other.get("draft_rule") != owner["draft_rule"]:
                problems.append(f"owner {key[1]}: claims {owner['draft_rule']} but the rules give no such row")
            elif any(owner.get(field) != other.get(field) for field in ROW_FIELDS):
                problems.append(f"owner {key[1]}: differs from its {owner['draft_rule']} draft (remove draft_rule to own it by hand)")
        for value in owner.get("artifacts") or []:
            identity = artifact_id(value)
            if identity is None:
                continue
            rule = value.get("draft_rule") if isinstance(value, dict) else None
            wanted = expected.get(identity)
            if rule:
                drafted += 1
                if wanted is None:
                    problems.append(f"{identity}: claims {rule} but the rules leave it open")
                elif (wanted[0], wanted[1]["draft_rule"], wanted[1]["confidence"]) != (key, rule, value.get("confidence")):
                    problems.append(f"{identity}: differs from its {wanted[1]['draft_rule']} draft ({wanted[0][1]}, {wanted[1]['confidence']})")
            else:
                hand += 1
                if wanted is not None and wanted[0] != key:
                    overrides.append(f"{identity}: the rules give {wanted[0][1]} ({wanted[1]['draft_rule']}), the plan {key[1]}")
    for row in plan.get("unresolved") or []:
        identity = row.get("artifact") if isinstance(row, dict) else None
        if identity in expected:
            overrides.append(f"{identity}: the rules give {expected[identity][0][1]} ({expected[identity][1]['draft_rule']}), the plan leaves it unresolved")
    fresh_emits = {row["artifact"]: row for row in fresh.get("header_emits") or []}
    for emit in plan.get("header_emits") or []:
        if not isinstance(emit, dict) or not emit.get("draft_rule"):
            continue
        other = fresh_emits.get(emit.get("artifact"))
        if other is None or any(emit.get(field) != other.get(field) for field in ("header", "reason", "library", "draft_rule")):
            problems.append(f"header_emits {emit.get('artifact')}: differs from its {emit['draft_rule']} draft")
    owner_changes, emit_changes = _row_changes(fresh, plan)
    return {
        "problems": problems,
        "drafted_entries": drafted,
        "hand_entries": hand,
        "open_rows": sum(1 for row in plan.get("unresolved") or [] if isinstance(row, dict) and row.get("draft") == DRAFT_OPEN),
        "overrides": overrides,
        "owner_changes": owner_changes,
        "header_emit_changes": emit_changes,
    }


def plan_rules_version(plan: dict[str, Any]) -> int:
    """The rules version ``source plan draft --check`` uses for a plan when ``--rules`` is not given.

    A plan keeps the rules it was drafted under (its ``draft.rules_version``):
    a version 1 plan is checked under 1 after version 2 became the default.
    A plan with no recorded version predates version 2 and is checked under 1.
    """

    draft = plan.get("draft") if isinstance(plan.get("draft"), dict) else {}
    recorded = draft.get("rules_version")
    if recorded is None:
        return UNVERSIONED_RULES
    if isinstance(recorded, int) and not isinstance(recorded, bool) and recorded in RULES_VERSIONS:
        return recorded
    raise SocomError(f"the plan's draft rules_version {recorded!r} is not one of {', '.join(map(str, RULES_VERSIONS))}")


def compare_plans(fresh: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Per-artifact agreement of a hand plan with a draft (calibration)."""

    def owners(document: dict[str, Any]) -> dict[str, tuple[str, str | None]]:
        found = {}
        for owner in document.get("owners") or []:
            for value in owner.get("artifacts") or []:
                identity = artifact_id(value)
                if identity:
                    found[identity] = _owner_key(owner)
        return found

    drafted, planned = owners(fresh), owners(plan)
    agree, disagree, open_planned, open_both = [], [], [], []
    open_ids = {row["artifact"] for row in fresh.get("unresolved") or []}
    for identity in sorted(set(drafted) | open_ids | set(planned), key=lambda value: int(value.rsplit(":", 1)[1], 16)):
        if identity in drafted:
            if identity not in planned:
                disagree.append(f"{identity}: draft {drafted[identity][1]}, plan unresolved or absent")
            elif drafted[identity] == planned[identity]:
                agree.append(identity)
            else:
                disagree.append(f"{identity}: draft {drafted[identity][1]}, plan {planned[identity][1]}")
        elif identity in open_ids:
            (open_planned if identity in planned else open_both).append(identity)
    return {"agree": len(agree), "disagree": disagree, "open_planner_owned": len(open_planned), "open_planner_unresolved": len(open_both)}
