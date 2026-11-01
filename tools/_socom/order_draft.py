"""Stage 5 phase A2 (drafts): source-order evidence and the emission-rule calibration.

``order draft`` reads the order target (``order_target``) and, for every
authored unit, the evidence for the *source* order of the definitions it
orders (decision D3: the functions and data a file defines):

* **DWARF lines**: the line of the first row of each function's line table
  (its definition line), for the units Metrowerks wrote line tables for;
* **local-static counter**: function-local statics are named ``name$N`` (a
  guard ``init$N`` follows a dynamically initialized one) with a per-unit
  counter; a function's value is the lowest N among the statics no other
  function of its unit references, and a static's own name carries its N;
* **literal labels**: the highest ``@N`` among the literals only that
  function references (the same per-unit counter);
* **static initializer**: the order in which the unit's ``__sinit_``
  function first references each data definition (C++ initializes a unit's
  objects in definition order; instruction scheduling adds some noise);
* **DWARF variable order**: file-scope variable DIEs of the unit's object
  contribution, in DIE order.

The **calibration** measures, on the units whose source order the DWARF
lines record, how well each evidence predicts it, and cross-checks the
counters on every unit.  What it finds decides how the evidence is used:
the address order of out-of-line definitions is the exact reverse of their
source order, the local-static counter follows source order, and literal
labels and DIE order follow the address (emission) order, so they
corroborate a draft but never constrain it.  Phase B's compiler probes
settle the rule; nothing here claims reproduction.

Per unit the draft gives a hypothesis source order of its functions
(DWARF line order where lines exist, else reverse address order) and of its
data per region (address order), every adjacency classed:

* ``proven``: both ends carry DWARF lines in this order;
* ``constrained``: the local-static counter (functions, data) or the static
  initializer (data) orders the pair this way;
* ``hypothesis``: only the calibrated rule places it.

Definitions without a source position are listed apart (``not_placed``):
compiler-generated ones (``__vt__``, ``__RTTI__``, ``__sinit_``,
``.p__sinit_``, ``__arraydtor$N``, ``init$N`` guards), functions without a
DWARF line in a unit that has lines (implicit members, emitted on demand)
and COMMON allocations (placed by the linker).  Evidence that contradicts a
draft adjacency is a ``conflict``; the rule's order is kept.

Read-only; the output is a disposable build product.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import struct
from collections import Counter, defaultdict
from contextlib import closing
from itertools import combinations
from pathlib import Path
from typing import Any

from .order_target import select_units
from .util import canonical_json

DRAFT_KIND = "socom-order-draft"
DRAFT_SCHEMA = 1
DRAFT_RULES_VERSION = 1
ADJACENCY_CLASSES = ("proven", "constrained", "hypothesis")
STATUSES = ("proven", "constrained", "hypothesis", "trivial")
CLASS_MEANING = {
    "proven": "DWARF lines of both definitions record this source order",
    "constrained": "a source-order counter (local statics) or the static initializer orders the pair this way",
    "hypothesis": "only the calibrated emission rule places the pair",
}
STATIC_COUNTER = re.compile(r"^(?P<base>[A-Za-z_]\w*)\$(?P<number>\d+)$")
LITERAL_LABEL = re.compile(r"^@(?P<number>\d+)$")
ARRAY_DESTRUCTOR = re.compile(r"^__arraydtor\$\d+$")
STATIC_GUARD = re.compile(r"^init\$\d+$")
SINIT = "__sinit_"
FILE_LOCAL = "@unnamed@"
_SHOWN = 12


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def draft_digest(draft: dict[str, Any]) -> str:
    """The digest a draft stores: canonical JSON of everything but ``draft_sha256``."""

    return _digest({key: value for key, value in draft.items() if key != "draft_sha256"})


def _int(value: str) -> int:
    return int(value, 16)


def _rate(agree: int, total: int) -> float | None:
    return round(agree / total, 4) if total else None


# -- raw evidence ---------------------------------------------------------------------------


def dwarf_variables(root: Path, graph: dict[str, Any]) -> list[dict[str, Any]]:
    """File-scope variable DIEs with a static address, in DIE order, with the object unit holding them.

    A variable DIE belongs to the object scope while the last compile unit
    seen is the object's own (a source path without a pc range); variables
    after a function or header compile unit are that function's.
    """

    from .dwarf1 import Dwarf1Debug
    from .elf import Elf32File
    from .source_graph import _is_source, _tu_name

    elf = Elf32File(root / "support" / "socom.elf")
    if ".debug" not in {section.name for section in elf.sections}:
        return []
    by_address = {_int(row["address"]): row["id"] for row in graph["artifacts"] if row["kind"] == "data"}
    rows = []
    unit, scope = None, None
    for die in Dwarf1Debug(elf.section_data(".debug")).parse(strict=True):
        if die.tag_name == "compile_unit":
            path = die.string("name") or ""
            low, high = die.integer("low_pc"), die.integer("high_pc")
            if path and _is_source(path) and not (low is not None and high is not None and high > low):
                unit, scope = _tu_name(path), "object"
            else:
                scope = "function"
            continue
        if scope != "object" or die.tag_name not in ("global_variable", "local_variable"):
            continue
        location = die.attribute("location")
        value = location.value if location is not None else None
        if not isinstance(value, bytes) or len(value) != 5 or value[0] != 0x03:  # OP_ADDR
            continue
        artifact = by_address.get(struct.unpack("<I", value[1:])[0])
        if artifact is not None:
            rows.append({"unit": unit, "order": len(rows), "artifact": artifact})
    return rows


def load_evidence(root: Path, cache: Path, graph: dict[str, Any]) -> dict[str, Any]:
    """The raw evidence of a draft: line rows, counter and label references, uses, compile-unit order, variables.

    ``cache`` is a fresh source cache (``source_cache.ensure_source_cache``)
    of the same graph.
    """

    with closing(sqlite3.connect(f"file:{cache.as_posix()}?mode=ro", uri=True)) as connection:
        lines = [
            {"artifact": artifact, "tu": tu, "address": address, "line": line}
            for artifact, tu, address, line in connection.execute(
                "SELECT c.artifact, c.tu, l.address, l.line FROM dwarf_cus c JOIN dwarf_lines l ON l.die_offset = c.die_offset "
                "WHERE c.kind = 'function' AND c.artifact IS NOT NULL AND l.line > 0"
            )
        ]
        labels = [
            {"site_artifact": site_artifact, "symbol": symbol}
            for site_artifact, symbol in connection.execute(
                "SELECT DISTINCT site_artifact, symbol FROM refs WHERE site_artifact IS NOT NULL AND symbol_binding = 'LOCAL' "
                "AND (symbol GLOB '@[0-9]*' OR symbol GLOB '*[$][0-9]*')"
            )
        ]
        uses = [
            {"site_artifact": site_artifact, "target_artifact": target_artifact, "site": site}
            for site_artifact, target_artifact, site in connection.execute(
                "SELECT site_artifact, target_artifact, min(site) FROM refs WHERE site_artifact IS NOT NULL "
                "AND target_artifact IS NOT NULL AND site_artifact <> target_artifact GROUP BY site_artifact, target_artifact"
            )
        ]
        units = [
            {"object_unit": unit, "die_offset": int(die, 16), "low_pc": low}
            for unit, die, low in connection.execute(
                "SELECT object_unit, die_offset, low_pc FROM dwarf_cus WHERE kind IN ('function', 'header') "
                "AND object_unit IS NOT NULL AND low_pc IS NOT NULL"
            )
        ]
    return {"lines": lines, "labels": labels, "uses": uses, "compile_units": units, "variables": dwarf_variables(root, graph)}


# -- derived evidence -----------------------------------------------------------------------


def _code_regions(target: dict[str, Any]) -> tuple[set[int], set[int]]:
    code = {row["region"] for row in target["regions"] if row["window_kind"] == "code"}
    common = {row["region"] for row in target["regions"] if row["common"]}
    return code, common


def derive_evidence(target: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Per-artifact evidence values over the target's authored units (see the module docstring)."""

    owner: dict[str, str] = {}
    entries: dict[str, dict[str, Any]] = {}
    functions: dict[str, set[str]] = defaultdict(set)
    for unit in target["units"]:
        for section in unit["sections"]:
            for entry in section["artifacts"]:
                owner[entry["artifact"]] = unit["unit"]
                entries[entry["artifact"]] = entry
                if entry["kind"] == "function":
                    functions[unit["unit"]].add(entry["artifact"])

    # DWARF lines: the row at the lowest address of the function's line table; only in its own unit.
    first: dict[str, tuple[int, int]] = {}
    for row in raw["lines"]:
        artifact = row["artifact"]
        unit = owner.get(artifact)
        if unit is None or str(row["tu"]).casefold() != unit.casefold():
            continue
        key = (int(row["address"]), int(row["line"]))
        if artifact not in first or key < first[artifact]:
            first[artifact] = key
    lines = {artifact: key[1] for artifact, key in first.items()}

    # Counters referenced by exactly one function of the unit (private): statics and literal labels.
    sites: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in raw["labels"]:
        site = row["site_artifact"]
        unit = owner.get(site)
        if unit is not None and site in functions[unit]:
            sites[(unit, row["symbol"])].add(site)
    statics: dict[str, int] = {}
    literals: dict[str, int] = {}
    for (unit, symbol), found in sites.items():
        if len(found) != 1:
            continue
        (site,) = found
        literal = LITERAL_LABEL.match(symbol)
        if literal:
            literals[site] = max(literals.get(site, 0), int(literal["number"]))
            continue
        static = STATIC_COUNTER.match(symbol)
        if static and not ARRAY_DESTRUCTOR.match(symbol):
            number = int(static["number"])
            statics[site] = min(statics.get(site, number), number)
    own: dict[str, int] = {}
    for artifact, entry in entries.items():
        match = STATIC_COUNTER.match(entry["name"] or "") if entry["kind"] == "data" else None
        if match:
            own[artifact] = int(match["number"])

    # The static initializer: first reference to each of the unit's data definitions, by site address.
    sinit_of = {
        artifact: owner[artifact]
        for artifact, entry in entries.items()
        if entry["kind"] == "function" and (entry["name"] or "").startswith(SINIT)
    }
    sinit_rows: dict[str, list[tuple[int, str]]] = defaultdict(list)
    users: dict[str, set[str]] = defaultdict(set)
    for row in raw["uses"]:
        site, found = row["site_artifact"], row["target_artifact"]
        users[found].add(site)
        unit = sinit_of.get(site)
        entry = entries.get(found)
        if unit is not None and owner.get(found) == unit and entry["kind"] == "data" and entry["class"] == "definition":
            sinit_rows[unit].append((int(row["site"]), found))
    sinit: dict[str, int] = {}
    for unit, rows in sinit_rows.items():
        for rank, (_site, artifact) in enumerate(sorted(rows)):
            sinit.setdefault(artifact, rank)

    variables = {row["artifact"]: row["order"] for row in raw["variables"] if owner.get(row["artifact"]) == row["unit"]}
    return {
        "lines": lines, "statics": statics, "literals": literals, "own_counters": own, "sinit": sinit,
        "variables": variables, "users": users, "compile_units": raw["compile_units"],
    }


