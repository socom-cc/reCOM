"""The ODR header-emit check of stage 4 owner plans (``source plan emit-check``)."""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from tools._socom.source_cache import SCHEMA
from tools._socom.source_emit_check import HeaderIndex, body_shape, emit_check, review_note

GRAPH = "f" * 64
HEADER = """#pragma once
namespace zdb
{
\tclass CNodeVector : public std::vector<int>
\t{
\t};
}

class CZSIScript
{
public:
\tvirtual void SetTimeScale(float);
};

class Particle
{
public:
\tclass Instance
\t{
\t\tvoid Tick(float);
\t};
};

template<class Object>
class RTArray
{
\tObject* m_data;
};

class CFwd;
class CAiMap
{
\tvoid Find(); // class CDecoy { in a comment
};

extern "C" {
template <typename T>
float clampf(T& value);
}
"""

# (address, kind, names, binding) of the artifacts; names carry the binding.
ARTIFACTS = [
    (0x1000, "function", ["__dt__Q23zdb11CNodeVectorFv"], "13"),  # implicit, kept by a.cpp, used by b.cpp's __sinit
    (0x1100, "function", ["SetTimeScale__10CZSIScriptFf"], "13"),  # only its vtable references it
    (0x1200, "function", ["__ct__10CZSIScriptFv"], "GLOBAL"),
    (0x1300, "function", ["Tick__Q28Particle8InstanceFf"], "13"),
    (0x1400, "function", ["GetPacketMsg__7CPacketFv"], "13"),  # two units, no header declares CPacket
    (0x1500, "function", ["GetNext__22RTArray<11ACTIVE_ANIM>Fb"], "WEAK"),  # a project template: one unit
    (0x1600, "function", ["@12@__dt__10CZSIScriptFv"], "13"),  # a this-adjusting thunk
    (0x1700, "function", ["__dt__Q23std12allocator<c>Fv"], "13"),  # MSL
    (0x1800, "function", ["Only__7CSingleFv"], "13"),  # one unit: defined in its .cpp
    (0x1900, "function", ["Use__6COtherFv"], "13"),  # a referencer no plan or draft places
    (0x1a00, "function", ["__dt__4CFwdFv"], "13"),  # implicit, but only a forward declaration
    (0x1b00, "function", ["Get__4CDwfFv"], "13"),  # two units; CDwf's members name a DWARF header unit
    (0x1c00, "function", ["Set__4CDwfFv"], "GLOBAL"),
    (0x1d00, "function", ["Cell__Q26CAiMap4cellFv"], "13"),  # nested class only its enclosing class declares
    (0x5000, "function", ["__sinit_b.cpp"], "GLOBAL"),
    (0x6000, "function", ["Build__5CBodyFv"], "GLOBAL"),
    (0x6100, "function", ["Run__5CBodyFv"], "GLOBAL"),
    (0x7000, "function", ["Stray__6CStrayFv"], "GLOBAL"),
    (0x9000, "data", ["__vt__10CZSIScript"], "GLOBAL"),
]
REFS = [
    (0x5000, 0x1000), (0x9000, 0x1100), (0x1200, 0x9000), (0x6000, 0x1200), (0x6100, 0x1300), (0x6100, 0x1400),
    (0x1800, 0x1500), (0x1100, 0x1800), (0x7000, 0x1900), (0x6100, 0x1b00), (0x6000, 0x1d00),
]


def _id(address: int, kind: str = "function") -> str:
    return f"socom:{kind}:0x{address:x}"


def _cache(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO meta VALUES ('graph_sha256', ?)", (GRAPH,))
        for address, kind, names, binding in ARTIFACTS:
            header = "Z:\\dev\\gamez\\zFoo\\zdwf.h" if address == 0x1c00 else None
            connection.execute(
                "INSERT INTO artifacts (id, kind, address, binding, classification, library, emitted_from_header) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_id(address, kind), kind, address, binding, "provider" if address == 0x1700 else "authored",
                 "MSL" if address == 0x1700 else None, header),
            )
            for number, name in enumerate(names):
                connection.execute("INSERT INTO names VALUES (?, ?, ?, ?)", (_id(address, kind), name, binding, address + number))
        kinds = {address: kind for address, kind, _names, _binding in ARTIFACTS}
        for site, target in REFS:
            connection.execute(
                "INSERT INTO refs (site, site_artifact, target, target_artifact) VALUES (?, ?, ?, ?)",
                (site, _id(site, kinds[site]), target, _id(target, kinds[target])),
            )
        connection.execute("INSERT INTO dwarf_cus (die_offset, kind, artifact) VALUES ('0x10', 'function', ?)", (_id(0x1c00),))
        connection.commit()
    return path


