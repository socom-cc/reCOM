"""Stage 3, function starts: give every function of the release map a Ghidra function in ``SCUS_971.34``.

    python tools/release/starts.py --plan
    python tools/release/starts.py --apply build/release/starts/plan-starts.json --dry-run
    python tools/release/starts.py --apply build/release/starts/plan-starts.json --yes [--batch N]
    python tools/release/starts.py --confirm-saved build/release/starts/plan-starts.apply-001.json
    python tools/release/starts.py --discard-unsaved build/release/starts/plan-starts.apply-001.json

It handles the map functions the names step left without a function of their own (map starts
without an instruction, map functions inside another Ghidra function, withheld creates) and the
boundary differences. Writes are ``disassemble_bytes`` over exactly a map extent (sent with
``restrict_to_execute_memory`` false, which the plugin passes to ``DisassembleCommand`` as its
followFlow argument, so only fall-through is disassembled) and ``create_function`` with
``disassemble_first`` false. Nothing is ever removed, cleared or saved by the tool.

What Ghidra 12.1.4 does after each write, as the plan predicts it (sources named in
``docs/release/RULES.md``, "Stage 3: function starts"):

* ``DisassembleCommand`` (followFlow false) disassembles every undefined address of the range by
  fall-through, skips defined data, stops silently at an existing identical instruction
  (``CodeManager.checkInstructionSet``: DUPLICATE), bookmarks a fall into data or bytes that do
  not decode ("Bad Instruction"), re-makes an existing instruction it meets as a delay slot, and
  goes on past the range end while the last instruction falls through; it notifies auto-analysis
  (``codeDefined``);
* the instruction analyzers then create a function at every call target that is none
  ("Subroutine References": a target without an instruction gets a one-byte place-holder),
  turn jumps to function entries into call-returns ("Shared Return Calls"), and may define data
  or disassemble at addresses the new code references (operand references);
* ``CreateFunctionCmd`` follows flow (``createflow``) and takes the new body out of an existing
  function it overlaps (``subtractBodyFromExisting``); the function analyzers then run "Shared
  Return Calls" for every added or re-bodied function: jumps to its entry become call-returns,
  and with "Assume Contiguous Functions Only" every unconditional jump between the previous
  function's entry and the next function that crosses a function makes Ghidra create a function
  at its target (the ``_doMC`` case of batch 1).

The plan repeats all of that over the release image and the live state, orders the steps so that
every call, jump or fall-through target is a function first, and withholds what it cannot
predict. The apply compares after every step the whole function list, every code gap, every
bookmark and every defined data item, and the bodies and signatures of the functions near the
step, with the prediction; a full snapshot of every function's body, signature and flags is taken
at the start and the end of a run. Any difference stops the run.
"""
from __future__ import annotations

import argparse
import bisect
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import createflow  # noqa: E402
import elfimage  # noqa: E402
import ghidra_bridge as gb  # noqa: E402
import mips  # noqa: E402
import names as nm  # noqa: E402
from elfimage import PROTOTYPE_SHA256, RELEASE_SHA256  # noqa: E402

OUT = Path("build/release/starts")
NAMES_PLAN = Path("build/release/names/plan-all.json")
PLAN_KIND = "socom-release-starts-plan"
PLAN_SCHEMA = 1
PLAN_STEM = "plan-starts"
AROUND = 0x40  # words on each side of a disassembled range whose code-unit state is compared
# "create": code without a function that the names step would create (a start disassembled by an
# earlier starts run whose create is still to come)
CASES = ("no-instruction", "inside", "boundary", "create-withheld", "create")
TERMINATORS = frozenset({createflow.ERET})
hx = nm.hx
Refused = nm.Refused


class Stop(nm.Stop):
    kind = "stop"


class StopBefore(Stop):
    """The live state is not the planned one; nothing was sent for this entry."""

    kind = "before"


class StopAfter(Stop):
    """A write was sent and what reads back differs from the prediction."""

    kind = "after"


class AnalysisStop(Stop):
    """Ghidra changed something after a write that the plan did not predict."""

    kind = "analysis"


WHAT_TO_DO = {
    "before": "nothing was sent for this entry: have the batch checked, save, --confirm-saved this report, "
              "rerun names.py --plan --all and replan",
    "after": "the write was sent and reads back otherwise: the program now holds it and whatever Ghidra's analysis "
             "did after it (a create that failed commits its partial effects too). Close the program without "
             "saving, --discard-unsaved this report, then replan; nothing is removed or cleared by hand (removing "
             "a new function gives a cut container neither its body nor its jumps back)",
    "analysis": "Ghidra's analysis changed something the plan did not predict (listed under analysis_changes, or "
                "side_effects for the end-of-run snapshot): check it; if acceptable, save and --confirm-saved (the "
                "change itself is not recorded), otherwise close without saving and --discard-unsaved; then replan",
    "stop": "check the report, then save and --confirm-saved or close without saving and --discard-unsaved",
}


# --- instruction facts (R5900, as Ghidra's language gives them) -------------------------------

def has_delay(word: int) -> bool:
    return (mips.branch_target(word, 0) is not None or mips.is_j(word) or mips.is_jal(word)
            or mips.is_jr(word) or createflow.is_call(word))


def falls_through(word: int) -> bool:
    if word in TERMINATORS or mips.is_j(word):
        return False
    if mips.is_jr(word):
        return False
    if mips.branch_target(word, 0) is not None and mips.is_unconditional_branch(word):
        return False
    return True


def flow_targets(word: int, pc: int) -> tuple[str, int] | None:
    """(kind, target) of a direct call, jump or branch."""

    if mips.is_jal(word):
        return "call", mips.jump_target(word, pc)
    if mips.is_j(word):
        return "jump", mips.jump_target(word, pc)
    target = mips.branch_target(word, pc)
    if target is None:
        return None
    if createflow.is_call(word):
        return "call", target
    return ("jump" if mips.is_unconditional_branch(word) else "branch"), target


def lui_references(word_at, start: int, end: int) -> list[tuple[int, int]]:
    """(instruction, address) of each lui/low-half pair inside [start, end): constant references."""

    out, high, clear_next = [], {}, False
    for pc in range(start, end, 4):
        word = word_at(pc)
        op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
        after_slot = clear_next  # a call clobbers registers after its delay slot, which still sees them
        clear_next = createflow.is_call(word)
        if op == 0x0F:
            high[rt] = (word & 0xFFFF) << 16
        else:
            if rs in high and (op == 0x09 or op == 0x0D or op in mips.LOADSTORE):
                low = (word & 0xFFFF) if op == 0x0D else mips.simm(word)
                out.append((pc, (high[rs] + low) & 0xFFFFFFFF))
            for reg in mips.written_registers(word):
                high.pop(reg, None)
        if after_slot:
            high.clear()
    return out


def access_kind(word: int) -> str:
    """How the low half of a lui pair uses the address: Ghidra gives loads READ and stores WRITE references."""

    op = word >> 26
    if op in mips.LOADS:
        return "read"
    if op in mips.LOADSTORE:
        return "write"
    return "address"


# --- address sets ------------------------------------------------------------------------------

def ranges(words) -> list[list[str]]:
    """Inclusive byte ranges of a set of word addresses, as hex pairs."""

    out: list[list[int]] = []
    for a in sorted(words):
        if out and out[-1][1] == a - 1:
            out[-1][1] = a + 3
        else:
            out.append([a, a + 3])
    return [[hx(lo), hx(hi)] for lo, hi in out]


def words_of(spans) -> set[int]:
    return {a for lo, hi in spans for a in range(int(lo, 16) if isinstance(lo, str) else lo,
                                                 (int(hi, 16) if isinstance(hi, str) else hi) + 1, 4)}


def subtract_interval(intervals: list[tuple[int, int]], lo: int, hi: int) -> list[tuple[int, int]]:
    out = []
    for a, b in intervals:
        if b < lo or a > hi:
            out.append((a, b))
            continue
        if a < lo:
            out.append((a, lo - 1))
        if b > hi:
            out.append((hi + 1, b))
    return out


def add_interval(intervals: list[tuple[int, int]], lo: int, hi: int) -> list[tuple[int, int]]:
    merged = sorted(intervals + [(lo, hi)])
    out: list[tuple[int, int]] = []
    for a, b in merged:
        if out and a <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# --- live reads --------------------------------------------------------------------------------

def read_gaps(bridge) -> list[dict]:
    value = bridge.get("find_code_gaps", gb.RELEASE_PROGRAM, min_size=1, offset=0, limit=1000000)
    if not isinstance(value, dict) or not isinstance(value.get("gaps"), list) or value.get("total") != len(value["gaps"]):
        raise gb.BridgeError(f"find_code_gaps did not answer the whole list: {str(value)[:200]}")
    return [{"start": int(g["start"], 16), "end": int(g["end"], 16), "undefined": bool(g["has_undefined_bytes"]),
             "orphans": bool(g["has_orphaned_instructions"]),
             "before": int(g["before_function_address"], 16) if g.get("before_function_address") else None,
             "after": int(g["after_function_address"], 16) if g.get("after_function_address") else None}
            for g in value["gaps"]]


def read_bookmarks(bridge) -> list[tuple]:
    value = bridge.get("list_bookmarks", gb.RELEASE_PROGRAM)
    if not isinstance(value, dict) or not isinstance(value.get("bookmarks"), list):
        raise gb.BridgeError(f"list_bookmarks: {str(value)[:200]}")
    return sorted((int(b["address"], 16), b.get("type"), b.get("category"), b.get("comment"))
                  for b in value["bookmarks"])


_DATA = re.compile(r"^.* @ ([0-9a-fA-F]+) \[(.*)\] \((\d+) bytes?\)$")


def read_data(bridge) -> list[tuple[int, int, str]]:
    text = bridge.get("list_data_items", gb.RELEASE_PROGRAM, offset=0, limit=10000000)
    if not isinstance(text, str):
        raise gb.BridgeError(f"list_data_items: {str(text)[:200]}")
    out = []
    for line in text.splitlines():
        if match := _DATA.match(line.strip()):
            out.append((int(match.group(1), 16), int(match.group(3)), match.group(2)))
    return sorted(out)


def read_functions(bridge) -> dict[int, dict]:
    return nm.function_list(bridge, gb.RELEASE_PROGRAM)


def is_code_live(bridge, address: int) -> bool:
    value = bridge.get("audit_global", gb.RELEASE_PROGRAM, address=hx(address))
    if not isinstance(value, dict):
        raise gb.BridgeError(f"audit_global {hx(address)}: {str(value)[:200]}")
    return bool(value.get("is_code_address"))


def references_to(bridge, address: int) -> list[str]:
    text = bridge.get("get_xrefs_to", gb.RELEASE_PROGRAM, address=hx(address), offset=0, limit=100)
    if not isinstance(text, str):
        return []
    return sorted(line.strip() for line in text.splitlines() if line.strip().startswith("From "))


def extent_references(bridge, start: int, size: int) -> list[str]:
    """Every reference to any word of an extent, as ``From <source> [<type>] -> <word>``."""

    return [f"{line} -> {hx(w)}" for w in range(start, start + size, 4) for line in references_to(bridge, w)]


def flow_references(bridge, address: int) -> list[tuple[int, str]]:
    """(target, reference type) of every flow reference from ``address`` (``get_xrefs_from``)."""

    text = bridge.get("get_xrefs_from", gb.RELEASE_PROGRAM, address=hx(address), offset=0, limit=100)
    if not isinstance(text, str):
        return []
    found = re.findall(r"^To ([0-9a-fA-F]+)\b.*\[(\w+)\]$", text, re.M)
    return [(int(a, 16), kind) for a, kind in found if "JUMP" in kind or "CALL" in kind]


def calls_to(bridge, address: int, target: int) -> bool:
    """A jump turned into a call-return shows a CALL reference to its target (seen at 0x153238)."""

    return any(to == target and "CALL" in kind for to, kind in flow_references(bridge, address))


