"""The release lane's Metrowerks demangler: literal symbols, the strict entry point, the whole ELF."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import mwmangle as mw

ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_ELF = ROOT / "support" / "socom.elf"
needs_elf = pytest.mark.skipif(not PROTOTYPE_ELF.is_file(), reason="support/socom.elf is not present")


# Every form the grammar knows with the C++ text it renders as. Most are symbols of
# support/socom.elf; the synthetic ones cover codes the ELF does not use.
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
    # the brief's examples (symbols of the prototype ELF)
    ("PrepModels__9CGameMenuFRC14CGameDlgDesign", "function", "CGameMenu::PrepModels(const CGameDlgDesign &)"),
    ("RunEventAnim__9CGameMenuFQ210ActionItem5EVENTPCc", "function",
     "CGameMenu::RunEventAnim(ActionItem::EVENT, const char *)"),
    ("GetChild__11CDlgObjSpecCFi", "function", "CDlgObjSpec::GetChild(int) const"),
    ("__ct__Q310Metrowerks7details62compressed_pair_imp<Q23std28allocator<15CDlgDesignModel>,Ui,1>FUi",
     "function",
     "Metrowerks::details::compressed_pair_imp<std::allocator<CDlgDesignModel>, unsigned int, 1>"
     "::compressed_pair_imp(unsigned int)"),
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
    ("__dt__Q23std46vector<8AnimType,Q23std20allocator<8AnimType>>Fv", "function",
     "std::vector<AnimType, std::allocator<AnimType> >::~vector()"),
    ("__opi__Q221@unnamed@zui_skb_cpp@10CInit<i,0>CFv", "function",
     "(anonymous namespace)::CInit<int, 0>::operator int() const"),
    ("Get__9Table<-1>Fv", "function", "Table<-1>::Get()"),
    ("DrawFunc<11CDynGrenade>__2aiFQ22ai9LINE_TYPEffUi11CDynGrenade", "function",
     "ai::DrawFunc<CDynGrenade>(ai::LINE_TYPE, float, float, unsigned int, CDynGrenade)"),
    ("__selection_sort<P7CTarget,PFRC7CTargetRC7CTarget_b>__3stdFP7CTargetP7CTargetPFRC7CTargetRC7CTarget_b",
     "function",
     "std::__selection_sort<CTarget *, bool (*)(const CTarget &, const CTarget &)>"
     "(CTarget *, CTarget *, bool (*)(const CTarget &, const CTarget &))"),
    # unnamed namespaces and function-local classes
    ("AccessKey__24@unnamed@zNetMedius_cpp@", "data", "(anonymous namespace)::AccessKey"),
    ("Decr__Q321@unnamed@zui_skb_cpp@13CSoftKeyboard21Local$2354zui_skb_cppFi", "function",
     "(anonymous namespace)::CSoftKeyboard::Local::Decr(int)"),
    # parameter types: function pointers, arrays, references, members, varargs, 128-bit
    ("sceVu0ClipBBox__FPA4_fP5PNT4D", "function", "sceVu0ClipBBox(float (*)[4], PNT4D *)"),
    ("Load__FRA4_A4_f", "function", "Load(float (&)[4][4])"),
    ("Set__FPFi_PCc", "function", "Set(const char *(*)(int))"),
    ("Print__FPCce", "function", "Print(const char *, ...)"),
    ("Scan__FPCPCcCPc", "function", "Scan(const char *const *, char *const)"),
    ("Wide__FwPVUsxUxrSc", "function",
     "Wide(wchar_t, volatile unsigned short *, long long, unsigned long long, long double, signed char)"),
    ("Field__FM3Fooi", "function", "Field(int Foo::*)"),
    ("SetupTeam__Q228@unnamed@hud_scorepopup_cpp@12CTeamDisplayFffffPCcM9CZNetGameFPCvPCv_ib", "function",
     "(anonymous namespace)::CTeamDisplay::SetupTeam(float, float, float, float, const char *, "
     "int (CZNetGame::*)() const, bool)"),
    ("zSysAddDMA__FP1P1", "function", "zSysAddDMA(unsigned __int128 *, unsigned __int128 *)"),
    ("Deep__Q_10_1a1b1c1d1e1f1g1h1i1jFv", "function", "a::b::c::d::e::f::g::h::i::j::Deep()"),
    # classified forms
    ("__vt__8CAiSGoto", "vtable", "virtual table of CAiSGoto"),
    ("@136@UpdateUIVar__17CRenderableStringFP11CUIVariable", "thunk",
     "this-adjusting thunk (136) to CRenderableString::UpdateUIVar(CUIVariable *)"),
    ("__sinit_ai_astar.cpp", "static_initializer", "static initializer of ai_astar.cpp"),
    ("main", "c_name", "C or assembler name main"),
    ("c__1", "c_name", "C or assembler name c__1"),
]


@pytest.mark.parametrize(("name", "kind", "text"), FIXTURES)
def test_every_form_parses_renders_and_mangles_back(name, kind, text):
    row = mw.demangle(name)
    assert row["kind"] == kind
    assert row["round_trip"] is True
    assert mw.mangle(json.loads(json.dumps(row["structured"]))) == name
    rendered = row["rendered"]
    assert (rendered.get("declaration") or rendered["text"]) == text


def test_function_parts_of_the_briefs_examples():
    parts = mw.function_parts(mw.demangle_function("RunEventAnim__9CGameMenuFQ210ActionItem5EVENTPCc"))
    assert parts["scope"] == ["CGameMenu"] and parts["name"] == "RunEventAnim" and parts["form"] == "ordinary"
    assert parts["const"] is False and parts["varargs"] is False
    enum, text = parts["params"]
    assert enum == {"t": "named", "name": [{"name": "ActionItem"}, {"name": "EVENT"}]}
    assert text == {"t": "pointer", "to": {"t": "builtin", "code": "c", "cv": "C"}}

    parts = mw.function_parts(mw.demangle_function("GetChild__11CDlgObjSpecCFi"))
    assert parts["const"] is True and parts["params"] == [{"t": "builtin", "code": "i"}]

    parts = mw.function_parts(mw.demangle_function("PrepModels__9CGameMenuFRC14CGameDlgDesign"))
    assert parts["params"] == [{"t": "reference", "to": {"t": "named", "name": [{"name": "CGameDlgDesign"}],
                                                          "cv": "C"}}]

    parts = mw.function_parts(mw.demangle_function(
        "__ct__Q310Metrowerks7details62compressed_pair_imp<Q23std28allocator<15CDlgDesignModel>,Ui,1>FUi"))
    assert parts["form"] == "constructor"
    assert parts["scope"] == ["Metrowerks", "details",
                              "compressed_pair_imp<std::allocator<CDlgDesignModel>, unsigned int, 1>"]
    template = parts["scope_nodes"][2]["args"]
    assert template[1] == {"t": "builtin", "code": "i", "sign": "U"} and template[2] == {"t": "value", "value": "1"}


def test_function_parts_no_parameter_varargs_and_thunks():
    assert mw.function_parts(mw.demangle_function("__dt__10CZSealBodyFv"))["params"] == []
    parts = mw.function_parts(mw.demangle_function("Print__FPCce"))
    assert parts["varargs"] is True and len(parts["params"]) == 1 and parts["scope"] == []
    parts = mw.function_parts(mw.demangle_function("@136@UpdateUIVar__17CRenderableStringFP11CUIVariable"))
    assert parts["thunk_offsets"] == [136] and parts["name"] == "UpdateUIVar"
    for form, name in (("operator", "__as__6CPnt3DFRC6CPnt3D"), ("conversion", "__opf__6RfloatCFv"),
                       ("destructor", "__dt__10CZSealBodyFv"), ("function-template", "Get<i>__3FooFv")):
        assert mw.function_parts(mw.demangle_function(name))["form"] == form


def test_strict_entry_point_fails_loudly():
    assert mw.demangle_function("main") is None
    assert mw.demangle_function("sceSifCheckStatRpc") is None
    assert mw.demangle_function("__sinit_ai_astar.cpp") is None
    for bad in ("Tick__10CZSealBodyFq",          # unknown type code
                "Tick__10CZSealBodyFP",          # ends inside a type
                "Tick__20CZSealBodyFf",          # the length prefix runs past the end
                "Tick__10CZSealBodyF",           # F without a parameter code
                "Tick__10CZSealBodyFfX",         # a code left over after the parameters
                "Tick__Q110CZSealBodyFf",        # Q with one name
                "Get__3Foo<i,Fv"):               # an unclosed template
        with pytest.raises(mw.MangleError):
            mw.demangle_function(bad)
    with pytest.raises(mw.MangleError):
        mw.demangle_function("__vt__8CAiSGoto")  # a vtable is no function
    with pytest.raises(mw.MangleError):
        mw.function_parts(mw.parse_symbol("f__FvPv"))  # void in the middle of a parameter list


def test_measure_counts_and_groups_failures():
    report = mw.measure(["Tick__10CZSealBodyFf", "main", "__sinit_x.cpp", "Tick__10CZSealBodyFq",
                         "Tock__10CZSealBodyFq", "__opf__6RfloatCFv"])
    assert (report["parsed"], report["not_mangled"], report["failed"]) == (2, 2, 2)
    assert report["not_mangled_kinds"] == {"c_name": 1, "static_initializer": 1}
    assert report["failures_by_shape"] == {
        "'...' looks mangled but does not parse to its end": {
            "count": 2, "examples": ["Tick__10CZSealBodyFq", "Tock__10CZSealBodyFq"]}}
    assert report["ambiguous"] == []  # a conversion operator's two readings agree


def test_project_type_names_follow_the_prototype_archive():
    # names and categories as the prototype's DWARF import has them (list_data_types of socom.elf)
    scope = mw.demangle_function("__dt__Q23std46vector<8AnimType,Q23std20allocator<8AnimType>>Fv")["scope"]
    node = {"t": "named", "name": scope}
    assert mw.type_name(node) == "vector<AnimType, std::allocator<AnimType>>"
    assert mw.type_category(node) == "/project/std"
    node = mw.parse_symbol("f__FRCQ33std42__list_deleter<PCv,Q23std14allocator<PCv>>19generic_iterator<0>")[
        "params"][0]["to"]
    assert mw.type_name(node) == "generic_iterator<0>"
    assert mw.type_category(node) == "/project/std/__list_deleter<void const*, std::allocator<void const*>>"
    assert mw.readable_type(mw.parse_symbol("f__FPFi_PCc")["params"][0]) == "char const* (*)(int)"
    assert mw.readable_type(mw.parse_symbol("f__FCPc")["params"][0]) == "char* const"
    assert mw.readable_type(mw.parse_symbol("f__FPA4_f")["params"][0]) == "float[4]*"
    assert mw.readable_type(mw.parse_symbol("f__FP1")["params"][0]) == "uint16*"
    with pytest.raises(mw.MangleError):
        mw.type_name({"t": "builtin", "code": "i"})


# -- the prototype ELF ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def prototype_symbols():
    import elfimage

    return elfimage.load(PROTOTYPE_ELF, "prototype").symbols


@needs_elf
def test_every_function_symbol_of_the_prototype(prototype_symbols):
    names = [s.name for s in prototype_symbols if s.kind == 2]
    report = mw.measure(names)
    assert report["failed"] == 0, report["failures_by_shape"]
    assert report["ambiguous"] == []
    assert report["names"] == len(set(names)) == 9672
    assert report["parsed"] == 6844
    assert report["not_mangled_kinds"] == {"array_destructor": 13, "c_name": 2667, "static_initializer": 148}


@needs_elf
def test_every_symbol_of_the_prototype_round_trips(prototype_symbols):
    for symbol in prototype_symbols:
        row = mw.demangle(symbol.name, "SECTION" if symbol.kind == 3 else None)
        assert row["round_trip"], symbol.name


@needs_elf
def test_real_symbols_by_address(prototype_symbols):
    by_name = {s.name: s for s in prototype_symbols if s.kind == 2}
    for name in ("PrepModels__9CGameMenuFRC14CGameDlgDesign", "RunEventAnim__9CGameMenuFQ210ActionItem5EVENTPCc",
                 "GetChild__11CDlgObjSpecCFi", "zSysAddDMA__FP1P1"):
        assert name in by_name, name
        assert mw.demangle_function(name)["kind"] == "function"
