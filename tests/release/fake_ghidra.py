"""An in-memory stand-in for the GhidraMCP bridge with the behaviour the names tool relies on.

It subclasses the real client and replaces only the transport, so the client's own refusals
(read-only, allowed endpoints, release-only writes) are exercised unchanged. The modelled
behaviour follows the plugin and Ghidra 12.1.4: programs looked up by project path, GET values
decoded twice, address lookups that fall back to the containing function, ``create_label`` that
renames a function whose name is still DEFAULT instead of labelling it
(``SymbolManager.tryUpdatingDefaultFunction``), DEFAULT thunks that show their target's name
(``FunctionSymbol.doGetName``), ``CreateFunctionCmd`` bodies that follow flow over the image's
instructions until an existing function entry (fall-through into a missing successor included), label lookup by the first function of a name, and labels by
address through ``get_function_documentation``.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, unquote, urlsplit

import createflow
import ghidra_bridge as gb
import mips
from elfimage import PROTOTYPE_SHA256, RELEASE_SHA256

TYPE_SIZES = {"char": 1, "uchar": 1, "bool": 1, "short": 2, "ushort": 2, "int": 4, "uint": 4, "float": 4}
BUILTINS = {"void", "undefined", "char", "uchar", "bool", "short", "ushort", "int", "uint", "float", "long"}


class Program:
    def __init__(self, name: str, path: str, sha256: str):
        self.name, self.path, self.sha256 = name, path, sha256
        self.functions: dict[int, dict] = {}  # entry -> {own, end, lo, thunk_of, noreturn}
        self.labels: dict[int, list[str]] = {}
        self.plates: dict[int, str] = {}
        self.code: set[int] = set()  # addresses holding an instruction
        self.flow_end: dict[int, int] = {}  # override: where CreateFunctionCmd ends a new body
        self.image = None  # the instructions CreateFunctionCmd follows
        self.analyzing = False
        self.types: dict[str, list[tuple[str, int]]] = {}  # name -> [(path, size)] in the data type manager

    def add_type(self, path: str, size: int) -> None:
        name = path.rsplit("/", 1)[1]
        self.types.setdefault(name, []).append((path, size))

    def add(self, entry: int, end: int, name: str | None = None, thunk_of=None, noreturn=False, lo=None):
        """``name`` None: a DEFAULT name (FUN_..., or the target's name for a thunk)."""

        self.functions[entry] = {"own": name, "end": end, "thunk_of": thunk_of, "noreturn": noreturn,
                                 "lo": entry if lo is None else lo, "holes": [],
                                 # the prototype: Ghidra's default until a signature is set
                                 "ret": "undefined", "conv": None, "params": [], "varargs": False,
                                 "storage": None}  # storage: a custom storage list, else dynamic
        self.code.add(entry)

    def sign(self, entry: int, ret: str, conv: str | None, params: list[tuple[str, str]], varargs=False):
        """Give a function a prototype: ``params`` as (type, name)."""

        f = self.functions[entry]
        f.update(ret=ret, conv=conv, params=[{"type": t, "name": n} for t, n in params], varargs=varargs)

    # FunctionDB delegates parameters, return and convention of a thunk to its target; the
    # varargs and no-return flags are the thunk's own.
    def signer(self, entry: int) -> dict:
        f = self.functions[entry]
        return self.signer(f["thunk_of"]) if f["thunk_of"] is not None else f

    def param_names(self, entry: int) -> list[str]:
        return [p["name"] if p["name"] and not re.match(r"^param_\d+$", p["name"]) else f"param_{i}"
                for i, p in enumerate(self.signer(entry)["params"], 1)]

    def storage(self, entry: int) -> list[str]:
        """Dynamic storage as r5900 __stdcall gives it (a0-a3, t0-t3; f12-f19 for floats)."""

        s = self.signer(entry)
        if s["storage"] is not None:
            return list(s["storage"])
        ints, floats, out = iter(["a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3"]), iter(f"f{n}" for n in range(12, 20)), []
        for p in s["params"]:
            size = 4 if p["type"].endswith("*") else TYPE_SIZES.get(p["type"], 4)
            out.append(f"{next(floats)}:4" if p["type"] == "float" else f"{next(ints)}_lo:{size}")
        return out

    def signature(self, entry: int) -> str:
        """FunctionDefinitionDataType.getPrototypeString(true)."""

        f, s = self.functions[entry], self.signer(entry)
        params = ", ".join(f"{p['type']} {n}" for p, n in zip(s["params"], self.param_names(entry)))
        if f["varargs"]:
            params += (", " if params else "") + "..."
        return (("noreturn " if f["noreturn"] else "") + s["ret"] + " " + (s["conv"] + " " if s["conv"] else "")
                + f"{self.shown(entry)}({params or 'void'})")

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
            if fn["lo"] <= address <= fn["end"] and not any(a <= address <= b for a, b in fn["holes"]):
                return entry
        return None


class FakeGhidra(gb.Bridge):
    def __init__(self, *, read_only: bool = False, release_sha=RELEASE_SHA256, writes=gb.WRITES):
        super().__init__("http://fake:1", read_only=read_only, writes=writes)
        self.prototype = Program(gb.PROTOTYPE_PROGRAM, gb.PROTOTYPE_PATH, PROTOTYPE_SHA256)
        self.release = Program(gb.RELEASE_PROGRAM, gb.RELEASE_PATH, release_sha)
        self.extra_programs: list[dict] = []
        self.ignore_renames = False  # simulate a rename that does not stick
        self.analysis_creates: dict[int, list[int]] = {}  # auto-analysis adding functions after a create
        self.analysis_names: dict[int, str] = {}  # Function ID naming a created function
        self.analysis_effects: dict[int, object] = {}  # create address -> callable(program): analysis follow-up
        self.drop_plate_read_after_set = False  # the next plate read after a set answers empty once
        self.mangle_prototype = False  # set_function_prototype loses the parameter names (a bad read-back)
        self.prototype_effects: dict[int, list] = {}  # address -> callables(program): analysis after a write
        self.requests: list[tuple[str, str]] = []

    def clones(self, count):
        return [self]  # one in-memory program: reads stay sequential

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
        return (f"Function: {name} at {entry:08x}\nSignature: {p.signature(entry)}\nEntry: {entry:08x}\n"
                f"Body: {f['lo']:08x} - {f['end']:08x}")

    def get_get_function_variables(self, q):
        p = self.program(q["program"])
        entry = p.at(int(q["address"], 16))  # ServiceUtils.getFunctionForAddress: at, else containing
        if entry is None:
            return {"error": f"No function at address: {q['address']}"}
        params = [{"name": n, "type": s["type"], "ordinal": i, "storage": st}
                  for i, (s, n, st) in enumerate(zip(p.signer(entry)["params"], p.param_names(entry), p.storage(entry)))]
        return {"function_name": p.shown(entry), "function_address": "%08x" % entry, "parameters": params,
                "locals": [], "total_locals": 0}

    def get_list_data_types(self, q):
        p = self.program(q["program"])
        rows = [f"{name} | {path.split('/')[-2] or 'builtin'} | {size} bytes | {path}"
                for name, found in sorted(p.types.items()) for path, size in found]
        return "\n".join(rows) if rows else "No data types found"

    def get_get_plate_comment(self, q):
        p = self.program(q["program"])
        entry = p.at(int(q["address"], 16))
        if entry is None:
            return {"error": f"No function at address: {q['address']}"}
        out = {"address": "%08x" % entry, "function_name": p.shown(entry)}
        if getattr(self, "drop_next_plate_read", False):
            self.drop_next_plate_read = False
            return out
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

    def get_get_xrefs_from(self, q):
        return f"No references found from address: {q['address']}"

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
        if address in p.flow_end:
            lo, end = address, p.flow_end[address]
        else:  # CreateFunctionCmd.getFunctionBody: FollowFlow, stopping at existing function entries
            flow = createflow.predict(p.image.word, p.image.contains, address, set(p.functions))
            lo, end = min(flow.body), max(flow.body) + 3
        thunk_of = None
        first = p.image.word(address) if p.image is not None else None
        if (lo, end) == (address, address + 7) and p.image.word(address + 4) == 0:
            target = mips.jump_target(first, address) if mips.is_j(first) else None
            if target in p.functions:  # CreateFunctionCmd.resolveThunk
                thunk_of = target
        p.add(address, end, self.analysis_names.get(address), lo=lo, thunk_of=thunk_of)
        for extra in self.analysis_creates.get(address, ()):
            p.add(extra, extra + 0xF)
        if address in self.analysis_effects:
            self.analysis_effects[address](p)
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
        if d["new_name"] in p.labels.get(entry, []):  # SymbolManager.checkDuplicateSymbolName
            return {"error": f"A symbol named {d['new_name']} already exists at this address!"}
        if not self.ignore_renames:
            p.functions[entry]["own"] = d["new_name"]
        return {"status": "success", "message": "Renamed"}

    def resolve(self, p, text: str):
        """DataTypeParser over the program's types: one type of the name, or a built-in."""

        text = text.strip()
        base = re.sub(r"(?:\s*\*)+$", "", text).strip()
        if base in BUILTINS or len(p.types.get(base, [])) == 1:
            return re.sub(r"\s*\*", " *", text).strip()
        return None

    def post_set_function_prototype(self, p, d):
        """FunctionService.setFunctionPrototype: FunctionSignatureParser, ApplyFunctionSignatureCmd
        (DYNAMIC_STORAGE_FORMAL_PARAMS, RENAME_IF_DEFAULT, varargs from the text, no-return
        untouched), then the calling convention in a second transaction."""

        fail = "Failed to set function prototype: "
        entry = p.at(int(d["function_address"], 16))  # getFunctionContaining
        if entry is None:
            return fail + "Could not find function at address: " + d["function_address"]
        text, conv = d["prototype"], d.get("calling_convention") or ""
        head = text[:text.index("(")]
        found = re.search(r"\b(__cdecl|__stdcall|__thiscall|__fastcall|__vectorcall)\b", head)
        if found:
            conv = conv or found.group(1)
            text = re.sub(r"\s+", " ", head[:found.start()] + head[found.end():] + text[text.index("("):]).strip()
        open_at, close_at = text.index("("), text.index(")")
        if text[close_at + 1:].strip():
            return fail + "Unexpected trailing text"
        words = text[:open_at].split()
        name, ret = words[-1], self.resolve(p, " ".join(words[:-1]))
        if any(c in name for c in "()*[], "):
            return fail + f"Can't parse name: {name}"
        if ret is None:
            return fail + "Can't resolve return type: " + " ".join(words[:-1])
        params, inside = [], text[open_at + 1:close_at].strip()
        if inside not in ("", "void"):
            for arg in (a.strip() for a in inside.split(",")):
                if arg == "...":
                    continue
                cut = max(arg.rfind(" "), arg.rfind("*")) + 1
                typed = self.resolve(p, arg[:cut])
                if typed is None:
                    return fail + "Can't resolve datatype: " + arg[:cut].strip()
                params.append({"type": typed, "name": arg[cut:].strip()})
        last = text.rfind(",")
        varargs = last >= 0 and text[last + 1:close_at].strip() == "..."
        f = p.signer(entry)  # updateFunction on a thunk updates its target
        own = p.functions[entry]
        if own["own"] is None and p.shown(entry) != name:
            own["own"] = name  # RENAME_IF_DEFAULT: the function at the address, a thunk too
        f.update(ret=ret, params=params, storage=None, varargs=varargs)  # dynamic storage; setVarArgs delegates
        if self.mangle_prototype:
            f["params"] = [dict(x, name=None) for x in f["params"]]
        for effect in self.prototype_effects.get(entry, ()):
            effect(p)
        if conv:
            if conv not in ("__stdcall", "__thiscall"):
                return fail + f"Unknown calling convention: {conv}. "
            f["conv"] = conv
        return f"Successfully set prototype for function at {d['function_address']}" + (
            f" with {conv} calling convention" if d.get("calling_convention") else "")

    def post_set_comment(self, p, d):
        assert d["type"] == "plate"
        p.plates[int(d["address"], 16)] = d["comment"]
        if self.drop_plate_read_after_set:
            self.drop_plate_read_after_set = False
            self.drop_next_plate_read = True
        return {"status": "success", "message": f"Set comment at {d['address']}"}
