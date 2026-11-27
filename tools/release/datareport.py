"""Counts, checks and the generated report of the data pairing (``docs/release/DATA.md``)."""
from __future__ import annotations

from collections import Counter, defaultdict

import protofacts

CLASSES = ("exact", "deviating", "unsure", "new", "removed")
FLAG_ORDER = ("settled", "witness-conflict", "release-shared", "contradicted", "offset-outside", "offset-changed",
              "size-changed", "size-unconfirmed", "content-changed", "pointer-changed", "section-changed",
              "size-from-release", "unrelocated-word", "constant-as-address", "single-aligned",
              "identical-copy", "order-only", "refs-removed", "refs-unaligned", "unreached", "ref-by-new")


def _table(counter: dict, keys) -> list[str]:
    out = ["| group | " + " | ".join(CLASSES) + " | " + " | ".join(c + " bytes" for c in CLASSES) + " |",
           "|" + "---|" * (1 + 2 * len(CLASSES))]
    for key in keys:
        row = counter[key]
        out.append("| %s | %s | %s |" % (key, " | ".join(str(row[c]) for c in CLASSES),
                                         " | ".join(str(row[c + "_bytes"]) for c in CLASSES)))
    return out


def self_check(pairing_, vt_pairs, entry_pairs) -> dict:
    """Table pairs against the pairing made without the table evidence."""

    independent = pairing_.resolve(use_tables=False)
    out = {"vtable": Counter(), "named-table": Counter(), "differences": []}
    for kind, pairs in (("vtable", [(p.address, r.address, p.name) for p, r in vt_pairs]),
                        ("named-table", [(p.address, r.address, "%s table, stride %d" % (p.kind, p.stride))
                                         for p, r in entry_pairs])):
        for p_address, r_address, what in pairs:
            hit = pairing_.index.containing(p_address)
            if hit is None:
                out[kind]["no object"] += 1
                out["differences"].append((kind, p_address, r_address, what, "no prototype object holds it"))
                continue
            obj, d = hit
            result = independent[obj.address]
            final = pairing_.results[obj.address]
            if d and result.base is not None and not result.conflict and result.base == final.base:
                # a table inside its object (a secondary vtable): the object pairs the same way;
                # the table's own offset moved when the release offset differs
                out[kind]["agree"] += 1
                if r_address - final.base != d:
                    out[kind]["inner offset moved"] += 1
                    out["differences"].append((kind, p_address, r_address, what, "inside %s at +%#x; release +%#x" % (
                        obj.name, d, r_address - final.base)))
                continue
            if result.conflict:
                out[kind]["conflict"] += 1
                out["differences"].append((kind, p_address, r_address, what, "conflict without the tables: %s" % (
                    ", ".join("%#x" % b for b, _ in result.conflict))))
            elif result.base is None:
                out[kind]["tables only"] += 1
            elif result.base + d == r_address:
                out[kind]["agree"] += 1
            else:
                out[kind]["differ"] += 1
                out["differences"].append((kind, p_address, r_address, what, "other evidence gives %#x" % (
                    result.base + d)))
            if final.base is None or final.conflict or final.base + d != r_address:
                out[kind]["final differs"] += 1
                if not (result.base is not None and not result.conflict and result.base + d != r_address):
                    out["differences"].append((kind, p_address, r_address, what, "final map gives %s" % (
                        "nothing" if final.base is None else "%#x" % (final.base + d))))
    return out


