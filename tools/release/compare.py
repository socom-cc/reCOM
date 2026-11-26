"""Compare the release executable with the prototype, function by function.

    python tools/release/compare.py [--root <repo>] [--no-write]

Reads ``support/socom.elf`` (prototype) and ``support/SCUS_971.34`` (release),
refusing any file whose SHA-256 is not the pinned one, plus the optional
``build/cache/source-graph.sqlite`` and the ``src/`` annotations. Writes
``docs/release/function-map.tsv``, ``docs/release/COMPARISON.md`` and
``build/release/function-map.json``. Standard library only; deterministic.
"""
from __future__ import annotations

import argparse
import bisect
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import discover  # noqa: E402
import elfimage  # noqa: E402
import functions  # noqa: E402
import mips  # noqa: E402
import pairing  # noqa: E402
import protofacts  # noqa: E402
import report  # noqa: E402
import vtables  # noqa: E402

PROTOTYPE = Path("support/socom.elf")
RELEASE = Path("support/SCUS_971.34")
SOURCE_GRAPH = Path("build/cache/source-graph.sqlite")
SETTLED = Path("docs/release/settled-pairs.tsv")
OUT_TSV = Path("docs/release/function-map.tsv")
OUT_MD = Path("docs/release/COMPARISON.md")
OUT_JSON = Path("build/release/function-map.json")
SHEETS = Path("build/release/sheets")
LISTS = Path("build/release/lists")


def prototype_functions(image, found: list) -> dict[int, protofacts.ProtoFunction]:
    """Sized FUNC symbols, plus swept code no sized symbol covers (crt0)."""

    sized = protofacts.sized_functions(image)
    spans = sorted((f.address, f.address + f.size) for f in sized.values())
    starts = [s for s, _ in spans]
    names = protofacts.symbol_names(image)


    for f in found:
        index = bisect.bisect_right(starts, f.start) - 1
        overlaps = index >= 0 and spans[index][1] > f.start
        nxt = spans[index + 1][0] if index + 1 < len(spans) else None
        if overlaps or (nxt is not None and nxt < f.end):
            continue
        sized[f.start] = protofacts.ProtoFunction(f.start, f.size, list(names.get(f.start, [])), sized=False)
    return dict(sorted(sized.items()))


