"""Stage 4 (source-correlation): translation-unit evidence from the immutable ELF.

``source graph`` is a deterministic, file-only producer.  It reads only the
reference ELF (symbols, relocations, bytes, DWARF 1 ``.debug`` and
``.line``); it never reads Ghidra, the tracker, or ``src/``, and it writes
nothing except the files it is asked to write under ``build/``.

Artifacts are the census-derived set: one node per start address of the
sized ``FUNC`` and ``OBJECT`` symbols (aliases at one address share a node),
plus every unsymbolled gap between neighbouring nodes of one ELF section
(a data-to-code gap is split where its first code input section starts).

Signals, each kept with its provenance:

* ``dwarf-cu``: a compile-unit DIE's pc range covers the artifact; a source
  path (``.c``/``.cpp``/``.s``) names the translation unit, a header path is
  only an emitted-from-header hint; the CU's ``.line`` unit gives its lines;
* ``dwarf-variable``: a variable DIE's ``DW_OP_ADDR`` location.  A static
  local names its CU's unit; a global is listed by every CU that uses it, so
  it stays weak;
* ``file-string``: a ``__FILE__``-like string (a whole ``@N`` literal, or a
  string inside other data), with the artifacts whose relocations reach it;
* ``unnamed-namespace``: an ``@unnamed@<file>@`` tag in a symbol name;
* ``sinit``: ``__sinit_<file>`` functions and ``.p__sinit_<file>`` words;
  the table's address order is the authored link order;
* ``gnu-object``: a ``gcc2_compiled.`` marker or ``.text`` section symbol
  opens a GNU-toolchain object; ``__ps2_libinfo__`` names its SCE library;
* ``local-relocation``: a relocation against a LOCAL symbol (or a section
  symbol) proves its site and its target share one object file;
* ``symtab-local-order``: the linker writes each object's LOCAL symbols
  contiguously, so clusters whose LOCAL index ranges overlap are one object;
* ``text-contiguity``: an object's text is contiguous, so functions between
  two members of one cluster join it (medium: an assumption, checked for
  contradictions);
* ``literal-pool``: ``@N`` literals are numbered per unit and laid out in
  address order, so a run of rising numbers suggests one unit (weak); a run
  stops where two different multi-member clusters (two objects) or two
  input sections meet;
* ``class-hint``: a demangled qualifier whose anchored methods all sit in
  one unit (weak).

A GNU object without function symbols (crt0's labelled code) owns the gap
its anchor opens; a provider DWARF path on an object's own code names its
library.

Every classification (authored / provider / compiler-generated / unknown) is
a candidate with the evidence that drove it, never an accepted owner.  A
function still unknown after the other rules whose relocations (either way)
reach provider code of exactly one library, at least two artifacts of it,
takes that library (weak); authored code casts no vote (library code calls
the program's operator new and delete).

Segments are contiguous windows of at most ``segment_size`` functions, cut
at the strongest available anchor and always at classification changes.
Compiler-generated and unknown functions are neutral; in a neutral run
between two families the next family starts at the first function that opens
a GNU object of it or whose relocations reach it and not the previous one.
Each segment lists its ``internal_boundaries``: the unit changes inside it
with the unanchored functions between the two anchors.
"""

from __future__ import annotations

import bisect
import hashlib
import re
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath
from typing import Any, Callable

from .dwarf1 import Dwarf1Debug, Dwarf1Line
from .elf import Elf32File
from .mips_flow import lo16_targets
from .mwdemangle import demangle, readable_component
from .util import SocomError, canonical_json, sha256_file, stable_id

SOURCE_GRAPH_KIND = "socom-source-graph"
SOURCE_GRAPH_SCHEMA = 1
SEGMENT_SIZE = 200
# Coordinator-supplied window of the GNU-compiled speech-recognition
# middleware (accepted stage 4 proposal); only GNU objects inside it use it.
SPEECH_WINDOW = (0x336EF0, 0x3788A0)
_ROUNDS = 16
STRENGTHS = ("strong", "medium", "weak", "hint")
_RANK = {name: rank for rank, name in enumerate(STRENGTHS)}

SOURCE_SUFFIXES = (".c", ".cc", ".cp", ".cpp", ".cxx", ".s", ".asm")
_FILE_STRING = re.compile(rb"[A-Za-z0-9_:\\/. -]{0,200}?[A-Za-z0-9_.-]+\.(?:cpp|cxx|cc|cp|c|hpp|h|s|asm)\0", re.IGNORECASE)
_BASENAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_UNNAMED = re.compile(r"@unnamed@([A-Za-z0-9_]+?)_(cpp|cxx|cc|cp|c)@")
_LITERAL = re.compile(r"^@(\d+)$")
_THUNK = re.compile(r"^@\d+@")
_LIBINFO = "__ps2_libinfo__"
_GNU_MARKER = "gcc2_compiled."

# Ordered name rules for GNU-toolchain objects: an object takes the library
# most of its function names match; objects nothing matches take the library
# of their archive neighbours (``archive-contiguity``).
GNU_LIBRARY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SCE", re.compile(r"^(?:_?sce|isce|_sce)[A-Z_]")),
    ("Medius", re.compile(r"^(?:Medius|rt_|RT_|Dme|KM_)")),
    ("RSA", re.compile(r"^(?:RSA|rsa|lint|LargeInt)")),
    ("lgAud", re.compile(r"^lgAud")),
    (
        "libgcc",
        re.compile(r"^(?:__(?:[a-z]+(?:di|si|ti|sf|df|tf)[234]|(?:un)?pack_[fd]|make_[fd]p|fpcmp_parts_[fd])|fpto[su]i|dpto[su]i)$"),
    ),
    (
        "newlib",
        re.compile(
            r"^(?:__ieee754_\w+|__kernel_\w+|_\w+_r|__s[a-z]\w*|__sf\w*|_?(?:mem|str)[a-z]+|"
            r"v?(?:s|sn|f)?printf|v?(?:s|f)?scanf|[cm]alloc|realloc|free|abort|atexit|exit|qsort|bsearch|"
            r"s?rand|ato[ifl]|l?abs|l?div|to(?:upper|lower)|"
            r"is(?:alpha|digit|space|upper|lower|alnum|print|punct|xdigit|cntrl|graph|inf|nan)|"
            r"f(?:open|close|read|write|seek|tell|flush|puts|gets|getc|putc|ileno|dopen)|puts|gets|getc|putc|"
            r"putchar|getchar|ungetc|setvbuf|setbuf|rewind|perror|getenv|"
            r"(?:a?(?:sin|cos|tan)h?|atan2|exp|log(?:10)?|pow|sqrt|ceil|floor|fabs|fmod|frexp|ldexp|modf|"
            r"copysign|scalbn|rint|finite)f?)$"
        ),
    ),
)
# Member-identity name rules: they refine which library an object belongs to
# but never move a segment cut (segments are cut by ``GNU_LIBRARY_RULES``
# alone, so the stage 4 items' segment numbers stay stable); a refined
# object's artifacts move to their library's planning scope instead.
# libgcc's fp-bit.c built with US_SOFTWARE_GOFAST names its soft-float entry
# points dpadd/fpadd ... and its NaN constant __thenan_df/__thenan_sf.
GNU_MEMBER_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "libgcc",
        re.compile(
            r"^(?:(?:dp|fp)(?:add|sub|mul|div|cmp|neg)|litodp|dptoli|dptoul|dptofp|sitofp|fptosi|fptoui|fptodp|"
            r"__thenan_[sd]f)$"
        ),
    ),
)
# The system-call layer newlib calls but leaves to the platform (libgloss; on
# the PS2 the SCE kernel library's glue object).  newlib defines only the
# ``_<name>_r`` wrappers, so these names show that an object serves newlib,
# never which library it belongs to: they cast no library vote.
GNU_VOTE_NEUTRAL_NAMES = frozenset(
    (
        "_exit", "close", "environ", "execve", "fork", "fstat", "getpid", "isatty", "kill",
        "link", "lseek", "open", "read", "sbrk", "stat", "times", "unlink", "wait", "write",
    )
)
# Name rules for Metrowerks-compiled provider code without a unit anchor:
# the C++ runtime entry points (exceptions, arrays, pointers to members,
# global destruction) and the 989snd API prefix its anchored unit uses.
MW_LIBRARY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "MW runtime",
        re.compile(
            r"^__(?:throw\w*|rethrow\w*|end_catch\w*|unexpected\w*|terminate\w*|ThrowHandler\w*|FindExceptionTable\w*|"
            r"destroy_(?:arr|new_array\w*|global_chain)|construct_(?:new_)?array\w*|ptmf_\w+|register_global_object\w*|"
            r"do_global_dtors|init_cpp|fini_cpp|dynamic_cast\w*)$"
        ),
    ),
    ("989snd", re.compile(r"^snd_[A-Z]")),
)
# Qualifiers of the C++ library namespaces; other mangled names are C++
# outside every provider namespace.
LIBRARY_NAMESPACES = ("std", "Metrowerks")
# Unit basenames whose library is known without a DWARF path.
TU_LIBRARY = {"989snd.c": "989snd", "largeint.c": "RSA", "rsa.c": "RSA"}


def _hex(value: int) -> str:
    return f"0x{value:x}"


def _tu_name(text: str) -> str:
    return PureWindowsPath(text.replace("/", "\\")).name


def _is_source(path: str) -> bool:
    return _tu_name(path).casefold().endswith(SOURCE_SUFFIXES)


def path_library(path: str) -> tuple[str, str | None] | None:
    """(classification, library) an original source path implies, if any."""

    folded = path.replace("/", "\\").casefold()
    if folded.startswith("z:\\dev\\"):
        return ("authored", None)
    if "\\msl\\" in folded:
        return ("provider", "MSL")
    if "ps2 support\\" in folded:
        return ("provider", "MW runtime")
    if _tu_name(path).casefold() == "crt0.s":
        return ("provider", "crt0")
    if "\\libptt" in folded:
        return ("provider", "libptt")
    if "\\sce" in folded:
        return ("provider", "SCE")
    return None


class _Union:
    """Deterministic union-find; the smaller key is always the root."""

    def __init__(self) -> None:
        self.parent: dict[Any, Any] = {}

    def find(self, key: Any) -> Any:
        parent = self.parent.setdefault(key, key)
        if parent == key:
            return key
        root = key
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[key] != root:
            self.parent[key], key = root, self.parent[key]
        return root

    def union(self, left: Any, right: Any) -> bool:
        a, b = self.find(left), self.find(right)
        if a == b:
            return False
        if b < a:
            a, b = b, a
        self.parent[b] = a
        return True

    def groups(self) -> dict[Any, list[Any]]:
        members: dict[Any, list[Any]] = defaultdict(list)
        for key in sorted(self.parent):
            members[self.find(key)].append(key)
        return members


