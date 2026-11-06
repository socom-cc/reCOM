from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools._socom.cxx_scan import (
    Program,
    data_symbols,
    declaration_text,
    definition_text,
    function_symbol,
    parse_head,
    scan_text,
)
from tools._socom.mw_mangle import mangle, parse_symbol
from tools._socom.order_skeleton import (
    BODY_ACTIONS,
    DATA_TYPE_SOURCES,
    JUDGMENT_KINDS,
    SIGNATURE_SOURCES,
    SNAPSHOT_KIND,
    _Types,
    _split_signature,
    accepted_plans,
    holding_file,
    settle_snapshot,
    stage3_facts,
    symbol_chains,
)
from tools._socom.util import SocomError, canonical_json

SOURCE = """\
#include "zsys.h"
typedef unsigned int u32;
typedef struct tagPNT { float x; } PNT;
typedef struct { int a; } ANON;
typedef enum tagMODE { MODE_A, MODE_B } MODE;
class CNode;
namespace zdb {
class CNode {
public:
    virtual ~CNode();
    static int s_count;
    void Attach(CNode *child, u32 flags = 0) const;
    int Count() const { return s_count; }
};
}
struct CPnt3D {
    float x, y, z;
    CPnt3D();
    CPnt3D operator+(const CPnt3D &other) const;
    operator float() const;
};
int g_value = 3;
int zdb::CNode::s_count = 0;
CPnt3D g_origin(0.0f, 0.0f, 0.0f);
static float s_table[] = { 1.0f, 2.0f };
extern int g_extern;
zdb::CNode::~CNode() { }
void zdb::CNode::Attach(CNode *child, u32 flags) const { if (child) { flags = 1; } }
CPnt3D::CPnt3D() : x(0), y(0), z(0) { }
CPnt3D CPnt3D::operator+(const CPnt3D &other) const { return *this; }
CPnt3D::operator float() const { return x; }
u32 Hash(const char *text, u32 seed = 5) { return seed; }
void Sort(void (fixup)(CPnt3D *, MODE), PNT *points, ANON anon) { }
void Bind(void (CPnt3D::*method)(), int (*table)[4]) { }
extern "C" void TRC_PreparePowerOff(void) { }
namespace zar { void Flush(FILE *file, uint32_t count) { } }
"""

EXPECTED_DEFINITIONS = [
    "__dt__Q23zdb5CNodeFv",
    "Attach__Q23zdb5CNodeCFPQ23zdb5CNodeUi",
    "__ct__6CPnt3DFv",
    "__pl__6CPnt3DCFRC6CPnt3D",
    "__opf__6CPnt3DCFv",
    "Hash__FPCcUi",
    "Sort__FPFP6CPnt3D7tagMODE_vP6tagPNT4ANON",
    "Bind__FM6CPnt3DFPCvPv_vPA4_i",
    "TRC_PreparePowerOff",
    "Flush__3zarFP7__sFILEUi",
]


def _program(*sources: tuple[str, str], chains: tuple[tuple[str, ...], ...] = ()) -> tuple[Program, list]:
    scans = [scan_text(path, text) for path, text in sources]
    return Program(scans, chains), scans


def test_scan_finds_scopes_definitions_and_spans() -> None:
    program, (scan,) = _program(("src/x/fixture.cpp", SOURCE))
    assert scan.preprocessor == {"include": 1} and scan.includes == ["zsys.h"]
    assert ("zdb",) in scan.namespaces and ("zar",) in scan.namespaces
    assert {klass.chain for klass in scan.classes} >= {("tagPNT",), ("ANON",), ("zdb", "CNode"), ("CPnt3D",)}
    assert ("CNode",) in scan.forwards and ("tagMODE",) in scan.enums
    outer = [row for row in scan.definitions if row.in_class is None]
    names = [mangle(function_symbol(program, row.tokens, row.scope, scan.tag).symbol) for row in outer]
    assert names == EXPECTED_DEFINITIONS
    # A default argument's '=' does not make a definition an initializer; spans cover head to brace.
    hashed = next(row for row in outer if row.tokens[1].text == "Hash")
    assert scan.text[hashed.start : hashed.end].startswith("u32 Hash(") and scan.text[hashed.end - 1] == "}"
    assert hashed.line == hashed.end_line == SOURCE.splitlines().index("u32 Hash(const char *text, u32 seed = 5) { return seed; }") + 1
    inline = [row for row in scan.definitions if row.in_class is not None]
    assert [mangle(function_symbol(program, row.tokens, row.scope, scan.tag, klass=row.in_class).symbol) for row in inline] == [
        "Count__Q23zdb5CNodeCFv"
    ]


