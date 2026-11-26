"""Per-module check sheets: everything a second agent needs to check a module's rows.

Per row: both sides' ordered references (calls, tail calls, loaded code
addresses) named through the map, the callers of both sides, the immediate
deltas grouped per base register (a structure-layout change shows as one
repeated delta), the strings and (file, line) tokens, and for a changed pair the
differing instructions side by side. Template-family changes (calls of one
template replaced by calls of another) are reported once for the module.
"""
from __future__ import annotations

import bisect
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import functions
import mips

REG = ("zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra")
I_ALU = {0x08: "addi", 0x09: "addiu", 0x0A: "slti", 0x0B: "sltiu", 0x0C: "andi", 0x0D: "ori", 0x0E: "xori",
         0x18: "daddi", 0x19: "daddiu"}
MEMORY = {0x20: "lb", 0x21: "lh", 0x22: "lwl", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x26: "lwr", 0x27: "lwu",
          0x28: "sb", 0x29: "sh", 0x2A: "swl", 0x2B: "sw", 0x2C: "sdl", 0x2D: "sdr", 0x2E: "swr", 0x2F: "cache",
          0x31: "lwc1", 0x33: "pref", 0x36: "lqc2", 0x37: "ld", 0x39: "swc1", 0x3E: "sqc2", 0x3F: "sd",
          0x1A: "ldl", 0x1B: "ldr", 0x1E: "lq", 0x1F: "sq"}
BRANCH = {0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz", 0x14: "beql", 0x15: "bnel", 0x16: "blezl",
          0x17: "bgtzl"}
SPECIAL = {0x00: "sll", 0x02: "srl", 0x03: "sra", 0x04: "sllv", 0x06: "srlv", 0x07: "srav", 0x08: "jr",
           0x09: "jalr", 0x0A: "movz", 0x0B: "movn", 0x0C: "syscall", 0x0D: "break", 0x0F: "sync",
           0x10: "mfhi", 0x11: "mthi", 0x12: "mflo", 0x13: "mtlo", 0x14: "dsllv", 0x16: "dsrlv", 0x17: "dsrav",
           0x18: "mult", 0x19: "multu", 0x1A: "div", 0x1B: "divu", 0x20: "add", 0x21: "addu", 0x22: "sub",
           0x23: "subu", 0x24: "and", 0x25: "or", 0x26: "xor", 0x27: "nor", 0x28: "mfsa", 0x29: "mtsa",
           0x2A: "slt", 0x2B: "sltu", 0x2C: "dadd", 0x2D: "daddu", 0x2E: "dsub", 0x2F: "dsubu", 0x38: "dsll",
           0x3A: "dsrl", 0x3B: "dsra", 0x3C: "dsll32", 0x3E: "dsrl32", 0x3F: "dsra32"}
LENGTH = re.compile(r"\d+")


