"""Stage 5 phase B rounds 2 and 3a: the static checks of a written skeleton tree (``order skeleton check``, read-only).

The check reads a preview written by ``order skeleton write`` (its write
manifest and its ``src/`` mirror), the same verified inputs (skeleton manifest,
body snapshot, accepted order plans, ``src/``) and the ELF.  None of its
results is stage evidence.

- **determinism**: the inputs render the same files twice, byte for byte, and
  those bytes are the files on disk; every other file of the mirror is the
  ``src/`` file; the write manifest is the one the inputs give.
- **S1**: every fenced definition and data entry, parsed back from its written
  file (cxx_scan with the preview's scope and typedef tables), mangles to its
  fence's name; local statics are checked by their declared variable name;
  the members of a function-local class cannot be named out of line and are
  listed as unverifiable (the compiler numbers the class).
- **S2**: the order re-derived from each unit file's fences (a local static or
  local-class member sits at its owner's place) equals the plan's order, and
  under the rule (``order plan validate``'s predictor over the plan's target
  addresses) it gives the target order; every planned row of the unit is
  written exactly once in its own unit and nowhere else; rows the writer could
  not write are listed with their reason; in-class rows are looked up in class
  bodies.  Every local static is written in its manifest owner (one of its
  candidates where several functions reference it).  The local-static order
  conflicts are derived from the plan's region order and the written owners
  (two consecutive statics of a region whose owners the planned function order
  writes the other way round, or file-scope rows between two statics of one
  function); the write manifest must flag exactly these, and a mismatch
  passes only inside a conflict's span.
- **S3**: every stage 4 annotation block is byte-identical to ``src/``'s, the
  ``@socom-artifact`` edges are the same set and keep the stage 4 baseline's
  edge digest, and ``audit docblocks`` / ``audit source-trace`` pass over the
  preview.
- **S4**: every ``body`` entry is its snapshot body byte for byte, or, for a
  recorded head rewrite (BD6, out of line), the recorded new head followed by
  the snapshot body's own text from the end of its declarator; each snapshot
  body lands exactly once.
- **S5**: the source guards find nothing in the preview they do not find in
  ``src/`` (findings compared by rule and line text).
- **S7** (headers, ``--all``): every written header, its generated regions
  stripped, equals its ``src/`` file but for the in-class bodies of out-of-line
  rows, whose declarations are re-derived; a new header is only its include
  guard outside its regions; every region is paired and is the recorded text;
  every planned member (and every own vtable slot member the writer declares)
  is declared exactly once in its class over the whole preview tree.  S1 also
  parses each generated declaration back in its class: the names must be the
  region's recorded ones.
- **S6** (``--lint``, report only): MSVC ``cl /Zs`` over the unit files with a
  small compatibility prelude, with the written headers and (``--all``) without
  them (the same render with the header writer off); unique diagnostics by
  category and code are reported, never failed on.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from .cxx_scan import Program, data_symbols, function_symbol, scan_text
from .mw_mangle import MangleError, mangle, parse_symbol
from .order_skeleton import _digest
from .order_skeleton_write import (
    HELD_FROM,
    WRITE_KIND,
    WRITE_MANIFEST,
    SkeletonInputs,
    _sha,
    parse_fences,
    render_skeletons,
)
from .util import SocomError, load_json

_SHOWN = 12
LINT_PRELUDE = """\
/* order skeleton check --lint: MSVC stand-ins for Metrowerks and GNU spellings (lint only). */
#define _ALLOW_KEYWORD_MACROS 1 /* else MSVC's STL headers stop the file (C1189) at the asm macro below */
#define __attribute__(x)
#define __inline__ __inline
#define __asm__ __asm
#define asm __asm
typedef unsigned __int64 u_long128_lint;
"""


def _mangle(symbol: dict[str, Any] | None) -> str | None:
    if symbol is None:
        return None
    try:
        return mangle(symbol)
    except (MangleError, KeyError, TypeError):
        return None


def _authored(path: Path) -> tuple[str, dict[str, str]]:
    from .source_apply import parse_blocks

    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    _bom, blocks, rest = parse_blocks(text)
    return rest, blocks


def load_write_manifest(target: Path) -> dict[str, Any]:
    path = target / WRITE_MANIFEST
    if not path.is_file():
        raise SocomError(f"{path.name} does not exist under the root: write the preview with order skeleton write first")
    manifest = load_json(path)
    if not isinstance(manifest, dict) or manifest.get("kind") != WRITE_KIND:
        raise SocomError(f"{path.name} is not a {WRITE_KIND}")
    if _digest({key: value for key, value in manifest.items() if key != "write_sha256"}) != manifest.get("write_sha256"):
        raise SocomError(f"{path.name}'s content does not match its write_sha256")
    return manifest


def check_skeletons(root: Path, tracker: dict[str, Any], target: Path, *, manifest_path: Path, snapshot_path: Path,
                    lint: bool = False, source_root: Path | None = None) -> dict[str, Any]:
    """Every static check of a written tree; ``source_root`` holds the ``src/`` it was written from (default: the root's)."""

    base = source_root if source_root is not None else root
    written = load_write_manifest(target)
    inputs = SkeletonInputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path, source_root=source_root)
    selection = written["selection"]
    segment = selection.get("segment")
    report: dict[str, Any] = {"kind": "socom-order-skeleton-check", "root": target.name, "selection": selection,
                              "write_sha256": written["write_sha256"]}
    again = SkeletonInputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path, source_root=source_root)
    report["determinism"] = _determinism(base, target, inputs, again, written, segment)
    scans = _preview_scans(target, written)
    program = Program(list(scans.values()) + [scan for path, scan in inputs.scans.items() if path not in scans and
                                              (target / path).is_file()], inputs.chains)
    report["s1"] = _s1(target, written, scans, program)
    report["s2"] = _s2(target, written, inputs, scans, program)
    report["s3"] = _s3(root, tracker, target, written, base=base)
    report["s4"] = _s4(target, written, inputs, scans, program)
    report["s5"] = _s5(base, target)
    report["s7"] = _s7(target, written, inputs, scans, program)
    report["s1"]["headers"] = report["s7"].pop("s1_headers")
    if not report["s1"]["headers"]["ok"]:
        report["s1"]["ok"] = False
    report["s6"] = _s6(base, target, written, inputs) if lint else {"run": False, "note": "pass --lint for the optional cl /Zs report"}
    checks = ("determinism", "s1", "s2", "s3", "s4", "s5", "s7")
    report["ok"] = all(report[key]["ok"] for key in checks)
    report["failed"] = [key for key in checks if not report[key]["ok"]]
    return report


