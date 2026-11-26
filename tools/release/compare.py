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

PROTOTYPE = Path("support/socom.elf")
RELEASE = Path("support/SCUS_971.34")
SOURCE_GRAPH = Path("build/cache/source-graph.sqlite")
OUT_TSV = Path("docs/release/function-map.tsv")
OUT_MD = Path("docs/release/COMPARISON.md")
OUT_JSON = Path("build/release/function-map.json")


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


def run(root: Path, write: bool = True) -> dict:
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

    matcher = pairing.Matcher(p_fns, r_fns, proto_image.entry, release_image.entry)
    matcher.run()

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
            "null_below_deviating": round(sum(1 for v in null_large if v < pairing.DEVIATING_MIN) / max(1, len(null_large)), 3),
            "null_below_unsure": round(sum(1 for v in null_large if v < pairing.UNSURE_MIN) / max(1, len(null_large)), 3),
            "call_at_or_above_deviating": round(sum(1 for v in large["call"] if v >= pairing.DEVIATING_MIN) / max(1, len(large["call"])), 3),
        },
        "matcher": dict(sorted(matcher.stats.items())),
    }
    if write:
        for relative, text in ((OUT_TSV, report.write_tsv(rows)), (OUT_MD, report.markdown(data, rows)),
                               (OUT_JSON, report.write_json(data, rows))):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
    data["rows"] = rows
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=HERE.parent.parent)
    parser.add_argument("--no-write", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        data = run(arguments.root.resolve(), write=not arguments.no_write)
    except elfimage.InputRefused as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2
    except FileNotFoundError as error:
        print("missing input: %s" % Path(error.filename).name, file=sys.stderr)
        return 2
    counts = Counter(row["class"] for row in data["rows"])
    print(" ".join("%s=%d" % (c, counts[c]) for c in report.CLASSES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