def test_class_members_and_file_scope_data() -> None:
    program, (scan,) = _program(("src/x/fixture.cpp", SOURCE))
    node = next(klass for klass in scan.classes if klass.chain == ("zdb", "CNode"))
    declared = set()
    for member in node.members:
        if hasattr(member, "body_start") or "(" in [token.text for token in member.tokens]:
            parsed = function_symbol(program, member.tokens, member.scope, scan.tag, klass=node.chain)
            declared.add(mangle(parsed.symbol))
        else:
            declared |= {mangle(row.symbol) for row in data_symbols(program, member.tokens, member.scope, scan.tag) if "static" in row.specifiers}
    assert declared == {"__dt__Q23zdb5CNodeFv", "s_count__Q23zdb5CNode", "Attach__Q23zdb5CNodeCFPQ23zdb5CNodeUi", "Count__Q23zdb5CNodeCFv"}
    data = {}
    for row in scan.declarations:
        if row.in_class is None:
            for parsed in data_symbols(program, row.tokens, row.scope, scan.tag):
                if parsed.symbol is not None:
                    data[mangle(parsed.symbol)] = parsed
    assert set(data) == {"g_value", "s_count__Q23zdb5CNode", "g_origin", "s_table", "g_extern"}
    assert "static" in data["s_table"].specifiers and "extern" in data["g_extern"].specifiers
    assert data["s_table"].type == {"t": "array", "size": None, "of": {"t": "builtin", "code": "f"}}


def test_definition_text_qualifies_hidden_names_and_round_trips() -> None:
    header = "class CNode;\nnamespace zdb { class CNode; class CGraph { void Link(::CNode *node); }; }\n"
    program, _scans = _program(("src/x/graph.h", header))
    symbol = parse_symbol("Link__Q23zdb6CGraphFP5CNode")
    head, problems, namespace = definition_text(program, symbol, "void", tag="graph_cpp")
    # Inside zdb::CGraph, a plain CNode would be zdb::CNode: the written name needs the leading ::.
    assert head == "void zdb::CGraph::Link(::CNode *)" and problems == [] and namespace is None
    assert mangle(parse_head(program, head, tag="graph_cpp", namespace=None).symbol) == "Link__Q23zdb6CGraphFP5CNode"
    assert declaration_text(program, symbol, "void", static=False, virtual=True) == "virtual void Link(::CNode *);"


def test_definition_text_writes_the_anonymous_namespace_of_its_unit() -> None:
    name = "Tick__Q222@unnamed@hud_main_cpp@4CFooFRCQ222@unnamed@hud_main_cpp@4CFoo"
    program, _scans = _program(chains=tuple(symbol_chains(parse_symbol(name))))
    head, problems, namespace = definition_text(program, parse_symbol(name), "int", tag="hud_main_cpp")
    assert (head, problems, namespace) == ("int CFoo::Tick(const CFoo &)", [], "anonymous")
    assert mangle(parse_head(program, head, tag="hud_main_cpp", namespace=namespace).symbol) == name
    _head, problems, _namespace = definition_text(program, parse_symbol(name), "int", tag="other_cpp")
    assert problems and "not this unit's" in problems[0]


@pytest.mark.parametrize(
    "name",
    [
        "Tick__10CZSealBodyFf",
        "Acquire__14CCharacterTypeCFv",
        "SetDefaults__Q28CZWeapon9AI_PARAMSF10EQUIP_ITEM",
        "__ct__9AI_PARAMSFRC9AI_PARAMS",
        "__dt__10CZSealBodyFv",
        "__as__6CPnt3DFRC6CPnt3D",
        "__cl__7CMatrixCFUiUi",
        "__vc__7CMatrixFi",
        "__ls__7CStreamFPCc",
        "__nw__FUi",
        "__dla__FPv",
        "__opPCc__3StrCFv",
        "Draw__FPFRC7CTargetRC7CTarget_bPA4_f",
        "Call__FM9C2DButtonFPCvPv_vM9C2DButtonFPCvPCv_i",
        "Get__3FooVFv",
        "Printf__FPCce",
        "Kick__FP1Ui",
        "Sum__FScUcsUsiUilUlxUxfdrwb",
        "Find__Q23std6vectorFv",
        "Get__9Table<-1>Fv",
    ],
)
def test_structured_forms_round_trip_through_written_declarators(name: str) -> None:
    symbol = parse_symbol(name)
    program, _scans = _program(chains=tuple(symbol_chains(symbol)))
    head, problems, namespace = definition_text(program, symbol, "void", tag="x_cpp")
    assert problems == []
    assert mangle(parse_head(program, head, tag="x_cpp", namespace=namespace).symbol) == name, head


