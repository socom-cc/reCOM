"""An in-memory stand-in for the GhidraMCP bridge with the behaviour the names tool relies on.

It subclasses the real client and replaces only the transport, so the client's own refusals
(read-only, allowed endpoints, release-only writes) are exercised unchanged. The modelled
behaviour follows the plugin and Ghidra 12.1.4: programs looked up by project path, GET values
decoded twice, address lookups that fall back to the containing function, ``create_label`` that
renames a function whose name is still DEFAULT instead of labelling it
(``SymbolManager.tryUpdatingDefaultFunction``), DEFAULT thunks that show their target's name
(``FunctionSymbol.doGetName``), label lookup by the first function of a name, and labels by
address through ``get_function_documentation``.
"""
from __future__ import annotations

import json
from urllib.parse import parse_qsl, unquote, urlsplit

import ghidra_bridge as gb
from elfimage import PROTOTYPE_SHA256, RELEASE_SHA256


class Program:
    def __init__(self, name: str, path: str, sha256: str):
        self.name, self.path, self.sha256 = name, path, sha256
        self.functions: dict[int, dict] = {}  # entry -> {own, end, lo, thunk_of, noreturn}
        self.labels: dict[int, list[str]] = {}
        self.plates: dict[int, str] = {}
        self.code: set[int] = set()  # addresses holding an instruction
        self.flow_end: dict[int, int] = {}  # where CreateFunctionCmd would end a new body
        self.analyzing = False

    def add(self, entry: int, end: int, name: str | None = None, thunk_of=None, noreturn=False, lo=None):
        """``name`` None: a DEFAULT name (FUN_..., or the target's name for a thunk)."""

        self.functions[entry] = {"own": name, "end": end, "thunk_of": thunk_of, "noreturn": noreturn,
                                 "lo": entry if lo is None else lo}
        self.code.add(entry)

    def shown(self, entry: int) -> str:
        f = self.functions[entry]
        if f["own"] is not None:
            return f["own"]
        target = f["thunk_of"]
        if target is not None:
            t = self.functions[target]
            shown = self.shown(target)
            return "thunk_" + shown if t["own"] is None and t["thunk_of"] is None else shown
        return "FUN_%08x" % entry

    def at(self, address: int):
        if address in self.functions:
            return address
        for entry, fn in self.functions.items():
            if fn["lo"] <= address <= fn["end"]:
                return entry
        return None


