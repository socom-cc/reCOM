"""Placeholder types for the mangled group: empty structures for names that exist in no program.

    python tools/release/placeholders.py --plan [--signatures build/release/signatures/signatures-all.json]
    python tools/release/placeholders.py --apply build/release/placeholders/placeholders-plan.json --dry-run
    python tools/release/placeholders.py --apply build/release/placeholders/placeholders-plan.json --yes [--batch N]
    python tools/release/placeholders.py --confirm-saved build/release/placeholders/placeholders-plan.apply-001.json
    python tools/release/placeholders.py --discard-unsaved build/release/placeholders/placeholders-plan.apply-001.json

Run only with the user's agreement. The mangled symbols name classes and parameter types that
exist in neither program (no DWARF record at all); with an empty structure of that name at the
category the archive's convention gives it (``/project/<scopes>``), ``T *`` parses in
``set_function_prototype``. The plan lists every missing name with its scope, category, uses, the
kind it would get, and the functions of the mangled group it unlocks (the derivation rerun with
every rule, the hidden-argument checks included).

What is created, and what is not:

* A name used as a receiver or only through a pointer or reference becomes an empty structure
  (length 0, which Ghidra reports as 1 byte, "not yet defined"): only the pointer's 4 bytes enter
  a signature, so no size is claimed. A receiver is a class (it has member functions).
* A name passed by value is not created: the name does not tell an enum from a class, and the
  by-value size decides the storage (DWARF gives these enums 1, 2 or 4 bytes).
* A name that is no C identifier (template arguments, ``@unnamed@``, ``$``) cannot go through
  the C parser.
* A name present in any spelling is not missing: hashed (``LOD@8a190117c9``), ``.conflict`` and
  ``/project/unresolved`` types count. A name equal, case ignored, to any type name of the program
  or to another planned name is left out: ``move_data_type_to_category`` finds its type case
  ignored in every category and takes the first hit (``ServiceUtils.findDataTypeByNameInAllCategories``),
  so ``dir`` would move ``/project/CAiMap/DIR``.

The two writes per type (GhidraMCP 6.0.0 ``DataTypeService``, Ghidra 12.1.4 ``CParser``):

1. ``import_data_types`` with ``source`` ``struct <Name>;``: ``CParser.parse`` with the program's
   manager. A forward-declared composite it finds nowhere is created as an empty
   ``StructureDataType`` in the ROOT category with default packing ENABLED and added with
   ``REPLACE_HANDLER``; one it finds by name is reused.
2. ``move_data_type_to_category`` with ``type_name`` and ``category_path``: finds the type (case
   ignored, first hit), creates the category, sets the category path.

``create_struct`` is no route: it refuses an empty field list, always creates at the root, and
refuses an existing name. Neither write touches another type nor any type's link to
``support/socom-types.gdt`` (a new type is local, without a source archive).

A later real layout must keep the type: switch its packing off (the C parser packs it) and grow
it in place (``add_struct_field``/``resize_struct``), which keeps every signature that names it.
Deleting and recreating it turns those parameters ``undefined``; importing the archive's type at
the same path would add a ``.conflict`` twin, which the signature parser then also finds.

The apply sends one type at a time and reads the whole type table before and after each write:
after the import exactly one new type, the name at the root with 1 byte; after the move exactly
that type at the planned category with 1 byte, none left at the root, no other type added,
removed, renamed, moved or resized. The first difference stops the run. Packing cannot be read
back through the bridge (``get_struct_layout`` prints size and alignment only). Types that read
back go into ``docs/release/ghidra-types.tsv`` as unsaved rows of the report; ``--confirm-saved``
and ``--discard-unsaved`` as for the other steps. Never a save.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import dwarf1  # noqa: E402
import elfimage  # noqa: E402
import ghidra_bridge as gb  # noqa: E402
import mangledsig as ms  # noqa: E402
import mips  # noqa: E402
import mwmangle as mw  # noqa: E402
import names  # noqa: E402
import signatures as sg  # noqa: E402
from names import Refused, canonical, sha256_text  # noqa: E402

OUT = Path("build/release/placeholders")
RECORD = Path("docs/release/ghidra-types.tsv")
RECORD_COLUMNS = ("type_path", "applied", "value", "source", "date", "state")
PLAN_KIND = "socom-release-placeholder-types-plan"
PLAN_SCHEMA = 2
APPLIED = "placeholder-type"
VALUE = "empty structure (length 0, shown as 1 byte; packing enabled by the C parser)"
WRITES = frozenset({"import_data_types", "move_data_type_to_category"})
C_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def named_uses(parts: dict) -> list[tuple[dict, str]]:
    """(named node, use) for every class or enum a function's signature needs."""

    out = []
    if parts["scope_nodes"]:
        out.append(({"t": "named", "name": parts["scope_nodes"]}, "receiver"))
    for node in parts["params"]:
        use = "by value"
        while node["t"] in ("pointer", "reference", "array"):
            node, use = (node["of"] if node["t"] == "array" else node["to"]), "pointer"
        if node["t"] == "named":
            out.append((node, use))
    return out


