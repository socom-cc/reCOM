from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools._socom.cxx_scan import Program, scan_text
from tools._socom.order_skeleton import _enumerators
from tools._socom.order_skeleton_headers import (
    HeaderWriter,
    _bottom_offset,
    _included,
    _insert,
    _top_offset,
    apply_edits,
    in_class_declaration,
    parse_regions,
    replacement_declaration,
    strip_regions,
)
from tools._socom.order_skeleton_write import normalized_sha256, tree_newline
from tools._socom.source import source_artifacts

HEADER = """#ifndef GAME_H
#define GAME_H

#include "base.h"

class CFoo
{
public:
\tint m_value;
\tvoid Reset() { m_value = 0; }
\tbool Ready() { return true; }
};
class CTiny {};
#endif"""


# -- regions -------------------------------------------------------------------------------


def test_parse_regions_pairs_fences_by_name_and_reports_strays() -> None:
    text = "a\n/* @socom-skeleton decl 4CFoo */\n\t/* @socom-skeleton decl 4CBar */\n\t/* @socom-skeleton end 4CBar */\n" \
           "/* @socom-skeleton end 4CFoo */\n/* @socom-skeleton end forward */\n/* @socom-skeleton decl include */\n"
    regions, problems = parse_regions(text)
    assert [(row["name"], row["start"], row["end"]) for row in regions] == [("4CFoo", 1, 4)]
    assert problems == ["line 6: end fence forward closes no open region", "line 7: region include is never closed"]


def test_insert_keeps_whole_lines_and_strip_restores_a_split_line() -> None:
    text = "class A {};\nclass B\n{\n};\n"
    whole, split = _insert(text, text.index("};\n", 15), ["\t/* @socom-skeleton decl 1B */", "\tvoid f();", "\t/* @socom-skeleton end 1B */"])
    assert not split and whole.endswith("\n")
    inline, split_a = _insert(text, text.index("}"), ["/* @socom-skeleton decl 1A */", "/* @socom-skeleton end 1A */"])
    assert split_a
    out = apply_edits(text, [(text.index("}"), text.index("}"), inline), (text.index("};\n", 15), text.index("};\n", 15), whole)])
    regions, problems = parse_regions(out)
    assert not problems and [row["name"] for row in regions] == ["1A", "1B"]
    assert strip_regions(out, regions, {0}) == text


def test_top_and_bottom_offsets_follow_the_include_guard() -> None:
    scan = scan_text("src/game/game.h", HEADER)
    assert HEADER[_top_offset(scan):].startswith("\nclass CFoo")
    assert HEADER[_bottom_offset(scan):] == "#endif"
    bare = scan_text("src/game/bare.h", "class X {};\n")
    assert _top_offset(bare) == 0 and _bottom_offset(bare) == len(bare.text)


def test_in_class_declarations_keep_the_head_and_drop_inline_and_initializers() -> None:
    scan = scan_text("x.h", "class C\n{\n\tC() : m(0) {}\n\tinline int Get() const { return m; }\n\tint m;\n};\n")
    first, second = [row for row in scan.definitions if row.in_class]
    assert in_class_declaration(scan, first) == ("C();", False)
    assert in_class_declaration(scan, second) == ("int Get() const;", True)


def test_a_replacement_that_contradicts_the_signature_takes_the_signature() -> None:
    scan = scan_text("src/game/game.h", HEADER)
    program = Program([scan])
    reset, ready = [row for row in scan.definitions if row.in_class]
    agree = {"declaration": "void Reset();", "return": {"text": "void", "source": "stage3"}, "member": {"kind": "instance"}}
    assert replacement_declaration(program, scan, reset, agree) == ("void Reset();", [])
    contradict = {"declaration": "virtual unsigned char Ready();", "return": {"text": "unsigned char", "source": "stage3"},
                  "member": {"kind": "instance"}}
    text, flags = replacement_declaration(program, scan, ready, contradict)
    assert text == "virtual unsigned char Ready();" and flags[0]["kind"] == "declaration-from-signature"


def test_included_paths_resolve_both_conventions() -> None:
    scan = scan_text("src/gamez/zAI/ai.cpp", '#include "zai.h"\n#include "gamez/zMath/zmath.h"\n#include "../zUtil/zutil.h"\n')
    found = _included("src/gamez/zAI/ai.cpp", scan)
    assert {"src/gamez/zAI/zai.h", "src/gamez/zMath/zmath.h", "src/gamez/zUtil/zutil.h"} <= found


def test_source_artifacts_accept_declaration_region_fences(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.h").write_text(
        "/* @socom-skeleton decl 4CFoo */\n/* @socom-skeleton end 4CFoo */\n/* @socom-skeleton dcl 4CFoo */\n", encoding="utf-8")
    assert source_artifacts(tmp_path)["errors"] == ["src/a.h:3: malformed @socom-skeleton fence"]