def _row(unit: str, *addresses: int, kind: str = "function") -> dict:
    return {"translation_unit": unit, "classification": "authored", "workspace_path": f"src/gamez/zFoo/{unit}",
            "confidence": "high", "evidence": ["x"],
            "artifacts": [{"artifact": _id(address, "data" if address == 0x9000 else kind), "confidence": "high", "basis": "x"}
                          for address in addresses]}


def _workspace(tmp_path: Path) -> tuple[Path, Path, dict, dict]:
    root = tmp_path
    (root / "src" / "gamez" / "zFoo" / "sub").mkdir(parents=True)
    (root / "src" / "gamez" / "zFoo" / "zfoo.h").write_text(HEADER, encoding="utf-8")
    (root / "src" / "gamez" / "zFoo" / "sub" / "zdwf.h").write_text("#pragma once\n", encoding="utf-8")
    cache = _cache(root / "build" / "cache" / "source-graph.sqlite")
    first = {
        "kind": "socom-source-owner-plan", "schema_version": 2, "work_item_id": "socom:work:source-segment-001",
        "graph_sha256": GRAPH,
        "owners": [_row("a.cpp", 0x1000, 0x1100, 0x1200, 0x1300, 0x1400, 0x1500, 0x1600, 0x1700, 0x1800, 0x1900, 0x1a00,
                        0x1b00, 0x1c00, 0x1d00, 0x9000)],
        # The row cites the namespace line, not the class.
        "header_emits": [{"artifact": _id(0x1000), "header": "src/gamez/zFoo/zfoo.h", "reason": "inline",
                          "evidence": ["src/gamez/zFoo/zfoo.h:2 declares it; used by a.cpp and b.cpp"]}],
        "notes": [],
    }
    second = {
        "kind": "socom-source-owner-plan", "schema_version": 2, "work_item_id": "socom:work:source-segment-002",
        "graph_sha256": GRAPH, "owners": [_row("b.cpp", 0x5000, 0x6100), _row("c.cpp", 0x6000)], "header_emits": [], "notes": [],
    }
    folder = root / "build" / "source-plans"
    folder.mkdir(parents=True)
    for plan in (first, second):
        (folder / f"{plan['work_item_id'].replace(':', '-')}.json").write_text(json.dumps(plan), encoding="utf-8")
    # Neither an evidence file nor a .prev copy is a plan.
    (folder / "socom-work-source-segment-001-evidence.json").write_text("{}", encoding="utf-8")
    (folder / "socom-work-source-segment-001.prev.json").write_text(json.dumps(second), encoding="utf-8")
    return root, cache, first, second


def test_the_header_index_reads_definitions_and_scopes(tmp_path: Path) -> None:
    root, _cache_path, _first, _second = _workspace(tmp_path)
    index = HeaderIndex(root)
    found = {(decl["chain"], decl["line"], decl["template"]) for decl in index.decls if decl["kind"] != "namespace"}
    assert (("zdb", "CNodeVector"), 4, False) in found and (("Particle", "Instance"), 18, False) in found
    assert (("RTArray",), 25, True) in found and (("clampf",), 38, True) in found
    # Forward declarations, comments and elaborated types are not definitions.
    assert not any(decl["chain"][-1] in ("CFwd", "CDecoy", "Object") for decl in index.decls)
    assert [decl["line"] for decl in index.matches(("CNodeVector",), kinds=("class",))] == [4]
    instance = index.matches(("Particle", "Instance"), kinds=("class",))
    assert [(decl["line"], decl["end"]) for decl in instance] == [(18, 21)]
    assert index.matches(("Instance",), kinds=("class",)) == []


