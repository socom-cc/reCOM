"""Mechanical review of one stage 3 live apply, shared by applier and verifier.

``explain_recon_diff`` classifies every row of a before/after fingerprint diff
against the program's writes: prototyped or renamed group functions,
restated prototypes that were already live (no diff row), Ghidra thunks that
show a prototyped target's signature, typed and relabelled globals, derived
``PTR_`` labels, and added pointer/array types.  Anything else is a problem.

``check_recon_apply`` runs the verifier's checklist read-only: plan and
program provenance, scope, live preflight, receipt reproduction, a fresh
fingerprint compared with the handoff's after-fingerprint, the diff
explanation, the apply calls against the post-claim dry run, and the strict
tracker audit.  It returns data-derived evidence lines; the accepter decides.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .batch_apply import _thunk_target, expected_signature
from .elf import Elf32File
from .recon import _functions, build_recon_program
from .util import SocomError, canonical_json, load_json, sha256_file


def _slug(item_id: str) -> str:
    return item_id.removesuffix("-apply").replace("socom:", "socom-").replace(":", "-")


def recon_apply_paths(root: Path, item_id: str, label: str, prev: str) -> dict[str, Path]:
    slug = _slug(item_id)
    apply_slug = f"{item_id.removesuffix('-apply')}-apply".replace(":", "-")
    return {
        "plan": root / f"build/recon-plans/{slug}.json",
        "program": root / f"build/apply/{slug}-apply.json",
        "claimed": root / f"build/preflight-recon/{apply_slug}-claimed.json",
        "report": root / f"build/apply/{apply_slug}-report.json",
        "scope": root / f"build/receipts/{apply_slug}-scope.json",
        "before": root / f"build/fingerprints/{label}-before.json",
        "after": root / f"build/fingerprints/{label}-after.json",
        "diff": root / f"build/fingerprints/{label}-diff.json",
        "prev_after": root / f"build/fingerprints/{prev}-after.json",
    }


def explain_recon_diff(
    root: Path, diff: dict[str, Any], before: dict[str, Any], steps: list[dict[str, Any]], result: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """(problems, summary) for a recon apply's fingerprint diff."""

    renamed = {int(s["body"]["function_address"], 16) for s in steps if s["endpoint"] == "rename_function_by_address"}
    protos = {int(s["body"]["function_address"], 16) for s in steps if s["endpoint"] == "set_function_prototype"}
    typed = {int(s["body"]["address"], 16): s["body"]["type_name"] for s in steps if s["endpoint"] == "apply_data_type"}
    relabel = {int(s["body"]["address"], 16): s["body"]["new_name"] for s in steps if s["endpoint"] == "rename_label"}
    problems: list[str] = []
    changed = {int(r["address"], 16) for r in diff["functions"]}
    before_rows = {int(r["address"], 16): r for r in before["functions"]}
    expected = {
        int(row["address"], 16): "Signature: " + expected_signature(row["prototype"], row["name"])
        for row in result["functions"]
        if row.get("prototype")
    }
    restated = {a for a in protos - changed - renamed if expected.get(a) in before_rows.get(a, {}).get("details", [])}
    elf = Elf32File(root / "support" / "socom.elf")
    sizes = {row["start"]: row["size"] for row in _functions(elf)}
    names = {int(row["address"], 16): row["name"] for row in result["functions"]}
    mirrored = set()
    for r in diff["functions"]:
        address = int(r["address"], 16)
        if address in renamed | protos or not (r["before"]["thunk"] and r["after"]["thunk"]):
            continue
        target = _thunk_target(elf, address, sizes.get(address))
        if target in protos and target in expected:
            want = expected[target].replace(f" {names[target]}(", f" {r['after']['name']}(", 1)
            if want in r["after"]["details"]:
                mirrored.add(address)
    accounted = changed - mirrored
    wanted = (renamed | protos) - restated
    if accounted != wanted:
        problems.append(
            f"changed functions differ from the prototyped/renamed set: extra {sorted(map(hex, accounted - wanted))}, "
            f"missing {sorted(map(hex, wanted - accounted))}"
        )
    for r in diff["functions"]:
        keep = lambda side: [x for x in r[side]["details"] if x.startswith(("Entry", "Body"))]  # noqa: E731
        if keep("before") != keep("after") or r["before"]["thunk"] != r["after"]["thunk"]:
            problems.append(f"{r['address']}: entry/body/thunk changed")
        address = int(r["address"], 16)
        if address in expected and expected[address] not in r["after"]["details"]:
            problems.append(f"{r['address']}: signature is not the planned one")
    old_to_new = {r["before"]["name"]: r["after"]["name"] for r in diff["functions"]}
    removed_at = {d["address"]: d for d in diff["data"]["removed"]}
    derived = set()
    for d in diff["data"]["added"]:
        old = removed_at.get(d["address"])
        suffix = "_" + d["address"]
        if (
            old
            and d["name"].startswith("PTR_")
            and old["name"].startswith("PTR_")
            and (d["type"], d["size"]) == (old["type"], old["size"])
            and old_to_new.get(old["name"][4 : -len(suffix)]) == d["name"][4 : -len(suffix)]
        ):
            derived.add(d["address"])
    for d in diff["data"]["added"]:
        address = int(d["address"], 16)
        if d["address"] in derived or (address in typed and d["type"] == typed[address]) or (
            address in relabel and d["name"] == relabel[address]
        ):
            continue
        problems.append(f"unexplained added data {d}")
    for d in diff["data"]["removed"]:
        address = int(d["address"], 16)
        if d["address"] in derived or address in typed or address in relabel or any(t < address < t + 64 for t in typed):
            continue
        problems.append(f"unexplained removed data {d}")
    if diff["references"]["added"] or diff["references"]["removed"] or not diff["blocks_equal"] or not diff["bookmarks_equal"]:
        problems.append(f"references/blocks/bookmarks changed: {diff['references']}")
    for t in diff["types"]["added"]:
        path = t.rsplit("|", 1)[0]
        if not (path.endswith("*") or path.endswith("]")):
            problems.append(f"new type is neither a pointer nor an array: {t}")
    if diff["types"]["removed"]:
        problems.append(f"types removed: {diff['types']['removed']}")
    summary = {
        "changed": sorted(map(hex, changed)),
        "prototyped": len(protos),
        "renamed": len(renamed),
        "restated": sorted(map(hex, restated)),
        "thunks": sorted(map(hex, mirrored)),
        "typed_globals": len(typed),
        "data_added": len(diff["data"]["added"]),
        "data_removed": len(diff["data"]["removed"]),
        "types_added": list(diff["types"]["added"]),
    }
    return problems, summary


