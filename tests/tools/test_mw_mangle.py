from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tools._socom.elf import Elf32File
from tools._socom.mw_mangle import (
    MangleError,
    demangle,
    mangle,
    mangle_type,
    parse_symbol,
    render,
    render_type,
    symbol_report,
)


def _declaration(name: str) -> str:
    row = demangle(name)
    assert row["round_trip"], row
    rendered = row["rendered"]
    return rendered.get("declaration") or rendered["text"]


# Every form the grammar knows, each with the C++ text it renders as.  Most
# are ELF symbols; the synthetic ones cover codes the ELF does not use.
FIXTURES = [
    # member, free and namespace functions; const members
    ("Tick__10CZSealBodyFf", "function", "CZSealBody::Tick(float)"),
    ("Tick__FP10CZSealBodyf", "function", "Tick(CZSealBody *, float)"),
    ("AbortPathPlan__2aiFP7CAiPath", "function", "ai::AbortPathPlan(CAiPath *)"),
    ("Acquire__14CCharacterTypeCFv", "function", "CCharacterType::Acquire() const"),
    ("SetDefaults__Q28CZWeapon9AI_PARAMSF10EQUIP_ITEM", "function", "CZWeapon::AI_PARAMS::SetDefaults(EQUIP_ITEM)"),
    ("AbortLoad__10CLoadStateFPCc", "function", "CLoadState::AbortLoad(const char *)"),
    ("Get__3FooVFv", "function", "Foo::Get() volatile"),
    ("Get__3FooCVFv", "function", "Foo::Get() const volatile"),
    # special names
    ("__ct__9AI_PARAMSFRC9AI_PARAMS", "function", "AI_PARAMS::AI_PARAMS(const AI_PARAMS &)"),
    ("__dt__10CZSealBodyFv", "function", "CZSealBody::~CZSealBody()"),
    ("__as__6CPnt3DFRC6CPnt3D", "function", "CPnt3D::operator=(const CPnt3D &)"),
    ("__pl__6CPnt3DCFRC6CPnt3D", "function", "CPnt3D::operator+(const CPnt3D &) const"),
    ("__cl__7CMatrixCFUiUi", "function", "CMatrix::operator()(unsigned int, unsigned int) const"),
    ("__nw__FUi", "function", "operator new(unsigned int)"),
    ("__dla__FPv", "function", "operator delete[](void *)"),
    ("__opf__6RfloatCFv", "function", "Rfloat::operator float() const"),
    ("__opPCc__3StrCFv", "function", "Str::operator const char *() const"),
    ("__defctor__Q23zdb11DiIntersectFv", "function", "zdb::DiIntersect::__defctor()"),
    # templates: types and integer values, nested, function templates
    (
        "__dt__Q23std46vector<8AnimType,Q23std20allocator<8AnimType>>Fv",
        "function",
        "std::vector<AnimType, std::allocator<AnimType> >::~vector()",
    ),
    (
        "__opi__Q221@unnamed@zui_skb_cpp@10CInit<i,0>CFv",
        "function",
        "(anonymous namespace)::CInit<int, 0>::operator int() const",
    ),
    ("Get__9Table<-1>Fv", "function", "Table<-1>::Get()"),
    (
        "DrawFunc<11CDynGrenade>__2aiFQ22ai9LINE_TYPEffUi11CDynGrenade",
        "function",
        "ai::DrawFunc<CDynGrenade>(ai::LINE_TYPE, float, float, unsigned int, CDynGrenade)",
    ),
    (
        "CompareT<Q26CAiMap4name>__FRCQ26CAiMap4nameRCQ26CAiMap4name",
        "function",
        "CompareT<CAiMap::name>(const CAiMap::name &, const CAiMap::name &)",
    ),
    (
        "__selection_sort<P7CTarget,PFRC7CTargetRC7CTarget_b>__3stdFP7CTargetP7CTargetPFRC7CTargetRC7CTarget_b",
        "function",
        "std::__selection_sort<CTarget *, bool (*)(const CTarget &, const CTarget &)>"
        "(CTarget *, CTarget *, bool (*)(const CTarget &, const CTarget &))",
    ),
    # unnamed namespaces and function-local classes
    ("AccessKey__24@unnamed@zNetMedius_cpp@", "data", "(anonymous namespace)::AccessKey"),
    (
        "Decr__Q321@unnamed@zui_skb_cpp@13CSoftKeyboard21Local$2354zui_skb_cppFi",
        "function",
        "(anonymous namespace)::CSoftKeyboard::Local::Decr(int)",
    ),
    (
        "__ct__Q215C2DWidePolyline29CPnt2D$1514c2dbitmap_poly_cppFff",
        "function",
        "C2DWidePolyline::CPnt2D::CPnt2D(float, float)",
    ),
    # parameter types: function pointers, arrays, references, members, varargs
    ("sceVu0ClipBBox__FPA4_fP5PNT4D", "function", "sceVu0ClipBBox(float (*)[4], PNT4D *)"),
    ("Load__FRA4_A4_f", "function", "Load(float (&)[4][4])"),
    ("Set__FPFi_PCc", "function", "Set(const char *(*)(int))"),
    ("Call__FF_v", "function", "Call(void ())"),
    ("Print__FPCce", "function", "Print(const char *, ...)"),
    ("Scan__FPCPCcCPc", "function", "Scan(const char *const *, char *const)"),
    ("Wide__FwPVUsxUxrSc", "function", "Wide(wchar_t, volatile unsigned short *, long long, unsigned long long, long double, signed char)"),
    ("Field__FM3Fooi", "function", "Field(int Foo::*)"),
    (
        "SetStatLbUiVar__23@unnamed@st_mpexit_cpp@FbPCcM10CZSealBodyFPCvPv_R10CSealStats",
        "function",
        "(anonymous namespace)::SetStatLbUiVar(bool, const char *, CSealStats &(CZSealBody::*)())",
    ),
    (
        "SetupTeam__Q228@unnamed@hud_scorepopup_cpp@12CTeamDisplayFffffPCcM9CZNetGameFPCvPCv_ib",
        "function",
        "(anonymous namespace)::CTeamDisplay::SetupTeam(float, float, float, float, const char *, "
        "int (CZNetGame::*)() const, bool)",
    ),
    ("zSysAddDMA__FP1P1", "function", "zSysAddDMA(unsigned __int128 *, unsigned __int128 *)"),
    ("Deep__Q_10_1a1b1c1d1e1f1g1h1i1jFv", "function", "a::b::c::d::e::f::g::h::i::j::Deep()"),
    # data and the classified forms
    ("m_isinit__7CNetCnf", "data", "CNetCnf::m_isinit"),
    ("__vt__8CAiSGoto", "vtable", "virtual table of CAiSGoto"),
    ("__RTTI__Q23std9exception", "rtti", "RTTI descriptor of std::exception"),
    (
        "@136@UpdateUIVar__17CRenderableStringFP11CUIVariable",
        "thunk",
        "this-adjusting thunk (136) to CRenderableString::UpdateUIVar(CUIVariable *)",
    ),
    (
        "@24@72@__dt__Q23std39basic_istream<w,Q23std14char_traits<w>>Fv",
        "thunk",
        "this-adjusting thunk (24, 72) to std::basic_istream<wchar_t, std::char_traits<wchar_t> >::~basic_istream()",
    ),
    ("__sinit_ai_astar.cpp", "static_initializer", "static initializer of ai_astar.cpp"),
    (".p__sinit_ai_astar.cpp", "static_initializer_pointer", "static initializer table entry of ai_astar.cpp"),
    ("__arraydtor$1945", "array_destructor", "array destructor #1945"),
    ("C$792", "local_static", "local static C (#792)"),
    ("init$600", "local_static_guard", "initialization flag init (#600)"),
    (
        "dummy$localstatic3$next__7CAiPathFv",
        "local_static",
        "local static dummy (#3) of CAiPath::next()",
    ),
    (
        "init$localstatic4$next__7CAiPathFv",
        "local_static_guard",
        "initialization flag init (#4) of CAiPath::next()",
    ),
    (
        "__init__id__Q23std14codecvt<c,c,i>",
        "static_member_guard",
        "initialization flag of std::codecvt<char, char, int>::id",
    ),
    ("@3101", "label", "literal label @3101"),
    ("$L10", "asm_label", "assembler label $L10"),
    ("_$vuFog0", "vu_label", "VU microcode label vuFog0"),
    ("main", "c_name", "C or assembler name main"),
    ("__exception_table_start__", "c_name", "C or assembler name __exception_table_start__"),
    ("c__1", "c_name", "C or assembler name c__1"),
    ("", "empty", "the null symbol"),
]


