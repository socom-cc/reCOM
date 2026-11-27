"""Predict the body Ghidra gives a function created at an address (standard library only).

``create_function`` runs ``CreateFunctionCmd(entry)`` (GhidraMCP ``FunctionService``), whose body
is ``CreateFunctionCmd.getFunctionBody(program, entry, false, monitor)`` (Ghidra 12.1.4
``CreateFunctionCmd.java`` 613-633): ``FollowFlow`` from the entry with calls not followed
(COMPUTED_CALL, CONDITIONAL_CALL, UNCONDITIONAL_CALL, INDIRECTION) and ``followIntoFunctions``
false. ``FollowFlow`` then

* follows every other flow reference (branches, ``j``, computed jumps that analysis resolved) and
  the fall-through, adding each instruction with its delay slot (``FollowFlow.getAdjustedInstruction``, 453-488);
* does not follow a flow reference to an address whose primary symbol is a function
  (743-764), nor a fall-through into one (557-568): an existing function entry ends the body;
* adds only instructions (``includeData`` false, 357-364): flow into undefined bytes or data ends there.

``subtractBodyFromExisting`` (``CreateFunctionCmd.java`` 407-460) then takes the addresses from the
new entry to the new body's end away from an existing function that starts before the entry and
overlaps it, so a create whose body would overlap an existing function changes that function.

``predict`` repeats the flow over the release image's instructions: ``entries`` are the function
entries that will exist when the create is sent, ``noreturn`` the callees whose calls do not
return, ``jumps`` the resolved targets of computed jumps. It returns the addresses reached and
the entries where flow was cut (fall-through or a branch into them).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import mips


@dataclass
class Flow:
    body: set[int] = field(default_factory=set)  # instruction addresses
    stops: set[int] = field(default_factory=set)  # function entries the flow reached and did not enter
    computed: list[int] = field(default_factory=list)  # computed jumps (jr other than jr ra)
    invalid: list[int] = field(default_factory=list)  # flow into bytes that do not decode
    outside: bool = False  # flow left the loaded image


def _is_call(word: int) -> bool:
    op = word >> 26
    return op == 3 or (op == 0 and (word & 0x3F) == 9) or (op == 1 and ((word >> 16) & 0x1F) in (0x10, 0x11, 0x12, 0x13))


is_call = _is_call  # a call, not followed by FollowFlow


ERET = 0x42000018  # eret: Ghidra's R5900 language gives it no fall-through (scePcStart, 0x15a470)


def predict(word_at, contains, entry: int, entries: set[int], noreturn: set[int] = frozenset(),
            jumps: dict[int, list[int]] | None = None, limit: int = 1 << 16, is_code=None,
            terminal=None) -> Flow:
    """``word_at(address)`` reads an instruction word, ``contains(address)`` says it is loaded.

    ``is_code(address)`` (optional): FollowFlow adds instructions only (``includeData`` false), so
    flow into an address that holds no instruction ends there; ``terminal(word)`` (optional): an
    instruction with no fall-through besides jumps and branches (``eret``). Both default to the
    behaviour above (every loaded word is an instruction; only jumps end a run).
    """

    flow = Flow()
    jumps = jumps or {}
    stack = [entry]
    while stack and len(flow.body) < limit:
        pc = stack.pop()
        if pc in flow.body:
            continue
        if not contains(pc) or not contains(pc + 4):
            flow.outside = True
            continue
        if is_code is not None and not is_code(pc):
            flow.invalid.append(pc)
            continue
        word = word_at(pc)
        if mips.is_invalid(word):
            flow.invalid.append(pc)
            continue
        if terminal is not None and terminal(word):
            flow.body.add(pc)
            continue

        def go(target: int) -> None:
            if target != entry and target in entries:
                flow.stops.add(target)
            else:
                stack.append(target)

        target = mips.branch_target(word, pc)
        if _is_call(word):
            flow.body.update((pc, pc + 4))
            callee = mips.jump_target(word, pc) if (word >> 26) == 3 else None
            if callee is None or callee not in noreturn:
                go(pc + 8)
        elif target is not None:
            flow.body.update((pc, pc + 4))
            go(target)
            if not mips.is_unconditional_branch(word):
                go(pc + 8)
        elif mips.is_j(word):
            flow.body.update((pc, pc + 4))
            go(mips.jump_target(word, pc))
        elif mips.is_jr(word):
            flow.body.update((pc, pc + 4))
            if word != mips.JR_RA:
                flow.computed.append(pc)
                for t in jumps.get(pc, ()):
                    go(t)
        else:
            flow.body.add(pc)
            go(pc + 4)
    flow.invalid.sort()
    return flow


def extent(start: int, size: int) -> set[int]:
    return set(range(start, start + size, 4))


def classify(creates: dict[int, int], existing: set[int], word_at, contains, noreturn=frozenset(),
             jumps=None, blocked: dict[int, str] | None = None) -> dict[int, dict]:
    """Every planned create (start -> size): safe, ordered (with the creates it needs first) or withheld.

    ``existing`` are the entries Ghidra has now; ``blocked`` creates already refused for another
    reason. A create is sendable when its predicted body is exactly its map extent once every
    sendable create it flows into exists; it is safe when that holds with the existing entries alone.
    """

    out: dict[int, dict] = {a: {"safety": "withheld", "reason": r, "after": []} for a, r in (blocked or {}).items()}
    sendable = {a for a in creates if a not in out}
    while True:
        dropped = False
        for start in sorted(sendable):
            want = extent(start, creates[start])
            flow = predict(word_at, contains, start, existing | sendable, noreturn, jumps)
            if flow.body != want:
                out[start] = {"safety": "withheld", "reason": _why(flow, want, start, creates[start], word_at),
                              "after": []}
                sendable.discard(start)
                dropped = True
        if not dropped:
            break
    for start in sorted(sendable):
        need = sorted(predict(word_at, contains, start, existing | sendable, noreturn, jumps).stops & sendable)
        alone = predict(word_at, contains, start, existing, noreturn, jumps)
        if alone.body == extent(start, creates[start]):
            out[start] = {"safety": "safe", "reason": "", "after": []}
        else:
            out[start] = {"safety": "ordered", "reason": "", "after": need}
    # A cycle (two creates each flowing into the other) has no safe order.
    changed = True
    while changed:
        changed = False
        for start in sorted(a for a, v in out.items() if v["safety"] == "ordered"):
            if _cycles(start, out):
                out[start] = {"safety": "withheld", "reason": "creates that flow into each other", "after": []}
                changed = True
            elif any(out[a]["safety"] == "withheld" for a in out[start]["after"]):
                out[start] = {"safety": "withheld", "reason": "flows into a withheld create", "after": []}
                changed = True
    return out


def _cycles(start: int, out: dict) -> bool:
    seen, stack = set(), list(out[start]["after"])
    while stack:
        a = stack.pop()
        if a == start:
            return True
        if a in seen or a not in out:
            continue
        seen.add(a)
        stack.extend(out[a]["after"])
    return False


def _why(flow: Flow, want: set[int], start: int, size: int, word_at=None) -> str:
    end = start + size
    beyond = sorted(a for a in flow.body if a not in want)
    missing = sorted(a for a in want if a not in flow.body)
    if beyond:
        nxt = beyond[0]
        if nxt == end and word_at is not None and word_at(end) == 0:
            pad = end
            while pad in flow.body and word_at(pad) == 0:
                pad += 4
            if pad not in flow.body:
                return (f"falls through {pad - end} bytes of padding (nop) into the next function: "
                        "Ghidra would take the padding into the body")
            return f"falls through {pad - end} bytes of padding (nop) into code at 0x{pad:06x} that is no function entry"
        where = "falls through past its end" if nxt == end else f"flows to 0x{nxt:06x}"
        return f"{where} into code that is no function entry (Ghidra would take it into the body)"
    if flow.invalid:
        return f"flow reaches bytes that do not decode at 0x{flow.invalid[0]:06x}"
    if flow.computed:
        return f"computed jump at 0x{flow.computed[0]:06x}: part of the extent is reached only through it"
    if missing:
        return f"flow does not reach 0x{missing[0]:06x}..: Ghidra's body would be shorter than the extent"
    return "the predicted body differs from the extent"
