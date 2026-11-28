"""Stage 3, step one: carry function starts, names and provenance comments into the release program.

    python tools/release/names.py --plan gamez/zArchive          # or --plan --all
    python tools/release/names.py --apply build/release/names/plan-gamez-zArchive.json --dry-run
    python tools/release/names.py --apply build/release/names/plan-gamez-zArchive.json --yes [--batch N]
    python tools/release/names.py --confirm-saved build/release/names/plan-gamez-zArchive.apply-001.json

``--plan`` reads ``build/release/function-map.json`` (refused unless it reproduces
``docs/release/function-map.tsv``), the settled pairs, the module notes and, read-only, both
Ghidra programs, and writes ``build/release/names/plan-<module>.json`` with a summary ``.md``.
The plan is deterministic and names no local path. ``--apply`` checks the bridge (exactly the
two programs open, the release program's recorded SHA-256, analysis idle), the plan's own digest
and that it was made from the current map, then makes the planned changes to ``SCUS_971.34``
only, per function in this order: create, rename, label, plate comment, each read back; a
failed read-back stops the run. It compares a snapshot of every release function before and
after and reports each change it did not make. It never saves. ``--dry-run`` does every read
and check and sends no write. Changes that read back go into ``docs/release/ghidra-applied.tsv``
as unsaved rows of the apply report; ``--confirm-saved`` re-reads them after the coordinator
saved and marks them saved, ``--discard-unsaved`` drops them after a close without saving. An
apply is refused while unsaved rows exist.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import createflow  # noqa: E402
import elfimage  # noqa: E402
import ghidra_bridge as gb  # noqa: E402
import mips  # noqa: E402
import report  # noqa: E402
from elfimage import PROTOTYPE_SHA256, RELEASE_SHA256  # noqa: E402

MAP_JSON = Path("build/release/function-map.json")
MAP_TSV = Path("docs/release/function-map.tsv")
RELEASE_ELF = Path("support/SCUS_971.34")
NOTES = Path("docs/release/notes")
OUT = Path("build/release/names")
RECORD = Path("docs/release/ghidra-applied.tsv")
RECORD_COLUMNS = ("release_address", "applied", "value", "source_pair", "date", "state")
PLAN_KIND = "socom-release-names-plan"
PLAN_SCHEMA = 3  # 3: label clashes, holes, jump holders, predicted thunks, creates made first
PLATE_PREFIX = "Release map: "
SHA_OPTION = "Executable SHA256"
NEAR_BYTES = 0x4000  # bodies within this distance of a create are re-read after it
SETTLE_SECONDS = 300  # longest wait for analysis to go idle
QUIET_SECONDS = 2.0  # idle this long without a break counts as settled
POLL_SECONDS = 0.2

# Flags whose prototype name does not carry over by itself: the plate names it instead.
NAME_BLOCK = {
    "name-changed": "the checker found the release name differs (name-changed)",
    "split": "the release function is part of the prototype function (split)",
    "merged": "the release function absorbed another prototype function (merged)",
    "rename-possible": "the checker left a class rename open (rename-possible)",
}
# Function actions that leave a map function without any write.
UNNAMED_ACTIONS = ("inside", "no-instruction", "excluded", "create-withheld")
_DEFAULT_NAME = re.compile(r"^(?:thunk_)?FUN_[0-9a-f]{8}$")


class Refused(RuntimeError):
    """An input, plan or live state this tool will not work from."""


class Stop(RuntimeError):
    """The apply stopped; ``written`` holds what read back before."""


def hx(value: int) -> str:
    return "0x%06x" % value


def is_default_name(name: str | None) -> bool:
    return bool(name) and bool(_DEFAULT_NAME.match(name))


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- inputs ----------------------------------------------------------------------------------

def load_map(root: Path) -> tuple[list[dict], list[dict], str]:
    path, tsv = root / MAP_JSON, root / MAP_TSV
    if not path.is_file():
        raise Refused(f"{MAP_JSON.as_posix()} is missing: run python tools/release/compare.py (about 90 s)")
    data = json.loads(path.read_text(encoding="utf-8"))
    text = tsv.read_text(encoding="utf-8")
    if report.write_tsv(data["rows"]) != text.replace("\r\n", "\n"):
        raise Refused(f"{MAP_JSON.as_posix()} does not reproduce {MAP_TSV.as_posix()}: rerun compare.py")
    if data["inputs"]["release"]["sha256"] != RELEASE_SHA256 or data["inputs"]["prototype"]["sha256"] != PROTOTYPE_SHA256:
        raise Refused("the function map describes other executables")
    return data["rows"], data["settled"], sha256_text(text.replace("\r\n", "\n"))


def notes_index(root: Path) -> dict[str, list[str]]:
    """Address token -> the notes that mention it (repo-relative, sorted)."""

    index: dict[str, list[str]] = defaultdict(list)
    for note in sorted((root / NOTES).glob("*.md")):
        rel = (NOTES / note.name).as_posix()
        text = note.read_text(encoding="utf-8")
        for token in sorted(set(re.findall(r"0x[0-9a-f]{6}\b", text))):
            index[token].append(rel)
    return index


def note_for(settled_row: dict | None, address: int, index: dict, root: Path) -> str | None:
    if not settled_row:
        return None
    candidates = index.get(hx(address), [])
    checker = settled_row.get("checker") or ""
    named = [n for n in candidates if checker and checker in (root / n).read_text(encoding="utf-8")]
    return (named or candidates or [None])[0]


# --- live reads ------------------------------------------------------------------------------

def preflight(bridge) -> dict:
    """Bridge reachable, exactly the two programs open, recorded hashes, analysis idle."""

    errors: list[str] = []
    try:
        programs = bridge.get("list_open_programs")
        rows = programs.get("programs", []) if isinstance(programs, dict) else []
        found = {row.get("name"): row.get("path") for row in rows if isinstance(row, dict)}
        if found != gb.PROGRAMS:
            errors.append(f"open programs are {sorted(found.items())}, expected exactly {sorted(gb.PROGRAMS.items())}")
        hashes = {}
        for program, expected in ((gb.RELEASE_PROGRAM, RELEASE_SHA256), (gb.PROTOTYPE_PROGRAM, PROTOTYPE_SHA256)):
            if program not in found:
                continue
            value = gb.program_option(bridge.get("get_program_options", program, group="Program Information"), SHA_OPTION)
            hashes[program] = value
            if not isinstance(value, str) or value.casefold() != expected:
                errors.append(f"{program} records {SHA_OPTION} {value!r}, expected {expected}")
            status = bridge.get("analysis_status", program)
            if not (isinstance(status, dict) and status.get("analyzed") is True and status.get("analyzing") is False):
                errors.append(f"{program}: analysis is not complete and idle ({status!r})")
    except gb.BridgeError as exc:
        errors.append(str(exc))
        hashes = {}
    return {"ok": not errors, "errors": errors, "executable_sha256": hashes}


def function_list(bridge, program: str) -> dict[int, dict]:
    value = bridge.get("list_functions_enhanced", program, offset=0, limit=100000)
    if not isinstance(value, dict) or not isinstance(value.get("functions"), list):
        raise gb.BridgeError(f"list_functions_enhanced ({program}) did not answer a list")
    out = {}
    for row in value["functions"]:
        out[int(row["address"], 16)] = {"name": row["name"], "thunk": bool(row.get("isThunk"))}
    if value.get("count") not in (None, len(out)):
        raise gb.BridgeError(f"list_functions_enhanced ({program}) returned {len(out)} of {value.get('count')}")
    return out


def read_function(bridge, program: str, address: int) -> dict | None:
    return gb.parse_function(bridge.get("get_function_by_address", program, address=hx(address)))


def read_plate(bridge, address: int) -> str | None:
    """The plate comment of the function starting at ``address`` ('' if none)."""

    value = bridge.get("get_plate_comment", gb.RELEASE_PROGRAM, address=hx(address))
    if not isinstance(value, dict) or "error" in value:
        raise gb.BridgeError(f"get_plate_comment {hx(address)}: {value!r}")
    if int(str(value.get("address")), 16) != address:
        raise gb.BridgeError(f"get_plate_comment {hx(address)} answered the function at {value.get('address')}")
    return value.get("comment") or ""


def live_function(bridge, address: int, assumed: frozenset = frozenset()) -> dict | None:
    """The release function at or containing ``address``, ignoring functions assumed removed."""

    found = read_function(bridge, gb.RELEASE_PROGRAM, address)
    return None if found is None or found["entry"] in assumed else found


def jump_targets(bridge, address: int) -> list[int]:
    """Flow targets Ghidra recorded for a computed jump (``get_xrefs_from``)."""

    text = bridge.get("get_xrefs_from", gb.RELEASE_PROGRAM, address=hx(address), offset=0, limit=1000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"get_xrefs_from {hx(address)}: {text!r}")
    return sorted(int(m.group(1), 16) for m in re.finditer(r"^To ([0-9a-fA-F]+)\b.*\[(\w*JUMP\w*)\]$", text, re.M))


def plan_creates(rows, bridge, live_list: dict, assumed: frozenset, image, exclude) -> tuple[dict, dict]:
    """Every map start Ghidra would have to create, whole map, with its safety class.

    A create is sent only when ``CreateFunctionCmd`` is predicted to give it exactly the map
    extent (``createflow``): safe in any order, ordered (the creates it flows into first), or
    withheld with the reason.
    """

    candidates: dict[int, int] = {}
    for row in rows:
        address = row["release_address"]
        if address is None or address in live_list or address in exclude:
            continue
        if live_function(bridge, address, assumed):
            continue  # inside another function's body
        audit = bridge.get("audit_global", gb.RELEASE_PROGRAM, address=hx(address))
        if isinstance(audit, dict) and audit.get("is_code_address"):
            candidates[address] = row["release_size"]
    details = {a: read_function(bridge, gb.RELEASE_PROGRAM, a) for a in live_list}
    noreturn = {a for a, d in details.items() if d and d["noreturn"]}
    spans = [(d["body_min"], d["body_max"]) for d in details.values() if d]
    map_starts = {r["release_address"] for r in rows if r["release_address"] is not None}
    # Existing functions holding a plain jump (not a call) to a map start that is no function yet:
    # analysis turned such jumps into calls and made functions there after a nearby create.
    holders: list[dict] = []
    for entry_point, d in sorted(details.items()):
        if not d:
            continue
        for pc in range(entry_point, d["body_max"] + 1, 4):
            if not image.contains(pc):
                break
            word = image.word(pc)
            if createflow.is_call(word):
                continue
            target = mips.jump_target(word, pc) if mips.is_j(word) else mips.branch_target(word, pc)
            if target is not None and target in map_starts and target not in live_list and target != entry_point:
                holders.append({"function": hx(entry_point), "at": hx(pc), "target": hx(target)})
    holder_entries = {int(h["function"], 16) for h in holders}
    blocked: dict[int, str] = {}
    jumps: dict[int, list[int]] = {}
    thunk_of: dict[int, int] = {}
    for address, size in sorted(candidates.items()):
        last = address + size - 1
        # A start in a gap of an existing body (between its entry and its end): batch 1 showed
        # that analysis then reworks the surrounding function.
        gap = [a for a, d in details.items() if d and a < address <= d["body_max"]]
        if gap:
            kind = "jump-neighbour" if gap[0] in holder_entries else "hole"
            blocked[address] = (f"{kind}: lies in a gap of the body of the function at {hx(gap[0])} "
                                f"(between its entry and its end {hx(details[gap[0]]['body_max'])})")
            continue
        if any(lo <= last and hi >= address for lo, hi in spans):
            # some body's range covers the extent; ask address by address (bodies may have holes)
            for pc in range(address + 4, address + size, 4):
                found = live_function(bridge, pc, assumed)
                if found:
                    blocked[address] = f"its extent overlaps the body of the function at {hx(found['entry'])}"
                    break
        for pc in range(address, address + size, 4):
            word = image.word(pc) if image.contains(pc) else 0
            if mips.is_jr(word) and word != mips.JR_RA:
                jumps[pc] = jump_targets(bridge, pc)
        # A body of one jump and a nop delay slot becomes a Ghidra thunk of the jump's target.
        first = image.word(address)
        if size == 8 and image.word(address + 4) == 0:
            if mips.is_j(first):
                thunk_of[address] = mips.jump_target(first, address)
            elif mips.is_unconditional_branch(first):
                thunk_of[address] = mips.branch_target(first, address)
    classes = createflow.classify(candidates, set(live_list), image.word, image.contains, noreturn, jumps, blocked)
    # Creates other creates flow or jump into are made before every other create, so that no
    # create's analysis meets a jump to a planned start that is no function yet.
    made_first = {a for c in classes.values() if c["safety"] == "ordered" for a in c["after"]}
    return classes, {"jump_holders": holders, "thunk_of": thunk_of, "first": made_first}


LABEL_CLASH = ("the prototype name {name} is already a label at this entry (Ghidra's analysis put it there): "
               "a function cannot take the name of a label at its own entry, so no rename is sent and the "
               "function keeps the analysis name {live}, which does not count against that name elsewhere")


def scan_entry_labels(bridge, items: list[tuple[int, str]], counts: Counter) -> dict[int, list[str]]:
    """The labels at each function entry ``(address, live name)``, read by address.

    ``get_function_labels`` finds the first function of a name, so it is used only for a name
    one function holds; otherwise ``get_function_documentation`` reads by address. Both are slow
    (they walk the symbol table or decompile), so three read-only clients share the work.
    """

    def read(client, address, name):
        if counts[name] == 1:
            found = read_labels(client, name)
        else:
            found = gb.parse_documentation_labels(
                client.get("get_function_documentation", gb.RELEASE_PROGRAM, address=hx(address)), address)
        return address, sorted(n for a, n in found if a == address)

    clients = bridge.clones(3)
    if len(clients) == 1:
        return dict(read(bridge, a, n) for a, n in items)
    chunks = [items[i::len(clients)] for i in range(len(clients))]
    with ThreadPoolExecutor(len(clients)) as pool:
        parts = pool.map(lambda pair: [read(pair[0], a, n) for a, n in pair[1]], zip(clients, chunks))
    return dict(item for part in parts for item in part)


def image_thunk_target(image, address: int) -> int | None:
    """The target of a thunk body ``j target`` / ``b target`` with a nop delay slot, else None."""

    if not (image.contains(address) and image.contains(address + 4)) or image.word(address + 4) != 0:
        return None
    word = image.word(address)
    if mips.is_j(word):
        return mips.jump_target(word, address)
    if mips.is_unconditional_branch(word):
        return mips.branch_target(word, address)
    return None


def withheld_group(reason: str) -> str:
    if reason.startswith("jump-neighbour"):
        return "jump-neighbour"
    if reason.startswith("hole"):
        return "hole"
    if "padding" in reason:
        return "padding"
    if "does not reach" in reason or "computed jump" in reason:
        return "unreachable"
    if "overlaps" in reason:
        return "overlap"
    if "falls through past" in reason or "flows to" in reason:
        return "flows into code that is no function"
    if "withheld create" in reason or "each other" in reason:
        return "depends on a withheld create"
    if "outside this plan" in reason:
        return "needs a create outside the plan"
    return "other"


def read_labels(bridge, function_name: str) -> list[tuple[int, str]]:
    return gb.parse_labels(bridge.get("get_function_labels", gb.RELEASE_PROGRAM, name=function_name, offset=0, limit=1000))


# --- the plan --------------------------------------------------------------------------------

# A library's functions keep their order from one build to the next, so a library pair that is
# not exact is named when it stands in the same place as in the prototype (user rule: the C
# standard library on 2026-11-26, every library on 2026-11-27).
C_PLACE = "library pair that is not exact, named by its place"


def _is_library(row: dict) -> bool:
    return row["prototype_classification"] == "provider" and bool(row["prototype_library"])


def library_place(rows: list[dict]) -> frozenset[int]:
    """Release addresses of the library pairs that stand in the same place as in the prototype.

    Per library, the pairs sorted by release address: the longest run of them whose prototype
    addresses rise too. A pair in it lies between the same neighbours in both executables.
    """

    placed: set[int] = set()
    libraries = sorted({r["prototype_library"] for r in rows
                        if r["prototype_classification"] == "provider" and r["prototype_library"]})
    for library in libraries:
        pairs = sorted((r["release_address"], r["prototype_address"]) for r in rows
                       if r["release_address"] is not None and r["prototype_address"] is not None
                       and r["prototype_classification"] == "provider" and r["prototype_library"] == library)
        tails: list[int] = []        # index into pairs of the last element of the best run of each length
        before: list[int | None] = []
        for index, (_, proto) in enumerate(pairs):
            lo, hi = 0, len(tails)
            while lo < hi:
                mid = (lo + hi) // 2
                if pairs[tails[mid]][1] < proto:
                    lo = mid + 1
                else:
                    hi = mid
            before.append(tails[lo - 1] if lo else None)
            if lo == len(tails):
                tails.append(index)
            else:
                tails[lo] = index
        at = tails[-1] if tails else None
        while at is not None:
            placed.add(pairs[at][0])
            at = before[at]
    return frozenset(placed)


def decide_name(row: dict, proto: dict | None, placed: frozenset | None = None) -> tuple[str | None, str | None, str]:
    """(name, label, reason): the prototype program's name and mangled label, or none and why.

    ``placed``: the result of ``library_place`` for the whole map; without it no library pair
    that is not exact is named.
    """

    if row["class"] == "new":
        return None, None, "new function: no name yet (proposed names are in the notes)"
    by_place = None
    if placed is not None and row["class"] != "exact" and _is_library(row):
        if row["release_address"] in placed:
            by_place = "it stands in the same place as in the prototype"
        elif row["class"] == "deviating" and "call" in row["evidence"]:
            by_place = "its place in the library differs, its callers decide it"
        elif row["class"] == "deviating" and "settled" in row["evidence"]:
            by_place = "its place in the library differs, a second agent's check settles it"
    if row["class"] == "unsure" and not by_place:
        return None, None, "unsure pair: the evidence does not settle it"
    if proto is None or is_default_name(proto["name"]):
        return None, None, "the prototype program has no name for its counterpart"
    if row["prototype_classification"] == "provider" and row["class"] != "exact" and not by_place:
        return None, None, "library pair that is not exact (libraries are named from exact pairs only)"
    for flag in row["flags"]:
        if flag in NAME_BLOCK:
            return None, None, NAME_BLOCK[flag]
    name = proto["name"]
    labels = [symbol for symbol in row["prototype_names"] if symbol and symbol != name]
    label = labels[0] if labels else None
    how = "the prototype program's name" + (" and its mangled label" if label else "")
    if "stubbed" in row["flags"]:
        how += "; stubbed: the same command-table entry, body emptied"
    if "identical-copy" in row["flags"]:
        how += "; identical-copy: equal bytes elsewhere, the copy was chosen by position"
    if by_place:
        how += f"; {C_PLACE} ({row['class']}): {by_place}"
    return name, label, how


def plate_text(row: dict, entry: dict, note: str | None) -> str:
    evidence = ",".join(row["evidence"]) or "-"
    flags = ",".join(row["flags"]) or "-"
    if row["class"] == "new":
        first = f"{PLATE_PREFIX}new, no prototype counterpart (evidence {evidence}; flags {flags})."
    else:
        first = (f"{PLATE_PREFIX}{row['class']} pair with prototype {hx(row['prototype_address'])} "
                 f"{row['prototype_symbol']} (evidence {evidence}; flags {flags}).")
    parts = [f"Owner {row['owner_file'] or '-'}"]
    if note:
        parts.append(f"settled: {note}")
    if entry.get("name") is None and row["class"] != "new" and entry.get("prototype"):
        parts.append(f"prototype name {entry['prototype']['name']} not applied: {entry['name_reason']}")
    if entry.get("name") and C_PLACE in (entry.get("name_reason") or ""):
        parts.append("named although the pair is not exact: " + entry["name_reason"].split(C_PLACE, 1)[1].split(": ", 1)[1])
    if entry.get("previous_name"):
        parts.append(f"{REPLACES}{entry['previous_name']}")
    live = entry.get("live") or {}
    if live.get("thunk"):
        parts.append(f"{THUNK_CLAUSE}{live.get('thunk_target') or 'an unknown target'}"
                     + ("" if entry.get("name") else ", shown under its target's name"))
    return first + "\n" + "; ".join(parts) + "."


# Plate clauses that describe the program as an earlier apply found it, or that a later step added.
REPLACES = "replaces the analysis name "
THUNK_CLAUSE = "Ghidra thunk of "
# Added by tools/release/signatures.py to the plate of a function whose pair is not exact.
SIGNATURE_CLAUSE = "signature carried from the prototype as a starting point (the pair is not exact)"
# Added by tools/release/signatures.py (group mangled) to every function whose signature it derived
# from the counterpart's mangled symbol; the clause goes on with the symbol and its evidence.
MANGLED_CLAUSE = "signature derived from the mangled symbol "


def plate_clauses(plate: str) -> tuple[str, list[str]]:
    """(first line, the clauses of the second line) of a plate written by plate_text."""

    first, _, rest = (plate or "").partition("\n")
    rest = rest[:-1] if rest.endswith(".") else rest
    return first, rest.split("; ") if rest else []


def join_plate(first: str, clauses: list[str]) -> str:
    return first + "\n" + "; ".join(clauses) + "."


def kept_plate(planned: str | None, recorded_value: str | None) -> str | None:
    """The plate the record holds, when a replan differs from it only where it cannot know better.

    A replan cannot see the analysis name an earlier apply replaced (the live name is the planned
    one now), and a function the tool created as a predicted thunk was planned before it was a
    thunk, so its plate lacks the thunk clause. A clause the signatures step added stays too (the
    deviating flag, and the clause of a signature derived from the mangled symbol). Any other
    difference gives the planned plate.
    """

    if not planned or not recorded_value or record_value(planned) == recorded_value:
        return planned
    recorded = recorded_value.replace(" // ", "\n")
    if record_value(recorded) != recorded_value or not recorded.startswith(PLATE_PREFIX):
        return planned
    first, mine = plate_clauses(planned)
    first_recorded, theirs = plate_clauses(recorded)
    if first != first_recorded:
        return planned
    only_planned = [c for c in mine if c not in theirs]
    only_recorded = [c for c in theirs if c not in mine]
    if all(c.startswith(THUNK_CLAUSE) for c in only_planned) \
            and all(c.startswith(REPLACES) or c == SIGNATURE_CLAUSE or c.startswith(MANGLED_CLAUSE)
                    for c in only_recorded) \
            and [c for c in mine if c in theirs] == [c for c in theirs if c in mine]:
        return recorded
    return planned


def select(rows: list[dict], module: str | None) -> list[dict]:
    chosen = [r for r in rows if r["release_address"] is not None]
    if module:
        chosen = [r for r in chosen if report.module_label(r) == module]
        if not chosen:
            known = sorted({report.module_label(r) for r in rows})
            raise Refused(f"no release function in module {module!r}; modules: {', '.join(known)}")
    return sorted(chosen, key=lambda r: r["release_address"])


def thunk_targets(live_list: dict) -> dict[int, int | None]:
    """Release thunk -> its target, read from the name a default thunk shows (FunctionSymbol.doGetName)."""

    out = {}
    for address, fn in live_list.items():
        if not fn["thunk"]:
            continue
        match = re.match(r"^thunk_FUN_([0-9a-f]{8})$", fn["name"])
        if match:
            out[address] = int(match.group(1), 16)
            continue
        same = [a for a, f in live_list.items() if f["name"] == fn["name"] and not f["thunk"]]
        out[address] = same[0] if len(same) == 1 else None
    return out


def thunk_shows_target(address: int, name: str | None, live_list: dict, targets: dict) -> bool:
    """True when the thunk's name is the one its DEFAULT symbol derives from its target."""

    target = targets.get(address)
    if target is None or name is None:
        return False
    shown = live_list.get(target, {}).get("name")
    return name in (shown, f"thunk_{shown}")


