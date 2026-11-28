"""The fake bridge with the reference behaviour the references tool relies on (GhidraMCP 6.0.0, Ghidra 12.1.4).

Modelled from the classes: ``add_memory_reference`` (``ReferenceDBManager.addMemoryReference``)
adds a reference from an instruction to a memory address on an operand with a type and a source;
the same from, to and operand is not added twice; a new reference is primary when its operand has
none yet; no symbol or data is made at the target, whose primary name turns dynamic (``DAT_``) once
something references it; nothing else runs. ``get_xrefs_from`` lists target and type only;
``disassemble_function`` lists every instruction from the entry to the body's end, a gap's too.
"""
from __future__ import annotations

import ghidra_bridge as gb
from fake_globals import FakeGlobals


class FakeReferences(FakeGlobals):
    def __init__(self, *, read_only=False, writes=gb.REFERENCE_WRITES):
        super().__init__(read_only=read_only, writes=writes)
        for p in (self.prototype, self.release):
            p.insn_text = {}  # address -> Ghidra's text of the instruction
            p.ref_ops = {}  # from -> [(to, type, operand, source)]
        self.reference_effects = {}  # from -> callable(program): analysis after the write
        self.reference_answers = {}  # from -> the answer the bridge gives instead

    def get_disassemble_function(self, q):
        p = self.program(q["program"])
        entry = p.at(int(q["address"], 16))
        if entry is None:
            return {"error": f"No function found at or containing address {q['address']}"}
        end = p.functions[entry]["end"]
        return "".join(f"{a:08x}: {p.insn_text.get(a, 'nop')} \n" for a in range(entry, end + 1, 4) if a in p.code)

    def post_add_memory_reference(self, p, d):
        at, to = int(d["from_address"], 16), int(d["to_address"], 16)
        if at in self.reference_answers:
            return self.reference_answers[at]
        ops = p.ref_ops.setdefault(at, [])
        if any(t == to and o == d["operand_index"] for t, _, o, _ in ops):
            return {"status": "success", "from_address": "%08x" % at, "to_address": "%08x" % to,
                    "ref_type": d["ref_type"], "source_type": d["source_type"], "operand_index": d["operand_index"],
                    "is_primary": True}
        primary = not any(o == d["operand_index"] for _, _, o, _ in ops)
        ops.append((to, d["ref_type"], d["operand_index"], d["source_type"]))
        p.refs_from.setdefault(at, []).append((to, d["ref_type"]))
        p.refs_to.setdefault(to, []).append(f"From {at:08x} in f [{d['ref_type']}]")
        if at in self.reference_effects:
            self.reference_effects[at](p)
        return {"status": "success", "from_address": "%08x" % at, "to_address": "%08x" % to,
                "ref_type": d["ref_type"], "source_type": d["source_type"], "operand_index": d["operand_index"],
                "is_primary": primary}