def fingerprint(functions: dict, gaps: list, bookmarks: list, data: list) -> dict:
    return {
        "functions": nm.sha256_text(nm.canonical(sorted([hx(a), f["name"], f["thunk"]] for a, f in functions.items()))),
        "gaps": nm.sha256_text(nm.canonical([[hx(g["start"]), hx(g["end"]), g["undefined"], g["orphans"]] for g in gaps])),
        "bookmarks": nm.sha256_text(nm.canonical([list(b[:3]) + [b[3]] for b in bookmarks])),
        "data": nm.sha256_text(nm.canonical([[hx(a), n, t] for a, n, t in data])),
        "counts": {"functions": len(functions), "gaps": len(gaps), "bookmarks": len(bookmarks), "data": len(data)},
    }


# --- the model: what the program holds, as the plan predicts it -------------------------------

class Model:
    """Function entries, bodies, instructions and gaps, before and after each planned step."""

    def __init__(self, image, functions: dict, spans: dict, noreturn: set, gaps: list, data: list, code_at):
        self.image = image
        self.functions = {a: dict(f) for a, f in functions.items()}  # entry -> name, thunk
        self.spans = dict(spans)  # entry -> (lo, hi)
        self.bodies: dict[int, set[int]] = {}  # entries whose body is known word by word
        self.noreturn = set(noreturn)
        self.order = sorted(self.functions)
        self.gaps = sorted((g["start"], g["end"]) for g in gaps)
        self.gap_flags = {(g["start"], g["end"]): (g["undefined"], g["orphans"]) for g in gaps}
        # gaps whose every instruction is known (none before the plan, or only the plan's own)
        self.known = {(g["start"], g["end"]) for g in gaps if not g["orphans"]}
        self.data = data
        self._data_starts = [d[0] for d in data]
        self.code_at = code_at  # live: does this word hold an instruction (cached)
        self.new_code: set[int] = set()
        self.refs_to = lambda address: []  # the reference types to an address (the plan reads them live)

    def copy(self) -> "Model":
        other = Model.__new__(Model)
        other.__dict__.update(self.__dict__)
        other.functions = {a: dict(f) for a, f in self.functions.items()}
        other.spans, other.bodies = dict(self.spans), {a: set(b) for a, b in self.bodies.items()}
        other.noreturn, other.order = set(self.noreturn), list(self.order)
        other.gaps, other.gap_flags, other.new_code = list(self.gaps), dict(self.gap_flags), set(self.new_code)
        other.known = set(self.known)
        return other

    def gap_of(self, address: int):
        i = bisect.bisect_right(self.gaps, (address, 1 << 40)) - 1
        if i >= 0 and self.gaps[i][0] <= address <= self.gaps[i][1]:
            return self.gaps[i]
        return None

    def in_data(self, address: int) -> bool:
        i = bisect.bisect_right(self._data_starts, address) - 1
        return i >= 0 and self.data[i][0] <= address < self.data[i][0] + self.data[i][1]

    def state(self, address: int) -> str:
        if address in self.new_code:
            return "code"
        if self.in_data(address):
            return "data"
        gap = self.gap_of(address)
        if gap is None:
            return "code"  # inside a function body
        if gap in self.known:
            return "undefined"  # every instruction of this gap is the plan's own
        return "code" if self.code_at(address) else "undefined"

    def is_code(self, address: int) -> bool:
        return self.image.contains(address) and self.state(address) == "code"

    def prev_entry(self, address: int) -> int | None:
        i = bisect.bisect_left(self.order, address) - 1
        return self.order[i] if i >= 0 else None

    def next_entry(self, address: int) -> int | None:
        i = bisect.bisect_right(self.order, address)
        return self.order[i] if i < len(self.order) else None

    def containing(self, address: int) -> int | None:
        for entry, body in self.bodies.items():
            if address in body:
                return entry
        if self.gap_of(address) is not None:
            return None
        entry = self.prev_entry(address + 1)
        while entry is not None:
            lo, hi = self.spans.get(entry, (entry, entry))
            if lo <= address <= hi and entry not in self.bodies:
                return entry
            entry = self.prev_entry(entry)
            if entry is not None and address - entry > 0x40000:
                return None
        return None

    def add_function(self, entry: int, body: set[int], name: str, thunk: bool) -> None:
        self.functions[entry] = {"name": name, "thunk": thunk}
        self.bodies[entry] = set(body)
        self.spans[entry] = (min(body), max(body) + 3)
        bisect.insort(self.order, entry)
        for a in body:
            self.take(a)

    def _flags(self, piece: tuple[int, int], known: bool, start_flag=None) -> None:
        """Flags of a gap the plan changed: known when every instruction in it is known."""

        lo, hi = piece
        if known:
            ours = any(a in self.new_code for a in range(lo - lo % 4, hi + 1, 4))
            undefined = lo not in self.new_code and not self.in_data(lo)
            self.gap_flags[piece] = (undefined, ours)
            self.known.add(piece)
        else:
            self.gap_flags[piece] = (start_flag, None)
            self.known.discard(piece)

    def take(self, address: int) -> None:
        gap = self.gap_of(address)
        if gap is None:
            return
        known = gap in self.known
        old_undefined = self.gap_flags.pop(gap)[0]
        self.gaps.remove(gap)
        self.known.discard(gap)
        for piece in subtract_interval([gap], address, address + 3):
            bisect.insort(self.gaps, piece)
            self._flags(piece, known, old_undefined if piece[0] == gap[0] else None)

    def free(self, address: int) -> None:
        """A word that leaves a body (an instruction) joins the gaps around it."""

        lo, hi, start_flag = address, address + 3, False
        for gap in (self.gap_of(address - 1), self.gap_of(address + 4)):
            if gap is not None:
                flag = self.gap_flags.pop(gap)[0]
                self.gaps.remove(gap)
                self.known.discard(gap)
                if gap[0] < lo:
                    start_flag = flag
                lo, hi = min(lo, gap[0]), max(hi, gap[1])
        bisect.insort(self.gaps, (lo, hi))
        self.gap_flags[(lo, hi)] = (start_flag, True)  # it holds the freed instruction

    def disassembled(self, words: set[int]) -> None:
        self.new_code |= words
        for gap in {self.gap_of(a) for a in words} - {None}:
            undefined, _ = self.gap_flags[gap]
            self.gap_flags[gap] = (False if gap[0] in words else undefined, True)

    def set_body(self, entry: int, body: set[int]) -> None:
        self.bodies[entry] = set(body)
        self.spans[entry] = (min(body), max(body) + 3)

    def expected_gaps(self) -> list[dict]:
        """Every gap as ``find_code_gaps`` should list it; a flag the plan cannot know is None."""

        return [{"start": lo, "end": hi, "undefined": self.gap_flags.get((lo, hi), (None, None))[0],
                 "orphans": self.gap_flags.get((lo, hi), (None, None))[1],
                 "before": self.prev_entry(lo), "after": self.next_entry(hi)} for lo, hi in self.gaps]


# --- simulation --------------------------------------------------------------------------------

def simulate_disassembly(model: Model, start: int, end: int) -> dict:
    """What ``DisassembleCommand`` (followFlow false) makes of [start, end)."""

    word_at = model.image.word
    new: set[int] = set()
    for first in range(start, end, 4):
        if first in new or model.state(first) != "undefined":
            continue
        pc = first
        while True:
            if not model.image.contains(pc):
                return {"error": f"flow leaves the loaded image at {hx(pc)}"}
            state = "code" if pc in new else model.state(pc)
            if state == "code":
                break  # an identical existing instruction: CodeManager marks a DUPLICATE, no bookmark
            if state == "data":
                return {"error": f"flow falls into defined data at {hx(pc)} (a Bad Instruction bookmark)"}
            word = word_at(pc)
            if mips.is_invalid(word):
                return {"error": f"bytes that do not decode at {hx(pc)} (a Bad Instruction bookmark)"}
            new.add(pc)
            step = 4
            if has_delay(word):
                slot = pc + 4
                slot_state = "code" if slot in new else model.state(slot)
                if slot_state == "code":
                    return {"error": f"the delay slot at {hx(slot)} is an existing instruction (the function entry "
                                     "there would be re-made as a delay slot)"}
                if slot_state == "data" or mips.is_invalid(word_at(slot)):
                    return {"error": f"the delay slot at {hx(slot)} is data or does not decode"}
                new.add(slot)
                step = 8
            if not falls_through(word):
                break
            pc += step
            if pc - end > 0x40:
                return {"error": f"falls through past its end beyond {hx(end + 0x40)}"}
    overrun = sorted(a for a in new if a >= end)
    return {"error": None, "new": new, "overrun": overrun}


FOUND_CODE = ("Analysis", "Found Code", "Found code from operand reference")
# what the Reference analyzer may define at an address the new code points to (checkForAscii,
# checkForUnicode, checkForPointer): a string, a unicode string or a pointer
DATA_KINDS = ("string", "unicode", "char", "ds", "pointer")


def data_kind_allowed(type_name: str) -> bool:
    low = type_name.lower()
    return "string" in low or "pointer" in low or low.startswith(DATA_KINDS)


def valid_subroutine(model: Model, target: int) -> tuple[bool, str, set[int]]:
    """``PseudoDisassembler.checkValidSubroutine(target, allowExistingCode=false, mustTerminate=true)``.

    Follows fall-through and jumps (not calls; a call to a no-return function ends its run), at
    most 4000 instructions; fails on bytes that do not decode, on existing code or data in the
    body, on a body of one instruction, on references into the body other than at its entry, on
    eight zero bytes at the entry; needs a return (jr ra, eret), a computed jump or a jump or call
    to an existing function.
    """

    word_at, contains = model.image.word, model.image.contains
    if not (contains(target) and contains(target + 4)):
        return False, "outside the image", set()
    if word_at(target) == 0 and word_at(target + 4) == 0:
        return False, "starts with eight zero bytes", set()
    starts_, stack, terminated, called = set(), [target], False, False
    while stack:
        pc = stack.pop()
        if pc in starts_:
            continue
        if len(starts_) > 4000 or not contains(pc) or not contains(pc + 4):
            return False, "runs out of the image or past 4000 instructions", set()
        word = word_at(pc)
        if mips.is_invalid(word) or model.state(pc) != "undefined":
            return False, f"meets {'bytes that do not decode' if mips.is_invalid(word) else model.state(pc)} at {hx(pc)}", set()
        starts_.add(pc)
        step = 4
        if has_delay(word):
            slot = pc + 4
            if mips.is_invalid(word_at(slot)) or model.state(slot) != "undefined":
                return False, f"its delay slot at {hx(slot)} is no undefined instruction", set()
            starts_.add(slot)
            step = 8
        if word == mips.JR_RA or word in TERMINATORS or (mips.is_jr(word) and word != mips.JR_RA):
            terminated = True
        found = flow_targets(word, pc)
        if found:
            kind, t = found
            if t in model.functions:
                called = True
            elif kind != "call":
                stack.append(t)
            if kind == "call" and t in model.noreturn:
                continue
        if falls_through(word):
            stack.append(pc + step)
    if not (terminated or called):
        return False, "does not reach a return", set()
    if len(starts_) == 1 and not called:
        return False, "one instruction", set()
    inside = [a for a in sorted(starts_) if a != target and model.refs_to(a)]
    if inside:
        return False, f"something references {hx(inside[0])} inside it", set()
    return True, "", starts_


def follow_disassembly(model: Model, target: int) -> dict:
    """``DisassembleCommand(target, null, true)`` as the Reference analyzer sends it: all flow, calls too."""

    word_at, new, calls, stack = model.image.word, set(), set(), [target]
    while stack:
        pc = stack.pop()
        if pc in new or model.state(pc) == "code":
            continue
        if model.state(pc) == "data" or mips.is_invalid(word_at(pc)):
            return {"error": f"its flow reaches data or bytes that do not decode at {hx(pc)}"}
        new.add(pc)
        step = 4
        if has_delay(word_at(pc)):
            new.add(pc + 4)
            step = 8
        found = flow_targets(word_at(pc), pc)
        if found:
            kind, t = found
            if kind == "call" and t not in model.functions and t != pc + 8:
                calls.add(t)
            stack.append(t)
            if kind == "call" and t in model.noreturn:
                continue
        if falls_through(word_at(pc)):
            stack.append(pc + step)
        if len(new) > 0x4000:
            return {"error": "runs on past 64 KiB"}
    if calls:
        return {"error": f"the code found calls {hx(min(calls))}, which is no function (Subroutine References "
                         "would make one)", "new": new}
    return {"error": None, "new": new}