def collect(pairing_, rows, new_rows, coverage, stats, witnesses, vt_pairs, entry_pairs, refs_by, anonymous) -> dict:
    by_class = defaultdict(Counter)
    by_section = defaultdict(Counter)
    by_module = defaultdict(Counter)
    flags = Counter()
    evidence_named = Counter()
    single = Counter()
    for result in pairing_.results.values():
        obj = result.obj
        size = obj.size
        for table, key in ((by_class, "all objects"), (by_section, obj.section),
                           (by_module, protofacts.module_of(obj.owner) or "(no owner)")):
            table[key][result.cls] += 1
            table[key][result.cls + "_bytes"] += size
        for f in result.flags:
            flags[f] += 1
        if result.base is not None and not result.conflict:
            if result.witnesses == 1:
                single[next(iter(result.evidence), "-")] += 1
            if not obj.anonymous:
                for kind in result.evidence:
                    evidence_named[kind] += 1
    for row in new_rows:
        for table, key in ((by_class, "all objects"), (by_section, row["section"]),
                           (by_module, protofacts.module_of(row["owner"]) or "(no owner)")):
            table[key]["new"] += 1
        for f in row["flags"]:
            flags[f] += 1
    named = [r for r in pairing_.results.values() if not r.obj.anonymous]
    named_paired = [r for r in named if r.base is not None and not r.conflict]
    first_kind = Counter()
    for r in named_paired:
        first_kind[next(iter(r.evidence))] += 1
    conflicts = []
    contradictions = []
    for result in sorted(pairing_.results.values(), key=lambda r: r.obj.address):
        if result.conflict:
            conflicts.append({"prototype": result.obj.address, "symbol": result.obj.name,
                              "size": result.obj.size, "tier": result.tier, "candidates": result.conflict,
                              "shared": "release-shared" in result.flags})
        if result.contradictions and not result.conflict:
            against = defaultdict(set)
            for b, kind, witness in result.contradictions:
                against[b].add("%s %s" % (kind, witness) if kind in ("content", "order") else witness)
            contradictions.append({"prototype": result.obj.address, "symbol": result.obj.name,
                                   "size": result.obj.size, "release": result.base,
                                   "decided_by": sorted(result.evidence), "tier": result.tier,
                                   "against": [(b, sorted(w)) for b, w in sorted(against.items())]})
    outside = [r for r in sorted(pairing_.results.values(), key=lambda r: r.obj.address) if "offset-outside" in r.flags]
    withheld = Counter()
    for result in pairing_.results.values():
        if result.cls in ("exact", "deviating"):
            for reason in result.withhold:
                withheld[reason] += 1
    rejected = Counter("repeated code, no key" if why == "repeated code, no key" else "a key leads elsewhere"
                       for _, _, _, why in pairing_.key_rejected)
    return {
        "withheld": withheld, "withheld_pairs": sum(1 for r in pairing_.results.values()
                                                    if r.withhold and r.cls in ("exact", "deviating")),
        "key_rejected": rejected, "settled_rows": len(pairing_.settled), "withhold_rows": len(pairing_.withheld),
        "by_class": by_class, "by_section": by_section, "by_module": by_module, "flags": flags,
        "coverage": {
            "named objects": len(named), "named paired": len(named_paired),
            "named paired by first evidence": dict(first_kind), "named supported by": dict(evidence_named),
            "single witness": dict(single), "single witness total": sum(single.values()),
            "anonymous objects": anonymous, **coverage,
            "release-only rows": len(new_rows),
        },
        "witness_stats": dict(sorted(stats.items())), "pairing_stats": dict(sorted(pairing_.stats.items())),
        "code_witnesses": len(witnesses), "mismatches": pairing_.mismatches,
        "conflicts": conflicts, "contradictions": contradictions, "outside": [(r.obj.address, r.obj.name, r.obj.size, r.base, r.field_moves)
                                            for r in outside],
        "self_check": self_check(pairing_, vt_pairs, entry_pairs),
        "tables": {"vtable pairs": len(vt_pairs), "named-table pairs": len(entry_pairs)},
    }


