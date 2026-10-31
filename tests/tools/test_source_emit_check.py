"""The ODR header-emit check of stage 4 owner plans (``source plan emit-check``)."""

from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from tools._socom.source_cache import SCHEMA
from tools._socom.source_emit_check import HeaderIndex, emit_check, review_note

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
