"""Stage 3, references: add the references from code to globals that Ghidra's analysis dropped.

    python tools/release/references.py --plan gamez/zCamera          # or --plan --all
    python tools/release/references.py --apply build/release/references/plan-gamez-zCamera.json --dry-run
    python tools/release/references.py --apply build/release/references/plan-all.json --yes [--batch N] [--only 0x..] [--check-every N]
    python tools/release/references.py --confirm-saved build/release/references/plan-all.apply-001.json
    python tools/release/references.py --discard-unsaved build/release/references/plan-all.apply-001.json

``--plan`` reads the release ELF, the function map, the data map and, read-only, the release
program; it writes ``build/release/references/plan-<module>.json`` and a summary ``.md``,
deterministic, with its own digest. Nothing is written to Ghidra. ``--apply`` adds the planned
references to ``SCUS_971.34`` only, one ``add_memory_reference`` per reference, and never saves.

Why references are missing (``docs/release/notes/stage3-globals.md``): the analyzer
(``SymbolicPropogator.makeReference``) drops a non-flow reference whose target no memory block
holds, and the block ``.bss`` (0x48d200..0x5d6cff) was added after analysis; for many functions
the analyzer also had no value of gp yet. The value of gp (0x494670) is now in the program
context, which makes the decompiler resolve gp offsets but creates no reference.

What the bridge does (GhidraMCP 6.0.0 ``XrefCallGraphService.addMemoryReference``, Ghidra 12.1.4
``ReferenceDBManager``, read from the classes):

* ``add_memory_reference`` (POST: ``from_address``, ``to_address``, ``ref_type`` a ``RefType``
  field name, default DATA; ``source_type`` USER_DEFINED by default, or ANALYSIS, IMPORTED,
  DEFAULT; ``operand_index``, default -1 the mnemonic) runs, in one transaction,
  ``ReferenceManager.addMemoryReference(from, to, type, source, operand)``: for a memory target it
  first deletes the stack and register references on that operand (``removeNonMemRefs``); a
  reference with the same from, to and operand is not duplicated: when the combined type is the
  old one nothing changes, otherwise the old one is replaced, keeping its primary flag
  (``combineReferenceType``: READ and WRITE give READ_WRITE, a flow type wins); a new reference is
  primary when the operand has none yet. Then ``REFERENCE_ADDED``; no symbol, data or code unit is
  made at the target (a ``DAT_`` name there is dynamic, not stored), and auto-analysis listens to
  no reference event (``AutoAnalysisManager``: function, code and flow events only), so nothing
  runs. Success: ``status success`` with from, to, ``ref_type``, ``source_type``,
  ``operand_index`` and ``is_primary`` (only ``is_primary`` is read from the stored reference; the
  type, source and operand are echoed from the request); failure: ``{"error": ...}``. There is no undo
  endpoint, but each write is its own transaction, so Edit > Undo in the Ghidra window can take back
  the last ones; the route this tool names stays closing without saving. ``remove_reference`` deletes
  every reference from-to whatever its source (never sent here).
* Once referenced, an address with no symbol shows a dynamic name: ``DAT_<address>`` (or the item's
  default label) at a data item's start or in no item; inside an item ``<item>+<offset>``,
  ``<item>.<field>`` or ``<item>[i]`` (``SymbolUtilities.getDynamicDataName``). The decompiler then
  shows that name where it showed a raw ``uRam..`` (``DecompileCallback.lookupSymbol``).
* ``get_xrefs_from`` lists the target and type of every reference from an address, not its
  operand, source or primary flag: no read endpoint shows those.

What the analyzer makes, measured on the prototype (``socom.elf``; every gp, ``lui`` pair and
register-offset use ``dataflow.py`` derives in the 9,705 function bodies, against every reference
Ghidra holds there), and the kinds this tool takes from it:

* load and store through gp (``lw t, n(gp)``): READ or WRITE to gp+n on operand 1
  (``addLoadStoreReference``): 7,224 of 7,224 agree; through a ``lui`` high half with the low half
  in the instruction: 6,640 of 6,640 (the right half ``lwr``/``ldr`` of an unaligned pair too; the
  left half ``lwl``/``ldl``/``swl``/``sdl`` never gets one). Every one has its relocation.
* address computations (``addiu r, gp, n``; ``lui``/``addiu``): 15,223 get a reference on that
  instruction (DATA or PARAM, the analyzer's ``makeVariableStorageReference`` at the instruction
  that last set the argument register), 1,457 on the store that stores the address instead, the
  rest none. This tool makes DATA on operand 0, the destination register the analyzer's
  ``findOpIndexForRef`` matches (PARAM is not made: the analyzer deletes PARAM references of any
  source when it revisits an instruction); an address that a store of the function stores, where
  that store already has the reference, is ``covered``. 35 address computations have no
  relocation: 17 ``lui``/``ori`` pairs (all constants: masks, magic numbers) and 6 ``addiu r, gp, 0``
  are withheld, and so is a pair equal to gp; the other 12 are linker-defined addresses (section
  bounds). Split by the target's block (the review ``socom-release-refs-review-r6``): into the
  uninitialised block the analyzer put DATA on the computation whatever the use (bases 719 of 719,
  other uses 5,533 of 5,537, stored 118 of 120, gp 254 of 254); into the initialised block it marks a
  base on the accesses through it, a stored address on the store, and other uses with PARAM on the
  computation (gp: 420 of 426). So address computations are made into the uninitialised block, and
  into the initialised block only through gp, for another use, as the function's one reference to
  that target (the release analyzer lacked gp there); a ``lui`` pair into the initialised block is
  what the release analyzer chose not to mark, and is withheld.
* register-offset accesses (``lw t, k(r)`` with r an address): the analyzer marks 1,070 of 2,716 and
  base plus offset lies outside the base's symbol in a third: withheld. Indexed accesses (an unknown
  register added) have no fixed target: not planned. Not derivable at all: references through
  pointers the analyzer read from initialized memory, and values stored as addresses that no
  address computation of the function builds.
* On the release the same derivation agrees with all 877 gp references the program holds.

Source type: ``ANALYSIS`` by default (what the analyzer would have made; the prototype's and the
release's are ANALYSIS), ``USER_DEFINED`` with ``--source-type``. Re-analysis removes neither
(memory references of every source stay; a matching analysis reference only combines the type);
the Clear dialog's "analysis references" and "user-defined references" boxes pick them apart.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as _dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import dataflow  # noqa: E402
import datapair  # noqa: E402
import elfimage  # noqa: E402
import ghidra_bridge as gb  # noqa: E402
import globals as gl  # noqa: E402
import mips  # noqa: E402
import names  # noqa: E402
import report  # noqa: E402
import signatures as sg  # noqa: E402
from names import Refused, Stop, canonical, hx, sha256_text  # noqa: E402

OUT = Path("build/release/references")
PLAN_KIND = "socom-release-references-plan"
PLAN_SCHEMA = 2  # 2: the initialised block's address computations withheld; offcut target names
REFERENCE = "reference"  # the record's kind
CHECK_EVERY = 250  # writes between two snapshots
SOURCE_TYPES = ("ANALYSIS", "USER_DEFINED")
# kind -> (ref_type, operand_index)
MADE = {"gp-load": ("READ", 1), "gp-store": ("WRITE", 1), "gp-address": ("DATA", 0),
        "pair-load": ("READ", 1), "pair-store": ("WRITE", 1), "pair-address": ("DATA", 0)}
WITHHELD_KINDS = {"field-load", "field-store"}
LEFT_HALVES = {0x22: "lwl", 0x2A: "swl", 0x1A: "ldl", 0x2C: "sdl"}
REGS = ("zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
        "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra")
_INSTRUCTION = re.compile(r"^([0-9a-fA-F]+): (.*?)\s*(?:; .*)?$")
_REF = re.compile(r"^To (\S+?)(?: to (?:function|data) .*?)? \[(\w+)\]$")

FIELD_REASON = ("a register-offset access: withheld (the prototype's analysis marks 1,070 of 2,716 and base plus "
                "offset lies outside the base's symbol in a third)")
ORI_REASON = "a lui/ori pair: a constant, not an address (all 17 in the prototype are constants)"
GP0_REASON = "the value of gp itself (addiu r, gp, 0, or a lui pair equal to gp): a base, not an object"
OTHER_REASON = "the instruction has other references ({}): their operand cannot be read through the bridge"
# Address computations into the initialised block (the analyzer had it and needed no gp for lui pairs):
# the prototype's analysis marks a base on its accesses, a stored address on the store, and puts PARAM
# on the computation only for other uses (gp: 420 of 426); into the uninitialised block it put DATA on
# the computation whatever the use, as this tool does.
INIT_PAIR_REASON = ("a lui/addiu pair into the initialised block: the analyzer had the block and the pair and "
                    "chose not to mark it")
INIT_BASE_REASON = ("a gp address into the initialised block used as a base: the analyzer marks the accesses "
                    "through it, not the computation")
INIT_STORED_REASON = ("a gp address into the initialised block that the function stores: the analyzer marks the "
                      "store, not the computation")
INIT_SECOND_REASON = ("a gp address into the initialised block that the function already references from {}: it "
                      "would be a second reference")

UNDO = (" Each reference is its own transaction, so Edit > Undo in the Ghidra window can take back the last ones; "
        "the route this tool names stays closing without saving and --discard-unsaved.")
AFTER_NOTHING = gl.AFTER_NOTHING
AFTER_A_WRITE = gl.AFTER_A_WRITE + "." + UNDO
AFTER_ANALYSIS = gl.AFTER_ANALYSIS + "." + UNDO
WHAT_TO_DO = {"StopBefore": AFTER_NOTHING, "StopAfter": AFTER_A_WRITE, "AnalysisStop": AFTER_ANALYSIS,
              "Stop": AFTER_A_WRITE, "BridgeError": AFTER_A_WRITE}
_REF_TO = re.compile(r"^From (\S+?)(?: in .*?)? \[(\w+)\]$")


# --- live reads --------------------------------------------------------------------------------

def refs_from(bridge, address: int) -> list[tuple[str, str]]:
    """Every reference from an address as (target, type), sorted; a target that is no plain
    address (a stack or register reference) is kept as Ghidra prints it."""

    text = bridge.get("get_xrefs_from", gb.RELEASE_PROGRAM, address=hx(address), offset=0, limit=1000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"get_xrefs_from {hx(address)}: {str(text)[:200]}")
    if text.startswith("No references"):
        return []
    out = []
    for line in text.splitlines():
        match = _REF.match(line.strip())
        if not match:
            raise gb.BridgeError(f"get_xrefs_from {hx(address)}: cannot read {line!r}")
        target = match.group(1)
        out.append((hx(int(target, 16)) if re.fullmatch(r"[0-9a-fA-F]+", target) else target, match.group(2)))
    return sorted(out)


def refs_to(bridge, address: int) -> list[tuple[str, str]]:
    """Every reference to an address as (from, type), sorted."""

    text = bridge.get("get_xrefs_to", gb.RELEASE_PROGRAM, address=hx(address), offset=0, limit=1000000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"get_xrefs_to {hx(address)}: {str(text)[:200]}")
    if text.startswith("No references"):
        return []
    out = []
    for line in text.splitlines():
        match = _REF_TO.match(line.strip())
        if not match:
            raise gb.BridgeError(f"get_xrefs_to {hx(address)}: cannot read {line!r}")
        source = match.group(1)
        out.append((hx(int(source, 16)) if re.fullmatch(r"[0-9a-fA-F]+", source) else source, match.group(2)))
    return sorted(out)


def instructions(bridge, entry: int) -> dict[int, str]:
    """Ghidra's instructions from a function's entry to its body's end, by address."""

    text = bridge.get("disassemble_function", gb.RELEASE_PROGRAM, address=hx(entry))
    if not isinstance(text, str):
        raise gb.BridgeError(f"disassemble_function {hx(entry)}: {str(text)[:200]}")
    out = {}
    for line in text.splitlines():
        if match := _INSTRUCTION.match(line.strip()):
            out[int(match.group(1), 16)] = match.group(2)
    return out