# -- determinism ---------------------------------------------------------------------------


def _determinism(root: Path, target: Path, inputs: SkeletonInputs, again: SkeletonInputs, written: dict[str, Any],
                 segment: int | None) -> dict[str, Any]:
    """Two renders from independently loaded inputs, compared with each other and with the files on disk."""

    first = render_skeletons(inputs, segment=segment)
    second = render_skeletons(again, segment=segment)
    problems = []
    if first["manifest"]["write_sha256"] != second["manifest"]["write_sha256"] or first["files"] != second["files"]:
        problems.append("two renders of the same inputs differ")
    if first["manifest"]["write_sha256"] != written["write_sha256"]:
        problems.append("the write manifest is not the one the current inputs give (stale preview: write it again)")
    differing, missing, extra = [], [], []
    for relative, data in sorted(first["files"].items()):
        path = target / relative
        if data is None:
            if path.exists():
                extra.append(relative)
        elif not path.is_file():
            missing.append(relative)
        elif path.read_bytes() != data:
            differing.append(relative)
    mirror_changed = []
    source = root / "src"
    for path in sorted(source.rglob("*"), key=lambda value: value.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in first["files"]:
            copy = target / relative
            if not copy.is_file() or copy.read_bytes() != path.read_bytes():
                mirror_changed.append(relative)
    for path in sorted((target / "src").rglob("*"), key=lambda value: value.as_posix()):
        relative = path.relative_to(target).as_posix()
        if path.is_file() and relative not in first["files"] and not (root / relative).is_file():
            extra.append(relative)
    for name, rows in (("files differ from a fresh render", differing), ("rendered files are missing", missing),
                       ("files should not exist", extra), ("mirrored files differ from src/", mirror_changed)):
        if rows:
            problems.append(f"{len(rows)} {name}: {', '.join(rows[:_SHOWN])}")
    return {"ok": not problems, "renders_identical": first["files"] == second["files"],
            "files_checked": len(first["files"]), "problems": problems}


# -- the preview's files -------------------------------------------------------------------


def _preview_scans(target: Path, written: dict[str, Any]) -> dict[str, Any]:
    scans = {}
    for row in written["files"]:
        path = target / row["path"]
        if path.is_file():
            rest, _blocks = _authored(path)
            scans[row["path"]] = scan_text(row["path"], rest)
    return scans


def _entries_by_file(written: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in written["entries"]:
        rows[entry["path"]].append(entry)
    return rows


# -- S1 ------------------------------------------------------------------------------------


def _s1(target: Path, written: dict[str, Any], scans: dict[str, Any], program: Program) -> dict[str, Any]:
    checked, failures, unverifiable, statics = 0, [], [], 0
    units = {row["path"] for row in written["files"] if row["action"] == "unit"}
    for path in sorted(units):
        scan = scans.get(path)
        if scan is None:
            continue
        lines = scan.text.split("\n")
        for fence in parse_fences(scan.text):
            name = fence["name"]
            low, high = fence["line"], fence["end_line"]
            symbol = parse_symbol(name)
            checked += 1
            if symbol["kind"] in ("function", "c_name") and not _is_data(name, written, path):
                found = [row for row in scan.definitions if row.in_class is None and low <= row.line <= high]
                names = [_mangle(function_symbol(program, row.tokens, row.scope, scan.tag).symbol) for row in found]
            else:
                found = [row for row in scan.declarations if row.in_class is None and low <= row.line <= high]
                names = [_mangle(parsed.symbol) for row in found for parsed in data_symbols(program, row.tokens, row.scope, scan.tag)]
            if names != [name]:
                failures.append({"path": path, "name": name, "line": fence["line"], "found": names[:4]})
            for inner in fence["nested"]:
                parsed = parse_symbol(inner["name"])
                if parsed["kind"] == "local_static":
                    statics += 1
                    following = lines[inner["line"]] if inner["line"] < len(lines) else ""
                    if not re.search(r"\bstatic\b.*\b" + re.escape(parsed["variable"]) + r"\b", following):
                        failures.append({"path": path, "name": inner["name"], "line": inner["line"],
                                         "found": [following.strip()[:80]]})
                else:
                    unverifiable.append(inner["name"])
    return {"ok": not failures, "checked": checked, "local_statics_checked": statics, "failed": len(failures),
            "failures": failures[:50], "unverifiable": sorted(unverifiable),
            "note": "members of a function-local class are numbered by the compiler (Local$N): checked in phase C"}


def _is_data(name: str, written: dict[str, Any], path: str) -> bool:
    return any(entry["kind"] == "data" and entry["name"] == name for entry in _entries_by_file(written).get(path, []))


# -- S2 ------------------------------------------------------------------------------------


def _s2(target: Path, written: dict[str, Any], inputs: SkeletonInputs, scans: dict[str, Any], program: Program) -> dict[str, Any]:
    from .order_plan import predict

    selected = [(number, unit) for number, unit in inputs.units
                if "segment" not in written["selection"] or number == written["selection"]["segment"]]
    waiting = {row.get("artifact") for row in written["waiting"]
               if row["kind"] in ("local-static-owner", "initializer-unrenderable", "type-undefined")}
    fences_by_path = {path: parse_fences(scan.text) for path, scan in scans.items()}
    entries = _entries_by_file(written)
    problems: list[str] = []
    explained: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    plan_order: list[dict[str, Any]] = []
    not_written: list[dict[str, Any]] = []
    positioned_by_owner: list[str] = []
    in_class: list[dict[str, Any]] = []
    class_bodies = _class_definitions(scans, inputs, program)
    checked_units = 0
    for number, unit in selected:
        path = unit["workspace_path"]
        fences = fences_by_path.get(path)
        if fences is None:
            problems.append(f"{path} was not written")
            continue
        checked_units += 1
        rank: dict[str, tuple[int, int]] = {}
        owner_of: dict[str, str] = {}  # a local static -> the entry it sits in
        for index, fence in enumerate(fences):
            rank.setdefault(fence["name"], (index, 0))
            for sub, inner in enumerate(fence["nested"], start=1):
                rank.setdefault(inner["name"], (index, sub))
                owner_of.setdefault(inner["name"], fence["name"])
        # Local statics declared in moved bodies have no fence: they sit at their owner's place, in counter order.
        for entry in entries.get(path, []):
            if entry.get("fence") != "body" or entry["name"] not in rank:
                continue
            found = [inner for inner in entry.get("nested") or [] if inner["kind"] == "local-static"
                     and any(flag["kind"] == "local-static-in-body" for flag in inner["flags"])]
            for sub, inner in enumerate(found, start=1):
                rank.setdefault(inner["name"], (rank[entry["name"]][0], sub))
        # A static not written yet (waiting for its type or initializer, or missing from its moved body) still has its
        # owner's place: the write manifest's nesting must agree with the file's, and every owner with the manifest's.
        for entry in entries.get(path, []):
            for inner in entry.get("nested") or []:
                if inner["kind"] != "local-static":
                    continue
                if owner_of.setdefault(inner["name"], entry["name"]) != entry["name"]:
                    problems.append(f"{inner['name']} is written in {owner_of[inner['name']]}, its write-manifest record nests it in {entry['name']}")
        wrong_owner = _owner_problems(unit, owner_of, inputs)
        if wrong_owner:
            problems.append(f"{len(wrong_owner)} local statics of {unit['unit']} are not written in their owner: {', '.join(wrong_owner[:3])}")
        artifact_of = {row["name"]: row["artifact"] for region in unit["data"] for row in region["rows"]}
        places = {name: (rank[owner][0], inputs.data[artifact_of[name]]["structured"].get("number") or 0)
                  for name, owner in owner_of.items() if owner in rank and name in artifact_of}
        rows = [("function", row) for row in unit["functions"]] + [
            ("data", row) for region in unit["data"] for row in region["rows"]
        ]
        # A fence in a unit file names one of that unit's rows (LOCAL names may repeat in other units).
        own = {row["name"] for _kind, row in rows}
        foreign = sorted({name for name in rank if name not in own})
        if foreign:
            problems.append(f"{path} has fences for rows that are not {unit['unit']}'s: {', '.join(foreign[:3])}")
        for kind, row in rows:
            name = row["name"]
            if kind == "function" and row.get("in_class"):
                found = class_bodies.get(name)
                in_class.append({"name": name, "unit": unit["unit"], "class_body": found})
                continue
            count = sum(1 for fence in fences if fence["name"] == name) + sum(
                1 for fence in fences for inner in fence["nested"] if inner["name"] == name)
            if count > 1:
                problems.append(f"{name} is written {count} times in {path}")
            if name not in rank:
                reason = "waiting" if row["artifact"] in waiting else "not in its owner's moved body" if any(
                    inner["name"] == name for entry in entries.get(path, []) for inner in entry.get("nested") or []) else None
                if reason is None:
                    problems.append(f"{name} ({unit['unit']}) is not written")
                not_written.append({"name": name, "unit": unit["unit"], "reason": reason or "missing"})
        addresses = {row["artifact"]: int(row["address"], 16) for _kind, row in rows}
        derived = {"functions": [], "data": []}
        local_members = {row["name"] for row in unit["functions"] if _local(row["name"])}
        for row in unit["functions"]:
            if row.get("in_class"):
                derived["functions"].append(dict(row))
            elif row["name"] in local_members:
                positioned_by_owner.append(row["name"])
                derived["functions"].append({**row, "position": None, "in_class": True, "evidence": {}})
            elif row["name"] in rank:
                derived["functions"].append({**row, "position": rank[row["name"]]})
        for region in unit["data"]:
            derived["data"].append({**region, "rows": [{**row, "position": rank[row["name"]]} for row in region["rows"] if row["name"] in rank]})
        # The written order against the plan's own order.
        written_functions = [row for row in derived["functions"] if not row.get("in_class")]
        plan_functions = {row["name"]: row["position"] for row in unit["functions"] if not row.get("in_class")}
        if [row["name"] for row in sorted(written_functions, key=lambda row: row["position"])] != [
            name for name, _position in sorted(((row["name"], plan_functions[row["name"]]) for row in written_functions), key=lambda item: item[1])
        ]:
            plan_order.append({"unit": unit["unit"], "scope": "functions"})
        for region, original in zip(derived["data"], unit["data"]):
            plan_positions = {row["name"]: row["position"] for row in original["rows"]}
            ordered = [row["name"] for row in sorted(region["rows"], key=lambda row: row["position"])]
            if ordered != sorted(ordered, key=lambda name: plan_positions[name]):
                plan_order.append({"unit": unit["unit"], "scope": original["label"]})
        # Positions as integers for the predictor (ranks are (entry, nested) pairs).
        flat = sorted({value for value in rank.values()})
        index_of = {value: position for position, value in enumerate(flat, start=1)}
        for row in derived["functions"]:
            if isinstance(row.get("position"), tuple):
                row["position"] = index_of[row["position"]]
        for region in derived["data"]:
            for row in region["rows"]:
                row["position"] = index_of[row["position"]]
        found = predict(derived, addresses)
        unit_conflicts = _derived_conflicts(unit, number, rank, places)
        conflicts.extend(unit_conflicts)
        for row in found["mismatches"]:
            record = {"unit": unit["unit"], "segment": number, **row}
            (explained if _explains(unit_conflicts, unit, row) else unexplained).append(record)
    # The writer's flagged conflicts must be exactly the ones the plan data give.
    flagged = {_conflict_key(row) for row in written.get("order_conflicts") or [] if row.get("kind") == "local-static-order-conflict"}
    expected = {_conflict_key(row) for row in conflicts}
    if extra := sorted(flagged - expected):
        problems.append(f"the write manifest flags {len(extra)} local-static order conflicts the plan data do not give: "
                        + "; ".join(" ".join(key) for key in extra[:3]))
    if missing := sorted(expected - flagged):
        problems.append(f"{len(missing)} local-static order conflicts the plan data give are not flagged in the write manifest: "
                        + "; ".join(" ".join(key) for key in missing[:3]))
    if unexplained:
        problems.append(f"{len(unexplained)} rows of the written order differ from the target under the rule outside every "
                        "local-static order conflict")
    pending_in_class = [row for row in in_class if not row["class_body"]]
    return {
        "ok": not problems, "units": checked_units, "mismatches": len(explained) + len(unexplained),
        "mismatches_explained": len(explained), "unexplained_mismatches": unexplained[:_SHOWN],
        "explained_mismatches": explained[:_SHOWN], "known_conflicts": conflicts, "known_conflict_count": len(conflicts),
        "written_order_differs_from_plan": plan_order[:_SHOWN], "written_order_differs_from_plan_count": len(plan_order),
        "not_written": not_written, "positioned_by_owner": sorted(positioned_by_owner),
        "in_class_rows": in_class, "in_class_pending": len(pending_in_class), "problems": problems[:_SHOWN * 2],
        "problem_count": len(problems),
    }


def _owner_problems(unit: dict[str, Any], owner_of: dict[str, str], inputs: SkeletonInputs) -> list[str]:
    """Local statics written outside their manifest owner (or, for one several functions reference, outside its candidates)."""

    artifact_of = {row["name"]: row["artifact"] for row in unit["functions"]}
    found = []
    for region in unit["data"]:
        for row in region["rows"]:
            fence = owner_of.get(row["name"])
            datum = inputs.data.get(row["artifact"]) or {}
            if fence is None or datum.get("storage") != "local-static":
                continue
            owner = datum.get("owner_function") or {}
            allowed = {owner["artifact"]} if owner.get("artifact") else set(owner.get("candidates") or [])
            decision = inputs.decision("local-static-owner", row["artifact"])
            if decision is not None:
                # A static without a usable owner goes where `order skeleton decide --owner` put it.
                allowed.add(artifact_of.get(decision["value"]))
            if artifact_of.get(fence) not in allowed:
                found.append(f"{row['name']} in {fence}")
    return found


def _derived_conflicts(unit: dict[str, Any], segment: int, rank: dict[str, tuple[int, int]],
                       places: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    """The local-static order conflicts the plan's region order and the owners give.

    A region's rows are taken in plan (address) order: the written file-scope
    rows, and every local static at its place ``(owner entry, counter)``; the
    plan's function order fixes the owners' entries.  Two consecutive statics
    conflict when the second one's place comes first, or when file-scope rows
    lie between them and both sit in one function.
    """

    from .order_skeleton_write import plan_basis_mentions

    found = []
    for region in unit["data"]:
        rows = [row for row in sorted(region["rows"], key=lambda row: row["position"])
                if row["name"] in places or rank.get(row["name"], (0, 1))[1] == 0]
        previous, run = None, []
        for row in [*rows, None]:
            if row is not None and row["name"] not in places:
                run.append(row["name"])
                continue
            if previous is not None and row is not None:
                a, b = places[previous["name"]], places[row["name"]]
                if a > b or (run and a[0] >= b[0]):
                    basis = plan_basis_mentions(unit, [previous["name"], row["name"]])
                    found.append({"unit": unit["unit"], "segment": segment, "region": region["label"],
                                  "before": previous["name"], "after": row["name"], "between": run,
                                  "positions": [previous["position"], row["position"]],
                                  "plan_basis_records": bool(basis)})
            previous, run = row, []
    return found


def _explains(conflicts: list[dict[str, Any]], unit: dict[str, Any], mismatch: dict[str, Any]) -> bool:
    """A data mismatch is forced when its pair crosses the plan-order span of one of the region's conflicts.

    The predictor compares rows that are consecutive among the written ones,
    so the pair spans the unwritten rows between them.  It is explained when
    that span and a conflict's span share more than an end point; where every
    row is written, that means the pair lies inside the conflict's span.
    """

    if mismatch.get("scope") != "data":
        return False
    positions = {row["name"]: row["position"] for region in unit["data"] if region["label"] == mismatch["region"] for row in region["rows"]}
    if mismatch["before"] not in positions or mismatch["after"] not in positions:
        return False
    low, high = sorted((positions[mismatch["before"]], positions[mismatch["after"]]))
    return any(row["region"] == mismatch["region"] and max(low, row["positions"][0]) < min(high, row["positions"][1])
               for row in conflicts)


def _conflict_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    before, after = row["before"], row["after"]
    return (row["unit"], row["region"], before["name"] if isinstance(before, dict) else before,
            after["name"] if isinstance(after, dict) else after)


def _local(name: str) -> bool:
    symbol = parse_symbol(name)
    return any("local" in component for component in symbol.get("scope") or [])


def _class_definitions(scans: dict[str, Any], inputs: SkeletonInputs, program: Program) -> dict[str, str]:
    """Mangled name -> where an in-class definition of it is (preview files, then the unchanged headers)."""

    found: dict[str, str] = {}
    pools = list(scans.values()) + [scan for path, scan in sorted(inputs.scans.items()) if path not in scans]
    for scan in pools:
        for klass in scan.classes:
            if not klass.chain or klass.template:
                continue
            for member in klass.members:
                if not hasattr(member, "body_start"):
                    continue
                name = _mangle(function_symbol(program, member.tokens, member.scope, scan.tag, klass=klass.chain).symbol)
                if name:
                    found.setdefault(name, f"{scan.path}:{member.line}")
    return found


# -- S3 ------------------------------------------------------------------------------------


def _s3(root: Path, tracker: dict[str, Any], target: Path, written: dict[str, Any], *, base: Path | None = None) -> dict[str, Any]:
    from .source import audit_docblocks, audit_source_trace, source_artifacts
    from .source_gate import BASELINE_KIND, _digest as gate_digest, _stage_row
    from .source_plan import SOURCE_STAGE

    problems: list[str] = []
    changed, compared = [], 0
    uncanonical: list[str] = []
    written_paths = {row["path"] for row in written["files"]}
    deleted = {row["path"] for row in written["deleted"]}
    source = base if base is not None else root
    for path in sorted((source / "src").rglob("*"), key=lambda value: value.as_posix()):
        if not path.is_file() or path.suffix.lower() not in (".cpp", ".c", ".cc", ".h", ".hpp", ".inc"):
            continue
        relative = path.relative_to(source).as_posix()
        _rest, blocks = _authored(path)
        copy = target / relative
        if relative in deleted:
            if blocks:
                problems.append(f"{relative} holds stage 4 blocks but was removed")
            continue
        if not copy.is_file():
            problems.append(f"{relative} is missing from the preview")
            continue
        _rest2, written_blocks = _authored(copy)
        compared += 1
        if written_blocks != blocks:
            changed.append(relative)
        elif written_blocks and relative in written_paths:
            # Stage 4's own form (blocks, one blank line, the rest): otherwise `source annotate --check` reports drift.
            from .source_apply import render_file

            text = copy.read_bytes().decode("utf-8").replace("\r\n", "\n")
            if render_file(text, {}, set(), assembly=relative.casefold().endswith(".s")) != text:
                uncanonical.append(relative)
    for row in written["files"]:
        if row["action"] == "holding":
            _rest, blocks = _authored(target / row["path"])
            if blocks:
                problems.append(f"{row['path']} (holding) holds stage 4 blocks")
    if changed:
        problems.append(f"{len(changed)} files' stage 4 blocks changed: {', '.join(changed[:_SHOWN])}")
    if uncanonical:
        problems.append(f"{len(uncanonical)} files are not in stage 4's block form (source annotate would report drift): "
                        + ", ".join(uncanonical[:_SHOWN]))
    def edges(base: Path) -> list[tuple[str, str, str, str]]:
        return sorted({(row["relation"], row["section"], row["artifact_id"], row["path"]) for row in source_artifacts(base)["artifacts"]})

    before, after = edges(source), edges(target)
    if before != after:
        problems.append(f"the @socom-artifact edges differ ({len(before)} in src/, {len(after)} in the preview)")
    stage = _stage_row(tracker, SOURCE_STAGE)
    baseline = stage.get("baseline") or {}
    recorded = ((baseline.get("state") or {}).get("annotations") or {}).get("sha256") if baseline.get("kind") == BASELINE_KIND else None
    digest = gate_digest([list(edge) for edge in after])
    if recorded and digest != recorded:
        problems.append("the preview's annotation edges do not keep the stage 4 baseline's edge digest")
    docblocks = audit_docblocks(root, source_root=target)
    trace = audit_source_trace(root, source_root=target)
    for name, result in (("audit docblocks", docblocks), ("audit source-trace", trace)):
        if not result["ok"]:
            problems.append(f"{name} fails over the preview: " + "; ".join(result["errors"][:3]))
    return {"ok": not problems, "files_compared": compared, "blocks_changed": len(changed), "edges": len(after),
            "edge_digest_matches_baseline": recorded is not None and digest == recorded,
            "docblocks_ok": docblocks["ok"], "source_trace_ok": trace["ok"], "problems": problems}


# -- S4 ------------------------------------------------------------------------------------


def _inner(text: str) -> str:
    """An entry's text without the namespace / extern "C" lines the writer wrapped it in."""

    lines = text.split("\n")
    opened = 0
    while opened < len(lines) and re.fullmatch(r'(?:namespace(?: \w+)? \{|extern "C" \{)', lines[opened]):
        opened += 1
    if opened:
        if lines[len(lines) - opened :] != ["}"] * opened:
            return text
        lines = lines[opened : len(lines) - opened]
    return "\n".join(lines)


def _s4(target: Path, written: dict[str, Any], inputs: SkeletonInputs, scans: dict[str, Any], program: Program) -> dict[str, Any]:
    from .order_skeleton_headers import class_member_names

    problems: list[str] = []
    landed: Counter = Counter()
    checked = rewrites = 0
    by_key = {(entry["path"], entry["name"]): entry for entry in written["entries"] if entry.get("fence") == "body" or
              entry["kind"].startswith("held-")}
    statements = {}
    for path, record in inputs.files.items():
        scan = inputs.scans[path]
        for declaration in scan.declarations:
            if declaration.in_class is None:
                statements[f"{path}:{declaration.line}"] = scan.text[declaration.start : declaration.end]
    for row in written["files"]:
        path = target / row["path"]
        if not path.is_file():
            continue
        rest, _blocks = _authored(path)
        for fence in parse_fences(rest):
            if fence["kind"] != "body":
                continue
            entry = by_key.get((row["path"], fence["name"]))
            if entry is None:
                problems.append(f"{row['path']}: body {fence['name']} has no write-manifest record")
                continue
            checked += 1
            source = entry["source"]
            text = fence["text"]
            held = HELD_FROM.format(source=source)
            if entry["kind"].startswith("held-"):
                if not text.startswith(held + "\n"):
                    problems.append(f"{row['path']}: held {fence['name']} does not start with its provenance line")
                    continue
                text = text[len(held) + 1 :]
            inner = _inner(text)
            if source in inputs.texts:
                landed[source] += 1
                original = inputs.texts[source]["text"]
                head = entry.get("head")
                if head:
                    rewrites += 1
                    tail = original[len(head["from"]) :]
                    if not inner.startswith(head["to"]) or inner[len(head["to"]) :] != tail or _sha(tail) != entry["body_sha256"]:
                        problems.append(f"{row['path']}: {fence['name']} is not its rewritten head and its snapshot body ({source})")
                elif _sha(inner) != inputs.texts[source]["sha256"]:
                    problems.append(f"{row['path']}: {fence['name']} differs from its snapshot body {source}")
            elif source in statements:
                if inner != statements[source]:
                    problems.append(f"{row['path']}: {fence['name']} differs from its provisional statement {source}")
            else:
                problems.append(f"{row['path']}: {fence['name']} cites an unknown source {source}")
    expected = set()
    selection = written["selection"]
    segment_units = None if "all" in selection else {unit["unit"] for number, unit in inputs.units if number == selection["segment"]}
    for body in inputs.manifest["bodies"]["definitions"]:
        if body["action"] == "preamble":
            continue
        if segment_units is None or (body.get("row") or {}).get("unit") in segment_units:
            expected.add(body["id"])
    # An in-class body moved out of line lands once: the header must keep only its declaration (headers: --all).
    header_bodies = 0
    if written.get("headers") is not None:
        replaced = {row["body"] for row in written["headers"]["replacements"]}
        for body in inputs.manifest["bodies"]["definitions"]:
            if body["action"] != "move-out-of-line":
                continue
            header_bodies += 1
            if body["id"] not in replaced:
                problems.append(f"{body['id']}: the header's in-class body of {body['mangled']} is not replaced by its declaration")
                continue
            scan = scans.get(body["path"])
            if scan is not None and any(name == body["mangled"] and kind == "definition" for klass in scan.classes
                                        if klass.chain and not klass.template for name, _line, kind in class_member_names(program, scan, klass)):
                problems.append(f"{body['id']}: {body['mangled']} lands twice (its in-class body is still in the header)")
    missing = sorted(identity for identity in expected if landed[identity] == 0)
    if segment_units is not None:
        missing = [identity for identity in missing if inputs.bodies[identity]["action"] in ("move-in-place", "cross-file-move",
                                                                                            "move-out-of-line", "bd6-declarator-rewrite")]
    twice = sorted(identity for identity, count in landed.items() if count > 1)
    if missing:
        problems.append(f"{len(missing)} snapshot bodies did not land: {', '.join(missing[:_SHOWN])}")
    if twice:
        problems.append(f"{len(twice)} snapshot bodies landed more than once: {', '.join(twice[:_SHOWN])}")
    return {"ok": not problems, "bodies_checked": checked, "head_rewrites": rewrites, "snapshot_bodies_landed": len(landed),
            "header_bodies_replaced": header_bodies, "problems": problems[:_SHOWN * 2]}


# -- S5 ------------------------------------------------------------------------------------


def _s5(root: Path, target: Path) -> dict[str, Any]:
    from .guards import GUARDS, run_guard

    rows = {}
    new_total = 0
    for name in sorted(GUARDS):
        before = run_guard(root, name)
        after = run_guard(target, name)
        baseline = Counter((row["rule"], row["text"]) for row in before["findings"] if row["path"].startswith("src/"))
        found = Counter((row["rule"], row["text"]) for row in after["findings"])
        new = found - baseline
        new_total += sum(new.values())
        rows[name] = {"src": sum(baseline.values()), "preview": after["count"], "new": sum(new.values()),
                      "new_findings": [{"rule": rule, "text": text} for (rule, text) in sorted(new)][:_SHOWN]}
    return {"ok": new_total == 0, "new_findings": new_total, "guards": rows}


# -- S7 ------------------------------------------------------------------------------------


def _s7(target: Path, written: dict[str, Any], inputs: SkeletonInputs, scans: dict[str, Any], program: Program) -> dict[str, Any]:
    """Headers: content outside the regions equals src/ but for the re-derived in-class replacements; members once."""

    from .order_skeleton_headers import class_member_names, parse_regions, replacement_declaration, strip_regions

    headers = written.get("headers")
    if headers is None:
        note = "headers are written by --all; this preview has none"
        return {"ok": True, "run": False, "note": note, "s1_headers": {"ok": True, "run": False, "note": note}}
    problems: list[str] = []
    records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in headers["regions"]:
        records[row["path"]].append(row)
    regions_found: dict[str, list[dict[str, Any]]] = {}
    texts: dict[str, str] = {}
    header_rows = [row for row in written["files"] if row["action"] in ("header", "new-header")]
    region_paths = sorted({row["path"] for row in headers["regions"]})
    for path in sorted({row["path"] for row in header_rows} | set(region_paths)):
        copy = target / path
        if not copy.is_file():
            problems.append(f"{path} was not written")
            continue
        rest, _blocks = _authored(copy)
        texts[path] = rest
        found, fence_problems = parse_regions(rest)
        problems.extend(f"{path}: {problem}" for problem in fence_problems)
        regions_found[path] = found
        expected = records.get(path, [])
        if [row["name"] for row in found] != [row["name"] for row in expected]:
            problems.append(f"{path}: its regions ({len(found)}) are not the {len(expected)} the write manifest records")
            continue
        lines = rest.split("\n")
        for region, record in zip(found, expected):
            if _sha("\n".join(lines[region["start"] : region["end"] + 1])) != record["region_sha256"]:
                problems.append(f"{path}: region {region['name']} (line {region['start'] + 1}) differs from its recorded text")
    identical = 0
    for row in header_rows:
        path = row["path"]
        if path not in texts:
            continue
        found = regions_found[path]
        splits = {index for index, record in enumerate(records.get(path, [])) if record.get("split")}
        stripped = strip_regions(texts[path], found, splits)
        source = inputs.scans.get(path)
        if source is None:
            guard = re.sub(r"\W", "_", PurePosixPath(path).name).upper()
            expected = f"#ifndef {guard}\n#define {guard}\n#endif\n"
        else:
            edits = []
            for body in inputs.manifest["bodies"]["definitions"]:
                if body["action"] != "move-out-of-line" or body["path"] != path:
                    continue
                definition = next((item for item in source.definitions if item.in_class is not None and item.line == body["span"]["start_line"]
                                   and _sha(source.text[item.start : item.end]) == body["sha256"]), None)
                if definition is None:
                    problems.append(f"{body['id']}: the in-class body is not in src/")
                    continue
                signature = inputs.signatures.get((body.get("row") or {}).get("artifact"))
                edits.append((definition.start, definition.end, replacement_declaration(inputs.program, source, definition, signature)[0]))
            from .order_skeleton_headers import apply_edits

            expected = apply_edits(source.text, edits)
        if stripped != expected:
            got, want = stripped.split("\n"), expected.split("\n")
            line = next((index for index, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
            problems.append(f"{path}: outside its regions it differs from src/ (line {line + 1} of the stripped text)")
        else:
            identical += 1
    # Every planned member is declared exactly once in its class (all bodies of the preview tree).
    pools = list(scans.values()) + [scan for path, scan in sorted(inputs.scans.items()) if path not in scans and (target / path).is_file()]
    declared: dict[tuple[str, ...], Counter] = defaultdict(Counter)
    for scan in pools:
        for klass in scan.classes:
            if klass.chain and not klass.template:
                declared[tuple(klass.chain)].update(name for name, _line, _kind in class_member_names(program, scan, klass))
    # Classes the writer lists as waiting are not written: S7 reports them through the waiting list, not as missing.
    skipped = {row["type"] for row in headers["waiting"]
               if row["kind"] in ("provider-declaration", "function-local-class", "class-unplaced", "nested-in-unwritten-class")}
    unspelled = {row.get("name") for row in headers["waiting"] if row["kind"] == "declaration-unspelled"}
    missing, twice, checked, classes = [], [], 0, 0
    for record in inputs.manifest["declarations"]["classes"]:
        if record["class"] in skipped:
            continue
        chain = tuple(record["chain"])
        wanted = {row["name"] for row in record["members_to_add"]} | set(record.get("members_declared_names") or [])
        wanted |= {row["name"] for row in record["static_data_members"] if row["declared"] or row.get("declaration")}
        wanted |= {row["member"] for row in (record.get("vtable") or {}).get("declare_virtual") or [] if row.get("declared") or row.get("declaration")}
        wanted -= unspelled
        classes += 1
        for name in sorted(wanted):
            checked += 1
            count = declared[chain][name]
            if count == 0:
                missing.append(f"{record['class']}: {name}")
            elif count > 1:
                twice.append(f"{record['class']}: {name} ({count})")
    if missing:
        problems.append(f"{len(missing)} planned members are not declared in their class: {', '.join(missing[:_SHOWN])}")
    if twice:
        problems.append(f"{len(twice)} planned members are declared more than once: {', '.join(twice[:_SHOWN])}")
    return {"ok": not problems, "run": True, "files": len(header_rows), "files_identical_outside_regions": identical,
            "new_headers": sum(1 for row in header_rows if row["action"] == "new-header"), "regions": len(headers["regions"]),
            "replacements": len(headers["replacements"]), "classes_checked": classes, "members_checked": checked,
            "members_missing": len(missing), "members_declared_twice": len(twice), "problems": problems[: _SHOWN * 2],
            "problem_count": len(problems), "s1_headers": _s1_headers(texts, regions_found, records, program)}


def _s1_headers(texts: dict[str, str], found: dict[str, list[dict[str, Any]]], records: dict[str, list[dict[str, Any]]],
                program: Program) -> dict[str, Any]:
    """Each generated declaration, parsed back in its class with the preview's tables, mangles to a recorded name."""

    from .order_skeleton_headers import class_member_names

    failures: list[dict[str, Any]] = []
    checked = 0
    for path, regions in sorted(found.items()):
        if [row["name"] for row in regions] != [row["name"] for row in records.get(path, [])]:
            continue
        scan = scan_text(path, texts[path])
        for region, record in zip(regions, records.get(path, [])):
            low, high = region["start"] + 1, region["end"] + 1
            groups = [(record.get("chain"), record["members"] + record["static_members"])]
            groups += [(row["chain"], row["members"] + row["static_members"]) for row in record["nested"]]
            for chain, names in groups:
                if not names:
                    continue
                got: Counter = Counter()
                for klass in scan.classes:
                    if klass.chain == tuple(chain or ()) and not klass.template:
                        got.update(name for name, line, _kind in class_member_names(program, scan, klass) if low <= line <= high)
                checked += len(names)
                want = Counter(names)
                if got != want:
                    failures.append({"path": path, "region": record["name"], "line": low,
                                     "missing": sorted(want - got)[:4], "unexpected": sorted(got - want)[:4]})
    return {"ok": not failures, "run": True, "checked": checked, "failed": len(failures), "failures": failures[:_SHOWN * 2]}


# -- S6 ------------------------------------------------------------------------------------


def _find_cl() -> tuple[Path | None, list[Path]]:
    """(cl.exe, include directories) from SOCOM_CL or vswhere; never recorded in the report."""

    candidates = []
    configured = os.environ.get("SOCOM_CL")
    if configured:
        candidates.append(Path(configured))
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if vswhere.is_file():
        try:
            found = subprocess.run([str(vswhere), "-latest", "-products", "*", "-find", "VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe"],
                                   capture_output=True, text=True, check=False, timeout=60).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            found = []
        candidates.extend(Path(row.strip()) for row in sorted(found, reverse=True) if row.strip())
    cl = next((path for path in candidates if path.is_file()), None)
    if cl is None:
        return None, []
    includes = [cl.parents[3] / "include"]
    kits = Path(os.environ.get("ProgramFiles(x86)", "")) / "Windows Kits" / "10" / "Include"
    if kits.is_dir():
        versions = sorted((child for child in kits.iterdir() if child.is_dir()), key=lambda value: value.name)
        if versions:
            includes += [versions[-1] / "ucrt", versions[-1] / "um", versions[-1] / "shared"]
    return cl, [path for path in includes if path.is_dir()]


# The categories S6 reports MSVC's error codes in (anything else counts as "other").
LINT_CATEGORIES = {
    "undeclared name": ("C2065", "C3861", "C2653", "C2871", "C2039", "C2510", "C3083"),
    "incomplete or unknown type": ("C2027", "C2079", "C2061", "C4430", "C2146", "C2143", "C2133", "C2512", "C2504", "C2501"),
    "declaration mismatch": ("C2511", "C2556", "C2371", "C2084", "C2086", "C2365", "C2040", "C2556", "C2597", "C2350", "C2373"),
    "conversion or call": ("C2664", "C2440", "C2660", "C2662", "C2665", "C2668", "C2672", "C2100", "C2228", "C2227", "C2819"),
    "syntax": ("C2059", "C2144", "C2238", "C2062", "C2447", "C2601", "C2629", "C2470"),
    "fatal": ("C1003", "C1004", "C1083", "C1075"),
}


def _lint_tree(cl: Path, includes: list[Path], tree: Path, files: list[str], work: Path) -> dict[str, Any]:
    """``cl /Zs`` over the unit files of one tree: error counts by code, category and file."""

    work.mkdir(parents=True, exist_ok=True)
    prelude = work / "prelude.h"
    prelude.write_text(LINT_PRELUDE, encoding="utf-8")
    response = work / "files.rsp"
    response.write_text("\n".join(f'"{tree / path}"' for path in files) + "\n", encoding="utf-8")
    environment = dict(os.environ, INCLUDE=";".join(str(path) for path in includes))
    command = [str(cl), "/nologo", "/Zs", "/TP", "/w", f"/FI{prelude}", f"/I{tree / 'src'}", f"@{response}"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=work,
                                   env=environment, check=False, timeout=3600)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"run": False, "note": f"cl /Zs did not run: {type(exc).__name__}"}
    errors: Counter = Counter()
    per_file: Counter = Counter()
    unique: set[tuple[str, str, str]] = set()
    by_unit: dict[str, set[str]] = defaultdict(set)  # unit file -> the files its diagnostics are in
    pattern = re.compile(r"^(?P<path>.+?)\((?P<line>\d+)\)\s*: (?:fatal )?error (?P<code>C\d+)")
    base = str(tree).lower().replace("/", "\\")
    current = None
    for line in (completed.stdout + completed.stderr).splitlines():
        stripped = line.strip()
        if stripped and "(" not in stripped and stripped.lower().endswith((".cpp", ".c", ".cc")):
            current = stripped.lower()  # cl echoes each source file's name before its diagnostics
            continue
        match = pattern.match(stripped)
        if not match:
            continue
        errors[match.group("code")] += 1
        path = match.group("path").lower().replace("/", "\\")
        where = path[len(base) + 1 :] if path.startswith(base) else PurePosixPath(path.replace("\\", "/")).name
        per_file[where] += 1
        unique.add((where, match.group("line"), match.group("code")))
        if current:
            by_unit[current].add(where)
    category_of = {code: name for name, codes in LINT_CATEGORIES.items() for code in codes}
    categories: Counter = Counter()
    for _where, _line, code in unique:
        categories[category_of.get(code, "other")] += 1
    names = {PurePosixPath(path).name.lower() for path in files}
    clean = len(names - set(by_unit))
    in_headers = sum(1 for where, _line, _code in unique if not where.endswith((".cpp", ".c", ".cc")))
    return {"run": True, "files": len(files), "files_without_errors": clean, "errors": sum(errors.values()),
            "unique_errors": len(unique), "unique_errors_in_headers": in_headers,
            "by_category": dict(sorted(categories.items(), key=lambda item: (-item[1], item[0]))),
            "by_code": dict(Counter(code for _where, _line, code in unique).most_common(15)),
            "most_errors": [{"file": path, "errors": count} for path, count in per_file.most_common(10)],
            "count": "by_category and by_code count unique diagnostics (file, line, code): a header's error counts once"}


def _s6(root: Path, target: Path, written: dict[str, Any], inputs: SkeletonInputs) -> dict[str, Any]:
    """Report only: the unit files linted with the written headers, and (``--all``) without them (the round 2 tree)."""

    import shutil

    cl, includes = _find_cl()
    if cl is None:
        return {"run": False, "ok": True, "note": "cl.exe not found (set SOCOM_CL or install MSVC); lint skipped"}
    files = [row["path"] for row in written["files"] if row["action"] == "unit"]
    lint = target / "lint"
    after = _lint_tree(cl, includes, target, files, lint / "after")
    report: dict[str, Any] = {"run": after.get("run", False), "ok": True, "after": after,
                              "note": "report only: MSVC is not the target compiler; nothing fails on it"}
    if written.get("headers") is None:
        return report
    # The same tree without the header writer: a mirror of src/ with the round 2 render.
    before_tree = lint / "before"
    if before_tree.exists():
        shutil.rmtree(before_tree)
    rendered = render_skeletons(inputs, segment=None, headers=False)
    for path in sorted((root / "src").rglob("*"), key=lambda value: value.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_file() and relative not in rendered["files"]:
            destination = before_tree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    for relative, data in rendered["files"].items():
        if data is not None:
            destination = before_tree / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    before = _lint_tree(cl, includes, before_tree, files, lint / "before-work")
    report["before"] = before
    if before.get("run") and after.get("run"):
        categories = sorted(set(before["by_category"]) | set(after["by_category"]))
        report["by_category"] = {name: {"before": before["by_category"].get(name, 0), "after": after["by_category"].get(name, 0)}
                                 for name in categories}
        for key in ("errors", "unique_errors", "unique_errors_in_headers", "files_without_errors"):
            report[key] = {"before": before[key], "after": after[key]}
    return report


def headline(report: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "determinism": ("ok", "renders_identical", "files_checked", "problems"),
        "s1": ("ok", "checked", "local_statics_checked", "failed", "unverifiable"),
        "s2": ("ok", "units", "mismatches", "mismatches_explained", "unexplained_mismatches", "known_conflict_count",
               "written_order_differs_from_plan_count", "in_class_pending", "positioned_by_owner", "problem_count", "problems"),
        "s3": ("ok", "files_compared", "blocks_changed", "edges", "edge_digest_matches_baseline", "docblocks_ok", "source_trace_ok", "problems"),
        "s4": ("ok", "bodies_checked", "head_rewrites", "snapshot_bodies_landed", "header_bodies_replaced", "problems"),
        "s5": ("ok", "new_findings"),
        "s7": ("ok", "run", "files", "files_identical_outside_regions", "new_headers", "regions", "replacements", "classes_checked",
               "members_checked", "members_missing", "members_declared_twice", "problem_count", "problems", "note"),
        "s6": ("run", "errors", "unique_errors", "unique_errors_in_headers", "files_without_errors", "by_category", "note"),
    }
    shown = {"ok": report["ok"], "failed": report["failed"], "write_sha256": report["write_sha256"]}
    for key, fields in keep.items():
        shown[key] = {field: report[key].get(field) for field in fields if field in report[key]}
    shown["s5"]["guards"] = {name: {k: v for k, v in row.items() if k != "new_findings" or v} for name, row in report["s5"]["guards"].items()}
    shown["s1"]["headers"] = {key: value for key, value in report["s1"].get("headers", {}).items() if key != "failures" or value}
    if report["s6"].get("after") and "errors" not in shown["s6"]:
        shown["s6"].update({key: report["s6"]["after"].get(key) for key in ("errors", "files_without_errors", "by_category")})
    shown["s2"]["not_written"] = Counter(row["reason"] for row in report["s2"]["not_written"])
    shown["s2"]["known_conflicts"] = [
        f"{row['unit']} {row['region']}: {row['before']} / {row['after']}" + ("" if row["plan_basis_records"] else " (not in the plan's basis)")
        for row in report["s2"]["known_conflicts"]
    ]
    return shown
