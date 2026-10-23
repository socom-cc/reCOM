from __future__ import annotations

from pathlib import Path

import pytest

from tools._socom.type_layout import (
    CallParameters,
    _Family,
    class_layout,
    mangled_qualifier,
    parameter_registers,
    render_layout,
    site_index,
    source_bits,
)
from tools._socom.mwdemangle import demangle
from tools._socom.util import SocomError, canonical_json


@pytest.fixture(scope="module")
def cvisual(root: Path) -> dict:
    return class_layout(root, "zdb::CVisual", with_derived=True)


def _class(report: dict, name: str) -> dict:
    return next(row for row in report["classes"] if row["class"] == name)


def _offset(row: dict, offset: int) -> dict:
    return next(entry for entry in row["offsets"] if entry["offset"] == offset)


def test_mangled_qualifier_and_parameter_registers() -> None:
    assert mangled_qualifier(["zdb", "CVisual"]) == "Q23zdb7CVisual"
    assert mangled_qualifier(["C2DVisual"]) == "9C2DVisual"
    with pytest.raises(SocomError):
        mangled_qualifier(["std", "vector<int>"])
    params = demangle("AttachDecal__Q23zdb7CVisualFUifUiPPQ23zdb10AddonPointPQ23zdb10CTexHandle")["params"]
    rows, complete = parameter_registers(params, has_this=True)
    assert complete
    # Floats take f12.. independently; everything else the next of a0-t3.
    assert [name for name, _value in rows] == ["a1", "f12", "a2", "a3", "t0"]
    by_value = demangle("Create__Q28Particle20Destruction_InstanceFRC6CPnt4DRC6CPnt4DRC6CPnt3DfffPQ23zdb7CVisual6CPnt3DPQ28Particle5Props")["params"]
    rows, complete = parameter_registers(by_value, has_this=False)
    assert not complete and [name for name, _value in rows] == ["a0", "a1", "a2", "f12", "f13", "f14", "a3"]


def test_source_bits_follows_shifts_and_masks() -> None:
    byte = (("ld", (("arg", 4), 1), 1, "int", False), 0)
    assert source_bits(byte) == 0xFF
    # dsll32 29 / dsrl32 31 (sll 61, srl 63) extracts bit 2 of the byte.
    assert source_bits((("bits", byte, (("dsll", 61), ("dsrl", 63))), 0)) == 0x4
    word = (("ld", (("arg", 4), 0), 4, "int", None), 0)
    assert source_bits((("bits", word, (("and", 0x100),)), 0)) == 0x100


def test_cvisual_family_sizes_bases_and_vtables(cvisual: dict) -> None:
    assert [row["class"] for row in cvisual["classes"]] == [
        "zdb::CVisual", "zdb::tag_VIS_PARAMS", "C2DVisual", "zdb::CMesh", "zdb::CSubMesh",
    ]
    visual = _class(cvisual, "zdb::CVisual")
    assert visual["size_evidence"] == [0x68]
    assert visual["bases"] == [{"class": "zdb::tag_VIS_PARAMS", "offset": 0}]
    assert {row["address"] for row in visual["rtti"]} == {"0x44f830", "0x459950", "0x4599e0", "0x4616c0"}
    assert visual["vtable"]["address"] == "0x472e90" and len(visual["vtable"]["slots"]) == 7
    assert visual["vtable"]["slots"][0]["mangled"] == "__dt__Q23zdb7CVisualFv"
    assert _class(cvisual, "zdb::CMesh")["size_evidence"] == [0x8c]
    assert _class(cvisual, "zdb::CSubMesh")["size_evidence"] == [0x70]
    assert _class(cvisual, "C2DVisual")["size_evidence"] == [0x70]
    for name in ("zdb::CMesh", "zdb::CSubMesh", "C2DVisual"):
        row = _class(cvisual, name)
        assert {"class": "zdb::CVisual", "offset": 0} in row["bases"]
        assert [call["this_adjustment"] for call in row["base_constructor_calls"]] == [0]


def test_inlined_derived_constructor_is_typed_by_its_vtable(cvisual: dict) -> None:
    # CMesh::Clone allocates 0x8c, calls the CVisual constructor, then stores
    # CMesh's vtable: the object is a CMesh, not a CVisual.
    visual = _class(cvisual, "zdb::CVisual")
    mesh = _class(cvisual, "zdb::CMesh")
    assert all(row["function"] != "0x30f330" for row in visual["allocations"])
    clone = next(row for row in mesh["allocations"] if row["function"] == "0x30f330")
    assert clone["size"] == 0x8c and clone["constructor"] == "zdb::CVisual::__ct(void)"
    assert clone["vtable_stores"]