# -- inputs ----------------------------------------------------------------


class _Image:
    def __init__(self, path: Path) -> None:
        self.elf = Elf32File(path)
        self.sha256 = sha256_file(path)
        self.symbols = self.elf.symbols()
        names = {section.name for section in self.elf.sections}
        self.relocations = self.elf.relocations(".relmain") if ".relmain" in names else ()
        self.segments = list(self.elf.load_segments())
        self.gp = int.from_bytes(self.elf.section_data(".reginfo")[20:24], "little") if ".reginfo" in names else None
        self.debug = Dwarf1Debug(self.elf.section_data(".debug")).parse(strict=True) if ".debug" in names else ()
        self.lines = (
            {unit.offset: unit for unit in Dwarf1Line(self.elf.section_data(".line")).parse()} if ".line" in names else {}
        )
        self.lo16 = lo16_targets(self.elf) if self.relocations and self.segments else {}

    def read(self, address: int, size: int) -> bytes:
        for row in self.segments:
            if row.virtual_address <= address and address + size <= row.virtual_address + row.file_size:
                offset = row.offset + address - row.virtual_address
                return self.elf.data[offset : offset + size]
        return b""

    def word(self, address: int) -> int | None:
        raw = self.read(address, 4)
        return int.from_bytes(raw, "little") if len(raw) == 4 else None


# -- artifacts -------------------------------------------------------------

_BINDING_RANK = {"GLOBAL": 0, "WEAK": 1, "LOCAL": 3}


def _artifacts(image: _Image) -> list[dict[str, Any]]:
    by_start: dict[int, dict[str, Any]] = {}
    for symbol in image.symbols:
        if symbol.type_name not in ("FUNC", "OBJECT") or not symbol.size:
            continue
        kind = "function" if symbol.type_name == "FUNC" else "data"
        row = by_start.setdefault(
            symbol.value,
            {"kind": kind, "start": symbol.value, "size": symbol.size, "section_index": symbol.section_index, "names": []},
        )
        if row["kind"] != kind:
            raise SocomError(f"FUNC and OBJECT symbols share address 0x{symbol.value:x}")
        if row["section_index"] != symbol.section_index:
            raise SocomError(f"symbols at 0x{symbol.value:x} name different sections")
        row["size"] = max(row["size"], symbol.size)
        row["names"].append(
            {
                "name": symbol.name,
                "binding": symbol.binding_name,
                "size": symbol.size,
                "symbol_index": symbol.index,
                "symbol_id": stable_id("symbol", symbol.index, symbol.name),
            }
        )
    rows = sorted(by_start.values(), key=lambda row: row["start"])
    for previous, current in zip(rows, rows[1:]):
        if previous["start"] + previous["size"] > current["start"]:
            raise SocomError(f"artifacts at 0x{previous['start']:x} and 0x{current['start']:x} overlap")
    for row in rows:
        row["names"].sort(key=lambda item: (item["symbol_index"], item["name"]))
        row["id"] = f"socom:{row['kind']}:{_hex(row['start'])}"
        row["binding"] = min(
            (item["binding"] for item in row["names"]), key=lambda value: (_BINDING_RANK.get(value, 2), value)
        )
        row["size_conflict"] = len({item["size"] for item in row["names"]}) > 1
    return rows


_CODE_SECTIONS = (".text", ".vutext")
# Input sections a data-only archive member may hold.
_DATA_SECTIONS = frozenset((".data", ".rodata", ".bss", ".sdata", ".sbss"))


def _section_starts(image: _Image) -> list[int]:
    """Start addresses of every input section the ELF's SECTION symbols open (``.DVP.`` overlays excluded)."""

    return sorted(
        {symbol.value for symbol in image.symbols if symbol.type_name == "SECTION" and symbol.value and ".DVP." not in symbol.name}
    )


