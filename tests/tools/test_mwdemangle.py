from __future__ import annotations

from tools._socom.mwdemangle import (
    demangle,
    readable_qualified,
    render_type,
    split_qualified,
    template_base,
)


def test_member_function_with_nested_qualifier_and_enum_parameter() -> None:
    value = demangle("SetDefaults__Q28CZWeapon9AI_PARAMSF10EQUIP_ITEM")
    assert value is not None
    assert value["name"] == "SetDefaults"
    assert readable_qualified(value["qualifier"]) == "CZWeapon::AI_PARAMS"
    assert [render_type(param) for param in value["params"]] == ["EQUIP_ITEM"]


def test_constructor_const_method_and_reference_parameters() -> None:
    constructor = demangle("__ct__9AI_PARAMSFRC9AI_PARAMS")
    assert constructor["name"] == "__ct"
    assert [render_type(param) for param in constructor["params"]] == [
        "AI_PARAMS const&"
    ]
    accessor = demangle("GetAccuracy__Q28CZWeapon9AI_PARAMSCFf")
    assert accessor["const"] is True
    assert [render_type(param) for param in accessor["params"]] == ["float"]


def test_template_qualifiers_render_readably() -> None:
    value = demangle(
        "__dt__Q23std46vector<8AnimType,Q23std20allocator<8AnimType>>Fv"
    )
    assert readable_qualified(value["qualifier"]) == (
        "std::vector<AnimType, std::allocator<AnimType>>"
    )
    assert template_base(value["qualifier"][-1]) == "vector"
    function_template = demangle(
        "do_assign<PC3LOD>__Q23std44__vector_imp<3LOD,Q23std15allocator<3LOD>,0>"
        "FPC3LODPC3LODQ23std20forward_iterator_tag"
    )
    assert function_template["name"] == "do_assign<PC3LOD>"
    assert readable_qualified(function_template["qualifier"]) == (
        "std::__vector_imp<LOD, std::allocator<LOD>, 0>"
    )
    assert len(function_template["params"]) == 3


def test_pointer_parameters_and_namespaces() -> None:
    value = demangle("Parse__3C2DFP5_zrdrPQ23zdb9CAssetLibPQ23zdb16CTextureRelocMgr")
    assert readable_qualified(value["qualifier"]) == "C2D"
    assert [render_type(param) for param in value["params"]] == [
        "_zrdr*",
        "zdb::CAssetLib*",
        "zdb::CTextureRelocMgr*",
    ]


def test_static_data_member_and_non_cxx_names() -> None:
    data = demangle("version__Q28CZWeapon9AI_PARAMS")
    assert data["params"] is None
    assert readable_qualified(data["qualifier"]) == "CZWeapon::AI_PARAMS"
    assert demangle(".p__sinit_main.cpp") is None
    assert demangle("__ps2_libinfo__") is None
    assert demangle("main") is None


def test_split_qualified_ignores_template_separators() -> None:
    assert split_qualified(
        "std::vector<zdb::CTexHandle*, std::allocator<zdb::CTexHandle*>>"
    ) == ["std", "vector<zdb::CTexHandle*, std::allocator<zdb::CTexHandle*>>"]
    assert split_qualified("CHUD") == ["CHUD"]


def test_function_and_member_function_pointers_render_as_declarators() -> None:
    value = demangle("Set__3FooFPFPCvPv_v")
    assert [render_type(param) for param in value["params"]] == [
        "void (*)(void const*, void*)"
    ]
    member = demangle(
        "push__3BarFRCM16CCnfStateMachineFPCvPvQ216CCnfStateMachine10STATE_FLAG_v"
    )
    assert [render_type(param) for param in member["params"]] == [
        "void (CCnfStateMachine::* const&)(void const*, void*, CCnfStateMachine::STATE_FLAG)"
    ]
