"""Placeholder types for the mangled group: a plan only (nothing here writes to Ghidra).

    python tools/release/placeholders.py --plan [--signatures build/release/signatures/signatures-all.json]

The mangled symbols name about 690 classes and parameter types that exist in neither program
(no DWARF record at all). This step would give each the empty structure C gives an incomplete
type (``struct T;``) at the category the archive's own convention gives it, so that ``T *``
parses in ``set_function_prototype``; it is run only if the user agrees. The plan lists every
missing name with its scope, category, uses, the kind it would get and the functions of the
mangled group it unlocks; ``build/release/placeholders/placeholders-plan.json`` and ``.md``.

What is created, and what is not:

* A name used as a receiver or only through a pointer or reference becomes an empty structure
  (``StructureDataType`` of length 0, "not yet defined"): only the pointer's 4 bytes enter a
  signature, so no size is claimed. A receiver is a class (it has member functions).
* A name passed by value is not created: the mangled name does not tell an enum from a class, and
  the by-value size decides the storage (DWARF gives these enums 1, 2 or 4 bytes); it stays
  withheld until its record is recovered.
* A name that is no C identifier (template arguments, ``@unnamed@``, ``$``) cannot go through
  the C parser and is not created; a name that would be missing at two categories would make two
  types of one name (the archive disambiguates those with ``@<hash>`` from DWARF; there is none
  here), so it is not created either.

The writes it would send, per type (read from GhidraMCP 6.0.0's ``DataTypeService`` and Ghidra
12.1.4's ``CParser``): ``import_data_types`` with ``source`` ``struct <Name>;`` (``CParser.parse``
with the program's manager: a forward-declared composite found nowhere is created as an empty
``StructureDataType`` in the root category and added with ``REPLACE_HANDLER``; one found anywhere
by name is reused, never replaced), then ``move_data_type_to_category`` with ``type_name`` and
``category_path`` (finds the type by name in all categories, creates the category, sets the
category path). ``create_struct`` is no route: it refuses an empty field list, always creates at
the root, and refuses an existing name. Neither write touches another type, nor any type's link
to ``support/socom-types.gdt`` (a new type is local, with no source archive). A later real
layout grows the same type in place (``add_struct_field``/``resize_struct``), which keeps every
signature that names it; deleting and recreating it would turn those parameters ``undefined``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import elfimage  # noqa: E402
import ghidra_bridge as gb  # noqa: E402
import mangledsig as ms  # noqa: E402
import mips  # noqa: E402
import mwmangle as mw  # noqa: E402
import names  # noqa: E402
import signatures as sg  # noqa: E402
from names import canonical, sha256_text  # noqa: E402

OUT = Path("build/release/placeholders")
PLAN_KIND = "socom-release-placeholder-types-plan"
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


def build(signatures_plan: dict, types_table: dict, prototype_image, release_image) -> dict:
    types = ms.Types(types_table, sg.strip_conflict, sg.C_PRIMITIVES)
    facts = ms.Facts(prototype_image)
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
                if not exc.reason.startswith(("missing type", "receiver missing")):
                    continue
            key = (mw.type_category(node), mw.type_name(node))
            row = missing.setdefault(key, {"name": key[1], "category": key[0],
                                           "scope": "::".join(mw.readable_component(c) for c in node["name"][:-1]),
                                           "uses": Counter(), "functions": set()})
            row["uses"][use] += 1
            row["functions"].add(e["address"])
            needs[e["address"]].add(key)
    by_name = Counter(name for _, name in missing)
    for (category, name), row in missing.items():
        if row["uses"]["by value"]:
            row["kind"], row["create"] = None, "no: passed by value (enum or class, size unknown)"
        elif not C_IDENTIFIER.match(name):
            row["kind"], row["create"] = None, "no: not a C identifier (the C parser cannot declare it)"
        elif by_name[name] > 1:
            row["kind"], row["create"] = None, "no: the name would be missing at two categories"
        elif name in types_table:
            row["kind"], row["create"] = None, "no: a type of that name exists elsewhere"
        else:
            row["kind"] = "class" if row["uses"]["receiver"] else "struct (incomplete)"
            row["create"] = "yes: empty structure"
    creatable = {k for k, r in missing.items() if r["kind"]}
    # The functions each placeholder set unlocks: rerun the derivation with the creatable ones.
    table = {n: list(v) for n, v in types_table.items()}
    for category, name in sorted(creatable):
        table.setdefault(name, []).append((f"{category}/{name}", 0))
    augmented = ms.Types(table, sg.strip_conflict, sg.C_PRIMITIVES)
    words = mips.words_of(release_image.data)
    unlocked, still = [], Counter()
    for e in blocked:
        if not needs.get(e["address"]) or not needs[e["address"]] <= creatable:
            still["needs a type that is not created" if needs.get(e["address"]) else "blocked otherwise"] += 1
            continue
        address, end = int(e["address"], 16), int(e["end"], 16)
        reads = ms.entry_reads(words, (address - release_image.base) // 4, (end + 1 - address) // 4, release_image.base)
        try:
            ms.derive(int(e["prototype"]["address"], 16), facts, augmented, reads, None, {}, lambda t: None)
        except ms.Withheld as exc:
            still[f"then withheld: {exc.group}"] += 1
            continue
        unlocked.append(e)
    unlocked_set = {e["address"] for e in unlocked}
    rows = []
    for key in sorted(missing):
        r = missing[key]
        rows.append({"name": r["name"], "category": r["category"], "scope": r["scope"],
                     "uses": dict(sorted(r["uses"].items())), "kind": r["kind"], "create": r["create"],
                     "functions_needing": len(r["functions"]),
                     "functions_unlocked": len(r["functions"] & unlocked_set)})
    plan = {
        "kind": PLAN_KIND, "schema_version": 1, "program": gb.RELEASE_PROGRAM,
        "signatures_plan_sha256": signatures_plan["plan_sha256"], "types": rows,
        "summary": {
            "missing_names": len(rows), "receivers": sum(1 for r in rows if r["uses"].get("receiver")),
            "parameter_types_only": sum(1 for r in rows if not r["uses"].get("receiver")),
            "would_create": len(creatable), "not_created": dict(Counter(r["create"] for r in rows if not r["kind"])),
            "blocked_functions": len(blocked), "functions_unlocked": len(unlocked),
            "functions_not_unlocked": dict(sorted(still.items())),
            "unlocked_by_module": dict(sorted(Counter(e["module"] for e in unlocked).items())),
            "writes_per_type": ["import_data_types {source: 'struct <Name>;'}",
                                "move_data_type_to_category {type_name: <Name>, category_path: <category>}"],
        },
    }
    plan["plan_sha256"] = sha256_text(canonical(plan))
    return plan


def markdown(plan: dict) -> str:
    s = plan["summary"]
    lines = ["# Placeholder types for the mangled group (plan only)", "",
             f"Signatures plan `{plan['signatures_plan_sha256'][:16]}`; plan sha256 `{plan['plan_sha256']}`.", "",
             f"- names missing from both programs: {s['missing_names']} ({s['receivers']} used as receivers, "
             f"{s['parameter_types_only']} only as parameter types)",
             f"- would be created as empty structures: {s['would_create']}; not created: {s['not_created']}",
             f"- functions of the group blocked by a type: {s['blocked_functions']}; unlocked by the placeholders: "
             f"{s['functions_unlocked']}; not unlocked: {s['functions_not_unlocked']}",
             f"- writes per type: {'; '.join(s['writes_per_type'])}", "",
             "| Name | Category | Uses | Kind | Functions needing / unlocked |", "|---|---|---|---|---|"]
    for r in sorted(plan["types"], key=lambda r: (-r["functions_needing"], r["name"])):
        lines.append(f"| `{r['name']}` | `{r['category']}` | {r['uses']} | {r['kind'] or r['create']} | "
                     f"{r['functions_needing']} / {r['functions_unlocked']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[1])
    parser.add_argument("--plan", action="store_true", required=True)
    parser.add_argument("--signatures", type=Path, default=Path("build/release/signatures/signatures-all.json"))
    parser.add_argument("--url")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    bridge = gb.Bridge(args.url, read_only=True)
    check = names.preflight(bridge)
    if not check["ok"]:
        print("refused: preflight failed: " + "; ".join(check["errors"]), file=sys.stderr)
        return 2
    signatures_plan = json.loads((root / args.signatures).read_text(encoding="utf-8"))
    plan = build(signatures_plan, sg.type_table(bridge, gb.RELEASE_PROGRAM),
                 elfimage.load(root / sg.PROTOTYPE_ELF, "prototype"), elfimage.load(root / names.RELEASE_ELF, "release"))
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / "placeholders-plan.json").write_text(canonical(plan), encoding="utf-8", newline="\n")
    (out / "placeholders-plan.md").write_text(markdown(plan), encoding="utf-8", newline="\n")
    print(json.dumps(plan["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
