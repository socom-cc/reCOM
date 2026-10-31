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

Rules version 2 (a plan is checked under the version it was drafted with)
changes two rules and keeps every other one:

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

Rules version 3 adds provider-scope rules and LOCAL section containment, and
keeps every other rule:

P-mw-unit       (row) in a provider plan, a Metrowerks-compiled provider unit
                of the plan's library (a provider path or a known unit name,
                such as 989snd.c) whose artifacts the unit rules decide gets a
                provider row: ``translation_unit``, its single provider path,
                ``archive_member.object`` ``<stem>.o`` (Metrowerks names an
                object after its source file) and ``linked: "unknown"``.  Its
                artifacts are decided by the anchors (``A-file-string``,
                ``A-local-block``, ...), ``A-between`` and ``D-referenced``,
                whose provider-scope versions accept functions and data the
                graph classifies as that same library.
P-gnu-data      data the graph places in no GNU object's cluster but inside
                one GNU object's LOCAL section run (``gnu_objects[].sections``:
                from its LOCAL SECTION symbol to the next input section) is
                that object's (high; medium when the run was cut short by
                another object's artifact or its window's end) before the
                "referenced only by" fallback, which applies only to data no
                run contains.  A cluster and a run naming different objects
                leave the datum open.
P-gnu-section   a non-padding gap inside one GNU object's LOCAL section run
                whose every relocation comes from that object's functions
                through its own LOCAL section symbols is that object's (high).

Rules version 4 (the default) decides unanchored runs between two units by
three ELF regularities that have no counterexample on the reference graph
``7bd4e540``, iterates them to a fixed point, keeps every version 3 rule, and
adds suggestions and header-emit rules.  The regularities (``_v4_functions``):

R1 kept copy    no reference to an inline (binding 13) or WEAK function comes
                from a function of another object placed before it: the
                linker keeps the first definer's copy (0 of 2609 cross-unit
                references between anchored functions; 496 same-unit
                references run forwards).  So a function calling a copy placed
                after it is in that copy's object, and so is everything in
                between.
R3 key function a GLOBAL vtable is emitted with its key function, one of its
                class's own non-inline virtuals (every one of the 162 GLOBAL
                vtables has one; the 75 without are binding 13; 11 of 11
                anchored single-candidate pairs agree, and an anchored
                vtable's unit is among its anchored candidates' units 78 of
                78 times).
R4 contiguity   an object's ``.text`` is contiguous (0 interleavings among
                2836 anchored functions).

A-kept-copy     (medium) R1: every function a call to a later copy spans
                (spans sharing a function merged) takes the one unit decided
                inside the span.
A-vtable-key    (medium) R3: the one own non-inline virtual of an anchored
                GLOBAL vtable that no rule decides for another unit is the
                vtable's unit; an unanchored GLOBAL vtable whose own non-inline
                virtuals are all decided for one unit is that unit.  A vtable
                ``D-referenced`` decides does not count (3 of 56 anchored
                vtables are read only by another unit's inline ctor/dtor
                copies).
A-contiguity    (medium) R4: a function strictly between two functions decided
                for the same unit is that unit's.
Each needs an authored unit and, for every function it decides or spans, no
GNU object start, no conflicting anchors, no provider-proven function and no
strong or medium candidate of another unit; ``D-referenced`` then runs on the
fixed point (it feeds nothing back).

Rules 5 keep every version 4 rule except that neither ``D-referenced`` nor
the "referenced only by" fallback of ``P-gnu-data`` decides a COMMON variable
(the graph's ``common``: linker-allocated, no defining section). Being read by
one object's functions does not name its definer (a tentative definition can
sit in a file that never reads it; Medius allocates one DME block across four
objects), so the row stays open with that reason and, in authored plans, an
``S-sole-referencer`` suggestion.

R2 (a WEAK copy closes its object) is not a rule: ``swap<Ui>`` 0x172ac0, WEAK
and DWARF-placed in database.cpp, precedes database.cpp's GLOBAL
``LoadWorld`` 0x172b60 (1 of 162 anchored WEAK functions), and every positive
use of it could be confused with an unnamed object between the two units
(segment 027 has one).  It only feeds ``S-weak-order``.

Suggestions (``suggest`` on an open row: ``{owner, rule, confidence,
basis}``; never a decision, ``--check`` ignores them):
S-sole-referencer  an open inline/WEAK copy every referencing function of
                   which (through data, including its ``__sinit``) is decided
                   for one unit; medium when that unit flanks the copy's run.
                   For open data: every referencing function is decided or
                   suggested for one unit (the weakest confidence).
S-class-flank      the function's mangled class has decided members in exactly
                   one of the two flanking units (medium when the class has no
                   decided member elsewhere).
S-weak-order       a WEAK copy with only inline/WEAK copies between it and the
                   left unit's last decided function (left unit), or a GLOBAL
                   after such a WEAK copy (right unit, unless an unnamed object
                   lies between); low.
Disagreeing suggestions keep the first in that order, at low confidence.

C-fill          also zero (or ``.bss``) fill of any size, without labels or
                relocations, that ends exactly at a GNU object start or LOCAL
                section run start and is smaller than that address's
                alignment (0x15b0cc: 52 bytes before 256-aligned 0x15b100).
P-gnu-section   also accepts relocations from data of the object's own LOCAL
                section runs (SCE 0x446d70, newlib's lconv 0x466e60).
H-template-family  an owned MSL template instance (inline or WEAK; an MSL
                classification or a ``std``/``Metrowerks`` qualifier) without
                a header compile unit of its own emits from the MSL header that
                every other instance of its class (or function) template with
                a header compile unit names (``<vector>``); disagreeing or no
                such instances leave the emit open with that reason.
H-class-header  an owned implicit special member (``__ct__``, ``__dt__``,
                ``__as__``; inline or WEAK) of an authored class without a
                header compile unit of its own emits from the one existing
                workspace header that the header compile units of the class's
                other members name.

Rules 6 (the default) keep every version 5 rule except:

D-referenced    (authored and provider-unit) and the "referenced only by"
P-gnu-data      fallback decide GLOBAL data only when its position agrees:
                it lies strictly inside the unit's (object's) own data run of
                its output-section region, between the nearest data artifacts
                before and after it that an anchor or containment rule places
                (unit anchors; a GNU cluster, LOCAL section run or data-only
                object), both of that unit.  A GLOBAL can be defined in a file
                that never reads it (CVisual's statics, read only by
                database.cpp, lie between zvid_init.cpp and vis_main.cpp
                data).  LOCAL and binding-13 data are decided as before.  A
                region ends at a window edge, a GNU section envelope change,
                a linker section symbol (``__data_end``, ``__bss_start``) and
                where file bytes end.  Otherwise the row stays open with the
                flanks in its reason and, in authored plans, an
                ``S-sole-referencer`` suggestion (low when a flank names
                another owner; COMMON rows get one too).
S-sole-referencer  copies: what references the copy counts by its own unit
                when it is a decided data artifact (a GLOBAL vtable emitted
                with its key function), else through the functions reading
                it; the copy's references back to itself do not count.  The
                first definer keeps a copy, so a copy placed before the
                referencing unit's first decided function gets the suggestion
                only when that function is the next decided one (the unit's
                object can start at it); otherwise none.