def test_emit_check_reports_the_rulings(tmp_path: Path) -> None:
    root, cache, first, _second = _workspace(tmp_path)
    report = emit_check(root, cache)
    assert report["plans_read"] == 2 and report["counts"]["plans"] == 2
    result = report["plans"]["socom:work:source-segment-001"]
    emits = {row["artifact"]: row for row in result["missing_emits"]}
    # The vtable's constructor caller (c.cpp) counts; the thunk, MSL and one-unit copies are not expected.
    assert sorted(emits) == [_id(0x1100), _id(0x1300), _id(0x1500), _id(0x1b00), _id(0x1d00)]
    script = emits[_id(0x1100)]
    assert script["units"] == ["a.cpp", "c.cpp"] and script["via_vtable"]["constructor_callers"] == 1
    assert (script["suggested"]["header"], script["suggested"]["line"]) == ("src/gamez/zFoo/zfoo.h", 9)
    assert emits[_id(0x1300)]["suggested"]["line"] == 18
    template = emits[_id(0x1500)]
    assert template["units"] == ["a.cpp"] and template["reason"] == "template" and template["suggested"]["line"] == 25
    dwarf = emits[_id(0x1b00)]["suggested"]
    assert (dwarf["header"], dwarf["source"], dwarf["mapped"]) == ("src/gamez/zFoo/sub/zdwf.h", "dwarf-header-unit", "by file name in the module tree")
    nested = emits[_id(0x1d00)]["suggested"]
    assert nested["line"] == 31 and "enclosing class" in nested["evidence"]
    assert [row["artifact"] for row in result["missing_notes"]] == [_id(0x1400)]
    assert "no header declares CPacket" in result["missing_notes"][0]["note"]
    assert [row["artifact"] for row in result["undetermined"]] == [_id(0x1900)]
    (wrong,) = result["wrong_citations"]
    assert wrong["artifact"] == _id(0x1000) and wrong["citations"][0]["line_text"] == "namespace zdb"
    assert wrong["declared_at"] == ["src/gamez/zFoo/zfoo.h:4"]
    assert result["counts"]["copies_checked"] == 10
    assert "5 missing header emits, 1 missing" in review_note(result, "p.json")

    # The fixed plan is clean: emits recorded, the note names the artifact, the citation declares the class.
    fixed = copy.deepcopy(first)
    fixed["header_emits"][0]["evidence"] = ["src/gamez/zFoo/zfoo.h:4 declares class CNodeVector; a.cpp and b.cpp"]
    for address in (0x1100, 0x1300, 0x1500, 0x1b00, 0x1d00):
        fixed["header_emits"].append({"artifact": _id(address), "header": "src/gamez/zFoo/zfoo.h", "reason": "inline", "evidence": ["x"]})
    fixed["notes"] = ["GetPacketMsg__7CPacketFv 0x1400: used by 2 units (a.cpp, b.cpp); no header declares CPacket"]
    clean = emit_check(root, cache, items=["socom:work:source-segment-001"],
                       replace={"socom:work:source-segment-001": ("p.json", fixed)})["plans"]["socom:work:source-segment-001"]
    assert clean["counts"]["missing_emits"] == clean["counts"]["missing_notes"] == clean["counts"]["wrong_citations"] == 0
    assert review_note(clean, "p.json") is None


def test_a_note_must_say_so_for_the_artifact_it_names(tmp_path: Path) -> None:
    root, cache, first, _second = _workspace(tmp_path)
    item = "socom:work:source-segment-001"

    def notes(*values: str) -> list[str]:
        plan = dict(first, notes=list(values))
        result = emit_check(root, cache, items=[item], replace={item: ("p.json", plan)})["plans"][item]
        return [row["artifact"] for row in result["missing_notes"]]

    # A note naming the copy among one-unit copies, and saying "no header declares" only of another artifact, is not enough.
    assert notes("no header emit for GetPacketMsg__7CPacketFv 0x1400 (one unit only); Use 0x1900: used by 2 units; "
                 "no header declares COther") == [_id(0x1400)]
    assert notes("0x1400 GetPacketMsg: used by 2 units; no provisional header under src/ declares CPacket") == []
    assert notes("used by 2 units; no header declares them, so no emit: GetPacketMsg 0x1400, Other 0x1900") == []


# -- the body shape of special members (ELF instructions) ----------------------------------------------