def disassemble(word: int, pc: int, name=None) -> str:
    """A compact rendering of one instruction; ``name`` maps a target address to a label."""

    op = word >> 26
    rs, rt, rd = (word >> 21) & 31, (word >> 16) & 31, (word >> 11) & 31
    imm = mips.simm(word)
    if word == 0:
        return "nop"
    if op == 0:
        funct = word & 0x3F
        m = SPECIAL.get(funct, "special.%02x" % funct)
        if funct in (0x00, 0x02, 0x03, 0x38, 0x3A, 0x3B, 0x3C, 0x3E, 0x3F):
            return "%s %s, %s, %d" % (m, REG[rd], REG[rt], (word >> 6) & 31)
        if funct == 0x08:
            return "jr %s" % REG[rs]
        if funct == 0x09:
            return "jalr %s" % REG[rs]
        if funct in (0x0C, 0x0D, 0x0F):
            return m
        if funct in (0x10, 0x12):
            return "%s %s" % (m, REG[rd])
        if funct in (0x18, 0x19, 0x1A, 0x1B):
            return "%s %s, %s" % (m, REG[rs], REG[rt])
        if funct in (0x21, 0x25, 0x2D) and rt == 0:
            return "move %s, %s" % (REG[rd], REG[rs])
        return "%s %s, %s, %s" % (m, REG[rd], REG[rs], REG[rt])
    if op in (2, 3):
        target = mips.jump_target(word, pc)
        return "%s %s" % ("jal" if op == 3 else "j", name(target) if name else "0x%x" % target)
    if op == 0x0F:
        return "lui %s, 0x%x" % (REG[rt], word & 0xFFFF)
    if op in I_ALU:
        value = word & 0xFFFF if op in (0x0C, 0x0D, 0x0E) else imm
        return "%s %s, %s, %s" % (I_ALU[op], REG[rt], REG[rs], hex(value) if op in (0x0C, 0x0D, 0x0E) else value)
    if op in MEMORY:
        target = ("$f%d" % rt) if op in (0x31, 0x39) else REG[rt]
        return "%s %s, %s(%s)" % (MEMORY[op], target, hex(imm) if imm >= 0 else "-" + hex(-imm), REG[rs])
    if op in BRANCH:
        return "%s %s, %s, +%d" % (BRANCH[op], REG[rs], REG[rt], 4 * imm + 4) if op in (4, 5, 0x14, 0x15) else \
            "%s %s, +%d" % (BRANCH[op], REG[rs], 4 * imm + 4)
    if op == 1:
        return "regimm.%d %s, +%d" % (rt, REG[rs], 4 * imm + 4)
    if op == 0x11:
        fmt = rs
        if fmt in (0, 4):
            return "%s %s, $f%d" % ("mfc1" if fmt == 0 else "mtc1", REG[rt], rd)
        if fmt == 8:
            return "bc1 +%d" % (4 * imm + 4)
        return "cop1.%02x.%02x $f%d, $f%d, $f%d" % (fmt, word & 0x3F, (word >> 6) & 31, rd, rt)
    if op == 0x1C:
        return "mmi.%02x %s, %s, %s" % (word & 0x3F, REG[rd], REG[rs], REG[rt])
    if op == 0x12:
        return "cop2 0x%08x" % word
    return ".word 0x%08x" % word


def qualifiers(name: str) -> list[str]:
    """The length-prefixed class qualifiers of a Metrowerks-mangled name (``Q23std42__list_deleter<...>``)."""

    out = []
    index = 0
    while index < len(name):
        if name.startswith("__", index) and index + 2 < len(name) and name[index + 2].isdigit():
            index += 2
            count = 1
        elif name[index] == "Q" and index + 1 < len(name) and name[index + 1].isdigit() and (
                index == 0 or name[index - 1] in "_PRCV"):
            count = int(name[index + 1])
            index += 2
        else:
            index += 1
            continue
        for _ in range(count):
            match = LENGTH.match(name, index)
            if not match:
                break
            length = int(match.group(0))
            out.append(name[match.end():match.end() + length])
            index = match.end() + length
        break
    return out


def family(name: str) -> str:
    """The first class template a mangled name is qualified by (``__list_deleter``), or ''."""

    for component in qualifiers(name or ""):
        if "<" in component:
            return component.split("<", 1)[0]
    return ""


class Namer:
    def __init__(self, matcher, protos):
        self.m = matcher
        self.protos = protos
        self.p_refs_by = defaultdict(set)
        self.r_refs_by = defaultdict(set)
        self.p_pointers = set()  # (target, referrer) where the referrer loads the target's address
        self.r_pointers = set()
        for f in matcher.P:
            for _, target, kind in f.typed_references():
                if target in matcher.p_by and target != f.address:
                    self.p_refs_by[target].add(f.address)
                    if kind == "ptr":
                        self.p_pointers.add((target, f.address))
        for f in matcher.R:
            for _, target, kind in f.typed_references():
                if target in matcher.r_by and target != f.address:
                    self.r_refs_by[target].add(f.address)
                    if kind == "ptr":
                        self.r_pointers.add((target, f.address))

    def proto_name(self, address: int) -> str:
        facts = self.protos.get(address)
        return facts.name if facts else "sub_%x" % address

    def p_label(self, address: int) -> str:
        pair = self.m.pairs.get(address)
        where = "0x%x" % pair.r.address if pair else "unpaired"
        return "`%s` (%s)" % (short(self.proto_name(address)), where)

    def r_label(self, address: int) -> str:
        proto = self.m.r_paired.get(address)
        if proto is None:
            return "0x%x (new)" % address
        return "0x%x = `%s`" % (address, short(self.proto_name(proto)))

    def r_name(self, address: int) -> str:
        proto = self.m.r_paired.get(address)
        return short(self.proto_name(proto)) if proto is not None else "0x%x" % address