# -- records -------------------------------------------------------------------------------


def test_enumerators_decode_dwarf1_element_lists_by_value() -> None:
    block = (1).to_bytes(4, "little", signed=True) + b"B\x00" + (0).to_bytes(4, "little") + b"A\x00"
    die = SimpleNamespace(integer=lambda name: 4, attribute=lambda name: SimpleNamespace(value=block))
    assert _enumerators(die) == ([["A", 0], ["B", 1]], None)
    narrow = SimpleNamespace(integer=lambda name: 1, attribute=lambda name: SimpleNamespace(value=b"\x02C\x00\xffD\x00"))
    assert _enumerators(narrow) == ([["D", -1], ["C", 2]], None)


def test_digests_are_newline_independent(tmp_path: Path) -> None:
    assert normalized_sha256(b"a\r\nb\r\n") == normalized_sha256(b"a\nb\n")
    (tmp_path / "src").mkdir()
    for name in ("a.cpp", "b.cpp"):
        (tmp_path / "src" / name).write_bytes(b"int x;\n")
    (tmp_path / "src" / "c.h").write_bytes(b"int y;\r\n")
    assert tree_newline(tmp_path) == "\n"
    (tmp_path / "src" / "d.h").write_bytes(b"int z;\r\n")
    assert tree_newline(tmp_path) == "\r\n"  # a tie keeps the default


# -- the writer on a small tree ------------------------------------------------------------


def _tree(tmp_path: Path) -> SimpleNamespace:
    (tmp_path / "src" / "game").mkdir(parents=True)
    (tmp_path / "src" / "game" / "game.h").write_text(HEADER, encoding="utf-8")
    (tmp_path / "src" / "game" / "unit.cpp").write_text("int g;\n", encoding="utf-8")
    scans = {path: scan_text(path, (tmp_path / path).read_text(encoding="utf-8")) for path in ("src/game/game.h", "src/game/unit.cpp")}
    program = Program(list(scans.values()), [("CFoo",), ("CBar",), ("CBaz",)])
    signature = {
        "f1": {"structured": {"scope": [{"name": "CFoo"}]}, "declaration": "void Reset();", "mentions": [],
               "return": {"text": "void", "source": "stage3"}, "member": {"kind": "instance"}},
        "f2": {"structured": {"scope": [{"name": "CBar"}]}, "declaration": "virtual void Tick(CBaz *);", "mentions": ["CBaz"],
               "return": {"text": "void", "source": "stage3"}, "member": {"kind": "instance"}},
    }
    bases = {"source": "rtti", "bases": [{"class": "CFoo", "components": [{"name": "CFoo"}], "offset": 0, "direct": True, "access": None}]}
    classes = [
        {"chain": ["CFoo"], "class": "CFoo", "mangled": "4CFoo", "key": "class", "key_source": "src", "units": {"unit.cpp": 1},
         "body": {"path": "src/game/game.h", "line": 6, "end_line": 12, "key": "class"}, "header": None,
         "members_to_add": [], "members_declared_names": ["Reset__4CFooFv"], "bases": {"source": "unknown", "bases": []},
         "static_data_members": [{"artifact": "d1", "name": "s_count__4CFoo", "declared": False, "declaration": "static int s_count;",
                                  "mentions": []}],
         "vtable": None},
        {"chain": ["CBar"], "class": "CBar", "mangled": "4CBar", "key": "class", "key_source": "default", "units": {"unit.cpp": 1},
         "body": None, "header": {"path": "src/game/game.h"}, "bases": bases, "static_data_members": [], "members_declared_names": [],
         "members_to_add": [{"artifact": "f2", "name": "Tick__4CBarFP4CBaz", "declaration": "virtual void Tick(CBaz *);",
                             "in_class": False, "mentions": ["CBaz"]}],
         "vtable": {"declare_virtual": [
             {"member": "__dt__4CBarFv", "slot": 0, "group": 0, "new": False, "declared": False, "declaration": "virtual ~CBar();", "mentions": []},
             {"member": "Tick__4CBarFP4CBaz", "slot": 1, "group": 0, "new": True, "declared": False, "declaration": None, "mentions": []},
         ], "unnamed_new_slots": []}},
    ]
    types = [
        {"chain": ["MODE"], "type": "MODE", "mangled": "4MODE", "src": "undeclared", "need": "full", "by_value": ["parameter"],
         "units": ["unit.cpp"], "provider": False, "record": {"basis": "DIE 0x10", "kind": "enum"}, "key": "enum",
         "definition": {"source": "dwarf", "kind": "enum", "key": "enum", "size": 4, "enumerators": [["OFF", 0], ["ON", 1]], "unproven": []},
         "placement": {"path": "src/game/game.h"}},
        {"chain": ["CBaz"], "type": "CBaz", "mangled": "4CBaz", "src": "undeclared", "need": "forward", "by_value": [], "units": ["unit.cpp"],
         "provider": False, "record": {"basis": "no record", "kind": None}, "key": None},
        {"chain": ["LOST"], "type": "LOST", "mangled": "4LOST", "src": "undeclared", "need": "full", "by_value": ["parameter"],
         "units": ["unit.cpp"], "provider": False, "record": {"basis": "no DWARF or stage 3 record", "kind": None}, "key": None},
    ]
    reset = next(row for row in scans["src/game/game.h"].definitions if row.in_class and row.line == 10)
    from tools._socom.order_skeleton_headers import _sha

    bodies = [{"id": "src/game/game.h:10", "action": "move-out-of-line", "path": "src/game/game.h", "mangled": "Reset__4CFooFv",
               "span": {"start_line": 10}, "sha256": _sha(scans["src/game/game.h"].text[reset.start : reset.end]),
               "row": {"artifact": "f1"}, "recipient": "src/game/unit.cpp"}]
    unit = {"unit": "unit.cpp", "workspace_path": "src/game/unit.cpp",
            "functions": [{"artifact": "f1"}, {"artifact": "f2"}], "data": [{"rows": [{"artifact": "d1"}]}]}
    manifest = {"declarations": {"classes": classes, "types": types}, "bodies": {"definitions": bodies}}
    # The writer's inputs: src/ is read from source_root (the root itself before the skeleton route writes src/); no decisions.
    return SimpleNamespace(root=tmp_path, source_root=tmp_path, program=program, scans=scans, manifest=manifest, units=[(1, unit)],
                           signatures=signature, data={"d1": {"unit": "unit.cpp", "const": False, "mentions": []}},
                           decision=lambda kind, key: None)