def target_state(bridge, address: int) -> dict:
    state = gl.audit(bridge, gb.RELEASE_PROGRAM, address)
    return {"address": hx(address), "name": state.get("name") or "", "type": state.get("type") or "", "length": state.get("length") or 0,
            "xref_count": state.get("xref_count"), "code": bool(state.get("is_code_address")),
            "entry": bool(state.get("is_function_entry"))}


def read_functions(bridge, entries) -> dict[int, dict]:
    """entry -> name, body lowest and highest, signature line, no-return (``get_function_by_address``)."""

    def read(client, entry):
        found = names.read_function(client, gb.RELEASE_PROGRAM, entry)
        if not found or found["entry"] != entry:
            raise gb.BridgeError(f"function {hx(entry)} is listed but does not read back")
        return {"name": found["name"], "lo": found["body_min"], "hi": found["body_max"],
                "signature": found.get("signature", ""), "noreturn": found["noreturn"]}

    return gl.parallel(bridge, sorted(entries), read)


# --- the derivation -----------------------------------------------------------------------------

def release_gp(image, words, entry_size: int) -> int:
    gp = datapair.gp_of(image, words, entry_size)
    if gp is None:
        raise Refused("the value of gp cannot be derived from the release entry function")
    return gp


def kind_of(ref, words, base: int, lo: int) -> str:
    if ref.gp:
        return "gp-" + ("address" if ref.kind == "addr" else ref.kind)
    if ref.off is None:
        return "indexed-" + ref.kind  # an unknown register added: no fixed target
    first = words[(lo - base) // 4 + ref.defs[0]] if ref.defs else 0
    if ref.kind == "addr" or (len(ref.defs) == 1 and (first >> 26) == 0x0F):
        return "pair-" + ("address" if ref.kind == "addr" else ref.kind)
    return "field-" + ref.kind


def stored_addresses(words, start: int, count: int, base: int, gp: int) -> dict[int, list[int]]:
    """def index of an address computation -> the indices of the stores that store that address."""

    states = dataflow._flow(words, start, count, base, gp)
    out: dict[int, list[int]] = defaultdict(list)
    for local in range(count):
        word = words[start + local]
        state = states[local]
        if (word >> 26) in dataflow.STORES and state:
            value = state.get((word >> 16) & 0x1F)
            if value is not None and value[0] == "addr" and value[3] == 0 and value[2]:
                out[value[2][-1]].append(local)
    return out


def derive(image, words, gp: int, entry: int, body: dict, insns: dict[int, str]) -> list[dict]:
    """Every use of a data address in one function body that has a fixed target."""

    lo, hi = body["lo"] & ~3, body["hi"]
    start, count = (lo - image.base) // 4, (hi + 1 - lo) // 4
    if lo < image.base or start + count > len(words) or count <= 0:
        return []
    stores = stored_addresses(words, start, count, image.base, gp)
    found = dataflow.references(words, start, count, image.base, gp)
    bases = {d for ref in found if ref.kind != "addr" for d in ref.defs}
    out = []
    for ref in found:
        at = lo + 4 * ref.index
        if at not in insns:
            continue  # bytes Ghidra does not hold as an instruction of this function
        kind = kind_of(ref, words, image.base, lo)
        word = words[start + ref.index]
        use = {"from": at, "kind": kind, "opcode": word >> 26, "word": word,
               "evidence": [[hx(lo + 4 * d), insns.get(lo + 4 * d, "%08x" % words[start + d])] for d in ref.defs
                            if lo + 4 * d != at] + [[hx(at), insns[at]]],
               "target": None if ref.off is None else ref.address + ref.off,
               "stores": [lo + 4 * s for s in stores.get(ref.index, [])] if ref.kind == "addr" else [],
               "base": ref.kind == "addr" and ref.index in bases}
        out.append(use)
    return out


# --- inputs --------------------------------------------------------------------------------------

class MapIndex:
    """The data map's release rows by start: the object holding an address and the offset in it."""

    def __init__(self, rows):
        self.rows = sorted(((int(r["release_address"], 16), r) for r in rows if r["release_address"] not in ("-", "")),
                           key=lambda x: (x[0], x[1]["prototype_address"]))
        self.starts = [a for a, _ in self.rows]

    def containing(self, address: int) -> dict | None:
        k = bisect.bisect_right(self.starts, address) - 1
        while k >= 0:
            start, row = self.rows[k]
            size = row["release_size"]
            top = int(size.split("..")[-1]) if size not in ("-", "") else 1
            if address < start + max(top, 1):
                return {"release": hx(start), "symbol": row["prototype_symbol"], "class": row["class"],
                        "offset": address - start, "size": size}
            if k and self.rows[k - 1][0] == start:
                k -= 1
                continue
            return None
        return None


def block_of(segments, address: int) -> str | None:
    return next((name for lo, hi, name in segments if lo <= address <= hi), None)


def select_functions(root: Path, live: dict[int, dict], module: str | None) -> tuple[list[int], str]:
    rows, _, map_sha = names.load_map(root)
    if not module:
        return sorted(live), map_sha
    chosen = {r["release_address"] for r in names.select(rows, module)}
    return sorted(a for a in live if a in chosen), map_sha


# --- the plan ------------------------------------------------------------------------------------

def build_plan(root: Path, bridge, module: str | None, image=None, source_type: str = "ANALYSIS",
               progress=None) -> dict:
    say = progress or (lambda message: None)
    if source_type not in SOURCE_TYPES:
        raise Refused(f"--source-type is one of {SOURCE_TYPES}")
    image = image or elfimage.load(root / names.RELEASE_ELF, "release")
    words = mips.words_of(image.data)
    say("reading the release program")
    segments = gl.read_segments(bridge, gb.RELEASE_PROGRAM)
    listed = names.function_list(bridge, gb.RELEASE_PROGRAM)
    chosen, map_sha = select_functions(root, listed, module)
    data_rows, data_sha = gl.load_data_map(root)
    maps = MapIndex(data_rows)
    entry_body = read_functions(bridge, [image.entry]) if image.entry in listed else {}
    gp = release_gp(image, words, entry_body[image.entry]["hi"] + 1 - image.entry if entry_body else 448)
    say(f"{len(chosen)} functions: bodies and instructions")
    bodies = read_functions(bridge, chosen)
    insns = gl.parallel(bridge, chosen, lambda c, a: instructions(c, a))
    uses: dict[int, dict] = {}
    for entry in chosen:
        for use in derive(image, words, gp, entry, bodies[entry], insns[entry]):
            uses.setdefault(use["from"], dict(use, function=entry))
    # disassemble_function lists every instruction up to the body's end, a gap's too: the function
    # holding the instruction (getFunctionContaining) decides, and an instruction in no body is left out
    holders = gl.parallel(bridge, sorted(uses), lambda c, a: names.read_function(c, gb.RELEASE_PROGRAM, a))
    in_gap = Counter()
    for at in sorted(uses):
        found = holders[at]
        if found is None or found["entry"] not in bodies:
            in_gap["in no function body" if found is None else "in a function of another selection"] += 1
            del uses[at]
        else:
            uses[at]["function"] = found["entry"]
    fixed = [u for u in uses.values() if u["target"] is not None]
    say(f"{len(uses)} uses, {len(fixed)} with a fixed target: references from them")
    had = gl.parallel(bridge, sorted(u["from"] for u in fixed), lambda c, a: refs_from(c, a))
    store_refs = gl.parallel(bridge, sorted({s for u in fixed for s in u["stores"]} - set(had)),
                             lambda c, a: refs_from(c, a))
    store_refs.update(had)
    targets = sorted({u["target"] for u in fixed if block_of(segments, u["target"])})
    say(f"{len(targets)} targets in memory: their state")
    states = gl.parallel(bridge, targets, lambda c, a: target_state(c, a))
    in_code = [t for t in targets if block_of(segments, t) == block_of(segments, image.entry)]
    holder = gl.parallel(bridge, in_code, lambda c, a: names.read_function(c, gb.RELEASE_PROGRAM, a))
    data = gl.DataIndex(gl.read_data(bridge, gb.RELEASE_PROGRAM))
    labels = gl.read_labels(bridge, gb.RELEASE_PROGRAM)
    init_block = block_of(segments, image.entry)
    entries, unfixed = [], Counter()
    for use in sorted(uses.values(), key=lambda u: u["from"]):
        if use["target"] is None:
            unfixed[use["kind"]] += 1
            continue
        entries.append(decide(use, had[use["from"]], store_refs, segments, states, holder, data, labels, maps,
                              bodies, source_type, gp, init_block))
    second_references(bridge, entries, bodies, init_block)
    plan = {
        "kind": PLAN_KIND, "schema_version": PLAN_SCHEMA, "program": gb.RELEASE_PROGRAM,
        "selection": module or "--all", "function_map_sha256": map_sha, "data_map_sha256": data_sha,
        "gp": hx(gp), "source_type": source_type,
        "segments": [[hx(lo), hx(hi), name] for lo, hi, name in segments],
        "functions": {hx(a): bodies[a] for a in chosen},
        "entries": entries, "no_fixed_target": dict(sorted(unfixed.items())),
        "left_out": dict(sorted(in_gap.items())),
    }
    plan["summary"] = summarize(plan)
    plan["plan_sha256"] = sha256_text(canonical(plan))
    return plan


def decide(use, had, store_refs, segments, states, holder, data, labels, maps, bodies, source_type, gp,
           init_block) -> dict:
    at, target, kind = use["from"], use["target"], use["kind"]
    fn = bodies[use["function"]]
    entry = {"from": hx(at), "to": hx(target), "kind": kind, "function": hx(use["function"]),
             "function_name": fn["name"], "evidence": use["evidence"], "had": [list(r) for r in had],
             "state": "withheld", "reason": None, "ref_type": None, "operand": None, "source_type": None}
    if kind.endswith("address"):
        # how the function uses the address: the analyzer marks the address computation itself when
        # the value goes to a call or is returned, the store when it is stored, the accesses through
        # it when it is a base (which this tool withholds)
        entry["feeds"] = sorted((["accesses through it"] if use["base"] else []) + (["a store"] if use["stores"] else []))
    block = block_of(segments, target)
    here = data.containing(target) if block else None
    entry["target"] = {"block": block, "labels": labels.get(target, []),
                       "state": states.get(target),
                       "data": [hx(here[0]), here[1], here[2], target - here[0]] if here else None,
                       "map": maps.containing(target)}
    if here and target > here[0]:
        # an address inside a data item: once referenced, its dynamic name derives from the item's
        entry["target"]["item_labels"] = labels.get(here[0], [])
    if any(t == hx(target) for t, _ in had):
        entry["state"] = "present"
        return entry
    covered = [s for s in use["stores"] if any(t == hx(target) for t, _ in store_refs.get(s, []))]
    if covered:
        entry["state"], entry["reason"] = "covered", f"the store at {hx(covered[0])} has the reference"
        return entry
    op = use["opcode"]
    state = states.get(target) or {}
    found = holder.get(target)
    reason = None
    if kind in WITHHELD_KINDS:
        reason = FIELD_REASON
    elif op in LEFT_HALVES:
        reason = f"the left half of an unaligned pair ({LEFT_HALVES[op]}): the analyzer marks only the right half"
    elif kind == "pair-address" and op == 0x0D:
        reason = ORI_REASON
    elif (kind == "gp-address" and (use["word"] & 0xFFFF) == 0) or (kind == "pair-address" and target == gp):
        reason = GP0_REASON
    elif block is None:
        reason = f"outside every memory block ({hx(target)})"
    elif kind.endswith("address") and (state.get("code") or found) and not state.get("entry"):
        where = f"{found['name']} at {hx(found['entry'])}" if found else "an instruction"
        reason = f"points into code that is not a function entry ({where})"
    elif not kind.endswith("address") and (state.get("code") or found):
        reason = "reads or writes code"
    elif had:
        reason = OTHER_REASON.format(", ".join(f"{t} {k}" for t, k in had))
    elif kind == "pair-address" and block == init_block:
        reason = INIT_PAIR_REASON
    elif kind == "gp-address" and block == init_block and use["base"]:
        reason = INIT_BASE_REASON
    elif kind == "gp-address" and block == init_block and use["stores"]:
        reason = INIT_STORED_REASON
    if reason:
        entry["reason"] = reason
        return entry
    ref_type, operand = MADE[kind]
    entry.update(state="planned", ref_type=ref_type, operand=operand, source_type=source_type)
    return entry


def second_references(bridge, entries, bodies, init_block) -> None:
    """A gp address into the initialised block is made only as the function's one reference to its target."""

    chosen = [e for e in entries if e["state"] == "planned" and e["kind"] == "gp-address"
              and e["target"]["block"] == init_block]
    if not chosen:
        return
    # Only references the program holds count: planned ones stand where analysis with gp would have
    # marked them too (it marks every such site).
    to = gl.parallel(bridge, sorted({int(e["to"], 16) for e in chosen}), lambda c, a: refs_to(c, a))
    for e in chosen:
        fn = bodies[int(e["function"], 16)]
        others = sorted({f for f, _ in to[int(e["to"], 16)] if f.startswith("0x") and f != e["from"]
                         and fn["lo"] <= int(f, 16) <= fn["hi"]})
        if others:
            e.update(state="withheld", reason=INIT_SECOND_REASON.format(", ".join(others)), ref_type=None,
                     operand=None, source_type=None)


def reason_group(reason: str) -> str:
    for prefix, group in (("a register-offset", "register-offset access"), ("the left half", "unaligned left half"),
                          ("a lui/ori", "lui/ori constant"), ("the value of gp", "gp itself"),
                          ("outside every memory block", "outside every memory block"),
                          ("points into code", "points into code"), ("reads or writes code", "reads or writes code"),
                          ("the instruction has other", "other references on the instruction"),
                          ("a lui/addiu pair into the initialised", "initialised block: pair address"),
                          ("a gp address into the initialised block used", "initialised block: gp address, a base"),
                          ("a gp address into the initialised block that the function stores",
                           "initialised block: gp address, stored"),
                          ("a gp address into the initialised block that the function already",
                           "initialised block: gp address, a second reference")):
        if reason.startswith(prefix):
            return group
    return "other"


def summarize(plan: dict) -> dict:
    entries = plan["entries"]
    planned = [e for e in entries if e["state"] == "planned"]
    return {
        "functions": len(plan["functions"]), "uses_with_a_fixed_target": len(entries),
        "uses_without_a_fixed_target": plan["no_fixed_target"],
        "uses_left_out": plan["left_out"],
        "planned": len(planned),
        "planned_by_kind": dict(sorted(Counter(e["kind"] for e in planned).items())),
        "planned_by_block": dict(sorted(Counter(e["target"]["block"] for e in planned).items())),
        "planned_by_kind_and_block": dict(sorted(Counter(f"{e['kind']} {e['target']['block']}"
                                                         for e in planned).items())),
        "planned_by_type": dict(sorted(Counter(f"{e['ref_type']} operand {e['operand']}" for e in planned).items())),
        "planned_targets": len({e["to"] for e in planned}),
        "planned_addresses_by_use": dict(sorted(Counter(", ".join(e["feeds"]) or "other (a call, a return, arithmetic)"
                                                        for e in planned if "feeds" in e).items())),
        "planned_targets_without_a_name": len({e["to"] for e in planned if not e["target"]["labels"]}),
        "present": dict(sorted(Counter(e["kind"] for e in entries if e["state"] == "present").items())),
        "covered_at_a_store": sum(1 for e in entries if e["state"] == "covered"),
        "withheld": dict(sorted(Counter(reason_group(e["reason"]) for e in entries
                                        if e["state"] == "withheld").items())),
        "withheld_by_kind": dict(sorted(Counter(e["kind"] for e in entries if e["state"] == "withheld").items())),
    }


def plan_markdown(plan: dict) -> str:
    s = plan["summary"]
    lines = [f"# References plan: {plan['selection']}", "",
             f"Plan sha256 `{plan['plan_sha256']}`; gp {plan['gp']}; source type {plan['source_type']}.", "",
             f"- functions: {s['functions']}; uses with a fixed target: {s['uses_with_a_fixed_target']}; "
             f"without one (an unknown index): {s['uses_without_a_fixed_target']}; left out (the instruction is in no "
             f"function body of the selection): {s['uses_left_out']}",
             f"- planned: {s['planned']} to {s['planned_targets']} addresses "
             f"({s['planned_targets_without_a_name']} without a stored label)",
             f"- already present: {s['present']}; covered by a reference at the store: {s['covered_at_a_store']}",
             f"- planned address computations by what the function does with the address: "
             f"{s['planned_addresses_by_use']}", "",
             "## Planned by kind and block", "", "| Kind | Block | References |", "|---|---|---|"]
    for key, count in s["planned_by_kind_and_block"].items():
        kind, block = key.split(" ", 1)
        lines.append(f"| {kind} | {block} | {count} |")
    lines += ["", f"Types: {s['planned_by_type']}", "", "## Withheld", "", "| Reason | Uses |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in s["withheld"].items()]
    lines += ["", f"By kind: {s['withheld_by_kind']}", ""]
    odd = [e for e in plan["entries"] if e["state"] == "withheld" and
           reason_group(e["reason"]) in ("points into code", "reads or writes code", "other references on the instruction")]
    if odd:
        lines += ["## Withheld one by one", "", "| From | To | Kind | Reason |", "|---|---|---|---|"]
        lines += [f"| {e['from']} | {e['to']} | {e['kind']} | {e['reason']} |" for e in odd]
        lines.append("")
    return "\n".join(lines) + "\n"


def plan_stem(selection: str) -> str:
    return gl.plan_stem(selection)


def write_plan(root: Path, plan: dict) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    stem = plan_stem(plan["selection"])
    (out / f"{stem}.json").write_text(canonical(plan), encoding="utf-8", newline="\n")
    (out / f"{stem}.md").write_text(plan_markdown(plan), encoding="utf-8", newline="\n")
    return out / f"{stem}.json"


def load_plan(path: Path, root: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("kind") != PLAN_KIND or plan.get("schema_version") != PLAN_SCHEMA:
        raise Refused(f"{path.name} is not a schema {PLAN_SCHEMA} references plan")
    if plan.get("program") != gb.RELEASE_PROGRAM:
        raise Refused(f"the plan targets {plan.get('program')!r}; writes go to {gb.RELEASE_PROGRAM} only")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if sha256_text(canonical(body)) != plan.get("plan_sha256"):
        raise Refused(f"{path.name} does not match its plan_sha256: regenerate it instead of editing it")
    if plan.get("function_map_sha256") != names.current_map_sha(root):
        raise Refused(f"{path.name} was made from another {names.MAP_TSV.as_posix()}: replan")
    return plan


# --- the apply -----------------------------------------------------------------------------------

def snapshot(bridge) -> dict:
    """What analysis could change: every function (name, thunk, body, signature, no-return), every
    defined data item, every stored label, every bookmark."""

    listed = names.function_list(bridge, gb.RELEASE_PROGRAM)
    detail = read_functions(bridge, listed)
    return {"functions": {a: dict(detail[a], thunk=f["thunk"]) for a, f in listed.items()},
            "data": set(gl.read_data(bridge, gb.RELEASE_PROGRAM)),
            "labels": {a: set(v) for a, v in gl.read_labels(bridge, gb.RELEASE_PROGRAM).items()},
            "bookmarks": set(gl.sg_bookmarks(bridge))}


def ok_answer(answer, entry) -> bool:
    """The plugin echoes ``ref_type``, ``source_type`` and ``operand_index`` from the request (and from
    and to as parsed); only ``is_primary`` is read from the stored reference. So the answer proves the
    request was taken and the new reference is primary on some operand, not its operand or source."""

    if not isinstance(answer, dict) or answer.get("status") != "success":
        return False
    try:
        same = (int(str(answer.get("from_address")), 16), int(str(answer.get("to_address")), 16)) == \
            (int(entry["from"], 16), int(entry["to"], 16))
    except ValueError:
        return False
    return same and answer.get("ref_type") == entry["ref_type"] and answer.get("source_type") == entry["source_type"] \
        and answer.get("operand_index") == entry["operand"] and answer.get("is_primary") is True


def record_value(entry: dict) -> str:
    return f"to {entry['to']} {entry['ref_type']} operand {entry['operand']} {entry['source_type']} ({entry['kind']})"


class Applier:
    def __init__(self, bridge, plan: dict, dry_run: bool, batch: int | None = None, only=frozenset(),
                 check_every: int = CHECK_EVERY):
        self.bridge, self.plan, self.dry_run = bridge, plan, dry_run
        self.batch, self.only, self.check_every = batch, set(only), max(1, check_every)
        self.written: list[dict] = []
        self.attempted: list[dict] = []
        self.would: list[dict] = []
        self.unchanged = 0
        self.analysis_changes: list[dict] = []
        self.after_stop: list[dict] = []
        self.checks = 0
        self.batch_full = False
        self.targets: dict[str, dict] = {}  # target -> the state expected now
        self.expected_from: dict[str, list] = {}  # planned instruction met in this run -> its references
        self.expected_to: dict[str, list] = {}  # written target -> the references to it

    def run(self) -> None:
        entries = [e for e in self.plan["entries"] if e["state"] == "planned"]
        if self.only:
            unknown = sorted(self.only - {e["from"] for e in entries})
            if unknown:
                raise sg.StopBefore(f"--only {unknown[0]}: not a planned reference of the plan")
            entries = [e for e in entries if e["from"] in self.only]
        if not self.dry_run:
            self.before = snapshot(self.bridge)
        since = 0
        try:
            for entry in entries:
                if self.batch and len(self.written) + len(self.would) >= self.batch:
                    self.batch_full = True
                    break
                if self.entry(entry) and not self.dry_run:
                    since += 1
                    status = self.bridge.get("analysis_status", gb.RELEASE_PROGRAM)
                    if since >= self.check_every or not (isinstance(status, dict) and status.get("analyzing") is False):
                        self.check(f"after {entry['from']}")
                        since = 0
        except Stop:
            if not self.dry_run and self.bridge.sent and not self.analysis_changes:
                try:
                    self.after_stop = self.differences()
                except (Stop, gb.BridgeError) as exc:
                    self.after_stop = [{"error": str(exc)}]
            raise
        if not self.dry_run and self.bridge.sent:
            self.check("at the end")

    def check(self, when: str) -> None:
        changes = self.differences()
        if changes:
            self.analysis_changes = [dict(c, seen=when) for c in changes]
            raise sg.AnalysisStop(f"the program differs from the prediction {when} ({len(changes)} differences, "
                                  f"listed under analysis_changes): {AFTER_ANALYSIS}")

    def differences(self) -> list[dict]:
        names.settle(self.bridge)
        now = snapshot(self.bridge)
        self.checks += 1
        changes = []
        for a in sorted(set(now["functions"]) | set(self.before["functions"])):
            if now["functions"].get(a) != self.before["functions"].get(a):
                changes.append({"function": hx(a), "before": self.before["functions"].get(a),
                                "after": now["functions"].get(a)})
        for d in sorted(now["data"] ^ self.before["data"]):
            changes.append({"data": [hx(d[0]), d[1], d[2]], "change": "added" if d in now["data"] else "missing"})
        for a in sorted(set(now["labels"]) | set(self.before["labels"])):
            got, want = now["labels"].get(a, set()), self.before["labels"].get(a, set())
            if got != want:
                changes.append({"labels": hx(a), "added": sorted(got - want), "missing": sorted(want - got)})
        for b in sorted(now["bookmarks"] ^ self.before["bookmarks"]):
            changes.append({"bookmark": [hx(b[0]), b[1], b[2], b[3]],
                            "change": "added" if b in now["bookmarks"] else "removed"})
        for target, want in sorted(self.targets.items()):
            got = target_state(self.bridge, int(target, 16))
            if not same_target(got, want):
                changes.append({"target": target, "expected": want, "now": got})
        for source, want in sorted(self.expected_from.items()):
            got = refs_from(self.bridge, int(source, 16))
            if got != want:
                changes.append({"references_from": source, "expected": want, "now": got})
        for target, want in sorted(self.expected_to.items()):
            got = refs_to(self.bridge, int(target, 16))
            if got != want:
                changes.append({"references_to": target, "expected": want, "now": got})
        return changes

    def entry(self, entry: dict) -> bool:
        at, to = int(entry["from"], 16), int(entry["to"], 16)
        planned = (entry["to"], entry["ref_type"])
        had = sorted(tuple(r) for r in entry["had"])
        live = refs_from(self.bridge, at)
        if live == sorted(had + [planned]):
            self.unchanged += 1
            self.expected_from[entry["from"]] = live
            return False
        if live != had:
            raise sg.StopBefore(f"{entry['from']}: the references from it are {live} now, the plan saw {had}: "
                                f"{AFTER_NOTHING}")
        fn = self.plan["functions"][entry["function"]]
        found = names.read_function(self.bridge, gb.RELEASE_PROGRAM, at)
        if not found or (hx(found["entry"]), found["body_min"], found["body_max"]) != (entry["function"], fn["lo"], fn["hi"]):
            raise sg.StopBefore(f"{entry['from']}: the function holding it is not {entry['function']} with the planned "
                                f"body now: {AFTER_NOTHING}")
        before = target_state(self.bridge, to)
        seen = entry["target"]["state"] or {}
        for key in ("type", "length", "code", "entry"):
            if before.get(key) != seen.get(key):
                raise sg.StopBefore(f"{entry['from']}: the target {entry['to']} has {key} {before.get(key)!r} now, the "
                                    f"plan saw {seen.get(key)!r}: {AFTER_NOTHING}")
        item = {"address": entry["from"], "applied": REFERENCE, "value": record_value(entry),
                "source_pair": f"derived from the code ({entry['kind']} in {entry['function_name']})",
                "to": entry["to"], "ref_type": entry["ref_type"]}
        body = {"from_address": entry["from"], "to_address": entry["to"], "ref_type": entry["ref_type"],
                "source_type": entry["source_type"], "operand_index": entry["operand"]}
        if self.dry_run:
            self.would.append(dict(item, endpoint="add_memory_reference", body=body))
            return True
        to_before = refs_to(self.bridge, to)
        self.attempted.append(item)
        answer = self.bridge.write("add_memory_reference", gb.RELEASE_PROGRAM, **body)
        if not ok_answer(answer, entry):
            raise sg.StopAfter(f"add_memory_reference {entry['from']} -> {entry['to']} answered {str(answer)[:300]!r}: "
                               f"{AFTER_A_WRITE}")
        back = refs_from(self.bridge, at)
        if back != sorted(had + [planned]):
            raise sg.StopAfter(f"{entry['from']}: the references from it read {back}, expected {sorted(had + [planned])}: "
                               f"{AFTER_A_WRITE}")
        self.expected_from[entry["from"]] = back
        after = target_state(self.bridge, to)
        want = dict(before, xref_count=(before.get("xref_count") or 0) + 1)
        if not same_target(after, want, entry["target"]):
            raise sg.StopAfter(f"{entry['from']}: the target {entry['to']} reads {after}, expected {want}: {AFTER_A_WRITE}")
        to_after = refs_to(self.bridge, to)
        if to_after != sorted(to_before + [(entry["from"], entry["ref_type"])]):
            raise sg.StopAfter(f"{entry['from']}: the references to {entry['to']} read {to_after}, expected those before "
                               f"plus this one: {AFTER_A_WRITE}")
        self.targets[entry["to"]] = dict(after)
        self.expected_to[entry["to"]] = to_after
        self.written.append(item)
        return True


def diff_string(offset: int) -> str:
    """``SymbolUtilities.getDiffString``: below 10 in decimal, else 0x and hex."""

    return str(offset) if offset < 10 else "0x%x" % offset


def has_no_components(type_name: str) -> bool:
    """A data item Ghidra gives no components: scalars, strings, pointers, analysis ``undefinedN``."""

    return type_name in gl.SCALARS or type_name.endswith("*") or bool(re.fullmatch(r"undefined\d*|pointer\d*", type_name))


def offcut_name_ok(name: str, target: dict) -> bool:
    """The dynamic name an address inside a data item takes once referenced (``SymbolUtilities.getDynamicDataName``):
    an item without components gives ``<item>+<offset>``; a structure or an array gives the component's path,
    ``<item>.<field>`` or ``<item>[i]`` (plus ``+<offset>`` inside a primitive), or ``<item>+<offset>`` in padding.
    ``<item>`` is a stored label at the item, else its own dynamic name (``<prefix>_<item address>``)."""

    item, _, type_name, offset = target["data"]
    roots = [re.escape(label) for label in target.get("item_labels") or []] or \
        [r"[A-Za-z][^\s+]*_%08x" % int(item, 16)]
    root = "(?:" + "|".join(roots) + ")"
    plus = re.escape("+" + diff_string(offset))
    if re.fullmatch(root + plus, name):
        return True
    return not has_no_components(type_name) and bool(re.fullmatch(root + r"(?:\.|\[)\S*", name))


def same_target(got: dict, want: dict, target: dict | None = None) -> bool:
    """The target as expected: type, length, code state and reference count; its primary name the
    same, or, where there was none, the dynamic name a referenced address takes: ``DAT_..`` (or the
    item's own default label) at a data item's start or in no item, the offcut forms inside an item."""

    if any(got.get(k) != want.get(k) for k in ("type", "length", "code", "entry", "xref_count")):
        return False
    if got.get("name") == want.get("name"):
        return True
    if want.get("name"):
        return False
    inside = (target or {}).get("data")
    if inside and inside[3] > 0:
        return offcut_name_ok(got.get("name") or "", target)
    return gl.is_dynamic(got.get("name") or "", int(got["address"], 16))


def reads_back(bridge, item: dict) -> bool:
    return (item["to"], item["ref_type"]) in refs_from(bridge, int(item["address"], 16))


def next_report(root: Path, stem: str) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    used = [int(m.group(1)) for p in out.glob(f"{stem}.apply-*.json") if (m := re.search(r"\.apply-(\d+)\.json$", p.name))]
    return out / f"{stem}.apply-{max(used, default=0) + 1:03d}.json"


def apply(root: Path, plan_path: Path, bridge, *, dry_run: bool, batch: int | None = None, only=frozenset(),
          check_every: int = CHECK_EVERY, today: str | None = None) -> dict:
    plan = load_plan(plan_path, root)
    if not dry_run:
        pending = names.unsaved(names.read_record(root))
        if pending:
            reports = sorted({row["state"].split(" ", 1)[1] for row in pending})
            raise Refused(f"{names.RECORD.as_posix()} holds {len(pending)} unsaved changes ({', '.join(reports)}): "
                          "save and --confirm-saved (or --discard-unsaved) first")
    check = names.preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    segments = gl.read_segments(bridge, gb.RELEASE_PROGRAM)
    if [[hx(lo), hx(hi), n] for lo, hi, n in segments] != plan["segments"]:
        raise Refused("the release program's memory blocks differ from the plan's: replan")
    out = (root / OUT / f"{plan_path.stem}.dry-run.json") if dry_run else next_report(root, plan_path.stem)
    applier = Applier(bridge, plan, dry_run, batch, only, check_every)
    stopped = kind = None
    try:
        applier.run()
    except (Stop, gb.BridgeError) as exc:
        stopped, kind = str(exc), type(exc).__name__
    finally:
        if not dry_run and applier.written:
            names.update_record(root, applier.written, today or _dt.date.today().isoformat(), out.name)
    result = {
        "plan": plan_path.name, "plan_sha256": plan["plan_sha256"], "selection": plan["selection"],
        "dry_run": dry_run, "stopped": stopped, "stop_kind": kind, "what_to_do": WHAT_TO_DO.get(kind) if kind else None,
        "saved": False, "batch": batch, "batch_full": applier.batch_full, "only": sorted(only),
        "checks": applier.checks, "sent": [] if dry_run else bridge.sent, "written": applier.written,
        "would_write": applier.would, "attempted": [] if dry_run else applier.attempted,
        "counts": {REFERENCE: len(applier.would if dry_run else applier.written)}, "unchanged": applier.unchanged,
        "analysis_changes": applier.analysis_changes, "differences_after_the_stop": applier.after_stop,
        "remove_by_hand": [],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical(result), encoding="utf-8", newline="\n")
    result["report"] = out.name
    return result


def confirm_saved(root: Path, report_path: Path, bridge, today: str | None = None) -> dict:
    return names.confirm_saved(root, report_path, bridge, today, reads_back=reads_back)


def discard_unsaved(root: Path, report_path: Path, bridge) -> dict:
    """After closing without a save: refused while the program holds any reference the report sent."""

    result = json.loads(report_path.read_text(encoding="utf-8"))
    present = [i["address"] for i in result.get("attempted", []) if reads_back(bridge, i)]
    if present:
        raise Refused(f"{len(present)} references of {report_path.name} are still in the program "
                      f"({', '.join(present[:10])}): save and --confirm-saved instead")
    rows = names.read_record(root)
    kept = {k: r for k, r in rows.items() if r["state"] != f"unsaved {report_path.name}"}
    names.write_record(root, kept)
    return {"discarded": len(rows) - len(kept), "report": report_path.name}


# --- command line --------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", nargs="?", const="", metavar="MODULE")
    mode.add_argument("--apply", type=Path, metavar="PLAN")
    mode.add_argument("--confirm-saved", type=Path, metavar="REPORT")
    mode.add_argument("--discard-unsaved", type=Path, metavar="REPORT")
    parser.add_argument("--all", action="store_true", help="with --plan: every release function")
    parser.add_argument("--source-type", default="ANALYSIS", choices=SOURCE_TYPES, help="with --plan")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--batch", type=int, metavar="N", help="with --apply: stop after N references")
    parser.add_argument("--only", action="append", default=[], metavar="0xADDR",
                        help="with --apply: the reference from this instruction only (repeatable), for a pilot")
    parser.add_argument("--check-every", type=int, default=CHECK_EVERY, metavar="N",
                        help="with --apply: references between two snapshots")
    parser.add_argument("--url")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.plan is not None:
            if bool(args.plan) == args.all:
                parser.error("--plan takes either a module or --all")
            bridge = gb.Bridge(args.url, read_only=True)
            check = names.preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            plan = build_plan(root, bridge, args.plan or None, source_type=args.source_type,
                              progress=lambda m: print(m, file=sys.stderr))
            path = write_plan(root, plan)
            print(json.dumps(plan["summary"], indent=1))
            print(f"wrote {path.relative_to(root).as_posix()} (plan sha256 {plan['plan_sha256']})")
            return 0
        if args.all:
            parser.error("--all goes with --plan")
        if args.confirm_saved or args.discard_unsaved:
            bridge = gb.Bridge(args.url, read_only=True)
            check = names.preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            done = (confirm_saved(root, args.confirm_saved.resolve(), bridge) if args.confirm_saved
                    else discard_unsaved(root, args.discard_unsaved.resolve(), bridge))
            print(json.dumps(done))
            return 0
        if args.dry_run == args.yes:
            print("refused: --apply needs exactly one of --dry-run and --yes", file=sys.stderr)
            return 2
        only = frozenset(hx(int(a, 16)) for a in args.only)
        bridge = gb.Bridge(args.url, read_only=args.dry_run, writes=gb.REFERENCE_WRITES)
        result = apply(root, args.apply.resolve(), bridge, dry_run=args.dry_run, batch=args.batch, only=only,
                       check_every=args.check_every)
        print(json.dumps({k: result[k] for k in ("report", "dry_run", "stopped", "stop_kind", "counts", "unchanged",
                                                 "batch_full", "checks")}, indent=1))
        if result["what_to_do"]:
            print(f"what to do: {result['what_to_do']}")
        return 1 if result["stopped"] else 0
    except (Refused, gb.BridgeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