def short(name: str, limit: int = 60) -> str:
    return name if len(name) <= limit else name[:limit - 3] + "..."


def immediate_deltas(p, r) -> list[str]:
    """Offsets that changed between aligned instructions of equal shape, per base register."""

    deltas = defaultdict(Counter)
    matcher = SequenceMatcher(None, p.shape, r.shape, autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            a, b = p.words[block.a + k], r.words[block.b + k]
            if a == b or p.masked[block.a + k] != a:
                continue  # equal, or the immediate is an address operand
            op = a >> 26
            if op in mips.LOADSTORE or op in (0x09, 0x19):
                base = (a >> 21) & 31
                if base in (0, mips.GP):
                    continue
                deltas[REG[base]][mips.simm(b) - mips.simm(a)] += 1
    out = []
    for register in sorted(deltas):
        parts = ["%+#x x%d" % (delta, count) for delta, count in sorted(deltas[register].items(), key=lambda x: (-x[1], x[0]))]
        out.append("%s: %s" % (register, ", ".join(parts)))
    return out


class DataNamer:
    """Names data operands through the prototype's symbols; release addresses through paired operands."""

    def __init__(self, matcher, proto_image=None, release_image=None, rows_of_interest=()):
        self.m = matcher
        symbols = []
        if proto_image is not None:
            for symbol in proto_image.symbols:
                if symbol.kind != 2 and symbol.name and not symbol.name.startswith(".") and symbol.address:
                    symbols.append((symbol.address, symbol.size, symbol.name))
        symbols.sort()
        self.symbols = symbols
        self.starts = [s[0] for s in symbols]
        self.p_strings = functions.Regions(proto_image, []) if proto_image is not None else None
        self.r_strings = functions.Regions(release_image, []) if release_image is not None else None
        votes = defaultdict(Counter)
        pairs = [pair for pair in matcher.pairs.values() if pair.p.key == pair.r.key]
        for pair in pairs:
            r_refs = dict(pair.r.data_refs)
            for index, address in pair.p.data_refs:
                if index in r_refs:
                    votes[r_refs[index]][address] += 1
        for pair in rows_of_interest:
            mapping = aligned(pair.p.masked, pair.r.masked)
            r_refs = dict(pair.r.data_refs)
            for index, address in pair.p.data_refs:
                other = mapping.get(index)
                if other is not None and other in r_refs:
                    votes[r_refs[other]][address] += 1
        self.release_to_proto = {r: c.most_common(1)[0][0] for r, c in votes.items()}

    def proto(self, address: int) -> str:
        text = self.p_strings.string_at(address) if self.p_strings else None
        if text is not None:
            return '"%s"' % short(text.replace("\n", "\\n"), 40)
        index = bisect.bisect_right(self.starts, address) - 1
        if index >= 0:
            start, size, name = self.symbols[index]
            if address == start:
                return name
            if address < start + max(size, 1) or address - start < 0x100:
                return "%s+0x%x" % (name, address - start)
        return "0x%x" % address

    def release(self, address: int) -> str:
        mapped = self.release_to_proto.get(address)
        if mapped is not None:
            return self.proto(mapped)
        text = self.r_strings.string_at(address) if self.r_strings else None
        if text is not None:
            return '"%s"' % short(text.replace("\n", "\\n"), 40)
        return "0x%x (unmapped)" % address


def aligned(a, b) -> dict[int, int]:
    out = {}
    for block in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            out[block.a + k] = block.b + k
    return out


FULL_DIFF = 200  # instructions: below this the whole function is listed side by side
DIFF_LINES = 400  # at most this many lines per row; the rest is counted, not dropped silently


def masked_diff(p, r, namer, data) -> list[str]:
    """Side-by-side listing aligned on masked words; data operands named on both sides."""

    p_data = dict(p.data_refs)
    r_data = dict(r.data_refs)

    def left(i):
        text = disassemble(p.words[i], p.address + 4 * i, lambda t: short(namer.proto_name(t), 36))
        if i in p_data:
            text += "  ; " + data.proto(p_data[i])
        return "+%03x %s" % (4 * i, text)

    def right(j):
        text = disassemble(r.words[j], r.address + 4 * j, lambda t: namer.r_name(t)[:36])
        if j in r_data:
            text += "  ; " + data.release(r_data[j])
        return "+%03x %s" % (4 * j, text)

    full = max(len(p.words), len(r.words)) < FULL_DIFF
    lines = []
    skipped = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, p.masked, r.masked, autojunk=False).get_opcodes():
        if tag == "equal":
            if full:
                lines.extend("  %-62s | %s" % (left(i1 + k), right(j1 + k)) for k in range(i2 - i1))
            else:
                skipped += i2 - i1
                lines.append("  ... %d equal instructions" % (i2 - i1))
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            lines.append("* %-62s | %s" % (left(i1 + k) if i1 + k < i2 else "", right(j1 + k) if j1 + k < j2 else ""))
    if len(lines) > DIFF_LINES:
        omitted = len(lines) - DIFF_LINES
        lines = lines[:DIFF_LINES] + ["... %d more lines omitted (raise DIFF_LINES in sheets.py to see them)" % omitted]
    return lines