def operand_effects(model: Model, start: int, end: int) -> dict:
    """What the Reference analyzer (``OperandReferenceAnalyzer``) does with what new code points to.

    For every lui/low-half pair of the new code whose target is undefined now: a load or a store
    gives READ/WRITE references, so only a string, a unicode string or a pointer may be defined
    there; an address taken (addiu/ori) at a target nothing reads or writes, which passes the
    valid-subroutine test, is disassembled with flow following (no function is made: its
    createFunctions is empty) and bookmarked "Found Code"; otherwise data may be defined there.
    """

    found, data, errors, seen = [], [], [], set()
    for pc, target in lui_references(model.image.word, start, end):
        if not model.image.contains(target) or target in model.functions or start <= target < end:
            continue
        if target in seen:  # checkedTargets: each target once
            continue
        seen.add(target)
        if model.state(target) != "undefined":
            continue
        kind = access_kind(model.image.word(pc))
        reads = [r for r in model.refs_to(target) if "READ" in r or "WRITE" in r]
        why = "a load or store: READ/WRITE references, no code is looked for" if kind != "address" else (
            "read or written elsewhere (hasDataAccessReferences)" if reads else "")
        if kind == "address" and not reads:
            ok, why, _ = valid_subroutine(model, target)
            why = f"no valid subroutine there: {why}" if not ok else why
            if ok:
                flow = follow_disassembly(model, target)
                if flow["error"]:
                    errors.append(f"the Reference analyzer would disassemble at {hx(target)} (from {hx(pc)}) and "
                                  f"{flow['error']}")
                    continue
                found.append({"target": hx(target), "by": hx(pc), "instructions": ranges(flow["new"]),
                              "bookmark": [hx(target), *FOUND_CODE]})
                continue
        data.append({"address": hx(target), "by": hx(pc), "access": kind, "why": why})
    return {"found": found, "data": data, "errors": errors}


def body_flow(model: Model, entry: int, jumps: dict | None = None):
    return createflow.predict(model.image.word, model.image.contains, entry, set(model.functions),
                              model.noreturn, jumps or {}, is_code=model.is_code,
                              terminal=lambda w: w in TERMINATORS)


def fallthrough_into(model: Model, dest: int) -> bool:
    """``SharedReturnAnalysisCmd.checkIfCouldHaveFallThruTo``: an instruction falls into ``dest``."""

    word_at = model.image.word
    if not model.is_code(dest - 4):
        return False
    if model.is_code(dest - 8) and has_delay(word_at(dest - 8)):
        return falls_through(word_at(dest - 8))
    if has_delay(word_at(dest - 4)):
        return False
    return falls_through(word_at(dest - 4))


def jump_sources(model: Model, dest: int, index: dict) -> list[int]:
    return [s for s in index.get(dest, ()) if model.is_code(s)]


def shared_return(model: Model, events: list[int], index: dict, jumps: dict, new: frozenset = frozenset(),
                  sources=None) -> dict:
    """``SharedReturnAnalyzer`` for every function added or re-bodied: overrides and functions it creates.

    Jumps to a function that existed before were turned into call-returns when that function was
    added, so only jumps to the ``new`` functions are predicted to change; ``sources`` limits the
    predicted overrides to these jump sites (the new code of a disassembly).
    """

    overrides: set[tuple[int, int]] = set()
    creates: list[dict] = []
    seen = set()

    def convert(dest):
        if dest not in new:
            return
        for src in jump_sources(model, dest, index):
            if src in model.functions or model.containing(src) == dest:
                continue
            if sources is None or src in sources:
                overrides.add((src, dest))

    def want(src, dest):
        if dest in model.functions:
            convert(dest)
            return
        if not model.is_code(dest) or fallthrough_into(model, dest) or model.image.word(dest) == mips.JR_RA:
            return
        creates.append({"at": hx(dest), "jump": hx(src)})

    queue = list(events)
    while queue:
        entry = queue.pop(0)
        if entry in seen:
            continue
        seen.add(entry)
        convert(entry)
        prev, nxt = model.prev_entry(entry), model.next_entry(entry)
        scan = set(range(prev if prev is not None else entry, entry + 1, 4))
        below = set(range(entry, (nxt if nxt is not None else entry + 4), 4))
        body = model.bodies.get(entry)
        if body is None and model.spans.get(entry, (None,))[0] == entry:
            lo, hi = model.spans[entry]  # a body known by its ends only: taken as one range
            body = set(range(lo, hi + 1, 4))
        if body is not None and len(ranges(body)) <= 1:
            below -= body
        elif body is not None:
            below |= body
        for src in sorted(scan | below):
            if not model.is_code(src):
                continue
            word = model.image.word(src)
            targets = []
            if mips.is_j(word):
                targets = [mips.jump_target(word, src)]
            elif mips.branch_target(word, src) is not None and mips.is_unconditional_branch(word) \
                    and not createflow.is_call(word):
                targets = [mips.branch_target(word, src)]
            elif mips.is_jr(word) and word != mips.JR_RA:
                targets = jumps.get(src, [])
            for dest in targets:
                if dest > src:
                    after = model.next_entry(src)
                    if after is not None and dest >= after:
                        want(src, dest)
                elif dest < src:
                    before = model.prev_entry(src)
                    if before is not None and dest < before:
                        want(src, dest)
    return {"overrides": sorted(overrides), "creates": creates}


def thunk_target(model: Model, entry: int, body: set[int]) -> int | None:
    if len(body) != 2 or model.image.word(entry + 4) != 0:
        return None
    word = model.image.word(entry)
    target = mips.jump_target(word, entry) if mips.is_j(word) else (
        mips.branch_target(word, entry) if mips.is_unconditional_branch(word) else None)
    return target if target in model.functions else None


def shown_name(model: Model, entry: int, thunk_of: int | None) -> str:
    if thunk_of is None:
        return "FUN_%08x" % entry
    shown = model.functions[thunk_of]["name"]
    return f"thunk_{shown}" if nm.is_default_name(shown) and not model.functions[thunk_of]["thunk"] else shown


def simulate_create(model: Model, entry: int, size: int, index: dict, jumps: dict) -> dict:
    """``CreateFunctionCmd`` at ``entry`` and the analysis after it, on ``model`` (changed in place)."""

    end = entry + size
    if not model.is_code(entry):
        return {"withheld": "no instruction at the start when the create would be sent"}
    flow = body_flow(model, entry, jumps)  # flow into an address without an instruction ends there
    if flow.outside:
        return {"withheld": "flow leaves the loaded image"}
    body = set(flow.body)
    extent = set(range(entry, end, 4))
    cuts = []
    for other, known in sorted(model.bodies.items()):
        if other == entry or not (known & body):
            continue
        top = max(body) + 3
        cut = {a for a in known if not (entry <= a <= (top if other < entry else other - 1))}
        if cut != known:
            if not cut:
                return {"withheld": f"the create would take the whole body of the function at {hx(other)}"}
            cuts.append((other, known, cut))
        body -= cut
    unknown = sorted(a for a in body if model.gap_of(a) is None and not any(a in k for _, k, _ in cuts))
    if unknown:
        return {"withheld": f"its body would overlap a function body the plan did not read at {hx(unknown[0])}"}
    accepted = None
    if body != extent:
        beyond = sorted(a for a in body if a >= end)
        missing = sorted(a for a in extent if a not in body)
        below = sorted(a for a in body if a < entry)
        if below:
            return {"withheld": f"its flow reaches {hx(below[0])}, below its entry"}
        if beyond and not missing and all(model.image.word(a) == 0 for a in beyond) \
                and beyond == list(range(end, end + 4 * len(beyond), 4)) and (end + 4 * len(beyond)) in model.functions:
            accepted = {"kind": "padding", "range": ranges(beyond)[0],
                        "why": "the last instruction falls through into padding (nop) up to the next function"}
        elif missing and [pc for pc in flow.computed if not jumps.get(pc)]:
            return {"withheld": f"computed jump at {hx(flow.computed[0])} without known targets and words of the "
                                "extent no flow reaches: Ghidra's switch analysis would decide the body"}
        elif missing and not beyond and min(body) == entry and max(body) == end - 4:
            accepted = {"kind": "unreachable", "ranges": ranges(missing),
                        "why": "words of the extent that no flow reaches (dead code); body lowest and highest "
                               "address equal the map's"}
        elif missing and not beyond and min(body) == entry and model.image.word(max(body)) in TERMINATORS:
            tail = [a for a in range(max(body) + 4, end, 4)]
            words = [model.image.word(a) for a in tail]
            if words == [mips.JR_RA, 0] and set(tail) <= set(missing):
                accepted = {"kind": "unreachable", "ranges": ranges(tail),
                            "why": "a jr ra; nop after an eret that no flow reaches"}
            else:
                return {"withheld": f"its flow ends at the eret at {hx(max(body))}; the {4 * len(tail)} bytes after it "
                                    "are reached by no flow (a body shorter than the map needs a decision)"}
        elif beyond:
            first = next((a for a in beyond if model.image.word(a) != 0), beyond[-1] + 4)
            return {"withheld": f"flows past its end to {hx(beyond[0])} into code that is no function entry",
                    "needs_function": first}
        elif flow.computed:
            return {"withheld": f"computed jump at {hx(flow.computed[0])}: part of the extent is reached only "
                                "through it (Ghidra's switch analysis would decide the body)"}
        else:
            return {"withheld": f"flow does not reach {hx(missing[0])}..: the body would end before the extent"}
    target = thunk_target(model, entry, body)
    for other, _, cut in cuts:
        model.set_body(other, cut)
    for other, known, cut in cuts:
        for a in known - cut - body:
            model.free(a)
    model.add_function(entry, body, shown_name(model, entry, target), target is not None)
    events = [entry] + [c[0] for c in cuts]
    analysis = shared_return(model, events, index, jumps, frozenset({entry}))
    if analysis["creates"]:
        c = analysis["creates"][0]
        return {"withheld": f"analysis would create a function at {c['at']}: the jump at {c['jump']} crosses "
                            "a function after this create (Shared Return Calls)",
                "needs_function": int(c["at"], 16)}
    return {"withheld": None, "body": body, "accepted": accepted, "thunk_of": target,
            "cuts": [{"function": hx(o), "before": ranges(k), "after": ranges(c)} for o, k, c in cuts],
            "overrides": [{"at": hx(s), "to": hx(d)} for s, d in analysis["overrides"]]}


# --- names from function-start patterns ---------------------------------------------------------

# Ghidra's "Function Start Search" (BytePatterns: FunctionStartAnalyzer) reads the language's
# pattern file; the Emotion Engine Reloaded extension ships r5900_LE_patterns.xml, whose
# <pattern> entries with <funcstart label=".." validcode="function"/> name the kernel call stubs
# (li v1,N; syscall; jr ra; nop). validcode="function" needs a function at the match, so the first
# whole-program search only left a "potential match" mark there; FunctionStartFuncAnalyzer (a
# function analyzer) searches those marks again when a function is added at one and then calls
# setFunctionLabel: SymbolTable.createLabel(.., ANALYSIS), which renames a function whose name is
# still DEFAULT; a further pattern of the same bytes adds a second label unless a symbol there
# already contains its text (AddDmacHandler and AddDmacHandler2 at 0x15a600). thunk="true" makes
# the function a thunk (CreateThunkFunctionCmd).
PATTERN_FILE = ("ghidra", "ghidra_12.1.4_PUBLIC", "Extensions", "ghidra-emotionengine-reloaded", "data", "patterns",
                "r5900_LE_patterns.xml")


def default_patterns() -> Path | None:
    if os.environ.get("SOCOM_R5900_PATTERNS"):
        return Path(os.environ["SOCOM_R5900_PATTERNS"])
    base = os.environ.get("APPDATA")
    return Path(base, *PATTERN_FILE) if base else None


def _ditted(text: str) -> list[tuple[int, int]]:
    """A Ghidra DittedBitSequence: hex tokens (0x.. with '.' nibbles) or 8-bit binary tokens."""

    out = []
    for token in text.split():
        if token.startswith("0x"):
            digits = token[2:]
            for i in range(0, len(digits), 2):
                pair, value, mask = digits[i:i + 2], 0, 0
                for ch in pair:
                    value, mask = value << 4, mask << 4
                    if ch != ".":
                        value |= int(ch, 16)
                        mask |= 0xF
                out.append((value, mask))
        else:
            value = mask = 0
            for ch in token:
                value, mask = value << 1, mask << 1
                if ch != ".":
                    value |= int(ch)
                    mask |= 1
            out.append((value, mask))
    return out