def test_typedefs_resolve_before_mangling() -> None:
    source = (
        "typedef unsigned int u32;\ntypedef u32 HANDLE;\ntypedef float f32;\ntypedef void (*Callback)(HANDLE, f32);\n"
        "namespace zdb { typedef int Index; void Use(Index i, HANDLE h, Callback cb, std::vector<int> &v, size_t n) { } }\n"
    )
    program, (scan,) = _program(("src/x/types.cpp", source))
    (definition,) = scan.definitions
    symbol = function_symbol(program, definition.tokens, definition.scope, scan.tag).symbol
    assert mangle(symbol) == "Use__3zdbFiUiPFUif_vRQ23std30vector<i,Q23std12allocator<i>>Ui"


def test_split_signature_reads_ghidra_prototypes() -> None:
    destructor = _split_signature("COurGame::~COurGame", "void * __stdcall COurGame::~COurGame(COurGame * this, short __dtor_flags)")
    assert destructor == {"returns": "void *", "default": False, "this": True, "params": []}
    static = _split_signature("CFoo::Make", "noreturn CFoo * __stdcall CFoo::Make(int count, char * * names)")
    assert static == {"returns": "CFoo *", "default": False, "this": False, "params": ["int count", "char * * names"]}
    assert _split_signature("entry", "undefined entry(void)")["default"] is True


def test_ghidra_types_are_qualified_from_their_category() -> None:
    class _NoDwarf:
        composites: dict = {}

    program, _scans = _program(chains=(("zdb", "CNode"),))
    types = _Types(program, {"/project/zdb/CNode": 96, "/project/unresolved/struct_1": 4, "/project/CPnt3D": 16}, _NoDwarf())
    node, why = types.ghidra_node("CNode *")
    assert why is None and node == {"t": "pointer", "to": {"t": "named", "name": [{"name": "zdb"}, {"name": "CNode"}]}}
    assert types.ghidra_node("uint")[0] == {"t": "builtin", "code": "i", "sign": "U"}
    assert types.ghidra_node("float[4][4]")[0] == {"t": "array", "size": 4, "of": {"t": "array", "size": 4, "of": {"t": "builtin", "code": "f"}}}
    assert types.ghidra_node("undefined4")[0] is None
    assert types.ghidra_node("struct_1")[1].startswith("stage 3 names the provisional type")
    assert types.size({"t": "named", "name": [{"name": "zdb"}, {"name": "CNode"}]}) == 96
    assert types.size({"t": "array", "size": 3, "of": {"t": "pointer", "to": {"t": "builtin", "code": "v"}}}) == 12


def test_ghidras_untyped_pointer_is_void_pointer_never_a_class() -> None:
    class _NoDwarf:
        composites: dict = {}

    program, _scans = _program()
    types = _Types(program, {}, _NoDwarf())
    void = {"t": "builtin", "code": "v"}
    assert types.ghidra_node("pointer") == ({"t": "pointer", "to": void}, None)
    assert types.ghidra_node("pointer *")[0] == {"t": "pointer", "to": {"t": "pointer", "to": void}}
    assert types.ghidra_node("pointer[2]")[0] == {"t": "array", "size": 2, "of": {"t": "pointer", "to": void}}
    assert types.size(types.ghidra_node("pointer")[0]) == 4
    # A class merely named like it is still looked up as a class.
    assert types.ghidra_node("pointer_t")[0]["t"] == "named"


def test_holding_file_is_per_module() -> None:
    assert holding_file("src/gamez/zSeal/seal_ai.cpp") == "src/gamez/zSeal/zseal_holding.cpp"
    assert holding_file("src/Apps/FTS/hud/hud_main.cpp") == "src/Apps/FTS/hud/hud_holding.cpp"