def global_names(rows, proto_list, live_list, keep: dict | None = None) -> tuple[dict, dict]:
    """Every planned name (whole map) and its collisions with each other and with live names.

    ``keep``: functions that keep their live name (address -> why), e.g. a label clash.
    """

    planned: dict[int, tuple] = {}
    placed = library_place(rows)
    for row in rows:
        if row["release_address"] is None:
            continue
        proto = proto_list.get(row["prototype_address"]) if row["prototype_address"] is not None else None
        planned[row["release_address"]] = decide_name(row, proto, placed)
    for address, why in (keep or {}).items():
        planned[address] = (None, None, why)
    # Default thunks show their target's name without holding it, in both programs.
    proto_targets = thunk_targets(proto_list)
    proto_count = Counter(f["name"] for a, f in proto_list.items()
                          if not (f["thunk"] and (is_default_name(f["name"])
                                                  or thunk_shows_target(a, f["name"], proto_list, proto_targets))))
    holders: dict[str, set] = defaultdict(set)
    for address, (name, _, _) in planned.items():
        if name:
            holders[name].add(address)
    targets = thunk_targets(live_list)
    for address, fn in live_list.items():
        name = fn["name"]
        if address in (keep or {}):
            continue  # it keeps an analysis name only because Ghidra refuses the planned one; its plate says so
        if address in targets and (is_default_name(name) or thunk_shows_target(address, name, live_list, targets)):
            # A default thunk shows its target's name (FunctionSymbol.doGetName) but holds no
            # symbol of that name: it is no second holder (0x27a650 shows 0x279ff0's name).
            continue
        if is_default_name(name) or name not in holders:
            continue
        if planned.get(address, (None,))[0] in (None, name):  # keeps this name after the apply
            holders[name].add(address)
    collisions = {}
    for name, addresses in holders.items():
        if len(addresses) > max(1, proto_count[name]):
            collisions[name] = {
                "name": name, "addresses": [hx(a) for a in sorted(addresses)], "prototype_count": proto_count[name],
                "live_holders": [hx(a) for a in sorted(addresses) if live_list.get(a, {}).get("name") == name],
                "resolution": "not applied to any of these functions: the release would hold the name more often "
                              "than the prototype program does",
            }
    return planned, collisions