def load_patterns(path: Path) -> dict:
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    patterns = []
    for index, node in enumerate(root.findall("pattern")):
        start = node.find("funcstart")
        if start is None or start.get("validcode") != "function":
            continue
        for data in node.findall("data"):
            patterns.append({"index": index, "bytes": _ditted(data.text or ""), "label": start.get("label"),
                             "thunk": start.get("thunk") == "true"})
    return {"file": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "patterns": patterns}


def pattern_effects(image, address: int, patterns: dict | None) -> dict:
    """The names, labels and thunk flag the function-start patterns give a function created at ``address``."""

    out = {"name": None, "labels": [], "thunk": False, "patterns": []}
    if not patterns:
        return out
    symbols: list[str] = []
    for p in patterns["patterns"]:
        n = len(p["bytes"])
        if not (image.contains(address) and image.contains(address + n - 1)):
            continue
        data = image.data[address - image.base:address - image.base + n]
        if all((b & m) == v for b, (v, m) in zip(data, p["bytes"])):
            out["patterns"].append(p["index"])
            out["thunk"] |= p["thunk"]
            label = p["label"]
            if label and not any(label in s for s in symbols):
                if out["name"] is None:
                    out["name"] = label  # createLabel renames the DEFAULT-named function
                else:
                    out["labels"].append(label)
                symbols.append(label)
    return out


# --- the plan ----------------------------------------------------------------------------------

def load_names_plan(root: Path, path: Path) -> dict:
    full = root / path
    if not full.is_file():
        raise Refused(f"{path.as_posix()} is missing: run python tools/release/names.py --plan --all")
    plan = json.loads(full.read_text(encoding="utf-8"))
    if plan.get("kind") != nm.PLAN_KIND or plan.get("selection") != "--all":
        raise Refused(f"{path.as_posix()} is not a names plan of the whole map")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if nm.sha256_text(nm.canonical(body)) != plan.get("plan_sha256"):
        raise Refused(f"{path.as_posix()} does not match its plan_sha256")
    if plan.get("function_map_sha256") != nm.current_map_sha(root):
        raise Refused(f"{path.as_posix()} was made from another function map: rerun names.py --plan --all")
    return plan


def jump_index(image, end: int) -> dict[int, list[int]]:
    """Every j and unconditional b of the text by target (instruction or not; the model decides)."""

    index: dict[int, list[int]] = {}
    for pc in range(image.base, min(end, image.end - 4), 4):
        word = image.word(pc)
        if mips.is_j(word):
            index.setdefault(mips.jump_target(word, pc), []).append(pc)
        elif mips.is_unconditional_branch(word) and not createflow.is_call(word) \
                and mips.branch_target(word, pc) is not None:
            index.setdefault(mips.branch_target(word, pc), []).append(pc)
    return index


class CodeCache:
    """``audit_global`` per word, cached, three clients in parallel when asked in bulk."""

    def __init__(self, bridge):
        self.bridge, self.known = bridge, {}

    def __call__(self, address: int) -> bool:
        if address not in self.known:
            self.known[address] = is_code_live(self.bridge, address)
        return self.known[address]

    def fill(self, addresses) -> None:
        todo = sorted(set(addresses) - set(self.known))
        clients = self.bridge.clones(3)
        if len(clients) == 1 or len(todo) < 16:
            for a in todo:
                self(a)
            return
        parts = [todo[i::len(clients)] for i in range(len(clients))]
        with ThreadPoolExecutor(len(clients)) as pool:
            for part in pool.map(lambda p: [(a, is_code_live(p[0], a)) for a in p[1]], zip(clients, parts)):
                self.known.update(part)


def describe_now(model: Model, start: int, size: int, refs: list[str]) -> dict:
    states = Counter(model.state(a) for a in range(start, start + size, 4))
    if states.get("data"):
        types = sorted({d[2] for d in model.data if d[0] < start + size and d[0] + d[1] > start})
        what = "defined data (" + ", ".join(types) + ")"
    elif states.get("code") and states.get("undefined"):
        what = "partly instructions"
    elif states.get("code"):
        what = "instructions, no function"
    else:
        what = "undefined bytes"
    return {"what": what, "words": dict(sorted(states.items())), "references": refs,
            "zero_words": sum(1 for a in range(start, start + size, 4) if model.image.word(a) == 0)}


def static_needs(model: Model, start: int, size: int, starts: set[int],
                 in_text=lambda address: True) -> tuple[set[int], list[str], list[dict]]:
    """Addresses that must be functions before this start is disassembled; reasons to withhold; references."""

    end, needs, why, refs = start + size, set(), [], []
    for pc in range(start, end, 4):
        found = flow_targets(model.image.word(pc), pc)
        if not found:
            continue
        kind, target = found
        if kind == "call" and target == pc + 8:
            continue  # FunctionAnalyzer.fallthroughCall
        if kind == "call" and target == start:
            why.append(f"calls itself at {hx(pc)}: Subroutine References would create it right after the disassembly")
        elif kind == "call" and start < target < end:
            why.append(f"calls into its own extent at {hx(target)}: analysis would create a function there")
        elif kind != "call" and start <= target < end:
            continue
        elif target in model.functions:
            continue
        elif target in starts:
            needs.add(target)
        elif kind == "call":
            why.append(f"calls {hx(target)}, which is no function and no map start (analysis would make one there)")
        else:
            why.append(f"the {kind} at {hx(pc)} leaves the extent to {hx(target)}, which is no function entry")
    for pc, target in lui_references(model.image.word, start, end):
        if not model.image.contains(target) or target in model.functions:
            continue
        state = model.state(target)
        refs.append({"at": hx(pc), "address": hx(target), "state": state})
        owner = next((s for s in starts if s <= target < s + starts[s]), None) if state == "undefined" else None
        if owner is not None and owner != start:
            needs.add(owner)  # that start first: its code is there then, and nothing is found
        # other undefined targets: what the Reference analyzer makes there is predicted per step
    return needs, why, refs


def classify_boundary(entry: dict, model: Model, names_plan: dict) -> dict:
    """What a map function whose Ghidra body differs needs, when no create of this plan fixes it."""

    address, end = int(entry["address"], 16), int(entry["end"], 16)
    live, b = entry.get("live") or {}, entry["boundary"]
    hi = int(b["ghidra_end"], 16)
    if live.get("thunk") and hi - address == 7:
        return {"decision": "cannot", "reason": (
            f"Ghidra made a thunk of the first 8 bytes (an unconditional branch over its delay slot) and the "
            f"function {live.get('thunk_target')} of the rest; the map's layout needs both removed and a create with "
            "an explicit body: create_function has no body parameter (CreateFunctionCmd.resolveThunk makes the "
            "thunk again) and this tool removes nothing")}
    if "ghidra_lowest" not in b and hi > end and all(model.image.word(a) == 0 for a in range(end + 1, hi + 1, 4)):
        return {"decision": "accept", "accepted": {"kind": "padding", "range": [hx(end + 1), hx(hi)],
                                                   "why": "the body takes the padding (nop) after a call that falls through"},
                "reason": "body differs from the map by padding only"}
    if "ghidra_lowest" not in b and hi < end:
        last = model.image.word(hi - 3)
        if last in TERMINATORS or (has_delay(model.image.word(hi - 7)) and not falls_through(model.image.word(hi - 7))) \
                or not falls_through(last):
            return {"decision": "accept", "accepted": {"kind": "unreachable", "ranges": [[hx(hi + 1), hx(end)]],
                                                       "why": "the map's last words follow an instruction without "
                                                              "fall-through (unreachable); a create cannot add them"},
                    "reason": "body differs from the map by unreachable words at its end only"}
    return {"decision": "cannot", "reason": "no create makes Ghidra's body equal the map's extent"}