@pytest.mark.parametrize(("name", "kind", "text"), FIXTURES)
def test_every_form_parses_renders_and_mangles_back(name: str, kind: str, text: str) -> None:
    row = demangle(name)
    assert row["kind"] == kind
    assert row["round_trip"] is True
    assert mangle(json.loads(json.dumps(row["structured"]))) == name
    assert _declaration(name) == text


def test_structured_form_is_derived_not_stored() -> None:
    value = parse_symbol("Tick__10CZSealBodyCFf")
    assert value == {
        "kind": "function",
        "name": {"text": "Tick"},
        "scope": [{"name": "CZSealBody"}],
        "cv": "C",
        "params": [{"t": "builtin", "code": "f"}],
    }
    # The mangler recomputes lengths, Q counts and codes from the structure.
    value["scope"] = [{"name": "zdb"}, {"name": "CVisData"}]
    value["cv"] = ""
    value["params"] = [{"t": "pointer", "to": {"t": "named", "name": [{"name": "CNode"}], "cv": "C"}}]
    assert mangle(value) == "Tick__Q23zdb8CVisDataFPC5CNode"
    value["name"] = {"text": "__ct"}
    assert render(value)["declaration"] == "zdb::CVisData::CVisData(const CNode *)"
    assert render(value)["member_declaration"] == "CVisData(const CNode *)"
    assert render(value)["special"] == "constructor"