def build_plan(root: Path, bridge, module: str | None, exclude: set[int] = frozenset(), progress=None,
               assumed: frozenset = frozenset(), image=None) -> dict:
    """``assumed``: release functions the plan treats as removed (the apply checks they are)."""

    check = preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    rows, settled, map_sha = load_map(root)
    recorded = read_record(root)
    settled_by_release = {s["release"]: s for s in settled if s["release"] is not None}
    index = notes_index(root)
    proto_list = function_list(bridge, gb.PROTOTYPE_PROGRAM)
    live_list = {a: f for a, f in function_list(bridge, gb.RELEASE_PROGRAM).items() if a not in assumed}
    chosen = select(rows, module)
    # A planned name that is already a label at the entry cannot be given (checkDuplicateSymbolName).
    items, wanted = [], {}
    placed = library_place(rows)
    for row in chosen:
        address = row["release_address"]
        if address not in live_list or row["prototype_address"] is None:
            continue
        name = decide_name(row, proto_list.get(row["prototype_address"]), placed)[0]
        if name and live_list[address]["name"] != name:
            items.append((address, live_list[address]["name"]))
            wanted[address] = name
    if progress:
        progress(f"labels at {len(items)} entries")
    at_entry = scan_entry_labels(bridge, items, Counter(f["name"] for f in live_list.values()))
    keep = {a: LABEL_CLASH.format(name=wanted[a], live=live_list[a]["name"])
            for a in sorted(wanted) if wanted[a] in at_entry.get(a, [])}
    planned, collisions = global_names(rows, proto_list, live_list, keep)
    targets = thunk_targets(live_list)
    starts = {r["release_address"] for r in rows if r["release_address"] is not None}
    image = image or elfimage.load(root / RELEASE_ELF, "release")
    for address, target in list(targets.items()):
        if target is None:  # a thunk that has its own name: read the jump itself
            targets[address] = image_thunk_target(image, address)
    creates, create_facts = plan_creates(rows, bridge, live_list, frozenset(assumed), image, exclude)
    selected = {r["release_address"] for r in chosen}

    entries = []
    for number, row in enumerate(chosen):
        if progress and number % 500 == 0:
            progress(f"{number}/{len(chosen)}")
        address, size = row["release_address"], row["release_size"]
        end = address + size - 1
        entry: dict = {
            "address": hx(address), "size": size, "end": hx(end), "class": row["class"],
            "module": report.module_label(row), "owner_file": row["owner_file"] or None,
            "evidence": row["evidence"], "flags": row["flags"],
            "library": (row["prototype_library"] or "?") if row["prototype_classification"] == "provider" else None,
            "source_pair": "new" if row["prototype_address"] is None
            else f"{hx(row['prototype_address'])} {row['prototype_symbol']} ({row['class']})",
            "prototype": None, "differences": [],
        }
        if row["prototype_address"] is not None:
            listed = proto_list.get(row["prototype_address"])
            detail = read_function(bridge, gb.PROTOTYPE_PROGRAM, row["prototype_address"]) if listed else None
            if detail and detail["entry"] != row["prototype_address"]:
                detail = None
            entry["prototype"] = None if not listed else {
                "address": hx(row["prototype_address"]), "symbol": row["prototype_symbol"], "name": listed["name"],
                "thunk": listed["thunk"], "noreturn": bool(detail and detail["noreturn"]),
            }

        live = live_function(bridge, address, frozenset(assumed))
        if live and live["entry"] == address:
            entry["live"] = {"name": live["name"], "body_max": hx(live["body_max"]),
                             "thunk": live_list.get(address, {}).get("thunk", False), "noreturn": live["noreturn"]}
            if entry["live"]["thunk"]:
                target = targets.get(address)
                entry["live"]["thunk_target"] = hx(target) if target is not None else None
                entry["live"]["default_thunk"] = (is_default_name(live["name"])
                                                  or thunk_shows_target(address, live["name"], live_list, targets))
            if live["body_max"] == end and live["body_min"] == address:
                entry["function"] = "exists"
            else:
                # The bridge reports a body's lowest and highest address only; a body below
                # its entry has more than one range (a branch target Ghidra pulled in).
                entry["function"] = "boundary"
                entry["boundary"] = {"ghidra_end": hx(live["body_max"]), "map_end": hx(end),
                                     "delta": live["body_max"] - end, "bytes": abs(live["body_max"] - end)}
                if live["body_min"] != address:
                    entry["boundary"]["ghidra_lowest"] = hx(live["body_min"])
        elif live:
            entry["live"] = {"inside": {"entry": hx(live["entry"]), "name": live["name"],
                                        "body_min": hx(live["body_min"]), "body_max": hx(live["body_max"])}}
            entry["function"] = "inside"
            entry["boundary"] = {"ghidra_function": hx(live["entry"]), "ghidra_lowest": hx(live["body_min"]),
                                 "ghidra_end": hx(live["body_max"]), "map_end": hx(end), "bytes": size}
        else:
            audit = bridge.get("audit_global", gb.RELEASE_PROGRAM, address=hx(address))
            code = isinstance(audit, dict) and bool(audit.get("is_code_address"))
            entry["live"] = {"code": code}
            entry["function"] = "create" if code else "no-instruction"
        if address in exclude:
            entry["function"] = "excluded"
        if entry["function"] == "create":
            info = dict(creates[address])
            outside = [a for a in info["after"] if a not in selected]
            if info["safety"] == "ordered" and outside:
                info = {"safety": "withheld", "after": [],
                        "reason": f"needs the create at {hx(outside[0])} first, which is outside this plan"}
            thunk_of = create_facts["thunk_of"].get(address)
            entry["create"] = {"safety": info["safety"], "after": [hx(a) for a in info["after"]],
                               "reason": info["reason"], "first": address in create_facts["first"],
                               "thunk_of": hx(thunk_of) if thunk_of is not None else None}
            if info["safety"] == "withheld":
                entry["function"] = "create-withheld"

        name, label, reason = planned[address]
        if name in collisions:
            name, label, reason = None, None, f"name collision: {name} ({collisions[name]['resolution']})"
        live_name = entry["live"].get("name")
        previous = None
        if entry["live"].get("thunk") and entry["live"].get("thunk_target") is None:
            name, label, reason = None, None, "Ghidra thunk whose target cannot be told from its name"
        if name and live_name and not is_default_name(live_name) and live_name != name \
                and not entry["live"].get("default_thunk"):
            if row["class"] == "exact":
                previous = live_name
            else:
                name, label, reason = None, None, f"Ghidra already names it {live_name} and the pair is not exact"
        entry.update({"name": name, "label": label, "name_reason": reason, "previous_name": previous,
                      "label_clash": address in keep})
        if entry["function"] in UNNAMED_ACTIONS:
            why = entry["create"]["reason"] if entry["function"] == "create-withheld" else ""
            entry.update({"name": None, "label": None, "plate": None,
                          "name_reason": f"not named: function {entry['function']}" + (f" ({why})" if why else "")})
        else:
            planned_plate = plate_text(row, entry, note_for(settled_by_release.get(address), address, index, root))
            entry["plate"] = kept_plate(planned_plate, recorded.get((hx(address), "plate"), {}).get("value"))
            replaced = [c for c in plate_clauses(entry["plate"])[1] if c.startswith(REPLACES)]
            if replaced and entry["name"] and not entry["previous_name"]:
                entry["previous_name"] = replaced[0][len(REPLACES):]  # replaced by an earlier apply (the record says so)
        proto, here = entry["prototype"], entry["live"]
        if proto and "thunk" in here and proto["thunk"] != here["thunk"]:
            entry["differences"].append(f"thunk: prototype {proto['thunk']}, release {here['thunk']}")
        if proto and "noreturn" in here and proto["noreturn"] != here["noreturn"]:
            entry["differences"].append(f"no-return: prototype {proto['noreturn']}, release {here['noreturn']}")
        entries.append(entry)

    spans = [(r["release_address"], r["release_address"] + r["release_size"]) for r in chosen]
    ghidra_only = []
    for address in sorted(a for a in live_list if a not in starts):
        if module is None or any(s <= address < e for s, e in spans):
            ghidra_only.append({"address": hx(address), "name": live_list[address]["name"],
                                "thunk": live_list[address]["thunk"]})
    chosen_addresses = {e["address"] for e in entries}
    plan = {
        "kind": PLAN_KIND, "schema_version": PLAN_SCHEMA, "program": gb.RELEASE_PROGRAM,
        "program_path": gb.RELEASE_PATH, "reference_program": gb.PROTOTYPE_PROGRAM,
        "release_sha256": RELEASE_SHA256, "prototype_sha256": PROTOTYPE_SHA256,
        "selection": module or "--all", "function_map_sha256": map_sha,
        "excluded": sorted(hx(a) for a in exclude), "assumed_removed": sorted(hx(a) for a in assumed),
        "entries": entries, "ghidra_only": ghidra_only,
        "jump_holders": [j for j in create_facts["jump_holders"]
                         if module is None or int(j["function"], 16) in selected or int(j["target"], 16) in selected],
        "collisions": sorted((c for c in collisions.values() if set(c["addresses"]) & chosen_addresses),
                             key=lambda c: c["name"]),
    }
    plan["summary"] = summarize(plan)
    plan["plan_sha256"] = sha256_text(canonical(plan))
    return plan


