#!/bin/bash
# portlay.sh [name]: the port's own class layouts from the comparison build's debug info
# ($SCRATCH/fp/<name>.elf, made by fpbuild.sh; default head) into $SCRATCH/fp/<name>.lay.json:
# {qualified class: [byte size, [[offset, member, lowest bit or -1, bit width or 0], ...],
# [[offset, base class], ...]]}, the first definition with members of each name. auditpack.py
# reads it (through cz.py -p) to show the port's member next to DWARF's where they differ.
# Read-only on the checkout; about a minute.
set -u
. "$(dirname "$(readlink -f "$0")")/env.sh"
N=${1:-head}; E=$SCRATCH/fp/$N.elf; J=$SCRATCH/fp/$N.lay.json
[ -f "$E" ] || { echo "portlay.sh: no $E (run fpbuild.sh first)" >&2; exit 1; }
mips64r5900el-ps2-elf-readelf --debug-dump=info "$E" 2>/dev/null | python3 -c '
import sys, re, json
TAG = re.compile(r"^ <(\d+)><([0-9a-f]+)>: Abbrev Number: \d+ \((DW_TAG_\w+)\)")
ATTR = re.compile(r"^    <[0-9a-f]+>\s+(DW_AT_\w+)\s*: ?(.*)$")
KEEP = {"DW_TAG_structure_type", "DW_TAG_class_type", "DW_TAG_union_type", "DW_TAG_namespace",
        "DW_TAG_member", "DW_TAG_inheritance", "DW_TAG_compile_unit"}
CONT = {"DW_TAG_structure_type", "DW_TAG_class_type", "DW_TAG_union_type", "DW_TAG_namespace"}
names = {}          # die offset -> qualified name (classes)
out = {}
stack = []          # [(depth, tag, name, die dict)]
cur = None
def num(v):
    m = re.search(r"DW_OP_plus_uconst: (\d+)", v)
    if m: return int(m.group(1))
    m = re.match(r"\s*(-?\d+|0x[0-9a-f]+)\b", v)
    return int(m.group(1), 0) if m else None
def sval(v):
    return v.rsplit(": ", 1)[-1].strip() if "indirect" in v or "(" in v[:2] else v.strip()
def close(d):
    if d is None: return
    tag = d["tag"]
    if tag in CONT:
        pass
pending = []        # class dies to finish: (qname, die)
def finish(c):
    q = c.get("q")
    if not q or c.get("decl") or c["tag"] == "DW_TAG_namespace": return
    mem = c.get("mem", [])
    if q in out and out[q][1]: return
    if not mem and q in out: return
    out[q] = [c.get("size") or 0, mem, c.get("bases", [])]
for line in sys.stdin:
    if line.startswith(" <"):
        m = TAG.match(line)
        if not m: continue
        depth, off, tag = int(m.group(1)), int(m.group(2), 16), m.group(3)
        while stack and stack[-1]["depth"] >= depth:
            finish(stack.pop())
        cur = {"depth": depth, "off": off, "tag": tag} if tag in KEEP else None
        if cur is not None and tag in CONT or (cur is not None and tag == "DW_TAG_compile_unit"):
            stack.append(cur)
        elif cur is not None:
            par = stack[-1] if stack and stack[-1]["depth"] == depth - 1 else None
            cur["parent"] = par
        if cur is None:
            stack.append({"depth": depth, "tag": tag, "skip": True})
        continue
    if cur is None: continue
    m = ATTR.match(line)
    if not m: continue
    a, v = m.group(1), m.group(2)
    t = cur["tag"]
    if a == "DW_AT_name":
        cur["name"] = sval(v)
        if t in CONT:
            pre = [s.get("name") for s in stack[:-1] if s["tag"] in CONT]
            cur["q"] = "::".join([p for p in pre if p] + [cur["name"]]) if all(pre) else None
            if cur.get("q"): names[cur["off"]] = cur["q"]
        elif t == "DW_TAG_member" and cur.get("parent") is not None:
            cur["parent"].setdefault("mem", []).append(cur.setdefault("row", [None, cur["name"], -1, 0]))
            cur["row"][1] = cur["name"]
    elif a == "DW_AT_declaration" and t in CONT:
        cur["decl"] = True
    elif a == "DW_AT_byte_size":
        if t in CONT: cur["size"] = num(v)
        else: cur["bsz"] = num(v)
    elif a == "DW_AT_data_member_location":
        cur["loc"] = num(v)
    elif a == "DW_AT_bit_size":
        cur["bits"] = num(v)
    elif a == "DW_AT_bit_offset":
        cur["bitoff_be"] = num(v)
    elif a == "DW_AT_data_bit_offset":
        cur["dbo"] = num(v)
    elif a == "DW_AT_type" and t == "DW_TAG_inheritance" and cur.get("parent") is not None:
        r = re.search(r"<0x([0-9a-f]+)>", v)
        if r: cur["parent"].setdefault("bases", []).append(cur.setdefault("brow", [None, int(r.group(1), 16)]))
    # fill the member row as attributes arrive
    row = cur.get("row")
    if row is not None:
        if cur.get("dbo") is not None:
            row[0], row[2], row[3] = cur["dbo"] // 8 if cur.get("bits") is None else (cur["dbo"] // 32) * 4, \
                (cur["dbo"] % 32 if cur.get("bits") is not None else -1), cur.get("bits") or 0
        else:
            row[0] = cur.get("loc")
            if cur.get("bits") is not None and cur.get("bitoff_be") is not None:
                us = cur.get("bsz") or 4
                row[2], row[3] = us * 8 - cur["bitoff_be"] - cur["bits"], cur["bits"]
    br = cur.get("brow")
    if br is not None and cur.get("loc") is not None:
        br[0] = cur["loc"]
while stack:
    finish(stack.pop())
for q, (sz, mem, bases) in out.items():
    out[q] = [sz, [r for r in mem if r[0] is not None], [[o, names.get(b, "?")] for o, b in bases if o is not None]]
json.dump(out, sys.stdout, separators=(",", ":"))
' > "$J.tmp" && mv "$J.tmp" "$J" && ls -la "$J"