SLOT_SCORED = 60  # candidates of a new/removed row's slot that get a similarity
SLOT_SHOWN = 8  # ... and how many of them are listed


def similarity(a, b) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def stored_pointers(image, spans, starts: set[int]) -> dict[int, list[int]]:
    """Function address -> data addresses outside code that hold it (callback tables, vtables)."""

    words = mips.words_of(image.data)
    spans = sorted(spans)
    begins = [s for s, _ in spans]
    out = defaultdict(list)
    for index, value in enumerate(words):
        if value not in starts:
            continue
        address = image.base + 4 * index
        k = bisect.bisect_right(begins, address) - 1
        if k >= 0 and spans[k][0] <= address < spans[k][1]:
            continue  # an instruction, not stored data
        out[value].append(address)
    return out


def vtable_places(tables) -> dict[int, list[str]]:
    out = defaultdict(list)
    for table in (tables or {}).values():
        for k, target in enumerate(table.slots):
            out[target].append("%s%s +0x%x" % (table.name, " (offset %d)" % table.offset if table.offset else "", 8 + 4 * k))
    return out


def slot_lines(matcher, namer, row) -> list[str]:
    """For a new or removed row: its paired neighbours and what the other side has between them."""

    if row["class"] == "new":
        side, index = matcher.R, matcher.r_index[row["release_address"]]
        paired = lambda f: f.address in matcher.r_paired  # noqa: E731
        partner = lambda f: matcher.p_by[matcher.r_paired[f.address]]  # noqa: E731
        other, other_index, other_paired = matcher.P, matcher.p_index, lambda f: f.address in matcher.pairs  # noqa: E731
        label_self, label_other = namer.r_label, namer.p_label
    else:
        side, index = matcher.P, matcher.p_index[row["prototype_address"]]
        paired = lambda f: f.address in matcher.pairs  # noqa: E731
        partner = lambda f: matcher.pairs[f.address].r  # noqa: E731
        other, other_index, other_paired = matcher.R, matcher.r_index, lambda f: f.address in matcher.r_paired  # noqa: E731
        label_self, label_other = namer.p_label, namer.r_label
    before = next((side[k] for k in range(index - 1, -1, -1) if paired(side[k])), None)
    after = next((side[k] for k in range(index + 1, len(side)) if paired(side[k])), None)
    out = ["- slot: between %s and %s" % (label_self(before.address) if before else "the start",
                                          label_self(after.address) if after else "the end")]
    if before and after:
        lo, hi = other_index[partner(before).address], other_index[partner(after).address]
        if lo < hi:
            between = [f for f in other[lo + 1:hi] if not other_paired(f)]
            me = side[index]
            ranked = between
            if len(between) > 1:
                # the most similar first (scored for at most SLOT_SCORED of them), at most SLOT_SHOWN shown
                scored = []
                for f in between[:SLOT_SCORED]:
                    small, large = sorted((me.size, f.size))
                    value = similarity(me.masked, f.masked) if large and small / large >= 0.25 else 0.0
                    scored.append((value, f))
                ranked = [f for _, f in sorted(scored, key=lambda x: (-x[0], x[1].address))] + between[SLOT_SCORED:]
                values = {f.address: v for v, f in scored}
            else:
                values = {}
            shown = ["%s%s" % (label_other(f.address), " %.2f" % values[f.address] if f.address in values else "")
                     for f in ranked[:SLOT_SHOWN]]
            out.append("- unpaired on the other side in that slot (most similar first): " + (", ".join(shown) or "none")
                       + (" (+%d more)" % (len(between) - SLOT_SHOWN) if len(between) > SLOT_SHOWN else ""))
        else:
            out.append("- the neighbours' partners are out of order on the other side")
    return out


