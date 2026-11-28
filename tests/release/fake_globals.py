"""The fake bridge with the data behaviour the globals tool relies on (GhidraMCP 6.0.0, Ghidra 12.1.4).

Modelled from the classes: ``create_label`` refuses a label of the same name at the address and
otherwise adds one (the first stored label at an address is primary; without one the primary is
a dynamic name when something references the address); ``apply_data_type`` resolves the type by
name and, with ``clear_existing`` false, only creates the data, refusing any overlap with an
instruction or defined data, and adds a DATA reference for each pointer component whose value is
neither 0 nor all ones; ``set_comment`` replaces one comment kind; ``list_globals`` lists stored
labels outside code; ``list_data_items``, ``audit_global``, ``get_comment``, ``get_xrefs_from``,
``get_struct_layout``, ``list_segments`` and ``list_bookmarks`` read what the model holds.
"""
from __future__ import annotations

import ghidra_bridge as gb
from fake_ghidra import FakeGhidra, TYPE_SIZES

BUILTIN_PATHS = {"char", "uchar", "bool", "short", "ushort", "int", "uint", "float", "string", "pointer", "char *"}


def model(p) -> None:
    for name, value in (("data", {}), ("refs_to", {}), ("refs_from", {}), ("comments", {}), ("segments", []),
                        ("layouts", {}), ("bookmarks", []), ("ns_symbols", {})):
        if not hasattr(p, name):
            setattr(p, name, value)


class FakeGlobals(FakeGhidra):
    def __init__(self, *, read_only=False, writes=gb.GLOBALS_WRITES):
        super().__init__(read_only=read_only, writes=writes)
        for p in (self.prototype, self.release):
            model(p)
        self.data_effects = {}  # address -> callable(program): analysis after a type there
        self.label_effects = {}  # address -> callable(program, name) -> answer or None
        self.refuse_types = set()  # addresses where createData throws although nothing shows

    # --- reads ---
    def primary(self, p, address):
        if p.labels.get(address):
            return p.labels[address][0]
        if address in p.ns_symbols:
            return p.ns_symbols[address]
        if p.refs_to.get(address):
            kind = p.data.get(address, ("undefined", 1))[0]
            return ("s_x_%08x" if kind == "string" else "PTR_%08x" if kind == "pointer" else "DAT_%08x") % address
        return ""

    def in_code(self, p, address):
        return address in p.code or p.at(address) is not None

    def get_list_segments(self, q):
        p = self.program(q["program"])
        return "\n".join(f"{n}: {lo:08x} - {hi:08x}" for n, lo, hi in p.segments) + "\n.comment: .comment::00000000 - .comment::0000002a"

    def get_list_data_items(self, q):
        p = self.program(q["program"])
        rows = []
        for a, (t, n) in sorted(p.data.items()):
            label = self.primary(p, a) or "DAT_%08x" % a
            rows.append(f"{label} @ {a:08x} [{t}] ({n} {'byte' if n == 1 else 'bytes'})")
        return "\n".join(rows)

    def get_list_globals(self, q):
        p = self.program(q["program"])
        sub = (q.get("name_substring") or "").lower()
        rows = []
        for a, names in sorted(p.labels.items()):
            if self.in_code(p, a) and a not in p.data:
                continue
            for n in names:
                t = p.data.get(a, ("undefined", 1))[0]
                line = f"{n} @ {a:08x} [Label] ({t}) xrefs={len(p.refs_to.get(a, []))}"
                if not sub or sub in line.lower():
                    rows.append(line)
        return "\n".join(rows)

    def get_audit_global(self, q):
        p = self.program(q["program"])
        a = int(q["address"], 16)
        t, n = p.data.get(a, ("", 0))
        out = {"address": "%08x" % a, "name": self.primary(p, a), "type": t, "length": n, "plate_comment": "",
               "xref_count": len(p.refs_to.get(a, [])), "issues": []}
        if a in p.code or a in p.functions:
            out.update(is_code_address=a in p.code, is_function_entry=a in p.functions)
        return out

    def get_get_comment(self, q):
        p = self.program(q["program"])
        a = int(q["address"], 16)
        c = p.comments.get(a, {})
        return {"address": "%08x" % a, "plate": p.plates.get(a), "pre": c.get("pre"), "eol": c.get("eol"),
                "post": c.get("post"), "repeatable": c.get("repeatable")}

    def get_get_xrefs_from(self, q):
        p = self.program(q["program"])
        a = int(q["address"], 16)
        rows = [f"To {t:08x} [{k}]" for t, k in p.refs_from.get(a, [])]
        return "\n".join(rows) if rows else f"No references found from address: {q['address']}"

    def get_get_xrefs_to(self, q):
        p = self.program(q["program"])
        rows = p.refs_to.get(int(q["address"], 16), [])
        return "\n".join(rows) if rows else f"No references found to address: {q['address']}"

    def get_get_struct_layout(self, q):
        p = self.program(q["program"])
        name = q["struct_name"]
        if name not in p.layouts:
            return f"Data type is not a structure: {name}" if name in p.types else f"Structure not found: {name}"
        rows = "".join(f"{o:6d} | {s:4d} | {t:<20s} | f{o}\n" for o, s, t in p.layouts[name])
        return f"Structure: {name}\nSize: 0 bytes\nAlignment: 1\n\nLayout:\nOffset | Size | Type | Name\n-------|------|------|-----\n{rows}"

    def get_list_bookmarks(self, q):
        p = self.program(q["program"])
        return {"bookmarks": [{"address": "%08x" % a, "type": t, "category": c, "comment": m} for a, t, c, m in p.bookmarks]}

    # --- writes ---
    def post_create_label(self, p, d):
        address = int(d["address"], 16)
        if address in self.label_effects:
            answer = self.label_effects[address](p, d["name"])
            if answer is not None:
                return answer
        return super().post_create_label(p, d)

    def type_length(self, p, name, address):
        if name == "string":
            data = p.image.data
            start = address - p.image.base
            return data.index(b"\0", start) - start + 1
        if name.endswith("*") or name == "pointer":
            return 4
        if name in TYPE_SIZES:
            return TYPE_SIZES[name]
        found = p.types.get(name, [])
        return found[0][1] if found else None

    def pointer_offsets(self, p, name):
        if name.endswith("*") or name == "pointer":
            return [0]
        return [o for o, s, t in p.layouts.get(name, []) if t.endswith("*")]

    def post_apply_data_type(self, p, d):
        assert d["clear_existing"] is False
        address, name = int(d["address"], 16), d["type_name"]
        length = self.type_length(p, name, address)
        if length is None:
            return f"ERROR: Unknown data type: {name}."
        end = address + length
        clash = [a for a, (t, n) in p.data.items() if a < end and a + n > address]
        code = [a for a in p.code if address - 3 <= a < end]
        if clash or code or address in self.refuse_types:
            where = clash[0] if clash else code[0] if code else address
            return {"error": f"Error applying data type: Conflicting data exists at address {where:08x}"}
        p.data[address] = (name, length)
        for k in self.pointer_offsets(p, name):
            value = p.image.word(address + k)
            if value not in (0, 0xFFFFFFFF):
                p.refs_from.setdefault(address + k, []).append((value, "DATA"))
        if address in self.data_effects:
            self.data_effects[address](p)
        return f"Successfully applied data type '{name}' at {d['address']} (size: {length} bytes)"