def test_cvisual_accesses_cover_vptr_bitfields_and_flag_conflicts(cvisual: dict) -> None:
    visual = _class(cvisual, "zdb::CVisual")
    vptr = _offset(visual, 0x20)
    assert vptr["vtable_stores"] == ["__vt__Q23zdb7CVisual+0x0"]
    assert {site["site"] for site in vptr["sites"]} >= {"0x30de70"}
    bits = _offset(visual, 0x0)
    assert "0x2" in bits["bitfield_masks"] and bits["conflicts"] == ["widths [1, 4]"]
    refcount = _offset(visual, 0x18)
    assert refcount["widths"] == [4] and refcount["kinds"] == ["int", "zero"]
    # A word moved through an FPR, or a store of zero, proves neither int nor float.
    centroid = _offset(visual, 0xC)
    assert set(centroid["kinds"]) == {"fpr-copy", "zero"} and not centroid["conflicts"]
    # VuUpdate reads past the allocation size (a CMesh field through a CVisual this).
    beyond = _offset(visual, 0x6C)
    assert beyond["conflicts"] == ["beyond the allocation size 0x68"]
    assert {site["function"] for site in beyond["sites"]} == {"0x30a900"}
    # Inner accesses of a typed sub-object are marked, not flagged.
    inner = _offset(visual, 0x28)
    assert inner["inside_subobject"] and not inner["conflicts"]
    sub = _class(cvisual, "zdb::CSubMesh")
    owner = _offset(sub, 0x6C)
    assert any("zdb::CMesh*" in site.get("value", "") for site in owner["sites"])


def test_receivers_are_proven_or_listed(cvisual: dict) -> None:
    visual = _class(cvisual, "zdb::CVisual")
    by_address = {row["address"]: row for row in visual["members"]}
    assert by_address["0x30de40"]["receiver"] == "constructor"
    assert by_address["0x30c990"]["receiver"].startswith("virtual: slot __vt__Q23zdb7CVisual+")
    assert by_address["0x30d290"]["receiver"].startswith("reads a0")
    # LandmarkEnable(bool) reads only a0, which a static function also takes.
    assert by_address["0x30cfb0"]["receiver"] is None
    assert "0x30cfb0" in {row["function"] for row in visual["unresolved"]}


def test_layout_is_deterministic_and_renders(root: Path, cvisual: dict) -> None:
    again = class_layout(root, "zdb::CVisual", with_derived=True)
    assert canonical_json(again) == canonical_json(cvisual)
    text = render_layout(cvisual)
    assert "## zdb::CVisual [requested]" in text and "0x30de70 sw v1,32(v0)" in text
    index = site_index(cvisual)
    assert 0x20 in index["zdb::CVisual"]
    with pytest.raises(SocomError):
        class_layout(root, "zdb::NoSuchClass")


def _call_rows(report: dict) -> list[dict]:
    return [
        site
        for cls in report["classes"]
        for site in [row for entry in cls["offsets"] for row in entry["sites"]] + cls["object_passes"]
        if site["access"].endswith("-passed")
    ]


def test_every_call_row_types_its_register_or_says_why_not(cvisual: dict) -> None:
    rows = {(site["site"], site["register"]): site for site in _call_rows(cvisual)}
    for site in rows.values():
        assert sum(key in site for key in ("parameter_type", "no_parameter", "parameter_unknown")) == 1, site
    # Regression: Clone's inlined vector assignments pass the end of each pointer vector to
    # compile_assert<1>::__as, a member operator whose a1 was left untyped.
    for site, offset in (("0x30f454", 0x30), ("0x30f46c", 0x3C), ("0x30f484", 0x48)):
        row = rows[(site, "a1")]
        assert (row["offset"], row["parameter_type"]) == (offset, "Metrowerks::compile_assert<1> const&")
    assert rows[("0x30f490", "a1")]["parameter_type"].startswith("std::vector<zdb::CTexHandle*")
    # SetMeshBuffer's receiver is unproven: its a0 reading is not guessed from the static form.
    assert rows[("0x30f860", "a0")]["parameter_unknown"] == (
        "receiver unproven: zdb::CMesh * (receiver) if a member, _word128* if static"
    )
    assert rows[("0x30f59c", "a1")]["parameter_unknown"] == "no mangled parameter list or DWARF subprogram"  # memcpy
    assert rows[("0x24295c", "a2")]["no_parameter"] is True  # CNode::GetMesh(void) takes only its receiver


def test_member_operators_and_dwarf_this_prove_receivers(root: Path) -> None:
    family = _Family(root, "zdb::CVisual", with_derived=True)
    # compile_assert<1>::__as reads only a0, but an operator= is never static.
    assert family.receivers.proof(0x1FC760).startswith("member operator=")
    assert family.receivers.proof(0x1E7F30) == "DWARF formal parameter this"  # zdb::CCamera::Update
    parameters = CallParameters(family.symbols, family.receivers)
    assert parameters.of(0x1FC760, "a1") == {"parameter_type": "Metrowerks::compile_assert<1> const&"}
    # An unproven receiver types a register where the member and static readings agree.
    assert parameters.of(0x30F050, "a1") == {"parameter_type": "_word128*"}
    assert parameters.of(0x30F050, "a3") == {"parameter_unknown": "receiver unproven: _word128* if a member, no parameter if static"}
    assert parameters.of(0x229510, "a1") == {"no_parameter": True}
    assert parameters.of(None, "a0") == {"parameter_unknown": "indirect call: the callee is not known"}