def _nodes(image: _Image, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Artifacts plus the unsymbolled gaps between neighbours of one section.

    A gap is split at every input section (a LOCAL SECTION symbol) that
    starts inside it: the bytes of one gap then never span two objects'
    input sections (``.rodata`` of puts.o and strtod.o).  In a gap that
    leads from data into code, the first code input section
    (``.text``/``.vutext``) opens the code run: the bytes before it are fill
    of the data run.  A gap that leads from code into data opens the data
    run at its start.
    """

    labels: dict[int, set[str]] = defaultdict(set)
    for symbol in image.symbols:
        if symbol.type_name == "NOTYPE" and symbol.name and symbol.value and not symbol.name.startswith("$L"):
            labels[symbol.value].add(symbol.name)
    label_starts = sorted(labels)
    code_starts = sorted(
        {symbol.value for symbol in image.symbols if symbol.type_name == "SECTION" and symbol.value and symbol.name in _CODE_SECTIONS}
    )
    section_starts = _section_starts(image)
    nodes: list[dict[str, Any]] = []
    for previous, current in zip([None, *artifacts], artifacts):
        if previous is not None and previous["section_index"] == current["section_index"]:
            start = previous["start"] + previous["size"]
            end = current["start"]
            before, after = previous["kind"], current["kind"]
            # Where the run of ``after`` opens inside the gap.
            transition = start
            if before != "function" and after == "function":
                position = bisect.bisect_right(code_starts, start)
                transition = code_starts[position] if position < len(code_starts) and code_starts[position] < end else start
            low_cut = bisect.bisect_right(section_starts, start)
            high_cut = bisect.bisect_left(section_starts, end)
            points = [start, *section_starts[low_cut:high_cut], end]
            pieces = []
            for low_address, high_address in zip(points, points[1:]):
                if before == after or low_address < transition:
                    edge = [before, before]
                elif low_address == transition:
                    edge = [before, after]
                else:
                    edge = [after, after]
                pieces.append((low_address, high_address, edge))
            for low_address, high_address, edge in pieces:
                size = high_address - low_address
                if size <= 0:
                    continue
                raw = image.read(low_address, size)
                fill = "nobits" if not raw else "zero" if raw.count(0) == len(raw) else "nonzero"
                low = bisect.bisect_left(label_starts, low_address)
                high = bisect.bisect_left(label_starts, high_address)
                inside = sorted({name for address in label_starts[low:high] for name in labels[address]})
                nodes.append(
                    {
                        "kind": "gap",
                        "id": f"socom:gap:{_hex(low_address)}",
                        "start": low_address,
                        "size": size,
                        "section_index": current["section_index"],
                        "fill": fill,
                        "padding": fill in ("zero", "nobits") and size < 16 and not inside,
                        "labels": inside,
                        "between": edge,
                        "names": [],
                        "binding": None,
                    }
                )
        nodes.append(current)
    return nodes


def _section_envelopes(image: _Image) -> list[tuple[int, int, str]]:
    """[first, last] address of each input-section name's SECTION symbols."""

    by_name: dict[str, list[int]] = defaultdict(list)
    for symbol in image.symbols:
        if symbol.type_name == "SECTION" and symbol.name.startswith(".") and symbol.value and ".DVP." not in symbol.name:
            by_name[symbol.name].extend((symbol.value, symbol.value + symbol.size))
    return sorted((min(values), max(values), name) for name, values in by_name.items())


def _input_section(envelopes: list[tuple[int, int, str]], node: dict[str, Any]) -> dict[str, Any]:
    for low, high, name in envelopes:
        if low <= node["start"] <= high:
            if (node["kind"] == "function") != (name in _CODE_SECTIONS) and node["kind"] != "gap":
                continue
            return {"name": name, "basis": "section-symbol envelope"}
    before = [name for low, high, name in envelopes if high < node["start"]]
    after = [name for low, high, name in envelopes if low > node["start"]]
    return {
        "name": None,
        "basis": "outside every section-symbol envelope",
        "between": [before[-1] if before else None, after[0] if after else None],
    }


def _windows(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Maximal runs of one artifact kind per section; gaps join their run."""

    windows: list[dict[str, Any]] = []
    for node in nodes:
        kind = {"function": "code", "data": "data"}.get(node["kind"])
        if kind is None and node["between"][0] != node["between"][1]:
            # A gap between runs of different kinds opens the run after it.
            kind = "code" if node["between"][1] == "function" else "data"
        current = windows[-1] if windows else None
        if current and current["section_index"] == node["section_index"] and kind in (None, current["kind"]):
            current["nodes"].append(node)
            continue
        windows.append({"kind": kind, "section_index": node["section_index"], "nodes": [node]})
    for window in windows:
        first, last = window["nodes"][0], window["nodes"][-1]
        window["start"] = first["start"]
        window["end"] = last["start"] + last["size"]
        window["id"] = f"socom:window:{_hex(window['start'])}"
        for node in window["nodes"]:
            node["window"] = window["id"]
    return windows


class _Locator:
    def __init__(self, nodes: list[dict[str, Any]]) -> None:
        self.nodes = nodes
        self.starts = [node["start"] for node in nodes]

    def find(self, address: int | None) -> int | None:
        if address is None:
            return None
        position = bisect.bisect_right(self.starts, address) - 1
        if position >= 0 and address < self.nodes[position]["start"] + self.nodes[position]["size"]:
            return position
        return None


def _sign16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _references(image: _Image, locator: _Locator) -> list[dict[str, Any]]:
    """Every relocation with its site node, resolved target and target node.

    R_MIPS_26 targets come from the instruction, R_MIPS_LO16 from the HI16
    whose ``lui`` reaches the site (mips_flow), R_MIPS_GPREL16 from the
    ``.reginfo`` $gp value and R_MIPS_32 from the data word.
    """

    rows = []
    for relocation in image.relocations:
        name = relocation.type_name
        site = relocation.offset
        target: int | None = None
        word = image.word(site)
        if name == "R_MIPS_26" and word is not None:
            target = ((site + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        elif name == "R_MIPS_LO16":
            target = (image.lo16.get(site) or {}).get("target")
        elif name == "R_MIPS_GPREL16" and image.gp is not None and word is not None:
            target = (image.gp + _sign16(word & 0xFFFF)) & 0xFFFFFFFF
        elif name == "R_MIPS_32":
            target = word
        rows.append(
            {
                "site": site,
                "target": target,
                "type": name,
                "symbol_index": relocation.symbol_index,
                "site_node": locator.find(site),
                "target_node": locator.find(target),
            }
        )
    return rows


def _literal_number(node: dict[str, Any]) -> int | None:
    for row in node["names"]:
        match = _LITERAL.match(row["name"])
        if match:
            return int(match.group(1))
    return None


# -- graph -----------------------------------------------------------------


class _Graph:
    def __init__(self, path: Path, segment_size: int) -> None:
        if segment_size < 1:
            raise SocomError("segment size must be positive")
        self.segment_size = segment_size
        self.image = _Image(path)
        self.nodes = _nodes(self.image, _artifacts(self.image))
        self.position = {node["id"]: index for index, node in enumerate(self.nodes)}
        self.locator = _Locator(self.nodes)
        self.windows = _windows(self.nodes)
        envelopes = _section_envelopes(self.image)
        for node in self.nodes:
            node["input_section"] = _input_section(envelopes, node)
            node["signals"] = []
        self.references = _references(self.image, self.locator)
        self.section_starts = _section_starts(self.image)
        self.coupling_moves: list[dict[str, Any]] = []
        self.dwarf_paths: list[str] = []
        self.header_hint: dict[int, str] = {}
        self.libinfo: dict[int, str] = {}
        self.sinit_order: dict[str, int] = {}
        self.contradictions: list[dict[str, Any]] = []
        self.edges: Counter[str] = Counter()

    def signal(self, index: int, name: str, strength: str, **fields: Any) -> None:
        self.nodes[index]["signals"].append({"signal": name, "strength": strength, **fields})

    def code_functions(self, window: dict[str, Any]) -> list[int]:
        return [self.position[node["id"]] for node in window["nodes"] if node["kind"] == "function"]

    # -- direct signals ------------------------------------------------------

    def dwarf_signals(self) -> None:
        debug = self.image.debug
        units = [number for number, die in enumerate(debug) if die.tag_name == "compile_unit"]
        variables: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for position, number in enumerate(units):
            die = debug[number]
            end = units[position + 1] if position + 1 < len(units) else len(debug)
            path = die.string("name") or ""
            if path:
                self.dwarf_paths.append(path)
            low, high = die.integer("low_pc"), die.integer("high_pc")
            stmt = die.integer("stmt_list")
            line = None
            unit = self.image.lines.get(stmt) if stmt is not None else None
            if unit is not None and unit.entries:
                line = {
                    "stmt_list": stmt,
                    "first": min(row.line for row in unit.entries),
                    "last": max(row.line for row in unit.entries),
                    "entries": len(unit.entries),
                }
            if low is not None and high is not None and high > low:
                fields = {
                    "die_offset": _hex(die.offset),
                    "path": path,
                    "producer": die.string("producer"),
                    "low_pc": _hex(low),
                    "high_pc": _hex(high),
                    "line": line,
                }
                index = max(bisect.bisect_right(self.locator.starts, low) - 1, 0)
                while index < len(self.nodes) and self.nodes[index]["start"] < high:
                    node = self.nodes[index]
                    if node["start"] + node["size"] > low:
                        if _is_source(path):
                            self.signal(index, "dwarf-cu", "strong", tu=_tu_name(path), **fields)
                        else:
                            self.signal(index, "dwarf-cu-header", "hint", **fields)
                            self.header_hint.setdefault(index, path)
                    index += 1
            for child in debug[number + 1 : end]:
                if child.tag_name not in ("global_variable", "local_variable"):
                    continue
                location = child.attribute("location")
                value = location.value if location is not None else None
                if not isinstance(value, bytes) or len(value) != 5 or value[0] != 0x03:
                    continue
                index = self.locator.find(int.from_bytes(value[1:5], "little"))
                if index is None:
                    continue
                if child.tag_name == "local_variable" and _is_source(path):
                    self.signal(
                        index,
                        "dwarf-variable",
                        "strong",
                        tu=_tu_name(path),
                        variable=child.string("name"),
                        tag="local_variable",
                        die_offset=_hex(child.offset),
                        path=path,
                    )
                else:
                    variables[index][child.string("name") or ""].add(path)
        for index, by_name in variables.items():
            for name, paths in sorted(by_name.items()):
                sources = sorted({_tu_name(path) for path in paths if _is_source(path)}, key=str.casefold)
                self.signal(
                    index,
                    "dwarf-variable",
                    "weak",
                    tu=sources[0] if len(sources) == 1 else None,
                    variable=name,
                    tag="global_variable",
                    paths=sorted(paths),
                )

    def string_signals(self) -> None:
        referrers: dict[int, set[int]] = defaultdict(set)
        for row in self.references:
            if row["target_node"] is not None and row["site_node"] is not None:
                referrers[row["target_node"]].add(row["site_node"])
        for window in self.windows:
            if window["kind"] != "data":
                continue
            blob = self.image.read(window["start"], window["end"] - window["start"])
            for match in _FILE_STRING.finditer(blob):
                if match.start() and blob[match.start() - 1] != 0:
                    continue
                text = match.group(0)[:-1].decode("ascii")
                name = _tu_name(text)
                if not _BASENAME.match(name):
                    continue
                address = window["start"] + match.start()
                index = self.locator.find(address)
                if index is None:
                    continue
                node = self.nodes[index]
                literal = node["start"] == address and _literal_number(node) is not None
                users = sorted(site for site in referrers.get(index, ()) if self.nodes[site]["kind"] != "data")
                fields = {
                    "text": text,
                    "string": _hex(address),
                    "literal": literal,
                    "referenced_by": [self.nodes[site]["id"] for site in users],
                }
                if _is_source(name):
                    self.signal(index, "file-string", "strong" if literal else "medium", tu=name, **fields)
                else:
                    self.signal(index, "file-string-header", "hint", **fields)
                for site in users:
                    self.signal(site, "file-string-reference", "hint", text=text, string_node=node["id"])

    def name_signals(self) -> None:
        for index, node in enumerate(self.nodes):
            for row in node["names"]:
                name = row["name"]
                match = _UNNAMED.search(name)
                if match:
                    self.signal(index, "unnamed-namespace", "strong", tu=f"{match.group(1)}.{match.group(2)}", symbol=name)
                if name.startswith("__sinit_") and node["kind"] == "function":
                    self.signal(index, "sinit", "strong", tu=name[len("__sinit_") :], symbol=name)
                if name.startswith(".p__sinit_") and node["kind"] == "data":
                    tu = name[len(".p__sinit_") :]
                    self.sinit_order.setdefault(tu.casefold(), len(self.sinit_order) + 1)
                    self.signal(index, "sinit", "strong", tu=tu, symbol=name, order=self.sinit_order[tu.casefold()])
                if name == _LIBINFO and node["kind"] == "data":
                    raw = self.image.read(node["start"], node["size"])
                    if raw.startswith(b"PsII") and len(raw) >= 16:
                        library = raw[4:12].decode("ascii", errors="replace").strip()
                        self.libinfo[index] = library
                        self.signal(index, "libinfo", "strong", library=library, version=raw[12:16].decode("ascii", errors="replace"))

    # -- clusters ------------------------------------------------------------

    def metrowerks_evidence(self) -> set[int]:
        symbols = self.image.symbols
        literal_users = {
            row["site_node"]
            for row in self.references
            if row["site_node"] is not None and row["symbol_index"] < len(symbols) and _LITERAL.match(symbols[row["symbol_index"]].name)
        }
        evidence = set()
        for index, node in enumerate(self.nodes):
            if node["kind"] != "function":
                continue
            if (
                node["binding"] == "13"
                or index in literal_users
                or any(demangle(row["name"]) for row in node["names"])
                or any(item["signal"] == "dwarf-cu" and "MW" in str(item.get("producer")) for item in node["signals"])
            ):
                evidence.add(index)
        return evidence

    def gnu_objects(self, mw_evidence: set[int]) -> list[dict[str, Any]]:
        anchors: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for symbol in self.image.symbols:
            if symbol.name == _GNU_MARKER or (symbol.type_name == "SECTION" and symbol.name == ".text"):
                anchors[symbol.value].append({"name": symbol.name, "symbol_index": symbol.index})
        objects = []
        for window in self.windows:
            if window["kind"] != "code":
                continue
            functions = self.code_functions(window)
            starts = [self.nodes[index]["start"] for index in functions]
            addresses = sorted(address for address in anchors if window["start"] <= address < window["end"])
            for number, address in enumerate(addresses):
                following = addresses[number + 1] if number + 1 < len(addresses) else None
                members: list[int] = []
                end_basis = "next GNU anchor" if following is not None else "window end (uncertain)"
                for index in functions[bisect.bisect_left(starts, address) :]:
                    start = self.nodes[index]["start"]
                    if following is not None and start >= following:
                        break
                    if index in mw_evidence and not (start == address and not members):
                        end_basis = "first Metrowerks-evidence function (uncertain)"
                        break
                    members.append(index)
                # An object without function symbols (crt0's labelled code)
                # is the unsymbolled gap its anchor opens.
                opening = self.locator.find(address)
                gaps = (
                    [opening]
                    if not members and opening is not None and self.nodes[opening]["kind"] == "gap"
                    and self.nodes[opening]["start"] == address and not self.nodes[opening]["padding"]
                    else []
                )
                objects.append(
                    {
                        "address": address,
                        "anchor": sorted(anchors[address], key=lambda row: row["symbol_index"]),
                        "gcc_compiled": any(row["name"] == _GNU_MARKER for row in anchors[address]),
                        "members": members,
                        "gaps": gaps,
                        "end_basis": end_basis,
                    }
                )
        return objects

    def local_indices(self, key: tuple[str, int]) -> list[int]:
        if key[0] == "s":
            return [key[1]]
        return [row["symbol_index"] for row in self.nodes[key[1]]["names"] if row["binding"] == "LOCAL"]

    def strong_units(self, keys: list[Any]) -> set[str]:
        return {
            item["tu"].casefold()
            for key in keys
            if key[0] == "n"
            for item in self.nodes[key[1]]["signals"]
            if item.get("tu") and item["strength"] == "strong"
        }

    def merge(self, union: _Union, gnu_nodes: set[int], contiguity: bool) -> int:
        rounds = 0
        for rounds in range(1, _ROUNDS + 1):
            changed = False
            intervals = []
            for root, keys in union.groups().items():
                indices = [value for key in keys for value in self.local_indices(key)]
                if indices:
                    intervals.append((min(indices), max(indices), root))
            current: tuple[int, int, Any] | None = None
            for low, high, root in sorted(intervals):
                if current is not None and low <= current[1]:
                    if union.union(current[2], root):
                        self.edges["symtab-local-order"] += 1
                        changed = True
                    current = (current[0], max(current[1], high), union.find(root))
                else:
                    current = (low, high, root)
            if contiguity:
                changed = self.contiguity(union, gnu_nodes) or changed
            if not changed:
                break
        return rounds

    def contiguity(self, union: _Union, gnu_nodes: set[int]) -> bool:
        groups = union.groups()
        units = {root: self.strong_units(keys) for root, keys in groups.items()}
        gnu = {root: any(key[0] == "n" and key[1] in gnu_nodes for key in keys) for root, keys in groups.items()}
        changed = False
        for window in self.windows:
            if window["kind"] != "code":
                continue
            functions = self.code_functions(window)
            spans: dict[Any, list[int]] = {}
            for order, index in enumerate(functions):
                spans.setdefault(union.find(("n", index)), [order, order])[1] = order
            for root, (low, high) in sorted(spans.items(), key=lambda item: (item[1], item[0])):
                for order in range(low + 1, high):
                    mine, other = union.find(root), union.find(("n", functions[order]))
                    if mine == other:
                        continue
                    a, b = units.get(mine, set()), units.get(other, set())
                    if (a and b and a != b) or gnu.get(mine, False) != gnu.get(other, False):
                        self.contradictions.append(
                            {
                                "kind": "interleaved objects",
                                "units": sorted(a | b),
                                "gnu": [gnu.get(mine, False), gnu.get(other, False)],
                                "cluster_span": [self.nodes[functions[low]]["id"], self.nodes[functions[high]]["id"]],
                                "at": self.nodes[functions[order]]["id"],
                            }
                        )
                        continue
                    union.union(mine, other)
                    merged = union.find(mine)
                    units[merged] = a | b
                    gnu[merged] = gnu.get(mine, False) or gnu.get(other, False)
                    self.edges["text-contiguity"] += 1
                    changed = True
        return changed

    def clusters(self) -> tuple[list[dict[str, Any]], int]:
        mw_evidence = self.metrowerks_evidence()
        union = _Union()
        symbols = self.image.symbols
        for index in range(len(self.nodes)):
            union.find(("n", index))
        def pure(index: int | None) -> bool:
            # An unsymbolled gap may hold several objects' bytes, so it
            # never joins a cluster.
            return index is not None and self.nodes[index]["kind"] != "gap"

        for row in self.references:
            site = row["site_node"]
            if not pure(site) or row["symbol_index"] >= len(symbols):
                continue
            symbol = symbols[row["symbol_index"]]
            if symbol.binding_name != "LOCAL" or not symbol.value:
                continue
            if symbol.type_name == "SECTION":
                # A section symbol is local to its object, and the address it
                # reaches lies in that object's section.
                self.edges["section-symbol"] += union.union(("n", site), ("s", symbol.index))
                if pure(row["target_node"]):
                    self.edges["section-symbol"] += union.union(("n", site), ("n", row["target_node"]))
                continue
            target = self.locator.find(symbol.value)
            if pure(target):
                self.edges["local-relocation"] += union.union(("n", site), ("n", target))
        objects = self.gnu_objects(mw_evidence)
        gnu_nodes = {index for row in objects for index in row["members"]}
        for row in objects:
            keys = [("n", index) for index in row["members"]] + [("s", item["symbol_index"]) for item in row["anchor"]]
            for key in keys[1:]:
                self.edges["gnu-object"] += union.union(keys[0], key)
        rounds = self.merge(union, gnu_nodes, contiguity=False)
        before = {}
        for root, keys in union.groups().items():
            units = self.strong_units(keys)
            for key in keys:
                if key[0] == "n":
                    before[key[1]] = units
        rounds += self.merge(union, gnu_nodes, contiguity=True)
        clusters = []
        for root, keys in union.groups().items():
            members = sorted(key[1] for key in keys if key[0] == "n")
            if not members:
                continue
            units: dict[str, dict[str, Any]] = {}
            for index in members:
                for item in self.nodes[index]["signals"]:
                    if item.get("tu") and item["strength"] == "strong":
                        unit = units.setdefault(item["tu"].casefold(), {"tu": item["tu"], "signals": set(), "artifacts": set()})
                        unit["signals"].add(item["signal"])
                        unit["artifacts"].add(index)
            cluster = {
                "id": f"socom:tu-cluster:{_hex(self.nodes[members[0]]['start'])}",
                "members": members,
                "units": units,
                "libraries": sorted({self.libinfo[index] for index in members if index in self.libinfo}),
                "local_symbols": sorted(value for key in keys for value in self.local_indices(key)),
            }
            if len(units) > 1:
                self.contradictions.append(
                    {
                        "kind": "one object names several units",
                        "units": sorted(unit["tu"] for unit in units.values()),
                        "at": self.nodes[members[0]]["id"],
                    }
                )
            for index in members:
                self.nodes[index]["cluster"] = cluster
                self.nodes[index]["contiguity_only"] = len(units) == 1 and not before.get(index)
            clusters.append(cluster)
        self.gnu = objects
        self.gnu.extend(self.data_only_objects(clusters))
        return clusters, rounds

    # -- LOCAL section blocks ----------------------------------------------------

    def section_extent(self, start: int, foreign: Callable[[int], bool]) -> tuple[int, str, list[int]]:
        """(end, end basis, artifacts) of the input section a LOCAL SECTION symbol opens at ``start``.

        The section runs to the next input section any SECTION symbol opens,
        but stops earlier at the end of its window or at the first artifact
        ``foreign`` rejects (Metrowerks objects carry no section symbols, so
        their data would otherwise seem to extend the last GNU section).
        """

        position = self.locator.find(start)
        if position is None or self.nodes[position]["start"] != start:
            return start, "no artifact starts there", []
        window = self.nodes[position]["window"]
        following = bisect.bisect_right(self.section_starts, start)
        limit = self.section_starts[following] if following < len(self.section_starts) else None
        indices: list[int] = []
        index = position
        while index < len(self.nodes) and (limit is None or self.nodes[index]["start"] < limit):
            node = self.nodes[index]
            if node["window"] != window:
                return node["start"], "window end", indices
            if node["kind"] != "gap" and foreign(index):
                return node["start"], f"foreign artifact {node['id']}", indices
            indices.append(index)
            index += 1
        if limit is None or index >= len(self.nodes):
            last = self.nodes[indices[-1]] if indices else self.nodes[position]
            return last["start"] + last["size"], "window end", indices
        return limit, "next section symbol", indices

    def mw_evidence_node(self, index: int) -> bool:
        """An artifact a Metrowerks unit (or another object) claims: no GNU section run may cross it."""

        node = self.nodes[index]
        if any(item.get("tu") and item["strength"] in ("strong", "medium") for item in node["signals"]):
            return True
        return any(
            _LITERAL.match(row["name"]) or _THUNK.match(row["name"]) or row["name"].startswith(("__RTTI__", "__vt__", ".p__sinit_"))
            for row in node["names"]
        )

    def data_only_objects(self, clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """GNU archive members without code, from their LOCAL section-symbol blocks.

        The linker writes each object's LOCAL symbols contiguously.  A run
        of LOCAL symbols that no object with functions claims, lying between
        two GNU objects' blocks, is split where a section name repeats (an
        object has one input section of each name).  A block with data
        section symbols (``.data``, ``.rodata``, ``.bss``, ``.sdata``,
        ``.sbss``) and no code is a data-only member (newlib's impure.o and
        ctype_.o, libgcc's _thenan_df.o) unless its sections hold an
        artifact of a neighbouring object's cluster (the neighbour's own
        leading section, such as locale.o's ``.data``) or a neighbour's
        functions reference its data (it could be that neighbour's leading
        or trailing section: a neighbour may take a block that repeats none
        of its section names, the previous one only when its own block does
        not end with ``gcc2_compiled.``, which GCC writes last).  Its
        identity is the lowest address its sections open; it owns their
        data and non-padding gaps.  Its library is set in ``gnu_libraries``.
        """

        symbols = self.image.symbols
        with_code: dict[int, dict[str, Any]] = {}
        object_of_node = {index: row for row in self.gnu for index in row["members"] + row["gaps"]}
        claimed: set[int] = set()
        for cluster in clusters:
            gnu = next((object_of_node[index] for index in cluster["members"] if index in object_of_node), None)
            if not any(self.nodes[index]["kind"] == "function" for index in cluster["members"]):
                continue
            claimed.update(cluster["members"])
            if gnu is None:
                continue
            for value in cluster["local_symbols"]:
                with_code[value] = gnu
        local = [symbol for symbol in symbols if symbol.binding_name == "LOCAL" and symbol.index > 0]
        users: dict[int, set[int]] = defaultdict(set)
        for reference in self.references:
            if reference["site_node"] is not None and reference["target_node"] is not None:
                users[reference["target_node"]].add(reference["site_node"])

        def names_of(start: int, step: int, gnu: dict[str, Any]) -> set[str]:
            found, index = set(), start
            while 0 <= index < len(local) and with_code.get(local[index].index) is gnu:
                if local[index].type_name == "SECTION":
                    found.add(local[index].name)
                index += step
            return found

        found: list[dict[str, Any]] = []
        position = 0
        while position < len(local):
            if local[position].index in with_code:
                position += 1
                continue
            first = position
            while position < len(local) and local[position].index not in with_code:
                position += 1
            previous = with_code.get(local[first - 1].index) if first else None
            following = with_code.get(local[position].index) if position < len(local) else None
            if previous is None or following is None:
                continue
            blocks: list[list[Any]] = [[]]
            for symbol in local[first:position]:
                if symbol.type_name == "SECTION" and any(
                    other.type_name == "SECTION" and other.name == symbol.name for other in blocks[-1]
                ):
                    blocks.append([])
                blocks[-1].append(symbol)
            previous_names = set() if local[first - 1].name == _GNU_MARKER else names_of(first - 1, -1, previous)
            following_names = names_of(position, 1, following)
            for number, block in enumerate(blocks):
                sections = [symbol for symbol in block if symbol.type_name == "SECTION" and symbol.name in _DATA_SECTIONS and symbol.value]
                if not sections or any(
                    symbol.type_name == "FUNC" or (symbol.type_name == "SECTION" and symbol.name not in _DATA_SECTIONS)
                    for symbol in block
                ):
                    continue
                extents = []
                inside: list[int] = []
                for symbol in sorted(sections, key=lambda row: row.value):
                    end, basis, indices = self.section_extent(symbol.value, self.mw_evidence_node)
                    extents.append(
                        {"name": symbol.name, "symbol_index": symbol.index, "start": symbol.value, "end": end, "end_basis": basis}
                    )
                    inside.extend(indices)
                if not inside or any(index in claimed for index in inside):
                    continue
                names = {symbol.name for symbol in sections}
                joinable = []
                if number == 0 and local[first - 1].name != _GNU_MARKER and not names & previous_names:
                    joinable.append(previous)
                if number == len(blocks) - 1 and not names & following_names:
                    joinable.append(following)
                neighbours = {index for row in joinable for index in row["members"]}
                if any(users.get(index, set()) & neighbours for index in inside):
                    continue
                found.append(
                    {
                        "address": min(symbol.value for symbol in sections),
                        "anchor": [{"name": symbol.name, "symbol_index": symbol.index} for symbol in sorted(block, key=lambda row: row.index) if symbol.type_name == "SECTION"],
                        "gcc_compiled": False,
                        "members": [],
                        "gaps": [index for index in inside if self.nodes[index]["kind"] == "gap" and not self.nodes[index]["padding"]],
                        "data": [index for index in inside if self.nodes[index]["kind"] == "data"],
                        "end_basis": "LOCAL section-symbol block",
                        "data_only": True,
                        "sections": extents,
                        "local_symbols": [block[0].index, block[-1].index],
                        "symtab_neighbours": [previous, following],
                    }
                )
        return sorted(found, key=lambda row: row["address"])

    # -- weak candidates -------------------------------------------------------

    def cluster_tu(self, index: int) -> str | None:
        units = self.nodes[index]["cluster"]["units"]
        return next(iter(units.values()))["tu"] if len(units) == 1 else None

    def object_boundary(self, left: int, right: int) -> bool:
        """Two data artifacts provably lie in different objects or input sections.

        Each of two different multi-member clusters is one object, so a
        literal run stops between them; so does an input-section change.
        """

        a, b = self.nodes[left], self.nodes[right]
        if a["input_section"].get("name") != b["input_section"].get("name"):
            return True
        return a["cluster"] is not b["cluster"] and len(a["cluster"]["members"]) > 1 and len(b["cluster"]["members"]) > 1

    def literal_pools(self) -> tuple[int, int]:
        runs: list[list[int]] = []
        for window in self.windows:
            if window["kind"] != "data":
                continue
            previous: tuple[int, int] | None = None
            for node in window["nodes"]:
                number = _literal_number(node) if node["kind"] == "data" else None
                if number is None:
                    continue
                index = self.position[node["id"]]
                if (
                    previous is not None
                    and previous[1] - 8 <= number <= previous[1] + 1024
                    and node["start"] - self.nodes[previous[0]]["start"] <= 4096
                    and not self.object_boundary(previous[0], index)
                ):
                    runs[-1].append(index)
                else:
                    runs.append([index])
                previous = (index, number)
        conflicts = 0
        for run in runs:
            units = {name.casefold(): name for name in (self.cluster_tu(index) for index in run) if name}
            if len(units) > 1:
                conflicts += 1
            elif len(units) == 1 and len(run) > 1:
                name = next(iter(units.values()))
                for index in run:
                    if not self.cluster_tu(index):
                        self.signal(index, "literal-pool", "weak", tu=name, run_start=self.nodes[run[0]]["id"], run_length=len(run))
        return len(runs), conflicts

    def class_hints(self) -> None:
        qualifiers: dict[int, str] = {}
        for index, node in enumerate(self.nodes):
            if node["kind"] != "function":
                continue
            for row in node["names"]:
                parsed = demangle(row["name"])
                if parsed and parsed.get("qualifier"):
                    qualifiers[index] = "::".join(readable_component(part) for part in parsed["qualifier"])
                    break
        homes: dict[str, set[str]] = defaultdict(set)
        for index, qualifier in qualifiers.items():
            name = self.cluster_tu(index)
            if name and self.nodes[index]["binding"] not in ("WEAK", "13"):
                homes[qualifier].add(name)
        for index, qualifier in sorted(qualifiers.items()):
            units = homes.get(qualifier, set())
            if not self.cluster_tu(index) and len(units) == 1 and self.nodes[index]["binding"] not in ("WEAK", "13"):
                self.signal(index, "class-hint", "weak", tu=next(iter(units)), qualifier=qualifier)
            else:
                self.signal(index, "class-qualifier", "hint", qualifier=qualifier)

    # -- classification ------------------------------------------------------

    def _assign_libraries(
        self, objects: list[dict[str, Any]], rules: tuple[tuple[str, re.Pattern[str]], ...]
    ) -> list[tuple[str | None, str | None]]:
        """(library, basis) of each GNU function object under the given name rules."""

        found: list[list[str | None]] = []
        for row in objects:
            cluster = self.nodes[row["members"][0]]["cluster"] if row["members"] else None
            votes: Counter[str] = Counter()
            for index in row["members"]:
                for name in self.nodes[index]["names"]:
                    if name["name"] in GNU_VOTE_NEUTRAL_NAMES:
                        continue
                    library = next((library for library, pattern in rules if pattern.search(name["name"])), None)
                    if library:
                        votes[library] += 1
            inside = SPEECH_WINDOW[0] <= row["address"] < SPEECH_WINDOW[1]
            library, basis = None, None
            # A provider DWARF path on the object's own code names its library.
            paths = sorted(
                {
                    item["path"]
                    for index in row["members"] + row["gaps"]
                    for item in self.nodes[index]["signals"]
                    if item["signal"] == "dwarf-cu" and (path_library(item["path"]) or ("",))[0] == "provider"
                }
            )
            if paths:
                library, basis = path_library(paths[0])[1], f"DWARF path {paths[0]}"
            elif cluster and cluster["libraries"]:
                library, basis = "SCE", "__ps2_libinfo__ " + ", ".join(cluster["libraries"])
            elif votes and not (inside and max(votes, key=lambda name: (votes[name], name)) != "SCE"):
                best = max(sorted(votes), key=lambda name: votes[name])
                library, basis = best, f"function names ({votes[best]} of {sum(votes.values())} matches)"
            elif inside:
                library, basis = "speech middleware", "coordinator window 0x336ef0-0x3788a0"
            found.append([library, basis])
        # Archive members link contiguously: an unnamed object takes the
        # library of its identified neighbours in its run of adjacent GNU
        # objects (each ending at the next GNU anchor).
        runs: list[list[int]] = []
        for number, row in enumerate(objects):
            if runs and objects[runs[-1][-1]]["end_basis"] == "next GNU anchor":
                runs[-1].append(number)
            else:
                runs.append([number])
        for run in runs:
            for position, number in enumerate(run):
                if found[number][0]:
                    continue
                before = next((found[item][0] for item in reversed(run[:position]) if found[item][0]), None)
                after = next((found[item][0] for item in run[position + 1 :] if found[item][0]), None)
                if before and after in (before, None):
                    found[number] = [before, "archive-contiguity"]
                elif after and before is None:
                    found[number] = [after, "archive-contiguity"]
        return [(library, basis) for library, basis in found]

    def gnu_libraries(self) -> None:
        """Each GNU object's library: segmentation rules, member refinements, coupling, data-only members.

        ``segment_library`` follows ``GNU_LIBRARY_RULES`` alone and drives the
        segment cuts; ``library`` adds the member-identity rules
        (``GNU_MEMBER_RULES``), then the coupling rule, and is the object's
        classification.
        """

        objects = [row for row in self.gnu if not row.get("data_only")]
        base = self._assign_libraries(objects, GNU_LIBRARY_RULES)
        refined = self._assign_libraries(objects, GNU_LIBRARY_RULES + GNU_MEMBER_RULES)
        for row, (segment_library, _basis), (library, basis) in zip(objects, base, refined):
            row["segment_library"] = segment_library
            row["library"], row["library_basis"] = library, basis
        self.coupling_moves = self.couple(objects)
        self.data_only_libraries()

    def couple(self, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """A GNU object without direct library evidence joins the one library it is coupled to.

        An object whose library rests on archive-contiguity alone (or is
        unidentified) joins library L when everything outside it that
        references it (its callers and the functions sharing its data) is
        code of GNU objects of L, at least two such artifacts, none of its
        current library, and it uses L itself (calls L's code or shares L's
        data).  An archive member is used by its own library or by the
        program; one that only L uses and that uses L is L's.  The evidence
        is read under the libraries before this rule, in one pass.
        """

        owner = {index: row for row in objects for index in row["members"] + row["gaps"]}
        callers: dict[int, set[int]] = defaultdict(set)
        targets: dict[int, set[int]] = defaultdict(set)
        for reference in self.references:
            site, target = reference["site_node"], reference["target_node"]
            if site is None or target is None or site == target:
                continue
            callers[target].add(site)
            targets[site].add(target)
        moves = []
        for row in objects:
            if not row["members"] or (row["library"] is not None and row["library_basis"] != "archive-contiguity"):
                continue
            mine = set(row["members"]) | set(row["gaps"])
            own_data = {
                index
                for member in row["members"]
                for index in self.nodes[member]["cluster"]["members"]
                if self.nodes[index]["kind"] != "function"
            } - mine
            inbound = {site for index in mine for site in callers.get(index, ()) if site not in mine and site not in own_data}
            used = {target for site in mine for target in targets.get(site, ()) if target not in mine}
            shared = {
                site
                for index in (own_data | {target for target in used if self.nodes[target]["kind"] != "function"})
                for site in callers.get(index, ())
                if site not in mine and self.nodes[site]["kind"] == "function"
            }
            coupled = inbound | shared
            if len(coupled) < 2 or any(site not in owner for site in coupled):
                continue
            libraries = {owner[site]["library"] for site in coupled}
            if len(libraries) != 1:
                continue
            library = next(iter(libraries))
            if library is None or library == row["library"]:
                continue
            uses = shared or any(target in owner and owner[target]["library"] == library for target in used)
            if not uses:
                continue
            shown = ", ".join(self.nodes[site]["id"] for site in sorted(coupled)[:4])
            moves.append(
                {
                    "address": _hex(row["address"]),
                    "from": row["library"],
                    "from_basis": row["library_basis"],
                    "to": library,
                    "referrers": len(coupled),
                }
            )
            row["pending"] = (
                library,
                f"coupling: referenced only by {library} objects ({len(coupled)} artifacts: {shown}) and uses {library} "
                f"(was {row['library'] or 'unidentified'} by {row['library_basis'] or 'no evidence'})",
            )
        for row in objects:
            if "pending" in row:
                row["library"], row["library_basis"] = row.pop("pending")
        return moves

    def data_only_libraries(self) -> None:
        """A data-only member takes the library of the GNU objects around its LOCAL block.

        Both symbol-table neighbours of one library give that library;
        otherwise the one library of the GNU objects whose functions
        reference its data, if any.
        """

        owner = {index: row for row in self.gnu if not row.get("data_only") for index in row["members"] + row["gaps"]}
        callers: dict[int, set[int]] = defaultdict(set)
        for reference in self.references:
            if reference["site_node"] is not None and reference["target_node"] is not None:
                callers[reference["target_node"]].add(reference["site_node"])
        for row in self.gnu:
            if not row.get("data_only"):
                continue
            previous, following = row["symtab_neighbours"]
            library, basis = None, None
            if previous["library"] and previous["library"] == following["library"]:
                library = previous["library"]
                basis = (
                    f"LOCAL symbol order between {library} objects {_hex(previous['address'])} and "
                    f"{_hex(following['address'])}"
                )
            else:
                sites = {site for index in row["data"] + row["gaps"] for site in callers.get(index, ()) if site in owner}
                libraries = {owner[site]["library"] for site in sites}
                if len(libraries) == 1 and None not in libraries:
                    library = next(iter(libraries))
                    basis = f"referenced only by {library} objects ({len(sites)} functions)"
            row["library"], row["library_basis"], row["segment_library"] = library, basis, library

    def section_runs(self, row: dict[str, Any], classes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The data input sections a GNU function object's LOCAL SECTION symbols open, with their extents.

        A run stops at the next input section, its window's end, or the
        first artifact another object claims (a Metrowerks unit's evidence,
        another cluster with functions, or a non-weak classification of
        another library or of authored code).
        """

        if row.get("data_only"):
            return row["sections"]
        if not row["members"]:
            return []
        cluster = self.nodes[row["members"][0]]["cluster"]
        mine = set(cluster["members"])
        if any(self.gnu_of.get(index, row) is not row for index in mine if self.nodes[index]["kind"] == "function"):
            # A cluster holding several objects' functions gives no object its sections.
            return []
        symbols = self.image.symbols
        library = row["library"] or "unidentified GNU object"

        def foreign(index: int) -> bool:
            node = self.nodes[index]
            if index in mine:
                return False
            if self.mw_evidence_node(index):
                return True
            if any(self.nodes[other]["kind"] == "function" for other in node["cluster"]["members"]):
                return True
            verdict = classes[index]
            if verdict.get("weak"):
                return False
            return verdict["candidate"] == "authored" or (verdict["candidate"] == "provider" and verdict["library"] != library)

        runs = []
        for value in cluster["local_symbols"]:
            symbol = symbols[value]
            if symbol.type_name != "SECTION" or symbol.name not in _DATA_SECTIONS or not symbol.value:
                continue
            end, basis, _indices = self.section_extent(symbol.value, foreign)
            runs.append({"name": symbol.name, "symbol_index": symbol.index, "start": symbol.value, "end": end, "end_basis": basis})
        return sorted(runs, key=lambda item: item["start"])

    def object_class(self, cluster: dict[str, Any]) -> dict[str, Any] | None:
        """The classification one object cluster's evidence supports."""

        members = cluster["members"]
        gnu = next((self.gnu_of[index] for index in members if index in self.gnu_of), None)
        if gnu is not None:
            kind = "gcc2_compiled." if gnu["gcc_compiled"] else ".text section symbol"
            evidence = [f"GNU object at {_hex(gnu['address'])} ({kind})"]
            if gnu["library_basis"]:
                evidence.append(f"library by {gnu['library_basis']}")
            return {"candidate": "provider", "library": gnu[self.library_key] or "unidentified GNU object", "evidence": evidence}
        authored_path = None
        for index in members:
            for item in self.nodes[index]["signals"]:
                if item["signal"] != "dwarf-cu":
                    continue
                verdict = path_library(item["path"])
                if verdict and verdict[0] == "provider":
                    return {"candidate": "provider", "library": verdict[1], "evidence": [f"DWARF path {item['path']}"]}
                if verdict:
                    authored_path = authored_path or item["path"]
        tu = next(iter(cluster["units"].values()))["tu"] if len(cluster["units"]) == 1 else None
        if tu:
            if tu.casefold() in TU_LIBRARY:
                return {"candidate": "provider", "library": TU_LIBRARY[tu.casefold()], "evidence": [f"unit {tu}"]}
            mapped = self.dwarf_library.get(tu.casefold())
            if mapped and mapped[0][0] == "provider":
                return {"candidate": "provider", "library": mapped[0][1], "evidence": [f"unit {tu} is DWARF path {mapped[1]}"]}
            reason = f"unit {tu} is DWARF path {mapped[1]}" if mapped else f"Metrowerks unit {tu} with no provider evidence"
            return {"candidate": "authored", "library": None, "evidence": [reason]}
        if authored_path:
            return {"candidate": "authored", "library": None, "evidence": [f"DWARF path {authored_path}"]}
        votes: Counter[str] = Counter()
        for index in members:
            if self.nodes[index]["kind"] != "function":
                continue
            for row in self.nodes[index]["names"]:
                library = next((library for library, pattern in MW_LIBRARY_RULES if pattern.search(row["name"])), None)
                if library:
                    votes[library] += 1
                    break
        if votes:
            best = max(sorted(votes), key=lambda name: votes[name])
            return {
                "candidate": "provider",
                "library": best,
                "evidence": [f"Metrowerks provider name rule ({votes[best]} of {len(members)} object members)"],
                "weak": True,
            }
        return None

    def classify(self, index: int, objects: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
        node = self.nodes[index]
        names = [row["name"] for row in node["names"]]
        verdict = objects[node["cluster"]["id"]] if node["kind"] != "gap" else None
        if verdict and verdict["candidate"] == "provider":
            return verdict
        literal = node["kind"] == "data" and any(_LITERAL.match(name) for name in names)
        if literal or any(name.startswith(("__RTTI__", "__vt__", ".p__sinit_", "__sinit_")) or _THUNK.match(name) for name in names):
            tu = self.cluster_tu(index)
            evidence = [f"compiler-emitted symbol {names[0]}"] + ([f"unit {tu}"] if tu else [])
            return {"candidate": "compiler-generated", "library": None, "evidence": evidence}
        if node["kind"] == "gap":
            if node["padding"]:
                return {"candidate": "compiler-generated", "library": None, "evidence": ["alignment padding"]}
            for item in node["signals"]:
                if item["signal"] == "dwarf-cu" and path_library(item["path"]):
                    candidate, library = path_library(item["path"])
                    return {"candidate": candidate, "library": library, "evidence": [f"DWARF path {item['path']}"]}
            gnu = self.gnu_of.get(index)
            if gnu is not None:
                return {
                    "candidate": "provider",
                    "library": gnu[self.library_key] or "unidentified GNU object",
                    "evidence": [f"GNU object at {_hex(gnu['address'])} without function symbols"],
                }
            return {"candidate": "unknown", "library": None, "evidence": []}
        return verdict or {"candidate": "unknown", "library": None, "evidence": []}

    def classifications(self, clusters: list[dict[str, Any]], *, refined: bool = True) -> list[dict[str, Any]]:
        """Each artifact's classification candidate.

        ``refined=False`` gives the segmentation classification: GNU objects
        by ``segment_library`` and no data-only members, so a member-identity
        refinement never moves a segment cut.
        """

        self.library_key = "library" if refined else "segment_library"
        self.gnu_of = {
            index: row
            for row in self.gnu
            if refined or not row.get("data_only")
            for index in row["members"] + row["gaps"] + (row.get("data") or [])
        }
        self.dwarf_library = {}
        for path in self.dwarf_paths:
            verdict = path_library(path)
            if verdict and _is_source(path):
                self.dwarf_library.setdefault(_tu_name(path).casefold(), (verdict, path))
        objects = {cluster["id"]: self.object_class(cluster) for cluster in clusters}
        classes = [self.classify(index, objects) for index in range(len(self.nodes))]
        # An unknown artifact between two artifacts of one class in its
        # window takes that class (weak).
        for window in self.windows:
            indices = [self.position[node["id"]] for node in window["nodes"] if node["kind"] != "gap"]
            known = [index for index in indices if classes[index]["candidate"] not in ("unknown", "compiler-generated")]
            for left, right in zip(known, known[1:]):
                a, b = classes[left], classes[right]
                if (a["candidate"], a["library"]) != (b["candidate"], b["library"]):
                    continue
                for index in range(left + 1, right):
                    if classes[index]["candidate"] == "unknown" and self.nodes[index]["kind"] != "gap":
                        classes[index] = {
                            "candidate": a["candidate"],
                            "library": a["library"],
                            "evidence": [f"contiguity between {self.nodes[left]['id']} and {self.nodes[right]['id']}"],
                            "weak": True,
                        }
        # Still unknown: C++ outside the library namespaces is authored (weak).
        for index, node in enumerate(self.nodes):
            if node["kind"] != "function" or classes[index]["candidate"] != "unknown":
                continue
            for row in node["names"]:
                parsed = demangle(row["name"])
                qualifier = (parsed or {}).get("qualifier") or []
                if parsed and not (qualifier and qualifier[0] in LIBRARY_NAMESPACES):
                    classes[index] = {
                        "candidate": "authored",
                        "library": None,
                        "evidence": [f"C++ symbol {row['name']} outside the library namespaces"],
                        "weak": True,
                    }
                    break
        # Still unknown: a function whose relocations (in either direction)
        # reach provider code of exactly one library, at least two artifacts
        # of it, takes that library (weak).  Authored code does not vote:
        # library code calls the program's own operator new and delete.
        neighbours = self.neighbours()
        for index, node in enumerate(self.nodes):
            if node["kind"] != "function" or classes[index]["candidate"] != "unknown":
                continue
            reached: dict[str, set[int]] = defaultdict(set)
            for other in neighbours.get(index, ()):
                if classes[other]["candidate"] == "provider":
                    reached[classes[other]["library"]].add(other)
            if len(reached) == 1 and len(next(iter(reached.values()))) >= 2:
                library, others = next(iter(reached.items()))
                shown = ", ".join(self.nodes[other]["id"] for other in sorted(others)[:4])
                classes[index] = {
                    "candidate": "provider",
                    "library": library,
                    "evidence": [f"relocations reach only {library} provider code ({len(others)} artifacts: {shown})"],
                    "weak": True,
                }
        return classes

    def neighbours(self) -> dict[int, set[int]]:
        """Non-gap artifacts each artifact's relocations connect it to, both ways."""

        if not hasattr(self, "_neighbours"):
            found: dict[int, set[int]] = defaultdict(set)
            for row in self.references:
                site, target = row["site_node"], row["target_node"]
                if site is None or target is None or site == target:
                    continue
                if self.nodes[site]["kind"] == "gap" or self.nodes[target]["kind"] == "gap":
                    continue
                found[site].add(target)
                found[target].add(site)
            self._neighbours = dict(found)
        return self._neighbours

    # -- output ----------------------------------------------------------------

    def gnu_object_row(self, row: dict[str, Any], classes: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "address": _hex(row["address"]),
            "anchor": row["anchor"],
            "gcc_compiled": row["gcc_compiled"],
            "functions": [self.nodes[index]["id"] for index in row["members"]],
            "gaps": [self.nodes[index]["id"] for index in row["gaps"]],
            "end_basis": row["end_basis"],
            "library": row["library"],
            "library_basis": row["library_basis"],
        }
        if row.get("segment_library") != row["library"]:
            # The library the segment cuts follow (member rules and coupling refine it).
            out["segment_library"] = row.get("segment_library")
        if row.get("data_only"):
            out["data_only"] = True
            out["data"] = [self.nodes[index]["id"] for index in row["data"]]
            out["local_symbols"] = row["local_symbols"]
            out["symtab_neighbours"] = [_hex(item["address"]) for item in row["symtab_neighbours"]]
        runs = self.section_runs(row, classes)
        if runs:
            out["sections"] = [
                {
                    "name": item["name"],
                    "symbol_index": item["symbol_index"],
                    "start": _hex(item["start"]),
                    "end": _hex(item["end"]),
                    "end_basis": item["end_basis"],
                }
                for item in runs
            ]
        return out

    def candidates(self, index: int) -> list[dict[str, Any]]:
        node = self.nodes[index]
        found: dict[str, dict[str, Any]] = {}
        for item in node["signals"]:
            if item.get("tu"):
                row = found.setdefault(item["tu"].casefold(), {"tu": item["tu"], "strength": item["strength"], "via": set()})
                row["via"].add(item["signal"])
                if _RANK[item["strength"]] < _RANK[row["strength"]]:
                    row["strength"] = item["strength"]
        tu = self.cluster_tu(index)
        if tu:
            row = found.setdefault(tu.casefold(), {"tu": tu, "strength": "strong", "via": set()})
            if node["contiguity_only"]:
                row["via"].update(("cluster", "text-contiguity"))
                if not any(item.get("tu") and item["tu"].casefold() == tu.casefold() and item["strength"] == "strong" for item in node["signals"]):
                    row["strength"] = "medium"
            else:
                row["strength"] = "strong"
                if len(node["cluster"]["members"]) > 1:
                    row["via"].add("cluster")
        return [
            {"tu": row["tu"], "strength": row["strength"], "via": sorted(row["via"]), "sinit_order": self.sinit_order.get(row["tu"].casefold())}
            for row in sorted(found.values(), key=lambda row: (_RANK[row["strength"]], row["tu"].casefold()))
        ]

    def build(self) -> dict[str, Any]:
        self.dwarf_signals()
        self.string_signals()
        self.name_signals()
        clusters, rounds = self.clusters()
        pool_runs, pool_conflicts = self.literal_pools()
        self.class_hints()
        self.gnu_libraries()
        cut_classes = self.classifications(clusters, refined=False)
        classes = self.classifications(clusters)
        rows = []
        for index, node in enumerate(self.nodes):
            row: dict[str, Any] = {
                "id": node["id"],
                "kind": node["kind"],
                "address": _hex(node["start"]),
                "end": _hex(node["start"] + node["size"]),
                "size": node["size"],
                "window": node["window"],
                "input_section": node["input_section"],
                "cluster": node["cluster"]["id"] if len(node["cluster"]["members"]) > 1 else None,
                "tu_candidates": self.candidates(index),
                "signals": sorted(node["signals"], key=canonical_json),
                "classification": classes[index],
            }
            if node["kind"] == "gap":
                row.update(fill=node["fill"], padding=node["padding"], labels=node["labels"])
            else:
                row.update(binding=node["binding"], names=node["names"])
                if node["size_conflict"]:
                    row["size_conflict"] = True
            if index in self.header_hint:
                row["emitted_from_header"] = self.header_hint[index]
            if index in self.gnu_of:
                row["gnu_object"] = _hex(self.gnu_of[index]["address"])
            rows.append(row)
        segments = _segments(self, rows, classes, cut_classes)
        contradictions = {canonical_json(row): row for row in self.contradictions}
        body = {
            "kind": SOURCE_GRAPH_KIND,
            "schema_version": SOURCE_GRAPH_SCHEMA,
            "source_sha256": self.image.sha256,
            "segment_size": self.segment_size,
            "rules": {
                "speech_window": [_hex(SPEECH_WINDOW[0]), _hex(SPEECH_WINDOW[1])],
                "gnu_library_rules": [[library, pattern.pattern] for library, pattern in GNU_LIBRARY_RULES],
                "gnu_member_rules": [[library, pattern.pattern] for library, pattern in GNU_MEMBER_RULES],
                # GNU objects the coupling rule moved to the library they are coupled to.
                "coupling_moves": self.coupling_moves,
                "gnu_vote_neutral_names": sorted(GNU_VOTE_NEUTRAL_NAMES),
                "mw_library_rules": [[library, pattern.pattern] for library, pattern in MW_LIBRARY_RULES],
                "library_namespaces": list(LIBRARY_NAMESPACES),
                "tu_libraries": dict(sorted(TU_LIBRARY.items())),
                "merge_rounds": rounds,
            },
            "windows": [
                {
                    "id": window["id"],
                    "kind": window["kind"],
                    "start": _hex(window["start"]),
                    "end": _hex(window["end"]),
                    "artifact_count": len(window["nodes"]),
                }
                for window in self.windows
            ],
            "gnu_objects": [self.gnu_object_row(row, classes) for row in self.gnu],
            "units": _units(rows, self.sinit_order, self.dwarf_paths),
            "clusters": sorted(
                (
                    {
                        "id": cluster["id"],
                        "members": [self.nodes[index]["id"] for index in cluster["members"]],
                        "units": sorted(
                            (
                                {"tu": unit["tu"], "signals": sorted(unit["signals"]), "artifacts": len(unit["artifacts"])}
                                for unit in cluster["units"].values()
                            ),
                            key=lambda unit: unit["tu"].casefold(),
                        ),
                        "libraries": cluster["libraries"],
                        "local_symbol_range": (
                            [cluster["local_symbols"][0], cluster["local_symbols"][-1]] if cluster["local_symbols"] else None
                        ),
                    }
                    for cluster in clusters
                    if len(cluster["members"]) > 1
                ),
                key=lambda row: int(row["id"].rsplit(":", 1)[1], 16),
            ),
            "contradictions": [contradictions[key] for key in sorted(contradictions)],
            "artifacts": rows,
            "segments": segments,
        }
        body["summary"] = _summary(body, self.edges, pool_runs, pool_conflicts)
        body["graph_sha256"] = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        return body


def _class_key(classification: dict[str, Any]) -> str:
    if classification["candidate"] == "provider":
        return f"provider:{classification['library']}"
    return classification["candidate"]


def _anchored(row: dict[str, Any]) -> bool:
    return bool(row["tu_candidates"]) and row["tu_candidates"][0]["strength"] in ("strong", "medium")


def _segments(
    graph: _Graph, rows: list[dict[str, Any]], classes: list[dict[str, Any]], cut_classes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    # Segment cuts follow the segmentation classification (``cut_classes``);
    # a segment's classification mix and data slice use the refined one.
    nodes = graph.nodes
    gnu_starts = {row["address"] for row in graph.gnu if not row.get("data_only")}

    def unit(index: int) -> str | None:
        return rows[index]["tu_candidates"][0]["tu"].casefold() if _anchored(rows[index]) else None

    neighbours = graph.neighbours()

    def reached(index: int) -> set[str]:
        return {
            _class_key(cut_classes[other])
            for other in neighbours.get(index, ())
            if cut_classes[other]["candidate"] not in ("compiler-generated", "unknown")
        }

    def families(functions: list[int]) -> list[str]:
        # Compiler-generated and unknown functions are neutral: they take
        # the family before them (or, leading a window, after them).  In a
        # neutral run between two families, the next family starts at the
        # first neutral function that opens a GNU object of it or whose
        # relocations reach that family and not the previous one: objects
        # are contiguous, so the run after it belongs to the next family.
        raw = [_class_key(cut_classes[index]) for index in functions]
        known = [value if value not in ("compiler-generated", "unknown") else None for value in raw]
        result: list[str] = []
        current = next((value for value in known if value), "unknown")
        for value in known:
            current = value or current
            result.append(current)
        position = 0
        while position < len(functions):
            if known[position] is not None:
                position += 1
                continue
            first = position
            while position < len(functions) and known[position] is None:
                position += 1
            if first == 0 or position == len(functions) or known[first - 1] == known[position]:
                continue
            before, after = known[first - 1], known[position]
            for split in range(first, position):
                index = functions[split]
                families_reached = reached(index)
                if (nodes[index]["start"] in gnu_starts and after.startswith("provider:")) or (
                    after in families_reached and before not in families_reached
                ):
                    result[split:position] = [after] * (position - split)
                    break
        return result

    def cut(left: int, right: int, families: tuple[str, str]) -> tuple[int, str]:
        if families[0] != families[1]:
            return 0, f"classification {families[0]} -> {families[1]}"
        reasons, level = [], 3
        if nodes[right]["start"] in gnu_starts:
            level = 1
            reasons.append("GNU object anchor")
        a, b = unit(left), unit(right)
        if a and b and a != b:
            level = 1
            reasons.append(f"unit {rows[left]['tu_candidates'][0]['tu']} -> {rows[right]['tu_candidates'][0]['tu']}")
        elif a != b:
            level = min(level, 2)
            reasons.append("edge of an anchored unit")
        elif nodes[left]["cluster"] is not nodes[right]["cluster"] and min(
            len(nodes[left]["cluster"]["members"]), len(nodes[right]["cluster"]["members"])
        ) > 1:
            level = min(level, 2)
            reasons.append("object cluster change")
        return level, "; ".join(reasons) or "segment size"

    pieces: list[dict[str, Any]] = []
    for window in graph.windows:
        if window["kind"] != "code":
            continue
        functions = graph.code_functions(window)
        if not functions:
            continue
        family = families(functions)
        cuts = {k: cut(functions[k - 1], functions[k], (family[k - 1], family[k])) for k in range(1, len(functions))}
        first_piece = len(pieces)
        start = 0
        while start < len(functions):
            limit = min(len(functions), start + graph.segment_size)
            stop = next((k for k in range(start + 1, limit) if cuts[k][0] == 0), None)
            if stop is None and limit < len(functions):
                for level in (1, 2):
                    options = [k for k in range(start + 1, limit + 1) if cuts[k][0] == level]
                    if options:
                        stop = options[-1]
                        break
            stop = stop or limit
            pieces.append(
                {
                    "window": window["id"],
                    "functions": functions[start:stop],
                    "span": [functions[start], functions[stop - 1]],
                    "start_cut": cuts.get(start),
                    "end_cut": cuts.get(stop),
                }
            )
            start = stop
        # The window's leading and trailing gaps belong to its outer segments.
        pieces[first_piece]["span"][0] = graph.position[window["nodes"][0]["id"]]
        pieces[-1]["span"][1] = graph.position[window["nodes"][-1]["id"]]

    by_function = {index: number for number, piece in enumerate(pieces) for index in piece["functions"]}
    # Data slices: data whose referencing functions (followed through
    # referencing data) all sit in one segment; unreferenced data follows
    # its cluster when that cluster's functions sit in one segment.
    users: dict[int, set[int]] = defaultdict(set)
    through: dict[int, set[int]] = defaultdict(set)
    for reference in graph.references:
        site, target = reference["site_node"], reference["target_node"]
        if site is None or target is None or nodes[target]["kind"] == "function":
            continue
        if site in by_function:
            users[target].add(by_function[site])
        elif nodes[site]["kind"] == "data" and site != target:
            through[site].add(target)
    for _round in range(_ROUNDS):
        changed = False
        for source in sorted(through):
            owners = users.get(source)
            if not owners:
                continue
            for target in sorted(through[source]):
                before = len(users[target])
                users[target] |= owners
                changed = changed or len(users[target]) != before
        if not changed:
            break
    data_windows = {window["id"] for window in graph.windows if window["kind"] == "data"}
    slices: dict[int, list[int]] = defaultdict(list)
    for index, node in enumerate(nodes):
        if node["window"] not in data_windows or (node["kind"] == "gap" and node["padding"]):
            continue
        owners = users.get(index, set())
        if not owners and node["kind"] == "data":
            owners = {by_function[member] for member in node["cluster"]["members"] if member in by_function}
        if len(owners) == 1:
            slices[next(iter(owners))].append(index)

    order = ("window edge", "hard", "strong", "medium", "weak")

    def edge(value: tuple[int, str] | None) -> dict[str, Any]:
        if value is None:
            return {"strength": "window edge", "reason": "code window boundary"}
        return {"strength": order[value[0] + 1], "reason": value[1]}

    def leading(sequence: list[int]) -> int:
        count = 0
        for index in sequence:
            if unit(index):
                break
            count += 1
        return count

    out = []
    for number, piece in enumerate(pieces):
        functions = piece["functions"]
        first, last = functions[0], functions[-1]
        low, high = piece["span"]
        units: dict[str, dict[str, Any]] = {}
        for index in functions:
            if not rows[index]["tu_candidates"]:
                continue
            primary = rows[index]["tu_candidates"][0]
            row = units.setdefault(
                primary["tu"].casefold(),
                {"tu": primary["tu"], "functions": 0, "strongest": primary["strength"], "sinit_order": primary["sinit_order"]},
            )
            row["functions"] += 1
            if _RANK[primary["strength"]] < _RANK[row["strongest"]]:
                row["strongest"] = primary["strength"]
        start_edge, end_edge = edge(piece["start_cut"]), edge(piece["end_cut"])
        mix = dict(sorted(Counter(_class_key(classes[index]) for index in functions).items()))
        cut_mix = dict(sorted(Counter(_class_key(cut_classes[index]) for index in functions).items()))
        # Unit changes inside the segment, with the unanchored functions
        # between the last anchor of one unit and the first of the next.
        anchored = [(order, index) for order, index in enumerate(functions) if unit(index)]
        internal = []
        for (left_order, left), (right_order, right) in zip(anchored, anchored[1:]):
            if unit(left) == unit(right):
                continue
            internal.append(
                {
                    "after": rows[left]["tu_candidates"][0]["tu"],
                    "before": rows[right]["tu_candidates"][0]["tu"],
                    "last_anchor": nodes[left]["id"],
                    "next_anchor": nodes[right]["id"],
                    "unanchored": [nodes[index]["id"] for index in functions[left_order + 1 : right_order]],
                }
            )
        segment_row = {
                "id": stable_id("source-segment", *(nodes[index]["id"] for index in functions)),
                "segment_number": number + 1,
                "window": piece["window"],
                "start": _hex(nodes[low]["start"]),
                "end": _hex(nodes[high]["start"] + nodes[high]["size"]),
                "function_count": len(functions),
                "artifacts": [nodes[index]["id"] for index in range(low, high + 1)],
                "data": [nodes[index]["id"] for index in sorted(slices.get(number, []))],
                "classification_mix": mix,
                "tu_candidates": sorted(units.values(), key=lambda row: (-row["functions"], row["tu"].casefold())),
                "unanchored_function_count": sum(1 for index in functions if not unit(index)),
                "boundary": {
                    "start": start_edge,
                    "end": end_edge,
                    "unanchored_at_start": leading(functions),
                    "unanchored_at_end": leading(list(reversed(functions))),
                },
                "internal_boundaries": internal,
                "anchor_strength": max((start_edge["strength"], end_edge["strength"]), key=order.index),
            }
        if cut_mix != mix:
            # The classification the cuts followed, before member refinements.
            segment_row["cut_classification_mix"] = cut_mix
        out.append(segment_row)
    return out


def _units(rows: list[dict[str, Any]], sinit_order: dict[str, int], dwarf_paths: list[str]) -> list[dict[str, Any]]:
    """Every translation-unit name seen, with its paths, order and extent."""

    paths: dict[str, set[str]] = defaultdict(set)
    for path in dwarf_paths:
        if _is_source(path):
            paths[_tu_name(path).casefold()].add(path)
    units: dict[str, dict[str, Any]] = {}
    for row in rows:
        for position, candidate in enumerate(row["tu_candidates"]):
            key = candidate["tu"].casefold()
            unit = units.setdefault(key, {"tu": candidate["tu"], "signals": set(), "functions": 0, "data": 0, "addresses": []})
            unit["signals"].update(candidate["via"])
            if position or not _anchored(row) or row["kind"] == "gap":
                continue
            unit["functions" if row["kind"] == "function" else "data"] += 1
            if row["kind"] == "function" and not row["names"][0]["name"].startswith("__sinit_"):
                unit["addresses"].append(int(row["address"], 16))
    out = [
        {
            "tu": unit["tu"],
            "paths": sorted(paths.get(key, ())),
            "sinit_order": sinit_order.get(key),
            "signals": sorted(unit["signals"]),
            "anchored_functions": unit["functions"],
            "anchored_data": unit["data"],
            "first_function": _hex(min(unit["addresses"])) if unit["addresses"] else None,
            "last_function": _hex(max(unit["addresses"])) if unit["addresses"] else None,
        }
        for key, unit in units.items()
    ]
    return sorted(out, key=lambda row: (int(row["first_function"], 16) if row["first_function"] else 1 << 40, row["tu"].casefold()))


def _summary(body: dict[str, Any], edges: Counter[str], pool_runs: int, pool_conflicts: int) -> dict[str, Any]:
    rows = body["artifacts"]
    classification: dict[str, Counter[str]] = defaultdict(Counter)
    signals: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        classification[row["kind"]][_class_key(row["classification"])] += 1
        for name in {item["signal"] for item in row["signals"]}:
            signals[name][row["kind"]] += 1
    functions = [row for row in rows if row["kind"] == "function"]
    data = [row for row in rows if row["kind"] == "data"]
    return {
        "artifact_counts": dict(sorted(Counter(row["kind"] for row in rows).items())),
        "classification": {kind: dict(sorted(counter.items())) for kind, counter in sorted(classification.items())},
        "signal_coverage": {name: dict(sorted(counter.items())) for name, counter in sorted(signals.items())},
        "cluster_edges": dict(sorted(edges.items())),
        "cluster_count": len(body["clusters"]),
        "unit_count": len(body["units"]),
        "gnu_object_count": len(body["gnu_objects"]),
        "data_only_member_count": sum(1 for row in body["gnu_objects"] if row.get("data_only")),
        "refined_library_objects": sum(1 for row in body["gnu_objects"] if "segment_library" in row and not row.get("data_only")),
        "literal_pool_runs": pool_runs,
        "literal_pool_conflicts": pool_conflicts,
        "contradiction_count": len(body["contradictions"]),
        "segment_count": len(body["segments"]),
        "internal_boundary_count": sum(len(segment["internal_boundaries"]) for segment in body["segments"]),
        "unanchored_at_internal_boundaries": sum(
            len(row["unanchored"]) for segment in body["segments"] for row in segment["internal_boundaries"]
        ),
        "functions_with_strong_tu_anchor": sum(1 for row in functions if row["tu_candidates"] and row["tu_candidates"][0]["strength"] == "strong"),
        "functions_without_tu_anchor": sum(1 for row in functions if not _anchored(row)),
        "functions_without_tu_anchor_by_class": dict(
            sorted(Counter(_class_key(row["classification"]) for row in functions if not _anchored(row)).items())
        ),
        "functions_without_tu_anchor_outside_gnu_objects": sum(
            1 for row in functions if not _anchored(row) and "gnu_object" not in row
        ),
        "functions_without_any_tu_candidate": sum(1 for row in functions if not row["tu_candidates"]),
        "data_without_tu_anchor": sum(1 for row in data if not _anchored(row)),
        "data_in_segment_slices": sum(len(segment["data"]) for segment in body["segments"]),
    }


def build_source_graph(elf_path: Path, *, segment_size: int = SEGMENT_SIZE) -> dict[str, Any]:
    """The deterministic translation-unit evidence graph of one ELF."""

    return _Graph(elf_path, segment_size).build()


def source_graph(root: Path, *, segment_size: int = SEGMENT_SIZE) -> dict[str, Any]:
    """The source graph of the immutable reference ELF."""

    from .constants import REFERENCE_SHA256

    body = build_source_graph(root / "support" / "socom.elf", segment_size=segment_size)
    if body["source_sha256"] != REFERENCE_SHA256:
        raise SocomError("support/socom.elf does not match the pinned reference SHA-256")
    return body


def segments_markdown(graph: dict[str, Any]) -> str:
    """A short human summary of the segments."""

    summary = graph["summary"]
    lines = [
        "# Source graph segments",
        "",
        f"Generated by `python tools/socom.py source graph`; graph `{graph['graph_sha256']}`.",
        "Every value is a candidate from ELF evidence; nothing here is an accepted owner.",
        "",
        f"- Artifacts: {', '.join(f'{key} {value}' for key, value in summary['artifact_counts'].items())}.",
        "- Function classification: "
        + ", ".join(f"{key} {value}" for key, value in summary["classification"].get("function", {}).items())
        + ".",
        f"- Functions with a strong TU anchor: {summary['functions_with_strong_tu_anchor']}; without any strong or medium"
        f" anchor: {summary['functions_without_tu_anchor']} (no candidate at all: {summary['functions_without_any_tu_candidate']}).",
        f"- Segments: {summary['segment_count']}; contradictions: {summary['contradiction_count']}.",
        "",
        "Anchor strength is the weaker of the segment's two boundaries (window edge, hard = classification change,",
        "strong = GNU anchor or a change between anchored units, medium = edge of an anchored unit or object",
        "cluster, weak = cut by size alone).",
        "",
        "| # | Range | Functions | Classification mix | TU candidates (functions) | Anchor strength |",
        "| ---: | --- | ---: | --- | --- | --- |",
    ]
    for segment in graph["segments"]:
        mix = ", ".join(f"{key} {value}" for key, value in segment["classification_mix"].items())
        units = segment["tu_candidates"]
        shown = ", ".join(f"{row['tu']} ({row['functions']})" for row in units[:5])
        if len(units) > 5:
            shown += f", +{len(units) - 5} more"
        lines.append(
            f"| {segment['segment_number']} | {segment['start']}-{segment['end']} | {segment['function_count']} "
            f"| {mix} | {shown or '-'} | {segment['anchor_strength']} |"
        )
    return "\n".join(lines) + "\n"
