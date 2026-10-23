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


def _relocated_words(elf: Elf32File) -> dict[int, int]:
    """R_MIPS_32 relocation sites and the address each relocated word holds."""

    segment = next(elf.load_segments())
    words = {}
    for relocation in elf.relocations(".relmain"):
        if relocation.type_name == "R_MIPS_32":
            offset = segment.offset + relocation.offset - segment.virtual_address
            words[relocation.offset] = int.from_bytes(elf.data[offset : offset + 4], "little")
    return words


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
    # The reverse: Ghidra split one ELF function into a thunk (its first
    # instruction `b`/`j` into its own body) and a target function holding the
    # rest.  A prototype set on the planned thunk is shared by that target, which
    # lies inside the planned function's ELF bytes (std::find<UIVarMixin**> at
    # 0x39e3f0 -> FUN_0039e3fc, group 76).
    from .recon import _code_word

    word = _code_word(elf)
    split = set()
    for r in diff["functions"]:
        address = int(r["address"], 16)
        if address in renamed | protos or r["before"]["thunk"] or r["after"]["thunk"]:
            continue
        for planned in protos:
            if planned not in expected or not before_rows.get(planned, {}).get("thunk"):
                continue
            if not planned < address < planned + (sizes.get(planned) or 0):
                continue
            insn = word(planned)
            branch = (
                planned + 4 + (((insn & 0xFFFF) ^ 0x8000) - 0x8000) * 4 if insn >> 16 == 0x1000
                else ((planned + 4) & 0xF0000000) | ((insn & 0x03FFFFFF) << 2) if insn >> 26 == 0x02
                else None
            )
            want = expected[planned].replace(f" {names[planned]}(", f" {r['after']['name']}(", 1)
            if branch == address and want in r["after"]["details"]:
                split.add(address)
    accounted = changed - mirrored - split
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
    # Typing a global as pointer data makes Ghidra add a DATA reference from each
    # pointer word; such a reference is explained when it starts inside a global
    # this plan typed and an R_MIPS_32 relocation at that word holds its target.
    sizes_by_address = {int(g["address"], 16): (g.get("size") or 4) for g in result.get("globals", [])}
    relocated = _relocated_words(elf)
    derived_refs = []
    other_refs = []
    for ref in diff["references"]["added"]:
        source, target = int(str(ref[0]), 16), int(str(ref[1]), 16)
        inside = any(a <= source < a + sizes_by_address.get(a, 4) for a in typed)
        if inside and len(ref) > 2 and ref[2] == "DATA" and relocated.get(source) == target:
            derived_refs.append(ref)
        else:
            other_refs.append(ref)
    if other_refs or diff["references"]["removed"] or not diff["blocks_equal"] or not diff["bookmarks_equal"]:
        problems.append(
            f"references/blocks/bookmarks changed: added {other_refs[:8]}, removed {diff['references']['removed'][:8]}"
        )
    # Ghidra copies a built-in type (schar, ushort, ...) into the program's root
    # category the first time a prototype uses it; a partial prototype may use
    # the built-in unknowns (undefined4, ...).
    from .batch_apply import BUILTINS, UNDEFINED_TYPES

    used_spellings = set()
    partial_used = set()
    for row in result.get("functions", []):
        prototype = row.get("prototype") or {}
        for text in [prototype.get("return_type") or ""] + [p.get("type") or "" for p in prototype.get("parameters") or []]:
            used_spellings.add(text.replace("*", "").strip())
            if prototype.get("partial"):
                partial_used.add(text.replace("*", "").strip())
    builtins_added = []
    for t in diff["types"]["added"]:
        path = t.rsplit("|", 1)[0]
        name = path.lstrip("/")
        if path.endswith("*") or path.endswith("]"):
            continue
        if path.count("/") == 1 and name in UNDEFINED_TYPES and name in partial_used:
            builtins_added.append(name)
            continue
        if path.count("/") == 1 and name in set(BUILTINS.values()) and name in used_spellings:
            builtins_added.append(name)
            continue
        problems.append(f"new type is neither a pointer nor an array: {t}")
    if diff["types"]["removed"]:
        problems.append(f"types removed: {diff['types']['removed']}")
    summary = {
        "changed": sorted(map(hex, changed)),
        "prototyped": len(protos),
        "renamed": len(renamed),
        "restated": sorted(map(hex, restated)),
        "thunks": sorted(map(hex, mirrored)),
        "builtins_added": sorted(builtins_added),
        "split_targets": sorted(map(hex, split)),
        "typed_globals": len(typed),
        "data_added": len(diff["data"]["added"]),
        "data_removed": len(diff["data"]["removed"]),
        "types_added": list(diff["types"]["added"]),
        "derived_references": len(derived_refs),
    }
    return problems, summary


