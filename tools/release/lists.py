"""Check lists: a module's rows split into lists of about equal checking work.

Each list holds whole owner files where possible (a file with more work than one
list carries is split by address range). A list shows its uncertain rows
(unsure, new, removed, and the weak pairs: evidence ``slot-only`` or flag
``role-only``), then a deterministic sample of its other deviating rows, then the
number of its exact rows. Unplaced new functions inside a list's address ranges
join that list. The work estimate per row comes from the first two module checks.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict

import report

MINUTES = {"unsure": 4.0, "new": 4.5, "removed": 4.5, "weak": 3.0, "sample": 1.5}
LETTERS = "abcdefghijklmnopqrstuvwxyz"
RANGE_GAP = 0x2000  # rows of one file further apart than this make separate address ranges


def slug(module: str) -> str:
    return module.replace("/", "-")


def is_weak(row: dict) -> bool:
    return row["class"] == "deviating" and ("slot-only" in row["evidence"] or "role-only" in row["flags"])


def kind(row: dict) -> str | None:
    """The work class of an uncertain row, or None."""

    if row["class"] in ("unsure", "new", "removed"):
        return row["class"]
    if is_weak(row) or {"identical-copy", "caller-mismatch", "callee-mismatch", "class-mismatch"} & set(row["flags"]):
        return "weak"
    return None


def key(row: dict) -> str:
    if row["release_address"] is not None:
        return "r:%x" % row["release_address"]
    return "p:%x" % row["prototype_address"]


def positions(matcher, rows: list[dict]) -> dict[str, int]:
    """A release-side position for every row; a removed row sits after its paired prototype predecessor."""

    out = {}
    for row in rows:
        if row["release_address"] is not None:
            out[key(row)] = row["release_address"]
            continue
        index = matcher.p_index[row["prototype_address"]]
        position = 0
        for k in range(index - 1, -1, -1):
            pair = matcher.pairs.get(matcher.P[k].address)
            if pair is not None:
                position = pair.r.address
                break
        out[key(row)] = position
    return out


def parse_done(items: list[str]) -> list[tuple[str, int, int]]:
    """``file`` or ``file:0xlo-0xhi`` (release range, inclusive): rows already checked."""

    out = []
    for item in items or []:
        name, _, span = item.partition(":")
        lo, hi = 0, 1 << 32
        if span:
            first, _, last = span.partition("-")
            lo, hi = int(first, 16), int(last, 16)
        out.append((name, lo, hi))
    return out


def split(module: str, rows: list[dict], matcher, count: int, sample: int = 15, done=(), first: str = "a") -> list[dict]:
    selected = [row for row in rows if report.module_label(row) == module]
    if not selected:
        raise ValueError("no rows for module %s" % module)
    count = max(1, min(count, len(LETTERS) - LETTERS.index(first)))
    where = positions(matcher, rows)
    if done:
        def checked(row):
            owner = row["owner_file"]
            return any(owner.endswith("/" + name) or owner == name for name, lo, hi in done
                       if lo <= where[key(row)] <= hi)
        excluded = [row for row in selected if checked(row)]
        selected = [row for row in selected if not checked(row)]
        done_ranges = [(lo, hi) for _, lo, hi in done]
    else:
        excluded, done_ranges = [], []
    files = defaultdict(list)
    ordered = sorted(selected, key=lambda row: (where[key(row)], key(row)))
    last_owner = ""
    for row in ordered:
        # a row of the module with no owner file (a new function whose neighbours disagree)
        # goes with the file just before it
        owner = row["owner_file"] or last_owner or "(no owner)"
        last_owner = row["owner_file"] or last_owner
        files[owner].append(row)

    def work(part):
        return sum(MINUTES[kind(row)] for row in part if kind(row))

    total = sum(work(part) for part in files.values())
    target = total / count if total else 0
    units = []  # (owner file, rows), a file split into address chunks when it is too large
    for owner in sorted(files):
        part = sorted(files[owner], key=lambda row: (where[key(row)], key(row)))
        if target and work(part) > 0.6 * target:
            # big files go in address chunks of about half a list, so lists can be balanced
            pieces = max(2, round(2 * work(part) / target))
            share = work(part) / pieces
            chunk, done = [], 0.0
            for row in part:
                chunk.append(row)
                done += MINUTES[kind(row)] if kind(row) else 0
                if done >= share and len(units) < 10 * count and row is not part[-1]:
                    units.append((owner, chunk))
                    chunk, done = [], 0.0
            if chunk:
                units.append((owner, chunk))
        else:
            units.append((owner, part))
    start = LETTERS.index(first)
    bins = [{"letter": LETTERS[start + i], "units": [], "work": 0.0} for i in range(count)]
    for owner, part in sorted(units, key=lambda unit: (-work(unit[1]), unit[0], where[key(unit[1][0])])):
        target_bin = min(bins, key=lambda b: (b["work"], b["letter"]))
        target_bin["units"].append((owner, part))
        target_bin["work"] += work(part)
    # unplaced new functions inside a list's address ranges join that list
    unplaced = [row for row in rows if row["class"] == "new" and report.module_label(row) == "(new, unplaced)"
                and not (excluded and any(lo <= row["release_address"] <= hi for lo, hi in done_ranges
                                          if hi - lo < 1 << 31))]
    lists = []
    for b in bins:
        members = [row for _, part in b["units"] for row in part]
        ranges = []
        for owner, part in b["units"]:
            span = sorted(where[key(row)] for row in part if row["release_address"] is not None) or [where[key(part[0])]]
            start = previous = span[0]
            for position in span[1:]:
                if position - previous > RANGE_GAP:  # a row far from the others (a moved template) starts a range
                    ranges.append((owner, start, previous))
                    start = position
                previous = position
            ranges.append((owner, start, previous))
        extra = [row for row in unplaced if any(lo <= row["release_address"] <= hi for _, lo, hi in ranges)]
        members += extra
        uncertain = sorted((row for row in members if kind(row)), key=lambda row: (where.get(key(row), 0), key(row)))
        deviating = sorted((row for row in members if row["class"] == "deviating" and not is_weak(row)), key=key)
        rng = random.Random("%s:%s" % (module, b["letter"]))
        sampled = sorted(rng.sample(deviating, min(sample, len(deviating))), key=lambda row: (where[key(row)], key(row)))
        minutes = sum(MINUTES[kind(row)] for row in uncertain) + MINUTES["sample"] * len(sampled)
        lists.append({
            "letter": b["letter"], "ranges": ranges, "uncertain": uncertain, "sample": sampled,
            "deviating": len(deviating), "exact": sum(1 for row in members if row["class"] == "exact"),
            "unplaced": len(extra), "minutes": minutes,
        })
    return lists


def render(module: str, item: dict, sample: int) -> str:
    out = ["# Check list %s-%s" % (module, item["letter"]), "",
           "Generated by `python tools/release/compare.py --lists %s`; not tracked. Estimated work %.0f minutes"
           % (module, item["minutes"]),
           "(unsure %.0f, new or removed %.1f, weak pair %.0f, sampled deviating %.1f minutes per row)."
           % (MINUTES["unsure"], MINUTES["new"], MINUTES["weak"], MINUTES["sample"]), "",
           "Owner files (release address ranges):", ""]
    for owner, lo, hi in item["ranges"]:
        out.append("- %s: 0x%x-0x%x" % (owner, lo, hi))
    out += ["", "## Uncertain rows (%d)" % len(item["uncertain"]), "",
            "| release | prototype | class | symbol | evidence | flags | owner |", "|---|---|---|---|---|---|---|"]
    for row in item["uncertain"]:
        out.append(_line(row))
    out += ["", "## Sampled deviating rows (%d of %d, seed `%s:%s`)" % (
        len(item["sample"]), item["deviating"], module, item["letter"]), "",
        "| release | prototype | class | symbol | evidence | flags | owner |", "|---|---|---|---|---|---|---|"]
    for row in item["sample"]:
        out.append(_line(row))
    out += ["", "Exact rows in this list: %d (not listed). Unplaced new functions included: %d." % (
        item["exact"], item["unplaced"]), ""]
    return "\n".join(out)


def _line(row: dict) -> str:
    return "| %s | %s | %s%s | `%s` | %s | %s | %s |" % (
        report.hx(row["release_address"]), report.hx(row["prototype_address"]), row["class"],
        " (weak)" if is_weak(row) else "", (row["prototype_symbol"] or "-").replace("|", "\\|"),
        ",".join(row["evidence"]) or "-", ",".join(row["flags"]) or "-", row["owner_file"] or "-")


def membership(lists: list[dict]) -> dict:
    return {item["letter"]: [key(row) for row in item["uncertain"] + item["sample"]] for item in lists}


def write(root, module: str, lists: list[dict], sample: int, directory) -> list:
    folder = root / directory
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for item in lists:
        path = folder / ("%s-%s.md" % (slug(module), item["letter"]))
        path.write_bytes(render(module, item, sample).encode("utf-8"))
        paths.append(path)
    index = folder / ("%s.json" % slug(module))
    index.write_bytes((json.dumps({"module": module, "lists": membership(lists)}, indent=1, sort_keys=True) + "\n")
                      .encode("utf-8"))
    return paths


def select(root, module: str, letter: str, rows: list[dict], directory) -> list[dict]:
    index = root / directory / ("%s.json" % slug(module))
    if not index.is_file():
        raise ValueError("no lists for %s yet: run --lists %s --split <n> first" % (module, module))
    wanted = json.loads(index.read_text(encoding="utf-8"))["lists"].get(letter)
    if wanted is None:
        raise ValueError("no list %s for %s" % (letter, module))
    wanted = set(wanted)
    return [row for row in rows if key(row) in wanted]


PAIR_CLASSES = ("exact", "deviating", "unsure")


def split_pairs(module: str, rows: list[dict], matcher, count: int, only: list[str] | None = None) -> list[dict]:
    """Every committed pair of the module's owner files (optionally only some files), for a cross-check.

    No sample and no uncertain rows: the lists hold pairs, whole owner files kept
    together where possible, a file larger than a list split by address range.
    """

    selected = [row for row in rows if report.module_label(row) == module and row["class"] in PAIR_CLASSES
                and (not only or any(row["owner_file"].endswith("/" + name) or row["owner_file"] == name
                                     for name in only))]
    if not selected:
        raise ValueError("no committed pairs for module %s" % module)
    count = max(1, min(count, len(LETTERS)))
    target = len(selected) / count
    files = defaultdict(list)
    for row in sorted(selected, key=lambda row: (row["release_address"], key(row))):
        files[row["owner_file"] or "(no owner)"].append(row)
    units = []
    for owner in sorted(files):
        part = files[owner]
        if len(part) > 1.15 * target:
            pieces = max(2, round(len(part) / target))
            size = -(-len(part) // pieces)
            units.extend((owner, part[k:k + size]) for k in range(0, len(part), size))
        else:
            units.append((owner, part))
    bins = [{"letter": LETTERS[i], "units": []} for i in range(count)]
    for owner, part in sorted(units, key=lambda unit: (-len(unit[1]), unit[0], unit[1][0]["release_address"])):
        target_bin = min(bins, key=lambda b: (sum(len(p) for _, p in b["units"]), b["letter"]))
        target_bin["units"].append((owner, part))
    out = []
    for b in bins:
        members = sorted((row for _, part in b["units"] for row in part), key=lambda row: row["release_address"])
        ranges = [(owner, part[0]["release_address"], part[-1]["release_address"]) for owner, part in b["units"]]
        out.append({"letter": b["letter"], "ranges": ranges, "pairs": members,
                    "classes": dict(Counter(row["class"] for row in members))})
    return out


def render_pairs(module: str, item: dict) -> str:
    out = ["# Cross-check list %s-%s (committed pairs)" % (module, item["letter"]), "",
           "Generated by `python tools/release/compare.py --lists %s --pairs-only`; not tracked. %d pairs (%s)." % (
               module, len(item["pairs"]), ", ".join("%s %d" % kv for kv in sorted(item["classes"].items()))), "",
           "Owner files (release address ranges):", ""]
    for owner, lo, hi in item["ranges"]:
        out.append("- %s: 0x%x-0x%x" % (owner, lo, hi))
    out += ["", "| release | prototype | class | symbol | evidence | flags | owner |", "|---|---|---|---|---|---|---|"]
    out += [_line(row) for row in item["pairs"]]
    return "\n".join(out) + "\n"


def write_pairs(root, module: str, lists: list[dict], directory) -> list:
    folder = root / directory
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for item in lists:
        path = folder / ("%s-pairs-%s.md" % (slug(module), item["letter"]))
        path.write_bytes(render_pairs(module, item).encode("utf-8"))
        paths.append(path)
    index = folder / ("%s-pairs.json" % slug(module))
    index.write_bytes((json.dumps({"module": module, "lists": {item["letter"]: [key(row) for row in item["pairs"]]
                                                               for item in lists}}, indent=1, sort_keys=True) + "\n")
                      .encode("utf-8"))
    return paths