ZERO, V0, V1, A0, A1, T0, T1, S0, S1, SP, RA = 0, 2, 3, 4, 5, 8, 9, 16, 17, 29, 31


def _r(rs: int, rt: int, rd: int, funct: int, sa: int = 0) -> int:
    return (rs << 21) | (rt << 16) | (rd << 11) | (sa << 6) | funct


def _i(op: int, rs: int, rt: int, imm: int) -> int:
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xFFFF)


def move(rd: int, rs: int) -> int:
    return _r(rs, ZERO, rd, 0x21)


def addiu(rt: int, rs: int, imm: int) -> int:
    return _i(0x09, rs, rt, imm)


def lw(rt: int, offset: int, base: int) -> int:
    return _i(0x23, base, rt, offset)


def sw(rt: int, offset: int, base: int) -> int:
    return _i(0x2B, base, rt, offset)


def lb(rt: int, offset: int, base: int) -> int:
    return _i(0x20, base, rt, offset)


def sb(rt: int, offset: int, base: int) -> int:
    return _i(0x28, base, rt, offset)


def branch(op: int, rs: int, rt: int, pc: int, target: int) -> int:
    return _i(op, rs, rt, (target - pc - 4) >> 2)


def jal(target: int) -> int:
    return (0x03 << 26) | ((target >> 2) & 0x03FFFFFF)


def lui(rt: int, imm: int) -> int:
    return _i(0x0F, 0, rt, imm)


JR_RA = _r(RA, 0, 0, 0x08)
NOP = 0
DSLL32_FLAG, DSRA32_FLAG = _r(0, S1, V0, 0x3C, 16), _r(0, V0, V0, 0x3F, 16)


def _words(start: int, words: list[int]) -> tuple[dict[int, int], int]:
    return {start + 4 * index: value for index, value in enumerate(words)}, 4 * len(words)


def _callee(address, symbol):
    names = {0x3000: "__dt__6CMemberFv", 0x3100: "__dl__FPv", 0x3200: "Detach__5CBaseFv", 0x3300: "erase__Q23std4listFv",
             0x3400: "__dt__5CItemFv"}
    name = names.get(address) or symbol
    info = {"name": name}
    for prefix, special in (("__dt__", "dt"), ("__ct__", "ct"), ("__as__", "as")):
        if name and name.startswith(prefix):
            info["special"] = special
    info["delete"] = bool(name) and name.startswith(("__dl__", "__dla__"))
    info["provider"] = bool(name) and "std" in name
    return info


def _shape_of(words: list[int], kind: str = "dtor", sites: dict | None = None, own: frozenset = frozenset()) -> dict:
    code, size = _words(0x2000, words)
    return body_shape(lambda address: code.get(address, 0), 0x2000, size, kind, sites or {}, _callee, own)


def _dtor(body: list[int]) -> list[int]:
    """A destructor at 0x2000: s0 = this, s1 = the delete flag, ``body``, the delete-flag test, operator delete, return."""

    head = [addiu(SP, SP, -32), sw(RA, 16, SP), sw(S0, 0, SP), sw(S1, 4, SP), move(S0, A0), move(S1, A1)]
    test = 0x2000 + 4 * (len(head) + len(body)) + 8
    tail = [DSLL32_FLAG, DSRA32_FLAG, branch(0x06, V0, 0, test, test + 16), NOP, jal(0x3100), move(A0, S0)]
    return head + body + tail + [move(V0, S0), lw(RA, 16, SP), lw(S0, 0, SP), JR_RA, addiu(SP, SP, 32)]


# The class's own vptr is loaded at 0x2018/0x201c (the first two body words).
OWN_VPTR = [lui(V0, 0x47), addiu(V0, V0, 0x100), sw(V0, 0, S0)]
VT_SITES = {0x2018: {"type": "R_MIPS_HI16", "symbol": "__vt__1X", "target_kind": None},
            0x201c: {"type": "R_MIPS_LO16", "symbol": "__vt__1X", "target_kind": "vtable"}}
OWN = frozenset({"__vt__1X"})


def test_a_compiler_shaped_destructor_is_implicit() -> None:
    # vptr store, a member destructor, the delete-flag test and operator delete on this.
    body = OWN_VPTR + [addiu(A0, S0, 8), jal(0x3000), addiu(A1, ZERO, -1)]
    assert _shape_of(_dtor(body), sites=VT_SITES, own=OWN) == {"shape": "implicit", "reasons": []}


