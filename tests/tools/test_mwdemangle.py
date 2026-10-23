from __future__ import annotations

from tools._socom.mwdemangle import (
    INT128_SPELLING,
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


def _params(mangled: str) -> list[str]:
    value = demangle(mangled)
    assert value is not None, mangled
    return [render_type(param) for param in value["params"]]


def test_code_1_is_the_128_bit_integer_not_a_one_letter_class() -> None:
    # socom.elf: SetBilinear(qword buffer, 0/1 in a2); TakeDrawPacket
    # forwards a1/a2 to zSysFifoKick (0x3805f0).  Not a class U then int.
    assert _params("SetBilinear__Q23zdb8CVisDataFP1Ui") == ["uint16*", "unsigned int"]
    assert _params("zSysFifoKick__FP1Ui") == ["uint16*", "unsigned int"]
    assert _params("ReadGsMemory__6CVideoFUiP1Ui") == ["unsigned int", "uint16*", "unsigned int"]
    # Not a class named i: callers pass a2 too (0x2f9c24).
    assert _params("MakeChain__Q23zdb12CGSTexBufferFP1i") == ["uint16*", "int"]
    value = demangle("MakeChain__Q23zdb12CGSTexBufferFP1i")
    assert value["params"][0] == {"modifiers": ["P"], "kind": "builtin", "name": INT128_SPELLING}


def test_code_1_ends_names_and_follows_any_modifier() -> None:
    # A name may end in P1 (no class name follows) and 1 may repeat.
    assert _params("ReplaceTextureData__Q23zdb8CVisDataFP1") == ["uint16*"]
    assert _params("zSysAddDMA__FP1P1") == ["uint16*", "uint16*"]
    assert _params("zSysSprGetPacket__FPP1") == ["uint16**"]
    insert = demangle("insert__Q23std38__vector_imp<1,Q23std12allocator<1>,0>FP1UiRC1")
    assert [render_type(param) for param in insert["params"]] == ["uint16*", "unsigned int", "uint16 const&"]
    # A bare template argument 1 stays literal: compile_assert<1> is a value.
    assert readable_qualified(insert["qualifier"]) == "std::__vector_imp<1, std::allocator<1>, 0>"
    assert _params("resize__Q23std38__vector_imp<1,Q23std12allocator<1>,0>FUiRC1") == [
        "unsigned int",
        "uint16 const&",
    ]


def test_lengths_starting_with_1_and_nested_one_letter_names_are_kept() -> None:
    assert _params("GetButtonState__13CCtrlrConfigsFQ210PadBtnFunc1_RC4CPad") == [
        "PadBtnFunc::_",
        "CPad const&",
    ]
    assert readable_qualified(demangle("MakeChain__Q23zdb12CGSTexBufferFP1i")["qualifier"]) == "zdb::CGSTexBuffer"
    assert _params("SetButtonState__13CCtrlrConfigsFP4CPadQ210PadBtnFunc1_9KEY_STATE") == [
        "CPad*",
        "PadBtnFunc::_",
        "KEY_STATE",
    ]
    # U and S do not combine with the 128-bit code.
    assert demangle("f__FU1") is None


def test_consumers_spell_the_128_bit_type_as_the_dwarf_import_does() -> None:
    from tools._socom.batch_apply import BUILTIN_SIZES, BUILTINS
    from tools._socom.type_apply import FUND_TYPES, INT128_FUND
    from tools._socom.type_layout import parameter_registers
    from tools._socom.type_plan_evidence import parameter_class

    # DWARF 0xA510 and the mangled code 1 name the same 16-byte builtin.
    assert BUILTINS[INT128_SPELLING] == FUND_TYPES[INT128_FUND].ghidra == "uint16"
    assert BUILTIN_SIZES[BUILTINS[INT128_SPELLING]] == 16
    # A pointer to it names no class sub-object.
    assert parameter_class("uint16*") is None
    # SetBilinear(this, uint16 *, unsigned int): a0, a1, a2.
    value = demangle("SetBilinear__Q23zdb8CVisDataFP1Ui")
    rows, complete = parameter_registers(value["params"], has_this=True)
    assert complete and [register for register, _ in rows] == ["a1", "a2"]