def test_snapshot_is_written_once_then_only_compared(tmp_path: Path) -> None:
    path = tmp_path / "build" / "stage5" / "provisional-bodies.json"
    fresh = {"kind": SNAPSHOT_KIND, "snapshot_sha256": "a", "bodies": [{"id": "f.cpp:1", "sha256": "1"}]}
    assert settle_snapshot(path, fresh, refresh=False)["status"] == "written"
    assert settle_snapshot(path, fresh, refresh=False)["status"] == "current"
    changed = {"kind": SNAPSHOT_KIND, "snapshot_sha256": "b", "bodies": [{"id": "f.cpp:1", "sha256": "2"}, {"id": "g.cpp:3", "sha256": "3"}]}
    stale = settle_snapshot(path, changed, refresh=False)
    assert stale["status"] == "stale" and stale["changed"] == ["f.cpp:1"] and stale["added"] == ["g.cpp:3"]
    assert json.loads(path.read_text(encoding="utf-8"))["snapshot_sha256"] == "a"
    assert settle_snapshot(path, changed, refresh=True)["status"] == "refreshed"
    assert json.loads(path.read_text(encoding="utf-8"))["snapshot_sha256"] == "b"


def _plan_tracker(tmp_path: Path, *, cite: bool = True, status: str = "accepted") -> dict:
    plans = tmp_path / "build" / "order-plans"
    plans.mkdir(parents=True)
    path = plans / "socom-work-order-segment-001.json"
    path.write_text(json.dumps({"kind": "socom-order-plan", "segment_number": 1, "units": []}), encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    item = {"id": "socom:work:order-segment-001", "kind": "order-plan-segment", "status": status,
            "evidence": [f"build/order-plans/socom-work-order-segment-001.json sha256:{sha}"] if cite else ["reviewed"]}
    return {"work_items": [item]}


def test_accepted_plans_need_the_cited_sha(tmp_path: Path) -> None:
    rows, link = accepted_plans(tmp_path, _plan_tracker(tmp_path))
    assert [row["item"] for row in rows] == ["socom:work:order-segment-001"] and link == {}


@pytest.mark.parametrize("options, message", [({"cite": False}, "is not the plan"), ({"status": "awaiting_acceptance"}, "not accepted")])
def test_accepted_plans_refuse_uncited_or_unaccepted_plans(tmp_path: Path, options: dict, message: str) -> None:
    with pytest.raises(SocomError, match=message):
        accepted_plans(tmp_path, _plan_tracker(tmp_path, **options))


def _digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _stage3(tmp_path: Path, *, tamper: bool = False) -> tuple[dict, Path, Path]:
    functions = [{"address": "00140d00", "name": "main", "details": ["Signature: int main(int argc, char * * argv)"]}]
    body = {"kind": "socom-ghidra-receipt", "indexes": {"functions": {"sha256": "f" * 64}}, "scoped_facts": {"functions": functions}}
    data = [{"address": "00475040", "name": "diPoolSize", "size": 4, "type": "int"}]
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"receipt": body, "receipt_sha256": _digest(body)}), encoding="utf-8")
    if tamper:
        body["scoped_facts"]["functions"][0]["name"] = "other"
        receipt.write_text(json.dumps({"receipt": body, "receipt_sha256": _digest({**body, "kind": "x"})}), encoding="utf-8")
    fingerprint = tmp_path / "fp.json"
    fingerprint.write_text(json.dumps({"data": data, "types": ["/project/zdb/CNode|96"]}), encoding="utf-8")
    baseline = {"receipt_sha256": _digest(body), "indexes": {"functions": {"sha256": "f" * 64}, "data": {"sha256": _digest(data)}}}
    tracker = {"stages": [{"name": "ghidra-reconstruction", "status": "accepted", "baseline": baseline}]}
    return tracker, receipt, fingerprint