def build_plan(root: Path, bridge, names_path: Path = NAMES_PLAN, progress=None, image=None,
               patterns_path: Path | None = None, patterns: dict | None = None) -> dict:
    check = nm.preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    say = progress or (lambda m: None)
    rows, _, map_sha = nm.load_map(root)
    names_plan = load_names_plan(root, names_path)
    image = image or elfimage.load(root / nm.RELEASE_ELF, "release")
    functions = read_functions(bridge)
    planned_entries = {int(e["address"], 16) for e in names_plan["entries"] if e["function"] in ("exists", "boundary")}
    planned_entries |= {int(g["address"], 16) for g in names_plan["ghidra_only"]}
    if planned_entries != set(functions):
        diff = sorted(planned_entries ^ set(functions))[:5]
        raise Refused(f"the names plan does not describe the live function list ({', '.join(map(hx, diff))}..): "
                      "rerun names.py --plan --all")
    gaps, bookmarks, data = read_gaps(bridge), read_bookmarks(bridge), read_data(bridge)
    say(f"{len(functions)} functions, {len(gaps)} gaps, {len(bookmarks)} bookmarks, {len(data)} data items")
    spans, noreturn = {}, set()
    for e in names_plan["entries"]:
        live = e.get("live") or {}
        if e["function"] in ("exists", "boundary"):
            lo = int((e.get("boundary") or {}).get("ghidra_lowest", e["address"]), 16)
            spans[int(e["address"], 16)] = (lo, int(live["body_max"], 16))
            if live.get("noreturn"):
                noreturn.add(int(e["address"], 16))
    for g in names_plan["ghidra_only"]:
        d = nm.read_function(bridge, gb.RELEASE_PROGRAM, int(g["address"], 16))
        spans[d["entry"]] = (d["body_min"], d["body_max"])
        if d["noreturn"]:
            noreturn.add(d["entry"])
    code = CodeCache(bridge)
    model = Model(image, functions, spans, noreturn, gaps, data, code)
    if patterns is None:
        path = patterns_path or default_patterns()
        if path is None or not Path(path).is_file():
            raise Refused("the R5900 function-start pattern file (r5900_LE_patterns.xml of the Emotion Engine "
                          "Reloaded extension) was not found: pass --patterns or set SOCOM_R5900_PATTERNS")
        patterns = load_patterns(Path(path))
    model.patterns = patterns
    ref_types: dict[int, list[str]] = {}

    def refs_to(address: int) -> list[str]:
        if address not in ref_types:
            ref_types[address] = [line.rsplit("[", 1)[-1].rstrip("]") for line in references_to(bridge, address)]
        return ref_types[address]

    model.refs_to = refs_to
    text_end = max(r["release_address"] + r["release_size"] for r in rows if r["release_address"] is not None)
    index = jump_index(image, text_end)
    extents = sorted((r["release_address"], r["release_address"] + r["release_size"]) for r in rows
                     if r["release_address"] is not None)
    starts_of = [a for a, _ in extents]

    def in_text(address: int) -> bool:
        """Inside a map function's extent (the release has data between its code areas)."""

        i = bisect.bisect_right(starts_of, address) - 1
        return i >= 0 and extents[i][0] <= address < extents[i][1]
    cases = [e for e in names_plan["entries"] if e["function"] in CASES]
    starts = {int(e["address"], 16): e["size"] for e in cases if e["function"] == "no-instruction"}
    # words whose state the model asks for: every extent, its padding, and the words around
    wanted = set()
    for e in cases:
        a, n = int(e["address"], 16), e["size"]
        wanted |= {w for w in range(a - 8, a + n + 0x44, 4) if model.gap_of(w) and model.gap_flags[model.gap_of(w)][1]}
    say(f"reading {len(wanted)} words in gaps with orphaned instructions")
    code.fill(wanted)
    jumps: dict[int, list[int]] = {}

    by_address = {e["address"]: e for e in names_plan["entries"]}
    out: dict[str, dict] = {}
    pending: dict[int, dict] = {}
    for e in cases:
        a, n = int(e["address"], 16), e["size"]
        item = {"address": e["address"], "size": n, "end": e["end"], "case": e["function"], "class": e["class"],
                "prototype_name": (e.get("prototype") or {}).get("name"),
                "module": e["module"], "source_pair": e["source_pair"], "steps": [], "after": [],
                "decision": None, "reason": ""}
        out[e["address"]] = item
        if e["function"] == "no-instruction":
            item["now"] = describe_now(model, a, n, extent_references(bridge, a, n))
            needs, why, refs = static_needs(model, a, n, starts, in_text)
            item["now"]["constant_references"] = refs
            if why:
                item.update(decision="withheld", reason=why[0])
                continue
            pending[a] = {"needs": needs, "item": item}
        elif e["function"] in ("create-withheld", "create"):
            item["now"] = describe_now(model, a, n, extent_references(bridge, a, n))
            item["names_reason"] = (e.get("create") or {}).get("reason")
            pending[a] = {"needs": set(), "item": item}  # create only: its code is there (in part)
        elif e["function"] == "inside":
            inside = e["live"]["inside"]
            container = int(inside["entry"], 16)
            item["now"] = {"what": f"inside the body of {inside['name']} ({inside['entry']}, "
                                   f"{inside['body_min']}..{inside['body_max']})", "container": inside["entry"]}
            pending[a] = {"needs": set(), "item": item, "container": container}
        else:
            item["now"] = {"what": f"Ghidra body {e['boundary'].get('ghidra_lowest', e['address'])}.."
                                   f"{e['boundary']['ghidra_end']}, map {e['address']}..{e['end']}",
                           "thunk": (e.get("live") or {}).get("thunk", False)}
    # Containers of the inside cases: their bodies word by word (get_function_by_address per word).
    containers = sorted({p["container"] for p in pending.values() if "container" in p})
    cut_by = {p["container"]: a for a, p in pending.items() if "container" in p}
    for c in containers:
        lo, hi = model.spans[c]
        # functions that lie wholly inside the container's span own their own words
        covered = sorted([model.spans[f] for f in model.order
                          if f != c and lo <= model.spans[f][0] and model.spans[f][1] <= hi]
                         + [g for g in model.gaps if g[1] >= lo and g[0] <= hi])
        members, at = [], lo
        for c_lo, c_hi in covered + [(hi + 1, hi + 1)]:
            members += range(at - at % 4, min(c_lo, hi + 1), 4) if c_lo > at else []
            at = max(at, c_hi + 1)
        say(f"reading the body of {hx(c)} ({len(members)} words outside other functions)")
        owners = owners_of(bridge, members)
        body = {w for w, o in owners.items() if o == c}
        if body:
            model.set_body(c, body)
    # computed jumps in the scanned neighbourhoods: their resolved targets
    for c in containers:
        lo, hi = model.spans[c]
        for pc in range(lo, hi + 1, 4):
            w = image.word(pc)
            if mips.is_jr(w) and w != mips.JR_RA and pc in model.bodies[c]:
                jumps[pc] = nm.jump_targets(bridge, pc)

    say(f"ordering {len(pending)} starts")
    order: list[str] = []
    rounds = 0
    while pending and rounds < 10000:
        rounds += 1
        ready = sorted(a for a, p in pending.items() if all(n in model.functions for n in p["needs"]))
        if not ready:
            reasons = {}
            for a, p in sorted(pending.items()):
                missing = sorted(n for n in p["needs"] if n not in model.functions)
                blocked = [n for n in missing if n not in pending]
                reasons[a] = (f"needs {hx(blocked[0])} first, which is withheld" if blocked else
                              f"needs {', '.join(map(hx, missing[:3]))} first, which wait in turn (a cycle)")
            for a, reason in reasons.items():
                pending[a]["item"].update(decision="withheld", reason=reason)
            break
        moved = False
        for a in ready:
            p = pending[a]
            if any(n not in model.functions for n in p["needs"]):
                continue
            # A start in a gap of another function's span: batch 1 showed analysis then reworks that
            # function, so it waits for the create that cuts the span, or is withheld.
            spanned = [f for f in model.order if f < a and f != p.get("container")
                       and model.spans[f][0] <= a <= model.spans[f][1]
                       and a not in model.bodies.get(f, ())][:1]
            if spanned and spanned[0] in cut_by and cut_by[spanned[0]] in pending:
                p["needs"].add(cut_by[spanned[0]])
                moved = True
                continue
            if spanned:
                del pending[a]
                moved = True
                p["item"].update(decision="withheld", reason=(
                    f"hole: lies in a gap of the body of the function at {hx(spanned[0])} (between its entry and its "
                    f"end {hx(model.spans[spanned[0]][1])}), and no create of this plan cuts that body"))
                continue
            trial = model.copy()
            result = plan_entry(trial, a, p["item"], index, jumps)
            need = result.pop("needs_function", None)
            if need is not None and need != a and need in pending and need not in p["needs"]:
                p["needs"].add(need)
                moved = True
                continue
            del pending[a]
            moved = True
            if result.get("withheld"):
                p["item"].update(decision="withheld", reason=result["withheld"])
                continue
            model = trial
            p["item"].update(decision="planned", steps=result["steps"], order=len(order) + 1,
                             after=sorted(hx(n) for n in p["needs"]))
            order.append(p["item"]["address"])
        if not moved:
            break
    for a, p in pending.items():
        if p["item"]["decision"] is None:
            p["item"].update(decision="withheld", reason="no order found")
    # the boundary entries: fixed by a planned create, accepted, or not possible
    for e in cases:
        if e["function"] != "boundary":
            continue
        item = out[e["address"]]
        a = int(e["address"], 16)
        fixed = [o for o in order for s in out[o]["steps"] for c in s.get("cuts", []) if c["function"] == e["address"]]
        if fixed:
            step = next(s for s in out[fixed[0]]["steps"] if s["kind"] == "create")
            after = next(c["after"] for c in step["cuts"] if c["function"] == e["address"])
            equal = after == [[e["address"], e["end"]]]
            item.update(decision="fixed-by-create" if equal else "withheld",
                        reason=(f"the create at {fixed[0]} cuts its body to {after}" + ("" if equal else
                                ", which is not the map's extent")), fixed_by=fixed[0])
        else:
            item.update(classify_boundary(e, model, names_plan))
            inner = [x for x in out.values() if x["case"] == "inside" and x["now"].get("container") == e["address"]]
            if inner and item["decision"] == "cannot":
                item["reason"] = f"the create at {inner[0]['address']} that would cut it is withheld: {inner[0]['reason']}"
    for item in out.values():  # which map function each predicted piece of found code belongs to
        for st in item["steps"]:
            for f in st.get("found_code", []):
                t = int(f["target"], 16)
                i = bisect.bisect_right(starts_of, t) - 1
                row = extents[i][0] if i >= 0 and extents[i][0] <= t < extents[i][1] else None
                f["map_row"] = hx(row) if row is not None else None
                f["map_row_state"] = (out[hx(row)]["decision"] if row is not None and hx(row) in out else
                                      "has a function" if row in functions else "no map function")
    plan = {
        "kind": PLAN_KIND, "schema_version": PLAN_SCHEMA, "program": gb.RELEASE_PROGRAM,
        "program_path": gb.RELEASE_PATH, "release_sha256": RELEASE_SHA256, "prototype_sha256": PROTOTYPE_SHA256,
        "function_map_sha256": map_sha, "names_plan_sha256": names_plan["plan_sha256"],
        "baseline": fingerprint(functions, gaps, bookmarks, data),
        "patterns": {"file": patterns["file"], "sha256": patterns["sha256"], "used": len(patterns["patterns"])},
        "order": order, "entries": [out[k] for k in sorted(out, key=lambda k: int(k, 16))],
    }
    plan["summary"] = summarize(plan)
    plan["plan_sha256"] = nm.sha256_text(nm.canonical(plan))
    return plan


def owners_of(bridge, words: list[int]) -> dict[int, int | None]:
    """The function each word belongs to (``get_function_by_address`` answers the containing one)."""

    def read(client, part):
        out = {}
        for w in part:
            d = nm.read_function(client, gb.RELEASE_PROGRAM, w)
            out[w] = d["entry"] if d else None
        return out

    clients = bridge.clones(3)
    if len(clients) == 1:
        return read(bridge, words)
    parts = [words[i::len(clients)] for i in range(len(clients))]
    owners: dict[int, int | None] = {}
    with ThreadPoolExecutor(len(clients)) as pool:
        for part in pool.map(lambda p: read(*p), zip(clients, parts)):
            owners.update(part)
    return owners


def plan_entry(model: Model, start: int, item: dict, index: dict, jumps: dict) -> dict:
    """The steps of one entry and their predictions, on ``model`` (changed when planned)."""

    size = item["size"]
    end = start + size
    steps = []
    if item["case"] == "no-instruction":
        dis = simulate_disassembly(model, start, end)
        if dis["error"]:
            return {"withheld": dis["error"]}
        stop = end
        if dis["overrun"]:
            pad = dis["overrun"]
            zeros = 0
            while zeros < len(pad) and pad[zeros] == end + 4 * zeros and model.image.word(pad[zeros]) == 0:
                zeros += 1
            if zeros < len(pad):
                return {"withheld": f"its last instruction falls through past its end into {hx(end + 4 * zeros)}, "
                                    "which is no instruction yet: the disassembly would run on into it",
                        "needs_function": end + 4 * zeros}
            stop = end + 4 * len(pad)
            if stop not in model.functions:
                return {"withheld": f"falls through padding into {hx(stop)}, which is no function entry",
                        "needs_function": stop}
        already = sorted(a for a in range(start, stop, 4) if model.state(a) == "code")
        model.disassembled(dis["new"])
        operands = operand_effects(model, start, end)
        if operands["errors"]:
            return {"withheld": operands["errors"][0]}
        for f in operands["found"]:  # orphan code the Reference analyzer makes; no function
            model.disassembled(words_of(f["instructions"]))
        data_refs = [d["address"] for d in operands["data"]]
        # SharedReturnJumpAnalyzer (an instruction analyzer) runs SharedReturnAnalysisCmd for every
        # function entry a new jump or branch reaches: unconditional jumps to it become call-returns
        # and its neighbourhood is scanned for jumps that cross a function.
        targets = sorted({t for pc in dis["new"] if (f := flow_targets(model.image.word(pc), pc))
                          and f[0] != "call" and (t := f[1]) in model.functions})
        after_dis = shared_return(model, targets, index, jumps, frozenset(targets), sources=dis["new"])
        if after_dis["creates"]:
            c = after_dis["creates"][0]
            return {"withheld": f"after its disassembly analysis would create a function at {c['at']}: the jump at "
                                f"{c['jump']} crosses a function (Shared Return Calls)",
                    "needs_function": int(c["at"], 16)}
        calls = sorted(pc for pc in dis["new"] if (f := flow_targets(model.image.word(pc), pc)) and f[0] == "call")
        steps.append({"kind": "disassemble", "start": hx(start), "end_exclusive": hx(stop),
                      "instructions": ranges(set(range(start, stop, 4))), "new": ranges(dis["new"]),
                      "already_instructions": ranges(already), "padding": ranges(dis["overrun"]) if dis["overrun"] else [],
                      "may_define_data_at": sorted(set(data_refs)),
                      "operand_references": operands["data"],
                      "found_code": operands["found"],
                      "overrides": [{"at": hx(s), "to": hx(d)} for s, d in after_dis["overrides"]],
                      "callees": sorted({hx(flow_targets(model.image.word(pc), pc)[1]) for pc in calls}),
                      "returns_after_calls": [hx(pc + 8) for pc in calls if start <= pc + 8 < stop]})
    effects = pattern_effects(model.image, start, getattr(model, "patterns", None))
    if effects["thunk"]:
        return {"withheld": "a function-start pattern (thunk=\"true\") would make it a thunk of a target the plan "
                            "cannot predict"}
    result = simulate_create(model, start, size, index, jumps)
    if result.get("withheld"):
        return result
    body = result["body"]
    default = model.functions[start]["name"]
    if effects["name"] and not result["thunk_of"]:
        model.functions[start]["name"] = effects["name"]  # what later predictions see
    steps.append({"kind": "create", "address": hx(start), "body": ranges(body),
                  "body_lowest": hx(min(body)), "body_highest": hx(max(body) + 3),
                  "accepted": result["accepted"], "thunk_of": hx(result["thunk_of"]) if result["thunk_of"] else None,
                  "name": default, "cuts": result["cuts"], "overrides": result["overrides"],
                  "signature": f"undefined {default}(void)" if not result["thunk_of"] else None,
                  "analysis_name": effects["name"], "analysis_labels": effects["labels"],
                  "pattern_thunk": effects["thunk"],
                  # jr other than jr ra: Decompiler Switch Analysis would add jump references to them
                  "computed_jumps": [hx(pc) for pc in sorted(body) if mips.is_jr(model.image.word(pc))
                                     and model.image.word(pc) != mips.JR_RA and not jumps.get(pc)]})
    return {"withheld": None, "steps": steps}