def evidence_digest(derived: dict[str, Any]) -> str:
    return _digest({key: derived[key] for key in ("lines", "statics", "literals", "own_counters", "sinit", "variables")})


# -- drafts ---------------------------------------------------------------------------------


# (row field, derived evidence key) per definition kind.
FUNCTION_FIELDS = (("line", "lines"), ("static_counter", "statics"), ("literal_label", "literals"))
DATA_FIELDS = (("static_counter", "own_counters"), ("sinit", "sinit"), ("variable", "variables"))
# (row field, basis, constrains the source order, a higher value is earlier in source).  Literal labels and
# DIE order follow the emission order (see the calibration): they corroborate, never constrain.
FUNCTION_TESTS = (
    ("line", "dwarf-line", True, False),
    ("static_counter", "local-static-counter", True, False),
    ("literal_label", "literal-labels", False, True),
)
DATA_TESTS = (
    ("static_counter", "local-static-counter", True, False),
    ("sinit", "static-initializer", True, False),
    ("variable", "dwarf-variable-order", False, False),
)


def _row(entry: dict[str, Any], region: int, derived: dict[str, Any], fields: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    artifact = entry["artifact"]
    row: dict[str, Any] = {"artifact": artifact, "name": entry["name"], "address": entry["address"], "region": region}
    for field, key in fields:
        if artifact in derived[key]:
            row[field] = derived[key][artifact]
    if FILE_LOCAL in (entry["name"] or ""):
        row["file_local"] = True
    return row


def _adjacency(a: dict[str, Any], b: dict[str, Any], tests: tuple[tuple[str, str, bool, bool], ...]) -> dict[str, Any]:
    """Classify ``a`` before ``b`` in the draft by every evidence both ends carry."""

    basis, conflicts, corroborated, contradicted = [], [], [], []
    same_line = False
    for field, name, constrains, descending in tests:
        if field not in a or field not in b:
            continue
        if a[field] == b[field]:
            same_line = same_line or field == "line"
            continue
        agrees = (a[field] > b[field]) if descending else (a[field] < b[field])
        if constrains:
            (basis if agrees else conflicts).append(name)
        else:
            (corroborated if agrees else contradicted).append(name)
    klass = "proven" if "dwarf-line" in basis else "constrained" if basis else "hypothesis"
    row: dict[str, Any] = {"before": a["artifact"], "after": b["artifact"], "class": klass, "basis": basis}
    if same_line:
        row["note"] = "both definitions start on one DWARF line"
    if conflicts:
        row["conflicts"] = conflicts
    if corroborated:
        row["corroborated_by"] = corroborated
    if contradicted:
        row["contradicted_by"] = contradicted
    return row


def _chain(rows: list[dict[str, Any]], field: str, basis: str) -> list[dict[str, Any]]:
    """Consecutive pairs in ``field`` order (a minimal set implying every pair), checked against the draft order."""

    position = {row["artifact"]: index for index, row in enumerate(rows)}
    ordered = sorted((row for row in rows if field in row), key=lambda row: (row[field], position[row["artifact"]]))
    return [
        {"before": a["artifact"], "after": b["artifact"], "basis": basis, "values": [a[field], b[field]],
         "agrees": position[a["artifact"]] < position[b["artifact"]]}
        for a, b in zip(ordered, ordered[1:])
        if a[field] != b[field]
    ]


def _status(adjacencies: list[dict[str, Any]]) -> str:
    if not adjacencies:
        return "trivial"
    classes = Counter(row["class"] for row in adjacencies)
    if classes["proven"] == len(adjacencies):
        return "proven"
    return "constrained" if classes["proven"] or classes["constrained"] else "hypothesis"


def unit_draft(unit: dict[str, Any], target: dict[str, Any], derived: dict[str, Any]) -> dict[str, Any]:
    """One unit's evidence and hypothesis source order (functions; data per region)."""

    code, common = _code_regions(target)
    lines = derived["lines"]
    defined = [
        (section, entry)
        for section in unit["sections"]
        for entry in section["artifacts"]
        if entry["class"] == "definition"
    ]
    dwarf = any(entry["artifact"] in lines for section, entry in defined if entry["kind"] == "function")
    placed, not_placed = [], []
    data: dict[int, dict[str, Any]] = {}
    for section, entry in defined:
        name = entry["name"] or ""
        reason = None
        if entry.get("generated"):
            reason = "generated"
        elif entry["kind"] == "function" and ARRAY_DESTRUCTOR.match(name):
            reason = "compiler-generated"
        elif entry["kind"] == "data" and STATIC_GUARD.match(name):
            reason = "static-guard"
        elif section["region"] in common:
            reason = "common"
        elif entry["kind"] == "function" and section["region"] not in code:
            reason = "outside-code"
        elif entry["kind"] == "function" and dwarf and entry["artifact"] not in lines:
            reason = "no-dwarf-line"
        if reason is not None:
            not_placed.append({"artifact": entry["artifact"], "name": entry["name"], "address": entry["address"],
                               "kind": entry["kind"], "reason": reason})
            continue
        if entry["kind"] == "function" and section["region"] in code:
            placed.append(_row(entry, section["region"], derived, FUNCTION_FIELDS))
            continue
        region = data.setdefault(section["region"], {"region": section["region"], "label": section["label"], "order": []})
        region["order"].append(_row(entry, section["region"], derived, DATA_FIELDS))

    if dwarf:
        order = sorted(placed, key=lambda row: (row["line"], -_int(row["address"])))
        basis = "dwarf-lines"
    else:
        order = sorted(placed, key=lambda row: -_int(row["address"]))
        basis = "reverse-address"
    adjacencies = [_adjacency(a, b, FUNCTION_TESTS) for a, b in zip(order, order[1:])]
    functions = {
        "basis": basis,
        "order": order,
        "adjacencies": adjacencies,
        "constraints": _chain(order, "static_counter", "local-static-counter"),
        "status": _status(adjacencies),
    }
    regions = []
    for number in sorted(data):
        region = data[number]
        rows = sorted(region["order"], key=lambda row: _int(row["address"]))
        found = [_adjacency(a, b, DATA_TESTS) for a, b in zip(rows, rows[1:])]
        regions.append(
            {
                "region": number, "label": region["label"], "basis": "address", "order": rows, "adjacencies": found,
                "constraints": _chain(rows, "static_counter", "local-static-counter") + _chain(rows, "sinit", "static-initializer"),
            }
        )
    data_adjacencies = [row for region in regions for row in region["adjacencies"]]
    every = adjacencies + data_adjacencies
    return {
        "unit": unit["unit"],
        "workspace_path": unit["workspace_path"],
        "segments": unit["segments"],
        "primary_segment": unit["primary_segment"],
        "link_position": unit["link_position"],
        "dwarf_lines": dwarf,
        "functions": functions,
        "data": regions,
        "not_placed": not_placed,
        "status": {"functions": functions["status"], "data": _status(data_adjacencies), "unit": _status(every)},
        "counts": _counts(every, len(order), sum(len(region["order"]) for region in regions), not_placed),
    }


def _counts(adjacencies: list[dict[str, Any]], functions: int, data: int, not_placed: list[dict[str, Any]]) -> dict[str, Any]:
    classes = Counter(row["class"] for row in adjacencies)
    return {
        "functions": functions,
        "data": data,
        "adjacencies": {klass: classes[klass] for klass in ADJACENCY_CLASSES},
        "conflicts": sum(1 for row in adjacencies if row.get("conflicts")),
        "corroborated": sum(1 for row in adjacencies if row.get("corroborated_by")),
        "not_placed": dict(sorted(Counter(row["reason"] for row in not_placed).items())),
    }


# -- calibration ----------------------------------------------------------------------------


def _pairs(rows: list[tuple[Any, Any]], agree) -> tuple[int, int]:
    """(agreeing, compared) over every pair of ``rows`` (``(x, y)`` values; ties in either value skipped)."""

    good = total = 0
    for a, b in combinations(rows, 2):
        if a[0] == b[0] or a[1] == b[1]:
            continue
        total += 1
        good += 1 if agree(a, b) else 0
    return good, total


def _measure(name: str, relation: str, good: int, total: int, **extra: Any) -> dict[str, Any]:
    return {"evidence": name, "relation": relation, "agree": good, "pairs": total, "rate": _rate(good, total), **extra}


def _longest_decreasing(values: list[int]) -> set[int]:
    """Indices of one longest strictly decreasing subsequence (the earliest-ending of equals)."""

    if not values:
        return set()
    best = [1] * len(values)
    back = [-1] * len(values)
    for j in range(len(values)):
        for i in range(j):
            if values[i] > values[j] and best[i] + 1 > best[j]:
                best[j], back[j] = best[i] + 1, i
    end = max(range(len(values)), key=lambda index: (best[index], -index))
    keep = set()
    while end >= 0:
        keep.add(end)
        end = back[end]
    return keep


def calibrate(target: dict[str, Any], derived: dict[str, Any], drafts: list[dict[str, Any]]) -> dict[str, Any]:
    """How well each evidence predicts the DWARF source order, and the counter cross-checks on every unit."""

    users = derived["users"]
    code, _common = _code_regions(target)
    by_unit = {row["unit"]: row for row in target["units"]}
    line_pairs = rev = steps = back = exact = units = units3 = functions = explained_pairs = 0
    lit = lit_pairs = stat = stat_pairs = 0
    counterexamples, displaced = [], []
    unplaced = []
    cross_static = cross_static_pairs = cross_literal = cross_literal_pairs = 0
    for draft in drafts:
        unit = by_unit[draft["unit"]]
        rows = sorted(draft["functions"]["order"], key=lambda row: _int(row["address"]))  # address order
        # Cross-checks on every unit: counters along the address order.
        good, total = _pairs([(_int(r["address"]), r["static_counter"]) for r in rows if "static_counter" in r], lambda a, b: a[1] > b[1])
        cross_static, cross_static_pairs = cross_static + good, cross_static_pairs + total
        good, total = _pairs([(_int(r["address"]), r["literal_label"]) for r in rows if "literal_label" in r], lambda a, b: a[1] < b[1])
        cross_literal, cross_literal_pairs = cross_literal + good, cross_literal_pairs + total
        if not draft["dwarf_lines"]:
            continue
        unplaced.extend(
            {"unit": draft["unit"], "name": row["name"], "address": row["address"], "reason": row["reason"]}
            for row in draft["not_placed"]
            if row["kind"] == "function" and row["reason"] in ("no-dwarf-line", "compiler-generated")
        )
        lined = [row for row in rows if "line" in row]
        if len(lined) < 2:
            continue
        units += 1
        units3 += 1 if len(lined) >= 3 else 0
        functions += len(lined)
        good, total = _pairs([(_int(r["address"]), r["line"]) for r in lined], lambda a, b: (a[0] < b[0]) == (a[1] > b[1]))
        rev, line_pairs = rev + good, line_pairs + total
        forward = [(a, b) for a, b in zip(lined, lined[1:]) if a["line"] < b["line"]]
        steps += len(lined) - 1
        back += sum(1 for a, b in zip(lined, lined[1:]) if a["line"] > b["line"])
        exact += 0 if forward else 1
        counterexamples.extend(
            {"unit": draft["unit"], "before": a["name"], "before_line": a["line"], "before_at": a["address"],
             "after": b["name"], "after_line": b["line"], "after_at": b["address"]}
            for a, b in forward
        )
        good, total = _pairs([(r["line"], r["literal_label"]) for r in lined if "literal_label" in r], lambda a, b: (a[0] < b[0]) == (a[1] < b[1]))
        lit, lit_pairs = lit + good, lit_pairs + total
        good, total = _pairs([(r["line"], r["static_counter"]) for r in lined if "static_counter" in r], lambda a, b: (a[0] < b[0]) == (a[1] < b[1]))
        stat, stat_pairs = stat + good, stat_pairs + total
        # Displaced: off one longest reverse chain; with the unit's first user in address order.
        keep = _longest_decreasing([row["line"] for row in lined])
        explained_pairs += sum(
            1 for i, j in combinations(range(len(lined)), 2) if lined[i]["line"] < lined[j]["line"] and not {i, j} <= keep
        )
        functions_in_unit = [
            entry for section in unit["sections"] if section["region"] in code for entry in section["artifacts"] if entry["kind"] == "function"
        ]
        index = {entry["artifact"]: position for position, entry in enumerate(functions_in_unit)}
        for position, row in enumerate(lined):
            if position in keep:
                continue
            found = sorted(index[site] for site in users.get(row["artifact"], ()) if site in index)
            here = index[row["artifact"]]
            item = {"unit": draft["unit"], "name": row["name"], "line": row["line"], "address": row["address"],
                    "file_local": bool(row.get("file_local"))}
            if found and found[0] < here:
                item["first_user"] = functions_in_unit[found[0]]["name"]
            elif not found:
                item["first_user"] = None
            else:
                item["first_user_after"] = functions_in_unit[found[0]]["name"]
            displaced.append(item)
    involved = {(row["unit"], row["name"]) for row in displaced}
    explained_steps = sum(
        1 for row in counterexamples if (row["unit"], row["before"]) in involved or (row["unit"], row["after"]) in involved
    )
    return {
        "dwarf_units": {"units": units, "units_with_3": units3, "functions": functions, "pairs": line_pairs, "steps": steps},
        "functions": [
            _measure("reverse-address", "a lower address is later in source", rev, line_pairs,
                     steps_agree=back, steps=steps, units_exact=exact, units=units),
            _measure("forward-address", "a lower address is earlier in source", line_pairs - rev, line_pairs),
            _measure("literal-labels", "a lower private @N is earlier in source", lit, lit_pairs),
            _measure("literal-labels-reversed", "a lower private @N is later in source", lit_pairs - lit, lit_pairs),
            _measure("local-static-counter", "a lower private local-static N is earlier in source", stat, stat_pairs),
        ],
        "cross_checks": [
            _measure("local-static-counter", "a lower address has a higher N (reverse-address rule)", cross_static, cross_static_pairs),
            _measure("literal-labels", "a lower address has a lower @N (emission order)", cross_literal, cross_literal_pairs),
        ],
        "data": _data_calibration(drafts, derived),
        "counterexamples": counterexamples[:_SHOWN],
        "counterexample_steps": len(counterexamples),
        "displaced": displaced,
        "counterexamples_involving_displaced": {"steps": explained_steps, "pairs": explained_pairs},
        "unplaced_in_dwarf_units": unplaced,
        "copies": _copy_placement(target, derived),
    }


def _data_calibration(drafts: list[dict[str, Any]], derived: dict[str, Any]) -> list[dict[str, Any]]:
    found = {"static_counter": [0, 0], "sinit": [0, 0], "variable": [0, 0]}
    examples: list[dict[str, Any]] = []
    for draft in drafts:
        for region in draft["data"]:
            for field in found:
                rows = [(_int(row["address"]), row[field], row["name"]) for row in region["order"] if field in row]
                good, total = _pairs(rows, lambda a, b: (a[0] < b[0]) == (a[1] < b[1]))
                found[field][0] += good
                found[field][1] += total
                if field == "sinit" and good < total and len(examples) < _SHOWN:
                    ordered = sorted(rows, key=lambda row: row[1])
                    examples.extend(
                        {"unit": draft["unit"], "label": region["label"], "first": a[2], "first_at": hex(a[0]),
                         "then": b[2], "then_at": hex(b[0])}
                        for a, b in zip(ordered, ordered[1:]) if a[0] > b[0]
                    )
    steps = defaultdict(list)
    for row in derived["compile_units"]:
        steps[row["object_unit"]].append((row["die_offset"], row["low_pc"]))
    ascending = total = 0
    for rows in steps.values():
        rows.sort()
        total += len(rows) - 1
        ascending += sum(1 for a, b in zip(rows, rows[1:]) if a[1] < b[1])
    return [
        _measure("local-static-counter", "a lower own N lies at a lower address (data)", *found["static_counter"]),
        _measure("static-initializer", "initialized earlier lies at a lower address", *found["sinit"], counterexamples=examples[:_SHOWN]),
        _measure("dwarf-variable-order", "an earlier file-scope variable DIE lies at a lower address", *found["variable"]),
        _measure("dwarf-function-order", "an earlier function compile-unit DIE has a lower address (steps)", ascending, total),
    ]


def _copy_placement(target: dict[str, Any], derived: dict[str, Any]) -> dict[str, Any]:
    """Kept binding-13 copies: where each sits relative to the first function of its unit that uses it."""

    code, _common = _code_regions(target)
    users = derived["users"]
    found = Counter()
    for unit in target["units"]:
        for section in unit["sections"]:
            if section["region"] not in code:
                continue
            rows = [entry for entry in section["artifacts"] if entry["kind"] == "function"]
            index = {entry["artifact"]: position for position, entry in enumerate(rows)}
            for here, entry in enumerate(rows):
                if entry["class"] != "copy" or entry["binding"] != "13":
                    continue
                seen = sorted(index[site] for site in users.get(entry["artifact"], ()) if site in index)
                if not seen:
                    found["no_user_in_unit"] += 1
                elif seen[0] > here:
                    found["before_first_user"] += 1
                elif all(rows[k]["class"] == "copy" or rows[k]["artifact"] not in derived["lines"] and rows[k]["class"] == "definition"
                         and rows[k]["binding"] == "LOCAL" for k in range(seen[0] + 1, here)):
                    found["right_after_first_user"] += 1
                else:
                    found["after_first_user"] += 1
    total = sum(found.values())
    return {"binding_13": total, **{key: found[key] for key in ("right_after_first_user", "after_first_user", "before_first_user", "no_user_in_unit")}}


def best_rule(calibration: dict[str, Any]) -> list[dict[str, Any]]:
    """The emission rule the calibration supports, each statement with its measurement."""

    functions = {row["evidence"]: row for row in calibration["functions"]}
    cross = {row["evidence"]: row for row in calibration["cross_checks"]}
    data = {row["evidence"]: row for row in calibration["data"]}
    reverse = functions["reverse-address"]
    involved = calibration["counterexamples_involving_displaced"]
    copies = calibration["copies"]
    with_user = copies["binding_13"] - copies["no_user_in_unit"]
    return [
        {"rule": "Out-of-line function definitions are emitted in reverse source order.",
         "measured": f"{reverse['agree']}/{reverse['pairs']} DWARF pairs, {reverse['steps_agree']}/{reverse['steps']} steps, "
                     f"{reverse['units_exact']}/{reverse['units']} units exactly reverse; "
                     f"{cross['local-static-counter']['agree']}/{cross['local-static-counter']['pairs']} local-static pairs on every unit"},
        {"rule": "Exceptions are functions emitted on demand, not at their source position: in-class (implicitly inline) "
                 "members, compiler-generated functions, kept inline copies (after the first function that needs them) "
                 "and WEAK instances (at the end).",
         "measured": f"{involved['pairs']}/{reverse['pairs'] - reverse['agree']} discordant pairs and "
                     f"{involved['steps']}/{calibration['counterexample_steps']} forward steps "
                     f"involve the {len(calibration['displaced'])} displaced functions; "
                     f"{copies['right_after_first_user']}/{with_user} binding-13 copies with a user in their unit sit right after its first user"},
        {"rule": "The local-static counter (name$N, init$N) follows source order; literal labels (@N) follow emission order "
                 "and so corroborate the address order without constraining the source order.",
         "measured": f"local statics {functions['local-static-counter']['agree']}/{functions['local-static-counter']['pairs']} DWARF pairs; "
                     f"@N {functions['literal-labels-reversed']['agree']}/{functions['literal-labels-reversed']['pairs']} DWARF pairs reversed, "
                     f"{cross['literal-labels']['agree']}/{cross['literal-labels']['pairs']} pairs ascending along the address"},
        {"rule": "Data definitions are laid out in source (declaration) order within each region.",
         "measured": f"own local-static N {data['local-static-counter']['agree']}/{data['local-static-counter']['pairs']} pairs; "
                     f"static initializer {data['static-initializer']['agree']}/{data['static-initializer']['pairs']} pairs; "
                     f"DIE order (emission order, {data['dwarf-function-order']['agree']}/{data['dwarf-function-order']['pairs']} "
                     f"function steps) {data['dwarf-variable-order']['agree']}/{data['dwarf-variable-order']['pairs']} variable pairs"},
    ]


# -- the draft ------------------------------------------------------------------------------


def _summary(drafts: list[dict[str, Any]]) -> dict[str, Any]:
    def classes(rows: list[dict[str, Any]]) -> dict[str, int]:
        found = Counter(row["class"] for row in rows)
        return {klass: found[klass] for klass in ADJACENCY_CLASSES}

    function_rows = [row for draft in drafts for row in draft["functions"]["adjacencies"]]
    data_rows = [row for draft in drafts for region in draft["data"] for row in region["adjacencies"]]
    function_chain = [row for draft in drafts for row in draft["functions"]["constraints"]]
    data_chain = [row for draft in drafts for region in draft["data"] for row in region["constraints"]]
    status = {
        scope: {value: sum(1 for draft in drafts if draft["status"][scope] == value) for value in STATUSES}
        for scope in ("functions", "data", "unit")
    }
    return {
        "units": len(drafts),
        "dwarf_units": sum(1 for draft in drafts if draft["dwarf_lines"]),
        "functions": {
            "placed": sum(draft["counts"]["functions"] for draft in drafts),
            "adjacencies": classes(function_rows),
            "conflicts": sum(1 for row in function_rows if row.get("conflicts")),
            "corroborated": sum(1 for row in function_rows if row.get("corroborated_by")),
            "contradicted": sum(1 for row in function_rows if row.get("contradicted_by")),
            "constraints": len(function_chain),
            "constraints_against_draft": sum(1 for row in function_chain if not row["agrees"]),
        },
        "data": {
            "placed": sum(draft["counts"]["data"] for draft in drafts),
            "adjacencies": classes(data_rows),
            "conflicts": sum(1 for row in data_rows if row.get("conflicts")),
            "corroborated": sum(1 for row in data_rows if row.get("corroborated_by")),
            "contradicted": sum(1 for row in data_rows if row.get("contradicted_by")),
            "constraints": len(data_chain),
            "constraints_against_draft": sum(1 for row in data_chain if not row["agrees"]),
        },
        "not_placed": dict(sorted(Counter(row["reason"] for draft in drafts for row in draft["not_placed"]).items())),
        "status": status,
    }


def build_order_draft(target: dict[str, Any], raw: dict[str, Any], selection: dict[str, Any] | None = None) -> dict[str, Any]:
    """The draft of the selected units (all by default); the calibration always covers every unit."""

    derived = derive_evidence(target, raw)
    drafts = [unit_draft(unit, target, derived) for unit in target["units"]]
    calibration = calibrate(target, derived, drafts)
    calibration["best_rule"] = best_rule(calibration)
    if selection:
        names = {row["unit"] for row in select_units(target, **selection)}
        drafts = [draft for draft in drafts if draft["unit"] in names]
    draft = {
        "kind": DRAFT_KIND,
        "schema_version": DRAFT_SCHEMA,
        "rules_version": DRAFT_RULES_VERSION,
        "selection": selection,
        "inputs": {
            "order_sha256": target["order_sha256"],
            "graph_sha256": target["inputs"].get("graph_sha256"),
            "evidence_sha256": evidence_digest(derived),
        },
        "classes": CLASS_MEANING,
        "calibration": calibration,
        "units": drafts,
        "summary": _summary(drafts),
    }
    draft["draft_sha256"] = draft_digest(draft)
    return draft


def headline(draft: dict[str, Any]) -> dict[str, Any]:
    """The counts and calibration rates a report prints."""

    calibration = draft["calibration"]
    return {
        "draft_sha256": draft["draft_sha256"],
        "order_sha256": draft["inputs"]["order_sha256"],
        "calibration": {
            "dwarf_units": calibration["dwarf_units"],
            "functions": {row["evidence"]: f"{row['agree']}/{row['pairs']}" for row in calibration["functions"]},
            "cross_checks": {row["evidence"]: f"{row['agree']}/{row['pairs']}" for row in calibration["cross_checks"]},
            "data": {row["evidence"]: f"{row['agree']}/{row['pairs']}" for row in calibration["data"]},
            "displaced": [f"{row['unit']}:{row['name']}" for row in calibration["displaced"]][:_SHOWN],
            "best_rule": [row["rule"] for row in calibration["best_rule"]],
        },
        **draft["summary"],
    }