def test_member_function_pointer_hidden_parameters_are_recorded() -> None:
    node = parse_symbol("Use__FM9CZNetGameFPCvPCv_ib")["params"][0]
    assert node["t"] == "member_pointer"
    assert node["to"]["member_this"] == "C"
    assert node["to"]["params"] == []
    assert render_type(node) == "int (CZNetGame::*)() const"
    assert mangle_type(node) == "M9CZNetGameFPCvPCv_i"
    # A member function type without the hidden pair keeps its parameters.
    plain = parse_symbol("Use__FM3FooFi_v")["params"][0]
    assert "member_this" not in plain["to"]
    assert mangle_type(plain) == "M3FooFi_v"


def test_template_arguments_keep_values_and_types_apart() -> None:
    value = parse_symbol("__vc__Q23std38__vector_imp<i,Q23std12allocator<i>,1>FUi")
    arguments = value["scope"][1]["args"]
    assert arguments[0] == {"t": "builtin", "code": "i"}
    assert arguments[2] == {"t": "value", "value": "1"}
    assert render(value)["scope"] == "std::__vector_imp<int, std::allocator<int>, 1>"


def test_names_that_are_not_metrowerks_stay_c_names() -> None:
    for name in ("c__1", "__ps2_libinfo__", "__end__catch", "__sinit", "foo__", "a__Fx__", "x__Q13Foo"):
        assert parse_symbol(name)["kind"] == "c_name", name
    assert demangle("c__10")["resembles_mangling"] is True
    assert parse_symbol(".text", "SECTION") == {"kind": "section", "name": ".text"}