def test_a_delete_loop_is_user_written() -> None:
    # for (p = m_items; p != end; p++) delete *p;  (the reviewers' List destructors)
    loop = 0x2000 + 4 * 8
    body = [lw(T0, 4, S0), lw(T1, 8, S0),
            lw(A0, 0, T0), jal(0x3400), addiu(A1, ZERO, 1), addiu(T0, T0, 4), branch(0x05, T0, T1, loop + 16, loop), NOP]
    result = _shape_of(_dtor(body))
    assert result["shape"] == "user-written"
    assert "calls __dt__5CItemFv on deref, not a base or member" in result["reasons"][0]


def test_an_inlined_base_destructor_is_not_the_members_own_work() -> None:
    # Own vptr, then a base's vptr store (in a call's delay slot) opens its inlined destructor, which calls a function.
    sites = VT_SITES | {0x2024: {"type": "R_MIPS_HI16", "symbol": "__vt__5CBase", "target_kind": None},
                        0x2028: {"type": "R_MIPS_LO16", "symbol": "__vt__5CBase", "target_kind": "vtable"}}
    body = OWN_VPTR + [lui(V0, 0x47), addiu(V0, V0, 0x200), move(A0, S0), jal(0x3200), sw(V0, 0, S0)]
    assert _shape_of(_dtor(body), sites=sites, own=OWN)["shape"] == "implicit"
    # The same call as the class's own statement, before any base vptr store, is user-written.
    result = _shape_of(_dtor(OWN_VPTR + [jal(0x3200), move(A0, S0)]), sites=VT_SITES, own=OWN)
    assert result["shape"] == "user-written" and "calls Detach__5CBaseFv" in result["reasons"][0]


def test_library_calls_copy_loops_and_constants() -> None:
    # An inlined library member destructor may call into std::: unknown, not user-written.
    library = _shape_of(_dtor([addiu(A0, S0, 4), jal(0x3300), NOP]))
    assert library["shape"] == "unknown" and "calls library code erase__Q23std4listFv" in library["reasons"][0]
    # operator=: a char[8] member copied byte by byte in a loop, then return this.
    loop = 0x2000 + 4 * 3
    assign = [move(T0, A1), move(T1, A0), addiu(V1, ZERO, 8),
              lb(V0, 0, T0), addiu(V1, V1, -1), sb(V0, 0, T1), addiu(T0, T0, 1), branch(0x07, V1, 0, loop + 16, loop),
              addiu(T1, T1, 1), move(V0, A0), JR_RA, NOP]
    assert _shape_of(assign, kind="assign") == {"shape": "implicit", "reasons": []}
    # A constructor storing a non-zero constant is user-written; zero initialization is compiler-shaped.
    assert _shape_of([addiu(V0, ZERO, 1), sw(V0, 4, A0), JR_RA, move(V0, A0)], kind="ctor")["shape"] == "user-written"
    assert _shape_of([sw(ZERO, 4, A0), JR_RA, move(V0, A0)], kind="ctor")["shape"] == "implicit"