def mask_audit(image, protos) -> dict:
    words = mips.words_of(image.data)
    agree = missed = 0
    extra = Counter()
    for f in protos.values():
        _, kinds = mips.mask_function(words, (f.address - image.base) // 4, f.size // 4, image.base)
        for index, kind in enumerate(kinds):
            relocated = image.relocations.get(f.address + 4 * index) in (4, 5, 6, 7)
            if kind and relocated:
                agree += 1
            elif kind:
                extra[kind] += 1
            elif relocated:
                missed += 1
    return {"agree": agree, "missed": missed, "extra": sum(extra.values()), "extra_hi": extra["hi"],
            "extra_lo": extra["lo"], "extra_gp": extra["gp"]}


def validate_discovery(protos, found) -> dict:
    truth = {f.address: f.size for f in protos.values() if f.sized}
    by_start = {f.start: f for f in found}
    exact = sum(1 for a, s in truth.items() if a in by_start and by_start[a].size == s)
    start_only = sum(1 for a, s in truth.items() if a in by_start and by_start[a].size != s)
    missed = [a for a in truth if a not in by_start]
    false = [f for f in found if f.start not in truth]
    return {"truth": len(truth), "exact_extent": exact, "start_only": start_only, "missed": len(missed),
            "missed_bytes": sum(truth[a] for a in missed), "false_starts": len(false),
            "false_bytes": sum(f.size for f in false)}


SETTLED_COLUMNS = ("release", "prototype", "basis", "checker", "date")


def read_settled(path: Path) -> list[dict]:
    """Rows of the settled-pairs file: release address or ``removed``, prototype address or ``new``."""

    if not path.is_file():
        return []
    rows = []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or tuple(lines[0].split("\t")) != SETTLED_COLUMNS:
        raise pairing.SettledError("%s: the header must be %s" % (path.name, " ".join(SETTLED_COLUMNS)))
    for number, line in enumerate(lines[1:], 2):
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split("\t")
        if len(cells) != len(SETTLED_COLUMNS):
            raise pairing.SettledError("%s:%d: %d columns, expected %d" % (
                path.name, number, len(cells), len(SETTLED_COLUMNS)))
        release, proto = cells[0].strip(), cells[1].strip()
        try:
            r_value = None if release == "removed" else int(release, 16)
            p_value = None if proto == "new" else int(proto, 16)
        except ValueError:
            raise pairing.SettledError("%s:%d: addresses are hex, or removed / new" % (path.name, number)) from None
        if r_value is None and p_value is None:
            raise pairing.SettledError("%s:%d: removed and new together say nothing" % (path.name, number))
        if not cells[2].strip() or not cells[3].strip():
            raise pairing.SettledError("%s:%d: basis and checker are required" % (path.name, number))
        rows.append({"release": r_value, "prototype": p_value, "basis": cells[2].strip(),
                     "checker": cells[3].strip(), "date": cells[4].strip()})
    return rows


def run(root: Path, write: bool = True, use_settled: bool = True, sheet: str | None = None,
        sheet_list: str | None = None, lists_module: str | None = None, split: int = 1, sample: int = 15,
        out: Path | None = None, done: list[str] | None = None, first: str = "a") -> dict:
    """Compare; ``out`` (default: the repository root) receives every output under the same relative paths."""

    out = out or root
    proto_image = elfimage.load(root / PROTOTYPE, "prototype")
    release_image = elfimage.load(root / RELEASE, "release")

    proto_found = discover.Discovery(proto_image).run()
    release_discovery = discover.Discovery(release_image)
    release_found = release_discovery.run()

    protos = prototype_functions(proto_image, proto_found)
    has_graph = protofacts.apply_source_graph(protos, root / SOURCE_GRAPH)
    protofacts.apply_annotations(protos, root)

    p_words = mips.words_of(proto_image.data)
    r_words = mips.words_of(release_image.data)
    p_spans = [(f.address, f.address + f.size) for f in protos.values()]
    r_spans = [(f.start, f.end) for f in release_found]
    p_fns = functions.build("p", proto_image, p_words, p_spans, functions.find_gp(proto_image, p_words))
    r_fns = functions.build("r", release_image, r_words, r_spans, functions.find_gp(release_image, r_words))

    sizes = {s.address: s.size for s in proto_image.symbols if s.name.startswith("__vt__")}
    proto_tables = vtables.find_tables(proto_image, {f.address for f in p_fns}, sizes)
    release_tables = vtables.find_tables(release_image, {f.address for f in r_fns})
    table_pairs = vtables.pair_tables(proto_tables, release_tables)
    matcher = pairing.Matcher(p_fns, r_fns, proto_image.entry, release_image.entry, table_pairs)
    matcher.proto_tables, matcher.release_tables = proto_tables, release_tables
    settled_rows = read_settled(root / SETTLED) if use_settled else []
    matcher.run([(row["release"], row["prototype"]) for row in settled_rows])

    rows = report.build_rows(matcher, protos, {f.start: f.evidence for f in release_found})
    by_evidence = {"call": [], "position": [], "string": [], "global": []}
    for pair in matcher.pairs.values():
        if pair.p.key == pair.r.key:
            continue
        for name in by_evidence:
            if any(e == name or e.startswith(name + "-") for e in pair.evidence):
                by_evidence[name].append(pair.similarity)
    null = matcher.null_distribution()
    null_large = matcher.null_distribution(min_size=64)
    large = {"call": [], "position": []}
    for pair in matcher.pairs.values():
        if pair.p.key != pair.r.key and pair.p.size >= 64:
            for name in large:
                if name in pair.evidence:
                    large[name].append(pair.similarity)
    first_evidence = Counter()
    for f in release_found:
        for name in ("entry", "call", "prologue", "pointer-table", "code-ref", "data-pointer", "sweep"):
            if name in f.evidence:
                first_evidence[name] += 1
                break
    data = {
        "schema_version": 1,
        "inputs": {
            "prototype": {"sha256": proto_image.sha256, "entry": proto_image.entry, "base": proto_image.base,
                          "image_bytes": len(proto_image.data), "functions": len(protos)},
            "release": {"sha256": release_image.sha256, "entry": release_image.entry, "base": release_image.base,
                        "image_bytes": len(release_image.data), "functions": len(release_found)},
            "source_graph": has_graph,
        },
        "discovery": {"evidence": dict(first_evidence),
                      "prototype_validation": validate_discovery(protos, proto_found)},
        "coverage": discover.coverage(release_image, release_found),
        "mask_audit": mask_audit(proto_image, protos),
        "distributions": {
            "call": report.histogram(by_evidence["call"]),
            "position": report.histogram(by_evidence["position"]),
            "string": report.histogram(by_evidence["string"]),
            "global": report.histogram(by_evidence["global"]),
            "null": report.histogram(null),
            "call (>= 16 instructions)": report.histogram(large["call"]),
            "position (>= 16 instructions)": report.histogram(large["position"]),
            "null (>= 16 instructions)": report.histogram(null_large),
        },
        "thresholds": {
            "deviating": pairing.DEVIATING_MIN, "unsure": pairing.UNSURE_MIN,
            "strong_similarity": pairing.STRONG_SIMILARITY, "strong_operations": pairing.STRONG_OPERATIONS,
            "call_slot_operations": pairing.CALL_SLOT_OPERATIONS,
            "null_below_deviating": round(sum(1 for v in null_large if v < pairing.DEVIATING_MIN) / max(1, len(null_large)), 3),
            "null_below_unsure": round(sum(1 for v in null_large if v < pairing.UNSURE_MIN) / max(1, len(null_large)), 3),
            "call_at_or_above_deviating": round(sum(1 for v in large["call"] if v >= pairing.DEVIATING_MIN) / max(1, len(large["call"])), 3),
        },
        "matcher": dict(sorted(matcher.stats.items())),
        "vtables": {"prototype": len(proto_tables), "release": len(release_tables), "paired": len(table_pairs),
                    "slots_paired": sum(1 for tp, tr, _ in matcher.vtable_correspondences()
                                        if tp in matcher.pairs and matcher.pairs[tp].r.address == tr),
                    "slots_inserted": matcher.stats.get("vtable-slots-inserted", 0),
                    "slots_dropped": matcher.stats.get("vtable-slots-dropped", 0),
                    "new_virtuals": len({t for table in release_tables.values() for t in table.slots
                                         if t in matcher.r_by and t not in matcher.r_paired}),
                    "removed_virtuals": len({t for table in proto_tables.values() for t in table.slots
                                             if t in matcher.p_by and t not in matcher.pairs})},
        "settled": settled_rows,
    }
    if write:
        for relative, text in ((OUT_TSV, report.write_tsv(rows)), (OUT_MD, report.markdown(data, rows)),
                               (OUT_JSON, report.write_json(data, rows))):
            path = out / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
    if lists_module:
        import lists

        made = lists.split(lists_module, rows, matcher, split, sample, lists.parse_done(done), first)
        data["lists"] = [(path, item) for path, item in zip(lists.write(out, lists_module, made, sample, LISTS), made)]
    if sheet:
        import lists
        import sheets

        selected = lists.select(out, sheet, sheet_list, rows, LISTS) if sheet_list else None
        path = sheet_path(out, sheet, sheet_list)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = sheets.module_sheet(sheet, matcher, rows, protos, proto_image, release_image, selected=selected,
                                   title=sheet + (" list " + sheet_list if sheet_list else ""))
        path.write_bytes(text.encode("utf-8"))
        data["sheet"] = path
    data["rows"] = rows
    return data


def sheet_path(out: Path, module: str, letter: str | None = None) -> Path:
    """A flat sheet name: build/release/sheets/<module with / as ->[-<letter>].md under ``out``."""

    return out / SHEETS / ("%s%s.md" % (module.replace("/", "-"), "-" + letter if letter else ""))


def shown(path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return Path(path).name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=HERE.parent.parent)
    parser.add_argument("--no-write", action="store_true", help="compute without writing the map")
    parser.add_argument("--write-map", action="store_true",
                        help="with --sheet or --lists: also rewrite the map (otherwise only the sheet or lists)")
    parser.add_argument("--out", type=Path, metavar="DIR",
                        help="write every output under DIR (same relative paths) instead of the repository")
    parser.add_argument("--no-settled", action="store_true", help="ignore docs/release/settled-pairs.tsv")
    parser.add_argument("--sheet", metavar="MODULE", help="also write a check sheet for MODULE, e.g. gamez/zArchive")
    parser.add_argument("--list", metavar="LETTER", help="with --sheet: only the rows of that check list")
    parser.add_argument("--lists", metavar="MODULE", help="split MODULE's rows into check lists")
    parser.add_argument("--split", type=int, default=1, metavar="N", help="with --lists: how many lists")
    parser.add_argument("--sample", type=int, default=15, metavar="K", help="with --lists: deviating rows sampled per list")
    parser.add_argument("--done", action="append", metavar="FILE[:LO-HI]",
                        help="with --lists: an owner file (optionally a release range of it) already checked; repeatable")
    parser.add_argument("--first", default="a", metavar="LETTER", help="with --lists: the letter of the first list")
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    out = (root / arguments.out).resolve() if arguments.out else root
    write = not arguments.no_write and (arguments.write_map or not (arguments.sheet or arguments.lists))
    try:
        data = run(root, write=write, out=out,
                   use_settled=not arguments.no_settled, sheet=arguments.sheet, sheet_list=arguments.list,
                   lists_module=arguments.lists, split=arguments.split, sample=arguments.sample,
                   done=arguments.done, first=arguments.first)
    except elfimage.InputRefused as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2
    except pairing.SettledError as error:
        print("settled pairs: %s" % error, file=sys.stderr)
        return 2
    except ValueError as error:
        print("lists: %s" % error, file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print("missing input: %s" % Path(error.filename).name, file=sys.stderr)
        return 2
    counts = Counter(row["class"] for row in data["rows"])
    print(" ".join("%s=%d" % (c, counts[c]) for c in report.CLASSES))
    for path, item in data.get("lists", []):
        print("list %s: %d uncertain, %d sampled, %d exact, about %.0f minutes: %s" % (
            item["letter"], len(item["uncertain"]), len(item["sample"]), item["exact"], item["minutes"],
            shown(path, root)))
    if data.get("sheet"):
        print("sheet: %s" % shown(data["sheet"], root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