def withheld_group(reason: str) -> str:
    for key, group in (("thunk", "Ghidra thunk split (needs a delete)"), ("padding only", "accepted: padding"),
                       ("unreachable words", "accepted: unreachable tail"), ("cycle", "creates that need each other"),
                       ("withheld", "needs a withheld start"), ("delay slot", "delay slot is another function's entry"),
                       ("Shared Return", "analysis would create another function"), ("calls", "calls a non-function"),
                       ("leaves the extent", "jumps out of its extent"), ("falls through", "falls through past its end"),
                       ("do not decode", "bytes that do not decode"), ("defined data", "defined data"),
                       ("does not reach", "unreachable part"), ("did not read", "overlap")):
        if key in reason:
            return group
    return "other"


def summarize(plan: dict) -> dict:
    entries = plan["entries"]
    planned = [e for e in entries if e["decision"] == "planned"]
    steps = Counter(s["kind"] for e in planned for s in e["steps"])
    return {
        "entries": len(entries),
        "by_case": dict(sorted(Counter(e["case"] for e in entries).items())),
        "by_decision": dict(sorted(Counter(e["decision"] for e in entries).items())),
        "by_case_and_decision": dict(sorted(Counter(f"{e['case']} / {e['decision']}" for e in entries).items())),
        "steps": dict(sorted(steps.items())),
        "accepted_differences": dict(sorted(Counter(
            s["accepted"]["kind"] for e in planned for s in e["steps"] if s.get("accepted")).items())),
        "planned_bytes": sum(e["size"] for e in planned),
        "withheld_by_group": dict(sorted(Counter(
            withheld_group(e["reason"]) for e in entries if e["decision"] in ("withheld", "cannot")).items())),
        "now": dict(sorted(Counter(e["now"]["what"] for e in entries if e["case"] == "no-instruction").items())),
        "referenced": sum(1 for e in entries if e["case"] == "no-instruction" and e["now"]["references"]),
        "predicted_cuts": sum(len(s.get("cuts", [])) for e in planned for s in e["steps"]),
        "predicted_overrides": sum(len(s.get("overrides", [])) for e in planned for s in e["steps"]),
        "thunks": sum(1 for e in planned for s in e["steps"] if s.get("thunk_of")),
        "may_define_data": sum(len(s.get("may_define_data_at", [])) for e in planned for s in e["steps"]),
        "found_code_predicted": sum(len(s.get("found_code", [])) for e in planned for s in e["steps"]),
        "operand_references_to_undefined": sum(len(s.get("operand_references", [])) + len(s.get("found_code", []))
                                               for e in planned for s in e["steps"]),
        "overrides_after_disassembly": sum(len(s.get("overrides", [])) for e in planned for s in e["steps"]
                                           if s["kind"] == "disassemble"),
        "analysis_names": {
            "entries": sum(1 for e in planned for s in e["steps"] if s.get("analysis_name")),
            "equal_to_prototype": sum(1 for e in planned for s in e["steps"]
                                      if s.get("analysis_name") and s["analysis_name"] == e.get("prototype_name")),
            "second_labels": sum(len(s.get("analysis_labels", [])) for e in planned for s in e["steps"]),
            "second_label_equal_to_prototype": sum(1 for e in planned for s in e["steps"]
                                                   if e.get("prototype_name") in s.get("analysis_labels", [])),
        },
    }


def plan_markdown(plan: dict) -> str:
    s = plan["summary"]
    lines = [f"# Function starts plan", "",
             f"Program `{plan['program']}`; function map sha256 `{plan['function_map_sha256'][:16]}`; names plan "
             f"`{plan['names_plan_sha256'][:16]}`; plan sha256 `{plan['plan_sha256']}`.", "",
             f"- entries: {s['entries']}; by case: {s['by_case']}",
             f"- decisions: {s['by_case_and_decision']}",
             f"- steps: {s['steps']}; planned bytes: {s['planned_bytes']}; accepted differences: "
             f"{s['accepted_differences']}",
             f"- predicted container cuts: {s['predicted_cuts']}; predicted jump-to-call overrides: "
             f"{s['predicted_overrides']}; thunks: {s['thunks']}; data the new code references, undefined now: "
             f"{s['may_define_data']}",
             f"- what is at the no-instruction starts now: {s['now']}; referenced from elsewhere: {s['referenced']}",
             f"- withheld or not possible, by group: {s['withheld_by_group']}",
             f"- jumps turned into calls after a disassembly: {s['overrides_after_disassembly']}",
             f"- names the function-start patterns give ({plan['patterns']['file']}): {s['analysis_names']}", "",
             "## Names Ghidra's analysis gives at the create (accepted, recorded; names.py decides later)", "",
             "| start | analysis name | second labels | prototype name |", "|---|---|---|---|"]
    for e in plan["entries"]:
        for st in e["steps"]:
            if st.get("analysis_name"):
                lines.append(f"| {e['address']} | {st['analysis_name']} | {', '.join(st['analysis_labels']) or '-'} | "
                             f"{e.get('prototype_name') or '-'} |")
    lines += ["", "## What the new code points to that is undefined now (Reference analyzer)", "",
              "| start | instruction | target | predicted effect | map function there |", "|---|---|---|---|---|"]
    for e in plan["entries"]:
        for st in e["steps"]:
            for f in st.get("found_code", []):
                lines.append(f"| {e['address']} | {f['by']} | {f['target']} | found code {f['instructions']}, bookmark "
                             f"Found Code | {f['map_row'] or '-'} ({f['map_row_state']}) |")
            for d in st.get("operand_references", []):
                lines.append(f"| {e['address']} | {d['by']} | {d['address']} | data may be defined ({d['access']}: "
                             "string, unicode or pointer) | - |")
    lines += ["", "## Not planned", ""]
    for e in plan["entries"]:
        if e["decision"] != "planned":
            lines.append(f"- {e['address']} ({e['size']} bytes, {e['case']}, {e['class']}): {e['decision']}: "
                         f"{e['reason']}")
    lines += ["", "## Planned, in order", "",
              "| # | start | bytes | case | steps | body | accepted | other changes |", "|---|---|---|---|---|---|---|---|"]
    for address in plan["order"]:
        e = next(x for x in plan["entries"] if x["address"] == address)
        create = next(st for st in e["steps"] if st["kind"] == "create")
        other = [f"cut {c['function']} to {c['after']}" for c in create["cuts"]] + \
                [f"{o['at']} jump to call" for o in create["overrides"]]
        acc = create["accepted"]["kind"] if create["accepted"] else "-"
        lines.append(f"| {e['order']} | {address} | {e['size']} | {e['case']} | "
                     f"{'+'.join(st['kind'] for st in e['steps'])} | {create['body_lowest']}..{create['body_highest']} | "
                     f"{acc} | {'; '.join(other) or '-'} |")
    return "\n".join(lines) + "\n"


def write_plan(root: Path, plan: dict) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{PLAN_STEM}.json").write_text(nm.canonical(plan), encoding="utf-8", newline="\n")
    (out / f"{PLAN_STEM}.md").write_text(plan_markdown(plan), encoding="utf-8", newline="\n")
    return out / f"{PLAN_STEM}.json"


def load_plan(path: Path, root: Path) -> dict:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("kind") != PLAN_KIND or plan.get("schema_version") != PLAN_SCHEMA:
        raise Refused(f"{path.name} is not a schema {PLAN_SCHEMA} function starts plan")
    if plan.get("program") != gb.RELEASE_PROGRAM:
        raise Refused(f"the plan targets {plan.get('program')!r}; writes go to {gb.RELEASE_PROGRAM} only")
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if nm.sha256_text(nm.canonical(body)) != plan.get("plan_sha256"):
        raise Refused(f"{path.name} does not match its plan_sha256: regenerate it instead of editing it")
    if plan.get("function_map_sha256") != nm.current_map_sha(root):
        raise Refused(f"{path.name} was made from another {nm.MAP_TSV.as_posix()}: replan")
    return plan


# --- the apply ---------------------------------------------------------------------------------

def full_snapshot(bridge) -> dict[int, dict]:
    """Every release function: name, thunk, body lowest/highest, signature line, no-return."""

    listed = read_functions(bridge)

    def read(client, part):
        out = {}
        for a in part:
            d = nm.read_function(client, gb.RELEASE_PROGRAM, a)
            if not d or d["entry"] != a:
                raise gb.BridgeError(f"function {hx(a)} is listed but does not read back")
            out[a] = {"name": d["name"], "thunk": listed[a]["thunk"], "lo": d["body_min"], "hi": d["body_max"],
                      "signature": d.get("signature"), "noreturn": d["noreturn"]}
        return out

    addresses = sorted(listed)
    clients = bridge.clones(3)
    if len(clients) == 1:
        return read(bridge, addresses)
    parts = [addresses[i::len(clients)] for i in range(len(clients))]
    snap: dict[int, dict] = {}
    with ThreadPoolExecutor(len(clients)) as pool:
        for part in pool.map(lambda p: read(*p), zip(clients, parts)):
            snap.update(part)
    return snap


def compare_snapshots(before: dict, after: dict, expected_changes: dict) -> list[dict]:
    """Differences between two full snapshots that ``expected_changes`` (entry -> fields) does not explain."""

    out = []
    for a in sorted(set(before) | set(after)):
        old, new, want = before.get(a), after.get(a), expected_changes.get(a)
        if new is None:
            out.append({"address": hx(a), "change": "vanished"})
            continue
        base = dict(old or {})
        if want:
            base.update(want)
        if old is None and not want:
            out.append({"address": hx(a), "change": "appeared", "name": new["name"]})
            continue
        for key in ("name", "thunk", "lo", "hi", "signature", "noreturn"):
            if key in base and base[key] != new[key]:
                out.append({"address": hx(a), "change": key, "expected": base[key], "found": new[key]})
    return out