def summarize(plan: dict) -> dict:
    entries = plan["entries"]
    named = Counter(e["class"] for e in entries if e["name"])
    unnamed = Counter(e["class"] for e in entries if not e["name"])
    boundary = [e for e in entries if e["function"] in ("boundary", "inside")]
    largest = sorted(boundary, key=lambda e: (-e["boundary"]["bytes"], e["address"]))[:10]

    def group(e):
        if e["class"] == "new":
            return "new"
        return "library" if e.get("library") else "game and engine"

    return {
        "functions": len(entries),
        "function_actions": dict(sorted(Counter(e["function"] for e in entries).items())),
        "names_by_class": dict(sorted(named.items())),
        "names_by_class_and_group": dict(sorted(Counter(
            f"{e['class']} / {group(e)}" for e in entries if e["name"]).items())),
        "comment_only_by_class": dict(sorted(unnamed.items())),
        "labels": sum(1 for e in entries if e["label"]),
        "plates": sum(1 for e in entries if e["plate"]),
        "analysis_names_replaced": sum(1 for e in entries if e["previous_name"]),
        "name_reasons": dict(sorted(Counter(e["name_reason"] for e in entries if not e["name"]).items())),
        "creates": {
            "safe": sum(1 for e in entries if e.get("create", {}).get("safety") == "safe"),
            "ordered": sum(1 for e in entries if e.get("create", {}).get("safety") == "ordered"),
            "withheld": sum(1 for e in entries if e.get("create", {}).get("safety") == "withheld"),
            "withheld_bytes": sum(e["size"] for e in entries if e.get("create", {}).get("safety") == "withheld"),
            "withheld_reasons": dict(sorted(Counter(
                re.sub(r"0x[0-9a-f]+", "0x..", e["create"]["reason"]) for e in entries
                if e.get("create", {}).get("safety") == "withheld").items())),
            "withheld_by_group": dict(sorted(Counter(
                withheld_group(e["create"]["reason"]) for e in entries
                if e.get("create", {}).get("safety") == "withheld").items())),
            "made_first": sum(1 for e in entries if e.get("create", {}).get("first")),
            "thunks": sum(1 for e in entries if e.get("create", {}).get("thunk_of")
                          and e["create"]["safety"] != "withheld"),
            "predicted_follow_ups": 0,  # none are predicted: any change analysis makes stops the run
        },
        "renames_skipped_for_label": sum(1 for e in entries if e.get("label_clash")),
        "jump_holders": len(plan.get("jump_holders", [])),
        "boundary_differences": len(boundary),
        "largest_boundary_differences": [
            {"address": e["address"], "function": e["function"], **e["boundary"]} for e in largest],
        "differences": dict(sorted(Counter(d.split(":")[0] for e in entries for d in e["differences"]).items())),
        "collisions": len(plan["collisions"]),
        "ghidra_only": len(plan["ghidra_only"]),
    }