def test_emit_check_expects_an_emit_only_for_a_compiler_shaped_body(tmp_path: Path) -> None:
    root, cache, first, _second = _workspace(tmp_path)
    with closing(sqlite3.connect(cache)) as connection:
        for address, name, binding, size in ((0x1e00, "__dt__6CAiMapFv", "13", 0x20), (0x3100, "__dl__FPv", "GLOBAL", 8)):
            connection.execute(
                "INSERT INTO artifacts (id, kind, address, size, binding, classification) VALUES (?, 'function', ?, ?, ?, 'authored')",
                (_id(address), address, size, binding),
            )
            connection.execute("INSERT INTO names VALUES (?, ?, ?, ?)", (_id(address), name, binding, address))
        connection.commit()
    item = "socom:work:source-segment-001"
    plan = copy.deepcopy(first)
    plan["owners"][0]["artifacts"].append({"artifact": _id(0x1e00), "confidence": "high", "basis": "x"})
    # CAiMap's destructor (one unit, a.cpp; zfoo.h declares CAiMap): the flag test and operator delete on this.
    implicit = [move(S0, A0), _r(0, A1, V0, 0x3C, 16), DSRA32_FLAG, branch(0x06, V0, 0, 0x1e0c, 0x1e1c), NOP,
                jal(0x3100), move(A0, S0), JR_RA]
    user = [lw(A0, 4, A0), jal(0x3100), NOP, JR_RA, NOP, NOP, NOP, NOP]  # delete m_p

    def run(words: list[int] | None, emits: bool = False) -> dict:
        tested = copy.deepcopy(plan)
        if emits:
            tested["header_emits"].append({"artifact": _id(0x1e00), "header": "src/gamez/zFoo/zfoo.h", "reason": "inline",
                                           "evidence": ["x"]})
        code = _words(0x1e00, words)[0] if words else {}
        word = (lambda address: code.get(address, 0)) if words else None
        return emit_check(root, cache, items=[item], replace={item: ("p.json", tested)}, word=word)["plans"][item]

    expected = run(implicit)
    (row,) = [value for value in expected["missing_emits"] if value["artifact"] == _id(0x1e00)]
    assert row["body_shape"] == "implicit" and row["units"] == ["a.cpp"] and row["suggested"]["line"] == 31
    assert any("compiler-shaped body" in basis for basis in row["basis"])
    written = run(user, emits=True)
    assert _id(0x1e00) not in [value["artifact"] for value in written["missing_emits"]]
    (candidate,) = written["user_written_emits"]
    assert candidate["artifact"] == _id(0x1e00) and candidate["header"] == "src/gamez/zFoo/zfoo.h"
    assert "calls __dl__FPv on member, not this" in candidate["body_reasons"][0]
    assert written["counts"]["shape_user_written"] == 1 and written["counts"]["user_written_emits"] == 1
    # Without the ELF the shape is unknown: listed, never expected.
    unknown = run(None)
    assert _id(0x1e00) not in [value["artifact"] for value in unknown["missing_emits"]]
    assert [(value["artifact"], value["has_emit"]) for value in unknown["unknown_shape"]] == [(_id(0x1e00), False)]


# An inlined member destructor: CAiEvent::~CAiEvent with CBits::~CBits inlined at this+0x20 (0x17fc20, 0x17f440).
BLEZ, DSLL32_S0 = 0x06, _r(0, S0, V0, 0x3C, 16)


def _member_dtor() -> list[int]:
    """CBits::~CBits at 0x1f00 (this in s1, the flag in s0): _free(m_bits, "<file>", 38); m_bits = 0; the deleting tail."""

    end = 0x1f00 + 4 * 14
    return [move(S1, A0), branch(0x04, S1, ZERO, 0x1f04, end), move(S0, A1),
            lw(A0, 4, S1), lui(A1, 0), addiu(A1, A1, 0x7f00), jal(0x3500), addiu(6, ZERO, 38),
            DSLL32_S0, DSRA32_FLAG, branch(BLEZ, V0, 0, 0x1f28, end), sw(ZERO, 4, S1), jal(0x3100), move(A0, S1),
            move(V0, S1), JR_RA, NOP]


def _holder_dtor() -> list[int]:
    """CAiMap::~CAiMap at 0x1e00: the same work under the compiler's `this+0x20 != 0` test, then the deleting tail."""

    end, skip = 0x1e00 + 4 * 18, 0x1e00 + 4 * 12
    return [move(S1, A0), branch(0x04, S1, ZERO, 0x1e04, end), move(S0, A1),
            addiu(V0, S1, 0x20), branch(0x04, V0, ZERO, 0x1e10, skip), NOP,
            lw(A0, 0x24, S1), lui(A1, 0), addiu(A1, A1, 0x7f00), jal(0x3500), addiu(6, ZERO, 38), sw(ZERO, 0x24, S1),
            DSLL32_S0, DSRA32_FLAG, branch(BLEZ, V0, 0, 0x1e38, end), NOP, jal(0x3100), move(A0, S1),
            move(V0, S1), JR_RA, NOP]