def markdown(data: dict) -> str:
    out = []
    add = out.append
    inputs = data["inputs"]
    add("# Release data pairing: prototype SCUS-972.05 against release SCUS-971.34")
    add("")
    add("Generated by `python tools/release/datapair.py`; do not edit by hand. The per-object table is")
    add("[data-map.tsv](data-map.tsv); a machine-readable copy with every witness is written to")
    add("`build/release/data-map.json`. The function pairs it starts from are")
    add("[function-map.tsv](function-map.tsv). The method is in [RULES.md](RULES.md), \"Stage 3: globals (pairing)\".")
    add("")
    add("## Inputs")
    add("")
    add("| role | SHA-256 | $gp |")
    add("|---|---|---|")
    add("| prototype | `%s` | %#x (`_gp`) |" % (inputs["prototype"], inputs["prototype_gp"]))
    add("| release | `%s` | %s (moved into $gp by the entry function) |" % (
        inputs["release"], "%#x" % inputs["release_gp"] if inputs["release_gp"] else "not found"))
    add("")
    add("%d function-map rows; %d prototype data objects (%d anonymous: addresses code reaches that no "
        "symbol holds)." % (inputs["function_map_rows"], inputs["objects"], data["coverage"]["anonymous objects"]))
    add("")
    add("## Classes")
    add("")
    add("- **exact**: same size (the next prototype object is paired at the same distance, or the next paired")
    add("  release object starts where the prototype size ends) and the same bytes once pointer words are")
    add("  masked (function pointers must map through the function map, data pointers through this map);")
    add("  `.bss` counts as zero bytes on both sides;")
    add("- **deviating**: paired, with a difference or a size the evidence only bounds (flags);")
    add("- **unsure**: witnesses that contradict each other, or a pair that rests on order alone;")
    add("- **new**: a release data address code references that no paired object covers (one row per address: a")
    add("  field of a new object is a row of its own);")
    add("- **removed**: a prototype object nothing paired (`refs-removed`: only removed functions use it;")
    add("  `refs-unaligned`: paired functions use it but not at an aligned place; `unreached`: no code uses it).")
    add("")
    add("Release sizes are `N` when confirmed, else `lower..upper`: the largest offset plus width the release")
    add("code accesses, and the distance to the next paired release object (`?` when none follows).")
    add("")
    add("## Totals")
    add("")
    out.extend(_table(data["by_class"], ["all objects"]))
    add("")
    add("Bytes are prototype sizes (new rows have none). Flags:")
    add("")
    add("| flag | objects |")
    add("|---|---|")
    for f in FLAG_ORDER:
        if data["flags"][f]:
            add("| `%s` | %d |" % (f, data["flags"][f]))
    add("")
    add("## By prototype section")
    add("")
    add("Sections are the input-section envelopes of the prototype's SECTION symbols, `between X and Y`")
    add("outside them, and `from <symbol>` after a linker symbol (as in")
    add("`docs/reconstruction/FUNCTION_ORDER.md`). The release section of a pair is the section of its")
    add("paired release neighbours; a pair whose neighbours lie elsewhere is `section-changed`. A release")
    add("address whose paired neighbours below and above lie in different sections reads `(below)..(above)`.")
    add("")
    sections = data["by_section"]
    out.extend(_table(sections, sorted(sections, key=lambda k: (-sum(sections[k][c] for c in CLASSES), k))))
    add("")
    add("## By module")
    add("")
    add("Owner: the prototype's `@socom-artifact defines main socom:data:` annotation, else the owner file most")
    add("of the prototype functions that reference it have (the function map's owner column).")
    add("")
    modules = data["by_module"]
    out.extend(_table(modules, sorted(modules, key=lambda k: (-sum(modules[k][c] for c in CLASSES), k))))
    add("")
    cov = data["coverage"]
    add("## Coverage")
    add("")
    add("| measure | value |")
    add("|---|---|")
    add("| named prototype objects | %d |" % cov["named objects"])
    add("| named objects paired (no conflict) | %d |" % cov["named paired"])
    for kind, n in sorted(cov["named paired by first evidence"].items(), key=lambda kv: -kv[1]):
        add("| ... strongest evidence `%s` | %d |" % (kind, n))
    for kind, n in sorted(cov["named supported by"].items(), key=lambda kv: -kv[1]):
        add("| named pairs `%s` supports | %d |" % (kind, n))
    add("| pairs resting on one witness | %d |" % cov["single witness total"])
    for kind, n in sorted(cov["single witness"].items(), key=lambda kv: -kv[1]):
        add("| ... of them `%s` | %d |" % (kind, n))
    add("| release data addresses code references | %d |" % cov["release referenced addresses"])
    add("| ... inside a paired object | %d |" % cov["covered by a paired object"])
    add("| release-only rows (`new`) | %d |" % cov["release-only rows"])
    add("")
    add("Code witnesses: %d aligned uses. Uses the alignment rejected:" % data["code_witnesses"])
    add("")
    for key, value in data["witness_stats"].items():
        add("- %s: %d" % (key, value))
    for key, value in data["pairing_stats"].items():
        add("- %s: %d" % (key, value))
    add("- aligned uses whose release address is code or outside the image: %d" % len(data["mismatches"]))
    add("")
    add("Key check of the `operand-aligned` uses (an aligned use votes only when no key near it, a callee")
    add("or decided object used once in the function or its own distinctive bytes, leads elsewhere; one in")
    add("repeated code needs a key that agrees): %d rejected because a key leads elsewhere, %d in repeated" % (
        data["key_rejected"]["a key leads elsewhere"], data["key_rejected"]["repeated code, no key"]))
    add("code without a key. Every rejected use is in `build/release/data-map.json` (`key_rejected`).")
    add("")
    add("## Settled rows and the apply step")
    add("")
    add("`docs/release/settled-data.tsv` (a checker's input, read on every run): %d rows decide a pair or" % data["settled_rows"])
    add("that there is none (evidence `settled`; evidence that still disagrees is listed as a contradiction),")
    add("%d objects carry a withhold reason from it. The map's `withhold` column says why the apply step must" % data["withhold_rows"])
    add("not carry a pair; %d committed pairs carry one:" % data["withheld_pairs"])
    add("")
    add("| reason | committed pairs |")
    add("|---|---|")
    for reason, count in sorted(data["withheld"].items(), key=lambda kv: (-kv[1], kv[0])):
        add("| %s | %d |" % (reason, count))
    add("")
    add("`single-aligned` marks every committed pair that rests on one `operand-aligned` witness and nothing")
    add("else; `size-from-release` a string whose release text differs (its size and type come from the")
    add("release bytes); `constant-as-address` a witness with no relocation behind it in the prototype (an")
    add("integer constant read as an address, or a linker symbol resolved without one); `unrelocated-word` an")
    add("unrelocated address word that maps through the pairs (masked like a pointer).")
    add("")
    add("## Self-check against the table pairs")
    add("")
    check = data["self_check"]
    add("The pairing is run again without the `vtable` and `named-table` evidence; each table pair of the")
    add("function comparison (%d vtables, %d named tables) is then compared with what the other evidence gives." % (
        data["tables"]["vtable pairs"], data["tables"]["named-table pairs"]))
    add("")
    add("| tables | agree | of them inside an object, offset moved | other evidence differs | conflict | only the tables reach it | final map differs |")
    add("|---|---|---|---|---|---|---|")
    for kind in ("vtable", "named-table"):
        c = check[kind]
        add("| %s | %d | %d | %d | %d | %d | %d |" % (kind, c["agree"], c["inner offset moved"], c["differ"],
                                                   c["conflict"], c["tables only"], c["final differs"]))
    add("")
    if check["differences"]:
        add("| tables | prototype | release (table pair) | what | difference |")
        add("|---|---|---|---|---|")
        for kind, p, r, what, why in check["differences"]:
            add("| %s | %#x | %#x | %s | %s |" % (kind, p, r, what.replace("|", "\\|"), why))
        add("")
    def witnesses(w):
        return " ".join(w[:6]) + (" +%d" % (len(w) - 6) if len(w) > 6 else "")

    add("## Witness conflicts (unsure)")
    add("")
    add("Every prototype object whose witnesses of the deciding tier, at the smallest offset, name different")
    add("release starts, or that shares one release start with another sized object (`release-shared`).")
    add("Witnesses: `fn:` a function pair (prototype address), `data:` the paired object whose pointer it is,")
    add("`vt:`/`tbl:` a table, `content`, `order`. Tiers: 0 unique content (8+ bytes or a C string) of a literal")
    add("(`@N`), 1 operand-exact and tables, 2 such content of other objects and pointers, 3 operand-aligned and")
    add("shorter content, 4 order.")
    add("")
    if data["conflicts"]:
        add("| prototype | symbol | size | tier | candidates |")
        add("|---|---|---|---|---|")
        for c in data["conflicts"]:
            cands = "; ".join("%#x: %s" % (b, witnesses(w)) for b, w in c["candidates"])
            add("| %#x | `%s` | %d | %d | %s%s |" % (c["prototype"], c["symbol"], c["size"], c["tier"], cands,
                                                   " (release-shared)" if c["shared"] else ""))
    else:
        add("None.")
    add("")
    add("## Contradicted pairs")
    add("")
    add("Pairs decided by a stronger tier where a weaker witness points outside the paired object (before its")
    add("start or past the next paired release object). The weaker witness does not vote; it is listed here.")
    add("")
    if data["contradictions"]:
        add("| prototype | symbol | size | release | decided by (tier) | contradicting release address: witnesses |")
        add("|---|---|---|---|---|---|")
        for c in data["contradictions"]:
            against = "; ".join("%#x: %s" % (b, witnesses(w)) for b, w in c["against"])
            add("| %#x | `%s` | %d | %s | %s (%d) | %s |" % (c["prototype"], c["symbol"], c["size"],
                                                           "removed" if c["release"] is None else "%#x" % c["release"],
                                                           ", ".join(c["decided_by"]), c["tier"], against))
    else:
        add("None.")
    add("")
    add("## Accesses outside the prototype size")
    add("")
    add("Pairs where release code accesses an offset outside the prototype object (a layout or size change:")
    add("for the module's note in stage 4). Offsets are prototype -> release.")
    add("")
    if data["outside"]:
        add("| prototype | symbol | size | release | field offsets (p -> r) |")
        add("|---|---|---|---|---|")
        for address, name, size, base, moves in data["outside"]:
            shown = sorted({(p, r) for p, r, _ in moves})
            text = " ".join("+%#x->+%#x" % (p, r) for p, r in shown[:8]) + (" ..." if len(shown) > 8 else "")
            add("| %#x | `%s` | %d | %#x | %s |" % (address, name, size, base, text))
    else:
        add("None.")
    add("")
    return "\n".join(out) + "\n"