def diff_note(summary: dict[str, Any]) -> str:
    renamed = f", {summary['renamed']} renamed" if summary["renamed"] else ""
    note = (
        f"{len(summary['changed'])} functions changed: {summary['prototyped'] - len(summary['restated'])} prototyped"
        f"{renamed} group functions, entry/body/thunk unchanged; data +{summary['data_added']}/-{summary['data_removed']}"
        f" explained ({summary['typed_globals']} typed globals); types added {len(summary['types_added'])}"
        " (pointer/array only); references, blocks and bookmarks unchanged"
    )
    if summary["restated"]:
        note += f"; {len(summary['restated'])} restated prototype(s) already live and unchanged ({', '.join(summary['restated'])})"
    if summary["thunks"]:
        note += f"; thunk(s) outside the scope now show their prototyped target's signature ({', '.join(summary['thunks'])})"
    return note


def check_recon_apply(
    root: Path,
    item_id: str,
    label: str,
    prev: str,
    *,
    fingerprint_output: Path,
    bridge_url: str | None = None,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """Run the apply verifier's checklist; read-only against Ghidra."""

    from .fingerprint import compare_fingerprints, program_fingerprint
    from .ghidra import live_preflight, load_receipt_scope, semantic_receipt
    from .tracker import audit_tracker, load_tracker, tracker_path
    from .util import atomic_write_json

    paths = recon_apply_paths(root, item_id, label, prev)
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        log(f"{'ok ' if ok else 'FAIL'} {name}: {detail}")

    for key, path in paths.items():
        if not path.is_file():
            raise SocomError(f"missing {key}: {path.relative_to(root).as_posix()}")
    tracker = load_tracker(tracker_path(root))
    apply_id = f"{item_id.removesuffix('-apply')}-apply"
    plan_id = item_id.removesuffix("-apply")
    items = {row["id"]: row for row in tracker["work_items"]}
    apply_item, plan_item = items.get(apply_id), items.get(plan_id)
    if apply_item is None or plan_item is None:
        raise SocomError(f"unknown item {item_id}")
    check("status", apply_item["status"] == "awaiting_acceptance" and plan_item["status"] == "accepted",
          f"apply {apply_item['status']}, plan {plan_item['status']}")
    handoff_receipt = next(
        (m.group(1) for e in apply_item.get("evidence", []) for m in [re.search(r"ghidra-receipt-sha256:\s*([0-9a-f]{64})", e)] if m),
        None,
    )
    plan_sha = sha256_file(paths["plan"])
    check("plan", any(plan_sha in e for e in plan_item.get("evidence", [])),
          f"plan sha256 {plan_sha} {'cited' if any(plan_sha in e for e in plan_item.get('evidence', [])) else 'NOT cited'} by the accepted plan item")
    program = load_json(paths["program"])
    regenerated = build_recon_program(root, tracker, paths["plan"])
    check("program", canonical_json(regenerated) == canonical_json(program),
          f"program sha256 {sha256_file(paths['program'])} regenerates {'identically' if canonical_json(regenerated) == canonical_json(program) else 'DIFFERENTLY'} from the plan")
    scope = load_json(paths["scope"])
    check("scope", scope == program["receipt_scope"],
          f"stored scope ({len(scope['functions'])} functions, {len(scope['globals'])} globals) "
          f"{'equals' if scope == program['receipt_scope'] else 'DIFFERS from'} the program's receipt_scope")
    preflight = live_preflight(root, bridge_url=bridge_url, strict_baseline=False)
    check("preflight", preflight["ok"], "live preflight ok" if preflight["ok"] else f"preflight errors: {preflight['errors']}")
    receipt = semantic_receipt(root, bridge_url=bridge_url, scope=load_receipt_scope(paths["scope"]))
    check("receipt", handoff_receipt is not None and receipt["receipt_sha256"] == handoff_receipt,
          f"receipt over the stored scope {receipt['receipt_sha256']} vs handoff {handoff_receipt}")
    log("fingerprint (several minutes)")
    fingerprint = program_fingerprint(root, bridge_url=bridge_url, log=log)
    atomic_write_json(fingerprint_output, fingerprint)
    after = load_json(paths["after"])
    now_vs_after = compare_fingerprints(after, fingerprint)
    check("fingerprint", now_vs_after["identical"],
          f"verifier fingerprint {fingerprint['fingerprint_sha256']} {'identical to' if now_vs_after['identical'] else 'DIFFERS from'} {label}-after")
    before = load_json(paths["before"])
    before_vs_prev = compare_fingerprints(load_json(paths["prev_after"]), before)
    check("chain", before_vs_prev["identical"],
          f"{label}-before {'identical to' if before_vs_prev['identical'] else 'DIFFERS from'} {prev}-after")
    recomputed = compare_fingerprints(before, after)
    stored_diff = load_json(paths["diff"])
    check("diff", canonical_json(recomputed) == canonical_json(stored_diff),
          f"recomputed {label} before/after diff {'equals' if canonical_json(recomputed) == canonical_json(stored_diff) else 'DIFFERS from'} the stored diff")
    claimed = load_json(paths["claimed"])
    report = load_json(paths["report"])
    result = report.get("result") or {}
    problems, summary = explain_recon_diff(root, recomputed, before, claimed.get("steps", []), result)
    check("explain", not problems, diff_note(summary) if not problems else "; ".join(problems))
    live = {int(r["address"], 16): r for r in fingerprint["functions"]}
    readback_problems = []
    for row in result.get("functions", []):
        address = int(row["address"], 16)
        details = live.get(address, {}).get("details", [])
        if row.get("prototype"):
            want = "Signature: " + expected_signature(row["prototype"], row["name"])
            if want not in details:
                readback_problems.append(f"{row['address']} live signature differs from the plan")
        else:
            if details != {int(r['address'], 16): r for r in before["functions"]}.get(address, {}).get("details"):
                readback_problems.append(f"{row['address']} (unresolved) changed")
    check("readback", not readback_problems,
          f"live signatures of {sum(1 for r in result.get('functions', []) if r.get('prototype'))} prototyped functions equal the plan; "
          f"{sum(1 for r in result.get('functions', []) if not r.get('prototype'))} unresolved unchanged"
          if not readback_problems else "; ".join(readback_problems))
    planned = [(s["endpoint"], canonical_json(s["body"])) for s in claimed.get("steps", [])]
    calls_ok = report.get("ok") and result.get("bridge_call_count") == len(planned) and claimed.get("ok")
    scope_addresses = {int(a, 16) for a in scope["functions"]} | {int(a, 16) for a in scope["globals"]}
    outside = [
        s for s in claimed.get("steps", [])
        if int(str(s["body"].get("address") or s["body"].get("function_address")), 16) not in scope_addresses
    ]
    check("calls", bool(calls_ok) and not outside,
          f"{result.get('bridge_call_count')} apply bridge calls; dry run planned {len(planned)} ({', '.join(sorted({e for e, _ in planned})) or 'none'}), "
          f"{len(outside)} outside the scope")
    errors = audit_tracker(tracker)
    check("audit", not errors, f"strict tracker audit ok at revision {tracker['revision']}" if not errors else "; ".join(errors[:3]))
    ok = all(row["ok"] for row in checks)
    return {
        "kind": "socom-recon-apply-check",
        "ok": ok,
        "mutation_performed": False,
        "item": apply_id,
        "revision": tracker["revision"],
        "receipt_sha256": receipt["receipt_sha256"],
        "checks": checks,
        "evidence": [f"check-recon-apply {row['name']}: {row['detail']}" for row in checks],
    }
