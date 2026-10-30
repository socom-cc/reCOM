"""Unresolved rows that a partial prototype could upgrade (read-only).

A partial row (decision of 2026-10-22, extended the same day) sets proven
parameters and leaves the return ``undefined``; it may replace Ghidra's
default signature (``undefined f(void)``, with or without a convention) when
every parameter has a proven type.  ``partial_candidates`` lists unresolved
rows of accepted plans whose live signature is such a default and whose
parameters the facts alone prove, so a recon repair (applied groups) or a
re-plan (groups not applied yet) can upgrade them:

* the stage 2 DWARF prototype's parameters, or the mangled signature's
  parameters with a receiver proven as ``recon draft`` proves it (a const
  method, or an argument register read beyond the parameters that the
  receiver accounts for); a ``...`` signature gives fixed parameters and the
  varargs flag;
* every type resolves to exactly one live type (no ``undefinedN``);
* every argument register some path reads before writing it is declared,
  after dropping reads ``recon_dead`` proves masked (registers after a
  varargs signature's fixed parameters carry the variadic arguments);
* no thunk, no VU0 instructions, no constructor or destructor (hidden
  arguments need a planner), and no class passed by value over one GPR slot
  (``recon_byvalue``: Ghidra would give it the wrong storage).

The return stays open: why is the row's own ``unresolved`` text.  Nothing is
written to Ghidra or the tracker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .batch_apply import _SIGNATURE_LINE, _declared_argument_registers, claims_nothing, parse_signature
from .mwdemangle import demangle
from .util import SocomError, load_json

APPLIED_STATUSES = frozenset({"accepted", "awaiting_acceptance"})


def proven_parameters(ctx: Any, row: dict[str, Any], types: Any) -> tuple[dict[str, Any] | None, str]:
    """({parameters, varargs, source}, why) for one evidence row, or (None, why not)."""

    from .recon_dead import GPR_NUMBERS, masked_read_problem
    from .recon_draft import _by_value_reasons, _class_name, _render, _stage2_parameters, _uses_vu0
    from .recon_facts import argument_reads

    address = int(row["address"], 16)
    if row.get("thunk_target"):
        return None, "thunk: it shows its target's signature"
    if _uses_vu0(ctx, address):
        return None, "VU0 instructions: register contracts need a planner"
    names = row.get("elf_names") or []
    mangled = next((name for name in names if demangle(name)), None)
    parsed = demangle(mangled) if mangled else None
    params = list((parsed or {}).get("params") or [])
    if params == [{"modifiers": [], "kind": "builtin", "name": "void"}]:
        params = []
    varargs = bool(params) and params[-1].get("kind") == "builtin" and params[-1].get("name") == "..."
    if varargs:
        params = params[:-1]
    stage2 = (row.get("stage2") or {}).get("prototype") if isinstance(row.get("stage2"), dict) else None
    reads = argument_reads(ctx, address)
    for register in list(reads):
        if register in GPR_NUMBERS:
            sites = [s for s in reads[register] if masked_read_problem(ctx, address, GPR_NUMBERS[register], s) is not None]
            if sites:
                reads[register] = sites
            else:
                del reads[register]
    gprs = {GPR_NUMBERS[name] for name in reads if name in GPR_NUMBERS}
    fprs = {int(name[1:]) for name in reads if name.startswith("f")}
    if stage2:
        parameters = _stage2_parameters(stage2, params)
        source = "stage 2 DWARF prototype"
        if not all(types.spells(p["type"]) for p in parameters):
            return None, "a stage 2 parameter type is not exactly one live type"
    elif parsed:
        if parsed.get("name") in ("__ct", "__dt"):
            return None, "constructor or destructor: hidden arguments need a planner"
        rendered = []
        for index, value in enumerate(params, 1):
            name, reason, _type_problem = _render(value, types)
            if name is None:
                return None, f"parameter {index}: {reason}"
            rendered.append(name)
        if byvalue := _by_value_reasons(ctx, params, rendered, types):
            # Recon validate refuses it: Ghidra would give it the wrong storage.
            return None, f"by-value aggregate over one GPR slot: {byvalue[0]}"
        parameters = [{"name": f"param_{index}", "type": name} for index, name in enumerate(rendered, 1)]
        source = f"mangled signature {mangled}"
        qualifier = parsed.get("qualifier") or []
        if qualifier:
            declared_g, declared_f = _declared_argument_registers({"parameters": parameters})
            with_this = _declared_argument_registers({"parameters": [{"type": "?"}] + parameters})
            beyond = (gprs - declared_g) | {f + 100 for f in fprs - declared_f}
            if not (parsed.get("const") or (beyond and gprs <= with_this[0] and fprs <= with_this[1])):
                return None, "receiver unproven: not a const method and no register read beyond the parameters"
            receiver, reason = types.resolve(_class_name(qualifier))
            if receiver is None:
                return None, f"receiver: {reason or 'the class exists only as a NAME@hash copy or in another case'}"
            parameters = [{"name": "this", "type": f"{receiver} *"}] + [
                {"name": f"param_{index}", "type": p["type"]} for index, p in enumerate(parameters, 1)
            ]
            source += " with a proven receiver"
    else:
        return None, "no mangled signature and no stage 2 prototype: a planner proves the parameters"
    if any(p["type"].replace("*", "").strip().startswith("undefined") for p in parameters):
        return None, "a parameter type is undefinedN"
    declared_g, declared_f = _declared_argument_registers({"parameters": parameters})
    if varargs:
        gprs = {reg for reg in gprs if reg in declared_g or reg < max(declared_g, default=3)}
        fprs = {reg for reg in fprs if reg in declared_f or reg < max(declared_f, default=11)}
    if not (gprs <= declared_g and fprs <= declared_f):
        return None, "an argument register read on some path is not declared"
    if varargs and not parameters:
        return None, "varargs with no fixed parameter"
    return {"parameters": parameters, "varargs": varargs, "source": source}, ""


def partial_candidates(
    root: Path,
    tracker: dict[str, Any],
    *,
    groups: str = "all",
    signatures: dict[int, str] | None = None,
    type_rows: list[dict[str, Any]] | None = None,
    bridge_url: str | None = None,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Unresolved rows of accepted plans with a default live signature and proven parameters."""

    from .recon import group_evidence, plan_digest, plan_path_for
    from .recon_draft import _TypeIndex
    from .recon_facts import context

    if groups not in ("all", "applied"):
        raise SocomError("--groups is applied or all")
    items = {row["id"]: row for row in tracker["work_items"]}
    repaired = {
        address
        for row in tracker["work_items"]
        if row.get("kind") == "recon-repair-plan" and row.get("status") == "accepted"
        for address in row["batch"]["functions"]
    }
    rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for item in tracker["work_items"]:
        if item.get("kind") != "recon-plan-group" or item.get("status") != "accepted":
            continue
        apply = items.get(f"{item['id']}-apply") or {}
        applied = apply.get("status") in APPLIED_STATUSES
        if groups == "applied" and not applied:
            continue
        path = plan_path_for(root, item["id"])
        if not path.is_file():
            continue
        info = {
            "group": item["id"],
            "group_number": item["batch"].get("group_number"),
            "apply_status": apply.get("status"),
            "applied": applied,
        }
        for row in load_json(path).get("functions", []):
            if not row.get("prototype") and row.get("address") not in repaired:
                rows.append((item, info, row))
    if signatures is None or type_rows is None:
        from .ghidra import GhidraBridge, _type_index

        bridge = GhidraBridge(bridge_url, timeout=300.0)
        if type_rows is None:
            type_rows = _type_index(bridge)
        if signatures is None:
            signatures = {}
            log(f"live signatures of {len(rows)} unresolved rows")
            for _item, _info, row in rows:
                text = bridge.request("get_function_by_address", address=row["address"])
                lines = text.splitlines() if isinstance(text, str) else []
                found = next((m.group(1) for line in lines if (m := _SIGNATURE_LINE.match(line))), None)
                if found is not None:
                    signatures[int(row["address"], 16)] = found
    types = _TypeIndex(type_rows)
    ctx = context(root)
    evidence_rows: dict[str, dict[str, dict[str, Any]]] = {}

    def evidence_for(item: dict[str, Any], address: str) -> dict[str, Any] | None:
        if item["id"] not in evidence_rows:
            stored = plan_path_for(root, item["id"])
            stored = stored.with_name(stored.stem + "-evidence.json")
            evidence = load_json(stored) if stored.is_file() else None
            if not isinstance(evidence, dict) or evidence.get("group_sha256") != plan_digest(item):
                log(f"evidence of {item['id']}")
                evidence = group_evidence(root, tracker, item["id"])
            evidence_rows[item["id"]] = {row["address"]: row for row in evidence["functions"]}
        return evidence_rows[item["id"]].get(address)

    found = []
    default_count = 0
    reasons: dict[str, int] = {}
    for item, info, row in rows:
        live = parse_signature(signatures.get(int(row["address"], 16)))
        if live is None or not claims_nothing(live):
            continue
        default_count += 1
        evidence = evidence_for(item, row["address"])
        if evidence is None:
            continue
        proven, why = proven_parameters(ctx, evidence, types)
        if proven is None:
            key = "a parameter type" if why.startswith("parameter ") else why.split(":", 1)[0]
            reasons[key] = reasons.get(key, 0) + 1
            continue
        found.append(
            {
                "address": row["address"],
                "name": live["name"],
                "signature": signatures[int(row["address"], 16)],
                **info,
                "route": "recon repair (progress add-recon-repair)" if info["applied"] and info["apply_status"] == "accepted"
                else "after the apply is accepted, a recon repair" if info["applied"]
                else "re-plan before the apply (progress work reopen)",
                "parameters": proven["parameters"],
                "varargs": proven["varargs"],
                "source": proven["source"],
                "unresolved": [str(text) for text in row.get("unresolved") or []],
            }
        )
    return {
        "kind": "socom-recon-partial-candidates",
        "mutation_performed": False,
        "groups": groups,
        "unresolved_rows": len(rows),
        "default_live_count": default_count,
        "candidate_count": len(found),
        "not_proven": dict(sorted(reasons.items())),
        "functions": sorted(found, key=lambda value: int(value["address"], 16)),
    }


def candidates_text(result: dict[str, Any]) -> str:
    lines = [
        f"# recon partial-candidates --groups {result['groups']}: {result['candidate_count']} of "
        f"{result['default_live_count']} unresolved rows with Ghidra's default live signature have parameters the "
        f"facts prove ({result['unresolved_rows']} unresolved rows in accepted plans)",
        "# not proven: " + (", ".join(f"{why} {count}" for why, count in result["not_proven"].items()) or "none"),
        "# a partial row still needs per-parameter evidence and the reviewer's check; the return stays undefined",
    ]
    for row in result["functions"]:
        params = ", ".join(f"{p['type']} {p['name']}" for p in row["parameters"]) + (", ..." if row["varargs"] else "")
        lines.append("")
        lines.append(f"{row['address']} {row['name']} :: {row['signature']}")
        lines.append(
            f"  group {row['group_number']} {row['group']}: apply {row['apply_status']}; route: {row['route']}"
        )
        lines.append(f"  parameters ({row['source']}): ({params or 'void'})")
        if row["unresolved"]:
            text = row["unresolved"][0]
            lines.append(f"  unresolved: {text[:200]}{'...' if len(text) > 200 else ''}")
    return "\n".join(lines)