def test_the_header_writer_adds_regions_and_keeps_everything_else(tmp_path: Path) -> None:
    inputs = _tree(tmp_path)
    writer = HeaderWriter(inputs, newline="\n")
    out = writer.render()
    header = out["headers"]["src/game/game.h"]["text"]
    regions, problems = parse_regions(header)
    assert not problems
    assert [row["name"] for row in regions] == ["forward", "4MODE", "4CFoo", "4CBar"]
    assert [row["name"] for row in writer.regions if row["path"] == "src/game/game.h"] == ["forward", "4MODE", "4CFoo", "4CBar"]
    assert "class CBaz;" in header and "enum MODE" in header and "\tstatic int s_count;" in header
    # The new class: its RTTI base (public, flagged), virtuals in slot order, the declaration text of the planned row.
    body = header[header.index("class CBar"):]
    assert body.startswith("class CBar : public CFoo\n{\npublic:\n\tvirtual ~CBar();\n\tvirtual void Tick(CBaz *);\n};")
    record = next(row for row in writer.regions if row["name"] == "4CBar")
    assert {flag["kind"] for flag in record["flags"]} >= {"base-access-unproven", "key-unproven"}
    assert record["members"] == ["__dt__4CBarFv", "Tick__4CBarFP4CBaz"]
    # Outside the regions: src/ but for the in-class body of the out-of-line row, which leaves its declaration.
    splits = {index for index, row in enumerate(r for r in writer.regions if r["path"] == "src/game/game.h") if row["split"]}
    expected = HEADER.replace("void Reset() { m_value = 0; }", "void Reset();")
    assert strip_regions(header, regions, splits) == expected
    assert [row["declaration"] for row in writer.replacements] == ["void Reset();"]
    # The unit includes the header (it defines members of its classes) and the type with no record waits.
    tail = out["units"]["src/game/unit.cpp"]["tail"]
    assert '#include "game.h"' in tail and tail.startswith("/* @socom-skeleton decl include */")
    assert [row["type"] for row in writer.waiting if row["kind"] == "type-no-record"] == ["LOST"]


def test_the_header_writer_refuses_a_header_that_already_holds_regions(tmp_path: Path) -> None:
    from tools._socom.util import SocomError

    inputs = _tree(tmp_path)
    fenced = HEADER.replace("class CTiny {};", "/* @socom-skeleton decl 5CTiny */\n/* @socom-skeleton end 5CTiny */\nclass CTiny {};")
    (tmp_path / "src" / "game" / "game.h").write_text(fenced, encoding="utf-8")
    inputs.scans["src/game/game.h"] = scan_text("src/game/game.h", fenced)
    with pytest.raises(SocomError, match="already holds generated declaration regions"):
        HeaderWriter(inputs, newline="\n").render()