def json_copy(pairing_, data: dict) -> dict:
    objects = []
    for result in sorted(pairing_.results.values(), key=lambda r: r.obj.address):
        obj = result.obj
        objects.append({
            "prototype": obj.address, "size": obj.size, "names": obj.names, "section": obj.section,
            "owner": obj.owner, "owner_source": obj.owner_source, "anonymous": obj.anonymous,
            "release": result.base, "class": result.cls, "flags": sorted(result.flags), "withhold": result.withhold,
            "release_size": result.r_size, "size_state": result.size_state, "content": result.content,
            "release_section": result.release_section, "evidence": result.evidence,
            "conflict": result.conflict, "field_moves": sorted(set(result.field_moves)), "tier": result.tier,
            "contradictions": sorted(set(result.contradictions)),
            "witnesses": sorted({(v.kind, v.witness, v.a, v.b, v.d) for v in result.votes}),
        })
    return {"schema_version": 1, "inputs": data["inputs"], "coverage": data["coverage"],
            "conflicts": data["conflicts"], "contradictions": data["contradictions"], "mismatches": data["mismatches"],
            "key_rejected": sorted(pairing_.key_rejected),
            "self_check": {k: (dict(v) if isinstance(v, Counter) else v) for k, v in data["self_check"].items()},
            "objects": objects}