def module_sheet(module: str, matcher, rows: list[dict], protos: dict, proto_image=None, release_image=None,
                 selected: list[dict] | None = None, title: str | None = None) -> str:
    import report  # late: report imports protofacts too

    namer = Namer(matcher, protos)
    p_vt = vtable_places(getattr(matcher, "proto_tables", None))
    r_vt = vtable_places(getattr(matcher, "release_tables", None))
    p_stored = stored_pointers(proto_image, [(f.address, f.end) for f in matcher.P], set(matcher.p_by)) \
        if proto_image is not None else {}
    r_stored = stored_pointers(release_image, [(f.address, f.end) for f in matcher.R], set(matcher.r_by)) \
        if release_image is not None else {}
    if selected is None:
        selected = [row for row in rows if report.module_label(row) == module]
    interesting = [matcher.pairs[row["prototype_address"]] for row in selected
                   if row["prototype_address"] in matcher.pairs and row["release_address"] is not None]
    data = DataNamer(matcher, proto_image, release_image, [p for p in interesting if p.p.key != p.r.key])
    name = title or module
    out = ["# Check sheet: %s" % name, "",
           "Generated by `python tools/release/compare.py --sheet %s`; not tracked. %d rows." % (module, len(selected)),
           ""]
    counts = Counter(row["class"] for row in selected)
    out.append("Classes: " + ", ".join("%s %d" % (c, counts[c]) for c in report.CLASSES if counts[c]) + ".")
    out.append("")
    families = defaultdict(set)
    for pair in interesting:
        # templates whose calls disappear and templates whose calls appear (callees named through the map)
        before = {family(namer.proto_name(t)) for _, t in pair.p.references()} - {""}
        after = {family(namer.proto_name(matcher.r_paired[t])) for _, t in pair.r.references()
                 if t in matcher.r_paired} - {""}
        for old in before - after:
            for new in (after - before) or {"(none)"}:
                families[(old, new)].add(pair.r.address)
    if families:
        out += ["## Template families replaced", "",
                "| prototype calls | release calls | functions | first release rows |", "|---|---|---|---|"]
        for (old, new), where in sorted(families.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            out.append("| %s | %s | %d | %s |" % (old, new, len(where), ", ".join("0x%x" % a for a in sorted(where)[:6])))
        out.append("")
    exact = [row for row in selected if row["class"] == "exact"]
    if exact:
        out += ["## Exact rows", "", "| release | prototype | symbol | references | flags |", "|---|---|---|---|---|"]
        for row in exact:
            pair = matcher.pairs[row["prototype_address"]]
            out.append("| 0x%x | 0x%x | `%s` | %d, %d consistent | %s |" % (
                row["release_address"], row["prototype_address"], short(row["prototype_symbol"]),
                len(pair.p.references()), pair.call_consistent, ",".join(row["flags"]) or "-"))
        out.append("")
    out += ["## Other rows", ""]
    for row in selected:
        if row["class"] == "exact":
            continue
        rel, proto = row["release_address"], row["prototype_address"]
        head = "### %s %s" % ("0x%x" % rel if rel is not None else "-", row["class"])
        if proto is not None:
            head += " - prototype 0x%x `%s`" % (proto, short(row["prototype_symbol"], 80))
        out.append(head)
        out.append("")
        facts = []
        if row["similarity"] is not None:
            facts.append("similarity %.3f, operations %.3f, size %+d" % (
                row["similarity"], row["operation_similarity"], row["size_delta"]))
        facts.append("evidence %s; flags %s; owner %s" % (
            ",".join(row["evidence"]) or "-", ",".join(row["flags"]) or "-", row["owner_file"] or "-"))
        out.append("- " + "; ".join(facts))
        if row["class"] in ("new", "removed"):
            out.extend(slot_lines(matcher, namer, row))
        p = matcher.p_by.get(proto) if proto is not None else None
        r = matcher.r_by.get(rel) if rel is not None else None
        if p is not None:
            refs = [namer.p_label(t) if t in matcher.p_by else "0x%x" % t for _, t in p.references()]
            out.append("- prototype references: " + (", ".join(refs) or "none"))
            callers = sorted(namer.p_refs_by.get(proto, ()))
            if callers or not p_vt.get(proto):
                out.append("- prototype callers (& loads its address): " + (", ".join(
                    ("&" if (proto, c) in namer.p_pointers else "") + namer.p_label(c) for c in callers[:12]) or "none")
                           + (" (+%d)" % (len(callers) - 12) if len(callers) > 12 else ""))
            if p_vt.get(proto):
                out.append("- prototype vtable slots: " + ", ".join(p_vt[proto][:8])
                           + (" (+%d)" % (len(p_vt[proto]) - 8) if len(p_vt[proto]) > 8 else ""))
            stored = p_stored.get(proto, [])
            if stored:
                out.append("- prototype pointers to it in data: " + ", ".join(data.proto(a) for a in stored[:8])
                           + (" (+%d)" % (len(stored) - 8) if len(stored) > 8 else ""))
            names = list(dict.fromkeys(data.proto(a) for _, a in p.data_refs))
            if names:
                out.append("- prototype data: " + ", ".join(names[:20]) + (" (+%d)" % (len(names) - 20) if len(names) > 20 else ""))
        if r is not None:
            refs = [namer.r_label(t) if t in matcher.r_by else "0x%x" % t for _, t in r.references()]
            out.append("- release references: " + (", ".join(refs) or "none"))
            callers = sorted(namer.r_refs_by.get(rel, ()))
            if callers or not r_vt.get(rel):
                out.append("- release callers (& loads its address): " + (", ".join(
                    ("&" if (rel, c) in namer.r_pointers else "") + namer.r_label(c) for c in callers[:12]) or "none")
                           + (" (+%d)" % (len(callers) - 12) if len(callers) > 12 else ""))
            if r_vt.get(rel):
                out.append("- release vtable slots: " + ", ".join(r_vt[rel][:8])
                           + (" (+%d)" % (len(r_vt[rel]) - 8) if len(r_vt[rel]) > 8 else ""))
            stored = r_stored.get(rel, [])
            if stored:
                out.append("- release pointers to it in data: " + ", ".join("0x%x" % a for a in stored[:8])
                           + (" (+%d)" % (len(stored) - 8) if len(stored) > 8 else ""))
            names = list(dict.fromkeys(("0x%x = " % a if a not in data.release_to_proto else "") + data.release(a)
                                       for _, a in r.data_refs))
            if names:
                out.append("- release data: " + ", ".join(names[:20]) + (" (+%d)" % (len(names) - 20) if len(names) > 20 else ""))
        for side, fn in (("prototype", p), ("release", r)):
            if fn is not None and (fn.strings or fn.lines):
                items = sorted(fn.strings)[:6] + ["%s:%d" % token for token in sorted(fn.lines)[:6]]
                out.append("- %s strings: %s" % (side, "; ".join(repr(s) for s in items)))
        if p is not None and r is not None:
            deltas = immediate_deltas(p, r)
            if deltas:
                out.append("- immediate deltas: " + "; ".join(deltas))
            if p.key != r.key:
                out += ["", "```text"] + masked_diff(p, r, namer, data) + ["```"]
        out.append("")
    return "\n".join(out) + "\n"