def test_invalid_structured_forms_are_refused() -> None:
    with pytest.raises(MangleError):
        mangle({"kind": "function", "name": {"text": "f"}, "scope": None, "cv": "", "params": []})
    with pytest.raises(MangleError):
        mangle_type({"t": "builtin", "code": "q"})
    with pytest.raises(MangleError):
        mangle_type({"t": "builtin", "code": "i", "cv": "K"})
    with pytest.raises(MangleError):
        mangle({"kind": "label", "number": "12"})
    with pytest.raises(MangleError):
        render({"kind": "function", "name": {"text": "__ct"}, "scope": None, "cv": "", "params": [{"t": "builtin", "code": "v"}]})


def test_report_counts_and_failures() -> None:
    report = symbol_report(
        [
            ("Tick__10CZSealBodyFf", "FUNC", "GLOBAL"),
            ("Tick__10CZSealBodyFf", "FUNC", "GLOBAL"),
            ("@12", "OBJECT", "LOCAL"),
            ("main", "FUNC", "GLOBAL"),
            (".text", "SECTION", "LOCAL"),
        ],
        include_rows=True,
    )
    assert report["ok"] is True
    assert report["symbol_count"] == 5
    assert report["name_count"] == 4
    assert report["parsed_names"] == 2
    assert report["plain_names"] == 2
    assert report["categories"]["function"]["symbols"] == 2
    assert report["categories"]["function"]["names"] == 1
    assert report["function_symbols"]["function_global_symbols"] == 2
    assert report["function_forms"] == {"ordinary": 1}
    assert len(report["rows"]) == 4


# -- real data -----------------------------------------------------------------------------


def test_every_elf_symbol_round_trips(reference: Elf32File) -> None:
    symbols = [(row.name, row.type_name, row.binding_name) for row in reference.symbols()]
    report = symbol_report(symbols)
    assert report["ok"] is True, report["failures"][:10]
    assert report["failed_names"] == 0
    assert report["symbol_count"] == len(symbols)
    assert report["round_trip_identical_names"] == report["name_count"]
    assert "error" not in report["categories"]
    # Every FUNC symbol either parses as a Metrowerks form or is a plain C name.
    functions = report["function_symbols"]
    assert functions["round_trip_identical_symbols"] == functions["func_symbols"]
    # The only C names that look mangled are f2c's numbered constants.
    assert all(re.fullmatch(r"c__\d+", name) for name in report["c_names_resembling_mangling"])


def test_authored_functions_round_trip(reference_source_graph: dict) -> None:
    authored = [
        entry["name"]
        for row in reference_source_graph["artifacts"]
        if row["kind"] == "function" and row["classification"].get("candidate") == "authored"
        for entry in row["names"]
    ]
    assert authored
    kinds: dict[str, int] = {}
    for name in authored:
        row = demangle(name)
        assert row["round_trip"], name
        assert not row.get("resembles_mangling"), name
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
    assert set(kinds) <= {"function", "array_destructor", "c_name"}
    assert kinds["function"] > 0.99 * len(authored)


def _run(root: Path, *arguments: str) -> tuple[int, dict]:
    completed = subprocess.run(
        [sys.executable, "tools/socom.py", *arguments],
        cwd=root,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    return completed.returncode, json.loads(completed.stdout) if completed.stdout else {"stderr": completed.stderr}


def test_reference_demangle_command(root: Path) -> None:
    code, result = _run(root, "reference", "demangle", "Tick__10CZSealBodyFf", "__vt__8CAiSGoto")
    assert code == 0
    assert result["ok"] is True
    assert [row["kind"] for row in result["symbols"]] == ["function", "vtable"]
    assert result["symbols"][0]["rendered"]["declaration"] == "CZSealBody::Tick(float)"
    code, _ = _run(root, "reference", "demangle")
    assert code != 0
    code, _ = _run(root, "reference", "demangle", "--all", "main")
    assert code != 0
    code, _ = _run(root, "reference", "demangle", "main", "--output", "outside.json")
    assert code != 0
    assert not (root / "outside.json").exists()