S-class-flank,  never point past an undecided function of a unit-less
S-weak-order    (unnamed) cluster lying between the function and that flank.
H-template-family  also LOCAL MSL function template instances, keyed by
                overload (each parameter's class template, ``*`` otherwise:
                ``swap(__vector_deleter&, ...)`` is ``<vector>``'s, the
                generic ``swap(T&, T&)`` ``<msl_utility>``'s): the one MSL
                header the overload's instances with a header compile unit
                name, or, when none has one, MSL's defining header
                (``MSL_FUNCTION_TEMPLATE_HEADERS``: ``find``, ``remove_copy``,
                ... in ``<algorithm>``) when every instance of the template
                with a header compile unit names it too.
``draft.open_row_header_emits`` (authored scopes) lists the emit each open
function takes once a planner owns it in an authored unit; ``--check``
proves such an emit row of a hand-owned function like a drafted one.
"""

from __future__ import annotations

import bisect
import os
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable

from .constants import REFERENCE_SHA256
from .mwdemangle import demangle, readable_qualified, template_base
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

DRAFT_RULES_VERSION = 6
RULES_VERSIONS = (1, 2, 3, 4, 5, 6)
# The version a plan without a recorded (known) draft rules version is checked under.
UNVERSIONED_RULES = 1
ANCHOR_ORDER = ("A-dwarf-cu", "A-dwarf-header", "A-sinit", "A-unnamed", "A-dwarf-static", "A-file-string", "A-local-block")
FILL_ROW = "compiler-generated"
# A DWARF producer of the project's own (Metrowerks) toolchain.
TOOLCHAIN_PRODUCER = re.compile(r"^(?:Metrowerks|MW)\b")
COPY_BINDINGS = frozenset({"WEAK", "13"})
# Namespaces of MSL's template code (rules 4, H-template-family).
MSL_NAMESPACES = frozenset({"std", "Metrowerks"})
SPECIAL_MEMBERS = ("__ct__", "__dt__", "__as__")
# Rules 4 suggestions, in the order a disagreement keeps.
SUGGEST_ORDER = ("S-sole-referencer", "S-class-flank", "S-weak-order")
# Rules 6: linker-defined symbols that open or close an output section (a data region barrier).
SECTION_BOUNDARY_SYMBOLS = frozenset({
    "_dataStart", "__data_start", "__data_end", "_fdata", "_edata", "_fsdata", "_esdata",
    "_fbss", "_fsbss", "_esbss", "__bss_start", "__bss_end", "_heapStart", "_end", "end",
})
# Rules 6 (H-template-family): the MSL header that defines each non-member function
# template (MSL_C++ MSL_Common/Include); used only when no instance of the overload
# has a header compile unit and every instance of the template that has one agrees.
MSL_FUNCTION_TEMPLATE_HEADERS = {
    ("std", name): "algorithm"
    for name in (
        "find", "find_if", "remove_copy", "remove_copy_if", "remove_if", "transform", "sort", "__sort132",
        "__selection_sort", "lower_bound", "push_heap", "pop_heap", "__insert_heap_down",
    )
} | {("std", "__advance"): "iterator"}


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
        # Each relocation reaching an artifact: (site, symbol index, symbol type).
        self.reaching: dict[str, list[tuple[str, Any, Any]]] = defaultdict(list)
        for reference in facts.get("references") or []:
            site, target = reference.get("site_artifact"), reference.get("target_artifact")
            if site and target and site != target:
                self.users[target].add(site)
                self.uses[site].add(target)
                self.reaching[target].append((site, reference.get("symbol_index"), reference.get("symbol_type")))
        # LOCAL section runs of the GNU function objects (rules 3), by start address.
        self.runs = sorted(
            (_hex_int(run["start"]), _hex_int(run["end"]), run, row["address"])
            for row in graph.get("gnu_objects") or []
            if not row.get("data_only")
            for run in row.get("sections") or []
        )
        self.run_starts = [run[0] for run in self.runs]
        # Where a GNU input section starts: an object's .text symbol or a LOCAL section run (rules 4, C-fill).
        self.section_starts = set(self.gnu_starts) | {
            _hex_int(run["start"]) for row in graph.get("gnu_objects") or [] for run in row.get("sections") or []
        }
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
        self.anchored = dict(self.decided)
        # Rules 6: data a referenced-only rule would decide but its position or COMMON
        # allocation withholds: identity -> (referencing unit, basis, whether position conflicts).
        self.withheld: dict[str, tuple[str, str, bool]] = {}
        self._between()
        if self.rules >= 4:
            self._v4_functions()

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
                if strong_provider(row, self.unit_library) not in self.own_library(unit):
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
            if strong_provider(other, self.unit_library) not in self.own_library(unit):
                return False
            if any(
                candidate["tu"].casefold() != unit and candidate["strength"] in ("strong", "medium")
                for candidate in other.get("tu_candidates") or []
            ):
                return False
        return True

    def own_library(self, unit: str) -> tuple[str | None, ...]:
        """Provider libraries ``A-between`` accepts between two anchors of ``unit``.

        Rules 3 (provider scope): functions the graph proves code of the
        unit's own provider library; before, none.
        """

        library = self.unit_library.get(unit.casefold())
        return (None, library) if self.rules >= 3 and library else (None,)

    # -- rules 4: unanchored runs ----------------------------------------------

    def authored_unit(self, unit: str) -> bool:
        return unit.casefold() not in self.unit_library

    def mark(self, identity: str) -> str | None:
        """The casefolded unit a function is decided for, ``?`` for conflicting anchors, else ``None``."""

        decided = self.decided.get(identity)
        if decided is not None:
            return decided[0].casefold()
        return "?" if len(self.conflict(identity)) > 1 else None

    def admissible(self, identity: str, unit: str) -> bool:
        """Rules 4: nothing about an undecided function contradicts ``unit`` (casefolded)."""

        row = self.by_id[identity]
        if row.get("gnu_object") or _hex_int(row["address"]) in self.gnu_starts or len(self.conflict(identity)) > 1:
            return False
        if strong_provider(row, self.unit_library) not in self.own_library(unit):
            return False
        return not any(
            candidate["tu"].casefold() != unit and candidate["strength"] in ("strong", "medium")
            for candidate in row.get("tu_candidates") or []
        )

    def _span_ok(self, functions: list[str], low: int, high: int, unit: str) -> bool:
        """Every function of ``functions[low..high]`` is decided for ``unit`` or admissible; no GNU object starts after ``low``."""

        for order in range(low, high + 1):
            identity = functions[order]
            if order > low and _hex_int(self.by_id[identity]["address"]) in self.gnu_starts:
                return False
            mark = self.mark(identity)
            if mark != unit and (mark is not None or not self.admissible(identity, unit)):
                return False
        return True

    def _v4_functions(self) -> None:
        """Rules 4: ``A-kept-copy``, ``A-vtable-key`` and ``A-contiguity`` to a fixed point."""

        self.copy_spans = self._copy_spans()
        self.vtables = self._vtables()
        changed = True
        while changed:
            changed = self._kept_copy() | self._vtable_key() | self._contiguity()

    def _copy_spans(self) -> dict[str, list[tuple[int, int, tuple[str, str]]]]:
        """Per code window, the merged spans (window orders) of calls to an inline/WEAK copy placed after the caller.

        A span keeps its first call as the cited link; spans sharing a
        function are one object, so they merge.
        """

        links: dict[str, set[tuple[int, int, str, str]]] = defaultdict(set)
        for target, sites in self.users.items():
            row = self.by_id.get(target)
            if row is None or row["kind"] != "function" or not self.bindings(row) & COPY_BINDINGS:
                continue
            for site in sites:
                caller = self.by_id[site]
                if caller["kind"] == "function" and caller["window"] == row["window"]:
                    low, high = self.window_order[site], self.window_order[target]
                    if low < high:
                        links[row["window"]].add((low, high, site, target))
        spans: dict[str, list[tuple[int, int, tuple[str, str]]]] = {}
        for window in sorted(links):
            merged: list[tuple[int, int, tuple[str, str]]] = []
            for low, high, site, target in sorted(links[window]):
                if merged and low <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], high), merged[-1][2])
                else:
                    merged.append((low, high, (site, target)))
            spans[window] = merged
        return spans

    def _kept_copy(self) -> bool:
        changed = False
        for window, spans in self.copy_spans.items():
            functions = self.windows[window]
            for low, high, (site, target) in spans:
                marks = {self.mark(functions[order]) for order in range(low, high + 1)} - {None}
                if len(marks) != 1 or "?" in marks:
                    continue
                unit = next(iter(marks))
                if not self.authored_unit(unit) or not self._span_ok(functions, low, high, unit):
                    continue
                holder = next(functions[order] for order in range(low, high + 1) if self.mark(functions[order]) == unit)
                spelled = self.decided[holder][0]
                basis = (
                    f"kept copy: {site} calls the inline/WEAK copy {target} placed after it, so {functions[low]}.."
                    f"{functions[high]} are one object, which holds {holder} ({spelled})"
                )
                for order in range(low, high + 1):
                    if functions[order] not in self.decided:
                        self.decided[functions[order]] = (spelled, "A-kept-copy", basis, "medium")
                        changed = True
        return changed

    def _contiguity(self) -> bool:
        changed = False
        for functions in self.windows.values():
            previous = None
            for order, identity in enumerate(functions):
                mark = self.mark(identity)
                if mark is None:
                    continue
                if (
                    previous is not None
                    and order - previous > 1
                    and mark != "?"
                    and self.mark(functions[previous]) == mark
                    and self.authored_unit(mark)
                    and self._span_ok(functions, previous, order, mark)
                ):
                    spelled = self.decided[functions[previous]][0]
                    basis = f"contiguous .text: strictly between {functions[previous]} and {identity}, both decided {spelled}"
                    for between in functions[previous + 1 : order]:
                        self.decided[between] = (spelled, "A-contiguity", basis, "medium")
                    changed = True
                previous = order
        return changed

    def _vtables(self) -> list[tuple[str, str, list[str]]]:
        """(GLOBAL vtable, its name, its class's own non-inline virtuals in address order)."""

        found = []
        for row in self.rows:
            if row["kind"] != "data":
                continue
            names = [item for item in row.get("names") or [] if str(item.get("name") or "").startswith("__vt__")]
            if len(names) != 1 or names[0].get("binding") != "GLOBAL":
                continue
            owner = _qualifier(names[0]["name"])
            if not owner:
                continue
            own = [
                target
                for target in sorted(self.uses.get(row["id"], ()), key=self.position.__getitem__)
                if self.by_id[target]["kind"] == "function"
                and not self.bindings(self.by_id[target]) & COPY_BINDINGS
                and any(_qualifier(item.get("name")) == owner for item in self.by_id[target].get("names") or [])
            ]
            found.append((row["id"], names[0]["name"], own))
        return found

    def _vtable_key(self) -> bool:
        changed = False
        for vtable, name, own in self.vtables:
            if not own:
                continue
            anchored = self.anchored.get(vtable)
            if anchored is not None:
                unit = anchored[0].casefold()
                if not self.authored_unit(unit):
                    continue
                # The key function is an own non-inline virtual of the vtable's unit.
                remaining = [value for value in own if (self.decided.get(value) or anchored)[0].casefold() == unit]
                if len(remaining) == 1 and remaining[0] not in self.decided and self.admissible(remaining[0], unit):
                    basis = (
                        f"vtable key function: the one own non-inline virtual of {name} ({vtable}, anchored "
                        f"{anchored[0]}) that no rule places in another unit"
                    )
                    self.decided[remaining[0]] = (anchored[0], "A-vtable-key", basis, "medium")
                    changed = True
            elif vtable not in self.decided and not self.anchor.get(vtable):
                units = {(self.decided.get(value) or ("",))[0].casefold() for value in own}
                row = self.by_id[vtable]
                if len(units) != 1 or "" in units or row.get("gnu_object") or strong_provider(row, self.unit_library) is not None:
                    continue
                unit = next(iter(units))
                if self.authored_unit(unit):
                    spelled = self.decided[own[0]][0]
                    basis = f"vtable key function: every own non-inline virtual of {name} ({len(own)}) is decided {spelled}"
                    self.decided[vtable] = (spelled, "A-vtable-key", basis, "medium")
                    changed = True
        return changed

    # -- rules 4: suggestions ----------------------------------------------------

    def flanks(self, identity: str) -> tuple[str | None, str | None]:
        """The nearest decided functions before and after a function in its code window."""

        functions = self.windows[self.by_id[identity]["window"]]
        order = self.window_order[identity]
        left = next((functions[k] for k in range(order - 1, -1, -1) if functions[k] in self.decided), None)
        right = next((functions[k] for k in range(order + 1, len(functions)) if functions[k] in self.decided), None)
        return left, right

    def class_units(self) -> dict[tuple[str, ...], Counter[str]]:
        if not hasattr(self, "_class_units"):
            found: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
            for identity, decided in self.decided.items():
                row = self.by_id[identity]
                if row["kind"] == "function" and (owner := _class_of(row)):
                    found[owner][decided[0].casefold()] += 1
            self._class_units = dict(found)
        return self._class_units

    def suggest_function(self, identity: str) -> dict[str, str] | None:
        """Rules 4: the suggestion for an undecided authored function, if any."""

        if not hasattr(self, "_suggested"):
            self._suggested: dict[str, dict[str, str] | None] = {}
        if identity not in self._suggested:
            self._suggested[identity] = self._suggest_function(identity)
        return self._suggested[identity]

    def _suggest_function(self, identity: str) -> dict[str, str] | None:
        row = self.by_id[identity]
        if (
            row["kind"] != "function" or identity in self.decided or row.get("gnu_object") or len(self.conflict(identity)) > 1
            or strong_provider(row, self.unit_library) is not None
        ):
            return None
        left, right = self.flanks(identity)
        flank = {side: self.decided[value][0] for side, value in (("left", left), ("right", right)) if value}
        flank_units = {value.casefold() for value in flank.values()}
        found: list[tuple[str, str, str, str]] = []
        bindings = self.bindings(row) - {None}
        v6 = self.rules >= 6
        # Rules 6: a flank only counts when no unit-less (unnamed) object's function lies between.
        reachable = {side: value for side, value in (("left", left), ("right", right))
                     if value and not (v6 and self.unitless_between(identity, value))}
        if bindings & COPY_BINDINGS:
            if v6:
                referrers, via_gap = self.copy_referrers(identity)
            else:
                users, via_gap = self.function_users(identity)
                referrers = {user: (self.decided.get(user) or ("",))[0] for user in users}
            users = set(referrers)
            units = {unit.casefold() for unit in referrers.values()}
            if users and not via_gap and len(units) == 1 and "" not in units and self.authored_unit(next(iter(units))):
                spelled = referrers[min(users, key=self.position.__getitem__)]
                first = self.first_function(spelled.casefold(), row["window"]) if v6 else None
                counted = f"{len(users)} referrer(s): functions, decided data by its own unit" if v6 else f"{len(users)} function(s)"
                basis = (
                    f"only {spelled} references this inline/WEAK copy ({counted}); only a referencing "
                    "object defines a copy and the first definer keeps it"
                )
                if first is not None and self.window_order[identity] < first:
                    # Rules 6: the kept copy is the earliest definer's.  Placed before the
                    # referencing unit's first decided function, it is that unit's only
                    # if the unit's object can start at it: that function is the next
                    # decided one (``right``); otherwise an earlier object holds it.
                    if right is not None and right == self.windows[row["window"]][first] and "right" in reachable:
                        found.append((
                            "S-sole-referencer", spelled, "medium",
                            f"{basis}; it lies before {spelled}'s first decided function {right}, with nothing decided "
                            f"between, so {spelled}'s object can start at it",
                        ))
                else:
                    found.append(("S-sole-referencer", spelled, "medium" if spelled.casefold() in flank_units else "low", basis))
        owner = _class_of(row)
        if owner and len(flank_units) == 2:
            members = self.class_units().get(owner, Counter())
            matching = [value for value in flank.values() if members.get(value.casefold())]
            side = next((key for key, value in flank.items() if matching and value == matching[0]), None)
            if len(matching) == 1 and (not v6 or side in reachable):
                spelled = matching[0]
                elsewhere = sum(count for unit, count in members.items() if unit != spelled.casefold())
                found.append((
                    "S-class-flank", spelled, "low" if elsewhere else "medium",
                    f"class {readable_qualified(list(owner))} has {members[spelled.casefold()]} decided member(s) in "
                    f"{spelled}, none in the other flanking unit" + (f", {elsewhere} in other units" if elsewhere else ""),
                ))
        if left is not None:
            functions = self.windows[row["window"]]
            between = functions[self.window_order[left] + 1 : self.window_order[identity]]
            if "WEAK" in bindings and all(self.bindings(self.by_id[value]) & COPY_BINDINGS for value in between):
                if "left" in reachable:
                    found.append((
                        "S-weak-order", flank["left"], "low",
                        f"WEAK copy with only inline/WEAK copies after {left} ({flank['left']}): WEAK copies usually close "
                        "their object (161 of 162 anchored)",
                    ))
            elif bindings == {"GLOBAL"} and right is not None and len(flank_units) == 2:
                weak = next((value for value in [left, *between] if "WEAK" in self.bindings(self.by_id[value])), None)
                if weak is not None and "right" in reachable:
                    found.append((
                        "S-weak-order", flank["right"], "low",
                        f"GLOBAL after the WEAK copy {weak}, which usually closes its object: {flank['right']} unless "
                        "an unnamed object lies between",
                    ))
        return _combined(found)

    def suggest_data(self, identity: str) -> dict[str, str] | None:
        """Rules 4: ``S-sole-referencer`` for open data whose referencing functions are decided or suggested for one unit."""

        row = self.by_id[identity]
        if row.get("gnu_object") or len(self.conflict(identity)) > 1 or strong_provider(row, self.unit_library) is not None:
            return None
        if identity in self.decided:
            return None
        if self.rules >= 6 and identity in self.withheld:
            # Rules 6: every referencing function is decided for one unit, but the
            # datum is COMMON or a GLOBAL its position does not confirm.
            unit, reason, conflict = self.withheld[identity]
            if unit.startswith("gnu:") or not self.authored_unit(unit):
                return None
            return {"owner": unit, "rule": "S-sole-referencer", "confidence": "low" if conflict or row.get("common") else "medium",
                    "basis": f"only {unit} references it; {reason}"}
        users, via_gap = self.function_users(identity)
        if not users or via_gap:
            return None
        units: set[str] = set()
        spelled = None
        confidence = "medium"
        suggested = 0
        for user in sorted(users, key=self.position.__getitem__):
            if user in self.decided:
                unit = self.decided[user][0]
            else:
                suggestion = self.suggest_function(user)
                if suggestion is None:
                    return None
                unit = suggestion["owner"]
                suggested += 1
                confidence = max(confidence, suggestion["confidence"], key=CONFIDENCES.index)
            units.add(unit.casefold())
            spelled = spelled or unit
        if len(units) != 1 or not suggested or spelled is None or not self.authored_unit(spelled):
            return None
        basis = f"referenced only by functions of {spelled} ({len(users) - suggested} decided, {suggested} suggested)"
        if self.rules >= 6 and self.global_data(row):
            # Rules 6: a GLOBAL's position, which a sole referrer does not override.
            inside, where, _container = self.data_position(identity, spelled.casefold())
            if not inside:
                if any(flank is not None and flank[1] != spelled.casefold() for flank in self.data_flanks(identity)):
                    confidence = "low"
                basis += f"; GLOBAL not strictly inside its own data run ({where})"
        return {"owner": spelled, "rule": "S-sole-referencer", "confidence": confidence, "basis": basis}

    # -- rules 4: header emits of instances without a header compile unit -------

    def family_headers(self) -> tuple[dict[tuple[str, ...], dict[str, list[str]]], dict[tuple[str, ...], dict[str, list[str]]]]:
        """(template family -> header path -> functions, class qualifier -> header path -> functions) over the graph."""

        if not hasattr(self, "_family_headers"):
            families: dict[tuple[str, ...], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
            classes: dict[tuple[str, ...], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
            for row in self.rows:
                header = row.get("emitted_from_header") if row["kind"] == "function" else None
                if not header:
                    continue
                if family := _template_family(row):
                    families[family][header].append(row["id"])
                if owner := _qualifier_of(row):
                    classes[owner][header].append(row["id"])
            self._family_headers = (dict(families), dict(classes))
        return self._family_headers

    def overload_headers(self) -> tuple[dict[Any, dict[str, list[str]]], dict[tuple[str, ...], dict[str, list[str]]]]:
        """Rules 6: (function template overload -> header -> functions, function template -> header -> functions)."""

        if not hasattr(self, "_overload_headers"):
            overloads: dict[Any, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
            templates: dict[tuple[str, ...], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
            for row in self.rows:
                header = row.get("emitted_from_header") if row["kind"] == "function" else None
                if header and (found := _function_template(row)):
                    overloads[found][header].append(row["id"])
                    templates[found[0]][header].append(row["id"])
            self._overload_headers = (dict(overloads), dict(templates))
        return self._overload_headers

    def containing_run(self, row: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
        """(LOCAL section run, GNU object address) whose extent holds the whole artifact (rules 3)."""

        start = _hex_int(row["address"])
        end = start + int(row.get("size") or 0)
        position = bisect.bisect_right(self.run_starts, start) - 1
        if position < 0:
            return None
        low, high, run, address = self.runs[position]
        if low <= start and end <= high:
            return run, address
        return None

    def aligned_fill(self, row: dict[str, Any]) -> str | None:
        """Rules 4: the basis of a zero fill gap that aligns the GNU input section starting where it ends."""

        size = int(row.get("size") or 0)
        if row.get("labels") or row.get("fill") not in ("zero", "nobits") or self.reaching.get(row["id"]):
            return None
        end = _hex_int(row["address"]) + size
        alignment = end & -end
        if end not in self.section_starts or not 0 < size < alignment:
            return None
        return f"{row.get('fill')} fill of {size} bytes, no labels or relocations, up to the 0x{alignment:x}-aligned GNU section start 0x{end:x}"

    def toolchain_producer(self, gnu: dict[str, Any]) -> str | None:
        """The project-toolchain DWARF producer of a GNU object's functions or gaps, if any."""

        for identity in [*(gnu.get("functions") or []), *(gnu.get("gaps") or [])]:
            for item in (self.by_id.get(identity) or {}).get("signals") or []:
                producer = item.get("producer")
                if item.get("signal") == "dwarf-cu" and isinstance(producer, str) and TOOLCHAIN_PRODUCER.match(producer):
                    return producer
        return None

    # -- data ------------------------------------------------------------------

    def function_users(self, identity: str, skip: str | None = None) -> tuple[set[str], bool]:
        """(functions referencing ``identity`` through data, whether any site is a gap).

        ``skip`` (rules 6, copies): a function whose references do not count
        (a copy's own references back to itself through data).
        """

        functions: set[str] = set()
        seen = {identity}
        pending = [identity]
        gap = False
        while pending:
            current = pending.pop()
            for site in self.users.get(current, ()):
                kind = self.by_id[site]["kind"]
                if kind == "function":
                    if site == skip:
                        continue
                    functions.add(site)
                elif kind == "gap":
                    gap = True
                elif site not in seen:
                    seen.add(site)
                    pending.append(site)
        return functions, gap

    def copy_referrers(self, identity: str) -> tuple[dict[str, str], bool]:
        """Rules 6: (referencing artifact -> its decided unit or ``""``, whether any site is a gap) of a copy.

        A function site counts by its unit; a decided data site (a GLOBAL
        vtable emitted with its key function, an anchored table) by its own
        unit, not by the functions that read it; an undecided data site by the
        functions referencing it.  The copy's own references back to itself
        through data do not count.
        """

        found: dict[str, str] = {}
        gap = False
        for site in self.users.get(identity, ()):
            kind = self.by_id[site]["kind"]
            if site == identity:
                continue
            if kind == "gap":
                gap = True
            elif kind == "function" or site in self.decided:
                found[site] = (self.decided.get(site) or ("",))[0]
            else:
                users, via_gap = self.function_users(site, skip=identity)
                gap |= via_gap
                found.update({user: (self.decided.get(user) or ("",))[0] for user in users})
                if not users:
                    found[site] = ""
        return found, gap

    def gnu_of_cluster(self, row: dict[str, Any]) -> set[str]:
        cluster = self.clusters.get(row.get("cluster") or "")
        if not cluster:
            return set()
        return {self.by_id[member].get("gnu_object") for member in cluster["members"] if self.by_id[member].get("gnu_object")}

    # -- rules 6: data position ----------------------------------------------------

    def global_data(self, row: dict[str, Any]) -> bool:
        return row["kind"] == "data" and "GLOBAL" in self.bindings(row)

    def data_regions(self) -> dict[str, tuple[int, int]]:
        """Data artifact -> (region, order) in its output-section region, in address order.

        A region ends at a window edge, where the GNU section envelope (or the
        pair of envelopes around it) changes, at a linker section symbol
        (``__data_end``, ``__bss_start``, ...) and where file-backed bytes end
        (NOBITS: the end of the last file-backed gap before the window's first
        ``nobits`` gap).
        """

        if not hasattr(self, "_data_regions"):
            first: dict[str, int] = {}
            for row in self.rows:
                if row["kind"] == "gap" and row.get("fill") == "nobits":
                    first.setdefault(row["window"], _hex_int(row["address"]))
            ends: dict[str, list[int]] = defaultdict(list)
            for row in self.rows:
                limit = first.get(row["window"])
                end = _hex_int(row["address"]) + int(row.get("size") or 0)
                if row["kind"] == "gap" and row.get("fill") in ("zero", "nonzero") and limit is not None and end <= limit:
                    ends[row["window"]].append(end)
            nobits = {window: max(ends[window], default=limit) for window, limit in first.items()}
            regions: dict[str, tuple[int, int]] = {}
            self.region_data: list[list[str]] = []
            previous = None
            for row in self.rows:
                section = row.get("input_section") or {}
                address = _hex_int(row["address"])
                key = (
                    row["window"], section.get("name") or tuple(section.get("between") or ()),
                    row["window"] in nobits and address >= nobits[row["window"]],
                )
                names = {item.get("name") for item in row.get("names") or []} | set(row.get("labels") or [])
                if key != previous or names & SECTION_BOUNDARY_SYMBOLS:
                    self.region_data.append([])
                    previous = key
                if row["kind"] == "data":
                    regions[row["id"]] = (len(self.region_data) - 1, len(self.region_data[-1]))
                    self.region_data[-1].append(row["id"])
            self._data_regions = regions
        return self._data_regions

    def position_owner(self, identity: str) -> str | None:
        """Who an anchor or containment rule places a data artifact with.

        A unit (casefolded) by its unit anchors, ``gnu:<address>`` by a GNU
        object's cluster, LOCAL section run or data-only object, ``?`` when
        these disagree, else ``None``.
        """

        if not hasattr(self, "_position_owners"):
            owners: dict[str, str] = {}
            for row in self.rows:
                if row["kind"] != "data":
                    continue
                found = {unit.casefold() for unit, _rule, _basis in self.anchor.get(row["id"], ())}
                objects = {value for value in self.gnu_of_cluster(row) if value in self.gnu}
                if row.get("gnu_object"):
                    objects.add(row["gnu_object"])
                held = self.containing_run(row)
                if held is not None:
                    objects.add(held[1])
                found |= {f"gnu:{value}" for value in objects}
                if found:
                    owners[row["id"]] = next(iter(found)) if len(found) == 1 else "?"
            self._position_owners = owners
        return self._position_owners.get(identity)

    def owner_label(self, owner: str) -> str:
        if owner.startswith("gnu:"):
            return f"GNU object {owner[4:]}"
        return "conflicting anchors" if owner == "?" else self._spelling(owner)

    def data_position(self, identity: str, owner: str) -> tuple[bool, str, str | None]:
        """(whether data lies strictly inside ``owner``'s own run, the flanks as text, the unit both flanks name).

        Its run: between the nearest data artifacts before and after it in its
        output-section region that an anchor or containment rule places, both
        with ``owner`` (``position_owner`` form).
        """

        left, right = self.data_flanks(identity)

        def side(flank: tuple[str, str] | None, where: str) -> str:
            return f"{flank[0]} ({self.owner_label(flank[1])})" if flank else f"no placed data {where} in its section region"

        text = f"between {side(left, 'before')} and {side(right, 'after')}"
        both = left[1] if left and right and left[1] == right[1] and left[1] != "?" else None
        return both == owner, text, (self.owner_label(both) if both else None)

    def data_flanks(self, identity: str) -> tuple[tuple[str, str] | None, tuple[str, str] | None]:
        """The nearest placed data (artifact, ``position_owner``) before and after a datum in its section region."""

        region, order = self.data_regions()[identity]
        members = self.region_data[region]
        left = next(((value, found) for value in reversed(members[:order]) if (found := self.position_owner(value))), None)
        right = next(((value, found) for value in members[order + 1 :] if (found := self.position_owner(value))), None)
        return left, right

    def withhold(self, identity: str, unit: str, owner: str, users: int, referrer: str) -> str | None:
        """Rules 6: the open reason of GLOBAL data whose position does not confirm its sole referrer, else ``None``."""

        inside, where, _container = self.data_position(identity, owner)
        if inside:
            return None
        conflict = any(flank is not None and flank[1] != owner for flank in self.data_flanks(identity))
        reason = (
            f"GLOBAL data referenced only by {users} function(s) of {referrer}, but not strictly inside its own data "
            f"run ({where}): a GLOBAL can be defined in a file that does not read it"
        )
        self.withheld[identity] = (unit, reason, conflict)
        return reason

    def unitless_between(self, identity: str, flank: str) -> str | None:
        """Rules 6: an undecided function of a cluster without a unit strictly between a function and a flank."""

        functions = self.windows[self.by_id[identity]["window"]]
        low, high = sorted((self.window_order[identity], self.window_order[flank]))
        for value in functions[low + 1 : high]:
            cluster = self.clusters.get(self.by_id[value].get("cluster") or "")
            if value not in self.decided and cluster is not None and not cluster.get("units"):
                return value
        return None

    def first_function(self, unit: str, window: str) -> int | None:
        """Rules 6: the window order of the first function decided for ``unit`` (casefolded) in ``window``."""

        if not hasattr(self, "_first_functions"):
            first: dict[tuple[str, str], int] = {}
            for identity, decided in self.decided.items():
                row = self.by_id[identity]
                if row["kind"] == "function":
                    key = (decided[0].casefold(), row["window"])
                    order = self.window_order[identity]
                    first[key] = min(first.get(key, order), order)
            self._first_functions = first
        return self._first_functions.get((unit, window))


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


def _qualifier(name: Any) -> tuple[str, ...] | None:
    """The Metrowerks qualifier of a mangled function or data name, if it has one."""

    value = demangle(str(name or ""))
    return tuple(value["qualifier"]) if value and value["qualifier"] else None


def _qualifier_of(row: dict[str, Any]) -> tuple[str, ...] | None:
    """The qualifier of a function's first mangled member-function name."""

    for item in row.get("names") or []:
        value = demangle(str(item.get("name") or ""))
        if value and value["qualifier"] and value.get("params") is not None:
            return tuple(value["qualifier"])
    return None


def _class_of(row: dict[str, Any]) -> tuple[str, ...] | None:
    """The authored class (or namespace) a function's mangled name qualifies it with (``S-class-flank``)."""

    owner = _qualifier_of(row)
    return owner if owner and owner[0] not in MSL_NAMESPACES else None


def _template_family(row: dict[str, Any]) -> tuple[str, ...] | None:
    """The class template (or function template) a function instance belongs to, template arguments removed."""

    for item in row.get("names") or []:
        value = demangle(str(item.get("name") or ""))
        if not value or value.get("params") is None:
            continue
        qualifier = value["qualifier"]
        if any("<" in part for part in qualifier):
            return tuple(template_base(part) for part in qualifier)
        if "<" in value["name"]:
            return (*qualifier, template_base(value["name"]))
    return None


def _function_template(row: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Rules 6: (function template, overload) of a non-member function template instance.

    The overload is each parameter's class template (``std::__vector_deleter``),
    ``*`` for any other type: ``swap(__vector_deleter&, ...)`` is defined in
    ``<vector>``, the generic ``swap(T&, T&)`` elsewhere.
    """

    for item in row.get("names") or []:
        value = demangle(str(item.get("name") or ""))
        if not value or value.get("params") is None:
            continue
        qualifier = value["qualifier"]
        if any("<" in part for part in qualifier) or "<" not in value["name"]:
            return None
        shape = tuple(
            "::".join(template_base(part) for part in param["components"])
            if param.get("kind") == "class" and param.get("components") and "<" in param["components"][-1] else "*"
            for param in value["params"]
        )
        return (*qualifier, template_base(value["name"])), shape
    return None


def _combined(found: list[tuple[str, str, str, str]]) -> dict[str, str] | None:
    """One ``suggest`` object from (rule, owner, confidence, basis) suggestions in ``SUGGEST_ORDER``."""

    if not found:
        return None
    rule, owner, confidence, basis = found[0]
    others = [(other, unit) for other, unit, _confidence, _basis in found[1:] if unit.casefold() != owner.casefold()]
    if others:
        confidence = "low"
        basis += "; " + "; ".join(f"{other} suggests {unit}" for other, unit in others)
    else:
        confidence = min((value for _rule, _unit, value, _basis in found), key=CONFIDENCES.index)
    return {"owner": owner, "rule": rule, "confidence": confidence, "basis": basis}


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
        aligned = draft.aligned_fill(row) if kind == "gap" and not row.get("padding") and draft.rules >= 4 else None
        if aligned is not None:
            # Rules 4: alignment fill of any size before an aligned GNU section start.
            place((FILL_ROW, None), _entry(identity, "high", aligned, "C-fill"), {
                "translation_unit": None, "classification": "compiler-generated", "workspace_path": None,
                "original_path": None, "provisional_file": None, "library": None, "archive_member": None,
                "evidence": ["alignment fill no unit defines: the graph's padding, or zero fill up to an aligned GNU section start"],
            })
            continue
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
            # Rules 3: the LOCAL section run holding the datum comes before
            # the "referenced only by" fallback.
            contained = draft.containing_run(row) if draft.rules >= 3 else None
            target, confidence, basis = None, None, None
            referenced_only = False
            if len(objects) == 1:
                target = next(iter(objects))
                confidence, basis = "high", f"object cluster {row.get('cluster')} of GNU object {target}"
                if contained is not None and contained[1] != target:
                    leave(identity, f"its object cluster names GNU object {target}, the LOCAL section run holding it GNU object {contained[1]}")
                    continue
            elif contained is not None:
                run, target = contained
                confidence = "high" if run.get("end_basis") == "next section symbol" else "medium"
                basis = (
                    f"inside GNU object {target}'s {run['name']} section run {run['start']}-{run['end']} "
                    f"(LOCAL section symbol {run['symbol_index']}; end: {run.get('end_basis')})"
                )
            elif users and not via_gap and len(user_objects) == 1 and None not in user_objects:
                if draft.rules >= 5 and row.get("common"):
                    leave(identity, _common_reason(f"GNU object {next(iter(user_objects))}", len(users)))
                    continue
                target = next(iter(user_objects))
                confidence, basis = "medium", f"referenced only by functions of GNU object {target} ({len(users)})"
                referenced_only = True
            if target is not None and not draft.anchor.get(identity):
                gnu = draft.gnu[target]
                gnu_library = gnu.get("library") or "unidentified GNU object"
                if library is not None and gnu_library != library:
                    leave(identity, f"data of GNU object {target} (library {gnu_library}), this plan's scope is {library}")
                    continue
                if referenced_only and draft.rules >= 6 and draft.global_data(row):
                    # Rules 6: a GLOBAL only one object reads is that object's only inside its own data run.
                    owner = f"gnu:{target}"
                    reason = draft.withhold(identity, owner, owner, len(users), f"GNU object {target}")
                    if reason is not None:
                        leave(identity, reason)
                        continue
                    basis += f", inside its own data run ({draft.data_position(identity, owner)[1]})"
                place(("provider", target), _entry(identity, confidence, basis, "P-gnu-data"), provider_row(gnu, gnu["functions"][0] if gnu["functions"] else identity))
                continue
        if kind == "gap" and draft.rules >= 3:
            reached = _section_gap(draft, row)
            if reached is not None:
                gnu, basis = reached
                gnu_library = gnu.get("library") or "unidentified GNU object"
                if library is not None and gnu_library != library:
                    leave(identity, f"gap of GNU object {gnu['address']}'s section run (library {gnu_library}), this plan's scope is {library}")
                    continue
                place(("provider", gnu["address"]), _entry(identity, "high", basis, "P-gnu-section"), provider_row(gnu, gnu["functions"][0]))
                continue
        if library is not None:
            decided = _provider_unit_decision(draft, row, library) if draft.rules >= 3 else None
            if decided is not None:
                # Rules 3: a Metrowerks-compiled member of the plan's library.
                unit, rule, basis, confidence = decided
                stem = PurePosixPath(unit).stem
                place(("provider", f"{library}:{stem}.o"), _entry(identity, confidence, basis, rule), _mw_unit_row(draft, unit, library))
                continue
            if identity in draft.withheld:
                leave(identity, draft.withheld[identity][1])
                continue
            leave(
                identity,
                "no GNU object rule decides it: a provider plan names its archive member by hand"
                if draft.rules < 3
                else "no GNU object or provider-unit rule decides it: a provider plan names its archive member by hand",
            )
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
                if draft.rules >= 5 and row.get("common"):
                    reason = _common_reason(spelled, len(users))
                    if draft.rules >= 6:
                        draft.withheld[identity] = (spelled, reason, False)
                    leave(identity, reason)
                    continue
                basis = f"referenced only by {len(users)} function(s) of {spelled}"
                if draft.rules >= 6 and draft.global_data(row):
                    # Rules 6: a GLOBAL can be defined in a file that does not read it.
                    reason = draft.withhold(identity, spelled, spelled.casefold(), len(users), spelled)
                    if reason is not None:
                        leave(identity, reason)
                        continue
                    basis += f", inside its own data run ({draft.data_position(identity, spelled.casefold())[1]})"
                decided = (spelled, "D-referenced", basis, "medium")
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

    suggested = 0
    if draft.rules >= 4 and library is None:
        # Rules 4: a reviewed suggestion on each open row the heuristics reach (never a decision).
        for open_row in open_rows:
            kind = draft.by_id[open_row["artifact"]]["kind"]
            suggestion = (
                draft.suggest_function(open_row["artifact"]) if kind == "function"
                else draft.suggest_data(open_row["artifact"]) if kind == "data" else None
            )
            if suggestion is not None:
                open_row["suggest"] = suggestion
                suggested += 1

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

    header_emits, open_emits, open_emit_reasons = _header_emits(draft, workspace, out_owners)
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
    if rules >= 4:
        plan["draft"]["open_header_emit_reasons"] = open_emit_reasons
        plan["draft"]["suggested"] = suggested
    if rules >= 6 and library is None:
        # Rules 6: the emit each open function takes once a planner owns it in an
        # authored unit (the header rules do not depend on which unit); --check
        # proves such a row of a hand-owned function like a drafted one.
        plan["draft"]["open_row_header_emits"] = [
            found for open_row in open_rows
            if isinstance(found := _row_emit(draft, workspace, draft.by_id[open_row["artifact"]]), dict)
        ]
    return plan


def _section_gap(draft: _Draft, row: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    """Rules 3: (GNU object, basis) of a non-padding gap its object reaches only through its own LOCAL section symbols."""

    contained = draft.containing_run(row)
    reaching = draft.reaching.get(row["id"], [])
    if contained is None or not reaching:
        return None
    run, address = contained
    gnu = draft.gnu.get(address)
    if gnu is None or not gnu.get("functions"):
        return None
    symbols = {item.get("symbol_index") for item in gnu.get("sections") or []}
    functions = set(gnu["functions"])

    def own_data(site: str) -> bool:
        # Rules 4: data inside one of the object's own LOCAL section runs (SCE 0x446d70's .data).
        other = draft.by_id[site]
        held = draft.containing_run(other) if draft.rules >= 4 and other["kind"] == "data" else None
        return held is not None and held[1] == address

    if not all((site in functions or own_data(site)) and kind == "SECTION" and index in symbols for site, index, kind in reaching):
        return None
    data = sum(1 for site, _index, _kind in reaching if site not in functions)
    return gnu, (
        f"inside GNU object {address}'s {run['name']} section run {run['start']}-{run['end']}, reached only through its "
        f"LOCAL section symbols from its functions" + (f" and its own section data ({data} of them)" if data else "")
        + f" ({len(reaching)} relocations)"
    )


def _common_reason(referrer: str, users: int) -> str:
    """Rules 5: the open reason of a COMMON variable only one object or unit references."""

    return (
        f"COMMON variable (linker-allocated, no defining section): the ELF names no definer; "
        f"referenced only by {users} function(s) of {referrer}"
    )


def _provider_unit_decision(draft: _Draft, row: dict[str, Any], library: str) -> tuple[str, str, str, str] | None:
    """Rules 3: the unit decision of an artifact of a Metrowerks-compiled provider unit of ``library``.

    The unit anchors and ``A-between`` (``_Draft.decided``), or for data
    ``D-referenced``: every referencing function is decided for that unit and
    the datum is not provider code of another library.
    """

    identity = row["id"]
    decided = draft.decided.get(identity)
    common = draft.rules >= 5 and row.get("common")
    if decided is None and row["kind"] == "data" and len(draft.conflict(identity)) <= 1 and not common:
        if strong_provider(row, draft.unit_library) in (None, library):
            users, via_gap = draft.function_users(identity)
            units = {(draft.decided.get(user) or ("",))[0].casefold() for user in users}
            if users and not via_gap and len(units) == 1 and "" not in units:
                spelled = draft.decided[next(iter(users))][0]
                basis = f"referenced only by {len(users)} function(s) of {spelled}"
                if draft.rules >= 6 and draft.global_data(row) and draft.unit_library.get(spelled.casefold()) == library:
                    # Rules 6: a GLOBAL only one unit reads is that unit's only inside its own data run.
                    if draft.withhold(identity, spelled, spelled.casefold(), len(users), spelled) is not None:
                        return None
                    basis += f", inside its own data run ({draft.data_position(identity, spelled.casefold())[1]})"
                decided = (spelled, "D-referenced", basis, "medium")
    if decided is None or draft.unit_library.get(decided[0].casefold()) != library:
        return None
    return decided


def _mw_unit_row(draft: _Draft, unit: str, library: str) -> dict[str, Any]:
    """Rules 3: the provider row of a Metrowerks-compiled member of ``library`` (``P-mw-unit``)."""

    known = draft.units.get(unit.casefold()) or {}
    sources = sorted({path for path in known.get("paths") or [] if _is_source(path)})
    original = sources[0] if len(sources) == 1 else None
    stem = PurePosixPath(unit).stem
    return {
        "translation_unit": unit,
        "classification": "provider",
        "workspace_path": None,
        "original_path": original,
        "provisional_file": None,
        "library": library,
        "archive_member": {"gnu_object": None, "object": f"{stem}.o", "linked": "unknown"},
        "draft_rule": "P-mw-unit",
        "evidence": [
            f"Metrowerks-compiled provider unit {unit} of {library}"
            + (f" (path {original})" if original else " (by its unit name; no DWARF path)"),
            f"object {stem}.o: Metrowerks names an object after its source file; whether it came from an archive "
            "is not evidenced (linked unknown)",
        ],
    }


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


def _header_name(header: str) -> str:
    return PureWindowsPath(header.replace("/", "\\")).name


def _workspace_header(workspace: _Workspace, header: str) -> str | None:
    """The existing workspace header a ``Z:\\dev`` header path names (under its module directory), if any."""

    verdict = path_library(header)
    module = original_module(header) if not verdict or verdict[0] == "authored" else None
    spelled = workspace.directories.get(module.casefold()) if module else None
    path = f"{spelled}/{_header_name(header)}" if spelled else None
    return path if path and workspace.exact_file(path) else None


def _header_emits(
    draft: _Draft, workspace: _Workspace, owners: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str], dict[str, str]]:
    """(header emits, artifacts whose emit stays open, rules 4: why each stays open)."""

    emits = []
    undecided = []
    reasons: dict[str, str] = {}
    for owner in owners:
        if owner.get("classification") != "authored":
            continue
        for value in owner["artifacts"]:
            identity = artifact_id(value)
            found = _row_emit(draft, workspace, draft.by_id[identity])
            if isinstance(found, dict):
                emits.append(found)
            elif isinstance(found, str):
                undecided.append(identity)
                reasons[identity] = found
    return emits, undecided, reasons if draft.rules >= 4 else {}


def _row_emit(draft: _Draft, workspace: _Workspace, row: dict[str, Any]) -> dict[str, Any] | str | None:
    """The header emit of a function an authored unit owns, why it stays open, or ``None`` (no emit)."""

    header = row.get("emitted_from_header")
    if row["kind"] != "function":
        return None
    if not header:
        return _family_emit(draft, workspace, row) if draft.rules >= 4 else None
    identity = row["id"]
    reason = _emit_reason(row)
    name = _header_name(header)
    verdict = path_library(header)
    evidence = [f"dwarf-cu-header {header}"]
    if reason is None:
        return "a header instance that is neither a template, WEAK nor inline (binding 13)"
    if verdict and verdict[0] == "provider" and verdict[1]:
        return {"artifact": identity, "header": f"<{name}>", "library": verdict[1], "reason": reason,
                "evidence": evidence, "draft_rule": "H-dwarf-header"}
    path = _workspace_header(workspace, header)
    if path:
        return {"artifact": identity, "header": path, "reason": reason, "evidence": evidence, "draft_rule": "H-dwarf-header"}
    return f"no existing workspace header {name} under the module directory of {header}"


def _family_emit(draft: _Draft, workspace: _Workspace, row: dict[str, Any]) -> dict[str, Any] | str | None:
    """Rules 4: the emit of an owned instance without a header compile unit, why it stays open, or ``None`` (no emit).

    ``H-template-family``: an MSL template instance takes the one MSL header
    every instance of its template with a header compile unit names.
    ``H-class-header``: an implicit special member of an authored class takes
    the one existing workspace header its class's other members' header
    compile units name (a class without one is defined in its source file).
    """

    classification = row.get("classification") or {}
    msl = classification.get("candidate") == "provider" and classification.get("library") == "MSL"
    function = _function_template(row) if draft.rules >= 6 else None
    if function is not None and (msl or function[0][0] in MSL_NAMESPACES):
        # Rules 6: an MSL function template instance, a LOCAL copy too.
        return _function_template_emit(draft, row, function)
    if not draft.bindings(row) & COPY_BINDINGS:
        return None
    reason = _emit_reason(row)
    families, classes = draft.family_headers()
    family = _template_family(row)
    if family and (msl or family[0] in MSL_NAMESPACES):
        label = readable_qualified(list(family))
        headers = families.get(family) or {}
        names = sorted({_header_name(path) for path in headers})
        libraries = {(path_library(path) or (None, None))[1] for path in headers}
        if not headers:
            return f"MSL template instance without a header compile unit; no instance of {label} has one"
        if len(names) != 1 or libraries != {"MSL"}:
            shown = ", ".join(f"<{name}>" for name in names) + ("" if libraries == {"MSL"} else " (not all MSL headers)")
            return f"MSL template instance without a header compile unit; instances of {label} name several headers: {shown}"
        examples = sorted(identity for values in headers.values() for identity in values)
        return {
            "artifact": row["id"], "header": f"<{names[0]}>", "library": "MSL", "reason": reason,
            "evidence": [
                f"no header compile unit of its own; every instance of {label} with one ({len(examples)}, e.g. "
                f"{', '.join(examples[:3])}) names <{names[0]}>",
            ],
            "draft_rule": "H-template-family",
        }
    owner = _qualifier_of(row)
    name = next((str(item.get("name") or "") for item in row.get("names") or []), "")
    if not owner or owner[0] in MSL_NAMESPACES or msl or not name.startswith(SPECIAL_MEMBERS):
        return None
    headers = {path: values for path, values in (classes.get(owner) or {}).items() if values != [row["id"]]}
    if not headers:
        return None
    label = readable_qualified(list(owner))
    distinct = sorted({path.casefold(): path for path in headers}.values(), key=str.casefold)
    if len(distinct) != 1:
        return f"implicit special member of {label}; its members' header compile units name several headers: {', '.join(distinct)}"
    path = _workspace_header(workspace, distinct[0])
    if path is None:
        return f"implicit special member of {label}; its members' header {distinct[0]} is no existing workspace header"
    members = sorted(headers[distinct[0]])
    return {
        "artifact": row["id"], "header": path, "reason": reason,
        "evidence": [
            f"implicit special member without a header compile unit; the other members of {label} with one "
            f"({len(members)}, e.g. {', '.join(members[:3])}) name {distinct[0]}",
        ],
        "draft_rule": "H-class-header",
    }


def _function_template_emit(
    draft: _Draft, row: dict[str, Any], function: tuple[tuple[str, ...], tuple[str, ...]]
) -> dict[str, Any] | str:
    """Rules 6 ``H-template-family`` of an MSL function template instance (inline, WEAK or LOCAL).

    The one MSL header every instance of the same overload with a header
    compile unit names; when none has one, MSL's defining header
    (``MSL_FUNCTION_TEMPLATE_HEADERS``) if every instance of the template that
    has a header compile unit names that header too.
    """

    template, shape = function
    label = readable_qualified(list(template))
    overloads, templates = draft.overload_headers()
    shown = f"{label}({', '.join(shape)})"

    def emit(header: str, evidence: str) -> dict[str, Any]:
        return {"artifact": row["id"], "header": f"<{header}>", "library": "MSL", "reason": _emit_reason(row) or "template",
                "evidence": [evidence], "draft_rule": "H-template-family"}

    headers = overloads.get(function) or {}
    names = sorted({_header_name(path) for path in headers})
    libraries = {(path_library(path) or (None, None))[1] for path in headers}
    if headers:
        if len(names) != 1 or libraries != {"MSL"}:
            listed = ", ".join(f"<{name}>" for name in names) + ("" if libraries == {"MSL"} else " (not all MSL headers)")
            return f"MSL function template instance without a header compile unit; instances of {shown} name several headers: {listed}"
        examples = sorted(identity for values in headers.values() for identity in values)
        return emit(names[0], f"no header compile unit of its own; every instance of {shown} with one ({len(examples)}, e.g. "
                              f"{', '.join(examples[:3])}) names <{names[0]}>")
    defining = MSL_FUNCTION_TEMPLATE_HEADERS.get(template)
    if defining is None:
        return f"MSL function template instance without a header compile unit; no instance of {shown} has one"
    others = sorted({_header_name(path) for path in templates.get(template) or {}} - {defining})
    if others:
        return (f"MSL function template instance without a header compile unit; MSL defines {label} in <{defining}> but "
                f"instances of other overloads name {', '.join(f'<{name}>' for name in others)}")
    return emit(defining, f"no instance of {shown} has a header compile unit; MSL defines {label} in <{defining}>"
                          + (", as every instance of it with one names" if templates.get(template) else ""))


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
    # Rules 6: an open row's emit holds for the function once the plan owns it in an authored unit.
    authored = {
        artifact_id(value) for owner in plan.get("owners") or [] if isinstance(owner, dict) and owner.get("classification") == "authored"
        for value in owner.get("artifacts") or []
    }
    for row in (fresh.get("draft") or {}).get("open_row_header_emits") or []:
        if row["artifact"] in authored:
            fresh_emits.setdefault(row["artifact"], row)
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
