"""Read-only scan for live signatures that contradict the ELF facts (stage 3).

Some live signatures came from Ghidra's built-in library archives (glibc
order and types) and were never proven; a group whose row stays unresolved
leaves them live.  ``live_contradictions`` lists every group function whose
live signature makes a claim the facts disprove:

* ``registers``: an argument register the code reads before writing it, on
  some path, that the live signature does not declare (``recon facts``
  ``argument_reads``; dead entry reads an accepted plan declares are dropped,
  and a varargs signature covers registers after its fixed parameters);
* ``count`` / ``type``: the Metrowerks mangled signature has another
  parameter count or varargs, or a parameter of another shape: pointer depth,
  float versus integer register, builtin width, or a scalar where the mangled
  type is a class (class names are not compared);
* ``drift``: an applied group's plan set a prototype that the live signature
  no longer shows;
* ``recorded``: a reviewed plan row records that the live signature is wrong.

Ghidra's default signature (``undefined FUN(void)``, no convention) claims
nothing and ``undefined*`` parameter types claim no type.  Live types whose
only definition lies outside ``/project`` (Ghidra's archives) are listed as
``library types``; they are not a contradiction by themselves.  Nothing is
written to Ghidra or the tracker.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .batch_apply import (
    BUILTIN_SIZES,
    BUILTINS,
    CALLING_CONVENTION,
    UNDEFINED_TYPES,
    _base_type,
    _declared_argument_registers,
    _SIGNATURE_LINE,
    _Types,
    expected_signature,
    parse_signature,
)
from .mwdemangle import demangle
from .util import SocomError, load_json

APPLIED_STATUSES = frozenset({"accepted", "awaiting_acceptance"})
_GPR = {4: "a0", 5: "a1", 6: "a2", 7: "a3", 8: "t0", 9: "t1", 10: "t2", 11: "t3"}
_REGISTER = {name: number for number, name in _GPR.items()} | {f"f{n}": 100 + n for n in range(12, 20)}
# Wording a reviewed plan uses when it records a wrong live signature.
_RECORDED = re.compile(
    r"live (?:signature|prototype)[^;]*?(?:contradict|disagree|wrong width|no (?:program )?evidence|library type archive|glibc)"
    r"|(?:contradict|disagree|different \d+-byte type|wrong width)[^;]*?live (?:signature|prototype)"
    r"|in the live (?:signature|prototype) is a different",
    re.IGNORECASE,
)
_BUILTIN_NAMES = frozenset(BUILTINS.values()) | frozenset(BUILTIN_SIZES)


def _slug(item_id: str) -> str:
    return item_id.replace("socom:", "socom-").replace(":", "-")


def _live_shape(type_name: str) -> tuple | None:
    """(pointer depth, kind, builtin, size) of a printed live type, or None if unknown."""

    base = _base_type(type_name)
    if base in UNDEFINED_TYPES or "[" in type_name:
        return None
    depth = type_name.count("*")
    if base in _BUILTIN_NAMES:
        return (depth, "builtin", base, BUILTIN_SIZES.get(base))
    return (depth, "other", None, None)


def _shape_conflict(live: tuple | None, mangled: tuple | None) -> str | None:
    if live is None or mangled is None:
        return None
    if live[0] != mangled[0]:
        return f"pointer depth {live[0]} vs {mangled[0]}"
    if live[0]:
        return None
    if mangled[1] == "builtin" and live[1] == "builtin":
        if (live[2] == "float") != (mangled[2] == "float"):
            return f"{live[2]} vs {mangled[2]} (float and integer registers differ)"
        if live[3] and mangled[3] and live[3] != mangled[3]:
            return f"{live[2]} ({live[3]} bytes) vs {mangled[2]} ({mangled[3]} bytes)"
        return None
    if mangled[1] == "class" and live[1] == "builtin":
        return f"scalar {live[2]} where the mangled type is a class passed by value"
    return None


def _mangled_conflicts(names: list[str], live: dict[str, Any]) -> list[str]:
    mangled = next((name for name in names if demangle(name)), None)
    parsed = demangle(mangled) if mangled else None
    if not parsed or parsed.get("params") is None:
        return []
    params = list(parsed["params"])
    if params == [{"modifiers": [], "kind": "builtin", "name": "void"}]:
        params = []
    varargs = bool(params) and params[-1].get("kind") == "builtin" and params[-1].get("name") == "..."
    if varargs:
        params = params[:-1]
    shown = list(live["parameters"])
    if parsed.get("qualifier") and shown and shown[0][1] == "this":
        shown = shown[1:]
    # Destructors (and their @N@__dt adjustor thunks) take the hidden flags.
    if str(parsed.get("name")).endswith("__dt") and shown and shown[-1][1] == "__dtor_flags":
        shown = shown[:-1]
    found = []
    if len(shown) != len(params):
        found.append(f"count: {mangled} has {len(params)} parameters, the live signature {len(shown)}")
    if varargs != live["varargs"]:
        found.append(f"count: {mangled} {'ends' if varargs else 'does not end'} in '...', the live signature "
                     f"{'does' if live['varargs'] else 'does not'}")
    for position, ((live_type, live_name), value) in enumerate(zip(shown, params), 1):
        conflict = _shape_conflict(_live_shape(live_type), _Types.mangled_shape(value))
        if conflict:
            found.append(f"type: parameter {position} {live_type} {live_name}: {conflict} ({mangled})")
    return found


def _register_conflicts(reads: dict[str, list[int]], live: dict[str, Any], dead: set[str]) -> list[str]:
    declared_g, declared_f = _declared_argument_registers({"parameters": [{"type": t} for t, _ in live["parameters"]]})
    declared = declared_g | {100 + reg for reg in declared_f}
    found = []
    for register, sites in reads.items():
        number = _REGISTER.get(register)
        if number is None or register in dead or number in declared:
            continue
        if live["varargs"] and (
            (number < 100 and number > max(declared_g, default=3))
            or (number >= 100 and number - 100 > max(declared_f, default=11))
        ):
            continue
        found.append(
            f"registers: {register} is read before any write (0x{sites[0]:x}) but the live signature declares "
            f"{len(live['parameters'])} parameter(s)"
        )
    return found


def _planned_signature(prototype: dict[str, Any]) -> dict[str, Any]:
    return parse_signature(
        expected_signature(
            {
                "calling_convention": CALLING_CONVENTION,
                "parameters": prototype.get("parameters") or [],
                "return_type": prototype.get("return_type") or "",
                "varargs": prototype.get("partial") and prototype.get("varargs"),
            },
            "planned",
        )
    ) or {}


def live_contradictions(
    root: Path,
    tracker: dict[str, Any],
    *,
    groups: str = "all",
    signatures: dict[int, str] | None = None,
    type_paths: dict[str, list[str]] | None = None,
    bridge_url: str | None = None,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Every group function whose live signature contradicts the facts.

    ``signatures`` (address -> Signature line) and ``type_paths`` (type name
    -> live paths) come from a fingerprint; otherwise they are read live.
    """

    from .recon_facts import argument_reads, context

    if groups not in ("all", "applied"):
        raise SocomError("--groups is applied or all")
    items = {row["id"]: row for row in tracker["work_items"]}
    plans = [row for row in tracker["work_items"] if row.get("kind") == "recon-plan-group"]
    if not plans:
        raise SocomError("the tracker has no reconstruction groups")
    owner: dict[int, dict[str, Any]] = {}
    for plan in plans:
        apply = items.get(f"{plan['id']}-apply") or {}
        info = {
            "group": plan["id"],
            "group_number": plan["batch"].get("group_number"),
            "plan_status": plan.get("status"),
            "apply_status": apply.get("status"),
            "applied": apply.get("status") in APPLIED_STATUSES,
            "plan_path": root / "build" / "recon-plans" / f"{_slug(plan['id'])}.json",
        }
        for value in plan["batch"]["functions"]:
            owner[int(value, 16)] = info
    wanted = sorted(address for address, info in owner.items() if groups == "all" or info["applied"])
    rows_by_plan: dict[Path, dict[int, dict[str, Any]]] = {}

    def plan_row(info: dict[str, Any], address: int) -> dict[str, Any] | None:
        path = info["plan_path"]
        if path not in rows_by_plan:
            rows_by_plan[path] = {}
            if path.is_file():
                try:
                    plan = load_json(path)
                except SocomError:
                    plan = {}
                for row in plan.get("functions", []) if isinstance(plan, dict) else []:
                    try:
                        rows_by_plan[path][int(str(row.get("address")), 16)] = row
                    except ValueError:
                        continue
        return rows_by_plan[path].get(address)

    if signatures is None or type_paths is None:
        from .ghidra import GhidraBridge, _type_index

        bridge = GhidraBridge(bridge_url, timeout=300.0)
        if type_paths is None:
            type_paths = {}
            for row in _type_index(bridge):
                type_paths.setdefault(row["name"], []).append(row["path"])
        if signatures is None:
            signatures = {}
            log(f"live signatures of {len(wanted)} functions")
            for address in wanted:
                text = bridge.request("get_function_by_address", address=f"0x{address:x}")
                lines = text.splitlines() if isinstance(text, str) else []
                found = next((m.group(1) for line in lines if (m := _SIGNATURE_LINE.match(line))), None)
                if found is not None:
                    signatures[address] = found
    ctx = context(root)
    names = {row["start"]: row["names"] for row in ctx.functions}
    rows = []
    library_typed = 0
    for address in wanted:
        info = owner[address]
        signature = signatures.get(address)
        live = parse_signature(signature)
        if live is None or live["default"]:
            continue
        row = plan_row(info, address)
        prototype = (row or {}).get("prototype") or None
        dead = {
            str(entry.get("register"))
            for entry in ((prototype or {}).get("dead_entry_reads") or [])
            if info["plan_status"] == "accepted"
        }
        kinds = _register_conflicts(argument_reads(ctx, address), live, dead)
        kinds += _mangled_conflicts(names.get(address, []), live)
        if prototype and info["applied"] and info["plan_status"] == "accepted":
            want = _planned_signature(prototype)
            if want and (
                [t for t, _ in want["parameters"]] != [t for t, _ in live["parameters"]]
                or want["return_type"] != live["return_type"]
                or want["varargs"] != live["varargs"]
            ):
                kinds.append(f"drift: the applied plan sets {want['return_type']} ({', '.join(t for t, _ in want['parameters']) or 'void'})")
        for reason in (row or {}).get("unresolved") or []:
            if isinstance(reason, str) and (match := _RECORDED.search(reason)):
                start = max(0, match.start() - 40)
                kinds.append(f"recorded ({info['plan_status']} plan): ...{reason[start : match.end() + 60]}...")
                break
        library = sorted(
            {
                f"{_base_type(t)} ({', '.join(paths)})"
                for t in [live["return_type"]] + [t for t, _ in live["parameters"]]
                if _base_type(t) not in _BUILTIN_NAMES | UNDEFINED_TYPES
                and (paths := (type_paths or {}).get(_base_type(t)))
                and not any(path.startswith("/project/") for path in paths)
                and not all(path.count("/") == 1 for path in paths)
            }
        )
        library_typed += bool(library)
        if not kinds:
            continue
        state = (
            "missing from its plan" if row is None
            else "partial" if (prototype or {}).get("partial")
            else "prototype" if prototype
            else "open" if row.get("draft") == "open"
            else "unresolved"
        )
        rows.append(
            {
                "address": f"0x{address:x}",
                "name": live["name"],
                "signature": signature,
                "group": info["group"],
                "group_number": info["group_number"],
                "plan_status": info["plan_status"],
                "apply_status": info["apply_status"],
                "applied": info["applied"],
                "row": state if info["plan_path"].is_file() else "no plan file",
                "contradictions": kinds,
                "library_types": library,
            }
        )
    kinds_count: dict[str, int] = {}
    for row in rows:
        for kind in {text.split(":", 1)[0].split(" (", 1)[0] for text in row["contradictions"]}:
            kinds_count[kind] = kinds_count.get(kind, 0) + 1
    return {
        "kind": "socom-recon-live-contradictions",
        "mutation_performed": False,
        "groups": groups,
        "scanned": len(wanted),
        "with_live_claims": sum(1 for a in wanted if (p := parse_signature(signatures.get(a))) and not p["default"]),
        "contradiction_count": len(rows),
        "applied_count": sum(1 for row in rows if row["applied"]),
        # The live signature is a prototype this project planned, not an unproven one.
        "planned_prototype_count": sum(1 for row in rows if row["row"] in ("prototype", "partial")),
        "kinds": dict(sorted(kinds_count.items())),
        "library_typed_count": library_typed,
        "functions": rows,
    }