class FakeGhidra(gb.Bridge):
    def __init__(self, *, read_only: bool = False, release_sha=RELEASE_SHA256):
        super().__init__("http://fake:1", read_only=read_only)
        self.prototype = Program(gb.PROTOTYPE_PROGRAM, gb.PROTOTYPE_PATH, PROTOTYPE_SHA256)
        self.release = Program(gb.RELEASE_PROGRAM, gb.RELEASE_PATH, release_sha)
        self.extra_programs: list[dict] = []
        self.ignore_renames = False  # simulate a rename that does not stick
        self.analysis_creates: dict[int, list[int]] = {}  # auto-analysis adding functions after a create
        self.analysis_names: dict[int, str] = {}  # Function ID naming a created function
        self.requests: list[tuple[str, str]] = []

    def program(self, path):
        return {p.path: p for p in (self.prototype, self.release)}[path]

    def _send(self, method, path, body=None):
        parts = urlsplit(path)
        endpoint = parts.path.lstrip("/")
        # The bridge decodes the query, splits it, and decodes each value again.
        query = {k: unquote(v) for k, v in parse_qsl(parts.query)}
        self.requests.append((method, endpoint))
        if method == "GET":
            return getattr(self, "get_" + endpoint)(query)
        data = json.loads(body.decode("utf-8"))
        assert query["program"] == data["program"]
        return getattr(self, "post_" + endpoint)(self.program(query["program"]), data)

    # reads
    def get_list_open_programs(self, q):
        rows = [{"name": p.name, "path": p.path} for p in (self.prototype, self.release)] + self.extra_programs
        return {"programs": rows, "count": len(rows)}

    def get_get_program_options(self, q):
        return {"options": [{"name": "Executable SHA256", "value": self.program(q["program"]).sha256}]}

    def get_analysis_status(self, q):
        p = self.program(q["program"])
        return {"name": p.name, "analyzed": True, "analyzing": p.analyzing}

    def get_list_functions_enhanced(self, q):
        p = self.program(q["program"])
        rows = [{"address": "%08x" % a, "name": p.shown(a), "isThunk": f["thunk_of"] is not None, "isExternal": False}
                for a, f in sorted(p.functions.items())]
        return {"functions": rows, "count": len(rows)}

    def get_get_function_by_address(self, q):
        p = self.program(q["program"])
        address = int(q["address"], 16)
        entry = p.at(address)
        if entry is None:
            return f"No function found for {q['address']}"
        f, name = p.functions[entry], p.shown(entry)
        sig = ("noreturn " if f["noreturn"] else "") + f"undefined {name}(void)"
        return (f"Function: {name} at {entry:08x}\nSignature: {sig}\nEntry: {entry:08x}\n"
                f"Body: {f['lo']:08x} - {f['end']:08x}")

    def get_get_plate_comment(self, q):
        p = self.program(q["program"])
        entry = p.at(int(q["address"], 16))
        if entry is None:
            return {"error": f"No function at address: {q['address']}"}
        out = {"address": "%08x" % entry, "function_name": p.shown(entry)}
        if entry in p.plates:
            out["comment"] = p.plates[entry]
        return out

    def get_get_function_labels(self, q):
        p = self.program(q["program"])
        entry = next((a for a in sorted(p.functions) if p.shown(a) == q["name"]), None)
        if entry is None:
            return f"Function not found: {q['name']}"
        rows = [f"Address: {a:08x}, Name: {n}, Source: USER_DEFINED"
                for a, names in sorted(p.labels.items()) if entry <= a <= p.functions[entry]["end"] for n in names]
        return "\n".join(rows) if rows else f"No labels found in function: {q['name']}"

    def get_get_function_documentation(self, q):
        p = self.program(q["program"])
        address = int(q["address"], 16)
        if address not in p.functions:
            return {"error": f"No function at {q['address']}"}
        end = p.functions[address]["end"]
        labels = [{"relative_offset": a - address, "name": n} for a, names in sorted(p.labels.items())
                  if address <= a <= end for n in names if n != p.shown(address)]
        return {"source_address": "%08x" % address, "function_name": p.shown(address), "labels": labels}

    def get_audit_global(self, q):
        p = self.program(q["program"])
        address = int(q["address"], 16)
        return {"address": "%08x" % address, "is_code_address": address in p.code,
                "is_function_entry": address in p.functions}

    # writes
    def post_create_function(self, p, d):
        address = int(d["address"], 16)
        assert d["disassemble_first"] is False
        if address in p.functions:
            return {"error": f"Function already exists at {d['address']}"}
        if address not in p.code:
            return {"error": "no instruction"}
        p.add(address, p.flow_end[address], self.analysis_names.get(address))
        for extra in self.analysis_creates.get(address, ()):
            p.add(extra, extra + 0xF)
        return {"success": True, "function_name": p.shown(address)}

    def post_create_label(self, p, d):
        address = int(d["address"], 16)
        names = p.labels.setdefault(address, [])
        if d["name"] in names:
            return {"error": f"Label '{d['name']}' already exists at address {d['address']}"}
        f = p.functions.get(address)
        if f is not None and f["own"] is None:
            f["own"] = d["name"]  # SymbolManager.tryUpdatingDefaultFunction: the function takes the name
        elif f is None or p.shown(address) != d["name"]:
            names.append(d["name"])
        return {"status": "success", "message": f"Created label '{d['name']}' at address {d['address']}"}

    def post_rename_function_by_address(self, p, d):
        assert d.get("strict_mode") == "off"
        entry = p.at(int(d["function_address"], 16))  # the plugin falls back to the containing function
        if entry is None:
            return {"error": "Function not found"}
        if not self.ignore_renames:
            p.functions[entry]["own"] = d["new_name"]
        return {"status": "success", "message": "Renamed"}

    def post_set_comment(self, p, d):
        assert d["type"] == "plate"
        p.plates[int(d["address"], 16)] = d["comment"]
        return {"status": "success", "message": f"Set comment at {d['address']}"}