class Applier:
    def __init__(self, bridge, plan: dict, image, dry_run: bool, batch: int | None, only=frozenset()):
        self.bridge, self.plan, self.image, self.dry_run, self.batch = bridge, plan, image, dry_run, batch
        self.only = set(only)  # a pilot: these entries only, in plan order
        self.written: list[dict] = []
        self.attempted: list[dict] = []
        self.would: list[dict] = []
        self.analysis_changes: list[dict] = []
        self.remove_by_hand: list[dict] = []
        self.done_entries = 0
        self.batch_full = False
        self.expected: dict[int, dict] = {}  # full-snapshot fields this run changes
        self.data_defined: list[dict] = []
        self.checked: Counter = Counter()

    def record(self, entry, applied, value, end):
        item = {"address": entry["address"], "applied": applied, "value": value, "source_pair": entry["source_pair"],
                "end": end}
        self.written.append(item)

    def send(self, entry, applied, value, end, endpoint, ok, **body):
        if self.dry_run:
            self.would.append({"address": entry["address"], "applied": applied, "value": value, "endpoint": endpoint,
                               "body": body})
            return None
        self.attempted.append({"address": entry["address"], "applied": applied, "value": value,
                               "source_pair": entry["source_pair"], "end": end})
        response = self.bridge.write(endpoint, gb.RELEASE_PROGRAM, **body)
        if not ok(response):
            # create_function runs inside the plugin's executeWrite, whose transaction is committed even when
            # the command fails; disassemble_bytes ends its own transaction unsuccessful (rolled back).
            held = ("the program may now hold the command's partial effects" if endpoint == "create_function"
                    else "its transaction was rolled back")
            raise StopAfter(f"{endpoint} at {entry['address']} failed ({held}): {str(response)[:300]}")
        return response

    def light(self):
        return read_functions(self.bridge), read_gaps(self.bridge), read_bookmarks(self.bridge), read_data(self.bridge)

    def run(self) -> None:
        functions, gaps, bookmarks, data = self.light()
        if fingerprint(functions, gaps, bookmarks, data) != self.plan["baseline"]:
            now = fingerprint(functions, gaps, bookmarks, data)
            changed = [k for k in ("functions", "gaps", "bookmarks", "data") if now[k] != self.plan["baseline"][k]]
            raise StopBefore(f"the program differs from the plan's baseline ({', '.join(changed)}): replan")
        self.before = full_snapshot(self.bridge)
        spans = {a: (f["lo"], f["hi"]) for a, f in self.before.items()}
        noreturn = {a for a, f in self.before.items() if f["noreturn"]}
        code = CodeCache(self.bridge)
        self.model = Model(self.image, functions, spans, noreturn, gaps, data, code)
        self.state = (functions, gaps, bookmarks, data)
        by_address = {e["address"]: e for e in self.plan["entries"]}
        for e in self.plan["entries"]:  # accepted differences of existing functions: re-read them
            if e["decision"] == "accept":
                self.accept_existing(e)
        order = self.plan["order"]
        if self.only:
            order = [a for a in order if a in self.only]
            unknown = sorted(self.only - set(order))
            if unknown:
                raise StopBefore(f"--only {unknown[0]}: not a planned entry")
            for a in order:  # every entry it needs first must be in the selection
                missing = [n for n in by_address[a]["after"] if n not in self.only]
                if missing:
                    raise StopBefore(f"--only {a} needs {missing[0]} first: add it to the selection")
        for address in order:
            if self.batch and self.done_entries >= self.batch:
                self.batch_full = True
                break
            self.entry(by_address[address])
            self.done_entries += 1

    def accept_existing(self, e):
        address = int(e["address"], 16)
        live = self.before.get(address)
        acc = e["accepted"]
        lo, hi = address, (int(acc["range"][1], 16) if acc["kind"] == "padding" else int(acc["ranges"][0][0], 16) - 1)
        if not live or live["lo"] != lo or live["hi"] != hi:
            raise StopBefore(f"{e['address']}: the accepted body {hx(lo)}..{hx(hi)} does not read back "
                             f"({live and (hx(live['lo']), hx(live['hi']))}): replan")
        # Nothing is written or recorded for it: the plan is the record of the decision (a row would
        # read back after a close without saving too, and --discard-unsaved could never drop it).
        self.checked["accepted as is"] += 1

    def entry(self, e):
        start, end = int(e["address"], 16), int(e["end"], 16)
        live = nm.read_function(self.bridge, gb.RELEASE_PROGRAM, start)
        if e["case"] == "inside":
            container = int(e["now"]["container"], 16)
            if not live or live["entry"] != container:
                raise StopBefore(f"{e['address']} no longer lies in the function at {e['now']['container']}: replan")
        elif live:
            raise StopBefore(f"{e['address']}: a function {live['name']} ({hx(live['entry'])}) holds it now: replan")
        for step in e["steps"]:
            if step["kind"] == "disassemble":
                self.disassemble(e, step)
            else:
                self.create(e, step)

    def disassemble(self, e, step):
        start, stop = int(step["start"], 16), int(step["end_exclusive"], 16)
        new = words_of(step["new"])
        # The code-unit state of every word of the range and AROUND words on each side, read before.
        around = range(start - AROUND, stop + AROUND, 4)
        before = {a: is_code_live(self.bridge, a) for a in around if self.image.contains(a)}
        for a in sorted(new):
            if before.get(a):
                raise StopBefore(f"{e['address']}: {hx(a)} holds an instruction already: replan")
        response = self.send(e, "disassemble", f"{hx(start)}-{hx(stop - 1)}", hx(stop - 1), "disassemble_bytes",
                             lambda r: isinstance(r, dict) and r.get("success") is True,
                             start_address=hx(start), end_address=hx(stop), restrict_to_execute_memory=False)
        self.model.disassembled(new)
        if response is None:
            return
        listed = {int(i["address"], 16) for i in response.get("instructions", [])}
        want = words_of(step["instructions"])
        if listed != want:
            extra, gone = sorted(listed - want), sorted(want - listed)
            raise StopAfter(f"disassembly at {e['address']} made instructions {ranges(listed)}, predicted "
                            f"{step['instructions']} (extra {[hx(a) for a in extra[:3]]}, missing "
                            f"{[hx(a) for a in gone[:3]]})")
        nm.settle(self.bridge)
        # Code the Reference analyzer may find where the new code points: all of it, or none of it.
        found_words, bookmarks = set(), set()
        for f in step.get("found_code", []):
            words = words_of(f["instructions"])
            made = [a for a in sorted(words) if is_code_live(self.bridge, a)]
            if made and len(made) != len(words):
                raise StopAfter(f"after the disassembly at {e['address']} the Reference analyzer made {len(made)} of the "
                                f"{len(words)} predicted instructions at {f['target']} ({f['instructions']})")
            if made:
                found_words |= words
                bookmarks.add((int(f["bookmark"][0], 16), *f["bookmark"][1:]))
                self.model.disassembled(words)
                lo, hi = min(words), max(words) + 3
                self.record({**e, "address": f["target"]}, "found-code-by-analysis",
                            f"{hx(lo)}-{hx(hi)}: from {f['by']} in {e['address']}; bookmark Found Code", hx(hi))
                self.checked["code found by the Reference analyzer"] += 1
            else:
                self.checked["predicted found code not made"] += 1
        moved = [a for a, was in before.items()
                 if is_code_live(self.bridge, a) != (was or a in new or a in found_words)]
        if moved:
            raise StopAfter(f"after the disassembly at {e['address']} the code-unit state differs from the "
                            f"prediction at {', '.join(hx(a) for a in moved[:5])}")
        self.record(e, "disassemble", f"{hx(start)}-{hx(stop - 1)}", hx(stop - 1))
        self.check_overrides(e, step)
        self.compare(e, step, allowed_data={int(a, 16) for a in step["may_define_data_at"]}, bookmarks=bookmarks)

    def labels(self, address: int) -> list[tuple[int, str]]:
        """The labels of the function at ``address`` (``get_function_documentation``, read by address)."""

        return gb.parse_documentation_labels(
            self.bridge.get("get_function_documentation", gb.RELEASE_PROGRAM, address=hx(address)), address)

    def check_overrides(self, e, step):
        """Every jump the plan says Shared Return Calls turns into a call-return shows a CALL reference to its target."""

        for o in step.get("overrides", []):
            if not calls_to(self.bridge, int(o["at"], 16), int(o["to"], 16)):
                found = flow_references(self.bridge, int(o["at"], 16))
                raise AnalysisStop(f"after the {step['kind']} at {e['address']} the jump at {o['at']} shows "
                                   f"{[(hx(a), k) for a, k in found] or 'no flow reference'}; predicted a call-return "
                                   f"to {o['to']} (Shared Return Calls)")
            self.checked["call-returns read back"] += 1

    def create(self, e, step):
        start = int(e["address"], 16)
        lo, hi = int(step["body_lowest"], 16), int(step["body_highest"], 16)
        body = words_of(step["body"])
        response = self.send(e, "create", f"{hx(lo)}-{hx(hi)}", hx(hi), "create_function", gb.ok_create,
                             address=e["address"], disassemble_first=False)
        thunk_of = int(step["thunk_of"], 16) if step["thunk_of"] else None
        for cut in step["cuts"]:
            other = int(cut["function"], 16)
            self.model.set_body(other, words_of(cut["after"]))
        for cut in step["cuts"]:
            for a in words_of(cut["before"]) - words_of(cut["after"]) - body:
                self.model.free(a)
        self.model.add_function(start, body, step["name"], thunk_of is not None)
        signature = step["signature"]
        if not signature and thunk_of:
            # A thunk shows its target's prototype under its OWN shown name: a default thunk of
            # FUN_0020ae80 reads "undefined thunk_FUN_0020ae80(void)" (seen in the pilot, 0x1d2780).
            target = self.before.get(thunk_of, {})
            signature = target.get("signature")
            if signature and target.get("name") and step["name"] != target["name"]:
                signature = signature.replace(f" {target['name']}(", f" {step['name']}(", 1)
        self.expected[start] = {"name": step["name"], "thunk": thunk_of is not None, "lo": lo, "hi": hi,
                                "noreturn": False, **({"signature": signature} if signature else {})}
        for cut in step["cuts"]:
            after = words_of(cut["after"])
            self.expected[int(cut["function"], 16)] = {"lo": min(after), "hi": max(after) + 3}
        if response is None:
            return
        nm.settle(self.bridge)
        back = nm.read_function(self.bridge, gb.RELEASE_PROGRAM, start)
        if not back or back["entry"] != start or (back["body_min"], back["body_max"]) != (lo, hi):
            got = "nothing" if not back else f"{hx(back['body_min'])}..{hx(back['body_max'])} ({hx(back['entry'])})"
            if back and back["entry"] == start:
                self.remove_by_hand.append({"address": e["address"], "name": back["name"], "body": got,
                                            "planned": f"{hx(lo)}..{hx(hi)}"})
            raise StopAfter(f"create {e['address']} read back {got}, predicted {hx(lo)}..{hx(hi)}")
        found = back["name"]
        by_pattern = step.get("analysis_name")
        if found == by_pattern and by_pattern and not thunk_of:
            # Function Start Search named it from its bytes (r5900_LE_patterns.xml): accepted, recorded
            signature = f"undefined {found}(void)"
            self.model.functions[start]["name"] = found
            self.expected[start].update(name=found, signature=signature)
        if found != self.model.functions[start]["name"] and not thunk_of or back["noreturn"] \
                or (signature and back.get("signature") != signature):
            raise AnalysisStop(f"create {e['address']} reads back as {found!r} {back.get('signature')!r}, "
                               f"predicted {step['name']!r}" + (f" or {by_pattern!r}" if by_pattern else "")
                               + f" {signature!r}")
        self.record(e, "create", f"{hx(lo)}-{hx(hi)}", hx(hi))
        labels = sorted(n for a, n in self.labels(start) if a == start and n != found)
        want_labels = sorted(step.get("analysis_labels", [])) if found == by_pattern else []
        if labels != want_labels:
            raise AnalysisStop(f"create {e['address']}: labels at the entry {labels}, predicted {want_labels}")
        if found == by_pattern and by_pattern:
            self.record(e, "name-by-analysis", found, hx(hi))
            for label in labels:
                self.record(e, "label-by-analysis", label, hx(hi))
            self.checked["named by Function Start Search"] += 1
        if step["accepted"]:
            acc = step["accepted"]
            self.record(e, "extent-accepted",
                        f"{hx(lo)}-{hx(hi)}: {acc['kind']} {acc.get('range') or acc.get('ranges')}", hx(hi))
        for cut in step["cuts"]:
            other = int(cut["function"], 16)
            d = nm.read_function(self.bridge, gb.RELEASE_PROGRAM, other)
            after = words_of(cut["after"])
            if not d or d["entry"] != other or (d["body_min"], d["body_max"]) != (min(after), max(after) + 3):
                raise AnalysisStop(f"after the create at {e['address']} the function at {cut['function']} reads "
                                   f"{d and (hx(d['body_min']), hx(d['body_max']))}, predicted {cut['after']}")
            self.record({**e, "address": cut["function"]}, "cut-by-analysis",
                        f"{hx(min(after))}-{hx(max(after) + 3)} (was {cut['before'][0][0]}-{cut['before'][-1][1]}; "
                        f"after the create at {e['address']})", hx(max(after) + 3))
        self.check_overrides(e, step)
        for pc in step.get("computed_jumps", []):
            found = flow_references(self.bridge, int(pc, 16))
            if found:  # the switch analysis resolved it: the body may grow later
                raise AnalysisStop(f"after the create at {e['address']} the computed jump at {pc} has flow "
                                   f"references {[(hx(a), k) for a, k in found]}; predicted none")
            self.checked["computed jumps without references"] += 1
        self.compare(e, step, allowed_data=set())

    def outside_code(self, address: int, length: int) -> bool:
        """No byte of it lies in a function's span or in the map extent of a function still to be made.

        Not "outside executable memory": the image is one executable block, so the bridge lists
        its data areas as gaps too. Every map function is either a Ghidra function (its span) or
        an entry of the plan (planned, withheld or not possible) with its map extent.
        """

        last = address + max(length, 1) - 1
        if any(lo <= last and address <= hi for lo, hi in self.model.spans.values()):
            return False
        return not any(int(x["address"], 16) <= last and address <= int(x["end"], 16) for x in self.plan["entries"])
    def compare(self, e, step, allowed_data: set[int], bookmarks: set = frozenset()):
        """Everything the bridge lists, against the model after this step (``bookmarks``: predicted, made)."""

        functions, gaps, found_bookmarks, data = self.light()
        changes = []
        want = self.model.functions
        for a in sorted(set(functions) | set(want)):
            if a not in functions:
                changes.append({"address": hx(a), "change": "vanished" if a in self.state[0] else "not created"})
            elif a not in want:
                changes.append({"address": hx(a), "change": "appeared", "name": functions[a]["name"]})
            elif functions[a]["thunk"] != want[a]["thunk"]:
                changes.append({"address": hx(a), "change": "thunk", "found": functions[a]["thunk"]})
            elif functions[a]["name"] != want[a]["name"] and not (want[a]["thunk"] or functions[a]["thunk"]):
                changes.append({"address": hx(a), "change": "name", "expected": want[a]["name"],
                                "found": functions[a]["name"]})
        expected = {(g["start"], g["end"]): g for g in self.model.expected_gaps()}
        found = {(g["start"], g["end"]): g for g in gaps}
        for key in sorted(set(expected) ^ set(found)):
            changes.append({"gap": [hx(key[0]), hx(key[1])], "change": "missing" if key in expected else "unexpected"})
        for key in sorted(set(expected) & set(found)):
            x, f = expected[key], found[key]
            for field in ("undefined", "orphans", "before", "after"):
                if x[field] is not None and x[field] != f[field]:
                    changes.append({"gap": [hx(key[0]), hx(key[1])], "change": field, "expected": x[field],
                                    "found": f[field]})
            if x["undefined"] is None or x["orphans"] is None:
                self.model.gap_flags[key] = (f["undefined"], f["orphans"])  # learnt, not predicted
                self.checked["gap flags not predicted"] += 1
        found_marks = set(found_bookmarks)
        expected_marks = set(self.state[2]) | set(bookmarks)
        if found_marks != expected_marks:
            for b in sorted(found_marks ^ expected_marks):
                changes.append({"bookmark": [hx(b[0]), b[1], b[2], b[3]],
                                "change": "added" if b in found_marks else "missing"})
        if data != self.state[3]:
            old = set(self.state[3])
            for d in sorted(set(data) ^ old):
                predicted = d[0] in allowed_data and data_kind_allowed(d[2])
                # Analysis also defines data at the offsets new code reads and writes from a base
                # (seen in batch 1: a table at 0x443ab0.., hardware registers at 0x10004004..), as
                # it did all over the program. Away from every function and every map extent still
                # to be made, that is accepted and listed; data inside code stays a stop.
                if d not in old and (predicted or self.outside_code(d[0], d[1])):
                    self.data_defined.append({"address": hx(d[0]), "length": d[1], "type": d[2],
                                              "after": e["address"], "predicted": predicted})
                elif d in old and d[2].lower().startswith("undefined") and any(
                        n not in old and n[0] <= d[0] and d[0] + d[1] <= n[0] + n[1]
                        and self.outside_code(n[0], n[1]) for n in data):
                    # An untyped item analysis itself had made, taken into a wider one the new code
                    # reads as a whole (seen in batch 4: 0x44c208, seven items become one undefined8).
                    self.data_defined.append({"address": hx(d[0]), "length": d[1], "type": d[2],
                                              "after": e["address"], "predicted": False, "replaced": True})
                else:
                    changes.append({"data": [hx(d[0]), d[1], d[2]], "change": "removed" if d in old else "added"})
        # Every function's body ends, name, signature line, thunk and no-return flags (a callee that
        # "Non-Returning Functions - Discovered" marks, a body its flow repair or switch analysis changes).
        if not changes:
            changes += [c for c in compare_snapshots(self.before, full_snapshot(self.bridge), self.expected)
                        if c.get("change") != "appeared"]  # appearances are listed above already
            self.checked["full snapshots"] += 1
        if changes:
            self.analysis_changes = [dict(c, after=f"{step['kind']} {e['address']}") for c in changes]
            raise AnalysisStop(f"after the {step['kind']} at {e['address']} the program differs from the prediction "
                               f"({len(changes)} differences, listed under analysis_changes)")
        self.state = (functions, gaps, found_bookmarks, data)
        self.model.data = data
        self.model._data_starts = [d[0] for d in data]


