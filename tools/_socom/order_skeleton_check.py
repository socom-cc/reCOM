"""Stage 5 phase B round 2: the static checks of a written skeleton tree (``order skeleton check``, read-only).

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
- **S6** (``--lint``, report only): MSVC ``cl /Zs`` over the written files with a
  small compatibility prelude; headers come in round 3, so its error counts are
  reported, never failed on.
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
                    lint: bool = False) -> dict[str, Any]:
    written = load_write_manifest(target)
    inputs = SkeletonInputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path)
    selection = written["selection"]
    segment = selection.get("segment")
    report: dict[str, Any] = {"kind": "socom-order-skeleton-check", "root": target.name, "selection": selection,
                              "write_sha256": written["write_sha256"]}
    again = SkeletonInputs(root, tracker, manifest_path=manifest_path, snapshot_path=snapshot_path)
    report["determinism"] = _determinism(root, target, inputs, again, written, segment)
    scans = _preview_scans(target, written)
    program = Program(list(scans.values()) + [scan for path, scan in inputs.scans.items() if path not in scans and
                                              (target / path).is_file()], inputs.chains)
    report["s1"] = _s1(target, written, scans, program)
    report["s2"] = _s2(target, written, inputs, scans, program)
    report["s3"] = _s3(root, tracker, target, written)
    report["s4"] = _s4(target, written, inputs)
    report["s5"] = _s5(root, target)
    report["s6"] = _s6(target, written) if lint else {"run": False, "note": "pass --lint for the optional cl /Zs report"}
    checks = ("determinism", "s1", "s2", "s3", "s4", "s5")
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


def _s3(root: Path, tracker: dict[str, Any], target: Path, written: dict[str, Any]) -> dict[str, Any]:
    from .source import audit_docblocks, audit_source_trace, source_artifacts
    from .source_gate import BASELINE_KIND, _digest as gate_digest, _stage_row
    from .source_plan import SOURCE_STAGE

    problems: list[str] = []
    changed, compared = [], 0
    deleted = {row["path"] for row in written["deleted"]}
    for path in sorted((root / "src").rglob("*"), key=lambda value: value.as_posix()):
        if not path.is_file() or path.suffix.lower() not in (".cpp", ".c", ".cc", ".h", ".hpp", ".inc"):
            continue
        relative = path.relative_to(root).as_posix()
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
    for row in written["files"]:
        if row["action"] == "holding":
            _rest, blocks = _authored(target / row["path"])
            if blocks:
                problems.append(f"{row['path']} (holding) holds stage 4 blocks")
    if changed:
        problems.append(f"{len(changed)} files' stage 4 blocks changed: {', '.join(changed[:_SHOWN])}")
    def edges(base: Path) -> list[tuple[str, str, str, str]]:
        return sorted({(row["relation"], row["section"], row["artifact_id"], row["path"]) for row in source_artifacts(base)["artifacts"]})

    before, after = edges(root), edges(target)
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


def _s4(target: Path, written: dict[str, Any], inputs: SkeletonInputs) -> dict[str, Any]:
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
            "problems": problems[:_SHOWN * 2]}


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


def _s6(target: Path, written: dict[str, Any]) -> dict[str, Any]:
    cl, includes = _find_cl()
    if cl is None:
        return {"run": False, "ok": True, "note": "cl.exe not found (set SOCOM_CL or install MSVC); lint skipped"}
    lint = target / "lint"
    lint.mkdir(exist_ok=True)
    prelude = lint / "prelude.h"
    prelude.write_text(LINT_PRELUDE, encoding="utf-8")
    files = [row["path"] for row in written["files"] if row["action"] == "unit"]
    response = lint / "files.rsp"
    response.write_text("\n".join(f'"{target / path}"' for path in files) + "\n", encoding="utf-8")
    environment = dict(os.environ, INCLUDE=";".join(str(path) for path in includes))
    command = [str(cl), "/nologo", "/Zs", "/TP", "/w", f"/FI{prelude}", f"/I{target / 'src'}", f"@{response}"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=lint,
                                   env=environment, check=False, timeout=1800)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"run": False, "ok": True, "note": f"cl /Zs did not run: {type(exc).__name__}"}
    errors: Counter = Counter()
    per_file: Counter = Counter()
    pattern = re.compile(r"^(?P<path>.+?)\((?P<line>\d+)\)\s*: (?:fatal )?error (?P<code>C\d+)")
    base = str(target).lower().replace("/", "\\")
    for line in (completed.stdout + completed.stderr).splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        errors[match.group("code")] += 1
        path = match.group("path").lower().replace("/", "\\")
        per_file[path[len(base) + 1 :] if path.startswith(base) else PurePosixPath(path.replace("\\", "/")).name] += 1
    clean = sum(1 for path in files if not any(key.replace("\\", "/").endswith(path.lower()) for key in per_file))
    return {"run": True, "ok": True, "files": len(files), "files_without_errors": clean, "errors": sum(errors.values()),
            "by_code": dict(errors.most_common(15)), "most_errors": [{"file": path, "errors": count} for path, count in per_file.most_common(10)],
            "note": "report only: headers and class declarations come in round 3, so undeclared names are expected"}


def headline(report: dict[str, Any]) -> dict[str, Any]:
    keep = {
        "determinism": ("ok", "renders_identical", "files_checked", "problems"),
        "s1": ("ok", "checked", "local_statics_checked", "failed", "unverifiable"),
        "s2": ("ok", "units", "mismatches", "mismatches_explained", "unexplained_mismatches", "known_conflict_count",
               "written_order_differs_from_plan_count", "in_class_pending", "positioned_by_owner", "problem_count", "problems"),
        "s3": ("ok", "files_compared", "blocks_changed", "edges", "edge_digest_matches_baseline", "docblocks_ok", "source_trace_ok", "problems"),
        "s4": ("ok", "bodies_checked", "head_rewrites", "snapshot_bodies_landed", "problems"),
        "s5": ("ok", "new_findings"),
        "s6": ("run", "files", "files_without_errors", "errors", "by_code", "note"),
    }
    shown = {"ok": report["ok"], "failed": report["failed"], "write_sha256": report["write_sha256"]}
    for key, fields in keep.items():
        shown[key] = {field: report[key].get(field) for field in fields if field in report[key]}
    shown["s5"]["guards"] = {name: {k: v for k, v in row.items() if k != "new_findings" or v} for name, row in report["s5"]["guards"].items()}
    shown["s2"]["not_written"] = Counter(row["reason"] for row in report["s2"]["not_written"])
    shown["s2"]["known_conflicts"] = [
        f"{row['unit']} {row['region']}: {row['before']} / {row['after']}" + ("" if row["plan_basis_records"] else " (not in the plan's basis)")
        for row in report["s2"]["known_conflicts"]
    ]
    return shown