def test_stage3_facts_check_the_baseline_digests(tmp_path: Path) -> None:
    tracker, receipt, fingerprint = _stage3(tmp_path)
    facts = stage3_facts(tmp_path, tracker, receipt, fingerprint)
    assert facts["functions"] == {0x140D00: ("main", "int main(int argc, char * * argv)")}
    assert facts["data"] == {0x475040: ("int", 4)} and facts["types"] == {"/project/zdb/CNode": 96}
    assert facts["record"]["receipt_is_baseline"] is True
    # A second read uses the digest cache keyed by the files' SHA-256.
    assert stage3_facts(tmp_path, tracker, receipt, fingerprint)["record"] == facts["record"]


def test_stage3_facts_refuse_a_receipt_that_does_not_match(tmp_path: Path) -> None:
    tracker, receipt, fingerprint = _stage3(tmp_path, tamper=True)
    with pytest.raises(SocomError, match="content digest"):
        stage3_facts(tmp_path, tracker, receipt, fingerprint)


def test_manifest_refuses_output_outside_build(root: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "tools/socom.py", "order", "skeleton", "manifest", "--output", "skeleton.json"],
        cwd=root, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert completed.returncode != 0 and "under build/" in completed.stdout + completed.stderr


def test_manifest_refuses_a_snapshot_refresh_once_the_route_base_exists(root: Path) -> None:
    from tools._socom.order_skeleton_route import BASE_DIR

    if not (root / BASE_DIR / "src").is_dir():
        pytest.skip("the skeleton route has not frozen its base")
    completed = subprocess.run(
        [sys.executable, "tools/socom.py", "order", "skeleton", "manifest", "--refresh-snapshot"],
        cwd=root, text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert completed.returncode != 0 and "refused once the base exists" in completed.stdout + completed.stderr


# -- real data -----------------------------------------------------------------------------


def test_s1_round_trips_every_authored_definition(root: Path, reference_source_graph: dict) -> None:
    """S1 over every authored function the ELF defines (copies excepted): the written declarator mangles back."""

    from tools._socom.elf import Elf32File
    from tools._socom.order_skeleton import scan_sources
    from tools._socom.order_target import COPY_BINDINGS, template_instance

    scans, _files = scan_sources(root)
    chains: set = set()
    for row in Elf32File(root / "support" / "socom.elf").symbols():
        if row.name:
            chains |= symbol_chains(parse_symbol(row.name))
    program = Program(scans, chains)
    checked, failures = 0, []
    for artifact in reference_source_graph["artifacts"]:
        if artifact["kind"] != "function" or artifact["classification"].get("candidate") != "authored":
            continue
        for entry in artifact["names"]:
            name = entry["name"]
            if {entry.get("binding"), artifact.get("binding")} & set(COPY_BINDINGS) or template_instance(name):
                continue
            symbol = parse_symbol(name)
            if symbol["kind"] != "function":
                continue
            scope = symbol.get("scope") or []
            tag = scope[0]["unnamed"] if scope and "unnamed" in scope[0] else "x_cpp"
            head, problems, namespace = definition_text(program, symbol, "void", tag=tag)
            back = parse_head(program, head, tag=tag, namespace=namespace)
            checked += 1
            if problems or back.symbol is None or mangle(back.symbol) != name:
                failures.append(name)
    assert checked > 4800
    # Only the members of zui_skb.cpp's function-local class (Local$2354) cannot be written out of line.
    assert all("Local$2354zui_skb_cpp" in name for name in failures) and len(failures) == 2


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "build" / "order-plans" / "socom-work-order-segment-001.json").is_file()
    or not (Path(__file__).resolve().parents[2] / "build" / "closeout-ghidra-reconstruction" / "receipt-stage-2.json").is_file(),
    reason="needs the accepted order plans and the stage 3 closeout receipt under build/",
)
def test_manifest_over_the_accepted_plans(root: Path) -> None:
    from tools._socom.order_skeleton import build_manifest, _digest as manifest_digest
    from tools._socom.order_skeleton_route import MANIFEST_PATH, SNAPSHOT_PATH, provisional_root
    from tools._socom.tracker import load_tracker
    from tools._socom.util import load_json

    from tools._socom.source_plan import SOURCE_PLAN_KINDS, plan_path

    from live_state import settled

    # The accepted plans as they stand without the stage 4 amendments and stage 5 reopenings in flight.
    live = load_tracker(root / ".agent" / "RECONSTRUCTION_PROGRESS.json")
    tracker = settled(live)
    try:
        # Every provisional input comes from the skeleton route's frozen base once it exists (src/ then holds skeletons).
        source_root = provisional_root(root, tracker)
    except SocomError as exc:
        pytest.skip(str(exc))
    try:
        manifest, snapshot = build_manifest(root, tracker, graph_path=root / "build" / "source-graph" / "graph.json",
                                            source_root=source_root)
    except SocomError as exc:
        # A stage 4 plan the wave in flight revises: its accepted version is no longer on disk.
        before = {row["id"]: row for row in live["work_items"]}
        revised = [plan_path(row["id"]) for row in tracker["work_items"] if row.get("kind") in SOURCE_PLAN_KINDS
                   and any(row.get(key) != before[row["id"]].get(key) for key in ("status", "handoff", "accepted", "evidence"))]
        if "changed after acceptance" in str(exc) and any(path in str(exc) for path in revised):
            pytest.skip(f"stage 4 amendments in flight revise {len(revised)} plans the manifest reads: {exc}")
        raise
    assert manifest["manifest_sha256"] == manifest_digest({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    # Over the plans the stored manifest cites, a rebuild reproduces it and its frozen body snapshot exactly.
    stored = load_json(root / MANIFEST_PATH) if (root / MANIFEST_PATH).is_file() else None
    if stored is not None and stored["inputs"]["plans"] == manifest["inputs"]["plans"] and (root / SNAPSHOT_PATH).is_file():
        assert manifest["manifest_sha256"] == stored["manifest_sha256"]
        assert snapshot["snapshot_sha256"] == load_json(root / SNAPSHOT_PATH)["snapshot_sha256"]
    s1 = manifest["s1"]
    assert s1["checked"] == manifest["summary"]["functions"] > 4000
    assert all(any("function-local class" in problem for problem in row["problems"]) for row in s1["failures"])
    bodies = manifest["bodies"]["definitions"]
    assert sorted(row["id"] for row in bodies) == sorted(row["id"] for row in snapshot["bodies"])
    assert {row["action"] for row in bodies} <= set(BODY_ACTIONS)
    assert all(row.get("holding_file") for row in bodies if row["action"] == "bd4-holding")
    assert all(row["rewrite"]["declarator"] for row in bodies if row["action"] == "bd6-declarator-rewrite")
    # Each planned row is claimed by at most one body.
    claimed = [row["row"]["artifact"] for row in bodies if row.get("row")]
    assert len(claimed) == len(set(claimed))
    for entry in manifest["signatures"]:
        assert {entry["return"]["source"], entry["member"]["source"]} <= set(SIGNATURE_SOURCES)
    for entry in manifest["data"]:
        assert entry["type"]["source"] in DATA_TYPE_SOURCES
        assert (entry["initializer"]["kind"] == "none") == entry["nobits"]
    assert {row["kind"] for row in manifest["judgment"]} <= set(JUDGMENT_KINDS)
    # Ghidra's untyped pointer is never a class: void *, or const char * where it points at a string literal.
    generic = [entry for entry in manifest["data"] if entry["type"].get("generic_pointer")]
    assert generic and all(entry["type"]["basis"] == "pointer" for entry in generic)
    for entry in generic:
        literal = any("literal" in row and row["offset"] == 0 for row in entry["initializer"].get("relocations") or [])
        spelled = "const char *" if literal else "void *"
        assert entry["declaration_type"].startswith(spelled), entry["name"]
    assert not any(row.get("type") == "pointer" for row in manifest["judgment"])
    assert not any(row.get("type") == "pointer" for row in manifest["declarations"]["types"])
    # Declarations for the header writer: every own vtable slot carries its declaration; complete types carry their record.
    for record in manifest["declarations"]["classes"]:
        for row in (record.get("vtable") or {}).get("declare_virtual") or []:
            assert {"declared", "planned", "declaration", "mentions"} <= set(row)
            assert row["declaration"] is None or row["declaration"].startswith("virtual ")
    enums = [row for row in manifest["declarations"]["types"] if (row.get("definition") or {}).get("kind") == "enum"]
    assert enums and all(row["definition"]["enumerators"] for row in enums)
    assert all(row["record"]["source"] in ("dwarf", "stage3") for row in manifest["declarations"]["types"] if row.get("definition"))
    assert all("mentions" in entry for entry in manifest["signatures"] if entry["linkage"] == "C++" and entry["s1"]["ok"])