def _inlined_case(tmp_path: Path, literal: str, out_of_line: bool) -> dict:
    """The emit check of CAiMap's destructor; ``literal``: the __FILE__ text; ``out_of_line``: CBits's copy exists."""

    root, cache, first, _second = _workspace(tmp_path)
    functions = [(0x1e00, "__dt__6CAiMapFv", "13", 4 * 21), (0x3100, "__dl__FPv", "GLOBAL", 8),
                 (0x3500, "_free__FPvPCci", "GLOBAL", 8)]
    if out_of_line:
        functions.append((0x1f00, "__dt__5CBitsFv", "13", 4 * 17))
    with closing(sqlite3.connect(cache)) as connection:
        for address, name, binding, size in functions:
            connection.execute(
                "INSERT INTO artifacts (id, kind, address, size, binding, classification) VALUES (?, 'function', ?, ?, ?, 'authored')",
                (_id(address), address, size, binding),
            )
            connection.execute("INSERT INTO names VALUES (?, ?, ?, ?)", (_id(address), name, binding, address))
        connection.execute(
            "INSERT INTO artifacts (id, kind, address, size, binding) VALUES (?, 'data', ?, 16, 'LOCAL')", (_id(0x7f00, "data"), 0x7f00)
        )
        connection.execute(
            "INSERT INTO file_strings (string, artifact, text, literal, referenced_by) VALUES (?, ?, ?, 1, ?)",
            (0x7f00, _id(0x7f00, "data"), literal, _id(0x1e00)),
        )
        for function, high in ((0x1e00, 0x1e1c), (0x1f00, 0x1f10)):
            for site, kind in ((high, "R_MIPS_HI16"), (high + 4, "R_MIPS_LO16")):
                connection.execute(
                    "INSERT INTO refs (site, site_artifact, target, target_artifact, type, symbol) VALUES (?, ?, ?, ?, ?, '@1318')",
                    (site, _id(function), 0x7f00, _id(0x7f00, "data"), kind),
                )
        connection.commit()
    item = "socom:work:source-segment-001"
    plan = copy.deepcopy(first)
    plan["owners"][0]["artifacts"].append({"artifact": _id(0x1e00), "confidence": "high", "basis": "x"})
    code = _words(0x1e00, _holder_dtor())[0] | _words(0x1f00, _member_dtor())[0]
    word = lambda address: code.get(address, 0)  # noqa: E731
    return emit_check(root, cache, items=[item], replace={item: ("p.json", plan)}, word=word)["plans"][item]


def test_an_identified_inlined_member_destructor_is_not_judged(tmp_path: Path) -> None:
    # (b) the guarded stretch, rebased by 0x20, equals the out-of-line CBits destructor; (a) its __FILE__ is not zfoo.h.
    both = _inlined_case(tmp_path / "both", "zmath_bits.h", out_of_line=True)
    assert both["special_members"][_id(0x1e00)]["shape"] == "implicit"
    (row,) = [value for value in both["missing_emits"] if value["artifact"] == _id(0x1e00)]
    assert row["body_inlined"] == [
        "0x1e18-0x1e30 (this+0x20): an inlined destructor, equal to the out-of-line __dt__5CBitsFv (0x1f00); "
        "__FILE__ zmath_bits.h, not a header of its class"
    ]
    # (b) alone: the literal names the class's own header.
    copy_only = _inlined_case(tmp_path / "copy", "zfoo.h", out_of_line=True)
    assert copy_only["special_members"][_id(0x1e00)]["shape"] == "implicit"
    # (a) alone: no out-of-line copy.
    file_only = _inlined_case(tmp_path / "file", "zmath_bits.h", out_of_line=False)
    assert file_only["special_members"][_id(0x1e00)]["shape"] == "implicit"
    # The null test alone identifies nothing: the stretch is judged as the destructor's own work.
    neither = _inlined_case(tmp_path / "neither", "zfoo.h", out_of_line=False)
    assert neither["special_members"][_id(0x1e00)]["shape"] == "user-written"


def test_the_out_of_line_member_destructor_stays_user_written() -> None:
    # No null test of this+N: nothing to identify, whatever identify would say.
    code, size = _words(0x1f00, _member_dtor())
    result = body_shape(lambda address: code.get(address, 0), 0x1f00, size, "dtor", {}, _callee, identify=lambda *_: "x")
    assert result["shape"] == "user-written" and "inlined" not in result
    assert result["reasons"][0] == "0x1f18 calls 0x3500"