def diff_note(summary: dict[str, Any]) -> str:
    renamed = f", {summary['renamed']} renamed" if summary["renamed"] else ""
    note = (
        f"{len(summary['changed'])} functions changed: {summary['prototyped'] - len(summary['restated'])} prototyped"
        f"{renamed} group functions, entry/body/thunk unchanged; data +{summary['data_added']}/-{summary['data_removed']}"
        f" explained ({summary['typed_globals']} typed globals); types added {len(summary['types_added'])}"
        " (pointer/array only); "
        + (
            f"{summary['derived_references']} DATA references added from pointer words of typed globals, each matching its R_MIPS_32 relocation; other references, blocks and bookmarks unchanged"
            if summary.get("derived_references")
            else "references, blocks and bookmarks unchanged"
        )
    )
    if summary["restated"]:
        note += f"; {len(summary['restated'])} restated prototype(s) already live and unchanged ({', '.join(summary['restated'])})"
    if summary.get("builtins_added"):
        note += "; Ghidra built-in type(s) first used by a planned prototype (" + ", ".join(summary["builtins_added"]) + ")"
    if summary.get("split_targets"):
        note += (
            "; Ghidra-split thunk target(s) inside a prototyped thunk's ELF function share its signature ("
            + ", ".join(summary["split_targets"]) + ")"
        )
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
    from .constants import tracker_path
    from .tracker import audit_tracker, load_tracker
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
    partial = sum(1 for r in result.get("functions", []) if (r.get("prototype") or {}).get("partial"))
    check("readback", not readback_problems,
          f"live signatures of {sum(1 for r in result.get('functions', []) if r.get('prototype'))} prototyped functions equal the plan; "
          + (f"{partial} of them partial (return left undefined, no-return flag as it was); " if partial else "")
          + f"{sum(1 for r in result.get('functions', []) if not r.get('prototype'))} unresolved unchanged"
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


# -- the readable-names repair -----------------------------------------------


def explain_names_diff(
    root: Path, diff: dict[str, Any], program: dict[str, Any], result: dict[str, Any]
) -> tuple[list[str], dict[str, Any]]:
    """(problems, summary) for the readable-names repair's fingerprint diff.

    Every changed function must be a planned rename (or a thunk whose renamed
    target it mirrors) whose only changes are its name in the Function and
    Signature lines; nothing else in the program may change.
    """

    unchanged = {int(row["address"], 16) for row in result.get("unchanged", []) if row.get("action") == "rename"}
    planned = {int(row["address"], 16): row for row in program["functions"]}
    renamed = {a: row for a, row in planned.items() if a not in unchanged}
    elf = Elf32File(root / "support" / "socom.elf")
    sizes = {row["start"]: row["size"] for row in _functions(elf)}
    problems: list[str] = []
    mirrored = []
    for r in diff["functions"]:
        address = int(r["address"], 16)
        before_name, after_name = r["before"]["name"], r["after"]["name"]
        if address in renamed:
            want = renamed[address]["readable_name"]
            if after_name != want or before_name != renamed[address]["current_name"]:
                problems.append(f"{r['address']}: {before_name!r} -> {after_name!r}, planned -> {want!r}")
        else:
            target = _thunk_target(elf, address, sizes.get(address))
            if not (r["before"]["thunk"] and r["after"]["thunk"] and target in renamed):
                problems.append(f"{r['address']}: changed but neither renamed nor a thunk of a renamed function")
                continue
            mirrored.append(f"0x{address:x}")
        expected = [line.replace(before_name, after_name, 1) if line.startswith(("Function:", "Signature:")) else line
                    for line in r["before"]["details"]]
        if expected != r["after"]["details"] or r["before"]["thunk"] != r["after"]["thunk"]:
            problems.append(f"{r['address']}: more than the name changed")
    changed = {int(r["address"], 16) for r in diff["functions"]}
    missing = sorted(set(renamed) - changed)
    if missing:
        problems.append(f"{len(missing)} planned renames show no change, e.g. {[hex(a) for a in missing[:5]]}")
    # Ghidra names an undefined pointer word after its target (PTR_<target>_<addr>);
    # renaming the target renames the label.  Only exact pairs are derived.
    old_to_new = {row["current_name"]: row["readable_name"] for row in renamed.values()}
    added = {(row["address"], row["size"], row["type"]): row["name"] for row in diff["data"]["added"]}
    derived = []
    leftover = []
    for row in diff["data"]["removed"]:
        key = (row["address"], row["size"], row["type"])
        name, suffix = row["name"], f"_{row['address']}"
        target = name[4:-len(suffix)] if name.startswith("PTR_") and name.endswith(suffix) else None
        if target in old_to_new and added.get(key) == f"PTR_{old_to_new[target]}{suffix}":
            derived.append(row["address"])
            del added[key]
        else:
            leftover.append(row)
    if leftover or added:
        problems.append(f"data changed beyond derived PTR_ labels: {len(leftover)} removed, {len(added)} added")
    if diff["types"]["added"] or diff["types"]["removed"]:
        problems.append("types changed")
    if diff["references"]["added"] or diff["references"]["removed"] or not diff["blocks_equal"] or not diff["bookmarks_equal"]:
        problems.append("references, blocks or bookmarks changed")
    summary = {
        "renamed": len(renamed),
        "already_readable": len(unchanged),
        "mirrored_thunks": mirrored,
        "changed_rows": len(diff["functions"]),
        "derived_pointer_labels": derived,
    }
    return problems, summary


def names_note(summary: dict[str, Any]) -> str:
    return (
        f"{summary['renamed']} functions renamed to their readable names ({summary['already_readable']} already readable, "
        f"unchanged); {len(summary['mirrored_thunks'])} thunks now show their renamed target's name; "
        f"{len(summary['derived_pointer_labels'])} derived PTR_ labels follow their renamed targets; only Function and "
        "Signature names changed otherwise; types, references, blocks and bookmarks unchanged"
    )


def check_names_repair(
    root: Path,
    label: str,
    prev: str,
    *,
    fingerprint_output: Path,
    bridge_url: str | None = None,
    log: Callable[[str], None] = lambda _message: None,
) -> dict[str, Any]:
    """The verifier's checklist for the readable-names repair; read-only against Ghidra."""

    from .constants import tracker_path
    from .fingerprint import compare_fingerprints, program_fingerprint
    from .ghidra import live_preflight, load_receipt_scope, semantic_receipt
    from .readable_names import READABLE_NAMES_REPAIR_ID, readable_names_program
    from .tracker import audit_tracker, load_tracker
    from .util import atomic_write_json

    slug = READABLE_NAMES_REPAIR_ID.replace(":", "-")
    paths = {
        "report": root / f"build/apply/{slug}-report.json",
        "dryrun": root / f"build/apply/{slug}-dryrun.json",
        "scope": root / f"build/receipts/{slug}-scope.json",
        "before": root / f"build/fingerprints/{label}-before.json",
        "after": root / f"build/fingerprints/{label}-after.json",
        "diff": root / f"build/fingerprints/{label}-diff.json",
        "prev_after": root / f"build/fingerprints/{prev}-after.json",
    }
    for key, path in paths.items():
        if not path.is_file():
            raise SocomError(f"missing {key}: {path.relative_to(root).as_posix()}")
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        log(f"{'ok ' if ok else 'FAIL'} {name}: {detail}")

    tracker = load_tracker(tracker_path(root))
    item = next((row for row in tracker["work_items"] if row["id"] == READABLE_NAMES_REPAIR_ID), None)
    if item is None:
        raise SocomError(f"{READABLE_NAMES_REPAIR_ID} is not in the tracker")
    check("status", item["status"] == "awaiting_acceptance", f"item {item['status']}")
    handoff_receipt = next(
        (m.group(1) for e in item.get("evidence", []) for m in [re.search(r"ghidra-receipt-sha256:\s*([0-9a-f]{64})", e)] if m),
        None,
    )
    report, dryrun = load_json(paths["report"]), load_json(paths["dryrun"])
    program = readable_names_program(root)
    stored = load_json(root / report["program"])
    check("program", canonical_json(program) == canonical_json(stored) and report.get("program_sha256") == program["program_sha256"],
          f"program {program['program_sha256']} regenerates {'identically' if canonical_json(program) == canonical_json(stored) else 'DIFFERENTLY'} from the ELF")
    scope = load_json(paths["scope"])
    check("scope", scope == program["receipt_scope"], f"stored scope ({len(scope['functions'])} functions) {'equals' if scope == program['receipt_scope'] else 'DIFFERS from'} the program's")
    preflight = live_preflight(root, bridge_url=bridge_url, strict_baseline=False)
    check("preflight", preflight["ok"], "live preflight ok" if preflight["ok"] else f"errors: {preflight['errors']}")
    receipt = semantic_receipt(root, bridge_url=bridge_url, scope=load_receipt_scope(paths["scope"]))
    check("receipt", handoff_receipt is not None and receipt["receipt_sha256"] == handoff_receipt,
          f"receipt {receipt['receipt_sha256']} vs handoff {handoff_receipt}")
    log("fingerprint (several minutes)")
    fingerprint = program_fingerprint(root, bridge_url=bridge_url, log=log)
    atomic_write_json(fingerprint_output, fingerprint)
    now_vs_after = compare_fingerprints(load_json(paths["after"]), fingerprint)
    check("fingerprint", now_vs_after["identical"], f"verifier fingerprint {fingerprint['fingerprint_sha256']} {'identical to' if now_vs_after['identical'] else 'DIFFERS from'} {label}-after")
    before = load_json(paths["before"])
    chain = compare_fingerprints(load_json(paths["prev_after"]), before)
    check("chain", chain["identical"], f"{label}-before {'identical to' if chain['identical'] else 'DIFFERS from'} {prev}-after")
    recomputed = compare_fingerprints(before, load_json(paths["after"]))
    check("diff", canonical_json(recomputed) == canonical_json(load_json(paths["diff"])), "recomputed diff equals the stored diff")
    result = report.get("result") or {}
    problems, summary = explain_names_diff(root, recomputed, program, result)
    check("explain", not problems, names_note(summary) if not problems else "; ".join(problems[:6]))
    live = {int(r["address"], 16): r["name"] for r in fingerprint["functions"]}
    wrong = [row["address"] for row in program["functions"] if live.get(int(row["address"], 16)) != row["readable_name"]]
    check("readback", not wrong, f"all {len(program['functions'])} planned functions show their readable names" if not wrong else f"{len(wrong)} differ, e.g. {wrong[:5]}")
    planned_steps = (dryrun.get("result") or {}).get("bridge_call_count")
    targets = {int(row["address"], 16) for row in program["functions"]}
    outside = [
        s for s in (dryrun.get("result") or {}).get("steps", [])
        if int(str(s["body"].get("address") or s["body"].get("function_address")), 16) not in targets
    ]
    check("calls", report.get("ok") and result.get("bridge_call_count") == planned_steps and not outside,
          f"{result.get('bridge_call_count')} bridge calls; dry run planned {planned_steps}; {len(outside)} outside the program")
    errors = audit_tracker(tracker)
    check("audit", not errors, f"strict tracker audit ok at revision {tracker['revision']}" if not errors else "; ".join(errors[:3]))
    return {
        "kind": "socom-names-repair-check",
        "ok": all(row["ok"] for row in checks),
        "mutation_performed": False,
        "item": READABLE_NAMES_REPAIR_ID,
        "revision": tracker["revision"],
        "receipt_sha256": receipt["receipt_sha256"],
        "checks": checks,
        "evidence": [f"check-names-repair {row['name']}: {row['detail']}" for row in checks],
    }