def plan_markdown(plan: dict) -> str:
    s = plan["summary"]
    lines = [f"# Names plan: {plan['selection']}", "",
             f"Program `{plan['program']}`; function map sha256 `{plan['function_map_sha256'][:16]}`; "
             f"plan sha256 `{plan['plan_sha256']}`.", "",
             f"- functions: {s['functions']}; actions: {s['function_actions']}",
             f"- names by class: {s['names_by_class']}; labels: {s['labels']}; plates: {s['plates']}",
             f"- comment only by class: {s['comment_only_by_class']}",
             f"- analysis names replaced: {s['analysis_names_replaced']}; renames skipped for a label at the "
             f"entry: {s['renames_skipped_for_label']}",
             f"- creates withheld by group: {s['creates']['withheld_by_group']}; made first: "
             f"{s['creates']['made_first']}; thunks: {s['creates']['thunks']}; predicted follow-ups: "
             f"{s['creates']['predicted_follow_ups']}",
             f"- existing functions jumping to a map start that is no function: {s['jump_holders']}",
             f"- collisions: {s['collisions']}; Ghidra-only functions: {s['ghidra_only']}",
             f"- thunk / no-return differences: {s['differences']}", "", "## Why a name is not applied", ""]
    lines += [f"- {count}: {reason}" for reason, count in s["name_reasons"].items()]
    lines += ["", "## Largest boundary differences (not fixed by this tool)", "",
              "| release | kind | Ghidra function | Ghidra lowest | Ghidra end | map end | bytes |",
              "|---|---|---|---|---|---|---|"]
    for b in s["largest_boundary_differences"]:
        lines.append(f"| {b['address']} | {b['function']} | {b.get('ghidra_function', b['address'])} | "
                     f"{b.get('ghidra_lowest', '-')} | {b['ghidra_end']} | {b['map_end']} | {b['bytes']} |")
    c = s["creates"]
    lines += ["", f"## Creates: {c['safe']} safe, {c['ordered']} after another create, {c['withheld']} withheld "
              f"({c['withheld_bytes']} bytes)", ""]
    lines += [f"- {e['address']} ({e['size']} bytes) after {', '.join(e['create']['after'])}"
              for e in plan["entries"] if e.get("create", {}).get("safety") == "ordered"]
    lines += [f"- withheld {e['address']} ({e['size']} bytes, {e['class']}): {e['create']['reason']}"
              for e in plan["entries"] if e.get("create", {}).get("safety") == "withheld"]
    unplaced = [e for e in plan["entries"] if e["function"] == "no-instruction"]
    if unplaced:
        lines += ["", f"## Starts without an instruction ({len(unplaced)}; need disassembly, not done)", ""]
        lines += [f"- {e['address']} ({e['size']} bytes, {e['class']})" for e in unplaced]
    replaced = [e for e in plan["entries"] if e["previous_name"]]
    if replaced:
        lines += ["", "## Analysis names replaced (exact pairs)", ""]
        lines += [f"- {e['address']}: {e['previous_name']} -> {e['name']}" for e in replaced]
    diffs = [e for e in plan["entries"] if e["differences"]]
    if diffs:
        lines += ["", "## Thunk and no-return differences (recorded, not applied)", ""]
        lines += [f"- {e['address']} {e['name'] or '-'}: {'; '.join(e['differences'])}" for e in diffs]
    if plan["collisions"]:
        lines += ["", "## Collisions", ""]
        lines += [f"- `{c['name']}` at {', '.join(c['addresses'])} (prototype holds it {c['prototype_count']}x)"
                  for c in plan["collisions"]]
    if plan.get("jump_holders"):
        lines += ["", "## Existing functions with a plain jump to a map start that is no function", ""]
        lines += [f"- {h['function']} at {h['at']} -> {h['target']}" for h in plan["jump_holders"]]
    clashes = [e for e in plan["entries"] if e.get("label_clash")]
    if clashes:
        lines += ["", "## Renames skipped: the name is a label at the entry", ""]
        lines += [f"- {e['address']}: {e['name_reason']}" for e in clashes]
    if plan["ghidra_only"]:
        lines += ["", "## Functions Ghidra has that the map does not", ""]
        lines += [f"- {g['address']} {g['name']}" + (" (thunk)" if g["thunk"] else "") for g in plan["ghidra_only"]]
    return "\n".join(lines) + "\n"


def write_plan(root: Path, plan: dict) -> Path:
    # A module label such as "(provider: newlib)" is no file name (a colon makes a stream on NTFS).
    stem = "plan-" + ("all" if plan["selection"] == "--all"
                      else re.sub(r"[^A-Za-z0-9._-]+", "-", plan["selection"]).strip("-"))
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{stem}.json").write_text(canonical(plan), encoding="utf-8", newline="\n")
    (out / f"{stem}.md").write_text(plan_markdown(plan), encoding="utf-8", newline="\n")
    return out / f"{stem}.json"




def current_map_sha(root: Path) -> str:
    return sha256_text((root / MAP_TSV).read_text(encoding="utf-8").replace("\r\n", "\n"))