def spellings(table: dict) -> tuple[set[str], set[str]]:
    """(every name present in some spelling: stripped of .conflict and @hash, in any category;
    every type name of the program in that base spelling, case ignored, for the collision check)."""

    base = {sg.strip_conflict(n).split("@", 1)[0] if not n.startswith("@") else n for n in table}
    return base, {n.lower() for n in base}


def build(signatures_plan: dict, types_table: dict, prototype_image, release_image,
          enums: dict | None = None, dwarf: dict | None = None) -> dict:
    types = ms.Types(types_table, sg.strip_conflict, sg.C_PRIMITIVES, enums)
    facts = ms.Facts(prototype_image)
    present, every = spellings(types_table)
    blocked = [e for e in signatures_plan["entries"] if e["group"] == "mangled" and e["action"] == "withheld"
               and e["reason_group"] in ("mangled type", "mangled receiver")]
    missing: dict[tuple, dict] = {}
    needs: dict[str, set] = defaultdict(set)
    for e in blocked:
        try:
            parts = facts.parts(int(e["prototype"]["address"], 16))
        except ms.Withheld:
            continue
        for node, use in named_uses(parts):
            if use == "receiver" and types.scope_kind(parts) == "namespace":
                continue
            try:
                types.resolve(node)
                continue
            except ms.Withheld as exc:
                if not exc.reason.startswith("missing type"):
                    continue
            name, category = mw.type_name(node), mw.type_category(node)
            if name in present:
                continue  # present in another spelling (hashed, .conflict, unresolved): not missing
            row = missing.setdefault((category, name), {
                "name": name, "category": category, "path": f"{category}/{name}",
                "scope": "::".join(mw.readable_component(c) for c in node["name"][:-1]),
                "uses": Counter(), "functions": set()})
            row["uses"][use] += 1
            row["functions"].add(e["address"])
            needs[e["address"]].add((category, name))
    planned_lower = Counter(name.lower() for _, name in missing)
    for (category, name), row in missing.items():
        if row["uses"]["by value"]:
            row["kind"], row["create"] = None, "no: passed by value (enum or class, size unknown)"
        elif not C_IDENTIFIER.match(name):
            row["kind"], row["create"] = None, "no: not a C identifier (the C parser cannot declare it)"
        elif name.lower() in every:
            row["kind"], row["create"] = None, "no: a type name of the program is the same, case ignored"
        elif planned_lower[name.lower()] > 1:
            row["kind"], row["create"] = None, "no: another planned name is the same, case ignored"
        else:
            row["kind"] = "class" if row["uses"]["receiver"] else "struct (incomplete)"
            row["create"] = "yes: empty structure"
    creatable = {k for k, r in missing.items() if r["kind"]}
    # The functions the created types unlock: the derivation rerun with them (every rule).
    table = {n: list(v) for n, v in types_table.items()}
    for category, name in sorted(creatable):
        table.setdefault(name, []).append((f"{category}/{name}", 1))
    augmented = ms.Types(table, sg.strip_conflict, sg.C_PRIMITIVES, enums)
    words = mips.words_of(release_image.data)
    dwarf = dwarf or {}
    unlocked, still = [], Counter()
    for e in blocked:
        if not needs.get(e["address"]) or not needs[e["address"]] <= creatable:
            still["needs a type that is not created" if needs.get(e["address"]) else "blocked otherwise"] += 1
            continue
        address, end = int(e["address"], 16), int(e["end"], 16)
        code = ms.entry_facts(words, (address - release_image.base) // 4, (end + 1 - address) // 4, release_image.base)
        proto = int(e["prototype"]["address"], 16)
        try:
            ms.derive(proto, facts, augmented, code, None, {}, lambda t: None, (dwarf.get(proto) or {}).get("return"))
        except ms.Withheld as exc:
            still[f"then withheld: {exc.group}"] += 1
            continue
        unlocked.append(e)
    unlocked_set = {e["address"] for e in unlocked}
    rows = []
    for key in sorted(missing):
        r = missing[key]
        rows.append({"name": r["name"], "category": r["category"], "path": r["path"], "scope": r["scope"],
                     "uses": dict(sorted(r["uses"].items())), "kind": r["kind"], "create": r["create"],
                     "functions_needing": len(r["functions"]),
                     "functions_unlocked": len(r["functions"] & unlocked_set)})
    plan = {
        "kind": PLAN_KIND, "schema_version": PLAN_SCHEMA, "program": gb.RELEASE_PROGRAM,
        "signatures_plan_sha256": signatures_plan["plan_sha256"],
        "type_table_sha256": sha256_text(canonical(types_table)), "types": rows,
        "summary": {
            "missing_names": len(rows), "receivers": sum(1 for r in rows if r["uses"].get("receiver")),
            "parameter_types_only": sum(1 for r in rows if not r["uses"].get("receiver")),
            "would_create": len(creatable), "not_created": dict(Counter(r["create"] for r in rows if not r["kind"])),
            "blocked_functions": len(blocked), "functions_unlocked": len(unlocked),
            "functions_not_unlocked": dict(sorted(still.items())),
            "unlocked_by_module": dict(sorted(Counter(e["module"] for e in unlocked).items())),
            "writes_per_type": ["import_data_types {source: 'struct <Name>;'}",
                                "move_data_type_to_category {type_name: <Name>, category_path: <category>}"],
            "later_layout": "switch packing off and grow the same type in place (add_struct_field, resize_struct); "
                            "never delete and recreate it; an archive import at the same path adds a .conflict twin",
        },
    }
    plan["plan_sha256"] = sha256_text(canonical(plan))
    return plan


def markdown(plan: dict) -> str:
    s = plan["summary"]
    lines = ["# Placeholder types for the mangled group", "",
             f"Signatures plan `{plan['signatures_plan_sha256'][:16]}`; plan sha256 `{plan['plan_sha256']}`.", "",
             f"- names missing from both programs: {s['missing_names']} ({s['receivers']} used as receivers, "
             f"{s['parameter_types_only']} only as parameter types)",
             f"- would be created as empty structures: {s['would_create']}; not created: {s['not_created']}",
             f"- functions of the group blocked by a type: {s['blocked_functions']}; unlocked by the placeholders: "
             f"{s['functions_unlocked']}; not unlocked: {s['functions_not_unlocked']}",
             f"- writes per type: {'; '.join(s['writes_per_type'])}",
             f"- a later real layout: {s['later_layout']}", "",
             "| Name | Category | Uses | Kind | Functions needing / unlocked |", "|---|---|---|---|---|"]
    for r in sorted(plan["types"], key=lambda r: (-r["functions_needing"], r["name"])):
        lines.append(f"| `{r['name']}` | `{r['category']}` | {r['uses']} | {r['kind'] or r['create']} | "
                     f"{r['functions_needing']} / {r['functions_unlocked']} |")
    return "\n".join(lines) + "\n"


# --- the record ------------------------------------------------------------------------------

def read_record(root: Path) -> dict[tuple, dict]:
    path = root / RECORD
    rows: dict[tuple, dict] = {}
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
        if lines and lines[0].split("\t") != list(RECORD_COLUMNS):
            raise Refused(f"{RECORD.as_posix()} has other columns than {RECORD_COLUMNS}")
        for line in lines[1:]:
            row = dict(zip(RECORD_COLUMNS, line.split("\t")))
            rows[(row["type_path"], row["applied"])] = row
    return rows


def write_record(root: Path, rows: dict[tuple, dict]) -> None:
    text = "\t".join(RECORD_COLUMNS) + "\n" + "".join(
        "\t".join(rows[k][c] for c in RECORD_COLUMNS) + "\n" for k in sorted(rows))
    (root / RECORD).write_text(text, encoding="utf-8", newline="\n")


# --- the apply -------------------------------------------------------------------------------

AFTER_NOTHING = "nothing was sent for this type: save, --confirm-saved this report, then replan"
AFTER_A_WRITE = ("the program may hold another type change: read the report's table difference; save and "
                 "--confirm-saved, or close without saving and --discard-unsaved; then replan")


def load_plan(path: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("kind") != PLAN_KIND or plan.get("schema_version") != PLAN_SCHEMA:
        raise Refused(f"{path.name} is not a schema {PLAN_SCHEMA} placeholder plan")
    if plan.get("program") != gb.RELEASE_PROGRAM:
        raise Refused(f"the plan targets {plan.get('program')!r}")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if sha256_text(canonical(body)) != plan.get("plan_sha256"):
        raise Refused(f"{path.name} does not match its plan_sha256: regenerate it instead of editing it")
    return plan


def table_rows(table: dict) -> set[tuple]:
    return {(name, path, size) for name, rows in table.items() for path, size in rows}


def apply(root: Path, plan_path: Path, bridge, *, dry_run: bool, batch: int | None = None,
          today: str | None = None) -> dict:
    plan = load_plan(plan_path)
    if not dry_run:
        pending = [r for r in read_record(root).values() if r["state"].startswith("unsaved")]
        if pending:
            raise Refused(f"{RECORD.as_posix()} holds {len(pending)} unsaved rows: --confirm-saved or "
                          "--discard-unsaved first")
    check = names.preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    recorded = read_record(root)
    out = (root / OUT / f"{plan_path.stem}.dry-run.json") if dry_run else next_report(root, plan_path.stem)
    written, would, attempted, unchanged, stopped, kind, difference = [], [], [], Counter(), None, None, []
    table = sg.type_table(bridge, gb.RELEASE_PROGRAM)
    first_table = table
    if sha256_text(canonical(table)) != plan["type_table_sha256"]:
        # since the plan, only the placeholder types saved by earlier runs may have been added
        saved_here = {k[0] for k, r in recorded.items() if r["state"].startswith("saved ")}
        others = [x for x in table_rows(table) if x[1] not in saved_here]
        if sha256_text(canonical(_regroup(others))) != plan["type_table_sha256"]:
            raise Refused("the release type table changed since the plan (beyond the saved placeholder types): replan")
    try:
        for row in plan["types"]:
            if not row["kind"]:
                continue
            if batch and len(written) >= batch:
                break
            present = [x for x in table_rows(table) if x[0].lower() == row["name"].lower()]
            if present == [(row["name"], row["path"], 1)] and recorded.get((row["path"], APPLIED), {}).get(
                    "state", "").startswith("saved "):
                unchanged["placeholder (saved)"] += 1
                continue
            if present:
                raise sg.StopBefore(f"{row['name']}: a type of that name, case ignored, is in the program now "
                                    f"({present[0][1]}): {AFTER_NOTHING}")
            if dry_run:
                would.append({"type_path": row["path"], "applied": APPLIED, "value": VALUE})
                continue
            item = {"type_path": row["path"], "applied": APPLIED, "value": VALUE,
                    "source": f"mangled symbols of {row['functions_needing']} functions"}
            attempted.append(item)
            before = table_rows(table)
            answer = bridge.write("import_data_types", gb.RELEASE_PROGRAM, source=f"struct {row['name']};")
            _check_answer("import_data_types", row, answer)
            middle = table_rows(sg.type_table(bridge, gb.RELEASE_PROGRAM))
            want = before | {(row["name"], "/" + row["name"], 1)}
            if middle != want:
                difference = _diff(want, middle)
                raise sg.StopAfter(f"import_data_types {row['name']} changed the table otherwise than planned: "
                                   f"{AFTER_A_WRITE}")
            answer = bridge.write("move_data_type_to_category", gb.RELEASE_PROGRAM, type_name=row["name"],
                                  category_path=row["category"])
            _check_answer("move_data_type_to_category", row, answer)
            table = sg.type_table(bridge, gb.RELEASE_PROGRAM)
            want = before | {(row["name"], row["path"], 1)}
            if table_rows(table) != want:
                difference = _diff(want, table_rows(table))
                raise sg.StopAfter(f"move_data_type_to_category {row['name']} left the table otherwise than planned: "
                                   f"{AFTER_A_WRITE}")
            written.append(item)
    except (names.Stop, gb.BridgeError) as exc:
        stopped, kind = str(exc), type(exc).__name__
    finally:
        if not dry_run and written:
            rows = read_record(root)
            for item in written:
                rows[(item["type_path"], APPLIED)] = dict(item, date=today or _dt.date.today().isoformat(),
                                                          state=f"unsaved {out.name}")
            write_record(root, rows)
    result = {"plan": plan_path.name, "plan_sha256": plan["plan_sha256"], "dry_run": dry_run, "stopped": stopped,
              "stop_kind": kind, "written": written, "would_write": would, "attempted": [] if dry_run else attempted,
              "unchanged": dict(unchanged), "table_difference": difference, "sent": [] if dry_run else bridge.sent,
              "types_before": len(table_rows(first_table)), "saved": False}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical(result), encoding="utf-8", newline="\n")
    result["report"] = out.name
    return result


def _regroup(rows) -> dict:
    out: dict = defaultdict(list)
    for name, path, size in rows:
        out[name].append((path, size))
    return {k: sorted(v) for k, v in sorted(out.items())}


def _check_answer(endpoint: str, row: dict, answer) -> None:
    text = json.dumps(answer) if not isinstance(answer, str) else answer
    if (isinstance(answer, dict) and "error" in answer) or re.search(r"\b(?:error|failed)\b", text, re.I):
        raise sg.StopAfter(f"{endpoint} {row['name']} answered {text[:200]!r}: {AFTER_A_WRITE}")


def _diff(want: set, got: set) -> list[dict]:
    return ([{"missing": list(x)} for x in sorted(want - got)] + [{"unexpected": list(x)} for x in sorted(got - want)])


def next_report(root: Path, stem: str) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    used = [int(m.group(1)) for p in out.glob(f"{stem}.apply-*.json") if (m := re.search(r"\.apply-(\d+)\.json$", p.name))]
    return out / f"{stem}.apply-{max(used, default=0) + 1:03d}.json"


def present_as_planned(table: dict, item: dict) -> bool:
    name = item["type_path"].rsplit("/", 1)[1]
    return [x for x in table_rows(table) if x[0].lower() == name.lower()] == [(name, item["type_path"], 1)]


def confirm_saved(root: Path, report_path: Path, bridge, today: str | None = None) -> dict:
    result = json.loads(report_path.read_text(encoding="utf-8"))
    table = sg.type_table(bridge, gb.RELEASE_PROGRAM)
    rows = read_record(root)
    mine = [k for k, r in rows.items() if r["state"] == f"unsaved {report_path.name}"]
    failed = [w["type_path"] for w in result["written"] if not present_as_planned(table, w)]
    if failed:
        raise Refused(f"{len(failed)} types do not read back ({', '.join(failed[:10])}); nothing marked saved")
    day = today or _dt.date.today().isoformat()
    for key in mine:
        rows[key]["state"] = f"saved {day}"
    write_record(root, rows)
    return {"confirmed": len(mine), "report": report_path.name}


def discard_unsaved(root: Path, report_path: Path, bridge) -> dict:
    result = json.loads(report_path.read_text(encoding="utf-8"))
    table = sg.type_table(bridge, gb.RELEASE_PROGRAM)
    names_now = {x[0].lower() for x in table_rows(table)}
    present = [i["type_path"] for i in result["attempted"] if i["type_path"].rsplit("/", 1)[1].lower() in names_now]
    if present:
        raise Refused(f"{len(present)} types of {report_path.name} are still in the program ({', '.join(present[:10])}): "
                      "save and --confirm-saved instead")
    rows = read_record(root)
    kept = {k: r for k, r in rows.items() if r["state"] != f"unsaved {report_path.name}"}
    write_record(root, kept)
    return {"discarded": len(rows) - len(kept), "report": report_path.name}


# --- command line ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", type=Path, metavar="PLAN")
    mode.add_argument("--confirm-saved", type=Path, metavar="REPORT")
    mode.add_argument("--discard-unsaved", type=Path, metavar="REPORT")
    parser.add_argument("--signatures", type=Path, default=Path("build/release/signatures/signatures-all.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--batch", type=int, metavar="N")
    parser.add_argument("--url")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.plan:
            bridge = gb.Bridge(args.url, read_only=True)
            check = names.preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            signatures_plan = json.loads((root / args.signatures).read_text(encoding="utf-8"))
            table = sg.type_table(bridge, gb.RELEASE_PROGRAM)
            prototype = elfimage.load(root / sg.PROTOTYPE_ELF, "prototype")
            facts = ms.Facts(prototype)
            plain = ms.Types(table, sg.strip_conflict, sg.C_PRIMITIVES)
            wanted = {n for e in signatures_plan["entries"] if e["group"] == "mangled" and e.get("prototype")
                      for n in sg.by_value_names(facts, plain, int(e["prototype"]["address"], 16))}
            plan = build(signatures_plan, table, prototype, elfimage.load(root / names.RELEASE_ELF, "release"),
                         sg.proven_enums(bridge, wanted, table), dwarf1.subroutines(root / sg.PROTOTYPE_ELF))
            out = root / OUT
            out.mkdir(parents=True, exist_ok=True)
            (out / "placeholders-plan.json").write_text(canonical(plan), encoding="utf-8", newline="\n")
            (out / "placeholders-plan.md").write_text(markdown(plan), encoding="utf-8", newline="\n")
            print(json.dumps(plan["summary"], indent=1))
            print(f"plan sha256 {plan['plan_sha256']}")
            return 0
        if args.confirm_saved or args.discard_unsaved:
            bridge = gb.Bridge(args.url, read_only=True)
            done = (confirm_saved(root, args.confirm_saved.resolve(), bridge) if args.confirm_saved
                    else discard_unsaved(root, args.discard_unsaved.resolve(), bridge))
            print(json.dumps(done, indent=1))
            return 0
        if not args.dry_run and not args.yes:
            print("refused: --apply writes to the release program; pass --yes (or --dry-run)", file=sys.stderr)
            return 2
        bridge = gb.Bridge(args.url, read_only=args.dry_run, writes=WRITES)
        result = apply(root, args.apply.resolve(), bridge, dry_run=args.dry_run, batch=args.batch)
        print(json.dumps({k: result[k] for k in ("report", "dry_run", "stopped", "stop_kind", "unchanged")}, indent=1))
        print(f"written {len(result['written'])}; would write {len(result['would_write'])}; sent {len(result['sent'])}")
        return 1 if result["stopped"] else 0
    except (Refused, gb.BridgeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
