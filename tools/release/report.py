"""Deterministic outputs: the function map (TSV and JSON) and COMPARISON.md."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from protofacts import module_of

CLASSES = ("exact", "deviating", "unsure", "new", "removed")
TSV_COLUMNS = (
    "release_address", "release_size", "class", "prototype_address", "prototype_size", "prototype_symbol",
    "prototype_classification", "prototype_library", "owner_file", "similarity", "shape_similarity",
    "operation_similarity", "size_delta", "evidence", "flags", "neighbour_group",
)


def hx(value) -> str:
    return "0x%06x" % value if isinstance(value, int) else "-"


def fmt(value) -> str:
    return "%.3f" % value if isinstance(value, float) else "-"


def build_rows(matcher, proto_facts: dict, release_found: dict) -> list[dict]:
    """One row per release function (address order), then one per removed prototype function."""

    rows = []
    owner_by_r = {}
    group_by_r = {}
    for f in matcher.R:
        pair_address = matcher.r_paired.get(f.address)
        if pair_address is None:
            continue
        facts = proto_facts.get(pair_address)
        if facts and facts.owner:
            owner_by_r[f.address] = facts.owner
        if facts:
            group_by_r[f.address] = (module_of(facts.owner) if facts.owner else
                                     ("provider:" + facts.library if facts.classification == "provider"
                                      else facts.classification or "unclassified"))
    ordered = [f.address for f in matcher.R]
    for index, f in enumerate(matcher.R):
        pair_address = matcher.r_paired.get(f.address)
        evidence_found = sorted(release_found.get(f.address, ()))
        row = {
            "release_address": f.address, "release_size": f.size, "class": "new",
            "prototype_address": None, "prototype_size": None, "prototype_symbol": "",
            "prototype_names": [], "prototype_classification": "", "prototype_library": "",
            "owner_file": "", "similarity": None, "shape_similarity": None, "operation_similarity": None,
            "size_delta": None, "evidence": [], "flags": [], "found_by": evidence_found,
            "neighbour_group": "", "prototype_unsized": False,
        }
        if pair_address is not None:
            pair = matcher.pairs[pair_address]
            facts = proto_facts.get(pair_address)
            row.update({
                "class": pair.cls, "prototype_address": pair.p.address, "prototype_size": pair.p.size,
                "similarity": round(pair.similarity, 3), "shape_similarity": round(pair.shape_similarity, 3),
                "operation_similarity": round(pair.operation_similarity, 3),
                "size_delta": f.size - pair.p.size, "evidence": sorted(pair.evidence), "flags": sorted(pair.flags),
            })
            if facts:
                row.update({
                    "prototype_symbol": facts.name, "prototype_names": list(facts.names),
                    "prototype_classification": facts.classification, "prototype_library": facts.library,
                    "owner_file": facts.owner, "prototype_unsized": not facts.sized,
                })
        else:
            # a new function between two release functions owned by the same file probably belongs there
            before = next((owner_by_r[a] for a in reversed(ordered[:index]) if a in owner_by_r), "")
            after = next((owner_by_r[a] for a in ordered[index + 1:] if a in owner_by_r), "")
            if before and before == after:
                row["owner_file"] = before
                row["flags"] = ["owner-guess"]
            group_before = next((group_by_r[a] for a in reversed(ordered[:index]) if a in group_by_r), "")
            group_after = next((group_by_r[a] for a in ordered[index + 1:] if a in group_by_r), "")
            if group_before and group_before == group_after:
                row["neighbour_group"] = group_before
            same = [p for p in matcher.p_by_key.get(f.key, ())]
            if same:
                row["flags"] = sorted(set(row["flags"]) | {"copy"})
        rows.append(row)
    for p in matcher.P:
        if p.address in matcher.pairs:
            continue
        facts = proto_facts.get(p.address)
        rows.append({
            "release_address": None, "release_size": None, "class": "removed",
            "prototype_address": p.address, "prototype_size": p.size,
            "prototype_symbol": facts.name if facts else "", "prototype_names": list(facts.names) if facts else [],
            "prototype_classification": facts.classification if facts else "",
            "prototype_library": facts.library if facts else "", "owner_file": facts.owner if facts else "",
            "prototype_unsized": bool(facts and not facts.sized),
            "similarity": None, "shape_similarity": None, "operation_similarity": None, "size_delta": None,
            "evidence": [], "flags": ["unsized-symbol"] if (facts and not facts.sized) else [], "found_by": [],
            "neighbour_group": "",
        })
    return rows


def write_tsv(rows: list[dict]) -> str:
    lines = ["\t".join(TSV_COLUMNS)]
    for row in rows:
        values = [
            hx(row["release_address"]), str(row["release_size"]) if row["release_size"] is not None else "-",
            row["class"], hx(row["prototype_address"]),
            str(row["prototype_size"]) if row["prototype_size"] is not None else "-",
            row["prototype_symbol"] or "-", row["prototype_classification"] or "-", row["prototype_library"] or "-",
            row["owner_file"] or "-", fmt(row["similarity"]), fmt(row["shape_similarity"]),
            fmt(row["operation_similarity"]),
            "%+d" % row["size_delta"] if row["size_delta"] is not None else "-",
            ",".join(row["evidence"]) or "-", ",".join(row["flags"]) or "-", row["neighbour_group"] or "-",
        ]
        lines.append("\t".join(v.replace("\t", " ") for v in values))
    return "\n".join(lines) + "\n"


def row_bytes(row) -> int:
    return row["release_size"] if row["release_size"] is not None else row["prototype_size"]


def group_label(row) -> str:
    if row["class"] == "new":
        return "(new: no prototype counterpart)"
    c = row["prototype_classification"]
    if c == "provider":
        return "provider: " + (row["prototype_library"] or "?")
    if not c:
        return "(no size in the symbol table: crt0)" if row.get("prototype_unsized") else "(unclassified)"
    return c


def module_label(row) -> str:
    module = module_of(row["owner_file"])
    if module:
        return module
    if row["class"] == "new":
        group = row["neighbour_group"]
        if group.startswith("provider:"):
            return "(provider: %s)" % group[len("provider:"):]
        return group if "/" in group else "(new, unplaced)"
    if row["prototype_classification"] == "provider":
        return "(provider: %s)" % (row["prototype_library"] or "?")
    return "(no owner file)"


def tally(rows, label):
    table = defaultdict(lambda: Counter())
    for row in rows:
        key = label(row)
        table[key][row["class"]] += 1
        table[key][row["class"] + "_bytes"] += row_bytes(row)
    return table


def _table(table, order=None, limit=None) -> list[str]:
    head = "| group | " + " | ".join(CLASSES) + " | " + " | ".join(c + " bytes" for c in CLASSES) + " |"
    out = [head, "|" + "---|" * (1 + 2 * len(CLASSES))]
    keys = order or sorted(table)
    for key in keys[:limit] if limit else keys:
        counts = table[key]
        out.append("| %s | %s | %s |" % (
            key.replace("|", "\\|"),
            " | ".join(str(counts[c]) for c in CLASSES),
            " | ".join(str(counts[c + "_bytes"]) for c in CLASSES),
        ))
    return out


def histogram(values, edges=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)) -> list[int]:
    counts = [0] * (len(edges) - 1)
    for v in values:
        for k in range(len(edges) - 1):
            if v < edges[k + 1] or k == len(edges) - 2:
                counts[k] += 1
                break
    return counts


def markdown(data: dict, rows: list[dict]) -> str:
    out = []
    add = out.append
    add("# Release comparison: prototype SCUS-972.05 against release SCUS-971.34")
    add("")
    add("Generated by `python tools/release/compare.py`; do not edit by hand. The per-function")
    add("table is [function-map.tsv](function-map.tsv); a machine-readable copy with every")
    add("field is written to `build/release/function-map.json`.")
    add("")
    add("## Inputs")
    add("")
    add("| role | SHA-256 | entry | loaded image | functions |")
    add("|---|---|---|---|---|")
    for side in ("prototype", "release"):
        info = data["inputs"][side]
        add("| %s | `%s` | %s | %s bytes at %s | %d |" % (
            side, info["sha256"], hx(info["entry"]), info["image_bytes"], hx(info["base"]), info["functions"]))
    add("")
    add("Prototype functions are the sized FUNC symbols plus the sweep-found code where the")
    add("symbol table gives no size (crt0). Release functions are found without symbols (below).")
    add("")
    add("## Classes")
    add("")
    add("- **exact**: equal masked instructions and layout (address operands masked: `j`/`jal`")
    add("  targets, address-range `lui` immediates, `$gp` offsets, low halves paired with an")
    add("  address `lui` through the function's control flow), and every call and data")
    add("  operand consistent with the other pairs;")
    add("- **deviating**: the same function with differences;")
    add("- **unsure**: a candidate pair the evidence does not settle (see the unsure section);")
    add("- **new**: release function with no prototype counterpart;")
    add("- **removed**: prototype function with no release counterpart.")
    add("")
    add("Similarity is `difflib.SequenceMatcher.ratio()` over the masked instruction words,")
    add("2M/(n+m) with M instructions matched in order: the share of instructions equal.")
    add("Shape similarity is the same over instructions with every immediate removed; flag")
    add("`imm-only` marks equal-size pairs whose shapes are identical, so only immediates or")
    add("offsets differ (such a pair is deviating whatever its similarity). Operation similarity")
    add("is the same over the operations alone (no registers, immediates or targets): it")
    add("survives register-allocation changes.")
    add("")
    add("## Totals")
    add("")
    totals = tally(rows, lambda r: "all")
    authored = tally([r for r in rows if r["prototype_classification"] == "authored"], lambda r: "authored")
    authored_new = tally([r for r in rows if r["prototype_classification"] == "authored"
                          or (r["class"] == "new" and "/" in module_label(r) and not module_label(r).startswith("("))],
                         lambda r: "x")
    add("| scope | " + " | ".join(CLASSES) + " | " + " | ".join(c + " bytes" for c in CLASSES) + " |")
    add("|" + "---|" * (1 + 2 * len(CLASSES)))
    for name, table in (("all functions", totals.get("all", Counter())),
                        ("authored (by prototype classification)", authored.get("authored", Counter())),
                        ("authored, with new functions placed in authored modules", authored_new.get("x", Counter()))):
        add("| %s | %s | %s |" % (name, " | ".join(str(table[c]) for c in CLASSES),
                                   " | ".join(str(table[c + "_bytes"]) for c in CLASSES)))
    add("")
    imm_only = [r for r in rows if r["class"] == "deviating" and "imm-only" in r["flags"]]
    add("Bytes are release sizes, prototype sizes for removed functions. Of the deviating")
    add("functions, %d (%d bytes) differ only in immediates or offsets (`imm-only`)." % (
        len(imm_only), sum(r["release_size"] for r in imm_only)))
    moved = [r for r in rows if "moved" in r["flags"]]
    add("%d pairs are out of order relative to the order anchors (`moved`)." % len(moved))
    add("")
    add("## By prototype classification")
    add("")
    table = tally(rows, group_label)
    out.extend(_table(table, sorted(table, key=lambda k: (-sum(table[k][c] for c in CLASSES), k))))
    add("")
    add("## By module")
    add("")
    add("Module = `gamez/<module>` or `Apps/FTS/<part>` of the owning source file (prototype")
    add("annotations; new functions take the file of their paired neighbours when both agree,")
    add("flag `owner-guess`). Sorted by changed bytes (deviating + unsure + new + removed).")
    add("")
    table = tally(rows, module_label)

    def changed(key):
        return sum(table[key][c + "_bytes"] for c in ("deviating", "unsure", "new", "removed"))

    out.extend(_table(table, sorted(table, key=lambda k: (-changed(k), k))))
    add("")
    add("## Function discovery and coverage (release)")
    add("")
    disc = data["discovery"]
    add("Starts by first evidence: " + ", ".join("%s %d" % kv for kv in sorted(disc["evidence"].items())) + ".")
    add("")
    validation = disc.get("prototype_validation")
    if validation:
        add("The same discovery run on the prototype, with its symbols hidden, against its symbol")
        add("table: %(truth)d sized functions; %(exact_extent)d found with the exact extent, "
            "%(start_only)d with the right start but another end, %(missed)d missed (%(missed_bytes)d bytes), "
            "%(false_starts)d starts that are not symbols (%(false_bytes)d bytes)." % validation)
        add("")
    add("| cluster start | end | functions | covered bytes | zero padding | unexplained bytes |")
    add("|---|---|---|---|---|---|")
    for c in data["coverage"]["clusters"]:
        add("| %s | %s | %d | %d | %d | %d |" % (hx(c["start"]), hx(c["end"]), c["functions"], c["covered"],
                                                  c["padding"], sum(u["nonzero_bytes"] for u in c["unexplained"])))
    add("")
    gaps = [g for c in data["coverage"]["clusters"] for g in c["unexplained"]]
    gaps.sort(key=lambda g: (-g["nonzero_bytes"], g["start"]))
    add("Unexplained gaps (non-zero bytes between found functions): %d." % len(gaps))
    if gaps:
        add("")
        add("| start | end | non-zero bytes |")
        add("|---|---|---|")
        for g in gaps[:40]:
            add("| %s | %s | %d |" % (hx(g["start"]), hx(g["end"]), g["nonzero_bytes"]))
        if len(gaps) > 40:
            add("")
            add("(%d more in the JSON copy.)" % (len(gaps) - 40))
    add("")
    add("## Masking rule check (prototype relocations)")
    add("")
    mask = data["mask_audit"]
    add("Every relocated instruction field of the prototype's functions against the masking rule:")
    add("%(agree)d masked fields carry a relocation; %(missed)d relocated fields are not masked; "
        "%(extra)d masked fields have no relocation (%(extra_hi)d `lui`, %(extra_lo)d low halves, "
        "%(extra_gp)d `$gp`). The extra masks are mostly integer constants inside the address "
        "range (0x100000, 0x3f0000) and linker-defined symbols; a difference in such a constant "
        "is invisible to exact matching." % mask)
    add("")
    add("## Similarity distributions and thresholds")
    add("")
    dist = data["distributions"]
    edges = ["%.1f-%.1f" % (k / 10, (k + 1) / 10) for k in range(10)]
    add("| similarity | " + " | ".join(edges) + " |")
    add("|" + "---|" * 11)
    for name in sorted(dist):
        add("| %s | %s |" % (name, " | ".join(str(v) for v in dist[name])))
    add("")
    add("`call`: non-exact pairs made by call-tree propagation (the pairing does not look at")
    add("similarity, so this is the distribution of real counterparts); `position`: pairs from the")
    add("positional alignment (which needs %.2f to propose a pair); `string`: pairs from unique" % data["thresholds"]["unsure"])
    add("shared strings; `global`: mutual best matches anywhere among the functions left over")
    add("(moved code, similarity >= %.2f); `null`: a prototype function of a call/position pair against the release" % data["thresholds"]["unsure"])
    add("functions two places before and after its partner, of comparable size (unrelated pairs).")
    add("Small functions look alike (accessors, stubs), so the null of all sizes has a tail near")
    add("1.0; for them the order between anchors decides and a pair is unsure (`ambiguous`) when an")
    add("unpaired alternative in the same gap scores within 0.05.")
    add("")
    t = data["thresholds"]
    add("Thresholds, from the >= 16-instruction rows: %.1f%% of null pairs stay below %.2f and"
        % (100 * t["null_below_deviating"], t["deviating"]))
    add("%.1f%% below %.2f, while %.1f%% of call-tree counterparts reach %.2f. So:"
        % (100 * t["null_below_unsure"], t["unsure"], 100 * t["call_at_or_above_deviating"], t["deviating"]))
    add("")
    add("- a positional, `global` or `call-deviating` pair is deviating at similarity >= %.2f, unsure" % t["deviating"])
    add("  from %.2f to %.2f;" % (t["unsure"], t["deviating"]))
    add("- a pair with independent evidence (called at the same call site of an exact pair, a")
    add("  unique shared string, the entry point) is deviating at similarity >= %.2f or operation" % t["strong_similarity"])
    add("  similarity >= %.2f, otherwise unsure (flag `low-similarity`);" % t["strong_operations"])
    add("- an exact byte match whose calls lead to functions paired elsewhere (`call-conflict`) or")
    add("  whose data operands point to another kind of region (`ref-kind`) is unsure.")
    add("")
    add("## Unsure pairs")
    add("")
    unsure = [r for r in rows if r["class"] == "unsure"]
    reasons = Counter()
    for r in unsure:
        reason = [f for f in r["flags"] if f in ("call-conflict", "ref-kind", "low-similarity")]
        reasons[",".join(reason) or "other"] += 1
    add("%d pairs: " % len(unsure) + ", ".join("%s %d" % kv for kv in sorted(reasons.items())) + ".")
    add("")
    add("| release | prototype | symbol | similarity | evidence | flags |")
    add("|---|---|---|---|---|---|")
    for r in sorted(unsure, key=lambda r: (-row_bytes(r), r["release_address"]))[:40]:
        add("| %s | %s | `%s` | %s | %s | %s |" % (hx(r["release_address"]), hx(r["prototype_address"]),
                                                   r["prototype_symbol"].replace("|", "\\|"), fmt(r["similarity"]),
                                                   ",".join(r["evidence"]), ",".join(r["flags"])))
    if len(unsure) > 40:
        add("")
        add("(%d more in function-map.tsv.)" % (len(unsure) - 40))
    add("")
    add("## Largest new functions")
    add("")
    add("| release | size | probable owner | between functions of |")
    add("|---|---|---|---|")
    new = sorted((r for r in rows if r["class"] == "new"), key=lambda r: (-r["release_size"], r["release_address"]))
    for r in new[:25]:
        add("| %s | %d | %s | %s |" % (hx(r["release_address"]), r["release_size"], r["owner_file"] or "-",
                                     r["neighbour_group"] or "-"))
    add("")
    add("## Largest removed functions")
    add("")
    add("| prototype | size | symbol | owner |")
    add("|---|---|---|---|")
    removed = sorted((r for r in rows if r["class"] == "removed"),
                     key=lambda r: (-r["prototype_size"], r["prototype_address"]))
    for r in removed[:25]:
        add("| %s | %d | `%s` | %s |" % (hx(r["prototype_address"]), r["prototype_size"],
                                         r["prototype_symbol"].replace("|", "\\|"), r["owner_file"] or "-"))
    add("")
    add("## Regenerate")
    add("")
    add("```powershell")
    add("python tools/release/compare.py")
    add("uv run --no-project --with pytest python -m pytest tests/release -q")
    add("```")
    add("")
    add("The tool reads `support/socom.elf` and `support/SCUS_971.34` (refused unless their")
    add("SHA-256 values are the pinned ones), the optional `build/cache/source-graph.sqlite`")
    add("for prototype classification, and the `src/` annotations for owners. Same inputs, same bytes.")
    add("")
    return "\n".join(out)


def write_json(data: dict, rows: list[dict]) -> str:
    payload = dict(data)
    payload["rows"] = rows
    return json.dumps(payload, indent=1, sort_keys=True) + "\n"