def contradictions_text(result: dict[str, Any]) -> str:
    lines = [
        f"# recon contradictions --groups {result['groups']}: {result['contradiction_count']} of "
        f"{result['with_live_claims']} live signatures with claims ({result['scanned']} group functions scanned) "
        f"contradict the facts; {result['applied_count']} are in applied groups",
        "# by kind: " + (", ".join(f"{kind} {count}" for kind, count in result["kinds"].items()) or "none")
        + f"; {result['planned_prototype_count']} of the signatures are prototypes a plan set, the rest unproven",
        f"# {result['library_typed_count']} scanned signatures use a type defined only outside /project (Ghidra's archives)",
    ]
    for row in result["functions"]:
        lines.append("")
        lines.append(f"{row['address']} {row['name']} :: {row['signature']}")
        lines.append(
            f"  group {row['group_number']} {row['group']}: plan {row['plan_status']}, apply {row['apply_status']}"
            f" ({'applied' if row['applied'] else 'not applied'}); row {row['row']}"
        )
        lines.extend(f"  {text}" for text in row["contradictions"])
        if row["library_types"]:
            lines.append("  library types: " + "; ".join(row["library_types"]))
    return "\n".join(lines)


def fingerprint_inputs(fingerprint: dict[str, Any]) -> tuple[dict[int, str], dict[str, list[str]]]:
    """Signature lines and type paths from a stored program fingerprint."""

    signatures: dict[int, str] = {}
    for row in fingerprint.get("functions", []):
        for line in row.get("details") or []:
            if match := _SIGNATURE_LINE.match(line):
                signatures[int(row["address"], 16)] = match.group(1)
    paths: dict[str, list[str]] = {}
    for text in fingerprint.get("types", []):
        path = text.rsplit("|", 1)[0]
        paths.setdefault(path.rsplit("/", 1)[-1], []).append(path)
    return signatures, paths