def reads_back(bridge, item: dict) -> bool:
    """Does the saved (or still open) program hold a row of this tool?"""

    address = int(item["address"], 16)
    if item["applied"] in ("name-by-analysis", "label-by-analysis"):
        live = nm.read_function(bridge, gb.RELEASE_PROGRAM, address)
        if not live or live["entry"] != address:
            return False
        if item["applied"] == "name-by-analysis":
            return live["name"] == item["value"]
        found = gb.parse_documentation_labels(
            bridge.get("get_function_documentation", gb.RELEASE_PROGRAM, address=hx(address)), address)
        return (address, item["value"]) in found
    lo, hi = (int(x, 16) for x in item["value"].split(" ")[0].rstrip(":").split("-"))
    if item["applied"] in ("disassemble", "found-code-by-analysis"):
        return is_code_live(bridge, lo) and is_code_live(bridge, hi - 3)
    live = nm.read_function(bridge, gb.RELEASE_PROGRAM, address)
    return bool(live) and live["entry"] == address and (live["body_min"], live["body_max"]) == (lo, hi)


def next_report(root: Path) -> Path:
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    used = [int(m.group(1)) for p in out.glob(f"{PLAN_STEM}.apply-*.json")
            if (m := re.search(r"\.apply-(\d+)\.json$", p.name))]
    return out / f"{PLAN_STEM}.apply-{max(used, default=0) + 1:03d}.json"


def apply(root: Path, plan_path: Path, bridge, *, dry_run: bool, today: str | None = None,
          batch: int | None = None, image=None, only=frozenset()) -> dict:
    plan = load_plan(plan_path, root)
    if not dry_run:
        pending = nm.unsaved(nm.read_record(root))
        if pending:
            reports = sorted({row["state"].split(" ", 1)[1] for row in pending})
            raise Refused(f"{nm.RECORD.as_posix()} holds {len(pending)} unsaved changes ({', '.join(reports)}): "
                          "save and --confirm-saved (or --discard-unsaved) first")
    check = nm.preflight(bridge)
    if not check["ok"]:
        raise Refused("preflight failed: " + "; ".join(check["errors"]))
    image = image or elfimage.load(root / nm.RELEASE_ELF, "release")
    out = (root / OUT / f"{plan_path.stem}.dry-run.json") if dry_run else next_report(root)
    applier = Applier(bridge, plan, image, dry_run, batch, only)
    stopped, kind, side_effects = None, None, []
    try:
        applier.run()
    except (nm.Stop, gb.BridgeError) as exc:
        # nm.Stop, not only this module's Stop: names.settle raises it on a timeout, and a run
        # that ends without its report can be neither confirmed nor discarded.
        stopped, kind = str(exc), getattr(exc, "kind", "stop")
    finally:
        if not dry_run and applier.written:
            nm.update_record(root, applier.written, today or _dt.date.today().isoformat(), out.name)
    if not dry_run and hasattr(applier, "before") and (applier.written or bridge.sent):
        try:
            nm.settle(bridge)
        except nm.Stop as exc:
            side_effects.append({"change": "analysis did not settle", "detail": str(exc)})
        side_effects += compare_snapshots(applier.before, full_snapshot(bridge), applier.expected)
        if side_effects and not stopped:
            stopped, kind = (f"the end-of-run snapshot differs from the prediction ({len(side_effects)} differences, "
                             "listed under side_effects)"), "analysis"
    result = {
        "plan": plan_path.name, "plan_sha256": plan["plan_sha256"], "dry_run": dry_run, "stopped": stopped,
        "stop_kind": kind, "what_to_do": WHAT_TO_DO.get(kind) if stopped else None, "saved": False, "batch": batch,
        "batch_full": applier.batch_full, "entries_done": applier.done_entries,
        "sent": [] if dry_run else bridge.sent, "written": applier.written, "would_write": applier.would,
        "attempted": [] if dry_run else applier.attempted,
        "counts": dict(sorted(Counter(w["applied"] for w in (applier.would if dry_run else applier.written)).items())),
        "analysis_changes": applier.analysis_changes, "remove_by_hand": applier.remove_by_hand,
        "data_defined_by_analysis": applier.data_defined, "side_effects": side_effects,
        "checked": dict(applier.checked),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(nm.canonical(result), encoding="utf-8", newline="\n")
    result["report"] = out.name
    return result


# --- command line ------------------------------------------------------------------------------

def parse_only(values: list[str]) -> frozenset[str]:
    """``--only`` takes hexadecimal addresses written 0x...; anything else is refused (a decimal is no address)."""

    out = set()
    for value in values:
        if not re.fullmatch(r"0x[0-9a-fA-F]+", value):
            raise Refused(f"--only {value!r}: write the start address in hexadecimal, as 0x...")
        out.add(hx(int(value, 16)))
    return frozenset(out)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="plan every map function the names step left without one")
    mode.add_argument("--apply", type=Path, metavar="PLAN")
    mode.add_argument("--confirm-saved", type=Path, metavar="REPORT")
    mode.add_argument("--discard-unsaved", type=Path, metavar="REPORT")
    parser.add_argument("--names-plan", type=Path, default=NAMES_PLAN,
                        help="the names plan of the whole map (default build/release/names/plan-all.json)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--batch", type=int, metavar="N", help="with --apply: stop after N planned entries")
    parser.add_argument("--only", action="append", default=[], metavar="0xADDR",
                        help="with --apply: these planned entries only, in plan order (a pilot; repeatable)")
    parser.add_argument("--patterns", type=Path,
                        help="with --plan: r5900_LE_patterns.xml (default: the installed Emotion Engine Reloaded "
                             "extension under %%APPDATA%%, or SOCOM_R5900_PATTERNS)")
    parser.add_argument("--url")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        if args.plan:
            plan = build_plan(root, gb.Bridge(args.url, read_only=True), args.names_plan,
                              progress=lambda m: print(m, file=sys.stderr), patterns_path=args.patterns)
            path = write_plan(root, plan)
            print(json.dumps(plan["summary"], indent=1))
            print(f"wrote {path.relative_to(root).as_posix()} (plan sha256 {plan['plan_sha256']})")
            return 0
        if args.confirm_saved or args.discard_unsaved:
            bridge = gb.Bridge(args.url, read_only=True)
            check = nm.preflight(bridge)
            if not check["ok"]:
                raise Refused("preflight failed: " + "; ".join(check["errors"]))
            done = (nm.confirm_saved(root, args.confirm_saved.resolve(), bridge, reads_back=reads_back)
                    if args.confirm_saved else
                    nm.discard_unsaved(root, args.discard_unsaved.resolve(), bridge, reads_back=reads_back))
            print(json.dumps(done))
            return 0
        if not args.dry_run and not args.yes:
            print("refused: --apply writes to the release program; pass --yes (or --dry-run)", file=sys.stderr)
            return 2
        if args.dry_run and args.yes:
            parser.error("--dry-run and --yes exclude each other")
        bridge = gb.Bridge(args.url, read_only=args.dry_run, writes=gb.STARTS_WRITES)
        result = apply(root, args.apply.resolve(), bridge, dry_run=args.dry_run, batch=args.batch,
                       only=parse_only(args.only))
        print(json.dumps({k: result[k] for k in ("report", "dry_run", "stopped", "stop_kind", "counts", "saved",
                                                 "batch_full", "entries_done")}, indent=1))
        if result["stopped"]:
            print(f"STOP ({result['stop_kind']}): {result['stopped']}\nwhat to do: {result['what_to_do']}")
        for item in result["remove_by_hand"]:
            print(f"the function {item['name']} at {item['address']} reads {item['body']}, planned {item['planned']}")
        if result["side_effects"]:
            print(f"{len(result['side_effects'])} differences in the end-of-run snapshot, listed in the report")
        if result["batch_full"]:
            print("batch complete: check, save, --confirm-saved the report, rerun names.py --plan --all, replan")
        return 1 if result["stopped"] or result["side_effects"] else 0
    except (Refused, gb.BridgeError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