def load_plan(path: Path, root: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("kind") != PLAN_KIND or plan.get("schema_version") != PLAN_SCHEMA:
        raise Refused(f"{path.name} is not a schema {PLAN_SCHEMA} names plan")
    if plan.get("program") != gb.RELEASE_PROGRAM:
        raise Refused(f"the plan targets {plan.get('program')!r}; writes go to {gb.RELEASE_PROGRAM} only")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if sha256_text(canonical(body)) != plan.get("plan_sha256"):
        raise Refused(f"{path.name} does not match its plan_sha256: regenerate it instead of editing it")
    if plan.get("function_map_sha256") != current_map_sha(root):
        raise Refused(f"{path.name} was made from another {MAP_TSV.as_posix()}: replan")
    return plan


# --- live snapshot ---------------------------------------------------------------------------

def snapshot(bridge) -> dict[int, dict]:
    """Every release function: name, thunk flag, body lowest and highest address, no-return."""

    out = {}
    for address, fn in function_list(bridge, gb.RELEASE_PROGRAM).items():
        detail = read_function(bridge, gb.RELEASE_PROGRAM, address)
        if not detail or detail["entry"] != address:
            raise gb.BridgeError(f"function {hx(address)} is listed but does not read back")
        out[address] = {"name": detail["name"], "thunk": fn["thunk"], "lo": detail["body_min"],
                        "hi": detail["body_max"], "noreturn": detail["noreturn"]}
    return out


def diff_snapshots(before: dict, after: dict, created: set, renamed: dict) -> list[dict]:
    """Every change between two snapshots that this run did not make itself."""

    def shown_by_default(address, state, other):
        # A DEFAULT thunk shows its target's name; it follows a rename of its target.
        targets = thunk_targets({a: {"name": f["name"], "thunk": f["thunk"]} for a, f in state.items()})
        return thunk_shows_target(address, other, {a: {"name": f["name"]} for a, f in state.items()}, targets)

    effects = []
    for address in sorted(set(before) | set(after)):
        old, new = before.get(address), after.get(address)
        if old is None:
            if address not in created:
                effects.append({"address": hx(address), "change": "appeared", "name": new["name"],
                                "body": f"{hx(new['lo'])}-{hx(new['hi'])}"})
            continue
        if new is None:
            effects.append({"address": hx(address), "change": "vanished", "name": old["name"]})
            continue
        for key in ("lo", "hi", "noreturn", "thunk"):
            if old[key] != new[key]:
                show = hx if key in ("lo", "hi") else str
                effects.append({"address": hx(address), "change": key, "before": show(old[key]),
                                "after": show(new[key])})
        if old["name"] != new["name"] and renamed.get(address) != new["name"]:
            if not (new["thunk"] and shown_by_default(address, after, new["name"])
                    and (is_default_name(old["name"]) or shown_by_default(address, before, old["name"]))):
                effects.append({"address": hx(address), "change": "name", "before": old["name"], "after": new["name"]})
    return effects


# --- the apply -------------------------------------------------------------------------------

def settle(bridge) -> None:
    """Wait until Ghidra's auto-analysis has been idle for QUIET_SECONDS without a break."""

    deadline = time.monotonic() + SETTLE_SECONDS
    quiet_since = None
    while True:
        status = bridge.get("analysis_status", gb.RELEASE_PROGRAM)
        now = time.monotonic()
        if isinstance(status, dict) and status.get("analyzing") is False:
            quiet_since = now if quiet_since is None else quiet_since
            if now - quiet_since >= QUIET_SECONDS:
                return
        else:
            quiet_since = None
        if now > deadline:
            raise Stop(f"analysis still running {SETTLE_SECONDS} s after a write")
        time.sleep(POLL_SECONDS)


class AnalysisStop(Stop):
    """Ghidra's analysis changed the program after a create beyond what the plan predicted."""


class Applier:
    def __init__(self, bridge, plan: dict, dry_run: bool, batch: int | None = None, recorded=frozenset()):
        self.bridge, self.plan, self.dry_run, self.batch = bridge, plan, dry_run, batch
        self.recorded = set(recorded)  # (address, applied) rows the record already holds
        self.attempted: list[dict] = []  # every write sent, as the record would hold it
        self.analysis_changes: list[dict] = []
        self.written: list[dict] = []  # read back correctly
        self.would: list[dict] = []  # dry run: writes that would be sent
        self.unchanged: Counter = Counter()
        self.skipped: list[dict] = []
        self.side_effects: list[dict] = []
        self.changed_entries = 0
        self.batch_full = False
        self.renamed: dict[int, str] = {}
        self.remove_by_hand: list[dict] = []  # functions a create made with the wrong extent

    # The names Ghidra shows, kept current through this run's renames (thunks follow targets).
    def show(self, address: int, name: str) -> None:
        old = self.display.get(address)
        if old is not None:
            self.counts[old] -= 1
        self.display[address] = name
        self.counts[name] += 1
        for thunk, target in self.targets.items():
            if target == address and thunk in self.default_thunks:
                default_target = is_default_name(name) and target not in self.targets
                self.show(thunk, f"thunk_{name}" if default_target else name)

    def send(self, entry: dict, applied: str, value: str, endpoint: str, ok, **body) -> bool:
        if self.dry_run:
            self.would.append({"address": entry["address"], "applied": applied, "value": value,
                               "source_pair": entry["source_pair"]})
            return False
        self.attempted.append({"address": entry["address"], "applied": applied, "value": value,
                               "source_pair": entry["source_pair"], "end": entry["end"]})
        response = self.bridge.write(endpoint, gb.RELEASE_PROGRAM, **body)
        if not ok(response):
            raise Stop(f"{endpoint} at {entry['address']} failed: {response!r}")
        return True

    def done(self, entry: dict, applied: str, value: str) -> None:
        self.written.append({"address": entry["address"], "applied": applied, "value": value,
                             "source_pair": entry["source_pair"], "end": entry["end"]})

    def settle(self) -> None:
        settle(self.bridge)

    def run(self) -> None:
        self.before = snapshot(self.bridge)
        listed = {a: {"name": f["name"], "thunk": f["thunk"]} for a, f in self.before.items()}
        self.targets = {a: t for a, t in thunk_targets(listed).items() if t is not None}
        for e in self.plan["entries"]:  # targets the plan read from the jump itself
            if e.get("live", {}).get("thunk_target"):
                self.targets.setdefault(int(e["address"], 16), int(e["live"]["thunk_target"], 16))
        self.default_thunks = {a for a in self.targets
                               if is_default_name(listed[a]["name"]) or thunk_shows_target(a, listed[a]["name"], listed, self.targets)}
        self.display = {a: f["name"] for a, f in self.before.items()}
        self.counts = Counter(self.display.values())
        self.listed = set(self.before)
        self.state = {a: dict(f) for a, f in self.before.items()}
        self.by_address = {e["address"]: e for e in self.plan["entries"]}
        self.processed: set[str] = set()
        ordered = sorted(self.plan["entries"], key=lambda e: int(e["address"], 16))
        # Creates other creates flow into come first, then everything in address order.
        ordered = [e for e in ordered if e.get("create", {}).get("first")] + \
                  [e for e in ordered if not e.get("create", {}).get("first")]
        try:
            for entry in ordered:
                if entry["function"] in UNNAMED_ACTIONS:
                    self.skipped.append({"address": entry["address"], "reason": entry["name_reason"]})
                    continue
                if entry["address"] in self.processed:
                    continue
                if self.batch and self.changed_entries >= self.batch:
                    self.batch_full = True
                    break
                self.process(entry, ())
        finally:
            if not self.dry_run and (self.written or self.bridge.sent):
                try:
                    self.settle()
                except Stop as exc:
                    self.side_effects.append({"change": "analysis did not settle", "detail": str(exc)})
                after = snapshot(self.bridge)
                created = {int(w["address"], 16) for w in self.written if w["applied"] == "create"}
                self.side_effects += diff_snapshots(self.before, after, created, self.renamed)

    def process(self, entry: dict, chain: tuple) -> None:
        """One entry, after the creates its flow falls or jumps into (descending runs come out first)."""

        for before in entry.get("create", {}).get("after", []):
            if before in chain:
                raise Stop(f"create order loops through {before}: replan")
            needed = self.by_address.get(before)
            if needed is None or needed["function"] != "create":
                raise Stop(f"{entry['address']} needs the create at {before}, which the plan does not make")
            if before not in self.processed:
                self.process(needed, chain + (entry["address"],))
        self.processed.add(entry["address"])
        if self.entry(entry):
            self.changed_entries += 1

    def labels_at(self, address: int, name: str) -> list[tuple[int, str]]:
        """Labels of the function at ``address``: by its name when unique, otherwise by address."""

        if self.counts[name] == 1:
            return read_labels(self.bridge, name)  # get_function_labels takes the first function of the name
        return gb.parse_documentation_labels(
            self.bridge.get("get_function_documentation", gb.RELEASE_PROGRAM, address=hx(address)), address)

    def entry(self, entry: dict) -> bool:
        address, end = int(entry["address"], 16), int(entry["end"], 16)
        writes = len(self.would) + len(self.bridge.sent)
        live = read_function(self.bridge, gb.RELEASE_PROGRAM, address)
        if live and live["entry"] != address:
            raise Stop(f"{entry['address']} now lies inside the function at {hx(live['entry'])}: replan")
        if live:
            seen = entry["live"].get("name")
            # A dry run changes nothing, so the live program still shows the names it started with.
            expected = self.before[address]["name"] if self.dry_run and address in self.before else self.display.get(address)
            allowed = (live["name"] in (entry["name"], seen) or is_default_name(live["name"])
                       or (address in self.default_thunks and live["name"] == expected))
            if live["name"] != expected or not allowed:
                raise Stop(f"{entry['address']} is named {live['name']!r} now, expected {expected!r} "
                           f"(the plan saw {seen!r}): replan")
        simulated = False
        if entry["function"] == "create":
            if live:
                if live["body_max"] != end or live["body_min"] != address:
                    raise Stop(f"{entry['address']}: a function exists with body {hx(live['body_min'])}.."
                               f"{hx(live['body_max'])}, the plan creates one ending at {entry['end']}")
                if {(entry["address"], "create"), (entry["address"], "create-by-analysis")} & self.recorded:
                    self.unchanged["create"] += 1
                else:  # Ghidra's analysis made it, with the map's extent
                    self.done(entry, "create-by-analysis", f"{entry['address']}-{entry['end']}")
                    self.recorded.add((entry["address"], "create-by-analysis"))
            else:
                audit = self.bridge.get("audit_global", gb.RELEASE_PROGRAM, address=entry["address"])
                if not (isinstance(audit, dict) and audit.get("is_code_address")):
                    raise Stop(f"{entry['address']}: no instruction at the start any more: replan")
                if entry.get("create", {}).get("safety") not in ("safe", "ordered"):
                    raise Stop(f"{entry['address']}: the plan gives this create no safety class: replan")
                for before in entry["create"]["after"]:
                    if not self.dry_run:
                        there = read_function(self.bridge, gb.RELEASE_PROGRAM, int(before, 16))
                        if not there or there["entry"] != int(before, 16):
                            raise Stop(f"{entry['address']} would flow into {before}, which is no function yet")
                if self.send(entry, "create", f"{entry['address']}-{entry['end']}", "create_function",
                             gb.ok_create, address=entry["address"], disassemble_first=False):
                    self.settle()
                    back = read_function(self.bridge, gb.RELEASE_PROGRAM, address)
                    if not back or back["entry"] != address or back["body_max"] != end or back["body_min"] != address:
                        got = "nothing" if not back else f"{hx(back['body_min'])}..{hx(back['body_max'])}"
                        if back and back["entry"] == address:
                            self.remove_by_hand.append({"address": entry["address"], "name": back["name"],
                                                        "body": got, "planned": f"{entry['address']}..{entry['end']}"})
                            raise Stop(f"create {entry['address']} read back {got}, expected {entry['address']}.."
                                       f"{entry['end']}: remove the function {back['name']} at {entry['address']} "
                                       "by hand in Ghidra, then save and --confirm-saved this report (or close "
                                       "without saving and --discard-unsaved it), then replan")
                        raise Stop(f"create {entry['address']} read back {got}, expected {entry['address']}..{entry['end']}")
                    self.done(entry, "create", f"{entry['address']}-{entry['end']}")
                    self.after_create(entry, back)
                    live = back
                else:
                    live = {"entry": address, "name": "FUN_%08x" % address, "body_max": end}
                    simulated = True
                    self.show(address, self.expected_display(entry, live["name"]))
                    live["name"] = self.display[address]
        elif not live:
            raise Stop(f"{entry['address']}: the planned function is gone: replan")
        plate = entry["plate"]
        current = "" if simulated else read_plate(self.bridge, address)
        if current == plate and (not entry["name"] or live["name"] == entry["name"]) \
                and address not in self.default_thunks:
            self.unchanged["entry"] += 1  # the plate is written last, so the entry is complete
            return False
        if entry["name"]:
            simulated |= self.rename(entry, live)
        if entry["label"]:
            self.label(entry, simulated)
        if current == plate:
            self.unchanged["plate"] += 1
        elif current and not current.startswith(PLATE_PREFIX):
            self.skipped.append({"address": entry["address"], "reason": "a plate comment not written by this tool"})
        elif self.send(entry, "plate", plate, "set_comment", gb.ok_status,
                       address=entry["address"], comment=plate, type="plate"):
            back = read_plate(self.bridge, address)
            if back != plate:
                raise Stop(f"plate {entry['address']} read back {back!r}")
            self.done(entry, "plate", plate)
        return len(self.would) + len(self.bridge.sent) > writes

    def expected_display(self, entry: dict, default: str) -> str:
        """The name a new function shows: a predicted thunk shows its target's (FunctionSymbol.doGetName)."""

        thunk_of = entry.get("create", {}).get("thunk_of")
        if not thunk_of:
            return default
        address, target = int(entry["address"], 16), int(thunk_of, 16)
        self.targets[address] = target
        self.default_thunks.add(address)
        shown = self.display.get(target, "FUN_%08x" % target)
        return f"thunk_{shown}" if is_default_name(shown) and target not in self.targets else shown

    def after_create(self, entry: dict, back: dict) -> None:
        """Stop on anything Ghidra's analysis changed after this create that the plan did not predict."""

        address = int(entry["address"], 16)
        now = function_list(self.bridge, gb.RELEASE_PROGRAM)
        changes: list[dict] = []
        for other in sorted(set(now) - set(self.state) - {address}):
            changes.append({"address": hx(other), "change": "appeared", "name": now[other]["name"]})
        for other in sorted(set(self.state) - set(now)):
            changes.append({"address": hx(other), "change": "vanished", "name": self.state[other]["name"]})
        thunk = bool(entry.get("create", {}).get("thunk_of"))
        if address in now and now[address]["thunk"] != thunk:
            changes.append({"address": entry["address"], "change": "thunk", "predicted": thunk,
                            "after": now[address]["thunk"]})
        shown = self.expected_display(entry, "FUN_%08x" % address)
        if back["name"] != shown:
            changes.append({"address": entry["address"], "change": "named by analysis", "name": back["name"],
                            "predicted": shown})
        self.state[address] = {"name": back["name"], "thunk": now.get(address, {}).get("thunk", thunk),
                               "lo": back["body_min"], "hi": back["body_max"], "noreturn": back["noreturn"]}
        self.show(address, back["name"])
        for other, fn in now.items():
            if other == address or other not in self.state:
                continue
            if fn["thunk"] != self.state[other]["thunk"]:
                changes.append({"address": hx(other), "change": "thunk", "before": self.state[other]["thunk"],
                                "after": fn["thunk"]})
            if fn["name"] != self.display.get(other):
                changes.append({"address": hx(other), "change": "name", "before": self.display.get(other),
                                "after": fn["name"]})
        near = [a for a, f in self.state.items() if a != address
                and (abs(a - address) <= NEAR_BYTES or f["lo"] <= address <= f["hi"])]
        for other in sorted(near):
            d = read_function(self.bridge, gb.RELEASE_PROGRAM, other)
            if not d or d["entry"] != other:
                continue  # already reported as vanished
            old = self.state[other]
            for key, value in (("lo", d["body_min"]), ("hi", d["body_max"]), ("noreturn", d["noreturn"])):
                if old[key] != value:
                    show = hx if key in ("lo", "hi") else str
                    changes.append({"address": hx(other), "change": key, "before": show(old[key]),
                                    "after": show(value)})
        if changes:
            self.analysis_changes = [dict(c, after_create=entry["address"]) for c in changes]
            raise AnalysisStop(
                f"Ghidra's analysis changed the program after the create at {entry['address']} "
                f"({len(changes)} changes, listed in the report under analysis_changes): nothing has to be "
                "removed by hand; have the batch checked, save, --confirm-saved this report, then replan")

    def rename(self, entry: dict, live: dict) -> bool:
        """Rename first: ``create_label`` would rename a DEFAULT-named function instead of labelling it."""

        address, name = int(entry["address"], 16), entry["name"]
        if live["name"] == name and address not in self.default_thunks:
            self.unchanged["name"] += 1
            return False
        if self.send(entry, "name", name, "rename_function_by_address", gb.ok_status,
                     function_address=entry["address"], new_name=name, strict_mode="off"):
            back = read_function(self.bridge, gb.RELEASE_PROGRAM, address)
            if not back or back["entry"] != address or back["name"] != name:
                raise Stop(f"rename {entry['address']} read back {back and back['name']!r}, expected {name!r}")
            self.done(entry, "name", name)
            self.renamed[address] = name
            self.default_thunks.discard(address)
            self.show(address, name)
            return False
        self.default_thunks.discard(address)
        self.show(address, name)
        return True  # dry run: the live program still shows the old name

    def label(self, entry: dict, simulated: bool) -> None:
        address, label = int(entry["address"], 16), entry["label"]
        name = self.display[address]
        if not simulated and (address, label) in self.labels_at(address, name):
            self.unchanged["label"] += 1
            return
        if self.send(entry, "label", label, "create_label", gb.ok_status, address=entry["address"], name=label):
            back = read_function(self.bridge, gb.RELEASE_PROGRAM, address)
            if not back or back["name"] != name:
                raise Stop(f"create_label at {entry['address']} changed the function name to {back and back['name']!r}")
            if (address, label) not in self.labels_at(address, name):
                raise Stop(f"label {label} at {entry['address']} did not read back")
            self.done(entry, "label", label)


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
            rows[(row["release_address"], row["applied"])] = row
    return rows


def write_record(root: Path, rows: dict[tuple, dict]) -> None:
    order = {"create": 0, "create-by-analysis": 0, "name": 1, "label": 2, "plate": 3, "prototype": 4}
    text = "\t".join(RECORD_COLUMNS) + "\n" + "".join(
        "\t".join(rows[k][c] for c in RECORD_COLUMNS) + "\n"
        for k in sorted(rows, key=lambda k: (int(k[0], 16), order.get(k[1], 9))))
    (root / RECORD).write_text(text, encoding="utf-8", newline="\n")


def record_value(value: str) -> str:
    return value.replace("\t", " ").replace("\n", " // ")


def unsaved(rows: dict) -> list[dict]:
    return [row for row in rows.values() if row["state"].startswith("unsaved")]


def update_record(root: Path, written: list[dict], today: str, report_name: str) -> None:
    rows = read_record(root)
    for item in written:
        rows[(item["address"], item["applied"])] = {
            "release_address": item["address"], "applied": item["applied"], "value": record_value(item["value"]),
            "source_pair": item["source_pair"], "date": today, "state": f"unsaved {report_name}"}
    write_record(root, rows)


def reads_back(bridge, item: dict) -> bool:
    address = int(item["address"], 16)
    live = read_function(bridge, gb.RELEASE_PROGRAM, address)
    if not live or live["entry"] != address:
        return False
    if item["applied"] in ("create", "create-by-analysis"):
        return live["body_min"] == address and live["body_max"] == int(item["end"], 16)
    if item["applied"] == "name":
        return live["name"] == item["value"]
    if item["applied"] == "label":
        labels = gb.parse_documentation_labels(
            bridge.get("get_function_documentation", gb.RELEASE_PROGRAM, address=item["address"]), address)
        return (address, item["value"]) in labels
    return read_plate(bridge, address) == item["value"]


def confirm_saved(root: Path, report_path: Path, bridge, today: str | None = None, reads_back=None) -> dict:
    """After the coordinator saved: re-read every change of the report and mark its rows saved.

    ``reads_back(bridge, item)``: the read-back of another step's rows (signatures.py).
    """

    reads_back = reads_back or globals()["reads_back"]
    result = json.loads(report_path.read_text(encoding="utf-8"))
    still = [item for item in result.get("remove_by_hand", [])
             if (f := read_function(bridge, gb.RELEASE_PROGRAM, int(item["address"], 16)))
             and f["entry"] == int(item["address"], 16)]
    if still:
        raise Refused(f"the function {still[0]['name']} at {still[0]['address']} ({still[0]['body']}) that the "
                      "report says to remove by hand is still there: remove it, save, then confirm")
    rows = read_record(root)
    mine = [k for k, row in rows.items() if row["state"] == f"unsaved {report_path.name}"]
    written = {(item["address"], item["applied"]) for item in result["written"]}
    # Writes sent whose read-back stopped the run: those the saved program holds are recorded too.
    late = [item for item in result.get("attempted", []) if (item["address"], item["applied"]) not in written
            and reads_back(bridge, item)]
    if not mine and not late:
        raise Refused(f"the record holds no unsaved rows of {report_path.name}")
    failed = [f"{item['address']} {item['applied']}" for item in result["written"] if not reads_back(bridge, item)]
    if failed:
        raise Refused(f"{len(failed)} changes do not read back ({', '.join(failed[:10])}); nothing marked saved")
    day = today or _dt.date.today().isoformat()
    for key in mine:
        rows[key]["state"] = f"saved {day}"
    for item in late:
        rows[(item["address"], item["applied"])] = {
            "release_address": item["address"], "applied": item["applied"], "value": record_value(item["value"]),
            "source_pair": item["source_pair"], "date": day, "state": f"saved {day}"}
    write_record(root, rows)
    return {"confirmed": len(mine), "recorded_after_a_stop": len(late), "report": report_path.name}


def discard_unsaved(root: Path, report_path: Path, bridge, reads_back=None) -> dict:
    """After the program was closed without saving: drop the report's unsaved rows."""

    reads_back = reads_back or globals()["reads_back"]
    result = json.loads(report_path.read_text(encoding="utf-8"))
    present = [f"{item['address']} {item['applied']}" for item in result["written"] if reads_back(bridge, item)]
    if present:
        raise Refused(f"{len(present)} changes of {report_path.name} are still in the program "
                      f"({', '.join(present[:10])}): save and --confirm-saved instead")
    rows = read_record(root)
    kept = {k: r for k, r in rows.items() if r["state"] != f"unsaved {report_path.name}"}
    write_record(root, kept)
    return {"discarded": len(rows) - len(kept), "report": report_path.name}


def next_report(root: Path, stem: str) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    used = [int(m.group(1)) for p in out.glob(f"{stem}.apply-*.json")
            if (m := re.search(r"\.apply-(\d+)\.json$", p.name))]
    return out / f"{stem}.apply-{max(used, default=0) + 1:03d}.json"


def apply(root: Path, plan_path: Path, bridge, *, dry_run: bool, today: str | None = None,
          batch: int | None = None) -> dict:
    plan = load_plan(plan_path, root)
    if not dry_run:
        pending = unsaved(read_record(root))
        if pending:
            reports = sorted({row["state"].split(" ", 1)[1] for row in pending})
            raise Refused(f"{RECORD.as_posix()} holds {len(pending)} unsaved changes ({', '.join(reports)}): "
                          "save and --confirm-saved (or --discard-unsaved) first")
    check = preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    out = (root / OUT / f"{plan_path.stem}.dry-run.json") if dry_run else next_report(root, plan_path.stem)
    for address in plan.get("assumed_removed", []):
        there = read_function(bridge, gb.RELEASE_PROGRAM, int(address, 16))
        if there and there["entry"] == int(address, 16):
            raise Refused(f"the plan assumes the function at {address} was removed, but it is still there")
    applier = Applier(bridge, plan, dry_run, batch, recorded=set(read_record(root)))
    stopped = None
    try:
        applier.run()
    except (Stop, gb.BridgeError) as exc:
        stopped = str(exc)
    finally:
        if not dry_run and applier.written:
            update_record(root, applier.written, today or _dt.date.today().isoformat(), out.name)
    result = {
        "plan": plan_path.name, "plan_sha256": plan["plan_sha256"], "selection": plan["selection"],
        "dry_run": dry_run, "stopped": stopped, "saved": False, "batch": batch,
        "batch_full": applier.batch_full, "entries_changed": applier.changed_entries,
        "sent": [] if dry_run else bridge.sent, "written": applier.written, "would_write": applier.would,
        "counts": dict(sorted(Counter(w["applied"] for w in (applier.would if dry_run else applier.written)).items())),
        "unchanged": dict(sorted(applier.unchanged.items())), "skipped": applier.skipped,
        "side_effects": applier.side_effects, "remove_by_hand": applier.remove_by_hand,
        "analysis_changes": applier.analysis_changes, "attempted": [] if dry_run else applier.attempted,
        "boundary_differences": plan["summary"]["boundary_differences"], "collisions": plan["summary"]["collisions"],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical(result), encoding="utf-8", newline="\n")
    result["report"] = out.name
    return result


# --- command line ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", nargs="?", const="", metavar="MODULE",
                      help="plan one module of the map (e.g. gamez/zArchive), or every function with --all")
    mode.add_argument("--apply", type=Path, metavar="PLAN")
    mode.add_argument("--confirm-saved", type=Path, metavar="REPORT",
                      help="after the coordinator saved: re-read the report's changes and mark them saved")
    mode.add_argument("--discard-unsaved", type=Path, metavar="REPORT",
                      help="after closing without a save: drop the report's unsaved rows")
    parser.add_argument("--all", action="store_true", help="with --plan: every release function")
    parser.add_argument("--exclude", action="append", default=[], metavar="0xADDR",
                        help="with --plan: leave this release function out (repeatable)")
    parser.add_argument("--assume-removed", action="append", default=[], metavar="0xADDR",
                        help="with --plan: plan as if the release function at this entry had been removed "
                             "(the apply refuses until it is)")
    parser.add_argument("--dry-run", action="store_true", help="with --apply: reads and checks only")
    parser.add_argument("--yes", action="store_true", help="with --apply: really write")
    parser.add_argument("--batch", type=int, metavar="N", help="with --apply: stop after N changed functions")
    parser.add_argument("--url", help="bridge URL (default SOCOM_GHIDRA_URL or http://127.0.0.1:8089)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.plan is not None:
            if bool(args.plan) == args.all:
                parser.error("--plan takes either a module or --all")
            exclude = {int(a, 16) for a in args.exclude}
            plan = build_plan(root, gb.Bridge(args.url, read_only=True), args.plan or None, exclude,
                              progress=lambda m: print(m, file=sys.stderr),
                              assumed=frozenset(int(a, 16) for a in args.assume_removed))
            path = write_plan(root, plan)
            print(json.dumps(plan["summary"], indent=1))
            print(f"wrote {path.relative_to(root).as_posix()} (plan sha256 {plan['plan_sha256']})")
            return 0
        if args.all or args.exclude or args.assume_removed:
            parser.error("--all, --exclude and --assume-removed go with --plan")
        if args.confirm_saved or args.discard_unsaved:
            bridge = gb.Bridge(args.url, read_only=True)
            check = preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            done = (confirm_saved(root, args.confirm_saved.resolve(), bridge) if args.confirm_saved
                    else discard_unsaved(root, args.discard_unsaved.resolve(), bridge))
            print(json.dumps(done))
            return 0
        if not args.dry_run and not args.yes:
            print("refused: --apply writes to the release program; pass --yes (or --dry-run)", file=sys.stderr)
            return 2
        if args.dry_run and args.yes:
            parser.error("--dry-run and --yes exclude each other")
        bridge = gb.Bridge(args.url, read_only=args.dry_run)
        result = apply(root, args.apply.resolve(), bridge, dry_run=args.dry_run, batch=args.batch)
        print(json.dumps({k: result[k] for k in ("report", "dry_run", "stopped", "counts", "unchanged", "saved",
                                                 "batch_full", "entries_changed")}, indent=1))
        print(f"sent: {len(result['sent'])}; skipped: {len(result['skipped'])}; side effects: "
              f"{len(result['side_effects'])}; boundary differences: {result['boundary_differences']}; "
              f"collisions: {result['collisions']}")
        for item in result["remove_by_hand"]:
            print(f"REMOVE BY HAND in Ghidra: the function {item['name']} at {item['address']} "
                  f"(body {item['body']}, planned {item['planned']})")
        if result["batch_full"]:
            print("batch complete: save through the bridge, then --confirm-saved the report, then rerun")
        if result["analysis_changes"]:
            print(f"ANALYSIS STOP: {len(result['analysis_changes'])} changes after a create, listed in the report; "
                  "nothing to remove by hand: check, save, --confirm-saved, replan")
        return 1 if result["stopped"] or result["side_effects"] else 0
    except (Refused, gb.BridgeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
